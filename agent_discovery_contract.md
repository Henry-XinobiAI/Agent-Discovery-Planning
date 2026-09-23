# agent-discovery-api 공통 계약 — 요청·응답, 후보 소스 인터페이스, 랭커 feature, 결정 로그

> `agent_discovery_redesign.md` §9의 2번. 구현이 **지켜야 하는 것**만 적는다. 이 계약 위에서 후보 소스 구현을 갈아 끼울 수 있고(R34 이후 구현은 하나지만 인터페이스는 남긴다), 클라이언트와 bourbon-agent는 바뀐 것을 모른다.
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

세 응답은 같은 이름의 `recommendation_id` 필드를 갖는다(값은 목록마다 새로 발급). 뒤의 상호작용 이벤트가 이 id로 되돌아온다.

**요소는 둘이다**(R63 개정). 타입 ①은 `RecommendedAgent`, 클라이언트가 카드를 그리는 타입 ②③은 거기에 표시 블록 둘을 더한 `DiscoverAgent`다. 공통 부분은 같고 §3-1이 둘을 나란히 인쇄한다.

---

## 1. 두 API

topic-api와 같은 방식이다. 라우터는 하나씩이고, 앱이 두 prefix로 두 번 붙인다.

- **클라이언트 API** `/api/svc/agent-discovery/…`: edge-auth 사이드카가 `x-user-id`를 덮어쓴다. 요청자는 그 헤더다. **헤더가 없거나 UUID가 아니면 401 `authorization_error`**(R62, 2026-09-17). 사이드카는 토큰 없는 요청을 막지 않고 **`x-user-id`를 제거해서** 통과시키므로 헤더의 부재는 "로그인하지 않았다"이고, 그 답은 401이다. 이 surface의 모든 route는 요청자를 필요로 한다 — 익명을 받는 route는 없다.
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
  "room_id": "uuid",                 // 로그 추적용. 이 서비스는 room을 읽지 않음
  "lang": "ko"                       // ko | en | ja (R40). 응답의 다국어 필드를 이 언어의 문자열 하나로. 기본 en, 그 밖의 값은 422
}
```

`topic_text`와 `context`는 유저의 말이다. **로그·예외·Sentry에 원문이 실리지 않는다.** 로그에는 다이제스트만 남는다.

### 2-2. 타입 ② `GET /discover/by-topic`

```
GET /discover/by-topic?per_section=5&sections=3&lang=ko      // 기본 5·3, 상한 20·10 (R30, 값은 설정 레지스터). 섹션 순서는 요청자 preference 점수
```

요청자의 grounding된 topic 중 preference 점수 상위 `sections`개를 섹션으로, 섹션마다 agent `per_section`명. 응답의 각 섹션에 `next_cursor`가 있고, 더 보기는 아래 route다.

**한 섹션이 묻는 것은 그 topic과 그 topic의 1 hop 자손이다**(R65). 요청자가 "커피"를 갖고 있으면 커피를 공개한 사람과 **핸드드립만** 공개한 사람이 같은 선반에 선다 — 섹션은 요청자가 가진 것을 말하고, 카드는 실제로 맞은 것을 말한다(§3-1).

- **아래 방향만, 1 hop만.** 부모·형제로는 넓히지 않는다. 요청자가 가진 것보다 *더 구체적인* 사람은 그 관심의 한 구석을 아는 사람이지만, 더 일반적인 쪽("음료")은 그렇지 않다.
- **타입 ①은 펼치지 않는다.** ①의 첫 정렬 키가 `coverage`이고 그 값은 "뽑힌 topic 중 몇 개를 가졌나"다(§4-4). 자손을 세면 "커피" 하나를 물었는데 핸드드립·에스프레소·로스팅을 공개한 사람이 coverage 3이 되어, 정확히 맞춘 사람을 제친다 — 분모가 뜻을 잃는다. 타입 ②에는 이 문제가 없다: ②는 `score desc`만으로 정렬하고 coverage를 보여주지도 쓰지도 않는다.
- **계층은 우리 `catalog_edges`에서 읽는다**(R26의 커밋된 카탈로그). 타입 ③의 content 소스가 이미 같은 표를 걷는다.
- **비용**(커밋된 카탈로그 + dev 스냅샷 실측, 2026-09-23): 사람들이 실제로 공개한 topic 377개 중 자식이 있는 것은 153개뿐이라, 섹션의 `IN` 목록은 **중앙값 1개 그대로**, p95 21개, 최악 69개가 된다. 3 hop이면 44 / 463이라 그쪽은 택하지 않았다.

```
GET /discover/by-topic/{topic_id}?limit=20&cursor=…&lang=ko      // limit 기본 20, 상한 50 (설정 레지스터)
```

`topic_id`는 요청자가 **가진** topic이어야 한다. 아니면 404(요청자의 topic 목록에 없음) — 자손은 섹션이 펼치는 것이지 이 route가 받는 것이 아니다. 펼치는 범위는 위와 같다. 요청자 자신의 topic 목록은 요청 시 topic-api 내부 route로 읽는다(R27 — 나중에 미러로 바꿀 수 있다). 읽는 범위는 본인의 `public`·`friends`·`private`이고 **`hidden`은 읽지 않는다**(R22). 어느 쪽이든 타인의 topic은 §5 규칙으로만 읽는다.

### 2-3. 타입 ③ `GET /discover/for-you`

```
GET /discover/for-you?limit=20&cursor=…&lang=ko                // limit 기본 20, 상한 50 (설정 레지스터)
```

입력은 요청자 id뿐이다. topic·로그는 서버가 이미 갖고 있고, persona(HEXACO 성향)는 자리만 있다 — 입력 경로가 열리기 전까지 그 feature는 0이다(R42·O20).

**규칙(R28)**: 요청자가 이미 대화를 시작한 agent는 for-you에서 제외한다. 다만 아직 안 보여 준 후보를 모두 소진했고 다음 갱신 전이면, 미대화 후보 뒤에 다시 나올 수 있다. 그 항목이 재등장이라는 표식은 결정 로그 `ranked[].talked_before`에만 있고 응답에는 없다(클라이언트는 자기 방 목록으로 안다. 표시 기획이 생기면 필드를 연다). 합성 정답도 같은 규칙을 쓴다.

**사전 계산이 없는 요청자**(항목이 아직 없는 유저 — 대화 0건, 또는 첫 대화 뒤 첫 스윕 전 — R19): 인기도와 content 소스만으로 `limit`을 채운 **완전한 목록**을 답한다. `basis`가 `popularity` 또는 `content`가 되고, `degraded`는 비어 있다. 첫 대화 이벤트 뒤 워커 스윕이 첫 항목을 만든다.

**사전 계산이 오래된 요청자**(R19): 있는 항목을 그대로 쓴다. 응답 직전 재확인(§5 불변식 4)과 이미 대화한 상대 제외가 그 사이의 변화를 걸러내고, 이 요청이 `agents.last_active_at`을 갱신해 다음 스윕이 항목을 새로 만든다. `cf_candidates_stale`는 §3-4의 임계를 넘겼을 때만 붙는다.

### 2-3-1. ②③의 내부 미러

`GET /api/internal/svc/agent-discovery/users/{user_id}/discover/by-topic`, `…/by-topic/{topic_id}`, `…/for-you`. 요청자가 경로의 `user_id`라는 것만 다르고 쿼리·응답은 같다.

### 2-4. 공통 규칙

- `lang`은 모든 요청에 있고(기본 `en`, 허용 `ko`·`en`·`ja` — 그 밖은 422), 응답의 다국어 필드(`label`, `owner_note`)는 그 언어의 **문자열 하나**다(R40). 폴백은 요청 언어 → `en` → 있는 첫 값 → null.
- 페이지네이션은 opaque `cursor`다. 오프셋을 노출하지 않는다(사전 계산 결과가 갈아엎어지면 오프셋은 의미가 없다). `recommendation_id`는 **목록 하나**(첫 페이지)에 발급되고 `cursor`가 그것을 실어 오므로 다음 페이지는 같은 id·같은 seed(R20)로 순서를 잇는다. 그 사이 사전 계산이 갱신될 수 있어(R19) 페이지 연속성은 best-effort다.
- **페이지가 있는 답은 `has_next`와 `next_cursor`를 같이 준다**(R64). bourbon-api의 목록 봉투(`GET /api/users`의 `UserListOut`)와 같은 모양이라, 클라이언트가 두 종류의 목록에 한 가지 페이지 로직을 쓴다. **둘은 언제나 일치한다** — `has_next`가 참인 것과 `next_cursor`가 있는 것은 같은 말이고, 그 불변은 봉투를 만드는 한 곳이 지킨다. 중복인 것을 알고 두는 것이다: 한 값만 보는 클라이언트가 어느 쪽을 골라도 맞게 하려는 것이고, 값이 갈리면 그것은 우리 결함이지 상태가 아니다. 커서가 없는 답(타입 ①)에는 둘 다 없다.
- 요청자 본인의 agent는 어느 타입에서도 결과에 없다.

### 2-5. 어트리뷰션 보고 `POST /attributions` (R47·R66)

클라이언트가 추천 카드에서 대화를 시작할 때 우리에게 직접 알린다. 다른 서비스의 route나 이벤트에 우리 필드를 얹지 않는다(플랫폼 이벤트 기준, 이벤트 정의서 §0).

| 필드 | 타입 | 의미 |
|---|---|---|
| `recommendation_id` | UUID | 그 카드가 속한 응답 envelope의 값. 타입 ①은 bourbon-agent가 카드 meta에 실어 준 값 |
| `owner_user_id` | UUID | 대화를 시작하는 상대 agent의 소유자(카드의 값) |
| `entry` | `recommend_explicit` \| `discover_by_topic` \| `discover_for_you` | 어느 화면에서 |
| `section_topic_id` | string \| null | **(R66)** 그 카드가 서 있던 선반의 topic. 타입 ②만 채우고 ①③은 null이다 |
| `position` | int \| null | **(R66)** 그 카드의 `position`(§3-1). 타입 ②는 선반마다 1부터 다시 세므로 `section_topic_id`와 짝일 때만 카드 하나를 가리킨다 |

요청자는 edge-auth의 `x-user-id`. 응답 204. 추천을 거치지 않은 대화 시작(`direct`)은 보고하지 않는다. 우리는 `attributions`(§6)에 적고 **`reported_at`은 우리 시계로 찍는다** — 이 payload에는 시각이 없다. 그 방의 첫 `message_created`가 같은 `(actor, owner)` 쌍으로 오면 `attribution.window_hours` 안의 최근 보고 하나를 `interactions.entry`·`recommendation_id`에 채우고 `attributed_by = report`를 남긴다(R51·R53). 보고가 없으면 예측 room 인덱스가 대신하고(`predicted`), 그것도 없으면 `entry = direct`다. 보고는 best-effort다 — 측정용 값이라 빠져도 추천은 영향이 없다.

**뒤의 두 칸이 생긴 이유(R66).** `(recommendation_id, owner_user_id)`만으로는 **어느 선반에서 눌렀는지 알 수 없다** — R65 이후 한 소유자가 한 화면의 두 선반에 동시에 선다(정확히 맞은 선반과 자손으로 맞은 선반). 둘은 같은 카드가 아닌데 보고는 같은 모양이 되고, 그러면 §2-6의 분모는 선반별로 갈리는데 분자가 안 갈린다 — R65가 답하려던 "자손으로 맞은 카드가 실제로 대화가 되는가"를 영영 못 재게 된다. **둘 다 없어도 보고는 유효하다**: 지금 모양으로 보내는 클라이언트의 보고는 그대로 받고 두 칸이 null이 된다.

### 2-6. 노출 보고 `POST /attributions/impressions` (R66)

카드를 **실제로 화면에 그렸을 때** 클라이언트가 알린다. §2-5가 분자면 이것이 분모다.

**왜 필요한가.** 클라이언트는 목록을 미리 fetch해 두고 나중에 그린다. 그래서 §8의 `served_at`은 "우리가 답한 때"이지 "사람이 본 때"가 아니고, 받아만 놓고 스크롤하지 않은 목록이 전부 분모에 들어간다. 노출 보고가 없으면 "추천이 대화를 만들었는가"는 **fetch 수로 나눈 값**이라 계속 낮게 읽히고, **그 왜곡의 크기조차 알 수 없다.** 타입 ②에서 더 크다 — 선반이 세로로 쌓여 있어 아래 선반은 대개 눈에 닿지 않는다.

| 필드 | 타입 | 의미 |
|---|---|---|
| `recommendation_id` | UUID | 그 카드들을 만들어 낸 응답 envelope의 값 |
| `cards[]` | 배열 | 이번에 화면에 그려진 카드들. 빈 배열은 422, **50장을 넘어도 422**(아래). 한 번에 다 보낼 필요는 없다 |
| `cards[].owner_user_id` | UUID | 카드의 값 |
| `cards[].position` | int | 카드의 `position`(§3-1) |
| `cards[].section_topic_id` | string \| null | 그 카드가 선 **선반**의 topic — `DiscoverSection.topic_id`(또는 섹션 route의 경로 파라미터)다. 타입 ②만 |

요청자는 edge-auth의 `x-user-id`. 응답 204.

**`section_topic_id`는 카드에서 읽는 값이 아니다.** 셋 중 둘(`owner_user_id`·`position`)만 카드에 있고, 선반 topic은 **카드를 감싼 섹션**에 있다. 카드에 있는 유일한 topic id는 `matched_topics[].topic_id`인데 **R65 이후 그건 대개 선반의 자손**이다("커피" 선반의 카드가 `핸드드립`을 든다 — §2-2). 거기서 읽으면 자손 id가 보고되고, **검증을 통과하고 그대로 적힌다** — 그 값을 우리가 아는 선반에 맞춰 보는 곳이 없으므로 선반별 분모가 틀린 채 아무도 모른다. 요청서 client §3이 이 문장을 그대로 싣는다.

**`entry`는 받지 않는다 — 무시가 아니라 422다.** 결정 로그 항목이 `type`을 이미 갖고 있다. 두 곳에 적으면 갈릴 수 있고, 갈렸을 때 어느 쪽이 맞는지 정할 근거가 없다. **요청 모델이 선언하지 않은 키를 거부하므로**(§2의 모든 요청과 같다) §2-5의 본문을 복사해 `entry`를 남겨 두면 **모든 보고가 422**가 된다 — 그리고 fire-and-forget이라 클라이언트가 알아채지 못한 채 그 분모가 영영 빈다.

**적히는 곳은 결정 로그다**(§8·§6-1). **노출 쪽에는** 새 테이블도 새 스윕도 마이그레이션도 없다(§2-5의 두 칸은 다르다 — 거기엔 컬럼 둘이 붙는다): `REC#{recommendation_id}`/`LOG` 항목의 `impressions[]`에 `pages[]`와 같은 방식으로 덧붙고, 보존은 그 항목의 TTL(`decision_log.ttl_days`)을 그대로 탄다. 읽는 쪽이 평가 배치 하나뿐이고 **조인 상대가 없어서다** — §2-5가 PostgreSQL에 있는 이유(워커가 `message_created`와 조인한다)가 여기엔 없다.

