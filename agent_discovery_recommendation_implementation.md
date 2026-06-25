# Agent Discovery & Recommendation — Implementation Approach (working)

> 이 문서는 구현 접근과 **재사용 후보**를 정리한 working document다. 확정 기술 스택이 아니다. 구체 기술 선택(특정 entity linker·store·ANN·LTR 확정)은 deep research 후 별도 `technology_selection` 문서에서 다룬다. 상세 아키텍처를 본격적으로 설계할 때는 별도 architecture 문서로 분리한다.
>
> **Alpha의 구현 병목은 RecSys 모델이 아니라 topic→anchor grounding과 agent-topic edge retrieval이다.**

## 0. 문서 위치

| 문서 | 역할 |
|---|---|
| `agent_discovery_recommendation_directions.md` | 설계 기준 / 개념 모델 / source of truth |
| `Agent_Discovery_Recommendation_Roadmap.md` | Alpha / Open Beta / Post-Open-Beta 단계 공유 |
| **이 문서** | 구현 접근 / 서비스 구성 / memory-api 경계 / build vs reuse / 후보 기술 |

구현 서비스명은 **`bourbon-agent-recommendation-api`**다. 설계·범위는 위 두 문서를 참조하고 여기서 재진술하지 않는다. 단계 정의(Alpha/Open Beta/Post)와 내부 단계(Discovery/Recommendation)는 directions §0·§5, Roadmap §1을 따른다.

## 1. 핵심 결론

- Alpha에 RecSys framework는 도입하지 않는다.
- 지금 가져올 것은 **Entity Linking / Wikidata / KG / structured retrieval** (IR 쪽)이다.
- RecSys는 **2-stage 패턴**과 일부 **부품**만 재사용한다.
- against / orthogonal / contested-axis / push silence / contribution은 **직접 구현**한다.
- `bourbon-memory-api`는 **anchor substrate는 지금 real로 쓸 수 있고, agent-topic edge substrate는 아직 없다.** 그래서 Alpha는 "real anchor API + mock edge/persona/eligibility provider"로 시작한다(§2).

## 2. Discovery 서비스 구성과 memory-api 경계

이 절이 이 문서의 척추다. "무엇을 짓고, `bourbon-memory-api`와 정확히 어디서 만나며, 지금 무엇이 real이고 무엇이 mock인가"를 정면에 둔다.

### 2.1 서비스 개요

Discovery & Recommendation은 `bourbon-agent-recommendation-api`라는 독립 백엔드 서비스로 구현한다. 요청을 받아 후보 agent를 찾아 need에 맞게 정렬해 돌려주는 query API다. 배포 형태(API 서비스 + pull skill 클라이언트 + push moderation 훅)는 README §5를 따르고 여기서 재진술하지 않는다. 이 절은 그 서비스의 **내부 모듈 구성**과 **`bourbon-memory-api`와의 경계**만 다룬다.

### 2.2 컴포넌트 뷰

서비스 내부는 directions의 Discovery 단계 → Recommendation 단계 분리(§5)를 그대로 모듈로 가진다. **아래 6개 모듈은 모두 `bourbon-agent-recommendation-api`가 소유한다.** "외부 의존" 열은 그 모듈이 호출하는 substrate/provider이지, 그 모듈을 외부가 대신 구현한다는 뜻이 아니다.

| # | 모듈 | 단계 | 하는 일 | 외부 의존 (substrate / provider) |
|---|---|---|---|---|
| 1 | **Query-side linker** | Discovery | 요청 topic text → Wikidata QID | `bourbon-memory-api` anchor search/get/connections (real) · §4 entity linking |
| 2 | **Candidate retrieval** | Discovery | QID → agent-topic edge 후보 (+ sparse 시 이웃 anchor 확장) | agent-topic edge: Alpha mock, later Memory real / 이웃 확장은 anchor connections (real) |
| 3 | **Gate** | Discovery | maturity / eligibility (+ 외부공개 시 safety) 필터 | eligibility: Alpha mock, later owner/privacy/safety |
| 4 | **Need ranking** | Recommendation | depth / for / against / coverage need별 ordering(scalar score 아님 — build_plan §4.2 ordering contract) | persona prior: Alpha mock, later Persona real (ranking 로직은 build) |
| 5 | **Serving** | Recommendation | 후보·이유·`routing_target` payload, push silence 판정 | — (build) |
| 6 | **Decision-log** | (공통) | 입력·생존·탈락 이유 기록 | — (build) |

모듈 1~3이 Discovery 단계로 directions의 **need-complete candidate pool**을 만들고, 4·5가 Recommendation 단계로 **need-conditioned 선택/서빙**을 한다 (directions §5 단계 경계와 일치). 6은 공통이다.

> `bourbon-memory-api`가 Query-side linker나 Candidate retrieval 모듈을 대신 구현하는 것은 아니다. Discovery가 두 모듈을 소유하고, memory-api는 anchor substrate와 (later) agent-topic edge substrate를 provider 경계로 제공할 뿐이다.

### 2.3 요청 처리 경로 (real vs mock)

Alpha 기준 한 요청의 **논리 경로**다. **[real]** = `bourbon-memory-api` 실제 호출, **[mock]** = 로컬/eval mock provider(배포 앱에서는 미사용 — 아래 참조), **[build]** = Discovery 직접 구현.

```
request(topic_text, need_type, user_stance_ref?)
  │
  ├─① query-side linker  topic_text → QID            KnowledgeEntityProvider.search_candidates()/suggest() [real]
  │                       (sparse면 이웃 anchor 확장)   KnowledgeEntityProvider.expand_connections() [real]
  ├─② candidate retrieval QID → agent-topic edges     MemoryEdgeProvider.get_edges()           [mock]
  ├─③ gate               maturity·eligibility 필터     EligibilityProvider.check()              [mock]
  ├─④ need ranking       depth/for/against need별 ordering PersonaProvider.get_prior() [mock] + ordering/LLM [build]
  ├─⑤ serving            payload + routing_target, silence 판정                                 [build]
  └─⑥ decision-log       생존/탈락 이유 기록                                                      [build]
```

핵심은 **①은 지금 실제 substrate가 있고, ②~③은 mock provider로, ④는 mock persona prior + build ranking으로 선대체한다**는 것이다(④의 ranking 로직 자체는 우리가 build하고, 그 안의 persona prior만 mock이다). 그래서 Discovery는 Memory/Persona 구현을 기다리지 않고 전체 경로를 끝까지 돌릴 수 있다. mock을 real로 바꾸는 것이 곧 통합이다(§7).

> **`[mock]`은 배포 런타임 provider가 아니라 로컬/eval substrate다.** 위 mock 경로가 성립하는 곳은 **로컬 CLI·eval·test**다. 배포 아티팩트(dev/prod)는 mock을 와이어링하지 않고, edge/persona/eligibility의 real-slot에 `Unavailable*` provider를 두어 통합 전까지 `upstream_unavailable`(503)을 반환한다(§7.6). 즉 Alpha의 "mock"은 개발/평가 substrate이지 배포 런타임 의존이 아니다 — 경계는 §2.5 표가 single source.

### 2.4 Provider 인터페이스 (sketch)

경계는 4개 provider 인터페이스로 고정한다. 아래는 **언어중립 sketch이며 확정 시그니처가 아니다.** mock과 real은 같은 인터페이스를 구현한다(§7.1).

`KnowledgeEntityProvider` — **real** (`bourbon-memory-api` `/knowledge/entities`). memory-api가 `8ffcec8`에서 public read model을 `Anchor*`→`Entity*`로 개명했다. **Discovery 문서의 도메인 용어 "anchor"(topic을 고정하는 QID 기준점)는 유지하되, 코드 타입·provider명은 memory-api 계약을 미러해 `Entity*`로 맞춘다.** list 라우트는 `Page[T]={items,limit,truncated}` envelope을 반환하므로 **provider가 `.items`로 unwrap**하고 도메인엔 `list[Entity*]`만 넘긴다:

```
search_candidates(text, limit?)      -> [EntitySummary{ qid, label, importance, pageview, … }]       # GET /knowledge/entities      (Page→.items)
suggest(text, limit?)                -> [EntitySuggestion{ qid, source, label, description }]         # GET /knowledge/entities/suggest (Page→.items; prefix/alias)
get(qid)                             -> Entity{ qid, label, labels, aliases, linked_qids, … }        # GET /knowledge/entities/{qid}    (bare)
expand_connections(qid, limit)       -> EntityConnections{ center, broader, narrower, links_*, limit, truncated }  # GET /knowledge/entities/{qid}/connections (bare)
search_articles(q, qid?, lang?)      -> [ArticleHit]                                                 # GET /knowledge/articles (Page→.items; 보조)
```

`KnowledgeEntityProvider`는 full entity linker가 아니라 **memory-api entity substrate adapter**다 — entity 검색(`search_candidates`)·prefix 보조(`suggest`)·단건 조회·connections 호출을 감쌀 뿐 disambiguation을 결정하지 않는다. Query-side linker(모듈 1)가 candidate generation을 `search_candidates ∪ suggest`(qid merge)로 모으고, 필요 시 별도 entity linker(§4.1)를 조합해 최종 QID를 정한다(구현 계획에서는 두 타입을 linker 내부 `EntityCandidate`로 정규화 — build_plan §3.1). **`lang`은 `search_articles`에만 있다** — entity 검색/suggest 계약엔 `lang` 파라미터가 없고 핵심 파라미터는 `q`다(계약 drift 방지).

