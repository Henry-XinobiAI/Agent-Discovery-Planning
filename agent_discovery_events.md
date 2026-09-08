# agent-discovery-api 이벤트 정의서 — 받을 것, 요청할 것, 보낼 곳

> `agent_discovery_redesign.md` §9의 3번, `agent_discovery_contract.md` §9-1을 발신 측에 붙일 수 있는 형태로 푼 것. 코드 조사는 2026-09-08(topic-api, bourbon-api, bourbon-agent 세 repo). 각 항목은 그 repo에 PR로 넣거나 담당에게 요청하는 단위다.
>
> 초안이고 발신하지 않았다. §5의 확인 항목에 오너 답이 붙으면 repo별 요청서로 잘라 낸다.

---

## 0. 한눈에

| 우리가 필요한 것 | 지금 있나 | 누가 | 어떻게 |
|---|---|---|---|
| 유저의 열린 topic 집합 (public·friends, 점수 포함) | **없음.** topic-api는 이벤트를 하나도 내지 않고 브로커 의존성도 없다 | topic-api | deferq 도입 + `bourbon.user_topics_snapshot` (§2-1) |
| agent 공개 여부 | **모델에 없음.** bourbon-api `Agent`에는 `enabled`만 있고 visibility 필드가 없다 | bourbon-api | 필드 추가 + `bourbon.personal_agent_visibility_changed` (§2-2) |
| friend 관계 변화 | **있음** `bourbon.friendship_changed` | bourbon-api | 구독만 |
| 유저 탈퇴 | **있음** `bourbon.user_deactivated` | bourbon-api | 구독만 → 그 유저 row 전부 삭제 |
| 타인 agent와 대화 시작 (귀속 키 포함) | **없음.** 착석 시 system message만 있고 이벤트 없음 | bourbon-api | `bourbon.personal_agent_seated` + 착석 route가 `recommendation_id`를 받아 실음 (§2-3) |
| 대화 진행(turn) | **없음.** `bourbon.message_created`는 있지만 "어느 agent에게"가 없다 | bourbon-agent (권고) 또는 bourbon-api | `bourbon.personal_agent_turn` (§2-4) |
| topic·agent 성숙도 | topic-api에 `score`만 있음(임시). "maturity"라는 것은 어디에도 없다 | 성숙도 컴포넌트(예정) | 스냅샷에 `score`로 받고, 컴포넌트가 생기면 `bourbon.agent_maturity_changed` (§2-5) |
| 타입 ① 요청자 = 실제 말한 사람 | **아님.** bourbon-agent는 `requester_user_id`에 agent 주인을 넣는다 | bourbon-agent | 새 계약으로 호출 변경 시 함께 (§2-6) |

### 설명과 코드가 다른 세 곳 — 확인 필요

1. **bourbon-agent → topic-api 이벤트 경로가 코드에 없다.** 오너 설명은 "agent가 추출하면 이벤트를 던지고 topic-api가 받아 grounding"인데, topic-api에는 어떤 이벤트 소비자도 없고(`pyproject.toml`에 deferq·aio-pika 없음), grounding 입구는 REST `POST /users/{user_id}/persona-topics`다. 그 route의 주석이 호출자로 `bourbon_agent.topic_sync.listener`를 지목하지만 **그 모듈은 bourbon-agent에 없고**, bourbon-agent는 topic-api를 어디서도 참조하지 않는다(`TOPIC_API_URL` 없음). bourbon-agent가 내는 `bourbon.persona_updated`는 있다(`revision`, 바뀐 preference 제목의 added/removed/changed). **이 연결을 누가 언제 만드는지**에 따라 §2-1의 발행 지점이 달라진다.
2. **agent visibility가 bourbon-api 모델에 없다.** "topic 하나라도 public이면 agent도 public" 규칙이 코드 어디에도 없다. 클라이언트 표시 규칙인지, 아직 미구현인지 확인이 필요하다. 우리는 이 값을 유도하지 않고 받기로 했으므로(재설계 §1-1) **필드와 이벤트가 생겨야 한다.**
3. **타인 agent와의 대화는 GROUP room에서 일어난다.** DM에는 자기 agent만 앉힐 수 있고(`ThirdPartyPersonalAgentError`), group room 주인이 타인 agent를 앉힌다. "대화 시작"의 자연스러운 지점은 **착석**(`POST /rooms/{room_id}/personal-agents`)이지 첫 메시지가 아니다. 탐색 탭에서 "대화 시작"을 누르면 클라이언트가 실제로 무엇을 호출하는지(새 group room 생성 + 착석?) 확인이 필요하다.

