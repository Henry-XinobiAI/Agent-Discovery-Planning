# 구현 계획 — bourbon-agent-discovery-api

> `agent_discovery_redesign.md` §9의 5·6번을 단계로 자른 것(2026-09-10). 결정은 `decisions.md`, 지켜야 할 것은 `agent_discovery_contract.md`, 값은 `agent_discovery_settings.md`다. 이 문서는 **순서와 완료 조건**만 정한다. 코드 repo에서 단계를 시작할 때 `tasks/todo.md`에 체크 항목으로 옮기고, 끝난 단계는 여기에 날짜를 적는다.

## 0. 전제 (R43·R44)

- **로컬 Docker에서 전부 돈다.** compose에 PostgreSQL 17, dynamodb-local, valkey, rabbitmq, topic-api 목 서버. 인프라 요청(`requests/infra.md`)은 1차 배포 2주 전에 보낸다.
- **DynamoDB 테이블은 하나**(`bourbon-agent-discovery-tokyo-{env}`), 엔티티는 PK/SK prefix(계약 §6-1). PostgreSQL은 조인·집계 집합만(R18) — 플랫폼에 처음 들어오는 저장소지만 인프라 확답을 받았다(R45). 요청서 §1의 근거는 기록이다.
- **외부 이벤트는 아직 오지 않는다.** 우리 CLI가 로컬 브로커에 발행해 발행→소비 왕복을 확인하고, 품질은 합성 모집단으로 본다. 요청서 다섯 개는 `requests/`에 있다.
- **산출물에 반드시 포함**: 합성 데이터를 로컬 저장소에 넣는 시드 스크립트, 세 타입을 호출하고 이벤트를 발행하는 테스트 CLI.

## 1. 단계

각 단계는 완료 조건을 모두 만족하면 끝난다. 테스트는 단계마다 먼저 쓴다(실패하는 테스트 → 구현). `pre-commit run --all-files`는 매 커밋.

### 1-1. 갭 정리 — 지금 코드에서 무엇을 남기고 무엇을 바꾸나

코드 repo는 재설계 이전 상태다(코드 읽은 기준: bourbon-agent-discovery-api main `b096aa2`, 2026-09-10 — `agent_discovery/`·`api/`·`worker/`·`cli/` 7,151줄, 765 테스트). 먼저 인벤토리를 만들고 그 뒤 단계를 시작한다.

| 남긴다 | 이유 |
|---|---|
| `agent_discovery/stages/` (expansion → grounding → retrieval → merge → ordering → assembly), `providers/topic_api/` (client·wire·adapter, 계약 위반 가드 4개), `providers/llm/` | 타입 ①의 free text → topic 확정 단계 그대로(계약 §4-1) |
| `worker/` 골격 (app, health, redis, scheduling, budget, ingest 재시도) | deferq 호스팅·debounce·heartbeat·재시도가 계약대로다. 리스너와 task만 바뀐다 |
| `api/main.py`, `api/middleware/`, `api/structs/errors.py`, 배포 매니페스트, `tests/test_deploy_env_wiring.py` | 서비스 골격 |
| `cli/` 골격 | `publish`·`recommend` 명령을 확장한다 |

| 바꾼다 / 지운다 | 무엇으로 |
|---|---|
| `worker/events.py`의 `bourbon.user_topic_updated`(존재하지 않는 이름, `touched` 필터) | `bourbon.topics_updated` 미러 + 새 이벤트 셋 선언(이벤트 정의서 §2). `touched` 필터 삭제 — 항상 재조회 |
| `api/routers/events/user-topics-changed` route (저장소 없이 읽기만 하고 로그만 남김) | 재조회 task가 저장소에 쓴다. 워커가 자기 API를 HTTP로 찌르는 구조는 유지할지 1-4에서 결정(아래 "열린 구현 판단" 1) |
| `agent_discovery/composition.py`의 요청 tier `public`만 | 타인 row `public`·`friends`, 요청자 프로필 `public`·`friends`·`private`(R22) |
| `api/routers/recommend/` `POST /recommend` 단일 route | `/recommend/explicit`(내부) + `/discover/by-topic`·`/discover/for-you`(클라이언트 + 내부 미러). 기존 route는 bourbon-agent 전환까지 유지 |
| `docs/recsys-intent.md`, `docs/topic-api-events.md` | 아카이브된 이전 레지스터에 기댄 문서 — 삭제하고 기획 저장소 링크 한 줄로. `docs/deferq-worker-readiness.md`는 deferq 요청서라 남긴다 |
| `RecommendSettings` 등 흩어진 설정 | 설정 레지스터와 같은 이름·docstring의 Settings 클래스 하나(R39) |

