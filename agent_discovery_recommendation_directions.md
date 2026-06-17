# Agent Discovery & Recommendation — 방향·관점 정리 (working doc)

> 이 문서는 **결정 전 단계의 방향·관점 정리**다. 확정 스펙이 아니라, Agent Discovery & Recommendation을 어떤 렌즈로 볼지·어디를 파야 할지를 합의하기 위한 작업 문서다. 결정된 항목과 미결정 항목을 명시적으로 구분한다.
>
> 메모리 구조는 `Agent_Memory_Vision.md`(L0 Record → L1 Capsule → L2 Personal Knowledge → L3 Public Knowledge)를 **확정 전제**로 둔다. 기존 discovery 자산(`agent_discovery_service_contract.md`, `agent_matching_candidates_for_mvp.md`, 메인 문서 7~8장)은 이 substrate 위에서 재배치 대상이다.

---

## 0. 전제

- **메모리 구조 확정** — 4계층(L0~L3). discovery가 닿는 1차 substrate는 **L3 public anchor(Wikidata QID 정박) + anchor↔개인 node link**다.
- **Privacy는 일단 배제** — 승급 게이팅·익명화·권한 link는 나중에 덧붙인다. 지금은 "무엇이 발견 가능한가"의 *모양*만 본다.
- **anchor↔개인 link는 "공통사실 승급" 규칙에 묶이지 않는다** — 공통 사실 승급(L3 ④)은 *여러 개인이 공유하는 shared facts*에 대한 규칙이고, anchor↔개인 link는 *개인별 발견 포인터*다. 따라서 이 link에 관점·입장 같은 정성 콘텐츠를 얹어도 규칙 위반이 아니다. (= 옛 Perspective Card의 자연스러운 거처)

---

## 1. 발견·추천의 두 모드

같은 엔진이되 **트리거와 입력이 다르다.**

| | 모드 A — 명시적 요청 (pull) | 모드 B — 맥락 기반 추천 (push) |
|---|---|---|
| 트리거 | 유저가 "이 주제로 얘기할 agent 추천해줘" | 대화 흐름 속에서 시스템이 필요를 **감지** |
| 입력 | 유저가 준 토픽/의도 | 대화 맥락에서 추출한 토픽 + **무슨 필요인지** 추론 |
| UX | 후보 리스트 제시 | 대화 중간 인라인 제안 |
| 정밀도 요구 | 보통 (유저가 골라봄) | **높음** — 끼어드는 거라 틀리면 방해 |
| 기존 recsys 대응 | 검색/IR + expert-finding | conversational + context-aware recsys |

모드 B가 어려운 핵심 이유: **"무슨 필요인지"를 먼저 분류**해야 한다. 이 need 분류가 우리 설계의 심장이다(아래 5장에서 목적함수로 이어진다).

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

"이 사람 소개받고 싶다/같이 하고 싶다"(invite·networking). discovery라기보다 **런타임 액션** 쪽(`agent_event_driven_architecture.md` 소관).

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
2. **아이템이 product가 아니라 대화하는 사람/agent다 → two-sided matching.** 추천은 소비의 끝이 아니라 관계의 시작. dating·구인·expert-network 같은 matching market에 가깝다.
3. **피드백이 희소·지연·모호하고 engagement가 함정.** engagement를 naive하게 최적화하면 편안한 강화 관점만 추천 → 모드 B의 diversity 목적이 붕괴.
4. **설명가능성이 필수.** "비슷한 사람들이…"(CF 블랙박스)는 관점 추천에서 안 먹힘 → KG path 설명으로 귀결.

---

## 5. 재활용 vs 신규 — 레이어로 가른다

**결론: "새로운 문제, 기존 부품(new problem, old parts)".** 블랙박스 wrapping(i)은 아니고, 부품 재활용 + 두꺼운 정책 레이어 신규(ii)다.

근본 차이는 스택 전체에 고른 게 아니라 **위층(목적·의도·오케스트레이션)에 몰려 있다.**

