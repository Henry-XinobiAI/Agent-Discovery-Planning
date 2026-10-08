# 사람에게 물어야 하는 질문의 agent 추천

> 상태: **기획 초안, 결정 아님**
> memory-api에서 읽는다면 §15의 memory-api 안내부터 — 그쪽에 바꿔 달라는 요청은 없다.
> 범위: 새 추천 타입(타입 ④ 후보)과 그것을 위한 새 서비스 `bourbon-lived-knowledge-api`, 그리고 `bourbon-agent-discovery-api` · `bourbon-agent` · `bourbon-api` · `bourbon-memory-api-v2` · `bourbon-topic-api`와의 경계
> 비범위: 타입 ①·②·③의 계약 변경, 추천된 agent의 실제 답변과 종합(경계만 정한다), bourbon-agent가 언제 recommend tool을 부를지(트리거 — 그쪽의 결정이다. 이 문서는 그쪽 요청에 기대하는 것만 적는다, §9 T0)
> **기획 단계에서 빼 둔 것**(오너, 2026-09-26): 공개 범위·동의(`consultable`)·방 범위. 설계와 실험에는 조건을 걸지 않고, 실 서비스화할 때 다룬다. 나중에 필터를 붙일 필드만 남긴다(§12).
> 선행 문서: `archive/2026-09-26_knowledge-type-first-draft/personal-knowledge-agent-recommendation.md`(2026-09-18 ~ 09-21, 아카이브). 그 문서는 memory-api personal build의 결과를 topic에 조인해 근거로 썼다. 이 문서는 **추천만을 위한 데이터를 새 서비스에 따로 두고**, 메시지 하나하나를 보낸 사람의 경험으로 저장한다. 무엇이 달라졌는지는 §17에 모았다.
> 이 문서의 "현재"는 각 repo의 HEAD 기준이다 — bourbon-agent `61f84aea`(origin/main, 09-25), bourbon-api `078eeeb`(origin/main, 09-21), memory-api-v2 `8c6a937`(origin/main, 09-19), topic-api `ffc62bf`(09-22), agent-discovery-api `bac5de9`(09-24), e3llm-api `19ca985`(08-20). 적재 방식(§7-1·§7-5)과 엔티티 병합(§7-3)은 2026-09-29에 bourbon-agent `89a49bf0`, bourbon-api `01c79c2`, memory-api-v2 `8c6a937`(모두 origin/main)에서 다시 읽었다

---

## 0. 요약

사용자의 personal agent가 **LLM으로는 답할 수 없는 질문**을 받으면, 그런 경험을 가진 다른 사용자의 personal agent를 추천해 그 agent와 이야기해 보게 한다. 여기서 "LLM으로는 답할 수 없는 질문"은 누군가 직접 겪은 경험, 취향, 해 보며 익힌 요령, 그 사람만 아는 사정이 필요한 질문이다. 일반적인 사실 질문에는 추천하지 않는다.

설계의 뼈대는 여섯 가지다.

1. **사람이 필요한 질문만 추천한다.** 질문을 받으면 먼저 "이것이 사람의 경험이 있어야 답할 수 있는 질문인가"를 판정하고, 추천의 근거로도 사실이 아닌 경험·취향·요령·사정만 쓴다(§1). 언제 추천을 부를지, 요청자 본인의 memory로 답할 수 있는지는 bourbon-agent가 정한다(§9 T0).
2. **추천용 데이터는 새 서비스 `bourbon-lived-knowledge-api`(이하 lived-knowledge)가 따로 만든다.** 방마다 대화가 잠잠해지면 그동안 올라온 메시지를 모아 읽고, 메시지마다 "보낸 사람이 직접 겪은 것"을 뽑아 **경험 기록**으로 저장한다. memory-api의 personal build(사용자마다 대화 전체를 LLM으로 읽어 만드는 지식 그래프)는 각 사용자 자신의 agent가 기억해 답하기 위한 데이터라 목적이 다르고, 그대로 둔다(§6-2, §7).
3. **경험 기록은 보낸 사람의 것이다.** A가 B와의 방에서 "나 그거 마셔 봤어"라고 하면 그 경험은 A의 기록이 된다. 기록의 시각은 그 메시지의 시각이다. 기록이 가리키는 대상(제품, 장소, 가게)에는 **엔티티 레지스트리**의 id를 붙여, 누가 어떤 표기로 말했든 같은 대상은 같은 id로 모이게 한다(§2, §7).
4. **원문은 저장하지 않는다.** 메시지를 읽고 기록을 뽑은 뒤 원문은 버린다. 남는 것은 기록, 짧은 요약문, 원 메시지의 id다(§7-2).
5. **topic과 엔티티는 후보를 모으는 데만 쓰고, 필터링에는 쓰지 않는다.** 둘 다 질문을 단순한 id 하나로 줄이는 과정이라 "이번 신상", "마셔 봤다" 같은 조건이 빠진다. 그래서 여러 경로로 후보를 넓게 모은 뒤, 순위는 경험 기록의 종류·시각·요약문이 질문의 조건과 얼마나 맞는지로 정한다(§3, §9).
6. **추천된 agent에게 근거를 넘긴다.** discovery는 추천마다 근거가 된 경험 기록의 id를 **추천 근거**로 저장한다. 요청자가 추천된 agent와 대화를 시작하면 bourbon-agent가 그것을 조회해 추천된 agent에게 넘기고, 추천된 agent는 그 기록을 출발점으로 답한다. 추천의 근거와 실제 대화의 출발점이 같아져 답을 찾지 못하는 경우가 줄어든다(§9 T6, §10-3).

추천이 보장하는 것은 **"이 사람이 이런 경험을 말한 적이 있다"** 까지다. 지금도 그 경험을 기억해 제대로 답할 수 있는지는 추천된 agent와의 실제 대화에서 드러난다. 그래서 이 기능의 품질은 "추천된 사람이 실제로 답해 낸 비율"로 잰다(§13-4).

---

## 1. 무엇을 추천하나

### 1-1. 사람만 줄 수 있는 네 가지

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

"누가 답할 수 있는가"를 질문마다 사용자 한 명씩 LLM에게 물으면 비용과 지연 시간이 사용자 수에 비례한다. 그래서 무거운 일은 메시지가 쌓일 때 미리 해 두고, 질문이 올 때는 조회와 계산만 한다.

| 언제 | 누가 | 무엇을 | LLM 호출 | 비용이 비례하는 것 |
|---|---|---|---|---|
| 방의 대화가 잠잠해질 때(방마다 모아서) | lived-knowledge | 그동안 올라온 메시지에서 보낸 사람의 경험 기록을 뽑아 저장 | 창(한 번에 넣는 메시지 묶음)마다 1회. 사전 필터(LLM 앞에서 경험 표현이 없는 메시지를 제외하는 값싼 판정)를 통과한 메시지가 없는 창은 0회 | 대화량(창 수) |
| 질문이 올 때 | discovery | 질문 분석 → 후보 조회 → 순위 → 응답 | 1~2회(질문 분석, topic이 모호할 때 disambiguation). `condition`이 있는 need에는 judge 1회, 모드 B는 재시도마다 1회 더(§9 T4-a) | 후보 수. 사용자 수와 무관 |
| 추천을 실행할 때 | bourbon-agent | 추천된 agent가 요청자와 대화 | agent가 평소 쓰는 만큼 | 이 기능의 비용이 아님 |

---

## 2. 용어

| 용어 | 뜻 |
|---|---|
| **요청자** | recommend tool을 부른 agent의 owner. 요청의 `user_id`다. 개인 방에서는 질문한 사람과 같지만, 그룹 방에서는 다른 참가자가 질문했어도 요청자는 agent의 owner다 — bourbon-agent가 `requester_user_id=payload.owner_user_id`로 보낸다(`bourbon_agent/agents/personal_agent/recommendation/tools.py:317`) |
| **topic visibility(tier)** | 사용자가 자기 topic마다 정하는 공개 범위 — `public`·`friends`·`private`·`hidden`. 관심 소스의 노출을 정하고, 이 문서에서는 경험 기록의 공개 범위도 정한다(§12) |
| **도달 가능성** | 요청자가 그 사람의 agent와 대화를 시작할 수 있는가 — 친구이거나 agent가 public(§6-1, §9 T3) |
| **보는 사람** | 추천 결과와 요약문을 보게 되는 사람들. 요청이 온 방의 사람 참가자이고, bourbon-agent가 요청에 실어 보낸다(없으면 discovery가 bourbon-api에서 읽는다, §12). owner 본인의 개인 방(PERSONAL)이면 요청자 한 명이고, 다른 사용자가 owner의 agent와 1:1로 대화하는 방이면 그 사용자다(§12) |
| **후보** | 추천될 수 있는 다른 사용자(와 그 사람의 agent) |
| **need** | 질문이 요구하는 것 하나. 질문 분석(§9 T1)이 0~3개로 나눈다. 각 need에 종류(`experienced` 등), 대상 엔티티, 시점 조건이 붙는다 |
| **topic** | topic-api 카탈로그의 분야 노드("몰트 위스키", "에스프레소"). 카탈로그는 분야(KIND)만 받고 제품·브랜드는 받지 않는다(§6-3) |
| **엔티티** | 경험의 대상이 되는 구체적인 것 — 제품, 브랜드, 증류소, 가게, 장소. "글렌드로낙", "글렌드로낙 21 팔리아먼트" |
| **상위 엔티티** | 한 엔티티를 포함하는 더 넓은 엔티티. "글렌드로낙 21 팔리아먼트"의 상위 엔티티는 "글렌드로낙"이다. 분야(topic)와는 다르다 — 상위 엔티티도 구체적인 대상이다 |
| **resolve** | 이름을 엔티티 레지스트리의 id로 바꾸는 것. "글렌드로낙"·"GlenDronach"을 같은 id로 |
| **지시어 해소** | "이번 신상"처럼 시점이나 맥락에 따라 가리키는 대상이 달라지는 지칭을 구체적인 이름으로 바꾸는 것. 요청에서는 bourbon-agent가 채워 보내고(§9 T0), 기록에서는 lived-knowledge가 필요할 때 웹 검색으로 한다(§7-3) |
| **엔티티 레지스트리** | lived-knowledge가 가진 엔티티 사전 테이블. 모든 사용자의 경험 기록이 함께 쓴다. 목적은 A가 "글렌드로낙 21"이라 쓰고 B가 "GlenDronach Parliament"라 써도 같은 id로 모이게 하는 것이다. Wikidata에 있는 것은 QID를, 새로 나온 병이나 동네 가게처럼 없는 것은 레지스트리가 새로 만든 id를 쓴다. 같은 대상이 다른 이름으로 따로 등록되면 하나로 병합한다(§7-3) |
| **창(window)** | 추출 LLM 호출 한 번에 넣는 메시지 묶음. 한 방의 이어진 메시지 최대 몇 개(기록을 뽑는 메시지)와 그 앞의 문맥 몇 개로 이루어진다. 문맥 메시지에서는 기록을 뽑지 않는다(§7-1) |
| **방 커서** | 방마다 "여기까지 추출했다"를 나타내는 마지막 메시지 id. 추출 결과를 쓰는 트랜잭션에서 함께 전진한다(§7-5) |
| **경험 기록** (줄여서 기록) | lived-knowledge가 메시지 하나에서 뽑아 저장하는 한 줄. 누가(보낸 사람), 어떤 종류로(`experienced` 등), 무엇에 대해(엔티티·topic), 어땠는지(긍정·부정), 언제(메시지 시각), 요약문, 원 메시지 id(§7-2) |
| **요약문** | 경험 기록마다 붙는 한두 문장. 보낸 사람 본인의 경험만 담는다. 추천 이유 문장과 검색에 쓴다 |
| **요약문 매칭** | 질문의 조건(`condition`)·엔티티 이름과 기록의 영어 요약문(`summary_en`)·이름 표기(`terms`)를 비교한 결과. 요약문을 비교하는 방식은 텍스트 검색 모드를 따른다. need 안에서의 순위로만 쓴다 |
| **텍스트 검색 모드** | 텍스트 경로와 요약문 매칭이 요약문을 비교하는 방식. 모드 A(임베딩 검색)는 조건과 요약문의 임베딩이 가까운지로, 모드 B(쿼리 확장)는 조건을 여러 표현으로 바꿔 단어가 겹치는지로 찾는다. 2단계에서 둘 다 만들어 비교하고 하나를 고른다(§7-6) |
| **LLM judge** (줄여서 judge) | `condition`이 있는 need에서, 가중 합 상위 후보의 요약문이 그 조건에 맞는지 LLM이 확인하는 단계(§9 T4-a). 맞지 않는 후보를 빼거나 순서를 바꾼다 |
| **관심 소스** | 후보를 찾는 첫 번째 데이터. topic-api에서 온, 사용자가 공개한 관심 topic(discovery의 `visible_topic_rows`). "이 분야에 관심을 드러낸 사람"을 알려 준다. 지금 있는 것이다 |
| **경험 소스** | 후보를 찾는 두 번째 데이터. lived-knowledge의 경험 기록. "이것을 겪었다·좋아한다·해 봤다·안다고 말한 사람"을 알려 준다 |
| **검색 경로** | 경험 소스에서 후보를 찾는 네 가지 방법 — 엔티티로, 상위 엔티티로(질문의 엔티티가 기록 엔티티의 상위일 때), topic으로, 요약문 텍스트로(§9 T3). 경로마다 상위 K명을 뽑아 합친다 |
| **관심 문구** | 관심 소스로만 찾은 후보의 추천 이유. "{need 이름}에 관심이 있는 agent입니다." |
| **authorship** | 한 사용자의 memory에 든 다른 사람의 말을 누구의 근거로 볼 것인가의 문제. 선행 문서의 가장 큰 미결 항목이었다(§12) |
| **추천 근거** | 추천마다 discovery가 저장해 두는 (추천 id, 요청자, 추천된 사람, 충족한 need, 근거가 된 경험 기록 id) 묶음. 만료 시각이 있다. 요청자에게는 내보내지 않고, 대화가 시작될 때 bourbon-agent가 조회해 추천된 agent에게 넘긴다(§10-3) |
| **personal build** | memory-api가 사용자마다 대화 전체를 LLM으로 읽어 엔티티·statement 그래프를 만드는 배치. 그 사용자 자신의 agent가 기억해 답하기 위한 것이다(§6-2) |
| **대화 검색(recall)** | bourbon-agent가 답하기 전에 memory-api의 대화 원문을 검색하는 것(`search_conversations` tool). 지표 이름으로서의 recall(찾아야 할 것 중 찾은 비율)과 구별해 이 문서에서는 "대화 검색"이라고 쓴다 |
| **불변식 N, 결정 R번호** | discovery 계약(`agent_discovery_contract.md` §5)의 불변식과 기획 repo `decisions.md`의 결정 번호. 이 문서가 인용하는 것 — 불변식 1(저장소에는 공개된 row만 있다), 불변식 2(friends tier 행은 요청자가 친구일 때만), 불변식 7(사용자의 글은 로그·예외·Sentry에 원문으로 남기지 않는다), 불변식 8(422는 봤는데 없다, 503은 못 봤다), R17(공개 범위 조건은 쿼리 안에서 건다), R22(요청자 본인의 hidden은 읽지 않는다), R44(DynamoDB 테이블 하나), R55·R56(visibility 변경 이벤트와 강한 읽기 재조회), R57(`agents.public`/`discoverable`은 public topic 보유에서 파생), R60(disambiguation 게이트), R68(탈퇴한 사용자는 다시 기록하지 않는다) |
| **coverage 상태** | need마다 후보 한 명의 근거가 어느 소스·경로에서 왔는지의 수준(관심 소스만 / topic / 텍스트 / 엔티티 경로)(§9 T3). 순위의 한 feature이고 응답에는 싣지 않는다 |
| **need 충족(covers)** | 후보가 그 need를 채운다고 보는 판정. coverage 상태·종류·stance·시점을 따로 보고 정한다(§9 T3). 두 사람 조합과 `nobody_covers`가 이것을 쓴다 |
| **설정 레지스터** | discovery의 모든 설정값(이름·뜻·기본값)을 모은 문서 `agent_discovery_settings.md`. "설정 레지스터 값"은 코드 상수가 아니라 거기 올리는 값이라는 뜻이다 |

---

## 3. 원칙 — topic과 엔티티는 모으는 데만 쓴다

### 3-1. 질문을 id로 바꾸면 조건이 빠진다

topic은 질문을 분야 하나로 줄인다("몰트 위스키"). 엔티티는 대상 하나로 줄인다("글렌드로낙"). 어느 쪽이든 줄이는 순간 "이번 신상", "마셔 봤다", "압력이 높을 때" 같은 조건이 빠진다. 조건까지 맞춰 볼 수 있는 것은 **근거 자체**뿐이다. 이 설계에서 근거는 경험 기록의 종류·시각·요약문이다.

그래서 역할을 나눈다. **topic과 엔티티는 후보를 넓게 모으는 데(recall) 쓰고, 경험 기록과 요약문은 그중에서 맞는 사람을 고르는 데(precision) 쓴다.**

### 3-2. 엔티티 매칭이 topic 매칭보다 위험한 이유

1. **양쪽 resolve 결과가 같아야 맞는다.** 질문 속 이름과 기록 속 이름이 같은 엔티티로 resolve되어야 매칭된다. 한 이름에 Wikidata 항목이 여럿이면(증류소·브랜드·회사) 어긋날 수 있다.
2. **이름이 모호하다.** 야마자키는 지명·증류소·인명이다. 엉뚱한 엔티티로 resolve되면 422도 없이 틀린 사람이 추천된다. topic 매칭이 실패하면 범위가 넓어질 뿐이지만, 엔티티 매칭이 실패하면 결과가 틀린다.
3. **범위(granularity)가 다를 수 있다.** 질문은 병 하나를 말하는데 기록은 증류소를 가리킬 수 있다.
4. **너무 좁게 매칭하면 답할 사람을 놓친다.** "글렌드로낙 신상 맛이 어때?"는 비슷한 셰리 캐스크 하이랜드 몰트를 많이 마셔 본 사람도 답할 수 있다.

1과 3은 lived-knowledge가 질문과 기록을 **같은 엔티티 레지스트리로** resolve해서(§7-3) 줄어든다. 같은 대상이 레지스트리에 다른 이름으로 따로 등록되어 1이 다시 생기는 것은 새 id를 만들기 전의 후보 확인과 병합 워커로 줄인다(§7-3). 2와 4는 아래 규칙으로 막는다.

### 3-3. 규칙 다섯

1. **topic과 엔티티로 후보를 필터링하지 않는다.** 후보는 need마다, 검색 경로마다 상위 K명을 뽑아 합친 합집합이다. 엔티티 매칭이 어긋나도 topic이나 텍스트로 들어온 사람은 순위 단계까지 간다.
2. **엔티티는 하나가 아니라 여러 개로 매칭한다.** resolve된 엔티티와 레지스트리에서 펼친 그 하위 엔티티를 함께 쓴다 — 질문이 "글렌드로낙"이면 "글렌드로낙 21 팔리아먼트"의 기록도 찾는다(§7-3).
3. **모호한 엔티티는 쓰지 않는다.** 이름이 모호하면 그 need는 topic과 텍스트로만 찾는다. 모호할 때는 좁히지 않고 넓게 간다.
4. **빠진 조건은 경험 기록과 요약문으로 반영한다.** 종류·시점은 기록의 필드로 반영한다. "이번 신상"처럼 시점에 기대는 지칭은 구체적인 이름으로 바꿔 찾는다 — 요청에서는 bourbon-agent가 채워 보내고(§9 T0), 기록에서는 lived-knowledge가 해소한다(§7-3). "압력" 같은 나머지 조건은 요약문 매칭으로 반영한다.
5. **얼마나 정확해야 하는지는 need가 정한다.** `precision: exact`(바로 그것을 겪은 사람) / `related`(비슷한 것을 겪은 사람도).

---

## 4. 전체 흐름

두 흐름이 있다. 메시지가 쌓일 때 lived-knowledge가 경험 기록을 쌓는 **적재 흐름**, 질문이 올 때 discovery가 추천을 만드는 **추천 흐름**이다.

### 4-1. 적재 흐름 — lived-knowledge

```text
bourbon-api ── bourbon.message_created (id, 보낸 사람, 방 종류. 본문 없음) ──▶ lived-knowledge
                                                                        │
  ① 사람이 보낸 텍스트 메시지면 그 방을 pending으로 두고 방 단위 debounce를 민다  │  읽지도, 부르지도 않는다
  ── 방의 대화가 잠잠해지면(길어도 최대 대기 시간 안에) 방 하나를 실행한다 ──      │
  ② bourbon-api에서 방 커서 다음의 메시지들과 커서 앞의 문맥을 읽는다            │
  ③ 창으로 나누고 사전 필터: 1인칭 경험·취향·요령 표현이 있는가                  │  대부분 여기서 끝(LLM 없이 기록 교체·커서 전진)
  ④ LLM 추출: 창마다 1회. 메시지마다 보낸 사람 본인에 관한 기록 0~N개 + 요약문   │  기록이 없으면 여기서 끝
  ⑤ 엔티티 resolve: 레지스트리 → memory-api resolve로 QID → 비슷한 후보 확인 → 새 id │
  ⑥ topic 매핑: 분야 이름을 topic-api 검색으로 topic id에                       │
  ⑦ 저장: 경험 기록 · 요약문 · 원 메시지 id, 방 커서 전진. 원문은 버린다          ▼
                                                                   경험 기록 (경험 소스)
```

1. `bourbon.message_created`에는 id만 있고 본문이 없다(`bourbon_api/messages/events.py:18-29`, 발행하는 세 곳 모두 같은 payload). `sender_type`으로 사람이 보낸 메시지만 남긴다 — agent의 발화는 그 사람의 경험이 아니다. 이 단계에서는 메시지를 읽지 않고, 그 방을 pending으로 두고 방 단위 debounce만 민다.
2. **메시지마다 처리하지 않고 방마다 모아서 처리한다.** 대화는 몇 분 사이에 여러 메시지가 이어서 온다. 메시지마다 LLM을 부르면 호출 수가 메시지 수를 따르고, 같은 앞 턴을 메시지마다 다시 넣는다. 방의 대화가 잠잠해지면 그동안 온 메시지를 한 번에 읽는다. 왜 사용자 단위가 아니라 방 단위인지는 §7-1에 있다.
3. 본문은 bourbon-api의 agent-context route로 방 커서 다음부터 읽는다. 커서 앞의 몇 턴은 "그거 마셔 봤어"의 "그거"가 무엇인지 알기 위한 문맥이고, 거기서는 기록을 뽑지 않는다.
4. 읽은 메시지를 창으로 나눈다. 사전 필터가 대부분의 메시지를 LLM 호출 전에 제외하고, 통과한 메시지가 하나도 없는 창은 LLM을 부르지 않는다. 여기서 놓친 것은 다시 찾을 수 없으므로 느슨하게 둔다.
5. 추출은 창마다 한 번이다. 기록마다 어느 메시지에서 나왔는지를 함께 받고, 그 메시지를 보낸 사람이 기록의 소유자다. 한 창에서 여러 발신자의 기록이 함께 나올 수 있지만, 한 사람의 말을 다른 사람의 기록으로 옮기지 않는다.
6. 대상이 레지스트리에 있으면 그 id, 없으면 memory-api의 공개 지식 resolve로 Wikidata QID를 찾는다. 그래도 없으면 비슷한 이름의 기존 엔티티가 있는지 확인한 뒤에야 새 id를 만든다 — 같은 대상이 이름만 달리해 쌓이지 않게(§7-3).
7. 분야 이름("malt whisky")을 topic id로 바꿔 둔다. 엔티티가 없거나 어긋나도 topic으로 찾을 수 있게.
8. 기록 저장과 방 커서 전진은 한 트랜잭션이다(§7-5). 원문은 이 흐름 안에서만 메모리에 있고 저장하지 않는다.
9. **뽑을 것이 없으면 다음 단계를 돌지 않는다.** 커서 다음에 사람 메시지가 없거나, 사전 필터를 통과한 메시지가 없거나, 추출한 기록이 0개면 그 뒤의 LLM·resolve·topic 매핑을 돌지 않는다(§7-1). 다만 그 메시지들의 기존 기록을 "0개"로 교체하는 쓰기는 한다 — 재추출에서 새 버전이 "경험이 아니다"라고 판단한 메시지에 이전 버전의 기록이 남지 않게(§7-5).
10. 이와 별도로 lived-knowledge의 워커 셋이 돈다 — 지시어로만 남은 기록의 대상을 웹 검색으로 해소하는 워커(§7-3), 같은 대상인데 따로 등록된 엔티티를 모으는 병합 워커(§7-3), 그리고 topic visibility를 모든 tier로 미러하는 워커(§7-7).

