# 11. Forward 로드맵 (미구현 Phase 8 잔여 → 9 → 10 → Open Beta)

← [개요로 돌아가기](README.md) · 관련: [03. linker(구현된 grounding 사다리)](03-normalize-and-linker.md) ·
[08. LLM](08-llm-layer.md) · [10. metrics + gates](10-eval-metrics-and-gates.md)

이 문서는 **앞으로 할 일**만 담습니다. 이미 구현된 것(8A rerank + 재정의된 8B 그라운딩 폴백 사다리 전체)은
"동작 설명"이므로 **[03. linker](03-normalize-and-linker.md)의 "grounding 폴백 사다리" 절로 이관**했고,
여기서는 포인터만 둡니다. 각 항목은 "무엇을 추가하나 + **기존 코드/계약이 이렇게 바뀐다**"를 명시합니다.
Alpha가 자리(hook)를 예약해 둔 덕에 대부분 additive이고, 계약 struct는 대체로 안 바뀝니다.

> **마일스톤:** **Alpha**(7월, 내부, Pull + for/against) → **Open Beta**(8월말, 외부, Push + orthogonal)
> → **Post**. Phase 8/9는 Alpha→Open Beta 사이의 품질·평가 작업이고, **Phase 10(real edge 통합)이
> user-facing Alpha 성립의 마지막 조각**입니다 (2026-07-07 승격).
>
> **다음 순서 (2026-07-09 합의):** **Phase 9(eval→CI gate) ✅ 완료(2026-07-10) → Phase 10(real
> edge/maturity) → Phase 8B 잔여 튜닝.** CI 게이트로 "깨지면 바로 보임"을 Phase 10의 integration surface
> 확대 전에 잠갔다. 8B
> 사다리 _구현_은 끝났고(→ [03](03-normalize-and-linker.md)), 남은 8B 작업은 **튜닝**뿐(expansion
> threshold + harness expander seam + expansion stratum)이며 memory-api relevance fix 이후에만 유효하다
> (그 전엔 현 search 품질에 맞춘 premature tuning).

---

## Phase 8 — 남은 LLM 활성화 (judge · gate 필드 · context; stance·reason은 착지)

Alpha가 결정성을 위해 우회했던 [LLM 레이어](08-llm-layer.md)를 깨우는 단계입니다.

> **이미 착지 (동작 설명은 [03. linker](03-normalize-and-linker.md) / [06. serving](06-serving-and-decision-log.md)):**
> LLM rerank fallback(rung ②, Phase 8A) · `fallback_used` 신호(Phase 8A) · 재정의된 8B 그라운딩 폴백
> 사다리 전체(expansion ③ + substitution ④ rung + Decision A 라우팅 + report-only eval strata) ·
> **for/against 자유형 stance 정규화(8-3, 문법 우선 + LLM 폴백, 기본 OFF)** · **풍부한 per-need reason +
> 원 신호 노출(8-5, 보강 + `signals` always-on, 기본 OFF)** · **agentic grounder 재설계(8-7, 최근 대화
> context → LLM tool-use ReAct 루프, 기본 OFF; 켜지면 module ①의 primary가 되어 symbolic 사다리를 대체)**.
> agent OFF(현 기본 배포)에선 정밀 코어가 유지되고 LLM은 gate·신호가 걸린 폴백/보강에서만 돌며, agent ON에선
> agentic이 primary·symbolic이 결정적 폴백으로 강등된다(둘 다 [03](03-normalize-and-linker.md)에 서술).
> **여기서는 아래 둘(8-4 · 8-6)만 남았습니다.**

