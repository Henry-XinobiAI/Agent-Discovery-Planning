# 오프라인 평가 하니스 (`eval/`)

추천 파이프라인을 위한 오프라인 평가 기반. **커밋된 벤치마크 코퍼스**를 실제 서빙
파이프라인(`discovery/`)에 **네트워크 없이, LLM 없이** 그대로 재생(replay)한다. 여기에는 두 개의
레이어가 있다:

- **Phase 6 — 실행 / 커버리지** (`harness.py`, `eval run`): 코퍼스를 재생하고 무슨 일이 일어났는지
  보고한다. 코퍼스가 잘 형성되어 있고, 캡처된 지식 기반에 대해 모든 시나리오가 **끝까지 실행됨(runs to
  completion)**을 증명한다.
- **Phase 7 — 지표 + 게이트** (`metrics.py`, `gates.py`, `eval gate`): 그 실행을 커밋된 gold와 얼려둔
  **ratchet baseline**에 대해 채점하고, CI pass/fail 종료 코드를 만들어낸다.

> **레이어 경계 (중요).** 실행 자체와 그 `EvalRun` 요약은 **점수가 없다(score-free)** — `harness.py` /
> `eval run` 어디에도 의도적으로 score, pass/fail, threshold, judge가 없다. 채점은 엄격히 한 레이어
> 위에 산다: `eval/metrics.py`가 실행의 decision-log 기반으로부터 `MetricReport`를 계산하고,
> `eval/gates.py`가 그것을 `baseline.json`에 대한 pass/fail로 바꾼다. 모든 채점은 **결정적 gold — LLM
> judge 없음** 위에서 이루어진다 (safety/exposure 게이트는 절대 확률적 judge에 올라타서는 안 된다);
> silver 라벨을 만드는 LLM judge는 **Phase 8**이다. 경계를 지켜라: 하니스나 요약에 threshold를 절대
> 추가하지 마라 — 그건 `metrics`/`gates`에 속한다.

`eval/`은 `discovery/`(도메인)에서 import해도 되지만, **`discovery/`와 `api/`는 절대 `eval/`을
import해서는 안 된다** — 서빙 그래프는 mock-free로 유지된다. 이는
`tests/test_import_isolation.py`로 강제된다.

---

## 1. 무엇을, 왜 평가하는가

추천 요청은 고정된 파이프라인(`discovery/pipeline.py`)을 통과한다. 하니스는 시나리오마다
`pipeline.recommend()` 호출을 한 번씩 구동하고 결과를 기록한다:

| # | 스테이지 | 모듈 | eval이 무엇을 검증하는가 |
|---|-------|--------|--------------------------|
| ⓠ | 정규화(Normalize) | `discovery/normalize.py` | query → 정규화된 need + stance |
| ① | **Linker** | `discovery/linker.py` | topic 텍스트 → 단일 anchor QID, **캡처된** `/knowledge/entities*` 응답에 grounding (기호적 label 매칭; LLM 없음, popularity 없음) |
| ② | **Retrieval** | `discovery/retrieval.py` | anchor QID → 후보 에이전트 (direct edge + sparse one-hop 확장) |
| ③ | **Gate** | `discovery/gate.py` | need-agnostic drop: `eligibility > discoverable > maturity` |
| ④ | **Ranking** | `discovery/ranking.py` | need별 ordering + for/against stance 필터. **ordering contract** — `rank`만 사용하고, scalar score는 절대 없다 (§4.2) |
| ⑤ | **Serving** | `discovery/serving.py` | 응답 payload + silence 결정 |
| ⑥ | **Decision log** | `discovery/decision_log.py` | 요청마다 찍히는 완전한 감사(audit) 기록 |

**왜 real anchor가 중요한가 ("real anchor = teeth").** Grounding은 진짜로 가짜로 꾸미기 어려운 유일한
스테이지다. 장난감 entity 목록에서 검색 결과를 계산하는 대신, linker는 `anchors.json`에 대해
실행된다 — **실제 memory-api `/knowledge/entities*` 응답의 얼려둔 캡처**(또는 같은 형태를 가진
손으로 작성한 대체물). 그래서 linker는 진짜 provider 출력에 대해, 오프라인으로 결정적으로 평가된다.
edge/persona/eligibility provider는 mock이며(Alpha에는 실제 소스가 없다), 코퍼스 fixture에서 공급된다.

