# Agent Discovery & Recommendation — 방향·관점 정리 (working base)

> 이 문서는 Agent Discovery & Recommendation의 **설계 기준 베이스(working base)**다. 아직 확정 스펙은 아니며, 어떤 렌즈로 볼지·어디를 파야 할지를 합의하면서 다듬는 살아있는 문서다. `[결정]`·`[경계]`·`[deferred]`·`(초안)` 표기로 확정/미확정을 구분한다.
>
> 메모리 구조는 `Agent_Memory_Vision.md`(L0 Record → L1 Capsule → L2 Personal Knowledge → L3 Public Knowledge)를 **확정 전제**로 둔다.
>
> **이 문서가 앞으로의 기준 베이스다.** 기존 discovery 자산(`agent_discovery_service_contract.md`, `agent_matching_candidates_for_mvp.md`, `agent_persona_extraction_and_representation.md`, 메인 문서 7~8장)은 **참고용으로만** 남긴다 — 마이그레이션·재매핑 대상이 아니라, 개념 출처(lineage)일 뿐이다. 본문에서 그 문서들의 용어(`DiscoverablePerspective`, AgentTopicPerspective 등)를 인용하는 것은 계약상 의존이 아니라 계보 표시다.

### 문서 구성 (읽는 법)

| 묶음 | 절 | 무엇 |
|---|---|---|
| **왜·무엇 (배경)** | 0~2 | 전제 / 두 모드(pull·push) / need 6유형 |
| **어떻게 갈까 (전략)** | 3~5 | need↔메모리 매핑 / 기존 recsys 비교 / 재활용 vs 신규 |
| **설계 핵심** | 6 | 표현·인덱싱(6.1~6.9) · 목적함수·need(6.10~6.11) · 피드백(6.12) |
| **흐름** | 7 | 모드 A·B end-to-end 파이프라인 |
| **요청** | 8 | memory·persona 팀 입력 계약 ← **핵심 결과물** |
| **남은 것** | 9 | 미결정·다음 작업 |

> 표기: `[결정]`=확정 원칙, `[경계]`=다른 팀/모듈 소관, `[deferred]`·`(초안)`=미확정.

---

## 0. 전제

- **메모리 구조 확정** — 4계층(L0~L3). discovery가 닿는 1차 substrate는 **L3 public anchor(Wikidata QID 정렬) + anchor↔개인 node link**다.
- **Privacy는 일단 배제** — 승급 게이팅·익명화·권한 link는 나중에 덧붙인다. 지금은 "무엇이 발견 가능한가"의 *모양*만 본다.
- **anchor↔개인 link는 "공통사실 승급" 규칙에 묶이지 않는다** — 공통 사실 승급(L3 ④)은 *여러 개인이 공유하는 shared facts*에 대한 규칙이고, anchor↔개인 link는 *개인별 발견 포인터*다. 따라서 이 link에 관점·입장 같은 정성 콘텐츠를 얹어도 규칙 위반이 아니다. (= 옛 Perspective Card의 자연스러운 거처)

---

## 1. 발견·추천의 두 모드

같은 엔진을 쓰되 **트리거와 입력이 다르다.**

| | 모드 A — 명시적 요청 (pull) | 모드 B — 맥락 기반 추천 (push) |
|---|---|---|
| 트리거 | 유저가 "이 주제로 얘기할 agent 추천해줘" | 대화 흐름 속에서 시스템이 필요를 **감지** |
| 입력 | 유저가 준 토픽/의도 | 대화 맥락에서 **토픽 추출** + **필요(need) 추론** |
| UX | 후보 리스트 제시 | 대화 중간 인라인 제안 |
| 정밀도 요구 | 보통 (유저가 골라봄) | **높음** — 끼어드는 거라 틀리면 방해 |
| 기존 recsys 대응 | 검색/IR + expert-finding | conversational + context-aware recsys |

모드 B가 어려운 핵심 이유: **"무슨 필요인지"를 먼저 분류**해야 한다. 이 need 분류가 우리 설계의 심장이다(아래 §6.10에서 목적함수로 이어진다).

---

## 2. 모드 B의 필요(need) 유형

### (1) 관점이 필요한 경우 — 유저의 현재 입장 대비 *방향*으로 갈림

- **대립 (against)** — 반대·도전. devil's advocate, stress-test. "다르게 보는 사람"
- **강화 (for)** — 동조·지지. 근거 보강, 더 잘 벼린 같은 입장. "내 생각을 받쳐줄 사람"
- **직교 (orthogonal)** — 찬반이 아니라 **안 보던 새 축/프레임**. 가장 가치 있는데 가장 감지가 어렵다.

### (2) 관점이 아닌 경우 — 대화 중에도 자주 생기는 다른 결의 필요

- **깊이·전문성 (knowledge gap)** — 토픽이 유저/자기 agent 지식보다 깊어짐. expert routing이 대화 속에서 발동.
- **경험 (experience)** — 추상 지식이 아니라 **직접 해본/겪은 사람**. 깊이와 다름 — 구체 episode.
- **유사성 (similar-other)** — 취향·상황이 비슷한 또래. "이런 거 좋아하는 사람은 또 뭘 좋아하지" 식 추천.

### (3) 정보를 넘어선 연결 — (옆에 둠)

"이 사람 소개받고 싶다/같이 하고 싶다"(invite·networking). discovery라기보다 **런타임 액션** 쪽(`archive/agent_event_driven_architecture.md` 소관).

---

## 3. need → 메모리 레이어 매핑

각 필요가 메모리 구조의 **다른 부분**에 기댄다. 이게 나중에 "edge에 무슨 메타데이터를 담을까"를 역으로 정해준다.

| 필요 | 라우팅 근거 (메모리) |
|---|---|
| 깊이·전문성 | L3 anchor + depth/freshness 메타데이터 (사실 측) |
| 대립/강화/직교 관점 | L2 의견·stance (의견 측) |
| 경험 | L1 Capsule / L0 Record provenance (겪은 episode) |
| 유사성 | persona/취향 프로파일 (별도 축) |

