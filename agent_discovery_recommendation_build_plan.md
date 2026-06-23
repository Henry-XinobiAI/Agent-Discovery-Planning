# Agent Discovery & Recommendation — Build Plan (Alpha)

> 이 문서는 **구현 실행 계획**이다. 설계 기준은 `agent_discovery_recommendation_directions.md`, 무엇을 짓는지·경계·후보 기술은 `agent_discovery_recommendation_implementation.md`(이하 **spec**)에 있다. 여기서는 그것들을 `bourbon-agent-recommendation-api` 레포에 **어떤 디렉토리·모듈·파일·순서로** 올릴지를 정한다. 설계 논거는 재진술하지 않고 spec 절 번호로 가리킨다.
>
> 구현 대상: `../bourbon-agent-recommendation-api` · 코드 스타일 기준: `../bourbon-memory-api` · LLM: `../bourbon-agent`의 `e3llm` 디렉토리를 vendor(추후 replace 가능).

## 0. 이 계획이 따르는 기준 (확정 사실)

세 레포를 직접 확인한 결과 (2026-06-23):

| 사실 | 출처 | 계획에의 영향 |
|---|---|---|
| 대상 레포는 **빈 레포가 아니라 동작하는 템플릿**(`project-template-python`, initial commit). FastAPI app factory·`module/`(도메인)·`api/`·`cli/`(argparse)·`tests/`·Docker·k8s·pre-commit 완비 | `bourbon-agent-recommendation-api` | bootstrap이 아니라 **확장**. echo 예제를 도메인 모듈로 치환 |
| Python `>=3.14,<3.15`, uv(`package=false`), ruff(line 120, B/Q/I/ASYNC/T20), mypy(pydantic plugin) — `[tool.mypy]`에 `strict=true`는 **없고**, pre-commit이 `--disallow-untyped-defs`/`--disallow-incomplete-defs`/`--check-untyped-defs`로 type annotation을 강제, pytest-asyncio(auto), structlog | 두 레포 공통 | 새 코드도 동일 규칙. **새 도구 도입 없음** |
| memory-api 도메인 패턴: `StrictBaseModel`(strict+validate_assignment), API는 `ApiModel`(extra=forbid), `structs.py`/`router.py`/`repository.py`/`writer.py` 분리, `EnvSettings.get()` 싱글턴, async `.create()` 팩토리, keyword-only 인자, `from __future__ import annotations` | `bourbon-memory-api` | 그대로 복제 |
| anchor public API = `d8135bb` 기준 4개 라우트 + `AnchorSummary`/`Anchor`/`AnchorConnections`/`ArticleHit` (spec §2.6) | `bourbon-memory-api` | real provider가 이 표면에 묶임 |
| `e3llm`은 vendored 디렉토리(서브모듈/패키지 아님). `package=false`라 sibling 모듈로 import. `create_orchestrator()` + `json_schema_format` + `invoke_structured` 패턴 | `bourbon-agent` | 디렉토리 복사 + e3llm runtime deps를 main `[project] dependencies`에 추가(§5) |

**확정 결정 / 기본값** (§12에 모음): 아래 셋은 2026-06-23 리뷰에서 **확정**됐다 — 도메인 패키지명을 템플릿의 placeholder `module/` → **`discovery/`** 로 변경(서비스 전체가 "Agent Discovery & Recommendation"; Recommendation은 내부 단계), mock 저장소는 **in-memory(JSON fixture 로드)**(Postgres/graph/vector는 spec §4·§5대로 when-needed·Alpha 미도입), 이 계획 문서는 planning 레포에 보관. 나머지 기본값(LLM provider·echo 제거 등)은 §12 참고.

## 1. 목표와 비범위

**이 계획이 끝나면 가능한 것** (= Alpha 구현 + spec §8 평가):

1. `POST /recommend`가 `(topic_text, need_type, user_stance_ref?)`를 받아 후보 agent를 need에 맞게 정렬해 이유·`routing_target`과 함께 돌려준다.
2. 경로 전체가 돈다: **real anchor grounding(memory-api) + mock edge/persona/eligibility**. mock→real은 구현 교체뿐(spec §7.6).
3. `python -m cli eval run`으로 평가 하니스가 돌아 grounding/retrieval/gate/ranking/stance/coverage/reason 지표를 **need별·난이도 stratum별**로 보고하고 quality gate(ratchet)를 건다(spec §8).
4. mock 코퍼스가 **실제 QID에 grounding된, 가드 역산·난이도 층화·known-item needle을 포함한** 평가 가능 데이터다(spec §7.3·§8.4) — happy-path 더미가 아니다.