**관심 소스는 이미 있다.** topic-api가 persona의 preferences에서 사용자의 관심 topic을 뽑고, discovery 워커가 `bourbon.topics_updated`를 받아 공개된 topic을 `visible_topic_rows`에 미러한다. 타입 ①②③이 쓰는 그 테이블이고, 이 흐름에서 바뀌는 것은 없다. 관심 강도는 이미 미러하고 있는 `topic_score`·`topic_maturity`를 쓴다. topic-api `score_detail`의 `knowledge` facet과 `confidence`는 지금 소비자 계약이 아니라서 쓰지 않고, 안정적인 값이 정해지면 그때 더한다(오너, 2026-09-28, §15 요청 7).

### 4-2. 추천 흐름 — discovery

```text
질문 ──▶ bourbon-agent (recommend tool) ──▶ discovery  POST /recommend/knowledge
                                              │
  T1 질문 분석 (LLM 1회)                        │ 사람이 필요한가? 아니면 여기서 mode: none
      need 0~3개, 종류, 엔티티 이름, 시점, 조건      │
  T2 topic 찾기 (topic-api 검색)                │
  T3 후보 모으기 ─┬─ 관심 소스: discovery DB의 visible_topic_rows (topic으로)
                 └─ 경험 소스: lived-knowledge 조회 1회
                       엔티티 · 상위 엔티티 · topic · 텍스트 네 경로, 경로마다 상위 K명
                    → 합집합 → 탈퇴자 제외, 요청자가 대화할 수 있는 사람만
  T4 순위 (종류 일치, 최근성, 요약문 매칭, 엔티티 매칭, 관심 강도)
  T4-a LLM judge (condition이 있는 need만, LLM 1회. 모드 B는 부족하면 표현을 바꿔 다시 조회, 최대 judge.max_retries번)
  T5 한 사람으로 부족하면 두 사람 조합
  T6 응답: 추천 이유(요약문 기반). 근거가 된 기록 id는 추천 근거로 저장
                                              │
bourbon-agent ◀────────────────────────────────┘
  카드로 보여 주고, 대화가 시작되면 추천 근거를 조회해 추천된 agent에게 넘긴다
  → 추천된 agent가 그 경험 기록에서 답을 시작한다
```

1. **T0 (bourbon-agent, 이 문서의 범위 밖)**: 언제 recommend tool을 부를지는 bourbon-agent가 정한다. discovery는 지칭이 구체적인 이름으로 채워진 요청을 기대한다.
2. **T1 질문 분석**: 질문을 need로 나누고, 사람이 필요 없는 질문이면 여기서 `mode: none`으로 멈춘다. 질문 원문은 이 LLM 호출에만 쓰고, 이후에는 T1이 만든 짧은 영어 조건 구절(`condition`)과 엔티티 이름만 넘어간다. "이번 신상" 같은 지칭은 bourbon-agent가 구체적인 이름으로 채워 보낸다(§9 T0). 채워지지 않았으면 표시하고, 그 지칭은 `condition`으로만 반영한다.
3. **보는 사람 확인**: 요청의 `participant_user_ids`를 쓴다. 없으면 T1과 병렬로 bourbon-api에서 요청 방의 사람 참가자를 읽는다. `friends` 기록을 쓸 수 있는지 정하는 데 쓴다(§12).
4. **T2 topic 찾기**: need마다 topic을 찾는다(타입 ①과 같은 방식). 엔티티는 discovery가 resolve하지 않고 이름 그대로 lived-knowledge에 넘긴다 — 경험 기록과 같은 레지스트리로 resolve하기 위해서다.
5. **T3 후보 모으기**: 관심 소스는 discovery DB에서 topic으로, 경험 소스는 lived-knowledge 조회 한 번으로 모은다. lived-knowledge가 네 경로에서 후보를 뽑아 사람별로 묶어 돌려주면, discovery가 둘을 합치고 탈퇴자를 빼고 요청자가 대화를 시작할 수 있는 사람만 남긴다.
6. **T4 순위**: 종류 일치, 최근성, 요약문 매칭, 엔티티 매칭, 관심 강도의 가중 합. 같은 입력이면 늘 같은 순위다(deterministic). `condition`이 있는 need는 그 뒤에 judge가 상위 후보의 요약문을 보고 맞지 않는 후보를 빼거나 순서를 바꾼다(§9 T4-a). judge가 실패하면 가중 합 순위를 그대로 쓴다.
7. **T5 조합**: 한 사람이 모든 need를 채우지 못하면 서로 보완하는 두 사람을 고른다.
8. **T6 응답**: 사람마다 추천 이유(근거가 된 기록의 요약문)를 붙이고, 근거가 된 기록의 id를 추천 근거로 저장한다.
9. lived-knowledge가 답하지 않으면 관심 소스만으로 추천하고 `degraded`에 남긴다(§11).

### 4-3. 왜 lived-knowledge를 discovery와 나누나

둘 다 결국 agent 추천을 위해 있지만, 한 서비스로 합치지 않는다. 이유는 둘이다.

1. **데이터 경계.** discovery는 남의 대화를 한 글자도 저장하지 않는다는 전제로 설계되어 있고(`agent_discovery_events.md` §2-4), 저장소에는 공개된 row만 있다(계약 §5 불변식 1). lived-knowledge는 그 반대편이다 — 원문 메시지를 읽고, 개인 정보인 요약문을 저장하고, topic visibility를 private·hidden까지 미러한다(§12). 합치면 이 경계가 서비스 경계에서 모듈·자격 증명 경계로 약해지고, discovery API 프로세스가 요약문과 private 여부를 읽을 수 있게 된다. discovery가 받는 것은 원문이 아니라 추출 단계에서 다듬은 요약문이고, 요약문도 사용자의 글로 다룬다(§13-1).
2. **데이터의 성격이 추천보다 memory에 가깝다.** lived-knowledge가 만드는 것은 "사람들이 겪은 것의 기억"이고, 나중에 memory-api로 옮겨 갈 수 있다(오너, 2026-09-26). 계약을 좁게 두면 그 이동이 쉽다.

나누는 비용도 있다 — 배포 단위·DB·워커가 하나씩 더 생기고, 추천 요청마다 네트워크 호출이 한 번 붙는다(장애 동작은 §11). memory-api 이동을 접고 lived-knowledge를 부르는 곳이 discovery 하나뿐이며 운영 비용이 문제가 되면, 서비스화 때 합치는 것을 다시 본다(열린 항목 16). discovery와 lived-knowledge 사이의 계약은 조회 route 둘로 좁게 둔다(§10-2) — memory-api로 옮기든 discovery와 합치든 바꿀 곳이 적다.

---

## 5. 예제 — 대화 하나가 각 서비스에 남기는 것

아래 데이터는 설명을 위해 만든 것이다. id와 QID는 플레이스홀더다.

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

### 5-3. lived-knowledge가 저장하는 것

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
record  person  kinds                  entity     topic        stance    observed_at (KST)   summary
r1      A       experienced, prefers   rg:7f3a…   malt whisky  negative  2026-09-21 21:04    글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 입에 맞지 않았다
r3      B       prefers                —          malt whisky  positive  2026-09-21 21:05    셰리 캐스크 위스키를 좋아한다
```

- r1은 A의 메시지 하나에서 나왔다. 마셔 본 것(`experienced`)과 평가(`prefers`)는 한 대상에 대한 한 진술이라 기록 하나에 `kinds` 둘로 적는다 — 둘로 나누면 같은 이야기가 두 기록으로 중복된다(§7-2). 평가는 그 병 하나에 대한 것으로만 적는다 — "셰리가 강한 위스키는 싫어한다"처럼 넓히면 과장이다. r3은 B의 메시지에서 나왔다.
- 세 메시지는 이어서 왔으므로 방의 debounce가 끝난 뒤 한 창에 들어가고, r1·r3은 LLM 호출 한 번에서 나온다. B의 첫 메시지 "요즘 뭐 마셔?"에서는 기록이 나오지 않는다(§7-1).
- 요약문에는 "지난 주말" 같은 상대 시점을 쓰지 않는다. 나중에 읽히면 틀린 말이 되고, 시점은 `observed_at`에 있다.
- 기록에는 자기 엔티티 id만 있다. 상위 엔티티 경로는 조회할 때 레지스트리에서 하위 엔티티를 펼쳐 찾는다 — 글렌드로낙(`wd:Q…`)으로 찾으면 레지스트리에서 그 하위인 `rg:7f3a…`를 펼쳐 r1이 나온다(§7-3). 레지스트리의 상위 관계가 나중에 고쳐져도 기록을 다시 쓸 일이 없다.
- B의 "친구가 그러는데 품절이래"는 B가 겪은 것이 아니라 들은 사실이라 기록하지 않는다(들은 것을 어떻게 다룰지는 열린 항목 6).
- 각 기록에는 표에 없는 필드도 있다 — `summary_en`(영어 검색용 요약), `message_id`, `room_id`·`room_type`, `specificity`, `extractor_version`(§7-2).
- **원문은 없다.** 요약문은 보낸 사람 본인의 경험만 담고, 다른 참가자의 말은 담지 않는다. 그래도 요약문은 A의 개인 정보다 — A의 취향과 마신 시점이 들어 있다(§7-2).

### 5-4. 질문이 오면

요청자 R: "글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어"

bourbon-agent가 대화 맥락이나 `search_web`으로 지칭을 채워 보낸 `question`: "글렌드로낙 21 팔리아먼트(글렌드로낙 신상) 마셔 본 사람이랑 이야기해 보고 싶어"(§9 T0)

```text
T1  need n0: kind=experienced, precision=exact, recency=recent, stance=null,
             entity_mentions=[GlenDronach (brand), GlenDronach 21 Parliament (product)],
             condition="new release", reference_unresolved=false
T2  topic: 몰트 위스키
T3  lived-knowledge:  "GlenDronach" → wd:Q…(GlenDronach)로 resolve
                      "GlenDronach 21 Parliament" → 레지스트리 alias로 rg:7f3a…
               엔티티 경로: entity_id = rg:7f3a…인 기록 r1 (A)
               상위 엔티티 경로: 레지스트리에서 wd:Q…의 하위 rg:7f3a…를 펼쳐 r1 (A)
               topic 경로: r1 (A), r3 (B)
               텍스트 경로: r1의 summary_en이 "GlenDronach 21 Parliament"·"new release"와 매칭
    관심 소스:  몰트 위스키 topic을 공개한 사람들
T4  A: record_entity(바로 그 엔티티) + 종류 일치 + 최근 + 요약문 매칭 → n0 충족, 1위
    B: record_topic, prefers(종류 불일치), 요약문 매칭 없음 → n0 미충족(종류가 mismatch이고, precision=exact인데 기준 대상의 기록이 없다)
    (글렌드로낙 12년을 마신 C가 있었다면: 상위 엔티티 경로로 후보가 되고 순위도 받지만, 기록의 엔티티가 기준 대상 rg:7f3a…가 아니라 n0 미충족)
T6  "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 입에 맞지 않았다"
    추천 근거로 (이 추천의 id, R, A, n0 "글렌드로낙 / experienced", r1)을 저장
```

bourbon-agent가 지칭을 채우지 않고 "글렌드로낙 이번 신상" 그대로 보내도 A는 상위 엔티티 경로(글렌드로낙)로 찾힌다. 다만 A가 요약문에 "신상"에 해당하는 말을 하지 않았다면 요약문 매칭이 빠져, 글렌드로낙의 다른 병을 마신 사람과 구별되지 않는다. 지칭을 채워 보내 달라고 요청하는 이유다(§15 요청 11).

A가 R의 친구가 아니고 A의 agent가 public도 아니면 R은 A와 대화를 시작할 수 없으므로, A는 T3에서 빠진다(§9 T3).

---

## 6. 서비스들의 현재

코드에서 읽은 사실만 적는다. 추론이면 추론이라고 적는다.

### 6-1. bourbon-api — 메시지는 고쳐지지도 지워지지도 않는다

- **메시지는 INSERT-only다**: "`messages_*` — ... INSERT-only; rows are never updated or deleted"(`bourbon_api/messages/models.py:10-11`). 수정·삭제 route도 이벤트도 없다. 메시지 이벤트는 `bourbon.message_created`·`message_translated`·`message_artifacts_updated`다(`bourbon_api/messages/events.py:32, 48, 61`).
- `message_created` payload: `room_id`, `message_id`, `sender_id`, `sender_type`, `type`, `room_type`(`user_dm`·`agent_dm`·`group`)(`events.py:18-29`). 본문은 없다.
- 본문은 `GET /api/internal/rooms/{room_id}/agent-context`로 다시 읽는다 — bourbon-agent가 memory에 적재할 때 쓰는 경로다(`bourbon_agent/memory/listeners.py:1-7, 93`, `api_internal_client/agent_context.py:59`). `before`·`after`·`around` 중 하나와 `limit`(1~100)을 받고, 오래된 순으로 돌려준다(`api/routers/internal/agent_context.py:41-42, 77-80, 94-129`). `after`는 기본적으로 그 id의 메시지를 빼고(`id > after`), `inclusive=true`면 넣는다(`agent_context.py:103`, `bourbon_api/messages/service.py:733`). 방 커서 다음을 `after=<커서>`로 한 번에 읽을 수 있고, 처음 받은 메시지부터 읽을 때는 `after=<그 id>&inclusive=true`다(§7-1).
- bourbon-agent로 가는 `bourbon.passive_observe` task도 id만 싣는다 — "bourbon-agent fetches the full message + context on its own side"(`bourbon_api/tasks/passive_observe.py:26-29`). 본문은 소비하는 쪽이 다시 읽는 것이 이 repo의 방식이다.
- `bourbon.user_deactivated`(`bourbon_api/events.py:15`)는 **best-effort**로 발행된다 — "AMQP failure is logged but does not roll back the deactivation"(`bourbon_api/users/service.py:518-523`). 유실될 수 있다.
- agent DM 게이트는 "친구이거나 agent가 public"이다(`bourbon_api/rooms/service.py:401-414`). 요청자가 추천된 사람과 대화를 시작하려면 둘 중 하나여야 한다.

### 6-2. memory-api-v2 — personal build는 이 목적과 맞지 않는다

personal build는 사용자 한 명의 대화 전체를 LLM stage 여섯 개(extract·grounding scoring·judge·dedup·competence·classes)로 읽어 엔티티·statement 그래프를 만드는 배치다. 그 사용자 자신의 agent가 기억해 답하기 위한 데이터다. 추천에 쓰려면 다음이 맞지 않는다(§5-2의 예제).

| 추천에 필요한 것 | personal build | 근거 |
|---|---|---|
| **말한 사람 본인의** 경험 | 한 사용자의 그래프에 다른 참가자의 발화도 statement로 들어간다. `speaker`는 이름 문자열이다 | `memory/knowledge/personal/structs.py:196`; 빌드는 sender id로 본인/타인 참조를 따로 센다(`memory/knowledge/personal/scoring.py:101-141`) |
| 겪은 **시각** | statement의 `created_at`은 빌드 시각 `datetime.now(UTC)`이고 `valid_time`은 제거됐다. 빌드는 provenance로 메시지 시각을 읽어 salience에 쓰지만(`time_by_msg`) statement에 남기지 않는다 | `reconcile.py:317`, `structs.py:5`, `scoring.py:117-127` |
| 사용자 사이의 **엔티티 동일성** | 엔티티 id가 사용자마다 따로(`uuid5(owner_id:canonical)`). Wikidata identity가 없는 엔티티는 `broader_qids = []`이고, statement의 `subject_qid`·`object_qid`도 null이다 | `memory/utils/ids.py:27-34`, `pipeline/resolve.py:85-91, 121` |
| 사실은 빼고 경험·취향만 | `declarative`가 기본값이다 | `extract.py:304-306` |
| 원래 표현 | statement `text`는 "a concise English summary" | `extract.py:299` |

하나씩 고치면 그쪽 데이터 모델을 이 추천 목적에 맞춰 억지로 바꾸는 일이 된다. **그래서 personal build는 건드리지 않는다.**

personal build의 방식 가운데 둘은 lived-knowledge가 참고한다.

- **창 단위 추출.** 대화를 이어진 메시지 최대 12개씩 창으로 나누고, 메시지 사이가 1시간 넘게 끊기면 새 창을 시작하며, 창마다 앞뒤 문맥 3개씩을 붙인다(`memory/knowledge/personal/config.py:23-26`). LLM 앞의 내용 필터는 없고, owner가 한 메시지도 보내지 않은 창만 뺀다. 빌드는 CLI나 admin route로 수동 실행한다. lived-knowledge의 창(§7-1)이 이것을 따른다.
- **엔티티 중복 확인.** QID가 없는 엔티티의 id 키는 LLM이 낸 영어 정규 이름(`canonical`)의 casefold다(`memory/utils/ids.py:27-34`, `extract.py:282`). 키가 다르면 새로 만들기 전에 이름 유사도(문자 bigram Jaccard) 0.6 이상인 후보를 최대 5개 모아 LLM에 같은 대상인지 묻는다(`dedup.py:63, 96`, `config.py:86-88`). 판정 원칙은 "When unsure, answer false: a duplicate entity is recoverable later, a wrong merge is not"(`dedup.py:44`)이다. 사후에 모으는 단계는 없다. 이 기준으로는 "GlenDronach 21"과 "GlenDronach Parliament"(유사도 약 0.48, 추론)가 LLM 확인까지 가지 않고 둘로 만들어진다. lived-knowledge의 레지스트리는 모든 사용자가 함께 쓰므로 표기 변형이 더 많이 쌓인다 — 새로 만들기 전의 후보 확인에 더해 병합 워커를 두는 이유다(§7-3).

memory-api에서 이 설계가 쓰는 것은 둘이다.

- **공개 지식 resolve** — `POST /knowledge/resolve`(`api/routers/knowledge/router.py:240`).
  - 입력 한도: mention 1~32개(`text` ≤ 200, `context`는 300자로 잘림), 후보 `limit` ≤ 50, `language` en/ko/ja.
  - 응답: 후보마다 `aliases_matched`, `instance_of`, `subclass_of`, `match{method: alias_exact|name|prose, score}`.
  - corpus: sitelink가 하나 이상인 Wikidata 항목 전부(`memory/knowledge/public/dump.py:119-127`).
  - 주의: `match.score`는 **mention끼리 비교할 수 없다**(`memory/knowledge/public/structs.py:127-129`).
  - 이 설계의 사용 규칙: resolve는 공개 지식 route이지만, lived-knowledge가 보내는 이름은 사용자의 메시지에서 나온 것이다("동네 그 바"의 이름 자체가 개인적일 수 있다). 그래서 **이름과 분야 이름만 보내고 메시지 텍스트는 `context`로도 보내지 않는다.** resolve는 mention을 digest로만 로그에 남긴다(`api/routers/knowledge/router.py:252-256`).
- **대화 저장** — bourbon-agent가 대화 검색으로 찾는 원문(`POST /{tenant}/search`)이 여기 있다. `POST /{tenant}/messages/lookup`은 메시지를 id로 찾되 `scope`가 허락하는 것만 돌려주고 `options.context`로 앞뒤 메시지를 붙인다(`api/routers/conversations/router.py:105-123`). 원 메시지를 다시 읽을 수 있는 경로다. 추천된 agent가 이것을 쓸지는 bourbon-agent·memory-api가 정한다(§10-3).

memory-api에는 인증이 없다(`verify_token`은 있지만 어느 router도 쓰지 않는다, `api/depends/tenant.py:4-6`).

### 6-3. topic-api — 분야(KIND)만 받는다

- 카탈로그는 KIND만 받는다. 분류 프롬프트가 "product, company, ... and one numbered or dated release"를 topic이 아니라고 적는다(`topic/catalog_import/review_llm.py:34-41`). 사용자 신호로 노드를 더하는 경로는 없고, 없는 것이 정책이다(`docs/catalog-maintenance.md:3-4`).
- 스카치 위스키는 편집에서 빠졌고(`too_specific`), 하이랜드는 카탈로그 어디에도 없다(`data/catalog_seeds/reviewed/food-drink.yaml:5851-5899`).
- 사용자 topic은 persona의 preferences 레이어에서 추출된다. facet은 `knowledge`·`engagement`·`affinity`·`duration`·`recency` + `volume`. "해 봤다"에 해당하는 facet은 없다.
- `/search/topics`는 lexical 검색(정규화, 형태소 분석 없음, ko/en/ja label과 alias)이고, 카탈로그에 없는 이름은 빈 목록이다(`topic/catalog/graph.py:57-71`).

**topic-api에 제품 노드를 요청하지 않는다.** 엔티티는 lived-knowledge의 레지스트리가 맡는다. topic-api는 분야와 관심 소스로 남는다.

### 6-4. bourbon-agent

- 대화 검색은 LLM이 고르는 tool(`search_conversations`)이고, 원문 대화를 BM25로 검색한다. personal knowledge의 context route는 어디서도 부르지 않는다.
- **대화 검색은 방이 기본이고, owner 본인의 기억은 topic 기준으로 더 닿는다.** PERSONAL 방에서는 owner의 기억 전체를 검색한다(PERSONAL clearance). PERSONAL 방 밖에서 `search_conversations`가 닿는 것은 대부분 그 방 사람들이 함께 나눈 대화이지만, owner의 기억 전체로 닿는 slice가 하나 더 있고 그 범위는 "owner가 이 방의 tier에 공개한 topic"이다. 이 범위는 코드로 강제되지 않고 프롬프트(`owner_topic_guidance`)로 지시된다(`bourbon_agent/agents/personal_agent/topic_memory.py:1-22`). 즉 owner 본인의 경험은 bourbon-agent가 topic visibility 기준으로 이미 쓴다. **다른 사용자가 다른 방에서 한 말에는 닿지 않는다** — 이 기능이 채우는 것은 그쪽이다.
- 질문에 답할 수 있는지 먼저 판단하는 게이트(answerability gate)가 없다. `recommend_agents` tool은 "추천해 달라"는 요청에만 불린다(예산 10초, `max_results=1`).
- agent가 agent에게 묻고 답을 합치는 코드는 없다. `moderator/__init__.py:12`가 `agent_recommender`를 "계획됨"으로 적어 두었을 뿐이다.
- **persona 추출은 사용자 단위로 모아서 한다.** `persona_extractor`는 `message_created` 가운데 `sender_type == "user"`만 받아(`persona_extractor/pipeline.py:94`) 그 사용자의 pending 방 집합에 방을 넣고, 사용자마다 한 칸인 deferq debounce를 민다(`persona_extractor/scheduling.py:47-75`). 조용해진 지 300초 뒤, 대화가 이어져도 1800초 안에 실행되고(`persona_extractor/config.py:42-44`), 한 번의 실행이 밀린 방들을 방 커서 다음부터 읽어 추출 LLM 한 번으로 처리한다(`pipeline.py:7-8`, 한 번에 최대 300개, `config.py:58`). 사용자 메시지가 3개·150자에 못 미치면 최대 2시간 보류한다(`config.py:48-53`). debounce 예약 실패는 로그만 남긴다(`scheduling.py:56-58`). lived-knowledge의 적재(§7-1)는 이 방식을 따르되 모으는 키를 방으로 둔다.

### 6-5. agent-discovery-api

- 타입 ① 파이프라인: expansion(LLM 1회) → grounding(topic-api 검색 + 모호할 때 disambiguation 1회) → 후보 조회 → 랭킹 → 조립. text→topic 구간 p50 1.77초 / p95 3.11초(disambiguation 게이트 on, `validation_results.md` §11-4), 요청 전체 p50 약 1.94초(추정).
- 미러: `visible_topic_rows`, `agents(… discoverable, agent_maturity …)`, `friends`, `departed_users`(R68).
- 카탈로그 복사본 3,174 topic(Wikidata 3,148 + 가상 노드 26, 가상 노드의 `source.qid`는 `N-…`). 위스키 계열 노드는 위스키·몰트·그레인·콘·아메리칸 위스키, 아일라·스페이사이드 싱글 몰트, 브랜드 예외 히비키·그랜츠다.

---

## 7. lived-knowledge 설계

`bourbon-lived-knowledge-api`(lived-knowledge). **lived knowledge**는 "직접 겪어서 알게 된 것"이라는 뜻이다 — 이 서비스가 저장하는 것은 사용자가 직접 겪은 경험, 취향, 요령, 사정이고, 사전·백과에 있는 사실과 대비된다. 일반 사실은 저장하지 않고, 전해 들은 것은 기본적으로 저장하지 않는다(전해 들은 사정을 `insider`로 둘지는 열린 항목 6).

### 7-1. 입력 — 방마다 모아서 처리한다

1. `bourbon.message_created`를 받는다(자기 큐, 자기 워커 — 이벤트 워커는 소비하는 repo가 소유한다). 바인딩은 문제없다는 답을 받았다(오너, 2026-09-28). 워커의 deferq가 쓰는 Redis DB 번호는 인프라에서 새로 할당받는다 — 로컬 구현 테스트(0-a단계)를 마친 뒤, dev에 올리기 전에 받는다(오너, 2026-09-29, §14).
2. **payload로 먼저 필터링한다**: `sender_type`이 사람이 아니면 버린다. `type`이 텍스트가 아니면 버린다(첫 버전). 남은 메시지도 **이때는 읽지 않는다.** 그 방을 pending으로 표시하고 방 단위 debounce를 민다.
   - pending 표시는 lived-knowledge의 PostgreSQL `room_cursors` 행(§7-5)에 `pending_since`를 쓰는 것이다. 방을 처음 보면 행을 만들고 `start_message_id`에 그 이벤트의 `message_id`를 둔다. 이벤트에는 이전 메시지 id가 없어서 "처음 받은 메시지 바로 앞"을 커서로 적을 수 없으므로, 커서(`cursor_message_id`)는 비워 두고 시작점을 따로 적는다. 그 이전의 대화는 백필이 맡는다.
   - 이벤트는 순서대로 온다는 보장이 없다(워커 동시성, 재전달). 뒤의 메시지 이벤트가 먼저 행을 만들면 앞의 메시지가 시작점 밖으로 빠지므로, 첫 실행이 행을 가져가기 전까지는 `start_message_id = LEAST(기존, 새 id)`로 더 앞선 id를 남긴다. 메시지 id는 uuid7이라 비교가 곧 시간순이다.
   - debounce는 deferq의 `.debounce(delay, uid=방마다 하나, max_wait=…)`다. bourbon-agent의 persona 추출과 같은 방식이고(§6-4), 키만 사용자가 아니라 방이다.
   - 값은 persona 추출과 같은 데서 시작한다 — 방이 조용해진 지 `ingest.debounce_seconds`(300초) 뒤, 대화가 계속 이어져도 `ingest.max_wait_seconds`(1800초) 안에. 경험 기록은 몇 분 늦게 쌓여도 추천에 문제가 없다.
3. **실행(방 하나)**: `room_cursors` 행을 lease로 잡고(§7-5), agent-context로 커서 다음의 메시지를 `after=<커서>`로 읽는다(한 번에 최대 100개, §6-1). 커서가 아직 비어 있으면(첫 실행) `after=<start_message_id>&inclusive=true`로 시작점의 메시지부터 읽는다. 커서 앞의 문맥은 `before=<커서>`(첫 실행이면 `before=<start_message_id>`)로 몇 개 읽는다. 한 실행이 읽는 양은 `ingest.max_messages_per_run`까지이고, 남으면 다시 debounce를 건다.
4. **창으로 나눈다**: 이어진 메시지 최대 `ingest.window_max_messages`개를 기록을 뽑는 메시지로, 그 앞의 `ingest.window_context_messages`개를 문맥으로 둔다. 메시지 사이가 `ingest.window_max_gap_seconds` 넘게 끊기면 새 창을 시작한다. 초기값은 memory-api personal build의 창(12개, 1시간, 문맥 3개, §6-2)에서 시작해 0단계에서 정한다.
5. **사전 필터**: 메시지마다 1인칭 경험·취향·요령 표현이 있는가를 규칙 또는 작은 분류기로 본다. 대부분의 메시지는 여기서 끝난다. 사전 필터가 놓친 것은 추출에서도 놓치므로 느슨하게 둔다.
6. 통과한 메시지가 하나라도 있는 창만 LLM 추출로 간다(§7-2). 창 안의 통과하지 못한 메시지도 문맥으로는 함께 넣는다 — "그거 마셔 봤어"는 앞의 질문 없이는 뜻이 없다.

**왜 방 단위로 모으나.**

| 방식 | LLM 호출 | 문제 |
|---|---|---|
| 메시지마다 | 사전 필터를 통과한 메시지 수 | 대화는 대개 여러 메시지가 이어서 온다. 같은 앞 턴을 메시지마다 다시 읽고 다시 넣는다 |
| 사용자마다(persona 추출의 방식, §6-4) | 사용자마다 한 번 | persona는 사용자 한 명의 프로필을 만들므로 사용자 단위가 맞다. 이 서비스는 한 방의 대화에서 그 방 사람 발신자 전원의 기록을 뽑는다. 사용자 단위로 모으면 세 사람의 그룹 방을 세 번 읽고 LLM도 세 번 부른다 |
| **방마다(이 문서)** | 대화 구간 하나를 한 번 읽고, 창마다 한 번 | 한 번의 실행이 여러 창이면 창마다 커밋한다(§7-5) |

persona 추출의 보류(사용자 메시지가 적으면 모일 때까지 미루는 것, §6-4)는 가져오지 않는다. "나 그거 마셔 봤어" 한 줄도 온전한 기록이고, debounce가 이미 이어진 메시지를 묶어 준다.

**뽑을 것이 없으면 다음 단계를 돌지 않는다.** 단계마다 입력이 비면 그 자리에서 끝난다.

| 단계 | 비었을 때 |
|---|---|
| 이벤트 | 사람이 보낸 텍스트가 아니면 pending에도 넣지 않는다 |
| 실행 시작 | 커서 다음에 사람이 보낸 텍스트가 없으면 커서만 옮기고 끝낸다 |
| 사전 필터 | 창에 통과한 메시지가 없으면 LLM을 부르지 않는다. 기록 교체(0개)와 커서 전진만 한다 |
| 추출 | 기록이 0개면 resolve·topic 매핑을 하지 않는다. 기록 교체(0개)와 커서 전진만 한다 |
| resolve | 대상이 없는 기록은 건너뛴다. 레지스트리에서 찾으면 memory-api를 부르지 않는다. 비슷한 후보가 없으면 병합 확인 LLM을 부르지 않는다(§7-3) |
| 지시어 해소 워커 | `reference_query`가 없는 기록은 대상이 아니다(§7-3) |

건너뛰는 것은 비용이 드는 단계(LLM·resolve·topic 조회)뿐이다. **"기록 0개"도 추출 결과이므로 저장한다** — 창의 사람 메시지들에 generation을 적고 기존 기록을 지운다(§7-5의 3·4). 새 메시지라면 지울 것이 없어 행 하나를 쓰는 것으로 끝나지만, 재추출에서는 이것이 없으면 이전 버전의 기록이 남는다.

**debounce가 사라져도 방이 잊히지 않게 한다.** deferq는 실패한 작업을 다시 전달하지 않고(재시도는 handler의 몫이다), persona 추출도 debounce 예약이 실패하면 로그만 남긴다(§6-4). 그래서 pending을 Redis가 아니라 PostgreSQL의 `pending_since`에 두고, 주기 sweep이 `pending_since`가 `ingest.max_wait_seconds`보다 오래된 방을 다시 debounce에 건다. 실행이 실패하면 커서를 옮기지 않고 다시 debounce를 건다(시도 횟수 상한, §11).

원문(창의 메시지와 문맥)은 이 흐름 안에서만 메모리에 있고, 저장하지 않는다. 로그·예외·Sentry에도 남기지 않는다 — 남는 것은 id, 길이, 사전 필터 판정, reason code다.

### 7-2. 추출과 경험 기록

LLM 한 번에 창 하나(기록을 뽑는 메시지들 + 그 앞의 문맥)를 넣고, 기록을 뽑는 메시지마다 **그 메시지를 보낸 사람 본인에 관한** 경험 기록 0~N개를 받는다. 기록마다 어느 메시지에서 나왔는지(창 안의 순번)를 함께 받아, `message_id`·`person_id`·`observed_at`·`room_id`는 그 메시지에서 채운다 — 기록의 소유자와 시각을 LLM이 정하지 않는다.

```text
lived_knowledge_records
  record_id           uuid
  person_id           uuid        보낸 사람 = 이 기록의 소유자
  kinds               text[]      experienced | prefers | practiced | insider 가운데 하나 이상, 중복 없음. 이 진술이 보여 주는 측면들 (규칙은 아래)
  entity_id           text | null 엔티티 레지스트리 id (§7-3). 대상은 모르고 상위만 알면 상위 엔티티 id. 상위 엔티티는 복사해 두지 않고 조회할 때 레지스트리에서 펼친다
  entity_type         text | null product | brand | organization | place | venue. 추출이 낸 대상의 종류. 대상이 해소되지 않은 기록을 나중에 resolve할 때의 힌트이기도 하다
  reference_query     text | null 대상이 지시어("이번 신상")로만 남았을 때의 검색 구절. 해소되면 null (§7-3)
  topic_ids           text[]      카탈로그 topic (§7-4)
  stance              text | null positive | negative | mixed
  specificity         smallint    0~3. 이름·수치·장소·시점이 얼마나 구체적인가
  summary             text        보낸 사람의 경험 한두 문장 (규칙은 아래)
  summary_lang        text        요약문 언어 (메시지 언어를 따른다)
  summary_en          text        같은 요약의 영어판 — 검색용
  summary_embedding   vector|null summary_en의 임베딩. 텍스트 경로가 모드 A일 때만(§7-6). 임베딩에 실패하면 null로 두고 나중에 채운다
  embedding_spec      text | null summary_embedding을 만든 설정(모델·차원·input_type). 지금 설정과 다르면 다시 임베딩한다(§7-6)
  terms               text[]      엔티티 이름의 표기들 (en/ko/ja, 별칭) — 검색용
  observed_at         timestamptz 메시지 시각
  message_id          uuid        원 메시지
  room_id, room_type  —           출처. 기획 단계에서는 필터링에 쓰지 않는다. 공개 범위 필터를 붙일 필드(§12)
  extractor_version   text        추출 프롬프트·스키마 버전 (표시용 이름)
  extractor_generation int        같은 버전의 정수 순서. 버전 비교는 이것으로 한다(§7-5)
  created_at          timestamptz
