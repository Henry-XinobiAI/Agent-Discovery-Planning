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

## Phase 8 — 남은 LLM 활성화 (stance · judge · reason · gate 필드)

Alpha가 결정성을 위해 우회했던 [LLM 레이어](08-llm-layer.md)를 깨우는 단계입니다.

> **이미 착지 (동작 설명은 [03. linker](03-normalize-and-linker.md)):** LLM rerank fallback(rung ②,
> Phase 8A) · `fallback_used` 신호(Phase 8A) · 재정의된 8B 그라운딩 폴백 사다리 전체(expansion ③ +
> substitution ④ rung + Decision A 라우팅 + report-only eval strata). 정밀 코어는 유지하고 LLM은
> gate·신호가 걸린 폴백 rung에서만 돈다. **여기서는 아래 넷만 남았습니다.**

### 8-3. for/against stance 자유형 정규화
- **추가:** [normalize](03-normalize-and-linker.md)의 보수적 문법 파서를 **자유형 LLM normalizer**로 보강.
- **기존 변경:**
  - `discovery/normalize.py` — `_parse_user_stance_ref`의 엄격 문법이 자유 문장 파싱을 허용하게 확장
    (문법 파서는 fallback으로 유지 가능).
  - `UserStanceRef.confidence` — 현재 Alpha에서 항상 `None`인 필드를 LLM normalizer가 채움 (query-side
    parse confidence). struct 변경 없음 (이미 forward-compat 필드).

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

### 8-5. 풍부한 reason (serving)
- **기존 변경:** `discovery/serving.py` `_reason()` — 결정적 feature 문자열을 per-need LLM explanation으로
  교체/보강. `RecommendationItem.reasons`는 list라 schema 변경 없음.

### 8-6. Open Beta 전 게이트 필드
- **기존 변경:** `discovery/structs/eligibility.py` `Eligibility` — `privacy_clearance` / `safety_verdict`
  필드 추가 (현재 `discoverable`만 활성). gate(③)의 `_need_agnostic_drop`에 새 drop 사유 추가 가능. safety는
  타 팀 위임, privacy는 deferred였음. (실제 gate 배선은 Open Beta stage 8 — 아래 참조.)

### 8-7. grounding 맥락 전달 (`topic_context`) — 동음이의 sense 선택
- **문제:** 맥락 없는 grounding은 동음이의에서 **dominant sense로 확정**한다(`Python`→언어). rerank 결함이
  아니라 context-free의 본질적 한계(근거: [findings](findings-real-anchor-grounding-ties.md) Spike 2 +
  "Memory-api public search relevance"). 그런데 현재 `/recommend` grounding이 보는 건 `topic_text`뿐 —
  `Query.context`(dict)는 eligibility 전용이라 grounding에 안 닿음. 즉 sense 선택은 **진입부터 맥락이 없다**.
- **추가(계약, additive):** `/recommend`의 `Query`에 optional 자연어 `topic_context: str | None` 예약 —
  client가 "그 주제가 등장한 문장/맥락"을 실어 보냄(구조화 type 힌트가 아니라 자연어; memory-api grounder가
  먹는 형태와 동일). Alpha에선 계약 예약 + 로그만, 소비는 rerank 튜닝/Phase 10. → [01](01-data-contracts.md).
