# 인프라 요청서 — bourbon-agent-discovery-api

> **2026-11-08 현재 상태**: dev PostgreSQL DB와 계정(§1), Redis DB 번호(§3), AMQP 계정(§4)은 받아서 dev가 돌고 있다(2026-09-24부터). 설계가 topic 기반에서 공개 note 기반으로 바뀌면서(`new-type/note-discovery-design.md`) 필요한 것이 달라졌다.
>
> 이번에 부탁드리는 것:
> 1. **(경우에 따라)** dev DB에 `vector` 확장. 우리 관리 계정으로 먼저 만들어 보고, 권한이 없다고 거부되면 부탁드린다(§1-1).
> 2. dev DynamoDB 테이블 삭제. 우리 배포 뒤에(§2).
> 3. RabbitMQ 큐 깊이 상한과 알람. 예전 요청에서 큐 이름만 바뀌었다(§4).
> 4. dev RabbitMQ의 `deferq.count_turn_on_message_created` 삭제(2026-11-12, §4(다)).
>
> 다음 배포는 잠깐 멈춤이 있는 배포다(옛 api·워커를 내리고 마이그레이션을 적용한 뒤 새 코드를 올린다). 그동안 울리는 api·워커 알람은 장애가 아니다. 되돌림은 없다. 우리 데이터는 note-api에서 다시 읽어 만든다(backfill).

## 0. 서비스 개요 (한 단락)

bourbon-agent-discovery-api는 유저의 **공개 note**로 "대화해 볼 사람"을 찾는다. route는 둘이다. 주제 추천(`/recommend/agents`)은 주제로 이야기할 만한 사람을, 답할 사람 찾기(`/recommend/notes`)는 질문에 답할 수 있는 note를 참조로 돌려준다. 입력은 note-api의 note 이벤트와 읽기(본문은 저장하지 않는다), bourbon-api의 탈퇴 이벤트다(대화 이벤트는 2026-11-12부터 받지 않는다). note마다 embedding(768차원)과 tag, note-api 공유 card 연결을 PostgreSQL에 두고, 요청마다 cosine 검색과 사람별 집계를 한다. api Deployment와 deferq 워커 Deployment가 dev에 있다(같은 이미지, 명령만 다름). topic-api와 친구 관계는 더 이상 쓰지 않는다.

## 1. PostgreSQL

**받은 것(2026-09-21)**: 기존 `pensieve-pg-tokyo-dev`(PostgreSQL 18)에 DB `bourbon_agent_discovery`, 관리 계정 `bourbon_agent_discovery_dbadmin`(테이블 소유, 마이그레이션 적용), 앱 계정 `bourbon_agent_discovery_app`(CRUD만). 앱의 접속 문자열은 Secret `bourbon-agent-discovery-api`의 `DATABASE_URL`. 마이그레이션은 우리가 관리 계정으로 bastion 터널을 거쳐 적용한다(배포 파이프라인에 마이그레이션 단계가 없다).

인스턴스를 공유해도 서비스 경계는 흐려지지 않는다. PostgreSQL에서는 한 커넥션이 한 데이터베이스에 묶여서, 같은 인스턴스여도 남의 DB를 읽지 못한다(`postgres_fdw` 없이는). 공유가 실제로 나눠 쓰게 만드는 것은 커넥션 수, 백업 단위, 파라미터 그룹이고, 커넥션 수는 §1-3에 있다.

### 1-1. `vector` 확장 — 다음 배포 전에 필요

note embedding을 `vector(768)` 컬럼에 두고 요청마다 cosine 거리로 검색한다(pgvector). 예전 요청서에서 "pgvector는 나중에 필요해지면 다시 요청한다"고 했던 그 시점이 왔다. 기준 마이그레이션(지금 0016, 그 전 0015와 0013)이 확장이 있는지 먼저 보고, 없으면 무엇을 하라는 메시지와 함께 멈춘다.

- **우리가 먼저 한다:** pgvector는 trusted 확장이라, DB에 CREATE 권한이 있는 계정이면 superuser가 아니어도 만들 수 있다. 관리 계정으로 `CREATE EXTENSION vector;`를 실행해 본다.
- **거부되면 부탁드린다:** 관리 계정에 그 권한이 없거나, RDS가 이 확장을 trusted로 두지 않아 권한 오류가 나면, `rds_superuser` 계정으로 dev DB `bourbon_agent_discovery`에서 같은 문장을 실행해 주세요.
- **가능 여부:** dev 인스턴스에서 켤 수 있다는 것은 2026-11-06에 확인했다. 확장은 DB 단위라 pensieve의 DB에는 영향이 없다.
- **prod:** prod RDS에서 켤 수 있는지는 prod 인프라 세팅 때 다시 묻는다(설계 열린 항목 1). 안 되면 설계 §3-1의 2안으로 간다.

