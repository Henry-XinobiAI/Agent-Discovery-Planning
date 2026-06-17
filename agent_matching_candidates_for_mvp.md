# Agent Matching Candidates for MVP

> 이 문서는 `agent_matching_candidates.md`의 범위를 MVP 수준으로 좁힌 참고 문서다.  
> MVP에서는 말투, 문장 길이, turn-taking 같은 **conversation dynamics는 제외**하고, 계산 가능한 최소 metadata로 agent 추천을 설계한다.

---

## 1. MVP 범위

MVP의 agent matching은 "말이 잘 통하는 agent"를 정교하게 찾는 문제가 아니다.

우선은 다음 질문에 답한다.

> 특정 요청이나 주제에 대해, 어떤 agent가 충분히 성숙한 관점과 적절한 조언 성향을 가지고 있는가?

따라서 MVP 추천은 다음 축으로 좁힌다.

```text
hard filter (gate):  Access / Safety / status 통과 여부

ranking score (가중합):
  w1 · Topic Relevance
+ w2 · Topic Knowledge Maturity
+ w3 · Advisory Fit
+ w4 · Freshness
```

> Access/Safety는 점수 항이 아니라 **통과/탈락 hard filter**다. 랭킹은 가중합으로 둔다 (이유는 §6).

MVP에서 제외한다.

- 말투 매칭
- 문장 길이 매칭
- 표현 습관 매칭
- turn-taking style
- 유저와 agent 간 정교한 style distance
- warmth/directness 같은 세밀한 conversation dynamics
- "나와 말이 잘 통함" 류의 감각적 추천

MVP에서 `persona`는 대화체 복제가 아니라 **agent가 문제를 어떻게 판단하고 조언하는가**를 나타내는 metadata로만 사용한다.

```text
conversation_style X
advisory_profile O

persona_fit X
advisory_fit O
```

### 1.1 SKL 기반 agent discovery와의 관계

이 문서의 MVP agent matching은 이전에 논의한 SKL 기반 agent discovery와 별개의 경쟁 설계가 아니다.

둘은 같은 문제를 다른 레이어에서 본다.

```text
SKL 기반 discovery:
  어떤 topic에 어떤 agent 관점들이 공개되어 있고, 어떻게 조직되는가?

MVP agent matching:
  그중 지금 이 요청에 어떤 agent를 추천할 것인가?
```

즉 SKL은 discovery의 substrate이고, MVP agent matching은 그 위에서 동작하는 retrieval/ranking policy에 가깝다.

```text
Public Agent Memory
  → SKL Projection
  → Topic Space / Perspective Index
  → Agent Perspective Card
  → AgentTopicPerspective Index
  → Matching / Ranking
  → Recommended Agents
```

차이를 정리하면 다음과 같다.

| 구분 | SKL 기반 discovery | MVP agent matching |
|---|---|---|
| 중심 질문 | 어떤 topic에 어떤 agent 관점들이 존재하는가? | 이 요청에 어떤 agent를 추천할 것인가? |
| 주요 단위 | Topic Space + Agent Perspective Card | AgentTopicPerspective + Effective Profile |
| 성격 | 지식/관점 네트워크 설계 | 추천 랭킹/서빙 설계 |
| 입력 | Public Agent Memory의 projection | 검색 가능한 perspective record + matching metadata |
| 출력 | 관련 agent 후보 발견 | ranked agent list |
| 강조점 | 공유 관점 구조, projection, discoverability | maturity, advisory fit, freshness, access filter |
| persona 사용 | card의 공개 가능한 style/stance 요약 | conversation dynamics 제외, advisory profile만 사용 |

따라서 이 문서의 `AgentTopicPerspective`는 SKL의 `Agent Perspective Card`를 실제 추천 시스템에서 쓰기 좋게 정규화한 serving model로 볼 수 있다.

```text
Conceptual layer:
  SKL / Perspective Card

Serving layer:
  AgentTopicPerspective Index
  Global Agent Profile
  Effective Profile
  Recommendation Ranker
```

실제 사용 시나리오에서는 다음처럼 갈린다.

