# 사람에게 물어야 하는 질문의 agent 추천

> 상태: **기획 초안, 결정 아님**
> 범위: 새 추천 타입(타입 ④ 후보)과 그것을 위한 새 서비스 `bourbon-lived-knowledge-api`, 그리고 `bourbon-agent-discovery-api` · `bourbon-agent` · `bourbon-api` · `bourbon-memory-api-v2` · `bourbon-topic-api`와의 경계
> 비범위: 타입 ①·②·③의 계약 변경, 추천받은 agent의 실제 답변과 종합(경계만 정한다)
> **기획 단계에서 빼 둔 것**(오너, 2026-09-26): 공개 범위·동의(`consultable`)·방 범위. 설계와 실험에는 조건을 걸지 않고, 실 서비스화할 때 다룬다. 나중에 붙일 자리만 남긴다(§12).
> 선행 문서: `archive/2026-09-26_knowledge-type-first-draft/personal-knowledge-agent-recommendation.md`(2026-09-18 ~ 09-21, 아카이브). 그 문서는 memory-api personal build의 결과를 topic에 조인해 근거로 썼다. 이 문서는 **추천만을 위한 데이터를 새 서비스에 따로 두고**, 메시지 하나하나를 보낸 사람의 경험으로 저장한다. 무엇이 달라졌는지는 §17에 모았다.
> 이 문서의 "현재"는 각 repo의 HEAD 기준이다 — bourbon-agent `61f84aea`(origin/main, 09-25), bourbon-api `078eeeb`(origin/main, 09-21), memory-api-v2 `8c6a937`(origin/main, 09-19), topic-api `ffc62bf`(09-22), agent-discovery-api `bac5de9`(09-24)

---

## 0. 요약

사용자의 personal agent가 **LLM으로는 답할 수 없는 질문** — 누군가 직접 겪은 경험, 취향, 해 보며 익힌 요령, 그 사람만 아는 사정이 필요한 질문 — 을 받으면, 그런 경험을 가진 다른 사용자의 personal agent를 추천해 그 agent와 이야기해 보게 한다. 일반적인 사실 질문에는 추천하지 않는다.

설계의 뼈대는 여섯 가지다.

1. **사람이 필요한 질문만 추천한다.** 질문을 받으면 먼저 "이것이 사람의 경험이 있어야 답할 수 있는 질문인가"를 판정하고, 추천의 근거로도 사실이 아닌 경험·취향·요령·사정만 쓴다(§1).
2. **추천용 데이터는 새 서비스가 따로 만든다.** 메시지가 올라올 때마다 "보낸 사람이 직접 겪은 것"을 뽑아 **경험 기록**으로 저장한다. memory-api의 personal build(사용자마다 대화 전체를 LLM으로 읽어 만드는 지식 그래프)는 각 사용자 자신의 agent가 기억해 답하기 위한 데이터라 목적이 다르고, 그대로 둔다(§6-2, §7).
3. **경험 기록은 보낸 사람의 것이다.** A가 B와의 방에서 "나 그거 마셔 봤어"라고 하면 그 경험은 A의 기록이 된다. 기록의 시각은 그 메시지의 시각이다. 기록이 가리키는 대상(제품, 장소, 가게)에는 **엔티티 레지스트리**의 id를 붙여, 누가 어떤 표기로 말했든 같은 대상은 같은 id로 모이게 한다(§2, §7).
4. **원문은 저장하지 않는다.** 메시지를 읽고 기록을 뽑은 뒤 원문은 버린다. 남는 것은 기록, 짧은 요약문, 원 메시지의 id다(§7-2).
5. **topic과 엔티티는 후보를 모으는 데만 쓰고, 필터링에는 쓰지 않는다.** 둘 다 질문을 단순한 id 하나로 줄이는 과정이라 "이번 신상", "마셔 봤다" 같은 조건이 빠진다. 그래서 여러 경로로 후보를 넓게 모은 뒤, 순위는 경험 기록의 종류·시각·요약문이 얼마나 맞는지로 정한다(§3, §9).
6. **추천받은 agent에게 근거를 넘긴다.** 추천마다 `evidence_ref` — 근거가 된 경험 기록을 가리키는 토큰 — 를 붙인다. 추천받은 agent만 이것으로 기록을 조회할 수 있고, 조회한 기록에서 답을 시작한다. 추천의 근거와 실제 대화의 출발점이 같아져 답을 찾지 못하는 경우가 줄어든다(§9 T6, §10-3).

추천이 보장하는 것은 **"이 사람이 이런 경험을 말한 적이 있다"** 까지다. 지금도 그 경험을 기억해 제대로 답할 수 있는지는 추천받은 agent와의 실제 대화에서 드러난다. 그래서 이 기능의 품질은 "추천한 사람이 실제로 답해 낸 비율"로 잰다(§13-4).

---

## 1. 무엇을 추천하나

### 1-1. 사람만 가진 것 넷

| 종류 | 이 문서의 이름 | 예 |
|---|---|---|
| 경험 | `experienced` | 글렌드로낙 신상을 마셔 봤다, 그 증류소에 아이와 가 봤다 |
| 취향·평가 | `prefers` | 셰리 캐스크가 과한 건 싫다, 그 병은 가격 대비 별로였다 |
| 해 보며 익힌 요령 | `practiced` | 우리 집 머신은 분쇄도를 이렇게 해야 압력이 맞는다 |
| 그 사람만 아는 사정 | `insider` | 동네 그 바에 그 병이 들어왔다, 그 행사는 오전에 가야 덜 붐빈다 |

**추천하지 않는 것**: 사전·백과·문서에 있는 사실("글렌드로낙은 하이랜드 증류소다"), 일반 절차("에스프레소 추출의 표준 압력"). 요청자의 agent가 직접 답할 수 있고, 사람을 찾으면 느리고 비싸기만 하다.

`practiced`와 일반 절차의 경계가 가장 흐리다. 기준은 **그 사람의 환경에서 직접 해 보고 얻은 것인가**다 — "보통 9 bar"는 사실이고, "우리 집 머신은 9 bar로 두면 쓰게 나와서 분쇄를 굵게 한다"는 요령이다.

### 1-2. 예시 질문

| 질문 | need 수 | 종류 | 엔티티 | 시점 |
|---|---|---|---|---|
| 글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어 | 1 | experienced | 글렌드로낙, 그 신상 | 최근 |
| 홈 에스프레소 머신에서 압력이 너무 높을 때 어떻게 해? | 1 | practiced | — | — |
| 도쿄에서 아이와 갈 만한 위스키 증류소 여행 어떻게 계획할까? | 2~3 | experienced·insider | — | — |
| 셰리 캐스크 싫어하는 사람한테 맞는 스페이사이드 추천해 줄 사람? | 1 | prefers | — | — |
| 글렌드로낙은 어느 지역 증류소야? | 0 | — (사실) | — | — |

need는 질문이 요구하는 것 하나하나다. 여러 개면 한 사람이 다 채우거나 두 사람이 나눠 채운다(§9 T5). 마지막 질문은 추천을 내지 않는다(`mode: none`, 사유 `answerable_without_people`). 요청자의 agent가 그 응답을 받고 스스로 답한다.

### 1-3. 언제 무엇을 하고, 비용은 어디서 드나

"누가 답할 수 있는가"를 질문마다 사용자 한 명씩 LLM에게 물으면 비용과 지연 시간이 사용자 수에 비례한다. 그래서 무거운 일은 메시지가 올라올 때 미리 해 두고, 질문이 올 때는 조회와 계산만 한다.

| 언제 | 누가 | 무엇을 | LLM 호출 | 비용이 비례하는 것 |
|---|---|---|---|---|
| 메시지가 올라올 때 | 새 서비스 | 보낸 사람의 경험 기록을 뽑아 저장 | 사전 필터(LLM 앞에서 경험 표현이 없는 메시지를 제외하는 값싼 판정)를 통과한 메시지만 1회 | 메시지 수 |
| 질문이 올 때 | discovery | 질문 분석 → 후보 조회 → 순위 → 응답 | 1~2회(질문 분석, topic이 모호할 때 disambiguation) | 후보 수. 사용자 수와 무관 |
| 추천을 실행할 때 | bourbon-agent | 추천받은 agent가 요청자와 대화 | agent가 평소 쓰는 만큼 | 이 기능의 비용이 아님 |

---

## 2. 용어

| 용어 | 뜻 |
|---|---|
| **need** | 질문이 요구하는 것 하나. 질문 분석(§9 T1)이 0~3개로 나눈다. 각 need에 종류(`experienced` 등), 대상 엔티티, 시점 조건이 붙는다 |
| **topic** | topic-api 카탈로그의 분야 노드("몰트 위스키", "에스프레소"). 카탈로그는 분야(KIND)만 받고 제품·브랜드는 받지 않는다(§6-3) |
| **엔티티** | 경험의 대상이 되는 구체적인 것 — 제품, 브랜드, 증류소, 가게, 장소. "글렌드로낙", "글렌드로낙 21 팔리아먼트" |
| **상위 엔티티** | 한 엔티티를 포함하는 더 넓은 엔티티. "글렌드로낙 21 팔리아먼트"의 상위 엔티티는 "글렌드로낙"이다. 분야(topic)와는 다르다 — 상위 엔티티도 구체적인 대상이다 |
| **resolve** | 이름을 엔티티 레지스트리의 id로 바꾸는 것. "글렌드로낙"·"GlenDronach"을 같은 id로 |
| **엔티티 레지스트리** | 새 서비스가 가진 엔티티 사전 테이블. 모든 사용자의 경험 기록이 함께 쓴다. 한 엔티티에 id 하나, 여러 표기(한/영/일, 별칭), 상위 엔티티(글렌드로낙 21 → 글렌드로낙)를 둔다. Wikidata에 있으면 그 QID를 id로 쓰고(`wd:Q…`), 새로 나온 병이나 동네 가게처럼 Wikidata에 없으면 레지스트리가 id를 새로 만든다(`rg:…`). 목적은 A가 "글렌드로낙 21"이라 쓰고 B가 "GlenDronach Parliament"라 써도 같은 id로 모이게 하는 것이다(§7-3) |
| **경험 기록** | 새 서비스가 메시지 하나에서 뽑아 저장하는 한 줄. 누가(보낸 사람), 어떤 종류로(`experienced` 등), 무엇에 대해(엔티티·topic), 어땠는지(긍정·부정), 언제(메시지 시각), 요약문, 원 메시지 id(§7-2) |
| **요약문** | 경험 기록마다 붙는 한두 문장. 보낸 사람 본인의 경험만 담는다. 추천 이유 문장과 검색에 쓴다 |
| **관심 소스** | 후보를 찾는 첫 번째 데이터. topic-api에서 온, 사용자가 공개한 관심 topic(discovery의 `visible_topic_rows`). "이 분야에 관심을 드러낸 사람"을 안다. 지금 있는 것이다 |
| **경험 소스** | 후보를 찾는 두 번째 데이터. 새 서비스의 경험 기록. "이것을 겪었다·좋아한다·해 봤다·안다고 말한 사람"을 안다 |
| **검색 경로** | 경험 소스에서 후보를 찾는 네 가지 방법 — 엔티티로, 상위 엔티티로, topic으로, 요약문 텍스트로(§9 T3). 경로마다 상위 K명을 뽑아 합친다 |
| **`evidence_ref`** | 추천 결과에 붙는 opaque 토큰. 근거가 된 경험 기록을 가리킨다. 요청자는 이것으로 아무것도 조회할 수 없고, 추천받은 agent가 새 서비스에 제시하면 그 기록을 돌려받는다(§10-3) |
| **personal build** | memory-api가 사용자마다 대화 전체를 LLM으로 읽어 엔티티·statement 그래프를 만드는 배치. 그 사용자 자신의 agent가 기억해 답하기 위한 것이다(§6-2) |
| **대화 검색(recall)** | bourbon-agent가 답하기 전에 memory-api의 대화 원문을 검색하는 것(`search_conversations` tool). 지표 이름으로서의 recall(찾아야 할 것 중 찾은 비율)과 구별해 이 문서에서는 "대화 검색"이라고 쓴다 |
| **불변식 N, RNN** | discovery 계약(`agent_discovery_contract.md` §5)의 불변식과 기획 repo `decisions.md`의 결정 번호. 이 문서가 인용하는 것 — 불변식 2(friends tier 행은 요청자가 친구일 때만), 불변식 7(사용자의 글은 로그·예외·Sentry에 원문으로 남기지 않는다), 불변식 8(422는 봤는데 없다, 503은 못 봤다), R17(공개 범위 조건은 쿼리 안에서 건다), R60(disambiguation 게이트), R68(탈퇴한 사용자는 다시 기록하지 않는다) |
| **coverage 상태** | need마다 후보 한 명이 얼마나 확실한 근거를 가졌는지의 단계(§9 T3). 순위에만 쓰고 응답에는 싣지 않는다 |

