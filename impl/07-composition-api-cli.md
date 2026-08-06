# 07. composition root + API + CLI (Phase 5)

← [개요로 돌아가기](README.md) · 관련: [02. Provider 경계](02-provider-boundary.md) ·
[06. decision log](06-serving-and-decision-log.md)

파이프라인을 서빙 provider로 배선해서 서비스로 만드는 레이어. 핵심 원칙:
**composition root는 serving-graph 구성요소만 배선(eval mock import 없음), 에러 매핑은 API layer 전용,
client 소유는 lifespan.**

---

## 두 층으로 나뉜다 — lifespan(소유) vs assembler(조립)

이 경계가 이 문서에서 가장 중요합니다.

| | `api/main.py` lifespan | `api/depends/pipeline.py` `build_edge_wiring` · `build_pipeline` |
|---|---|---|
| 역할 | **httpx pool을 가진 client를 만들고·주입하고·닫는다** | **client 비소유 조립기** — 받은 것을 배선만 |
| flag 읽기 | 어떤 client를 **만들지** 정함 | 받은 인자로 가드 적용 |
| client 생성 | ✅ 여기서만 | ❌ 안에서 절대 생성 안 함 |

(순수 함수는 아닙니다 — 설정을 읽고 여러 객체를 만듭니다. 핵심은 **HTTP client를 생성·소유하지 않는다**는
것입니다.)

**왜 이렇게 나눴나:** 조립이 도중에 raise해도 lifespan의 `finally`가 이미 만든 client를 전부 닫습니다.
`build_pipeline`은 **자기가 소유한 적 없는 자원을 샐 수 없습니다**. 반대로 client를 안에서 만들면
"조립 실패 시 방금 만든 pool이 새는" 경로가 생깁니다.

**부수 효과 — 조립기가 재사용 가능해졌습니다.** client를 안 들기 때문에 lifespan 밖에서도 부를 수 있고,
실제로 **두 번째 호출자**가 생겼습니다: e2e 진단 CLI(아래 "CLI" 절). 진단 도구는 앱과 **같은 그래프**를
돌려야 의미가 있으므로(같은 가드·같은 provenance·같은 LLM leg) 두 번째 composition root를 파지 않고
이 함수들을 그대로 씁니다.

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
    sink: DecisionLogSink | None = None,                  # 미지정 = StructlogDecisionLogSink (배포 기본)
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
            sink=sink if sink is not None else StructlogDecisionLogSink(),   # 배포 기본 = emit-only
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

### 켜짐은 세 단계다 — "dormant"는 더 이상 충분한 서술이 아니다

기본 OFF 플래그를 "dormant"로만 부르면 **모순이 생깁니다**: 여러 게이트가 *"측정한 뒤에 켠다"*인데,
측정하려면 먼저 켜야 하기 때문입니다. 그래서 켜짐을 세 단계로 나눕니다(코드 `4ecec3e`가 `discovery/
config.py` 모듈 docstring에 같은 어휘를 심었습니다):

| 단계 | 뜻 | 어디서 |
|---|---|---|
| **measurement activation** | 증거를 만들려고 비프로덕션에서 켠다 | dev overlay |
| **serving activation** | 그 증거로 게이트를 닫고 사용자 트래픽에 쓴다 | 게이트별 |
| **base promotion** | overlay를 떠나 `k8s/base`를 상속하는 **모든 overlay의 공통 설정**이 된다 (코드 기본값은 계속 OFF) | `k8s/base`, 기능당 전용 커밋 |

**게이트 문구의 *"<gate> 전엔 안 켠다"*는 언제나 serving + promotion을 뜻하지 measurement를 막지 않습니다.**
플래그는 `k8s/base`에 넣지 않습니다 — 기능별로 dev overlay에서 측정 → 게이트 종료 → 개별 promotion
커밋으로 이동합니다. (`REAL_EDGE_ENABLED`를 base나 prod overlay에 넣으면 `_reject_real_edge_in_production`
이 `ValueError`를 던져 **CrashLoopBackOff**입니다.)

