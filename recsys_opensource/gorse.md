# Gorse 활용 검토

> **결론**: **채택했다**(`decisions.md` `D06`). surface 2는 Gorse가 하는 일 그 자체이므로 통째로 쓰고,
> surface 1에서는 **후보 생성기**로 쓴다(`D07`) — 더미 topic item의 이웃을 라벨별로 물어 가중합하는
> 경로가 실제로 동작한다(§11-2). requester-dependent friends/private gate, surface-aware ranker,
> propensity 노출 로그는 **계속 우리 것**이고, 그 경계가
> [`README.md` §9](README.md)의 "도구와 무관하게 우리가 계속 소유할 것" 표다.
>
> **역할**: 조사 자료. 결정은 [`decisions.md`](../decisions.md)가 소유한다.
>
> **§1–§10은 `문서` 근거, §11은 `실측`, §12는 `소스` 근거의 규모 분석과 개선 후보다(rev 3).** §12의 열
> 가지 중 **7·9는 `D22`로 채택**됐고 나머지는 후보다 — §12-5의 실험 `GOR-X1`–`X5`가 닫는다(`decisions.md` C11).
> **compact 뒤에 이어서 하려면 §12-6에서 시작한다.** rev 2(2026-09-03)에서 **§11이 뒤집은 자리는 앞 절
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

**경로 B + 센티넬 — 결합 쿼리에 `__QUERY__`를 더한 것** (2026-09-04, `GOR-X1`)

```text
쿼리 = coffee + drip + espresso + roasting + latte + __QUERY__
   broad 0.5083  deep6 0.5066  partial 0.5032  generalist 0.5030  narrow 0.5015  parentonly 0.5004
   센티넬 없는 대조군: broad 누락(M2), 나머지 순서 동일
```

M2가 막히고 **깊은 사람(broad·deep6)이 1·2위**다. 순서는 공식 그대로 `commonSum·commonCount / √wsum(d)` —
공통 라벨 수의 제곱에 IDF를 곱하고 보유 태그 폭으로 나눈 값이라, **coverage가 같으면 태그 적은 쪽이 위**고
coverage가 높아도 태그가 아주 많으면(generalist 12개) coverage 낮고 태그 적은 쪽(partial 3개) 아래로 간다.
결과 상세와 10⁴ 규모의 축소 확인은 §12-5 X1 결과.

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

`열린 항목` **2,000개 너머는 미검증.** 이 실험은 상위 라벨당 보유자 250명까지만 갔다.
rev 3 정정(2026-09-03, 소스 확인): *"보유자 수에 이차적일 수 있다"*는 우려는 **코드상 근거가 없다** —
tags 유사도는 brute force가 아니라 **HNSW**(`logics/item_to_item.go`, `ann.NewHNSW`)라 item당 ~log N이
기대되고, 위 10 ms/item에는 **item당 Redis 왕복 3회**(AddScores · digest/time Set · DeleteScores)가
포함돼 있다. 실제 곡선은 `GOR-X3`이 잰다(§12-5).

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

---

## 12. `소스` 규모 — 1억 유저에서 무엇이 깨지나, 그리고 개선 후보 (2026-09-03)

> **이 절은 후보안이다** — 단 7·9는 `D22`(2026-09-03, 오너)로 채택됐다. 나머지의 채택은 `decisions.md`가 하고,
> 지금은 C11(열린 항목)이다. 앞 절과 달리 근거가
> 실측이 아니라 **v0.5.11 소스**다 — 그래서 12-1을 먼저 적고, 그 위에서 문제 둘과 개선 후보 열 가지를 세운
> 뒤, 12-5에서 **무엇을 어떻게 실험해야 후보가 결정이 되는지**를 적는다. 실험이 끝나면 이 절을 그 결과로
> 고쳐 쓴다.

### 12-1 소스에서 확인한 것 (v0.5.11)

