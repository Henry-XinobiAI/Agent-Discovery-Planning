# 05. gate (③) + stance (④a) + ranking (④b)

← [개요로 돌아가기](README.md) · 관련: [04. retrieval](04-retrieval.md) ·
[06. serving + decision log](06-serving-and-decision-log.md) · [01. 데이터 계약](01-data-contracts.md)

세 단계를 함께 봅니다. 핵심 분업: **Gate = need-무관 탈락** · **stance = for/against 입장 판정(I/O)** ·
**Ranker = need-의존 순서 + stance 필터(순수)**. 이 경계가 "왜 여기서 거르고 저기서 거르나"의 답입니다.

---

## ③ Gate (`discovery/gate.py`)

`EdgeHit` → 완성된 `Candidate`. per-agent provider I/O를 **여기서 전부** 처리해서, Ranker를 순수
함수로 남깁니다.

### 두 provider를 바인딩 — **agent당 1회** 질문
```python
async def screen(self, hits, *, context):
    # Phase 1: eligibility는 hard-required — unique agent당 1회 동시 fetch, 첫 실패 전파(swallow 금지)
    eligibilities = await _fetch_once_per_agent(
        (hit.edge.agent_id for hit in hits), partial(self._eligibility.check, context=context))
    # need-무관 partition (검사는 edge별)
    for hit in hits:
        reason = _need_agnostic_drop(hit.edge, eligibilities[hit.edge.agent_id], maturity_min=...)
        (dropped if reason else rankable) ...
    # Phase 2: persona는 optional — survivor를 가진 agent당 1회
    personas = await _fetch_once_per_agent((hit.edge.agent_id for hit in rankable), self._persona.get_prior)
```

- **eligibility·persona는 agent-level 판정**이므로 `_fetch_once_per_agent`(`gate.py:73`)가 unique agent당
  한 번만 묻고 그 agent의 모든 edge가 결과를 공유합니다. 한 agent가 여러 anchor에 걸치는 pool(②)에서
  edge마다 물으면, real provider가 한 요청 안에서 다르게 답할 때 같은 agent의 edge들이 **모순된 verdict**를
  갖게 됩니다. `dict.fromkeys`로 first-appearance 순서 유지, `gather`(no `return_exceptions`)로 첫 실패 전파.
- **per-edge 검사(maturity·`edge.discoverable`)는 그대로 edge별**입니다 — 그건 edge 필드니까. 그래서 한
  agent의 미성숙 edge는 탈락하고 형제 edge는 살아남을 수 있습니다.
- eligibility 실패는 전체 gate를 실패시킴 (real provider의 503이 swallow되면 안 됨).
- **dropped 후보는 persona를 안 fetch** — 랭킹 신호인데 랭킹 안 될 거라서. 단 이 규칙은 **agent 기준**:
  한 edge가 drop돼도 형제 edge가 필요한 prior는 fetch되고, 두 edge가 다 살아도 재fetch하지 않습니다.
- 공유된 prior가 후보들을 결합시키지 않는 근거는 `StrictBaseModel`의 `revalidate_instances="always"` —
  nested 컨테이너까지 deep-revalidate해 **후보별 별 인스턴스**가 됩니다(`tests/test_gate.py`가 mutation으로
  고정).
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
`stance_unevaluated`/`wrong_stance`류는 **여기가 아니라 Ranker**의 need-filter (R2). dropped도
`Candidate`로 반환해서 decision log가 기록.

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

## ④a stance 평가 (`discovery/stance.py`) — Gate와 Ranker 사이

for/against일 때만 끼어드는 단계입니다. Gate가 Candidate를 완성한 **뒤**, Ranker가 정렬하기 **전에**
각 후보의 query-time stance를 채웁니다. 여기 있는 이유가 곧 설계입니다:

- **Gate 뒤**여야 하는 이유 — 근거 검색은 **eligibility 통과한 owner에게만** 나갑니다. Gate 앞에 두면
  노출 불가 판정을 받을 사람의 발언까지 검색하게 됩니다.
