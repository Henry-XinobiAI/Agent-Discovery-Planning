# 07. composition root + API + CLI (Phase 5)

← [개요로 돌아가기](README.md) · 관련: [02. Provider 경계](02-provider-boundary.md) ·
[06. decision log](06-serving-and-decision-log.md)

파이프라인을 서빙 provider로 배선해서 서비스로 만드는 레이어. 핵심 원칙:
**composition root는 serving-graph 구성요소만 배선(eval mock import 없음), 에러 매핑은 API layer 전용,
client 소유는 lifespan.**

---

## 두 층으로 나뉜다 — lifespan(소유) vs assembler(조립)

이 경계가 이 문서에서 가장 중요합니다.

| | `api/main.py` lifespan | `api/depends/pipeline.py` `build_pipeline` |
|---|---|---|
| 역할 | **httpx pool을 가진 client를 만들고·주입하고·닫는다** | **client 비소유 조립기** — 받은 것을 배선만 |
| flag 읽기 | 어떤 client를 **만들지** 정함 | 받은 인자로 가드 적용 |
| client 생성 | ✅ 여기서만 | ❌ 안에서 절대 생성 안 함 |

(순수 함수는 아닙니다 — 설정을 읽고 여러 객체를 만듭니다. 핵심은 **HTTP client를 생성·소유하지 않는다**는
것입니다.)

**왜 이렇게 나눴나:** 조립이 도중에 raise해도 lifespan의 `finally`가 이미 만든 client를 전부 닫습니다.
`build_pipeline`은 **자기가 소유한 적 없는 자원을 샐 수 없습니다**. 반대로 client를 안에서 만들면
"조립 실패 시 방금 만든 pool이 새는" 경로가 생깁니다.

## composition root (`api/depends/pipeline.py`)

`discovery/`의 concrete provider만 import하고 **절대 `eval/`을 안 함** → 서빙 그래프에 eval mock이 안 샙니다.

```python
def build_pipeline(
    knowledge: KnowledgeEntityProvider,
    stance_search: StanceEvidenceSearchProvider | None,   # 있으면 ④a 켜짐 (lifespan이 flag로 결정)
    *,
    edge_provider: MemoryEdgeProvider | None = None,      # Phase 10 real edge (넷 다 lifespan이 공급)
    eligibility_provider: EligibilityProvider | None = None,
    edge_version: str | None = None,
    eligibility_version: str | None = None,
) -> RecommendationPipeline:
    edge, eligibility, edge_ver, elig_ver = _resolve_edge_wiring(...)   # Guard 0/1 (아래)
    settings = LinkerSettings.get()
    agent_on = GroundingAgentSettings.get().GROUNDING_AGENT_ENABLED   # ①이 agentic이면 symbolic ladder 은퇴
    grounder    = LLMGrounder(knowledge) if agent_on else None
    reranker    = None if agent_on else LLMReranker()                                            # 8A rerank fallback
    expander    = None if agent_on else (LLMExpander()    if settings.EXPANSION_ENABLED    else None)  # 8B rung③ (dormant)
    substituter = None if agent_on else (LLMSubstituter() if settings.SUBSTITUTION_ENABLED else None)  # 8B rung④ (dormant)
    reason_generator = LLMReasonGenerator() if ServingSettings.get().REASON_GENERATOR_ENABLED else None  # 8-5 (dormant)
    stance_settings  = StanceSettings.get()   # 한 번 읽어 evaluator와 K에 같은 객체를 흘림
    stance_evaluator = StanceEvaluator(       # ④a — 주입된 search client가 곧 on/off 스위치
        search=stance_search, query_generator=LLMStanceQueryGenerator(),
        judge=LLMStanceJudge(), settings=stance_settings,
    ) if stance_search is not None else None
    return RecommendationPipeline(
        linker=Linker(knowledge, reranker=reranker, expander=expander, substituter=substituter, grounder=grounder),
        retriever=Retriever(edge, knowledge),            # OFF면 UnavailableEdgeProvider → 503
        gate=Gate(eligibility, NullPersonaProvider()),   # OFF면 elig 503, persona는 항상 None
        ranker=Ranker(),
        reason_generator=reason_generator,
        stance_evaluator=stance_evaluator,
        stance_shortlist_limit=stance_settings.STANCE_SHORTLIST_LIMIT,
        log=DecisionLog(
            clock=lambda: datetime.now(UTC),
            id_factory=lambda: f"dl_{uuid4().hex}",
            provider_versions=ProviderVersions(          # edge/elig는 **넘겨받은 문자열 그대로**
                anchor="memory-api@v0", edge=edge_ver, persona="null@v0", eligibility=elig_ver),
            contract_version="edge@v0",
            sink=StructlogDecisionLogSink(),             # emit-only, 무한 메모리 없음
        ),
    )
```

