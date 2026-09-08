# agent-discovery-api 공통 계약 — 요청·응답, 후보 소스 인터페이스, 랭커 feature, 결정 로그

> `agent_discovery_redesign.md` §9의 2번. 두 구현안(A 오픈소스 중심 / B 직접 구현 / 혼합)이 **똑같이 지켜야 하는 것**만 적는다. 이 계약 위에서 두 안을 갈아 끼우고, 같은 측정을 하고, 최종 선택 뒤에도 클라이언트와 bourbon-agent는 바뀐 것을 모른다.
>
> 기존 `POST /recommend`의 필드명은 유지하지 않는다(오너 2026-09-08). 타입별로 route와 스키마를 나눈다.
>
> 초안. 필드는 구현 중 바뀔 수 있지만 **§5 불변식은 바뀌지 않는다.**

---

## 0. 한눈에

| 타입 | route | 면 | 요청자 |
|---|---|---|---|
| ① 명시 요청 | `POST /recommend/explicit` | 내부 `/api/internal/svc/agent-discovery` | body `user_id` |
| ② topic별 목록 | `GET /discover/by-topic` (섹션 개요), `GET /discover/by-topic/{topic_id}` (섹션 한 개, 페이지) | 클라이언트 `/api/svc/agent-discovery` | edge-auth `x-user-id` |
| ③ 나를 위한 목록 | `GET /discover/for-you` | 클라이언트 | edge-auth `x-user-id` |
| ②③ 내부 미러 | `GET /users/{user_id}/discover/…` | 내부 | 경로 `user_id` |

세 응답은 모두 같은 `RecommendedAgent` 요소와 같은 `recommendation_id`를 갖는다. 뒤의 상호작용 이벤트가 이 id로 되돌아온다.

---

## 1. 두 면

topic-api와 같은 방식이다. 라우터는 하나씩이고, 앱이 두 prefix로 두 번 붙인다.

- **클라이언트 면** `/api/svc/agent-discovery/…`: edge-auth 사이드카가 `x-user-id`를 덮어쓴다. 요청자는 그 헤더다. 헤더가 없거나 UUID가 아니면 "인증 안 됨"이 아니라 "검사를 우회했다"이므로 403.
- **내부 면** `/api/internal/svc/agent-discovery/…`: 게이트웨이의 내부 게이트만 지난다. edge-auth가 없으므로 **어떤 route도 `x-user-id`를 읽지 않는다.** 요청자는 body나 경로의 `user_id`다.

타입 ①은 내부 면에만 있다(호출자가 bourbon-agent). 타입 ②③은 클라이언트 면이 본 면이고, 내부 미러는 시험·운영 확인·다른 서비스 용이다.

---

## 2. 요청

### 2-1. 타입 ① `POST /recommend/explicit`

```json
{
  "user_id": "uuid",                 // 요청자. 결과에서 본인은 제외
  "topic_text": "캠핑하면서 핸드드립커피",   // free text, 1~200자
  "context": "…",                    // 대화 맥락, ≤ 2000자, 선택
  "max_results": 3,                  // 1~20, 기본 3
  "room_id": "uuid",                 // 로그 상관용. 이 서비스는 room을 읽지 않음
  "lang": "ko"                       // 응답 라벨 언어 힌트, 기본 en
}
```

`topic_text`와 `context`는 유저의 말이다. **로그·예외·Sentry에 원문이 실리지 않는다.** 로그에는 다이제스트만 남는다.

### 2-2. 타입 ② `GET /discover/by-topic`

```
GET /discover/by-topic?per_section=5&sections=10&lang=ko
```

요청자의 grounding된 topic 중 preference 점수 상위 `sections`개를 섹션으로, 섹션마다 agent `per_section`명. 응답의 각 섹션에 `next_cursor`가 있고, 더 보기는 아래 route다.

```
GET /discover/by-topic/{topic_id}?limit=20&cursor=…&lang=ko
```

