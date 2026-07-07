# 01. 데이터 계약 (`discovery/structs/`)

← [개요로 돌아가기](README.md) · 관련: [02. Provider 경계](02-provider-boundary.md) ·
[06. decision log](06-serving-and-decision-log.md)

파이프라인 사이로 흐르는 자료구조입니다. 이걸 먼저 이해해야 나머지 단계가 읽힙니다.
전부 Pydantic v2 `StrictBaseModel`(또는 `ApiModel`) 기반이고, 로직이 아니라 **계약**입니다.

---

## 세 개의 I/O 경계 (`structs/recommend.py`)

같은 "요청"이라도 레이어마다 다른 타입을 씁니다. 도메인 로직이 API 스키마에 오염되지 않게
하려는 의도적 분리입니다.

| 타입 | base | 무엇 | 특징 |
|---|---|---|---|
| `Query` | `ApiModel` | API 요청과 1:1 | 원시 `user_stance_ref` **문자열**을 그대로 담음 |
| `NormalizedQuery` | `StrictBaseModel` | 파이프라인 입력 | `user_stance_ref`가 `UserStanceRef`로 파싱됨, 원시 문자열은 사라짐 |
| `Recommendation` | `ApiModel` | API 응답과 1:1 | `decision_log_id`로 로그에 연결 |

- `api/routers/recommend/structs.py`가 `Query`를 `RecommendRequest`로 re-export만 합니다 —
  그래서 도메인은 `api/`를 **절대 의존하지 않음**.
- linker/ranker/serving은 `NormalizedQuery`만 봅니다. 원시 문자열 파싱의 애매함이 파이프라인
  안으로 새지 않습니다.

```python
class Query(ApiModel):
    topic_text: str = Field(min_length=1)
    need_type: NeedType
    user_stance_ref: str | None = None   # "axis=…; dir=…; text=…" (§3.1), 나중에 파싱
    lang: str | None = "ko"
    limit: int = Field(default=10, ge=1, le=50)
    context: dict[str, Any] | None = None  # eligibility용 호출 컨텍스트
```

### enum들
- `NeedType`: `depth` / `experience` / `for` / `against` / `coverage`
- `MaturityBand`: `high` / `medium` / `low` (raw maturity를 cutoff로 자른 밴드)
- `AnchorVia`: `direct` / `neighbor` (후보가 앵커에 어떻게 도달했는지)

---

## `AgentTopicEdge` — 시스템의 심장 (`structs/edge.py`)

"에이전트가 한 주제에 대해 무엇을 아는가"를 Wikidata QID에 앵커링한 계약(v0). 이게 전문성
신호의 원천입니다.

핵심 필드:
- `agent_id`, `anchor_id`(= QID, **join 키**)
- `maturity` (0~1) — **1차 게이트 신호** (전문성 성숙도)
- `evidence_strength`, `freshness` — 부차 신호 (freshness는 cutoff 아니라 decay)
- `experience_source_type`(firsthand/secondhand/None), `experience_specificity` —
  **experience를 depth와 가르는 신호**
- `observed_stance`, `stance_axis`, `stance_confidence` — for/against용
- `discoverable` — privacy가 소유하는 노출 플래그
- `source_owner` — **필드마다 누가 소유·거버넌스하는지의 맵**

### 비자명한 결정 3가지

**(1) `extra="forbid"`** — StrictBaseModel은 strict지만 extra를 forbid하진 않습니다. edge에만
따로 forbid를 겁니다:
```python
model_config = ConfigDict(extra="forbid")
```
stale한 provider가 삭제된 필드(예: 과거의 `routing_target`)를 아직 달고 오면 조용히 drop되지
않고 **시끄럽게 실패**합니다. edge는 얼린 계약 표면이라 drift가 조용히 지나가면 안 됩니다.
(base 전체가 아니라 edge에만 거는 이유: base-wide면 Entity round-trip이 깨짐.)

**(2) `source_owner` 키 완전성 validator** — `_SOURCE_OWNER` 맵이 단일 진실원입니다. 값은
오버라이드 가능해도 **키 집합은 정확히 일치**해야 합니다. 부분 맵을 주면 거버넌스가 조용히
깨지므로:
```python
if set(self.source_owner) != set(_SOURCE_OWNER):
    raise ValueError(...)  # missing / extra 키를 짚어줌
```

**(3) `agent_id`의 소유자가 `DERIVED`인 이유** — Memory는 `owner_id`만 줍니다. `agent_id`는
하위(bourbon-api `personal_agent_id`)에서 파생되므로 `SourceOwner.DERIVED`. (`OWNER`는
routing_target 제거 후 활성 필드 없는 reserved.)

**(4) experience 짝 불변식** — `experience_source_type=None`이면 `experience_specificity`도
반드시 `None`. 둘은 함께 움직입니다.

---

## `Candidate` — 모듈 ②→④를 관통하는 내부 객체 (`structs/recommend.py`)

edge를 감싸서 파이프라인 중간 상태를 나릅니다.

```python
class Candidate(StrictBaseModel):
    edge: AgentTopicEdge
    via: AnchorVia
    via_qid: str | None = None          # via=neighbor일 때 원 앵커 QID
    persona: PersonaPrior | None = None
    eligibility: Eligibility
    features: dict[str, float]          # 원시 연속 정렬 입력값
    ordering_keys: list[str]            # 이 need의 사전식 정렬 키 이름
    stance_axis / stance_dir            # 관측된 stance 반영
    drop_reason: str | None = None      # gate/filter 탈락 사유 (로그용)
```

- **scalar score 필드가 없음** — Alpha 랭킹은 ordering contract라서. score를 안 두는 게 계약.
- **`via_qid` iff `neighbor` 불변식**을 validator로 강제 (retrieval의 `EdgeHit`과 동일한 불변식을
  미러). `via==neighbor`일 때 정확히 `via_qid`가 설정됨.

---

## 나머지 struct

- **`Eligibility`** (`eligibility.py`) — `agent_id`, `discoverable`, `reason`. Alpha에선
  `discoverable`만 활성. `privacy_clearance`/`safety_verdict`는 Open Beta 전 추가
  ([Phase 8–10 로드맵](11-phase-8-9-roadmap.md) 참조).
- **`PersonaPrior`** (`persona.py`) — `prior_stance`, `stable_traits`, `expertise_claims`.
  **hollow guard**: stance/특성을 힌트할 뿐 topic `maturity`를 세울 수 없음. 랭킹은 밴드 내
  late tiebreak로만 쓰고, 밴드를 가로질러 승격시키지 못함. Alpha에선 사실상 no-op.
- **`entity.py`** — memory-api 전송 타입(`Entity`, `EntitySummary`, `EntitySuggestion`,
  `EntityConnections`, `ArticleHit`, `EntityCandidate`). 도메인어로는 "anchor", 코드 타입으로는
  `Entity*`.
- **`decision_log.py`** — 감사 기록 미러(순수 record). [06 문서](06-serving-and-decision-log.md).
- **`base.py`** — `StrictBaseModel`(strict 타입), `ApiModel`, `UtcDateTime`(discovery측 소유로
  역의존 차단).

---

**요점:** 계약을 먼저 얼렸기에(Phase 1) mock과 real이 같은 필드에 합의할 수 있고, 파이프라인
단계들은 이 struct들만 알면 됩니다. 다음은 이 struct들을 **누가 공급하는가** —
[02. Provider 경계](02-provider-boundary.md).
