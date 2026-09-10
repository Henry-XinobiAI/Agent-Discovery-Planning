# agent-discovery-api 이벤트 정의서 — 받을 것, 우리가 먼저 정의할 것, 발행 가능성 검증

> `agent_discovery_redesign.md` §9의 3번, `agent_discovery_contract.md` §9-1을 발신 측에 그대로 전달할 수 있는 형태로 풀어 쓴 것. 코드 조사는 **2026-09-08, 세 repo를 pull한 최신 main** 기준(topic-api `cae7fd8`, bourbon-api `c4c3300`, bourbon-agent `208a6286`).
>
> **진행 방식(오너 2026-09-08)**: 추가가 필요한 이벤트는 agent-discovery-api에서 먼저 정의하고, 우리가 직접 발행해 테스트하며 써 보고, 그 뒤에 발신 repo에 요청한다. 대신 **그 이벤트를 발행할 repo가 그 지점에서 그 필드를 실제로 갖고 있는지**를 먼저 검증한다. §3이 그 검증이다.
>
> rev 2. rev 1은 pull 이전 코드를 봤고 topic-api에 이벤트가 없다고 적었다. 틀렸다 — 아래 §1에 정정.

---

## 0. 한눈에

> **플랫폼의 이벤트 추가 기준(2026-09-10 공유, R46·R47·R48의 근거)**: 판정 기준이 명확하고 소비자가 여럿인 것만 이벤트로 만든다(가입·탈퇴·메시지·리액션·친구 상태 갱신 같은 것). 이벤트는 상태를 내포하지 않아야 한다("전에 방문했다"를 알아야 하는 `room_revisited`류는 기각). 단일 소비자·사후분석용은 그 서비스 안에서 풀거나 로그 기반으로 간다. DB 직접 접근은 불가, AMQP vhost 공유는 가능, deferq Redis DB 번호는 서비스별 할당. 아래 요청은 이 기준으로 2026-09-10에 다시 잰 것이다.

| 우리가 필요한 것 | 지금 있나 | 우리 처리 | 요청할 것 |
|---|---|---|---|
| 유저 topic이 바뀌었다는 힌트 | **있음** `bourbon.topics_updated` (topic-api 워커, persona 동기화로 변경된 topic마다 1건) | 힌트로 받고 그 유저의 공개된 집합을 **재조회한다** (§2-1) | 없음 |
| 유저가 visibility를 바꿨다는 힌트 | **없음.** `PATCH /me/topics/{topic_id}`는 api 프로세스에서 처리되고, 그 프로세스에는 AMQP 연결이 없다 | 같은 재조회 | topic-api에 "필요"만 요청하고 형태는 topic-api가 정한다(§2-2, R48). **비공개 전환이 이 경로로만 오므로 가장 중요** |
| 공개된 집합 조회 | **있음** `GET /api/internal/svc/topic/users/{id}/topics?visibility=public&visibility=friends` (반복 파라미터, 기본 `public`) — 항목마다 `score, visibility, revision, updated_at, support, descriptions` | 재조회의 실제 호출 | 없음 |
| 요청자 자신의 프로필 조회 | **있음** 같은 route, `visibility=public&visibility=friends&visibility=private` — `hidden`은 요청하지 않는다(R22) | 타입 ②의 섹션·타입 ③ content 입력 — 요청 시 조회(R27) | 없음 |
| 카탈로그 그래프(edge 목록) | **없음.** 카탈로그는 `data/catalog_dist/catalog.json`으로 이미지에 실리고 내부 route가 없다 | content 유사도의 계층 감쇠(R25)에 최단 hop 거리가 필요 | 없음 — `catalog.json`을 빌드 때 복사(R26). route는 보류(§2-8) |
| agent 공개 여부 | **없음.** 새 필드 `discoverable`(기본 false)을 bourbon-api에 요청한다(R23) | 우리가 정의 (§2-3) | bourbon-api |
| friend 관계 변화 | **있음** `bourbon.friendship_changed` | 구독 | 없음 |
| 유저 가입 (추천 대상 agent의 등장) | **있음** `bourbon.user_registered` (`CREATED → ACTIVATED` 전이에서 발행) | 구독 → `agents` row 생성 (§2-7) | 없음 |
| 유저 탈퇴 | **있음** `bourbon.user_deactivated` | 구독 → 전부 삭제 | 없음 |
| 타인 agent와 대화 시작 | **없음.** 대화는 `AGENT_DM` room(`A:B'`)이고 `ensure_agent_dm_room`이 find-or-create 하지만 이벤트는 없다 | bourbon-api의 일반 이벤트 `room_created`를 `room_type == agent_dm`으로 필터(§2-4, R46) | bourbon-api. 어트리뷰션 키는 클라이언트가 우리 route에 직접 보고한다(R47, 계약 §2-5) |
| 대화 진행(turn) | **있음** `bourbon.message_created` (`room_id, sender_id, sender_type, room_type=agent_dm`) | 대화 시작 이벤트의 `room_id`와 조인 | 없음 — **새 turn 이벤트가 필요 없다** |
| 성숙도 | topic 단위는 `score`(topic-api 임시). agent 단위는 컴포넌트 예정 | `score`를 feature로 | 컴포넌트가 생기면 (§2-6) |
| 요청자·소유자의 HEXACO 성향 벡터 | **없음.** bourbon-agent의 추출 노트(`PERSONA_EXTRACTION#note`)에 암호화되어 있고, 이벤트 필드가 없다(bourbon-agent에 API를 열 가능성은 없으므로 route는 선택지가 아니다, R42). topic-api는 persona 테이블을 복호화 키를 공유해 직접 읽지만 우리는 그렇게 하지 않는다(R42) | 코드에 자리만(R42): feature `persona_similarity`는 0 | bourbon-agent — **이벤트**로(확정 아님). 어느 이벤트·어느 필드·어느 시점인지는 O20 뒤에 요청 |

