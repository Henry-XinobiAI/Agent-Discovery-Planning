# 개인화 에이전트 & 관점 네트워크 — 문서 인덱스

이 디렉토리는 "개인화 에이전트와 그 관점으로 구성되는 네트워크" 제품의 설계 문서 모음이다.

핵심 한 줄:

> 개인이 자기 agent와 대화하며 **지식·관점(memory·persona)**을 쌓는다 → 그 일부가 **공개(publish)**되어 **공개 지식 그래프(Wikidata anchor)**에 정렬된다 → 다른 유저가 정답 문서가 아니라 **관점을 가진 agent를 발견하고 대화하며 소비**한다.

> **프레이밍 메모:** 초기 설계는 SKL(Topic Space + Perspective Index) 프레이밍이었고(→ `archive/`), 현재 메모리 기반은 `Agent_Memory_Vision.md`의 **4계층 지식그래프 + Wikidata anchor**로 갈아탔다. discovery & recommendation 설계는 그 위에서 `agent_discovery_recommendation_directions.md`로 새로 정리한다.

---

## 1. 현재 기준 문서 (active)

| 문서 | 레이어 | 다루는 것 | 핵심 단위 |
|---|---|---|---|
| `Agent_Memory_Vision.md` | **메모리 기반 (확정 전제)** | 개인 지식그래프 4계층(L0 Record → L1 Capsule → L2 Personal Knowledge → L3 Public Knowledge), Wikidata anchor 정렬, expert routing | anchor↔personal-node link |
| `agent_discovery_recommendation_directions.md` | **discovery & recommendation 기준 베이스** | 위 메모리 구조 위에서 발견·추천: 두 모드(pull·push), need 6유형, 토픽⊥입장 표현, 쟁점 축, need별 목적함수, 피드백, **memory·persona 팀 입력 계약(§8)** | stance descriptor (edge) |

> 현재 active 설계 문서는 위 둘뿐이다. 런타임·초기 discovery 등 나머지 설계 문서는 모두 `archive/`(아래)에 둔다.

---

## 2. 보관(계보) 문서 — `archive/`

초기 discovery 설계 문서들. **현재 베이스에서 마이그레이션·재매핑 대상이 아니라 개념 출처(lineage)**로만 남긴다. `agent_discovery_recommendation_directions.md`가 그 용어(`DiscoverablePerspective` 등)를 계보로 인용하되, 메모리 모델은 anchor 그래프(`Agent_Memory_Vision.md`)로 갈아탔다.

| 문서 | 당시 다루던 것 |
|---|---|
| `archive/personalized_agent_memory_and_perspective_network.md` | 초기 메인 — Memory⊥Persona, 메모리 3계층, SKL, Agent Perspective Card |
| `archive/agent_persona_extraction_and_representation.md` | persona 추출(extraction)·발현(representation) |
| `archive/agent_discovery_service_contract.md` | discovery 독립 서비스 계약 — `DiscoverablePerspective` |
| `archive/agent_matching_candidates_for_mvp.md` | MVP 추천 랭킹·인덱스 — `AgentTopicPerspective` |
| `archive/agent_matching_candidates.md` | 위 MVP 문서의 부모(초기 매칭 후보 정리) |
| `archive/agent_event_driven_architecture.md` (+ `_core.md`) | 런타임(질문 생성·타이밍·액션·오케스트레이션) 초기 설계 |

---

## 3. 읽는 순서

1. **`Agent_Memory_Vision.md`** — 메모리 전제(4계층·anchor). 먼저 읽는다.
2. **`agent_discovery_recommendation_directions.md`** — discovery & recommendation 설계. 자립적이며, 상단에 "읽는 법" 안내가 있다. memory·persona 팀에 거는 입력 계약은 **§8**.
3. 런타임·이벤트 구조나 초기 배경·계보가 궁금하면 → `archive/`

---

## 4. 유지되는 제품 불변식 (프레이밍과 무관)

설계 framing이 SKL → anchor 그래프로 바뀌어도 그대로 유지되는 제품 수준 규칙(상세는 `Agent_Memory_Vision.md` / directions 문서):

- **소유·접근** — 모든 기억·지식은 사용자 소유이고, 접근은 **항상 그 사용자의 agent를 거쳐서만** 가능.
- **공개는 description 수준** — 개별 기억 원문이 아니라, 발견·전문성 판별이 가능한 **간략 description/관점**만 공개.
- **인덱스는 projection** — 검색 인덱스는 source of truth가 아니라 재빌드 가능한 투영.
- **freshness는 decay 가중치, hard cutoff 아님** — evergreen 관점을 죽이지 않음.
- **추천은 agent-매개 소비** — 사람-대-사람 직접 연결이 아니라, publish된 관점을 agent가 대신 내어주는 소비 모델(현 스코프). 직접 연결(invite)은 미래·런타임 소관.
