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
| 1 | **Query-side linker** | Discovery | 요청 topic text → Wikidata QID | `bourbon-memory-api` anchor search/get/graph (real) · §4 entity linking |
| 2 | **Candidate retrieval** | Discovery | QID → agent-topic edge 후보 (+ sparse 시 이웃 anchor 확장) | agent-topic edge: Alpha mock, later Memory real / 이웃 확장은 anchor graph (real) |
| 3 | **Gate** | Discovery | maturity / eligibility (+ 외부공개 시 safety) 필터 | eligibility: Alpha mock, later owner/privacy/safety |
| 4 | **Need ranking** | Recommendation | depth / for / against / coverage 스코어링 | persona prior: Alpha mock, later Persona real (ranking 로직은 build) |
| 5 | **Serving** | Recommendation | 후보·이유·`routing_target` payload, push silence 판정 | — (build) |
| 6 | **Decision-log** | (공통) | 입력·생존·탈락 이유 기록 | — (build) |

모듈 1~3이 Discovery 단계로 directions의 **need-complete candidate pool**을 만들고, 4·5가 Recommendation 단계로 **need-conditioned 선택/서빙**을 한다 (directions §5 단계 경계와 일치). 6은 공통이다.

> `bourbon-memory-api`가 Query-side linker나 Candidate retrieval 모듈을 대신 구현하는 것은 아니다. Discovery가 두 모듈을 소유하고, memory-api는 anchor substrate와 (later) agent-topic edge substrate를 provider 경계로 제공할 뿐이다.

### 2.3 요청 처리 경로 (real vs mock)

Alpha 기준 한 요청의 경로다. **[real]** = `bourbon-memory-api` 실제 호출, **[mock]** = mock provider, **[build]** = Discovery 직접 구현.

```
request(topic_text, need_type, user_stance_ref?)
  │
  ├─① query-side linker  topic_text → QID            KnowledgeAnchorProvider.search_candidates() [real]
  │                       (sparse면 이웃 anchor 확장)   KnowledgeAnchorProvider.expand_graph()   [real]
  ├─② candidate retrieval QID → agent-topic edges     MemoryEdgeProvider.get_edges()           [mock]
  ├─③ gate               maturity·eligibility 필터     EligibilityProvider.check()              [mock]
  ├─④ need ranking       depth/for/against 스코어링     PersonaProvider.get_prior() [mock] + rule/LLM [build]
  ├─⑤ serving            payload + routing_target, silence 판정                                 [build]
  └─⑥ decision-log       생존/탈락 이유 기록                                                      [build]
```

핵심은 **①은 지금 실제 substrate가 있고, ②~③은 mock provider로, ④는 mock persona prior + build ranking으로 선대체한다**는 것이다(④의 ranking 로직 자체는 우리가 build하고, 그 안의 persona prior만 mock이다). 그래서 Discovery는 Memory/Persona 구현을 기다리지 않고 전체 경로를 끝까지 돌릴 수 있다. mock을 real로 바꾸는 것이 곧 통합이다(§7).

### 2.4 Provider 인터페이스 (sketch)

경계는 4개 provider 인터페이스로 고정한다. 아래는 **언어중립 sketch이며 확정 시그니처가 아니다.** mock과 real은 같은 인터페이스를 구현한다(§7.1).

`KnowledgeAnchorProvider` — **real** (`bourbon-memory-api`):

```
search_candidates(text, lang?)   -> [AnchorCandidate{ qid, label, importance }]                    # GET /knowledge/anchors
get(qid)                         -> Anchor{ qid, label, description, instance_of, subclass_of, … }  # GET /knowledge/anchors/{qid}
expand_graph(qid, edges, limit)  -> [AnchorNeighbor{ qid, label, relation }]                        # GET /knowledge/anchors/{qid}/graph
search_articles(q, qid?, lang?)  -> [ArticleChunk]                                                  # GET /knowledge/articles (보조)
```

`KnowledgeAnchorProvider`는 full entity linker가 아니라 **memory-api anchor substrate adapter**다 — anchor 검색/조회/graph 호출을 감쌀 뿐 disambiguation을 결정하지 않는다. Query-side linker(모듈 1)가 이 provider와 필요 시 별도 entity linker(§4.1)를 조합해 최종 QID를 정한다.

