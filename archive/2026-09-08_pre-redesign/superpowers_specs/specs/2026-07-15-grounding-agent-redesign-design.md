# Grounding Agent 재설계 — 설계 spec

- **상태:** 설계 초안 — **방향 승인**, 구현 세부 fleshing 대기. 전 설계 결정(D1–D7) 잠금.
- **작성:** 2026-07-15
- **영향 범위:** discovery 모듈 ① linker (grounding) 전면 재설계. retrieval ②~serving ⑤는 계약 불변. **decision-log ⑥은 예외** — grounding trajectory block additive 확장(§7).
- **문서 반영(승인 후):** `impl/03-normalize-and-linker.md` 재작성 · `impl/11-forward-roadmap.md` §8-7 재작성 + Phase 10 선행 #2(`_score` 투영 ask) 제거 · `impl/00-pipeline-io-reference.md` ① 갱신.

---

## 1. 문제 / 동기

- 기존 grounding = **symbolic 정밀 코어**(exact-label match + margin gate). 정상 경로는 결정적·LLM-free이고, LLM은 폴백 rung(rerank/expansion/substitution)에서만.
- **다국어 인덱스 fix로 recall(MISS)은 대체로 해소**됐고, 남은 지배적 실패는 **identical-label homonym TIE**(같은 label "Python"을 언어·뱀이 공유; 재측정 GROUND 7 / **TIE 10** / MISS 3). symbolic은 둘 다 confidence 1.0 → margin 0 → tie를 원리적으로 못 깬다.
- **memory-api가 `/knowledge/entities` 검색에서 `context=`를 제거**(현 `POST /knowledge/entities/search`는 `queries[]`/`instance_of`/`fanout`만; `5530192` 확인). → backend rank로 sense를 boost할 방법이 없어졌고, 링커가 backend 순서에 기댈 근거도 사라졌다.
- 결론: **context(최근 대화)를 읽고 sense를 고르는 주체가 LLM이어야 한다.** 이전에 검토한 (a) memory-api `context=`/`_score` 투영 접근은 **완전 폐기**(엔드포인트에서 `context=` 사라짐 + cross-team 의존 회피).

## 2. 결정 — Agentic LLM-primary Grounding

topic + 최근 대화 context를 받아, **도구를 쓰는 LLM 에이전트**(bounded ReAct 루프)가 `/knowledge/*`를 검색·탐색해 **최적 QID를 고르거나 abstain**한다.

- 이것은 "symbolic 정밀 코어가 영구 primary"라는 기존 불변식을 **의식적으로 대체**하는 결정이다(구 8B "listwise full replacement" 폐기 결정을, 다른 근거 = context= 제거 + tool-use + bounded loop + membership guard 로 되살림). **정직하게 문서화한다.**
- symbolic 코어는 **죽지 않고 "결정적 offline/eval 폴백 + (선택) unambiguous short-circuit"으로 강등**된다 → baseline byte-identical + CI 커버리지 유지.

✅ **D1 — context 유무로 분기 (리뷰 반영, 완화).** "항상 agentic"은 context 없을 때 새 정보 없이 비용·latency·비결정성만 늘리므로 완화한다:

| context_messages | symbolic 결과 | 동작 |
|------------------|---------------|------|
| **있음** | (무관) | **agentic primary** — 유일 exact-label이어도 context 대비 sense 검증, 안 맞으면 재확장 |
| **없음/비어있음** | unique exact | **symbolic adopt** (결정적·저비용·eval 커버 가능) |
| **없음/비어있음** | tie / recall miss | ✅ **기본 abstain(침묵)** (보수안, 리뷰 반영) — agentic은 이 케이스 **report-only만** |

근거: 동음이의어는 유일 exact-label이어도 전혀 다른 entity일 수 있으나, **그걸 판별할 새 정보(context)가 없으면 LLM도 못 가린다.** context 있을 때만 agent가 값을 더한다. context 없는 tie/miss에서 agent가 상세/importance로 "dominant sense"를 고르면 **popularity/default-sense 추천으로 회귀**(popularity prior 금지 원칙 위반) → 그래서 **기본 abstain**(보수안). → 이로써 "context 없으면 dormant / 항상 agentic" 충돌 해소. symbolic은 (a) offline/eval 결정적 폴백 + (b) **online context-absent unique-exact 채택 경로**로 남는다(후자는 결정적이라 CI가 커버).