**비범위 (Alpha에서 안 함, spec §5)**: RecSys framework, vector/ANN, LTR, graph/vector DB, orthogonal serving, contested-axis, push silence policy의 학습형, contribution/reputation, safety/privacy gate 활성화(=inactive). LLM은 **linker 재정렬·stance 분류·B2 silver judge**에만 쓴다(단독 QID 생성 ❌, spec §4.1).

## 2. 디렉토리 / 모듈 레이아웃

템플릿 위에 얹는 최종 형태 (★=신규, ✎=수정, ⌫=제거):

```
bourbon-agent-recommendation-api/
├── e3llm/                         ★ bourbon-agent에서 복사 (vendored, replaceable)
├── api/
│   ├── main.py                    ✎ recommend 라우터 등록, echo 제거, lifespan에 provider 부착
│   ├── depends/
│   │   └── pipeline.py            ★ get_pipeline / get_providers (app.state에서 주입)
│   ├── middleware/                  (그대로)
│   ├── routers/
│   │   ├── health/                  (그대로)
│   │   ├── recommend/             ★ POST /recommend
│   │   │   ├── router.py
│   │   │   ├── structs.py         ★ RecommendRequest / RecommendResponse (ApiModel)
│   │   │   └── examples.py
│   │   └── echo/                  ⌫ 제거 (또는 reference로 보존)
│   └── structs/errors.py          ✎ 도메인 에러 추가(GroundingError 등)
├── discovery/                     ★ 도메인 패키지 (구 module/ 개명)
│   ├── config.py                  ★ EnvSettings 서브클래스 (MemoryApiSettings, LlmSettings, …)
│   ├── llm.py                     ★ e3llm 래퍼 (get_orchestrator / invoke_structured)
│   ├── log_config.py                (템플릿 것 유지)
│   ├── structs/
│   │   ├── base.py                ★ StrictBaseModel (memory-api 것 복제)
│   │   ├── anchor.py              ★ AnchorSummary/Anchor/AnchorConnections/ArticleHit (§2.6 필드 미러)
│   │   ├── edge.py                ★ AgentTopicEdge, Maturity, Stance, SourceOwner enum
│   │   ├── persona.py             ★ PersonaPrior
│   │   ├── eligibility.py         ★ Eligibility
│   │   └── recommend.py           ★ NeedType, Query, Candidate, Recommendation, DecisionLog
│   ├── providers/
│   │   ├── base.py                ★ 4개 Protocol (Knowledge/Edge/Persona/Eligibility)
│   │   ├── anchor_http.py         ★ HttpKnowledgeAnchorProvider [real] (memory-api httpx)
│   │   ├── mock_edge.py           ★ MockMemoryEdgeProvider (fixture-backed)
│   │   ├── mock_persona.py        ★ MockPersonaProvider
│   │   └── mock_eligibility.py    ★ MockEligibilityProvider
│   ├── linker/linker.py           ★ 모듈1: topic→QID 2-tier (anchor search + LLM rerank)
│   ├── retrieval/retrieval.py     ★ 모듈2: QID→edges + sparse 이웃 확장
│   ├── gate/gate.py               ★ 모듈3: maturity/eligibility 필터
│   ├── ranking/
│   │   ├── scorers.py             ★ 모듈4: depth/experience/for/against/coverage rule scorer
│   │   └── stance.py              ★ for/against 분류 (symbolic + LLM)
│   ├── serving/serving.py         ★ 모듈5: payload + routing_target + silence 판정(Alpha=stub)
│   ├── decision_log/log.py        ★ 모듈6: decision-log 기록 (day-one)
│   └── pipeline.py                ★ 1→6 오케스트레이션 (RecommendationPipeline)
├── eval/                          ★ 평가 하니스 (CLI에서 실행)
│   ├── corpus/                    ★ regression benchmark 본체 = git 추적 (§8.5)
│   │   ├── fixtures/
│   │   │   ├── anchors.json        ·  pinned 실제 QID 목록 (memory-api에서 선별)
│   │   │   ├── agents.json         ·  합성 agent
│   │   │   ├── edges.json          ·  합성 agent-topic edge (real QID grounding)
│   │   │   └── scenarios.json      ·  need별 시나리오 질의
│   │   └── gold/
│   │       └── gold.json           ·  4단계 gold label (scoring rule과 독립, §8.2)
│   ├── output/                    ★ eval 실행 산출물·report·`*.silver.json` 재생성분 = .gitignore
│   ├── builders/
│   │   ├── anchors.py             ★ memory-api에서 real anchor 선별 → corpus/fixtures/anchors.json
│   │   ├── corpus.py              ★ agent/edge/scenario 합성 (strata + needle)
│   │   └── guards.py              ★ §7.3 가드 역산 fixture 생성
│   ├── metrics/                   ★ grounding/retrieval/gate/ranking/stance/coverage/reason/calibration
│   ├── judge/silver.py            ★ B2 LLM silver judge (e3llm, §8.2)
│   ├── gates.py                   ★ quality gate threshold + ratchet (baseline.json)
│   ├── report.py                  ★ need×stratum 분해 리포트 + failure bucket
│   ├── harness.py                 ★ providers→pipeline→metrics 실행 루프
│   └── baseline.json              ★ ratchet 상태 (gate 기준선)
├── cli/
│   ├── __main__.py                ✎ recommend / eval / corpus 서브커맨드 등록
│   ├── recommend.py               ★ 단건 추천 실행
│   ├── corpus.py                  ★ 코퍼스 빌드 (build-anchors / build / build-guards)
│   └── eval.py                    ★ eval run / report
├── tests/                         ✎ echo 테스트 제거, 모듈별 단위 + integration 추가
├── .env.example                   ✎ MEMORY_API_BASE_URL, GOOGLE_CLOUD_*, EVAL_* 추가
└── pyproject.toml                 ✎ e3llm runtime deps를 main dependencies에 추가, eval/dev group 정리(§5)
```

