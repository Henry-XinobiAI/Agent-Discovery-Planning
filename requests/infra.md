# 인프라 요청서 — bourbon-agent-discovery-api

> 보내는 시점: 1차 배포 2주 전. 그 전까지는 로컬 Docker(PostgreSQL 17, dynamodb-local, valkey, rabbitmq)로 개발·검증한다(R43). 아래 네 항목 중 **DynamoDB는 방침대로 dev에서 우리가 직접 만들고**, prod terraform 코드화 시점에 포함해 주시면 된다.

## 0. 서비스 개요 (한 단락)

bourbon-agent-discovery-api는 유저에게 "대화해 볼 타인의 personal agent"를 추천하는 서비스다. 세 종류의 요청(자기 agent에게 free text로 묻기, 탐색 탭의 내 topic별 목록, 탐색 메인의 개인화 목록)을 받고, 입력은 topic-api의 유저 topic(공개 범위 public·friends만 저장), bourbon-api의 친구 관계·agent 공개 여부·대화 시작 이벤트다. api Deployment와 deferq 워커 Deployment가 이미 dev에 있다(같은 이미지, 명령만 다름). 새로 필요한 것은 저장소다.

## 1. PostgreSQL — 플랫폼에 처음 들어오는 저장소 (2026-09-10 사전 확답, R45)

2026-09-10 인프라 팀과 이야기해 이 서비스가 PostgreSQL을 쓰는 것으로 확답받았고, 요청 시 추가해 주기로 했다. 아래 근거는 왜 DynamoDB만으로 하지 않는지의 **기록**이다.

**요청**: RDS PostgreSQL 17, dev·prod 각 1 인스턴스(가장 작은 단계로 시작, 예 `db.t4g.small`), DB `agent_discovery`, 앱 계정 1개(DDL 포함 — 스키마 마이그레이션은 앱이 alembic으로 배포 시 적용), 서비스 네임스페이스에서만 접근. 접속 문자열은 Secret `DATABASE_URL`로.

**왜 DynamoDB만으로 하지 않는가.** 방침(서비스별 주 DB는 DynamoDB)을 알고 있고, 단건 키 읽기·쓰기인 데이터는 전부 DynamoDB에 둔다(§2). PostgreSQL에 두는 것은 **요청마다 조인·집계가 필요한 집합**만이다(결정 R18). 구체적으로:

| 요청 시 쿼리 | 모양 | DynamoDB로 하면 |
|---|---|---|
| 타입 ①: topic 1~3개를 가진 소유자를 **몇 개를 가졌나(커버리지) 순**으로 | `WHERE topic_id IN (…) AND (tier='public' OR (tier='friends' AND owner IN 친구집합)) GROUP BY owner ORDER BY count DESC, score DESC` | topic마다 Query 1회 + 친구 판정 + 클라이언트 병합·정렬. 친구 판정은 후보마다 집합 조회 |
| 타입 ③ content 유사도: 요청자 topic과 겹치는 소유자, 겹침을 **IDF(그 topic 보유자 수의 로그)와 카탈로그 계층 거리**로 가중 | topic 보유자 수 집계 + parent edge 테이블 조인 + 소유자별 합 | 보유자 수는 별도 카운터를 매 쓰기마다 유지, 계층 거리는 앱에서 계산 뒤 소유자별 합을 클라이언트 병합 |
| 인기도: 최근 30일 대화 시작을 반감기 7일로 감쇠해 소유자별 합 | 시간 창 집계 | 소유자별 감쇠 카운터를 이벤트마다 갱신(가능하지만 반감기 변경 시 재계산 불가) |
| CF 학습 입력: (요청자, 소유자, turn 수, 재방문 수) 전량 | 하루 1회 전체 스캔 | Scan(가능) |
| 갱신 스윕: `last_active_at > cf_candidates_computed_at` 인 유저 | 두 컬럼 비교 필터 | Scan + 필터, 또는 GSI 하나 추가 |
| 실측 보정: 유저별 대화 횟수 분포, agent별 순위-빈도 | GROUP BY + 퍼센타일 | 전량 Scan 뒤 앱에서 집계 |

topic-api가 같은 문제를 DynamoDB로 풀며 겪은 것이 참고가 된다: 단일 topic의 보유자 순위 하나를 위해 GSI에 shard를 넣고 top-k 병합 스트림을 두어야 했다(topic-api `docs/dynamodb-key-design.md`, 2026-09-10 기준). 우리 타입 ①은 그것을 **topic 3개의 교집합 × 친구 술어**로 확장한 것이라, 접근 패턴마다 GSI와 병합 코드를 늘리는 대신 SQL 한 문장이 맞다.

**규모와 비용.** 10만 유저 기준 공개 topic row 36만 건, 27 MB — 가장 작은 인스턴스의 메모리에 다 들어간다. 실측(2026-09-08, `library_verification.md` §2): 커버리지 쿼리 p50 0.8 ms / p95 2.3 ms, 위반 0건. 같은 쿼리를 OpenSearch로 하면 3배 느렸다. DynamoDB로 같은 정확도를 내려면 위 표의 접근 패턴마다 GSI(각각 쓰기 비용 2배)와 클라이언트 병합이 필요하고, 그 개발·운영 비용이 작은 RDS 인스턴스 하나보다 크다고 판단했다.

