# Agent Event-driven Architecture — 핵심 아이디어

## 1. 핵심 결론

> **상태 변화가 일어나면 로그 기반 이벤트 버스에 이벤트를 쌓고, 각 컴포넌트가 자기가 관심 있는 이벤트를 구독해 비동기로 일한다.**
> 실시간 대화 응답 경로(serving)는 이와 분리해 빠르고 얇게 유지한다.

API와 Agent가 모든 일을 직접 처리하지 않는다. 페르소나 생성, 메모리화, public 승인·관리, 추천, 콘텐츠화, safety/audit 등은 전부 이벤트를 소비하는 별도 컴포넌트가 비동기로 맡는다. 새 기능이 붙어도 **새 consumer를 이벤트 버스에 추가**하면 되고, serving 경로와 producer는 건드리지 않는다.

이 문서의 코어는 두 가지다.

1. **로그 기반 이벤트 버스**(Kafka API 계열)를 중심에 둔다 → 3장.
2. **각 컴포넌트는 consumer**로서 이벤트를 받아 자기 책임만 처리한다 → 6장.

---

## 2. 기존 구성 (요약)

현재 실시간 대화 경로는 다음과 같고, 이 구조 자체는 유지한다.

```text
Client ─(WebSocket)→ API ─(command)→ AMQP ─→ Agent
                      ▲                          │
                      └────(NDJSON streaming)────┘
                      └────(WebSocket)──────────→ Client
```

- **Client ↔ API**: WebSocket (양방향)
- **API → AMQP → Agent**: command
- **Agent → API**: NDJSON streaming → API가 WebSocket으로 Client에 중계

여기에 **이벤트 버스와 background consumer 계층을 추가**하는 것이 이 문서의 제안이다.

---

## 3. 코어 — 로그 기반 Event Bus

### 3.1 Command Queue와 Event Bus를 나눈다

둘을 섞으면 실패 처리·retry·idempotency·ownership이 전부 애매해진다.

| | Command | Event |
|---|---|---|
| 의미 | "이 일을 처리해줘" | "이런 일이 일어났다" |
| 수신자 | 특정 consumer 지정 | 모르고 발행, 필요한 쪽이 구독 |
| 예시 | `GenerateAgentResponse` | `ConversationTurnCompleted`, `MemoryCandidateApprovedAsPublic` |
| 인프라 | **AMQP** (기존 MQ) | **로그 기반 이벤트 버스** |

→ **기존 AMQP는 Command Queue로 유지**, 도메인 이벤트는 별도의 로그 기반 버스로. (AMQP는 전송 프로토콜 이름이고, 그 위의 논리 역할이 Command Queue다.)

### 3.2 왜 로그 기반(Kafka API 계열)인가

이벤트 버스가 충족해야 하는 건 단순 task 분배가 아니라 **독립 consumer 다중 fan-out + replay**이고, 둘 다 로그 기반의 본질적 강점이다.

- **다중 consumer group**: 하나의 `ConversationTurnCompleted`를 Memory·Persona·Analytics·Content가 각자 자기 offset으로 독립 소비한다. 로그 기반의 기본 동작이다.
- **replay (운영 필수)**: 어떤 processor에 버그가 있어 고쳤을 때, 지난 N일 이벤트를 offset 되감기로 재처리한다.
- **aggregate 단위 순서 보장**: `conversation_id`를 파티션 키로 쓰면 한 대화의 이벤트 순서가 유지된다.
- **consumer 추가 = 토픽 구독 추가**: producer를 건드리지 않고 새 기능을 붙인다.

> 구현체: 클라우드 비종속·작은 팀이면 **Redpanda**(Kafka API 호환, 단일 바이너리)를 기본값으로 추천. GCP면 Pub/Sub, AWS면 MSK Serverless. Kafka 호환을 유지하면 나중에 갈아타도 코드가 안 바뀐다.
>
> 초기엔 물리적으로 하나의 시스템으로 시작해도 되지만, **command와 event는 논리적으로 반드시 분리**해 토픽/consumer group을 처음부터 나눠둔다.

### 3.3 이벤트 발행 주체 = 상태를 commit하는 쪽

