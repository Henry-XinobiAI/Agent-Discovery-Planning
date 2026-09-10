# bourbon-api 요청서 — agent 공개 여부와 대화 시작 이벤트

> 코드 읽은 기준: bourbon-api main `c4c3300`(2026-09-08). 결정: R23(`discoverable`), R24(`recommendation_id` 전달), R15(대화 시작은 bourbon-api의 방 열기에서). 이 요청이 **가장 먼저**다 — `recommendation_id`가 이벤트에 실리지 않은 기간의 대화는 "추천이 만들었는지 모름"으로 영구히 남고 소급할 수 없다.

## 1. personal agent에 새 필드 `discoverable` (기본 `false`) + 이벤트

**무엇**: personal agent 모델에 boolean `discoverable`을 추가한다. 기본값 `false`. 의미는 "타인에게 추천 목록에 나올 수 있는가"다. `enabled`를 재사용하지 않는 이유: `enabled=false`는 agent가 동작하지 않는다는 뜻이고, "쓰되 목록에는 안 올린다"는 다른 선택이다(R23).

**어디**: 쓰기 지점은 `personal_agents/service.py`(agent 설정을 바꾸는 함수). 클라이언트가 값을 바꾸는 route는 bourbon-api가 정한다 — 우리는 route 모양에 의존하지 않는다.

**이벤트**: 값이 바뀔 때마다 발행한다(같은 값으로의 쓰기는 내지 않아도 된다).

```python
class PersonalAgentVisibilityChangedPayload(BaseModel):
    owner_user_id: UUID
    agent_id: UUID
    discoverable: bool
    occurred_at: AwareDatetime

personal_agent_visibility_changed = Event("bourbon.personal_agent_visibility_changed", PersonalAgentVisibilityChangedPayload)
```

**우리 처리**: `false` → 그 소유자의 공개 topic row 전부 삭제. `true` → 다음 topic 재조회가 채운다. 탈퇴(`user_deactivated`)와 겹쳐도 무해하다.

## 2. 타인 agent와의 대화 시작 이벤트 `agent_dm_opened` + route 파라미터

**무엇**: `ensure_agent_dm_room(actor_id, other_id)`의 **create와 re-enter 분기**에서 발행한다. 이미 들어 있는 방을 다시 여는 find 분기는 내지 않는다(시작이 아니다). `actor_id == other_id`(자기 agent)는 내지 않는다.

```python
class AgentDmOpenedPayload(BaseModel):
    room_id: UUID
    actor_user_id: UUID              # 대화를 시작한 사람
    owner_user_id: UUID              # 상대 agent의 소유자
    agent_id: UUID                   # 상대 agent
    reopened: bool                   # False = 방 생성, True = 재입장
    entry: str                       # "recommend_explicit" | "discover_by_topic" | "discover_for_you" | "direct" | "unknown"
    recommendation_id: UUID | None   # 우리 응답의 값을 클라이언트가 그대로 넘긴 것
    occurred_at: AwareDatetime

agent_dm_opened = Event("bourbon.agent_dm_opened", AgentDmOpenedPayload)
```

**route**: 대화 시작 요청(`POST /rooms/dm/{user_id}/agent`, 현재 `rooms/service.py`)에 **선택** 파라미터 둘을 받는다 — body 또는 query, bourbon-api가 편한 쪽으로.

- `recommendation_id: UUID | None`
- `entry: str | None` — 없으면 `"unknown"`으로 발행. 클라이언트가 추천을 거치지 않고 열었으면 `"direct"`.

bourbon-api는 두 값을 **검증하지 않고 그대로 이벤트에 싣는다**. 우리가 결정 로그와 조인해 확인한다.

**방 종류에 의존하지 않는다.** 친구 게이트를 풀면서 방 종류나 경로가 바뀌어도(오너: DM 유력) payload에는 `room_id`만 있어 그대로다. 이름 `agent_dm_opened`는 bourbon-api 용어에 맞춰 바꿔도 된다(예 `agent_conversation_opened`) — 바꾸면 알려 주시면 미러를 맞춘다.

**우리 처리**: `interactions`에 기록, 인기도 증가, 결정 로그의 `recommendation_id`와 조인. 이 이벤트가 CF 학습 입력의 시작점이다.

## 3. 그대로 쓰는 것 (변경 요청 없음)

- `bourbon.friendship_changed` (`user_low, user_high, action, occurred_at`) — 친구 미러(R17).
- `bourbon.user_registered` (`user_id`, `email`) — 추천 대상 agent row 생성. **`email`은 읽지 않는다.**
- `bourbon.user_deactivated` (`user_id`) — 전부 삭제.
- `bourbon.message_created` (`room_id, message_id, sender_id, sender_type, type, room_type`) — `room_type == agent_dm`인 유저 메시지를 turn으로 센다. 새 turn 이벤트는 필요 없다.

## 4. 확인 질문

1. §1 — `discoverable`의 클라이언트 노출(설정 화면)은 bourbon-api·클라이언트가 정한다. 우리는 이벤트만 받는다. 필드 이름이 달라져도 payload의 `discoverable` 하나로 받으니 알려만 주시면 된다.
2. §2 — 친구가 아니어도 방을 열 수 있게 하는 변경(오너 2026-09-08)의 시점. 추천은 "public agent는 누구에게나 열린다"를 전제한다.
3. §2 — re-enter 분기가 지금 코드에서 어디인지 우리가 짚은 곳(`ensure_agent_dm_room`)이 맞는지.