---

## 4. 기존 recommendation system과의 비교

### 빌려오는 것 (구조는 표준)

| 기존 recsys | 우리 substrate에서 |
|---|---|
| 2단계: candidate generation → ranking | anchor 기반 retrieval → 다신호 ranking |
| **KG-based recsys** (KG 임베딩 + path 추론) | L3 anchor 그래프와 거의 완벽히 맞음 |
| content/knowledge-based (cold-start 강건) | interaction 이력 없어도 L3 메타데이터로 "이 토픽 깊이 안다" 판단 |
| learning-to-rank | 피드백 쌓이면 랭킹 학습 |
| diversity/serendipity re-ranking | 단, 부차 제약이 아니라 **1급 목적**으로 승격 |

특히 **KG-based recommender가 천연 핏**이다: (1) cold-start 강건, (2) **path 기반 설명가능성**(anchor→개인 node→evidence). 둘 다 provenance 메타데이터로 공짜로 얻는다.

### 근본적으로 다른 것 (그대로 쓰면 깨짐)

1. **목적이 종종 유사성이 아니라 반-유사성이다.** 기존 recsys는 affinity 최적화(→ 필터버블). 우리 need는 스펙트럼을 다 걸침: **강화(for) = 기존 affinity recsys 그 자체**, **대립/직교 = 의도적 anti-recsys**. 목적함수의 부호가 need에 따라 바뀐다 → 단일 relevance score로 못 묶음.
2. **아이템이 정적 product가 아니라 대화형·생성적이다.** 영화처럼 미리 별점 매길 수 없고 *대화해봐야* 가치가 정해짐 → value 측정·피드백이 비고전적(6.10⑥과 연결). ⚠️ 이건 *interactive item* 문제이지 **two-sided matching이 아니다** — 현 스코프는 그 사람이 publish해둔 관점을 agent가 대신 내어주는 **agent-매개 *소비*(콘텐츠/크리에이터 추천 모델)**라, 상대편 사람이 실시간 루프에 없다. two-sided/reciprocity는 사람-대-사람 *연결(invite)*을 지향할 미래에만 재등장(런타임/연결 need로 분리, §2(3)). 주인의 의향은 publish 게이트(privacy와 함께 deferred)가 흡수.
3. **피드백이 희소·지연·모호하고 engagement가 함정.** engagement를 naive하게 최적화하면 편안한 강화 관점만 추천 → 모드 B의 diversity 목적이 붕괴.
4. **설명가능성이 필수.** "비슷한 사람들이…"(CF 블랙박스)는 관점 추천에서 안 먹힘 → KG path 설명으로 귀결.

---

## 5. 재활용 vs 신규 — 레이어로 가른다

**결론: "새로운 문제, 기존 부품(new problem, old parts)".** 기존 recsys를 블랙박스로 통째 wrapping하는 게 아니라, **부품(검색·랭킹 기계장치)은 재활용하고 그 위에 두꺼운 정책 레이어를 새로** 쌓는다.

근본 차이는 스택 전체에 고른 게 아니라 **위층(목적·의도·오케스트레이션)에 몰려 있다.**

| 레이어 | 차이 있나 | 판단 |
|---|---|---|
| ANN/벡터 검색, KG 임베딩, 인덱스 | 없음 | **그대로 재활용** |
| 2단계 retrieve→rank 골격 | 없음 | **그대로 재활용** |
| learning-to-rank 기계장치 | 없음 | **재활용** |
| 목적함수 (무엇을 최적화) | 있음 (affinity↔diversity 부호) | **새로** |
| intent/need 레이어 | 있음 (기존엔 거의 없는 층) | **새로** |
| 피드백 해석 (engagement 함정) | 있음 | **새로** |
| 오케스트레이션 (언제 끼어드나) | 있음 | **새로** |

### 블랙박스 wrapping이 깨지는 결정적 이유

wrapper는 **하위 retrieval이 이미 꺼내온 후보만 재정렬**할 수 있다. 기존 recsys는 affinity 기준으로 후보를 뽑으므로, 임베딩 공간에서 멀리 있는 **대립·직교 후보는 애초에 후보 집합에 안 들어온다.** 꺼내오지 않은 걸 재정렬할 수 없다 → diversity 목적은 얇은 wrapper로 해결 안 되고 **retrieval 층 자체가 diversity-aware**해야 한다. 즉 목적함수가 최하위 검색 층까지 새어 내려간다.

반대로 **강화(affinity)·깊이(expertise) need는 기존 recsys가 잘하는 영역**이라 재활용 비중이 높다.

### Phasing 함의

- **1차 (재활용 비중 높음, 저위험)**: 강화·깊이 need — 거의 표준 recsys 부품으로 빠르게.
- **2차 (신규 구축, 차별점)**: 대립·직교 관점 + 대화 중 끼어들기 — 의도적으로 새로 설계.

---

## 6. 설계 핵심 — 표현·인덱싱 · 목적함수 · 피드백

> 구성: **6.1~6.9 표현·인덱싱**(토픽 ⊥ 입장 ⊥ global persona 3층, 쟁점 축, descriptor) · **6.10~6.11 목적함수·need** · **6.12 피드백**.

### 6.0 표현·인덱싱의 출발점 — 토픽 ⊥ 입장 분리

diversity-aware retrieval은 모드 A·B 공통이지만, 공통의 진짜 핵심은 "diversity 알고리즘"이 아니라 **토픽과 입장을 분리된 축(차원)으로 표현**하는 것이다. (여기서 "축"은 좌표축처럼 *위치를 잴 수 있는 차원*을 뜻한다 — 예: "산미 ↔ 바디" 같은 선호의 차원.) 한 임베딩에 엉키면 모드 A는 커버리지 실패, 모드 B는 "같은 토픽 반대 입장"을 아예 못 한다.

