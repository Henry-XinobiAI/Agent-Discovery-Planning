# 구현 진행 현황 — PR 단위 체크리스트

> `implementation_plan.md` §1의 단계를 실제 PR 단위로 쪼개 진행 상황을 적는 문서다(2026-09-10 시작). 계획·근거는 `implementation_plan.md`, 결정은 `decisions.md`가 갖고, 여기는 **무엇이 끝났고 다음이 무엇인지**만 갖는다. PR이 머지되면 체크하고 PR 번호를 적는다. 코드 repo는 `bourbon-agent-discovery-api`(`main` + PR, develop 없음).

**작업 규칙**(오너, 2026-09-10): 코드는 파이썬스럽고 단순하고 읽기 쉽게. 커밋 단위마다 리뷰어 패스를 통과한 것만 커밋한다. PR 전에 각 구현을 상세히 설명해 오너가 전체를 리뷰하고, 그 뒤 push / PR.

**모델 표시** — 작은 모델로 진행해도 되는 PR을 미리 표시한다. 기준은 "계약·레지스터·이벤트 정의서에 답이 그대로 적혀 있어 옮기기만 하면 되는가". 어느 쪽이든 **커밋 전 리뷰어는 큰 모델**로 둔다.

| 표시 | 뜻 |
|---|---|
| 🟢 | 작은 모델로 진행 가능 |
| 🟡 | 조건부 — 안에서 기계적인 부분만 작은 모델, 나머지는 큰 모델 |
| 🔴 | 큰 모델 |

## 끝난 것

- [x] **PR #18** `recsys/1-1-gap-inventory` — 1-1 갭 인벤토리(문서 둘 삭제, README 포인터), 1-2 로컬 스택(`StorageSettings`, compose 스토어, `agent_discovery/storage/` 스키마·카탈로그 저장소·DynamoDB 정의, alembic, 스크립트 넷, topic-api 목 서버, `init` 서비스, 카탈로그 복사본 커밋). 791 tests, 라이브 28. 머지 2026-09-10. ← 🔴로 진행

## 남은 것 (순서대로)

- [x] **1. 기획 저장소 — 레지스터 §9 두 행** 🟢
  `agent_discovery_settings.md` §9에 `refresh.max_attempts`(5), `refresh.attempt_timeout_seconds`(10)을 추가한다. 워커 재시도 예산이 `INGEST_*` 대신 이 두 행에서 나오므로 코드(1-3a)보다 먼저 들어가야 한다(R39: 설정의 집은 하나). 완료 조건: 두 행이 표에 있고 §11 코드 매핑 주석이 맞다.
  PR: #61 (머지 2026-09-10). §11에 "워커 예산 = `max_attempts` × `attempt_timeout_seconds` + 대기 합, 여기서 파드 종료 유예까지 나온다"를 명시. 지금 값으로 65/70/75/90 s — 현행과 같다.

- [x] **2. 1-3a 설정 클래스** 🟡
  `agent_discovery/settings.py` — 레지스터 그룹을 그대로 비추는 중첩 pydantic 모델(`Settings().rank.for_you.w_persona`), 필드 docstring = 표의 "뜻 / 올리면·내리면", `SETTINGS_OVERRIDES_PATH`(ConfigMap 파일) 딥머지, `settings_hash()` → `"v1@<hash>"`. `scripts/sync_planning_docs.py`로 레지스터 표 복사본을 `docs/`에 커밋하고, 표를 파싱해 이름·기본값·설명이 클래스와 같은지 비교하는 테스트. 아직 어디에도 연결하지 않는다.
  작은 모델 가능 범위: 표 파싱 테스트와 해시 설계를 큰 모델이 먼저 만들면, 나머지 그룹·필드 옮기기.
  완료 조건: 레지스터↔클래스 일치 테스트 통과, 해시가 값 변경에만 반응.
  PR: #19 (머지 2026-09-10). 22 그룹 67 필드, frozen·`extra="forbid"`, 부분 오버라이드는 pydantic 기본값이 채우므로 딥머지 코드 없음. `settings_hash()` = `v1@<12 hex>`(값만). 레지스터 68행 ↔ 클래스 67 리프, 차이는 `dynamodb.table_name` 하나(환경 소유, 예외 목록도 검사). 설명문은 비교하지 않는다 — 레지스터는 한국어, 코드 docstring은 영어(`CLAUDE.md`)라 다르게 읽히면 레지스터가 맞다. 886 tests. 리뷰어 지적 11건 전부 반영.

- [x] **3. 1-3b 설정 연결·env 제거** 🟢
  composition과 `worker/scheduling.py`가 새 `Settings`를 읽는다. 레지스터 행으로 대체된 `TOPIC_API_TIMEOUT_SECONDS`·`WORKER_REFRESH_*`를 config·ConfigMap·README·`.env.example`·테스트에서 제거한다. 주의: `topic_api.timeout_ms`는 레지스터 800 ms, 지금 env 기본 3 s — 1-9 실측 전에는 3000으로 시작하는 쪽이 안전(계획 파일 판단 1).
  완료 조건: `test_deploy_env_wiring.py` 통과, 두 env 키 참조 0건.
  PR: #20 (머지 2026-09-10). `topic_api.timeout_ms`는 800 대신 현행 3000에서 시작하기로 하고 레지스터를 먼저 고쳤다(#62) — 동작 변화 0. `TOPIC_API_MAX_ATTEMPTS`는 남는다(시도 예산은 환경의 결정). 두 composition root가 부팅 때 레지스터를 읽는다: 워커에서 오버라이드 파일이 잘못되면 리스너 안에서 터지고 deferq는 DLQ 없이 ack하므로 재조회가 조용히 사라진다. `compose/settings.overrides.json`이 로컬 디바운스 3 s이자 ConfigMap 마운트 파일의 워크드 예제. conftest autouse 픽스처 하나가 값·경로 캐시와 env를 되돌린다. 889 tests. 리뷰어 지적 9건 전부 반영.

