# agent-discovery-api 재설계 — 제품 모델, 세 가지 추천, 구현 뼈대, 검증 프로토콜

> 2026-09-08 오너 설명을 바탕으로 새로 시작하는 문서. **이전 recsys 문서들이 정한 제약과 결정을 전제하지 않는다.** 그 문서들은 참고 자료로 남고, 이 문서에서 다시 판단한다. 다른 문서 없이 읽히도록 필요한 사실은 본문에 풀어 썼다.
>
> 결정이 아니라 **출발점**이다. 결정은 `decisions.md`가 갖는다.

---

## 0. 한 페이지 요약

- **제품**: 모든 유저는 personal agent를 하나 가진다. agent는 유저와 대화하며 persona와 preference를 배우고, topic-api가 그 preference를 topic 트리에 grounding해 유저의 관심 topic 목록을 만든다. topic마다 공개 범위가 있고, 친구 관계가 있으며, agent 자체에도 공개 여부가 있다.
- **추천은 세 타입**이다. ① 유저가 자기 agent에게 "이 topic 잘 아는 사람 agent 찾아줘"라고 명시 요청(free text topic + context). ② 탐색 탭 서브탭: 내 topic으로 대화해 볼 수 있는 타인 agent 목록. ③ 탐색 탭 메인: 나와 비슷한 사람들이 좋아했고 내가 좋아할 만한 타인 agent 목록.
- **구현은 하나다(R34, 2026-09-09).** 처음 계획은 오픈소스 중심안(A)과 직접 구현안(B)을 둘 다 만들어 10만 합성 유저로 비교하는 것이었다(R09). 검증(`library_verification.md`)에서 타입 ①②는 PostgreSQL 인덱스가 OpenSearch보다 빠르고, CF는 `implicit` ALS가 Gorse와 동시 출현 이웃을 앞서는 것이 확인되어 비교 없이 그 조합으로 간다: **PostgreSQL 역인덱스 + 인기도 + content 유사도 + `implicit` ALS**. 합성 모집단은 이 구현의 품질·부하 검증에 쓴다. §5의 A안/B안 절은 그 판단의 기록이다.
- **저장소는 MySQL, PostgreSQL, DynamoDB, Redis, OpenSearch 다섯 가지 안에서** 고른다. 다른 저장소 추가는 선호하지 않는다.
- **지금 없는 것은 상호작용 로그다.** 타입 ③의 협업 필터링(CF)은 "누가 어떤 agent와 대화했나"가 쌓여야 학습된다. 이벤트는 우리가 정의해 발행 측에 요청하거나 PR로 추가한다. 쌓이기 전까지 메인 탭은 인기도로 시작해도 된다.

---

## 1. 제품 모델

### 1-1. 구성 요소와 데이터 흐름

```
user ──대화──▶ personal agent (bourbon-agent)
                  │  persona + preference 추출
                  ▼  이벤트
             topic-api ── grounding ──▶ user topics (topic_id, visibility, 임시 성숙도)
                  │                         │ 유저에게 표시, 유저가 visibility 편집
                  ▼  이벤트(있음: bourbon.topics_updated) ▼
          agent-discovery-api  ◀── friend 관계 이벤트 ── bourbon-api
                  │                                      (agent visibility도 여기)
                  ▼
        타인 agent 추천 (세 타입) ──▶ 유저가 타인 agent와 대화 시작
```

- **personal agent의 id는 user id에서 결정론적으로 계산**된다. 따라서 "agent를 추천한다"와 "그 agent의 소유자 유저를 고른다"는 같은 일이고, 추천 대상 집합의 크기는 유저 수와 같다.
- **persona / preference 추출**은 bourbon-agent가 한다. 추출되면 `bourbon.persona_updated`를 발행하고 topic-api 워커가 받아 topic에 grounding한다(연결은 진행 중). topic-api는 변경된 topic마다 `bourbon.topics_updated`를 이미 발행한다. persona는 sharable·private 두 slot × `bio`·`traits`·`preferences` 세 레이어이고, **topic-api가 grounding하는 것은 `preferences` 레이어 하나다**(2026-09-10 코드 확인, §1-2). HEXACO 25 facet 추정치·자유 성향·traits 서술형 텍스트·bio는 topic으로 오지 않는다 — 이 중 HEXACO의 활용 방향과 코드 자리는 R42, 실제 도입은 O20.
- **topic별 visibility**는 topic-api가 유저에게 직접 노출해 관리한다. 값은 네 가지다: `public`, `friends`, `private`, `hidden`. `hidden`은 삭제 대신 숨기기로, 본인 외 어느 목록에도 나오지 않는다. 타인이 이 유저의 agent와 대화할 때, agent는 두 사람의 관계와 topic의 visibility로 기억과 preference의 접근을 제어한다.
- **friend 관계**는 요청과 수락으로 성립한다. bourbon-api가 관리하고, 성립·해제 시 `bourbon.friendship_changed` 이벤트를 **이미 발행한다** (`accepted` / `removed`, 두 user id를 정렬한 canonical pair). 친구 목록 조회 route도 있고, 한 유저의 친구 상한은 5,000이다.
- **default는 private다.** 새로 생긴 topic도, agent 자체도 private로 시작하고, 유저가 명시적으로 `public`이나 `friends`로 바꾼다. **다시 private로 돌아갈 수도 있다.** 그러므로 추천 대상은 "유저가 공개한 것"뿐이고, 비공개로 되돌리면 즉시 빠져야 한다(§3-2).
- **agent 공개 여부**(추천에 나올 수 있는가)는 bourbon-api의 새 필드 `discoverable`(기본 false, R23)이다. agent가 동작하는가(`enabled`)와 다른 축이다 — 쓰되 목록에는 안 올리는 선택이 있다. topic의 공개 여부에서 유도하지 말고 **받은 값을 그대로 저장**한다(R06: default private, 되돌릴 수 있다).
- **성숙도**는 topic 단위와 agent 단위 둘이 있다. 둘 다 전용 컴포넌트가 아직 없다. topic 성숙도는 topic-api가 임시로 단순 계산해 넣고 있고, agent 성숙도는 곧 들어올 예정이다. 추천에서는 **랭커 feature 하나**로 두고, 값의 출처가 바뀌어도 자리는 유지되게 설계한다.