**다섯 개의 Phase 6 green bar (build_plan §6)** — 코퍼스는 잘 형성되고 오프라인 실행 가능한
벤치마크다 (`tests/eval/test_corpus_acceptance.py`):

1. 모든 코퍼스 파일이 **schema-validate**되고, 파일 간 참조가 해소된다 (dangling / 중복 row 없음).
2. 모든 `edge.anchor_id`는 anchored provider가 **재생할 수 있는 QID**다 (`∈ anchors.entities`).
3. 네 개의 **strata**가 모두 비어 있지 않고, 모든 **need**가 ≥ 20개의 시나리오를 갖는다.
4. 아홉 개의 Alpha-active **guard** 각각이 ≥ 1개의 커버리지 fixture를 갖고, need당 **needle**이 ≥ 1개다.
5. `eval run`이 `errored == 0`으로 **오프라인 완료**된다 (memory-api down 상태).

**Phase 7 green bar** — 채점된 실행이 모든 게이트를 통과한다
(`tests/eval/test_phase7_acceptance.py`), 전부 결정적 gold 위에서:

6. **Hard gate** 통과: `must_not_show` false-pass = 0, discoverability-off exposure = 0, needle
   top-1 = 100%, easy/needle retrieval recall = 100%.
7. **Ratchet** 지표가 실제(비어 있지 않은) 분모 위에서 측정되어 `baseline.json`에 얼려진다
   — grounding top-1 / top-3 및 ambiguous fallback rate; 실행은 이 값들 아래로 regress할 수 없다.
8. **완료된 시나리오당 정확히 하나의 schema-valid decision-log 기록**; 보고서가 byte-reproducible하며;
   커밋된 baseline이 코퍼스와 **in sync**이고; `eval gate`가 0으로 종료된다.

---

## 2. 데이터

모든 것은 `eval/corpus/` 아래에 산다. 커밋된 벤치마크는 **평평한(flat) fixtures 디렉터리**다 — 러너
(`run_eval(corpus_dir=…)`)가 `anchors.json`과 함께 한 디렉터리에서 `agents/edges/scenarios/gold.json`을
읽는다.

```
eval/corpus/
  baseline.json             # Baseline        — Phase 7 게이트가 비교하는, 얼려둔 ratchet floor
  seeds/
    anchor_queries.json     # 큐레이션된 [{query_id, query, expected_qid}] — build-anchors 입력
  fixtures/
    anchors.json            # PinnedAnchorFixture — 캡처된 지식 기반 (grounding이 이 위에서 실행됨)
    agents.json             # AgentFixture[]  — agent_id + persona prior + eligibility 판정
    edges.json              # AgentTopicEdge[] — 실제 QID 위의 agent↔topic 전문성 edge
    scenarios.json          # Scenario[]      — eval 쿼리 (need × anchor, + guard row)
    gold.json               # GoldLabel[]     — 합성 relevance 라벨 (Phase 7 채점 gold)
```

`eval/output/`(빌드 스크래치)와 `**/*.silver.json`(Phase 8 judge 라벨)은 git-ignore된다.

### `anchors.json` — 지식 기반 (`PinnedAnchorFixture`)

memory-api의 오프라인 재생. `AnchoredKnowledgeProvider`를 뒷받침하며, 이는 얼려둔 응답을 재생함으로써
다섯 개의 `/knowledge/entities*` 읽기 메서드를 서빙한다:

- `queries[]` — 쿼리별: `query`, `limit`, 캡처된 `search` / `suggest` 후보 목록, 그리고 linker가
  채택해야 할 `expected_qid` (validator가 이것이 캡처된 후보 중에 있음을 assert한다).
- `entities` / `connections` / `articles` — `get` / `expand_connections` / `search_articles`용의
  QID-keyed 상세 저장소.
- `contract` — 출처(provenance): `memory_api_commit`, `entity_contract`, `generated_at`.

**출처 — `manual-seed` vs. 실제 캡처 (D8).** 커밋된 fixture는 현재
`memory_api_commit="manual-seed"`이다: 각 쿼리가 단일 **exact-label** 후보로 해소되도록 손으로 작성한
대체물이며, 그래서 grounding은 confidence `1.0` / margin `1.0`으로 안착하고 모든 시나리오가 깨끗하게
ground된다. `limit`은 `20`이다 (linker의 후보 limit과 일치 — provider의 캡처-지평(capture-horizon)
가드). dense baseline pool이 one-hop expand를 절대 트리거하지 않기 때문에 `connections`는 비어 있고,
Alpha의 후보 경로가 그것들을 사용하지 않기 때문에 `articles`도 비어 있다. memory-api에 도달 가능해지면
`build-anchors`가 이것을 진짜 캡처로 **backfill**한다 (실제 `memory_api_commit`, 그리고 채워진
`connections`); 모든 구조적 보장은 어느 쪽이든 유지된다.

