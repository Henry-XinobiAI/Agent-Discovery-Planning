# agent-discovery-api 공통 계약 — 요청·응답, 후보 소스 인터페이스, 랭커 feature, 결정 로그

> `agent_discovery_redesign.md` §9의 2번. 두 구현안(A 오픈소스 중심 / B 직접 구현 / 혼합)이 **똑같이 지켜야 하는 것**만 적는다. 이 계약 위에서 두 안을 갈아 끼우고, 같은 측정을 하고, 최종 선택 뒤에도 클라이언트와 bourbon-agent는 바뀐 것을 모른다.
>
> 기존 `POST /recommend`의 필드명은 유지하지 않는다(오너 2026-09-08). 타입별로 route와 스키마를 나눈다.
>
> 초안. 필드는 구현 중 바뀔 수 있지만 **§5 불변식은 바뀌지 않는다.**

---

## 0. 한눈에

| 타입 | route | API | 요청자 |
|---|---|---|---|
| ① 명시 요청 | `POST /recommend/explicit` | 내부 `/api/internal/svc/agent-discovery` | body `user_id` |
| ② topic별 목록 | `GET /discover/by-topic` (섹션 개요), `GET /discover/by-topic/{topic_id}` (섹션 한 개, 페이지) | 클라이언트 `/api/svc/agent-discovery` | edge-auth `x-user-id` |
| ③ 나를 위한 목록 | `GET /discover/for-you` | 클라이언트 | edge-auth `x-user-id` |
| ②③ 내부 미러 | `GET /users/{user_id}/discover/…` | 내부 | 경로 `user_id` |

세 응답은 모두 같은 `RecommendedAgent` 요소와 같은 `recommendation_id`를 갖는다. 뒤의 상호작용 이벤트가 이 id로 되돌아온다.

---

## 1. 두 API

topic-api와 같은 방식이다. 라우터는 하나씩이고, 앱이 두 prefix로 두 번 붙인다.

- **클라이언트 API** `/api/svc/agent-discovery/…`: edge-auth 사이드카가 `x-user-id`를 덮어쓴다. 요청자는 그 헤더다. 헤더가 없거나 UUID가 아니면 "인증 안 됨"이 아니라 "검사를 우회했다"이므로 403.
- **내부 API** `/api/internal/svc/agent-discovery/…`: 게이트웨이의 내부 게이트만 지난다. edge-auth가 없으므로 **어떤 route도 `x-user-id`를 읽지 않는다.** 요청자는 body나 경로의 `user_id`다.