`topic_id`는 요청자가 가진 topic이어야 한다. 아니면 404(요청자의 topic 목록에 없음). 요청자가 그 topic을 private/hidden으로 갖고 있어도 자기 것이므로 조회는 된다. 이 route는 요청자의 topic을 읽지만 타인의 것은 §5 규칙으로만 읽는다.

### 2-3. 타입 ③ `GET /discover/for-you`

```
GET /discover/for-you?limit=20&cursor=…&lang=ko
```

입력은 요청자 id뿐이다. persona·topic·로그는 서버가 이미 갖고 있다.

### 2-4. 공통 규칙

- `lang`은 topic 라벨의 언어 힌트다. 응답은 항상 `ko`, `en` 두 키를 주고 없으면 null이다.
- 페이지는 불투명 `cursor`다. 오프셋을 노출하지 않는다(사전 계산 결과가 갈아엎어지면 오프셋은 의미가 없다).
- 요청자 본인의 agent는 어느 타입에서도 결과에 없다.

---

## 3. 응답

### 3-1. 공통 요소 `RecommendedAgent`

```json
{
  "agent_id": "uuid",              // personal agent id
  "owner_user_id": "uuid",         // agent 주인. agent_id에서 유도되지만 클라이언트가 유도하지 않게 준다
  "position": 1,                   // 이 응답 안의 순위 (1부터). 페이지가 이어져도 계속 증가
  "matched_topics": [              // 이 agent가 여기 있게 만든 topic들
    {
      "topic_id": "…",
      "labels": {"ko": "캠핑", "en": "Camping"},
      "requested": true,           // 타입 ①: 뽑힌 topic 중 하나인가. 타입 ②: 섹션 topic이면 true
      "owner_note": {"ko": "…", "en": null}   // 주인이 그 topic에 쓴 한 문장. 선택, null 가능
    }
  ],
  "signals": {                     // 왜 여기 있나 — 랭커 feature 중 보여줘도 되는 것 (§7)
    "coverage": 2,                 // 타입 ①: 뽑힌 topic 중 몇 개를 가졌나. ②③: null
    "topic_maturity": 0.7,         // matched_topics 중 최고, 0~1, 없으면 null
    "agent_maturity": 0.4,         // 0~1, 없으면 null
    "popularity": 0.2,             // 0~1 정규화, 없으면 null
    "similar_users": 12            // 타입 ③: 이 agent와 대화한 "비슷한 사람" 수. 로그 없으면 null
  },
  "fit": null                      // "맞음/안 맞음" 표시. 제품 미확정이라 지금은 항상 null, 자리만 둔다
}
```

`owner_note`는 주인이 쓴 글이다. **응답에 실리는 것으로 여행이 끝난다.** 로그, 예외, 결정 로그, Sentry에 들어가지 않는다.

### 3-2. 타입별 봉투

**① `POST /recommend/explicit` → 200**

```json
{
  "recommendation_id": "uuid",
  "resolved_topics": [ {"topic_id": "…", "labels": {…}} ],   // free text에서 확정된 topic, 1~3개, 커버리지의 분모
  "agents": [ RecommendedAgent… ],                            // 커버리지 내림차순, 같은 커버리지 안에서 점수순
  "empty_reason": null,          // agents가 비었을 때만: "no_open_holders" | "all_filtered"
  "degraded": []                 // 아래 §3-4
}
```

**② `GET /discover/by-topic` → 200**

```json
{
  "recommendation_id": "uuid",
  "sections": [
    {
      "topic_id": "…", "labels": {…},
      "agents": [ RecommendedAgent… ],
      "next_cursor": "…" | null
    }
  ],
  "degraded": []
}
```

섹션이 비면(그 topic을 연 타인이 없음) 섹션은 `agents: []`로 남긴다. 섹션이 아예 없으면(요청자가 topic이 없음) `sections: []`.

**③ `GET /discover/for-you` → 200**