| # | 사실 | 위치 |
|---|---|---|
| S1 | tags item-to-item은 **HNSW** 인덱스다. `Push`가 삽입, `PopAll`이 `SearchIndex(i, n+1)` | `logics/item_to_item.go` `newTagsItemToItem`·`baseItemToItem.PopAll` |
| S2 | `n` = **`[recommend] cache_size`**(템플릿 100). 즉 item당 저장되는 이웃은 최대 100 | `master/tasks.go` `updateItemToItem` → `logics.NewItemToItem(cfg, m.Config.Recommend.CacheSize, …)` |
| S3 | **거리 공식**: `1 − commonSum·commonCount / √wsum(a) / √wsum(b) / (commonCount+100)`. `commonSum`=공통 태그 IDF 합, `commonCount`=공통 태그 수, `wsum`=그 item 태그 IDF 합. 점수 = `1/(1+distance)` | `logics/item_to_item.go` `IDF.distance` |
| S4 | 태그 집합이 완전히 같으면 distance 0 — **M2의 원인** | 같은 함수 첫 분기 |
| S5 | `IsHidden` item은 인덱스에 안 들어가고 **벡터로 검색만** 된다 — "이웃은 있지만 남의 이웃은 아니다" | `baseItemToItem.pushItem`·`PopAll` 주석 |
| S6 | `Push`는 **`needUpdate`와 무관하게 전 item에 대해 매 사이클** 돈다. `needUpdate`는 **저장**만 가른다 | `updateItemToItem` 첫 `parallel.ForEach` |
| S7 | `needUpdateItemToItem` = 캐시 없음 ∨ digest 불일치 ∨ updateTime > `cache_expire`. **item 자체의 변경 시각은 보지 않는다** | `master/tasks.go` `needUpdateItemToItem` |
| S8 | 병렬도 = `[master] n_jobs`(템플릿 1) | 같은 함수의 `parallel.ForEach/For(…, m.Config.Master.NumJobs, …)` |
| S9 | master 한 프로세스가 데이터셋 전체 + HNSW를 RAM에 든다. 샤딩 없음 | `updateItemToItem(ctx, dataset)` 시그니처 |

S3에서 두 가지가 바로 읽힌다. **단일 라벨 쿼리**(공통 1개)에서는 `commonSum`·`commonCount`가 모든 보유자에게
같으므로 **`√wsum(d)`만 남는다** — 태그가 적고 흔한 사람이 이긴다(§11-2의 실측이 이것이다). **다중 라벨
쿼리**에서는 공통 라벨이 늘수록 `commonSum`도 `commonCount`도 커져 **분자가 두 겹으로 자란다** — coverage가
높은 사람이 이긴다. §11-2가 경로 B에서 broad를 잃은 것은 길이 정규화가 아니라 **S4(M2)** 때문이었다.

### 12-2 문제 ① — 라벨별 100 컷이 깊은 사람부터 자른다

`D07`의 근거는 *"topic당 100명 컷·페이징 없음이라는 상한이 사라진다"*였다. 정확히는 **하나의 100 컷이
라벨 수만큼의 100 컷으로 쪼개진다**(S2). 100 → 최대 라벨 수 × 100이니 이득은 실제지만 상한은 남는다.

그리고 대규모에서 컷의 **성격이 나빠진다.** 6명이면 다 들어온다. 1억이면 `coffee` 보유자가 수십만이고,
단일 라벨 쿼리의 상위 100은 S3에 의해 **"coffee만 가진 사람" 100명**이다. 그 주제를 가장 깊게 아는 사람은
컷 밖이라 **가중합 단계에 도달조차 못 한다** — 가중합은 컷을 통과한 사람만 재정렬한다. `SURV-R4`가 배포
전 게이트인 이유가 이것이고, **합성 fixture로는 원리상 보이지 않는 종류**다.

### 12-3 문제 ② — 매 사이클 전부 다시 짓고, 한 프로세스가 든다

S6: HNSW를 증분으로 짓는 길이 없다. 사이클마다 전 item을 `Push`한다. S9: 그걸 master 한 프로세스가 든다.
S7: 우리가 읽는 쿼리 item의 이웃 목록은 `cache_expire`(72h)마다만 다시 계산된다 — 새 agent가 순위가 낮은 게
아니라 **72시간 동안 아예 안 보인다**(`decisions.md` C7의 실체).