- **Ranker 앞**이어야 하는 이유 — Ranker는 provider-free 순수 함수라는 계약이라, LLM·HTTP를 하는 일은
  전부 그 밖으로 밀어냅니다. Ranker는 이미 채워진 필드를 **읽기만** 합니다.

흐름은 `hard-K 선별 → symmetric query 생성(LLM 1콜) → owner-scoped 검색(provider 호출 1회) → owner별
judge(각 1콜) → 후보에 verdict 주입`입니다. **provider 호출 1회가 HTTP 1회는 아닙니다** — 어댑터가 owner
20명 chunk로 `ceil(K/20)`개 POST를 냅니다. 단계별 계약과 6가지 침묵 사유는
**[00. 파이프라인 I/O 참조](00-pipeline-io-reference.md)의 ④a 절**에 정리돼 있습니다.

**★ hard-K의 단위 = distinct agent** (`stance_shortlist`, spec §D2). K가 묶는 비용(검색 fan-out ·
후보별 judge 콜)이 agent당 발생하는데 이 단계의 입력은 **edge**라서(② 확장에서 한 사람이 여러 facet),
edge를 K개 세면 형제 edge 둘이 슬롯 둘을 먹고 judge는 한 번만 나갑니다. 그래서 후보는 세 상태로
갈립니다 — **kept**(대표 없는 agent의 첫 edge + K 여유) / `duplicate_agent_edge`(형제가 대표로 judge됨) /
`stance_shortlist_limit`(K 소진 후 처음 본 agent와 **그 agent의 모든 edge** — 아무것도 judge 안 됨).
뒤의 두 사유를 합치면 "판정됐다"와 "판정 자체가 없었다"가 로그에서 구분되지 않습니다.

여기서 꼭 짚을 두 가지:

- **판정은 절대값이고, 방향 적용은 Ranker 몫입니다.** judge는 `need_type`을 아예 모릅니다 —
  `supports`/`opposes`/`insufficient`만 냅니다. 요청한 쪽만 남기는 건 아래 `_REQUIRED_POSITION`이 합니다.
  이 분업 덕에 "for 요청이라 for 쪽으로 기운 판정"이 구조적으로 불가능합니다.
- **evaluator는 `drop_reason`을 안 답니다.** `insufficient`거나 judge가 실패한 후보는 stance 필드를
  **그냥 안 채운 채** Ranker로 갑니다. drop 사유를 붙이는 주체를 하나(Ranker)로 유지하려는 것.

---

## ④b Ranker (`discovery/ranking.py`)

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
모든 순서는 `agent_id asc`로 종료 — **서로 다른 agent 사이에서는 total order**이고 결정적입니다. 같은
agent의 형제 edge끼리는 `agent_id`가 같으므로 이 키가 tie를 못 깹니다(아래 "대표 edge" 절의 완전 동점 항).

### ★ 대표 edge — "한 agent를 대표하는 edge"는 ranking 결정
한 agent는 ranked slot을 **최대 1개**만 가집니다. 그런데 pool은 한 agent의 edge를 여러 개 담을 수
있습니다(② one-hop 확장에서 같은 사람이 여러 이웃 facet에 걸림). 그 중 누가 대표인지를 **Ranker가**
정하고 나머지를 `duplicate_agent_edge`로 drop합니다 (2026-08-04 `24ebc2d`).

**왜 retrieval이 아닌가.** ②는 need를 모릅니다. traversal 순서로 하나만 남기면 experience 요청에
firsthand edge가 아닌 쪽이 대표가 되거나, 심하면 **게이트를 통과할 edge가 통과 못 할 edge에 가려**
후보가 0이 됩니다. 실제로 real run `run-72ecb8940fb5`가 그렇게 `no_candidates`가 됐습니다 — maturity
0.500 edge(게이트 통과)가 0.250 edge(탈락)에 가려짐.

