# 세 타입의 동작 흐름 — 예제 하나로 끝까지 따라가기

> `agent_discovery_redesign.md` §2·§5와 `agent_discovery_contract.md` §4~§9를 **한 요청이 들어와서 응답이 나갈 때까지** 순서대로 풀어 쓴 설명 문서다. 저장소(PostgreSQL / DynamoDB / MySQL / OpenSearch / Redis)에 어떤 row가 들어 있고, `implicit`·Gorse가 그 위에서 무엇을 읽고 무엇을 쓰는지를 같은 예제로 보인다.
>
> **R33·R34(2026-09-09) 이후 읽는 법**: 구현은 하나다 — 타입 ①②는 B안의 PostgreSQL 역인덱스, 타입 ③ CF는 A안 라이브러리형 `implicit` ALS(§5-3 첫 변형). Gorse 변형(§2-3, §5-3 서비스형)과 B안 동시 출현 CF(§5-3 B안)는 비교 설계 시점의 기록으로 남긴다. 본문의 "A안/B안"은 그 절이 어느 쪽 기록인지 가리킬 뿐이다.
>
> 새 결정은 없다. 결정은 `decisions.md`가 갖고, 이 문서는 그 결정과 계약이 실제로 어떻게 움직이는지를 그린다. 숫자·가중치·주기는 **예시값**이고, 미정인 것은 그 자리에서 열린 항목 번호(O…)를 단다. 실측 수치는 `library_verification.md`에서 가져왔다.

---

## 0. 예제 세계

문서 전체에서 같은 사람들을 쓴다. 이름은 읽기 위한 것이고 실제 id는 UUID다.

**요청자 R(민수)**. topic-api가 grounding해 둔 R의 topic과 preference 점수:

| topic | 점수 | visibility |
|---|---|---|
| `camping` | 0.9 | public |
| `hand_drip` | 0.7 | friends |
| `hiking` | 0.3 | private |

R의 친구: **B**, **F**. (C, D, E, G, H와는 친구가 아니다.)

**타인 agent의 소유자들**. agent id는 소유자 id에서 결정론적으로 나오므로 "agent A" = "A의 personal agent"다.

| 소유자 | topic → (visibility, 점수, 성숙도) | agent 공개 | R과 친구 | 비고 |
|---|---|---|---|---|
| **A** | `camping` (public .8 .7), `hand_drip` (public .9 .6) | public | 아니오 | 두 topic 다 공개 |
| **B** | `camping` (public .6 .5), `hand_drip` (**friends** .9 .9) | public | **예** | 커피는 친구에게만 |
| **C** | `camping` (**friends** .95 .9) | public | 아니오 | R에게는 안 보여야 함 |
| **D** | `camping` (private), `hand_drip` (private) | public | 아니오 | 전부 비공개 → 저장소에 row 없음 |
| **E** | `hiking` (public .8 .8) | public | 아니오 | topic은 안 겹치지만 **가장 인기** |
| **F** | `camping` (public .7 .4) | **private** | 예 | agent 비공개 → 저장소에 row 없음 |
| **G** | `photography` (public .9 .7) | public | 아니오 | R과 비슷한 사람들이 많이 찾은 agent |
| **H** | `board_game` (public .5 .3) | public | 아니오 | R이 최근 짧게 대화한 상대. topic은 R과 겹치지 않고 인기도도 낮다 |

R이 지금까지 대화를 시작한 상대: **A**(12 turn, 다시 방을 연 적 1회), **H**(2 turn).

---

## 1. 공통 뼈대 — 어느 안이든 이 순서로 움직인다

```
요청 ─▶ QueryBuilder ─▶ CandidateSource들 ─▶ VisibilityFilter ─▶ Ranker ─▶ Assembler ─▶ 응답 + 결정 로그
        타입별          A안/B안이 다른 곳     공통 (하나)          공통      공통
```

| 단계 | 하는 일 | A안과 B안 |
|---|---|---|
| QueryBuilder | 요청을 `TopicQuery`(타입 ①②) 또는 `UserQuery`(타입 ③)로 바꾼다 | 같다 |
| CandidateSource | 쿼리를 받아 `SourceHit(owner_user_id, tier, topic_id, source, score, evidence)` 목록을 낸다. PostgreSQL을 읽는 소스는 visibility 조건(`public ∨ friends∧친구`)를 쿼리 안에 넣어 `limit`만큼만 읽고, 조건을 넣을 수 없는 소스(외부 엔진)만 넉넉히(예: 3배) 낸다(R17) | **다르다.** 어떤 저장소를 읽고 어떤 라이브러리·엔진이 뒤에 있는지가 여기서 갈린다 |
| VisibilityFilter | 조건을 이미 적용한 hit(tier 있음)은 통과. tier가 없는 hit에는 공개된 row 저장소에서 tier를 붙이고, friends row는 요청자가 친구일 때만 통과시키고, row가 없으면 버린다 | 같다. 코드 하나를 두 안이 공유 |
| Ranker | feature 벡터 → 점수. 타입 ①은 `(coverage desc, score desc)`, ②③은 `score desc`. 타입 ③은 그 뒤 점수 구간 안에서만 섞는다(R20, seed = `recommendation_id`) | 같다. 가중치는 설정 레지스터 하나(R39) |
| Assembler | 라벨·owner_note를 채우고(hydration), **응답 직전에 공개된 row가 아직 있는지 다시 확인**하고, 결정 로그 한 건을 쓴다 | 같다 |

두 안이 아무리 달라도 **노출을 허가하는 저장소는 하나**다: 공개된 row 저장소 `visible_topic_rows`(계약 §6). 엔진이든 사전 계산이든 "이 agent를 보여줘도 되나"를 스스로 답하지 못하고, 이 저장소에 row가 있어야만 응답에 실린다.

---

## 2. 저장소에 무엇이 들어 있나 — 예제 세계를 row로

### 2-1. 두 안이 공유하는 저장소 (계약 §6)

**`visible_topic_rows`** — 공개된 (topic, 소유자, tier) row만. B안은 PostgreSQL 테이블 하나에 `(topic_id, tier, owner_user_id)` B-tree 인덱스, 이것이 구현이다(R34). OpenSearch 인덱스(§2-3)는 검증 뒤 쓰지 않기로 한 기록이다 — 노출을 허가하는 저장소는 이 테이블 하나다.

| topic_id | tier | owner_user_id | topic_score | topic_maturity | updated_at |
|---|---|---|---|---|---|
| camping | public | A | .8 | .7 | … |
| hand_drip | public | A | .9 | .6 | … |
| camping | public | B | .6 | .5 | … |
| hand_drip | friends | B | .9 | .9 | … |
| camping | friends | C | .95 | .9 | … |
| hiking | public | E | .8 | .8 | … |
| photography | public | G | .9 | .7 | … |
| board_game | public | H | .5 | .3 | … |

D의 row는 없다(전부 private). F의 row도 없다(agent가 private이면 소유자 row 전부 삭제). 이 두 "없음"이 불변식 1이다. R 자신의 `camping`(public)·`hand_drip`(friends) row도 실제로는 있다(다른 사람이 R을 찾을 때 쓰인다) — 위 표는 R의 요청에 관여하는 row만 적었고, R의 요청에서 본인은 제외다.