```

**추출 규칙**

- **보낸 사람 본인에 관한 것만.** 한 창에 여러 사람의 메시지가 있어도, 한 사람의 말을 다른 사람의 기록으로 옮기지 않는다. B가 "A가 그거 마셔 봤대"라고 하면 그것은 A의 기록도 B의 기록도 아니다(전해 들은 것, 열린 항목 6). 문맥 메시지에서는 누구의 기록도 뽑지 않는다. 선행 문서가 결정하지 못한 authorship 문제(한 사용자의 memory에 든 다른 사람의 말을 누구의 근거로 볼 것인가)가 여기서 대부분 해결된다.
- **기록 하나는 한 대상에 대한 한 진술이다.** "마셔 봤는데 별로였다"는 기록 하나에 `kinds = [experienced, prefers]`다. 대상이 다르거나 stance·요약이 갈리면 기록을 나눈다 — "이 병은 마셔 봤고, 셰리 캐스크는 대체로 좋아한다"는 대상이 달라 두 기록이다. `kinds`의 값마다 메시지에 근거가 있어야 한다. 한 모금 맛본 것을 `practiced`로, 병 하나의 평가를 취향 전체로 넓히지 않는다 — 배열이 되면 종류를 넉넉히 붙이기 쉬워서 이 규칙이 스칼라일 때보다 중요하다.
- **사실 진술은 기록하지 않는다**(§1-1). 1인칭이어도 "그 증류소는 하이랜드에 있어"는 버린다.
- **사람은 엔티티가 되지 않는다.** 지인·동료·가족은 레지스트리에도 `terms`에도 남기지 않는다. "민수랑 갔다"의 민수는 요약문에서도 "친구와"로 쓴다.
- **요약문은 보낸 사람의 경험만, 과장 없이.** 한두 문장, 메시지 언어로. "한 모금 맛봤다"를 "마셔 봤다"로 부풀리지 않고, 병 하나에 대한 평가를 취향 전체로 넓히지 않는다. "지난 주말" 같은 상대 시점은 쓰지 않는다(시점은 `observed_at`). 다른 참가자의 이름·발언, 개인정보(전화번호·주소 등)는 옮기지 않는다. 원문을 인용하지 않는다. `summary_en`은 같은 내용의 영어판이다 — 질문 쪽 `condition`이 영어라서(§9 T1) 질문과 기록을 같은 언어로 비교하려는 것이다.
- 창과 문맥으로도 대상을 알 수 없으면, 알 수 있는 상위 엔티티("글렌드로낙의 어떤 병")를 `entity_id`에 두고 `specificity`를 낮춘다. 그것도 모르면 `entity_id = null`. 대상이 "이번 신상"처럼 지시어로만 남았으면 이름을 지어내지 않고 `reference_query`를 함께 낸다(§7-3의 기록 쪽 지시어 해소).
- 대상마다 `entity_type`(`product` | `brand` | `organization` | `place` | `venue`)과, 쓰인 표기 그대로(`as_written`)와 영어 정식 이름(`canonical_en`)을 함께 낸다. memory-api personal build의 추출이 영어 정규 이름을 내는 것과 같은 방식이다(`extract.py:282`, §6-2). 언어가 달라 같은 대상이 따로 등록되는 것을 줄이고, 모두 레지스트리 resolve의 입력이다(§7-3).

**원문은 저장하지 않는다.** discovery가 추천된 agent에게 넘기는 것은 경험 기록과 요약문까지다. 원 메시지를 다시 읽을지, 읽는다면 어떤 경로와 scope로 읽을지는 bourbon-agent·memory-api가 정한다(§10-3, §15 요청 5). 원문의 기준은 bourbon-api와 memory-api에만 있고, lived-knowledge는 사본을 두지 않는다.

**요약문도 개인 정보다.** 요약문은 원문보다 축약되고 다른 참가자의 발화를 제거한 파생 데이터지만, 여전히 사용자의 개인 정보이며 공개 범위와 동의의 적용 대상이다. 그 사람의 취향, 간 곳과 시점, 건강·가족·직장에 관한 경험, 특정 제품에 대한 부정적인 평가, agent DM에서만 한 이야기가 담길 수 있다. 추천 이유로 요청자에게 보이므로(§9 T6) 서비스화 때 공개 범위와 동의를 정하는 대상이다(§12).

### 7-3. 엔티티 레지스트리

경험 기록끼리, 그리고 질문과 경험 기록 사이에서 같은 대상을 같은 id로 부르기 위한 테이블이다. 모든 사용자의 기록이 함께 쓴다.

```text
entities
  entity_id       text     "wd:Q…" (Wikidata) 또는 "rg:<uuid>" (레지스트리가 새로 만든 id)
  label           jsonb    언어별 이름
  entity_type     text     product | brand | organization | place | venue
  parent_ids      text[]   상위 엔티티
  qid             text | null
  created_at, merged_into

entity_aliases
  entity_id       text     entities.entity_id
  alias           text     표기 그대로
  alias_norm      text     정규화한 표기 (casefold, 공백·기호 정리). 찾기는 이것으로 한다
  lang            text | null
  mention_count   int      이 표기로 resolve된 횟수
  last_seen_at    timestamptz
  (entity_id, alias_norm) unique. 같은 alias_norm이 여러 엔티티에 있을 수 있다
