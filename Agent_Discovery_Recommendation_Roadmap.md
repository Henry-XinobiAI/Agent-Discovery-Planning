# Agent Discovery & Recommendation Roadmap

> Agent Discovery & Recommendation은 사용자가 어떤 주제에 대해 대화할 만한 agent를 찾고, 대화 흐름 안에서 필요한 경우 적절한 agent를 추천하는 시스템이다.
>
> 핵심은 "비슷한 사람 추천"만이 아니다. 어떤 상황에서는 같은 입장을 강화해줄 agent가 필요하고, 어떤 상황에서는 반대 관점이나 완전히 다른 프레임을 열어줄 agent가 필요하다. 그래서 추천 목적은 대화 맥락과 need에 따라 달라진다.

핵심 통찰: **public anchor는 정답을 보관하는 장소가 아니라, 특정 주제를 잘 아는 agent와 그 agent의 관점으로 가는 연결점이다.** Discovery는 이 연결을 이용해 "누가 이 주제에 대해 말할 가치가 있는가"를 찾는다.

---

## 1. 무엇을 다루는가

이 문서는 Agent Discovery & Recommendation의 개발 방향을 간단히 공유하기 위한 문서다.

다루는 범위:

- 유저가 직접 agent를 찾는 **pull 추천**
- 대화 중 시스템이 필요를 감지해 제안하는 **push 추천**
- topic, stance, evidence, persona를 이용한 후보 검색과 랭킹
- memory/persona/moderation 팀이 discovery에 제공해야 하는 입력 계약

다루지 않는 범위:

- 사람 대 사람 연결, invite, networking
- full privacy/permission 설계
- 고도화된 reputation learning
- topic-conditioned embedding 또는 별도 학습 모델

현재 목표는 복잡한 모델을 먼저 만드는 것이 아니라, **memory/persona 구조 위에서 작동하는 MVP 추천 파이프라인**을 만드는 것이다.

MVP의 1차 산출물은 **topic과 need를 입력받아 추천 가능한 agent 후보, 추천 이유, `routing_target`을 반환하는 API/projection**이다.

---

## 2. 추천의 두 모드

| 모드 | 설명 | 결과 |
| --- | --- | --- |
| **Pull** | 사용자가 직접 "이 주제로 이야기할 agent 추천해줘"라고 요청 | 후보 리스트 |
| **Push** | 대화 중 runtime/moderation이 다른 agent가 도움이 될 상황을 감지 | 인라인 추천 또는 침묵 |

Pull은 사용자가 직접 고르기 때문에 best-effort 후보 리스트를 반환할 수 있다.

Push는 대화에 끼어드는 추천이므로 기준이 더 높다. 충분히 좋은 후보가 없으면 추천하지 않고 침묵한다.

---

## 3. Need 유형

추천은 하나의 목적만 갖지 않는다. 대화 상황에 따라 필요한 agent의 종류가 다르다.

| need | 의미 | 예 |
| --- | --- | --- |
| **깊이/전문성** | 이 주제를 더 깊이 아는 agent | "이 기술을 실제로 잘 아는 사람" |
| **경험** | 직접 해봤거나 겪어본 agent | "이걸 실제로 써본 사람" |
| **유사성** | 취향이나 상황이 비슷한 agent | "나와 비슷한 사람이 뭘 선택했는지" |
| **강화(for)** | 내 입장을 더 잘 뒷받침할 agent | "내 생각을 더 탄탄하게 해줄 사람" |
| **대립(against)** | 내 입장을 반대로 검증할 agent | "반대편에서 문제를 짚어줄 사람" |
| **직교(orthogonal)** | 찬반이 아니라 다른 프레임을 열 agent | "전혀 다른 기준으로 보는 사람" |

여기서 `need`는 전통적인 recsys 표준 용어라기보다, 이 문서에서 쓰는 추천 intent/objective type이다.

---

## 4. 핵심 데이터 모델

Discovery의 기본 검색 단위는 **agent-topic edge**다.

```text
public anchor(QID)
  <-> agent
  <-> topic-specific metadata
```

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

### 4.2 edge의 두 얼굴

agent-topic edge는 두 종류의 정보를 가진다.

| face | 의미 | 사용처 |
| --- | --- | --- |
| **Knowledge face** | 이 topic에 대해 근거 있게 말할 수 있는가 | maturity gate, expert ranking |
| **Stance face** | 이 topic에서 어떤 입장인가 | for/against/orthogonal 추천 |

중요한 원칙:

```text
prior는 stance만 채운다.
maturity는 채우지 않는다.
```

Global persona를 보면 어떤 입장을 가질지 추정할 수는 있다. 하지만 그 topic을 실제로 깊이 아는지는 evidence로만 판단해야 한다.

---

## 5. MVP 추천 방식

MVP는 복잡한 임베딩이나 학습 모델 없이 시작한다.

| MVP에서 한다 | 의미 |
| --- | --- |
| topic을 public anchor(QID)에 연결 | 유저의 topic을 표준 anchor로 grounding |
| anchor에 연결된 agent 후보 조회 | 해당 topic을 가진 agent-topic edge 검색 |
| stance descriptor 비교 | 사람이 읽을 수 있는 `stance_summary`, `axis_positions` 등으로 비교 |
| for/against 판단 | 유저 입장과 같은 편인지, 반대편인지 LLM/텍스트 비교로 판단 |
| orthogonal 판단 | 찬반이 아니라 다른 쟁점 축을 가진 agent를 찾음 |
| maturity/evidence/freshness gate | 근거가 얇거나 오래된 후보를 낮춤 |
| 기본 피드백 기록 | 선택 여부, 대화 길이, 1-tap 평가 |

예:

```text
유저: 나는 커피에서 산미가 제일 중요하다고 봐.
```

| 추천 유형 | 찾는 agent |
| --- | --- |
| for | 산미를 중요하게 보는 agent |
| against | 바디감이나 고소함을 더 중요하게 보는 agent |
| orthogonal | 맛 취향이 아니라 가격, 장비 관리, 윤리적 소비 같은 다른 축을 보는 agent |

임베딩 기반 고도화는 later다. MVP는 symbolic descriptor 중심으로 먼저 동작하게 만든다.

---

## 6. Retrieval과 Ranking 흐름

공통 파이프라인은 아래와 같다.

```text
1. 입력 정규화
   topic, need_type, user_stance_ref, requester_persona_ref

2. anchor 해소
   topic -> Wikidata QID 또는 자체 anchor

3. 후보 검색
   anchor에 연결된 agent-topic edge 조회

4. gate
   on-topic
   maturity floor
   candidate safety/reliability
   privacy/eligibility (later)

5. need별 연산
   depth / experience / similarity / for / against / orthogonal

6. ranking
   need-specific score + diversity

7. serving
   후보, 설명, routing_target 반환

8. feedback logging
   acceptance, turns, explicit feedback, later memory impact
```

랭킹은 하나의 고정 relevance score가 아니다.

```text
강화 = 유사한 입장을 찾음
대립 = 반대 입장을 찾음
직교 = 다른 프레임을 찾음
```

따라서 need에 따라 stance 연산과 가중치가 달라진다.

---

## 7. Stance Space

Stance는 전역 공간 하나로 만들지 않는다.

"반대"는 topic 안에서만 의미가 있다.

```text
커피에서 산미 vs 바디감
원격근무에서 자율성 vs 협업 밀도
```

이 두 축은 같은 축이 아니다. 그래서 anchor별 local stance space를 둔다.

### 7.1 contested axis

`contested axis`는 한 topic 안에서 사람들이 실제로 갈라지는 쟁점 축이다.

MVP에서는 아래 정도만 한다.

```text
1. LLM으로 coarse axis 생성
2. observed / inherited / world-knowledge source 태깅
3. divergence가 충분하면 established
4. established 또는 inherited_established 축만 orthogonal 서빙에 사용
```

Cold/sparse anchor에서는 상위 anchor의 established axis를 `inherited_established`로 상속할 수 있다. 이 경우 orthogonal 서빙에 사용할 수 있다. 근거가 약한 축은 `provisional`로 두고 후보 탐색이나 hint에만 사용한다.

---

## 8. Feedback과 Contribution

유저가 추천을 클릭했다고 해서 좋은 추천이었다고 볼 수는 없다.

| 신호 | 의미 | 주의 |
| --- | --- | --- |
| acceptance | 추천을 선택함 | 카드 매력이나 위치 편향일 수 있음 |
| turns | 대화가 오래 지속됨 | 대립/직교는 짧아도 가치 있을 수 있음 |
| 1-tap feedback | 직접 평가 | 희소하지만 유용 |
| memory impact | 유저의 L2 지식/stance 변화 | later의 핵심 value signal |

장기적으로 가장 중요한 신호는 추천 대화 후 유저의 L2 지식이나 stance가 실제로 좋아졌는지다.

예:

- 깊이 추천: 새 fact node가 생김
- 대립 추천: 기존 stance가 더 정교해짐
- 직교 추천: 보지 않던 축에 새 입장이 생김

이 신호는 나중에 contribution score로 누적할 수 있다. 단, global popularity score로 뭉치면 안 된다. need별, topic별, agent별로 분리해야 한다.

---

## 9. 팀 계약

Discovery는 source of truth가 아니다. Memory, Persona, Moderation이 raw signal을 제공하고, Discovery가 추천용 projection을 만든다.

처음 구현 논의에서는 **P0 항목만 먼저 보면 된다.** P1은 MVP 품질을 올리거나 특정 need를 더 잘 지원하기 위한 항목이고, P2는 MVP 이후 고도화 항목이다.

우선순위는 아래처럼 본다.

| 우선순위 | 의미 |
| --- | --- |
| **P0 - MVP 필수** | 없으면 기본 discovery/recommendation이 성립하지 않음 |
| **P1 - MVP 품질/특정 need** | 없어도 일부 동작은 가능하지만 품질이 낮거나 특정 need가 약해짐 |
| **P2 - Later** | MVP 이후 학습, contribution, 고도화에 필요 |

### 9.1 Memory 팀이 제공해야 하는 것

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
| **P2** | post-conversation `L2 delta + provenance` | 추천 대화 이후 유저의 L2 지식/stance가 어떻게 바뀌었는지와 그 출처 | later memory impact와 contribution 계산 |

Discovery는 이 raw signal로 `topic_knowledge_maturity`와 `evidence_strength`를 계산한다.

### 9.2 Memory 또는 Persona 팀이 합의해야 하는 것

Stance는 L2 opinion이기도 하고 persona 추론과도 닿는다. 어느 팀이 소유할지 합의가 필요하다.

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | opinion/stance content per `(agent, anchor)` | 특정 agent가 특정 topic에 대해 가진 의견, 선호, 판단, 관점의 요약 | for/against/orthogonal matching |
| **P1** | `extraction_confidence` | 그 stance 추출이 얼마나 확실한지에 대한 confidence | stance와 axis confidence 계산 |
| **P1** | optional `useful_for` hint | 이 stance가 어떤 need에 유용할지에 대한 힌트. 예: `for`, `against`, `experience` | need matching 품질 향상 |

Discovery는 개별 stance를 모아 contested axes를 만든다. Memory/Persona가 axis 자체를 만들 필요는 없다.

### 9.3 Persona 팀이 제공해야 하는 것

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | global persona / stable core | `agent_id`에 붙은 공개 가능한 persona 요약. 성향, 선호, 판단 스타일, 대화 스타일 등 | cold anchor prior, similarity, orthogonal 기준 frame |
| **P1** | `persona_maturity` | global persona가 충분한 관찰에서 만들어졌는지의 정도 | persona prior를 얼마나 믿을지 |
| **P1** | `consistency` | persona가 시간과 상황에 걸쳐 얼마나 안정적인지 | observed stance와 prior를 blend할 때 사용 |
| **P1** | `global_profile_version` | persona projection의 버전 | stale projection 식별 |

Global persona는 topic별 stance가 부족할 때 prior로 쓴다. 단, maturity를 올리는 데는 쓰지 않는다.

### 9.4 Moderation/Runtime 팀이 제공해야 하는 것

| 우선순위 | 데이터 | 무엇인가 | 왜 필요한가 |
| --- | --- | --- | --- |
| **P0** | `mode` | 요청이 pull인지 push인지 | pull/push 동작 차이 |
| **P0** | `need_type` | 현재 추천이 해결해야 하는 need. 예: `depth`, `against`, `orthogonal` | discovery 목적함수 선택 |
| **P0** | `user_stance_ref` | 현재 대화에서 드러난 유저의 topic별 입장 요약 | for/against/orthogonal 기준점 |
| **P0** | candidate-level `safety/reliability verdict` | 후보 agent 또는 routing target별 안전성/신뢰성 verdict | 후보 agent별 hard gate |
| **P1** | `need_confidence` | runtime/moderation이 need 판단을 얼마나 확신하는지 | push 추천의 precision control |
| **P1** | `requester_persona_ref` | 추천을 요청하는 현재 유저 또는 유저 agent의 persona/profile reference | similarity와 orthogonal 기준 frame |
| **P1** | `context_safety_verdict` | 지금 대화 맥락에서 다른 agent 추천을 시도해도 되는지에 대한 verdict | 위험한 맥락에서 push 추천 방지 |
| **P1** | `silence_threshold` | push 추천에서 이 점수 미만이면 추천하지 않는 기준 | 약한 추천으로 대화를 방해하지 않기 위해 |

