# 10. eval metrics + gates — 채점 (Phase 7)

← [개요로 돌아가기](README.md) · 관련: [09. harness](09-eval-harness.md) ·
[06. decision log](06-serving-and-decision-log.md) · [11. Forward 로드맵](11-phase-8-9-roadmap.md)

평가 시스템의 **위 절반**. harness의 실행을 gold와 baseline에 대해 **채점**하고 CI pass/fail exit
code를 냅니다. **전부 결정적 gold — LLM judge 없음** (safety 게이트가 확률적 judge에 올라타면
안 됨).

세 파일: `eval/metrics.py`(측정), `eval/gates.py`(판정), `cli/eval.py`의 `gate`(배선).

---

## substrate = decision log

지표는 두 입력면을 `log_id == decision_log_id`로 join해서 계산:
- **summary** (`execution.run.scenarios`) — 각 시나리오가 무엇을 서빙했나 `(agent_id, rank)`.
- **decision logs** (`execution.decision_logs`) — pre-gate `candidate_pool`, grounding
  `considered` trace, `fallback_used`.

```python
record_by_id = {r.log_id: r for r in execution.decision_logs}
records_by_scenario = {r.scenario_id: record_by_id[r.decision_log_id]
                       for r in results if r.decision_log_id is not None}
```
completed만 join. stamped인데 record 없으면 **loud KeyError** (계약 위반).

---

## 지표 3분류 (`metrics.py: MetricReport`)

### (A) Hard gate — 고정 threshold, 절대 ratchet 아님
| 지표 | 타입 | 목표 | 의미 |
|---|---|---|---|
| `must_not_show_false_pass` | int | 0 | gold가 must_not_show인 agent를 서빙 |
| `discoverability_off_exposure` | int | 0 | undiscoverable이어야 할 agent를 서빙 |
| `needle_top1` | Ratio | 100% | unique-ideal known-item이 rank 1 |
| `retrieval_recall_easy_needle` | Ratio | 100% | target이 pre-gate pool에 존재 |

- `must_not_show`: 서빙된 (scenario, agent) 중 gold=must_not_show 개수.
- `discoverability_off_exposure`: agent-level(eligibility.discoverable=False) OR edge-level(pool에
  기여한 edge의 discoverable=False). pool entry를 `(agent_id, anchor_id)`로 edges에 join — 파이프
  라인이 쓴 것과 같은 QID join 키.
- `needle_top1`: needle당 정확히 1개 ideal이어야. 0/≥2면 **precondition violation**(분모에서 제외,
  silent skip 아님).
- `retrieval_recall`: easy ∨ needle 범위, target ∈ {ideal, acceptable}, per-target micro-avg,
  **pre-gate pool** 기준 (retrieve됐다 gate-drop돼도 retrieved로 침). errored in-scope는 miss.

### (B) Ratchet — 전역, measure→freeze→can't-regress
| 지표 | 방향 | 의미 |
|---|---|---|
| `grounding_top1` | higher | adopted qid == expected qid / completed |
| `grounding_top3` | higher | expected qid ∈ considered[:3] / completed |
| `ambiguous_fallback_rate` | lower | fallback_used / completed ambiguous |

- `ambiguous_fallback_rate`: decision B — `fallback_used`만 (grounding_failed 에러는 errored-count
  hard fail로 이미 잡히니 double-book 안 함). eval은 reranker를 주입하지 않아(offline default
  `reranker=None`) rerank fallback이 eval에선 안 떠 `fallback_used`가 항상 False → **0.0**. fallback
  자체는 serving에서 live (Phase 8A); rerank·substitution report-only strata가 가짜 rung을 주입해 eval에서도 fallback 경로를 밟지만 committed baseline은 불변(가짜는 그 strata에만 주입·committed gate는 `reranker=None`/`substituter=None` → baseline byte-identical); real-anchor 코퍼스로 eval을 reranker와 함께 돌릴 때 regression signal(변별력)이 생긴다.

### (C) report-only
- `by_need` / `by_stratum` breakdown (`grounding_top1` · `fallback_rate` · `context_grounding_rate`) —
  **절대 gate 조건 아님** (decision A). `context_grounding_rate`(8-7)는 context-carrying 시나리오를 agentic
  grounder가 옳게 grounding한 비율 — 커밋 코퍼스는 context 미보유라 분모 0, 8-4 B2/human이 live로 채점.

### precondition (loud, 먼저 확인)
- needle 비유니크 ideal, 또는 gated 지표의 빈 분모(`total==0`). *해석*될 수 없는 지표는 threshold가
  저울질되기 전에 실패. `precondition_violations` 리스트로. (ambiguous 시나리오 없는 코퍼스 →
  empty-denominator precondition → vacuous pass 방지. 커밋된 코퍼스는 25개 보유.)

### Ratio
```python
class Ratio(StrictBaseModel):
    count: int; total: int
    @computed_field
    def value(self) -> float: return self.count / self.total if self.total else 0.0
```
`value`가 computed_field라 `{value, count, total}` 전부 model_dump에 나옴 → ratchet은 value로
비교, count/total은 리뷰용.

---

## 게이트 (`eval/gates.py`)

