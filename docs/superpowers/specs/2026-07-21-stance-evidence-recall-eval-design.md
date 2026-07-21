# Stance-evidence recall eval — design

**날짜:** 2026-07-21
**관련:** [[2026-07-20-agentic-stance-retrieval-design]] §D3(symmetric query·lexical scaffold)·§D6-2(single ANY-match·owner-cap crowding known risk)·§5(recall eval가 server per_query_limit/semantic 격상 gate). 이 문서는 그 §5 "전용 stance-evidence recall eval"을 구체화한다.
**기준 코드:** `bourbon-agent-recommendation-api` `feat/agentic-stance-retrieval`(AF1–AF5 완료). 평가 하네스=Phase 6 corpus / Phase 7 metrics·gate 위에 얹되 **별도 opt-in 하네스**.

---

## 1. 문제 · 범위

AF-final의 stance retrieval은 **single ANY-match + owner-chunk fan-out**으로 배포됐고(§D6-2), symmetric query는 방향을 판정하지 않는 **lexical recall scaffold**다(§D3). 여기서 두 가지가 관측되지 않는다: (a) **어휘 불일치**(요약 text가 검색어와 안 걸림), (b) **owner-cap crowding**(한쪽 polarity가 owner top-`per_owner_limit`를 점유해 반대편 evidence가 밀려남). 기존 결정적 gate의 `retrieval_recall_easy_needle`는 pre-gate **agent** recall이지 **statement** recall이 아니며, 오프라인 fake(`FakeStanceEvidenceSearch`)는 매칭을 모델링하지 않는다.

**이 eval의 목적:** "올바른 support/oppose statement가 **judge 입력까지 도달했는가**"를 측정 — **retrieval recall만**.

**Non-goals (명시):**
- judge 정확도(verdict 옳음)·ranking·serving·silence 동작 — **실제 LLM judge는 실행하지 않는다**(evaluator를 통과시키되 `RecordingStanceJudge`가 입력만 캡처·§2.1).
- 어휘 강화 프롬프트(AF-prompt)의 개선을 **객관적으로 비교**하고, server-side `per_query_limit`(per-query fanout)/semantic search 격상 여부를 **판정**하는 근거를 만든다. 판정 근거 제공이 목적이지, 격상 자체는 별도 결정.

**실행 성격 (정확히):**
- **일반 `eval stance-recall run` = network-only** — 커밋된 query snapshot을 읽어 실 memory-api를 때린다. **LLM 미호출**.
- **`eval stance-recall refresh-queries` = network + LLM** — real query generator를 돌려 새 snapshot을 만든다(유일한 LLM 경로·측정과 분리된 별도 커맨드·§5.2).
- **오프라인 deterministic gate(`eval gate`)와 완전 분리** — byte-identical·무네트워크 gate에 절대 포함하지 않는다. import-isolation(discovery/·api/ ↛ eval) 불변.

### 1.1 구현 경계 (이번 단계 · writing-plan 전 고정)
- **이번 구현(cross-team 계약 불필요):** corpus/GT 포맷·loader·`SnapshotStanceQueryGenerator`·`RecordingStanceJudge`·runner·단일-query 진단·metrics·manifest, 전부 `httpx.MockTransport` 유닛 테스트까지. **network 실행 경로(코드)는 compile·test 가능**.
- **cross-team 계약(§11) 전 blocked:** ① seed backend(tenant ingestion) ② run 시작 시 **tenant corpus-hash 조회**(§4-6) — 둘 다 memory-api 신규 계약 의존. 따라서 **실제 baseline 산출과 live tenant 대상 opt-in smoke는 계약 전에는 불가**. 정확한 표현: *"network 실행 경로는 compile/test 가능하지만 실제 baseline 산출은 seed+hash 계약에 blocked"*.
- **seed CLI 결정:** 서브커맨드 **port만 만들고**(surface·args 확정), 백엔드가 없으므로 호출 시 **명시적으로 unavailable 처리**(`seed backend pending cross-team contract §11`로 loud fail — repo의 Unavailable* stand-in 선례와 일관). 이월이 아니라 "port 존재 + 명시적 미가용"으로 둬 CLI 표면을 일관되게 유지.

