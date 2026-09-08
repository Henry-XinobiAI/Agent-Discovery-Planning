# agent-discovery-api 이벤트 정의서 — 받을 것, 우리가 먼저 정의할 것, 발행 가능성 검증

> `agent_discovery_redesign.md` §9의 3번, `agent_discovery_contract.md` §9-1을 발신 측에 붙일 수 있는 형태로 푼 것. 코드 조사는 **2026-09-08, 세 repo를 pull한 최신 main** 기준(topic-api `cae7fd8`, bourbon-api `c4c3300`, bourbon-agent `208a6286`).
>
> **진행 방식(오너 2026-09-08)**: 추가가 필요한 이벤트는 agent-discovery-api에서 먼저 정의하고, 우리가 직접 발행해 테스트하며 써 보고, 그 뒤에 발신 repo에 요청한다. 대신 **그 이벤트를 발행할 repo가 그 지점에서 그 필드를 실제로 갖고 있는지**를 먼저 검증한다. §3이 그 검증이다.
>
> rev 2. rev 1은 pull 이전 코드를 봤고 topic-api에 이벤트가 없다고 적었다. 틀렸다 — 아래 §1에 정정.

---

## 0. 한눈에

| 우리가 필요한 것 | 지금 있나 | 우리 처리 | 요청할 것 |
|---|---|---|---|
| 유저 topic이 바뀌었다는 힌트 | **있음** `bourbon.topics_updated` (topic-api 워커, persona 동기화가 움직인 topic마다 1건) | 힌트로 받고 그 유저의 열린 집합을 **다시 읽는다** (§2-1) | 없음 |
| 유저가 visibility를 바꿨다는 힌트 | **없음.** `PATCH /me/topics/{topic_id}`는 api 프로세스에서 처리되고, 그 프로세스에는 AMQP 연결이 없다 | 같은 재읽기 | topic-api api 프로세스에서 발행 (§2-2). **닫힘이 이 경로로만 오므로 가장 중요** |
| 열린 집합 읽기 | **있음** `GET /api/internal/svc/topic/users/{id}/topics?visibility=public,friends` — 항목마다 `score, visibility, revision, updated_at, support` | 재읽기의 실제 호출 | 없음 |
| agent 공개 여부 | **미정.** `Agent.enabled`가 그 역할을 할지 새 필드가 생길지 결정 전(오너) | 결정 뒤 이벤트 하나 | 결정 뒤 (§2-3) |
| friend 관계 변화 | **있음** `bourbon.friendship_changed` | 구독 | 없음 |
| 유저 가입 (추천 대상 agent의 등장) | **있음** `bourbon.user_registered` (`CREATED → ACTIVATED` 전이에서 발행) | 구독 → `agents` row 생성 (§2-7) | 없음 |
| 유저 탈퇴 | **있음** `bourbon.user_deactivated` | 구독 → 전부 삭제 | 없음 |
| 타인 agent와 대화 시작 | **없음.** 대화는 `AGENT_DM` room(`A:B'`)이고 `ensure_agent_dm_room`이 find-or-create 하지만 이벤트는 없다 | 우리가 정의 (§2-4) | bourbon-api + 클라이언트(귀속 키) |
| 대화 진행(turn) | **있음** `bourbon.message_created` (`room_id, sender_id, sender_type, room_type=agent_dm`) | 대화 시작 이벤트의 `room_id`와 조인 | 없음 — **새 turn 이벤트가 필요 없다** |
| 성숙도 | topic 단위는 `score`(topic-api 임시). agent 단위는 컴포넌트 예정 | `score`를 feature로 | 컴포넌트가 생기면 (§2-5) |

### rev 1 정정 — 설명과 코드가 다르다고 적었던 세 곳