**`agents`** — 추천 대상 풀. `bourbon.user_registered`가 만들고(`discoverable=false`로 시작), 공개 여부·성숙도 이벤트가 갱신한다. `last_active_at`(R19)은 그 유저가 우리 API를 호출했을 때, 대화를 시작했을 때(그 방의 첫 `message_created`, R51), `topics_updated`가 왔을 때 갱신된다. `cf_candidates_computed_at`(R19)은 그 유저의 top-K를 마지막으로 만든 시각이다. R은 `cf_candidates_computed_at`이 9/05(H와의 대화 뒤 스윕)이고, 오늘 for-you 요청으로 `last_active_at`이 갱신됐으니 TTL 조건으로 다음 스윕의 갱신 대상이다.

| owner_user_id | agent_id | discoverable | agent_maturity | last_active_at | cf_candidates_computed_at |
|---|---|---|---|---|---|
| A | agent(A) | true | .6 | … | … |
| B | agent(B) | true | .8 | … | … |
| … | | | | | |
| F | agent(F) | **false** | .3 | … | … |
| R | agent(R) | true | .5 | 오늘 (for-you 요청) | 9/05 |

**`friends`** — `bourbon.friendship_changed`로 미러한다(R17). 저장은 canonical pair `(user_low, user_high)`, 조회는 요청자의 친구 집합 `R → {B, F}`(상한 5,000). `visible_topic_rows`와 같은 PostgreSQL에 두어 후보 조회 쿼리가 이 집합을 배열로 받거나 조인한다. 요청 시 bourbon-api 조회는 하지 않는다.

**`interactions`** — CF와 인기도의 원천. **그 방의 첫 `bourbon.message_created`** 가 row를 만들고(R51 — 소유자는 추천 시점에 계산해 둔 room id로 찾는다), `attributions`(R47 — 클라이언트가 카드에서 우리 route에 보고한 것)가 `entry`·`recommendation_id`를 채우고, `bourbon.message_created`(`room_type = agent_dm`, 유저 메시지)가 `room_turns[room_id]`를 올린다 — 순서 문제를 피하려고 카운터는 방 키로 따로 두고 읽을 때 조인한다(R49). 아래 표의 `turns` 열은 그 조인 결과다.

| actor_user_id | owner_user_id | room_id | started_at | turns | entry | recommendation_id |
|---|---|---|---|---|---|---|
| R | A | room-1 | 9/01 | 12 | discover_by_topic | rec-… |
| R | H | room-2 | 9/05 | 2 | direct | null |
| (다른 유저들) | … | | | | | |

**`popularity`** — 소유자별 시간 감쇠 카운트. 정의는 R29(최근 30일 대화 시작, 반감기 7일 감쇠, confidence 가중, 신규 agent 부스트)이고 아래 숫자는 예시다. PostgreSQL 테이블 하나다(R17·R18) — `visible_topic_rows`와 같은 DB여야 visibility 조건을 조인으로 붙일 수 있다.

| owner | 감쇠 카운트 | 정규화(전체 최대로 나눔) |
|---|---|---|
| E | 412 | 1.00 |
| G | 260 | .63 |
| A | 90 | .22 |
| B | 15 | .04 |
| H | 3 | .01 |

**`cf_candidates`** — 타입 ③의 유저별 top-K 스냅샷. 배치가 쓰고 서빙이 읽는다. **DynamoDB**, `USER#{user_id}` / `CF_CANDIDATES`(R18, key space는 R44·계약 §6-1): 조인이 없는 단건 읽기·쓰기라 여기가 맞다. TTL은 두지 않는다 — 두면 돌아온 유저가 콜드스타트 경로로 밀린다. **전원을 매일 다시 만들지 않는다**(R19): 워커의 주기 스윕이 읽혔거나 활동한 유저 중 오래됐거나 새 대화가 있는 유저만 모아 배치로 다시 만든다(조건과 SQL은 §5-3). K는 100~200으로 넉넉히 둔다(R20의 pool). 유저당 K=200이면 항목이 12~13 KB(uuid 소유자 id 기준, 약 13 WRU)라 전원을 매일 다시 쓰면 10만 유저에 월 $50 안팎인데, R19로는 그날 읽혔거나 활동한 유저 몫만 쓴다. `computed_at`이 TTL의 몇 배(R36: 7일)를 넘겼을 때만 `cf_candidates_stale`.

```
PK user_id=R → {computed_at, model_version, candidates: [{owner_user_id: G, score: .81}, {owner_user_id: B, score: .44}, …]}
```

**결정 로그와 `event_log`** — 둘 다 DynamoDB(R18). 결정 로그는 `REC#{recommendation_id}` / `LOG`, 평가 배치가 날짜·타입으로 읽는 GSI `served-day-index`(파티션 키에 shard), TTL. `event_log`는 워커가 받은 이벤트 원본을 `EVT#{날짜}#{shard}` 아래 TTL 180일로(key space는 R44·계약 §6-1). 어느 쪽도 서빙이 읽지 않고 조인이 없다.

**`requester_topics`** — R 자신의 topic 목록(§0의 첫 표). 저장하지 않고 요청 시 topic-api 내부 route로 읽는다(R27). 타입 ②의 섹션과 타입 ③의 content 쿼리 입력이다.

### 2-2. row가 어떻게 들어오고 나가나 — 적재 경로

```
topic-api ──bourbon.topics_updated {user_id, topic_id, …}──▶ 워커
topic-api ──visibility 변경 신호 (요청 예정, 형태는 topic-api 선택 — R48)──▶ 워커
              │ user_id 단위 debounce (수 초, 상한 1분)
              ▼
     GET /api/internal/svc/topic/users/{id}/topics?visibility=public&visibility=friends
              │
              ▼
     그 유저의 visible_topic_rows를 통째로 교체 (없어진 row 삭제, 새 row upsert)

bourbon-api ──personal_agent_visibility_changed {discoverable:false}──▶ 그 소유자 row 전부 삭제, agents.discoverable=false
클라이언트 ──POST /attributions {recommendation_id, owner_user_id, entry}──▶ attributions insert (R47)
bourbon-api ──message_created {room_id, sender_id, room_type=agent_dm}──▶ room_turns +1, 첫 turn이면 ROOM#{room_id} 조회 ──▶ interactions insert (attributions와 (actor, owner)로 조인), popularity 증가
bourbon-api ──message_created {room_id, room_type=agent_dm, sender_type=user}──▶ interactions.turns += 1
bourbon-api ──friendship_changed {user_low, user_high, action}──▶ friends 미러 갱신 (accepted 삽입 / removed 삭제)
bourbon-api ──user_registered {user_id}──▶ agents row 생성 (email은 읽지 않음)
```

예: B가 `hand_drip`를 friends → private로 되돌리면, topic-api api 프로세스가 visibility 변경 신호를 내고(요청 예정, R48), 워커가 B의 공개된 집합을 재조회해 `(hand_drip, friends, B)` row를 **지운다**. 갱신이 아니라 삭제다. 이벤트를 놓쳤다면 B의 다음 힌트에서 재조회가 고친다.

### 2-3. A안만 갖는 저장소 (기록 — OpenSearch·Gorse는 R33·R34로 쓰지 않는다)

**OpenSearch (타입 ①②를 OpenSearch로 할 때).** 소유자 하나가 문서 하나, 공개된 row가 nested 항목. §2-1의 표를 그대로 옮긴 모양이다.