- 사용자가 **"이 주제에는 어떤 관점들이 있어?"**처럼 묻는 경우: SKL discovery가 전면에 나온다. 결과는 agent list보다 topic / perspective cluster 중심이다.
- 사용자가 **"누구랑 이야기하면 좋아?"**, **"이 문제를 봐줄 agent 추천해줘"**처럼 묻는 경우: MVP agent matching이 전면에 나온다. 결과는 ranked agent 중심이다.
- 사용자가 **"서로 다른 관점의 agent 여러 명 보여줘"**처럼 묻는 경우: SKL의 관점 클러스터링으로 다양성을 확보하고, matching으로 각 클러스터의 대표 agent를 고른다.

짧게 말하면, **SKL discovery는 관점 지도를 펼치는 경험**이고, **MVP agent matching은 지금 대화할 agent를 고르는 경험**이다.

### 1.2 네이밍 정리: 비슷해 보이는 세 레코드

세 이름은 경쟁 모델이 아니라 같은 대상을 보는 **다른 레이어**다.

| 이름 | 레이어 | 정의 |
|---|---|---|
| `Agent Perspective Card` | 개념/제품 | 메인 문서 7장의 공개 관점 카드 |
| `DiscoverablePerspective` | contract | producer-consumer 일반 인터페이스 (`agent_discovery_service_contract.md`) |
| `AgentTopicPerspective` | 서빙 | agent matching 서빙 인덱스의 물리/논리 레코드 (이 문서 §11) |

> **`AgentTopicPerspective`는 `DiscoverablePerspective` 중 `entity_type = agent`인 레코드를, matching serving에 맞게 denormalize + feature enrichment한 형태다.** 단순 denormalize가 아니라 **matching 전용 feature를 추가로 얹는다.**

contract(`DiscoverablePerspective`)에는 `style_descriptors`는 있어도 `advisory_profile`은 없다. MVP matching은 `advisory_fit`에 강하게 의존하므로, 이 feature들은 **contract 바깥의 matching extension**이다.

```yaml
matching_features:        # contract 필드 + 아래 enrichment
  advisory_profile        # = advisory_tags (§3 MVP 축소형)
  topic_knowledge_maturity
  perspective_lens
```

> 구조: **contract만 있어도 discovery는 가능하고, matching 품질은 이 enrichment가 있을 때 좋아진다.** advisory_profile을 contract로 끌어올리지 않는 이유는 contract를 generic·thin하게 유지하기 위해서다 (agent 외 producer엔 advisory 개념이 없을 수 있다).

### 1.3 용어 정리: maturity는 새 confidence가 아니다

`topic_knowledge_maturity`는 메인 문서의 confidence 계열과 겹쳐 보이지만, 새 계열이 아니라 **그 파생 serving feature**다. 셋의 관계를 다음으로 고정한다.

| 용어 | 위치 | 의미 |
|---|---|---|
| `evidence_strength` | 추출/원본 | 원자료의 양·일관성·구체성 |
| `perspective_confidence` | 공개 카드 | 공개 관점 카드의 신뢰도·품질 (evidence_strength에서 산출) |
| `topic_knowledge_maturity` | matching 서빙 | 특정 topic에서 agent가 **대화 가능한 수준까지 관점이 성숙했는가** |

> `topic_knowledge_maturity`는 ranking에서 쓰는 serving feature이며, 입력으로 `evidence_strength · consistency · feedback` 등을 쓴다. **새 confidence 계열을 만들지 않고 `perspective_confidence`의 matching용 파생값으로 둔다.** (`extraction_confidence`·`persona_maturity`와도 다른 층 — 메인 문서 3.3·3.4 참고.)
>
> **freshness는 maturity의 입력에 넣지 않는다.** maturity에 freshness를 섞으면 active-set·ranking에서 freshness를 또 쓸 때 이중 계산이 된다. freshness는 **maturity와 독립된 별도 feature**로만 둔다 (§4.1·§6).

---

## 2. 핵심 분리: Global Profile과 Topic-Specific Profile

조언 성향은 두 곳에 존재할 수 있다.

