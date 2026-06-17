# Agent Discovery 독립 서비스: 입력 계약 명세

> 이 문서는 메인 설계 문서 `personalized_agent_memory_and_perspective_network.md`의 **참고(companion) 문서**다. 메인 문서의 발견·추천 레이어(5~8·13장)를 **persona/memory 내부 디테일과 분리된 독립 서비스**로 설계·개발하기 위한 입력 계약(contract)을 정의한다.
>
> 자매 문서: 추출·발현 레이어는 `agent_persona_extraction_and_representation.md` 참고.

---

## 0. 한 문장 요약

> **Discovery는 "(엔티티 × 토픽 × 관점) 레코드에 대한 retrieval + ranking 엔진"이며, persona/memory가 *어떻게* 만들어졌는지 전혀 모른 채 `DiscoverablePerspective` 계약과 생애주기 이벤트에만 의존해 동작한다.**

persona/memory 서브시스템은 이 서비스의 **하나의 producer**일 뿐이다. 같은 계약을 만족하면 수작업 프로필, 임포트된 전문가, 조직·브랜드 에이전트 등 다른 source도 producer가 될 수 있다.

> 메인 문서 7장의 **Agent Perspective Card**는 이 일반화된 `DiscoverablePerspective`의 **`entity_type: agent`인 구체 인스턴스**다. 두 문서가 어긋나지 않도록 이 매핑을 기준으로 본다.

---

## 1. 분리 원칙

Discovery가 상류(persona/memory)에서 소비하는 것은 **publish된 구조화 레코드 + 생애주기 이벤트**가 전부다.

| Discovery가 의존하는 것 | Discovery가 몰라도 되는 것 |
|---|---|
| `DiscoverablePerspective` (구조화 필드) | persona_maturity, stable core ⊥ contextual overlay |
| publish / update / revoke 이벤트 | evidence 링크, 10k persona brief |
| 임베딩(또는 임베딩할 텍스트) | 발현 정책, Private Memory |
| `access_policy` | 추출 방식·내부 신호 (extraction_confidence 등) |

> 경계: Discovery의 상류 의존은 **`DiscoverablePerspective` 계약 한 점**으로 모인다. 메인 문서의 "publish 이벤트 → projection"(5.1·5.2)이 곧 이 producer/consumer seam이다.

> 주의 — `extraction_confidence`의 위치: 이건 Discovery가 *직접 소비하지 않을* 뿐, 무의미한 게 아니다. **producer 쪽에서 `confidence`(2.1)를 산정하는 상류 입력**이다. Discovery 계약에는 producer가 만든 `confidence`만 들어오고, 그 값을 만드는 신호(extraction_confidence, evidence 양·일관성 등)는 계약 바깥에 있다.

이 분리 덕분에 Discovery는 persona 추출이 성숙하기 전에도 **합성/수작업 카드로 독립 개발·테스트**할 수 있다.

---

## 2. 입력 계약 (Producer → Discovery)

### 2.1 DiscoverablePerspective

발견·추천의 최소 단위. 한 producer가 "특정 **엔티티**가 특정 관점 영역에서 갖는 공개 관점·스타일"을 표현한다. 개인 에이전트에 한정하지 않도록 일반화한 타입이다.

```yaml
DiscoverablePerspective:
  # ── 엔티티/라우팅 ──
  entity_id: string            # 발견 대상 식별자
  entity_type: enum            # agent | expert_profile | imported_persona | org | brand | ...
                               # 같은 인프라에 이종 producer를 태우기 위한 구분
  perspective_id: string       # (entity, 관점 영역) 단위 식별자
  routing_target: ref          # 발견 후 대화/연결을 핸드오프할 주소 (endpoint·agent ref 등)

  # ── 매칭·임베딩용 텍스트 (relevance 계산의 입력) ──
  summary: string              # 이 엔티티가 이 영역을 어떻게 보는지 요약
  claims_or_stances: [string]  # 핵심 입장/주장
  useful_for: [string]         # 어떤 도움을 줄 수 있는가

  # ── 스타일 ──
  style_descriptors: [string]  # MVP에선 필터/설명용 metadata. ranking 승격은 이후 (2.4·3 참고)

  # ── 출처/품질/신선도 ──
  source_provenance:           # confidence calibration의 입력 (2.4-1)
    producer_type: string      #   agent | manual | import | ...
    source_quality: string?    #   producer가 매긴 원자료 품질 힌트
    manual_verified: bool?     #   사람이 검수했는가
  confidence: enum(low|medium|high) | float[0,1]
                               # producer가 매긴 raw 신뢰도. Discovery가 calibration layer로 정규화 (2.4-1)
  freshness: date              # 최신성. cutoff가 아니라 decay 가중치로 사용.

  # ── 거버넌스 ──
  access_policy:
    discoverable: bool
    requires_permission: bool
    exposes_private_memory: false   # 반드시 false. 누락/위반 시 색인 거부 (2.4-3)

  # ── 선택: topic 배정 ──
  topic: string?               # producer가 줄 수 있으나 hint일 뿐. authoritative 배정은 Discovery (2.3)
```

