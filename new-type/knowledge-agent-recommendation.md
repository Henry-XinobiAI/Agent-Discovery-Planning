# 사람에게 물어야 하는 질문의 agent 추천 — 경험 projection

> 상태: **기획 초안, 결정 아님**
> 범위: 새 추천 타입(타입 ④ 후보)과 그것을 위한 새 서비스(가칭 `bourbon-experience-api`), 그리고 `bourbon-agent-discovery-api` · `bourbon-agent` · `bourbon-api` · `bourbon-memory-api-v2` · `bourbon-topic-api`와의 경계
> 비범위: 타입 ①·②·③의 계약 변경, 선택된 agent의 실제 답변과 종합(경계만 정한다)
> **기획 단계에서 빼 둔 것**(오너, 2026-09-26): 공개 범위·동의(`consultable`)·방 범위. 설계와 실험에는 조건을 걸지 않고, 실 서비스화할 때 다룬다. 나중에 얹을 자리만 남긴다(§10).
> 선행 문서: `personal-knowledge-agent-recommendation.md`(2026-09-18 ~ 09-21). 그 문서는 memory-api personal build의 파생본을 topic에 조인해 근거로 썼다. 이 문서는 **추천만을 위한 projection을 새 서비스로 따로 두고**, 메시지 단위로 말한 사람에게 귀속한다. 무엇이 달라졌는지는 §14에 모았다.
> 이 문서의 "현재"는 각 repo의 HEAD 기준이다 — bourbon-agent `61f84aea`(origin/main, 09-25), bourbon-api `078eeeb`(origin/main, 09-21), memory-api-v2 `8c6a937`(origin/main, 09-19), topic-api `ffc62bf`(09-22), agent-discovery-api `bac5de9`(09-24)

---

## 0. 요약

사용자의 personal agent가 **LLM으로는 답할 수 없는 질문** — 누군가의 경험, 취향, 해 보며 익힌 요령, 그 사람만 아는 사정이 필요한 질문 — 을 받았을 때, 그것을 가진 다른 사용자의 personal agent를 추천해 그 agent와 이야기해 보게 한다. 일반 사실은 추천하지 않는다.

설계는 여섯 문장이다.

1. **추천할 근거는 "사람만 가진 것"뿐이다.** 질문 쪽에서는 need마다 사람이 필요한지를 먼저 판정하고, 근거 쪽에서는 사실 진술을 담지 않는다(§1).
2. **근거는 새 서비스의 경험 projection이다.** memory-api의 personal build는 owner 자신의 agent가 기억해 답하기 위한 그래프라 이 목적과 어긋난다. 그것은 그대로 두고, 추천만을 위한 기록을 따로 만든다(§3-2, §5).
3. **기록은 메시지 단위로, 그 메시지를 보낸 사람에게 귀속한다.** 그래서 "누가 겪었나"가 정의상 맞고(authorship), 기록의 시각이 곧 겪은 것을 말한 시각이며(recency), 개체는 사람 사이에 공유되는 레지스트리에 붙는다(새 병처럼 Wikidata에 없는 것도)(§5).
4. **원문은 담지 않는다.** 조회 → 추출 → 폐기. 담는 것은 기록, 요약문, 원 메시지를 가리키는 핸들이다(§5-2).
5. **키는 후보를 넓히고, 기록이 고른다.** 키는 topic과 개체 둘이고 어느 쪽도 후보를 거르지 않는다 — 합집합으로 모은 뒤 기록의 종류·시각·요약문 매치로 순위를 정한다(§2, §6).
6. **핸들이 응답 가능성을 올린다.** 추천마다 근거 기록의 핸들을 대상 agent에게만 넘겨, 실행할 때 그 기록에서 답을 시작하게 한다. 추천의 근거와 실행의 근거가 가까워진다(§6 T6, §7-3).

추천 시점의 런타임 의존성은 e3llm(need 추출 1회), topic-api 검색(타입 ①과 같음), 새 서비스 조회 1회(그 안에서 memory-api 공개 지식 resolve)다. 새 서비스가 답하지 않으면 topic 관심 근거만으로 추천하고 `degraded`에 남긴다.

추천은 **답할 근거를 가졌을 가능성**의 순위다. 확정은 선택된 agent가 실행 시점에 한다.

---

## 1. 무엇을 추천하나

### 1-1. 사람만 가진 것 넷

| 종류 | 이 문서의 이름 | 예 |
|---|---|---|
| 경험 | `experienced` | 글렌드로낙 신상을 마셔 봤다, 그 증류소에 아이와 가 봤다 |
| 취향·평가 | `prefers` | 셰리 캐스크가 과한 건 싫다, 그 병은 가격 대비 별로였다 |
| 해 보며 익힌 요령 | `practiced` | 우리 집 머신은 분쇄도를 이렇게 해야 압력이 맞는다 |
| 그 사람만 아는 사정 | `insider` | 동네 그 바에 그 병이 들어왔다, 그 행사는 오전에 가야 덜 붐빈다 |

**추천하지 않는 것**: 사전·백과·문서에 있는 사실("글렌드로낙은 하이랜드 증류소다"), 일반 절차("에스프레소 추출의 표준 압력"). 요청자의 agent가 직접 답할 수 있고, 사람을 찾을수록 느리고 비싸기만 하다.

`practiced`와 일반 절차의 경계가 가장 흐리다. 가르는 기준은 **그 사람의 조건에서 겪어 얻은 것인가**다 — "보통 9 bar"는 사실이고, "우리 집 머신은 9 bar로 두면 쓰게 나와서 분쇄를 굵게 한다"는 요령이다.

### 1-2. 예시 질문

| 질문 | need | 종류 | 개체 | 시점 |
|---|---|---|---|---|
| 글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어 | 1 | experienced | 글렌드로낙, 그 신상 | 최근 |
| 홈 에스프레소 머신에서 압력이 너무 높을 때 어떻게 해? | 1 | practiced | — | — |
| 도쿄에서 아이와 갈 만한 위스키 증류소 여행 어떻게 계획할까? | 2~3 | experienced·insider | — | — |
| 셰리 캐스크 싫어하는 사람한테 맞는 스페이사이드 추천해 줄 사람? | 1 | prefers | — | — |
| 글렌드로낙은 어느 지역 증류소야? | 0 | — (사실) | — | — |

마지막 질문은 추천을 내지 않는다(`mode: none`, 사유 `answerable_without_people`, §7-1). 요청자의 agent가 그 답을 받아 스스로 답한다.

### 1-3. 온라인 비용

"누가 답할 수 있는가"를 사람마다 LLM에게 물으면 비용과 지연 시간이 유저 수에 비례한다. 그래서 셋으로 나눈다.

```text
메시지가 올 때   발신자의 경험 기록 추출              새 서비스, LLM (게이트를 통과한 메시지만)
질문이 올 때     질문 → need → 키 → 후보 → 순위      discovery LLM 1회(타입 ① expansion의 형제 프롬프트), 새 서비스 조회 1회, SQL, 산술
실행할 때       선택된 1~2명이 자기 recall로 답한다    bourbon-agent가 매 턴 이미 하는 일
```

---

## 2. 원칙 — 키는 넓히고, 기록이 고른다

### 2-1. 키는 전부 손실 압축이다

topic은 질문을 분야로 줄인다("몰트 위스키"). 개체 QID는 개체로 줄인다("글렌드로낙"). 줄이는 순간 조건 — "이번 신상", "마셔 봤다", "압력이 높을 때" — 이 빠진다. 조건을 잃지 않는 것은 **근거 자체와의 대조**뿐이다. 이 설계에서 근거는 기록(종류·시각·개체)과 요약문이다.

그래서 역할을 가른다 — **키는 recall(후보를 모으는 것), 기록과 요약문은 precision(그중에서 고르는 것).**

### 2-2. 개체 키가 topic 키보다 위험한 이유

1. **양쪽이 독립적으로 정한다.** 질문 쪽 개체 해석과 기록 쪽 개체 해석이 같은 것을 골라야 매치된다. 한 이름에 Wikidata 항목이 여럿이면(증류소·브랜드·회사) 어긋날 수 있다.
2. **이름이 모호하다.** 야마자키(지명·증류소·인명). 틀린 개체로 가면 422도 없이 확신에 찬 오답이 나간다. topic 쪽 실패는 넓어짐이고, 개체 쪽 실패는 틀림이다.
3. **입도가 맞지 않을 수 있다.** 질문은 한 병이고 키는 증류소일 수 있다.
4. **너무 정밀하면 답할 사람을 놓친다.** "글렌드로낙 신상 맛이 어때?"는 비슷한 셰리 캐스크 하이랜드 몰트를 많이 마셔 본 사람도 답한다.

