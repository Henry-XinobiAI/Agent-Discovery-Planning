# Agent Discovery & Recommendation - 방향 정리 (working base)

> 이 문서는 Agent Discovery & Recommendation의 설계 기준 베이스다. 아직 확정 스펙은 아니며, 단계별(Alpha/Open Beta) 범위와 컴포넌트 간 계약을 맞추기 위한 working document다.
>
> 메모리 구조는 `Agent_Memory_Vision.md`의 4계층 구조(L0 Record -> L1 Capsule -> L2 Personal Knowledge -> L3 Public Knowledge)를 전제로 둔다.
>
> 기존 discovery 문서(`agent_discovery_service_contract.md`, `agent_matching_candidates_for_mvp.md`, `agent_persona_extraction_and_representation.md`, 메인 문서 7~8장)는 참고용 lineage로만 본다. 이 문서가 이후 논의의 기준 베이스다.

## 0. 한 페이지 요약

### 우리가 만들려는 것

Agent Discovery는 유저가 어떤 주제에 대해 대화할 agent를 찾도록 돕는 시스템이다.

두 가지 모드가 있다.

| 모드 | 설명 | 출력 |
|---|---|---|
| **모드 A: 명시적 요청 추천(pull)** | 유저가 직접 "이 주제로 agent 추천해줘"라고 요청 | 후보 리스트 |
| **모드 B: 맥락 기반 추천(push)** | 대화 중 시스템이 "지금 다른 agent가 도움이 될 수 있다"고 감지 | 인라인 추천 또는 침묵 |

모드 B가 더 어렵다. 대화 중 끼어드는 추천이기 때문에 틀리면 방해가 된다. 그래서 먼저 "지금 어떤 Need인가"를 알아야 한다.

요청 방식과 내부 처리 단계는 별개의 구분이다.

- 요청 방식은 **pull / push**다. pull은 유저가 직접 추천을 요청하는 경우이고, push는 대화 중 시스템이 추천을 제안하는 경우다.
- 내부 처리 단계는 **Discovery / Recommendation**이다. Discovery는 topic을 anchor에 연결하고 후보 agent pool을 만든다. Recommendation은 그 후보 중에서 need에 맞는 agent를 고르고, 순서와 노출 방식을 정한다.

따라서 pull과 push 모두 **Discovery → Recommendation**을 거친다. pull이 Discovery이고 push가 Recommendation인 것이 아니다. Alpha에서는 pull을 먼저 노출하고, Open Beta에서는 push를 추가로 노출할 뿐이다. 단계별 책임 정의는 §5에 있다.

### Need 유형

| Need | 의미 | 핵심 신호 |
|---|---|---|
| **깊이/전문성** | 이 주제를 더 잘 아는 agent | maturity, evidence |
| **경험** | 직접 겪어본 agent | L1/L0 episode provenance |
| **유사성** | 취향/상황이 비슷한 agent | global persona similarity |
| **강화(for)** | 내 입장을 더 잘 뒷받침할 agent | 같은 축, 같은 방향 stance |
| **대립(against)** | 내 생각을 반대로 검증할 agent | 같은 축, 반대 방향 stance |
| **직교(orthogonal)** | 찬반이 아니라 다른 프레임을 열 agent | 다른 contested axis |

### 핵심 설계 원칙

1. **검색 단위는 agent-topic edge다.**  
   `anchor_id(QID) <-> agent_id` link를 기본 retrieval 단위로 쓴다.

2. **topic과 stance를 분리한다.**  
   "무슨 주제인가"와 "그 주제에서 어떤 입장인가"를 같은 벡터 하나에 섞지 않는다.

3. **prior와 maturity를 분리한다.**  
   global persona로 예상 stance는 채울 수 있다. 하지만 "이 주제를 깊이 아는가"는 관찰된 evidence로만 판단한다.

4. **목적함수는 Need마다 바뀐다.**  
   강화는 유사성을 찾지만, 대립/직교는 의도적으로 다른 관점을 찾는다. 단일 relevance score로 모두 처리하면 안 된다.

5. **평판은 보강 신호일 뿐 지배 항이 아니다.**  
   contribution은 Need별 validated memory impact로만 쌓는다. global reputation을 강하게 쓰면 popularity bias가 되살아난다.

### 범위와 단계 (Alpha / Open Beta / Post)

전체 산출은 세 단계로 나눈다.

| 단계 | 시점 | 노출 | 핵심 |
|---|---|---|---|
| **Alpha** | 7월 | 내부/closed | Pull 모드 user-facing. retrieval/ranking/serving 검증 |
| **Open Beta** | 8월말 | 외부 공개 | Push 모드 user-facing + orthogonal(조건부) + feedback logging |
| **Post-Open-Beta** | 이후 | — | memory impact·contribution·reputation·embedding 고도화 |

단계와 무관하게 기본 경로는 복잡한 임베딩/학습 모델 없이도 동작하도록 둔다. 핵심은 **구조화된 텍스트 필드와 간단한 규칙**이다.

**Alpha (7월, 내부/closed)** — Pull 중심.