### 1-2. 코드에서 확인한 사실 (2026-09-08, 2026-09-10 추가)

| 사실 | 어디서 |
|---|---|
| visibility는 `public / friends / private / hidden` 네 값 | topic-api `topic/structs.py` `Visibility` |
| friend 성립·해제 이벤트 `bourbon.friendship_changed`가 이미 있다 | bourbon-api `friends/events.py` |
| topic-api는 friends tier를 **fail-closed**로 판정한다: bourbon-api 조회에 실패하면 "친구 없음"으로 답하고 public만 보여준다. 실패는 캐시하지 않는다 | topic-api `topic/visibility/friends.py` |
| topic-api의 타인 topic 조회는 "friends tier를 안 가짐"과 "친구가 아니라서 안 보여줌"을 응답에서 구별할 수 없게 만든다. 구별되면 숨긴 topic의 존재가 유출되기 때문 | topic-api `api/routers/users/router.py` |
| topic-api는 같은 라우터를 두 prefix로 붙인다. `/api/svc/topic`은 edge-auth가 `x-user-id`를 채우는 클라이언트 API, `/api/internal/svc/topic`은 서비스가 user_id를 경로에 명시하는 내부 API | topic-api `api/main.py`, `api/surfaces.py` |
| free text를 topic으로 바꾸는 검색 route가 내부 API에 있다 (`/search/topics`) | topic-api `api/routers/internal/search/router.py` |
| 우리 코드에 free text → 개념 확장(LLM) → topic-api 검색 → topic 확정 단계가 이미 있다 | 이 repo `agent_discovery/stages/grounding.py` 등 |
| topic-api는 deferq 워커로 `bourbon.persona_updated`를 소비해 persona를 topic에 동기화하고, 변경된 topic마다 `bourbon.topics_updated`를 발행한다. 유저의 visibility 편집(api 프로세스)은 아무것도 발행하지 않는다 | topic-api `worker/listener.py`, `worker/events.py` |
| bourbon-agent가 **발행하는 이벤트는 `bourbon.persona_updated` 하나**다. payload의 `changes[].topics`는 preferences 마크다운의 헤딩 텍스트이고 topic id는 없다. 추출은 소유자가 말한 모든 방을 5분 debounce(상한 30분) 뒤 LLM 1회로 처리하며 bio·traits(HEXACO)·preferences를 한 번에 낸다. preferences만 두 번째 LLM 호출로 "평가가 담긴 문장"만 남긴다 | bourbon-agent `bourbon_agent/events.py`, `persona_extractor/pipeline.py`, `persona_extractor/detail_filter.py` (2026-09-10) |
| topic-api 워커는 bourbon-agent의 persona 테이블 sharable slot을 **복호화 키를 공유해 직접 읽고** `preferences` 레이어만 문서로 만든다. `bio`·`traits`는 의도적으로 제외한다(traits 섹션을 신호로 읽었더니 잘못된 interest topic이 생긴 사례가 코드 주석에 있다) | topic-api `topic/agent_persona/persona.py`, `topic/storage/agent_persona.py` (2026-09-10) |
| HEXACO 추정치(25 facet, 1.0~5.0, confidence, 관측 수)는 persona slot이 아니라 **추출 노트**(`PERSONA_EXTRACTION#note`)에 있고 visibility 구분이 없다. persona slot의 `traits`는 서술형 텍스트다. persona 텍스트는 대화 언어와 무관하게 영어다 | bourbon-agent `bourbon_agent/user_persona/extraction_note.py`, `persona_extractor/prompt/system.py` (2026-09-10) |
| 타인 agent와의 대화는 `AGENT_DM` room(`A:B'`, 방향성). main에서는 두 사람이 친구여야 열 수 있고, 임시 브랜치가 그 게이트를 내린다. **오너(2026-09-08): 친구가 아니어도 열 수 있게 할 것이며 방법은 bourbon-api의 몫.** 추천은 public agent가 누구에게나 열린다고 전제한다 | bourbon-api `rooms/models.py` `RoomType`, `rooms/service.py` `ensure_agent_dm_room` |

### 1-3. 호출 API

topic-api의 두 prefix 패턴을 그대로 따른다.

| 타입 | 호출자 | API | 요청자 식별 |
|---|---|---|---|
| ① 명시 요청 | bourbon-agent | 내부 (`/api/internal/svc/agent-discovery/…`) | 요청 body나 경로의 `user_id`. 내부 API는 edge-auth를 거치지 않으므로 **`x-user-id` 헤더를 읽지 않는다** |
| ②, ③ 탐색 탭 | 클라이언트 직접 호출 (오너 2026-09-08: topic-api가 `/api/svc/topic`을 열어 둔 것과 같은 형태) | 클라이언트 (`/api/svc/agent-discovery/…`) | edge-auth가 채운 `x-user-id` |

두 API가 같은 도메인 코드를 호출하고, 요청자 id가 어디서 오는지만 다르다.

---

## 2. 세 가지 추천

| | ① 명시 요청 | ② 탐색 서브탭 | ③ 탐색 메인 |
|---|---|---|---|
| 입력 | free text topic + 대화 context | 요청자의 grounding된 topic 집합 | 요청자의 topic + (쌓이면) 상호작용 로그 + (O20 뒤) HEXACO 성향(R42, 지금은 자리만) |
| 요청 시 외부 호출 | LLM(개념 확장) + topic-api 검색 | 요청자 topic 목록 조회 1회 (topic-api 내부 route, R27) | 같은 조회 1회 (R27) |
| 핵심 계산 | text → 1~3개 topic → **topic 커버리지 순** agent | topic → agent (content 매칭) | 유사 유저 → 그들이 좋아한 agent (CF) + 내가 좋아할 agent (content) |
| 예상 지연 시간 | LLM이 대부분을 차지, 수백 ms~수 초 | 수십 ms | 수십 ms (사전 계산 결과 읽기) |
| 결과 수 | 소수 (대화 안에서 제시) | 목록 | 목록 |

