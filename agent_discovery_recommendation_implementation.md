# Agent Discovery & Recommendation — Implementation Approach (working)

> 이 문서는 구현 접근과 **재사용 후보**를 정리한 working document다. 확정 기술 스택이 아니다. 구체 기술 선택(특정 entity linker·store·ANN·LTR 확정)은 deep research 후 별도 `technology_selection` 문서에서 다룬다.
>
> **Alpha의 구현 병목은 RecSys 모델이 아니라 topic→anchor grounding과 agent-topic edge retrieval이다.**

## 0. 문서 위치

| 문서 | 역할 |
|---|---|
| `agent_discovery_recommendation_directions.md` | 설계 기준 / 개념 모델 / source of truth |
| `Agent_Discovery_Recommendation_Roadmap.md` | Alpha / Open Beta / Post-Open-Beta 단계 공유 |
| **이 문서** | 구현 접근 / build vs reuse / 후보 기술 / 도입 순서 |

설계·범위는 위 두 문서를 참조하고 여기서 재진술하지 않는다. 단계 정의(Alpha/Open Beta/Post)와 내부 단계(Discovery/Recommendation)는 directions §0·§5, Roadmap §1을 따른다.

## 1. 핵심 결론

- Alpha에 RecSys framework는 도입하지 않는다.
- 지금 가져올 것은 **Entity Linking / Wikidata / KG / structured retrieval** (IR 쪽)이다.
- RecSys는 **2-stage 패턴**과 일부 **부품**만 재사용한다.
- against / orthogonal / contested-axis / push silence / contribution은 **직접 구현**한다.

## 2. Build vs Reuse 원칙

- **2-stage 패턴은 재사용한다.** candidate generation → ranking은 업계 표준이고, 우리의 Discovery 단계 → Recommendation 단계 분리가 사실상 그 패턴이다.
- **framework의 default objective는 쓰지 않는다.** engagement / popularity / affinity 최대화는 이 시스템이 §0·§5.4(directions)에서 거부한 모델이다. 프레임워크를 통째로 얹으면 그 bias가 다시 들어온다.
- **feedback은 reward가 아니다.** Open Beta feedback은 운영 진단 신호다(directions §6, Roadmap §8). ranking 정답 라벨이나 contribution/reputation score로 바로 환산하지 않는다.

> **RecSys framework는 "모델 동물원"이 아니라 "부품 창고"로만 본다.** RecBole/TFRS/Merlin을 도입하면 추천이 해결된다는 오해를 막는다. 재사용 대상은 retrieval/indexing 메커니즘·diversity 알고리즘·off-policy 평가 같은 *부품*이지, opinionated한 CF/engagement 파이프라인이 아니다.

## 3. Component 후보

특정 기술 확정이 아니라 후보·도입 시점·주의점을 정리한다. 판단 컬럼: **Alpha / Open Beta / Post / when-needed / build**.

### 3.1 Discovery 단계 (후보 공간 구성)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **Entity linking** | ReFinED, BLINK, GENRE / OpenTapioca·Falcon 2.0(Wikidata 특화) | query-side: topic text → Wikidata QID | **Alpha 핵심** | producer-side(Memory) anchoring과 **같은 QID vocabulary로 정렬**돼야 후보가 맞음 (§5). 계열별 차이 큼 — 라이선스·모델 크기·배포 방식·Wikidata 최신성/QID directness·다국어(한국어) 성능·confidence calibration을 검증 항목으로 둘 것 |
| **Wikidata / KG access** | WDQS(SPARQL)·dumps·qwikidata / 로컬 Qlever·Oxigraph | QID, parent/neighbor, sparse anchor fallback | **Alpha** | 라이브 WDQS vs 로컬 덤프 운영 방식은 별도 비교 |
| **Edge store + metadata filter** | Postgres(+pgvector), graph DB(Neo4j·Nebula) / Vespa | `anchor_id` 기반 edge 조회 + maturity·freshness·discoverability·safety 필터 | **Alpha**(Postgres/graph) / when-needed(Vespa) | Alpha 검색은 대부분 structured query라 vector 없이 충분할 수 있음. Vespa는 retrieve+filter+rank를 한 엔진으로 통합하고 싶을 때의 후보지만, 첫 선택지는 아님(운영 복잡도) — 선택 기준은 §6 |
| **KG embedding** | PyKEEN, DGL-KE, AmpliGraph | anchor 연관도/이웃 확장 | when-needed | semantic 이웃 확장이 필요해질 때 |
| **ANN / vector** | Faiss, Qdrant | stance/persona embedding, topic-conditioned embedding 검색 | when-needed | embedding 도입·semantic recall·대규모 candidate gen 시에만. Alpha 조기 dependency 아님 |