```json
{ "owner": "B", "rows": [
    {"topic_id": "camping",   "tier": "public",  "w": 1.198},
    {"topic_id": "hand_drip", "tier": "friends", "w": 1.297} ] }
```

`w = 1 + 0.33·topic_score`처럼 **[1, 1 + 1/3) 안**에 가둔다. topic k개가 매칭되면 점수가 [k, k+1)에 갇혀 커버리지가 먼저 정렬된다(검증 §2-2의 함정). 검증 결과 같은 정답을 PostgreSQL이 3배 빠르게 내므로 타입 ①②는 PostgreSQL 인덱스로 간다(R34). 이 절은 그 판단의 기록이다.

**`implicit` (라이브러리형 CF).** 자기 저장소가 없다. 배치 프로세스가 `interactions`를 읽어 메모리에서 학습하고, 결과 top-K를 `cf_candidates`(DynamoDB, R18)에 BatchWriteItem으로 쓴다. 저장소에 남는 것은 그 top-K뿐이다. agent factor 행렬(10만 × 16 float, 6 MB)은 워커 프로세스 메모리에 들고 스윕 사이에 재사용하며, 다음 전역 학습이 갈아 끼우고 재시작 시 다시 fit한다(1~2 s라 영속화할 이유가 없다).

**Gorse (서비스형 CF).** 저장소 둘을 스스로 쓴다.

| Gorse가 쓰는 곳 | 무엇 | 우리 데이터의 대응 |
|---|---|---|
| data store (MySQL 또는 PostgreSQL) `users` | user_id, labels | 요청자·소유자 전원 |
| data store `items` | item_id, is_hidden, categories, labels, timestamp | **item = agent(소유자)**. categories는 우리 모양에 없어 `[]` |
| data store `feedback` | feedback_type, user_id, item_id, timestamp | `interactions` 한 row → feedback 한 row (type 예: `dm_opened`). turn 수·재방문은 feedback type을 나눠 실어야 한다 |
| cache store (MySQL 또는 PostgreSQL. **Redis는 Redis Stack 전용**이라 ElastiCache 불가) `documents` | collection(`recommend`, `collaborative-filtering`, `latest`, `popular` …), subset(=user_id), id(=item), score, categories, is_hidden | worker가 만든 유저별 추천 목록. 10만 유저면 약 1,400만 행 |

우리 저장소와 **이중으로** 든다. `interactions`는 우리 CF 학습·인기도·보정 통계에도 쓰이므로 Gorse에 넣었다고 없어지지 않는다.

---

## 3. 타입 ① — "캠핑하면서 핸드드립커피 잘 아는 agent 찾아줘"

호출자는 bourbon-agent, 내부 API `POST /api/internal/svc/agent-discovery/recommend/explicit`, 요청자는 body의 `user_id`.

```json
{ "user_id": "R", "topic_text": "캠핑하면서 핸드드립커피", "context": "…", "max_results": 3, "room_id": "room-9", "lang": "ko" }
```

### 3-1. QueryBuilder — free text → topic 1~3개 (A/B 같음)

1. LLM이 문장을 개념 묶음으로 나눈다: {캠핑}, {핸드드립 커피}.
2. 묶음마다 topic-api 내부 검색 `/search/topics`를 호출해 topic 하나로 확정한다: `camping`, `hand_drip`.
3. 셋을 넘으면 점수 상위 3개만 남긴다. 0개면 **422**(봤는데 없다), LLM·topic-api가 응답하지 않으면 **503**(못 봤다).

결과 `TopicQuery(requester=R, topic_ids=("camping", "hand_drip"), limit=3)`. `topic_text` 원문은 여기서 끝이고, 로그에는 sha256 앞 64비트 다이제스트만 남는다.

이 단계가 지연 시간의 대부분(수백 ms~수 초)이다. 뒤의 인덱스 조회는 수 ms다.

### 3-2. CandidateSource `topic_index`

**B안 — PostgreSQL 역인덱스.** 미러에서 읽은 친구 집합 `{B, F}`를 배열로 넘겨 visibility 판정을 쿼리 안에서 끝낸다(R17). 그래서 뒤의 필터에서 빠지는 것이 없고, `limit`보다 조금만 더 읽는다.

```sql
SELECT owner_user_id, count(*) AS coverage, sum(topic_score) AS s,
       array_agg(topic_id) AS matched, array_agg(tier) AS tiers
FROM visible_topic_rows
WHERE topic_id = ANY('{camping,hand_drip}') AND owner_user_id <> 'R'
  AND (tier = 'public' OR (tier = 'friends' AND owner_user_id = ANY('{B,F}')))
GROUP BY owner_user_id
ORDER BY coverage DESC, s DESC
LIMIT 4;            -- 조건이 WHERE에 있어 필터에서 빠지는 것이 없다. 여유 1은 응답 직전 재확인에서 빠질 몫
```

| owner | coverage | s | matched | 왜 이렇게 나오나 |
|---|---|---|---|---|
| **A** | 2 | 1.7 | camping, hand_drip | 둘 다 public |
| **B** | 2 | 1.5 | camping, hand_drip(friends) | R이 B의 친구라 friends row 통과 |
| (C) | — | — | — | `camping`이 friends인데 R은 친구가 아니다 → WHERE에서 빠짐 |
| (D, F) | — | — | — | row 자체가 없다 |

실측(10만 유저, 36만 row): p50 0.8 ms / p95 2.3 ms, friends 유출 0건, 커버리지 역전 0건.

**A안 — OpenSearch.** topic마다 nested 절 하나. 절 점수는 `function_score`로 그 row의 `w`로 **대체**하고, 상위 `bool.should`가 합산한다.

```
bool.should = [
  nested(rows): topic_id=camping   ∧ (tier=public ∨ (tier=friends ∧ owner ∈ {B,F})) → score = w
  nested(rows): topic_id=hand_drip ∧ (tier=public ∨ (tier=friends ∧ owner ∈ {B,F})) → score = w
]
```

A = 1.264 + 1.297 = 2.561, B = 1.198 + 1.297 = 2.495 — 둘 다 [2, 3) 안이라 topic 하나만 가진 agent(최대 1.33)를 앞선다. E·G는 매칭 없음. 순서는 PostgreSQL과 같다(정답 겹침 1.000). p50 2.3 ms / p95 3.9 ms. 클라이언트에 `Accept-Encoding: gzip`을 고정해야 한다(zstd 함정, 검증 §2-3).

### 3-3. VisibilityFilter

SQL이 tier 판정을 이미 끝냈으므로(hit마다 `tier`가 있다) 필터는 그대로 통과시킨다. 이 단계가 실제로 일하는 것은 tier를 모르는 hit(§5-4)뿐이다. 친구 집합이 `visible_topic_rows`와 같은 DB에 있으므로 "친구 집합은 못 읽었는데 row는 읽었다"는 상황은 없고, 그 DB가 죽으면 503이다(R17·R18). 계약의 `friends_unavailable`은 예약만 되어 있다 — 만약 그 값이 나오는 구성이라면 friends row를 **버리고**, B는 `camping`만 남아 coverage 1로 내려가고, 응답에는 "B의 커피가 가려졌다"는 어떤 흔적도 없다(불변식 5).

