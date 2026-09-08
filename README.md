# Agent-Discovery-Planning

`bourbon-agent-discovery-api`의 설계 문서. **2026-09-08 재설계 출발점부터 다시 시작했다.** 읽는 순서는 `HOW_TO_READ.md`.

| 문서 | 내용 | 상태 |
|---|---|---|
| [`agent_discovery_redesign.md`](agent_discovery_redesign.md) | 제품 모델(세 타입·visibility·friend·성숙도), 두 구현안(오픈소스 중심 / 직접 구현)과 혼합, 10만 합성 유저 비교 프로토콜, 열린 질문 | 출발점 |
| [`decisions.md`](decisions.md) | 결정 레지스터 R01–R16, 열린 항목 O1–O16 | 유효 |
| [`agent_discovery_contract.md`](agent_discovery_contract.md) | 타입별 route·요청·응답, 후보 소스/필터/랭커 인터페이스, 불변식, 저장 모델, feature 표, 결정 로그 | 초안 |
| [`agent_discovery_events.md`](agent_discovery_events.md) | 있는 이벤트의 소비, 우리가 먼저 정의할 이벤트, 발행 지점 필드 검증, 확인 항목 | 초안 rev 2 |
| [`synthetic_population_spec.md`](synthetic_population_spec.md) | 합성 모집단 생성기 파라미터·순서·출력·정답·검증, §8 실측 보정(이벤트 → 파라미터 자동 갱신) | 초안 |
| [`library_verification.md`](library_verification.md) | §5-1 후보(Gorse·`implicit`·LightFM·OpenSearch)와 B안(PostgreSQL·동시 등장)을 10만 합성 유저로 실측. O8·O11의 근거. 스크립트는 `spikes/` | 실측 2026-09-08 |
| [`archive/`](archive/) | 이전 문서 전부. `2026-09-08_pre-redesign/`의 결정은 유효하지 않고 실측·단가·코드 독해만 참고 | 아카이브 |

## 다음 할 일

1. 코드 repo에서 워커의 이벤트 미러를 실제 이름(`bourbon.topics_updated`)으로 고치고, 새 이벤트 셋을 선언하고, CLI 발행 명령을 만든다.
2. 합성 모집단 생성기 구현, 10만 유저 생성.
3. A안·B안 구현 → 비교 → 최종 선택(그때 `decisions.md`에 기록).