`MemoryEdgeProvider` — **mock** (Alpha):

```
get_edges(anchor_id) -> [AgentTopicEdge{ agent_id, anchor_id,
                          maturity, evidence_strength, freshness,
                          observed_stance, stance_summary, evidence_refs,
                          routing_target, source_owner }]
```

`PersonaProvider` — **mock** (Alpha):

```
get_prior(agent_id) -> PersonaPrior{ prior_stance?, stable_traits, expertise_claims }
```

`EligibilityProvider` — **mock** (Alpha):

```
check(agent_id, context?) -> Eligibility{ discoverable, … }   # owner / privacy / (safety)
```

`AnchorCandidate`·`Anchor`만 real 응답(§2.6의 노출 9필드)에 묶이고, 나머지 타입은 contract로 합의해 mock으로 채운다(§7.2). 필드별 `source_owner` 규칙은 §7.2.

### 2.5 경계 요약표

| Discovery 호출 | 뒷단 | Alpha 상태 |
|---|---|---|
| `topic_text` → QID | `bourbon-memory-api` `GET /knowledge/anchors` | **real** |
| anchor 단건/검증 | `GET /knowledge/anchors/{qid}` | **real** |
| 이웃 anchor 확장(sparse) | `GET /knowledge/anchors/{qid}/graph` | **real** |
| article 보조 자료 | `GET /knowledge/articles` | **real** (보조) |
| agent-topic edge | `MemoryEdgeProvider` | **mock** |
| persona prior | `PersonaProvider` | **mock** |
| discoverability / eligibility | `EligibilityProvider` | **mock** |
| evidence 원문 조회 | conversation search | 후일 (Alpha 미사용) |

이 표가 경계의 single source다 — "real인 줄 알았는데 mock"인 혼선을 막는다. `evidence_refs`의 원문 조회는 conversation search로 연결될 수 있으나 Alpha 후보 생성 경로엔 들어가지 않는다.

### 2.6 현재 `bourbon-memory-api` 현황

`../bourbon-memory-api`를 직접 읽지 않아도 통합 상황을 이해할 수 있게 적은 요약이다. 결론은 **anchor substrate는 real로 바로 쓸 수 있고, agent-topic edge substrate는 아직 없다**는 것이다.

**현재 구현된 것** — 구현 중심은 두 가지다.

| 영역 | 현재 제공 | Discovery에서의 의미 |
|---|---|---|
| **Conversation memory (L0)** | 메시지 저장, room timeline, keyword/time-range search, context expansion, cross-room recall | 후일 `evidence_refs`의 원천이 될 수 있다. 지금 agent-topic edge를 만들지는 않는다 |
| **Public knowledge backbone (L3)** | Wikidata 기반 anchor index, anchor search, 단건 조회, ego graph, Wikipedia article BM25 search | query-side anchor grounding / KG 확장 / QID vocabulary 기준으로 **바로 활용 가능** |

현재 public anchor API 표면:

| API | 용도 | Discovery 적용 |
|---|---|---|
| `GET /knowledge/anchors?q=…` | label/aliases 기반 검색, `importance` 정렬 | topic → QID 후보 생성 |
| `GET /knowledge/anchors/{qid}` | QID 단건 조회 | 선택 anchor 검증, label/description 표시 |
| `GET /knowledge/anchors/{qid}/graph` | `linked_qids` + hierarchy 기반 ego graph | sparse anchor fallback, 관련 anchor 확장 |
| `GET /knowledge/articles?q=…` | Wikipedia article chunk BM25 검색 | topic 설명/axis hint 보조. agent 추천 근거로 직접 쓰지 않음 |

Anchor는 Wikidata QID를 `external_id`로 보존한다. **단, Discovery는 DB가 아니라 API를 소비하므로 "모델이 가진 필드"와 "API가 주는 필드"를 구분해야 한다.**