1. agent 전체에 안정적으로 나타나는 성향
2. 특정 topic에서만 드러나는 성향

예를 들어 "실행 중심"이라는 성향은 agent 전체 persona일 수도 있고, `startup_gtm` 주제에서만 강하게 나타나는 성향일 수도 있다. "데이터 기반"도 마찬가지다. 어떤 agent는 전반적으로 framework 기반으로 말하지만, `finance` 주제에서는 data 기반으로 말할 수 있다.

따라서 MVP에서도 metadata를 한 곳에 몰아넣지 않고 다음처럼 나눈다.

```text
Agent Matching =
  Global Agent Profile
+ Topic-Specific Perspective Profile
```

---

## 3. Global Agent Profile

`Global Agent Profile`은 agent 전반에 안정적으로 나타나는 조언 성향이다.

이 값은 특정 topic evidence가 약하거나, 사용자의 요청이 topic보다 역할/태도에 가까울 때 fallback으로 사용된다.

> **MVP 축소형 (중요)**: 아래 예시들은 advisory를 6차원 연속값(0.0~1.0)으로 보여주지만, 이건 **성숙기의 target 표현**이다. 처음부터 연속값을 정확히 뽑으려 하면 다시 persona extraction 문제가 커진다. **MVP에서는 거친 tag + low/medium/high로 시작한다.**
>
> ```yaml
> advisory_tags:           # 태그별 강도를 low/medium/high로 (연속값 대신)
>   practical: high
>   strategic: medium
>   challenging: low
>   # mentor_like / decision_oriented 등 필요한 태그만
> ```
>
> 단일 `advisory_level` 하나로는 태그별 강도를 표현할 수 없으므로 **태그→레벨 맵**으로 둔다. 연속값(0.0~1.0)·6차원 전체로의 확장은 feedback이 쌓여 calibration이 가능해진 뒤로 미룬다.

예시 (target 표현):

```yaml
global_agent_profile:
  role_tags:
    - mentor
    - operator

  advisory_modes:
    practical: 0.7
    strategic: 0.8
    analytical: 0.8
    creative: 0.4
    supportive: 0.5
    challenging: 0.6

  decision_orientation:
    explores_options: 0.5
    narrows_options: 0.7
    action_bias: 0.6
    risk_sensitive: 0.7

  evidence_style:
    experience_based: 0.7
    framework_based: 0.8
    data_based: 0.5
    intuition_based: 0.3
```

### 3.1 필드 의미

`role_tags`는 agent의 대표 역할을 나타낸다.

예:

- `mentor`
- `operator`
- `critic`
- `coach`
- `strategist`
- `explorer`

`advisory_modes`는 agent가 조언할 때 주로 취하는 태도다.

- `practical`: 실행 중심
- `strategic`: 큰 그림과 방향성 중심
- `analytical`: 구조화와 분석 중심
- `creative`: 아이디어 발산 중심
- `supportive`: 지지와 안정감 중심
- `challenging`: 반박과 검증 중심

`decision_orientation`은 결정과 실행을 다루는 방식이다.

- `explores_options`: 선택지를 넓힘
- `narrows_options`: 선택지를 좁힘
- `action_bias`: 다음 행동으로 밀어줌
- `risk_sensitive`: 리스크를 민감하게 봄

`evidence_style`은 조언의 근거 스타일이다.

- `experience_based`: 경험 기반
- `framework_based`: 프레임워크 기반
- `data_based`: 데이터 기반
- `intuition_based`: 직관 기반

---

## 4. Topic-Specific Perspective Profile

`Topic-Specific Perspective Profile`은 특정 topic에서의 지식 성숙도와 조언 성향을 함께 표현한다.

이 값은 추천의 중심이다. MVP에서 "이 agent가 이 주제에 대해 추천될 만한가"는 대부분 여기서 결정된다.

예시:

```yaml
topic_perspectives:
  - topic: startup_gtm
    maturity: 0.86
    evidence_volume: 0.8
    consistency: 0.9
    freshness: 0.7
    stance_summary: "초기 B2B SaaS에서는 founder-led sales와 좁은 ICP 검증을 중시함."

    advisory_modes:
      practical: 0.95
      strategic: 0.6
      analytical: 0.7
      creative: 0.2
      supportive: 0.3
      challenging: 0.8

    perspective_lens:
      market: 0.9
      product: 0.5
      user: 0.8
      technical: 0.2
      financial: 0.6
      organizational: 0.4

    evidence_style:
      experience_based: 0.95
      framework_based: 0.6
      data_based: 0.4
      intuition_based: 0.2
```

### 4.1 필드 의미

`maturity`는 해당 topic에 대한 지식과 관점의 성숙도다.

이 값은 단순히 많이 언급했는지가 아니라, 다음을 종합한다.

- evidence volume
- consistency
- specificity
- repeated use across conversations
- user/public feedback if available

`freshness`는 최근성이다. `maturity`와 합치지 않는다.

오래됐지만 깊은 evergreen 관점과, 최근성이 높지만 얕은 관점은 다르게 다뤄야 하기 때문이다.

`stance_summary`는 이 agent가 해당 topic을 어떻게 보는지에 대한 짧은 요약이다.

이는 embedding, 결과 설명, 사용자 선택 UI에 모두 사용할 수 있다.

`advisory_modes`는 topic-specific 값으로, agent 전체 성향과 다를 수 있다. global 값을 완전히 덮어쓰는 override가 아니라, §5의 `effective_profile`에서 `topic_specificity`에 따라 global과 **혼합(blend)**된다. (MVP 표현은 §3의 축소형을 따른다.)

`perspective_lens`는 같은 topic을 어떤 렌즈로 보는지 나타낸다.

- `market`
- `product`
- `user`
- `technical`
- `financial`
- `organizational`

`evidence_style`도 topic별로 달라질 수 있다.

---

## 5. Effective Profile 계산

추천 시점에는 global profile과 topic-specific profile을 섞어 `effective_profile`을 만든다.

```text
effective_profile(topic) =
  global_agent_profile × (1 - topic_specificity)
+ topic_perspective_profile × topic_specificity
```

`topic_specificity`는 해당 topic profile을 얼마나 믿을 수 있는지 나타낸다.

초기 후보:

```text
topic_specificity =
  maturity × consistency
```

예:

```text
maturity = 0.86
consistency = 0.90
topic_specificity = 0.774
```

topic evidence가 충분하고 일관적이면 topic-specific profile을 더 많이 반영한다. topic evidence가 약하면 global profile을 fallback으로 쓴다.

---

## 6. 추천 스코어 후보

MVP 추천은 **hard filter → 가중합 ranking** 두 단계로 둔다.

```text
1) hard_filter = access / safety / status 통과 여부 (통과 못하면 후보에서 제외)

2) score =
     w1 · topic_relevance
   + w2 · topic_knowledge_maturity
   + w3 · advisory_fit
   + w4 · freshness_decay
```

각 항목의 의미:

- `topic_relevance`: 사용자 요청과 topic/stance의 관련성
- `topic_knowledge_maturity`: 해당 topic에 대한 성숙도 (§1.3)
- `advisory_fit`: 요청 intent와 effective profile의 적합도
- `freshness_decay`: 최근성 가중치
- `access / safety / status`: discoverable, permission, safety — 점수 항이 아니라 hard filter (gate)

> **왜 곱셈이 아니라 가중합인가**: 곱셈식은 한 feature가 낮으면 전체가 과하게 무너지고 초기 calibration이 어렵다. MVP에서는 **가중합이 튜닝하기 쉽다.** feature가 안정화되면 learning-to-rank나 multiplicative boost를 검토한다. (intent별 weight는 §8.)
>
> **contract의 score와의 관계**: `agent_discovery_service_contract.md` §3의 `relevance × confidence × freshness_decay`는 **모든 `entity_type`에 공통인 generic discovery baseline(예시)**이다. 이 문서의 가중합 score는 그것을 **`entity_type = agent` 추천에 맞게 specialization**한 것이다 — `advisory_fit`을 더하고 결합을 가중합으로 둔다. 즉 결합 방식(곱셈/가중합)은 baseline의 고정 규칙이 아니라 레이어별 구현 선택이다.

