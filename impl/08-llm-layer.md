# 08. LLM 레이어 (`discovery/llm/`)

← [개요로 돌아가기](README.md) · 관련: [03. linker](03-normalize-and-linker.md) ·
[11. Forward 로드맵](11-forward-roadmap.md)

포팅한 structured-LLM 레이어. **rerank leg는 Phase 8A에서 깨어나 serving에서 동작**합니다(linker
fallback — gate 실패 시에만 호출). 그 위에 **agentic grounder(8-7)**·**stance query generator + judge
(④a)**·rich reason generator(8-5)가 **dormant-ship**(기본 OFF, composition root가 ON일 때만 주입)으로
실렸고, expansion③·substitution④ rung도 같은 opt-in 계약입니다. B2 silver judge만 아직 예약.

---

## 결정: e3llm vendor 폐기 → memory-api spine 포팅

- e3llm SDK를 vendor하는 대신, memory-api `memory/llm`의 **structured-completion spine + tool-calling
  응답 표면**을 포팅 (tool-calling은 proxy 경유 `complete_with_tools`; Phase 8-7 agentic grounder가 사용).
- 아직 제외한 것은 **direct-provider tool 번역**(ToolSpec / OpenAI↔Gemini)뿐 — serving은 proxy 전용이라 불필요.
- deps는 `google-genai` 하나.

---

## 구조

| 파일 | 역할 |
|---|---|
| `llm/config.py` | `LLMSettings` — provider 선택 + 엔드포인트 |
| `llm/proxy.py` | OpenAI-호환 proxy client + `complete_with_tools` (**Alpha default runtime**) |
| `llm/providers.py` | `_BaseLLMProvider` (httpx client lifecycle + backoff retry) · `LLMResponse`(tool_calls/finish_reason/message) |
| `llm/structured.py` | JSON-schema 헬퍼 (Pydantic 모델 → wire schema) |
| `llm/wrapper.py` | `get_client` mode 선택 (proxy/direct) + `complete_with_tools` 모듈 헬퍼 |

### proxy default (`llm/proxy.py`)
```python
# Discovery는 provider SDK가 아니라 LLM_PROXY_URL의 proxy를 호출.
# OpenAI/Gemini를 하나의 wire format + response_format json_schema로 구동.
# LLM_PROXY_MODEL 로 코드 변경 없이 provider/model 전환 (기본 google/gemini-3.1-flash-lite).
```
- proxy가 auth를 담당 → API key 안 보냄.
- transient blip은 exponential backoff로 retry (429+5xx만 retryable, 4xx 즉시 raise).

### direct는 inactive (`llm/config.py`)
```python
LLM_MODE = "proxy"   # "proxy"(default) | "direct"(포팅됐지만 비활성)
```
`LLM_MODE=direct`는 명시적 에러 — direct provider들이 아직 structured output을 못 함. structured
direct adapter는 후속.

### structured spine (`llm/structured.py`)
- **단일 진실원**: wire schema를 응답을 파싱하는 Pydantic 모델에서 파생
  (`pydantic_response_format`) → schema가 struct에서 drift 불가.
- `X | None` 필드를 `anyOf[…, null]`로 렌더 (OpenAI strict + Gemini 둘 다 수용). 손으로 쓴
  `{"type": ["string", "null"]}` 타입-배열은 Gemini가 거부하므로 안 씀.
- `extra="forbid"` base 기반 모델은 `additionalProperties: false`를 자동 emit → OpenAI strict 충족.

---

## 무엇이 깨어 있고 무엇이 잠들어 있나

LLM 사용 지점은 **일곱**이고, 묶으면 셋입니다(grounding 계열 4 · stance 2 · reason 1). grounding 계열의 두
갈래는 `GROUNDING_AGENT_ENABLED`로 **상호 배타**(둘이 절대 안 겹침)이고, 나머지는 폴백/보강/조건부 need라
기본 결정적 경로를 안 바꿉니다:

- **grounding 계열 (module ①)** — flag에 따라 둘 중 하나만 돎:
  - **agentic grounder**(8-7, dormant·`GROUNDING_AGENT_ENABLED`) — ON이면 ①의 **primary**가 되어 대화
    맥락 위에서 native tool 루프로 grounding하고 아래 symbolic recovery rung을 **은퇴**시킴
    ([03 문서](03-normalize-and-linker.md)).
  - **symbolic recovery rung** (agent OFF, 현 기본) — rerank②(Phase 8A live)·expansion③(`EXPANSION_ENABLED`,
    dormant)·substitution④(`SUBSTITUTION_ENABLED`, dormant)가 기호적 gate가 애매/miss일 때만 같은/넓힌
    후보 풀을 재채점·재검색 ([03 문서](03-normalize-and-linker.md)).
- **stance 계열 (④a, dormant·`STANCE_JUDGE_ENABLED`)** — 둘이 **순차 파이프라인**이라 함께 켜지고 함께
  꺼집니다 ([05 문서](05-gate-and-ranking.md)):
  - **stance query generator**(B4) — `(topic, proposition)` → neutral/support/oppose **세 방향 검색어**
    (`StanceQueries`). 요청당 **1콜**. 한 방향이라도 비면 편향된 확장이라 `None` 강등.
  - **stance judge**(B5) — 한 owner의 statement들을 proposition에 대고 읽어 **절대 verdict**
    (`supports`/`opposes`/`insufficient`) 산출. **후보당 1콜**. 이게 for/against verdict의 **유일한**
    출처입니다 — statement의 kind/epistemic/confidence는 검색 prior이지 verdict 지름길이 아님.