---

## 3. 원칙 — topic과 엔티티는 모으는 데만 쓴다

### 3-1. 질문을 id로 바꾸면 조건이 빠진다

topic은 질문을 분야 하나로 줄인다("몰트 위스키"). 엔티티는 대상 하나로 줄인다("글렌드로낙"). 어느 쪽이든 줄이는 순간 "이번 신상", "마셔 봤다", "압력이 높을 때" 같은 조건이 빠진다. 조건까지 맞춰 볼 수 있는 것은 **근거 자체** — 이 설계에서는 경험 기록의 종류·시각·요약문 — 뿐이다.

그래서 역할을 나눈다. **topic과 엔티티는 후보를 넓게 모으는 데(recall) 쓰고, 경험 기록과 요약문은 그중에서 맞는 사람을 고르는 데(precision) 쓴다.**

### 3-2. 엔티티 매칭이 topic 매칭보다 위험한 이유

1. **양쪽 resolve 결과가 같아야 맞는다.** 질문 속 이름과 기록 속 이름이 같은 엔티티로 resolve되어야 매칭된다. 한 이름에 Wikidata 항목이 여럿이면(증류소·브랜드·회사) 어긋날 수 있다.
2. **이름이 모호하다.** 야마자키는 지명·증류소·인명이다. 엉뚱한 엔티티로 resolve되면 422도 없이 틀린 사람이 추천된다. topic 매칭이 실패하면 범위가 넓어질 뿐이지만, 엔티티 매칭이 실패하면 결과가 틀린다.
3. **범위(granularity)가 다를 수 있다.** 질문은 병 하나를 말하는데 기록은 증류소를 가리킬 수 있다.
4. **너무 정확하면 답할 사람을 놓친다.** "글렌드로낙 신상 맛이 어때?"는 비슷한 셰리 캐스크 하이랜드 몰트를 많이 마셔 본 사람도 답할 수 있다.

1과 3은 새 서비스가 질문과 기록을 **같은 엔티티 레지스트리로** resolve해서(§7-3) 줄어든다. 2와 4는 아래 규칙으로 막는다.

### 3-3. 규칙 다섯

1. **topic과 엔티티로 후보를 필터링하지 않는다.** 후보는 need마다, 검색 경로마다 상위 K명을 뽑아 합친 합집합이다. 엔티티 매칭이 어긋나도 topic이나 텍스트로 들어온 사람은 순위 단계까지 간다.
2. **엔티티는 하나가 아니라 여러 개로 매칭한다.** resolve된 엔티티와 그 상위 엔티티를 함께 쓴다.
3. **애매한 엔티티는 쓰지 않는다.** 이름이 모호하면 그 need는 topic과 텍스트로만 찾는다. 애매할 때는 좁히지 않고 넓게 간다.
4. **빠진 조건은 경험 기록과 요약문으로 반영한다.** 종류·시점은 기록의 필드로, "신상"·"압력" 같은 나머지 조건은 요약문 매칭으로.
5. **얼마나 정확해야 하는지는 need가 정한다.** `precision: exact`(바로 그것을 겪은 사람) / `related`(비슷한 것을 겪은 사람도).

---

## 4. 전체 흐름

두 흐름이 있다. 메시지가 올라올 때 새 서비스가 경험 기록을 쌓는 **적재 흐름**, 질문이 올 때 discovery가 추천을 만드는 **추천 흐름**이다.

### 4-1. 적재 흐름 — 새 서비스

```text
bourbon-api ── bourbon.message_created (id, 보낸 사람, 방 종류) ──▶ 새 서비스
                                                                   │
  ① 사람이 보낸 텍스트 메시지만 남긴다 (agent 발화 제외)                 │
  ② bourbon-api에서 그 메시지와 앞의 몇 턴을 다시 읽는다                 │
  ③ 사전 필터: 1인칭 경험·취향·요령 표현이 있는가 (규칙·작은 분류기)        │  대부분 여기서 끝
  ④ LLM 추출: 보낸 사람 본인에 관한 경험 기록 0~N개 + 요약문              │
  ⑤ 엔티티 resolve: 레지스트리에서 찾고, 없으면 memory-api resolve로 QID   │
  ⑥ topic 매핑: 분야 이름을 topic-api 검색으로 topic id에                 │
  ⑦ 저장: 경험 기록 · 요약문 · 원 메시지 id. 원문은 버린다                 ▼
                                                              경험 기록 (경험 소스)
```

1. `bourbon.message_created`에는 id만 있고 본문이 없다. `sender_type`으로 사람이 보낸 메시지만 남긴다 — agent의 발화는 그 사람의 경험이 아니다.
2. 본문은 bourbon-api의 agent-context route로 다시 읽는다. 앞의 몇 턴은 "그거 마셔 봤어"의 "그거"가 무엇인지 알기 위해서만 읽는다.
3. 사전 필터가 대부분의 메시지를 LLM 호출 전에 제외한다. 여기서 놓친 것은 다시 찾을 수 없으므로 느슨하게 둔다.
4. 추출은 보낸 사람 본인의 경험만 기록한다. 앞 턴에서 다른 사람이 한 말은 문맥일 뿐 기록하지 않는다.
5. 대상이 레지스트리에 있으면 그 id, 없으면 memory-api의 공개 지식 resolve로 Wikidata QID를 찾고, 그래도 없으면 새 id를 만든다(§7-3).
6. 분야 이름("malt whisky")을 topic id로 바꿔 둔다. 엔티티가 없거나 어긋나도 topic으로 찾을 수 있게.
7. 원문은 이 흐름 안에서만 메모리에 있고 저장하지 않는다.

**관심 소스는 이미 있다.** topic-api가 persona의 preferences에서 사용자의 관심 topic을 뽑고, discovery 워커가 `bourbon.topics_updated`를 받아 공개된 topic을 `visible_topic_rows`에 미러한다. 타입 ①②③이 쓰는 그 테이블이다. 이 흐름에서 바뀌는 것은 topic-api 응답의 `knowledge` facet과 `confidence`를 컬럼으로 더하는 것뿐이다.

### 4-2. 추천 흐름 — discovery

```text
질문 ──▶ bourbon-agent (recommend tool) ──▶ discovery  POST /recommend/knowledge
                                              │
  T1 질문 분석 (LLM 1회)                        │ 사람이 필요한가? 아니면 여기서 mode: none
      need 0~3개, 종류, 엔티티 이름, 시점, 조건      │
  T2 topic 찾기 (topic-api 검색)                │
  T3 후보 모으기 ─┬─ 관심 소스: discovery DB의 visible_topic_rows (topic으로)
                 └─ 경험 소스: 새 서비스 조회 1회
                       엔티티 · 상위 엔티티 · topic · 텍스트 네 경로, 경로마다 상위 K명
                    → 합집합 → 탈퇴자 제외, 요청자가 대화할 수 있는 사람만
  T4 순위 (종류 일치, 최근성, 요약문 매칭, 엔티티 매칭, 관심 강도)
  T5 한 사람으로 부족하면 두 사람 조합
  T6 응답: 추천 이유(요약문 기반) + evidence_ref
                                              │
bourbon-agent ◀────────────────────────────────┘
  카드로 보여 주고, 실행하면 추천받은 agent에게 evidence_ref를 넘긴다
  → 추천받은 agent가 그 경험 기록에서 답을 시작한다
```

1. **T0 (bourbon-agent)**: 요청자의 agent가 "이 질문에는 사람의 경험이 필요하다"고 판단하면 recommend tool을 부른다.
2. **T1 질문 분석**: 질문을 need로 나누고, 사람이 필요 없는 질문이면 여기서 `mode: none`으로 멈춘다. 질문 원문은 이 LLM 호출에만 쓰고, 이후에는 T1이 만든 짧은 조건문(영어)과 엔티티 이름만 넘어간다.
3. **T2 topic 찾기**: need마다 topic을 찾는다(타입 ①과 같은 방식). 엔티티는 discovery가 resolve하지 않고 이름 그대로 새 서비스에 넘긴다 — 경험 기록과 같은 레지스트리로 resolve하기 위해서다.
4. **T3 후보 모으기**: 관심 소스는 discovery DB에서 topic으로, 경험 소스는 새 서비스 조회 한 번으로 모은다. 새 서비스가 네 경로에서 후보를 뽑아 사람별로 묶어 돌려주면, discovery가 둘을 합치고 탈퇴자를 빼고 요청자가 대화를 시작할 수 있는 사람만 남긴다.
5. **T4 순위**: 종류 일치, 최근성, 요약문 매칭, 엔티티 매칭, 관심 강도의 가중 합. 같은 입력이면 늘 같은 순위다(deterministic).
6. **T5 조합**: 한 사람이 모든 need를 채우지 못하면 서로 보완하는 두 사람을 고른다.
7. **T6 응답**: 사람마다 추천 이유(근거 기록의 요약문)와 `evidence_ref`를 붙인다.
8. 새 서비스가 답하지 않으면 관심 소스만으로 추천하고 `degraded`에 남긴다(§11).

### 4-3. 왜 새 서비스를 discovery와 나누나

원문 메시지를 읽고 추출하는 쪽과 추천을 계산하는 쪽을 나누기 위해서다. discovery는 "남의 대화를 한 글자도 들고 있지 않다"는 전제로 설계되어 있고(`agent_discovery_events.md` §2-4), 그 전제를 지킨다. discovery가 받는 것은 요약문 — 원문이 아니라 추출이 다듬은 문장 — 이고, 요약문도 사용자의 글로 다룬다(§13-1). 새 서비스는 나중에 memory-api로 옮겨 갈 수 있다(오너, 2026-09-26). 그래서 discovery와 새 서비스 사이의 계약은 조회 route 하나로 좁게 둔다(§10-2).

---

## 5. 예제 — 대화 하나가 각 서비스에 남기는 것

아래 데이터는 설명을 위해 만든 것이다. id와 QID는 자리만 표시한다.

### 5-1. 대화

그룹 방, 참가자 A와 B.

```text
B: 요즘 뭐 마셔?
A: 지난 주말에 글렌드로낙 21 팔리아먼트 새로 나온 거 마셔 봤는데 셰리가 너무 세서 좀 별로였어
B: 난 셰리 캐스크 좋아해서 궁금하네. 친구가 그러는데 그거 벌써 품절이래
```

### 5-2. memory-api-v2가 저장하는 것 (지금 있는 것)

**대화 원문** — 세 메시지 전부, 방 단위로. bourbon-agent가 대화 검색을 할 때 찾는 대상이다.

**personal build** — 사용자마다 따로 만드는 그래프. A의 그래프와 B의 그래프에 **같은 대화가 각각** 들어간다.

```text
A의 그래프
  entity    "GlenDronach 21 Parliament"   source=NONE (Wikidata identity 없음), broader_qids=[]
  entity    "GlenDronach"                 source=WIKIDATA, knowledge_qid=Q…
  statement "A tried the new GlenDronach 21 Parliament; the sherry was too strong"
            statement_kind=experiential, speaker="A", subject_qid=null, created_at=<빌드 시각>

B의 그래프
  statement "A tried the new GlenDronach 21 Parliament; the sherry was too strong"
            statement_kind=experiential, speaker="A"          ← A의 경험이 B의 그래프에도 들어간다
  statement "B likes sherry cask whisky"   statement_kind=preference, speaker="B"
  statement "GlenDronach 21 Parliament is already sold out"   statement_kind=declarative
```