---

## 2. 평가 단위 · 측정 지점

- **평가 단위** = `(topic_qid, proposition, owner_id)`.
- **파이프라인(측정 경로):** 동결 query snapshot → 실 memory-api `POST /{prefix}/personal/statements/search`(owner-chunk fan-out·실 BM25) → real `_admit`(owner·shortlist·subject_qid 검증 + statement_id dedup) → judge에 전달되는 `by_owner`. **judge LLM 미실행.**
- **측정 지점 = production evaluator가 judge에 넘긴 정확한 statement 집합.** query-gen 결과가 실제 검색을 통과한 직후, judge 이전.

### 2.1 `_admit` public 노출 없이 캡처 (LOCK)

`discovery/stance.py`의 `_admit`/`_collect_evidence`를 eval용으로 public화하지 **않는다**. 대신 eval 쪽에 두 stub을 두고 **real `StanceEvaluator.evaluate()`를 그대로 통과**시킨다:

- **`SnapshotStanceQueryGenerator`** (duck-types `StanceQueryGenerator`): LLM 대신 **해당 eval case의 K번째 표본 queries**(`StanceQueries` — neutral/support/oppose 세 리스트, symmetric)를 반환. snapshot 파일은 all-case(§5)이고 **runner가 `(case, sample_k)`마다 그 case에 바인딩된 generator**를 만든다(한 `evaluate()` 호출 = 한 case). `generate()`는 네트워크·LLM 없이 즉시 반환.
- **`RecordingStanceJudge(expected_owner_ids=[...])`** (duck-types `StanceJudge`): `judge(proposition, statements)` 시그니처엔 **`owner_id`가 없다** — `statements`가 비면(= 완전 miss) hit로 owner를 알 수 없어, **가장 중요한 완전 miss가 잘못 귀속**될 수 있다. evaluator가 **candidate 순서대로 순차 judge**한다는 계약을 이용해 다음을 고정한다:
  1. 생성 시 `expected_owner_ids` = candidates 순서의 `edge.agent_id` 큐를 받는다.
  2. **호출마다 다음 expected owner를 consume**하고, 그 owner의 judge 입력으로 `statements`를 기록.
  3. non-empty `statements`면 **hit들의 `owner_id`가 그 expected owner와 일치하는지 검증**(순서 계약 위반 시 loud fail).
  4. **empty list도 그 expected owner의 빈 judge 입력으로 기록**(완전 miss가 정확히 그 단위에 귀속).
  5. 종료 완전성 검증은 **runner가 evaluation 결과로 분기**(§9): search/query-gen 실패 시 evaluator는 judge를 **아예 호출하지 않고** pre-judge failure evaluation을 반환하므로, 큐가 소진되지 않는 것이 정상이다. 따라서 정상 evaluation일 때만 **호출 수 == `len(expected_owner_ids)` + 큐 소진**을 요구하고, pre-judge failure면 **`judge_calls == 0`**을 요구한다. (RecordingJudge 자신은 큐/호출을 기록만 하고, 완전성 판정은 runner가 `StanceEvaluation.silence_reason`을 보고 내린다.)
  6. 모든 호출에 `StanceVerdict(verdict=insufficient, …)` 반환(LLM 미호출).
  이 **순서 의존성은 테스트로 고정**한다(evaluator가 candidate 순서대로 judge함을 pin — 계약이 깨지면 red).

이렇게 하면:
- **검색·scope guard·dedup을 전부 실제 경로**(real `HttpStanceEvidenceSearch` + real `_admit`)로 검증한다.
- judge에 도달한 statement 집합을 **정확히** 캡처한다(RecordingJudge가 받은 `statements`가 곧 judge 입력).
- judge가 전원 `insufficient`를 반환하므로 `evaluate()`는 clean하게 끝난다(silence=`all_candidates_insufficient`) — eval은 `StanceEvaluation` 출력이 아니라 **RecordingJudge가 기록한 집합**을 소비한다.
- eval-전용 API 표면(`_admit`/`_collect_evidence` 노출)을 새로 만들지 않는다.

### 2.2 단일-query 진단 경로

