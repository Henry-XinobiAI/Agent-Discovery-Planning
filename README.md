# 개인화 에이전트 & 관점 네트워크 — 문서 인덱스

이 디렉토리는 "개인화 에이전트와 그 관점으로 구성되는 네트워크" 제품의 설계 문서 모음이다. 문서가 여러 개로 나뉘어 있으므로, **어떤 문서가 무엇을 다루는지 / 같은 개념을 레이어별로 어떻게 부르는지 / 어떤 순서로 읽어야 하는지**를 여기서 먼저 정리한다.

핵심 한 줄:

> 개인 대화로 **Memory와 Persona**가 자란다 → 주인이 **publish**한 일부가 **Public Agent Memory**로 공개된다 → 그것이 **SKL**에 투영되어, 다른 유저가 정답 문서가 아니라 **관점을 가진 에이전트를 발견하고 대화**하게 한다.

---

## 1. 문서 지도

| 문서 | 레이어 | 다루는 것 | 핵심 단위 |
|---|---|---|---|
| `personalized_agent_memory_and_perspective_network.md` | **개념/제품 (메인)** | 비전, Memory⊥Persona, 메모리 3계층, SKL 역할·구조·생애주기, 발견 흐름, 확장성 | Agent Perspective Card |
| `agent_persona_extraction_and_representation.md` | **추출·발현** | persona/memory를 *어떻게 뽑고*(extraction) *어떻게 발화하는가*(representation) | structured evidence store, persona brief |
| `agent_discovery_service_contract.md` | **contract** | discovery를 persona/memory와 분리된 독립 서비스로 보는 producer-consumer 계약 | DiscoverablePerspective |
| `agent_matching_candidates_for_mvp.md` | **서빙/랭킹 (MVP)** | 그 위에서 "지금 이 요청에 어떤 agent를 추천할까"의 구체 랭킹·인덱스 설계 | AgentTopicPerspective |

런타임(질문 생성·타이밍·액션·오케스트레이션)은 이 묶음의 범위 밖이며 `agent_event_driven_architecture.md`(+ `_core.md`) 소관이다.

> 노션 공유용 사본은 `*_notion.md` 접미사로 별도 관리한다 (헤딩 H3 이하·코드펜스 호환 변환본). 원본은 GitHub/표준 마크다운 기준으로 둔다.

---

## 2. 데이터 흐름 (한 store → 여러 projection)

```text
대화 / 미디어
  → structured evidence store        [추출·발현 문서: source of truth]
      ├─ Private Memory ──────────────┐
      │                               ├─▶ persona brief (자기/대변 발현)  → system prompt
      └─(publish gate)─▶ Public Agent Memory
                                      └─▶ projection
                                            → SKL (Topic Space + Perspective Index)   [메인]
                                            → DiscoverablePerspective  (contract 계약 단위)
                                            → AgentTopicPerspective Index (서빙)        [MVP]
                                                  → matching / ranking → Recommended Agents
```

- **추출·발현 문서**는 화살표 왼쪽(저장·발현)을 담당한다.
- **메인 문서**는 "publish → projection → 발견"의 개념을 정의한다.
- **contract 문서**는 그 projection을 받는 discovery의 입력 계약(`DiscoverablePerspective`)을 고정한다.
- **MVP matching 문서**는 그 계약 위에서 실제 추천 랭킹·인덱스를 설계한다.

---

## 3. 네이밍 정리: 비슷해 보이는 세 레코드

같은 대상을 보는 **다른 레이어**다. 경쟁 모델이 아니다.

| 이름 | 레이어 | 정의 |
|---|---|---|
| `Agent Perspective Card` | 개념/제품 | 메인 7장의 공개 관점 카드 (Memory ∩ Persona의 공개 투영) |
| `DiscoverablePerspective` | contract | producer-consumer 일반 인터페이스. `entity_type`으로 agent 외(전문가·조직·브랜드)도 수용 |
| `AgentTopicPerspective` | 서빙 | matching 서빙 인덱스의 물리/논리 레코드 |