## 3. 입력 계약 — `Query.context_messages`

moderator가 `/recommend`에 **최근 대화 히스토리**를 실어 보낸다. bourbon-agent `TaskPayload.context_messages: list[ContextMessage]`와 **같은 정보**를 나른다(`bourbon-agent/bourbon_agent/structs/context.py:207`).

✅ **D2 — wire 파리티 + 내부 projection (리뷰 반영, 2-layer).** 두 층으로 분리해 파리티의 편의와 표면 최소화를 동시에:
- **외부 요청(wire):** `Query.context_messages`는 bourbon-agent `ContextMessage` **파리티**로 받는다 — moderator가 가진 걸 평탄화 없이 전달, 직렬화 마찰 0. (import 아닌 **벤더링 미러** + drift 방지 **parity guard 테스트**.)
- **내부 grounding DTO:** 수신 즉시 최소 `GroundingContextMessage{speaker(sender_type), time(created_at), text, system_event?}`로 **projection**. **LLM에는 이 projection만** 전달. → attachments/artifacts/publish-preview 같은 무관 타입이 바뀌어도 grounding 계약·LLM 입력은 안 흔들림.
- **PII/masking = projection 지점에서** 건다(단일 chokepoint). "어디까지 grounding LLM에 보내나"를 이 projection이 정의.
- 즉 wire=파리티(무거움 수용), 내부=lean(표면 최소). 리뷰 지적("attachments/artifacts까지 미러하면 안 쓰는 타입 변화에도 Discovery 계약이 흔들림") 해소.

✅ **D3 — 컨텍스트 예산 느슨하게 시작.** 우선 과하게 제한하지 않고(관대한 recency window/토큰) 넣어 품질 먼저 확인, **비용효율은 추후 개선**(예산 튜닝은 provisional). 단 bounded loop(§6-3)로 결정적 종료는 보장.

`Query`에 추가(additive): `context_messages: list[ContextMessage] | None = None` (없으면 context 레버 dormant → topic만으로 grounding).

## 4. 도구 계약 (live openapi `:8081` 확인)

discovery가 자체 tool 정의 작성(memory SDK는 conversation-search만 노출, knowledge는 안 함). 각 tool = LLM 함수 선언 + `POST/GET` 어댑터.

| tool | Alpha | endpoint | 입력 | 반환 | 역할 |
|------|-------|----------|------|------|------|
| `search_entities` | **코어** | `POST /knowledge/entities/search` | `queries[1..16]`, `instance_of?[≤20]`, `fanout?[0..50]`, `limit?[1..100]` | `Page[EntitySummary]` | recall + 타입필터 |
| `get_entity` | **코어** | `GET /knowledge/entities/{qid}` | `qid` | `Entity`(풀 상세: 다국어 `descriptions/abstracts`, `subclass_of`, `occupations`, `aliases`, `typed_links` …) | 확정용 drill-down + 클래스 QID 도출 |
| `get_connections` | **opt-in(기본 off)** | `GET /knowledge/entities/{qid}/connections` | `qid`, `limit?` | `EntityConnections`(broader/narrower/links_out/links_in/typed_out) | 이웃 탐색 |