### 8-3. for/against stance 자유형 정규화 — ✅ **구현 완료** (동작 설명은 [03. normalize](03-normalize-and-linker.md)의 "자유형 stance 정규화" 절)
보수적 문법 파서를 **자유형 LLM normalizer 폴백**으로 보강. 문법이 canonical 경로로 남고, LLM은 문법
파싱이 실패할 때만 도는 폴백. rerank과 같은 dormant-ships(`STANCE_NORMALIZER_ENABLED` 기본 OFF).
- **실제 구현 (설계와 달라진 점):**
  - `normalize_query`를 async화하지 **않고** sync·문법 전용으로 유지 + 새 `normalize_query_async`
    sibling에 LLM 폴백을 얹음. 이유 = `eval/corpus/structs.py`의 sync `@model_validator`가
    `normalize_query`를 부르는데 통째 async화하면 조용히 깨짐(await 불가). blast radius = 파이프라인 1줄.
  - LLM wire 스키마는 새 `discovery/stance_normalize.py`의 `StanceNormalization`(strict, `extra=forbid`),
    concrete `LLMStanceNormalizer`도 여기. `StanceNormalizer` **Protocol은 소비자 `normalize.py`가 소유**
    (linker의 Reranker/Expander/Substituter 관례) — impl은 Protocol을 import하지 않는 duck-type.
  - `UserStanceRef.confidence` — Alpha에서 문법 경로는 항상 `None`, LLM normalizer가 채움 (query-side
    parse confidence, struct 변경 없음=이미 forward-compat). **decision log(audit)에만** 흐르고
    응답·gate·ranking 미노출 (parser지 policy 아님).
  - 결정성 보존: eval harness는 normalizer 미주입(`None`)이라 LLM 경로 dead + 모든 fixture가 문법형 →
    `baseline.json` byte-identical. 코드 repo `feat/phase-8-3-stance-normalizer` T1–T5 (contracts →
    `LLMStanceNormalizer` → `normalize_query_async` → wiring → 통합 테스트).

### 8-4. B2 silver judge + judge-derived 지표
- **추가:** LLM judge가 silver 라벨(`b2_silver`) 생성. 품질 지표를 gold에서 확장.
- **기존 변경:**
  - `eval/corpus/structs.py` `GoldSource` enum은 **이미 `B1_HUMAN` / `B2_SILVER` / `SYNTHETIC`를 정의**하고
    있음 (또 하나의 예약된 hook). Phase 6은 `synthetic`만 *커밋*할 뿐 — Phase 8은 enum을 바꾸는 게 아니라
    그 tier로 라벨을 **생성·커밋**함 (B1=double-review human gold=유일한 품질-주장 가능 tier, B2=pinned
    judge version의 LLM silver).
  - **핵심 계약: `eval gate`는 절대 live judge를 호출하지 않음.** B2 silver는 **persist**되고, 게이트는
    persisted 라벨을 읽음. [Phase 7](10-eval-metrics-and-gates.md)에서 세운 ratchet baseline이 B2 silver가
    꽂히는 분모가 됨.
  - `eval/metrics.py` — judge-derived 품질 지표 추가 (report-only 또는 새 ratchet). safety/exposure hard
    gate는 **여전히 결정적 gold만** (확률적 judge에 안 올라탐).
  - judge 버전이 ratchet 분모의 일부가 됨 (judge 업그레이드 = baseline 재설정 사유).

### 8-5. 풍부한 reason (serving) — ✅ **구현 완료** (동작 설명은 [06. serving](06-serving-and-decision-log.md)의 "reason + signals" 절)
결정적 feature 문자열을 per-need LLM explanation으로 **보강**(교체 아님)하고, 그 reason이 만들어진 **원
신호를 응답에 함께 노출**. rerank/stance와 같은 dormant-ships(`REASON_GENERATOR_ENABLED` 기본 OFF).
- **실제 구현 (설계와 달라진 점 / 리뷰로 잠근 것):**
  - **보강 + `signals` always-on:** `RecommendationItem`에 `signals: EdgeSignalsView`(원 maturity/evidence/
    freshness + presence-based 경험 필드) 신규 — **flag 무관 항상** 실림(결정적·`serve` settings-free).
    `maturity_band`는 신호가 아니라 cutoff artifact라 **제외**(클라이언트가 튜닝값에 결합되는 것 방지;
    band는 `feature_breakdown`=로그/튜닝에만). `reasons`는 list라 schema 변경 없음.
  - **sync-core + async-sibling** (8-3 `normalize_query`/`_async`와 동형): `serve`는 sync·순수 유지하고
    `reasons_by_agent` 맵을 소비만. 파이프라인이 `serve` 전에 `generate_reasons_async`(serving.py)를 await —
    `returned`는 **top-N 서빙 슬라이스만**, `topic`은 `grounding.label`(주제명이자 언어 신호).
  - **단일 소스 `_signals`:** 응답의 `signals`와 LLM 입력을 같은 함수로 지어 프로즈가 함께 실린 신호만
    말할 수 있음("response never lies"를 생성 레이어로 확장).
  - **소비자 소유 Protocol / duck-type impl:** `ReasonGenerator` Protocol은 소비자 `serving.py`, concrete
    `LLMReasonGenerator`는 새 `discovery/reason_generate.py`(Protocol import 안 함·client 무보유·batch 1콜).
  - **strict coverage + 예외 가드(리뷰):** 응답이 서빙 agent를 non-blank로 정확히 커버 못하면 → 전량
    결정적 폴백(부분 혼합 금지); generator가 throw해도 좁게 잡아 degrade(200을 500으로 악화 안 함). 프롬프트에
    honesty 가드 = `experience_source_type`가 firsthand일 때만 "직접 경험" 주장 허용.
  - 결정성 보존: eval harness는 generator 미주입(`None`) → LLM 경로 dead → `baseline.json` byte-identical +
    `eval run` 요약 불변. 코드 repo `feat/phase-8-5-rich-reason` T1–T5 (contracts+signals → `LLMReasonGenerator`
    → `generate_reasons_async` → wiring → 통합 테스트).

