# Agent Matching Candidates

> 이 문서는 에이전트 추천/매칭 방식을 나중에 참고하기 위한 후보 정리다.  
> 메인 discovery 문서가 `Perspective Card / SKL / retrieval` 구조를 다룬다면, 이 문서는 **어떤 기준으로 agent를 추천할 수 있는가**를 예시 중심으로 정리한다.

---

## 1. 기본 관점

Agent 추천은 단순히 "공유된 지식 기반으로 관련 agent를 찾는 것"에만 한정되지 않는다.

더 일반화하면 다음 질문에 답하는 문제다.

> 지금 이 유저가, 이 상황에서, 어떤 agent와 대화하면 좋은가?

이때 핵심 입력은 크게 두 축이다.

```text
Agent Recommendation =
  Persona Fit
  × Topic Knowledge Maturity
  × Access / Safety
  × Freshness / Diversity
```

---

## 2. 주요 입력

### 2.1 Agent Persona Card

약 10k 토큰 수준으로 요약된 agent의 persona view다.

이 카드는 "이 agent가 어떤 주제에 대해 무엇을 아는가"보다, **이 agent와 대화하면 어떤 느낌인가**를 판단하는 데 쓰인다.

포함될 수 있는 정보:

- 대화 스타일
- 가치관
- 판단 방식
- 사고 습관
- 설명 방식
- 반박/공감 성향
- 역할감: 멘토형, 코치형, 동료형, 비평가형 등
- conversation dynamics: 문장 길이, 질문 방식, turn-taking, 표현 습관

### 2.2 Topic Knowledge Maturity

대화에서 추출된 특정 주제별 지식, 경험, 관점의 성숙도다.

이 값은 "이 agent가 이 주제에 대해 얼마나 깊고 일관되게 말할 수 있는가"를 판단하는 데 쓰인다.

포함될 수 있는 정보:

- topic
- maturity
- evidence volume
- evidence consistency
- freshness
- stance summary
- useful_for
- source provenance

중요한 점은 `Persona Card`와 `Topic Knowledge Maturity`를 억지로 하나의 카드에 합치지 않는 것이다. 둘은 별도 feature store로 두고, 추천 시점에 조합하는 편이 낫다.

```text
Agent Persona Card
  - stable style
  - values
  - conversation dynamics
  - role fit

Agent Topic Maturity Index
  - topic
  - maturity
  - evidence volume
  - consistency
  - freshness
  - stance summary

Recommendation Layer
  - user/query intent에 따라 둘을 조합
```

---

## 3. 추천 예시

### 3.1 주제 + 말투 매칭

사용자 요청:

> 초기 스타트업 GTM에 대해 현실적으로 조언해줄 사람 추천해줘.

추천 기준:

- Topic: `startup_gtm`
- Topic Knowledge Maturity: high
- Persona: direct, practical, founder-like, low-fluff

추천 결과:

> 초기 B2B 세일즈 경험이 누적되어 있고, 직설적이고 실행 중심으로 말하는 agent

이 경우 단순히 GTM 지식이 높은 agent가 아니라, **그 지식을 어떤 스타일로 전달하는지**까지 본다.

### 3.2 같은 주제, 다른 persona

사용자 요청:

> 브랜딩 고민 중인데, 서로 다른 관점의 agent 3명 추천해줘.

추천 기준:

- Topic: `brand_strategy`
- Topic Knowledge Maturity: medium 이상
- Persona diversity 높게

추천 결과:

- 감각적이고 narrative 중심 agent
- 숫자와 포지셔닝 중심 agent
- 창업자/시장 관점에서 보는 agent

여기서는 topic maturity는 최소 조건이고, 실제 차별화는 persona card에서 나온다.

### 3.3 특별한 주제 없음, persona 우선

사용자 요청:

> 요즘 나랑 대화가 잘 맞을 agent 추천해줘.

추천 기준:

- User Persona Card와 Agent Persona Card 간 style fit
- 최근 대화 상태
- topic maturity는 최근 관심 주제에 대해 보조 신호로 사용

추천 결과:

> 짧고 구조화해서 말하고, 감정 과잉 없이 현실적으로 반응하는 agent

특정 topic query가 없어도, 최근 사용자의 관심사가 `career`, `startup`, `relationship`이면 해당 주제 maturity가 있는 agent를 살짝 우대할 수 있다.

### 3.4 보완형 추천

사용자 상태:

> 사용자는 아이디어는 많지만 결정이 느림.

추천 기준:

- Persona complementarity: decision-oriented, prioritization-heavy
- Topic Knowledge Maturity: 사용자의 최근 고민 주제에서 medium 이상

추천 결과:

> 우선순위 결정과 trade-off 정리에 강하고, 애매한 선택지를 빠르게 좁혀주는 agent

이 방식은 "나와 비슷한 agent"가 아니라 **나를 보완하는 persona**를 고르는 방식이다.

### 3.5 깊은 대화 추천

사용자 요청:

> AI product strategy에 대해 깊게 이야기할 agent 있어?

추천 기준:

- Topic: `ai_product_strategy`
- Topic Knowledge Maturity: high
- Persona: abstract thinking, systems thinking, tolerant of long-form reasoning

추천 결과:

> AI 제품 전략에 대한 누적 대화가 많고, 단기 기능보다 시스템 구조와 시장 포지션을 함께 보는 agent

여기서는 주제 maturity만 높아도 부족하고, persona card에 **깊은 추론을 견디는 대화 성향**이 있어야 한다.

### 3.6 가벼운 대화 추천

사용자 요청:

> 그냥 편하게 얘기할 agent 추천해줘.

추천 기준:

- Persona: warm, casual, low-pressure
- Topic Knowledge Maturity: 낮아도 됨
- 최근 사용자 관심 주제와 약하게 겹치면 가산점

추천 결과:

> 전문성보다는 대화 텐션과 안정감이 맞는 agent

이 경우 topic maturity는 primary ranking feature가 아니라 fallback 또는 secondary feature다.

### 3.7 검증 / 반박형 추천

사용자 요청:

> 내 생각을 반박해줄 agent 추천해줘.

추천 기준:

- Persona: skeptical, direct, analytical
- Topic Knowledge Maturity: 사용자가 제시한 주제에서 high
- Conversation style: debate-friendly, not overly agreeable

추천 결과:

> 해당 주제에 대한 성숙한 관점을 갖고 있고, 동의보다 반례와 리스크를 먼저 제시하는 agent

여기서는 persona card에서 **agreeableness 낮음 / critical thinking 높음** 같은 신호가 중요하다.

### 3.8 멘토형 추천

사용자 요청:

> 이 문제를 같이 봐줄 멘토 같은 agent 있어?

추천 기준:

- Topic Knowledge Maturity: high
- Persona: patient, explanatory, experience-based, not too terse
- Role fit: mentor / coach-like

추천 결과:

> 경험 기반으로 맥락을 물어보고, 결론만 던지기보다 판단 과정을 설명하는 agent

### 3.9 빠른 실행형 추천

사용자 요청:

> 길게 말고 액션 아이템만 뽑아줄 agent.

추천 기준:

- Persona: concise, action-oriented, checklist style
- Topic Knowledge Maturity: medium 이상

추천 결과:

> 주제 이해도는 충분하고, 설명보다 다음 행동을 압축해서 주는 agent

### 3.10 최신성 포함 추천

사용자 요청:

> 요즘 creator economy 쪽 얘기 잘하는 agent?

추천 기준:

- Topic: `creator_economy`
- Topic Knowledge Maturity: high
- Freshness 높음
- Persona: trend-sensitive, market-aware

추천 결과:

> 최근 creator economy 관련 대화와 관점 업데이트가 많고, 트렌드를 빠르게 해석하는 agent

여기서는 maturity와 freshness를 분리해야 한다. 오래 축적된 고수와 최근 트렌드 감각이 좋은 agent는 다를 수 있다.

---

## 4. 요청 유형별 가중치 후보

추천 스코어는 대략 다음처럼 시작할 수 있다.

```text
score =
  query_relevance
× topic_knowledge_maturity
× persona_fit
× freshness_decay
× safety_access
× diversity_adjustment
```

요청 유형에 따라 가중치는 달라진다.

```text
주제 질문:
  topic_knowledge_maturity > query_relevance > persona_fit

대화 상대 추천:
  persona_fit > recent_user_context > topic_knowledge_maturity

멘토 / 코치 추천:
  persona_fit(role) × topic_knowledge_maturity

반박 / 검증 추천:
  topic_knowledge_maturity × critical_persona_fit

가벼운 대화:
  persona_fit >> topic_knowledge_maturity

최신 트렌드 대화:
  query_relevance × freshness_decay × topic_knowledge_maturity
```

---

## 5. 설계 메모

### 5.1 Persona Card와 Topic Maturity는 분리한다

`Persona Card`는 agent의 stable style과 role fit을 설명하고, `Topic Knowledge Maturity`는 특정 주제에 대한 지식·관점의 성숙도를 설명한다.

둘은 서로 다른 feature store로 관리하고, 추천 시점에 조합한다.

### 5.2 Topic query가 없어도 추천은 가능하다

특별한 주제가 없어도 다음 신호로 agent를 추천할 수 있다.

- user persona와 agent persona의 fit
- 최근 대화에서 드러난 관심사
- 현재 상태와 대화 목적
- 보완적 성향
- 다양성 / serendipity

단, 이 경우 topic maturity는 primary feature가 아니라 보조 feature가 된다.

### 5.3 Maturity와 freshness는 분리한다

`topic_knowledge_maturity`는 지식과 관점의 깊이·일관성을 의미하고, `freshness`는 최근성을 의미한다.

둘을 합치면 다음 문제가 생긴다.

- 오래됐지만 깊이 있는 evergreen agent가 사라짐
- 최근 대화가 많지만 얕은 agent가 과대평가됨

따라서 ranking에서는 둘을 별도 feature로 사용한다.

### 5.4 Style match는 점진적으로 강화한다

초기에는 `conversation_style`을 필터나 설명용 metadata로만 써도 된다.

이후 `Persona Card`가 안정화되면 다음과 같은 feature를 ranking에 넣을 수 있다.

- directness fit
- verbosity fit
- warmth fit
- analytical depth fit
- challenge / support preference fit
- role fit

### 5.5 Safety / Access는 ranking 이전에 적용한다

추천 후보는 점수 계산 전에 먼저 access와 safety 필터를 통과해야 한다.

예:

- `discoverable = true`
- `requires_permission` 충족
- private leakage risk 없음
- blocked / muted / rate-limited agent 제외

이 필터는 점수 가중치가 아니라 hard constraint로 취급하는 편이 안전하다.

---

## 6. 현재 결론

Agent matching은 knowledge discovery만으로 정의하면 좁다.

더 적절한 정의는 다음과 같다.

> Agent matching은 유저의 요청, 상태, 선호, 최근 맥락에 맞춰 **Persona Fit**과 **Topic Knowledge Maturity**를 조합해 대화할 agent를 고르는 문제다.

따라서 개발 관점에서는 다음 두 feature source를 분리해 만들고, recommendation layer에서 조합하는 것이 좋다.

```text
Persona Card
+ Topic Knowledge Maturity Index
→ Agent Recommendation
```
