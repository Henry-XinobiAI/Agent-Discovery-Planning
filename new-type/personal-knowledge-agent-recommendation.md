# Personal Knowledge 기반 답변 가능 Agent·Agent Group 추천

> 상태: 설계 초안  
> 작성일: 2026-09-18  
> 범위: `bourbon-agent`, `bourbon-agent-discovery-api`, `bourbon-memory-api-v2` 사이의 새 추천 타입  
> 비범위: 기존 타입 ① 명시 추천, 타입 ② topic별 discovery, 타입 ③ for-you의 계약 변경

---

## 0. 요약

사용자의 personal agent가 질문에 답할 충분한 근거를 자신의 personal knowledge에서 찾지 못했을 때, 그 질문에 답할 근거를 가진 다른 사용자의 personal agent를 추천한다. 한 agent가 질문 전체를 커버하지 못하면 질문을 여러 `knowledge need`로 나누고, 서로 보완하는 두세 agent를 group으로 추천한다. group을 실제로 실행할 때는 각 agent가 자기 근거로 담당 부분만 답하고 coordinator가 답변을 종합한다.

이 기능의 핵심 경계는 다음과 같다.

- `bourbon-memory-api-v2`는 **누가 어떤 근거를 얼마나 보유하는지** 검색한다.
- `bourbon-agent-discovery-api`는 **누구를 추천하고 어떤 group을 만들지** 결정한다.
- 각 personal agent는 **자기 private memory만 사용해 담당 질문에 답한다.**
- coordination 계층은 **여러 답변을 종합하고 충돌과 빈 부분을 보존한다.**
- discovery와 coordinator는 다른 사용자의 원본 message·statement·provenance id를 읽거나 노출하지 않는다.

운영용 후보 검색은 memory-api에 배치형 capability/evidence 검색 계약을 추가하는 방향을 권고한다. 기존 단건 API 조합은 PoC에는 쓸 수 있지만, production에서는 N+1 호출, 부분 실패 판정, 저장 구조 결합, private data 과다 조회 문제가 있다.

권고 route 이름은 다음 중 하나다.

```http
POST /{tenant}/internal/personal/capabilities/search
```

또는:

```http
POST /{tenant}/internal/personal/evidence/search
```

`expertise/search`는 memory-api가 최종 전문가 판정과 추천 점수를 소유하는 것처럼 읽히므로 피한다.

---

## 1. 제품 시나리오

### 1-1. 단일 agent 추천

사용자가 자기 agent에게 질문한다.

> 홈 에스프레소 머신에서 압력이 너무 높을 때 추출을 어떻게 조정해야 해?

요청자의 agent는 자기 personal knowledge를 검색하지만 관련 절차·경험 근거가 부족하다. discovery는 질문을 분석하고, espresso extraction과 pressure adjustment에 관한 procedural 또는 experiential statement를 충분히 가진 다른 agent를 찾는다.

응답은 다음 의미를 가져야 한다.

> 이 질문은 내가 가진 근거만으로 답하기 어렵습니다. 에스프레소 추출 조정에 관한 경험 근거가 있는 agent를 연결할 수 있습니다.

추천 이유는 공개 가능한 capability metadata에만 근거한다. 타인의 private statement나 메시지 내용은 이유에 포함하지 않는다.

### 1-2. agent group 추천

사용자가 복합 질문을 한다.

> 도쿄에서 아이와 갈 만한 위스키 증류소 여행을 어떻게 계획할까?

질문은 최소 다음 need로 나뉠 수 있다.

1. 도쿄 근교 위스키 증류소
2. 어린이 입장 조건과 가족 방문 경험
3. 도쿄에서 증류소까지 이동 방법

한 agent가 세 need 모두에 충분한 근거를 가지면 단일 agent를 추천한다. 그렇지 않으면 예를 들어 다음 group을 구성한다.

- Agent A: 일본 위스키·증류소 경험, `n1`과 `n2` 담당
- Agent B: 도쿄 가족 여행·교통 경험, `n3` 담당

group 추천은 단순 상위 N명 목록이 아니다. required need 전체를 최소 인원으로 덮는 제한된 set-cover 문제다.

### 1-3. 추천하지 않는 경우

다음 경우에는 억지로 agent 또는 group을 만들지 않는다.

- required need 중 핵심 하나를 아무도 커버하지 못함
- grounding confidence가 임계값보다 낮음
- provenance가 없는 추론성 statement만 존재함
- consultable 동의를 한 후보가 없음
- 후보 검색이 일부 실패해 완전한 추천이라고 말할 수 없음
- 한 후보의 높은 owner-internal salience만으로 전문성이 있다고 오판할 위험이 큼

이 경우 결과는 `insufficient_coverage`, `no_consultable_agents`, `grounding_ambiguous`, `search_incomplete`처럼 서비스 상태와 지식 부족을 구분해야 한다. 외부 응답에서 숨은 후보의 존재를 누설하지 않는 규칙은 기존 discovery 불변식과 동일하게 유지한다.

