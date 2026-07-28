# 02. Provider 경계 (`discovery/providers/base.py`)

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[07. composition](07-composition-api-cli.md) · [09. eval harness](09-eval-harness.md)

이게 시스템에서 가장 중요한 아키텍처 결정입니다. Discovery와 데이터 소스 사이의 **이음매(seam)**를
Python `Protocol` 5개로 코드화했습니다.

---

## 5개의 Protocol

```python
class KnowledgeEntityProvider(Protocol):
    async def search_candidates(self, text, *, limit=20) -> list[EntitySummary]: ...  # 단일-쿼리 POST /knowledge/entities/search
    async def search_entities(self, queries, *, instance_of=None, fanout=0, limit=20) -> list[EntitySummary]: ...  # 멀티-쿼리 (+instance_of 필터)
    async def get(self, qid) -> Entity | None: ...
    async def expand_connections(self, qid, *, limit=30) -> EntityConnections: ...
    async def search_articles(self, q, *, qid=None, lang=None, limit=10) -> list[ArticleHit]: ...

class MemoryEdgeProvider(Protocol):
    async def get_edges(self, anchor_id) -> list[AgentTopicEdge]: ...

class PersonaProvider(Protocol):
    async def get_prior(self, agent_id) -> PersonaPrior | None: ...

class EligibilityProvider(Protocol):
    async def check(self, agent_id, *, context=None) -> Eligibility: ...

class StanceEvidenceSearchProvider(Protocol):   # ④a stance step (for/against 전용)
    async def search(self, *, subject_qid, owner_ids, queries, per_owner_limit) -> StanceEvidenceResult: ...
```

| Protocol | 무엇을 주는가 | Alpha 상태 | degradation 정책 |
|---|---|---|---|
| `KnowledgeEntityProvider` | QID 앵커 substrate (memory-api `/knowledge/entities*`) | **real HTTP** 또는 eval의 pinned 캡처 | 필수 |
| `MemoryEdgeProvider` | 앵커의 agent-topic edge들 | **mock만** (real 소스 미통합) | hard → 없으면 503 |
| `PersonaProvider` | 에이전트 persona prior | mock (Alpha no-op) | optional → `None` OK |
| `EligibilityProvider` | 자격 판정 | mock | hard → 없으면 fail (pass 아님) |
| `StanceEvidenceSearchProvider` | owner별 statement 근거 (memory-api statement search) | real HTTP(dormant) / eval fake | **silence** → 실패해도 200, 사유 붙은 침묵 |

### 다섯 번째 Protocol이 다른 점 (`StanceEvidenceSearchProvider`)

앞의 넷과 계약 모양이 다릅니다. 알아둘 게 셋입니다.

- **recall-only, score 없음.** 관련도는 **리스트 순서로만** 전달되고 `score` 필드는 계약에 없습니다
  (`StanceEvidenceHit`이 `extra="forbid"`라 서버가 `score`를 흘려도 조용히 무시가 아니라 **fail-loud**).
  시스템 전역 "scalar score 없음" 규칙이 provider 경계에서도 유지됩니다.
- **`owner_ids`는 owner 공간이지 agent 공간이 아닙니다.** real edge에서 `agent_id`는 owner의 단방향
  파생이라 그걸로 검색하면 memory-api가 본 적 없는 id를 묻는 셈입니다. 그래서 호출자는
  `AgentTopicEdge.memory_owner_id`로 스코프를 잡고 응답도 같은 키로 join합니다
  (`discovery.stance._evidence_key`). mock/eval edge는 owner가 없어 `agent_id`로 폴백 — 거기선 두 공간이
  일치하므로 baseline이 안 바뀝니다. wire 타입은 그냥 `list[str]`이고, **의미만** Protocol이 못박습니다.
- **owner_ids는 반드시 eligibility 통과 shortlist에서 와야 합니다** (global discovery 금지). 게이트를
  우회한 검색이 존재하지 않도록 계약 문서에 박아둔 제약입니다.

`per_owner_limit`에 **기본값이 없는** 것도 의도입니다 — `StanceSettings.STANCE_SEARCH_PER_OWNER_LIMIT`가
유일한 출처라서, 어댑터나 fake가 조용히 다른 값을 쓰지 못합니다.

---

## 왜 Protocol인가 — mock-first / contract-first

real 구현(HTTP)과 mock이 **같은 Protocol**을 구현합니다. 그래서:

> real ↔ mock 교체는 **코드 변경이 아니라 배선(wiring)**입니다.

이게 전략의 뼈대입니다. Memory/Persona/Eligibility 팀의 실제 소스를 **안 기다리고도** 전체
파이프라인을 짓고 평가할 수 있습니다. Alpha에서:
- 실제 구현은 `KnowledgeEntityProvider`뿐 (`providers/entity_http.py`, HTTP).
- 나머지 3개는 mock만 존재 (eval 코퍼스가 공급 — [09 문서](09-eval-harness.md)).