crowding/lexical 분류(§6)를 위해 **각 query를 개별로** 검색한다. 단일 query는 symmetric이 아니라 `evaluate()`에 부적합하므로, 진단은 **public Protocol의 `HttpStanceEvidenceSearch.search(subject_qid, owner_ids, queries=[q], per_owner_limit=<진단값>)`을 직접 호출**하고 반환 hit에 GT id가 나타나는지만 본다(membership 판정이므로 admit/dedup 불필요). production 측정(`evaluate()`)과 진단(`search()`) **둘 다 `_admit`을 건드리지 않는다**.

---

## 3. Corpus · GT (큐레이션 합성 · 커밋)

### 3.1 구조
실제 wire hit(`StanceEvidenceHit`)과 evaluator 입력(`Candidate`/`edge`·`NormalizedQuery`)을 **실제 경로로** 만들 수 있어야 하므로, corpus는 3층으로 커밋한다:

- **eval case** — `{ case_id, topic_qid, topic_text, proposition, owner_ids: [...] }`. 한 case = 한 `evaluate()` 호출. `owner_ids`는 그 case의 shortlist(= Candidate 세트).
- **statement** — `{ statement_key, case_id, owner_id, subject_qid, subject_entity_key, text (영어 요약형), statement_kind, epistemic, confidence, provenance_message_ids }`.
  - `text`는 build 시점 LLM extractor의 **영어 요약형**을 모사(원문 발췌 아님·§D6-2 note).
  - `subject_entity_key` = 안정 fixture 키 → 시딩이 실제 `subject_entity_id`로 매핑(§4). `StanceEvidenceHit`의 wire-required 필드(`subject_entity_id`·`provenance_message_ids`)를 채우기 위함.
- **GT** — `(topic_qid, proposition, owner_id) → { statement_key: supports | opposes }`. corpus와 **함께 커밋**. `statement_key`는 fixture 안정 키(§4에서 실제 memory-api statement id로 매핑).

> ⚠️ **`case_id`는 fixture bookkeeping 전용 — 검색 격리 필드가 아니다.** memory-api는 `case_id`로 필터링하지 않으므로, **같은 `(owner_id, subject_qid)`를 공유하는 다른 case의 statement도 검색에 함께 들어온다**. 격리는 오직 `(owner_id, subject_qid)`로만 이뤄진다. corpus 작성자는 case 독립성을 가정하면 안 되며, cross-case 오염을 피하려면 case마다 **distinct owner/QID**를 쓰거나 GT가 cross-case statement를 감안해야 한다.

**Candidate/edge fixture 구성 (LOCK):** runner는 각 case의 `owner_ids`로 **최소 `Candidate`(edge.agent_id=owner)** 세트와 topic_qid를 담은 `NormalizedQuery`(need_type=FOR/AGAINST·proposition)를 만들어 `evaluate()`에 넣는다. `_admit`이 검증하는 값(hit.owner_id ∈ shortlist·hit.subject_qid == case.subject_qid)이 실제 corpus/시딩과 일치하도록 고정한다. edge의 나머지 필드는 stance recall과 무관하므로 최소 stub(Alpha owner-only 계약).

### 3.2 의도적 strata (실패 원인 분리 가능하게)
1. **support/oppose 동의어·우회 표현** — 방향별 lexical 다양성.
2. **same-topic·stance 무관** — 같은 QID지만 입장 없는 배경/사실 statement(precision 잡음).
3. **prolific owner crowding** — 한쪽 polarity가 owner의 top-`per_owner_limit`를 점유하도록 대량 statement 배치(반대편이 밀려나는지).
4. **한국어 원문 → 영어 요약형** — cross-language 요약 recall.
5. **조건부·부분 입장 & 배경 사실** — "반대하지만 X까지는 찬성" 류.
6. **lexical mismatch와 owner-cap crowding을 각각 독립 재현** — 한 시나리오는 한 실패 모드만 자극하도록 설계(원인 분리).

### 3.3 이월
- 실 데이터 스냅샷 라벨링 = 하네스·지표가 안정된 뒤 **2차 현실성 benchmark**로 추가(프라이버시·데이터 변동·라벨 모호성 때문에 초기엔 프롬프트 개선과 corpus 노이즈를 못 가른다).