### `scenarios.json` — eval 쿼리 (`Scenario`)

baseline은 **(need, anchor)**마다 시나리오 하나(5 need × 20 anchor = 100), 여기에 guard마다 태그된
**guard 커버리지** 시나리오 하나(11)를 더한다. 각 시나리오는 다음을 갖는다:

- `need_type` — `depth` / `experience` / `for` / `against` / `coverage` 중 하나.
- `anchor_query_id` — `anchors.queries[]`로 들어가는 **안정적 handle** (시나리오↔anchor 링크가 topic
  텍스트가 아니라 id로 키잉되므로, 문구를 편집해도 링크가 조용히 깨질 수 없다). `topic_text`는 런타임에
  linker가 ground하는 대상이며; 로더는 이 둘이 같은 것으로 정규화됨을 교차 확인한다.
- `stratum` — 난이도 밴드: `easy` / `hard`(ranking-hard: 근접하게 동점인 maturity) / `ambiguous`
  (거의 동등한 경쟁 후보) / `guard`.
- `is_needle` — known-item 프로브: 정확히 한 에이전트가 rank-1을 차지해야 한다. need당 needle ≥ 1개.
- `user_stance_ref` / `expected_axis` — `for` / `against`에만 존재하고 방향성을 가진다.
- `tags` — coverage row의 guard 이름.

for/against는 **상대적(relative)** need다: 코퍼스는 항상 유저 자신의 stance를 `for`로 선언하므로,
`for` 시나리오는 같은 방향 에이전트를 유지하고 `against` 시나리오는 반대 편을 유지한다.

### `edges.json` — 전문성 edge (`AgentTopicEdge`)

`build-guards`/`build`는 anchor당 에이전트의 dense pool(`POOL_SIZE = 5`)을 합성하며, 각 edge는
anchor의 **실제 QID** 위에 있고, `maturity`, anchor 축 위의 `stance`, 그리고 experience 출처를 담는다.
seed에 의해 지터되는 것은 부차적 신호(evidence / freshness / stance-confidence)뿐이다; maturity
사다리(밴드, needle 승자, gate 결과를 결정)는 고정되어 있다.

### `agents.json` — 에이전트 기록 (`AgentFixture`)

12개의 에이전트, 각각이 `PersonaPrior`(Alpha에서는 no-op prior)와 `Eligibility` 판정을 하나의
`agent_id` 아래에 묶는다 (세 개의 id가 일치해야 한다).

### `gold.json` — 합성 라벨 (`GoldLabel`)

(시나리오, 후보 에이전트)마다의 기계적 라벨 — **regression seed이지 인간의 품질 주장이 아니다** —
그리고 **Phase 7 지표 레이어가 채점하는 대상**인 gold. `source`는 `synthetic`으로 고정되고 모든
`rationale`은 `synthetic_rule:`을 접두어로 갖는다. 그래서 하위 지표가 이것을 어떤 품질 집계에서든
제외할 수 있다. 규칙은 파이프라인 자신의 게이트를 **우선순위 순서로** 그대로 반영한다:
not-discoverable → `must_not_show`(exposure 게이트가 needle보다도 우선); 아니면 지정된 needle 승자
→ `ideal`; 아니면 stance need에서 off-axis/wrong-side/low-confidence → `bad`; 아니면 maturity floor
아래 → `bad`; 아니면 maturity 밴드 → `ideal` / `acceptable`. 인간(`b1_human`)과 LLM-silver
(`b2_silver`) 계층은 후속 phase다.

### `baseline.json` — 얼려둔 ratchet floor (`Baseline`)

Phase 7 게이트가 각 실행을 비교하는, 커밋된 floor. `corpus_version`(출처)과 세 개의 **ratchet**
지표만 담는다 — `grounding_top1`, `grounding_top3`, `ambiguous_fallback_rate` — 각각을
`{value, count, total}`로 (게이트는 `value`로 비교하고; count/total은 리뷰용). **hard-gate** 지표는
여기 *없다*: 그것들의 threshold(`= 0` / `= 100%`)는 코드에 고정되어 있고 절대 ratchet되지 않는다.
`eval gate --update-baseline`이 작성하며 diff-stable하다 (정렬된 키, 2-space indent, 끝 개행). 수락
스위트는 이것이 코퍼스와 in sync로 유지됨을 assert하므로, re-baseline 없이 코퍼스를 바꾸면 시끄럽게
실패한다.

