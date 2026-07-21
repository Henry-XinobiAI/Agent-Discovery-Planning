# agentic stance retrieval — 설계 (for/against agent 추천)

- **상태**: PROVISIONAL / 브레인스토밍 수렴본. 아직 writing-plans 미착수, 구현 미시작.
- **날짜**: 2026-07-20 — 기존 `2026-07-16-stance-for-against-retrieval-design.md`(2-tier) + `2026-07-16-on-demand-stance-axis-registry-design.md`(axis registry)를 **단일 agentic on-demand 설계로 통합·재작성**. **axis_id registry는 폐기**(§2·§7). 이전 설계는 git 이력에 남는다.
- **범위**: Discovery의 for/against agent 추천을 memory-api personal knowledge로 **on-demand** 구현 + 필요한 cross-team 계약.
- **관련**: Phase 10 real-edge 통합(competence/groundings → AgentTopicEdge 투영), Phase 8-3 stance normalizer(query 정규화 재사용), Phase 8-5 rich-reason(top-N async LLM slice 패턴), grounding-agent LLM-component 규율(단 여기선 symbolic floor가 없어 judge=유일 엔진 — §D5).

---

## 1. 문제

`GET /{prefix}/personal/entities`(우리가 얘기하던 edge)가 각 에이전트의 토픽별 지식/입장을 준다. Discovery의 for/against는 "특정 명제에 대한 입장(favor/against)"이 필요한데, 응답이 주는 stance 신호는 `competence.sentiment`(극성) + `opinion_ratio` + `consistency` + `support_ids` 정도다.

**핵심 난점**: polarity(sentiment) 단독으로는 for/against를 못 정한다. sentiment는 "대상을 향한 감정 valence"이고 stance는 "명제 위에서의 방향"이라 자주 어긋난다(열정적 비판자 = 높은 engagement + against). 명제/축(axis)과 방향이 빠진 극성만으로는 방향 확정 불가.

**핵심 불변식 (설계 전체가 여기 달림)**: **sentiment는 stance verdict가 아니다. for/against verdict의 유일한 source는 LLM claim-judge다.** memory-api가 주는 topic-level stance는 verdict가 아니다 — stance 방향은 본질적으로 **query-axis-relative**인데(같은 topic이라도 "원전 확대"엔 against·"안전규제 강화"엔 for), 사전계산된 topic-level 값은 **axis-blind**라 verdict가 될 수 없다. 따라서 **live symbolic floor는 없다.** judge가 disabled/unavailable/degraded면 for/against는 후보를 반환하지 않고 **명시 사유와 함께 silence**한다(§D5). **sentiment→dir 합성 금지** — sentiment는 retrieval prior·evidence selection 전용.

**metadata→verdict 지름길 금지 (전부 query-axis 무지)**: 아래는 전부 retrieval prior로만 쓰고 verdict로 승격 금지 — `sentiment=positive → for` · `epistemic=opinion → stance 있음` · `statement_kind=preference → query에 찬성` · `confidence=1.0 → stance 확실` · `BM25 relevance 높음 → for/against 확정`. 이유는 하나로 수렴한다: 이 신호들은 **query 축을 모른다**. 방향 판정은 judge가 query stance를 알고 실제 claim을 읽어야만 성립한다.

## 2. 기각된 대안 (왜 안 되는지 기록)

**(a) aspect(토픽 하위 논점)를 discrete 키로 매칭** — 모든 시도가 같은 벽: aspect는 open-vocabulary + many-expression-one-meaning이라 exact 키는 파편화하고 fuzzy 키는 토픽 내 변별력이 붕괴한다.

- **새 aspect-QID 온톨로지 신설**: 토픽마다 aspect가 제각각 → 큐레이션/유지 비용 폭발. 파편화를 없애는 게 아니라 한 계단 아래로 relocate.
- **context-QID로 변별**: "climate change / global warming / carbon emissions / net zero"가 서로 다른 QID라, 같은 aspect 입장이어도 exact 겹침 실패. many-to-one 그대로.
- **임베딩 유사도**: 한 토픽 안 aspect들은 공유 성분이 지배해 cosine이 좁은 고대역에 뭉침 → 변별력 없음.

**구조적 결론**: aspect 세밀도에는 공짜 discrete 키가 없다. aspect 매칭엔 "유지되는 정규화 레이어"라는 없앨 수 없는 비용이 따른다.

**(b) axis_id registry (사전/점증 정규화 + verdict 캐시)** — 이전 설계는 반복 query의 judge 비용을 줄이려 opaque `axis_id`를 점증 생성하고 verdict를 materialize했다. **폐기**: (1) registry는 correctness에 필요한 구조가 아니라 순수 비용 캐시였고, (2) 캐시 freshness가 "판정에 쓴 evidence 집합"이 아니라 "entity/topic 전체 active-statement 상태"를 봐야 해서 memory-api `statement_revision` 계약을 새로 요구했으며, (3) axis_id·promotion/merge·materialization·lifecycle이라는 상당한 복잡도를 얹었다. Alpha(내부·저볼륨)엔 재사용 이득보다 복잡도가 크다. → **on-demand live judge를 유일 경로로.** 캐시는 나중에 진짜 비용 문제가 생기면 순수 최적화로 재도입하되 **axis_id 없이**(§7).

**결론**: Alpha = **topic QID 앵커 + 요청별 ephemeral proposition + agentic evidence search + live judge.** 유지할 온톨로지·registry 없음.

## 3. 파이프라인 개요 (on-demand, 요청마다 live)