원칙: **`api/`(전송) ↔ `discovery/`(도메인, FastAPI import 금지) ↔ `eval/`(평가) 3분리**. memory-api의 `memory/` 도메인 격리 규칙과 동일. `eval/`은 `discovery/`를 import하지만 그 역은 금지.

## 3. Provider 계약을 코드로 (Phase 1 동결 대상)

spec §2.4의 언어중립 sketch를 Python `Protocol`로 고정한다. mock·real이 **같은 Protocol**을 구현한다(spec §7.1). 이게 통합 경계 그 자체다.

```python
# discovery/providers/base.py
from __future__ import annotations
from typing import Protocol
from discovery.structs.anchor import Anchor, AnchorConnections, AnchorSummary, ArticleHit
from discovery.structs.edge import AgentTopicEdge
from discovery.structs.persona import PersonaPrior
from discovery.structs.eligibility import Eligibility

class KnowledgeAnchorProvider(Protocol):          # real (memory-api)
    async def search_candidates(self, text: str, *, lang: str | None = None) -> list[AnchorSummary]: ...
    async def get(self, qid: str) -> Anchor | None: ...
    async def expand_connections(self, qid: str, *, limit: int = 30) -> AnchorConnections: ...
    async def search_articles(self, q: str, *, qid: str | None = None, lang: str | None = None) -> list[ArticleHit]: ...

class MemoryEdgeProvider(Protocol):               # mock (Alpha)
    async def get_edges(self, anchor_id: str) -> list[AgentTopicEdge]: ...

class PersonaProvider(Protocol):                  # mock (Alpha)
    async def get_prior(self, agent_id: str) -> PersonaPrior | None: ...

class EligibilityProvider(Protocol):              # mock (Alpha)
    async def check(self, agent_id: str, *, context: dict | None = None) -> Eligibility: ...
```

**Real anchor provider** — memory-api를 httpx로 감싼다. memory-api의 `*.create()` async 팩토리·`EnvSettings` 패턴을 따른다. `limit`은 associative links만 제한한다는 spec §2.4 주석을 docstring에 박는다.

```python
# discovery/providers/anchor_http.py  (스케치)
class HttpKnowledgeAnchorProvider:
    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    @classmethod
    async def create(cls, *, settings: MemoryApiSettings | None = None) -> "HttpKnowledgeAnchorProvider":
        settings = settings or MemoryApiSettings.get()
        client = httpx.AsyncClient(base_url=settings.MEMORY_API_BASE_URL, timeout=settings.TIMEOUT_S)
        return cls(client)

    async def search_candidates(self, text, *, lang=None):
        r = await self._client.get("/knowledge/anchors", params={"q": text, "lang": lang})
        r.raise_for_status()
        return [AnchorSummary.model_validate(x) for x in r.json()]
    # get / expand_connections / search_articles 동형
    async def aclose(self) -> None: await self._client.aclose()
```

