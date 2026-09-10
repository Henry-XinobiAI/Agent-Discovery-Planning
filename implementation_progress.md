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

- [ ] **3. 1-3b 설정 연결·env 제거** 🟢
  composition과 `worker/scheduling.py`가 새 `Settings`를 읽는다. 레지스터 행으로 대체된 `TOPIC_API_TIMEOUT_SECONDS`·`WORKER_REFRESH_*`를 config·ConfigMap·README·`.env.example`·테스트에서 제거한다. 주의: `topic_api.timeout_ms`는 레지스터 800 ms, 지금 env 기본 3 s — 1-9 실측 전에는 3000으로 시작하는 쪽이 안전(계획 파일 판단 1).
  완료 조건: `test_deploy_env_wiring.py` 통과, 두 env 키 참조 0건.
  PR: —

- [ ] **4. 1-3c 계약 스키마·도메인 인터페이스** 🟢
  `api/structs/`에 세 타입의 요청·응답 모델(envelope `contract_version, recommendation_id, resolved_topics[], agents[], empty, degraded[]`, `lang` ko·en·ja, 422/503), `agent_discovery/domain/`에 `TopicQuery`·`UserQuery`(`requester_traits` 예약)·`SourceHit`·`CandidateSource`·`VisibilityFilter`·`Ranker`·`Assembler` Protocol. route 없음.
  완료 조건: 계약 §2·§3의 예시 JSON이 모델로 파싱·직렬화된다.
  PR: —

- [ ] **5. 1-4a 이벤트 미러·CLI publish** 🟢
  `worker/events.py`를 실제 이벤트로 교체 — `topics_updated`, 임시 이름 `user_topic_settings_updated`(R48), `personal_agent_visibility_changed`, `room_created`(R46), `message_created`, `friendship_changed`, `user_registered`, `user_deactivated`(payload는 이벤트 정의서 §2). `touched` 필터 삭제(항상 재조회). `cli publish <event>` 이벤트별 서브커맨드. `tests/worker/test_user_topics.py`의 필터 테스트 4개 삭제, `test_app.py` import 한 줄.
  완료 조건: 이벤트 이름·필드가 정의서와 같고 CLI로 각 이벤트를 로컬 브로커에 넣을 수 있다.
  PR: —

- [ ] **6. 1-4b 저장 모델** 🟢
  PostgreSQL `visible_topic_rows`(+`descriptions`)·`agents`·`friends`·`interactions`·`room_turns`(R49)·`attributions`(R47) 테이블과 마이그레이션(계약 §6), DynamoDB 항목 저장소 `USER#…/CF_CANDIDATES`·`REC#…/LOG`·`EVT#…`·`CONFIG/CF_GATE`(§6-1). fake 저장소로 유닛 테스트, `LOCAL_STACK=1` 라이브 테스트. 아직 연결하지 않는다. 1-2b(`storage/catalog.py`)가 패턴.
  완료 조건: `alembic check` 깨끗, 불변식 1(private·hidden 없음)을 저장소 쓰기가 거부한다는 테스트.
  PR: —

- [ ] **7. 1-4c 워커가 저장소에 직접 쓴다** 🔴
  재조회 task가 `visible_topic_rows`를 통째로 교체(`agents` 없으면 생성, `topic_revision` 복제 지연 시 재시도). `worker/ingest.py`(테스트 14)·`api/routers/events/`(테스트 9)·`UserTopicsChanged`·`get_user_topics*` 삭제, 재시도 사다리를 `worker/retry.py`로, 예산은 레지스터 행에서. `test_surface_boundary.py`·`test_composition.py`·`test_budget.py`·`test_deploy_env_wiring.py` 한 줄 수정. **한 커밋으로 원자적으로.**
  완료 조건: CLI로 `topics_updated` 세 번 → 재조회 1회·row 교체 1회, 65/70/75/90 s 체인 유지.
  PR: —

- [ ] **8. 1-4d 나머지 리스너** 🟡
  흐름마다 한 커밋. 🟢 `friendship_changed`(friends 미러), `user_registered`(agent id 결정론 계산, `email` 안 읽음), `user_deactivated`(삭제·익명화), `message_created`(`room_turns` +1). 🔴 `room_created`(agent_dm 필터, attributions 조인, `last_active_at`), `personal_agent_visibility_changed`(소유자 row 일괄 삭제), 그리고 모든 리스너의 `event_log` append.
  완료 조건: 구현 계획 1-4 완료 조건 전부(순서 뒤바뀐 `message_created`도 turn 보존).
  PR: —

- [ ] **9. 1-4e 첫 공개 route** 🔴
  `POST /api/svc/agent-discovery/attributions`(계약 §2-5), `PUBLIC_PREFIX`, 라우터를 `api/routers/internal/`·`public/`으로 분리. `test_surface_boundary.py`를 "route는 모듈이 말하는 prefix 아래에만, 내부 route는 `x-user-id`를 읽지 않는다"로 재작성.
  완료 조건: 공개 route가 edge-auth 헤더로 요청자를 잡고 내부 route에는 헤더 의존이 없다는 테스트.
  PR: —

- [ ] **10. 1-5 타입 ①②** 🔴
  `topic_index` 소스(친구 배열 조건, GROUP BY owner, 커버리지 정렬), 랭커 가중합(레지스터 §2), Assembler hydration(`lang` 하나, 응답 직전 재확인, `hydration_partial`), `/recommend/explicit`, `/discover/by-topic`(+섹션 커서), 결정 로그 쓰기. 기존 `POST /recommend` 유지.
  완료 조건: walkthrough §3·§4 예제 데이터로 문서의 순서가 재현, friends row 유출 0건.
  PR: —

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