| 레이어 | 차이 있나 | 판단 |
|---|---|---|
| ANN/벡터 검색, KG 임베딩, 인덱스 | 없음 | **그대로 재활용** |
| 2단계 retrieve→rank 골격 | 없음 | **그대로 재활용** |
| learning-to-rank 기계장치 | 없음 | **재활용** |
| 목적함수 (무엇을 최적화) | 있음 (affinity↔diversity 부호) | **새로** |
| intent/need 레이어 | 있음 (기존엔 거의 없는 층) | **새로** |
| 피드백 해석 (engagement 함정) | 있음 | **새로** |
| 오케스트레이션 (언제 끼어드나, two-sided 자격) | 있음 | **새로** |

### 블랙박스 wrapping이 깨지는 결정적 이유

wrapper는 **하위 retrieval이 이미 꺼내온 후보만 재정렬**할 수 있다. 기존 recsys는 affinity 기준으로 후보를 뽑으므로, 임베딩 공간에서 멀리 있는 **대립·직교 후보는 애초에 후보 집합에 안 들어온다.** 꺼내오지 않은 걸 재정렬할 수 없다 → diversity 목적은 얇은 wrapper로 해결 안 되고 **retrieval 층 자체가 diversity-aware**해야 한다. 즉 목적함수가 최하위 검색 층까지 새어 내려간다.

반대로 **강화(affinity)·깊이(expertise) need는 기존 recsys가 잘하는 영역**이라 재활용 비중이 높다.

### Phasing 함의

- **1차 (재활용 비중 높음, 저위험)**: 강화·깊이 need — 거의 표준 recsys 부품으로 빠르게.
- **2차 (신규 구축, 차별점)**: 대립·직교 관점 + 대화 중 끼어들기 — 의도적으로 새로 설계.

---

## 6. 표현·인덱싱: 토픽 ⊥ 입장 ⊥ global persona (3층)

diversity-aware retrieval은 모드 A·B 공통이지만, 공통의 진짜 핵심은 "diversity 알고리즘"이 아니라 **토픽과 입장을 분리된 축으로 표현**하는 것이다. 한 임베딩에 엉키면 모드 A는 커버리지 실패, 모드 B는 "같은 토픽 반대 입장"을 아예 못 한다.

### 6.1 3층 표현

| 층 | 단위 | 무엇 | 질문 |
|---|---|---|---|
| **토픽 축** | anchor | QID + KG 임베딩 | *어디(where)* |
| **국소 stance** | edge (anchor↔개인) | 그 anchor 쟁점 축 위의 위치 | *여기서 무슨 입장(what here)* |
| **global persona** | agent 노드 | 안정적 성향 + 스타일 (= stable core / Global Profile / persona brief, 같은 것) | *대체로 어떻게 생각/말하나(how in general)* |

### 6.2 전역 stance 공간은 없다 — anchor별 국소 공간이다

"반대"는 같은 토픽 안에서만 정의된다("anti-커피"와 "anti-재택"은 같은 축이 아니다). 하나의 글로벌 입장 공간을 만들지 않는다. 대신:

- **anchor 층 (공유)**: 그 토픽의 **쟁점 축(contested dimensions)** = 국소 stance 공간의 정의. *다수의 집계*에서 창발.
- **edge 층 (개인)**: 이 사람의 그 공간 안 **좌표** + stance descriptor + provenance.

(비전 L3 = 공유 anchor + 개인 link 구조 그대로)

### 6.3 표현: 연속 + 상징 하이브리드

| 형태 | 무엇 | 강한 곳 |
|---|---|---|
| **연속: topic-conditioned perspective embedding** | 토픽 성분 제거한 입장 *잔차* 벡터 (국소 공간) | **for/against** (벡터 유사도 부호) |
| **상징: stance descriptor / 쟁점 축** | "무엇에 대해 어떤 입장"의 구조화 | **orthogonal** + **설명가능성** |

- for/against ↔ 연속 벡터 / orthogonal ↔ 상징 쟁점 축(유저가 안 선 다른 축으로 전환). orthogonal은 임베딩 기하의 "수직"이 아니라 "다른 프레임"이라 상징이 더 잘 잡는다.
- ⚠️ 입장 텍스트를 그냥 임베딩하면 토픽이 재혼입 → "topic-conditioned(잔차)"가 disentanglement의 핵심 난점.

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