### 2-1. 타입 ①: free text → topic → 커버리지 순서

예: "캠핑하면서 핸드드립커피" → `camping`, `hand-drip coffee` 두 topic(라벨은 예시). 순서 규칙은 오너가 말한 대로다.

1. **뽑힌 topic을 모두 가진 agent가 먼저** 나온다.
2. 그 다음 일부만 가진 agent가 나온다. 많이 가진 쪽이 먼저다.
3. 같은 커버리지 안에서는 topic별 점수(preference 강도, 성숙도)와 agent 성숙도로 순서를 정한다.

즉 1차 정렬 키는 **커버한 topic 수**이고, 2차 키가 점수다. 뽑히는 topic은 하나일 수도, 두세 개일 수도 있다. **상한은 우선 3개**(오너 2026-09-08). 네 개 이상이면 커버리지 조합이 늘고 LLM 프롬프트도 흐려지므로, 3개를 넘게 뽑히면 점수 상위 3개만 쓴다.

text → topic 단계는 우리 코드에 이미 있는 흐름(LLM으로 개념 묶음을 만들고, 묶음마다 topic-api 검색을 해 하나로 확정)을 쓴다. 확정된 topic이 하나도 없으면 "요청이 모호함"(4xx)이고, topic-api나 LLM이 응답하지 않아 확정을 못 한 것은 "우리가 답하지 못함"(5xx)이다. 이 둘을 섞지 않는다.

### 2-2. 타입 ②: 내 topic으로 대화해 볼 타인 agent

topic-api가 이미 grounding해 둔 요청자의 topic만 쓴다. LLM도 topic-api 호출도 없다. **목록은 topic별 묶음**이다(오너 2026-09-08): "camping으로 대화해 볼 agent N명", "hand-drip coffee로 N명" 같이 요청자의 topic 하나가 섹션 하나다.

따라서 타입 ②는 커버리지 정렬이 없다. topic 하나에 대해 그 topic을 가진 agent를 점수 순으로 내는 **단일 topic 조회**를 요청자의 topic 수만큼 한다. 같은 agent가 여러 섹션에 나올 수 있고, 그것은 정상이다. 요청자의 topic이 많으면(수십 개) 섹션 순서와 페이지가 필요하다: 요청자 쪽 preference 점수가 높은 topic부터, 섹션당 N명, 섹션 단위 페이지.

계산은 타입 ①의 "topic 하나 → agent 목록" 조회와 같다. 인덱스는 공유한다.

### 2-3. 타입 ③: 비슷한 사람들이 좋아한, 내가 좋아할 만한

두 신호가 섞인다.

- **"비슷한 사람들이 좋아했던"** = CF. (요청자, 타인 agent) 상호작용이 있어야 한다. 아이템 수가 유저 수와 같고, 한 유저가 대화해 볼 agent는 많지 않으므로 행렬은 매우 희소하다. CF가 의미 있으려면 로그가 어느 정도 쌓여야 하고, 그 전까지는 다음 순서로 간다.
  1. **인기도** (오너 허용): 최근 기간에 많이 대화가 시작된 agent. 새 유저에게도 답이 나온다.
  2. **content 유사도**: 요청자의 topic 집합과 겹치는 topic을 가진 agent. 정의(R25): 겹침은 카탈로그 계층을 따라 감쇠하고(양방향 최단 hop, topic-api 검색 설정에서 빌린 0.6/hop, 최대 3 hop) 흔한 topic은 IDF로 낮추며, 임베딩 kNN은 넣지 않는다 — 카탈로그가 이미 의미 계층이다. 카탈로그는 topic-api의 `catalog.json`을 빌드 때 복사한다(R26). 요청자의 프로필은 본인 `public`·`friends`·`private` topic이고(R22), 타인 agent 방에서 한 말도 bourbon-agent의 추출 → topic-api를 거쳐 여기로 들어온다. 그래서 "대화한 agent의 topic을 프로필에 더하는" 별도 경로는 없다(R25).
  3. **CF**: 로그가 쌓이면 행렬 분해(`implicit` ALS, R33) 점수를 랭커 feature로 섞는다. 가중은 자동 게이트가 올린다(R35).
- **"내가 좋아할 만한"** = content. 2번과 같다.

인기도 → content → CF는 대체가 아니라 **누적**이다. 셋을 다 feature로 받는 랭커 하나가 순서를 정하고, 신호가 없을 때는 그 feature가 0이 된다.

네 번째 feature 자리가 예약되어 있다(R42): **`persona_similarity`** — 요청자와 소유자의 HEXACO 성향 벡터 유사도. topic이 겹치지 않아도 성향이 맞는 사람을 찾아내는 신호로, content(topic 겹침)와 CF(행동)가 답하지 못하는 것이다. bourbon-agent의 persona 테이블을 직접 읽지 않고(복호화 키 공유 없음) bourbon-agent가 **이벤트**로 주는 것을 받는다 — 방향만이고 확정은 아니지만, bourbon-agent에 API(내부 route)를 열 가능성은 없다(오너 2026-09-10). 경로·동의 범위·가중 규칙·검증은 O20이고, 그때까지 feature는 0이라 목록은 바뀌지 않는다.