규모: 1억 item, `n_jobs=32`면 사이클당 **수십 분~수 시간**(S1·S8 — 정확한 곡선은 X3), RAM **수십 GB** 한
박스. "끝나지 않는다"는 아니지만 **매 사이클 그 비용을 내고, 사이클 길이가 곧 새 agent의 가시성 지연**이다.

### 12-4 개선 후보 열 가지 (7·9는 `D22`, 나머지는 결정 아님)

| # | 무엇 | 왜 되나 (12-1) | 비용 | 안 고치는 것 | 닫는 실험 |
|---|---|---|---|---|---|
| **1** | **다중 라벨 쿼리 + 센티넬** — 확정 topic의 라벨 전부를 한 쿼리 item에 | S3: 공통 라벨 수가 분자를 두 겹으로 키움. S4: 센티넬이 M2를 막음. 상위 100은 **`coverage²·IDF / √태그 폭` 순** — coverage 우선이지만 태그가 아주 많은 사람은 아래로 간다(X1 실측) | topic당 쿼리 1개 추가. 코드 변경 0 | 컷 자체. 깊은 사람이 100명 넘으면 그 안에서 다시 `√wsum(d)` | **X1** |
| 2 | **파생 태그 `T#deep`** — 자손 k개 이상 공개한 사람에게 프로젝션이 붙임 | 희소 태그 → IDF 높음 → 분자 큼. 모집단이 작아 컷 안에 다 들어옴. `D13`(파생은 우리 것) 정합 | (agent, 상위 topic)당 태그 1개. 임계값 k 튜닝 축 | 태그가 늘어 `√wsum(d)`가 커짐 — 1과 같이 쓰면 상쇄 | X4 |
| 3 | **뜨거운 라벨만 쿼리 item 샤딩** — agent에 `coffee~s`(s=hash mod S), 쿼리 item S개 | 쿼리 item은 우리가 만드는 것. S개 병렬 조회 → S×100 후보. S는 복제본의 보유자 수에서 자동 | 뜨거운 라벨에 한해 agent당 태그 1개, 쿼리 item S개(hidden). 조회 S개 병렬 | 샤드 안 100은 여전히 `√wsum(d)` 순 — 1·2와 조합 필요 | X4 |
| 4 | `cache_size` 상향 | S2 | **전역**이라 전 item 캐시가 커짐 | 단독으로는 불가. 7과 묶이면 가능 | X3 |
| **5** | **surface 1 후보를 우리 인덱스로** — 복제본(`D10`) 위의 posting list (DynamoDB GSI 또는 OpenSearch) | 우리가 원하는 것은 "라벨 보유자를 coverage/depth 순으로, 페이징 있게"이고 그것은 검색 문제다(`recsys_adoption_discussion.md` §3). 증분이라 새 agent 즉시 노출 | 검색 인덱스 운영(`SURV-R6` §7-5 빈칸). **`D07` 재개방** | surface 2는 무관(Gorse 유지). surface 1은 feedback을 안 읽어 R5 무관 | X2·X3 → **C11** |
| **6** | **item 집합을 `I_eligible`로** — 공개 topic ≥1 · recommendable인 agent만 | `D16`이 이미 프로젝션을 우리 것으로 뒀다. 5%면 빌드·RAM·캐시 전부 1/20 | 지금은 **가정**(출시 전) — 출시 후 우리 복제본에서 센다 | — | **X2**(시나리오) |
| **7 `D22`** | **surface 1 전용 Gorse 인스턴스** — tags item-to-item만, user·feedback 없음 | `D09`(store는 파생물)가 프로젝션 둘을 허용. surface 2의 유저별 캐시(560 GB)와 분리되어 4가 가능해짐 | 배포 둘 (운영 ~1.3배) | 빌드 자체 | X3 |
| 8 | `n_jobs` 상향 + master 사이징 | S8·S9 | 박스 하나 크게 | 단일 프로세스 한계 | X3 |
| **9 `D22`** | **쿼리 item을 사이클마다 새 id로 재생성** (`q:<label>:<gen>`), `cache_expire`는 길게 | S7: 새 item = 캐시 없음 = 무조건 계산. agent들의 목록(아무도 안 읽음)은 한 번 쓰고 끝 → Redis 왕복 3억 회 절약. **새 agent가 1 사이클 안에 보인다** | 사이클마다 hidden item ~3천 개 생성·이전 세대 삭제 | 빌드 자체(S6) | **X5** |
| 10 | (한계) | 9까지 해도 **사이클 시간 ≥ 전면 HNSW 빌드**. 6·7·8이 줄이고 **5만이 없앤다** | | | |