- **소비 위치 결정 (B-vs-C) — 잠정 lean = C, 확정은 Phase 10:**
  - **(B)** discovery의 rerank가 `topic_context`를 프롬프트 맥락으로 소비.
  - **(C)** memory-api가 ingest용 `Grounder.ground(mention, *, context=)`를 read 엔드포인트로 노출 →
    discovery가 `ground(topic_text, context=topic_context)` 호출.
  - **잠정 판단 = C (2026-07-10).** 근거:
    - **조인 정합성(핵심):** discovery의 존재 이유가 query-anchor QID ↔ agent-topic-edge QID 조인인데,
      그 edge들은 바로 그 `Grounder`가 만든 것. C는 query를 edge를 만든 같은 도구로 grounding →
      두 QID가 같은 disambiguation 로직에서 나옴 → 조인 어긋남 위험 제거. B는 rerank가 같은 mention에
      Grounder와 **다른 QID**를 고를 수 있어 체계적 miss 여지.
    - sense 판별 로직을 두 곳에서 각자 구현해 drift하는 것을 C가 방지.
    - C는 신규 능력 구현이 아니라 **이미 있는 offline Grounder를 endpoint로 노출**하는 것(가벼움).
  - **C 확정 전 확인 조건 2개(둘 다 Phase 10 real edge에서):**
    1. **memory-api가 Grounder를 read endpoint로 노출할 의향/커밋.** 현재 Grounder는 offline-build 전용
       (HTTP 없음). 우리가 소유 못 하는 크리티컬 패스이므로 memory-api 커밋 전엔 확정 불가.
    2. **얇은 query 맥락에서도 정합성 이득이 실측될 것.** Grounder는 edge 쪽 풍부한 문서/대화 맥락용 설계 —
       query 쪽은 짧은 topic + 얇은 `topic_context`라 이득이 부분적일 수 있음. real edge에서 실측 필요.
  - **C의 트레이드오프(확정 시 감안):** hot path에 network hop + LLM 호출을 memory-api 뒤로 밀어넣음 →
    latency·가용성 종속. 현 코어는 로컬·결정적(search-only precision core)임.
  - **폴백 경로:** `topic_context` 필드는 B/C에 무관(맥락을 안쪽으로 나르기만 함). 필요하면 우리가 소유하는
    **B로 임시로 막았다가 memory-api가 endpoint를 내놓으면 C로 이관** 가능 — client 계약은 어느 쪽이든 불변.
  - **B/C 공통 선결:** 아래 memory-api 검색 recall/ranking 개선(A). Grounder의 candidate 단계도 같은
    lexical recall을 재사용하므로 C도 A를 피해가지 못함.
- **선행:** 무엇을 택하든 memory-api **검색 recall/ranking 개선**(cross-language/alias 정본 누락)이 선결 —
  후보가 recall돼야 sense를 고를 수 있음(A는 맥락과 무관; [findings](findings-real-anchor-grounding-ties.md)
  + `memory_api_agent_recommendation_requirements*.md`).

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
- **선행(진짜 크리티컬 패스):** memory-api와 edge/maturity 계약 협의. `/personal/groundings`는 maturity 등을
  안 주므로 **translation layer 또는 전용 discovery 엔드포인트**가 필요. 출발점 = 2026-07-03 rec-signal
  계약(owner_id-only, agent_id는 bourbon-api `personal_agent_id` 파생). **핵심 안건 = maturity 소유**
  (memory-api가 제공 vs discovery측 계산). 계약 협의는 리드타임이 기니(rec-signal 계약도 한 라운드) 코드
  작업과 무관하게 즉시 시작.
- **8B 잔여 튜닝·8-4와의 순서:** 8B 사다리 _구현_은 끝났다(→ [03](03-normalize-and-linker.md)). 남은 8B
  **튜닝**(expansion threshold + expansion stratum)과 judge 분모(8-4)는 후보가 mock인 상태에선
  end-to-end 레버리지가 낮아 **real edge(Phase 10) 이후**로 미룬다. 8B 튜닝은 memory-api relevance fix에도
  의존. 그리고 §8-7(`topic_context` 소비 B-vs-C, **잠정 lean = C**)도 real edge 붙일 때 확인 조건 2개
  (memory-api Grounder endpoint 노출 커밋 + 얇은 query 맥락 정합성 실측)를 확인해 확정한다.
- **Push shadow(로드맵 단계 7):** Phase 10 이후로 **명시 이월**. Alpha 기간에는 query DTO 계약 초안 합의만 한다.

> **이력:** 2026-07-07 판의 "권장 착수 순서"는 위 2026-07-09 합의 순서(Phase 9 → 10 → 8B 튜닝)로 대체됨.

---

## Open Beta 로드맵 (Alpha 이후)

Alpha(Pull + for/against, 내부)에서 Open Beta(외부)로 가려면 **새 기능 축**이 붙습니다.
번호는 [Roadmap](../Agent_Discovery_Recommendation_Roadmap.md)의 단계와 맞춥니다.

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
