# 11. Phase 8/9 로드맵 (대부분 미구현 — 8-1 rerank fallback · 8-2는 **Phase 8A 완료**)

← [개요로 돌아가기](README.md) · 관련: [08. LLM](08-llm-layer.md) ·
[03. linker](03-normalize-and-linker.md) · [10. metrics + gates](10-eval-metrics-and-gates.md)

여기부터는 **대부분 아직 구현하지 않은** 내용입니다 (예외: 8-1의 rerank **fallback**과 8-2
`fallback_used` teeth는 Phase 8A에서 착지 — 각 절에 ✅ 표시). 각 항목마다 "무엇을 추가하나 +
**기존 코드/계약이 이렇게 바뀐다**"를 명시합니다. Alpha가 자리(hook)를 예약해 둔 덕에 대부분
additive이고, 계약 struct는 대체로 안 바뀝니다.

> 마일스톤 정리: **Alpha**(7월, 내부, Pull + for/against) → **Open Beta**(8월말, 외부, Push +
> orthogonal) → **Post**. Phase 8/9는 Alpha→Open Beta 사이의 작업 단계입니다.

---

## Phase 8 — LLM rerank / stance / B2 silver judge

Alpha가 결정성을 위해 우회했던 [LLM 레이어](08-llm-layer.md)를 깨우는 단계입니다. **Phase 8A가
8-1의 rerank fallback과 8-2를 이미 착지**시켰습니다 (아래 ✅). 남은 것은 8-1의 full listwise 교체
(8B) · stance(8-3) · judge(8-4) · rich reason(8-5) · gate 필드(8-6).

### 8-1. Linker LLM rerank — ✅ **fallback은 Phase 8A 완료** (full 교체는 8B)
- **Phase 8A에서 한 것:** 기호적 gate가 실패할 때만 도는 **LLM rerank fallback**을 추가. 기호적
  3-tier를 통째로 **교체**한 게 아니라, gate 애매 시 같은 후보셋을 LLM으로 재채점하는 이음매.
  실코드: `discovery/rerank.py`(`LLMReranker`), `linker.py`(`Reranker` Protocol + `ground()` 배선).
  채택 winner는 별도 `RERANK_CONF_MIN`/`RERANK_MARGIN_MIN` gate 통과 필수. injection-safety는
  **구조적 봉쇄**로 보존(후보 텍스트=data, qid 집합 전단사 검증, gate). `GroundingResult.method`는
  `Literal["symbolic","rerank"]`로 확장, `fallback_used` 필드 신설.
- **아직 (Phase 8B):** 기호적 confidence를 **매 질의 listwise reranker로 완전 대체** + alias-aware
  tier 재도입 → `EntitySummary`/`EntitySuggestion`에 `match_kind`/aliases 투영(memory-api 계약
  협의) + 비결정 eval 전략. Phase 8A는 fallback-only라 eval을 결정적으로 유지함.

### 8-2. `fallback_used` teeth — ✅ **Phase 8A 완료**
- **한 것:** `discovery/decision_log.py` `_logged_grounding()`의 `fallback_used=False` 하드코딩을
  `grounding.fallback_used`로 교체. rerank fallback이 grounding을 구제하면 serving 로그에 True.
- **`ambiguous_fallback_rate` 현황:** eval은 reranker를 주입하지 않아(offline default) fallback이
  eval에선 안 떠 여전히 **0.0**·baseline 불변. teeth가 실제로 붙는 건 real-anchor 코퍼스로 eval을
  reranker와 함께 돌릴 때(후속). `eval/metrics.py` `_ambiguous_fallback_rate()` 로직은 무변경(이미
  `fallback_used`를 읽음).

### 8-3. for/against stance 자유형 정규화
- **추가:** [normalize](03-normalize-and-linker.md)의 보수적 문법 파서를 **자유형 LLM
  normalizer**로 보강.
- **기존 변경:**
  - `discovery/normalize.py` — `_parse_user_stance_ref`의 엄격 문법이 자유 문장 파싱을 허용하게
    확장 (문법 파서는 fallback으로 유지 가능).
  - `UserStanceRef.confidence` — 현재 Alpha에서 항상 `None`인 필드를 LLM normalizer가 채움
    (query-side parse confidence). struct 변경 없음 (이미 forward-compat 필드).