### 6.1 3층 표현

| 층 | 단위 | 무엇 | 질문 |
|---|---|---|---|
| **토픽 축** | anchor | QID + KG 임베딩 | *어디(where)* |
| **국소 stance** | edge (anchor↔개인) | 그 anchor 쟁점 축 위의 위치 | *여기서 무슨 입장(what here)* |
| **global persona** | agent 노드 | 안정적 성향 + 스타일 (= stable core / Global Profile / persona brief, 같은 것) | *대체로 어떻게 생각/말하나(how in general)* |

### 6.2 전역 stance 공간은 없다 — anchor별 국소 공간이다

"반대"는 같은 토픽 안에서만 정의된다("anti-커피"와 "anti-재택"은 같은 축이 아니다). 하나의 글로벌 입장 공간을 만들지 않는다. 대신:

- **anchor 층 (공유)**: 그 토픽의 **쟁점 축**(= 사람마다 *의견이 갈리는 차원*; contested dimensions) = 국소 stance 공간의 정의. *다수의 입장을 모아* 도출.
- **edge 층 (개인)**: 이 사람의 그 공간 안 **좌표** + stance descriptor + provenance.

(비전 L3 = 공유 anchor + 개인 link 구조 그대로)

### 6.3 표현: 연속 + 상징 하이브리드

| 형태 | 무엇 | 강한 곳 |
|---|---|---|
| **연속: topic-conditioned perspective embedding** | 토픽 성분 제거한 입장 *잔차* 벡터 (국소 공간) | **for/against** (벡터 유사도 부호) |
| **상징: stance descriptor / 쟁점 축** | "무엇에 대해 어떤 입장"의 구조화 | **orthogonal** + **설명가능성** |

- for/against ↔ 연속 벡터 / orthogonal ↔ 상징 쟁점 축(유저가 안 선 다른 축으로 전환). orthogonal은 임베딩 기하의 "수직"이 아니라 "다른 프레임"이라 상징이 더 잘 잡는다.
- ⚠️ 입장 텍스트를 그냥 임베딩하면 토픽 성분이 다시 섞여 들어감 → "topic-conditioned(토픽 성분을 뺀 잔차)"가 disentanglement의 핵심 난점.

### 6.4 인덱싱·연산

- **파티션 = anchor.** anchor로 좁히고(QID 매칭 + KG 이웃 확장) 파티션 *안에서* stance 연산. (matching "검색 단위 = agent-topic perspective", active-set과 일치)
- **모드 A (cover)**: 국소 stance 공간 클러스터링 → 대표들 고르게 샘플 = 관점 커버리지.
- **모드 B (direct)**: 유저 현재 입장을 국소 공간에 놓고 → for=최근접 / against=반대부호 / orthogonal=다른 쟁점 축.

### 6.5 global persona = prior (보완), override 아님

global persona는 토픽 무관 agent-level 성향이고, 토픽 stance의 **사전(prior)**이다. 관찰이 충분하면 토픽-특화 stance가 우선:

> **effective stance(A)** = blend( global persona를 A에 투영, A에서 관찰된 stance ), 가중치 = `topic_specificity = maturity × consistency`

이게 두 구멍을 메운다:
- **cold anchor 해결** — 관찰 희소 시 global persona가 예상 입장을 채우는 prior.
- **disentanglement 잔차 정의** — 토픽-특화 stance = 관찰 입장 − (global persona 투영 예측) = 그 사람 baseline 대비 *놀라움(surprise)*.

일부 need에선 global persona가 *주축*: **유사성**(닮은 사람 = global persona 유사도 primary), **orthogonal**(유저 자신의 global persona = 기준 프레임), **스타일 매칭**(단 MVP 랭킹 제외, advisory만).

### 6.6 [결정] prior ⊥ maturity — 분리 원칙

> **"예상 입장(predicted stance)"과 "대화에서 얻을 가치(conversation value)"는 다른 양이다.** prior는 *어디에 설지·후보 자격*은 채우되, *대화하면 뭘 얻을지*는 채우지 못한다.

규칙: **prior는 stance를 채우되 maturity는 절대 채우지 않는다.**
- **stance 추정** ← global persona prior 사용 가능.
- **`topic_knowledge_maturity`** ← **관찰된 실제 engagement만.** prior로 부풀리면 대화 가치를 속이는 셈.
- prior-채운 stance는 *추정 신뢰도*는 높아도 `topic_knowledge_maturity`는 낮은 상태가 정상 (둘은 따로 논다).

스코어링 귀결:
- **eligibility/방향**(후보 자격, for/against/orthogonal) — prior 기여 OK.
- **value/추천 점수** — **maturity가 floor(하한 게이트) + 큰 가중치.** prior가 확신해도 관찰 없으면 value는 바닥 → hollow agent가 상위로 구조되지 않음.

미세조정:
- **gain = depth + novelty.** maturity ≈ 0이면 "다른 프레임"조차 prior 추측(hollow)이라 floor는 필요. 단 floor 위에서 maturity만 과하게 쥐면 신선·직교 목소리를 죽여 diversity와 충돌 → **maturity는 하한이지 정렬의 전부가 아님.**
- **maturity 가중치 자체가 need-조건부.** 깊이(expert) need → maturity ≈ 게이트. 유사성/peer(co-explore) need → 둘 다 초심자여도 함께 탐색 가치, maturity 덜 중요. (= "목적함수가 need에 따라 바뀐다"의 일부)

### 6.7 anchor 쟁점 축(contested axes) 도출

6.2의 "anchor 층 = 쟁점 축"을 어떻게 만드는가. 국소 stance 공간 전체가 여기 의존한다.

**핵심: 쟁점 축은 "공통사실 승급"의 반대편 — 같은 인구 집계의 두 출력.**