추천에 쓰기 어려운 점이 여기서 보인다 — A의 경험이 B의 그래프에도 있고, 새 병은 QID가 없어 상위 엔티티와의 연결이 조회되지 않으며, 시각이 빌드 시각이다(§6-2).

### 5-3. 새 서비스가 저장하는 것

**엔티티 레지스트리**

```text
entity_id                     label                                         parent         qid
wd:Q…(GlenDronach)            {ko: 글렌드로낙, en: GlenDronach}              []             Q…
rg:7f3a…                      {ko: 글렌드로낙 21 팔리아먼트,                   [wd:Q…]        null
                               en: GlenDronach 21 Parliament}
aliases(rg:7f3a…) = [글렌드로낙 21, GlenDronach Parliament, 팔리아먼트]
```

**경험 기록** — 메시지마다, 보낸 사람 기준으로.

```text
record  person  kind         entity     parent     topic        stance    observed_at (KST)   summary
r1      A       experienced  rg:7f3a…   [wd:Q…]    malt whisky  negative  2026-09-21 21:04    글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다
r2      A       prefers      rg:7f3a…   [wd:Q…]    malt whisky  negative  2026-09-21 21:04    글렌드로낙 21 팔리아먼트는 셰리가 너무 강해 입에 맞지 않았다
r3      B       prefers      —          []         malt whisky  positive  2026-09-21 21:05    셰리 캐스크 위스키를 좋아한다
```

- r1·r2는 A의 메시지 하나에서 나왔다. r2는 그 병 하나에 대한 평가로만 적는다 — "셰리가 강한 위스키는 싫어한다"처럼 넓히면 과장이다. r3은 B의 메시지에서 나왔다.
- 요약문에는 "지난 주말" 같은 상대 시점을 쓰지 않는다. 나중에 읽히면 틀린 말이 되고, 시점은 `observed_at`에 있다.
- `parent`는 기록을 쓸 때 레지스트리의 상위 엔티티를 복사해 둔 것이다. 상위 엔티티 경로는 이 컬럼으로 찾는다(§7-2).
- B의 "친구가 그러는데 품절이래"는 B가 겪은 것이 아니라 들은 사실이라 기록하지 않는다(들은 것을 어떻게 다룰지는 열린 항목 6).
- 각 기록에는 표에 없는 필드도 있다 — `summary_en`(영어 검색용 요약), `message_id`, `room_id`·`room_type`, `specificity`, `extractor_version`(§7-2).
- **원문은 없다.** 요약문은 보낸 사람 본인의 경험만 담고, 다른 참가자의 말은 담지 않는다.

### 5-4. 질문이 오면

요청자 R: "글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어"

```text
T1  need n0: kind=experienced, precision=exact, recency=recent,
             entity_mentions=[GlenDronach], condition="the newest GlenDronach release"
T2  topic: 몰트 위스키
T3  새 서비스:  "GlenDronach" → wd:Q…(GlenDronach)로 resolve
               상위 엔티티 경로: parent ∋ wd:Q…인 기록 r1·r2 (A)
               topic 경로: r1·r2 (A), r3 (B)
               텍스트 경로: r1의 summary_en이 "newest GlenDronach release"와 매칭
    관심 소스:  몰트 위스키 topic을 공개한 사람들
T4  A: experienced + 상위 엔티티 매칭 + 최근 + 요약문 매칭 → 1위
    B: prefers(종류 불일치), 엔티티 매칭 없음 → 아래
T6  "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다"
    + A의 기록 r1을 가리키는 evidence_ref
```

A가 R의 친구가 아니고 A의 agent가 public도 아니면 R은 A와 대화를 시작할 수 없으므로, A는 T3에서 빠진다(§9 T3).

---

## 6. 서비스들의 현재

코드에서 읽은 사실만 적는다. 추론이면 추론이라고 적는다.

### 6-1. bourbon-api — 메시지는 고쳐지지도 지워지지도 않는다

- **메시지는 INSERT-only다**: "`messages_*` — ... INSERT-only; rows are never updated or deleted"(`bourbon_api/messages/models.py:10-11`). 수정·삭제 route도 이벤트도 없다. 메시지 이벤트는 `bourbon.message_created`·`message_translated`·`message_artifacts_updated`다(`bourbon_api/messages/events.py:32, 48, 61`).
- `message_created` payload: `room_id`, `message_id`, `sender_id`, `sender_type`, `type`, `room_type`(`user_dm`·`agent_dm`·`group`)(`events.py:18-29`). 본문은 없다.
- 본문은 `GET /api/internal/rooms/{room_id}/agent-context`(`around=message_id`)로 다시 읽는다 — bourbon-agent가 memory에 적재할 때 쓰는 경로다(`bourbon_agent/memory/listeners.py:1-7, 93`, `api_internal_client/agent_context.py:59`).
- `bourbon.user_deactivated`(`bourbon_api/events.py:15`)는 **best-effort**로 발행된다 — "AMQP failure is logged but does not roll back the deactivation"(`bourbon_api/users/service.py:518-523`). 유실될 수 있다.
- agent DM 게이트는 "친구이거나 agent가 public"이다(`bourbon_api/rooms/service.py:401-414`). 요청자가 추천받은 사람과 대화를 시작하려면 둘 중 하나여야 한다.

### 6-2. memory-api-v2 — personal build는 이 목적과 맞지 않는다

personal build는 사용자 한 명의 대화 전체를 LLM 여섯 단계(extract·grounding scoring·judge·dedup·competence·classes)로 읽어 엔티티·statement 그래프를 만드는 배치다. 그 사용자 자신의 agent가 기억해 답하기 위한 데이터다. 추천에 쓰려면 다음이 맞지 않는다(§5-2의 예제).

| 추천에 필요한 것 | personal build | 근거 |
|---|---|---|
| **말한 사람 본인의** 경험 | 한 사용자의 그래프에 다른 참가자의 발화도 statement로 들어간다. `speaker`는 이름 문자열이다 | `memory/knowledge/personal/structs.py:196`; 빌드는 sender id로 본인/타인 참조를 따로 센다(`memory/knowledge/personal/scoring.py:101-141`) |
| 겪은 **시각** | statement의 `created_at`은 빌드 시각 `datetime.now(UTC)`이고 `valid_time`은 제거됐다. 빌드는 provenance로 메시지 시각을 읽어 salience에 쓰지만(`time_by_msg`) statement에 남기지 않는다 | `reconcile.py:317`, `structs.py:5`, `scoring.py:117-127` |
| 사용자 사이의 **엔티티 동일성** | 엔티티 id가 사용자마다 따로(`uuid5(owner_id:canonical)`). Wikidata identity가 없는 엔티티는 `broader_qids = []`이고, statement의 `subject_qid`·`object_qid`도 null이다 | `memory/utils/ids.py:27-34`, `pipeline/resolve.py:85-91, 121` |
| 사실은 빼고 경험·취향만 | `declarative`가 기본값이다 | `extract.py:304-306` |
| 원래 표현 | statement `text`는 "a concise English summary" | `extract.py:299` |

하나씩 고치면 그쪽 모델을 이쪽 목적에 맞게 비트는 일이 된다. **그래서 personal build는 건드리지 않는다.**

memory-api에서 이 설계가 쓰는 것은 둘이다.

- **공개 지식 resolve** — `POST /knowledge/resolve`(`api/routers/knowledge/router.py:240`). mention 1~32개(`text` ≤ 200, `context`는 300자로 잘림), 후보 `limit` ≤ 50, `language` en/ko/ja. 후보마다 `aliases_matched`, `instance_of`, `subclass_of`, `match{method: alias_exact|name|prose, score}`. corpus는 sitelink가 하나 이상인 Wikidata 항목 전부이고(`memory/knowledge/public/dump.py:119-127`), `match.score`는 **mention 사이에 비교할 수 없다**(`memory/knowledge/public/structs.py:127-129`). resolve는 공개 지식 route이지만, 새 서비스가 보내는 이름은 사용자의 메시지에서 나온 것이다("동네 그 바"의 이름 자체가 개인적일 수 있다). 그래서 **이름과 분야 이름만 보내고 메시지 텍스트는 `context`로도 보내지 않는다.** resolve는 mention을 digest로만 로그에 남긴다(`api/routers/knowledge/router.py:252-256`).
- **대화 저장** — bourbon-agent가 대화 검색으로 찾는 원문(`POST /{tenant}/search`)이 여기 있다. `POST /{tenant}/messages/lookup`은 메시지를 id로 찾되 `scope`가 허락하는 것만 돌려주고 `options.context`로 앞뒤 메시지를 붙인다(`api/routers/conversations/router.py:105-123`). 추천받은 agent가 원 메시지를 다시 읽는 자리다(§10-3).

memory-api에는 인증이 없다(`verify_token`은 있지만 어느 router도 쓰지 않는다, `api/depends/tenant.py:4-6`).

### 6-3. topic-api — 분야(KIND)만 받는다

- 카탈로그는 KIND만 받는다. 분류 프롬프트가 "product, company, ... and one numbered or dated release"를 topic이 아니라고 적는다(`topic/catalog_import/review_llm.py:34-41`). 사용자 신호로 노드를 더하는 경로는 없고, 없는 것이 정책이다(`docs/catalog-maintenance.md:3-4`).
- 스카치 위스키는 편집에서 빠졌고(`too_specific`), 하이랜드는 카탈로그 어디에도 없다(`data/catalog_seeds/reviewed/food-drink.yaml:5851-5899`).
- 사용자 topic은 persona의 preferences 레이어에서 추출된다. facet은 `knowledge`·`engagement`·`affinity`·`duration`·`recency` + `volume`. "해 봤다"에 해당하는 facet은 없다.
- `/search/topics`는 lexical 검색(정규화, 형태소 분석 없음, ko/en/ja label과 alias)이고, 카탈로그에 없는 이름은 빈 목록이다(`topic/catalog/graph.py:57-71`).

**topic-api에 제품 노드를 요청하지 않는다.** 엔티티는 새 서비스의 레지스트리가 맡는다. topic-api는 분야와 관심 소스로 남는다.

### 6-4. bourbon-agent

- 대화 검색은 LLM이 고르는 tool(`search_conversations`)이고, 원문 대화를 BM25로 검색한다. personal knowledge의 context route는 어디서도 부르지 않는다.
- **대화 검색의 범위는 방이다.** PERSONAL 방 밖에서 `search_conversations`가 닿는 것은 대부분 그 방 사람들이 함께 나눈 대화다(`bourbon_agent/agents/personal_agent/topic_memory.py:3-5`). 사용자가 다른 방에서 한 말은 요청자와의 방에서 보통 닿지 않는다.
- answerability gate가 없다. `recommend_agents` tool은 "추천해 달라"는 요청에만 불린다(예산 10초, `max_results=1`).
- agent가 agent에게 묻고 답을 합치는 코드는 없다. `moderator/__init__.py:12`가 `agent_recommender`를 "계획됨"으로 적어 두었을 뿐이다.

### 6-5. agent-discovery-api

- 타입 ① 파이프라인: expansion(LLM 1회) → grounding(topic-api 검색 + 모호할 때 disambiguation 1회) → 후보 조회 → 랭킹 → 조립. text→topic 단계 p50 1.77초 / p95 3.11초(disambiguation 게이트 on, `validation_results.md` §11-4), 요청 전체 p50 약 1.94초(추정).
- 미러: `visible_topic_rows`, `agents(… discoverable, agent_maturity …)`, `friends`, `departed_users`(R68).
- 카탈로그 복사본 3,174 topic(Wikidata 3,148 + 가상 노드 26, 가상 노드의 `source.qid`는 `N-…`). 위스키 계열 노드는 위스키·몰트·그레인·콘·아메리칸 위스키, 아일라·스페이사이드 싱글 몰트, 브랜드 예외 히비키·그랜츠다.

---

## 7. 새 서비스 설계

