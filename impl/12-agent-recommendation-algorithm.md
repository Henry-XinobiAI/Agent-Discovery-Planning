# 12. Agent recommendation algorithm — 현재 구현 축과 이후 개인화 축

← [개요로 돌아가기](README.md) · 관련: [00. 파이프라인 I/O 참조](00-pipeline-io-reference.md) ·
[05. gate+ranking](05-gate-and-ranking.md) · [11. Forward 로드맵](11-forward-roadmap.md)

이 문서는 "agent recommendation"을 제품 관점에서 설명한다. 현재 구현 중인 Discovery 파이프라인은
**주제에 대한 전문성 기반 추천(topic-expertise recommendation)** 이고, 이후 고도화할 축은
**사용자 관심사·persona·social graph 기반 개인화 추천(personalized/social recommendation)** 이다.

두 축은 섞지 않는다. Alpha/Pull API는 먼저 "이 주제에 대해 누가 가장 적합한가"를 안정적으로 풀고,
Open Beta 이후 "이 사용자에게 왜 이 agent인가"를 별도 레이어로 얹는다.

---

## 1. 한 문장 정의

현재 Discovery가 하는 일:

```text
topic + need
→ context-aware topic grounding(QID)
→ topic에 대한 agent expertise edge
→ eligibility/gate
→ need별 deterministic ranking
→ 추천 응답 + decision log
```

즉 현재 추천의 중심 질문은:

> "이 사용자가 입력한 주제와 필요에 대해, 어떤 agent가 충분한 근거와 성숙도를 가지고 답할 수 있는가?"

아직 중심 질문이 아닌 것:

> "이 사용자의 관계망·선호·persona·과거 행동을 고려할 때, 어떤 agent를 더 좋아하거나 신뢰할 가능성이 높은가?"

후자는 중요하지만, 현재 구현 축과 분리된 다음 추천 레이어다.

---

## 2. 현재 구현 중인 추천 축 — topic expertise

현재 파이프라인은 다음 신호를 사용한다.

| 축 | 현재 상태 | 의미 |
|---|---|---|
| topic grounding | **agentic LLM-primary grounding shipped (기본 OFF, dormant)** | `topic_text` + 최근 대화 context로 하나의 QID를 확정하거나 abstain |
| candidate retrieval | Phase 10 real edge 통합 예정 | QID에 연결된 agent-topic edge 수집 |
| eligibility | Alpha는 얇은 stub 예정, Open Beta에서 확장 | 노출 가능 여부, discoverable/privacy/safety |
| maturity | 구현된 rank/gate 신호 | 해당 topic에 대한 agent 지식 성숙도 |
| evidence_strength | 구현된 rank 신호 | 답변 근거의 강도 |
| freshness | 구현된 rank 신호 | 해당 topic 관련 기억/근거의 최신성 |
| experience signals | 구현된 rank 신호 | firsthand/secondhand, specificity |
| stance | for/against need에서 구현 | 같은 편/반대 편 agent 추천 |
| coverage | 구현 | 한 facet에 쏠리지 않도록 anchor group round-robin |
| reason + signals | Phase 8-5 구현 | 추천 이유와 원 신호를 응답에 노출 |
| decision log | 구현 | 왜 이 추천이 나왔는지 감사 가능하게 기록 |

핵심 특징:

- score 합산이 아니라 **ordering contract**다.
- popularity/importance를 독립 ranking 신호로 쓰지 않는다.
- grounding은 큰 축 전환 중이다. context가 있으면 bounded tool-use LLM agent가 memory-api `/knowledge/*`
  도구로 QID를 고르고, context가 없고 unique exact일 때는 symbolic adopt를 유지한다.
- eval/CI에서는 LLM grounder를 주입하지 않아 symbolic fallback으로 baseline 결정성을 유지한다.

현재 구현/계획의 좋은 점은 "추천의 근거가 무엇인지"가 비교적 명확하다는 것이다. 추천 응답의 `signals`와
decision log의 `feature_breakdown`이 같은 원 신호 계열을 공유하므로, 왜 특정 agent가 올라왔는지 추적할 수 있다.