---

## 7. MVP 추천 유형

> 아래 "주요 신호"의 `×` 표기는 곱셈식이 아니라 **그 intent에서 가중치를 높이는 신호**를 뜻하는 약식 표현이다. 실제 점수는 §6의 가중합으로 계산하고, intent별 weight는 §8을 따른다.

### 7.1 주제 전문성 추천

사용자 요청:

> GTM 잘 아는 agent 추천해줘.

주요 신호:

```text
topic_relevance × topic_knowledge_maturity
```

`advisory_fit`은 약하게만 사용한다.

### 7.2 주제 + 역할 추천

사용자 요청:

> GTM을 현실적으로 봐줄 agent 추천해줘.

주요 신호:

```text
topic_relevance × topic_knowledge_maturity × practical
```

`practical`은 effective profile에서 계산한다. topic-specific practical 값이 충분히 성숙하면 global practical보다 우선한다.

### 7.3 반박 / 검증형 추천

사용자 요청:

> 내 생각을 반박해줄 agent 추천해줘.

주요 신호:

```text
topic_relevance × topic_knowledge_maturity × challenging × analytical
```

반박형 추천은 단순히 도전적인 agent가 아니라, 해당 topic maturity가 충분한 agent여야 한다.

### 7.4 멘토형 추천

사용자 요청:

> 이 문제를 같이 봐줄 멘토 같은 agent 있어?

주요 신호:

```text
topic_relevance × topic_knowledge_maturity × role:mentor × experience_based
```

topic-specific `experience_based`가 있으면 그것을 우선하고, 없으면 global evidence style을 사용한다.

### 7.5 최신성 기반 추천

사용자 요청:

> 요즘 creator economy 쪽 얘기 잘하는 agent?

주요 신호:

```text
topic_relevance × topic_knowledge_maturity × freshness_decay
```

여기서는 freshness의 가중치를 더 높인다. 단, freshness가 높아도 maturity가 너무 낮으면 추천하지 않는다.

### 7.6 결정 보조형 추천

사용자 요청:

> 선택지를 줄여서 결정 도와줄 agent 추천해줘.

주요 신호:

```text
topic_relevance × topic_knowledge_maturity × narrows_options × action_bias
```

사용자가 topic을 명시하지 않으면 최근 대화 topic 또는 사용자가 입력한 문제 설명에서 topic을 추출한다.

---

## 8. 요청 유형별 가중치 후보

```yaml
recommendation_intents:
  topic_expert:
    weights:
      topic_relevance: 0.45
      topic_knowledge_maturity: 0.40
      advisory_fit: 0.10
      freshness: 0.05

  topic_plus_practical:
    weights:
      topic_relevance: 0.35
      topic_knowledge_maturity: 0.35
      advisory_fit: 0.25
      freshness: 0.05

  challenger:
    weights:
      topic_relevance: 0.30
      topic_knowledge_maturity: 0.35
      advisory_fit: 0.30
      freshness: 0.05

  mentor:
    weights:
      topic_relevance: 0.30
      topic_knowledge_maturity: 0.35
      advisory_fit: 0.30
      freshness: 0.05

  fresh_topic:
    weights:
      topic_relevance: 0.35
      topic_knowledge_maturity: 0.25
      advisory_fit: 0.10
      freshness: 0.30

  decision_helper:
    weights:
      topic_relevance: 0.25
      topic_knowledge_maturity: 0.30
      advisory_fit: 0.40
      freshness: 0.05
```

---

## 9. 전체 카드 예시