### 8-6. Open Beta 전 게이트 필드
- **기존 변경:** `discovery/structs/eligibility.py` `Eligibility` — `privacy_clearance` / `safety_verdict`
  필드 추가 (현재 `discoverable`만 활성). gate(③)의 `_need_agnostic_drop`에 새 drop 사유 추가 가능. safety는
  타 팀 위임, privacy는 deferred였음. (실제 gate 배선은 Open Beta stage 8 — 아래 참조.)

### 8-7. grounding 맥락 disambiguation — agentic grounder ✅ **구현 완료 · 기본 OFF** (동작 설명은 [03. linker](03-normalize-and-linker.md)의 "agentic grounder" 절)
- **문제:** recall(MISS)은 memory-api 다국어 인덱스 fix로 대체로 해소됐고, 남은 지배적 실패는 **identical-label
  homonym TIE** — 같은 label(`Python`)을 언어·뱀이 공유(재측정 GROUND 7 / **TIE 10** / MISS 3). symbolic은 둘 다
  confidence 1.0 → margin 0 → tie를 **원리적으로** 못 깬다. tie를 가르는 유일한 새 정보는 **최근 대화 맥락**이다.
- **★2026-07-15 방향 확정 — C-lite/backend-search 접근 폐기:** memory-api가 `/knowledge/entities` 검색에서
  **`context=`를 제거**했다(현 `POST /knowledge/entities/search`는 `queries[]`/`instance_of`/`fanout`만;
  `5530192`). backend rank로 sense를 boost할 방법이 사라졌고, 링커가 backend 순서에 기댈 근거도 없어졌다.
  이전 판(2026-07-14)의 "C-lite(`context=` prose bias 검색) + 링커 채택계약을 backend 순서 동점깨기로 변경 +
  `_score` projection ask" 계획은 **전부 폐기**한다.
- **결론 = context를 읽고 sense를 고르는 주체가 LLM이어야 한다 → agentic grounder(재설계).** context-bias 검색
  (C-lite)도, write-side `Grounder`를 read endpoint로 노출(구 full-C)도 아니고, discovery가 **최근 대화
  (`context_messages`)를 받아 native tool-use ReAct 루프로 직접 grounding**한다.