- [x] **4. 1-3c 계약 스키마·도메인 인터페이스** 🟢
  `api/structs/`에 세 타입의 요청·응답 모델(envelope `contract_version, recommendation_id, resolved_topics[], agents[], empty, degraded[]`, `lang` ko·en·ja, 422/503), `agent_discovery/domain/`에 `TopicQuery`·`UserQuery`(`requester_traits` 예약)·`SourceHit`·`CandidateSource`·`VisibilityFilter`·`Ranker`·`Assembler` Protocol. route 없음.
  완료 조건: 계약 §2·§3의 예시 JSON이 모델로 파싱·직렬화된다.
  PR: #21 (머지 2026-09-10). 도메인 어휘(`Tier`·`FeatureName`·`Entry`·`Degradation`·`SourceHit`·`Features`·`RankedOwner`·`MatchedTopic`·`Signals`)와 §4의 네 Protocol(`CandidateSource[Q: Query]`·`VisibilityFilter`·`Ranker`·`Assembler`), `api/structs/discovery.py`에 요청 넷·응답 셋. 불변식 7을 타입이 지키게 했다 — 이용자가 쓴 글(`owner_note`, `HolderNote.text`)은 기본 repr에서 빠진다. 불변식 5는 응답 어디에도 "몇 개를 걸렀다"가 없다는 것으로, 필드 이름이 아니라 모델 필드 집합을 훑는 테스트로 지킨다. 레지스터가 정하는 상한(`limit` 등)은 검증 시점에 레지스터에서 읽고, 계약이 정하는 하한만 필드 제약으로 둔다. 945 tests. 리뷰어 지적 24건 전부 반영. 계약 §11에 열린 항목 하나를 남겼다 — `GET /discover/by-topic/{topic_id}`의 응답 envelope이 §3-2에 없어 타입 ②의 envelope(섹션 하나)으로 읽었다.

- [x] **5. 1-4a 이벤트 미러·CLI publish** 🟢
  `worker/events.py`를 실제 이벤트로 교체 — `topics_updated`, 임시 이름 `user_topic_settings_updated`(R48), `personal_agent_visibility_changed`, `room_created`(R46), `message_created`, `friendship_changed`, `user_registered`, `user_deactivated`(payload는 이벤트 정의서 §2). `touched` 필터 삭제(항상 재조회). `cli publish <event>` 이벤트별 서브커맨드. `tests/worker/test_user_topics.py`의 필터 테스트 4개 삭제, `test_app.py` import 한 줄.
  완료 조건: 이벤트 이름·필드가 정의서와 같고 CLI로 각 이벤트를 로컬 브로커에 넣을 수 있다.
  PR: #22 (머지 2026-09-10). 정의서 §2의 열 개 중 여덟 개를 미러(`agent_maturity_changed`는 컴포넌트 대기, `persona_updated`는 직접 쓰지 않음 — 둘 다 이유를 docstring에 적었다). 소비는 둘, 나머지 여섯은 리스너보다 먼저 선언만 — 큐는 리스너가 만드므로 비용 0. `touched` 필터는 최적화가 아니라 버그였다: `topics_updated`에는 그 필드가 없고 미러는 모르는 필드를 무시하므로 실제 이벤트의 **100%** 를 건너뛰었을 것이다. **미러의 세 규칙**은 근거가 하나다 — deferq는 역직렬화 실패도 ack하고(DLQ 없음) pydantic 에러를 `logger.exception`·Sentry로 보내는데, 그 에러는 거절한 값을, 필드 누락이면 **입력 문서 전체**를 인용한다. 그래서 모르는 필드 무시·필수 필드 없음(`null`도 부재)·식별자는 `str`이다. 못 쓰는 값은 플로우가 digest와 함께 떨군다. `discoverable`은 `bool | None`(false = 그 소유자 공개 row 전부 삭제라, 잘린 payload와 의도적 철회가 구별돼야 한다), `user_registered`의 `email`은 읽을 attribute 자체가 없다. `cli publish <event>` 여덟 서브커맨드. 리스너 rename이 버리는 큐는 **binding을 유지한 채 사본을 모은다** — 로컬에서 실제로 관찰(compose worker가 소스를 bind-mount하고 `.py`마다 재시작해 편집 중간 이름이 큐를 선언, 메시지 2건 적재). 배포 브로커에서 `deferq.arm_refresh_on_user_topic_updated`를 손으로 지워야 한다. 검증: 두 종류 3건 → `refresh.armed` ×3 → `refresh.delivered` ×1, 잘못된 user_id → 경고 1건(값 없이 digest·길이). 1014 tests. 리뷰 2회 지적 22건 전부 반영.