> **메인 문서 7장 `agent_perspective_card`와의 매핑**: Agent Perspective Card는 `DiscoverablePerspective`의 `entity_type: agent` 인스턴스다. 메인 문서 필드 대응 — `agent_id`→`entity_id`, `perspective_summary`→`summary`, `stance`→`claims_or_stances`, `conversation_style`→`style_descriptors`, `perspective_confidence`→`confidence`.
>
> 지금은 **우선 넓혀두고**(이종 producer 수용 가능하게), `entity_type`별 세부 필드·검증 규칙은 이후 producer가 실제로 늘어날 때 구체화한다.

### 2.2 생애주기 이벤트

Discovery의 active-set과 projection을 정확히 유지하기 위해 producer는 다음 이벤트를 durable하게 발행한다.

```text
publish (entity_id, card)     → 신규/갱신 카드를 색인 반영
update  (entity_id, card)     → 기존 카드 필드 변경
revoke  (entity_id, card_id)  → 카드를 발견 대상에서 제거 (메인 5.2 revoke 절차와 대응)
```

- 반영은 실시간이 아니어도 된다 — Discovery는 debounce 배치로 모아 반영한다 (메인 5.3.1).
- 이벤트가 유실돼도 카드 원본(Public Agent Memory)에서 **재빌드 가능**해야 한다 (메인 5.1). 따라서 raw publish 이벤트 자체는 durable해야 한다.

### 2.3 토픽 배정 — Discovery가 소유 (권장)

`topic`은 선택 필드다. **권장 설계는 Discovery가 임베딩 기반으로 토픽을 동적 클러스터링하는 것**이다 (메인 13.3). 그러면:

- producer 계약이 얇아진다 ("관점 텍스트만 주면 토픽은 Discovery가 붙인다").
- 고정 taxonomy의 long-tail 문제를 피한다.
- **long-tail query, embedding cluster, topic merge/split, synonym 처리**까지 일관되게 Discovery 한쪽 문제로 다룰 수 있다.
- 토픽 공간(Topic Space)·클러스터링·재배치를 Discovery가 온전히 소유한다.

producer가 `topic`을 줄 수도 있으나, 그건 **hint일 뿐** authoritative 배정이 아니며 Discovery의 클러스터링을 강제하지 않는다.

### 2.4 계약 불변식 (새는 seam의 봉합)

분리를 실제로 유지하려면 다음을 계약에 못 박아야 한다.

1. **`confidence`는 producer가 raw로 주고, Discovery가 calibration layer로 정규화한다.** — 외부 producer에게 동일 스케일을 *강제할 수는 없다.* 그래서 표준화 책임을 producer에 지우는 대신, Discovery 내부에 **calibration layer**를 둔다: producer가 준 `confidence` + `source_provenance`(`producer_type·source_quality·manual_verified`)를 입력으로 **normalized confidence**로 변환해 랭킹에 쓴다. MVP에선 producer는 `low | medium | high` 또는 `0..1`만 주면 충분하다. (너무 똑똑한 confidence를 producer마다 만들면 랭킹이 바로 망가진다.)
2. **`style_descriptors`는 안정적이어야 하지만, MVP에선 ranking에 쓰지 않는다.** — 메인 8.1은 style_match를 stable core 축으로 재라고 한다. 그러나 MVP에서 style_match까지 잘하려 들면 **persona 의존성이 다시 끌려 들어온다.** 그래서 MVP 랭킹은 style 항을 빼고(3장), `style_descriptors`는 **필터/설명용 metadata**로만 쓴다. descriptor가 안정화되면 ranking feature로 **승격**한다. (메인 8.1의 풀 공식은 *목표*이고, MVP는 그 부분집합 — 모순이 아니라 phasing이다.)
3. **privacy는 Discovery가 보장하는 게 아니라 fail-closed로 방어한다.** — Discovery는 "이 카드가 private을 누출하지 않는다"를 **판단할 수 없다.** privacy correctness는 **upstream(publish 게이트, 메인 5.2) 책임**, Discovery는 **enforcement 책임**이다. 다음은 색인 거부 또는 검색 제외한다:
   - `access_policy` 누락
   - `discoverable: false`
   - `exposes_private_memory != false`
   - 권한(`requires_permission` 등) 불명확
4. **`entity_id` / `routing_target`은 안정적이고 라우팅 가능** — Discovery의 산출물은 "이 엔티티와 대화하라"는 포인터다. 대화 서브시스템으로 핸드오프 가능한 안정 식별자·주소여야 한다.

