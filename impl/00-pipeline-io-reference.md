# 00. 파이프라인 I/O 참조 — 단계별 input → 처리 → output

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[03. normalize+linker](03-normalize-and-linker.md) · [04. retrieval](04-retrieval.md) ·
[05. gate+ranking](05-gate-and-ranking.md) · [06. serving+decision-log](06-serving-and-decision-log.md)

이 문서는 `RecommendationPipeline.recommend(query)` 한 콜이 거치는 **8단계를 데이터 계약 관점**으로
정리한 빠른 참조입니다. 각 단계를 **INPUT → 처리 → OUTPUT** 한 틀로 보여주고, rung으로 나뉜 ① linker는
rung별로 쪼갭니다. "왜 이렇게 설계했나"의 서술형 deep-dive는 03–06에 있고, 이 문서는 그 **shape/흐름
요약**입니다(관점이 다름, 중복 아님).

> 코드 참조는 code repo `bourbon-agent-recommendation-api/discovery/`의 `파일:줄` 기준입니다(값·줄번호는
> 작성 시점 기준, 스레숄드는 문서 하단 [부록 A](#부록-a--스레숄드-한눈에)에 집약).

---

## 한눈에 — 8단계 파이프라인 (`discovery/pipeline.py`)

```
ⓠ normalize → ① linker → ② retrieval → ③ gate → [④a stance] → ④b ranking → ⑤ serving → ⑥ decision log
```

| # | 단계 | 모듈 | INPUT | OUTPUT |
|---|------|------|-------|--------|
| ⓠ | normalize | `normalize.py` | `Query` (raw) | `NormalizedQuery` |
| ① | linker | `linker.py` | `topic_text: str` | `GroundingResult` *(또는 `GroundingFailedError` raise)* |
| ② | retrieval | `retrieval.py` | `grounding.qid: str` | `list[EdgeHit]` |
| ③ | gate | `gate.py` | `list[EdgeHit]` + `eligibility_context` | `GateResult(survivors, dropped)` |
| ④a | stance *(for/against만)* | `stance.py` | `survivors`, `NormalizedQuery`, `subject_qid` | `StanceEvaluation(candidates, silence_reason)` |
| ④b | ranking | `ranking.py` | `survivors`, `NormalizedQuery` | `(ranked, filter_dropped)` |
| ⑤ | serving | `serving.py` | `ranked`, `grounding`, `reasons` | `Recommendation` |
| ⑥ | decision log | `decision_log.py` | 전 단계 중간물 | `DecisionLogRecord` + `decision_log_id` stamp |

파이프라인은 provider를 직접 안 들고, 도메인 모듈 5개(linker/retriever/gate/ranker/log)와 optional
seam 2개(stance evaluator·reason generator)만 조합합니다 → `eval/` import 0 (import-isolation 테스트로
강제). provider는 [composition root](07-composition-api-cli.md)가 각 모듈에 주입.

④a만 need에 따라 **조건부**입니다(for/against 아니면 아예 안 돎). 그래서 번호가 ④a/④b로 갈립니다 —
둘 다 "need를 아는 단계"지만 ④a는 I/O(LLM·검색)를 하고 ④b는 순수 함수입니다.

### 두 개의 "0" (§4.1)

| 상황 | 어디서 | 결과 |
|------|--------|------|
| **grounding 0** | ① linker | `GroundingFailedError` **전파** → 로그 row 없음 (추천 자체 부재; Phase 5가 422 매핑) |
| **pool 0** | ⑤ serving | 에러 아님. `recommendations=[]` + `silence.silent=True`로 **200**, 로그 row는 남김 (침묵도 결정) |

---

## ⓠ normalize (`discovery/normalize.py`)

for/against 요청이 실은 **`proposition`**(판단 대상 주장 문장)의 존재·non-blank를 검증하고, 대화 맥락을
lean projection으로 투영한다. topic→QID는 **안** 함(그건 ①). 파싱할 문법도 LLM 폴백도 없어 **순수 sync**.

### INPUT — `Query` (`ApiModel`, API 요청과 1:1 · `structs/recommend.py:75`)

| 필드 | 타입 | 이 단계에서 |
|------|------|-------------|
| `topic_text` | `str` (min_length=1) | 손대지 않고 통과 |
| `need_type` | `NeedType` | depth / experience / **for** / **against** / coverage |
| `proposition` | `str \| None` | for/against가 판단할 **주장 문장**(자유 문장, 문법 없음). stance need면 필수·non-blank, 그 외 need에선 무시 |
| `context_messages` | `list[ContextMessage] \| None` | 최근 대화 턴 → `grounding_context`로 투영(①의 agentic 라우팅용, Phase 8-7). `context`(eligibility)와 **직교** |
| `lang` / `limit` / `eligibility_context` | `str?` / `int(1–50)` / `dict?` | 통과 (`eligibility_context`=eligibility dict, ③ gate까지 · **grounding엔 안 닿음**) |

### 처리

1. **stance need 검증**: `need_type ∈ STANCE_NEEDS`(= `{for, against}`, `structs/recommend.py:42`의 단일
   진실원)이면 `proposition`이 `None`이거나 blank → `InvalidNeedError`. 통과하면 `strip()`해서 나른다.
   그 외 need는 `proposition`이 와도 **무시**하고 `None`으로 통과.
2. **해석 없음**: proposition을 내부 문법으로 파싱하거나 의미를 재작성하지 않는다 — 정규화가 하는 일은
   존재·blank 검증과 **양끝 공백 제거(`strip()`)** 뿐이고, 그 결과가 canonical proposition이다. 해석할
   게 없으니 `normalize_query()`는 **유일한 정본이자 sync**로 남는다(eval 코퍼스 validator가 sync
   `@model_validator`에서 부르므로 async화 불가). async sibling은 **없다**.
3. **대화 맥락 투영** (Phase 8-7): `context_messages` → `grounding_context`를 **tri-state**로 — 없음→`None`,
   usable text 있음→lean projection(non-empty), blank/attachment-only→`[]`. 이게 ①의 D1 라우팅(agentic vs
   symbolic)을 정한다. `grounding_context_truncated`는 context cap(`GROUNDING_CONTEXT_MAX_MESSAGES`=30) 절단
   여부. **raw wire 메시지는 drop**(lean projection만 파이프라인에 진입).

> **폐기된 구 모델 (stance 재설계).** 초기 Alpha는 `user_stance_ref: str`를 반구조 문법
> `"axis=…; dir=…; text=…"`로 파싱해 `UserStanceRef{axis, dir, text, confidence}`를 만들고, 그 위에 자유
> 문장을 받는 LLM normalizer(Phase 8-3, `STANCE_NORMALIZER_ENABLED`)를 폴백으로 얹었다. 요청 필드·문법·
> `UserStanceRef`·neutral 가드·LLM normalizer는 **전부 제거**됐다. 이유: 필요 방향은 이제 유저 stance에서
> 상대적으로 파생되지 않고 **`need_type`이 절대적으로 정하며**(④b), 후보의 입장은 edge에 관측된 stance가
> 아니라 **query-time judge**가 정하기 때문이다. 남은 유저 입력은 판단 대상 주장 하나뿐이다.

### OUTPUT — `NormalizedQuery` (`StrictBaseModel`, 파이프라인 입력 · `structs/recommend.py:92`)

`topic_text`/`need_type`/`lang`/`limit`/`eligibility_context`는 그대로 복사, `proposition`에 strip된 주장
(또는 `None`), `grounding_context`(+`grounding_context_truncated`)에 투영된 대화. **핵심: raw
`context_messages`는 여기서 사라진다**(drop) — 파이프라인은 lean `grounding_context`만 본다. strip된 이
**canonical proposition** 하나가 judge 입력·응답 `StanceView.proposition`·로그 `LoggedQuery.proposition`에
**동일한 문자열로** 흐른다.

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
search_candidates(topic_text, limit=LINKER_CANDIDATE_LIMIT)   # POST /knowledge/entities/search, alias-aware recall
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
> [11 §8-7](11-forward-roadmap.md).

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
  `POST /knowledge/entities/search` **재검색**(concurrent, `gather` order 보존) → 원+재검색 풀 병합 후 **원 주제의 exact
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
`list[EdgeHit]` + `context`(= `normalized.eligibility_context`, eligibility용).

### 처리 (`Gate.screen()` `gate.py:82`)
1. **eligibility (hard-required)**: 모든 hit에 `eligibility.check(agent_id, context=...)` concurrent
   (`gather`, `return_exceptions` 미설정 → 첫 실패가 전체 gate 실패시킴, 조용한 drop 금지).
2. **need-agnostic drop** (`_need_agnostic_drop`, precedence = 가장 강한 노출 gate 먼저):
   `eligibility.discoverable` → `edge.discoverable` → `edge.maturity < MATURITY_MIN`(0.45). drop된 것은
   `drop_reason` 달아 `dropped`로(로그용), **persona 미fetch**.
3. **persona (optional 신호)**: survivor에만 `persona.get_prior` concurrent 바인딩.
4. need-specific 필터(`stance_unevaluated`/`wrong_stance`/`low_stance_confidence`)는 **여기 아님** —
   ④b Ranker 몫(R2).

### OUTPUT
`GateResult(survivors, dropped)` (`gate.py:32`) — 둘 다 `list[Candidate]`. survivor는 `drop_reason=None` +
persona 바인딩(랭킹 준비 완료), dropped는 `drop_reason` 설정(랭킹 안 됨, 로그만). **`Candidate`는 여기서
태어남**(EdgeHit + Eligibility, R1).

---

## ④a stance (`discovery/stance.py`) — for/against 전용, 랭킹 **전에** 입장 판정

edge에 관측된 stance를 미러링하는 게 아니라 **요청 시점에** 각 후보의 입장을 판정해 넣는다. 이 단계가
없으면(dormant) for/against는 조용히 열화되지 않고 **명시적으로 침묵**한다.

### INPUT
`survivors: list[Candidate]`, `NormalizedQuery`(= `proposition` 보유), `subject_qid`(= `grounding.qid`).

### 처리 (`pipeline.py:107` → `StanceEvaluator.evaluate()`)

0. **hard-K 선별** — evaluator가 붙어 있을 때만 `Ranker.stance_shortlist(limit=STANCE_SHORTLIST_LIMIT=20)`.
   stance-무관 competence 키(`_depth_key`)로 상위 K만 남기고 나머지는 `stance_shortlist_limit`으로 drop
   로그. **검색·judge 비용을 evidence 검색 이전에 묶는 유일한 지점.** 결정적 hard-K 근사이지 최종 stance
   랭킹의 무손실 prefix가 아니다(`_stance_key`는 competence 3키 *뒤에* `stance_confidence`를 넣으므로,
   경계 동점에서 잘린 후보가 나중에 더 높은 confidence를 받을 수 있다 — 알려진 trade-off).
   dormant면 이 단계를 **건너뛴다**(judge가 없는데 K drop을 로그하면 거짓말).
1. **symmetric query 생성** (LLM 1콜) — `StanceQueryGenerator.generate(topic, proposition)` →
   `StanceQueries{neutral, support, oppose}`. 요청한 쪽만 검색하면 그 owner의 **반대 주장을 놓쳐**
   오추천하므로 세 방향을 항상 함께 만든다. 한 방향이라도 비면 편향된 확장이라 `None` 강등 →
   `stance_query_generation_failed`(**검색 미발행**).
2. **owner-scoped 검색 — provider 호출 1회** — `StanceEvidenceSearchProvider.search()`를 정확히 한 번.
   distinct phrase 전부를 하나의 ANY-match로, `subject_qid` 스코프 + eligibility 통과한 owner만
   (global discovery 없음), owner별 `STANCE_SEARCH_PER_OWNER_LIMIT`(10)까지.
   응답은 `_admit`이 재검증: owner 일치 · shortlist 소속 · `subject_qid` 일치 · **`attribution=OWNER`**
   (노출≠주장, 서버 필터가 회귀해도 방어) · `statement_id` dedupe.
   > **`OWNER`의 의미 (계약).** numeric confidence가 높다는 뜻이 **아니다.** 현 memory-api 계약에서 `OWNER`는
   > claim의 **provenance에 owner sender가 있을 때만** 부여되는 **assertion-source attribution**이다. Discovery는
   > 이 의미론을 신뢰해 admit하고, 그럼에도 응답을 `_admit`에서 재검증한다(defense in depth). 협의 경위와 코드
   > 근거는 `../archive/memory_api_statement_attribution_followup.md` §1, 향후 `confidence` 의미 변경 리스크는
   > `../memory_api_discovery_open_requests.md` **R7**(deferred — 지금 막는 것 없음).
   > **provider 호출 1회 ≠ HTTP POST 1회.** 엔드포인트가 `owner_ids`를 20명으로 캡하므로 HTTP 어댑터가
   > owner chunk별로 **`ceil(K/20)`개의 POST**로 fan-out합니다(`STANCE_SEARCH_MAX_CONCURRENCY`=5로 동시성
   > 제한, chunk 하나라도 실패하면 부분 recall이 verdict를 뒤집을 수 있으므로 **전체 실패**). 기본
   > K=20에서는 POST도 1개지만 `STANCE_SHORTLIST_LIMIT`을 올리면 늘어납니다.
3. **owner별 judge** (후보당 LLM 1콜, **순차 루프**) — `StanceJudge.judge(proposition, statements)` →
   `StanceVerdict{verdict, evidence_stmt_ids, graded_confidence}`. verdict는 **절대값**
   (supports/opposes/insufficient) — 요청 방향은 안 넘긴다. positional verdict는 **실제로 보여준**
   statement id를 최소 1개 인용해야 하고(firsthand-honesty), 아니면 `insufficient`로 강등.
4. **후보 주입** — supports/opposes만 `stance_proposition`/`stance_position`/`stance_confidence`에 기록.
   `insufficient`와 judge `None`(엔진 실패)은 필드를 **안 건드린다** → ④b에서 `stance_unevaluated` drop.
   evaluator는 `drop_reason`을 직접 안 단다(그건 ranker 몫).

### OUTPUT
`StanceEvaluation(candidates, silence_reason)` (`structs/stance.py`). `silence_reason`이 있으면 ⑤가
payload를 **강제로 비운다**. 파이프라인의 `_evaluate_stance`(`pipeline.py:158`)가 evaluator 부재/예외를
coarse 사유로 매핑 — 이 경우 후보는 **빈 리스트**가 되어 ④b에 도달하지 않는다.

| silence 사유 (`StanceSilenceReason`, 6값) | 누가 정하나 | 언제 |
|---|---|---|
| `stance_judge_disabled` | 파이프라인 | evaluator 미주입 (dormant 기본) |
| `stance_judge_unavailable` | 파이프라인 | 의존성 미배선 → `UpstreamUnavailableError` 전파 (설정 갭) |
| `stance_judge_failed` | 파이프라인 / evaluator | evaluator 전면 예외, 또는 usable 0 + judge 에러 ≥1 |
| `stance_query_generation_failed` | evaluator | 1단계 생성이 실패·비대칭 (검색 미발행) |
| `stance_evidence_search_failed` | evaluator | 배선된 검색이 요청 시점에 실패 |
| `all_candidates_insufficient` | evaluator | judge가 **깨끗하게** 돌고 전원 insufficient (에러 0) |

순서는 엄격한 파이프라인이라 **앞 단계 사유가 뒤 단계에 덮이지 않는다**(query-gen 실패는 검색 전에
short-circuit, 검색 실패는 judge 전에 short-circuit). 후보가 애초에 0이면 여기서 사유를 만들지 않고
⑤의 일반 `no_candidates`로 보낸다 — judge가 안 돈 걸 `all_candidates_insufficient`라 하면 거짓말이므로.

> **아직 소비자 없는 설정 2개:** `STANCE_MAX_SEARCH_CALLS`(=2)와 `STANCE_INLINE_PREVIEW_LIMIT`(=10,
> Tier-1 inline preview)은 스펙상 자리를 잡아뒀지만 현재 evaluator는 **provider 검색을 정확히 1회**만
> 한다(escalation 미구현). 주의: `STANCE_MAX_SEARCH_CALLS`는 향후 pre/post **escalation leg 수**의 상한이지
> 위 chunk POST 수의 상한이 **아니다**(그건 `ceil(K/20)`로 정해짐). `STANCE_SEARCH_MAX_CONCURRENCY`(=5)만
> HTTP 어댑터가 실제로 사용한다.

---

## ④b ranking (`discovery/ranking.py`) — 순서 확정 (scalar score 없음)

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
   - **for/against**: `_rank_stance` — **absolute need**. 필요 position은 `need_type`이 직접 정한다:
     `_REQUIRED_POSITION = {FOR: SUPPORTS, AGAINST: OPPOSES}` (`ranking.py:30`). 유저 stance 기준의 상대
     계산(`_OPPOSITE_STANCE`)은 폐기. 랭커는 **candidate의 query-time stance만** 읽고 edge의
     `observed_stance`는 **절대 안 읽는다**. stance 필터 `_stance_drop_reason`(precedence):
     `stance_unevaluated`(`stance_position is None`) → `wrong_stance`(position ≠ required) →
     `low_stance_confidence`(`stance_confidence < STANCE_CONFIDENCE_MIN=0.60`, None=low). **`off_axis`는
     없다** — 폐기된 것은 production Ranker의 axis 비교 단계와 그 drop 사유이고(`stance_axis` 필드 자체는
     frozen edge 계약과 결정적 eval mirror에 남아 있다), 그 자리를 `stance_unevaluated`가 흡수한다.
     통과분만 `_stance_key`로 정렬(band↓, evidence↓, freshness↓, stance_confidence↓[late tiebreak],
     agent_id↑).
   - **coverage**: `_coverage_round_robin` — `edge.anchor_id`로 그룹핑, core 그룹(direct hit의 anchor_id)
     먼저, 그다음 anchor_id asc, 그룹 간 **round-robin**으로 한 facet 독점 방지.

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
   await(`pipeline.py:71`), **top-N 슬라이스(`ranked[:limit]`)만** 대상 → LLM은 서빙될 것만 봄. `_signals`가
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

### INPUT (`DecisionLog.record()` `decision_log.py:69`)
`normalized` + `grounding` + `candidate_pool`(= survivors + gate.dropped) +
`dropped`(= gate.dropped + filter_dropped, 병합) + `ranked` + `recommendation`. **raw `Query`는 받지
않는다** — 정규화가 순수 검증뿐이라 raw/normalized를 나란히 남길 이유가 사라졌다.

### 처리
- `_logged_query`: `topic_text`/`need_type`/`lang`/`limit` + `proposition`(canonical proposition, audit only).
- `_logged_grounding`: `method`/`fallback_used`/`substitution_used`(파생)/provenance/`considered` +
  `trajectory`(agentic 채택의 tool 스텝 trace, additive block; symbolic·abstain은 없음).
- `candidate_pool`→`PoolEntry`(agent/anchor/via/via_qid), `dropped`→`DropEntry`(reason 없으면 `ValueError`
  loud-fail), `ranked`→`RankedEntry`(rank/passed_gate/need_filter/feature_breakdown[raw + maturity_band 항상,
  experience면 source_type/rank]/ordering_keys/stance).
- `reasons`/`serving`(silent/reason/returned=len) 매핑. id mint → `sink.write(row)`.

### OUTPUT
`DecisionLogRecord` (sink에 append). 파이프라인이 `recommendation.decision_log_id = record.log_id`로
**stamp back**(`pipeline.py:85`, P3). sink = prod `StructlogDecisionLogSink`(emit-only) / 테스트·eval·CLI
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
| `STANCE_SHORTLIST_LIMIT` (K) | 20 | ④a 검색·judge 이전 hard-K |
| `STANCE_SEARCH_PER_OWNER_LIMIT` | 10 | ④a owner별 statement 상한 (cost cap) |
| `STANCE_CONFIDENCE_MIN` (τ) | 0.60 | ④b for/against 신뢰 guard |
| `MATURITY_HIGH/MEDIUM_CUTOFF` | 0.75 / 0.50 | ④b maturity band 절단 |
| `MATURITY_BAND_RANK` | HIGH 2 / MED 1 / LOW 0 | ④b band 정수 rank |
| `EXPERIENCE_SOURCE_RANK` | firsthand 2 / secondhand 1 / None 0 | ④b experience 정수 rank |

## 부록 B — LLM rung 활성화 & eval 결정성

| slice | flag | serving | eval (결정적 gold gate) |
|-------|------|---------|--------------------------|
| ① **agentic grounder** | `GROUNDING_AGENT_ENABLED` | 기본 OFF (ON이면 아래 rung 은퇴) | 미주입 (`grounder=None`) |
| ① rung ② rerank | (flag 없음) | **항상 주입** (8A live; agent ON이면 은퇴) | 미주입 (`reranker=None`) |
| ① rung ③ expansion | `EXPANSION_ENABLED` | 기본 OFF | 미주입 |
| ① rung ④ substitution | `SUBSTITUTION_ENABLED` | 기본 OFF | 미주입 |
| ④a stance query-gen + judge | `STANCE_JUDGE_ENABLED` | 기본 OFF (침묵) | `EdgeMirrorStanceEvaluator` 주입 (LLM 없음) |
| ⑤ rich reason | `REASON_GENERATOR_ENABLED` | 기본 OFF | 미주입 |

모든 LLM slice는 **결정적 gold 게이트에 절대 주입되지 않음** → `baseline.json` byte-identical. 품질은 주입·
비결정 **report-only stratum**에서만 측정. ④a만 예외적으로 eval에 *무언가*를 주입하지만, 그건 LLM이 아니라
edge를 미러링하는 결정적 stand-in이라 결정성이 유지된다(그게 없으면 코퍼스의 for/against 시나리오가 전부
침묵해 gold가 무의미해진다).

---

**요점:** `Query`가 ⓠ에서 정규화되고, ①에서 QID로 grounding(정밀 코어 → 폴백 4-rung), ②에서 후보 edge를
모으고, ③에서 Candidate로 완성·need-무관 탈락, ④a에서 (for/against면) query-time 입장을 판정, ④b에서
need별 순서·stance 필터, ⑤에서 top-N payload·침묵, ⑥에서 전 과정을 감사 row로 굳힌다. 서술형 "왜"는 [03](03-normalize-and-linker.md)–[06](06-serving-and-decision-log.md).