---

## 2. 서비스 책임

| 책임 | 소유 서비스 | LLM |
|---|---|---|
| 요청자 자신의 근거 검색 | requester personal agent + memory-api | 없음 |
| 답변 가능성 1차 gate | requester personal agent | 없음 |
| 경계선 answerability 판정 | requester personal agent | 조건부 |
| 질문의 knowledge need 분해 | agent-discovery-api | 필요 |
| QID/공개 지식 후보 검색 | memory/public knowledge adapter | 없음 |
| 모호한 grounding 결정 | agent-discovery-api | 조건부 |
| cross-owner capability/evidence 검색 | memory-api | 없음 |
| consent·consultable 필터 | memory-api | 없음 |
| 단일 후보 랭킹 | agent-discovery-api | 없음 |
| group 구성 | agent-discovery-api | 없음 |
| 추천 이유 | agent-discovery-api | 기본은 템플릿, LLM 불필요 |
| 각 agent의 담당 답변 | 선택된 personal agent | 필요 |
| 답변 종합과 충돌 표현 | coordination 계층 | 필요 |

### 2-1. memory-api가 소유하는 것

memory-api는 personal knowledge의 저장 의미와 검색 의미를 소유한다.

- entity와 statement 검색
- QID identity/broader 매칭
- owner별 evidence 집계
- declarative/procedural/experiential/preference/intention 분류
- active·invalidated·superseded 상태
- grounding confidence와 last seen
- provenance 존재 여부
- 결과 truncation과 search completeness
- agent-consultable 정책 강제

memory-api는 최종 `expertise_score`나 agent 추천 순위를 만들지 않는다. 전문성을 무엇으로 볼지와 어떤 사용자를 추천할지는 discovery의 제품 정책이다.

### 2-2. discovery-api가 소유하는 것

- 질문 분해 결과인 knowledge need
- need 중요도와 required/optional 구분
- 후보별 coverage matrix
- cross-owner 신호의 calibration
- 단일 agent sufficiency threshold
- group set-cover와 group size 제한
- 요청자 본인 제외
- 추천 응답과 decision journal
- degradation·empty 결과 의미

### 2-3. agent/coordinator가 소유하는 것

discovery는 답변을 실행하지 않는다.

- requester agent는 자기 근거로 직접 답할지 discovery를 호출할지 결정한다.
- 선택된 agent는 자기 memory만 조회해 자신에게 할당된 질문을 답한다.
- coordinator는 선택된 agent의 공개 가능한 답변만 받아 종합한다.
- coordinator는 원본 private memory를 직접 조회하지 않는다.

---

## 3. 전체 요청 흐름

```text
User
  │ question
  ▼
Requester Personal Agent
  ├─ local personal evidence search
  ├─ deterministic answerability gate
  └─ optional LLM answerability judge
         │ insufficient
         ▼
Agent Discovery
  ├─ LLM: knowledge need decomposition
  ├─ search: QID candidate grounding
  ├─ optional LLM: ambiguous grounding decision
  ├─ Memory API: batch capability/evidence search
  ├─ deterministic single-agent ranking
  └─ deterministic group planning
         │ recommendation plan
         ▼
Coordinator / Bourbon Agent
  ├─ selected agents called in parallel
  ├─ each agent retrieves only its own evidence
  ├─ each agent returns structured claims
  └─ LLM synthesizes claims, conflicts and gaps
         │
         ▼
Final Answer
```

추천만 보여주는 UX라면 discovery 결과에서 멈춘다. 사용자가 추천을 수락하거나 제품이 자동 협업을 허용하면 그 뒤의 agent 실행과 종합이 시작된다. 이 둘은 별도 latency budget과 실패 계약을 가져야 한다.

---

## 4. 단계별 상세 설계와 LLM 경계

### S0. 요청자 자신의 근거 검색

요청자의 personal agent는 먼저 자기 personal knowledge를 검색한다.

확인 신호:

- 질문과 일치하는 entity·statement가 있는가
- statement가 active인가
- provenance가 존재하는가
- required concept를 얼마나 커버하는가
- procedural/experiential 지식이 필요한 질문에 해당 종류의 statement가 있는가
- 근거가 지나치게 오래되지 않았는가

명확한 충분/부족은 규칙으로 판정한다. 이 단계에 LLM을 기본 호출로 넣지 않는다.

### S1. 경계선 answerability 판정

검색 결과가 경계선일 때만 LLM을 쓴다. 모델은 자기 일반 지식이 아니라 검색된 근거가 질문을 지지하는지를 판단한다.

```json
{
  "can_answer": false,
  "coverage": 0.35,
  "missing_needs": [
    "증류소별 어린이 입장 정책",
    "도쿄에서의 이동 방법"
  ],
  "reason_code": "missing_required_evidence"
}
```