**현재 overlay 상태**(코드 `c1ba21e`): dev = `STAGE=dev` · `MEMORY_API_PREFIX=demo` ·
`REAL_EDGE_ENABLED=true`, prod = `STAGE=prod` · `MEMORY_API_PREFIX=bourbon` · 플래그 없음.
`k8s/base`의 env 블록은 여전히 비어 있습니다. ⚠️ **머지는 배포가 아닙니다** — CI에 deploy job이 없어
`k8s/scripts/deploy.sh dev`는 수동이고, 아래 문서들이 "dev에서 켜져 있다"고 할 때는 **매니페스트 상태**를
뜻합니다.

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
    edge, eligibility, edge_version, eligibility_version = build_edge_wiring(edge_projection)
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
- **`build_edge_wiring`은 flag를 안 읽습니다.** `edge_projection`의 존재 자체가 스위치이고, `None`이면
  네 값 전부 `None`을 반환 — 그게 Guard 0을 만족시키는 방식입니다. (flag를 읽는 건 `build_pipeline` 안의
  `_resolve_edge_wiring`이고, 이쪽이 Guard 0/1을 겁니다. 이름이 비슷하니 주의 — 하나는 **재료를 만들고**,
  하나는 **flag와 대조해 검증**합니다.)

### production 거부 가드 (`_reject_real_edge_in_production`)

**이 가드가 없었다면** env var 두 개(`STAGE=prod` + `REAL_EDGE_ENABLED=1`)만으로 프로덕션이 real edge로
부팅될 수 있습니다. 그런데 turn-on 게이트가 아직 열려 있습니다.

**가드는 `STAGE=prod`만 막습니다.** 그래서 게이트는 "전부 닫혀야 무엇이든 켠다"가 아니라 "전부 닫혀야
**prod**를 켠다"이고, 아래 둘은 성격이 다릅니다(2026-08-06 재분류, 코드 `4ecec3e`):

**① 비프로덕션에서 증거를 만드는 것** — dev 활성화의 blocker가 아니라 제거 판단의 입력입니다.