`판단` 순서는 **결정이 필요 없는 것부터**: 1(실험 한 시간) · 6(측정) · 8(설정값). Gorse에 남는다면 7 + 9 +
뜨거운 라벨에 3. `I_eligible`이 수천만 이상이면 5 — 그 규모에서 tags item-to-item은 역인덱스를 흉내 내는
도구고 흉내의 비용(전역 컷·근사·전면 재빌드·단일 프로세스)이 도구를 안 쓰는 비용을 넘는다. **5는 오너
결정이다.**

`판단` **다만 `I_eligible`은 출시 전에 알 수 없다**(X2). 그러므로 지금 할 수 있는 결정은 "5냐 7+9냐"가 아니라
**"되돌리기 쉬운 쪽으로 시작하고, 뒤집는 조건을 적어 두는 것"**이다. 후보 소스는 S3 한 단계의 일이고
(`recommendation_pipeline_design.md` §10 — 단계는 부품), S3을 port로 유지하면 소스를 바꿔도 S1·S2·S4–S6은
그대로다. Gorse는 내부 규모에서 이미 동작이 확인됐고(§11) 5는 인덱스를 새로 짓는 일이므로, **시작은 Gorse +
7 + 9, 뒤집는 조건은 X3의 `N*`**이 자연스럽다 — **→ `D22`로 채택됐다**(2026-09-03, 오너). 뒤집는 조건은
**`I_eligible ≥ 0.5·N*`이면 5로 전환 착수**. 1·2·3은 이 시작안과 **직교**한다 —
②가 아니라 ①의 것이고, 1은 X1이 통과하는 즉시(예상: 한 시간) 합류하며 2·3은 X4가 조합을 정한다. **미룬 것이지
기각한 것이 아니다.**

### 12-5 실험 설계 — `GOR-X1`–`X5`

공통: 환경은 §11과 같다(`gorse-in-one` v0.5.11, playground 없이 config 주입, `[[recommend.item-to-item]]
name="topic_neighbors" type="tags" column="item.Labels.topics"`). 쿼리 item은 전부 `IsHidden=true`, 라벨에
센티넬 `__QUERY__` 포함. 조회는 `GET /api/item-to-item/topic_neighbors/{query-id}?n=100`. 재계산 강제는
`cache_expire`를 짧게 두거나 쿼리 item을 새 id로 만든다(S7). **결과는 이 절에 표로 붙이고, 그 결과로 12-4의
해당 행을 채택/기각으로 바꾼다.**

#### X1 — 경로 B + 센티넬 (후보 1) `한 시간`

- **fixture**: §11-2의 5명(broad·partial·narrow·parentonly·generalist) + **`deep6`** = coffee + 하위 4 +
  무관 1(6태그; 집합이 쿼리와 다르면서 coverage는 broad와 같음).
- **쿼리**: `{coffee, drip, espresso, roasting, latte, __QUERY__}` 하나. 대조군으로 센티넬 없는 동일 쿼리
  (경로 B 원본 — broad 누락 재현).
- **측정**: 순위·점수 전부.
- **통과**: broad·deep6가 1·2위, 순위가 공통 라벨 수 내림차순과 일치(동률은 `√wsum(d)` 오름차순), 센티넬
  없는 쪽에서만 broad 누락.
- **실패의 뜻**: 12-1 S3 해석이 틀렸다 → 공식 재독. 통과하면 12-4의 1을 채택하고 §11-2 표에 "B + 센티넬" 행을
  추가한다.

**결과 (2026-09-04)** — 통과 기준 넷 중 셋 충족, 하나는 기준 자체가 틀렸다. **채택 여부는 오너 결정**(규칙 ③).