- `EntitySummary` 필드: `qid/source/label/description/importance/pageview/pagerank/sitelink_count/categories/instance_of/abstract`.
- **의도된 패턴:** 후보 좁힘 → `get_entity`로 `instance_of`/`subclass_of`/`occupations` 확인 → 클래스 QID 도출 → `search_entities(instance_of=[classQID])` 재검색으로 확정.
- ✅ **D4(리뷰 반영) — `get_connections`는 Alpha에서 opt-in(기본 off).** 이유: **타입 disambiguation은 `get_entity`가 이미 준다**(`instance_of`/`subclass_of`/`occupations`) → connections 없이도 sense 판별 가능. connections는 "무엇이 *관련*됐나"(links_out/in)라 rabbit-hole·latency가 크고, **MAX_CALLS=5 예산을 잠식**한다(final qid는 반드시 `get_entity` 필수 → 여유 적음: `search → get_entity A → get_entity B → search(instance_of) → get_entity final`이면 이미 5콜). enable 시에도 **≤1회 호출**로 cap하고 예산에 계상. report-only에서 이웃 탐색이 tie 해소에 필요하다고 실측되면 기본 on 전환.
- **Alpha 생략(+되돌림 트리거):** `connections/{group}`(페이징 — 배치로 충분) · `articles/search`+`articles/{qid}`(qid 선택엔 granularity 안 맞음·토큰 무거움·rabbit-hole). → report-only에서 entity-level 필드로 sense 안 갈리면 `articles/search` 재고.
- **grounding connections ≠ retrieval ② `expand_connections`:** 전자=disambiguation(어느 qid), 후자=resolved qid에 붙은 agent 수집. 별개 경로(코드/캐시 공유는 구현 판단).

## 5. 에이전트 루프

```
입력: topic, GroundingContextMessage[](projection), (settings)
loop (LLM 콜 ≤ MAX_CALLS=5):
    LLM이 tool 호출(search_entities / get_entity / get_connections) 또는 최종 응답
    tool 결과를 다음 턴에 피드백
    # 유일 exact-label 후보라도 context 대비 sense-fit을 검증(D1);
    # 안 맞으면 context 기반 다른 query expansion으로 재검색
종료:
    최종 {qid, confidence, confidence_rationale, reason, evidence_qids/supporting_observations}  또는  abstain{abstain_reason}
채택 게이트 (D5, 4중):
    ① final qid ∈ **get_entity로 observed된 qid 집합**  # membership = observed set (search/connections에서 스쳐본 qid는 불충분)
    ② (①의 정의상) final qid는 get_entity(qid) 상세를 반드시 거침
    ③ confidence ≥ GROUNDING_AGENT_CONF_MIN                    # LLM confidence floor (provisional)
    ④ reason이 observed 필드 기반 구조적 근거(evidence)를 포함  # observed-field evidence
    하나라도 실패 → GroundingFailedError (침묵)
cap 도달 시 (D6): abstain → GroundingFailedError (침묵)
```

✅ **D5 — 채택 게이트 = 4중 (리뷰 반영, 강화).** LLM self-confidence는 calibration이 약해 floor 단독으론 "본 후보 중 그럴듯한 걸 자신 있게 잘못 고르는" 케이스를 못 막는다. 그래서 **membership guard + get_entity 상세확인 + confidence floor + observed-field 기반 구조적 근거** 4중. → final pick은 반드시 `get_entity(qid)`를 거친 entity여야 하고(5콜 중 1콜 소비), reason은 실제 retrieve한 필드를 인용해야 한다(anti-hallucination/anti-injection). **margin은 추후 테스트 후 추가 결정.**

**seed + calibration (리뷰 반영):**
- `GROUNDING_AGENT_CONF_MIN` **initial seed = 0.70 (provisional)** — 값 자체가 아니라 "provisional·report-only에서 조정" 구조를 명시.
- report-only eval에서 **false-positive(잘못 채택) vs abstain(놓침) tradeoff**를 측정해 조정. **confidence는 단독 품질 지표가 아니라 gate input** 중 하나(4중의 ③).
- agent 응답 schema에 **`confidence_rationale`(왜 이 confidence인지) + abstain 시 `abstain_reason`** 포함 → 나중에 "왜 채택/abstain했나" 분석 가능(calibration 데이터).

