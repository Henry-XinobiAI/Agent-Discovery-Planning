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
| `MemoryEdgeProvider` | 앵커의 agent-topic edge들 | **real 배선됨** (`REAL_EDGE_ENABLED` 기본 OFF → `Unavailable*`) | hard → 없으면 503 |
| `PersonaProvider` | 에이전트 persona prior | serving=`NullPersonaProvider`, eval=mock (Alpha no-op) | optional → `None` OK |
| `EligibilityProvider` | 자격 판정 | 잠정 allow-all (real edge ON일 때) / OFF면 `Unavailable*` | hard → 없으면 fail (pass 아님) |
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
파이프라인을 짓고 평가할 수 있었습니다. 다만 배당금의 범위는 정확히 말해야 합니다 — **계약과 owner-space
routing이 먼저 정렬된 뒤, lifespan turn-on 배선 자체가 discovery 파이프라인 변경 없이 끝났다**는 것입니다.
그 선행 정렬에는 파이프라인 변경이 포함됐습니다: `AgentTopicEdge.memory_owner_id` 신설과
`discovery.stance._evidence_key()` 도입(정의 + 호출 2곳)이 그것입니다 — agent 공간과 owner 공간이 갈리는
순간 evidence 조회 키를 바꿔야 했기 때문입니다.

### `discovery/providers/` 현재 목록

| 파일 | 무엇 | 상태 |
|---|---|---|
| `entity_http.py` | `HttpKnowledgeEntityProvider` — memory-api `/knowledge/entities*` | **상시 real** |
| `statement_search_http.py` | `HttpStanceEvidenceSearch` — statement search (④a) | `STANCE_JUDGE_ENABLED` ON일 때 |
| `edge_projection_http.py` | `HttpOwnerTopicProjectionProvider` — personal-entity competence → `OwnerTopicProjection` | `REAL_EDGE_ENABLED` ON일 때 |
| `identity_edge.py` | `IdentityResolvingEdgeProvider` — projection + resolver → `AgentTopicEdge` | 〃 (데코레이터) |
| `identity_resolver.py` | `DerivedOwnerIdentityResolver` — owner UUID → agent_id (UUID5) | 〃 |
| `eligibility_allow_all.py` | `AllowAllEligibilityProvider` — 승인된 잠정 정책 | 〃 |
| `unavailable.py` | `Unavailable*`(정직한 503) + `NullPersonaProvider`(항상 `None`) | flag OFF = 배포 기본 |
| `tenant.py` / `base.py` | prefix 검증 / Protocol 정의 | — |

위 목록은 **provider 구현 7개 + 지원 모듈 2개**(`tenant.py` prefix 검증 · `base.py` Protocol 정의 —
배선 대상이 아니라 계약·유틸)입니다. 배선되는 7개도 "real"이라는 한 단어로 묶으면 안전 경계가 흐려지므로
네 갈래로 나눠 읽으세요:

| 갈래 | 무엇 | 해당 |
|---|---|---|
| **HTTP substrate adapter** | 실제 upstream을 호출 | `entity_http` · `statement_search_http` · `edge_projection_http` |
| **local adapter / policy** | upstream 호출 없음. 파생 복제 · 잠정 정책 · 데코레이터 | `identity_resolver`(consumer-side 파생 **복제**) · `eligibility_allow_all`(real verdict 아닌 **승인된 잠정 정책**) · `identity_edge`(production adapter) |
| **unavailable / null** | 정직한 503 · 항상 `None` | `unavailable.py` — flag OFF = 배포 기본 |
| **eval mock** | 코퍼스 fixture로 채워지는 오프라인 substrate | `eval/providers/*` ([09 문서](09-eval-harness.md)) |

두 번째 갈래가 특히 중요합니다. `AllowAllEligibilityProvider`는 **eligibility verdict를 실제로 계산하지
않고**, `DerivedOwnerIdentityResolver`는 **upstream에 묻지 않습니다** — 둘 다 프로덕션 그래프에 들어갈 수는
있지만 "real 신호를 가져온다"는 뜻이 아닙니다.

다만 **둘의 처지는 다릅니다**:

- `AllowAllEligibilityProvider`는 stance 단계를 포함해 **승인된 임시 production 정책**입니다. real
  eligibility는 turn-on 블로커에서 **제외**됐고(Open Beta 몫), 그래서 composition root에도 이걸 막는
  가드가 없습니다.
- `DerivedOwnerIdentityResolver` 쪽만 게이트를 붙들고 있습니다 — producer-side pin 부재(B1)와
  phantom-agent 검증·정책 미정 둘 다 이 파생 복제에서 나옵니다.

### real edge는 provider 하나가 아니라 **세 겹**입니다

memory-api가 `AgentTopicEdge`를 주지 않기 때문입니다. 주는 건 owner별 **competence vector**뿐이라,
그걸 edge로 만드는 translation layer가 필요합니다.

```
GET /{prefix}/personal/entities/{qid}     (owner_id 생략 → 전 owner = cross-owner 후보)
  └─ HttpOwnerTopicProjectionProvider     wire → OwnerCompetenceSignal 검증
       └─ translate()  (discovery/edge_translate.py, 순수·clock 주입)
            → OwnerTopicProjection        = AgentTopicEdge − agent_id + owner_id
  └─ IdentityResolvingEdgeProvider        owner_id → agent_id 해소 (유일한 지점)
       └─ DerivedOwnerIdentityResolver    uuid5(AGENT_NAMESPACE, f"personal_agent:{owner_id}")
            → list[AgentTopicEdge]        = MemoryEdgeProvider Protocol 충족
```

- **`translate`는 순수 함수**(`edge_translate.py`)라 HTTP 없이 단위 테스트됩니다. maturity는
  `depth × (0.6 + 0.4 × consistency)` — **곱셈**이라 consistency가 depth를 넘어설 수 없습니다(선형 blend면
  `depth=0.10 / consistency=1.0`이 0.45 게이트를 통과해버림. consistency는 모순 **패널티**이지 얕은
  depth의 구제책이 아님). evidence_strength는 `n/(n+4)` 포화, freshness는 90일 반감기 decay.
- **identity 해소가 데코레이터로 분리된 이유** — projection provider는 identity를 아예 모릅니다.
  파생 규칙이 bourbon-api 소유라 언젠가 실제 조회로 갈아끼워야 하고, resolver를 주입받게 해두면 그게
  배선 변경으로 끝납니다. 지금 resolver는 bourbon-api의 UUID5 파생을 **복제**하고 알려진 vector로 고정한
  것이지, upstream drift를 탐지하지는 **못합니다**(turn-on 요청 B1).
- **exact-mapping 강제** — 누락·초과·충돌·invalid가 전부 loud-fail(`UnresolvedOwnerIdentityError`).
  resolver 장애를 "등록 안 된 owner"로 오해하지 않기 위해서입니다.
- **one-owner/QID 불변식은 두 겹 모두에서 재확인** — Protocol이 임의의 projection source를 허용하므로
  데코레이터가 HTTP provider의 중복 검사에 기댈 수 없습니다(defense in depth).
- **실패는 위반 종류에 따라 다른 예외로 갈립니다.** 공통 원칙은 "**필수 substrate 상태를 추측하지 않는다**"
  이고, "**부분 후보 집합을 돌려주느니 거절한다**"는 논리는 **앞의 둘에만** 적용됩니다:

  | 실패 | 예외 |
  |---|---|
  | projection adapter의 **transport·non-2xx·payload drift·translation 계약 위반** (truncation·QID/source/ownership 불일치·중복 projection owner·`support_ids` 빈 competence) | `EdgeProjectionError` |
  | owner→agent **exact-mapping** 위반 (누락·초과·충돌·invalid) | `UnresolvedOwnerIdentityError` |
  | flag OFF 상태의 `Unavailable*`, knowledge substrate 장애 | `UpstreamUnavailableError` |

  **real edge가 켜져 있을 때의 HTTP 실패는 `UpstreamUnavailableError`가 아니라 `EdgeProjectionError`**
  입니다 — projection adapter가 transport 실패까지 자기 예외로 감싸므로, "edge 경로가 깨졌다"와 "다른
  substrate가 죽었다"가 로그에서 섞이지 않습니다. 앞의 둘은 real edge와 함께 신설됐고, 셋째는 원래 있던
  넓은 범주입니다([07 에러 매핑](07-composition-api-cli.md)).

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