```

alias는 테이블로 따로 둔다. 표기마다 몇 번 쓰였는지와 마지막으로 쓰인 때를 세어, 병합 워커의 판단과 0단계 측정에 쓴다. 누가 썼는지는 세지 않는다 — 레지스트리에 사람과 이름을 잇는 정보를 두지 않는다.

**lived-knowledge가 양쪽 resolve를 다 한다** — 추출할 때 기록의 엔티티를, 질문이 올 때 need의 엔티티를 같은 레지스트리로 resolve한다. 선행 문서에서는 질문 쪽(discovery)과 근거 쪽(memory-api 빌드)이 따로 resolve해서 어긋날 수 있었다(§3-2의 1번).

resolve 순서:

1. 이름(`as_written`과 `canonical_en` 둘 다)을 정규화해 레지스트리의 label·alias에서 찾는다. 결과는 **후보 목록**이다 — "Apple"·"야마자키"처럼 같은 이름의 엔티티가 여럿일 수 있다. 후보가 하나이고 `entity_type`이 맞으면 그 id다. **하나여도 `entity_type`이 맞지 않으면 채택하지 않고 2로 넘어간다** — 맞는 엔티티가 아직 등록되지 않았을 뿐일 수 있다("Apple"이 회사로만 있는데 질문은 과일). 여럿이면 `entity_type`으로 좁히고, 그래도 여럿이면 모호하다(`ambiguous`).
2. 없으면 memory-api `/knowledge/resolve`로 QID를 찾는다. 판정은 **mention마다** 한다(점수는 mention 사이에 비교할 수 없다):
   - `match.method`가 `alias_exact` 또는 `name`인 후보만 쓴다.
   - 후보의 `instance_of`가 `entity_type` 힌트와 맞지 않으면 쓰지 않는다(타입과 Wikidata 클래스의 대응표는 lived-knowledge가 둔다).
   - 점수의 최소 절대값은 두지 않는다. 점수는 mention끼리 비교할 수 없으므로, method와 타입 일치로 필터링한다.
   - 2위 점수 ÷ 1위 점수가 `registry.ambiguity_ratio` 이상이면(두 후보의 점수가 가까우면) 모호한 것으로 보고 QID를 붙이지 않는다.
   - 그렇지 않으면 1위를 `wd:` id로 등록하고, 이름을 alias에 더한다.
3. **QID도 없으면, 새로 만들기 전에 비슷한 기존 엔티티를 찾는다**(추출 쪽만).
   - 후보: 같은 `entity_type`이고, 문맥에서 상위 엔티티가 잡혔으면 그 하위 안에서, `alias_norm`·label의 `pg_trgm` 유사도가 `registry.candidate_similarity` 이상인 것 상위 `registry.candidate_limit`개. `as_written`과 `canonical_en` 둘 다로 비교한다. 같은 이름을 달리 쓴 대상이 가장 많이 모이는 곳이 같은 상위 엔티티 아래다("글렌드로낙 21"과 "글렌드로낙 21 팔리아먼트").
   - 후보가 있으면 LLM에 "같은 대상인가"를 한 번 묻는다. 넣는 것은 이름·종류·상위 엔티티 이름·alias뿐이고 메시지는 넣지 않는다. **확실하지 않으면 다르다고 본다.**
   - 같다고 판정되면 새 id를 만들지 않고 그 엔티티를 쓰며, 이 이름을 alias로 더한다.
   - 후보가 없으면 LLM을 부르지 않고 4로 간다.
4. `rg:` id를 새로 만들고(새로 나온 병, 동네 가게), 문맥에서 잡힌 상위 엔티티(글렌드로낙)를 `parent_ids`에 넣는다. `as_written`과 `canonical_en`을 alias로 넣는다.
5. 나중에 같은 대상이 QID로 resolve되면 `rg:` id를 `wd:` id로 병합한다. 병합 워커(아래)가 찾은 `rg:`끼리도 병합한다. 둘 다 `merged_into`를 쓰고, 기록은 조회할 때 병합된 id로 읽힌다.

레지스트리 쓰기(새 id, alias 추가)는 기록 쓰기와 따로 커밋한다. 기록 쓰기가 버려져도(탈퇴, 경합, §7-5) 레지스트리에 남는 것은 공개 이름뿐이라 해가 없다.

**잘못 합치는 것이 잘못 나누는 것보다 나쁘다.** 다른 대상을 하나로 합치면 엉뚱한 사람이 추천된다 — §3-2의 2번, 엔티티 매칭이 결과를 틀리게 만드는 경우다. 같은 대상이 둘로 나뉘면 엔티티 경로의 recall만 떨어지고, 상위 엔티티·topic·텍스트 경로가 그 사람을 다시 찾는다. memory-api personal build의 dedup도 같은 원칙이다(§6-2). 그래서 새로 만들 때는 보수적으로 확인하고, 모으는 것은 병합 워커가 따로 한다.

**병합 워커 — 따로 등록된 같은 대상을 모은다.** 레지스트리는 모든 사용자가 함께 쓰므로 표기 변형("팔리아먼트", "드로낙 21", "GlenDronach Parliament" …)이 사용자 수만큼 쌓이고, resolve 순서 3의 확인에서 같다고 판정되지 않아 따로 만들어진 `rg:` id도 생긴다.

1. 주기적으로, 같은 `entity_type`·같은 상위 엔티티 아래의 `rg:` 엔티티 쌍을 이름 유사도(label·alias 전부)로 모은다. 새 `rg:` id가 생긴 상위 엔티티 아래만 다시 본다.
2. 후보 쌍마다 resolve 순서 3과 같은 LLM 확인을 한다. 확실하지 않으면 합치지 않는다.
3. 같다고 판정되면 한쪽을 다른 쪽으로 병합한다(`merged_into`). 남는 쪽은 `wd:`가 있으면 그쪽, 아니면 기록이 더 많은 쪽, 같으면 먼저 만들어진 쪽이다. 흡수된 쪽의 label·alias는 남는 쪽의 alias로 옮긴다. `merged_into`는 늘 최종 엔티티를 가리키게 둔다 — 흡수된 쪽을 가리키던 id도 남는 쪽으로 옮긴다.
4. 기록은 다시 쓰지 않는다. 조회할 때 병합된 id를 모아 비교하므로(아래 "상위 엔티티는 조회할 때 펼친다") 병합은 레지스트리 몇 행을 바꾸는 일이다.
5. 잘못된 병합은 `merged_into`를 지워 되돌린다. 병합 전에 저장된 기록은 자기 `entity_id`를 그대로 갖고 있어 원래대로 돌아간다. 다만 병합 뒤에 저장된 기록은 처음부터 남는 쪽 id로 저장되어 되돌려도 나뉘지 않는다 — 기록의 `terms`에 표기가 남아 있어 다시 가를 근거는 있다(열린 항목 30).

**`entity_type` 힌트**: 추출 LLM은 기록의 대상마다, T1은 `entity_mentions`마다 `entity_type`을 낸다. 분야 이름(추출의 분야 이름, T1의 `probes`)도 함께 넘겨 같은 이름의 후보를 가르는 데 쓴다. 둘 다 이름의 종류일 뿐 개인 정보가 아니다.

**상위 엔티티는 조회할 때 펼친다.** 엔티티 E로 찾을 때 레지스트리에서 E의 하위 엔티티(`parent_ids`를 따라 내려간 것)와 E로 병합된 id를 모아 기록의 `entity_id`와 비교한다. 기록에 상위 엔티티를 복사해 두지 않으므로, 병합이나 상위 관계를 고쳐도 기록 쪽에 낡은 값이 남지 않는다.

**기록 쪽 지시어 해소.** A가 이름 없이 "이번 신상 마셔 봤어"라고만 하면 창과 문맥으로도 대상을 알 수 없다. 이때 "이번"은 질문 시각이 아니라 **메시지 시각** 기준이다.

1. 추출 때는 상위 엔티티(글렌드로낙)를 `entity_id`에 두고 `reference_query`를 함께 저장한다(§7-2). 추출 경로에서는 웹 검색을 하지 않는다 — 메시지마다 검색하면 비싸고 추출이 느려진다.
2. 별도 워커가 `reference_query`가 남은 기록만 골라, 메시지의 연월을 붙인 검색 구절로 웹 검색을 한다. e3llm은 chat completions의 `web_search_options`로 모델 자체의 검색(Gemini·OpenAI)과 내부 `search_web` 백엔드를 지원하고 검색 결과를 캐시한다(e3llm-api `README.md:14, 213`, `api/routers/chat/completions/examples.py:451-488`). 검색어에는 `reference_query`와 메시지 연월만 넣고 원문은 넣지 않는다. 후보를 가를 때 기록의 `entity_type`을 힌트로 쓴다.
3. 대상을 찾으면 위의 resolve 순서로 id를 얻고 기록의 `entity_id`를 그 id로 바꾸고 `reference_query`를 비운다. 이 갱신도 쓰기 트랜잭션이라 첫 statement에서 탈퇴를 확인한다(§7-5).
4. 찾지 못하면 상위 엔티티로 남기고 다음 주기에 다시 시도한다. 시도 횟수에 상한을 둔다.

이렇게 하면 bourbon-agent가 채워 보낸 질문의 이름과 기록 쪽이 같은 구체적인 이름에서 만난다.

질문 쪽 resolve는 1~2까지만 한다 — 질문 때문에 레지스트리에 새 id를 만들지도, alias를 더하지도 않고, 요청 경로에 병합 확인 LLM을 더하지 않는다. 대신 병합 워커가 모아 둔 alias 덕분에 1(label·alias에서 찾기)이 더 자주 맞는다. 질문의 이름이 레지스트리에도 Wikidata에도 없으면 그 이름(mention)은 `not_found`이고, 그 이름으로는 엔티티 경로를 돌지 않고 텍스트 경로에만 쓴다. 같은 need의 다른 이름이 resolve되면 그 이름으로 엔티티 경로를 돈다(§9 T3). resolve가 답하지 않으면 `unavailable`이고 레지스트리에서만 찾는다.

레지스트리에는 엔티티의 **공개 이름**만 있다. 누가 그것을 겪었는지는 경험 기록에 있고 레지스트리에는 없다. 사람은 등록하지 않는다(§7-2).

### 7-4. topic

추출 LLM이 기록마다 분야 이름 1~3개("malt whisky", "whisky")를 낸다. 가장 넓은 이름과 가장 구체적인 이름을 늘 함께 낸다 — 넓은 쪽은 topic-api가 persona에서 topic을 붙이는 방식과 같고(`topic/persona_topics/stages.py:58-64`), 구체적인 쪽은 공개 범위 판정이 가장 제한적인 topic을 따르므로(§12) owner가 구체적인 topic에 둔 visibility를 놓치지 않기 위해서다. lived-knowledge가 이 이름들을 topic-api `/search/topics`로 찾아 `topic_ids`에 넣는다. 엔티티가 없는 기록도, 엔티티 매칭이 어긋난 질문도 topic으로 찾을 수 있다.

### 7-5. 중복 처리·무효화·탈퇴·재추출

- **같은 메시지를 두 번 처리해도 결과가 같아야 한다.** `message_created`는 다시 전달될 수 있고, 재시도·백필·재추출이 같은 메시지를 또 읽는다. LLM은 같은 입력에도 다른 기록을 낼 수 있어 기록 하나하나에 안정적인 키를 붙일 수 없다. 그래서 **메시지 하나의 기록은 늘 한 번의 추출 결과 전체**로 두고, 어디까지 처리했는지는 **방 커서**로 나타낸다. 메시지마다 상태 행을 두지 않는다.
  - 버전은 이름 `extractor_version`(표시용)과 정수 `extractor_generation`(비교용) 둘로 둔다. "더 높은 버전"은 generation으로 비교한다.
  - 진행 테이블 `room_cursors(room_id, extractor_generation, start_message_id, cursor_message_id, pending_since, status, attempts, lease_owner, lease_until, updated_at)`. 키는 `(room_id, extractor_generation)`이다. `status`는 `idle | running | failed`이고, `pending_since`가 비어 있지 않으면 그 방에 처리할 메시지가 있다는 뜻이다(§7-1). `cursor_message_id`는 마지막으로 처리한 메시지이고, 비어 있으면 `start_message_id`부터(그 메시지 포함) 읽는다.
  - **같은 이벤트가 다시 와도 무해하다.** 이벤트가 하는 일은 `pending_since`를 채우고 debounce를 미는 것뿐이고, 실행은 커서 다음만 읽는다.
  - **실행은 claim해서 가져간다.** debounce가 실행되면 워커가 그 방의 행을 `SELECT … FOR UPDATE SKIP LOCKED`로 잡아, `running`이 아니거나 `lease_until`이 지났을 때만 `running`·`lease_owner`·새 `lease_until`을 쓰고 `pending_since`를 비운 뒤 커밋한다. 이미 다른 실행이 잡고 있으면 아무것도 하지 않는다 — 그 사이에 온 메시지는 `pending_since`를 다시 채우므로, 잡고 있던 실행이 끝날 때 보고 다시 debounce를 건다. 메시지 읽기와 LLM 호출은 길어서 트랜잭션 밖에서 하고, 행 잠금이 아니라 이 lease가 "누가 처리 중인가"를 나타낸다.
  - **결과는 창마다 한 트랜잭션으로 쓴다.** 순서는 다음과 같다.
    1. 탈퇴 확인 — 첫 statement. 창의 발신자 가운데 탈퇴한 사람의 기록은 넣지 않고 나머지만 넣는다.
    2. `room_cursors` 행을 `FOR UPDATE`로 잠그고, `lease_owner`가 자기이고 커서가 직전 창의 끝(첫 창이면 실행이 읽기 시작한 위치, 첫 실행이면 빈 값) 그대로인지 확인한다. lease가 끝난 뒤 다른 실행이 앞질렀으면 자기 결과를 버리고 실행을 끝낸다.
    3. 창의 기록을 뽑는 메시지들의 버전 확인(아래).
    4. 그 메시지들의 기존 기록 삭제, 새 기록 삽입.
    5. 커서를 창의 마지막 메시지로 옮기고 lease를 늘린다.
  - 사전 필터에서 끝난 창, 기록이 0개인 창도 **같은 트랜잭션을 그대로** 쓴다(넣을 기록이 없으니 1은 할 일이 없다). 3·4를 건너뛰면 두 가지가 깨진다.
    - 재추출에서 v1이 만든 기록을 v2가 "경험이 아니다"라고 판단해도 v1 기록을 지울 기회가 없다.
    - `message_extractions`에 v2가 남지 않으므로, 재추출하는 동안 계속 도는 v1 적재가 같은 메시지를 늦게 쓰면 아래의 버전 확인이 막지 못한다.
  - 그래서 3·4의 대상은 창의 **사람이 보낸 메시지 전부**다(사전 필터를 통과했는지, 기록이 나왔는지와 상관없이). agent가 보낸 메시지는 원래 기록이 생기지 않으므로 대상에서 뺀다. 늘어나는 것은 사람 메시지마다 `message_extractions` 한 행이다.
  - **커서는 성공한 창까지만 전진한다.** 창 하나가 실패하면(LLM·resolve·agent-context 실패) 그 창에서 멈추고, 커서는 그 앞에 남는다. 뒤의 창을 먼저 저장하지 않는다 — 커서 하나로 "여기까지 끝났다"를 말할 수 있게(memory-api personal build의 watermark와 같은 원칙). `attempts`를 올리고 다시 debounce를 건다. 시도 횟수가 `ingest.max_attempts`를 넘으면 그 창을 건너뛰고 커서를 옮긴다 — 창 하나 때문에 방 전체의 적재가 멈추지 않게. 건너뛴 창은 `skipped_windows(room_id, extractor_generation, first_message_id, last_message_id, reason, created_at)`에 남기고, 백필이 다시 처리한다.
  - **버전 사이의 경합도 막는다.** v1 추출이 늦게 끝나 먼저 저장된 v2의 결과를 덮으면 안 된다. 메시지마다 한 행인 `message_extractions(message_id PK, extractor_generation)`을 두고, 쓰기 트랜잭션은 커서 확인 다음 statement에서 창의 기록을 뽑는 메시지들(사람이 보낸 메시지 전부, 기록 0개 포함)의 행을 `SELECT … FOR UPDATE`로 잠근다(없으면 만든다). 저장된 generation이 자기보다 높은 메시지는 건너뛰고, 낮거나 같으면 기록을 교체하고 generation을 자기 것으로 둔다. 같은 generation의 두 실행은 위의 커서 확인에서 이미 한쪽이 버려졌다.
  - **재추출과 백필**: 새 `extractor_version`이 나오면 그 generation의 `room_cursors` 행을 만들고 `start_message_id`를 방의 첫 메시지로 두어(백필이 `before`로 거슬러 올라가 찾는다) 같은 방식으로 돈다. 메시지마다 이전 버전의 기록을 새 기록으로 바꾼다(원자적 교체). 한 메시지에는 한 버전의 기록만 있다. 재추출하는 동안에는 이전 generation의 적재를 계속 돌리고, 새 generation의 커서가 방의 끝을 따라잡으면 이전 것을 멈춘다 — 그 사이 새 메시지의 기록이 비지 않게. 이전 generation이 늦게 쓴 기록은 위의 버전 확인이 막는다.
- **같은 경험을 여러 번 말해도 경험의 폭이 부풀지 않아야 한다.** 한 사람이 같은 병 이야기를 열 번 하면 기록이 열 개다. 순위(§9 T4)는 기록 수가 아니라 서로 다른 엔티티 수와 서로 다른 날짜 수를 세고 상한을 둔다. 기록 자체는 지우지 않는다 — 어느 기록이 가장 잘 맞는지는 질문마다 다르다. 그래서 기록은 계속 쌓인다. 보존 기간과 정리 규칙은 열린 항목 32다.
- **메시지는 고쳐지지도 지워지지도 않는다**(§6-1). 그래서 원문의 수정·삭제를 따라갈 일은 없다. 기록이 무효가 되는 경우는 둘이다 — 그 사람의 **탈퇴**, 그리고 서비스화 때 정할 **범위 밖으로 나가는 것**(방이나 동의, §12).
- **탈퇴는 R68과 같은 방식이다.** `bourbon.user_deactivated`를 받으면 그 사람의 기록을 전부 지우고 id를 남긴다. 그리고 **기록을 만들거나 바꾸는 모든 쓰기 트랜잭션이 첫 statement에서 그 id를 확인한다** — 창마다의 추출 결과 쓰기, 백필, 재추출, resolve 재시도 뒤의 갱신 모두. 메시지는 지워지지 않으므로 탈퇴한 사람의 메시지는 원천에 남아 있고, 확인 없는 백필은 그 기록을 되살린다.
- **탈퇴 이벤트가 유실될 수 있다.** `user_deactivated`는 best-effort라(§6-1) 유실되면 탈퇴한 사람의 기록이 남는다. bourbon-api에는 탈퇴한 id 목록을 주는 route도, 발행을 보장하는 방식도 아직 없다. 그래서 `user_deactivated`를 탈퇴의 기준으로 쓴다(오너, 2026-09-28, §15 요청 1). bourbon-api의 내부 사용자 조회에 없다는 것만으로는 탈퇴로 볼 수 없다 — 해당 코드에 "absence must not be read as a deletion signal"이라고 적혀 있다.
  - **discovery와 같은 보장 수준이다.** discovery도 탈퇴를 이 이벤트 하나로만 안다(`worker/deactivation.py`, R68).
  - 두 서비스는 같은 이벤트를 각자의 큐로 받는다. 한쪽 큐에서만 유실되면 다른 쪽이 막는다 — discovery가 경험 소스의 후보를 자기 `departed_users`·`agents`로 한 번 더 필터링하고(§9 T3), 근거 조회 때도 같은 확인을 한다(§10-3).
  - 발행 자체가 실패하면 두 서비스 모두 모른다. bourbon-api에 발행을 보장하는 방법이 생기기 전까지 타입 ①②③과 함께 남는 위험이다.
- **재추출은 원천에서 다시 읽는다**(방식은 위의 재추출과 백필). 원문을 저장하지 않은 대가이고, 그래서 백필 경로를 처음부터 둔다. 백필도 위의 탈퇴 확인을 거친다.

### 7-6. 저장소 — PostgreSQL을 권장한다

lived-knowledge가 하는 일을 기준으로 두 후보를 비교한다.

| 필요한 것 | PostgreSQL | OpenSearch |
|---|---|---|
| 탈퇴 확인을 쓰기 트랜잭션의 첫 statement에 두고, 기록 교체와 방 커서 전진을 같은 트랜잭션에 두기(§7-5) | 그대로 된다. discovery의 R68 구현(advisory lock + 테이블)과 같은 방식으로 쓴다 | 트랜잭션이 없다. 확인과 쓰기 사이의 경합(race condition)을 따로 막아야 한다 |
| 기록 ↔ 레지스트리 ↔ 사람 조인, `rg:`→`wd:` 병합 | 조인과 트랜잭션으로 자연스럽다 | 비정규화해 두고 병합할 때 재인덱싱 |
| `entity_id`·`topic_ids`로 찾기, 레지스트리에서 하위 엔티티 펼치기 | 배열 컬럼 + GIN 인덱스, 재귀 CTE | keyword 필드 term 쿼리, 펼치기는 따로 |
| 경로마다 사람별 상위 K명 | window function(`row_number() over (partition by …)`) | terms aggregation + top_hits |
| 요약문 텍스트 검색 | `summary_en`에 두 모드(아래) — pgvector 임베딩, 또는 영어 full-text(`tsvector`). 이름 표기에는 `pg_trgm` | BM25, 언어별 analyzer(nori·kuromoji). 벡터 검색도 있다 |
| 규모 | 사용자 10만 × 사용자당 기록 수백 = 수천만 행까지 무리 없다(추론, 0단계에서 기록 수를 잰다) | 더 큰 규모에 유리 |
| 운영 | discovery와 같은 방식(공용 RDS에 DB 하나, alembic) | memory-api와 같은 AOSS. 탈퇴 기록 같은 트랜잭션이 필요한 데이터는 결국 PostgreSQL에도 두게 되어 저장소가 둘이 된다 |

**PostgreSQL을 권장한다.** 가장 중요한 요구인 "탈퇴한 사람의 기록이 되살아나지 않게 하기"가 트랜잭션에 기대고, 데이터가 관계형이다. 텍스트 검색은 `summary_en`을 두어 영어 하나로 모았기 때문에 PostgreSQL 안에서 할 수 있다 — 아래 두 모드 모두 PostgreSQL에서 돈다. 메시지 언어로 쓴 요약(`summary`)은 보여 주기용이고 검색하지 않는다.

**텍스트 경로의 두 모드 — 2단계에서 둘 다 만들어 비교하고 하나를 고른다.** 텍스트 경로는 이름도 topic도 맞지 않을 때 사람을 찾는 유일한 경로이고, "압력이 높을 때", "혼자 가기 좋은" 같은 조건은 요약문 매칭으로만 반영된다(§9 T3). 그런데 요약문은 나중에 올 질문을 모르는 채로 쓰이므로, 질문의 `condition`과 같은 뜻을 다른 단어로 말한 경우가 흔하다 — "for beginners"와 "the first whisky they bought". 단어가 겹치는지만 보는 검색(`tsvector`, `condition` 하나)으로는 이런 기록을 못 찾는다. judge(§9 T4-a)는 이미 찾은 후보만 보므로 이 문제를 풀지 못한다 — 찾는 단계에서 풀어야 한다.

| | 모드 A — 임베딩 검색(`embedding`) | 모드 B — 쿼리 확장(`paraphrase`) |
|---|---|---|
| 찾는 방식 | `condition`의 임베딩과 가까운 `summary_embedding`(pgvector, cosine) | `condition`과 `condition_variants`(§9 T1)를 표현마다 `tsquery`로 만들어 OR로 묶고 `ts_rank`로 순위. 모든 단어를 요구하는 쿼리 하나로 이어 붙이면 오히려 덜 찾힌다 |
| 적재 때 | 기록마다 `summary_en`을 임베딩해 저장 | 없음 |
| 질문 때 | lived-knowledge가 need마다 `condition`을 임베딩(1회). 문장을 생성하는 호출이 아니다 | T1의 출력이 조금 길어질 뿐, 호출은 늘지 않는다 |
| judge | 1회 | 1회 + 재시도 최대 `judge.max_retries`번(§9 T4-a) |
| 강점 | 단어가 달라도 뜻이 가까운 표현 | 바꿔 말할 표현이 예상되는 경우("entry level", "first bottle") |
| 약점 | 임베딩 모델과 호출 경로가 하나 더 생긴다. 쿼리 안 필터와 근사 최근접 검색(ANN)이 함께 걸릴 때의 recall(아래) | 연결에 추론이 필요한 표현("마감 직전에 밤새며" ↔ "압력이 높을 때"). 조건만 있는 need에서는 흔한 단어만 겹친 기록이 상위 K를 채운다 |
| 지연 | 거의 고정 | 재시도마다 늘어난다 |

- **임베딩은 lived-knowledge가 한다.** 기록과 질문을 같은 모델로 바꿔야 하므로, 양쪽을 가진 쪽이 맡는다. 호출은 e3llm의 `POST /v1/embeddings`로 한다(§15 요청 16) — 추출 LLM과 같은 경로라 provider 인증을 lived-knowledge가 갖지 않는다.
- **임베딩 설정 셋은 한 묶음으로 고정한다.** 모델, 차원, `input_type`(무엇에 쓰는 임베딩인가) 중 하나라도 바뀌면 이미 저장된 벡터와 새 질문의 벡터가 비교되지 않는다. 그래서 기록마다 `embedding_spec`을 남기고, 설정을 바꾸면 모든 기록을 다시 임베딩한다(백필, §7-5와 같은 방식).
  - `input_type`을 쓴다면 기록의 `summary_en`은 `document`, 질문의 `condition`은 `query`로 짝을 맞춘다. Gemini에서는 `RETRIEVAL_DOCUMENT`·`RETRIEVAL_QUERY`로 바뀌어, 저장된 문서와 그것을 찾는 질의를 서로 다르게 임베딩한다(비대칭 검색). 쓸지는 비교로 정한다(§13-3).
  - 차원은 768~1024를 기본으로 본다. pgvector의 `vector` 타입 HNSW 인덱스는 2000차원까지라 `gemini-embedding-001`의 기본 3072는 줄여서 저장해야 하고, 한두 문장짜리 영어 요약에는 이 정도면 충분하다고 본다(추론).
- **점수는 need 안의 순위로만 쓴다.** cosine 값 자체는 좁은 범위에 몰려 기준선으로 쓰기 어렵다 — 문장 한 쌍으로 잰 예비 값에서 맞는 문장과 다른 문장의 차이가 0.588 대 0.503이었다(2026-10-07, `gemini-embedding-001` 768차원). 그래서 일정 점수 이상을 거르지 않고, 경로마다 상위 K를 순위로 뽑는다. 요약문 매칭을 need 안의 순위로만 쓰는 원칙(§9 T3)과 같다.
- **쿼리 안 필터와 근사 최근접 검색(ANN).** 볼 수 없는 후보는 자르기 전에 뺀다(§9 T3). HNSW 같은 ANN 인덱스는 인덱스에서 가까운 것을 먼저 꺼낸 뒤 조건을 걸기 때문에, 필터가 많이 걸러 내면 K명보다 적게 나온다. pgvector 0.8의 iterative index scan을 쓰거나(로컬 compose 이미지는 0.8.7), 기록 수가 작은 동안은 인덱스 없이 exact search(전수 비교)로 찾는다. exact search와의 recall 차이를 2단계에서 잰다.
- 두 모드 모두 이름 표기(`terms`)는 지금처럼 `pg_trgm`으로 비교한다. 바뀌는 것은 `summary_en` 쪽뿐이다.
- 모드는 discovery의 설정 레지스터 값 `experience.text_mode`(`embedding` | `paraphrase`)로 정하고, 조회 요청에 실어 보낸다(§10-2). 평가 하네스는 요청마다 바꿀 수 있다 — 같은 질문 세트로 두 모드를 비교하기 위해서다(§13-3).
- **운영에는 하나만 남긴다.** 고르는 기준을 비교 전에 정하고(§13-3), 고른 뒤 다른 모드의 코드는 지운다. 두 모드를 함께 유지하면 저장소·테스트·장애 대응이 모두 두 배가 된다.
- 모드 A는 공용 RDS에서 pgvector 확장을 쓸 수 있어야 한다(§15 요청 15). 쓸 수 없으면 모드 B만 만든다.

**다시 볼 조건**: 0·2단계에서 요약문 검색의 품질이 부족하면(§13-2) — 예를 들어 영어로 옮기면서 제품명·지명이 바뀌거나 빠져 매칭이 떨어지면 — 검색만 OpenSearch로 옮기고 기록의 기준은 PostgreSQL에 둔다. lived-knowledge가 memory-api로 옮겨 가는 날에도 같은 판단을 다시 한다.

### 7-7. 조회

discovery 한 곳을 위한 조회 route 둘(후보 조회, 근거 조회)을 둔다(§10-2). **discovery가 경험 기록을 복제해 두지 않는다** — lived-knowledge는 우리가 만들고 이 조회를 위해 설계하므로, 선행 문서의 폴링 루프·manifest cursor·reconciliation이 필요 없다. 대신 추천 요청마다 호출하는 런타임 의존성이 되고, lived-knowledge가 답하지 않을 때의 동작을 정한다(§11).

**topic visibility 미러도 lived-knowledge에 둔다**(§12). `topic_visibility(user_id, topic_id, visibility)` — id와 tier만, 모든 tier(`public`·`friends`·`private`·`hidden`). 자기 워커가 `bourbon.topics_updated`·`bourbon.topic_visibility_changed`를 받아 topic-api를 모든 tier로 다시 읽는다 — discovery 워커와 같은 방식(유저 단위 debounce, `consistent=true` 읽기, 계약 §9-1·R55·R56)이다. 탈퇴 때 그 사람의 행을 지운다. 상위 topic을 따라 올라가는 판정(§12)을 위해 카탈로그의 부모 관계도 둔다 — discovery의 `catalog_edges`와 같은 방식으로 카탈로그를 복사한다. discovery는 이 미러를 갖지 않는다 — discovery의 저장소에는 지금처럼 공개된 row만 있다(불변식 1).

**보장 수준은 discovery의 `visible_topic_rows`와 같다.** 판정은 요청 시점의 로컬 미러로 한다. 이벤트가 늦는 동안에는 이전 공개 범위가 적용되고, 기획 단계에서는 이 지연을 무시한다(오너, 2026-09-28). 이벤트가 유실되면 — `topic_visibility_changed`는 쓰기 뒤 best-effort 발행이다(R55) — 그 사람의 다음 topic 이벤트까지 미러가 낡은 채 남는다. 이것은 `visible_topic_rows`도 같다. 철회 반영을 강화한다면(주기 재조회, 근거를 답변에 넣기 직전 원본 확인 등) 두 미러를 함께 강화한다(열린 항목 28).

### 7-8. 비용

- 추출 LLM은 **사전 필터를 통과한 메시지가 있는 창**마다 1회다(§7-1). 메시지마다 부를 때보다 호출 수가 줄고, 메시지마다 반복해서 넣던 앞 턴도 창마다 한 번만 들어간다(추론). 물량은 모른다 — 하루 메시지 수 × 사람 발신 비율로 읽을 양을, 창 크기와 사전 필터 통과율로 호출 수를 추정하고, dev에서 통과율과 창 크기 분포부터 잰다(§13-2).
- 병합 확인 LLM은 새로 만들려는 이름에 비슷한 후보가 있을 때만 1회, 그리고 병합 워커의 후보 쌍마다 1회다(§7-3). 이름·종류만 넣는 작은 호출이다.
- 추출도 e3llm을 쓴다. 추천 요청과 같은 proxy를 쓰면 배치 부하가 추천 요청의 tail latency(p95·p99)를 늘릴 수 있다. 추출은 우선순위가 낮은 별도 한도(동시성 상한)로 돌리는 것이 맞다고 보고, 가능한지는 e3llm 쪽에 묻는다. 이 요청은 나중에 다룬다(오너, 2026-09-28, §15 요청 13).
- 웹 검색은 대상이 지시어로만 남은 기록에만, 추출과 따로 비동기로 한다(§7-3). 물량은 그런 기록의 비율로 정해진다 — 0단계에서 잰다(§13-2).
- 텍스트 경로가 모드 A면(§7-6) 기록마다 임베딩 1회(적재 때)와 need마다 임베딩 1회(질문 때)가 더해진다. 짧은 요약문 하나를 벡터로 바꾸는 호출이라 추출 LLM보다 훨씬 싸다(추론). `gemini-embedding-001`과 `text-embedding-*`는 e3llm이 100개씩 묶어 부르고, 그 밖의 Gemini 임베딩 모델은 Vertex에서 요청 하나에 텍스트 하나만 받아 텍스트마다 따로 부른다(프로세스당 동시 8개까지). 모드 B는 적재 비용이 늘지 않는다.

---

## 8. 두 소스

| | 관심 소스 | 경험 소스 |
|---|---|---|
| 데이터 | discovery의 `visible_topic_rows` | lived-knowledge의 `lived_knowledge_records` |
| 어디서 오나 | topic-api가 persona의 preferences에서 뽑은 topic | lived-knowledge가 메시지에서 뽑은 경험 기록 |
| 담긴 정보 | "이 분야에 관심을 드러냈다"와 관심 강도 | "이것을 겪었다·좋아한다·해 봤다·안다"와 언제, 어땠는지 |
| 찾는 기준 | topic | 엔티티, 상위 엔티티, topic, 요약문 텍스트 |
| 지금 있나 | 있다(타입 ①②③이 쓰는 것) | 새로 만든다 |
| 공개 범위 | topic tier와 `discoverable`을 쿼리 안에서 건다(R17) | 기록의 topic에 대한 owner의 visibility를 따른다. 규칙은 정했고, 필터는 서비스화 때 건다(§12) |

관심 소스는 경험 소스가 없거나 답하지 않을 때의 폴백이면서, 경험 소스가 놓친 사람을 찾는 보조 경로다. 관심 소스만으로 추천된 사람은 "관심이 있는 사람"으로만 소개한다(§9 T6).

---

## 9. 추천 설계 (discovery)

### T0. 트리거와 요청 (bourbon-agent — 이 문서의 범위 밖)

언제 recommend tool을 부를지는 bourbon-agent가 정한다. 요청자 본인의 memory로 답할 수 있는지, 명시적 요청인지 자동 호출인지도 그쪽의 판단이다. 이 문서는 그 판단을 정하지 않는다. discovery가 그쪽의 요청에 기대하는 것만 적는다.

**기대하는 것 — 지칭을 채워 보낸다.** "글렌드로낙 이번 신상"처럼 시점이나 맥락에 따라 대상이 달라지는 지칭은 bourbon-agent가 구체적인 이름으로 채워 보낸다. 대화 맥락에 이름이 있으면 그것으로, 없으면 그쪽의 `search_web` tool(`bourbon_agent/scraper/tools.py:92`)로 찾는다.

```text
사용자:       글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어
question:    글렌드로낙 21 팔리아먼트(글렌드로낙 신상) 마셔 본 사람이랑 이야기해 보고 싶어
```

**discovery는 요청 경로에서 웹 검색을 하지 않는다.** bourbon-agent는 이미 대화 맥락과 검색 tool을 갖고 있고, discovery가 또 검색하면 bourbon-agent의 10초 예산 안에 LLM과 검색 호출이 쌓인다. 채워지지 않은 지칭이 오면 T1이 `reference_unresolved`로 표시하고 그 지칭은 `condition`으로만 반영한다. 이 비율을 decision log에 남겨 bourbon-agent에 알려 준다(§13-1). 웹 검색이 필요한 곳은 기록 쪽이다 — 사람들이 이름 없이 말한 경험을 lived-knowledge가 나중에 해소한다(§7-3).

**요청자 본인의 기억은 bourbon-agent가 쓴다.** 개인 방에서는 owner의 기억 전체를, 다른 방에서는 owner가 그 방의 tier에 공개한 topic 범위의 기억을 대화 검색으로 찾는다(§6-4). 그래서 discovery는 요청자 본인의 기록을 돌려주지 않고, 요청자를 후보에서 빼기만 한다.

참고로 전할 것: 이 기능에서 더 위험한 실패는 사람이 필요한 질문에 모델이 사전학습 지식으로 답해 버리고 tool을 부르지 않는 쪽이다. 호출률은 bourbon-agent 쪽에서 낼 지표로 요청한다(§13-4, §15 요청 12).

### T1. 질문 분석 — expansion을 본뜬 별도 프롬프트

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
     "stance": null,
     "entity_mentions": [{"text": "GlenDronach", "as_written": "글렌드로낙", "entity_type": "brand"},
                         {"text": "GlenDronach 21 Parliament", "as_written": "글렌드로낙 21 팔리아먼트", "entity_type": "product"}],
     "condition": "new release",
     "condition_variants": ["newly launched", "latest bottling"],
     "reference_unresolved": false}
  ]
}
```