| Alpha에서 한다 | 쉽게 말하면 |
|---|---|
| topic을 public anchor(QID)에 연결 | "커피 추출"을 `coffee brewing` 같은 표준 topic id에 붙인다 |
| anchor에 연결된 agent 후보를 찾는다 | 그 topic에 대해 말할 수 있는 agent들을 가져온다 |
| request text에서 topic·need_type·user_stance를 추출한다 | Pull에서는 stance를 항상 외부에서 주지 않으므로 Discovery가 요청 문장에서 뽑는다 |
| agent의 stance descriptor를 비교한다 | `stance_summary`, `axis_positions` 같은 사람이 읽을 수 있는 필드로 비교한다 |
| for/against를 coarse하게 판단한다 | 유저 입장과 같은 편/반대편인지 규칙·LLM으로 본다. established axis까지는 요구하지 않는다 |
| maturity/evidence/freshness로 후보를 거른다 | 근거가 얇거나 오래된 후보는 위로 올리지 않는다 |
| 기본 피드백 + decision-log를 기록한다 | 선택 여부·대화 길이·1-tap 평가, 그리고 나중 분석을 위한 추천 단위 로그를 남긴다 |
| Push DTO 초안 + shadow mode를 준비한다 | 실제 노출 없이 "이 시점에 추천/침묵했을 것"만 로깅한다 |

예를 들어 유저가 이렇게 말한다.

```text
나는 커피에서 산미가 제일 중요하다고 봐.
```

이런 식으로 추천한다.

| 추천 유형 | 찾는 agent | 단계 |
|---|---|---|
| for | 산미를 중요하게 보는 agent | Alpha |
| against | 바디감/고소함을 더 중요하게 보는 agent | Alpha |
| orthogonal | 맛 취향이 아니라 가격, 장비 관리, 윤리적 소비 같은 다른 축을 보는 agent | Open Beta |

**Open Beta (8월말, 외부 공개)** — Push와 orthogonal을 더한다.

| Open Beta에서 더한다 | 쉽게 말하면 |
|---|---|
| Push 모드 user-facing | 대화 중 top-1 또는 소수 추천, 기준 미달이면 침묵 |
| orthogonal 추천(조건부) | established/inherited_established axis가 있는 anchor에 한정. 근거 부족하면 coverage/against로 fallback |
| candidate safety + discoverability gate | 외부 공개이므로 후보 안전성·노출 동의를 hard 요건으로 적용(§11) |
| feedback logging 확대 + Need별 평가 | push impression/dismiss/accept, Need별 funnel, threshold 튜닝 |

orthogonal은 Pull/Push와 별개로 난도가 높다. 7월 시점엔 divergence mass가 부족할 수 있어 Open Beta 안에서도 best-effort로 둔다.

**Post-Open-Beta** — 충분한 데이터·검증이 쌓인 뒤에 한다.

| Post-Open-Beta | 왜 나중인가 |
|---|---|
| topic-conditioned perspective embedding | topic과 stance를 벡터에서 분리하는 작업은 난도가 높다 |
| supervised projection layer | 충분한 학습 데이터가 쌓인 뒤에 의미가 있다 |
| ideal-point/요인분해 기반 축 도출 | 많은 stance 데이터가 있어야 안정적으로 작동한다 |
| memory-impact 기반 contribution 학습 | 추천 후 L2 변화 추적이 준비된 뒤 가능하다 |
| advanced reputation learning | popularity bias 가드와 충분한 피드백 데이터가 필요하다 |
| full privacy/permission system | 별도 제품/정책 설계가 필요하다 (§11 결정 영역 참조) |

정리하면 초기 단계는 **상징 구조(symbolic descriptor)** 중심으로 간다. 임베딩은 나중에 비용, 속도, 규모 문제가 생길 때 추가한다.

---

## 1. 전제와 범위

### 1.1 메모리 substrate

Discovery가 직접 밟고 서는 데이터 기반은 다음이다.

```text
L3 public anchor(Wikidata QID)
  <-> agent의 personal node/link
  <-> stance/evidence/provenance metadata
```

여기서 `substrate`는 추천 알고리즘이 읽고 계산하는 밑바탕 데이터 구조라는 뜻이다.

### 1.2 privacy는 deferred

Privacy, 권한, 익명화, 공개 동의는 중요하지만 현재 문서에서는 상세 설계를 하지 않는다. 다만 discovery gate와 혼동하지 않기 위해 아래 세 축은 분리한다.

| 게이트 | 질문 | 소유 |
|---|---|---|
| **maturity** | 이 agent가 이 topic에 대해 근거 있게 말할 수 있나? | Discovery가 Memory raw signal로 계산 |
| **safety/reliability** | 보여주면 위험하거나 품질 문제가 있나? | Discovery 외부에서 verdict 제공 (결정 영역은 §11) |
| **privacy/eligibility** | 공개해도 되나? 동의/권한이 있나? | 별도 결정 영역 (§11) |

### 1.3 anchor-personal link는 discovery 대상이다

공통사실 승급 규칙과 anchor-personal link는 다르다.

공통사실 승급은 여러 사람에게서 공유되는 fact를 L3로 올리는 규칙이다. 반면 anchor-personal link는 특정 agent가 어떤 public anchor와 연결되어 있음을 나타내는 개인별 발견 포인터다. 따라서 이 link에 stance, evidence, provenance 같은 discovery metadata를 붙일 수 있다.

---

## 2. 두 모드와 Need

### 2.1 모드 A: 명시적 요청 추천(pull)

유저가 직접 요청한다.

```text
"커피 추출 방식에 대해 이야기할 agent 추천해줘."
```

특징:

- 후보 리스트를 보여준다.
- precision bar는 상대적으로 낮다. 유저가 직접 고를 수 있기 때문이다.
- Need가 없으면 coverage를 기본값으로 둔다.

### 2.2 모드 B: 맥락 기반 추천(push)

대화 중 moderation/runtime이 필요를 감지한다.

```text
현재 대화: 유저가 한 관점만 반복하고 있음
감지된 Need: orthogonal
출력: "다른 관점에서 이 문제를 본 agent가 있는데 연결해볼까요?"
```

특징:

- top-1 또는 소수 후보만 제안한다.
- precision bar가 높다.
- 기준을 넘지 못하면 추천하지 않고 침묵한다.

### 2.3 Need와 필요한 데이터

| Need | 필요한 데이터 | 비고 |
|---|---|---|
| 깊이/전문성 | maturity, evidence_strength, freshness | 표준 expert ranking에 가까움 |
| 경험 | episode provenance, source_type | 추상 지식이 아니라 직접 겪은 근거 |
| 유사성 | global persona | agent-level similarity |
| 강화 | user stance + same-axis alignment | 유저 입장이 필요 |
| 대립 | user stance + same-axis opposition | 유저 입장이 필요 |
| 직교 | user stance/persona + other-axis stance | contested axes가 필요 |

Invite/networking은 현재 범위 밖이다. 이 문서는 "사람을 연결"하는 설계가 아니라, publish된 관점을 agent가 매개해 소비하는 discovery 모델을 다룬다.

---

## 3. 핵심 데이터 모델

> anchor · anchor↔personal-node link · evidence는 `Agent_Memory_Vision.md`가 정의하는 **Memory substrate**다. 이 절은 그 substrate를 Discovery가 읽어 만드는 projection 관점에서 정리한 것이며, Discovery가 이 데이터를 소유하지 않는다.

### 3.1 세 층 표현

| 층 | 단위 | 역할 |
|---|---|---|
| **Topic anchor** | `anchor_id` | 무엇에 대한 이야기인가 |
| **Agent-topic edge** | `anchor_id <-> agent_id` | 이 agent가 이 topic에 대해 무엇을 알고/어떻게 생각하나 |
| **Global persona** | `agent_id` | 이 agent의 일반 성향, 스타일, 안정적 preference |

`agent_id`는 discovery/recommendation에 노출되는 **publish된 agent identity**다. 실제 사용자나 private memory owner를 직접 가리키는 id가 아니다.

```text
user_id
= 실제 사용자 / 소유자

agent_id
= discovery에 노출되는 publish된 agent identity

global_persona_projection
= agent_id에 붙은 공개 가능한 persona 요약
```

각 `agent_id`는 owner/user에 속하지만 `user_id`와 동일하지 않다. anchor-personal link, stance/evidence projection, contribution/reputation은 `agent_id`에 붙는다. `routing_target`은 `agent_id`와 같을 수도 있고, 별도의 대화 endpoint일 수도 있다.

### 3.2 Agent-topic edge에 담기는 정보

agent-topic edge는 knowledge signal과 stance signal을 나눠 가진다.

| 구분 | 의미 | prior 사용 |
|---|---|---|
| **Knowledge signal** | 이 topic에 대해 얼마나 근거가 있는가 | 금지 |
| **Stance signal** | 이 topic에서 어떤 입장인가 | 가능 |

초기 edge projection:

```json
{
  "anchor_id": "QID",
  "agent_id": "agent_id",
  "knowledge": {
    "topic_knowledge_maturity": 0.0,
    "evidence_strength": 0.0,
    "freshness": "...",
    "evidence_refs": ["L2/L1/L0 pointers"]
  },
  "stance": {
    "stance_summary": "...",
    "useful_for": ["for", "against", "orthogonal", "experience"],
    "axis_positions": [
      {
        "axis_id": "...",
        "value": "...",
        "value_confidence": 0.0,
        "source": "observed|prior",
        "evidence_refs": ["..."]
      }
    ],
    "estimate_source": "observed|prior",
    "estimate_confidence": 0.0
  },
  "versions": {
    "stance_space_version": "...",
    "global_profile_version": "..."
  },
  "routing_target": "..."
}
```

### 3.3 prior와 maturity

`prior`는 직접 관찰된 topic data가 부족할 때, global persona로 stance를 추정하는 값이다.

예:

```text
global persona:
- 실용주의적
- 비용 대비 효율 중시

관찰 없음:
- "커피 머신"에 대한 직접 stance 없음

prior stance:
- 고가 하이엔드보다 관리 쉽고 가성비 좋은 머신을 선호할 가능성
```

중요한 원칙:

```text
prior는 stance만 채운다.
maturity는 채우지 않는다.
```

이유는 단순하다. global persona로 "어디에 설 것 같은가"는 추정할 수 있다. 하지만 "이 주제를 깊이 아는가"는 실제 evidence가 있어야 한다.

관찰된 topic-specific stance와 global persona prior가 모두 있으면 둘을 섞어 `effective stance`를 만든다.

```text
effective stance
= observed topic stance와 global persona prior의 blend

observed stance가 충분히 성숙하고 일관적일수록 observed 쪽에 더 큰 가중치를 둔다.
```

### 3.4 maturity

`topic_knowledge_maturity`는 해당 agent가 특정 topic에 대해 얼마나 근거 있게 말할 수 있는지를 나타낸다.

Discovery가 계산하는 projection 값이며, 입력은 Memory가 제공하는 관찰 evidence raw signal이다.

```text
evidence volume
consistency
specificity
freshness
provenance quality
```

주의: 여기서 maturity는 engagement가 아니다. 유저가 오래 대화했다는 사실만으로 maturity를 올리면 안 된다.

---

## 4. Stance Space

### 4.1 왜 topic과 stance를 분리하나

일반 임베딩은 topic과 stance를 함께 섞는다.

```text
"커피는 산미가 중요하다"
= coffee topic + acidity preference + value judgment
```

Discovery에는 이 둘을 분리하는 구조가 필요하다.

```text
topic = coffee
stance = acidity is important
```

그래야 같은 topic 안에서 for/against/orthogonal을 계산할 수 있다.

