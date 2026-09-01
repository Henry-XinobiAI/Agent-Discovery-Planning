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

- **recall-only, score 없음.** 관련도는 **리스트 순서로만** 전달되고 `score` 필드는 계약에 없습니다.
  다만 그 불변식이 *어떻게* 지켜지는지는 정확히 써야 합니다 — 응답은 tolerant `_WireStatement`
  (`extra="ignore"`)가 받으므로 서버가 `score`를 흘리면 **wire 경계에서 조용히 버려집니다**(의도된 동작,
  아래 「upstream wire를 파싱하는 두 규율」 ①). `StanceEvidenceHit`의 `extra="forbid"`가 막는 것은 wire
  drift가 아니라 **우리 변환 코드**가 score를 실어보내는 것입니다. 즉 전역 "scalar score 없음"은 응답을
  **거부해서**가 아니라 경계에서 **떨어뜨려서** 유지됩니다.
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
- `DerivedOwnerIdentityResolver` 쪽만 게이트를 붙들고 있습니다 — phantom-agent 검증·정책
  미정이 이 파생 복제에서 나옵니다. (구 B1 producer-side pin 요청은 **2026-08-24 종결**:
  발신하지 않기로 결정 — 파생은 bourbon-api 지정 고정 계약, 명문화는
  `../recommendation_pipeline_design.md` S6-0.)

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
  것이지, upstream drift를 탐지하지는 **못합니다**(구 B1 — 2026-08-24 종결: producer-side pin
  요청은 발신하지 않기로 결정, 파생은 bourbon-api 지정 고정 계약으로 취급.
  `../recommendation_pipeline_design.md` S6-0).
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
- **`/connections`는 그 `Page[T]` unwrap이 아니라 명시적 projection입니다** (코드 `92bb014`). upstream은
  그룹마다 page 봉투를 두고, 그 안의 item을 typed edge로 감싸고, 다섯째 그룹 `typed_out`을 더 실어보냅니다:

  ```
  {center, broader|narrower|links_out|links_in|typed_out:
      NeighborPage{items: [NeighborEdge{relation, entity}], limit, truncated, total}}
  ```

  provider-private `_WireConnections`/`_WireNeighborPage`/`_WireNeighborEdge`가 이 세 겹을 검증하고
  `EntityConnections`(center + 4그룹 `list[EntitySummary]`)로 투영합니다. **두 겹**(page 봉투 + edge wrapper)이
  경계에서 벗겨지므로 paging·relation 메타데이터는 파이프라인에 닿지 않습니다. `typed_out`은 **검증만 하고
  투영하지 않습니다** — required key로 둬서 rename은 잡되, 소비자가 없으므로 도메인에 올리지 않습니다.
  `EntityConnections`에 `limit`/`truncated`가 **없는** 것도 같은 재설계의 결과입니다: 그룹별 봉투에서 request
  단위 cap을 합성하면 응답이 더는 담지 않는 사실을 진술하게 됩니다. 이 wire 모양은 memory-api PR #92에서
  바뀌었고 Discovery는 그중 POST-search 부분만 반영해 3주간 `/connections`가 죽어 있었습니다.
- **article 표면은 제거됐습니다**(코드 `32d8cc6`). 원래 `search_articles`가 `GET /knowledge/articles?q=…`를
  호출했지만 라이브 memory-api에는 `POST /knowledge/articles/search`와 단건 읽기
  `GET /knowledge/articles/{qid}`만 있어 **첫 호출에서 404**였을 것입니다 — connections와 **같은 upstream
  커밋**(PR #92)에서 바뀐 세 번째 부분입니다. 파이프라인 어디서도 호출하지 않았기 때문에(호출자는 그
  메서드 자신의 테스트뿐) 아무것도 깨지지 않았고, 그래서 계약을 교정하는 대신 **표면 전체를 제거**했습니다:
  Protocol·HTTP 구현·`ArticleHit`·eval provider 2개의 메서드와 상태·`PinnedAnchorFixture.articles`와 그
  validator·builder의 `articles={}`·fixture의 빈 키까지. **article retrieval 기능을 폐기한 것이 아니라
  소비자가 없는 transport seam을 걷어낸 것**이고, 나중에 필요해지면 현재 POST 계약과 실제 use case를 기준으로
  새 seam을 설계합니다.
- **read-only retry**: GET(`get`/`expand_connections`)과 entity 검색
  (`POST /knowledge/entities/search`, 읽기 전용이라 재시도 안전) 모두 429/5xx/transport 에러만 재시도,
  4xx/404는 즉시 처리. `get()`만 404→None, `expand_connections`는 404→raise.
