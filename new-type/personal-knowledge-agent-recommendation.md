# Personal knowledge 기반 답변 가능 agent 추천

> 상태: **설계 초안, 결정 아님** — 2026-09-18 초안을 2026-09-21에 세 서비스의 코드를 읽고 전면 재작성했다
> 범위: `bourbon-agent` · `bourbon-agent-discovery-api` · `bourbon-memory-api-v2` · `bourbon-topic-api` 사이의 새 추천 타입(타입 ④ 후보)
> 비범위: 타입 ①·②·③의 계약 변경, 선택된 agent들의 실제 답변 실행과 종합(이 문서는 경계만 정한다)
> 이 문서의 "현재"는 각 repo의 HEAD 기준이다 — bourbon-agent `80d81bf`(09-10), memory-api-v2 `6c0ae52`(09-15), topic-api `ae09a28`(09-19), agent-discovery-api `339a99f`(09-21)

---

## 0. 요약

사용자의 personal agent가 자기 지식으로 답할 수 없는 질문을 받았을 때, **그 질문에 답할 근거를 가진 다른 사용자의 personal agent**를 추천한다. 질문이 여러 knowledge need로 나뉘고 한 사람이 전부 덮지 못하면 서로 보완하는 두 명을 group으로 추천한다.

1차 초안과 달라진 결론은 넷이다.

1. **"유저 X가 질문 Q에 답할 수 있는가"를 (X, Q) 쌍마다 판단하지 않는다.** 그렇게 하면 LLM 호출이 유저 수에 비례한다. 대신 owner별·QID별 capability 집계를 **오프라인**에 두고, 온라인에서는 질문을 QID 몇 개로 grounding한 뒤 그 집계를 조회해 **결정적으로** 랭킹한다. 유저가 몇 명이든 온라인 비용은 후보 수에만 비례한다.
2. **discovery 경로의 LLM 호출은 타입 ①이 이미 내는 그 호출 하나다.** need 분해를 기존 expansion 프롬프트의 스키마 확장으로 처리하고, answerability judge는 두지 않는다. 최악 2회(모호할 때 batch disambiguation 1회 추가), 보통 1회.
3. **topic-api의 카탈로그가 Wikidata QID를 들고 있어서**(3,190개 중 3,164개, 1:1) grounding 한 번으로 topic-api 파생 근거와 memory-api 파생 근거를 **같은 key space**에서 조회할 수 있다. 1차 초안은 이 조인을 쓰지 않았다. 단, id 체계는 같아도 **가리키는 층이 다르다** — memory-api는 개체(야마자키 증류소)에 QID를 붙이고 클래스 축으로 올라가며, 카탈로그는 주제(위스키)를 큐레이션한 계층이다. 그래서 등식 조인이 아니라 **topic이 덮는 QID 집합**(`topic_qid_map`)으로 조인하고, 그 커버리지는 실제 빌드 결과로 재야 한다(§6 T2, §7-4).
4. **memory-api는 이벤트를 발행하지 않는다.** 그러므로 memory 파생 근거는 push 미러가 아니라 **빌드 manifest를 폴링하는 pull 파생본**이어야 하고, 그 파생본에는 statement·label·blurb가 없다 — owner×QID의 개수와 날짜만 있다. "모든 memory를 미러링"하는 것이 아니다.
5. **후보 조회는 두 단계다.** 1단계는 우리 DB의 파생본으로 후보를 수십 명까지 좁힌다(topic과 근거 종류·양). 2단계는 그 후보만 memory-api에 넘겨 **질문 텍스트로 재점수**한다 — 점수와 개수만 돌아오고 statement 텍스트는 오지 않는다. 2단계가 답하지 않으면 **1단계 순위를 그대로 응답**하고 `degraded`에 남긴다. fallback이 장애 때만 도는 별도 경로가 아니라 매 요청 항상 도는 1단계라는 것이 요점이다.

추천 시점의 런타임 의존성은 topic-api 검색(지금 타입 ①과 같음)과 **memory-api evidence route 1회**다. 후자가 없어도 추천은 나간다.

---

## 1. 세 서비스의 현재

이 절은 코드에서 읽은 사실만 적는다. 1차 초안이 전제로 두었던 것과 어긋나는 부분은 §1-5에 모았다.

### 1-1. bourbon-agent — recall은 tool이고, gate는 없다

- **memory recall은 prefetch가 아니라 LLM이 고르는 tool**이다. `search_conversations` tool이 BM25 키워드 쿼리 1~5개를 모델이 직접 써서 `POST /{tenant}/search`로 **원문 대화**를 검색한다. personal knowledge의 `POST /{tenant}/users/{user_id}/personal/context`는 어디서도 호출하지 않는다. scope(clearance·참가자 그룹)는 서버가 정하고 모델이 고르지 않는다.
- **answerability gate가 없다.** 빈 recall 검사도, 확신도도, "모르겠다" 분기도 없다. 프롬프트가 "추측하거나 모른다고 하지 말고 tool을 써라"고 유도하는 것이 전부다.
- **`recommend_agents` tool이 이미 있다.** 모델이 짧은 topic 하나와 context를 뽑아 `POST /api/internal/svc/agent-discovery/recommend`를 부른다(예산 10초, `max_results=1` 고정). 결과는 모델에 돌려주고, 부수 효과로 `agent_profiles_v1` 카드를 방에 게시한다. 트리거는 **"소유자나 방의 누군가가 추천을 요청할 때"** 로 한정돼 있다.
- **agent가 agent에게 묻고 답을 합치는 코드는 없다.** 발화자는 moderator가 정하고(DM은 규칙, 그 외 방은 moderator LLM), agent들은 각자 독립 task로 답하며 서로의 답은 다음 턴의 transcript로만 본다. `moderator/agent_recommender/`가 "계획됨"으로 적혀 있고 비어 있다.
- 예산: 턴 120초, 보이는 스트림 60초 상한(bourbon-api 쪽), memory 읽기 15초, discovery 10초, tool loop 최대 5회.
- memory 적재는 이 repo가 `message_created`를 받아 메시지를 재조회해 memory-api에 upsert한다. **LLM 단계 없음.** 유일한 LLM 추출은 `persona_extractor`이고 그 결과는 memory-api가 아니라 DynamoDB의 persona 문서로 간다.

### 1-2. memory-api-v2 — 읽기는 LLM 없이, 빌드는 LLM으로