환경: `zhenghaoz/gorse-in-one:latest`(= v0.5.11, 2026-07-14 빌드), 포트 18088, config 인라인 아래. 첫 사이클은
insert 후 **45초**에 서빙됐다.

| 후보 | 태그 | 다중+센티넬 | 다중, 센티넬 없음 |
|---|---|---|---|
| broad | coffee drip espresso roasting latte | **0.508299** ① | **누락** (M2) |
| deep6 | 위 5 + hiking | **0.506615** ② | 0.509706 ① |
| partial | coffee drip espresso | 0.503167 ③ | 0.504632 |
| generalist | 위 5 + 무관 7 (12개) | 0.502976 ④ | 0.504352 |
| narrow | coffee drip | 0.501467 | 0.502142 |
| parentonly | coffee | 0.500417 | 0.500609 |
| unrelated | outdoor hiking photo | 0.500000 | 0.500000 |

- ✓ broad·deep6가 1·2위. ✓ 동률(coverage 5)은 `√wsum(d)` 오름차순 — broad(5개) > deep6(6개). ✓ 센티넬 없는 쪽에서만 broad 누락.
- ✗ **"순위 = 공통 라벨 수 내림차순"은 성립하지 않는다.** generalist(공통 5, 태그 12)가 partial(공통 3, 태그 3) 아래다.
  이것은 S3 해석이 틀린 게 아니다 — **12-1 S3 공식으로 계산한 예측이 소수 6자리까지 실측과 일치했다**(IDF 풀 N=9,
  hidden 쿼리 item도 IDF 분모에 들어간다). 틀린 것은 12-4 행 1의 요약 "coverage 순"이고, 그 행을 고쳐 썼다.
  정확한 서술: 점수 순서 = `commonSum·commonCount / √wsum(d)`, 즉 **coverage² × IDF / √태그 폭**.

**10⁴ 규모 축소 확인**(같은 컨테이너, X4의 축소판 — 결정 근거가 아니라 방향 확인): 합성 agent 10,007명(상위 라벨
300 × 하위 9 = 3,000 라벨, 상위 인기 Zipf s=1, coffee가 1위, 태그 1–12, seed 20260904, 생성 코드는 아래) + 위 7명.
coffee 보유자 2,725명, 그중 하위 4개 전부(depth 4) 35명, 3개(depth 3) 209명. 정답 = depth 내림차순·태그 적은 순 상위 100.

| 쿼리 | 상위 100 구성 | 정답 회수 | depth ≥ 3 | broad / deep6 순위 | HNSW vs 정확 검색 |
|---|---|---|---|---|---|
| coffee 단일 + 센티넬 | **전부 coffee 하나만 가진 사람**(태그 1개, depth 0) | 0/100 | 0/244 | 930 / 1465 | 동률 201명 중 임의 100 |
| 다중 5라벨 + 센티넬 | depth 4 31명 + depth 3 69명 | 91/100 | 100/244 | 1 / 14 | **100/100 일치** |

- **문제 ①이 규모에서 그대로 재현된다** — 단일 라벨의 100 컷은 `√wsum(d)`만으로 갈려 태그 하나짜리 201명이 동률
  1위가 되고 깊은 사람은 전부 컷 밖이다. 다중 라벨 쿼리는 컷 안이 전원 depth ≥ 3이다.
- 다중 쿼리에서 빠진 depth 4 네 명은 **모두 태그 11–12개**(generalist형). 그 자리를 태그 4–6개의 depth 3이 채웠다.
  이것이 위 ✗ 항목의 규모판이고, 이게 문제인지(넓은 사람도 깊으면 컷 안에 있어야 하는지)는 **X4의 recall 기준으로
  오너가 정할 것**이다. 후보 2(`#deep` 파생 태그)가 정확히 이 네 명을 위한 것이다.
- 10⁴에서 HNSW는 정확 검색과 상위 100이 완전히 일치했다. 사이클은 insert 후 66초 안에 서빙됐다(ticker 대기 포함,
  item당 비용이 아님 — 그건 X3).
