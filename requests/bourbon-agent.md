# bourbon-agent 요청서 — 공개 note 기반 추천 API를 쓰는 법

> **코드 읽은 기준:** bourbon-agent `origin/deploy/2611` `25cfc9a3`(2026-11-10; 추천 관련 파일은 `main`과 같다). discovery `note-discovery_phase9`(phase 9 — route 이름, 본문 없음, 이유와 설명. 2026-11-11). 설계는 `new-type/note-discovery-design.md` §6(주제 추천)·§7(답할 사람 찾기)이다.
>
> **요약:** agent-discovery-api가 topic 기반에서 **공개 note 기반**으로 바뀐다. discovery의 dev 배포(`deploy/2611`)와 함께 지금 bourbon-agent가 부르는 `POST /recommend/explicit`가 없어진다. 대신 route가 둘 생긴다.
>
> 1. **부탁 (dev 배포에 맞춰 필요):** `recommend_agents` 도구가 부르는 곳을 `/recommend/agents`로 바꿔 주시면 된다(§4).
> 2. **제안 (선택, 결정은 bourbon-agent):** 다른 사람의 공개 note로 질문에 답하는 새 도구를 `/recommend/notes`로 만들 수 있다(§5). 응답에는 note 본문이 없어서, 붙인다면 note-api의 public 읽기를 bourbon-agent가 직접 불러야 한다.
>
> 2026-11-11에 route 이름을 무엇을 추천하는지에 맞춰 바꿨다(`/recommend/subject` → `/recommend/agents`, `/recommend/answerers` → `/recommend/notes`). 옛 이름은 dev에 나간 적이 없어 남겨 두지 않는다.
>
> 이전 요청서(topic 시절, `/recommend/explicit`·카드 meta의 `recommendation_id`)는 `archive/2026-11-10_topic-era-bourbon-agent-request/`로 옮겼다. 그 요청은 철회한다.

## 1. 용어

- **note:** note-api가 대화에서 만든 기록. 제목과 page(본문 조각) 몇 개로 되어 있고, 소유자가 있다.
- **공개 note:** `visibility`가 public인 note. agent-discovery는 **공개 note만** 근거로 쓴다. 비공개로 바꾼 note는 다음 요청부터 응답에 나오지 않는다.
- **tag:** agent-discovery가 note마다 붙이는 주제 라벨(예: key `peaty whisky`, label "피트 위스키"). key는 영어, label은 한국어 하나뿐이다.
- **주제 추천 (`/recommend/agents`):** "이 주제로 이야기할 만한 사람"(그 사람의 Ami)을 찾는다. 지금 `recommend_agents`가 하는 일이 이것이다.
- **답할 사람 찾기 (`/recommend/notes`):** 질문에 답이 되는 다른 사람의 공개 note를 찾는다. note는 참조(id, version, 제목)로만 오고 본문은 오지 않는다.
- **이유(`reason`):** 항목마다 왜 추천했는지. 늘 오는 구조화된 부분과, `explain: true`일 때만 오는 한 줄 글(`text`)이 있다.
- **requester:** 요청의 `user_id`. 결과에서 자동으로 빠지고, "이미 대화한 사람" 판단과 결정 로그의 기준이 된다.

## 2. agent-discovery가 제공하는 것

두 route 모두 내부 API다(edge-auth 없음, `/api/internal/svc/agent-discovery` 아래). 공통으로:

- **응답에 나오는 사람과 내용은 그 요청에서 note-api에 다시 확인한 공개 note에서만 나온다.** 그 사이 비공개로 바꿨거나 지웠거나 탈퇴한 사람은 나오지 않는다.
- **requester 본인은 결과에 나오지 않는다.** `exclude_user_ids`로 더 뺄 수 있다(같은 방에 있는 사람 등).
- **응답 시간:** 목표는 p95 2.5초다. 질문 분석(LLM 한 번 + embedding 한 번)과 note-api 확인에 3초 마감이 걸려 있고, 그 밖의 DB 조회는 마감 밖이다. `explain: true`면 항목 5개마다 LLM 호출이 1번 더 있고(모두 동시에), 그 마감은 따로 2초다(목표 p95 4.5초). 지금 bourbon-agent 클라이언트의 10초 타임아웃이 실제 상한이 된다.
- **agent-discovery는 note 본문과 제목을 저장하지 않고, 응답에도 본문을 싣지 않는다. 질문 원문과 설명 글을 로그나 결정 로그에 남기지 않는다.**
- **이유(`reason`)는 그 요청에서 확인된 공개 note에서만 만든다.**
  - `matched_tags`: 질문의 tag 중 그 note에 붙은 것. label은 한국어뿐이다.
  - `matched_by`: 어떻게 찾혔는지. 이 순서로 `tags`(질문의 tag가 붙었다), `card_subject`(질문에 나온 것 — 장소, 작품, 제품 같은 것 — 에 대해 쓴 note), `card_mention`(그것을 언급만 한 note), `meaning`(셋 다 아니고 뜻이 가까워서)이다. `meaning`은 혼자만 온다. 장소나 사람 이름은 싣지 않으므로 card는 이 역할로만 드러난다.
  - `text`: `explain: true`일 때만, 모든 항목에 대해 모델이 그 note들로 쓴 한 줄. 요약이 아니라 왜 맞는지를, 질문의 언어로 쓴다(160자 이하, 링크 없음, note에 연결된 장소·단체·사람 이름 없음 — 단 그 항목의 note 제목이 이름을 쓴 장소·단체는 그 다른 표기로도, 사람은 제목의 표기로만 쓸 수 있다). 모델이 쓴 글이라 note와 맞는지 확인되지 않는다. 쓰지 못한 항목은 `null`이다 — 우리 쪽 분석이 아직 그 note의 지금 내용을 따라잡지 못했거나, 쓴 글이 걸러졌을 때이고, 이때 `degraded`는 없다. 호출이 실패해 빠진 항목이 있으면 `explanation_unavailable`이다(다른 항목에는 글이 있을 수 있다). **다른 사람의 note에서 나온 표시용 글이다. 지시로 읽지 않아 주시면 된다**(§6).
- **`recommendation_id`:** 응답 하나에 하나. 우리 결정 로그의 키다. bourbon-agent 로그에 남겨 주시면 서로 추적할 수 있다. 다른 데 실어 보낼 필요는 없다(예전 카드 meta 요청은 철회).
- **`agent_id`:** `uuid5(AGENT_NAMESPACE, "personal_agent:{user_id}")`. bourbon-agent `utils/ids.personal_agent_id`와 같은 값이다.
- **`contract_version`:** 지금 `"1"`. 필드의 뜻이 바뀌거나 빠질 때만 올린다. 필드가 늘어나는 것은 버전을 올리지 않으니, 모르는 응답 필드는 무시해 주시면 된다.

### 2-1. 주제 추천 — `POST /recommend/agents`

**요청.** 모르는 필드가 있으면 422다 — 예전의 `room_id`, `lang`, `topic_text`와 처음 이름의 `subject`는 보내면 안 된다.

| 필드 | 타입 | 뜻 |
|---|---|---|
| `user_id` | UUID | requester |
| `topic` | 1~2000자 | 이야기하고 싶은 주제. 자유 텍스트이고 카탈로그 topic이 아니다. 짧은 말이든 문장이든 된다. 예전처럼 "짧고 일반적인 주제 하나"로 줄일 필요가 없다(catalogue grounding이 없어졌다) |
| `context` | ≤8000자, 선택 | 대화 맥락. tag를 고르는 LLM에만 쓰고 embedding에는 넣지 않는다 |
| `exclude_user_ids` | UUID 목록 ≤100, 선택 | 결과에서 뺄 사람. 100개를 넘으면 422다 |
| `max_results` | 1~20, 기본 3 | 최대 몇 명 |
| `explain` | bool, 기본 false | 켜면 사람마다 `reason.text`를 쓴다. LLM 호출이 5명마다 1번(동시에) 늘어난다 |

**응답:**

