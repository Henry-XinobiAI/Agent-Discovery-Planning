# Agent Discovery & Recommendation — Build Plan (Alpha)

> **📦 보관됨 (2026-07-14) — historical.** 이 build plan은 Phase 1–7 실행 계획의 히스토리 기록이다. 현재 구현 계약·순서의 source of truth는 `../impl/`(특히 `../impl/README.md` + `01`–`11`)이고, 실제 구현 plan은 코드 레포 `tasks/todo.md`에 있다. 아래 내용은 당시 계획 그대로 두되 최신 상태와 어긋날 수 있다.

> 이 문서는 **구현 실행 계획**이다. 설계 기준은 `agent_discovery_recommendation_directions.md`, 무엇을 짓는지·경계·후보 기술은 `agent_discovery_recommendation_implementation.md`(이하 **spec**)에 있다. 여기서는 그것들을 `bourbon-agent-recommendation-api` 레포에 **어떤 디렉토리·모듈·파일·순서로** 올릴지를 정한다. 설계 논거는 재진술하지 않고 spec 절 번호로 가리킨다.
>
> 구현 대상: `../bourbon-agent-recommendation-api` · 코드 스타일·LLM 레이어 기준: `../bourbon-memory-api`(`memory/llm/` OpenAI-compatible proxy 패턴 포팅; e3llm SDK 직접 의존 안 함, §5).

## 0. 이 계획이 따르는 기준 (확정 사실)

