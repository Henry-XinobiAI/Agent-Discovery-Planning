# 09. eval harness — 실행/커버리지 (Phase 6)

← [개요로 돌아가기](README.md) · 관련: [10. metrics + gates](10-eval-metrics-and-gates.md) ·
[06. decision log](06-serving-and-decision-log.md) · [02. Provider 경계](02-provider-boundary.md)

평가 시스템의 **아래 절반**. 커밋된 벤치마크 코퍼스를 **네트워크 없이, LLM 없이** 실제 파이프라인에
재생하고 "무슨 일이 일어났는지"만 보고합니다. **점수가 없습니다(score-free).**

한글 번역 참고: [`eval_README_ko.md`](eval_README_ko.md) (eval/README.md 전문 번역).

---

## 레이어 경계 (핵심)

`harness.py` / `eval run`에는 **의도적으로** score, pass/fail, threshold, judge가 **없습니다**.
채점은 한 레이어 위([10 문서](10-eval-metrics-and-gates.md)). 이 경계를 `EvalRun` 계약 가드가
기계적으로 강제 — payload에 `score`/`judge`/`threshold`/`pass`/`fail` 키가 절대 없음.

---

## 코퍼스 (`eval/corpus/fixtures/`)

flat 디렉터리. 러너가 한 곳에서 읽음:

| 파일 | struct | 무엇 |
|---|---|---|
| `anchors.json` | `PinnedAnchorFixture` | 지식 substrate 캡처 (**grounding이 이 위에서 실행**) |
| `agents.json` | `AgentFixture[]` | agent_id + persona prior + eligibility 판정 |
| `edges.json` | `AgentTopicEdge[]` | 실제 QID 위의 agent↔topic edge |
| `scenarios.json` | `Scenario[]` | eval 쿼리 (need × anchor + guard row) |
| `gold.json` | `GoldLabel[]` | 합성 라벨 (Phase 7 채점 gold) |

- **`anchors.json`이 "teeth"**: `AnchoredKnowledgeProvider`를 뒷받침, 5개 `/knowledge/entities*`
  메서드를 pinned 응답 재생으로 서빙. 현재 `memory_api_commit="manual-seed"`(손으로 seed한
  대체물, 각 쿼리가 단일 exact-label 후보 → grounding conf/margin 1.0). memory-api 도달 가능해지면
  `build-anchors`가 진짜 캡처로 backfill.
- **`gold.json`은 regression seed이지 인간 품질 주장 아님**: `source=synthetic`, 모든 rationale
  `synthetic_rule:` 접두. 파이프라인 자신의 게이트를 우선순위 순서로 미러 (not-discoverable →
  must_not_show → needle winner=ideal → stance bad → maturity floor bad → band ideal/acceptable).

### scenario 필드
- `need_type`, `anchor_query_id`(anchors.queries[]로 들어가는 안정 handle — 문구 편집이 링크를
  안 깸), `stratum`(easy/hard/ambiguous/guard), `is_needle`(정확히 1개가 rank-1), for/against면
  `user_stance_ref`/`expected_axis`, guard면 `tags`, 그리고 `context_messages`(agentic grounder
  stratum용 대화 맥락 — `None`이 기본이고 커밋 코퍼스는 미보유 → symbolic 경로).

### 9개 guard (두 레이어로 분리)
- **coverage row** (`eval/builders/guards.py`) — guard당 태그된 시나리오 1개, 셈 가능. 동작 증명
  아님.
- **behavior proof** (`tests/eval/guards/test_guard_assertions.py`) — 각 guard를 가장 명료한
  스테이지로 구동해 불변식 assert (retrieval-expansion, ambiguous-topic, same-axis-disagreement,
  weak-evidence-low-maturity, experience-vs-depth, high-persona-low-memory, stale-but-valuable,
  discoverability-off, rerank-injection).

---

## harness (`eval/harness.py`)