`bourbon-lived-knowledge-api`. **lived knowledge**는 "직접 살아 보며 얻은 앎"이라는 뜻이다 — 이 서비스가 저장하는 것은 사용자가 직접 겪은 경험, 취향, 요령, 사정이고, 사전·백과에 있는 사실과 대비된다. 일반 사실은 저장하지 않고, 전해 들은 것은 기본적으로 저장하지 않는다(전해 들은 사정을 `insider`로 둘지는 열린 항목 6).

### 7-1. 입력과 사전 필터

1. `bourbon.message_created`를 받는다(자기 큐, 자기 워커 — 이벤트 워커는 소비하는 repo가 소유한다).
2. **payload로 먼저 필터링한다**: `sender_type`이 사람이 아니면 버린다. `type`이 텍스트가 아니면 버린다(첫 버전).
3. agent-context로 그 메시지와 **앞의 몇 턴**을 다시 읽는다. 앞의 턴은 "그거" 같은 지시어가 무엇을 가리키는지 알기 위해서만 읽는다.
4. **사전 필터**: 1인칭 경험·취향·요령 표현이 있는가를 규칙 또는 작은 분류기로 본다. 대부분의 메시지는 여기서 끝난다. 사전 필터가 놓친 것은 추출에서도 놓치므로 느슨하게 둔다.
5. 통과한 메시지만 LLM 추출로 간다.

원문(메시지와 앞 턴)은 이 흐름 안에서만 메모리에 있고, 저장하지 않는다. 로그·예외·Sentry에도 남기지 않는다 — 남는 것은 id, 길이, 사전 필터 판정, reason code다.

### 7-2. 추출과 경험 기록

LLM 한 번에 메시지 하나(+ 앞 턴 문맥)를 넣고, **보낸 사람 본인에 관한** 경험 기록 0~N개를 받는다.

```text
lived_knowledge_records
  record_id           uuid
  person_id           uuid        보낸 사람 = 이 기록의 소유자
  kind                text        experienced | prefers | practiced | insider
  entity_id           text | null 엔티티 레지스트리 id (§7-3). 없으면 null
  parent_entity_ids   text[]      상위 엔티티 (브랜드·증류소). 쓸 때 레지스트리에서 복사하고, 엔티티가 없어도 채울 수 있다. 상위 엔티티 경로가 이 컬럼으로 찾는다
  topic_ids           text[]      카탈로그 topic (§7-4)
  stance              text | null positive | negative | mixed
  specificity         smallint    0~3. 이름·수치·장소·시점이 얼마나 구체적인가
  summary             text        보낸 사람의 경험 한두 문장 (규칙은 아래)
  summary_lang        text        요약문 언어 (메시지 언어를 따른다)
  summary_en          text        같은 요약의 영어판 — 검색용
  terms               text[]      엔티티 이름의 표기들 (en/ko/ja, 별칭) — 검색용
  observed_at         timestamptz 메시지 시각
  message_id          uuid        원 메시지
  room_id, room_type  —           출처. 기획 단계에서는 필터링에 쓰지 않는다. 공개 범위 조건이 붙을 자리(§12)
  extractor_version   text        추출 프롬프트·스키마 버전
  created_at          timestamptz
```

**추출 규칙**

- **보낸 사람 본인에 관한 것만.** 앞 턴에서 다른 사람이 한 말은 문맥이지 기록이 아니다. 선행 문서가 결정하지 못한 authorship 문제(한 사용자의 memory에 든 다른 사람의 말을 누구의 근거로 볼 것인가)가 여기서 대부분 해결된다.
- **사실 진술은 기록하지 않는다**(§1-1). 1인칭이어도 "그 증류소는 하이랜드에 있어"는 버린다.
- **사람은 엔티티가 되지 않는다.** 지인·동료·가족은 레지스트리에도 `terms`에도 남기지 않는다. "민수랑 갔다"의 민수는 요약문에서도 "친구와"로 쓴다.
- **요약문은 보낸 사람의 경험만, 과장 없이.** 한두 문장, 메시지 언어로. "한 모금 맛봤다"를 "마셔 봤다"로 올리지 않고, 병 하나에 대한 평가를 취향 전체로 넓히지 않는다. "지난 주말" 같은 상대 시점은 쓰지 않는다(시점은 `observed_at`). 다른 참가자의 이름·발언, 개인정보(전화번호·주소 등)는 옮기지 않는다. 원문을 인용하지 않는다. `summary_en`은 같은 내용의 영어판이다 — 질문 쪽 조건문이 영어라서(§9 T1) 검색이 같은 언어에서 만나게 하려는 것이다.
- 앞 턴으로도 대상을 알 수 없으면 엔티티 없이 기록한다(`entity_id = null`, 알 수 있는 상위 엔티티만).

**원문은 저장하지 않는다.** 추천받은 agent가 쓰는 것은 경험 기록과 요약문이고, 원 메시지는 그 방의 scope가 허락할 때만 대화 저장소에서 다시 읽는다(§10-3). 원문의 기준은 한 곳(bourbon-api와 memory-api)에만 있다.

### 7-3. 엔티티 레지스트리

경험 기록끼리, 그리고 질문과 경험 기록 사이에서 같은 대상을 같은 id로 부르기 위한 테이블이다. 모든 사용자의 기록이 함께 쓴다.

```text
entities
  entity_id       text     "wd:Q…" (Wikidata) 또는 "rg:<uuid>" (레지스트리가 새로 만든 id)
  label           jsonb    언어별 이름
  aliases         text[]   표기 변형 (누적)
  parent_ids      text[]   상위 엔티티
  qid             text | null
  created_at, merged_into
```

**새 서비스가 양쪽 resolve를 다 한다** — 추출할 때 기록의 엔티티를, 질문이 올 때 need의 엔티티를 같은 레지스트리로 resolve한다. 선행 문서에서는 질문 쪽(discovery)과 근거 쪽(memory-api 빌드)이 따로 resolve해서 어긋날 수 있었다(§3-2의 1번).

resolve 순서:

1. 이름을 정규화해 레지스트리의 label·alias에서 찾는다. 있으면 그 id.
2. 없으면 memory-api `/knowledge/resolve`로 QID를 찾는다. 판정은 **mention마다** 한다(점수는 mention 사이에 비교할 수 없다):
   - `match.method`가 `alias_exact` 또는 `name`인 후보만 쓴다.
   - 1위와 2위의 점수 비가 `registry.ambiguity_ratio`보다 가까우면 모호한 것으로 보고 QID를 붙이지 않는다.
   - 그렇지 않으면 1위를 `wd:` id로 등록하고, 이름을 alias에 더한다.
3. QID가 없으면(새로 나온 병, 동네 가게) `rg:` id를 새로 만들고, 문맥에서 잡힌 상위 엔티티(글렌드로낙)를 `parent_ids`에 넣는다.
4. 나중에 같은 대상이 QID로 resolve되면 `rg:` id를 `wd:` id로 합친다(`merged_into`). 기록은 조회할 때 합쳐진 id로 읽힌다.

질문 쪽 resolve는 1~2까지만 한다 — 질문 때문에 레지스트리에 새 id를 만들지 않는다. 질문의 이름이 레지스트리에도 Wikidata에도 없으면 `not_found`이고, 그 need는 topic 경로와 텍스트 경로로 찾는다(§9 T3). resolve가 답하지 않으면 `unavailable`이고 레지스트리에서만 찾는다.

레지스트리에는 엔티티의 **공개 이름**만 있다. 누가 그것을 겪었는지는 경험 기록에 있고 레지스트리에는 없다. 사람은 등록하지 않는다(§7-2).

### 7-4. topic

추출 LLM이 기록마다 분야 이름 1~3개("malt whisky", "whisky")를 함께 낸다. 새 서비스가 그것을 topic-api `/search/topics`로 찾아 `topic_ids`에 넣는다 — topic-api가 persona에서 topic을 붙이는 방식과 같다(가장 넓은 분야 이름을 늘 함께 낸다, `topic/persona_topics/stages.py:58-64`). 엔티티가 없는 기록도, 엔티티 매칭이 어긋난 질문도 topic으로 만난다.

### 7-5. 무효화·탈퇴·재추출

- **메시지는 고쳐지지도 지워지지도 않는다**(§6-1). 그래서 원문의 수정·삭제를 따라갈 일은 없다. 기록이 무효가 되는 경우는 둘이다 — 그 사람의 **탈퇴**, 그리고 서비스화 때 정할 **범위 밖으로 나가는 것**(방이나 동의, §12).
- **탈퇴는 R68과 같은 방식이다.** `bourbon.user_deactivated`를 받으면 그 사람의 기록을 전부 지우고 id를 남긴다. 그리고 **기록을 만들거나 바꾸는 모든 쓰기 트랜잭션이 첫 문장에서 그 id를 확인한다** — 추출 결과 쓰기, 백필, 재추출, resolve 재시도 뒤의 갱신 모두. 메시지는 지워지지 않으므로 탈퇴한 사람의 메시지는 원천에 남아 있고, 확인 없는 백필은 그 기록을 되살린다.
- **탈퇴 이벤트가 유실될 수 있다**(`user_deactivated`는 best-effort, §6-1). 유실되면 탈퇴한 사람의 기록이 남는다. 두 겹으로 막는다 — discovery가 경험 소스의 후보를 자기 `departed_users`와 `agents`로 한 번 더 필터링하고(§9 T3), bourbon-api에 믿을 수 있는 탈퇴 확인 방법을 요청한다(§15 요청 1). bourbon-api의 내부 사용자 조회는 탈퇴자를 빼고 답하지만 "absence must not be read as a deletion signal"이라고 적어 두었으므로, 거기 없다는 것을 탈퇴로 읽을 수는 없다.
- **재추출**: `extractor_version`이 바뀌면 원천에서 다시 읽어 만든다. 원문을 저장하지 않은 대가이고, 백필 경로를 처음부터 둔다. 백필도 위의 탈퇴 확인을 거친다.

### 7-6. 저장소 — PostgreSQL을 권한다

새 서비스가 하는 일을 기준으로 두 후보를 비교한다.

| 필요한 것 | PostgreSQL | OpenSearch |
|---|---|---|
| 탈퇴 확인을 쓰기 트랜잭션의 첫 문장에 두기(§7-5) | 그대로 된다. discovery의 R68 구현(advisory lock + 테이블)을 같은 모양으로 쓴다 | 트랜잭션이 없다. 확인과 쓰기 사이의 경쟁을 따로 막아야 한다 |
| 기록 ↔ 레지스트리 ↔ 사람 조인, `rg:`→`wd:` 합치기 | 조인과 트랜잭션으로 자연스럽다 | 비정규화해 두고 합칠 때 재인덱싱 |
| `entity_id`·`parent_entity_ids`·`topic_ids`로 찾기 | 배열 컬럼 + GIN 인덱스 | keyword 필드 term 쿼리 |
| 경로마다 사람별 상위 K명 | window function(`row_number() over (partition by …)`) | terms aggregation + top_hits |
| 요약문 텍스트 검색 | `summary_en`에 영어 full-text(`tsvector`) + 이름 표기에 `pg_trgm` | BM25, 언어별 analyzer(nori·kuromoji) |
| 규모 | 사용자 10만 × 사용자당 기록 수백 = 수천만 행까지 무리 없다(추론, 0단계에서 기록 수를 잰다) | 더 큰 규모에 유리 |
| 운영 | discovery와 같은 방식(공용 RDS에 DB 하나, alembic) | memory-api와 같은 AOSS. 탈퇴 기록 같은 트랜잭션이 필요한 데이터는 결국 PostgreSQL에도 두게 되어 저장소가 둘이 된다 |

**PostgreSQL을 권한다.** 가장 중요한 요구 — 탈퇴한 사람의 기록이 되살아나지 않게 하는 것 — 가 트랜잭션에 기대고, 데이터가 관계형이다. 텍스트 검색은 `summary_en`을 두어 영어 하나로 모았기 때문에 PostgreSQL의 영어 full-text로 충분하다고 본다. 한국어 원문 요약(`summary`)은 보여 주기용이고 검색하지 않는다.