**Mock providers** — fixture 파일(JSON)을 `EdgeFixture` 형태로 로드해 in-memory dict로 서빙. real과 동일 Protocol. `get_edges`는 `anchor_id`(=QID) 키 조회. **fixture는 §7.3 가드 역산 케이스를 기본 포함**(아래 §8).

각 도메인 struct는 memory-api의 `StrictBaseModel`을 복제한 base 위에 둔다. anchor 4종은 spec §2.6 필드를 그대로 미러(우리가 memory-api를 패키지로 import하지 않고, provider 경계가 자기 모델을 소유 — 통합 시 계약 검증 지점). `AgentTopicEdge`는 모든 필드에 의미를 갖되, `source_owner`로 필드별 소유(Memory/Persona/owner/privacy)를 태깅(spec §7.2).

## 4. 파이프라인 (모듈 1→6)

`discovery/pipeline.py`가 spec §2.3 경로를 그대로 오케스트레이션한다. 순수 함수/작은 클래스로, 각 모듈은 자기 디렉토리에서 단독 테스트 가능.

```python
# discovery/pipeline.py  (스케치)
class RecommendationPipeline:
    def __init__(self, *, anchors: KnowledgeAnchorProvider, edges: MemoryEdgeProvider,
                 persona: PersonaProvider, eligibility: EligibilityProvider,
                 linker: Linker, ranker: Ranker, log: DecisionLog) -> None: ...

    async def recommend(self, query: Query) -> Recommendation:
        qid, grounding = await self._linker.resolve(query.topic_text, lang=query.lang)   # ① real anchor
        candidates = await self._retrieve(qid)                                           # ② mock edge (+ ① 이웃확장)
        survivors, dropped = await self._gate(candidates)                                # ③ mock eligibility
        ranked = await self._ranker.rank(survivors, need=query.need_type, stance=query.user_stance_ref)  # ④ persona mock + rule/LLM
        result = self._serve(ranked, qid=qid)                                            # ⑤ payload/routing_target/silence
        self._log.write(query, grounding, candidates, survivors, dropped, ranked)        # ⑥ decision-log
        return result
```

- **①  Linker (2-tier, spec §4.1)**: `search_candidates` → 후보가 모호/희박하면 `expand_connections`로 이웃 anchor 확장 → LLM rerank로 최종 QID 선택. LLM은 후보 위 재정렬만(`invoke_structured`로 구조화 출력). 단독 QID 생성 금지.
- **②  Retrieval**: `edges.get_edges(qid)`. sparse면 `expand_connections` 이웃 QID들로 풀 확장(이웃 확장은 real).
- **③  Gate**: maturity 임계 + `eligibility.check`(discoverable). safety/privacy는 Alpha inactive(spec §8.2).
- **④  Ranking**: need별 rule scorer + `persona.get_prior`(mock prior는 maturity를 못 채움 — hollow guard, spec §10) + stance 분류(for/against).
- **⑤  Serving**: 후보·이유·`routing_target` payload. push silence는 Alpha에서 threshold stub(policy는 Open Beta).
- **⑥  Decision-log**: 입력·중간값·생존/탈락 이유를 day-one 기록. Open Beta OPE replay harness로 승계(spec §7.5·§8.9). off-policy를 위해 propensity·action set·reward proxy 자리를 로그 스키마에 비워둔다(spec §7.5).

## 5. e3llm 통합

1. **vendor (pycache 제외)** — `../bourbon-agent/e3llm`에 `__pycache__`/`.pyc`가 있으므로 `cp -r`를 쓰지 않는다:
   ```bash
   rsync -a --exclude='__pycache__' --exclude='*.pyc' ../bourbon-agent/e3llm/ ./e3llm/
   ```
   (vendored, 추후 패키지로 replace 시 import 경로 불변. `.gitignore`의 `__pycache__` 규칙도 e3llm 하위에 적용되는지 확인.)
2. **dependency 배치 — runtime vs eval 분리** (대상 레포 Dockerfile은 `uv sync --frozen --no-install-project`로 **default group을 그대로 prod에 설치**한다). API runtime이 LLM(linker rerank·stance)과 anchor httpx를 쓰므로 e3llm 런타임 의존은 **dev group이 아니라 main `[project] dependencies`** 에 둔다 — 그래야 prod 이미지에 반드시 들어가고, 나중에 memory-api처럼 `--no-default-groups`로 바꿔도 빠지지 않는다:
   ```toml
   [project]
   dependencies = [ # ... 기존 fastapi/pydantic/structlog/sentry 등에 추가
     "google-genai>=1.74.0", "openai>=1.82.0", "httpx>=0.28.1", "dateparser>=1.3.0",  # e3llm runtime
   ]
   [dependency-groups]
   eval = ["…"]  # eval 전용 도구만 별도 group (judge·report 등 prod 불필요분)
   dev  = ["mypy", "pytest", "pytest-asyncio", "ruff", "…"]
   ```
   이러면 Dockerfile은 **수정 불필요**(runtime deps가 main에 있으므로). dev/eval만 group으로 남겨 prod 격리를 명확히 한다.