이 구조 덕에 사전 계산을 **읽혔거나 활동한 유저만, 그 뒤에** 갱신해도 화면에 구멍이 없다(R19). 셋 중 사전 계산인 것은 CF top-K 하나고 인기도·content는 요청 시 계산이다. 오래된 항목은 한 번 그대로 서빙하고, 그 요청 뒤 워커 스윕이 다시 만든다. 항목이 없는 신규 유저는 CF feature만 0인 완전한 목록을 받는다. 타입 ③ 최종 목록은 점수 구간 안에서 섞어 같은 사람만 보이지 않게 한다(R20 — O15의 첫 답). 후보(소유자) 쪽은 활동 여부로 빼지 않는다 — `recency`·`popularity`가 순위로 내리고, 하드 제외는 하지 않는다(R31).

### 2-4. "왜 맞는지 / 안 맞는지"

탐색 탭에서 "이 agent가 나와 어디가 맞고 어디가 안 맞는지"를 보여주는 것은 미확정이지만 필요할 수 있다. 랭커가 feature 벡터로 점수를 내면 그 feature가 그대로 설명 재료가 된다(겹치는 topic, 겹치지 않는 topic, 성숙도 차이, "비슷한 사람 N명이 대화함"). 처음부터 점수를 **feature별로 분해 가능하게** 두면 나중에 비용 없이 붙인다. HEXACO가 들어오면(O20) "다른 관점도 살펴봐요"의 재료도 여기서 나온다 — 겹치지 않는 topic은 관심이 없다는 뜻이지 다른 관점이라는 뜻이 아니라서, 성향 축이 있어야 부정 표시(R41) 없이 그 축을 설명할 수 있다.

### 2-5. 확장

네 번째 타입이 들어오면 **쿼리 생성기 하나와 후보 소스 조합 하나**를 추가하는 일이어야 한다(§5). 랭커·필터·응답 조립은 공유한다.

---

## 3. visibility와 friend — 후보 필터

### 3-1. 규칙

추천은 public을 우선하되 friends까지 포함한다(오너). visibility는 이미 유저가 고르는 값이므로 **friends tier는 처음부터 후보에 든다**: friends로 공개한 유저는 친구에게 보일 것을 기대한다. 규칙은 이렇다.

- **agent visibility가 private면 어떤 추천에도 나오지 않는다.** topic 상태와 무관하게 받은 값으로 판정한다.
- **topic이 `public`이면** 모든 요청자에게 후보다.
- **topic이 `friends`면** 요청자가 그 agent 소유자의 친구일 때만 후보다.
- **`private`, `hidden`은 후보 저장소에 들어오지 않는다.** 타인의 것은 그 두 tier를 읽지 않는다. 미러에 없으니 셀 수도 없다. 요청자 **자신의** topic 목록(타입 ②③의 입력)은 본인의 `public`·`friends`·`private`을 읽고 `hidden`은 읽지 않는다(R22). 요청 시 topic-api 내부 route로 읽는다(R27).
- **판정은 후보 단계**에서 한다. 랭킹 뒤에 가리면 "몇 개가 가려졌다"가 유출되고, 페이지 크기도 흔들린다.
- **fail-closed**: 친구 집합을 못 가져오면 friends tier는 후보에서 빠지고 public만 답한다. 에러가 아니라 축소된 답이다. topic-api와 같은 계약이다. (R17·R18로 친구 집합이 공개된 row와 같은 PostgreSQL에 있으므로 이 경우는 저장소 장애 = 503이고, 축소 응답 `friends_unavailable`은 계약에 예약만 되어 있다.)
- **구별 불가**: 응답은 "friends topic이 있는데 안 보여줌"과 "그런 topic 없음"을 같게 만든다. 가려진 개수, 가려졌다는 표시를 넣지 않는다.

### 3-2. 저장 모양에 주는 영향 — 회귀(비공개 전환)를 먼저 설계한다

default가 private이고 언제든 private로 돌아가므로, 저장소에는 **"공개된 (topic, agent) row만 있다"**가 불변식이다. 이벤트는 "공개"보다 "비공개 전환"을 놓치면 안 된다.

- topic이 `public`/`friends` → `private`/`hidden`으로 바뀌면 해당 row를 **지운다.** 갱신이 아니라 삭제다.
- agent가 `private`로 바뀌면 그 agent의 row를 **모두 지운다.**
- 사전 계산 결과(타입 ③의 유저별 top-K `cf_candidates`)는 계산 시점의 스냅샷이다. 그 안에 있는 agent가 그 사이에 비공개로 돌아갔을 수 있으므로 **응답 직전에 현재 row 존재 여부로 다시 거른다.** 사전 계산은 후보를 좁힐 뿐 노출을 허가하지 않는다.
- 놓친 이벤트에 대비한다. 놓친 "공개"는 늦게 나타나는 손해지만, 놓친 "비공개 전환"은 유저가 비공개로 되돌린 것을 계속 보여주는 사고다. **topic 이벤트를 힌트로만 받고 그 유저의 공개된 집합을 topic-api에서 재조회해 통째로 교체하면** 다음 힌트의 재조회가 어긋남을 고치므로 별도 정합성 검사가 필요 없다. topic-api가 스스로 이벤트를 그렇게 정의했다(`agent_discovery_events.md` §1·§2-1).

### 3-3. 저장 모양

후보 row는 `(topic_id, owner_user_id, tier ∈ {public, friends}, 점수…)`로 tier를 같이 갖는다. 요청 시:

```
후보(topic, 요청자 R) = rows[topic, tier=public]
                     ∪ (rows[topic, tier=friends] ∩ {agent | owner(agent) ∈ friends(R)})
```

friends(R)는 `bourbon.friendship_changed`로 우리 저장소에 **미러한다**(R17). 요청 시 bourbon-api를 읽는 방식(topic-api의 조회+TTL 캐시)은 hot path에 외부 호출을 넣고 실패하면 축소 응답을 강제하므로 쓰지 않는다. 친구 상한 5,000이므로 한 요청자의 집합은 항상 작고, 위 합집합은 **후보 조회 쿼리 하나의 WHERE 절**이다. friend 관계가 바뀌어도 **재인덱싱이 필요 없다.** 교집합이 요청 시 계산이기 때문이다.