```json
{
  "recommendation_id": "uuid",
  "agents": [ RecommendedAgent… ],
  "basis": "popularity" | "content" | "collaborative",   // 이 응답을 주로 만든 신호. 콜드스타트 표시용
  "next_cursor": "…" | null,
  "degraded": []
}
```

### 3-3. 오류

| 상태 | 언제 | 타입 |
|---|---|---|
| 200 + 빈 목록 + `empty_reason` | 열린 보유자가 없다, 또는 있었지만 필터에서 다 빠졌다 | 모두 |
| 403 | 클라이언트 면에서 `x-user-id` 없음/비정상 | ②③ |
| 404 | `by-topic/{topic_id}`의 topic이 요청자 것이 아님 | ② |
| 422 | `topic_text`에서 확정된 topic이 0개 (요청이 모호함) | ① |
| 503 | topic 확정을 시도하지 못했다(LLM·topic-api 무응답), 또는 저장소 무응답 | 모두 |

422와 503의 구분은 **어디서 멈췄나로** 결정되고, 나중에 상태만 보고 추정하지 않는다. "봤는데 없다"가 422, "못 봤다"가 503이다.

### 3-4. `degraded`

응답이 완전하지 않지만 답할 수 있을 때. 값은 요청자 개인이나 특정 주인에 관한 사실을 새기지 않는 것만 허용한다.

| 값 | 뜻 |
|---|---|
| `friends_unavailable` | 친구 목록을 못 읽어 friends tier를 후보에서 뺐다. public만 답했다 |
| `expansion_partial` | 타입 ①: 개념 확장 일부가 답을 못 받아 topic이 덜 뽑혔을 수 있다 |
| `hydration_partial` | 라벨·owner_note를 다 못 채웠다 |
| `stale_precompute` | 타입 ③: 사전 계산 결과가 갱신 주기를 넘겼다 |

"몇 개가 가려졌다"는 어떤 형태로도 응답에 없다(§5).

---

## 4. 도메인 인터페이스 — A안과 B안이 갈아 끼우는 자리

```
요청 ─▶ QueryBuilder ─▶ CandidateSource들 ─▶ VisibilityFilter ─▶ Ranker ─▶ Assembler ─▶ 응답
        타입별          A/B가 다름          공통                 공통      공통
```

### 4-1. 질의

```python
@dataclass(frozen=True)
class TopicQuery:            # 타입 ①(topic 1~3개), 타입 ②(topic 1개)
    requester: UUID
    topic_ids: tuple[str, ...]
    limit: int

@dataclass(frozen=True)
class UserQuery:             # 타입 ③
    requester: UUID
    limit: int
    cursor: str | None
```

타입 ①의 QueryBuilder는 free text → 개념 확장 → topic-api 검색 → topic 확정(기존 코드의 S1·S2)이고, 결과가 `TopicQuery`다. 타입 ②의 QueryBuilder는 요청자의 topic 목록을 읽어 topic마다 `TopicQuery` 하나를 만든다. 타입 ③은 `UserQuery` 그대로다.

### 4-2. 후보 소스

```python
@dataclass(frozen=True)
class SourceHit:
    owner_user_id: UUID
    tier: Literal["public", "friends"]   # 이 hit이 근거한 row의 tier
    topic_id: str | None                 # topic 근거가 있으면. CF/인기도 hit은 None
    source: str                          # "topic_index" | "popularity" | "content_similarity" | "cf_item" | "cf_engine" …
    score: float                         # 소스 안에서만 비교 가능한 값
    evidence: Mapping[str, float]        # 랭커 feature 재료 (예: topic_score, topic_maturity, co_count)

class CandidateSource(Protocol):
    name: str
    async def candidates(self, query: TopicQuery | UserQuery) -> Sequence[SourceHit]: ...
```