### 아홉 개의 Alpha-active guard (`§8.3`)

Guard는 특정 파이프라인 동작을 고정하는 적대적(adversarial) 시나리오다. 의도적으로 분리된 **두 개의
레이어**가 있다:

- **Coverage row** (`eval/builders/guards.py`) — guard마다 태그된 `guard`-stratum 시나리오 하나,
  코퍼스에 병합되어 "guard-9 각각 ≥ 1"이 셈 가능해진다. Coverage row는 동작 증명이 **아니다**.
- **Behavior proof** (`tests/eval/guards/test_guard_assertions.py`) — 각 guard가 가장 명료한
  파이프라인 스테이지를 통해, 목적 지향으로 만든 inline fixture로 구동되어, 선언된 불변식을 assert한다.

| Guard | Assertion |
|-------|-----------|
| `retrieval-expansion` | cold anchor ⇒ sparse가 one-hop expand 트리거 (이웃 QID가 떠오름); dense ⇒ expand 없음 |
| `ambiguous-topic` | confidence/margin이 게이트 아래 ⇒ `grounding_failed` raise |
| `same-axis-disagreement` | `for`는 같은 방향 유지 / `against`는 반대 유지; 틀린 편은 need-filter가 drop |
| `weak-evidence-low-maturity` | 낮은 **maturity** 에이전트가 maturity floor에서 drop (evidence는 ordering 키이지 gate가 아님) |
| `experience-vs-depth` | `experience`에서, 직접경험(더 낮은 maturity)이 추상적 high-maturity 위에 랭크 |
| `high-persona-low-memory` | 높은 persona가 low-maturity 에이전트를 **구하지 못함** (persona는 Alpha에서 no-op) |
| `stale-but-valuable` | stale 에이전트가 **배제되지 않음** (freshness는 soft 키, cutoff 없음); 더 낮게 랭크되되 사라지지 않음 |
| `discoverability-off` | `edge.discoverable=false` ⇒ 이유 `discoverable`; `eligibility.discoverable=false` ⇒ 이유 `eligibility` |
| `rerank-injection` | Alpha에는 LLM rerank 없음 ⇒ well-formed + 태그만 (실제 assertion은 Phase 8) |

두 개의 placeholder guard(`established-axis-ambiguity`, `favorite-bypass`)는 tag-only, assertion 없음.

---

## 3. 실행 방법

모든 명령은 repo 루트에서 `uv` 아래 실행된다. `eval run`, `build`, `build-guards`는 완전히
오프라인이며; `build-anchors`만 live memory-api가 필요하다.

### 커밋된 코퍼스에 대해 eval 실행 (오프라인)

```bash
uv run python -m cli eval run \
  --corpus eval/corpus/fixtures \
  --anchors eval/corpus/fixtures/anchors.json
# 기계-판독 가능한 payload는 --format json 추가
# 시나리오가 errored여도 exit 0을 강제하려면 --allow-errors 추가 (로컬 디버그 탈출구 전용)
```

**종료 코드:** 모든 시나리오가 완료됐을 때만 `0`. 어떤 시나리오라도 errored면, 기본적으로 명령은
**non-zero**로 종료된다 — 숨겨진 시나리오별 실패가 green으로 읽혀서는 안 된다. `--allow-errors`는 그것을
`0`으로 강등한다 (errored 개수는 여전히 표시됨); 수락 테스트나 CI에서는 절대 사용되지 않는다.

### gold + baseline에 대해 실행을 게이트 (오프라인 — 이것이 CI 계약)

```bash
uv run python -m cli eval gate \
  --corpus eval/corpus/fixtures \
  --anchors eval/corpus/fixtures/anchors.json \
  --baseline eval/corpus/baseline.json
# {report, gate, baseline_updated} 봉투는 --format json 추가
# 이 실행으로부터 baseline을 재-freeze하려면 --update-baseline 추가 (아래 참조)
```

**종료 코드:** `errored == 0`이고 **동시에** 게이트가 통과할 때만 `0` — precondition, hard-gate,
ratchet 위반 없음. baseline 누락(`--update-baseline` 없이)도 실패한다. 보고서는 **stdout**으로
출력되고(그래서 `--format json`이 기계-청결하다); `PASS` / `FAIL` 판정과 진단은 **stderr**로 간다.

