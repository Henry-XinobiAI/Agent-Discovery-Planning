# Personal knowledge 기반 답변 가능 agent 추천

> 상태: **설계 초안, 결정 아님**
> 범위: `bourbon-agent` · `bourbon-agent-discovery-api` · `bourbon-memory-api-v2` · `bourbon-topic-api` 사이의 새 추천 타입(타입 ④ 후보)
> 비범위: 타입 ①·②·③의 계약 변경, 선택된 agent들의 실제 답변 실행과 종합(이 문서는 경계만 정한다)
> 개정 이력: 1차 초안 2026-09-18 → 2차 2026-09-21 세 서비스의 코드를 읽고 전면 재작성 → 2차 보정 2026-09-21 외부 리뷰 반영(동의 경계, export route 선행, bounded map, coverage 상태, 슬라이스 순서)
> 이 문서의 "현재"는 각 repo의 HEAD 기준이다 — bourbon-agent `80d81bf`(09-10), memory-api-v2 `6c0ae52`(09-15), topic-api `ae09a28`(09-19), agent-discovery-api `339a99f`(09-21)

---

## 0. 요약

사용자의 personal agent가 자기 지식으로 답할 수 없는 질문을 받았을 때, **그 질문에 답할 근거를 가진 다른 사용자의 personal agent**를 추천한다. 질문이 여러 knowledge need로 나뉘고 한 사람이 전부 덮지 못하면 서로 보완하는 두 명을 group으로 추천한다.

설계는 다섯 문장이다.

1. **"유저 X가 질문 Q에 답할 수 있는가"를 (X, Q) 쌍마다 판단하지 않는다.** owner별·QID별 capability 집계를 오프라인에 두고, 온라인에서는 질문을 topic/QID로 grounding한 뒤 그 집계를 조회해 결정적으로 랭킹한다. 유저 수가 늘어도 온라인 비용은 후보 수에만 비례한다(§1).
2. **discovery 경로의 LLM 호출은 타입 ①이 이미 내는 그 호출이다.** need 분해는 expansion 스키마의 필드 둘이고, answerability judge는 없다. 보통 1회, 모호할 때 2회(§6 T1·T2).
3. **근거 소스는 둘이고 같은 QID key space에서 만난다.** 소스 A는 topic-api 파생(관심·지식 신호, `prior`), 소스 B는 memory-api 파생(근거 statement의 개수·종류·날짜, 텍스트 없음). 두 소스는 개체 층과 주제 층이 달라 `topic_qid_map`으로 조인한다(§6 T2·T3, §7).
4. **후보 조회는 두 단계다.** 1단계는 우리 DB로 수십 명까지 좁히고, 2단계는 그 후보만 memory-api에 넘겨 질문 텍스트로 재점수한다. 2단계가 답하지 않으면 1단계 순위를 그대로 응답한다 — fallback은 별도 경로가 아니라 매 요청 항상 도는 1단계다(§6 T3).
5. **동의 요건이 소스마다 다르다.** 소스 A는 owner가 이미 공개한 관심사라 `discoverable`로 가고, 소스 B는 개수만 있어도 개인 데이터라 `consultable` opt-in 뒤에만 production에 적재한다(§10).

추천 시점의 런타임 의존성은 topic-api 검색(지금 타입 ①과 같음)과 memory-api evidence route 1회다. 후자가 없어도 추천은 나간다. 1차 초안과 무엇이 달라졌는지는 §3-5에 표로 모았다.

---

## 1. 문제의 재정의

핵심 질문은 "수많은 유저 중 누가 이 질문에 답할 수 있는가"다. 이것을 유저마다 LLM에게 물으면 비용과 지연 시간이 유저 수에 비례하므로 애초에 설계에 넣을 수 없다. 대신 셋으로 나눈다.

```text
오프라인  owner × QID capability 집계          memory-api 빌드가 이미 만든다 / topic-api sync가 이미 만든다
온라인    질문 → QID 몇 개 → 집계 조회 → 랭킹     LLM 1회(타입 ①과 같은 호출), SQL, evidence route 1회, 산술
실행 시   선택된 1~2명이 자기 recall로 답한다      agent가 매 턴 이미 하는 일, discovery 비용 아님
```

"진짜 답할 수 있는지"는 온라인에서 확정하지 않는다. 추천은 **근거를 가졌을 가능성**의 순위이고, 확정은 선택된 agent가 실행 시점에 자기 memory를 검색해서 한다. 그래서 이 기능의 핵심 품질 지표는 "추천 당시 coverage와 실행 당시 실제 answerability 사이의 calibration error"이고(§13), 랭커는 그 지표로 고친다.

이 구조는 타입 ①과 같다. 타입 ①이 10만 합성 유저에서 후보 조회를 한 자릿수 ms로 끝낸 이유가 그대로 적용된다 — 온라인 비용은 유저 수가 아니라 grounding된 topic의 보유자 수에 비례한다.

---

## 2. 제품 시나리오

### 2-1. 단일 agent

> 홈 에스프레소 머신에서 압력이 너무 높을 때 추출을 어떻게 조정해야 해?

요청자의 agent가 자기 recall에서 근거를 찾지 못한다. discovery는 질문을 need 하나(espresso 추출 조정, procedural)로 읽고, 그 topic/QID 아래에 procedural·experiential 근거를 가진 소유자를 찾는다.

> 이 질문은 제가 가진 근거로 답하기 어렵습니다. 에스프레소 추출 조정에 관한 근거가 있는 agent를 연결할 수 있습니다.

추천 이유는 공개 가능한 것에만 근거하고, 근거의 확실성에 따라 문구가 달라진다(§6 T6). 타인의 statement·메시지 내용은 이유에 들어가지 않는다.

### 2-2. agent group

> 도쿄에서 아이와 갈 만한 위스키 증류소 여행을 어떻게 계획할까?

need는 셋으로 나뉜다 — ① 도쿄 근교 위스키 증류소(declarative), ② 어린이 입장 조건·가족 방문 경험(experiential), ③ 도쿄에서 증류소까지 이동(procedural). 한 사람이 셋을 다 덮으면 단일 추천이 group보다 우선한다. 아니면 A(①②)와 B(③)처럼 **required need 전체를 최소 인원으로 덮는** 조합을 고른다. group은 상위 N명 목록이 아니라 제한된 set-cover다.

### 2-3. 추천하지 않는 경우

- required need 중 하나를 아무도 덮지 못한다
- grounding이 실패했거나 모호하게 끝났다
- 동의한 후보가 없다
- 근거 소스 조회가 일부 실패해 완전한 추천이라고 말할 수 없다

응답은 **지식 부족과 서비스 상태를 구분**한다 — 앞의 셋은 `mode: none`·`empty: true`이고, 마지막은 답을 내되 `degraded[]`에 남긴다. 이름은 §8에 있다. 숨은 후보의 존재를 응답에서 유출하지 않는 규칙은 기존 불변식 5와 같다.

---

## 3. 세 서비스의 현재

이 절은 코드에서 읽은 사실만 적는다. 설계는 §1·§4~§7이고, 여기는 그 설계가 기대는 근거다. 1차 초안이 전제로 두었던 것과 어긋나는 부분은 §3-5에 모았다.

### 3-1. bourbon-agent — recall은 tool이고, gate는 없다

- **memory recall은 prefetch가 아니라 LLM이 고르는 tool**이다. `search_conversations` tool이 BM25 키워드 쿼리 1~5개를 모델이 직접 써서 `POST /{tenant}/search`로 **원문 대화**를 검색한다. personal knowledge의 `POST /{tenant}/users/{user_id}/personal/context`는 어디서도 호출하지 않는다. scope(clearance·참가자 그룹)는 서버가 정하고 모델이 고르지 않는다.
- **answerability gate가 없다.** 빈 recall 검사도, 확신도도, "모르겠다" 분기도 없다. 프롬프트가 "추측하거나 모른다고 하지 말고 tool을 써라"고 유도하는 것이 전부다.
- **`recommend_agents` tool이 이미 있다.** 모델이 짧은 topic 하나와 context를 뽑아 `POST /api/internal/svc/agent-discovery/recommend`를 부른다(예산 10초, `max_results=1` 고정). 결과는 모델에 돌려주고, 부수 효과로 `agent_profiles_v1` 카드를 방에 게시한다. 트리거는 **"소유자나 방의 누군가가 추천을 요청할 때"** 로 한정돼 있다.
- **agent가 agent에게 묻고 답을 합치는 코드는 없다.** 발화자는 moderator가 정하고(DM은 규칙, 그 외 방은 moderator LLM), agent들은 각자 독립 task로 답하며 서로의 답은 다음 턴의 transcript로만 본다. `moderator/agent_recommender/`가 "계획됨"으로 적혀 있고 비어 있다.
- 예산: 턴 120초, 보이는 스트림 60초 상한(bourbon-api 쪽), memory 읽기 15초, discovery 10초, tool loop 최대 5회.
- memory 적재는 이 repo가 `message_created`를 받아 메시지를 재조회해 memory-api에 upsert한다. **LLM 단계 없음.** 유일한 LLM 추출은 `persona_extractor`이고 그 결과는 memory-api가 아니라 DynamoDB의 persona 문서로 간다.