### 3-4. Ranker — 1차 키 커버리지, 2차 키 점수

계약 §7 feature로 2차 점수를 만든다. 가중치는 설정 레지스터(`rank.explicit.*`)이고 아래는 예시다.

```
score = 0.5·topic_score(합/2) + 0.2·topic_maturity(최대) + 0.2·agent_maturity + 0.1·popularity
A: 0.5·0.85 + 0.2·0.7 + 0.2·0.6 + 0.1·0.22 = 0.707
B: 0.5·0.75 + 0.2·0.9 + 0.2·0.8 + 0.1·0.04 = 0.719
```

정렬은 `(coverage desc, score desc)` → A와 B는 coverage가 같아 점수로 갈리고 **B가 1위**다. coverage 1인 agent가 있었다면 점수가 아무리 높아도 그 뒤다(R03).

### 3-5. Assembler — hydration, 재확인, 응답

1. topic 라벨과 소유자의 `owner_note`를 topic-api에서 채우고, 요청 `lang`(ko)의 문자열 하나로 내린다(R40). 실패하면 `hydration_partial`.
2. **응답 직전에 `visible_topic_rows`에 A·B의 근거 row가 아직 있는지 다시 본다.** 그 사이 B가 `hand_drip`를 비공개로 돌렸다면 B는 coverage 1로 떨어지거나 빠진다.
3. 결정 로그 한 건을 DynamoDB에 쓴다(R18). 원문 없음, `filter.out` 같은 개수는 로그에만.

```json
{
  "contract_version": 1, "recommendation_id": "rec-7f…",
  "resolved_topics": [{"topic_id": "camping", "label": "캠핑"},
                      {"topic_id": "hand_drip", "label": "핸드드립"}],
  "agents": [
    {"agent_id": "agent(B)", "owner_user_id": "B", "position": 1,
     "matched_topics": [{"topic_id": "camping", "requested": true, …}, {"topic_id": "hand_drip", "label": "핸드드립", "requested": true, "owner_note": "주말마다 캠핑장에서 내려요"}],
     "signals": {"coverage": 2, "topic_maturity": 0.9, "agent_maturity": 0.8, "popularity": 0.04, "similar_users": null}, "fit": null},
    {"agent_id": "agent(A)", "owner_user_id": "A", "position": 2, "matched_topics": […], "signals": {"coverage": 2, …}, "fit": null}
  ],
  "empty": false, "degraded": []
}
```

결정 로그(DynamoDB에만, PK `recommendation_id`):

```json
{"recommendation_id": "rec-7f…", "type": "recommend_explicit", "requester_user_id": "R", "implementation": "v1@3f9c…",
 "query": {"topic_text_digest": "a3f9…", "resolved_topic_ids": ["camping", "hand_drip"]},
 "sources": [{"name": "topic_index", "hits": 2, "latency_ms": 1}],
 "filter": {"in": 2, "out": 0, "friends_used": true, "degraded": []},
 "ranked": [{"owner_user_id": "B", "position": 1, "features": {"coverage": 2, "topic_score": 0.75, …}, "score": 0.719}, …],
 "latency_ms": {"query": 640, "sources": 1, "filter": 1, "rank": 0, "assemble": 12, "total": 654},
 "served_at": "2026-09-08T…Z"}
```

R이 이 응답에서 B의 agent와 대화를 시작하면 클라이언트가 `POST /attributions`에 `entry=recommend_explicit, recommendation_id=rec-7f…`를 보고하고(R47 — 타입 ①은 bourbon-agent 카드의 meta에서 읽는다), 이어 그 방의 첫 `message_created`가 오면 둘을 (R, B) 쌍으로 이어 `interactions`에 쌓인다(R51).

---

## 4. 타입 ② — 탐색 서브탭 "내 topic으로 대화해 볼 agent"

클라이언트가 직접 `GET /api/svc/agent-discovery/discover/by-topic?per_section=5&sections=3`. 요청자는 edge-auth가 채운 `x-user-id = R`. LLM도 topic-api 검색도 없다.

### 4-1. QueryBuilder — 요청자의 topic이 곧 섹션

R의 topic 목록을 요청 시 topic-api 내부 route로 읽는다(R27). preference 점수순으로 `sections`개: `camping`(.9), `hand_drip`(.7), `hiking`(.3). topic마다 `TopicQuery(requester=R, topic_ids=(topic,), limit=per_section)` 하나. R의 `hiking`이 private인 것은 상관없다 — 요청자 프로필은 본인의 `public`·`friends`·`private`을 읽고 `hidden`만 뺀다(R22). 이것은 "R이 무엇에 관심 있나"의 입력이고, 타인의 row만 계약 §5 규칙으로 읽는다.

### 4-2. CandidateSource — 타입 ①과 같은 인덱스, topic 하나씩

같은 SQL(또는 같은 OpenSearch 쿼리)을 `topic_id = ANY('{camping}')`처럼 topic 하나로 세 번 던진다. 커버리지는 항상 1이라 정렬은 점수만 본다.

| 섹션 | 후보 (필터 뒤) | 빠진 것 |
|---|---|---|
| `camping` | A(.8), B(.6) | C(friends, 친구 아님), D(private), F(agent private) |
| `hand_drip` | A(.9), B(.9, friends 통과) | D(private) |
| `hiking` | E(.8) | — |

같은 agent(A, B)가 두 섹션에 나오는 것은 정상이다(R04).

### 4-3. Ranker·Assembler

섹션 안에서 `score desc`(2차 점수식은 타입 ①과 같다). 섹션마다 `next_cursor`(opaque)를 붙이고, "더 보기"는 `GET /discover/by-topic/camping?cursor=…`가 같은 단일 topic 조회를 이어서 한다. `topic_id`가 R의 topic이 아니면 404.

```json
{ "contract_version": 1, "recommendation_id": "rec-8a…",
  "sections": [
    {"topic_id": "camping",   "label": "…", "agents": [A…, B…], "next_cursor": null},
    {"topic_id": "hand_drip", "label": "…", "agents": [B…, A…], "next_cursor": null},
    {"topic_id": "hiking",    "label": "…", "agents": [E…],     "next_cursor": null} ],
  "degraded": [] }
```

지연 시간은 인덱스 조회 × 섹션 수라 수십 ms 안이다. 섹션 크기·페이지는 R30(설정 레지스터 `by_topic.*`).

**A안과 B안의 차이는 타입 ①과 똑같다** — 인덱스가 PostgreSQL이냐 OpenSearch냐 하나뿐이고, 검증 결과 PostgreSQL이 낫다. 타입 ②에는 엔진(Gorse/`implicit`)이 등장하지 않는다.

---

## 5. 타입 ③ — 탐색 메인 "비슷한 사람들이 좋아한, 내가 좋아할 agent"

클라이언트가 `GET /api/svc/agent-discovery/discover/for-you?limit=20`. 입력은 요청자 id뿐: `UserQuery(requester=R, limit=20)`. 여기가 A안과 B안이 **가장 다른** 곳이고, 소스가 셋이다.

```
UserQuery(R) ─▶ popularity ─┐
             ─▶ content_similarity ─┼─▶ 합쳐서 VisibilityFilter ─▶ Ranker(가중 합) ─▶ Assembler
             ─▶ cf_item | cf_engine ─┘         (조건을 못 넣은 hit에만 tier 붙이기)
```