> anchor에 모인 다수의 입장에서 **합의(converge) → 공통사실**(비전 §4④), **불합치(diverge) → 쟁점 축.** 별도 파이프라인이 아니라 같은 집계의 두 출력. ("모두 동의 = 사실, 갈라짐 = 축"이라는 경계가 공짜)

**쟁점 축이란:** 그 토픽에서 실제로 갈라지는 *쟁점*. 양극/스펙트럼을 가짐. **anchor당 여러 개(다차원)** — orthogonal need는 축 ≥2여야 성립하므로 평면 클러스터링(축을 뭉갬)은 부적합. **상징(이름) + 선택적 연속**, edge는 입장 가진 축에만 좌표(나머지는 prior로 채움).

**도출 방법 — anchor 성숙도에 따라 계층적:**

| 성숙도 | 방법 |
|---|---|
| cold/young | **LLM 추론** — 가용 입장에서 "갈라지는 쟁점과 양극은?" → 이름 붙은 축. 소수로 작동·설명가능, 불안정 |
| mature | **aspect 추출 + 축별 divergence**, 또는 **ideal-point/잠재요인 분해**(정치학 NOMINATE/IRT 동형 — 입장에서 잠재 대립 차원 복원) 후 LLM 명명. 안정·다중 직교축 |

**cold-start — KG 활용:** 입장 0~1개면 축 미정의 → **KG 부모/이웃 anchor에서 축 상속**(Wikidata 위계 payoff). 교차-anchor 축(예 "정통성 vs 편의")은 상위 anchor에 달고 하향 상속 — cold-start·orthogonal 둘 다 도움. LLM 세계지식으로 *잠정 축* 생성 후 실제 입장으로 확정/수정.

**prior ⊥ maturity 규율 적용:** 상속·LLM추측 축은 **잠정(provisional)** — placement(candidacy)엔 쓰되 확정 구조 행세 금지. 축에 **source 태그**(`observed`/`inherited`/`world-knowledge`) + **최소 divergence 질량** 넘어야 `established`(거짓 논쟁 제조 방지). stance의 `extraction_confidence`를 축 confidence로 전파. 잠정 축이어도 추천 value는 관찰 maturity가 게이트.

**변화 관리(시간에 따른 갱신):** 축 생성·병합·분할(contract topic merge/split 정신). **`stance_space_version` per anchor**(global_profile_version의 anchor판), 축 변경 시 edge 좌표 재계산, **debounce + active-set**으로 잦은 재계산(thrashing) 방지.

**연산 연결:** orthogonal = 유저가 입장 안 잡은 축에서 강한 보유자(축 없으면 계산 불가) / cover = 각 축 양극 샘플 / for·against = 유저가 선 축의 같은·반대 극.

> **권고(MVP):** stance 인구에서 **LLM 추론으로 이름 붙은 다중 축 + 양극**, divergence 질량으로 established↔provisional 태그, 희소 시 **KG 상위 anchor 상속**. ideal-point/요인분해는 규모 차면. 축은 **discovery 소유 anchor-level 구조** + `stance_space_version` 관리.

### 6.8 stance descriptor 스키마 (edge T2)

edge(anchor↔개인)에 담는 것. 새로 만들지 않고 contract `DiscoverablePerspective`를 이 substrate에 맞게 **정련**한 것이다.

**핵심 구조 — edge는 두 얼굴(L2 사실/의견 분리를 상속):**

| 얼굴 | 무엇 | need | 6.6 관계 |
|---|---|---|---|
| **knowledge face** (사실/깊이) | maturity·evidence·provenance | 깊이/expert, 경험 | **value/게이트** (관찰만) |
| **stance face** (의견/입장) | 축 좌표·stance 요약·useful_for | 대립/강화/직교 | **estimate** (prior 채움 가능) |

→ maturity(knowledge) ⊥ stance estimate(stance)가 다른 얼굴이라 **스키마에서 구조적으로 분리**된다.

**필드 ([MVP]/[later]):**

- endpoints: `anchor_id` ↔ `agent_id`
- **knowledge face (prior 금지, 관찰만)**: `topic_knowledge_maturity`(value 게이트)[MVP] · `evidence_strength`·`freshness`(decay)[MVP] · `evidence_refs`→[L2/L1/L0 포인터] (provenance·KG-path 설명·경험 need 근거, payload 아님)[MVP]
- **stance face (prior 채움 가능)**: `stance_summary`(상징 텍스트, MVP for/against 서빙 비교)[MVP] · `useful_for`(tags)[MVP] · `axis_positions[]` = `{axis_id, value(극/스칼라), value_confidence, source: observed|prior, evidence_refs}`[MVP coarse→later full] · `perspective_embedding`(topic-conditioned 잔차)[later] · `estimate_source`/`estimate_confidence`(observed↔prior, maturity와 분리)[MVP]
- **versions/handoff**: `stance_space_version`·`global_profile_version`(stale 관리)[MVP] · `routing_target`(agent-level 핸드오프 참조)[MVP]

**옛 DiscoverablePerspective → 정련 5가지:** (1) `topic`(hint) → `anchor_id`(권위 QID) · (2) `claims_or_stances`(자유형) → `stance_summary`+`axis_positions`(구조화) · (3) `style_descriptors` → agent 노드(global persona)로 이동, edge에서 제거 · (4) `confidence`(단일) → `estimate_confidence` ⊥ `topic_knowledge_maturity`(분리) · (5) observed↔prior 명시.

> **MVP 최소형:** `{anchor_id, agent_id}` + knowledge `{maturity, evidence_strength, freshness, evidence_refs}` + stance `{stance_summary, useful_for, axis_positions(coarse), estimate_source, estimate_confidence}` + `{stance_space_version, global_profile_version, routing_target}`. 임베딩·full 축 좌표는 later.

원칙 재확인: **edge=topic-specific만 / global persona·style은 agent 노드 / payload 아니라 thin 요약 + L2 포인터.**

### 6.9 MVP phasing — 상징 우선, 임베딩 나중

