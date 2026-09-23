# bourbon-api 요청서 — agent 공개 여부, 그리고 친구 게이트

> 코드 읽은 기준: bourbon-api main `c4c3300`(2026-09-08), 발행 이벤트 목록 2026-09-10, `rooms/service.py`·`rooms/dm_identity.py`·`agent_context/` 2026-09-11. 결정: R23(`discoverable`), **R51(방 생성 이벤트 요청 철회 — R46 개정)**, R47(어트리뷰션은 우리가 직접 받는다), R52·R53.
>
> **남은 요청은 없다(2026-09-13).** §1은 철회했고(§1-1), §2는 해결됐다(§2-2 — PR #325·#326). 이 문서에 남은 것은 요청이 아니라 **알려 드릴 것 셋**이고 §2-2 끝에 있다. 아래 §1·§2 본문은 보낸 그대로 남긴다(README "쓰는 규칙").
>
> 2026-09-10 판까지 이 문서의 §2는 방 생성 이벤트 요청이었고 "가장 먼저"인 이유도 그것이었다 — 그 뒤 친구 게이트가 그 자리를 물려받았고, 이제는 둘 다 닫혔다.

플랫폼의 이벤트 추가 기준(판정 기준이 명확하고 소비자가 여럿, stateless, 단일 소비자·사후분석은 그 서비스 안에서)에 맞춰 2026-09-10에 다시 쓴 요청이다. 처음 안에 있던 우리 전용 이벤트 `agent_dm_opened`, 상태 필드 `reopened`, route 파라미터 `recommendation_id`·`entry`는 **모두 뺐고**, 남아 있던 방 생성 이벤트도 2026-09-11에 철회했다.

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

## 1-1. 철회 (2026-09-13, R57) — 그 필드 대신 `agents.public`이 생겼다

**요청을 거둔다.** #325·#326으로 만들어진 것은 `discoverable`이 아니라 `agents.public`이고, 우리가 부탁한 것과는 다른 물건이다 — 그런데 **우리에게 더 필요한 쪽이 이미 해결됐으므로** 이 요청을 다시 내지 않는다.

- `agents.public`은 유저가 쓰는 필드가 아니다. 쓰는 곳은 `reconcile_public` 하나이고 값은 "이 사람이 public topic을 갖고 있나"의 파생이다. route도 응답 스키마도 이 값을 노출하지 않는다.
- 그 변화를 알리는 이벤트는 없다. 그래서 우리가 폴링 없이 그 값을 알 길도 없다.

**우리는 같은 사실을 직접 파생한다.** 우리 재조회가 이미 `GET /users/{id}/topics`를 읽고 있으므로, 읽어 온 집합에 `public` row가 하나라도 있으면 `discoverable = true`를 **row를 교체하는 그 트랜잭션 안에서** 쓴다. 술어도 입력도 `reconcile_public`과 같다. bourbon-api 쪽 작업은 **없다.**

**R23이 지키려던 것 중 살아남지 못한 절반**을 적어 둔다 — 나중에 이 문서를 보고 "왜 그때 더 밀어붙이지 않았나" 묻지 않도록. `discoverable`은 "agent는 쓰되 추천 목록에는 안 올린다"는 **옵트인**이었고, `agents.public`은 "누구나 말 걸 수 있나"라는 **도달 가능성**이다. 세기가 다른 노출인데 지금은 스위치가 하나라, public topic을 하나 공개하면 둘 다 켜지고 빼는 방법은 그 topic을 비공개로 돌리는 것뿐이다. 우리 판단은 **이것이 bourbon-api에 다시 낼 요청이 아니라는 것**이다 — 추천 목록은 우리 제품이므로, 따로 두기로 하면 우리 route와 우리 컬럼으로 끝난다(O22).

## 2. 친구가 아니어도 agent DM을 열 수 있게 (막고 있는 것)

**무엇**: `ensure_agent_dm_room`이 지금 친구가 아니면 방 생성을 거부한다(`_assert_friends_to_open` → `FriendshipRequiredError`). 이 서비스가 추천하는 상대는 **`public` tier로 공개한 사람**이고, 그 대부분은 요청자의 친구가 아니다. 그래서 오늘 기준으로는 추천 카드가 나가도 **누를 수 없다** — 추천 제품이 성립하지 않는다.

오너 결정은 2026-09-08에 이미 났다("public agent는 누구에게나 열린다"). 우리가 아는 것은 **언제** 풀리는지뿐이고, 그것이 우리 일정의 유일한 외부 의존이다. 방 종류나 경로가 바뀌어도 우리 쪽은 영향받지 않는다 — 우리는 `message_created`의 `room_type`만 읽는다.

## 2-2. 해결 (2026-09-13, #325·#326) — 그리고 알려 드릴 것 셋

**게이트가 내려갔다.** `_agent_reachable`은 이제 **친구이거나, 상대 agent가 public이면**(그리고 agent가 켜져 있고 소유자가 활성이면) 통과시킨다. 방 생성뿐 아니라 재입장과 쓰기에도 같은 조건이 걸리고, 거절은 403 `agent_not_accessible`이다. 우리 일정의 유일한 외부 의존이었고, 이제 없다. 고맙다.

**우리 쪽이 잘 맞는다.** 여기서 `public`이 "public topic이 1개 이상 있나"의 파생이므로, **게이트의 두 갈래가 우리 후보 조회의 두 갈래와 일대일이다** — public tier row는 public topic이 있는 소유자에게만 생기고, friends tier row는 친구에게만 나간다. 우리가 내는 카드는 게이트가 통과시키는 집합이다. 우리가 요청할 것은 없고, 아래는 **우리가 본 것을 알려 드리는 것**이다. 셋 다 우리 쪽에서 할 수 있는 일이 없어서 적는다.

**(1) 백필이 없다.** `agents.public`은 `DEFAULT 0`으로 들어왔고 #326에 데이터 마이그레이션이 없다. 두 커밋 메시지와 마이그레이션 docstring이 "one-off reconcile script"를 가리키는데 **그 스크립트가 repo에 없다**(`cli/`에는 `translate`, `translate_prompt`, `worker`, `media_worker`, `seed_terms`뿐). 그러면 기존 유저는 **자기 topic의 visibility를 한 번 건드릴 때까지** 도달 불가로 남고, 그 사이 우리 카드는 403을 받는다 — §2가 적었던 "눌러도 안 되는 추천 카드"가 자리만 옮긴 모양이다. 우리 쪽에는 이걸 알 방법이 없다(그 컬럼이 어디에도 노출되지 않는다).

**(2) 리컨사일에 재시도가 없다.** `TopicApiError`는 로그를 남기고 다시 raise되는데 deferq에는 재시도도 DLQ도 없으므로 그 전달은 사라지고, `agents.public`은 **다음 visibility 이동까지 낡은 값을 유지한다.** 방향 둘 다 조용하다: 낡은 `false`는 도달 가능한 사람이 못 열리는 것이고, 낡은 `true`는 public topic을 다 내린 사람의 agent가 계속 열리는 것이다.

**(3) 우리가 늘 더 최신일 것이다.** 우리 재조회는 `topic_visibility_changed`뿐 아니라 `topics_updated`(persona 동기화)로도 돌기 때문에, 같은 사실에 대해 우리 `discoverable`이 그쪽 `agents.public`보다 앞설 때가 정기적으로 생긴다. 그러면 **우리 추천이 게이트를 앞질러** 아직 403인 사람의 카드를 낸다. 우리 쪽에서 늦추는 것은 답이 아니라고 보고(노출 방향이 아니라 실패 방향이라 안전한 쪽이다), 적어만 둔다.

**우리가 못 보는 게이트 조건 셋**도 같이 적어 둔다 — `agent.enabled`, 소유자의 활성 상태, 그리고 agent row의 존재 자체(#325가 `_ensure_personal_agent` 부트스트랩을 지워서 row가 없으면 404 `agent_not_found`다). 셋 다 게이트가 우리보다 엄한 방향이라 노출이 아니라 **눌리지 않는 카드**로 나타난다. 지금은 그대로 감수한다.

## 3. edge-auth 익명 허용 (2026-09-17) — 우리 쪽은 준비됐고, 물을 것이 하나 있다

`feature/edge-auth-anonymous`(`cb63b92`)를 읽었다. 익명 allow 경로에서 `x-envoy-auth-headers-to-remove`에 `x-user-id`를 더하신 것이 이 변경의 안전을 떠받치는 한 줄이라고 본다 — 그것이 없으면 클라이언트가 보낸 `x-user-id`가 검증된 것처럼 우리에게 도착하고, 우리 public surface 전체가 위장 가능해진다. 제대로 돼 있다.

**우리 쪽 선행 작업은 없었다.** public route 넷(`discover/for-you`, `discover/by-topic`, `discover/by-topic/{topic_id}`, `attributions`)이 전부 필수 identity 의존성을 이미 갖고 있었다. PR 본문 서비스 표에 우리가 "`get_requester_id` → 401"로 적혀 있는데 **오늘 기준으로는 403**이고, 지금 401 `authorization_error`로 옮겼다(R62) — 표가 가정하신 쪽으로 맞춘 것이다. 가이드가 요구하시는 route-table 테스트도 넣었다. 기존 테스트가 "route가 `x-user-id` 파라미터를 선언했는가"만 보고 있어서, 헤더를 optional로 읽고 익명을 그냥 서빙하는 route를 통과시킨다는 것을 적대적 리뷰에서 실제로 확인했다. 가이드의 *"the test is what catches the route someone forgot"*이 정확했다.

**묻고 싶은 것 하나 — 웹 클라이언트의 401 인터셉터.** 가이드는 클라이언트에 "401이면 `GET /api/auth/session`으로 갱신하고 재시도"를 지시하고, 같은 문서가 authorizer 장애를 401이 아니라 503으로 답하는 이유로 *"a 401 would send every web client into a session-refresh loop over a problem no client can fix"*를 듭니다. **"처음부터 로그인하지 않았다"도 갱신으로 풀리지 않는 것**인데, 필수 identity route에서는 그것이 401이 됩니다. 클라이언트 쪽에서 "익명이라 401"과 "세션이 만료돼 401"을 구분할 방법이 준비돼 있는지(예: 로컬에 토큰이 없으면 갱신을 시도하지 않는다) 알려 주시면, 우리 쪽 메시지 문구를 거기에 맞추겠습니다. 우리가 보내는 것은 `{request_id, error_code: "authorization_error", message: "x-user-id header is missing"}`입니다.

**알려 드릴 것 하나 — 익명 트래픽의 rate limit.** `POST /attributions`는 요청마다 PostgreSQL row 하나를 쓰고, 이 서비스 안에는 볼륨을 제한하는 것이 없습니다(그것이 edge의 일이라고 route docstring에 적어 뒀습니다). 토큰 없는 요청에도 edge rate limit이 걸리는지 확인이 필요합니다. 안 걸린다면 우리 쪽에서 이 route만 따로 막는 방법을 생각하겠습니다.

**`/api/webhooks/svc/`**: 우리에게는 오늘 쓸 데가 없습니다 — 우리가 받는 것은 전부 이벤트입니다. 등록 블록이 `x-user-id`를 제거한다는 점만 확인했습니다.

## 2-1. 철회: 방 생성 이벤트 `bourbon.room_created` (R51, 2026-09-11)

**요청을 거둔다.** 기각과 함께 주신 대안(`GET /api/internal/rooms/{room_id}/agent-context`)도 쓰지 않는다. 이유를 적어 두는 이유는, 나중에 누가 이 문서를 보고 다시 요청할 필요가 없게 하기 위해서다.

- 그 route가 가진 것 중 우리에게 없는 것은 **소유자 id 하나**다. `room_type`과 actor는 `message_created`가 이미 싣고, 응답에는 방 종류도 `creator_id`도 방 생성 시각도 없다(그 셋은 `GET /users/{id}/rooms`의 `RoomOut`에 있는데 그쪽은 소유자를 주지 않는다).
- 그 하나를 얻는 대가로 **`context_messages`가 함께 온다.** `limit` 최솟값이 1이라 끌 수 없다. 우리 서비스는 남의 대화 본문을 한 글자도 들고 있지 않고, 그것이 계약 불변식 7이다.
- 같이 제안해 주신 나머지는 우리에게 해당이 없었다. 메시지 수·유저 메시지 수는 이미 `message_created`로 **메시지당 O(1)** 로 세고 있고(R49), 리액션은 쓰지 않으며, "활성 room 감지 64샤드 스윕"은 우리 설계에 없다 — 우리는 처음부터 이벤트 구동이다.

**대신 우리가 하는 것**: agent DM의 방 id는 `uuid5(DM_NAMESPACE, "dm:user:{user}:agent:{agent}")`로 결정론적이고(`rooms/dm_identity.py`, find·create 두 분기가 같은 식을 쓴다), 추천을 낼 때 requester와 agent id를 다 아니 **그 방이 열리면 어떤 id일지 그때 계산해 둔다.** 그 방의 첫 `message_created`가 오면 우리 인덱스에서 소유자를 찾는다. bourbon-api 쪽 작업은 **없다.**

**그래서 하나만 부탁드린다**: `DM_NAMESPACE`나 room id 계산식(`dm:user:{user}:agent:{agent}`)을 바꾸실 일이 생기면 알려 주시면 된다. 우리가 그 규칙을 복제해 두었고, 바뀌면 우리 쪽은 조용히 아무것도 못 찾게 된다(에러가 아니라 적중률 0으로 나타난다). `AGENT_NAMESPACE`는 이미 같은 이유로 복제해 쓰고 있다.

**우리가 감수한 것**(참고): 추천으로 시작되지 않은 대화는 소유자를 알 수 없어 기록하지 않는다(R52). 그리고 대화의 시작 시각이 방 생성이 아니라 **첫 메시지**가 된다. 답으로 주신 (a)·(b) 두 대안 중 **(b)를 택한 셈**인데, 원문에서 (b)를 "우리가 원하는 길은 아니다"라고 적었던 이유(추천 밖 대화를 못 본다)는 그대로 남고 R52가 그것을 명시적으로 감수한 결정이다.

### 2-1-1. 보낸 요청 원문 (기록)

> 이 문서의 규칙대로, 무엇을 부탁했는지는 그대로 남긴다(README "쓰는 규칙"). 아래는 2026-09-10 판의 §2이고, **더 이상 유효한 요청이 아니다.**

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

## 2-2. 공개 prefix `/api/svc/agent-discovery/`를 경로 레지스트리에 등록 (2026-09-11)

**부탁**: `k8s/base/api-svc-dispatch.yaml`의 `404` 폴백 **위에** 블록 하나를 추가해 주세요. 지금 우리 서비스는
`/api/internal/svc/agent-discovery/` 블록만 등록돼 있습니다.

```yaml
    - match:
        - uri:
            prefix: /api/svc/agent-discovery/
      route:
        - destination:
            host: bourbon-agent-discovery-api
            port:
              number: 80
```

**왜**: 클라이언트가 추천 카드에서 대화를 시작할 때 우리에게 보고하는 route `POST /api/svc/agent-discovery/attributions`
(계약 §2-5, R47)와, 이어질 탐색 탭 route(타입 ②③)가 이 prefix에 있습니다. 등록이 없으면 SPA의 catch-all로 떨어져
HTML이 돌아옵니다.

**우리 쪽에서 이미 끝난 것**: pod에 `bourbon.xinobi.ai/edge-auth: enabled` 라벨이 붙어 있어(공개 surface가 없던
때부터) 이 prefix는 등록되는 즉시 사이드카 검사를 받습니다. 우리는 `x-user-id`를 파싱만 하고 토큰을 읽지 않으며,
CORS preflight는 우리 앱이 직접 답합니다(`docs/microservice-edge-auth.md` 5단계). 별도 워크로드나 정책 예외는
필요 없습니다.

**답이 필요한 것은 없습니다** — 머지 시점만 알려 주시면 됩니다.

## 3. 그대로 쓰는 것 (변경 요청 없음)

- `bourbon.friendship_changed` (`user_low, user_high, action, occurred_at`) — 친구 미러(R17).
- `bourbon.user_registered` (`user_id`, `email`) — 추천 대상 agent row 생성. **`email`은 읽지 않는다.**
- `bourbon.user_deactivated` (`user_id`) — 전부 삭제.
- `bourbon.message_created` (`room_id, message_id, sender_id, sender_type, type, room_type`) — `room_type == agent_dm`인 유저 메시지를 turn으로 센다. 새 turn 이벤트는 필요 없다.
- 대화 시작 route(`POST /rooms/dm/{user_id}/agent`) — **파라미터 추가를 요청하지 않는다.**

## 4. 확인 질문

1. **§2 — 친구 게이트를 언제 푸는지.** 우리 일정의 유일한 외부 의존이고, 풀리기 전에는 추천이 나가도 채택되지 않는다.
2. §1 — `discoverable`의 클라이언트 노출(설정 화면)은 bourbon-api·클라이언트가 정한다. 우리는 이벤트만 받는다. 필드 이름이 달라져도 payload의 `discoverable` 하나로 받으니 알려만 주시면 된다.
3. §2-1 — room id 계산식이나 `DM_NAMESPACE`를 바꿀 계획이 있는지. 없으면 답 안 주셔도 되고, 생기면 그때 알려 주시면 된다.
4. **§5 — 내부 배치 route 둘을 요청 경로에서 읽기 시작합니다.** 지금까지 우리는 bourbon-api를 HTTP로 부른 적이 없습니다. 아래 §5에 무엇을 얼마나 부르는지 적었고, 물을 것 셋이 거기 있습니다.

---

## 5. 내부 배치 route 둘을 요청 경로에서 읽기 시작합니다 (2026-09-22, R63)

**무엇을 정했는지.** 클라이언트가 직접 부르는 탐색 화면(`GET /api/svc/agent-discovery/discover/…`)의 응답에, 추천된 사람의 표시 필드를 **우리가 채워서** 내립니다. 지금까지는 `agent_id`·`owner_user_id`만 주고 클라이언트가 해결하게 돼 있었는데 — 방 안의 `agent_profiles_v1` 카드가 그렇게 하고 있고 그쪽 `AgentProfileItem` docstring이 그 규칙을 적고 있습니다 — 그 규칙은 **한 장에 한 명**인 카드에 맞춰진 것이라 봅니다. 탐색 목록은 한 페이지가 기본 20건·상한 50건이라 같은 규칙이면 클라이언트가 공개 `GET /users/{user_id}`를 스크롤 한 페이지마다 20~50번 치게 되고, 그 route는 personal_agent를 bootstrap·realign 하고 커밋까지 하는 경로입니다. 그래서 **목록을 그리는 데 필요한 것만** 우리가 배치로 읽기로 했습니다.

**무엇을 부르는지.**

응답에 싣는 블록은 **`GET /api/users`의 `UserOut`과 같은 모양**으로 잡았습니다(그 endpoint를 부른다는 뜻이 아니라, 클라이언트의 기존 유저 카드 렌더러가 블록을 그대로 받게 하려는 것입니다). 그래서 읽는 필드가 그 모양을 채우는 것들입니다.

| route | 쓰는 필드 | 한 번에 보내는 id 수 |
|---|---|---|
| `GET /api/internal/users?ids=` | `name`, `picture`, `handle` | 한 응답의 **중복 제거된** 소유자 수 |
| `GET /api/internal/agents?ids=` | `name`, `picture`, `public` | 같음 |

**정정 — 호출 수가 요청 1건당 두 번이 아닐 수 있습니다.** 처음에 "요청 1건당 각 1회, id 최대 50"이라고 적고 물었는데, 화면 셋 중 하나가 그보다 큽니다. 탐색 목록(`for-you`)과 섹션 한 개 페이지는 한 응답이 최대 50명이라 맞지만, **섹션 개요(`by-topic`)는 섹션 최대 10 × 섹션당 최대 20 = 200명**입니다. 배치 상한이 100이니 그 화면에서는 route마다 **최대 2회**, 합쳐서 요청 1건당 최대 4회가 됩니다(중복 제거 뒤라 보통은 그보다 적습니다 — 한 소유자가 요청자의 여러 topic을 갖는 일이 흔합니다). 기본값 기준(섹션 3 × 5 = 15명)으로는 route마다 1회입니다. **이 수치로도 괜찮다고 확인받았습니다**(오너, 2026-09-22). 조정이 필요해지면 손대는 것은 우리 쪽 상한(`sections`·`per_section`, 설정 레지스터 §1)이지 그쪽 route가 아닙니다.

둘을 병렬로, 응답을 내보내기 직전에 한 번씩. 타임아웃은 2초(그쪽 peer에 대해 bourbon-topic-api가 쓰는 값과 같게 시작합니다). **캐시도 미러도 하지 않습니다** — 받은 값을 그 응답에 싣고 버립니다. `x-user-id`는 보내지 않고(내부 route가 읽지 않으니), 요청자 신원은 이 호출에 아예 실리지 않습니다. 보내는 id는 추천된 소유자들뿐입니다. 붙이는 헤더는 request id 하나입니다.

**안 부르는 것.** 뷰어에 따라 달라지는 값(친구 관계, 이미 열려 있는 DM 방 id)은 우리가 만들지 않습니다. 목록이 아니라 카드를 **누른** 시점에 필요한 값이라, 클라이언트가 그때 공개 `GET /users/{user_id}`를 한 번 치는 것으로 뒀습니다 — 방 안의 카드와 같은 동작입니다.

**실패하면.** 200으로 답하고 그 필드만 null로 둡니다(`degraded: ["hydration_partial"]`). bourbon-api가 답하지 않아도 목록의 길이와 순서는 같습니다 — 이 조회는 랭킹이 끝난 뒤의 단계라 누가 답에 드는지를 바꾸지 않습니다.

**물은 것 셋, 둘은 답이 왔다.**

1. ~~**이 호출량이 괜찮은지.**~~ → **괜찮다**(오너, 2026-09-22 구두). 레이트 리밋이나 권장 상한은 받지 않았다. 처음 물을 때 적은 수치가 틀려서(위 "정정" — 섹션 개요는 요청 1건당 route마다 최대 2회다) 고쳐서 다시 물었고, **그 수치로도 괜찮다**는 답을 받았다. 조정이 필요해지면 조이는 것은 우리 쪽 상한(`sections`·`per_section`, 설정 레지스터 §1)이다 — 그쪽에 다시 요청할 일이 아니다.
2. ~~**`GET /api/internal/agents`를 요청 경로에서 써도 되는지.** 그쪽 모듈 docstring이 카탈로그를 "이벤트 소비자 밑에 까는 주기 스윕"용으로 설명해서 물었다.~~ → **써도 된다**(오너, 2026-09-22 구두). 그래서 users 쪽만으로 좁히는 대안은 접는다 — agent의 `name`·`picture`를 그대로 싣는다.
3. **네트워크가 닿는지.** 우리 네임스페이스에서 `http://bourbon-api`로 나가는 호출이 처음입니다. NetworkPolicy나 메시 규칙에 더할 것이 있으면 알려 주십시오. **답을 기다리지 않고 dev에서 직접 확인한다** — 파드에서 한 번 부르면 답이 나오는 질문이고, 막혀 있으면 그때 요청이 구체적이 된다.
4. ~~**`enabled`를 봐야 합니까.**~~ → **안 봐도 된다**(오너, 2026-09-22). 그래서 응답에 싣지 않는다. 물은 이유는 적어 둔다: 그쪽 DM 게이트가 `public` **and** `enabled` **and** 소유자 활성 셋을 보므로(`bourbon_api/rooms/service.py`의 `AgentNotAccessibleError`), public topic이 있으면서 personal agent는 꺼 둔 소유자가 카드에 `public: true`로 나갈 수 있다고 봤다. 그 경우를 어떻게 다룰지는 그쪽 판단이고, 우리는 `public`만 통과시킨다.

**알려 드릴 것 하나.** 이 결정으로 우리 쪽에 bourbon-api 클라이언트가 처음 생깁니다. go-live 백필(기존 유저 전원을 우리 저장소에 채우는 일회성 작업 + 주기 잡)이 쓰려던 것과 같은 클라이언트라, 그쪽이 앞당겨집니다. 열거 셀렉터(`after`/`limit`)를 쓰는 것은 그때고, 지금 여는 것은 `ids` 배치뿐입니다.
