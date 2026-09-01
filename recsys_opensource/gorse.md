# Gorse 활용 검토

> **결론**: Gorse는 추천 운영 서비스를 가장 빨리 얻는 선택이다. public-only 개인화 baseline에는 잘
> 맞지만 requester-dependent friends/private gate, surface-aware ranker, propensity 노출 로그를 그대로 맡길 수는
> 없다. 포크보다 후보·행동 신호 공급자로 제한하는 하이브리드를 먼저 검증한다.
>
> **역할**: 이 문서는 [`recommendation_scoring_design.md` §9-2](../recommendation_scoring_design.md)의
> Gorse 판정 근거다. 제품 요구사항이나 도입 결정을 여기서 새로 만들지 않는다.
>
> **§1–§10은 `문서` 근거, §11은 `실측`이다.** §11이 앞 절의 서술 다섯 개를 뒤집거나 넓히므로,
> §6-1·§6-2·§9를 읽을 때 §11을 같이 본다.

## 1. 성격과 실행 구조

Gorse는 Go로 작성된 Apache-2.0 오픈소스 추천 엔진이다. user/item/feedback를 적재하면 master·worker·
server가 모델 학습, 사용자별 offline recommendation, cache, REST serving을 나눠 맡는다. 여러
recommender의 후보를 합치고 ranker가 점수화해 cache에 쓰며, server가 read item을 필터하고 fallback을
채운다. [공식 저장소](https://github.com/gorse-io/gorse),
[pipeline](https://gorse.io/docs/concepts/pipeline)

```text
our services → Gorse REST/data store
                    ├─ master: config/model
                    ├─ worker: offline candidate/ranking
                    └─ server: recommend API/cache filtering
```

라이브러리가 아니라 별도 운영 컴포넌트라는 점이 다른 세 후보와 가장 큰 차이다.

## 2. 입력

공식 데이터 모델은 User, Item, Feedback 세 컬렉션이다.
[Data Source](https://gorse.io/docs/concepts/data-source)

### User = 추천받는 requester

```json
{
  "UserId": "user-a",
  "Labels": {
    "seeks_topics": ["topic:coffee", "topic:photography"],
    "preferred_languages": ["ko"],
    "preferred_styles": ["concise"],
    "profile_embedding": [0.12, -0.07, 0.31],
    "feature_version": "v1"
  },
  "Comment": "dashboard용 식별 설명"
}
```

`Labels`는 임의 JSON이지만 저장한 모든 값이 자동으로 학습되는 것은 아니다. recommender의 type/column이
읽을 field를 정한다. `Comment`는 dashboard용이지 자유 텍스트 의미 모델의 자동 입력이 아니다.

### Item = 추천되는 personal agent

```json
{
  "ItemId": "agent-b",
  "IsHidden": false,
  "Categories": ["personal-agent"],
  "Timestamp": "2026-08-28T12:00:00Z",
  "Labels": {
    "public_topics": ["topic:coffee", "topic:drip-coffee"],
    "provided_languages": ["ko", "en"],
    "provided_styles": ["detailed"]
  },
  "Comment": "dashboard용 agent 설명"
}
```

현실에서 owner가 User와 같아도 ID namespace와 feature projection은 분리한다.

### Feedback = requester-agent 행동

```json
{
  "FeedbackType": "conversation_started",
  "UserId": "user-a",
  "ItemId": "agent-b",
  "Value": 1,
  "Timestamp": "2026-08-28T12:03:00Z"
}
```

positive/read/negative feedback type은 설정한다. request ID, surface, position, propensity, candidate causes는
별도 exposure stream에 보존한다. Gorse feedback은 원본 사건이 아니라 학습 projection이다.

### 이번 요청 topic은 User label이나 Feedback이 아니다

A의 Gorse User labels가 영화·위스키라고 해도 이번 `topic=coffee` 요청 때문에 labels를 갱신하지 않는다.

```text
기존 Gorse User
  Labels.seeks_topics = [movie, whisky]

이번 discovery request
  topic = coffee
  context = 집에서 드립 커피를 시작하고 싶다
```

Gorse의 표준 recommendation endpoint는 이 자연어 query를 직접 받지 않는다. 따라서 discovery가 커피
후보를 만들고 Gorse의 장기 개인화 결과와 교차하거나, 안정적인 category가 있으면 `category=coffee`를
사용한다. 어느 경우에도 요청 한 건을 다음 update로 바꾸지 않는다.

```json
{
  "UserId": "user-a",
  "Labels": {
    "seeks_topics": ["topic:movie", "topic:whisky", "topic:coffee"]
  }
}
```

위 갱신은 사용자가 profile에서 커피를 명시적으로 추가했을 때만 가능하다.

또한 추천 요청이나 결과 생성 자체를 positive Gorse Feedback으로 쓰지 않는다.

```text
recommend requested     → Gorse positive feedback 아님
result generated        → 실제 노출인지 아직 모름
card exposed            → read/exposure 원본 기록; 제품 정의가 같을 때 Gorse read projection
card selected/talked    → 정의된 positive projection 후보
```

`write-back-type`은 API가 반환한 결과를 편의상 read로 기록할 수 있지만, 실제 화면에 렌더되기 전에 이탈할 수
있다. 평가 정확도가 필요하면 frontend가 실제 노출을 확인한 뒤 원본 exposure를 쓰고, 거기서 Gorse read
feedback을 파생한다.

정리하면 query topic은 **후보 제약**, Gorse User labels는 **장기 profile projection**, Feedback은 **실제
후속 행동 projection**이다. 세 입력의 writer와 갱신 시점을 분리한다.

## 3. 출력

```http
GET /api/recommend/user-a?n=3
```

```json
["agent-b", "agent-c", "agent-d"]
```

일부 세부 API는 `[{"Id": ..., "Score": ...}]`도 반환한다. 최종 agent 카드는 우리 서비스가 hydrate하고
discovery 근거를 결합한다. [REST API](https://gorse.io/docs/api/restful-api)

표준 사용자 추천 요청은 `user-id`, `n`, `offset`, `category` 정도를 받고 우리의 `topic`·자연어 `context`를
받지 않는다. 따라서 Gorse의 기본 함수는 “이 사용자가 평소 좋아할 agent”이고, 현재 discovery의 함수는
“이 사용자의 이번 topic/context에 맞는 agent”다. Gorse를 직접 대체재로 놓지 않고 discovery가 만든
request candidate를 보강하거나, 홈/탐색 surface의 일반 개인화에 쓰는 이유다.

## 4. user-to-user와 역할 분리

Gorse는 tag, embedding, 공통 favorite item 기반 user-to-user recommender를 제공한다. tag 방식은 흔한
tag의 IDF를 낮춘 overlap cosine이다. [User-to-User](https://gorse.io/docs/concepts/recommenders/user-to-user)

public topic 기반 유사 사용자 보조 후보에는 쓸 수 있지만 주 모델에는 맞지 않는다.

- query-side private interest는 소유자 개인화에만 쓸 수 있다.
- candidate-side private interest는 타인 대상 추천에 쓸 수 없다.
- friends interest는 requester-owner 관계에 따라 달라진다.
- Gorse의 한 User vector와 offline cache는 이 비대칭을 표현하지 못한다.

따라서 주 표현은 `User=requester`, `Item=personal_agent`로 둔다.

## 5. bio·traits

tag는 namespace를 붙인다.

```json
{"match_tags": ["topic:coffee", "language:ko", "style:concise", "role:mentor"]}
```

공통 tag는 유사성을 나타낼 뿐 `seeks:beginner ↔ provides:expert` 같은 상보성을 자동으로 표현하지 않는다.
원문 bio는 외부 producer가 embedding으로 만들 수 있지만 embedding도 개인정보 projection이다. 모델·feature
version, 삭제·재학습 정책이 필요하다.

## 6. visibility와 확장점

```text
Gorse Item labels = public projection only
friends topic     = 관계 확인 후 external source에서 후보 추가
private topic     = candidate 학습·cache에서 제외
final gate        = discovery가 소유
```

External Recommender는 JavaScript에서 외부 HTTP endpoint를 호출해 item ID 배열을 후보로 넣는다. 공식
문서도 production business logic을 엔진 하나가 모두 포괄할 수 없어 이 확장점을 둔다고 설명한다.
[External API Recommenders](https://gorse.io/docs/concepts/recommenders/external)

friends 후보를 여기서 공급할 수는 있지만 requester 인증, 관계 확인, cache key, timeout/fail-closed,
public 후보와의 merge, attribution은 우리 책임이다.

### 6-1 제외와 후보 pool 지원 범위

Gorse는 몇 가지 필터를 자체 지원하지만, 표준 추천 API가 임의의 requester별 candidate ID 집합을 받아 그
안에서만 점수화하는 형태는 아니다.

| 요구 | Gorse 기본 지원 | 범위 |
|---|---|---|
| 모든 사용자에게서 item 제거 | `IsHidden=true` | 전역 제외. 삭제·판매 중단·법적 차단에 적합 |
| category 안에서 추천 | `GET /api/recommend/{user-id}?category=...` | item의 `Categories`를 이용한 coarse filter |
| 이미 읽은 item 제외 | read feedback와 관련 설정 | Gorse가 알고 있는 read 이력 기준 |
| 추천 결과를 read로 기록 | `write-back-type`, `write-back-delay` | 편의 기능. 실제 노출과 다를 수 있음 |
| 요청별 arbitrary allowlist | 표준 endpoint에 없음 | 외부에서 교집합하거나 별도 integration 필요 |
| 요청별 arbitrary denylist | 표준 endpoint에 없음 | 외부에서 제거해야 함 |

> ⚠ **§11-1 M1·M2가 이 표의 다섯째 행을 넓힌다.** 표준 endpoint에 인자가 없는 것은 맞지만,
> **더미 topic item의 이웃을 묻는 경로로 topic별 후보 검색이 된다**(숨긴 item도 동작). 다만
> **질의와 태그 집합이 같은 후보가 제외되는 미문서화 동작**이 있어 질의를 라벨 단위로 쪼개야 한다.

[공식 data model](https://gorse.io/docs/concepts/data-source)에 따르면 `IsHidden=true`는 즉시 추천에서
제외되고, 다시 `false`로 돌린 item은 refresh 주기를 거쳐 복귀한다.

```json
{
  "ItemId": "agent-deleted",
  "IsHidden": true,
  "Categories": ["personal-agent"],
  "Labels": {}
}
```

requester마다 달라지는 차단이나 `friends` 권한에 `IsHidden`을 쓰면 안 된다. 한 사람에게 숨기기 위해 모든
사람에게 item이 사라지기 때문이다. category도 `coffee`, `ko`, `personal-agent` 같은 비교적 안정적인
분류에는 쓸 수 있지만 `friends-of-alice` 같은 동적 권한 집합을 category로 만들면 관계 수만큼 category와
cache invalidation이 생긴다.

#### 우리 요청에서의 권장 흐름

```text
Gorse recommendation IDs (coarse category, 충분히 overfetch)
            ∩
topic grounding이 만든 후보
            ∩
requester-aware visibility/safety/self gate
            ↓
허용된 결과만 현재 ordering에 사용
```

```python
gorse_ids = await gorse.recommend(
    requester_user_id,
    category="personal-agent",
    limit=overfetch_limit,
)
eligible_ids = {
    candidate.personal_agent_id
    for candidate in discovery_candidates
    if candidate.is_visible_to(requester_user_id)
}
usable_ids = [agent_id for agent_id in gorse_ids if agent_id in eligible_ids]
```

이 방식은 결과 노출을 fail-closed로 막지만 단점이 있다. Gorse 상위 N이 모두 gate에서 떨어지면 뒤에 있던
허용 후보를 알 수 없고, overfetch를 늘려도 충분한 결과를 보장하지 못한다. 즉 Gorse는 이 구성에서 exact
candidate-pool reranker라기보다 **general recommendation source**다.

Gorse의 external recommender로 우리 endpoint에서 candidate ID를 공급할 수는 있다. 그러나 이것은 표준
recommend 호출에 매 요청 allowlist를 직접 넘기는 것과 같지 않다. 동기 HTTP 의존성과 script 계약이
생기므로 별도 PoC에서 latency·실패·권한 freshness를 검증한다.

#### 결론

- 전역 삭제/차단은 `IsHidden`으로 Gorse에도 동기화한다.
- 안정적인 coarse 분류는 category filter를 사용할 수 있다.
- read 제외는 제품의 “이미 봄” 정의와 Gorse feedback 정의가 같을 때만 사용한다.
- requester별 visibility, block list, 현재 topic 후보 pool은 우리 gate가 소유한다.
- exact allowlist 안에서만 모델 점수를 얻는 것이 핵심 요구라면 Gorse 표준 API보다 `implicit.items`나
  Cornac `rank(item_indices=...)`가 직접적이다.

### 6-2 확장성: 전체 사용자 pool 1억

> ⚠ **재계산 비용과 신선도 실측은 §11-4다.** `≈10 ms/item`(2,000개까지 선형)이고,
> 이웃 갱신 주기는 `[recommend] cache_expire`(기본 `72h`)가 지배한다.

Gorse는 master·worker·server로 분리된 cluster 구성을 제공한다. 공식 문서상 server는 stateless하게 수평
확장해 online throughput을 늘리고, worker를 늘려 offline recommendation 처리를 분담한다.
[Pipeline](https://gorse.io/docs/concepts/pipeline), [Docker deployment](https://gorse.io/docs/deploy/docker)

그러나 이 사실만으로 1억 사용자 적합성이 증명되지는 않는다. 기본 pipeline은 worker가 모든 사용자의
offline recommendation을 만들어 cache database에 저장한다.

```text
100,000,000 users × cached top 100 = 10,000,000,000 recommendation entries
```

entry당 ID와 score를 16 bytes로만 가정해도 160 GB의 payload 하한이다. 실제 DB row/key/index/replication
overhead와 fallback·neighbor·ranker cache는 포함하지 않은 값이다. cache K가 500이면 entry 수는 500억으로
늘어난다.

1억 규모 PoC는 다음을 분리해 측정한다.

| 축 | 측정할 값 |
|---|---|
| data store | user/item/feedback row 수, ingest throughput, index 크기 |
| offline workers | 전체 refresh wall time, worker 증가에 따른 scaling efficiency |
| cache store | user당 K, 총 entry/bytes, replication, eviction, stale ratio |
| servers | QPS, p95/p99 latency, fallback 비율 |
| freshness | feedback→추천 반영 시간, hidden item 제거 시간 |
| operations | master 병목, DB backup/restore, rolling upgrade |

server와 worker가 수평 확장되어도 data store, cache store와 master의 실제 병목은 별도다. 공식 배포 문서가
1억 user benchmark를 보장한다고 읽지 않는다.

우리 시스템에서는 모든 등록 사용자를 Gorse User로 즉시 넣지 않는 선택도 비교한다.

```text
registered 100M
  → 최근 active/requested users만 Gorse User projection
  → 추천 가능한 active personal agents만 Item projection
  → 장기 inactive 사용자는 Gorse 밖 cold-start 규칙
```

다만 lazy projection은 첫 요청 latency, 삭제 동기화, 과거 feedback 복원이라는 비용을 만든다. full projection,
active-window projection, on-demand projection을 각각 1%→10%→목표 규모로 부하 시험한다.

#### Gorse 샤딩 전략

Gorse에서는 먼저 공식 cluster의 역할 분리를 사용한다.

```text
API traffic       → 여러 stateless gorse-server
offline user jobs → 여러 gorse-worker
metadata/model    → gorse-master
source rows       → data store
recommend caches  → cache store
```

이는 application-level에서 user를 독립 Gorse model로 나누는 것과 다르다. data/cache sharding과 replication은
선택한 MySQL/PostgreSQL/MongoDB/ClickHouse/Redis 계열 backend의 기능과 실제 Gorse access pattern에 맞춰
설계한다. 특히 cache key는 user 중심이므로 `hash(user_id)` 분산이 자연스럽지만, backend가 지원한다고 해서
Gorse query·refresh가 선형 확장된다고 가정하지 않고 부하 시험한다.

| 대상 | 권장 전략 | 주의 |
|---|---|---|
| ingestion | user/feedback batch를 hash partition 후 병렬 API/bulk sync | 같은 event의 중복·순서 보존 |
| server | stateless replica 수평 확장 | cache/backend connection 한계 |
| worker | offline job worker 추가 | master·DB/cache 병목과 refresh tail |
| cache store | user-key 기반 backend partition/cluster 검토 | user당 K와 hot-user skew |
| item catalogue | 전역 일관성 유지 | `IsHidden`과 삭제가 모든 worker/server에 같은 의미여야 함 |

다음 방식은 기본안으로 삼지 않는다.

```text
hash(user_id) % N
  → 서로 독립된 Gorse cluster N개
```

이렇게 하면 item catalogue와 model을 N번 복제하고, user 간 collaborative signal을 shard 경계에서 잃는다.
재샤딩 시 user history와 cache도 함께 이동해야 한다. tenant·법적 region처럼 shard 사이 추천과 학습이 실제로
금지된 경우에만 독립 cluster가 자연스럽다.

topic별 Gorse cluster도 같은 문제가 있다. 한 user와 agent가 여러 topic에 걸치므로 feedback이 중복되고 최종
점수를 직접 비교하기 어렵다. topic은 현재 discovery retrieval index의 shard key로 사용할 수 있지만 Gorse
model shard key로 자동 승격하지 않는다.

1억 PoC의 통과 조건은 server/worker replica를 늘렸을 때뿐 아니라 다음을 함께 만족하는 것이다.

1. 같은 model/config version이 모든 worker와 server에서 관측된다.
2. `IsHidden`과 삭제가 shard/cache 전체에 정해진 시간 안에 반영된다.
3. worker 추가가 전체 refresh p95를 실제로 낮춘다.
4. backend shard 장애가 허용되지 않은 item을 fallback으로 되살리지 않는다.
5. 독립 cluster가 필요해질 경우 cross-cluster recommendation이 없다는 제품 경계가 먼저 존재한다.

Gorse의 장점은 이 규모에서 우리가 직접 scheduler/cache/API를 만들 필요를 줄일 가능성이다. 반대로 exact
request pool을 직접 받지 않으므로 cache된 상위 결과와 현재 gate의 교집합에서 recall이 얼마나 떨어지는지도
함께 측정해야 한다. 운영 확장성만 좋고 허용 후보를 충분히 반환하지 못하면 현재 제품에는 맞지 않는다.

## 7. 최소 실행 예제

아래는 API 모양을 보여주는 예시다. 실제 endpoint port와 API key는 배포 설정을 따른다.

### 7-1 requester 등록

```bash
curl -X POST http://gorse-server:8087/api/user \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: ***' \
  -d '{
    "UserId": "user-a",
    "Labels": {
      "seeks_topics": ["topic:coffee"],
      "preferred_languages": ["ko"],
      "preferred_styles": ["concise"]
    },
    "Comment": ""
  }'
```

### 7-2 personal agent 등록

```bash
curl -X POST http://gorse-server:8087/api/item \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: ***' \
  -d '{
    "ItemId": "agent-b",
    "IsHidden": false,
    "Categories": ["personal-agent"],
    "Timestamp": "2026-08-28T12:00:00Z",
    "Labels": {
      "public_topics": ["topic:coffee", "topic:espresso"],
      "provided_languages": ["ko", "en"]
    },
    "Comment": ""
  }'
```

여기 넣는 것은 source of truth가 아니라 재생성 가능한 projection이다. topic visibility가 바뀌거나 agent가
비활성화되면 sync worker가 Item을 갱신한다.

### 7-3 행동 적재

```bash
curl -X POST http://gorse-server:8087/api/feedback \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: ***' \
  -d '[{
    "FeedbackType": "conversation_started",
    "UserId": "user-a",
    "ItemId": "agent-b",
    "Value": 1,
    "Timestamp": "2026-08-28T12:03:00Z"
  }]'
```

`POST`는 같은 `(user,item,type)`의 Value를 누적하고 `PUT`은 덮어쓴다. 따라서 raw event를 무조건 POST하면
“사건 수”가 되는 반면, 최신 집계 confidence를 보내려면 PUT projection이 더 맞을 수 있다. 둘 중 무엇인지
event contract에서 먼저 정한다.

### 7-4 추천 읽기와 hydrate

```bash
curl 'http://gorse-server:8087/api/recommend/user-a?n=20' \
  -H 'X-API-Key: ***'
```

```python
gorse_ids = await gorse.recommend(requester_user_id, limit=20)
topic_candidates = await discovery.ground_and_retrieve(topic, context)

eligible = gate(
    union(gorse_ids, topic_candidates),
    requester=requester_user_id,
    friendships=friendships,
)
ordered = score(eligible, surface="topic_search")
return assemble(ordered[:max_results])
```

Gorse가 반환한 ID가 삭제·숨김·권한 변경으로 stale할 수 있으므로 hydrate 실패를 upstream 계약 위반으로
오귀속하지 않고 stale candidate로 계측해 제거한다.

### 7-5 설정의 의미

실제 설정은 현재 버전 template에서 시작한다. 개념적으로는 다음을 결정한다.

```toml
[recommend.data_source]
positive_feedback_types = ["conversation_started", "resolved"]
read_feedback_types = ["exposed"]
negative_feedback_types = ["not_interested"]

[[recommend.user-to-user]]
name = "shared_public_topics"
type = "tags"
column = "user.Labels.public_topics"

[recommend.ranker]
type = "fm"
```

이 예시는 우리 결정값이 아니다. `conversation_started`가 항상 positive인지, `resolved`를 누가 생산하는지,
read가 노출과 같은지부터 측정해야 한다. Gorse는 이 이름의 의미를 대신 정해 주지 않는다.

## 8. 데이터 동기화와 운영 구성

### 8-1 필요한 adapter

```text
catalogue projection worker
  bourbon user/agent/topic changes
    → public-only Gorse User/Item upsert
    → hidden/deleted item 반영

feedback projection worker
  append-only product events
    → idempotency/aggregation
    → Gorse Feedback POST 또는 PUT

online client
  timeout/retry/circuit breaker
    → recommendation IDs
    → stale ID filtering
```

Gorse DB를 product source of truth로 만들지 않는다. projection worker를 다시 실행해 재구축할 수 있어야 한다.

### 8-2 cache와 privacy

공식 pipeline은 user neighbors, item neighbors, non-personalized 결과, ranker output을 주기적으로 cache한다.
따라서 다음 변경은 즉시 모든 결과에 반영된다고 가정하지 않는다.

- public → private 전환
- friendship 해제
- owner/agent 삭제
- safety/maturity 상태 변경

권한 철회는 추천 품질 freshness가 아니라 보안 freshness다. Gorse cache TTL을 기다리지 않고 online gate가
source of truth에서 다시 확인해야 한다. friends-only feature를 Gorse의 전역 cached Item에 넣지 않는
이유도 같다.

### 8-3 장애 경계

| 장애 | 권장 동작 |
|---|---|
| Gorse timeout/unavailable | 현재 topic/RRF ordering으로 계속, personalization absent 계측 |
| feedback sync 실패 | durable retry; 추천 요청은 실패시키지 않음 |
| catalogue sync 지연 | online gate/hydration이 stale ID 제거 |
| unknown requester | public/content fallback, 가짜 평균 user로 기록하지 않음 |
| cache/model 갱신 중 | 응답마다 Gorse pipeline/model 식별자를 얻을 수 있는지 PoC에서 확인 |

Gorse API 인증은 network/service credential이고 requester authorization을 대신하지 않는다. requester ID를
호출자가 임의로 바꿀 수 없는 내부 경계에서만 호출한다.

## 9. 시스템 배치안

### A. Gorse가 전체 추천 API

가장 빠르지만 topic grounding, requester-aware gate, 표면별 가중치, attribution과 exposure schema를 크게
재작성한다. 범용 홈 피드이고 정책이 단순할 때만 적합하다.

> ⚠ **이 기각은 질의가 있는 표면을 전제로 한 것이다.** 질의 없는 표면(사용자 활동 기반 추천)에는
> A안이 그대로 맞는다 — 거기서는 topic grounding도 표면별 질의도 없다. 남는 전제는
> [`README.md` §3 R1](README.md)(그 표면이 `friends` 보유까지 근거로 삼는가) 하나다.

### B. Gorse 후보 + 우리 gate/rerank — 우선 PoC

```text
Gorse public/behavior candidates ┐
topic-api topic candidates        ├→ gate → our score → response/log
friends external candidates      ┘
```

### C. core fork

가능하지만 요청별 scenario score가 offline cache와 맞지 않으면 config, serialization, worker, server, cache,
dashboard까지 변경된다. 포크가 작고 upstream 가능하며 Go owner가 있을 때만 선택한다.

## 10. PoC와 판정

1. public topics와 최소 interaction만 적재한다.
2. 같은 discovery candidate set에서 Gorse score를 보조 키로 적용한다.
3. cold user/agent, sparse feedback, cache staleness를 측정한다.
4. 친구가 아닌 requester에게 friends-only topic이 영향 주지 않는 leakage test를 둔다.
5. Gorse unavailable 시 기존 ordering으로 열화한다.
6. 운영비와 품질이 로컬 artifact 방식보다 나은지 비교한다.

현재 공식 문서에서 dashboard의 pipeline 편집·모니터링·데이터 관리는 확인되지만, 실험군 배정부터
노출·전환 분석까지 갖춘 일반적인 A/B 플랫폼 계약은 확인하지 못했다. A/B를 도입 근거로 삼기 전에 현재
버전에서 따로 검증한다.

---

## 11. `실측` v0.5.11 컨테이너 검증 (2026-09-01)

§1–§10은 공식 문서·저장소 근거다. 이 절은 `zhenghaoz/gorse-in-one` v0.5.11을 실제로 실행해 확인한
것이고, **앞 절의 서술 다섯 개를 뒤집거나 넓힌다.** fixture는 합성 6~19 item이므로 **기능 유무와 방향
확인까지만 유효하고 품질 주장이 아니다.**

설정: `[[recommend.item-to-item]] type="tags", column="item.Labels.topics"` 를 추가하고,
playground 없이 `/etc/gorse/config.toml` 을 주입해 실행.

### 11-1 문서 서술이 뒤집힌 것

| # | 앞 절 서술 | 실측 |
|---|---|---|
| M1 | §6-1 "요청별 arbitrary allowlist — 표준 endpoint에 없음" | **더미 topic item을 만들어 그 이웃을 물으면 topic별 후보 검색이 된다.** `IsHidden=true`인 item도 이웃이 계산·서빙된다(숨긴 것과 보이는 대조군의 결과가 완전히 동일) |
| M2 | (서술 없음) | **질의 item과 태그 집합이 완전히 같은 후보는 이웃에서 제외된다.** 공식 문서에 없고 사양서로 예측 불가이며, topic 검색 용도에서는 "그 주제만 파는 전문가가 탈락"으로 나타난다 |
| M3 | §8-2 "cache TTL을 기다리지 않고 online gate가 재확인" | 맞지만 원인이 달랐다. **이웃 갱신 주기를 지배하는 것은 `[recommend] cache_expire`이고 기본값이 `72h`다.** 파이프라인이 60초마다 돌아도 이 값 전에는 기존 item의 이웃이 재계산되지 않는다 |
| M4 | (서술 없음) | 전면 재계산 비용 **≈10 ms/item**, 2,000개까지 선형. 상위 라벨을 다수가 공유하는 계층 편중이 비용을 키우지 않았다 |
| M5 | §7 "실제 endpoint port와 API key는 배포 설정을 따른다" | `--playground`는 **재시작마다 설정 파일을 재생성하고 데이터를 재임포트한다.** 설정을 바꾸려면 playground 없이 띄우고 config를 주입해야 한다 |

### 11-2 세 경로의 실제 결과

**경로 A — `?category=<topic>`** (agent `Categories`에 보유 topic id를 넣음)

후보 집합은 **정확히** 좁혀진다. 그러나 순서가 인기도다.

```text
gen  = 6개 주제 보유, 피드백 12건
dave = drip 전담,     피드백 0건

?category=drip  →  gen  dave  carol      ← 전담 전문가가 2등
```

**경로 B — 더미 topic item에 하위 라벨을 전부 실은 결합 질의**

```text
질의 = coffee + drip + espresso + roasting + latte
   generalist 0.507  partial 0.505  narrow 0.501  parentonly 0.501
   ⚠ broad (상위+하위 전부 보유 = 찾으려던 사람) 결과에 없음    ← M2
```

M2와 길이 정규화가 동시에 터진다. **질의 태그를 늘릴수록 정답이 제외될 확률이 올라간다.**

**경로 C — 라벨별 개별 질의 + 가중 합산** (성립하는 형태)

M2가 두 가지로 해소된다.

| 질의 | 센티넬 없음 | 센티넬 있음 |
|---|---|---|
| 상위 라벨 | 상위만 보유한 agent **누락** | 누락 없음 |
| 하위 라벨 | 누락 없음 | 누락 없음 |

- **하위 라벨 질의는 원래 안 터진다** — 하위 보유가 상위 보유를 함의하는 데이터에서는 하위 보유자의
  태그 집합이 단일 라벨 질의와 같아질 수 없다.
- **상위 라벨 질의는 센티넬 태그 하나로 막힌다** — 어떤 agent도 갖지 않는 태그(`__QUERY__`)를 질의
  item에 넣는다. 어떤 후보와도 매칭되지 않아 분자 기여가 0이고, 분모는 후보별 상수라 순서에 영향이 없다.

라벨별 원점수는 `매칭 여부 × 1/‖d‖` 구조다(0.5 초과분 ×10⁻³):

| | coffee | drip | espresso | roasting | latte |
|---|---|---|---|---|---|
| broad (5개) | 0.606 | 0.693 | 0.789 | 0.898 | 0.898 |
| partial (3개) | 0.843 | 0.964 | 1.098 | — | — |
| narrow (2개) | 1.081 | 1.236 | — | — | — |
| parentonly (1개) | **1.601** | — | — | — | — |
| generalist (12개) | 0.302 | 0.345 | 0.393 | 0.448 | 0.448 |

**한 라벨만 보면 항상 보유 폭이 좁은 쪽이 높다.** 변별은 *몇 개 라벨에서 매칭되는가*에서 나오므로
합산해야 의미가 생긴다. 가중치별 결과:

| 가중 | 결과 |
|---|---|
| 균등 (상위1·하위1×4) | **broad 3.88** > partial 2.90 > narrow 2.32 > generalist 1.94 > parentonly 1.60 |
| 하위 강조 (상위1·하위3) | broad 10.44 > partial 7.03 > **generalist 5.21** > narrow 4.79 |
| 상위 강조 (상위4·하위1) | **parentonly 6.40** > broad 5.70 > narrow 5.56 > partial 5.43 |
| 좁은 질의 (coffee1·drip5) | **narrow 7.26** > partial 5.66 > broad 4.07 > generalist 2.03 |

★ **상위 라벨은 랭킹 신호가 아니라 recall 장치다.** 하위가 상위를 함의하면 subtree 안 모두가 상위
라벨을 가지므로 IDF가 낮아 변별력이 없고, 남는 것은 `1/‖d‖`뿐이라 "보유가 적은 사람"을 고르게 된다.
상위 질의는 후보를 긁어오는 데 쓰고 랭킹 가중은 하위에 준다.

마지막 행이 **질의 구체성이 보존된다**는 증거다 — 좁은 질의에서 좁고 깊은 전문가가 1등이 된다.

오버헤드는 호출당 **약 1.1 ms**(순차 10회 10.7 ms). 확장이 라벨 10개를 내도 문제없다.

### 11-3 이 형태로도 못 하는 것

| | 실측 |
|---|---|
| **보유 강도/깊이** | 세 인코딩 전부 실패. 객체 `{"topics":{"coffee":5}}`는 저장되지만 태그로 읽히지 않음 · 반복 `["coffee"×5]`는 `["coffee"]`와 **점수 동일** · 별도 태그 `tea@L5`는 **역방향**(깊이 태그 없는 쪽이 위. 순서가 깊이가 아니라 태그 희소성의 부산물) |
| **focus** | "그 사람 보유 전체 중 이 subtree 비중"을 주지 않는다. 하위 강조 시 generalist가 narrow를 앞지르는 원인 |
| 미보유자 혼입 | 이웃 결과에 매칭 0인 후보가 기본값으로 섞인다 |
| `POST /api/session/recommend` | 이 빌드에서 **모든 조합에 200 + `null`**. 숨긴/보이는 더미 topic, 일반 item, 복수 item, feedback type 변경 전부 |

`판단` 앞의 둘은 애초에 rerank에서 소유하기로 한 것이므로 Gorse 쪽 미해결 제약은 아니다.

### 11-4 신선도 (M3 상세)

| 시도 | 결과 |
|---|---|
| 신규 item 삽입 후 파이프라인 6회 실행 대기(340s) | 기존 item의 이웃에 **등장하지 않음** |
| 질의 item을 다시 POST 해서 touch | **갱신되지 않음** |
| 컨테이너 재시작 | 전면 재계산. 전부 등장 |
| `cache_expire = "2m"` | **120.2초 만에 반영** |

```text
반영 지연 = max( cache_expire, 전면 재계산 시간 )
전면 재계산 ≈ 10 ms × 전체 item 수      (증분 갱신 없음)
```

| 태그 분포 | 21 | 500 | 2,000 |
|---|---|---|---|
| 희소 (토픽 2,000개 중 2~8개) | 1.7s | 6.1s | 20.2s |
| 계층 편중 (상위 1개 + 하위 1~4개) | 1.7s | 5.5s | 20.7s |

`열린 항목` **2,000개 너머는 미검증.** 흔한 태그 하나 안에서 보유자 수에 이차적일 수 있고, 이 실험은
상위 라벨당 보유자 250명까지만 갔다.

`판단` **신선도는 채택 결정 요인이 아니라 운영 파라미터다.** 단, 차단·삭제·자격 상실은 여기 의존하지
않고 서빙 시점에 원본으로 재확인한다(§8-2).

### 11-5 부수 확인

- `?user-id=<id>` 파라미터는 **그 사용자가 이력을 가진 후보를 결과에서 제외한다**(실측: alice가
  `talked`한 bob·carol이 사라짐). 합성 피드백으로 self-exclusion을 넣을 여지가 있다.
- `[[recommend.item-to-item]]`은 **배열**이라 이름별로 여러 개를 정의할 수 있다. `tags`/`embedding`/`users` 세 type.
- 태그가 완전히 같은 item 두 개는 **접히지 않는다.** 둘 다 색인에 남고 각각 조회된다.

★ **규율: 문서에 없는 동작은 문서가 아니라 실행이 답한다.** M2·M3은 서술 자체가 없었고 둘 다 채택
판단을 바꾸는 크기였다.

★ **규율: 같은 증상에 두 원인 후보가 있으면 값싼 쪽(캐시)을 먼저 배제한다.** 신규 item이 안 보이는
것을 알고리즘 성질(중복 태그 접힘)로 추정했으나 틀렸고 원인은 M3이었다. 알고리즘이면 설계를 바꾸게
되고 캐시면 설정값 하나를 바꾼다.
