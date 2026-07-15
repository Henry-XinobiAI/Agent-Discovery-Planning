# 04. retrieval (②) — QID → 후보 에이전트 pool

← [개요로 돌아가기](README.md) · 관련: [03. linker](03-normalize-and-linker.md) ·
[05. gate + ranking](05-gate-and-ranking.md)

linker가 확정한 앵커 QID로 agent-topic edge를 모읍니다. 핵심은 **sparse할 때만 한 홉 확장**하고
**direct가 이긴다**는 두 규칙입니다.

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
async def retrieve(self, anchor_qid):
    direct = await self._edges.get_edges(anchor_qid)
    direct_hits = _dedupe_direct_wins([EdgeHit(edge=e, via=DIRECT) for e in direct])
    hits = list(direct_hits)
    if len(direct_hits) < RETRIEVAL_MIN_DIRECT_EDGES:   # sparse면
        hits.extend(await self._expand_neighbors(anchor_qid))
    return _dedupe_direct_wins(hits)
```

### (1) direct fetch → **dedupe 먼저**
sparsity 판정은 **distinct direct agent 수**(usable pool)를 셉니다. 그래서 한 에이전트의 중복
edge가 확장을 억누르면 안 됩니다 → 판정 전에 dedupe.

핵심 finding: sparse 판정을 raw edge가 아니라 **deduped agent pool** 기준으로 해야 함.

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

- **이웃 QID 수집** (`_neighbor_qids`): `broader/narrower/links_out/links_in` 전부를 균일하게
  다룸 (relationship-type weighting은 후속 튜닝). 앵커 자신은 제외. `dict.fromkeys`로 dedupe +
  결정적 순서, `RETRIEVAL_MAX_NEIGHBORS=50`으로 cap (concurrent fan-out 제한).
- `asyncio.gather`(never `as_completed`)라 이웃 순서 보존 → 다운스트림 dedupe가 결정적.

### (3) direct-wins dedupe
```python
def _dedupe_direct_wins(hits):
    # agent_id당 하나만 유지. direct hit이 앞에 나열되므로 direct가 neighbor를 이김 (R3).
```
같은 `agent_id`가 direct로도 neighbor로도 왔으면 **direct 우선**. (retrieve 마지막에 한 번 더
호출 — direct_hits가 리스트 앞에 있으므로 순서만으로 direct-wins 보장.)

---

## 설정 (`config.py: LinkerSettings`)

| 설정 | 기본 | 의미 |
|---|---|---|
| `RETRIEVAL_MIN_DIRECT_EDGES` | 3 | distinct direct agent가 이 미만이면 확장 |
| `RETRIEVAL_MAX_NEIGHBORS` | 50 | 확장 시 이웃 QID cap (fan-out 제한) |

`RETRIEVAL_MAX_NEIGHBORS`는 Alpha mock 코퍼스보다 넉넉한 headroom이라 실제 Alpha 동작을 안 자름.
memory-api taxonomy cap이 100이라 real provider도 안전.

---

## 범위 밖 (Phase 8)

- **linker-side ambiguity 확장** (여러 QID 후보를 동시에 탐색)은 별개 관심사로 이월. retrieval의
  확장은 어디까지나 "**확정된** 앵커의 이웃"을 도는 것. (LLM disambiguation 자체는 rerank rung·agentic
  grounder로 이미 shipped — 남은 것은 retrieval이 다중 앵커 QID를 동시에 탐색하는 부분뿐.)

---

**요점:** retrieval은 앵커 QID로 `EdgeHit` pool을 만들되, direct가 sparse할 때만 이웃으로 넓히고
direct를 우선합니다. 이 pool이 다음 단계 [05. gate](05-gate-and-ranking.md)에서 `Candidate`로
완성되고 걸러집니다.