```yaml
agent_id: agent_123

global_agent_profile:
  role_tags:
    - operator
    - critic
    - mentor

  advisory_modes:
    practical: 0.7
    strategic: 0.8
    analytical: 0.8
    creative: 0.3
    supportive: 0.4
    challenging: 0.6

  decision_orientation:
    explores_options: 0.4
    narrows_options: 0.8
    action_bias: 0.7
    risk_sensitive: 0.7

  evidence_style:
    experience_based: 0.7
    framework_based: 0.8
    data_based: 0.5
    intuition_based: 0.3

topic_perspectives:
  - topic: startup_gtm
    maturity: 0.86
    evidence_volume: 0.8
    consistency: 0.9
    freshness: 0.7
    stance_summary: "초기 B2B SaaS에서는 founder-led sales와 좁은 ICP 검증을 중시함."

    advisory_modes:
      practical: 0.95
      strategic: 0.6
      analytical: 0.7
      creative: 0.2
      supportive: 0.3
      challenging: 0.8

    perspective_lens:
      market: 0.9
      product: 0.5
      user: 0.8
      technical: 0.2
      financial: 0.6
      organizational: 0.4

    evidence_style:
      experience_based: 0.95
      framework_based: 0.6
      data_based: 0.4
      intuition_based: 0.2

  - topic: ai_product_strategy
    maturity: 0.74
    evidence_volume: 0.6
    consistency: 0.8
    freshness: 0.8
    stance_summary: "AI 제품은 기능보다 workflow integration과 distribution이 중요하다고 봄."

    advisory_modes:
      practical: 0.6
      strategic: 0.9
      analytical: 0.8
      creative: 0.5
      supportive: 0.3
      challenging: 0.6

    perspective_lens:
      market: 0.8
      product: 0.9
      user: 0.7
      technical: 0.6
      financial: 0.4
      organizational: 0.5

    evidence_style:
      experience_based: 0.6
      framework_based: 0.8
      data_based: 0.5
      intuition_based: 0.3

access_policy:
  discoverable: true
  requires_permission: false
  exposes_private_memory: false
```

---

## 10. 현재 결론

MVP에서는 agent matching을 정교한 persona/style matching으로 보지 않는다.

대신 다음처럼 좁힌다.

```text
Global Agent Profile
+ Topic-Specific Perspective Profile
→ Effective Profile
→ Advisory Fit
→ Agent Recommendation
```

이 구조는 다음 장점을 가진다.

- conversation dynamics 없이도 계산 가능하다.
- 전역 persona의 과잉 적용을 피할 수 있다.
- topic별로 달라지는 조언 성향을 표현할 수 있다.
- topic evidence가 약할 때 global profile을 fallback으로 사용할 수 있다.
- 이후 conversation dynamics를 추가하더라도 별도 feature로 확장하기 쉽다.

---

## 11. 대규모 저장과 검색 전략

> **중복 방지 cross-ref**: hot/cold active-set, 권한 push-down, 비동기 projection, "index는 재빌드 가능한 projection" 같은 **일반 scale-out 원칙은 `agent_discovery_service_contract.md` §3·§6 및 메인 문서 13장과 동일**하다. 여기서는 길게 반복하지 않고, **matching 고유 사항**(검색 단위 = agent-topic perspective, global profile denormalize, query 없는 추천 bucket, topic별 maturity threshold)에 집중한다.

유저 베이스가 커지고, 각 agent가 여러 topic에 대해 maturity 정보를 가지면 검색 비용이 빠르게 커진다.

naive한 구조는 다음처럼 폭발한다.

```text
수억 agents × agent별 topic perspectives N개
= 수십억~수백억 discoverable perspective records
```

따라서 검색 단위는 `agent`가 아니라 **agent-topic perspective record**여야 한다.

```text
(agent_id, topic_id, perspective_id)
```

즉 "이 agent가 어떤 사람인가"를 먼저 찾는 것이 아니라, **특정 topic에서 추천 가능한 agent의 관점 단위**를 찾고, 마지막에 agent 단위로 묶는다.

### 11.1 저장 단위: AgentTopicPerspective

대규모 검색의 기본 레코드는 다음과 같다.