- **구현 (shipped dormant, 코드 repo `feat/grounding-agent` T1–T9):**
  - `Query.context_messages: list[ContextMessage]`(대화 턴)을 ⓠ normalize가 `grounding_context`(lean
    projection·raw wire 메시지는 drop)로 투영 → 링커가 agentic grounder에 전달. → [01](01-data-contracts.md).
  - `LLMGrounder`(`discovery/grounding_agent.py`)가 `complete_with_tools`(≤5턴, `tool_choice="required"`)로 4개
    tool(`search_entities`/`get_entity`/`get_connections`/`submit_grounding`)을 돌려 QID를 확정. **4중 adoption
    gate**: membership(=`get_entity`로 관측한 qid만) · confidence ≥ `GROUNDING_AGENT_CONF_MIN`(0.70) · self-cite
    (qid ∈ evidence) · evidence ⊆ observed · non-blank obs.
  - **D1 라우팅:** context 有 → **agentic primary** / context 無 → symbolic `_ground_symbolic()`. context 無에서
    unique-exact는 채택(결정적·저비용·CI 커버)되고, tie·miss가 실패(abstain)하는 것은 **agent-ON composition root가
    rerank/expansion/substitution rung을 미주입**하기 때문이지 Linker 자체 계약이 아니다(agent OFF 기본 배포·hand-built
    Linker는 rung이 살아 있어 기존 사다리대로 — [03](03-normalize-and-linker.md) "라우팅 vs rung 은퇴"). context 無 +
    tie·miss abstain의 근거 = dominant-sense 추천 = popularity prior 회귀 금지. context 공급됐으나 usable text 0
    (attachment-only) → terminal `GroundingFailedError`(symbolic 부활 안 함).
  - **활성화:** `GroundingAgentSettings.GROUNDING_AGENT_ENABLED`(기본 **OFF**, dormant ship). composition root가
    ON일 때만 `LLMGrounder` 주입 + **rerank/expansion/substitution rung 전부 은퇴**(agent가 context-primary로 그
    회복 역할 흡수). eval/offline 미주입 → 전 경로 symbolic 폴백 → `baseline.json` byte-identical + CI 커버 유지.
  - **trajectory 로깅:** decision_log ⑥에 각 스텝(queries/instance_of/본 qid들/따라간 connection) + 최종 pick +
    사유를 **additive block**으로 — symbolic `considered` trace의 agentic 대응(retrieval~serving 계약은 불변).
  - `GroundingMode` enum에 **`agentic` 추가**(online agentic=`agentic`, context-absent unique-exact 및 offline
    폴백=`symbolic`; 구 rung 값 `rerank`/`expansion`/`best_effort_substitution`는 enum 유지하되 **live 경로 은퇴**).
    `fallback_used`는 agentic·symbolic 모두 `False`(agentic은 폴백 아니라 primary online 경로 — 관측 정직성).
- **의식적 불변식 대체(정직하게):** "symbolic 정밀 코어가 영구 primary"라는 기존 불변식을 **의식적으로 대체**한다 —
  구 Phase 8B "listwise full replacement" 폐기 결정을 **다른 근거**(memory-api `context=` 제거 + bounded tool-use
  loop + membership guard)로 되살린 것. symbolic은 죽지 않고 **결정적 offline/eval 폴백 + online context-absent
  unique-exact short-circuit**으로 강등된다.
- **선행 (online rollout 게이트):** context grounding의 relatedness는 model/human-judged라 **8-4 B2/human judge**가
  online 활성화의 게이트다(결정적 gold gate는 context 품질을 보증 못 함). `context_messages` 공급은 **agent
  moderator**(대화 보유 상위 계층) 몫 — discovery는 대화를 직접 보지 않고 나르기만 한다.
- **폐기 기록:** `context=`(search param) · `_score` projection · `types=`-as-search-param 접근 = **미채택**. 되돌림
  트리거 = memory-api가 `context=`를 다시 배포하고 real edge에서 backend-rank 이득이 실측될 때 재평가.

---

## Phase 9 — eval → CI gate ✅ 구현 완료 (2026-07-10)

`.github/workflows/ci.yml` 배선 완료(code repo `feat/phase-9-ci-gate` 머지). PR + `main` push마다
**3개 병렬 job**이 돈다:

- **`checks`** — `uvx pre-commit run --all-files` (ruff lint+format · mypy · codespell · yamlfmt ·
  uv-lock). `uv sync` 없음 — pre-commit이 자기 hook env를 따로 만듦.
- **`test`** — `uv sync` + `uv run pytest`. `E3LLM_LIVE` 미설정 → live-LLM smoke 자동 skip →
  **오프라인·결정적**(네트워크·LLM 비용 0).
- **`eval-gate`** — [`eval gate`](10-eval-metrics-and-gates.md)를 committed corpus + `baseline.json`에
  대해 실행. **결정적**(reranker/expander/substituter = None → LLM 무접촉); ratchet 회귀·errored
  시나리오·stale baseline이면 non-zero exit로 job이 red. JSON 리포트를 `eval-report` artifact로 업로드.

- **동작 세부:** interpreter는 `UV_PYTHON=3.14` pin(uv on-demand 설치; 러너 실측 3.14.6). 액션은 전부
  node24 major(`checkout@v5` · `setup-uv@v8.3.2` · `cache@v5` · `upload-artifact@v6`). baseline 갱신
  절차와 "CI가 무엇을 보증/미보증하는가"(층별)는 [10. eval metrics + gates](10-eval-metrics-and-gates.md)
  "CI wiring (Phase 9)" 절 + code repo README `## Continuous Integration` 참조.
