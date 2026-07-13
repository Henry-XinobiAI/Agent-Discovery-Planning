# 08. LLM 레이어 (`discovery/llm/`)

← [개요로 돌아가기](README.md) · 관련: [03. linker](03-normalize-and-linker.md) ·
[11. Forward 로드맵](11-phase-8-9-roadmap.md)

포팅한 structured-LLM 레이어. **rerank leg는 Phase 8A에서 깨어나 serving에서 동작**합니다(linker
fallback — gate 실패 시에만 호출). free-form stance normalizer(8-3)·rich reason generator(8-5)는
**dormant-ship**(기본 OFF, composition root가 ON일 때만 주입). B2 silver judge만 아직 예약.

---

## 결정: e3llm vendor 폐기 → memory-api spine 포팅

- e3llm SDK를 vendor하는 대신, memory-api `memory/llm`의 **structured-completion spine만** 포팅.
- tool-calling 표면은 제외.
- deps는 `google-genai` 하나.

---

## 구조

| 파일 | 역할 |
|---|---|
| `llm/config.py` | `LLMSettings` — provider 선택 + 엔드포인트 |
| `llm/proxy.py` | OpenAI-호환 proxy client (**Alpha default runtime**) |
| `llm/providers.py` | `_BaseLLMProvider` (httpx client lifecycle + backoff retry) |
| `llm/structured.py` | JSON-schema 헬퍼 (Pydantic 모델 → wire schema) |
| `llm/wrapper.py` | `get_client` — mode 선택 (proxy/direct) |

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

LLM 호출 지점은 셋이고, 셋 다 **폴백/보강**이며 기본 결정적 경로를 안 바꿉니다:
1. **linker rerank fallback**(Phase 8A) — 기호적 gate가 애매해 실패할 때만 같은 후보셋을 재채점
   ([03 문서](03-normalize-and-linker.md)).
2. **free-form stance normalizer**(8-3, dormant) — for/against `user_stance_ref`가 문법 파싱에
   실패할 때만 도는 normalize(ⓠ) 폴백 ([03 문서](03-normalize-and-linker.md)).
3. **rich reason generator**(8-5, dormant) — serving(⑤)이 서빙된 후보에 per-need reason을 한 batch로
   생성 ([06 문서](06-serving-and-decision-log.md)); 실패/미커버 시 결정적 문자열로 전량 폴백.

기본(및 eval)에서는 여전히 결정적입니다:
- normalize(ⓠ)는 **기본 결정적 파서** — 자유형 stance만 LLM normalizer 폴백(8-3, flag OFF면 dead).
- serving reason은 **기본 결정적 문자열**(원 `signals`는 flag 무관 항상 실림) — 리치화는 8-5, flag OFF면 dead.
- eval 채점은 **결정적 gold — LLM judge 없음** ([10 문서](10-eval-metrics-and-gates.md)). eval은
  reranker/normalizer/reason-generator를 **하나도 주입하지 않아** 세 폴백이 eval에선 절대 안 뜸 →
  오프라인·결정성 유지 (baseline 불변).

`GroundingResult.method="rerank"` / `fallback_used` 자리는 이제 예약이 아니라 **활성**입니다.
stance normalizer(8-3)·reason generator(8-5)는 이음매가 아니라 **shipped(기본 OFF)**. B2 silver judge만
아직 예약 상태로 남아 있습니다.

---

## PR 리뷰에서 다듬은 것

- httpx client DI + `max_retries` 노출 (private poke 제거).
- 4xx 즉시 raise (`_is_retryable_status` = 429 + 5xx).
- `settings.from_env` → `.get()` (테스트는 `_instances.clear()` 전후 격리).
- `GoogleProvider`의 catch-all retry는 direct adapter 활성화 시 재검토.

---

**요점:** Phase 8A가 이 레이어의 **rerank leg를 깨워** serving에서 동작시킵니다 (linker fallback,
e3llm-api proxy 경유 · keyless Gemini 기본). eval은 reranker 미주입으로 오프라인·결정적 유지. Phase 8B에서 expansion③·substitution④ rung도 shipped(opt-in dormant, default OFF)됐지만, rerank와 마찬가지로 결정적 eval엔 절대 주입되지 않고(report-only strata에서만) — 그래서 offline·결정적 보장은 그대로다.
stance normalizer(8-3)·reason generator(8-5)도 같은 dormant-ship 계약으로 실렸고(기본 OFF·eval 미주입),
B2 silver judge만 아직 예약 — [11. Forward 로드맵](11-phase-8-9-roadmap.md).