**다시 볼 조건**: 0·2단계에서 요약문 검색의 품질이 부족하면(§13-2) — 예를 들어 영어 번역이 제품명·지명을 흔들어 매칭이 떨어지면 — 검색만 OpenSearch로 옮기고 기록의 기준은 PostgreSQL에 둔다. 새 서비스가 memory-api로 옮겨 가는 날에도 같은 판단을 다시 한다.

### 7-7. 조회

discovery 한 곳을 위한 조회 route 하나를 둔다(§10-2). **discovery가 경험 기록을 복제해 두지 않는다** — 새 서비스는 우리가 만들고 이 조회를 위해 설계하므로, 선행 문서의 폴링 루프·manifest cursor·reconciliation이 필요 없다. 대신 추천 요청마다 호출하는 런타임 의존성이 되고, 새 서비스가 답하지 않을 때의 동작을 정한다(§11).

### 7-8. 비용

- LLM은 **사전 필터를 통과한, 사람이 보낸 메시지**마다 1회다. 물량은 모른다 — 하루 메시지 수 × 사람 발신 비율 × 사전 필터 통과율로 추정하고, dev에서 통과율부터 잰다(§13-2).
- 추출도 e3llm을 쓴다. 추천 요청과 같은 proxy를 쓰면 배치 부하가 추천 요청의 꼬리 지연 시간을 늘릴 수 있다. 추출은 우선순위가 낮은 별도 한도(동시성 상한)로 돌리는 것이 맞다고 보고, 가능한지는 e3llm 쪽에 묻는다(§15 요청 13).

---

## 8. 두 소스

| | 관심 소스 | 경험 소스 |
|---|---|---|
| 데이터 | discovery의 `visible_topic_rows` | 새 서비스의 `lived_knowledge_records` |
| 어디서 오나 | topic-api가 persona의 preferences에서 뽑은 topic | 새 서비스가 메시지에서 뽑은 경험 기록 |
| 아는 것 | "이 분야에 관심을 드러냈다"와 관심 강도 | "이것을 겪었다·좋아한다·해 봤다·안다"와 언제, 어땠는지 |
| 찾는 기준 | topic | 엔티티, 상위 엔티티, topic, 요약문 텍스트 |
| 지금 있나 | 있다(타입 ①②③이 쓰는 것) | 새로 만든다 |
| 공개 범위 | topic tier와 `discoverable`을 쿼리 안에서 건다(R17) | 기획 단계에서는 걸지 않는다(§12) |

관심 소스는 경험 소스가 없거나 답하지 않을 때의 폴백이면서, 경험 소스가 놓친 사람을 찾는 보조 경로다. 관심 소스만으로 추천된 사람은 "관심이 있는 사람"으로만 소개한다(§9 T6).

---

## 9. 추천 설계 (discovery)

### T0. 트리거 (bourbon-agent)

`recommend_agents`의 트리거를 "소유자의 질문에 사람의 경험이 필요할 때"로 넓히거나 두 번째 tool을 둔다. 추가 LLM 호출은 없다. 판단이 틀리는 방향은 둘인데, **사람이 필요한 질문에 모델이 사전학습 지식으로 답해 버리고 tool을 부르지 않는 쪽이 더 위험하다.** 첫 실험부터 호출률(사람이 필요한 질문에서 tool이 실제로 불린 비율)을 잰다(§13-4).

"이번 신상"처럼 요청자가 이름을 말하지 않았을 때, 방에서 그 이름이 나왔으면 `context`에 넣어 넘기는 것이 가장 싸고 정확한 보정이다. bourbon-agent 쪽 프롬프트 설계의 문제다(§15 요청 11).

### T1. 질문 분석 — expansion의 형제 프롬프트

타입 ①의 expansion은 "개념 그룹 0~3개, 그룹마다 검색어(probe)"를 낸다. need는 그 그룹에 필드를 더한 것이다.

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

- `people_needed`: 질문이 사람의 경험을 필요로 하는가. `false`면 이후 단계를 돌지 않고 `mode: none`, `empty_reason: answerable_without_people`.
- `kind`: `experienced` | `prefers` | `practiced` | `insider` | `null`(종류 무관). 경험 기록의 `kind`와 같은 값이다.
- `precision`: `exact` | `related`(§3-3 규칙 5).
- `recency`: `recent` | `null`. discovery가 설정 레지스터의 값으로 `recency_days`로 바꿔 새 서비스에 넘긴다.
- `entity_mentions`: 질문이 이름으로 가리킨 대상 0~2개. `text`는 영어 정식 이름, `as_written`은 질문에 쓰인 표기. 분야 이름은 넣지 않는다. 모델이 모르는 것("이번 신상")은 지어내지 않는다.
- `condition`: topic·엔티티에 담기지 않는 조건을 영어 한 구절로. 요약문(`summary_en`) 매칭에 쓴다(T3). 질문에서 나와 새 서비스로 가는 텍스트는 이것과 `entity_mentions`뿐이다.
- `probes`는 지금처럼 분야 이름이다.

규칙:

- 호출은 한 번이다. **타입 ①의 프롬프트는 한 글자도 바꾸지 않고** 형제 프롬프트를 새로 둔다. 확장 프롬프트와 grounding 게이트는 서로를 전제로 쓰여 있고, 둘이 어긋나면 422가 크게 움직인다 — R60의 실측에서 게이트를 끈 쪽은 질문의 26%가 422였다.
- need 상한은 3.
- 스키마 검증에 실패한 필드는 후보가 넓어지는 쪽으로 폴백한다 — `people_needed=true`, `importance=required`, `kind=null`, `precision=related`, `recency=null`, `entity_mentions=[]`, `condition=null`. `degraded`에 `need_fields_defaulted`.
- 질문 원문은 로그·예외·Sentry에 남기지 않는다(불변식 7).

**대안 — 질문 분석을 bourbon-agent의 tool 인자로 옮기기.** bourbon-agent의 모델은 recommend tool을 부를 때 이미 질문을 읽고 있다. tool 인자에 need 필드(`people_needed`, `kind`, `precision`, `recency`, `entity_mentions`, `condition`, 분야 이름)를 넣게 하면 discovery의 T1 LLM 호출이 없어진다.

| | discovery의 T1 (이 문서의 기본) | bourbon-agent의 tool 인자 |
|---|---|---|
| 지연 시간 | 요청 경로의 가장 긴 단계(p50 1~2초) | 그만큼 줄어든다. 턴 안의 tool call 인자가 조금 길어질 뿐이다 |
| LLM 호출 | 질문당 1회 더 | 없음 |
| 추출 품질 관리 | 우리 프롬프트, 우리 테스트, 우리가 측정 | bourbon-agent의 tool 설명과 그쪽 모델에 기댄다. 필드가 틀려도 우리가 고칠 수 없다 |
| 계약 | 요청은 질문 원문 | 요청이 구조화된 need 목록이 된다. 계약이 무거워지고, 필드가 늘 때마다 두 repo가 함께 바뀐다 |
| 폴백 | T1이 실패하면 질문 그대로 | 인자가 비거나 잘못되면 discovery가 T1을 돌리는 경로가 여전히 필요하다 |

1단계는 discovery의 T1로 시작하고, 지연 시간이 문제가 되면 이 대안을 검토한다. 두 방식을 같은 질문 세트로 비교할 수 있게, 요청이 need 목록을 받으면 T1을 건너뛰는 입구를 처음부터 열어 둘지는 열린 항목 18이다.

### T2. topic 찾기

타입 ①의 grounding 그대로 — probe로 topic-api 검색, 규칙으로 하나를 고르고, 모호할 때만 disambiguation 1회. 결과는 need마다 topic 하나 또는 없음.

엔티티는 discovery가 resolve하지 않는다. `entity_mentions`를 이름 그대로 새 서비스에 넘기고, 새 서비스가 경험 기록과 **같은 레지스트리로** resolve한다(§7-3).

| topic | 엔티티 이름 | 이 need는 |
|---|---|---|
| 찾음 | 있음 | 모든 경로로 후보를 찾는다 |
| 찾음 | 없음 | topic·텍스트 경로로 |
| 못 찾음 | 있음 | 엔티티·텍스트 경로로(경험 소스만) |
| 모호 | 있음 | topic을 쓰지 않고 엔티티·텍스트 경로로(§3-3 규칙 1·3) |
| 못 찾음 | 없음 | required면 422 `grounding_failed` |
| 모호 | 없음 | required면 422 `grounding_ambiguous`, optional이면 그 need를 빼고 `degraded`에 `need_dropped` |

topic-api가 답하지 않으면 503(타입 ①과 같음).

### T3. 후보 모으기

**관심 소스 — discovery DB.** `visible_topic_rows`에서 need의 topic(+ `catalog_edges`로 펼친 하위 topic)을 공개한 사람. topic-api `score_detail`의 `knowledge` facet과 `confidence`를 컬럼으로 더한다.

**경험 소스 — 새 서비스 조회 1회**(§10-2). need마다 topic id 목록(discovery가 하위 topic까지 펼쳐서), 엔티티 이름, `kind`, `recency_days`, `condition`을 넘기면, 새 서비스가 네 경로로 경험 기록을 찾아 사람별로 묶어 돌려준다.

```text
엔티티 경로      entity_id = resolve된 엔티티 (+ 합쳐진 id)             precision=exact일 때의 주 경로
상위 엔티티 경로  parent_entity_ids ∋ resolve된 엔티티                   하위 엔티티(예: QID가 없는 신제품)를 겪은 사람
topic 경로       topic_ids ∋ need의 topic들                            엔티티가 어긋나거나 없을 때
텍스트 경로      summary_en·terms가 condition·엔티티 이름과 매칭         다른 경로가 모두 빗나갔을 때
```

- 경로마다 상위 K명(설정 레지스터, 초기 25)을 뽑아 합친다. 전체 점수로 상위 N명을 자르지 않는다 — 소수의 엔티티 경험자가 다수의 분야 경험자에 묻히지 않게.
- `kind`와 `recency`는 **필터링 조건이 아니라** 경로 안의 순위 조건이다. 종류가 다른 기록도 후보가 되되 낮은 순위로 — T1의 `kind` 판정이 틀렸을 때도 후보가 사라지지 않게.
- 네 경로의 모든 기록에 `condition`과 `terms`(resolve된 엔티티의 표기들)로 `summary_en` 매칭 순위를 붙인다. **"이번 신상" 같은 조건은 여기서만 반영된다.**
- 텍스트 경로가 있어서, 엔티티를 찾지 못했거나(`not_found`) topic이 없는 need도 후보를 얻는다(§3-3 규칙 1).
- 응답은 사람별로: 경로별 기록 수, 가장 잘 맞은 기록 몇 개(`record_id`, `kind`, `stance`, `specificity`, `observed_at`, 매칭 순위, 요약문), need별 `complete` 여부.

**경험 소스의 사람은 discovery가 다시 필터링한다.**

- `person_id`를 `agents.owner_user_id`로 조인해 `agent_id`를 얻는다. 조인되지 않으면 뺀다.
- `departed_users`에 있으면 뺀다.
- **요청자가 대화를 시작할 수 있는 사람만** 남긴다. bourbon-api의 agent DM 게이트는 "친구이거나 agent가 public"이다(§6-1). discovery 미러로는 `friends`(불변식 2의 그 집합) 또는 `agents.discoverable`이다.

이 마지막 조건은 기획 단계에서 빼 둔 동의 문제가 아니다 — 요청자가 말을 걸 수 없는 사람을 추천하면 그 추천은 틀린 것이다.

두 소스의 합집합을 전체 상한 N(설정 레지스터, 초기 50)으로 자른다. 자르는 규칙은 deterministic하다(같은 입력이면 같은 결과) — required need마다 최소 자리를 먼저 채우되 그 안에서 **경험 소스의 엔티티·상위 엔티티 경로 후보를 먼저**, 남은 자리를 전체 점수 순으로, 동점은 `(score desc, agent_id asc)`.

