# 07. composition root + API + CLI (Phase 5)

← [개요로 돌아가기](README.md) · 관련: [02. Provider 경계](02-provider-boundary.md) ·
[06. decision log](06-serving-and-decision-log.md)

파이프라인(모듈 5개)을 **실제 provider로 배선**해서 서비스로 만드는 레이어. 핵심 원칙:
**composition root는 real provider만, 에러 매핑은 API layer 전용.**

---

## composition root (`api/depends/pipeline.py`)

배포된 앱이 파이프라인을 조립하는 **단 하나의 장소**. `discovery/`의 concrete provider만
import하고 **절대 `eval/`을 안 함** → 서빙 그래프 mock-free.

```python
def build_pipeline(knowledge: KnowledgeEntityProvider) -> RecommendationPipeline:
    settings = LinkerSettings.get()
    agent_on = GroundingAgentSettings.get().GROUNDING_AGENT_ENABLED   # ①이 agentic이면 symbolic ladder 은퇴
    grounder    = LLMGrounder(knowledge) if agent_on else None
    reranker    = None if agent_on else LLMReranker()                                            # 8A rerank fallback
    expander    = None if agent_on else (LLMExpander()    if settings.EXPANSION_ENABLED    else None)  # 8B rung③ (dormant)
    substituter = None if agent_on else (LLMSubstituter() if settings.SUBSTITUTION_ENABLED else None)  # 8B rung④ (dormant)
    stance_normalizer = LLMStanceNormalizer() if NormalizeSettings.get().STANCE_NORMALIZER_ENABLED else None  # 8-3 (dormant)
    reason_generator  = LLMReasonGenerator()  if ServingSettings.get().REASON_GENERATOR_ENABLED  else None     # 8-5 (dormant)
    return RecommendationPipeline(
        linker=Linker(knowledge, reranker=reranker, expander=expander, substituter=substituter, grounder=grounder),
        retriever=Retriever(UnavailableEdgeProvider(), knowledge),      # edge 미통합 → 503
        gate=Gate(UnavailableEligibilityProvider(), NullPersonaProvider()),  # elig 503, persona None
        ranker=Ranker(),
        stance_normalizer=stance_normalizer,
        reason_generator=reason_generator,
        log=DecisionLog(
            clock=lambda: datetime.now(UTC),
            id_factory=lambda: f"dl_{uuid4().hex}",
            provider_versions=_DEPLOYED_VERSIONS,   # anchor=memory-api@v0, edge=unavailable@v0 …
            contract_version="edge@v0",
            sink=StructlogDecisionLogSink(),        # emit-only, 무한 메모리 없음
        ),
    )
```

### 비자명한 점
- **Alpha는 knowledge substrate만 real** (memory-api). edge/eligibility는 hard-required지만 아직
  미통합 → `Unavailable*` provider로 배선. 배포된 `/recommend`는 앵커를 grounding(real)한 뒤
  candidate 단계에서 **정직한 503**을 반환 (에이전트를 날조하지 않음). persona는 optional →
  `NullPersonaProvider`(항상 `None`, 503 아님).
- **LLM leg는 전부 flag로 배선** — rerank(8A)는 상시, expansion③/substitution④/stance normalizer(8-3)/
  reason generator(8-5)는 각 `*_ENABLED`(기본 OFF)일 때만. `GROUNDING_AGENT_ENABLED`(8-7)는 유일한
  **비-additive** 스위치: ON이면 `LLMGrounder`가 ①의 primary가 되고 rerank/expansion/substitution rung을
  전부 은퇴(`agent_on`이 게이트해 두 상태가 절대 안 겹침). 클라이언트는 아무도 안 들고 proxy를
  `wrapper` 싱글턴으로 공유. eval은 이들을 하나도 주입하지 않음 → 결정적 baseline 불변.
- **파이프라인은 startup에 1회 생성** (lifespan), `app.state`에 저장, `get_pipeline`이 매 요청에
  같은 인스턴스 전달. 공유 httpx client **둘**(knowledge + rerank fallback이 lazily 만드는 LLM proxy
  client)을 소유, shutdown에 `try/finally` close (D4). ownership 테스트로 검증.
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
    GroundingFailedError.code: 422,   # grounding_failed
    InvalidNeedError.code:     422,   # invalid_need
    UpstreamUnavailableError.code: 503,  # upstream_unavailable
}
```
- 각 타입을 명시적으로 등록 (Starlette MRO가 catch-all `Exception`(500 fallback)보다 우선).
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

**요점:** composition root가 real provider를 배선하고(mock은 override로만), API layer가 도메인
예외를 HTTP로 번역하며, 도메인은 transport를 모릅니다. 이 이음매(Protocol) 덕에 Open Beta에서
real edge/eligibility provider로 갈아끼우는 게 배선 변경으로 끝납니다
([11 로드맵](11-phase-8-9-roadmap.md)).