- 저장소는 **OpenSearch만**. tenant당 인덱스 다섯(`entities`·`statements`·`links`·`build`·`classes`), owner 구분은 인덱스 경계가 아니라 `owner_id` 필터다.
- **personal knowledge 빌드는 LLM을 여섯 단계에서 부른다**(extract·grounding scoring·judge·dedup·competence·classes). 배치이고 `BackgroundTasks`로 돈다. **읽기 경로는 LLM 0회**, BM25와 필터만 쓴다. embedding·kNN은 없다. "LLM을 안 쓴다"는 읽기에 대해 맞고, 빌드에 대해서는 틀리다 — 다만 빌드 비용은 owner당 한 번 내는 것이고 질문마다 내지 않는다.
- entity에는 `grounding.knowledge_qid`(Wikidata), `grounding.broader_qids[]`, `salience`, `competence_score`, `hands_on_statements`, `grounding.last_seen`이 있다. statement에는 `statement_kind`(declarative·procedural·experiential·preference·intention), `epistemic`(fact·opinion), `status`(active·invalidated), `provenance_message_ids`가 있다.
- **QID가 붙는 층은 개체다.** `knowledge_qid`는 "야마자키 증류소 Q1146917"처럼 구체적인 것이고, `broader_qids`는 `[*instance_of(P31), *occupations(P106), *class_ancestors(YAGO 클래스 폐포)]`다(`positioning.py:38-58`). 개체 자신의 P279 체인이나 제품·재료 관계는 들어가지 않는다 — 야마자키 증류소는 "위스키 증류소 → 증류소 → 공장 → …"으로 올라가고 **"위스키 Q281"에는 닿지 않는다.** extractor가 개체에 `broader`·`related` grounding을 덧붙이면 그 QID와 그것의 조상이 함께 들어가지만, 그것은 모델의 선택이라 확률적이다. 지인(acquaintance)은 `GroundingSource.LOCAL`로 `knowledge_qid=None`, QID가 없다.
- 공개 지식 corpus는 `wikidata-latest-all`(2026-06-21 수집)에서 만들고 `--dump-version 20260802`로 인덱싱한다. topic-api 카탈로그의 `dump_version`과 같은 날짜다.
- **cross-owner route가 이미 있다.** `GET /{tenant}/personal/themes/{qid}/owners`는 QID 하나에 대해 **OpenSearch 집계 한 번**으로 owner별 `count`·`last_seen`과 샘플 entity를 준다(정렬 `count|recent|pagerank`, `limit≤100`). `GET /{tenant}/personal/grounded/{qid}/entities`는 owner_id가 붙은 entity 목록을 준다. 둘 다 entity label·`personal_blurb`·salience를 그대로 노출한다.
- **이벤트 발행 없음. 인증 없음. personal 데이터에 visibility·동의 모델 없음.** 접근 제어는 tenant 경로 세그먼트뿐이다("wire authentication in before exposing this service externally"). 변경 피드에 가장 가까운 것은 빌드 manifest의 `last_build_delta.changed_entity_ids`다.
- owner당 규모 힌트: context 조립의 entity pool 상한 500, provenance entity 상한 200. 명시적 유저 수·statement 수 목표는 없다.

### 1-3. topic-api — persona에서 관심을 뽑고, QID를 들고 있다

- topic_id는 opaque 32-hex이지만 **각 항목이 `source.qid`를 갖는다.** 3,190개 중 3,164개가 Wikidata QID(중복 없음), 26개는 `N-…` 가상 축 노드다. `dump_version`은 `20260802`로 memory-api와 같다.
- **노드는 주제이고 계층은 편집 큐레이션이다.** "위스키 Q281 → 몰트 위스키·아메리칸 위스키·아일라 싱글 몰트"처럼 제품·활동·분야가 노드이고, "증류소" 같은 시설 클래스 노드는 없다. 부모 edge는 Wikidata에서 오지 않는다 — 편집 정책이 "발견에 사용한 seed나 Wikidata의 분류 경로를 그대로 사용자 계층으로 옮기지 않는다"고 명시한다(`docs/catalog-editorial-policy.md:10`). 즉 memory-api의 클래스 축과 카탈로그의 계층은 **같은 QID를 쓰는 서로 다른 두 그래프**다.
- 유저 topic은 **메시지가 아니라 bourbon-agent의 persona 문서 중 preferences 레이어**에서 LLM 두 단계로 추출된다(`persona_updated` → 신호 추출 → 카탈로그 lexical 검색으로 grounding → 마킹). persona의 `expertise` 레이어는 **의도적으로 제외**한다. 집합은 persona 텍스트의 sha256이 바뀔 때만 움직이고, 유저당 상한 300, recency 반감기 180일.
- `score`(0~100)는 **관심 강도**다. 여섯 facet(`knowledge`·`engagement`·`affinity`·`duration`·`recency` LLM 판정 + `volume` 측정)의 가중 평균에 coverage·confidence를 곱한다. **`knowledge` facet은 `score_detail.facets` 안에만 남고** 인덱스·정렬·필터 대상이 아니다. 사용자 간 비교는 설계상 가능하다(같은 범위, 같은 식, 같은 파이프라인).
- `bourbon.topics_updated`는 sync 한 번당 한 건(batch)이고 payload에 score가 없어 소비자가 재조회한다 — 우리 워커가 지금 하는 그대로다.
- memory-api와는 독립이다. 첨부물(이미지·노트·링크)만 memory-api에서 가져오고 statement는 읽지 않는다. `ExtractedTopic.extras`가 "memory-API theme payload 예약"으로 비어 있다.

### 1-4. agent-discovery-api — 우리가 이미 가진 것

- 타입 ① 파이프라인: S1 expansion(LLM 1회, 개념 그룹 0~3개 + probe) → S2 grounding(topic-api 이름 검색 + 모호할 때 batch disambiguation 1회) → S3 retrieval(`visible_topic_rows`) → S4 merge → S5 ordering → S6 assembly. 실측 p50 1.77초 / p95 3.11초(disambiguation 켠 조건, `validation_results.md` §11-4), 그중 약 98%가 모델 호출.
- 미러: `visible_topic_rows(topic_id, tier, owner_user_id, topic_score, topic_maturity, descriptions, updated_at)`, `agents(owner_user_id, agent_id, discoverable, agent_maturity, …)`. `discoverable`은 "공개 topic이 하나 이상"에서 **우리가 파생**한다(bourbon-api는 그 이벤트를 만들지 않았다).
- 카탈로그 복사본(`data/catalog_dist/catalog.json`, 3,190 / 3,136 edges)을 커밋해 두고 있고, `evaluation/search.py`에 topic-api 이름 검색의 검증된 in-process 복사본이 있다(2,775 probe로 원본과 대조).
- 워커는 여섯 주기 루프를 돌리고(`popularity-rebuild`·`cf-fit`·`cf-sweep`·`cf-gate`·`population-count`·`retention-sweep`), 이벤트 여섯을 받는다. `message_created`는 id만 싣는다.

### 1-5. 1차 초안의 전제와 어긋나는 것

| 1차 초안 | 코드의 현재 | 이 문서의 대응 |
|---|---|---|
| S0 요청자 agent가 자기 근거를 결정적으로 검색한다 | 그런 단계가 없다. recall은 모델의 tool 선택이다 | 트리거를 tool 결정으로 둔다(§6 T0) |
| S1 경계선에서 LLM answerability judge | 존재하지 않고, 두면 discovery 앞에 LLM 1회가 추가된다 | 두지 않는다 |
| consultable 필터는 memory-api가 강제한다 | memory-api에 동의 모델·인증이 없다 | 첫 슬라이스(§15의 1번)는 우리 `agents.discoverable`, opt-in은 bourbon-api에 요청(§10) |
| Phase F에서 이벤트로 projection | memory-api는 이벤트를 발행하지 않는다 | 빌드 manifest 폴링(§7-2) |
| topic-api 신호는 관심이라 knowledge에 못 쓴다 | `knowledge` facet이 `score_detail`에 있다 | 미러에 컬럼으로 추가해 첫 근거 소스로 쓴다(§7-1) |
| grounding은 memory 쪽 QID 어댑터 | 카탈로그가 QID를 1:1로 들고 있다. 다만 memory는 개체·클래스 축, 카탈로그는 주제·큐레이션 축이라 등식으로는 자주 빈다 | 기존 S2 grounding 한 번 + `topic_qid_map`으로 두 소스를 조회한다(§6 T2, §7-4). 커버리지는 측정 항목이다(§16) |
| memory-api에 배치 capability API를 신설한다(Phase B) | 있는 route는 전부 label·blurb·텍스트를 돌려준다 | 신설은 맞다. 다만 모양이 다르다 — tenant 전체 검색이 아니라 **우리가 넘긴 후보 목록 안에서** 질문 텍스트로 재점수하고 점수·개수만 돌려주는 route(§6 T3, §16) |

---

## 2. 문제의 재정의

핵심 질문은 "수많은 유저 중 누가 이 질문에 답할 수 있는가"다. 이것을 유저마다 LLM에게 물으면 비용과 지연 시간이 유저 수에 비례하므로 애초에 설계에 넣을 수 없다. 대신 셋으로 나눈다.