---

## 3. 현재 축에서 아직 남은 일

현재 topic-expertise 추천 자체에도 미완성 지점이 있다.

### 3.1 real edge 통합

Phase 10의 핵심이다. mock edge가 아니라 memory-api의 `GroundingMatch`/`Competence`를
`AgentTopicEdge`로 투영해야 한다.

주요 작업:

- `/personal/groundings/{qid}` 기반 cross-owner 후보 수집
- `Competence` 신호를 `maturity`, `evidence_strength`, `freshness`, experience signal로 변환
- `support_ids`를 외부 응답/로그에서 쓸 수 있는 `evidence_refs`로 노출하거나 dereference하는 계약
- eligibility/privacy/safety/discoverable 계약 확정
- stance axis/dir/confidence를 어디서 만들지 확정

### 3.2 agentic context-aware grounding

Grounding은 기존 `symbolic exact-label + margin` primary에서 **agentic LLM-primary**로 재설계됐다
(shipped·기본 OFF `GROUNDING_AGENT_ENABLED`, dormant). 배경은 memory-api 검색에서 `context=`가 사라져
backend rank로 sense를 boost하는 접근이 폐기됐고, identical-label homonym tie를 symbolic만으로 깰 수
없기 때문이다.

현재 shipped된 구조 (기본 OFF, dormant):

- moderator가 최근 대화 히스토리를 `context_messages`로 전달한다.
- Discovery는 wire에서는 bourbon-agent `ContextMessage` parity를 받고, 내부에서는 최소
  `GroundingContextMessage{speaker, time, text, system_event?}`로 projection한다.
- context가 있으면 grounding agent가 `search_entities` / `get_entity` / opt-in `get_connections` 도구를
  bounded loop로 호출해 QID를 고르거나 abstain한다.
- context가 없고 unique exact-label이면 symbolic adopt를 유지한다.
- context가 없고 tie/miss면 abstain이다 — 단 이는 **agent ON composition**(legacy rung 미주입) 기준이다.
  online 기본은 `GROUNDING_AGENT_ENABLED` OFF라 symbolic 사다리(rerank/expansion/substitution)가 그대로
  돌고, agentic 품질은 report-only stratum·eval에서 관찰한다.
- final QID는 membership guard, `get_entity` 상세 확인, confidence floor, observed-field evidence를 모두
  통과해야 한다.
- decision log에는 grounding trajectory block을 additive로 남긴다.

이 작업은 "Python" 같은 동음이의 topic에서 dominant/default sense가 아니라 실제 대화 맥락에 맞는 sense를 고르게
하기 위한 것이다. 자세한 설계는
[Grounding Agent 재설계 spec](../docs/superpowers/specs/2026-07-15-grounding-agent-redesign-design.md)을 따른다.

### 3.3 Open Beta gate 필드

Open Beta에서는 단순 `discoverable`만으로는 부족하다.

- privacy clearance
- safety verdict
- visibility scope
- blocked/report state
- beta policy에 따른 exposure rule

이 필드들은 추천 품질 신호가 아니라 먼저 통과해야 하는 노출 게이트다.

---

## 4. 현재 약한 축 — personalized/social recommendation

현재 구현은 "topic에 적합한 agent"를 찾는 데 집중되어 있다. 제품 관점의 agent recommendation에서
상대적으로 약한 축은 다음이다.

### 4.1 사용자 관심사와 persona

현재 `Query.eligibility_context`와 `context_messages`는 grounding/gate를 돕는 **call-local 맥락**이지, 사용자의 장기 선호
모델이 아니다. `context_messages`는 "지금 이 대화에서 topic이 어떤 sense인지"를 고르기 위한 입력이고,
personalized recommendation을 위한 user profile은 별도 축이다.

아직 없는 것:

- 사용자가 선호하는 답변 깊이
- 사용자가 선호하는 agent 스타일
- 사용자가 자주 찾는 topic cluster
- 사용자가 신뢰하는 관점/전문성 유형
- 사용자의 persona와 agent persona의 compatibility

