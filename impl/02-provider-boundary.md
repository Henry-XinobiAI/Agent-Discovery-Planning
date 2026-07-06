# 02. Provider 경계 (`discovery/providers/base.py`)

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[07. composition](07-composition-api-cli.md) · [09. eval harness](09-eval-harness.md)

이게 시스템에서 가장 중요한 아키텍처 결정입니다. Discovery와 데이터 소스 사이의 **이음매(seam)**를
Python `Protocol` 4개로 코드화했습니다.

---

## 4개의 Protocol

```python
class KnowledgeEntityProvider(Protocol):
    async def search_candidates(self, text, *, limit=20) -> list[EntitySummary]: ...
    async def suggest(self, text, *, limit=8) -> list[EntitySuggestion]: ...
    async def get(self, qid) -> Entity | None: ...
    async def expand_connections(self, qid, *, limit=30) -> EntityConnections: ...
    async def search_articles(self, q, *, qid=None, lang=None, limit=10) -> list[ArticleHit]: ...

class MemoryEdgeProvider(Protocol):
    async def get_edges(self, anchor_id) -> list[AgentTopicEdge]: ...

class PersonaProvider(Protocol):
    async def get_prior(self, agent_id) -> PersonaPrior | None: ...

class EligibilityProvider(Protocol):
    async def check(self, agent_id, *, context=None) -> Eligibility: ...
```

| Protocol | 무엇을 주는가 | Alpha 상태 | degradation 정책 |
|---|---|---|---|
| `KnowledgeEntityProvider` | QID 앵커 substrate (memory-api `/knowledge/entities*`) | **real HTTP** 또는 eval의 pinned 캡처 | 필수 |
| `MemoryEdgeProvider` | 앵커의 agent-topic edge들 | **mock만** (real 소스 미통합) | hard → 없으면 503 |
| `PersonaProvider` | 에이전트 persona prior | mock (Alpha no-op) | optional → `None` OK |
| `EligibilityProvider` | 자격 판정 | mock | hard → 없으면 fail (pass 아님) |

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

이 정책은 gate(③)에서 실제로 구현됩니다 — eligibility는 `asyncio.gather`로 전부 fetch하며 첫
실패를 전파(swallow 금지)하고, persona는 survivor에 대해서만 optional fetch.
([05 문서](05-gate-and-ranking.md) 참조.)

---

## real HTTP provider의 비자명한 점 (`entity_http.py`)

- memory-api list 라우트는 wire에서 `Page[T]` 봉투를 반환 → provider가 `.items`를 unwrap해서
  도메인은 항상 `list[Entity*]`만 봄 (봉투는 transport).
- **GET-only retry**: 429/5xx/transport 에러만 재시도, 4xx/404는 즉시 처리. `get()`만 404→None,
  `expand_connections`는 404→raise.
- 2xx인데 invalid → `UpstreamUnavailableError`로 래핑.
- `lang`은 `search_articles`에만 노출 — entity/suggest 검색은 `q`만 받고 `lang` 없음 (계약 drift
  가드). 후보 검색은 `lang`을 넘기면 안 됨.
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