```text
query 정규화                 (need_type + proposition 검증)
  → topic_qid + ephemeral proposition (방향-중립) + need_type(FOR | AGAINST)

Tier 1  후보 발견            (기존 memory-api 엔드포인트, 1콜)
  → topic-QID cross-owner shortlist + owner별 capped inline statements

Tier 1.5  agentic evidence search   (on-demand·single-pass·owner-chunk fan-out)
  → 요청당 1회 symmetric 검색어 생성 → subject_qid + shortlist owner_ids ANY-match 검색
    (owner_ids ≤20/call → ceil(K/20)회 owner-chunk fan-out)
  → owner별 union/dedup

Tier 2  claim judge          (유일 verdict source)
  → owner별 evidence 묶음 판정 → supports | opposes | insufficient
    (proposition에 대한 절대 입장 — 요청 방향 모름)

serving
  → need_type 필터 (FOR→supports · AGAINST→opposes) + deterministic ranking
  → evidence 부족/judge off·fail → 명시 silence
```

모든 요청이 "cold"(live judge)다 — verdict 캐시 없음.

## 4. 확정 결정 (LOCK)

### D1. Alpha = topic-QID 앵커 + ephemeral proposition (axis 온톨로지·registry 없음)

- 후보 발견의 앵커 = 깨끗한 Wikidata **topic QID 하나**(≠axis_id — 이건 Wikidata grounding이라 파편화 0). query는 요청 시점에 **ephemeral proposition + `need_type`(FOR/AGAINST)**으로만 정규화하고 **persistent id를 mint하지 않는다.**
- **★ proposition은 방향-중립(direction-neutral)이다** — claim만 담고 방향은 절대 인코딩하지 않는다(`"원전 확대"` O · `"원전 확대 반대"`/`"원전 확대 (against)"` X). 요청 방향은 **오직 `need_type` 한 곳**에만 존재한다. judge에는 `proposition`만 전달되고 **요청 방향은 전달되지 않는다**(judge는 proposition에 대한 **절대 입장**만 판정 — B5 계약). proposition에 방향을 겹쳐 넣거나 judge에 요청 방향을 알려주면 verdict가 뒤집힐 수 있다. B6 caller는 `proposition = Query.proposition`으로 고정.
- verdict는 Tier 2 judge가 **proposition에 대한 절대값(`supports`/`opposes`/`insufficient`)**으로 만든다(요청 방향과 무관) — aspect 온톨로지 없이도 축 구분("원전 확대" vs "안전규제")이 judge 안에서 암묵적으로 처리된다. 요청 방향과의 정렬은 이후 ranker가 `need_type`으로 필터링한다(§D4).
- aspect가 실제로 필요한 유일 케이스("전반 반대지만 이 한 축만 찬성")는 niche → **Open Beta 이월**. 추구 시 필요한 정규화 레이어는 **Discovery 소유**(memory-api 아님·§D6 ownership).

### D2. Tier 1 — topic-QID cross-owner shortlist (기존 계약)

- `GET /{prefix}/personal/entities/{qid}?owner_id=(생략=전 owner)&sort=confidence&with_statements=true&statements_limit=M&limit=K`(`api/routers/personal/router.py:195`)가 cross-owner 후보 pool(각 owner의 `PersonalEntitySummary`=competence·salience·opinion_ratio·hands_on_ratio·sentiment) + `with_statements`로 owner당 active statement M개 인라인을 **1콜**로 준다. → Tier 1은 신규 계약 없이 성립(§D6-1 — server-side 필터/정렬 추가 안 함).
- 후보 발견은 (가능 여부와 무관하게) **exact topic QID 경로로 제한한다 — 이 설계의 correctness 선택**. `POST /personal/entities/search`가 owner/QID 없는 global label/alias 검색을 지원하지만, free-text 후보 발견은 §2(a) 파편화를 되살리므로 채택하지 않는다(앵커는 항상 QID).
- **★ eligibility 선행 gate (LOCK · 모든 단계 앞)**: Tier 1 후보 pool은 **statement 검색·judge 입력·provenance deref 어느 것보다 먼저** eligibility+discoverable로 걸러야 한다. 불변식 **`judge_owner_ids ⊆ eligible_and_discoverable_owner_ids`** — Tier 1.5 검색에 넘기는 `owner_ids`, judge에 넣는 후보, provenance dereference 모두 eligibility 통과 owner에 한정. provenance는 PII gate뿐 아니라 **owner 공개 범위(disclosure scope)** 도 적용. (eligibility provider 구현은 별도 트랙이나, 이 **선행 순서**는 stance 파이프라인의 LOCK 불변식.)
- **★ K = 전체 recall 상한 (안전장치 필요)**: Tier 1.5는 shortlist `owner_ids` 안에서만 검색하므로 `sort=confidence&limit=K`에서 탈락한 owner는 이후 **복구 불가**. **grounding confidence ≠ stance relevance**이고 `has_opinion`도 experiential/procedural에 담긴 입장을 놓쳐 **hard filter로 부적절 → prior로만**. 대응(§5 확정): **충분히 overfetch 후 Discovery에서 축소 + eval에서 Tier 1 owner recall@K 측정·K ratchet**. (eligible-pagination은 현 memory-api `Page`가 cursor/offset 없이 `truncated`만 주므로 불가 — `api/routers/base.py:202` — Alpha에서 memory-api 변경 1건 유지 위해 배제.)
- **★ owner ↔ topic-entity 카디널리티 (candidate 정의 근거)**: **exact anchor QID 경로**(`GET /personal/entities/{qid}` · statement `subject_qid`가 `knowledge_qid`와 정확히 일치)에서는 **`(owner_id, subject_qid)`당 personal entity가 0개 또는 1개**다(memory 불변식 — WIKIDATA grounding reuse-before-mint, `structs.py:226`·`pipeline.py:845`; 표기가 달라도 **같은 QID로 올바로 grounding된 경우** 1 entity로 병합). grounding 없는 owner도 있고 K cutoff로 응답에서 빠질 수도 있어 "정확히 1"이 아니라 **"0 또는 1"**. → stance judge의 **후보 단위 = `(owner_id, subject_entity_id)`**(owner 단독 키 아님 — `subject_entity_id`를 judge input·evidence 연결·로그에서 유지해야 계약 변화·grounding 오류를 안전하게 감지); 그 덕에 owner별 evidence 묶음이 **단일 topic entity로 안정적으로 귀결**된다. ⚠️ 단 1:1은 **exact QID에만** — `POST /personal/entities/search`의 `qids` 필터는 role-tagged grounding 전체(IDENTITY/BROADER/RELATED)를 훑어 같은 broader/related QID에 한 owner의 **여러 entity**가 걸릴 수 있으므로 그 global search 결과엔 이 불변식을 적용하지 않는다.
- ⚠️ **statement `text`의 성질(judge/검색이 알아야 함)**: `text`는 조회 시 생성값이 아니라 **build 시점에 LLM extractor가 원문을 압축·영어화해 저장한 요약**(원문 발췌·Wikidata desc 아님)이라 반어·인용·부정에서 nuance가 소실되고, reconcile `noop` 시 최초 요약이 고정되어 **stale**할 수 있다. statement `confidence`는 **발화자 귀속(attribution)** 신뢰도(owner 1.0 / owner-engaged 타인 0.7·결정적)이지 진위·요약 정확도·stance 강도가 아니다. → 원문 근거가 필요하면 `support_snippet`/provenance deref(§D6-3).