### rev 1 정정 — 설명과 코드가 다르다고 적었던 세 곳

1. ~~bourbon-agent → topic-api 이벤트 경로가 없다~~ → **있다, 그리고 진행 중이다(오너).** topic-api에 deferq 워커(`worker/`)가 있고 `bourbon.persona_updated`를 소비해 persona 동기화를 돌리며, 변경된 topic마다 `bourbon.topics_updated`를 발행한다. 워커는 prod에서 LLM 프록시 문제로 0 replicas다(README).
2. ~~agent visibility 필드가 없다~~ → 없는 것은 맞다. **R23(2026-09-09)**: 새 필드 `discoverable`로 결정. 이벤트 모양은 §2-3.
3. ~~타인 agent와의 대화는 group room~~ → **`AGENT_DM`이라는 room 종류가 따로 있다.** `A:B'` = A가 B의 agent와 대화하는 방향성 있는 방. 멤버 {A}, 착석 {A', B'}. group room 착석은 다른 경로다. 대화 시작의 자연스러운 지점은 `ensure_agent_dm_room`의 **create**다(re-enter는 상태 이벤트라 R46으로 제외).

### 새로 발견한 것 — 확인 필요

- **main에서 agent DM을 열려면 두 사람이 친구여야 한다** (`_assert_friends_to_open`). 원격 브랜치 `temp/agent-dm-open-without-friendship`(2026-09-02)이 그 게이트를 제거한다. **오너 답(2026-09-08)**: 친구가 아니어도, 어떤 방향으로든 대화를 시작할 수 있게 할 것이고 그 방법(방 종류)은 bourbon-api의 몫이다. DM으로 결정될 가능성이 크다. `room_created`(§2-4, R46)는 `room_type`을 싣는 일반 이벤트라 bourbon-api가 방 종류를 바꾸면 우리 필터 값만 바뀐다.
- **우리 워커가 미러하는 `bourbon.user_topic_updated`(`touched` 필드)는 topic-api에 없다.** 실제 이름은 `bourbon.topics_updated`이고 payload도 다르다. 우리 코드 쪽 정정 대상이다(§4).

---

## 1. topic-api에 지금 있는 것 (코드 기준)

```
bourbon-agent ──bourbon.persona_updated──▶ topic-api worker
                                            │ sync_user(): grounding, 쓰기
                                            ▼
                                   bourbon.topics_updated  ×(변경된 topic 수)
                                   {user_id, topic_id, persona_revision, topic_revision}
```