- 쿼리 item과 태그 집합이 완전히 같은 agent가 4명 있었고 센티넬 덕에 넷 다 컷 안이다(그중 broad가 1위).

<details><summary>재현: config.toml · fixture · 생성기</summary>

```toml
[master]
n_jobs = 1
[server]
default_n = 20
auto_insert_user = false
auto_insert_item = false
cache_expire = "1s"
[recommend]
cache_size = 100
cache_expire = "1m"
[recommend.data_source]
positive_feedback_types = ["talked"]
read_feedback_types = ["exposed"]
[[recommend.item-to-item]]
name = "topic_neighbors"
type = "tags"
column = "item.Labels.topics"
[recommend.collaborative]
type = "mf"
fit_period = "1m"
[recommend.fallback]
recommenders = ["item-to-item/topic_neighbors", "latest"]
```

```sh
docker run -d --name gorse-x1 -p 18088:8088 -v $PWD/config.toml:/etc/gorse/config.toml zhenghaoz/gorse-in-one:latest
curl -X POST -H 'Content-Type: application/json' --data @fixture.json localhost:18088/api/items
# ~60s 뒤
curl 'localhost:18088/api/item/q:multi:sent/neighbors/?n=100'
```

fixture (9 item; `Categories`는 임의, `Timestamp` 고정 `2026-08-01T00:00:00Z`, `IsHidden`은 q:*만 true):

```text
a:broad       coffee drip espresso roasting latte
a:partial     coffee drip espresso
a:narrow      coffee drip
a:parentonly  coffee
a:generalist  coffee drip espresso roasting latte outdoor hiking photo food cooking music travel
a:unrelated   outdoor hiking photo
a:deep6       coffee drip espresso roasting latte hiking
q:multi:sent   (hidden) coffee drip espresso roasting latte __QUERY__
q:multi:nosent (hidden) coffee drip espresso roasting latte
```

10⁴ 생성기(핵심만; `random.seed(20260904)`): 상위 300개 Zipf(1/rank) 중 agent당 1–4개를 가중 {45,30,17,8}로,
상위마다 하위 0–5개를 가중 {30,28,20,12,7,3}·하위 인기 Zipf로 뽑고 상위 라벨을 함께 넣는다(하위 ⇒ 상위). 태그 12개 상한.
coffee의 하위 = drip espresso roasting latte grinder beans cold_brew pour_over cupping. 검증용 정확 순위는
12-1 S3 공식을 그대로 옮긴 파이썬으로 계산했다(IDF = max(log(N/freq), 1e-3), N은 hidden 포함 전체 item 수).

</details>

#### X2 — `I_eligible` 시나리오와 출시 후 계측 (후보 6, C11의 임계값)

**출시 전에는 측정할 수 없다**(2026-09-03, 오너 — 내부 사용 단계라 공개 topic 보유자 수·분포·증가율에
표본이 없다). 그래서 이 항목은 측정이 아니라 **두 부분**이다.

- **(a) 지금 — 시나리오.** `I_eligible = U × r`로 두고 `U = 10⁸`(목표), `r ∈ {1%, 5%, 20%}` → 10⁶ · 5×10⁶ ·
  2×10⁷. 태그 수 분포는 §11 fixture의 1–12를 Zipf로 잡는다. **이 세 점이 X3의 입력이고, X3이 돌려주는 것은
  임계값 `N*`** — Gorse 사이클·RAM이 한계를 넘기 시작하는 item 수. 그러면 C11의 질문은 "I_eligible이 얼마인가"에서
  **"우리 목표 규모가 `N*`보다 큰가"**로 바뀌고, 그건 표본 없이 기획이 답할 수 있다.
- **(b) 출시 후 — 계측.** 공개 보유 복제본(`D10`)이 우리 것이므로 **topic-api 협의 없이** 센다: 공개 topic ≥1인
  user 수, 그 분포(p50·p95·max), 주간 증가. 이 값이 `N*`에 접근하면 C11을 다시 연다(아래 "뒤집는 조건").
  `recommendable` opt-in이 생기면(`EVT-E4`) 그 축을 곱한다. `SURV-R8`·`STO-S1`이 같은 질문이다.