- 소스는 **tier를 반드시 붙인다.** tier를 모르는 소스(예: 엔진이 준 agent 목록)는 뒤의 필터가 열린 row 저장소에서 tier를 조회해 붙이고, row가 없으면 버린다. 즉 엔진 결과는 후보를 좁힐 뿐 노출을 허가하지 못한다.
- 한 타입이 소스 여러 개를 쓸 수 있다. 타입 ③은 `popularity + content_similarity + cf_*`.
- 소스는 `limit`보다 넉넉히 낸다(필터에서 빠지는 양을 감안, 예: 3배). 부족하면 파이프라인이 한 번 더 넉넉히 요청한다.
- A안은 `cf_engine`(Gorse 등)과 `topic_index`(OpenSearch 또는 B의 색인), B안은 `topic_index`, `popularity`, `content_similarity`, `cf_item`을 구현한다. 혼합은 소스 조합 설정이다.

### 4-3. visibility 필터

```python
class VisibilityFilter(Protocol):
    async def allow(self, requester: UUID, hits: Sequence[SourceHit]) -> tuple[Sequence[SourceHit], Degradation]: ...
```

규칙은 §5. 구현은 하나다. 두 안이 공유하고, 비교에서 같은 코드를 쓴다.

### 4-4. 랭커

```python
@dataclass(frozen=True)
class Features:              # §7의 feature 벡터. 없는 값은 0, 있었는지는 mask로
    values: Mapping[str, float]
    present: frozenset[str]

class Ranker(Protocol):
    def features(self, owner: UUID, hits: Sequence[SourceHit], query: TopicQuery | UserQuery) -> Features: ...
    def score(self, f: Features) -> float: ...
```

타입 ①은 `score` 앞에 커버리지 정렬이 온다: `(coverage desc, score desc)`. 타입 ②③은 `score desc`. 처음엔 가중합(가중치는 설정 파일), 로그가 쌓이면 학습 모델로 교체하되 인터페이스는 같다.

### 4-5. 조립

`RecommendedAgent`를 만들고 라벨·owner_note를 채운다(hydration). hydration은 응답 직전이고 실패하면 `hydration_partial`. **응답 직전에 열린 row 존재를 다시 확인**한다(§5 불변식 4).

---

## 5. 불변식 — 두 안 모두, 언제나

1. **저장소에는 열린 row만 있다.** `(topic_id, owner, tier ∈ {public, friends})`. private·hidden은 들어오지 않고, 닫히면 지운다. agent private면 그 주인의 row 전부를 지운다.
2. **friends row는 요청자가 주인의 친구일 때만 통과한다.** 친구 여부는 bourbon-api가 기준이다.
3. **친구 목록을 못 읽으면 friends tier는 빠진다(fail-closed).** 응답은 `degraded: ["friends_unavailable"]`, 상태는 200.
4. **사전 계산 결과는 노출을 허가하지 않는다.** 응답 직전에 현재 열린 row로 다시 거른다.
5. **응답은 "가려짐"과 "없음"을 구별하지 못한다.** 가려진 개수, 표시, 순위 공백이 없다.
6. **요청자 본인은 결과에 없다.**
7. **유저의 글(topic_text, context, owner_note)은 로그·예외·Sentry에 원문으로 실리지 않는다.** 결정 로그에도 없다.
8. **상태 코드는 멈춘 지점에서 결정된다.** 422 = 봤는데 없다, 503 = 못 봤다.

---

## 6. 열린 row 저장 모델 — 저장소 무관

두 안이 공유하는 최소 모델. 어느 저장소(MySQL/PostgreSQL/DynamoDB/Redis/OpenSearch)에 두든 이 모양이다.