- `worker/listener.py` `on_persona_updated_sync_topics`: 동기화 뒤 `changed`가 비어 있지 않으면 `_announce`가 topic마다 `topics_updated`를 발행한다. best-effort — 발행 실패는 경고만 남긴다. docstring이 소비자 계약을 이렇게 적는다: **"a consumer that missed an event converges on its next read of the user's topics."** 즉 topic-api 스스로 이벤트를 **힌트**로 정의했다.
- `topic_revision` = 그 topic row의 카운터(`UserTopic.revision`). 읽어 온 row의 `revision`이 이 값 이상이면 이벤트가 말한 상태 이상이다.
- 같은 워커의 `worker/images.py`가 `topics_updated`를 소비해 이미지 작업을 한다. 소비자가 이미 하나 있어 이벤트가 살아 있다.
- **api 프로세스(gunicorn)에는 AMQP가 없다.** `PATCH /me/topics/{topic_id}`(visibility), `PUT /users/{id}/topics/{topic_id}/score`, `PUT /users/{id}/topics/scores/bulk`, `DELETE /users/{id}`, 카탈로그 병합은 모두 발행 없이 끝난다.
- 내부 조회 route `GET /users/{user_id}/topics`는 `visibility=` 쿼리(기본 `public`)로 tier를 고르고, 항목에 `score, visibility, revision, updated_at, support, descriptions`가 있다.

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

**우리 처리**: 리스너는 `user_id`만 꺼내 유저 단위 debounce(수 초, 상한 1분)를 걸고 끝. task가 `GET /api/internal/svc/topic/users/{id}/topics?visibility=public&visibility=friends`를 호출해 그 유저의 공개된 row를 **통째로 교체**한다(없어진 것 삭제, 새것 upsert). 한 동기화가 topic 10개를 변경해 이벤트 10건이 와도 재조회는 1회다.

**왜 스냅샷 이벤트를 요청하지 않나**: topic-api가 이미 "힌트 + 재조회"를 계약으로 정했고, 조회 route가 스냅샷 그 자체다. 우리가 필요한 스냅샷을 이벤트에 실어 달라고 하면 topic-api가 같은 조회를 발행 시점에 대신 하는 것뿐이다. 놓친 비공개 전환은 다음 힌트의 재조회가 고친다. 재조회가 하루에 한 번도 일어나지 않는 유저(비활성)는 어차피 바뀐 것이 없다.

**topic_revision 활용**: 재조회 결과의 row `revision`이 이벤트의 `topic_revision`보다 작으면(복제 지연) 잠시 뒤 한 번 더 조회한다. 그 이상이면 정상.

### 2-2. visibility 변경 신호 — topic-api에 "필요"만 요청, 형태는 topic-api가 정한다(R48)

비공개 전환(`public/friends → private/hidden`)은 **오직** `PATCH /me/topics/{topic_id}`로 일어나고 이 경로는 지금 아무것도 발행하지 않는다(api 프로세스에 AMQP 연결이 없다). 힌트가 없으면 유저가 비공개로 되돌린 topic이 다음 persona 동기화까지 추천에 남고, 대화하지 않는 유저에게는 그 "다음"이 오지 않는다. 응답 직전 재확인(계약 §5 불변식 4)은 우리 저장소를 다시 보는 것이라 이를 잡지 못한다. 이것이 요청의 핵심이다.

**우리가 필요한 것**: visibility가 바뀌면 `user_id`(가능하면 `topic_id`)가 담긴 이벤트 하나. 새 visibility 값은 필요 없다 — 우리는 어차피 재조회하고, 값이 있으면 소비자가 재조회를 생략하려는 유혹이 생긴다.

**형태는 topic-api가 정한다.** 플랫폼 기준(§0, "판정 기준이 명확하고 소비자가 여럿인 것만 새 타입으로")에 비추어 우리가 특정 타입을 요구하지 않는다. 보이는 길은 셋이고 우리 처리는 셋 모두 같다.

1. 기존 `bourbon.topics_updated`를 settings 쓰기에서도 발행한다. payload는 이미 `user_id, topic_id, topic_revision`을 갖는다. `persona_revision: PositiveInt`(persona 동기화의 출처 추적용 — 추출이 읽은 persona 슬롯 버전. 지금 읽는 소비자가 없고 우리도 읽지 않는다)를 어떻게 할지는 topic-api의 몫이다. **"타입 추가 신중" 기준에 가장 가깝다는 의견만 적는다.**
2. 마지막 추출 기록의 `persona_revision`을 그대로 실어 1과 같이 발행한다 — 스키마 변경 없음, 쓰기마다 읽기 하나.
3. 새 타입(예 `bourbon.user_topic_settings_updated` `{user_id, topic_id, topic_revision}`) — 처음 우리가 제안했던 안.