### 세 종류의 스위치

flag가 배선에 닿는 방식이 셋으로 갈립니다. 헷갈리기 쉬운 지점입니다.

| 방식 | 누가 | 예 |
|---|---|---|
| **assembler가 직접 flag를 읽음** | `build_pipeline` | `GROUNDING_AGENT_ENABLED` · `EXPANSION_ENABLED` · `SUBSTITUTION_ENABLED` · `REASON_GENERATOR_ENABLED` |
| **주입된 client의 존재 자체가 스위치** | lifespan이 flag로 결정 | `STANCE_JUDGE_ENABLED` → `stance_search`(있음/`None`) |
| **flag + 주입을 양쪽에서 교차 검증** | lifespan이 공급, assembler가 가드 | `REAL_EDGE_ENABLED` → 4-tuple + Guard 0/1 |

두 번째가 client 소유 원칙의 직접적 결과입니다 — pool을 가진 건 lifespan만 만들 수 있으니, assembler는
"받았는가"로 켜짐 여부를 압니다. 세 번째는 **hard-required substrate**라 한 단계 더 엄격합니다.

### Phase 10 real edge — Guard 0 / Guard 1

`REAL_EDGE_ENABLED`(기본 **OFF**)가 **단일 권위**입니다. 두 가드가 flag와 배선이 어긋나는 걸 막습니다.
둘 다 startup `ValueError` — 요청 시점 503이 아니라 **부팅 실패**입니다.

- **Guard 0 (OFF가 권위)** — flag가 꺼졌는데 provider가 주입되면 거부. 조용히 쓰지도, 조용히 버리지도
  않습니다. "설정이 잘못됐다"를 명시적으로 말하는 쪽.
- **Guard 1 (ON 완전성)** — provider 둘 **과** version 둘이 전부 필수이고, version은 **non-blank**여야
  합니다. edge만 배선하고 부팅에 성공한 뒤 요청 시점에 503 나는 걸 막고, real provider가
  `unavailable@v0`라는 **거짓 provenance**로 기록되는 것도 막습니다. blank version은 `is not None`을
  통과하지만 substrate identity가 비어 있어 provenance가 아니므로 함께 거부합니다.

Guard 1은 **배선 완전성만** 봅니다 — 주입된 provider가 믿을 만한지에 대한 판정이 아닙니다. 그 판단은
turn-on graph를 조립하는 쪽 몫입니다.

**eligibility에는 가드가 없습니다.** real eligibility provider가 생기기 전까지 `AllowAllEligibilityProvider`
(모두 discoverable, stance 단계 포함)가 **승인된 잠정 정책**이지 misconfiguration이 아니기 때문입니다.

**provenance는 넘겨받은 문자열 그대로** 기록합니다 — provider 타입에서 추론하지 않습니다. 그래서 주입된
fake는 정확히 자기가 넘긴 문자열로 로그에 남고, "real처럼 보이는데 mock" 같은 상태가 로그에서 티납니다.

### lifespan (`api/main.py`)

```python
real_edge_enabled = EdgeSettings.get().REAL_EDGE_ENABLED
if real_edge_enabled:
    _reject_real_edge_in_production()      # ← try 밖: 막힌 부팅은 치울 게 없음

knowledge = stance_search = edge_projection = None
try:
    knowledge = HttpKnowledgeEntityProvider.from_settings()
    stance_search = HttpStanceEvidenceSearch.from_settings() if StanceSettings.get().STANCE_JUDGE_ENABLED else None
    if real_edge_enabled:
        edge_projection = HttpOwnerTopicProjectionProvider.from_settings()
    edge, eligibility, edge_version, eligibility_version = _build_edge_wiring(edge_projection)
    app.state.pipeline = build_pipeline(knowledge, stance_search, edge_provider=edge, ...)
    yield
finally:
    await _close_lifespan_clients(knowledge, stance_search, edge_projection)
```