**coverage 상태** — need마다 후보의 근거 단계. 순위와 폴백에 쓰고 응답에는 싣지 않는다(§10-1).

```text
prior_only       관심 소스만 — 이 분야에 관심을 드러냈다
record_topic     경험 소스의 topic 경로 — 이 분야에서 무언가를 겪었다·좋아한다·해 봤다·안다
record_entity    경험 소스의 엔티티·상위 엔티티 경로 — 바로 이것(또는 그 상위)을 겪었다·…
record_match     요약문이 need의 조건·엔티티 이름과 맞는 기록이 있다 (텍스트 경로로만 들어온 사람도 여기)
```

`record_match`도 "답할 수 있다"가 아니라 "그런 경험을 말한 적이 있다"다.

### T4. 순위 — deterministic

feature(설정 레지스터에 올린다):

- required need coverage(통과 조건)
- coverage 상태별 가중치: `record_match` > `record_entity` > `record_topic` > `prior_only`
- 종류 일치: 기록의 `kind` = need의 `kind`
- 엔티티 매칭의 종류: 바로 그 엔티티 1, 상위 엔티티 0.5. 가중치는 `precision`이 정한다(`exact`면 크다)
- 최근성: `recency: recent`인 need는 `observed_at`의 반감기 감쇠를 크게, 아니면 작게
- `specificity`, 같은 need에 대한 기록 수의 log
- 요약문 매칭의 **need 안에서의 순위**(점수 자체는 need끼리 비교하지 않는다)
- 관심 소스: `knowledge` facet, `confidence`, tier
- 두 소스가 같은 사람을 가리키는가, `agent_maturity`

**곱셈식을 쓰지 않는다.** 곱하면 관심 소스만 있는 후보는 0이 되고, 새 서비스가 답하지 않으면 전원이 0이 된다. coverage 상태별 가중 합이고, 측정되지 않은 feature는 없는 것으로 둔다(discovery의 `Features.present`가 이미 그 구분을 한다). 구현은 타입 ①의 `Ranker.features/score`와 같은 모양이다.

한 사람이 모든 required need를 채우면 한 명 추천이 두 명 조합보다 우선한다.

**선택 단계 — LLM 리랭커.** 기본은 위의 가중 합이고, 요청 경로에서 후보를 고르는 LLM은 없다. 다만 조건이 얽힌 질문에서는 가중 합이 약할 수 있다. 예를 들어 "셰리 싫어하는 사람한테 맞는 스페이사이드 추천해 줄 사람?"은 취향의 방향(셰리를 싫어한다)과 대상(스페이사이드)이 얽혀 있어, 요약문 텍스트 매칭과 가중 합만으로는 "셰리를 싫어하면서 스페이사이드를 많이 마셔 본 사람"을 위로 올리기 어렵다. 그런 경우를 위해 T4 뒤에 선택 단계를 둘 수 있다 — 가중 합 상위 10~20명의 요약문을 need와 함께 LLM에 넣어 다시 정렬한다.

| | 가중 합만(기본) | + LLM 리랭커 |
|---|---|---|
| 조건이 얽힌 질문의 정확도 | 약하다 | 좋아질 가능성이 크다(추론) |
| 지연 시간 | 요청 p50 약 2~2.5초(추정) | +1~2초 |
| 비용 | 질문당 LLM 1~2회 | 1회 더 |
| 재현성·설명 | deterministic, decision log로 설명된다 | 같은 입력에도 순위가 흔들릴 수 있다. decision log에 리랭커 전후 순위를 둘 다 남겨야 한다 |
| 데이터 경계 | 후보의 요약문이 LLM에 가지 않는다 | 다른 사람들의 경험 요약이 요청 경로의 LLM으로 간다(§12) |

**처음에는 붙이지 않는다.** 2단계의 합성 대화 측정에서 조건이 얽힌 질문의 precision이 부족할 때 붙인다(§13-3). T4 뒤에 얹는 단계라 나중에 붙여도 앞 단계의 구조는 바뀌지 않는다. 붙이더라도 리랭커가 실패하거나 시간을 넘기면 가중 합 순위를 그대로 쓴다. 붙일지와 조건은 열린 항목 19다.

### T5. 두 사람 조합 — deterministic

한 명으로 부족할 때만. 최대 2명, 모든 required need가 기준 이상, 각자 상대가 못 채우는 need를 하나 이상 채운다. need 최대 3, 후보 수십 명이면 조합은 수백 개다. LLM을 쓰지 않는다.

### T6. 응답 조립 — 요약문 기반 이유와 `evidence_ref`

- **추천 이유는 요약문으로 만든다**(오너, 2026-09-26: 요약문을 저장한다). 템플릿 `"{need 이름} 관련 경험({observed_at의 연월}): {요약문}"`에 가장 잘 맞은 기록의 요약문을 그대로 넣는다 — "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다". 관심 소스만 있는 사람은 "{need 이름}에 관심이 있는 agent입니다."
- LLM으로 이유 문장을 새로 쓰지 않는다. 요약문은 추출 때 규칙(§7-2)으로 이미 다듬어졌다.
- 기록 하나의 요약문만 쓴다. 여러 기록을 이어 붙여 그 사람의 프로필처럼 보이게 하지 않는다.
- 사람마다 근거 기록의 `evidence_ref` 1~3개를 응답 때 발급해 붙인다. 요청자의 화면에는 쓰지 않고, bourbon-agent가 실행할 때 추천받은 agent에게만 넘긴다(§10-3).

---

## 10. API 초안

### 10-1. discovery — `POST /api/internal/svc/agent-discovery/recommend/knowledge`

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