- **우리 처리**: §2-1과 같은 debounce → 재조회. 어느 형태든 같은 task로 모인다.
- **발행 지점**(어느 안이든): `api/routers/me_topics/router.py` `patch_my_topic` → `write_topic_settings` → 저장소 `write_settings`(UPDATED_NEW) 성공 뒤. best-effort 발행이라 브로커가 없어도 patch는 성공해야 한다.
- **전제 작업**: api 프로세스에 AMQP 연결. 워커의 `worker/amqp.py`를 api 프로세스 lifespan에도 붙이는 일이고, 설정 `DEFERQ_AMQP_URL`은 이미 있다(현재 "worker only").
- **우리 미러**: 답이 오기 전까지 `bourbon.user_topic_settings_updated` `{user_id, topic_id, topic_revision}`을 임시 이름으로 두고 CLI 발행으로 테스트한다. 형태가 정해지면 이름만 바꾼다(1안이면 `topics_updated` 리스너 하나로 합쳐진다).

### 2-3. `bourbon.personal_agent_visibility_changed` — 새 필드 `discoverable`(R23), bourbon-api에 요청

R23(2026-09-09): bourbon-api의 personal agent에 새 필드 `discoverable`(기본 false)을 두고 그 쓰기 지점에서 발행한다. 필드 정의가 뒤에 바뀌어도 우리가 받는 것은 같다.

```python
class PersonalAgentVisibilityChangedPayload(BaseModel):
    owner_user_id: UUID
    agent_id: UUID
    discoverable: bool               # 필드 이름이 무엇이든 "추천에 나올 수 있는가" 하나로 받는다
    occurred_at: AwareDatetime
```

발행 지점은 `discoverable`의 쓰기 지점(`personal_agents/service.py`). 탈퇴는 `user_deactivated`로 따로 오므로 겹쳐도 무해하다. **우리 처리**: `false` → 그 소유자의 공개된 row 전부 삭제 + `agents` 갱신. `true` → `agents`만 갱신하고 row는 다음 topic 재조회가 채운다(또는 즉시 재조회 1회).

플랫폼 기준(§0)으로 2026-09-10에 다시 봤고 **유지**한다(오너): 필드의 소유자가 bourbon-api고 변화를 알 다른 길은 폴링뿐이다. 유저가 쓰는 boolean 필드의 변경이라 `friendship_changed`와 같은 부류고 payload에 새 값만 실려 상태를 내포하지 않는다. 소비자는 지금 우리 하나지만 프로필·검색이 같은 값을 읽게 될 수 있다 — 요청서에 이 근거를 적는다.

### 2-4. `bourbon.room_created` — bourbon-api의 일반 이벤트, 우리는 `agent_dm`만 필터(R46)

대화 시작 = 타인의 agent와의 방이 **만들어졌을 때**. 지금 코드에서는 `ensure_agent_dm_room(actor_id, other_id)`의 create 분기(room row insert 커밋 뒤)다. 이미 있는 방을 다시 여는 find·re-enter 분기는 내지 않는다 — 재입장은 "전에 있었다"를 아는 상태 이벤트라 플랫폼 기준(§0)에 어긋나고, 우리에게 필요하면 `message_created` 간격으로 우리 안에서 계산한다.

처음 안은 우리 전용 `agent_dm_opened`(actor·owner·`reopened`·`entry`·`recommendation_id`)였다. 플랫폼 기준으로 다시 보면 단일 소비자 전용 이름에 상태 필드와 사후분석 필드가 실린 모양이라, **bourbon-api가 어느 소비자에게나 낼 수 있는 일반 이벤트**로 바꾼다. bourbon-api에는 지금 방 생성 이벤트가 없다(발행 중인 것은 `user_registered`·`user_deactivated`·`friendship_changed`·`message_created`·`message_translated`).

```python
class RoomAgentSeat(BaseModel):
    agent_id: UUID
    owner_user_id: UUID | None       # personal agent의 소유자. 소유자 없는 agent가 생기면 None

class RoomCreatedPayload(BaseModel):
    room_id: UUID
    room_type: str                   # RoomType 값: "user_dm" | "agent_dm" | "group"
    creator_id: UUID
    member_user_ids: list[UUID]
    agents: list[RoomAgentSeat]      # 생성 시점의 착석 agent
    occurred_at: AwareDatetime

room_created = Event("bourbon.room_created", RoomCreatedPayload)
```