1과 3은 새 서비스가 **양쪽 해석을 한 곳에서** 하므로(§5-3 레지스트리) 선행 문서의 구조(질문은 우리가, 근거는 memory-api 빌드가)보다 작아진다. 2와 4는 규칙으로 막는다.

### 2-3. 규칙 다섯

1. **어떤 키도 후보를 거르지 않는다.** 후보는 need × 경로별 top K의 합집합이다. 개체 키가 어긋나도 topic 키로 들어온 사람은 순위 단계에 닿는다.
2. **개체 키는 집합이다.** 해석 후보 중 기준을 넘는 것을 모두 쓰고, 기록 쪽은 개체 자신과 그 부모를 다 받는다.
3. **확신이 낮은 개체 키는 끈다.** 모호하면 그 need는 topic 키로만 간다 — 실패가 틀림이 아니라 넓어짐이 되게.
4. **조건은 기록과 요약문이 되찾는다.** 종류·시점은 기록의 필드로, "신상"·"압력" 같은 나머지는 요약문 매치로.
5. **정밀도는 need가 정한다.** `precision: exact`(그것 자체를 겪은 사람) / `related`(가까운 것을 겪은 사람도).

---

## 3. 서비스들의 현재

코드에서 읽은 사실만 적는다. 추론이면 추론이라고 적는다.

### 3-1. bourbon-api — 메시지는 고쳐지지도 지워지지도 않는다

- **메시지는 INSERT-only다**: "`messages_*` — ... INSERT-only; rows are never updated or deleted"(`bourbon_api/messages/models.py:10-11`). 수정·삭제 route도 이벤트도 없다. 메시지 이벤트는 `bourbon.message_created`·`message_translated`·`message_artifacts_updated`다(`bourbon_api/messages/events.py:32, 48, 61`).
- `bourbon.user_deactivated`(`bourbon_api/events.py:15`)는 **best-effort**로 발행된다 — "AMQP failure is logged but does not roll back the deactivation"(`bourbon_api/users/service.py:518-523`). 이벤트가 유실될 수 있다.
- `message_created` payload: `room_id`, `message_id`, `sender_id`, `sender_type`, `type`, `room_type`(`user_dm`·`agent_dm`·`group`)(`bourbon_api/messages/events.py:18-29`). 본문은 없다.
- 본문은 `GET /api/internal/rooms/{room_id}/agent-context`(`around=message_id`)로 다시 읽는다 — bourbon-agent의 memory 적재가 이 경로를 쓴다(`bourbon_agent/memory/listeners.py:1-7, 93`, `api_internal_client/agent_context.py:59`).

### 3-2. memory-api-v2 — personal build는 이 목적과 어긋난다

personal build는 owner 한 명의 대화 전체를 LLM 여섯 단계(extract·grounding scoring·judge·dedup·competence·classes)로 읽어 개체·statement 그래프를 만드는 배치다. 결과는 owner 자신의 agent의 recall을 위한 것이다. 추천에 쓰려면 다음이 어긋난다.

| 추천에 필요한 것 | personal build | 근거 |
|---|---|---|
| **말한 사람 본인의** 경험 | owner의 memory에 다른 참가자의 발화도 statement로 들어간다. `speaker`는 이름 문자열이다 | `memory/knowledge/personal/structs.py:196`; 빌드는 sender id로 owner/타인 참조를 따로 센다(`memory/knowledge/personal/scoring.py:101-141`) |
| 겪은 **시각** | statement의 `created_at`은 빌드 시각 `datetime.now(UTC)`이고 `valid_time`은 제거됐다. 빌드는 provenance로 메시지 시각을 읽어 salience에 쓰지만(`time_by_msg`) statement에 남기지 않는다 | `reconcile.py:317`, `structs.py:5`, `scoring.py:117-127` |
| 사람 사이의 **개체 동일성** | 개체 id가 owner마다 따로(`uuid5(owner_id:canonical)`). Wikidata identity가 없는 개체는 `broader_qids = []`이고, statement의 `subject_qid`·`object_qid`도 null이다 | `memory/utils/ids.py:27-34`, `pipeline/resolve.py:85-91, 121` |
| 사실은 빼고 경험·취향만 | `declarative`가 기본값이다 | `extract.py:304-306` |
| 원래 표현 | statement `text`는 "a concise English summary" | `extract.py:299` |

하나씩 고치면 그쪽 모델을 이쪽 목적에 맞게 뒤트는 일이 된다. **그래서 personal build는 건드리지 않는다.**

memory-api에서 이 설계가 쓰는 것은 둘이다.

- **공개 지식 resolve** — `POST /knowledge/resolve`(`api/routers/knowledge/router.py:240`). mention 1~32개(`text` ≤ 200, `context`는 300자로 잘림), 후보 `limit` ≤ 50, `language` en/ko/ja. 후보마다 `aliases_matched`, `instance_of`, `subclass_of`, `match{method: alias_exact|name|prose, score}`. corpus는 sitelink가 하나 이상인 Wikidata 항목 전부이고(`memory/knowledge/public/dump.py:119-127`), `match.score`는 **mention 사이에 비교할 수 없다**(`memory/knowledge/public/structs.py:127-129`). 새 서비스가 개체를 QID에 붙이는 데 쓴다.
- **대화 저장** — bourbon-agent가 실행 시점에 recall하는 원문(`POST /{tenant}/search`)이 여기 있다. `POST /{tenant}/messages/lookup`은 메시지를 id로 찾되 `scope`가 읽을 수 있는 것만 돌려주고 `options.context`로 앞뒤를 붙인다(`api/routers/conversations/router.py:105-123`) — 핸들이 가리키는 메시지를 다시 읽는 자리다(§7-3).

memory-api에는 인증이 없다(`verify_token`은 있지만 어느 router도 쓰지 않는다, `api/depends/tenant.py:4-6`). resolve는 공개 지식 route이지만, 새 서비스가 보내는 mention은 개인의 메시지에서 나온 이름이다("동네 그 바"의 이름 자체가 개인적일 수 있다). 그래서 **mention 이름과 KIND 이름만 보내고 메시지 텍스트는 `context`로도 보내지 않는다.** resolve는 mention을 digest로만 로그에 남긴다(`api/routers/knowledge/router.py:252-256`).

### 3-3. topic-api — KIND만 받는다

- 카탈로그는 KIND만 받는다. 분류 프롬프트가 "product, company, ... and one numbered or dated release"를 topic이 아니라고 적는다(`topic/catalog_import/review_llm.py:34-41`). 사용자 신호로 노드를 더하는 경로는 없고, 없는 것이 정책이다(`docs/catalog-maintenance.md:3-4`).
- 스카치 위스키는 편집에서 빠졌고(`too_specific`), 하이랜드는 카탈로그 어디에도 없다(`data/catalog_seeds/reviewed/food-drink.yaml:5851-5899`).
- 유저 topic은 persona의 preferences 층에서 추출된다. facet `knowledge`·`engagement`·`affinity`·`duration`·`recency` + `volume`. "해 봤다"에 해당하는 facet은 없다.
- `/search/topics`는 lexical(정규화, 형태소 분석 없음, ko/en/ja label과 alias)이고 카탈로그에 없는 이름은 빈 목록이다(`topic/catalog/graph.py:57-71`).

**topic-api에 제품 노드를 요청하지 않는다.** 개체는 새 서비스의 레지스트리가 맡는다. topic-api는 분야 키와 관심 근거(소스 A)로 남는다.

### 3-4. bourbon-agent

- memory recall은 LLM이 고르는 tool(`search_conversations`)이고, 원문 대화를 BM25로 검색한다. personal knowledge의 context route는 어디서도 부르지 않는다.
- **recall의 범위는 방이다.** PERSONAL 방 밖에서 `search_conversations`가 닿는 것은 대부분 그 방 사람들이 함께 나눈 대화다(`bourbon_agent/agents/personal_agent/topic_memory.py:3-5`). owner의 다른 방에서 한 말은 요청자와의 방에서 보통 닿지 않는다.
- answerability gate가 없다. `recommend_agents` tool은 "추천해 달라"는 요청에만 불린다(예산 10초, `max_results=1`).
- agent가 agent에게 묻고 답을 합치는 코드는 없다. `moderator/__init__.py:12`가 `agent_recommender`를 "계획됨"으로 적어 두었을 뿐이다.