### 3-2. memory-api-v2 — 읽기는 LLM 없이, 빌드는 LLM으로

- 저장소는 **OpenSearch만**. tenant당 인덱스 다섯(`entities`·`statements`·`links`·`build`·`classes`), owner 구분은 인덱스 경계가 아니라 `owner_id` 필터다.
- **personal knowledge 빌드는 LLM을 여섯 단계에서 부른다**(extract·grounding scoring·judge·dedup·competence·classes). 배치이고 `BackgroundTasks`로 돈다. **읽기 경로는 LLM 0회**, BM25와 필터만 쓴다. embedding·kNN은 없다. "LLM을 안 쓴다"는 읽기에 대해 맞고, 빌드에 대해서는 틀리다 — 다만 빌드 비용은 owner당 한 번 내는 것이고 질문마다 내지 않는다.
- **QID가 붙는 층은 개체다.** `knowledge_qid`는 "야마자키 증류소 Q1146917"처럼 구체적인 것이고, `broader_qids`는 `[*instance_of(P31), *occupations(P106), *class_ancestors(YAGO 클래스 폐포)]`다(`positioning.py:38-58`). 개체 자신의 P279 체인이나 제품·재료 관계는 들어가지 않는다 — 야마자키 증류소는 "위스키 증류소 → 증류소 → 공장 → …"으로 올라가고 **"위스키 Q281"에는 닿지 않는다.** extractor가 개체에 `broader`·`related` grounding을 덧붙이면 그 QID와 그것의 조상이 함께 들어가지만, 그것은 모델의 선택이라 확률적이다. 지인(acquaintance)은 `GroundingSource.LOCAL`로 `knowledge_qid=None`, QID가 없다.
- **cross-owner route가 이미 있다.** `GET /{tenant}/personal/themes/{qid}/owners`는 QID 하나에 대해 **OpenSearch 집계 한 번**으로 owner별 `count`·`last_seen`과 샘플 entity를 준다(정렬 `count|recent|pagerank`, `limit≤100`). `GET /{tenant}/personal/grounded/{qid}/entities`는 owner_id가 붙은 entity 목록을 준다. 둘 다 entity label·`personal_blurb`·salience를 그대로 노출한다.
- entity에는 `grounding.knowledge_qid`(Wikidata), `grounding.broader_qids[]`, `salience`, `competence_score`, `hands_on_statements`, `grounding.last_seen`이 있다. statement에는 `statement_kind`(declarative·procedural·experiential·preference·intention), `epistemic`(fact·opinion), `status`(active·invalidated), `provenance_message_ids`가 있다. owner-scoped entity 목록 route에는 **kind별 statement 개수와 provenance 유무가 없고**, statements route는 `text`와 `provenance_message_ids`를 싣는다(`api/routers/personal/structs.py:117-138, 165-172`).
- **이벤트 발행 없음. 인증 없음. personal 데이터에 visibility·동의 모델 없음.** 접근 제어는 tenant 경로 세그먼트뿐이다("wire authentication in before exposing this service externally"). 변경 피드에 가장 가까운 것은 빌드 manifest의 `last_build_delta.changed_entity_ids`(truncated)이고, manifest 목록 route는 `offset`·`limit`만 받는다(`admin.py:353-368`). 계정 삭제는 manifest를 지우고 tombstone을 남기지 않는다(`manifest.py:449`).
- 공개 지식 corpus는 `wikidata-latest-all`(2026-06-21 수집)에서 만들고 `--dump-version 20260802`로 인덱싱한다. topic-api 카탈로그의 `dump_version`과 같은 날짜다. `POST /knowledge/expand`는 seed 최대 32개, 결과 최대 500개, pagination 없음, depth 2의 두 번째 hop seed는 상위 64개다(`expand.py:19-30`).
- owner당 규모 힌트: context 조립의 entity pool 상한 500, provenance entity 상한 200. 명시적 유저 수·statement 수 목표는 없다.

### 3-3. topic-api — persona에서 관심을 뽑고, QID를 들고 있다

- topic_id는 opaque 32-hex이지만 **각 항목이 `source.qid`를 갖는다.** 3,190개 중 3,164개가 Wikidata QID(중복 없음), 26개는 `N-…` 가상 축 노드다. `dump_version`은 `20260802`로 memory-api와 같다.
- **노드는 주제이고 계층은 편집 큐레이션이다.** "위스키 Q281 → 몰트 위스키·아메리칸 위스키·아일라 싱글 몰트"처럼 제품·활동·분야가 노드이고, "증류소" 같은 시설 클래스 노드는 없다. 부모 edge는 Wikidata에서 오지 않는다 — 편집 정책이 "발견에 사용한 seed나 Wikidata의 분류 경로를 그대로 사용자 계층으로 옮기지 않는다"고 명시한다(`docs/catalog-editorial-policy.md:10`). 즉 memory-api의 클래스 축과 카탈로그의 계층은 **같은 QID를 쓰는 서로 다른 두 그래프**다.
- 유저 topic은 **메시지가 아니라 bourbon-agent의 persona 문서 중 preferences 레이어**에서 LLM 두 단계로 추출된다(`persona_updated` → 신호 추출 → 카탈로그 lexical 검색으로 grounding → 마킹). persona의 `expertise` 레이어는 **의도적으로 제외**한다. 집합은 persona 텍스트의 sha256이 바뀔 때만 움직이고, 유저당 상한 300, recency 반감기 180일.
- `score`(0~100)는 **관심 강도**다. 여섯 facet(`knowledge`·`engagement`·`affinity`·`duration`·`recency` LLM 판정 + `volume` 측정)의 가중 평균에 coverage·confidence를 곱한다. **`knowledge` facet은 `score_detail.facets` 안에만 남고** 인덱스·정렬·필터 대상이 아니다. 사용자 간 비교는 설계상 가능하다(같은 범위, 같은 식, 같은 파이프라인).
- `bourbon.topics_updated`는 sync 한 번당 한 건(batch)이고 payload에 score가 없어 소비자가 재조회한다 — 우리 워커가 지금 하는 그대로다. 재조회 응답은 `score_detail`을 `item.blocks[]` 안의 `type: "score_detail"` block으로 싣는다.
- memory-api와는 독립이다. 첨부물(이미지·노트·링크)만 memory-api에서 가져오고 statement는 읽지 않는다. `ExtractedTopic.extras`가 "memory-API theme payload 예약"으로 비어 있다.

### 3-4. agent-discovery-api — 우리가 이미 가진 것

- 타입 ① 파이프라인: S1 expansion(LLM 1회, 개념 그룹 0~3개 + probe) → S2 grounding(topic-api 이름 검색 + 모호할 때 batch disambiguation 1회) → S3 retrieval(`visible_topic_rows`) → S4 merge → S5 ordering → S6 assembly. 실측 p50 1.77초 / p95 3.11초(disambiguation 켠 조건, `validation_results.md` §11-4), 그중 약 98%가 모델 호출.
- 미러: `visible_topic_rows(topic_id, tier, owner_user_id, topic_score, topic_maturity, descriptions, updated_at)`, `agents(owner_user_id, agent_id, discoverable, agent_maturity, …)`. `discoverable`은 "공개 topic이 하나 이상"에서 **우리가 파생**한다(bourbon-api는 그 이벤트를 만들지 않았다).
- topic-api wire는 `blocks`를 opaque로 통과시키고(`providers/topic_api/wire.py:30-34`, "우리가 합의하지 않은 계약"), adapter에 `_score_detail(blocks)`가 있다(`adapter.py:353`). `PublishedTopic`(`domain/published.py:45-49`)에는 그 필드가 없다.
- 세 타입이 응답 항목으로 한 모델 `RecommendedAgent`를 쓰고, `position`·`matched_topics`·`signals`가 필수다(`api/structs/discovery.py:360-365`).
- 카탈로그 복사본(`data/catalog_dist/catalog.json`, 3,190 / 3,136 edges)을 커밋해 두고 있고, `evaluation/search.py`에 topic-api 이름 검색의 검증된 in-process 복사본이 있다(2,775 probe로 원본과 대조).
- 워커는 여섯 주기 루프를 돌리고(`popularity-rebuild`·`cf-fit`·`cf-sweep`·`cf-gate`·`population-count`·`retention-sweep`), 이벤트 여섯을 받는다. `message_created`는 id만 싣는다.

### 3-5. 1차 초안의 전제와 어긋나는 것