`question`과 `context`는 T1의 LLM에만 쓴다. 새 서비스로 가는 것은 T1이 만든 `entity_mentions`·`condition`과, discovery가 만든 topic id 목록·`kind`·`recency_days`뿐이다. 로그에는 `question_digest`·`question_chars`·`context_chars`만 남는다.

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
     "reason": "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다",
     "evidence_refs": ["opaque…"]}
  ],
  "empty": false,
  "degraded": []
}
```

- `mode`: `single | group | none`. `none`일 때 `empty_reason`: `answerable_without_people`(T1), `nobody_covers`(required need를 아무도 못 채움).
- `needs[].label`은 엔티티가 resolve됐으면 레지스트리의 공개 이름, 아니면 topic의 카탈로그 이름.
- **`agents[]`는 새 wire 모델 `KnowledgeRecommendedAgent`다.** 타입 ①②③의 `RecommendedAgent`는 `matched_topics`·`signals`가 필수다. 공통 필드(`agent_id`·`owner_user_id`·`position`)만 공유한다.
- `covers[]`는 need id 목록이고 coverage 상태는 싣지 않는다. `confidence`도 싣지 않는다(calibration 전).
- `evidence_refs`는 opaque 문자열이다. 요청자 UI에 쓰지 않는다(§10-3).
- `degraded[]`: `expansion_partial`, `need_fields_defaulted`, `need_dropped`, `entity_resolution_unavailable`, `experience_unavailable`, `experience_incomplete`.

### 10-2. 새 서비스 — discovery가 부르는 조회

```http
POST /api/internal/svc/lived-knowledge/candidates
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
     "entity": {"entity_id": "wd:Q…", "label": {"ko": "글렌드로낙", "en": "GlenDronach"}, "state": "resolved"},
     "complete": true}
  ],
  "people": [
    {"person_id": "…", "needs": [
      {"need_id": "n0",
       "paths": {"entity": 0, "parent": 1, "topic": 2, "text": 1},
       "records": [
         {"record_id": "…", "kind": "experienced", "stance": "negative", "specificity": 3,
          "observed_at": "2026-09-21T12:04:00Z", "match_rank": 1,
          "summary": "…", "evidence_ref": "opaque…"}
       ]}
    ]}
  ]
}
```

- `entity.state`: `resolved` | `ambiguous` | `not_found` | `unavailable`(resolve 장애, 레지스트리에서만 찾음) | `none`(엔티티 이름 없음). `ambiguous`·`not_found`면 엔티티·상위 엔티티 경로를 돌지 않고 topic·텍스트 경로만 돈다(§3-3 규칙 3).
- 요청자 본인은 뺀다. 탈퇴한 사람은 기록이 없다(§7-5).
- `condition`은 새 서비스의 로그에 원문으로 남기지 않는다 — digest와 길이만.
- 이 route가 discovery와 새 서비스 사이의 **계약 전부**다. 새 서비스가 memory-api로 옮겨 가도 이 모양은 그대로 둔다.

### 10-3. `evidence_ref` — 추천의 근거를 대화의 출발점으로

- `evidence_ref`는 응답 때 `record_id`(와 버전)를 서명해 만드는 opaque 토큰이다. 저장하지 않는다. 요청자는 누구의 어떤 기록인지 알 수 없다.
- bourbon-agent가 추천을 실행할 때 추천받은 agent의 턴에 `evidence_ref`를 넘긴다(요청자가 수락한 뒤에 실행할지 자동으로 실행할지는 열린 항목 12). 추천받은 agent는 새 서비스에 이것을 제시해 **그 경험 기록 — 종류, 엔티티, 시각, 요약문 — 을 받고, 거기서 답을 시작한다.**
- **원 메시지는 기본으로 읽지 않는다.** 원 메시지는 대개 요청자가 없던 방에서 나왔고, bourbon-agent의 대화 검색 범위는 방이다(§6-4). 그 메시지와 앞뒤를 요청자와의 방에서 읽으면 다른 방의 대화가 유출된다. 원 메시지가 필요하면 memory-api `POST /{tenant}/messages/lookup`을 **지금 방의 scope로** 부르고, 그 scope에서 읽을 수 있을 때만 쓴다. 대부분은 요약문에서 답을 시작하고, 더 자세한 것은 추천받은 agent가 평소처럼 대화 검색으로 찾는다. 요약문은 그 사람 본인의 경험만 담도록 추출했으므로(§7-2) 다른 사람의 말이 새는 경로가 아니다.
- **`evidence_ref`로 기록을 조회할 수 있는 것은 기록 소유자의 agent뿐이어야 한다.** 그런데 지금 내부 서비스 사이에는 호출자 인증이 없고, bourbon-agent 한 프로세스가 모든 agent를 대신해 말한다 — "호출한 agent의 소유자"는 호출자가 주장하는 값일 뿐이다. 기획 단계에서는 다른 내부 route와 같은 신뢰 범위 안에 두고, 서비스화 전에 내부 호출 인증이 먼저 있어야 한다(§12).
- 기대하는 효과(추론, §13-4로 잰다): 추천받은 agent가 검색어를 잘못 써서 근거를 못 찾는 실패가 줄고, 추천의 근거와 대화의 출발점이 같은 기록이라 "둘이 다른 데이터를 봐서 생긴 오차"가 줄어든다.

---

## 11. 실패와 degradation

discovery:

| 실패 | 동작 |
|---|---|
| T1 LLM 실패 | 타입 ①과 같이 질문 그대로 폴백 + `expansion_partial`. `people_needed=true`, `entity_mentions=[]` — 후보가 넓어지는 쪽 |
| need 필드 스키마 위반 | 넓어지는 쪽으로 폴백 + `need_fields_defaulted` |
| `people_needed=false` | `mode: none`, `empty_reason: answerable_without_people`. 판단이 틀리면 사람이 필요한 질문에 추천이 안 나간다 — 호출률과 함께 잰다 |
| topic 못 찾음, 엔티티 이름 있음 | 경험 소스로만 |
| topic·엔티티 이름 둘 다 없음 | required면 422 `grounding_failed` |
| topic 모호, 엔티티 이름 있음 | topic을 쓰지 않고 엔티티·텍스트 경로로 |
| topic 모호, 엔티티 이름 없음 | required면 422 `grounding_ambiguous`, optional이면 빼고 `need_dropped` |
| topic-api 검색 불가 | 503 |
| 새 서비스 timeout·5xx | 관심 소스만으로 응답 + `experience_unavailable`. 전원 `prior_only`, 이유는 관심 문구, `evidence_ref` 없음. **관심 소스로 볼 것이 없는 required need(topic을 못 찾은 need)가 있으면 503** — 못 본 것이지 없는 것이 아니다(불변식 8). timeout은 설정 레지스터 값이고, 새 route 전체 deadline(bourbon-agent의 10초 아래) 안에 든다 |
| resolve 장애(새 서비스 안) | 레지스트리에서만 찾고 계속 + `entity_resolution_unavailable` |
| 새 서비스 일부 need `complete=false` | 받은 것으로 순위 + `experience_incomplete`. required need가 불완전하면 두 사람 조합을 내지 않는다 |
| 엔티티 `ambiguous`·`not_found` | topic·텍스트 경로로. degraded 아님(요청에 대한 판단) |
| 새 서비스가 요청자를 돌려줌 | 그 항목은 버리고 로그. 계약 위반이라 알람 |
| 경험 소스의 사람이 `agents`에 없거나 `departed_users`에 있음 | 뺀다(§9 T3). 탈퇴 이벤트 유실에 대한 두 번째 방어 |
| required need를 아무도 못 채움 | `mode: none`, `empty_reason: nobody_covers` |
| 실행 시 `evidence_ref`로 기록이 조회되지 않음 | 추천받은 agent가 평소처럼 대화 검색으로 |

새 서비스:

| 실패 | 동작 |
|---|---|
| agent-context 재조회 실패 | 재시도(discovery 워커와 같은 모양) 뒤 버리고 로그. 백필이 채운다 |
| 추출 LLM 실패 | 같음 |
| resolve 실패 | 엔티티를 QID 없이 기록하고 나중에 다시 resolve |
| 탈퇴한 사람에 대한 쓰기(늦게 온 `message_created`, 백필, 재추출) | 트랜잭션 첫 문장의 확인에서 거절(§7-5) |
| `user_deactivated` 유실 | 기록이 남는다. discovery의 재필터링이 막고, 믿을 수 있는 확인 방법을 요청한다(§15 요청 1) |

---

## 12. 기획 단계에서 빼 둔 것과 남겨 둔 자리

오너(2026-09-26): 새 타입의 기획이므로 공개 범위는 빼 두고 해 본 뒤, 실 서비스화할 때 고려한다.

**빼 둔 것** — 설계와 실험에서 조건을 걸지 않는다.

- 방의 공개 범위(DM·비공개 방에서 한 말을 기록할 것인가)
- 추천 대상이 되는 것에 대한 동의(`consultable` 같은 opt-in)
- 요약문이 요청자에게 보이는 것에 대한 동의
- LLM 리랭커를 붙인다면(§9 T4), 후보들의 요약문이 요청 경로의 LLM으로 가는 것
- topic tier(`public`/`friends`)와 경험 소스의 관계

**빼 둔 결정이 이 기능의 가치를 좌우한다.** 경험 기록이 가장 많이 나올 곳은 아마 사용자가 자기 agent와 나눈 대화(`agent_dm`)일 것이다 — "나 어제 이거 마셨는데" 같은 말을 사람보다 자기 agent에게 더 편하게 할 것이라고 본다(추론). 그리고 그곳이 공개 범위 문제가 가장 큰 곳이다. 0단계에서 기록 수를 방 종류별로 나눠 재면(§13-2) 이 결정이 얼마나 무거운지 미리 보인다.

**빼 두지 않는 것** — 요청자가 그 사람과 대화를 시작할 수 있는가(agent DM 게이트, §9 T3)와 탈퇴. 둘 다 동의가 아니라 추천이 맞는지의 문제다.

**남겨 둔 자리** — 나중에 필터를 붙일 때 구조를 고치지 않게.

- 기록마다 `room_id`·`room_type`(§7-2). 방 범위 조건은 이 필드 위의 필터다.
- 기록마다 `person_id`(보낸 사람). 동의 조건은 이 필드와 동의 미러의 조인이다. 미러는 fail-closed로 둔다 — 값을 모르면 뺀다.
- 요약문 이유와 관심 문구를 가르는 분기(T6). 요약문이 보이는 것에 대한 동의가 없으면 관심 문구로 떨어진다.
- 관심 소스는 지금처럼 topic tier와 `discoverable`을 쿼리 안에서 건다(R17). 기존 타입과 같은 노출이라 빼 둘 이유가 없다.

**실험의 경계**(이 문서의 판단): 빼 둔 조건이 정해지기 전까지 실제 사용자 데이터를 production에 적재하거나 추천을 내보내지 않는다. 실험은 dev와 합성 대화에서 한다. `evidence_ref`로 기록을 조회하는 route의 호출자 인증(§10-3)도 서비스화 전에 있어야 한다.

**authorship**: 선행 문서의 가장 큰 열린 질문(한 사용자의 memory에 든 다른 사람의 말을 그 사용자의 근거로 셀 것인가)은 **보낸 사람 기준 저장으로 대부분 해결된다** — 기록은 말한 사람의 것이다. 남는 것은 전해 들은 것을 다시 말하는 경우다("친구가 그러는데 그 병 별로래"). 추출 규칙은 이것을 말한 사람의 `experienced`로 기록하지 않는다. `insider`로 볼지는 실험으로 정한다(열린 항목 6).

---

## 13. 관측과 평가

### 13-1. decision log (discovery)

원문 없이:

```text
question_digest, question_chars, context_chars
people_needed, needs_total, needs_required, need_fields_defaulted
needs_with_topic, needs_with_entity, entity_state_by_need
candidates_by_path          interest, entity, parent, topic, text, 그리고 겹침
final_by_path               최종 상위 k명이 어느 경로로 들어왔는가
coverage_states             need × 상위 agent의 상태별 수
experience_status           ok | unavailable | incomplete
single_sufficient, group_size, covered_required
degraded[], empty_reason
latency_ms.{expand, ground, experience, rank, group, assemble, total}
```

**불변식 7의 범위를 넓힌다.** 사용자의 글 목록(topic_text, context, owner_note)에 `summary`·`summary_en`·`reason`·`condition`을 더한다 — 로그·예외·Sentry·decision log에 원문으로 싣지 않는다. decision log는 `reason`을 읽지 않는다(`discovery/journal.py`가 `matched_topics`를 읽지 않는 것과 같다, `journal.py:20-23`). 같은 규칙이 새 서비스와 bourbon-agent의 로그에도 적용된다.

`final_by_path`가 핵심 운영 지표다. 엔티티 질문인데 topic 경로로만 들어온 사람이 최종 상위에 자주 있으면 엔티티 resolve가 어긋나고 있다는 신호이고, 합집합(§3-3 규칙 1)이 없었다면 놓쳤을 사람이다.

### 13-2. 먼저 재는 것 (0단계)

1. **추출 정밀도** — dev 메시지 샘플에서 기록이 (가) 보낸 사람 본인의 것인가 (나) 사실이 아니라 경험·취향·요령·사정인가 (다) 요약문이 과장하지 않는가. 사람이 라벨을 단다.
2. **사전 필터 recall** — 사전 필터가 버린 메시지 중 기록할 것이 있었던 비율. 추출 전체의 상한이다.
3. **엔티티 resolve 일치** — 같은 대상을 가리키는 기록이 같은 id로 모이는 비율, `rg:` id가 나중에 `wd:`로 합쳐지는 비율, `ambiguous` 비율.
4. **요약문 검색 품질** — 한국어 메시지의 `summary_en`이 제품명·지명을 보존하는가, 영어 조건문으로 찾히는가. 부족하면 저장소 판단을 다시 본다(§7-6).
5. **추출 물량과 비용** — 하루 메시지 수, 사람 발신 비율, 사전 필터 통과율, 통과 메시지당 기록 수. 모델 크기별 추출 정밀도와 호출당 비용을 함께 비교해 추출 모델을 정한다.
6. **데이터 밀도** — 활성 사용자당 경험 기록 수와 그 분포(기록이 한 건도 없는 사용자의 비율), 방 종류(`user_dm`·`agent_dm`·`group`)별 기록 수. 경험 기록은 사람이 채팅에서 말한 경험만 담으므로, 초기에는 대부분의 질문에 근거를 가진 사람이 없을 수 있다.
7. **질문당 근거 보유자 수** — 질문 샘플마다, 요청자가 대화를 시작할 수 있는(§9 T3) `record_match` 또는 `record_entity` 후보가 한 명 이상 있는 비율.

**6과 7이 2단계를 진행할지 정하는 기준이다.** 이 두 숫자가 낮으면 경험 소스를 만들어도 대부분의 추천이 `prior_only`(관심 소스)로 떨어져 체감 품질이 오르지 않는다. 그때는 기록이 쌓일 원천(예: `agent_dm`의 범위 결정, §12)을 먼저 정하거나 2단계를 미룬다. 기준값은 0단계의 결과를 보고 정한다.

이 측정은 dev의 실제 대화를 읽는다. 기획 단계의 범위(공개 범위·동의 제외)는 **dev 내부 데이터로 실험한다**는 뜻이고, 결과로 남기는 것은 비율과 라벨 집계다.

### 13-3. 오프라인 — 합성 대화

기존 10만 합성 모집단에는 topic만 있고 대화가 없다. 그래서 **합성 대화 세트**를 만든다 — 사람마다 심어 둔 경험(엔티티, 종류, 시각, 긍정·부정)을 LLM이 여러 대화 속 발화로 만들어 넣고, 일부는 다른 참가자의 발화로, 일부는 사실 진술로 섞는다. 정답은 심어 둔 경험이다.

- 추출: 심은 경험의 recall, 다른 사람의 발화·사실 진술을 기록한 false positive
- 추천: 질문 세트(심은 경험에서 만든 질문 + 사람이 필요 없는 질문)의 relevant person recall@K / precision@K, `people_needed` 판정 정확도
- 경로 기여: 엔티티·상위 엔티티·topic·텍스트 경로를 하나씩 끄면 recall이 얼마나 떨어지는가
- 조건이 얽힌 질문(취향의 방향 + 대상, 예: "셰리 싫어하는 사람에게 맞는 스페이사이드")을 따로 모아 precision을 잰다. 이 숫자가 LLM 리랭커(§9 T4)를 붙일지의 근거다
- 요청자 본인 포함 0건

합성 대화는 **생성기의 가정 위에서** 잰다. 실제 사람의 말투·생략·지시어는 §13-2의 dev 측정으로 본다.

### 13-4. 핵심 품질 지표

추천 당시의 coverage 상태와, 실행했을 때 추천받은 agent가 실제로 답해 냈는지(`supported/unsupported`)의 차이(calibration error) — 상태별, 경로별로. `evidence_ref`로 기록이 조회된 실행과 안 된 실행을 나눠 재면 그 효과가 보인다.

**호출률**(T0, bourbon-agent 쪽): 사람이 필요했던 질문 중 tool이 불린 비율, 근거 없이 직접 답한 비율, 명시적 요청 때의 호출 성공률.

---

## 14. 구현 단계

한 단계가 끝나면 그 자체로 배포해 쓸 수 있게 나눴다. 나누는 기준은 **다른 팀이나 새 서비스가 필요해지는 지점**이다 — 그쪽이 늦어도 앞 단계까지는 내보낼 수 있게.

```text
0. 측정 ──▶ 2. 경험 소스로 추천 ──▶ 3. evidence_ref ──▶ 4. 트리거 ──▶ 5. 실행·종합 ──▶ 서비스화
                ▲