### 4.2 전역 stance 공간은 만들지 않는다

"반대"는 항상 topic 안에서 정의된다.

```text
anti-coffee
anti-remote-work
```

이 둘은 같은 축이 아니다. 따라서 하나의 global stance vector space를 만들지 않는다.

대신 anchor별 local stance space를 둔다.

```text
anchor: coffee
axis_1: acidity <-> body
axis_2: convenience <-> ritual
axis_3: cost efficiency <-> premium experience
```

### 4.3 contested axes

`contested axis`는 한 topic 안에서 사람들이 실제로 갈라지는 쟁점 축이다.

도출 방식:

| anchor 상태 | 방법 |
|---|---|
| cold/young | LLM으로 coarse axis 추론 |
| sparse | KG 상위/이웃 anchor에서 axis 상속 |
| mature | aspect extraction, divergence, ideal-point/요인분해 |

Open Beta까지는 다음까지만 한다.

```text
1. LLM이 이름 붙인 coarse axes 생성
2. source를 observed / inherited / world-knowledge로 태깅
3. divergence mass가 충분하면 established
4. orthogonal 서빙은 established axis 또는 parent-established inherited axis에만 허용
```

기본 규칙은 보수적으로 둔다.

- `observed established` axis는 orthogonal 서빙에 사용할 수 있다.
- cold/sparse anchor가 상위 anchor의 `established` axis를 상속한 경우, 그 축은 `inherited_established`로 표시하고 orthogonal 서빙에 사용할 수 있다.
- LLM world-knowledge나 근거가 약한 inherited axis는 `provisional`로 둔다. 이 축은 후보 탐색이나 axis hint에는 쓸 수 있지만, orthogonal 추천을 직접 서빙하지 않는다.

이렇게 하면 cold anchor에서도 완전히 침묵하지 않되, 근거 없는 "거짓 쟁점"을 만들어 추천하는 위험을 줄인다.

Anchor-level contested axis projection 예시는 다음과 같다.

```json
{
  "anchor_id": "QID",
  "stance_space_version": "v1",
  "axes": [
    {
      "axis_id": "axis_acidity_body",
      "name": "산미 vs 바디감",
      "poles": ["acidity", "body"],
      "source": "observed|inherited|world-knowledge",
      "establishment": "established|inherited_established|provisional",
      "parent_anchor_id": "QID|null",
      "divergence_mass": 0.0,
      "confidence": 0.0
    }
  ]
}
```

### 4.4 for / against / orthogonal

| Need | 계산 방식 |
|---|---|
| for | 같은 axis에서 유저 stance와 가까운 후보 |
| against | 같은 axis에서 유저 stance와 반대인 후보 |
| orthogonal | 유저가 보지 않은 다른 axis에서 강한 stance를 가진 후보 |
| coverage | 여러 axis와 극단을 고르게 보여줌 |

orthogonal fallback은 orthogonal로 가장하지 않는다. 충분한 orthogonal 후보(established/inherited_established axis)가 없으면 silence하거나, coverage/against로 fallback하되 그 사실을 내부 `reason`/`fallback_type`에 명시한다. 즉 fallback이 일어나도 추천 의도(orthogonal)가 against·coverage로 조용히 바뀌지 않는다.

### 4.5 임베딩 도입은 Post-Open-Beta

초기 단계의 기본 경로는 임베딩 없이도 동작하도록 둔다.

```text
anchor partition
+ stance_summary
+ LLM/text comparison
+ coarse axis
```

이 조합으로도 실용적인 pseudo-disentanglement를 얻는다. 같은 anchor 안에서만 stance를 비교하면 topic 성분이 retrieval 단계에서 이미 고정되기 때문이다.

임베딩은 규모, 비용, latency 문제가 생길 때 Post-Open-Beta 단계로 도입한다.

| 단계 | 설명 |
|---|---|
| 2차 | LLM이 만든 stance-only text를 embed |
| 3차 | base embedding 위에 supervised projection layer 학습 |

주의: embedding model의 `dimensions` 파라미터는 차원 수 압축이지 topic/stance 분리가 아니다.

---

## 5. Retrieval과 Ranking

파이프라인은 두 내부 단계로 나뉜다. **Discovery 단계**는 topic을 anchor에 grounding하고 agent-topic edge를 조회·게이팅해 후보 공간을 만든다. **Recommendation 단계**는 그 후보 중 `need_type`에 맞게 stance 연산·ranking·serving·push silence를 수행하고, feedback 기반 평가/튜닝을 책임진다. pull과 push 모두 이 두 단계를 거치며, Alpha/Open Beta는 어떤 모드를 먼저 노출할지에 대한 일정 구분이다(§0).

### 5.1 공통 파이프라인

```text
[Discovery 단계 — 후보 공간 구성]

1. 입력 정규화
   topic, need_type, user_stance_ref?, requester_persona_ref?

2. anchor 해소
   topic -> Wikidata QID + KG 이웃 확장

3. 후보 retrieval
   anchor partition에서 agent-topic edge 조회

4. gate
   on-topic
   maturity >= floor_need
   candidate safety/reliability verdict (Alpha 내부 inactive, 외부 공개 시 active — §11)
   eligibility/privacy (Alpha 내부 inactive, 외부 공개 시 active — §11)

-> 출력: need-complete candidate pool

[Recommendation 단계 — need-conditioned 선택/서빙]

5. Need별 stance 연산
   for / against / orthogonal / depth / experience / similarity

6. ranking
   need-specific weighted score + diversity

7. serving
   후보 + 설명 + routing_target + push silence

8. feedback logging
   acceptance, turns, explicit feedback (memory impact는 Post-Open-Beta)
```