이 축이 들어오면 추천 질문은 다음처럼 바뀐다.

```text
"이 주제에 적합한 agent 중, 이 사용자에게 특히 맞는 agent는 누구인가?"
```

### 4.2 social graph / trust graph

현재 ranking에는 사용자와 agent owner 간 관계가 없다.

향후 고려할 신호:

- 내가 팔로우하거나 신뢰하는 사람이 만든 agent
- 내 관계망에서 많이 사용한 agent
- 나와 비슷한 persona/관심사를 가진 사용자가 만족한 agent
- 같은 조직/커뮤니티 안에서 검증된 agent
- 신뢰도 높은 사용자의 평가가 누적된 agent

이 축은 단순 popularity와 다르다. 전체 인기보다 **나의 관계망 안에서의 신뢰**가 중요하다.

### 4.3 사용자 행동 기반 feedback

AIA/KTA 같은 고도 평가 프레임은 장기적으로 중요하지만, Open Beta 첫 버전에서는 더 단순한 참여 신호가
현실적이다.

초기 신호 후보:

| 신호 | 의미 |
|---|---|
| `impression` | 추천 목록에 agent가 노출됨. 클릭 여부와 무관한 분모 신호. |
| `click` / `open` | 사용자가 추천된 agent 상세/대화 진입 화면을 열었음. 노출 대비 관심 신호. |
| `conversation_started` | 실제 agent와 대화를 시작했음. 단순 클릭보다 강한 사용 의도 신호. |
| `follow-up question` | 첫 답변 이후 추가 질문을 했음. 대화가 이어질 만큼 유용했을 가능성. 단, 혼란 때문에 길어질 수도 있어 단독 긍정 신호로 보지 않음. |
| `early abandon` | 추천 agent를 열거나 대화를 시작한 뒤 매우 짧은 시간 안에 이탈. 낮은 적합도/불만족 가능성. |
| `revisit` | 같은 agent를 나중에 다시 방문하거나 재사용. 지속 가치/신뢰 신호. |
| `like` / `dislike` | 낮은 마찰의 명시적 만족/불만족 피드백. 조작·친분 편향 가능성이 있어 smoothing 필요. |
| `star rating` | 더 세밀한 명시적 평점. 초기에는 단순 like보다 수집 부담이 크지만 calibration에 유용. |
| `short review answer` | "도움 됐나요?", "왜 별로였나요?" 같은 짧은 문답형 피드백. 정성 이유를 얻는 데 사용. |
| `report` / `hide` / `dismiss` | 신고, 숨김, 추천 제외. safety/quality/개인 선호의 강한 부정 신호이며 ranking보다 gate/policy에도 연결될 수 있음. |

초기에는 명시적 피드백을 과도하게 신뢰하지 않고, 행동 신호와 함께 calibration 용도로 쓰는 편이 안전하다.

### 4.4 exploration / diversity / cold start

현재 ordering contract는 결정적이고 보수적이다. 하지만 추천 제품으로 가면 다음도 필요하다.

- 새 agent를 제한적으로 노출하는 exploration slot
- 같은 owner/같은 관점/같은 topic facet 과다 노출 방지
- 관계망 밖이지만 topic 적합도가 높은 agent 탐색
- 인기 agent 쏠림 방지
- feedback이 적은 agent의 cold-start 처리

이 레이어는 현재 ranker의 deterministic ordering 위에 곧바로 섞기보다, 별도 Open Beta 추천 정책으로 다루는 게
낫다.

---

## 5. 권장 레이어링

추천 알고리즘을 다음 3층으로 나눈다.

### Layer 1. Topic expertise retrieval/ranking — 현재 구현 중

역할:

- agentic context-aware topic grounding(QID 선택 또는 abstain)
- agent-topic edge retrieval
- eligibility gate
- need별 ranking
- reason/signals/decision log(+ grounding trajectory)

이 레이어는 "추천 가능한 전문성 후보 집합"을 만든다. 현재 Discovery의 주 책임이다.

### Layer 2. Beta feedback quality — Open Beta 초입

역할:

- 좋아요/별점/간단 리뷰/숨김 같은 저비용 피드백 수집
- click/conversation/revisit/abandon 같은 행동 로그 수집
- agent/topic별 품질·만족도 신호 생성
- 악의적/편향된 피드백을 바로 ranking에 과반영하지 않도록 smoothing

이 레이어는 AIA/KTA의 가벼운 전 단계다. 고도 LLM rubric보다 먼저, 사람들이 익숙한 참여 방식으로 추천 루프를
닫는다.

### Layer 3. Personalized/social recommendation — 이후 고도화

역할:

- user interest profile
- user persona preference
- social/trust graph
- similar-user behavior
- agent-owner relationship
- exploration/diversity policy

이 레이어가 "이용자의 관심사나 퍼소나에 따라 agent를 추천"하는 영역이다. 현재 Discovery 파이프라인의
부족한 부분이며, Phase 10 real edge가 안정된 뒤 별도 설계가 필요하다.

---

## 6. Open Beta에 맞는 현실적 접근

오픈베타에서 바로 복잡한 AIA/KTA/LLM-rubric 평가를 추천의 중심에 두지 않는다. 대신:

1. Topic expertise 추천을 먼저 안정화한다.
2. 추천 노출/클릭/대화 시작/재방문/이탈/간단 피드백을 기록한다.
3. 간단한 quality prior를 만든다.
4. 관계망/persona 신호는 별도 레이어로 점진 도입한다.

초기 추천은 다음 조합이 현실적이다.

```text
topic expertise ordering
+ eligibility/privacy/safety gate
+ simple beta feedback prior
+ light diversity rule
```

이후 고도화 추천은 다음으로 확장한다.

```text
topic expertise ordering
+ user interest/persona match
+ social/trust graph affinity
+ calibrated behavioral feedback
+ exploration/diversity policy
```

---

## 7. 현재 계획에 추가해야 할 future work

현재 문서/계획에 별도 축으로 추가할 후보:

| 항목 | 성격 | 위치 |
|---|---|---|
| `RecommendationFeedbackSignal` | Open Beta feedback 계약 | Phase 10 이후 / Open Beta |
| `UserAgentInteractionEvent` | impression/click/start/revisit/dismiss 로그 | Open Beta |
| `UserInterestProfile` | 장기 관심사/선호 모델 | Post-Alpha |
| `UserAgentAffinity` | 사용자-agent 관계/선호 점수 | Post-Alpha |
| `SocialTrustSignal` | 관계망 기반 신뢰 신호 | Post-Alpha |
| `PersonalizedRanker` 또는 re-ranking layer | topic expertise 결과 위 개인화 재정렬 | Post-Alpha |
| exploration/diversity policy | 노출 정책 | Open Beta 이후 |

주의할 점:

- 이 신호들을 현재 `AgentTopicEdge`에 억지로 넣지 않는다. `AgentTopicEdge`는 topic expertise edge다.
- social/persona/feedback은 agent-topic 전문성의 대체물이 아니라 **그 위에 얹는 추천 정책 신호**다.
- decision log에는 grounding trajectory와 나중의 personalized layer feature를 별도 블록으로 남겨야 한다.
  그래야 "어떤 QID로 해석됐는가", "전문성 때문에 올라온 것", "개인화 때문에 올라온 것"을 구분할 수 있다.

---

## 8. 결론

현재 구현 중인 Discovery는 추천 알고리즘의 **전문성 기반 후보 생성과 deterministic ranking**을 맡는다. 이 축은
Alpha/Pull API에 맞고, real edge 통합과 agentic context-aware grounding이 붙으면 "이 대화 맥락의 이 주제에
대해 누구를 추천할까"라는 문제는 꽤 단단해진다.

다만 제품으로서의 agent recommendation은 여기서 끝나지 않는다. 이후에는 persona, social graph, beta feedback,
사용자 행동 로그를 별도 개인화 레이어로 추가해야 한다. 그때의 핵심 질문은 "누가 잘 아는가"에서 "이 사용자에게
누가 맞는가"로 확장된다.