### 3-5. agent-discovery-api

- 타입 ① 파이프라인: expansion(LLM 1회) → grounding(topic-api 검색 + 모호할 때 disambiguation 1회) → 후보 조회 → 랭킹 → 조립. text→topic 단계 p50 1.77초 / p95 3.11초(disambiguation 게이트 on, `validation_results.md` §11-4), 요청 전체 p50 약 1.94초(추정).
- 미러: `visible_topic_rows`, `agents(… discoverable, agent_maturity …)`, `departed_users`(R68).
- 카탈로그 복사본 3,174 topic(Wikidata 3,148 + 가상 노드 26, 가상 노드의 `source.qid`는 `N-…`). 위스키 계열 노드는 위스키·몰트·그레인·콘·아메리칸 위스키, 아일라·스페이사이드 싱글 몰트, 브랜드 예외 히비키·그랜츠다.

---

## 4. 구성

```text
                      message_created (id만)
bourbon-api ─────────────────────────────────▶ 새 서비스 (가칭 bourbon-experience-api)
     ▲  agent-context 재조회                      ├─ 게이트: 사람이 보낸 메시지인가, 1인칭 표현이 있는가   (값싼 판정)
     └────────────────────────────────────────── ├─ 추출: 발신자의 경험 기록 + 요약문                   (LLM 1회)
                                                 ├─ 개체 해석: 레지스트리 + memory-api resolve
                                                 └─ 저장: 기록 · 요약문 · 핸들  (원문은 버린다)

질문 ──▶ bourbon-agent ──▶ discovery  POST /recommend/knowledge
                            T1 need 추출 (LLM 1회)
                            T2 topic 키 (topic-api 검색)
                            T3 후보: 소스 A (우리 visible_topic_rows) ∪ 소스 E (새 서비스 조회, 개체 해석 포함)
                            T4 순위 · T5 group · T6 조립 (요약문 기반 이유 + 핸들)
                                    │
bourbon-agent ◀─────────────────────┘  카드 제시, 실행: 대상 agent가 핸들의 기록에서 답을 시작한다
```

**새 서비스가 discovery와 따로인 이유**: 원문 메시지를 읽고 추출하는 쪽과 추천을 계산하는 쪽을 가른다. discovery는 "남의 대화를 한 글자도 들고 있지 않다"는 전제로 설계되어 있고(`agent_discovery_events.md` §2-4), 그 전제를 유지한다. discovery가 받는 것은 요약문(원문이 아니라 추출이 다듬은 문장)이고, 요약문도 유저의 글로 다룬다(§9-1). 새 서비스는 나중에 memory-api로 옮겨 갈 수 있다(오너, 2026-09-26) — 그래서 discovery와 새 서비스 사이의 계약을 좁게 둔다(§7-2).

**소스는 둘이다.**

- **소스 A** — topic-api 파생, 우리 `visible_topic_rows`. "이 분야에 관심을 드러낸 사람". 지금 있는 것이고 새 의존성이 없다.
- **소스 E** — 새 서비스의 경험 기록. "이것을 겪었거나, 좋아하거나, 해 봤거나, 사정을 아는 사람".

---

## 5. 새 서비스 — 경험 projection

### 5-1. 입력과 게이트

1. `bourbon.message_created`를 받는다(자기 큐, 자기 워커 — 이벤트 워커는 소비하는 repo가 소유한다).
2. **payload로 거른다**: `sender_type`이 사람이 아니면 버린다 — agent의 발화는 owner의 경험이 아니다. `type`이 텍스트가 아니면 버린다(첫 버전).
3. `agent-context`로 그 메시지와 **앞의 몇 턴**을 다시 읽는다. 앞의 턴은 "그거 마셔 봤어"의 "그거"를 풀기 위해서만 읽는다 — 기록은 발신자의 발화에서만 나온다.
4. **값싼 게이트**: 1인칭 경험·취향·요령 표현이 있는가를 규칙 또는 작은 분류기로 본다. 대부분의 메시지는 여기서 끝난다. 게이트의 recall이 추출 전체의 recall 상한이므로 느슨하게 둔다.
5. 통과한 메시지만 LLM 추출로 간다.

원문(메시지와 앞 턴)은 이 흐름 안에서만 메모리에 있고, 저장하지 않는다. 로그·예외·Sentry에도 남기지 않는다 — 남는 것은 id, 길이, 게이트 판정, reason code다.

### 5-2. 추출과 기록

LLM 한 번에 메시지 하나(+ 앞 턴 문맥)를 넣고, **발신자 본인에 관한** 기록 0~N개를 받는다.

```text
experience_record
  record_id           uuid
  person_id           uuid        발신자 = 이 기록의 주인
  kind                text        experienced | prefers | practiced | insider
  entity_key          text | null 공유 개체 키 (§5-3). 없으면 null
  parent_qids         text[]      개체의 상위 QID (브랜드·증류소·분야). 개체가 없어도 채울 수 있다
  topic_ids           text[]      카탈로그 topic (분야 키용, §5-4)
  stance              text | null positive | negative | mixed
  specificity         smallint    0~3. 이름·수치·장소·시점이 얼마나 구체적인가
  summary             text        발신자의 경험 한두 문장 (규칙은 아래)
  summary_lang        text        요약문 언어 (메시지 언어를 따른다)
  summary_en          text        같은 요약의 영어판 — 검색용. condition(영어)과 같은 언어에서 만나게
  terms               text[]      개체 이름의 표기들 (en/ko/ja, 별칭) — 검색용
  observed_at         timestamptz 메시지 시각
  room_id, room_type  —           출처. 기획 단계에서는 필터로 쓰지 않는다. 공개 범위 조건이 얹힐 자리(§10)
  message_id          uuid        원 메시지. 핸들은 이것을 저장하지 않고 응답 때 record_id로 발급한다 (§7-3)
  extractor_version   text        추출 프롬프트·스키마 버전
  created_at          timestamptz
```

**추출 규칙**

- **발신자 본인에 관한 것만.** 앞 턴에서 다른 사람이 한 말은 문맥이지 기록이 아니다. A가 B의 방에서 "나 마셔 봤어"라고 하면 그 경험은 A의 기록이다 — 선행 문서의 authorship 문제가 추출 단위에서 풀린다.
- **사실 진술은 기록하지 않는다**(§1-1). 1인칭이어도 "그 증류소는 하이랜드에 있어"는 버린다.
- **사람은 개체가 되지 않는다.** 지인·동료·가족은 `entity_key`로도 `terms`로도 남기지 않는다. "민수랑 갔다"의 민수는 요약문에서도 "친구와"로 쓴다.
- **요약문은 발신자의 경험을 발신자의 말로.** 한두 문장, 메시지 언어로, 과장하지 않는다 — "한 모금 맛봤다"를 "마셔 봤다"로 올리지 않는다. 다른 참가자의 이름·발언, PII(전화번호·주소 등)는 옮기지 않는다. 원문을 인용하지 않는다.
- 앞 턴으로도 무엇을 말하는지 풀리지 않으면 개체 없이 기록한다(`entity_key = null`, `parent_qids`만).

**원문은 담지 않는다.** 실행 시점에 대상 agent가 쓰는 것은 기록과 요약문이고, 원 메시지는 그 방의 scope가 허락할 때만 대화 저장소에서 다시 읽는다(§7-3). 원문의 정본은 한 곳에 남는다.

### 5-3. 공유 개체 레지스트리

기록 사이, 그리고 질문과 기록 사이에서 같은 것을 같은 키로 부르기 위한 표다. **새 서비스가 양쪽 해석을 모두 한다** — 추출할 때 기록의 개체를, 질문이 올 때 need의 개체를 같은 레지스트리로 푼다. 선행 문서에서 질문 쪽(우리)과 근거 쪽(memory-api 빌드)이 따로 해석해 생기던 어긋남(§2-2 1번)이 여기서 작아진다.

```text
entity
  entity_key      text     "wd:Q…" (Wikidata) 또는 "rg:<uuid>" (레지스트리 고유)
  label           jsonb    언어별 이름
  aliases         text[]   표기 변형 (누적)
  parent_qids     text[]   상위 QID
  qid             text | null
  created_at, merged_into
```

해석 순서:

1. 이름을 정규화해 레지스트리의 label·alias에서 찾는다. 있으면 그 키.
2. 없으면 memory-api `/knowledge/resolve`로 QID를 찾는다. 규칙은 **mention마다** 적용한다(점수는 mention 사이에 비교할 수 없다):
   - `match.method`가 `alias_exact` 또는 `name`인 후보만.
   - 1위와 2위의 점수 비가 `registry.ambiguity_ratio`보다 가까우면 QID를 붙이지 않는다.
   - 그렇지 않으면 1위를 `wd:` 키로 등록하고, 이름을 alias에 더한다.
3. QID가 없으면(새 병, 동네 가게) `rg:` 키를 새로 만들고, 문맥에서 잡힌 상위 개체(글렌드로낙)의 QID를 `parent_qids`에 넣는다.
4. 나중에 같은 것이 QID로 풀리면 `rg:` 키를 `wd:` 키로 합친다(`merged_into`). 기록은 조회 시 합쳐진 키로 읽힌다.

질문 쪽 해석은 1~2까지만 한다 — 질문 때문에 레지스트리에 새 키를 만들지 않는다. 질문의 이름이 레지스트리에도 Wikidata에도 없으면 개체는 `not_found`이고, 그 need는 분야 경로와 텍스트 경로로 간다(§6 T3). resolve가 답하지 않으면 `unavailable`이고 레지스트리 매치만 쓴다.

레지스트리에는 개체의 **공개 이름**만 있다. 누가 그것을 겪었는지는 기록에 있고 레지스트리에 없다. 사람은 등록하지 않는다(§5-2).

### 5-4. 분야 키 — topic_ids

추출 LLM이 기록마다 KIND 이름 1~3개("malt whisky", "whisky")를 함께 낸다. 새 서비스가 그것을 topic-api `/search/topics`로 풀어 `topic_ids`에 넣는다 — topic-api가 persona에서 topic을 붙이는 방식과 같다(가장 넓은 KIND 이름을 늘 함께 낸다, `topic/persona_topics/stages.py:58-64`). 개체 키가 없는 기록도, 개체 키가 어긋난 질문도 이 키로 만난다.

### 5-5. 무효화·탈퇴·재추출

- **메시지는 고쳐지지도 지워지지도 않는다**(§3-1). 그래서 원문의 수정·삭제를 따라갈 일은 없다. 기록이 무효가 되는 길은 둘이다 — 그 사람의 **탈퇴**, 그리고 서비스화 때 정할 **범위의 상실**(방이나 동의, §10).
- **탈퇴는 R68과 같은 방식이다.** `bourbon.user_deactivated`를 받으면 그 사람의 기록을 전부 지우고 id를 남긴다. 그리고 **기록을 만들거나 바꾸는 모든 쓰기 트랜잭션이 첫 문장에서 그 id를 확인한다** — 추출 결과의 쓰기, 백필, 재추출, resolve 재시도 뒤의 갱신 모두. 메시지는 지워지지 않으므로 탈퇴한 사람의 메시지는 원천에 남아 있고, 확인 없는 백필은 그 기록을 되살린다.
- **이벤트가 유실될 수 있다**(`user_deactivated`는 best-effort, §3-1). 유실되면 탈퇴한 사람의 기록이 남는다. 두 겹으로 막는다 — discovery는 소스 E의 후보를 자기 `departed_users`와 `agents` 미러로 다시 거르고(§6 T3), 새 서비스는 bourbon-api에 믿을 수 있는 탈퇴 확인 경로를 요청한다(§12 요청 1). bourbon-api의 내부 사용자 조회는 탈퇴자를 빼고 답하며 "absence must not be read as a deletion signal"이라 적고 있어, 그 부재를 탈퇴로 읽을 수는 없다.
- **재추출**: `extractor_version`이 바뀌면 원천에서 다시 읽어 만든다. 원문을 담지 않은 대가이고, 백필 경로를 처음부터 둔다. 백필도 위의 탈퇴 확인을 지난다.

### 5-6. 저장과 조회

- 기록·레지스트리·핸들은 관계형이 자연스럽다(PostgreSQL). 요약문 검색은 한국어·영어·일본어가 섞인다 — PostgreSQL 전문 검색으로 충분한지, OpenSearch(nori·kuromoji)를 둘지는 spike로 정한다(열린 항목 2).
- 조회 API는 discovery 한 곳을 위해 만든다(§7-2). **discovery가 기록을 미러링하지 않는다** — 새 서비스가 우리 것이고 이 조회를 위해 설계되므로, 선행 문서의 폴링 루프·manifest cursor·reconciliation이 필요 없다. 대신 요청 경로의 런타임 의존성이 되고, 그것이 답하지 않을 때의 동작을 정한다(§8).

### 5-7. 비용

- LLM은 **게이트를 통과한, 사람이 보낸 메시지**마다 1회다. 물량은 모른다 — 하루 메시지 수 × 사람 발신 비율 × 게이트 통과율로 추정하고, dev에서 게이트 통과율부터 잰다(§9-2).
- 추출도 e3llm을 쓴다. 요청 경로와 같은 proxy를 쓰면 배치 부하가 요청 경로의 꼬리 지연 시간을 늘릴 수 있다. 추출은 우선순위가 낮은 별도 한도(동시성 상한)로 돌리는 것이 맞다고 본다 — 둘 수 있는지는 e3llm 쪽에 묻는다(§12 요청 13).

---

## 6. 추천 흐름 (discovery)

### T0. 트리거 (bourbon-agent)

`recommend_agents`의 트리거를 "소유자의 질문에 사람의 근거가 필요할 때"로 넓히거나 두 번째 tool을 둔다. 추가 LLM 호출은 없다. 오판은 두 방향이고, **사람이 필요한 질문에 사전학습 지식으로 답하고 tool을 부르지 않는 쪽이 더 위험하다.** 첫 실험부터 호출 recall을 잰다(§9-4).

"이번 신상"처럼 요청자가 이름을 말하지 않은 경우, 방에서 그 이름이 나왔으면 `context`에 넣어 넘기는 것이 가장 싸고 정확한 보정이다. 그쪽 프롬프트 설계의 문제다(§12 요청 11).

### T1. need 추출 — expansion의 형제 프롬프트

타입 ①의 expansion은 "개념 그룹 0~3개, 그룹마다 probe"를 낸다. need는 그 그룹에 필드를 더한 것이다.

```json
{
  "people_needed": true,
  "groups": [
    {"index": 0,
     "probes": ["malt whisky", "whisky"],
     "importance": "required",
     "kind": "experienced",
     "precision": "exact",
     "recency": "recent",
     "entity_mentions": [{"text": "GlenDronach", "as_written": "글렌드로낙"}],
     "condition": "the newest GlenDronach release"}
  ]
}
```

- `people_needed`: 질문 전체가 사람의 근거를 필요로 하는가. `false`면 T2 이후를 돌지 않고 `mode: none`, `empty_reason: answerable_without_people`.
- `kind`: `experienced` | `prefers` | `practiced` | `insider` | `null`(종류 무관). 기록의 `kind`와 같은 어휘다.
- `precision`: `exact` | `related`(§2-3 규칙 5).
- `recency`: `recent` | `null`. discovery가 레지스터 행으로 `recency_days`로 바꿔 새 서비스에 넘긴다.
- `entity_mentions`: 질문이 이름으로 가리킨 고유한 것 0~2개. `text`는 영어 정식 이름, `as_written`은 질문의 표기. 분야 이름은 넣지 않는다. 모델이 모르는 것("이번 신상")은 지어내지 않는다.
- `condition`: 키에 담기지 않는 조건을 영어 한 구절로. 요약문(`summary_en`) 매치에 쓴다(T3). 질문에서 나와 새 서비스로 가는 텍스트는 이것과 `entity_mentions`뿐이다.
- `probes`는 지금처럼 분야 이름이다.

규칙:

- 호출은 하나다. **타입 ①의 프롬프트는 바이트 단위로 그대로 두고** 형제 프롬프트를 새로 둔다. 확장 프롬프트와 grounding 게이트는 서로를 전제로 쓰여 있고, 그 짝이 어긋나면 422가 크게 움직인다 — R60의 실측에서 게이트를 끈 쪽은 질문의 26%가 422였다.
- 그룹 상한은 3.
- 스키마 검증에 실패한 필드는 넓어지는 쪽으로 폴백한다 — `people_needed=true`, `importance=required`, `kind=null`(종류 무관), `precision=related`, `recency=null`, `entity_mentions=[]`, `condition=null`. `degraded`에 `need_fields_defaulted`.
- 질문 원문은 로그·예외·Sentry에 남기지 않는다(불변식 7).