`expand_connections(qid, limit)`의 `limit`은 memory-api 기준으로 associative links(`links_out`/`links_in`)만 제한한다(`EntityConnections.limit`/`truncated`가 이 cap을 echo). taxonomy 방향의 `broader`/`narrower`는 memory-api 내부 cap을 따른다.

`MemoryEdgeProvider` — Alpha: **eval mock** / 배포 **unavailable→503**:

```
get_edges(anchor_id) -> [AgentTopicEdge{ agent_id, anchor_id,
                          maturity, evidence_strength, freshness,
                          observed_stance, stance_summary, evidence_refs,
                          routing_target, source_owner }]
```

`PersonaProvider` — Alpha: **eval mock** / 배포 **unavailable→503**:

```
get_prior(agent_id) -> PersonaPrior{ prior_stance?, stable_traits, expertise_claims }
```

`EligibilityProvider` — Alpha: **eval mock** / 배포 **unavailable→503**:

```
check(agent_id, context?) -> Eligibility{ discoverable, … }   # owner / privacy / (safety)
```

`EntitySummary`·`Entity`·`EntitySuggestion`·`EntityConnections`·`ArticleHit`만 real 응답(§2.6의 현재 API 표면)에 묶인다. 나머지 타입은 contract로 합의하고, **local/eval에서는 mock fixture로 채우되 배포 앱은 real 통합 전까지 `Unavailable*` provider로 503을 반환한다**(§2.5 표·§7.2). 필드별 `source_owner` 규칙은 §7.2.

### 2.5 경계 요약표

**provider별로 `Alpha local/eval`(개발·평가 substrate)과 `배포 앱`(dev/prod 런타임)을 분리한다** — "mock"은 전자에만 산다.

| Provider / 호출 | 뒷단 | Alpha local/eval | 배포 앱(deployed) |
|---|---|---|---|
| `KnowledgeEntityProvider` (topic→QID, suggest, entity 단건, connections, articles) | `bourbon-memory-api` `/knowledge/entities*` | real / pinned `anchors.json` | **real** |
| `MemoryEdgeProvider` (agent-topic edge) | Memory (미통합) | eval mock | **unavailable → 503** (real 통합 전) |
| `PersonaProvider` (persona prior) | Persona (미통합) | eval mock | **unavailable → 503** |
| `EligibilityProvider` (discoverability) | owner/privacy (미통합) | eval mock | **unavailable → 503** |
| Future `UserPreferenceProvider` (favorite/user preference) | `bourbon-api` (미통합) | not implemented | not implemented (Post-Open-Beta) |
| evidence 원문 조회 | conversation search | — | 후일 (Alpha 미사용) |

이 표가 경계의 single source다 — "real인 줄 알았는데 mock"·"Alpha 배포가 mock으로 돈다"는 혼선을 막는다. mock은 `eval/providers/`에 있고 **배포 serving 경로는 mock-free**다(deployed 앱은 `eval/`을 import하지 않음); edge/persona/eligibility의 real이 없는 동안 배포 앱은 `Unavailable*` provider로 503을 반환한다(§7.6). `evidence_refs`의 원문 조회는 conversation search로 연결될 수 있으나 Alpha 후보 생성 경로엔 들어가지 않는다. **`UserPreferenceProvider`(favorite)는 personalization 신호로 expertise·gate와 무관하며 Alpha 후보/랭킹에 쓰지 않는다(reserved, 코드 미구현)** — 출처는 memory-api/persona가 아닌 `bourbon-api`, 실소비는 Post-Open-Beta(directions §9.7, ranking 거버넌스 §5.3).

### 2.6 현재 `bourbon-memory-api` 현황 (스냅샷)

> **이 절은 `bourbon-memory-api`의 특정 시점 스냅샷(2026-06-24 재확인, memory-api `8ffcec8`(`/knowledge`·`/personal` unify + anchor/node→**entity** rename) / HEAD `9784b7e` 기준)이며 live-tracking 문서가 아니다.** 직전 스냅샷(`d8135bb`)의 `Anchor*` / `/knowledge/anchors` 표면은 `Entity*` / `/knowledge/entities`로 갱신됐다. Discovery는 memory-api 진행 상황을 계속 따라가며 맞추는 방식이 아니라, §2.4 provider contract와 §7 mock-first 전략을 기준으로 구현한다. memory/persona가 통합 가능한 시점에 contract를 재검증하고 mock provider를 real로 교체한다(§7.6). 그때까지 **능동 조율이 필요한 건 두 checkpoint뿐**이고 나머지 현황 변화는 추적하지 않는다:
> 1. **QID vocabulary / anchor 의미 계약** — query-side ↔ producer-side QID가 같은 disambiguation 기준인지, alias/redirect/local anchor 처리(아래 "QID 계약" + §7.4). mock으로 숨길 수 없어 **Alpha 중 한 번은 Memory와 합의**해야 한다.
> 2. **edge contract shape** — 아래 "아직 없는 것" 표의 필드(`maturity`/`evidence_strength`/`freshness`/`observed_stance`/`evidence_refs`/`routing_target`/`discoverability` 등)를 실제로 줄 수 있는지와 **필드별 source owner**.

필요시 `../bourbon-memory-api`에서 직접 확인할 수 있고, 아래는 통합 상황 이해를 돕는 요약이다. 핵심 결론은 **anchor substrate는 real로 바로 쓸 수 있고, agent-topic edge substrate는 아직 없다**는 것이다.

**현재 구현된 것** — 구현 중심은 두 가지다.

| 영역 | 현재 제공 | Discovery에서의 의미 |
|---|---|---|
| **Conversation memory (L0)** | 메시지 저장, room timeline, keyword/time-range search, context expansion, cross-room recall | 후일 `evidence_refs`의 원천이 될 수 있다. 지금 agent-topic edge를 만들지는 않는다 |
| **Public knowledge backbone (L3)** | Wikidata 기반 anchor index, anchor search, 단건 조회, typed connections, Wikipedia article BM25 search | query-side anchor grounding / KG 확장 / QID vocabulary 기준으로 **바로 활용 가능** |

현재 public knowledge(entity) API 표면 (`/knowledge` prefix, list는 `Page[T]` envelope):

| API | 용도 | Discovery 적용 |
|---|---|---|
| `GET /knowledge/entities?q=…` → `Page[EntitySummary]` | label/description full-text 검색, `importance` 정렬 | topic → QID 후보 생성 |
| `GET /knowledge/entities/suggest?q=…` → `Page[EntitySuggestion]` | label/aliases prefix autocomplete(typeahead) | linker candidate gen 보조(prefix/alias recall) |
| `GET /knowledge/entities/{qid}` → `Entity` (bare) | QID 단건 조회 | 선택 anchor 검증, label/description 표시 |
| `GET /knowledge/entities/{qid}/connections` → `EntityConnections` (bare) | `linked_qids` + hierarchy 기반 typed ego connections(`broader`/`narrower`/`links_out`/`links_in`) | sparse anchor fallback, 관련 anchor 확장 |
| `GET /knowledge/articles?q=…` → `Page[ArticleHit]` | Wikipedia article chunk BM25 검색 | topic 설명/axis hint 보조. agent 추천 근거로 직접 쓰지 않음 |

`Entity`는 Wikidata QID를 `qid`로 보존한다. **Discovery의 `anchor_id`는 memory-api의 `qid`와 동일하게 둔다.**

list 라우트(`entities`/`suggest`/`articles`)는 `Page[T]={items,limit,truncated}` transport envelope을 반환하고, detail(`Entity`)·connections(`EntityConnections`)는 bare 모델을 직접 반환한다(응답 표면이 다름). **`Page[T]` unwrap은 provider 책임**(`.items`만 도메인에 전달).

- **`GET /knowledge/entities?q=…` → `Page[EntitySummary]`** (`.items` 언랩); 각 `EntitySummary`: `qid`, `source`, `label`, `description`, `importance`, `pageview`, `pagerank`, `sitelink_count`, `categories`, `instance_of`, `abstract`.
- **`GET /knowledge/entities/suggest?q=…` → `Page[EntitySuggestion]`** (`.items` 언랩); 각 `EntitySuggestion`: `qid`, `source`, `label`, `description` (display/ranking 신호 생략 — typeahead용 경량).
- **`GET /knowledge/entities/{qid}` → `Entity`**: `qid`, `source`, `label`, `labels`, `description`, `aliases`, `instance_of`, `subclass_of`, `occupations`, `sitelink_count`, `sitelinks`, `pageview`, `pagerank`, `importance`, `categories`, `linked_qids`, `abstract`, `fetched_at`. (`occupations`는 P106·people-only로 `EntitySummary`엔 없고 detail `Entity`에만 있다; memory-api `positioning.py`가 `instance_of`와 함께 broader positioning seed로 쓴다 — Alpha 미사용이나 향후 axis/coverage 신호 후보.)
- **`GET /knowledge/entities/{qid}/connections` → `EntityConnections`**: `center`, `broader`, `narrower`, `links_out`, `links_in`, `limit`, `truncated`; 각 node는 `EntitySummary`.
- **`GET /knowledge/articles?q=…` → `Page[ArticleHit]`** (`.items` 언랩); 각 `ArticleHit`: `chunk_id`, `qid`, `title`, `lang`, `section_path`, `ordinal`, `text`.