---

## 3. Discovery가 소유하는 것 (서비스 책임)

입력 계약만 충족되면 Discovery는 내부적으로 다음을 자체 책임으로 수행한다 (메인 6·8·13장).

- **색인**: Topic Space(narrative) + Perspective Index(구조화/임베딩). 토픽 클러스터링·merge/split·synonym.
- **confidence calibration**: producer가 준 raw `confidence` + `source_provenance` → **normalized confidence** (2.4-1). 이 정규화 층이 producer 이질성을 흡수한다.
- **retrieval**: query → topic match → 후보 검색 (대규모에선 분산 ANN, 메인 13.3).
- **권한 필터링**: `access_policy`를 인덱스 안으로 push-down (post-filter 금지, 메인 13.3). 2.4-3의 거부 조건 적용.
- **ranking** (generic baseline — 모든 `entity_type` 공통 예시):
  - **MVP**: `score = relevance × confidence × freshness_decay` (style 항 제외, 2.4-2).
  - **목표(메인 8.1)**: `× style_match` 추가 — style descriptor가 안정화된 뒤 승격.
  - freshness는 cutoff가 아니라 decay 가중치.
  - 이 baseline은 **예시**다. 결합 방식(곱셈/가중합)·추가 feature는 `entity_type`별로 specialization될 수 있다. 예: `entity_type = agent`의 agent 추천 랭킹은 `advisory_fit`을 더한 **가중합**으로 둔다 (`agent_matching_candidates_for_mvp.md` §6).
- **active-set 관리**: freshness·(normalized)confidence 결합 축출 (메인 5.3.2). "오래됐고 *동시에* 저품질"만 cold로.
- **갱신 운영**: publish/update/revoke 이벤트를 debounce 배치로 반영 (메인 5.3.1).
- **핸드오프**: 추천 결과 = `routing_target` 목록 → 대화 서브시스템이 그 엔티티와의 대화를 구동.

> Discovery는 **최종 답변을 생성하지 않는다.** "이 관점을 가진 엔티티와 대화하라"까지만 책임진다 (메인 5·8장의 pointer-not-payload 원칙).

---

## 4. 책임 분리 표

| 관심사 | Producer (persona/memory 등) | Discovery |
|---|---|---|
| 카드 내용 생성 | ✅ | — |
| raw `confidence` + `source_provenance` 제공 | ✅ | — |
| confidence 정규화(calibration) | — | ✅ (producer 이질성 흡수) |
| `style_descriptors` 안정화 | ✅ (core 역산) | MVP: 필터/설명용만 · 이후 ranking 승격 |
| private 비노출 보장 | ✅ (publish 게이트) | enforce + fail-closed 거부 |
| 토픽 배정 | hint만(선택) | ✅ authoritative 소유 (클러스터링) |
| 색인·retrieval·ranking | — | ✅ |
| active-set·갱신 운영 | durable 이벤트 발행 | ✅ |
| 대화 구동(발현) | 별도 서브시스템 | 핸드오프만 |

---

## 5. 일반화와 실익

- **다중 producer**: 같은 계약(`DiscoverablePerspective`)을 만족하면 개인 에이전트 외에도 전문가 프로필, 임포트된 persona, 조직·브랜드 에이전트까지 동일 Discovery 인프라에 태울 수 있다 (`entity_type`으로 구분).
- **병렬 개발**: persona 추출의 어려운 문제(정확도·프라이버시)와 분리해, Discovery를 **합성/수작업 카드로 먼저 구축·검증**할 수 있다.
- **권장 개발 착수 순서**: **retrieval → ranking → active-set → revoke**를 합성/수작업 카드로 먼저 세운다. persona 추출이 성숙하기 전에 발견 품질·생애주기 동작을 독립 검증할 수 있다.
- **재빌드 안전성**: Discovery 인덱스는 카드 원본에서 언제든 재생성 가능하므로(메인 5.1), 워커 장애·재처리 설계가 단순하다.

---

## 6. MVP → 대규모 (메인 13장 매핑)

| 영역 | MVP | 대규모 |
|---|---|---|
| 저장 | 단일 DB (문서 + 구조화 인덱스) | 분산 vector DB + ANN |
| 권한 | query 시점 필터 | 인덱스 push-down / 파티셔닝 |
| 토픽 | 소수 클러스터 | 임베딩 동적 클러스터링, 토픽 내부 샤딩 |
| 갱신 | debounce 단일 워커 | projection 워커 수평 분산 + durable 큐 |

계약(2장)은 MVP·대규모에서 **동일**하다. 바뀌는 것은 Discovery 내부 구현(3·6장)뿐이며, producer는 영향받지 않는다.