- **client는 셋** (둘 아님): knowledge · stance-search(④a ON일 때만) · edge-projection(real edge ON일 때만).
  넷째로 LLM proxy client가 있지만 그건 **process-wide 싱글턴**이라 rerank/stance 폴백이 lazily 만들고
  `wrapper.close_client()`가 닫습니다(안 만들었으면 no-op).
- **`_close_lifespan_clients`는 중첩 `finally` 3단** — 하나가 raise해도 나머지 close가 전부 시도됩니다.
  둘 이상 raise하면 가장 안쪽 예외가 전파됩니다. 꺼진 단계의 client는 `None`이라 각 close가 가드됩니다.
- **`_build_edge_wiring`은 flag를 안 읽습니다.** `edge_projection`의 존재 자체가 스위치이고, `None`이면
  네 값 전부 `None`을 반환 — 그게 Guard 0을 만족시키는 방식입니다.

### production 거부 가드 (`_reject_real_edge_in_production`)

**이 가드가 없었다면** env var 두 개(`STAGE=prod` + `REAL_EDGE_ENABLED=1`)만으로 프로덕션이 real edge로
부팅될 수 있습니다. 그런데 turn-on 게이트가 아직 열려 있습니다:

- **requester self-exclusion 미구현** — 요청자가 자기 자신의 에이전트를 추천받을 수 있음
- **identity-contract / catalog-existence** — bourbon-api가 파생 규칙을 producer-side로 고정하지 않았고
  (요청 B1), 파생된 agent ID가 실제 agent 카탈로그에 있는지 확인하지 않으며, phantom agent 처리 정책
  (fail loud vs 후보 drop)이 미정
- **memory-api turn-on 요청 R1–R6** — 비활성 owner가 후보로 남는 문제, join 완전성, stale competence 등

**문서 경고는 config 한 줄을 못 막으므로** 현재 코드는 client가 하나라도 만들어지기 **전에**
`ValueError`로 부팅을 차단합니다(그래서 막힌 부팅은 치울 자원이 없습니다). 예외 타입은 Guard 0/1과 같은
`ValueError` — 셋 다 "이 배포는 잘못 설정됐다"는 같은 뜻입니다.

> **제거 조건:** 위에 나열한 것만이 아니라 **스펙 §9의 게이트 전부**가 닫힐 때, **전용 커밋**으로 함수·
> 호출부·테스트를 삭제합니다. 그 커밋이 "프로덕션 turn-on 승인"의 기록입니다. (그래서 예외 메시지는
> 게이트를 열거하지 않고 스펙을 가리킵니다 — 열거하면 그 목록이 또 stale해집니다.)

### 나머지 비자명한 점
- **LLM leg는 전부 flag로 배선** — rerank(8A)는 상시, 나머지는 각 `*_ENABLED`(기본 OFF)일 때만.
  `GROUNDING_AGENT_ENABLED`(8-7)는 유일한 **비-additive** 스위치: ON이면 `LLMGrounder`가 ①의 primary가
  되고 rerank/expansion/substitution rung을 전부 은퇴(`agent_on`이 게이트해 두 상태가 절대 안 겹침).
  이들은 클라이언트를 안 들고 proxy를 `wrapper` 싱글턴으로 공유. eval은 하나도 주입하지 않음 →
  결정적 baseline 불변.
- **파이프라인은 startup에 1회 생성**, `app.state`에 저장, `get_pipeline`이 매 요청에 같은 인스턴스 전달.
- **mock은 여기 안 들어옴** — 테스트는 `app.dependency_overrides[get_pipeline]`로 mock-backed
  파이프라인 주입. 이 모듈은 안 건드림.

---

## API layer

### 라우터 (`api/routers/recommend/router.py`)
얇은 transport shell:
```python
class RecommendRouter:
    def __init__(self, prefix=""):
        self.router = APIRouter(prefix=prefix, dependencies=[Depends(verify_token)])  # bearer, 라우터 전체
        self.router.add_api_route("/recommend", self.recommend, methods=["POST"])

    async def recommend(self, request: RecommendRequest, pipeline=Depends(get_pipeline)):
        return await pipeline.recommend(request)   # 로직은 전부 discovery/에
```
- bearer auth를 라우터 전체에 (HTTPBearer/verify_token, 누락/오류 → 401). `/health`는 열려 있음.
- 이 라우터는 도메인 예외를 **잡지도 매핑하지도 않음**.