- [x] **6. 1-4b 저장 모델** 🟢
  PostgreSQL `visible_topic_rows`(+`descriptions`)·`agents`·`friends`·`interactions`·`room_turns`(R49)·`attributions`(R47) 테이블과 마이그레이션(계약 §6), DynamoDB 항목 저장소 `USER#…/CF_CANDIDATES`·`REC#…/LOG`·`EVT#…`·`CONFIG/CF_GATE`(§6-1). fake 저장소로 유닛 테스트, `LOCAL_STACK=1` 라이브 테스트. 아직 연결하지 않는다. 1-2b(`storage/catalog.py`)가 패턴.
  완료 조건: `alembic check` 깨끗, 불변식 1(private·hidden 없음)을 저장소 쓰기가 거부한다는 테스트.
  PR: #23 (머지 2026-09-10). 커밋 둘 — PostgreSQL 여섯 테이블·마이그레이션·드라이버 경계 하나, DynamoDB 키스페이스·item store 넷. CHECK 제약은 도메인 타입에서 만든다(`get_args(Tier)`) — 타입이 늘면 제약도 같이 는다. **불변식 7은 애플리케이션이 아니라 드라이버 경계에서 지켜야 한다**는 것을 알았다: 이용자가 쓴 글이 예외로 새는 길이 셋인데(SQLAlchemy의 `[parameters: …]`, PostgreSQL의 `DETAIL:  Failing row contains (…)`, asyncpg가 인코딩 못 한 값을 그대로 적는 `invalid input for query argument $N: <repr>`) `hide_parameters`는 첫째만 막는다. 나머지 둘은 `handle_error` 리스너가 예외를 **교체하지 않고 그 자리에서** 지운다 — 교체하면 SQLAlchemy가 원본에서 `from`으로 다시 던져 지우지 않은 원본이 `__cause__`와 모든 traceback·Sentry에 남고, `pgcode`(23505/23514를 구별하는 근거)도 잃는다. `alembic check`에는 **CHECK 비교기가 없다** — 그래서 `op.f()`를 빠뜨려 이름이 두 번 붙은 제약(`ck_friends_ck_friends_pair_is_ordered`)이 초록으로 지나갔다. 이제 `pg_constraint`를 직접 읽어 인용된 리터럴을 **집합으로** 비교하고, 음성 대조군(테이블 하나를 metadata에 더해 `AutogenerateDiffsDetected`를 확인)을 둔다. DynamoDB 쪽에서는 내가 낸 결함 넷을 테스트가 잡았다 — `served_day_key`가 **날짜로** 샤딩해 하루치 쓰기가 한 파티션에 몰렸고, naive datetime을 UTC로 정규화하지 않아 같은 시각이 `+09:00`과 `Z`에서 다른 날 파티션에 들어갔고, `read_day`가 1 MB 경계에서 조용히 끊겼고, `append_page`가 조건 없는 `update_item`이라 없는 로그에 페이지를 붙이면 TTL 없는 영생 고아를 만들었다(`attribute_exists(PK)`로 막았다). fake가 KEYS_ONLY를 잘못 흉내 낸 것(인덱스 키 속성도 함께 투영된다)은 라이브 테스트만 잡을 수 있었다. 1060 tests, 라이브 81. 리뷰 2회 지적 23건 전부 반영.

- [x] **7. 1-4c 워커가 저장소에 직접 쓴다** 🔴
  재조회 task가 `visible_topic_rows`를 통째로 교체(`agents` 없으면 생성, `topic_revision` 복제 지연 시 재시도). `worker/ingest.py`(테스트 14)·`api/routers/events/`(테스트 9)·`UserTopicsChanged`·`get_user_topics*` 삭제, 재시도 사다리를 `worker/retry.py`로, 예산은 레지스터 행에서. `test_surface_boundary.py`·`test_composition.py`·`test_budget.py`·`test_deploy_env_wiring.py` 한 줄 수정. **한 커밋으로 원자적으로.**
  완료 조건: CLI로 `topics_updated` 세 번 → 재조회 1회·row 교체 1회, 65/70/75/90 s 체인 유지.
  PR: #24 (머지 2026-09-10). 커밋 둘 — 계획이 말한 "원자적으로"는 **삭제와 대체가 한 커밋**이라는 뜻으로 읽었다: 첫 커밋은 아직 아무도 부르지 않는 코드만 더하고(도메인 투영 `PublishedTopic(s)`, `TopicApiAdapter.published_topics`, `HoldingsRepository.replace`, `worker/retry.py`), 둘째 커밋이 HTTP 홉을 지우면서 그것들을 연결한다 — 어느 시점에도 워커가 반쯤 옮겨간 상태가 없다. **재시도 분류를 클래스 이름으로 쓰면 아무것도 재시도하지 않는다**를 실측으로 배웠다: SQLAlchemy의 asyncpg 방언은 `OperationalError`를 정의만 하고 **한 번도 던지지 않는다** — 포트가 닫히면 맨 `builtins.OSError`, 접속 중 서버 오류는 `asyncpg.exceptions.*` 원본(번역은 커서 경로에서만 일어난다), 트랜잭션 도중 연결이 끊기면 `sqlalchemy.exc.InternalError`에 `connection_invalidated=True`다. 그래서 분류를 `storage/postgres.py::is_transient`로 옮겨 **플래그 → 좁은 클래스 튜플 → SQLSTATE 클래스(08·40·53·57)** 순으로 본다(asyncpg는 스텁이 없어 import하지 않는다). 사다리는 `worker/retry.py::keep_trying` 하나뿐이고 — `UpstreamUnavailable` 또는 `is_transient`만 재시도, `RetriesExhausted`는 **핸들러 밖에서** 던져 드라이버 예외가 `__cause__`로 붙지 않게 한다(불변식 7) — 레지스터가 1-4c에 남겨둔 "사다리 중첩" 질문은 워커 쪽 topic-api 전송을 **1회 시도**로 접어 풀었다(`TOPIC_API_ATTEMPTS = 1`). 사용자 대면 타임아웃을 1-9 측정 전에 조이지 않고 65/70/75/90 s 체인을 지키는 유일한 선택이었다. **`HoldingsRepository.replace`의 문장 순서가 곧 자물쇠다**: `agents` upsert가 첫 문장이어야 동시 재조회 둘이 거기서 줄을 서고, 뒤로 밀면 READ COMMITTED에서 `DELETE`가 문장 시작 시점으로 스냅숏을 뜨므로 두 집합이 **둘 다 남는다**. docstring과, `pg_stat_activity`로 잠금 대기를 확인해 인터리빙을 강제하는 라이브 테스트로 못 박았다. **표적 테스트는 변이로만 증명된다**를 셋 배웠다 — 범위 없는 `DELETE`가 전 테스트를 통과했고(모든 테스트에 소유자가 하나였다), 첫 직렬화 테스트는 잡으려던 변이를 통과했고, `assert app.TOPIC_API_ATTEMPTS == 1`은 동어반복이었다(이제 실제 전송의 `_max_attempts`를 본다). 헤더 규칙의 음성 대조군은 규칙과 **똑같은 방식으로 눈이 멀어** 있었다: `route.dependant.header_params`는 엔드포인트 자기 시그니처만 본다 — 의존성 트리를 직접 걸어 고쳤고, `from __future__ import annotations` 아래에서는 테스트 함수 안에 정의한 의존성이 조용히 사라진다는 것도 같이 알았다. 검증: publish 3건 → `refresh.armed` ×3 → `refresh.stored topics=2`, row 둘(public·friends, `topic_maturity` null, `agents.discoverable` false), 토픽을 private로 돌리면 다음 재조회에서 사라진다(2→1), topic-api를 내리면 1/2/4/8 s 사다리 뒤 `worker.gave_up`, PostgreSQL을 내려도 같은 사다리(`gaierror` — 첫 분류였다면 통째로 건너뛰었을 예외다). 1081 tests(라이브 포함 1115). 리뷰 2회 지적 29건 중 28건 반영, 1건은 실험 둘을 섞은 오진이라 근거를 들어 거절했다.