### 1-2. 테이블 정리 (우리가 한다, 알려 드리는 것)

마이그레이션 0012~0014가 topic 시절 테이블 9개를 지우고 새 테이블 6개를 만든다. 앱 계정 권한은 관리 계정이 직접 준다.

**2026-11-10: migration을 기준 하나(0015)로 합쳤다.** 0001~0014는 discovery `df05ccb`까지만 있다. dev는 한 번만 손으로 옮긴다: 옛 api와 worker를 멈춤 → `df05ccb` worktree에서 `alembic upgrade 0014`(관리 계정) → 새 테이블 권한 → dev 스키마를 새 기준과 비교(읽기만, 차이가 없어야 한다) → `alembic stamp --purge 0015` → 배포 후 두 deployment를 1로 되돌림. 절차는 `new-type/note-discovery-dev-deploy.md` §3에 있다. 테이블과 남는 데이터(아래 표)는 그대로다. prod에는 아직 DB가 없어 이 절차가 필요 없다.

| 지우는 테이블 (0012) | 새 테이블 (0013, 0014) | 남는 테이블 |
|---|---|---|
| `visible_topic_rows`, `catalog_edges`, `catalog_snapshots`, `friends`, `popularity`, `attributions`, `interactions`, `population_stats`, `agents` | `notes`, `tags`, `note_tags`, `cards`, `note_cards`, `decisions` | `room_turns`, `departed_users` |