### 3.2 Recommendation 단계 (need-conditioned 선택/서빙)

| 영역 | 후보 | 용도 | 현재 판단 | 주의점 |
|---|---|---|---|---|
| **rule scoring + LLM/text 비교** | (직접) | depth / for / against / coverage coarse scoring | **Alpha 핵심** | symbolic descriptor 중심 |
| **diversity / coverage** | MMR, DPP, xQuAD·PM-2, calibrated recommendation | coverage Need, 결과 다양화 | **Open Beta** | against/orthogonal을 **대신하지 못함** — 다양화 프리미티브일 뿐 |
| **evaluation** | 표준 metric(Recall@K·Precision@K·NDCG·MRR, Evidently 참고) + off-policy(OBP) | feedback 진단, threshold 튜닝, shadow/신정책 평가 | **Open Beta** (진단용) | reward로 직결 ❌. **off-policy(OPE)는 logged propensity·action set·reward proxy 정의가 없으면 불가/제한적이며 잘못된 확신을 줄 수 있다** — decision-log에 이 필드들을 남기는 게 선행 |
| **Learning-to-rank** | LightGBM LambdaRank, XGBoost(rank:ndcg) | need별 reranker | **Post** | feedback label·evaluation policy 안정 후. global engagement label 단일 학습 ❌ |
| **RecSys framework** | RecBole(benchmark), TFRS(multi-task 실험), Merlin(대규모) | 알고리즘 비교·실험·scale-out | **Post** / benchmark·실험용 | 제품 핵심 로직 대체 ❌, default objective ❌ |

### 3.3 직접 구현 (기성 컴포넌트 없음, 프리미티브만 재사용)

| 항목 | 정의 | 빌릴 프리미티브 | 현재 판단 |
|---|---|---|---|
| **against / orthogonal** | against = same axis·opposite stance / orthogonal = different established axis | stance detection, ABSA | for/against=**Alpha**, orthogonal=**Open Beta**(조건부) |
| **contested-axis 도출** | 쟁점 축 establishment·divergence mass 게이팅 | BERTopic·aspect extraction / ideal-point(PyMC/Stan) | **Open Beta**: LLM coarse + established/inherited_established gate / **Post**: mature factorization(ideal-point·요인분해) |
| **push silence / when-to-recommend** | 기준 미달 시 침묵 | CRS(conversational rec) 문헌, abstain-action bandit | **Open Beta** |
| **contribution / reputation** | validated memory impact 누적, popularity guard | fairness-in-ranking·bandit 문헌 | **Post** |

## 4. 단계별 도입 순서

| 단계 | 가져올 것 | 미룰 것 |
|---|---|---|
| **Alpha** | Entity linking, Wikidata/KG access, structured edge store + filter, rule/LLM scoring, decision-log 설계 | RecSys framework, vector/ANN(임베딩 전), LTR |
| **Open Beta** | diversity/coverage 알고리즘 일부, feedback diagnostic metric, off-policy evaluation 검토. vector/ANN은 embedding 도입 시 | LTR/model-based ranking |
| **Post-Open-Beta** | LightGBM LambdaRank류 reranker, TFRS/RecBole 실험, Faiss/Qdrant scale-out, KG embedding, Merlin(대규모 시), contribution/reputation 학습(validated memory impact 준비 후) | — |

## 5. 선결 의존성과 리스크

- **topic→anchor grounding 품질** — Alpha 성공이 추천 모델이 아니라 여기에 달려 있다.
- **query-side / producer-side anchor vocabulary 정렬 (Memory와 선결)** — Discovery 질의 linker(topic→QID)와 Memory의 producer-side anchoring(agent L2 node→QID)이 **같은 KG·같은 disambiguation·같은 QID 표준**으로 수렴해야 한다. 안 그러면 같은 주제가 서로 다른 QID로 풀려 후보가 안 만나진다.
- **Memory의 agent-topic edge readiness** — 후보 공간 자체가 Memory 산출물이다(directions §9.1, `anchor-personal node link` P0). Memory가 QID-anchored edge를 publish하지 않으면, query-side linker가 아무리 좋아도 후보가 0이다. entity-linker 비교보다 이 readiness 합의가 먼저다.
- **objective default 함정** — framework·라이브러리의 기본 목적함수(engagement/affinity)를 무심코 쓰지 않는다.
- **vector infra premature adoption** — Alpha 검색은 structured query 중심. ANN/vector는 when-needed.
- **feedback ≠ reward** — off-policy 평가(OBP 등)와 decision-log 필드 설계가 선행. shadow mode와 짝.

## 6. Mock-first / contract-first 전략

