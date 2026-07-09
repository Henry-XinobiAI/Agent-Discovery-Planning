# 11. Phase 8–10 로드맵 (대부분 미구현 — 8-1 rerank fallback · 8-2는 **Phase 8A 완료**)

← [개요로 돌아가기](README.md) · 관련: [08. LLM](08-llm-layer.md) ·
[03. linker](03-normalize-and-linker.md) · [10. metrics + gates](10-eval-metrics-and-gates.md)

여기부터는 **대부분 아직 구현하지 않은** 내용입니다 (예외: 8-1의 rerank **fallback**과 8-2
`fallback_used` teeth는 Phase 8A에서 착지 — 각 절에 ✅ 표시). 각 항목마다 "무엇을 추가하나 +
**기존 코드/계약이 이렇게 바뀐다**"를 명시합니다. Alpha가 자리(hook)를 예약해 둔 덕에 대부분
additive이고, 계약 struct는 대체로 안 바뀝니다.

> 마일스톤 정리: **Alpha**(7월, 내부, Pull + for/against) → **Open Beta**(8월말, 외부, Push +
> orthogonal) → **Post**. Phase 8/9는 Alpha→Open Beta 사이의 품질·평가 작업 단계이고,
> **Phase 10(real edge 통합)이 user-facing Alpha 성립의 마지막 조각**입니다 (2026-07-07 승격).

---

## Phase 8 — LLM rerank / stance / B2 silver judge

Alpha가 결정성을 위해 우회했던 [LLM 레이어](08-llm-layer.md)를 깨우는 단계입니다. **Phase 8A가
8-1의 rerank fallback과 8-2를 이미 착지**시켰습니다 (아래 ✅). 남은 것은 **8B — 그라운딩 폴백
사다리(expansion + proxy; 아래 재설계)** · stance(8-3) · judge(8-4) · rich reason(8-5) ·
gate 필드(8-6).

### 8-1. Linker LLM rerank — ✅ **fallback(rung ②)은 Phase 8A 완료** · 나머지 사다리 = 재정의된 8B
- **Phase 8A에서 한 것:** 기호적 gate가 실패할 때만 도는 **LLM rerank fallback**을 추가. 기호적
  3-tier를 통째로 **교체**한 게 아니라, gate 애매 시 같은 후보셋을 LLM으로 재채점하는 이음매.
  실코드: `discovery/rerank.py`(`LLMReranker`), `linker.py`(`Reranker` Protocol + `ground()` 배선).
  채택 winner는 별도 `RERANK_CONF_MIN`/`RERANK_MARGIN_MIN` gate 통과 필수. injection-safety는
  **구조적 봉쇄**로 보존(후보 텍스트=data, qid 집합 전단사 검증, gate). `GroundingResult.method`는
  `Literal["symbolic","rerank"]`로 확장, `fallback_used` 필드 신설.
- **원래 8B — 폐기(2026-07-08 재설계):** "기호적 confidence를 매 질의 listwise reranker로 **완전
  대체**"하려던 원안은 폐기됐다. 정밀 코어(결정성·popularity-free·감사가능성)를 버리는 비용이 raw
  quality 이득보다 크고, 그 이득은 더 값싸게 재현 가능하다(memory-api recall + expansion). alias /
  cross-language recall은 discovery confidence tier가 아니라 **memory-api search 개선**의 몫으로 이동.
