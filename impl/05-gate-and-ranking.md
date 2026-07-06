# 05. gate (③) + ranking (④)

← [개요로 돌아가기](README.md) · 관련: [04. retrieval](04-retrieval.md) ·
[06. serving + decision log](06-serving-and-decision-log.md) · [01. 데이터 계약](01-data-contracts.md)

두 단계를 함께 봅니다. 핵심 분업: **Gate = need-무관 탈락**, **Ranker = need-의존 순서 + stance
필터**. 이 경계가 "왜 여기서 거르고 저기서 거르나"의 답입니다.

---

## ③ Gate (`discovery/gate.py`)

`EdgeHit` → 완성된 `Candidate`. per-agent provider I/O를 **여기서 전부** 처리해서, Ranker를 순수
함수로 남깁니다.

### 두 provider를 바인딩
```python
async def screen(self, hits, *, context):
    # Phase 1: eligibility는 hard-required — 전부 동시 fetch, 첫 실패 전파(swallow 금지)
    eligibilities = await asyncio.gather(*(self._eligibility.check(h.edge.agent_id, context=context) for h in hits))
    # need-무관 partition
    for hit, elig in zip(hits, eligibilities, strict=True):
        reason = _need_agnostic_drop(hit.edge, elig, maturity_min=...)
        (dropped if reason else rankable) ...
    # Phase 2: persona는 optional — survivor에 대해서만 fetch
    personas = await asyncio.gather(*(self._persona.get_prior(h.edge.agent_id) for h, _ in rankable))
```

- eligibility 실패는 전체 gate를 실패시킴 (real provider의 503이 swallow되면 안 됨).
- **dropped 후보는 persona를 안 fetch** — 랭킹 신호인데 랭킹 안 될 거라서.
- `gather()`에 코루틴 0개면 `[]` 반환 → 전부 drop된 pool도 특수 처리 불필요.

### need-무관 drop 우선순위
```python
def _need_agnostic_drop(edge, eligibility, *, maturity_min):
    if not eligibility.discoverable:  return "eligibility"    # 가장 강한 노출 게이트
    if not edge.discoverable:         return "discoverable"
    if edge.maturity < maturity_min:  return "maturity"
    return None
```
**eligibility > discoverable > maturity.** "아예 노출 불가"(eligibility)가 "단지 private"
(discoverable)이나 "미성숙"(maturity)을 이깁니다.

> 주의: `eligibility.discoverable=False` → reason `"eligibility"`, `edge.discoverable=False` →
> reason `"discoverable"`. 둘은 다른 사유. (fixture 발견: elig.discoverable=False면 "eligibility".)

### 산출물
```python
class GateResult:
    survivors: list[Candidate]  # drop_reason None, Ranker로
    dropped: list[Candidate]    # drop_reason 설정, 로그에만
```
off_axis/wrong_stance류는 **여기가 아니라 Ranker**의 need-filter (R2). dropped도 `Candidate`로
반환해서 decision log가 기록.

### 설정 (`config.py: RankingSettings`)
```python
MATURITY_MIN = 0.45   # rankable-eligibility 게이트 floor
```
- **`MATURITY_MIN`(0.45)은 medium cutoff(0.50)보다 일부러 낮음**: 게이트는 "랭크 가능한가"만
  결정(LOW 밴드도 통과 가능), 밴드는 survivor를 정렬. 게이트와 순서는 별개 책임. LOW 밴드로
  살아남는 구간 = `[0.45, 0.50)`.
- 게이트 drop 경계는 유닛 테스트에서 검증 (`tests/test_gate.py`): `maturity=0.3`(< 0.45) →
  `drop_reason="maturity"`; `maturity=0.1` + `discoverable=False` → `"eligibility"`(우선순위).
- **주의 — 커밋된 코퍼스에는 maturity 게이트 탈락이 없음**: `edges.json`의 maturity는 전부
  ≥ 0.52 (최소 0.52, 최대 0.90). 그래서 코퍼스 실행에서 maturity로 탈락하는 후보는 0이고,
  maturity 게이트는 유닛 테스트로만 커버됩니다. ([Phase 7 hard gate](10-eval-metrics-and-gates.md)가
  코퍼스에서 깨끗하게 통과하는 배경 중 하나.)