- **Anchor 내부 모델**: `external_id`, `source`, `label`, `labels`, `description`, `aliases`, `instance_of`, `subclass_of`, `sitelink_count`, `pageview`, `pagerank`, `importance`, `categories`, `linked_qids`, `abstract`, `fetched_at`.
- **`GET /knowledge/anchors`·`/{qid}` 응답이 노출하는 것(현재)**: `external_id`, `source`, `label`, `labels`, `description`, `aliases`, `instance_of`, `subclass_of`, `importance` — 9개.
- `linked_qids`는 `/{qid}/graph`에서 neighbor 형태로 **간접** 노출되고, `categories`는 graph node에서만 노출된다.
- raw `pageview` / `pagerank` / `sitelink_count` / `abstract` / `fetched_at`은 **현재 anchor 응답에 없다**.
- 따라서 Discovery의 `anchor_id`는 `external_id`로 잡되, 나머지는 위 9개 + graph 표면 안에서 설계한다.

`importance`는 pageview / PageRank / sitelink_count를 섞은(0.5·pageview + 0.3·pagerank + 0.2·sitelink_count, log 압축·정규화) public-anchor notability 신호다. Discovery에서는 **entity 후보 disambiguation prior**나 sparse fallback 정렬에만 쓴다. 이 값을 agent 추천 품질·expertise·contribution·reputation으로 해석하면 안 된다 — anchor(개념)에 붙은 값이지 agent에 붙은 값이 아니다.

**raw signal은 Alpha에서 요구하지 않는다.** Alpha 목적은 query-side grounding + 후보 retrieval/ranking skeleton 검증이고 `importance` 하나로 충분하다. raw `pageview/pagerank`는 disambiguation 미세튜닝엔 쓸 수 있으나 지금은 objective 혼선만 키우고, `abstract`는 axis hint에 유용하지만 이미 `/knowledge/articles`가 있고 axis/orthogonal은 Open Beta다. → raw signal 노출(예: `anchor_enrichment_fields`)은 **Open Beta 검토 항목**으로 남기고, 필요해지면 그때 Memory API contract로 요청한다.

**아직 없는 것** — Discovery가 기대하는 Memory/Persona contract 중 아래는 현재 API에 없다.

| Discovery가 필요한 것 | 현재 상태 | Alpha 대응 |
|---|---|---|
| `anchor_id ↔ agent_id` 단위 **agent-topic edge** | 없음 | `MockMemoryEdgeProvider` fixture로 선대체 |
| `topic_knowledge_maturity` / `evidence_strength` / `freshness` | 없음 | mock edge에 명시. 실제 산식은 Memory와 contract 합의 |
| `observed_stance` / `stance_summary` / opinion·experience 분리 | 없음 | mock edge + Discovery-side coarse extraction으로 시작 |
| `routing_target` | 없음 | routing source owner를 contract에 태깅하고 mock |
| `discoverability` / privacy eligibility | 없음 | privacy source owner를 contract에 태깅하고 mock |
| Persona prior | 이 repo에 Persona 구현 없음 | `MockPersonaProvider`로 선대체 |

즉 `bourbon-memory-api`의 Vision/Roadmap은 L0 → L1 → L2 → L3 흐름과 anchor routing 방향을 이미 갖고 있지만, 현재 코드 구현은 L0 conversation memory와 L3 public anchor backbone에 머물러 있다. Personal KG(L2), public anchor → personal node link, expert routing은 로드맵상 뒤쪽이다.

**privacy는 완전 백지가 아니다.** L0 conversation에는 이미 `PiiSensitivity`(PUBLIC/PERSONAL/SENSITIVE/SECRET) 기반 masking/clearance 모델이 있다. 다만 이건 message 마스킹 쪽이고, Discovery가 필요한 **agent-topic edge discoverability / candidate eligibility와는 직접 동일하지 않다.** 후자는 아직 없다. 나중에 eligibility contract(directions §11)는 새로 발명하지 말고 이 기존 PII sensitivity와 **정합**되게 둔다.

**QID 계약 — 이미 맞는 부분과 아직 합의할 부분.** schema가 `anchor_id: string`으로 맞아도 값의 의미가 다르면 후보가 만나지 않으므로, QID는 스키마가 아니라 의미 계약이다(§7.4).