**완료 조건**: 위 표가 `tasks/todo.md`에 옮겨져 있고, 삭제 대상의 테스트 수를 알며, 남기는 모듈의 테스트가 그대로 통과.

### 1-2. 로컬 스택과 카탈로그

- compose: `postgres:17-alpine`, `amazon/dynamodb-local:3.1.0`, `valkey/valkey:9.1-alpine`(지금 `redis:7-alpine`을 바꾼다), `rabbitmq:4.2-alpine` — 세 이미지 태그는 bourbon-agent·topic-api의 compose와 같다(2026-09-10 기준). 그리고 **topic-api 목 서버**(`/users/{id}/topics`, `/search/topics`를 적재된 합성 데이터로 답한다. 응답 지연 시간 5 ms 고정, 스펙 §7).
- 스키마: SQLAlchemy 2 async + alembic. DynamoDB는 aioboto3, 테이블 생성 스크립트 하나(로컬·dev는 우리가 만든다. prod는 인프라 요청서 §2).
- 카탈로그(R26): `scripts/sync_catalog.py`가 topic-api repo의 `data/catalog_dist/catalog.json`을 우리 `data/catalog_dist/`로 복사하고 `built_at`·원본 커밋을 옆 파일에 남긴다. 복사본은 **커밋한다** — 빌드가 다른 repo를 읽지 않게. 바뀌면 스크립트 재실행 → 커밋 → 재배포.
- `.env.example`·README 표·k8s configmap에 새 키(`DATABASE_URL`, `DYNAMODB_TABLE_NAME`, `DYNAMODB_ENDPOINT_URL`(로컬만)). `test_deploy_env_wiring.py`가 셋의 일치를 강제한다.

**완료 조건**: `docker compose up -d` 뒤 `alembic upgrade head`와 테이블 생성이 돌고, 목 서버가 빈 응답을 돌려주며, 카탈로그 edge 테이블에 2,959 edge가 적재된다.

### 1-3. 설정 클래스와 계약 스키마

- `agent_discovery/settings.py`: 설정 레지스터 §1~§10의 그룹이 중첩 필드. 필드 docstring = 표의 "뜻"과 "올리면 / 내리면". `settings_hash()`가 결정 로그 `implementation: "v1@<hash>"`를 만든다. 테스트: 레지스터 표의 이름 목록과 클래스 필드 목록이 같다(표를 파싱해 비교).
- `api/structs/`: 세 타입의 요청·응답 pydantic 모델, envelope, `degraded`, 오류(422/503), `lang` 검증(ko·en·ja). `label`·`owner_note`는 문자열, 대체 순서 requested → en → 있는 것 → null.
- 도메인 인터페이스(계약 §4): `TopicQuery`, `UserQuery`(`requester_traits` 예약), `SourceHit`, `CandidateSource`, `VisibilityFilter`, `Features`/`Ranker`, `Assembler`. 구현 없이 Protocol과 dataclass만.

**완료 조건**: 계약 §2·§3의 예시 JSON이 모델로 파싱·직렬화되고, 레지스터-클래스 일치 테스트가 통과.

### 1-4. 저장 모델과 적재 경로

PostgreSQL: `visible_topic_rows`(+ `descriptions` JSON, hydration용), `agents`, `friends`, `interactions`, `room_turns`(R49), `attributions`(R47), `catalog_edges`, `population_stats`. 인기도는 `interactions`에서 요청 시 계산(30일 창이라 작다) — 별도 테이블은 p95가 나빠지면.
DynamoDB(계약 §6-1): `USER#…/CF_CANDIDATES`, `REC#…/LOG`, `EVT#…`, `CONFIG/CF_GATE`.

리스너(전부 `worker/`에 한 흐름씩): `topics_updated`·visibility 변경 신호(임시 이름 `user_topic_settings_updated`, R48) → 같은 debounce → 재조회 task(row 통째 교체, `agents` 없으면 생성, `topic_revision` 복제 지연 시 재시도); `personal_agent_visibility_changed`; 그 방의 첫 `message_created`(→ `interactions`, 소유자는 추천 시점에 계산해 둔 room id로, `attributions` 보고가 예측보다 우선, `agents.last_active_at` — R51·R53); `message_created`(`room_type`·`sender_type` 필터 → `room_turns[room_id]` +1, `room_created`와 순서 무관 — R49); `friendship_changed`; `user_registered`(agent id 결정론적 계산, `email` 읽지 않음); `user_deactivated`. 모든 리스너가 `event_log`에 append. 어트리뷰션 보고 route `POST /attributions`(계약 §2-5, R47)는 이 단계에서 같이 만든다 — `room_created` 리스너가 조인하는 상대다.

CLI: `python -m cli publish <event> …` 이벤트마다 하나.