**우리 처리**: `room_type == "agent_dm"`만 받는다. actor = `creator_id`, 소유자 = `agents` 중 `owner_user_id != creator_id`인 착석 agent의 소유자(agent DM에는 actor 자신의 agent도 착석하므로 둘 중 하나다). 착석 agent가 모두 creator 소유면 자기 agent 방이라 무시. `interactions`에 `(actor, owner, room_id, started_at)` 기록, `popularity[owner]` 증가, `agents.last_active_at` 갱신. `entry`·`recommendation_id`는 이 이벤트가 아니라 `attributions`(R47, 계약 §2-5)와의 조인으로 채운다.

**방 종류에 의존하지 않는다.** bourbon-api가 친구 게이트를 풀면서 방 종류나 경로를 바꿔도 payload는 그대로고 우리 필터 값만 바뀐다.

**기각 시 대안**(요청서에 같이 적는다):

- (a) bourbon-api **내부 route로 room 구성 조회** — `message_created`(`room_type=agent_dm`)의 첫 건에서 `room_id`로 1회 읽어 actor·소유자를 알아낸다. 모든 대화를 보고, DB 직접 접근이 아니다. 새 room당 호출 1회(10만 유저 기준 하루 수천 건).
- (b) agent DM의 room id는 `uuid5(DM_NAMESPACE, f"dm:user:{user_id}:agent:{agent_id}")`로 **결정론적**이다(`rooms/dm_identity.py`). 추천 시점에 후보별 room id를 계산해 결정 로그에 두고 `message_created`의 `room_id`와 매칭한다. 추천된 대화만 보이고(인기도·CF가 편향된다) bourbon-api의 id 규칙과 네임스페이스 상수에 결합되므로 마지막 수단.

### 2-5. `bourbon.message_created` — 있는 것으로 turn을 셈

```python
# bourbon-api messages/events.py 그대로 미러
room_id, message_id, sender_id, sender_type, type, room_type
```

`room_type == "agent_dm"`이고 `sender_type`이 유저인 메시지 = 그 방의 actor가 agent에게 한 turn. 리스너는 `room_type` 필터 뒤 **`room_turns[room_id]`를 +1만 한다**(R49). `room_created`(§2-4)와는 큐가 달라 순서 보장이 없으므로 카운터를 방 키로 독립시켜 어느 쪽이 먼저 와도 버리거나 보류할 것이 없게 한다. 읽는 쪽이 `room_id`로 `interactions`와 조인해 (actor, owner)를 얻고, `interactions` 행이 없는 방(우리가 시작을 놓쳤거나 우리 서비스 이전에 열린 방)은 조인에서 빠지며 `room_turns.orphan_ttl_days` 뒤 정리한다. **bourbon-agent에 turn 이벤트를 요청할 필요가 없다.**

### 2-6. `bourbon.agent_maturity_changed` — 컴포넌트가 생기면

```python
class AgentMaturityChangedPayload(BaseModel):
    owner_user_id: UUID
    maturity: float                  # 0~1
    maturity_version: int
    occurred_at: AwareDatetime
```

topic 단위는 재조회 결과의 `score`가 그 자리다. 컴포넌트가 `score`를 대체하든 새 필드를 추가하든 우리 변경은 feature 매핑 한 줄이다.

### 2-7. 이미 있어서 구독만

