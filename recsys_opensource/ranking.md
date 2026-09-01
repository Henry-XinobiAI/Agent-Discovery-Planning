# Learned reranking OSS 활용 검토

> **결론**: 요청별 gate가 만든 100~1,000개 후보에는 **LR request-group baseline**부터 쓴다. 라벨과
> 비선형 이득이 충분해지면 LightGBM `LGBMRanker`와 XGBoost ranker를 challenger로 비교한다. CF 점수를
> 최종 점수로 쓰지 않고 하나의 feature로 넣는다. 채택 판단은
> [`recommendation_scoring_design.md` §4·§9-3](../recommendation_scoring_design.md)가 소유한다.

## 1. 문제 형태

```text
request q
  → grounding + requester-aware gate
  → eligible agents [a₁ ... aₙ]
  → feature row (q, aᵢ)
  → ranker score
  → ordered top-K
```

학습 행의 그룹 키는 requester가 아니라 **recommendation decision/request(`qid`)**다. 같은 후보도 요청 topic,
surface, visibility, capacity에 따라 다른 그룹과 feature로 나타난다. 학습·평가 split도 행을 무작위로
나누지 않고 시간과 `qid` 경계를 지킨다.

## 2. 입력 예시

| qid | candidate | topic_rank | topic_rrf | lang_match | persona | implicit_score | implicit_missing | activity | label |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| req-1 | agent-b | 1 | 0.032 | 1 | 0.7 | null | 1 | 0.9 | 2 |
| req-1 | agent-c | 2 | 0.016 | 1 | 0.2 | null | 1 | 0.8 | 0 |
| req-2 | agent-b | 4 | 0.010 | 0 | 0.5 | -0.08 | 0 | 0.9 | 1 |

규율:

- privacy·safety·self-exclusion·hard capacity는 feature가 아니라 앞선 gate다.
- 신호 부재는 0으로 대체하지 않고 값 + missing indicator로 표현한다.
- `implicit_score`처럼 버전마다 좌표계가 달라지는 값은 표준화 규칙·source model version을 함께 남긴다.
- owner note나 사용자 원문을 feature row에 그대로 영구 저장하지 않는다. 승인된 파생값만 쓴다.
- train과 serve가 같은 `features.py`를 import한다.

## 3. LR baseline

```text
score = β₀(surface) + β_topic·topic_rrf + β_lang·lang_match
      + β_persona·persona + β_cf·implicit_score + β_missing·implicit_missing + ...
```

LR의 가치:

- 계수와 부호를 읽을 수 있어 feature·라벨 결함을 빨리 찾는다.
- 라벨이 적을 때 tree ensemble보다 과적합을 통제하기 쉽다.
- 작은 순수 추론 구현으로 export하기 쉽다.
- “수동 가중합”과 달리 계수는 학습 데이터가 정하고 versioned artifact로 남는다.

LR도 후보 행을 독립 분류하는 것만으로 충분하지 않을 수 있다. loss가 pointwise여도 평가와 calibration은
반드시 request group 안에서 한다. surface별 모델을 쪼개기 전에 surface와 interaction feature를 넣고,
표본이 충분한 경우에만 분리를 challenger로 둔다.

## 4. LightGBM ranker