- **변별력의 현재 한계(과장 금지):** 현 ratchet은 manual-seed 코퍼스에서 전부 천장(top1/top3=1.0 over 111,
  fallback 0/25) — **엄격하되 좁은 분포**만 검사한다. hard gate는 코퍼스 크기와 무관하게 지금도 유효(절대
  불변식). 한계는 **evaluation coverage이지 gate leniency가 아니며**, 더 강한 **regression signal**은
  real anchor + ambiguous 층이 들어오는 **Phase 10 이후**에 붙는다. gold도 synthetic이라 change-detector
  이지 quality measure가 아니다 → [10](10-eval-metrics-and-gates.md).
- **선행 전제(2026-07-08/07-10):** real 앵커는 **동음이의 exact-label 동점**을 드러냄(오프라인에서 7/25만
  ground — [findings](findings-real-anchor-grounding-ties.md)). 강한 재측정의 실질 선행은 **memory-api
  search relevance 개선**(alias는 이미 검색되나 흔한 이름은 label^3에 밀림; memory-api 팀 소유 외부
  dependency, discovery 8B가 지는 작업 아님). **2026-07-10 실측**으로 gap 확인(예: `q=JavaScript` → 정본
  top-50 밖). 맥락-무관 recall/ranking(A)과 동음이의 sense 선택(맥락 필요, §8-7)은 **별개**다 —
  [findings](findings-real-anchor-grounding-ties.md) "Memory-api public search relevance",
  `memory_api_agent_recommendation_requirements*.md`.
- **2026-07-14 갱신:** memory-api가 **다국어 인덱스 overwrite 버그를 fix + 전체 재색인** → cross-language
  burial 해소(예: `q=JavaScript`→Q2005 rank 1). 전량 재측정(20-seed) = **GROUND 7 / TIE 10 / MISS 3**; 실패
  원인이 recall→**tiebreak**로 이동(canonical이 rank 1로 표면화하나 exact-label 동점을 linker가 margin 0으로
  무너뜨림). 상세 = [findings](findings-real-anchor-grounding-ties.md) 'Update (2026-07-14)'.
  - **2026-07-15 후속:** 당시 열렸던 검색 `context=` 경로는 memory-api가 이후 **제거**(`5530192`)했고, 동음이의
    disambiguation은 대화-context를 읽는 **agentic grounder(§8-7, 구현 완료·기본 OFF)**로 방향이 바뀌었다.

---

## Phase 10 — real edge 통합 (user-facing Alpha 성립) — **2026-07-07 신설**

Roadmap §10 Alpha 단계 2(agent-topic edge projection)·4(maturity gate)에 대응합니다. Phase 8/9가 전부
품질·평가 작업인 반면, 배포된 Pull API가 grounding 후 후보 단계에서 503을 반환하는 현 상태를 해소하는
**유일한 성립 작업**이라 별도 phase로 승격했습니다. (real edge를 Open Beta로 미루면 어차피 OB의 크리티컬
패스로 되돌아올 뿐입니다.)

- **최소 범위** — mock 3종을 전부 교체하지 않습니다:

  | Provider | Alpha 처리 | 근거 |
  |---|---|---|
  | `MemoryEdgeProvider` | **real HTTP 교체 — 유일 필수** | 후보가 나오는 유일한 소스 |
  | `EligibilityProvider` | `discoverable=true` 가정의 얇은 stub | 2026-07-03 rec-signal 계약: visibility 보류 → agent-rec true 가정 |
  | `PersonaProvider` | NullProvider 유지 | `persona=None` 합법 · Alpha ranking no-op |

- **기존 변경:** Protocol seam([02](02-provider-boundary.md)) 덕에 코드 작업은 **real `MemoryEdgeProvider`
  구현 1개 + deployed-only `AllowAllEligibilityProvider`(가칭) stub + composition
  root([07](07-composition-api-cli.md)) 교체**로 유계. eligibility stub이 왜 필수인가: 현 배포 graph는
  `UnavailableEligibilityProvider`(hard-required → 503)라 real edge만 붙이면 503이 후보 단계에서 gate
  단계로 옮겨갈 뿐임. eval의 mock eligibility는 import-isolation(serving graph의 `eval/` import 금지) 때문에
  재사용 불가 — `discovery/providers/`에 얇은 stub을 신설하고, decision log의 `ProviderVersions`도
  edge·eligibility 둘 다 `unavailable@v0`에서 real/stub 표기로 갱신(출처 정직성). Phase 2의
  `HttpKnowledgeEntityProvider`가 real HTTP provider의 템플릿.
