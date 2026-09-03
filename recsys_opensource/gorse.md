# Gorse 활용 검토

> **결론**: **채택했다**(`decisions.md` `D06`). surface 2는 Gorse가 하는 일 그 자체이므로 통째로 쓰고,
> surface 1에서는 **후보 생성기**로 쓴다(`D07`) — 더미 topic item의 이웃을 라벨별로 물어 가중합하는
> 경로가 실제로 동작한다(§11-2). requester-dependent friends/private gate, surface-aware ranker,
> propensity 노출 로그는 **계속 우리 것**이고, 그 경계가
> [`README.md` §9](README.md)의 "도구와 무관하게 우리가 계속 소유할 것" 표다.
>
> **역할**: 조사 자료. 결정은 [`decisions.md`](../decisions.md)가 소유한다.
>
> **§1–§10은 `문서` 근거, §11은 `실측`이다.** rev 2(2026-09-03)에서 **§11이 뒤집은 자리는 앞 절
> 본문을 고쳐 썼다** — 이전 판은 경고만 달고 옛 서술을 남겨 두었고, 그 방식이 §6-1에서 실제로
> 오독을 만들었다(`decisions.md` 규칙 ②). §11-1의 M 표는 "문서에 없는 동작은 실행이 답한다"는
> 교훈으로 남긴다.

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

Gorse의 표준 recommendation endpoint는 이 자연어 query를 직접 받지 않는다. **그러나 쿼리를 받을 수
있는 경로가 따로 있다** — 확정 topic을 더미 item으로 두고 그 이웃을 라벨별로 물어 가중합하면
topic별 후보 검색이 된다(§11-2 경로 C, `D07`). `?category=`는 후보 집합은 정확히 좁히지만 **순서가
인기도**라 쓰지 않는다(§11-2 경로 A).

어느 경우에도 요청 한 건을 다음 update로 바꾸지 않는다.

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

표준 사용자 추천 요청(`GET /api/recommend/{user-id}`)은 `user-id`·`n`·`offset`·`category`를 받고
자연어 `context`를 받지 않는다. 그 함수는 "이 사용자가 평소 좋아할 agent"이고, **surface 2가 정확히 그
질문**이므로 여기서는 통째로 쓴다(`D06`).

surface 1의 질문("이번 topic/context에 맞는 agent")은 이 endpoint가 아니라 **item-to-item 이웃 쿼리**로
답한다(§11-2 경로 C). 두 surface가 Gorse의 서로 다른 경로를 쓰고, **surface 1의 경로는 feedback을 읽지
않는다**([`feedback_semantics.md` §1-3](feedback_semantics.md)).

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

표준 추천 API는 임의의 requester별 candidate ID 집합을 받아 그 안에서만 점수화하지 않는다. 그러나
**topic별 후보 검색은 다른 경로로 된다**(§11-2 경로 C).

| 요구 | 실제 동작 | 우리 쪽 결론 |
|---|---|---|
| 모든 사용자에게서 item 제거 | `IsHidden=true` | 전역 제외에 쓴다. **단 이웃 쿼리 경로에서는 숨긴 item의 이웃도 계산·서빙된다**(§11-1 M1) — 쿼리용 더미 item을 숨겨 두는 데 쓸 수 있다는 뜻이고, **가림막으로 믿으면 안 된다는 뜻이기도 하다** |
| topic별 후보 검색 | **더미 topic item + 라벨별 이웃 쿼리 + 가중합** | `D07`의 경로. `?category=`는 후보를 정확히 좁히지만 **순서가 인기도**라 쓰지 않는다(§11-2 A) |
| 이미 본 사람 제외 | **feedback row가 하나라도 있으면 타입 불문 영구 제외** | 우리 요구와 **정면 충돌**한다. `enable_replacement`가 유일한 레버이고 쿨다운은 우리 것이다([`feedback_semantics.md` §2](feedback_semantics.md) · `D18`) |
| 추천 결과를 read로 기록 | `write-back-type` — **반환한 모든 item에 row를 쓴다** | **쓰지 않는다.** 실제 렌더와 다를 수 있는 데다 위 행 때문에 부작용이 크다(`feedback_semantics.md` §2-6) |
| 요청별 arbitrary allowlist·denylist | 표준 endpoint에 없음 | 우리 gate가 소유한다 |