---

## 4. 시딩 계약 (seed / run 분리 · deterministic)

시딩은 **일반 run과 분리된 명시적 단계**다. 일반 run이 tenant를 자동 reset/삭제하면 오조작 위험 + 시딩 실패와 retrieval 실패를 못 가른다.

```
eval stance-recall seed --tenant stance-eval     # 시딩(별도·명시)
eval stance-recall run  --tenant stance-eval     # 측정(시딩 안 함)
```

**시딩 계약 (LOCK):**
1. **전용 tenant guard (강함)** — 시딩/reset은 **허용 목록의 eval 전용 tenant에만**. production/실 tenant 이름이면 **즉시 거부**(오조작 방지).
2. **extraction LLM 재실행 금지** — 커밋된 statement `text`/metadata를 **그대로 적재**(요약 재생성 안 함 → corpus 결정성 보존).
3. **안정 ID 매핑** — 시딩이 `statement_key → 실제 memory-api statement id` **및** `subject_entity_key → 실제 subject_entity_id` 매핑을 **반환·기록**(또는 결정적 id 부여). GT/hit 대조는 `statement_key` 기준, wire hit의 `subject_entity_id`는 `subject_entity_key` 매핑으로 채움. run이 이 매핑으로 실제 id와 대조.
4. **reset 후 OpenSearch refresh barrier** — 시딩 완료 = 인덱스가 검색 가능해질 때까지 대기(refresh 완료 확인). barrier 없이 run하면 부분 인덱스로 거짓 miss.
5. **corpus hash를 tenant metadata에 기록** — 시딩한 corpus의 hash를 tenant에 남긴다.
6. **run 시작 시 hash 검증** — run이 **기대 corpus hash vs tenant 실제 hash**를 대조, 불일치면 **loud fail**(stale/오염 tenant로 측정 방지).

### 4.1 tenant binding (LOCK · 측정 대상 정확성)
`HttpStanceEvidenceSearch.from_settings()`는 `MEMORY_API_PREFIX`를 prefix로 쓴다(`discovery/providers/statement_search_http.py`). CLI가 받은 `--tenant`로 corpus hash를 검증하면서 검색 client가 **설정의 다른 prefix**를 쓰면 **다른 tenant를 측정**하게 된다. 방지:
- **`--tenant` 하나가 seed guard · hash lookup · statement-search prefix 모두의 single source of truth.**
- eval runner는 **`from_settings()`를 그대로 쓰지 않는다** — base URL/timeout/limits 등만 설정에서 읽되 **`prefix = validated_cli_tenant`로 `HttpStanceEvidenceSearch`를 직접 구성**(생성자가 `prefix` 인자·tenant 정규식 검증 보유).
- manifest에 **실제 요청 tenant 기록**.
- **`MEMORY_API_PREFIX`로 조용한 fallback 금지** — CLI tenant와 search path prefix 일치를 **테스트로 고정**.

**cross-team 선결:** tenant ingestion 경로 **및 tenant corpus-hash 조회**(위 5·6)는 memory-api 소유의 신규 계약이다. 설계는 corpus+하네스+시딩 계약을 지금 확정하고, **ingestion/hash 엔드포인트는 문서화된 선결 조건(cross-team 티켓·§11)**으로 둔다. 이번 단계에서 seed CLI는 **port-only + 명시적 unavailable**(§1.1), 실제 baseline은 계약 후. dev memory-api에 시드+hash 계약이 서면 하네스 실행 가능.

---

## 5. Query snapshot 정책 (프롬프트 버전 × K 표본 동결)

query generator 입력은 `(topic, proposition)`이므로 **한 표본 파일은 단일 `StanceQueries`가 아니라 모든 eval case의 결과를 담는다.**