```json
{
  "contract_version": "1",
  "recommendation_id": "c0b09266-…",
  "agents": [
    {
      "agent_id": "806e57fa-…",
      "owner_user_id": "019ddd04-…",
      "position": 1,
      "already_talked": false,
      "reason": {
        "matched_tags": [{"key": "board game", "label": "보드게임", "note_count": 1}],
        "matched_by": ["tags"],
        "notes": [{"note_id": "01a1b149-…", "title": "적당히 강한 가문으로 시작하는 섭정 플레이", "experienced": true}],
        "text": null
      }
    }
  ],
  "empty": false,
  "empty_reason": null,
  "degraded": []
}
```

- **`agents`:** 관련도 높은 순. 각 사람은 공개 note가 그 요청에서 확인된 사람이다.
- **`reason.notes`:** 그 사람의 note 중 질문과 가장 가까운 것 최대 3개의 id, 제목, 직접 경험 여부. 제목은 note가 쓰인 언어 그대로다.
- **`reason.matched_tags`:** 위 note들에 붙은 tag 중 질문과 겹치는 것과, 그 tag가 붙은 note 수(`note_count`, 위 `notes` 안에서 센다). 비어 있을 수 있다 — 그때 `matched_by`가 왜 뽑혔는지 말한다.
- **`reason.matched_by`:** 위 note들이 찾힌 방법을 모은 것(§2).
- **"왜 이 사람인지"는 `reason`으로 말하면 된다.** tag label, note 제목, `experienced`, card 역할로 충분하고, `explain: true`면 `text`를 그대로 보여 줄 수 있다.
- **`already_talked`:** requester가 이 사람의 Ami와 1:1 방(agent DM)에서 대화한 적이 있다(그 방의 마지막 메시지에서 365일까지). `start_thread`로 연 guest 방은 세지 않는다. 순위가 조금 내려가지만 빠지지는 않는다.
- 이름은 싣지 않는다. 지금처럼 bourbon-api에서 `owner_user_id`로 조회해 주시면 된다.

### 2-2. 답할 사람 찾기 — `POST /recommend/notes`

**요청:**

| 필드 | 타입 | 뜻 |
|---|---|---|
| `user_id` | UUID | requester |
| `question` | 1~2000자 | 질문. "그거", "새로 나온 거" 같은 지칭은 bourbon-agent가 풀어서 보내 주시면 된다 |
| `context` | ≤8000자, 선택 | 질문이 가리키는 것. tag 고르기에만 쓴다 |
| `exclude_user_ids` | UUID 목록 ≤100, 선택 | 이 사람들의 note는 빼고 |
| `max_results` | 1~12, 기본 8 | 최대 몇 개의 note. 처음 이름 `max_notes`는 422다 |
| `explain` | bool, 기본 false | 켜면 note마다 `reason.text`를 쓴다. LLM 호출이 5개마다 1번(동시에) 늘어난다 |

**응답:**

```json
{
  "contract_version": "1",
  "recommendation_id": "…",
  "notes": [
    {
      "note_id": "01a1b149-…",
      "owner_user_id": "019ddd04-…",
      "agent_id": "806e57fa-…",
      "position": 1,
      "version": 1,
      "title": "적당히 강한 가문으로 시작하는 섭정 플레이",
      "experienced": false,
      "language": "ko",
      "conversation_ended_at": "2026-10-12T00:52:11Z",
      "reason": {
        "matched_tags": [{"key": "strategy game", "label": "전략 게임"}],
        "matched_by": ["tags", "card_subject"],
        "text": null
      }
    }
  ],
  "empty": false,
  "empty_reason": null,
  "degraded": []
}
```

- **`notes`는 답을 쓸 note의 참조다.** 관련도 높은 순이고, 한 사람의 note는 최대 3개까지만 들어간다(한 사람의 경험에 답이 갇히지 않게).
- **본문은 없다.** note-api의 public 읽기로 직접 읽어 주시면 된다(§5). 그때 받은 `version`이 응답의 `version`과 다르거나 note가 없으면(404) 그 note는 버린다 — 그 사이 고쳐졌거나 비공개가 됐거나 지워진 것이다.
- **소유자 목록(`owners`)은 없다.** note마다 `owner_user_id`와 `agent_id`가 있으니 필요하면 묶어서 쓰면 된다.
- **`experienced`:** 소유자가 직접 경험한 일인지(note-api의 값). 답에서 "직접 해 본 분"과 "알아본 분"을 구분하는 데 쓸 수 있다.
- **`language`, `conversation_ended_at`:** note의 언어와, note가 나온 대화가 끝난 시각.
- **`version`:** 위의 확인용이다.