이벤트 producer는 **API(또는 그 뒤 Conversation Service)** 다. Agent는 응답을 생성·스트리밍하고 메타데이터(사용한 memory id 등)를 API에 넘길 뿐, **이벤트 버스에 직접 발행하지 않는다.**

- 원칙: 상태를 commit하는 쪽이 **같은 트랜잭션의 outbox**로 이벤트를 발행한다(Transactional Outbox). DB 저장과 이벤트 발행 사이 정합성을 보장.
- 효과: Agent는 stateless하게 유지되고, producer가 한 곳으로 모인다.
- consumer 측: duplicate delivery가 있어도 결과가 깨지지 않게 **모든 consumer는 idempotent**해야 한다(처리한 event는 skip).

> DB = source of truth, Event Bus = state change notification / 후처리 trigger. 완전한 event sourcing은 초기에 복잡도가 너무 높다.

---

## 4. 두 개의 경로

### 4.1 Serving Path (동기, 얇게)

```text
1. Client → user message (WS)
2. API가 UserMessage 저장 (+ outbox)
3. API가 GenerateAgentResponse command 발행
4. Agent Worker가 consume → context retrieval → 응답 생성
5. Agent가 NDJSON으로 API에 스트리밍 (+ 사용한 memory id 등), API가 WS로 Client에 중계
6. API가 최종 AgentMessage 저장 (+ outbox)
```

serving에서 하는 것: 메시지 저장 / command 발행 / context·memory retrieval / 응답 생성 / streaming / 최종 저장.
serving에서 **빼는 것**: memory extraction, persona update, public 후보 생성, 추천, content draft, summary, analytics — 전부 이벤트로 넘겨 비동기 처리.

> **읽기는 동기, 쓰기는 비동기**: 서빙 시 Agent는 그 시점의 최신 스냅샷을 읽는다(eventual consistency). 방금 대화에서 추출될 memory는 다음 턴부터 반영된다.

### 4.2 Learning / Processing Path (비동기, 이벤트 소비)

핵심: 모든 consumer가 `ConversationTurnCompleted` 하나를 병렬로 받는 게 아니라 **이벤트 체인**을 이룬다. 특히 public 계열은 turn 이벤트가 아니라 **승인 이벤트**를 트리거로 한다.

| 트리거 이벤트 | consumer | 한 일 |
|---|---|---|
| `ConversationTurnCompleted` | Memory Processor | private memory / public 후보 생성 |
| `ConversationTurnCompleted` | Persona Processor | 페르소나(축별 모델) 업데이트 |
| `ConversationTurnCompleted` | Content Processor | post / snapshot 등 **후보** 생성 |
| `ConversationTurnCompleted` | Analytics Processor | 지표 적재 |
| `MemoryCandidateCreated` | Safety Processor | 민감정보·사칭·abuse check |
| `MemoryCandidateApprovedAsPublic` | Public Knowledge Processor | 승인된 public을 발견 인덱스(SKL)에 반영 |
| `PublicKnowledgeIndexed` | Recommendation Processor | 추천 후보 갱신 |

```text
[turn 단계]    ConversationTurnCompleted → Memory / Persona / Analytics / Content(후보)

[승인 후 단계] MemoryCandidateApprovedAsPublic → Public Knowledge Processor
                 → PublicKnowledgeIndexed → Recommendation Processor
```

> **승인 게이트(이벤트 트리거 관점)**: 비동기 processor는 public **후보 생성까지만** 한다. public 확정·발견 인덱스 반영은 **사용자 승인 이벤트(`MemoryCandidateApprovedAsPublic`) 이후에만** 일어난다. SKL의 입력은 raw conversation이 아니라 승인된 public이어야 한다. (이게 메모리 문서의 "publish". 모델 디테일은 메모리 문서 참조.)

### 4.3 비용 게이트 (per-turn)

매 턴마다 LLM으로 추출·갱신을 돌리면 비용이 폭발하고 대부분 무의미하다.

- `ConversationTurnCompleted`에 먼저 **싸구려 salience 게이트**(룰/소형 분류기)를 걸어, 가치 있는 턴만 비싼 LLM 추출로 보낸다.
- 또는 세션 경계·유휴 시점에 배치로 모아 돌린다.
- Analytics처럼 가벼운 처리만 매 턴 무조건 수행한다.