`linked_qids`는 `EntitySummary`에는 없고 detail `Entity`에만 있다. 따라서 direct out-link 목록이 필요하면 `GET /knowledge/entities/{qid}`를 호출하고, typed neighbor pool이 필요하면 `GET /knowledge/entities/{qid}/connections`를 호출한다.

따라서 Alpha에서 별도 API 확장 없이도 `pageview` / `pagerank` / `sitelink_count` / `categories` / `abstract` / `linked_qids`를 읽을 수 있다. 다만 이 값들은 **anchor grounding과 sparse expansion 보조 신호**이지 agent expertise나 recommendation quality 신호가 아니다.

`importance`는 pageview / PageRank / sitelink_count를 섞은(0.5·pageview + 0.3·pagerank + 0.2·sitelink_count, log 압축·정규화) public-anchor notability 신호다. Discovery에서는 **entity 후보 disambiguation prior**나 sparse fallback 정렬에만 쓴다. 이 값을 agent 추천 품질·expertise·contribution·reputation으로 해석하면 안 된다 — anchor(개념)에 붙은 값이지 agent에 붙은 값이 아니다.

**raw signal은 이미 노출되지만 Alpha에서는 제한적으로 쓴다.** Alpha 목적은 query-side grounding + 후보 retrieval/ranking skeleton 검증이므로, `importance`와 raw ranking/display signal은 QID 후보 prior, disambiguation 보조, sparse fallback 정렬에만 사용한다. `abstract`와 `categories`는 설명/axis hint에 유용할 수 있으나, axis/orthogonal serving은 Open Beta 범위다. 이 신호를 agent 추천 점수·expertise·contribution·reputation으로 직접 연결하지 않는다.

**아직 없는 것** — Discovery가 기대하는 Memory/Persona contract 중 아래는 현재 API에 없다.

| Discovery가 필요한 것 | 현재 상태 | Alpha 대응 |
|---|---|---|
| `anchor_id ↔ agent_id` 단위 **agent-topic edge** | 없음 | `MockMemoryEdgeProvider` fixture로 선대체 |
| `topic_knowledge_maturity` / `evidence_strength` / `freshness` | 없음 | mock edge에 명시. 실제 산식은 Memory와 contract 합의 |
| `observed_stance` / `stance_summary` / opinion·experience 분리 | 없음 | mock edge + Discovery-side coarse extraction으로 시작 |
| `routing_target` | 없음 | routing source owner를 contract에 태깅하고 mock |
| `discoverability` / privacy eligibility | 없음 | privacy source owner를 contract에 태깅하고 mock |
| Persona prior | 이 repo에 Persona 구현 없음 | `MockPersonaProvider`로 선대체 |

즉 `bourbon-memory-api`의 Vision/Roadmap은 L0 → L1 → L2 → L3 흐름과 anchor routing 방향을 이미 갖고 있고, `8ffcec8` 시점엔 **Personal Knowledge(L2) `/personal` API가 추가됐다**(personal entity graph + public QID grounding). 다만 Discovery가 필요한 **agent-topic edge**는 여전히 직접 제공되지 않는다.

> **Future real edge source 후보(메모).** memory-api `GET /personal/groundings/{qid}?owner_ids=&sort=confidence&limit=` → `Page[GroundingMatch]`(`={owner_id: UUID, entity: PersonalEntitySummary}`)는 특정 public QID에 grounded된 owner personal entity를 cross-owner로 찾는다 — "anchor에 연결된 personal knowledge로 expert routing"의 초기 substrate에 가깝다. 그러나 `agent_id` 매핑·`maturity`·`evidence_strength`·`freshness`·`observed_stance`·`stance_confidence`·`routing_target`·`discoverable`가 전부 빠져 있어 **`AgentTopicEdge`를 바로 대체하지 못한다.** translation layer 또는 전용 discovery endpoint가 여전히 필요하다(Open Beta `MemoryEdgeProvider` real 통합 후보로만 메모). **특히 `owner_id`/`personal_entity_id`를 Discovery의 `agent_id`와 어떻게 연결할지가 real `MemoryEdgeProvider` 통합의 첫 번째 handshake**이며, 통합 때 가장 먼저 막힐 선결 지점이다. (`owner_id`는 존재하지만 Discovery가 호출 가능한 agent routing endpoint가 아니므로 `routing_target`으로 보지 않는다 — 위 "빠진 필드"의 `routing_target`은 이 의미다.) Alpha는 계속 `MockMemoryEdgeProvider` fixture로 선대체한다.

**privacy는 완전 백지가 아니다.** L0 conversation에는 이미 `PiiSensitivity`(PUBLIC/PERSONAL/SENSITIVE/SECRET) 기반 masking/clearance 모델이 있다. 다만 이건 message 마스킹 쪽이고, Discovery가 필요한 **agent-topic edge discoverability / candidate eligibility와는 직접 동일하지 않다.** 후자는 아직 없다. 나중에 eligibility contract(directions §11)는 새로 발명하지 말고 이 기존 PII sensitivity와 **정합**되게 둔다.

**QID 계약 — 이미 맞는 부분과 아직 합의할 부분.** schema가 `anchor_id: string`으로 맞아도 값의 의미가 다르면 후보가 만나지 않으므로, QID는 스키마가 아니라 의미 계약이다(§7.4).

이미 맞는 부분:

- Memory vision과 public anchor 구현 모두 Wikidata QID를 anchor 기준으로 본다.
- `Entity.qid`는 Wikidata QID를 그대로 보존한다.
- anchor connections는 `instance_of`·`subclass_of`·`linked_qids`를 `broader`/`narrower`/`links_out`/`links_in`으로 분류해 KG 확장을 지원한다.

아직 합의할 부분:

- Discovery query-side linker가 고른 QID와 Memory producer-side anchoring이 붙인 QID가 **같은 disambiguation 기준**인지.
- alias / redirect / 다국어 label에서 어느 QID를 canonical로 볼지.
- **local anchor 계약** — `Entity` 모델엔 이미 `source: EntitySource = WIKIDATA | LOCAL`이 있으므로 "local anchor를 만들지 말지"가 아니라 **기존 `LOCAL` enum 위에서 규칙을 합의**하는 문제다: ① local anchor ID namespace, ② Wikidata QID와의 충돌 방지, ③ lifecycle, ④ 나중에 Wikidata로 매핑될 때 merge/redirect 방식, ⑤ Discovery fixture에 local anchor를 포함할지. 이건 Alpha QID vocabulary 합의와 한 묶음이다.
- L2 personal node가 여러 public anchor에 걸칠 때 primary/secondary anchor를 어떻게 표현할지.

→ 따라서 public anchor API가 이미 있다는 건 좋은 출발점이지만, **QID 의미 계약은 여전히 Alpha 선결**이다.

## 3. Build vs Reuse 원칙

- **2-stage 패턴은 재사용한다.** candidate generation → ranking은 업계 표준이고, 우리의 Discovery 단계 → Recommendation 단계 분리가 사실상 그 패턴이다.
- **framework의 default objective는 쓰지 않는다.** engagement / popularity / affinity 최대화는 이 시스템이 directions §0·§5.4에서 거부한 모델이다. 프레임워크를 통째로 얹으면 그 bias가 다시 들어온다.
- **feedback은 reward가 아니다.** Open Beta feedback은 운영 진단 신호다(directions §6, Roadmap §8). ranking 정답 라벨이나 contribution/reputation score로 바로 환산하지 않는다.

> **RecSys framework는 "모델 동물원"이 아니라 "부품 창고"로만 본다.** RecBole/TorchRec/Merlin을 도입하면 추천이 해결된다는 오해를 막는다. 재사용 대상은 retrieval/indexing 메커니즘·diversity 알고리즘·off-policy 평가 같은 *부품*이지, opinionated한 CF/engagement 파이프라인이 아니다.

## 4. Component 후보 (미확정)

특정 기술 확정이 아니라 **후보·도입 시점·주의점**을 정리한다. 확정은 §9 → 별도 `technology_selection`. 판단 컬럼: **Alpha / Open Beta / Post / when-needed / build**.

이 절의 후보는 **성능 보장 목록이 아니다.** 논문·repo 기준으로 "대표적이거나 실무 검토 가치가 있는 후보"를 적은 것이며, 우리 서비스 품질은 §8의 gold set / evaluation harness로 직접 검증해야 한다. 몇 년 지난 기술도 여전히 도입 후보일 수 있지만, 그 경우 **최신 SOTA**가 아니라 **stable baseline / production-practical primitive**로 본다. 반대로 최신 연구라도 운영 복잡도·언어 커버리지·Wikidata/QID directness가 맞지 않으면 Alpha 후보가 아니다. archived·non-commercial·broken·EOL 같은 강한 판정의 출처·버전·확인일은 본문에 싣지 않고 `technology_selection_evidence.md`(근거 로그)에 남긴다 — 재확인 후 갱신 대상이다.