**이 서비스에서 조건이 붙는 유일한 보고다.** append는 `attribute_exists(PK) AND requester_user_id = :requester` 아래에서만 일어난다(§8의 `pages[]`가 쓰는 조건과 같다). 우리가 낸 적 없는 목록에도, 남의 목록에도 적히지 않는다. §2-5는 대조할 상대가 없어 무엇이든 받지만(R47), 이쪽은 **우리가 그 목록을 누구에게 냈는지 이미 알고 있다.**

**조건에 걸려도 204다.** 404는 "그 `recommendation_id`가 존재하는가"를 묻는 도구가 되고, 클라이언트는 어차피 할 수 있는 것이 없다(fire-and-forget). 대신 구조화 로그가 남는다.

**`cards[]`의 상한은 한 요청을 묶는 값이지 한 응답의 크기가 아니다.** 처음에 "한 응답이 낼 수 있는 카드 수"(타입 ②의 `sections`×`per_section`)로 유도했는데 **틀렸다** — 클라이언트는 스크롤을 따라 보고하고 다음 페이지는 같은 `recommendation_id`를 이어 가므로, **한 섹션을 끝까지 읽은 정직한 보고가 어느 한 응답보다 길다.** 요청을 묶는 값은 **한 번에 그려질 수 있는 양**이고 그건 한 페이지다 — 가장 긴 목록이 `for_you.limit_max`(50)이므로 50이다. 레지스터 행이 아니고 그 행에서 계산하지도 않는다: 레지스터를 좁히는 것은 배포가 할 수 있는 일이고, 같이 움직이는 요청 상한은 정직한 보고를 거절하기 시작한다. 넘으면 나눠 보내면 된다.

**한 목록에 여러 번 온다.** 스크롤을 따라 같은 `recommendation_id`에 append가 이어지므로 항목이 자란다. 클라이언트는 한 목록 안에서 **카드 하나를 처음 보일 때 한 번만** 보고하고, 서버는 그 목록에 보고된 **카드 수**가 `attribution.max_impression_cards`를 넘기면 더 붙이지 않는다.

**cap이 세는 것은 보고 건수가 아니라 카드 수다.** 건수를 세면 크기가 안 묶인다 — 보고 하나가 카드 50장을 실을 수 있어서, 건수 상한만으로는 항목이 **DynamoDB의 400 KB를 넘는다**(실측: 13건). 그리고 넘긴 항목은 **그 뒤 아무것도 못 받는다** — 같은 항목의 `pages[]`까지 막히는데 그건 답변 경로의 기록이다. 게다가 그 실패는 거절이 아니라 오류라서, 그 목록에 대한 이후 모든 요청이 **장애처럼 생긴 로그**를 남긴다. cap은 **보고 하나만큼의 여유**를 갖는다: 상한 직전에 닿은 보고는 통째로 들어간다(크기를 이유로 보고를 쪼개 거절하는 것보다 싸다).

**"보여줬다"의 기준은 클라이언트가 정한다.** 뷰포트 몇 %·몇 초인지는 우리가 볼 수 없는 값이고, 그 정의가 분모의 의미를 통째로 정한다. 요청서 client §4의 질문이고, **정해지면 여기에 적는다.**

**같은 카드가 두 번 실릴 수 있고, 읽는 쪽이 distinct로 센다.** append는 멱등이 아니고 전송 계층이 재시도한다 — 쓰기가 닿은 뒤 응답이 끊기면 같은 보고가 두 번 들어간다. 클라이언트 재시도와 스크롤 왕복도 같다. 그래서 **분모는 `impressions[]`의 항목 수가 아니라 그 안의 서로 다른 `(owner_user_id, section_topic_id, position)` 수**다. 쓰기 시점에 막지 않는 이유는 그러려면 보고마다 id를 들려 보내거나 항목을 읽어야 하는데, 읽는 쪽에서 한 번 세는 것이 같은 답을 더 싸게 주기 때문이다.

