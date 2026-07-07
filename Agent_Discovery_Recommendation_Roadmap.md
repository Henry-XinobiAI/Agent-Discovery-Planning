# Agent Discovery & Recommendation Roadmap

> Agent Discovery & Recommendation은 사용자가 어떤 주제에 대해 대화할 만한 agent를 찾고, 대화 흐름 안에서 필요한 경우 적절한 agent를 추천하는 시스템이다.
>
> 핵심은 "비슷한 사람 추천"만이 아니다. 어떤 상황에서는 같은 입장을 강화해줄 agent가 필요하고, 어떤 상황에서는 반대 관점이나 완전히 다른 프레임을 열어줄 agent가 필요하다. 그래서 추천 목적은 대화 맥락과 need에 따라 달라진다.

핵심 통찰: **public anchor는 정답을 보관하는 장소가 아니라, 특정 주제를 잘 아는 agent와 그 agent의 관점으로 가는 연결점이다.** Discovery는 이 연결을 이용해 "누가 이 주제에 대해 말할 가치가 있는가"를 찾는다.

---

## 1. 무엇을 다루는가

이 문서는 Agent Discovery & Recommendation의 개발 방향을 간단히 공유하기 위한 문서다.

다루는 범위:

- 유저가 직접 agent를 찾는 **명시적 요청 추천(pull)**
- 대화 중 시스템이 필요를 감지해 제안하는 **맥락 기반 추천(push)**
- topic, stance, evidence, persona를 이용한 후보 검색과 랭킹
- memory/persona/moderation 팀이 discovery에 제공해야 하는 입력 계약

다루지 않는 범위:

- 사람 대 사람 연결, invite, networking
- full privacy/permission 설계
- 고도화된 reputation learning
- topic-conditioned embedding 또는 별도 학습 모델

현재 목표는 memory/persona 구조 위에서 작동하는 추천 파이프라인의 입력, 출력, 컴포넌트 간 계약을 맞추는 것이다.

일정은 세 단계로 나눈다.

| 단계 | 노출 | 핵심 |
| --- | --- | --- |
| **Alpha** | 내부/closed | Pull 모드 user-facing. retrieval/ranking/serving 검증 |
| **Open Beta** | 외부 공개 | Push 모드 user-facing + orthogonal(조건부) + feedback logging |
| **Post-Open-Beta** | — | memory impact·contribution·reputation·embedding 고도화 |

Alpha의 1차 산출물은 **topic과 need를 입력받아 Pull 모드로 추천 가능한 agent 후보(`agent_id`), 추천 이유를 반환하는 API**다. 내부 구현은 request-time fetch로 시작하고, 필요하면 projection/cache/index로 확장한다. (`routing_target`은 계약에서 제거 — dispatch는 bourbon-api 런타임 해석.)

내부적으로는 **Discovery 단계**와 **Recommendation 단계**를 구분한다.

- **Discovery 단계** = topic을 anchor에 grounding하고, agent-topic edge를 조회·게이팅해 후보 공간을 만든다.
- **Recommendation 단계** = 그 후보 중 `need_type`에 맞게 stance 연산, ranking, serving, push silence, 평가/튜닝을 수행한다.

요청 방식과 내부 처리 단계는 별개의 구분이다. 요청 방식은 pull / push이고, 내부 처리 단계는 Discovery / Recommendation이다.

따라서 pull과 push 모두 **Discovery → Recommendation**을 거친다. pull이 Discovery이고 push가 Recommendation인 것이 아니다. Alpha에서는 pull을 먼저 노출하고, Open Beta에서는 push를 추가로 노출할 뿐이다. 상위명 "Agent Discovery & Recommendation"은 이 두 내부 단계를 함께 가리킨다.

---

## 2. 추천의 두 모드

| 모드 | 설명 | 결과 |
| --- | --- | --- |
| **명시적 요청 추천 (pull)** | 사용자가 직접 "이 주제로 이야기할 agent 추천해줘"라고 요청 | 후보 리스트 |
| **맥락 기반 추천 (push)** | 대화 중 runtime/moderation이 다른 agent가 도움이 될 상황을 감지 | 인라인 추천 또는 침묵 |

명시적 요청 추천은 사용자가 직접 고르기 때문에 best-effort 후보 리스트를 반환할 수 있다.

맥락 기반 추천은 대화에 끼어드는 추천이므로 기준이 더 높다. 충분히 좋은 후보가 없으면 추천하지 않고 침묵한다.