타입 ①은 내부 API에만 있다(호출자가 bourbon-agent). 타입 ②③은 클라이언트 API가 기본이고, 내부 미러는 테스트·운영 확인·다른 서비스 용이다.

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
GET /discover/by-topic?per_section=5&sections=10&lang=ko      // 기본값 5·10은 플레이스홀더 — 섹션 크기와 페이지는 미정(결정 레지스터 O9)
```

요청자의 grounding된 topic 중 preference 점수 상위 `sections`개를 섹션으로, 섹션마다 agent `per_section`명. 응답의 각 섹션에 `next_cursor`가 있고, 더 보기는 아래 route다.

```
GET /discover/by-topic/{topic_id}?limit=20&cursor=…&lang=ko
```

`topic_id`는 요청자가 가진 topic이어야 한다. 아니면 404(요청자의 topic 목록에 없음). 요청자 자신의 topic 목록을 어디서 읽는지(요청 시 topic-api 조회 vs 우리 미러)는 미정이다(결정 레지스터 O2). 어느 쪽이든 타인의 topic은 §5 규칙으로만 읽는다.

### 2-3. 타입 ③ `GET /discover/for-you`

```
GET /discover/for-you?limit=20&cursor=…&lang=ko
```

입력은 요청자 id뿐이다. persona·topic·로그는 서버가 이미 갖고 있다.

**가정**: 요청자가 이미 대화를 시작한 agent는 for-you에서 제외한다(제품이 다르게 정하면 바꾼다). 합성 정답도 같은 가정을 쓴다.

**사전 계산이 없는 요청자**(항목이 아직 없는 유저 — 대화 0건, 또는 첫 대화 뒤 첫 스윕 전 — R19): 인기도와 content 소스만으로 `limit`을 채운 **완전한 목록**을 답한다. `basis`가 `popularity` 또는 `content`가 되고, `degraded`는 비어 있다. 첫 대화 이벤트 뒤 워커 스윕이 첫 항목을 만든다.

**사전 계산이 오래된 요청자**(R19): 있는 항목을 그대로 쓴다. 응답 직전 재확인(§5 불변식 4)과 이미 대화한 상대 제외가 그 사이의 변화를 걸러내고, 이 요청이 `agents.last_active_at`을 갱신해 다음 스윕이 항목을 새로 만든다. `cf_candidates_stale`는 §3-4의 임계를 넘겼을 때만 붙는다.

### 2-3-1. ②③의 내부 미러

`GET /api/internal/svc/agent-discovery/users/{user_id}/discover/by-topic`, `…/by-topic/{topic_id}`, `…/for-you`. 요청자가 경로의 `user_id`라는 것만 다르고 쿼리·응답은 같다.

### 2-4. 공통 규칙

- `lang`은 topic 라벨의 언어 힌트다. 응답은 항상 `ko`, `en` 두 키를 주고 없으면 null이다.
- 페이지네이션은 opaque `cursor`다. 오프셋을 노출하지 않는다(사전 계산 결과가 갈아엎어지면 오프셋은 의미가 없다). `recommendation_id`는 **목록 하나**(첫 페이지)에 발급되고 `cursor`가 그것을 실어 오므로 다음 페이지는 같은 id·같은 seed(R20)로 순서를 잇는다. 그 사이 사전 계산이 갱신될 수 있어(R19) 페이지 연속성은 best-effort다.
- 요청자 본인의 agent는 어느 타입에서도 결과에 없다.

---

## 3. 응답

### 3-1. 공통 요소 `RecommendedAgent`

```json
{
  "agent_id": "uuid",              // personal agent id
  "owner_user_id": "uuid",         // agent 소유자. agent_id에서 유도되지만 클라이언트가 유도하지 않게 준다
  "position": 1,                   // 이 응답 안의 순위 (1부터). 페이지가 이어져도 계속 증가
  "matched_topics": [              // 이 agent가 여기 있게 만든 topic들
    {
      "topic_id": "…",
      "labels": {"ko": "캠핑", "en": "Camping"},
      "requested": true,           // 타입 ①: 뽑힌 topic 중 하나인가. 타입 ②: 섹션 topic이면 true
      "owner_note": {"ko": "…", "en": null}   // 소유자가 그 topic에 쓴 한 문장(topic-api 유저 topic의 descriptions). 응답 직전 hydration으로 채움. 선택, null 가능
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

`owner_note`는 소유자가 쓴 글이다. **응답에 싣는 것으로 끝이다.** 로그, 예외, 결정 로그, Sentry에 들어가지 않는다.

### 3-2. 타입별 envelope

**① `POST /recommend/explicit` → 200**

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "resolved_topics": [ {"topic_id": "…", "labels": {…}} ],   // free text에서 확정된 topic, 1~3개, 커버리지의 분모
  "agents": [ RecommendedAgent… ],                            // 커버리지 내림차순, 같은 커버리지 안에서 점수순
  "empty": false,                // agents가 비었으면 true. 이유는 싣지 않는다 — "있었지만 가려졌다"는 §5 불변식 5 위반
  "degraded": []                 // 아래 §3-4
}
```

**② `GET /discover/by-topic` → 200**

```json
{
  "contract_version": 1,
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

섹션이 비면(그 topic을 공개한 타인이 없음) 섹션은 `agents: []`로 남긴다. 섹션이 아예 없으면(요청자가 topic이 없음) `sections: []`.

**③ `GET /discover/for-you` → 200**

```json
{
  "contract_version": 1,
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
| 200 + 빈 목록 | 요청자에게 보일 수 있는 agent가 없다. "없다"와 "있지만 가려졌다"를 구분하는 값은 없다(§5-5) | 모두 (①은 `empty: true`, ②는 빈 `agents`, ③은 빈 `agents`) |
| 403 | 클라이언트 API에서 `x-user-id` 없음/비정상 | ②③ |
| 404 | `by-topic/{topic_id}`의 topic이 요청자 것이 아님 | ② |
| 422 | `topic_text`에서 확정된 topic이 0개 (요청이 모호함) | ① |
| 503 | topic 확정을 시도하지 못했다(LLM·topic-api 무응답), 또는 저장소 무응답 | 모두 |

422와 503의 구분은 **어디서 멈췄나로** 결정되고, 나중에 상태만 보고 추정하지 않는다. "봤는데 없다"가 422, "못 봤다"가 503이다.

### 3-4. `degraded`

응답이 완전하지 않지만 답할 수 있을 때. 값은 요청자 개인이나 특정 소유자에 관한 사실을 드러내지 않는 것만 허용한다.

| 값 | 뜻 |
|---|---|
| `friends_unavailable` | 친구 집합을 못 읽어 friends tier를 후보에서 뺐다. public만 답했다. R17·R18 배치에서는 실제로 나오지 않는 예약 값이다 — §5 불변식 3 |
| `expansion_partial` | 타입 ①: 개념 확장 일부가 답을 못 받아 topic이 덜 뽑혔을 수 있다 |
| `hydration_partial` | 라벨·owner_note를 다 못 채웠다 |
| `cf_candidates_stale` | 타입 ③: 사전 계산 결과가 **있는데** TTL의 몇 배(O13, 예 7일) 이상 오래됐다. TTL을 넘긴 정도는 정상 경로(그대로 서빙하고 스윕이 갱신, R19)라 붙이지 않는다. 항목이 없어서 인기도·content로 답한 경우는 이 값이 아니다 — `basis`가 그것을 말한다 |

"몇 개가 가려졌다"는 어떤 형태로도 응답에 없다(§5).

---

## 4. 도메인 인터페이스 — A안과 B안이 갈아 끼우는 자리

```
요청 ─▶ QueryBuilder ─▶ CandidateSource들 ─▶ VisibilityFilter ─▶ Ranker ─▶ Assembler ─▶ 응답
        타입별          A/B가 다름          공통                 공통      공통
```

### 4-1. 쿼리

```python
@dataclass(frozen=True)
class TopicQuery:            # 타입 ①(topic 1~3개), 타입 ②(topic 1개)
    requester: UUID
    topic_ids: tuple[str, ...]
    limit: int
    cursor: str | None = None   # 타입 ②의 섹션 페이지. 타입 ①은 None

@dataclass(frozen=True)
class UserQuery:             # 타입 ③
    requester: UUID
    limit: int
    cursor: str | None
```

타입 ①의 QueryBuilder는 free text → 개념 확장 → topic-api 검색 → topic 확정(기존 코드 `agent_discovery/stages/`의 확장·확정 단계)이고, 결과가 `TopicQuery`다. 타입 ②의 QueryBuilder는 요청자의 topic 목록을 읽어 topic마다 `TopicQuery` 하나를 만든다. 타입 ③은 `UserQuery` 그대로다.

### 4-2. 후보 소스

```python
@dataclass(frozen=True)
class SourceHit:
    owner_user_id: UUID
    tier: Literal["public", "friends"] | None   # 이 hit이 근거한 row의 tier. 모르는 소스는 None → 필터가 채우거나 버린다
    topic_id: str | None                 # topic 근거가 있으면. CF/인기도 hit은 None
    source: str                          # "topic_index" | "popularity" | "content_similarity" | "cf_item" | "cf_engine" …
    score: float                         # 소스 안에서만 비교 가능한 값
    evidence: Mapping[str, float]        # 랭커 feature 재료 (예: topic_score, topic_maturity, co_count)

class CandidateSource(Protocol):
    name: str
    async def candidates(self, query: TopicQuery | UserQuery) -> Sequence[SourceHit]: ...
```

- **공개된 row 저장소를 읽는 소스는 visibility 술어를 쿼리 안에 넣는다**(R17): `tier = 'public' OR (tier = 'friends' AND owner_user_id = ANY(friends(요청자)))`. `topic_index`, `content_similarity`, PostgreSQL `popularity`, B안 이웃 테이블이 여기 든다. 결과는 tier가 이미 붙어 있고 필터에서 빠지는 것이 없으므로 **`limit`만큼만(응답 직전 재확인에서 빠질 몫만 여유를 두고) 읽는다.** 친구 집합은 미러(§6 `friends`)에서 배열로 넘기거나 조인한다.
- **요청자별 사전 계산**(`cf_item`, 라이브러리형 `cf_engine`의 배치)은 배치 시점의 요청자 친구 집합으로 같은 술어를 적용해 top-K를 뽑는다. 그래도 스냅샷이므로 응답 직전 재확인(§5 불변식 4)은 남는다.
- **tier를 모르는 소스만 넉넉히 반환한다**(예: 3배): 외부 엔진(Gorse)이 준 agent 목록처럼 술어를 넣을 수 없는 곳. 뒤의 필터가 공개된 row 저장소에서 tier를 조회해 붙이고, row가 없으면 버리고, 부족하면 파이프라인이 한 번 더 요청한다. 이 재요청 비용은 그 소스의 비용으로 비교(재설계 §6)에 기록한다. 엔진 결과는 후보를 좁힐 뿐 노출을 허가하지 못한다.
- 한 타입이 소스 여러 개를 쓸 수 있다. 타입 ③은 `popularity + content_similarity + cf_*`.
- A안은 `cf_engine`(Gorse 등)과 `topic_index`(OpenSearch 또는 B의 인덱스), B안은 `topic_index`, `popularity`, `content_similarity`, `cf_item`을 구현한다. 혼합은 소스 조합 설정이다.

### 4-3. visibility 필터

```python
class VisibilityFilter(Protocol):
    async def allow(self, requester: UUID, hits: Sequence[SourceHit]) -> tuple[Sequence[SourceHit], Degradation]: ...

Degradation = frozenset[str]   # §3-4의 값 집합. 비어 있으면 완전한 답
```

규칙은 §5. 구현은 하나다. 두 안이 공유하고, 비교에서 같은 코드를 쓴다. 역할은 둘이다: 술어를 이미 적용한 hit(`tier`가 있음)은 그대로 통과시키고, `tier = None`인 hit에는 `visible_topic_rows`를 소유자 키로 조회해 tier를 붙이며(friends row는 요청자가 친구일 때만) row가 없으면 버린다. 친구 집합을 읽지 못한 요청의 처리는 §5 불변식 3.

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

**타입 ③은 정렬 뒤 점수 구간 안에서만 섞는다**(R20). 구간 경계는 설정(예 상위 5·다음 15·다음 30), seed는 `recommendation_id`. `cursor`가 첫 페이지의 `recommendation_id`를 실어 오므로 다음 페이지도 같은 seed로 순서를 잇는다(§2-4, best-effort). 결정 로그는 `ranked`에 섞기 **전** 순서를, `shuffle`에 seed와 구간 경계를 남겨 서빙 순서를 재현한다. 타입 ①②는 섞지 않는다.

### 4-5. 응답 조립

`RecommendedAgent`를 만들고 라벨·owner_note를 채운다(hydration). hydration은 응답 직전이고 실패하면 `hydration_partial`. **응답 직전에 공개된 row가 존재하는지 다시 확인**한다(§5 불변식 4).

---

## 5. 불변식 — 두 안 모두, 언제나

1. **저장소에는 공개된 row만 있다.** `(topic_id, owner, tier ∈ {public, friends})`. private·hidden은 들어오지 않고, 비공개로 되돌리면 지운다. agent가 private이면 그 소유자의 row 전부를 지운다.
2. **friends row는 요청자가 소유자의 친구일 때만 통과한다.** 기준은 bourbon-api이고, 판정은 `bourbon.friendship_changed`로 미러한 친구 집합으로 후보 조회 쿼리 안에서 한다(R17).
3. **친구 집합을 못 읽으면 friends tier는 빠진다(fail-closed).** 응답은 `degraded: ["friends_unavailable"]`, 상태는 200. R17·R18 배치에서는 친구 집합이 `visible_topic_rows`와 같은 PostgreSQL에 있어 "row는 읽었는데 친구 집합만 못 읽는" 경우가 없고 그 장애는 503이다. 이 항은 계약에 예약된 규칙으로 남긴다 — 친구 집합을 다른 저장소로 옮기는 날 다시 살아난다.
4. **사전 계산 결과는 노출을 허가하지 않는다.** 응답 직전에 현재 공개된 row로 다시 거른다.
5. **응답은 "가려짐"과 "없음"을 구별하지 못한다.** 가려진 개수, 표시, 순위 공백이 없다.
6. **요청자 본인은 결과에 없다.**
7. **유저의 글(topic_text, context, owner_note)은 로그·예외·Sentry에 원문으로 실리지 않는다.** 결정 로그에도 없다.
8. **상태 코드는 멈춘 지점에서 결정된다.** 422 = 봤는데 없다, 503 = 못 봤다.

---

## 6. 공개된 row 저장 모델 — 모양은 저장소 무관, 배치는 R18

두 안이 공유하는 최소 모델. 모양은 저장소와 무관하고, 배치는 R18이다: **조인·집계가 있는 집합은 PostgreSQL, 단건 키 읽기·쓰기만 있는 집합은 DynamoDB, Redis는 deferq만.** 아래 표에서 `cf_candidates`만 DynamoDB이고 나머지는 전부 PostgreSQL이다. `requester_topics`는 O2가 (b) 미러일 때만 생기는 집합이고, 그때는 단건 키 집합이라 R18 규칙으로 DynamoDB다.

| 집합 | 키 | 값 | 갱신 |
|---|---|---|---|
| `visible_topic_rows` | `(topic_id, tier, owner_user_id)` | `topic_score`(소유자 쪽 preference 강도), `topic_maturity`, `updated_at` | topic 변경 이벤트. 비공개 전환 = 삭제 |
| `visible_topic_rows` 보조 인덱스 | `owner_user_id` | → 그 소유자의 row들 | agent private 시 일괄 삭제용 |
| `agents` | `owner_user_id` | `agent_id`, `discoverable`, `agent_maturity`, `registered_at`, `updated_at`, **`last_active_at`**(R19) | `bourbon.user_registered`로 생성(추천 대상 풀), 공개 여부·성숙도 이벤트로 갱신, `bourbon.user_deactivated`로 삭제. 없는 채로 topic 이벤트가 오면 재조회가 만든다. `last_active_at`은 우리 API 요청·`agent_dm_opened`의 actor·`topics_updated` 셋 중 어느 것이든 갱신한다. **`cf_candidates_computed_at`**(R19)은 그 유저의 top-K를 마지막으로 만든 시각 — 스윕 조건 `last_active_at > cf_candidates_computed_at`의 오른쪽 |
| `requester_topics` (**O2 대기**) | `user_id` | 요청자 자신의 topic 목록(점수 포함). 타입 ②의 섹션과 타입 ③의 content 쿼리에 씀 | 두 안: (a) 미러하지 않고 요청 시 topic-api 내부 route로 읽는다(권고), (b) 미러하되 소유자 키 아래에만 두고 후보 조회에는 쓰지 않는다. 결정 레지스터 O2 |
| `friends` (**R17: 미러, 필수**) | canonical pair `(user_low, user_high)`. 조회는 `user_id` → 친구 id 집합(상한 5,000) | — | `bourbon.friendship_changed`: `accepted` → 삽입, `removed` → 삭제. 요청 시 bourbon-api 조회·TTL 캐시는 쓰지 않는다. `visible_topic_rows`와 같은 저장소에 두어 후보 조회 쿼리가 배열로 받거나 조인한다 |
| `popularity` | `owner_user_id` | 시간 감쇠 카운트 | 대화 시작 이벤트 |
| `cf_candidates` | `user_id` | `candidates: [(owner_user_id, score)]` top-K, `computed_at`, `model_version`(어느 전역 학습으로 만들었나 — 재현·갱신 판단용) | 워커의 주기 스윕이 배치로 쓴다 — 조건은 R19. K는 100~200(R20의 pool). **DynamoDB**(PK `user_id`, R18, **TTL 없음**): 서빙은 단건 GetItem, 조인은 없다(재확인은 PostgreSQL `visible_topic_rows`에서). 오래된 항목도 그대로 서빙한다. 항목이 없는 요청자는 §2-3의 콜드스타트 경로 |
| `interactions` | `(actor_user_id, owner_user_id, room_id)` | `started_at`, `reopened_count`, `turns`, `entry`, `recommendation_id` | `agent_dm_opened`로 생성, `message_created`(room_id 조인)로 `turns` 증가. CF 학습 입력 |

타입 ①②의 조회는 `visible_topic_rows[topic_id, public]` ∪ (`visible_topic_rows[topic_id, friends]` ∩ friends(요청자)) 이고, 타입 ①은 topic ≤ 3개의 결과를 owner로 합쳐 커버리지를 센다. 이 합집합은 쿼리 하나의 WHERE 절이다(§4-2, R17). 타입 ③의 `popularity`·`content_similarity`·이웃 조회도 같은 술어를 `visible_topic_rows`에 대한 조인(또는 EXISTS)으로 붙여 요청자에게 보이는 소유자만 읽는다. 엔진(A안)이 자기 저장소를 따로 가져도 위 집합은 그대로 있어야 한다. 불변식 1·4가 여기서 판정되기 때문이다.

---

## 7. 랭커 feature

| feature | 정의 | 범위 | 출처 | 타입 |
|---|---|---|---|---|
| `coverage` | 뽑힌 topic 중 가진 수 | 0~3 | topic_index | ① (1차 정렬 키) |
| `topic_score` | 소유자 쪽 preference 강도, matched topic 합 또는 최대 | 0~1 | visible_topic_rows | ①② |
| `topic_maturity` | matched topic 성숙도 최대 | 0~1 | visible_topic_rows (임시값 → 컴포넌트) | ①②③ |
| `agent_maturity` | agent 성숙도 | 0~1 | agents | ①②③ |
| `popularity` | 정의는 미정(결정 레지스터 O4). 첫 구현 플레이스홀더: 최근 N일 대화 시작 수, 시간 감쇠, 전체 최대로 정규화 | 0~1 | popularity | ③ (①②는 약한 가중) |
| `content_similarity` | 요청자 topic 집합과 소유자 topic 집합의 가중 겹침 | 0~1 | requester_topics × visible_topic_rows | ③ |
| `cf_score` | 아이템 이웃 또는 행렬 분해 점수, 소스 안에서 정규화. **학습 입력의 confidence는 "대화 시작 1회"가 아니라 `1 + α·log(1 + turns) + β·reopen_count`** — 배우는 대화(길고 다시 찾는 대화)가 한 번 시작하고 끝난 대화보다 강한 신호다(오너 2026-09-08, 결정 레지스터 R16). α·β는 설정. 가중을 켜는 시점은 O14 | 0~1 | cf_item / cf_engine (입력: `interactions` + turn 카운터) | ③ |
| `similar_users` | 이 agent와 대화한 유사 유저 수 | 정수 | cf_item | ③ (표시용) |
| `recency` | 소유자의 마지막 topic 갱신이 얼마나 최근인가 | 0~1 | visible_topic_rows.updated_at | 모두, 작은 가중. 오래 활동하지 않은 소유자를 **후보에서 빼지 않고** 이 feature로 내린다(R19). 하드 제외는 O17 |
| `tier_is_friends` | 근거 row가 friends tier인가 | 0/1 | 필터 결과 | 모두. 친구를 살짝 올릴지는 제품 판단 |

없는 feature는 0이고 `present`에 없다. 가중치는 설정이며 비교(재설계 §6)에서는 두 안이 같은 가중치를 쓴다.

---

## 8. 결정 로그

목록마다 한 건 — 첫 페이지에 발급된 `recommendation_id`가 PK고, 다음 페이지 요청은 같은 항목에 `pages[]`로 덧붙인다(§2-4). 오프라인 평가와 A/B 비교의 정답 로그다. **유저의 글은 없다.** 저장은 **DynamoDB**(R18): PK `recommendation_id`(대화 시작 이벤트의 `recommendation_id`가 단건으로 찾아온다), 평가 배치가 기간·타입별로 읽도록 GSI `(type, served_day)`, 보존은 TTL. 집계는 SQL이 아니라 평가 배치의 코드다.

```json
{
  "recommendation_id": "uuid",
  "type": "recommend_explicit" | "discover_by_topic" | "discover_for_you",   // agent_dm_opened.entry와 같은 값 집합
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
  "ranked": [ {"owner_user_id": "uuid", "position": 1, "features": {…}, "score": 0.83} ],   // 섞기 전(랭커) 순서. 서빙 순서는 shuffle로 재현
  "basis": "content",                             // ③
  "cf_model_version": "fit-2026-09-08T03Z",       // ③ 어느 cf_candidates 스냅샷으로 답했나
  "shuffle": {"seed": "rec-…", "bands": [5, 20, 50]},   // ③ R20. bands = 구간의 누적 상한(1~5, 6~20, 21~50). 구간 안 순서를 재현하는 재료
  "latency_ms": {"query": 640, "sources": 9, "filter": 3, "rank": 1, "assemble": 12, "total": 665},
  "served_at": "2026-09-08T…Z"
}
```

`filter.out`은 로그에만 있다. 응답에 실리면 불변식 5를 깬다.

---

## 9. 이벤트

### 9-1. 우리가 받는 것

| 이벤트 | 상태 | payload | 우리 처리 |
|---|---|---|---|
| `bourbon.friendship_changed` | **있음** (bourbon-api) | `user_low, user_high, action, occurred_at` | `friends` 미러 갱신: `accepted` 삽입, `removed` 삭제 (R17) |
| `bourbon.topics_updated` | **있음** (topic-api 워커, persona 동기화가 움직인 topic마다) | `user_id, topic_id, persona_revision, topic_revision` | 힌트. 유저 단위 debounce 뒤 내부 route `GET /users/{id}/topics?visibility=public&visibility=friends`(반복 파라미터)를 읽어 공개된 row를 통째로 교체. 상세 `agent_discovery_events.md` §2-1 |
| `bourbon.user_topic_settings_updated` | 우리가 정의, topic-api api 프로세스에 요청 (그 프로세스에 AMQP 연결 필요) | `user_id, topic_id, topic_revision, touched` | 같은 debounce → 같은 재조회. **비공개 전환은 이 경로로만 오므로 핵심**. §2-2 |
| `bourbon.personal_agent_visibility_changed` | 우리가 정의, bourbon-api에 요청 (`enabled` 재사용인지 새 필드인지 미정) | `owner_user_id, agent_id, discoverable, occurred_at` | `false` → 그 소유자 row 전부 삭제 |
| `bourbon.agent_maturity_changed` | 정의해 요청 (성숙도 컴포넌트, 예정) | `owner_user_id, maturity, maturity_version, occurred_at` | `agents` 갱신 |
| `bourbon.agent_dm_opened` | 우리가 정의, bourbon-api에 요청 (타인 agent와의 대화는 `AGENT_DM` room `A:B'`. `ensure_agent_dm_room`의 create·re-enter) | `room_id, actor_user_id, owner_user_id, agent_id, reopened, entry, recommendation_id?, occurred_at` | `interactions` 기록, `popularity` 증가. `recommendation_id`는 클라이언트가 대화 시작 요청에 실어야 온다 |
| `bourbon.message_created` | **있음** (bourbon-api) | `room_id, message_id, sender_id, sender_type, type, room_type` | `room_type == agent_dm`인 유저 메시지를 `room_id`로 `agent_dm_opened` 기록과 조인해 turn을 셈. 새 turn 이벤트 불필요 |
| `bourbon.user_registered` | **있음** (bourbon-api, 활성화 전이) | `user_id, email` | `agents` row 생성(`discoverable=false`). `email`은 읽지 않는다 |
| `bourbon.user_deactivated` | **있음** (bourbon-api) | `user_id` | 그 유저의 모든 데이터 삭제. `interactions`의 actor 쪽만 익명화 |

진행 방식은 우리가 먼저 미러·발행·테스트하고 그 뒤 요청한다. 재조회 tier 범위는 결정 레지스터 O2다.

### 9-2. 우리가 내는 것

지금은 없다. 결정 로그(§8)는 저장소에 쓰고 이벤트로는 내지 않는다. 다른 서비스가 "추천이 나갔다"를 알아야 할 때 그때 정의한다.

---

## 10. 버전과 호환

세 envelope 모두 `contract_version: 1`을 갖는다. 필드 추가는 같은 버전, 필드 의미 변경이나 삭제는 버전을 올린다. 비교 기간에 A·B가 같은 버전으로 답해야 하고, `implementation`은 결정 로그에만 있고 응답에는 없다.

---

## 11. 이 계약의 열린 항목

- `fit`의 내용(제품 미확정). 자리만 있다.
- `tier_is_friends`에 가중치를 줄지 (결정 레지스터 O12).
- 타입 ② 섹션 순서가 요청자 preference 점수인지 다른 기준인지. 지금은 preference.
- `cf_candidates`의 TTL·스윕 주기·사이클 상한과 `cf_candidates_stale` 임계 (결정 레지스터 O13). 모양은 R19.