---

## 5. 아키텍처 다이어그램

```text
                         ┌────────────────────┐
                         │       Client        │
                         └─────────┬──────────┘
                                   │ WebSocket (양방향)
                                   ▼
                         ┌────────────────────┐
                         │        API          │
                         │ WS ↔ NDJSON gateway │
                         └──────┬───────▲─────┘
                 command publish│       │NDJSON (Agent→API)
                                ▼       │
                         ┌────────────────────┐
                         │ Command Queue (AMQP)│
                         └─────────┬──────────┘
                                   ▼
                         ┌────────────────────┐
                         │ Agent Worker        │  (stateless)
                         └─────────┬──────────┘
                                   │ NDJSON → API (API가 최종 저장)
                                   ▼
                         ┌────────────────────┐
                         │ Conversation Store  │  ← API가 write
                         └─────────┬──────────┘
                                   │ domain events via outbox
                                   ▼
                ┌──────────────────────────────────────┐
                │   Event Bus (로그 기반, Kafka API)      │
                └──┬────┬────┬────┬────────────────┬───┘
                   │    │    │    │                │
        ┌──────────┘    │    │    └──────┐         └─────────┐
        ▼               ▼    ▼           ▼                   ▼
┌──────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────────────┐
│   Memory     │ │  Persona   │ │  Analytics │ │     Safety       │
│  Processor   │ │ Processor  │ │  Processor │ │   Processor      │
└──────┬───────┘ └────────────┘ └────────────┘ └──────────────────┘
       │ user 승인 → MemoryCandidateApprovedAsPublic
       ▼
┌──────────────────────┐   PublicKnowledgeIndexed   ┌──────────────────┐
│ Public Knowledge     │ ─────────────────────────▶ │ Recommendation   │
│ Processor            │                            │ Processor        │
└──────────────────────┘                            └──────────────────┘
```

---

## 6. 컴포넌트 책임 — 무엇을 소비해 무엇을 하는가

각 컴포넌트는 consumer group이다. "구독하는 이벤트 → 하는 일"로 본다.

| 컴포넌트 | 구독 이벤트 | 하는 일 | 하면 안 되는 것 |
|---|---|---|---|
| **API / Conv. Service** | (producer) | auth·validation, 메시지 저장, Client WS 유지, command 발행, **outbox로 이벤트 발행**, read model 제공 | 직접 memory·persona 처리, 무거운 LLM 후처리 |
| **Agent Worker** | command consume | context retrieval, LLM 응답 생성, NDJSON 스트리밍, 사용한 memory·grounding 메타데이터 반환 | **최종 저장·이벤트 직접 발행**, 정책 결정 (stateless 유지) |
| **Memory Processor** | `ConversationTurnCompleted` | candidate 추출·분류, private/pending/public 분리 | **public 확정**(승인 필요) |
| **Persona Processor** | `ConversationTurnCompleted` | 축별 페르소나 업데이트, prompt용 user model 생성 | — |
| **Public Knowledge Processor** | `MemoryCandidateApprovedAsPublic` 등 | 승인된 public을 발견 인덱스(SKL)에 반영·삭제, source attribution 유지 | 승인 안 된 것 반영 |
| **Recommendation Processor** | `PublicKnowledgeIndexed` | 추천 후보 생성(비동기) + ranking(요청 시 동기) | — |
| **Content Processor** | `ConversationTurnCompleted` | snapshot/post/summary **후보** 생성 | 게시·public 전환(승인 필요) |
| **Safety / Audit Processor** | `MemoryCandidateCreated` 등 | 민감정보·사칭·abuse 검사, report, audit log | — |

---

## 7. Event 카탈로그 (타입 예시)

> 어떤 event가 흐르는지 감을 주기 위한 **타입 예시**다.

- **Conversation**: `UserMessageCreated`, `AgentMessageCompleted`, `ConversationTurnCompleted`, `ConversationSummarized`
- **Memory**: `MemoryCandidateCreated`, `MemoryCandidateApprovedAsPublic`, `MemoryCandidateRejected`, `MemoryDeleted`, `MemoryUsedInAgentResponse`
- **Persona**: `UnderstandingAxisUpdated`, `PersonaSnapshotCreated`, `OnboardingCompleted`
- **Public Knowledge**: `PublicMemoryApproved`, `PublicMemoryRevoked`, `PublicKnowledgeIndexed`, `PublicKnowledgeRemoved`
- **Recommendation**: `RecommendationShown`, `RecommendationClicked`, `FollowCreated`
- **Safety**: `MessageFlagged`, `UserReported`, `UserBlocked`, `PublicMemorySafetyRejected`