### 5.1 snapshot 파일 포맷 (all-case · identity-hashed)
`queries_<promptver>/sample_01..K.json`, 각 파일:
```json
{
  "schema_version": 1,
  "prompt_identity": { "prompt_hash": "...", "schema_hash": "...", "model": "...", "generator_commit": "..." },
  "cases": {
    "case_nuclear_expansion": {
      "topic_text": "nuclear power",
      "proposition": "nuclear generation should be expanded",
      "queries": { "neutral_queries": [], "support_queries": [], "oppose_queries": [] }
    }
  }
}
```
- **prompt version은 수동 문자열만으로 부족** — `prompt_identity`(prompt/schema/model/generator_commit **hash**)로 표본의 출처를 고정한다. run/manifest가 이 identity를 기록·검증.
- **loader는 corpus의 case 집합 == snapshot의 case 집합**을 **정확히** 검사(누락/잉여 case면 loud fail). 각 case의 `queries`는 유효한 symmetric `StanceQueries`.

### 5.2 refresh / run 분리 (artifact 생성 ≠ 측정)
seed/run 분리 원칙과 맞추어 **refresh를 별도 커맨드**로 둔다(§8):
- **`eval stance-recall refresh-queries --prompt-version <ver>` (유일한 LLM 경로):** real `LLMStanceQueryGenerator`를 **case × K회** 실행. invalid case가 섞인 sample_k는 loader의 all-case/symmetric 계약을 못 지키므로, 완성 계약을 명시한다:
  - **case마다 K개의 유효 snapshot**을 생성한다.
  - invalid/asymmetric generation은 **명시적으로 카운트 + bounded retry**(같은 case 재시도).
  - **`max_attempts` 초과 시 refresh 전체 실패**(부분 결과 커밋 금지).
  - refresh report에 **attempts · invalid count/rate 기록**(조용한 재시도로 prompt 안정성 문제를 숨기지 않음 — 관측 대상).
  - **모든 case × K가 완성된 뒤에만 snapshot 디렉터리를 atomic publish**.
  - 기존 버전 overwrite는 **명시적 `--force` 없이는 거부**.
  → retrieval recall은 **유효 query 조건**에서 측정하면서 prompt 안정성도 별도로 노출.
- **`eval stance-recall run` (network-only):** **커밋된 snapshot만** 읽음 → LLM 비용 0.
- **라이브 K-sample:** 주기적 prompt **안정성 점검용 report-only** 별도 모드(기본 경로에서 제외).

### 5.3 recall 집계 · 재현성
- recall은 고정 K개 표본에 대해 **mean / min / max**(K개에 LLM 비결정성 포함).
- **재현성 계약 = "입력이 replayable하고 환경 drift를 manifest로 추적"** — corpus·query가 동결돼도 OpenSearch의 **동점 문서 순서·segment 상태** 때문에 **byte-level 결정성은 보장하지 않는다**. manifest(§7)가 memory_api_commit·OpenSearch 버전/설정·corpus hash·prompt_identity를 남겨 재현 조건을 고정한다.

---

## 6. 지표 (recall 전용)

모든 지표는 K표본에 대해 **mean / min / max**로 집계.

### 6.1 recall 분모 — micro + macro (둘 다 필수)
- **micro recall** — 전체 GT statement 기준(∑recalled / ∑GT).
- **macro recall** — `(topic_qid, proposition, owner_id)` 단위 recall의 평균.
- micro만 두면 **prolific owner가 전체 지표를 지배**하므로 반드시 둘 다 보고.

### 6.2 방향별 · 양쪽
- **support recall / oppose recall (분리)** — crowding 비대칭이 핵심.
- **both-sides recall** — owner가 support·oppose를 **둘 다** 가진 단위에서 **양쪽 ≥1씩** recall된 비율(symmetric 목표 직접 측정).

### 6.3 miss 3분류 (LOCK · 명명 고정)
각 GT statement를 정확히 하나로 분류:
- **`batch_recalled`** — production ANY-match@`per_owner_limit`(=40)의 `by_owner`에서 recall.
- **`single_query_recoverable`** — batch에서는 miss지만 **단일-query 진단 중 하나**에서 recall. → **ANY-match dilution / cross-query crowding의 강한 증거.**
- **`unresolved_miss`** — 단일-query 진단에서도 miss. → **lexical mismatch 또는 single-query 내부 cap crowding**(둘을 합쳐 표현). **진짜 lexical miss로 단정하지 않는다** — 개별 query에서도 top-`<진단값>` 밖으로 밀렸을 수 있다. 순수 lexical miss 확정에는 **uncapped rank/trace 또는 semantic 비교**가 필요(이월).