**`impressions[].at`은 우리 시계다.** payload에 시각이 없는 것도, 그 이유도 §2-5의 `reported_at`과 같다 — 클라이언트의 시계는 아무것도 증명하지 않는다. 읽을 때도 같게 읽는다: "그들이 본 때"가 아니라 "보고가 우리에게 닿은 때"다.

보고는 §2-5와 같이 best-effort다. 빠져도 추천은 영향이 없다.

---

## 3. 응답

### 3-1. 요소 둘 — `RecommendedAgent`와 `DiscoverAgent`

**공통 요소 `RecommendedAgent`** — 타입 ①이 답하는 것이자 나머지 둘의 바탕이다.

```json
{
  "agent_id": "uuid",              // personal agent id
  "owner_user_id": "uuid",         // agent 소유자. agent_id에서 유도되지만 클라이언트가 유도하지 않게 준다
  "position": 1,                   // 이 응답 안의 순위 (1부터). 페이지가 이어져도 계속 증가
  "matched_topics": [              // 이 agent가 여기 있게 만든 topic들
    {
      "topic_id": "…",
      "label": "캠핑",              // 요청 lang의 라벨 하나 (R40)
      "requested": true,           // 타입 ①: 뽑힌 topic 중 하나인가. 타입 ②: 섹션 topic이면 true, 그 자손으로 맞았으면 false (R65)
      "owner_note": "…"            // 소유자가 그 topic에 쓴 한 문장(유저 topic의 descriptions에서 lang의 것 하나, R40). 항상 있고, 안 썼으면 null
    }
  ],
  "signals": {                     // 왜 여기 있나 — 랭커 feature 중 보여줘도 되는 것 (§7)
    "coverage": 2,                 // 타입 ①: 뽑힌 topic 중 몇 개를 가졌나. ②③: null
    "topic_maturity": 0.7,         // matched_topics 중 최고, 0~1, 없으면 null
    "agent_maturity": 0.4,         // 0~1, 없으면 null
    "popularity": 0.2,             // 0~1 정규화, 없으면 null
    "similar_users": 12            // 타입 ③: 이 agent와 대화한 "비슷한 사람" 수. 로그 없으면 null
  },
  "fit": null                      // "맞음/안 맞음" 표시. 첫 버전에 "안 맞음"은 없다(R41). 지금은 항상 null, 자리만 둔다. 기획 중인 방향은 "나와 비슷해요 / 다른 관점도 살펴봐요"(O5)
}
```

예약된 필드: `talked_before`(타입 ③, R28의 "소진 뒤 재등장" 표식). 코드는 계산하고 결정 로그에 남기지만 **응답에는 넣지 않는다** — 표시 기획이 요청하면 같은 `contract_version`으로 연다.

`owner_note`는 소유자가 쓴 글이다. **응답에 싣는 것으로 끝이다.** 로그, 예외, 결정 로그, Sentry에 들어가지 않는다.

**답의 필드는 키가 빠지지 않는다 — 값이 `null`이거나 비어 있을 뿐이다.** 널 가능한 쪽이
`owner_note`, `fit`, `signals`의 다섯, `next_cursor`, 타입 ②③의 `owner`·`agent`이고, 널이 아닌 쪽도
같다 — `matched_topics`는 `null`이 아니라 `[]`이고, `degraded`도 비었으면 `[]`이며,
`contract_version`은 늘 실린다. 클라이언트가 "없는 키"와 "null인 값"을 구분할 이유가 없도록 한쪽으로
고정한 것이다. **발행 스키마와 발행 예제도 그렇게 말한다** — 스키마의 `required`가 빠뜨리거나 예제에서
null인 필드가 키째 사라지면, 클라이언트는 그 필드가 그 카드에 없다고 읽는다.

**`owner_note`가 null인 것은 degraded가 아니다.** 소유자가 그 topic에 아무것도 안 썼다는 사실이고,
그건 답이 덜 채워진 것이 아니라 완전한 답이다(불변식 5).

**`requested`는 타입 ②에서 실제로 갈린다**(R65). 섹션이 펼쳐지기 전에는 이 필드가 늘 참이었다 — 맞은 것이 곧 물어본 것이었으니까. 이제 `false`는 **"섹션 topic의 1 hop 자손으로 맞았다"**는 뜻이고, 1 hop만 펼치므로 그 이상의 거리를 말할 값이 필요 없다.

```json
{ "topic_id": "…", "label": "커피", "has_next": false, "next_cursor": null,
  "agents": [
    { "…": "…", "matched_topics": [ {"topic_id": "…", "label": "커피",   "requested": true,  "owner_note": "…"} ] },
    { "…": "…", "matched_topics": [ {"topic_id": "…", "label": "핸드드립", "requested": false, "owner_note": null} ] }
  ] }
```

**섹션에서 유도할 수 있는데도 싣는다.** `section.topic_id`와 비교하면 같은 것을 알 수 있지만, 이 계약은 `empty`와 `has_next`에서 이미 같은 선택을 했다 — 유도할 수 있어도 응답에 담아 주고, **한 곳에서 유도해 어긋날 수 없게 한다.** 클라이언트가 두 값을 조합하게 만들지 않는 쪽이 이 문서의 습관이다.

**타입 ②의 `matched_topics`는 비지 않는다.** 섹션 topic이든 그 자손이든 카드에는 언제나 맞은 이유가 있고, 응답 직전 재확인에서 전부 사라진 소유자는 카드가 비는 것이 아니라 **답에서 빠진다**(불변식 4). 비는 것은 타입 ③뿐이다 — 거기서는 인기도·CF가 topic을 근거로 뽑지 않아 이름 붙일 것이 애초에 없다.

**타입 ②③의 요소 `DiscoverAgent`** — 위의 모든 필드에 표시 블록 둘을 더한다.

```json
{
  …공통 필드 전부…,
  "owner": {                       // 못 채우면 null. 요청 시 채운다 (R63)
    "name": "지원",                  // 받은 그대로. 폴백은 그리는 쪽이 정한다. null 가능
    "picture": "https://…",        // null 가능
    "handle": "jiwon"              // null 가능 — 아직 정하지 않은 유저가 있다
  },
  "agent": {                       // 못 채우면 null. owner만 채워지는 경우도 있다(아래)
    "name": "지원의 에이전트",         // null 가능
    "picture": "https://…",        // null 가능
    "public": true                 // 친구가 아닌 사람에게 DM 진입을 그릴지. bourbon-api가 파생하는 값
  }
}
```

**표시 필드는 우리가 채우고, 뷰어에 따라 달라지는 것은 클라이언트가 읽는다**(R63). 값은 요청 시 내부 route 둘(`GET /api/internal/users?ids=`, `GET /api/internal/agents?ids=`)을 배치로 읽어 채우고, 미러하지 않는다(§6). 못 채우면 그 필드는 null이고 `degraded`에 `hydration_partial`이 붙는다 — 상태는 200이고 카드는 id만 가진 채로 그려진다. **필드 목록은 디자인이 정해지기 전의 기준값이다**(§11).

**id는 최상위에만 있고 블록에는 없다.** `agent_id`·`owner_user_id`가 이 계약의 키다 — 카드를 누른 시점의 조회와 §2-5 어트리뷰션 보고가 그것을 쓴다. 블록 안에 되풀이하면 한 카드에 같은 값이 세 번 적힌다.

**`agent`는 혼자서도 null이 될 수 있다.** bourbon-api는 사람과 agent를 두 row로 답하고, 사람 쪽만 오는 경우가 있다. 둘이 같이 null이면 하이드레이션 실패이고, 그때만 `hydration_partial`이 붙는다.

**`enabled`는 싣지 않는다.** bourbon-api가 "그건 안 봐도 된다"고 답했다(2026-09-22). 그럴듯한 추론 하나를 같이 적어 둔다 — *우리가 discoverable한 소유자만 답하니 항상 true일 것이다* — 이것은 **틀렸다**: `discoverable`은 "public topic이 있나"(R57)이고 agent가 켜져 있는지는 말하지 않으며, 그쪽 DM 게이트는 `public` **and** `enabled` **and** 소유자 활성 셋을 본다. 빼는 근거는 그 추론이 아니라 그쪽의 답이다.

**타입 ①에는 이 블록들이 아예 없다 — null이 아니라 키가 없다**(R63 개정). 그 답은 bourbon-agent가 받고, 그쪽은 카드를 그리지 않는다: owner id를 꺼내 사람을 **자기가** 조회해 모델이 쓸 문장을 만들고, 방에 올리는 프로필 카드에는 그 id 하나만 싣는다. 우리가 채우면 그쪽이 곧바로 하는 호출을 우리 데드라인 안에서 한 번 더 하는 것이고, 받는 쪽은 그 값을 버린다. null인 키는 "채우려다 실패했다"로 읽히는데 타입 ①의 답은 완전하므로, 그것은 사실이 아닌 말이 된다.

반대로 **요청자와 소유자의 관계에 따라 달라지는 값은 이 응답에 없다.** 친구 관계와, 이미 열려 있는 DM 방 id가 그것이다. 기준이 bourbon-api이고, 목록을 *그리는* 데 필요한 것이 아니라 카드 하나를 *누를* 때 필요한 것이라, 클라이언트가 그 시점에 공개 `GET /users/{user_id}` 한 번으로 읽는다. 방 안의 `agent_profiles_v1` 카드가 하는 것과 같은 해석이다 — 다른 점은 카드가 한 장에 한 명이고 목록은 한 페이지에 최대 `for_you.limit_max`명이라는 것뿐이며, 그래서 배치가 필요한 쪽은 목록뿐이다.

### 3-2. 타입별 envelope