```text
오프라인  owner × QID capability 집계        memory-api 빌드가 이미 만든다 / topic-api sync가 이미 만든다
온라인    질문 → QID 몇 개 → 집계 조회 → 랭킹   LLM 1회(타입 ①과 같은 호출), 나머지는 SQL과 산술
실행 시   선택된 1~2명이 자기 recall로 답한다     agent가 매 턴 이미 하는 일, discovery 비용 아님
```

"진짜 답할 수 있는지"는 온라인에서 확정하지 않는다. 추천은 **근거를 가졌을 가능성**의 순위이고, 확정은 선택된 agent가 실행 시점에 자기 memory를 검색해서 한다. 그래서 이 기능의 핵심 품질 지표는 "추천 당시 coverage와 실행 당시 실제 answerability 사이의 calibration error"이고(§13), 랭커는 그 지표로 고친다.

이 구조는 타입 ①과 같다. 타입 ①이 10만 합성 유저에서 후보 조회를 한 자릿수 ms로 끝낸 이유가 그대로 적용된다 — 온라인 비용은 유저 수가 아니라 grounding된 topic의 보유자 수에 비례한다.

---

## 3. 제품 시나리오

### 3-1. 단일 agent

> 홈 에스프레소 머신에서 압력이 너무 높을 때 추출을 어떻게 조정해야 해?

요청자의 agent가 자기 recall에서 근거를 찾지 못한다. discovery는 질문을 need 하나(espresso 추출 조정, procedural)로 읽고, 그 topic/QID 아래에 procedural·experiential 근거를 가진 소유자를 찾는다.

> 이 질문은 제가 가진 근거로 답하기 어렵습니다. 에스프레소 추출 조정 경험이 있는 agent를 연결할 수 있습니다.

추천 이유는 공개 가능한 것에만 근거한다. 타인의 statement·메시지 내용은 이유에 들어가지 않는다.

### 3-2. agent group

> 도쿄에서 아이와 갈 만한 위스키 증류소 여행을 어떻게 계획할까?

need는 셋으로 나뉜다 — ① 도쿄 근교 위스키 증류소(declarative), ② 어린이 입장 조건·가족 방문 경험(experiential), ③ 도쿄에서 증류소까지 이동(procedural). 한 사람이 셋을 다 덮으면 단일 추천이 group보다 우선한다. 아니면 A(①②)와 B(③)처럼 **required need 전체를 최소 인원으로 덮는** 조합을 고른다. group은 상위 N명 목록이 아니라 제한된 set-cover다.

### 3-3. 추천하지 않는 경우

- required need 중 하나를 아무도 덮지 못한다
- grounding이 실패했거나 모호하게 끝났다
- discoverable(나중에는 consultable) 후보가 없다
- 근거 소스 조회가 일부 실패해 완전한 추천이라고 말할 수 없다

결과는 `insufficient_coverage`·`no_consultable_agents`·`grounding_ambiguous`·`source_incomplete`처럼 **지식 부족과 서비스 상태를 구분**한다. 숨은 후보의 존재를 응답에서 유출하지 않는 규칙은 기존 불변식 5와 같다.

---

## 4. 서비스 책임

| 책임 | 소유 | LLM |
|---|---|---|
| "내 근거로 못 답한다"는 판단과 discovery 호출 | requester agent(bourbon-agent), tool 결정 | 추가 호출 없음 — 이미 돌고 있는 턴의 tool call |
| 질문 → knowledge need(개념 그룹 + 중요도 + 지식 종류) | agent-discovery-api, 기존 expansion 확장 | 1회 |
| need → topic_id/QID grounding | agent-discovery-api, 기존 S2 | 모호할 때만 batch 1회 |
| owner × QID capability 집계 만들기 | memory-api 빌드, topic-api sync | 그쪽 배치(이미 지불) |
| 집계를 우리 쪽에 파생본으로 유지 | agent-discovery-api 워커 | 없음 |
| 1단계: 파생본으로 후보 좁히기 | agent-discovery-api | 없음 |
| 2단계: 후보의 statement를 질문 텍스트로 재점수 | memory-api evidence route (BM25) | 없음 |
| calibration·최종 랭킹 | agent-discovery-api | 없음 |
| group 구성 | agent-discovery-api | 없음 |
| 추천 이유 | agent-discovery-api, 템플릿 | 없음 |
| discoverable / consultable 판정 | 첫 슬라이스는 우리 `agents.discoverable`, 이후 bourbon-api의 agent 설정 | 없음 |
| 선택된 agent의 답변 | 그 agent(bourbon-agent) | agent당 1회 이상 |
| 답변 종합·충돌 보존 | moderator 계열(bourbon-agent) | 1회 |

### 4-1. memory-api가 소유하는 것

personal knowledge의 저장 의미와 검색 의미 — entity·statement, QID grounding(identity·broader), statement kind, active·invalidated, provenance, salience·competence, 빌드 manifest, 그리고 **우리가 넘긴 후보 안에서 질문 텍스트와 statement의 매치 점수**. **최종 추천 점수나 순위는 만들지 않는다.** 누가 전문가인지는 discovery의 제품 정책이다.

### 4-2. discovery가 소유하는 것

need와 중요도, coverage matrix, cross-owner 신호의 calibration, 단일 충분성 threshold, group set-cover와 인원 상한, 요청자 제외, 응답과 decision log, degradation의 의미, **그리고 근거 파생본의 스키마와 갱신 주기.**

### 4-3. bourbon-agent가 소유하는 것

discovery를 부를지의 판단, 선택된 agent의 실행, 종합. discovery는 답변을 실행하지 않는다. 종합 계층의 자연스러운 자리는 이미 "계획됨"으로 적힌 `moderator/agent_recommender/`다 — moderator는 방 전체를 보고 발화자를 고르는 유일한 자리다.

---

## 5. 요청 흐름

```text
User
  │ 질문
  ▼
Requester Personal Agent  (bourbon-agent, 이미 돌고 있는 턴)
  ├─ search_conversations 등 자기 recall (모델의 선택, 지금과 같음)
  └─ 근거가 없다고 판단하면 tool 호출  ──────────┐   추가 LLM 0회
                                              ▼
Agent Discovery  POST /recommend/knowledge
  ├─ T1 need 추출 = expansion 스키마 확장         LLM 1회
  ├─ T2 grounding → topic_id (+QID)             topic-api 검색, 모호할 때 batch LLM 1회
  ├─ T3-1 후보 좁히기: 소스 A(topic 파생) + 소스 B(memory 파생)   우리 PostgreSQL, 수십 명
  ├─ T3-2 재점수: 그 후보만 memory-api evidence route            질문 텍스트 BM25, 점수만 회신
  │        └─ 답 없으면 T3-1 순위로 진행 + degraded
  ├─ T4 결정적 랭킹, T5 group planning
  └─ T6 조립 + decision log
                                              │ 추천
                                              ▼
Requester Agent → 사용자에게 제시 (카드), 수락 시 실행은 별도 경로
```

추천만 보여 주는 UX는 discovery 결과에서 끝난다. 실행과 종합은 **별도 예산과 별도 실패 계약**을 갖는다(§11-3).

---

## 6. 단계별 설계

### T0. 트리거 — judge를 두지 않고 tool 결정으로 한다

bourbon-agent의 `recommend_agents` tool은 지금 "누군가 추천을 요청할 때"만 불린다. 이 조건을 **"소유자의 질문에 내 recall로 답할 근거가 없을 때"** 로 넓히거나, 같은 클라이언트를 쓰는 두 번째 tool을 둔다. 어느 쪽이든:

- 추가 LLM 호출이 없다. 모델은 이미 턴 안에서 돌고 있고 tool call은 그 턴의 일부다.
- 새 route가 memory-api에 필요하지 않다. 요청자의 근거 검색은 지금 하는 `search_conversations`다.
- 1차 초안이 걱정한 "모델이 사전학습 지식으로 충분하다고 오판"은 방향이 반대다 — 여기서 오판은 **도움을 청하는 쪽**이라 비용이 추천 한 번이다.