### D3. Tier 1.5 — agentic evidence search (on-demand·batch·symmetric·owner-chunk fan-out·bounded)

Tier 1 inline만으로 판정이 어려운 후보에 대해, 관련 stance evidence를 **on-demand로 recall**한다. **recall 전용 — verdict 아님.**

- **요청당 batch (후보별 K회 아님)**: 요청 단위로 검색어를 **한 번** 생성하고, shortlist owner들을 대상으로 **batch 검색**(§D6-2 `subject_qid` + `owner_ids`) 후 owner별 union/dedup. (후보마다 개별 tool loop를 돌리지 않는다 — 비용/latency 폭증 방지.)
- **★ "요청당 1회"의 정확한 의미 (배포된 Alpha shape)**: **symmetric 검색어 생성(LLM query-expansion)이 요청당 1회**다. 검색 실행은 memory-api 엔드포인트가 `owner_ids`를 호출당 20개로 제한하므로(§D6-2), Discovery 어댑터가 shortlist를 **owner-chunk로 나눠 `ceil(K/20)`회 fan-out**한다(bounded-concurrency semaphore·chunk는 disjoint owner set이라 concat merge). 각 호출은 **모든 query를 하나의 ANY-match 배치**로 보낸다(단일 검색, query별 top-F fanout 아님·§D6-2). **Alpha는 post-judge escalation이 없다** — shortlist 전원에 대해 한 번 검색한 뒤 바로 judge한다. (2단계 escalation[pre-judge 조건부 검색 + post-judge `insufficient` 재검색]은 §D3-future 모델로 이월 — inline-완결 후보가 별도로 존재해야 성립하므로 §D5의 whole-request silence와 함께 후속.)
- **★ symmetric 검색어 (recall scaffold — 방향 판정 아님)**: BM25 query는 **stance 방향을 판정하지도, 보장하지도 않는다**(어떤 매칭이 support인지 oppose인지 lexical match만으로는 알 수 없다). `neutral`/`support`/`oppose` 세 목록의 목적은 **polarity별 lexical vocabulary를 골고루 생성해 양방향 recall 폭을 넓히는 scaffold**일 뿐이다 — 한쪽 어휘만 생성하면 그 owner의 반대편 claim이 lexical하게 아예 안 걸려 recall에서 누락된다("원전 확대 반대" 요청인데 oppose 어휘만 만들면 그 owner의 support claim이 검색조차 안 됨). **실제 방향 판정(supports/opposes)은 judge만** 담당한다(§D4·절대 verdict). 검색어는 항상 **대칭 생성**한다:
  ```json
  { "neutral_queries": ["nuclear power expansion", "building additional nuclear plants"],
    "support_queries": ["increase nuclear generation capacity"],
    "oppose_queries":  ["phase out nuclear power", "against new nuclear plants"] }
  ```
  검색은 양쪽 evidence를 recall하고, **입장(supports/opposes) 판정은 judge만** 한다. 어휘 mismatch(요약 text가 검색어와 안 걸림)와 single ANY-match의 owner-cap crowding(§D6-2)이 recall에 미치는 영향은 **전용 stance-evidence recall eval에서 측정**한다(§5).
- **Alpha flow = single-pass (escalation 없음)**: `symmetric query-gen → shortlist 전원 owner-chunk 검색 → judge`. inline-완결 후보를 따로 골라 검색을 건너뛰는 short-circuit이 없고, `insufficient` 후보를 다시 검색하는 post-judge retry도 없다 — 부족하면 바로 drop.
  - **§D3-future (이월)**: **2단계 escalation** — Pre-judge(`statements_truncated=true`·inline 부족·dense/prolific owner일 때만 검색) + Post-judge retry(inline 판정이 `insufficient`면 그 owner만 **딱 한 번** 재검색 후 재판정). inline-완결 후보가 별도로 존재해야 성립하므로 §D5 whole-request silence 모델을 실제 도입할 때 함께 온다.