CF·인기도 신호(§2-3)에도 같은 조건이 걸린다. "비슷한 사람들이 좋아한 agent"가 요청자에게 안 보이는 tier만 가진 agent라면 후보에서 빠진다. 우리 저장소를 읽는 소스는 조건을 쿼리에 넣고, 요청자별 사전 계산은 배치 시점 친구 집합으로 후보를 제한하며, 조건을 넣을 수 없는 외부 엔진 결과만 넉넉히 받아 뒤에서 거른다(계약 §4-2).

---

## 4. 이벤트 — 있는 것과 정의해야 할 것

이벤트는 우리가 필요한 것을 정의하고, 줄 수 있는 컴포넌트에 요청하거나 우리가 PR로 추가한다(오너). 지금 없는 것은 "아직 안 붙인 것"이지 "붙일 수 없는 것"이 아니다.

### 4-1. 있는 것

| 이벤트 | 발행 | 내용 | 우리 용도 |
|---|---|---|---|
| `bourbon.friendship_changed` | bourbon-api | `user_low, user_high, action(accepted/removed), occurred_at` | friends tier 필터의 친구 집합(`friends` 미러, R17) |
| `bourbon.topics_updated` | topic-api 워커 | `user_id, topic_id, persona_revision, topic_revision` | 재조회 힌트 → 정의서 §2-1 |
| `bourbon.message_created` | bourbon-api | `room_id, room_type, sender_type, …` | turn 카운트 → 정의서 §2-5 |
| `bourbon.user_registered` / `bourbon.user_deactivated` | bourbon-api | `user_id`(`email`은 읽지 않는다) / `user_id` | `agents` 풀 생성·삭제 → 정의서 §2-7 |

### 4-2. 정의해서 요청할 것

> 아래 표는 첫 스케치다. 세 repo 코드 조사 뒤의 정의는 `agent_discovery_events.md`가 갖는다 — topic 변경은 이미 있는 `bourbon.topics_updated`를 힌트로 받아 재조회, 비공개 전환은 topic-api api 프로세스에 새 이벤트 요청, 대화 시작은 `AGENT_DM` room 열기, turn은 이미 있는 `message_created`로. 진행 방식은 우리가 먼저 정의·발행·테스트하고 뒤에 요청한다(오너 2026-09-08).

| 필요 | 정의 |
|---|---|
| user topic 변경(공개·점수) | 있음 — `bourbon.topics_updated`를 힌트로 재조회 → 이벤트 정의서 §2-1 |
| user topic 비공개 전환(visibility 편집) | topic-api에 필요만 요청, 형태는 topic-api 선택(R48) → 정의서 §2-2 |
| agent 공개 여부 | 우리가 정의 — 새 필드 `discoverable`(R23) → 정의서 §2-3 |
| 대화 시작 | bourbon-api의 일반 이벤트 `bourbon.room_created`(R46) → 정의서 §2-4. 귀속 키는 클라이언트가 우리 route에 직접 보고(R47, 계약 §2-5) |
| 대화 진행(turn) | 있음 — `bourbon.message_created` 조인 → 정의서 §2-5 |
| agent 성숙도 | 컴포넌트 생기면 → 정의서 §2-6 |
| 재방문 | 위에서 유도 — 같은 (actor, owner)의 두 번째 이후 시작. 강한 긍정 신호 |
| 명시 피드백(있다면) | 클라이언트가 내는 좋아요 / 숨기기 / 관심 없음. 부정 신호는 로그로 유도가 안 되므로 있으면 가치가 크다(O6) |

우리 자신은 **추천 노출과 선택**을 기록한다: 어떤 요청에 어떤 agent를 어느 순위로 내놨고 무엇이 선택됐나. 대화 시작 이벤트의 `recommendation_id`가 이 기록과 이어진다. 이것이 오프라인 평가의 정답 로그다.

이 데이터는 처음에 없다. 그래서 타입 ③은 인기도부터 시작하고, 인기도(R29)는 위 이벤트에서 계산된다. **즉 대화 시작 이벤트는 CF 전에 인기도를 위해서도 첫 번째로 필요하다.**

---

## 5. 구현 뼈대

**요청·응답 계약, 필터, 평가 로그**는 후보 소스 구현과 분리한다. 클라이언트와 bourbon-agent는 어느 소스가 뒤에 있는지 모른다. 그래야 §6의 소스별 ablation이 공정하고, 뒤에 소스를 교체할 수 있다. 구현은 하나지만(R34) 이 분리는 남긴다.

```
요청 ─▶ 쿼리 생성 ─▶ 후보 소스들 ─▶ visibility 필터 ─▶ 랭커 ─▶ 응답 조립(설명 포함) ─▶ 응답
        타입별      소스별            공통               공통     공통
```

- **쿼리 생성**: 타입 ①은 text → topic 목록, 타입 ②는 요청자 topic 목록, 타입 ③은 요청자 id(사전 계산 결과의 키). 새 타입 = 새 쿼리 생성기.
- **후보 소스**: `(쿼리) → [(agent_id, tier, 소스별 점수)]`를 내는 것들. 한 요청이 여러 소스를 합칠 수 있다. 소스 구현은 이 인터페이스 뒤에서 교체된다(계약 §4-2).
- **visibility 필터**: §3. 소스와 무관하게 하나.
- **랭커**: feature 벡터 → 점수. feature 목록은 계약 §7(커버리지, topic 점수, topic 성숙도, agent 성숙도, 인기도, content 유사도, CF 점수, 유사 유저 수, 최근성, friends tier 여부). 처음엔 가중합, 로그가 쌓이면 학습.
- **응답 조립**: 응답 + 설명 재료 + 결정 로그.

### 5-1. A안 — 오픈소스 recsys를 중심에 (비교 설계 시점의 기록)

> R33·R34(2026-09-09): A안에서 채택된 것은 라이브러리형 `implicit`뿐이다. Gorse와 OpenSearch 인덱스는 제외. 아래는 그 판단 전의 기록이다.

