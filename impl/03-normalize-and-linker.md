# 03. normalize (ⓠ) + linker (①) — grounding

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[04. retrieval](04-retrieval.md) · [08. LLM](08-llm-layer.md)

파이프라인의 첫 두 단계. **가장 정교한 로직**이 여기(linker)에 있습니다. "real anchor = teeth"
— 진짜로 가짜로 꾸미기 어려운 유일한 스테이지입니다.

---

## ⓠ normalize (`discovery/normalize.py`)

`Query` → `NormalizedQuery`. 입력 정규화만 하고, 주제→QID는 linker의 일입니다 (관심사 분리).

### `proposition` — 유일한 stance 입력

for/against 요청은 **판단 대상 주장 문장** 하나를 싣습니다. 파싱할 문법도, 채울 하위 필드도 없습니다.

```python
if query.need_type in STANCE_NEEDS:                       # {for, against}
    if query.proposition is None or not query.proposition.strip():
        raise InvalidNeedError                            # 필수 · non-blank
    proposition = query.proposition.strip()
# depth/experience/coverage → proposition 무시, None으로 통과
```

- **자유 문장.** `"원격근무는 생산성을 높인다"` 처럼 옵니다. discovery는 이걸 **파싱하거나 의미를
  재작성하지 않고**, 양끝 공백만 제거한 canonical proposition을 judge 프롬프트의 명제·응답
  `StanceView.proposition`·로그에 **동일하게** 흘립니다. 검증은 존재·blank 두 가지뿐 — "parser지
  policy가 아니다"를 극단까지 밀어붙인 형태.
- **방향은 요청이 아니라 need가 정합니다.** `for`는 그 주장을 **지지**하는 에이전트, `against`는
  **반대**하는 에이전트. 유저의 기준 stance를 받아 상대적으로 계산하던 구조가 사라졌으므로 neutral
  같은 미정의 방향도 없습니다.
- 다른 need에 stray `proposition`이 와도 무시(에러 아님)하고 `NormalizedQuery.proposition=None`.

### `normalize_query`는 sync 하나뿐

문법이 없어졌으므로 LLM 폴백이 붙을 자리도 없습니다. `normalize_query()`가 **유일한 정본이고 sync**입니다
(`eval/corpus/structs.py`의 sync `@model_validator`가 이걸 부르므로 async화 불가). `normalize_query_async`
sibling은 **존재하지 않습니다**.

> **폐기 기록 (Phase 8-3).** 한때 반구조 문법 `"axis=…; dir=…; text=…"` → `UserStanceRef{axis, dir, text,
> confidence}` 파서와, 그 파싱이 실패할 때만 도는 LLM stance normalizer(`LLMStanceNormalizer`,
> `stance_normalize.py`, `NormalizeSettings.STANCE_NORMALIZER_ENABLED`)가 있었습니다. 구현·머지까지 갔으나
> stance 재설계에서 요청 모델 자체가 절대 verdict 모델로 바뀌며 **문법·타입·normalizer·플래그·async
> sibling이 전부 제거**됐습니다. 정규화할 자유형 stance가 더는 없기 때문입니다 — 남은 자유 텍스트인
> proposition은 *해석* 대상이 아니라 judge에게 넘길 *명제*입니다.

### 대화 맥락 투영 (Phase 8-7) — agentic grounder 입력

normalize는 proposition 검증 외에 **grounding용 대화 맥락**도 투영합니다. `Query.context_messages`(최근 대화 턴)를
`NormalizedQuery.grounding_context`(lean projection)로 옮기되 **tri-state**로 표현 — 이게 linker의 D1 라우팅
(아래 "agentic grounder" 절)을 결정합니다.

- `context_messages`가 **없음** → `grounding_context = None`(context 미공급 → symbolic 경로).
- **있고 usable text가 있음** → `grounding_context = 투영된 lean 대화`(non-empty → agentic primary).
- **공급됐으나 blank/attachment-only** → `grounding_context = []`(usable text 0 → terminal, symbolic 부활 안 함).

`bool(query.context_messages)`가 공급 여부의 **단일 소스**라 별도 bool을 두지 않으며, `grounding_context_truncated`는
context cap(`GROUNDING_CONTEXT_MAX_MESSAGES`=30)에서 오래된 턴이 잘렸는지를 나른다. **raw wire 메시지는 여기서
drop** — 파이프라인 안으로는 lean projection만 들어갑니다(원문은 audit/PII 표면 최소화).

---

## ① linker (`discovery/linker.py`) — 주제 텍스트 → QID 하나