- **bounded (명시)**: Alpha는 재검색 loop 없이 **owner-chunk fan-out(`ceil(K/20)`) + owner당 `per_owner_limit`**로 상한이 정해진다 · 검색 결과 밖 evidence id 사용 금지 · 부족 시 **`insufficient`/drop** (topic-discussers fallback **금지** — §D5; stance 미평가 후보를 결과로 내보내지 않음). (후보별 tool loop·비용 폭증 차단.)
- **가드**: statement-search 결과는 **relevance 순서로만** 오고 **score는 응답에 없다**(§D6-2) — 순서를 stance confidence로 쓰거나 owner간/query간 비교 금지. **검색 miss ≠ "그 owner는 입장 없음"**(그냥 그 요청에서 evidence를 못 찾은 것). §2(a) 파편화 회귀 아님 — 앵커는 여전히 QID, BM25는 그 QID 안에서 관련 claim을 고를 뿐.
- **★ hit → shortlist key 검증 (acceptance)**: 각 search hit은 **`(hit.owner_id, hit.subject_entity_id) ∈ shortlisted_candidate_keys`**(§D2 후보 키)여야 한다. 위반 hit은 **judge 입력에서 제외** + decision log에 **contract violation** 기록 — cardinality 불변식이 깨졌을 때 다른 entity의 evidence를 owner 기준으로 잘못 합치는 것을 방지.

### D4. Tier 2 — judge는 "선택"이 아니라 "판정" (ordering contract 보존)

- LLM은 후보(**단위 = `(owner_id, subject_entity_id)`**·§D2)별 **판정만**: `{verdict: supports | opposes | insufficient, evidence_stmt_ids, graded_confidence}` (proposition에 대한 **절대 입장** — 요청 방향 미전달). `graded_confidence`는 랭킹에 쓰므로 **필수 `[0,1]`** — 누락/범위 밖이면 그 응답은 **schema-invalid = judge engine 실패**이므로 그 후보를 **`None`(candidate judge error)** 로 처리한다(evidence 부족인 `insufficient`와 구분: malformed output은 "증거로 판단 불가"가 아니라 "판정기가 못 돌았다"). B6는 이 `None`을 후보 단위 judge error로 세고, **usable verdict가 0이면서 judge `None`이 하나라도 있으면 `stance_judge_failed` silence**(mixed insufficient+`None`도 포함 — `None`은 verdict가 아니라 엔진 오류이므로 우선; §D5 line 117과 동일 규칙). confidence 없는 후보가 랭킹에 섞이는 일은 이 `None`-drop으로 차단된다.
- 랭킹은 그 위에서 **여전히 결정적으로** competence + judge `graded_confidence`(= stance verdict confidence)로. LLM verdict는 **필터/주석**이지 scalar score가 아님. → "scalar score 없음 · 결정적 lexicographic ordering" 계약 유지.
- **불변식**:
  - judge는 **후보 집합(Tier 1 shortlist) 밖 agent를 추가하지 못한다.**
  - verdict=`insufficient` 후보는 for/against need에서 **drop**한다.
  - **firsthand-honesty**: `evidence_stmt_ids`는 **judge에게 실제 제공된 statement id의 subset이어야 한다** — Alpha에서 제공 집합 = `judge_input_stmt_ids` = **Tier 1.5 검색 결과 중 검증(owner·shortlist·subject_qid match)·dedup 후 실제 전달된 id**뿐이다(evaluator가 Tier 1 inline을 judge에 합치지 않는다 — `discovery/stance.py`). violation 시 degrade scope는 **후보 단위**(§D5). (Tier 1 inline id ∪ Tier 1.5는 inline-완결 후보를 도입하는 §D3-future escalation 모델의 계약 — Alpha 아님.)
  - **★ verdict → ranker adapter (LOCK · 배포됨)**: judge verdict는 **proposition에 대한 절대 입장**이다(요청 방향과 무관). **need 필터** (ranker C2): `NeedType.FOR → verdict=supports만 유지` · `NeedType.AGAINST → verdict=opposes만 유지`. 배포된 계약:
    1. **Candidate의 query-time 필드는 `stance_proposition`·`stance_position`·`stance_confidence`**(`discovery/structs/recommend.py`)로, evaluator가 judge 결과로 채운다 — `stance_proposition = Query.proposition` · `stance_position` = judge verdict(`StancePosition` = supports/opposes) · `stance_confidence` = judge graded_confidence. (relative `stance_axis`/`stance_dir` 모델은 폐기 — 방향은 Candidate가 아니라 `need_type` 필터가 적용한다.)
    2. **ranker의 stance filter/정렬 key/confidence gate는 edge가 아니라 이 Candidate 값을 소비**한다(edge에서 stance를 읽던 경로 제거 완료).
    3. **`AgentTopicEdge`는 변경하지 않음**(memory 소유·stance 저장 안 함). [00 pipeline-io](../../../impl/00-pipeline-io-reference.md) 참조.

### D5. judge = for/against의 유일 엔진 · 플래그 · judge-off silence

