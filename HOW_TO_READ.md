# 읽는 순서

2026-09-08에 새로 시작했다. 이전 문서는 전부 `archive/2026-09-08_pre-redesign/`에 있고 그 안의 결정은 유효하지 않다.

| 순서 | 문서 | 왜 |
|---|---|---|
| 1 | `agent_discovery_redesign.md` | 제품 모델, 세 타입, visibility/friend 필터, 두 구현안, 비교 프로토콜. 나머지 문서의 뿌리 |
| 2 | `decisions.md` | 오너가 정한 것(R01–R16)과 정해지지 않은 것(O1–O16). 본문이 이 표와 다르면 표가 맞다 |
| 3 | `agent_discovery_contract.md` | 두 구현안이 똑같이 지키는 것: route, 스키마, 인터페이스, 불변식 8개, 저장 모델, 결정 로그 |
| 4 | `agent_discovery_events.md` | 있는 이벤트를 어떻게 소비하고, 없는 것을 우리가 먼저 어떻게 정의·시험하는지. 발행 지점 검증 |
| 5 | `synthetic_population_spec.md` | 비교의 정답 데이터를 만드는 생성기. §8은 서비스가 돌기 시작한 뒤 이벤트에서 파라미터를 자동으로 갈아 끼우는 절차 |
| 6 | `library_verification.md` | §5-1 후보와 B안을 같은 합성 데이터로 실측한 결과. O8·O11의 근거. 재현은 `spikes/` |
| 참고 | `archive/2026-09-08_pre-redesign/README.md` | 아카이브 안에서 사실·실측으로 남는 것 |

새 문서는 이전 결정 번호(D, C, S, K …)를 인용하지 않는다. 필요한 제약은 본문에 글로 풀어 쓴다.