---

## 3. Need (intent/objective type)

추천은 하나의 목적만 갖지 않는다. 대화 상황에 따라 필요한 agent의 종류가 다르다.

| need | 의미 | 예 |
| --- | --- | --- |
| **깊이/전문성** | 이 주제를 더 깊이 아는 agent | "이 기술을 실제로 잘 아는 사람" |
| **경험** | 직접 해봤거나 겪어본 agent | "이걸 실제로 써본 사람" |
| **유사성** | 취향이나 상황이 비슷한 agent | "나와 비슷한 사람이 뭘 선택했는지" |
| **강화(for)** | 내 입장을 더 잘 뒷받침할 agent | "내 생각을 더 탄탄하게 해줄 사람" |
| **대립(against)** | 내 입장을 반대로 검증할 agent | "반대편에서 문제를 짚어줄 사람" |
| **직교(orthogonal)** | 찬반이 아니라 다른 프레임을 열 agent | "전혀 다른 기준으로 보는 사람" |

---

## 4. 핵심 데이터 모델

Discovery의 기본 검색 단위는 **agent-topic edge**다.

```text
public anchor(QID)
  <-> agent
  <-> topic-specific metadata
```

> anchor · anchor↔personal-node link · evidence는 `Agent_Memory_Vision.md`가 정의하는 **Memory substrate**다. Discovery는 이를 소유하지 않고, 읽어서 추천용 projection을 만든다.

### 4.1 세 층 구조

| 층 | 단위 | 역할 |
| --- | --- | --- |
| **Topic anchor** | `anchor_id` | 무엇에 대한 이야기인가 |
| **Agent-topic edge** | `anchor_id <-> agent_id` | 이 agent가 이 topic에 대해 무엇을 알고, 어떤 입장을 갖는가 |
| **Global persona** | `agent_id` | 이 agent의 일반 성향, 스타일, 안정적 preference |

`agent_id`는 discovery/recommendation에 노출되는 publish된 agent identity다. 실제 사용자 id나 private memory owner id와는 다르다.

```text
user_id = 실제 사용자 / 소유자
agent_id = 공개 가능한 agent identity
global_persona_projection = agent_id에 붙은 공개 가능한 persona 요약
```

추천, contribution, reputation, routing metadata는 `user_id`가 아니라 `agent_id` 기준으로 붙는다.

### 4.2 Agent-topic edge에 담기는 정보

agent-topic edge는 두 종류의 정보를 가진다.

| 구분 | 의미 | 사용처 |
| --- | --- | --- |
| **Knowledge** | 이 topic에 대해 근거 있게 말할 수 있는가 | maturity gate, expert ranking |
| **Stance** | 이 topic에서 어떤 입장인가 | for/against/orthogonal 추천 |

중요한 원칙:

```text
prior는 stance만 채운다.
maturity는 채우지 않는다.
```

Global persona를 보면 어떤 입장을 가질지 추정할 수는 있다. 하지만 그 topic을 실제로 깊이 아는지는 evidence로만 판단해야 한다.

---

## 5. 단계별 추천 방식

Alpha(내부/closed)에서 먼저 다루는 범위:

| Alpha에서 한다 | 의미 |
| --- | --- |
| topic을 public anchor(QID)에 연결 | 유저의 topic을 표준 anchor로 grounding |
| anchor에 연결된 agent 후보 조회 | 해당 topic을 가진 agent-topic edge 검색 |
| request text에서 topic·need_type·user_stance 추출 | Pull에서는 stance를 항상 외부에서 주지 않으므로 Discovery가 요청 문장에서 뽑음 |
| stance descriptor 비교 | 사람이 읽을 수 있는 `stance_summary`, `axis_positions` 등으로 비교 |
| for/against coarse 판단 | 유저 입장과 같은 편/반대편 비교. established axis까지는 요구하지 않음 |
| maturity/evidence/freshness gate | 근거가 얇거나 오래된 후보를 낮춤 |
| 기본 피드백 + decision-log 기록 | 선택 여부·대화 길이·1-tap, 그리고 나중 분석용 추천 단위 로그 |

Open Beta(외부 공개)에서 더하는 범위:

| Open Beta에서 더한다 | 의미 |
| --- | --- |
| Push 모드 user-facing | 대화 중 top-1/소수 추천, 기준 미달이면 침묵 |
| orthogonal 추천(조건부) | established/inherited_established axis가 있는 anchor에 한정. 부족하면 coverage/against로 fallback |
| candidate safety + discoverability gate | 외부 공개이므로 후보 안전성·노출 동의를 hard 요건으로 적용(§11) |
| feedback logging 확대 + Need별 평가 | push impression/dismiss/accept, Need별 funnel, threshold 튜닝 |

예:

```text
유저: 나는 커피에서 산미가 제일 중요하다고 봐.
```

| 추천 유형 | 찾는 agent | 단계 |
| --- | --- | --- |
| for | 산미를 중요하게 보는 agent | Alpha |
| against | 바디감이나 고소함을 더 중요하게 보는 agent | Alpha |
| orthogonal | 맛 취향이 아니라 가격, 장비 관리, 윤리적 소비 같은 다른 축을 보는 agent | Open Beta |

---

## 6. Retrieval과 Ranking 흐름

공통 파이프라인은 두 내부 단계로 나뉜다. **Discovery 단계**가 후보 공간을 만들고, **Recommendation 단계**가 그 후보를 need에 맞게 선택·서빙한다(§1).

```text
[Discovery 단계 — 후보 공간 구성]

1. 입력 정규화
   topic, need_type, user_stance_ref, requester_persona_ref

2. anchor 해소
   topic -> Wikidata QID 또는 자체 anchor

3. 후보 검색
   anchor에 연결된 agent-topic edge 조회

4. gate
   on-topic
   maturity floor
   discoverability / eligibility pass (Alpha active — eval gate, mock/eval에서도 지킴)
   (safety / privacy gate: Alpha 내부 inactive, 외부 공개 시 active — §11)

-> 출력: need-complete candidate pool

[Recommendation 단계 — need-conditioned 선택/서빙]

5. need별 연산
   depth / experience / similarity / for / against / orthogonal

6. ranking
   need-specific lexicographic ordering + diversity (Alpha: 가중합 scalar score 아님, ordering contract)

7. serving
   후보(agent_id), 설명, push silence 반환

8. feedback logging
   acceptance, turns, explicit feedback (memory impact는 Post-Open-Beta)
```

경계 계약: Discovery는 affinity로 과도하게 pruning하지 않은 **need-complete candidate pool**을 Recommendation에 넘긴다. `need_type`은 Recommendation의 objective를 정하지만, 규모가 커지면 recall을 위해 Discovery 검색 단계에도 전달될 수 있다.

랭킹은 하나의 고정 relevance score가 아니다.

```text
강화 = 유사한 입장을 찾음
대립 = 반대 입장을 찾음
직교 = 다른 프레임을 찾음
```

따라서 need에 따라 stance 연산과 가중치가 달라진다.

> 단계별 score 템플릿 등 더 깊은 상세는 설계 문서(`agent_discovery_recommendation_directions.md` §5)를 source of truth로 본다.

---

## 7. Stance Space

Stance는 전역 공간 하나로 만들지 않는다. "반대"는 topic 안에서만 의미가 있으므로(커피의 산미 vs 바디감, 원격근무의 자율성 vs 협업 밀도는 서로 다른 축) anchor별 local stance space를 둔다. 한 topic 안에서 사람들이 갈라지는 쟁점 축이 `contested axis`이며, Open Beta까지는 LLM으로 coarse axis를 만들고 source(observed/inherited/world-knowledge)를 태깅해 established 또는 inherited_established 축만 orthogonal 서빙에 사용한다(근거가 약한 축은 provisional로 두고 후보 탐색·hint에만 사용).

orthogonal fallback은 orthogonal로 가장하지 않는다. 충분한 orthogonal 후보가 없으면 silence하거나 coverage/against로 fallback하되, 그 사실을 내부 `reason`/`fallback_type`에 명시한다 — fallback이 일어나도 추천 의도가 조용히 바뀌지 않는다.

> stance space·contested axis 도출의 상세는 directions §4를 source of truth로 본다.

---

## 8. Feedback과 Contribution

**Feedback logging은 Open Beta 범위, contribution/reputation은 Post-Open-Beta다.** 둘을 섞으면 안 된다. Open Beta의 목표는 "추천을 평가할 수 있다"이지 "자동 학습/평판 루프를 닫는다"가 아니다.

- Open Beta까지: feedback logging, implicit/explicit signal 수집, 운영 평가(Need별 funnel, threshold 튜닝).
- Post-Open-Beta: memory impact, validated L2 delta, contribution score, need/topic/agent별 reputation learning.