Memory·Persona 구현을 기다리면 Discovery/Recommendation Alpha가 막힌다. 그래서 **Memory/Persona와 공동 합의한 contract를 mock provider로 구현해 개발을 먼저 시작**한다. 핵심은 mock이 "버려질 개발용 더미"가 아니라 **통합 경계 그 자체 = 통합 리허설**이 되도록 만드는 것이다.

### 6.1 Provider 인터페이스 (real과 동일)

- Discovery는 Memory/Persona DB를 직접 읽지 않는다. `MemoryProvider` / `PersonaProvider` 인터페이스 뒤에 둔다.
- Alpha 개발 중에는 `MockMemoryProvider` / `MockPersonaProvider`를 붙이고, 실제 팀 API가 나오면 **구현만 교체**한다.
- **mock provider는 real provider와 동일한 인터페이스를 구현한다.** 이걸 명시하지 않으면 mock이 개발용 샘플로 전락하고 통합이 rewrite가 된다.

### 6.2 입력 contract — 공동 서명 (Discovery 단독 동결 ❌)

contract를 Discovery가 임의로 정하면 그건 우리 추측일 뿐이고, 통합 때 실제 출력과 어긋나면 mock 위에 쌓은 게 전부 rewrite다. 최소한 다음은 Memory/Persona와 **합의**해야 한다:

- 필드별 **source owner** (Memory / Persona / owner / privacy / safety) — 모든 필드에 `source_owner` 태그를 붙인다. `routing_target`·`discoverability`·safety verdict는 Memory 본체가 아니라 owner/privacy/safety 소유일 수 있어, 책임 경계가 흐려지지 않게 한다. (§9.3 observed=Memory / prior=Persona, §11 eligibility와 일관)
- **nullable · confidence · freshness · versioning** 규칙
- `anchor_id`가 가리키는 **KG/QID vocabulary**의 의미 (→ §6.4)
- producer-side anchoring과 query-side linking이 **같은 disambiguation 기준**을 쓰는가

contract에는 **버전**을 박고, 그 버전을 fixture·contract test와 묶는다. 통합 때 "어느 계약 버전 기준인가"가 흐려지면 mock→real 교체가 다시 추측이 된다.

### 6.3 Fixture dataset — 가드에서 역산한 회귀 세트

happy-path 샘플이 아니라, directions·Roadmap에 흩어진 주요 리스크·가드에서 역산한다.

원칙은 간단하다: **가드 하나당 그걸 깨는 fixture 하나**를 둔다. 예: directions §10 가드 표, directions §1.2 maturity gate, directions/Roadmap §4 freshness/contested axis, directions/Roadmap §11 eligibility.

그러면 fixture set이 곧 설계 불변식의 회귀 테스트가 된다. mock 데이터가 너무 예쁘면 Discovery/Recommendation이 실제보다 잘 되는 것처럼 보이므로, 험한 케이스를 기본 포함한다.

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

### 6.4 QID는 스키마가 아니라 의미 계약 (Alpha 선결, mock과 별개)

`anchor_id: "Q123"` 같은 **필드 모양**은 contract test로 검증되지만, "이 QID가 같은 개념을 가리키는가"는 **mock으로 숨길 수 없다** (모양은 맞는데 값이 다른 QID). 따라서 QID **vocabulary · fallback · ambiguity · alias/redirect** 처리 기준은 contract test와 별개 트랙으로, **Alpha 선결 합의**로 둔다. §5의 anchor vocabulary 정렬 리스크와 동일한 문제다.

### 6.5 Decision-log from day one

실제 feedback이 없어도, 추천 한 번마다 **어떤 입력으로 어떤 후보가 왜 살아남고 탈락했는지** 로그를 남긴다. 이게 Open Beta 평가·threshold 튜닝·off-policy 평가(§3.2)의 선행 데이터가 된다.

### 6.6 통합 = 교체

실제 팀 API가 나오면 mock provider를 real provider로 바꾸고, **같은 contract test를 실제 데이터에 돌린다.** mock 단계에서 인터페이스·계약 버전·fixture 가드를 지켜왔다면, 통합은 rewrite가 아니라 교체 + integration test다.

## 7. Open Questions (→ 별도 `technology_selection` 문서, deep research 대상)

- entity linker 비교: ReFinED vs BLINK vs OpenTapioca/Falcon (Wikidata 적합성·라이선스·성숙도)
- KG access 방식: 라이브 WDQS vs 로컬 dump/local store
- edge store 선택: Postgres vs graph DB vs Vespa(retrieve+filter+rank 통합 시)
- vector infra 도입 조건: 언제부터 embedding·ANN이 필요한가
- evaluation stack 선택: 자체 metric vs Evidently, off-policy(OBP) 도입 시점