---

## 1. 원칙 — 이전 제안에서 이어받은 것

1. **델타가 아니라 현재 전체 집합 + `revision`.** "topic 추가됨/닫힘"을 받으면 한 건만 잃어도 영구히 어긋난다. "이 유저의 지금 열린 집합은 이것"을 받으면 순서는 최대 revision 채택으로 끝나고 중복은 무해하다. 발신 측 수용은 2026-09-01에 확인돼 있다. **이것이 재설계 §3-2의 "주기적 대조"를 대체한다** — 놓친 닫힘은 다음 스냅샷이 고친다.
2. **판단값이 아니라 셀 수 있는 것.** 상류가 공식을 바꾸면 우리 feature가 조용히 움직인다. 단, 지금 topic-api의 `score`는 임시 성숙도로 받는다(오너). 이름을 `score`로 그대로 받고 우리 쪽에서 `topic_maturity` feature로 해석한다. 공식이 바뀌면 `score_version`을 같이 올려 달라고 요청한다.
3. **행동 이벤트에 귀속 키를 처음부터.** `recommendation_id` 없는 대화 시작은 "무엇을 보여줬기 때문에 생겼나"를 영구히 알 수 없다. `(요청자, agent, 시간창)` 조인은 오귀속을 측정할 방법이 없다. **소급 불가 항목이라 가장 먼저 닫는다.** 키는 우리가 응답에 실어 보낸 값을 그대로 돌려받는 것이고 발신 측이 만들지 않는다.
4. **과거 로그의 `topic_id`는 재작성하지 않는다.** topic 병합·분할이 일어나면 매핑 테이블로 해석한다. 지금 정해도 비용이 없고 선택지를 보존한다.
5. **deferq 관례를 따른다.** `Event[Payload]("bourbon.<name>", Payload)`, dataclass payload, best-effort 발행(트랜잭션 커밋 뒤, 실패는 로그만), at-least-once, 소비자 멱등. 소비자는 예외를 내면 이벤트를 영구히 잃으므로 재시도는 소비자 안에서 한다.

---

## 2. 요청 항목

### 2-1. topic-api — `bourbon.user_topics_snapshot`

**전제 작업**: deferq와 AMQP 설정을 topic-api에 도입한다(현재 없음). bourbon-api의 `friends/events.py`·`amqp.py`가 복사할 모양이다.

```python
@dataclass
class UserTopicSnapshotItem:
    topic_id: str
    visibility: str          # "public" | "friends" | "private"  (hidden은 싣지 않음)
    score: float             # topic-api가 지금 계산하는 값. 임시 성숙도
    score_version: int       # 공식이 바뀌면 올림
    updated_at: str          # ISO 8601

@dataclass
class UserTopicsSnapshotPayload:
    user_id: str
    revision: int            # 유저 단위 단조 증가. 같은 revision 재전송은 무해
    occurred_at: str
    topics: list[UserTopicSnapshotItem]

user_topics_snapshot = Event("bourbon.user_topics_snapshot", UserTopicsSnapshotPayload)
```

**tier 범위 — 선택지 둘, 오너 판단(§5-1)**