3. `discovery/llm.py`에 얇은 래퍼 — bourbon-agent `scribe/llm.py`의 `invoke_structured` 패턴을 그대로:
   ```python
   _orch: ChatOrchestrator | None = None
   def get_orchestrator() -> ChatOrchestrator:
       global _orch
       if _orch is None: _orch = create_orchestrator()
       return _orch
   async def invoke_structured(*, system: str, user: str, schema: type[T],
                               model: str | None = None) -> T | None:
       req = E3ChatRequest(model=model or LlmSettings.get().DEFAULT_MODEL,
                           messages=[ChatMessage(role="system", content=system),
                                     ChatMessage(role="user", content=user)],
                           response_format=json_schema_format(schema, name=schema.__name__))
       resp = await get_orchestrator().invoke(req)
       raw = resp.choices[0].message.content if resp.choices else None
       return schema.model_validate_json(raw) if raw else None
   ```
   사용처는 linker rerank(`discovery/linker`), stance 분류(`discovery/ranking/stance.py`), B2 judge(`eval/judge`) **세 곳뿐**. LLM 의존을 이 래퍼 뒤에 가둬, 추후 e3llm replace 시 영향 면적을 최소화한다.
4. `.env.example`에 `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` (Vertex ADC) 추가. LLM 호출은 항상 mockable하게(테스트는 fake orchestrator 주입).

## 6. 구현 단계 (순서·체크리스트)

각 Phase는 독립 PR 단위. **acceptance**를 못 넘으면 다음으로 안 간다(CLAUDE.md 검증 우선).

- **Phase 0 — Scaffold 정렬**: `module/`→`discovery/` 개명, echo 제거, `e3llm` vendor + deps, `.env.example`/config 추가, `cli` 골격. `pre-commit run --all-files`·`pytest` green.
- **Phase 1 — 계약 동결**: `discovery/structs/*` + `providers/base.py` Protocol. anchor 4종 필드를 spec §2.6에 1:1 맞춤. *acceptance*: `pre-commit run --all-files`(ruff+mypy) 통과, struct round-trip 테스트.
- **Phase 2 — Real anchor grounding**: `HttpKnowledgeAnchorProvider` + 최소 linker(LLM 없이 top-1). **provider lifecycle을 lifespan에 박는다**: startup에서 `await HttpKnowledgeAnchorProvider.create()`로 만들어 `app.state`에 붙이고, **shutdown에서 `await provider.aclose()`로 httpx client를 닫는다**(누수 방지). *acceptance*: 실제 memory-api(또는 recorded fixture)로 topic→QID가 도는 integration 테스트 + **startup create / shutdown close가 호출되는지 검증**(TestClient lifespan context).
- **Phase 3 — Mock providers + 코퍼스 로더**: `mock_edge/persona/eligibility` + JSON fixture 스키마. *acceptance*: fixture 로드→`get_edges` 조회 단위 테스트.
- **Phase 4 — Pipeline 1→6**: retrieval·gate·ranking(rule)·serving·decision-log. stance/LLM rerank는 rule/stub 먼저. *acceptance*: mock 위에서 `recommend(query)`가 끝까지 도는 단위 테스트 + decision-log 생성.
- **Phase 5 — API + CLI recommend**: `POST /recommend` + `python -m cli recommend …`. *acceptance*: TestClient integration 테스트(template `tests/integration` 패턴).
- **Phase 6 — 평가 코퍼스 빌더**: §8의 생성 전략 구현(real QID grounding·strata·needle·가드 역산·gold label). **real memory-api 의존을 빌드 시점으로 격리**: `corpus build-anchors`만 live memory-api를 호출해 anchor를 **선별·고정(`anchors.json`)하는 수동/갱신 전용** 명령이고, 그때 응답을 recorded fixture로 함께 저장한다. `corpus build`(agent/edge/scenario/gold 합성)와 이후 `eval run`은 **pinned `anchors.json` + recorded fixture만** 읽고 live 호출하지 않는다 → eval/CI는 네트워크 없이 결정론. *acceptance*: `python -m cli corpus build`가 재현 가능한 코퍼스+gold 산출, 검증 리포트(stratum 분포·needle 존재·QID 실재) green, **`eval run`이 memory-api 미가동 상태에서도 통과**.
- **Phase 7 — Eval 하니스 + 지표 + gate + CLI**: `python -m cli eval run`. need×stratum 지표, failure bucket, ratchet gate. *acceptance*: baseline 고정 후 재실행 시 gate green; `must_not_show` false-pass=0 / discoverability-off exposure=0 hard fail 동작.
- **Phase 8 — LLM rerank + stance + B2 silver judge**: linker disambiguation, for/against, `eval/judge`. *acceptance*: judge meta-eval(order-swap 일관성) + B1 agreement 측정 자리 동작(spec §8.2).
- **Phase 9 — 검증/CI**: eval을 CI step으로(ratchet=regression). lessons/리뷰 정리.