### 8.1 무엇을 로깅하나

추천 단위(decision log)로 남긴다. 이 골격은 분석이 Open Beta여도 **Alpha에서 설계해 넣는다**(나중 retrofit이 비쌈).

- 추천 요청/노출 단위: `request_id`, mode(pull|push), `need_type`, topic/anchor_id, axis_hint, user_stance 유무, candidate list(`agent_id`), ordering keys + feature snapshot, reason shown, evidence_refs 유무
- Implicit: impression, click/select, no-click, dismiss, 대화 시작 여부, turns, duration, early exit, re-engagement, (push) silence 여부
- Explicit: 1-tap helpful/not-helpful, agent가 topic에 맞았는지, 추천 이유가 이해됐는지, for/against/orthogonal 의도가 맞았는지, 간단한 not-helpful reason

분석은 Need별로 한다: depth 선택률, against helpful rate, orthogonal dismiss rate, push silence rate, push 노출 후 dismiss/accept 비율, topic/stance mismatch 비율.

### 8.2 feedback을 reward로 쓰지 않는다

Open Beta feedback은 candidate quality, topic/stance mismatch, UX friction, push intrusiveness를 진단하고 threshold·product policy를 조정하기 위한 **운영 신호**다. 이를 곧바로 ranking 정답 라벨이나 contribution/reputation score로 환산하지 않는다.

- acceptance가 높다 ≠ 좋은 추천
- turns가 길다 ≠ 좋은 추천
- dismiss가 있다 ≠ 나쁜 추천

특히 대립/직교는 대화가 짧고 불편해도 가치 있을 수 있고, 유사성/강화는 engagement가 높아도 echo chamber를 강화할 수 있다. 그래서 against/orthogonal은 성공 지표 자체를 다르게 정의한다(예: orthogonal = 새 축에 engage했는지, 이후 그 축을 다시 언급했는지).

장기적으로 가장 중요한 신호는 추천 대화 후 유저의 L2 지식·stance가 실제로 좋아졌는지(memory impact)이며, 이는 need별·topic별·agent별로 분리해 누적한다. 단일 global popularity score로 뭉치지 않는다. (Post-Open-Beta)

> 피드백 funnel과 contribution/reputation 가드의 상세는 설계 문서(`agent_discovery_recommendation_directions.md` §6)를 source of truth로 본다.

---

## 9. Discovery 입력 source (input contract)

Discovery는 source of truth가 아니다. 다른 컴포넌트(Memory, Persona, Moderation/Runtime)가 raw signal을 제공하고, Discovery가 추천용 projection을 만든다. 아래는 "어느 source가 무엇을 제공하는가"를 정리한 것이다.

처음 구현 논의에서는 **P0 항목만 먼저 보면 된다.** P1은 Open Beta 품질을 올리거나 특정 need를 더 잘 지원하기 위한 항목이고, P2는 Open Beta 이후 고도화 항목이다.

우선순위는 아래처럼 본다.

| 우선순위 | 의미 |
| --- | --- |
| **P0 - 필수** | 없으면 기본 discovery/recommendation이 성립하지 않음 (Alpha 또는 Open Beta 성립 필수) |
| **P1 - Open Beta 품질** | 없어도 동작은 하지만 품질이 낮거나 특정 need가 약해짐 |
| **P2 - Post-Open-Beta** | Open Beta 이후 학습, contribution, 고도화에 필요 |

우선순위(P0/P1/P2)와 일정(Alpha/Open Beta)은 별개 축이다. source 구획이 일정과 대체로 맞아떨어진다: **§9.1 Memory·§9.2 Persona·§9.3 stance는 Pull(Alpha) 성립에 필요**하고, **§9.4 Moderation/Runtime은 Push(Open Beta)에 필요하되 query DTO 계약 합의는 Alpha 동안 한다.**