- **유일 엔진**: floor가 없으므로 judge는 for/against 기능의 **유일한 구현체**다. 플래그(`STANCE_JUDGE_ENABLED` 류) 의미 = **"for/against 기능 on/off"**. dark-merge(코드 OFF 머지)는 OK지만 **Alpha 배포는 judge를 ON으로 돌린다**.
- **judge OFF / unavailable / degraded → (b) 명시 silence**: `recommendations=[]` + `silence.silent=true` + `silence.reason`. **empty result와 구분되도록 사유를 남긴다** (closed vocabulary **6종**):
  - `stance_judge_disabled` — 플래그 OFF (dormant-ship 기본)
  - `stance_judge_unavailable` — evaluator/의존성이 미제공·미배선(`UpstreamUnavailableError`). **구성/통합 갭**이지 런타임 실패가 아니며, 실검색 실패와 구분한다.
  - `stance_query_generation_failed` — LLM query-expansion leg 실패(또는 비대칭 expansion). 검색이 **아예 실행되지 않았으므로** search 실패로 보고하면 거짓이다 → 별도 사유.
  - `stance_evidence_search_failed` — statement-search가 **실행됐으나** 요청 시점에 실패(upstream 오류).
  - `stance_judge_failed` — judge 런타임 실패(≥1 후보 judge `None`; mixed insufficient+`None` 포함 — `None`은 verdict가 아니라 엔진 오류).
  - `all_candidates_insufficient` — shortlist는 있었고 judge가 **전원 깨끗이** 돌았으나 verdict=insufficient(엔진 오류 0).
- **stage ordering + 선행 실패 short-circuit**: 평가는 `query-gen → search → judge`의 **엄격한 파이프라인**이다. 앞 단계 실패는 뒤 단계를 **실행하지 않고** 즉시 그 단계의 silence로 종료한다(query-gen 실패 → search·judge 미실행 / search 실패 → judge 미실행). 이로써 뒤 단계(예: 빈 입력에 대한 judge `None`)가 앞 단계 사유를 덮어쓰는 **역전을 원천 차단**하고 불필요한 LLM 호출도 없앤다.
  - (기존 `SilenceView(silent, reason)` 계약 재사용 — `serving.py`, 현행 `"no_candidates"`에 위 사유 추가)
- **"topic discussers fallback" 금지**: stance 미평가 후보를 stance recommendation으로 반환하지 않는다("response never lies"). 관측성은 `silence.reason` + decision log로.
- **serve는 sync 유지, judge/search는 shortlist만 async**: Phase 8-5 `generate_reasons_async`가 top-N만 await하는 shape 재사용.
- **eval**: for/against **verdict 품질은 judge stratum(비결정적)에서만** 측정(8-4 B2 silver judge). 결정적 gate는 배관만(stub judge·stub search: shortlist retrieval·owner-chunk fan-out·single-pass query-gen→search→judge 순서·insufficient→drop·`silence.reason`·non-stance 질의 불변). gate에 judge/실검색 안 넣음.
- **degrade scope (judge)**: `evidence_stmt_ids` firsthand-honesty violation은 기본적으로 해당 candidate만 invalid(→ insufficient/drop). judge 응답 전체 shape이 깨진 경우에만 batch degrade → `stance_judge_failed` silence.
- **degrade scope (search/expansion · whole-request silence)**: Alpha 구현은 **단일 ANY-match batch search**라 "검색 없이 판정 가능한 inline-완결 후보"가 별도로 존재하지 않는다 — 모든 후보가 그 한 번의 배치 검색에 의존한다. 따라서 evidence 수집 leg가 실패하면 그 **요청 전체가 silence**가 된다: symmetric query 생성 실패·한쪽 query 누락은 `stance_query_generation_failed`(검색 미실행), OpenSearch 전체 실패·일부 owner 결과 실패·batch shape 오류는 `stance_evidence_search_failed`. 두 경우 모두 judge 실패(`stance_judge_failed`)와는 계속 구분한다(관측성). (후보 단위 부분 격리는 §D3-future의 inline/2단계 escalation 모델을 실제 도입할 때의 후속.)

### D6. memory-api 계약 (cross-team)

aspect 온톨로지·stance verdict·방향·axis 무엇도 요청하지 않는다. **memory-api는 query-agnostic primitive만** 준다. **유일 신규 계약이었던 §D6-2(statement-search)는 배포 완료** — Tier 1 후보 조회와 provenance 원문 조회는 기존 엔드포인트로 이미 충족(§D6-1·§D6-3). (계약 협의 기준 repo: `bourbon-memory-api` main@`f12e8b2`.)