- `people_needed`: 질문이 사람의 경험을 필요로 하는가. `false`면 이후 단계를 돌지 않고 `mode: none`, `empty_reason: answerable_without_people`.
- `kind`: `experienced` | `prefers` | `practiced` | `insider` | `null`(종류 무관). 경험 기록의 `kinds`에 들어가는 값과 같다. need 쪽은 스칼라로 둔다 — "마셔 보고 좋아한 사람"은 `kind=experienced`·`stance=positive`로 나타낸다.
- `precision`: `exact` | `related`(§3-3 규칙 5).
- `recency`: `recent` | `null`. discovery가 설정 레지스터 값에 따라 `recency_days`로 바꿔 lived-knowledge에 넘긴다.
- `stance`: `positive` | `negative` | `null`(무관). 질문이 특정 방향의 경험을 찾을 때만 쓴다 — "셰리 캐스크 싫어하는 사람"이면 `negative`. 기록의 `stance`와 비교한다(T3).
- `entity_mentions`: 질문이 이름으로 가리킨 대상 0~2개. `text`는 영어 정식 이름, `as_written`은 질문에 쓰인 표기, `entity_type`은 레지스트리 resolve의 힌트(§7-3). 분야 이름은 넣지 않는다. 모델이 모르는 것("이번 신상")은 지어내지 않는다. 한 need의 이름들은 브랜드와 그 제품처럼 상하 관계여야 한다 — 서로 관계없는 대상이 여럿이면("21 팔리아먼트와 18 알라데일") need를 나눈다. 가장 구체적인 이름이 `precision: exact` 충족의 기준 대상이다(T3).
- `reference_unresolved`: need의 대상이 "이번 신상"·"올해 한정판"처럼 시점이나 맥락에 기대는 지칭인데 질문과 `context` 어디에도 구체적인 이름이 없으면 true. 그러면 그 지칭은 `condition`(요약문 매칭)으로만 반영하고 — 함께 적힌 이름은 엔티티 경로에 그대로 쓴다 — `degraded`에 `reference_unresolved`를 단다. bourbon-agent가 지칭을 채워 보내는지 재는 지표이기도 하다(§9 T0).
- `condition`: topic·엔티티에 담기지 않는 조건을 영어 한 구절로. 요약문(`summary_en`) 매칭에 쓴다(T3). 질문에서 나와 lived-knowledge로 가는 텍스트는 이것과 `condition_variants`, `entity_mentions`뿐이다.
- `condition_variants`: `condition`을 다른 말로 바꾼 영어 구절 2~4개. 요약문이 같은 뜻을 다른 단어로 썼을 때도 찾히게 하려는 것으로, 텍스트 경로가 모드 B일 때만 쓴다(§7-6). 두 모드의 비교가 T1의 차이로 흐려지지 않게, T1은 모드와 관계없이 같은 프롬프트로 낸다. `condition`과 같이 사용자의 글로 다룬다(불변식 7).
- `probes`는 지금처럼 분야 이름이다.

규칙:

- 호출은 한 번이다. **타입 ①의 프롬프트는 한 글자도 바꾸지 않고** 그것을 본뜬 별도 프롬프트를 새로 둔다. expansion 프롬프트와 grounding 게이트는 서로를 전제로 쓰여 있고, 둘이 어긋나면 422 비율이 크게 달라진다 — R60의 실측에서 게이트를 끈 쪽은 질문의 26%가 422였다.
- need 상한은 3.
- 스키마 검증에 실패한 필드는 후보가 넓어지는 쪽으로 폴백한다 — `people_needed=true`, `importance=required`, `kind=null`, `precision=related`, `recency=null`, `stance=null`, `entity_mentions=[]`, `condition=null`, `condition_variants=[]`, `reference_unresolved=false`. `degraded`에 `need_fields_defaulted`.
- 질문 원문은 로그·예외·Sentry에 남기지 않는다(불변식 7).

**대안 — 질문 분석을 bourbon-agent의 tool 인자로 옮기기.** bourbon-agent의 모델은 recommend tool을 부를 때 이미 질문을 읽고 있다. tool 인자에 need 필드(`people_needed`, `kind`, `precision`, `recency`, `stance`, `entity_mentions`, `condition`, 분야 이름)를 넣게 하면 discovery의 T1 LLM 호출이 없어진다.

| | discovery의 T1 (이 문서의 기본) | bourbon-agent의 tool 인자 |
|---|---|---|
| 지연 시간 | 요청 경로의 가장 긴 단계(p50 1~2초) | 그만큼 줄어든다. 턴 안의 tool call 인자가 조금 길어질 뿐이다 |
| LLM 호출 | 질문당 1회 더 | 없음 |
| 추출 품질 관리 | 우리 프롬프트, 우리 테스트, 우리가 측정 | bourbon-agent의 tool 설명과 그쪽 LLM에 기댄다. 필드가 틀려도 우리가 고칠 수 없다 |
| 계약 | 요청은 질문 원문 | 요청이 구조화된 need 목록이 된다. 계약이 무거워지고, 필드가 늘 때마다 두 repo가 함께 바뀐다 |
| 폴백 | T1이 실패하면 질문 그대로 | 인자가 비거나 잘못되면 discovery가 T1을 돌리는 경로가 여전히 필요하다 |

1단계는 discovery의 T1로 시작하고, 지연 시간이 문제가 되면 이 대안을 검토한다. 두 방식을 같은 질문 세트로 비교할 수 있게, 요청에 need 목록이 있으면 T1을 건너뛰는 옵션을 처음부터 둘지는 열린 항목 18이다.

### T2. topic 찾기

타입 ①의 grounding 그대로 — probe로 topic-api 검색, 규칙으로 하나를 고르고, 모호할 때만 disambiguation 1회. 결과는 need마다 topic 하나 또는 없음.

엔티티는 discovery가 resolve하지 않는다. `entity_mentions`를 이름 그대로 lived-knowledge에 넘기고, lived-knowledge가 경험 기록과 **같은 레지스트리로** resolve한다(§7-3).

| topic | 엔티티 이름 | 이 need는 |
|---|---|---|
| 찾음 | 있음 | 모든 경로로 후보를 찾는다 |
| 찾음 | 없음 | topic·텍스트 경로로 |
| 못 찾음 | 있음 | 엔티티·텍스트 경로로(경험 소스만) |
| 모호 | 있음 | topic을 쓰지 않고 엔티티·텍스트 경로로(모호한 것은 쓰지 않는다 — §3-3 규칙 3과 같은 원칙) |
| 못 찾음 | 없음 | `condition`이 있으면 텍스트 경로로(경험 소스만), 없고 required면 422 `grounding_failed` |
| 모호 | 없음 | required면 422 `grounding_ambiguous`, optional이면 그 need를 빼고 `degraded`에 `need_dropped` |

**topic-api가 답하지 않을 때**는 타입 ①과 달리 곧바로 503을 내지 않는다. 이 타입에는 topic 말고도 엔티티·텍스트 경로가 있다.

| 상황 | 동작 |
|---|---|
| 모든 required need에 엔티티 이름이나 `condition`이 있다 | 엔티티·텍스트 경로로 계속 + `degraded`에 `topic_unavailable`. 관심 소스는 topic이 없어 쓰지 못한다 |
| 엔티티 이름도 `condition`도 없는 optional need | 그 need를 빼고 계속 + `need_dropped` |
| 엔티티 이름도 `condition`도 없는 required need가 있다 | 503 — 그 need는 볼 방법이 없었다(불변식 8) |
| lived-knowledge도 답하지 않는다 | 503 |

### T3. 후보 모으기

**관심 소스 — discovery DB.** `visible_topic_rows`에서 need의 topic(+ `catalog_edges`로 펼친 하위 topic)을 공개한 사람. 관심 강도는 `topic_score`·`topic_maturity`다(§4-1).

**경험 소스 — lived-knowledge 조회 1회**(§10-2). need마다 topic id 목록(discovery가 하위 topic까지 펼쳐서), 엔티티 이름과 `entity_type`, `kind`, `stance`, `recency_days`, `condition`을 넘기면, lived-knowledge가 네 경로로 경험 기록을 찾아 사람별로 묶어 돌려준다.

```text
엔티티 경로      entity_id = resolve된 엔티티 (+ 병합된 id)             precision=exact일 때의 주 경로
상위 엔티티 경로  entity_id ∈ 레지스트리에서 펼친 하위 엔티티            하위 엔티티(예: QID가 없는 신제품)를 겪은 사람
topic 경로       topic_ids ∋ need의 topic들                            엔티티가 어긋나거나 없을 때
텍스트 경로      summary_en·terms가 condition·엔티티 이름과 매칭(§7-6)   다른 경로가 모두 빗나갔을 때
```

- 경로마다 상위 K명(설정 레지스터, 초기 25)을 뽑아 합친다. 전체 점수로 상위 N명을 자르지 않는다 — 소수의 엔티티 경험자가 다수의 분야 경험자에 묻히지 않게.
- **볼 수 없는 후보는 자르기 전에 뺀다.** 자른 뒤에 빼면 볼 수 없는 후보가 K자리를 차지해 볼 수 있는 후보를 밀어낸다. 그래서 lived-knowledge가 경로별 상위 K명을 뽑는 쿼리 **안에서** 뺀다(R17과 같은 원칙).
  - 공개 범위(필터는 서비스화 때 켠다, §12): private·hidden 기록을 뺀다. `friends` 기록은 요청의 `friend_owner_ids`에 있는 owner의 것만 남긴다.
  - 도달 가능성: owner가 요청자의 친구(`requester_friend_ids`)이거나 public topic을 하나 이상 가진 사람만 남긴다. agent DM 게이트는 요청자와 owner 사이만 보므로, 여기서는 보는 사람 전원이 아니라 요청자의 친구로 판정한다. public topic이 있는가는 lived-knowledge의 visibility 미러로 계산한다 — bourbon-api의 `agents.public`이 곧 이 조건이다(R57).
  - 두 목록 모두 discovery가 `friends` 미러로 만든다. `friend_owner_ids`는 보는 사람 모두와 친구인 owner, `requester_friend_ids`는 요청자의 친구다. lived-knowledge는 이 목록들을 그 요청 안에서만 쓰고 저장하지 않는다.
  - 쿼리 밖에 남는 조건(`agents` 조인, 탈퇴자, bourbon-api 게이트의 `enabled`·활성 상태)은 discovery가 아래에서 한 번 더 건다. 이 차이는 작아서, 경로마다 K보다 조금 더 받아(`per_path_limit` + 여유분) 흡수한다. 경로마다 lived-knowledge가 `has_more`(받은 한도를 채우고도 더 있었는가)를 돌려준다. **`has_more`인 경로가 사후 필터 뒤 K명에 못 미치면** 그 need는 불완전으로 다룬다(§11) — 필터 때문에 잘렸고 더 가져올 후보가 있었다는 뜻이므로. `has_more`가 아니면 후보를 전부 읽은 것이라 K명보다 적어도 완전하다. 애초에 해당하는 사람이 3명뿐인 검색을 불완전으로 표시하지 않기 위해서다.
- `kind`·`stance`·`recency`는 **필터링 조건이 아니라** 경로 안의 순위 조건이다. 종류가 다른 기록도 후보가 되되 낮은 순위로 — T1의 `kind` 판정이 틀렸을 때도 후보가 사라지지 않게.
- 네 경로의 모든 기록에 `condition`과 need 엔티티의 표기들(resolve된 엔티티의 label·alias)을 기록의 `summary_en`·`terms`와 비교해 요약문 매칭 순위를 붙인다. **"이번 신상" 같은 조건은 여기서만 반영된다.** `summary_en`을 비교하는 방식은 텍스트 경로와 같은 모드를 따른다(§7-6).
- 텍스트 경로가 있어서, 엔티티를 찾지 못했거나(`not_found`) topic이 없는 need도 후보를 얻는다(§3-3 규칙 1).
- 응답은 사람별로: 경로별 기록 수, 가장 잘 맞은 기록 몇 개(`record_id`, `entity_id`, `kinds`, `stance`, `specificity`, `observed_at`, 매칭 순위, 요약문, `audience`), 서로 다른 엔티티 수·날짜 수(T4의 경험의 폭). need별로 `complete`(네 경로를 모두 돌았는가 — lived-knowledge 안의 timeout·장애로 빠진 경로가 없는가)와 경로별 `has_more`.

**경험 소스의 사람은 discovery가 다시 필터링한다.** 위 쿼리 안의 필터를 믿지 않고 방어로 한 번 더 건다.

- `person_id`를 `agents.owner_user_id`로 조인해 `agent_id`를 얻는다. 조인되지 않으면 뺀다.
- `departed_users`에 있으면 뺀다.
- **요청자가 대화를 시작할 수 있는 사람만** 남긴다. bourbon-api의 agent DM 게이트는 "친구이거나 agent가 public"이다(§6-1). discovery 미러로는 `friends`(불변식 2의 그 집합) 또는 `agents.discoverable`이다.

이 마지막 조건은 기획 단계에서 빼 둔 동의 문제가 아니다 — 요청자가 말을 걸 수 없는 사람을 추천하면 그 추천은 틀린 것이다.

두 소스의 합집합은 전체 상한 N(설정 레지스터, 초기 50)으로 자른다. 자르는 순서는 다음과 같다. ① required need마다 최소 인원을 먼저 채우고, 이때 경험 소스의 엔티티·상위 엔티티 경로 후보를 우선한다. ② 남은 인원은 전체 점수 순으로 채운다. ③ 동점은 `(score desc, agent_id asc)`로 정한다. 같은 입력이면 늘 같은 결과다(deterministic).

**need마다 후보를 보는 축** — 서로 섞지 않고 따로 계산한다. 순위(T4)와 need 충족 판정이 이것을 쓰고, decision log에 축마다 남긴다. 응답에는 싣지 않는다(§10-1).

```text
coverage 상태   근거가 어느 경로에서 왔나. 가장 좋은 경로 하나
                  prior_only     관심 소스만 — 이 분야에 관심을 드러냈다
                  record_topic   경험 소스의 topic 경로 — 이 분야에서 무언가를 겪었다·좋아한다·해 봤다·안다
                  record_text    경험 소스의 텍스트 경로로만 — 요약문이 조건·이름과 맞지만 엔티티·topic으로는 안 잡혔다
                  record_entity  경험 소스의 엔티티·상위 엔티티 경로 — 바로 이것(또는 그 상위)에 대한 기록
kind 일치       exact | compatible | mismatch   need의 kind가 기록의 kinds에 있으면 exact. need의 kind가 null이면 exact
stance 일치     match | conflict | irrelevant   need의 stance가 null이면 irrelevant
시점            sufficient | weak | stale       recency_days 안 / 반감기 안 / 그 밖
요약문 매칭      need 안에서의 순위, 또는 없음
```

- `compatible`은 need가 `experienced`이고 기록의 엔티티가 기준 대상(아래 need 충족 판정)이고 `kinds`에 `experienced`는 없지만 `prefers`가 있는 경우다 — 그 대상을 겪었다는 말 없이 평가만 남긴 기록이다. 대상이 없거나 다른 기록의 `prefers`는 `mismatch`다. 평가는 대개 겪은 뒤에 하지만, 겪은 것이 드러나면 추출이 `experienced`도 함께 적으므로 이 경우는 좁다(열린 항목 22). 그 밖은 `mismatch`다.
- 요약문 매칭은 coverage 상태가 아니라 따로 둔 축이다. 텍스트로만 들어온 기록이 엔티티로 들어온 기록보다 저절로 위에 오지 않게 하려는 것이다 — 다른 브랜드의 "신상" 요약문도 조건과 맞을 수 있다.

**need 충족(covers) 판정** — 두 사람 조합(T5), 응답의 `covers[]`, `nobody_covers`가 쓴다.

- **2단계부터**: 경험 소스의 기록 하나가 다음을 모두 만족하면 그 need를 채운다 — coverage 상태가 `prior_only`가 아님, kind 일치가 `mismatch`가 아님, stance 일치가 `conflict`가 아님, `recency: recent`인 need면 시점이 `stale`이 아님. `precision: exact`인 need는 여기에 더해 **기록의 엔티티가 기준 대상이어야 한다** — need에서 가장 구체적인 resolve된 이름의 엔티티이거나, 그것에 병합된 id, 그 하위 엔티티다. `record_entity`는 후보를 찾고 순위를 매기는 신호이지 충족의 증명이 아니다. 21 팔리아먼트를 묻는 need에 글렌드로낙 12년을 마신 기록은 상위 엔티티 경로로 `record_entity`가 되지만 충족하지 못한다. 요약문 매칭(조건 일치)도 순위에만 쓴다 — "신상"은 다른 병의 요약문에도 맞는다. 가장 구체적인 이름이 resolve되지 않았으면 exact 충족은 없다(후보와 순위는 그대로, 열린 항목 31). **`prior_only`는 need를 채우지 못한다** — 후보와 폴백은 될 수 있지만 "답할 경험이 있는 사람"이라는 보장이 아니다.
- **1단계, 그리고 경험 소스가 답하지 않을 때**: `prior_only`가 need를 채운 것으로 본다. 이때의 추천은 "관심 있는 사람" 추천이고 이유는 관심 문구다(T6). 2단계 이후 lived-knowledge가 답하지 않을 때도 이 규칙으로 폴백하고 `experience_unavailable`을 단다.

need 충족도 "답할 수 있다"가 아니라 "그런 경험을 말한 적이 있다"다.

### T4. 순위 — deterministic

feature(설정 레지스터에 올린다):

- need 충족(T3의 판정). 모든 required need를 채운 후보가 먼저다
- coverage 상태별 가중치: `record_entity` > `record_topic`·`record_text` > `prior_only`. 요약문 매칭은 따로 더하는 feature라, 텍스트로만 들어온 후보가 엔티티로 들어온 후보를 넘으려면 요약문 매칭이 충분히 좋아야 한다
- 종류 일치(`exact` > `compatible` > `mismatch`)와 stance 일치(`conflict`는 크게 깎는다)
- 엔티티 매칭의 종류: 바로 그 엔티티 1, 상위 엔티티 0.5. 가중치는 `precision`이 정한다(`exact`면 크다)
- 최근성: `recency: recent`인 need는 `observed_at`의 반감기를 짧게(오래된 기록을 빨리 낮춤), 아니면 길게
- `specificity`, 같은 need에 대한 경험의 폭 — 기록 수가 아니라 서로 다른 엔티티 수·서로 다른 날짜 수의 log, 상한 있음(§7-5)
- 요약문 매칭의 **need 안에서의 순위**(점수 자체는 need끼리 비교하지 않는다)
- 관심 소스: `topic_score`, `topic_maturity`, tier. `knowledge` facet·`confidence`는 안정적인 값이 정해지면 더한다(§15 요청 7)
- 두 소스가 같은 사람을 가리키는가, `agent_maturity`

**곱셈식을 쓰지 않는다.** 곱하면 관심 소스만 있는 후보는 0이 되고, lived-knowledge가 답하지 않으면 전원이 0이 된다. coverage 상태별 가중 합이고, 측정되지 않은 feature는 없는 것으로 둔다(discovery의 `Features.present`가 이미 그 구분을 한다). 구현은 타입 ①의 `Ranker.features/score`와 같은 구조다.

한 사람이 모든 required need를 채우면 한 명 추천이 두 명 조합보다 우선한다.

### T4-a. LLM judge와 재시도 — `condition`이 있는 need만

가중 합은 구조 필드(종류·stance·엔티티·시점)는 잘 구분하지만, `condition`이 맞는지는 요약문 매칭 하나에 기댄다. 요약문 매칭은 맞는 기록을 놓치기도 하고(다른 단어로 쓴 경우), 맞지 않는 기록을 올리기도 한다(흔한 단어가 겹친 경우, 모드 B에서 특히). 그래서 `condition`이 있는 need에는 가중 합 뒤에 LLM judge를 둔다. `condition`이 없는 need는 구조 필드로 충분히 걸러지므로 judge를 돌지 않는다. 요청 경로에서 후보를 고르는 데 LLM을 쓰는 곳은 이 단계뿐이다.

- **입력**: need(종류, stance, `condition`, 엔티티 label)와 가중 합 상위 `judge.top_m`명(초기 15)의 가장 잘 맞은 기록 1~3개의 `summary_en`. 사람의 id·이름은 넣지 않고 순번만 쓴다.
- **출력**: 후보마다 `fits`(`yes` | `no` | `unclear`). 모드 B에서는 "맞는 후보가 부족하다"는 판정과 새 표현 2~4개를 함께 낸다 — 첫 시도에서 찾은 요약문을 보고 만들므로, 요약문이 실제로 쓰는 단어로 다시 찾을 수 있다.
- **적용 방식**: `no`를 받은 후보를 빼는 필터로 할지, `fits`를 feature로 더해 순서만 바꿀지는 측정으로 정한다(§13-3의 잘못 뺀 비율). 어느 쪽이든 need 충족 판정(T3)은 바꾸지 않는다 — judge는 "이 요약문이 조건에 맞는가"만 본다.
- **재시도(모드 B만)**: judge가 부족하다고 판정하면 discovery가 새 표현을 `condition_variants`로 넣어 그 need만 lived-knowledge 조회를 다시 부르고, 새로 들어온 후보를 가중 합과 judge에 다시 넣는다. 계약은 그대로다 — 바뀌는 것은 표현뿐이다. 멈추는 조건은 셋이다: 재시도 `judge.max_retries`번(초기 1), 남은 시간 예산이 한 번의 시도보다 적음, 지난 시도에서 새 후보가 없음. 근거를 가진 사람이 아예 없는 질문에서도 judge는 "부족하다"고 판정하므로, 이 조건들이 없으면 초기에 가장 흔할 이런 질문에서 지연이 가장 길어진다(§13-2 항목 6·7).
- **실패**: judge가 실패하거나 시간을 넘기면 가중 합 순위를 그대로 쓰고 `degraded`에 `judge_unavailable`.

| | 가중 합만 | + judge (모드 A) | + judge와 재시도 (모드 B) |
|---|---|---|---|
| 조건이 있는 질문의 정확도 | 약하다 | 좋아질 가능성이 크다(추론) | 같음. 첫 시도에서 놓친 사람을 재시도로 일부 되찾는다 |
| 지연 시간 | 요청 p50 약 2~2.5초(추정) | +1~2초 | 시도마다 +1.5~2.5초(추정). bourbon-agent의 10초 예산 안에서 재시도는 1~2번이 한계다 |
| 요청당 LLM 호출 | 1~2회 | +1회 | +1 + 재시도 수 |
| 재현성·설명 | deterministic, decision log로 설명된다 | 같은 입력에도 결과가 흔들릴 수 있다. decision log에 judge 전후 순위를 남긴다 | 같음. 시도마다의 판정도 남긴다 |
| 데이터 경계 | 후보의 요약문이 LLM에 가지 않는다 | 다른 사람들의 경험 요약이 요청 경로의 LLM으로 간다(§12) | 같음 |

**2단계에서 두 모드와 함께 만들어 비교한다**(§7-6, §13-3). judge는 두 모드에서 같은 프롬프트와 출력 형식을 쓴다 — 결과의 차이가 찾는 방식에서만 나오게. T4 뒤에 붙는 처리라 앞의 구조는 바뀌지 않는다. 숫자와 기준은 열린 항목 19다.

### T5. 두 사람 조합 — deterministic

