# 개인화 에이전트 & 관점 네트워크 — 문서 인덱스

이 디렉토리는 "개인화 에이전트와 그 관점으로 구성되는 네트워크" 제품의 설계 문서 모음이다.

핵심 한 줄:

> 개인이 자기 agent와 대화하며 **지식·관점(persona: topic·claim)**을 쌓는다 → 그중 **공개 가능한 것**이 검색 가능해진다 → 다른 유저가 정답 문서가 아니라 **그 topic을 잘 아는 agent를 발견하고 대화하며 소비**한다.

> **프레이밍 메모 (4차, 2026-08-21):** ⑴ 초기 SKL(Topic Space + Perspective Index) → ⑵ `Agent_Memory_Vision.md`의 4계층 지식그래프 + **Wikidata anchor**(memory-api 소스) → ⑶ **persona extractor 체인**(우리가 topic/claim을 소유하고 AOSS에 색인) → ⑷ **`bourbon-topic-api`로 축 이전**(2026-08-21 확정) — 토픽 저장·검색·랭킹의 주체가 이미 구현된 별도 서비스이고, 우리는 소비자 + 얇은 보정층이 된다. 앞 두 프레이밍의 문서는 `archive/`에 있고, ⑷의 근거·결정 기록은 `topic_api_analysis.md`, 설계 정본은 `recommendation_pipeline_design.md`다. ⑶의 문서(`persona_topic_search_design.md`)는 2026-08-24 `archive/`(§2e)로 이동했다. **⑵ 기반의 shipped 시스템은 전환 완료 전까지 계속 가동**되며 그 구현 계약은 `impl/`이 소유한다.

---

## 1. 현재 기준 문서 (active)

| 문서 | 레이어 | 다루는 것 | 핵심 단위 |
|---|---|---|---|
| **`topic_api_analysis.md`** | **분석 + 방향 결정 기록 (rev 8, 2026-08-25 — topic-api HEAD `9ee67f3`, 상류 이동 감사법은 부록 B-4)** | `bourbon-topic-api` 전수 분석(검색 메커니즘·카탈로그 실측·성능/비용·프라이버시 모델) + **축 이전 결정** + rev 14 폐기/승계 목록 + 열린 질문. **재설계의 입력이며 설계 문서가 아니다** | 사실/결정/열린 질문 |
| **`recommendation_pipeline_design.md`** | **설계 정본 rev 5.9 (2026-08-27, 외부 리뷰 4회 반영 + 응답 wire 4값 확장)** | topic-api 소비 기반 추천 파이프라인 S1–S6: 단계별 동작·topic-api endpoint·산출물·실패 3분기. `persona_topic_search_design.md`(rev 14)를 대체(2026-08-24 archive) — 열린 결정은 §9 | 파이프라인 단계 산출물 |
| **`serving_surface_design.md`** | **설계 rev 3.3 (2026-08-24, §7 열린 결정 전부 해소)** | 노출 표면: internal-only(`/api/internal/svc/agent-discovery/` 단독) + edge-auth 관례 채택 + topic-api 레퍼런스 이디엄 차용. **신규 repo = `bourbon-agent-discovery-api`** (project-template-python scaffold, 기존 repo는 전환 후 archive). x-user-id 금지·신원=body·label 유지·surface boundary 테스트. **표면 정비는 코드 repo에 반영 완료**(`4176b0a`·`05ec707`·`d861b5f`) — §7 열린 결정 전부 해소 — dispatch 등록 PR도 준비(bourbon-api `0eb55b6`)·순서 제약 없음 | 표면 계약 / template 델타 |
| **`impl/` (README + `01`–`11`)** | **현행 shipped 시스템의 구현 계약 (전환 전까지 유효)** | memory-api 기반의 실제 가동 중 시스템: 데이터 계약·provider 경계·grounding·gate/ranking·serving·eval. 전환 시 삭제 패스의 기준선이기도 하다 | typed struct / phase |