- **선행(진짜 크리티컬 패스) — cross-team 계약:** (1) **memory-api edge = Competence vector 투영 계약**
  (2026-07-14 감사로 재정의). memory-api가 이미 주는 것: **(a) cross-owner 후보 검색** —
  `GET /personal/groundings/{qid}?owner_ids=…`(생략 시 전 owner)가 public QID 기준으로 owner별 매치를
  돌려줌(`Page[GroundingMatch]`, 각 항목이 `owner_id` 보유). **(b) agent identity** — `owner_id`에서 파생
  (bourbon-api `personal_agent_id`; 2026-07-03 rec-signal owner_id-only 계약 그대로 → memory-api 갭 아님).
  **(c) expertise 신호** — #64 "competence vector"(`8092bc3`, "salience-orthogonal expertise axis **for
  Discovery**"·커밋이 "supersedes gap-proposal §4② maturity fields"라고 명시): `Competence{frequency,
  breadth, depth, consistency, sentiment + depth/consistency_rationale, aspects_covered, open_questions,
  persona_blurb, support_ids}` + Tier-2(`degree`=centrality, `hands_on_ratio`=경험/실무 비중, `last_seen`,
  `opinion_ratio`), `PersonalEntitySummary`로 노출. → **협의 방향이 "expertise edge를 새로 만들어달라"가
  아니라 "이미 있는 competence/groundings를 Discovery `AgentTopicEdge`로 투영하는 계약 + translation
  layer"로 이동.** 신호 매핑(직접 대체 아님·translation layer의 입력):

  | AgentTopicEdge | memory-api 소스 | 성격 |
  |---|---|---|
  | cross-owner 후보 검색 | `/personal/groundings/{qid}` (`owner_id` 포함) | ✅ 이미 있음 |
  | agent identity | `owner_id`→`personal_agent_id` 파생 (bourbon-api) | ✅ 갭 아님 |
  | maturity | `depth`(+`breadth`+`consistency` 조합) | ⚠️ 입력신호, 직접 대체 아님 |
  | evidence_strength | `support_ids` 수 + statement confidence + `consistency`/`frequency` | ⚠️ 조합 |
  | experience_source_type/specificity | `hands_on_ratio` | ⚠️ **strong candidate**, exact 아님 — `StatementKind.EXPERIENTIAL/PROCEDURAL` 원자료 필요 |
  | freshness | `last_seen` | ⚠️ source 있음, `now − last_seen` decay/normalize(0..1) transform 필요 |
  | coverage 재료 | `breadth` / `aspects_covered` | ✅ |
  | evidence_refs | `support_ids`(UUID) | ⚠️ 외부 노출·dereference(statement/message id·tenant 경계) 계약 필요 |
  | reason 재료 | `persona_blurb` / `aspects_covered` | ✅ |
  | **eligibility**(discoverable/privacy/safety) | 없음 | ❌ **진짜 갭** |
  | **stance** axis/dir/confidence | `sentiment`만(축 아님) | ❌ **진짜 갭** |

  즉 남은 진짜 갭 = **① Discovery edge projection(eligibility + stance axis/dir/confidence 포함) ②
  competence→edge signal translation layer(maturity/evidence/freshness 파생) ③ evidence-ref 노출 계약** —
  대부분 discovery·bourbon-api·persona 몫이지 memory-api가 새 edge를 만들 일이 아님. (2) **agent moderator의
  `context_messages` 공급** — agentic grounder(§8-7) sense 선택 context의 유일 소스(discovery는 대화를 직접 안 봄);
  없으면 grounder는 context-absent 경로(unique-exact 채택 / tie·miss abstain)로만 동작. 대화 맥락은 이미 있는
  축이라 계약 예약. 계약 협의는 리드타임이 기니 코드 작업과 무관하게 즉시 시작.
  - **폐기(2026-07-15):** 구 선행 "memory-api relevance/`_score` projection"(grounding 동점을 backend 순서로
    깨려던 ask)은 memory-api가 검색 `context=`를 제거하며 **철회**됨 — 동점 disambiguation은 이제 agentic
    grounder가 대화 맥락으로 처리한다(§8-7).
- **8B 잔여 튜닝·8-4와의 순서:** 8B 사다리 _구현_은 끝났다(→ [03](03-normalize-and-linker.md)). 남은 8B
  **튜닝**(expansion threshold + expansion stratum)과 judge 분모(8-4)는 후보가 mock인 상태에선
  end-to-end 레버리지가 낮아 **real edge(Phase 10) 이후**로 미룬다. §8-7(동음이의 disambiguation)은 **agentic
  grounder로 구현 완료(기본 OFF)** — online 활성화 게이트가 8-4 judge라 순서상 8-4에 이어진다(§8-7 참조).
- **Push shadow(로드맵 단계 7):** Phase 10 이후로 **명시 이월**. Alpha 기간에는 query DTO 계약 초안 합의만 한다.

> **이력:** 2026-07-07 판의 "권장 착수 순서"는 위 2026-07-09 합의 순서(Phase 9 → 10 → 8B 튜닝)로 대체됨.

---

## Open Beta 로드맵 (Alpha 이후)

Alpha(Pull + for/against, 내부)에서 Open Beta(외부)로 가려면 **새 기능 축**이 붙습니다.
번호는 [Roadmap](../archive/Agent_Discovery_Recommendation_Roadmap.md)(보관됨)의 단계와 맞춥니다.

### OB 선행 — 계약·게이트 결정 (cross-team, 리드타임 김)
- **Roadmap 단계 7 — Push DTO + shadow.** Alpha 기간엔 query DTO 계약 초안만 합의(shadow). Open Beta에서
  `SilenceView`가 실제 push-silence 판정을 수행하게 됨.
- **§11 safety/privacy 외부 게이트.** candidate safety verdict·privacy clearance의 **소유·계약을 타 팀과
  협의**(Alpha에선 deferred). 이게 OB의 크리티컬 패스 — 코드보다 협의 리드타임이 관건.

### OB 단계 8–11 — 기능 활성화
8. **candidate safety + discoverability gate 활성화** — `Eligibility`의 `privacy_clearance` /
   `safety_verdict`(8-6에서 *자리만* 만든 필드)를 gate `_need_agnostic_drop`에 실제 배선. real
   `EligibilityProvider`가 신호를 채움.
9. **Push user-facing** — shadow였던 Push를 실서빙 경로로. Push-silence 판정이 사용자에게 반영됨.
10. **orthogonal 조건부 서빙** — Alpha stance는 for/against까지. orthogonal은 OB에서 조건부로 서빙.
11. **feedback logging + per-need eval** — 서빙 피드백 수집 → per-need 품질 지표로 확장.

### 계약/파이프라인이 더 크게 바뀌는 것 (대부분 schema 변경 없이 흡수)
- **real provider 완성** — edge는 **Phase 10**(위)으로 이미 승격. 남는 것은 `EligibilityProvider`(실제
  discoverability/safety 신호)·`PersonaProvider`의 real
  교체. 이음매가 Protocol이라 **배선 변경**으로 끝남 ([02](02-provider-boundary.md),
  [07](07-composition-api-cli.md)).
- **OpeBlock 채움** — `DecisionLogRecord.ope`가 Alpha에선 빈 채 형태만. OB OPE replay가
  propensity/action_set/reward_proxy를 채움 (**schema 변경 없이**).
- **favorite/preference 신호** — Alpha reserved slot(no-op). personalization(≠expertise)로
  UserPreferenceProvider(bourbon-api 출처 예상) 신설, negative-first, tie-break only, gate 우회 금지.
- **reputation/contribution** — 품질 보강이지 popularity prior 금지. safety=gate, contribution=need-조건부,
  reputation=tiebreaker.

## Post (Open Beta 너머)
- **disentangled 임베딩** — 연구 베팅이 아니라 anchor 파티션 → stance-only embed → projection layer 사다리.

---

**요점:** Alpha가 계약 struct와 Protocol 이음매를 먼저 얼려둔 덕에, 남은 Phase 8 잔여·9·10 변경의 대부분은
여전히 **additive**로 흡수됩니다 (`UserStanceRef.confidence`·`OpeBlock`·b1/b2 gold tier·eligibility 필드
같은 예약 hook). 그 배당금의 마지막 수취처가 **Phase 10**입니다 — user-facing Alpha를 성립시키는 real edge
교체가 provider 구현 1개 + 배선으로 끝나는 것은 seam을 먼저 얼려뒀기 때문입니다.