| 집합 | 키 | 값 | 갱신 |
|---|---|---|---|
| `open_topic_rows` | `(topic_id, tier, owner_user_id)` | `topic_score`(요청자 쪽 preference 강도), `topic_maturity`, `updated_at` | topic 변경 이벤트. 닫힘 = 삭제 |
| `open_topic_rows` 보조 색인 | `owner_user_id` | → 그 주인의 row들 | agent private 시 일괄 삭제용 |
| `agents` | `owner_user_id` | `visibility`, `agent_maturity`, `updated_at` | agent 변경 이벤트 |
| `requester_topics` | `user_id` | 요청자 자신의 topic 목록(tier 무관, 점수 포함) | topic 변경 이벤트. 타입 ②의 섹션과 타입 ③의 content 질의에 씀 |
| `friends` (선택) | `user_id` | 친구 id 집합 | `bourbon.friendship_changed`. 미러하지 않으면 요청 시 조회+TTL |
| `popularity` | `owner_user_id` | 시간 감쇠 카운트 | 대화 시작 이벤트 |
| `precomputed_for_you` | `user_id` | `[(owner_user_id, score, basis)]` top-K, `computed_at` | 배치 |
| `interactions` | `(viewer, owner, started_at)` | `turns`, `duration`, `entry`, `recommendation_id` | 대화 이벤트. CF 학습 입력 |

타입 ①②의 조회는 `open_topic_rows[topic_id, public]` ∪ (`open_topic_rows[topic_id, friends]` ∩ friends(요청자)) 이고, 타입 ①은 topic ≤ 3개의 결과를 owner로 합쳐 커버 수를 센다. 엔진(A안)이 자기 저장소를 따로 가져도 위 집합은 그대로 있어야 한다. 불변식 1·4가 여기서 판정되기 때문이다.

---

## 7. 랭커 feature

| feature | 정의 | 범위 | 출처 | 타입 |
|---|---|---|---|---|
| `coverage` | 뽑힌 topic 중 가진 수 | 0~3 | topic_index | ① (1차 정렬 키) |
| `topic_score` | 주인 쪽 preference 강도, matched topic 합 또는 최대 | 0~1 | open_topic_rows | ①② |
| `topic_maturity` | matched topic 성숙도 최대 | 0~1 | open_topic_rows (임시값 → 컴포넌트) | ①②③ |
| `agent_maturity` | agent 성숙도 | 0~1 | agents | ①②③ |
| `popularity` | 최근 N일 대화 시작 수, 시간 감쇠, 전체 최대로 정규화 | 0~1 | popularity | ③ (①②는 약한 가중) |
| `content_similarity` | 요청자 topic 집합과 주인 topic 집합의 가중 겹침 | 0~1 | requester_topics × open_topic_rows | ③ |
| `cf_score` | 아이템 이웃 또는 행렬 분해 점수, 소스 안에서 정규화 | 0~1 | cf_item / cf_engine | ③ |
| `similar_users` | 이 agent와 대화한 유사 유저 수 | 정수 | cf_item | ③ (표시용) |
| `recency` | 주인의 마지막 topic 갱신이 얼마나 최근인가 | 0~1 | open_topic_rows.updated_at | 모두, 작은 가중 |
| `tier_is_friends` | 근거 row가 friends tier인가 | 0/1 | 필터 결과 | 모두. 친구를 살짝 올릴지는 제품 판단 |

없는 feature는 0이고 `present`에 없다. 가중치는 설정이며 비교(§`redesign` 6)에서는 두 안이 같은 가중치를 쓴다.

---

## 8. 결정 로그

응답마다 한 건. 오프라인 평가와 A/B 비교의 정답 로그다. **유저의 글은 없다.**

```json
{
  "recommendation_id": "uuid",
  "type": "explicit" | "by_topic" | "for_you",
  "requester_user_id": "uuid",
  "implementation": "A" | "B" | "mix-…",          // 비교 기간 동안 어느 안이 답했나
  "query": {                                      // 타입별. 원문 없음
    "topic_text_digest": "16hex",                 // ① sha256 앞 64비트
    "resolved_topic_ids": ["…"],                  // ①
    "topic_id": "…",                              // ② 섹션 route
    "cursor": "…"                                 // ②③
  },
  "sources": [ {"name": "topic_index", "hits": 41, "latency_ms": 6} ],
  "filter": {"in": 41, "out": 29, "friends_used": true, "degraded": []},   // 개수는 로그에만. 응답엔 없음
  "ranked": [ {"owner_user_id": "uuid", "position": 1, "features": {…}, "score": 0.83} ],
  "basis": "content",                             // ③
  "latency_ms": {"query": 640, "sources": 9, "filter": 3, "rank": 1, "assemble": 12, "total": 668},
  "served_at": "2026-09-08T…Z"
}
```