이미 맞는 부분:

- Memory vision과 public anchor 구현 모두 Wikidata QID를 anchor 기준으로 본다.
- `Anchor.external_id`는 Wikidata QID를 그대로 보존한다.
- anchor graph는 `instance_of`·`subclass_of`·`linked_qids`로 KG 확장을 지원한다.

아직 합의할 부분:

- Discovery query-side linker가 고른 QID와 Memory producer-side anchoring이 붙인 QID가 **같은 disambiguation 기준**인지.
- alias / redirect / 다국어 label에서 어느 QID를 canonical로 볼지.
- **local anchor 계약** — Anchor 모델엔 이미 `source = WIKIDATA | LOCAL`이 있으므로 "local anchor를 만들지 말지"가 아니라 **기존 `LOCAL` enum 위에서 규칙을 합의**하는 문제다: ① local anchor ID namespace, ② Wikidata QID와의 충돌 방지, ③ lifecycle, ④ 나중에 Wikidata로 매핑될 때 merge/redirect 방식, ⑤ Discovery fixture에 local anchor를 포함할지. 이건 Alpha QID vocabulary 합의와 한 묶음이다.
- L2 personal node가 여러 public anchor에 걸칠 때 primary/secondary anchor를 어떻게 표현할지.

→ 따라서 public anchor API가 이미 있다는 건 좋은 출발점이지만, **QID 의미 계약은 여전히 Alpha 선결**이다.

## 3. Build vs Reuse 원칙

- **2-stage 패턴은 재사용한다.** candidate generation → ranking은 업계 표준이고, 우리의 Discovery 단계 → Recommendation 단계 분리가 사실상 그 패턴이다.
- **framework의 default objective는 쓰지 않는다.** engagement / popularity / affinity 최대화는 이 시스템이 directions §0·§5.4에서 거부한 모델이다. 프레임워크를 통째로 얹으면 그 bias가 다시 들어온다.
- **feedback은 reward가 아니다.** Open Beta feedback은 운영 진단 신호다(directions §6, Roadmap §8). ranking 정답 라벨이나 contribution/reputation score로 바로 환산하지 않는다.

> **RecSys framework는 "모델 동물원"이 아니라 "부품 창고"로만 본다.** RecBole/TFRS/Merlin을 도입하면 추천이 해결된다는 오해를 막는다. 재사용 대상은 retrieval/indexing 메커니즘·diversity 알고리즘·off-policy 평가 같은 *부품*이지, opinionated한 CF/engagement 파이프라인이 아니다.

## 4. Component 후보 (미확정)

특정 기술 확정이 아니라 **후보·도입 시점·주의점**을 정리한다. 확정은 §9 → 별도 `technology_selection`. 판단 컬럼: **Alpha / Open Beta / Post / when-needed / build**.

### 4.1 Discovery 단계 (후보 공간 구성)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **Entity linking** | ReFinED, BLINK, GENRE / OpenTapioca·Falcon 2.0(Wikidata 특화) | query-side: topic text → Wikidata QID | **Alpha 핵심** | producer-side(Memory) anchoring과 **같은 QID vocabulary로 정렬**돼야 후보가 맞음(§6.2). 계열별 차이 큼 — 라이선스·모델 크기·배포 방식·Wikidata 최신성/QID directness·다국어(한국어) 성능·confidence calibration을 검증 항목으로 둘 것 |
| **Wikidata / KG access** | WDQS(SPARQL)·dumps·qwikidata / 로컬 Qlever·Oxigraph | QID, parent/neighbor, sparse anchor fallback | **Alpha** | 라이브 WDQS vs 로컬 덤프 운영 방식은 별도 비교 |
| **Edge store + metadata filter** | Postgres(+pgvector), graph DB(Neo4j·Nebula) / Vespa | `anchor_id` 기반 edge 조회 + maturity·freshness·discoverability·safety 필터 | **Alpha**(Postgres/graph) / when-needed(Vespa) | Alpha 검색은 대부분 structured query라 vector 없이 충분할 수 있음. Vespa는 retrieve+filter+rank를 한 엔진으로 통합하고 싶을 때의 후보지만, 첫 선택지는 아님(운영 복잡도) — 선택 기준은 §9 |
| **KG embedding** | PyKEEN, DGL-KE, AmpliGraph | anchor 연관도/이웃 확장 | when-needed | semantic 이웃 확장이 필요해질 때 |
| **ANN / vector** | Faiss, Qdrant | stance/persona embedding, topic-conditioned embedding 검색 | when-needed | embedding 도입·semantic recall·대규모 candidate gen 시에만. Alpha 조기 dependency 아님 |