| 1차 초안 | 코드의 현재 | 이 문서의 대응 |
|---|---|---|
| S0 요청자 agent가 자기 근거를 결정적으로 검색한다 | 그런 단계가 없다. recall은 모델의 tool 선택이다 | 트리거를 tool 결정으로 둔다(§6 T0) |
| S1 경계선에서 LLM answerability judge | 존재하지 않고, 두면 discovery 앞에 LLM 1회가 추가된다 | 두지 않는다 |
| consultable 필터는 memory-api가 강제한다 | memory-api에 동의 모델·인증이 없다 | 소스 A는 우리 `agents.discoverable`, 소스 B는 bourbon-api에 `consultable`을 요청하고 그 뒤에만 적재(§10) |
| Phase F에서 이벤트로 projection | memory-api는 이벤트를 발행하지 않는다 | 빌드 manifest 폴링 + reconciliation(§7-3) |
| topic-api 신호는 관심이라 knowledge에 못 쓴다 | `knowledge` facet이 `score_detail`에 있다 | 미러에 컬럼으로 추가해 첫 근거 소스(`prior_only`)로 쓴다(§7-1) |
| grounding은 memory 쪽 QID 어댑터 | 카탈로그가 QID를 1:1로 들고 있다. 다만 memory는 개체·클래스 축, 카탈로그는 주제·큐레이션 축이라 등식으로는 자주 빈다 | 기존 S2 grounding 한 번 + `topic_qid_map`으로 두 소스를 조회한다(§6 T2, §7-2). 커버리지는 측정 항목이다(§16) |
| memory-api에 배치 capability API를 신설한다(Phase B) | 있는 route는 전부 label·blurb·텍스트를 돌려준다 | 신설은 맞다. 다만 모양이 다르다 — tenant 전체 검색이 아니라 **우리가 넘긴 후보 목록 안에서** 질문 텍스트로 재점수하고 점수·개수만 돌려주는 route(§6 T3-2, §16). 파생본용 compact export route도 따로 필요하다(§7-3) |

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
| 동의 판정 | 소스 A는 우리 `agents.discoverable`(파생), 소스 B는 bourbon-api의 `consultable`(그쪽 소유, 우리가 미러) | 없음 |
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

### T0. 트리거 (bourbon-agent 쪽) — judge를 두지 않고 tool 결정으로 한다

bourbon-agent의 `recommend_agents` tool은 지금 "누군가 추천을 요청할 때"만 불린다. 이 조건을 **"소유자의 질문에 내 recall로 답할 근거가 없을 때"** 로 넓히거나, 같은 클라이언트를 쓰는 두 번째 tool을 둔다. 어느 쪽이든:

- 추가 LLM 호출이 없다. 모델은 이미 턴 안에서 돌고 있고 tool call은 그 턴의 일부다.
- 새 route가 memory-api에 필요하지 않다. 요청자의 근거 검색은 지금 하는 `search_conversations`다.
- 오판은 두 방향이다. 근거가 있는데 tool을 부르는 쪽은 비용이 추천 한 번이다. **근거가 없는데 사전학습 지식으로 답하고 tool을 부르지 않는 쪽이 더 위험하다** — 랭커가 아무리 좋아도 불리지 않으면 이 기능은 없는 것과 같다. bourbon-agent의 프롬프트가 "모른다고 하지 말고 tool을 써라"고 유도하지만 `recommend_agents`는 지식 tool이 아니어서 그 유도가 여기로 흐르지 않는다.

단점은 결정적이지 않다는 것이다. 그래서 첫 실험부터 **호출 recall**을 잰다(§13): 추천이 필요했던 질문 중 tool이 실제 불린 비율, recall 검색이 비었는데 tool을 부르지 않은 비율, 근거 없는 직접 답변 비율, "다른 agent 찾아 줘"라고 명시했을 때의 호출 성공률. "추천이 필요했던 질문"에는 라벨이 필요하므로, 합성 모집단에서 owner의 근거로 답할 수 없는 질문 세트를 먼저 만들어 오프라인으로 호출률을 잰다(§14). 결정적 gate가 필요해지면 그 자리는 `moderator/agent_recommender/`이고, 그때도 discovery 계약은 바뀌지 않는다.

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
- **프롬프트와 스키마는 타입 ①의 것을 고치지 않고 형제로 따로 둔다.** 출력 필드가 둘 늘어나는 것만으로도 grounding 결과가 흔들릴 수 있다 — R60에서 프롬프트 한 줄이 422 비율을 26%까지 움직였다. 타입 ①의 프롬프트는 바이트 단위로 그대로이고, 새 프롬프트는 그것을 복사해 두 필드를 더한 것으로 시작한다. 두 프롬프트가 갈라지는 것은 감수한다.
- 그룹 상한은 타입 ①의 3을 그대로 쓴다. 1차 초안의 "1~5개"보다 좁고, 첫 슬라이스에는 충분하다.
- `importance`·`knowledge_kind`가 스키마 검증에 실패하면 각각 `required`·`declarative`로 폴백하고 `degraded`에 남긴다. 그룹 자체를 버리지 않는다.
- 모델은 owner·agent를 고르지 않고, 근거 소스를 보지 않는다. 질문 원문은 타입 ①과 같이 로그·예외·Sentry에 남기지 않는다(불변식 7).

### T2. grounding — 한 번, 두 소스

기존 S2를 그대로 쓴다. probe로 topic-api 이름 검색을 하고, 규칙으로 하나를 고르며, 못 고를 때만 batch disambiguation 1회. 결과는 그룹마다 `topic_id` 하나다.

topic_id에서 QID는 우리가 커밋한 카탈로그로 읽는다(`source.qid`, 3,164/3,190). 가상 노드 26개는 QID가 없으므로 소스 B 조회를 건너뛰고 소스 A만 쓴다.

**소스 B의 조회 키는 topic의 QID 하나가 아니라 topic이 덮는 QID 집합이다.** memory-api는 개체에 QID를 붙이고 P31·YAGO 클래스 축으로 올라가므로(§3-2), "위스키 Q281"로 등식 조회를 하면 "야마자키 증류소"만 말한 사람은 나오지 않는다 — 그 개체의 `broader_qids`는 증류소·공장 쪽으로 올라가고 위스키에 닿지 않는다. 그래서 오프라인에 `topic_qid_map(topic_id, qid, via, distance)`를 두고(§7-2) 조회는 `qid IN (SELECT qid FROM topic_qid_map WHERE topic_id = …)`로 한다.

그래도 **grounding은 한 번**이다. 결과 topic_id 하나가 소스 A에는 그대로, 소스 B에는 매핑을 거쳐 조회 키가 된다. 1차 초안의 "S3 공개 지식 grounding + S4 memory 검색"이 여기서 한 단계로 합쳐지는 것은 같다.

이 매핑이 잡지 못하는 것이 있다. "위스키 증류소 → 위스키" 같은 **시설↔제품** 관계는 P279·P31에도 memory-api의 typed_links 화이트리스트(author·director·manufacturer·genre 계열)에도 없다. 그래서 소스 B는 주제를 개체로 직접 언급한 사람("위스키 좋아해")은 잡고, 구체적 개체만 말한 사람("야마자키·하쿠슈 다녀왔어")은 extractor가 related grounding을 붙였을 때만 잡는다. 이 사각의 크기는 설계로 정할 수 없고 실제 빌드 결과로 재야 한다(§16 memory-api 질문 2).

### T3. 근거 조회 — 두 단계

후보를 **좁히는 일**과 **고르는 일**을 나눈다. 좁히는 것은 우리 DB가 하고(T3-1), 고르는 것은 memory-api가 질문 텍스트로 한다(T3-2). T3-2가 답하지 않으면 T3-1의 순위가 그대로 답이다.

```text
T3-1  우리 PostgreSQL   topic + 근거 종류·양     10만 명 → 수십 명     "무엇에 대해"
T3-2  memory-api       질문 텍스트 BM25         수십 명 재점수        "정확히 어떤 조건"
```

grounding에서 질문의 조건("압력이 너무 높을 때")은 topic으로 압축되며 사라진다. T3-1만으로는 에스프레소에 procedural 근거 8건을 가진 사람이 그 8건 모두 로스팅 이야기인지 구분하지 못한다. T3-2가 그 조건을 되찾는다. 두 단계는 다른 축(topic ↔ 텍스트)을 보므로 겹치지 않고 보완한다.

두 단계가 need마다 owner의 **coverage 상태**를 한 단계씩 올린다. 이 상태가 랭킹 가중·응답 문구·fallback 강도를 한 번에 정하고, 뒤의 T4·T6·§8·§12·§13이 전부 이것을 읽는다.

```text
prior_only              소스 A만 있음 — 관심·지식 신호는 있으나 근거 statement는 확인 안 됨      T3-1이 매김
evidence_coarse         소스 B 행 있음 — 이 topic 아래 근거 statement가 있음, 질문의 조건은 미확인  T3-1이 매김
evidence_text_matched   T3-2에서 질문 텍스트와 matched ≥ 1                                    T3-2가 올림
```

T3-2가 없거나 답하지 않으면 상태는 `evidence_coarse`까지다.

#### T3-1. 후보 좁히기 — 두 소스, 우리 DB

두 소스 모두 우리 PostgreSQL에 있고 조회는 SQL이다. 각 소스가 무엇을 답하는지가 다르다.

**소스 A — topic-api 파생. "이 주제에 깊은 관심을 드러낸 사람".**
`visible_topic_rows`에 컬럼 둘을 더한다: `knowledge_facet`(`score_detail.facets.knowledge`, 0~100)과 `confidence`. `topics_updated`를 받으면 이미 재조회하므로 적재 경로는 바뀌지 않는다. 서브트리 롤업은 `catalog_edges`로 지금과 같이 한다.