검증된 엔진을 쓰되, 타입 ①②의 "topic 커버리지 순서"와 "요청자별 friends 필터"는 **어느 범용 엔진도 그대로 제공하지 않는다.** 따라서 A안도 후보 단계에 우리 인덱스가 하나는 필요하다. A안의 핵심은 "타입 ③의 CF·인기도·유사 이웃 계산을 엔진에 맡긴다"이다.

| 역할 | 후보 | 저장소(허용 목록 안) |
|---|---|---|
| 타입 ③ CF + 인기도 + 유저 이웃 | Gorse (서비스형, 자체 스케줄러·대시보드, MySQL/PostgreSQL data store + cache store — Redis cache store는 Redis Stack 전용이라 ElastiCache 불가, 검증 §4-1) 또는 `implicit` (라이브러리형, 배치로 돌려 유저별 top-K를 `cf_candidates`에 씀. LightFM은 Python 3.14 빌드 실패로 제외) | Gorse: MySQL 또는 PostgreSQL 둘(data·cache). `implicit`: 결과만 DynamoDB(R18) |
| 타입 ①② topic → agent | OpenSearch (topic id를 term으로 인덱싱, 커버리지는 matched term 수로 정렬 가능) 또는 아래 B안의 인덱스 | OpenSearch 또는 PostgreSQL |
| topic·friend·agent visibility 미러 | B안과 같은 PostgreSQL 테이블 | PostgreSQL |

**A안의 장점**: CF와 인기도, 유저-유저 이웃, 재계산 스케줄, 평가 지표를 만들지 않고 얻는다. 엔진이 검증돼 있고 커뮤니티가 있다. **A안이 어려운 점**: 엔진의 아이템·유저·feedback 모델에 우리 모양(아이템 = 유저, tier가 요청자마다 다름, 커버리지 정렬)을 끼워 넣어야 한다. 엔진이 요청자별 필터를 못 하므로 엔진 결과를 받아 우리가 다시 거르고, 걸러서 부족하면 더 받아야 한다. 컴포넌트가 하나 더 돌고, 그 컴포넌트의 재계산 비용·메모리·장애 모드를 우리가 운영한다. 실측에서 재계산 시간이 아이템 수에 비례해 자라는 것이 이미 확인됐다(`library_verification.md` §4, 이 문서의 전제는 아님).

### 5-2. B안 — 우리 서비스 모양에 맞춘 직접 구현 (인덱스·인기도·content는 이대로 구현)

> R34(2026-09-09): 아래 표의 인덱스·인기도·content 유사도·재계산 행이 구현이다. CF 행의 동시 출현 이웃은 만들지 않고 `implicit` ALS로 대신한다(R33).

기존 recsys의 계산법을 참고해 우리가 구현한다. 목표는 **빠른 응답, 낮은 재계산 비용, 우리 모양 그대로**다.

| 역할 | 구현 | 저장소 |
|---|---|---|
| topic → agent 인덱스 | `(topic_id, tier, agent_id, 점수)` 역인덱스. 타입 ①은 topic별 목록을 읽어 agent별 커버 수를 세고 정렬(topic ≤ 3이므로 목록 3개 합치기). 타입 ②도 같음 | PostgreSQL (B-tree 하나). 캐시 없음 — 실측 p50 0.8 ms라 필요 없다(검증 §2) |
| 인기도 | 대화 시작 이벤트를 받아 시간 감쇠 카운터 | PostgreSQL 테이블. `visible_topic_rows`와 같은 DB여야 visibility 조건을 조인으로 붙일 수 있다(R17). sorted set은 쓰지 않는다(R18) |
| content 유사 유저 | 요청자 topic 집합과의 가중 겹침 — IDF 가중 + 카탈로그 계층 감쇠 0.6/hop·최대 3 hop(R25). 벡터 kNN은 R25가 다시 볼 조건(grounding 실패 비율)이 나쁠 때만 | PostgreSQL (같은 인덱스 + 카탈로그 edge 테이블 — topic-api의 `catalog.json`을 빌드 때 복사, R26). 벡터 kNN은 pgvector / OpenSearch |
| CF | `implicit` ALS를 배치로 돌려 유저별 top-K를 DynamoDB `cf_candidates`에 저장(R33·R34). 동시 출현 이웃(`cf_item`)은 만들지 않는다 — 검증 §3에서 ALS의 절반이었다 | 유저별 top-K는 DynamoDB `cf_candidates`, 로그는 PostgreSQL `interactions` (R18) |
| 재계산 | 이벤트 도착 시 해당 유저 row만 갱신(증분). CF만 주기 배치(전역 학습 + 읽기 기준 스윕, R19). 인기도 카운터는 대화 시작 이벤트로 증분 | |

**B안의 장점**: 커버리지 정렬과 friends 필터가 인덱스 구조 그 자체다. 재계산이 "바뀐 유저의 row"로 국소화된다. 컴포넌트가 우리 API와 워커 둘이다. 저장소가 플랫폼에 이미 있고 운영 절차가 있는 것(PostgreSQL, DynamoDB)이다. **B안이 어려운 점**: CF·평가·튜닝을 우리가 만들고 검증해야 한다. 오픈소스 엔진이 무료로 주는 대시보드·A/B·지표를 직접 만든다. 유저가 늘어 인덱스가 한 노드를 넘을 때의 샤딩을 우리가 설계한다. "검증된 recsys"라는 신뢰를 우리 테스트로 대신해야 한다.

### 5-3. 채택된 조합 (R34)

**B안의 인덱스로 타입 ①②를, 라이브러리형 `implicit` ALS로 타입 ③의 CF 점수를** 내고 랭커에서 합친다. 처음에는 이것을 "혼합"이라 부르고 A·B 순수형과 함께 재려 했으나, 검증 결과가 방향을 정해 이것이 구현이다(R34). 실제 흐름은 `agent_discovery_walkthrough.md`.

---