- [x] **8. 1-4d 나머지 리스너** 🟡
  흐름마다 한 커밋. 🟢 `friendship_changed`(friends 미러), `user_registered`(agent id 결정론 계산, `email` 안 읽음), `user_deactivated`(삭제·익명화), `message_created`(`room_turns` +1). 🔴 `room_created`(agent_dm 필터, attributions 조인, `last_active_at`), `personal_agent_visibility_changed`(소유자 row 일괄 삭제), 그리고 모든 리스너의 `event_log` append.
  완료 조건: 구현 계획 1-4 완료 조건 전부(순서 뒤바뀐 `message_created`도 turn 보존).
  PR: #25 (머지 2026-09-11). 커밋 다섯 — 공용 배관·이벤트 로그, friends 미러, `agents` row를 쓰는 둘, 대화·turn·탈퇴, 그리고 실측이 잡은 버그 하나. **모든 리스너가 자기 이벤트를 흐름보다 먼저 기록한다**(계약 §6-1) — 실패한 흐름이야말로 리플레이 대상인데 deferq는 어느 쪽이든 ack하기 때문이고, DynamoDB가 죽어도 경고 한 줄로 넘어간다(저장소가 제품, 로그는 경위서). 여기서 **시각을 둘로 갈랐다**: `occurred_at`은 발행자 것이고 키라서 하루치 읽기가 *행동*의 하루가 되고, 보존은 우리가 소비한 시각부터 센다 — 아니면 옛 시각으로 찍힌 이벤트가 **이미 만료된 채** 들어와 다음 스윕에 조용히 사라진다. 가드는 마커가 아니라 행동이다: 레지스트리를 돌며 모든 리스너를 실제로 불러 ①기록되는지 ②자기 로그보다 **먼저** 기록되는지 본다. **deferq의 동시성이 이번 설계의 축이었다** — `prefetch_count=WORKER_CONCURRENCY`에 메시지마다 태스크라, 한 큐에서 열이 동시에 돌고 **커밋 순서가 곧 결과 순서**다. 재시도 backoff가 그 창을 초 단위로 벌린다. `discoverable`은 그래서 마이그레이션 0003(`visibility_changed_at`)으로 고쳤다 — 켜기→끄기가 뒤집히면 최종 상태가 **discoverable=true**, 불변식 1을 지는 플래그가 열린 채 실패한다. 이제 자기보다 오래된 이벤트는 플래그도 row도 건드리지 않는다(오래된 `false`가 지금 보이는 사람을 비우면 안 되니까). **`friends`는 같은 방법으로 못 고친다** — `removed`가 row를 지우니 늦게 온 `accepted`에게는 비교할 시각이 없다. R50 결정 대상. **숨긴 소유자의 row는 다음 재조회에 되살아난다**: `discoverable`은 "숨김"이자 "bourbon-api가 아직 말 안 함"이고 기본값 false인데 R23 이벤트를 아직 아무도 발행하지 않아, 재조회가 이 플래그를 존중하면 누구의 row도 저장되지 않는다. 삭제는 즉시성이고 답에서 숨기는 건 **읽기가 `agents.discoverable`을 조인하는 것**이다 — 라이브 테스트로 현재 사실을 못 박아 반대를 전제로 짜지 못하게 했다. `room_created`는 bourbon-api가 기각하고 대안을 줬다(R46 대안 (a)) — 다음 단계에서 교체하므로 이번 구현은 오늘의 R46이다. **리뷰가 못 본 것을 실측이 잡았다**: 이벤트 로그를 처음 진짜 테이블에서 읽자 `_whole_query`가 boto3에 `None`을 넘겨 전부 `ParamValidationError`였는데, **라이브 테스트의 stand-in이 그 `None`을 지워주고** 있어 초록이었다 — 대역이 대상의 결함을 대신 메우고 있었다. 검증: `topics_updated` ×3 → 재조회 1회·row 2, 비공개 전환 → row 0, 그보다 **오래된 `true`는 `visibility.superseded`**, `message_created` 둘을 `room_created`보다 **먼저** → turn 2 보존 뒤 조인으로 `entry`·`recommendation_id` 채워진 `interactions` 1행 + `last_active_at` 갱신, 탈퇴 → 그 사람 흔적 전부 0이고 그가 한 대화는 다른 actor id로 남음, 이벤트 로그 하루치 7종 17건에 `email` 없음. 1149 tests(라이브 포함 1218). 리뷰 3회 지적 33건 중 30건 반영.

  이어서 나간 것 둘 — 같은 1-4d의 주제이고, 하나는 리뷰가, 하나는 bourbon-api의 답이 만들었다.
  **#26 (R50, 머지 2026-09-11)**: `friends` 미러가 지우기를 그만둔다. deferq는 큐 하나에서 메시지마다 태스크를 돌리므로 한 쌍에 대한 이벤트 둘이 **커밋 순서**로 정착하고, 재시도 backoff가 그 창을 초 단위로 벌린다 — `accepted`가 뒤에 커밋하면 **끊은 친구가 계속 보이고**, friends tier는 후보 조회 쿼리 안의 필터라 조용하며 프라이버시에 닿는다. 지우는 설계로는 못 고친다: 지워진 row에는 늦게 온 이벤트가 질 시각이 없다. 그래서 `state`·`changed_at`(발행자 시각)을 남기고 새 이벤트에만 진다. **탈퇴도 같은 이유로 친구관계를 지우지 않고 끝낸다** — 이건 원래 있던 결함이었다: row가 사라진 뒤 날아온 `accepted`가 떠난 사람을 누군가의 친구로 **영구히** 되살렸다. 시각을 섞지 않는 것도 배웠다 — 브로커 발행 시각은 같은 메시지의 `occurred_at`보다 항상 늦어서, fallback으로 날짜를 매기면 부활이 뒷문으로 돌아온다. 대가 둘을 감수한다: 읽는 쪽마다 조건이 하나 늘고(그래서 `state`를 아는 곳을 한 군데로 묶고 소스를 훑는 테스트를 뒀다), tombstone이 스윕 전까지 쌓인다.
  **#27 (R51·R52·R53, 머지 2026-09-11)**: `room_created` 요청을 철회하고 대화 시작을 **그 방의 첫 `message_created`** 로 안다. bourbon-api가 준 대안 route는 우리에게 없는 것이 **소유자 id 하나**인데 대가로 이용자 메시지 본문이 딸려 오고(끄지 못한다), 방 종류도 creator도 생성 시각도 주지 않는다. 대신 agent DM의 room id가 (유저, agent)의 결정론적 함수라 **추천을 낼 때 미리 계산**해 둔다. `room_turns` upsert가 개수를 돌려주니 "이 방 처음 본다"가 이미 하던 쓰기에 딸려오고, 그때 한 번 조회한다. 부수 이득: `room_created`가 create 분기에서만 나와 못 보던 **재방문**이 보인다. 감수한 것: 추천 밖 대화는 기록하지 않고(R52 — 인기도·CF·R28이 추천 전용 표본을 읽게 되므로 **못 찾은 방마다 카운터**를 올려 1-7에서 다시 판단한다), 시작 시각이 방 생성이 아니라 첫 메시지가 된다. 어트리뷰션은 보고와 예측 둘 다 두고 **보고가 이기며**(R53), 어느 쪽이었는지 `interactions.attributed_by`에 남긴다 — 구별하지 않으면 R47이 재려던 화면별 수치가 누르지 않은 방문으로 부푼다.
  이 둘이 남긴 것: `identity.py`가 room id도 계산하고(벡터는 bourbon-api의 함수로 직접 뽑았다), 마이그레이션 0004·0005, 그리고 **예측 인덱스를 쓰는 쪽은 1-5**라는 이음매 — 그게 붙기 전까지는 어떤 대화도 기록되지 않는다.