### 2-3. 빈 결과와 오류

| 응답 | 뜻 | bourbon-agent가 할 일 |
|---|---|---|
| 200, `empty: true`, `empty_reason: "no_matching_notes"` | 맞는 공개 note가 없다 | "찾지 못했다"고 말한다. 다시 부르지 않는다 |
| 200, `empty: true`, `empty_reason: "note_read_unavailable"`, `degraded`에 `note_read_unavailable` | note-api 확인이 실패하거나 마감을 넘겼다. 확인 못 한 사람은 싣지 않는다 | 같다. "지금은 찾지 못했다" |
| 200, 결과 있음, `degraded`에 `query_analysis_unavailable` | tag 분석이 실패해 embedding만으로 찾았다. 덜 정확할 수 있다 | 결과를 그대로 쓴다. 다시 부르지 않는다 |
| 200, 결과 있음, `degraded`에 `explanation_unavailable` | `explain: true`였지만 일부 또는 모든 항목의 설명을 쓰지 못했다(마감 초과, LLM 오류). 그 항목은 `text`가 `null`이고 구조화된 이유는 있다 | 구조화된 이유로 말한다. 다시 부르지 않는다 |
| 503 `question_unavailable` | 질문을 읽지 못했다(질문 분석의 마감 초과, embedding이나 LLM 쪽 오류) | "지금은 쓸 수 없다". 같은 턴에 다시 부르지 않는다 |
| 503 `database_unavailable` | DB가 응답하지 않았다 | 같다 |
| 422 `validation_error` | 요청 모양이 틀렸다(모르는 필드, 길이·개수 초과 등) | 코드 버그다. 모델에게는 "지금은 쓸 수 없다" |

오류 본문은 `{"request_id", "error_code", "message"}`다. 예전의 422 `grounding_failed`/`grounding_ambiguous`는 **없어졌다.** `degraded`는 앞으로 값이 늘 수 있으니 모르는 값은 무시해 주시면 된다.

## 3. 지금 bourbon-agent가 하는 일 (`deploy/2611` 기준)

- `agents/personal_agent/recommendation/tools.py`의 `recommend_agents(topic, context)`는 모든 모드에서 켜진다. 조건은 `owner_user_id`, `AGENT_DISCOVERY_URL`, `BOURBON_API_URL`, 워커의 공유 HTTP 세션이다(`enable_agent_recommendation_tools`). `RECOMMENDATION_GUIDANCE`가 "추천해 줘, 찾아 줘, 소개해 줘"마다 반드시 부르도록 한다.
- `api_internal_client/agent_discovery.py`의 `AgentDiscoveryClient.recommend`가 `/recommend/explicit`에 `{user_id, room_id, topic_text, context, max_results: 1, lang}`을 보낸다. 도구 인자도 같은 파일의 `TopicText`(≤200자)·`Context`(≤2000자) 타입을 쓴다.
- 첫 사람 하나만 쓰고, bourbon-api에서 이름을 조회해 `{topic, agents: [{id, owner_user_id, owner_name, topics, narrower_topics, owner_notes}]}`를 모델에게 돌려준다.
- 조회 직후 방에 `agent_profiles_v1` 카드를 올리고, `note_recommended()`로 이번 턴의 `start_thread` 초대 목록에 넣는다.
- 422 grounding이면 "짧은 주제로 다시"라는 힌트를, 그 밖의 오류면 "지금은 쓸 수 없다"를 돌려준다.
- `recommendation/thread.py`의 `start_thread`는 소유자 혼자 있는 방에서만 켜진다. 초대할 수 있는 사람은 이번 턴에 `note_recommended()`로 들어온 사람과, **이 Ami가 앞서 보낸 `agent_profiles_v1` 카드에 있는 사람**이다(`_recommended_in_cards`). `THREAD_GUIDANCE`가 먼저 묻게 하므로 보통 다음 턴에 불리고, 그때는 카드가 유일한 근거다.
- `notes/tools.py`의 `search_notes`는 note-api 키워드 검색으로 **소유자 자신의 note**를 찾는다. 다른 사람의 note는 찾지 않는다.