1. 관심 소스로 추천 ──▶ 1-b. 두 사람 조합   (0과 무관하게 먼저 시작할 수 있다)
```

### 0단계 — 경험 기록이 쓸 만큼 쌓이는지 먼저 잰다

- **목표**: 새 서비스를 제대로 만들기 전에, 이 방식이 가치가 있는지 dev 데이터로 확인한다.
- **만드는 것**: 새 서비스의 최소 골격 — 사전 필터, 추출, 엔티티 레지스트리. 추천 route는 아직 없다.
- **재는 것**: §13-2의 일곱 가지. 추출 정확도, 사전 필터가 놓치는 비율, 엔티티 resolve 일치, 요약문 검색 품질, 물량과 비용, 그리고 **사용자당 기록 수**와 **질문마다 근거를 가진 사람이 있는 비율**.
- **정하는 것**: 추출에 쓸 모델, 저장소(§7-6), 그리고 **2단계를 진행할지**. 마지막 두 숫자가 낮으면 2단계를 만들어도 추천 대부분이 관심 소스로 떨어진다.

### 1단계 — 관심 소스만으로 한 명 추천

- **목표**: 새 추천 route를 먼저 열어 둔다. 새 서비스 없이 지금 있는 데이터로.
- **추천하는 사람**: 이 분야에 관심을 드러낸 사람(`prior_only`). "겪어 본 사람"이 아니라 "관심 있는 사람"이다.
- **만드는 것**: `POST /recommend/knowledge` route와 응답 형식, T1 질문 분석(새 필드를 전부 뽑아 decision log에 남긴다), 사실 질문 판정(`people_needed`), topic-api `knowledge` facet 컬럼, 순위.
- **필요한 것**: 없음. discovery 안에서 끝난다.
- **내보내는 범위**: 관심 기반 추천이라 사용자가 명시적으로 "추천해 달라"고 할 때만 쓴다.

### 1-b단계 — 두 사람 조합

- **목표**: need가 여럿인 질문에 서로 보완하는 두 사람을 추천한다.
- **만드는 것**: 조합 탐색(최대 2명).
- **필요한 것**: 없음. 1단계 위에 얹는다.

### 2단계 — 경험 소스로 추천

- **목표**: "이것을 겪었다·좋아한다·해 봤다·안다고 말한 사람"을 추천한다. 이 타입의 핵심이다.
- **만드는 것**: `bourbon-lived-knowledge-api` 전체 — 이벤트 소비, 추출, 저장, 조회 API. discovery 쪽은 네 검색 경로를 받아 합치는 부분과 요약문 기반 추천 이유.
- **필요한 것**: 0단계의 "진행" 판단, bourbon-api의 agent-context 호출 허락(§15 요청 2), memory-api resolve 사용 허락(§15 요청 4).
- **끝났다고 보는 기준**: 합성 대화 세트(§13-3)에서 recall·precision을 재고, 경로별 기여를 확인한다. 조건이 얽힌 질문의 precision으로 LLM 리랭커(§9 T4)를 붙일지 정한다.

### 3단계 — `evidence_ref`로 근거 넘기기

- **목표**: 추천받은 agent가 근거가 된 경험 기록에서 바로 답을 시작하게 한다.
- **만드는 것**: `evidence_ref` 발급과 조회, 기록 소유자 확인.
- **필요한 것**: bourbon-agent의 실행 경로 변경(§15 요청 10). 원 메시지가 필요하면 memory-api `messages/lookup`.
- **끝났다고 보는 기준**: `evidence_ref`로 기록을 조회한 대화와 그렇지 않은 대화의 답변 성공률을 나눠 잰다(§13-4).

### 4단계 — 트리거 넓히기

- **목표**: 사용자가 "추천해 달라"고 하지 않아도, 사람의 경험이 필요한 질문에서 agent가 알아서 추천을 부르게 한다.
- **필요한 것**: bourbon-agent의 tool 설명 변경 또는 두 번째 tool(§15 요청 9). 2단계가 먼저 끝나 있어야 한다 — 관심 기반 추천을 자동으로 내보내지 않는다.
- **끝났다고 보는 기준**: 호출률(§13-4).

### 5단계 — 실행과 종합

추천받은 agent가 실제로 답하고, 여러 agent의 답을 합치는 부분이다. bourbon-agent가 맡고 이 문서 범위 밖이다.

### 서비스화

- 기획 단계에서 빼 둔 공개 범위·동의(§12)를 정하고, 남겨 둔 자리에 필터를 붙인다.
- `evidence_ref`를 조회하는 route에 내부 호출 인증을 붙인다(§10-3).
- 그 뒤에 production 데이터를 적재한다.

### 질문 하나가 단계마다 어디까지 가는가

"글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어"

| 끝난 단계 | 추천되는 사람 |
|---|---|
| 1 | 위스키·몰트 위스키에 관심이 큰 사람 |
| 2 | 글렌드로낙이나 그 신상을 마셔 봤다고 말한 사람. 최근에 말했고, 요약문이 "신상"과 맞는 사람이 맨 위 |
| 3 | 위와 같고, 그 사람의 agent가 대화할 때 그 경험 기록에서 답을 시작한다 |

---

## 15. 요청하고 확인할 것

**bourbon-api**

1. **믿을 수 있는 탈퇴 확인 방법.** `user_deactivated`는 best-effort이고, 내부 사용자 조회에 없다는 것을 탈퇴 신호로 읽지 말라고 적혀 있다(§7-5). 탈퇴한 id 목록을 주는 route나, 발행을 보장하는 방식(outbox 등)이 있는지.
2. 새 서비스가 `GET /api/internal/rooms/{room_id}/agent-context`를 bourbon-agent와 같은 방식으로 불러도 되는지, 부하 한도.
3. 새 서비스의 큐를 `bourbon.message_created`에 바인딩하는 것 — 이벤트 워커는 소비하는 repo가 소유한다는 기존 원칙대로.

**memory-api**

4. `POST /knowledge/resolve`를 추출 경로에서(메시지마다가 아니라 레지스트리에 없는 새 이름마다) 불러도 되는지, 처리량과 지연 시간.
5. `POST /{tenant}/messages/lookup`을 `evidence_ref` 실행에서 지금 방의 scope로 부르는 것이 그쪽 scope의 의미에 맞는지(§10-3).
6. personal build는 건드리지 않는다는 것을 알린다. 이 추천을 위해 그쪽 모델을 바꿀 요청은 없다.

**topic-api**

7. `score_detail` block의 facet 이름과 `confidence`를 소비자 계약으로 삼아도 되는지(관심 소스).
8. 제품·브랜드 노드는 요청하지 않는다. 엔티티는 새 서비스의 레지스트리가 맡는다.

**bourbon-agent**

9. `recommend_agents`의 트리거를 넓히는 것과 두 번째 tool 중 어느 쪽이 맞는지. 그리고 질문 분석(need 필드)을 그쪽 tool 인자로 받는 대안(§9 T1)이 그쪽 프롬프트 설계에 맞는지.
10. 실행 경로에서 `evidence_ref`를 추천받은 agent의 턴에 넘길 자리 — 그 기록에서 답을 시작하게 하는 프롬프트·tool. 그리고 내부 호출 인증(§10-3).
11. 요청자가 이름을 모를 때("이번 신상") `context`에 제품명을 넣어 줄 수 있는지, 되묻는 것이 맞는지.
12. 호출률 지표를 그쪽 journal에서 낼 수 있는지.

**e3llm**

13. 추출의 배치 부하(§7-8)와 새 타입의 요청 부하. 배치에 별도 한도를 둘 수 있는지.

---

## 16. 열린 항목

1. 새 서비스의 repo와 배포 단위.
2. 저장소 — PostgreSQL을 권하되(§7-6), 요약문 검색 품질에 따라 검색만 OpenSearch로 옮길지.
3. 사전 필터의 방식 — 규칙, 작은 분류기, 작은 LLM(§7-1).
4. 추출에 넣을 앞 턴의 수.
5. `registry.ambiguity_ratio`와 `rg:` → `wd:` 합치기의 기준.
6. 전해 들은 것을 다시 말한 경우("친구가 그러는데")를 기록할 것인가, 한다면 어떤 종류로(§12).
7. `people_needed` 판단이 틀렸을 때의 비용 — 사람이 필요한 질문을 사실 질문으로 판단하면 추천이 안 나간다. 기준을 어느 쪽으로 기울일 것인가.
8. `kind`를 순위 조건으로만 둘 것인가, 필터링 조건으로 쓸 경우가 있는가.
9. `recency_days`의 초기값, 그리고 종류별로 다르게 둘지(`prefers`는 오래 유효하고 `insider`는 빨리 낡는다).
10. 추천 이유의 요약문을 요청 언어로 번역할 것인가(요약문은 메시지 언어다).
11. `evidence_ref`의 유효 기간.
12. 요청자가 추천을 수락한 뒤에만 실행할지, 자동으로 실행할지.
13. 두 사람 조합을 세 사람으로 늘릴 조건.
14. required need 하나가 비었을 때 부분 답을 허용할지.
15. 실행 단계의 피드백 이벤트(추천 id ↔ `supported/unsupported`) — calibration을 재려면 먼저 있어야 한다.
16. 새 서비스를 memory-api로 옮기는 시점과 기준(오너: 우선 새 서비스, 필요하면 넘긴다).
17. §12에서 빼 둔 것 전부 — 실 서비스화 때.
18. 질문 분석을 discovery의 T1에 둘지, bourbon-agent의 tool 인자로 옮길지(§9 T1). 그리고 요청이 need 목록을 받으면 T1을 건너뛰는 입구를 1단계부터 열어 둘지.
19. LLM 리랭커(§9 T4)를 붙일지, 붙인다면 몇 명을 넣고 timeout을 얼마로 둘지, 요청마다 켤지 조건이 얽힌 need에만 켤지.

---

## 17. 선행 문서와 달라진 것

| 선행 문서(아카이브된 `personal-knowledge-agent-recommendation.md`) | 이 문서 | 이유 |
|---|---|---|
| 근거는 memory-api personal build의 결과 | 추천만을 위한 경험 기록, 새 서비스(경험 소스). personal build는 건드리지 않는다 | personal build는 각 사용자 자신의 agent가 기억해 답하기 위한 그래프라 말한 사람·시각·엔티티 동일성·사실 비중이 이 목적과 맞지 않는다(§6-2, §5-2) |
| 사용자의 memory 단위, authorship은 결정 대기 정책 | 메시지 단위, 보낸 사람 기준 | "누가 겪었나"가 정의상 맞게 된다. authorship 질문이 대부분 사라진다(§12) |
| 근거는 개수와 날짜만, 텍스트 없음 | 요약문을 저장한다(오너, 2026-09-26). 원문은 저장하지 않는다 | 조건("이번 신상")을 요약문 매칭으로 반영하고 추천 이유를 구체적으로 쓴다 |
| 시각은 빌드 시각 | 메시지 시각 | "최근에"가 조건이다 |
| 찾는 기준은 topic 하나, memory 근거는 `topic_qid_map`을 거쳐 조회 | topic과 엔티티. 엔티티는 새 서비스의 레지스트리가 질문과 기록 양쪽을 같은 방식으로 resolve한다 | 카탈로그는 분야만 받고, 따로 하는 두 resolve는 어긋난다(§3-2) |
| `topic_qid_map`, 폴링 루프, manifest cursor, reconciliation | 없음. discovery가 새 서비스를 조회한다 | 새 서비스는 우리가 이 조회를 위해 만든다 |
| 모든 질문이 대상 | `people_needed`로 사실 질문을 뺀다 | 사람이 필요한 질문만 추천할 가치가 있다(§1) |
| knowledge_kind 다섯(memory-api의 값) | kind 넷(`experienced`·`prefers`·`practiced`·`insider`) | 사람만 가진 것의 분류다. 사실(`declarative`)과 계획(`intention`)은 추천의 근거가 아니다 |
| 추천 이유는 중립 문구 하나 | 요약문 기반 이유, 관심 소스만이면 관심 문구 | 요약문을 저장하기로 했다. 동의는 서비스화 때(§12) |
| 실행 시점의 근거 찾기는 agent의 대화 검색에 맡김 | `evidence_ref`로 근거 기록을 추천받은 agent에게 넘긴다 | 답을 찾지 못하는 경우를 줄이고, 추천과 대화의 출발점을 같게 한다(§10-3) |
| 동의(`consultable`)와 authorship이 production의 선행 조건 | 기획 단계에서 공개 범위·동의를 빼 두고 자리만 남긴다 | 오너, 2026-09-26 |
| 오프라인 측정은 합성 모집단에 파생 데이터를 합성 | 합성 **대화** 세트, 그리고 dev 추출 정밀도 | 추출이 새로 생긴 단계이고, 대화 없이는 그것을 잴 수 없다 |