Phase 0–5 = "경로가 돈다", 6–8 = "평가가 돈다", 9 = "회귀가 잠긴다". Phase 2와 6은 둘 다 real anchor를 쓰므로 memory-api 응답을 **recorded fixture(VCR식)** 로 캐시해 오프라인 테스트를 가능케 한다.

## 7. 핵심 설계 규칙 (pythonic·simple)

- **Protocol 기반 DI** (PEP 544) — 상속 트리 없이 mock↔real 교체. FastAPI `Depends`로 `app.state`의 provider 주입(memory-api `depends/` 패턴).
- **Pydantic v2 strict** — 도메인은 `StrictBaseModel`, API는 `ApiModel(extra=forbid)`. enum은 `Field(strict=False)`(memory-api 규칙).
- **async 일관** — 모든 I/O(httpx, LLM) async. 팩토리는 `async def create`. keyword-only 인자.
- **`from __future__ import annotations`** 전 모듈. PEP 604 union(`str | None`), `list[...]`.
- **LLM은 래퍼 뒤에만** — `discovery/llm.invoke_structured` 외부에서 e3llm 직접 호출 금지(테스트 주입성·replace 대비).
- **over-engineering 금지** — Postgres/graph/vector/LTR/framework는 spec §5 when-needed. Alpha는 in-memory mock + structured 조회로 충분.
- **결정론** — eval 코퍼스 빌더는 seed 고정(재현). LLM 사용 지점은 항상 fake로 대체 가능.

## 8. Mock 코퍼스 & 평가 데이터 설계 (가장 중요한 부분)

사용자 요구: *"mock 데이터도 정말 discovery를 evaluation할 수 있는 데이터를 만든다."* spec §7.3·§8.1–8.4를 데이터 생성 절차로 구체화한다. **happy-path 더미 금지** — 데이터 자체가 설계 불변식의 regression set이 되게 한다.

### 8.1 생성 파이프라인 (spec §8.4)

```
① real anchor 선별   memory-api에서 20~30개 실제 QID (도메인 다양·dense/cold 혼합)
② agent 합성        30~50개. 각 agent에 expertise_claims/persona/stable_traits
③ edge 합성         agent×anchor → AgentTopicEdge. maturity/evidence/freshness/observed_stance
                    를 **명시적으로** 부여 (실제 산식은 Memory와 contract, Alpha는 우리가 심음)
④ scenario 합성     need 5종(depth/experience/for/against/coverage) × 20~40 = 100~200개
⑤ gold label        scoring rule과 **독립**으로 ideal/acceptable/bad/must_not_show 부여 (§8.2)
⑥ 검증              QID 실재(memory-api 조회)·stratum 분포·needle 존재·가드 커버리지
```

핵심 불변식: **edge가 가리키는 anchor는 반드시 real QID**(spec §8.3). 그래서 grounding(모듈1) 평가는 합성이 아니라 real substrate 위에서 실측된다. agent/edge만 합성.

### 8.2 난이도 stratum (spec §8.4) — 데이터에 강제

easy만 모으면 지표가 포화되어 아무것도 못 배운다. 빌더가 각 stratum을 **의도적으로** 심는다:

| stratum | 코퍼스에 심는 케이스 |
|---|---|
| **easy** | 명백 정답 + **known-item needle**(반드시 1등이어야 할 expert) — sanity |
| **guard** | §8.3 가드 역산 (discoverability off / weak evidence / wrong stance / hollow) |
| **hard / confusable** | near-duplicate expert(stance만 다름), adjacent-axis distractor, partial-evidence(maturity 부족), stale-but-valid vs fresh-but-shallow |
| **ambiguous** | 정답이 본질적으로 갈리는 stance 케이스 — gate 계산에서 제외, 별도 추적(spec §8.7) |

