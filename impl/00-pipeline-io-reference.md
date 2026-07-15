# 00. 파이프라인 I/O 참조 — 단계별 input → 처리 → output

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[03. normalize+linker](03-normalize-and-linker.md) · [04. retrieval](04-retrieval.md) ·
[05. gate+ranking](05-gate-and-ranking.md) · [06. serving+decision-log](06-serving-and-decision-log.md)

이 문서는 `RecommendationPipeline.recommend(query)` 한 콜이 거치는 **7단계를 데이터 계약 관점**으로
정리한 빠른 참조입니다. 각 단계를 **INPUT → 처리 → OUTPUT** 한 틀로 보여주고, rung으로 나뉜 ① linker는
rung별로 쪼갭니다. "왜 이렇게 설계했나"의 서술형 deep-dive는 03–06에 있고, 이 문서는 그 **shape/흐름
요약**입니다(관점이 다름, 중복 아님).

> 코드 참조는 code repo `bourbon-agent-recommendation-api/discovery/`의 `파일:줄` 기준입니다(값·줄번호는
> 작성 시점 기준, 스레숄드는 문서 하단 [부록 A](#부록-a--스레숄드-한눈에)에 집약).

---

## 한눈에 — 7단계 파이프라인 (`discovery/pipeline.py`)

```
ⓠ normalize → ① linker → ② retrieval → ③ gate → ④ ranking → ⑤ serving → ⑥ decision log
```

| # | 단계 | 모듈 | INPUT | OUTPUT |
|---|------|------|-------|--------|
| ⓠ | normalize | `normalize.py` | `Query` (raw) | `NormalizedQuery` |
| ① | linker | `linker.py` | `topic_text: str` | `GroundingResult` *(또는 `GroundingFailedError` raise)* |
| ② | retrieval | `retrieval.py` | `grounding.qid: str` | `list[EdgeHit]` |
| ③ | gate | `gate.py` | `list[EdgeHit]` + `context` | `GateResult(survivors, dropped)` |
| ④ | ranking | `ranking.py` | `survivors`, `NormalizedQuery` | `(ranked, filter_dropped)` |
| ⑤ | serving | `serving.py` | `ranked`, `grounding`, `reasons` | `Recommendation` |
| ⑥ | decision log | `decision_log.py` | 전 단계 중간물 | `DecisionLogRecord` + `decision_log_id` stamp |

파이프라인은 provider를 직접 안 들고, 도메인 모듈 5개(linker/retriever/gate/ranker/log)만 조합합니다 →
`eval/` import 0 (import-isolation 테스트로 강제). provider는 [composition root](07-composition-api-cli.md)가
각 모듈에 주입.

### 두 개의 "0" (§4.1)

| 상황 | 어디서 | 결과 |
|------|--------|------|
| **grounding 0** | ① linker | `GroundingFailedError` **전파** → 로그 row 없음 (추천 자체 부재; Phase 5가 422 매핑) |
| **pool 0** | ⑤ serving | 에러 아님. `recommendations=[]` + `silence.silent=True`로 **200**, 로그 row는 남김 (침묵도 결정) |

---

## ⓠ normalize (`discovery/normalize.py`)

원본 요청의 자유형 `user_stance_ref` 문자열을 구조화된 `UserStanceRef`로 파싱해 string-parsing 모호성이
파이프라인 안쪽으로 새지 않게 막는다. topic→QID는 **안** 함(그건 ①).

### INPUT — `Query` (`ApiModel`, API 요청과 1:1 · `structs/recommend.py:69`)

| 필드 | 타입 | 이 단계에서 |
|------|------|-------------|
| `topic_text` | `str` (min_length=1) | 손대지 않고 통과 |
| `need_type` | `NeedType` | depth / experience / **for** / **against** / coverage |
| `user_stance_ref` | `str \| None` | 반구조 문법 `"axis=…; dir=…; text=…"` — stance 파싱 대상 |
| `context_messages` | `list[ContextMessage] \| None` | 최근 대화 턴 → `grounding_context`로 투영(①의 agentic 라우팅용, Phase 8-7). `context`(eligibility)와 **직교** |
| `lang` / `limit` / `context` | `str?` / `int(1–50)` / `dict?` | 통과 (`context`=eligibility dict, ③ gate까지 · **grounding엔 안 닿음**) |

### 처리

1. **게이트**: `need_type ∈ {for, against}` 일 때만 stance 파싱. 그 외 need는 `user_stance_ref`가 와도
   **무시**하고 `user_stance=None`으로 통과 (`normalize.py:126`).
2. **sync 정본** `normalize_query()` (`normalize.py:113`) — grammar 전용, **sync 유지**(eval 코퍼스
   validator가 sync `@model_validator`에서 부르므로 async화 불가):
   - `_parse_user_stance_ref()`: `;` 분할 → 첫 `=`에서 `partition`(text에 `=` 포함 허용) → 허용 키
     `axis/dir/text`만, 미지/중복 키·`=`없는 segment → `InvalidNeedError`. `dir`은 `Stance` enum 강제.
     빈 `text=`는 `None`으로 붕괴(LLM 경로 hygiene와 shape 일치).
   - **neutral 가드** `_require_directional()`: for/against는 상대 need라 반대편 없는 `dir=neutral` →
     `InvalidNeedError`. **문법·LLM 양 경로의 resolved stance에 동일 적용**.
3. **async fallback** `normalize_query_async()` (`normalize.py:134`) — LLM은 **정본 아닌 폴백**. 세 조건이
   **모두** 참일 때만 LLM 도달: `need ∈ {for,against}` **∧** `user_stance_ref 존재` **∧** `normalizer 주입`.
   하나라도 아니면 sync에 위임(LLM 미접촉). eligible 분기 안: 문법 먼저 → `InvalidNeedError`만 **좁게** catch
   → 그때만 `stance_normalizer.normalize(raw)` → `None`/throw면 다시 `InvalidNeedError`(자유형 실패는 문법
   실패보다 무르지 않음). LLM impl(`LLMStanceNormalizer`, `stance_normalize.py`)은 Protocol을 import 없이
   duck-type, 300자 초과·blank axis → `None` 강등, strict schema(`extra="forbid"`)로 injection 봉쇄.
   - **활성화:** `NormalizeSettings.STANCE_NORMALIZER_ENABLED` (기본 **OFF**, dormant ship). eval 미주입 →
     baseline byte-identical.
4. **대화 맥락 투영** (Phase 8-7): `context_messages` → `grounding_context`를 **tri-state**로 — 없음→`None`,
   usable text 있음→lean projection(non-empty), blank/attachment-only→`[]`. 이게 ①의 D1 라우팅(agentic vs
   symbolic)을 정한다. `grounding_context_truncated`는 context cap(`GROUNDING_CONTEXT_MAX_MESSAGES`=30) 절단
   여부. **raw wire 메시지는 drop**(lean projection만 파이프라인에 진입).

### OUTPUT — `NormalizedQuery` (`StrictBaseModel`, 파이프라인 입력 · `structs/recommend.py:80`)

`topic_text`/`need_type`/`lang`/`limit`/`context`는 그대로 복사, `user_stance`에 파싱 결과(`UserStanceRef`
또는 `None`), `grounding_context`(+`grounding_context_truncated`)에 투영된 대화. **핵심: 원본 `user_stance_ref`
문자열과 raw `context_messages`는 여기서 사라진다**(drop) — linker/ranker/serving은 구조화된 `user_stance`와
lean `grounding_context`만 본다. `UserStanceRef.confidence`는 LLM 경로만 채우며 **audit-log only**(응답/gate/
ranking 미노출).

---

## ① linker (`discovery/linker.py`) — topic_text → QID 하나

정밀 코어(symbolic) → 폴백 사다리 4-rung. popularity 신호 절대 안 씀. LLM rung은 자기 실패 케이스에서만 돎.

> **두 모드 (Phase 8-7 재설계, 기본 OFF):** `GROUNDING_AGENT_ENABLED` OFF(현 기본)면 아래 symbolic + 4-rung
> 사다리가 그대로. ON이면 **agentic grounder**(`LLMGrounder`, 대화 `grounding_context` → tool-use ReAct)가 primary가
> 되고 rerank/expansion/substitution rung은 **은퇴**, symbolic은 결정적 offline/eval 폴백 + context-absent
> unique-exact 채택으로 강등(D1 라우팅). 서술 = [03 "agentic grounder" 절](03-normalize-and-linker.md).

### INPUT / OUTPUT (전체)

- **INPUT:** `topic_text: str` (`normalized.topic_text`).
- **OUTPUT:** `GroundingResult` (`linker.py:152`) — `qid`/`label`/`confidence`/`margin` + `method`
  (`symbolic`/`agentic`/`rerank`/`expansion`/`best_effort_substitution`) + `fallback_used`(symbolic·agentic은
  False) + `considered`(로그용) + rung별 provenance(`original_topic`/`expanded_query`/`substitute_anchor_qid`/
  `substitution_reason`) + `trajectory`(agentic 채택 시 tool 스텝 trace, 그 외 `None`). 아무것도 채택 못 하면
  `GroundingFailedError` **raise**.

### 공통 전처리 (`Linker.ground()` `linker.py:350`)

```
search_candidates(topic_text, limit=LINKER_CANDIDATE_LIMIT)   # /knowledge/entities, alias-aware recall
  → _to_candidates (qid dedupe, provider 순서 보존)
  → _score (기호적 label-match confidence, confidence-desc 정렬)
  → n_exact = exact-label(confidence==1.0) 후보 수
```

`_confidence`: 정규화 label(`strip().casefold()`)이 query와 같으면 `_CONF_EXACT_LABEL=1.0`, 아니면
`_CONF_NON_EXACT=0.55`. `_margin`: 후보 1개면 자기 confidence, 2개+면 `top1−top2` (**full 정렬 집합** 기준
— cap이 runner-up을 숨겨 애매한 쌍을 통과시키지 못하게).

> **agentic 모드일 때 (Phase 8-7, 기본 OFF).** 위 공통 전처리(symbolic recall→score→`n_exact`)는 **agent OFF의
> 기본 경로**다. `GROUNDING_AGENT_ENABLED` ON이면 링커는 대화 맥락 유무로 라우팅한다(D1): context 有 → `LLMGrounder`가
> `grounding_context`를 tool-use ReAct로 grounding(→ `method="agentic"`) / context 無 + unique-exact → 아래 symbolic
> 채택 / context 無 + tie·miss → abstain. 폐기: 구 "memory-api `context=`/`types=` backend 검색으로 sense boost"
> 계획은 memory-api가 `context=`를 제거하며 철회됨. 상세 = [03 "agentic grounder" 절](03-normalize-and-linker.md) ·
> [11 §8-7](11-phase-8-9-roadmap.md).

### Decision A — `n_exact`로 rung 분기 (`linker.py:387`)

| `n_exact` | 분기 |
|-----------|------|
| **1, margin 통과** | rung ① 채택 (`symbolic`) |
| **1, margin 실패** | **종료(침묵) — 대체 안 함** (유일 정답의 확신 부족은 애매함이 아님, terminal) |
| **≥2 (동음이의 동점)** | rung ② rerank |
| **0 (recall miss)** | rung ③ expansion |

rerank·expansion의 **모든 비채택 경로**는 침묵 전에 `_substitute_or_raise`(rung ④)를 거침.

---

### rung ① symbolic — 정밀 코어 (기본 경로)

- **INPUT:** scored 후보 + `n_exact == 1`.
- **처리:** `_margin(scored) >= LINKER_MARGIN_MIN`(0.15) 이면 채택. binary regime에서 유일 exact는 항상 통과
  (margin≥0.45); 명시 분기는 높인 MIN·더 세밀한 미래 scorer에서도 routing 정직성 유지. margin 실패는
  **terminal**(사다리 안 탐, `linker.py:390`).
- **OUTPUT:** `_adopt(method="symbolic", fallback_used=False)`.
- **injection-safe:** 후보 텍스트는 오직 *비교*만, 절대 해석 안 됨.

### rung ② rerank — 동음이의 정리 (`_rerank` `linker.py:397`)

- **언제:** `n_exact ≥ 2` (exact-label이 여럿 → margin 0 붕괴).
- **INPUT:** 원 주제 + **같은 후보 풀**(`Reranker.rerank(topic_text, candidates)`).
- **처리:** LLM이 같은 풀을 재채점(recall 확장 아니라 *정리*). 응답은 후보 qid 집합에 **전단사 검증**
  (`order_toward_choice`: 누락/중복/외부 qid 거부, chosen_qid가 top-tie면 그것을 앞세우되 strictly-below면
  `None` 강등). winner는 **별도** `RERANK_CONF_MIN`(0.50) **∧** `RERANK_MARGIN_MIN`(0.15) gate 통과 필수.
  reranker `None`/degrade/gate 미달 → `_substitute_or_raise`.
- **활성화:** flag 없음 — composition root가 `LLMReranker()`를 **항상** 주입(Phase 8A live). eval 미주입
  (`reranker=None`).
- **OUTPUT:** `_adopt(method="rerank", fallback_used=True)`.

### rung ③ expansion — recall miss 회복 (`_expand` `linker.py:426`)

- **언제:** `n_exact == 0` (원 주제 exact-label 후보 없음). 빈 풀도 recall miss로 여기 라우팅.
- **INPUT:** 원 주제 + 표면화된 non-exact 후보(맥락, `Expander.expand`).
- **처리:** LLM이 **대체 검색어만** 제안(QID 절대 아님). linker 경계 가드(`linker.py:456`)로 shape 방어
  (bare str→단일 term, non-str drop, strip, blank drop, `_MAX_EXPANSION_TERMS=5` cap) → 각 term을
  `/knowledge/entities` **재검색**(concurrent, `gather` order 보존) → 원+재검색 풀 병합 후 **원 주제의 exact
  gate 재적용**. 즉 최종 QID는 여전히 검색+기호 gate가 결정, LLM은 recall만 확장. 유일 exact + margin 통과
  못 하면 넓힌 풀로 `_substitute_or_raise`.
- **활성화:** `LinkerSettings.EXPANSION_ENABLED` (기본 **OFF**, opt-in). composition root 전용.
- **OUTPUT:** `_adopt(method="expansion", fallback_used=True, original_topic=원주제,
  expanded_query=winner를 띄운 검색어)`.

### rung ④ best-effort substitution — 침묵 직전 대체 (`_substitute_or_raise` `linker.py:496`)

- **언제:** rung ②·③가 gate를 못 넘어 원래대로면 침묵할 자리(모든 terminal point에서 호출).
- **INPUT:** 원 주제 + 표면화된 풀(`Substituter.substitute`) + 직전 `failure`.
- **처리:** substituter `None`/빈 풀 → **원래 `failure` 그대로 raise**(off/실패 대체가 에러를 바꾸지 않음,
  성공만 바꿈). LLM이 풀 안에서 **가장 가까운 관련 대체 앵커**를 **필수 사유와 함께** 고름(in-set qid만 —
  bijection, QID 발명 불가). 별도 `SUBSTITUTION_CONF_MIN`(0.50) **∧** `SUBSTITUTION_MARGIN_MIN`(0.15) gate.
  못 넘으면 `failure` raise.
- **활성화:** `LinkerSettings.SUBSTITUTION_ENABLED` (기본 **OFF**, opt-in). **product 표면 큼**(다른 주제로
  답) → prod 활성화는 product 승인 + B2/human relatedness eval 통과 필요.
- **OUTPUT:** `_adopt(method="best_effort_substitution", fallback_used=True, substitute_anchor_qid==qid,
  original_topic, substitution_reason)` — **항상 대체임이 티나게** 신호(조용한 강등 금지).

---

## ② retrieval (`discovery/retrieval.py`) — QID → 후보 edge

### INPUT
`anchor_qid: str` (= `grounding.qid`).

### 처리 (`Retriever.retrieve()` `retrieval.py:91`)
1. `edges.get_edges(anchor_qid)` → direct edge 수집, `EdgeHit(via=DIRECT)`로 래핑.
2. **sparsity 판정 전 dedupe**: `_dedupe_direct_wins`로 agent별 1개(threshold는 **distinct agent** 수를
   세므로 중복 edge가 확장을 억누르면 안 됨).
3. distinct direct agent < `RETRIEVAL_MIN_DIRECT_EDGES`(3) → **one-hop 이웃 확장**
   (`_expand_neighbors`): `expand_connections`로 이웃 QID 수집(`_neighbor_qids`: broader/narrower/links_out/
   links_in 균일 취급, 앵커 자기 제외, dedupe, `RETRIEVAL_MAX_NEIGHBORS=50` cap) → 각 이웃 `get_edges`
   concurrent(`gather` 이웃 순서 보존) → `EdgeHit(via=NEIGHBOR, via_qid=원앵커)`.
4. 최종 `_dedupe_direct_wins` → **direct-wins**(같은 agent가 양쪽이면 direct).

### OUTPUT
`list[EdgeHit]` (`retrieval.py:33`) — `edge` + `via`(DIRECT/NEIGHBOR) + `via_qid`. **불변식:
`via==NEIGHBOR ⟺ via_qid 설정`**(R3; neighbor hit의 `edge.anchor_id`는 이웃 QID, `via_qid`는 원 앵커).
아직 `Candidate` 아님 — eligibility 미바인딩.

---

## ③ gate (`discovery/gate.py`) — EdgeHit → 완성된 Candidate

### INPUT
`list[EdgeHit]` + `context`(= `normalized.context`, eligibility용).

### 처리 (`Gate.screen()` `gate.py:82`)
1. **eligibility (hard-required)**: 모든 hit에 `eligibility.check(agent_id, context=...)` concurrent
   (`gather`, `return_exceptions` 미설정 → 첫 실패가 전체 gate 실패시킴, 조용한 drop 금지).
2. **need-agnostic drop** (`_need_agnostic_drop`, precedence = 가장 강한 노출 gate 먼저):
   `eligibility.discoverable` → `edge.discoverable` → `edge.maturity < MATURITY_MIN`(0.45). drop된 것은
   `drop_reason` 달아 `dropped`로(로그용), **persona 미fetch**.
3. **persona (optional 신호)**: survivor에만 `persona.get_prior` concurrent 바인딩.
4. need-specific 필터(off_axis/wrong_stance/low_stance_confidence)는 **여기 아님** — ④ Ranker 몫(R2).

### OUTPUT
`GateResult(survivors, dropped)` (`gate.py:32`) — 둘 다 `list[Candidate]`. survivor는 `drop_reason=None` +
persona 바인딩(랭킹 준비 완료), dropped는 `drop_reason` 설정(랭킹 안 됨, 로그만). **`Candidate`는 여기서
태어남**(EdgeHit + Eligibility, R1).

---

## ④ ranking (`discovery/ranking.py`) — 순서 확정 (scalar score 없음)

Alpha 랭킹은 **ordering contract**: need별 사전식 정렬 키를 **정수 rank map**으로 비교(StrEnum 문자열 정렬은
`medium>low>high` 버그라 정수 필수). provider-free·deterministic·**sync**. (단 Candidate를 in-place annotate
→ referentially pure 아님.)

### INPUT
`survivors: list[Candidate]`, `query: NormalizedQuery`.

### 처리 (`Ranker.rank()` `ranking.py:57`)
1. **annotate**: 각 candidate에 raw features(maturity/evidence/freshness, need별 experience_specificity·
   stance_confidence 추가) + `ordering_keys`(이 need의 키 이름) 기록(로그용).
2. **need별 순서**:
   - **depth**: `_depth_key` = (maturity_band↓, evidence↓, freshness↓, agent_id↑).
   - **experience**: `_experience_key` = (source_rank↓, specificity↓, evidence↓, freshness↓, band↓, agent_id↑).
     `EXPERIENCE_SOURCE_RANK` = firsthand 2 / secondhand 1 / **None 0**(abstract는 뒤로).
   - **for/against**: `_rank_stance` — **relative need**. `required_dir` = for면 `user_stance.dir`, against면
     그 반대(`_OPPOSITE_STANCE`, for↔against만; `NeedType→Stance` 매핑 금지). stance 필터
     `_stance_drop_reason`(precedence): `off_axis`(axis None/불일치) → `wrong_stance`(방향 불일치) →
     `low_stance_confidence`(`stance_confidence < STANCE_CONFIDENCE_MIN=0.60`, None=low). 통과분만
     `_stance_key`로 정렬(band↓, evidence↓, freshness↓, stance_confidence↓[late tiebreak], agent_id↑).
   - **coverage**: `_coverage_round_robin` — `edge.anchor_id`로 그룹핑, core 그룹(direct hit의 anchor_id)
     먼저, 그다음 anchor_id asc, 그룹 간 **round-robin**으로 한 facet 독점 방지.
3. stance 가드: user_stance 없이 for/against가 ranker 도달 → `ValueError`(내부 불변식, 정상은 normalize가 거름).

### OUTPUT
`(ranked, need_filter_dropped)` (`ranking.py:57`). `need_filter_dropped`는 for/against에서만 non-empty(stance
필터 drop), 나머지 need는 `[]`. Gate의 need-agnostic drop과는 파이프라인에서 병합(⑥).

---

## ⑤ serving (`discovery/serving.py`) — 응답 payload + 침묵

pure·provider-free assembly. 전체 랭킹은 ⑥에 로그, **응답은 `limit`으로 truncate**.

### INPUT
`ranked: list[Candidate]`, `grounding: GroundingResult`, `query: NormalizedQuery`,
`reasons_by_agent: dict[str,str] | None`.

### 처리
1. **rich reason (Phase 8-5, serve 전 async)**: 파이프라인이 `generate_reasons_async`를 **serve보다 먼저**
   await(`pipeline.py:65`), **top-N 슬라이스(`ranked[:limit]`)만** 대상 → LLM은 서빙될 것만 봄. `_signals`가
   단일 소스(응답 표시 신호 = LLM 입력 신호). strict coverage(정확히 served agent_ids, non-blank) 아니면
   `None`으로 전량 폴백. optional 경로라 raise해도 200을 500으로 안 만듦(degrade). `ReasonGenerator` 미주입
   (`REASON_GENERATOR_ENABLED` 기본 OFF)이면 `None`.
2. **serve() (sync·pure, `serving.py:59`)**: `returned = ranked[:limit]` → 각 항목 `_item`:
   `rank`(1-base) + `stance`(for/against만, `_stance_view` — 누락 시 `ValueError` loud-fail) +
   `reasons`(rich 있으면 그것, 없으면 `_reason` 결정적 feature 문자열) + `signals`(항상, raw edge) +
   `evidence_refs`. grounding은 `_grounding_view`로 투영(substitution인데 `substitute_anchor_qid != qid`이거나
   reason 비면 `ValueError` — "응답은 거짓말하지 않는다").
3. **silence**: `silent = not items`(= payload 기준; limit이 non-empty 랭킹을 0으로 잘라도 응답 자기일관).

### OUTPUT
`Recommendation` (`structs/recommend.py:207`) — `anchor`/`grounding`/`need_type`/`recommendations`/`silence`/
`decision_log_id`(여기선 `None`, ⑥에서 stamp).

---

## ⑥ decision log (`discovery/decision_log.py`) — 감사 row

decision-maker 아니라 **mapper**: 이미 결정된 중간물을 읽어 기록. provider I/O 없음 — clock/id_factory/
provider_versions/contract_version/sink 전부 composition root 주입(결정성·D4).

### INPUT (`DecisionLog.record()` `decision_log.py:71`)
`query`(raw) + `normalized` + `grounding` + `candidate_pool`(= survivors + gate.dropped) +
`dropped`(= gate.dropped + filter_dropped, 병합) + `ranked` + `recommendation`.

### 처리
- `_logged_query`: raw `user_stance_ref` + normalized stance(**confidence는 여기가 유일 surface**).
- `_logged_grounding`: `method`/`fallback_used`/`substitution_used`(파생)/provenance/`considered` +
  `trajectory`(agentic 채택의 tool 스텝 trace, additive block; symbolic·abstain은 없음).
- `candidate_pool`→`PoolEntry`(agent/anchor/via/via_qid), `dropped`→`DropEntry`(reason 없으면 `ValueError`
  loud-fail), `ranked`→`RankedEntry`(rank/passed_gate/need_filter/feature_breakdown[raw + maturity_band 항상,
  experience면 source_type/rank]/ordering_keys/stance).
- `reasons`/`serving`(silent/reason/returned=len) 매핑. id mint → `sink.write(row)`.

### OUTPUT
`DecisionLogRecord` (sink에 append). 파이프라인이 `recommendation.decision_log_id = record.log_id`로
**stamp back**(`pipeline.py:79`, P3). sink = prod `StructlogDecisionLogSink`(emit-only) / 테스트·eval·CLI
`ListDecisionLogSink`(retains).

---

## 부록 A — 스레숄드 한눈에

`discovery/config.py`. 모두 **provisional seed**(eval ratchet 대상, 학습 weight 아님). 구조는 permanent,
상수는 provisional.

| 상수 | 값 | 쓰임 |
|------|-----|------|
| `LINKER_MARGIN_MIN` | 0.15 | ① symbolic top1−top2 gate |
| `RERANK_CONF_MIN` / `RERANK_MARGIN_MIN` | 0.50 / 0.15 | rung ② rerank gate |
| `SUBSTITUTION_CONF_MIN` / `SUBSTITUTION_MARGIN_MIN` | 0.50 / 0.15 | rung ④ substitution gate |
| `_MAX_EXPANSION_TERMS` | 5 | rung ③ 검색어 fan-out cap (linker 경계) |
| `LINKER_CANDIDATE_LIMIT` | 20 (ge=2) | 후보 풀 cap (≥2라 margin에 runner-up 보장) |
| `RETRIEVAL_MIN_DIRECT_EDGES` | 3 | ② 이보다 적으면 이웃 확장 |
| `RETRIEVAL_MAX_NEIGHBORS` | 50 | ② 이웃 fan-out cap |
| `MATURITY_MIN` | 0.45 | ③ rankable-eligibility floor (medium cutoff 0.50 **아래** — gate와 ordering 분리) |
| `STANCE_CONFIDENCE_MIN` (τ) | 0.60 | ④ for/against 신뢰 guard |
| `MATURITY_HIGH/MEDIUM_CUTOFF` | 0.75 / 0.50 | ④ maturity band 절단 |
| `MATURITY_BAND_RANK` | HIGH 2 / MED 1 / LOW 0 | ④ band 정수 rank |
| `EXPERIENCE_SOURCE_RANK` | firsthand 2 / secondhand 1 / None 0 | ④ experience 정수 rank |

## 부록 B — LLM rung 활성화 & eval 결정성

| slice | flag | serving | eval (결정적 gold gate) |
|-------|------|---------|--------------------------|
| ⓠ stance normalizer | `STANCE_NORMALIZER_ENABLED` | 기본 OFF | 미주입 |
| ① **agentic grounder** | `GROUNDING_AGENT_ENABLED` | 기본 OFF (ON이면 아래 rung 은퇴) | 미주입 (`grounder=None`) |
| ① rung ② rerank | (flag 없음) | **항상 주입** (8A live; agent ON이면 은퇴) | 미주입 (`reranker=None`) |
| ① rung ③ expansion | `EXPANSION_ENABLED` | 기본 OFF | 미주입 |
| ① rung ④ substitution | `SUBSTITUTION_ENABLED` | 기본 OFF | 미주입 |
| ⑤ rich reason | `REASON_GENERATOR_ENABLED` | 기본 OFF | 미주입 |

모든 LLM slice는 **결정적 gold 게이트에 절대 주입되지 않음** → `baseline.json` byte-identical. 품질은 주입·
비결정 **report-only stratum**에서만 측정.

---

**요점:** `Query`가 ⓠ에서 정규화되고, ①에서 QID로 grounding(정밀 코어 → 폴백 4-rung), ②에서 후보 edge를
모으고, ③에서 Candidate로 완성·need-무관 탈락, ④에서 need별 순서·stance 필터, ⑤에서 top-N payload·침묵,
⑥에서 전 과정을 감사 row로 굳힌다. 서술형 "왜"는 [03](03-normalize-and-linker.md)–[06](06-serving-and-decision-log.md).