1. ~~bourbon-agent → topic-api 이벤트 경로가 없다~~ → **있다, 그리고 진행 중이다(오너).** topic-api에 deferq 워커(`worker/`)가 있고 `bourbon.persona_updated`를 소비해 persona 동기화를 돌리며, 움직인 topic마다 `bourbon.topics_updated`를 발행한다. 워커는 prod에서 LLM 프록시 문제로 0 replicas다(README).
2. ~~agent visibility 필드가 없다~~ → 없는 것은 맞고, **`enabled`가 그 역할을 할지 새 필드가 생길지 미정**이다(오너). 우리는 결정을 기다리되 이벤트 모양은 어느 쪽이든 같다(§2-3).
3. ~~타인 agent와의 대화는 group room~~ → **`AGENT_DM`이라는 room 종류가 따로 있다.** `A:B'` = A가 B의 agent와 대화하는 방향성 있는 방. 멤버 {A}, 착석 {A', B'}. group room 착석은 다른 경로다. 대화 시작의 자연스러운 지점은 `ensure_agent_dm_room`의 **create**(그리고 나갔다 돌아오는 re-enter)다.

### 새로 발견한 것 — 확인 필요

- **main에서 agent DM을 열려면 두 사람이 친구여야 한다** (`_assert_friends_to_open`). 그대로면 public agent를 친구 아닌 사람에게 추천해도 대화를 열 수 없다. 원격 브랜치 `temp/agent-dm-open-without-friendship`(2026-09-02, "임시")이 그 게이트를 내린다. **어느 쪽이 제품 의도인지**가 타입 ①②③ 전부에 걸린다(§5-1).
- **우리 워커가 미러하는 `bourbon.user_topic_updated`(`touched` 필드)는 topic-api에 없다.** 실제 이름은 `bourbon.topics_updated`이고 payload도 다르다. 우리 코드 쪽 정정 대상이다(§4).

---

## 1. topic-api에 지금 있는 것 (코드 기준)

```
bourbon-agent ──bourbon.persona_updated──▶ topic-api worker
                                            │ sync_user(): grounding, 쓰기
                                            ▼
                                   bourbon.topics_updated  ×(움직인 topic 수)
                                   {user_id, topic_id, persona_revision, topic_revision}
```

- `worker/listener.py` `on_persona_updated_sync_topics`: 동기화 뒤 `changed`가 비어 있지 않으면 `_announce`가 topic마다 `topics_updated`를 발행한다. best-effort — 발행 실패는 경고만 남긴다. docstring이 소비자 계약을 이렇게 적는다: **"a consumer that missed an event converges on its next read of the user's topics."** 즉 topic-api 스스로 이벤트를 **힌트**로 정의했다.
- `topic_revision` = 그 topic row의 카운터(`UserTopic.revision`). 읽어 온 row의 `revision`이 이 값 이상이면 이벤트가 말한 상태 이상이다.
- 같은 워커의 `worker/images.py`가 `topics_updated`를 소비해 이미지 작업을 한다. 소비자가 이미 하나 있어 이벤트가 살아 있다.
- **api 프로세스(gunicorn)에는 AMQP가 없다.** `PATCH /me/topics/{topic_id}`(visibility), `PUT /users/{id}/topics/{topic_id}/score`, `POST /users/{id}/scores`, `DELETE /users/{id}`, 카탈로그 병합은 모두 발행 없이 끝난다.
- 내부 읽기 route `GET /users/{user_id}/topics`는 `visibility=` 쿼리(기본 `public`)로 tier를 고르고, 항목에 `score, visibility, revision, updated_at, support, descriptions`가 있다.

---

## 2. 이벤트 정의 — 우리가 먼저 미러하고 테스트한다

### 2-1. `bourbon.topics_updated` — 있는 것을 힌트로 소비

```python
class TopicUpdatedPayload(BaseModel):     # topic-api worker/events.py 그대로 미러
    user_id: UUID
    topic_id: TopicId
    persona_revision: PositiveInt
    topic_revision: PositiveInt
```