단점은 결정적이지 않다는 것이다. 얼마나 자주 불리는지, 불렸을 때 실제로 근거가 없었는지는 decision log로 잰다(§13). 결정적 gate가 필요해지면 그 자리는 `moderator/agent_recommender/`이고, 그때도 discovery 계약은 바뀌지 않는다.

### T1. need 추출 — expansion 스키마 확장

타입 ①의 S1 expansion은 이미 "개념 그룹 0~3개, 그룹마다 probe"를 낸다(`ConceptGroup{index, probes}`). knowledge need는 개념 그룹에 두 필드를 더한 것이다.

```json
{
  "groups": [
    {"index": 0, "probes": ["도쿄 위스키 증류소", "Tokyo whisky distillery"],
     "importance": "required", "knowledge_kind": "declarative"},
    {"index": 1, "probes": ["증류소 어린이 입장", "family distillery visit"],
     "importance": "required", "knowledge_kind": "experiential"},
    {"index": 2, "probes": ["도쿄 근교 이동", "Tokyo transit"],
     "importance": "optional", "knowledge_kind": "procedural"}
  ]
}
```

- 호출은 **하나**다. 분해와 확장을 따로 부르지 않는다.
- 그룹 상한은 타입 ①의 3을 그대로 쓴다. 1차 초안의 "1~5개"보다 좁고, 첫 슬라이스에는 충분하다.
- `importance`·`knowledge_kind`가 스키마 검증에 실패하면 각각 `required`·`declarative`로 폴백하고 `degraded`에 남긴다. 그룹 자체를 버리지 않는다.
- 모델은 owner·agent를 고르지 않고, 근거 소스를 보지 않는다. 질문 원문은 타입 ①과 같이 로그·예외·Sentry에 남기지 않는다(불변식 7).

### T2. grounding — 한 번, 두 소스

기존 S2를 그대로 쓴다. probe로 topic-api 이름 검색을 하고, 규칙으로 하나를 고르며, 못 고를 때만 batch disambiguation 1회. 결과는 그룹마다 `topic_id` 하나다.

topic_id에서 QID는 우리가 커밋한 카탈로그로 읽는다(`source.qid`, 3,164/3,190). 가상 노드 26개는 QID가 없으므로 소스 B 조회를 건너뛰고 소스 A만 쓴다.

**소스 B의 조회 키는 topic의 QID 하나가 아니라 topic이 덮는 QID 집합이다.** memory-api는 개체에 QID를 붙이고 P31·YAGO 클래스 축으로 올라가므로(§1-2), "위스키 Q281"로 등식 조회를 하면 "야마자키 증류소"만 말한 사람은 나오지 않는다 — 그 개체의 `broader_qids`는 증류소·공장 쪽으로 올라가고 위스키에 닿지 않는다. 그래서 오프라인에 `topic_qid_map(topic_id, qid, via, distance)`를 두고(§7-4) 조회는 `qid IN (SELECT qid FROM topic_qid_map WHERE topic_id = …)`로 한다.

그래도 **grounding은 한 번**이다. 결과 topic_id 하나가 소스 A에는 그대로, 소스 B에는 매핑을 거쳐 조회 키가 된다. 1차 초안의 "S3 공개 지식 grounding + S4 memory 검색"이 여기서 한 단계로 합쳐지는 것은 같다.

이 매핑이 잡지 못하는 것이 있다. "위스키 증류소 → 위스키" 같은 **시설↔제품** 관계는 P279·P31에도 memory-api의 typed_links 화이트리스트(author·director·manufacturer·genre 계열)에도 없다. 그래서 소스 B는 주제를 개체로 직접 언급한 사람("위스키 좋아해")은 잡고, 구체적 개체만 말한 사람("야마자키·하쿠슈 다녀왔어")은 extractor가 related grounding을 붙였을 때만 잡는다. 이 사각의 크기는 설계로 정할 수 없고 실제 빌드 결과로 재야 한다(§16 memory-api 질문 2).

### T3. 근거 조회 — 두 단계

후보를 **좁히는 일**과 **고르는 일**을 나눈다. 좁히는 것은 우리 DB가 하고(T3-1), 고르는 것은 memory-api가 질문 텍스트로 한다(T3-2). T3-2가 답하지 않으면 T3-1의 순위가 그대로 답이다.

```text
T3-1  우리 PostgreSQL   topic + 근거 종류·양     10만 명 → 수십 명     "무엇에 대해"
T3-2  memory-api       질문 텍스트 BM25         수십 명 재점수        "정확히 어떤 조건"
```

grounding에서 질문의 조건("압력이 너무 높을 때")은 topic으로 압축되며 사라진다. T3-1만으로는 에스프레소에 procedural 근거 8건을 가진 사람이 그 8건 모두 로스팅 이야기인지 구분하지 못한다. T3-2가 그 조건을 되찾는다. 두 단계는 다른 축(topic ↔ 텍스트)을 보므로 겹치지 않고 보완한다.

#### T3-1. 후보 좁히기 — 두 소스, 우리 DB

두 소스 모두 우리 PostgreSQL에 있고 조회는 SQL이다. 각 소스가 무엇을 답하는지가 다르다.

**소스 A — topic-api 파생. "이 주제에 깊은 관심을 드러낸 사람".**
`visible_topic_rows`에 컬럼 둘을 더한다: `knowledge_facet`(`score_detail.facets.knowledge`, 0~100)과 `confidence`. `topics_updated`를 받으면 이미 재조회하므로 적재 경로는 바뀌지 않는다. 서브트리 롤업은 `catalog_edges`로 지금과 같이 한다.

**소스 B — memory-api 파생. "이 주제에 대해 구체적 근거 statement를 가진 사람".**
새 테이블 `knowledge_capabilities`, key는 `(owner_user_id, qid)`:

```text
owner_user_id            uuid
qid                      text        Wikidata QID (identity 또는 broader)
match                    text        identity | broader
active_statements        int
procedural_statements    int
experiential_statements  int
hands_on_statements      int
has_provenance           bool
last_seen_at             timestamptz
competence_norm          float       owner 내부 분포로 정규화한 값, 원시 competence_score 아님
observed_build_at        timestamptz memory-api manifest의 built_at
```

**들어가지 않는 것**: statement 텍스트, entity label, `personal_blurb`, message id, salience 원시값. 이 테이블은 "몇 개, 언제"만 안다. 크기는 owner당 entity 수(수백)로, `visible_topic_rows`의 유저당 상한 300과 같은 자릿수다. 10만 유저면 수천만 행이고 PostgreSQL이 감당하는 범위다.

조회는 소스 A가 `topic_id`(+ `catalog_edges` 서브트리), 소스 B가 `qid IN (topic_qid_map의 그 topic 행)`이고, `JOIN agents … WHERE discoverable`과 요청자 제외를 여기서 적용한다. 두 소스를 owner로 합쳐 need별 coverage matrix를 만들고, 1단계 점수로 정렬해 **상위 N명**(레지스터, 초기 50)을 남긴다. 둘 다 인덱스 한 번 타는 SQL이다.

이 시점의 순위를 `stage1_ranking`으로 보관한다. T3-2가 실패하면 이것이 응답이 된다.

#### T3-2. 재점수 — 후보만 memory-api에

1단계의 N명 id와 need를 memory-api의 evidence route에 넘긴다. **`owners` 허용 목록이 요청의 일부**라는 것이 이 route의 핵심이다.

```json
POST /{tenant}/personal/evidence/search
{
  "needs": [
    {"need_id": "n0", "text": "에스프레소 압력 높을 때 추출 조정",
     "kind": "procedural", "qids": ["Q...", "Q..."]}
  ],
  "owners": ["<1단계 N명의 owner id>"],
  "exclude_owner": "<requester>"
}
```