경계 계약: Discovery는 affinity로 과도하게 pruning하지 않은 **need-complete candidate pool**을 Recommendation에 넘긴다. `need_type`은 Recommendation의 objective를 정하지만, 규모가 커지면 recall 최적화를 위해 Discovery retrieval 단계에도 전달될 수 있다(§5.4).

### 5.2 score template

```text
gate:
  on-topic
  AND maturity >= floor_need
  AND candidate safety/reliability pass (Alpha 내부 inactive, 외부 공개 시 active — §11)
  AND eligibility/discoverability pass (Alpha 내부 inactive, 외부 공개 시 active — §11)

score_need:
  alpha * stance_term
  + beta * maturity
  + gamma * freshness
  + delta * persona_similarity
  + epsilon * experience_specificity
  + zeta * novelty
  + eta * validated_contribution_need (Post-Open-Beta / inactive)
```

Need가 바꾸는 것은 두 가지다.

1. stance 연산 방식
2. 각 항의 가중치와 floor

### 5.3 Need별 ranking

| Need | stance term | 주요 가중치 |
|---|---|---|
| 깊이 | 없음 | maturity, evidence, freshness |
| 경험 | 없음 | episode specificity, situation match |
| 유사성 | 없음 | persona similarity |
| 강화 | positive alignment | stance alignment, maturity |
| 대립 | opposition | opposition, maturity, contribution |
| 직교 | off-axis strength | axis novelty, maturity, contribution |

`contribution`은 Post-Open-Beta 신호다. 표에서 대립/직교에 특히 표시한 이유는 이 두 Need에서 engagement가 value proxy로 가장 위험하기 때문이다. 깊이/경험/강화에도 나중에 contribution을 쓸 수 있지만, Open Beta까지의 ranking에는 어떤 Need에서도 contribution을 사용하지 않는다(contribution은 Post-Open-Beta).

### 5.4 기존 recommender와 다른 점

기존 추천은 대체로 affinity를 최적화한다.

이 시스템은 Need에 따라 방향이 달라진다.

```text
강화 = affinity 추천
대립 = anti-affinity 추천
직교 = 다른 frame 추천
```

따라서 하위 retrieval이 이미 affinity 후보만 가져오면 대립/직교 후보는 사라진다. wrapper로 재정렬하는 방식만으로는 부족하다. retrieval 단계부터 Need-aware여야 한다.

---

## 6. Feedback, Contribution, Reputation

**단계 구분이 먼저다.** Feedback logging과 기본 평가는 Open Beta 범위이고, memory impact·contribution·reputation은 Post-Open-Beta다. Open Beta의 목표는 "추천을 평가할 수 있다"이지 "자동 학습/평판 루프를 닫는다"가 아니다.

- Open Beta까지 (§6.1–6.2): feedback logging, implicit/explicit signal 수집, 운영 평가(Need별 funnel, threshold 튜닝).
- Post-Open-Beta (§6.3–6.5): memory impact, validated L2 delta, contribution score, reputation guard.

### 6.1 Open Beta feedback logging

추천 단위(decision log)로 남긴다. 이 골격은 분석이 Open Beta여도 **Alpha에서 설계해 넣는다**(나중 retrofit이 비쌈).

- 추천 요청/노출 단위: `request_id`, mode(pull|push), `need_type`, topic/anchor_id, axis_hint, user_stance 유무, candidate list, ranking score snapshot, reason shown, evidence_refs 유무, routing_target
- Implicit: impression, click/select, no-click, dismiss, 대화 시작 여부, turns, duration, early exit, re-engagement, (push) silence 여부
- Explicit: 1-tap helpful/not-helpful, agent가 topic에 맞았는지, 추천 이유가 이해됐는지, for/against/orthogonal 의도가 맞았는지, 간단한 not-helpful reason

분석은 Need별로 한다: depth 선택률, against helpful rate, orthogonal dismiss rate, push silence rate, push 노출 후 dismiss/accept 비율, topic/stance mismatch 비율.

### 6.2 feedback을 reward로 쓰지 않는다

유저가 추천을 클릭했는지와 추천이 실제로 가치 있었는지는 다르다. Open Beta feedback은 candidate quality, topic/stance mismatch, UX friction, push intrusiveness를 진단하고 threshold·product policy를 조정하기 위한 **운영 신호**이며, 곧바로 ranking 정답 라벨이나 contribution/reputation score로 환산하지 않는다.

| 신호 | 의미 | 위험 |
|---|---|---|
| acceptance | 카드가 선택됨 | position/popularity bias |
| turns | 대화가 오래 지속됨 | 대립/직교는 짧아도 좋을 수 있음 |
| implicit sentiment | 즉시 반응 | friction을 나쁨으로 오해 가능 |
| 1-tap explicit feedback | 희소한 직접 평가 | UX 비용, peak-end bias |
| memory impact | 실제 L2 변화 | 느리지만 가장 중요한 value signal (Post-Open-Beta) |

- acceptance가 높다 ≠ 좋은 추천
- turns가 길다 ≠ 좋은 추천
- dismiss가 있다 ≠ 나쁜 추천

특히 대립/직교는 대화가 짧고 불편해도 가치 있을 수 있고, 유사성/강화는 engagement가 높아도 echo chamber를 강화할 수 있다. 그래서 against/orthogonal은 성공 지표 자체를 다르게 정의한다(예: orthogonal = 새 축에 engage했는지, 이후 그 축을 다시 언급했는지).

### 6.3 Post-Open-Beta: memory impact

