# bourbon-api 요청서 — agent 공개 여부와 방 생성 이벤트

> 코드 읽은 기준: bourbon-api main `c4c3300`(2026-09-08), 발행 이벤트 목록 2026-09-10(`user_registered`·`user_deactivated`·`friendship_changed`·`message_created`·`message_translated`). 결정: R23(`discoverable`), R46(일반 이벤트 `room_created`), R47(어트리뷰션은 우리가 직접 받는다 — bourbon-api에 부탁하지 않는다). 이 요청이 **가장 먼저**다 — 방 생성 이벤트가 없는 기간의 대화는 "언제 누가 누구와 시작했는지"가 우리에게 영구히 없고 소급할 수 없다.

플랫폼의 이벤트 추가 기준(판정 기준이 명확하고 소비자가 여럿, stateless, 단일 소비자·사후분석은 그 서비스 안에서)에 맞춰 2026-09-10에 다시 쓴 요청이다. 처음 안에 있던 우리 전용 이벤트 `agent_dm_opened`, 상태 필드 `reopened`, route 파라미터 `recommendation_id`·`entry`는 **모두 뺐다.**

## 1. personal agent에 새 필드 `discoverable` (기본 `false`) + 이벤트

**무엇**: personal agent 모델에 boolean `discoverable`을 추가해 주시면 된다. 기본값 `false`. 의미는 "타인에게 추천 목록에 나올 수 있는가"다. `enabled`를 재사용하지 않는 이유: `enabled=false`는 agent가 동작하지 않는다는 뜻이고, "쓰되 목록에는 안 올린다"는 다른 선택이다(R23).

**어디**: 쓰기 지점은 `personal_agents/service.py`(agent 설정을 바꾸는 함수). 클라이언트가 값을 바꾸는 route는 bourbon-api가 정한다 — 우리는 route 모양에 의존하지 않는다.

**이벤트**: 값이 바뀔 때마다 발행해 주시면 된다(같은 값을 다시 써도 발행하지 않아도 된다).

```python
class PersonalAgentVisibilityChangedPayload(BaseModel):
    owner_user_id: UUID
    agent_id: UUID
    discoverable: bool
    occurred_at: AwareDatetime

personal_agent_visibility_changed = Event("bourbon.personal_agent_visibility_changed", PersonalAgentVisibilityChangedPayload)
```

**이벤트 기준에 비추어**: 유저가 쓰는 boolean 필드의 변경이라 판정이 명확하고, payload에는 새 값만 있어 상태를 내포하지 않는다 — `friendship_changed`와 같은 부류다. 소비자는 지금 우리 하나지만, 필드의 소유자가 bourbon-api고 변화를 알 다른 길은 폴링뿐이어서 이벤트로 부탁한다. 프로필·검색이 같은 값을 읽게 되면 소비자가 늘어난다.

**우리 처리**: `false` → 그 소유자의 공개 topic row 전부 삭제. `true` → 다음 topic 재조회가 채운다. 탈퇴(`user_deactivated`)와 겹쳐도 문제없다.

## 2. 방 생성 이벤트 `bourbon.room_created` (일반 이벤트)

**무엇**: 방 row가 만들어져 커밋된 뒤 발행해 주시면 된다. 우리 전용 이름이 아니라 **어느 소비자에게나 낼 수 있는 일반 이벤트**로 부탁한다 — 방 생성은 지금 이벤트가 없고, 소유자 알림·분석 등 다른 소비자가 있을 수 있는 사실이다. 지금 코드에서는 `ensure_agent_dm_room`·`ensure_user_dm_room`의 create 분기와 group 생성이다. 이미 있는 방을 다시 열거나 다시 들어오는 분기(find, re-enter)는 **발행하지 않는다** — 재입장은 "전에 있었다"를 알아야 하는 상태라 이벤트로 적절하지 않다.

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

- `agents[].owner_user_id`를 부탁하는 이유: agent DM에는 만든 사람의 agent와 상대의 agent가 함께 착석하므로, 소유자가 있어야 "누구의 agent와 대화를 시작했나"가 payload만으로 정해진다. `agent_id`만 주시는 쪽이 편하면 우리가 personal agent id 규칙으로 역산해야 하는데, 그러면 `AGENT_NAMESPACE` 상수를 공유해야 한다 — 어느 쪽이 나은지 알려 주시면 된다.
- 이벤트 이름·필드 이름은 bourbon-api 용어에 맞춰 바꾸셔도 된다. 바꾸실 때 알려 주시면 미러를 맞춘다.
- 우리는 `room_type == "agent_dm"`만 읽고, 착석 agent가 모두 creator 소유인 방(자기 agent 방)은 무시한다.

**우리 처리**: `interactions`에 (creator, 상대 agent의 소유자, room_id, started_at) 기록, 인기도 증가. 이 이벤트가 CF 학습 입력의 시작점이다. 추천 어트리뷰션(`recommendation_id`)은 **bourbon-api에 부탁하지 않는다** — 클라이언트가 우리 route에 직접 보고하고 우리가 이 이벤트와 잇는다(R47).

**이 요청이 어려울 때의 대안** — 알려 주시면 우리가 맞춘다:

- (a) room 구성을 돌려주는 **내부 route**(`room_id` → `room_type`, 멤버, 착석 agent와 소유자). 우리는 `message_created`의 첫 건에서 방마다 1회 호출한다. 새 방당 1회라 부담이 작다.
- (b) 아무것도 없으면 agent DM room id가 `uuid5(DM_NAMESPACE, "dm:user:{user}:agent:{agent}")`로 결정론적인 점을 써서, 추천한 상대별 room id를 우리가 미리 계산해 `message_created`와 매칭한다. 추천을 거치지 않은 대화는 못 보고 `DM_NAMESPACE`에 결합되므로 우리가 원하는 길은 아니다.

## 3. 그대로 쓰는 것 (변경 요청 없음)

- `bourbon.friendship_changed` (`user_low, user_high, action, occurred_at`) — 친구 미러(R17).
- `bourbon.user_registered` (`user_id`, `email`) — 추천 대상 agent row 생성. **`email`은 읽지 않는다.**
- `bourbon.user_deactivated` (`user_id`) — 전부 삭제.
- `bourbon.message_created` (`room_id, message_id, sender_id, sender_type, type, room_type`) — `room_type == agent_dm`인 유저 메시지를 turn으로 센다. 새 turn 이벤트는 필요 없다.
- 대화 시작 route(`POST /rooms/dm/{user_id}/agent`) — **파라미터 추가를 요청하지 않는다.**

## 4. 확인 질문

1. §1 — `discoverable`의 클라이언트 노출(설정 화면)은 bourbon-api·클라이언트가 정한다. 우리는 이벤트만 받는다. 필드 이름이 달라져도 payload의 `discoverable` 하나로 받으니 알려만 주시면 된다.
2. §2 — 친구가 아니어도 방을 만들 수 있게 하는 변경(오너 2026-09-08)을 언제 하는지. 추천은 "public agent는 누구에게나 열린다"를 전제한다.
3. §2 — `agents[].owner_user_id`를 실을지, `agent_id`만 실을지.
4. §2 — group 방과 user DM에도 같은 이벤트를 내는 것이 bourbon-api 쪽에서 자연스러운지(우리는 `agent_dm`만 읽지만, 일반 이벤트로 부탁하는 취지에 맞는지 확인).