1. **Tier 1 retrieval — 이미 충족 (신규 변경 없음)**: cross-owner qid-match 엔드포인트가 topic QID→owner pool + competence 랭킹 + limit + `with_statements` 인라인을 이미 제공(§D2). **server-side `has_opinion` 필터는 요청하지 않는다** — hard filter로 부적절(§D2·experiential/procedural 입장 누락)하고, server-side 정렬/필터를 더하면 statement-search 외 memory-api 변경이 하나 더 생긴다. 기존 응답의 `opinion_ratio`는 **Discovery prior로만** 사용.
2. **★ neutral statement-search primitive — 유일 신규 계약 (배포됨)**: QID + shortlist owner 범위에서 **statement `text`를 relevance 검색**하는 API가 없었다 → **`POST /{prefix}/personal/statements/search`로 배포됨**. 기존 statement 인덱스(`memory/knowledge/personal/opensearch.py:42` — `owner_id`·`subject_qid`·`text`(analyzed)·`status`·`statement_kind`·`epistemic`·`confidence`·`provenance` 필드 **이미 존재**)에 얹어 **신규 인덱스·rebuild 없이** 구현.
   - **재사용 불가 근거**: 최근 추가된 `POST /personal/entities/search`는 `owner_ids`+`qids`를 받지만 검색 대상이 **entity label/alias**지 statement text가 아니다(`api/routers/personal/structs.py`·`repository.py:search_entities_for_owner`). 게다가 그 `qids` 필터는 role-tagged grounding 전체(IDENTITY/BROADER/RELATED)를 훑어 exact-QID 1:1도 아니다(§D2). unified `/search`도 conversation/artifact라 QID 제한·statement id 반환·evidence 연결이 안 됨.
   ```text
   POST /{prefix}/personal/statements/search
   { "subject_qids": ["Q8063"], "owner_ids": ["...≤20 per call..."], "queries": ["..."],
     "limit": 20, "per_owner_limit": 40 }   // per-query knob 없음 · active_only 요청 필드 없음(엔드포인트가 active-only)
   // subject_qids = 단일 grounded topic QID를 1-element list로(엔드포인트 scope 계약이 plural).
   // 모든 query를 하나의 ANY-match 배치로 검색 → owner별 top-`per_owner_limit` relevance cap.
   // limit = owner-group 상한 = 이 호출의 owner 수(len(chunk)) — match-count owner truncation이 eligible owner를 못 떨구게.
   // owner_ids는 호출당 ≤20 (초과 shortlist는 Discovery가 owner-chunk로 ceil(K/20)회 fan-out·§D3).
   ```
   - **★ scope 제약 (LOCK · Discovery adapter 정책)**: memory-api **엔드포인트 자체는 permissive**하다 — `subject_qids`/`owner_ids`가 nullable이라 생략 시 **global 검색이 가능**하고 `limit`/`per_owner_limit`에도 기본값이 있다. 반면 **Discovery 어댑터는 안전을 위해** 이를 강제한다: `subject_qids` = 단일 QID를 1-element list로 · `owner_ids` = **eligibility 통과 shortlist(§D2)에서 온 non-empty** 값(≤20/call) · `queries` non-empty(blank 제거) · `limit`·`per_owner_limit` **명시**. 즉 "엔드포인트가 global discovery를 제공하지 않는다"가 아니라 **"엔드포인트는 제공하지만 어댑터가 eligibility 선행 우회를 막기 위해 쓰지 않는다"** — owner_ids를 optional/global로 흘리면 eligibility 불변식을 우회하므로, 이 강제는 client-side 계약이다(네트워크 호출 전에 위반을 reject).
   - **구현 범위 (배포됨)**: request/response DTO · `PersonalRepository.search_statements()`(subject_qids + owner_ids + 항상 active 필터 · `text`에 symmetric queries를 **하나의 ANY-match로 검색 → owner별 top-`per_owner_limit` relevance cap** · owner_ids 호출당 ≤20 · 요청 상한 owner_ids/queries 개수) · **검색 전용 owner-grouped 응답 모델**(기존 `StatementSummary`엔 `owner_id`·`subject_entity_id`가 없어 별도 모델) · repository/router 테스트. (per-query top-F fanout knob은 **미구현** — 아래 recall 계약 참조.) *(Discovery 어댑터는 이 wire 응답을 normalized `StanceEvidenceHit`/`OwnerEvidence`/`StanceEvidenceResult`로 변환 — 아래 매핑.)*
   - **★ score는 응답에 넣지 않는다 (LOCK)**: OpenSearch `_score`는 memory-api **내부에서 owner별 relevance top-K 선정에만** 쓰고, 응답은 **선정된 statement를 relevance 순서로만** 반환(순서가 곧 relevance 신호). BM25 score는 query·corpus **상대값이라 owner 간·요청 간 calibrated가 아님** → 노출하면 stance confidence 오인·owner간/query간 비교·judge 편향을 부른다. 디버깅용은 `with_trace=true` **report-only**로만.
   - **응답 shape (wire · owner-grouped)**: `{ owners: [ { owner_id, statements: [WireStatement], truncated } ], subject_qids, per_owner_limit, limit, truncated }` — **owner별 그룹**으로 반환(후보/judge가 owner별로 evidence를 묶으므로 grouped가 가장 명확; score 숨긴 flat "relevance 순서"가 owner 간 비교로 오해되는 것을 제거). 그룹 내 `statements`는 **owner-내부 relevance 순서**.
     - `WireStatement` = `id`·`text`·`statement_kind`·`epistemic`·`confidence`·`provenance_message_ids`·`subject_entity_id`·`subject_qid`(nullable — ungrounded면 drop) (**score 없음**).
     - **echo 필드**: `subject_qids`·`per_owner_limit`·`limit`는 요청값을 그대로 되돌린다 → 어댑터가 **echo 일치를 검증**(불일치 = 계약 위반 → `stance_evidence_search_failed`).
     - **truncated (2단계, 의미가 다름)**: group `truncated` = 그 owner가 `per_owner_limit`보다 많이 매칭됨 = **recall-risk 신호(report-only·로깅)**, 제어 흐름에 영향 없음(Tier 1.5는 이후 추가 검색/pagination 안 함). top-level `truncated` = 매칭 owner가 `limit`보다 많음 — `limit=len(chunk)`이라 발생할 수 없으므로, **true면 계약 위반으로 간주해 어댑터가 `StanceEvidenceSearchError`를 던진다(→ whole-request silence·§D5)** = control-flow 신호.
     - **Discovery normalized 매핑**: `owners → results`, statement `id → statement_id` · `confidence → statement_confidence`, owner-그룹 → `OwnerEvidence`, 전체 → `StanceEvidenceResult`(`discovery/structs/stance.py`). 이름 분리는 transport shape과 파이프라인을 디커플하기 위함(Plan B port-not-wire).
   - **★ query-direction recall — Alpha의 known open risk (배포된 single ANY-match)**: 배포된 엔드포인트는 **모든 query를 하나의 ANY-match로 검색한 뒤 owner별 top-`per_owner_limit`**를 뽑는다. per-query top-F fanout이 없으므로, support 표현 매칭이 많은 owner에서는 top-`per_owner_limit`가 한쪽으로 채워져 **oppose 매칭이 밀려날 수 있다**(symmetric 검색의 목적과 부분 충돌). 이는 Alpha에서 **구조적으로 방지되지 않은 채 수용된 리스크**다. 현재 완화책은 두 가지뿐: (1) **symmetric + 어휘 강화 BM25 query**(§D3 대칭 생성 + B4 프롬프트 vocab enrichment)로 양방향 recall 폭을 넓히고, (2) Discovery가 **overfetch**(호출당 `limit=len(chunk)`로 match-count owner truncation을 막고 `per_owner_limit`로 owner별 절삭)한다. **근본 완화(server-side `per_query_limit` per-query fanout 또는 semantic escalation)는 이월** — 전용 **stance-evidence recall eval**(아래)의 측정 결과에 gate되며, **기존 결정적 ratchet과는 무관**하다(그 ratchet은 Tier 1 owner recall@K만 측정하지 stance-evidence direction recall을 측정하지 않는다).
   - **owner fairness + active 계약 (acceptance)**: 최대 반환 = `limit × per_owner_limit` (owner-group 수 × owner별 상한). `limit`은 **owner-group 상한**이지 flat result 상한이 아니다 — 어댑터가 `len(chunk)`로 설정하고 응답 echo를 검증한다. global top-N을 먼저 자르고 owner cap을 적용하는 순서 **금지**(owner당 topic entity는 1개[§D2]여도 statement는 여럿이라 statement 많은 owner가 타 owner를 0건으로 밀어냄). owner당 entity 1개[§D2]와 owner별 top-`per_owner_limit`는 **서로 다른 문제를 푸는 별개 계약**. active 필터는 **요청 파라미터가 아니라 엔드포인트에 내장**(항상 ACTIVE만) — invalidated statement 유입 금지.
   - **호출 계약 (배포됨)**: 엔드포인트가 `owner_ids`를 호출당 ≤20으로 제한하므로 Discovery는 **owner-chunk당 1회 = 요청당 `ceil(K/20)`회** 호출한다(bounded-concurrency·disjoint chunk concat merge·§D3). server 내부는 "단일 OpenSearch query"가 아니라 chunk별 **단일 bounded batch operation — owner별 N+1 호출 금지**(`_msearch`·query fanout 구현 허용). "owner 독립"은 relevance selection 의미론이지 backend N회 호출이 아니다.
   - **★ 실패 계약 (error taxonomy split)**: 이 엔드포인트의 모든 실패 — transport 오류 · non-2xx(429/503 throttle 포함) · 계약 위반 body(schema drift·`subject_qids` echo 불일치·불가능한 top-level `truncated`) — 는 Discovery 어댑터에서 `StanceEvidenceSearchError`로 올라가 **`stance_evidence_search_failed` silence**로 격리된다(§D5). **한 chunk라도 실패하면 검색 전체를 실패로 본다**(partial recall이 verdict를 뒤집을 수 있으므로). 이 어댑터는 `UpstreamUnavailableError`(=미배선)를 던지지 않는다 — AF4가 배선한 뒤로 unwired 상태가 없다.
   - **왜 neutral 검색 primitive인가(ownership)**: 무엇이 stance-bearing인지는 **query-relative** 지식이라 memory-api가 알면 경계 침범. memory-api는 **QID-bound BM25 검색**만, expansion 쿼리(stance-relative)와 evidence 선택은 **Discovery 에이전트**가 소유(§D3).
   - **기각한 대안**: memory-api 무변경 + owner마다 `GET /entities/{qid}/statements` 호출(Discovery 전량 검색) = 후보 수만큼 N+1 · owner당 최대 200 · relevance 검색 없음 · dense owner recall 미보장 → bounded batch Tier 1.5와 불합치.