### 9.1 Source: Memory

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | `anchor-personal node link` | public anchor(QID)와 특정 `agent_id`의 personal knowledge node를 잇는 link | discovery의 기본 검색 단위 |
| **P0** | `evidence_volume` | 해당 topic과 연결된 Record, Capsule, L2 node의 양 | 근거가 충분한 agent인지 판단 |
| **P0** | `freshness` | 해당 topic evidence가 관찰되거나 갱신된 시점 | 오래된 정보 decay |
| **P0** | `evidence_refs` | 추천 근거가 되는 L2/L1/L0 포인터. payload가 아니라 reference | 설명, provenance, experience 추천 근거 |
| **P1** | `consistency` | 같은 topic에 대한 지식이나 입장이 시간·출처에 걸쳐 얼마나 일관적인지 | 신뢰도와 maturity 계산 |
| **P1** | `specificity` | "관심 있음" 수준인지, 구체적 지식·경험이 있는지의 정도 | 얕은 관심과 실제 전문성 구분 |
| **P1** | `experience flag` | 이 topic 지식이 직접 경험에서 나온 것인지 표시 | experience need 후보 필터링 |
| **P1** | `source_type` | conversation, document, external source, episode 등 evidence의 출처 타입 | 근거 성격 구분 |
| **P2** | post-conversation `L2 delta + provenance` | 추천 대화 이후 유저의 L2 지식/stance가 어떻게 바뀌었는지와 그 출처 | Post-Open-Beta memory impact와 contribution 계산 |

Discovery는 이 raw signal로 `topic_knowledge_maturity`와 `evidence_strength`를 계산한다.

### 9.2 Source: Persona

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | global persona / stable core | `agent_id`에 붙은 공개 가능한 persona 요약. 성향, 선호, 판단 스타일, 대화 스타일 등 | cold anchor prior, similarity, orthogonal 기준 frame |
| **P1** | `persona_maturity` | global persona가 충분한 관찰에서 만들어졌는지의 정도 | persona prior를 얼마나 믿을지 |
| **P1** | `consistency` | persona가 시간과 상황에 걸쳐 얼마나 안정적인지 | observed stance와 prior를 blend할 때 사용 |
| **P2** | `global_profile_version` | persona projection의 버전 | 추천용 projection/cache/index를 갖게 되면 stale 식별에 필요. 초기에는 매 요청 시 persona를 직접 가져와 쓰므로 versioning이 필수는 아니다 |

Global persona는 topic별 stance가 부족할 때 prior로 쓴다. 단, maturity를 올리는 데는 쓰지 않는다.

### 9.3 Source: stance (observed = Memory, prior = Persona)

Stance의 소유는 "Memory냐 Persona냐"의 양자택일이 아니라 **source로 나뉜다**. §4.2의 원칙(prior는 stance만 채움)대로, observed stance와 prior stance는 출처가 다르고 Discovery가 둘을 blend한다.

| stance 종류 | source of truth | 제공자 |
| --- | --- | --- |
| **observed** topic-specific stance | L2 opinion/preference/judgment node | Memory |
| **prior** stance | stable persona/preference | Persona |
| effective stance + `axis_positions` projection | (위 둘의 blend·계산) | Discovery가 derive |

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | opinion/stance content per `(agent, anchor)` (observed) | 특정 agent가 특정 topic에 대해 가진 의견, 선호, 판단, 관점의 요약 | for/against/orthogonal matching |
| **P1** | `extraction_confidence` | 그 stance 추출이 얼마나 확실한지에 대한 confidence | stance와 axis confidence 계산 |

observed stance는 agent-topic edge에서 **읽고**(edge는 Memory substrate이므로 Discovery가 소유·기록하지 않는다), `axis_positions`·effective stance는 Discovery가 **derive**한다. Discovery는 개별 stance를 모아 contested axes를 만들며, 이 source는 axis 자체를 만들 필요는 없다.

이 observed/prior 소유 구분은 Alpha의 for/against가 성립하기 위한 선결 합의다. 어떤 Need(for/against/orthogonal)에 맞는지도 producer가 태깅하지 않는다. Discovery가 request-time에 `user_stance_ref`·`need_type` 대비 판단한다(§6). lived experience 적합성은 Memory의 `experience flag`/`source_type`로 충분하다.

### 9.4 Source: Moderation / Runtime

| 우선순위 | needed_by | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- | --- |
| **P0** | Open Beta (Push) | `mode` | 요청이 pull인지 push인지 | pull/push 동작 차이 |
| **P0** | Open Beta (Push) | `need_type` | 현재 추천이 해결해야 하는 need. 예: `depth`, `against`, `orthogonal` | Recommendation objective 선택. 필요 시 Discovery retrieval recall에도 전달 |
| **P0** | Open Beta (Push) | `user_stance_ref` | 현재 대화에서 드러난 유저의 topic별 입장 요약 | for/against/orthogonal 기준점 |
| **P1** | Open Beta (Push) | `need_confidence` | runtime/moderation이 need 판단을 얼마나 확신하는지 | push 추천의 precision control |
| **P1** | Open Beta | `requester_persona_ref` | 후보 agent가 아니라 추천을 요청하는 현재 유저/agent의 persona/profile reference | similarity와 orthogonal 기준 frame |

