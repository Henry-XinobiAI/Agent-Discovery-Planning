# 04. retrieval (②) — QID → 후보 에이전트 pool

← [개요로 돌아가기](README.md) · 관련: [03. linker](03-normalize-and-linker.md) ·
[05. gate + ranking](05-gate-and-ranking.md)

linker가 확정한 앵커 QID로 agent-topic edge를 모읍니다. 핵심은 **sparse할 때만 한 홉 확장**하고
**direct가 이긴다**는 두 규칙입니다.

> **retrieval은 "한 agent를 대표하는 edge"를 고르지 않습니다** (2026-08-04 `24ebc2d`). 그건 need를
> 아는 [Ranker](05-gate-and-ranking.md) 몫입니다. 여기 남은 축소는 두 가지뿐 — direct pool의
> **같은 `(agent_id, anchor_id)` 중복 제거**와, **한 agent 안에서** direct가 그 agent의 neighbor edge를
> 밀어내는 **선점**. 한 agent가 여러 이웃 QID에 걸쳐 있으면 그 facet들은 **전부 Gate로 넘어갑니다**.

---

## 산출물: `EdgeHit` (Candidate가 아님)

```python
class EdgeHit(StrictBaseModel):
    edge: AgentTopicEdge
    via: AnchorVia              # direct | neighbor
    via_qid: str | None = None  # neighbor일 때 원 앵커 QID
```

- **왜 `Candidate`가 아닌가:** `Candidate`는 `Eligibility` 판정을 요구하는데, 그건 Gate(③)가
  바인딩합니다 (R1). `EdgeHit`은 ②→③ 사이의 precursor로, 이 모듈 내부에 머뭅니다.
- **`via_qid` iff `neighbor` 불변식**: `via==neighbor`일 때 정확히 `via_qid` 설정 (validator 강제).
  neighbor hit의 `edge.anchor_id`는 edge가 실제로 사는 **이웃 QID**이고, `via_qid`는 확장을
  트리거한 **원래 앵커 QID** (R3).

---

## 흐름 (`Retriever.retrieve`)

```python
async def retrieve(self, anchor_qid):                                       # retrieval.py:113
    direct = await self._edges.get_edges(anchor_qid)
    direct_hits = _one_hit_per_direct_agent([EdgeHit(edge=e, via=DIRECT) for e in direct])
    if len(direct_hits) >= RETRIEVAL_MIN_DIRECT_EDGES:   # sparse가 아니면 확장 없음
        return direct_hits
    neighbor_hits = await self._expand_neighbors(anchor_qid)
    return direct_hits + _preempted_by_direct(direct_hits, neighbor_hits)
```

### (1) direct fetch → agent별 1개로 축소 (`_one_hit_per_direct_agent`, `retrieval.py:72`)
direct edge는 **모두 같은 확정 앵커 위에** 있으므로, 같은 agent의 두 번째 direct hit은 같은
`(agent_id, anchor_id)`의 중복 — 따로 랭크할 facet이 아닙니다. 그래서 여기서 접는 게 안전합니다.

동시에 이 축소가 `len()`을 **distinct direct agent 수**로 만들어 sparsity 판정의 의미를 정합니다.
한 에이전트의 중복 edge가 확장을 억눌러선 안 됩니다 → 판정 전에 축소.

핵심 finding: sparse 판정을 raw edge가 아니라 **distinct agent pool** 기준으로 해야 함.

### (2) sparse면 one-hop 확장
```python
RETRIEVAL_MIN_DIRECT_EDGES = 3   # 이보다 적으면 확장 (§4②/D3)
```
```python
async def _expand_neighbors(self, anchor_qid):
    connections = await self._knowledge.expand_connections(anchor_qid)
    neighbor_qids = _neighbor_qids(connections, exclude=anchor_qid, limit=RETRIEVAL_MAX_NEIGHBORS)
    edge_lists = await asyncio.gather(*(self._edges.get_edges(qid) for qid in neighbor_qids))
    # 각 edge에 via=NEIGHBOR, via_qid=anchor_qid (원 앵커) 태그
```

- **이웃 QID 수집** (`_neighbor_qids`): `broader/narrower/links_out/links_in`에 **가중치를 주지 않음**
  (relationship-type weighting은 후속 튜닝). 앵커 자신은 제외. `dict.fromkeys`로 dedupe + 결정적 순서,
  `RETRIEVAL_MAX_NEIGHBORS=50`으로 cap (concurrent fan-out 제한).
  > ⚠️ **"가중치 없음"이 "균일하게 다룬다"는 아닙니다** — 그룹을 고정 순서로 이어붙인 뒤 자르므로 cap에
  > 걸리면 **뒤 그룹이 통째로 굶습니다**(실측: `links_in` 0개). 아래 설정 절 참조.