3. **provenance 원문 조회 — 이미 있음 (신규 계약 불필요)**: `POST /{prefix}/conversations/messages/lookup`(최대 200 · context 확장 · **PII clearance** 지원 · `api/routers/conversations/router.py:515`)로 `provenance_message_ids`를 원문 dereference 가능. → support_snippet용 별도 계약 불필요; judge가 summary로 부족할 때(반어·인용·부정) 이 엔드포인트로 원문 확인(**§D2 eligibility 선행** — 어떤 owner의 provenance를 조회할지가 owner disclosure scope 통제점). `support_snippet`을 statement-search 응답에 inline하는 건 순수 latency 최적화(선택). ⚠️ **disclosure 검증은 Discovery 책임 (acceptance)**: `messages/lookup`은 PII clearance는 적용하나 `owner_id`/discoverability scope는 받지 않으므로(신규 memory-api 계약은 불필요), Discovery 테스트로 불변식 고정 — **`lookup_message_ids ⊆ eligible candidate들의 judge input provenance IDs`**. 임의 message id나 eligibility 이전 statement의 provenance가 lookup으로 넘어가지 않게.

**ownership 경계 요약**: memory-api = QID-bound neutral 검색(신규·§D6-2) · grounding · metadata · provenance 원문(기존 `messages/lookup`). Discovery = query expansion · evidence 선택 · eligibility gate · need_type 방향 필터 · 추천 (verdict는 judge가 proposition-absolute로 생성). judge = stance verdict. statement-search는 relevance **순서만** 제공(score 미노출·§D6-2) — recall 신호일 뿐 stance confidence 아님.

## 5. Open items (다음 결정)