### RATCHET_DIRECTIONS — 단일 진실원
```python
RATCHET_DIRECTIONS = {"grounding_top1": "higher", "grounding_top3": "higher",
                      "ambiguous_fallback_rate": "lower"}
```
`baseline_from_report`, `apply_gate`, unknown-key guard가 **전부 여기서 파생** → baseline 키셋과
게이트 비교가 drift 불가.

### apply_gate — 위반 순서
```python
violations = _precondition_violations(report) + _hard_gate_violations(report) + _ratchet_violations(report, baseline)
return GateResult(passed=not violations, violations=violations)
```
**precondition → hard_gate → ratchet.** hard 100%는 `count != total`(정수) 비교.

### ratchet 비교
```python
elif direction == "higher" and current.value < base.value - EPS:  # regressed
elif direction == "lower"  and current.value > base.value + EPS:   # regressed
```
`EPS=1e-9`. baseline 항목 누락도 위반.

### Baseline I/O
- `load_baseline(path)`: 파일 **없음만** None, malformed는 loud (corrupt를 "no baseline"으로 오인
  → 조용히 덮어쓰기 방지).
- `Baseline` model_validator: unknown metric key → 즉시 ValueError (typo/stale). missing key는 허용
  (→ apply_gate에서 ratchet violation).
- `baseline_from_report` + `write_baseline`(diff-stable: sort_keys, 2-indent, trailing `\n`) 분리.
- `may_update_baseline`: precondition 없음 + hard-gate 통과 (ratchet regression은 일부러 무시 —
  re-baseline이 ratchet이 움직이는 방법). `errored==0`은 CLI가 결합.

---

## CLI `eval gate` (`cli/eval.py`)
```bash
uv run python -m cli eval gate --corpus eval/corpus/fixtures \
  --anchors eval/corpus/fixtures/anchors.json --baseline eval/corpus/baseline.json
# --format json → {report, gate, baseline_updated} 봉투
# --update-baseline → 이 run으로 re-freeze (valid floor일 때만)
```
- run_eval → compute_metrics(CLI가 loader로 아티팩트 로드) → apply_gate → exit code.
- exit≠0: errored>0 OR gate 위반 OR baseline 없음&¬update.
- report → **stdout** (json 청결), PASS/FAIL/UPDATED → **stderr**.
- `--update-baseline`: `errored==0 ∧ may_update_baseline`일 때만 write (ratchet 비교 스킵).

---

## CI wiring (Phase 9) ✅

`eval gate`는 `.github/workflows/ci.yml`의 **`eval-gate` job**으로 배선됨(PR + `main` push마다,
`checks`/`test`와 병렬). 결정적(reranker/expander/substituter = None) → LLM 무접촉, baseline
byte-identical. JSON 리포트는 `eval-report` artifact. 전체 파이프라인 = [11. Phase 9](11-phase-8-9-roadmap.md),
운영 절차 = code repo README `## Continuous Integration`.

**CI가 무엇을 보증/미보증하는가 (층별 — 과장 금지):**
- **hard gate** = 절대 correctness 불변식. 코퍼스 크기와 무관하게 지금도 유효.
- **ratchet** = 천장 고정이라 엄격(한 지표만 어긋나도 trip)하나 manual-seed는 **좁은 분포**. 한계는
  **evaluation coverage이지 gate leniency가 아니며**, 강한 **regression signal**은 real anchor(Phase 10)
  이후에 붙는다.
- **gold = synthetic** → change-detector / 회귀 tripwire이지 quality measure가 아님. 진짜 품질 주장은
  B1_human / B2_silver(Phase 8-4)부터.
- **metric 계산 정합성** = `test`(pytest) job 소관(유닛 테스트), `eval-gate` 아님.

즉 green CI = "회귀 없음"이지 "품질 증명"이 아니다.

---

## 커밋된 baseline (`eval/corpus/baseline.json`)
```json
{ "corpus_version": "manual-seed",
  "metrics": {
    "grounding_top1": {"count":111,"total":111,"value":1.0},
    "grounding_top3": {"count":111,"total":111,"value":1.0},
    "ambiguous_fallback_rate": {"count":0,"total":25,"value":0.0} } }
```
hard-gate 지표는 여기 **없음** (threshold가 코드 고정).

---

## Phase 7 green bar (`tests/eval/test_phase7_acceptance.py`)
6. hard gate 통과 (0/0/100%/100%).
7. ratchet이 real 분모 위에서 측정 + baseline freeze.
8. 시나리오당 schema-valid record 1개, report byte-reproducible, **baseline in-sync**, `eval gate`
   exit 0.

**★ baseline-in-sync = ratchet 회귀 tripwire:**
```python
assert committed == baseline_from_report(report, corpus_version=corpus_version)
```
코퍼스를 바꿔 ratchet 지표가 움직였는데 re-baseline을 빼먹으면 이 테스트가 실패 → 조용히 넘어가는
걸 막음.

---

**요점:** metrics는 decision log substrate를 측정만 하고, gates는 hard threshold + ratchet으로
CI 판정. 전부 결정적 gold. `ambiguous_fallback_rate` 슬롯은 eval이 reranker 미주입이라 잠잠하지만
(0.0), fallback 자체는 serving에서 이미 live (Phase 8A)이고 rerank·substitution report-only strata(주입 가짜)가 eval에서 fallback 경로를 밟아도 committed baseline은 그대로다 — [11. Forward 로드맵](11-phase-8-9-roadmap.md).