### 4.1 Discovery 단계 (후보 공간 구성)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **Entity linking** (2-tier) | **Candidate-gen**: memory-api anchor search + Wikidata label/alias + dense retrieval / **Disambiguation**: LLM rerank / **참조 모델**: ReFinED·BELA·mGENRE / OpenTapioca·ReLiK·BLINK·GENRE | query-side: 한국어 topic text → Wikidata QID | **Alpha 핵심.** 단일 EL 모델 선택이 아니라 **candidate generator + LLM rerank 2-tier**로 간다 (memory-api anchor search가 candidate-gen의 한 축) | **한국어 topic→QID turnkey 오픈모델은 없다 — 그래서 2-tier다.** 위 오픈모델들(ReFinED·OpenTapioca·ReLiK·BELA·BLINK·GENRE·mGENRE)은 영어 전용·archived·non-commercial·QID 비직결 중 하나 이상에 걸려, **production default가 아니라 architecture/reference/baseline으로만** 본다(항목별 라이선스·maintenance·출처·확인일은 evidence log). LLM은 retriever 후보 위 rerank/disambiguation만 — **단독 QID 생성은 hallucination 위험이 커 gold set 검증 전까지 쓰지 않는다**(콜드 QID 생성 ❌). producer-side(Memory) anchoring과 **같은 QID vocabulary** 정렬 필수(§6.2). 검증 항목: 한국어 candidate recall·QID directness·라이선스·calibration |
| **Wikidata / KG access** | memory-api anchor API(우선) / WDQS(SPARQL)·dumps / 로컬 self-host: **QLever**·Oxigraph(subset) | QID, parent/neighbor, sparse anchor fallback | **Alpha** | "최신 ML" 문제가 아니라 운영 substrate 선택이다. Alpha는 memory-api public anchor API를 우선 사용. self-host가 필요하면 **QLever**(full Wikidata 단일 장비 수용 + Wikimedia가 택한 WDQS 차기 백엔드)가 1순위, Oxigraph는 full Wikidata 못 올려(로드 >1주) subset/sparse fallback 한정. **공개 WDQS는 2025.5 graph split(scholarly 분리)·rate limit으로 production hot path 부적합**. qwikidata는 2019 dump-parser(미유지보수)라 엔진 아님. **Blazegraph는 EOL(2020~ 미유지보수, WDQS가 떠나는 중인 legacy)이라 신규 후보 아님** |
| **Edge store + metadata filter** | Postgres / graph DB(Neo4j·Nebula) / Vespa | `anchor_id` 기반 edge 조회 + maturity·freshness·discoverability·safety 필터 | **Alpha**: Postgres/structured query 우선. graph DB·Vespa는 when-needed | Alpha 검색은 대부분 structured query라 vector 없이 충분할 수 있음. Postgres는 최신성보다 단순성·트랜잭션·필터링이 장점. graph DB는 multi-hop traversal이 실제 병목일 때. Vespa는 retrieve+filter+rank를 한 엔진으로 통합하고 싶을 때 강한 후보지만, 첫 선택지는 아님(운영 복잡도) — 선택 기준은 §9 |
| **KG embedding** | PyKEEN / GraphStorm(대규모) / PyTorch-BigGraph(archived·reference) | anchor 연관도/이웃 확장, link prediction | when-needed / Post | 최신 서비스 품질을 보장하는 컴포넌트가 아니다. PyKEEN=실험·재현성 적합(단일 GPU 한정). 대규모는 **GraphStorm**(DGL-KE는 최신 DGL에서 broken·AWS가 GraphStorm으로 redirect). PyTorch-BigGraph=archived(2024.3)지만 **Wikidata 78M 임베딩을 바로 받을 수 있어** frozen reference로 유용. AmpliGraph는 stale + 스케일 부적합(YAGO3-10급)이라 제외. Alpha의 sparse fallback은 KG traversal + rules로 충분할 가능성이 높고, KG embedding은 semantic 이웃 확장이 실제 필요해질 때만 |
| **ANN / vector** | pgvector / Qdrant / Milvus / Faiss / Vespa | stance/persona embedding, topic-conditioned embedding 검색, hybrid vector+metadata filter | when-needed | embedding 도입 전에는 불필요(5종 모두 2026 활발). pgvector는 Postgres 안에서 시작(0.8+ iterative scan으로 filtered ANN 수천만 벡터까지; 한계는 maturity가 아니라 단일 노드 스케일). **Qdrant=가벼운 first-reach 독립 DB(filter-aware HNSW), Milvus=무거운 scale-out(동급 아님)**. Faiss는 라이브러리(메타데이터 필터 직접 구현), Vespa는 retrieve+filter+rank 통합 필요 시. filtered ANN의 recall/latency trade-off는 §8 harness로 검증 |

### 4.2 Recommendation 단계 (need-conditioned 선택/서빙)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **rule scoring + LLM/text 비교** | (직접) | depth / for / against / coverage coarse scoring | **Alpha 핵심** | symbolic descriptor 중심 |
| **diversity / coverage** | MMR, DPP, xQuAD·PM-2, calibrated recommendation | coverage Need, 결과 다양화 | **Open Beta** | 최신 기술이라기보다 검증된 classical primitive다. against/orthogonal을 **대신하지 못함** — 다양화 프리미티브일 뿐 |
| **evaluation** | 표준 metric(Recall@K·Precision@K·NDCG·MRR; TorchMetrics·ranx 등 유지보수 구현) + Evidently(드리프트) + off-policy(OBP) | feedback 진단, threshold 튜닝, shadow/신정책 평가 | **Open Beta** (진단용) | reward로 직결 ❌. **off-policy(OPE)는 logged propensity·action set·reward proxy 정의가 없으면 불가/제한적이며 잘못된 확신을 줄 수 있다** — decision-log에 이 필드들을 남기는 게 선행(§7.5). **OBP 원본은 2022 이후 dormant → 유지보수 fork(`sb-obp`) 또는 reference-only**, 구형 `pytrec_eval` 회피. Alpha 평가 전략(gold set·지표·failure bucket)은 §8 |
| **Learning-to-rank** | LightGBM LambdaRank, XGBoost(rank:ndcg), CatBoost ranking | need별 reranker | **Post** | 최신 딥러닝 랭커는 아니지만 tabular LTR에서 여전히 강한 production-stable 후보. XGBoost(2026.6)·CatBoost(2026.2)는 fresh, **LightGBM은 태그 stale(2025.2)·repo가 `lightgbm-org`로 이전(2026.3)**이니 핀/URL 갱신. feedback label·evaluation policy 안정 후에만 검토. global engagement label 단일 학습 ❌ |
| **RecSys framework** | RecBole(benchmark), TorchRec(실험·scale-out), keras-rs(TF/JAX stack 시) | 알고리즘 비교·실험·scale-out | **Post** / benchmark·실험용 | 제품 핵심 로직 대체 ❌, default objective ❌. RecBole=research benchmark, TorchRec=활발(Meta, scale-out). **TFRS는 Keras 2 legacy로 동결 → TF/JAX가 필요하면 `keras-rs`(아직 research candidate, production 후보로 단정 ❌). Merlin은 2024 이후 정체라 GPU preprocessing 한정**. Alpha/Open Beta objective를 대신하지 않는다 |

### 4.3 직접 구현 (기성 컴포넌트 없음, 프리미티브만 재사용)

| 항목 | 정의 | 빌릴 프리미티브 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **against / orthogonal** | against = same axis·opposite stance / orthogonal = different established axis | LLM classification, stance detection, ABSA/PyABSA, InstructABSA(reference) | for/against=**Alpha**, orthogonal=**Open Beta**(조건부) | 기성 product component 없음. ABSA/stance 모델은 domain transfer가 약해 primitive로만 본다(InstructABSA=논문 reference-only, PyABSA=single-maintainer bus-factor 주의). Alpha는 LLM + symbolic stance descriptor로 시작하고, 모델 도입은 gold set에서 이득이 확인될 때 |
| **contested-axis 도출** | 쟁점 축 establishment·divergence mass 게이팅 | BERTopic·aspect extraction / ideal-point(PyMC/Stan) / LLM clustering | **Open Beta**: LLM coarse + established/inherited_established gate / **Post**: mature factorization(ideal-point·요인분해) | BERTopic/PyMC/Stan은 여전히 유효한 primitive지만 자동으로 "좋은 축"을 보장하지 않는다. divergence mass·evidence gate 없이 바로 serving하면 false controversy 위험 |
| **push silence / when-to-recommend** | 기준 미달 시 침묵 | CRS(conversational rec) 문헌, abstain-action bandit | **Open Beta** | 기성 product component 없음. policy + threshold + shadow log로 직접 구현 |
| **contribution / reputation** | validated memory impact 누적, popularity guard | fairness-in-ranking·bandit 문헌 | **Post** | feedback을 reward로 바로 닫지 않는다. validated memory impact 준비 후 검토 |