**우리 처리**: 리스너는 `user_id`만 꺼내 유저 단위 debounce(수 초, 상한 1분)를 걸고 끝. task가 `GET /internal/.../users/{id}/topics?visibility=public,friends`를 읽어 그 유저의 열린 row를 **통째로 교체**한다(없어진 것 삭제, 새것 upsert). 한 동기화가 topic 10개를 움직여 이벤트 10건이 와도 재읽기는 1회다.

**왜 스냅샷 이벤트를 요청하지 않나**: topic-api가 이미 "힌트 + 재읽기"를 계약으로 정했고, 읽기 route가 스냅샷 그 자체다. 우리가 필요한 스냅샷을 이벤트에 실어 달라고 하면 topic-api가 같은 읽기를 발행 시점에 대신 하는 것뿐이다. 놓친 닫힘은 다음 힌트의 재읽기가 고친다. 재읽기가 하루에 한 번도 안 오는 유저(비활성)는 어차피 바뀐 것이 없다.

**topic_revision 활용**: 재읽기 결과의 row `revision`이 이벤트의 `topic_revision`보다 작으면(복제 지연) 짧게 한 번 다시 읽는다. 그 이상이면 정상.

### 2-2. `bourbon.user_topic_settings_updated` — 우리가 정의, topic-api api 프로세스에 요청

닫힘(`public/friends → private/hidden`)은 **오직** `PATCH /me/topics/{topic_id}`로 일어나고 이 경로는 지금 아무것도 발행하지 않는다. 힌트가 없으면 유저가 닫은 topic이 다음 persona 동기화까지(며칠일 수 있다) 추천에 남는다. 이것이 요청의 핵심이다.

```python
class UserTopicSettingsUpdatedPayload(BaseModel):
    user_id: UUID
    topic_id: TopicId
    topic_revision: PositiveInt      # patch 뒤 row 카운터. topic-api의 patch 응답이 이미 revision을 돌려준다
    touched: list[str]               # patch가 건드린 필드명. 지금은 ["visibility"]만 가능

user_topic_settings_updated = Event("bourbon.user_topic_settings_updated", UserTopicSettingsUpdatedPayload)
```

- 새 visibility **값은 싣지 않는다.** 우리는 어차피 재읽기하고, 값이 있으면 소비자가 재읽기를 생략하려는 유혹이 생긴다.
- **우리 처리**: §2-1과 같은 debounce → 재읽기. 리스너가 둘, task는 하나.
- **발행 지점**: `api/routers/me_topics/router.py` `patch_my_topic` → `patch_settings` 성공 뒤. 응답 구조 `TopicSettingsPatchResponse`에 `revision`이 이미 있어 payload 재료가 다 있다(§3).
- **전제 작업**: api 프로세스에 AMQP 연결. 워커의 `worker/amqp.py`를 api 프로세스 lifespan에도 붙이는 일이고, 설정 `DEFERQ_AMQP_URL`은 이미 있다(현재 "worker only"). best-effort 발행이므로 브로커가 없어도 patch는 성공해야 한다.
- 대안으로 `topics_updated`를 재사용할 수도 있으나 `persona_revision: PositiveInt`가 필수여서 persona 동기화가 아닌 쓰기에는 맞지 않는다. 이름도 "persona 동기화가 움직였다"는 뜻이라 섞지 않는 것이 맞다.

### 2-3. agent 공개 여부 — 결정 뒤

`enabled`로 가든 새 필드로 가든 우리가 받을 것은 같다.

```python
class PersonalAgentVisibilityChangedPayload(BaseModel):
    owner_user_id: UUID
    agent_id: UUID
    discoverable: bool               # 필드 이름이 무엇이든 "추천에 나올 수 있는가" 하나로 받는다
    occurred_at: AwareDatetime
```

`enabled`로 결정되면 `disable_for_user`(탈퇴)와 재활성 지점이 발행 지점이고, 탈퇴는 `user_deactivated`로도 오므로 겹쳐도 무해하다. 새 필드가 생기면 그 필드의 쓰기 지점. **우리 처리**: `false` → 그 주인의 열린 row 전부 삭제 + `agents` 갱신. `true` → `agents`만 갱신하고 row는 다음 topic 재읽기가 채운다(또는 즉시 재읽기 1회).