**final response wire schema (agent의 구조적 최종 출력):**
```
GroundingAgentFinal {
  qid: str | None                       # None = abstain
  confidence: float
  confidence_rationale: str
  reason: str
  evidence_qids: list[str]              # observed set에서
  supporting_observations: list[str]    # observed 필드 인용
  abstain_reason: str | None
}
```
- **validator:** `qid is None` → `abstain_reason` 필수(그 외 evidence 무시). `qid is not None` → `evidence_qids`/`supporting_observations` 비어있지 않아야(게이트 ④). strict `extra="forbid"`(injection 봉쇄, 다른 LLM wire schema와 동형).
- **membership set 정의(D5 ①):** 최종 qid의 membership 판정 집합은 **`get_entity`로 observed된 qid 집합** 하나로 고정한다(search/connections가 반환한 qid는 후보 탐색용일 뿐, 최종 채택엔 불충분). 가장 단순하고 게이트 ②와 동치.
✅ **D6 — cap(5콜) 도달 시 abstain(침묵)** 기본. best-so-far 채택은 두지 않음(확신 미달은 침묵).

## 6. 가드레일 (필수 7)

1. **membership guard** — 최종 qid는 에이전트가 실제 검색으로 반환받은 집합 안. QID 발명·미검색 QID 금지. injection의 하드 백스톱.
2. **abstain → 침묵** — 확신 없으면 강제 pick 금지, `GroundingFailedError`. "틀린 앵커 < 침묵" 보존.
3. **bounded loop** — LLM ≤5콜 + 검색/connections fan-out 상한 → 결정적 종료.
4. **prose=data** — entity description/abstract/label(외부·공격자 영향 가능)는 user-turn JSON data, system prompt 고정. (1)이 실질 방어.
5. **결정적 offline 폴백** — LLM 미주입(eval/offline)이면 symbolic exact-label(topic) → 실패는 `GroundingFailedError`. **baseline byte-identical.**
6. **report-only 측정 = 사실상 선행(prerequisite)** — real anchor + B2/human relatedness judge(8-4). grounding에 결정적 가드가 사라지므로 유일한 회귀 신호. dormant/report-only로 **먼저 품질 측정 → 그 다음 online flag rollout**(§12 구현 순서).
7. **trajectory 로깅** — decision_log에 각 스텝(queries/instance_of/본 결과 qid들/따라간 connections) + 최종 pick + 사유. symbolic `considered` trace 대체. **이건 decision_log ⑥의 additive 확장**(grounding trajectory block) — retrieval~serving 계약은 불변이지만 decision_log는 예외.

## 7. 출력 계약 (불변)

`GroundingResult` 형태는 최대한 유지(하류 retrieval~serving~log 계약 불변):
- `qid/label/confidence/method/fallback_used/considered`.
- ✅ **D7 — `GroundingMode` enum에 `agentic` 추가.** online agentic 경로는 `agentic` emit; online context-absent unique-exact 및 offline 폴백은 `symbolic`. enum은 **추후를 위해 유지**(구 rung 값 `rerank`/`expansion`/`best_effort_substitution`는 live 경로에서 은퇴 → agent가 흡수; prune 여부는 후속).
- ✅ **`fallback_used` — agentic에선 `False` (리뷰 반영).** agentic은 폴백이 아니라 primary online 경로이므로 `fallback_used=False`로 두고 구 rung fallback 의미와 분리(정직성). symbolic 경로도 `False`.
- `considered` = **하류 호환용 요약**(기존 `GroundingResult` 필드; 에이전트가 본 최종 후보 슬라이스). `decision_log.grounding_trajectory`는 **전체 audit trace** — 둘은 요약 vs 전체 관계라 중복 아님.
- 침묵 = `GroundingFailedError` (오늘과 동일, 전파 → 422).

**trajectory 최소 schema (리뷰 반영 — decision_log ⑥ additive block):**
```
GroundingTrajectory {
  steps: [ { step_index, action: "search_entities"|"get_entity"|"get_connections",
             args, returned_qids, selected_for_followup } ],
  final_qid, final_reason, confidence, confidence_rationale,
  abstain_reason?,               # abstain일 때
  context_message_count, context_truncated,
}
```
- **로그 크기/PII 제한:** 전체 tool result를 남기지 않는다. step당 **`args` + `returned_qids` + 짧은 label/description**만(긴 abstract·본문 제외). PII는 이미 §3 projection에서 걸리므로 trajectory엔 QID/label 수준만.
- 이 block은 `impl/06`의 decision_log 계약 **additive 확장** — 기존 필드 불변, grounding trajectory 필드만 추가.

## 8. 결정성 · eval