## 5. 단계별 도입 순서

| 단계 | 가져올 것 | 미룰 것 |
|---|---|---|
| **Alpha** | Entity linking, Wikidata/KG access, structured edge store + filter, rule/LLM scoring, decision-log 설계 | RecSys framework, vector/ANN(임베딩 전), LTR |
| **Open Beta** | diversity/coverage 알고리즘 일부, feedback diagnostic metric, off-policy evaluation 검토. vector/ANN은 embedding 도입 시 | LTR/model-based ranking |
| **Post-Open-Beta** | LightGBM LambdaRank류 reranker, RecBole/TorchRec 실험, Faiss/Qdrant scale-out, KG embedding(GraphStorm/PyKEEN), contribution/reputation 학습(validated memory impact 준비 후) | — |

## 6. 책임 분할과 선결 의존성

### 6.1 누가 무엇을 만드나

축은 *팀별 작업 목록*이 아니라 **소유/책임(누가 만드나)**이다. Discovery 팀이 정당하게 소유하는 건 "직접 만드는 것"과 "외부에서 받는 것의 형태(contract)"이지, 다른 팀의 백로그가 아니다.

| 구분 | 내용 | 이 문서에서의 취급 |
|---|---|---|
| **A. Discovery 단독** | edge-derived feature projection(Memory가 준 edge를 추천용 feature로 가공·소비; edge 생성 자체는 Memory), need별 랭킹, for/against, push silence, serving payload, decision-log, **query-side QID linking**(topic→QID) | 여기서 상세 (§2·§4·§6.2) |
| **B. 외부에서 받음** (Memory / Persona / owner·privacy) | observed/prior stance, maturity raw signal, agent-topic edge, discoverability, `routing_target` | **contract로 받고 mock으로 선대체**(§7). 무엇을 받는지의 source of truth는 **directions §9** — 여기서 재진술하지 않는다 |
| **C. 공동 handshake** (어느 쪽도 혼자 못 함) | **QID vocabulary 정렬**(query-side ↔ producer-side), contract 공동 서명·버전, mock→real 통합 테스트 | §6.2 리스크 + §7 전략. **주관을 명시해 "서로 상대가 하겠지" 공백을 없앤다** |

A/B는 mock provider 경계(§7.1)로 분리된다 — B는 mock 뒤에 두고 Discovery는 A에 집중한다. **C는 mock으로 숨길 수 없다**(§7.4): QID 정렬은 contract test가 모양만 보고 값(의미)은 못 잡으므로, Memory와 별도 합의 트랙으로 Alpha 선결한다.

### 6.2 선결 의존성과 리스크

- **topic→anchor grounding 품질** — Alpha 성공이 추천 모델이 아니라 여기에 달려 있다.
- **query-side / producer-side anchor vocabulary 정렬 (Memory와 선결)** — Discovery 질의 linker(topic→QID)와 Memory의 producer-side anchoring(agent L2 node→QID)이 **같은 KG·같은 disambiguation·같은 QID 표준**으로 수렴해야 한다. 안 그러면 같은 주제가 서로 다른 QID로 풀려 후보가 안 만나진다.
- **Memory의 agent-topic edge readiness** — 후보 공간 자체가 Memory 산출물이다(directions §9.1, `anchor-personal node link` P0). Memory가 QID-anchored edge를 publish하지 않으면, query-side linker가 아무리 좋아도 후보가 0이다. entity-linker 비교보다 이 readiness 합의가 먼저다.
- **objective default 함정** — framework·라이브러리의 기본 목적함수(engagement/affinity)를 무심코 쓰지 않는다.
- **vector infra premature adoption** — Alpha 검색은 structured query 중심. ANN/vector는 when-needed.
- **feedback ≠ reward** — off-policy 평가(OBP 등)와 decision-log 필드 설계가 선행. shadow mode와 짝.

## 7. Mock-first / contract-first 전략

Memory·Persona 구현을 기다리면 Discovery/Recommendation Alpha가 막힌다. 그래서 **Memory/Persona와 공동 합의한 contract를 mock provider로 구현해 개발을 먼저 시작**한다. 핵심은 mock이 "버려질 개발용 더미"가 아니라 **통합 경계 그 자체 = 통합 리허설**이 되도록 만드는 것이다.

### 7.1 Provider 인터페이스 (real과 동일)

- Discovery는 Memory/Persona DB를 직접 읽지 않는다. §2.4의 provider 인터페이스 뒤에 둔다.
- Alpha 개발 중에는 `MockMemoryEdgeProvider` / `MockPersonaProvider` / `MockEligibilityProvider`를 붙이고, 실제 팀 API가 나오면 **구현만 교체**한다.
- **mock provider는 real provider와 동일한 인터페이스를 구현한다.** 이걸 명시하지 않으면 mock이 개발용 샘플로 전락하고 통합이 rewrite가 된다.

### 7.2 입력 contract — 공동 서명 (Discovery 단독 동결 ❌)

contract를 Discovery가 임의로 정하면 그건 우리 추측일 뿐이고, 통합 때 실제 출력과 어긋나면 mock 위에 쌓은 게 전부 rewrite다. 최소한 다음은 Memory/Persona와 **합의**해야 한다:

- 필드별 **source owner** (Memory / Persona / owner / privacy / safety) — 모든 필드에 `source_owner` 태그를 붙인다. `routing_target`·`discoverability`·safety verdict는 Memory 본체가 아니라 owner/privacy/safety 소유일 수 있어, 책임 경계가 흐려지지 않게 한다. (directions §9.3 observed=Memory / prior=Persona, §11 eligibility와 일관)
- **nullable · confidence · freshness · versioning** 규칙
- `anchor_id`가 가리키는 **KG/QID vocabulary**의 의미 (→ §7.4)
- producer-side anchoring과 query-side linking이 **같은 disambiguation 기준**을 쓰는가

contract에는 **버전**을 박고, 그 버전을 fixture·contract test와 묶는다. 통합 때 "어느 계약 버전 기준인가"가 흐려지면 mock→real 교체가 다시 추측이 된다.

### 7.3 Fixture dataset — 가드에서 역산한 regression set

happy-path 샘플이 아니라, directions·Roadmap에 흩어진 주요 리스크·가드에서 역산한다.

원칙은 간단하다: **가드 하나당 그걸 깨는 fixture 하나**를 둔다. 예: directions §10 가드 표, directions §1.2 maturity gate, directions/Roadmap §4 freshness/contested axis, directions/Roadmap §11 eligibility.

그러면 fixture set이 곧 설계 불변식의 regression 테스트가 된다. mock 데이터가 너무 예쁘면 Discovery/Recommendation이 실제보다 잘 되는 것처럼 보이므로, 험한 케이스를 기본 포함한다.

| fixture | 방어하는 리스크 / 가드 |
|---|---|
| dense / cold topic | sparse anchor fallback |
| ambiguous topic (QID 분기) | QID 정렬 실패 |
| same-axis disagreement | for/against 성립 |
| weak evidence agent | maturity gate |
| high persona / low memory | hollow agent (prior로 maturity 안 채움, §10) |
| stale but valuable | freshness = decay, hard cutoff 아님 |
| discoverability off | privacy/eligibility gate (§11) |
| established axis 유무 | orthogonal · false controversy (established/inherited_established, §10) |

### 7.4 QID는 스키마가 아니라 의미 계약 (Alpha 선결, mock과 별개)

`anchor_id: "Q123"` 같은 **필드 모양**은 contract test로 검증되지만, "이 QID가 같은 개념을 가리키는가"는 **mock으로 숨길 수 없다** (모양은 맞는데 값이 다른 QID). 따라서 QID **vocabulary · fallback · ambiguity · alias/redirect** 처리 기준은 contract test와 별개 트랙으로, **Alpha 선결 합의**로 둔다. §6.2의 anchor vocabulary 정렬 리스크, §2.6의 QID 계약 합의 항목과 동일한 문제다.

### 7.5 Decision-log from day one

실제 feedback이 없어도, 추천 한 번마다 **어떤 입력으로 어떤 후보가 왜 살아남고 탈락했는지** 로그를 남긴다. 이게 Open Beta 평가·threshold 튜닝·off-policy 평가(§4.2)의 선행 데이터가 된다.

### 7.6 통합 = 교체

실제 팀 API가 나오면 mock provider를 real provider로 바꾸고, **같은 contract test를 실제 데이터에 돌린다.** mock 단계에서 인터페이스·계약 버전·fixture 가드를 지켜왔다면, 통합은 rewrite가 아니라 교체 + integration test다.

## 8. 평가 전략 (Alpha — mock 위에서의 품질 평가)

mock-first로 개발을 시작하면 곧바로 "그럼 추천 품질은 어떻게 평가하나"가 문제가 된다. 핵심은 **합성 데이터로는 "실제 사용자에게 좋은가"를 증명할 수 없다**는 것이다. 우리가 agent·edge를 직접 만들면 그 데이터로 매기는 평가는 순환 논리가 된다(정답을 우리가 심고 그걸 다시 맞히는지 보는 것). 따라서 Alpha 평가의 목표를 처음부터 다르게 잡는다: **설계한 Discovery/Recommendation behavior가 mock contract 위에서 재현 가능하고 need별로 regression 가능한가**를 검증하는 것이지, 최종 품질을 증명하는 것이 아니다.