**Alpha Pull에서는 Runtime이 `mode`·`need_type`·`user_stance_ref`를 주지 않아도 된다** — Discovery가 request text에서 직접 추출한다(§5). 따라서 이 표의 Runtime 제공 입력은 P0이지만 일정상 **Push(Open Beta) 의존**이며, query DTO 계약은 Alpha 동안 shadow mode로 확정한다. (P0=성립 필수, needed_by=언제 필요한가 — 두 축은 별개다.)

`topic_candidates`, `anchor_hint`, `axis_hint`는 Moderation/Runtime이 줄 수도 있고, Discovery가 anchor 해소 단계에서 만들 수도 있다. 둘 다 있으면 Discovery가 최종 anchor와 axis를 결정한다.

Push에서 추천할지 침묵할지 결정하는 threshold는 input으로 받지 않는다. `silence_threshold`는 Recommendation 단계의 serving policy로 두고, mode·Need·후보 품질 신호·ordering 결과·제품 정책에 따라 적용한다.

safety / privacy 관련 verdict(후보 agent 안전성, 대화 맥락 안전성, 공개 권한 등)는 이 표에 포함하지 않는다. Alpha(내부/closed)에서는 inactive로 두고, 외부 공개(Open Beta) 시 hard gate로 활성화한다. query DTO 계약은 Alpha 동안 확정해 shadow mode로 검증한다. 결정해야 할 주제는 §11에 정리한다.

### 9.5 Discovery / Recommendation 단계가 내부에서 derive하는 것

다른 source가 만들 필요 없는 것. 어느 내부 단계가 derive하는지로 묶는다(§6).

| 단계 | 우선순위 | 데이터/산출물 | 무엇인가 | 어디에 쓰는가 |
| --- | --- | --- | --- | --- |
| **Discovery** | **P0** | `topic_knowledge_maturity` | Memory raw signal을 바탕으로 계산한 agent-topic별 지식 성숙도 | maturity gate, expert ranking |
| **Discovery** | **P0** | `evidence_strength` | evidence volume, specificity, consistency 등을 합친 근거 강도 | 얇은 후보와 근거 있는 후보 구분 |
| **Discovery** | **P0** | prior-fill | topic-specific stance가 부족할 때 global persona로 예상 stance를 채우는 projection | cold anchor에서 후보 방향성 보완 (Recommendation objective가 소비) |
| **Discovery** | **P1** | contested axes | 한 topic 안에서 사람들이 갈라지는 쟁점 축. 예: 산미 vs 바디감 | for/against/orthogonal 계산 |
| **Discovery** | **P1** | axis positions projection | 각 agent가 contested axis 위에서 어디에 있는지 계산한 값 | stance matching과 coverage (Recommendation objective가 소비) |
| **Discovery** | **P1** | axis confidence calibration | axis와 stance position을 얼마나 믿을 수 있는지 보정한 값 | provisional/established 판단, false controversy 방지 |
| **Discovery** | **P2** | stance space version | anchor별 stance space의 버전 | 추천용 projection/cache/index를 갖게 되면 axis 변경 시 stale 식별에 필요 |
| **Discovery** | **P2** | topic-conditioned embedding | topic 성분을 줄인 stance/perspective embedding | 규모가 커졌을 때 for/against matching 최적화 |
| **Recommendation** | **P0** | ranking/objective | need별 scoring과 후보 정렬 로직 | 최종 추천 순서 결정 |
| **Recommendation** | **P0** | serving policy / `silence_threshold` | push 추천에서 기준 미달이면 침묵하도록 하는 내부 정책값 | 약한 추천으로 대화를 방해하지 않기 위해 |
| **Recommendation** | **P2** | contribution/reputation score | 추천 이후 검증된 memory impact를 agent/topic/need별로 누적한 점수 | Post-Open-Beta ranking 보강, 단 popularity bias 가드 필요 |

### 9.6 Lifecycle events (projection/cache/index 도입 시)

초기에는 Discovery가 추천 요청마다 필요한 source 데이터를 그때그때 가져와서 사용한다. 따라서 lifecycle 이벤트는 초기 필수가 아니다.