## 4. 부탁: `recommend_agents`를 주제 추천으로 (dev 배포에 맞춰 필요)

아래를 바꿔 주시면 된다. 카드, `start_thread`, 이름 조회, `RECOMMENDATION_GUIDANCE`는 `owner_user_id`만 쓰므로 그대로 두면 된다.

**`api_internal_client/agent_discovery.py`**

- URL을 `/api/internal/svc/agent-discovery/recommend/agents`로 바꿔 주시면 된다.
- 요청 모델: `topic_text` → `topic`. 길이 타입 `TopicText`는 2000자, `Context`는 8000자로 늘려 주시면 된다(도구 인자도 이 타입을 쓴다). `exclude_user_ids: list[UUID]`(≤100)를 더하고, **`room_id`·`lang`은 빼 주시면 된다**(보내면 422).
- 응답 모델: §2-1의 모양으로. `matched_topics` 대신 `reason{matched_tags[{key, label, note_count}], matched_by, notes[{note_id, title, experienced}], text}`, `already_talked`, envelope의 `empty`, `empty_reason`. `explain`은 우선 보내지 않아도 된다(기본 false). 지금처럼 쓰는 필드만 선언하면 된다. `MatchedTopicResponse`는 필요 없어진다.
- `GROUNDING_ERROR_CODES`, `topic_not_grounded`는 지워 주시면 된다.

**`agents/personal_agent/recommendation/tools.py`**

| 지금 | 바꿀 것 |
|---|---|
| `RecommendRequest(topic_text=args.topic, room_id=…, lang=…, max_results=1)` | `topic=args.topic`, `max_results=1`(카드 한 장이니 그대로), `exclude_user_ids` = 방의 다른 사람. `payload.room_members`의 `UserInfo.id`와 사람 소유 Ami의 `AgentInfo.owner_user_id` 중 requester가 아닌 것, 100개까지. 이를 위해 `RecommendationToolContext`에 방 구성원을 넣어 주시면 된다. 소유자 혼자 있는 방에서는 비어 있고, 다른 사람이 있는 방(deputy)에서만 의미가 있다 |
| 결과의 `topics`, `narrower_topics`, `owner_notes`(`RecommendedAgentNote`) | `tags`(= `reason.matched_tags`의 label), `notes`(= `reason.notes`의 title과 `experienced`), `matched_by`, `already_talked`. `explain`을 켜면 `why`(= `reason.text`, 있을 때만) |
| `RecommendAgentsArgs.topic`의 설명과 도구 설명의 "one short, general subject… never a list of qualifiers" (두 곳) | 그 제약을 풀어 주시면 된다. 예: "the subject the person should know about, in a few words or a sentence; details of what the owner wants go in context" |
| 도구 설명의 "using topics, narrower_topics and the owner's own notes, quoting the notes…"와 "If an Ami appears only through narrower_topics…" | 예: "say why each one matches from their tags, the titles of their notes and whether they lived it; if already_talked, mention that your owner has talked with their Ami before" |
| 422 grounding 재시도 분기 | 지워 주시면 된다 |
| `lang`: `Lang`, `_RECOMMEND_LANGS`, `_recommend_lang`, `RecommendationToolContext.lang` | 필요 없어진다 |
| `RecommendError` 그 밖, 예외 | 그대로("unavailable") |
| `empty: true` | 지금처럼 빈 `agents`로 돌려주면 된다(모델은 "찾지 못했다"고 말한다) |
| 로그: `topic=args.topic`(INFO, 여러 곳), 결과 전체(DEBUG, `personal_agent.recommendation.result`) | 결과에는 다른 사람의 note 제목이 들어간다. §6-1을 봐 주시면 된다 |

**함께 바뀌는 것**

- 테스트 `tests/bourbon_agent/agents/personal_agent/test_recommendation_tools.py`(옛 필드를 쓰는 곳이 많다).
- 도구 설명이 들어간 프롬프트 스냅샷 `tests/prompt_snapshots/personal_agent/agent/{personal,deputy_present,deputy_absent}.txt`.
- 문서 `docs/personal_agent/tools-and-memory.md`.