## 6. 검증 프로토콜 — 10만 합성 유저

### 6-1. 무엇을 재나

| 바로 잴 수 있음 | 조건이 붙음 |
|---|---|
| 타입 ①②③ 각각의 요청 지연 시간 p50 / p95 (동시성 고정) | **CF 품질**: 합성 데이터에 심어 둔 잠재 구조가 있어야 recall@K가 의미 있다 |
| 재계산 시간, 그 동안 CPU·RAM | **content 품질**: 합성 persona의 topic 분포가 실제와 닮아야 한다 |
| 저장 용량, 월 비용(도쿄 단가) | |
| 컴포넌트 수, 장애 시 동작(CF 워커 중단, `cf_candidates` 비어 있음, 이벤트 유입 중단 — `friendship_changed`·`topics_updated` 지연) | |
| 증분 갱신 지연 시간(이벤트 → 추천 반영) | |

**합성 데이터 생성기가 검증의 절반**이다. 소스별 ablation(인기도만·content만·CF만·합친 랭커)이 같은 정답을 상대해야 하므로 생성기 스펙을 먼저 고정한다.

### 6-2. 합성 데이터 생성기 스펙 (초안)

파라미터 U(유저 수)로 돌릴 수 있게 만들어 10만에서 재고 100만으로 다시 잰다.

| 요소 | 생성 방식 | 왜 |
|---|---|---|
| persona 군집 | K개 군집(값은 `synthetic_population_spec.md` §2), 군집마다 topic 선호 분포 | "비슷한 사람"의 정답. CF와 content 유사도의 ground truth |
| 유저 → 군집 | 각 유저는 주 군집 1 + 부 군집 0~2 | 경계가 흐린 유저가 있어야 현실적 |
| 유저 topic 수 | 로그정규(값은 스펙 §2) | topic-api 실데이터 분포가 있으면 그것으로 교체 |
| topic 선택 | 군집 분포에서 Zipf 샘플 + 소량 랜덤 | 인기 topic과 희귀 topic이 같이 있어야 커버리지 정렬이 테스트됨 |
| topic 점수·성숙도 | 유저별 분포 | 랭커 2차 키 |
| visibility | **default private에서 유저가 공개한 비율**로 생성. 예: 유저의 60%가 하나 이상 공개하고, 공개한 유저의 topic 중 public 40 / friends 20 / private 35 / hidden 5(스펙 §2 `tier_mix_of_opened`). 비율은 베타 뒤 실측으로 교체 | 추천 가능 집합이 전체보다 훨씬 작다는 현실을 반영. 이 비율이 콜드스타트와 friends 필터 효과를 좌우 |
| 공개·비공개 전환 이벤트 시퀀스 | 생성 뒤 일부 topic을 비공개로 되돌리는 이벤트 시퀀스를 함께 생성 | §3-2 삭제 경로와 응답 직전 재확인이 실제로 동작하는지 테스트 |
| agent visibility | 규칙 그대로 + 소량 예외 | 규칙이 분리될 수 있음을 테스트 |
| friend 그래프 | 군집 내 확률 높게, degree 로그정규(스펙 §2), 상한 5,000 | friends tier 후보가 요청자마다 달라지는 정도 |
| 상호작용 로그 | 잠재 친화도(요청자 군집 × agent 소유자 군집) + agent 인기도 + 노이즈로 (actor, agent, 시각, turns) 생성 | CF 정답. 노이즈 비율을 바꿔 CF가 무너지는 지점을 본다 |
| 타입 ① 쿼리 | topic 라벨 1~3개를 자연어 템플릿에 끼움 | text → topic 단계와 커버리지 정렬 평가 |

정답은 생성기가 안다: 유저 u에 대해 "같은 군집 유저가 많이 대화한 agent", "u의 topic을 모두 가진 agent" 등. 이걸로 recall@10, NDCG@10, 커버리지 정렬 위반 수를 계산한다.

### 6-3. 측정 항목

| 항목 | 어떻게 |
|---|---|
| 지연 시간 | 타입별 p50/p95, 동시성 1·10·50. text → topic 단계는 소스와 무관하므로 분리 측정해 뺀 값도 기록 |
| 재계산 | 전체 재계산 1회 시간과 자원, 이벤트 1건 반영 지연 시간 |
| 저장 | 저장소별 용량(10만·100만), 도쿄 월 단가로 환산 |
| 품질 | recall@10, NDCG@10(타입 ③ — R20 섞기 **전** 순서로 잰다). 타입 ③은 **인기도만·content만·CF만** 단독 행과 합친 랭커를 같은 표에 놓는다(검증 §3은 content만 행이 없었다). 커버리지 위반 0건(타입 ①), 콜드스타트 유저(로그 0)에서의 결과 |
| 운영 | 컴포넌트 수, 장애 주입 3종(CF 워커 중단 / `cf_candidates` 비어 있음 / 이벤트 유입 중단)의 응답 |
| 확장 | 10만 → 100만에서 위 값의 증가율 |

### 6-4. 공정성 규칙

같은 머신, 같은 합성 데이터, 같은 visibility 필터 코드, 같은 랭커 feature 정의. 설정값(`agent_discovery_settings.md`) 변경은 기록한다. 단계별로 따로 재서 "어디서 시간이 가나"가 보이게 한다.

### 6-5. 산출물

검증 결과 문서 한 편. 표로 정리된 위 측정치와, 그 위에서 정하는 **설정 초기값**(랭커 가중, CF 게이트 임계, 갱신 값). 그 문서는 근거이고, 값은 `agent_discovery_settings.md`에, 결정은 `decisions.md`에 R 행으로 적는다.

---

## 7. 규모 단계

테스트는 10만, 1차 목표 20만, 이후 100만, 1천만(오너). 생성기와 측정 스크립트는 U만 바꿔 다시 돌릴 수 있어야 하고, 검증 문서는 10만과 100만 두 점을 기록해 증가율을 보인다. 1천만 이후는 그 증가율로 외삽하고, 실제 유저 분포가 나온 뒤 다시 잰다.

