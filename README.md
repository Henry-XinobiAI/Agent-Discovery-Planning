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
| `agent_discovery_recommendation_directions.md` | **discovery & recommendation 설계 근거 (canonical)** | 위 메모리 구조 위에서 발견·추천: 두 모드(pull·push), need 6유형, 토픽⊥입장 표현, 쟁점 축, need별 목적함수, 피드백, **팀 입력 계약(§9)** | stance descriptor (edge) |
| **`impl/` (README + `01`–`11`)** | **구현 계약·단계 spec (현재 source of truth)** | 데이터 계약·provider 경계·normalize/linker·retrieval·gate/ranking·serving·composition·LLM·eval·metrics/gates·Phase 8–9 로드맵. 실제 shipped 상태를 반영 | typed struct / phase |
| `agent_discovery_recommendation_implementation.md` | **구현 접근·근거 (research/rationale)** | build vs reuse 원칙, 단계별 컴포넌트 후보(Discovery/Recommendation), 선결 의존성·리스크. 확정 스택 아님 | — |

> 현재 active 문서는 위 넷이다. **설계 근거는 directions, 구현 계약·빌드 순서·단계 spec은 `impl/`(README + `01`–`11`)이 현재 source of truth, 구현 접근·근거는 implementation**으로 본다. 겹치는 설계 섹션은 directions가 우선이고, 겹치는 구현 계약은 `impl/`이 우선한다. 구현 형태(wiring) 요약은 §5. 초기 로드맵·build plan·walkthrough·런타임 등 히스토리 문서는 모두 `archive/`(아래)에 둔다.

---

## 2. 보관 문서 — `archive/`

### 2a. 계보(lineage) — 초기 설계 문서

초기 discovery 설계 문서들. **현재 베이스에서 마이그레이션·재매핑 대상이 아니라 개념 출처(lineage)**로만 남긴다. `agent_discovery_recommendation_directions.md`가 그 용어(`DiscoverablePerspective` 등)를 계보로 인용하되, 메모리 모델은 anchor 그래프(`Agent_Memory_Vision.md`)로 갈아탔다.

| 문서 | 당시 다루던 것 |
|---|---|
| `archive/personalized_agent_memory_and_perspective_network.md` | 초기 메인 — Memory⊥Persona, 메모리 3계층, SKL, Agent Perspective Card |
| `archive/agent_persona_extraction_and_representation.md` | persona 추출(extraction)·발현(representation) |
| `archive/agent_discovery_service_contract.md` | discovery 독립 서비스 계약 — `DiscoverablePerspective` |
| `archive/agent_matching_candidates_for_mvp.md` | MVP 추천 랭킹·인덱스 — `AgentTopicPerspective` |
| `archive/agent_matching_candidates.md` | 위 MVP 문서의 부모(초기 매칭 후보 정리) |
| `archive/agent_event_driven_architecture.md` (+ `_core.md`) | 런타임(질문 생성·타이밍·액션·오케스트레이션) 초기 설계 |

### 2b. 빌드 문서 (superseded)

Alpha 구현이 진행되며 실측·계약 기준이 `impl/`로 이동해 대체된 빌드 문서들. **히스토리 기록**으로만 남긴다(상단에 archived masthead).

| 문서 | 당시 역할 | 현재 대체 |
|---|---|---|
| `archive/Agent_Discovery_Recommendation_Roadmap.md` | 초기 제품 빌드 페이징·로드맵·검토 항목 | `impl/11-phase-8-9-roadmap.md` (+ `impl/README.md`) |
| `archive/agent_discovery_recommendation_build_plan.md` | Phase 1–7 실행 계획(레포 레이아웃·모듈·순서) | `impl/` + 코드 레포 `tasks/todo.md` |
| `archive/agent_discovery_recommendation_walkthrough.md` | 초기 동작 설명(요청→응답 시나리오) | `impl/README.md` + `impl/01`–`11` |

---

## 3. 읽는 순서

1. **`Agent_Memory_Vision.md`** — 메모리 전제(4계층·anchor). 먼저 읽는다.
2. **`agent_discovery_recommendation_directions.md`** — discovery & recommendation 설계 근거. 자립적이며, 상단에 "읽는 법" 안내가 있다. memory·persona·moderation 팀에 거는 입력 계약은 **§9**.
3. **`impl/README.md` → `impl/01`–`11`** — 현재 구현 계약·단계 spec(shipped 상태 반영). 무엇이 실제로 지어졌는지·다음 단계는 여기.
4. **`agent_discovery_recommendation_implementation.md`** — 구현 접근·근거(가져올 것 vs 직접 구현, 단계별 컴포넌트 후보)가 궁금하면.
5. 초기 로드맵·build plan·walkthrough·런타임·이벤트 구조·계보가 궁금하면 → `archive/`

---

## 4. 유지되는 제품 불변식 (프레이밍과 무관)

설계 framing이 SKL → anchor 그래프로 바뀌어도 그대로 유지되는 제품 수준 규칙(상세는 `Agent_Memory_Vision.md` / directions 문서):

- **소유·접근** — 모든 기억·지식은 사용자 소유이고, 접근은 **항상 그 사용자의 agent를 거쳐서만** 가능.
- **공개는 description 수준** — 개별 기억 원문이 아니라, 발견·전문성 판별이 가능한 **간략 description/관점**만 공개.
- **인덱스는 projection** — 검색 인덱스는 source of truth가 아니라 재빌드 가능한 투영.
- **freshness는 decay 가중치, hard cutoff 아님** — evergreen 관점을 죽이지 않음.
- **추천은 agent-매개 소비** — 사람-대-사람 직접 연결이 아니라, publish된 관점을 agent가 대신 내어주는 소비 모델(현 스코프). 직접 연결(invite)은 미래·런타임 소관.

---

## 5. 구현 형태 (how it's wired)

> 설계 근거는 directions 문서에, 구현 계약·빌드 페이징은 `impl/`(특히 `impl/11-phase-8-9-roadmap.md`)에 있고, 여기엔 "어떤 형태로 wiring 되나"만 간략히 둔다. 구체 스택은 미정(TBD).

discovery는 호출 가능한 **백엔드 서비스(API)**로 구현한다 — 버전된 공유 인덱스(anchor 파티션·stance space·contested axes), cross-agent 집계, lifecycle 이벤트 기반 갱신이 필요해 호출마다 재구축할 수 없기 때문이다. 두 모드는 이 엔진을 부르는 *경로*가 다르다.

- **엔진** — query API. 요청 = typed DTO(`mode`·`topic`·`need_type`·`user_stance_ref`·`silence_threshold` 등, directions §7.3), 응답 = ranked candidates(`agent_id` 중심; `routing_target`은 계약에서 제거 — dispatch는 bourbon-api 런타임 해석). 침묵 판정도 서버가 한다.
- **모드 A (pull)** — 유저 agent가 호출하는 **thin skill/tool 클라이언트**. API를 감싸기만 하고 로직을 재구현하지 않는다.
- **모드 B (push)** — **moderation/runtime이 게이팅하는 이벤트 훅.** agent가 자유 호출하는 skill로 만들지 않는다 — 그러면 "약한 추천으로 끼어들지 않는다"는 침묵 규율(directions §7.2)이 깨진다.

구체 스택(프로토콜·DB·skill 패키징이 MCP인지 등)은 agent 런타임에 따라 정해지며 현재 TBD.