- [x] **9. 1-4e 첫 공개 route** 🔴
  `POST /api/svc/agent-discovery/attributions`(계약 §2-5), `PUBLIC_PREFIX`, 라우터를 `api/routers/internal/`·`public/`으로 분리. `test_surface_boundary.py`를 "route는 모듈이 말하는 prefix 아래에만, 내부 route는 `x-user-id`를 읽지 않는다"로 재작성.
  완료 조건: 공개 route가 edge-auth 헤더로 요청자를 잡고 내부 route에는 헤더 의존이 없다는 테스트.
  PR: #28 (머지 2026-09-11). 커밋 넷 — 저장소 쓰기, 라우터 분리, 공개 surface와 route, CORS. **두 surface는 정반대 규칙을 갖고, 그 규칙을 지키는 것은 테스트뿐이다.** 내부 prefix에서는 공유 정책이 edge-auth를 건너뛰므로 `x-user-id`가 호출자가 쓴 값이고 아무도 읽지 않는다. 공개 prefix에서는 사이드카가 그 헤더를 **덮어쓰므로** 요청자는 반드시 헤더이고 body에 같은 뜻의 필드가 있으면 안 된다. 어디에 마운트하느냐가 검사 여부를 정하는 전부인데 메시 정책은 잘못 놓인 route를 알아채지 못한다 — 그래서 route가 **정의된 패키지**를 읽는 경계 테스트로 옮겼고(목록이 아니라), 라우터를 `api/routers/internal/`·`public/`으로 가른 것이 그 때문이다. 헤더가 없으면 **403이지 401이 아니다** (계약 §1): 사이드카는 허용한 모든 요청에 넣으므로 없다는 건 "검사를 지나오지 않음"이고, 세션 갱신은 도움이 안 되며 우리는 자격증명을 읽지도 못한다. **`reported_at`은 우리 시계다** — §2-5 payload에 시각이 없다. 읽는 쪽이 이것을 bourbon-api가 찍은 대화 시작 시각과 `<=`로 자르므로 시계가 둘이고, 비용은 한쪽으로만 간다: 우리가 앞서면 보고가 자기 대화를 놓치고 예측(R51)이나 `direct`가 답할 뿐, 아직 나가지 않은 추천에 대화가 붙지는 않는다. 204는 "미뤘다"가 아니라 "답할 게 없다"이고, 쓰기가 실패하면 500이다 — best-effort는 클라이언트가 답을 무시해도 된다는 뜻이지 우리가 지어내도 된다는 뜻이 아니다. **계획에 없던 커밋 하나를 넣었다(CORS).** 실측으로 preflight가 405에 CORS 헤더 0개였다. edge-auth는 preflight를 검사에서 빼므로 위쪽 누구도 답하지 않고, 브라우저는 거기서 멈춘다 — 만들어 놓고 브라우저가 못 부르는 surface였다. 셋을 코드로 막았다: `*`는 버리고(Starlette이 `*`+credentials를 "물어본 origin을 되돌려준다"로 읽어, 우리가 소유하지 않은 ConfigMap의 한 글자가 세션 실은 cross-site POST를 막는 유일한 장치를 무력화한다), **공개 prefix에만** 답하고(`CORSMiddleware`는 라우터를 안 봐서 그냥 붙이면 edge-auth가 건너뛰어지는 내부 prefix에도 답한다), 가장 바깥에 둔다. **리뷰 3회 지적 40건 전부 반영, 블로커 둘 다 내가 쓰려던 코드 밖에 있었다.** 하나는 **단위 테스트가 아무것도 검사하지 않던 것** — 컴파일된 SQL 문자열에서는 모든 값이 `%(name)s` 자리표시자라, user id 쌍을 뒤바꾸든 `reported_at`을 안 쓰든 `entry`를 상수로 박든 네 변이가 전부 초록이었다(바인딩된 파라미터를 통째로 비교하도록 바꾸고 네 변이를 실제로 만들어 확인). 다른 하나는 **배포 순서**: API가 DB 클라이언트가 되면서 boot이 막히는데 Secret은 손으로 넣는 것이고 `optional: true`였다 — 키 없는 네임스페이스에서 CrashLoopBackOff이고 내부 `/recommend`까지 같이 못 뜨며 이유는 어디에도 안 적힌다. `optional`을 빼서 kubelet이 **없는 키 이름을 말하며** 거부하게 했다(단, 이건 *없는* 경우만 잡는다 — 엔진 생성은 아무 데도 연결하지 않고 readiness는 DB를 묻지 않으므로 틀린 DSN은 멀쩡히 뜬다). 나머지 지적의 가장 큰 묶음은 **"규칙이 빈 집합 위에서 참"**이었다: body 필드 워커가 `Report | None`과 중첩 모델을 못 봄, 헤더 워커가 `request.headers.get()`을 구조로 못 봄(텍스트로 막음), 공개 route가 `OPTIONS`를 받으면 안 된다는 규칙 부재(preflight는 검사 면제라 그 헤더가 클라이언트 것인데 기존 단언은 그런 route를 **승인**한다), 가드 없는 단언 하나, 공개 테스트가 fake를 빠뜨리면 진짜 DB에 쓰던 것. 새 가드는 전부 변이로 확인했다. 1176 tests(라이브 포함 1259). **남는 전제 둘**: dev·prod Secret의 `DATABASE_URL` 확인(머지 전), 그리고 bourbon-api 경로 레지스트리에 공개 prefix 등록(요청서 §2-2, PR #70) — 없으면 밖에서는 SPA catch-all로 떨어져 HTML이 돌아온다. CORS 커밋이 그 등록보다 **먼저** 머지돼야 한다.