| 이벤트 | payload | 우리 처리 |
|---|---|---|
| `bourbon.friendship_changed` | `user_low, user_high, action, occurred_at` | `friends` 미러 갱신: `accepted` → `(user_low, user_high)` 삽입, `removed` → 삭제. 요청 시 조회 캐시는 두지 않는다(R17) |
| `bourbon.user_registered` | `user_id, email` | **추천 대상 agent의 등록.** `agents`에 `(owner_user_id, agent_id, discoverable=false, registered_at)` row를 만든다. agent id는 bourbon-api가 `uuid5(AGENT_NAMESPACE, f"personal_agent:{user_id}")`로 결정론적으로 만들므로 읽어 올 필요 없이 같은 규칙으로 계산한다(네임스페이스 상수를 공유하거나, 첫 `room_created`·공개 여부 이벤트에서 받은 `agent_id`로 채운다). **`email`은 저장도 로그도 하지 않는다** — payload에서 읽지 않는다. 이 row가 있어야 공개된 topic이 하나도 없는 agent도 "존재하는 대상"으로 세어지고, 콜드스타트 신규 agent 부스트와 타입 ③의 모집단 크기가 정의된다 |
| `bourbon.user_deactivated` | `user_id` | 그 유저의 공개된 row·agents·사전 계산·요청자 데이터 삭제. 상호작용 로그의 actor 쪽은 익명화 |
| `bourbon.persona_updated` | `user_id, revision, extracted_at, consumed_messages{room_id → from/to message_id}, changes[{layer: bio\|traits\|preferences, visibility: sharable\|private, topics{added, removed, changed} — preferences만}]` | 직접 사용하지 않는다. topic id가 없고 `changes[].topics`는 preferences 마크다운의 **헤딩 텍스트**다. `topics_updated`가 곧 온다는 뜻일 뿐. bourbon-agent가 **발행하는 유일한 이벤트**다(2026-09-10 코드 기준, `bourbon_agent/events.py`). persona 중 topic으로 오지 않는 레이어(HEXACO 추정치·자유 성향·traits 서술형 텍스트·bio)은 이 이벤트에도 실리지 않는다 — HEXACO 입력 경로는 O20(R42) |

### 2-8. 카탈로그 그래프 내부 route — 보류(R26). 필요해지면 topic-api에 요청

**R26(2026-09-09)**: route를 지금 요청하지 않는다. topic-api repo의 `data/catalog_dist/catalog.json`을 빌드 때 우리 이미지에 복사해 edge 테이블을 채우고, 카탈로그가 바뀌면 재배포한다. 카탈로그 `built_at`을 결정 로그에 기록하고, topic-api 응답에 우리 카탈로그가 모르는 topic_id가 오면 그 topic은 정확 일치만 적용하며 건수를 지표로 남긴다 — 어긋남이 잦아지면 아래 route를 요청한다. 아래는 그때 쓸 정의다.

이벤트가 아니라 조회다. content 유사도(R25)가 두 topic 사이의 카탈로그 거리(최단 hop)를 알아야 하는데, 카탈로그는 topic-api 이미지 안의 JSON 아티팩트(`data/catalog_dist/catalog.json`: topic 3,003개, parent edge 2,959개, 다중 부모 노드 10개의 DAG — 최단 hop이 필요한 이유)이고 이를 내주는 내부 route가 없다.

```
GET /api/internal/svc/topic/catalog/graph
→ { built_at, topics: [{topic_id, selectable}], edges: [{topic_id, parent_id}] }
```

- `selectable: false`(drawer 43개)는 유저가 가질 수 없는 노드라 일치 노드가 아니고 거리 계산의 통과 노드로만 쓴다.
- 확인 항목: 아티팩트의 topic에는 `status`와 병합 체인(`MAX_MERGE_HOPS` 16)이 있다. 병합·퇴역된 topic을 응답에서 빼는지, `status`를 함께 내주는지는 route를 정의할 때 topic-api와 정한다.
- 카탈로그는 빌드 때만 바뀌므로 워커가 하루 1회 읽어 `built_at`이 바뀌었을 때만 우리 edge 테이블을 교체한다.
- 아티팩트 파일을 우리 이미지에도 싣는 것이 R26이 택한 길이다. 두 서비스의 카탈로그 버전이 어긋날 수 있어 처음 안은 route를 권했지만, 어긋남은 위의 감지 규칙(`built_at` 기록, 모르는 topic_id 건수)으로 잡고 잦아지면 route를 요청한다.
- **검증(§3 방식)**: topic-api `topic/catalog/artifact.py`가 `edges: list[tuple[TopicId, TopicId]]`와 `built_at`을 이미 갖고 있고 `runtime/services.py`가 시작 시 메모리에 올리므로, route는 그 객체를 직렬화하는 일이다. 발행 지점 검증에 해당하는 "그 필드가 있는가"는 충족된다.

---

## 3. 발행 가능성 검증 — 그 repo가 그 지점에서 그 필드를 갖는가