위 표현·인덱싱(6.1~6.8) 전체를 MVP에서 어디까지 만들지 좁힌 범위.

> **MVP**: 토픽 = anchor QID(상징 검색 + KG 이웃 확장). 입장 = edge의 **stance descriptor(상징)**. for/against는 서빙 시점에 유저 입장 대비 **LLM/텍스트 비교**로 판정(disentangle 임베딩 불필요, 싸고 설명가능). 모드 A 커버리지 = stance descriptor 클러스터링.
>
> **다음 단계**: 규모 요구 시 topic-conditioned perspective embedding 추가(확장 가능한 for/against), anchor 인구에서 쟁점 축 도출을 정교화(6.7, orthogonal).

이유: disentangled 임베딩에 처음부터 베팅하는 건 위험(연구 난제)하고, 상징 descriptor + 서빙 비교가 더 견고·설명가능 — 설명가능성 1급 요구와 일치.

### 6.10 need 분류 → 목적함수 매핑

thesis "**목적함수의 부호·형태가 need에 따라 바뀐다**"의 구체화. **need는 discovery의 입력 파라미터**다(누가 분류하는지는 6.11).

**통합 템플릿 — 게이트 + need-매개 가중합** (matching "hard filter + weighted sum", 곱셈 아님):

> **score_need(후보 | 유저, 질의)** = **게이트**: on-topic ∧ (maturity ≥ `floor_need`) ∧ eligibility → **가중합**: `α·stance_term + β·maturity + γ·freshness + δ·persona_sim + ε·experience + ζ·novelty`

need가 정하는 것은 둘뿐: **(a) stance 연산(어느 축·어떤 부호), (b) 가중치 벡터와 floor.**

| need | 검색 방향 | stance 연산 | 지배 신호 | maturity | 기존 recsys |
|---|---|---|---|---|---|
| **깊이** | anchor(+이웃) | — | maturity, evidence | **목적 자체** | expert rank — 재활용 |
| **강화** | anchor+**같은 축** | **+alignment** | stance_align(+), maturity | 신뢰성 게이트 | affinity CF — 재활용 |
| **대립** | anchor+**같은 축** | **−alignment(거리)** | opposition, **maturity(신뢰성)** | **신뢰성 담보** | **신규** |
| **직교** | anchor+**다른 축** | off-axis 강도 | off_axis_strength, maturity | 게이트 | **신규** |
| **경험** | anchor+episode | — | experience_specificity, 상황매치 | *경험적 깊이*로 재정의 | case-based 일부 |
| **유사성** | **persona 유사**(agent) | — | persona_similarity | **완화**(peer) | content/CF — 재활용 |

**핵심 통찰:**
- **① stance 항 부호가 뒤집힌다(강화 + / 대립 −)** — 단일 relevance score로 둘 다 못 섬김. thesis의 핵심.
- **② maturity = 거의 보편 게이트, 역할은 need마다 다름. 그리고 diversity의 안전장치.** 대립/직교에서 maturity는 신뢰성 floor — *"최대한 반대"가 아니라 "신뢰할 만한 반대"* 보장 → fringe·troll·랜덤 붕괴 방지.
- **③ 진짜 신규는 대립·직교 둘뿐.** 나머지는 재활용 → §5 phasing 확증. 신규의 정체 = (a) 같은 축 반대극 retrieval, (b) 축-전환 retrieval. 둘 다 6.7 축 의존.
- **④ mode × need 호환성** — 강화/대립/직교는 유저 입장(참조점) 필요 → **본질적으로 모드 B**. 깊이/경험/유사성은 참조점 불필요 → **두 모드 다**.
- **⑤ 모드 A 기본 = coverage** (need 미지정 시 stance 공간 고르게 덮기 + 고-maturity 혼합).
- **⑥ 피드백도 need-특이적** — 강화는 engagement가 proxy OK, 대립/직교는 오도(가치 있는 도전은 짧고 불편). 피드백 모델 need-aware.

정합: 게이트=hard filter, 나머지=weighted sum (matching 그대로). contract baseline(`relevance × confidence × freshness`)의 **agent entity_type 특화형**.

### 6.11 [경계] need 감지는 discovery 밖 — agent moderation 소관

**need를 *무엇이* 분류하는지는 discovery가 소유하지 않는다.** 대화 맥락에서 "지금 어떤 need인가"를 판단하는 것은 **agent moderation(런타임)** 영역(`archive/agent_event_driven_architecture.md`)이며, 아직 형태는 미정이지만 **어떤 형태로든 정해질 것이고 need가 구분된(typed) 요청으로 discovery에 들어온다.**

→ discovery 입장에서 need는 **주어진 입력 파라미터**다(6.10 그대로). 따라서 query-side 계약에 `need_type`이 추가된다(producer-side 계약 `DiscoverablePerspective`와 대칭). 모드 A는 유저가 need를 고르거나 미지정(→coverage), 모드 B는 moderation이 추론해 typed로 전달.

### 6.12 피드백 모델 (need-aware)

추천 생애주기 funnel — 단계마다 신호, 각 함정 주의:

| 단계 | 신호 | 측정 | 함정 |
|---|---|---|---|
| 노출→**선택** | acceptance (얼마나 골라 대화 시작) | 카드 표면 매력 | 대화 value 아님, position·인기 편향 |
| 선택→**대화 길이** | turns/지속 | engagement | **need 함정**: 대립/직교는 짧아도 좋음 |
| 대화 중→**만족도 추출** | implicit sentiment | 즉시 반응 | friction≠나쁨, 최적화 시 **sycophancy 드리프트→강화만 생존** |
| 종료→**명시 피드백** | 1-tap 평가 | ground-truth-ish | 희소·UX 비용·peak-end 편향 |

**결정적 신호 — 사후 메모리 임팩트 (우리 substrate라 가능):**

> 추천 대화 *후* 유저 L2(지식·스탠스)가 실제로 바뀌었나. comfort/duration이 아니라 **outcome(학습·변화)**을 재므로 engagement 함정 우회.