| | (a) public·friends만 | (b) public·friends·private |
|---|---|---|
| 우리 저장소 | 열린 row만. private는 우리 쪽에 존재하지 않는다 | 열린 row + 요청자 자신의 topic 목록(`requester_topics`). private는 **주인 키 아래에만** 저장되고 후보 조회에는 절대 쓰이지 않는다 |
| 타입 ② 섹션, 타입 ③ content 질의 | 요청자의 topic 목록을 **요청 시 topic-api에서 읽는다** (내부 route 있음, 짧은 캐시). 지연 수십 ms 추가. 타입 ③ 사전 계산 배치가 유저마다 topic-api를 부른다 | 우리 저장소에서 읽는다. 요청 시 외부 호출 없음 |
| 보호 | 가장 강하다: 받지 않은 것은 샐 수 없다 | 유출 표면이 생긴다. 조회 경로 분리와 테스트로 막아야 한다 |

권고는 **(a)로 시작**한다. 타입 ②③의 요청자 topic은 topic-api 내부 route로 읽고, 지연이 문제로 측정되면 (b)로 넓힌다. 넓히는 것은 필드 하나 추가라 값싸고, 좁히는 것은 저장된 데이터를 지우는 일이라 비싸다.

**발행 지점** — 유저의 topic이 바뀌는 모든 쓰기 뒤. 스냅샷이므로 무엇이 바뀌었는지 알 필요 없이 **쓰기 뒤 그 유저의 현재 트리를 읽어 보낸다.**

| 쓰기 | 어디 | 비고 |
|---|---|---|
| 유저가 visibility 변경 | `PATCH /me/topics/{topic_id}` → `patch_settings` | 유일한 유저 주도 visibility 변경. 이전 값을 읽지 않는데(`ALL_NEW`), 스냅샷이라 필요 없다 |
| 점수 갱신 | `PUT /users/{id}/topics/{topic_id}/score`, `POST /users/{id}/scores` | |
| persona 동기화 | `POST /users/{id}/persona-topics` → `sync_persona_topics` | topic 추가·퇴출·이동이 한 번에 일어남. **한 번의 스냅샷**으로 충분 |
| 유저 삭제 | `DELETE /users/{id}` | `topics: []`인 스냅샷, 또는 `bourbon.user_deactivated` 구독으로 대체 |
| 카탈로그 병합 | `topic/user_topics/migration.py` | 영향받는 유저마다 스냅샷. 원칙 4에 따라 우리 로그는 재작성하지 않음 |

같은 유저에 쓰기가 몰리면 발행을 유저 단위로 짧게 모아도 된다(수 초). 스냅샷이므로 마지막 것만 유효하다.

**우리 처리**: `revision`이 저장된 것보다 크면 그 유저의 열린 row를 **스냅샷으로 통째로 교체**한다(있던 것 중 없는 것은 삭제, 새것은 upsert). 작거나 같으면 무시. 이것으로 재설계 §3-2의 닫힘 처리와 대조가 한 번에 끝난다.

### 2-2. bourbon-api — agent visibility 필드와 `bourbon.personal_agent_visibility_changed`

**전제 확인(§5-2)**: visibility가 어디에 있는지. 지금 `Agent` 모델에는 `enabled`, `owner_user_id`만 있다.

```python
@dataclass
class PersonalAgentVisibilityChangedPayload:
    owner_user_id: str
    agent_id: str
    visibility: str          # "public" | "private"
    occurred_at: str
```

발행 지점은 그 필드가 바뀌는 곳(유저가 바꾸든 규칙이 바꾸든). `disable_for_user`(탈퇴)도 `private`로 한 번 낸다. **우리 처리**: `private` → 그 주인의 열린 row 전부 삭제 + `agents` 갱신. `public` → `agents`만 갱신(row는 topic 스냅샷이 채운다).

### 2-3. bourbon-api — `bourbon.personal_agent_seated` + 착석 route의 `recommendation_id`

타인 agent와의 대화는 group room 착석으로 시작된다. 착석 route 둘(`POST /rooms/{room_id}/personal-agents`, 일괄 `POST …/personal-agents/bulk`)이 지금 system message `personal_agent_added`만 남긴다.

```python
@dataclass
class PersonalAgentSeatedPayload:
    room_id: str
    agent_id: str
    owner_user_id: str        # agent 주인
    actor_user_id: str        # 앉힌 사람 = 대화를 시작한 사람
    entry: str                # "recommend_explicit" | "discover_by_topic" | "discover_for_you" | "direct" | "unknown"
    recommendation_id: str | None   # 우리 응답의 값을 클라이언트가 그대로 넘긴 것
    occurred_at: str
```