**① `POST /recommend/explicit` → 200**

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "resolved_topics": [ {"topic_id": "…", "label": "…"} ],    // free text에서 확정된 topic, 1~3개, 커버리지의 분모
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
      "topic_id": "…", "label": "…",
      "agents": [ DiscoverAgent… ],
      "has_next": true,                  // next_cursor의 유무와 언제나 같다 (R64, §2-4)
      "next_cursor": "…" | null
    }
  ],
  "degraded": []
}
```

섹션이 비면(그 topic을 공개한 타인이 없음) 섹션은 `agents: []`로 남긴다. 섹션이 아예 없으면(요청자가 topic이 없음) `sections: []`.

**페이지는 섹션 *안*에만 있다.** `sections` 자체에는 커서가 없다 — 요청자 topic 중 preference 점수 상위 `sections`개로 고정이고, 더 보고 싶으면 `sections`를 올려서 다시 요청한다(상한 `by_topic.sections_max`). 섹션마다 인덱스 쿼리가 하나씩이라 그 수를 올리는 비용이 선형이고, 화면을 계속 내리는 상호작용은 섹션 안의 "더 보기"다(오너, 2026-09-22).

**③ `GET /discover/for-you` → 200**

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "agents": [ DiscoverAgent… ],
  "basis": "popularity" | "content" | "collaborative",   // 이 응답을 주로 만든 신호. 콜드스타트 표시용
  "has_next": true,              // next_cursor의 유무와 언제나 같다 (R64, §2-4)
  "next_cursor": "…" | null,
  "degraded": []
}
```

### 3-3. 오류

| 상태 | 언제 | 타입 |
|---|---|---|
| 200 + 빈 목록 | 요청자에게 보일 수 있는 agent가 없다. "없다"와 "있지만 가려졌다"를 구분하는 값은 없다(§5 불변식 5) | 모두 (①은 `empty: true`, ②는 빈 `agents`, ③은 빈 `agents`) |
| 401 | 클라이언트 API에서 `x-user-id` 없음/비정상 — 로그인한 호출자가 없다(R62). `error_code`는 플랫폼 철자인 `authorization_error` | ②③ |
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
| `hydration_partial` | 표시 필드를 다 못 채웠다 — 라벨(커밋된 카탈로그에 그 topic의 이름이 없다)이거나 `owner`·`agent`(bourbon-api, R63)다. **`owner_note`가 null인 것은 여기 해당하지 않는다** — 소유자가 안 쓴 것이다. **어느 쪽인지는 응답이 말하지 않는다**: 값 하나가 두 원인을 덮으므로 호출자가 보는 것은 "덜 채워졌다" 하나이고, 무엇이 비었는지는 로그에 남는다. 호출자가 그 구분으로 할 수 있는 일이 없어서 나누지 않았다 |
| `cf_candidates_stale` | 타입 ③: 사전 계산 결과가 **있는데** TTL의 몇 배(R36: 7일) 이상 오래됐다. TTL을 넘긴 정도는 정상 경로(그대로 서빙하고 스윕이 갱신, R19)라 붙이지 않는다. 항목이 없어서 인기도·content로 답한 경우는 이 값이 아니다 — `basis`가 그것을 말한다 |

"몇 개가 가려졌다"는 어떤 형태로도 응답에 없다(§5).

**이 목록도 여기에 남는다**(R54). 응답에 실려 나가는 닫힌 값 집합이라 소비자가 읽는 것이 이 표와 OpenAPI 스키마이고, 코드에서는 `agent_discovery/domain/discovery.py`의 `DegradedReason`이 같은 목록을 갖는다. 값을 더할 때는 둘을 같이 고친다 — 소비자가 모르는 값을 받게 되는 변경이므로 계약 버전(§0)을 먼저 본다.

---

## 4. 도메인 인터페이스 — 소스를 갈아 끼우는 자리

```
요청 ─▶ QueryBuilder ─▶ CandidateSource들 ─▶ VisibilityFilter ─▶ Ranker ─▶ Assembler ─▶ 응답
        타입별          소스별              공통                 공통      공통
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
    requester_traits: Mapping[str, float] | None = None   # R42 예약: HEXACO facet → 추정치. 입력 경로가 없어 지금은 항상 None(O20)
```

타입 ①의 QueryBuilder는 free text → 개념 확장 → topic-api 검색 → topic 확정(기존 코드 `agent_discovery/stages/`의 확장·확정 단계)이고, 결과가 `TopicQuery`다. 타입 ②의 QueryBuilder는 요청자의 topic 목록을 읽어 topic마다 `TopicQuery` 하나를 만든다. 타입 ③은 `UserQuery` 그대로다.

### 4-2. 후보 소스

```python
@dataclass(frozen=True)
class SourceHit:
    owner_user_id: UUID
    tier: Literal["public", "friends"] | None   # 이 hit이 근거한 row의 tier. 모르는 소스는 None → 필터가 채우거나 버린다
    topic_id: str | None                 # topic 근거가 있으면. CF/인기도 hit은 None
    source: str                          # "topic_index" | "popularity" | "content_similarity" | "cf_engine" … ("cf_item"은 예약 이름 — R34로 지금은 구현 없음)
    score: float                         # 소스 안에서만 비교 가능한 값
    evidence: Mapping[str, float]        # 랭커 feature 재료 (예: topic_score, topic_maturity, co_count)

class CandidateSource(Protocol):
    name: str
    async def candidates(self, query: TopicQuery | UserQuery) -> Sequence[SourceHit]: ...
```

- **공개된 row 저장소를 읽는 소스는 visibility 조건을 쿼리 안에 넣는다**(R17): `tier = 'public' OR (tier = 'friends' AND owner_user_id = ANY(friends(요청자)))`. `topic_index`, `content_similarity`, PostgreSQL `popularity`가 여기 든다(이웃 테이블을 만들면 그것도). 결과는 tier가 이미 붙어 있고 필터에서 빠지는 것이 없으므로 **`limit`만큼만(응답 직전 재확인에서 빠질 몫만 여유를 두고) 읽는다.** 친구 집합은 미러(§6 `friends`)에서 배열로 넘기거나 조인한다.
- **요청자별 사전 계산**(라이브러리형 `cf_engine`의 배치가 만드는 `cf_candidates`)은 배치 시점의 요청자 친구 집합으로 같은 조건을 적용해 top-K를 뽑는다. 그래도 스냅샷이므로 응답 직전 재확인(§5 불변식 4)은 남는다. `cf_item`(agent×agent 이웃 테이블, R34로 지금은 만들지 않음)은 요청자별 사전 계산이 아니고, 첫 항처럼 요청 시 조건을 쿼리에 넣는다.
- **tier를 모르는 소스만 넉넉히 반환한다**(예: 3배): 외부 엔진(Gorse)이 준 agent 목록처럼 조건을 넣을 수 없는 곳. 뒤의 필터가 공개된 row 저장소에서 tier를 조회해 붙이고, row가 없으면 버리고, 부족하면 파이프라인이 한 번 더 요청한다. 이 재요청 비용은 그 소스의 비용으로 검증(재설계 §6)에 기록한다. 엔진 결과는 후보를 좁힐 뿐 노출을 허가하지 못한다.
- 한 타입이 소스 여러 개를 쓸 수 있다. 타입 ③은 `popularity + content_similarity + cf_*`.
- 구현은 하나다(R34): `topic_index`(PostgreSQL), `popularity`, `content_similarity`, `cf_engine`(`implicit` ALS 배치 → `cf_candidates`, R33). `cf_item`(동시 출현 이웃)과 Gorse 소스는 만들지 않는다 — 인터페이스는 그대로라 뒤에 추가할 수 있다.

### 4-3. visibility 필터

```python
class VisibilityFilter(Protocol):
    async def allow(self, requester: UUID, hits: Sequence[SourceHit]) -> tuple[Sequence[SourceHit], Degradation]: ...

Degradation = frozenset[str]   # §3-4의 값 집합. 비어 있으면 완전한 답
```

규칙은 §5. 구현은 하나다. 역할은 둘이다: 조건을 이미 적용한 hit(`tier`가 있음)은 그대로 통과시키고, `tier = None`인 hit에는 `visible_topic_rows`를 소유자 키로 조회해 tier를 붙이며(friends row는 요청자가 친구일 때만) row가 없으면 버린다. 친구 집합을 읽지 못한 요청의 처리는 §5 불변식 3.

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

타입 ①은 `score` 앞에 커버리지 정렬이 온다: `(coverage desc, score desc)`. 타입 ②③은 `score desc`.

**타입 ②에서 자손으로 맞은 hit의 `topic_score`에는 `content.decay_per_hop`이 곱해진다**(R65). 그러지 않으면 정확히 맞춘 사람과 자손만 가진 사람이 같은 무게가 된다. 상수는 타입 ③의 content 소스가 쓰는 것을 그대로 빌린다 — 새로 지어내지 않는다. 1 hop만 펼치므로 지수는 언제나 1이고, 가중치가 아니라 **feature에 들어가기 전의 값**에 걸리므로 §7의 이름은 바뀌지 않는다.