**Re-baselining.** `--update-baseline`은 현재 실행의 ratchet 지표를 `baseline.json`에 freeze하고
ratchet 비교를 건너뛴다 — 하지만 실행이 유효한 floor일 때(`errored == 0`이고 precondition / hard-gate
실패 없음)만이다; 그렇지 않으면 거부하고 non-zero로 종료한다. 작성된 값을 리뷰하고 커밋하라. 이것이
ratchet이 정당하게 올라가는 방법이다 (예: grounding 개선 이후).

### anchor로부터 코퍼스 재빌드 (오프라인, 결정적)

```bash
# 전체 벤치마크 = baseline + guard coverage row (이것이 커밋된 것):
uv run python -m cli corpus build-guards --anchors eval/corpus/fixtures/anchors.json --out eval/output --seed 0

# baseline만 (guard row 없음):
uv run python -m cli corpus build --anchors eval/corpus/fixtures/anchors.json --out eval/output --seed 0
```

결정적 (D5): 같은 `anchors.json` + `--seed`는 **byte-identical** 출력을 만든다 (정렬된 키, 고정 indent,
끝 개행). 커밋된 코퍼스는 `--seed 0`으로 빌드되었다.

### live memory-api로부터 anchor 갱신 (backfill)

```bash
uv run python -m cli corpus build-anchors \
  --seeds eval/corpus/seeds/anchor_queries.json \
  --out eval/corpus/fixtures/anchors.json \
  --memory-api-commit <memory-api-sha>          # anchors.json에 찍히는 출처
  # --memory-api-url http://localhost:8080      # 선택; 생략하면 MemoryApiSettings 사용
```

`build-anchors`는 seed마다 live provider를 한 번씩 쿼리하고, 응답을 freeze하고, 출처를 찍는다. seed의
`expected_qid`가 upstream에 없거나 캡처된 후보에 없으면 **시끄럽게 실패**한다 (stale seed / memory-api
drift가 조용히 얼려져서는 안 된다). memory-api에 도달할 수 없으면 안내와 함께 non-zero로 종료한다. 성공적
캡처 후, 수락 테스트를 재실행하고 새 `anchors.json` + 재생성된 코퍼스를 커밋하라.

### 테스트 실행

```bash
uv run pytest tests/eval/test_corpus_acceptance.py    # Phase 6 커밋된-코퍼스 green bar (7 테스트)
uv run pytest tests/eval/test_phase7_acceptance.py    # 커밋된 코퍼스에 대한 Phase 7 게이트 green bar
uv run pytest tests/eval/test_metrics.py              # 순수 지표 레이어 (지표별 유닛 테스트)
uv run pytest tests/eval/test_gates.py                # 게이트 + baseline 레이어
uv run pytest tests/cli/test_eval.py                  # eval run / eval gate CLI 배선
uv run pytest tests/eval/guards/                      # 아홉 개 guard 동작 증명
uv run pytest tests/test_import_isolation.py          # discovery/api는 절대 eval/를 import하지 않음
```

---

## 4. 출력

`eval run`은 **실행 / 커버리지 요약**을 출력한다 — 개수와 시나리오별 결과, 그리고 판정처럼 보이는 것은
아무것도 없다.

### `--format table` (기본)

Need별 row, 그다음 한 줄 footer:

```
need         scenarios completed errored   recs needles
depth               29        29       0    145       1
experience          21        21       0    105       1
for                 21        21       0     63       1
against             20        20       0     40       1
coverage            20        20       0    100       1
run_id=run_… corpus_version=manual-seed scenarios=111 completed=111 errored=0
```

- `scenarios` / `completed` / `errored` — need의 실행 개수.
- `recs` — need의 시나리오 전반에서 방출된 추천 총합.
- `needles` — need 안의 needle 시나리오 (각 ≥ 1).

### `--format json`

전체 `EvalRun` payload (`by_need`와 `by_stratum` 두 축 모두, 그리고 모든 시나리오):