| 이벤트 | 발행 repo · 지점 | 필드 | 그 지점에 있나 |
|---|---|---|---|
| visibility 변경 신호(R48, 형태는 topic-api 선택) | topic-api `api/routers/me_topics/router.py` `patch_my_topic`, `write_topic_settings` 반환 뒤 | `user_id` | ✅ `owner`(`OwnerId` = demo stand-in 적용 뒤 **실제 쓰인 id**). `viewer_id`는 응답에 echo되는 헤더 id라 쓰지 않는다 |
| | | `topic_id` | ✅ 경로 |
| | | `topic_revision` | ✅ `write_settings`(UPDATED_NEW)가 돌려주고 응답 `TopicWriteReceipt.revision`에 이미 실린다 |
| | | AMQP 연결 | ❌ api 프로세스에 없음 — **전제 작업** |
| `room_created` | bourbon-api `rooms/service.py` `ensure_agent_dm_room` create 분기, room 생성 트랜잭션 커밋 뒤(같은 자리의 `user_dm`·group 생성에서도 같은 이벤트) | `room_id, room_type, creator_id` | ✅ `room.id, room.type, actor_id` |
| | | `member_user_ids` | ✅ 같은 트랜잭션의 `RoomMember` row |
| | | `agents[{agent_id, owner_user_id}]` | ✅ `_seat(agent_id=…)` 둘(`actor_agent_id`, `target_agent_id`). 소유자는 `_ensure_personal_agent`가 받은 `user_id` |
| | | AMQP | ✅ bourbon-api는 `friends/events.py`가 같은 모양으로 발행 중 |
| `personal_agent_visibility_changed` | bourbon-api `personal_agents/service.py` — 새 필드 `discoverable`의 쓰기 지점(R23) | `owner_user_id, agent_id, discoverable` | ❌ 필드가 아직 없다 — **전제 작업**(필드 추가). `agent.id`, `owner_user_id`는 그 서비스에 있다 |
| `topics_updated` 소비 | — | — | ✅ 이미 발행 중. 우리 워커가 이름·payload를 맞춰야 함 |
| `message_created` 소비 | — | `room_type` | ✅ payload에 있다. 값은 `RoomType` enum(`user_dm, agent_dm, group`), 두 repo 주석도 같다. `sender_type`은 `user / agent / system` |
| `agent_maturity_changed` | 성숙도 컴포넌트 | — | 컴포넌트가 없어 검증 불가. 미룸 |
| 카탈로그 그래프 route(§2-8, R26으로 보류) | topic-api `topic/catalog/artifact.py`, `runtime/services.py`가 시작 시 메모리에 올림 | `built_at, topics, edges` | ✅ 아티팩트 객체가 셋 다 갖고 있다 — route는 직렬화만. 지금은 같은 파일을 빌드 때 복사한다 |

결론: **visibility 변경 신호와 `room_created`는 발행 지점에 필드가 다 있고, `personal_agent_visibility_changed`는 새 필드 `discoverable`이 전제다.** 막힌 것은 둘 — topic-api api 프로세스의 AMQP 연결, bourbon-api의 `discoverable` 필드(R23). 어트리뷰션은 다른 서비스를 거치지 않는다(R47).

---

## 4. agent-discovery-api에서 먼저 하는 일

1. **미러 정정**: `worker/events.py`의 `bourbon.user_topic_updated`(`touched`)를 실제 이름 `bourbon.topics_updated`(`user_id, topic_id, persona_revision, topic_revision`)로 바꾼다. 필터 조건 "`touched`에 visibility가 있을 때만"은 사라진다 — `topics_updated`는 persona 동기화로 변경된 topic이라 **항상** 재조회 대상이다.
2. **새 이벤트 셋을 우리 `worker/events.py`에 선언**한다(§2-2, §2-3, §2-4의 모양). 발신 repo가 아직 안 내도 큐는 만들어지고 비어 있을 뿐이다.
3. **CLI 발행 명령**: `cli publish topics-updated / topic-settings-updated / room-created / message-created …`로 로컬 RabbitMQ에 넣어 왕복을 테스트한다. 합성 데이터 생성기(재설계 §6-2)가 같은 발행기를 써서 10만 유저의 이벤트 스트림을 만든다.
4. **재조회 task 하나**: `topics_updated`와 visibility 변경 신호(임시 이름 `user_topic_settings_updated`, R48) 두 리스너가 같은 debounce → 같은 task로 모인다. task는 내부 route를 `visibility=public&visibility=friends`로 조회해 공개된 row를 교체한다. 지금 코드는 `public`만 조회한다(`agent_discovery/composition.py`의 요청 tier) — 한 줄 변경.
5. **turn 카운터**: `message_created`를 `room_type` 필터로 받아 `interactions`를 보강한다.
6. **카탈로그 edge 테이블**: R26대로 topic-api repo의 `catalog.json`을 빌드 때 복사해 edge 테이블을 채우고, R25의 hop 계산을 테스트한다. `built_at`을 결정 로그에 남긴다.
7. 위가 로컬에서 도는 것을 확인한 뒤 §6의 요청서를 낸다.

