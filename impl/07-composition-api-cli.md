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

**종료 코드 계약**(문자열 파싱 금지 — transport 실패와 계약 위반이 설계상 같은 도메인 예외 타입이라
메시지로 가르는 건 추측입니다):

| | 뜻 |
|---|---|
| `0` | 결론이 선 진단 결과 — 추천·**빈 결과**·명시 silence·`GroundingFailedError`. 빈 결과도 발견이다 |
| `1` | provider I/O·상류 계약 위반·생성기 degrade·cleanup 실패·예상 밖 예외 |
| `2` | **로컬 전제만** — CLI 사용법·범위 밖 `--limit`·공백 인자·`STAGE=prod`·fixture 부재/해시 불일치 |

이 구분은 문서가 아니라 **구조로** 강제됩니다: preflight phase A는 **sync 함수**이고 provider를 하나도 안
받습니다 — provider 호출은 전부 coroutine이므로 phase A가 그중 **어느 것도 부른 적이 없음**이 타입으로
드러납니다. 즉 **exit 2는 provider client가 만들어지기 전, network I/O 이전에 확정**됩니다. ("I/O를 전혀 안
한다"는 아닙니다 — fixture 부재·해시 불일치는 `load_fixture`의 **로컬 파일** I/O 결과이고, 그것도 exit 2입니다.
경계는 sync/async가 아니라 **로컬 전제 vs 상류 응답**입니다.) phase B가 보고하는 건 전부 I/O 결과입니다.

**단일 불변식 = 저장된 리포트가 프로세스 종료 방식과 절대 어긋나지 않는다.** 실패해도 부분 리포트가
남고, cleanup 중 `BaseException`(Ctrl-C 포함)도 기록한 뒤 남은 cleanup을 마치고 재전파합니다. 외부 리뷰
5라운드가 전부 이 한 불변식의 서로 다른 누수 경로였습니다.

**이 도구가 관측 못 하는 것을 리포트가 스스로 밝힙니다** — 탈락 후보의 원 verdict(drop이 `{agent_id, reason}`만
남김: `wrong_stance`는 verdict가 있었다가 이 이음매에서 사라진 것, `stance_unevaluated`는 애초에 없던 것 →
다르게 출력), raw competence 신호(어댑터 내부 translation에만 존재), preflight QID는 symbolic 규칙 기반
**heuristic**(agentic grounder는 그 규칙을 안 씀 → `probe_qid`라 부르고 불일치 시 명시), agent catalog 존재는
`unverified`(bourbon-api에 조회 수단 없음 = turn-on 게이트 3).

**안전 봉투:** `STAGE=prod` 거부(앱 startup 가드와 같은 규칙) · **requester self-exclusion 미구현** —
리포트가 매번 `self_exclusion_enforced: false`라는 **정책 상태**를 싣지만, 실제 self-recommendation
**검출은 `--requester-owner-id`를 준 run에서만** 되고 생략하면 "could not be checked at all"이라고 씁니다
(막지는 못하고 말하기만 합니다 = turn-on 게이트 1) · artifacts는 로컬 전용(gitignore) · 실제 statement
본문은 120자 절단이 기본.

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