**그리고 펼치는 섹션의 `topic_score`는 matched 중 합이 아니라 최대다**(R65, §7). 감쇠만으로는 부족하기 때문이다 — 섹션은 topic 하나를 묻고 §3-4의 합은 물어본 수로 나누므로, 분모가 1이 되어 자손이 그냥 더해진다. 실측(2026-09-23): 0.9짜리 자손 둘은 감쇠 뒤 0.54씩이지만 합이 1.08이라 topic을 정확히 1.0으로 공개한 사람(0.500)을 0.540으로 제쳤고, `topic_score`도 §7이 정한 0~1을 벗어났다. 최대로 접으면 자손은 사람을 **선반에 올릴 수는 있어도 정확히 맞춘 사람을 넘지는 못한다.** **후보를 자르는 쿼리도 같은 방식으로 접는다** — 자르는 쪽과 순위 매기는 쪽이 다르게 접으면, 랭커는 이미 빠진 사람이 없는 목록을 받는다.
 처음엔 가중합(가중치는 설정 레지스터 `agent_discovery_settings.md` §2), 로그가 쌓이면 학습 모델로 교체하되 인터페이스는 같다. feature 이름은 §7이 전부이고 예약 feature(`persona_similarity`, R42)도 같은 경로로 들어온다 — 입력이 없으면 값 0, `present`에 없음. 예약 feature가 실제로 켜지는 것은 설정값과 입력 경로가 갖춰졌을 때의 일이고 인터페이스는 바뀌지 않는다.

**타입 ③은 정렬 뒤 점수 구간 안에서만 섞는다**(R20). 구간 경계는 설정(예 상위 5·다음 15·다음 30), seed는 `recommendation_id`. `cursor`가 첫 페이지의 `recommendation_id`를 실어 오므로 다음 페이지도 같은 seed로 순서를 잇는다(§2-4, best-effort). 결정 로그는 `ranked`에 섞기 **전** 순서를, `shuffle`에 seed와 구간 경계를 남겨 서빙 순서를 재현한다. 타입 ①②는 섞지 않는다.

### 4-5. 응답 조립

요소를 만들고 표시 필드를 채운다(hydration). **요청 시에 읽는 업스트림은 하나뿐이다** — 타입 ②③의
`owner`·`agent`를 bourbon-api 내부 route 배치로 읽는다(R63). 실패하면 그 필드만 null이 된 채
`hydration_partial`이 붙고, 타입 ①에는 이 단계가 아예 없다.

나머지 둘은 이미 우리 쪽에 있다: **라벨은 커밋된 카탈로그**(R26)에서 읽고 — topic-api를 답마다 부르면
파일이 바뀔 때만 변하는 값 때문에 그쪽 가용성이 답 경로에 올라온다 — **`owner_note`는 재확인이 되읽는
우리 행의 `descriptions`**에서 온다(§4-2의 두 번째 읽기). 그래서 이 둘은 업스트림 장애로 비지 않는다:
라벨이 비면 카탈로그에 그 topic의 이름이 없다는 뜻이고, 노트가 비면 소유자가 안 썼다는 뜻이다.

**답 하나에 한 번이지 선반마다 한 번이 아니다.** 타입 ②는 섹션 단위로 조립하므로 거기서 채우면 한 페이지가 섹션 수만큼의 업스트림 호출이 되고, 요청자의 topic 여럿을 가진 소유자를 그 수만큼 다시 묻게 된다. 그래서 답 전체의 row를 모아 한 번 묻고, 같은 소유자를 여러 선반에 되돌려 놓는다.

**이 단계는 어떤 후보가 답에 드는지를 바꾸지 않는다.** 랭킹이 끝난 뒤이고 페이지가 이미 정해져 있어서, bourbon-api가 답하지 않아도 목록의 길이도 순서도 같다 — 그래서 503이 아니다. 친구 집합(불변식 3)과 갈리는 지점이 정확히 여기다: 그쪽은 후보 쿼리 **안**의 조건이라 못 읽으면 답이 줄어든다.

**그 약속을 지키는 데 세 가지가 필요하다**, 셋 다 말이 아니라 동작이다. (가) bourbon-api 조회의 예산은 **그 업스트림의 예산과 요청에 남은 시간 중 작은 쪽**이다 — 데드라인이 거의 소진된 요청에서 예산을 그대로 쓰면 바깥 데드라인이 먼저 터져 **완성된 페이지가 503이 된다.** 남은 것이 없으면 호출하지 않는다. (나) 한 chunk가 실패해도 답한 chunk는 버리지 않는다(§6의 100개 쪼개기). (다) 실패는 그것이 감싸여 온 모양이 아니라 **실패 자체로** 가려낸다 — 업스트림 실패만 `hydration_partial`이 되고 나머지는 그대로 올라간다. 셋 중 하나라도 없으면 이 절의 첫 문장이 거짓이 된다.

**hydration은 §8의 독립된 stage다**(`hydrate`). 업스트림 시간이라 조립 시간에 섞으면, 느린 bourbon-api가 느린 assembler로 읽힌다.

**응답 직전에 공개된 row가 존재하는지 다시 확인**한다(§5 불변식 4).

---

## 5. 불변식 — 언제나

1. **저장소에는 공개된 row만 있다.** `(topic_id, owner, tier ∈ {public, friends})`. private·hidden은 들어오지 않고, 비공개로 되돌리면 지운다. 소유자 단위 공개 여부(`agents.discoverable`)는 **그 row들에서 파생된다**(R57): public row가 하나도 없으면 false다. 지우는 규칙이 아니라 세는 규칙이라, 플래그와 row가 어긋날 자리가 없다.
2. **friends row는 요청자가 소유자의 친구일 때만 통과한다.** 기준은 bourbon-api이고, 판정은 `bourbon.friendship_changed`로 미러한 친구 집합으로 후보 조회 쿼리 안에서 한다(R17).
3. **친구 집합을 못 읽으면 friends tier는 빠진다(fail-closed).** 응답은 `degraded: ["friends_unavailable"]`, 상태는 200. R17·R18 배치에서는 친구 집합이 `visible_topic_rows`와 같은 PostgreSQL에 있어 "row는 읽었는데 친구 집합만 못 읽는" 경우가 없고 그 장애는 503이다. 이 항은 계약에 예약된 규칙으로 남긴다 — 친구 집합을 다른 저장소로 옮기는 날 다시 살아난다.
4. **사전 계산 결과는 노출을 허가하지 않는다.** 응답 직전에 현재 공개된 row로 다시 거른다.
5. **응답은 "가려짐"과 "없음"을 구별하지 못한다.** 가려진 개수, 표시, 순위 공백이 없다.
6. **요청자 본인은 결과에 없다.**
7. **유저의 글(topic_text, context, owner_note)은 로그·예외·Sentry에 원문으로 실리지 않는다.** 결정 로그에도 없다.
8. **상태 코드는 멈춘 지점에서 결정된다.** 422 = 봤는데 없다, 503 = 못 봤다.

---

## 6. 공개된 row 저장 모델 — 모양은 저장소 무관, 배치는 R18

최소 저장 모델. 모양은 저장소와 무관하고, 배치는 R18이다: **조인·집계가 있는 집합은 PostgreSQL, 단건 키 읽기·쓰기만 있는 집합은 DynamoDB, Redis는 deferq만.** 아래 표에서 DynamoDB는 `cf_candidates`이고 나머지는 전부 PostgreSQL이다(`requester_topics`는 R27로 만들지 않는다).