가장 중요한 value signal은 추천 대화 후 유저의 L2 지식/stance가 실제로 바뀌었는지다.

예:

| Need | 좋은 impact |
|---|---|
| 깊이 | 새 fact node 생성 |
| 대립 | 기존 stance가 정교화됨 |
| 직교 | 보지 않던 axis에 새 입장이 생김 |
| 경험 | 구체 episode가 의사결정에 도움 |

단, 모든 변화가 좋은 것은 아니다. 정보폭탄이나 stance 교란을 보상하면 안 된다.

따라서 contribution으로 인정되는 변화는 다음 조건을 만족해야 한다.

```text
durable
+ validated
+ recommendation conversation에 attribution 가능
```

### 6.4 Post-Open-Beta: contribution score

memory impact는 contribution score로 누적한다.

분리해서 쌓는다.

```text
agent-level contribution
topic-level contribution
need-level contribution
```

절대 하나의 global popularity score로 뭉치지 않는다.

나쁜 설계:

```text
global_score = 평균 만족도 + 평균 대화 길이 + 선택률
```

좋은 설계:

```json
{
  "depth": "validated new knowledge",
  "against": "validated stance refinement",
  "orthogonal": "validated new axis opened",
  "experience": "validated episode usefulness",
  "similarity": "peer-fit satisfaction"
}
```

### 6.5 Post-Open-Beta: reputation guard

평판은 추천을 보강해야지 popularity prior가 되면 안 된다.

| 신호 | 위치 | 이유 |
|---|---|---|
| safety/reliability | hard gate | 위험과 novelty는 trade-off하지 않음 |
| topic-local credibility | maturity/evidence | 이미 edge knowledge signal에 있음 |
| validated contribution | Need-specific booster | 실제 memory impact만 반영 |
| global reputation | tie-breaker/weak prior | 지배 항이면 rich-get-richer 발생 |

신규 agent는 contribution 이력이 없어도 exploration 슬롯을 받을 수 있어야 한다. contribution은 booster이지 floor나 penalty가 아니다.

---

## 7. 모드별 흐름

### 7.1 모드 A: 명시적 요청 추천(pull)

```text
1. 유저 요청에서 topic과 optional Need 추출
2. topic을 anchor로 grounding
3. 후보 edge retrieval
4. Need가 없으면 coverage
5. Need가 있으면 Need별 ranking
6. 후보 리스트 제공
7. 선택/대화/피드백 logging
```

모드 A는 best-effort 리스트를 반환한다.

### 7.2 모드 B: 맥락 기반 추천(push)

```text
1. moderation/runtime이 typed request 발행
2. discovery가 anchor grounding + retrieval
3. maturity/candidate-safety gate 적용
4. Need별 ranking
5. threshold를 넘으면 top-1 또는 소수 추천
6. threshold를 못 넘으면 침묵
```

모드 B의 핵심은 침묵 옵션이다. 약한 추천으로 대화를 방해하지 않는다.

### 7.3 query-side contract

모드 B에서 Discovery는 Need를 직접 감지하지 않는다. moderation/runtime이 typed request를 준다.

예상 DTO:

```json
{
  "mode": "pull|push",
  "topic": "...",
  "topic_candidates": ["..."],
  "anchor_hint": "...",
  "axis_hint": "...",
  "need_type": "depth|experience|similarity|for|against|orthogonal|coverage",
  "need_confidence": 0.0,
  "user_stance_ref": "...",
  "stance_confidence": 0.0,
  "requester_persona_ref": "...",
  "context_safety_verdict": {
    "status": "pass|block|unknown",
    "confidence": 0.0
  }
}
```

`context_safety_verdict`는 "지금 이 대화 맥락에서 추천을 시도해도 되는가"에 대한 query-level verdict다.

후보 agent 자체의 안전성은 query DTO 하나로 표현할 수 없다. 후보별 safety/reliability는 candidate projection 또는 moderation-provided candidate verdict로 들어와야 하며, §5.2의 hard gate에서 per-candidate로 적용된다.

Push에서 추천할지 침묵할지 결정하는 threshold는 query input으로 받지 않는다. `silence_threshold`는 Recommendation 단계의 serving policy로 두고, mode·Need·후보 점수·제품 정책에 따라 적용한다.

---

## 8. Anchor 해소와 KG 확장

Anchor 해소는 topic text를 Wikidata QID로 grounding하는 단계다.

```text
"푸어오버 커피" -> QID 후보
```

KG 확장은 정확히 같은 QID에 붙은 edge만 보지 않고, 관련 anchor까지 넓히는 단계다.

대부분은 commodity 기술을 재활용한다.

```text
entity linking
disambiguation
KG traverse
hop distance decay
ANN retrieval
KG embedding
```

프로젝트 고유 설계는 세 가지다.

### 8.1 granularity 선택

질의가 여러 레벨에 걸칠 수 있다.

```text
푸어오버
커피 추출
커피
```

너무 구체적이면 cold/sparse해지고, 너무 일반적이면 noisy해진다. 원칙은 다음이다.

```text
maturity density가 충분한 가장 구체적인 anchor를 고른다.
```

정확한 threshold는 Alpha 전 결정이 필요하다.

### 8.2 aspect -> axis hint

질의가 topic이 아니라 쟁점일 수 있다.

```text
"커피의 가성비 문제"
```

이 경우 출력은 topic만이 아니라 `(anchor, axis_hint)`가 되어야 한다.

### 8.3 상위 anchor 축 상속

KG 위로 확장하는 것은 recall만을 위한 게 아니다. cold anchor에서 contested axes를 상속하는 역할도 한다.

```text
specific anchor가 sparse
-> parent anchor의 established axes를 inherited_established로 상속
```