- [x] **10. 1-5 타입 ①②** 🔴
  `topic_index` 소스(친구 배열 조건, GROUP BY owner, 커버리지 정렬), 랭커 가중합(레지스터 §2), Assembler hydration(`lang` 하나, 응답 직전 재확인, `hydration_partial`), `/recommend/explicit`, `/discover/by-topic`(+섹션 커서), 결정 로그 쓰기. 기존 `POST /recommend` 유지.
  완료 조건: walkthrough §3·§4 예제 데이터로 문서의 순서가 재현, friends row 유출 0건.
  PR: (`recsys/1-5-topic-index-answers`, 번호는 머지 때 채운다). 커밋 여섯 — 저장소의 읽는 쪽, ports, 소스와 커서, 랭커, Assembler, 그리고 두 route. **조건이 쿼리 안에 있다는 것이 이 단계의 뼈대다**(R17): 두 읽기가 `_eligible` 하나를 공유하고 **tier·친구 집합·공개 여부를 인자로 받지 않아** 넓게 부르는 호출이 타입 수준에서 없다. 후보 조회는 세 단계다 — `(owner, topic)`당 강도 하나(테이블 키가 한 topic을 두 tier로 허용하고, row로 세면 커버리지가 부풀고 점수가 두 번 더해진다: 실측으로 강도 0.8이 1.0을 이겼다) → 소유자를 커버리지·강도로 정렬해 자름(답은 사람의 목록이라 LIMIT이 여기) → 그 소유자들의 row 읽기. 랭커는 문서의 **0.707 / 0.719를 그대로** 내고, `topic_score`를 매칭 수가 아니라 **물어본 topic 수**로 나눈다(매칭 수로 나누면 커버리지가 두 번 값을 치른다). Assembler는 마지막 읽기로 결정하고(불변식 4) 커버리지·성숙도를 **살아남은 것에서** 다시 계산한다 — §3-1의 `topic_maturity`는 `matched_topics 중 최고`라, 랭킹 시점 벡터에서 읽으면 더 이상 싣지 않는 row의 값이 카드에 남는다. **리뷰가 잡은 진짜 버그 하나**: 페이지는 랭킹의 창이 아니라 **저장소 순서의 창**이다. 창 전체를 랭크하고 자르면 잘리는 것이 "저장소가 마지막에 준 소유자"가 아니라 "랭킹이 마지막인 소유자"라, 다음 페이지가 이미 보여준 카드를 다시 내고 잘린 카드를 영영 건너뛴다(레지스터 기본 가중치로 재현: 카드 하나짜리 셸프가 한 사람을 두 번, 세 번째를 0번). 이제 저장소의 앞 `page_size`명만 랭크·조립하고 그 너머 하나는 "다음 페이지가 있나"에만 쓴다. 결정 로그 페이지 append는 **요청자로 조건**을 건다 — 커서는 불투명하되 서명하지 않으므로, 남의 목록에 페이지가 붙어 "한 사람이 다른 사람의 답을 읽었다"는 평가 데이터가 생기는 것을 막는 건 그 조건뿐이다(dynamodb-local로 확인). **유저의 말이 Sentry로 새고 있었다 — 로깅 호출이 아닌 두 경로**: 파싱된 요청 body가 요청 전체의 scope에 붙어 그 요청의 **모든** 이벤트에 실리고(길다고 거절한 바로 그 422에도), 나가는 모든 호출이 query string을 breadcrumb로 남기는데 topic 검색의 `?q=`가 곧 유저의 말이라 무관한 요청의 이벤트까지 따라간다. 설정을 읽어서가 아니라 **SDK가 보낼 이벤트를 캡처해서** 찾았고(다섯 이벤트 → 0건), 이전 route에도 있던 문제라 이번에 같이 닫았다. 검증: walkthrough §3-4·§3-5와 §4-2·§4-3을 **실제 row로** 재현, 답 → `message_created` → `interactions` 1행 `attributed_by = predicted`, compose 스택에서 공개 route 직접 호출(403/200/404/422, 커서가 목록 id를 잇고 결정 로그가 `pages[]`까지 되읽힘). 1343 tests(라이브 포함 1447). 리뷰 4회 지적 33건 전부 반영.