```json
{
  "owners": [
    {"owner_id": "…", "needs": [
      {"need_id": "n0", "matched": 3, "max_score": 12.4,
       "procedural": 2, "experiential": 1,
       "last_seen": "2026-07-12", "has_provenance": true}
    ]},
    {"owner_id": "…", "needs": [{"need_id": "n0", "matched": 0}]}
  ],
  "searched_needs": ["n0"],
  "truncated": false
}
```

- memory-api는 `owners` 안의 statement만 BM25로 매치한다. **statement 텍스트·entity label·message id는 응답에 없다.** 점수와 개수와 날짜만 온다.
- `owners`가 우리 `discoverable`을 이미 통과한 집합이라, 비동의 owner에 관한 데이터는 어떤 형태로도 우리 프로세스에 오지 않는다(§10). memory-api에 동의 모델이 없어도 이 경계는 우리 쪽에서 닫힌다.
- 검색 범위가 N명이라 OpenSearch 비용도 tenant 전체 집계가 아니다.
- timeout은 레지스터 행(`evidence_search.timeout_ms`, 초기 800)으로 두고, 재시도 사다리는 우리 쪽 하나만 갖는다(§12).

T3-2의 점수가 T3-1의 순위를 다시 매긴다. 에스프레소 근거가 많아 1단계 상위였지만 압력 이야기가 없는 사람은 내려가고, 압력 조정을 3건 말한 사람은 올라간다.

#### fallback — T3-2가 답하지 않을 때

memory-api가 죽었거나 timeout 안에 답이 없으면 **`stage1_ranking`을 그대로 응답**하고 `degraded: ["evidence_search_unavailable"]`을 붙인다. 새로 계산하는 것이 없다 — 장애 때만 도는 별도 코드 경로가 아니라, 매 요청 항상 돌던 1단계의 결과다. `truncated: true`면 받은 것으로 순위를 매기고 `evidence_search_incomplete`를 붙인다.

#### 부수 효과 — 매 요청이 실측

정상 요청에서는 두 순위가 다 있다. `stage1_ranking` 상위 k와 최종 순위 상위 k의 겹침을 journal에 남기면(§13) **"topic만으로 얼마나 맞히는가"** 를 운영 중에 계속 잰다. 겹침이 높으면 fallback 때 품질 손실이 작고, 낮으면 fallback 때 `mode: none`을 더 쉽게 내도록 threshold를 올리는 근거가 된다.

#### 한계

T3-1이 찍지 못한 사람은 T3-2도 보지 못한다. `topic_qid_map`의 사각(§7-4)이 그대로 recall 상한이다. 사각이 크게 측정되면 `owners` 없이 tenant 전체를 치는 모드를 여는지 다시 논의하되, 그것은 memory-api 쪽에서 동의를 걸러 줄 수 있게 된 뒤의 이야기다(열린 항목 §17-11).

### T4. 단일 agent 랭킹 — 결정적

feature 후보(타입 ①의 랭커 feature 표와 같은 방식으로 레지스터에 올린다):

- required need coverage(gate), optional need coverage
- 소스 A: `knowledge_facet`, `confidence`, tier
- 소스 B: need의 `knowledge_kind`와 일치하는 statement 수, `has_provenance`, `last_seen_at`의 신선도, `competence_norm`, identity/broader 구분
- 두 소스가 같은 owner를 가리키는지(교차 확인)
- `agent_maturity`(이미 있음)

```text
single_score = required_coverage_gate × Σ_need( kind_match × evidence × freshness × provenance ) × source_agreement
```

원시 `competence_score`·`salience`는 owner 내부 척도다. 사용자 간 절대 순위로 쓰지 않고 owner별 분포로 정규화한 값만 feature로 쓴다. 한 agent가 모든 required need를 threshold 이상으로 덮으면 단일 추천이 group보다 우선한다.

### T5. group planning — 결정적

단일이 부족할 때만 돈다. 후보 pool을 랭킹 상위 일정 수로 제한한 뒤 bounded combination search.

- 첫 슬라이스 **최대 2명**
- 모든 required need가 threshold 이상
- 각 member는 다른 member가 못 덮는 need를 최소 하나 덮어야 한다
- 같은 need만 중복하는 member는 제외

need 최대 3, 후보 수십, 인원 2면 탐색은 조합 수백 개다. LLM을 쓰면 재현성과 decision log 설명력이 떨어진다.

### T6. 응답 조립

이유는 템플릿이다. "일본 위스키·증류소 관련 근거가 있습니다." "도쿄 가족 여행 경험을 보완할 수 있습니다." LLM 문장 생성은 품질상 필수가 아니고, 타인의 근거를 모델에 보낼 유인이 생기므로 첫 슬라이스에 넣지 않는다.

---

## 7. 근거 파생본의 적재

### 7-1. 소스 A — 지금 이벤트 그대로

`topics_updated` → 재조회 → `visible_topic_rows` 교체. 바뀌는 것은 재조회 응답에서 `score_detail.facets.knowledge`·`confidence`를 읽어 컬럼에 넣는 것뿐이다. topic-api의 `GET /users/{id}/topics` 응답에 `score_detail`이 포함되는지는 확인이 필요하다(§16).

### 7-2. 소스 B — 폴링 파생본

memory-api는 이벤트를 내지 않으므로 우리 워커의 **일곱 번째 주기 루프**가 pull한다.

1. `GET /{tenant}/admin/personal/build`(모든 owner의 manifest, 페이지)를 읽어 `built_at`이 우리 `observed_build_at`보다 새로운 owner를 고른다.
2. 그 owner에 대해 owner-scoped route로 entity를 읽고(`GET /{tenant}/users/{id}/personal/entities`, grounding 필드만 사용) 소스 B 행을 **교체**한다(타입 ①의 `CatalogRepository.replace`처럼 트랜잭션 하나).
3. label·blurb·statement 텍스트는 읽고 버린다. 저장하지 않는다.

주기는 memory-api 빌드 주기에 맞춘다. 빌드 자체가 배치라 폴링이 잃는 신선도는 없다. 한 사이클이 만지는 owner 수와 소요 시간은 로그로 낸다.

**이것이 "모든 memory를 미러링"이 아닌 이유**: 원본은 statement(owner당 수천, 텍스트 포함)이고 파생본은 owner×QID 행(owner당 수백, 숫자와 날짜)이다. 파생본에서 원문을 복원할 수 없고, 삭제·동의 철회는 다음 폴링에서 행 교체로 따라간다.

**memory-api에 바라는 것 하나**(§16): label 없이 `(qid, match, counts, last_seen)`만 주는 owner-scoped 집계 route. 없어도 동작하지만 있으면 읽고 버리는 데이터가 없어지고 응답이 작아진다. 1차 초안의 "배치 capability API"보다 훨씬 작은 요청이다.

### 7-3. 소스 B가 비어 있을 때

`bourbon-v2` tenant에 personal build가 실제로 몇 owner에 대해 돌았는지는 코드로 알 수 없다(§16). 소스 B 행이 없는 owner는 소스 A만으로 랭킹되고, 두 소스의 교차 확인 feature는 0이다. 파생본이 비어 있어도 서비스는 동작한다 — 그래서 슬라이스 1을 소스 A만으로 시작할 수 있다(§15).

### 7-4. `topic_qid_map` — 카탈로그 topic이 덮는 QID 집합

카탈로그가 바뀔 때만 다시 만드는 오프라인 파생본이다. 카탈로그 복사본처럼 커밋해 두고 `load_catalog`와 같은 방식으로 적재한다.

```text
topic_id    카탈로그 topic
qid         이 topic의 근거로 인정할 Wikidata QID
via         seed | narrower | typed
distance    0 (seed) | 1 | 2
```

재료는 memory-api의 공개 지식 route다. `POST /knowledge/expand`는 seed QID 최대 32개를 받아 `narrower`(역 P31·P279), `typed`(화이트리스트 관계), `co_link`를 depth 2까지 돌려주는 배치 traversal이고 hop당 round trip이 고정이다. 3,164 topic이면 100회 안쪽이다. `max_generality`로 지나치게 넓은 클래스를 잘라 낸다.