`filter.out`은 로그에만 있다. 응답에 실리면 불변식 5를 깬다.

---

## 9. 이벤트

### 9-1. 우리가 받는 것

| 이벤트 | 상태 | payload | 우리 처리 |
|---|---|---|---|
| `bourbon.friendship_changed` | **있음** (bourbon-api) | `user_low, user_high, action, occurred_at` | friends 미러 갱신 또는 캐시 무효화 |
| `bourbon.user_topics_snapshot` | 정의해 요청 (topic-api, deferq 도입 필요) | `user_id, revision, occurred_at, topics: [{topic_id, visibility, score, score_version, updated_at}]` — 유저의 **현재 열린 집합 전체** | `revision`이 더 크면 그 유저의 열린 row를 스냅샷으로 통째로 교체(없어진 것은 삭제). 델타가 아니라 스냅샷이라 놓친 닫힘이 다음 스냅샷에서 고쳐진다. 상세 `agent_discovery_events.md` §2-1 |
| `bourbon.personal_agent_visibility_changed` | 정의해 요청 (bourbon-api — **visibility 필드 자체가 아직 모델에 없음**) | `owner_user_id, agent_id, visibility, occurred_at` | private → 그 주인 row 전부 삭제 |
| `bourbon.agent_maturity_changed` | 정의해 요청 (성숙도 컴포넌트, 예정) | `user_id, maturity, occurred_at` | `agents` 갱신 |
| `bourbon.personal_agent_seated` | 정의해 요청 (bourbon-api — 타인 agent와의 대화는 group room **착석**으로 시작된다) | `room_id, agent_id, owner_user_id, actor_user_id, entry, recommendation_id?, occurred_at` | `interactions` 기록, `popularity` 증가. `recommendation_id`는 클라이언트가 착석 요청에 실어야 온다 |
| `bourbon.personal_agent_turn` | 정의해 요청 (bourbon-agent 권고, 대안 bourbon-api) | `room_id, agent_id, owner_user_id, speaker_user_id, occurred_at` | `interactions`의 turn 수·지속 보강 |
| `bourbon.user_deactivated` | **있음** (bourbon-api) | `user_id` | 그 유저의 모든 데이터 삭제 |

topic 스냅샷의 tier 범위(public·friends만 / private 포함)와 turn 이벤트 발행 주체는 `agent_discovery_events.md` §5의 오너 확인 항목이다.

### 9-2. 우리가 내는 것

지금은 없다. 결정 로그(§8)는 저장소에 쓰고 이벤트로는 내지 않는다. 다른 서비스가 "추천이 나갔다"를 알아야 할 때 그때 정의한다.

---

## 10. 버전과 호환

응답 봉투에 `contract_version: 1`. 필드 추가는 같은 버전, 필드 의미 변경이나 삭제는 버전을 올린다. 비교 기간에 A·B가 같은 버전으로 답해야 하고, `implementation`은 결정 로그에만 있고 응답에는 없다.

---

## 11. 이 계약이 열어 둔 것

- `fit`의 내용(제품 미확정). 자리만 있다.
- `tier_is_friends`에 가중치를 줄지.
- 타입 ② 섹션 순서가 요청자 preference 점수인지 다른 기준인지. 지금은 preference.
- 대화 이벤트의 발행 주체.
- `precomputed_for_you`의 갱신 주기와 `stale_precompute` 기준.