```yaml
agent_topic_perspective:
  perspective_id: perspective_123
  agent_id: agent_123
  topic_id: startup_gtm
  topic_cluster_id: startup_gtm/founder_sales

  embedding_text:
    stance_summary: "초기 B2B SaaS에서는 founder-led sales와 좁은 ICP 검증을 중시함."
    useful_for:
      - 초기 GTM 전략 점검
      - ICP narrowing
      - founder sales script 피드백
    representative_claims:
      - "초기에는 PLG보다 직접 고객 대화가 우선"
      - "시장보다 ICP 선명도가 먼저"

  embedding_vector: "<vector>"

  maturity: 0.86
  evidence_volume: 0.8
  consistency: 0.9
  freshness: 0.7

  advisory_profile:
    practical: 0.95
    strategic: 0.6
    analytical: 0.7
    creative: 0.2
    supportive: 0.3
    challenging: 0.8

  perspective_lens:
    market: 0.9
    product: 0.5
    user: 0.8
    technical: 0.2
    financial: 0.6
    organizational: 0.4

  access_policy:
    discoverable: true
    visibility_scope: public
    requires_permission: false
    exposes_private_memory: false
    safety_class: normal

  status:
    lifecycle: active
    revoked: false
```

이 레코드는 source of truth가 아니라 검색용 projection이다. 원본은 agent profile, topic perspective store, publish/revoke event log에 있고, 검색 인덱스는 언제든 재빌드 가능해야 한다.

> **Global profile denormalize (matching 고유)**: 검색 단위가 `AgentTopicPerspective`이므로, `effective_profile`(§5) 계산에 필요한 **global profile의 작은 부분집합(role_tags, advisory_tags 등)을 각 레코드에 denormalize**해 두는 편이 낫다. 매 검색마다 agent profile store를 join하면 latency·복잡도가 오른다. 단 global profile이 자주 바뀌면 projection rebuild 비용이 생기므로, **MVP에서는 작고 안정적인 필드만** denormalize한다.
>
> denormalize한 값에는 **`global_profile_version`**을 함께 넣는다. global profile이 갱신되면 이 버전으로 stale 레코드를 식별해 다시 projection할 수 있어, 운영 모델(언제 갱신할지)이 명확해진다.

### 11.2 Hot / Cold 분리

검색 대상은 active-set으로 제한한다. **일반 원칙(hot/cold, evergreen 유지, 재승격)은 메인 5.3.2 / contract §3와 동일**하므로 여기서는 matching 고유의 active 조건만 적는다 — active-set 판정에 **topic별 maturity 임계**가 들어간다는 점이다.

```text
active if:
  discoverable = true
  AND revoked = false
  AND maturity >= topic_min_maturity
  AND (freshness >= topic_min_freshness OR maturity >= evergreen_maturity)
```

### 11.3 검색 흐름

대규모에서는 전체 perspective index를 한 번에 검색하지 않는다.

기본 흐름은 다음과 같다.

```text
User Query
  ↓
Query Understanding
  - topic 후보 추출
  - intent 추출: expert / mentor / challenger / practical / fresh_topic 등
  ↓
Topic Routing
  - topic_id 또는 topic_cluster_id 선택
  ↓
ANN Retrieval
  - 해당 topic shard에서 perspective vector top K 검색
  ↓
Metadata Push-down Filter
  - access / safety / maturity / language / region
  ↓
Rerank
  - relevance / maturity / advisory_fit / freshness / diversity
  ↓
Group by Agent
  - agent별 best perspective 선택
  ↓
Top N Agents
```

검색은 크게 두 단계다.

1. ANN retrieval로 넓게 후보를 찾는다.
2. metadata filter와 rerank로 실제 추천 agent를 고른다.

### 11.4 샤딩 기준

기본 샤딩 키는 `topic_cluster_id`가 적절하다.

```text
shard = topic_cluster_id
```

대부분의 요청이 특정 문제나 주제와 연결되기 때문이다.

다만 인기 topic은 단일 shard가 커질 수 있으므로 내부 sub-cluster로 한 번 더 나눈다.

```text
startup_gtm
  / founder_sales
  / plg
  / enterprise_sales
  / pricing
  / icp
```

이 sub-cluster는 처음에는 수동 taxonomy나 seed topic으로 시작할 수 있지만, 장기적으로는 embedding clustering 기반으로 관리하는 편이 낫다.

### 11.5 권한 필터는 index 안으로 push-down