- **K / M / per_owner_limit / batch shape + K recall 안전장치**: Tier 1 shortlist 크기(K), inline preview 상한(M), 검색 owner당 상한, per-candidate vs 소배치. **K는 전체 recall 상한이므로(§D2)** — **overfetch-후-축소 + recall@K ratchet**으로 고정(eligible-pagination은 `Page`에 cursor/offset 없어 배제).
- **bounded 한계값**: Alpha는 재검색 loop 없이 owner-chunk fan-out(`ceil(K/20)`) + `per_owner_limit`로 상한이 정해진다(post-judge retry는 §D3-future로 이월). 이월 시 결정할 값: 최대 검색 호출·재판정 횟수.
- **★ stance-evidence recall eval + 관측성 갭 (server 격상의 선결)**: 현재 **stance-evidence direction recall을 측정하는 메트릭이 없다** — 기존 결정적 ratchet은 Tier 1 owner recall@K만 본다(§D2). 배포된 single ANY-match의 oppose-crowding 리스크(§D6-2)와 B4 vocab enrichment의 개선 효과는 **전용 recall eval**로만 객관 측정 가능하다. 따라서 순서 = **① 전용 recall eval 구축 + 현 프롬프트 baseline 측정 → ② B4 vocab enrichment → ③ 동일 eval로 개선 측정 → ④ 결과에 따라 server-side `per_query_limit`(per-query fanout)/semantic escalation 필요성 판단**. prompt를 eval보다 먼저 바꾸면 baseline 비교가 불가능하다. server 변경은 이 eval에 gate되며 **기존 ratchet과 무관**.
- **silence.reason 최종 taxonomy**: 위 6종(`stance_judge_disabled`/`_unavailable`/`stance_query_generation_failed`/`stance_evidence_search_failed`/`stance_judge_failed`/`all_candidates_insufficient`) + 기존 `no_candidates` 중복 정리(serving 계약).
- **multi-proposition 결합 의미론**: 질의에 명제 여러 개일 때 AND 전부일치 / coverage 부분일치 / round-robin. Alpha single이면 이월.
- ~~옵트인 파라미터 최종 이름 + statement-search 응답 필드 확정~~ **(배포됨)**: request = `subject_qids`·`owner_ids`(≤20/call)·`queries`·`limit`(=len(chunk))·`per_owner_limit`, **per-query knob 없음 · active_only 요청 필드 없음**(엔드포인트가 active-only); 응답 = owner-grouped(`owners[].statements[].{id,confidence,…}`)·echo(`subject_qids`/`limit`/`per_owner_limit`)·`truncated`(2단계)·**score 미노출**. Discovery는 `StanceEvidenceHit`/`OwnerEvidence`/`StanceEvidenceResult`로 normalize. per-query fanout 재도입은 위 recall eval에 gate.
- **confidence 명명 분리**: `statement_confidence`(claim 단위 = 발화자 귀속 신뢰도; 진위·요약 정확도·stance 강도 아님), `competence.*`, judge `graded_confidence`(= 사실상의 stance confidence), BM25 `_score`(recall 신호). 같은 `confidence` 이름 재사용 금지.
- **extraction 프롬프트 강화는 recall 측정 뒤로 gate (memory-api 소유·高 blast radius)**: 현 `text` 계약은 negation/modality/조건/시점/지역·atomic multi-proposition split·quoted-opinion 비변환·stance-holder 명시를 강제하지 않아 recall·correctness 갭(예: "원전 반대하지만 폐쇄 전까지 안전규제 강화"가 1문장 압축·조건 소실; "loved The Martian"처럼 주어 생략 짧은 요약은 검색 recall 부족). 단 프롬프트 변경 = `PIPELINE_VERSION` 범프 = 전 owner FULL rebuild + eval 재baseline. → **현재 text로 Tier 1.5 recall을 먼저 측정**하고 병목일 때만 강화. 최우선 2개: multi-proposition atomic split(recall/precision), quoted-opinion을 owner 입장으로 변환 금지(correctness — 인용된 타인 입장을 owner로 오추천 방지·`confidence`=0.7 other-engaged 신호와 연동하되 하드 필터 아님). Alpha와 디커플.

## 6. Phase 10 정합

이 설계는 Phase 10(competence/groundings → AgentTopicEdge 투영 + translation layer)의 stance 축을 구체화한다. 진짜 갭 "eligibility + stance + evidence-ref 노출" 중 **stance·evidence-ref**를 다룸(eligibility는 별도 트랙). **이 작업은 독립 phase가 아니라 Phase 10의 stance 슬라이스** — 단 memory-api **neutral statement-search 엔드포인트**(§D6-2) 계약 협의는 lead-time상 먼저 킥오프하고, verdict 품질 검증은 **8-4 B2 silver judge** stratum에 의존한다.

## 7. 폐기 이력 — verdict caching (deferred, no axis_id)

axis_id registry(§2b)를 폐기하며 함께 사라지는 것: `axis_id` mint, axis lifecycle/promotion/merge, verdict materialization, 그리고 그것이 요구하던 **freshness 계약(memory-api `statement_revision`)**. Alpha는 반복 query도 매번 live judge(내부·저볼륨이라 수용). 나중에 query 볼륨이 실제 비용 문제가 되면 verdict 캐시를 **순수 최적화로** 재도입할 수 있으나 — (a) `axis_id` 없이 `(topic_qid + ephemeral proposition hash + entity + judge_version)` 키로, (b) freshness는 "판정에 쓴 evidence"가 아니라 **entity/topic 전체 active-statement 상태**(monotonic revision 또는 변경 event)로 검증, (c) freshness 계약이 닫히기 전엔 serving 금지 — 를 전제한다. 이전 설계 전문은 git 이력에 있다.