인기도 → content → CF는 대체가 아니라 **누적**이다(재설계 §2-3). 신호가 없는 feature는 0이 되고 랭커 하나가 순서를 정한다. 응답의 `basis`는 그 응답을 주로 만든 신호를 말한다.

### 5-1. 소스 1 `popularity` — 로그가 거의 없을 때부터 답이 나온다 (A/B 같음)

§2-1의 `popularity`(PostgreSQL 테이블, 정의는 R29)를 점수순으로 읽는다: E(1.00), G(.63), A(.22), B(.04), H(.01). 타입 ①②와 같은 조건을 EXISTS로 붙여 **R에게 보이는 소유자만** 읽는다(R17). 필터에서 빠지는 것이 없으니 `limit`만큼만 읽는다.

```sql
SELECT p.owner_user_id, p.score
FROM popularity p
WHERE p.owner_user_id <> 'R'
  AND EXISTS (SELECT 1 FROM visible_topic_rows r
              WHERE r.owner_user_id = p.owner_user_id
                AND (r.tier = 'public' OR (r.tier = 'friends' AND r.owner_user_id = ANY('{B,F}'))))
ORDER BY p.score DESC LIMIT 20;
```

F(agent private, row 없음)와 C(friends row만, 친구 아님)는 여기서 이미 나오지 않는다. hit에는 `tier`가 붙어 나간다. Redis sorted set에 두지 않는 이유가 이것이다(R18): sorted set은 tier를 모르고 조건을 붙일 수 없어 넉넉히 읽고 뒤에서 걸러야 한다.

### 5-2. 소스 2 `content_similarity` — 내 topic과 겹치는 소유자 (A/B 같음)

R의 topic 집합(`camping` .9, `hand_drip` .7, `hiking` .3)과 `visible_topic_rows`의 가중 겹침. 타입 ①②와 같은 인덱스를 R의 topic 전부로 한 번 읽는다.

```sql
SELECT owner_user_id, sum(req.w * r.topic_score) AS sim, array_agg(r.topic_id) AS matched
FROM visible_topic_rows r JOIN (VALUES ('camping',.9),('hand_drip',.7),('hiking',.3)) AS req(topic_id, w) USING (topic_id)
WHERE owner_user_id <> 'R' AND (tier='public' OR (tier='friends' AND owner_user_id = ANY('{B,F}')))
GROUP BY owner_user_id ORDER BY sim DESC LIMIT 20;
```

| owner | sim | 근거 |
|---|---|---|
| A | .9·.8 + .7·.9 = 1.35 | 두 topic 겹침 |
| B | .9·.6 + .7·.9 = 1.17 | friends row 통과 |
| E | .3·.8 = 0.24 | hiking만 |
| G | — | 겹침 없음(JOIN이라 행이 나오지 않는다. 랭커에서 content 0) |

이 소스는 tier를 안다(row에서 나왔다). 조건이 WHERE에 있어 C·D·F는 나오지 않고, 필터에서 빠지는 것도 없다.

위 SQL은 topic id 정확 일치의 가중 합이다. R25의 정의로는 둘이 바뀐다: `camping`처럼 흔한 topic의 겹침은 IDF로 낮아지고, `hand_drip`의 부모 `coffee`만 가진 소유자도 0.6 배로 잡힌다(카탈로그 계층 감쇠 — topic-api 검색 설정에서 빌린 상수, 거리는 양방향 최단 hop. 카탈로그 edge는 topic-api의 `catalog.json`을 빌드 때 복사해 채운다, R26). R25는 임베딩 kNN을 넣지 않고, "R이 대화한 agent들의 topic을 R의 프로필에 더하는" 경로도 넣지 않는다 — R이 H의 agent 방에서 한 말은 bourbon-agent가 R의 persona로 추출해 topic-api → `topics_updated` → §2-2 적재 경로로 R의 topic에 이미 들어오고, agent의 발화를 R의 취향으로 세는 것은 추출기가 금지한 추론이다. 행동 신호는 §5-3 CF의 몫이다.

### 5-3. 소스 3 CF — "비슷한 사람들이 좋아한". 여기서 A안과 B안이 갈린다

CF의 입력은 어느 안이든 `interactions`이고, 학습 신호는 "대화를 시작했다" 1회가 아니라 confidence다(R16):

```
confidence = 1 + α·log(1 + turns)        (α는 설정. 예시 α=1. 재방문 항은 R46으로 제외 — 이벤트로 받지 않는다)
R–A: 1 + log(13) = 3.56      ← 긴 대화 = 강한 신호
R–H: 1 + log(3)  = 2.10
```

`interactions`를 (유저 × agent) 희소 행렬로 본 것이 학습 데이터다. 10만 유저면 행렬은 10만 × 10만, 채워진 칸은 대화 쌍 수(스펙 λ=3이면 약 23만).

#### A안 (라이브러리형) — `implicit` ALS를 배치로 돌려 top-K를 저장

```
[fit_cf_model — 전역 학습, 하루 1회 (R36)]
interactions(전원) ──▶ scipy.sparse CSR (행=유저, 열=agent, 값=confidence)   # 학습에는 읽히지 않는 유저의 대화도 그대로 쓴다
             ──▶ implicit.als.AlternatingLeastSquares(factors=16, regularization=0.5).fit()   # 10만×10만에서 0.9~1.8 s. agent factor가 갱신된다

[refresh_cf_candidates — 유저별 갱신, 워커 스윕, 예 30분마다 (R19)]
PostgreSQL: SELECT owner_user_id FROM agents
            WHERE EXISTS (SELECT 1 FROM interactions i WHERE i.actor_user_id = agents.owner_user_id)   -- 대화가 1건 이상 (없으면 CF가 없다)
              AND last_active_at > coalesce(cf_candidates_computed_at, '-infinity')   -- 만든 뒤 읽혔거나 활동했다. 아직 안 만든 유저(NULL)는 항상 참
              AND (coalesce(cf_candidates_computed_at, '-infinity') < now() - interval '24 hours'         -- TTL이 지났거나
                   OR EXISTS (SELECT 1 FROM interactions i WHERE i.actor_user_id = agents.owner_user_id AND i.started_at > coalesce(cf_candidates_computed_at, '-infinity')))  -- 새 대화가 있다
            ORDER BY last_active_at DESC LIMIT 5000
             ──▶ 모은 유저를 한 번에 recommend(userids, user_items=<스윕 시점 interactions로 새로 만든 CSR 행>, N=200, items=<공통 public 후보>, recalculate_user=True, filter_already_liked_items=True)
                 # 유저별 최소제곱 한 번 + 행렬곱 한 번. recalculate_user=True는 user_items에서 그 유저의 factor를 즉석에서 다시 풀어(agent factor 고정) 새 대화가 전역 재학습 없이 반영된다.
                 # 단, 마지막 전역 학습 뒤 처음 등장한 agent는 factor가 없어 다음 학습까지 미반영. items는 배치 전체에 배열 하나 — 그래서 공통 후보만 여기 들어간다 (implicit 0.7.3 시그니처 확인)
                 # 후보의 공통 부분(public row가 있는 소유자)은 전원 같아 배치가 되고, 유저별 friends-only 후보만 작은 추가 패스 (R17)
                 # 이미 대화한 A, H 제외(R28)
             ──▶ DynamoDB cf_candidates PK=R: candidates=[(G, .81), (B, .44), … 200개], computed_at, model_version   (BatchWriteItem 25건씩)
             ──▶ agents.cf_candidates_computed_at = now()

[서빙]
GetItem(cf_candidates, R) ──▶ 있는 것을 그대로 (오래됐어도) SourceHit(owner_user_id=G, tier=None, source="cf_engine", score=.81, evidence={cf_score:.81})   # p50 3~5 ms
                                  없으면 CF feature 0 (§5-6)
```