**소스 B — memory-api 파생. "이 주제에 대해 구체적 근거 statement를 가진 사람".**
새 테이블 `knowledge_capabilities`, key는 `(owner_user_id, qid)` 하나이되, **identity와 broader를 같은 행의 다른 컬럼**으로 둔다. 같은 owner가 한 entity에서는 어떤 QID를 identity로, 다른 entity에서는 broader로 가질 수 있어서(`positioning.py:83` — identity는 자기 조상만, non-identity는 자기 qid도 넣는다) `match` 한 칸으로는 표현이 안 된다.

```text
owner_user_id                uuid
qid                          text        Wikidata QID
identity_entities            int         이 QID가 knowledge_qid인 entity 수
broader_entities             int         이 QID가 broader_qids에 든 entity 수
active_statements            int         위 entity들의 active statement 수 (entity 중복 없이)
procedural_statements        int
experiential_statements      int
hands_on_statements          int
has_provenance               bool
last_seen_at                 timestamptz
observed_build_at            timestamptz memory-api manifest의 built_at
last_seen_in_source_at       timestamptz 우리 폴링이 이 owner를 마지막으로 본 시각 (§7-3 제거 정책)
```

**들어가지 않는 것**: statement 텍스트, entity label, `personal_blurb`, message id, salience 원시값, **그리고 `competence_score`와 그 파생값**. competence를 owner 내부에서 정규화해도 사용자 간 비교가 되지 않는다 — 아는 것이 거의 없는 사람의 최고 entity도 percentile 1.0이다. 실행 단계의 `supported/unsupported`가 쌓인 뒤 cross-owner calibration이 되면 그때 다시 본다. 이 테이블은 "몇 개, 언제"만 안다. 크기는 owner당 entity 수(수백)로, `visible_topic_rows`의 유저당 상한 300과 같은 자릿수다.

**topic 단위로 합칠 때 `SUM`을 쓰지 않는다.** entity 하나의 `broader_qids` 여러 개가 같은 topic의 `topic_qid_map`에 함께 들어가면 그 entity가 여러 번 세어져 topic의 근거량이 부푼다. 첫 버전은 중복에 강한 집계만 쓴다 — QID 행들 사이의 `MAX(active_statements)`, `MAX(last_seen_at)`, `bool_or(has_provenance)`, 그리고 export route가 topic 단위 distinct entity 수를 줄 수 있으면 그것(§16 memory-api 질문 3). `SUM`은 상한을 둔 capped sum으로만.

조회는 소스 A가 `topic_id`(+ `catalog_edges` 서브트리), 소스 B가 `qid IN (topic_qid_map의 그 topic 행)`이고, `JOIN agents … WHERE consultable`(소스 A만 있는 슬라이스에서는 `discoverable`)과 요청자 제외를 여기서 적용한다. 두 소스를 owner로 합쳐 need별 coverage matrix를 만들고, 1단계 점수로 정렬해 **상위 N명**(레지스터, 초기 50)을 남긴다. 둘 다 인덱스 한 번 타는 SQL이다.

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
- `owners`가 우리 `consultable`을 이미 통과한 집합이라, 비동의 owner에 관한 데이터는 어떤 형태로도 우리 프로세스에 오지 않는다(§10). memory-api에 동의 모델이 없어도 이 경계는 우리 쪽에서 닫힌다.
- 검색 범위가 N명이라 OpenSearch 비용도 tenant 전체 집계가 아니다.
- timeout은 레지스터 행(`evidence_search.timeout_ms`)으로 두고 초기값은 실측 뒤 정한다. 재시도 사다리는 우리 쪽 하나만 갖는다(§12).
- **`max_score`는 sufficiency가 아니다.** BM25 점수는 같은 need·같은 응답 안에서의 정렬에만 쓸 수 있다 — need 사이에서 비교되지 않고, 언어와 statement 길이에 흔들리며, "검색어와 비슷하다"는 뜻이지 "답할 만큼 충분하다"는 뜻이 아니다. 그래서 랭커는 점수가 아니라 **need별 rank**(또는 need 안에서 정규화한 값)를 feature로 받고, `matched ≥ 1`이 `evidence_text_matched`의 조건이다. `matched = 0`인 owner는 소스 A가 아무리 높아도 그 need에서 `prior_only`(소스 B 행이 있으면 `evidence_coarse`)로 남는다. sufficiency threshold는 평가(§14)로 정한다.

T3-2의 rank가 T3-1의 순위를 다시 매긴다. 에스프레소 근거가 많아 1단계 상위였지만 압력 이야기가 없는 사람은 내려가고, 압력 조정을 3건 말한 사람은 올라간다.

#### fallback — T3-2가 답하지 않을 때

memory-api가 죽었거나 timeout 안에 답이 없으면 **`stage1_ranking`을 그대로 응답**하고 `degraded: ["evidence_search_unavailable"]`을 붙인다. 새로 계산하는 것이 없다 — 장애 때만 도는 별도 코드 경로가 아니라, 매 요청 항상 돌던 1단계의 결과다. `truncated: true`면 받은 것으로 순위를 매기고 `evidence_search_incomplete`를 붙인다.

#### 부수 효과 — 매 요청이 실측

정상 요청에서는 두 순위가 다 있다. `stage1_ranking` 상위 k와 최종 순위 상위 k의 겹침을 journal에 남기면(§13) **"topic만으로 얼마나 맞히는가"** 를 운영 중에 계속 잰다. 겹침이 높으면 fallback 때 품질 손실이 작고, 낮으면 fallback 때 `mode: none`을 더 쉽게 내도록 threshold를 올리는 근거가 된다.

#### 한계

T3-1이 찍지 못한 사람은 T3-2도 보지 못한다. `topic_qid_map`의 사각(§7-2)이 그대로 recall 상한이다. 사각이 크게 측정되면 `owners` 없이 tenant 전체를 치는 모드를 여는지 다시 논의하되, 그것은 memory-api 쪽에서 동의를 걸러 줄 수 있게 된 뒤의 이야기다(열린 항목 §17-10).

### T4. 단일 agent 랭킹 — 결정적

feature 후보(타입 ①의 랭커 feature 표와 같은 방식으로 레지스터에 올린다):

- required need coverage(gate) — need마다 coverage 상태가 threshold 이상인가. **`prior_only`만으로 required need를 covered로 볼지는 레지스터 행**으로 두고(초기값은 "본다", 단 문구와 강도가 낮다), 열린 항목으로 남긴다(§17-12)
- coverage 상태별 가중: `evidence_text_matched` > `evidence_coarse` > `prior_only`
- 소스 A: `knowledge_facet`, `confidence`, tier
- 소스 B: `log(1 + active_statements)`, need의 `knowledge_kind`와 일치하는 statement 수, `has_provenance`, `last_seen_at`의 신선도, `identity_entities > 0`인지(identity가 broader보다 강하다)
- T3-2: need별 rank
- 두 소스가 같은 owner를 가리키는지(교차 확인)
- `agent_maturity`(이미 있음)

```text
single_score = required_coverage_gate × Σ_need( state_weight × kind_match × log_evidence × freshness × provenance × text_rank ) × source_agreement
```

**쓰지 않는 것**: `competence_score`·`salience`와 그 파생값. owner 내부 척도라 다른 owner와 비교되지 않고, owner 내부 정규화도 그것을 바꾸지 못한다(T3-1). 위 feature는 전부 사용자 간 같은 뜻을 갖는 것만 골랐다 — 개수의 log, 종류 일치, 출처 유무, 날짜, identity/broader, 그리고 같은 need 안의 rank. 한 agent가 모든 required need를 threshold 이상으로 덮으면 단일 추천이 group보다 우선한다.

### T5. group planning — 결정적

단일이 부족할 때만 돈다. 후보 pool을 랭킹 상위 일정 수로 제한한 뒤 bounded combination search.

- 첫 슬라이스 **최대 2명**
- 모든 required need가 threshold 이상
- 각 member는 다른 member가 못 덮는 need를 최소 하나 덮어야 한다
- 같은 need만 중복하는 member는 제외

need 최대 3, 후보 수십, 인원 2면 탐색은 조합 수백 개다. LLM을 쓰면 재현성과 decision log 설명력이 떨어진다.

### T6. 응답 조립

이유는 템플릿이고, **coverage 상태가 문구를 정한다.** 소스 A만 매칭된 owner에게 "근거가 있습니다"라고 쓰면 과장이다 — topic-api의 `knowledge` facet은 persona의 preferences 레이어에서 뽑은 관심 topic의 한 면이고, `expertise` 레이어는 빠져 있다.

```text
prior_only              "일본 위스키에 관심과 지식 신호가 있습니다."
evidence_coarse         "일본 위스키·증류소에 관한 근거가 있습니다."
evidence_text_matched   "증류소 어린이 방문에 관한 근거가 있습니다."   ← need의 label을 쓴다
group 보완 문구          "도쿄 가족 여행 쪽을 보완할 수 있습니다."
```

LLM 문장 생성은 품질상 필수가 아니고, 타인의 근거를 모델에 보낼 유인이 생기므로 첫 슬라이스에 넣지 않는다.