> 관계: **`AgentTopicPerspective` = `DiscoverablePerspective` 중 `entity_type = agent`인 레코드를 matching serving에 맞게 denormalize + feature enrichment한 형태**(advisory_profile 등 matching 전용 feature가 더 붙는다)이고, 그 개념적 원형이 `Agent Perspective Card`다. contract만 있어도 discovery는 가능하고, matching 품질은 enrichment가 있을 때 좋아진다.

---

## 4. 용어 정리: confidence / maturity 계열

여러 문서에 신뢰도·성숙도 항이 흩어져 있어 혼동하기 쉽다. **서로 다른 층의 신호**이며 다음으로 고정한다.

| 용어 | 위치 | 의미 |
|---|---|---|
| `extraction_confidence` | 추출 후보 | 추출된 *후보 자체*의 신뢰도 (단정 저장 회피용) |
| `persona_maturity` | 페르소나 추정 | 페르소나 코어 추정이 얼마나 무르익었는가 (관찰 양·일관성) |
| `evidence_strength` | 원본 자료 | 원자료의 양·일관성·구체성 |
| `perspective_confidence` | 공개 카드 | 공개 관점 카드의 신뢰도·품질 (evidence_strength에서 산출) |
| `topic_knowledge_maturity` | matching 서빙 | 특정 topic에서 대화 가능한 수준까지 관점이 성숙했는가 (perspective_confidence의 matching 파생값) |
| `freshness` | 공통 | 최근성. cutoff가 아니라 **decay 가중치**로 사용 (maturity와 분리) |

> 원칙: 새 confidence 계열을 늘리지 않는다. `topic_knowledge_maturity`는 `perspective_confidence`의 파생이고, contract의 `confidence`는 producer가 준 raw 값을 discovery가 calibration한 정규화 값이다.

---

## 5. 문서 간 공유 불변식

여러 문서가 함께 지키는 규칙. 한 곳에서 깨지면 전체가 어긋난다.

- **Private Memory는 하드 월** — 타인이 내 에이전트와 대화할 때 접근 경로 자체가 없다.
- **publish는 단일 게이트** — 사용 권한 + 발견 권한을 함께 켠다. 누출 위험이 이 한 점에 집중되므로 파이프라인(privacy classifier → 주인 승인 → audit log → projection)을 거친다.
- **SKL/인덱스는 source of truth가 아니라 projection** — Public Agent Memory에서 언제든 재빌드 가능.
- **freshness는 decay 가중치, hard cutoff가 아니다** — evergreen 관점을 죽이지 않기 위해 perspective_confidence와 분리.
- **발현에서 에이전트는 1인칭 본인 행세를 하지 않는다** — 대변 발현도 대리 에이전트로서 관점·스타일만 채택.
- **MVP는 conversation style을 랭킹에서 제외** — advisory(무엇을·어떻게 판단/조언) O, conversation dynamics(말투·길이·turn-taking) X. style은 descriptor 안정화 후 승격.
- **privacy는 discovery가 보장하지 않고 enforce한다** — correctness는 upstream publish 게이트 책임, discovery는 fail-closed 거부.

---

## 6. 읽는 순서

1. **`personalized_agent_memory_and_perspective_network.md`** — 전체 그림과 개념. 먼저 읽는다.
2. 관심 방향에 따라 분기:
   - 추출·발현(저장 모델, persona brief, 발현 정책)이 궁금하면 → `agent_persona_extraction_and_representation.md`
   - discovery를 독립 서비스로 떼어 개발하려면 → `agent_discovery_service_contract.md`
   - 실제 추천 랭킹·인덱스 MVP를 설계하려면 → `agent_matching_candidates_for_mvp.md`
3. 런타임·이벤트 구조 → `agent_event_driven_architecture.md`

---

## 7. 개발 착수 권장

- discovery/matching은 persona 추출 성숙 이전에 **합성/수작업 카드로 독립 개발·검증** 가능하다.
- 권장 순서: **retrieval → ranking → active-set → revoke** (contract §5, matching §11).
- 추출·발현의 어려운 문제(정확도·프라이버시)와 **병렬 진행**한다.