규칙:

- 모델 입력에는 요청자의 근거만 들어간다.
- `can_answer=true`는 입력으로 받은 evidence id 집합과 연결되어야 한다.
- 모델의 사전학습 지식만으로 충분 판정을 내려서는 안 된다.
- 결과 schema validation 실패는 부족 판정 또는 안전한 재시도로 수렴한다.

### S2. knowledge need 분해

discovery가 질문과 선택적 context를 구조화된 need로 변환한다. 이 단계는 LLM이 필요하다.

```json
{
  "needs": [
    {
      "need_id": "n1",
      "query": "도쿄 근교 위스키 증류소",
      "importance": "required",
      "knowledge_kind": "declarative"
    },
    {
      "need_id": "n2",
      "query": "증류소 어린이 입장과 가족 방문 경험",
      "importance": "required",
      "knowledge_kind": "experiential"
    },
    {
      "need_id": "n3",
      "query": "도쿄에서 증류소까지 이동 방법",
      "importance": "required",
      "knowledge_kind": "procedural"
    }
  ]
}
```

제약:

- need 수는 초기 1~5개로 제한한다.
- required와 optional을 구분한다.
- 모델은 owner나 agent를 선택하지 않는다.
- 모델은 실제 지식 검색 결과를 보지 않는다.
- 사용자 원문은 기존 explicit route와 동일하게 로그·예외·Sentry에 남기지 않는다.

### S3. 공개 지식 grounding

각 need를 memory personal knowledge가 사용하는 QID 공간에 연결한다.

1. alias·label·description으로 후보 검색
2. 후보가 명확하면 결정적 선택
3. 후보가 여러 개일 때만 LLM disambiguation
4. 모델이 고른 QID가 실제 후보 집합에 있는지 코드로 검증
5. 필요하면 broader QID를 함께 구성

LLM은 QID를 새로 만들어서는 안 된다. 선택지는 검색 결과의 후보 집합으로 제한한다.

여러 need가 동시에 모호하다면 need마다 순차 completion을 호출하지 않는다. 한 번의 구조화된 batch disambiguation으로 결정하거나 제한된 동시성으로 병렬 호출한다. 그렇지 않으면 질문 복잡도에 따라 latency가 선형 증가한다.

### S4. cross-owner capability/evidence 검색

이 단계는 online LLM 없이 OpenSearch query와 aggregation으로 처리한다.

입력 예시:

```json
{
  "requester_user_id": "uuid",
  "needs": [
    {
      "need_id": "n1",
      "text": "일본 위스키 증류소 방문 경험",
      "knowledge_kind": "experiential",
      "groundings": [
        {"qid": "Q0001", "match": "identity"},
        {"qid": "Q0002", "match": "broader"}
      ]
    },
    {
      "need_id": "n2",
      "text": "도쿄 가족 여행 이동 방법",
      "knowledge_kind": "procedural",
      "groundings": [
        {"qid": "Q0003", "match": "broader"}
      ]
    }
  ],
  "owner_limit": 100,
  "evidence_per_need": 5
}
```

응답 예시:

```json
{
  "owners": [
    {
      "owner_id": "uuid",
      "needs": [
        {
          "need_id": "n1",
          "matched_qids": ["Q0001"],
          "identity_matches": 1,
          "broader_matches": 2,
          "active_statement_count": 8,
          "procedural_statement_count": 1,
          "experiential_statement_count": 3,
          "hands_on_statement_count": 2,
          "grounding_confidence": 0.91,
          "last_seen_at": "2026-08-14T03:12:00Z",
          "provenance_available": true
        }
      ]
    }
  ],
  "truncated": false,
  "searched_needs": ["n1", "n2"]
}
```

반환하지 않는 정보:

- message body
- statement text
- message/conversation id
- 다른 사용자의 상세 private entity label
- 원문을 유추할 수 있는 owner note

필요하면 실제 선택된 agent가 자기 근거를 다시 찾는 데 쓸 수 있는 opaque·단기 `evidence_ref`를 반환할 수 있다. discovery나 requester가 그 ref로 타인의 원문을 읽을 수 있어서는 안 된다.

### S5. 단일 agent 랭킹

이 단계는 deterministic해야 한다.

초기 feature 후보:

- required need coverage
- optional need coverage
- QID identity/broader relation
- grounding confidence
- query-to-statement relevance
- 필요한 knowledge kind와 statement kind의 일치
- provenance availability
- evidence freshness
- evidence diversity
- hands-on evidence
- agent maturity 또는 응답 품질 신호가 있다면 별도 feature

개념식:

```text
single_score =
    required_coverage_gate
  × relevance
  × grounding_quality
  × evidence_sufficiency
  × freshness
  × provenance_quality
```

