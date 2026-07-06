# 08. LLM 레이어 (`discovery/llm/`)

← [개요로 돌아가기](README.md) · 관련: [03. linker](03-normalize-and-linker.md) ·
[11. Phase 8/9 로드맵](11-phase-8-9-roadmap.md)

**포팅은 했지만 Alpha 파이프라인에선 대부분 잠들어 있는** 레이어입니다. Phase 8 rerank/stance/
judge를 위한 준비물입니다.

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
# LLM_PROXY_MODEL=google/gemini-2.5-flash 로 코드 변경 없이 provider 전환.
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

## Alpha에서 왜 잠들어 있나

Alpha 파이프라인의 어느 단계도 LLM을 호출하지 않습니다:
- linker(①)는 **기호적 label 매칭**만 ([03 문서](03-normalize-and-linker.md)).
- normalize(ⓠ)는 **결정적 파서**만.
- ranking/serving reason은 **결정적 문자열**.
- eval 채점은 **결정적 gold — LLM judge 없음** ([10 문서](10-eval-metrics-and-gates.md)).

그래서 이 레이어는 "언제든 붙일 수 있게 이음매를 준비해 둔" 상태입니다. `GroundingResult.method`,
`LoggedGrounding.fallback_used`, `ScoredCandidate` 같은 자리가 이미 `"rerank"`/fallback을 위해
예약돼 있습니다.

---

## PR 리뷰에서 다듬은 것

- httpx client DI + `max_retries` 노출 (private poke 제거).
- 4xx 즉시 raise (`_is_retryable_status` = 429 + 5xx).
- `settings.from_env` → `.get()` (테스트는 `_instances.clear()` 전후 격리).
- `GoogleProvider`의 catch-all retry는 direct adapter 활성화 시 재검토.

---

**요점:** LLM spine은 포팅됐지만 Alpha는 결정성을 위해 그것을 우회합니다. Phase 8이 linker rerank
/ stance normalizer / B2 silver judge로 이 레이어를 깨웁니다 —
[11. Phase 8/9 로드맵](11-phase-8-9-roadmap.md).