**열린 구현 판단 1 — 워커가 저장소에 직접 쓰나, API를 찌르나.** 지금 코드는 워커 → HTTP → API route다(pod 분리 대비). 저장소가 생기면 워커가 직접 쓰는 쪽이 단순하고 재시도가 한 곳이다. 권고: **워커가 직접 쓴다.** 권고를 택하면 `ingest.py`와 `/events/*` route를 지우고 API는 읽기만 한다.

**완료 조건**: CLI로 `topics_updated`를 세 번 발행하면 재조회 1회·row 교체 1회, visibility 변경 신호로 private 전환 뒤 row가 사라지고, 예측 room 인덱스와 `POST /attributions` 뒤 첫 `message_created` → `interactions` 1행(`entry`·`recommendation_id`·`attributed_by` 채워짐) + `last_active_at` 갱신, 예측하지 않은 방의 `message_created`는 turn만 세고 기록되지 않으며(R52), 각 이벤트가 `event_log`에 1건. 불변식 1(저장소에 private·hidden 없음)을 테스트가 강제.

### 1-5. 타입 ①② — 인덱스 소스와 응답

- `topic_index` 소스: 계약 §6의 쿼리(조건 안에 친구 배열, GROUP BY owner, 커버리지 정렬). 실측 스파이크의 SQL을 옮긴다.
- 랭커 가중합(레지스터 §2 explicit), Assembler(hydration: `visible_topic_rows.descriptions`와 카탈로그 라벨에서 `lang` 하나, 응답 직전 재확인, `hydration_partial`).
- `/recommend/explicit`: 기존 grounding 단계 → `TopicQuery` → 소스 → 응답. `topic_text`·`context`는 로그에 원문 금지(테스트로 강제 — 로그 캡처에 문자열이 없어야 한다).
- `/discover/by-topic`: 요청자 프로필 재조회(R27, `public`·`friends`·`private`), preference 순 상위 `sections`개, 섹션당 `per_section`, 섹션별 커서 `/discover/by-topic/{topic_id}`.
- 결정 로그 쓰기(`REC#…`, `pages[]` append, `served_day_key` shard).
- **예측 room 인덱스 쓰기**(R51): 답한 후보마다 `ROOM#{uuid5(DM_NAMESPACE, "dm:user:{requester}:agent:{agent_id}")}`에 `(requester, owner, recommendation_id, entry, served_at)`. 읽는 쪽은 1-4d에 이미 있고, 이것이 없으면 어떤 대화도 `interactions`에 기록되지 않는다.

**완료 조건**: walkthrough §3·§4의 예제 데이터를 적재하면 문서의 결과 순서가 그대로 나온다(문서의 예시값을 테스트 픽스처로). 위반 0건 테스트(friends row가 비친구에게 나가지 않음). 답한 뒤 그 후보의 room id로 `message_created`를 발행하면 `interactions` 1행이 `attributed_by = predicted`로 생긴다 — 1-4d의 읽는 쪽과 이어지는 유일한 지점이다.

### 1-6. 합성 생성기, 시드 스크립트, 테스트 CLI

- `synthetic/`(코드 repo): 스펙 §2~§5 그대로. 출력 파일 형식은 스펙 §5. 시드 고정.
- `scripts/seed_local.py`: 출력 파일을 로컬 PostgreSQL·DynamoDB·목 서버 데이터로 적재(10만 유저 기본, `--users`로 축소). 이벤트 스트림은 CLI 발행 명령을 재사용해 브로커에 넣는 모드와, 저장소에 직접 넣는 빠른 모드 둘.
- `python -m cli recommend explicit|by-topic|for-you …`, `cli publish …`, `cli seed …`, `cli validate …`(1-9).

**완료 조건**: 10만 유저 적재가 노트북에서 10분 안에 끝나고, 스펙 §6 생성기 자체 검증이 통과하며, 세 타입 CLI가 응답을 낸다.

### 1-7. 타입 ③ — 인기도·content·콜드스타트

- `popularity` 소스(R29: 30일, 반감기 7일, confidence 가중, 신규 항목 prior, 최대값으로 정규화).
- `content_similarity` 소스(R25: IDF × `0.6^hop`, 양방향 최단 hop ≤ 3, 경로당 가장 구체적인 일치 하나, drawer 통과, `catalog_edges`로). 모르는 topic id → 정확 일치 + 지표.
- `UserQuery`, 이미 대화한 상대 제외와 후보 소진 뒤 재노출(R28, `talked_before`는 로그만), 구간 섞기(R20, seed = `recommendation_id`), `cf_candidates` 없으면 콜드스타트 경로.
- `/discover/for-you` + 커서.