- **판정**: 없음. (a)는 X3의 입력이고 (b)는 운영 지표다.

#### X3 — 대규모 빌드 (SURV-R3 확장; 후보 4·7·8 사이징)

- **합성 데이터**: N ∈ {10⁵, 10⁶, 10⁷}. 라벨 3천 개(카탈로그 규모), 라벨 인기 Zipf(s≈1 — `coffee`류 뜨거운
  라벨이 생기게), agent당 태그 수는 X2 분포(없으면 1–12).
- **변수**: `n_jobs` ∈ {1, 8, 32}.
- **측정**: 사이클 시간을 **`Push` 구간과 저장 구간으로 분리**(tracer span 또는 로그 타임스탬프), master RSS
  최대, Redis 쓰기 횟수, 뜨거운 라벨 쿼리 item의 `PopAll` 시간.
- **산출**: item당 비용 곡선(S1이면 ~log N), RAM/item. X2 값을 대입해 사이클 시간·박스 크기.
- **판정**: 사이클 ≤ 목표 가시성 지연(C7이 정할 값) ∧ RAM ≤ 한 박스. 이 둘을 만족하는 최대 item 수가
  **`N*`**이고, `D22`의 뒤집는 조건은 **`I_eligible ≥ 0.5·N*`**이다. `N*`가 나오면 `decisions.md` D22에 숫자로
  적는다.

#### X4 — 컷 안의 깊은 사람 비율 (후보 1·2·3 비교; SURV-R4의 핵심) `X3의 10⁶ 세트 재사용`

- **대상**: 보유자 ≥ 5만인 뜨거운 라벨 하나.
- **ground truth**: 그 topic에 대한 각 agent의 depth 점수 — `ranking.md`의 식이 있으면 그것, 없으면 하위
  라벨 보유 수. 상위 100명이 정답 집합.
- **조건**: (a) 단일 라벨 쿼리 (b) 다중 라벨 + 센티넬 (c) `#deep` 파생 태그 쿼리 (d) 샤딩 S=50 단일 라벨
  (e) b + d.
- **지표**: 후보 합집합에 정답 100명 중 몇이 들어오는가(recall@100). 부수: 후보 수, 쿼리 수, 조회 지연.
- **통과**: 채택 조합의 recall ≥ 0.9 (오너 확정 2026-09-03).
- **결과 사용**: 12-4의 1·2·3 중 무엇을 어떤 조합으로 쓰는지가 여기서 정해진다.

#### X5 — 쿼리 item 재생성 (후보 9; C7 해소 경로)

- **절차**: `cache_expire = 8760h`. 사이클마다 `q:<label>:<gen>` hidden item 생성, 이전 세대 `DELETE /api/item`.
  새 agent 1명을 넣고 다음 사이클 뒤 **새 세대** 쿼리 결과에 보이는지.
- **확인 둘**: ⑴ item 삭제 시 Gorse가 그 item의 캐시 이웃 목록을 지우는지(`DeleteItem` 경로 — 지우지 않으면
  세대마다 Redis 키가 쌓이므로 우리가 지우는 절차가 필요). ⑵ 세대가 바뀌는 순간 서빙이 옛 세대와 새 세대를
  섞지 않는지(우리 쪽 — 세대 번호를 원자적으로 바꾼다).
- **통과**: 새 agent가 1 사이클 안에 노출. 삭제 세대의 키가 남지 않거나 우리가 지우는 절차가 확정됨.

### 12-6 실행 순서와 결정 지점 — **compact 뒤에는 여기서 시작한다**

**2026-09-03 시점 상태**: `D22` 채택(7+9로 시작, 여유율 50%). 열린 것은 C11의 잔여 둘 — `N*`의 숫자(X3), ①
쪽 조합(X1·X4). C7(가시성)은 9가 해소 경로이고 X5가 확인한다.

**2026-09-04**: X1 완료 — 공식 검증 통과, 센티넬 유효, 단 "coverage 순"은 틀려서 12-4 행 1을 고쳐 썼다. **후보 1의 채택은
오너 결정으로 남아 있다**(결과 소절 참조). 다음은 X5.