### T2. topic 키

기존 S2 그대로 — probe로 topic-api 검색, 규칙으로 하나, 모호할 때만 batch disambiguation 1회. 결과는 need마다 `topic_id` 하나 또는 없음.

개체 키는 discovery가 풀지 않는다. `entity_mentions`를 그대로 새 서비스에 넘기고, 새 서비스가 기록과 **같은 레지스트리로** 푼다(§5-3). 질문과 기록이 한 해석기를 지나는 것이 이 구조의 요점이다.

need의 grounding 상태:

| topic 키 | 개체 mention | need |
|---|---|---|
| 있음 | 있음 | 두 경로로 후보 |
| 있음 | 없음 | topic 경로로만 |
| 없음 | 있음 | 개체 경로로만(소스 E만) |
| 없음 | 없음 | grounding 실패 — required면 422 `grounding_failed` |
| 모호 | 있음 | topic 키를 끄고 개체·텍스트 경로로(규칙 1) |
| 모호 | 없음 | required면 422 `grounding_ambiguous`, optional이면 그 need 제외 + `degraded`에 `need_dropped` |

topic-api가 답하지 않으면 503(타입 ①과 같음).

### T3. 후보와 근거

두 소스를 need마다 부른다.

**소스 A — 우리 PostgreSQL.** `visible_topic_rows`에서 need의 topic(+ `catalog_edges` 서브트리)을 가진 사람. `knowledge_facet`(topic-api `score_detail.facets.knowledge`)과 `confidence`를 컬럼으로 더한다.

**소스 E — 새 서비스 조회 1회**(§7-2). need마다 `topic_ids`, `entity_mentions`, `kind`, `recency`, `condition`을 넘기면, 새 서비스가 세 경로로 기록을 찾아 사람별로 모아 돌려준다.

```text
개체 경로     entity_key = 풀린 키 (+ 합쳐진 키)                 precision=exact의 주 경로
부모 경로     parent_qids ∋ 풀린 개체의 QID / 개체의 상위 QID      새 병처럼 QID 없는 개체를 겪은 사람
분야 경로     topic_ids ∋ need의 topic_ids                        개체가 어긋나거나 없을 때
텍스트 경로   summary_en·terms가 condition·mention 이름과 매치      키가 모두 빗나가거나 없을 때
```

서브트리는 discovery가 `catalog_edges`로 펼쳐 `topic_ids`에 담아 보낸다 — 새 서비스는 카탈로그 계층을 갖지 않는다. 텍스트 경로가 있어서 `not_found`인 개체도, topic 키가 없는 need도 후보를 얻는다(규칙 1).

- 경로마다 top K(레지스터, 초기 25)를 뽑아 합집합한다. 전체 점수 상위 N명이 아니다 — 소수의 개체 경험자가 다수의 분야 경험자에 묻히지 않게.
- `kind`와 `recency`는 **필터가 아니라** 경로 안의 순위 조건이다. 종류가 다른 기록도 후보가 되되 낮게 — T1의 `kind` 판정이 틀렸을 때 넓어지는 쪽으로.
- 네 경로의 모든 기록에 `condition`과 `terms`(풀린 개체의 표기들)로 `summary_en` 매치 순위를 붙인다. **"이번 신상"은 여기서만 되찾는다.**
- 응답은 사람별로: 경로별 기록 수, 매치한 기록 상위 몇 개(`record_id`, `kind`, `stance`, `specificity`, `observed_at`, 매치 순위, `summary`, 핸들), 그리고 need별 completeness.

**소스 E의 사람은 discovery가 다시 거른다.** `person_id`를 `agents.owner_user_id`로 조인해 `agent_id`를 얻고(조인이 안 되면 뺀다), `departed_users`에 있으면 빼고, 요청자와 **대화할 수 있는 사람만** 남긴다 — bourbon-api의 agent DM 게이트는 "친구이거나 agent가 public"이다(`bourbon_api/rooms/service.py:401-414`). 우리 미러로는 `friends`(불변식 2의 그 집합) 또는 `agents.discoverable`이다. 이것은 기획 단계에서 빼 둔 동의 문제가 아니다 — 요청자가 말을 걸 수 없는 사람을 추천하면 추천이 틀린 것이다.

두 소스의 합집합을 전체 상한 N(레지스터, 초기 50)으로 자른다. 자르는 규칙은 결정적이다 — required need마다 최소 슬롯을 먼저 채우되 그 안에서 **소스 E의 개체·부모 경로 후보를 먼저**, 남은 슬롯을 전체 점수 순으로, 동점은 `(score desc, agent_id asc)`.

**coverage 상태** — need마다 사람의 상태. 순위와 fallback에 쓰이고 응답에는 나가지 않는다(§7-1).

```text
prior_only       소스 A만 — 이 분야에 관심을 드러냈다
record_topic     소스 E 분야 경로 — 이 분야에서 무언가를 겪었다/좋아한다/해 봤다/안다
record_entity    소스 E 개체·부모 경로 — 이것(또는 이것의 상위)을 겪었다/…
record_match     요약문이 need의 condition·terms와 맞는 기록이 있다 (텍스트 경로로만 들어온 사람도 여기)
```

`record_match`도 "답할 수 있다"가 아니라 "그런 경험을 말한 적이 있다"다. 확정은 실행 시점이다.

### T4. 순위 — 결정적

feature(레지스터에 올린다):

- required need coverage(gate)
- 상태별 가중: `record_match` > `record_entity` > `record_topic` > `prior_only`
- 종류 일치: 기록의 `kind` = need의 `kind`
- 개체 매치의 종류: 개체 자신 1, 부모 0.5. 가중은 `precision`이 정한다(`exact`면 크다)
- 신선도: `recency: recent`인 need는 `observed_at`의 반감기 감쇠를 크게, 아니면 작게
- `specificity`, 같은 need에 대한 기록 수의 log
- 요약문 매치의 **need 안 순위**(점수 자체는 need 사이에 비교하지 않는다)
- 소스 A: `knowledge_facet`, `confidence`, tier
- 두 소스가 같은 사람을 가리키는가(교차 확인), `agent_maturity`

**곱셈식을 쓰지 않는다.** 곱하면 소스 A만 있는 후보는 0이 되고, 새 서비스가 답하지 않으면 전원이 0이 된다. 상태별 branch의 가중 합이고, 측정되지 않은 feature는 absent다(우리 `Features.present`가 이미 그 구분을 갖는다). 구현은 타입 ①의 `Ranker.features/score`와 같은 모양이다.

한 사람이 모든 required need를 덮으면 단일 추천이 group보다 우선한다.

### T5. group — 결정적

단일이 부족할 때만. 최대 2명, 모든 required need가 threshold 이상, 각 member가 다른 member가 못 덮는 need를 하나 이상 덮는다. need 최대 3, 후보 수십이면 조합 수백 개다. LLM을 쓰지 않는다.

### T6. 조립 — 요약문 기반 이유와 핸들

- **이유는 요약문에서 만든다**(오너, 2026-09-26: 요약문을 담는다). 템플릿이 need label과 가장 잘 맞은 기록의 요약문을 잇는다 — "최근 글렌드로낙 신상을 마셔 봤고 셰리가 강했다는 경험이 있습니다." 소스 A만 있는 사람은 중립 문구 "{need label}에 관심이 있는 agent입니다."
- LLM으로 이유 문장을 새로 쓰지 않는다. 요약문은 추출 때 규칙(§5-2)으로 이미 다듬어졌다.
- 기록 하나의 요약문만 쓴다. 여러 기록을 합쳐 사람의 프로필처럼 보이게 하지 않는다.
- **핸들**: 사람마다 근거 기록의 핸들 1~3개를 응답 때 발급해 붙인다. 요청자의 화면에는 쓰이지 않고, bourbon-agent가 실행할 때 대상 agent에게만 넘긴다(§7-3).

---

## 7. API 초안

### 7-1. discovery — `POST /api/internal/svc/agent-discovery/recommend/knowledge`

요청:

```json
{
  "user_id": "uuid",
  "question": "글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어",
  "context": "선택. 현재 대화 맥락. 제품명을 알면 여기에",
  "allow_group": true,
  "max_agents": 2,
  "room_id": "uuid",
  "lang": "ko"
}
```