DynamoDB 쓰기는 유저 수가 아니라 그날 읽혔거나 활동한 유저 수에 비례하고, 서빙에서 버려지는 것은 스윕 뒤에 비공개로 돌아간 소유자 정도다. 갱신을 deferq task로 유저마다 넣지 않고 스윕으로 모으는 이유(R19): API가 예약을 몰라도 되고, 모아서 행렬곱 한 번이 유저 하나씩보다 훨씬 싸고, deferq에는 재시도가 없어 실패한 task는 사라지지만 스윕 조건은 다음 사이클에도 참이라 스스로 다시 잡는다. 무엇을 어디에 남기나: **DynamoDB `cf_candidates`의 top-K만.** factor 행렬은 워커 프로세스 메모리(RSS 300 MB 이하)에 머물며 스윕이 재사용한다. R의 이웃이 왜 G인지 — R처럼 A와 길게, H와도 대화한 유저들이 G와도 대화했기 때문이고, 16차원 factor가 그 공통 패턴을 잡는다. `similar_users`(표시용)는 ALS에서는 직접 나오지 않으므로 별도 카운트(A·H와 대화한 유저 중 G와도 대화한 수)로 채우거나 null로 둔다.

실측: λ=3에서 HR@10 0.0054(인기도 0.0090의 60 %), λ=10에서 0.0096(인기도와 동률)이고 같은 군집 비율은 인기도의 두 배. 즉 **인기도 위에 얹는 개인화 feature**로 쓴다.

#### A안 (서비스형) — Gorse에 맡기면

```
[적재] 우리 워커가 interactions를 Gorse REST로 복사
   POST /api/users     {UserId: "R"}                 → data store users
   POST /api/items     {ItemId: "agent(G)", Categories: [] …}   → data store items
   POST /api/feedback  {FeedbackType: "dm_opened", UserId: "R", ItemId: "agent(A)", Timestamp: …}  → data store feedback
   (turn 수는 feedback 값으로 실어 positive_feedback_types = ["dm_opened", "dm_turns>=5"]처럼 임계 식으로 positive 판정에 넣을 수 있지만,
    R16의 연속값 confidence는 BPR 학습에 그대로 들어가지 않는다 — Gorse의 CF는 positive/negative 이진이다)

[Gorse worker, 상시 반복 — R19의 읽기 기준 갱신이 불가능하다. 전원을 계속 다시 만든다] Load Dataset(3 s) ──▶ BPR 학습(19 s) ──▶ 10만 유저 전부 추천 생성(1.5~7분)
   ──▶ cache store documents: (collection="collaborative-filtering", subset="R", id="agent(G)", score=…) × collection마다 유저당 100~130행(두 collection 합계 약 1,390만 행, 검증 §4-3)

[서빙] GET /api/recommend/R?n=60 ──▶ Gorse가 documents에서 R의 목록을 읽어 반환 ──▶ 우리 SourceHit(tier=None, source="cf_engine")
```

동작하려면 기본값 둘을 바꿔야 한다(검증 §4-3): `[recommend.ranker] recommenders=["collaborative"]`(기본 ranker는 오프라인 캐시를 읽지 않는다), 그리고 MySQL cache store의 multi-valued 인덱스가 `categories=[]`인 행을 숨기므로 item에 category를 하나 주거나 PostgreSQL cache store를 쓴다. 고친 뒤 서빙 HR@10 0.0006(`implicit` ALS의 1/9). 요청자별 visibility 조건을 Gorse 안에 넣을 방법이 없으므로, 이것이 결과를 넉넉히 받아 우리가 거르고 부족하면 더 받아야 하는 **유일한 소스**다(R17의 예외 경로). 이 경로의 실측 판단은 `library_verification.md` §0·§4에 있고, R33으로 제외됐다.

#### B안 — 동시 출현 이웃을 우리가 계산

```
[배치] interactions ──▶ agent × agent 동시 출현 카운트 co[X][Y] = 두 agent 모두와 대화한 유저 수
   (정규화 없음. 코사인 정규화는 인기도를 지워 무작위 수준이 된다 — 검증 §3)
   ──▶ neighbors[X] = co[X][·] 상위 N   → PostgreSQL 테이블 (agent, neighbor, co_count) — 조건 조인을 위해 visible_topic_rows와 같은 DB
[서빙] R이 대화한 {A, H}의 이웃 목록을 합산: score(G) = co[A][G] + co[H][G] = 31 + 18 = 49, tie-break는 popularity
   (이웃 테이블이 PostgreSQL이면 §5-1의 EXISTS 조건을 같은 쿼리에 붙여 R에게 보이는 이웃만 읽는다)
   ──▶ SourceHit(owner_user_id=G, tier="public", source="cf_item", score=49, evidence={co_count: 49, similar_users: 49})
```

`similar_users`가 그대로 나온다(49명). 실측: 인기도 tie-break를 붙이면 λ=10에서 ALS 16f와 같은 프로필, 빼면 HR이 25 % 떨어진다. λ=3에서는 ALS의 절반. 라이브러리 의존이 없다는 것이 유일한 장점이었고, R34로 만들지 않는다.

### 5-4. VisibilityFilter — 조건을 못 넣은 hit에만 tier를 붙인다

조건을 쿼리에 넣은 소스(PostgreSQL의 인기도·content·이웃)에서 온 hit은 tier가 있고 F·C는 처음부터 오지 않는다. 필터가 일하는 것은 tier가 `None`인 hit — Gorse가 준 목록, 그리고 배치 시점 조건으로 뽑았지만 tier를 싣지 않은 `cf_candidates` 항목 — 이고, `visible_topic_rows`를 소유자 키로 조회해 tier를 붙인다. 아래 표는 §5-1~§5-3에서 온 hit 전부의 최종 판정이다 — 조건을 이미 거친 hit은 통과만 한다.

| hit | row 조회 결과 | 판정 |
|---|---|---|
| E (popularity 1.00) | `hiking public` | 통과, tier=public |
| G (popularity .63, cf .81) | `photography public` | 통과 |
| A (popularity .22, sim 1.35) | public row 있음 | 통과하지만 **이미 대화한 상대라 for-you에서 제외**(R28) |
| H (popularity .01) | `board_game public` | 통과하지만 **이미 대화한 상대라 제외** — A와 같은 규칙 |
| B (sim 1.17, cf .44) | `camping public`, `hand_drip friends` | 통과 (public row가 있으니 친구 여부와 무관) |
| F (인기가 있어도) | row 없음 | **버림** — agent private |
| C (누가 추천해도) | friends row만, R은 친구 아님 | **버림** |

"엔진이 F를 1위로 줬다"는 아무 힘이 없다. row가 없으면 없다.