- `seed`: topic의 QID 자체. identity 매치.
- `narrower`: 그 topic의 하위 클래스와 인스턴스. "몰트 위스키"의 narrower에 "야마자키 12년"이 있다면 그것을 개체로 가진 사람이 잡힌다.
- `typed`: 화이트리스트 관계로 이어진 것. 저작·제작 계열이라 취미·기술 topic에서는 기여가 작을 것으로 본다. 측정 뒤 뺄 수 있다.

**넣지 않는 것**: memory-api의 `broader` 확장(위로 올라가면 "음료·식품"까지 번져 topic 경계가 사라진다), `co_link`(링크 그래프 동시 출현은 근거가 아니다).

한 QID가 여러 topic에 속할 수 있다(몰트 위스키 ⊂ 위스키). 그 경우 두 topic 행에 모두 넣고, 랭킹은 grounding된 topic 쪽 행만 읽으므로 이중 계산은 없다.

**이 테이블의 커버리지가 소스 B의 상한이다.** 실제 memory 빌드의 `broader_qids`·`knowledge_qid` 분포와 `topic_qid_map`의 교집합이 얼마인지가 첫 측정이고, 그 숫자가 낮으면 시설↔제품 같은 빠진 관계를 카탈로그 쪽 편집(예: "위스키 증류소"를 위스키의 자식 topic으로)으로 메울지, 매핑에 수동 행을 둘지 정한다.

---

## 8. API 초안

기존 `POST /recommend/explicit`은 공개 topic 보유자를 찾는 타입이라 그대로 둔다. 새 타입은 route가 다르고 응답 envelope에 `needs`와 `mode`가 있다.

```http
POST /api/internal/svc/agent-discovery/recommend/knowledge
```

요청:

```json
{
  "user_id": "uuid",
  "question": "도쿄에서 아이와 갈 만한 위스키 증류소 여행을 어떻게 계획할까?",
  "context": "선택. 현재 대화 맥락",
  "allow_group": true,
  "max_agents": 2,
  "room_id": "uuid",
  "lang": "ko"
}
```