### 2-4. `bourbon.agent_dm_opened` — 우리가 정의, bourbon-api에 요청

대화 시작 = `ensure_agent_dm_room(actor_id, other_id)`가 room을 **만들었을 때**, 그리고 나갔던 멤버가 **다시 들어왔을 때**. 이미 들어 있는 방을 다시 열 때(find)는 내지 않는다 — 그건 시작이 아니다. `actor_id == other_id`(자기 agent)는 내지 않는다.

```python
class AgentDmOpenedPayload(BaseModel):
    room_id: UUID
    actor_user_id: UUID              # 대화를 시작한 사람
    owner_user_id: UUID              # 상대 agent의 주인
    agent_id: UUID                   # 상대 agent
    reopened: bool                   # False = 방 생성, True = 재입장
    entry: str                       # "recommend_explicit" | "discover_by_topic" | "discover_for_you" | "direct" | "unknown"
    recommendation_id: UUID | None   # 우리 응답의 값을 클라이언트가 그대로 넘긴 것
    occurred_at: AwareDatetime
```

**귀속 키의 여행**: 우리 응답 `recommendation_id` → 클라이언트 → agent DM 열기 route(`POST /rooms/agent-dm/{user_id}`에 선택 body 또는 query `recommendation_id`, `entry`) → 이 이벤트. **클라이언트 변경이 같이 필요하다.** 사슬이 끊기면 `recommendation_id: null`, `entry: "unknown"`으로 오고 그 대화는 "추천이 만들었는지 모름"으로 영구히 남는다. 소급 불가라 가장 먼저 닫는다.

**우리 처리**: `interactions`에 (actor, owner, room_id, started_at, entry, recommendation_id) 기록, `popularity[owner]` 증가, 결정 로그의 `recommendation_id`와 조인.

### 2-5. `bourbon.message_created` — 있는 것으로 turn을 셈

```python
# bourbon-api messages/events.py 그대로 미러
room_id, message_id, sender_id, sender_type, type, room_type
```

`room_type == "agent_dm"`이고 `sender_type`이 유저인 메시지 = 그 방의 actor가 agent에게 한 turn. `room_id`로 §2-4의 기록과 조인하면 (actor, owner)가 나온다. 조인 대상이 없는 room_id(우리가 시작을 놓쳤거나 우리 서비스 이전에 열린 방)는 버린다. **bourbon-agent에 turn 이벤트를 요청할 필요가 없다.** 메시지 양이 많으므로 리스너는 `room_type` 필터 뒤 카운터만 올린다.

### 2-6. `bourbon.agent_maturity_changed` — 컴포넌트가 생기면

```python
class AgentMaturityChangedPayload(BaseModel):
    owner_user_id: UUID
    maturity: float                  # 0~1
    maturity_version: int
    occurred_at: AwareDatetime
```

topic 단위는 재읽기의 `score`가 자리다. 컴포넌트가 `score`를 대체하든 새 필드를 추가하든 우리 변경은 feature 매핑 한 줄이다.

### 2-7. 이미 있어서 구독만

| 이벤트 | payload | 우리 처리 |
|---|---|---|
| `bourbon.friendship_changed` | `user_low, user_high, action, occurred_at` | friends 미러 갱신 또는 조회 캐시 무효화 |
| `bourbon.user_registered` | `user_id, email` | **추천 대상 agent의 등록.** `agents`에 `(owner_user_id, agent_id, discoverable=false, registered_at)` row를 만든다. agent id는 bourbon-api가 `uuid5(AGENT_NAMESPACE, f"personal_agent:{user_id}")`로 결정론적으로 만들므로 읽어 올 필요 없이 같은 규칙으로 계산한다(네임스페이스 상수를 공유하거나, 첫 `agent_dm_opened`·공개 여부 이벤트에서 받은 `agent_id`로 채운다). **`email`은 저장도 로그도 하지 않는다** — payload에서 읽지 않는다. 이 row가 있어야 topic이 하나도 열리지 않은 agent도 "존재하는 대상"으로 세어지고, 콜드스타트 신규 agent 부스트와 타입 ③의 모집단 크기가 정의된다 |
| `bourbon.user_deactivated` | `user_id` | 그 유저의 열린 row·agents·사전 계산·요청자 데이터 삭제. 상호작용 로그의 actor 쪽은 익명화 |
| `bourbon.persona_updated` | `user_id, revision, changes[…]` | 직접 쓰지 않는다. topic id가 없다. `topics_updated`가 곧 온다는 뜻일 뿐 |