---

## ④ Ranker (`discovery/ranking.py`)

**provider-free, 결정적** 함수. Gate가 이미 provider를 바인딩했으므로 여기선 I/O 없음. Alpha
랭킹은 **ordering contract** — 가중합 score가 아니라 사전식 정렬 키.

### 정수 rank map (StrEnum 정렬 버그 회피)
```python
MATURITY_BAND_RANK   = {HIGH: 2, MEDIUM: 1, LOW: 0}
EXPERIENCE_SOURCE_RANK = {FIRSTHAND: 2, SECONDHAND: 1, None: 0}
```
StrEnum을 문자열로 정렬하면 `"medium" > "low" > "high"` — 잠재 버그. 그래서 정렬 키는 이 정수를
비교. 이 맵들은 튜닝 threshold가 아니라 **순서 의미론**이라 frozen module 상수
(`MappingProxyType`, 공유되므로 읽기 전용).

### need별 ordering key
```python
DEPTH:      [maturity_band, evidence_strength, freshness, agent_id]
EXPERIENCE: [experience_source_rank, experience_specificity_rank, evidence, freshness, band, agent_id]
FOR/AGAINST:[maturity_band, evidence, freshness, stance_confidence, agent_id]
COVERAGE:   [coverage_group, maturity_band, evidence, freshness, agent_id]
```
모든 순서는 `agent_id asc`로 종료 (완전한 total order → 결정적).

### 순수성 주의
Ranker는 각 `Candidate`를 **in-place로 annotate**(`features`/`ordering_keys`/stance/`drop_reason`)
해서 decision log로 상태를 나릅니다. 즉 referentially pure가 아님 — 같은 Candidate 객체를 여러
rank 호출에 재사용하면 안 됨.

### for/against = 상대적 need (가장 미묘)
```python
required_dir = stance.dir if need == FOR else _OPPOSITE_STANCE[stance.dir]
```
- **`NeedType.FOR → Stance.FOR` 직접 매핑 금지.** 필요 방향은 유저 stance에서 파생: `for`는 같은
  편, `against`는 반대 편.
- drop 우선순위 (`_stance_drop_reason`):
  1. `off_axis` — stance_axis/observed_stance 없음, 또는 axis 불일치 (casefold+strip).
  2. `wrong_stance` — 관측 stance ≠ required_dir.
  3. `low_stance_confidence` — confidence < τ(`STANCE_CONFIDENCE_MIN=0.60`). None은 low 취급.
- `stance_confidence`는 **guard이자 late tiebreak** (게이트는 이미 적용됨, 정렬 키 끝에서 다시).
- 산출: `(kept_ranked, dropped)` — dropped는 need-filter drop으로 로그로.

### coverage = round-robin
```python
groups = candidate.edge.anchor_id 별 그룹
core_anchor = via==DIRECT인 첫 hit의 anchor_id  # 원 앵커
group_order = core 먼저, 그다음 anchor_id asc
# 각 그룹 내부는 _depth_key로 정렬, depth별로 그룹을 순회하며 round-robin
```
한 sub-topic(facet)이 결과를 지배하지 못하게 앵커 그룹을 번갈아 뽑음. (via_qid는 R3 때문에 모든
neighbor hit에서 원 앵커라 facet 구분 불가 → `edge.anchor_id`로 그룹.)

### experience order
`source → specificity → evidence → freshness → band`. firsthand(직접 경험, 낮은 maturity라도)가
abstract high-maturity를 이김. `None`(경험 근거 없음)은 마지막. → **experience ≠ depth 변형.**

### persona
Alpha no-op (hollow guard, [01 문서](01-data-contracts.md) 참조).

---

**요점:** Gate는 "노출해도 되나"(need-무관)를 정하고, Ranker는 "어떤 순서로"(need-의존)를 순수
함수로 정합니다. 둘 다 score를 안 만듭니다 — 순서와 drop 사유만. 다음:
[06. serving + decision log](06-serving-and-decision-log.md)가 이걸 응답과 감사 기록으로 만듭니다.