**완료 조건**: §5-5 표의 가중(pop .4 / content .4 / cf .2)과 cf 열 값을 입력으로 주면 walkthrough §5 예제에서 그 표의 점수가 재현되고, 섞기가 seed로 재현되며, ablation "인기도만"·"content만"이 스펙 §4의 정답으로 recall@10을 낸다.

### 1-8. CF — `implicit` ALS, 스윕, 게이트

- `fit_cf_model` 주기 작업(레지스터 §3·§6): `interactions` → confidence 행렬 → ALS → 모델 버전. 워커 메모리에 factors 유지.
- `refresh_cf_candidates` 스윕: 조건 SQL(`coalesce`, `interactions > 0`), 배치 `recommend(... recalculate_user=True, items=…)`, 공개 후보 공통 matmul + 친구 후보 유저별(재설계 §7), DynamoDB 쓰기, `cf_candidates_computed_at`.
- 게이트(R35, 레지스터 §4): 실제 로그 leave-one-out HR@10·군집 다양성, `w_cf` 조정, `CONFIG/CF_GATE`에 기록.
- 서빙: `cf_engine` 소스가 `cf_candidates`를 읽고 stale이면 그대로 서빙 + 스윕 표시(`cf_candidates_stale`).

**완료 조건**: 합성 10만 유저에서 학습 1~2초(16 factors, `library_verification.md` §3-1 실측과 같은 자릿수), 스윕 5,000명/사이클, 게이트가 λ=3에서는 `w_cf`를 올리지 않고 λ=10에서는 올린다(같은 §3-1의 실측: λ=10에서 HR 동률·군집 신호 2배 — `gate.min_hr_ratio` 1.0·`gate.min_cluster_gain` 1.5를 만족).

### 1-9. 검증 — 소스별 ablation, 부하, 설정 초기값

- `cli validate`: 스펙 §4 정답으로 인기도만·content만·CF만·합친 랭커의 recall@10·NDCG@10·군집 비율·위반 수 표, λ∈{3,10,30} 세 값, 같은 `params.json` 스냅샷.
- 부하: 타입 ①② p50/p95(목표: 실측 스파이크 자릿수), 타입 ③ 콜드스타트·`cf_candidates` 있는 경우.
- 결과 문서 `validation_results.md`(기획 저장소), 설정 레지스터의 "분석" 값을 측정값으로 갱신.

**완료 조건**: 표가 있고, 레지스터의 가중치가 측정 근거를 가리킨다.

### 1-10. 배포 준비

- 요청서 발송(`requests/README.md`의 순서). 인프라 답 → configmap/secret 갱신, dev 테이블·GSI 생성, alembic 적용.
- 실측 보정 작업(R37, 스펙 §8)은 배포 뒤 첫 주기부터.
- go-live 전제 확인: bourbon-api `discoverable`과 **친구 게이트 해제**(그 전에는 비친구 추천이 채택되지 않는다), bourbon-api 경로 레지스트리에 공개 prefix `/api/svc/agent-discovery/` 등록(요청서 §2-2 — 없으면 공개 route가 밖에서 닿지 않는다), 클라이언트 `POST /attributions` 호출, topic-api api AMQP + visibility 변경 신호, prod topic-api 워커.

## 2. 순서의 이유

- 생성기(1-6)가 타입 ③(1-7)보다 앞인 것은 R34가 검증 방법을 생성기로 정했기 때문이다. 타입 ①②(1-5)는 walkthrough 예제만으로 검증되므로 생성기 전에 끝낸다.
- 저장 모델(1-4)이 route(1-5)보다 앞인 것은 불변식 1·4가 저장소에서 검증되기 때문이다.
- CF(1-8)가 마지막 구현인 것은 가중이 0에서 시작하고(R35) 그 전 단계가 전부 있어야 게이트가 잴 대상이 있기 때문이다.

## 3. 열린 구현 판단 (오너 결정이 아닌 것)

1. 워커가 저장소에 직접 쓰나, API를 찌르나 — 1-4에서 "직접" 권고.
2. `popularity`를 요청 시 집계하나 테이블로 두나 — 요청 시로 시작, p95가 나빠지면 테이블.
3. 목 서버를 우리 repo에 두나, topic-api repo의 dynamodb-local compose를 그대로 띄우나 — 목 서버(우리 합성 데이터를 답해야 하므로).
4. 기존 `POST /recommend`를 언제 닫나 — bourbon-agent 요청서 §4의 답에 따른다.

## 4. 위험

- **`recommendation_id` 전달이 늦으면** 어트리뷰션 없는 기간이 생긴다. 소급 불가라 요청서 묶음을 보낼 때 bourbon-api·클라이언트를 가장 먼저 보낸다(`requests/README.md`).
- **topic-api prod 워커가 0 replicas인 채로 있으면** `topics_updated`가 없다. dev에서 테스트하고 prod는 그 조건이 해소된 뒤.