---

## 3. 발행 가능성 검증 — 그 repo가 그 지점에서 그 필드를 갖는가

| 이벤트 | 발행 repo · 지점 | 필드 | 그 지점에 있나 |
|---|---|---|---|
| `user_topic_settings_updated` | topic-api `api/routers/me_topics/router.py` `patch_my_topic`, `patch_settings` 반환 뒤 | `user_id` | ✅ `viewer_id` (demo stand-in이면 stand-in id — **실제 쓰인 id**를 실어야 함) |
| | | `topic_id` | ✅ 경로 |
| | | `topic_revision` | ✅ `patch_settings`가 `ALL_NEW`로 돌려주고 응답 `revision`에 이미 실린다 |
| | | `touched` | ✅ `patch.touched`, 로그에 이미 찍는다 |
| | | AMQP 연결 | ❌ api 프로세스에 없음 — **전제 작업** |
| `agent_dm_opened` | bourbon-api `rooms/service.py` `ensure_agent_dm_room`, room 생성 트랜잭션 커밋 뒤 / `_restore_membership_and_seat` 뒤 | `room_id, actor_user_id, owner_user_id` | ✅ `room_id, actor_id, other_id` |
| | | `agent_id` | ✅ `target_agent_id` (create), re-enter는 `personal_agent_id(other_id)` |
| | | `reopened` | ✅ 두 분기가 코드에서 갈린다 |
| | | `entry, recommendation_id` | ❌ route에 없음 — **route 파라미터 추가 + 클라이언트 전달** |
| | | AMQP | ✅ bourbon-api는 `friends/events.py`가 같은 모양으로 발행 중 |
| `personal_agent_visibility_changed` | bourbon-api `personal_agents/service.py` (enabled로 갈 경우 `_upsert_agent`, `disable_for_user`) | 전부 | ✅ `agent.id, owner_user_id, enabled` 모두 그 함수 안에 있다. 새 필드면 그 쓰기 지점 |
| `topics_updated` 소비 | — | — | ✅ 이미 발행 중. 우리 워커가 이름·payload를 맞춰야 함 |
| `message_created` 소비 | — | `room_type` | ✅ payload에 있다. 단 bourbon-api 주석은 값을 `dm/group`, bourbon-agent 주석은 `user_dm/agent_dm/group`으로 적는다 — **실제 값은 `RoomType` enum(`user_dm, agent_dm, group`)**. 소비 전 한 번 실측 |
| `agent_maturity_changed` | 성숙도 컴포넌트 | — | 컴포넌트가 없어 검증 불가. 미룸 |

결론: **새로 정의하는 이벤트 셋(`user_topic_settings_updated`, `agent_dm_opened`, `personal_agent_visibility_changed`) 모두 발행 지점에 필드가 있다.** 막힌 것은 둘 — topic-api api 프로세스의 AMQP 연결, 그리고 agent DM 열기 route가 `recommendation_id`·`entry`를 받는 일(클라이언트 포함).

---

## 4. agent-discovery-api에서 먼저 하는 일