다만 추천 품질·속도·규모를 위해 Discovery가 자체 **추천용 projection/cache/index**를 갖게 될 가능성이 높다. 그 단계에서는 source가 바뀔 때 인덱스를 최신으로 유지하기 위한 이벤트가 필요해진다.

필요해질 이벤트:

```text
publish
update
revoke
```

| 이벤트 대상 | source |
| --- | --- |
| anchor-personal link | Memory |
| stance content | observed=Memory, prior=Persona (§9.3) |
| global persona | Persona |

safety / privacy verdict의 lifecycle은 해당 기능을 도입하는 시점에 함께 정한다(§11).

---

## 10. 개발 로드맵

**Alpha (내부/closed)**

| 단계 | 산출물 | 목표 |
| --- | --- | --- |
| 1 | Discovery input contract | Memory/Persona/stance P0 입력 확정(observed/prior 소유 확정 선결, §9.3) + Moderation/Runtime query DTO 초안 |
| 2 | Agent-topic edge projection | anchor, agent, evidence, stance를 추천용 edge로 구성 |
| 3 | Pull recommendation API | topic·need·request text에서 stance 추출 후 후보 리스트 반환 |
| 4 | Maturity gate | Memory raw signal로 `topic_knowledge_maturity` 계산 후 후보 필터링 |
| 5 | for/against matching | stance descriptor 기반 coarse for/against (established axis 불요) |
| 6 | Serving payload + decision log | 후보(`agent_id`)·이유·evidence refs 반환 + 추천 단위 로그 |
| 7 | Push DTO + shadow mode | query DTO 초안 확정, 노출 없이 추천/침묵 로깅 |

> **구현 전략:** Memory/Persona 통합을 기다리지 않고 **공동 합의한 mock contract** 기반으로 Discovery 구현을 시작한다.
> Provider 인터페이스 + mock provider + 가드 역산 fixture로 먼저 개발하고, 실제 API가 준비되면 provider 구현만 교체한다.
> 단, QID vocabulary 합의는 mock과 별개인 Alpha 선결 조건이다. 상세는 `agent_discovery_recommendation_implementation.md` §7.

> **현황·결정 (2026-07-07):** 코드 repo(Phase 0–8A)가 단계 1·3·5·6을 착지시켰다 — 계약 동결,
> real anchor grounding(+LLM rerank fallback), for/against ordering, serving + decision log +
> 평가 게이트. 단, 후보 substrate(edge/eligibility/persona)는 아직 mock이라 배포된 Pull API는
> grounding 후 후보 단계에서 503을 반환한다. user-facing Alpha 성립에 남은 것은 **단계 2·4의
> real edge + maturity + allow-all eligibility 배선**이며, 이를 코드 repo **Phase 10**으로
> 승격했다(상세: `impl/11-phase-8-9-roadmap.md`). 최소 범위: `MemoryEdgeProvider`만 real
> 교체(협의 출발점 = 2026-07-03 rec-signal 계약), eligibility는 `discoverable=true` 가정의 얇은
> stub 배선(visibility 보류 합의; 현 배포는 hard-required `Unavailable*`라 real edge만으로는
> gate에서 여전히 503), persona는 NullProvider 유지(Alpha ranking no-op). 핵심 협의 안건 = **maturity 소유**
> (memory-api가 제공하는가 vs discovery측 translation layer가 계산하는가). 단계 7(Push DTO +
> shadow)은 Phase 10 이후로 **명시 이월** — query DTO 계약 초안 합의만 Alpha 기간에 한다.

**Open Beta (외부 공개)**

| 단계 | 산출물 | 목표 |
| --- | --- | --- |
| 8 | candidate safety + discoverability gate | 외부 공개 hard 요건 (§11) — Push user-facing의 선결 |
| 9 | Push recommendation user-facing | gate 활성화 이후. runtime/moderation query DTO, silence policy, top-1/소수 추천 |
| 10 | Orthogonal recommendation (조건부) | established/inherited_established axis 한정, 부족하면 fallback |
| 11 | Feedback logging 확대 + Need별 평가 | push impression/dismiss/accept, funnel, threshold 튜닝 |

> **Open Beta 후보 항목 (bourbon-api 신호 존재 시):** negative preference — `hidden`/`muted`(do-not-show serving suppression), `dismissed_recently`(Push fatigue/silence). positive favorite tie-break은 Post-Open-Beta(stage 13). favorite/preference는 expertise·gate를 우회하지 않는다.