### 흐름
```python
async def run_eval(*, corpus_dir, anchors_path, run_id, corpus_version, generated_at,
                   reranker=None, substituter=None, grounder=None) -> EvalExecution:  # LLM seam, 기본 미주입
    anchors = loader.load_anchors(anchors_path)
    scenarios = sorted(loader.load_scenarios(...), key=lambda s: s.scenario_id)
    agents, gold = loader.load_agents(...), loader.load_gold(...)
    loader.validate_corpus_refs(...)          # green bar #1: dangling/dup → loud fail 여기서

    sink = ListDecisionLogSink()               # run_eval이 소유
    pipeline = _build_pipeline(corpus_dir, anchors, sink)
    results = [await _run_scenario(pipeline, s) for s in scenarios]
    run = _summarize(results, scenarios, run_id=..., corpus_version=..., generated_at=...)
    return EvalExecution(run=run, decision_logs=list(sink.records))
```

### `EvalExecution` = `{run, decision_logs}` (Phase 7 경계)
- `run: EvalRun` — 실행/커버리지 요약 (`eval run`이 출력, score-free).
- `decision_logs: list[DecisionLogRecord]` — **Phase 7 지표가 채점하는 substrate**. run_eval이
  sink를 소유·주입한 뒤 `sink.records`를 읽음 (이전엔 내부 생성·폐기했음).
- 계약: **완료 시나리오당 record 1개**. errored 시나리오는 로그 쓰기 전에 throw → record 없음,
  `ScenarioResult.decision_log_id is None`. 커밋된 코퍼스는 전부 완료 → 시나리오당 정확히 1개,
  `log_id == decision_log_id`로 join.

### 오프라인 substrate 배선 (`_build_pipeline`)
```python
knowledge = AnchoredKnowledgeProvider(anchors)   # real HTTP 아님, pinned 재생
RecommendationPipeline(
    linker=Linker(knowledge, reranker=reranker, substituter=substituter, grounder=grounder),  # seam 기본 None → symbolic·결정적
    retriever=Retriever(MockMemoryEdgeProvider.from_fixtures(corpus_dir), knowledge),
    gate=Gate(MockEligibilityProvider.from_fixtures(corpus_dir), MockPersonaProvider.from_fixtures(corpus_dir)),
    ranker=Ranker(),
    log=DecisionLog(clock=lambda: _FIXED_CLOCK, id_factory=lambda: next(ids), ..., sink=sink),
)
```
- **재현성 (D5)**: `run_id`/`corpus_version`/`generated_at`을 caller가 **주입**. clock 고정
  (`2026-01-01`), id `dl_0, dl_1, …`. 같은 코퍼스 + 같은 주입 → byte-identical.
- mock provider 3종은 `eval/providers/*`. eligibility mock은 fail-closed (미지 → discoverable=False).

### 실패는 치명적이지 않음 (D6)
```python
try:
    recommendation = await pipeline.recommend(query)
except Exception:
    logger.exception(...)   # traceback 보존
    return ScenarioResult(..., status=_ERRORED, decision_log_id=None)
```
per-scenario 실패는 **세지만** run을 중단 안 함 → 요약이 정직. exit code는 CLI가 errored 수로 결정.

### 요약 (`EvalRun`)
- `summary`: scenario_count / completed / errored / recommendation_count / needle_count.
- `by_need` / `by_stratum`: 그룹별 실행 개수 (빈 그룹 생략).
- `scenarios`: 시나리오별 결과 (rank only, adopted_anchor_qid, silent, decision_log_id, status).

---

## 5개 green bar (`tests/eval/test_corpus_acceptance.py`)
1. 모든 파일 schema-validate + cross-ref 해소.
2. 모든 `edge.anchor_id`가 anchors.entities의 QID.
3. 4개 strata 비지 않음, need당 ≥ 20 시나리오.
4. 9개 guard 각 ≥ 1 coverage, need당 needle ≥ 1.
5. `eval run`이 errored==0으로 오프라인 완주.

---

## 실행
```bash
uv run python -m cli eval run --corpus eval/corpus/fixtures --anchors eval/corpus/fixtures/anchors.json
# --format json / --allow-errors (로컬 디버그 전용)
```
exit 0 = 모든 시나리오 완료. 하나라도 errored면 non-zero (숨은 실패가 green으로 안 읽히게).

---

**요점:** harness는 "코퍼스가 잘 형성됐고 파이프라인이 끝까지 돈다"를 점수 없이 증명하고,
그 부산물인 decision log를 다음 레이어에 넘깁니다 —
[10. metrics + gates](10-eval-metrics-and-gates.md)가 채점합니다.
