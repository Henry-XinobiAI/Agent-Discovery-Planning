# 클라이언트 요청서 — 탐색 탭 호출과 `recommendation_id` 전달

> 결정: R07(탐색 탭은 우리 API 직접 호출), R47(어트리뷰션은 우리 route에 직접 보고 — R24 개정), R40(`lang`). bourbon-api 요청서와 **같이** 보낸다 — 방 생성 이벤트와 이 보고가 맞아야 어트리뷰션이 이어진다.

## 1. 탐색 탭 → 우리 API 직접 호출

topic-api의 `/api/svc/topic`과 같은 형태로 `/api/svc/agent-discovery` 아래 route를 호출해 주시면 된다. edge-auth가 `x-user-id`를 채우므로 클라이언트가 유저 id를 보내지 않는다.

| 화면 | route | 파라미터 |
|---|---|---|
| 탐색 메인 "비슷한 사람들이 좋아한" | `GET /api/svc/agent-discovery/discover/for-you` | `lang`, `limit`(기본 20, 상한 50), `cursor` |
| 탐색 서브탭 "내 topic으로 대화해 볼 agent" | `GET /api/svc/agent-discovery/discover/by-topic` | `lang`, `per_section`(기본 5, 상한 20), `sections`(기본 3, 상한 10) |
| 섹션 더 보기 | `GET /api/svc/agent-discovery/discover/by-topic/{topic_id}` | `lang`, `limit`, `cursor`(섹션의 `next_cursor`) |

- **`lang`을 모든 요청에 보내 주기를 요청한다.** 허용값 `ko`, `en`, `ja`. 없으면 `en`으로 답하고, 그 외 값은 422. 응답의 `label`·`owner_note`는 요청 언어의 문자열 하나로 온다(언어별 맵이 아니다). 요청한 언어의 문자열이 없으면 en → 다른 언어 → null 순으로 대체된다(R40).
- 응답 envelope마다 **`recommendation_id`**가 있다. 페이지를 이어 가면 `cursor`가 이 값을 실어 같은 목록이 이어진다.
- `degraded`가 비어 있지 않으면 일부 신호가 빠진 응답이다(예 `friends_unavailable`). 상태 코드는 200이고 표시를 바꿀 필요는 없다.
- 응답에 "가려진 개수"나 순위 공백은 없다. 빠진 항목은 응답에 아예 나타나지 않는다.

정확한 스키마는 `agent_discovery_contract.md` §2·§3. 타입 ①(자기 agent에게 free text로 묻기)은 클라이언트가 호출하지 않는다 — bourbon-agent가 내부 API로 부른다.

## 2. 추천 카드에서 대화를 시작할 때 우리에게 보고

추천 카드에서 대화 시작을 누르면, bourbon-api의 대화 시작 요청과 **별개로** 우리 route를 한 번 호출해 주시면 된다. bourbon-api 요청에는 아무것도 추가하지 않는다.

```
POST /api/svc/agent-discovery/attributions
{ "recommendation_id": "<uuid>", "owner_user_id": "<uuid>", "entry": "discover_for_you" }
→ 204
```

| 상황 | `recommendation_id` | `owner_user_id` | `entry` |
|---|---|---|---|
| 탐색 메인 목록에서 | 그 응답 envelope의 값 | 카드의 값 | `discover_for_you` |
| 탐색 서브탭 목록에서 | 그 응답 envelope의 값 | 카드의 값 | `discover_by_topic` |
| 자기 agent의 추천 카드에서 (타입 ①) | **카드 meta의 값**(bourbon-agent가 넣어 준다) | 카드의 값 | `recommend_explicit` |
| 추천을 거치지 않고(프로필, 검색, 링크 등) | 호출하지 않음 | | |

- 값을 만들거나 바꾸지 않고, 받은 것을 그대로 넘겨 주시면 된다. 카드 meta에 값이 없으면(구버전 카드) 호출하지 않는다.
- fire-and-forget이다. 실패해도 재시도나 사용자 안내가 필요 없고, 대화 시작 흐름을 막지 않아야 한다.
- 순서는 상관없다. 대화 시작 요청 전이든 후든 우리가 시간 창 안에서 이어 붙인다.

**왜**: 이 값이 없으면 "추천이 대화를 만들었는가"를 영구히 알 수 없다. 추천 품질 측정과 CF 가중 게이트(R35)가 이 조인에 기댄다. bourbon-api를 거치지 않는 이유는 우리만 읽는 값을 다른 서비스의 요청과 이벤트에 얹지 않기 위해서다(플랫폼 이벤트 기준, R47).

## 3. 확인 질문

1. 탐색 탭 두 화면의 첫 버전 노출 순서와 "더 보기" 상호작용(섹션 커서를 어떻게 쓰는지).
2. 카드 meta에서 `recommendation_id`를 읽는 위치 — bourbon-agent 요청서 §2와 맞춘다. §2의 보고 호출을 대화 시작 요청과 같은 탭 핸들러에서 보내는지.
3. `lang`을 앱 언어 설정에서 가져오는지, 대화 언어에서 가져오는지(우리는 어느 쪽이든 받는다).