### 4.2 Recommendation 단계 (need-conditioned 선택/서빙)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **rule scoring + LLM/text 비교** | (직접) | depth / for / against / coverage coarse scoring | **Alpha 핵심** | symbolic descriptor 중심 |
| **diversity / coverage** | MMR, DPP, xQuAD·PM-2, calibrated recommendation | coverage Need, 결과 다양화 | **Open Beta** | against/orthogonal을 **대신하지 못함** — 다양화 프리미티브일 뿐 |
| **evaluation** | 표준 metric(Recall@K·Precision@K·NDCG·MRR, Evidently 참고) + off-policy(OBP) | feedback 진단, threshold 튜닝, shadow/신정책 평가 | **Open Beta** (진단용) | reward로 직결 ❌. **off-policy(OPE)는 logged propensity·action set·reward proxy 정의가 없으면 불가/제한적이며 잘못된 확신을 줄 수 있다** — decision-log에 이 필드들을 남기는 게 선행(§7.5). Alpha 평가 전략(gold set·지표·failure bucket)은 §8 |
| **Learning-to-rank** | LightGBM LambdaRank, XGBoost(rank:ndcg) | need별 reranker | **Post** | feedback label·evaluation policy 안정 후. global engagement label 단일 학습 ❌ |
| **RecSys framework** | RecBole(benchmark), TFRS(multi-task 실험), Merlin(대규모) | 알고리즘 비교·실험·scale-out | **Post** / benchmark·실험용 | 제품 핵심 로직 대체 ❌, default objective ❌ |

### 4.3 직접 구현 (기성 컴포넌트 없음, 프리미티브만 재사용)

| 항목 | 정의 | 빌릴 프리미티브 | 현재 판단 |
|---|---|---|---|
| **against / orthogonal** | against = same axis·opposite stance / orthogonal = different established axis | stance detection, ABSA | for/against=**Alpha**, orthogonal=**Open Beta**(조건부) |
| **contested-axis 도출** | 쟁점 축 establishment·divergence mass 게이팅 | BERTopic·aspect extraction / ideal-point(PyMC/Stan) | **Open Beta**: LLM coarse + established/inherited_established gate / **Post**: mature factorization(ideal-point·요인분해) |
| **push silence / when-to-recommend** | 기준 미달 시 침묵 | CRS(conversational rec) 문헌, abstain-action bandit | **Open Beta** |
| **contribution / reputation** | validated memory impact 누적, popularity guard | fairness-in-ranking·bandit 문헌 | **Post** |

## 5. 단계별 도입 순서

| 단계 | 가져올 것 | 미룰 것 |
|---|---|---|
| **Alpha** | Entity linking, Wikidata/KG access, structured edge store + filter, rule/LLM scoring, decision-log 설계 | RecSys framework, vector/ANN(임베딩 전), LTR |
| **Open Beta** | diversity/coverage 알고리즘 일부, feedback diagnostic metric, off-policy evaluation 검토. vector/ANN은 embedding 도입 시 | LTR/model-based ranking |
| **Post-Open-Beta** | LightGBM LambdaRank류 reranker, TFRS/RecBole 실험, Faiss/Qdrant scale-out, KG embedding, Merlin(대규모 시), contribution/reputation 학습(validated memory impact 준비 후) | — |

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
| **B. 합성 + independent gold label** | 우리 생성(현실적 구조) | **사람이 별도로** 판정 | 상대 품질·랭킹 지표 *proxy*(설정 A vs B 비교) | ✅ 일부 |
| **C. 실데이터 + 행동** | 실제 사용자 | accept/click + dogfooding/human review | 실사용에 가까운 품질 신호 (단독 "정답" 아님) | ❌ (real 연결 + dogfooding + Open Beta) |

