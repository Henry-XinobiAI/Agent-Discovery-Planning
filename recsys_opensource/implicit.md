# implicit 활용 검토

> **결론**: `implicit`은 대화 시작·재방문·선택처럼 별점이 없는 행동 데이터로 첫 collaborative baseline을
> 만들기에 가장 직접적이다. bio/traits와 visibility는 직접 지원하지 않으므로 discovery gate와 자체
> feature score를 유지한 채 personalization 신호 하나로 사용한다.

## 1. 성격

`implicit`은 implicit-feedback collaborative filtering용 Python/Cython 라이브러리다. ALS, BPR,
Logistic Matrix Factorization, cosine/TF-IDF/BM25 item-item 모델과 CPU multi-thread, 일부 CUDA 구현을
제공한다. [공식 저장소](https://github.com/benfred/implicit)

서버나 데이터 수집기가 아니다.

```text
sparse interaction matrix → fit → factor artifact → IDs/scores
```

## 2. 입력

입력은 `(number_of_users, number_of_items)` CSR sparse matrix다. nonzero는 관측 positive, 값은 좋아할
confidence다. [Model API](https://benfred.github.io/implicit/api/models/recommender_base.html)

```python
# rows=requesters, columns=personal agents, values=positive confidence
user_items = scipy.sparse.csr_matrix(...)
model = implicit.als.AlternatingLeastSquares(factors=64)
model.fit(user_items)
```

event projection의 예시는 다음과 같다. 숫자는 결정값이 아니다.

```text
exposure only                         0
card selected                         +1
conversation started                  +2
resolved without re-query             +3
same topic re-queried elsewhere       별도 negative/weight 정책
```

- 0은 “싫어함”이 아니라 대부분 “관측하지 않음”이다.
- exposure 없이 선택 기회가 없었던 agent를 negative로 학습하지 않는다.
- 대화 깊이는 목적에 따라 부호가 달라 단독 positive로 쓰지 않는다.
- 시간 감쇠와 event aggregation은 공용 feature extractor가 소유한다.

문자열 ID를 integer index로 바꾸는 versioned map도 artifact 일부다.

```json
{
  "users": {"user-a": 0, "user-d": 1},
  "items": {"agent-b": 0, "agent-c": 1},
  "version": "2026-08-28.1"
}
```

### 2.1 event에서 CSR까지

source event는 모델 행렬이 아니다. 먼저 중복 제거·시간 감쇠·노출 자격을 적용한 projection을 만든다.

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Interaction:
    requester_user_id: str
    personal_agent_id: str
    event: str
    occurred_at: datetime


EVENT_CONFIDENCE = {
    "card_selected": 1.0,
    "conversation_started": 2.0,
    "resolved": 3.0,
}
```

```python
import numpy as np
from scipy.sparse import coo_matrix


def build_matrix(interactions: list[Interaction]):
    user_ids = sorted({x.requester_user_id for x in interactions})
    item_ids = sorted({x.personal_agent_id for x in interactions})
    user_to_idx = {raw: idx for idx, raw in enumerate(user_ids)}
    item_to_idx = {raw: idx for idx, raw in enumerate(item_ids)}

    # 같은 pair의 여러 positive event는 이 예시에서 합한다. 실제 상한·감쇠는
    # event 계약으로 별도 결정한다.
    rows, cols, values = [], [], []
    for interaction in interactions:
        confidence = EVENT_CONFIDENCE.get(interaction.event)
        if confidence is None:
            continue
        rows.append(user_to_idx[interaction.requester_user_id])
        cols.append(item_to_idx[interaction.personal_agent_id])
        values.append(confidence)

    matrix = coo_matrix(
        (np.asarray(values, dtype=np.float32), (rows, cols)),
        shape=(len(user_ids), len(item_ids)),
    ).tocsr()
    matrix.sum_duplicates()
    return matrix, user_ids, item_ids
```

Alice가 Bob agent를 선택하고 대화까지 시작했다면 같은 cell은 `3.0`이 된다. 이 합산은 예시이지 자동으로
옳은 의미가 아니다. `card_selected`가 `conversation_started`의 전제라면 둘을 더하는 것이 같은 funnel을
이중 보상할 수 있다. `max(event confidence)` 또는 event별 별도 실험이 더 맞을 수 있다.

### 2.2 public/friends/private가 행렬에 들어가는가

행렬은 “행동이 있었다”를 기록한다. interest visibility 자체를 cell로 만들지 않는다.

```text
public coffee 보유     ≠ Bob agent와 상호작용
friends coffee 보유    ≠ Alice가 Bob을 선택
private coffee 보유    ≠ 학습용 positive
```

과거 상호작용에 private topic이 원인이었는지 추론하여 행렬에서 제거하는 것도 보통 불가능하다. 따라서 source
event의 수집 목적·retention을 별도로 승인하고, online에서는 현재 visibility로 후보를 다시 gate한다. 과거에
볼 수 있었던 candidate가 지금도 볼 수 있다는 뜻은 아니다.

## 3. 출력과 요청별 후보

```python
ids, scores = model.recommend(
    userid=0,
    user_items=user_items[0],
    N=10,
    filter_already_liked_items=True,
)
```

출력은 integer item ID와 score 배열이다. ID map으로 personal agent ID를 복원한다. `items=`로 점수화할
후보 subset을 제한할 수 있다.

```python
ids, scores = model.recommend(
    user_idx,
    user_items[user_idx],
    N=max_results,
    items=eligible_candidate_indices,
)
```

우리 online path는 discovery/gate가 허용한 작은 후보만 넘긴다. 전체 카탈로그 추천과 요청별 topic
rerank를 섞지 않는 핵심 이음매다.

예를 들어 현재 request에서 gate를 통과한 후보가 Bob과 Carol뿐이면 다음과 같이 ID를 투영한다.

```python
eligible_raw_ids = ("agent-bob", "agent-carol")
eligible_indices = np.asarray(
    [item_to_idx[agent_id] for agent_id in eligible_raw_ids if agent_id in item_to_idx],
    dtype=np.int32,
)

ids, scores = model.recommend(
    userid=user_to_idx["alice"],
    user_items=user_items[user_to_idx["alice"]],
    N=min(10, len(eligible_indices)),
    items=eligible_indices,
    filter_already_liked_items=False,
)
```

`filter_already_liked_items`는 제품 의미로 결정한다. “이미 대화한 agent를 다시 보여주지 않는다”가 계약이면
`True`, 재방문이 유효하면 `False`다. 라이브러리 기본값에 맡길 문제가 아니다.

## 4. 역할, topic, bio

```text
matrix row    = requester_user_id
matrix column = personal_agent_id(owner_user_id에서 유도)
```

같은 사람이어도 row/column map은 별도고 self-exclusion은 후보 생성 전에 적용한다.

`implicit`은 user bio, item topic tag, 언어, traits, friendship graph를 직접 받지 않는다. feature를 가짜
interaction으로 만들지 않는다.

```text
잘못된 예: coffee interest 보유
          → 모든 coffee agent와 상호작용했다고 행 생성
```

이는 실제 행동과 content prior를 섞고 평가가 자기 입력을 재발견하게 한다. late fusion을 쓴다.

```text
score = w_topic   × grounded topic relevance
      + w_persona × role-compatible trait score
      + w_engage  × implicit model score
```

첫날 `w_engage`는 부재/0이고 interaction이 쌓인 뒤 실험으로 비중을 정한다.

## 5. visibility와 개인정보

```text
topic-api/discovery
  → public + requester가 볼 수 있는 friends holdings
  → private/self/safety 제외
  → eligible candidate IDs
  → implicit.recommend(items=eligible IDs)
```

interaction matrix 자체도 민감하다. artifact를 외부 API로 직접 노출하지 않고 serving process가 로컬 파일로
읽는다. 다음을 함께 둔다.

- model artifact와 ID map 접근 통제
- 삭제 요청 시 source snapshot과 다음 재학습에서 제거
- API/log에 latent factor와 raw score detail 비노출
- friends 관계를 attribution으로 암시하지 않음
- private topic을 interaction side feature로 합성하지 않음

### 5-1 제외와 후보 pool 지원 범위

네 도구 중 `implicit`이 이 요구를 가장 직접적으로 지원한다. 공용 `recommend()`에 제외와 포함 양쪽 인자가
있다. [Recommender API](https://benfred.github.io/implicit/api/models/recommender_base.html)

| 인자 | 의미 |
|---|---|
| `filter_already_liked_items=True` | 전달한 `user_items`에 이미 있는 item 제외 |
| `filter_items=[...]` | 지정한 item ID를 결과에서 추가 제외 |
| `items=[...]` | 지정한 item ID만 점수화하는 allowlist |

`items`와 `filter_items`는 동시에 사용할 수 없다. 우리 request path에서는 denylist보다 **gate가 만든
allowlist를 `items`로 넘기는 방식**이 더 안전하다.

```python
eligible_indices = np.asarray(
    [
        item_to_idx[candidate.personal_agent_id]
        for candidate in candidates
        if candidate.is_visible_to(requester_user_id)
        and not candidate.is_requester
        and not candidate.is_blocked
        and candidate.personal_agent_id in item_to_idx
    ],
    dtype=np.int32,
)

ids, scores = model.recommend(
    userid=user_idx,
    user_items=user_items[user_idx],
    N=min(max_results, len(eligible_indices)),
    items=eligible_indices,
    filter_already_liked_items=False,
)
```

allowlist가 유리한 이유는 새 제외 규칙이 생겼을 때다.

```text
denylist 방식
  전체 model catalogue - 우리가 기억한 금지 목록
  → 새 금지 규칙을 빼먹으면 candidate가 통과

allowlist 방식
  이번 요청에서 모든 gate를 통과한 candidate만 전달
  → 모르는 candidate는 기본적으로 들어오지 않음
```

`filter_already_liked_items`는 privacy 기능이 아니다. 학습 행렬에 nonzero였던 item을 제거할 뿐이다. 이미
대화한 agent와의 재방문이 제품상 유효하면 `False`여야 하고, 재추천 금지가 계약이면 `True` 또는 별도
event-based gate를 쓴다.

`filter_items`는 batch의 모든 사용자에게 같은 추가 제외 목록을 적용하는 데 적합하다. 전역 삭제된 agent나
법적 차단 목록에 쓸 수 있지만, requester마다 다른 friends/block 권한에는 `items` allowlist가 더 명확하다.

```text
grounded candidates
  → requester-aware visibility/safety/self gate
  → model에 알려진 ID만 items=로 전달
  → implicit이 그 pool 안에서 top-N 계산
  → model에 없는 신규 agent는 규칙 점수/exploration으로 합류
```

빈 `eligible_indices`에서 전체 catalogue 추천으로 fallback하지 않는다. 이 빈 값은 “모델 후보가 없다”가
아니라 “현재 요청에서 허용된 known candidate가 없다”는 뜻일 수 있다. 전체 호출은 privacy gate를 우회한다.

contract test는 최소한 다음을 고정한다.

1. `items`에 없는 agent는 결과에 절대 나오지 않는다.
2. blocked/friends-ineligible/self candidate는 `items` 생성 전에 빠진다.
3. allowlist가 비면 model을 호출하지 않는다.
4. unknown 신규 agent는 제거가 아니라 규칙 기반 ordering으로 남는다.
5. `items` 제한을 없애는 mutation이 privacy 테스트에서 실패한다.

### 5-2 확장성: 전체 사용자 pool 1억

`implicit`은 sparse matrix, native multi-thread 구현, ALS/BPR의 GPU 지원과 일부 ANN integration을 제공한다.
[공식 문서](https://benfred.github.io/implicit/) 그러나 기본 artifact는 여전히 user factors와 item factors를
가진다. library가 빠르다는 사실과 1억×1억 ID 공간을 한 node에 올릴 수 있다는 주장은 다르다.

factor 64, `float32`의 배열 하한은 다음과 같다.

```text
100M user factors = 25.6 GB
100M item factors = 25.6 GB
factor arrays only = 51.2 GB
```

평균 interaction 20개면 `nnz=20억`이고 CSR value `float32` + column index `int32`만 약 16 GB다. row pointer,
ID map, 학습 temporary, model copy, serving worker별 복제는 별도다. API worker가 artifact를 하나씩 load하면
factor 51.2 GB가 worker 수만큼 반복될 수 있다.

따라서 기본 설계는 등록 user 1억 전부가 아니라 active sparse cohort다.

```text
registered users 100M
  → train window 안 positive behavior가 있는 U_active
candidate agents up to 100M
  → 현재 추천 가능 + 최소 interaction이 있는 I_model
  → ALS/item-item artifact

cold/inactive IDs
  → topic/content rule + exploration
```

예를 들어 active requester 1천만, model-known agent 5백만, factor 64면 factor 배열 하한은 약 3.84 GB다.
이 정도부터 실제 hardware에서 CSR·working memory를 포함한 peak RSS와 train 시간을 측정한다.

online 확장성은 `items=` allowlist 덕분에 training 규모와 분리할 수 있다. 전체 item factor가 크더라도 요청에서
100~1,000개 index만 점수화한다면 전역 1억 dot product를 피한다. 반대로 `items`를 빼고 1억 전체에서 top-N을
찾는 경로는 ANN 없이는 요청 비용이 너무 크고, ANN을 써도 requester별 privacy를 별도로 재검사해야 한다.

#### implicit 샤딩 전략

`implicit`을 사용할 때는 학습 전 데이터, 학습된 factor serving, 학습 알고리즘을 별도로 본다.

```text
event/aggregation shards   가능
factor serving shards      가능하나 custom serving 필요
ALS/BPR training shards    library가 투명하게 제공하지 않음
```

##### 1. event와 CSR 준비

원본 event는 `hash(requester_user_id)`로 partition하면 한 requester의 history를 같은 reducer에서 집계하기
쉽다. 최종 CSR row index와 item index는 하나의 versioned global map으로 확정한다.

```text
event partitions
  → requester별 dedupe/confidence/decay
  → global user/item ID-map version V
  → row-block CSR files
```

row-block CSR을 만드는 것은 가능하지만 `model.fit()`에 block을 하나씩 독립 전달해 model을 합치면 안 된다.
각 block model은 다른 latent 좌표계를 학습한다.

##### 2. factor serving

하나의 전역 학습이 만든 factor를 ID hash 또는 연속 row range로 나눌 수 있다.

```text
model version V
  user-factor shard  = hash(requester_user_id) % S_u
  item-factor shard  = hash(personal_agent_id) % S_i

request
  1. user factor home shard에서 U[u] 조회
  2. eligible candidate IDs를 item shard별 batch
  3. 각 shard가 U[u] · V[i] 계산 또는 factor 반환
  4. 같은 version V의 partial 결과를 merge/top-K
```

request pool이 100~1,000이면 item factor를 batch fetch해 한 process에서 dot product하는 방식도 충분할 수 있다.
전체 catalogue ANN/top-K를 shard별로 만들 필요가 없다.

이 구성을 쓰면 `implicit.model.recommend(items=...)`를 그대로 호출하는 것이 아니라 학습된 factor를 읽는
별도 scorer가 될 수 있다. 즉 library API의 편리함을 일부 포기하므로 다음 contract가 필요하다.

- custom dot product가 원래 `recommend(items=...)`와 fixture에서 같은 순서를 낸다.
- user/item shard 모두 같은 model version과 factor dimension을 쓴다.
- rollout 중 V와 V+1 factor를 한 요청에서 섞지 않는다.
- shard timeout은 score 0이 아니다. model signal absent 또는 명시적 실패다.
- 재샤딩 중 dual-read가 candidate를 중복/누락하지 않는다.

##### 3. training

`implicit`의 CPU multi-thread/GPU 지원은 한 학습 실행을 빠르게 하지만, 여러 machine의 independent ALS
model을 하나로 합치는 분산 계약은 아니다. 올바른 distributed ALS는 item factor를 고정해 user block을
갱신하고, 갱신된 user factor로 item block을 다시 갱신하는 전역 iteration/barrier가 필요하다.

단일 고메모리 node/GPU에서 active cohort가 더 이상 맞지 않으면 다음을 비교한다.

1. 검증된 distributed ALS 구현으로 trainer만 교체하고 serving factor 계약을 유지한다.
2. active window, factor 수와 model-known item 조건을 줄인다.
3. collaborative model은 head/active cohort에만 적용하고 tail은 content rule로 둔다.
4. tenant·region이 실제 독립일 때만 separate model을 운영한다.

user hash별 독립 `implicit` model은 기본안이 아니다. 같은 candidate의 factor와 score가 shard마다 달라지고,
cross-shard user behavior를 비교할 수 없기 때문이다.

단계별 capacity gate:

1. active U/I/nnz를 매 train snapshot에서 기록한다.
2. 1%→10%→목표 active 규모로 peak RSS, iterations/sec, artifact size를 잰다.
3. model load와 atomic swap 동안 old+new artifact 두 벌이 공존하는 memory를 포함한다.
4. worker별 복제를 포함한 pod 총 memory를 계산한다.
5. candidate pool 10/100/1,000에서 p95/p99 latency를 측정한다.
6. single-node 예산을 넘으면 user/item sharding을 이 library 주위에 즉흥적으로 만들지 않는다. distributed ALS,
   vector store 또는 managed platform을 새로운 후보로 비교한다.

`partial_fit_users/items`는 일부 갱신을 줄일 수 있지만 신규 ID map, deletion과 factor 전체 배포 문제를
자동으로 해결하지 않는다. freshness 요구가 실제로 batch retrain 주기를 넘을 때만 검토한다.

## 6. 시스템 배치

현재 설계의 “모델은 서비스가 아니라 파일”과 잘 맞는다.

```text
CronJob
  exposure + feedback partitions
    → shared aggregation
    → CSR matrix + ID maps
    → ALS/BPR fit
    → versioned artifact

Serving
  artifact load
    → gate-approved candidate subset
    → model score
    → weighted ordering
```

artifact bundle은 `model.npz`, `user_ids.json`, `item_ids.json`, `metadata.json`으로 구성할 수 있다.
metadata에는 model/feature/event schema version, train window, ID map digest, visibility projection, metrics를
둔다. 초기 규모에는 incremental update보다 재현 가능한 batch retraining을 우선한다.

`implicit`도 Gorse와 달리 daemon이 아니다. 아래 운영 부품을 library 바깥에 만들어야 한다.

| 부품 | 책임 |
|---|---|
| event aggregator | source event dedupe, confidence, decay, deletion 반영 |
| ID-map builder | deterministic raw↔integer mapping과 digest |
| trainer | CSR 생성, fit, offline metric, artifact 작성 |
| artifact publisher | staging/validation/atomic promotion/rollback |
| serving scorer | artifact load, eligible subset score, cold fallback |
| monitoring | model version, known-ID 비율, score coverage, latency |

### 6.1 학습·저장 예시

```python
from implicit.als import AlternatingLeastSquares


model = AlternatingLeastSquares(
    factors=64,
    regularization=0.05,
    iterations=30,
    random_state=42,
)
model.fit(user_items)
model.save("artifacts/implicit/2026-08-28.1/model.npz")
```

공식 base API는 `save(fileobj_or_path)`와 `load(fileobj_or_path)`를 제공한다.
[Recommender API](https://benfred.github.io/implicit/api/models/recommender_base.html) model 파일만으로 raw ID를
복구할 수 없으므로 ID map과 metadata를 같은 version directory에 원자적으로 승격한다.

```text
artifacts/implicit/2026-08-28.1/
├── model.npz
├── user_ids.json
├── item_ids.json
├── metadata.json
└── READY
```

```json
{
  "artifact_version": "2026-08-28.1",
  "algorithm": "als",
  "matrix_shape": [18204, 7311],
  "matrix_nnz": 249802,
  "event_schema": 4,
  "train_until": "2026-08-27T23:59:59Z",
  "user_map_sha256": "…",
  "item_map_sha256": "…"
}
```

### 6.2 in-process scorer 예시

```python
from dataclasses import dataclass

import numpy as np
from implicit.als import AlternatingLeastSquares


@dataclass(frozen=True, slots=True)
class CollaborativeSignal:
    personal_agent_id: str
    score: float


class ImplicitScorer:
    def __init__(self, bundle) -> None:
        self._model = AlternatingLeastSquares.load(bundle.model_path)
        self._user_to_idx = bundle.user_to_idx
        self._item_to_idx = bundle.item_to_idx
        self._item_ids = bundle.item_ids
        self._user_items = bundle.user_items

    def score(self, *, requester_user_id: str, eligible_agent_ids: tuple[str, ...]):
        user_idx = self._user_to_idx.get(requester_user_id)
        if user_idx is None:
            return None  # cold requester: 규칙 기반 ordering으로 열화

        candidate_indices = np.asarray(
            [
                self._item_to_idx[agent_id]
                for agent_id in eligible_agent_ids
                if agent_id in self._item_to_idx
            ],
            dtype=np.int32,
        )
        if candidate_indices.size == 0:
            return ()

        ids, scores = self._model.recommend(
            user_idx,
            self._user_items[user_idx],
            N=len(candidate_indices),
            items=candidate_indices,
            filter_already_liked_items=False,
        )
        return tuple(
            CollaborativeSignal(self._item_ids[item_idx], float(score))
            for item_idx, score in zip(ids, scores, strict=True)
        )
```

후보 중 model에 없는 신규 agent는 결과에서 빠진다. 호출자는 이를 낮은 점수로 읽지 않고 content/topic
ordering에 남겨 exploration 기회를 줄 수 있다. 반환된 점수는 모델 버전 안에서만 비교하며 wire에는 싣지
않는다.

### 6.3 프로세스와 갱신 방식

factor matrix는 각 API worker가 하나씩 읽으면 worker 수만큼 메모리를 쓴다. artifact 크기와 worker 수를
곱해 pod memory limit을 계산한다. 모델이 커지면 다음 선택지를 별도 비교한다.

1. discovery worker마다 in-process load: 가장 단순하고 네트워크 장애가 없다.
2. node-local/shared scorer process: 메모리를 공유하지만 RPC 계약과 새 장애면이 생긴다.
3. 전용 recommendation service: 독립 scaling이 가능하지만 사실상 Gorse와 유사한 운영 제품을 우리가
   만드는 선택이다.

초기에는 1번으로 시작하고 artifact load 후 health-check가 끝난 객체를 atomic swap한다. ALS는
`partial_fit_users`/`partial_fit_items`를 제공하지만, ID map·삭제·event projection까지 원자적으로 맞추기
어렵다. [ALS API](https://benfred.github.io/implicit/api/models/cpu/als.html) 충분한 freshness 요구가 관측되기
전에는 전체 batch 재학습이 더 재현 가능하다.

## 7. 모델 선택

- **ALS**: confidence-weighted positive matrix의 첫 baseline. 관측되지 않은 값을 다루는 가정과 exposure
  편향을 함께 검토한다.
- **BPR**: pairwise ordering에 가깝지만 negative sampling에서 미노출 agent를 negative로 뽑지 않게 한다.
- **item-item BM25/TF-IDF**: “함께 사용된 agent” baseline으로 설명하기 쉽지만 cold requester fallback이
  필요하다.

첫 PoC는 ALS와 item-item 하나면 충분하다.

## 8. PoC와 판정

1. exposure가 있는 pair만 평가 negative 후보로 쓸 수 있게 한다.
2. 시간 분할하고 마지막 resolved/select event를 test로 둔다.
3. 현재 topic ordering, item-item, ALS를 같은 request candidate set에서 비교한다.
4. cold requester/agent/저활동 user를 별도 stratum으로 본다.
5. popularity concentration과 신규 agent coverage를 함께 잰다.
6. artifact 없음, unknown ID, ID-map mismatch에서 규칙 기반으로 열화한다.
7. `items=` 제한을 제거하는 mutation이 privacy-ineligible candidate test에서 잡히게 한다.

interaction positive와 exposure 로그가 충분하고 작은 artifact가 안정적인 개인화 이득을 내면 채택한다.
matrix가 비어 있거나 exposure가 없어 negative sampling을 정직하게 할 수 없으면 library를 미리 배선하지
않고 event/log 계약부터 만든다.

## 9. 실패와 열화 계약

| 상태 | 동작 | 잘못된 대체 |
|---|---|---|
| artifact 없음/검증 실패 | topic·trait 기반 ordering | 빈 model을 정상 model로 표시 |
| requester가 ID map에 없음 | cold-start ordering | 임의 user factor/0점 |
| candidate가 ID map에 없음 | content score + exploration 유지 | candidate 삭제 |
| map digest와 model 불일치 | artifact 교체 거절 | integer ID를 그대로 신뢰 |
| eligible subset이 비었음 | upstream empty reason 유지 | 전체 item recommend 호출 |

특히 마지막 fallback은 금지한다. `items=`가 빈 이유가 privacy gate라면 전체 추천 호출은 정확히 금지된
candidate를 되살린다.

## 10. 평가 예시

공식 evaluation 모듈은 train/test split과 precision@K, MAP@K, NDCG@K, AUC를 제공한다.
[Evaluation API](https://benfred.github.io/implicit/api/evaluation.html) 무작위 leave-k-out은 시간·노출 편향을
자동으로 해결하지 않는다. 우리 평가 dataset은 request 당시 eligible candidate set을 보존해야 한다.

```text
train: 2026-05-01 .. 2026-07-31
test:  각 requester의 8월 첫 resolved/select event
candidate set: 그 request 시각에 실제 노출 가능했던 agents
```

다음 slice를 별도로 낸다.

- warm requester / cold requester
- warm agent / 신규 agent
- public-only / friends candidate가 섞인 request
- interaction 밀도와 언어
- head topic / tail topic

offline 이득만으로 weight를 올리지 않는다. 노출 로그가 없는 데이터에서는 “선택되지 않은 item”이 실제로
보였는지 알 수 없으므로 counterfactual 비교가 아니다. 이 한계를 metric 옆에 기록한다.