```jsonc
{
  "run_id": "run_…",                 // CLI 경계에서 주입 (uuid)
  "corpus_version": "manual-seed",   // == anchors.json contract.memory_api_commit
  "generated_at": "2026-…Z",         // 주입됨 (하니스 내부에서는 절대 datetime.now() 아님)
  "summary": {
    "scenario_count": 111, "completed": 111, "errored": 0,
    "recommendation_count": 453, "needle_count": 5
  },
  "by_need":    [ { "key": "depth", "scenarios": 29, "completed": 29, "errored": 0,
                    "recommendations": 145, "needles": 1 }, … ],
  "by_stratum": [ { "key": "easy",  "scenarios": …, … }, … ],   // easy / guard / hard / ambiguous
  "scenarios": [
    {
      "scenario_id": "depth-aq00",
      "need": "depth",
      "anchor_query_id": "aq00",
      "expected_anchor_qid": "Q28865",
      "adopted_anchor_qid": "Q28865",         // grounding이 실제 채택한 것 (errored면 null)
      "recommendations": [
        // rank만 — 절대 score 아님 (§4.2); reason은 결정적 문자열, LLM 없음
        { "agent_id": "a00", "rank": 1, "reasons": ["maturity 0.90 · evidence 0.85 · freshness 0.80"] }
      ],
      "silent": false,
      "decision_log_id": "dl_…",
      "status": "completed"                    // completed | errored
    }, …
  ]
}
```

**재현성.** `run_id` / `corpus_version` / `generated_at`을 동일하게 주입하면, 같은 코퍼스에 대한 두
번의 `run_eval` 호출이 **byte-identical** JSON을 만든다 (수락 테스트가 canonical serialization으로 이를
assert한다). **CLI** 경로는 의도적으로 byte-stable이 *아니다* — `run_id`를 uuid로, `generated_at`을
now로 찍는다.

**계약 가드.** payload에는 절대 `score` / `judge` / `threshold` / `pass` / `fail` 키가 포함되지 않는다.
추천은 `rank`만 담는다. 이는 하니스 테스트가 assert한다 — Phase 6/7 경계를 기계적으로 만든 것이다.

---

## 5. 게이트 (`eval gate`)

`eval gate`는 같은 실행을 채점하고 게이트를 적용한다. **보고서는 stdout으로 간다**; `PASS` / `FAIL` /
`UPDATED` 판정은 **stderr**로 가서, JSON 소비자는 봉투만 본다.

### `--format table` (기본)

```
Hard gates:
  must_not_show_false_pass      0
  discoverability_off_exposure  0
  needle_top1                   1.000 (5/5)
  retrieval_recall_easy_needle  1.000 (200/200)
Ratchet:
  grounding_top1                1.000 (111/111)
  grounding_top3                1.000 (111/111)
  ambiguous_fallback_rate       0.000 (0/25)
Gate: PASS
```

각 ratio는 `value (count/total)`로 출력된다. 실패 시 `Gate: FAIL` 다음에 위반당 한 줄씩,
**precondition → hard_gate → ratchet** 순서로 온다 (해석 불가능한 지표가 그 threshold보다 먼저 떠오른다
— 예: 빈 분모).

### `--format json`

stdout에 기계-청결한 단일 봉투:

```jsonc
{
  "report": { /* MetricReport: 네 개 hard-gate 지표, 세 개 ratchet Ratio,
                 by_need / by_stratum breakdown, 그리고 precondition_violations */ },
  "gate":   { "passed": true, "violations": [] },   // --update-baseline일 때 null (비교 건너뜀)
  "baseline_updated": false
}
```

### 게이트가 결정하는 방법

- **Hard gate** (코드에 고정, 절대 ratchet 아님): 두 개의 exposure/safety 개수는 `0`이어야 하고; 두
  개의 known-item ratio는 `100%`여야 한다 (정확히 `count == total`로 비교).
- **Ratchet** (`baseline.json`에 freeze, 방향은 `RATCHET_DIRECTIONS`에 따름): higher-is-better
  (`grounding_top1/top3`)는 baseline 아래로 떨어질 수 없고; lower-is-better
  (`ambiguous_fallback_rate`)는 그 위로 올라갈 수 없다 (둘 다 `EPS = 1e-9` 이내). baseline 항목 누락은
  그 자체로 위반이다.
- **Precondition** (시끄럽게, 먼저 확인): 고유한 `ideal`이 없는 needle, 또는 분모가 빈 임의의 gated
  지표 — *해석*될 수 없는 지표는 그 threshold가 저울질되기 전에 실패한다.

`ambiguous_fallback_rate`는 Alpha에서 `0.0`이다. linker에 rerank fallback 경로가 없기 때문이다
(`fallback_used`는 항상 `false`); ratchet 슬롯은 실재하지만 잠잠하며, fallback이 안착하는 Phase 8에서
teeth를 갖게 된다.