---

## 5. 오너 확인 항목

1. ~~agent DM의 친구 게이트~~ **답 있음(2026-09-08)**: 친구가 아니어도 대화를 시작할 수 있게 한다. 방법은 bourbon-api가 정하고(DM 유력), 우리 이벤트는 그에 맞춰 조정한다. 추천은 "public agent는 누구에게나 열린다"를 전제한다.
2. ~~agent 공개 여부의 필드~~ **답 있음(2026-09-09, R23)**: 새 필드 `discoverable`, 기본 false. §2-3.
3. ~~`recommendation_id`의 전달 경로~~ **답 있음(2026-09-09, R24 → 2026-09-10 R47로 개정)**: 클라이언트가 우리 route `POST /attributions`에 직접 보고한다. 계약 §2-5.
4. ~~재조회 tier 범위~~ **답 있음(2026-09-09, R22)**: 타인 row는 `visibility=public&visibility=friends`만 조회해 저장한다. 요청자 자신의 프로필은 `public`·`friends`·`private`이고 `hidden`은 읽지 않는다. 어디서 읽나는 R27 — 요청 시 topic-api 조회. 소유자 키 아래에만 두는 미러는 지연 시간이 문제될 때의 대안.
5. **topic-api 워커 0 replicas**: prod에서 persona 동기화가 안 돌면 `topics_updated`도 없다. 우리 테스트는 dev에서 하되, prod 시점에는 이 전제가 풀려 있어야 한다.
6. ~~재활성 이벤트가 없다~~ **답 있음(2026-09-09, R38)**: 탈퇴 뒤 재가입은 신규 가입으로 본다. 재활성 기획이 생기면 수정. bourbon-api에는 `user_registered`(활성화 전이)와 `user_deactivated`만 있고, 탈퇴 뒤 돌아오는 유저를 알리는 이벤트는 없다. 조용히 재활성되는 경로가 있으면 우리 `agents` row가 없는 채로 topic 이벤트가 오므로, 재조회 task가 `agents` row를 **없으면 만든다**로 방어한다.

---

## 6. 요청서로 자를 때의 단위

그대로 붙여 넣을 수 있는 문장으로 푼 요청서는 `requests/`에 있다(R43): `infra.md`, `bourbon-api.md`, `client.md`, `bourbon-agent.md`, `bourbon-topic-api.md`. 보내는 순서와 시점은 `requests/README.md`.

| 받는 곳 | 묶음 | 선행 |
|---|---|---|
| topic-api | api 프로세스 AMQP 연결 + visibility 변경 신호 발행(`patch_my_topic` 1곳, 형태는 topic-api 선택 — R48) | 바로 가능. 카탈로그 route는 보류(R26) |
| bourbon-api | 일반 이벤트 `room_created` 발행(방 생성 커밋 뒤, R46); `personal_agent_visibility_changed`(새 필드 `discoverable`, R23) | R23·R46 |
| 클라이언트 | 카드에서 대화를 시작할 때 우리 route `POST /attributions`에 `recommendation_id`·`owner_user_id`·`entry` 보고(R47). 타입 ②③은 우리 응답에서, 타입 ①은 bourbon-agent 카드의 meta에서 받는다 | R47 |
| bourbon-agent | 타입 ① 호출을 새 계약으로(요청자 = 실제 말한 사람. 자기 agent에게 묻는 경우 소유자와 같다. 타인의 agent 방에서 묻는 경우가 제품에 있다면 그 사람이어야 하는데, 지금 코드는 항상 agent 소유자를 보낸다), 응답의 `recommendation_id`를 카드 meta에 실어 전달(R24·R47 — 클라이언트가 meta에서 읽어 우리 route에 보고한다). **HEXACO 성향 벡터를 싣는 이벤트 필드는 이 묶음에 넣지 않는다** — 이벤트로 받는다는 방향만 있고(R42, bourbon-agent에 API는 열지 않는다) 무엇을 내보낼지·동의 범위가 O20에서 정해진 뒤 별도 요청 | 계약 확정 · R47 · (HEXACO는 O20 뒤) |
| 성숙도 컴포넌트 | `agent_maturity_changed` | 컴포넌트 존재 |