[공식 data model](https://gorse.io/docs/concepts/data-source)은 `IsHidden=true`가 즉시 추천에서
제외되고 `false`로 되돌린 item은 refresh 주기를 거쳐 복귀한다고 적는다. **이웃 쿼리 경로는 예외라는
것이 §11-1 M1이다.**

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

#### 우리 요청에서의 흐름 (rev 2 — `D07`)

```text
확정 topic (grounding)
   ↓
라벨별 개별 쿼리 + 가중합        Gorse item-to-item, tags       ← 후보를 만드는 곳
   ↓
미보유자 필터                    우리 복제본으로 판정 (D08·D10)
   ↓
requester-aware visibility/safety/self gate
   ↓
정렬
   ↓
최종 N명 hydrate + 재확인        topic-api /users/{id}/topics (D11·D21)
```

★ **rev 1의 흐름은 `Gorse ∩ topic grounding 후보`였고 삭제했다.** 교집합은 topic-api가 이미 준
사람만 남기므로 그들 랭킹의 상위 100명 컷을 그대로 물려받는다 — 그러면 Gorse를 쓰는 이유가
없어진다. 뒤집힌 경위는 [`decisions.md` §2](../decisions.md).

**Gorse의 external recommender**로 우리 endpoint에서 candidate ID를 공급하는 길도 있지만 채택하지
않았다. 동기 HTTP 의존성과 script 계약이 생기고, `D07`의 경로가 그것 없이 성립한다.

#### 결론

- 전역 삭제/차단은 `IsHidden`으로 동기화하되 **이웃 쿼리 경로에서는 가림막이 아니다**(M1).
- **requester별 visibility, block list, 재추천 정책, 최종 자격 판정은 우리 gate가 소유한다.**
- 후보 pool은 Gorse가 만들고 **증명은 우리 복제본이 한다**(`D08`) — 근거 topic을 붙일 수 없는
  후보는 응답 자체를 만들 수 없기 때문이다(§11-3).

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

entry당 ID와 score를 16 bytes로 가정하면 160 GB의 payload 하한이다. **그 가정은 정수 ID의 것이고 우리 `ItemId`는 UUID라 실제로는 560 GB, 복제본까지 1.1 TB다** — 계산과 backend별 비용은 [`storage_sizing.md` §2](storage_sizing.md)가 소유한다. 실제 DB row/key/index/replication
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
request pool을 직접 받지 않으므로 cache된 상위 결과와 현재 gate를 함께 걸었을 때 recall이 얼마나 떨어지는지도
함께 측정해야 한다. 운영 확장성만 좋고 허용 후보를 충분히 반환하지 못하면 현재 제품에는 맞지 않는다.

## 7. 최소 실행 예제

아래는 API 모양을 보여주는 예시다. 실제 endpoint port와 API key는 배포 설정을 따른다.

> ⚠ **`--playground`로 띄우면 재시작마다 설정 파일이 재생성되고 데이터가 재임포트된다**(§11-1 M5).
> 설정을 바꾸려면 playground 없이 띄우고 config를 주입해야 한다.

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

위는 **surface 2**의 호출이다. surface 1은 §11-2 경로 C(라벨별 이웃 쿼리)를 쓴다.

```python
# surface 1
topics = await ground(topic, context)                    # topic-api /search/topics
candidates = await gorse.neighbors_weighted(topics)      # 라벨별 쿼리 + 가중합
held = filter_by_mirror(candidates, topics)              # 미보유자 제거 (D08·D10)
eligible = gate(held, requester=requester_user_id)
ordered = rank(eligible)                                 # 자르지 않는다
return await hydrate_and_verify(ordered, max_results)    # D11·D21 — 여기서 자른다
```

`hydrate_and_verify`가 `D11`(복제본이 못 주는 다섯 값)과 `D21`(차단·삭제·철회 재확인)을 **한 번의
왕복으로** 처리한다. 읽지 못한 후보는 stale로 계측해 제거하고 뒤에서 채운다 — upstream 계약 위반으로
오귀속하지 않는다. **rev 1의 `union(gorse_ids, topic_candidates)`는 삭제했다**(`D07` — 합집합이 아니라
surface마다 단일 소스다).

### 7-5 설정의 의미

실제 설정은 현재 버전 template에서 시작한다. 개념적으로는 다음을 결정한다.

```toml
[server]
auto_insert_user = false          # D16 — 켜 두면 우리 카탈로그 경계를 Gorse가 넘는다
auto_insert_item = false

[recommend.data_source]
positive_feedback_types = ["conversation_started", "depth_reached>=N"]
read_feedback_types     = ["exposed"]
negative_feedback_types = []      # C10 미결 — 영구 제외라 정할 때까지 비운다

[recommend.replacement]
enable_replacement = true         # D18 — 제품 요구가 강제한다
positive_replacement_decay = 0.8
read_replacement_decay     = 0.6

[[recommend.item-to-item]]        # surface 1의 경로 (§11-2 C)
name   = "topic_neighbors"
type   = "tags"
column = "item.Labels.topics"

[recommend.ranker]
type = "fm"                       # replacement가 이것을 요구한다
```

**값은 우리 결정이 아니지만 모양은 결정이다**(rev 2). `conversation_started`가 항상 positive인지,
`resolved`를 누가 생산하는지, `N`이 얼마인지는 측정 대상이다. 반면 위 네 블록의 **존재**는
`D16`·`D18`과 `D07`이 정했다(negative는 `C10`으로 미결) — rev 1의 예시는 `[[recommend.user-to-user]] type="tags"`를
보여줬는데 실제로 동작하는 경로는 `item-to-item`이고, `[recommend.replacement]`가 아예 없었으며,
`negative_feedback_types = ["not_interested"]`는 그 쌍을 영구히 죽이는 값이었다.

> **[`feedback_semantics.md`](feedback_semantics.md)가 여기서부터를 이어받는다.** v0.5.11 소스에서
> 확인한 것 셋만 미리 적으면: 버킷은 이름 목록이 아니라 `read>=3` 같은 **식**이고, `read`는 제외가
> 아니라 학습에서 **`-1`**이며, **어떤 타입이든 feedback row가 하나 있으면 그 item은 그 사용자의
> 추천에서 영구히 빠진다**(`enable_replacement`가 유일한 레버). 마지막 항목은 "써 본 상대도 다시
> 추천된다"는 우리 요구와 정면으로 충돌하므로 채택 전에 닫아야 한다.

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
| Gorse timeout/unavailable | **surface 1: topic-api 보유자 랭킹으로 후보 생성 + `candidates_fallback` 선언**(`D20`). rev 1의 "현재 ordering으로 계속"은 `D07` 이후 성립하지 않는다 — 잃는 것이 개인화가 아니라 후보 자체다. **surface 2: surface가 없다** |
| feedback sync 실패 | durable retry; 추천 요청은 실패시키지 않음 |
| catalogue sync 지연 | online gate/hydration이 stale ID 제거 |
| unknown requester | public/content fallback, 가짜 평균 user로 기록하지 않음 |
| cache/model 갱신 중 | 응답마다 Gorse pipeline/model 식별자를 얻을 수 있는지 PoC에서 확인 |

Gorse API 인증은 network/service credential이고 requester authorization을 대신하지 않는다. requester ID를
호출자가 임의로 바꿀 수 없는 내부 경계에서만 호출한다.

## 9. 시스템 배치안

### A. Gorse가 전체 추천 API

가장 빠르지만 topic grounding, requester-aware gate, surface별 가중치, attribution과 exposure schema를 크게
재작성한다. 범용 홈 피드이고 정책이 단순할 때만 적합하다.

> ⚠ **이 기각은 쿼리가 있는 surface를 전제로 한 것이다.** 쿼리 없는 surface(사용자 활동 기반 추천)에는
> A안이 그대로 맞는다 — 거기서는 topic grounding도 surface별 쿼리도 없다. 남는 전제는
> [`README.md` §13 `SURV-R1`](README.md)(그 surface가 `friends` 보유까지 근거로 삼는가) 하나다.

### B. Gorse 후보 + 우리 gate/rerank — **채택**(`D06`·`D07`)

```text
surface 1   확정 topic → Gorse 라벨별 쿼리 + 가중합 ─┐
                                                  ├→ 미보유자 필터 → gate → 정렬 → hydrate → 응답
surface 2   requester id → Gorse /api/recommend ─────┘
                                                     └ surface 2는 근거 topic이 없어 응답 형태가 다르다 (D02)
```

rev 1의 세 갈래(`Gorse public/behavior` + `topic-api topic` + `friends external`)는 삭제했다 —
합집합이 아니라 **surface마다 단일 소스**이고, 그래서 합집합 규칙(SCORE-Q5)이 닫혔다.

### C. core fork

가능하지만 요청별 scenario score가 offline cache와 맞지 않으면 config, serialization, worker, server, cache,
dashboard까지 변경된다. 포크가 작고 upstream 가능하며 Go owner가 있을 때만 선택한다.

## 10. PoC와 판정

채택은 끝났고(`D06`) 남은 것은 **배포 전 게이트**다.

1. **`SURV-R4` — 실제 보유 데이터에서 §11-2 경로 C의 품질.** 지금 근거는 합성 6명 fixture에서 확인한
   *메커니즘*뿐인데 `D07`이 후보 생성 전체를 여기 맡긴다. **이것이 최우선이다.**
2. public topics와 최소 interaction만 적재한다.
3. cold user/agent, sparse feedback, cache staleness를 측정한다(§11-4).
4. 친구가 아닌 requester에게 friends-only topic이 영향 주지 않는 leakage test를 둔다.
5. **Gorse unavailable 시 `candidates_fallback`으로 열화한다**(`D20`) — 기존 ordering이 아니라
   기존 *후보 생성*으로 돌아가는 것이다.
6. **`FBK-F5` — config 핫리로드 여부.** 버킷 변경이 재시작을 요구하는지 미확인이다.

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
| M2 | (서술 없음) | **쿼리 item과 태그 집합이 완전히 같은 후보는 이웃에서 제외된다.** 공식 문서에 없고 사양서로 예측 불가이며, topic 검색 용도에서는 "그 주제만 파는 전문가가 탈락"으로 나타난다 |
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

**경로 B — 더미 topic item에 하위 라벨을 전부 실은 결합 쿼리**

```text
쿼리 = coffee + drip + espresso + roasting + latte
   generalist 0.507  partial 0.505  narrow 0.501  parentonly 0.501
   ⚠ broad (상위+하위 전부 보유 = 찾으려던 사람) 결과에 없음    ← M2
```

M2와 길이 정규화가 동시에 터진다. **쿼리 태그를 늘릴수록 정답이 제외될 확률이 올라간다.**

**경로 C — 라벨별 개별 쿼리 + 가중 합산** (성립하는 형태)

M2가 두 가지로 해소된다.

| 쿼리 | 센티넬 없음 | 센티넬 있음 |
|---|---|---|
| 상위 라벨 | 상위만 보유한 agent **누락** | 누락 없음 |
| 하위 라벨 | 누락 없음 | 누락 없음 |

- **하위 라벨 쿼리는 원래 안 터진다** — 하위 보유가 상위 보유를 함의하는 데이터에서는 하위 보유자의
  태그 집합이 단일 라벨 쿼리와 같아질 수 없다.
- **상위 라벨 쿼리는 센티넬 태그 하나로 막힌다** — 어떤 agent도 갖지 않는 태그(`__QUERY__`)를 쿼리
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
| 좁은 쿼리 (coffee1·drip5) | **narrow 7.26** > partial 5.66 > broad 4.07 > generalist 2.03 |

★ **상위 라벨은 랭킹 신호가 아니라 recall 장치다.** 하위가 상위를 함의하면 subtree 안 모두가 상위
라벨을 가지므로 IDF가 낮아 변별력이 없고, 남는 것은 `1/‖d‖`뿐이라 "보유가 적은 사람"을 고르게 된다.
상위 쿼리는 후보를 긁어오는 데 쓰고 랭킹 가중은 하위에 준다.

마지막 행이 **쿼리 구체성이 보존된다**는 증거다 — 좁은 쿼리에서 좁고 깊은 전문가가 1등이 된다.

오버헤드는 호출당 **약 1.1 ms**(순차 10회 10.7 ms). 확장이 라벨 10개를 내도 문제없다.

### 11-3 이 형태로도 못 하는 것

| | 실측 |
|---|---|
| **보유 강도/깊이** | 세 인코딩 전부 실패. 객체 `{"topics":{"coffee":5}}`는 저장되지만 태그로 읽히지 않음 · 반복 `["coffee"×5]`는 `["coffee"]`와 **점수 동일** · 별도 태그 `tea@L5`는 **역방향**(깊이 태그 없는 쪽이 위. 순서가 깊이가 아니라 태그 희소성의 부산물) |
| **focus** | "그 사람 보유 전체 중 이 subtree 비중"을 주지 않는다. 하위 강조 시 generalist가 narrow를 앞지르는 원인 |
| 미보유자 혼입 | 이웃 결과에 매칭 0인 후보가 기본값으로 섞인다 |
| `POST /api/session/recommend` | 이 빌드에서 **모든 조합에 200 + `null`**. 숨긴/보이는 더미 topic, 일반 item, 복수 item, feedback type 변경 전부 |

`판단` 앞의 둘은 애초에 rerank에서 소유하기로 한 것이므로 Gorse 쪽 미해결 제약은 아니다.

`판단` **셋째 행만 성격이 다르다 — 미보유자 혼입은 품질 문제가 아니라 계약 문제다.** 우리 응답은
추천마다 "어느 topic 때문인가"를 **필수로** 요구한다(`agent_discovery/domain/recommendation.py`의
`Recommendation.representative`는 옵셔널이 아니다). 쿼리 topic을 실제로 보유하지 않은 후보에는 붙일
이유가 없으므로 **응답을 만들 수조차 없다.**

따라서 미보유자 필터는 켜고 끄는 품질 옵션이 아니라 **surface 1에서 Gorse가 후보를 *추가*할 수 있게
하는 전제**다. 없으면 교집합(topic-api가 이미 준 사람만)으로 후퇴해야 하고, 그러면 Gorse는
재정렬기이지 후보 생성기가 아니다.

★ **판정은 Gorse 점수가 아니라 우리 복제본으로 한다**(`D08`·`D10`). §11-2의 원점수는 `매칭 여부 × 1/‖d‖` 구조라
임계값이 후보의 보유 폭에 따라 움직인다. 대신 [`inbound_event_contract.md`
§3-2](../inbound_event_contract.md)가 이미 받기로 한 `public_topics`의 **`topic_id` 목록을 우리
store에 함께 두면 로컬 집합 연산**이 되고 왕복이 0이다.

거르고 나면 attribution이 이만큼 나온다:

| 필드 | 출처 |
|---|---|
| `topic_id` | 쿼리를 우리가 구성했으므로 어느 라벨에서 매칭됐는지 안다 |
| `labels` | 카탈로그 — grounding에서 이미 읽었다 |
| `distance` | 쿼리 topic과 매칭 topic의 계층 관계 |
| `owner_notes` | **없다** — topic-api의 보유자 응답에만 있다 |

`owner_notes`는 빈 값이 허용되므로 응답 자체는 만들어지지만, **Gorse가 데려온 사람만 본인 문장 없이
렌더되는 비대칭**이 생긴다. `GET /users/{user_id}/topics`로 메울 수 있고(코드에 이미 있다) 후보 수만큼
왕복이 늘어난다 — 지연 예산이 선행 조건이 된다.

`열린 항목` **필터의 위치.** Gorse 응답 직후인가, 우리 gate와 같은 자리인가. 앞이면 뒤따르는 왕복이
줄고, 뒤면 제외 카운트가 한 곳에 모인다.

### 11-4 신선도 (M3 상세)

| 시도 | 결과 |
|---|---|
| 신규 item 삽입 후 파이프라인 6회 실행 대기(340s) | 기존 item의 이웃에 **등장하지 않음** |
| 쿼리 item을 다시 POST 해서 touch | **갱신되지 않음** |
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
- 태그가 완전히 같은 item 두 개는 **접히지 않는다.** 둘 다 인덱스에 남고 각각 조회된다.

★ **규율: 문서에 없는 동작은 문서가 아니라 실행이 답한다.** M2·M3은 서술 자체가 없었고 둘 다 채택
판단을 바꾸는 크기였다.

★ **규율: 같은 증상에 두 원인 후보가 있으면 값싼 쪽(캐시)을 먼저 배제한다.** 신규 item이 안 보이는
것을 알고리즘 성질(중복 태그 접힘)로 추정했으나 틀렸고 원인은 M3이었다. 알고리즘이면 설계를 바꾸게
되고 캐시면 설정값 하나를 바꾼다.