> **논의 기록 (결정 아님)** — `facets_ownership_split_discussion.md` (rev 1, 2026-08-26):
> topic-api에서 `score`/`score_detail`을 떼어 facet producer가 소유하는 DynamoDB로 옮기고
> agent-discovery가 읽기 전용으로 join하는 구조의 **사실·판단·열린 항목**. 기준 문서가 아니고
> 어떤 계약도 이것으로 바뀌지 않았다 — 착수 자격은 측정값 셋이 준다(§7-1). 결정이 생기면 정본 §S3·§S4·§9로 올라간다.

> **논의 기록 (결정 아님)** — `service_boundary_discussion.md` (rev 1, 2026-08-27):
> topic-api ↔ agent-discovery 경계 — "자연어+맥락 → 토픽"이 어느 쪽 역할인가에 대한 2026-08-26
> 슬랙 문제 제기와, 세 repo에서 `file:line`으로 확인한 **사실·판단·열린 항목(SB1–SB5)**.
> 규칙 한 줄 = 데이터 소유자는 사실과 검색 프리미티브, 호출하는 쪽은 해석·정책·실패 계약.
> 위 facets 문서와 **같은 경계의 다른 절반**이다(값의 소유 ↔ 순위 정책의 소유, §4-2). 기준 문서가
> 아니고 요청도 발신하지 않았다 — closed beta 이후 항목이다.

> **방향 근거는 `topic_api_analysis.md`, 설계 정본은 `recommendation_pipeline_design.md`, 가동 중인
> 것의 계약은 `impl/`.** `persona_topic_search_design.md`(3차 프레이밍 기록)는 2026-08-24에
> `archive/`(§2e)로 이동했다. 이전 프레이밍의
> 설계 근거 문서들(directions·implementation·Agent_Memory_Vision·technology_selection_evidence)은
> 2026-08-20에 `archive/`(§2d)로 이동했다 — 현행 시스템이 *왜 그렇게 지어졌는지*가 궁금할 때만
> 연다. 구현 형태(wiring) 요약은 §5(현행 시스템 기준).

---

## 2. 보관 문서 — `archive/`

### 2a. 계보(lineage) — 초기 설계 문서

초기 discovery 설계 문서들. **마이그레이션·재매핑 대상이 아니라 개념 출처(lineage)**로만 남긴다. `archive/agent_discovery_recommendation_directions.md`가 그 용어(`DiscoverablePerspective` 등)를 계보로 인용한다.

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
| `archive/Agent_Discovery_Recommendation_Roadmap.md` | 초기 제품 빌드 페이징·로드맵·검토 항목 | `impl/11-forward-roadmap.md` (+ `impl/README.md`) |
| `archive/agent_discovery_recommendation_build_plan.md` | Phase 1–7 실행 계획(레포 레이아웃·모듈·순서) | `impl/` + 코드 레포 `tasks/todo.md` |
| `archive/agent_discovery_recommendation_walkthrough.md` | 초기 동작 설명(요청→응답 시나리오) | `impl/README.md` + `impl/01`–`11` |

### 2c. 외부 협의·결정 이력

타 팀(memory-api·bourbon-api)과의 협의 문서 중 **더 이상 열린 요청이 아닌 것**. 결정의 *내용*은 `impl/`과
아래 active 레지스터가 갖고, 여기 있는 문서는 **무엇을 왜 요청했고 어떻게 착지했는지**의 경위를 보존한다
(각각 상단에 masthead).