---

## 7. 근거 파생본의 적재

소스 A(§7-1)는 지금 이벤트 그대로다. 소스 B는 셋으로 이뤄진다 — 조인 키인 `topic_qid_map`(§7-2), 폴링 파생본 `knowledge_capabilities`(§7-3), 그리고 비어 있을 때의 동작(§7-4).

### 7-1. 소스 A — 지금 이벤트 그대로

`topics_updated` → 재조회 → `visible_topic_rows` 교체. 바뀌는 것은 재조회 응답에서 `score_detail.facets.knowledge`·`confidence`를 읽어 컬럼에 넣는 것뿐이다.

응답에는 이미 들어 있다. topic-api는 `score_detail`을 `item.blocks[]` 안의 `type: "score_detail"` block으로 보내고, 우리 wire는 blocks를 opaque로 통과시키며(`providers/topic_api/wire.py:30-34`), adapter에 `_score_detail(blocks)`가 있다(`adapter.py:353`). 빠진 것은 우리 쪽이다 — `PublishedTopic`(`domain/published.py:45-49`)에 필드가 없고, `_published()`가 block을 읽지 않고, storage 스키마에 컬럼이 없다. wire 주석이 "우리가 합의하지 않은 계약"이라 적어 둔 대로, topic-api에 물을 것은 "포함되는가"가 아니라 **"이 block의 facet 이름을 소비자 계약으로 삼아도 되는가"** 다(§16). upstream fixture로 필드를 고정하는 것이 우리 완료 조건에 들어간다.

### 7-2. `topic_qid_map` — 카탈로그 topic이 덮는 QID 집합

카탈로그가 바뀔 때만 다시 만드는 오프라인 파생본이다. 카탈로그 복사본처럼 커밋해 두고 `load_catalog`와 같은 방식으로 적재한다. **완전한 map이 아니라 bounded map이다** — 어디까지 봤고 어디서 잘렸는지를 스스로 말한다.

```text
헤더    catalog_version, knowledge_dump_version(20260802), expand 파라미터(kinds, depth, limit, max_generality), 생성 시각
행      topic_id    카탈로그 topic
        qid         이 topic의 근거로 인정할 Wikidata QID
        via         seed | narrower | typed
        distance    0 (seed) | 1 | 2
topic별 truncated   그 topic의 expand 결과가 상한에 잘렸는가
```

재료는 memory-api의 공개 지식 route다. `POST /knowledge/expand`는 seed QID를 받아 `narrower`(역 P31·P279), `typed`(화이트리스트 관계), `co_link`를 depth 2까지 돌려주는 배치 traversal이고 hop당 round trip이 고정이다. `max_generality`로 지나치게 넓은 클래스를 잘라 낸다.

**넣는 것**:

- `seed`: topic의 QID 자체. identity 매치.
- `narrower`: 그 topic의 하위 클래스와 인스턴스. "몰트 위스키"의 narrower에 "야마자키 12년"이 있다면 그것을 개체로 가진 사람이 잡힌다.
- `typed`: 화이트리스트 관계로 이어진 것. 저작·제작 계열이라 취미·기술 topic에서는 기여가 작을 것으로 본다. 측정 뒤 뺄 수 있다(§17-8).

**넣지 않는 것**: memory-api의 `broader` 확장(위로 올라가면 "음료·식품"까지 번져 topic 경계가 사라진다), `co_link`(링크 그래프 동시 출현은 근거가 아니다).

**그러나 한 요청으로 완전한 결과를 받을 수 없다.** 계약이 seed 최대 32개, 결과 최대 500개, pagination 없음, depth 2의 두 번째 hop seed는 상위 64개다(§3-2). 넓은 topic 32개를 한 요청에 넣으면 500을 나눠 쓰고 어느 topic의 narrower가 잘렸는지는 `total > len(items)`로만 안다 — 뒤 페이지를 가져올 길이 없다. 그래서:

- 넓은 topic(카탈로그 상위 계층, 자식이 많은 것)은 **seed 하나씩** 요청한다. 좁은 topic만 묶는다.
- 그래도 잘린 topic은 `truncated = true`로 표시하고, **그 topic에서는 소스 B를 쓰지 않는다**(소스 A만, `prior_only`). 잘린 map으로 재면 그 topic의 근거량이 실제보다 작게 나와, 어느 owner가 불리해지는지를 우리가 통제하지 못한다.
- 잘린 topic이 많으면 `expand` 대신 공개 지식 인덱스나 원본 dump에서 오프라인으로 직접 만든다. 그건 memory-api 쪽에 인덱스 읽기 권한이나 dump 접근을 요청하는 일이다(§17-14).

**소스 B 구현 전 spike 하나**: 카탈로그 3,164 QID를 위 규칙으로 돌려 topic별 결과 수와 truncated 비율을 재고, 그 결과를 이 문서에 표로 적는다. 그 숫자가 나오기 전에 §15 슬라이스 2를 시작하지 않는다.

한 QID가 여러 topic에 속할 수 있다(몰트 위스키 ⊂ 위스키). 그 경우 두 topic 행에 모두 넣고, 랭킹은 grounding된 topic 쪽 행만 읽으므로 topic 사이의 이중 계산은 없다. **topic 안의 이중 계산**은 다른 문제다 — entity 하나의 `broader_qids` 여러 개가 같은 topic의 map에 들어가면 그 entity가 여러 행에 나타난다. 그래서 T3-1이 `SUM`을 쓰지 않는다.

**이 테이블의 커버리지가 소스 B의 상한이다.** 실제 memory 빌드의 `broader_qids`·`knowledge_qid` 분포와 `topic_qid_map`의 교집합이 얼마인지가 첫 측정이고, 그 숫자가 낮으면 시설↔제품 같은 빠진 관계를 카탈로그 쪽 편집(예: "위스키 증류소"를 위스키의 자식 topic으로)으로 메울지, 매핑에 수동 행을 둘지 정한다.

### 7-3. 소스 B — 폴링 파생본

memory-api는 이벤트를 내지 않으므로 우리 워커의 **일곱 번째 주기 루프**가 pull한다.

**지금 있는 route로는 만들 수 없다.** `GET /{tenant}/users/{id}/personal/entities`의 항목에는 `salience_statements`·`salience_opinions`·`hands_on_statements`·`competence_score`·`grounding{knowledge_qid, broader_qids, last_seen}`은 있지만 **procedural·experiential 개수와 provenance 유무가 없다.** 그것을 얻으려면 entity마다 `/entities/{id}/statements`를 불러야 하는데, 그건 N+1이면서 응답이 `text`와 `provenance_message_ids`를 싣는다(§3-2) — 원문이 우리 프로세스에 들어온다. 그래서 **memory-api의 compact export route가 소스 B의 선행 의존성**이다(§16 memory-api 질문 3). 축소판(QID·hands_on·last_seen만)으로 시작하는 길도 있지만 `knowledge_kind` 구분이 사라져 소스 B의 존재 이유가 절반 없어진다.

route가 있다고 할 때 한 사이클:

1. `GET /{tenant}/admin/personal/build`로 manifest를 훑어 `built_at`(또는 `rescored_at`)이 우리 `observed_build_at`보다 새로운 owner를 고른다. **`consultable`인 owner만** 다음 단계로 간다(§10-2).
2. 그 owner에 대해 export route로 `(qid, identity/broader entity 수, kind별 statement 수, has_provenance, last_seen)`을 받아 소스 B 행을 **교체**한다(타입 ①의 `CatalogRepository.replace`처럼 트랜잭션 하나). `last_seen_in_source_at`을 갱신한다.
3. 사이클 끝에 **full reconciliation**: manifest에서 보이지 않은 owner의 `last_seen_in_source_at`이 K 사이클 이전이면 행을 지운다. 계정 삭제는 manifest를 지우고 tombstone을 남기지 않으므로(§3-2), 이것이 삭제를 따라가는 유일한 길이다. `consultable`을 끈 owner도 같은 경로로 빠진다.

**manifest 훑기 자체가 문제다.** `list_builds`는 `offset`·`limit`만 받는다 — `updated_since`도 cursor도 없다. owner가 10만이면 사이클마다 전체를 넘기고, 넘기는 중 새 빌드가 끼면 offset 이동으로 중복·누락이 생긴다. `last_build_delta`는 truncated라 증분 피드로 못 쓴다. 필요한 것은 `(built_at, owner_id)` 기반 안정 cursor 또는 `updated_since`이고, 이건 memory-api 변경이다(§16 memory-api 질문 5). 그 전까지는 사이클당 owner 상한과 backlog(안 본 owner 수)를 로그로 내고, 상한에 자주 닿으면 주기를 늘리는 것이 아니라 cursor를 기다린다.

주기는 memory-api 빌드 주기에 맞춘다. 빌드 자체가 배치라 폴링이 잃는 신선도는 없다.