`actor_user_id == owner_user_id`(자기 agent를 자기 방에)는 내지 않는다. 짝인 `personal_agent_unseated`는 지금 필요 없다.

**귀속 키의 여행**: 우리 응답 `recommendation_id` → 클라이언트 → 착석 요청 body(선택 필드 `recommendation_id`, `entry`) → 이 이벤트. **클라이언트 변경이 같이 필요하다.** 이 사슬이 하나라도 끊기면 `recommendation_id: null`로 오고, 그 대화는 "추천이 만들었는지 모름"으로 영구히 남는다(원칙 3).

### 2-4. 대화 진행 — `bourbon.personal_agent_turn`

시작만 있으면 "한 번 눌러 보고 나감"과 "오래 대화함"이 같다. turn을 받아 가중치 재료로 쓴다.

```python
@dataclass
class PersonalAgentTurnPayload:
    room_id: str
    agent_id: str
    owner_user_id: str
    speaker_user_id: str      # 이 turn에서 말한 사람. owner와 같으면 내지 않음
    occurred_at: str
```

**발행 주체 — 둘 중 하나, 오너 판단(§5-3)**

| | bourbon-agent | bourbon-api |
|---|---|---|
| 근거 | 이미 turn마다 `resolve_mode`로 `SHARED`(주인 없이 타인이 대화)·`ACCOMPANYING`을 판정하고, `room_members`와 마지막 `sender_id`로 speaker를 안다 | `bourbon.message_created`를 이미 낸다(`room_id, sender_id, sender_type`). 방의 `RoomAgent`를 알므로 "이 방의 personal agent"를 붙일 수 있다 |
| 장점 | "어느 agent가 이 turn에 응답했나"를 정확히 안다. 방에 agent가 둘이어도 맞다 | 발행 코드가 이미 있어 필드 추가에 가깝다 |
| 단점 | 이벤트 발행 코드가 한 곳(`persona_updated`)뿐이라 새로 붙인다 | 방에 personal agent가 둘이면 어느 쪽에 말했는지 모른다 |

권고는 **bourbon-agent**. 대화가 실제로 일어난 곳이 응답을 낸 곳이다. 대안으로 `message_created`에 `room_type`이 이미 있으니 우리가 그것을 받아 room 착석 이벤트(§2-3)와 조인해 근사할 수도 있다. 이 경우 새 이벤트 없이 시작할 수 있으나 agent가 둘인 방은 틀린다.

### 2-5. 성숙도 컴포넌트(예정) — `bourbon.agent_maturity_changed`

```python
@dataclass
class AgentMaturityChangedPayload:
    owner_user_id: str
    maturity: float          # 0~1
    maturity_version: int
    occurred_at: str
```

topic 단위 성숙도는 §2-1 스냅샷의 `score`가 자리다. 컴포넌트가 생기면 topic-api가 그 값을 `score` 자리에 쓰든, 스냅샷에 `maturity` 필드를 추가하든 둘 다 우리 쪽 변경은 feature 매핑 한 줄이다.

### 2-6. bourbon-agent — 타입 ① 호출을 새 계약으로

지금 `AgentDiscoveryClient.recommend`는 `requester_user_id=payload.owner_user_id`를 보낸다. `SHARED` 모드(타인이 주인 없는 방에서 agent와 대화)에서는 **실제로 물어본 사람이 요청자로 가지 않는다.** 새 계약 `POST /recommend/explicit`으로 바꾸면서:

- `user_id` = **실제 말한 사람**(마지막 `sender_id`). 본인 제외와 friends 필터가 이 사람 기준이다.
- `topic_text`, `context`, `max_results`, `room_id`, `lang`은 지금과 같은 뜻.
- 응답의 `recommendation_id`를 agent가 카드에 실어 클라이언트까지 보내야 §2-3의 사슬이 이어진다. **이 값이 agent 응답 → 클라이언트로 어떻게 전달되는지**는 확인 항목(§5-4).