| 집합 | 키 | 값 | 갱신 |
|---|---|---|---|
| `visible_topic_rows` | `(topic_id, tier, owner_user_id)` | `topic_score`(소유자 쪽 preference 강도, §7의 범위로 변환해서 저장), `topic_maturity`, `updated_at` | topic 변경 이벤트. 비공개 전환 = 삭제 |
| `visible_topic_rows` 보조 인덱스 | `owner_user_id` | → 그 소유자의 row들 | agent private 시 일괄 삭제용 |
| `agents` | `owner_user_id` | `agent_id`, `discoverable`, `agent_maturity`, `registered_at`, `updated_at`, **`last_active_at`**, **`cf_candidates_computed_at`**(R19) | `bourbon.user_registered`로 생성(추천 대상 풀, `discoverable`은 기본 false), **`discoverable`은 재조회가 파생한다**(R57 — 읽어 온 집합에 `public` row가 있나. row 교체와 **같은 트랜잭션**이라 둘이 어긋날 수 없고, 그래서 이벤트 순서를 비교하던 `visibility_changed_at`은 없앴다), 성숙도는 성숙도 이벤트로, `bourbon.user_deactivated`로 삭제. 없는 채로 topic 이벤트가 오면 재조회가 만든다. `last_active_at`은 우리 API 요청·**agent_dm 방의 첫 `message_created`를 보낸 사람**(R51)·`topics_updated` 셋 중 어느 것이든 갱신한다. **`cf_candidates_computed_at`**(R19)은 그 유저의 top-K를 마지막으로 만든 시각 — 스윕 조건 `last_active_at > cf_candidates_computed_at`의 오른쪽 |
| `requester_topics` (**R27: 저장하지 않음**) | `user_id` | 요청자 자신의 topic 목록(점수 포함) — 본인의 `public`·`friends`·`private`, `hidden` 제외(R22). 타입 ②의 섹션과 타입 ③의 content 쿼리에 씀 | 요청 시 topic-api 내부 route(`visibility=public&visibility=friends&visibility=private`)로 읽는다(R27). 소유자 키 아래에만 두는 미러는 지연 시간이 문제될 때의 대안 |
| `owner`·`agent` 표시 블록 (**R63: 저장하지 않음**) | — | `owner`(`name`·`picture`·`handle`)와 `agent`(`name`·`picture`·`public`). id는 요소 최상위에만 있다(§3-1) | 요청 시 bourbon-api 내부 route 둘(`GET /api/internal/users?ids=`, `GET /api/internal/agents?ids=`)을 배치로 읽는다. **한 응답의 distinct 소유자 수가 그쪽 배치 상한 100을 넘을 수 있다**: 타입 ③과 섹션 한 개 페이지는 `for_you.limit_max`·`by_topic.page_limit_max`(각 50)로 안전하지만, **타입 ②의 섹션 개요는 `sections_max × per_section_max` = 200**이다. 그래서 소유자 id를 **중복 제거한 뒤 100개씩 끊어** 보낸다 — 한 소유자가 요청자의 여러 topic을 가질 수 있어 distinct 수는 대개 그보다 적고, 중복 제거가 같은 사람을 섹션 수만큼 다시 묻는 것을 막는다. **끊은 것 중 하나가 실패해도 답한 것은 버리지 않는다**: 넷이 답하고 다섯째가 실패했다고 화면 전체의 블록을 비우는 것보다, 덜 채워졌다고 말하는 편이(`hydration_partial`) 언제나 낫다. **미러하지 않는다** — 우리가 받는 이벤트(§9-1) 중 프로필 변경을 싣는 것이 하나도 없어서 미러를 최신으로 유지할 방법이 주기 스윕뿐인데, 이름과 사진은 그 주기만큼 눈에 띄게 낡는다. 남의 소유인 값의 낡음만 우리가 떠안는 거래다. `friends`가 반대 방향인 이유는 그쪽이 후보 쿼리 **안**의 조인이기 때문이고(R17), 이쪽은 랭킹이 끝난 뒤의 표시 필드다 |
| `friends` (**R17: 미러, 필수**) | canonical pair `(user_low, user_high)`. 조회는 `user_id` → 친구 id 집합(상한 5,000) | `state ∈ {friends, removed}`, `changed_at`(발행자 시각) | `bourbon.friendship_changed`: `accepted`·`removed` 모두 upsert, **자기보다 새 `changed_at`이 있으면 적용하지 않는다**(R50 — 이벤트 둘이 커밋 순서로 정착하므로 지우는 설계로는 끊긴 친구가 남는다). 읽는 쪽은 전부 `state = 'friends'`이고, 그 조건을 빠뜨릴 자리를 없애려 저장소가 "친구 집합"만 답한다. `removed` tombstone은 `friends.tombstone_ttl_days` 뒤 정리. 요청 시 bourbon-api 조회·TTL 캐시는 쓰지 않는다. `visible_topic_rows`와 같은 저장소에 두어 후보 조회 쿼리가 배열로 받거나 조인한다 |
| `popularity` | `owner_user_id` | 시간 감쇠 카운트(계산 시점에 전체 최대로 나눈 값이라 저장된 값이 곧 §7의 0~1 feature), `computed_at` | **주기적으로 다시 만든다**(`popularity.refresh_minutes`): `interactions` ⋈ `room_turns`를 `popularity.window_days` 창으로 읽어 집계 SQL 한 문장으로 덮어쓴다. 대화 시작 이벤트마다 더하는 방식이 아니다 — R29의 가중은 `1 + α·log(1 + turns)`이고 대화가 시작되는 순간의 `turns`는 1이라 그 대화의 최종 무게를 아직 모르며, 30일 창은 아무 일도 일어나지 않는 동안에도 움직이는 경계다(1-7에서 확인). 대화가 0건인 소유자는 행이 없고, `popularity.new_agent_prior`는 랭커가 그 자리에 넣는 값이다 — 저장소에 넣으면 대화 없는 agent 전부가 같은 점수로 묶여 인기도 소스가 무작위 agent 생성기가 된다 |
| `cf_candidates` | `user_id` | `candidates: [(owner_user_id, score)]` top-K, `computed_at`, `model_version`(어느 전역 학습으로 만들었나 — 재현·갱신 판단용) | 워커의 주기 스윕이 배치로 쓴다 — 조건은 R19. K는 설정 레지스터 `cf.pool_k`(R20의 pool). **DynamoDB**(R18·R44 — `USER#{user_id}` / `CF_CANDIDATES`, §6-1, **TTL 없음**): 서빙은 단건 GetItem, 조인은 없다(재확인은 PostgreSQL `visible_topic_rows`에서). 오래된 항목도 그대로 서빙한다. 항목이 없는 요청자는 §2-3의 콜드스타트 경로 |
| `interactions` | `(actor_user_id, owner_user_id, room_id)` | `started_at`, `entry`, `recommendation_id`, **`attributed_by`**(R53) (`turns`는 `room_turns`에서 조인) | **그 방의 첫 `message_created`로 생성**(R51 — `room_created` 요청은 철회했다). 소유자는 예측 인덱스 `ROOM#{room_id}`에서 오고, 거기 없는 방은 기록하지 않는다(R52). `entry`·`recommendation_id`는 `attributions` 보고가 먼저·예측 인덱스가 다음이고 `attributed_by`가 어느 쪽인지 남긴다(R53). CF 학습 입력. 자기 agent 방·user DM·group은 행 없음. 탈퇴: owner 행 삭제, actor 행은 actor 익명화(R49) |
| `room_turns` (R49) | `room_id` | `turns`, `last_turn_at` | `message_created`(`room_type == agent_dm`, `sender_type == user`)마다 +1. 같은 이벤트가 `interactions`도 만들지만(R51) 예측하지 않은 방은 turn만 세므로 방 키로 독립시킨다. `interactions` 행이 없는 방은 읽기 조인에서 빠지고 `room_turns.orphan_ttl_days` 뒤 정리 |
| `attributions` (R47·R66) | `(requester_user_id, owner_user_id, reported_at)` | `recommendation_id`, `entry`, `section_topic_id`·`position`(R66, nullable — 어느 선반의 어느 카드였나. 측정용이라 아래 조인은 읽지 않는다) | 클라이언트의 §2-5 보고로 생성하고 `reported_at`은 우리가 찍는다. 그 방의 첫 `message_created`가 오면 `attribution.window_hours` 안의 최근 것 하나를 `interactions`에 옮긴다(R51). 보존은 `decision_log.ttl_days`와 같게 |

### 6-1. DynamoDB key space — 테이블 하나 (R44)

인프라 방침대로 서비스 소유 테이블 하나(`bourbon-agent-discovery-tokyo-{env}`, `PK`·`SK` 문자열, `PAY_PER_REQUEST`, TTL 속성 `expires_at`)에 엔티티를 prefix로 나눈다. 두 번째 테이블은 성능·비용 근거가 생길 때만(`requests/infra.md` §2).

| 항목 | PK | SK | 읽기 | TTL |
|---|---|---|---|---|
| `cf_candidates` | `USER#{user_id}` | `CF_CANDIDATES` | 단건 GetItem. `candidates[(owner_user_id, score)]`, `computed_at`, `model_version` | 없음(R18) |
| 결정 로그(§8) | `REC#{recommendation_id}` | `LOG` | 단건 GetItem(어트리뷰션 조인, 디버깅). 페이지는 같은 항목의 `pages[]`에, 노출 보고(§2-6)는 `impressions[]`에 append | `decision_log.ttl_days` |
| 결정 로그 평가용 GSI `served-day-index` | `served_day_key = {type}#{YYYY-MM-DD}#{shard}` | `served_at` | 하루·타입 단위 Query를 shard 수만큼 병합. `KEYS_ONLY` — 본문은 PK로 다시 읽는다 | — |
| `event_log` | `EVT#{YYYY-MM-DD}#{shard}` | `{occurred_at}#{event_id}` | 하루 단위 Query 병합(이벤트 리플레이·보정, 합성 스펙 §8-2). 이벤트 이름·`occurred_at`·payload JSON. 유저의 글·`email`은 payload에 없다 | `event_log.ttl_days` |
| 예측 room 인덱스(R51) | `ROOM#{room_id}` | `PREDICTED` | 단건 GetItem. 추천을 낼 때 `room_id = uuid5(DM_NAMESPACE, "dm:user:{requester}:agent:{agent_id}")`로 미리 계산해 `requester`, `owner_user_id`, `recommendation_id`, `entry`, `served_at`을 쓴다. 그 방의 첫 turn에서 한 번 읽는다 | `attribution.predicted_room_ttl_hours` |
| 게이트 상태 | `CONFIG` | `CF_GATE` | 단건. 런타임에 움직이는 유일한 설정값 `w_cf`와 마지막 평가(R35) | 없음 |

`shard = hash(id) % N`, N은 설정 `dynamodb.log_shards`. **shard는 지금 키 포맷에 들어간다** — topic-api가 받은 피드백대로, 하루치 쓰기가 한 파티션에 몰려 GSI가 스로틀되면 베이스 테이블 쓰기까지 막히기 때문이다. N을 늘려도 옛 항목의 shard 값은 새 범위 안에 있으므로 마이그레이션이 필요 없다. 주 읽기 패턴(날짜별 전체)가 Scan이 아니라 Query인 것도 같은 피드백에서 왔다.

타입 ①②의 조회는 `visible_topic_rows[topic_id, public]` ∪ (`visible_topic_rows[topic_id, friends]` ∩ friends(요청자)) 이고, 타입 ①은 topic ≤ 3개의 결과를 owner로 합쳐 커버리지를 센다. 이 합집합은 쿼리 하나의 WHERE 절이다(§4-2, R17). 타입 ③의 `popularity`·`content_similarity`·이웃 조회도 같은 조건을 `visible_topic_rows`에 대한 조인(또는 EXISTS)으로 붙여 요청자에게 보이는 소유자만 읽는다. 다른 소스가 자기 저장소를 따로 가져도 위 집합은 그대로 있어야 한다. 불변식 1·4가 여기서 판정되기 때문이다.

---

## 7. 랭커 feature