- 2xx인데 invalid → `UpstreamUnavailableError`로 래핑.
- **entity 검색은 `lang`을 받지 않습니다** — `POST /entities/search`는 `queries`(+`instance_of`)만 받으므로
  후보 검색에 `lang`을 넘기면 안 됩니다(계약 drift 가드). article 표면이 사라진 뒤로는 **이 seam의 어떤
  메서드도 `lang`을 노출하지 않습니다** — 대조할 표면이 없어졌을 뿐 가드는 그대로 유효합니다.
- 공유 httpx client 하나를 `from_settings()`로 만들고 async-with 생명주기로 관리.

---

## upstream wire를 파싱하는 두 규율

connections 계약 drift 복구(코드 `92bb014`)에서 나온 규율입니다. 적용 범위를 먼저 못박습니다 — 지금은
**명시적 projection adapter 3개**(`entity_http`의 `/connections` · `statement_search_http` ·
`edge_projection_http`)에만 적용됩니다. knowledge의 `Page[T]`와 `Entity`는 아직 domain/wire **겸용**이라 이
규율 밖이고, 남은 direct-parse 표면은 별도 정리 대상입니다. **"모든 provider가 이미 이 규율을 따른다"고 읽지
마세요.**

### 규율 ① — 독립 배포 upstream의 response wire DTO

> 독립적으로 배포되는 upstream의 응답을 명시적으로 domain에 투영하는 adapter에서는 provider-private response
> wire DTO가 additive 필드를 허용한다(`extra="ignore"`). 대신 소비하거나 completeness 검증에 쓰며 **실효 응답
> 계약이 항상 직렬화를 보장하는** 필드는 default 없이 required로 두어 rename/removal을 fail-loud 처리한다.
> **키 부재가 정상 의미인 필드만** optional/default를 허용하고, 그 의미와 **rename 감지 상실**을 그 자리에
> 기록한다.

두 조각이 한 쌍입니다. `forbid`면 upstream의 **additive 변경이 그대로 장애**가 되고, default를 주면 **rename이
"빈 그룹"으로 읽힙니다.** tolerant하게 받되, **존재가 보장된 키는 반드시 요구합니다** — 무엇이 보장되는지는
다음 항목의 판단 기준으로 정합니다.

**required 여부는 서버 모델의 타입이 아니라, 그 route + 우리가 보내는 request scope가 만드는 실효 응답
계약으로 판단합니다.** 타입이 nullable이어도 그 route에서 항상 실린다면 required가 맞습니다.
`ExcludeNoneRoute`(`response_model_exclude_none=True`)를 쓰는 memory-api에서는 **null과 키 부재가 같은
진술**이므로, 어떤 필드를 optional로 푸는 순간 absence가 합법적 의미가 되어 **그 필드의 rename 감지를
잃습니다.** 푸는 필드마다 그 대가를 그 자리(docstring)에 명시하고, 감당할 수 없으면 풀지 않습니다.

**판단은 3단계** — ①만 보면 양방향으로 틀립니다:

1. 서버 응답 모델의 **타입**
2. **그 값을 채우는 소스** — 예: `GroundingLink.source`/`last_seen`은 링크 위에서 non-nullable
3. **그 route가 무엇으로 매칭/필터하는지** — 예: `GET /personal/entities/{qid}`는 `knowledge_qid`로
   매칭하므로 grounding 링크의 존재 자체가 보장됨

2026-08-04에 **양쪽을 다 틀렸습니다.** 한 방향만 기록하면 다음 사람이 반대쪽으로 넘어집니다:

| 방향 | 무엇을 했나 | 결과 |
|---|---|---|
| **너무 엄격** | `competence`를 required로 둠 | 판정된 statement가 아직 없는 owner에서 real run이 죽음 — 서버가 `None`을 **생략**하므로 |
| **너무 느슨** | 그걸 고치며 nullable 4개를 전부 optional로 풂 | `last_seen` rename을 조용히 받아 freshness를 flatten시킬 수 있었음 |

최종형 = **`competence` 하나만 optional.** `knowledge_qid`/`source`/`last_seen`은 required로 되돌렸습니다.
**계약을 느슨하게 만드는 수정은 엄격하게 만드는 수정만큼 위험합니다.**

**statement-search는 반례로 남깁니다.** 서버 타입은 `subject_qid: str | None = None`이지만, adapter가
`if not subject_qid: raise ValueError` 가드 후 **항상** 단일 non-blank QID로 scope하고 서버가 그 QID로 필터·에코
하므로 **required가 맞습니다.** "서버 타입이 nullable이면 optional"이 틀렸음을 보여주는 가장 짧은 예입니다.
반대로 connections `_WireNeighborPage`의 `items`/`limit`/`truncated`/`total`은 애초에 nullable이 아니어서
required가 맞습니다. 어느 쪽이든 **판단 근거를 docstring에 남겨** 다음 사람이 규칙을 잘못 일반화하지 않게
합니다.