**기호적 우선 경로** (Phase 4). popularity 없음. 기호적 gate 통과가 정상 경로 — LLM은 gate가
애매해서 실패할 때만 rerank **fallback**으로 호출됩니다 (Phase 8A, [08 LLM](08-llm-layer.md)).

> **두 모드 (Phase 8-7 재설계):** module ①은 **symbolic**(기본·아래 전부 서술)과 **agentic**(구현 완료·기본 OFF)
> 두 grounder를 갖습니다. `GROUNDING_AGENT_ENABLED`가 OFF인 **현 기본 배포**에선 아래 symbolic 정밀 코어 +
> rerank/expansion/substitution 사다리가 그대로 동작합니다. ON이면 agentic grounder가 primary가 되고 이 사다리는
> **은퇴**하며, symbolic은 결정적 offline/eval 폴백 + context-absent unique-exact 채택으로 강등됩니다 — 아래
> "agentic grounder (Phase 8-7 재설계)" 절 참조.

### 흐름

```
search_candidates  (search-only recall; /knowledge/entities)
  → _to_candidates (qid로 dedupe, provider 순서 보존)
  → _score (기호적 label-match confidence, confidence-desc 정렬)
  → margin 계산
  → adoption gate (top이 exact-label match AND margin ≥ MIN)
  → 통과: GroundingResult / 실패: GroundingFailedError
```