> 주의: "어떤 query에도 안 나오면 lexical miss"는 **틀림** — 그래서 `unresolved_miss`라는 합성 라벨을 쓴다.

### 6.4 진단 파라미터
- 단일-query 진단 검색의 `per_owner_limit`은 **엔드포인트 ceiling(50)**까지 올려 single-query 내부 cap 영향을 줄이되, 그래도 밀릴 수 있음을 `unresolved_miss` 정의가 흡수.

---

## 7. Baseline · compare · CLI

**baseline + report + compare는 지금, 자동 ratchet은 이후.**

- **baseline (단계 구분 · §1.1과 정합):** 실제 baseline 산출은 seed+hash 계약에 blocked이므로:
  - **지금:** baseline/report/compare **기능**과 현재 prompt의 K snapshot을 **준비**(코드+snapshot artifact). 실측 수치는 아직 없음.
  - **cross-team 계약 직후:** 고정 tenant에서 **첫 실제 결과를 baseline artifact로 publish**.
  - **ratchet:** 반복 안정성·분산 확인 후.
- **`compare <verA> <verB>`:** **같은 tenant 상태 + 같은 memory-api/OpenSearch 버전에서 연속 실행**(A run → B run 인접, 환경 고정). **pairing 단위 주의**: `vA/sample_01`과 `vB/sample_01`은 **독립 LLM 표본이라 직접 pairing 금지**. 각 version에서 **case별 K 평균을 먼저 계산**한 뒤, **동일 eval case 단위로 A/B delta**를 pairing한다. AF-prompt 개선량은 이 case-단위 delta로 판정.
- **자동 ratchet/CI gate는 이후** — 지표 안정성과 반복 실행 분산을 먼저 확인한 뒤 threshold 추가. `eval gate`의 결정적 ratchet과는 **별개**.

### CLI 표면
```
eval stance-recall seed            --tenant <eval-tenant>                      # network (ingestion) — port-only, unavailable until cross-team 계약(§1.1/§11)
eval stance-recall refresh-queries --prompt-version <ver> [--force]            # network + LLM (new snapshot·atomic publish)
eval stance-recall run             --tenant <eval-tenant> --prompt-version <ver>   # network-only — real 실행은 seed+hash 계약 후(§1.1)
eval stance-recall compare         --tenant <eval-tenant> <verA> <verB>        # case-단위 paired delta (실패 표본 있으면 non-zero/publish 금지·§9)
```
- run은 시작 시 corpus hash 검증(§4-6), 종료 시 **manifest** 기록.
- **manifest** 필드: `memory_api_commit` · OpenSearch 설정/버전 · corpus hash · `prompt_identity`(prompt/schema/model/generator_commit hash) · 사용된 생성 query(표본별) · owner별 반환 statement id · cap/truncation 정보 · 계산된 지표(micro/macro/방향별/both-sides/3분류, mean/min/max).

---

## 8. 코드 레이아웃 · isolation

- `eval/stance_recall/` — corpus/GT 포맷·loader·`SnapshotStanceQueryGenerator`·`RecordingStanceJudge`·runner·단일-query 진단·metrics·manifest.
- `eval/corpus/fixtures/stance_recall/` — 커밋 corpus + GT + `queries_<promptver>/sample_*.json` + baseline artifact.
- `cli/eval.py` — `stance-recall` 서브커맨드(`seed`[port-only]·`refresh-queries`·`run`·`compare`) 추가.
- **오프라인 gate 불변:** `EdgeMirrorStanceEvaluator`(harness.py) 그대로. 이 하네스만 real `HttpStanceEvidenceSearch`를 쓴다.
- import-isolation fitness(discovery/·api/ ↛ eval)는 그대로 통과 — 새 코드는 전부 `eval/` 아래.

---

## 9. 에러 처리 · 경계