상위 anchor에서도 established가 아닌 축은 `provisional`로만 상속한다. `inherited_established`는 orthogonal 서빙에 사용할 수 있지만, `provisional`은 후보 탐색과 axis hint에만 사용한다.

---

## 9. Discovery 입력 source (input contract)

Discovery는 source of truth가 아니다. 다른 컴포넌트(Memory, Persona, Moderation/Runtime)가 raw signal을 제공하고, Discovery가 retrieval/ranking용 projection을 만든다.

### 9.1 Source: Memory

| 데이터 | 이유 |
|---|---|
| anchor-personal node link | discovery의 retrieval 단위 |
| `evidence_volume`, `consistency`, `specificity` | Discovery가 `topic_knowledge_maturity`와 `evidence_strength`를 계산하기 위한 입력 |
| `freshness` | stale 정보 decay |
| `evidence_refs` | explanation, experience, attribution |
| `experience flag`, `source_type` | experience Need |
| post-conversation L2 delta + provenance | memory impact, contribution |

### 9.2 Source: Persona

| 데이터 | 이유 |
|---|---|
| global persona / stable core | prior, similarity, orthogonal 기준 frame |
| persona_maturity, consistency | prior 신뢰도 조절 |
| global_profile_version | 추천용 projection/cache/index를 갖게 되면 stale 식별에 필요 |

Global persona는 topic별 stance가 부족할 때 prior로 쓴다. 단, maturity를 올리는 데는 쓰지 않는다.

### 9.3 Source: stance (observed = Memory, prior = Persona)

Stance의 소유는 "Memory냐 Persona냐"의 양자택일이 아니라 **source로 나뉜다**. §3.2 스키마가 이미 stance를 `observed|prior`로 태깅하고, §3.3이 둘을 blend해 effective stance를 만든다.

| stance 종류 | source of truth | 제공자 |
|---|---|---|
| **observed** topic-specific stance | L2 opinion/preference/judgment node | Memory |
| **prior** stance | stable persona/preference | Persona |
| effective stance + `axis_positions` projection | (위 둘의 blend·계산) | Discovery가 derive |

stance의 원본은 observed면 L2 opinion/preference/judgment node(Memory)에, prior면 stable persona(Persona)에 있다. Discovery가 사용하는 stance는 agent-topic edge에 붙은 topic-specific projection이며, observed stance는 edge에서 **읽고**(edge는 Memory substrate이므로 Discovery가 소유·기록하지 않는다), `axis_positions`·effective stance는 Discovery가 **derive**한다.

| 데이터 | 이유 |
|---|---|
| opinion/stance content per `(agent, anchor)` (observed) | stance matching, axis derivation |
| extraction_confidence | axis confidence, estimate confidence |

이 observed/prior 소유 구분은 Alpha의 for/against가 성립하기 위한 선결 합의다(§10). 어떤 Need(for/against/orthogonal)에 맞는지는 producer가 태깅하지 않는다. Discovery가 request-time에 `user_stance_ref`·`need_type` 대비 판단한다(§4.4). lived experience 적합성은 Memory의 `experience flag`/`source_type`로 충분하다.

### 9.4 Source: Moderation / Runtime

| 데이터 | 이유 |
|---|---|
| `mode` | pull/push 동작 차이 |
| `need_type` | Recommendation objective 선택. 필요 시 Discovery retrieval recall에도 전달 |
| `need_confidence` | push precision control |
| `user_stance_ref` | for/against/orthogonal 기준점 |
| `requester_persona_ref` | similarity와 orthogonal 기준 frame |
| `context_safety_verdict` | 현재 대화 맥락에서 추천을 시도해도 되는지 판단 |
| candidate-level `safety/reliability verdict` | 후보별 hard gate |

`topic_candidates`, `anchor_hint`, `axis_hint`는 moderation/runtime이 줄 수도 있고 Discovery의 anchor 해소 단계(§8)가 만들 수도 있다. 둘 다 있으면 Discovery가 disambiguation과 confidence를 기준으로 최종 anchor/axis를 정한다.

`context_safety_verdict`와 candidate-level `safety/reliability verdict`는 Alpha(내부/closed)에서는 inactive로 두고, 외부 공개(Open Beta) 시 hard gate로 활성화한다. Push 자체는 Open Beta 목표지만, 이 verdict와 query DTO 계약은 Alpha 동안 확정해 shadow mode로 검증한다. 결정해야 할 주제는 §11에 정리한다.

### 9.5 Discovery / Recommendation 단계가 내부에서 derive하는 것

다른 source가 만들 필요 없는 것. 어느 내부 단계가 derive하는지로 나눈다(§5).

```text
[Discovery 단계 derive — 후보 공간/projection]
topic_knowledge_maturity
evidence_strength
prior-fill
contested axes
axis_positions projection
axis confidence calibration
stance_space_version (projection/cache/index 도입 시)
topic-conditioned embedding (Post-Open-Beta)

[Recommendation 단계 derive — objective/serving]
ranking/objective
serving policy / silence_threshold
contribution/reputation score (Post-Open-Beta)
```

`prior-fill`·`axis_positions projection`은 Discovery가 derive하지만 Recommendation의 for/against/orthogonal objective가 강하게 소비한다.

### 9.6 Lifecycle events (projection/cache/index 도입 시)

초기에는 Discovery가 추천 요청마다 필요한 source 데이터를 그때그때 가져와서 사용할 수 있다. 이 경우 lifecycle 이벤트는 초기 필수가 아니다.