- **proxy 아니라 미션 지표** — "남의 관점 소비로 내 지식이 자란다"는 제품 목적 그 자체.
- **attribution 가능** — 그 대화의 L0/L1 Capsule → 산출 L2 node를 provenance로 추적해 특정 추천에 귀속.
- **need별 typed** — 깊이→새 사실 node / 직교→비었던 축에 새 입장 / 대립→기존 스탠스 수정·정교화.
- ⚠️ **gaming 가드** — "변화 최대화"는 정보폭탄·스탠스 교란을 보상 → **durable + validated(되돌려지지 않고 유저 calibration 통과한) 변화만** 인정(추출 문서 round-trip과 연결).
- **느린 신호** — 빠른 implicit(선택률·길이)을 선행지표로, 임팩트는 이를 재보정하는 느린 ground-truth로.

**두 원칙:** (1) **"골랐나(acceptance) ≠ 좋았나(value)" 분리** — 선택률은 카드 랭킹, 임팩트/명시평가는 대화 value 학습. (2) **need별 가중 + sycophancy 가드** — 추천마다 `need_type`이 붙으므로(6.11) need-조건부 집계; 강화는 만족도·길이 OK지만 **대립/직교는 메모리 임팩트로만 평가**(comfort 신호 금지). 명시 피드백은 implicit를 calibration하는 희소 ground-truth, need에 맞게 질문 프레이밍.

> **MVP:** acceptance + 대화 지속(기본 implicit) + 종료 시 1-tap need-프레이밍 평가(희소 ground-truth). 2차: 메모리 임팩트(L2 변화)를 value 신호로 — 대립/직교 평가의 본선. 모든 신호 `need_type`별 분리.

---

## 7. 모드 A·B 실제 흐름

두 모드는 **같은 엔진**을 쓰되 *입력 획득·정밀도·서빙*이 다르다.

### 7.1 공통 엔진 (7 stage)

```text
① 입력 정규화   : (topic, need_type, user_stance_ref?, user_persona)
② anchor 해소   : topic → Wikidata QID + KG 이웃 확장
③ 후보 retrieval: 해당 anchor 파티션의 edge(stance descriptor) 끌어옴
                  + 하드 게이트 (on-topic ∧ maturity≥floor_need ∧ eligibility)
④ stance 연산   : need별 — for=같은축 근접 / against=같은축 반대극 /
                  orthogonal=다른축 / 깊이·경험·유사=stance 스킵
⑤ 랭킹          : 6.10 need-매개 가중합 + intra-list diversity
⑥ 서빙          : 후보 + KG-path 설명 (모드별 surface 다름)
⑦ 피드백 로깅   : acceptance → (길이·만족도·메모리 임팩트), need_type·mode 태그
```

reuse 매핑: ②③ = candidate generation, ④⑤ = ranking (§5 2단계 골격). ④의 for/against/orthogonal이 §5에서 말한 **신규 retrieval**(나머지는 재활용).

### 7.2 모드 A — 명시적 pull

> 유저가 "이 주제로 얘기할 agent 추천해줘"

1. 질의에서 **topic + (선택) need** 추출. need 미지정이 기본.
2. anchor 해소(②) → 후보 retrieval·게이트(③).
3. **need 분기**:
   - 미지정 → **coverage**: stance 공간 클러스터링해 축별 대표 + 고-maturity 혼합.
   - 참조점 불필요 need(깊이/경험/유사) → 해당 목적함수.
   - 유저가 요청에 입장을 밝혔으면 → for/against/orthogonal 가능.
4. 랭킹·리스트 다양화(⑤) → **후보 리스트로 제시**(설명 포함).
5. 유저 선택 = acceptance → 대화 시작 → 사후 피드백.
- **항상 best-effort 리스트 반환.** 정밀도 바 낮음(유저가 걸러봄).

### 7.3 모드 B — 맥락 push

> 대화 중 moderation이 need를 감지해 typed 요청 발행

1. moderation이 typed 요청 발행: `{topic(맥락 추출), need_type, user_stance_ref, user_persona}`. **여기서 참조점(유저 현재 입장)이 들어온다** → for/against/orthogonal이 사는 곳.
2. anchor 해소(②) → retrieval·게이트(③). maturity floor가 **hollow agent의 끼어듦을 차단**.
3. stance 연산(④): need대로. orthogonal은 user_persona를 기준 프레임으로 "유저가 안 선 축" 선택.
4. 랭킹(⑤) 후 **높은 정밀도 바 + 침묵 옵션**: 최상위 후보가 바를 못 넘으면 **추천하지 않고 침묵**(약한 추천으로 끼어들지 않음). 보통 top-1~소수.
5. 통과 시 **대화 내 인라인 제안**(유저 자기 agent가 프레이밍) → 수락 시 핸드오프 → 사후 피드백(메모리 임팩트 포함).
- **추천 또는 침묵**의 종단 분기가 모드 A와 결정적으로 다름.

### 7.4 차이 요약

| | 모드 A (pull) | 모드 B (push) |
|---|---|---|
| 트리거 | 유저 명시 요청 | moderation 감지 |
| 입력 제공 | 유저 | moderation (typed) |
| stance 참조점 | 보통 없음 | **있음**(맥락) |
| 가능 need | 깊이/경험/유사 + (입장 밝히면) 관점 | **전부**(대립/직교 포함) |
| 후보 수 | 리스트 | top-1~소수 |
| 침묵 옵션 | 없음(best-effort) | **있음**(바 미달 시) |
| surface | 후보 리스트 UI | 대화 내 인라인 |
| 기본값 | coverage | need별 목적함수 |

### 7.5 경계 (분업)