`salience`와 현재 `competence_score`는 owner 내부 척도다. 원시 값을 사용자 간 절대 순위로 쓰지 않는다. 쓰려면 owner별 분포를 정규화하거나, cross-owner 검증 데이터로 calibration한 feature로 변환한다.

한 agent가 모든 required need를 각 need threshold 이상으로 커버하면 단일 추천이 group보다 우선한다. 사람 수를 늘리는 것은 비용과 지연, 정보 노출 면적을 모두 늘린다.

### S6. agent group 계획

단일 agent가 충분하지 않을 때만 group planner가 동작한다. LLM은 필요하지 않다.

목표:

```text
group_score =
    required_need_coverage
  + evidence_quality
  + complementary_coverage
  + optional_need_coverage
  - member_count_cost
  - redundant_coverage_cost
  - weak_grounding_cost
```

초기 제약:

- 최대 인원 3명
- 모든 required need가 threshold 이상이어야 함
- 각 member는 최소 하나의 need에 실질적으로 기여해야 함
- 같은 need만 중복하는 member는 제외
- 후보 pool은 랭킹 상위 일정 수로 제한한 뒤 조합 탐색
- 핵심 need는 필요하면 두 agent의 독립 근거를 허용해 교차검증 가능

need가 최대 5개, 후보가 수십 명, group이 최대 3명이면 greedy set-cover 또는 bounded combination search로 충분하다. 이 문제에 LLM을 사용하면 결과 재현성과 decision log 설명 가능성이 떨어진다.

### S7. 추천 응답 assembly

추천 이유는 기본적으로 템플릿으로 만든다.

```text
일본 위스키와 증류소 방문 경험에 관한 근거가 있습니다.
도쿄 가족 여행과 대중교통 경험을 보완할 수 있습니다.
```

LLM 문장 생성은 품질상 필수가 아니며 private evidence를 모델에 전달할 유인이 생기므로 첫 버전에는 넣지 않는다.

### S8. 선택된 agent의 부분 답변

실제 협업이 시작되면 각 agent는 자신에게 할당된 sub-question만 받는다.

```json
{
  "need_id": "n2",
  "question": "해당 증류소를 아이와 방문한 경험이나 어린이 입장 조건은?",
  "answer_only_from_retrieved_evidence": true
}
```

각 agent는 자기 memory만 검색하고 구조화된 답을 반환한다.

```json
{
  "need_id": "n2",
  "status": "supported",
  "claims": [
    {
      "text": "...",
      "confidence": 0.82,
      "evidence_available": true,
      "observed_at": "2026-07"
    }
  ],
  "limitations": []
}
```

agent는 다음을 지켜야 한다.

- 자기 retrieval 결과 밖의 사실을 확정적으로 말하지 않음
- 다른 participant의 사적 발화를 그대로 인용하지 않음
- 답할 수 없는 need는 `unsupported`로 반환
- 공개 가능한 수준의 요약만 coordinator에 전달
- provenance는 내부 검증에 사용하되 raw message id/body를 반환하지 않음

### S9. group 답변 종합

coordinator LLM은 agent 답변만 입력으로 받는다. 원본 memory에는 접근하지 않는다.

역할:

- 중복 claim 병합
- need별 답변 연결
- 상충하는 claim 탐지
- confidence와 freshness 반영
- uncovered need 표시
- 자연어 최종 답변 생성

충돌은 임의로 지우지 않는다.

```json
{
  "agreements": [],
  "conflicts": [
    {
      "need_id": "n2",
      "claim": "어린이 입장이 가능한가",
      "positions": [
        {"agent_id": "A", "answer": "가능", "confidence": 0.70},
        {"agent_id": "B", "answer": "일부 프로그램만 가능", "confidence": 0.82}
      ]
    }
  ],
  "uncovered_needs": []
}
```

---

## 5. 추천 API 초안

기존 `POST /recommend/explicit`은 공개 topic 보유자를 찾는 타입이므로 그대로 둔다. 새 타입은 별도 route와 domain model을 가진다.

```http
POST /api/internal/svc/agent-discovery/recommend/knowledge
```

요청:

```json
{
  "user_id": "uuid",
  "question": "도쿄에서 아이와 갈 만한 위스키 증류소 여행을 어떻게 계획할까?",
  "context": "선택적인 현재 대화 맥락",
  "allow_group": true,
  "max_agents": 3,
  "room_id": "uuid",
  "lang": "ko"
}
```

응답:

```json
{
  "contract_version": 1,
  "recommendation_id": "uuid",
  "mode": "group",
  "needs": [
    {
      "need_id": "n1",
      "label": "일본 위스키 증류소",
      "importance": "required",
      "grounded_qids": ["Q0001"]
    },
    {
      "need_id": "n2",
      "label": "도쿄 가족 여행",
      "importance": "required",
      "grounded_qids": ["Q0003"]
    }
  ],
  "agents": [
    {
      "agent_id": "uuid",
      "owner_user_id": "uuid",
      "covers": ["n1"],
      "confidence": 0.87,
      "reason": "일본 위스키와 증류소 방문 경험에 관한 근거가 있습니다."
    },
    {
      "agent_id": "uuid",
      "owner_user_id": "uuid",
      "covers": ["n2"],
      "confidence": 0.81,
      "reason": "도쿄 가족 여행과 이동 경험을 보완할 수 있습니다."
    }
  ],
  "empty": false,
  "degraded": []
}
```

`confidence`는 “이 사람이 전문가일 확률”이 아니라 해당 질문 need를 검색된 evidence가 커버한다는 discovery의 calibrated confidence여야 한다. calibration 전에는 외부 필드로 열지 않고 decision log에만 두는 선택도 가능하다.

`mode` 후보:

- `single`
- `group`
- `none`

내부 empty/degradation 후보:

- `insufficient_coverage`
- `no_consultable_agents`
- `grounding_failed`
- `grounding_ambiguous`
- `memory_search_unavailable`
- `memory_search_incomplete`
- `expansion_partial`

숨은 후보가 있었는지 추정할 수 있는 상세 count나 거절 이유는 외부 응답에 싣지 않는다.

---

## 6. discovery domain 확장

기존 `TopicQuery`, `SourceHit`, `ExplicitRanker`에 이 타입을 끼워 넣지 않는다. 기존 타입은 공개 topic row의 tier와 topic coverage를 의미하고, 새 타입은 private memory에서 파생된 capability와 evidence sufficiency를 의미한다.

새 domain 후보:

```text
KnowledgeQuestion
KnowledgeNeed
GroundedNeed
KnowledgeQuery
NeedEvidence
ExpertiseHit
AgentCapability
SingleAgentPlan
AgentGroupPlan
KnowledgeRecommendation
```

새 stage 후보:

```text
AnswerabilityGate        requester agent 쪽 책임일 수 있음
KnowledgeDecomposition
KnowledgeGrounding
CapabilityRetrieval
CapabilityCalibration
KnowledgeRanking
GroupPlanning
KnowledgeAssembly
KnowledgeJournal
```

기존 explicit pipeline에서 재사용 가능한 것은 구조와 일부 구현이다.

- deadline orchestration
- structured LLM transport
- expansion/grounding의 후보 제한과 schema validation 방식
- digest 기반 private text logging 원칙
- decision journal 패턴
- requester self-exclusion

재사용하면 안 되는 의미:

- topic visibility를 personal knowledge consent로 간주
- `SourceHit.tier`에 private capability 의미를 억지로 넣기
- topic score를 evidence sufficiency로 간주
- 기존 `coverage`를 그대로 group coverage로 사용

---

## 7. 개인정보·권한 모델

현재 memory personal knowledge의 cross-owner route는 tenant 경계 외에 `public/friends/private` 의미가 없다. 현행 API가 존재한다는 사실은 추천 또는 제3자 agent 답변에 대한 사용자 동의를 의미하지 않는다.

최소한 다음 정책 축이 필요하다.

```text
discoverable       다른 사용자의 질문에서 capability 후보로 발견될 수 있음
consultable        다른 agent가 질문을 보낼 수 있음
answer_share_scope public | friends | nobody
evidence_share     none | summary | citations
```

정책 강제 위치:

- `discoverable`과 `consultable`은 memory capability search 또는 그 앞의 authoritative projection에서 필터한다.
- discovery가 private 후보를 모두 받은 뒤 필터하지 않는다. 그 시점에는 이미 불필요한 private metadata를 읽었다.
- 실제 답변 시점에 agent가 `answer_share_scope`를 다시 확인한다. 추천 시점의 권한은 실행 시점의 권한을 보장하지 않는다.
- 답변 직전 recheck가 실패하면 해당 agent를 제외하고, group required coverage가 깨지면 partial answer 또는 실행 중단으로 처리한다.

topic-api의 user-topic `public/friends/private`나 block visibility는 personal knowledge consultation 동의로 재사용하지 않는다. 관심사를 공개하는 것과 사적 대화에서 배운 지식을 대신 답하게 하는 것은 노출 강도가 다르다.

### 7-1. 모델 제공자 경계

- 다른 owner의 raw personal memory를 discovery LLM에 보내지 않는다.
- 선택된 agent의 LLM에는 그 agent 자신의 retrieval 결과만 보낸다.
- coordinator LLM에는 각 agent가 공개 가능한 형태로 만든 answer claims만 보낸다.
- 로그·Sentry·decision journal에는 질문과 답변 원문 대신 digest, 길이, count, reason code만 기록한다.

---

## 8. 예상 지연 시간

### 8-1. 전제

아래 수치는 SLA가 아니라 첫 구현의 latency budget을 잡기 위한 추정이다.

확인된 기준점:

- 현행 discovery의 LLM 기반 text→topic 실측은 disambiguation을 켠 조건에서 약 **p50 1.77초 / p95 3.11초**다.
- 같은 검증에서 타입 ① 전체의 약 98%가 모델 호출이었다.
- PostgreSQL topic 후보 조회 자체는 10만 합성 유저에서 한 자릿수 ms였다.
- 현행 `LLM_PROXY_TIMEOUT_SECONDS`는 시도당 6초, 최대 2회이고 pipeline deadline은 20초다.
- memory capability batch search는 아직 구현·실측되지 않았다. 아래 OpenSearch 구간은 동일 리전 내부 호출과 bounded aggregation을 가정한 추정이다.

따라서 새 타입도 모델 호출 수를 제한하지 않으면 storage 최적화보다 LLM 호출 수가 p95를 결정한다.

### 8-2. 추천만 생성하는 경로

| 단계 | LLM | 예상 p50 | 예상 p95 | 비고 |
|---|---:|---:|---:|---|
| S0 로컬 personal evidence 검색 | 아니오 | 40~120 ms | 150~350 ms | owner-scoped OpenSearch |
| S1 deterministic answerability gate | 아니오 | < 5 ms | < 10 ms | 애플리케이션 계산 |
| S1 경계선 answerability judge | 조건부 | 0.6~1.5 s | 2.5~5 s | 명확한 miss에는 생략 |
| S2 need decomposition | 예 | 0.8~1.8 s | 2.5~4.5 s | 출력 1~5 needs |
| S3 QID 후보 검색 | 아니오 | 30~100 ms | 150~400 ms | batch query 권고 |
| S3 grounding disambiguation | 조건부 | 0.5~1.5 s | 2~4 s | batch completion 1회 권고 |
| S4 memory capability batch search | 아니오 | 80~250 ms | 400~900 ms | 구현 후 반드시 실측 |
| S5 후보 calibration·랭킹 | 아니오 | 2~15 ms | 30~80 ms | 후보 상한 100 가정 |
| S6 group planning | 아니오 | 1~10 ms | 20~50 ms | 최대 3명, bounded search |
| S7 hydration·권한 recheck·assembly | 아니오 | 20~100 ms | 150~400 ms | agent metadata store 포함 |
| journal write | 아니오 | 3~20 ms | 30~100 ms | 응답을 막지 않는 방식 검토 |

예상 end-to-end:

| 경로 | 예상 p50 | 예상 p95 | 설명 |
|---|---:|---:|---|
| 명확한 local miss, grounding 모호성 없음 | 1.2~2.5 s | 3.5~6 s | decomposition 1회가 대부분 |
| grounding LLM 필요 | 2~4 s | 5~9 s | batch disambiguation 1회 |
| answerability judge까지 필요 | 2.5~5 s | 7~12 s | requester 쪽 LLM이 앞에 추가 |
| warm cache + 단순 단일 need | 0.9~2 s | 3~5 s | grounding/search cache 적중 |

현재 20초 discovery deadline 안에는 들어오지만, LLM 재시도가 겹치면 꼬리는 쉽게 20초에 접근한다. need마다 순차 disambiguation을 하면 안 되는 이유다.

### 8-3. 실제 단일 agent 답변까지 생성하는 경로

추천 이후 다음 비용이 추가된다.

| 단계 | 예상 p50 | 예상 p95 |
|---|---:|---:|
| 선택 agent의 자기 evidence 재조회 | 50~250 ms | 300~800 ms |
| agent answer completion | 1~4 s | 6~12 s |
| 공개 정책·schema 검증 | 5~30 ms | 50~150 ms |

추천부터 실제 답변까지의 전체 추정은 **p50 3~7초 / p95 10~20초**다. 모델·프롬프트·출력 길이에 따라 변화가 크므로 첫 구현에서 실측해야 한다.

### 8-4. 2~3 agent group 답변까지 생성하는 경로

agent 호출은 반드시 병렬 실행한다. 순차 실행은 member 수만큼 latency가 증가한다.

| 단계 | 예상 p50 | 예상 p95 | 비고 |
|---|---:|---:|---|
| 2~3 agent retrieval + answer 병렬 | 2~6 s | 8~15 s | 가장 느린 member가 경로를 결정 |
| coordinator synthesis | 1~3 s | 5~8 s | claim 수와 출력 길이에 영향 |
| 전체: discovery + group 실행 + synthesis | 5~10 s | 15~25 s | 일부 agent timeout 제외 정책 필요 |

현행 discovery의 20초 deadline을 group execution 전체에 공유하면 부족할 수 있다. 권고는 추천과 실행을 분리하는 것이다.

```text
knowledge recommendation deadline: 8~12초 목표, hard cap 20초
agent member deadline: member당 8~12초
group coordination deadline: 전체 20~30초
```