- **requester self-exclusion** — **구현·시행됩니다**(코드 PR #34). pre-gate 단계가 요청자 본인 agent를
  제거하고, `requester_owner_id` 누락은 **422 `requester_identity_required`로 거부**합니다. 남은 건
  호출자 적용과 비프로덕션 acceptance인데, **실배포 호출자가 아직 0개**라 마이그레이션할 대상이 없습니다.
- **catalog existence** — 파생된 agent ID가 실제 카탈로그 row와 맞는지 확인하지 않습니다. **우리 진단으로는
  닫을 수 없습니다**: bourbon-api에 lookup 엔드포인트가 없어 CLI preflight가 `unverified`로 **명시 보고**
  합니다. 답은 소비 컴포넌트가 반환된 ID를 end-to-end로 해석할 때 나옵니다.

**② 프로덕션 서빙 전에 해소돼야 하는 것** — 전부 정책 결정인 것은 아닙니다.

- **phantom agent 처리 정책** — fail loud vs 후보 drop, 미정.
- **memory-api R1–R6** — 비활성 owner가 후보로 남는 문제, join 완전성, stale competence. R1은 "비프로덕션
  tenant는 seed 데이터뿐"이라는 전제로 연기됐고, **그 전제는 프로덕션으로 확장되지 않습니다.**
- **producer-side derivation pin (B1)** — 값 일치는 bourbon-api 소스 복사로 확인됐고 규칙도 불변으로
  확정돼, correctness unknown이 아니라 **drift 보험**입니다. 보상 탐지기가 없어서 목록에 남습니다.

**문서 경고는 config 한 줄을 못 막으므로** 현재 코드는 client가 하나라도 만들어지기 **전에**
`ValueError`로 부팅을 차단합니다(그래서 막힌 부팅은 치울 자원이 없습니다). 예외 타입은 Guard 0/1과 같은
`ValueError` — 셋 다 "이 배포는 잘못 설정됐다"는 같은 뜻입니다.

> **제거 조건:** 위에 나열한 것만이 아니라 **스펙 §9의 게이트 전부**가 닫힐 때, **전용 커밋**으로 함수·
> 호출부·테스트를 삭제하고 **`REAL_EDGE_ENABLED`를 dev overlay에서 `k8s/base`로 옮깁니다**. 그 커밋이
> "프로덕션 turn-on 승인"의 기록입니다. (그래서 예외 메시지는 게이트를 열거하지 않고 스펙을 가리킵니다 —
> 열거하면 그 목록이 또 stale해집니다. **이 절이 실제로 그렇게 stale해졌습니다**: self-exclusion이 구현된
> 뒤에도 "미구현"으로 남아 있었고, 그건 코드 docstring에서 먼저 발견돼 고쳐졌습니다.)

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
    RequesterIdentityRequiredError.code: 422,  # requester_identity_required — enforcing self-exclusion인데 필드 없음
    UpstreamUnavailableError.code:  503,  # upstream_unavailable      — hard-required substrate 부재/장애
    EdgeProjectionError.code:       503,  # edge_projection_failed    — 배선된 real-edge projection이 계약 위반 응답
    UnresolvedOwnerIdentityError.code: 503,  # unresolved_owner_identity — resolver가 불일치 매핑 반환
}
```
- 각 타입을 명시적으로 등록 (Starlette MRO가 catch-all `Exception`(500 fallback)보다 우선).
- **`requester_identity_required`(422)만 배포 조건부**입니다 — pre-gate exclusion이 enforcing일 때(=real
  edge ON)만 납니다. 스키마에서 `requester_owner_id`는 여전히 optional인데, "어떤 배포에서만 필수"는
  스키마로 표현할 수 없기 때문입니다(그래서 `/docs`에는 optional로 보이고, 필드 description이 그 대가를
  말합니다). 계약 전문 = spec `2026-08-05-requester-self-exclusion-design.md`.
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
- **`cli/e2e/`** — `e2e-recommend`(아래 절). **배포된 서빙 그래프를 real memory-api 상대로** 도는 유일한 CLI.
  (`cli/corpus.py build-anchors`도 real memory-api를 치지만 그건 코퍼스 **빌드**용 검색이지 파이프라인 실행이
  아닙니다. `cli/recommend.py`는 `--corpus` mock 전용.)
- `eval/`은 각 핸들러 안에서 **lazy import** → `cli/`가 import-isolation 스캔 밖.

### `e2e-recommend` — real 코퍼스 상대 진단 도구 (2026-07-29 머지, PR #28)

**왜 있나:** `/recommend`가 빈 결과를 돌려줬을 때 트레이스만으로는 **"코퍼스가 비어서"와 "버그라서"를
가를 수 없습니다.** 이 도구는 run에 쓸 client를 그대로 써서 memory-api에 **먼저 직접 물어보고**(preflight),
그다음 파이프라인을 돌린 뒤, 둘을 한 리포트에 나란히 적습니다.

`create`(합성 대화 fixture 생성) / `run`(fixture로 파이프라인 실행) 두 하위 명령입니다. **도구가 지어내는
것은 requester↔requester-agent 대화 하나뿐**이고 후보 신호(competence·statement)는 전부 이미 있는 데이터며,
**memory-api에 아무것도 쓰지 않습니다.**

배선은 `_run`이 위 조립기를 그대로 부릅니다 — projection을 `RecordingProjection`으로 감싸 →
`build_edge_wiring` → 돌아온 edge provider를 `RecordingEdgeProvider`로 **두 번째로** 감쌉니다.
순서가 load-bearing입니다: 앞은 **owner 공간**의 competence, 뒤는 **identity resolution이 만들어낸
agent 공간**의 edge — edge만 감싸면 그 사이 정보가 사라집니다([02](02-provider-boundary.md) 세 겹 구조).
`sink`로는 `ListDecisionLogSink`를 주입해 record를 되읽어 트레이스로 렌더합니다.

**종료 코드 계약 — 축은 시간이 아니라 "운영자가 고칠 수 있는 전제 오류 vs 실행 중 실패"입니다**(문자열
파싱 금지 — transport 실패와 계약 위반이 설계상 같은 도메인 예외 타입이라 메시지로 가르는 건 추측입니다):

| | 뜻 |
|---|---|
| `0` | 결론이 선 진단 결과 — 추천·**빈 결과**·명시 silence·`GroundingFailedError`. 빈 결과도 발견이다 |
| `1` | **실행이 실패함** — provider I/O·상류 계약 위반·생성기 degrade·**cleanup 실패**·**도구 내부 예상 밖 예외** |
| `2` | **운영자가 입력을 고쳐 다시 돌리면 되는 것** — CLI 사용법·범위 밖 `--limit`·공백 인자·**stance 캡 초과 proposition**(직접 입력 또는 replay fixture)·**topic-only 시나리오에 준 `--proposition`**·`STAGE=prod`·fixture 부재/해시 불일치·대화형 proposition 선택 오답 |

반대편을 "상류"로 부르지 않는 이유: **exit 1이 전부 상류 탓은 아닙니다.** cleanup 실패와 도구 내부의
예상 밖 예외도 여기 들어가고, 그건 어떤 upstream도 고칠 수 없습니다.

**exit 2를 "아직 아무것도 안 썼다"로 읽으면 안 됩니다.** `run` 경로에서는 마침 그렇습니다 — preflight
phase A는 **sync 함수**이고 provider를 하나도 안 받는데, provider 호출은 전부 coroutine이므로 phase A가
그중 **어느 것도 부른 적이 없음**이 타입으로 드러납니다(→ exit 2가 provider client 생성 전·network I/O
이전에 확정). 하지만 **`create`에는 그 보장이 없습니다**: proposition 후보 3개를 LLM으로 받은 **뒤에야**
운영자에게 고르라고 묻기 때문에, 잘못된 번호를 입력하면 **network 호출 이후에 나는 exit 2**입니다
(`cli/e2e/run.py::_choose_proposition`, 회귀 테스트
`test_create_exits_2_on_an_invalid_selection_after_the_llm_call`). 안정적인 계약은 **"운영자가 고칠 수 있는
전제 오류 vs 실행 중 실패"**이지 타이밍이 아닙니다.

**입력 생성기도 자기가 먹이는 계약 안에 있어야 합니다** (코드 main `f3a245c`). proposition은
`stance_query_generate.MAX_PROPOSITION_CHARS`(200, 공개 상수)를 넘으면 검색 **전에** None으로 거부되는데,
**이 변경 전에는** 캡을 넘긴 proposition이 모든 로컬 검사를 통과해 저장된 뒤 `stance_query_generation_failed`
침묵으로 끝났습니다 — **진단 대상의 실패가 아니라 진단 입력의 실패**였습니다. 지금은 proposition이
들어오는 **세 지점 각각에서, 실패 소유자에 맞는 코드로** 거부됩니다:

| 출처 | 검사 위치 | 종료 코드 |
|---|---|---|
| 생성 후보 | `generate._valid_propositions` → `None` | **1** (생성기 degrade) |
| `--proposition` | `run._check_options` | **2** (운영자 몫) |
| replay fixture | `preflight._proposition_item` | **2** |

**캡은 `ConversationFixture` 모델에는 두지 않습니다.** 캡은 *이 빌드의* stance generator 소유이고 fixture는
다른 머신에서 replay되는 durable artifact라, 캡이 내려가도 이미 쓴 fixture가 로드 불가가 되면 안 됩니다
(judge 플래그를 fixture 계약에 넣지 않은 것과 같은 이유 — 그래서 replay 경로의 검사도 모델이 아니라
preflight에 있습니다). 값은 `Options` 생성 시점부터 canonical이고(`normalize`가 어차피 strip하므로 캡은
generator가 보는 값에 걸립니다), 손으로 고친 fixture의 공백은 — 이건 artifact 정규성이라 **모델이** —
조용히 고치지 않고 **거부**합니다.

**fixture는 `conversation-fixture@v2`이고, version literal은 정확히 하나의 wire shape를 지칭합니다.**
default 있는 additive 필드도 bump 사유입니다 — 한 버전이 두 shape를 가리키는 것이 literal이 막으려던
바로 그것이기 때문입니다. v1 loader는 없습니다 — bump 시점이 **real run 이전**이고 커밋된 fixture도
없어서, 보존해야 할 재사용 fixture가 없었습니다(호환 분기를 두면 도달 경로가 없는 코드가 영구히 남습니다).
추가된 `proposition_generation`은 **경로 기반** provenance입니다: 생성기가 내놓을 문자열을 운영자가
그대로 타이핑해도 `None`이며, `proposition`과의 조합이 세 상태(topic-only / operator-supplied / generated)를
닫습니다.

**conversation 프롬프트의 의미 조항은 불변식이 아니라 지시입니다** — post-parse 검증이 보는 것은
shape(턴 수·교대·blank)뿐이라, 조항을 무시한 대화도 그대로 저장됩니다. (proposition 쪽은 다릅니다:
개수·non-blank·상이성·200자 캡이 전부 검증됩니다.) 그래서 문서·help는 그 의미 조항에 대해
"보장한다"가 아니라 **"지시한다"** 로 쓰고, 동명이의어는 **입력에 이미 있는 판별 단서 반영까지만**
요구합니다(운영자가 의도한 sense를 전달하는 입력이 없으므로). 판별 정보 조작은 요구한 범주
전체(domain·use·place·period·person·identifier·biographical fact)를 금지합니다 — 요구와 금지의 범위가
어긋나면 요구한 것만 조작 가능해집니다.

**단일 불변식 = 저장된 리포트가 프로세스 종료 방식과 절대 어긋나지 않는다.** 실패해도 부분 리포트가
남고, cleanup 중 `BaseException`(Ctrl-C 포함)도 기록한 뒤 남은 cleanup을 마치고 재전파합니다. 외부 리뷰
5라운드가 전부 이 한 불변식의 서로 다른 누수 경로였습니다.

**이 도구가 관측 못 하는 것을 리포트가 스스로 밝힙니다** — 탈락 후보의 원 verdict(drop이
`{agent_id, anchor_id, reason}`만 남김: `wrong_stance`는 verdict가 있었다가 이 이음매에서 사라진 것,
`stance_unevaluated`는 애초에 없던 것, `duplicate_agent_edge`는 **같은 agent의 다른 edge가 대표로 뽑혀
이 edge는 judge되지 않은 것**[stance run에서만 §11에 표시] → 세 경우를 다르게 출력. drop 집계 라벨이
`edge drops:`인 이유도 이것 — 단위가 agent가 아니라 edge입니다), raw competence 신호(어댑터 내부
translation에만 존재), preflight QID는 symbolic 규칙 기반
**heuristic**(agentic grounder는 그 규칙을 안 씀 → `probe_qid`라 부르고 불일치 시 명시), agent catalog 존재는
`unverified`(bourbon-api에 조회 수단 없음 = turn-on 게이트 3).

**안전 봉투:** `STAGE=prod` 거부 — **앱 startup 가드와 같은 규칙이 아닙니다.** 이 도구는 real 코퍼스를
읽으므로 **플래그와 무관하게** prod stage를 거부하고, 앱 가드는 **prod + real-edge 조합만** 거부합니다
(`preflight.py:124`가 그 차이를 detail 문구에 직접 씁니다) · artifacts는 로컬 전용(gitignore) · 실제 statement
본문은 120자 절단이 기본.

**self-exclusion 보고는 3상태입니다** — 구현·시행되므로(코드 PR #34) 리포트는 상태를 **하드코딩하지 않고
decision log에서 읽습니다**(`report.py:218`). "drop row가 없다"만으로는 *돌았지만 일치가 없었다*와
*애초에 배선되지 않았다*를 구분할 수 없고, 전자를 "검증됨"으로 렌더링하는 것이 이 리포트가 절대 유도하면
안 되는 독해이기 때문입니다.

| run 상태 | 리포트가 말하는 것 |
|---|---|
| `--requester-owner-id` 없음 | self-exclusion이 이 요청에서 **돌 수 없었다**. **real-edge CLI run의 정상 도달 상태가 아닙니다** — `_check_options`(`run.py:590`)가 실행 **전에** usage 단계에서 거부해 **exit 2**이고 리포트 자체가 없습니다. 이 분기는 비강제 구성·실패 리포트·테스트 shape을 정직하게 렌더링하기 위한 것입니다 |
| 줬으나 파생 미완료 | owner id는 받았지만 preflight identity resolution 전/중에 끝나 **이 run이 실증하지 못했다** |
| 파생 완료 | 파생 agent id를 싣고, 정책별로 `applied` / `registered but inactive` + 제거한 edge 수 |

owner id와 파생 agent id는 **다른 사실**이라 2상태로 접으면 운영자 자신의 입력을 거짓으로 서술하게 됩니다 —
실패를 설명하는 것이 임무인 리포트에서.

> **누락 처리는 두 진입점에서 다릅니다 — 섞지 마세요.** CLI real-edge run은 **exit 2**(운영자가 고칠
> 로컬 전제, I/O 전에 판정), 배포된 `POST /recommend`는 enforcing 정책이 **422
> `requester_identity_required`**. 우회 플래그는 **일부러 없습니다** — safety 정책을 끄는 스위치는 영구
> 운영 API가 되고, acceptance run이 실제 후보 경로와 갈라지며, 깨끗한 진단처럼 읽히는 리포트를 남깁니다.
> CLI 체크는 친절한 조기 오류이고 **실제 불변식은 정책 자신의 체크**입니다 — 둘 다 남습니다.

**재현성**은 seed가 아니라 **fixture 재사용**입니다(proxy가 seed-결정적이지 않음). fixture는 대화 본문의
`content_hash`를 들고 다니고 `run`이 재계산해 불일치를 거부합니다 — 턴을 고치고 해시를 그대로 두면 조용히
로드돼 그 이후의 모든 비교가 무효가 되기 때문입니다. 생성기는 턴 수·화자 순서·공백·중복 위반 시 **패딩하거나
재시도하지 않고 `None`으로 degrade**합니다(자기 입력을 고치는 진단 도구는 없느니만 못함).

사용법·환경변수·acceptance 체크리스트의 단일 소스는 코드 repo `cli/e2e/README.md`입니다.

---

## decision log sink (`discovery/decision_log_sink.py`)

배포 vs 테스트의 보관 정책을 가르는 곳:

| sink | 동작 | 쓰는 곳 |
|---|---|---|
| `ListDecisionLogSink` | in-memory list 보관, `records` 읽기 전용 노출 | 테스트 / eval / CLI `--corpus` / `e2e-recommend` |
| `StructlogDecisionLogSink` | record당 structured event 1개 emit, **아무것도 안 보관** | 배포 서빙 |

배포 경로가 `List`를 쓰면 long-running 서버에서 무한 증가 → leak. 그래서 배포는 `Structlog`.
`decision_log_id`가 로그 event로 되짚는 join 키.

`build_pipeline`의 `sink` 인자가 이 선택을 **호출자에게** 넘깁니다(미지정 = `Structlog` = 기존 배포 동작
그대로). `e2e-recommend`가 `List`를 주입하는 이유는 record를 **되읽어야** 하기 때문입니다 — emit-only sink
위에서는 트레이스를 렌더할 수 없고, 그렇다고 로그를 파싱하는 건 계약이 아닙니다.

---

**요점:** lifespan이 pool을 가진 client를 소유하고, composition root가 그것들로 real provider를
배선하며(mock은 override로만), API layer가 도메인 예외를 HTTP로 번역하고, 도메인은 transport를 모릅니다.
이 이음매(Protocol) 덕에, 계약과 owner-space routing이 먼저 정렬된 뒤로는 **lifespan turn-on 배선 자체가
discovery 파이프라인 변경 없이** 끝났습니다(선행 정렬에는 `memory_owner_id`·`_evidence_key` 같은 파이프라인
변경이 포함됐습니다 — [02](02-provider-boundary.md)). 남은 것은 이 레이어의 일이 아니라 **production
promotion 게이트**이고, 그중 상당수는 다른 곳의 새 코드입니다 ([11 로드맵](11-forward-roadmap.md)).