**규칙:** 대표 선택은 **그 need의 기존 ordering key로** 합니다. 새 tiebreak key를 만들지 않고, depth
중심 규칙을 다른 need에 강요하지도 않습니다. 적용 지점은 need별로 key가 확정되는 **가장 이른 곳**:

| need | 지점 | 함수 |
|---|---|---|
| depth / experience | 정렬 **후** 1회 스캔 | `_keep_one_edge_per_agent` (`ranking.py:57`) |
| coverage | round-robin **안** (skip-and-backfill) | `_coverage_round_robin` (`ranking.py:187`) |
| for / against | `stance_shortlist` **안** (judge 앞) | `stance_shortlist` (`ranking.py:106`) |

- **coverage는 사후 dedupe가 불가**합니다: 중복을 정렬 뒤에서 지우면 그 facet 그룹이 슬롯을 **통째로
  잃습니다**(round-robin이 이미 그 자리를 그 그룹에 배분한 뒤라서). 그래서 그룹별 커서로 이미 대표된
  agent를 **건너뛰고 그 그룹의 다음 후보로 backfill**합니다 — 대표 하나를 잃은 게 facet 하나를 잃는
  일이 되지 않게.
- **for/against는 judge 앞**이라 K의 단위가 걸립니다 → 위 ④a 절의 `stance_shortlist`.
- **★ 형제 edge가 need 키에서 완전 동점이면 입력 순서가 대표를 정합니다.** ordering key는 `agent_id`로
  끝나는데 형제끼리는 그 값이 같으므로, need-specific feature까지 전부 같으면 **키가 tie를 깨지 못하고**
  Python stable sort가 **retrieval traversal 순서**(provider 응답 순 → `gather` 이웃 순, 결정적)를 그대로
  둡니다. 이건 결함이 아니라 **정책**입니다 — 그 need의 기준으로 두 edge가 정확히 동등하다면 어느 쪽을
  골라도 랭킹은 같고, tie를 깨려고 `anchor_id` 같은 **새 key를 추가하지 않는다**는 것이 이 설계의 규칙이기
  때문입니다(그 key는 need와 무관한 선호를 몰래 들여옵니다). 대신 **결과로 남는 것**은 봐야 합니다:
  `RankedEntry.anchor_id`와 edge-level 지표가 보는 anchor가 이 경우 입력 순서에서 나옵니다. 키로 결정되길
  원하게 되면 그때 `anchor_id` 최종 tiebreak를 **계약과 코드에 동시에** 넣습니다(현재는 미도입).
- 산출: `rank()`는 `(ranked, ranking_dropped)`를 반환하고, `ranking_dropped`에는 **모든 need의**
  `duplicate_agent_edge`와 for/against의 stance 필터 drop이 함께 들어갑니다. 즉 비-stance need에서도
  non-empty일 수 있습니다.

### 순수성 주의
Ranker는 각 `Candidate`를 **in-place로 annotate**(`features`/`ordering_keys`/stance/`drop_reason`)
해서 decision log로 상태를 나릅니다. 즉 referentially pure가 아님 — 같은 Candidate 객체를 여러
rank 호출에 재사용하면 안 됨.

### for/against = 절대적 need (가장 미묘)
```python
_REQUIRED_POSITION = {NeedType.FOR: StancePosition.SUPPORTS, NeedType.AGAINST: StancePosition.OPPOSES}
required = _REQUIRED_POSITION[query.need_type]
```
- **need_type이 요구 position을 직접 정합니다.** 유저 stance를 기준점으로 잡고 `for`=같은 편 /
  `against`=반대 편으로 파생하던 상대 규칙(`_OPPOSITE_STANCE`)은 폐기됐습니다. 질문이 "유저와 같은
  편인가"에서 "이 주장을 지지하는가"로 바뀌었기 때문입니다.
- **랭커는 edge를 읽지 않습니다.** 비교 대상은 오직 `Candidate.stance_position` — ④a stance 단계에서
  judge가 채운 **query-time** 값. `edge.observed_stance`는 memory 소유 필드로 남아 있지만 랭킹 입력이
  아닙니다.