한 명으로 부족할 때만. 최대 2명, 모든 required need가 충족(T3)되고, 각자 상대가 못 채우는 need를 하나 이상 채운다. need 최대 3, 후보가 상한 N(초기 50)명이어도 조합은 1,225개다. LLM을 쓰지 않는다.

### T6. 응답 조립 — 요약문 기반 이유와 추천 근거

- **추천 이유는 요약문으로 만든다**(오너, 2026-09-26: 요약문을 저장한다). 템플릿 `"{need 이름} 관련 경험({observed_at의 연월}): {요약문}"`에 가장 잘 맞은 기록의 요약문을 그대로 넣는다 — "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다". 관심 소스만 있는 사람은 관심 문구("{need 이름}에 관심이 있는 agent입니다.")를 쓴다.
- LLM으로 이유 문장을 새로 쓰지 않는다. 요약문은 추출 때 규칙(§7-2)으로 이미 다듬어졌다.
- 기록 하나의 요약문만 쓴다. 여러 기록을 이어 붙여 그 사람의 프로필처럼 보이게 하지 않는다.
- 사람마다 근거가 된 기록 1~3개의 id를 추천 근거로 저장한다. 응답에는 싣지 않는다 — 요청자에게도 bourbon-agent에게도 나가지 않고, 대화가 시작될 때 조회된다(§10-3).
- 경험 소스의 결과가 불완전하면(`experience_incomplete`) 1위는 "전체 후보 중 1위"가 아니라 "받은 후보 중 1위"다.

---

## 10. API 초안

### 10-1. discovery — `POST /api/internal/svc/agent-discovery/recommend/knowledge`

요청:

```json
{
  "user_id": "uuid",
  "question": "글렌드로낙 21 팔리아먼트(글렌드로낙 신상) 마셔 본 사람이랑 이야기해 보고 싶어",
  "context": "선택. 현재 대화 맥락",
  "allow_group": true,
  "max_agents": 2,
  "room_id": "uuid",
  "participant_user_ids": ["uuid"],
  "lang": "ko"
}
```

- `user_id`는 요청자, 곧 recommend tool을 부른 agent의 owner다(§2). 새 계약의 타입 ① 요청과 같은 이름이다(`agent_discovery_contract.md` §2). `requester_user_id`는 동결된 옛 `/recommend` route의 이름이라 따르지 않는다.
- `question`은 지칭이 구체적인 이름으로 채워진 질문이다(§9 T0).
- `allow_group`은 두 사람 조합(T5)을 허용할지, `max_agents`는 응답의 최대 인원이다. `lang`은 타입 ① 요청과 같다.
- `participant_user_ids`: 요청 방의 **사람 참가자 전원**(요청자가 그 방에 있으면 요청자 포함). bourbon-agent는 방의 참가자를 이미 알고 있으므로 요청에 싣는다. 보는 사람은 이 목록이다 — owner의 개인 방이면 `[owner]`, 다른 사용자가 owner의 agent와 1:1로 대화하는 방이면 `[그 사용자]`, 그룹 방이면 사람 전원. 빈 목록은 받지 않는다("개인 방"과 "누락"이 구별되지 않으므로). 없거나 비어 있으면 discovery가 `room_id`로 bourbon-api에서 읽는다(§12).
- `question`과 `context`는 T1의 LLM에만 쓴다. lived-knowledge로 가는 것은 T1이 만든 `entity_mentions`(`entity_type` 포함)·`condition`·`kind`·`stance`와, discovery가 만든 topic id 목록·`recency_days`뿐이다(그 밖에는 id와 한도만 간다 — 요청자, `friend_owner_ids`, `requester_friend_ids`, `per_path_limit`). 로그에는 `question_digest`·`question_chars`·`context_chars`만 남는다.

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
     "reason": "글렌드로낙 관련 경험(2026년 9월): 글렌드로낙 21 팔리아먼트 신상을 마셔 봤고, 셰리가 너무 강해 별로였다"}
  ],
  "empty": false,
  "degraded": []
}
```

- `mode`: `single | group | none`. `none`일 때 `empty_reason`: `answerable_without_people`(T1), `nobody_covers`(required need를 아무도 못 채움).
- `needs[].label`은 엔티티가 resolve됐으면 레지스트리의 공개 이름, 아니면 topic의 카탈로그 이름. 엔티티가 여럿일 때 어느 이름을 쓸지는 열린 항목 29다(이 문서의 예제는 첫 이름 "글렌드로낙").
- **`agents[]`는 새 wire 모델 `KnowledgeRecommendedAgent`다.** 타입 ①②③의 `RecommendedAgent`는 `matched_topics`·`signals`가 필수다. 공통 필드(`agent_id`·`owner_user_id`·`position`)만 공유한다.
- `empty`는 `agents`가 비었을 때만 true이고, 그때 `mode`는 `none`이다. 타입 ① envelope과 모양을 맞추려고 둔다.
- `covers[]`는 need id 목록이고 coverage 상태는 싣지 않는다. `confidence`도 싣지 않는다(calibration 전).
- 추천 근거는 응답에 싣지 않는다. discovery가 저장하고, 대화가 시작될 때 §10-3의 route로 조회된다.
- `recommendation_id`는 대화 시작까지 전달되어야 한다. 어떤 카드·UI로 전달할지는 client 연동 때 정한다(§10-3, §15 요청 14).
- `degraded[]`: `expansion_partial`, `need_fields_defaulted`, `need_dropped`, `reference_unresolved`(채워지지 않은 지칭, §9 T0), `audience_unknown`(보는 사람을 읽지 못함, §12), `topic_unavailable`, `entity_resolution_unavailable`, `experience_unavailable`, `experience_incomplete`.

### 10-2. lived-knowledge — discovery가 부르는 조회

```http
POST /api/internal/svc/lived-knowledge/candidates
```

```json
{
  "needs": [
    {"need_id": "n0",
     "topic_ids": ["…"],
     "entity_mentions": [{"text": "GlenDronach", "as_written": "글렌드로낙", "entity_type": "brand"},
                         {"text": "GlenDronach 21 Parliament", "as_written": "글렌드로낙 21 팔리아먼트", "entity_type": "product"}],
     "kind": "experienced", "stance": null, "recency_days": 90, "condition": "new release",
     "condition_variants": ["newly launched", "latest bottling"]}
  ],
  "requester": "<requester>",
  "friend_owner_ids": ["…"],
  "requester_friend_ids": ["…"],
  "per_path_limit": 25,
  "text_mode": "embedding"
}
```

```json
{
  "needs": [
    {"need_id": "n0",
     "entities": [{"entity_id": "wd:Q…", "label": {"ko": "글렌드로낙", "en": "GlenDronach"}, "state": "resolved"},
                  {"entity_id": "rg:7f3a…", "label": {"ko": "글렌드로낙 21 팔리아먼트", "en": "GlenDronach 21 Parliament"}, "state": "resolved"}],
     "complete": true,
     "text_fallback": false,
     "has_more": {"entity": false, "parent": false, "topic": true, "text": false}}
  ],
  "people": [
    {"person_id": "…", "needs": [
      {"need_id": "n0",
       "paths": {"entity": 2, "parent": 2, "topic": 2, "text": 1},
       "distinct_entities": 1, "distinct_days": 1,
       "records": [
         {"record_id": "…", "entity_id": "rg:7f3a…", "kinds": ["experienced", "prefers"], "stance": "negative", "specificity": 3,
          "observed_at": "2026-09-21T12:04:00Z", "match_rank": 1,
          "summary": "…", "audience": "public"}
       ]}
    ]}
  ]
}
```

- `entities[].state`(mention마다): `resolved` | `ambiguous` | `not_found` | `unavailable`(resolve 장애, 레지스트리에서만 찾음). `ambiguous`·`not_found`인 이름으로는 엔티티·상위 엔티티 경로를 돌지 않고 텍스트 경로에만 쓴다(§3-3 규칙 3). 엔티티 이름이 하나도 없는 need는 `entities`가 비고 topic·텍스트 경로만 돈다.
- `friend_owner_ids`: 보는 사람 모두와 친구인 owner id 목록. `friends` 기록을 쿼리 안에서 필터링하는 데 쓴다. `requester_friend_ids`: 요청자의 친구 id 목록. 도달 가능성을 쿼리 안에서 필터링하는 데 쓴다. 둘 다 discovery가 `friends` 미러로 만들고, lived-knowledge는 저장하지 않는다(§9 T3).
- `audience`: 이 기록을 볼 수 있는 범위, `public | friends`. lived-knowledge가 topic visibility 미러로 정한다. private·hidden인 기록은 응답에 넣지 않는다. discovery는 `friends` 기록을 `friends` 미러로 한 번 더 확인한다(§12).
- 요청자 본인은 뺀다. 탈퇴한 사람은 기록이 없다(§7-5).
- `condition`·`condition_variants`는 lived-knowledge의 로그에 원문으로 남기지 않는다 — digest와 길이만.
- `text_mode`: 텍스트 경로와 요약문 매칭의 방식, `embedding` | `paraphrase`(§7-6). discovery의 설정 레지스터 값을 싣는다. `condition_variants`는 `paraphrase`일 때만 쓴다. judge의 재시도(§9 T4-a)는 같은 route를 그 need만, 새 `condition_variants`로 다시 부른다.
- `text_fallback`: `embedding`인데 `condition`의 임베딩에 실패해 그 need의 텍스트 경로를 `tsvector`(`condition` 하나)로 돌았으면 true. 경로가 빠진 것은 아니므로 `complete`는 바꾸지 않는다.
- 근거 조회용 route를 하나 더 둔다 — `POST /api/internal/svc/lived-knowledge/records/lookup`(`record_id` 목록 → 기록. 없거나 지워진 것, 조회 시점의 visibility가 private·hidden인 것은 빼고, 나머지에 `audience`를 붙여 돌려준다, §10-3).
- 이 두 route가 discovery와 lived-knowledge 사이의 **계약 전부**다. lived-knowledge가 memory-api로 옮겨 가도 이 요청·응답 형식은 그대로 둔다.

### 10-3. 추천 근거 — 추천의 근거를 대화의 출발점으로

추천과 대화 시작 사이에는 시간이 있다. 사용자는 카드를 나중에 누를 수 있고, 대화는 요청자와 추천된 사람 사이의 방에서 시작된다. 그 시점에 근거가 어디서 오는지가 이 절의 내용이다.

- **서버에 저장한다.** discovery가 추천마다 `(recommendation_id, requester_user_id, owner_user_id, source_room_id, record_ids, covered_needs, expires_at)`을 저장한다.
  - `covered_needs`: 그 owner가 충족한 need의 공개 이름과 종류(예: "글렌드로낙 / experienced"). `needs[].label`은 레지스트리나 카탈로그의 공개 이름이라 사용자의 글이 아니다.
  - `source_room_id`: 추천이 나온 방. 조회 조건으로는 쓰지 않고(대화는 추천된 사람과의 다른 방에서 시작된다), 감사와 서비스화 때 붙일 방 범위 규칙을 위해 남긴다.
  - **저장하지 않는 것**: 질문 원문과 `condition`(원문은 요청자의 글이고, `condition`도 불변식 7의 범위에 둔 파생 텍스트다), 요약문. 묶음에는 id와 공개 이름만 있다.
  - 위치는 discovery의 DynamoDB 테이블(R44)의 `REC#{recommendation_id}` key space이고, 보존은 TTL이다.
  - 요청자와 client가 받는 것은 `recommendation_id`뿐이고, 기록 id는 받지 않는다.
- **조회는 대화가 시작될 때 한다.** bourbon-agent가 추천된 agent의 턴을 준비할 때 discovery의 근거 조회 route(`POST /api/internal/svc/agent-discovery/recommend/knowledge/evidence`)에 `recommendation_id`·`requester_user_id`·`owner_user_id`와 그 방의 `participant_user_ids`를 넘긴다. **`recommendation_id`는 필수다.** discovery는 저장된 묶음과 세 값이 모두 맞고 만료 전일 때만 lived-knowledge에서 그 기록을 **다시 읽어** 돌려준다.
- **`recommendation_id`가 없으면 근거 없이 일반 대화로 시작한다.** "두 사람 사이의 가장 최근 추천"으로 대신하지 않는다. 같은 사람이 같은 날 글렌드로낙 경험과 도쿄 여행 경험으로 따로 추천될 수 있고, 그러면 글렌드로낙 카드를 눌렀는데 도쿄 여행 근거가 들어간다. attribution(계약 §2-5)은 측정용이라 가장 최근 것으로 찾아도 되지만, 근거는 agent의 답에 직접 들어간다.
- **카드를 누른 사람이 요청자와 다르면 근거를 주지 않는다.** 그룹 방에서는 카드를 다른 참가자가 누를 수 있다. 저장된 요청자와 맞지 않으므로 근거 없이 일반 대화로 시작한다. 그 사람이 추천된 agent와 DM을 열 수 있는지는 bourbon-api의 DM 게이트가 정한다. 막히는 쪽이 안전하다고 보고 이대로 둔다.
- 추천된 agent는 **`covered_needs`와 그 경험 기록(종류, 엔티티, 시각, 요약문)을 받고, 거기서 답을 시작한다.** "무엇에 대한 어떤 종류의 경험을 묻는 추천인가"는 `covered_needs`로 알고, 구체적인 질문은 대화에서 요청자가 말한다. 새 방의 첫 메시지를 누가 어떻게 보낼지(요청자가 다시 묻는지, 자동으로 보내는지)는 bourbon-agent와 client의 UX 결정이다(§15 요청 10, 열린 항목 12).
- **다시 읽으므로 과거의 권한이 고정되지 않는다.** 저장하는 것은 id뿐이고, 기록은 조회할 때마다 lived-knowledge에서 읽는다. 그 사이 탈퇴한 사람의 기록은 이미 지워져 없다.
- **공개 범위도 조회할 때 다시 판정한다.** 추천 뒤 owner가 topic을 private으로 바꿨을 수 있다. `records/lookup`이 조회 시점의 visibility로 private·hidden 기록을 빼고(§10-2), discovery가 `friends` 기록을 조회 시점의 친구 관계로 다시 확인한다. 보는 사람은 대화가 시작된 방의 사람 참가자(`participant_user_ids`)다 — 요청자와 추천된 agent의 방이라 보통 요청자 한 명이다. 추천 시점과 근거 사용 시점에 같은 규칙을 쓴다(§12). 서비스화 때 동의 철회를 확인하는 곳도 여기다.
- **묶음 자체는 탈퇴 때 지우지 않고 TTL에 맡긴다.** 키가 `REC#{recommendation_id}`라 사용자로 역조회할 수 없다. discovery의 탈퇴 처리도 TTL이 있는 DynamoDB 항목은 TTL에 맡기고, TTL이 없는 CF pool만 지운다(`worker/deactivation.py:9-12`). 대신 조회할 때 요청자와 소유자를 `departed_users`로 확인해 탈퇴자면 돌려주지 않는다(fail-closed). 묶음에는 id만 있고 글은 없다.
- **`recommendation_id`가 대화 시작까지 전달되어야 한다.** `recommendation_id`가 필수이므로, 추천을 보여 준 화면에서 대화를 시작하는 쪽이 그 값을 알아야 한다. 지금 `agent_profiles_v1`은 사람의 id(`owner_user_id`)만 싣는다(bourbon-api `AgentProfileItem`). 같은 카드 블록에 실을지, 다른 방식으로 보여 줄지는 UX·UI에 따라 달라지므로 실제 client 연동 때 정한다(오너, 2026-09-28, §15 요청 14). 추천 하나가 한 묶음이고, 두 사람 조합도 추천 하나라는 점만 정해 둔다.
- **discovery가 주는 것은 추천 근거(`covered_needs`와 경험 기록)까지다.** 추천된 agent가 원 메시지나 그 앞뒤 대화를 더 읽을지, 어떤 경로와 scope로 읽을지는 bourbon-agent·memory-api가 기획과 함께 정한다(§15 요청 5). 참고로 전할 것: 원 메시지는 대개 요청자가 없던 방에서 나왔으므로, 그 방의 scope로 원 메시지와 앞뒤를 읽어 요청자와의 방에서 쓰면 다른 방의 대화가 유출될 수 있다. 기록에는 원 메시지 id(`message_id`)가 있어, 그쪽이 필요하다고 정하면 기록 조회 응답에 실을 수 있다.
- **요약문은 요청자에게 보인다.** 추천 이유에 요약문이 그대로 들어가므로(§9 T6), 추천 근거를 숨겨도 요청자는 요약 내용을 본다. 요약문에 다른 참가자의 말은 없지만, 요약문 자체가 그 사람의 개인 정보다(§7-2). 기획 단계에서 이 노출의 동의를 빼 두었을 뿐이다(§12).
- **근거를 조회할 수 있는 것은 기록 소유자의 agent뿐이어야 한다.** 그런데 지금 내부 서비스 사이에는 호출자 인증이 없고, bourbon-agent 한 프로세스가 모든 agent를 대신해 말한다 — "호출한 agent의 소유자"는 호출자가 주장하는 값일 뿐이다. 저장된 묶음과 요청자·소유자를 맞춰 보는 것은 피해 범위를 줄일 뿐이고, bourbon-agent를 믿는다는 전제는 그대로다. 기획 단계에서는 다른 내부 route와 같은 신뢰 범위 안에 두고, 서비스화 전에 내부 호출 인증이 먼저 있어야 한다(§12).
- 기대하는 효과(추론, §13-4로 잰다): 추천된 agent가 검색어를 잘못 써서 근거를 못 찾는 실패가 줄고, 추천의 근거와 대화의 출발점이 같은 기록이라 "둘이 다른 데이터를 봐서 생긴 오차"가 줄어든다.

---

## 11. 실패와 degradation

discovery:

| 실패 | 동작 |
|---|---|
| T1 LLM 실패 | 타입 ①과 같이 질문 그대로 폴백 + `expansion_partial`. `people_needed=true`, `entity_mentions=[]` — 후보가 넓어지는 쪽 |
| need 필드 스키마 위반 | 넓어지는 쪽으로 폴백 + `need_fields_defaulted` |
| `people_needed=false` | `mode: none`, `empty_reason: answerable_without_people`. 판단이 틀리면 사람이 필요한 질문에 추천이 안 나간다 — 호출률과 함께 잰다 |
| topic 못 찾음, 엔티티 이름 있음 | 경험 소스로만 |
| topic·엔티티 이름 둘 다 없음 | `condition`이 있으면 텍스트 경로로, 없고 required면 422 `grounding_failed` |
| topic 모호, 엔티티 이름 있음 | topic을 쓰지 않고 엔티티·텍스트 경로로 |
| topic 모호, 엔티티 이름 없음 | required면 422 `grounding_ambiguous`, optional이면 빼고 `need_dropped` |
| 보는 사람을 알 수 없음(`participant_user_ids`가 없고 bourbon-api에서도 읽지 못함) | `friends` 기록과 그 요약문을 빼고 `public` 기록으로 계속 + `audience_unknown`(§12) |
| 지칭이 채워지지 않은 질문 | 그 지칭은 `condition`으로만 반영하고 계속 + `reference_unresolved`(§9 T0) |
| topic-api 검색 불가 | 엔티티·텍스트 경로로 계속 + `topic_unavailable`. 엔티티 이름도 `condition`도 없는 required need가 있거나 lived-knowledge도 답하지 않으면 503(§9 T2) |
| lived-knowledge timeout·5xx | 관심 소스만으로 응답 + `experience_unavailable`. 전원 `prior_only`, need 충족은 1단계 규칙(§9 T3), 이유는 관심 문구, 추천 근거 없음. timeout은 설정 레지스터 값이고, 새 route 전체 deadline(bourbon-agent의 10초 아래) 안에 든다 |
| lived-knowledge 장애 중, 관심 소스로 볼 것이 없는 required need(topic을 못 찾은 need)가 있음 | 503 — 못 본 것이지 없는 것이 아니다(불변식 8) |
| resolve 장애(lived-knowledge 안) | 레지스트리에서만 찾고 계속 + `entity_resolution_unavailable` |
| judge 실패·timeout(§9 T4-a) | 가중 합 순위를 그대로 + `judge_unavailable` |
| 텍스트 경로가 `tsvector`로 폴백(`text_fallback`, §10-2) | 받은 것으로 계속 + `text_fallback` |
| lived-knowledge 일부 need가 불완전(`complete=false`, 또는 `has_more`인 경로가 사후 필터 뒤 K명에 못 미침, §9 T3. `has_more`가 아닌 경로가 K명보다 적은 것은 불완전이 아니다) | 받은 것으로 순위 + `experience_incomplete`. 이때의 1위는 "받은 후보 중 1위"다. required need가 불완전하면 두 사람 조합을 내지 않는다 |
| 엔티티 `ambiguous`·`not_found` | topic·텍스트 경로로. degraded 아님(요청에 대한 판단) |
| lived-knowledge가 `people`에 요청자를 돌려줌 | 그 항목은 버리고 로그. 계약 위반이라 알람 |
| 경험 소스의 사람이 `agents`에 없거나 `departed_users`에 있음 | 뺀다(§9 T3). 탈퇴 이벤트 유실에 대한 두 번째 방어 |
| required need를 아무도 못 채움 | `mode: none`, `empty_reason: nobody_covers` |
| 대화 시작 때 추천 근거가 없음(`recommendation_id` 없음, 만료, 요청자·소유자 불일치, 탈퇴자, 기록이 지워짐, 조회 시점의 공개 범위가 허락하지 않음) | 추천된 agent가 평소처럼 대화 검색으로 |

lived-knowledge:

| 실패 | 동작 |
|---|---|
| 같은 이벤트가 다시 옴 | `pending_since`를 채우고 debounce를 미는 것뿐이라 무해하다. 실행은 방 커서 다음만 읽는다(§7-5) |
| debounce 예약 실패, 실행 유실 | pending이 PostgreSQL에 남아 있어 주기 sweep이 다시 건다(§7-1) |
| agent-context 재조회 실패 | 그 창에서 멈추고 커서를 옮기지 않은 채 다시 debounce. `ingest.max_attempts`를 넘으면 그 창을 `skipped_windows`에 남기고 건너뛴다. 백필이 채운다(§7-5) |
| 추출 LLM 실패 | 같음 |
| 두 실행이 겹침(lease가 끝난 뒤) | 쓰기 트랜잭션의 커서 확인에서 늦은 쪽이 자기 결과를 버린다(§7-5) |
| resolve 실패 | 엔티티를 QID 없이 기록하고 나중에 다시 resolve |
| 기록의 임베딩 실패(모드 A) | `summary_embedding`을 null로 두고 저장한다. 주기 워커가 채운다. 그동안 그 기록은 텍스트 경로에서 빠지고, 다른 경로로는 찾힌다 |
| 병합 확인 LLM 실패 | 합치지 않고 새 `rg:` id를 만든다 — 나누는 쪽이 안전하다. 병합 워커가 나중에 모은다(§7-3) |
| 기록 쪽 지시어 해소 실패 | 상위 엔티티로 남기고 다음 주기에 다시 시도한다. 시도 횟수 상한을 넘으면 그만둔다(§7-3) |
| 탈퇴한 사람에 대한 쓰기(늦게 온 `message_created`, 백필, 재추출) | 트랜잭션 첫 statement의 확인에서 거절(§7-5) |
| `user_deactivated` 유실 | 기록이 남는다. lived-knowledge 쪽 큐에서만 유실되면 discovery의 재필터링이 막는다. 발행 자체가 실패하면 discovery와 함께 모른다(§7-5) |

---

## 12. 기획 단계에서 빼 둔 것과 남겨 둔 필드

오너(2026-09-26): 새 타입의 기획이므로 공개 범위는 빼 두고 해 본 뒤, 실 서비스화할 때 고려한다.

**빼 둔 것** — 설계와 실험에서 조건을 걸지 않는다.

- 방의 공개 범위(DM·비공개 방에서 한 말을 기록할 것인가)
- 추천 대상이 되는 것에 대한 동의(`consultable` 같은 opt-in)
- 요약문이 요청자에게 보이는 것에 대한 동의. 요약문도 개인 정보다(§7-2)
- judge(§9 T4-a)가 후보들의 요약문을 요청 경로의 LLM으로 보내는 것, 모드 A(§7-6)에서 요약문이 임베딩 모델로 가는 것

**공개 범위 규칙 — topic visibility를 따른다**(오너, 2026-09-28). 이 서비스는 한 방에서 쌓인 경험을 다른 사람과 나누는 것이 목적이다. 그래서 "다른 방에서 한 말이 보인다"는 것 자체는 문제가 아니다. 막아야 하는 것은 **owner가 보이지 않게 정한 것이 보이는 것**이고, owner가 그것을 정하는 수단은 topic visibility다.