### 8.1 무엇을 평가할 수 있고, 무엇은 못 하는가

평가를 3층으로 나눠 각 층이 *정직하게* 증명하는 범위를 고정한다.

| 층 | 데이터 | 정답(label) 출처 | 증명 범위 | Alpha 가용 |
|---|---|---|---|---|
| **A. 합성 + rule-derived label** | 우리 생성 | 우리 생성(스코어 규칙) | 파이프라인 정합성·가드 동작·regression — **품질 아님** | ✅ 전부 |
| **B1. 합성 + human gold core** | 우리 생성(현실적 구조) | **산식과 독립된 사람**이 더블로 판정(소량) | Alpha에서 **제한적 품질 주장**이 가능한 유일한 층(설정 A vs B 비교) | ✅ 소량 |
| **B2. 합성 + LLM-assisted silver** | 우리 생성 | 다른 LLM judge(다른 프롬프트) | 대량 regression/탐색 커버리지 — **품질 주장 ❌(silver)** | ✅ 대량 |
| **C. 실데이터 + 행동** | 실제 사용자 | accept/click + dogfooding/human review | 실사용에 가까운 품질 신호 (단독 "정답" 아님) | ❌ (real 연결 + dogfooding + Open Beta) |

Alpha는 **A 전부 + B1 소량(제한적 품질은 오직 여기서) + B2 대량(regression/탐색, 품질 주장 아님)**까지만 주장한다. C는 못 한다 — 이걸 박아두어야 합성 지표를 과신하지 않는다. C도 "진짜 품질의 정답"은 아니다: accept/click은 합성보다 나은 behavioral signal이지만 그 자체가 품질이 아니라 **운영 proxy**이고(특히 against/orthogonal은 클릭·짧은 대화가 품질을 왜곡할 수 있다, §3 feedback≠reward), dogfooding/human review와 **함께 해석**한다.

### 8.2 핵심 원칙 — gold label ≠ scoring rule

이 평가에서 가장 쉽게 무너지는 지점이다. **fixture(§7.3)는 시스템 *입력*이고, gold label은 사람이 "이 요청에는 이 agent가 좋은 추천이다/아니다"를 별도로 판단한 *정답*이다.** 둘을 같은 규칙으로 만들면(예: `maturity ≥ 0.9`면 자동 정답으로 라벨링) 평가는 "구현이 자기 공식을 잘 반복하는지"만 보게 되고, 품질 측정이 아니라 동어반복이 된다.

따라서:

- gold label은 스코어링 산식과 **독립**으로 만든다(데이터 생성과 정답 판정의 주체/프롬프트 분리 — 같은 LLM이 둘 다 만들면 construct validity 붕괴).
- **B1(human gold core)과 B2(LLM silver)를 명시적으로 분리한다.** B1은 산식과 독립된 *사람*이 더블로 판정한 소량 core로, Alpha의 제한적 품질 주장은 **오직 여기서만** 나온다. B2는 다른 LLM이 다른 프롬프트로 단 대량 silver set으로 regression/탐색 커버리지를 넓히는 용도이며 **품질 주장에 쓰지 않는다** — judge와 generator의 모델 prior가 상관돼 같은 맹점을 공유할 수 있다. 리포트에서 B2 점수는 항상 silver로 표기한다.
- 라벨은 4단계로 둔다: **`ideal` / `acceptable` / `bad` / `must_not_show`**. `must_not_show`는 단순 하위 등급이 아니라 **hard negative class**로, "절대 떠선 안 되는" 후보의 false-pass를 직접 측정한다. **Alpha에선** discoverability off, weak evidence, wrong stance, hollow agent 같은 hard negative를 담는다(safety/privacy gate는 Alpha inactive — Open Beta 이전 활성화 시 safety/privacy 위반을 별도 세분화한다).
- **B2 silver judge 운영 원칙**(human gold 대체가 아니라 보조라서 검증이 필요하다, §8.11):
  - **multi-criteria rubric으로 분해한다** — "relevant?" 하나로 묻지 말고 topicality / evidence support / need fit / stance-axis fit / must_not_show risk로 나눠 판정한다(direct grading보다 robust·해석 가능, Farzi et al.).
  - **judge 입력을 설계한다** — raw edge를 다 던지지 말고 *scenario + user stance/profile 요약 + candidate evidence*를 준다(Fabbri et al.).
  - **judge 자체를 meta-evaluate한다** — order swap·prompt variation·pairwise consistency/transitivity 점검(Feng et al.; position/verbosity/self-enhancement bias는 Zheng et al.), **주기적으로 B1 human core와 agreement 측정**. agreement가 무너지면 해당 silver 결과를 신뢰 강등한다.

### 8.3 real substrate 기반으로 실측 가능한 부분

합성 평가에도 진짜로 믿을 수 있는 부분이 있다. **anchor substrate(`bourbon-memory-api`, Wikidata/QID)는 mock이 아니라 real이다(§2).** 우리가 합성하는 건 agent→topic edge뿐이고, 그 edge가 가리키는 anchor는 실제 QID여야 한다. 따라서:

- 합성 agent를 **실제 QID에 grounding** → **topic→QID grounding(모듈 1)은 실제 anchor substrate 위에서** 평가된다. (sparse 시 이웃 anchor 확장도 real이다. 단 agent-topic edge retrieval 자체는 mock이다.)
- 그래서 **real substrate 기반 quality gate는 QID grounding accuracy다.** agent retrieval **Recall@K는 mock edge 기준 후보 생성 regression·coverage 지표**이고, ranking-with-edge 지표와 함께 B층 *proxy*로 본다(§8.1).
- 부수 효과로, 합성 데이터를 만드는 행위 자체가 QID vocabulary 정렬(§7.4) 리허설이 된다.

### 8.4 Evaluation harness 구조와 코퍼스 규모

```
mock providers(edge/persona/eligibility) + REAL anchor API
  → synthetic agents / edges  (REAL QID에 grounding)
  → scenario queries          (need별)
  → qrels / gold labels        ideal · acceptable · bad · must_not_show  (≠ scoring rule, §8.2)
  → run recommendation
  → 단계별 지표 + decision-log inspection
  → failure bucket 분석 (§8.8)
```

코퍼스 규모(Alpha 출발 기준):

- **agent 30~50개**, **anchor 20~30개**, **topic(anchor)당 다수 agent-topic edge**.
- **scenario query 전체 100~200개**(need 5종에 걸쳐 need별 최소 20~40개씩), 각 scenario의 후보 agent들에 4단계 gold label. — regression set이 성숙하면 need별로 더 키운다.
- §7.3 가드 역산 케이스와 **known-item needle**(명백히 1등이어야 할 expert를 의도적으로 심는 sanity 케이스)을 정상 경로로 포함한다.

코퍼스는 **난이도 stratum으로 층화**한다 — easy 케이스만 모으면 "정답이 너무 보이는" fixture가 돼 ranking 지표가 포화되고 아무것도 못 배운다:

- **easy**: 명백한 정답이 있는 기본 케이스(known-item needle 포함).
- **guard**: §7.3 가드 역산(discoverability off / weak evidence / wrong stance / hollow).
- **hard / confusable**: near-duplicate expert(거의 같고 stance만 다름), adjacent-axis distractor(관련 있어 보이나 need 축이 다름), partial-evidence(맞지만 maturity 부족), stale-but-valid vs fresh-but-shallow, persona는 강하나 memory 근거가 약한 hollow expert.
- **ambiguous**: 정답이 본질적으로 갈리는 케이스 — 실패가 아니라 별도 분리(특히 stance, §8.7).

지표는 stratum별로 보고한다(§8.5) — aggregate만 보면 hard층 실패가 easy층에 가려진다.

gold set은 **한 번 만들어 regression benchmark로 고정**하고 실험 간 재사용한다(TREC식 pooling: 여러 랭킹 변형의 top-k + 랜덤 샘플을 pool로 모아 사람이 판정).

### 8.5 단계별 지표

| 평가 대상 | 지표 | 비고 |
|---|---|---|
| **grounding** | QID top-1 / top-3 accuracy | **real substrate 기반 quality gate**(§8.3) |
| **retrieval** | Recall@K, 후보 누락률 | **mock edge 기준** 후보 생성 regression — 후보 공간 천장(여기서 새면 ranking 무의미) |
| **gate** | false block / false pass | `must_not_show`가 false-pass를 직격 |
| **ranking** | nDCG@K, MRR, Precision@K, MAP@K | B층 proxy(B1 품질비교 / B2 silver) |
| **stance** | same-axis / opposite-stance 판정 정확도 | for / against |
| **coverage** | unique axis / source / persona coverage, redundancy | same-axis crowding 가드 |
| **reason(설명)** | evidence_ref 없는 설명·과장 설명·stance mismatch 수 | explanation fail |
| (보조) **calibration** | confidence ↔ 판정 관련성 상관 | |

각 지표의 의미와 그것으로 얻는 판단:

- **grounding — QID top-1 / top-3 accuracy.** topic text를 정답 QID로 푼 비율(top-1 = 1순위가 정답, top-3 = 상위 3개 안에 정답). → 링커가 안정적으로 옳은 anchor를 잡는가. *top-1은 낮은데 top-3가 높으면* disambiguation rerank로 회수 가능하다는 신호, *둘 다 낮으면* vocabulary 정렬(§7.4)이나 링커 자체 문제. real substrate라 memory-api anchor 커버리지 공백도 여기서 드러난다.
- **retrieval — Recall@K, 후보 누락률.** gold가 "관련"으로 판정한 agent 중 후보 풀 상위 K에 들어온 비율(Recall@K)과 그 반대(누락률). → 후보 공간이 **천장**이다. ranking이 아무리 좋아도 여기서 빠진 agent는 절대 못 뜬다. 낮으면 edge coverage·이웃 anchor 확장·K 상향을 본다. **Alpha에선 edge가 mock이므로 이건 mock edge 기준 후보 생성 regression 지표**이고, real substrate 품질 측정은 통합 후다(§8.10).
- **gate — false block / false pass.** 보여야 할 후보(ideal/acceptable)를 자른 비율(false block = over-prune)과 `must_not_show`인데 통과시킨 비율(false pass). → 게이트 임계가 과한가/느슨한가. *false block↑* → maturity/eligibility cutoff 완화 검토, *false pass↑* → eligibility/discoverability 게이트 강화. **Alpha 게이트는 maturity/eligibility(discoverability)까지이고 safety/privacy는 inactive**(directions §11) — safety/privacy의 false pass는 그 게이트 활성화 시(Open Beta 이전) 별도로 본다.
- **ranking — nDCG@K, MRR, Precision@K, MAP@K.** nDCG = 등급(ideal>acceptable>…)을 순위 가중으로 반영한 종합 점수(좋은 걸 위로 올렸나), MRR = 첫 관련 결과의 평균 역순위(첫 좋은 추천이 얼마나 위에 오나), Precision@K = 상위 K 중 관련 비율(짧은 리스트 정확도), MAP@K = 다수 관련 항목의 순위 품질 평균. → need별 ranking 로직이 의도대로 정렬하는가. **단 mock edge 위에서는 B층 proxy**(§8.1: B1은 제한적 품질 비교용, B2는 silver regression용) — 설정 A vs B 비교용이지 절대 품질이 아니다(B1도 synthetic 위라 real-user 품질의 proxy일 뿐, 신뢰도가 높아 제한적 주장에 쓸 뿐이다).
- **stance — same-axis / opposite-stance 판정 정확도.** for(같은 축·같은 방향)·against(같은 축·반대 방향) 요청에서 후보의 축/방향 분류가 gold와 맞는 비율. → for/against가 "다른 주제"나 "같은 의견 반복"으로 새지 않는가. against가 orthogonal(다른 축)로 새는 흔한 실패를 잡는다.
- **coverage — unique axis / source / persona coverage, redundancy.** 결과 리스트가 덮는 고유 축/출처/페르소나 수와 중복도. → coverage need에서 비슷한 agent만 반복(same-axis crowding)하지 않고 의미 있는 범위를 덮는가. redundancy↑면 다양화 프리미티브(MMR 등, §4.2) 필요 신호.
- **reason — evidence_ref 없는 설명·과장 설명·stance mismatch 수.** 추천 이유가 실제 edge/evidence와 어긋나는 건수. → 설명이 사후 합리화가 아니라 실제 근거에 묶이는가. evidence_ref 없는 설명은 hallucinated reason, stance mismatch는 이유-결론 불일치.
- **calibration — confidence ↔ 판정 관련성 상관.** 시스템이 매긴 confidence가 실제 gold 관련성과 상관하는가. → confidence를 threshold·push silence 판정에 믿고 쓸 수 있는가. 상관이 낮으면 confidence 기반 침묵 판정이 위험하다.

지표는 need별(depth / experience / for / against / coverage) **그리고 난이도 stratum별(§8.4: easy / guard / hard / ambiguous)**로 분리해 본다 — 단일 평균은 need별·hard층 regression 실패를 둘 다 가린다.

### 8.6 Quality gate — provisional threshold + ratchet

"gate"라 부르려면 걸 숫자가 있어야 한다. 처음부터 완벽한 값일 필요는 없다 — **절대 품질 보장이 아니라 regression ratchet**으로 쓴다: 한 번 넘긴 기준 아래로 떨어지면 evaluation failure(CI red). 기준은 gold set이 성숙하며 상향한다.

| gate | 기준 설정 방식 | 성격 |
|---|---|---|
| grounding top-1 accuracy | 초기 측정값을 baseline으로 고정 → ratchet | real substrate quality gate(§8.3) |
| grounding top-k recall | 초기 측정값을 baseline으로 고정 → ratchet(top-1보다 높게 마련) | disambiguation으로 회수 가능한 상한 |
| **must_not_show false pass** | **= 0 (hard fail, ramp 없음)** | hard negative 노출 무관용 |
| **discoverability-off candidate exposure** | **= 0 (hard fail)** | 노출 금지 후보가 결과에 등장 금지 |
| QID ambiguous fallback rate | baseline → 상향 금지(ratchet) | 높으면 vocabulary 정렬(§7.4)·링커 문제 신호 |

숫자 게이트(grounding accuracy/recall, fallback rate)는 **확정값을 미리 박지 않고 초기 측정값을 baseline으로 고정한 뒤 ratchet**한다 — 데이터가 없는 지금 임의의 목표치를 단정하지 않는다. **= 0 게이트(must_not_show false pass / discoverability-off exposure)만 처음부터 hard fail**로 둔다(ramp 없음). 통합 후에도 같은 게이트를 real substrate에 다시 돌려 §8.10의 substrate report로 쓴다.

### 8.7 Stance gold labeling protocol

for/against는 다른 라벨보다 주관성이 높아 단순 정답 라벨로 처리하면 위험하다(annotator 불일치가 크다). 별도 protocol을 둔다:

1. **axis를 먼저 고정한다.** 무엇에 대한 찬반인지(축)를 라벨링 전에 확정 — 축이 흔들리면 방향 판정이 무의미해진다.
2. **같은 axis 위에서 stance direction만 판정한다.** for(같은 축·같은 방향)·against(같은 축·반대 방향)·orthogonal(다른 축)을 분리한다.
3. **human double-labeling.** 최소 2인이 독립 판정한다(이 stance gold는 B1 core에 속한다, §8.1).
4. **disagreement는 실패가 아니라 ambiguous case로 분리한다(§8.4 ambiguous stratum).** 불일치 케이스는 gate 통과/실패 계산에서 제외하고 별도 추적 — 억지 정답을 강요하지 않는다.

이 protocol로 만든 stance gold만 §8.5 stance 지표의 정답으로 쓴다.

### 8.8 Failure bucket

지표 숫자만으로는 *어디서* 망가졌는지 모른다. 실패를 단계로 국소화해 분류한다.

| bucket | 무엇이 틀렸나 |
|---|---|
| **grounding fail** | topic이 QID로 잘못 풀림 |
| **retrieval miss** | 좋은 agent edge가 후보 풀에 안 들어옴 |
| **gate over-prune** | 좋은 후보를 maturity/eligibility에서 잘라냄 |
| **ranking fail** | 후보엔 있었는데 순위가 낮음 |
| **stance fail** | for/against 축을 잘못 해석 |
| **explanation fail** | 추천 이유가 실제 edge/evidence와 안 맞음 |

같은 nDCG 하락이라도 retrieval miss인지 ranking fail인지에 따라 고칠 모듈이 다르다 — bucket이 그걸 가른다.

### 8.9 Alpha가 주장할 수 있는 것 / 없는 것

- **할 수 있다:** behavior 재현성·need별 regression, 가드 동작 검증, **topic→QID grounding 실측**(real anchor substrate 기반), mock edge 기준 retrieval/ranking regression, **B1 human gold core 위에서의 제한적·상대적 품질 비교**(설정 A vs B), 실패의 모듈 국소화.
- **할 수 없다:** "실제 사용자에게 좋은 추천인가"(절대 품질) — real Memory/Persona 연결 → 내부 dogfooding → Open Beta feedback 순으로만 증명한다(§3 feedback≠reward 유지). **B2 silver 점수는 품질 근거로 쓰지 않는다.**

§7.5 decision-log를 day-one부터 남기는 것이 여기 연결된다: 지금 만드는 evaluation harness가 그대로 **Open Beta off-policy 평가(§4.2)의 replay harness로 승계**된다.

Open Beta에선 feedback을 단일 reward로 뭉치지 않고 **UX·behavior·OPE로 분리**해서 본다(§8.11): Pull은 selection·CSAT·follow-up turn, Push는 silence·dismiss·interruption cost·intervention 후 accept처럼 turn-level signal을 나눠 보고(Mahmud et al.; Chen et al.), 새 ranking/silence policy는 실제 노출 전에 **decision-log 기반 off-policy evaluation으로 먼저 진단**한다(Saito et al.; ranking 큰 action space는 Takahashi et al.). 이는 §3 feedback≠reward의 운영 측 구현이다.