- `asyncio.gather`(never `as_completed`)라 이웃 순서 보존 → 다운스트림 선점·대표 선택이 결정적.

### (3) direct-wins = **선점**(dedupe 아님) — `_preempted_by_direct` (`retrieval.py:88`)
```python
def _preempted_by_direct(direct_hits, neighbor_hits):
    direct_agents = {hit.edge.agent_id for hit in direct_hits}
    return [hit for hit in neighbor_hits if hit.edge.agent_id not in direct_agents]
```
같은 `agent_id`가 direct로도 neighbor로도 왔으면 **direct 우선**(R3). 여기서 밀려나는 건 **그 agent의
neighbor edge뿐**입니다 — direct edge가 없는 agent는 자기 neighbor edge를 **전부** 유지합니다.

> **★ 두 함수를 하나로 합치지 마세요.** 예전 `_dedupe_direct_wins`는 호출 지점 2개(sparsity 계수용
> 축소 / R3 선점)를 겸했는데, 둘은 역할이 다릅니다. 합치면 "agent별 1개"가 pool 전체에 다시 걸려
> **한 agent의 여러 neighbor facet 중 하나만 traversal 순서로 살아남고**, sparsity 판정이 세는 대상도
> 조용히 바뀝니다. 실제로 그 형태가 real run `run-72ecb8940fb5`에서 maturity 0.500 edge를 0.250 edge로
> 가려 `no_candidates`를 만들었습니다 — 대표 선택을 need별 순서로 하는 Ranker로 옮긴 이유
> ([05. ranking](05-gate-and-ranking.md)의 "대표 edge" 절).

---

## 설정 (`config.py: LinkerSettings`)

| 설정 | 기본 | 의미 |
|---|---|---|
| `RETRIEVAL_MIN_DIRECT_EDGES` | 3 | distinct direct agent가 이 미만이면 확장 |
| `RETRIEVAL_MAX_NEIGHBORS` | 50 | 확장 시 이웃 QID cap (fan-out 제한) |

**★ `RETRIEVAL_MAX_NEIGHBORS`(50)는 fan-out 비용 상한이고 recall-neutral하지 않습니다.** 실제 배포에서
**두 층의 cap이 모두 후보를 잘랐습니다** — real run `run-72ecb8940fb5`의 앵커 Q8486에서(진단 목적 `curl`
재호출 실측):

```
upstream(memory-api) limit=30 : broader 6/6 · narrower 30/68 · links_out 30/30 · links_in 30/3836(truncated)
retrieval cap 50              : deduped 96개 이웃 → 50개만 탐색
실제 배분                      : broader 6 · narrower 30 · links_out 14 · links_in 0
```

- `links_in`은 **구조적으로 0**이 됐습니다. `_neighbor_qids`가 그룹을 고정 순서로 이어붙인 뒤 자르므로,
  "모든 관계를 균일하게 취급한다"는 서술과 달리 **관계별 우선순위가 사실상 존재**합니다(가중치는 없지만
  순서가 있음).
- 이 run에서는 결과가 안 바뀌었습니다 — 버려진 46개 중 owner를 가진 `Q1362405`(gelato)의 두 owner가 모두
  maturity 0.05였기 때문. **"이번엔 같았다"이지 "cap이 일반적으로 안전하다"가 아닙니다.**
- 위 수치는 다른 시점의 `curl` 재호출이라 **진단으로는 유효하나 리포트 근거로는 부적격**입니다. 그룹별
  truncation과 cap 전후 분포는 **request-scoped observer 트랙**(기본 no-op collector)에서 관측한 뒤,
  group round-robin / quota / 관계 우선순위 중 하나를 명시적으로 고릅니다. cap을 무작정 키우지 않습니다 —
  concurrent fan-out 비용만 늘어납니다.

---

## 범위 밖 (Phase 8)

- **linker-side ambiguity 확장** (여러 QID 후보를 동시에 탐색)은 별개 관심사로 이월. retrieval의
  확장은 어디까지나 "**확정된** 앵커의 이웃"을 도는 것. (LLM disambiguation 자체는 rerank rung·agentic
  grounder로 이미 shipped — 남은 것은 retrieval이 다중 앵커 QID를 동시에 탐색하는 부분뿐.)

---

**요점:** retrieval은 앵커 QID로 `EdgeHit` pool을 만들되, direct가 sparse할 때만 이웃으로 넓히고
direct를 우선합니다. pool은 **한 agent의 여러 edge를 담을 수 있고**(여러 이웃 facet), 그 중 누가 그
agent를 대표하는지는 여기서 정하지 않습니다. 이 pool이 다음 단계
[05. gate](05-gate-and-ranking.md)에서 `Candidate`로 완성되고 걸러집니다.