**환경**(모든 실험 공통): `gorse-in-one` v0.5.11, playground 없이 `/etc/gorse/config.toml` 주입(§11 서두·M5),
`[[recommend.item-to-item]] name="topic_neighbors" type="tags" column="item.Labels.topics"`, `n_jobs`는 코어 수.
쿼리 item은 `IsHidden=true` + `__QUERY__`. §11의 fixture 파일이 repo에 없으므로 **X1 결과를 적을 때 fixture를
그 아래에 인라인으로 붙인다**(다음 사람이 재현할 수 있게).

| 순서 | 실험 | 선행 | 결과가 바꾸는 것 | 문서 갱신 |
|---|---|---|---|---|
| 1 | **X1** 경로 B + 센티넬 — **완료 2026-09-04** | 없음 (한 시간) | 12-4 행 1 채택/기각 (**오너 판단 대기**) | §11-2 표에 "B + 센티넬" 행 · 통과 시 `decisions.md`에 `Dnn`(출처 **실측**) · 기준 문서 §S3 "라벨별 개별 쿼리 + 가중합"에 다중 라벨 쿼리 추가 |
| 2 | **X5** 쿼리 item 세대 재생성 | 없음 | 9의 두 확인(삭제 시 캐시 정리 · 세대 전환 원자성) | 12-4 행 9에 확인 결과 · 캐시 정리 절차가 필요하면 §12-5 X5 아래 · C7에 "해소 경로 확인" |
| 3 | **X3** 대규모 빌드 | **합성 데이터 생성기**(라벨 3천 · Zipf s≈1 · 태그 1–12 · N = 10⁶/5×10⁶/2×10⁷) | **`N*`** | `D22`에 `N*` 숫자 · `storage_sizing.md`에 surface 1 인스턴스 이웃 캐시(`I_eligible × cache_size`) 추가 · `SURV-R3` 닫기 |
| 4 | **X4** 컷 안 깊은 사람 비율 | X3의 10⁶ 세트 | 12-4 행 2·3 조합 (통과 기준 recall ≥ 0.9, 오너 확정) | 채택 조합 → `Dnn` · 기준 문서 §S3 · `SURV-R4`(배포 전 게이트) 판정 |
| 5 | — 결정 | 1–4 | **C11 닫기** | `decisions.md` C11에 "해소" · 기준 문서 §S3에 최종 형태(전용 인스턴스 · 세대 · 조합) · `recsys_opensource/README.md` §2 표 갱신 |

**출시 후**(실험이 아니라 운영): 우리 복제본에서 `I_eligible`을 주간으로 센다(X2(b)). `0.5·N*`에 닿으면 `D22`의
뒤집는 조건이 발동 — C11이 아니라 **새 C 항목**으로 열고 12-4의 5를 실행 계획으로 바꾼다.

**결과 기록 형식**: 각 실험의 §12-5 소절 아래에 `**결과 (YYYY-MM-DD)**` 소절 — 표 · 통과/실패 · 실패면 그
뜻(12-5가 미리 적어 둔 "실패의 뜻") · 그 결과로 바뀐 문서 목록. 12-4의 해당 행은 **고쳐 쓴다**(경고를 덧붙이지
않는다 — `decisions.md` 규칙 ②).

**하지 말 것**: 실험 전에 1·2·3을 채택으로 쓰지 않는다(규칙 ③). `N*` 없이 D22의 조건을 숫자로 쓰지 않는다.
결과를 이 문서 밖(대화·scratchpad)에만 남기지 않는다.

### 12-7 이 절이 하지 않는 것

- **채택하지 않았다.** 열 가지는 후보이고 C11이 열려 있다.
- **지연 예산을 정하지 않았다**(`decisions.md` C9). X3의 판정 기준 "목표 가시성 지연"은 C7·C9가 정할 값이다.
- **저장 규모를 다시 계산하지 않았다.** surface 1 전용 인스턴스(7)의 이웃 캐시(`I_eligible` × `cache_size`)는
  `storage_sizing.md`가 X2 뒤에 더한다.