- [ ] **11. 1-6 합성 생성기·시드·테스트 CLI** 🟡
  🔴 `synthetic/` 생성기(스펙 §2~§6, 자체 검증). 🟢 `scripts/seed_local.py`(PostgreSQL·DynamoDB·목 서버 픽스처 적재, `--users`), `cli recommend|publish|seed|validate` 골격.
  완료 조건: 10만 유저 적재가 노트북에서 10분 안, 세 타입 CLI가 응답.
  PR: —

- [ ] **12. 1-7 타입 ③** 🔴
  `popularity`·`content_similarity` 소스, 콜드스타트 경로, `/discover/for-you`, `persona_similarity` 자리(값 0, R42).
  완료 조건: walkthrough §5 예제 재현, 이미 대화한 상대 제외와 소진 뒤 재노출(R28).
  PR: —

- [ ] **13. 1-8 CF·게이트** 🔴
  `implicit` ALS 학습 배치, R19 스윕이 `cf_candidates`를 DynamoDB에, R35 자동 게이트(λ=3에서 안 올리고 λ=10에서 올림).
  완료 조건: 구현 계획 1-8 완료 조건.
  PR: —

- [ ] **14. 1-9 검증** 🔴
  합성 10만 유저로 품질·지연 시간·불변식 위반 0건 측정, 결과를 이 저장소 검증 문서에 기록. `topic_api.timeout_ms` 값 확정.
  PR: —

- [ ] **15. 1-10 배포 준비** 🟢
  요청서 발송(`requests/`), `DATABASE_URL`의 `optional: true` 제거, Redis DB 번호 반영, `INGEST_BASE_URL` 등 잔여 키 정리, go-live 차단 항목 해소.
  PR: —

## 미룬 소소한 것 (해당 PR에서 되짚기)