[LightGBM `LGBMRanker`](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.LGBMRanker.html)는 각
query의 row 수를 `group=[...]`으로 받고 ranking objective를 학습한다. parameters에는 `lambdarank`와
feature별 [monotone constraints](https://lightgbm.readthedocs.io/en/latest/Parameters.html)가 있다.

```python
from lightgbm import LGBMRanker

model = LGBMRanker(
    objective="lambdarank",
    n_estimators=200,
    learning_rate=0.05,
    monotone_constraints=[1, 1, 0, 0, 0, 1],
)
model.fit(X_train, y_train, group=train_group_sizes)
scores = model.predict(X_request)
```

장점:

- 수치·범주·결측 feature의 비선형 상호작용을 싸게 학습한다.
- feature별 단조 제약으로 “활동성이 커질수록 다른 조건이 같을 때 불리해지지 않는다” 같은 방향을 강제할
  수 있다.
- 수백 행 batch 추론이 가볍다.

주의:

- 단조 제약은 **그 feature 하나에 대한 모델 출력 방향**이지 공정성·capacity 보장이 아니다.
- position-biased 행동 label을 그대로 넣으면 그 편향을 더 잘 학습한다. propensity/탐색 계약이 선행한다.
- category encoding과 model export/runtime을 PoC에서 고정해야 한다.

## 5. XGBoost ranker

[XGBoost learning-to-rank](https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/learning_to_rank.html)는
`qid`로 query group을 표현하고 `rank:ndcg`, `rank:map`, `rank:pairwise` objective를 제공한다. monotonic
constraints와 CPU/GPU·distributed training 선택지도 있다.

```python
from xgboost import XGBRanker

model = XGBRanker(
    objective="rank:ndcg",
    n_estimators=200,
    learning_rate=0.05,
    monotone_constraints={"topic_rrf": 1, "activity": 1},
)
model.fit(X_train, y_train, qid=qid_train)
scores = model.predict(X_request)
```

XGBoost 문서의 `lambdarank_unbiased`는 position bias를 다루는 선택지지만, 이것이 우리 propensity 이벤트와
estimand를 대신 정해 주지는 않는다. experimental option 하나를 근거로 N1을 생략하지 않는다.

## 6. 비교 기준

| 축 | LR | LightGBM | XGBoost |
|---|---|---|---|
| 초기 라벨 | 가장 적합 | 과적합 감시 필요 | 과적합 감시 필요 |
| 비선형·상호작용 | 제한 | 강함 | 강함 |
| ranking objective | 별도 구현/pointwise 가능 | Lambdarank | NDCG/MAP/pairwise |
| 단조 제약 | 계수 부호 | 지원 | 지원 |
| artifact 단순성 | 가장 단순 | runtime/export 검증 | runtime/export 검증 |
| distributed/GPU | 불필요 | 가능하지만 현재 불필요 | 가능하지만 현재 불필요 |

현재 후보 수와 예상 라벨에서는 GPU·distributed가 선택 이유가 아니다. 중요한 것은 request-group semantics,
결측 처리, artifact 재현성과 latency다.

## 7. CF 점수는 feature다

ALS score는 부호가 있을 수 있고 model version마다 scale이 바뀐다. 다음처럼 고정 계수로 다른 신호와
직접 합치면 계수의 의미가 artifact마다 변한다.

```text
금지에 가까운 구성: 0.5 × topic_score + 0.3 × als_score
```

대신 source version과 missingness를 가진 feature로 넣는다.

```json
{
  "implicit_score": -0.081,
  "implicit_score_missing": false,
  "implicit_model_version": "als-12"
}
```

GBDT가 있다고 scale 문제가 자동으로 사라지는 것은 아니다. 분포가 바뀌면 split 의미도 바뀌므로 ranker와
source model을 한 training snapshot에서 함께 version하고, source artifact 교체 시 ranker를 재검증한다.

## 8. 평가와 채택 게이트

```text
same time split
same request qids
same eligible candidate replay
same labels and propensity treatment
  → deterministic baseline
  → LR
  → LR + implicit feature (밀도 gate 통과 시)
  → LightGBM / XGBoost challenger
```

최소 결과:

- request-group NDCG/Recall뿐 아니라 false adoption·coverage·집중도를 함께 낸다.
- cold requester, 신규 agent, 신호 부재 cohort를 따로 낸다.
- calibration이 필요한 product decision이면 ranking metric과 별도로 검증한다.
- p50/p95 latency와 artifact size·load time을 잰다.
- LR보다 좋아진 feature ablation을 제시한다.
- supply capacity hard limit은 ranker가 아니라 gate가 지킨다.

“positive label이 N개를 넘었다”는 GBDT 채택 조건이 아니다. 같은 request replay에서 위 지표와 운영 비용이
LR을 이길 때만 전환한다.

## 9. library 형태의 운영 구성

LightGBM·XGBoost는 Gorse 같은 서비스가 아니다.

```text
append-only decisions/rewards
  → snapshot + shared feature extraction
  → train/evaluate CLI
  → versioned artifact + schema metadata
  → serving process loads artifact
  → request candidate rows → predict → deterministic tiebreak
```

우리가 추가로 소유할 것:

- artifact registry, checksum, feature schema version, rollback
- raw ID와 row의 안정적 결합
- train/serve 공용 extractor와 import boundary
- model absence fallback
- shadow/canary promotion과 요청별 model version event
- 현재·과거 artifact의 삭제 SLA

별도 ranker microservice는 기본안이 아니다. 후보 수백 개의 in-process 추론을 네트워크 홉으로 바꿀 이유가
관측될 때만 연다.