- **규칙**: 경험 기록 하나는 그 기록의 topic에 대해 owner가 정한 visibility가 허락하는 보는 사람에게만 보인다. 후보 선정, 추천 이유의 요약문, 대화 시작 때의 추천 근거 세 곳에 같은 규칙을 건다. 추천 시점과 근거 사용 시점에 따로 판정한다(§10-3).
- **판정은 두 서비스가 나눠 한다.** lived-knowledge가 자기 `topic_visibility` 미러(§7-7)로 기록마다 visibility를 보고, private·hidden이면 응답에 넣지 않고, 나머지에 `audience: public | friends`를 붙인다(§10-2). discovery는 `friends`인 기록을 보는 사람이 모두 owner의 친구일 때만 쓴다. discovery는 누가 무엇을 private으로 두었는지 알지 못한다.
- **보는 사람은 요청에 실려 온다.** 요청 방의 사람 참가자 전원(`participant_user_ids`, §10-1)이다. bourbon-agent는 방의 참가자를 이미 알고 있다(agent-context의 `room_members`, `api_internal_client/agent_context.py:14-29`). 다른 사용자가 owner의 agent와 1:1로 대화하는 방(`agent_dm`이지만 보는 사람은 그 사용자)도 이 목록으로 맞게 판정된다. 빈 목록은 받지 않는다.
- **목록이 없을 때만 discovery가 읽는다.** 요청의 `room_id`로 bourbon-api `GET /api/internal/rooms/{room_id}/agent-context`를 읽어 `room_members`에서 사람만 고른다. T1과 병렬로 부르고, 응답의 메시지 본문은 쓰지 않으며 로그에도 남기지 않는다. 그것도 읽지 못하면 `friends` 기록을 뺀다(fail-closed, §11).
- **hidden은 어느 경로에서도 쓰지 않는다**(오너, 2026-09-28). hidden은 사용자가 삭제 대신 고르는 상태다(topic-api `docs/dynamodb-key-design.md:25`). 요청자 본인의 프로필에서도 hidden을 읽지 않는 R22와 같다.
- **topic 하나의 visibility**(오너, 2026-09-28): owner O, 기록의 topic t에 대해 순서대로 본다.
  1. O가 t를 가졌으면 t의 tier.
  2. 아니면 카탈로그에서 t의 상위를 따라 올라가며 **O가 가진 가장 가까운 상위 topic**의 tier. 가장 가까운 상위가 이긴다 — "증류주" private, "위스키" public이면 몰트 위스키 기록은 "위스키"를 따른다.
  3. 가진 상위도 없으면 topic-api의 기본 visibility. 원래 기본은 private이고, 지금은 테스트 중이라 임시로 public이다. 기본값은 기획에 따라 정리된다(오너, 2026-09-28 — R22의 "새 topic은 default private"이 원래 기본값이다). 설정 레지스터 값 `experience.default_visibility`로 두고 topic-api의 기본값이 바뀔 때 함께 바꾼다(§15 요청 8-b).
  - 카탈로그에서 한 topic의 부모는 늘 하나이고, owner가 하위 topic을 가지면 상위 topic도 늘 가진다(오너). 그래서 가장 가까운 상위는 하나로 정해지고, 상위 topic에 붙은 기록은 언제나 1에서 그 topic 자신의 tier를 찾는다.
  - 미러에 모든 tier가 있으므로 "미러에 없다"는 "그 topic을 갖고 있지 않다"는 뜻 하나다.
  - **조회할 때 계산하고 기록에 저장하지 않는다.** 판정의 재료는 `topic_visibility` 미러와 카탈로그의 부모 관계뿐이다. owner가 visibility를 바꾸거나(`topic_visibility_changed`), 나중에 persona가 그 하위 topic을 owner에게 만들면(`topics_updated`) 미러가 바뀌고 다음 조회부터 반영된다. 기록을 다시 쓰지 않는다.
- **topic이 여럿인 기록**: 가장 제한적인 쪽을 따른다(하나라도 private이면 가린다). 잠정이고 바뀔 수 있다(오너, 열린 항목 24).
- **사용자가 visibility의 의미를 알고 설정했는가**: 지금 topic visibility는 "관심 프로필을 누구에게 보일지"의 설정이다. 그것이 경험 기록의 공개까지 정한다는 것은 서비스화 때 동의와 함께 다룬다.
- **적용 시점**: 규칙은 정했고, 필터를 거는 것은 서비스화 때다. 그 전의 dev 실험에서는 private topic의 기록도 노출된다 — discovery 불변식 1(private·hidden은 저장소에 들어오지 않는다)의 취지와 어긋나므로 production에 내보내지 않는 이유 중 하나다. 미러를 2단계에서 미리 만들어 둘지는 열린 항목 25다.

**빼 둔 결정이 이 기능의 가치를 좌우한다.** 경험 기록이 가장 많이 나올 곳은 아마 사용자가 자기 agent와 나눈 대화(`agent_dm`)일 것이다 — "나 어제 이거 마셨는데" 같은 말을 사람보다 자기 agent에게 더 편하게 할 것이라고 본다(추론). 그리고 그곳이 공개 범위 문제가 가장 큰 곳이다. 0-b단계에서 dev의 기록 수를 방 종류별로 나눠 재면(§13-2) 이 결정이 얼마나 무거운지 미리 보인다.

**빼 두지 않는 것** — 요청자가 그 사람과 대화를 시작할 수 있는가(agent DM 게이트, §9 T3)와 탈퇴. 둘 다 동의가 아니라 추천이 맞는지의 문제다.

**남겨 둔 필드** — 나중에 필터를 붙일 때 구조를 고치지 않게.

- 기록마다 `topic_ids`(§7-2). 공개 범위 규칙은 이 필드와 `topic_visibility` 미러의 조인이다.
- 기록마다 `room_id`·`room_type`(§7-2). 방 범위 조건은 이 필드에 붙이는 필터다.
- 기록마다 `person_id`(보낸 사람). 동의 조건은 이 필드와 동의 미러의 조인이다. 미러는 fail-closed로 둔다 — 값을 모르면 뺀다.
- 요약문 이유와 관심 문구를 가르는 분기(T6). 요약문이 보이는 것에 대한 동의가 없으면 관심 문구로 폴백한다.
- 관심 소스는 지금처럼 topic tier와 `discoverable`을 쿼리 안에서 건다(R17). 기존 타입과 같은 노출이라 빼 둘 이유가 없다.

**실험의 경계**(이 문서의 판단): 빼 둔 조건이 정해지기 전까지 실제 사용자 데이터를 production에 적재하거나 추천을 내보내지 않는다. 실험은 dev와 합성 대화에서 한다. 추천 근거를 조회하는 route의 호출자 인증(§10-3)도 서비스화 전에 있어야 한다.

**dev 데이터도 사용 범위가 필요하다.** 0-b단계는 dev의 실제 대화를 읽고 사람이 라벨을 단다(§13-2). dev라는 이유만으로 공개 범위 문제가 사라지지는 않는다. 0-a단계(합성 대화)는 실제 대화를 읽지 않으므로 이 승인 없이 한다. 다만 discovery dev 미러의 유저·topic을 합성 대화 생성 LLM에 넘기는 것은 discovery가 이 데이터를 쓰던 방식에 없던 새 용도라 함께 적어 둔다(§13-3). 0-b단계를 시작하기 전에 dev에 누구의 대화가 있고, 누가 어떤 범위로 사용을 승인했는지 적어 둔다(열린 항목 21).

**authorship**: 선행 문서의 가장 큰 미결 항목이던 authorship(§2)은 **보낸 사람 기준 저장으로 대부분 해결된다** — 기록은 말한 사람의 것이다. 남는 것은 전해 들은 것을 다시 말하는 경우다("친구가 그러는데 그 병 별로래"). 추출 규칙은 이것을 말한 사람의 `experienced`로 기록하지 않는다. `insider`로 볼지는 실험으로 정한다(열린 항목 6).

---

## 13. 관측과 평가

### 13-1. decision log (discovery)

원문 없이:

```text
question_digest, question_chars, context_chars
people_needed, needs_total, needs_required, need_fields_defaulted
needs_with_topic, needs_with_entity, entity_state_by_need
reference_unresolved        채워지지 않은 지칭이 온 need 수 (§9 T0) — bourbon-agent에 알려 줄 지표
candidates_by_path          interest, entity, parent, topic, text, 그리고 겹침
final_by_path               최종 상위 k명이 어느 경로로 들어왔는가
coverage_states             need × 상위 agent의 상태별 수
match_axes                  need × 상위 agent의 kind 일치·stance 일치·시점별 수
evidence_stored             추천 근거를 저장한 agent 수
experience_status           ok | unavailable | incomplete
text_mode, text_fallback    텍스트 경로의 모드(§7-6)와, tsvector로 폴백한 need 수
judge                       need별: judge를 돌았는가, fits별 수, 뺀 수, 재시도 횟수와 시도마다 새로 들어온 후보 수 (§9 T4-a)
single_sufficient, group_size, covered_required
degraded[], empty_reason
latency_ms.{expand, ground, experience, rank, judge, group, assemble, total}
```

**불변식 7의 범위를 넓힌다.** 사용자의 글 목록(topic_text, context, owner_note)에 `summary`·`summary_en`·`reason`·`condition`·`condition_variants`·`reference_query`·기록 쪽 지시어 해소의 검색 결과를 더한다 — 로그·예외·Sentry·decision log에 원문으로 싣지 않는다. decision log는 `reason`을 읽지 않는다(`discovery/journal.py`가 `matched_topics`를 읽지 않는 것과 같다, `journal.py:20-23`). 같은 규칙이 lived-knowledge와 bourbon-agent의 로그에도 적용된다.

`final_by_path`가 핵심 운영 지표다. 엔티티 질문인데 topic 경로로만 들어온 사람이 최종 상위에 자주 있으면 엔티티 resolve가 어긋나고 있다는 신호이고, 합집합(§3-3 규칙 1)이 없었다면 놓쳤을 사람이다.

### 13-2. 먼저 재는 것 (0단계)

항목마다 어디서 재는지를 괄호에 적는다 — **0-a**는 로컬의 합성 대화(§13-3), **0-b**는 dev의 실제 대화다(§14). 합성 대화에서는 정답이 심어 둔 경험이라 라벨이 필요 없지만, 생성기가 만든 말투와 밀도 위에서 잰 값이다.

1. **추출 정밀도**(0-a, 0-b에서 다시 확인) — 메시지 샘플에서 기록이 (가) 보낸 사람 본인의 것인가 (나) 사실이 아니라 경험·취향·요령·사정인가 (다) 요약문이 과장하지 않는가. 사람이 라벨을 단다.
2. **사전 필터 recall**(0-a는 생성기의 말투 위에서, 실제 값은 0-b) — 사전 필터가 버린 메시지 중 기록할 것이 있었던 비율. 추출 전체의 상한이다.
3. **엔티티 resolve 일치**(0-a — 같은 대상을 여러 표기로 심어 잰다) — 같은 대상을 가리키는 기록이 같은 id로 모이는 비율, `rg:` id가 나중에 `wd:`로 병합되는 비율, `ambiguous` 비율, alias 하나가 여러 엔티티를 가리키는 비율, 대상이 지시어로만 남은 기록의 비율과 그중 나중에 해소된 비율(§7-3). 그리고 **파편화** — 같은 실제 대상 하나에 `rg:` id가 몇 개 생겼는가(사람이 샘플을 보고 묶는다), 새로 만들기 전의 후보 확인과 병합 워커의 LLM 판정이 맞는 비율(특히 잘못 합친 비율).
4. **요약문 검색 품질**(0-a는 생성기의 말투 위에서, 실제 값은 0-b) — 한국어 메시지의 `summary_en`이 제품명·지명을 보존하는가, 영어 `condition`으로 찾히는가. 부족하면 저장소 판단을 다시 본다(§7-6).
5. **추출 물량과 비용**(창 수·창당 메시지 수·LLM 크기별 비용은 0-a, 하루 메시지 수·사람 발신 비율은 0-b) — 하루 메시지 수, 사람 발신 비율, 사전 필터 통과율, 통과 메시지당 기록 수, 실행당 창 수와 창당 메시지 수(debounce 값에 따라 달라진다), LLM을 부르지 않고 끝난 창의 비율. LLM 크기별 추출 정밀도와 호출당 비용을 함께 비교해 추출에 쓸 LLM을 정한다.
6. **데이터 밀도**(0-b만 — 합성 대화에서는 심은 만큼 나온다) — 활성 사용자당 경험 기록 수와 그 분포(기록이 한 건도 없는 사용자의 비율), 방 종류(`user_dm`·`agent_dm`·`group`)별 기록 수. 경험 기록은 사람이 채팅에서 말한 경험만 담으므로, 초기에는 대부분의 질문에 근거를 가진 사람이 없을 수 있다.
7. **질문당 근거 보유자 수**(0-b만) — 질문 샘플마다, 요청자가 대화를 시작할 수 있고 need를 충족하는(둘 다 §9 T3) 경험 소스 후보가 한 명 이상 있는 비율.

**6과 7이 2단계를 진행할지 정하는 기준이다.** 이 두 숫자가 낮으면 경험 소스를 만들어도 대부분의 추천이 `prior_only`(관심 소스)에 그쳐 체감 품질이 오르지 않는다. 그때는 기록이 쌓일 원천(예: `agent_dm`의 범위 결정, §12)을 먼저 정하거나 2단계를 미룬다. 그래서 2단계의 진행은 0-b에서 정한다. 기준값은 0-b의 결과를 보고 정한다.

0-b의 측정은 dev의 실제 대화를 읽는다. 승인된 데이터 사용 범위 안에서만 한다(§12). 결과로 남기는 것은 비율과 라벨 집계다.

### 13-3. 오프라인 — 합성 대화

**합성 대화 세트**를 만든다. 사람과 topic은 discovery dev 미러에서 가져온 유저와 그 topic이다 — 기존 10만 합성 모집단은 대화가 없고 leaf topic만 공개해 상위 엔티티·topic 계층 경로를 시험할 수 없다. 0-a단계에서 쓰고, 2단계의 끝 기준(§14)에서도 쓴다. 대화는 이렇게 만든다 — 사람마다 심어 둔 경험(엔티티, 종류, 시각, 긍정·부정)을 LLM이 여러 대화 속 발화로 만들어 넣고, 일부는 다른 참가자의 발화로, 일부는 사실 진술로 섞는다. 정답은 심어 둔 경험이다.

- 추출: 심은 경험의 recall, 다른 사람의 발화·사실 진술을 기록한 false positive
- 추천: 질문 세트(심은 경험에서 만든 질문 + 사람이 필요 없는 질문)의 relevant person recall@K / precision@K, `people_needed` 판정 정확도
- 경로 기여: 엔티티·상위 엔티티·topic·텍스트 경로를 하나씩 끄면 recall이 얼마나 떨어지는가
- **텍스트 경로의 두 모드와 judge**(2단계, §7-6, §9 T4-a) — 같은 질문 세트를 세 가지 구성으로 돌린다: baseline(`tsvector`, `condition` 하나, judge 없음), 모드 A, 모드 B. A와 B는 judge를 켠 것과 끈 것을 따로 재서, 좋아진 것이 찾는 방식 덕인지 judge 덕인지 나눈다
  - **이름도 topic도 없이 조건만 있는 질문**과 **조건이 얽힌 질문**(취향의 방향 + 대상, 예: "셰리 싫어하는 사람에게 맞는 스페이사이드")을 따로 모아 집계한다. 모드 사이의 차이는 주로 이 질문들에서 난다
  - 재는 것: relevant person recall@K / precision@K, 지연 p50·p95, 요청당 LLM 호출 수. 모드 B는 재시도마다 새로 찾은 정답 수, judge는 뺀 후보 중 정답이었던 비율(잘못 뺀 비율)
  - **고르는 기준은 비교 전에 정한다.** 예: 조건만 있는 질문에서 A의 recall이 B보다 낮지 않으면, 지연이 고정되고 호출이 적은 A를 고른다. 재시도로 새로 찾은 정답이 적으면 재시도를 넣지 않는다. 잘못 뺀 비율이 크면 judge를 필터가 아니라 순서에만 쓴다
  - 모드 A 안에서는 `input_type`(없음 / `document`·`query`)과 모델·차원 후보를 축으로 함께 잰다. 문장 한 쌍으로 잰 예비 값에서는 `input_type`을 줘도 맞는 문장과 다른 문장의 점수 차이가 거의 그대로였다(+0.085 → +0.093) — 결론이 아니라, 질문 세트로 재야 하는 이유다
  - 합성 대화도 LLM이 쓴 말투라 요약문·바꿔 말한 표현과 단어가 잘 겹쳐, 모드 B가 실제보다 좋게 나올 수 있다. 고른 모드는 dev의 실제 대화(0-b의 승인 범위 안)에서 질문 샘플로 다시 확인한다
- 지시어가 있는 질문("이번 신상")을 따로 모아, 지칭을 채운 질문과 채우지 않은 질문의 recall을 비교한다 — bourbon-agent에 채워 보내 달라고 요청하는 근거다. 기록 쪽 지시어 해소(§7-3)를 켰을 때와 껐을 때도 비교한다
- 요청자 본인이 추천 결과에 들어간 경우가 0건인지

합성 대화는 **생성기의 가정 위에서** 잰다. 실제 사람의 말투·생략·지시어는 §13-2의 dev 측정(0-b)으로 본다.

### 13-4. 핵심 품질 지표

추천 당시의 coverage 상태·need 충족과, 실행했을 때 추천된 agent가 실제로 답해 냈는지(`supported/unsupported`)를 비교해 둘의 차이(calibration error)를 잰다. 상태별·경로별로 나눠 본다. 추천 근거가 조회된 대화와 안 된 대화를 나눠 재면 그 효과가 보인다.

**호출률**(T0, bourbon-agent 쪽): 사람이 필요했던 질문 중 tool이 불린 비율, 근거 없이 직접 답한 비율, 요청자의 memory에 근거가 있어 직접 답한 비율(§9 T0), 명시적 요청 때의 호출 성공률.

---

## 14. 구현 단계

한 단계가 끝나면 그 자체로 배포해 쓸 수 있게 나눴다. 나누는 기준은 **다른 팀이나 lived-knowledge가 필요해지는 지점**이다 — 그쪽이 늦어도 앞 단계까지는 내보낼 수 있게.

```text
0-a. 합성 측정 ──▶ 0-b. dev 측정 ──▶ 2. 경험 소스로 추천 ──▶ 3. 추천 근거 ──▶ 4. 자동 트리거 준비 ──▶ 5. 실행·종합 ──▶ 서비스화
                                         ▲
1. 관심 소스로 추천 ──▶ 1-b. 두 사람 조합   (0단계와 무관하게 먼저 시작할 수 있다)
```

### 0단계 — 경험 기록이 쓸 만큼 쌓이는지 먼저 잰다

- **목표**: lived-knowledge를 제대로 만들기 전에, 이 방식이 동작하는지(0-a)와 실제 데이터로 가치가 있는지(0-b)를 차례로 확인한다.
- **만드는 것**: lived-knowledge의 최소 골격 — 방 단위 적재(debounce·방 커서), 사전 필터, 창 단위 추출, 엔티티 레지스트리(새로 만들기 전의 후보 확인 포함). 추천 route는 아직 없다.

**0-a — 로컬, 합성 대화** (오너, 2026-09-29)

- **데이터**: discovery dev 미러에서 가져온 유저와 topic으로 합성 대화를 만든다(§13-3). 실제 대화는 읽지 않는다.
- **실행 환경**: 로컬. deferq는 로컬 Redis로 돌리고, agent-context는 합성 대화를 돌려주는 fake로 바꾼다. memory-api resolve는 허락받은 대로 부른다(§15 요청 4).
- **재는 것**: §13-2의 1·3·5(창·비용), 2·4는 생성기의 말투 위에서. §13-3의 추출 지표.
- **정하는 것**: 추출에 쓸 LLM, 창·debounce 값(`ingest.*`), 레지스트리 기준(`registry.*`), 저장소(§7-6).
- **필요한 것**: 없음.

**0-b — dev 실제 대화**

- **시작 조건**: 0-a를 마친 뒤. dev 데이터 사용 범위는 0-a의 결과를 보고 정한다(§12, 열린 항목 21). lived-knowledge 워커의 Redis DB 번호는 이때 인프라에서 받는다(§7-1).
- **재는 것**: §13-2의 2·4의 실제 값, 5의 물량, 그리고 **사용자당 기록 수**(6)와 **질문마다 근거를 가진 사람이 있는 비율**(7). 1은 실제 말투에서 다시 확인한다.
- **정하는 것**: **2단계를 진행할지**. 6·7이 낮으면 2단계를 만들어도 추천 대부분이 관심 소스에 그친다. 합성 대화로는 이 둘을 잴 수 없다 — 생성기가 심은 만큼 나온다.
- **필요한 것**: dev 대화 사용 범위의 승인, Redis DB 번호. bourbon-api의 agent-context 호출·큐 바인딩과 memory-api resolve는 허락받았다(§15 요청 2·3·4).

### 1단계 — 관심 소스만으로 한 명 추천

- **목표**: 새 추천 route를 먼저 열어 둔다. lived-knowledge 없이 지금 있는 데이터로.
- **추천하는 사람**: 이 분야에 관심을 드러낸 사람(`prior_only`). "겪어 본 사람"이 아니라 "관심 있는 사람"이다. 이 단계에서는 `prior_only`가 need를 채운 것으로 본다(§9 T3). UI와 문구도 "관심 있는 agent"로 유지한다.
- **만드는 것**: `POST /recommend/knowledge` route와 응답 형식, T1 질문 분석(새 필드를 전부 뽑아 decision log에 남긴다), 사실 질문 판정(`people_needed`), 순위.
- **필요한 것**: 없음. discovery 안에서 끝난다.
- **내보내는 범위**: 관심 기반 추천이라 사용자가 명시적으로 "추천해 달라"고 할 때만 쓴다.

### 1-b단계 — 두 사람 조합

- **목표**: need가 여럿인 질문에 서로 보완하는 두 사람을 추천한다.
- **만드는 것**: 조합 탐색(최대 2명).
- **필요한 것**: 알고리즘은 1단계 위에 얹으면 된다. 사용자에게 내보내려면 bourbon-agent의 `recommend_agents`(지금 `max_results=1`, 1위 한 명만 쓴다)와 카드(§10-3)가 두 명을 다룰 수 있어야 한다(§15 요청 9). 카드·UI는 client 연동 때 정한다(§15 요청 14).
- **내보내는 범위**: 관심 소스만으로 만든 조합은 실험용이다.

### 2단계 — 경험 소스로 추천

- **목표**: "이것을 겪었다·좋아한다·해 봤다·안다고 말한 사람"을 추천한다. 이 타입의 핵심이다.
- **먼저 확정할 것**: need 충족 판정(§9 T3), 적재의 중복 처리(§7-5), 엔티티 ambiguity(§7-3)를 구현 계약으로 정한다.
- **만드는 것**: `bourbon-lived-knowledge-api` 전체 — 이벤트 소비, 추출, 중복 처리, 저장, 조회 API. discovery 쪽은 네 검색 경로를 받아 합치는 부분, 보는 사람 판정(방 참가자, §12), 요약문 기반 추천 이유. lived-knowledge 쪽에는 기록 쪽 지시어 해소 워커와 엔티티 병합 워커(§7-3). 텍스트 경로의 두 모드(§7-6)와 judge·재시도(§9 T4-a) — 비교하려고 둘 다 만들고, 고른 뒤 하나를 지운다.
- **필요한 것**: 0-b단계의 "진행" 판단, lived-knowledge 워커의 Redis DB 번호(0-b단계에서 받는다), e3llm 배치 한도(§15 요청 13), memory-api resolve(허락받았다, §15 요청 4), 모드 A를 위한 pgvector와 임베딩 호출 경로(§15 요청 15·16).
- **끝났다고 보는 기준**: 합성 대화 세트(§13-3)에서 recall·precision을 재고, 경로별 기여를 확인한다. 텍스트 경로의 모드 하나와, judge를 필터로 쓸지 순서에만 쓸지, 재시도를 넣을지를 미리 정한 기준으로 고른다(§13-3).

### 3단계 — 추천 근거 넘기기

- **목표**: 추천된 agent가 근거가 된 경험 기록에서 바로 답을 시작하게 한다.
- **시작 조건**: 근거의 전달 방식(§10-3)과 호출자의 권한 모델이 합의된 뒤에 구현한다. 근거를 조회할 때 공개 범위를 추천 때와 같은 규칙으로 다시 판정하는 것이 필수다(§10-3).
- **만드는 것**: 추천 근거 저장과 조회 route(discovery), 기록 조회 route(lived-knowledge).
- **필요한 것**: bourbon-agent의 실행 경로 변경(§15 요청 10), 카드의 `recommendation_id`(§15 요청 14).
- **끝났다고 보는 기준**: 추천 근거를 조회한 대화와 그렇지 않은 대화의 답변 성공률을 나눠 잰다(§13-4).

### 4단계 — 자동 트리거에 맞춘 준비