응답:

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "mode": "group",
  "needs": [
    {"need_id": "n0", "label": "일본 위스키 증류소", "importance": "required", "topic_id": "…"},
    {"need_id": "n1", "label": "도쿄 가족 여행", "importance": "required", "topic_id": "…"}
  ],
  "agents": [
    {"agent_id": "uuid", "owner_user_id": "uuid", "covers": ["n0"], "reason": "일본 위스키·증류소 관련 근거가 있습니다."},
    {"agent_id": "uuid", "owner_user_id": "uuid", "covers": ["n1"], "reason": "도쿄 가족 여행 경험을 보완할 수 있습니다."}
  ],
  "empty": false,
  "degraded": []
}
```

- `mode`: `single | group | none`
- `agents[]`의 항목은 타입 ①의 `RecommendedAgent`를 재사용하고 `covers`만 더한다.
- `confidence`는 **첫 슬라이스에서 외부 필드로 열지 않는다.** calibration 전의 숫자는 decision log에만 둔다(열린 항목 §17-5).
- `degraded[]` 후보: `expansion_partial`(기존), `need_fields_defaulted`, `source_b_stale`, `evidence_search_unavailable`, `evidence_search_incomplete`. `grounding_failed`·`grounding_ambiguous`는 타입 ①과 같이 422다.
- 걸러진 후보 수, 숨은 후보의 존재를 추정할 수 있는 값은 응답에 없다(불변식 5).

---

## 9. 도메인 확장

1차 초안은 "기존 `TopicQuery`·`SourceHit`·`ExplicitRanker`에 끼워 넣지 말라"고 했다. 이 문서는 그것을 **슬라이스별로**(§15) 본다. 그 경고의 이유 셋 — topic visibility를 동의로 간주, `SourceHit.tier`에 memory 의미를 넣음, `topic_score`를 evidence sufficiency로 읽음 — 은 전부 **memory-api 파생 근거를 topic row의 모양에 담을 때** 생기는 문제다. 1차 초안에는 그 근거밖에 없었다.

- **슬라이스 1(소스 A만)**: need 하나는 grounding된 `topic_id`이고, 그것은 곧 `TopicQuery`다. 데이터는 진짜 topic row라 tier는 진짜 topic visibility이고 `knowledge_facet`은 topic-api가 그 row에 붙인 값이다 — 억지로 넣는 의미가 없고, 동의는 tier가 아니라 `agents.discoverable`로 따로 건다(§10-2). 새 것은 need 여러 개를 한 요청에서 돌리는 orchestration, `knowledge_facet`·coverage를 읽는 랭커 feature, set-cover, envelope이다. 기존 도메인 위에 얹는 것이 맞다. 여기서 새 `CandidateSource`를 만들면 `visible_topic_rows`를 읽는 코드가 둘이 되어 조금씩 다르게 굴러간다.
- **슬라이스 2(소스 B)**: QID로 조회하는 새 `CandidateSource`와 새 `SourceHit` 종류가 필요하다. 여기서부터 `SourceHit.tier`에 memory 의미를 억지로 넣지 않는다는 1차 초안의 경고가 유효하다.

새 도메인 후보: `KnowledgeNeed`(ConceptGroup + importance + kind), `NeedCoverage`, `CapabilityHit`(소스 B), `GroupPlan`, `KnowledgeRecommendation`. 새 stage 후보: `GroupPlanning` 하나. 나머지는 기존 stage의 파라미터 확장이다.

재사용하면 안 되는 의미는 1차 초안과 같다 — topic visibility를 personal knowledge 동의로 간주하지 않고, `topic_score`를 evidence sufficiency로 읽지 않는다.

---

## 10. 개인정보·권한

### 10-1. 지금 있는 것과 없는 것

- memory-api personal 데이터에는 visibility·동의가 없다. cross-owner route는 tenant 경로만 알면 누구의 label이든 준다.
- topic-api의 `public/friends/private`는 **관심사 공개** 범위다. 관심사를 공개하는 것과 사적 대화에서 배운 것을 대신 답하게 하는 것은 노출 강도가 다르다. 재사용하지 않는다.
- 우리 `agents.discoverable`은 "공개 topic이 하나 이상"에서 파생한 값이다.

### 10-2. 첫 슬라이스의 정책

```text
discoverable   agents.discoverable (지금 것). 후보로 발견될 수 있음
consultable    없음 → bourbon-api의 agent 설정에 opt-in 필드로 요청 (§16). 있기 전에는 discoverable로 대체하고 응답 문구에 "연결 가능" 대신 "관련 근거가 있는 것으로 보임"을 쓴다
answer_share_scope, evidence_share   실행 단계(bourbon-agent)의 것. 이 문서 범위 밖
```

강제 위치: 후보 조회 SQL의 `JOIN agents … WHERE discoverable`(나중에 `consultable`). **discovery가 모든 후보를 받은 뒤 거르지 않는다** — 파생본 자체에 label이 없으니 걸러 내기 전에 읽는 private 데이터도 없다.

실행 시점 재확인은 agent가 한다. 추천 시점의 권한은 실행 시점의 권한을 보장하지 않는다.

### 10-3. 모델 제공자 경계

- discovery의 LLM에는 요청자의 질문만 간다. 타인의 근거는 어떤 형태로도 가지 않는다(파생본에 텍스트가 없어 갈 수도 없다).
- 선택된 agent의 LLM에는 그 agent 자신의 recall 결과만 간다.
- 종합 LLM에는 각 agent가 공개 가능한 형태로 만든 answer claim만 간다.
- 로그·Sentry·decision log에는 digest·길이·count·reason code만 남는다.

---

## 11. 지연 시간과 비용

### 11-1. 전제

SLA가 아니라 첫 구현의 예산을 잡기 위한 추정이다. 확인된 기준점:

- 타입 ① 실측: disambiguation 켠 조건에서 p50 1.77초 / p95 3.11초, 약 98%가 모델 호출
- PostgreSQL 후보 조회: 10만 합성 유저에서 한 자릿수 ms
- `LLM_PROXY_TIMEOUT_SECONDS` 시도당 6초 최대 2회, `RECOMMEND_DEADLINE_SECONDS` 20초
- bourbon-agent 쪽 예산: discovery 호출 10초, 턴 120초, 보이는 스트림 60초

### 11-2. 추천 경로

| 단계 | LLM | 예상 p50 | 예상 p95 | 비고 |
|---|---:|---:|---:|---|
| T0 tool 결정 | 없음(추가분) | 0 | 0 | 이미 돌고 있는 턴 |
| T1 need 추출 | 1회 | 0.8~1.8 s | 2.5~4.5 s | 타입 ① expansion과 같은 호출, 출력 필드 둘 추가 |
| T2 grounding 검색 | 없음 | 30~100 ms | 150~400 ms | 그룹 3개 병렬 |
| T2 disambiguation | 조건부 1회 | 0.5~1.5 s | 2~4 s | batch 1회 |
| T3-1 두 소스 조회 | 없음 | 2~15 ms | 30~80 ms | SQL, 후보 상한 N=50 |
| T3-2 evidence route | 없음 | 80~250 ms | 400~900 ms | 후보 N명 BM25, 1차 초안 추정 그대로, **구현 후 실측** |
| T4·T5 랭킹·group | 없음 | < 10 ms | < 50 ms | |
| T6 조립·journal | 없음 | 5~30 ms | 30~100 ms | |

**end-to-end 추정: p50 1.6~2.8초, p95 4~7초.** 1차 초안의 3회 LLM(judge·decomposition·disambiguation) 대비 경로가 하나 줄었고, 남은 둘은 타입 ①이 이미 실측한 호출이다. T3-2가 더한 것은 네트워크 1홉이고 timeout 800 ms가 상한이다. bourbon-agent의 10초 예산 안에 든다.

### 11-3. 실행 경로 — 이 문서 범위 밖이지만 예산은 분리한다

선택된 agent 1~2명이 병렬로 자기 recall(15초 예산)과 답변 completion을 하고, 종합이 1회 더 든다. 1차 초안의 추정(단일 p50 3~7초, group p50 5~10초 / p95 15~25초)은 유지하되 **실측 전의 숫자**다. 턴 120초 / 스트림 60초 안에 들지만, 추천 응답과 실행을 하나의 timeout에 넣지 않는다.

### 11-4. 비용

질문당 LLM 호출 1~2회, 토큰은 타입 ① 대비 출력 필드 둘만큼 증가. 소스 B의 폴링은 LLM이 없고, memory-api 빌드 비용은 우리 것이 아니다. **유저 수에 비례하는 LLM 비용이 없다**는 것이 이 설계의 요점이다.

---

## 12. 실패와 degradation

| 실패 | 추천 단계 | 실행 단계 |
|---|---|---|
| T1 LLM 실패 | 타입 ①과 같이 verbatim 폴백 + `expansion_partial` | — |
| need 필드 스키마 위반 | `required`·`declarative`로 폴백 + `need_fields_defaulted` | — |
| grounding 후보 없음 | 422 `grounding_failed` | 실행 안 함 |
| grounding 모호 | required need면 422 `grounding_ambiguous`, optional이면 그 need 제외 + degraded | — |
| topic-api 검색 불가 | 503(타입 ①과 같음) | — |
| 소스 B 파생본이 오래됨 | 정상 응답 + `source_b_stale`(threshold는 레지스터). T3-2가 살아 있으면 조건 매치가 보정한다 | — |
| 소스 B 폴링 실패 | 다음 사이클로, 추천은 소스 A로 계속 | — |
| evidence route timeout·5xx | `stage1_ranking`으로 응답 + `evidence_search_unavailable` | — |
| evidence route `truncated` | 받은 것으로 재점수 + `evidence_search_incomplete` | — |
| evidence route가 `owners` 밖 owner를 돌려줌 | 그 항목은 버리고 로그. 계약 위반이라 알람 | — |
| required need 하나를 아무도 못 덮음 | `mode: none`, `empty: true` | — |
| 실행 시 agent가 `unsupported` | — | 다른 후보로 한 번 대체, 그래도 실패면 uncovered |
| member timeout | — | 남은 member로 required coverage 재계산 |

재시도는 한 계층만 갖는다. discovery가 topic-api나 evidence route를 재시도하면 그쪽은 자기 OpenSearch 요청을 다시 재시도하지 않고, LLM은 transport 재시도와 pipeline 재시도를 중첩하지 않는다.

**calibration error는 모드별로 따로 잰다.** T3-2가 죽어 있던 시간대의 `unsupported` 비율이 평소보다 얼마나 높은지가 "fallback으로 버틸 만한가"의 답이다. 차이가 크면 fallback 때 `mode: none`을 더 자주 내도록 threshold를 올린다 — 틀린 추천보다 추천 없음이 나은 제품이라면.

---

## 13. 관측과 decision log

원문 없이 다음을 남긴다.

```text
question_digest, question_chars, context_chars
needs_total, needs_required, needs_grounded, needs_ambiguous, need_fields_defaulted
grounding_llm_calls
candidates_source_a, candidates_source_b, candidates_both
discoverable_candidates, stage1_candidates
evidence_search_status         ok | unavailable | incomplete
stage1_final_overlap_at_k      1단계 상위 k와 최종 상위 k의 겹침 — "topic만으로 얼마나 맞히는가"
single_sufficient, group_size, covered_required, uncovered_required
source_b_max_age_seconds
degraded[]
latency_ms.{expand, ground_search, ground_llm, retrieve, evidence_search, rank, group, assemble, total}
```

실행은 별도 journal이다(`recommendation_id`, `members_requested/answered/timed_out`, `needs_supported/unsupported`, `conflict_count`, latency).

**핵심 지표**: 추천 당시 need coverage와 실행 당시 `supported/unsupported`의 calibration error. "잘 알 것이라고 추천했는데 실제 agent가 답하지 못한 비율"을 계속 잰다. 랭커 feature 가중치는 이 지표로 고친다.

알람 후보: `evidence_search_status != ok` 비율, `source_b_stale` 비율, 폴링 사이클 실패, `grounding_ambiguous` 비율(타입 ①과 공유), 실행 단계 `unsupported` 비율(모드별).

---

## 14. 평가

### 14-1. 오프라인 — 합성 모집단 위에서

기존 10만 합성 모집단에 소스 B 파생본을 합성으로 더한다(owner별 QID 분포는 `visible_topic_rows`와 상관을 두되 `knowledge_kind` 분포는 따로 뽑는다). 재는 것:

- relevant owner recall@K, precision@K
- required need coverage, 요청자 자기 포함 0건, 숨은 후보 존재 유출 0건
- procedural 질문에서 procedural·experiential 근거 보유자가 선택된 비율
- entity만 일치하고 질문의 조건은 맞지 않는 false positive 비율
- group: 평균 인원, 불필요한 member 비율, 오라클 최소 group 대비 인원 차이

### 14-2. 온라인 — 실측만 답하는 것

offline 합성 데이터로는 실제 answerability를 검증할 수 없다. §13의 calibration error가 유일한 답이고, 그것은 실행 단계가 있어야 잰다. 실행 단계 없이 추천만 내보내는 기간에는 **사용자가 추천을 수락했는지**를 대리 지표로 쓴다.

---

## 15. 구현 슬라이스

**슬라이스**는 혼자서 배포되어 동작하는 증분 하나다. 각 슬라이스는 route·데이터·랭킹을 끝까지 갖춘 채로 앞 슬라이스 위에 얹히고, 뒤 슬라이스가 없어도 그 자체로 추천을 낸다. 나누는 기준은 **새로 생기는 의존성**이다 — 다른 팀의 일정에 걸리는 것이 슬라이스 경계가 되도록 잘라서, 그쪽이 늦어도 앞 슬라이스는 배포된다. 문서 앞부분의 "첫 슬라이스"는 아래 표의 1번이다.

| 슬라이스 | 새 의존성 | 새 LLM 호출 | 답하는 질문 | 완료 조건 |
|---|---|---|---|---|
| **1. 소스 A만** | 없음 | 0 (스키마 확장) | 이 주제에 깊은 관심과 지식을 드러낸 사람. **"아는 사람"과 "해 본 사람"은 구분하지 못한다** — topic row에 statement 종류가 없어 `knowledge_kind`는 추출·journal만 하고 랭킹에 쓰이지 않는다 | route·envelope, `knowledge_facet` 미러, need 다중 grounding, 결정적 랭킹, 합성 모집단 측정 |
| **2. 소스 B** | memory-api **폴링만** | 0 | 구체적 근거 statement를 가진 사람 | 커버리지 측정(§16 질문 2)이 먼저. 그 뒤 `topic_qid_map`, `knowledge_capabilities`, 일곱 번째 루프, 두 소스 합산 랭킹, `source_b_stale` |
| **3. T3-2 재점수** | memory-api **evidence route**(그쪽 신설) | 0 | 질문의 조건까지 맞는 사람 | route 계약 합의, 클라이언트, timeout·fallback, `stage1_final_overlap_at_k` journal |
| **4. group** | 없음 | 0 | 두 need를 두 사람이 나눠 덮는 경우 | set-cover, `mode: group`, 인원 2 |
| **5. 트리거** | bourbon-agent 변경 | 0 | 실제로 불리는가 | tool 설명 변경 또는 두 번째 tool, 호출 빈도 로그 |
| **6. 실행·종합** | bourbon-agent 소유 | agent당 1 + 종합 1 | 실제 답변 | 이 문서 범위 밖. `moderator/agent_recommender/` |

슬라이스 1·2는 memory-api route 없이 동작하는 형태라 그쪽 일정과 무관하게 배포할 수 있다. 슬라이스 3이 들어가는 날부터 fallback이 곧 그 전날까지의 동작이다 — 새 경로가 아니다.

슬라이스 1은 타입 ① 위에 "need 여러 개 + knowledge 가중 랭커"를 얹는 것이라 새 도메인이 거의 없다. 슬라이스 5는 1과 동시에 시작할 수 있다 — discovery 쪽이 준비되기 전에는 지금 `recommend_agents`가 하는 일과 같으니 사용자에게 보이는 변화가 없다.

---

## 16. 확인할 것과 요청할 것

다른 팀에 물어야 하는 것이다. 답이 오기 전에는 위 설계를 그대로 두고 슬라이스 1을 진행할 수 있다.

**memory-api**
1. `bourbon-v2` tenant에 personal build가 실제로 돌고 있는지, 몇 owner인지, 주기는 어떻게 되는지. 소스 B의 가치가 이 숫자에 달려 있다.
2. 그 빌드 결과에서 **`knowledge_qid`·`broader_qids`의 상위 분포**를 받아 볼 수 있는지(QID와 개수만, owner·label 없이). 우리 카탈로그 QID와 `topic_qid_map`(§7-4)의 교집합이 얼마인지가 소스 B 커버리지의 첫 측정이다. 이것을 모르면 소스 B를 만들어도 얼마나 잡히는지 말할 수 없다.
3. label·blurb 없이 `(qid, match, statement kind별 count, has_provenance, last_seen)`만 주는 owner-scoped 집계 route를 추가해 주실 수 있는지. 없어도 `GET /users/{id}/personal/entities`로 읽고 버리면 되지만, 있으면 private 텍스트가 우리 프로세스에 들어오지 않는다.
4. **evidence route**(§6 T3-2) — `POST /{tenant}/personal/evidence/search`. 조건은 셋이다. (가) `owners` 허용 목록이 필수이고 그 밖의 owner는 어떤 형태로도 응답에 없다. (나) 응답에 statement 텍스트·entity label·message id가 없고 점수·개수·날짜만 있다. (다) 그쪽에서 OpenSearch 재시도를 중첩하지 않는다(우리가 사다리를 갖는다). 요청자의 질문 텍스트가 그쪽으로 가므로, 이 route와 함께 내부 호출 인증이 들어가야 한다. 1차 초안이 Phase B로 제안했던 것의 축소판이다.
5. `GET /{tenant}/admin/personal/build`를 폴링 피드로 써도 되는지, 페이지 크기와 부하 상한. 그리고 `POST /knowledge/expand`를 카탈로그 갱신 때마다 100회 안쪽으로 호출해도 되는지.

**topic-api**
6. `GET /users/{id}/topics`(우리가 재조회하는 route)의 응답에 `score_detail.facets`·`confidence`가 포함되는지. 없으면 포함을 요청한다.
7. 소스 B 커버리지 측정에서 시설↔제품처럼 Wikidata 관계로 못 건너는 구멍이 크게 나오면, 카탈로그 편집으로 메울 수 있는지(예: "위스키 증류소"를 위스키의 자식 topic으로). 편집 정책에 맞는지는 그쪽 판단이다.

**bourbon-api**
8. agent 설정에 `consultable`(다른 사용자의 질문에 내 agent가 대신 답해도 되는가) opt-in 필드를 둘 수 있는지, 그리고 그 변경을 이벤트로 낼 수 있는지. `personal_agent_visibility_changed`가 만들어지지 않았던 것과 같은 이유로 이벤트 대신 재조회가 될 수도 있다.

**bourbon-agent**
9. `recommend_agents`의 트리거를 넓히는 것과 두 번째 tool을 두는 것 중 어느 쪽이 프롬프트 설계상 맞는지. `moderator/agent_recommender/`의 계획이 이 기능과 같은 것인지.

---

## 17. 열린 항목

1. `consultable`이 생기기 전 `discoverable`로 대체하는 기간을 둘 것인가, 아니면 필드가 생길 때까지 기다릴 것인가.
2. 요청자가 추천을 수락한 뒤에만 실행할지, 자동 실행할지(1차 초안 3번, 그대로).
3. required need 하나가 비었을 때 partial answer를 허용할지(1차 초안 5번, 그대로).
4. group 인원을 2에서 3으로 올릴 조건.
5. calibrated confidence를 외부 필드로 열 시점과 조건.
6. 소스 B의 `stale` threshold — memory-api 빌드 주기가 정해진 뒤 레지스터 행으로.
7. 실행 단계의 feedback event(추천 id ↔ `supported/unsupported`) 이름과 payload. calibration error를 재려면 이것이 먼저 있어야 한다.
8. 슬라이스 1을 타입 ① 도메인 위에 얹는 것을 슬라이스 2에서 새 소스로 나누는 시점의 기준.
9. `topic_qid_map`에 `typed` 관계를 넣을지, `narrower`만으로 시작할지 — 커버리지 측정 결과로 정한다.
10. 소스 B 커버리지가 낮을 때 조인 키를 memory-api의 `classes` 인덱스(그쪽이 theme으로 판정한 클래스)로 바꾸는 대안을 열어 둘지. tenant별로 동적이라 매핑 테이블이 어차피 필요하고, 첫 슬라이스에서는 `expand` 쪽이 단순하다고 본다.
11. evidence route에 `owners` 없이 tenant 전체를 치는 모드를 열 것인가. T3-1의 사각을 피할 수 있지만, 비동의 owner의 count가 우리에게 오는 문제를 memory-api 쪽 `consultable` 필터로 풀 수 있게 된 뒤에만 가능하다. 커버리지 측정 결과를 보고 정한다.
12. 1단계 후보 상한 N의 초기값(50)과, fallback 모드에서 `mode: none`을 내는 threshold를 평소보다 올릴지.