**참고**

- **label은 한국어뿐이다.** 소유자가 영어·일본어를 쓰면 모델이 옮겨 말하게 된다. 지금 `lang`이 하던 일을 우리 쪽에서 채우려면 tag에 다른 언어 label이 필요하다(§7).
- **requester:** 지금처럼 Ami의 소유자를 보내면 된다. 다른 사람이 있는 방에서 남이 "추천해 줘"라고 할 때 그 사람을 requester로 할지는 제품 판단이다 — 바꾸면 결과에서 빠지는 사람과 `already_talked`가 그 사람 기준이 된다(§8).

## 5. 제안: 답할 사람 찾기 도구 (선택)

지금 Ami는 다른 사람의 경험으로 답할 방법이 없다. `search_notes`는 소유자 자신의 note만 본다. `/recommend/notes`를 쓰면 "제주 갈 때 어디 들르면 좋아?" 같은 질문에 다른 사람의 공개 note로 답하고, 그 note를 쓴 사람과 이어 줄 수 있다. 붙일지, 언제 부를지는 bourbon-agent가 정해 주시면 된다. 붙인다면 이런 모양을 제안한다.

- **도구:** 예를 들어 `ask_other_amis(question, context)`. 소유자가 다른 사람의 경험이 도움이 될 질문을 할 때 부른다. 자기 기억이나 자기 note로 답할 질문이면 `search_notes`와 메모리 쪽이다.
- **본문 읽기 (새로 필요한 것):** 응답에는 본문이 없으니, 도구가 note-api에서 직접 읽는다. 지금 `NotesClient`에는 다른 사람의 note를 읽는 public 경로가 없어서 하나 더해 주셔야 한다.
  - 여러 개를 한 번에: `POST /api/internal/svc/note/notes/lookup`, body `{"notes": [{"user_id", "note_id"}, …]}`(1~100개). public인 것만 돌아오고, 빠진 것은 읽을 수 없는 note다.
  - 또는 하나씩: `GET /api/internal/svc/note/users/{owner_user_id}/notes/{note_id}?visibility=public`. 맞지 않으면 404다.
  - **`/api/internal/svc/note/trusted/…`는 쓰지 않아 주시면 된다.** private note도 돌려주는 서비스용 경로이고, note-api는 그 내용이 agent의 답에 들어가면 안 된다고 정해 두었다.
  - 받은 `version`이 우리 응답의 `version`과 다르거나 빠졌으면 그 note는 버린다(§2-2).
- **모델에 돌려줄 것:** note마다 소유자 이름, 제목, note-api에서 읽은 본문(page의 `text`), `experienced`, 그리고 `note_id`나 순번 — 모델이 어느 note를 인용했는지 말할 수 있게. 본문이 길면 note마다 잘라 주시면 된다(우리는 자르지 않는다).
- **답 쓰기 지침 (지켜 주시면 하는 것, 설계 §7-5):**
  - 답에 **실제로 쓴 note의 소유자만** "이 분의 경험"으로 소개한다. 쓰지 않은 note의 소유자를 근거처럼 말하지 않는다.
  - 근거 밖 일반론을 섞지 않는다. 섞는다면 "다른 분들의 경험"과 "Ami의 생각"을 나눠서 말한다. 실험에서 모호한 질문과 두 note를 합치는 질문의 답 13~19%에 일반론이 섞였다.
  - 답을 쓸 근거가 없으면 note의 소유자들로 "이 분들이 비슷한 이야기를 남겼다"고만 하고, 내용을 지어내지 않는다.
- **이어서 대화방 열기:** 지금의 `start_thread`는 다음 턴에 불리고, 그때 초대할 수 있는 사람은 **이 Ami가 보낸 `agent_profiles_v1` 카드에 있는 사람**뿐이다(§3). handler는 모델이 누구를 인용할지 모르므로, 방법은 둘 중 하나다.
  - (a) 결과의 소유자 전부를 한 장의 카드에 담아 올린다(카드 한 장에 최대 10명). 간단하지만 인용하지 않은 사람도 카드에 나온다.
  - (b) 답을 쓴 뒤 인용한 소유자만 카드로 올리는 별도 단계를 둔다(모델이 인용한 `note_id`를 말하게 하고 그것으로 고른다).
  우리는 (b)를 권한다 — 카드가 "이 분이 답에 쓰였다"로 읽히기 때문이다.