| 문서 | 당시 다루던 것 | 성격 / 현재 위치 |
|---|---|---|
| `archive/memory_api_statement_attribution_request.md` | statement `owner_asserted: bool` 필드 + 검색 필터 (K-A1 rev 3) | **채택되지 않은 초안** — 필드는 미생성. assertion-source `confidence` tier를 `attribution` enum으로 투영하는 형태로 착지 |
| `archive/memory_api_statement_attribution_followup.md` | 위 협의의 종결 기록 (K-A1 rev 5) | **채택된 종결 결정** — 의미론 + server-side 필터 둘 다 착지(`#129`/`3e4e7c1`, `f246f93`). 계약 요약은 `impl/00`, 잔여 테스트 공백은 R2, 연기된 리스크는 R7 |
| `archive/memory_api_agent_recommendation_requirements.md` | memory-api가 제공해야 할 최소 계약 (2026-07-14 이전) | **이전 협의 기록** — 현재 계약 아님. 현재 상태는 `impl/findings-real-anchor-grounding-ties.md` / `impl/11-forward-roadmap.md` |
| `archive/persona_api_discovery_requests.md` | persona 팀에 걸 데이터·API 요청서 (rev 15, 2026-08-13) | **폐기된 트랙 (2026-08-19)** — persona-api를 소스로 삼는 전환 자체가 폐기됐다. 요청·열린 질문 전부 무효. rev 16과 실사 문서 `persona_source_review.md`는 미머지 폐기(태그 `discarded/persona-api-ownership-split`) |
| `archive/persona_api_endpoint_summary.md` | 위 요청서의 endpoint 요약 — persona 팀에 **실제 공유됨** | **폐기된 트랙 (2026-08-19)** — 공유한 문서라 폐기 사실을 persona 팀에 별도 통지해야 한다 |
| `archive/bourbon_api_discovery_open_requests.md` | bourbon-api 요청 레지스터 (B1–B2, 미발신 초안) | **종결 (2026-08-24)** — B1(owner→agent uuid5 producer-side pin)은 발신하지 않기로 결정: 파생은 bourbon-api 지정 고정 계약이며 명문화는 `recommendation_pipeline_design.md` S6-0. B2(신뢰된 requester identity)는 호출자가 bourbon-agent로 바뀐 새 wire 계약(`requester_user_id`)으로 대체 |

### 2d. 방향 재변경으로 보관 (2026-08-20) — 2차 프레이밍의 기준 문서들

2026-08-19 아키텍처 재변경(persona extractor 체인 확정)으로 **전제가 폐기된** 2차 프레이밍
(4계층 + Wikidata anchor)의 기준 문서들. 각 상단 masthead 참조. 현행 shipped 시스템의 계약은
계속 `impl/`이 소유하므로, 이 문서들은 "그 시스템이 왜 그렇게 설계됐는지"의 기록이다.

| 문서 | 당시 역할 | 현재 대체 |
|---|---|---|
| `archive/Agent_Memory_Vision.md` | 메모리 기반 확정 전제 (4계층 + Wikidata anchor) | `archive/persona_topic_search_design.md` §0 체인 |
| `archive/agent_discovery_recommendation_directions.md` | discovery & recommendation 설계 근거 (need 6유형·stance·팀 입력 계약 §9) | `archive/persona_topic_search_design.md` (1차 = 단일 추천 유형; need 체계는 그쪽 Q8) |
| `archive/agent_discovery_recommendation_implementation.md` | 구현 접근·build vs reuse (anchor grounding이 병목이라는 전제) | `archive/persona_topic_search_design.md` §1-⑧·⑪ |
| `archive/technology_selection_evidence.md` | entity linking·KG 스택 후보 근거 로그 | 대상 소멸 — 검색 스택은 memory-api `memory/search/` 재사용 |
| `archive/memory_api_discovery_open_requests.md` | memory-api 요청 레지스터 (R1–R7, 미발신 초안) | **폐기** — memory-api가 소스에서 빠짐. 항목별 후계 매핑은 masthead |

### 2e. 방향 재변경으로 보관 (2026-08-24) — 3차 프레이밍의 설계 문서

| 문서 | 당시 역할 | 현재 대체 |
|---|---|---|
| `archive/persona_topic_search_design.md` | 3차 프레이밍 설계 (rev 14) — 우리가 topic/claim을 소유하고 AOSS에 색인 + 2단계 읽기 + 열린 질문 Q1–Q15 | 설계는 `recommendation_pipeline_design.md`, rev 14 결정·규율의 항목별 폐기/승계 처분은 `topic_api_analysis.md` §9 |