### 5-5. Ranker — 가중 합, CF 가중은 게이트 뒤에

> 이 절과 §3-4의 예시는 `recency`를 넣지 않는다 — 예제 세계에 row의 `updated_at`이 없어 계산할 값이 없기 때문이고, `rank.w_recency`를 0으로 둔 가중 집합이라는 뜻이다. 실제 서비스에서는 세 타입 모두 이 항을 갖는다(`rank.recency_half_life_days`, 레지스터 §2). 구현의 재현 테스트는 이 문단이 말하는 가중 집합을 그대로 주고 돌린다.

```
score = w_pop·popularity + w_content·content_similarity(정규화) + w_cf·cf_score + w_mat·agent_maturity + …
```

`w_cf`는 **처음에 0**이다. R35의 자동 게이트대로 배치가 실제 로그 leave-one-out에서 ALS가 인기도를 이길 때만 0에서 올린다. 아래는 예시 가중(pop .4 / content .4 / cf .2)으로 `w_cf`가 켜진 뒤의 값이다. content는 §5-2의 최대값(A의 1.35, 이미 대화한 상대를 제외하기 전 값)으로 정규화했다. 제외 전 최대값으로 나누는 이유는 정규화가 "누구와 이미 대화했나"에 따라 흔들리지 않게 하려는 것이다(B의 content를 1.0으로 두면 B가 E를 앞선다). 식의 `…`에는 `persona_similarity`(R42 예약)도 들어가지만 입력 경로가 없어 이 예시에서는 0이다(O20).

| owner | popularity | content(정규화) | cf | score | 주로 만든 신호 |
|---|---|---|---|---|---|
| **E** | 1.00 | .18 | 0 | .40 + .07 + 0 = **.47** | popularity |
| **B** | .04 | .87 | .44 | .016 + .348 + .088 = **.45** | content |
| **G** | .63 | 0 | .81 | .25 + 0 + .16 = **.41** | collaborative |

`basis`는 상위 결과를 주로 만든 신호로 정한다(예: 상위 K의 feature 기여 합이 가장 큰 것). 위 셋의 기여 합은 popularity .67 / content .42 / cf .25라 이 응답의 `basis`는 `"popularity"`다(섞기 전 순서 기준) — CF가 켜져 있어도 인기도가 답을 주도하면 그렇게 표시한다. `recency`(소유자의 마지막 topic 갱신, 계약 §7)도 작은 가중으로 들어간다 — 오래 활동하지 않은 소유자는 후보에서 빠지지 않고 이 feature와 `popularity` 감쇠로 순위가 내려간다(R19). 하드 제외는 하지 않는다(R31). 로그가 0인 신규 유저(콜드스타트)는 content와 popularity만 남아 `basis: "popularity"` 또는 `"content"`다.

**구간 섞기(R20).** 랭커가 정한 순서를 그대로 내리지 않는다. 최종 점수를 구간(예 상위 5·다음 15·다음 30)으로 나누고 **구간 안에서만** 섞는다 — 구간 사이 순서는 그대로라 1위권이 30위로 밀리는 일은 없고, 구간 안 순서만 방문마다 다르다. seed는 `recommendation_id`라 다음 페이지가 같은 순서를 잇고 결정 로그(`shuffle.seed`, `shuffle.bands`)가 재현한다. 위 예의 E·B·G(.47/.45/.41)는 같은 상위 구간이라 어느 순서로도 나올 수 있고, 아래 응답은 seed가 만든 한 순서다. 타입 ①②는 섞지 않는다. 같은 사람만 보이는 노출 편향을 줄이는 O15의 첫 답이고, 검증(R34)의 정확도는 섞기 전 순서로 잰다.

### 5-6. Assembler — 스냅샷은 노출을 허가하지 않는다

1. hydration(라벨·owner_note).
2. **응답 직전에 `visible_topic_rows` 재확인.** `cf_candidates`는 배치 시점 스냅샷이라 그 사이 G가 agent를 private로 돌렸을 수 있다. 그러면 G는 빠지고, 순위 공백 없이 다음 후보가 올라온다. 아직 안 보여 준 후보를 다 소진했고 다음 스윕 전이면, 이미 대화한 A·H가 그 뒤에 붙는다(R28). 재등장 표식 `talked_before`는 결정 로그에만 남고 응답에는 없다.
3. `computed_at`이 TTL의 몇 배(R36: 7일)를 넘겼으면 `degraded: ["cf_candidates_stale"]`. 항목이 **없는** 경우는 다르다 — 아래.

**돌아온 유저의 첫 요청.** 같은 R이 대신 6개월 만에 돌아왔다면 어떻게 되나. 6개월 전 항목이 남아 있으니 그것을 **그대로 한 번 서빙한다**(R19). 그 사이 비공개로 돌아간 소유자는 2번 재확인이 걸러내고, `computed_at`이 7일을 넘겼으니 `degraded: ["cf_candidates_stale"]`가 붙는다. 이 요청이 `agents.last_active_at`을 갱신해 다음 스윕(30분 안)이 R의 항목을 새로 만들고, 다음 방문부터 새 것이다. 항목이 아예 없는 유저(대화가 0건인 신규 유저)는 §5-1 인기도와 §5-2 content가 요청 시 PostgreSQL 쿼리라 그대로 답이 나오고, 랭커는 CF feature만 0인 채로 `limit`을 채운다 — `basis: "popularity"`(또는 `"content"`), `degraded: []`, 축소 응답이 아니다. 첫 대화 이벤트 뒤 다음 스윕이 첫 항목을 만든다. 타입 ②는 사전 계산이 없으니 처음부터 영향이 없다.

```json
{ "contract_version": 1, "recommendation_id": "rec-9c…",
  "agents": [
    {"agent_id": "agent(E)", "owner_user_id": "E", "position": 1, "matched_topics": [{"topic_id": "hiking", "requested": false, …}],
     "signals": {"coverage": null, "topic_maturity": 0.8, "agent_maturity": 0.7, "popularity": 1.0, "similar_users": null}, "fit": null},
    {"agent_id": "agent(B)", "owner_user_id": "B", "position": 2, …, "signals": {…, "popularity": 0.04, "similar_users": null}},
    {"agent_id": "agent(G)", "owner_user_id": "G", "position": 3, "matched_topics": [], "signals": {…, "similar_users": null}} ],
  "basis": "popularity", "next_cursor": "…", "degraded": [] }
```

`similar_users`는 B안(`cf_item`)이면 co_count(G의 49)로 채우고, A안(ALS)에서는 직접 나오지 않아 null이다. 위 응답은 A안 기준이다.

이 목록의 결정 로그(계약 §8)는 `recommendation_id` `rec-9c…` 한 항목이다: `ranked`는 섞기 전 순서 E·B·G, `shuffle: {seed: "rec-9c…", bands: [5, 20, 50]}`, `cf_model_version`은 이 답을 만든 `cf_candidates`의 `model_version`, `basis: "popularity"`, `filter.out`은 재확인에서 빠진 수. `next_cursor`가 같은 `recommendation_id`를 실으므로 다음 페이지 요청은 같은 항목의 `pages[]`에 덧붙고 같은 seed로 섞기 순서가 이어진다(R20).

