# 06. serving (⑤) + decision log (⑥)

← [개요로 돌아가기](README.md) · 관련: [05. gate + ranking](05-gate-and-ranking.md) ·
[10. eval metrics + gates](10-eval-metrics-and-gates.md)

파이프라인의 마지막 두 단계. serving은 **응답 payload**를, decision log는 **감사 기록**을
만듭니다. decision log는 나중에 [Phase 7 지표](10-eval-metrics-and-gates.md)의 substrate가 되므로
특히 중요합니다.

---

## ⑤ serving (`discovery/serving.py`)

순수, provider-free 조립 단계. ranked survivor + grounding → `Recommendation`.

```python
def serve(ranked, *, grounding, query):
    returned = ranked[: query.limit]          # top-limit 잘라냄
    items = [_item(c, rank, is_stance=...) for rank, c in enumerate(returned, start=1)]
    return Recommendation(
        anchor=AnchorView(qid=grounding.qid, label=grounding.label),
        need_type=query.need_type,
        recommendations=items,
        silence=SilenceView(silent=not items, reason=None if items else "no_candidates"),
    )
```

### 비자명한 점

**(1) silence = `not items` 기준** — 입력 pool이 아니라 **payload** 기준. `limit`이 비어있지 않은
ranking을 0으로 잘라도 응답이 자기 일관적. (리뷰 Medium 반영.)

**(2) top-limit 비대칭** — *로그*는 전체 ordering trace를 유지하고, *payload*는 top-N만.
`serving.returned`는 실제 반환된 top-N만 기록.

**(3) 결정적 reason (no-LLM)**:
```python
def _reason(edge):
    return f"maturity {edge.maturity:.2f} · evidence {edge.evidence_strength:.2f} · freshness {edge.freshness:.2f}"
```
항상 존재하는 정렬 신호로 만든 문자열. 풍부한 per-need reason은 Phase 8.

**(4) stance 누락 loud fail** — for/against 응답인데 stance가 없으면 계약 위반이므로 조용히 서빙
안 하고 `ValueError`. (ranked stance 후보는 need-filter를 통과했으니 stance가 있어야 함.)

**(5) `decision_log_id`는 여기서 None** — 파이프라인이 로그 row를 쓴 뒤 stamp (id는
`DecisionLog.record` 안에서 mint).

---

## ⑥ decision log (`discovery/decision_log.py`)

`recommend()` 한 번 = `DecisionLogRecord` 한 개. **매퍼이지 의사결정자가 아님** — 이미 결정된
객체들을 읽어서 기록만. provider I/O 없음.

### 주입되는 것 (composition root가 결정)
```python
DecisionLog(
    clock,             # ts 결정성 (D4)
    id_factory,        # log_id 결정성
    provider_versions, # 배포별 substrate provenance (mock vs real)
    contract_version,
    sink,              # 완성 record가 가는 곳
)
```
- `clock`/`id_factory` 주입 → 테스트에서 `ts`/`log_id` 결정적.
- `sink` (`decision_log_sink.py`): 배포 root는 `StructlogDecisionLogSink`(emit-and-forget, 무한
  메모리 없음), 테스트/eval/CLI는 `ListDecisionLogSink`(`records` 보관). writer는 `sink.write()`만
  호출 — 보관 정책은 sink에.

### record() 매핑
```python
row = DecisionLogRecord(
    log_id=id_factory(), ts=clock(),
    query=_logged_query(query, normalized),          # raw + normalized stance 둘 다
    grounding=_logged_grounding(grounding),          # considered trace, fallback_used
    candidate_pool=[_pool_entry(c) for c in candidate_pool],  # survivors + gate.dropped
    dropped=[_drop_entry(c) for c in dropped],       # gate.dropped + filter_dropped 병합
    ranked=[_ranked_entry(c, rank, need) ...],       # 전체 ranking (top-limit 아님)
    reasons=_logged_reasons(recommendation),
    serving=_logged_serving(recommendation),         # silent/reason/returned
    provider_versions=..., ope=OpeBlock(),           # ope는 Alpha 빈 채, Open Beta 채움
)
sink.write(row)
```

### 비자명한 결정
- **`fallback_used=grounding.fallback_used`** (Phase 8A) — rerank fallback이 grounding을 구제하면
  True로 기록되어 serving 경로에선 live. eval은 reranker를 주입하지 않아(offline default) 항상
  False → [ambiguous_fallback_rate](10-eval-metrics-and-gates.md)가 eval에서 0.0인 이유.
- **`need_filter="same_axis_required_stance"` 상수** — 방향은 각 entry의 `stance.dir`에 있음.
  그래서 "against"가 절대 stance 라벨로 오독되지 않고 "유저의 반대 편"으로 읽힘.
- **`ConsideredEntity.confidence`** (score 아님) — 시스템 전역 "no scalar score" 규칙과의 혼동
  방지. entity-linking confidence는 별개 개념.
- **`feature_breakdown`은 raw + derived band 항상** — Post-OB 튜닝이 band cutoff를 refit 가능.
  experience면 source_type/rank도. 타입 `dict[str, float|int|str|None]`.
- **`_drop_entry`/`_stance_log` loud fail** — dropped인데 reason 없거나, ranked stance인데 stance
  없으면 파이프라인 불변식 위반 → `ValueError`. 모순된 row를 조용히 로그하지 않음.
- **dropped 병합** = `gate.dropped + filter_dropped` (P1, 파이프라인 책임). pool = survivors +
  gate.dropped.

---

## `DecisionLogRecord` 구조 (`structs/decision_log.py`)

순수 record (로직 없음). 이게 Open Beta OPE replay가 "왜 이 추천이 나왔나"를 재구성하는 근거:

```
log_id, ts, contract_version
query (LoggedQuery)          — topic, need, raw+normalized stance
grounding (LoggedGrounding)  — resolved_qid, method, fallback_used, considered[]
candidate_pool [PoolEntry]   — agent_id, anchor_id, via, via_qid
dropped [DropEntry]          — agent_id, reason
ranked [RankedEntry]         — rank, feature_breakdown, ordering_keys, stance (no score!)
reasons [LoggedReason]
serving (LoggedServing)      — silent, reason, returned
provider_versions            — mock↔real 비교용 provenance
ope (OpeBlock)               — Alpha 빈 채, 형태만 존재 → Open Beta가 schema 변경 없이 채움
```

- ranked entry에 scalar score 없음, `ordering_keys` + raw `feature_breakdown`으로 대체 → Post-OB
  LTR/threshold 튜닝이 사후에 cutoff를 fit 가능.
- `ope`는 Alpha에서 비었지만 형태가 존재 → Open Beta가 schema 변경 없이 채움.

---

## 파이프라인이 두 "0"을 여기서 어떻게 다루나

- **grounding 0**: linker가 throw → recommend가 전파. row **없음** (추천 자체가 없으니).
- **pool 0**: grounding 됐고 후보 0 → serving이 빈 목록 + `silent=True` 200, row는 **남김**
  (침묵도 결정). P4: 두 개의 "0"이 로그에서 다르게 나타남.

---

**요점:** serving은 top-N 응답을, decision log는 전체 trace를 만듭니다. 이 로그가 다음 절반인
평가 시스템의 원료입니다 — [09. harness](09-eval-harness.md)가 이걸 수집하고
[10. metrics](10-eval-metrics-and-gates.md)가 채점합니다.