- **목표**: bourbon-agent가 "추천해 달라"는 요청 없이도 추천을 부르게 될 때(그쪽의 결정, §9 T0) discovery 쪽에 필요한 것을 갖춰 둔다.
- **만드는 것**: 호출률과 `reference_unresolved` 지표를 bourbon-agent와 나눌 방법.
- **전할 것**: 2단계가 먼저 끝나 있어야 한다는 것 — 관심 기반 추천을 자동으로 내보내는 것은 권하지 않는다(§15 요청 9).
- **끝났다고 보는 기준**: 호출률(§13-4)을 볼 수 있다.

### 5단계 — 실행과 종합

추천된 agent가 실제로 답하고, 여러 agent의 답을 종합하는 부분이다. bourbon-agent가 맡고 이 문서 범위 밖이다.

### 서비스화

- 기획 단계에서 빼 둔 공개 범위·동의(§12)를 정하고, 남겨 둔 필드에 필터를 붙인다.
- 추천 근거를 조회하는 route에 내부 호출 인증을 붙인다(§10-3).
- 그 뒤에 production 데이터를 적재한다.

### 질문 하나가 단계마다 어디까지 가는가

"글렌드로낙 이번 신상 마셔 본 사람이랑 이야기해 보고 싶어"

| 끝난 단계 | 추천되는 사람 |
|---|---|
| 1 | 위스키·몰트 위스키에 관심이 큰 사람 |
| 2 | bourbon-agent가 채워 보낸 그 신상(예: 글렌드로낙 21 팔리아먼트)을 마셔 봤다고 말한 사람이 맨 위. 이름이 채워지지 않았으면 글렌드로낙을 마셔 봤다고 최근에 말했고 요약문이 "신상"과 맞는 사람 |
| 3 | 위와 같고, 그 사람의 agent가 대화할 때 그 경험 기록에서 답을 시작한다 |

---

## 15. 요청하고 확인할 것

**bourbon-api**

1. **믿을 수 있는 탈퇴 확인 방법.** `user_deactivated`는 best-effort이고, 내부 사용자 조회에 없다는 것을 탈퇴 신호로 읽지 말라고 적혀 있다(§7-5). 탈퇴한 id 목록을 주는 route나, 발행을 보장하는 방식(outbox 등)이 있는지.
   - **답(2026-09-28)**: 아직 없다. `user_deactivated`를 탈퇴로 본다(§7-5).
2. lived-knowledge가 `GET /api/internal/rooms/{room_id}/agent-context`를 bourbon-agent와 같은 방식으로 불러도 되는지, 부하 한도. 그리고 요청에 참가자 목록이 없을 때 discovery가 같은 route로 방의 참가자를 읽는 것(§12) — 참가자만 필요하므로 메시지 문맥을 최소로 받을 방법이 있는지.
   - **답(2026-09-28)**: 불러도 된다. 부하 한도와 문맥을 최소로 받는 방법은 필요해지면 따로 묻는다.
   - (2026-09-29) 부르는 방식이 바뀌었다 — 메시지마다 `around`로 읽지 않고, 방마다 모아 `after=<커서>`로 한 번에 최대 100개씩 읽는다(§7-1). 호출 수는 메시지 수가 아니라 실행 수를 따른다. 부하 한도를 물을 때 이 형태로 묻는다.
3. lived-knowledge의 큐를 `bourbon.message_created`에 바인딩하는 것 — 이벤트 워커는 소비하는 repo가 소유한다는 기존 원칙대로.
   - **답(2026-09-28)**: 문제없다. 워커가 쓸 Redis DB 번호는 할당받아야 한다(§7-1).

**memory-api**

memory-api에서 이 문서를 읽는다면 먼저 전할 것(2026-10-02):

- **personal build와 그 데이터 모델을 바꿔 달라는 요청은 없다**(아래 요청 6). §6-2의 표는 personal build의 결함이 아니라, 그 사용자 자신의 agent가 기억해 답하기 위한 데이터라 이 추천과 목적이 다르다는 것을 적은 것이다. 창 나누기와 엔티티 중복 확인은 오히려 그 방식을 참고했다.
- **lived-knowledge가 나중에 memory-api로 옮겨 갈 수 있다는 것**(§4-3, 열린 항목 16)은 오너의 방향이다 — 우선 lived-knowledge로 두고, 필요하면 넘긴다. 지금 넘기는 계획이나 일정은 없다. discovery와의 계약을 조회 route 둘로 좁게 둔 것(§10-2)이 그때를 위한 준비다.
- **요청 5(추천된 agent가 원 메시지를 다시 읽을지)는 열어 둔 질문이다.** 정해진 일을 맡기는 것이 아니라, bourbon-agent와 함께 정할 때 참고할 사실을 적어 둔 것이다.
- 읽을 곳: §5-2·§6-2(personal build를 근거로 쓰지 않는 이유와 참고한 방식), §7-3(`/knowledge/resolve`의 사용 방식 — 이름과 분야 이름만 보내고 메시지 텍스트는 보내지 않는다), 아래 요청 4~6, §4-3과 열린 항목 16(memory-api로 옮기는 것).

4. `POST /knowledge/resolve`를 추출 경로에서(메시지마다가 아니라 레지스트리에 없는 새 이름마다) 불러도 되는지, 처리량과 지연 시간.
   - **답(2026-09-28, 오너 판단)**: 불러도 된다고 본다. resolve는 레지스트리에 없는 새 이름마다만 부르므로 호출량이 작다고 가정했다(추론). 처리량과 지연 시간은 0단계에서 잰다.
5. **전달 사항**: 추천된 agent가 원 메시지나 그 앞뒤 대화를 읽을지, 읽는다면 어떤 경로(`POST /{tenant}/messages/lookup` 등)와 scope로 읽을지는 bourbon-agent·memory-api가 기획과 함께 정할 일이다(§10-3). discovery는 추천 근거까지만 주고, 필요하다면 기록의 `message_id`를 조회 응답에 실을 수 있다. (2026-09-28 개정: 처음에는 "지금 방의 scope로 부르는 것이 맞는지"를 물었으나, 경로를 정하는 것은 우리 몫이 아니다.)
6. personal build는 건드리지 않는다는 것을 알린다. 이 추천을 위해 그쪽 데이터 모델을 바꿀 요청은 없다.

**topic-api**

7. `score_detail` block의 facet 이름과 `confidence`를 소비자 계약으로 삼아도 되는지(관심 소스).
   - **답(2026-09-28)**: 지금은 계약으로 삼지 않는다. 관심 소스는 `topic_score`·`topic_maturity`로 순위를 매기고, 안정적인 값이 정해지면 그때 쓴다(§4-1).
8. 제품·브랜드 노드는 요청하지 않는다. 엔티티는 lived-knowledge의 레지스트리가 맡는다.
   - **확정(2026-09-28)**: 요청하지 않는다.
8-a. lived-knowledge가 내부 route로 사용자 topic을 **모든 tier**(`private`·`hidden` 포함)로 읽고, `topics_updated`·`topic_visibility_changed`에 큐를 바인딩해도 되는지(§12). 읽는 것은 id와 tier뿐이다.
   - **답(2026-09-28)**: 구독해도 된다.
8-b. 사용자 topic의 기본 visibility를 소비자가 알 방법(route나 계약 값)(§12).
   - **답(2026-09-28)**: 기본 visibility는 기획에 따라 정리된다. 원래 기본은 private이고, 지금은 테스트 중이라 임시로 public이다. 따로 알려 주는 route는 두지 않고, 설정 레지스터 값 `experience.default_visibility`를 기획의 결정에 맞춰 바꾼다.

**bourbon-agent** — 9~12는 묻는 것이 아니라 **discovery가 먼저 계약을 정하고 bourbon-agent가 맞추는 것**이다(오너, 2026-09-28). 언제 recommend tool을 부를지(트리거)만 그쪽의 결정이다(§9 T0).

9. **tool 계약**: `recommend_agents`가 새 route(§10-1)를 부르고, 1-b단계 이후 두 사람 조합을 다루도록 맞춘다(지금 `max_results=1`). 질문 분석(need 필드)을 tool 인자로 옮길지(§9 T1)는 discovery가 측정한 뒤 정하고, 옮기기로 하면 그쪽이 맞춘다. 참고로 전할 것 — 관심 기반 추천을 자동으로 내보내는 것은 권하지 않는다.
10. **근거 조회**: 대화가 시작될 때 §10-3의 route로 추천 근거를 조회해 추천된 agent의 턴에 넘긴다 — 그 기록에서 답을 시작하게 하는 프롬프트·tool은 그쪽이 만든다. 새 방의 첫 메시지 UX(요청자가 다시 묻는지, 자동으로 보내는지)와, 그때 `covered_needs`를 어떻게 쓸지. 그리고 내부 호출 인증(§10-3).
11. **요청의 지칭을 채워 보낸다**(§9 T0) — "이번 신상" 같은 지칭을 대화 맥락이나 `search_web`으로 구체적인 이름으로 바꿔 `question`에 넣는 것. discovery는 요청 경로에서 웹 검색을 하지 않는다. 찾지 못했을 때 사용자에게 되물을지는 그쪽의 판단이다.
12. **호출률 지표**: 지표의 정의는 discovery가 정하고(§13-4), 그쪽 journal에 남긴다.
12-a. 질문한 사람의 id: 지금 `user_id`로는 agent의 owner를 보낸다(§2). 따로 필요해지면 discovery가 계약에 필드를 더한다.
12-b. **참가자 목록**: 요청과 근거 조회에 방의 사람 참가자 전원(`participant_user_ids`)을 싣는다(§10-1, §12).

**e3llm**

13. 추출의 배치 부하(§7-8)와 새 타입의 요청 부하. 배치에 별도 한도를 둘 수 있는지. 그리고 기록 쪽 지시어 해소(§7-3)의 웹 검색 — 배치 부하, `web_search_options`와 구조화된 출력을 한 호출에서 쓸 수 있는지, 검색 한도.
   - **답(2026-09-28)**: 나중에 다룬다.

**bourbon-api · client (카드)**

14. `agent_profiles_v1` 카드 블록(`AgentProfilesV1Block`)에 `recommendation_id`를 추가 필드로 한 번 싣는 것(§10-3). 추천 하나가 카드 하나다. 그리고 카드에서 대화를 시작할 때 그 값이 bourbon-agent까지 전달되는 경로. 추천 이유와 `covers`는 bourbon-agent의 모델이 문장으로 말하므로 카드에 싣지 않아도 된다.
   - **답(2026-09-28)**: 미룬다. 같은 카드 블록이 될지, 다른 방식으로 보여 줄지는 UX·UI에 따라 달라지므로 실제 client 연동 때 정한다. `recommendation_id`가 대화 시작까지 전달되어야 한다는 조건만 남긴다(§10-3).

**인프라 · e3llm (텍스트 경로 모드 A)**

15. discovery DB가 있는 공용 RDS에서 lived-knowledge DB에 pgvector 확장(`CREATE EXTENSION vector`)을 쓸 수 있는지, 그 버전(iterative index scan은 0.8부터, §7-6). 쓸 수 없으면 모드 A는 빠진다.
16. 임베딩 모델과 호출 경로 — e3llm으로 임베딩 API를 호출할 수 있는지, 모델과 차원, 적재(배치)와 요청 경로 각각의 한도(§7-8).
   - **확인(2026-10-07)**: e3llm에 임베딩 route가 없었다. origin/main(`19ca985`)의 route는 chat completions와 모델 목록뿐이고, Gemini 모델 목록에서 임베딩 모델을 일부러 뺀다(`e3llm/models/google.py`).
   - **진행(2026-10-07, 오너)**: e3llm-api의 로컬 브랜치 `feat/embeddings`(`00628c0`, push 전)에 OpenAI 호환 `POST /v1/embeddings`를 만들었다. chat과 같은 `provider/model` id(`google/gemini-embedding-001`, `google/text-embedding-005`, `openai/text-embedding-3-*`), `dimensions`, `encoding_format`(`float`|`base64`), 그리고 확장 필드 `input_type`(8개 값, Gemini는 task_type으로 번역하고 OpenAI는 무시한다). 토큰 한도를 넘는 텍스트는 잘라 내지 않고 400으로 거절하고, prefix만 맞고 없는 모델은 chat처럼 404다. 실제 Vertex와 OpenAI로 768차원 응답, 150개 묶음, 8개 `input_type`, 400·404를 확인했다. **남은 것**: e3llm 쪽 리뷰와 머지, 적재(배치)와 요청 경로의 한도.

---

## 16. 열린 항목

1. lived-knowledge의 repo와 배포 단위.
2. 저장소 — PostgreSQL을 권하되(§7-6), 요약문 검색 품질에 따라 검색만 OpenSearch로 옮길지. 텍스트 경로의 모드(열린 항목 19)와 함께 본다.
3. 사전 필터의 방식 — 규칙, 작은 분류기, 작은 LLM(§7-1).
4. 창의 크기(기록을 뽑는 메시지 수, 끊김 기준)와 커서 앞 문맥 수, debounce 값(`ingest.*`, §7-1).
5. `registry.ambiguity_ratio`, 새로 만들기 전 후보 찾기의 유사도·후보 수(`registry.candidate_similarity`·`registry.candidate_limit`), 병합 워커의 주기와 기준(`rg:`→`wd:`, `rg:`→`rg:`)(§7-3).
6. 전해 들은 것을 다시 말한 경우("친구가 그러는데")를 기록할 것인가, 한다면 어떤 종류로(§12).
7. `people_needed` 판단이 틀렸을 때의 비용 — 사람이 필요한 질문을 사실 질문으로 판단하면 추천이 안 나간다. 기준을 어느 쪽으로 기울일 것인가.
8. `kind`를 순위 조건으로만 둘 것인가, 필터링 조건으로 쓸 경우가 있는가. 필터링한다면 기록의 `kinds`와 겹치는가(`&&`)로 보고 GIN 인덱스를 둔다.
9. `recency_days`의 초기값, 그리고 종류별로 다르게 둘지(`prefers`는 오래 유효하고 `insider`는 빨리 낡는다).
10. 추천 이유의 요약문을 요청 언어로 번역할 것인가(요약문은 메시지 언어다).
11. 추천 근거의 보존 기간(TTL).
12. 요청자가 추천을 수락한 뒤에만 실행할지, 자동으로 실행할지.
13. 두 사람 조합을 세 사람으로 늘릴 조건.
14. required need 하나가 비었을 때 부분 답을 허용할지.
15. 실행 단계의 피드백 이벤트(추천 id ↔ `supported/unsupported`) — calibration을 재려면 먼저 있어야 한다.
16. lived-knowledge를 memory-api로 옮기는 시점과 기준(오너: 우선 lived-knowledge, 필요하면 넘긴다). 옮기지 않기로 하면 discovery와 합칠지도 함께 본다(§4-3).
17. §12에서 빼 둔 것 전부 — 실 서비스화 때.
18. 질문 분석을 discovery의 T1에 둘지, bourbon-agent의 tool 인자로 옮길지(§9 T1). 그리고 요청에 need 목록이 있으면 T1을 건너뛰는 옵션을 1단계부터 둘지.
19. 텍스트 경로의 모드(임베딩 검색 / 쿼리 확장, §7-6)와 judge·재시도(§9 T4-a) — 어느 모드를 남길지와 고르는 기준값, judge를 필터로 쓸지 순서에만 쓸지, `judge.top_m`·`judge.max_retries`·judge timeout, 임베딩 설정(모델·차원·`input_type`). 2단계의 비교로 정한다(§13-3).
20. (닫힘 — 요청자 본인의 기억은 bourbon-agent가 쓰므로 `self_support`를 두지 않는다, §9 T0.)
21. 0-b단계에서 읽을 dev 대화의 범위와 승인(§12). 0-a단계(합성 대화)의 결과를 보고 정한다(오너, 2026-09-29).
22. kind `compatible`의 범위 — `kinds`가 배열이 되어 "겪고 평가한" 기록은 `exact`가 되므로, 남는 것은 평가만 있는 기록(`kinds = [prefers]`)을 `experienced` need에 얼마나 쳐줄지다. 추출이 `kinds`를 얼마나 넉넉히 붙이는지는 0단계에서 측정한다. 경험의 폭 상한(§9 T3·T4).
23. 기록 쪽 지시어 해소의 재시도 주기와 상한, 검색 결과 후보 수(§7-3).
24. topic이 여럿인 기록의 공개 범위 — 가장 제한적인 쪽을 따르는 것은 잠정이다(§12).
25. `topic_visibility` 미러를 2단계에서 미리 만들어 둘지, 서비스화 때 만들지(§12). 쿼리 안의 도달 가능성 필터(§9 T3)가 이 미러로 public topic을 계산하므로, 서비스화 때 만들면 2단계의 도달 가능성은 discovery의 사후 필터(`friends`·`agents.discoverable`)로만 걸린다.
26. topic이 하나도 붙지 않은 기록의 공개 범위 — `/search/topics`는 lexical이라 빈 결과가 나올 수 있다(§6-3, §7-4). 기본값을 따를지 막을지.
27. 카탈로그가 바뀔 때(topic 병합·폐기) 기록의 `topic_ids`를 다시 매핑하는 경로 — 낡은 id는 미러와 맞지 않아 기본값으로 떨어진다.
28. visibility 철회 반영의 보장 수준 — 이벤트 유실에 대비한 주기 재조회나, 근거를 답변에 넣기 직전의 원본 확인. `visible_topic_rows`와 함께 정한다(§7-7).
29. need에 엔티티가 여럿일 때 `needs[].label`(과 `covered_needs`)에 어느 이름을 쓸지 — 첫 이름, 가장 구체적인 이름 등(§10-1).
30. 잘못된 병합을 되돌리는 절차 — 병합 뒤에 저장된 기록은 `merged_into`를 지워도 나뉘지 않는다. `terms`로 다시 가를지, 병합을 되돌릴 수 있는 기간을 둘지(§7-3).
31. `precision: exact` 충족의 가장자리(§9 T3) — 가장 구체적인 이름이 resolve되지 않았을 때 요약문·`terms`에서 그 이름이 확인되면 충족으로 볼지(지금은 충족 없음), "21이나 18"처럼 OR로 묻는 질문을 need 하나의 기준 대상 여럿으로 둘지(지금은 T1이 need를 나누므로 둘 다 채워야 하는 질문처럼 다뤄진다). 0단계 질문 세트에서 얼마나 자주 나오는지 보고 정한다.
32. 경험 기록의 보존과 정리 — 지금 기록이 지워지는 것은 탈퇴와 재추출의 교체뿐이고, 최근성은 순위에서 낮출 뿐 기록은 남는다(§7-5). 기록이 늘수록 무거워지는 곳은 셋이다. 질문 때 경로별 쿼리(특히 topic 경로), 모드 A의 임베딩과 `embedding_spec`을 바꿀 때의 재임베딩, ANN과 쿼리 안 필터가 겹칠 때의 recall(§7-6). 보존 기간을 둘지, 사람·엔티티별 기록 상한을 둘지, 오래된 반복 기록을 정리할지를 정한다. 그 전에 0-b단계에서 사용자당 기록 수가 늘어나는 속도를 잰다(§13-2 항목 6).
33. 답변 모드 — 사람을 추천하는 대신, 다른 사용자들의 경험 기록으로 답변을 만들고 누구의 경험이 쓰였는지 밝히는 것(오너, 2026-10-08 논의).
    - **구조상 가능하다.** 기록이 보낸 사람 한 명의 한 진술이라(§7-2) 문장마다 출처를 기록 id 하나로 붙일 수 있다. T1~T4와 lived-knowledge 조회(§10-2)는 그대로 쓰고, 바뀌는 것은 T5·T6이다.
    - **별도 타입보다 같은 파이프라인의 두 번째 출력으로 본다.** "A와 B의 경험으로는 이렇다"로 답하고, "더 물어보려면 A의 agent와"로 추천을 함께 붙인다. 요약문으로 부족한 부분과 확인을 사람이 채운다.
    - **답변은 bourbon-agent의 모델이 쓴다.** discovery는 LLM으로 문장을 새로 쓰지 않는다는 원칙(§9 T6)을 지키고, 기록 단위의 근거와 출처를 돌려준다. 기록 id를 응답에 싣지 않는다는 결정(§10-3)은 이 모드에서는 다시 정해야 한다.
    - **동의가 선행 조건이다.** 당사자가 대화에 끼지 않은 채 여러 사람의 경험이 이름과 함께 한 답변에 쓰인다. "추천 대상이 되는 것"과 "내 경험이 남의 답변에 인용되는 것"은 다른 동의일 가능성이 크고, §12처럼 빼 두고 실험할 수 없다.
    - **요약문만으로는 답이 얕다.** 원문은 저장하지 않고(§7-2), 원 메시지를 다시 읽으면 다른 방의 대화가 새어 나간다(§10-3). 추출 때 답변에 쓸 세부를 더 남길지 정해야 한다. 그것도 그 사람의 개인 정보다.
    - **확인할 사람이 빠진다.** 추천은 "말한 적이 있다"까지 보장하고 나머지는 실제 대화에서 드러나지만(§0), 답변 모드에는 그 단계가 없다. 추출 오류, 낡은 `insider` 정보, 생성 LLM의 잘못된 귀속이 겹친다. 문장마다 기록 id를 인용하게 하고, 입력에 없는 id와 기록이 뒷받침하지 않는 문장을 검사하고, 기록의 시점을 함께 보여 줘야 한다.

---

## 17. 선행 문서와 달라진 것

| 선행 문서(아카이브된 `personal-knowledge-agent-recommendation.md`) | 이 문서 | 이유 |
|---|---|---|
| 근거는 memory-api personal build의 결과 | 추천만을 위한 경험 기록, lived-knowledge(경험 소스). personal build는 건드리지 않는다 | personal build는 각 사용자 자신의 agent가 기억해 답하기 위한 그래프라 말한 사람·시각·엔티티 동일성·사실 비중이 이 목적과 맞지 않는다(§6-2, §5-2) |
| 사용자의 memory 단위, authorship은 결정 대기 정책 | 메시지 단위, 보낸 사람 기준 | "누가 겪었나"가 정의상 맞게 된다. authorship 질문이 대부분 사라진다(§12) |
| 근거는 개수와 날짜만, 텍스트 없음 | 요약문을 저장한다(오너, 2026-09-26). 원문은 저장하지 않는다 | 조건("이번 신상")을 요약문 매칭으로 반영하고 추천 이유를 구체적으로 쓴다 |
| 시각은 빌드 시각 | 메시지 시각 | "최근에"가 조건이다 |
| 찾는 기준은 topic 하나, memory 근거는 `topic_qid_map`을 거쳐 조회 | topic과 엔티티. 엔티티는 lived-knowledge의 레지스트리가 질문과 기록 양쪽을 같은 방식으로 resolve한다 | 카탈로그는 분야만 받고, 따로 하는 두 resolve는 어긋난다(§3-2) |
| `topic_qid_map`, 폴링 루프, manifest cursor, reconciliation | 없음. discovery가 lived-knowledge를 조회한다 | lived-knowledge는 우리가 이 조회를 위해 만든다 |
| 모든 질문이 대상 | `people_needed`로 사실 질문을 뺀다. 요청자 본인의 기억은 bourbon-agent가 쓴다(§9 T0, §6-4) | 사람이 필요한 질문만 추천할 가치가 있다(§1) |
| knowledge_kind 다섯(memory-api의 값), statement마다 하나 | kind 넷(`experienced`·`prefers`·`practiced`·`insider`), 기록마다 하나 이상(`kinds`) | 사람만 줄 수 있는 것의 분류다. 사실(`declarative`)과 계획(`intention`)은 추천의 근거가 아니다. 겪고 평가한 한 진술을 두 기록으로 나누지 않는다 |
| 추천 이유는 중립 문구 하나 | 요약문 기반 이유, 관심 소스만이면 관심 문구 | 요약문을 저장하기로 했다. 동의는 서비스화 때(§12) |
| 실행 시점의 근거 찾기는 agent의 대화 검색에 맡김 | 근거가 된 기록의 id를 discovery가 추천 근거로 저장하고, 대화가 시작될 때 추천된 agent에게 넘긴다 | 답을 찾지 못하는 경우를 줄이고, 추천과 대화의 출발점을 같게 한다(§10-3) |
| 동의(`consultable`)와 authorship이 production의 선행 조건 | 기획 단계에서 공개 범위·동의를 빼 두고, 나중에 필터를 붙일 필드만 남긴다 | 오너, 2026-09-26 |
| 시점에 기대는 지칭("이번 신상")을 따로 다루지 않음 | 요청에서는 bourbon-agent가 구체적인 이름으로 채워 보내고, 기록에서는 lived-knowledge가 필요할 때 웹 검색으로 해소한다 | 문장 매칭만으로는 약하고, 이름이 있어야 엔티티 경로를 쓴다. 요청 쪽은 bourbon-agent가 맥락과 검색 tool을 이미 갖고 있다(§9 T0, §7-3) |
| 오프라인 측정은 합성 모집단에 파생 데이터를 합성 | 합성 **대화** 세트, 그리고 dev 추출 정밀도 | 추출이 새로 생긴 단계이고, 대화 없이는 그것을 잴 수 없다 |