서빙 지연 시간은 사전 계산 결과 읽기 + 인덱스 조회 한두 번이라 수십 ms다. Gorse를 서빙 경로에 두면 그 위에 REST 왕복(p50 5 ms / p95 15 ms)이 더해진다.

---

## 6. 세 타입 한눈에

| | ① 명시 요청 | ② 서브탭 | ③ 메인 |
|---|---|---|---|
| 호출 | bourbon-agent → 내부 API | 클라이언트 → 클라이언트 API | 클라이언트 → 클라이언트 API |
| 요청자 | body `user_id` | `x-user-id` | `x-user-id` |
| QueryBuilder | LLM + topic-api 검색 → topic ≤ 3 | 내 topic 목록 → topic마다 쿼리 | 요청자 id 그대로 |
| 소스 | `topic_index` | `topic_index` | `popularity` + `content_similarity` + `cf_item`/`cf_engine` |
| 읽는 저장소 | `visible_topic_rows`, `friends`, `agents`, `popularity`(약한 가중) | 같음 + 요청자 topic(topic-api 조회, R27) | `popularity`, `visible_topic_rows`, `friends`, `agents`, `cf_candidates`, 요청자 topic(topic-api 조회) |
| 정렬 | (coverage desc, score desc) | score desc, 섹션별 | score desc (가중 합) → 구간 안 섞기(R20) |
| A안 ↔ B안 차이 | 인덱스: OpenSearch vs PostgreSQL | 같음 | CF: `implicit` ALS 또는 Gorse vs 동시 출현 이웃 |
| 지연 시간 | LLM 수백 ms~수 초 + 인덱스 수 ms | 수십 ms | 수십 ms (+ Gorse면 REST 왕복) |
| 결과 | 소수, `resolved_topics` 포함 | topic별 섹션 | 목록 + `basis` |

---

## 7. 저장소 지도 — 무엇이 어디에, 어느 안에서

| 저장소 | 들어 있는 것 | A안 | B안 | 비고 |
|---|---|---|---|---|
| **PostgreSQL** | `visible_topic_rows`, `friends` 미러(R17), `agents`, `interactions`(turn 카운터 포함), `popularity`, `population_stats`(스펙 §8), B안 이웃 테이블 | ● | ● | 조인·집계가 있는 집합 전부(R18). 노출 판정의 유일한 기준은 `visible_topic_rows`. `friends`·`popularity`·이웃을 같은 DB에 두어 조건을 쿼리에 넣는다 |
| **DynamoDB** | 테이블 하나(R44, 계약 §6-1): `cf_candidates`(`USER#…/CF_CANDIDATES`), 결정 로그(`REC#…/LOG`, GSI `served-day-index`, TTL), `event_log`(`EVT#날짜#shard`, TTL 180일), 게이트 상태(`CONFIG/CF_GATE`) | ● | ● | 단건 키 읽기·쓰기만 있고 조인이 없는 집합(R18). 사용량 과금이라 10만~100만에서 Redis 전용 노드보다 한 자릿수 배 저렴. GetItem p50 3~5 ms |
| **Redis** (공유 ElastiCache) | deferq(워커 debounce)만 | ● | ● | 우리 데이터는 두지 않는다(R18). Gorse cache store로는 못 쓴다(Redis Stack 전용) |
| **OpenSearch** | 쓰지 않는다(R34). §2-3의 nested 인덱스는 기록 | — | — | PostgreSQL이 같은 정답을 3배 빠르게 낸다. 남는 용도는 R25가 임베딩을 다시 볼 때의 topic 벡터 kNN(지금은 넣지 않음) |
| **MySQL** (Gorse 전용) | 쓰지 않는다(R33). §2-3의 data·cache store는 기록 | — | — | 10만 유저에 cache 약 1,400만 행, 상시 재계산 |
| **워커 프로세스 메모리** (`implicit`) | agent factor 행렬 (10만 × 16) | ● | — | 영속화하지 않음. 전역 학습이 갈아 끼우고 스윕이 재사용. 결과 top-K만 DynamoDB |

● 필수 · ○ 선택 · — 없음

---

## 8. 흐름이 스스로를 고치는 부분 — 보정과 게이트

`interactions`는 서빙 입력만이 아니다(스펙 §8, R35·R37).

```
interactions + turn 카운터 + visible_topic_rows + agents + friends
   ──▶ 하루 1회 배치 ──▶ population_stats (snapshot_date, window_days, param, value_json: 퍼센타일 + 샘플 수)
   ──▶ params_measured.json (합성 생성기 params.json과 같은 스키마, 측정 안 된 값은 source: "default")
   ──▶ 합성 검증을 실측 파라미터로 다시 돈다

같은 배치 ──▶ 실제 로그 leave-one-out: ALS 16f vs 인기도 (HR@10, 같은 군집 비율)
   ──▶ ALS가 이기면 랭커 설정의 w_cf를 0에서 올린다 (R35 자동 게이트)
```

게이트 쪽 구현 메모 셋(1-8). **숨긴 대화는 학습에서도 뺀다** — 안 그러면 ALS가 맞혀야 할 쌍을 이미 배운 상태가 되어, 켜는 날 CF가 비정상적으로 좋게 나온다. **인기도 쪽도 같은 로그로 다시 만든다** — `popularity` 테이블은 숨긴 그 대화를 이미 봤으므로, 한쪽만 답을 아는 비교가 된다. 그리고 **"같은 군집"은 실서비스에 입력이 없어** 대리 지표를 쓴다(요청자 본인이 공개한 topic과의 겹침 — 계약 §11의 열린 항목, 레지스터 §4).

임계값(활성 유저 1,000명·대화 시작 5,000건 미만이면 기본값 유지)과 주기(하루 1회)는 R37 — 값은 설정 레지스터 `calibration.*`. λ(유저당 대화 시작 수)는 `entry=direct`인 시작만으로 재고, 추천을 거친 시작은 `conversation_rate_via_recommend`로 따로 둔다 — 추천이 만든 대화로 추천 파라미터를 보정하면 순환이 된다.

---

## 9. 이 문서가 정하지 않는 것

이 문서의 예시값은 결정이 아니다. 실제 값이 걸린 열린 항목:

| 이 문서의 어디 | 열린 항목 |
|---|---|
| §3-5 `fit` 표시의 축("나와 비슷해요 / 다른 관점도 살펴봐요", 기획 중) | O5 |
| §5-5 구간 섞기(R20) 이상의 탐색 항을 넣을지 | O15 |
| §5-5 가중 합의 예약 항 `persona_similarity`(R42, 지금 0) — 입력 경로·동의 범위·가중 규칙 | O20 |

2026-09-09에 닫힌 것: `requester_topics`는 요청 시 조회(R27), `popularity` 정의(R29), 섹션 크기(R30), TTL·스윕·전역 학습 주기·stale 임계(R36), `w_cf` 게이트(R35), 보정 값(R37), 비활성 소유자 하드 제외 없음(R31), content 정의(R25)와 카탈로그 소스(R26), 이미 대화한 상대 제외와 소진 뒤 재등장(R28), `recommendation_id` 전달(R24), A안/B안 비교 종료(R33·R34). 이 문서의 예시값 중 결정으로 정해진 값은 `agent_discovery_settings.md`에 있다.

`friends`를 미러하는가(O10)는 R17로 닫혔다: 미러하고, visibility 판정은 후보 조회 쿼리 안에서 한다.