### 8-4. B2 silver judge + judge-derived 지표
- **추가:** LLM judge가 silver 라벨(`b2_silver`) 생성. 품질 지표를 gold에서 확장.
- **기존 변경:**
  - `eval/corpus/structs.py` `GoldSource` enum은 **이미 `B1_HUMAN` / `B2_SILVER` / `SYNTHETIC`를
    정의**하고 있음 (또 하나의 예약된 hook). Phase 6은 `synthetic`만 *커밋*할 뿐 — Phase 8은 enum을
    바꾸는 게 아니라 그 tier로 라벨을 **생성·커밋**함 (B1=double-review human gold=유일한 품질-주장
    가능 tier, B2=pinned judge version의 LLM silver).
  - **핵심 계약: `eval gate`는 절대 live judge를 호출하지 않음.** B2 silver는 **persist**되고,
    게이트는 persisted 라벨을 읽음. [Phase 7](10-eval-metrics-and-gates.md)에서 세운 ratchet
    baseline이 B2 silver가 꽂히는 분모가 됨.
  - `eval/metrics.py` — judge-derived 품질 지표 추가 (report-only 또는 새 ratchet). safety/exposure
    hard gate는 **여전히 결정적 gold만** (확률적 judge에 안 올라탐).
  - judge 버전이 ratchet 분모의 일부가 됨 (judge 업그레이드 = baseline 재설정 사유).

### 8-5. 풍부한 reason (serving)
- **기존 변경:** `discovery/serving.py` `_reason()` — 결정적 feature 문자열을 per-need LLM
  explanation으로 교체/보강. `RecommendationItem.reasons`는 list라 schema 변경 없음.

### 8-6. Open Beta 전 게이트 필드
- **기존 변경:** `discovery/structs/eligibility.py` `Eligibility` — `privacy_clearance` /
  `safety_verdict` 필드 추가 (현재 `discoverable`만 활성). gate(③)의 `_need_agnostic_drop`에
  새 drop 사유 추가 가능. safety는 타 팀 위임, privacy는 deferred였음.

---

## Phase 9 — eval을 CI 스텝으로

- **추가:** [`eval gate`](10-eval-metrics-and-gates.md)를 CI 파이프라인의 게이트 스텝으로 배선.
  모든 PR에서 ratchet 강제, baseline 갱신은 PR 리뷰로.
- **기존 변경:**
  - 코드 변경은 최소 — `eval gate`가 이미 exit code 계약을 갖고 있음 (0/non-zero). CI yaml/workflow
    추가가 주 작업.
  - baseline.json 갱신이 리뷰 대상 diff가 됨 (이미 diff-stable JSON).
  - real anchor backfill(`build-anchors`)이 CI 이전에 선행돼야 "teeth" 있는 게이트가 됨
    (`manual-seed` → 실제 memory-api 캡처).

---

## Open Beta 및 그 이후 (Phase 8/9 너머)

계약 struct나 파이프라인 골격이 더 크게 바뀌는 것들 — 참고용:

- **Push 모드** — Alpha에선 shadow. `SilenceView`가 실제 push-silence 판정을 수행하게 됨.
- **orthogonal 서빙** — Alpha stance는 for/against까지. orthogonal은 Open Beta 조건부 서빙.
- **real provider 교체** — `MemoryEdgeProvider`/`PersonaProvider`/`EligibilityProvider`의 mock을
  real HTTP로. 이음매가 Protocol이라 **배선 변경**으로 끝남 ([02](02-provider-boundary.md),
  [07](07-composition-api-cli.md)). 단 memory-api `/personal/groundings`는 maturity 등을 안 줘서
  translation layer 또는 전용 discovery 엔드포인트 필요.
- **OpeBlock 채움** — `DecisionLogRecord.ope`가 Alpha에선 빈 채 형태만. Open Beta OPE replay가
  propensity/action_set/reward_proxy를 채움 (**schema 변경 없이**).
- **favorite/preference 신호** — Alpha reserved slot(no-op). personalization(≠expertise)로
  UserPreferenceProvider(bourbon-api 출처 예상) 신설, negative-first, tie-break only, gate 우회
  금지.
- **reputation/contribution** — 품질 보강이지 popularity prior 금지. safety=gate,
  contribution=need-조건부, reputation=tiebreaker.
- **disentangled 임베딩** — 연구 베팅 아니라 anchor 파티션 → stance-only embed → projection layer
  사다리. Post 단계.

---

**요점:** Phase 8A는 Alpha가 예약해 둔 `method="rerank"` / `fallback_used` 자리를 실제 serving
경로에서 활성화했습니다. 남은 `UserStanceRef.confidence`, `OpeBlock`, b1/b2 gold tier, eligibility
필드 같은 hook 덕분에 Phase 8/9 변경의 대부분은 여전히 **additive**로 흡수됩니다. 계약 struct와
Protocol 이음매를 먼저 얼려둔 전략의 배당금입니다.