- **재정의된 8B — 그라운딩 폴백 사다리:** 정밀 코어는 영구 유지하고, LLM 작업을 **게이트·신호가 걸린
  폴백 rung**으로만 한정한다: rung ② rerank(8A 완료) → **rung ③ query expansion** → **rung ④ proxy**.
  eval 결정성 유지(폴백 컴포넌트는 gold 게이트에 미주입 → `baseline.json` byte-identical); 품질은
  주입·비결정 stratum에서만 측정. 실행 계획(트랙 1–4)·미해결 결정(rung 라우팅·proxy 선택방식·proxy
  응답 노출)은 코드 repo `tasks/todo.md`.
  - **범위 경계 (섞지 말 것):** **8B = discovery 폴백 사다리 _구현만_**(rerank/expansion/proxy).
    **memory-api search relevance/alias/cross-language 개선 + 그 뒤 real-anchor 재측정은 8B의 _선행
    dependency_이지 8B의 일부가 아니다** — 소유는 memory-api 팀이고 discovery 8B는 그 작업을 책임지지
    않는다. 아래 "먼저" 표현은 우선순위가 아니라 **의존성**을 뜻한다(둘을 섞으면 discovery 8B가
    memory-api 작업까지 지는 것처럼 오독됨).
- **그라운딩 모드 재설계 (2026-07-08 결정 · 상세는 별도 문서):** grounding을 **search-only 정밀
  코어**(exact-label winner만 채택 — suggest는 grounding에서 제거, autocomplete 전용) + **폴백
  사다리**로 재정의하기로 함: rerank(=disambiguation, 후보에 정답 有) → **query expansion**(=recall
  회복; LLM은 검색어만 제안, 최종 QID는 `/knowledge/entities` 재검색+gate에서) → **proxy**(=best-effort
  대체, 별도 method/gate·항상 신호). 각 계층이 별도 `method`/`grounding_mode`. **memory-api search
  relevance/alias/cross-language 개선을 먼저**(최고 ROI — alias는 이미 검색되나 흔한 이름은 label^3에
  밀림). 원래 8B가 노렸던 alias-aware/listwise 품질은 이 사다리 + memory-api recall로 흡수되며
  **symbolic 전면 교체는 하지 않는다**. **rung 라우팅(잠정, 코드 repo 확정): exact 동점→rerank,
  exact 0(miss)→expansion.** proxy는 이번 사이클 스코프(opt-in·항상 신호). 전체 설계·근거·데이터:
  `findings-real-anchor-grounding-ties.md` → "Recommended behavior".

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

## Phase 10 — real edge 통합 (user-facing Alpha 성립) — **2026-07-07 신설**

Roadmap §10 Alpha 단계 2(agent-topic edge projection)·4(maturity gate)에 대응합니다. Phase
8/9가 전부 품질·평가 작업인 반면, 배포된 Pull API가 grounding 후 후보 단계에서 503을 반환하는
현 상태를 해소하는 **유일한 성립 작업**이라 별도 phase로 승격했습니다. (이 문서의 이전 판은
real provider 교체를 아래 "Open Beta 및 그 이후"에 두어 Roadmap의 Alpha 표와 모순이었음 —
지금 정정. real edge를 OB로 미루면 어차피 OB의 크리티컬 패스로 되돌아올 뿐입니다.)

- **최소 범위** — mock 3종을 전부 교체하지 않습니다:

  | Provider | Alpha 처리 | 근거 |
  |---|---|---|
  | `MemoryEdgeProvider` | **real HTTP 교체 — 유일 필수** | 후보가 나오는 유일한 소스 |
  | `EligibilityProvider` | `discoverable=true` 가정의 얇은 stub | 2026-07-03 rec-signal 계약: visibility 보류 → agent-rec true 가정 |
  | `PersonaProvider` | NullProvider 유지 | `persona=None` 합법 · Alpha ranking no-op |

- **기존 변경:** Protocol seam([02](02-provider-boundary.md)) 덕에 코드 작업은 **real
  `MemoryEdgeProvider` 구현 1개 + deployed-only `AllowAllEligibilityProvider`(가칭) stub +
  composition root([07](07-composition-api-cli.md)) 교체**로 유계. eligibility stub이 왜
  필수인가: 현 배포 graph는 `UnavailableEligibilityProvider`(hard-required → 503)라 real
  edge만 붙이면 503이 후보 단계에서 gate 단계로 옮겨갈 뿐임. eval의 mock eligibility는
  import-isolation(serving graph의 `eval/` import 금지) 때문에 재사용 불가 —
  `discovery/providers/`에 얇은 stub을 신설하고, decision log의 `ProviderVersions`도
  edge·eligibility 둘 다 `unavailable@v0`에서 real/stub 표기로 갱신(출처 정직성).
  Phase 2의 `HttpKnowledgeEntityProvider`가 real HTTP provider의 템플릿.