Alpha는 **A 전부 + B 일부**까지만 주장한다. C는 못 한다 — 이걸 박아두어야 합성 지표를 과신하지 않는다. C도 "진짜 품질의 정답"은 아니다: accept/click은 합성보다 나은 behavioral signal이지만 그 자체가 품질이 아니라 **운영 proxy**이고(특히 against/orthogonal은 클릭·짧은 대화가 품질을 왜곡할 수 있다, §3 feedback≠reward), dogfooding/human review와 **함께 해석**한다.

### 8.2 핵심 원칙 — gold label ≠ scoring rule

이 평가에서 가장 쉽게 무너지는 지점이다. **fixture(§7.3)는 시스템 *입력*이고, gold label은 사람이 "이 요청에는 이 agent가 좋은 추천이다/아니다"를 별도로 판단한 *정답*이다.** 둘을 같은 규칙으로 만들면(예: `maturity ≥ 0.9`면 자동 정답으로 라벨링) 평가는 "구현이 자기 공식을 잘 반복하는지"만 보게 되고, 품질 측정이 아니라 동어반복이 된다.

따라서:

- gold label은 스코어링 산식과 **독립된 사람(또는 다른 기준)**이 만든다.
- 데이터 생성과 정답 판정의 주체/프롬프트를 분리한다(같은 LLM이 둘 다 만들면 construct validity 붕괴).
- 라벨은 4단계로 둔다: **`ideal` / `acceptable` / `bad` / `must_not_show`**. `must_not_show`는 단순 하위 등급이 아니라 **hard negative class**로, "절대 떠선 안 되는" 후보의 false-pass를 직접 측정한다. **Alpha에선** discoverability off, weak evidence, wrong stance, hollow agent 같은 hard negative를 담는다(safety/privacy gate는 Alpha inactive — Open Beta 이전 활성화 시 safety/privacy 위반을 별도 세분화한다).

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
  → failure bucket 분석 (§8.6)