- **seed 실패 vs retrieval 실패 분리** — 자동 reset/seed 금지(§4). run은 시딩된 tenant를 전제, hash 불일치면 retrieval을 시도하지 않고 loud fail.
- **tenant guard** — eval 전용 tenant 허용 목록 밖이면 seed/reset 거부.
- **★ 실패 표본 정책 (LOCK · baseline 정직성):** 성공 표본만 평균내면 upstream 실패가 recall 지표에서 사라지므로 명시한다:
  - **pre-judge failure**(`stance_evidence_search_failed`/`stance_query_generation_failed`) evaluation → 그 `(case, sample)`을 **retrieval 측정 실패로 기록**하고 `judge_calls == 0` 검증(§2.1). recall 분자/분모에 **성공으로 섞지 않는다**.
  - **단일-query 진단 실패**(§2.2) → 해당 GT를 `unresolved_miss`로 분류하지 **않고** **diagnostic failure로 기록**(3분류 오염 방지).
  - **baseline/compare**: 실패한 case/sample이 **하나라도 있으면 불완전 결과** → **non-zero 종료 AND baseline/compare artifact publish 금지**(둘 다·부분 평균을 정상 지표로 publish하는 구현 차단). 실패 진단용 manifest는 별도 **`incomplete=true`**로 저장 가능(디버깅용, 정상 baseline 아님).
- **snapshot 부재/버전 불일치** — 커밋된 snapshot이 없거나 `prompt_identity`/case 집합이 corpus와 불일치하면 run은 **명시적 에러**(조용한 빈 측정 금지). 새 snapshot은 `refresh-queries`로만 생성.

---

## 10. 테스트 전략

- **오프라인 유닛(네트워크 0):** `SnapshotStanceQueryGenerator`(all-case 파일 로드·case별 K표본·symmetric)·metrics(micro/macro/방향별/both-sides/3분류 계산)·manifest 직렬화·corpus/GT loader(case 집합 == snapshot case 집합 검사)·tenant guard(허용 목록 밖 거부)·hash 검증(불일치 loud fail). 실 memory-api는 `httpx.MockTransport`로 wire 응답 모사.
- **★ `RecordingStanceJudge` 순서 계약 테스트(구현 전 고정):** expected owner 큐를 candidate 순서로 consume·non-empty hit owner 불일치 시 loud fail·**empty list도 그 expected owner에 귀속**(완전 miss 정확 귀속). **완전성 분기 둘 다 테스트**: (a) 정상 evaluation → 호출 수==큐 길이+큐 소진, (b) pre-judge failure(search/query-gen 실패) evaluation → **`judge_calls == 0`**(큐 미소진이 정상, retrieval 측정 실패로 기록). evaluator가 candidate 순서대로 judge함을 pin.
- **3분류 로직 테스트:** batch hit set + 단일-query hit set을 fixture로 주입해 `batch_recalled`/`single_query_recoverable`/`unresolved_miss` 분기 고정.
- **통합(opt-in·네트워크):** dev memory-api에 시드된 tenant 대상 smoke — CI 결정적 gate에서 **제외**, 수동/주기 실행.
- **재현성 확인(byte-level 아님):** 같은 snapshot+tenant 재실행이 manifest 고정 환경(memory_api_commit·OpenSearch 버전·corpus hash)에서 **동일 입력을 replay**함을 확인 — OpenSearch 동점/segment 때문에 결과 byte-동일은 요구하지 않고 지표 분산을 report.

---

## 11. Open items (이후 결정)

- **tenant ingestion + corpus-hash 계약** — memory-api cross-team 계약(전용 tenant·extraction 재실행 금지·안정 statement/entity id·OpenSearch refresh barrier·corpus hash를 tenant metadata에 기록·**run이 조회·검증할 hash lookup**). seed 커맨드의 실제 백엔드이자 run의 hash 검증 근거 — 이 계약 전까지 실제 baseline·live smoke는 blocked(§1.1).
- **순수 lexical-miss 확정** — `unresolved_miss` 세분화(uncapped rank/trace 또는 semantic 비교)는 이후.
- **자동 ratchet/CI threshold** — 반복 실행 분산 측정 후.
- **2차 현실성 benchmark** — 실 데이터 스냅샷 hand-label.
- **prompt 안정성 report-only 라이브 K-sample** 운영 주기.