**Post-Open-Beta**

| 단계 | 산출물 | 목표 |
| --- | --- | --- |
| 12 | 고도화 track | memory impact, validated contribution, reputation, embedding/learning-to-rank 고도화 |
| 13 | positive favorite 반영 | favorite을 bounded tie-break(깊이/경험/강화, 대립/직교 제외). 출처: `bourbon-api`. expertise/gate 우회·단일 popularity score 금지 |

---

## 11. 공개 전 결정해야 할 Safety / Privacy 주제

Alpha는 내부/closed 범위로 운영하므로 safety/privacy 게이트 없이 Pull 파이프라인 검증에 집중한다. **따라서 아래 결정 영역들이 해소되기 전에는 외부 공개(Open Beta 포함)로 노출하지 않는다.** 이 절은 결정해야 할 *주제*를 모은 것이지 예정된 구현 작업 목록이 아니며, 로드맵 단계와 별개다.

세 게이트는 직교한다: maturity는 Discovery가 계산하고, safety와 privacy는 Discovery 외부에서 verdict/정책으로 들어온다.

### 11.1 Safety / reliability

| 주제 | 결정해야 할 것 | 언제 필요한가 |
| --- | --- | --- |
| candidate verdict | 무엇을 단언하나(이 agent를 노출해도 품질·위험상 괜찮은가), 스키마(pass/block/unknown + confidence) | 외부 공개(Open Beta) |
| context verdict | 지금 이 대화 맥락에서 추천을 시도해도 되나 (push) | Push(Open Beta) |
| 적용 지점 | hard gate를 후보별·맥락별로 어디서 적용하나 | 외부 공개 |
| unknown 처리 | verdict가 unknown일 때 fail-open이냐 fail-closed냐 | 외부 공개 |
| lifecycle | 후보·agent가 나중에 unsafe로 판정되면 revoke/update → Discovery가 재계산·제외 | projection/cache 도입 시 |

safety와 novelty는 trade-off하지 않는다. 따라서 safety는 weak prior가 아니라 hard gate다.

### 11.2 Privacy / eligibility

| 주제 | 결정해야 할 것 | 언제 필요한가 |
| --- | --- | --- |
| discoverability opt-in | 이 agent를 애초에 후보로 노출해도 되나(owner 동의) — 최소 1비트 | 외부 공개(Open Beta) |
| 노출 입도 | 후보에 대해 무엇까지 보여주나 — description 수준(`stance_summary`, 근거 존재 여부)이지 raw memory 내용은 아님 | 외부 공개 |
| provenance 노출 | `evidence_refs`를 추천 이유로 보일 때 출처를 얼마나 드러내나(익명 vs attributed) | 외부 공개 |
| ~~routing_target 노출~~ | 계약에서 제거 — recommendation은 `agent_id`만 반환하고 dispatch는 bourbon-api가 해석하므로 노출 이슈 없음 | — |
| 동의 범위·철회 | 토픽별이냐 전역이냐, 철회 시 전파 방식 | 외부 공개 |
| 공통사실 승급과의 관계 | L3 공통사실 승급의 익명·권한 link 정책과 일관되게 둘 것 | full privacy 설계 시 |

full privacy/permission 시스템은 Post-Open-Beta다. 다만 외부 공개의 선결 조건은 단순한 opt-in 1비트가 아니라 **minimum external eligibility layer**다 — discoverability opt-in에 더해 provenance·`stance_summary`의 노출 입도까지 외부 공개 전에 결정해야 한다. full privacy/permission 시스템과 이 최소 layer의 경계가 §11의 핵심 구분이다.

---

## 검토 중인 항목

- **stance content의 observed/prior source 소유 확정** (Alpha 선결, §9.3)
- `floor_need` 기본값과 need별 maturity floor
- contested axis의 `established` 기준
- cold anchor에서 inherited axis를 어느 정도까지 허용할지
- query DTO 스키마
- memory impact를 언제부터 value signal로 쓸지 (Post-Open-Beta)

safety/privacy 관련 결정 영역은 §11에 정리한다.

> 구체 기술 선택(저장소, ANN, embedding model, learning-to-rank 등)은 Alpha/Open Beta 계약과 데이터 흐름이 확정된 뒤 별도 문서에서 다룬다. 구현 접근·build vs reuse·단계별 컴포넌트 후보는 `agent_discovery_recommendation_implementation.md`(working)에 정리한다.