### 에러 매핑 (`api/errors.py`)
`discovery/`는 stable `code`를 가진 plain 예외를 던지고 **FastAPI를 절대 import 안 함**
(`discovery/errors.py`). 번역은 **여기서만**:
```python
_STATUS_BY_CODE = {
    GroundingFailedError.code:      422,  # grounding_failed  — 요청을 물어본 대로 서빙할 수 없음
    InvalidNeedError.code:          422,  # invalid_need
    UpstreamUnavailableError.code:  503,  # upstream_unavailable      — hard-required substrate 부재/장애
    EdgeProjectionError.code:       503,  # edge_projection_failed    — 배선된 real-edge projection이 계약 위반 응답
    UnresolvedOwnerIdentityError.code: 503,  # unresolved_owner_identity — resolver가 불일치 매핑 반환
}
```
- 각 타입을 명시적으로 등록 (Starlette MRO가 catch-all `Exception`(500 fallback)보다 우선).
- **세 503의 공통점은 "필수 substrate 상태를 추측하거나 날조하지 않는다"** 입니다. 다만 적용 범위는
  다릅니다:
  - `UpstreamUnavailableError` — **가장 넓음**. knowledge substrate 장애, 미배선 의존성 등 hard-required
    provider가 답을 못 줄 때 전반. real edge와 무관하게 원래 있던 것.
  - `EdgeProjectionError` / `UnresolvedOwnerIdentityError` — **real edge 전용**으로 새로 들어왔고, 여기서만
    "**부분 후보 집합을 돌려주느니 거절한다**"는 논리가 적용됩니다. projection이 truncation·QID/ownership
    불일치·중복 owner를 만나거나, resolver가 owner→agent 매핑을 누락/중복/충돌로 돌려주면 일부만 서빙하지
    않습니다 — 조용히 줄어든 후보 목록은 "이 주제에 전문가가 적다"로 오독되기 때문입니다.
- 표준 봉투 `{request_id, error_code, message}`. `request_id`는 방어적 getattr (미들웨어 부재/
  순서 어긋나도 매핑된 status 유지, 500으로 강등 안 함).

이게 왜 중요한가: 도메인 layer가 **transport-free**로 남습니다. discovery는 HTTP를 모릅니다.

---

## CLI (`cli/`)

- **`cli/recommend.py`** — `--corpus`(entities/edges/agents.json 담긴 dir)로 end-to-end 추천.
  eval mock 4종(`MockKnowledgeEntityProvider.from_fixtures` 등)을 배선. corpus 없으면 exit 2.
  eval을 lazy import.
- **`cli/corpus.py`** — 코퍼스 빌더 (`build` / `build-guards` / `build-anchors`). [09 문서](09-eval-harness.md).
- **`cli/eval.py`** — `run`(Phase 6) + `gate`(Phase 7). [10 문서](10-eval-metrics-and-gates.md).
- `eval/`은 각 핸들러 안에서 **lazy import** → `cli/`가 import-isolation 스캔 밖.

---

## decision log sink (`discovery/decision_log_sink.py`)

배포 vs 테스트의 보관 정책을 가르는 곳:

| sink | 동작 | 쓰는 곳 |
|---|---|---|
| `ListDecisionLogSink` | in-memory list 보관, `records` 읽기 전용 노출 | 테스트 / eval / CLI `--corpus` |
| `StructlogDecisionLogSink` | record당 structured event 1개 emit, **아무것도 안 보관** | 배포 서빙 |

배포 경로가 `List`를 쓰면 long-running 서버에서 무한 증가 → leak. 그래서 배포는 `Structlog`.
`decision_log_id`가 로그 event로 되짚는 join 키.

---

**요점:** lifespan이 pool을 가진 client를 소유하고, composition root가 그것들로 real provider를
배선하며(mock은 override로만), API layer가 도메인 예외를 HTTP로 번역하고, 도메인은 transport를 모릅니다.
이 이음매(Protocol) 덕에, 계약과 owner-space routing이 먼저 정렬된 뒤로는 **lifespan turn-on 배선 자체가
discovery 파이프라인 변경 없이** 끝났습니다(선행 정렬에는 `memory_owner_id`·`_evidence_key` 같은 파이프라인
변경이 포함됐습니다 — [02](02-provider-boundary.md)). 남은 것은 이 레이어의 일이 아니라 **production
promotion 게이트**이고, 그중 상당수는 다른 곳의 새 코드입니다 ([11 로드맵](11-forward-roadmap.md)).