1. **미러 정정**: `worker/events.py`의 `bourbon.user_topic_updated`(`touched`)를 실제 이름 `bourbon.topics_updated`(`user_id, topic_id, persona_revision, topic_revision`)로 바꾼다. 필터 조건 "`touched`에 visibility가 있을 때만"은 사라진다 — `topics_updated`는 persona 동기화가 움직인 topic이라 **항상** 재읽기 대상이다.
2. **새 이벤트 셋을 우리 `worker/events.py`에 선언**한다(§2-2, §2-3, §2-4의 모양). 발신 repo가 아직 안 내도 큐는 만들어지고 비어 있을 뿐이다.
3. **CLI 발행 명령**: `cli publish topics-updated / topic-settings-updated / agent-dm-opened / message-created …`로 로컬 RabbitMQ에 넣어 왕복을 시험한다. 합성 데이터 생성기(재설계 §6-2)가 같은 발행기를 써서 10만 유저의 이벤트 열을 만든다.
4. **재읽기 task 하나**: `topics_updated`와 `user_topic_settings_updated` 두 리스너가 같은 debounce → 같은 task로 모인다. task는 내부 route를 `visibility=public,friends`로 읽어 열린 row를 교체한다.
5. **turn 카운터**: `message_created`를 `room_type` 필터로 받아 `interactions`를 보강한다.
6. 위가 로컬에서 도는 것을 확인한 뒤 §6의 요청서를 낸다.

---

## 5. 오너 확인 항목

1. **agent DM의 친구 게이트**: main은 친구여야 열린다. 임시 브랜치는 게이트를 내린다. 추천은 어느 전제인가. 게이트가 남으면 친구 아닌 사람의 public agent를 추천하는 것은 "대화 못 여는 카드"가 된다.
2. **agent 공개 여부의 필드**: `enabled` 재사용인지 새 필드인지. 결정 전까지 §2-3은 미러만 하고 소비하지 않는다.
3. **`recommendation_id`의 여행**: 클라이언트가 agent DM 열기 요청에 실어야 한다. 타입 ①은 bourbon-agent의 카드 → 클라이언트 → route. 이 사슬을 지금 요청 범위에 넣는가.
4. **재읽기 tier 범위**: `visibility=public,friends`만 읽어 저장하고, 타입 ②③에 필요한 요청자 자신의 topic 목록은 요청 시 topic-api를 읽는다(권고). 아니면 요청자 자신의 것은 tier 무관하게 미러하되 주인 키 아래에만 둔다.
5. **topic-api 워커 0 replicas**: prod에서 persona 동기화가 안 돌면 `topics_updated`도 없다. 우리 시험은 dev에서 하되, prod 시점에는 이 전제가 풀려 있어야 한다.
6. **재활성 이벤트가 없다.** bourbon-api에는 `user_registered`(활성화 전이)와 `user_deactivated`만 있고, 탈퇴 뒤 돌아오는 유저를 알리는 이벤트는 없다. 돌아오면 `user_registered`가 다시 나오는지, 아니면 조용히 재활성되는지 확인이 필요하다. 조용하면 우리 `agents` row가 없는 채로 topic 이벤트가 오므로, 재읽기 task가 `agents` row를 **없으면 만든다**로 방어한다.

---

## 6. 요청서로 자를 때의 단위

| 받는 곳 | 묶음 | 선행 |
|---|---|---|
| topic-api | api 프로세스 AMQP 연결 + `user_topic_settings_updated` 발행(`patch_my_topic` 1곳) | §5-4는 무관. 바로 가능 |
| bourbon-api | `agent_dm_opened` 발행(`ensure_agent_dm_room` 2분기) + route에 `recommendation_id`·`entry` 선택 파라미터; 공개 여부 결정 뒤 `personal_agent_visibility_changed` | §5-1, §5-2, §5-3 |
| 클라이언트 | agent DM 열기 요청에 `recommendation_id`·`entry` | §5-3 |
| bourbon-agent | 타입 ① 호출을 새 계약으로(요청자 = 실제 말한 사람; 지금은 agent 주인을 보낸다), 응답의 `recommendation_id`를 카드에 실어 전달 | 계약 확정 |
| 성숙도 컴포넌트 | `agent_maturity_changed` | 컴포넌트 존재 |