`topic_candidates`, `anchor_hint`, `axis_hint`는 Moderation/Runtime이 줄 수도 있고, Discovery가 anchor 해소 단계에서 만들 수도 있다. 둘 다 있으면 Discovery가 최종 anchor와 axis를 결정한다.

### 9.5 Discovery가 내부에서 만드는 것

다른 팀이 만들 필요 없는 것:

| 우선순위 | 데이터/산출물 | 무엇인가 | 어디에 쓰는가 |
| --- | --- | --- | --- |
| **P0** | `topic_knowledge_maturity` | Memory raw signal을 바탕으로 계산한 agent-topic별 지식 성숙도 | maturity gate, expert ranking |
| **P0** | `evidence_strength` | evidence volume, specificity, consistency 등을 합친 근거 강도 | 얇은 후보와 근거 있는 후보 구분 |
| **P0** | ranking/objective | need별 scoring과 후보 정렬 로직 | 최종 추천 순서 결정 |
| **P0** | prior-fill | topic-specific stance가 부족할 때 global persona로 예상 stance를 채우는 projection | cold anchor에서 후보 방향성 보완 |
| **P1** | contested axes | 한 topic 안에서 사람들이 갈라지는 쟁점 축. 예: 산미 vs 바디감 | for/against/orthogonal 계산 |
| **P1** | axis positions projection | 각 agent가 contested axis 위에서 어디에 있는지 계산한 값 | stance matching과 coverage |
| **P1** | axis confidence calibration | axis와 stance position을 얼마나 믿을 수 있는지 보정한 값 | provisional/established 판단, false controversy 방지 |
| **P1** | stance space version | anchor별 stance space의 버전 | axis 변경 시 stale projection 식별 |
| **P2** | topic-conditioned embedding | topic 성분을 줄인 stance/perspective embedding | 규모가 커졌을 때 for/against matching 최적화 |
| **P2** | contribution/reputation score | 추천 이후 검증된 memory impact를 agent/topic/need별로 누적한 점수 | later ranking 보강, 단 popularity bias 가드 필요 |

### 9.6 Lifecycle events

Discovery index는 projection이므로 source가 바뀌면 이벤트가 필요하다.

필요 이벤트:

```text
publish
update
revoke
```

| 이벤트 대상 | 소유 |
| --- | --- |
| anchor-personal link | Memory |
| stance content | Memory 또는 Persona 합의 |
| global persona | Persona |
| safety verdict | Moderation/response team |
| privacy/eligibility | Deferred |

Safety verdict도 lifecycle 대상이다. agent나 routing target이 나중에 unsafe로 판정되면 moderation/response team이 update 또는 revoke 이벤트를 발행하고, Discovery는 해당 candidate를 재계산하거나 gate에서 제외한다.

---

## 10. 개발 로드맵

| 단계 | 산출물 | 목표 |
| --- | --- | --- |
| 1 | Discovery input contract | Memory/Persona/Moderation에서 받을 P0 입력 확정 |
| 2 | Agent-topic edge projection | anchor, agent, evidence, stance를 추천용 edge로 구성 |
| 3 | Pull recommendation API | topic과 optional need를 받아 후보 리스트 반환 |
| 4 | Maturity gate | Memory raw signal로 `topic_knowledge_maturity` 계산 후 후보 필터링 |
| 5 | Stance matching | stance descriptor 기반 for/against 추천 |
| 6 | Orthogonal MVP | coarse contested axes 기반 다른 프레임 추천 |
| 7 | Serving payload | 후보, 추천 이유, evidence refs, `routing_target` 반환 형식 |
| 8 | Push recommendation contract | runtime/moderation query DTO, threshold, silence 동작 정의 |
| 9 | Feedback logging | acceptance, turns, 1-tap feedback 기록 |
| 10 | Later track | memory impact, contribution, embedding 고도화 |

---

## 검토 중인 항목

- `floor_need` 기본값과 need별 maturity floor
- contested axis의 `established` 기준
- cold anchor에서 inherited axis를 어느 정도까지 허용할지
- query DTO와 candidate safety verdict 스키마
- privacy/eligibility의 MVP 포함 여부와 최소 필드
- memory impact를 언제부터 value signal로 쓸지

> 구체 기술 선택(저장소, ANN, embedding model, learning-to-rank 등)은 MVP 계약과 데이터 흐름이 확정된 뒤 별도 문서에서 다룬다.