- **선행(진짜 크리티컬 패스):** memory-api와 edge/maturity 계약 협의. `/personal/groundings`는
  maturity 등을 안 주므로 **translation layer 또는 전용 discovery 엔드포인트**가 필요. 출발점 =
  2026-07-03 rec-signal 계약(owner_id-only, agent_id는 bourbon-api `personal_agent_id` 파생).
  **핵심 안건 = maturity 소유**(memory-api가 제공 vs discovery측 계산). 계약 협의는 리드타임이
  기니(rec-signal 계약도 한 라운드) 코드 작업과 무관하게 즉시 시작.
- **8B/8-4와의 순서:** 후보가 mock인 상태에서 linker 품질(8B)·judge 분모(8-4)를 올리는 것은
  end-to-end 레버리지가 낮음 — **real edge 이후**로 미룸.
- **Push shadow(로드맵 단계 7):** Phase 10 이후로 **명시 이월**. Alpha 기간에는 query DTO 계약
  초안 합의만 한다.

### 권장 착수 순서 (2026-07-07 기준)

1. **real-anchor backfill** (`build-anchors`) — memory-api dev 배포로 언블록. Phase 9 / 8-4 /
   8A `ambiguous_fallback_rate` teeth의 공통 선행. 현 ratchet은 전부 천장(top1/top3=1.0,
   fallback=0.0)이라 real anchor + ambiguous 층이 들어와야 게이트에 변별력이 생김.
2. **Phase 9** (eval gate → CI) — 얇음(yaml 위주), 이후 작업의 안전망.
3. **Phase 10 계약 협의 킥오프** — 1·2와 병행 시작, 계약 확정 시 구현.
4. 8-3 / 8-5 — 독립·얇음, 틈새에.
5. 8-4 → 8B — real anchor/edge 이후.

> **2026-07-08 보강:** real-anchor backfill(1)은 real 앵커가 **동음이의 exact-label 동점**을
> 드러냄을 전제로 해야 함(오프라인에서 7/25만 ground — 상세 `findings-real-anchor-grounding-ties.md`).
> 실질 선행 2가지: **(a) discovery search-only 그라운딩 정렬**(정밀 코어·결정적·작음; 코드 repo
> `tasks/todo.md`), **(b) memory-api search relevance 개선**(최고 ROI). 이후 real-anchor 재측정 →
> 남는 하드 케이스만 LLM 폴백 사다리(rerank→expansion→proxy).

---

## Open Beta 및 그 이후 (Phase 8–10 너머)

계약 struct나 파이프라인 골격이 더 크게 바뀌는 것들 — 참고용:

- **Push 모드** — Alpha에선 shadow. `SilenceView`가 실제 push-silence 판정을 수행하게 됨.
- **orthogonal 서빙** — Alpha stance는 for/against까지. orthogonal은 Open Beta 조건부 서빙.
- **real provider 완성** — edge는 **Phase 10으로 승격**(위 참조). 남는 것은
  `EligibilityProvider`(실제 discoverability/safety 신호)와 `PersonaProvider`의 real 교체.
  이음매가 Protocol이라 **배선 변경**으로 끝남 ([02](02-provider-boundary.md),
  [07](07-composition-api-cli.md)).
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
Protocol 이음매를 먼저 얼려둔 전략의 배당금입니다. 그리고 그 배당금의 마지막 수취처가
**Phase 10**입니다 — user-facing Alpha를 성립시키는 real edge 교체가 provider 구현 1개 +
배선으로 끝나는 것은 seam을 먼저 얼려뒀기 때문입니다.