**루프 하나가 커넥션 하나다.** 워커 풀의 하한은 `WORKER_CONCURRENCY` + 상시 루프 수이고, 지금 10 + 6 = 16에 dev·base가 정확히 8 + 8이다. 일곱 번째 루프가 들어가면 17이라 `DB_POOL_SIZE`·`DB_MAX_OVERFLOW`를 같이 올려야 한다. 잊으면 풀 오류가 아니라 재조회의 `attempt_timeout`이 먼저 걸려 이벤트가 조용히 버려진다. `test_deploy_env_wiring.py`가 `started(` 호출을 세므로 테스트가 잡지만, 이 문서에도 적어 둔다.

**이것이 "모든 memory를 미러링"이 아닌 이유**: 원본은 statement(owner당 수천, 텍스트 포함)이고 파생본은 owner×QID 행(owner당 수백, 숫자와 날짜)이다. 파생본에서 원문을 복원할 수 없고, 삭제·동의 철회는 다음 사이클의 교체와 reconciliation으로 따라간다. **그래도 개인 데이터다** — 누가 무엇을 얼마나 아는지의 요약이므로, `consultable` 없이 적재하지 않는다.

### 7-4. 소스 B가 비어 있을 때

`bourbon-v2` tenant에 personal build가 실제로 몇 owner에 대해 돌았는지는 코드로 알 수 없다(§16). 소스 B 행이 없는 owner는 소스 A만으로 랭킹되고(`prior_only`), 두 소스의 교차 확인 feature는 0이다. 파생본이 비어 있어도 서비스는 동작한다 — 그래서 슬라이스 1을 소스 A만으로 시작할 수 있다(§15).

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
    {"agent_id": "uuid", "owner_user_id": "uuid", "position": 1,
     "covers": [{"need_id": "n0", "coverage": "evidence_coarse"}],
     "reason": "일본 위스키·증류소에 관한 근거가 있습니다."},
    {"agent_id": "uuid", "owner_user_id": "uuid", "position": 2,
     "covers": [{"need_id": "n1", "coverage": "prior_only"}],
     "reason": "도쿄 가족 여행 쪽을 보완할 수 있습니다."}
  ],
  "empty": false,
  "degraded": []
}
```

- `mode`: `single | group | none`. `none`이면 `empty: true`이고 `agents`는 빈 배열이다 — required need를 아무도 덮지 못했거나 동의한 후보가 없을 때(§2-3).
- **`agents[]`의 항목은 새 wire 모델 `KnowledgeRecommendedAgent`다.** 타입 ①②③의 `RecommendedAgent`는 `position`·`matched_topics`·`signals`가 필수이고 세 타입이 한 모델을 쓴다(§3-4) — 거기에 `covers`를 더하면 세 계약에 필드가 생기고, 위 예시처럼 `matched_topics`·`signals`를 빼면 그 모델이 아니다. 내부 공통 base(`agent_id`·`owner_user_id`·`position`)만 나누고 wire 모델은 분리한다. `covers[]`의 `coverage`는 §6 T3의 세 상태다.
- `confidence`는 **첫 슬라이스에서 외부 필드로 열지 않는다.** calibration 전의 숫자는 decision log에만 둔다(열린 항목 §17-4).
- `degraded[]` 후보: `expansion_partial`(기존), `need_fields_defaulted`, `source_b_stale`, `evidence_search_unavailable`, `evidence_search_incomplete`. `grounding_failed`·`grounding_ambiguous`는 타입 ①과 같이 422다.
- 걸러진 후보 수, 숨은 후보의 존재를 추정할 수 있는 값은 응답에 없다(불변식 5).

---

## 9. 도메인 확장

1차 초안은 "기존 `TopicQuery`·`SourceHit`·`ExplicitRanker`에 끼워 넣지 말라"고 했다. 이 문서는 그것을 **슬라이스별로**(§15) 본다. 그 경고의 이유 셋 — topic visibility를 동의로 간주, `SourceHit.tier`에 memory 의미를 넣음, `topic_score`를 evidence sufficiency로 읽음 — 은 전부 **memory-api 파생 근거를 topic row의 모양에 담을 때** 생기는 문제다. 1차 초안에는 그 근거밖에 없었다.

- **슬라이스 1(소스 A만)**: need 하나는 grounding된 `topic_id`이고, 그것은 곧 `TopicQuery`다. 데이터는 진짜 topic row라 tier는 진짜 topic visibility이고 `knowledge_facet`은 topic-api가 그 row에 붙인 값이다 — 억지로 넣는 의미가 없고, 동의는 tier가 아니라 `agents.discoverable`로 따로 건다(§10-2). 새 것은 need 여러 개를 한 요청에서 돌리는 orchestration, `knowledge_facet`·coverage를 읽는 랭커 feature, set-cover, envelope이다. 기존 도메인 위에 얹는 것이 맞다. 여기서 새 `CandidateSource`를 만들면 `visible_topic_rows`를 읽는 코드가 둘이 되어 조금씩 다르게 굴러간다.
- **슬라이스 2(소스 B)**: QID로 조회하는 새 `CandidateSource`와 새 `SourceHit` 종류가 필요하다. 여기서부터 `SourceHit.tier`에 memory 의미를 억지로 넣지 않는다는 1차 초안의 경고가 유효하다.

새 도메인 후보: `KnowledgeNeed`(ConceptGroup + importance + kind), `NeedCoverage`, `CapabilityHit`(소스 B), `GroupPlan`, `KnowledgeRecommendation`. 새 stage 후보: `GroupPlanning` 하나. 나머지는 기존 stage의 파라미터 확장이다.

재사용하면 안 되는 의미는 1차 초안과 같다 — topic visibility를 personal knowledge 동의로 간주하지 않고, `topic_score`를 evidence sufficiency로 읽지 않는다.

### 9-1. 타입 ①·②·③에 미치는 영향

②·③은 접점이 없다. ①과 공유하는 것을 만지는 지점은 다음이고, 각각 어떻게 막는지를 적는다.

| 만지는 것 | 영향 | 막는 방법 |
|---|---|---|
| expansion 프롬프트·스키마 | **있을 수 있음** — ①과 공유하면 grounding이 흔들린다 | 형제 프롬프트로 분리(§6 T1). ①의 것은 그대로 |
| 워커 주기 루프 추가 | **있음** — 풀 하한 16 → 17 | 풀 크기 조정(§7-3). 배선 테스트가 잡는다 |
| `visible_topic_rows` 컬럼 둘 | 없음 — nullable 추가, ①②③ 랭커는 읽지 않음 | 응답에 없으면 NULL |
| `CandidateSource`·`VisibilityFilter` 재사용 | 없음 — 읽기만 | — |
| 새 route·랭커·stage·테이블 둘 | 없음 — 별도. 응답 모델도 `KnowledgeRecommendedAgent`로 분리(§8) | — |
| 레지스터 행 추가 | 동작 없음. `settings_hash`가 바뀌어 **①②③ decision log의 해시가 배포 후 달라진다** | 배포 노트에 "값 변경 아님, 행 추가" |
| deferq | 없음 — 새 이벤트를 받지 않으니 새 큐도 없다 | — |

**공유 자원의 부하**는 코드가 아니라 호출량의 문제다. 새 타입은 질문당 e3llm 1~2회, topic-api 검색 1~3회를 더 보낸다. e3llm에는 용량 문서도 서킷 브레이커도 없어서(R60 ⑤) 새 타입이 많이 불리면 ①의 꼬리 지연 시간이 같이 늘 수 있다. 슬라이스 4(트리거)를 넓히기 전에 e3llm 쪽에 용량을 묻는다(§16).

---

## 10. 개인정보·권한

### 10-1. 지금 있는 것과 없는 것

- memory-api personal 데이터에는 visibility·동의가 없다. cross-owner route는 tenant 경로만 알면 누구의 label이든 준다.
- topic-api의 `public/friends/private`는 **관심사 공개** 범위다. 관심사를 공개하는 것과 사적 대화에서 배운 것을 대신 답하게 하는 것은 노출 강도가 다르다. 재사용하지 않는다.
- 우리 `agents.discoverable`은 "공개 topic이 하나 이상"에서 파생한 값이다.

### 10-2. 동의 정책 — 소스 A와 B가 다르다

```text
discoverable   agents.discoverable (지금 것, "공개 topic이 하나 이상"). 소스 A 후보로 발견될 수 있음
consultable    없음 → bourbon-api의 agent 설정에 opt-in 필드로 요청 (§16). 소스 B 적재와 T3-2의 owners 목록은 이것을 요구한다
answer_share_scope, evidence_share   실행 단계(bourbon-agent)의 것. 이 문서 범위 밖
```

- 소스 A(topic row)는 owner가 이미 `public`/`friends`로 공개한 관심사다. 그것을 "이 사람이 관심 있어 보인다"는 prior로 쓰는 것은 타입 ①②③이 지금 하는 일과 같은 노출이라 `discoverable`로 충분하다. 단, 문구는 `prior_only`의 것이어야 한다(§6 T6) — "근거가 있다"가 아니라 "관심과 지식 신호가 있다".
- 소스 B(memory 파생)는 다르다. **owner가 어떤 QID를 알고, statement가 몇 개이고 어떤 종류이며, 언제 마지막으로 말했는지**는 텍스트가 아니어도 개인 데이터다. `discoverable`은 그 사용에 동의한 것이 아니다. 그래서 **소스 B의 production 적재는 `consultable`이 있고 그 값이 true인 owner에 대해서만** 한다. 그 전에는 dev와 합성 모집단에서만 만든다. 이것이 슬라이스 2의 선행 의존성이다(§15).

이 갈림은 2차 보정에서 정했다. 1차 초안의 열린 항목 "`consultable`이 생기기 전 `discoverable`로 대체하는 기간을 둘 것인가"는 이것으로 닫힌다 — 소스 A는 대체하고, 소스 B는 기다린다. 남는 것은 `consultable`의 소유와 기본값(opt-in인가 opt-out인가)이고 그건 bourbon-api와 제품의 결정이다(§16 질문 8).

강제 위치: 소스 B 적재의 owner 선별(§7-3 1단계)과 후보 조회 SQL의 `JOIN agents … WHERE consultable`. **discovery가 비동의 owner의 데이터를 받은 뒤 거르는 일이 없어야 한다** — 적재 단계에서 걸러야 파생본에 그 owner의 행이 처음부터 없다. 2차 초안에서 "파생본에 label이 없으니 걸러 내기 전에 읽는 private 데이터도 없다"고 쓴 것은 틀렸다.

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

**유효 deadline은 호출자의 10초다.** 우리 파이프라인 deadline이 20초여도 bourbon-agent가 10초에 끊으면 그 뒤는 아무도 안 받는 답이다. 새 route는 **자기 deadline을 호출자 예산 아래**(레지스터 행, 초기 8초)로 두고, 그러면 따라오는 것이 있다 — LLM 시도 예산 6초 × 2회 = 12초가 8초 안에 들어가지 않는다. 이 route의 completion은 `4초 × 2회` 또는 `6초 × 1회`처럼 **타입 ①과 다른 시도 예산**을 가져야 한다(레지스터 행). R60 ②가 20초 벽에 대해 말한 꼬리 문제가 여기서는 10초 벽이다. bourbon-agent 쪽 예산을 함께 바꾸는 것도 길이지만 그건 그쪽 턴 예산의 문제다(§16).

### 11-2. 추천 경로

| 단계 | LLM | 예상 p50 | 예상 p95 | 비고 |
|---|---:|---:|---:|---|
| T0 tool 결정 | 없음(추가분) | 0 | 0 | 이미 돌고 있는 턴 |
| T1 need 추출 | 1회 | 0.8~1.8 s | 2.5~4.5 s | 타입 ① expansion과 같은 호출, 출력 필드 둘 추가. 시도 예산은 이 route 것(§11-1) |
| T2 grounding 검색 | 없음 | 30~100 ms | 150~400 ms | 그룹 3개 병렬 |
| T2 disambiguation | 조건부 1회 | 0.5~1.5 s | 2~4 s | batch 1회 |
| T3-1 두 소스 조회 | 없음 | 2~15 ms | 30~80 ms | SQL, 후보 상한 N=50 |
| T3-2 evidence route | 없음 | 80~250 ms | **≤ timeout** | 후보 N명 BM25. p95는 timeout이 자른다. timeout 초기값은 실측 뒤 — 추정 p95(400~900 ms)보다 낮게 잡으면 fallback 비율이 그만큼 오른다 |
| T4·T5 랭킹·group | 없음 | < 10 ms | < 50 ms | |
| T6 조립·journal | 없음 | 5~30 ms | 30~100 ms | |

**end-to-end 추정: p50 1.6~2.8초, p95 4~7초, hard cap은 route deadline 8초.** 1차 초안의 3회 LLM(judge·decomposition·disambiguation) 대비 경로가 하나 줄었고, 남은 둘은 타입 ①이 이미 실측한 호출이다. T3-2가 더한 것은 네트워크 1홉이고 timeout이 상한이다. 꼬리에서는 T1의 재시도 한 번(4초 × 2)만으로 8초에 닿을 수 있으므로, T1이 재시도한 요청은 disambiguation을 생략하고 규칙 결과로 진행하는 것을 검토한다(열린 항목 §17-13).

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
| owner의 manifest가 사라짐(계정 삭제) | K 사이클 뒤 reconciliation이 행을 지운다. 그 사이 그 owner는 후보가 될 수 있다 — `agents` 쪽 `user_deactivated` 처리가 먼저 잡는다 | — |
| owner가 `consultable`을 끔 | 다음 사이클에 적재 대상에서 빠지고 reconciliation이 행을 지운다. 조회 SQL의 `WHERE consultable`이 그 사이를 막는다 | — |
| `topic_qid_map`에서 잘린 topic | 그 need는 소스 A만, 상태 `prior_only` 상한 | — |
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
coverage_states                need × 상위 agent의 prior_only / evidence_coarse / evidence_text_matched 개수
single_sufficient, group_size, covered_required, uncovered_required
source_b_max_age_seconds
degraded[]
latency_ms.{expand, ground_search, ground_llm, retrieve, evidence_search, rank, group, assemble, total}
```