- **moderation/런타임**: 모드 B의 need 감지·참조점 추출(6.11), 그리고 수락 후 **추천 agent를 대화에 어떻게 끌어들이나**(side-thread? 자기 agent가 중계?)의 오케스트레이션.
- **discovery**: ②~⑤ + 침묵 판정. **랭킹된 후보 + `routing_target` 반환에서 끝난다.** 대화 구동은 넘기지 않는다.
- **feedback(⑦)**: discovery가 로깅·재보정에 사용하되, 메모리 임팩트 산출은 메모리 계층과 협업.

### 7.6 anchor 해소·KG 이웃 확장 (초안 · 미확정, 리뷰 대기)

7.1 ②의 구체화. **대부분 commodity 재활용이고, 설계가 필요한 고유 부분은 3개뿐.**

**하는 일:** anchor 해소 = 질의(A: 유저 텍스트 / B: 대화 맥락) → Wikidata QID grounding(entity linking). 이웃 확장 = 그 QID에 정확히 달린 edge만이 아니라 관련 anchor로 넓혀 관점 회수.

**commodity (재활용, 새 설계 불필요):** entity linking(mention→후보→문맥 disambiguation), ANN, KG 그래프 traverse, hop 거리 감쇠, 임베딩 최근접. = §5 "KG 임베딩·KG retrieval 그대로 재활용".

**프로젝트 고유 (설계 필요) 3개:**

1. **granularity(레벨) 선택 정책** — 질의가 여러 레벨에 매칭될 때 어느 QID를 anchor로 삼나(푸어오버 / 커피추출 / 커피). 너무 구체=cold·희소, 너무 일반=noisy. → cold anchor 문제와 직결, **maturity 밀도가 충분한 가장 구체적 레벨**을 고르는 식의 정책 필요.
2. **aspect → axis 힌트** — 질의가 토픽이 아니라 *쟁점*("커피의 *가성비* 문제")이면 6.7 쟁점 축으로 매핑 → 해소 출력이 `(anchor, axis_hint)`. 모드 B의 for/against/orthogonal이 바로 정확해짐. (우리 stance 모델 고유)
3. **위-확장 = 축 상속 (double duty)** — KG 위로 확장하는 건 recall만이 아니라 **6.7 cold-anchor 쟁점 축 상속과 같은 연산.** 이웃 확장이 후보 회수 + stance 공간 상속을 겸한다. 방향별 의미: 위=일반화/축 상속, 아래=구체화, 옆=대안.

**미해결(리뷰 시 볼 것):** granularity 정책의 "충분한 밀도" 임계, 다중 anchor(교집합 "React ∩ 성능") 결합 규칙, KG에 없는 토픽의 자체 anchor 발행(비전 §4②), 확장 관계 화이트리스트·hop 예산.

---

## 8. memory · persona 팀 요청사항 (discovery 입력 계약)

discovery는 memory/persona projection의 **소비자**다. 아래는 discovery가 동작하려면 그쪽이 *생산·노출*해야 하는 신호와 그 **이유**다.

> **관통 원칙: discovery가 축 도출·confidence calibration·prior-fill·랭킹을 *자체 수행*한다.** 그래서 그쪽은 **정확한 raw 신호**만 주면 되고 가공물(축·점수·prior)을 만들 필요 없다. 무엇을 그쪽이 주고 무엇을 우리가 derive하는지 §8.6에 명시.

**Memory vs Persona 구분 (아래 표의 `소유` 열):**
- **Memory** = *무엇을 아는가* — L0~L3 지식·사실·anchor·provenance·maturity (`Agent_Memory_Vision.md` 소관).
- **Persona** = *어떻게 생각/말하는가* — stable core·advisory·style.
- **애매** = 의견·입장(stance)은 비전상 L2(Memory)에 있으나 persona 추론과도 닿음 → 두 팀이 소유를 합의해야 함.

> **[중요] Memory ↔ 메타데이터 바인딩:** `Agent_Memory_Vision.md` §4③은 anchor→personal-node link에 **언제(temporal)/어떻게(provenance)/얼마나(depth·confidence)** 메타데이터를 단다고 했다. **그 메타데이터는 정확히 이 문서의 edge(stance descriptor) knowledge face와 동일한 것이어야 한다** — 별도·발산하는 메타데이터가 아니라 같은 필드·같은 자리:
> - 언제 → `freshness`
> - 어떻게 → `evidence_refs` (provenance)
> - 얼마나 → `topic_knowledge_maturity` + `evidence_strength`
>
> 즉 vision이 "link 메타데이터에 담아야 한다"고 한 것은 **곧 이 문서의 8.0·8.1을 채우는 것**이다(8.1 표 ★ 표시).

### 8.0 가장 근본 — anchor↔개인 node link (검색 단위) · **소유: Memory**

> 비전 §4③의 **L3 anchor↔personal-node link**를 노출할 것. 각 link는 Wikidata QID에 정렬된 (user, topic) 쌍이다.

- **어디서:** 7.1 ②③ — discovery의 **retrieval 단위 그 자체.**
- **왜:** 이게 없으면 discovery는 아무것도 못 한다. anchor 정렬(personal node → QID)은 비전상 memory 소관이므로 **discovery는 이 정렬에 의존**한다.

### 8.1 link별 — knowledge face (관찰값, **prior 금지**) · **소유: Memory**

★ = `Agent_Memory_Vision.md` §4③의 link 메타데이터(언제/어떻게/얼마나)와 **동일한 것**. vision이 link에 담으라 한 그 값이 곧 이 필드다.