**값 제약은 경계에서 강제합니다 — DTO 제약이든, parse 직후의 의미 검증이든.** 필드 이름만 맞추고 아무 검증도
두지 않으면 서버가 보낼 **수 없는** 값을 받아들여 계약을 조용히 넓힙니다. 어느 형태를 쓰는지는 **그 값이
downstream에서 다시 검증되는지**로 갈립니다:

- **projection에서 버려져 downstream 검증을 받지 않는 값**은 DTO 제약으로 못박습니다. connections의
  `relation`(`min_length=1`)과 `limit`/`total`(`ge=0`)이 그래서 추가됐습니다 — 세 값 모두 투영 과정에서
  사라지므로 여기서 안 잡으면 **아무도 안 잡습니다.** 경계 테스트도 함께 뒀습니다.
- **요청값과의 관계로만 의미가 정해지는 값**은 plain 타입으로 받고 parse 직후 검증합니다. statement-search의
  응답 `per_owner_limit`/`limit`은 **우리가 보낸 값과의 동등성**으로, edge projection의 page `limit`/`truncated`는
  요청 cap 일치와 truncation 금지로 검사합니다. 서버 bound를 복제하는 것으로는 이 조건을 **표현할 수 없습니다.**

즉 규율은 "서버의 모든 제약을 DTO에 복제한다"가 아니라 **"경계를 넘은 값이 검증 없이 통과하는 구멍을 남기지
않는다"**입니다.

**비적용** — 여기서는 `extra="forbid"`가 맞습니다(typo·스키마 혼합 방지): 우리가 소유하는 **request DTO** ·
**LLM structured output** · **frozen domain/artifact schema** · **strict API surface**.

### 규율 ② — HTTP 경계 계약 테스트의 payload를 consumer 모델에서 유도하지 않는다

> HTTP adapter 계약 테스트의 response payload를 **consumer domain model에서 유도하지 않는다** —
> `model_dump()`뿐 아니라 **그 필드 모양을 손으로 베끼는 것도 포함**한다. 그렇게 만든 fixture에는 upstream
> drift가 **표현될 수 없다.** 실제 캡처 wire, 또는 consumer model과 **독립적으로 정의한** wire fixture를 쓴다.

connections drift가 3주간 조용했던 이유가 정확히 이것입니다. 오프라인 965개가 전부 초록인 동안 실제 경로는
죽어 있었습니다. 두 가지가 겹쳤습니다:

- **fixture가 wire가 아니라 우리 믿음에서 나왔습니다.** 옛 테스트의 payload는 손으로 쓴
  `{"center": {...}, "limit": 30}` — `model_dump()` 호출은 아니었지만 **당시 `EntityConnections`의 필드
  모양 그대로**였습니다. 출처가 소비자 모델인 fixture는, 손으로 썼든 덤프했든, upstream이 바뀐 사실을 담을
  방법이 없습니다.
- **파싱 대상이 default를 가진 domain 모델이었습니다.** 네 그룹이 모두 `default_factory=list`라 **그룹이
  하나도 없는 payload가 정상 검증**됐고, 테스트는 `center.qid` 하나만 단언했습니다. 즉 "키 부재"와 "빈 그룹"이
  구분되지 않았습니다 — 규율 ①의 *default 없이 required*가 규율 ②의 나머지 절반인 이유입니다.

지금은 라이브 응답을 작은 `limit`으로 캡처해 **바이트째** 커밋하고(정렬·정리 금지, rewriting pre-commit 훅에서
제외), 길이와 SHA-256을 테스트에서 고정합니다. 그리고 새 단언에 이빨이 있는지는 계약을 일시적으로 약화시켜
(`ignore`→`forbid`, required→default) **딱 그 테스트만 깨지는지** 확인해 증명했습니다.

**eval/mock provider는 예외가 아니라 애초에 대상이 아닙니다** — Protocol *아래*의 domain fake이므로 domain
model을 반환하는 것이 **맞습니다.** "fake는 consumer model로 만들지 않는다"로 일반화하면 eval 구조 자체를
부정하게 됩니다. 규율 ②는 **wire를 건너는 지점**에만 적용됩니다.

---

## import 격리 (mock-free 서빙 그래프)

- `eval/`은 `discovery/`를 import 가능.
- `discovery/`와 `api/`는 **절대 `eval/`을 import하지 않음** → 서빙 그래프에 mock이 새지 않음.
- `cli/`는 `eval/`을 **lazy import** (핸들러 안에서) → import-isolation 스캔 밖.
- 이걸 `tests/test_import_isolation.py`가 AST 스캔으로 강제.

**요점:** Protocol이라는 얇은 계약 하나로 "진짜 서비스"와 "평가용 가짜"가 같은 파이프라인을
공유합니다. 다음은 이 provider들을 실제로 소비하는 파이프라인 단계들 —
[03. normalize + linker](03-normalize-and-linker.md)부터.