| feature | 정의 | 범위 | 출처 | 타입 |
|---|---|---|---|---|
| `coverage` | **물어본** topic 중 가진 수. 섹션이 펼쳐져도 자손은 세지 않는다 — 물어본 것이 아니고, 세면 이 칸의 범위를 벗어난다(R65) | 0~3 | topic_index | ① (1차 정렬 키) |
| `topic_score` | 소유자 쪽 preference 강도. **타입 ①은 matched topic 합을 물어본 topic 수로 나눈 값**(§3-4의 `합/2`), **펼치는 타입 ②는 matched 중 최대**(R65 — 섹션은 topic 하나를 묻기 때문에 합은 나누는 수가 1이라 자손 둘이면 그냥 더해져 이 칸의 범위를 벗어난다). **topic-api의 `score`는 0~100이고 이 feature는 0~1이다** — 변환은 `providers/topic_api/adapter.py`에서 한 번 한다(그쪽 단위가 우리 단위로 넘어오는 유일한 지점). 원본 스케일 그대로 두면 `rank.*.w_topic_score` 하나가 나머지 feature 전부의 100배가 되어 가중합에 항이 하나만 남는다(1-6에서 발견) | 0~1 | visible_topic_rows | ①② |
| `topic_maturity` | matched topic 성숙도 최대 | 0~1 | visible_topic_rows (임시값 → 컴포넌트) | ①②③ |
| `agent_maturity` | agent 성숙도 | 0~1 | agents | ①②③ |
| `popularity` | R29: 최근 30일 창의 대화 시작을 반감기 7일로 감쇠해 합산, 시작마다 `cf_score`와 같은 confidence 가중, 전체 최대로 정규화 — 여기까지가 §6의 주기 집계이고, 대화가 0건이라 행이 없는 소유자에게 `popularity.new_agent_prior`를 넣는 것은 랭커다. 값은 설정 레지스터 | 0~1 | popularity | ③ (①②는 약한 가중) |
| `content_similarity` | 요청자 topic 집합과 소유자 topic 집합의 가중 겹침. R25: IDF 가중 × 카탈로그 계층 감쇠(양방향 최단 hop, 0.6/hop·최대 3 hop, 경로당 최구체 일치 하나, drawer는 통과 노드), 임베딩 없음. 0~1 정규화와 IDF의 **보유자 수**(그 topic을 가진 소유자 수)는 그 요청의 쿼리 안에서 나오고, **모집단**(`log(모집단 / 보유자 수)`의 나누는 쪽)은 **주기 스냅샷에서 읽는다**(R59) — **답에 나올 수 있는 소유자 수**(공개된 row가 하나라도 있는 사람, R58)를 `population_stats`에서 한 줄로 읽고, 읽을 것이 없거나 그 값이 0이면 그 자리에서 센다. 정규화는 **R28로 빼기 전** 최대값으로 한다(누구와 이미 대화했나에 따라 스케일이 흔들리지 않게, walkthrough §5-5) | 0~1 | 요청자 topic(R27) × visible_topic_rows + 카탈로그 edge 테이블(R26) | ③ |
| `cf_score` | 행렬 분해(ALS) 점수, 소스 안에서 정규화. **학습 입력의 confidence는 "대화 시작 1회"가 아니라 `1 + α·log(1 + turns) + β·reopen_count`** — 배우는 대화(길고 다시 찾는 대화)가 한 번 시작하고 끝난 대화보다 강한 신호다(오너 2026-09-08, 결정 레지스터 R16). α·β는 설정. 가중은 자동 게이트가 0에서 올린다(R35) | 0~1 | cf_engine — `implicit` ALS(R33) (입력: `interactions` + turn 카운터) | ③ |
| `similar_users` | 이 agent와 대화한 유사 유저 수 | 정수 | `interactions` 카운트(요청자가 대화한 소유자들과도 대화한 유저 수). ALS에서 직접 나오지 않는다 | ③ (표시용) |
| `recency` | 소유자의 마지막 topic 갱신이 얼마나 최근인가 | 0~1 | visible_topic_rows.updated_at | 모두, 작은 가중. 오래 활동하지 않은 소유자를 **후보에서 빼지 않고** 이 feature로 내린다(R19). 하드 제외는 하지 않는다(R31) |
| `tier_is_friends` | 근거 row가 friends tier인가 | 0/1 | 필터 결과 | 모두. 초기 가중 .05, 측정 뒤 조정(R32) |
| `persona_similarity` | **R42 예약.** 요청자와 소유자의 HEXACO facet 벡터 유사도(confidence·관측 수 가중). topic이 겹치지 않아도 성향이 맞는 사람을 찾아낸다. **입력 경로가 없어 지금은 항상 0이고 `present`에 없다**(O20) | 0~1 | 요청자 성향(`UserQuery.requester_traits`) × 소유자 성향 — 둘 다 bourbon-agent가 **이벤트**로 준다(방향만, O20 — bourbon-agent에 API를 열 가능성은 없다). persona 테이블 직접 읽기·복호화 키 공유는 하지 않는다(R42) | ③. 가중 `rank.for_you.w_persona`는 0에서 시작, 올리는 규칙은 O20 |

없는 feature는 0이고 `present`에 없다. 가중치는 설정이다 — 뜻은 `agent_discovery_settings.md`, 값은 코드다(R54).

**이 목록은 여기에 남는다**(R54). 튜닝하는 값이 아니라 답이 무엇으로 이루어지는지를 말하는 어휘이고, 소스를 갈아 끼울 때(§4) 새 소스가 무엇을 채워야 하는지를 이 표가 정한다. 코드에서는 `agent_discovery/domain/discovery.py`의 `FeatureName`이 같은 목록을 갖는다 — 한쪽만 늘어나도 알려 주는 것이 없으므로 feature를 더할 때는 둘을 같이 고친다.

---

## 8. 결정 로그

목록마다 한 건 — 첫 페이지에 발급된 `recommendation_id`가 PK고, 다음 페이지 요청은 같은 항목에 `pages[]`로 덧붙인다(§2-4). 오프라인 평가의 정답 로그다. **유저의 글은 없다.** 저장은 **DynamoDB**(R18·R44, key space는 §6-1): `REC#{recommendation_id}` / `LOG`(어트리뷰션 보고 §2-5의 `recommendation_id`가 단건으로 찾아온다), 평가 배치가 날짜·타입별로 읽도록 GSI `served-day-index`(`served_day_key = {type}#{YYYY-MM-DD}#{shard}`, shard 병합), 보존은 TTL(`decision_log.ttl_days`). 집계는 SQL이 아니라 평가 배치의 코드다.

```json
{
  "recommendation_id": "uuid",
  "type": "recommend_explicit" | "discover_by_topic" | "discover_for_you",   // attributions.entry(§2-5)와 같은 값 집합
  "requester_user_id": "uuid",
  "implementation": "v1@<settings_hash>",         // 어느 코드·설정 스냅샷이 답했나 (R34 이전에는 A/B 표식이었다)
  "query": {                                      // 타입별. 원문 없음
    "topic_text_digest": "16hex",                 // ① sha256 앞 64비트
    "resolved_topic_ids": ["…"],                  // ①
    "topic_id": "…",                              // ② 섹션 route
    "section_topic_ids": ["…"],                   // ② 첫 화면이 어떤 topic을 섹션으로 삼았나. ①의 resolved_topic_ids와 같은 종류의 값이고, 목록이 무엇을 중심으로 만들어졌는지를 남긴다(구현 1-5에서 추가)
    "cursor": "…"                                 // ②③
  },
  "sources": [ {"name": "topic_index", "hits": 20, "latency_ms": 6} ],
  "filter": {"in": 20, "out": 0, "friends_used": true, "degraded": []},   // 개수는 로그에만. 응답엔 없음. 조건이 쿼리에 있어 out은 보통 0(R17) — 응답 직전 재확인에서 빠진 수만 여기 선다
  "ranked": [ {"owner_user_id": "uuid", "position": 1, "topics": ["…"], "features": {…}, "score": 0.83, "talked_before": false} ],   // 섞기 전(랭커) 순서. 서빙 순서는 shuffle로 재현. talked_before는 R28의 재등장 표식(응답에는 없음). topics는 이 소유자가 어느 topic으로 순위에 들었나 — 타입 ②는 선반들을 이어 붙인 목록이라 이것이 없으면 선반 경계를 복구할 수 없다(R65)
  "basis": "content",                             // ③
  "cf_model_version": "fit-2026-09-08T03Z",       // ③ 어느 cf_candidates 스냅샷으로 답했나
  "shuffle": {"seed": "rec-…", "bands": [5, 20, 50]},   // ③ R20. bands = 구간의 누적 상한(1~5, 6~20, 21~50). 구간 안 순서를 재현하는 재료
  "latency_ms": {"query": 640, "sources": 9, "filter": 3, "rank": 1, "assemble": 12, "total": 665},
  "served_at": "2026-09-08T…Z",
  "pages": [ {"cursor": "…", "positions": [21, 40], "served_at": "…"} ],   // 다음 페이지 요청마다 한 항목(§2-4). 첫 페이지는 위 필드들
  "impressions": [                                // 실제로 화면에 그려진 카드(§2-6, R66). 스크롤을 따라 한 목록에 여러 건 온다
    {"at": "2026-09-23T…Z",                       // 보고가 우리에게 닿은 때. 우리 시계다 (§2-5의 reported_at과 같은 이유)
     "cards": [{"owner_user_id": "uuid", "position": 3, "section_topic_id": "topic_food"}]}
  ]
}
```

`filter.out`은 로그에만 있다. 응답에 실리면 불변식 5를 깬다.