- drop 우선순위 (`_stance_drop_reason`):
  1. `stance_unevaluated` — **Ranker까지 도달했는데** `stance_position is None`인 후보. 네 경로가
     여기로 모입니다: 후보별 judge가 `insufficient`를 냈거나, judge가 `None`(엔진 실패)을 냈거나,
     평가기가 **처리한** evidence 실패로 후보가 손대지 않은 채 돌아왔거나, eval mirror의
     proposition-match 가드에 걸린 경우. **edge stance로 폴백하지 않는다**는 계약이 이 한 줄로 강제됩니다.
  2. `wrong_stance` — `stance_position != required`.
  3. `low_stance_confidence` — `stance_confidence < τ`(`STANCE_CONFIDENCE_MIN=0.60`). None은 low 취급.
- **`off_axis` drop 사유가 사라졌습니다.** 폐기된 것은 **production Ranker의 axis 비교 단계와 그 drop
  사유**이지, `stance_axis` 필드 자체가 아닙니다(frozen edge 계약과 eval 코퍼스에 그대로 남아 있음).
  관련성 판정은 이제 judge의 `insufficient`가 맡고, 그 결과는 `stance_unevaluated`로 나타납니다.
- `stance_confidence`는 **guard이자 late tiebreak** (게이트는 이미 적용됨, 정렬 키 끝에서 다시).
- 산출: `(ranked, ranking_dropped)` — stance 필터 drop + `duplicate_agent_edge`가 함께 로그로.

> **평가기 부재/전면 실패는 `stance_unevaluated`가 아닙니다.** 평가기가 아예 안 붙었거나(dormant)
> 통째로 예외를 던지면 `_evaluate_stance`(`pipeline.py:158`)가 후보를 **빈 리스트**로 바꾸고
> request-level silence(`stance_judge_disabled` / `_unavailable` / `_failed`)를 반환합니다. 후보가
> Ranker에 도달하지 않으므로 per-candidate drop도 기록되지 않습니다 — 침묵의 층위가 다릅니다
> (요청 전체 vs 후보 하나).

### coverage = round-robin (+ skip-and-backfill)
```python
groups = candidate.edge.anchor_id 별 그룹
core_anchor = via==DIRECT인 첫 hit의 anchor_id  # 원 앵커
group_order = core 먼저, 그다음 anchor_id asc
cursors = 그룹별 커서   # 그룹을 번갈아 돌며 "아직 대표 안 된 agent"를 하나씩
# 각 그룹 내부는 _depth_key로 정렬. 커서가 만난 후보가 이미 대표된 agent면
# duplicate_agent_edge로 drop하고 같은 그룹의 다음 후보로 backfill(그 턴을 낭비하지 않음)
```
한 sub-topic(facet)이 결과를 지배하지 못하게 앵커 그룹을 번갈아 뽑음. (via_qid는 R3 때문에 모든
neighbor hit에서 원 앵커라 facet 구분 불가 → `edge.anchor_id`로 그룹.) 커서를 그룹별로 두는 이유는
위 "대표 edge" 절 — 공용 인덱스 하나로는 skip한 턴이 그 facet의 슬롯 손실이 됩니다.

### experience order
`source → specificity → evidence → freshness → band`. firsthand(직접 경험, 낮은 maturity라도)가
abstract high-maturity를 이김. `None`(경험 근거 없음)은 마지막. → **experience ≠ depth 변형.**

### persona
Alpha no-op (hollow guard, [01 문서](01-data-contracts.md) 참조).

---

**요점:** Gate는 "노출해도 되나"(need-무관)를 정하고, ④a는 for/against일 때 "이 사람은 그 주장에 어느
편인가"를 요청 시점에 판정하며, Ranker는 "어떤 순서로"(need-의존)를 순수 함수로 정합니다. 셋 중 누구도
score를 안 만듭니다 — 입장·순서·drop 사유만. 다음:
[06. serving + decision log](06-serving-and-decision-log.md)가 이걸 응답과 감사 기록으로 만듭니다.