두 가지 주의:

- **턴 종료 정의**: 한 턴에 tool call로 여러 `AgentMessage`가 생길 수 있다. `AgentMessageCompleted`(개별 메시지 완료)와 `ConversationTurnCompleted`(턴당 한 번)를 구분한다. 모든 후처리 트리거는 `ConversationTurnCompleted`이므로 "무엇이 턴을 닫는가"를 명확히 정의해야 한다.
- **token 단위 event는 이벤트 버스에 흘리지 않는다**: token streaming은 NDJSON/WebSocket path에서 처리하고, 버스에는 completion 이벤트만 발행한다.

**P0 (최소)**: `UserMessageCreated`, `AgentMessageCompleted`, `ConversationTurnCompleted`, `MemoryCandidateCreated`, `MemoryCandidateApproved/Rejected`, `MemoryDeleted`, `PublicMemoryApproved/Revoked`, `RecommendationShown/Clicked`, `UserFollowed`, `UserBlocked`.

---

## 8. 처리 흐름 예시

### 8.1 일반 대화 1턴

```text
1. Client → user message (WS)
2. API가 UserMessage 저장, UserMessageCreated 발행
3. API가 GenerateAgentResponse command 발행
4. Agent가 consume → retrieval → 응답 생성
5. Agent가 NDJSON으로 API에 스트리밍, API가 WS로 Client에 중계
6. API가 최종 AgentMessage 저장
7. API가 AgentMessageCompleted / ConversationTurnCompleted 발행 (outbox)
8. (salience 통과 시) Memory / Persona Processor가 consume, Analytics는 무조건
```

### 8.2 삭제 / revoke 흐름 (생성만큼 중요)

```text
User deletes public memory → MemoryDeleted
  → Public Knowledge Processor가 발견 인덱스에서 제거
  → Recommendation Processor가 관련 추천 무효화
  → context cache 무효화 → Audit log 기록
```

**public 삭제·visibility 변경 시 발견 인덱스·추천에서도 반드시 제거**되어야 한다. 프라이버시 신뢰가 여기서 결정된다.

---

## 9. MVP 구현 전략

처음부터 모든 component를 microservice로 나누지 않는다.

```text
API Service
Agent Worker
Background Worker   ← Memory/Persona/PublicKnowledge/Recommendation/Content/Safety를 모듈로
Event Bus (로그 기반, Kafka API 계열)
Command Queue (AMQP, 기존 MQ)
Main DB
Object Storage
```

- 처음엔 하나의 worker process여도 되지만, **토픽 / consumer group / processor module은 처음부터 분리**해둔다.
- 병목 시 분리 순서: Memory → Recommendation → PublicKnowledge → Safety.

**WebSocket 응답 라우팅 (멀티 인스턴스 주의)**: Client WS는 특정 API 인스턴스에 핀되지만 command는 임의의 Agent worker가 consume한다. 따라서 Agent의 NDJSON 응답은 **그 클라이언트의 WS를 든 바로 그 API 인스턴스**로 돌아와야 한다 — connection/session id로 키된 reply 채널이 필요하다. MVP부터 정해야 멀티 인스턴스 스트리밍이 동작한다.

---

## 10. 최종 권장안

> 상태 변화는 **로그 기반 이벤트 버스**에 outbox로 발행하고, 각 컴포넌트는 **consumer group**으로 자기 이벤트를 소비해 비동기로 일한다.
> Agent는 실시간 응답 생성에 집중하고 stateless하게 유지한다.
> Command queue(AMQP)와 event bus(로그 기반)는 논리적으로 분리한다.
> DB를 source of truth로 두고, event는 후처리·동기화 trigger로 쓴다.
> public/발견 인덱스는 반드시 사용자 승인 이벤트 이후에만 반영한다. (메모리 모델 디테일은 메모리 문서 소관.)