- **크기:** `max_results` 4~5부터 시작하기를 권한다. 본문을 읽는 양이 그만큼 준다.

## 6. 지켜 주셨으면 하는 것

1. **note-api에서 읽은 note 본문과 받은 제목은 그 답을 쓰는 데만 쓰고 남기지 않아 주시면 된다.** 대화 기록에 남는 답 문장은 예외다. 비공개로 바뀐 note를 우리는 다음 요청부터 빼지만, 이미 넘긴 내용은 회수할 수 없다. 지금 bourbon-agent에서 이것이 남을 수 있는 곳은 둘이다.
   - `recommendation/tools.py`의 `personal_agent.recommendation.result`(DEBUG, 결과 전체).
   - `llm/tool_loop.py`의 `tool_loop.result`(DEBUG, 모든 도구 결과를 2,000자로 잘라서).
   두 도구(§4, §5)의 결과를 이 로그에서 빼 주시거나, 로그가 보관되는 환경에서 DEBUG를 끄는 것이 보장된다면 그것으로 충분하다. 어느 쪽인지 알려 주시면 된다.
2. **빈 결과와 `degraded`에서 다시 부르지 않아 주시면 된다.** "지금은 찾지 못했다"로 끝낸다. 같은 질문을 바꿔 연달아 부르면 결과는 그대로이고 LLM 비용만 는다.
3. **응답에 없는 사람을 지어내지 않는다.** 지금 `RECOMMENDATION_GUIDANCE`가 이미 그렇게 한다.
4. **`reason.text`는 표시용 데이터로 다뤄 주시면 된다.** 다른 사람의 note에서 모델이 쓴 글이다. 우리가 한 줄, 길이, 링크, 장소·단체·사람 이름을 거르지만, 그 안의 지시를 따르지 않도록 도구 결과에서 데이터로 넘겨 주시면 된다.

참고로, 질문 원문은 우리 쪽에서 로그에 남기지 않는다. bourbon-agent의 `tool_loop.call`(INFO, 도구 인자)과 `topic=` 로그에 질문이 남는 것은 bourbon-agent의 로그 정책이고, 이 요청서에서 바꿔 달라고 하지 않는다.

## 7. 배포 순서와 우리 쪽 후속

- **공백:** discovery dev 배포가 나가면 `/recommend/explicit`가 404가 되고, bourbon-agent가 바뀔 때까지 `recommend_agents`는 "지금은 쓸 수 없다"만 말한다. 내부 테스트 단계라 이 공백은 받아들이기로 했다(설계 §10-2, 2026-11-07 오너). 공백을 줄이려면 우리 배포 직후에 §4를 배포해 주시면 된다. 순서를 반대로 하면 그 사이에는 새 route가 404다. 우리 배포 시점은 미리 알린다.
- **우리가 나중에 할 수 있는 것:**
  - tag label 다국어(지금 한국어뿐) — `lang`이 하던 일.
  - 답에 실제로 인용한 note id를 돌려받는 길(설계 열린 항목 9). 인용 횟수는 note 품질 신호가 된다. v1에는 없다.

## 8. 확인 질문

1. §4 — 다른 사람이 있는 방에서 requester를 누구로 할지. 지금처럼 소유자로 둘지.
2. §4 — `exclude_user_ids`에 방의 다른 사람을 넣는 데 이견이 없는지.
3. §5 — 답할 사람 찾기 도구를 붙일지, 붙인다면 언제쯤이고 방 열기는 (a)·(b) 중 어느 쪽인지. note-api public 읽기 client를 여러 개 조회와 단건 중 어느 것으로 할지.
4. §6-1 — 로그에서 빼는 것과 DEBUG를 끄는 것 중 어느 쪽인지.
5. §7 — §4를 배포할 수 있는 시점.