저장소 배치(R18)는 단계와 무관하게 처음부터 같다 — 규모가 커진다고 Redis에서 DynamoDB로 옮기는 일은 없다. 1천만 단계에서 다시 볼 것은 PostgreSQL 쪽이다: `interactions`의 turn 카운터(메시지마다 UPDATE)가 쓰기 부하로 보이면 그 카운터만 떼어낸다.

유저 수에 비례해 매일 도는 비용은 `cf_candidates` 쓰기 하나이고, R19가 그것을 **그날 읽혔거나 활동한 유저 수**에 비례하도록 바꾼다(스윕이 그중 TTL이 지났거나 새 대화가 있는 유저만 다시 만든다). 1천만 유저 중 하루에 활동하는 유저가 10 %면 DynamoDB 쓰기 비용도 1/10이다. TTL·스윕 주기는 R36(설정 레지스터), 활성 분포는 합성 스펙 §8-1로 실측한다.

top-K 생성 자체의 확장 규칙 하나: 유저 한 명의 top-K는 아이템 전부(= 유저 수)와의 내적이라 전체 비용은 (그날 갱신하는 유저 수 × 유저 수)에 비례한다. 이를 배치 행렬곱으로 처리하려면 R17의 유저별 후보 제한을 **공통 부분(public row가 있는 소유자, 전원 같음)의 배치 + 유저별 friends-only 후보의 작은 추가 패스**로 나눠야 한다. 그렇지 않으면 배치가 유저별 루프로 퇴화한다. 1천만 단계에서는 `implicit`의 근사 최근접(Faiss 등) 경로가 다음 수단이다.

---

## 8. 열린 항목

2026-09-08에 답이 난 것: 타입 ②는 topic별 묶음(§2-2), 타입 ① topic 상한 3(§2-1), friends tier는 처음부터 후보(§3-1, default private·회귀 가능이 전제), 탐색 탭은 클라이언트가 `/api/svc/agent-discovery`로 직접 호출(§1-3).

제품 판단이 남은 것.

1. ~~인기도 정의~~ R29로 결정(30일 창, 반감기 7일, confidence 가중, 신규 부스트).
2. **"맞음/안 맞음" 표시**: "안 맞음"은 첫 버전에 넣지 않는다(R41). 기획 중인 축은 "나와 비슷해요 / 다른 관점도 살펴봐요" (O5).
3. ~~상호작용 이벤트의 발행 주체~~ 분석으로 정해짐(R15): 시작은 bourbon-api의 방 열기, turn은 이미 있는 `message_created`.
4. **명시 피드백**: 좋아요/숨기기가 제품에 있나. 부정 신호의 유일한 출처다. 2026-09-09 기준 논의 없음 (O6).
5. ~~타입 ② 섹션 크기와 페이지~~ R30으로 결정(preference 순, 5명 × 3섹션, 요청 파라미터).

기술 판단이 남은 것.

6. ~~타입 ③ CF의 첫 구현을 아이템 기반 이웃으로 하나, ALS로 하나~~ `implicit` ALS로 확정, 비교 없음 (R33·R34).
7. ~~friends(R)를 요청 시 조회하나 미러하나~~ 미러로 결정, 판정은 후보 조회 쿼리 안에서 (R17, O10 닫힘).
8. ~~A안의 엔진을 Gorse(서비스형)로 하나 `implicit`(라이브러리형)으로 하나~~ `implicit` (R33).
9. **persona(HEXACO) 도입**: 방향·복호화 키 비공유·코드 자리(`requester_traits`, `persona_similarity`, `w_persona` 0)는 R42(2026-09-10). 경로·동의 범위·가중 규칙·검증은 O20.

---

## 9. 다음 할 일

1. 오너 답 받기 — 2026-09-08에 넷(타입 ② 모양, 상한, friends, 호출 API) 완료. 2026-09-09에 O1·O2·O3·O4·O7·O8·O9·O11·O12·O13·O14·O16·O17·O18·O19 답 완료(R23~R41). 2026-09-10에 persona(HEXACO) 방향 R42, 도입은 O20으로 신설. 남은 것은 O5·O6·O15·O20.
2. 공통 계약 정의: 요청·응답 스키마(세 타입), 후보 소스 인터페이스, 랭커 feature 목록, 결정 로그 스키마. → 초안 `agent_discovery_contract.md` (2026-09-08).
3. §4-2 이벤트 정의서 작성 → 초안 `agent_discovery_events.md` (2026-09-08). 오너 확인 6건 뒤 repo별 요청서로 자름.
4. 합성 데이터 생성기 구현 (§6-2), 10만 유저 생성. → 스펙 `synthetic_population_spec.md` (2026-09-08).
5. 구현(R34): PostgreSQL 인덱스 + 인기도 + content 유사도 + `implicit` ALS 배치·스윕, 설정 레지스터(`agent_discovery_settings.md`)와 같은 이름의 설정 클래스. 단계와 완료 조건은 `implementation_plan.md`(2026-09-10, R43) — 로컬 Docker에서 먼저, 시드 스크립트와 테스트 CLI 포함. 요청서는 `requests/`.
6. §6-3 측정(소스별 ablation), 검증 문서, 설정 초기값 확정.

---

## 10. 이전 문서와의 관계

이전 문서는 전부 `archive/2026-09-08_pre-redesign/`에 있다(오너 2026-09-08). 그 안의 Gorse 실측, 저장소 단가, 파이프라인 단계 정의, 지연 시간 추정 같은 **사실과 계산**은 참고 가치가 있고, 아카이브 README가 무엇이 남는지 표로 안내한다. 그러나 그 문서들이 내린 **결정과 제약은 이 문서의 전제가 아니다.** 결정은 새 `decisions.md`(R01~)만 갖는다.

같은 이유로 이 문서는 이전 문서의 결정 번호나 항목 번호를 인용하지 않는다.