> **루트에 활성 요청 레지스터는 더 이상 없다** — bourbon-api 레지스터(B1–B2)는 2026-08-24 종결·보관(§2c).
> 새 체인의 cross-team 열린 결정은 `recommendation_pipeline_design.md` §9(열린 결정)와
> `topic_api_analysis.md` §11(열린 질문)이 갖는다.

---

## 3. 읽는 순서

1. **`recommendation_pipeline_design.md`** — 확정된 방향(설계 정본). §0 요약 → S1–S6(§3) → §9 열린 결정 순. 서빙 표면은 `serving_surface_design.md`.
2. **`topic_api_analysis.md`** — 그 설계의 입력. topic-api의 사실·실측·결정·열린 질문(§11).
3. **`impl/README.md` → `impl/01`–`11`** — 지금 가동 중인 시스템의 계약(전환 전까지 유효, 전환 시 삭제 패스 기준선).
4. 위 두 문서의 열린 결정(설계 §9)·열린 질문(분석 §11) — 타 팀에 걸려 있는 항목.
5. 현행 시스템이 *왜* 그렇게 지어졌는지 → `archive/`의 프레이밍 문서들(§2d·§2e). 그보다 앞 계보는 §2a.

---

## 4. 유지되는 제품 불변식 (프레이밍과 무관)

framing이 SKL → anchor 그래프 → persona extractor 체인 → topic-api 소비로 바뀌어도 그대로 유지되는 제품 수준 규칙(4차 프레이밍에서의 구체화는 `recommendation_pipeline_design.md`):

- **소유·접근** — 모든 기억·지식은 사용자 소유이고, 접근은 **항상 그 사용자의 agent를 거쳐서만** 가능.
- **공개는 description 수준** — 개별 기억 원문이 아니라, 발견·전문성 판별이 가능한 **간략 description/관점**만 공개.
- **인덱스는 projection** — 검색 인덱스는 source of truth가 아니라 재빌드 가능한 투영.
- **freshness는 decay 가중치, hard cutoff 아님** — evergreen 관점을 죽이지 않음.
- **추천은 agent-매개 소비** — 사람-대-사람 직접 연결이 아니라, publish된 관점을 agent가 대신 내어주는 소비 모델(현 스코프). 직접 연결(invite)은 미래·런타임 소관.

---

## 5. 구현 형태 (how it's wired) — 현행 shipped 시스템 기준

> **이 절은 전환 전까지 가동되는 현행 시스템의 wiring이다** (구현 계약은 `impl/`, 설계 근거 기록은 `archive/agent_discovery_recommendation_directions.md`). 전환 후 형태는 `recommendation_pipeline_design.md` §0. API-first·thin client·moderation-gated push라는 골격은 전환 후에도 유지된다.

discovery는 호출 가능한 **백엔드 서비스(API)**로 구현한다 — 버전된 공유 인덱스(anchor 파티션·stance space·contested axes), cross-agent 집계, lifecycle 이벤트 기반 갱신이 필요해 호출마다 재구축할 수 없기 때문이다. 두 모드는 이 엔진을 부르는 *경로*가 다르다.

- **엔진** — query API. 요청 = typed DTO(`mode`·`topic`·`need_type`·`user_stance_ref`·`silence_threshold` 등, directions §7.3), 응답 = ranked candidates(`agent_id` 중심; `routing_target`은 계약에서 제거 — dispatch는 bourbon-api 런타임 해석). 침묵 판정도 서버가 한다.
- **모드 A (pull)** — 유저 agent가 호출하는 **thin skill/tool 클라이언트**. API를 감싸기만 하고 로직을 재구현하지 않는다.
- **모드 B (push)** — **moderation/runtime이 게이팅하는 이벤트 훅.** agent가 자유 호출하는 skill로 만들지 않는다 — 그러면 "약한 추천으로 끼어들지 않는다"는 침묵 규율(directions §7.2)이 깨진다.

구체 스택(프로토콜·DB·skill 패키징이 MCP인지 등)은 agent 런타임에 따라 정해지며 현재 TBD.
