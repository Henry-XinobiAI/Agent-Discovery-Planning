# 03. normalize (ⓠ) + linker (①) — grounding

← [개요로 돌아가기](README.md) · 관련: [01. 데이터 계약](01-data-contracts.md) ·
[04. retrieval](04-retrieval.md) · [08. LLM](08-llm-layer.md)

파이프라인의 첫 두 단계. **가장 정교한 로직**이 여기(linker)에 있습니다. "real anchor = teeth"
— 진짜로 가짜로 꾸미기 어려운 유일한 스테이지입니다.

---

## ⓠ normalize (`discovery/normalize.py`)

`Query` → `NormalizedQuery`. 입력 정규화만 하고, 주제→QID는 linker의 일입니다 (관심사 분리).

### `user_stance_ref` 문법 (Alpha는 보수적)
```
axis=<text>; dir=<for|against|neutral>; text=<optional>
```
- `axis`, `dir` 필수, `text` 선택.
- `key=value`를 `partition("=")`로 파싱 (첫 `=`만 → `text`에 `=` 포함 가능).
- 알 수 없는 키 / 중복 키 / 빈 axis(min_length) → `InvalidNeedError`.

### need별 처리 (핵심 규칙)
```python
if query.need_type in (FOR, AGAINST):
    if query.user_stance_ref is None:  raise InvalidNeedError   # 필수
    user_stance = _parse_user_stance_ref(...)
    if user_stance.dir is Stance.NEUTRAL:  raise InvalidNeedError  # neutral은 반대가 없음
# depth/experience/coverage → user_stance_ref 무시, user_stance=None
```

- **for/against는 상대적 need**라서 유저의 기준 stance가 필수. neutral은 "반대편"이 없으므로
  방향성 stance를 요구 → **for/against + neutral = `InvalidNeedError`**.
- 다른 need에 stray `user_stance_ref`가 와도 무시 (에러 아님). 원시 `Query`에는 남아서 로그에
  기록되지만 `NormalizedQuery`로는 절대 넘어가지 않음.

---

## ① linker (`discovery/linker.py`) — 주제 텍스트 → QID 하나

**기호적 우선 경로** (Phase 4). popularity 없음. 기호적 gate 통과가 정상 경로 — LLM은 gate가
애매해서 실패할 때만 rerank **fallback**으로 호출됩니다 (Phase 8A, [08 LLM](08-llm-layer.md)).

### 흐름

```
search_candidates ∪ suggest  (두 recall 경로, 동시 fetch)
  → _merge_candidates (qid로 병합, provider 순서 보존)
  → _score (기호적 label-match confidence, confidence-desc 정렬)
  → margin 계산
  → adoption gate (confidence ≥ MIN AND margin ≥ MIN)
  → 통과: GroundingResult / 실패: GroundingFailedError
```

### (1) 후보 생성 — 두 개의 recall 경로
```python
summaries, suggestions = await asyncio.gather(
    self._knowledge.search_candidates(topic_text, limit=limit),
    self._knowledge.suggest(topic_text, limit=limit),
)
```
`asyncio.gather`가 인자 순서를 보존하므로 병합 순서(→ both-route tier)가 결정적. 두 경로 모두
alias-aware라 **recall**을 위한 것.

### (2) confidence — 기호적 3-tier
```python
_CONF_EXACT_LABEL  = 1.0   # 정규화 label == query
_CONF_BOTH_ROUTES  = 0.75  # search + suggest 둘 다에서 등장 (corroborated)
_CONF_SINGLE_ROUTE = 0.55  # 한 경로만 (fuzzy/partial)
```
- `_norm` = `strip().casefold()` (순서·공백 무관 비교).
- **popularity 신호 절대 안 씀** (D2): `importance`/`pageview`/`pagerank`가 선택을 조종하지
  않음 → 앵커 선택이 popularity prior를 물려받지 않음.
- alias tier는 별도로 관측 불가(`EntitySummary`/`EntitySuggestion` 투영에 aliases 없음, aliases는
  full `Entity`에만) → Phase 4는 route provenance로 흡수. Phase 8B에서 재도입.
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

### (4) adoption gate
```python
LINKER_CONF_MIN   = 0.50   # 절대 confidence floor
LINKER_MARGIN_MIN = 0.15   # top1-top2 gap
if top.confidence < CONF_MIN or margin < MARGIN_MIN:
    raise GroundingFailedError(...)  # "grounding 0"
```
- seed는 memory-api `Grounder`(`GROUNDING_MIN_SCORE`/`GROUNDING_MIN_MARGIN`)에서 빌려옴,
  **provisional** (eval ratchet가 retune 가능). 학습된 weight가 아님.
- 후보 자체가 0개여도 `GroundingFailedError`.
- `GroundingFailedError`는 `considered`(qid, confidence 쌍)를 담아서 decision log가 "왜 실패했나"를
  기록 가능하게 함.

### 산출물
```python
class GroundingResult:
    qid / label / confidence / margin
    method: Literal["symbolic","rerank"]  # "rerank" = LLM fallback으로 채택 (Phase 8A)
    fallback_used: bool                   # rerank fallback이 grounding을 구제했을 때만 True
    considered: list[ScoredCandidate]     # confidence-desc, 로그용
```

---

## 무엇이 provisional이고 무엇이 permanent인가

- **provisional (바뀔 수 있음):** confidence *함수* (3-tier 값), threshold seed.
- **permanent (구조):** gate/margin *구조*, injection-safety, popularity 배제.

Phase 8A가 gate 실패 시 LLM rerank **fallback**을 붙였습니다 — gate/margin 골격은 그대로, 별도
`RERANK_*` 상수로 재심. 기호적 confidence를 listwise reranker로 **완전 대체**하는 건 Phase 8B.
([11 로드맵](11-phase-8-9-roadmap.md) 참조.)

---

**요점:** normalize는 입력을 정리하고, linker는 진짜 provider 출력에 대해 결정적으로 QID를
확정합니다. 다음: QID로 후보 에이전트를 모으는 [04. retrieval](04-retrieval.md).