정확한 값은 e3llm 처리량과 실제 answer token 분포를 확인한 뒤 설정 레지스터에 넣는다. 위 숫자를 코드 상수로 복사하지 않는다.

### 8-5. latency를 줄이는 핵심 규칙

1. local answerability의 명확한 경우는 LLM 없이 처리한다.
2. need decomposition과 query expansion을 가능하면 completion 하나에서 만든다.
3. 여러 need의 grounding 후보 검색은 batch로 호출한다.
4. 여러 모호한 need의 disambiguation은 한 번의 구조화 completion으로 제한한다.
5. memory capability 검색은 need 전체를 받는 단일 batch API로 만든다.
6. owner별 상세 조회 N+1을 금지한다.
7. group member answer는 병렬 실행한다.
8. coordinator는 raw memory가 아니라 짧은 structured claims만 받는다.
9. recommendation-only 응답과 full answer 실행을 API와 timeout에서 분리한다.

---

## 9. 실패와 degradation

| 실패 | 추천 단계의 처리 | 실행 단계의 처리 |
|---|---|---|
| requester local memory unavailable | discovery로 바로 넘기지 않고 상태 구분 | 사용자에게 자기 근거 확인 실패 표시 |
| decomposition LLM unavailable | fallback 분해가 가능하면 1개 verbatim need | `expansion_partial` 또는 503 |
| grounding 후보 없음 | 422 성격의 grounding failure | 실행하지 않음 |
| grounding 일부 모호 | required need면 중단, optional이면 degradation 검토 | 빠진 need 표시 |
| memory capability search unavailable | 추천 불가 | 503 |
| memory 결과 truncated | 완전성 threshold에 따라 degraded 또는 재조회 | group coverage 과대평가 금지 |
| candidate recheck 실패 | 후보 제거 후 재계산 | required coverage가 깨지면 partial/중단 |
| 한 group member timeout | 남은 member로 required coverage 재계산 | 빈 need를 명시하거나 중단 |
| agent가 unsupported 반환 | 다른 후보로 한 번 대체 가능 | 그래도 실패하면 uncovered로 표시 |
| agent 답변 간 충돌 | 추천 실패가 아님 | 최종 답변에 conflict 보존 |
| coordinator LLM 실패 | structured agent answers는 유지 | 개별 답변을 분리해 반환할지 제품 결정 |

재시도는 한 계층만 소유한다. discovery가 memory client를 재시도하고 memory가 같은 OpenSearch 요청을 다시 중첩 재시도하는 식으로 두 사다리를 두지 않는다. LLM도 transport retry와 pipeline retry를 중첩하지 않는다.

---

## 10. 관측과 decision journal

원문을 기록하지 않고 다음을 기록한다.

```text
question_digest
question_chars
context_chars
needs_total
needs_required
needs_grounded
needs_ambiguous
grounding_llm_calls
capability_candidates
consultable_candidates
single_sufficient
group_size
covered_required_needs
uncovered_required_needs
memory_truncated
degraded[]
latency_ms.local_search
latency_ms.answerability
latency_ms.decompose
latency_ms.grounding_search
latency_ms.grounding_llm
latency_ms.capability_search
latency_ms.rank
latency_ms.group_plan
latency_ms.assemble
latency_ms.total
```

full execution을 별도 journal로 기록한다.

```text
recommendation_id
coordination_id
members_requested
members_answered
members_timed_out
needs_supported
needs_unsupported
conflict_count
synthesis_llm_calls
latency_ms.member_max
latency_ms.synthesis
latency_ms.total
```

금지:

- 질문·context 원문
- 타인의 statement·message 원문
- provenance message ids
- agent 답변 원문 전체
- owner별 private entity 목록

핵심 알람 후보:

- `memory_search_unavailable`
- `memory_search_incomplete`
- `grounding_disambiguation_failed`
- discovery deadline
- group member timeout 비율
- coordinator failure
- `unsupported`가 추천 confidence와 모순되는 비율
- 추천 당시 coverage와 실행 당시 실제 answerability의 calibration error

마지막 항목은 이 기능의 핵심 품질 지표다. “잘 알 것이라고 추천했는데 실제 agent가 답하지 못한 비율”을 계속 측정해야 한다.

---

## 11. 평가 지표

### 11-1. retrieval

- relevant owner recall@K
- irrelevant owner precision@K
- required need coverage
- consultable 정책 위반 0건
- requester self-inclusion 0건
- hidden candidate existence leakage 0건

### 11-2. 단일 추천

- 추천 agent의 실제 `supported` 응답 비율
- confidence calibration
- procedural 질문에서 procedural/experiential evidence가 선택된 비율
- entity만 일치하고 질문 predicate는 맞지 않는 false positive 비율

### 11-3. group

- required need coverage
- 평균 group size
- 불필요한 member 비율
- redundant coverage 비율
- oracle 최소 group 대비 member 수 차이
- group 추천 후 실제 uncovered need 비율