2026-11-12: `room_turns`는 migration 0016으로 지웠다(discovery phase 10). 남는 테이블은 `departed_users`뿐이다. 같은 날 0015와 0016을 기준 하나(`0016`)로 다시 합쳤다(discovery #97). dev는 이미 그 스키마의 `0016`이라 할 일이 없다. prod는 빈 DB에 `alembic upgrade head` 뒤 테이블 일곱과 `tags_tag_id_seq`에 앱 계정 권한을 준다(discovery `docs/operations.md`).

### 1-3. 커넥션 수 — 공유하기 때문에 우리가 먼저 줄인 것

프로세스마다 SQLAlchemy 커넥션 풀을 하나 들고, pod당 프로세스는 1개다. 풀 크기는 `DB_POOL_SIZE`·`DB_MAX_OVERFLOW`로 환경마다 정한다. **숫자는 예전과 같다.**

| | api 프로세스당 | worker 프로세스당 | api pod | worker pod | 정상 최대 | 롤링 배포 중 |
|---|---|---|---|---|---|---|
| dev (공유, 지금) | 2+3=**5** | 8+8=**16** | 1~3 (HPA) | 1 | **31** | ~52 |
| prod | 5+10=15 | 8+8=16 | 2~5 (HPA) | 1 | **91** | ~137 |

`pensieve-pg-tokyo-dev`(`db.t4g.small`)의 RDS 기본 `max_connections`는 약 225이고, iac가 걸어 둔 커넥션 알람 임계는 125다. 여기에 pensieve 자신의 사용량이 더해진다.

**worker의 16은 예산이 아니라 하한 때문이다.** `WORKER_CONCURRENCY`(10)만큼의 핸들러가 각자 트랜잭션 동안 커넥션을 쥐고, 그 옆에서 이벤트가 깨우지 않는 루프 4개(보존 스윕, note sync, 주기적 다시 맞추기, backfill)가 돈다. 하한은 10+4=14이고 16은 그 위다. 예전에는 루프가 6개(인기도, CF 학습 등)라 하한이 16이었는데, note 기반으로 바뀌며 줄었다. 하한은 테스트가 워커 코드에서 루프 수를 직접 세어 계산하므로, 루프가 늘면 따라 올라간다.

하한을 밑돌아도 풀 오류는 나지 않는다. 남는 핸들러가 기다리다가 재시도 끝에 이벤트를 버린다(deferq에 DLQ가 없다). 커넥션이 모자란 풀은 "응답 없는 데이터베이스"처럼 보이므로, 하한을 코드에서 지킨다.

### 1-4. 알고 있는 것

- **TLS:** iac의 rds 모듈 파라미터 그룹이 `rds.force_ssl = 0`이다. 그래서 dev는 TLS 설정 없이 접속하고 있다.
- **`statement_timeout`은 역할 기본값으로 짧게 걸지 말아 주시길 부탁드린다.** 요청 경로 쿼리는 짧지만, backfill과 주기적 다시 맞추기는 note 전체를 훑는다. 요청 경로의 상한은 앱이 건다.
- **terraform에는 이 DB, 계정, 확장이 나타나지 않는다.** rds 모듈은 `db_name` 하나만 만들므로 모두 손으로 만든 것이 된다. 기록해 둔다.

### 1-5. prod에서 다시 물어야 하는 것

iac에 이미 `pensieve-pg-tokyo-prod`(PostgreSQL 18, multi-AZ, 백업 7일)가 정의돼 있는 것을 봤다. dev처럼 그 인스턴스에 얹을지, 전용으로 갈지는 prod 배포 시점에 정한다. 그때 함께 볼 것:

- **`vector` 확장(§1-1)을 prod RDS에서 켤 수 있는지.** 설계 열린 항목 1.
- **복원 단위.** PITR이 인스턴스 단위라, 공유하면 옆 서비스 사고로 우리 데이터가 같은 시점으로 되감긴다. 우리 데이터는 note-api에서 다시 읽어 만들 수 있어서(backfill) 손실은 시간 문제지만, prod에서도 받아들일지는 따로 정한다.
- **커넥션 예산.** 위 표의 prod 91(롤링 137)은 전용 인스턴스 가정이다. 공유라면 dev처럼 우리가 먼저 줄인다.
- **인스턴스 이름.** 새로 만든다면 서비스 이름을 넣지 않기를 권한다(`bourbon-pg-tokyo-prod`처럼). 두 번째 서비스가 들어오면 이름이 거짓이 되고, RDS identifier 변경은 사실상 재생성이다.

**왜 PostgreSQL인가.** 요청마다 하는 일이 cosine 검색(pgvector)과 사람별 집계(검색 가능한 모든 note로 사람 점수를 내고 z-score를 계산)다. 둘 다 한 DB에서 SQL로 하는 것이 맞고, OpenSearch를 더하지 않아도 된다. 규모는 note 1만 개(768차원)에서 요청당 수 ms~수십 ms로 본다(설계 §6-2 "비용"). 실제 지연은 dev에서 잰다.

## 2. DynamoDB — 더 이상 쓰지 않는다

예전에는 결정 로그·이벤트 로그·CF 후보 등을 테이블 하나에 두었다. note 기반으로 다시 만들면서 결정 로그는 PostgreSQL `decisions` 테이블로 옮겼고(30일 보존), 나머지는 없어졌다. 코드에서 DynamoDB를 쓰는 곳은 없다(discovery phase 1, 2026-11-07).

**요청:** 우리 배포 뒤에 dev 테이블 `bourbon-agent-discovery-tokyo-dev`를 삭제해 주세요. 옛 로그는 내보내지 않는다(2026-11-07 오너). 새 코드가 테이블을 읽지 않으므로, 배포가 끝난 뒤라면 언제든 괜찮다.

- **IAM은 그대로 두셔도 된다.** dev의 `bourbon-app` 정책은 `bourbon-*-tokyo-dev` 와일드카드 한 줄이라 우리 테이블만 뺄 수 없고, 다른 서비스가 같은 줄을 쓴다. 테이블이 지워지면 그 줄이 우리에게 허용하는 것은 없다.
- **prod 테이블은 만들지 않는다.** 예전에 부탁했던 "prod IAM에 우리 테이블 ARN 추가"도 필요 없다.

## 3. Redis — deferq 전용 DB 번호

**받은 것**: 공유 ElastiCache `pensieve-redis-tokyo-dev`의 DB 13(ConfigMap `DEFERQ_REDIS_URL`). 우리 데이터는 Redis에 두지 않는다. 새 워커에는 예약 작업이 없어서, 들어가는 것은 deferq 워커 등록 key뿐이다. prod 번호는 prod 배포 때 받는다.

topic 시절 예약 작업(`agent_discovery.refresh_user_topics`)이 남긴 key는 배포 뒤 우리가 지운다. deferq가 작업 이름을 hash tag로 붙여 두는 `deferq:time:{agent_discovery.refresh_user_topics}`, `deferq:args:{…}`, `deferq:ceil:{…}`, `deferq:run:*:{…}`다.

## 4. RabbitMQ

**계정**: dev는 받았다(Secret `DEFERQ_AMQP_URL`). 우리는 발행하는 이벤트가 없고 소비만 한다.

**큐 깊이 상한과 알람 (2026-09-16 요청, 큐 이름만 바뀜).** 우리 워커는 데이터베이스에 닿지 못하면 뜨지 않는다. deferq는 실패한 리스너의 메시지를 ack하고, 재전달도 DLQ도 하지 않는다. 그래서 뜬 채로 소비하면 그 이벤트는 영구 손실이고, 안 뜨면 큐에 남는다. 그런데 우리 큐에는 `x-max-length`도 `x-message-ttl`도 없고, 브로커는 `SINGLE_INSTANCE`이며 여러 서비스가 같은 vhost를 쓰고, 큐 깊이 알람이 없다. 그래서 둘을 부탁드린다.

- **(가)** 우리 큐에 `x-max-length`(또는 `x-max-length-bytes`)와 overflow 동작을 정책으로 걸어 주시고, 며칠치 백로그를 감당할 수 있는지 알려 주세요. **패턴을 `deferq.*`로 잡지는 말아 주세요.** deferq는 모든 서비스의 컨슈머 큐를 그 접두어로 짓기 때문에 다른 팀의 큐까지 건드린다. 지금 우리 큐는 다섯이다:
  - `deferq.erase_on_user_deactivated`
  - `deferq.mark_pending_on_note_created`
  - `deferq.mark_pending_on_note_updated`
  - `deferq.mark_pending_on_note_visibility_changed`
  - `deferq.mark_pending_on_note_deleted`
- **(다) dev의 `deferq.count_turn_on_message_created`를 지워 주세요(2026-11-12).** phase 10에서 리스너를 지웠는데, 우리가 콘솔에 들어가지 못해 queue가 남아 있다. purge가 아니라 delete다(purge한 queue는 binding이 남아 모든 `message_created`를 계속 모은다). 이 queue에 걸어 두신 정책이 있으면 함께 풀어 주세요.
- **(나)** 큐 깊이(`MessageCount` 등) 알람. 임계는 브로커 용량 쪽에서 정해 주시는 편이 정확하다. note 이벤트의 실제 발생률은 dev 배포 뒤에 알려 드린다.

**옛 큐는 우리가 지운다.** topic 시절 큐 넷은 리스너가 없어졌는데 바인딩이 남아 이벤트가 계속 쌓인다. 배포 뒤 워커가 새 큐를 소비하는 것을 확인하고 우리가 지운다. 이 큐들에 정책을 걸어 두셨다면 함께 풀어 주세요.
- `deferq.arm_refresh_on_topics_updated`
- `deferq.arm_refresh_on_topic_visibility_changed`
- `deferq.mirror_friends_on_friendship_changed`
- `deferq.create_agent_on_user_registered`

**순서 주의:** 큐와 바인딩은 컨슈머가 선언한다. 새 리스너(`mark_pending_on_note_*`)가 한 번 뜨기 전에 발행된 note 이벤트는 브로커가 버린다. 그래서 note-api가 `note_visibility_changed`, `note_deleted`를 발행하기 시작하기 전에 우리 워커가 먼저 떠 있어야 한다. 놓친 것은 배포 뒤 `cli backfill`과 주기적 다시 맞추기가 메운다.

## 5. 필요 없는 것

- 새 네임스페이스·Deployment·Service: 이미 있다(api + worker, 같은 이미지).
- OpenSearch, MySQL, DynamoDB, Redis 데이터 저장.
- IRSA 역할: AWS를 부르는 코드가 없다. Deployment에도 `serviceAccountName`이 없다.

## 6. 확인 질문

1. §1-1 — 우리 관리 계정으로 `CREATE EXTENSION vector`가 거부되면 `rds_superuser`로 실행해 주실 수 있는지.
2. §2 — dev DynamoDB 테이블 삭제(우리 배포 뒤).
3. §4 — 다섯 큐에 걸 수 있는 깊이 상한과 기대할 수 있는 백로그 기간, 알람 임계.
4. §4(다) — dev의 `deferq.count_turn_on_message_created`를 delete해 주실 수 있는지.
5. prod — §1-5는 prod 배포 시점에 다시 묻는다.
