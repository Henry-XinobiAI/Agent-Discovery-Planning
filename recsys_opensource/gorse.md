# Gorse 활용 검토

> **결론**: Gorse는 추천 운영 서비스를 가장 빨리 얻는 선택이다. public-only 개인화 baseline에는 잘
> 맞지만 requester-dependent friends/private gate, 표면별 점수식, 풍부한 노출 로그를 그대로 맡길 수는
> 없다. 포크보다 후보·행동 신호 공급자로 제한하는 하이브리드를 먼저 검증한다.

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
