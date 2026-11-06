# bourbon-note-api — discovery가 알아야 할 것

> **코드 읽은 기준(2026-11-06):** `main` `a367d0e`(#21까지)와, 아직 머지되지 않은 최신 브랜치 `feat/note-audience-policy` `fe5a3af`. 이 브랜치는 `main` 위에 `feat/opensearch`(#18–#31)와 audience policy 커밋을 얹은 것이다. 따로 적지 않으면 이 브랜치 기준이다.
>
> **이 문서의 역할:** note-api는 개발 중이고 discovery는 그 note를 계속 읽는다. 그래서 note-api 코드에서 discovery에 영향이 있는 사실만 여기 모아 둔다. 우리 쪽 설계와 결정은 [`new-type/ami-note-direction-notes.md`](../new-type/ami-note-direction-notes.md) §13에 있다. 이 문서는 "note-api가 지금 어떻게 되어 있나"만 다룬다.
>
> **관리 규칙:**
> - note-api 코드를 다시 읽으면 위의 기준 commit과 맨 아래 갱신 기록을 고친다.
> - 사실마다 note-api의 파일 경로를 적어 둔다. note-api 쪽에서 "그 사이 바뀌었다"를 바로 말할 수 있게 하기 위해서다.
> - note-api README에 적혀 있지만 아직 코드가 없는 것은 **"약속(코드 없음)"**이라고 따로 표시한다.

## 0. 한눈에

1. **읽는 경로가 바뀐다.** internal route가 `/api/internal/svc/note/trusted/...`와 `/delegated/...` 둘로 나뉘었다. 다시 맞추기와 backfill에 쓸 것은 `trusted/`다. 옛 경로(`/api/internal/svc/note/users/...`)는 이 브랜치에서 없어진다(§2).
2. **옛 경로를 부르면 "note 없음"과 같은 404가 온다.** `error_code`도 `not_found`로 같다. 경로를 잘못 맞추면 모든 note를 삭제로 처리하게 된다(§2-2).
3. **trusted로 읽은 것은 agent의 답에 들어가면 안 된다는 것이 note-api의 원칙이다.** 그런데 discovery는 답에 쓰기 직전의 재확인, shout 재순위, "왜 이 사람인지" 설명에 note를 쓴다. note-api와 합의가 필요하다(§3, §11).
4. **발행되는 이벤트는 `bourbon.note_created` 하나뿐이다.** 수정·공개 범위 변경·삭제 이벤트는 모양만 합의됐고 발행되지 않는다. 그런 기능 자체가 아직 없다(§6).
5. **note는 만들어진 뒤 바뀌지 않는다.** `version`은 항상 1이고 `visibility`는 항상 `public`이다. discovery의 version 비교와 private flag는 지금 쓰일 일이 없다(§5).
6. **trusted 읽기는 탈퇴한 유저의 note도 돌려준다.** 탈퇴 직후 늦게 저장된 note에 대해 `note_created`가 올 수 있다. discovery가 쓰기 전마다 탈퇴 여부를 확인해야 한다(§7).
7. **drip 사본이 없어졌다.** note-api는 자체 OpenSearch index(키워드 검색, embedding 없음)를 갖는다. discovery의 semantic·tag·entity 사본을 대신하지 않는다(§8).
8. **이 브랜치의 머지는 prod OpenSearch 결정을 기다린다.** 옛 형식 note는 배포 전에 지운다. discovery의 경로 변경과 backfill 시점이 둘 다 여기에 걸려 있다(§9).

## 1. 브랜치 상태

| 내용 | `main`(`a367d0e`) | `feat/note-audience-policy`(`fe5a3af`) |
|---|---|---|
| 저장 형식: 제목·본문 등은 `content`로 암호화, 메타데이터는 평문(#10, #14) | 있음 | 있음 |
| `note_created` 발행, 탈퇴 처리(#8, #9) | 있음 | 있음 |
| Draft와 `missing`(#17, #21), 카드 평가(#13) | 있음 | 있음 |
| internal route 경로 | `/api/internal/svc/note/users/...`, `/notes/lookup` | `/trusted/...`, `/delegated/...` |
| 검색 | drip으로 하는 `POST /notes/search` | OpenSearch, `POST /delegated/notes/search` |
| note id | UUIDv4 | UUIDv7(`b4242ac`) |
| `language` 필드 | 없음 | 필수 |

**배포 상태는 이 문서가 다루지 않는다.** 어느 commit이 dev에 떠 있는지는 note-api 쪽에 확인한다.

## 2. discovery가 부르는 route

### 2-1. 경로

internal 표면은 두 prefix로 나뉜다(`api/surfaces.py:39-42`). 어느 쪽을 쓸지는 header나 flag가 아니라 **경로**로 정해진다.

- **`trusted/`:** 서비스가 자기 권한으로 읽는다. 저장된 그대로 돌려주고 private note도 포함한다. README와 router docstring(`api/routers/internal/trusted/notes/router.py:1-4`)은 "여기서 읽은 것은 agent의 답에 들어가면 안 된다"고 적는다. discovery 설계와 부딪히는 점은 §3에 있다.
- **`delegated/`:** agent가 대화 안에서 답할 때 쓴다. 대화의 policy로 거른다(§3).

discovery가 쓸 세 route는 모두 `trusted/`에 있다. 요청에 header나 신원 정보는 필요 없다(`api/routers/internal/trusted/notes/router.py:28-69`).

| 용도 | 이 브랜치 | `main`과 그 전 |
|---|---|---|
| 단건 조회(이벤트를 받은 뒤) | `GET /api/internal/svc/note/trusted/users/{user_id}/notes/{note_id}` | `/trusted` 없이 같은 경로 |
| 여러 개 조회(주기적 다시 맞추기) | `POST /api/internal/svc/note/trusted/notes/lookup`, body `{"notes": [{"user_id", "note_id"}, ...]}`, 1–100개 | `/trusted` 없이 같은 경로 |
| 목록 조회(backfill) | `GET /api/internal/svc/note/trusted/users/{user_id}/notes?limit=&after=`, `limit` 1–100(기본 20) | `/trusted` 없이 같은 경로 |

**응답:**
- **단건 조회:** `StoredNote`. 없으면 404이고, private note는 404가 아니다(docstring: "a private Note is not a deleted one").
- **여러 개 조회:** `{notes: [StoredNote]}`. 요청 순서대로 오고, 중복은 한 번만 온다. 없는 것은 응답에서 빠진다.
- **목록 조회:** `{notes: [StoredNote], next_after}`. bundle이 최근인 것부터 온다. `next_after`와 `after`는 note id가 아니라 **bundle id**다(`trusted/notes/structs.py:10-12`). 그대로 넘기기만 하는 cursor로 다루고, 여기에 note id를 넣지 않는다.

**handler 로직은 `main`과 같다.** 경로만 옮겨졌다(`c961846`).

**모든 유저의 목록은 여전히 없다.** backfill할 유저 목록은 discovery가 따로 구해야 한다(메모 §13-4).

### 2-2. 404를 해석할 때 주의

- 존재하지 않는 **경로**로 요청하면 framework가 404를 낸다. note-api는 이 404에도 note가 없을 때와 같은 `error_code: "not_found"`를 붙인다(`api/main.py:67`, `api/structs/errors.py:49-53`).
- 둘을 구분할 수 있는 것은 `message`뿐이다. 경로가 없으면 "Not Found", note가 없으면 "note not found"다. 이 문구는 계약이 아니다.
- 그래서 discovery는 이렇게 판단한다.
  - **삭제의 근거는 여러 개 조회뿐이다.** 응답이 200이고 그 쌍이 빠져 있을 때만 tombstone을 남긴다(`trusted/notes/router.py:61-69`). 경로가 틀리면 요청 전체가 404로 실패하므로, 이 경우와 섞이지 않는다.
  - **단건 조회의 404는 "여러 개 조회로 다시 확인"으로 다룬다.** 바로 tombstone을 남기지 않는다.
  - 경로 prefix는 client 코드의 상수로 두고, 실제 note 하나로 경로를 확인하는 계약 테스트를 둔다. note-api 브랜치가 머지될 때 함께 바꾼다.

### 2-3. 500을 삭제로 보지 않는다

- note 하나를 읽을 수 없으면(옛 형식, 복호화 실패) 건너뛰지 않고 500을 낸다. `error_code`는 `internal_server_error`다(`api/main.py:160-164`).
  - 목록 조회와 여러 개 조회는 `skip_unreadable=False`로 읽는다(`bourbon_note/notes/originals.py:498-505`).
  - 단건 조회는 그 옵션 없이 바로 decode한다(`originals.py:297-305`).
- 그래서 note 하나만 문제여도 backfill 페이지 하나, 또는 **최대 100개짜리 여러 개 조회 전체**가 실패한다.
- 5xx는 재시도 대상이고, tombstone 근거가 아니다. 여러 개 조회가 계속 500이면 묶음을 반으로 나눠 다시 읽어서 문제 note를 골라낸다.

## 3. audience policy와 discovery의 사용

### 3-1. `delegated/`의 policy

- **요청:** `speaker: {agent_id, user_id}`와 `participants`(1–100개, `{type: "user", id}` 또는 `{type: "agent", id, user_id}`)가 필수다. 모르는 필드는 거절한다(`api/routers/internal/delegated/conversation.py:49-73`).
- **private이 보이는 조건:** 그 유저의 agent가 답하고, 대화에 있는 **사람**이 그 유저 한 명뿐일 때다. 다른 agent는 함께 있어도 된다(`bourbon_note/notes/audience.py:44-49`).
- **그 밖의 경우:** public note만 `kind: "shared"`로 온다(`bourbon_note/notes/search.py:61-94`).
  - 빠지는 필드: room id, 메시지 id, `element_ids`, `questions`, `visibility`, 첨부 id.
  - 남는 필드: 제목, 본문, `experienced`, `language`, `public_element_ids`, 네 개의 시각, `version`.
- **보이지 않는 note:** 숨겨진 private note와 탈퇴한 유저의 note는 없는 것으로 다룬다. get은 404이고 list에서는 빠진다(`bourbon_note/notes/delegated.py:35,51`).
- **route:** `POST /delegated/notes/search`, `/list`, `/get`.

### 3-2. discovery의 사용과 부딪히는 점(합의 필요)

- **다시 맞추기와 backfill:** 사본을 만드는 일이라 `trusted/`가 맞다.
- **부딪히는 곳:** 메모 §13-4의 2는 답에 닿는 읽기에도 GET을 쓴다.
  - 답에 쓰기 직전의 재확인(§5-5)
  - shout B1 재순위의 입력
  - "왜 이 사람인지" 설명에 쓰는 note 제목

  재순위 입력은 discovery 내부의 LLM prompt이고, agent의 답 자체는 아니다. 하지만 그 결과와 설명은 답에 닿고, 재확인한 note는 답에 인용된다. note-api 원칙으로는 `trusted/`가 아니라 `delegated/`를 써야 하는 자리다.
- **선택지:**
  - (가) discovery가 trusted로 읽고 public만 쓰도록 스스로 거르는 것을 note-api가 인정한다.
  - (나) 답에 닿는 읽기는 `delegated/`로 옮긴다. discovery가 실제 대화(speaker, participants)를 알아야 한다.
  - (다) note-api에 discovery용 route를 따로 요청한다. 예: public만 돌려주고 탈퇴 유저를 거르는 여러 개 조회.
- 결정은 note-api와 오너가 한다(§11).

## 4. Note 모델

`StoredNote`(`bourbon_note/notes/originals.py:140-183`):

| 필드 | 형태 | discovery에서 |
|---|---|---|
| `id` | UUID. 이 브랜치에서는 v7, `main`은 v4 | 키. id 순서에 의미를 두지 않는다 |
| `room_id` | UUID | 쓰지 않음 |
| `title` | str | hash 입력, 검색 입력 |
| `pages` | `[{text, attachment_ids}]` | hash 입력은 **`text`만** 쓴다(§10 결정 필요) |
| `experienced` | bool | hash 입력, 직접 경험 여부 |
| `visibility` | `"public"` 또는 `"private"` | private flag |
| `material_ids`, `reference_ids` | list[UUID] | 쓰지 않음 |
| `element_ids` | list[UUID]. 개인 카드 포함 | 쓰지 않는다. 다른 유저에게 영향을 주는 계산에는 쓰면 안 된다 |
| `public_element_ids` | list[UUID] | entity 연결에 쓸 수 있다 |
| `questions` | `[{id, text}]` | 쓰지 않음 |
| `language` | ISO 639-1 두 글자. **이 브랜치에서 새로 생겼고 필수** | embedding과 검색에서 언어 처리 |
| `other_room_messages` | `[{room_id, material_ids, reference_ids}]`, 기본 `[]` | 쓰지 않음 |
| `conversation_started_at`, `conversation_ended_at` | UTC | 대화한 시점. 최근성 계산에 `created_at`보다 맞다 |
| `created_at` | UTC | 저장한 시각. backfill로 저장된 note는 몇 주 늦을 수 있다 |
| `updated_at` | UTC | 처음에는 `created_at`과 같다. 순서는 `version`으로 정한다 |
| `version` | 양의 정수, 처음은 1 | version 비교 |

시각은 모두 마이크로초까지 고정 폭 UTC다(`2026-11-04T01:02:03.000000+00:00`).

**저장(참고):**
- 제목, 본문, `questions`, `other_room_messages`, 그리고 앞으로 추가될 필드는 `content` 하나로 암호화된다. 이 값은 item key에 묶인다.
- 나머지는 평문 attribute다(`PLAINTEXT_ATTRIBUTES`, `originals.py:60-75`).
- 번역은 `NOTE_TR#<note>`에 따로 저장된다. `version`도 GET 응답도 바꾸지 않으므로 discovery에는 영향이 없다.

## 5. Note가 만들어지는 과정

- **쓰는 곳은 writer 하나다.** `bourbon_note/writer/bundle.py`의 `_write`(:715-776)가 `save_note`를 부른다. 다른 쓰기 경로는 없다.
  - trusted router의 docstring도 "Notes are read only"라고 적는다.
  - `version`은 항상 1(`FIRST_VERSION`)이다.
  - `visibility`는 항상 `PUBLIC`이다(`bundle.py:760`).
- **Draft:** 아직 note가 될 만큼 모이지 않은 대화 묶음이다(`bourbon_note/drafts/contract.py:32-44`).
  - 열린 Draft는 `started_at`(주인이 그 묶음에서 처음 보낸 메시지 시각)부터 14일(`WRITER_DRAFT_DAYS`)이 지나면 TTL로 사라진다(`contract.py:51-52`). 승격 중인 Draft에는 TTL이 없다(`drafts/store.py:17`).
  - 다른 Draft와 합쳐지거나 note로 승격될 수 있다.
  - **승격되면 새 note id(UUIDv7)로 note가 하나 저장되고, Draft는 지워진다.** Draft id가 note id가 되는 일은 없다. 승격하다가 중복(REPEAT)이나 빈 본문으로 끝나면 note가 생기지 않는다.
  - Draft는 이벤트를 내지 않는다. discovery가 받는 것은 승격으로 생긴 note의 `note_created`뿐이다.
  - Draft는 `trusted/users/{id}/drafts`로 읽을 수 있다. 주인 본인의 대화에서 쓰는 용도라 discovery는 읽지 않는다.
- **카드 평가(#13):** 공유 카드(card ledger)에 붙는 평가 문장이다. note에는 실리지 않는다.

## 6. 이벤트

계약의 원본은 note-api README "Events this service publishes"와 `bourbon_note/events.py`다.

| 이벤트 | payload | 언제 | 상태 |
|---|---|---|---|
| `bourbon.note_created` | `{user_id, note_id, version}` | writer가 note를 저장하고 index에 넣은 뒤 | **발행됨** |
| `bourbon.note_updated` | `{user_id, note_id, version}` | 내용이 바뀜 | 합의만, 발행 안 됨 |
| `bourbon.note_visibility_changed` | `{user_id, note_id, version}` | 공개 범위가 바뀜 | 합의만, 발행 안 됨 |
| `bourbon.note_deleted` | `{user_id, note_id}` | 유저가 note 하나를 지움(탈퇴 때는 없음) | 합의만, 발행 안 됨 |

- **payload는 엄격하다.** `extra="forbid"`이고, id는 UUID, `version`은 양의 정수다. discovery의 mirror는 늘 하던 대로 느슨하게 둔다.
- **발행 순서:** 저장 → index에 넣기 → 번역 예약 → `note_created` → bundle 끝 표시(`bundle.py:772-774`).
  - 이미 저장된 note를 다시 처리하는 경로(`_written`, :545-547)에서도 다시 발행한다.
  - 발행이 실패하면 bundle 실행이 실패하고, 재시도 때 다시 발행한다. **그래서 보통은 최소 한 번 전달되고, 중복될 수 있다.**
  - index에 넣기가 이벤트보다 앞이다. 그래서 OpenSearch가 멈추면 `note_created`도 bundle이 성공할 때까지 늦어진다. bundle 재시도는 횟수 제한 없이 대기를 늘려 가며 계속된다. 다만 다음 시도를 예약하지 못하면 Sentry에 알리기만 하고 멈춘다(`bundle.py:28-32`). 이벤트가 끝내 나가지 않는 경우가 이것이다.
- **끝내 오지 않은 `note_created`는 discovery가 알 수 없다.**
  - note-api README는 "consumer의 주기적 re-sync가 메운다"고 적는다. 하지만 discovery의 주기적 다시 맞추기는 이미 가진 key만 다시 읽는다.
  - 받지 못한 생성은 유저별 목록 조회로만 찾을 수 있다(메모 §13-4의 1).
  - deferq는 재전달이 없다. 그래서 discovery listener는 실패할 수 있는 일보다 먼저 `pending`을 기록해야 한다(메모 §13-2).
- **약속(코드 없음):** README에는 이렇게 적혀 있다. "`version`은 내용이든 공개 범위든 바뀔 때마다 정확히 1 오르고, 조건부 쓰기로 지킨다. 아무것도 바뀌지 않으면 발행하지 않는다." 이를 구현할 수정 경로는 아직 없다.
- **broker 연결:** `bourbon_note/broker.py`가 `DEFERQ_AMQP_URL`로 프로세스당 연결 하나를 연다. 지금 발행하는 쪽은 worker뿐이다.

## 7. 탈퇴

- **`bourbon.user_deactivated`를 받으면**(`bourbon_note/accounts/erase.py`):
  1. `DEACTIVATED#<id>` 표시를 남긴다. 7일 TTL이다.
  2. 그 유저의 note를 OpenSearch에서 지운다.
  3. `USER#<id>` partition을 지운다. note, pointer, link, 번역, room 상태, Draft, 개인 카드가 다 들어 있다.
  4. Draft index에서 그 유저의 것을 지운다.
- **두 번째 삭제:** split·bundle·translate task의 timeout 중 가장 긴 시간이 지나면 한 번 더 지운다. 실패하면 대기를 두 배로 늘려 최대 5회 다시 한다.
- **수동 실행:** `DELETE /trusted/users/{id}`가 같은 삭제를 한다.
- **`note_deleted`는 내지 않는다.**
- **discovery에 중요한 빈틈:**
  - 탈퇴 시점에 이미 돌던 bundle은 삭제 뒤에 note를 저장하고 `note_created`를 낼 수 있다.
  - trusted 읽기는 탈퇴 표시를 보지 않는다(`trusted/notes/router.py:42-47`). 탈퇴 유저를 거르는 것은 delegated 읽기와 검색뿐이다(`notes/delegated.py:35,51`, `notes/search.py:236-239`). 그래서 두 번째 삭제 전까지는 그 note가 200으로 읽힌다.
  - 따라서 discovery는 note를 맞추는 handler의 **모든 쓰기**(upsert, tombstone, pending)에서 탈퇴 유저 확인(R68의 `departed_users`)을 거쳐야 한다. 이벤트를 받을 때뿐 아니라 backfill과 주기적 다시 맞추기도 같다.

## 8. 검색과 OpenSearch

- **drip 사본은 없어졌다**(`b4242ac`). note-api는 drip을 writer의 웹 검색에만 쓴다.
- **index:** `{prefix}-{kind}-v{N}`이 alias `{prefix}-{kind}` 뒤에 있다. prefix 기본값은 `bourbon-note`이고, kind는 셋이다.
  - `notes`: private과 public 모두 들어간다. `visibility`는 filter 필드다. room·메시지·첨부·`questions`·개인 `element_ids`는 넣지 않는다.
  - `drafts`: 열린 Draft만.
  - `cards`: 공유 카드만.
- **검색 방식:** BM25 키워드 검색이다. embedding이나 vector는 없다. 분석기는 ko(nori), en, ja(kuromoji)와 CJK bigram을 쓴다.
- **번역:** note를 ko·en·ja 중 자기 언어가 아닌 것 모두로 번역해 index에 함께 넣는다. ko·en·ja가 아닌 언어의 note는 셋 모두로 번역된다(`notes/translations.py:57-58`). `TRANSLATE_ENABLED`는 기본값이 꺼짐이고, dev에서만 켜져 있다.
- **동기화:** writer가 저장 직후 동기로 넣는다. 번역은 별도 task가 나중에 넣는다. 다시 만들 때는 `cli index backfill`을 쓴다. stream은 없다.
- **검색 결과 확인:** 검색 결과는 DynamoDB에서 다시 읽어 확인한다. note가 아직 있는지, 공개 범위와 기간이 맞는지, 작성자가 탈퇴하지 않았는지를 본다.
- **여러 유저에 걸친 검색:** `POST /delegated/notes/search`의 `others_public`은 대화에 닿지 않는 모든 유저의 public note를 키워드로 찾는다. `limit`은 최대 20이고, 대화(speaker, participants)가 필수다.
- **discovery와의 관계(메모 §13-6 "drip 사본 vs discovery 사본"):**
  - 겹치지 않는다. note-api index는 대화 안의 키워드 검색용이다.
  - discovery 사본은 semantic 검색, tag, entity, 사람 단위 집계용이다.
  - delegated route는 실제 대화를 전제로 하므로, discovery가 speaker를 지어내서 부르면 안 된다.
  - discovery가 키워드 신호를 따로 원하면 note-api에 **trusted 쪽의 여러 유저 public 검색** route를 요청해야 한다. 지금은 필요하지 않다.

## 9. 설정과 배포

- **discovery 쪽 설정:** `NOTE_API_BASE_URL=http://bourbon-note-api`(메모 §13-4). 경로 prefix(`/api/internal/svc/note/trusted`)는 client 코드 상수로 두고, note-api 브랜치가 머지될 때 함께 바꾼다(§2-2).
- **머지 조건:** prod overlay에 "prod collection은 아직 정해지지 않았고, index 작업이 main에 들어가기 전에 정해야 한다"고 적혀 있다(`k8s/overlays/prod/configmap-patch.yaml:14`, `worker-configmap-patch.yaml:12`). 그래서 `trusted/` 경로 이동이 `main`에 들어가는 시점도 이 결정을 기다린다.
- **옛 형식 note:** 형식이 바뀔 때마다 옛 note는 읽히지 않는다(#10 `doc` 형식, `language`가 없는 형식). note-api는 "그런 note가 든 테이블은 배포 전에 비운다"고 적어 두었다. 이렇게 사라지는 note에는 이벤트가 없다.
  - **discovery backfill은 note-api가 마지막으로 형식을 바꾼 배포 뒤에 한다.**
- **시작할 때 확인:** note-api API와 worker는 index alias가 없으면 뜨지 않는다.

## 10. discovery 쪽에 남는 일

- [ ] note client 경로를 `trusted/` 기준의 상수로 두고, 실제 note 하나로 경로를 확인하는 계약 테스트를 둔다(§2-2).
- [ ] tombstone은 여러 개 조회가 200을 주고 그 쌍을 뺐을 때만 남긴다. 단건 조회의 404는 여러 개 조회로 다시 확인한다. 5xx는 재시도하고, 계속되면 묶음을 나눠 문제 note를 찾는다(§2-2, §2-3).
- [ ] 탈퇴 유저 확인을 handler의 모든 쓰기에 건다. 이벤트, backfill, 주기적 다시 맞추기 모두다(§7).
- [ ] 이벤트를 받으면 실패할 수 있는 일보다 먼저 `pending`을 기록한다. 받지 못한 생성은 유저별 목록 조회로만 찾을 수 있다(§6).
- [ ] **결정 필요:** hash 입력을 `title`, 각 page의 `text`, `experienced`로 한정할지(첨부 id 변화는 제외). 메모 §13-4는 "제목, 본문, `experienced`"라고만 적었다.
- [ ] **결정 필요:** `language`를 저장해 embedding과 검색에 쓸지. 최근성 계산에 `conversation_ended_at`을 쓸지.
- [ ] 메모 §13-3의 경로·drip·이벤트 부분은 지난 사실이다. 이 문서가 대신한다.

## 11. note-api와 합의하거나 확인할 것

1. **답에 닿는 읽기를 어느 route로 할지(§3-2).** (가) trusted로 읽고 discovery가 public만 쓰도록 거른다, (나) delegated로 옮긴다, (다) discovery용 route를 새로 만든다. 오너 결정과 note-api 합의가 필요하다.
2. `feat/note-audience-policy`의 머지 시점과 dev 배포 시점. prod OpenSearch collection 결정이 먼저다(§9). discovery client 경로를 바꿀 시점이 여기에 걸려 있다.
3. 형식 변경으로 dev 테이블을 비우는 일이 끝났는지. discovery backfill 시점이 여기에 걸려 있다.
4. 수정·공개 범위 변경·삭제 기능의 일정. 기능이 생기면 §6의 약속(조건부 쓰기로 `version` 올리기)이 코드가 되는지 확인한다.

## 갱신 기록

| 날짜 | 기준 | 내용 |
|---|---|---|
| 2026-11-06 | `main` `a367d0e`, `feat/note-audience-policy` `fe5a3af` | 처음 작성 |