세 종류의 provider 구현이 있습니다:
1. **real** — `providers/entity_http.py`의 `HttpKnowledgeEntityProvider`.
2. **unavailable** — `providers/unavailable.py`. 배포된 서빙 경로에서 edge/eligibility가 아직
   없으니 정직하게 503을 던지는 provider. persona는 `NullPersonaProvider`(항상 `None`, 503 아님).
3. **mock** — `eval/providers/*`. 코퍼스 fixture로 채워지는 오프라인 substrate.

---

## degradation 정책이 왜 다른가

provider마다 "없을 때" 행동이 다릅니다. 이건 **의미론적 결정**입니다:

- **edge / eligibility = hard-required** → 없으면 `UpstreamUnavailableError`(503). eligibility가
  없으면 **fail-closed** — 즉 "판정 없음"을 "통과"로 읽지 않습니다. 노출 안전이 걸린 게이트라
  조용히 통과시키면 안 됨.
- **persona = optional** → `None`이 정당한 답. persona가 없다고 503을 던지면 안 됨 (Alpha에선
  어차피 no-op).
- **stance evidence search = silence** → 세 번째 정책. 실패해도 503이 아니고, 빈 결과를 "입장 없음"으로
  읽지도 않습니다. `StanceEvidenceSearchError`(배선된 검색이 요청 시점에 실패)는 사유가 붙은 **명시
  침묵**(`stance_evidence_search_failed`)으로 200 응답이 됩니다. 다만 **미배선**은 다릅니다 —
  `UpstreamUnavailableError`가 잡히지 않고 전파돼 `stance_judge_unavailable`로 매핑됩니다. "설정 갭"과
  "요청 시점 장애"를 절대 뭉개지 않는 게 이 provider 계약의 핵심입니다.

앞의 두 정책은 gate(③)에서 구현됩니다 — eligibility는 `asyncio.gather`로 전부 fetch하며 첫
실패를 전파(swallow 금지)하고, persona는 survivor에 대해서만 optional fetch.
([05 문서](05-gate-and-ranking.md) 참조.) 세 번째는 ④a stance 단계에서 구현됩니다
([00 §④a](00-pipeline-io-reference.md)).

> **왜 stance만 침묵인가.** edge/eligibility가 없으면 "누가 후보인가"를 아예 모르므로 답 자체가
> 존재할 수 없습니다(503). 반면 stance 근거를 못 찾은 건 **답을 알 수 있는데 근거가 없는** 상태라,
> 추측한 입장을 서빙하는 것보다 "왜 못 골랐는지 말하고 아무도 안 주는" 쪽이 정직합니다. 침묵이
> 열화가 아니라 **하나의 결정**인 이유.

---

## real HTTP provider의 비자명한 점 (`entity_http.py`)

- memory-api list 라우트는 wire에서 `Page[T]` 봉투를 반환 → provider가 `.items`를 unwrap해서
  도메인은 항상 `list[Entity*]`만 봄 (봉투는 transport).
- **read-only retry**: GET(`get`/`expand_connections`/`search_articles`)과 entity 검색
  (`POST /knowledge/entities/search`, 읽기 전용이라 재시도 안전) 모두 429/5xx/transport 에러만 재시도,
  4xx/404는 즉시 처리. `get()`만 404→None, `expand_connections`는 404→raise.
- 2xx인데 invalid → `UpstreamUnavailableError`로 래핑.
- `lang`은 `search_articles`에만 노출 — entity 검색(`POST /entities/search`)은 `queries`(+`instance_of`)만
  받고 `lang` 없음 (계약 drift 가드). 후보 검색은 `lang`을 넘기면 안 됨.
- 공유 httpx client 하나를 `from_settings()`로 만들고 async-with 생명주기로 관리.

---

## import 격리 (mock-free 서빙 그래프)

- `eval/`은 `discovery/`를 import 가능.
- `discovery/`와 `api/`는 **절대 `eval/`을 import하지 않음** → 서빙 그래프에 mock이 새지 않음.
- `cli/`는 `eval/`을 **lazy import** (핸들러 안에서) → import-isolation 스캔 밖.
- 이걸 `tests/test_import_isolation.py`가 AST 스캔으로 강제.

**요점:** Protocol이라는 얇은 계약 하나로 "진짜 서비스"와 "평가용 가짜"가 같은 파이프라인을
공유합니다. 다음은 이 provider들을 실제로 소비하는 파이프라인 단계들 —
[03. normalize + linker](03-normalize-and-linker.md)부터.