권한을 검색 후처리(post-filter)로만 처리하면 후보가 말라붙는다 — query 시점에 index filter로 push-down해야 한다. **원칙·근거는 contract §3 / 메인 13.3와 동일**하므로 여기서는 matching 인덱스가 실제로 들고 있어야 할 **필수 filter metadata**만 적는다.

```yaml
discoverable: boolean
status: active | cold | revoked
visibility_scope: public | restricted
requires_permission: boolean
safety_class: normal | sensitive | restricted
language: string
region: string
topic_cluster_id: string
```

### 11.6 Maturity는 filter이자 ranking feature

`maturity`는 두 번 쓰인다.

1. candidate filter
2. reranking feature

```text
candidate filter:
  maturity >= min_maturity_for_topic

rerank:
  §6의 가중합 score 사용
  ( w1·relevance + w2·maturity + w3·advisory_fit + w4·freshness_decay )
```

단, maturity threshold는 topic별로 달라야 한다.

예:

- medical / legal / finance: 높은 maturity threshold
- casual / lifestyle: 낮은 maturity threshold 허용
- fast-moving trend: freshness 비중 높음
- evergreen strategy: maturity 비중 높음

### 11.7 Agent 단위 grouping

검색 단위가 perspective라서 같은 agent가 여러 perspective로 여러 번 나올 수 있다.

따라서 rerank 후 agent 단위 grouping이 필요하다.

```text
retrieve top K perspectives
→ group by agent_id
→ agent별 best perspective 선택
→ diversity rerank
→ top N agents 반환
```

결과에는 추천 이유를 함께 붙인다.

```yaml
recommended_agent:
  agent_id: agent_123
  matched_perspective_id: perspective_123
  matched_topic: startup_gtm
  reasons:
    - high maturity in startup_gtm
    - practical/challenging advisory fit
    - recent enough
```

### 11.8 Query 없는 추천은 materialized bucket

홈 화면 추천처럼 명시적 query가 없는 경우는 실시간 전체 검색보다 미리 만든 bucket을 쓰는 편이 낫다.

> **주의 — per-user materialize는 피한다.** 유저마다 topic/intent bucket을 통째로 materialize하면 저장 비용이 유저 수에 비례해 폭발한다. 대신 **bucket은 global / segment / topic-intent 단위로만 precompute**하고, **유저 개인화는 serving 시점의 lightweight rerank**로 처리한다.

```text
Precompute (유저 독립):
  candidate agents per (topic, intent) bucket   # global/segment 단위

Serving (유저별):
  관련 bucket candidate 로드
  → user signal(recent_interest_topics, preferred advisory, blocked/seen)로 lightweight rerank
```

버킷 예 (유저 독립):

```text
startup_gtm:expert
startup_gtm:challenger
startup_gtm:mentor
creator_economy:fresh
ai_product_strategy:strategic
```

### 11.9 쓰기 경로는 비동기 projection

agent 대화에서 topic maturity가 바뀔 때마다 인덱스를 즉시 갱신하면 비용이 크다. 쓰기 경로는 비동기 배치가 적절하다. matching 고유 단계는 **maturity recalculation → publish gate**이고, 나머지(비동기 배치·재빌드 가능성)는 contract §3 / 메인 5.3.1과 동일하다.

```text
conversation / event → extraction → topic perspective update candidate
  → maturity recalculation → publish / discoverable gate
  → event stream → projection worker → hot index batch update
```

### 11.10 전체 구조

```text
Source Stores
  Agent Profile Store
  Agent Topic Perspective Store
  Publish / Revoke Event Log

Projection
  Active Perspective Builder
  Topic Clusterer
  Embedding Generator

Serving Indexes
  Hot Vector Index by topic_cluster
  Metadata / Permission Index
  Precomputed Recommendation Buckets

Query Serving
  Query Understanding
  Topic Routing
  ANN Retrieval
  Metadata Push-down Filter
  Reranker
  Agent Grouping
```

현재 기준으로 꼭 지켜야 할 원칙은 세 가지다.

```text
1. 검색 단위는 agent가 아니라 agent-topic perspective다.
2. index는 source of truth가 아니라 projection이다.
3. hot active-set과 cold store를 분리한다.
```