**MySQL 대신 PostgreSQL인 이유.** 플랫폼에 MySQL(bourbon-memory)이 이미 있고 위 쿼리는 MySQL로도 된다. PostgreSQL을 고른 이유는 (a) 친구 집합을 배열 파라미터로 넘기는 술어(`owner = ANY($1)`), (b) 나중에 topic 벡터 kNN이 필요해지면 pgvector 확장으로 같은 인스턴스에서 해결(OpenSearch 추가 없이).

## 2. DynamoDB — 테이블 1개, 방침대로

**요청**: prod terraform 시점에 아래 테이블을 포함. dev는 우리가 직접 만든다(권한은 `bourbon-*-tokyo-dev` 와일드카드로 이미 열려 있다).

| 항목 | 값 |
|---|---|
| 테이블 | `bourbon-agent-discovery-tokyo-{dev,prod}` |
| 키 | `PK` (S) HASH, `SK` (S) RANGE |
| 과금 | `PAY_PER_REQUEST` |
| TTL | 속성 `expires_at`(N, epoch 초). 결정 로그·이벤트 로그만 값이 있고, `cf_candidates`는 없다(만료되면 돌아온 유저가 콜드스타트로 밀린다, R18) |
| GSI 1 | `served-day-index`: HASH `served_day_key` (S), RANGE `served_at` (S), `KEYS_ONLY`. 결정 로그를 "타입·날짜"로 읽는 오프라인 평가용. 파티션 키에 shard가 들어 있다(아래) |

엔티티는 테이블을 늘리지 않고 key space로 나눈다(계약 `agent_discovery_contract.md` §6-1이 정본):

| 항목 | PK | SK | 비고 |
|---|---|---|---|
| CF 후보 top-K | `USER#{user_id}` | `CF_CANDIDATES` | 단건 GetItem. K=200이면 12~13 KB(uuid 소유자 id 기준). TTL 없음 |
| 결정 로그 | `REC#{recommendation_id}` | `LOG` | 단건 GetItem(어트리뷰션 조인, 디버깅). 페이지는 같은 항목의 `pages[]`에 append. TTL은 설정 `decision_log.ttl_days`(365일). GSI 속성 `served_day_key = {type}#{YYYY-MM-DD}#{shard}`, `shard = hash(recommendation_id) % N` |
| 이벤트 로그 | `EVT#{YYYY-MM-DD}#{shard}` | `{occurred_at}#{event_id}` | append-only, 하루 단위 Query로 리플레이. TTL은 설정 `event_log.ttl_days`(180일). `shard = hash(event_id) % N` |
| 게이트 상태 | `CONFIG` | `CF_GATE` | 런타임에 움직이는 유일한 설정값(`w_cf`)과 마지막 평가 결과. 단건 |

topic-api에 주신 두 피드백을 처음부터 반영했다: 지배적 읽기(날짜별 전량)가 Scan이 아니라 Query가 되게 날짜를 파티션 키에 넣었고, 하루치 쓰기가 한 파티션에 몰리지 않게 **shard를 키 포맷에 지금 박아 둔다**(N은 설정 `dynamodb.log_shards`, 8로 시작. 읽기는 N개 Query 병합). 두 번째 테이블이 필요해지는 경우는 지금 보이지 않는다 — 생기면 성능·비용 근거를 이 문서에 추가해 다시 요청한다.

## 3. Redis — deferq 전용 DB 번호

**요청**: 공유 ElastiCache(`pensieve-redis-tokyo-{dev,prod}`)에서 우리 워커의 deferq 스케줄 키 공간으로 쓸 DB 번호 1개(dev·prod 각각). bourbon-agent가 8(deferq)·9(상태)를 쓰고 있어(`bourbon-agent/k8s/overlays/dev/configmap-patch.yaml`, 2026-09-10 기준) 그 다음 번호를 주시면 된다. 우리 데이터는 Redis에 두지 않는다(R18) — deferq의 debounce 예약만 들어간다. 값은 ConfigMap `DEFERQ_REDIS_URL`.

## 4. RabbitMQ — 워커 자격

**요청**: 우리 워커가 이벤트 exchange를 구독할 AMQP 자격(bourbon-agent와 같은 형태, Secret `DEFERQ_AMQP_URL`). 우리는 지금 발행하는 이벤트가 없다(계약 §9-2) — 소비자 자격만 필요하다. dev에 이미 있다면 그대로 쓴다 — 워커 Deployment가 지금도 그 Secret으로 시작한다.

## 5. 필요 없는 것

- 새 네임스페이스·Deployment·Service: 이미 있다(api + worker, 같은 이미지).
- OpenSearch, MySQL, Redis 데이터 저장.
- IAM 개별 등록: 와일드카드 정책으로 충분.

## 6. 확인 질문

1. §1 — 인스턴스 크기·엔진 버전(17)·접속 방식(Secret `DATABASE_URL`)에 이견이 있는지.
2. §3 — DB 번호.
3. prod terraform 코드화 시점을 알려 주시면 그 전에 dev 테이블·GSI 정의를 최종 확인해 드린다.