실행은 별도 journal이다(`recommendation_id`, `members_requested/answered/timed_out`, `needs_supported/unsupported`, `conflict_count`, latency).

**핵심 지표**: 추천 당시 need coverage와 실행 당시 `supported/unsupported`의 calibration error. "잘 알 것이라고 추천했는데 실제 agent가 답하지 못한 비율"을 계속 잰다. 랭커 feature 가중치는 이 지표로 고친다. coverage 상태별로 나눠 재면 `prior_only` 추천이 얼마나 자주 `unsupported`로 끝나는지가 보이고, 그것이 §17-12의 답이다.

**호출 recall**(T0, bourbon-agent 쪽 journal): 추천이 필요했던 질문 중 tool이 불린 비율, recall 검색이 비었는데 tool을 부르지 않은 비율, 근거 없는 직접 답변 비율, 명시적 요청 때의 호출 성공률. 이 네 개가 나쁘면 랭커 지표는 의미가 없다.

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
- **T0 호출 recall**: owner의 근거로 답할 수 없는 질문 세트를 합성 모집단에서 만들고(정답 = "tool을 불러야 한다"), bourbon-agent의 프롬프트·tool 설명 변형별로 호출률을 잰다. 랭커보다 먼저 재야 하는 숫자다

### 14-2. 온라인 — 실측만 답하는 것

offline 합성 데이터로는 실제 answerability를 검증할 수 없다. §13의 calibration error가 유일한 답이고, 그것은 실행 단계가 있어야 잰다. 실행 단계 없이 추천만 내보내는 기간에는 **사용자가 추천을 수락했는지**를 대리 지표로 쓴다.

---

## 15. 구현 슬라이스

**슬라이스**는 혼자서 배포되어 동작하는 증분 하나다. 각 슬라이스는 route·데이터·랭킹을 끝까지 갖춘 채로 앞 슬라이스 위에 얹히고, 뒤 슬라이스가 없어도 그 자체로 추천을 낸다. 나누는 기준은 **새로 생기는 의존성**이다 — 다른 팀의 일정에 걸리는 것이 슬라이스 경계가 되도록 잘라서, 그쪽이 늦어도 앞 슬라이스는 배포된다. 문서 앞부분의 "첫 슬라이스"는 아래 표의 1번이다.

| 슬라이스 | 새 의존성 | 새 LLM 호출 | 답하는 질문 | 완료 조건 |
|---|---|---|---|---|
| **1. 소스 A + 단일 추천** | 없음 | 0 (스키마 확장) | 이 주제에 깊은 관심과 지식을 드러낸 사람(`prior_only`). **"아는 사람"과 "해 본 사람"은 구분하지 못한다** — topic row에 statement 종류가 없어 `knowledge_kind`는 추출·journal만 하고 랭킹에 쓰이지 않는다 | route·`KnowledgeRecommendedAgent` envelope, `knowledge_facet` 미러(우리 쪽 `PublishedTopic`·storage·fixture), need 다중 grounding, 결정적 랭킹, 합성 모집단 측정 |
| **1-b. group** | 없음 | 0 | 두 need를 두 사람이 나눠 덮는 경우 | 1의 coverage matrix 위에 set-cover, `mode: group`, 인원 2. **1의 중간 모델이 group을 지원하는 모양인지 검증하는 테스트 역할** |
| **2. 소스 B** | bourbon-api **`consultable`** + memory-api **compact export route** + `topic_qid_map` **spike 완료** | 0 | 구체적 근거 statement를 가진 사람(`evidence_coarse`) | 커버리지 측정(§16 질문 2 또는 파생본 자체로), `topic_qid_map`(bounded), `knowledge_capabilities`, 일곱 번째 루프 + reconciliation, 두 소스 합산 랭킹, `source_b_stale` |
| **3. T3-2 재점수** | memory-api **evidence route** | 0 | 질문의 조건까지 맞는 사람(`evidence_text_matched`) | route 계약 합의, 클라이언트, timeout·fallback, `stage1_final_overlap_at_k` journal |
| **4. 트리거** | bourbon-agent 변경 | 0 | 실제로 불리는가 | tool 설명 변경 또는 두 번째 tool, 호출 recall 지표 넷 |
| **5. 실행·종합** | bourbon-agent 소유 | agent당 1 + 종합 1 | 실제 답변 | 이 문서 범위 밖. `moderator/agent_recommender/` |

