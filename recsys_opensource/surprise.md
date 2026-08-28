# Surprise 활용 검토

> **결론**: Surprise는 explicit rating 예측을 배우기 쉬운 기준선이다. 현재 필요한 implicit behavior,
> topic/bio feature, requester-aware 후보를 직접 지원하지 않으므로 주 학습 도구로는 맞지 않는다. 명시적
> 만족도 계약이 생기면 sanity baseline으로 쓴다.

## 1. 성격과 범위

Surprise는 Python의 scikit-learn 스타일 recommender 라이브러리다. SVD/SVD++, NMF, user/item k-NN,
baseline, co-clustering과 cross-validation/grid search를 제공한다.

공식 저장소가 범위를 명확히 제한한다: **explicit rating data용이며 implicit rating과 content-based
information을 지원하지 않는다.** [공식 저장소](https://github.com/NicolasHug/Surprise)

“대화를 시작했다”를 별점 5로 바꾸면 실행은 되지만 사건의 의미를 왜곡한다. 사용 편의가 데이터 계약을
정해서는 안 된다.

## 2. 입력

입력은 `(user_id, item_id, rating)`이다.

```python
ratings = pd.DataFrame([
    {"user": "user-a", "item": "agent-b", "rating": 5.0},
    {"user": "user-a", "item": "agent-c", "rating": 2.0},
    {"user": "user-d", "item": "agent-b", "rating": 4.0},
])
reader = Reader(rating_scale=(1, 5))
data = Dataset.load_from_df(ratings[["user", "item", "rating"]], reader)
```

정직한 rating 원천은 명시적 질문이 실제 product event로 있을 때뿐이다.

```text
“이 agent가 도움이 되었나요?” 1..5
“다시 추천받고 싶나요?” 1..5
```

카드 노출, 클릭, 대화 시작·길이, 재질의, 추정된 해결 여부는 rating이 아니다. positive-only이거나 맥락에
따라 부호가 달라지는 implicit event다.

## 3. 출력

한 pair의 출력은 Prediction 객체다.
[Algorithm API](https://surprise.readthedocs.io/en/stable/algobase.html)

```python
prediction = algo.predict("user-a", "agent-b")
```

```json
{
  "uid": "user-a",
  "iid": "agent-b",
  "r_ui": null,
  "est": 4.37,
  "details": {}
}
```

top-N은 독립 serving API가 아니다. 아직 rating하지 않은 pair의 예측을 만든 뒤 `est`로 정렬하는 예제가
공식 FAQ에 있다. [Top-N FAQ](https://surprise.readthedocs.io/en/stable/FAQ.html) 전체 anti-testset은 online
path에 두지 않고 discovery가 만든 작은 후보마다 `predict(uid, iid)`를 호출한다.

예를 들어 Alice에게 이미 privacy gate를 통과한 Bob·Carol 두 agent만 비교한다.

```python
eligible = ["agent-bob", "agent-carol"]
predictions = [algo.predict("alice", agent_id) for agent_id in eligible]
ordered = sorted(predictions, key=lambda p: (-p.est, p.iid))

for prediction in ordered:
    print(prediction.iid, prediction.est)
```

```text
agent-carol 4.31
agent-bob   3.84
```

`4.31`은 “Carol이 coffee topic에 더 정확하다”가 아니라 **Alice가 Carol에게 줄 것으로 예측한 rating**이다.
topic grounding, public/friends 판정, self-exclusion을 대신하지 않는다.

## 4. 역할과 traits

```text
Surprise user = requester_user_id
Surprise item = personal_agent_id
```

owner가 같은 users table에 있어도 candidate 역할은 item으로 분리한다. user-based k-NN은 rating pattern이
비슷한 requester를 찾는 것이지 candidate user의 public traits로 사람을 찾는 기능이 아니다.

```text
지원:       user-item-rating
직접 미지원: user/item feature, topic tags, bio, embedding, social graph
```

traits를 rating에 섞지 않는다.

```text
잘못된 값 = 만족도 + topic overlap + 같은 언어 + 성향 유사도
```

이 값은 rating도 아니고 신호별 평가도 불가능하다. traits는 우리 scorer의 별도 신호로 두고 `est`만 한
항으로 사용한다.

## 5. visibility와 cold start

Surprise는 privacy policy를 모른다.

- candidate universe는 public projection으로 만든다.
- friends 후보는 requester-aware gate가 허용한 pair만 predict한다.
- private trait는 rating model에 encode하지 않는다.
- rating과 raw ID map/model artifact에 retention 정책을 붙인다.

unknown user/item이면 기본 prediction으로 대체할 수 있다. 이를 정상 개인화로 읽지 말고 `known=false`로
기록해 cold-start 규칙으로 보낸다.

### 5-1 제외와 후보 pool 지원 범위

Surprise에는 `implicit.recommend(items=...)` 같은 top-N candidate-pool 인자가 없다. 핵심 API가
`predict(user, item)`이므로, 우리 코드가 허용된 pair만 만들어 하나씩 예측하는 방식으로 같은 결과를
구성한다.

| 요구 | Surprise 지원 | 우리 책임 |
|---|---|---|
| arbitrary candidate pool | 허용된 item마다 `predict(uid, iid)` | pool 생성·정렬·top-K |
| arbitrary denylist | 전용 필터 없음 | 예측 전에 제거 |
| 이미 rating한 item 제외 | `build_anti_testset()`은 offline 전체 미평가 pair 생성 | online에서는 직접 결정 |
| 전역 hidden/deleted item | 지원하지 않음 | catalogue snapshot과 gate에서 제외 |
| unknown user/item | default prediction 가능 | 개인화로 오인하지 않고 fallback |

```python
def rank_eligible(
    algo,
    *,
    requester_user_id: str,
    eligible_agent_ids: tuple[str, ...],
    limit: int,
):
    predictions = [
        algo.predict(requester_user_id, agent_id)
        for agent_id in eligible_agent_ids
    ]
    known = [
        prediction
        for prediction in predictions
        if not prediction.details.get("was_impossible", False)
    ]
    return sorted(known, key=lambda p: (-p.est, p.iid))[:limit]
```

`eligible_agent_ids`는 Surprise가 만들지 않는다.

```text
topic grounding
  → public/friends/private + self/block/safety gate
  → 허용된 requester–agent pair만 predict
  → predicted rating으로 보조 정렬
```

공식 FAQ의 `trainset.build_anti_testset()`은 알려진 모든 user–item 중 rating이 없는 pair를 만들어 offline
top-N 예제를 실행한다. [Top-N FAQ](https://surprise.readthedocs.io/en/stable/FAQ.html) 이것을 online request에
사용하면 현재 topic과 visibility에 무관한 catalogue 전체를 확장하므로 쓰지 않는다.

“이미 rating한 agent”도 자동 제외가 항상 정답은 아니다. rating이 만족도 기록이고 재추천이 허용된다면
과거 rating이 있다는 이유로 빼면 안 된다. 반대로 제품에서 “이미 평가한 카드 제외”가 계약이면 event store와
현재 candidate pool의 차집합을 우리가 만든다.

후보 수가 작으면 pair별 `predict()`가 단순하고 충분하다. 후보가 수천 개라서 호출 비용이 문제가 되면
Surprise 내부 최적화보다 먼저 왜 request gate가 그렇게 넓은지를 검토한다. Surprise는 exact-pool serving
engine이 아니라 explicit-rating baseline이라는 기존 역할과도 일치한다.

### 5-2 확장성: 전체 사용자 pool 1억

Surprise의 Trainset은 raw user/item ID를 inner integer ID로 매핑하고 user별·item별 rating 구조를 만든다.
공식 top-N 예제의 `build_anti_testset()`은 알려진 모든 user와 item의 **rating이 없는 pair**를 생성한다.
1억 requester × 1억 agent에서는 잠재 pair가 `10^16`이므로 이 경로는 크기 계산만으로 제외한다.

Surprise의 SVD도 user/item factor를 가진다. factor 64, `float32`라는 단순 하한만 적용해도 두 쪽 1억 row는
51.2 GB이고, 실제 dtype·bias·rating 구조·Python dict와 학습 buffer가 추가된다. KNN 계열은 유사도 구조에
따라 더 불리할 수 있다. Surprise는 공통 distributed training/serving 제품이 아니다.

따라서 1억 전체 pool에서 Surprise의 역할은 full-catalogue production model이 아니라 명시적 rating이 있는
표본의 sanity baseline이다.

```text
전체 100M
  → 실제 rating을 남긴 active requester/agent cohort
  → 시간·활동도·topic별 stratified sample
  → GlobalMean / BaselineOnly / SVD 비교
  → 현재 규칙·implicit challenger가 복잡성만 늘렸는지 확인
```

online에서는 full anti-testset을 만들지 않고 gate가 준 수십~수백 candidate pair만 `predict()`한다. 이
방식은 요청 latency는 통제하지만, model artifact 자체에 1억 user/item을 넣는 문제를 해결하지는 않는다.

#### Surprise 샤딩 전략

Surprise에 적합한 샤딩은 rating 원본과 평가 작업의 분할이다.

| 대상 | 가능한 방식 | 한계 |
|---|---|---|
| rating event store | `hash(requester_user_id)` + time partition | 중복·삭제 계약은 우리 책임 |
| offline evaluation | fold/model/parameter별 독립 job | metric은 합칠 수 있지만 model은 합칠 수 없음 |
| online candidate scoring | gate 후보를 worker에 batch 분배 | 각 worker가 같은 full model을 load해야 함 |
| model training | 기본 투명 shard 없음 | 독립 SVD factor를 단순 병합할 수 없음 |

다음 구성을 production 확장안으로 읽지 않는다.

```text
rating users를 10개 shard로 나눔
  → SVD model 10개 독립 학습
  → 각 model의 estimated rating을 하나의 순위로 merge
```

각 model의 bias·factor와 rating population이 다르므로 score calibration이 같다는 보장이 없다. user shard마다
item rating signal도 일부만 보아 collaborative 정보가 잘린다.

Surprise scorer replica를 수평 확장하는 것은 가능하지만 각 replica가 동일 model/trainset artifact를 읽는다.
request candidate가 수십~수백이면 CPU scoring 분산보다 process-local batch가 먼저다. artifact가 너무 커서
replica마다 복제할 수 없으면 Surprise의 역할 범위를 넘었다는 신호로 본다.

독립 model shard를 허용할 수 있는 경우는 tenant·region·rating scale·candidate catalogue가 실제로 분리되어
cross-shard 추천과 점수 비교가 전혀 없을 때뿐이다. 그 경우도 shard마다 별도 model version과 metric을
관리하며 전역 top-K로 합치지 않는다.

확장 판단은 다음과 같이 제한한다.

- rating population과 전체 가입자 수를 분리한다.
- 최소 rating 수를 충족한 active cohort만 baseline 학습 대상으로 삼는다.
- unknown user/item은 global mean 개인화로 위장하지 않고 rules/cold-start로 보낸다.
- 표본에서 얻은 RMSE를 전체 population latency·memory 적합성으로 해석하지 않는다.
- Surprise가 이긴다면 동일 알고리즘의 더 큰 규모용 구현을 별도 검토할 수 있지만, 그 결과를 Surprise 자체의
  1억 production 적합성으로 기록하지 않는다.

## 6. 시스템 배치와 평가

```text
explicit rating snapshot
  → Surprise SVD/KNN experiment
  → saved model + raw↔inner ID map
  → gate가 허용한 pair만 predict
  → 우리 가중합의 한 신호
```

현재는 rating 입력이 실재하지 않으므로 production module을 만들지 않는다. 실제 rating이 생긴 뒤
`cli/evaluate.py` 기준선으로만 추가한다.

Surprise는 Gorse처럼 실행 중인 별도 추천 서비스가 아니다. 라이브러리 채택은 다음 네 부품을 우리가
소유한다는 뜻이다.

```text
rating event store
  │
  ├─ snapshot/training job ──→ model artifact + metadata
  │                              │
  └─ discovery request ──→ gate ─┴─→ in-process predict adapter
                                      → weighted ordering
```

| 부품 | Gorse가 제공 | Surprise를 쓸 때 우리 책임 |
|---|---:|---|
| feedback 저장과 upsert API | 예 | event store와 중복 제거 |
| 학습 스케줄러 | 예 | CronJob/워크플로 |
| model registry | 일부 운영 흐름에 포함 | 버전·승격·rollback |
| online REST API | 예 | discovery process 안 adapter 또는 별도 사내 service |
| candidate privacy gate | 아니오 | 항상 우리 책임 |
| dashboard/A/B 배선 | 제공 기능 있음 | 실험 플랫폼과 직접 연결 |

### 6.1 학습 예시

아래는 explicit rating이 실제로 생겼다는 가정의 최소 학습 흐름이다.

```python
from pathlib import Path

import pandas as pd
from surprise import Dataset, Reader, SVD, dump


ratings = pd.read_parquet("ratings-2026-08-28.parquet")
reader = Reader(rating_scale=(1, 5))
dataset = Dataset.load_from_df(
    ratings[["requester_user_id", "personal_agent_id", "rating"]],
    reader,
)

# 최종 production fit은 검증을 마친 뒤 전체 train snapshot을 사용한다.
trainset = dataset.build_full_trainset()
model = SVD(n_factors=64, n_epochs=30, random_state=42)
model.fit(trainset)

Path("artifacts/surprise/2026-08-28.1").mkdir(parents=True)
dump.dump(
    "artifacts/surprise/2026-08-28.1/model.pkl",
    algo=model,
)
```

`surprise.dump`는 pickle 계열 artifact다. 신뢰하지 않는 artifact를 load하지 않고, model bucket의 쓰기 권한과
승격 주체를 제한한다. Python·Surprise 버전, rating schema, train window, git SHA, metric을 별도
`metadata.json`에 기록한다. [dump/load API](https://surprise.readthedocs.io/en/stable/dump.html)

```json
{
  "artifact_version": "2026-08-28.1",
  "algorithm": "SVD",
  "python": "3.13",
  "rating_scale": [1, 5],
  "train_window": ["2026-05-01", "2026-08-27"],
  "event_schema": 3,
  "source_commit": "…"
}
```

### 6.2 serving adapter 예시

프로세스 시작 때 승인된 artifact 하나를 읽고, request마다 gate가 준 candidate만 점수화한다.

```python
from dataclasses import dataclass
from surprise import dump


@dataclass(frozen=True, slots=True)
class RatingSignal:
    personal_agent_id: str
    estimated_rating: float | None
    known: bool


class SurpriseRatingScorer:
    def __init__(self, artifact_path: str) -> None:
        _, self._model = dump.load(artifact_path)

    def score(
        self,
        *,
        requester_user_id: str,
        eligible_agent_ids: tuple[str, ...],
    ) -> tuple[RatingSignal, ...]:
        result = []
        trainset = self._model.trainset
        requester_known = requester_user_id in trainset._raw2inner_id_users

        for agent_id in eligible_agent_ids:
            item_known = agent_id in trainset._raw2inner_id_items
            prediction = self._model.predict(requester_user_id, agent_id)
            known = requester_known and item_known and not prediction.details.get(
                "was_impossible", False
            )
            result.append(
                RatingSignal(
                    personal_agent_id=agent_id,
                    estimated_rating=prediction.est if known else None,
                    known=known,
                )
            )
        return tuple(result)
```

위 `_raw2inner_id_*`는 Surprise 내부 표현에 닿는 예시다. production adapter에서는 지원 버전을 pin하고
contract test를 둔다. 더 안전하게는 학습 때 raw ID 집합을 별도 artifact로 내보내 `known` 판정을 그 파일이
소유하게 한다. unknown pair의 global-mean 추정값을 개인화 결과처럼 사용하지 않는 것이 핵심이다.

### 6.3 artifact 교체

```text
train → temporary version directory → 검증 → READY marker
     → serving process가 새 버전 load/health-check
     → atomic pointer 교체 → 이전 버전 보관
```

request 중 model 객체를 바꾸지 않는다. 새 model을 완전히 읽은 뒤 참조를 한 번에 교체하고, 실패하면 이전
artifact를 계속 쓴다. 별도 Surprise service를 만들 수도 있지만, 모델이 작고 discovery와 같은 Python
runtime이면 처음에는 in-process adapter가 네트워크 홉과 별도 장애면을 만들지 않아 더 단순하다.

Surprise는 KFold, ShuffleSplit, LeaveOneOut, grid/random search를 제공한다.
[Model selection](https://surprise.readthedocs.io/en/stable/model_selection.html) 일반 KFold는 미래 rating이
과거 학습에 섞일 수 있으므로 먼저 시간 분할한다. RMSE/MAE뿐 아니라 request candidate set의 NDCG,
coverage, false adoption/regression, concentration을 함께 본다.

예를 들어 `2026-07-31`까지 학습하고 8월의 첫 rating을 test로 둔다. 자발적으로 rating을 남긴 사람만의
RMSE가 좋아져도 전체 추천이 좋아졌다고 결론내리지 않는다. rating 제출률, requester activity, 언어,
신규/기존 agent별로 선택 편향을 함께 보고, 실제 request 당시 노출 가능했던 후보 집합 안에서만 ranking
metric을 계산한다.

## 7. 실패와 열화 계약

| 상태 | online 동작 | 관측 |
|---|---|---|
| artifact 없음/손상 | 규칙 기반 ordering | `rating_model_available=false` |
| unknown requester | rating signal 없음 | `rating_requester_known=false` |
| unknown agent | 그 candidate의 rating signal 없음 | unknown item count |
| artifact schema mismatch | startup 또는 교체 거절 | version mismatch |
| predict 중 우리 결함 | 요청 전체를 조용히 평균값으로 대체하지 않음 | typed failure/alert |

rating signal은 보조 신호이므로 부재 시 전체 추천을 503으로 만들 필요는 없다. 단, “부재”를 `0점`이나
global mean으로 기록하지 않는다. 값 없음과 낮은 만족도는 다른 관측이다.

## 8. PoC 판정

착수 조건은 rating의 의미·scale·표본 선택 편향이 제품 계약으로 정의되는 것이다. 그때 GlobalMean,
BaselineOnly, KNN, SVD와 `현재 규칙 + rating signal`만 비교한다.

명시적 만족도가 충분하고 SVD/KNN이 행동 모델과 독립적인 이득을 주면 제한 채택한다. rating이 없거나
극소수 자발 응답만 있고 목표가 implicit engagement ranking이면 연기한다. 현재 상태는 후자다.