리포트는 stratum별 분리(spec §8.5) — aggregate는 hard 실패를 가린다.

### 8.3 가드 역산 fixture (spec §7.3) — 가드 1개당 깨는 케이스 1개

`eval/builders/guards.py`가 다음을 결정론적으로 생성. **이게 곧 설계 불변식의 regression 테스트**:

| fixture | 방어 가드 |
|---|---|
| dense / cold topic | sparse anchor fallback |
| ambiguous topic (QID 분기) | QID 정렬 실패 (§7.4) |
| same-axis disagreement | for/against 성립 |
| weak evidence agent | maturity gate |
| high persona / low memory | hollow agent (prior가 maturity 못 채움) |
| stale but valuable | freshness=decay, hard cutoff 아님 |
| discoverability off | privacy/eligibility gate |
| established axis 유무 | orthogonal / false controversy |

### 8.4 gold label ≠ scoring rule (spec §8.2) — 동어반복 방지

- gold label은 **스코어링 산식과 독립**으로 만든다. 같은 LLM/규칙이 데이터와 정답을 둘 다 만들면 construct validity 붕괴.
- **B1(human gold core, 소량)** = 산식과 독립된 *사람* 더블 라벨 — Alpha의 제한적 품질 주장은 **오직 여기서**. (Alpha 초기엔 B1을 "사람 검수 대기" 슬롯으로 두고, 합성 silver와 분리만 강제. 사람 라벨 채워지면 품질 비교 활성.)
- **B2(LLM silver, 대량)** = *다른* 프롬프트의 LLM judge — regression/탐색 커버리지용, **품질 주장 ❌**. 리포트에 항상 `silver` 표기.
- 라벨 4단계: `ideal` / `acceptable` / `bad` / `must_not_show`. `must_not_show`는 hard negative class(false-pass 직격).

### 8.5 산출물 형식 / 재현성

- 빌더는 **seed 고정 + 결정론**. 추적 정책을 한 곳으로 고정한다(§2 레이아웃과 일치):
  - **git 추적** = regression benchmark의 본체: `eval/corpus/fixtures/*.json`(anchors/agents/edges/scenarios)와 `eval/corpus/gold/*.json`(4단계 human/pinned gold). spec §8.4 "한 번 만들어 고정·재사용".
  - **`.gitignore`** = 매 실행 재생성되는 것: `eval/output/`(지표·report·decision-log dump)와 **LLM이 개입한 silver 산출물**(`*.silver.json`은 비결정적이라 추적하지 않고 빌더로 재생성).
- gold set 확장은 TREC식 pooling(여러 랭킹 변형 top-k + 랜덤 샘플 → 사람 판정). 빌더에 pool export 모드 포함.

## 9. Eval 하니스 & CLI

`eval/harness.py`가 **substrate-agnostic**(provider만 교체하면 mock↔real, spec §8.10·§7.1):

```
load corpus (anchors/agents/edges/scenarios/gold)
  → build providers (mock edge/persona/eligibility + real|recorded anchor)
  → for each scenario: pipeline.recommend(query) + decision-log 수집
  → metrics: grounding/retrieval/gate/ranking/stance/coverage/reason/calibration
  → report: need × stratum 분해 + failure bucket(§8.8)
  → gates: ratchet 비교 (baseline.json) → CI red/green
```

**지표** (spec §8.5, `eval/metrics/`): grounding(QID top-1/top-3, real substrate quality gate) · retrieval(Recall@K, mock edge regression) · gate(false block/false pass) · ranking(nDCG@K/MRR/P@K/MAP@K, B층 proxy) · stance(same-axis/opposite) · coverage(unique axis/source/persona, redundancy) · reason(evidence_ref 없는 설명·stance mismatch 수) · calibration. 구현은 표준식 직접(외부 평가 프레임워크 미도입; spec §4.2 `pytrec_eval` 회피).

**Quality gate** (spec §8.6, `eval/gates.py`): 숫자 게이트(grounding accuracy/recall, fallback rate)는 baseline 고정→ratchet. **`must_not_show` false pass = 0**, **discoverability-off exposure = 0** 은 처음부터 hard fail(ramp 없음).

**CLI** (argparse, memory-api/template 패턴):

