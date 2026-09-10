# Agent-Discovery-Planning

`bourbon-agent-discovery-api`의 설계 문서. **2026-09-08 재설계 출발점부터 다시 시작했다.** 이전 문서는 전부 `archive/2026-09-08_pre-redesign/`에 있고 그 안의 결정은 유효하지 않다.

## 문서 — 읽는 순서대로

| 순서 | 문서 | 내용 | 상태 |
|---|---|---|---|
| 1 | [`agent_discovery_redesign.md`](agent_discovery_redesign.md) | 제품 모델(세 타입·visibility·friend·성숙도), 구현 뼈대(R34 이후 단일 구현: PostgreSQL 인덱스·인기도·content + `implicit` ALS — A안/B안 절은 비교 설계 시점의 기록), 10만 합성 유저 검증 프로토콜, 열린 항목. 나머지 문서의 뿌리 | 출발점 |
| 2 | [`decisions.md`](decisions.md) | 오너가 정한 것(R01–R49)과 정해지지 않은 것(O5·O6·O15·O20 — 나머지 O1~O19·O21은 닫힘). **본문이 이 표와 다르면 표가 맞다** | 유효 |
| 3 | [`agent_discovery_contract.md`](agent_discovery_contract.md) | 구현이 지키는 것: 타입별 route·요청·응답, 후보 소스/필터/랭커 인터페이스, 불변식 8개, 저장 모델, feature 표, 결정 로그 | 초안 |
| 4 | [`agent_discovery_events.md`](agent_discovery_events.md) | 있는 이벤트의 소비, 우리가 먼저 정의할 이벤트, 카탈로그 그래프 내부 route 요청(§2-8), 발행 지점 필드 검증, 확인 항목 | 초안 rev 2 |
| 5 | [`synthetic_population_spec.md`](synthetic_population_spec.md) | 검증(소스별 ablation·부하·CF 게이트)의 정답 데이터를 만드는 생성기: 파라미터·순서·출력·정답·검증. §8은 서비스가 돌기 시작한 뒤 이벤트에서 파라미터를 자동으로 갈아 끼우는 절차 | 초안 |
| 6 | [`library_verification.md`](library_verification.md) | 재설계 §5-1 후보(Gorse·`implicit`·LightFM·OpenSearch)와 B안(PostgreSQL·동시 출현)을 같은 10만 합성 유저로 실측. O8·O11(→ R33·R34)의 근거. 재현은 `spikes/` | 실측 2026-09-08 |
| 7 | [`agent_discovery_walkthrough.md`](agent_discovery_walkthrough.md) | 1~6을 읽고도 "요청 하나가 실제로 어떻게 흐르나"가 안 그려질 때. 예제 하나(요청자 R, 소유자 A~H)로 세 타입·저장소를 끝까지 따라간다. `implicit`이 무엇을 읽고 쓰는지 포함. Gorse·동시 출현 CF 절은 R34 이전 비교 기록 | 설명 (결정 없음) |
| 8 | [`agent_discovery_settings.md`](agent_discovery_settings.md) | 설정 레지스터(R39): 모든 설정값의 이름·기본값·뜻·올리고 내릴 때의 효과·출처 결정. 다른 문서는 값을 쓰지 않고 여기를 가리킨다 | 초안 |
| 9 | [`implementation_plan.md`](implementation_plan.md) | 구현 단계와 완료 조건(R43): 갭 정리 → 로컬 스택 → 설정·계약 → 저장·적재 → 타입 ①② → 생성기·시드 스크립트·CLI → 타입 ③ → CF → 검증 → 배포 준비. 순서의 이유와 열린 구현 판단 | 계획 |
| 10 | [`requests/`](requests/README.md) | 받는 곳별 요청서(인프라·bourbon-api·클라이언트·bourbon-agent·topic-api). 이벤트 정의서 §6의 묶음을 그대로 붙여 넣을 수 있는 문장으로. 보내는 시점은 1차 배포 즈음 | 초안 |
| 참고 | [`archive/`](archive/) | 이전 문서 전부. `2026-09-08_pre-redesign/README.md`가 그 안에서 사실·실측·단가·코드 독해로 남는 것을 안내한다 | 아카이브 |

새 문서는 이전 결정 번호(D, C, S, K …)를 인용하지 않는다. 필요한 제약은 본문에 글로 풀어 쓴다.

## 다음 할 일

1. 코드 repo에서 워커의 이벤트 미러를 실제 이름(`bourbon.topics_updated`)으로 고치고, 새 이벤트 셋을 선언하고, CLI 발행 명령을 만든다.
2. 합성 모집단 생성기 구현, 10만 유저 생성.
3. 단일 구현(R34) → 합성 모집단으로 검증(재설계 §6, 소스별 ablation) → 설정 초기값 확정(`agent_discovery_settings.md`).