- **online(serving):** context 有 → agentic(LLM 주입, 비결정적 → 결정적 게이트 미진입). context 無 + unique exact → **symbolic 채택(결정적, CI 커버 가능)**.
- **offline(eval/CI):** LLM 미주입 → 전 경로 symbolic 폴백 → `baseline.json` byte-identical + CI 커버리지 유지.
- **품질:** agentic 경로는 주입·비결정 **report-only stratum**에서만(real anchor + B2/human). → **8-4 judge는 "동반"이 아니라 사실상 "선행"**: 결정적 가드가 약해 judge 없이 online을 켜면 품질을 알 방법이 없다(§12 구현 순서에서 online rollout을 judge 뒤에 둠).

## 9. 문서 영향 (승인·구현 후)

- `impl/03` grounding 절 재작성(사다리 → agentic + 결정적 폴백).
- `impl/11` §8-7 재작성 + Phase 10 선행 #2(`_score` 투영 ask) **제거**; "구 8B 폐기" 노트에 "agentic 변형으로 채택(근거 상이)" 갱신.
- `impl/00` ① linker 갱신 + context forward-pointer를 "구현됨"으로.
- 폐기 기록: `context=`/`_score`/`types=`-as-search-param 접근 미채택 + 되돌림 트리거(articles 재고, 등).

## 10. Non-goals / 이월

- retrieval ②~serving ⑤ 계약 변경 없음(grounding 내부 교체만). **decision-log ⑥은 grounding trajectory block additive 확장 예외**(§7).
- Push / orthogonal / real edge(Phase 10)는 별개.
- `articles/*` 도구, `connections/{group}` 페이징 = 트리거 시 재고.

## 11. Open Decisions 요약

| # | 결정 | 상태 |
|---|------|------|
| D1 | context 유무 라우팅 | ✅ context 有→agentic / 無+unique exact→symbolic adopt / **無+tie·miss→기본 abstain(agentic report-only)** |
| D2 | context_messages 계약 | ✅ **wire 파리티 + 내부 projection** — `GroundingContextMessage`(speaker/time/text/system-event), PII는 projection에서 |
| D3 | 컨텍스트 예산 | ✅ **느슨하게 시작**, 비용효율 추후 개선 |
| D4 | `get_connections` | ✅ **opt-in(기본 off)·enable 시 ≤1콜**; grounding≠retrieval connections 분리 |
| D5 | 채택 게이트 | ✅ **4중** — membership + get_entity 상세확인 + conf floor(**seed 0.70 provisional**) + observed-field 근거; margin 추후 |
| D6 | cap 도달 시 동작 | ✅ **abstain(침묵)** |
| D7 | `GroundingMode` enum + `fallback_used` | ✅ **`agentic` 추가**, enum 유지, 구 rung 은퇴; `fallback_used`=agentic/symbolic 모두 False |

**전 결정 잠금 완료.** 남은 fleshing(구현 세부): 에이전트 시스템 프롬프트, tool JSON schema 상세, 구 rung 값 prune 여부.

## 12. 구현 순서 (리뷰 반영 — online rollout은 judge 뒤)

| T | 작업 | 비고 |
|---|------|------|
| **T1** | `ContextMessage` wire 파리티 + `GroundingContextMessage` projection 계약 (+ parity guard, PII chokepoint) | D2 |
| **T2** | tool adapters + JSON schema 3종(`search_entities`/`get_entity`/`get_connections`) | §4 |
| **T3** | agentic grounder **dormant/report-only**(online flag OFF) | 게이트 4중·membership·abstain |
| **T4** | trajectory logging (decision_log additive block) | §7 |
| **T5** | real-anchor **report-only eval + B2/human judge** (8-4) | **online 켜기 전 선행** |
| **T6** | online flag rollout | judge 통과 후 |

**다음 단계:** 방향 승인 완료 → **writing-plans로 구현 plan**(code repo `tasks/todo.md`, T1–T6 기반). 남은 구현 세부(에이전트 시스템 프롬프트 · tool JSON schema 상세 · 구 rung enum prune 여부)는 plan/구현 단계에서 확정.