`question`과 `context`는 T1의 LLM에만 간다. 새 서비스로 가는 것은 T1이 만든 `entity_mentions`·`condition`과, discovery가 만든 `topic_ids`·`kind`·`recency_days`뿐이다. 로그에는 `question_digest`·`question_chars`·`context_chars`만 남는다.

응답:

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "mode": "single",
  "empty_reason": null,
  "needs": [
    {"need_id": "n0", "label": "글렌드로낙", "importance": "required", "kind": "experienced"}
  ],
  "agents": [
    {"agent_id": "uuid", "owner_user_id": "uuid", "position": 1,
     "covers": ["n0"],
     "reason": "최근 글렌드로낙 신상을 마셔 봤고 셰리가 강했다는 경험이 있습니다.",
     "evidence_handles": ["opaque…"]}
  ],
  "empty": false,
  "degraded": []
}
```

- `mode`: `single | group | none`. `none`의 `empty_reason`: `answerable_without_people`(T1), `nobody_covers`(required need를 아무도 못 덮음).
- `needs[].label`은 개체가 풀렸으면 레지스트리의 공개 이름, 아니면 topic의 카탈로그 label.
- **`agents[]`는 새 wire 모델 `KnowledgeRecommendedAgent`다.** 타입 ①②③의 `RecommendedAgent`는 `matched_topics`·`signals`가 필수다. 공통 base(`agent_id`·`owner_user_id`·`position`)만 나눈다.
- `covers[]`는 need id 목록이고 coverage 상태는 싣지 않는다. `confidence`도 열지 않는다(calibration 전).
- `evidence_handles`는 불투명 문자열이다. 요청자 UI에 쓰지 않는다(§7-3).
- `degraded[]`: `expansion_partial`, `need_fields_defaulted`, `need_dropped`, `entity_resolution_unavailable`, `experience_unavailable`, `experience_incomplete`.

### 7-2. 새 서비스 — discovery가 부르는 조회

```http
POST /api/internal/svc/experience/candidates
```

```json
{
  "needs": [
    {"need_id": "n0",
     "topic_ids": ["…"],
     "entity_mentions": [{"text": "GlenDronach", "as_written": "글렌드로낙"}],
     "kind": "experienced", "recency_days": 90, "condition": "the newest GlenDronach release"}
  ],
  "exclude_person": "<requester>",
  "per_path_limit": 25
}
```

```json
{
  "needs": [
    {"need_id": "n0",
     "entity": {"entity_key": "wd:Q…", "label": {"ko": "글렌드로낙", "en": "GlenDronach"}, "state": "resolved"},
     "complete": true}
  ],
  "people": [
    {"person_id": "…", "needs": [
      {"need_id": "n0",
       "paths": {"entity": 2, "parent": 1, "topic": 5, "text": 3},
       "records": [
         {"record_id": "…", "kind": "experienced", "stance": "mixed", "specificity": 3,
          "observed_at": "2026-09-14T…", "match_rank": 1,
          "summary": "…", "handle": "opaque…"}
       ]}
    ]}
  ]
}
```

- `entity.state`: `resolved` | `ambiguous` | `not_found` | `unavailable`(resolve 장애, 레지스터 매치만 씀) | `none`(mention 없음). `ambiguous`·`not_found`면 개체·부모 경로를 돌지 않고 분야·텍스트 경로만 돈다(§2-3 규칙 3).
- 요청자 본인은 제외한다. 탈퇴한 사람은 기록이 없다(§5-5).
- `condition`은 새 서비스의 로그에 원문으로 남지 않는다 — digest와 길이만.
- 이 route가 discovery와 새 서비스 사이의 **계약 전부**다. 새 서비스가 memory-api로 옮겨 가도 이 모양은 그대로 둔다.

### 7-3. 핸들 — 추천의 근거를 실행의 근거로

- 핸들은 응답 때 `record_id`(와 버전)를 서명해 만드는 불투명 토큰이다. 저장하지 않는다. 요청자가 누구의 기록인지 풀 수 없다.
- bourbon-agent가 추천을 실행할 때 대상 agent의 턴에 핸들을 넘긴다(수락 뒤에 실행할지 자동 실행할지는 열린 항목 12). 대상 agent는 새 서비스에 핸들을 제시해 **그 기록 — 종류, 개체, 시각, 요약문 — 을 받고, 거기서 답을 시작한다.**
- **원 메시지는 기본으로 읽지 않는다.** 원 메시지는 대개 요청자가 없던 방에서 나왔고, bourbon-agent의 recall 범위는 방이다(§3-4). 그 메시지와 앞뒤를 요청자와의 방에서 읽으면 다른 방의 대화가 새어 나간다. 원 메시지가 필요하면 memory-api `POST /{tenant}/messages/lookup`을 **지금 방의 scope로** 부르고, 그 scope가 읽을 수 있을 때만 쓴다. 대부분은 요약문으로 답을 시작하고, 자세한 것은 대상 agent가 평소 recall로 찾는다. 요약문은 그 사람 본인의 경험만 담도록 추출됐으므로(§5-2) 다른 사람의 말이 새는 길이 아니다.
- **핸들을 풀 수 있는 것은 기록의 주인의 agent뿐이어야 한다.** 그런데 지금 내부 서비스 사이에는 호출자 인증이 없고, bourbon-agent 한 프로세스가 모든 agent를 대신해 말한다 — "호출한 agent의 owner"는 호출자가 주장하는 값일 뿐이다. 기획 단계에서는 다른 내부 route와 같은 신뢰 경계 안에 두고, 서비스화 전에 내부 호출 인증이 선행되어야 한다(§10).
- 기대하는 효과(추론, §9-4로 잰다): 실행 시점에 모델이 쿼리를 잘못 써서 근거를 못 찾는 실패가 줄고, 추천의 근거와 실행의 출발점이 같은 기록이라 calibration error에서 "둘이 다른 데이터를 봐서 생긴 오차"가 줄어든다.

---

## 8. 실패와 degradation

| 실패 | 동작 |
|---|---|
| T1 LLM 실패 | 타입 ①과 같이 verbatim 폴백 + `expansion_partial`. `people_needed=true`, `entity_mentions=[]` — 넓어지는 쪽 |
| need 필드 스키마 위반 | 넓어지는 쪽 폴백 + `need_fields_defaulted` |
| `people_needed=false` | `mode: none`, `empty_reason: answerable_without_people`. 오판이면 사람이 필요한 질문에 추천이 안 나간다 — 호출 recall과 함께 잰다 |
| topic 키 없음, 개체 mention 있음 | 소스 E로만 |
| topic 키·개체 mention 둘 다 없음 | required면 422 `grounding_failed` |
| topic 모호, 개체 mention 있음 | topic 키를 끄고 개체·텍스트 경로로 |
| topic 모호, 개체 mention 없음 | required면 422 `grounding_ambiguous`, optional이면 제외 + `need_dropped` |
| topic-api 검색 불가 | 503 |
| 새 서비스 timeout·5xx | 소스 A만으로 응답 + `experience_unavailable`. 상태는 전원 `prior_only`, 이유는 중립 문구, 핸들 없음. **소스 A로 볼 것이 없는 required need(topic 키가 없는 need)가 있으면 503** — 못 본 것이지 없는 것이 아니다(불변식 8). timeout은 레지스터 행이고, 새 route 전체 deadline(bourbon-agent의 10초 아래) 안에 든다 |
| resolve 장애(새 서비스 안) | 레지스트리 매치만으로 계속 + `entity_resolution_unavailable` |
| 새 서비스 일부 need `complete=false` | 받은 것으로 순위 + `experience_incomplete`. required need가 불완전하면 group을 내지 않는다 |
| 개체 `ambiguous`·`not_found` | 그 need는 분야·텍스트 경로로. degraded 아님(요청에 대한 판단) |
| 새 서비스가 요청자를 돌려줌 | 그 항목은 버리고 로그. 계약 위반이라 알람 |
| 소스 E의 사람이 `agents`에 없거나 `departed_users`에 있음 | 뺀다(§6 T3). `user_deactivated` 유실의 두 번째 겹 |
| required need를 아무도 못 덮음 | `mode: none`, `empty_reason: nobody_covers` |
| 실행 시 핸들이 안 풀림 | 대상 agent가 평소 recall로 |

새 서비스 쪽:

| 실패 | 동작 |
|---|---|
| agent-context 재조회 실패 | 재시도 사다리(우리 워커와 같은 모양) 뒤 버리고 로그. 백필이 메운다 |
| 추출 LLM 실패 | 같음 |
| resolve 실패 | 개체를 QID 없이 기록(`entity_key=null`, `parent_qids`만). 나중에 재해석 |
| 탈퇴한 사람에 대한 쓰기(늦은 `message_created`, 백필, 재추출) | 첫 문장의 확인에서 거절(§5-5) |
| `user_deactivated` 유실 | 기록이 남는다. discovery의 재필터가 막고, 믿을 수 있는 확인 경로를 요청한다(§12 요청 1) |

---

## 9. 관측과 평가

### 9-1. decision log (discovery)

원문 없이:

```text
question_digest, question_chars, context_chars
people_needed, needs_total, needs_required, need_fields_defaulted
needs_topic_key, needs_entity_mention, entity_state_by_need
candidates_by_path          source_a, entity, parent, topic, text, 그리고 겹침
final_by_path               최종 상위 k가 어느 경로로 들어왔는가
coverage_states             need × 상위 agent의 상태별 개수
experience_status           ok | unavailable | incomplete
single_sufficient, group_size, covered_required
degraded[], empty_reason
latency_ms.{expand, ground, experience, rank, group, assemble, total}
```

**불변식 7을 넓힌다.** 유저의 글 목록(topic_text, context, owner_note)에 `summary`·`summary_en`·`reason`·`condition`을 더한다 — 로그·예외·Sentry·decision log에 원문으로 싣지 않는다. decision log는 `reason`을 읽지 않는다(`discovery/journal.py`가 `matched_topics`를 읽지 않는 것과 같다, `journal.py:20-23`). 같은 규칙이 새 서비스와 bourbon-agent의 로그에도 적용된다.

`final_by_path`가 핵심 운영 지표다. 개체 질문에서 분야 경로로만 들어온 사람이 최종 상위에 자주 있으면 개체 해석이 어긋나고 있다는 신호이고, 합집합(§2-3 규칙 1)이 없었다면 잃었을 사람이다.

### 9-2. 먼저 재는 것

1. **추출 정밀도** — dev 메시지 표본에서 기록이 (가) 발신자 본인의 것인가 (나) 사실이 아니라 경험·취향·요령·사정인가 (다) 요약문이 과장하지 않는가. 사람이 라벨을 단다.
2. **게이트 recall** — 게이트가 버린 메시지 중 기록할 것이 있었던 비율. 게이트가 추출 전체의 상한이다.
3. **개체 해석 일치** — 같은 것을 가리키는 기록들이 같은 키로 모이는 비율, `rg:` 키가 나중에 `wd:`로 합쳐지는 비율, `ambiguous` 비율.
4. **추출 물량과 비용** — 하루 메시지 수, 사람 발신 비율, 게이트 통과율, 통과 메시지당 기록 수.

이 측정은 dev의 실제 대화를 읽는다. 기획 단계의 범위(공개 범위·동의 제외)는 **dev 내부 데이터로 실험한다**는 뜻이고, 결과로 남기는 것은 비율과 라벨 집계다.

### 9-3. 오프라인 — 합성 대화

기존 10만 합성 모집단은 topic 보유만 있고 대화가 없다. 그래서 **합성 대화 세트**를 만든다 — 사람마다 심어 둔 경험(개체, 종류, 시각, stance)을 LLM이 여러 대화 속 발화로 풀어 쓰고, 일부는 다른 참가자의 발화로, 일부는 사실 진술로 섞는다. 정답은 심어 둔 기록이다.

- 추출: 심은 경험의 recall, 타인 발화·사실 진술을 기록한 false positive
- 추천: 질문 세트(심은 경험에서 만든 질문 + 사람이 필요 없는 질문)의 relevant person recall@K / precision@K, `people_needed` 판정 정확도
- 경로 기여: 개체·부모·분야·텍스트 경로를 하나씩 끄면 recall이 얼마나 떨어지는가
- 요청자 자기 포함 0건

합성 대화는 **생성기의 가정 위에서** 잰다. 실제 사람의 말투·생략·지시어는 §9-2의 dev 측정이 대신한다.

### 9-4. 핵심 품질 지표

추천 당시 coverage와 실행 당시 `supported/unsupported`의 calibration error — 상태별, 경로별로. 핸들이 풀린 실행과 안 풀린 실행을 나눠 재면 핸들의 효과가 보인다.

**호출 recall**(T0, bourbon-agent 쪽): 사람이 필요했던 질문 중 tool이 불린 비율, 근거 없는 직접 답변 비율, 명시적 요청 때의 호출 성공률.

---

## 10. 기획 단계에서 빼 둔 것과 남겨 둔 자리

오너(2026-09-26): 새 타입의 기획이므로 공개 범위는 빼 두고 해 본 뒤, 실 서비스화할 때 고려한다.

**빼 둔 것** — 설계와 실험에서 조건을 걸지 않는다.

- 방의 공개 범위(DM·비공개 방에서 한 말을 기록할 것인가)
- 추천 대상이 되는 동의(`consultable` 같은 opt-in)

빼 두지 **않는** 것: 요청자가 그 사람에게 말을 걸 수 있는가(agent DM 게이트, §6 T3)와 탈퇴. 둘 다 동의가 아니라 추천이 맞는지의 문제다.
- 요약문이 요청자에게 보이는 것에 대한 동의
- topic tier(`public`/`friends`)와 소스 E의 관계

**남겨 둔 자리** — 나중에 필터로 얹을 때 구조를 고치지 않게.

- 기록마다 `room_id`·`room_type`(§5-2). 방 범위 조건은 이 필드 위의 필터다.
- 기록마다 `person_id`(발신자). 동의 조건은 이 필드와 동의 미러의 조인이다. 미러는 fail-closed로 둔다 — 값을 모르면 제외.
- 요약문과 중립 문구를 가르는 분기(T6). 요약문이 보이는 것에 대한 동의가 없으면 중립 문구로 떨어진다.
- 소스 A는 지금처럼 topic tier와 `discoverable`을 쿼리 안에서 건다(R17). 기존 타입과 같은 노출이라 빼 둘 이유가 없다.

**실험의 경계**(이 문서의 판단): 빼 둔 조건이 정해지기 전까지 실제 사용자 데이터로 production에 적재하거나 추천을 내보내지 않는다. 실험은 dev와 합성 대화에서 한다. 핸들을 푸는 route의 호출자 인증(§7-3)도 서비스화의 선행 조건이다.

**authorship**: 선행 문서의 가장 큰 열린 질문(owner의 memory에 든 타인의 발화를 owner의 근거로 셀 것인가)은 **발신자 귀속으로 대부분 풀린다** — 기록은 말한 사람의 것이다. 남는 것은 들은 것을 다시 말하는 경우다("친구가 그러는데 그 병 별로래"). 추출 규칙은 이것을 말한 사람의 `experienced`로 기록하지 않는다. `prefers`나 `insider`로 볼지는 실험으로 정한다(열린 항목 6).

---

## 11. 구현 슬라이스

슬라이스는 혼자서 배포되어 동작하는 증분 하나다. 나누는 기준은 새로 생기는 의존성이다.

| 슬라이스 | 새 의존성 | 답하는 질문 | 완료 조건 |
|---|---|---|---|
| **0. 추출 spike** | 새 서비스 골격, dev 메시지 읽기 | — (측정만) | 게이트·추출·레지스트리를 dev 표본에 돌려 §9-2의 넷을 잰다. 저장소 선택(§5-6) |
| **1. 소스 A + 단일** | 없음 | 이 분야에 관심을 드러낸 사람(`prior_only`) | route·envelope, T1 형제 프롬프트(새 필드 전부 추출·journal), `knowledge_facet` 미러, 결정적 순위, `people_needed` 판정 |
| **1-b. group** | 없음 | 두 need를 두 사람이 나눠 덮는 경우 | set-cover, 인원 2 |
| **2. 소스 E** | 새 서비스(이벤트 소비, 추출, 저장, 조회 API) | 이것을 겪었다·좋아한다·해 봤다·안다고 말한 사람 | 세 경로, 요약문 검색, 요약문 기반 이유, 합성 대화 측정 |
| **3. 핸들** | bourbon-agent 실행 경로(+ 원 메시지가 필요하면 memory-api `messages/lookup`) | 실행 시점에 근거를 바로 찾는가 | 핸들 발급·풀기, 소유자 검사, calibration을 핸들 유무로 나눠 재기 |
| **4. 트리거** | bourbon-agent 변경 | 실제로 불리는가 | tool 설명 변경 또는 두 번째 tool, 호출 recall |
| **5. 실행·종합** | bourbon-agent | 실제 답변 | 이 문서 범위 밖 |
| **서비스화** | 공개 범위·동의 결정(§10) | — | 필터를 남겨 둔 자리에 얹고, production 적재 |

- 슬라이스 0이 먼저다. 추출 정밀도와 물량을 모르면 2의 가치와 비용을 말할 수 없다.
- 슬라이스 1·1-b는 새 서비스 없이 배포된다. 그 결과는 **관심사 기반 추천**이지 "겪은 사람" 추천이 아니므로, 명시적 요청 경로에서만 내보낸다.

"글렌드로낙 이번 신상 마셔 본 사람" 질문이 슬라이스마다 어디까지 오는가:

| 도달 | 나오는 사람 |
|---|---|
| 1 | 위스키·몰트 위스키에 관심이 큰 사람 |
| 2 | 글렌드로낙(또는 그 신상)을 마셔 봤다고 말한 사람이 개체·부모 경로로. `recency`로 최근에 말한 사람이 위로. `summary_en`이 "newest release"와 맞으면 맨 위 |
| 3 | 그 사람의 agent가 실행 때 그 기록에서 답을 시작한다 |

---

## 12. 요청하고 확인할 것

**bourbon-api**

1. **믿을 수 있는 탈퇴 확인 경로.** `user_deactivated`는 best-effort이고, 내부 사용자 조회의 부재는 탈퇴 신호로 읽지 말라고 적혀 있다(§5-5). 탈퇴한 id 목록을 주는 route나, 발행을 보장하는 방식(outbox 등)이 있는지.
2. 새 서비스가 `GET /api/internal/rooms/{room_id}/agent-context`를 bourbon-agent와 같은 방식으로 불러도 되는지, 부하 한도.
3. 새 서비스의 큐를 `bourbon.message_created`에 바인딩하는 것 — 이벤트 워커는 소비하는 repo가 소유한다는 기존 원칙대로.

**memory-api**

4. `POST /knowledge/resolve`를 추출 경로에서(메시지마다가 아니라 레지스트리에 없는 새 이름마다) 불러도 되는지, 처리량과 지연 시간.
5. `POST /{tenant}/messages/lookup`을 핸들 실행에서 지금 방의 scope로 부르는 것이 그쪽 scope 의미에 맞는지(§7-3).
6. personal build는 건드리지 않는다는 것을 알린다. 이 추천을 위해 그쪽 모델을 바꿀 요청은 없다.

**topic-api**

7. `score_detail` block의 facet 이름과 `confidence`를 소비자 계약으로 삼아도 되는지(소스 A).
8. 제품·브랜드 노드는 요청하지 않는다. 개체는 새 서비스의 레지스트리가 맡는다.

**bourbon-agent**

9. `recommend_agents`의 트리거를 넓히는 것과 두 번째 tool 중 어느 쪽이 맞는지.
10. 실행 경로에서 핸들을 대상 agent의 턴에 넘길 자리 — 대상 agent가 그 핸들의 기록에서 답을 시작하게 하는 프롬프트·tool. 그리고 내부 호출 인증(§7-3).
11. 요청자가 이름을 모를 때("이번 신상") `context`에 제품명을 넣어 줄 수 있는지, 되묻는 것이 맞는지.
12. 호출 recall 지표를 그쪽 journal에서 낼 수 있는지.

**e3llm**

13. 추출의 배치 부하(§5-7)와 새 타입의 요청 부하. 배치에 별도 한도를 둘 수 있는지.

---

## 13. 열린 항목

1. 새 서비스의 이름, repo, 배포 단위.
2. 요약문 검색의 저장소 — PostgreSQL 전문 검색인가 OpenSearch인가(§5-6). 그리고 `summary_en`(영어 검색판)을 두는 것으로 언어 사이 매치가 충분한가 — 번역이 지명·제품명을 흔들 수 있다.
3. 게이트의 방식 — 규칙, 작은 분류기, 작은 LLM(§5-1).
4. 추출에 넣을 앞 턴의 수.
5. `registry.ambiguity_ratio`와 `rg:` → `wd:` 합치기의 기준.
6. 들은 것을 다시 말한 경우("친구가 그러는데")를 어떤 종류로 기록할 것인가(§10).
7. `people_needed` 판정의 오판 비용 — 사람이 필요한 질문을 사실 질문으로 판정하면 추천이 안 나간다. threshold를 어느 쪽으로 기울일 것인가.
8. `kind`를 순위 조건으로만 둘 것인가, 강한 필터로 쓸 조건이 있는가.
9. `recency_days`의 초기값, 그리고 종류별로 다르게 둘지(`prefers`는 오래 유효하고 `insider`는 빨리 낡는다).
10. 이유에 쓰는 요약문을 요청 언어로 번역할 것인가(요약문은 메시지 언어다).
11. 핸들의 수명 — 추천 뒤 언제까지 풀리게 할 것인가.
12. 요청자가 추천을 수락한 뒤에만 실행할지, 자동 실행할지.
13. group 인원을 3으로 올릴 조건.
14. required need 하나가 비었을 때 partial answer를 허용할지.
15. 실행 단계의 feedback event(추천 id ↔ `supported/unsupported`) — calibration을 재려면 먼저 있어야 한다.
16. 새 서비스를 memory-api로 옮기는 시점과 기준(오너: 우선 새 서비스, 필요하면 넘긴다).
17. §10의 빼 둔 것 전부 — 실 서비스화 때.

---

## 14. 선행 문서와 달라진 것

| 선행 문서(`personal-knowledge-agent-recommendation.md`) | 이 문서 | 이유 |
|---|---|---|
| 근거는 memory-api personal build의 파생본(소스 B) | 추천만을 위한 경험 projection, 새 서비스(소스 E). personal build는 건드리지 않는다 | personal build는 owner의 recall을 위한 그래프라 귀속·시각·개체 동일성·사실 비중이 이 목적과 어긋난다(§3-2) |
| owner의 memory 단위, authorship은 결정 대기 정책 | 메시지 단위, 발신자에게 귀속 | "누가 겪었나"가 정의상 맞게 된다. authorship 질문이 대부분 사라진다(§10) |
| 근거는 개수와 날짜만, 텍스트 없음 | 요약문을 담는다(오너, 2026-09-26). 원문은 담지 않는다 | 조건("이번 신상")을 되찾고 이유를 풍부하게 한다 |
| 시각은 빌드 시각 | 메시지 시각 | "최근에"가 조건이다 |
| 키는 topic 하나, 소스 B는 `topic_qid_map`을 거쳐 조회 | 키는 topic과 개체. 개체는 새 서비스의 레지스트리가 질문과 기록 양쪽을 한 해석기로 푼다 | 카탈로그는 KIND만 받고, 독립된 두 해석은 어긋난다(§2-2) |
| `topic_qid_map`, 폴링 루프, manifest cursor, reconciliation | 없음. discovery가 새 서비스를 조회한다 | 새 서비스는 우리 것이고 이 조회를 위해 설계된다 |
| 모든 질문이 대상 | `people_needed`로 사실 질문을 거른다 | 사람이 필요한 질문만 추천할 가치가 있다(§1) |
| knowledge_kind 다섯(memory-api 어휘) | kind 넷(`experienced`·`prefers`·`practiced`·`insider`) | 사람만 가진 것의 분류다. 사실(`declarative`)과 계획(`intention`)은 추천의 근거가 아니다 |
| 이유는 중립 문구 하나 | 요약문 기반 이유, 소스 A만이면 중립 문구 | 요약문을 담기로 했다. 동의는 서비스화 때(§10) |
| 실행 시점의 근거 찾기는 agent의 recall에 맡김 | 핸들로 근거 기록을 대상 agent에게 넘긴다 | 응답 가능성을 올리고, 추천과 실행의 출발점을 같게 한다(§7-3) |
| 동의(`consultable`)와 authorship이 소스 B production의 선행 조건 | 기획 단계에서 공개 범위·동의를 빼 두고 자리만 남긴다 | 오너, 2026-09-26 |
| 오프라인 측정은 합성 모집단에 파생본을 합성 | 합성 **대화** 세트, 그리고 dev 추출 정밀도 | 추출이 새로 생긴 단계이고, 대화 없이는 그것을 잴 수 없다 |