### 11-4. 답변

- evidence-supported claim 비율
- unsupported claim 비율
- conflict 보존율
- stale evidence 경고 정확도
- 사용자 만족도 또는 후속 대화 지속률

offline 합성 데이터만으로는 실제 answerability를 완전히 검증할 수 없다. owner personal knowledge에서 질문·정답·근거를 생성하되, 평가 세트 생성에 사용한 statement를 추천 모델 입력으로 직접 노출하지 않는 분리가 필요하다.

---

## 12. 구현 단계

### Phase A. 기존 API를 이용한 PoC

- 기존 `/personal/grounded/{qid}/entities`
- 기존 `/personal/themes/{qid}/owners`
- 소수 후보에 대한 owner-scoped statement 확인
- discovery 내부에서 temporary coverage matrix 구성

목표는 필요한 feature와 false positive 유형을 찾는 것이다. production latency나 privacy 경계의 최종 형태로 보지 않는다.

완료 조건:

- 실제 질문 세트에서 단일/group 구분 가능
- 어떤 statement kind가 answerability에 유효한지 확인
- owner-internal salience/competence의 cross-owner 오차 측정
- batch API 응답 필드 확정

### Phase B. memory capability batch API

- multi-need batch request
- QID identity/broader + statement text 검색
- owner aggregation
- consultable 필터
- truncation/completeness 계약
- raw prose 없는 응답
- OpenSearch 부하·p50·p95 측정

### Phase C. discovery 새 추천 타입

- `KnowledgeQuery` 계열 domain
- decomposition·grounding
- capability source
- single ranker
- group planner
- assembly와 decision journal
- API contract와 typed failures

### Phase D. agent 실행

- per-agent scoped question contract
- 자기 memory evidence retrieval
- structured claims
- 실행 시점 consent recheck
- 병렬 호출과 member timeout

### Phase E. coordination

- claim merge
- conflict detection
- uncovered need
- final synthesis
- full execution journal

### Phase F. projection 최적화 검토

요청량이 커져 memory-api의 실시간 aggregation이 병목이면, consultable capability만 이벤트로 발행해 discovery에 projection을 둘 수 있다.

projection에는 raw statement나 message id를 넣지 않는다. memory-api가 system of record이고, discovery projection은 검색 가능한 공개 capability의 파생본이다. 삭제·동의 철회·rebuild event가 빠지면 private 후보가 잔존할 수 있으므로, 이벤트 계약과 정기 full reconciliation이 먼저 필요하다.

---

## 13. 열린 결정

1. `discoverable`, `consultable`, `answer_share_scope`, `evidence_share`를 어느 서비스가 저장하는가.
2. 기존 agent 공개 설정과 consultable을 분리할 것인가.
3. requester가 추천을 수락한 뒤에만 agent를 실행할지, 자동 실행할지.
4. agent group 최대 인원을 2명으로 시작할지 3명으로 시작할지.
5. required need 하나가 비었을 때 partial answer를 허용할지.
6. 충돌하는 agent 답변을 사용자에게 어떤 UI로 보여줄지.
7. discovery 응답에 calibrated confidence를 노출할지 내부에만 둘지.
8. `evidence_ref`가 필요한지, 필요하다면 누가 redeem할 수 있는지.
9. memory capability search가 free-text statement 검색까지 맡을지, QID 기반 검색만 첫 버전에 넣을지.
10. 추천 결과와 실제 answerability의 feedback event 이름과 payload.
11. agent owner가 답변 사용 내역을 확인하거나 거부할 수 있어야 하는지.
12. 추천-only와 full coordination을 동기 API로 둘지, coordination만 비동기 job/stream으로 둘지.

---

## 14. 권고안

첫 production slice는 다음으로 제한한다.

- requester agent가 명확한 local miss일 때만 호출
- knowledge need 최대 3개
- memory capability batch API는 QID + statement full-text를 함께 사용
- consultable opt-in이 있는 owner만 반환
- 단일 agent 우선
- group 최대 2명
- recommendation과 agent 실행은 분리
- discovery 경로 LLM은 decomposition 1회, 필요 시 batch disambiguation 1회까지
- agent 답변은 병렬 실행
- coordinator는 structured claims만 입력으로 받음
- raw provenance는 owner agent 밖으로 나오지 않음
- latency 목표는 추천 p50 2.5초 이내, p95 6초 이내에서 시작하되 실측 후 확정
- full group answer는 별도 budget으로 p50 10초 이내를 초기 목표로 두고 p95를 우선 관측

이 순서라면 personal knowledge의 강점인 구체적 entity·statement·provenance를 활용하면서도, 다른 사용자의 private memory를 discovery 데이터로 바꾸는 위험을 피할 수 있다. 또한 단일 추천 품질을 먼저 검증한 뒤 group orchestration 비용과 복잡도를 추가할 수 있다.