- **rich reason generator**(⑤, 8-5, dormant) — 서빙된 후보에 per-need reason을 한 batch로 생성
  ([06 문서](06-serving-and-decision-log.md)); 실패/미커버 시 결정적 문자열로 전량 폴백.

일곱 지점의 **공통점은 격리**입니다: **예상 가능한** LLM runtime 오류(proxy transport)나 malformed 출력이
500으로 새지 않습니다 — structured seam 6곳에서는 `None`으로, agentic 루프에서는 **복구 가능한 tool
observation 또는 최종 `None`**으로 갇힙니다. 반대로 **프로그래밍/설정 오류는 일부러 전파**됩니다
(`LLM_MODE=direct`로 client 생성 실패, Gemini로 번역 불가한 스키마 등 — 이건 degrade가 아니라 배선 버그).

다만 **구현은 둘로 갈립니다**:

| | structured-completion 6곳 | agentic grounder 1곳 |
|---|---|---|
| 진입점 | `invoke_structured` | `complete_with_tools` bounded ReAct 루프 |
| 검증 | strict Pydantic 스키마 **1회** 파싱 | tool-call shape → JSON args → tool 스키마 → 최종 `GroundingAgentFinal` → membership 가드, **단계별** |
| 실패 처리 | `LLMProxyError`/`ValidationError` → `None`, 끝 | 실패 종류에 따라 **복구 시도 or 중단** (아래) |

grounder의 실패가 전부 곧장 `None`인 게 **아니라는 게** 핵심입니다. 네 갈래입니다:

| 실패 | 결과 |
|---|---|
| proxy 예외 · malformed tool-call envelope · tool args가 JSON object로 파싱 안 됨 | **즉시 `None`** (침묵) |
| knowledge-tool의 args 검증 실패 · provider 예외 · qid 부재 | **non-fatal** — `run_tool`이 `error`/`found:false` payload를 담은 `ToolObservation`으로 바꾸고 **루프 계속**. 모델이 다음 턴에 스스로 복구하라는 설계 |
| terminal `submit_grounding`의 검증·adoption gate·membership 가드 실패 | **`None`** |
| call cap까지 `submit_grounding`을 못 함 | **`None`** (abstain) |

`run_tool`은 **절대 raise하지 않고**(arg validation이 guard **안**에 있음) 한 번의 잘못된 tool 콜이 런을
죽이지 못하게 합니다. 반면 `submit_grounding`은 terminal이라 재시도 여지가 없어 곧장 중단입니다.

주입 안전은 일곱 곳 모두 동형입니다 — 고정 system prompt + 사용자 텍스트를 user turn에 JSON **data**로
적재 + strict 스키마(`extra="forbid"`).

기본(및 eval)에서는 여전히 결정적입니다:
- grounding(①)은 **기본 symbolic**(맥락 미공급 시) — agentic은 8-7, flag OFF면 dead.
- normalize(ⓠ)는 **LLM을 아예 안 씁니다** — proposition을 해석하지 않으므로 여기엔 이음매가 없음
  (구 8-3 stance normalizer는 요청 모델 재설계와 함께 **제거**됨, [03 문서](03-normalize-and-linker.md)).
- stance(④a)는 **flag OFF면 dead** — for/against는 LLM을 몰래 안 쓰고 `stance_judge_disabled`로 **침묵**.
- serving reason은 **기본 결정적 문자열**(원 `signals`는 flag 무관 항상 실림) — 리치화는 8-5, flag OFF면 dead.
- eval 채점은 **결정적 gold — LLM judge 없음** ([10 문서](10-eval-metrics-and-gates.md)). eval은
  reranker/reason-generator/grounder/stance query-gen/judge를 **하나도 주입하지 않아** 일곱 LLM 지점이
  eval에선 절대 안 뜸 → 오프라인·결정성 유지 (baseline 불변). ④a만 eval에 대체물을 넣지만 그건 LLM이
  아니라 edge를 미러링하는 결정적 `EdgeMirrorStanceEvaluator`입니다.

`GroundingResult.method`의 `rerank`/`agentic`, `fallback_used`, `trajectory` 자리는 이제 예약이 아니라
**활성**입니다. stance 계열(B4/B5)·reason generator(8-5)·agentic grounder(8-7)는 이음매가 아니라
**shipped(기본 OFF)**. B2 silver judge만 아직 예약 상태로 남아 있습니다 — 이름이 비슷하지만 **stance
judge와 별개**입니다(B5 = 서빙 시점 verdict 생산자, B2 = 오프라인 품질 채점자).

---

## PR 리뷰에서 다듬은 것

- httpx client DI + `max_retries` 노출 (private poke 제거).
- 4xx 즉시 raise (`_is_retryable_status` = 429 + 5xx).
- `settings.from_env` → `.get()` (테스트는 `_instances.clear()` 전후 격리).
- `GoogleProvider`의 catch-all retry는 direct adapter 활성화 시 재검토.

---

**요점:** Phase 8A가 이 레이어의 **rerank leg를 깨워** serving에서 동작시킵니다 (linker fallback,
e3llm-api proxy 경유 · keyless Gemini 기본). Phase 8B의 expansion③·substitution④ rung, 그리고 stance
query-gen + judge(④a)·reason generator(8-5)·agentic grounder(8-7)는 모두 **dormant-ship**(기본 OFF)으로
실렸습니다. eval은 이들(reranker 포함)을 **하나도 주입하지 않으므로** 오프라인·결정적 baseline이
그대로입니다 (rung은 report-only strata에서만 관측). B2 silver judge만 아직 예약 —
[11. Forward 로드맵](11-forward-roadmap.md).