- 목 서버 검색 `limit`은 최상위 노드만 자른다(topic-api는 `is_match` 노드를 셈) — 1-6에서 픽스처가 커지면 확인.
- compose `init`의 테이블 생성 재시도 루프에 상한이 없다 — 엔드포인트가 틀리면 멈춘다. 물리면 상한을 준다.
- `k8s/overlays/dev` Redis DB 10은 할당받지 않은 번호다(인프라 요청서 §3) — 1-10.
- `popularity`는 계약 §6의 일곱째 집합인데 만들지 않았다 — 레지스터 행이 **감쇠 집계**를 말하므로 저장 스칼라·머티리얼라이즈드 뷰·`interactions` 직접 쿼리 중 무엇인지가 타입 ③ 결정이다(1-7). 입력은 이미 다 있다(`interactions.started_at`, `room_turns.turns`).
- `interactions`는 계약이 정한 `(actor, owner, room_id)` PK를 그대로 둔다 — `started_at` 월 파티셔닝을 하려면 그 컬럼이 키에 들어가야 하고, #23에서 더한 `UNIQUE (room_id)`가 그 자리를 대신 맡을 수 있다. 계약 편집이라 오너 판단.
- 완료 조건의 "`topic_revision` 복제 지연 시 재시도"는 하지 않았다 — topic-api의 목록 응답에 revision이 없고, 디바운스는 이벤트의 revision을 **설계상** 버린다(유저당 uid 하나짜리 슬롯을 upsert하므로 최댓값을 합칠 자리가 없다). 코드로 흉내 내는 대신 topic-api에 대한 요청으로 남긴다.
- 오버레이가 `SETTINGS_OVERRIDES_PATH`에 파일을 마운트하는 날 `test_the_worker_pod_outlives_the_delivery_it_may_be_draining`이 조용히 무의미해진다 — 테스트는 레지스터의 **코드 기본값**을 읽고 `worker/app.py`는 `get_settings()`를 읽는다. 테스트 docstring에 적어뒀고, 오버레이가 실제로 마운트하는 PR에서 고친다.
- `agents`에 `visibility_changed_at`을 더했다(마이그레이션 0003) — 계약 §6 `agents` 값 목록에 한 줄 추가이고 읽는 쪽은 그대로다. 순서 없는 이벤트 둘을 비교할 자리가 필요해서지 새 의미가 아니다.
- ~~**읽기가 `agents.discoverable`을 조인해야 한다**(1-5)~~ — **했다**(항목 10). 계약 §6의 후보 조회 쿼리에는 그 조인이 없지만, 플래그가 false로 시작하고 topic 이벤트가 그보다 먼저 row를 만들므로 `visible_topic_rows`에는 비공개 소유자의 row가 정상적으로 존재한다. 후보 조회와 응답 직전 재확인 둘 다 `agents`를 INNER JOIN 하고 `discoverable`을 조건에 넣으며(`agents` row 자체가 없으면 "말 안 한" 것이지 허락한 것이 아니다), 공개 row를 가진 비공개 소유자(walkthrough의 F)로 라이브 테스트가 그것을 지킨다. 타입 ③ 소스도 같은 조건을 써야 한다(1-7).
- **`rank.w_recency`는 지금 아무 효과가 없다.** 레지스터 §2에 가중치 행은 있는데 감쇠 스케일 행이 없다 — "얼마나 최근이면 1인가"를 정하지 않으면 0~1로 만들 수 없고, 코드에 반감기를 지어내면 R39가 "설정은 한 곳"이라고 한 그 한 곳이 둘이 된다. 입력(`visible_topic_rows.updated_at`)은 이미 있으므로 행 하나면 켜진다. 1-7에서 `popularity`(소스가 그때 생긴다)와 같이 본다 — 둘 다 지금은 `present`에 없고 가중합이 0을 곱한다.
- **walkthrough §3-1의 "점수 상위 3개"는 코드가 그대로 할 수 없다.** grounding은 그룹당 topic 하나를 확정하거나 못 하거나이고 그룹에 점수가 없다. 구현은 그룹 순서로 앞에서 `explicit.topic_max`개를 자른다 — 0번이 verbatim 그룹이라 무엇이 잘리든 이용자가 실제로 친 말은 검색된다. 그룹에 confidence가 생기는 날 다시 볼 문장.
- **API 프로세스가 DynamoDB 클라이언트가 됐다**(항목 10). 결정 로그와 예측 room 인덱스를 답할 때마다 쓴다. 워커와 달리 부팅 때 테이블을 확인하지 않는다 — 그 두 쓰기는 이미 맞는 답에 대한 증거라 실패해도 답이 나가야 하고, 확인을 넣으면 "지금 DynamoDB가 닿나"가 모든 추천 앞에 서기 때문이다. dev·prod 파드가 그 테이블에 쓸 수 있는지는 배포 전 확인 항목이다.
- **코드 상수 둘이 레지스터 행 후보다**: 저널 쓰기 예산(3 s — 답이 나간 뒤의 쓰기가 요청을 붙잡는 상한)과 DynamoDB 전송 타임아웃(connect 2 s / read 3 s / 2회). 둘 다 "실패가 얼마나 비싼가"를 정할 뿐 답의 모양을 정하지 않아 지금은 코드에 뒀다. 1-9에서 실측하며 레지스터로 올릴지 본다.
- bourbon-api의 `ensure_agent_dm_room`이 아직 **친구가 아니면 방 생성을 거부**한다(`FriendshipRequiredError`). 오늘 기준으로 비친구에게 추천이 나가도 채택 자체가 불가능하다 — R46이 "친구 게이트를 풀면서"라고 적어둔 그 게이트다. 우리 일정이 아니라 플랫폼 일정 항목.