```

코퍼스 규모(Alpha 출발 기준):

- **agent 30~50개**, **anchor 20~30개**, **topic(anchor)당 다수 agent-topic edge**.
- **scenario query 전체 100~200개**(need 5종에 걸쳐 need별 최소 20~40개씩), 각 scenario의 후보 agent들에 4단계 gold label. — regression set이 성숙하면 need별로 더 키운다.
- §7.3 가드 역산 케이스와 **known-item needle**(명백히 1등이어야 할 expert를 의도적으로 심는 sanity 케이스)을 정상 경로로 포함한다.

gold set은 **한 번 만들어 regression benchmark로 고정**하고 실험 간 재사용한다(TREC식 pooling: 여러 랭킹 변형의 top-k + 랜덤 샘플을 pool로 모아 사람이 판정).

### 8.5 단계별 지표

| 평가 대상 | 지표 | 비고 |
|---|---|---|
| **grounding** | QID top-1 / top-3 accuracy | **real substrate 기반 quality gate**(§8.3) |
| **retrieval** | Recall@K, 후보 누락률 | **mock edge 기준** 후보 생성 regression — 후보 공간 천장(여기서 새면 ranking 무의미) |
| **gate** | false block / false pass | `must_not_show`가 false-pass를 직격 |
| **ranking** | nDCG@K, MRR, Precision@K, MAP@K | B층 proxy |
| **stance** | same-axis / opposite-stance 판정 정확도 | for / against |
| **coverage** | unique axis / source / persona coverage, redundancy | same-axis crowding 가드 |
| **reason(설명)** | evidence_ref 없는 설명·과장 설명·stance mismatch 수 | explanation fail |
| (보조) **calibration** | confidence ↔ 판정 관련성 상관 | |

각 지표의 의미와 그것으로 얻는 판단:

- **grounding — QID top-1 / top-3 accuracy.** topic text를 정답 QID로 푼 비율(top-1 = 1순위가 정답, top-3 = 상위 3개 안에 정답). → 링커가 안정적으로 옳은 anchor를 잡는가. *top-1은 낮은데 top-3가 높으면* disambiguation rerank로 회수 가능하다는 신호, *둘 다 낮으면* vocabulary 정렬(§7.4)이나 링커 자체 문제. real substrate라 memory-api anchor 커버리지 공백도 여기서 드러난다.
- **retrieval — Recall@K, 후보 누락률.** gold가 "관련"으로 판정한 agent 중 후보 풀 상위 K에 들어온 비율(Recall@K)과 그 반대(누락률). → 후보 공간이 **천장**이다. ranking이 아무리 좋아도 여기서 빠진 agent는 절대 못 뜬다. 낮으면 edge coverage·이웃 anchor 확장·K 상향을 본다. **Alpha에선 edge가 mock이므로 이건 mock edge 기준 후보 생성 regression 지표**이고, real substrate 품질 측정은 통합 후다(§8.8).
- **gate — false block / false pass.** 보여야 할 후보(ideal/acceptable)를 자른 비율(false block = over-prune)과 `must_not_show`인데 통과시킨 비율(false pass). → 게이트 임계가 과한가/느슨한가. *false block↑* → maturity/eligibility cutoff 완화 검토, *false pass↑* → eligibility/discoverability 게이트 강화. **Alpha 게이트는 maturity/eligibility(discoverability)까지이고 safety/privacy는 inactive**(§8.2) — safety/privacy의 false pass는 그 게이트 활성화 시(Open Beta 이전) 별도로 본다.
- **ranking — nDCG@K, MRR, Precision@K, MAP@K.** nDCG = 등급(ideal>acceptable>…)을 순위 가중으로 반영한 종합 점수(좋은 걸 위로 올렸나), MRR = 첫 관련 결과의 평균 역순위(첫 좋은 추천이 얼마나 위에 오나), Precision@K = 상위 K 중 관련 비율(짧은 리스트 정확도), MAP@K = 다수 관련 항목의 순위 품질 평균. → need별 ranking 로직이 의도대로 정렬하는가. **단 mock edge 위에서는 B층 proxy**(§8.1) — 설정 A vs B 비교용이지 절대 품질이 아니다.
- **stance — same-axis / opposite-stance 판정 정확도.** for(같은 축·같은 방향)·against(같은 축·반대 방향) 요청에서 후보의 축/방향 분류가 gold와 맞는 비율. → for/against가 "다른 주제"나 "같은 의견 반복"으로 새지 않는가. against가 orthogonal(다른 축)로 새는 흔한 실패를 잡는다.
- **coverage — unique axis / source / persona coverage, redundancy.** 결과 리스트가 덮는 고유 축/출처/페르소나 수와 중복도. → coverage need에서 비슷한 agent만 반복(same-axis crowding)하지 않고 의미 있는 범위를 덮는가. redundancy↑면 다양화 프리미티브(MMR 등, §4.2) 필요 신호.
- **reason — evidence_ref 없는 설명·과장 설명·stance mismatch 수.** 추천 이유가 실제 edge/evidence와 어긋나는 건수. → 설명이 사후 합리화가 아니라 실제 근거에 묶이는가. evidence_ref 없는 설명은 hallucinated reason, stance mismatch는 이유-결론 불일치.
- **calibration — confidence ↔ 판정 관련성 상관.** 시스템이 매긴 confidence가 실제 gold 관련성과 상관하는가. → confidence를 threshold·push silence 판정에 믿고 쓸 수 있는가. 상관이 낮으면 confidence 기반 침묵 판정이 위험하다.

지표는 need별(depth / experience / for / against / coverage)로 분리해 본다 — 단일 평균은 need별 regression 실패를 가린다.

### 8.6 Failure bucket

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

### 8.7 Alpha가 주장할 수 있는 것 / 없는 것

- **할 수 있다:** behavior 재현성·need별 regression, 가드 동작 검증, **topic→QID grounding 실측**(real anchor substrate 기반), mock edge 기준 retrieval/ranking regression, 실패의 모듈 국소화.
- **할 수 없다:** "실제 사용자에게 좋은 추천인가" — real Memory/Persona 연결 → 내부 dogfooding → Open Beta feedback 순으로만 증명한다(§3 feedback≠reward 유지).

§7.5 decision-log를 day-one부터 남기는 것이 여기 연결된다: 지금 만드는 evaluation harness가 그대로 **Open Beta off-policy 평가(§4.2)의 replay harness로 승계**된다.

### 8.8 mock provider가 공급하는 신호 품질은 평가하지 않는다 — 통합 시 substrate 평가로 전환

"memory-api/Persona가 줄 부분을 mock으로 채운 단계에서, 그 부분도 평가해야 하나?"에 대한 답은 **단계에 따라 다르다.** 평가 대상(system-under-test)을 데이터 출처와 분리해서 봐야 한다.

- **mock provider 단계(Alpha): 아니오 — mock이 공급하는 신호의 "품질"은 평가하지 않는다.** mock edge/persona/eligibility는 *우리가 옳다고 가정하고 넣은 oracle*이다. 이걸 채점하면 §8.2의 자기채점(우리 fixture를 우리가 다시 맞히는지)으로 되돌아간다. 이 단계에서 SUT는 **mock provider를 제외한 Discovery/Recommendation 로직**이고, 질문은 "입력이 옳다고 가정할 때 Discovery/Recommendation이 설계대로 행동하는가"다.
  - **예외 — anchor substrate는 이미 real이라 지금도 평가된다(§8.3).** 즉 mock provider 단계에서도 **QID grounding 지표**(+anchor graph 확장)는 memory-api anchor 쪽에 "이 anchor 커버리지/disambiguation을 개선하라"는 피드백을 **이미** 줄 수 있다. agent-topic edge/persona/eligibility는 아직 없으므로(=mock) 평가 대상이 아닐 뿐이다.

- **통합 단계(memory-api/Persona 연결 후): 예 — 같은 gold set·scenario를 real substrate에 돌려 substrate 자체를 평가한다.** 이때 SUT가 **Discovery + real substrate 합동**으로 바뀌므로, 지금 만든 evaluation harness가 그대로 **upstream substrate evaluation report**가 된다: edge coverage 공백, maturity/evidence 산식 calibration, producer-side anchoring 오류 등을 memory-api/Persona 팀에 정량으로 돌려준다. 사용자의 직관("붙여서 돌려보고 memory-api 성능을 개선하라고 알려준다")이 정확히 이 모드다.

**전제: 실패 귀속(attribution).** real이 되면 나쁜 추천이 Discovery 탓인지 substrate 탓인지 갈라야 한다. §8.6 failure bucket이 그 장치다 — **grounding fail / retrieval miss / gate over-prune은 substrate(anchoring·edge·eligibility) 쪽으로, ranking / stance / explanation fail은 Discovery 쪽으로** 기운다. 다만 최종 귀속은 decision-log의 입력값·중간값·threshold를 보고 판단한다: retrieval miss는 K/neighbor expansion 문제일 수 있고, stance fail도 upstream `observed_stance` 오류일 수 있다. mock provider 단계의 점수를 baseline으로 고정해 두면, real로 바꾼 뒤의 지표 변화가 곧 substrate 품질 변화의 측정값이 된다.

**설계 함의:** 그래서 evaluation harness를 **substrate-agnostic**하게(provider 교체만으로 mock↔real 전환) 만들고 gold set을 통합 전후로 **동일하게 고정**해야 한다. 그래야 통합 전후 비교가 substrate 품질을 깨끗하게 분리해낸다. 이는 §7.1(provider 동일 인터페이스)·§7.6(통합=교체)의 평가 측 대응이다.

## 9. Open Questions (→ 별도 `technology_selection` 문서, deep research 대상)

- entity linker 비교: ReFinED vs BLINK vs OpenTapioca/Falcon (Wikidata 적합성·라이선스·성숙도)
- KG access 방식: 라이브 WDQS vs 로컬 dump/local store
- edge store 선택: Postgres vs graph DB vs Vespa(retrieve+filter+rank 통합 시)
- vector infra 도입 조건: 언제부터 embedding·ANN이 필요한가
- evaluation stack 선택: 자체 metric vs Evidently, off-policy(OBP) 도입 시점