### (1) 후보 생성 — search-only recall
```python
summaries = await self._knowledge.search_candidates(topic_text, limit=limit)
```
`search_candidates`(`POST /knowledge/entities/search`, alias-aware)만 recall에 쓴다 (멀티-쿼리 recall이
필요한 rung은 `search_entities`). 구 `suggest`(autocomplete 전용)는 memory-api가 라우트를 삭제해(#87)
discovery에서도 제거됨 — grounding recall과 무관. 후보는 qid로 dedupe하며 provider(first-appearance)
순서를 보존해 confidence 동점 시 결정적 tie-break으로 쓴다.

### (2) confidence — 기호적 binary
```python
_CONF_EXACT_LABEL = 1.0   # 정규화 label == query
_CONF_NON_EXACT   = 0.55  # exact-label match가 아닌 backend search hit
```
- `_norm` = `strip().casefold()` (순서·공백 무관 비교).
- **popularity 신호 절대 안 씀**: `importance`/`pageview`/`pagerank`가 선택을 조종하지
  않음 → 앵커 선택이 popularity prior를 물려받지 않음.
- alias/cross-language recall은 search backend의 몫이지 여기의 별도 confidence tier가 아님
  (`EntitySummary` 투영에 aliases 없음). 더 세밀한 tier는 후속 `match_kind` 투영 / LLM 폴백에서 재도입(memory-api recall 개선이 선행).
- **injection-safe by construction**: 기호적 경로에서 후보 텍스트는 오직 *비교*(정규화 문자열 동등)만
  되고 절대 해석되지 않음 → 적대적 label이 제어 흐름을 못 바꿈. Phase 8A rerank fallback도 이를
  **구조적으로 봉쇄**함 — 후보 텍스트는 data(고정 system 프롬프트·user turn JSON), 응답은 후보 qid
  집합에 전단사 검증, 채택 winner는 여전히 gate 통과 필수.

### (3) margin — 애매함 판정
```python
margin = top.confidence if len(scored) == 1 else top.confidence - scored[1].confidence
```
- 후보 1개면 `confidence` 자체, 2개 이상이면 `top1 − top2`.
- **full 정렬 집합 기준**으로 계산 (pool cap이 runner-up을 숨기지 못하게).
- `LINKER_CANDIDATE_LIMIT ge=2`로 floor — provider를 이 limit으로 쿼리하므로, 더 작으면
  runner-up이 fetch도 되기 전에 잘려서 애매한 쌍이 통과할 수 있음.

### (4) adoption gate — exact-label winner 필수
```python
LINKER_MARGIN_MIN = 0.15   # top1-top2 gap
if top.confidence != _CONF_EXACT_LABEL or margin < LINKER_MARGIN_MIN:
    raise GroundingFailedError(...)  # "grounding 0"
```
- **채택은 유일 exact-label match만**: top 후보가 exact-label hit(confidence == 1.0)이라야 하고
  margin gate도 통과해야 한다. non-exact top은 절대 symbolic 채택 안 됨(evidence/trace·rerank 입력일 뿐);
  exact 동음이의(homonym tie) 2개+는 margin이 0으로 무너져 실패. 이로써 단일 non-exact `0.55`가
  single-candidate margin(=자기 confidence 0.55 ≥ 0.15)으로 통과하던 구멍을 닫는다.
- `LINKER_CONF_MIN`(구 절대 confidence floor)은 폐기 — exact는 항상 1.0이라 floor가 무의미. `LINKER_MARGIN_MIN`
  seed는 memory-api `Grounder`(`GROUNDING_MIN_MARGIN`)에서 빌려옴, **provisional**(eval ratchet 대상). 학습 weight 아님.
- 후보 자체가 0개여도 `GroundingFailedError`.
- `GroundingFailedError`는 `considered`(qid, confidence 쌍)를 담아서 decision log가 "왜 실패했나"를
  기록 가능하게 함.

### 산출물
```python
class GroundingResult:
    qid / label / confidence / margin
    method: GroundingMode   # Literal["symbolic","agentic","rerank","expansion","best_effort_substitution"]
    fallback_used: bool     # 폴백 rung(rerank/expansion/substitution)이 구제하면 True (symbolic·agentic은 False)
    considered: list[ScoredCandidate]   # confidence-desc, 로그용
    # ↓ 폴백 rung이 채우는 출처 필드 (symbolic 채택이면 전부 None)
    original_topic: str | None          # expansion·substitution이 원 주제를 보존
    expanded_query: str | None          # expansion에서 winner를 띄운 검색어
    substitute_anchor_qid: str | None   # substitution이 고른 대체 QID
    substitution_reason: str | None     # substitution의 필수 사유
    trajectory: GroundingTrajectory | None  # agentic 채택 시 tool-스텝 trace, 그 외 None
```
- **`method`가 곧 모드**입니다 — 별도 `grounding_mode` 필드는 없음. 침묵은 결과 struct가 아니라
  `GroundingFailedError`로 표현.

---

## grounding 폴백 사다리 (rung ②–④) — 구현 완료

위의 기호적 채택이 사다리의 **rung ①**입니다. 정밀 코어가 후보를 확정하지 못하면(동음이의 동점 또는
recall miss), 점점 best-effort해지는 **LLM rung을 한 칸씩** 올라갑니다. 각 rung은 **자기 gate와
신호(`method`/`fallback_used`)** 를 갖고, 어떤 rung도 구제하지 못하면 `GroundingFailedError`(= 침묵)로
끝납니다. **(이 사다리는 agent OFF 기본 배포의 경로입니다** — `GROUNDING_AGENT_ENABLED` ON이면 아래 "agentic
grounder" 절대로 은퇴하고, 정밀 코어는 결정적 offline/eval 폴백 + context-absent 채택으로만 남습니다.)

```
symbolic ① → rerank ② → expansion ③ → substitution ④ → 침묵
```

### 어느 rung으로 갈지 — Decision A (exact-label 후보 수로 분기)

기호적 채택이 실패하면 `Linker.ground()`가 **exact-label 후보 개수(`n_exact`)** 로 다음 rung을 고릅니다.

| 상황 | 분기 | 이유 |
|---|---|---|
| exact 1개 · margin 통과 | **rung ① 채택** (`method="symbolic"`) | 정상 경로 |
| exact 1개 · margin 실패 | **종료(침묵) — 대체 안 함** | 유일 정답이 margin을 못 내면 "애매"가 아니라 "확신 부족"이라, 억지 대체는 오히려 해로움 |
| exact ≥2개 (동음이의 동점) | **rung ② rerank** | 원 주제 exact-label 후보가 *여럿* → 같은 풀을 재정렬해 하나를 고름 |
| exact 0개 (recall miss) | **rung ③ expansion** | 원 주제 exact-label 후보가 *없음* → 검색어를 넓혀 exact-label 후보를 다시 찾음 |
| rung ②·③가 gate 실패 | **rung ④ substitution → 그래도 실패면 침묵** | 마지막으로 근접 대체 시도, 안 되면 원래 실패를 raise |

핵심은 **"원 주제 exact-label 후보가 여럿이라 못 고르나(≥2 → rerank) / 아예 없나(0 → expansion)"** 라는 서로 다른 실패를 서로 다른 rung으로
보내는 것입니다. 그리고 **exact 1개인데 margin 실패는 terminal**이라 사다리를 타지 않습니다.

실제 제어 흐름 (`discovery/linker.py`, `Linker.ground()`):
```python
if n_exact == 1:
    if _margin(scored) >= LINKER_MARGIN_MIN:
        return _adopt(scored, method="symbolic", fallback_used=False)
    raise _grounding_failed(..., error=GroundingAmbiguousError)  # 유일 exact + margin 실패 = 종료
                                          # (사다리 안 탐) · runner-up이 근접 = 증명된 모호성(C4-7)
if n_exact >= 2:
    return await self._rerank(...)        # 동음이의 → rung ②
return await self._expand(...)            # recall miss (n_exact == 0) → rung ③
```
rerank·expansion의 **모든 비채택 경로**는 침묵하기 전에 `_substitute_or_raise(...)`(rung ④)를 거칩니다.

### rung ② rerank — 동음이의 정리 · **serving 상시 ON**
- **언제:** exact-label이 2개+로 margin이 0에 무너질 때.
- **무엇을:** LLM이 **같은 후보 풀**을 재채점해 하나를 고름(recall을 늘리는 게 아니라 *정리*). 채택은
  별도 `RERANK_CONF_MIN`(0.50)/`RERANK_MARGIN_MIN`(0.15) gate 통과 필수.
- **활성화:** flag 없음 — composition root가 `LLMReranker()`를 **항상** 주입 (Phase 8A에서 착지).
- **신호:** `method="rerank"`, `fallback_used=True`.
- **injection-safe:** 후보 텍스트=data, 응답은 후보 qid 집합에 전단사 검증, winner는 여전히 gate 통과 필수.
- **맥락 한계(context-free):** rerank는 `topic_text` + 후보만 보고 **dominant sense로 확정**한다(예: `Python`→
  언어). 사용자의 국소 의도와 다를 수 있음(근거: [findings](findings-real-anchor-grounding-ties.md) Spike 2). 이
  한계를 실제로 해소하는 것이 **agentic grounder(Phase 8-7, 아래 절)** — 대화 맥락을 읽어 sense를 고른다. rerank는
  agent OFF 기본 배포의 동음이의 rung으로 남는다.

> **폐기 노트 (2026-07-15):** 한때 계획한 "memory-api `context=`(prose bias)·`types=` 검색 배포 → 링커 채택계약을
> context-반영 backend 순서 동점깨기로 변경" 접근은, memory-api가 검색 `context=`를 **제거**하며 폐기됐다. 동음이의
> disambiguation은 이제 **대화-context를 읽는 agentic grounder**가 담당한다 (아래 절 · [11 §8-7](11-forward-roadmap.md)).

### rung ③ expansion — recall miss 회복 · **opt-in, 기본 OFF**
- **언제:** exact-label 후보가 0개(검색 결과에 원 주제와 exact-label로 채택 가능한 후보가 없음).
- **무엇을:** LLM이 **대체 검색어만** 제안(최대 5개; **QID는 절대 제안 안 함**) → linker가 그 검색어로
  `/knowledge/entities`를 재검색해 풀을 넓힘 → **원 주제의 exact-label gate를 넓힌 풀에 다시 적용**.
  즉 최종 QID는 여전히 검색+기호적 gate가 정하고, LLM은 recall만 돕니다.
- **활성화:** `EXPANSION_ENABLED` (기본 **False**). composition root에서만 주입.
- **신호:** `method="expansion"`, `fallback_used=True`, `original_topic`=원 주제,
  `expanded_query`=winner를 띄운 검색어.

### rung ④ best-effort substitution — 침묵 직전 대체 · **opt-in, 기본 OFF**
- **언제:** rerank②·expansion③이 gate를 못 넘어 원래대로면 침묵할 자리.
- **무엇을:** LLM이 풀 안에서 **가장 가까운 관련 대체 앵커**를 **필수 사유와 함께** 고름(같은 주제 복원이
  아니라 related-topic *교체* — 그래서 이름이 substitution). 별도 `SUBSTITUTION_CONF_MIN`(0.50)/
  `SUBSTITUTION_MARGIN_MIN`(0.15) gate. 못 넘으면 원래 실패를 raise(= 침묵).
- **활성화:** `SUBSTITUTION_ENABLED` (기본 **False**). composition root에서만 주입.
- **신호:** `method="best_effort_substitution"`, `fallback_used=True`, `original_topic`·
  `substitute_anchor_qid`·`substitution_reason` 채움 — **항상 대체임이 티나게** 신호(조용한 강등 금지).
- **개명 유래:** 구 이름 `proxy`는 LLM 게이트웨이 transport의 "proxy"와 충돌 → `substitution`으로 개명.
  expansion(same-topic 회복) vs substitution(related-topic 교체) 경계도 이름으로 선명해짐.

### 활성화 상태 & eval 결정성

| rung | serving | eval (결정적 gold gate) |
|---|---|---|
| ① symbolic | 항상 | 항상 |
| ② rerank | **항상 주입** | **미주입** (`reranker=None`) |
| ③ expansion | `EXPANSION_ENABLED` (기본 OFF) | 미주입 |
| ④ substitution | `SUBSTITUTION_ENABLED` (기본 OFF) | 미주입 |

폴백 rung은 **결정적 gold 게이트에 절대 주입되지 않습니다** → `baseline.json` byte-identical 유지. 품질은
주입·비결정 **report-only stratum**에서만 측정(게이트에 안 올라탐). 오프라인에서 real 앵커가 7/25만
ground되는 것은 `reranker=None`인 eval artifact이지 serving 능력이 아닙니다 — serving 경로는 rerank로
동음이의를 복구합니다.

### 관측 — "응답은 거짓말하지 않는다"
- **decision log** (`LoggedGrounding`): `method`(무엇이 실제로 일어났나) · `fallback_used` ·
  `substitution_used`(=`method == "best_effort_substitution"`, 필터용으로 파생) · `original_topic` ·
  `expanded_query` · `substitute_anchor_qid` · `substitution_reason` · `considered`.
- **response** (`GroundingView.mode`): substitution인데 `substitute_anchor_qid != qid`이거나 사유가
  비면 `serving._grounding_view()`가 `ValueError`로 막습니다 → 사용자에게 나가는 grounding은 실제 일어난
  것과 항상 일치.

---

## ① agentic grounder (`discovery/grounding_agent.py`, Phase 8-7 재설계) — 구현 완료 · 기본 OFF

> ✅ **해소됨 (2026-08-10).** 2026-08-06 dev 실측에서 한국어 토픽 36 run 중 **13건(36%)이 abstain**으로
> 끝났는데, 원인은 모델의 판단이 아니라 `submit_grounding`에서 **`qid` 필드만 누락**된 스키마 위반이
> 조용히 abstain으로 세탁된 것이었습니다. 최종 tool을 **두 개로 분리**(아래 루프 참조)해 모델이 어느
> 쪽인지를 *tool 선택으로* 말하게 하자 abstain율 **36.1% → 0/71**, grounded **63.9% → 97.2%**(QID drift
> 없음·호출 수 증가 없음). 남은 것은 성질이 다른 더 작은 실패(malformed `qid` 문자열로 인한 adoption-gate
> 거부 2.8%)입니다. 수치·추적·재측정 = [findings](findings-agentic-grounder-submit-omission.md).
>
> ⚠️ 이 해소는 **turn-on 게이트를 열지 않습니다** — online 활성화 게이트는 아래 "online rollout 게이트"의
> judge이고, 그건 별개입니다.

동음이의 **identical-label homonym TIE**(같은 label `Python`을 언어·뱀이 공유)는 symbolic이 원리적으로 못 깹니다
(둘 다 confidence 1.0 → margin 0). tie를 가르는 유일한 새 정보는 **최근 대화 맥락**이고, 그걸 읽고 sense를 고르는
주체는 LLM이어야 합니다. 그래서 재설계는 **최근 대화(`context_messages`)를 받아 native tool-use ReAct 루프로 직접
grounding하는 agentic grounder**를 module ①의 (조건부) primary로 도입합니다. rerank/stance/reason과 같은
dormant-ships(`GroundingAgentSettings.GROUNDING_AGENT_ENABLED` 기본 OFF) — composition root가 ON일 때만
`LLMGrounder`를 주입하고, eval/offline은 절대 주입하지 않아 `baseline.json` byte-identical + CI 커버리지 유지.

> **배경:** 한때 검토한 memory-api `context=`(prose bias 검색)·`_score` projection 접근("C-lite")은 memory-api가
> 검색 엔드포인트에서 `context=`를 제거하며 **폐기**됐습니다([11 §8-7](11-forward-roadmap.md)). 구 Phase 8B
> "listwise full replacement" 폐기 결정을 **다른 근거**(bounded tool-use loop + membership guard)로 되살려,
> "symbolic 정밀 코어가 영구 primary"라는 불변식을 **의식적으로 대체**합니다.

### native tool 루프 + 4중 adoption gate
- **입력:** `topic_text` + `grounding_context`(ⓠ가 `context_messages`에서 투영한 lean 대화; raw wire 메시지는 drop).
- **루프:** `complete_with_tools`(`tool_choice="required"`, ≤`GROUNDING_AGENT_MAX_CALLS`=5턴)로 **5개 tool** —
  knowledge tool 3개 `search_entities`(multi-query 검색)·`get_entity`(상세 관측)·`get_connections`(이웃, opt-in)와
  **terminal tool 2개** `submit_grounding`(qid 제출)·`abstain_grounding`(`abstain_reason`만, `qid` 속성 없음) — 을
  돕니다. terminal을 둘로 나눈 것이 위 결함의 수정입니다: **"제출인가 포기인가"를 모델이 tool 선택으로 말하므로**
  필드 누락이 포기로 세탁될 자리가 없어집니다. assistant tool_call 턴은 verbatim echo(thought_signature 등
  provider 왕복 필드 보존).
- **4중 gate (submit 시):** ① **membership** = 최종 qid가 `get_entity`로 실제 관측한 집합 안 · ② confidence ≥
  `GROUNDING_AGENT_CONF_MIN`(0.70) · ③ **self-cite** = qid ∈ evidence_qids · ④ evidence ⊆ observed ∧ 관측 텍스트에
  non-blank 최소 1개. 하나라도 실패 → `AdoptionGateRejected`(실패한 conjunct 전부를 선언 순서로 실어서). LLM이
  QID를 **발명**하거나 관측하지 않은 근거를 대는 것을 구조적으로 봉쇄.
  ⚠️ **gate 거부는 abstain이 아닙니다** — 모델은 판단을 했고 우리가 거절한 것입니다. 이 문서의 옛 서술이
  둘을 "abstain(`None`)"으로 합쳐 부르던 것이 C4-3이 없앤 혼동입니다(바로 아래).
- **injection-safe:** 고정 system prompt + 대화/후보는 user turn의 JSON data. tool 결과만 관측 집합에 들어가고,
  채택 qid는 반드시 관측 + gate를 통과.

### D1 — context 유무 라우팅 (`Linker.ground()`)

| `context_messages` | 동작 |
|---|---|
| **없음** (`None`) | **symbolic `_ground_symbolic()`** — 주입된 rung대로 처리(아래 "라우팅 vs rung 은퇴" 참조) |
| **있음** (non-empty) | **agentic primary** — 채택되지 않은 **모든** outcome이 terminal(`GroundingFailedError`, symbolic 부활 안 함) |
| **공급됐으나 usable text 0** (`[]`, attachment/blank-only) | **terminal `GroundingFailedError`** (grounder 미호출·LLM 낭비 0) |

- **라우팅은 Linker 계약, rung 은퇴는 composition-root 정책 (구분):** `Linker.ground(context=None)`은 항상
  `_ground_symbolic()`로 가고, 거기서 tie·miss가 실패하느냐는 **어떤 rung이 주입됐느냐**에 달렸다.
  `GROUNDING_AGENT_ENABLED` ON인 composition root는 rerank/expansion/substitution을 **미주입**하므로 context-absent
  tie·miss가 곧장 `GroundingFailedError`(abstain). 반대로 hand-built `Linker(grounder=…, reranker=…)`나 **agent OFF
  기본 배포**는 이 rung들이 살아 있어 context-absent tie에서 **기존 symbolic 사다리가 그대로** 돈다(위 "grounding
  폴백 사다리" 절). 즉 "context 없으면 tie·miss abstain"은 **agent-ON 배선의 결과**지 Linker 자체 불변식이 아니다.
- 그 은퇴가 옳은 이유: context 없이 agent(나 rung)가 상세/importance로 dominant sense를 고르면 **popularity/
  default-sense 추천 회귀**(popularity prior 금지 위반) → context 없을 땐 tie·miss를 정직하게 abstain시키는 게 낫다.
- tri-state는 정규화의 `grounding_context`(None / `[]` / non-empty) **단일 소스**로 표현(별도 bool 없음).

### 사다리와의 관계 · 신호 · 관측
- agent ON이면 composition root가 **rerank/expansion/substitution rung을 전부 미주입**(=live 은퇴) — agent가
  context-primary로 그 회복 역할을 흡수하기 때문. `GroundingMode` enum의 구 rung 값은 **enum엔 유지**(D7)하되
  live 경로에서만 은퇴.
- `method="agentic"`, `fallback_used=False`(agentic은 폴백이 아니라 primary online 경로 — 관측 정직성; symbolic
  경로도 False). context-absent unique-exact 채택과 offline 폴백은 `method="symbolic"`.
- **trajectory:** 채택 시 `GroundingResult.trajectory`에 각 스텝(action/args/본 qid들/follow-up) + 최종 pick + 사유
  + confidence를 기록 → decision log ⑥가 **additive block**으로 저장(symbolic `considered`의 agentic 대응).
  실패한 run은 추천이 없어서 **decision-log row 자체가 없다**(의도된 설계) — 대신 아래 실패 outcome이 구조화된
  trace와 단일 로그 이벤트를 남긴다. 즉 채택 경로의 sink와 실패 경로의 sink는 서로 다르다.
- **소비자 소유 Protocol / duck-type impl:** `Grounder` Protocol은 소비자 `linker.py`가 소유, concrete
  `LLMGrounder`(`grounding_agent.py`)는 Protocol을 import 없이 duck-type(Reranker/Expander/Substituter 관례) —
  구조 매칭은 composition root `Linker(grounder=…)`에서 mypy가 검증. **반환 타입은 `GroundingOutcome`**(아래).

### 실패 outcome 계약 (C4-3, 2026-08-10 · PR #44)

`ground()`는 원래 `GroundingResult | None`이었고, 그 `None`이 **성질이 다른 세 사건을 경계에서 지웠다** —
모델이 일부러 qid를 withhold한 것 / gate가 well-formed 최종을 거절한 것 / proxy가 죽은 것. judge 품질 문제를
쫓는 운영자가 실제로는 outage를 보고 있어도 로그에 구분이 없었다. 게다가 **cause 4종은 이벤트조차 없었다** —
무음 `return None` 3곳에서 나오는데, 그중 한 분기가 **서로 다른 두 실패를 한 곳에 담고** 있었다
(`no_tool_call`과 `malformed_tool_call`). `malformed_final`은 *어느 필드가 깨졌는지*만 알리고 *run이 끝났다는
사실*은 알리지 않았다.

- **반환 타입 = `GroundingOutcome`** = `Adopted` | `ExplicitAbstain` | `AdoptionGateRejected` | `GrounderFailure`.
  이 vocabulary는 **소비자(`linker.py`)가 소유**한다 — Protocol이 거기 있으므로 그 런타임 반환 어휘도 거기 산다.
  `structs/`는 직렬화되는 wire 어휘의 자리이고, 프로세스를 벗어나지 않는 outcome 집합은 거기 속하지 않는다.
  `grounding_agent.py`는 이 이름들을 import하지만 Protocol은 import하지 않아 의존은 **한 방향**으로 유지된다.
- **`GrounderFailure`의 cause 7종**(`GrounderFailureCause`, 누가 실패했는지로 묶음): 모델의 수
  (`no_tool_call`·`arguments_not_json`·`arguments_not_object`·`malformed_final`) / wire
  (`malformed_tool_call`·`proxy_error`) / 우리 예산(`cap_reached`).
  - `no_tool_call` ⊥ `malformed_tool_call`: `tool_choice="required"`인데 빈 턴이 온 건 **모델 행동** 질문이고,
    읽을 수 없는 shape는 모델 판단에 대해 **아무 말도 하지 않는다**. (이전 서술의 "malformed shape → 침묵
    `None`"은 이제 틀렸다 — `GrounderFailure(MALFORMED_TOOL_CALL)`로 이름이 붙는다.)
  - `cap_reached`는 abstain이 아니라 **failure**로 둔다 — spec D6은 cap-without-submit을 abstain이라 부르지만,
    그건 모델이 withhold한 게 아니라 우리 예산이 끝난 것이다. 합치면 **모델 판단을 재는 유일한 지표를 오염**시킨다.
  - 7종 전부가 **cause를 필드로 갖는 단일 이벤트**로 로깅된다(이름이 7개가 아니라 1개) → sink가 이름을 미리 다
    알지 않고도 group by 할 수 있다. severity는 보존: `proxy_error`만 warning, 나머지는 info.
- **안전하게 보관 가능한 실패 trace**(`GroundingFailureTrace`) — 스텝, 죽는 순간 호출 중이던 tool
  (`attempted_action`), 본 context 양. sanitize 선은 **terminal 인자**에 그린다: `reason`·`confidence_rationale`·
  `abstain_reason`은 *사용자 대화에서 파생된 모델 산문*이라 단일 변환 지점에서 제거하고, knowledge tool 인자
  (`queries`·`qid` — 짧은 용어이자 진단 가치의 전부)는 남긴다. sanitize를 통과하는 것은 **named field로** 남긴다:
  abstain은 `ExplicitAbstain.abstain_reason`, gate 거부는 `AdoptionGateRejected.reasons`, malformed final은
  tool 이름 + `field:error_type`. **raw 인자를 버리는 게 규율이고, tool 이름까지 버리면 안전한 절반을 잃는다.**
  채택 경로(`GroundingTrajectory`)는 손대지 않았다 — 거긴 여전히 raw 인자를 decision log로 싣는 audit mirror다.
- **에러는 속성 하나로 싣는다** — `GroundingFailedError.grounding_outcome`이 outcome **객체 전체**를 싣는다.
  cause/trace/reasons를 각각 인자로 받으면 서로 모순될 수 있다(self-exclusion 선례). `None`은 "grounder가
  아무 말도 안 했다"가 아니라 **"grounder가 돌지 않았다"** — 다른 사실이다.
- **`invalid_fields`는 `malformed_final` 전용**이고, 타입과 리포트 경계 **양쪽**이 biconditional
  `(cause is MALFORMED_FINAL) == bool(invalid_fields)`을 강제한다. 두 방향 다 조용히 실패하기 때문이다 —
  다른 cause에 라벨이 붙으면 *일어나지 않은 validation*으로 렌더되고, 라벨 없는 malformed final은 *아무것도
  말해주지 않는 cause*로 렌더된다.
- **외부 계약은 C4-3 시점에 불변이었다** — `/recommend`의 422 `grounding_failed`는 code·message 그대로였고
  (byte-identical) 바뀐 건 `Grounder`→`Linker` **내부** 계약과 관측뿐이었다. 그 메시지가 **부정확했고**(gate
  거부·proxy 오류·cap 도달에도 "abstained") 구조화 outcome이 그 부정확성을 *보이게* 만들었다.
  ⇒ **C4-7에서 닫혔다**(2026-08-11 · 코드 PR #45): 3 code로 갈라지고 메시지는 3수준이 됐다. 계약 전문은
  [07](07-composition-api-cli.md) "grounding 실패의 wire 계약". 이 문서 관점에서 핵심 두 가지:
  - **503 선이 이 문서의 타입 경계에 그대로 떨어진다** — `GrounderFailure`(cause 7종 전부)만
    `grounding_unavailable`(503)이고, `ExplicitAbstain`·`AdoptionGateRejected`는 **판단**이므로 422에 남는다.
    기준은 "판단에 도달했는가"이지 "결정적인가"가 아니다(LLM은 결정적이지 않다). 그리고 abstain·gate 거부를
    통과할 때까지 재시도하는 것은 **안전 게이트의 확률적 우회**다.
  - **cause 7종은 wire에 안 나간다** — code로든 cause별 메시지로든. 여기 있는 어휘는 운영자용이고, 내보내면
    한 번 개명한 적 있는 taxonomy가 호출자 계약으로 굳는다(이 어휘를 `structs/`가 아니라 `linker.py`에 둔
    근거와 같다).

### online rollout 게이트
context grounding의 relatedness는 model/human-judged라 **8-4 B2/human judge**([11](11-forward-roadmap.md))가
online 활성화의 게이트입니다 — 결정적 gold gate는 context 품질을 보증 못 합니다. 그래서 기본 OFF로 ship됐고, judge가
붙기 전엔 report-only stratum에서만 측정됩니다.

---

## 무엇이 provisional이고 무엇이 permanent인가

- **provisional (바뀔 수 있음):** confidence *함수*(binary exact/non-exact 값), threshold seed
  (`LINKER_MARGIN_MIN`·`RERANK_*`·`SUBSTITUTION_*` = eval ratchet 대상, 학습 weight 아님).
- **permanent (구조):** 기호적 정밀 코어, gate/margin *구조*, injection-safety, popularity 배제, 그리고
  "LLM은 폴백 rung에서만 돈다"는 사다리 골격.

기호적 confidence를 listwise reranker로 **완전 대체**하려던 원안(구 Phase 8B)은 2026-07-08 재설계 때 한 번
폐기됐습니다 — 정밀 코어를 버리는 비용이 raw quality 이득보다 크다는 이유로. **2026-07-15 Phase 8-7 재설계는 그
"symbolic 영구 primary" 불변식을 다시 대체**하되, **근거가 다릅니다**: (a) memory-api가 검색 `context=`를 제거해
backend-rank 동점깨기가 불가능해졌고, (b) bounded tool-use loop + membership guard로 "정밀 코어를 버린다"는 구
8B의 리스크를 봉쇄합니다. 결과적으로 symbolic은 죽지 않고 **결정적 offline/eval 폴백 + context-absent unique-exact
short-circuit**으로 강등되며(agentic은 dormant·context 있을 때만 primary), 정밀 코어의 결정성·CI 커버리지는 유지됩니다.
앞으로의 forward work(미구현 Phase 8 잔여·9·10·Open Beta)는 [11 로드맵](11-forward-roadmap.md)에.

---

**요점:** normalize는 입력을 정리하고, linker는 진짜 provider 출력에 대해 결정적으로 QID를
확정합니다 — 기호적 정밀 코어(rung ①)가 정상 경로이고, 애매하면 gate·신호가 걸린 LLM 폴백
사다리(rerank ②/expansion ③/substitution ④)를 오르며 아무것도 못 구제하면 침묵합니다.
다음: QID로 후보 에이전트를 모으는 [04. retrieval](04-retrieval.md).
