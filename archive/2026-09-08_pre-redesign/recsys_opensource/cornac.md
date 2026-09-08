# Cornac 활용 검토

> **결론**: Cornac은 production service가 아니라 모델·modality·평가 방법을 같은 데이터로 비교하는
> 오프라인 실험 하네스다. 학습 이미지/CronJob에만 두고 **Cornac runtime은 요청 경로에 넣지 않는다.**
> §6-2의 요청 예는 *학습이 내보낸 artifact*를 읽는 얇은 scorer이지 Cornac을 서빙에 두는 것이 아니다
> (2026-09-03 명확화 — 배너와 §6-2가 모순으로 읽혔다).
>
> **역할**: 이 문서는 [`recommendation_scoring_design.md` §9-1](../recommendation_scoring_design.md)의
> Cornac 판정과 Q6 종결 근거다. 제품 요구사항이나 도입 결정을 여기서 새로 만들지 않는다.

## 1. 성격

Cornac은 Python 기반 multimodal recommender 비교 프레임워크다. interaction뿐 아니라 feature, text,
image, graph, sentiment modality를 모델에 연결하고 여러 모델과 metric을 한 experiment에서 비교한다.
[공식 저장소](https://github.com/PreferredAI/cornac)

REST API, online ingestion, requester authorization, cache, 배포 orchestration은 제공하지 않는다.

## 2. 입력

기본 Dataset은 UIR 또는 UIRT다.
[Data API](https://cornac.readthedocs.io/en/stable/api_ref/data.html)

```python
interactions = [
    ("user-a", "agent-b", 1.0),
    ("user-a", "agent-c", 0.4),
    ("user-d", "agent-b", 1.0),
]
dataset = cornac.data.Dataset.from_uir(interactions)
```

timestamp를 포함하면 `(user, item, value, timestamp)`다. 여러 event는 공용 feature extractor에서 confidence로
집계한다. exposure되지 않은 pair를 negative로 오인하지 않는다.

`FeatureModality`는 ID와 정렬된 dense/sparse 2차원 배열을 받는다.

```python
user_modality = FeatureModality(
    ids=["user-a", "user-d"],
    features=np.array([
        # seeks coffee, prefers ko, concise
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 0.0],
    ]),
)
```

topic·traits를 multi-hot/수치/embedding으로 만드는 로직은 우리 소유다. `GraphModality`의
`(source_user, target_user, value)`로 friendship 실험도 가능하지만 관계 feature와 authorization은 다르다.

### 이번 요청 topic은 user modality나 UIRT 행이 아니다

A의 장기 feature가 영화·위스키이고 이번 요청만 커피라고 하자.

```text
Cornac user modality(A) = movie, whisky, ko, concise
request query           = coffee
```

커피 요청 한 건 때문에 user feature vector의 coffee bit를 1로 바꾸지 않는다. request topic은 discovery가
커피 agent 후보를 만들 때 사용하고, Cornac scorer는 그 candidate indices 안에서 A의 기존 model score를
계산한다.

```python
coffee_candidates = grounding_and_gate(topic="coffee", requester="user-a")
ranked, scores = model.rank(
    user_idx=user_index["user-a"],
    item_indices=[item_index[agent_id] for agent_id in coffee_candidates],
    k=-1,
)
```

추천 요청 자체도 UIRT interaction을 만들지 않는다.

```text
recommend(topic=coffee)          → UIRT 없음
agent가 실제 노출됨              → exposure dataset에 기록
agent 선택·대화·해결             → aggregation 규칙을 통과하면 UIRT positive 후보
사용자가 coffee interest를 추가  → 다음 profile snapshot의 user modality 변경
```

Cornac offline experiment에서 query topic을 사용하려면 request replay dataset의 context/candidate-set column으로
보존한다. 그것을 user modality로 합치면 한 번의 탐색이 영구 선호처럼 모든 미래 요청에 적용된다.

### 2-1 원본 event에서 UIRT를 만드는 예

```python
from collections import defaultdict

from agent_discovery.scoring.features import aggregate_behavioral_confidence


def to_uirt(events: list[dict]) -> list[tuple[str, str, float, int]]:
    grouped = defaultdict(list)
    for event in events:
        grouped[(event["requester_user_id"], event["personal_agent_id"])].append(event)

    rows = []
    for (user_id, agent_id), pair_events in grouped.items():
        value = aggregate_behavioral_confidence(pair_events)
        if value <= 0:
            continue
        latest = max(event["occurred_at"] for event in pair_events)
        rows.append((user_id, agent_id, value, int(latest.timestamp())))
    return rows
```

이 함수가 production scoring feature extractor와 별개로 생기면 training/serving skew가 된다. 실제 구현은
공용 event aggregation module을 train/evaluate 양쪽이 import해야 한다.

### 2-2 실험 하나의 전체 모양

```python
import cornac
from cornac.eval_methods import RatioSplit
from cornac.metrics import AUC, MAP, NDCG, Precision, Recall
from cornac.models import BPR, WMF

uirt = to_uirt(events)

evaluation = RatioSplit(
    data=uirt,
    fmt="UIRT",
    test_size=0.2,
    val_size=0.1,
    rating_threshold=1.0,
    seed=42,
    exclude_unknowns=False,
)

experiment = cornac.Experiment(
    eval_method=evaluation,
    models=[
        BPR(k=32, max_iter=100, seed=42),
        WMF(k=32, max_iter=100, seed=42),
    ],
    metrics=[
        Precision(k=10),
        Recall(k=10),
        NDCG(k=10),
        AUC(),
        MAP(),
    ],
    user_based=True,
    verbose=True,
)
experiment.run()
```

`RatioSplit`은 API 예시를 보여주기 위한 시작점이다. 실제 gate에서는 무작위 분할 대신 시간 분할을
구성해야 한다. `exclude_unknowns=False`도 cold-start를 숨기지 않기 위한 실험 선택이며, 모델별 unknown
처리를 확인해야 한다. Cornac `Experiment`는 eval method, 여러 model, 여러 metric을 한 번에 실행한다.
[Experiment API](https://cornac.readthedocs.io/en/stable/api_ref/experiment.html)

## 3. 출력

[Model API](https://cornac.readthedocs.io/en/stable/api_ref/models.html)는 original ID top-K 또는 후보 subset의
index·score를 반환한다.

```python
item_ids = model.recommend("user-a", k=10, remove_seen=True, train_set=train_set)
ranked, scores_in_input_order = model.rank(
    user_idx,
    item_indices=candidate_indices,
    k=-1,
)
```

점수는 모델 간 공통 척도가 아니다. wire에 노출하거나 고정 threshold로 읽지 않고 model version과 함께
ordering signal로 쓴다.

### 3-1 모델 저장과 online adapter

Cornac model은 `save()`/`load()`를 제공한다. 모델만 저장해도 raw ID와 내부 index의 대응 및 일부 평가에
train set이 필요할 수 있다. 배포 bundle에 model file 하나만 복사하지 않는다.

```python
model_path = model.save(
    save_dir="artifacts/cornac/2026-08-28.1",
    save_trainset=True,
    metadata={
        "feature_version": "features-v3",
        "visibility_projection": "public-candidate-v1",
    },
)
```

```python
class CornacScorer:
    def __init__(self, model, train_set, item_index: dict[str, int]):
        self._model = model
        self._train_set = train_set
        self._item_index = item_index

    def score_candidates(self, requester: str, candidates: list[str]) -> dict[str, float] | None:
        user_index = self._train_set.uid_map.get(requester)
        if user_index is None:
            return None  # cold user: 0이라는 측정값을 만들지 않는다.

        known = [(item, self._item_index[item]) for item in candidates if item in self._item_index]
        if not known:
            return None

        candidate_indices = [index for _, index in known]
        ranked_indices, scores_in_input_order = self._model.rank(
            user_index,
            item_indices=candidate_indices,
            k=-1,
        )
        score_by_index = dict(zip(candidate_indices, scores_in_input_order, strict=True))
        raw_by_index = {index: raw_id for raw_id, index in known}
        return {
            raw_by_index[index]: float(score_by_index[index])
            for index in ranked_indices
        }
```

위 코드는 구조 예시다. Cornac의 internal mapping을 직접 추측하지 말고 선택한 model과 저장한 train set으로
round-trip fixture를 만들어 raw ID 복원을 검증한다. `ranked_indices`는 점수순이지만 반환 score 배열은
입력 `item_indices` 순서에 대응하므로 둘을 단순 zip하지 않는다. candidate subset에서는 `k=-1`로 전부
정렬한 뒤 우리 코드가 top-K를 자른다. 조사·구현 시 Cornac 버전을 pin하고 이 계약을 테스트로 고정한다.

## 4. 역할, topic, bio

```text
row user-a     = requester representation
column agent-a = candidate representation owned by user-a
```

| 원천 | modality 후보 | 주의 |
|---|---|---|
| topic IDs | sparse FeatureModality | stable topic_id 사용 |
| bio/traits | dense feature/embedding | requester/candidate projection 분리 |
| persona text | TextModality/embedding | sharable만, 삭제 정책 필요 |
| friendship | GraphModality | gate 대체 금지 |
| conversation | UIR/UIRT | exposure와 positive 분리 |

모든 모델이 모든 modality를 읽지는 않는다. 한 번에 하나씩 축을 추가하되 candidate 생성 변화와
reranker 변화를 같은 축에 놓지 않는다.

```text
candidate axis: C0 현재 topic-api + gate / C1 이후 승인된 추가 source
reranker axis: R0 현재 RRF
               R1 LR(topic·surface·missingness)
               R2 R1 + interaction model score (D8 통과 시)
               R3 R1 + 승인된 public modality
```

## 5. visibility

```text
candidate item feature = public topic/bio only
requester user feature = 그 owner에게 사용이 허용된 입력만
friends feature        = global artifact에서 제외, online requester-aware 계산
```

friends graph를 넣었다고 friends-only content를 전역 item feature에 넣어도 되는 것은 아니다. latent model은
정보를 섞으므로 응답에서 필드만 지워 회수할 수 없다. 원본 snapshot, ID map, model, derived embedding에
같은 retention/deletion lineage를 붙인다.

### 5-1 제외와 후보 pool 지원 범위

Cornac의 공용 `rank()`는 `item_indices`를 받아 **그 후보 index 안에서만** 순위를 계산한다. 반면 original
ID를 받는 편의 함수 `recommend()`는 전체 known item을 대상으로 하며 `remove_seen` 정도만 제공한다.
[Model API](https://cornac.readthedocs.io/en/stable/api_ref/models.html)

| 요구 | Cornac API | 우리 책임 |
|---|---|---|
| arbitrary candidate pool | `rank(user_idx, item_indices=...)` | raw ID→index 변환과 gate |
| 이미 본 item 제외 | `recommend(..., remove_seen=True, train_set=...)` | “seen”이 제품 의미와 같은지 결정 |
| arbitrary denylist | 전용 공통 인자 없음 | pool에서 먼저 빼거나 candidate index 차집합 |
| unknown/new item | 모델에 따라 score 불가 | content ordering과 exploration fallback |
| 전역 삭제·정책 차단 | model 기능이 아님 | snapshot과 online gate 양쪽에서 제거 |

우리 경로에서는 전체 추천용 `recommend()`보다 candidate subset용 `rank()`가 맞다.

```python
eligible_raw_ids = eligibility.filter(
    requester_user_id=requester_user_id,
    candidates=grounded_candidates,
)
known = [
    (raw_id, item_index[raw_id])
    for raw_id in eligible_raw_ids
    if raw_id in item_index
]
ranked_indices, candidate_scores = model.rank(
    user_idx,
    item_indices=[index for _, index in known],
    k=-1,
)
```

`item_indices`가 권한을 판정하는 것은 아니다. Cornac은 전달된 index가 Alice에게 허용되는지 모른다. topic
grounding, `public/friends/private`, self-exclusion, block/safety를 우리 코드가 먼저 적용한다.

```text
grounded candidates
  → requester-aware gate
  → raw ID를 Cornac item index로 프로젝션
  → rank(item_indices=eligible)
  → 신규/unknown item을 규칙 점수로 합류
```

후보 pool이 비면 `rank()`를 전체 item fallback으로 다시 호출하지 않는다. 빈 pool은 권한 또는 grounding의
결과일 수 있으므로 전체 catalogue 추천으로 바꾸면 제외한 후보가 되살아난다.

채택할 모델별 contract test는 다음을 고정한다.

1. 전달하지 않은 item index가 결과에 나오지 않는다.
2. 입력 pool 순서를 바꿔도 같은 순위가 나온다.
3. 한 item을 pool에서 제거하면 결과에도 없다.
4. unknown item은 낮은 점수로 위장되지 않고 별도 fallback으로 간다.

### 5-2 확장성: 전체 사용자 pool 1억

Cornac은 비교 실험과 multimodal 모델 구현을 쉽게 만드는 프레임워크다. 일부 구현이 OpenMP, GPU 또는 ANN
wrapper를 지원하지만, 모든 모델을 1억 user/item에 공통으로 분산 학습시키는 하나의 cluster 계약을
제공한다고 가정하지 않는다. 모델마다 메모리·학습 복잡도와 auxiliary modality 비용이 크게 다르다.

factor 64의 단순 user/item matrix만 보더라도 requester 1억 + candidate agent 1억이면 `float32` factor
배열 하한이 51.2 GB다. Cornac Dataset의 ID map, interaction, modality matrix, train/validation/test와 모델별
working memory가 추가된다. text embedding 768차원을 item 1억 개에 그대로 보관하면 `float32` 값만 약
307.2 GB이므로, “bio도 함께 넣을 수 있다”와 “전체 1억에 그대로 넣는다”는 다른 결정이다.

따라서 Cornac의 1차 역할은 full production population 학습기가 아니라 **표본과 active cohort에서 모델
가치를 판별하는 실험 하네스**다.

```text
100M registered population
  ├─ 시간 기준 active cohort
  ├─ head/tail topic stratified sample
  ├─ cold requester/agent holdout
  └─ friends/public visibility strata
        → candidate snapshot C* × reranker R* 교차 비교
```

표본 실험에서 이긴 모델만 목표 active snapshot으로 단계 확대한다.

1. 1% 데이터로 구현과 metric 방향을 검증한다.
2. 10%에서 peak RSS, train time, artifact와 modality 크기를 기록한다.
3. 전체 active cohort 예상치를 단순 선형 외삽하지 말고 실제로 한 단계 더 실행한다.
4. 단일 node/GPU 예산을 넘으면 그 모델의 distributed 구현 또는 feature 축소를 별도 비교한다.
5. production에서는 이미 좁혀진 `item_indices`만 score하여 catalogue-wide ranking을 피한다.

Cornac ANN integration은 전체 item retrieval을 빠르게 할 수 있지만, 현재 request는 topic grounding과 권한
gate 이후 작은 pool을 rerank한다. ANN을 먼저 도입하면 권한 필터가 어려운 1억 전역 검색을 다시 만드는 셈일
수 있다. exact request pool이 수천 이하라면 단순 subset score가 더 예측 가능하다.

#### Cornac 샤딩 전략

Cornac에서는 **실험 데이터 병렬화**와 **하나의 model 학습 샤딩**을 구분한다.

안전하게 나눌 수 있는 작업:

- 시간·topic·activity stratum별 독립 evaluation job
- hyperparameter/model 후보별 병렬 Experiment
- request replay metric의 user partition 후 numerator/denominator 합산
- production factor artifact를 user/item ID hash로 나눈 serving lookup

독립 job 결과를 합칠 때 metric은 sample size와 동일 모집단 정의를 보존한다. 모델별 실험을 병렬로 실행하는
것은 하나의 모델을 분산 학습하는 것이 아니다.

```text
Experiment shards
  BPR(k=32) cohort A ─┐
  BPR(k=32) cohort B ─┼─→ metric aggregation은 가능
                      └─→ model parameter merge는 불가
```

cohort A/B에서 각각 학습한 factor model은 latent 좌표계가 다르므로 user/item factor나 점수를 단순 평균·병합할
수 없다. full active cohort model이 단일 node를 넘는다면 다음 중 하나를 새 결정으로 택한다.

1. Cornac에서 선정한 알고리즘의 공식/검증된 distributed 구현으로 재학습한다.
2. feature/factor 차원과 active window를 줄여 단일 artifact 계약을 유지한다.
3. tenant·region이 실제로 독립이면 domain별 model로 분리한다.
4. Cornac은 sample benchmark에 남기고 production trainer를 다른 도구로 선택한다.

serving factor를 shard하는 경우에는 training이 만든 하나의 전역 좌표계를 유지한다.

```text
model version V
  user factors → hash(user_id) item-independent home shards
  item factors → hash(agent_id) item shards

request
  user factor 1개 + eligible item factors batch
  → 같은 V 안에서 dot product → merge
```

Cornac model object 자체가 factor export를 안정적으로 제공하는지는 선택 모델별로 다르다. private field를
긁어 범용 sharder를 만들지 않고, 모델별 exporter와 round-trip contract test가 있는 경우에만 이 구성을
쓴다. export할 수 없다면 작은 request pool scorer를 동일 process에 load하는 기존 구성을 유지한다.

Cornac을 full-scale production runtime으로 채택하려면 선택한 모델 하나에 대해 별도 capacity 문서를 만든다.
“Cornac이 된다”가 아니라 “BPR k=64, active U/I/nnz N, hardware H에서 train T시간·artifact S GB·p99 L ms”처럼
구체적인 계약이어야 한다.

## 6. 우리 시스템 배치

```text
agent_discovery/scoring/features.py   # serving과 공유하는 유일한 feature 정의
cli/train.py                          # Cornac 선택 사용
cli/evaluate.py                       # experiment + 우리 request replay 평가
```

Cornac은 `train` dependency group과 CronJob image에만 둔다. serving image가 수치/학습 stack을 import하지
못하게 boundary test를 둔다. artifact에는 model/feature/ID-map version, train window, visibility projection,
metrics를 기록한다.

Cornac의 all-catalog split/metric을 그대로 **쓰지 않는다**. 우리 문제는 요청마다 grounding과 gate가
candidate set을 바꾸는 group ranking이다. 모델 구현은 재사용하되 실제 request candidate set 재생과
gold/exposure 대조는 우리 harness가 소유한다. 비교표도 CF 모델 목록 하나가 아니라
`candidate/retrieval snapshot × reranker variant` 두 축으로 기록한다.

### 6-1 프레임워크이므로 필요한 배포 구성

Cornac을 설치했다고 endpoint가 생기지 않는다. 최소 네 조각이 더 필요하다.

```text
snapshot builder
  event partitions + public feature snapshots
    → UIRT + modality matrices + ID maps

experiment runner
  candidate configurations
    → report + selected challenger

artifact publisher
  model/trainset/maps/metadata/checksums
    → immutable object-store path + current pointer

serving adapter
  startup에서 검증·load
    → request candidate subset score
    → failure면 model signal absent
```

학습과 서빙 image도 다르다.

```text
training image: agent-discovery + numpy/scipy + Cornac + 선택 model의 추가 의존성
serving image:  agent-discovery + 실제 artifact 추론에 꼭 필요한 최소 runtime
```

선택 모델이 Cornac runtime 전체를 요구하면 serving image가 커진다. artifact를 작은 공용 형식(예: factor
matrix/선형 계수)으로 export할 수 있는지 PoC에서 측정한다. export가 model마다 다르면 범용 exporter를
미리 만들지 않는다.

### 6-2 요청 예

```python
async def order_for_request(command, grounded, candidates):
    eligible = await eligibility.filter(
        requester=command.requester_user_id,
        candidates=candidates,
    )
    model_scores = cornac_scorer.score_candidates(
        str(command.requester_user_id),
        [str(candidate.agent_id) for candidate in eligible],
    )
    return order_with_optional_signal(
        eligible,
        model_scores=model_scores,
        model_version=cornac_scorer.version if model_scores is not None else None,
    )
```

Cornac이 candidate를 만들게 두는 실험과 discovery candidate를 rerank하는 실험은 별도 challenger다. 전자는
coverage를 바꾸고 후자는 order만 바꾸므로 같은 지표 한 줄로 합치지 않는다.

## 7. PoC와 판정

1. 노출·feedback event schema가 생긴 뒤 시작한다.
2. 시간 분할과 requester/agent ID map을 고정한다.
3. candidate snapshot(C0, 이후 C1)과 reranker(R0~R3)를 별도 축으로 기록한다.
4. BPR·WMF score는 D8 밀도 gate를 통과한 뒤 R1의 optional feature challenger로 비교한다.
5. public topic modality는 R1 다음 challenger고, 승인된 source만 쓴다.
6. request candidate subset에서 NDCG, correct gain, false adoption, regression을 잰다.
7. cold requester/agent를 별도 stratum으로 본다.
8. artifact load 실패 시 현재 ordering으로 열화한다.

모델 교체 비용이 낮아지고 auxiliary modality가 재현 가능한 이득을 내면 채택한다. adapter/evaluation 수정이
모델보다 커지거나 작은 LR/GBDT가 같은 품질을 내면 benchmark 전용으로 축소한다.