group이 1-b인 이유는 이 절의 정의 그대로다 — 외부 의존성이 없고, 소스 A만으로 `KnowledgeNeed[]`·후보·coverage matrix가 이미 만들어지므로 group planner에 필요한 입력이 전부 있다. 2차 초안에서 4번에 둔 것은 정의를 내가 어긴 것이다.

슬라이스 1·1-b는 memory-api와 bourbon-api의 일정과 무관하게 배포할 수 있다. **슬라이스 2는 세 선행 조건이 다 있어야 시작한다** — `consultable` 없이 적재하면 동의 경계를 넘고(§10-2), export route 없이는 파생본을 만들 수 없고(§7-3), spike 없이는 map이 얼마나 잘리는지 모른다(§7-2). 슬라이스 3이 들어가는 날부터 fallback이 곧 그 전날까지의 동작이다 — 새 경로가 아니다.

슬라이스 1은 타입 ① 위에 "need 여러 개 + knowledge 가중 랭커"를 얹는 것이라 새 도메인이 거의 없다. 슬라이스 4는 1과 동시에 시작할 수 있다 — discovery 쪽이 준비되기 전에는 지금 `recommend_agents`가 하는 일과 같으니 사용자에게 보이는 변화가 없고, 호출 recall 측정(§14)은 discovery 없이도 시작할 수 있다.

---

## 16. 확인할 것과 요청할 것

다른 팀에 물어야 하는 것이다. 답이 오기 전에는 위 설계를 그대로 두고 슬라이스 1을 진행할 수 있다.

**memory-api**
1. `bourbon-v2` tenant에 personal build가 실제로 돌고 있는지, 몇 owner인지, 주기는 어떻게 되는지. 소스 B의 가치가 이 숫자에 달려 있다.
2. 그 빌드 결과에서 **`knowledge_qid`·`broader_qids`의 상위 분포**를 받아 볼 수 있는지(QID와 개수만, owner·label 없이). 우리 카탈로그 QID와 `topic_qid_map`(§7-2)의 교집합이 얼마인지가 소스 B 커버리지의 첫 측정이다. 이것을 모르면 소스 B를 만들어도 얼마나 잡히는지 말할 수 없다.
3. **compact export route**(소스 B의 선행 의존성, §7-3) — owner 하나에 대해 `(qid, identity_entities, broader_entities, active_statements, procedural_statements, experiential_statements, hands_on_statements, has_provenance, last_seen)`을 label·blurb·text·message id 없이 돌려주는 owner-scoped route. 지금 entity route에는 kind별 개수와 provenance 유무가 없고, statements route는 원문을 싣기 때문에 우리가 조합해 만들 수 없다(§3-2). 가능하면 `qids` 목록을 받아 그 집합 단위의 **distinct entity 수**도 함께 — topic 단위 합산에서 entity 중복을 빼는 유일한 길이다(§6 T3-1).
4. **evidence route**(§6 T3-2) — `POST /{tenant}/personal/evidence/search`. 조건은 셋이다. (가) `owners` 허용 목록이 필수이고 그 밖의 owner는 어떤 형태로도 응답에 없다. (나) 응답에 statement 텍스트·entity label·message id가 없고 점수·개수·날짜만 있다. (다) 그쪽에서 OpenSearch 재시도를 중첩하지 않는다(우리가 사다리를 갖는다). 요청자의 질문 텍스트가 그쪽으로 가므로, 이 route와 함께 내부 호출 인증이 들어가야 한다. 1차 초안이 Phase B로 제안했던 것의 축소판이다.
5. **폴링 피드**: `GET /{tenant}/admin/personal/build`가 지금 `offset`·`limit`만 받는다. `(built_at, owner_id)` 기반 안정 cursor 또는 `updated_since`를 붙여 주실 수 있는지, 그리고 계정 삭제로 manifest가 지워질 때 tombstone을 남길 수 있는지. 없으면 우리는 전체 페이지를 매 사이클 넘기고 K 사이클 reconciliation으로 삭제를 따라간다(§7-3). 그리고 `POST /knowledge/expand`를 카탈로그 갱신 때 넓은 topic은 seed 하나씩, 합쳐 수백 회 호출해도 되는지.

**topic-api**
6. `GET /users/{id}/topics` 응답의 `blocks[]` 안 `type: "score_detail"` block — 이미 오고 있고 우리 adapter가 읽는다(§7-1). 물을 것은 **그 block의 facet 이름(`knowledge` 등)과 `confidence`를 소비자 계약으로 삼아도 되는가**다. 우리 wire 주석이 "합의하지 않은 계약"이라 적어 둔 것을 합의로 바꾸는 일이고, 그쪽 답이 "예"면 우리 upstream fixture에 고정한다.
7. 소스 B 커버리지 측정에서 시설↔제품처럼 Wikidata 관계로 못 건너는 구멍이 크게 나오면, 카탈로그 편집으로 메울 수 있는지(예: "위스키 증류소"를 위스키의 자식 topic으로). 편집 정책에 맞는지는 그쪽 판단이다.

**bourbon-api**
8. agent 설정에 `consultable`(다른 사용자의 질문에 내 agent가 대신 답해도 되는가) opt-in 필드를 둘 수 있는지, 기본값을 opt-in으로 할지, 그리고 그 변경을 이벤트로 낼 수 있는지. `personal_agent_visibility_changed`가 만들어지지 않았던 것과 같은 이유로 이벤트 대신 재조회가 될 수도 있다.

**e3llm**
9. 새 타입이 질문당 completion 1~2회를 더 보낸다. 슬라이스 4에서 트리거를 넓히면 호출량이 타입 ①의 몇 배가 될지 우리도 모른다. 처리량·레이트 리밋 상한이 얼마인지 — 타입 ① 요청서에 이미 있는 질문과 같은 것이다.

**bourbon-agent**
10. `recommend_agents`의 트리거를 넓히는 것과 두 번째 tool을 두는 것 중 어느 쪽이 프롬프트 설계상 맞는지. `moderator/agent_recommender/`의 계획이 이 기능과 같은 것인지.
11. T0의 **호출 recall 지표 넷**(§13)을 그쪽 journal에서 낼 수 있는지 — tool 호출 여부는 그쪽만 안다. 그리고 새 tool의 호출 예산을 지금 `recommend_agents`의 10초로 둘지, 그 안에서 우리 route deadline 8초가 맞는지(§11-1).

---

## 17. 열린 항목

1. 요청자가 추천을 수락한 뒤에만 실행할지, 자동 실행할지(1차 초안 3번, 그대로).
2. required need 하나가 비었을 때 partial answer를 허용할지(1차 초안 5번, 그대로).
3. group 인원을 2에서 3으로 올릴 조건.
4. calibrated confidence를 외부 필드로 열 시점과 조건.
5. 소스 B의 `stale` threshold — memory-api 빌드 주기가 정해진 뒤 레지스터 행으로.
6. 실행 단계의 feedback event(추천 id ↔ `supported/unsupported`) 이름과 payload. calibration error를 재려면 이것이 먼저 있어야 한다.
7. 슬라이스 1을 타입 ① 도메인 위에 얹는 것을 슬라이스 2에서 새 소스로 나누는 시점의 기준.
8. `topic_qid_map`에 `typed` 관계를 넣을지, `narrower`만으로 시작할지 — 커버리지 측정 결과로 정한다.
9. 소스 B 커버리지가 낮을 때 조인 키를 memory-api의 `classes` 인덱스(그쪽이 theme으로 판정한 클래스)로 바꾸는 대안을 열어 둘지. tenant별로 동적이라 매핑 테이블이 어차피 필요하고, 첫 슬라이스에서는 `expand` 쪽이 단순하다고 본다.
10. evidence route에 `owners` 없이 tenant 전체를 치는 모드를 열 것인가. T3-1의 사각을 피할 수 있지만, 비동의 owner의 count가 우리에게 오는 문제를 memory-api 쪽 `consultable` 필터로 풀 수 있게 된 뒤에만 가능하다. 커버리지 측정 결과를 보고 정한다.
11. 1단계 후보 상한 N의 초기값(50)과, fallback 모드에서 `mode: none`을 내는 threshold를 평소보다 올릴지.
12. `prior_only`(소스 A만)로 required need를 covered로 볼 것인가. 초기값은 "본다, 단 낮은 가중과 약한 문구"이고, coverage 상태별 calibration error(§13)가 답을 준다.
13. T1이 재시도한 요청에서 disambiguation을 생략할 것인가 — route deadline 8초 안에 LLM 두 번을 넣는 방법으로, 정확도를 꼬리 지연 시간과 바꾸는 결정이다.
14. `topic_qid_map`을 `expand`로 만들지, 잘린 topic이 많으면 공개 지식 인덱스·dump에서 직접 만들지 — spike 결과로 정한다(§7-2).

닫힌 항목: "`consultable`이 생기기 전 `discoverable`로 대체하는 기간을 둘 것인가"는 §10-2에서 소스별로 갈라 정했다.