### 8.10 mock provider가 공급하는 신호 품질은 평가하지 않는다 — 통합 시 substrate 평가로 전환

"memory-api/Persona가 줄 부분을 mock으로 채운 단계에서, 그 부분도 평가해야 하나?"에 대한 답은 **단계에 따라 다르다.** 평가 대상(system-under-test)을 데이터 출처와 분리해서 봐야 한다.

- **mock provider 단계(Alpha): 아니오 — mock이 공급하는 신호의 "품질"은 평가하지 않는다.** mock edge/persona/eligibility는 *우리가 옳다고 가정하고 넣은 oracle*이다. 이걸 채점하면 §8.2의 자기채점(우리 fixture를 우리가 다시 맞히는지)으로 되돌아간다. 이 단계에서 SUT는 **mock provider를 제외한 Discovery/Recommendation 로직**이고, 질문은 "입력이 옳다고 가정할 때 Discovery/Recommendation이 설계대로 행동하는가"다.
  - **예외 — anchor substrate는 이미 real이라 지금도 평가된다(§8.3).** 즉 mock provider 단계에서도 **QID grounding 지표**(+anchor connections 확장)는 memory-api anchor 쪽에 "이 anchor 커버리지/disambiguation을 개선하라"는 피드백을 **이미** 줄 수 있다. agent-topic edge/persona/eligibility는 아직 없으므로(=mock) 평가 대상이 아닐 뿐이다.

- **통합 단계(memory-api/Persona 연결 후): 예 — 같은 gold set·scenario를 real substrate에 돌려 substrate 자체를 평가한다.** 이때 SUT가 **Discovery + real substrate 합동**으로 바뀌므로, 지금 만든 evaluation harness가 그대로 **upstream substrate evaluation report**가 된다: edge coverage 공백, maturity/evidence 산식 calibration, producer-side anchoring 오류 등을 memory-api/Persona 팀에 정량으로 돌려준다. 사용자의 직관("붙여서 돌려보고 memory-api 성능을 개선하라고 알려준다")이 정확히 이 모드다.

**전제: 실패 귀속(attribution).** real이 되면 나쁜 추천이 Discovery 탓인지 substrate 탓인지 갈라야 한다. §8.8 failure bucket이 그 장치다 — **grounding fail / retrieval miss / gate over-prune은 substrate(anchoring·edge·eligibility) 쪽으로, ranking / stance / explanation fail은 Discovery 쪽으로** 기운다. 다만 최종 귀속은 decision-log의 입력값·중간값·threshold를 보고 판단한다: retrieval miss는 K/neighbor expansion 문제일 수 있고, stance fail도 upstream `observed_stance` 오류일 수 있다. mock provider 단계의 점수를 baseline으로 고정해 두면, real로 바꾼 뒤의 지표 변화가 곧 substrate 품질 변화의 측정값이 된다.

**설계 함의:** 그래서 evaluation harness를 **substrate-agnostic**하게(provider 교체만으로 mock↔real 전환) 만들고 gold set을 통합 전후로 **동일하게 고정**해야 한다. 그래야 통합 전후 비교가 substrate 품질을 깨끗하게 분리해낸다. 이는 §7.1(provider 동일 인터페이스)·§7.6(통합=교체)의 평가 측 대응이다.

### 8.11 설계 근거 — 참고 문헌

§8의 설계는 최신 연구 흐름과 정렬돼 있다. 한 줄 요지: 최신 연구는 *"LLM judge를 쓰지 말라"*가 아니라 **human gold와 분리하고, rubric을 쪼개고, judge 자체를 검증하고, online behavior는 reward가 아니라 proxy/OPE로 다루라**는 방향이다. (확인일 2026-06-22 — arXiv ID는 영구 식별자이나 venue·version·acceptance status는 재확인 대상.)

**LLM judge ≠ human gold — B1/B2 분리의 근거(§8.1·8.2)**
- Soboroff, *Don't Use LLMs to Make Relevance Judgments* (2024). LLM으로 TREC식 relevance judgment를 통째로 대체하는 데 대한 경고 → **B1 human core 분리** 정당화. [arxiv.org/abs/2409.15133](https://arxiv.org/abs/2409.15133)
- Thomas et al., *Large language models can accurately predict searcher preferences* (SIGIR 2024). 프롬프트된 LLM이 human급 라벨 가능 → **B2 silver의 대량 확장** 타당성(반대 방향 근거). [arxiv.org/abs/2309.10621](https://arxiv.org/abs/2309.10621)
- Upadhyay et al., *UMBRELA* (LLM4Eval @ SIGIR 2024). Bing relevance assessor의 오픈 재현 → **B2 judge 구현 레퍼런스**. [arxiv.org/abs/2406.06519](https://arxiv.org/abs/2406.06519)

**Judge rubric & judge 검증 — §8.2 B2 운영 원칙의 근거**
- Farzi et al., *Criteria-Based LLM Relevance Judgments* (ICTIR 2025). relevance를 exactness/coverage/topicality/contextual-fit로 분해 → **multi-criteria rubric**. [arxiv.org/abs/2507.09488](https://arxiv.org/abs/2507.09488)
- Fabbri et al., *Evaluating Podcast Recommendations with Profile-Aware LLM-as-a-Judge* (RecSys 2025). scenario+profile+evidence를 주는 judge가 raw보다 낫다 → **judge 입력 설계**. [arxiv.org/abs/2508.08777](https://arxiv.org/abs/2508.08777)
- Zheng et al., *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* (NeurIPS 2023). position/verbosity/self-enhancement bias 최초 정식화. [arxiv.org/abs/2306.05685](https://arxiv.org/abs/2306.05685)
- Feng et al., *Are We on the Right Way to Assessing LLM-as-a-Judge?* (2025). judge의 pairwise stability·transitivity **meta-evaluation** 필요. [arxiv.org/abs/2512.16041](https://arxiv.org/abs/2512.16041)
- Gu et al., *A Survey on LLM-as-a-Judge* (2024). bias 원인·완화·메타평가 종합 survey. [arxiv.org/abs/2411.15594](https://arxiv.org/abs/2411.15594)

**합성 코퍼스·user simulator의 한계 — §8.4 stratum·validity의 근거**
- Zhang et al., *On Generative Agents in Recommendation* (Agent4Rec, SIGIR 2024). LLM 에이전트 user simulator의 대표작. [arxiv.org/abs/2310.10108](https://arxiv.org/abs/2310.10108)
- Zhu et al., *How Reliable is Your Simulator?* (2024). simulator의 leakage·history 편향 → **합성 평가 validity 경계**. [arxiv.org/abs/2403.16416](https://arxiv.org/abs/2403.16416)

**Offline–online gap / construct validity — §8.1 A·B vs C 분리의 근거**
- Ferrari Dacrema et al., *Are We Really Making Much Progress?* (RecSys 2019). 약한 baseline이 offline 향상을 착시로 만든다 → **baseline·known-item needle**의 중요성. [arxiv.org/abs/1907.06902](https://arxiv.org/abs/1907.06902)
- Krichene & Rendle, *On Sampled Metrics for Item Recommendation* (KDD 2020). sampled metric이 순위를 뒤집는다 → offline 프로토콜 construct validity. [dl.acm.org/doi/10.1145/3394486.3403226](https://dl.acm.org/doi/10.1145/3394486.3403226)

**Conversational/proactive 평가 & off-policy — Open Beta·Push의 근거(§8.9)**
- Mahmud et al., *Evaluating User Experience in Conversational Recommender Systems* (OzCHI 2025). turn-level affective UX를 분리해 보라. [arxiv.org/abs/2508.02096](https://arxiv.org/abs/2508.02096)
- Chen et al., *Evaluating Conversational Recommender Systems via LLMs: A User-Centric Framework* (2025). dialogue/언어/추천/응답 4분할 평가. [arxiv.org/abs/2501.09493](https://arxiv.org/abs/2501.09493)
- Saito et al., *Open Bandit Dataset and Pipeline* (NeurIPS 2021). logged data 기반 OPE 표준 → **decision-log replay**. [arxiv.org/abs/2008.07146](https://arxiv.org/abs/2008.07146)
- Takahashi et al., *Off-Policy Evaluation of Ranking Policies via Embedding-Space User Behavior Modeling* (2025). 큰 ranking action space OPE → Push/silence policy 진단. [arxiv.org/abs/2506.00446](https://arxiv.org/abs/2506.00446)

## 9. Open Questions (→ 별도 `technology_selection` 문서, deep research 대상)

- 한국어 entity linking 2-tier 설계: Wikidata candidate generator(label/alias + dense retrieval) + LLM rerank — 한국어 candidate recall·QID directness·라이선스 검증 (ReFinED·BELA·mGENRE는 archived/non-commercial이라 reference)
- KG access 방식: 라이브 WDQS(graph split·rate limit) vs 로컬 self-host(QLever 우선)
- edge store 선택: Postgres vs graph DB vs Vespa(retrieve+filter+rank 통합 시)
- vector infra 도입 조건: 언제부터 embedding·ANN이 필요한가
- evaluation stack 선택: 자체 metric vs Evidently, off-policy(OBP) 도입 시점