```
python -m cli corpus build-anchors   # [live memory-api, 수동/갱신 전용] real QID 선별 → anchors.json + recorded fixture 저장
python -m cli corpus build           # [offline] pinned anchors.json 기반 agent/edge/scenario/gold 합성 (seed 고정)
python -m cli corpus build-guards    # [offline] §8.3 가드 역산 fixture
python -m cli eval run [--strata all|hard] [--needs depth,for,…] [--against-real]  # [offline] pinned anchors + recorded fixture
python -m cli eval report [--bucket]
python -m cli recommend --topic "…" --need depth   # 단건 디버그 (live/recorded 선택)
```

`build-anchors`만 live memory-api에 접속하고, 그 외 코퍼스 빌드·`eval run`·CI는 pinned `anchors.json` + recorded fixture로 **네트워크 없이 결정론**으로 돈다(Phase 6). `--against-real`을 줄 때만 통합 후 real edge에 붙는다.

`--against-real`은 mock edge 대신 real(통합 후) — 같은 gold set으로 substrate report(spec §8.10).

## 10. 테스트 & 검증 전략

- **단위**: 각 모듈(linker/retrieval/gate/ranking/serving/log) + metric 계산. LLM·httpx는 fake 주입.
- **integration**(`tests/integration`, TestClient): `POST /recommend` end-to-end(mock providers). template `test_api.py` 패턴(에러 envelope·request-id) 재사용.
- **recorded anchor**: memory-api 응답을 fixture로 녹화해 grounding 테스트를 오프라인·결정론으로.
- **eval = 회귀 테스트**: Phase 7부터 `python -m cli eval run`을 CI step. ratchet 하향 시 red(CLAUDE.md "완료 전 증명").
- **계약 테스트**: mock provider가 Protocol을 만족하는지 + struct가 spec §2.6 anchor 표면과 일치하는지(통합 시 real로 같은 테스트 재실행, spec §7.6).
- **staff-engineer 체크**: 새 도구 0개(기존 uv/ruff/mypy/pytest만), 도메인↔전송↔eval 격리 유지, LLM 의존 단일 래퍼.

## 11. 선결 / 능동 조율 (mock으로 못 숨김, spec §6.2·§7.4)

코드와 별개로 Alpha 중 Memory와 **합의 트랙**:

1. **QID vocabulary 의미 계약** — query-side linker QID ↔ producer-side anchoring QID가 같은 disambiguation 기준인지, alias/redirect/`LOCAL` anchor 규칙(spec §2.6·§7.4). 코퍼스 빌드가 이 정렬의 1차 리허설.
2. **edge contract shape + 필드별 source_owner** — `maturity/evidence_strength/freshness/observed_stance/routing_target/discoverability`를 실제로 줄 수 있는지(spec §2.6·§7.2). mock edge 스키마가 합의 초안 역할.

이 둘은 contract test가 "모양"만 보고 "값의 의미"는 못 잡으므로(spec §7.4) 별도 합의가 필요하다.

## 12. 결정·가정 (사용자 확인 대상) / Open Items

✅ = 2026-06-23 리뷰에서 사용자 확정. 나머지는 기본값(뒤집으려면 알려주세요):

| 결정 | 값 | 상태 |
|---|---|---|
| 도메인 패키지명 | `discovery/` (구 `module/`) | ✅ 확정 (recommendation/은 RecSys affinity로 오독 위험) |
| 이 계획 문서 위치 | planning 레포(여기) | ✅ 확정 |
| mock 저장소 | in-memory(JSON fixture) | ✅ 확정 (Postgres/vector는 spec §5 when-needed) |
| eval 산출물 git 추적 | fixtures/gold 추적, output/silver ignore (§8.5) | 기본값 |
| LLM provider | e3llm 기본 `google/gemini`(Vertex ADC) | 기본값 (OpenAI 대안) |
| echo 라우터 | 제거 | 기본값 |
| e3llm runtime deps 배치 | main `[project] dependencies` (dev/eval만 group) | ✅ 리뷰 반영 (§5) |

Open Items(코드 무관, spec §9 deep research 대상): 한국어 EL 2-tier 세부, KG access(memory-api vs WDQS vs self-host), edge store 확정(통합 후), vector 도입 조건, eval stack(자체 metric 유지 vs Evidently).

---

**다음 행동**: §12 결정이 확정됐으므로(✅), 승인 시 **Phase 0**(scaffold 정렬: `module/`→`discovery/` 개명 + e3llm vendor + runtime deps 배치 + echo 제거 + `.env.example`/config)부터 착수한다.
