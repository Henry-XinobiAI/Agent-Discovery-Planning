# Off-policy 평가 도구 활용 검토

> **결론**: 패키지를 먼저 고르지 않는다. N1에서 먼저 고정할 것은 **무엇의 반사실을 추정할지
> (estimand)**와 그 값을 식별할 수 있는 exposure·propensity 계약이다. 초기 batch evaluator 후보는
> Open Bandit Pipeline(OBP), 탐색 정책까지 함께 검증할 후보는 Vowpal Wabbit(VW)다. 요구사항과 채택
> 판단은 [`recommendation_scoring_design.md`](../recommendation_scoring_design.md)가 소유한다.

## 1. 왜 지금 조사하는가

추천 정책이 후보와 순서를 정하면 이후 행동은 그 노출에 조건부로 생긴다. 기존 정책이 보여주지 않은
후보의 보상은 관측되지 않는다. IPS·SNIPS·DR은 이 편향을 줄일 수 있지만, 로그에 당시 선택 확률과
후보 집합이 없으면 사후에 복구할 수 없다.

```text
eligible candidates C(x)
  → logging policy π₀(a|x, C)
  → shown action/slate a + propensity p
  → delayed reward r
  → target policy π₁의 가치 추정
```

결정적 정책만 쓰면 선택된 action은 `p=1`, 선택되지 않은 action은 `p=0`이다. target policy가 다른 후보를
고르는 영역에는 overlap이 없어 IPS도 DR도 답하지 못한다. 그래서 **탐색 슬롯과 propensity 이벤트는 한
작업**이다.

## 2. estimator보다 먼저 정할 estimand

| 질문 | action 단위 | 필요한 propensity |
|---|---|---|
| 후보 한 명을 보여줬다면 선택됐는가 | item | 그 문맥에서 그 item이 해당 자리에 갈 확률 |
| top-K 목록 전체가 더 나았는가 | ordered slate | 목록의 joint probability 또는 자리별 conditional probability |
| 1번 자리만 다른 정책이었다면 | position-aware item | 이전 자리 선택을 조건으로 한 확률 |
| 최종 대화 해소가 좋아졌는가 | slate/request | attribution window와 censoring 계약까지 필요 |

`candidate_propensity=0.2` 하나만 남기고 실제로는 5개 순서 전체의 가치를 묻는 것은 계약 위반이다.
without-replacement 순서를 뽑는다면 예를 들어 각 자리의 조건부 확률을 남긴다.

```json
{
  "decision_id": "dec-123",
  "position": 2,
  "personal_agent_id": "agent-b",
  "conditional_propensity": 0.18,
  "previous_agent_ids": ["agent-a"],
  "logging_policy_version": "explore-3"
}
```

joint propensity가 필요하면 같은 decision의 조건부 확률을 곱할 수 있지만, underflow와 로그 누락을 피하려면
`log_propensity`도 함께 저장하는 편이 안전하다.

## 3. N1 이벤트에 필요한 필드

### 3-1 decision 한 건

```json
{
  "decision_id": "dec-123",
  "request_id": "req-123",
  "requester_user_id": "user-a",
  "surface": "topic_search",
  "requested_topic_ids": ["topic-coffee"],
  "eligible_candidate_ids": ["agent-a", "agent-b", "agent-c"],
  "excluded_counts": {"privacy": 3, "self": 1, "capacity": 0},
  "feature_version": "features-2",
  "ranker_version": "lr-7",
  "logging_policy_version": "epsilon-slot-3",
  "occurred_at": "2026-08-31T12:00:00Z"
}
```

### 3-2 노출 행

```json
{
  "decision_id": "dec-123",
  "personal_agent_id": "agent-b",
  "position": 2,
  "conditional_propensity": 0.18,
  "log_propensity": -1.7148,
  "exploration": true
}
```

### 3-3 reward 행

```json
{
  "decision_id": "dec-123",
  "personal_agent_id": "agent-b",
  "event_type": "resolved_without_requery",
  "value": 1.0,
  "occurred_at": "2026-08-31T12:18:00Z",
  "attribution_window": "24h",
  "finalized": true
}
```

필수 규율:

- eligible set은 **gate 뒤·ranker 전**의 집합이다. hand-added fixture를 섞지 않는다.
- 후보 feature를 원문으로 영구 저장할 필요는 없지만, 당시 값을 재구성할 snapshot/version이 있어야 한다.
- `policy_version`만 있고 실제 확률을 재현할 random seed·모수·후보 집합이 없으면 검증이 불가능하다.
- 지연 reward는 아직 안 왔음과 부정 결과를 구분한다. `finalized=false`를 0점으로 읽지 않는다.
- 사용자·후보 ID가 있으므로 보존·삭제·접근제어는 application log와 분리한다.

## 4. 추정기별 의미와 실패 조건

| 추정기 | 요약 | 장점 | 실패/주의 |
|---|---|---|---|
| IPS | `π₁/π₀ × reward` | 단순하고 정책 차이를 직접 보정 | 작은 propensity에서 분산 폭발, overlap 없으면 불가 |
| SNIPS | IPS를 weight 합으로 정규화 | 유한 표본에서 안정적인 경우가 많음 | 편향이 생기며 support 문제는 해결 못 함 |
| DM | reward model로 모든 action 예측 | 낮은 분산 | reward model이 틀리면 그대로 편향 |
| DR | DM + IPS residual | logging 또는 reward model 중 하나가 맞으면 강건 | 둘 다 틀리거나 overlap 없으면 실패 |
| clipped/switch | 큰 importance weight를 제한·DM으로 전환 | variance 제어 | clip/switch 값이 새 정책 결정이므로 사전 선언 필요 |

점추정 하나만 보고 채택하지 않는다. effective sample size, weight 분포, 최대 weight, overlap 위반 수,
bootstrap confidence interval을 같은 결과에 붙인다.

## 5. OSS 후보

### 5-1 Open Bandit Pipeline

[OBP](https://zr-obp.readthedocs.io/en/latest/)는 bandit dataset·policy learning·IPS/DR 계열 OPE를 한
Python 프레임워크에 둔다. 여러 estimator를 같은 logged bandit feedback에 적용하고 synthetic data로
편향/분산을 검증하기 좋다.

우리 구성:

```text
event snapshot
  → request/action/reward 배열 adapter
  → OBP estimators
  → estimator별 value + CI + ESS report
```

주의: 우리 제품은 top-K ordered slate다. OBP의 contextual bandit 예제에 맞추려고 slate를 독립 item 행으로
찢으면 joint exposure를 잃을 수 있다. 첫 PoC는 “탐색 슬롯 한 자리” estimand로 좁히고, 전체 slate 평가는
별도 계약 테스트 뒤에 연다.

### 5-2 Vowpal Wabbit

[VW contextual bandit](https://vowpalwabbit.org/docs/vowpal_wabbit/python/latest/tutorials/python_Contextual_bandits_and_Vowpal_Wabbit.html)은
context·action·probability·cost를 입력으로 online learning과 exploration을 제공한다. `cb_explore_adf`는
요청마다 action 집합이 달라지는 경우를 표현할 수 있다.

```text
shared | request/surface features
| candidate agent-a features
| candidate agent-b features
→ chosen action + probability
→ action:cost:probability feedback
```

장점은 logging policy와 learner가 같은 구현에 있어 propensity 생성 경로가 명확하다는 점이다. 대가는
VW runtime·feature text/binary 계약·online artifact 운영을 새로 소유하는 것이다. 초기 LR ranker 전체를
VW로 대체하지 말고 **탐색 정책 challenger**로만 검증한다.

## 6. 권장 실험 순서

1. 탐색 슬롯 한 자리의 estimand와 reward window를 결정한다.
2. synthetic policy에서 알려진 정답을 만들고 IPS·DR이 회복하는지 contract test를 쓴다.
3. N1 event를 shadow로 기록해 propensity 합, eligible-set replay, 중복 decision을 검증한다.
4. 아주 작은 exploration traffic에서 overlap·ESS·weight tail을 측정한다.
5. OBP estimator report와 직접 계산한 작은 fixture를 교차 검증한다.
6. VW는 탐색 정책 운영이 자체 구현보다 싼지 별도 PoC한다.

## 7. 채택 게이트

- propensity를 사후 추측하지 않고 logging policy가 생성 시점에 기록한다.
- target policy의 action support가 logging policy support 안에 있다.
- delayed/censored reward가 0과 구별된다.
- item estimand와 slate estimand를 섞지 않는다.
- estimator 결과에 CI·ESS·weight diagnostics가 붙는다.
- 삭제 요청이 snapshot·report·artifact에 반영되는 SLA가 있다.

이 조건이 닫히기 전에는 “DR을 쓴다”는 라이브러리 선택일 뿐 평가 설계가 아니다.