---

## 3. 이미 있어서 구독만 하는 것

| 이벤트 | payload | 우리 처리 |
|---|---|---|
| `bourbon.friendship_changed` | `user_low, user_high, action(accepted/removed), occurred_at` | friends 미러 갱신, 또는 요청 시 조회 캐시 무효화 |
| `bourbon.user_deactivated` | `user_id` | 그 유저의 열린 row·agents·requester 데이터·사전 계산 전부 삭제. 상호작용 로그의 viewer 쪽은 익명화 |
| `bourbon.persona_updated` | `user_id, revision, changes[…]` (preference 제목 diff, topic id 아님) | 직접 쓰지 않는다. topic id가 없어 후보 갱신에 못 쓴다. §5-1의 연결이 정해지면 "곧 스냅샷이 온다"는 힌트 정도 |
| `bourbon.message_created` | `room_id, message_id, sender_id, sender_type, room_type` | §2-4의 대안 경로에서만 |

---

## 4. 우리 소비자의 규칙

- 이벤트마다 소비자 하나, 모듈 하나. 리스너는 검증하고 스케줄만 하고 일은 task가 한다(bourbon-agent `persona_extractor`의 모양).
- 스냅샷은 `revision` 비교로 멱등. 행동 이벤트는 `(room_id, agent_id, speaker, occurred_at)`로 중복 제거.
- 파싱 불가 payload는 버리고 기록한다(재시도해도 같다). 저장소 실패는 소비자 안에서 재시도한다(deferq는 재시도하지 않는다).
- **어떤 payload에도 유저의 글은 없다.** 스냅샷의 `topic_id`는 카탈로그 id다. 있어도 로그에 싣지 않는다.

---

## 5. 오너 확인 항목

1. **스냅샷 tier 범위**: (a) public·friends만 + 요청자 topic은 요청 시 조회, (b) private까지 실어 우리 저장소에 주인 키로만 보관. 권고 (a).
2. **agent visibility의 소재**: bourbon-api 모델에 없다. 어디서 만들 것인가, "topic 하나라도 public이면 agent public" 규칙은 누가 계산하는가.
3. **turn 이벤트 발행 주체**: bourbon-agent(권고) / bourbon-api / `message_created` 근사로 시작.
4. **`recommendation_id`의 여행**: 타입 ①은 agent 응답 카드 → 클라이언트 → 착석 요청, 타입 ②③은 목록 → 클라이언트 → 착석 요청. 클라이언트와 bourbon-agent 양쪽 변경이 필요하다. 이 사슬을 지금 요청할 것인가.
5. **bourbon-agent → topic-api 연결**: 코드에 없다. 누가 만드는 중인가. 스냅샷 발행 지점(§2-1 표)은 그 연결의 모양과 무관하게 topic-api의 쓰기 뒤이므로 우리 요청은 영향받지 않지만, "이벤트가 안 온다"의 원인을 갈라 두어야 한다.
6. **탐색 탭 "대화 시작"의 실제 호출**: 새 group room 생성 후 착석인가. 착석 route 하나에 `recommendation_id`를 붙이면 되는지, room 생성 route에도 붙여야 하는지.

---

## 6. 요청서로 자를 때의 단위

| 받는 곳 | 묶음 | 선행 조건 |
|---|---|---|
| topic-api | deferq 도입 + `user_topics_snapshot` 발행(5개 쓰기 지점) | §5-1 |
| bourbon-api | visibility 필드 + `personal_agent_visibility_changed`; `personal_agent_seated` + 착석 route에 `recommendation_id`·`entry` | §5-2, §5-6 |
| bourbon-agent | `personal_agent_turn` 발행; 타입 ① 호출을 새 계약으로(요청자 = 말한 사람, `recommendation_id` 전달) | §5-3, §5-4 |
| 클라이언트 | 착석 요청에 `recommendation_id`·`entry` 실기 | §5-4, §5-6 |
| 성숙도 컴포넌트 | `agent_maturity_changed` | 컴포넌트 존재 |