다만 추천 품질·속도·규모를 위해 Discovery가 자체 추천용 projection/cache/index를 갖게 되면, source 변경을 반영하기 위한 lifecycle 이벤트가 필요해진다.

필요해질 이벤트:

```text
publish
update
revoke
```

소유:

| 이벤트 대상 | source |
|---|---|
| anchor-personal link | Memory |
| stance content | observed=Memory, prior=Persona (§9.3) |
| global persona | Persona |
| safety verdict | Discovery 외부 (§11) |
| privacy/eligibility | 별도 결정 영역 (§11) |

Safety/privacy verdict의 lifecycle은 해당 기능을 도입하는 시점에 함께 정한다(§11). 후보 agent나 특정 routing target이 나중에 unsafe로 판정되는 구조를 도입하면, Discovery 외부에서 update 또는 revoke 이벤트가 발행되고 Discovery는 해당 candidate projection을 재계산하거나 gate에서 제외한다.

---

## 10. Open Questions

### Alpha 전에 결정해야 하는 것

- **stance content의 observed/prior source 소유 확정** (Alpha 선결, §9.3) — for/against 성립 전제
- granularity 선택 기준: "충분한 maturity density"의 임계값
- `floor_need` 기본값과 Need별 maturity floor
- request text에서 topic·need_type·user_stance를 뽑는 추출 경로

### Open Beta 전에 결정해야 하는 것

- `established` contested axis 판정 기준: divergence mass threshold
- `axis_positions`를 extraction 시점에 채울지, serving 시점에 lazy 계산할지
- `need_type` / `context_safety_verdict` / candidate-level safety verdict 스키마
- Mode B silence policy와 Need별 threshold 기본값
- discoverability opt-in과 candidate safety gate 활성화 기준 (§11)

### Post-Open-Beta로 미룬 것

- topic-conditioned perspective embedding
- supervised projection layer
- ideal-point/요인분해 기반 mature axis derivation
- full privacy/visibility/permission model
- memory-impact 기반 contribution learning
- global reputation tuning
- embedding model versioning과 full re-embed policy
- two-sided matching / invite / networking

### 주요 리스크와 가드

| 리스크 | 가드 |
|---|---|
| popularity bias | global reputation은 tie-breaker/weak prior로 제한 |
| rich-get-richer | 신규 agent exploration 슬롯 보장 |
| reputation farming | durable + validated memory impact만 contribution 인정 |
| sycophancy drift | 대립/직교는 engagement로 평가하지 않음 |
| false controversy | established / inherited_established axis만 orthogonal 서빙에 사용 |
| hollow agent | prior로 maturity를 채우지 않음 |

---

## 11. 공개 전 결정해야 할 Safety / Privacy 주제

Alpha는 내부/closed 범위로 운영하므로 safety/privacy 게이트 없이 Pull 파이프라인 검증에 집중한다. **따라서 아래 결정 영역들이 해소되기 전에는 외부 공개(Open Beta 포함)로 노출하지 않는다.** 이 절은 결정해야 할 *주제*를 모은 것이지 예정된 구현 작업 목록이 아니며, 로드맵 단계와 별개다.

세 게이트는 직교한다(§1.2): maturity는 Discovery가 계산하고, safety와 privacy는 Discovery 외부에서 verdict/정책으로 들어온다.

### 11.1 Safety / reliability

| 주제 | 결정해야 할 것 | 언제 필요한가 |
|---|---|---|
| candidate verdict | 무엇을 단언하나(이 agent를 노출해도 품질·위험상 괜찮은가), 스키마(pass/block/unknown + confidence) | 외부 공개(Open Beta) |
| context verdict | 지금 이 대화 맥락에서 추천을 시도해도 되나 (push) | Push(Open Beta) |
| 적용 지점 | hard gate를 후보별·맥락별로 어디서 적용하나 | 외부 공개 |
| unknown 처리 | verdict가 unknown일 때 fail-open이냐 fail-closed냐 | 외부 공개 |
| lifecycle | 후보·routing target이 나중에 unsafe로 판정되면 revoke/update → Discovery가 재계산·제외 | projection/cache 도입 시 |

safety와 novelty는 trade-off하지 않는다(§6.4). 따라서 safety는 weak prior가 아니라 hard gate다.

### 11.2 Privacy / eligibility

| 주제 | 결정해야 할 것 | 언제 필요한가 |
|---|---|---|
| discoverability opt-in | 이 agent를 애초에 후보로 노출해도 되나(owner 동의) — 최소 1비트 | 외부 공개(Open Beta) |
| 노출 입도 | 후보에 대해 무엇까지 보여주나 — description 수준(`stance_summary`, 근거 존재 여부)이지 raw memory 내용은 아님 | 외부 공개 |
| provenance 노출 | `evidence_refs`를 추천 이유로 보일 때 출처를 얼마나 드러내나(익명 vs attributed) | 외부 공개 |
| routing_target 노출 | 연결 endpoint를 어디까지 노출하나 | 외부 공개 |
| 동의 범위·철회 | 토픽별이냐 전역이냐, 철회 시 전파 방식 | 외부 공개 |
| 공통사실 승급과의 관계 | L3 공통사실 승급의 익명·권한 link 정책과 일관되게 둘 것 | full privacy 설계 시 |

full privacy/permission 시스템은 Post-Open-Beta다(§10). 다만 외부 공개의 선결 조건은 단순한 opt-in 1비트가 아니라 **minimum external eligibility layer**다 — discoverability opt-in에 더해 `routing_target`·provenance·`stance_summary`의 노출 입도까지 외부 공개 전에 결정해야 한다. full privacy/permission 시스템과 이 최소 layer의 경계가 §11의 핵심 구분이다.