| 파라미터 | 소유 | 어디서 어떻게 | 왜 제공 |
|---|---|---|---|
| ★ `topic_knowledge_maturity` (=얼마나) | Memory | 7.1③ 게이트(floor) + 6.10 β가중(특히 깊이 need) | value·신뢰성 신호. **prior⊥maturity상 반드시 *관찰값* — 우리가 못 위조.** hollow 추천·diversity 붕괴 방지의 핵심 |
| ★ `evidence_volume`·`consistency`·`specificity` (=evidence_strength, =얼마나) | Memory | maturity 산출 입력 + 6.10 랭킹 | 잘 근거된 것 vs 얇은 것 구분 |
| ★ `freshness` (observed_at / last_update, =언제) | Memory | 6.10 γ decay 가중 | evergreen vs stale. cutoff 아니라 decay |
| ★ `evidence_refs` (L0/L1/L2 포인터, =어떻게) | Memory | 7.1⑥ KG-path 설명 + 경험 need + 6.12 메모리 임팩트 attribution | **설명가능성 필수** + 경험 need + 피드백 귀속. payload 아니라 포인터 |
| `experience flag` (episode 여부 + source_type) | Memory (source_type은 Persona와 겹침) | 경험 need retrieval/ranking | 경험 ≠ 깊이. lived episode 구분 필요 (추출의 source attribution) |

### 8.2 link별 — stance face (의견) · **소유: 애매 (Memory L2 의견 ↔ Persona stance)**

> 비전은 의견을 L2(Memory)에 두지만, 토픽별 stance 추출은 persona 추론과도 닿는다. **누가 토픽별 stance를 추출·소유하는지 두 팀이 합의 필요.** 단 discovery는 어느 쪽이 주든 동일한 필드를 받으면 됨.

| 파라미터 | 소유 | 어디서 어떻게 | 왜 제공 |
|---|---|---|---|
| 추출된 **opinion/stance content** per (user, topic) | **애매** | 6.7 축 도출 *입력* + 7.1④ stance 연산 + stance_summary | perspective matching의 핵심. **개별 stance만 주면 됨 — 쟁점 축은 우리가 인구 집계로 derive(§8.6)** |
| `extraction_confidence` | **애매** (stance와 동일 소유) | 6.7 축 confidence 전파 + estimate_confidence | 단정 저장 회피, 각 stance 신뢰도를 알아야 |
| (옵션) `useful_for` 힌트 | 애매 (Persona-쪽, 또는 discovery derive) | need 매칭 강화 | intent 매칭. derive 가능하나 있으면 품질↑ |

### 8.3 agent별 — global persona · **소유: Persona**

| 파라미터 | 소유 | 어디서 어떻게 | 왜 제공 |
|---|---|---|---|
| **global persona** (stable core: thinking style, `advisory_profile`, `conversation_style`) | Persona | 6.5 prior + 6.10 유사성 primary·orthogonal 기준 프레임·effective blend | cold anchor 보완, similar-other, 일반 성향. **advisory는 랭킹 사용 / style은 MVP 제외(나중)** |
| `persona_maturity` + `consistency` | Persona | 6.5 `topic_specificity = maturity × consistency` (prior vs observed 비중) | prior 가중을 제어 — 무르익은 persona일수록 prior 신뢰 |
| `global_profile_version` | Persona | 서빙 시 global persona를 edge에 denormalize (6.8) | denormalize된 값의 stale 식별·재투영 위해 버전 필요 |

### 8.4 lifecycle 이벤트 · **소유: 분리 (Memory + Persona)**

> `publish` / `update` / `revoke` 이벤트.

- **소유:** link·stance lifecycle = **Memory** / global persona lifecycle = **Persona**. 각자 자기 산출물의 변경을 이벤트로 발행.
- **어디서:** 인덱스 일관성·active-set·revoke 처리.
- **왜:** discovery는 source of truth가 아니라 **projection** — 변경 이벤트가 있어야 stale 없이 재투영.

### 8.5 역방향 — 피드백을 위한 L2 변화 노출 · **소유: Memory (stance 이동 부분은 8.2와 동일 애매)**

> 추천 대화 *후* **L2 change delta + provenance**(어느 대화에 귀속되는지) 노출.

- **소유:** 사실 node 변화 = **Memory**. 스탠스 이동(8.2의 의견 측) 변화는 8.2와 같은 **애매**.
- **어디서:** 6.12 메모리 임팩트 신호.
- **왜:** discovery의 **최고 value 신호이자 미션 지표.** durable+validated 변화를 관찰하려면 L2 delta 가시성 필요. (산출은 memory와 협업)

### 8.6 [경계] 우리가 derive — 그쪽이 안 만들어도 되는 것

memory/persona가 **만들 필요 없는** 것(중복 작업 방지):

- **쟁점 축(contested axes)** — 우리가 stance 인구 집계로 도출(6.7). 그쪽은 개별 stance만.
- **confidence calibration** — raw `extraction_confidence`만 주면 정규화는 우리가.
- **prior-fill** — cold anchor 예상 입장은 우리가 global persona로 채움(6.5). 그쪽은 관찰값만.
- **ranking·objective, topic-conditioned 임베딩, stance-space 버저닝** — discovery 내부.

---

## 9. 미결정 / 다음에 팔 것

- **쟁점 축 세부** — established 판정의 divergence 질량 임계, mature 단계 분해 기법 선택, 교차-anchor 축의 위계 부착 규칙.
- **descriptor 세부** — `axis_positions`를 추출 시점에 채우나 서빙 시점 lazy 계산하나, 한 (agent,anchor)에 다중 입장 처리, `useful_for` taxonomy를 need와 정렬, `estimate_confidence`를 topic_specificity에서 도출하는 식.
- **cold anchor fallback 구체화** — prior 비중(topic_specificity) 계산식, floor 임계.
- **목적함수 가중치 튜닝** — 6.10 템플릿의 `α…ζ`·`floor_need` 실제 값/학습(형식은 정해짐).
- **[deferred] two-sided / reciprocity** — 현 스코프 out of scope. 추천 = agent-매개 *소비*(콘텐츠/크리에이터 모델), 상대편 사람이 실시간 루프에 없음. 사람-대-사람 *연결(invite)*을 지향할 미래에만 재등장(런타임/연결 need).
- **피드백 세부** — 메모리 임팩트의 "durable+validated" 판정 구현, need별 가중 학습(형식은 6.12에서 정해짐).