세 레포를 직접 확인한 결과 (base: 2026-06-23, memory-api 계약: **2026-07-07 재확인 — main `bc9110c`(#60)까지도 public `/knowledge/entities*` 계약 불변**. `d66b2c1`→`bc9110c`은 **29커밋·288파일**(image/vision·SDK 추출 `#52`·OpenSearch/contract cleanup `#51`·conversation/artifact·webapp·eval)로 크지만 **전부 미러 계약 밖**: read model `public/structs.py`·`entity_repository.py`와 `/knowledge` `router.py`(5라우트·6모델) diff 0, `Page[T]`(`{items,limit,truncated}`)도 불변(그 파일 `api/routers/base.py`는 artifact용 `ArtifactContentResponse` 추가로 +36 변했으나 `Page[T]` 자체는 무변경). entity rename은 `8ffcec8`에서 도입. `4106366`→`d66b2c1`은 LongMemEval 평가 튜닝·**신규 conversation artifacts/conversations 라우트(대화메모리 도메인 = Discovery 범위 밖)**·personal KG 강화(statement→public-KG-by-QID 매핑·entity salience·context-band)·shared-utils 위주로 **public entity 계약은 동일**. salience/statement-edge는 이제 main personal KG에 있으나 Discovery edge 계약(`AgentTopicEdge`) 대체물이 아니다 — §4②·§11 메모):

> **★2026-07-14 감사 정정 (`bc9110c`→`2f268fe`, 38커밋): 위 "public entity 계약 불변" 명제는 이 구간에서 처음 깨졌다.** ⑴ `/knowledge/entities/suggest` 라우트 + `EntitySuggestion` struct **삭제**(#87) → 아래 표·§3의 "5라우트·6모델(incl suggest/EntitySuggestion)"은 이제 **4라우트**(+ additive `neighbors`/`typed-relations`)다. ⑵ `GET /knowledge/entities` search에 `context=`/`types=` 파라미터 landing(#78 다국어 fix 포함). ⑶ **`EntitySummary`(linker/search 소비 struct)만 필드 불변**(query-time `_score` 없음). ⑷ **#64 competence vector**(Discovery expertise 축)가 personal KG에 신설 → §4②·§705 메모 재정의(아래). 상세 = memory-api-state 메모 `2f268fe` 블록. discovery provider의 `suggest()`/`EntitySuggestion`(providers/base·entity_http·structs/entity)는 이제 stale = code repo cleanup 티켓(grounding은 search-only라 런타임 무영향).

| 사실 | 출처 | 계획에의 영향 |
|---|---|---|
| 대상 레포는 **빈 레포가 아니라 동작하는 템플릿**(`project-template-python` 유래). FastAPI app factory·도메인 패키지·`api/`·`cli/`(argparse)·`tests/`·Docker·k8s·pre-commit 완비 | `bourbon-agent-recommendation-api` | bootstrap이 아니라 **확장**. echo 예제를 도메인 모듈로 치환 |
| **현재 상태(2026-06-23 재확인 기준)**: 사용자가 **`module/`→`discovery/` 개명을 이미 완료**. `discovery/`는 현재 템플릿 잔재(`echo/`·`utils/`·`log_config.py`)만 보유. echo router/health 잔존, `discovery/llm/`·`recommend` router·`eval/`·`discovery/{structs,providers,linker}` **미존재**. `.env.example`에 `MEMORY_API_BASE_URL`/`LLM_PROXY_*` **없음** | `bourbon-agent-recommendation-api` | **Phase 0의 개명 단계는 완료**(§6). 나머지 Phase 0(echo 제거·LLM 레이어 포팅·deps·env)부터 착수 |
| pyproject 기존 deps에 **`httpx[http2]`·`dateparser`·`aiofiles`·`aiohttp` 이미 포함**, `tool.uv`에 `default-groups` 없음(dev만 implicit) | `bourbon-agent-recommendation-api` | LLM 레이어 추가분은 **`google-genai` 하나뿐**(OpenAI는 raw httpx, `httpx[http2]` 기존; `openai`/e3llm 불필요, §5) |
| Python `>=3.14,<3.15`, uv(`package=false`), ruff(line 120, B/Q/I/ASYNC/T20), mypy(pydantic plugin) — `[tool.mypy]`에 `strict=true`는 **없고**, pre-commit이 `--disallow-untyped-defs`/`--disallow-incomplete-defs`/`--check-untyped-defs`로 type annotation을 강제, pytest-asyncio(auto), structlog | 두 레포 공통 | 새 코드도 동일 규칙. **새 도구 도입 없음** |
| memory-api 도메인 패턴: `StrictBaseModel`(strict+validate_assignment), API는 `ApiModel`(extra=forbid), `structs.py`/`router.py`/`repository.py`/`writer.py` 분리, `EnvSettings` + `.from_env()` 클래스메서드, async `.create()` 팩토리, keyword-only 인자, `from __future__ import annotations` | `bourbon-memory-api` | 그대로 복제 |
| knowledge public API = **`8ffcec8`(unify /knowledge & /personal + anchor/node→**entity** rename) / main `bc9110c`(2026-07-07 재확인 — ★ 그후 `2f268fe`에서 #87로 깨짐, 위 감사 노트 참조)** 기준 (당시) 5라우트였으나 **현행은 4라우트**(`entities/suggest` 삭제) `GET /knowledge/{entities, entities/{qid}, entities/{qid}/connections, articles}` + 모델 `EntitySource`/`Entity`/`EntitySummary`/~~`EntitySuggestion`~~[#87 삭제]/`EntityConnections`/`ArticleHit`. **list 응답은 `Page[T]={items,limit,truncated}` transport envelope**(cursor 아님), `entities/{qid}`·`connections`만 bare 모델 (spec §2.6) | `bourbon-memory-api` | real provider가 이 표면에 묶임. **`Page[T]` unwrap은 provider 책임**(`.items`만 도메인에 전달, envelope가 Discovery로 새지 않음) |
| LLM은 e3llm SDK 직접 의존이 아니라 memory-api `memory/llm/` 패턴(OpenAI-compatible proxy client + 자체 provider 레이어; `memory/`에 `import e3llm` 0건). 런타임은 `LLM_PROXY_URL` 뒤 e3llm-api 프록시 서비스 | `bourbon-memory-api` | `memory/llm/`을 `discovery/llm/`로 포팅(proxy default, direct provider=inactive) + `google-genai`를 main `[project] dependencies`에 추가(§5) |

**확정 결정 / 기본값** (§12에 모음): 아래 셋은 2026-06-23 리뷰에서 **확정**됐다 — 도메인 패키지명 `module/` → **`discovery/`**(**현재 기준 적용 완료**; 서비스 전체가 "Agent Discovery & Recommendation"·Recommendation은 내부 단계), mock 저장소는 **in-memory(JSON fixture 로드)**(Postgres/graph/vector는 spec §4·§5대로 when-needed·Alpha 미도입), 이 계획 문서는 planning 레포에 보관. 나머지 기본값(LLM provider·echo 제거 등)은 §12 참고.

## 1. 목표와 비범위

**이 계획이 끝나면 가능한 것** (= Alpha 구현 + spec §8 평가):

1. `POST /recommend`가 `(topic_text, need_type, user_stance_ref?)`를 받아 후보 agent를 need에 맞게 정렬해 이유·근거와 함께 `agent_id` 목록으로 돌려준다(이 **후보 반환 full path**는 provider가 갖춰진 local/eval/test override에서 성립; 배포본은 아래 Alpha 의미 배너 참조).
2. 경로 전체가 **local CLI / eval / TestClient(dependency override)** 에서 end-to-end로 검증된다: **real(또는 pinned fixture) anchor grounding + `eval/providers/`의 mock edge/persona/eligibility**. 배포 앱은 real provider만 와이어링하고 mock을 서빙에 쓰지 않는다(§3 와이어링 규칙). mock→real은 구현 교체뿐(spec §7.6).
3. `uv run python -m cli eval run`으로 평가 하니스가 돌아 grounding/retrieval/gate/ranking/stance/coverage/reason 지표를 **need별·난이도 stratum별**로 보고하고 quality gate(ratchet)를 건다(spec §8).
4. mock 코퍼스가 **실제 QID에 grounding된, 가드 역산·난이도 층화·known-item needle을 포함한** 평가 가능 데이터다(spec §7.3·§8.4) — happy-path 더미가 아니다.

> **Alpha의 의미 (배포 모델 명확화).** Alpha 완료 = "**mock-backed API를 배포한다**"가 아니라 "**API contract + pipeline + eval harness를 mock substrate로 검증 완료한다**"이다. 배포 아티팩트(dev/prod)는 **real provider만** 와이어링하며, edge/persona/eligibility의 real이 아직 없으면 그 경로는 통합 시점에 채워진다(spec §7.6). mock-first 개발·튜닝은 **로컬 CLI/eval/test**에서 일어난다.

**비범위 (Alpha에서 안 함, spec §5)**: RecSys framework, vector/ANN, LTR, graph/vector DB, orthogonal serving, contested-axis, push silence policy의 학습형, contribution/reputation, **favorite/user-preference의 ranking 소비**(§3·§4.2에 reserved — slot만 예약, score 미사용), safety/privacy gate 활성화(Alpha에서는 inactive, directions §11). LLM은 **linker 재정렬·stance 분류·B2 silver judge**에만 쓴다(단독 QID 생성 ❌, spec §4.1).

## 2. 디렉토리 / 모듈 레이아웃

템플릿 위에 얹는 최종 형태 (★=신규, ✎=수정, ⌫=제거):

```
bourbon-agent-recommendation-api/
├── api/
│   ├── main.py                    ✎ recommend 라우터 등록, echo 제거, lifespan에 provider 부착
│   ├── depends/
│   │   └── pipeline.py            ★ get_pipeline / get_providers (배포=real만 주입, eval/ import 금지)
│   ├── middleware/                  (그대로)
│   ├── routers/
│   │   ├── health/                  (그대로)
│   │   ├── recommend/             ★ POST /recommend
│   │   │   ├── router.py
│   │   │   ├── structs.py         ★ RecommendRequest / RecommendResponse (ApiModel)
│   │   │   └── examples.py
│   │   └── echo/                  ⌫ 제거 (또는 reference로 보존)
│   └── structs/errors.py          ✎ 도메인 에러 추가(GroundingError 등)
├── discovery/                     ✓ 도메인 패키지 (module/→discovery/ 개명 완료)
│   ├── echo/                      ⌫ 현재 템플릿 잔재 — 제거
│   ├── utils/                       (elapsed_timer·sentry, 템플릿 것 유지)
│   ├── config.py                  ★ EnvSettings base(memory-api `memory/config.py` 복제) + MemoryApiSettings(Phase 0 minimal: URL·timeout → Phase 2 확장). RankingSettings[§4.2 임계]·LinkerSettings[§4① 임계]는 Phase 4/8에서 추가(LLMSettings는 llm/config.py §5)
│   ├── llm/                       ★ memory-api `memory/llm/` 포팅 (config·providers·proxy·structured·wrapper; proxy default, direct=inactive, §5)
│   ├── log_config.py                (템플릿 것 유지)
│   ├── structs/
│   │   ├── base.py                ★ StrictBaseModel (memory-api 것 복제)
│   │   ├── entity.py              ★ Entity* read models (EntitySummary/Entity/EntitySuggestion[#87 삭제·stale]/EntityConnections/ArticleHit) + Page[T] (provider-parsing 전용 transport helper — `__all__`/domain import 비노출, entity_http가 .items 언랩 후 버림, pipeline/ranking 비전파; 도메인 anchor 개념은 §3 노트)
│   │   ├── edge.py                ★ AgentTopicEdge, Stance, SourceOwner enum
│   │   ├── persona.py             ★ PersonaPrior
│   │   ├── eligibility.py         ★ Eligibility
│   │   ├── recommend.py           ★ NeedType, MaturityBand, AnchorVia, Query, NormalizedQuery, UserStanceRef, Candidate, Recommendation
│   │   └── decision_log.py        ★ DecisionLogRecord + 하위 record 모델 (§4.3 audit record — writer는 discovery/decision_log.py)
│   ├── providers/                   ← shipped 런타임 경계만 (mock은 eval/에, 아래 주석)
│   │   ├── base.py                ★ 4개 Protocol (Knowledge/Edge/Persona/Eligibility)
│   │   ├── entity_http.py         ★ HttpKnowledgeEntityProvider [real] (memory-api /knowledge/entities httpx, Page unwrap)
│   │   └── unavailable.py         ★ Unavailable{Edge,Eligibility}Provider(호출 시 raise→503) + NullPersonaProvider(get_prior→None) — real 미통합 시 배포 default (edge/elig=hard, persona=degradable, §3)
│   ├── linker.py                  ★ 모듈1: topic→QID deterministic symbolic linker (search-only, no LLM — LLM rerank는 Phase 8)
│   ├── retrieval.py               ★ 모듈2: QID→edges + sparse 이웃 확장
│   ├── gate.py                    ★ 모듈3: maturity/eligibility 필터
│   ├── ranking.py                 ★ 모듈4: need별 ordering(depth/experience/for/against/coverage, §4.2 — scalar score 아님) + for/against stance 분류(symbolic)
│   ├── serving.py                 ★ 모듈5: payload(agent_id·이유·evidence_refs) + silence 판정(Alpha=stub)
│   ├── decision_log.py            ★ 모듈6: decision-log writer (day-one; record 모델은 structs/decision_log.py)
│   └── pipeline.py                ★ 1→6 오케스트레이션 (RecommendationPipeline)
├── eval/                          ★ 평가 하니스 (CLI에서 실행)
│   ├── providers/                 ★ mock providers — 로컬 CLI/eval 전용, 배포 serving 경로 미사용
│   │   ├── knowledge.py           ·  MockKnowledgeEntityProvider (pinned anchor fixture 서빙, offline substrate)
│   │   ├── edge.py                ·  MockMemoryEdgeProvider (discovery Protocol 구현)
│   │   ├── persona.py             ·  MockPersonaProvider
│   │   └── eligibility.py         ·  MockEligibilityProvider
│   ├── corpus/                    ★ regression benchmark 본체 = git 추적 (§8.5)
│   │   ├── structs.py             ·  Scenario/GoldLabel/PinnedAnchorFixture + Stratum/GoldLabelClass/GoldSource enum (§8.6·§8.7)
│   │   ├── fixtures/
│   │   │   ├── anchors.json        ·  pinned anchor fixture = eval/CI offline anchor substrate (PinnedAnchorFixture schema §8.7; search/detail/connections 포함, §9)
│   │   │   ├── agents.json         ·  합성 agent
│   │   │   ├── edges.json          ·  합성 agent-topic edge (real QID grounding)
│   │   │   └── scenarios.json      ·  need별 시나리오 질의 (Scenario, §8.6)
│   │   └── gold/
│   │       └── gold.json           ·  4단계 gold label (GoldLabel, scoring rule과 독립, §8.4·§8.6)
│   ├── output/                    ★ eval 실행 산출물·report·`*.silver.json` 재생성분 = .gitignore
│   ├── builders/
│   │   ├── anchors.py             ★ memory-api에서 real anchor 선별 → corpus/fixtures/anchors.json
│   │   ├── corpus.py              ★ agent/edge/scenario 합성 (strata + needle)
│   │   └── guards.py              ★ §7.3 가드 역산 fixture 생성
│   ├── metrics/                   ★ grounding/retrieval/gate/ranking/stance/coverage/reason/calibration
│   ├── judge/silver.py            ★ B2 LLM silver judge (LLM proxy, §8.2)
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
├── .env.example                   ✎ MEMORY_API_BASE_URL, LLM_PROXY_URL/MODEL, EVAL_* 추가 (GOOGLE_CLOUD_*·OPENAI_API_KEY=optional direct mode 주석)
└── pyproject.toml                 ✎ google-genai를 main dependencies에 추가, eval/dev group 정리(§5)
```

원칙: **`api/`(전송) ↔ `discovery/`(도메인, FastAPI import 금지) ↔ `eval/`(평가) 3분리**. memory-api의 `memory/` 도메인 격리 규칙과 동일. `eval/`은 `discovery/`를 import하지만 그 역은 금지.

## 3. Provider 계약을 코드로 (Phase 1 동결 대상)

spec §2.4의 언어중립 sketch를 Python `Protocol`로 고정한다. mock·real이 **같은 Protocol**을 구현한다(spec §7.1). 이게 통합 경계 그 자체다.

> **용어: anchor(도메인) vs `Entity*`(코드 타입).** memory-api가 `8ffcec8`에서 public read model을 `Anchor*`→`Entity*`로 개명했다. Discovery 문서에서 **anchor는 "topic을 고정하는 QID 기준점"이라는 도메인 개념으로 계속 쓴다**(anchor grounding, `AnchorVia`, pinned `anchors.json` 등). 다만 **memory-api 계약을 미러하는 코드 타입·provider명은 `Entity*`/`KnowledgeEntityProvider`로 맞춘다.** 둘은 충돌이 아니라 레이어가 다른 것 — 개념(anchor) ↔ 전송 타입(Entity).

```python
# discovery/providers/base.py
from __future__ import annotations
from collections.abc import Mapping
from typing import Any, Protocol
from discovery.structs.entity import Entity, EntityConnections, EntitySummary, EntitySuggestion, ArticleHit  # EntitySuggestion: memory-api #87로 라우트 삭제 → stale
from discovery.structs.edge import AgentTopicEdge
from discovery.structs.persona import PersonaPrior
from discovery.structs.eligibility import Eligibility

class KnowledgeEntityProvider(Protocol):          # real (memory-api /knowledge/entities)
    async def search_candidates(self, text: str, *, limit: int = 20) -> list[EntitySummary]: ...   # GET /knowledge/entities (full-text)
    async def suggest(self, text: str, *, limit: int = 8) -> list[EntitySuggestion]: ...            # ⚠ DELETED memory-api #87 — route gone; stale method (cleanup only)
    async def get(self, qid: str) -> Entity | None: ...
    async def expand_connections(self, qid: str, *, limit: int = 30) -> EntityConnections: ...
    async def search_articles(self, q: str, *, qid: str | None = None, lang: str | None = None, limit: int = 10) -> list[ArticleHit]: ...  # memory-api: limit ge=1 le=100

class MemoryEdgeProvider(Protocol):               # runtime contract; Alpha는 local/eval에서만 mock 구현
    async def get_edges(self, anchor_id: str) -> list[AgentTopicEdge]: ...
    # Future real edge source 후보(메모): memory-api `GET /personal/groundings/{qid}` → Page[GroundingMatch]
    # ={owner_id, entity:PersonalEntitySummary}. QID→owner personal entity retrieval은 시드하지만
    # maturity/evidence_strength/freshness/observed_stance/stance_confidence가 빠져 있어 AgentTopicEdge를
    # 대체하지 못함 — translation layer 또는 전용 discovery endpoint 필요(Open Beta).
    # agent_id는 memory가 아니라 owner_id에서 파생: bourbon-api personal_agent_id(owner_id)=uuid5(결정적).
    # routing_target은 계약에서 제거(memory·agent-rec 둘 다 미관리; bourbon-api가 런타임 dispatch 해석).
    # (owner_id==bourbon-api users.id 전제 — memory 팀과 확인 필요.)

class PersonaProvider(Protocol):                  # runtime contract; Alpha는 local/eval에서만 mock 구현
    async def get_prior(self, agent_id: str) -> PersonaPrior | None: ...

class EligibilityProvider(Protocol):              # runtime contract; Alpha는 local/eval에서만 mock 구현
    async def check(self, agent_id: str, *, context: Mapping[str, Any] | None = None) -> Eligibility: ...
```

**Real entity provider** — memory-api `/knowledge/entities`를 httpx로 감싼다. memory-api의 `EnvSettings` + classmethod 팩토리 패턴을 따르되, 실제 구현은 **동기 `from_settings()`**(내부에서 `MemoryApiSettings.get()`을 읽음)로 client를 구성한다(async `create()` 아님). `connections`의 `limit`은 associative links만 제한한다는 §2.6 주석을 docstring에 박는다. **list 라우트(`entities`/`suggest`/`articles`)는 `Page[T]={items,limit,truncated}` envelope을 반환하므로 provider가 `.items`로 unwrap**하고 도메인에는 `list[Entity*]`만 넘긴다(envelope이 Discovery 도메인으로 새지 않게 — transport 책임은 provider에 가둔다). **`lang`은 `search_articles`에만 있다** — `entities`/`suggest` 검색 계약엔 `lang` 파라미터가 없으므로(핵심 파라미터는 `q`) candidate 검색에는 전달하지 않는다(계약 drift 방지).

```python
# discovery/providers/entity_http.py  (스케치)
class HttpKnowledgeEntityProvider:
    def __init__(self, base_url: str, *, timeout: float = 10.0, http2: bool = True,
                 limits: httpx.Limits | None = None, max_retries: int = 3,
                 client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, http2=http2, limits=limits or httpx.Limits())
        self._max_retries = max(1, max_retries)          # >=1: retry loop body가 최소 1회 실행

    @classmethod
    def from_settings(cls) -> "HttpKnowledgeEntityProvider":     # 배포 와이어링 경로 (동기 팩토리)
        cfg = MemoryApiSettings.get()
        return cls(base_url=cfg.MEMORY_API_BASE_URL, timeout=cfg.MEMORY_API_TIMEOUT_SECONDS,
                   http2=cfg.MEMORY_API_HTTP2, max_retries=cfg.MEMORY_API_MAX_RETRIES,
                   limits=httpx.Limits(max_connections=cfg.MEMORY_API_MAX_CONNECTIONS,
                                       max_keepalive_connections=cfg.MEMORY_API_MAX_KEEPALIVE_CONNECTIONS))

    async def search_candidates(self, text: str, *, limit: int = 20) -> list[EntitySummary]:
        r = await self._get("/knowledge/entities", params={"q": text, "limit": limit})  # GET-only backoff retry(429/5xx/transport)
        return Page[EntitySummary].model_validate_json(r.content).items   # raw JSON bytes(.text 아님) → Page envelope → .items (transport는 여기서 끝)
    # suggest(/knowledge/entities/suggest) / get / expand_connections / search_articles 동형 — list 라우트는 모두 Page[T].items로 unwrap
    async def close(self) -> None: await self._client.aclose()
```

> **HTTP client 규칙 (효율의 실제 레버).** agent-recommendation-api는 매 요청마다 memory-api를 호출하므로 **client lifecycle이 성능을 가른다**. 규칙: **request마다 `httpx.AsyncClient`를 새로 만들지 않는다 — lifespan에서 1번 생성해 `app.state`로 재사용**(connection pool·keep-alive 재사용). 이게 핵심이고, `httpx` vs `aiohttp` 선택은 부차적이다(둘 다 pooling 지원). httpx를 1차로 두는 이유: 템플릿·memory-api에 `httpx[http2]` 이미 존재(의존성 0 추가), **`httpx.MockTransport`** 로 외부 도구 없이 테스트 결정론(새 도구 0개 원칙 유지 — `respx` 등 미도입), Protocol 뒤라 병목 확인 시 호출부 변경 없이 교체 가능. **fan-out**(linker의 이웃 anchor `get()` 다발)은 라이브러리 교체가 아니라 `asyncio.gather` + `httpx.Limits` 튜닝으로 푼다. 대량 streaming·connector 세밀 튜닝이 실측 병목이 되면 그때 provider 내부만 aiohttp로 교체한다.

**Mock providers** — fixture JSON을 in-memory dict로 서빙하는 얇은 어댑터. `discovery/providers/base.py`의 Protocol을 구현하지만(real과 동일 인터페이스, §7.1) **위치는 `discovery/`가 아니라 `eval/providers/`다.** 이유: mock은 **로컬 CLI 튜닝 + eval 전용**이고 dev/prod 배포본의 serving 경로에서는 쓰이지 않는다(repo·이미지엔 존재하되 미사용). 런타임 의존이 아니므로 shipped 도메인 패키지에 두지 않는다. mock 데이터(`eval/corpus/fixtures/*`)는 튜닝하며 계속 늘어난다.

> **provider 와이어링 규칙 (배포 경계).** **배포 앱**(`api/depends/pipeline.py`)은 **real provider만** 와이어링하고 `eval/`을 import하지 않는다 — 배포본 serving 경로에 mock import가 0이어야 한다. **mock 합성**은 `cli/recommend.py`(로컬 디버그)·`cli/eval.py`·`eval/harness.py`·tests에서만 일어난다(real anchor + `eval/providers/`의 mock edge/persona/eligibility). 이로써 §7 mock-first 개발/튜닝은 로컬·eval에서 돌리고, 배포본은 real 계약에만 묶인다(통합 = real 채워짐).
>
> **Alpha 배포본의 real provider 공백 처리.** Alpha 시점엔 edge/persona/eligibility의 real 구현이 아직 없다(Memory/Persona 미통합). 배포 앱은 mock으로 fallback하지 않고, real-slot에 **shipped default**를 와이어링한다: `edge`·`eligibility`는 **`Unavailable{Edge,Eligibility}Provider`**(호출 시 `upstream_unavailable` 503), `persona`는 **`NullPersonaProvider`**(`get_prior`→`None`). 결과: 배포 `/recommend`는 **anchor grounding(real)까지는 동작**하고, edge에 의존하는 후보 생성/랭킹 단계에서 **503을 정직하게 반환**한다(가짜 후보 ❌). 이 default들은 real이 통합되면 real 구현으로 교체(= §7.6 통합). 즉 "후보를 돌려준다"는 **로컬/eval/test(override)** 에서 검증되고, 배포 serving의 후보 경로 활성화는 real 통합 시점이다. **provider 필수성 구분(부분 통합 대비)**: `edge`·`eligibility`는 **hard-required**(없으면 후보·게이트가 성립 안 함 → `Unavailable*`가 503), `persona`는 **optional/degradable**(`get_prior`가 `PersonaPrior \| None`, ranking에선 동일 band 내 late 보조뿐 — hollow guard). 따라서 **`UnavailablePersonaProvider`는 만들지 않는다** — persona 공백은 배포 default부터 `NullPersonaProvider`(`None`)로 degrade하므로 persona 부재가 503을 유발하지 않는다(edge만 먼저 통합되는 부분 통합에서도 동일).
>
> **Reserved (Alpha 미구현) — `UserPreferenceProvider`.** favorite/hidden/muted/dismissed는 `bourbon-api` 출처의 **user→agent preference 신호**(Memory/Persona와 소유가 다름). Alpha에서는 코드 Protocol·`Unavailable*` provider를 만들지 않고 **문서 레벨 integration point만 예약**한다. positive favorite은 **Post-Open-Beta** tie-break, negative preference는 **Open Beta 후보 항목**(serving suppression). 상세: directions §9.7, §4.2.

각 도메인 struct는 memory-api의 `StrictBaseModel`을 복제한 base 위에 둔다. memory-api entity read model(`EntitySummary`/`Entity`/`EntityConnections`/`ArticleHit`; `EntitySuggestion`은 memory-api #87로 삭제 → discovery 미러는 stale)은 spec §2.6 표면을 미러하고, `Page[T]` envelope은 provider parsing helper로만 둔다(read model이 아니라 transport — §2 레이아웃). 우리가 memory-api를 패키지로 import하지 않고, provider 경계가 자기 모델을 소유 — 통합 시 계약 검증 지점.

### 3.1 도메인 struct 핵심 필드 (mock fixture 해석 고정)

mock fixture를 만들 때 필드 해석이 열리지 않도록 핵심 struct의 필드·타입·소유를 못 박는다. (값 범위는 contract v0 가정이며 §7.2에서 Memory/Persona와 공동 서명한다. 실수형 점수는 모두 `0.0–1.0`.)

**enums** — `NeedType`(`depth`/`experience`/`for`/`against`/`coverage`) · `Stance`(`for`/`against`/`neutral`) · `SourceOwner`(`memory`/`persona`/`owner`/`privacy`/`safety`) · `AnchorVia`(`direct`/`neighbor`) · `MaturityBand`(`high`/`medium`/`low` — raw `maturity`를 cutoff로 band화, §4.2 ordering·§4.3 log에서 사용) · `ExperienceSourceType`(`firsthand`/`secondhand` — experience need 전용 근거 출처 종류, directions §9.1 `source_type`; `None`은 "직접 경험 근거 없음"=추상 지식 edge를 뜻한다). 전부 `StrEnum` + `Field(strict=False)`(memory-api 규칙).

> **similarity need 결정**: directions/Roadmap에는 `similarity`가 남아 있으나, **Alpha API `NeedType`은 위 5종으로 시작하고 `similarity`는 Persona real contract(+embedding) 이후로 미룬다.** Alpha는 mock persona라 similarity를 지금 넣으면 순환이 된다(spec §4·§5 when-needed). 포함 결정이 뒤집히면 §3.1·§4.1·§4.2·§8.1·Phase 6/7의 need 5종을 6종으로 일괄 변경한다.

**`UserStanceRef`** (내부 normalized, for/against용) — `axis: str` · `dir: Stance` · `text: str \| None = None` · **`confidence: float \| None = None`**(forward-compat: 보수적 Alpha의 결정론 파싱에선 `None`, Phase 8 free-form LLM normalize가 채움). API는 `user_stance_ref: str`로 받지만 **pipeline 진입 전 request normalizer**(별도 입력 정규화 단계, linker와 분리 — linker는 topic→QID 책임만)가 이 구조로 normalize한다. stance 분류(§4.2)·stance 지표(spec §8.5)·테스트는 모두 이 normalized 구조를 기준으로 하므로 문자열 파싱 ambiguity가 pipeline 안으로 새지 않는다.

> **`UserStanceRef.confidence` ≠ `AgentTopicEdge.stance_confidence`.** 전자는 **질의측** stance 파싱 신뢰도(Alpha=`None`), 후자는 **agent측** observed_stance 추출 신뢰도(= directions §9.3 extraction_confidence, edge/Memory 제공). 이름이 비슷하나 소유·의미가 다르다 — 혼동 금지.

**Alpha 입력 문법 (보수적 — free-form은 Phase 8 LLM normalize로).** Alpha의 `user_stance_ref` 문자열은 작게 고정된 semi-structured 문법만 받는다:

```
axis=<text>; dir=<for|against|neutral>; text=<optional text>
```

파싱 규칙(Phase 1 normalizer 테스트가 검증):
- `axis`·`dir` **필수**, `text` optional.
- **unknown key → invalid**, `dir` 값이 `Stance` enum 밖 → invalid.
- need=for/against인데 parse 실패(필수 키 누락·invalid) → **`invalid_need` 422**.
- **need=for/against인데 `dir=neutral` → `invalid_need`**. for/against는 user stance 기준 **상대 need**(§4.2 — same/opposite)라 방향이 필요한데 `neutral`은 same/opposite를 정의할 수 없다(축만 있고 방향 없음). 문법상 `dir=neutral`은 유효하나 for/against need에서만 거부(depth/experience/coverage는 `dir` 무관·ignore).
- need=depth/experience/coverage에서 `user_stance_ref`가 와도 **reject하지 않고 ignore** — raw는 `NormalizedQuery`로 넘기지 않고(거기선 사라짐, §3.1 `NormalizedQuery` 정의) **원본 `Query`에 그대로 남아 decision-log(§4.3 `user_stance_ref_raw`)로 기록**된다(log-only, 기록 시점은 Phase 4). 클라이언트가 공통 payload를 보낼 수 있으므로 불필요한 stance에 422를 내지 않는다(API를 까다롭게 만들지 않음).

(`NormalizedQuery`는 raw `Query`를 normalize한 결과 — `topic_text`/`need_type`/`lang`/`limit`/`context: dict \| None`(eligibility 호출 컨텍스트, Gate로 전달) + `user_stance: UserStanceRef \| None`.)

**`EntityCandidate`** (linker 내부, 모듈① candidate generation의 정규화 타입) — search-only이므로 `search_candidates`(→`EntitySummary`) 히트를 **하나의 후보 타입으로 래핑**해 linker·LLM rerank 입력을 provider 투영과 분리한다: `qid: str` · `label: str` · `description: str\|None` · `summary: EntitySummary\|None`(rerank가 읽을 `importance`/`pageview`류 full 투영 보존). `label`/`description`은 top-level로 승격한다. 이 타입은 linker 안에서만 살고 pipeline 밖으로는 최종 QID만 나간다. (search∪suggest merge를 기록하던 `sources`/`suggestion` 필드는 폐기 — grounding이 suggest를 recall에 쓰지 않으므로 dead; D4.)

**`AgentTopicEdge`** (contract v0; Alpha는 local/eval fixture가 이 모델을 채움, spec §2.4·§7.2) — 모든 필드에 `source_owner`를 단다:

| 필드 | 타입 | 의미 | source_owner |
|---|---|---|---|
| `agent_id` | `str` | agent 식별자. **memory는 `owner_id`만 제공**; `agent_id`는 edge assembly 단계에서 bourbon-api `personal_agent_id(owner_id)`로 파생 | bourbon-api / derived |
| `anchor_id` | `str` | = Wikidata QID (spec §2.6) | memory |
| `maturity` | `float` | topic_knowledge_maturity (게이트 임계의 1차 신호) | memory |
| `evidence_strength` | `float` | 근거의 양/질 | memory |
| `freshness` | `float` | 최신성(=decay, hard cutoff 아님) | memory |
| `experience_source_type` | `ExperienceSourceType \| None` | 경험 근거의 출처 종류(`firsthand`/`secondhand`). `None`=직접 경험 근거 없음(추상 지식 edge). experience need가 depth와 갈라지는 1차 신호(directions §2.3 episode provenance·§9.1 `source_type`) | memory |
| `experience_specificity` | `float \| None` | 경험 근거의 구체성(episode specificity, directions §9.1). experience ordering 2차 키. experience 외 need는 미사용. **불변식(validator): `experience_source_type is None`이면 `experience_specificity`도 `None`**(경험 근거가 없는데 구체성만 있을 수 없음) | memory |
| `observed_stance` | `Stance \| None` | 관측된 입장 (축 위에서) | memory |
| `stance_axis` | `str \| None` | 입장이 놓인 축 라벨(for/against 판정 기준) | memory |
| `stance_summary` | `str \| None` | 입장 요약 텍스트 | memory |
| `stance_confidence` | `float \| None` | `observed_stance`의 추출/추정 신뢰도(= directions §9.3 `extraction_confidence`). §4.2 for/against filter guard `≥ τ`의 입력 | memory |
| `evidence_refs` | `list[str]` | conversation 원문 ref (Alpha 후보경로 미사용) | memory |
| ~~`routing_target`~~ | — | **계약에서 제거**: recommendation은 `agent_id`만 반환하고 dispatch는 bourbon-api가 런타임 해석. Current code still carries routing_target on AgentTopicEdge / RecommendationItem; remove in the implementation pass. | removed |
| `discoverable` | `bool` | edge 수준 노출 가능 여부 | privacy |
| `source_owner` | `dict[str,SourceOwner]` | 필드별 소유 맵(위 열을 코드로). *Current code source_owner map still reflects pre-removal fields (`agent_id=MEMORY`, `routing_target=OWNER`); update in implementation pass.* | — |

**`PersonaPrior`** (contract v0; Alpha는 local/eval fixture가 이 모델을 채움, spec §2.4) — `agent_id: str` · `prior_stance: Stance \| None` · `stable_traits: list[str]` · `expertise_claims: list[str]`(주장된 QID/topic). **prior는 maturity를 못 채운다**(hollow guard, spec §10): ranking에서 동일 band 내 보조 신호로만.

**`Eligibility`** (contract v0; Alpha는 local/eval fixture가 이 모델을 채움, spec §2.4) — `agent_id: str` · `discoverable: bool` · `reason: str \| None`. (Alpha는 `discoverable`만 active; `privacy_clearance`/`safety_verdict`는 Open Beta 이전 활성화 시 추가, directions §11.)

**`Candidate`** (내부, 모듈 ②→④ 통과 객체) — `edge: AgentTopicEdge` · `via: AnchorVia` (+`via_qid: str\|None` 이웃확장 출처) · `persona: PersonaPrior \| None` · `eligibility: Eligibility` · `features: dict[str,float]`(ordering 입력 **raw 연속값**, §4.2 — band는 cutoff로 derive) · `ordering_keys: list[str]`(이 need의 lexicographic 정렬 키) · `stance_axis/stance_dir` · `drop_reason: str \| None`(게이트/필터 탈락 사유, decision-log용). **scalar `score` 없음** — Alpha ranking은 ordering contract(§4.2)라 가중합 점수를 만들지 않는다.

**`Query` / `NormalizedQuery` / `Recommendation`** — 세 단계의 입출력 경계를 분리한다(⓪ normalizer 도입의 귀결, §4):

- **`Query`** = API request와 1:1(`RecommendRequest`). raw `user_stance_ref: str | None` 포함, `ApiModel`(extra=forbid). §4.1.
- **`NormalizedQuery`** = pipeline 내부 입력. `topic_text` · `lang` · `need_type` · `limit` · `context` + **`user_stance: UserStanceRef | None`**(raw 문자열은 여기서 사라지고 `{axis,dir,text}`로 normalize됨). ⓪ request normalizer가 `Query`→`NormalizedQuery`로 변환하며, 이후 linker/ranker/serving은 모두 이 구조만 본다.
- **`Recommendation`** = API response와 1:1(`RecommendResponse`). §4.1.

### 3.2 memory-api 신호 → Discovery 소비 맵 (무엇을 받아 무엇을 계산/사용하는가)

Alpha에서 **memory-api로부터 real로 받는 값은 anchor/entity 신호뿐**이다(edge/persona/eligibility는 Alpha엔 mock — §3.1 contract; future-real 출처는 §11). 아래는 public `/knowledge` 라우트가 주는 각 값의 의미·범위와, Discovery가 그걸로 **무엇을 계산해 어디에 쓰는지**다. **핵심 원칙: anchor에 붙은 값은 anchor disambiguation/확장에만 쓰고, agent expertise·추천 품질 신호로 해석하지 않는다**(spec §2.6).

| memory-api 값 (출처 라우트) | 의미 | 값/범위 | Discovery가 계산/사용 | Alpha |
|---|---|---|---|---|
| `qid` (전 라우트) | Wikidata 식별자 | `"Q…"` 문자열 | **`anchor_id`로 그대로 사용** = edge join key(§3.1) | ✓ |
| `label`·`description` | 표시/검색 텍스트 | str | LLM rerank 입력 + 응답 `anchor.label` 표시 | ✓ |
| `importance` (Summary/detail) | pageview·pagerank·sitelink 혼합 notability(산식 spec §2.6) | ~`0.0–1.0` 정규화 | **disambiguation prior**(후보 정렬·rerank 보조)·sparse fallback 정렬만 | ✓(제한) |
| `pageview`·`pagerank`·`sitelink_count` | popularity/centrality raw | int/float ≥0 | `importance`의 구성요소; 단독으론 보조 정렬만 | ✓(제한) |
| `aliases`·`labels`·`sitelinks` | 다국어·이표기 | list/dict | linker candidate **alias recall** 보강(한국어) | 부분 |
| `instance_of`·`subclass_of`·`categories`·`abstract` | 분류/설명 | list/str | rerank 문맥; (future) axis hint | 부분 |
| `linked_qids` (detail) | associative out-edges | list[QID] | sparse expansion 후보 풀 | ✓ |
| `occupations` (detail) | P106 직업(people-only) | list[QID] | **Alpha 미사용**; future positioning/axis seed(§11) | ✗ |
| `connections{broader/narrower/links_out/links_in}` | typed 이웃 | `EntitySummary[]` | **이웃 anchor 확장**(sparse fallback) → neighbor QID 풀(§4②) | ✓ |
| `Page[T]{items,limit,truncated}` | list transport envelope | — | provider가 `.items` 언랩 후 버림(도메인 비전파, §3) | ✓ |

**우리가 추가로 계산하는 값**(memory-api가 주지 않음):
- **per-candidate linker confidence** — `EntityCandidate`(§3.1) 위 산출(`0.0–1.0`); **Alpha는 symbolic label-match**(exact 1.0 / non-exact 0.55), LLM rerank는 Phase 8 → **grounding 채택 게이트**: top이 **유일 exact-label match**(confidence == 1.0) ∧ `margin ≥ LINKER_MARGIN_MIN(0.15)`, `margin`=후보 1개 `confidence`·2개+ `top1−top2`(§4①). non-exact top·exact 동음이의 tie → 미달 → `grounding_failed` 422.
- **`AnchorVia`**(`direct`/`neighbor`) + `via_qid` — 후보가 resolved QID 직접인지 이웃 확장 출처인지(§3.1 Candidate; gate `on_topic` 판정 입력).

edge 신호(`maturity`/`evidence_strength`/`freshness`/`observed_stance`/`stance_confidence` 등)는 **Alpha에선 memory-api가 아니라 mock fixture**가 채운다 — 의미·`source_owner`는 §3.1 표, ranking에서의 소비는 §4.2, future-real 출처 후보(personal KG salience/reference_kind 포함)는 §11에 있다.

## 4. 파이프라인 (모듈 1→6)

`discovery/pipeline.py`가 spec §2.3 경로를 그대로 오케스트레이션한다. 순수 함수/작은 클래스로, 각 모듈은 자기 디렉토리에서 단독 테스트 가능. **pipeline은 provider가 mock인지 real인지 모른다** — Protocol만 보고 동작하며, 주입은 호출자(배포=`api/depends`, 로컬/eval=CLI·harness)가 결정한다.

```python
# discovery/pipeline.py  (스케치)
class RecommendationPipeline:
    def __init__(self, *, linker: Linker, retriever: Retriever, gate: Gate,
                 ranker: Ranker, log: DecisionLog) -> None: ...
    # provider들은 파이프라인이 아니라 각 collaborator(Linker/Retriever/Gate)에 주입된다 — 파이프라인은 이 5개만 조립

    async def recommend(self, query: Query) -> Recommendation:
        normalized = normalize_query(query)                                    # ⓪ request normalizer (str→UserStanceRef; InvalidNeedError 가능)
        grounding = await self._linker.ground(normalized.topic_text)           # ① topic→QID only (GroundingFailedError propagates)
        hits = await self._retriever.retrieve(grounding.qid)                   # ② edges + sparse 이웃확장
        gated = await self._gate.screen(hits, context=normalized.context)      # ③ eligibility + persona → Candidate 완성
        ranked, filter_dropped = self._ranker.rank(gated.survivors, normalized)  # ④ ordering(§4.2) + stance filter — sync, no provider I/O
        recommendation = serve(ranked, grounding=grounding, query=normalized)  # ⑤ payload (top-limit) + silence
        record = self._log.record(...)                                         # ⑥ decision-log: full ranking + merged drops(gate+filter)
        recommendation.decision_log_id = record.log_id                         # log id를 응답에 stamp
        return recommendation
```

- **⓪  Request normalizer**: raw `Query`(API `RecommendRequest`) → `NormalizedQuery`. `user_stance_ref: str`를 `UserStanceRef{axis,dir,text}`로 파싱·정규화(§3.1). **linker와 분리** — 입력 정규화는 여기서, topic→QID는 ①에서. 문자열 파싱 ambiguity가 pipeline 안으로 안 샌다.
- **①  Linker (2-tier; symbolic 우선 + gate 실패 시 rerank fallback[8A], spec §4.1)**: candidate generation = `search_candidates`(`/knowledge/entities` full-text)만 — qid로 dedupe해 `EntityCandidate`(§3.1)로 정규화 → **symbolic label-match confidence**(exact label 1.0 / non-exact 0.55)로 후보에 confidence를 매겨 최종 QID를 고른다. `suggest`는 autocomplete 전용이라 grounding recall에서 제외한다(D2; 실측 recall 기여 0). **symbolic이 결정적 우선 경로다 — 채택 게이트가 실패하면 주입된 reranker가 있을 때만 LLM rerank fallback으로 넘어간다**(Phase 8A serving path에 주입됨; eval/offline은 `reranker=None`이라 미주입 → terminal. 아래 rerank 경계 참조; 전면 listwise 대체 원안은 폐기(2026-07-08) — 재정의된 8B는 폴백 사다리 `symbolic→rerank②→expansion③→substitution④→silence`로 구현됨(rerank②는 Phase 8A serving에 라이브; expansion③·substitution④는 opt-in shipped·default OFF로 dormant)). **linker-side `expand_connections`는 쓰지 않는다** — 이웃 anchor 확장은 linker가 아니라 Retrieval ②의 sparse expansion 책임이다. **topic→QID 책임만 진다**(stance 파싱 아님). 단독 QID 생성 금지. **채택 게이트**: top이 **유일 exact-label match**(confidence == exact 1.0) ∧ `margin ≥ LINKER_MARGIN_MIN`이라야 그 QID를 채택; non-exact top이나 exact 동음이의 tie는 채택 금지, 미달이면 `grounding_failed`(§4.1). 이 exact-required 가드가 단일 non-exact 0.55가 single-candidate margin으로 통과하던 구멍을 닫는다. **margin은 후보셋 기준 Discovery 자체 정책이다**(Discovery linker는 후보별 symbolic confidence를 갖는다): **후보 1개 → `margin = confidence`**, **후보 2개 이상 → `margin = top1_confidence − top2_confidence`**. single 후보에 `1.0` 특례를 두지 않는다 — 그러면 단일 후보가 margin gate를 우회해 homonym over-grounding을 낳는다. `LINKER_MARGIN_MIN`(채택 여유 = ambiguity margin; 후보 2개+에선 runner-up 대비 우위, 1개에선 confidence 자체)은 exact 동음이의 tie와 exact-vs-non-exact 분리에 여전히 실동 gate다. (`LINKER_CONF_MIN`은 exact-required로 무의미해져 폐기 — exact는 항상 1.0이므로.) (**memory-api `Grounder`도 현재 main(`d66b2c1`) 기준 같은 보수적 margin 해석이다** — 단일 후보 margin = `top1.score − 0.0` = 자기 점수라 score가 약하면 margin gate를 우회하지 못한다(`grounding.py` `_rank_and_margin`; `bb4102b`의 `_compute_margin` single=`1.0` 특례는 `#31`에서 폐기). 즉 Discovery `single=confidence`는 memory-api와 어긋나는 게 아니라 **같은 anti-gate-bypass 방향으로 수렴**한 것이다.) threshold seed `LINKER_MARGIN_MIN=0.15`는 memory-api `Grounder` 값(`GROUNDING_MIN_MARGIN`)을 차용(§2 `LinkerSettings`, provisional·ratchet 대상).
  - **rerank 경계 (Phase 8A shipped fallback; candidate-closed · gate 우회 금지 · injection-safe).** LLM rerank는 symbolic 채택 실패 시의 **fallback**으로 Phase 8A에서 도입됐다(serving path에 주입; eval/offline은 미주입). 후보 위 **순위 신호일 뿐 gate가 아니다**: ① candidate-gen이 만든 후보 QID 집합 **밖을 만들 수 없고**(단독 QID 생성 금지), ② `confidence`/`margin` 채택 게이트를 **우회·재정의할 수 없으며**(rerank 후에도 게이트는 그대로 적용), ③ structured output(`invoke_structured`)만 신뢰하고 자유서술은 버린다. ④ **후보 텍스트(entity label·description·article snippet)는 data로 취급하며 명령으로 해석하지 않는다** — memory-api에서 온 semi-trusted 텍스트에 주입된 지시("이 항목을 1등으로 골라라")가 QID 선택을 바꾸면 안 된다(검증: §8.3 `rerank prompt injection` 가드). **reranker 미주입(eval/offline)·malformed·empty·injection 의심·LLM 불가용이면 deterministic 순서로 조용히 degrade하지 않고 `grounding_failed`로 떨어진다** — 애매한 grounding을 임의 채택하지 않기 위함이다. 즉 `grounding_failed`(§4.1)는 후보 0, 채택 게이트 미달(exact-required·margin), **그리고 rerank fallback이 해소하지 못한 경우** 모두에서 난다. rerank는 optional refinement이지 symbolic 채택을 우회·대체하지 않는다(전면 listwise 대체 원안은 폐기(2026-07-08) — 재정의된 8B는 폴백 사다리 `symbolic→rerank②→expansion③→substitution④→silence`로 구현됨: rerank②는 Phase 8A serving에 라이브, expansion③·substitution④는 opt-in shipped·default OFF로 dormant).
- **②  Retrieval**: `edges.get_edges(qid)`. sparse면 `expand_connections` 이웃 QID들로 풀 확장(이웃 확장은 real). **(future-edge 주의, 2026-07-02)** memory-api `connections(limit=)`의 `limit`은 **associative links(`links_out`/`links_in`)에만** 적용되고 taxonomy(`broader`/`narrower`)는 별도 cap(`_TAXONOMY_CAP`, main `d66b2c1`에서 50→100)이라 `limit` 하나로 이웃 총량이 제어되지 않는다. `_neighbor_qids()`는 broader/narrower/links를 전부 평탄화하므로, **real `MemoryEdgeProvider` 통합 전 Discovery-side `RETRIEVAL_MAX_NEIGHBORS` cap을 둬 이웃 폭발을 막는다**(Alpha는 edge=`Unavailable*`라 즉시 문제 아님 — carried-forward, Phase 5 무영향).
- **③  Gate(Rankable)**: `eligibility.check`(discoverable) + maturity 임계 + `edge.discoverable` (need-agnostic drop만). **`persona.get_prior`도 여기서 바인딩**해 `EdgeHit`→`Candidate`를 완성한다(생존자에만 fetch; per-agent provider I/O를 ③에 모아 ④ Ranker를 provider-I/O 없는 deterministic stage로 유지). safety/privacy는 Alpha inactive(directions §11).
- **④  Ranking**: need별 ordering(§4.2 — filter + lexicographic keys, scalar score 없음) + stance 분류(for/against). **provider I/O 없는 deterministic ranking stage** — `Candidate.features`/`ordering_keys`/`stance_axis`/`stance_dir`/`drop_reason`을 in-place annotate하므로 referentially pure는 아니나 provider I/O·비결정성은 없다. persona는 ③에서 이미 바인딩됨(정렬에선 within-band late tie-break 슬롯이나 **Alpha no-op**, §4.2). persona prior는 maturity를 못 채운다(hollow guard, spec §10).
- **⑤  Serving**: 후보(`agent_id`)·이유·evidence_refs payload. push silence는 Alpha에서 threshold stub(policy는 Open Beta). (`routing_target`은 계약에서 제거 — dispatch는 bourbon-api가 런타임 해석.)
- **⑥  Decision-log**: 입력·중간값·생존/탈락 이유를 day-one 기록(§4.3). Open Beta OPE replay harness로 승계(spec §7.5·§8.9).

### 4.1 API contract — `POST /recommend`

`ApiModel`(extra=forbid). 요청/응답 필드를 못 박아 구현 흔들림을 줄인다.

**`RecommendRequest`**:

| 필드 | 타입 | 필수 | 기본 | 의미 |
|---|---|---|---|---|
| `topic_text` | `str` | ✓ | — | grounding할 주제 텍스트 |
| `need_type` | `NeedType` | ✓ | — | depth/experience/for/against/coverage |
| `user_stance_ref` | `str \| None` |  | `null` | for/against의 기준 입장. semi-structured 문법 `axis=…; dir=…; text=…`(§3.1). need=for/against에서 parse 실패 시 `invalid_need`; depth/experience/coverage에선 와도 ignore+log-only(§3.1). **request normalizer가 `UserStanceRef`로 normalize 후 pipeline 전달** |
| `lang` | `str \| None` |  | `"ko"` | linker 언어 힌트 |
| `limit` | `int` |  | `10` | 반환 후보 상한(1–50) |
| `context` | `Mapping[str,Any] \| None` |  | `null` | eligibility용 호출 맥락 |

**`RecommendResponse`**:

```jsonc
{
  "anchor": { "qid": "Q11660", "label": "인공지능" },     // grounding 결과
  "need_type": "depth",
  "recommendations": [
    { "agent_id": "a_07", "rank": 1,                       // Alpha는 scalar score 없이 rank만(§4.2 ordering contract)
      "stance": { "axis": "...", "dir": "for" },           // for/against need일 때
      "reasons": ["maturity 0.9·evidence 0.8", "..."],     // evidence_ref에 묶임(§8.5 reason 지표)
      "evidence_refs": ["msg:..."] }
  ],
  "silence": { "silent": false, "reason": null },          // push silence 판정(Alpha=대개 false)
  "decision_log_id": "dl_..."                               // §4.3 로그와 연결
}
```

> **`routing_target` 제거(target 계약).** 응답은 `agent_id` 중심이며 `routing_target`은 담지 않는다 — dispatch는 bourbon-api가 `agent_id`로 런타임 해석한다(agent에 endpoint 필드 없음). Current code still carries routing_target on AgentTopicEdge / RecommendationItem; remove in the implementation pass.

**error code** (`AppError` 서브클래스, template `api/structs/errors.py` 패턴):

| code | status | 발생 |
|---|---|---|
| `grounding_failed` | 422 | **anchor grounding 후보 0**, 채택 게이트 미달(top이 exact-label match 아님 ∨ `margin < LINKER_MARGIN_MIN` — 예: exact 동음이의 tie), **또는 rerank fallback 미해소**(§4 ①) — topic→QID 자체 실패 |
| `invalid_need` | 422 | need=for/against인데 `user_stance_ref` 없음 (pydantic+model_validator) |
| `upstream_unavailable` | 503 | memory-api anchor 호출 실패, **또는 edge/eligibility real 미통합**(배포 앱의 `Unavailable{Edge,Eligibility}Provider`, §3). persona 부재는 503 아님(`NullPersonaProvider`→`None`) |

**두 종류의 "0"을 구분한다(오독 방지):**
- **anchor grounding 후보 0** (topic을 QID로 못 풀음) → `grounding_failed` **422 에러**. grounding은 모든 후속 단계의 전제라, 실패하면 추천 자체가 성립 안 함.
- **agent recommendation 후보 0** (QID는 풀렸으나 edge 없음/전부 게이트 탈락) → **에러 아님**. `recommendations: []` + `silence.silent=true`로 **200** 반환(침묵도 정상 결정, decision-log에 기록).

### 4.2 Alpha ranking — ordering contract (formula 아님)

수식·학습 weight를 데이터 전에 단정하지 않는다(spec §8.6 ratchet). **Alpha 산출물은 가중합 score가 아니라 ordering contract**다: `Gate → NeedFilter → NeedOrdering(lexicographic) → TieBreak → ServingSuppression`. 각 need를 **filter + ordering key 리스트**로 고정하고 점수 스칼라는 만들지 않는다(0.55·0.30 같은 계수는 데이터 전엔 근거 없음 + feature 분포 미정규화 상태에선 가중합이 오해를 만든다). 입력은 edge 신호(`maturity`/`evidence_strength`/`freshness`/`observed_stance`/`stance_confidence`)뿐 — **anchor `importance`/pageview류는 안 쓴다**(spec §2.6: agent 추천 신호 아님).

> **불변식 — aggregate scalar objective 금지 (≠ atomic feature 금지).** *Aggregate scalar metrics/objectives may be used for offline measurement, audit, or regression detection; they must not become serving-time optimization objectives. Atomic typed features may be used at serving time only as explicitly enumerated gates or lexicographic keys — never combined into a learned/weighted serving score.* **aggregate 스칼라**(nDCG·calibration·KL coverage divergence·LLM judge score 같은 *합성/집계* 지표)는 **오프라인 측정·감사·regression 탐지 전용**이고 serving-time 최적화 목적함수가 되지 않는다. 반면 **atomic typed feature**(`maturity`/`evidence_strength`/`freshness`/`stance_confidence`, linker `confidence`/`margin`)는 serving에서 **명시적으로 열거된 gate(§4① 채택 게이트·Gate(Rankable)) 또는 lexicographic ordering key(아래 표)로만** 쓰이며 — **가중합·학습된 단일 score로 합쳐지지 않는다.** 즉 핵심은 'scalar 금지'가 아니라 **'aggregate/weighted serving score·objective 금지'**다(개별 feature를 gate/lexicographic key로 쓰는 건 허용 — 그게 이 §4.2 계약 자체다). calibration·coverage·OPE·judge 지표가 앞으로 유입돼도 전부 이 경계(측정 OK / 서빙 score·objective ❌) 아래 둔다(§8.6 ratchet·§11 future 후보가 모두 하위 적용).
>
> **이 단계(④ agent ordering)엔 LLM이 개입하지 않는다** — 순위는 아래 lexicographic ordering key로만 결정된다. LLM listwise rerank는 **①linker(topic→QID 후보 선택)에만** 존재하며 agent 순위를 만들지 않는다(§4①). 즉 "scalar score 금지"는 *LLM이 점수를 못 만들게 막는다*가 아니라 **이 단계에 LLM/scalar optimization이 아예 없음**으로 보장된다(둘을 한 절에 합치면 경계가 흐려지므로 §4①과 분리해 서술).

**Gate (Rankable)** — 통과해야 ordering 진입: `on_topic ∧ maturity ≥ MATURITY_MIN ∧ eligibility.discoverable ∧ edge.discoverable ∧ safety_eligible`. `on_topic` = `edge.anchor_id == resolved_qid` **또는** accepted neighbor expansion via(§4 ②). safety/privacy는 penalty가 아니라 **gate**다 — score에서 trade-off하지 않는다(directions §11). **Alpha는 `safety_eligible`=true로 간주**한다(필드·게이트 활성화는 Open Beta 이전); `eligibility`는 `discoverable`만 active(§3.1).

**Need별 filter + ordering keys** (전부 `desc`, 말단 `agent_id asc`로 결정론):

| need | filter | ordering keys |
|---|---|---|
| `depth` | — | `maturity_band` → `evidence_strength` → `freshness` → `agent_id` |
| `experience` | — | `experience_source_rank` → `experience_specificity_rank` → `evidence_strength` → `freshness` → `maturity_band` → `agent_id` |
| `for` | `same_axis ∧ observed_stance = user_stance.dir ∧ stance_confidence ≥ τ` | `maturity_band` → `evidence_strength` → `freshness` → `stance_confidence` → `agent_id` |
| `against` | `same_axis ∧ observed_stance = opposite(user_stance.dir) ∧ stance_confidence ≥ τ` | `maturity_band` → `evidence_strength` → `freshness` → `stance_confidence` → `agent_id` |
| `coverage` | — | `edge.anchor_id`로 group(core=`via==DIRECT`의 anchor_id, direct 없으면 anchor_id asc부터) → **round-robin**(pass마다 group당 1명) → (group 내) `maturity_band` → `evidence_strength` → `freshness` → `agent_id` |

- **for/against = expertise-primary.** wrong-axis/wrong-direction은 낮은 점수가 아니라 **후보집합 밖**(hard filter — orthogonal로 안 샘, spec §8.5). `stance_confidence`는 ① filter reliability guard(`≥ τ`) ② decision-log diagnostic ③ **late tie-break**의 3역할뿐 — extraction/측정 confidence가 전문성을 못 이기게 **1순위로 두지 않는다**. 값은 **edge(Memory) 제공**(§3.1 `stance_confidence` = directions §9.3 extraction_confidence)이고, for/against **방향 판정**(observed_stance vs `user_stance`)은 Discovery가 request-time에 derive한다(directions §9.3·§4.4) — edge가 need를 태깅하지 않는다.
- **for/against are relative needs, not absolute stance labels (오독 금지).** `need_type`은 목표 stance 그 자체가 아니라 **user stance 기준으로 같은 편(for)/반대 편(against)을 찾는 상대 관계**다(directions §4.4 표). 따라서 필요 방향은 반드시 `user_stance.dir`에서 derive한다: **`need=for → required_dir = user_stance.dir`; `need=against → required_dir = opposite(user_stance.dir)`** (`opposite`: for↔against 만 정의). **`user_stance.dir=neutral`은 for/against에 invalid** — same/opposite를 정의할 수 없으므로(축만 있고 방향 없음) normalizer가 `invalid_need`로 거부한다(§3.1). **`NeedType.FOR → Stance.FOR` 같은 절대 매핑을 두면 안 된다** — 예: user가 `탈원전 dir=for`이면 `need=against`는 **탈원전 반대** agent를 찾는다. **필터 판정 순서(단일 drop reason, decision-log)**: axis 비교는 `casefold().strip()` equality. ⑴ `stance_axis` 또는 `observed_stance`가 `None` → `off_axis`; ⑵ axis 불일치 → `off_axis`; ⑶ axis 일치 + `observed_stance != required_dir` → `wrong_stance`; ⑷ axis+required_dir 일치 + (`stance_confidence`가 `None` 이거나 `< τ`) → `low_stance_confidence`(**`stance_confidence is None`은 low로 처리**).
- **experience = direct-experience-primary.** experience가 depth의 변형(같은 신호 재정렬)으로 무너지지 않게, **직접 경험 근거를 1·2차 키로 앞세운다**: `experience_source_rank`(직접 경험 출처 종류) → `experience_specificity_rank`(경험 구체성, `None`→0.0 coalesce — 아래 규칙) → 그다음에야 `evidence_strength`/`freshness`/`maturity_band`. 이로써 "직접 겪은 agent"가 "근거만 많은 expert"를 이긴다(directions §2.3 "추상 지식이 아니라 직접 겪은 근거"). `experience_source_type=None`(추상 지식 edge)은 rank 0이라 자연히 뒤로 밀린다(별도 필터 없이 ordering으로 표현). depth는 반대로 `maturity_band`를 1차 키로 두므로 두 need가 같은 edge 집합에서도 다른 순서를 낸다.
- **coverage = round-robin dedupe.** MMR/DPP는 Open Beta(spec §4.2). marginal-diversity는 선택순서 의존이라 정적 score가 아님. **group key = `edge.anchor_id`**(edge가 실제 붙은 QID) — `via_qid`는 R3상 neighbor hit들이 전부 원 anchor로 동일해서 facet 구분이 안 되므로 group key가 될 수 없다. **core group**(resolved anchor)은 **`via==DIRECT`인 후보들의 `edge.anchor_id`로 추론**한다(Ranker 입력에 `anchor_qid`를 따로 넘기지 않음); direct 후보가 하나도 없으면 그냥 `anchor_id asc`로 group 순서를 시작한다. group 순서 = core 먼저, 그다음 `anchor_id asc`. round-robin = 각 pass에서 group당 best 1명씩(group 내부는 depth-like ordering). 로그(§4.3)의 `ordering_keys`엔 이 group 단계가 `coverage_group`이라는 1차 키 이름으로 기록된다(그다음 `maturity_band`→`evidence_strength`→`freshness`→`agent_id`).
- **순서형 키는 명시 rank map으로 비교하고 `None`은 coalesce한다 (StrEnum 문자열 정렬 금지 · None/float 혼합 정렬 금지).** `maturity_band`·`experience_source_rank`는 `StrEnum` 값을 문자열로 sort하면 안 된다 — `"high"/"medium"/"low"`를 문자열 desc로 정렬하면 `medium > low > high`가 되어 **high가 꼴찌로 밀린다**. ordering은 반드시 정수 rank로 비교: `MATURITY_BAND_RANK = {high:2, medium:1, low:0}`, `EXPERIENCE_SOURCE_RANK = {firsthand:2, secondhand:1, None:0}`(둘 다 `discovery/config.py`의 **frozen module 상수** — `MappingProxyType`, ordering *semantics*라 tunable `RankingSettings` 필드가 아니다; cutoff/τ 같은 임계만 settings). `experience_specificity`는 `float | None`이라 정렬 전 **coalesce**: `experience_specificity_rank = experience_specificity or 0.0`(`None`→0.0, 위 validator 불변식과 일관 — source_type 없으면 specificity도 없음). 파생 편의값 `has_experience_evidence := experience_source_type is not None`(= `EXPERIENCE_SOURCE_RANK ≥ 1`; **firsthand·secondhand 둘 다 포함** — "direct"는 firsthand만 뜻하므로 쓰지 않는다)도 여기서 나온다(별도 저장 필드 아님; firsthand만 구분하려면 `experience_source_rank == 2`).
- **lexicographic은 weight를 없애지만 임계는 여전히 파라미터다** — `maturity_band` cutoff는 band 안에서만 evidence가 compensate하므로 고-레버리지. ranking 임계 셋은 **`discovery/config.py`의 `RankingSettings`(provisional 상수, eval-ratchet 대상, spec §8.6)** 에 모은다. **Alpha seed(학습값 아님 · ratchet 대상)**: `MATURITY_MIN=0.45`, `STANCE_CONFIDENCE_MIN=0.60`(= `τ`, for/against guard), `MATURITY_BAND_CUTOFFS={high≥0.75, medium≥0.50, low<0.50}`. **`MATURITY_MIN(0.45) < medium(0.50)`은 의도**다 — gate는 "rankable 최소 자격"만 보고(그래서 low band 후보도 통과 가능), band는 통과한 후보를 정렬한다(gate ↔ ordering 책임 분리). 전부 Alpha 기본값일 뿐 학습값 아니며, decision-log raw feature로 Post-OB에서 재튜닝한다(§4.3).
- **gate floor = 단일 `MATURITY_MIN`** (need별 분리 안 함). gate는 "최소 후보 자격"만 판단하고 **need 차이는 ordering에서 표현**한다(gate/ranking 책임 분리) — need별 floor(directions `floor_need`)를 지금부터 두면 또 다른 임의 파라미터가 된다. *Alpha v0 uses a single `MATURITY_MIN`; need-specific floors are deferred until eval shows clear need-specific failure modes.* **전환 트리거**: depth가 false-pass인데 experience가 false-block이면 그때 `MATURITY_MIN` → `MATURITY_MIN_BY_NEED`(`dict[NeedType,float]`)로 분리(directions §10).
- ordering이 스칼라를 안 만드므로 **전역 tie-break = need ordering keys 자체**(말단 `agent_id`로 결정론 보장). persona prior는 동일 band 내 late 보조 슬롯(hollow guard)이나 — **Alpha에선 정렬 튜플에 넣지 않는다(no-op), 슬롯만 예약**한다(위치: `stance_confidence`가 있으면 그 뒤·`agent_id` 앞). `PersonaPrior`가 hollow prior라 지금 넣으면 실제 expertise evidence를 대체한다는 오해가 생기므로 활성화는 후속 phase. 각 신호는 raw로 decision-log `feature_breakdown`에 남긴다(§4.3). need 의미의 source of truth는 directions §5.

**Favorite / user-preference 신호 (Alpha: reserved — 소비 안 함).** 즐겨찾기는 **personalization 신호이지 expertise 근거가 아니다.** 따라서 `maturity`/`evidence_strength`/stance match 같은 핵심 feature보다 앞설 수 없고, **어떤 gate(topic/maturity/safety/discoverability)도 우회하지 못한다.** Alpha는 favorite을 **ranking score term으로 쓰지 않는다**(평가축이 흐려짐, §1 비범위). **Post-Open-Beta**에 승격하더라도 score 가산이 아니라 **bounded tie-break key**로만(ordering keys 말단 — 전문성 키 뒤·`agent_id` 앞의 late tie-break), 그것도 need별로 제한한다:

| need | favorite 사용 (Post-Open-Beta 승격 시) |
|---|---|
| `depth` / `experience` / `for` | bounded tie-break 가능 |
| `against` / `orthogonal` | **사용 안 함(0)** — 익숙한 관점에서 벗어나는 게 objective인데 favorite은 유저와 stance가 정렬될 확률이 높아 objective를 훼손("줄인다"가 아니라 끈다) |
| `coverage` | 기본 미사용, diversity 훼손 없음이 입증될 때만 검토 |
| `similarity` | Persona real 이후 별도 논의(§3.1) |

**negative preference가 positive favorite보다 먼저다.** `hidden`/`muted`는 유저의 명시적 억제 intent라 부작용이 적어 serving **hard filter**에 가깝고, `dismissed_recently`는 Push fatigue/silence 보조 신호로 유용하다. 이들은 플랫폼 safety/privacy gate가 **아니라** 유저 개인의 **preference-based serving suppression**(maturity/safety/privacy 3종과 별개 축 — 소스 directions §9.7, 게이트 직교성 directions §11)이며, **Open Beta 후보 항목**(bourbon-api 신호 존재 시)으로 positive favorite(Post-Open-Beta)보다 먼저 검토한다. 구현 우선순위: **do-not-show(hidden/muted) → reduce-repeat/fatigue(dismissed) → 그다음에야 positive favorite tie-break.**

> Favorite is a user-preference signal, not expertise evidence. It must never bypass topic, maturity, safety, or discoverability gates. In Alpha the **design** reserves a future `UserPreferenceProvider` integration point, but **no runtime Protocol or no-op provider is added**; favorite is **not** a ranking score term. **Post-Open-Beta** it may serve only as a bounded tie-break for `depth`, `experience`, and `for`; it is **disabled** for `against` and `orthogonal`. Negative preferences (`hidden`, `muted`, `dismissed_recently`) are safer serving signals — **Open Beta candidates** (if a `bourbon-api` signal exists), handled before any positive favorite boost.

### 4.3 Decision-log 최소 스키마

추천 1회 = 로그 1행(JSONL, `eval/output/` 또는 런타임 sink). Open Beta OPE replay의 입력이므로 **최소 필드를 지금 박는다**. 시간은 호출자가 주입(스크립트 `Date.now` 금지 규칙과 무관하게 런타임은 주입).

```jsonc
{
  "log_id": "dl_...", "ts": "2026-..Z", "contract_version": "edge@v0",
  "query": { "topic_text": "...", "need_type": "depth", "lang": "ko", "limit": 10,
             "user_stance_ref_raw": null,                                  // API 원문 문자열
             "user_stance_ref_normalized": null },                         // {axis,dir,text} or null (§3.1)
  "grounding": { "resolved_qid": "Q...", "label": "...", "method": "symbolic",   // Alpha=symbolic; LLM rerank는 Phase 8
                 "fallback_used": false, "considered": [{"qid":"Q..","confidence":0.9}] },
  "candidate_pool": [{ "agent_id": "...", "anchor_id": "Q...", "via": "direct|neighbor", "via_qid": null }],
  "dropped": [{ "agent_id": "...", "reason": "maturity|eligibility|discoverable|off_axis|wrong_stance|low_stance_confidence" }],
  "ranked": [{ "agent_id": "...", "rank": 1, "passed_gate": true,
               "need_filter": "same_axis_required_stance",                  // for/against만; depth/experience/coverage는 null
               "feature_breakdown": { "maturity": 0.78, "maturity_band": "high",   // raw 연속값 + derived band 병기 (high cutoff=0.75)
                                      "evidence_strength": 0.81, "freshness": 0.62,
                                      "stance_confidence": 0.69 },
                                      // ↑ 위는 for/against need 예시. need별로 raw feature가 다르다 — experience need면
                                      //   "experience_source_type":"firsthand","experience_source_rank":2,"experience_specificity":0.55 도 raw로 남긴다(§4.2)
               "ordering_keys": ["maturity_band","evidence_strength","freshness","stance_confidence","agent_id"],  // 이 need의 lexicographic 정렬 키(§4.2)
               "stance": { "axis": "...", "dir": "for" } }],
  "reasons": [{ "agent_id": "...", "text": "...", "evidence_refs": ["msg:..."] }],
  "serving": { "silent": false, "reason": null, "returned": 5 },
  "provider_versions": { "anchor": "memory-api@…", "edge": "mock@v0", "persona": "mock@v0", "eligibility": "mock@v0" },
                       // ↑ local/eval 예시. substrate별로 값이 다름: 배포=unavailable@v0(real 미통합), eval=mock@v0, 통합후=memory-api@… (§2.5·§8.10)
  "ope": { "propensity": null, "action_set": ["..."], "reward_proxy": null }   // Alpha 비움, Open Beta OPE 자리(spec §7.5)
}
```

Alpha ranking은 가중합 스칼라를 만들지 않으므로 **`score` 필드 대신 `ordering_keys` + raw `feature_breakdown`을 남긴다**(§4.2 ordering contract). raw 연속값(`maturity`)과 derived `maturity_band`를 **둘 다** 기록해야 Post-OB에서 LTR/threshold tuning/error analysis가 band cutoff·weight를 역으로 fit할 수 있다(band만 남기면 정보 손실). `provider_versions`로 mock→real 전환 전후 비교가 가능해진다(spec §8.10 substrate report). `ope` 블록은 Alpha에서 비우되 **존재**시켜, Open Beta에서 스키마 변경 없이 채운다.

## 5. LLM 통합 (memory-api `memory/llm/` 포팅 — proxy default)

> Alpha defaults to the OpenAI-compatible proxy path for deployment parity with memory-api/e3llm-api. The direct OpenAI/Gemini providers are ported as an **inactive provider layer** — the completion spine (`complete`/`complete_messages`) only, no tool-calling surface — so the provider spine is preserved for a later Vertex direct mode. Enabling that direct mode still requires a **structured direct adapter** (the direct providers' `complete()` takes no `response_format`; in memory-api structured output is proxy-only), which is **follow-up work, not Alpha**. `get_client()` returns the proxy client only; `LLM_MODE=direct` is rejected with an explicit error. **Direct mode is not part of Alpha serving acceptance.**

1. **structured-completion spine 포팅 (e3llm SDK 직접 의존 안 함).** memory-api `d66b2c1`은 e3llm 패키지를 import하지 않고 자체 OpenAI-compatible proxy client를 쓴다(coldbrew `agent/client.py` 패턴; `memory/llm/`에 `import e3llm` **0건** — 2026-07-02 재확인). Discovery는 `../bourbon-memory-api/memory/llm/`의 **structured-completion spine만** `discovery/llm/`로 포팅한다 — `complete`/`complete_messages` + `convert_schema`/structured 경로. **tool-calling 표면은 제외**(`ToolSpec`/`to_openai_tool`/`ToolCallingProvider`/`complete_with_tools`/`openai_tools_to_gemini`/`gemini_tool_config`/`openai_messages_to_gemini`/`_TOOL_CHOICE_MODE`·`GoogleProvider._config`의 `tools`/`tool_choice`): Discovery의 3개 LLM 사용처(linker rerank·stance·B2 judge)는 전부 structured-output이고 agentic loop가 없으며, 원형 `providers.py:18`의 `from memory.conversation.tools.spec import ToolSpec`는 Discovery에 미존재라 literal copy 자체가 불가하다. tool-calling이 실제로 필요해지면(다중 provider fan-out·근거부족 시 추가 retrieval·동적 explanation/judge lookup) **그때 별도 `tools.py`로** 추가하고 spine에 반쯤 남기지 않는다. 새 추상화는 설계하지 않는다(memory-api와 drift 방지). 런타임 LLM은 e3llm-api 프록시 서비스(k8s `LLM_PROXY_URL`)가 담당한다. **(2026-07-02 drift 메모)** main `d66b2c1`의 `memory/llm/`은 `config.py`·`structured.py` **불변**(env var·`convert_schema`/`parse_model_string`/`make_provider` 시그니처 안정)이나 `providers.py`/`proxy.py`에 `RetriesExhaustedError`/`LLMProxyRetriesExhausted` 래핑·`reasoning_effort`+`max_completion_tokens`·`_DEFAULT_MAX_TOKENS 4096→8192`·`tool_choice="none"` 특례가 추가됐다. Discovery LLM은 Phase 8까지 inactive라 지금 재조정 불요 — **Phase 8 전 선택 포팅 대상**은 retries-exhausted 계열·output budget/reasoning support뿐이고 **tool-calling surface는 계속 제외**한다(drift 방지 원칙 유지).
   ```
   discovery/llm/
     config.py      LLMSettings(EnvSettings) — LLM_PROXY_URL/MODEL/timeout/max_tokens (+ direct 필드: LLM_MODE/LLM_PROVIDER/LLM_MODEL/LLM_API_KEY[현재 미소비]; openai 직접 키는 env OPENAI_API_KEY를 make_provider가 읽음)
     providers.py   LLMProvider Protocol · _BaseLLMProvider(httpx + _request_with_retry) · OpenAIProvider(complete/_messages) · GoogleProvider(Vertex ADC; complete/_messages만, _config는 system/max_output_tokens로 단순화) · convert_schema · parse_model_string · make_provider · LLMResponse · Message   ← memory-api spine과 동일 유지 (tool-calling 표면 제외)
     proxy.py       LLMProxyClient(_BaseLLMProvider) — /v1/chat/completions, response_format json_schema   ← 기본 runtime client
     structured.py  pydantic_response_format(model, name) — convert_schema 검증 게이트(import 시점에 Gemini 변환 가능성 검증)
     wrapper.py     invoke_structured + get_client/set_client — provider 종류를 모름, LLMClient Protocol만 의존
   ```
2. **proxy default + 가드.**
   - 기본 runtime client = `LLMProxyClient.from_settings()`(proxy 경로). Gemini는 **별도 코드 경로 없이** `LLM_PROXY_MODEL=google/gemini-2.5-flash`로 모델명만 바꿔 통일한다(프록시가 OpenAI-compatible↔Gemini 변환을 책임).
   - direct OpenAI/Gemini provider는 **spine만 포팅하되 inactive** — `get_client()`는 proxy client만 반환하고 `LLM_MODE=direct`는 명시 에러로 막는다(기본 `LLM_MODE=proxy`). direct path는 structured `response_format`를 받지 않으므로(memory-api에서도 structured는 proxy 전용) 활성화하려면 **structured direct adapter**가 필요하고 이는 후속 작업이다.
   - **direct GoogleProvider는 Alpha serving acceptance path에 끼우지 않는다**(Vertex 직접 모드는 provider spine 보존으로 후속 가능성만 확보; call site 무변경 보장은 아님).
   - **LLM provider 선택은 rerank/stance/judge 호출 하부에서만** 일어난다 — agent ordering(§4.2)에는 절대 연결하지 않는다(provider 선택이 순위에 새면 scalar 불변식·ordering 계약 위반).
3. **dependency — 추가는 `google-genai` 하나.** memory-api는 OpenAI를 raw httpx로 부르므로(SDK 아님) `openai` 패키지가 **없다**. `httpx[http2]`는 이미 main deps에 존재. **추가할 것은 `google-genai`뿐**(GoogleProvider + `convert_schema` 스키마 변환 게이트용 — 후자는 Vertex 호출이 아니라 json_schema → Gemini subset 변환에 쓰임). API runtime이 proxy client(httpx)를 쓰므로 main `[project] dependencies`에 둔다(Dockerfile 무수정):
   ```toml
   [project]
   dependencies = [ # 한 줄만 추가 (httpx[http2]는 이미 있음; openai/e3llm 불필요)
     "google-genai>=2.9.0",   # memory-api와 동일 핀 (GoogleProvider + convert_schema)
   ]
   [dependency-groups]
   eval = ["…"]  # eval 전용 도구만 별도 group (judge·report 등 prod 불필요분)
   dev  = ["mypy", "pytest", "pytest-asyncio", "ruff", "…"]  # 기존 dev에 watchdog 등 유지
   ```
4. **wrapper (`discovery/llm/wrapper.py`) — provider-agnostic.** `LLMClient` Protocol(`async complete(system, user, *, response_format) -> LLMResponse`)만 의존하고 proxy/direct를 구분하지 않는다. memory-api 추출의 structured 패턴 그대로:
   ```python
   _client: LLMClient | None = None
   def get_client() -> LLMClient:
       global _client
       if _client is None: _client = make_client_from_settings()  # LLM_MODE=proxy → LLMProxyClient.from_settings(); LLM_MODE=direct → 명시 에러(Alpha 비활성, §5 가드)
       return _client
   def set_client(c: LLMClient | None) -> None:  # 테스트 주입/리셋
       global _client
       _client = c
   async def invoke_structured(*, system: str, user: str, schema: type[T],
                               name: str | None = None) -> T | None:
       resp = await get_client().complete(
           system, user, response_format=pydantic_response_format(schema, name or schema.__name__))
       raw = resp.content
       if not raw:
           return None
       try:
           return schema.model_validate_json(raw)
       except ValidationError as e:
           logger.warning("invoke_structured: malformed LLM output dropped (%s)", e)
           return None   # malformed=fatal 아님 → drop+warning (coldbrew 규칙)
   ```
   사용처는 linker rerank(`discovery/linker`), stance 분류(`discovery/ranking/stance.py`), B2 judge(`eval/judge`) **세 곳뿐**. LLM 의존을 이 wrapper 뒤에 가둬, 추후 client replace 시 영향 면적을 최소화한다. **drop 단위 주의(coldbrew 매핑)**: stance/judge는 **단건** 호출이라 malformed→`None`(graceful degrade). **linker rerank는 후보 리스트를 산출**하므로 item-level drop이 필요한데, `invoke_structured(schema: type[T])`는 단일 모델만 검증하므로 `list[...]`을 직접 넘기지 않는다 — **wrapper 모델로 받는다**: `schema=RerankResponse`(`RerankResponse(items: list[LenientRerankItem])`, item은 관대한 mirror 모델). 그 다음 호출부(linker)가 `items`를 돌며 strict 도메인 모델로 **item별 재검증해 malformed item만 drop+warning, 나머지 후보는 보존**한다(memory-api `extract.py`의 lenient mirror→strict 패턴; `list` 자체 검증이 필요하면 `TypeAdapter(list[T])` 사용). 즉 **wrapper-level은 항상 단건(`None` or `RerankResponse`)이고 item-level drop은 linker 호출부 책임** — rerank만 item drop, stance/judge는 call-level `None`.
5. **env + 테스트 격리.** 기본 `.env.example`은 **proxy 경로만** 채운다 — `LLM_PROXY_URL`(기본 `http://localhost:8081`, k8s dev=`http://e3llm-api/`)·`LLM_PROXY_MODEL`(`openai/gpt-4o-mini` | `google/gemini-2.5-flash`). direct provider env(`LLM_MODE=direct`·`LLM_PROVIDER`·`LLM_MODEL`·openai 직접은 `OPENAI_API_KEY`[make_provider가 읽는 실제 var; `LLM_API_KEY` 필드는 현재 미소비]·Vertex ADC `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION`)는 **"optional direct mode"로만 주석 문서화**한다. **테스트 격리**: `set_client(fake)`로 fake client 주입 + fixture teardown에서 `set_client(None)` 리셋(global singleton이 테스트 간 새지 않게 — flaky 방지). **direct provider 테스트는 contract만** — schema conversion(`convert_schema`), model string parse(`parse_model_string`), fake client injection, provider factory env validation(`make_provider`). direct GoogleProvider 실호출은 Alpha 회귀에 넣지 않는다.

## 6. 구현 단계 (순서·체크리스트)

> **이 Phase 0–9는 milestone이 아니라 Alpha를 만들기 위한 구현 순서다. Phase 9 green = eval/CI 골격 완성이고, user-facing Alpha 성립은 그 뒤 Phase 10(real edge, 2026-07-07 승격)까지다.** Open Beta / Post-Open-Beta 항목(Push mode, orthogonal 조건부, feedback logging, real Persona 통합, contribution/reputation, LTR/model-based ranking, OPE loop)은 이 문서의 **비범위**이며(real **edge** 통합은 예외로 Phase 10 = Alpha 범위로 승격), Alpha 산출물(provider contract, decision-log, eval harness)을 기반으로 **별도 build plan에서 확장**한다. milestone↔phase 관계: **Alpha = Phase 0–9 + Phase 10(real edge)** · Open Beta/Post-OB = 이 문서 밖 후속 build plan.

각 Phase는 독립 PR 단위. **acceptance**를 못 넘으면 다음으로 안 간다(CLAUDE.md 검증 우선).

- **Phase 0 — Scaffold 정렬**: ~~`module/`→`discovery/` 개명~~ **(현재 기준 완료)**. 남은 작업: echo 제거(`discovery/echo/`·`api/routers/echo/`·`cli/echo.py`·관련 test), **memory-api `memory/llm/` structured-completion spine 포팅**(`discovery/llm/`: config·providers·proxy·structured·wrapper; tool-calling 표면 제외, proxy default·direct=inactive, §5) + deps(`google-genai` 추가), `.env.example`에 `MEMORY_API_BASE_URL`/`LLM_PROXY_URL`/`LLM_PROXY_MODEL` 추가(`GOOGLE_CLOUD_*`=optional direct mode). **`discovery/config.py` 골격 — Phase 0 범위만**: `EnvSettings` base(memory-api `memory/config.py` 복제) + `LLMSettings`(§5는 `llm/config.py`) + 최소 `MemoryApiSettings`(`MEMORY_API_BASE_URL`·timeout만). connection limit 등 entity_http 실사용값은 Phase 2, `RankingSettings`(§4.2 임계)·`LinkerSettings`(§4① 임계)는 Phase 4/8에서 추가 — Phase 0에 settings를 미리 다 채우지 않는다. **`cli/__main__.py`는 echo import 제거 후 빈 CLI를 graceful 처리**: subparser `required=False`, 커맨드 없으면 help 출력 + 명시적 exit code(traceback 금지); recommend/corpus/eval은 Phase 5/6/7에서 순차 추가. *acceptance*: `pre-commit run --all-files`·`pytest` green(echo 제거로 깨지는 test 정리 포함) + **`uv run python -m cli`(인자 없음)이 traceback 없이 help 출력하고 결정된 exit code 반환**.
- **Phase 1 — 계약 동결**: `discovery/structs/*` + `providers/base.py` Protocol + **`providers/unavailable.py`(`Unavailable{Edge,Eligibility}Provider` + `NullPersonaProvider` — Protocol과 한 몸으로 지금 정의해 Phase 5는 와이어링만)**. entity read model(`EntitySummary`/`Entity`/`EntityConnections`/`ArticleHit`; `EntitySuggestion`은 이후 memory-api #87로 삭제 — legacy) + `Page[T]` envelope을 spec §2.6에 1:1 맞춤. `Query`/`NormalizedQuery`/`Recommendation` + `UserStanceRef`(§3.1) + linker 내부 `EntityCandidate`(§3) 정의. *acceptance*: `pre-commit run --all-files`(ruff+mypy) 통과, struct round-trip 테스트, **`Query`→`NormalizedQuery` normalizer 테스트**(§3.1 문법) — parse 실패 케이스를 명시 커버: `missing axis` / `missing dir` / `invalid dir`(enum 밖) / `unknown key` / `duplicated key` / `malformed segment` → for·against는 `invalid_need` 422; **need=depth/experience/coverage + user_stance_ref → no error(422 아님) + normalizer가 거부/raise 안 함**(`NormalizedQuery.user_stance`는 `None`, raw 문자열은 `NormalizedQuery`에 싣지 않고 원본 `Query`에 보존 — §3.1) — log-only의 *기록*(decision-log `user_stance_ref_raw`) 단정은 decision-log가 생기는 Phase 4/7에서; Phase 1은 "거부/유실하지 않고 통과시킨다"까지만 검증; 정상 입력 round-trip. 그리고 `UnavailableEdge/EligibilityProvider` 호출 시 `upstream_unavailable` raise + `NullPersonaProvider.get_prior`→`None` 단위 테스트.
- **Phase 2 — Real entity provider (단독)**: `HttpKnowledgeEntityProvider`(`/knowledge/entities`, Page unwrap) 단독. **linker는 Phase 4, API lifespan 와이어링은 Phase 5**다 — Phase 2는 provider 계약·transport만 다룬다(FastAPI app 경계가 아직 없음). **`MemoryApiSettings`를 entity_http 실사용값으로 확장**(connection limit·http2·keep-alive·retry 등 §3 sketch 필드 — Phase 0의 최소 골격에서 늘림). provider는 `from_settings()`로 자체 client를 구성하고 `close()`로 닫되(async-with lifecycle), **`app.state`/lifespan 1회 생성·request 재사용은 Phase 5로 미룬다**. *acceptance* (PR 기본은 **offline 결정론**, live는 env-gated): **(a) PR 필수 — `httpx.MockTransport`로 canned `/knowledge/entities`·`connections` 응답을 물려 provider 메서드가 `Page[T].items`로 unwrap되고 topic→QID가 도는 결정론 테스트**(★`suggest`는 memory-api #87로 삭제 → 재도입 금지, 기존 stale 메서드는 cleanup 대상)(외부 도구 0개 원칙 §2, 로컬 서비스 상태에 PR red가 좌우되지 않게 — pinned `anchors.json` 전체 코퍼스는 Phase 6라 canned로 충분) + GET-only retry(429/5xx/transport)·4xx 즉시 raise·2xx-invalid→`UpstreamUnavailableError` 래핑 단위 테스트; **(b) env-gated smoke — 실제 memory-api(live)** 로 동일 경로를 도는 integration 테스트(`MEMORY_API_BASE_URL` 등 env 있을 때만, CI 기본 skip). **(lifespan 1회 생성·shutdown close·request간 client 재사용 acceptance는 Phase 5 API 와이어링에서 검증)**
- **Phase 3 — Mock providers + 코퍼스 로더**: `eval/providers/{edge,persona,eligibility}.py`(discovery Protocol 구현) + JSON fixture 스키마. *acceptance*: fixture 로드→`get_edges` 조회 단위 테스트, **배포 앱 import 그래프에 `eval/` 미포함 검증**(serving 경로 mock-free).
- **Phase 4 — Pipeline ⓠ→⑥**: linker(symbolic)·retrieval·gate·ranking(ordering, §4.2)·serving·decision-log. stance는 symbolic 분류; **LLM rerank는 Phase 8**(Alpha linker는 deterministic symbolic, §4①). *acceptance*: mock 위에서 `recommend(query)`가 끝까지 도는 단위 테스트 + decision-log 생성.
- **Phase 5 — API + CLI recommend**: `POST /recommend` + `uv run python -m cli recommend …`. 배포 앱은 real provider만 와이어링하고, real 미통합인 edge/eligibility는 `Unavailable*`로, persona는 `NullPersonaProvider`로 채운다(§3). **provider/client lifecycle을 lifespan에 박는다**(Phase 2에서 이월): startup에서 `HttpKnowledgeEntityProvider.from_settings()`로 **httpx client를 1번 생성**해 `app.state`에 붙이고(request마다 재생성 금지·pool/keep-alive 재사용), **shutdown에서 `await provider.close()`로 닫는다**. *acceptance*: (a) **배포 와이어링** — `/recommend`가 anchor grounding까지 동작하고 edge 의존 단계에서 **503 `upstream_unavailable`** 반환(가짜 후보 ❌); (b) **full path** — TestClient `dependency_overrides`로 `eval/providers/` mock 주입 시 후보까지 end-to-end 동작(override는 test scope만); (c) **lifespan** — startup 1회 생성 / shutdown close / 여러 request가 동일 client 인스턴스 재사용 검증(TestClient lifespan context). template `tests/integration` 패턴.
- **Phase 6 — 평가 코퍼스 빌더**: §8의 생성 전략 구현(real QID grounding·strata·needle·가드 역산·gold label). **real memory-api 의존을 빌드 시점으로 격리**: `corpus build-anchors`만 live memory-api를 호출해 anchor를 **선별·고정(`anchors.json`)하는 수동/갱신 전용** 명령이고, search/detail/connections에 필요한 정보를 `anchors.json`에 함께 저장한다(= offline anchor substrate). `corpus build`(agent/edge/scenario/gold 합성)와 이후 `eval run`은 **pinned `anchors.json`만** 읽고 live 호출하지 않는다 → eval/CI는 네트워크 없이 결정론. *acceptance (green 최소 조건, 전부 통과해야 함)*:
  - 모든 코퍼스 JSON이 struct로 **schema-validate** 통과 — edge/agent/persona는 §3.1, scenario/gold는 §8.6(`Scenario`/`GoldLabel`) (깨지면 fail).
  - 모든 `edge.anchor_id`가 pinned `anchors.json`으로 **QID replay 성공**(실재 QID 아니면 fail).
  - stratum 4종(easy/guard/hard/ambiguous) 모두 non-empty, need 5종 각 **≥20 scenario**.
  - §8.3 **`stage=Alpha active` 가드 9종** **각각 ≥1 fixture** 존재·실제 단정. orthogonal/false-controversy(Open Beta)·favorite 비우회(Post-OB)는 corpus 태그만 — Alpha active assertion 제외. **known-item needle ≥1/need** 존재·유일.
  - `uv run python -m cli eval run`이 memory-api **미가동 상태에서도** 끝까지 실행 — **판정 없는 실행/커버리지 요약만** 낸다(`--format table|json`; score·pass/fail·threshold·judge 전부 ❌ = Phase 7/8 경계 보존). `table`=need별 `scenarios|completed|errored|recs_total|needles`, `json`=`{run_id·corpus_version·generated_at(주입)·summary·by_need·by_stratum·scenarios[]}` — scenario row는 `rank`만 싣고 **`score` 미포함**(§4.2 ordering contract). **exit code=scenario 하나라도 errored면 non-zero**(개별 실패가 green으로 보이지 않게), `--allow-errors`는 local-debug escape hatch로만(acceptance/CI 미사용). 커밋된 벤치마크 코퍼스는 **errored==0(exit 0)** 이어야 한다.
- **Phase 7 — Eval 하니스 + 지표 + gate + CLI**: `uv run python -m cli eval run`. need×stratum 지표, failure bucket, ratchet gate. *acceptance (green 최소 조건)*:
  - **hard fail = 0**: `must_not_show` false-pass = 0 **그리고** discoverability-off exposure = 0(둘 중 하나라도 >0이면 red, ramp 없음, spec §8.6). 이 =0 게이트와 아래 needle top-1은 **synthetic/human gold 라벨에서 결정론적으로 계산**한다 — LLM judge에 의존하지 않는다(안전·노출 게이트가 확률적 judge에 걸리면 안 된다; judge는 §8 fuzzy quality 전용).
  - **known-item needle top-1 = 100%**(심어둔 명백 expert가 1등 아니면 ranking 깨짐 — sanity gate).
  - **easy/needle stratum retrieval Recall@K = 100%**(후보 풀에서 누락되면 ranking 무의미).
  - 모든 scenario에 대해 **decision-log(§4.3) 1행씩 emit + schema-valid**.
  - grounding top-1/top-3, QID ambiguous fallback rate를 **baseline으로 측정·고정**(이후 ratchet 기준선).
  - **재실행 결정론**: 같은 코퍼스/seed로 재실행 시 지표 동일, baseline 이하로 떨어지면 red.
- **Phase 8 — LLM rerank + stance + B2 silver judge**: linker disambiguation, for/against, `eval/judge`. **judge=생성 단계 / metric=소비 단계로 분리한다**: B2 silver는 **pinned judge version(`judge@vN` + prompt·model·provenance)으로 생성해 persist**한다. Phase 7이 만든 metric layer는 phase 순서상 B2를 기다리지 않고(그 자체는 deterministic gold로 돈다), **이후 Phase 8의 persisted B2 silver 라벨을 소비할 수 있다** — **`eval run`은 기본적으로 live judge를 호출하지 않는다**(런마다 judge가 흔들리면 ratchet 비교가능성·offline 결정론이 깨진다). 이때 B2 silver가 ratchet 분모가 되므로 `*.silver.json`을 **커밋되는 versioned fixture로 승격**한다(§8.5). *acceptance*: judge meta-eval(order-swap 일관성) + B1 agreement 측정 자리 동작(spec §8.2).
- **Phase 9 — 검증/CI**: eval을 CI step으로(ratchet=regression). lessons/리뷰 정리.

Phase 0–5 = "경로가 돈다", 6–8 = "평가가 돈다", 9 = "회귀가 잠긴다". Phase 2/6은 둘 다 real anchor를 쓰며, Phase 6의 `corpus build-anchors`가 만든 pinned `anchors.json`이 이후 **오프라인 결정론 anchor substrate**가 된다(raw HTTP 카세트는 Alpha v0 미도입, §9).

> **Alpha 완료 = Phase 9 green.** Phase 9는 Post-OB가 아니라 Alpha의 완성 조건이다. Open Beta는 여기에 real Memory/Persona 통합·Push mode·orthogonal·feedback logging을 얹는 **다음 milestone**으로, 이 문서가 만든 provider contract·decision-log·eval harness를 기반으로 별도 build plan에서 이어간다.

## 7. 핵심 설계 규칙 (pythonic·simple)

- **Protocol 기반 DI** (PEP 544) — 상속 트리 없이 mock↔real 교체. FastAPI `Depends`로 `app.state`의 provider 주입(memory-api `depends/` 패턴).
- **Pydantic v2 strict** — 도메인은 `StrictBaseModel`, API는 `ApiModel(extra=forbid)`. enum은 `Field(strict=False)`(memory-api 규칙).
- **async 일관** — 모든 I/O(httpx, LLM) async. 팩토리는 `async def create`. keyword-only 인자.
- **`from __future__ import annotations`** 전 모듈. PEP 604 union(`str | None`), `list[...]`.
- **LLM은 래퍼 뒤에만** — `discovery/llm/wrapper.invoke_structured` 외부에서 LLM client 직접 호출 금지(테스트 주입성·replace 대비). wrapper는 provider 종류를 모르고 `LLMClient` Protocol만 의존(proxy default; direct provider는 `LLM_MODE=direct`에서만, Alpha acceptance 비포함). **provider 선택은 이 3곳(linker rerank·stance·B2 judge) 하부에서만 일어나고 agent ordering(§4.2)에는 절대 연결되지 않는다.** 호출 3곳은 memory-api 추출 패턴을 따른다: **structured output**(Pydantic schema 강제, `pydantic_response_format`) + **dual-model**(lenient mirror로 받아 strict 도메인 모델로 재검증, malformed 1건은 fatal 아니라 drop+warning — coldbrew, memory-api `extract.py`).
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

> **for/against는 추가로 perspective(axis+direction+stance)축 strata를 둔다.** 단순 semantic similarity가 아니라 *관점*을 retrieval에 반영하는 과제이므로(perspective-aware retrieval, impl §8.11), stratum을 관점축으로 짜되 **Alpha-active/OB-shadow**와 **human-gold/synthetic-negative** 비용 태그를 함께 붙인다(태깅 없으면 B1 라벨링 비용이 조용히 몇 배가 된다). 표 전체는 impl §8.7.

### 8.3 가드 역산 fixture (spec §7.3) — 가드 1개당 깨는 케이스 1개

`eval/builders/guards.py`가 다음을 결정론적으로 생성. **이게 곧 설계 불변식의 regression 테스트**:

| fixture | 방어 가드 | stage |
|---|---|---|
| dense / cold topic | sparse anchor fallback | **Alpha active** |
| ambiguous topic (QID 분기) | QID 정렬 실패 (§7.4) | **Alpha active** |
| same-axis disagreement | for/against 성립 | **Alpha active** |
| weak evidence agent | maturity gate | **Alpha active** |
| experience vs depth 구분 | experience need가 `experience_source_type`을 무시하고 depth처럼 maturity-heavy expert를 1등에 두지 않는지 — 직접경험 agent(`firsthand`, 낮은 maturity)가 추상지식 expert(`None`, 높은 maturity)를 experience에서 이겨야 함(§4.2) | **Alpha active** |
| high persona / low memory | hollow agent (prior가 maturity 못 채움) | **Alpha active** |
| stale but valuable | freshness=decay, hard cutoff 아님 | **Alpha active** |
| discoverability off | privacy/eligibility gate | **Alpha active** |
| rerank prompt injection | linker LLM rerank가 candidate description에 주입된 지시문에 흔들려 QID 선택을 바꾸지 않음 — 후보 텍스트=data, 명령 아님; 주입 케이스에서도 채택 QID 불변(§4①) | **Alpha active** |
| established axis 유무 | orthogonal / false controversy | Open Beta placeholder |
| favorite but topic-irrelevant | favorite이 need-complete gate를 **우회 못함**(§4.2). topic-irrelevant drop 자체는 weak-evidence/maturity 가드가 이미 커버 | Post-OB placeholder |

> **stage 열 의미.** `Alpha active` = Phase 6 acceptance의 가드 assertion 대상(각 ≥1 fixture·실제 단정). `Open Beta placeholder`(orthogonal/false-controversy)·`Post-OB placeholder`(favorite 비우회)는 **코퍼스에 태그만 심고** assertion은 해당 milestone에서 활성화 — Alpha는 orthogonal 미서빙·favorite 미소비라 위반 자체가 성립하지 않는다.

### 8.4 gold label ≠ scoring rule (spec §8.2) — 동어반복 방지

- gold label은 **스코어링 산식과 독립**으로 만든다. 같은 LLM/규칙이 데이터와 정답을 둘 다 만들면 construct validity 붕괴.
- **B1(human gold core, 소량)** = 산식과 독립된 *사람* 더블 라벨 — Alpha의 제한적 품질 주장은 **오직 여기서**. (Alpha 초기엔 B1을 "사람 검수 대기" 슬롯으로 두고, 합성 silver와 분리만 강제. 사람 라벨 채워지면 품질 비교 활성.)
- **B2(LLM silver, 대량)** = *다른* 프롬프트의 LLM judge — regression/탐색 커버리지용, **품질 주장 ❌**. 리포트에 항상 `silver` 표기.
- 라벨 4단계: `ideal` / `acceptable` / `bad` / `must_not_show`. `must_not_show`는 hard negative class(false-pass 직격).

### 8.5 산출물 형식 / 재현성

- 빌더는 **seed 고정 + 결정론**. 추적 정책을 한 곳으로 고정한다(§2 레이아웃과 일치):
  - **git 추적** = regression benchmark의 본체: `eval/corpus/fixtures/*.json`(anchors/agents/edges/scenarios)와 `eval/corpus/gold/*.json`(4단계 human/pinned gold). spec §8.4 "한 번 만들어 고정·재사용".
  - **`.gitignore`** = 매 실행 재생성되는 것: `eval/output/`(지표·report·decision-log dump)와 **LLM이 개입한 silver 산출물**(`*.silver.json`은 비결정적이라 추적하지 않고 빌더로 재생성). **단 Phase 8에서 B2 silver가 ratchet 분모가 되면** 비교 기준선이 흔들리면 안 되므로 그 silver set은 **커밋되는 versioned fixture로 승격**한다. wildcard `*.silver.json` ignore에 negative rule을 거는 대신, 승격 대상은 **버전 경로**(예: `eval/corpus/gold/b2_silver/judge_vN/*.json`)에 따로 두고 그 경로만 track한다 — 나머지 ephemeral silver ignore는 그대로 유지(구현 시 negative-path 혼선 방지).
- gold set 확장은 TREC식 pooling(여러 랭킹 변형 top-k + 랜덤 샘플 → 사람 판정). 빌더에 pool export 모드 포함.

### 8.6 eval artifact 최소 schema (Scenario / GoldLabel)

scenario·gold도 도메인 struct처럼 필드를 못 박는다 — Phase 6 `schema-validate`가 검증할 대상이자 eval 품질의 전제. eval 전용 pydantic 모델(`StrictBaseModel`, `eval/corpus/structs.py`).

**`Scenario`** (`scenarios.json` 1행):

| 필드 | 타입 | 의미 |
|---|---|---|
| `scenario_id` | `str` | 고유 ID |
| `topic_text` | `str` | 질의 주제 |
| `need_type` | `NeedType` | depth/experience/for/against/coverage |
| `user_stance_ref` | `str \| None` | for/against 기준 입장(그 외 `null`) |
| `expected_anchor_qid` | `str` | grounding 정답 QID(real, §8.1 불변식) |
| `expected_axis` | `str \| None` | for/against 기대 축 |
| `stratum` | `Stratum` | easy/guard/hard/ambiguous(§8.2) |
| `is_needle` | `bool` | known-item needle 여부(top-1 sanity, §8.2) |
| `tags` | `list[str]` | 가드/케이스 라벨 |

**`GoldLabel`** (`gold.json` 1행):

| 필드 | 타입 | 의미 |
|---|---|---|
| `scenario_id` | `str` | Scenario FK |
| `agent_id` | `str` | 대상 agent |
| `label` | `GoldLabelClass` | ideal/acceptable/bad/must_not_show(§8.4) |
| `rationale` | `str` | 판정 근거 |
| `source` | `GoldSource` | `b1_human`/`b2_silver`/`synthetic` — **B1/B2/synthetic 분리를 코드로 강제**(§8.4); 품질 주장은 `b1_human`만 |

eval enum 추가: `Stratum`(easy/guard/hard/ambiguous) · `GoldLabelClass`(ideal/acceptable/bad/must_not_show) · `GoldSource`(b1_human/b2_silver/synthetic). 전부 `StrEnum`.

### 8.7 `anchors.json` 최소 schema (`PinnedAnchorFixture`)

offline anchor substrate(§6 Phase 6·§9)의 모양을 못 박는다 — Phase 6 `schema-validate`의 대상이자, real memory-api 계약과의 drift를 잡는 지점. `eval/corpus/structs.py`의 pydantic 모델(`StrictBaseModel`)이고, **중첩 타입은 우리가 미러한 entity read model**(`discovery/structs/entity.py`의 `EntitySummary`/`Entity`/`EntityConnections`/`ArticleHit`; `EntitySuggestion`은 memory-api #87로 삭제 → legacy/stale, fixture는 suggest를 캡처하지 않음 D2)을 쓴다. memory-api `tests/routers/knowledge/test_examples.py`의 검증 패턴(예시 payload를 실제 모델로 `model_validate`)을 가져와, `anchors.json`을 `PinnedAnchorFixture`로 load-time validate한다(§10 계약 테스트 겸함).

```jsonc
{
  "contract": {                                  // → decision-log provider_versions.anchor · §8.10 substrate report
    "memory_api_commit": "<build-anchors가 호출한 memory-api commit>",  // 빌더가 실제 commit을 주입(placeholder — 상단 스냅샷 핀과 별개, build 시점값으로 채움)
    "entity_contract": "knowledge-entity@v0",
    "generated_at": "2026-..Z"                    // 빌더 주입(Date.now 금지 규칙과 무관, 런타임 주입)
  },
  "queries": [
    { "query_id": "aq_01",                        // fixture-내부 안정 핸들(scenario가 문자열 대신 이걸 참조 → query 변경에 안전)
      "query": "인공지능", "limit": 20,
      "search":  [ /* EntitySummary[] — Page.items 언랩 후 */ ],
      "expected_qid": "Q11660" }                  // suggest는 캡처 안 함(D2)
  ],
  "entities":    { "Q11660": { /* Entity (detail) */ } },          // → get(qid)
  "connections": { "Q11660": { /* EntityConnections */ } },        // → expand_connections(qid)
  "articles":    { "Q11660": [ /* ArticleHit[] */ ] }              // → search_articles (Alpha 후보경로 미사용 → optional)
}
```

설계 결정:
- **raw `Page` 저장 ❌, unwrap된 list로 저장** — Protocol 메서드가 이미 `list[…]`를 반환하고 `.items` 언랩은 real provider 책임이라(§3), fixture에 envelope을 넣으면 mock도 언랩을 중복 구현하게 된다. `Page.limit/truncated`는 오프라인 grounding eval 미사용(의도적 scope cut).
- **블록 ↔ Protocol 매핑**: `queries[].search`(키 = `(query, limit)`) → `search_candidates` · `entities` → `get` · `connections` → `expand_connections` · `articles` → `search_articles`. `suggest`는 fixture에 캡처하지 않으므로(D2) 오프라인 provider가 `[]`를 반환한다(Protocol 만족용, D3). pinned provider의 런타임 조회 키는 `NormalizedQuery`가 넘기는 **`query` 문자열**(provider는 `text`만 받음); `query_id`는 fixture 무결성·scenario 교차참조용 안정 핸들이다(런타임 조회 키 아님).
- **provenance**: `contract.memory_api_commit`/`entity_contract`가 substrate별 비교(mock↔real, §4.3 `provider_versions`)의 기준이 된다.

## 9. Eval 하니스 & CLI

`eval/harness.py`가 **substrate-agnostic**(provider만 교체하면 mock↔real, spec §8.10·§7.1):

```
load corpus (anchors/agents/edges/scenarios/gold)
  → build providers (eval mock edge/persona/eligibility + pinned-fixture|real anchor)
  → for each scenario: pipeline.recommend(query) + decision-log 수집
  → metrics: grounding/retrieval/gate/ranking/stance/coverage/reason/calibration
  → report: need × stratum 분해 + failure bucket(§8.8)
  → gates: ratchet 비교 (baseline.json) → CI red/green
```

**지표** (spec §8.5, `eval/metrics/`): grounding(QID top-1/top-3, real substrate quality gate) · retrieval(Recall@K, mock edge regression) · gate(false block/false pass) · ranking(nDCG@K/MRR/P@K/MAP@K, B층 proxy) · stance(same-axis/opposite) · coverage(unique axis/source/persona, redundancy) · reason(evidence_ref 없는 설명·stance mismatch 수) · calibration. 구현은 표준식 직접(외부 평가 프레임워크 미도입; spec §4.2 `pytrec_eval` 회피).

**Quality gate** (spec §8.6, `eval/gates.py`): 숫자 게이트(grounding accuracy/recall, fallback rate)는 baseline 고정→ratchet. **`must_not_show` false pass = 0**, **discoverability-off exposure = 0** 은 처음부터 hard fail(ramp 없음).

**CLI** (argparse, memory-api/template 패턴):

```
uv run python -m cli corpus build-anchors   # [live memory-api, 수동/갱신 전용] real QID 선별 → anchors.json(search/detail/connections 정보 포함) 저장
uv run python -m cli corpus build           # [offline] pinned anchors.json 기반 agent/edge/scenario/gold 합성 (seed 고정)
uv run python -m cli corpus build-guards    # [offline] §8.3 가드 역산 fixture
uv run python -m cli eval run [--format table|json] [--strata all|hard] [--needs depth,for,…] [--allow-errors] [--against-real]  # [offline] pinned anchors.json substrate; Phase 6=판정 없는 실행/커버리지 요약, gate는 Phase 7
uv run python -m cli eval report [--bucket]
uv run python -m cli recommend --topic "…" --need depth --substrate eval-mock|real   # 단건 디버그
```

`recommend`의 `--substrate`가 provider 조합을 고른다(배포 앱과 달리 CLI는 mock 사용 가능): `eval-mock`=**pinned anchor fixture(`anchors.json`) + `eval/providers/` mock** edge/persona/eligibility(기본, 오프라인), `real`=live memory-api + real edge/persona/eligibility(통합 후). 배포 serving 경로(`api/`)는 이 플래그와 무관하게 항상 real-only다. (raw HTTP response 카세트 `eval/corpus/recorded/`와 `recorded-anchor` substrate는 **Alpha v0 미도입** — anchor contract drift를 잡아야 할 때 Later 추가하고, grounding/linker만의 오프라인 디버그가 필요하면 별도 `anchor-debug` 명령으로 뺀다.)

`build-anchors`만 live memory-api에 접속하고, 그 외 코퍼스 빌드·`eval run`·CI는 pinned `anchors.json`(offline anchor substrate)로 **네트워크 없이 결정론**으로 돈다(Phase 6). `--against-real`을 줄 때만 통합 후 real edge에 붙는다.

`--against-real`은 mock edge 대신 real(통합 후) — 같은 gold set으로 substrate report(spec §8.10).

## 10. 테스트 & 검증 전략

- **단위**: 각 모듈(linker/retrieval/gate/ranking/serving/log) + metric 계산. LLM·httpx는 fake 주입.
- **integration**(`tests/integration`, TestClient): `POST /recommend` end-to-end via **FastAPI `dependency_overrides`로 `eval/providers/` mock 주입**(배포 앱은 mock-free, override는 test scope만). template `test_api.py` 패턴(에러 envelope·request-id) 재사용.
- **pinned anchor fixture**: `build-anchors`가 anchor 응답 정보를 `anchors.json`에 고정 → grounding/retrieval 테스트를 오프라인·결정론으로(raw HTTP 카세트 `recorded/`는 Alpha v0 미도입, §9).
- **eval = 회귀 테스트**: Phase 7부터 `uv run python -m cli eval run`을 CI step. ratchet 하향 시 red(CLAUDE.md "완료 전 증명").
- **계약 테스트**: mock provider가 Protocol을 만족하는지 + Entity* read model + provider `Page[T]` parser가 spec §2.6 memory-api entity read surface와 일치하는지(통합 시 real로 같은 테스트 재실행, spec §7.6).
- **staff-engineer 체크**: 새 도구 0개(기존 uv/ruff/mypy/pytest만), 도메인↔전송↔eval 격리 유지, LLM 의존 단일 래퍼.

## 11. 선결 / 능동 조율 (mock으로 못 숨김, spec §6.2·§7.4)

코드와 별개로 Alpha 중 Memory와 **합의 트랙**:

1. **QID vocabulary 의미 계약** — query-side linker QID ↔ producer-side anchoring QID가 같은 disambiguation 기준인지, alias/redirect/`LOCAL` anchor 규칙(spec §2.6·§7.4). 코퍼스 빌드가 이 정렬의 1차 리허설.
2. **edge contract shape + 필드별 source_owner** — `maturity/evidence_strength/freshness/observed_stance/discoverability`를 실제로 줄 수 있는지(spec §2.6·§7.2). mock edge 스키마가 합의 초안 역할. (`routing_target`은 계약에서 제거 — bourbon-api 런타임 해석; `agent_id`는 owner_id에서 파생.)

   > **(2026-07-02 갱신 메모, future MemoryEdgeProvider)** memory-api **main personal KG**(`d66b2c1`)에 **entity salience**(`salience` + owner/other refs·statements·opinions 분해)와 mention **reference_kind**(`public_figure`/`personal_acquaintance`/`unknown`)가 들어와 있다(WIP 브랜치가 아니라 main 코드). Discovery 입장의 판단은 그대로다: **이들은 retrieval prior·grounding precision 보조 신호 후보일 뿐, `maturity`/`evidence_strength`/`stance_confidence`를 대체하지 않는다** — salience는 "그 owner에게 자주/중요하게 등장"이지 "전문성이 높다"가 아니다(혼동 시 popularity prior 재유입 — directions의 평판/기여도 popularity-prior 금지 원칙 위반). 순기능: `reference_kind=personal_acquaintance → LOCAL` short-circuit이 public QID에 개인 지인 오결합을 줄여 `/personal/groundings/{qid}`의 noise를 낮춘다 = Discovery grounding precision↑. **신규(4106366 이후, `#36` 계열)**: statement가 이제 **public-KG-by-QID로 직접 매핑**되고(`_resolve_statement_entity` QID-direct→title-grounding fallback), `Statement`에 `subject_qid`/`object_qid`가 비정규화되며, `statement_edges.py`가 ASSERTED edge를 만든다 — **memory-api에서 "agent-topic edge"에 가장 가까운 실체**로, future real `MemoryEdgeProvider` 소스가 형태를 잡아가는 신호다(`anchor_id=QID` join이 Discovery 계약과 정렬). 다만 여전히 `/personal/*`(공개 `/knowledge` 아님)이고 아래 §11/implementation §2.6대로 discoverable/privacy/safety·`maturity`/`evidence`/`freshness`·`experience_*`·stance 필드가 빠져 있어 **`AgentTopicEdge` 직접 대체는 여전히 불가**(`routing_target`은 계약에서 제거됨·별개; `agent_id`는 owner_id에서 파생) → Phase 5 `Unavailable{Edge,Eligibility}Provider` 유지 판단 재확인. **salience serving 금지 재강조**: 나중에 쓰더라도 Alpha ordering은 lexicographic·no-aggregate-scalar이므로 salience를 serving score로 끌어오지 않고 **atomic feature 또는 eval/diagnostic로만** 쓴다.

   > **★2026-07-14 감사 갱신 (`2f268fe`·#64 competence vector):** 위 salience/statement-edge 메모를 competence 축이 대체한다. memory-api가 `Competence{frequency,breadth,depth,consistency,sentiment + rationales/aspects/persona_blurb/support_ids}` + Tier-2(`degree`/`hands_on_ratio`/`last_seen`/`opinion_ratio`)를 `PersonalEntitySummary`/`GroundingMatch`로 노출하고, cross-owner 검색(`/personal/groundings/{qid}?owner_ids=…`)도 이미 있다(agent_id는 owner_id 파생). 커밋이 명시적으로 "salience-orthogonal expertise axis for Discovery"·"supersedes gap-proposal maturity fields"라 부른다. ⇒ **`AgentTopicEdge` 직접 대체는 여전히 불가지만, edge 계약 협의가 "expertise edge 신설"→"competence/groundings→edge 투영 + translation layer"로 이동**했다. 매핑은 직접 대체 아님(maturity←depth조합·experience←hands_on_ratio는 candidate·freshness←last_seen transform); 진짜 남은 갭 = eligibility·stance axis/dir/confidence·evidence-ref 노출·`_score` projection. 상세 = impl/11 Phase 10 + memory-api-state 메모. (salience serving 금지 원칙은 그대로 유효.)

이 둘은 contract test가 "모양"만 보고 "값의 의미"는 못 잡으므로(spec §7.4) 별도 합의가 필요하다.

> **(future handshake) Open Beta 기법 후보 — Alpha 미도입(경계 흐림 방지).** 최신 연구로 검토했으나 Alpha 계약(no-scalar serving·not-RecSys·mock-first)과 충돌하거나 substrate 미성숙이라 **Open Beta로 보류**한다(근거 impl §8.11):
> - **KG-RAG rerank** (KG subgraph retrieval+rerank로 추천 보강): future `MemoryEdgeProvider`·salience/reference_kind가 안정화된 뒤에. 지금 넣으면 "추천 시스템" 냄새가 강해져 IR 골격 경계가 흐려진다.
> - **stance disentanglement / perspective embedding**: for/against를 stance-only 임베딩으로 푸는 사다리(anchor 파티션 → stance-only embed → projection layer). Alpha는 새 모델 없이 filter+ordering으로 충분.
> - **calibration / KL coverage divergence**: coverage를 1급 목적으로 보는 *개념적* 근거로는 타당하나 **서빙엔 금지**(MILP/KL/스칼라 목적함수는 §4.2 불변식 위반). **eval metric으로만** 채택 가능하며, 그때도 **reference distribution을 명시**해야 한다 — `KL(서빙결과 ‖ ?)`에서 reference는 Alpha coverage의 **round-robin group target**이다. 정의 없는 KL은 반증 불가능한 지표라 채택하지 않는다.

## 12. 결정·가정 (사용자 확인 대상) / Open Items

✅ = 2026-06-23 리뷰에서 사용자 확정. 나머지는 기본값(뒤집으려면 알려주세요):

| 결정 | 값 | 상태 |
|---|---|---|
| 도메인 패키지명 | `discovery/` (구 `module/`) | ✅ 확정 (recommendation/은 RecSys affinity로 오독 위험) |
| 이 계획 문서 위치 | planning 레포(여기) | ✅ 확정 |
| mock 저장소 | in-memory(JSON fixture) | ✅ 확정 (Postgres/vector는 spec §5 when-needed) |
| mock provider 위치/용도 | `eval/providers/` — 로컬 CLI 튜닝+eval 전용, 배포 serving 경로 미사용(repo엔 존재) | ✅ 확정 (배포 앱은 real만 와이어링, §3) |
| favorite/user-preference 소비 | Alpha 미소비(slot만 문서 예약, no-op 구현 X). 출처=`bourbon-api`(예상, memory-api/persona 아님). **positive favorite=Post-Open-Beta tie-break**(depth/experience/for, against/orthogonal=0), **negative preference(hidden/muted/dismissed)=Open Beta 후보 항목** | ✅ 확정 (§3·§4.2) |
| eval 산출물 git 추적 | fixtures/gold 추적, output/silver ignore (§8.5) | 기본값 |
| LLM 경로 | proxy default(`LLM_PROXY_MODEL`; Gemini=`google/gemini-2.5-flash`). direct OpenAI/Gemini=inactive layer(`LLM_MODE=direct`, Alpha acceptance 비포함) | ✅ 리뷰 반영 (§5) |
| echo 라우터 | 제거 | 기본값 |
| LLM deps | `google-genai`만 main `[project] dependencies`에 추가(OpenAI=raw httpx, `openai`/e3llm 불필요) | ✅ 리뷰 반영 (§5) |

Open Items(코드 무관, spec §9 deep research 대상): 한국어 EL 2-tier 세부, KG access(memory-api vs WDQS vs self-host), edge store 확정(통합 후), vector 도입 조건, eval stack(자체 metric 유지 vs Evidently).

---

**다음 행동**: 개명은 현재 기준 완료됐으므로, 승인 시 **Phase 0의 남은 작업**(echo 제거 + memory-api `memory/llm/` 포팅 + `google-genai` 추가 + `.env.example`/config·llm 골격)부터 착수한다.