**`served_at`은 답한 때이고 본 때가 아니다**(R66). 클라이언트가 미리 fetch하므로 둘은 다르고, 본 때를 말하는 것은 `impressions[]`뿐이다. 노출당 비율을 잴 때 분모는 `ranked[]`가 아니라 `impressions[]`이고, `impressions[]`가 비어 있는 항목은 **분모 0**이지 전환 0이 아니다 — 보고가 best-effort라 "안 봤다"와 "보고가 안 왔다"를 우리는 구별하지 못한다. 그 둘의 비를 재려면 클라이언트 버전별 보고율을 따로 봐야 한다.

---

## 9. 이벤트

### 9-1. 우리가 받는 것

| 이벤트 | 상태 | payload | 우리 처리 |
|---|---|---|---|
| `bourbon.friendship_changed` | **있음** (bourbon-api) | `user_low, user_high, action, occurred_at` | `friends` 미러 갱신: `accepted` 삽입, `removed` 삭제 (R17) |
| `bourbon.topics_updated` | **있음** (topic-api 워커, persona 동기화가 움직인 topic마다) | `user_id, topic_id, persona_revision, topic_revision` | 힌트. 유저 단위 debounce 뒤 내부 route `GET /users/{id}/topics?visibility=public&visibility=friends`(반복 파라미터)를 읽어 공개된 row를 통째로 교체. 상세 `agent_discovery_events.md` §2-1 |
| `bourbon.topic_visibility_changed` | **있음** (topic-api #68 — settings 쓰기 다섯 지점, 움직인 topic마다) | `user_id, topic_id`(계정 삭제는 `topic_id` 없음) | 같은 debounce → 같은 재조회. **비공개 전환은 이 경로로만 오므로 핵심**. revision이 없어 재조회는 `consistent=true`로 읽는다(R55·R56). 정의서 §2-2 |
| ~~`bourbon.personal_agent_visibility_changed`~~ | **요청 철회**(R57). bourbon-api가 만든 것은 `discoverable`이 아니라 파생 상태 `agents.public`이고, 그 변화를 알리는 이벤트는 없다 | — | 재조회가 같은 사실을 파생한다 — 읽어 온 집합에 `public` row가 있으면 `discoverable = true`. 정의서 §2-3 |
| `bourbon.agent_maturity_changed` | 정의해 요청 (성숙도 컴포넌트, 예정) | `owner_user_id, maturity, maturity_version, occurred_at` | `agents` 갱신 |
| ~~`bourbon.room_created`~~ | **요청 철회**(R51). bourbon-api가 기각하고 내부 route `GET /api/internal/rooms/{id}/agent-context`를 대안으로 줬는데, 우리에게 필요한 소유자 하나를 얻자고 이용자들의 메시지 본문을 받게 된다. 대신 추천 시점에 room id를 계산해 둔다 | — | `message_created`가 이 자리를 대신한다 |
| `bourbon.message_created` | **있음** (bourbon-api) | `room_id, message_id, sender_id, sender_type, type, room_type` | `room_type == agent_dm`인 유저 메시지마다 `room_turns[room_id]` +1(R49 — `room_created`와 순서 무관). 읽을 때 `interactions`와 `room_id`로 조인. 새 turn 이벤트 불필요 |
| `bourbon.user_registered` | **있음** (bourbon-api, 활성화 전이) | `user_id, email` | `agents` row 생성(`discoverable=false` — 첫 재조회가 뒤집는다). `email`은 읽지 않는다. 탈퇴 뒤 재가입도 같은 경로 — 신규로 본다(R38) |
| `bourbon.user_deactivated` | **있음** (bourbon-api) | `user_id` | 그 유저의 모든 데이터 삭제. `interactions`의 actor 쪽만 익명화 |

진행 방식은 우리가 먼저 미러·발행·테스트하고 그 뒤 요청한다. 재조회 tier 범위는 정해져 있다 — 타인 row는 `public`·`friends`(위 표), 요청자 자신의 프로필은 `public`·`friends`·`private`(R22). 요청자 프로필은 요청 시 topic-api 내부 route로 읽는다(R27).

**두 읽기는 일관성 수준이 다르다**(R56): 워커의 재조회는 `consistent=true`(DynamoDB 강한 읽기)로 읽는다 — 남의 row를 저장할지 정하는 읽기라 "바꾸기 전" 스냅샷 하나가 불변식 1을 깨고 다음 재조회까지 남는다. 요청 시 요청자 프로필은 약한 읽기 그대로다 — 남의 노출을 정하지 않고 응답 지연에 직접 올라탄다.

### 9-2. 우리가 내는 것

지금은 없다. 결정 로그(§8)는 저장소에 쓰고 이벤트로는 내지 않는다. 다른 서비스가 "추천이 나갔다"를 알아야 할 때 그때 정의한다.

---

## 10. 버전과 호환

세 envelope 모두 `contract_version: 1`을 갖는다. 필드 추가는 같은 버전, 필드 의미 변경이나 삭제는 버전을 올린다. `implementation`은 결정 로그에만 있고 응답에는 없다. 구현은 하나라(R34) 비교용 버전 분기는 없다.

---

## 11. 이 계약의 열린 항목

- `fit`의 내용(O5 — 기획 중: "나와 비슷해요 / 다른 관점도 살펴봐요"). 자리만 있다.
- 명시 피드백 이벤트(O6 — 제품 논의 없음). 자리도 아직 없다.
- persona(HEXACO) 입력의 경로·동의 범위·가중 규칙(O20). 자리만 있다(R42): `UserQuery.requester_traits`, feature `persona_similarity`, 설정 `rank.for_you.w_persona`.
- **타입 ③에서 소스 하나를 못 읽었을 때의 응답.** §3-4에 값이 없다. 구현(1-7)은 요청자 topic 조회(R27)가 실패하면 **503**으로 끝낸다 — 타입 ②와 같은 처리이고, "봤는데 없다"가 아니라 "못 봤다"이기 때문이다(§3-3). 다만 타입 ②와 달리 타입 ③에서 요청자 topic은 세 소스 중 하나의 입력일 뿐이라, 인기도만으로도 완전한 목록이 나온다 — 그쪽을 택하면 `degraded`에 "content를 못 읽었다"에 해당하는 값이 필요하고, 그 값은 요청자 개인에 대한 사실을 드러내지 않는다(§3-4의 조건을 만족한다). 어느 쪽이든 계약이 정할 일이라 코드에서 지어내지 않았다. 실측(1-9)에서 topic-api 장애가 이 화면을 얼마나 자주 멈추는지를 보고 정하는 것이 낫다.
- **게이트가 재는 "군집 다양성"의 실서비스 입력.** R35는 ALS와 인기도를 HR@10과 **같은 군집 비율**로 비교하라고 하고, 검증 §3-1은 합성 모집단의 persona 군집 라벨로 그것을 쟀다. 실서비스에는 그 라벨이 없다 — R42로 persona를 읽지 않고, R27로 요청자 topic을 저장하지 않는다. 1-8 구현은 가진 입력으로 같은 질문을 하는 **대리 지표**를 쓴다: 추천된 소유자가 **요청자 본인이 공개한 topic**을 공개하고 있으면 개인화 쪽으로 센다. 두 방법에 같은 자를 대므로 비교 자체는 성립하지만, 눈금이 다르다 — persona 군집은 굵은 분할이고 topic 겹침은 잘게 나뉘며 인기 소유자가 인기 topic을 갖는다(10만 실측: 인기도 0.345, ALS 0.249). 지금의 대리 지표로는 `gate.min_cluster_gain` 1.5를 넘길 수 없다. 실측(1-9)에서 두 지표를 나란히 재고, 임계를 다시 정하거나 지표를 계약에 명시하는 것이 낫다. 설정 레지스터 §4에도 같은 내용을 적어 뒀다.
- **목록 카드가 실제로 무엇을 그리는가.** §3-1의 `owner`·`agent` 필드 목록은 **디자인이 나오기 전의 기준값이지 확정이 아니다**(오너, 2026-09-22). 필드를 더하거나 빼는 것은 §3-1과 hydration 한 곳만 고치면 되는 변경이라 싸다. **비싼 쪽은 따로 있다**: 목록 단계에서 "친구예요" 같은 **뷰어에 따라 달라지는 값**을 그리기로 하면 전제 자체가 깨진다 — 우리가 친구 미러로 답하거나(그러면 불변식 3의 fail-closed가 표시 필드까지 지배한다), 클라이언트가 한 페이지마다 최대 `for_you.limit_max`번 읽거나 둘 중 하나다. 요청서 `requests/client.md` §3의 4번으로 물어 뒀다.
- **섹션을 1 hop보다 깊이 펼칠 것인가**(R65 후속). 지금은 1 hop이라 `requested: false`가 곧 "직계 자손"이고 거리를 실을 필요가 없다. 2 hop 이상으로 늘리면 그 한 비트가 자식과 손자를 구분하지 못하므로, 그때 거리를 응답에 더한다 — 필드를 더하는 것은 `contract_version`을 올리지 않는다(§10). **미리 만들지 않는다.**
- 섹션 한 개 페이지(`GET /discover/by-topic/{topic_id}`)의 응답 envelope. §3-2가 인쇄하지 않는다. 구현(1-3c에서 읽고 **1-5에서 그대로 냈다**)은 **타입 ②의 envelope에 섹션 하나**로 답한다 — 클라이언트가 `sections[0].next_cursor`를 꺼내야 하는 비용이 있다. 전용 envelope(`topic_id`·`label`·`agents`·`has_next`·`next_cursor`를 최상위에)로 정하면 §3-2에 인쇄하고 이 항목을 지운다. 클라이언트가 붙기 전이라 지금 바꾸는 값은 코드뿐이다.