일부 need에선 global persona가 *주축*: **유사성**(닮은 사람 = global persona 유사도 primary), **orthogonal**(유저 자신의 global persona = 기준 프레임), **스타일**(단 MVP 랭킹 제외, advisory만).

### 6.6 [결정] prior ⊥ maturity — 분리 원칙

> **"예상 입장(predicted stance)"과 "대화에서 얻을 가치(conversation value)"는 다른 양이다.** prior는 *어디에 설지·후보 자격*은 채우되, *대화하면 뭘 얻을지*는 채우지 못한다.

규칙: **prior는 stance를 채우되 maturity는 절대 채우지 않는다.**
- **stance 추정** ← global persona prior 사용 가능.
- **`topic_knowledge_maturity`** ← **관찰된 실제 engagement만.** prior로 부풀리면 대화 가치를 거짓말하는 것.
- prior-채운 stance는 *추정 신뢰도*는 높아도 `topic_knowledge_maturity`는 낮은 상태가 정상 (둘은 따로 논다).

스코어링 귀결:
- **eligibility/방향**(후보 자격, for/against/orthogonal) — prior 기여 OK.
- **value/추천 점수** — **maturity가 floor(하한 게이트) + 큰 가중치.** prior가 확신해도 관찰 없으면 value는 바닥 → hollow agent가 상위로 구조되지 않음.

미세조정:
- **gain = depth + novelty.** maturity ≈ 0이면 "다른 프레임"조차 prior 추측(hollow)이라 floor는 필요. 단 floor 위에서 maturity만 과하게 쥐면 신선·직교 목소리를 죽여 diversity와 충돌 → **maturity는 하한이지 정렬의 전부가 아님.**
- **maturity 가중치 자체가 need-조건부.** 깊이(expert) need → maturity ≈ 게이트. 유사성/peer(co-explore) need → 둘 다 초심자여도 함께 탐색 가치, maturity 덜 중요. (= "목적함수가 need에 따라 바뀐다"의 일부)

### 6.7 MVP phasing — 상징 우선, 임베딩 나중

> **MVP**: 토픽 = anchor QID(상징 검색 + KG 이웃 확장). 입장 = edge의 **stance descriptor(상징)**. for/against는 서빙 시점에 유저 입장 대비 **LLM/텍스트 비교**로 판정(disentangle 임베딩 불필요, 싸고 설명가능). 모드 A 커버리지 = stance descriptor 클러스터링.
>
> **다음 단계**: 규모 요구 시 topic-conditioned perspective embedding 추가(확장 가능한 for/against), anchor 인구에서 쟁점 축 창발(orthogonal).

이유: disentangled 임베딩에 처음부터 베팅하는 건 위험(연구 난제)하고, 상징 descriptor + 서빙 비교가 더 견고·설명가능 — 설명가능성 1급 요구와 일치.

---

## 7. 미결정 / 다음에 팔 것

- **anchor 쟁점 축 창발** — 다수 입장에서 contested dimension을 어떻게 뽑나 (orthogonal의 토대).
- **stance descriptor 스키마** — edge T2에 정확히 무엇을 담나. (원칙: edge=topic-specific만, global persona는 agent 노드에 `global_profile_version` 달아 denormalize; payload 아니라 thin descriptor + L2 포인터)
- **cold anchor fallback 구체화** — prior 비중(topic_specificity) 계산식, floor 임계.
- **need 분류 → 목적함수 매핑** — need별 affinity↔diversity 부호/형태, maturity 가중치 형식화.
- **모드 B의 "필요 감지" 주체** — 유저의 자기 agent가 대화 맥락에서 판단 → discovery 엔진이 아니라 agent 런타임(event-driven) 영역.
- **two-sided matching 제약** — 상대 agent의 의향·reciprocity (privacy와 별개).
- **피드백 모델** — engagement에 무너지지 않는 품질 신호.
- **기존 자산 재매핑** — Perspective Card / DiscoverablePerspective / AgentTopicPerspective / matching policy를 이 substrate 위 어디에.
