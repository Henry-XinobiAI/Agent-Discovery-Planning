# Agent Event-driven Architecture 제안

> **정합성 노트**: 이 문서는 `personalized_agent_memory_and_perspective_network.md`(이하 "메모리 문서")의 런타임/인프라 짝이다. 메모리 문서가 "무엇을(개념 모델)"을 정의하고, 이 문서는 "어떻게 흘리고 처리하는가(event-driven)"를 정의한다. 용어와 불변식은 메모리 문서를 기준으로 맞춘다.
>
> **용어 매핑**
> - 이 문서의 **public memory** = 메모리 문서의 **Public Agent Memory**
> - 이 문서의 **SKL (Shared Knowledge Layer)** = 메모리 문서의 **SKL** (= Topic Space + Perspective Index)
> - 이 문서의 **Persona / Understanding(축별 모델)** = 메모리 문서의 **Persona**
> - **Perspective Card** = Memory ∩ Persona를 공개 가능한 형태로 투영한 것 (양 문서 공통, Perspective Index의 최소 단위)
>
> **이 문서가 지켜야 하는 핵심 불변식** (메모리 문서 기준)
> - **Private는 하드 월**: 외부 대화에서 접근 경로 자체가 없다. 타 에이전트가 참조 가능한 것은 Public Agent Memory뿐이다.
> - **publish = 사용 권한 + 발견 권한 묶음**(MVP)이며, 반드시 **주인 승인 후**에만 일어난다.
> - **SKL = Public Agent Memory의 projection**: 단일 진실 원천은 Public Agent Memory이고, SKL은 언제든 재빌드 가능하다.
> - **SKL 갱신은 debounce 비동기 배치**, active-set은 **freshness·confidence 결합 축출**로 관리한다.
> - **발견 랭킹은 confidence/freshness를 분리**한다 (freshness는 hard cutoff가 아니라 decay 가중치).

## 1. 배경

현재 구조는 다음과 같다.

```text
Client  ⇄(WebSocket)  API
                        │  유저 질의 → MQ (command)
                        ▼
                      Agent
                        │  응답 → API (NDJSON streaming)
                        ▼
                      API  ──(WebSocket)──▶  Client
```

Client는 API와 **WebSocket**으로 양방향 연결을 유지한다. API는 클라이언트로부터 받은 유저 질의를 MQ에 command로 넣고, Agent가 consume해서 응답을 생성한다. Agent는 생성한 응답을 **NDJSON streaming**으로 API에 보내고, API는 이를 다시 **WebSocket**으로 클라이언트에 전달한다.

즉 구간별 전송은 다음과 같다.

- **Client ↔ API**: WebSocket (양방향)
- **API → MQ → Agent**: command
- **Agent → API**: NDJSON streaming
- **API → Client**: WebSocket

이 구조는 **실시간 대화 응답 생성**에는 적합하다.

장점은 다음과 같다.

- API가 클라이언트와 WebSocket connection을 유지할 수 있다.
- Agent worker를 MQ 기반으로 scale-out할 수 있다.
- LLM 응답 생성 경로가 비교적 단순하다.
- Agent→API NDJSON + API→Client WebSocket streaming으로 사용자 경험을 빠르게 만들 수 있다.

하지만 앞으로 서비스가 확장되면 Agent와 API의 책임이 급격히 커질 가능성이 있다.

앞으로 추가될 가능성이 높은 기능은 다음과 같다.

- 유저 페르소나 생성
- Private memory 생성
- Public memory 후보 생성
- Public memory 승인 및 관리
- 모든 에이전트가 참조할 수 있는 Shared Knowledge Layer(SKL) 구축
- 추천 시스템
- 콘텐츠 후보 생성
- 대화 요약
- safety / moderation / audit
- analytics enrichment

따라서 현재 구조를 유지하되, **응답 생성 경로와 학습/메모리/지식화 경로를 분리**하는 방향이 적절하다.

---

## 2. 핵심 결론

제안하는 방향은 다음과 같다.

> Conversation serving path는 빠르고 얇게 유지하고,  
> 학습, 메모리, 페르소나, 공유 지식, 추천, 콘텐츠화는 event-driven background processing으로 분리한다.

즉, API와 Agent가 모든 일을 직접 처리하는 구조가 아니라, 주요 상태 변화가 발생할 때 event를 발행하고 각 backend component가 해당 event를 consume하여 자기 책임을 처리하는 구조로 확장한다.

---

## 3. Command Queue와 Event Bus의 구분

가장 중요한 설계 원칙은 **Command Queue와 Event Bus를 구분하는 것**이다.

### 3.1 Command Queue

Command는 “누가 이 일을 처리해줘”에 가깝다.

예시:

```text
GenerateAgentResponse
SummarizeConversation
ExtractMemoryNow
```

참고: 평상시 memory 추출은 `ConversationTurnCompleted` event 기반 비동기로 처리한다(4.2). `ExtractMemoryNow`는 "유저가 지금 이걸 기억해줘"처럼 **명시적·동기적 요청** 같은 예외 케이스에만 쓰는 command다. 두 경로가 같은 일을 중복으로 하지 않도록 트리거를 구분한다.

현재 API가 Agent에게 MQ로 넘기는 메시지는 command에 가깝다.

```text
API → MQ → Agent
```

이는 “이 유저 메시지에 대한 응답을 생성하라”는 명령이다.

### 3.2 Event Bus

Event는 “이런 일이 일어났다”에 가깝다.

예시:

```text
UserMessageCreated
AgentMessageCompleted
ConversationTurnCompleted
MemoryCandidateApproved
PostPublished
UserFollowed
```

Event는 특정 consumer를 모르고 발행된다. 각 component는 필요한 event를 subscribe해서 자기 처리를 수행한다.

### 3.3 구분이 필요한 이유

Command와 Event를 섞으면 실패 처리, retry, idempotency, ownership이 애매해진다.

예를 들어:

```text
MessageCreated
```

는 event다.

반면:

```text
GenerateReplyForMessage
```

는 command다.

둘은 처리 방식이 다르다.

추천 구조는 다음과 같다.

```text
Command Queue:
- Agent response generation
- 즉시 처리해야 하는 작업

Event Bus:
- Memory processing
- Persona processing
- Public knowledge indexing
- Recommendation update
- Content draft generation
- Analytics
- Safety audit
```

---

## 4. 전체 아키텍처 제안

### 4.1 Serving Path

실시간 대화 응답 생성 경로는 현재 구조를 유지한다.

```text
Client ─(WebSocket)→ API
→ API stores UserMessage (+ outbox: UserMessageCreated)
→ API publishes GenerateAgentResponse command
→ Agent Worker consumes command
→ Agent streams response to API (NDJSON), with used-memory ids / grounding metadata
→ API relays to Client (WebSocket)
→ API stores final AgentMessage (+ outbox: AgentMessageCompleted / ConversationTurnCompleted)
```

이벤트 발행 주체는 **API(또는 그 뒤의 Conversation Service)** 다. Agent는 응답을 생성·스트리밍하고 필요한 메타데이터(사용한 memory id, grounding 등)를 API에 넘길 뿐, **Event Bus에 직접 발행하지 않는다.** 상태를 commit하는 쪽이 같은 트랜잭션의 outbox로 이벤트를 발행한다는 원칙에 따른 것이며, 이렇게 하면 Agent는 stateless하게 유지되고 이벤트 producer가 한 곳으로 모인다. (7.1·7.2·10·11.1과 동일)

**읽기 경로**: 서빙 시 Agent는 context retrieval 단계에서 **Private Memory + 최신 Persona snapshot**을 읽어 컨텍스트에 넣는다. 메모리·페르소나의 쓰기는 비동기(processor)지만 읽기는 동기이며, Agent는 그 시점에 존재하는 최신 스냅샷을 본다(eventual consistency). 즉 방금 끝난 대화에서 추출될 memory는 다음 턴부터 반영될 수 있다.

**WebSocket 응답 라우팅 (멀티 인스턴스 주의)**: Client WS는 특정 API 인스턴스에 핀된다. 그러나 command는 MQ를 거쳐 임의의 Agent worker가 consume하므로, Agent의 NDJSON 응답은 **그 클라이언트의 WS를 들고 있는 바로 그 API 인스턴스**로 돌아와야 한다. 따라서 응답은 단순 "Agent → API"가 아니라 **connection/session id로 키된 reply 채널**로 라우팅해야 한다.

- 예: Redis pub/sub `channel = connection_id`를 그 API 인스턴스가 subscribe, 또는
- command payload에 **origin API instance id**를 실어 해당 인스턴스의 reply queue로 보낸다.

이 reply-channel 전략은 MVP부터 정해야 멀티 인스턴스에서 스트리밍이 동작한다.

Serving path에서 처리해야 하는 것:

- 유저 메시지 저장
- command 발행
- context retrieval
- memory retrieval
- Agent response generation
- streaming
- 최종 agent message 저장

Serving path에서 빼야 하는 것:

- memory extraction
- persona update
- public memory 후보 생성
- Shared Knowledge Layer(SKL) update
- recommendation update
- content draft generation
- long summary
- analytics enrichment

### 4.2 Learning / Processing Path

비동기 후처리 경로는 event 기반으로 구성한다. 중요한 점은 **모든 processor가 `ConversationTurnCompleted` 하나를 병렬로 consume하는 것이 아니라, 이벤트 체인을 이룬다**는 것이다. 특히 public / SKL 계열은 `ConversationTurnCompleted`가 아니라 **승인·indexing 이벤트**를 트리거로 한다 (6.4의 승인 게이트 원칙).

이벤트 → consumer 매핑:

| 트리거 이벤트 | consumer | 한 일 |
|---|---|---|
| ConversationTurnCompleted | Memory Processor | private memory / pending(public) candidate 생성 |
| ConversationTurnCompleted | Persona Processor | understanding axes 업데이트 |
| ConversationTurnCompleted | Content Processor | post / snapshot / perspective card **후보** 생성 (게시는 승인 필요) |
| ConversationTurnCompleted | Analytics Processor | funnel / retention / quality 지표 적재 |
| MemoryCandidateCreated | Safety Processor | 민감정보·사칭·abuse check (public 후보 차단) |
| MemoryCandidateApprovedAsPublic | Public Knowledge Processor | 승인된 public memory를 SKL에 index (Perspective Card aggregate) |
| PublicKnowledgeIndexed | Recommendation Processor | 추천 후보 갱신 |

즉 흐름은 **turn 단계**와 **승인 후 단계** 둘로 갈린다.

```text
[turn 단계]     ConversationTurnCompleted
                  → Memory / Persona / Analytics / Content(후보)

[승인 후 단계]  MemoryCandidateApprovedAsPublic
                  → Public Knowledge Processor
                  → PublicKnowledgeIndexed
                  → Recommendation Processor
```

> 주의: public memory 후보 생성은 **Memory Processor의 책임**이다(7.3). 별도의 "Public Memory Processor"는 두지 않는다. 승인된 후보를 SKL에 반영하는 것만 Public Knowledge Processor(7.5)가 맡는다.

**비용 게이트 (중요)**: 매 턴마다 Memory 추출·Persona 갱신을 LLM으로 돌리면 비용이 폭발하고 대부분 무의미하다 (메모리 문서 13.4). 따라서 turn 단계 처리는 무조건 다 돌리지 않는다.

- `ConversationTurnCompleted`에 먼저 **싸구려 salience 게이트**(룰 / 소형 분류기)를 걸어, "추출할 가치가 있는 턴"만 비싼 LLM 추출로 보낸다.
- 또는 Memory / Persona 갱신을 **세션 경계·유휴 시점**(`ConversationSummarized` 등)에 배치로 모아 돌린다.
- Analytics처럼 가벼운 처리만 매 턴 무조건 수행한다.

---

## 5. 추천 아키텍처 다이어그램

```text
                         ┌────────────────────┐
                         │       Client        │
                         └─────────┬──────────┘
                                   │ WebSocket (양방향)
                                   ▼
                         ┌────────────────────┐
                         │        API          │
                         │ auth / validation   │
                         │ WS ↔ NDJSON gateway │
                         └──────┬───────▲─────┘
                                │       │
                 command publish│       │NDJSON (Agent→API)
                                ▼       │
                         ┌────────────────────┐
                         │   Command Queue     │
                         └─────────┬──────────┘
                                   ▼
                         ┌────────────────────┐
                         │    Agent Worker     │
                         │ response generation │
                         │ context retrieval   │
                         └─────────┬──────────┘
                                   │ NDJSON → API (API가 최종 저장)
                                   ▼
                         ┌────────────────────┐
                         │ Conversation Store  │  ← API/Conv. Service가 write
                         └─────────┬──────────┘
                                   │
                    domain events via outbox (by API/Conv. Service)
                                   ▼
                         ┌────────────────────┐
                         │     Event Bus       │
                         └──┬────┬────┬────┬──┘
                            │    │    │    │
          ┌─────────────────┘    │    │    └─────────────────┐
          ▼                      ▼    ▼                      ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│ Memory Processor │  │ Persona Processor│  │ Safety Processor │
└────────┬─────────┘  └────────┬─────────┘  └──────────────────┘
         │                     │
         ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│   Memory Store   │  │ Understanding DB │
└────────┬─────────┘  └──────────────────┘
         │
         ▼ user 승인 → MemoryCandidateApprovedAsPublic
┌──────────────────────┐
│ Public KB Processor  │   (= SKL projection 워커)
└──────────┬───────────┘
           │ PublicKnowledgeIndexed
           ▼
┌──────────────────────┐
│ SKL                  │
│ Topic Space +        │
│ Perspective Index    │   (MVP: Main DB + 벡터 인덱스)
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ Recommendation       │
│ Processor            │
└──────────────────────┘
```

위 하단 체인은 4.2의 "승인 후 단계"와 동일하다. Memory Store의 내용이 곧바로 SKL로 가는 것이 아니라, **user 승인 이벤트**를 거쳐야 Public KB Processor가 동작한다.

---

## 6. 핵심 설계 원칙

## 6.1 대화 응답 latency에 후처리를 묶지 않는다

유저가 체감하는 응답 경로는 최대한 빠르고 단순해야 한다.

따라서 memory extraction, persona update, recommendation generation 등은 기본적으로 비동기로 처리한다.

대화 중에는 lightweight reflection 정도만 제공하고, canonical memory 생성은 background processor가 처리하는 방식이 적절하다.

예:

```text
Agent response:
“이 대화에서 이런 관점이 보였어요.”

Background processor:
Pending memory candidate 생성
→ API에서 memory review card 노출
```

## 6.2 DB는 source of truth, Event는 processing trigger

D-110 단계에서 완전한 event sourcing을 도입하는 것은 복잡도가 높다.

추천 구조는 다음과 같다.

```text
DB = source of truth
Event Bus = state change notification / background processing trigger
```

예:

- 메시지는 Conversation DB에 저장
- 메모리는 Memory DB에 저장
- 프로필은 User/Profile DB에 저장
- 이벤트는 후처리와 동기화를 위한 trigger로 사용

## 6.3 모든 consumer는 idempotent해야 한다

Event-driven 구조에서는 duplicate delivery가 발생할 수 있다.

따라서 모든 processor는 같은 event를 여러 번 받아도 결과가 깨지지 않아야 한다.

예:

```text
MemoryProcessor가 ConversationTurnCompleted(event_id=abc)를 두 번 받음
```

처리 결과:

- 같은 memory candidate를 중복 생성하지 않음
- processing log에 event_id 기록
- 이미 처리한 event면 skip

필수 필드:

```text
event_id
idempotency_key
aggregate_id
schema_version
occurred_at
```

## 6.4 Public memory와 SKL은 사용자 승인 후에만 업데이트

가장 중요한 제품/프라이버시 원칙이다.

비동기 processor가 할 수 있는 일:

```text
대화에서 public memory candidate 생성
```

비동기 processor가 하면 안 되는 일:

```text
사용자 승인 없이 public memory 확정
사용자 승인 없이 SKL에 반영
```

올바른 흐름:

```text
ConversationTurnCompleted
→ Memory Processor extracts private memory / public candidate
→ User reviews candidate
→ MemoryCandidateApprovedAsPublic
→ Public Memory Store update
→ PublicKnowledgeProcessor indexes approved public memory
→ PublicKnowledgeIndexed
```

SKL의 입력은 raw conversation이 아니라, 반드시 **승인된 public memory 또는 public content**여야 한다.

이 승인 액션이 메모리 문서의 **publish**다. 승인 한 번이 **사용 권한**(Public Memory Store 반영 → 타 에이전트가 대화에서 참조)과 **발견 권한**(SKL indexing → 검색·추천)을 함께 켠다. MVP에서는 이 둘을 분리하지 않는다.

## 6.5 SKL에는 access control이 필수

“모든 에이전트가 공유하는 지식 베이스”라는 표현은 위험할 수 있다.

정확히는:

> 모든 에이전트가 무조건 접근하는 KB가 아니라,  
> visibility와 권한에 따라 검색 가능한 public knowledge index.

예:

```text
Private memory: 내 에이전트만 접근
Public memory: 타인 에이전트가 접근 가능
Public content: 검색/추천/에이전트 답변에 접근 가능
Deleted memory: 접근 불가
Limited profile memory: followers-only 또는 조건부 접근
```

따라서 SKL query에는 항상 access control filter가 들어가야 한다.

예:

```text
query_shared_kb(
  requester_user_id,
  target_agent_id,
  visibility_scope,
  blocked_user_ids,
  language,
  region
)
```

Vector DB에 넣고 아무나 similarity search하는 구조는 피해야 한다.

---

## 7. 컴포넌트 책임 분리

## 7.1 API

책임:

- Client auth
- Request validation
- User message creation
- Client WebSocket connection 유지 (+ Agent NDJSON → Client WS 중계)
- Command 발행
- Domain event 발행 또는 outbox 기록
- Read model 제공

하지 말아야 할 것:

- 직접 memory extraction
- 직접 persona 생성
- 직접 SKL update
- 무거운 LLM 후처리

## 7.2 Agent Worker

책임:

- Command consume
- Context retrieval
- LLM response generation
- Tool orchestration
- Streaming (NDJSON → API)
- Answer grounding metadata 생성
- 응답 + 메타데이터(사용한 memory id, grounding 등)를 API에 반환

하지 말아야 할 것:

- 모든 memory 영구화 책임
- **최종 AgentMessage 저장 / 도메인 이벤트 직접 발행** (API/Conversation Service가 담당)
- SKL 직접 update
- Recommendation system 직접 update
- Public/private 정책 결정

Agent는 응답 생성에 집중하고 **stateless하게 유지**한다. 상태 저장과 이벤트 발행은 상태를 commit하는 API/Conversation Service가 outbox로 처리한다.

다만 응답 생성 중 사용한 context와 memory id는 반드시 메타데이터로 API에 넘겨야 한다. API가 이를 포함해 `AgentMessageCompleted` / `MemoryUsedInAgentResponse` 등을 발행한다.

## 7.3 Memory Processor

책임:

- 대화/포스트/댓글에서 memory candidate 추출
- Memory type 분류
- Sensitivity 분류
- Confidence score 부여
- Private / pending / public candidate 분리
- 중복 memory merge 후보 생성

주의:

- Public 확정은 user action 필요
- 민감 정보는 public candidate로 올리지 않음

## 7.4 Persona / Understanding Processor

책임:

- Onboarding answers와 대화에서 축별 이해 업데이트
- UnderstandingAxis 관리
- Persona snapshot 생성
- Agent prompt에 들어갈 compact user model 생성

예:

```text
user_understanding_summary:
- thinking_style: execution_oriented, evidence_sensitive
- conversation_preference: structure_first
- social_boundary: agent_first
```

Memory와 Persona는 구분해야 한다.

- Memory: 개별 사실, 취향, 관점
- Persona / Understanding: 여러 memory와 행동을 종합한 축별 모델

## 7.5 Public Knowledge Processor

이 processor가 곧 메모리 문서에서 말하는 **SKL projection 워커**다. 승인된 Public Agent Memory / public content를 받아 SKL(Topic Space + Perspective Index)에 반영한다.

책임:

- Approved public memory / public content를 KB item으로 indexing
- KB item을 **(agent, topic)별 Perspective Card로 aggregate** → Perspective Index 갱신
- 해당 topic의 Topic Space narrative 갱신
- Deletion / revocation 처리 (생성만큼 중요)
- Source attribution 유지

메모리 문서의 불변식을 그대로 따른다.

- **projection이므로 재빌드 가능**: SKL은 원본(Public Agent Memory)에서 다시 빌드할 수 있다. 따라서 이 워커의 배치 손실은 치명적이지 않다 (raw 이벤트만 durable하면 됨).
- **debounce 배치**: 같은 topic에 대한 갱신을 윈도로 모아 한 번에 반영한다 (실시간 불필요 → 쓰기 경합 제거).
- **active-set 관리**: freshness·confidence를 결합해 "오래됐고 동시에 저품질"인 KB item/Card만 cold로 축출(compaction)한다. evergreen high-confidence는 유지.

KB item과 Perspective Card의 관계는 다음과 같다.

> KB item = 승인된 public memory/content의 최소 색인 단위(raw 재료).
> Perspective Card = 한 에이전트의 한 topic에 대한 KB item들을 집계한 공개 투영(Memory ∩ Persona).
> SKL discovery는 Perspective Card 단위로 에이전트를 추천하고, KB item은 그 근거/출처가 된다.

모든 KB item은 source와 visibility를 가져야 한다.

예:

```text
kb_item_id
source_type: public_memory | public_post | public_comment
source_id
owner_user_id
agent_id
topic_id
visibility
confidence
freshness
embedding
created_at
revoked_at
```

## 7.6 Recommendation Processor

책임:

- User-person match 후보 생성
- Agent recommendation 생성
- Content recommendation 생성
- Explanation 생성
- Ranking feature 업데이트

추천은 두 층으로 나누는 것이 좋다.

```text
candidate generation: 비동기
ranking: 요청 시 동기
```

즉, background에서 후보 pool을 만들어두고, 사용자가 추천 화면을 열었을 때 최신 context로 ranking한다.

## 7.7 Content Processor

책임:

- Conversation snapshot 후보 생성
- Post draft 후보 생성
- Perspective card 후보 생성
- Summary 생성

단, 게시/public 전환은 user approval이 필요하다.

## 7.8 Safety / Audit Processor

책임:

- 민감 정보 감지
- Public memory 후보 safety check
- Impersonation risk check
- Abuse detection
- Report pipeline
- Audit log

---

## 8. 주요 Event 제안

## 8.1 Conversation Events

```text
UserMessageCreated
AgentResponseRequested
AgentMessageStarted
AgentMessageCompleted
AgentMessageFailed
ConversationTurnCompleted
ConversationSummarized
```

주의:

Token 단위 event를 event bus에 흘리는 것은 추천하지 않는다. Token streaming은 API/WebSocket/SSE/NDJSON path에서 처리하고, event bus에는 completion 중심 event만 발행하는 것이 좋다.

**턴 종료 정의**: 한 턴에 tool call 등으로 **여러 AgentMessage**가 생길 수 있다. 둘을 구분한다.

- `AgentMessageCompleted`: 개별 agent 메시지 하나가 완료될 때.
- `ConversationTurnCompleted`: 그 턴의 마지막 agent 메시지가 끝나 "유저 입력에 대한 응답이 완결된 시점"에 **턴당 한 번** 발행.

모든 후처리(Memory/Persona/Analytics)의 트리거는 `ConversationTurnCompleted`다. 따라서 "무엇이 턴을 닫는가"(마지막 agent 메시지 종료, 또는 일정 idle)를 명확히 정의해야 한다.

## 8.2 Memory Events

```text
MemoryCandidateCreated
MemoryCandidateUpdated
MemoryCandidateApprovedAsPrivate
MemoryCandidateApprovedAsPublic
MemoryCandidateRejected
MemoryDeleted
MemoryVisibilityChanged
MemoryUsedInAgentResponse
```

`MemoryUsedInAgentResponse`는 audit에 중요하다. 나중에 “왜 이 답변을 했는가”를 추적하려면 어떤 memory가 context에 들어갔는지 알아야 한다.

## 8.3 Persona / Understanding Events

```text
UnderstandingAxisUpdated
PersonaSnapshotCreated
PersonaConfidenceChanged
OnboardingStepCompleted
OnboardingCompleted
```

Persona는 고정 텍스트가 아니라 축별 상태로 보는 것이 좋다.

예:

```text
conversation_style: structure_first
social_boundary: agent_first
ai_trust_boundary: consent_sensitive
```

## 8.4 Public Knowledge Events

```text
PublicMemoryApproved
PublicMemoryRevoked
PublicContentPublished
PublicContentDeleted
PublicKnowledgeCandidateCreated
PublicKnowledgeIndexed
PublicKnowledgeRemoved
PublicKnowledgeReindexed
```

중요:

- Public memory 삭제 시 SKL에서도 반드시 제거되어야 한다.
- Post 비공개 전환 시 index에서도 제거되어야 한다.
- Delete/revoke event는 create/index event만큼 중요하다.

## 8.5 Recommendation Events

```text
RecommendationRequested
RecommendationGenerated
RecommendationShown
RecommendationClicked
RecommendationDismissed
RecommendationFeedbackGiven
ConnectRequestCreated
FollowCreated
```

## 8.6 Safety Events

```text
MessageFlagged
MemoryFlagged
UserReported
UserBlocked
AgentResponseSafetyFailed
PublicMemorySafetyRejected
```

---

## 9. Event Envelope 예시

Event envelope은 통일하는 것이 좋다.

```json
{
  "event_id": "evt_01H...",
  "event_type": "ConversationTurnCompleted",
  "schema_version": 1,
  "occurred_at": "2026-06-15T12:34:56Z",
  "producer": "conversation-service",
  "aggregate_type": "conversation",
  "aggregate_id": "conv_123",
  "actor_user_id": "user_123",
  "tenant_id": "xinobi",
  "correlation_id": "req_abc",
  "causation_id": "cmd_xyz",
  "payload": {
    "conversation_id": "conv_123",
    "user_message_id": "msg_user_123",
    "agent_message_id": "msg_agent_456",
    "agent_id": "agent_789",
    "conversation_type": "my_agent",
    "language": "ko"
  }
}
```

중요 필드:

- `event_id`: 중복 처리 방지
- `event_type`: consumer routing
- `schema_version`: event schema versioning
- `occurred_at`: event 발생 시각
- `producer`: event 발행 주체
- `aggregate_id`: domain object 식별
- `actor_user_id`: 누가 일으킨 event인지
- `correlation_id`: 한 요청의 trace
- `causation_id`: 어떤 command/event 때문에 생긴 event인지

---

## 10. Outbox Pattern 권장

API 또는 domain service가 DB 저장과 event 발행을 동시에 해야 할 때 정합성 문제가 생길 수 있다.

예:

```text
DB에는 메시지가 저장됐는데 event publish 실패
Event는 발행됐는데 DB 저장 실패
```

이를 막기 위해 **Transactional Outbox Pattern**을 추천한다.

흐름:

```text
1. DB transaction 안에서 message 저장
2. 같은 transaction 안에서 outbox_events 테이블에 event 저장
3. 별도 outbox publisher가 event bus로 publish
4. publish 성공 시 marked_as_published
```

이렇게 하면 DB state와 event 발행 사이의 정합성을 유지할 수 있다.

참고: outbox는 **domain event 전용**이다. command(`GenerateAgentResponse` 등)는 도메인 상태가 아니라 작업 지시이므로 outbox 대상이 아니라 Command Queue로 바로 보낸다.

D-110 production 기준으로 outbox pattern은 거의 필수에 가깝다.

---

## 11. 처리 흐름 예시

## 11.1 일반 대화 1턴

```text
1. Client sends user message
2. API stores UserMessage
3. API emits UserMessageCreated
4. API publishes GenerateAgentResponse command
5. Agent consumes command
6. Agent retrieves context / memories
7. Agent streams response to API (NDJSON, + used-memory ids / grounding), API relays to Client (WebSocket)
8. API stores final AgentMessage
9. API emits AgentMessageCompleted (outbox)
10. API / Conversation service emits ConversationTurnCompleted (outbox)
11. (salience 게이트 통과 시) Memory Processor consumes ConversationTurnCompleted
12. (salience 게이트 통과 시) Persona Processor consumes ConversationTurnCompleted
13. Analytics Processor consumes ConversationTurnCompleted
```

여기서 Recommendation Processor는 `ConversationTurnCompleted`가 아니라, 이후 승인 체인의 **`PublicKnowledgeIndexed`** 를 받아 동작한다 (4.2의 "승인 후 단계"). 즉 추천 갱신은 대화 직후가 아니라 public 승인·indexing 이후에 일어난다.

## 11.2 Memory 생성 흐름

```text
ConversationTurnCompleted
→ MemoryProcessor extracts candidates
→ stores MemoryCandidate(status=pending)
→ emits MemoryCandidateCreated
→ API shows pending memory to user
→ user approves public
→ emits MemoryCandidateApprovedAsPublic
→ PublicMemoryStore updates
→ PublicKnowledgeProcessor indexes it
→ emits PublicKnowledgeIndexed
```

## 11.3 Public memory 삭제 흐름

```text
User deletes public memory
→ MemoryDeleted
→ PublicKnowledgeProcessor removes from vector index
→ RecommendationProcessor invalidates related recommendations
→ AgentContextCache invalidates cached context
→ Audit log records deletion
```

삭제/visibility change flow는 생성 flow만큼 중요하다. 프라이버시 신뢰가 여기서 결정된다.

---

## 12. Memory, Persona, SKL의 구분

이 셋은 반드시 분리해야 한다.

## 12.1 Memory

개별적인 사실, 취향, 관점 단위.

예:

```text
“근거 없는 단정형 콘텐츠를 선호하지 않음.”
“AI를 관계 인프라 관점에서 봄.”
```

## 12.2 Persona / Understanding

여러 memory와 행동을 종합한 축별 모델.

예:

```text
thinking_style = evidence_sensitive + execution_oriented
conversation_preference = structure_first
social_boundary = agent_first
```

## 12.3 Shared Knowledge Layer (SKL)

승인된 public memory(=Public Agent Memory)와 public content를 주제별로 조직한, 권한 조건에 따라 조회 가능한 **관점 인덱스**다. 정답을 직접 제공하는 DB가 아니라 **"어떤 에이전트와 대화할지"를 찾아주는 라우팅 레이어**다 (메모리 문서 5장).

구조는 메모리 문서와 동일하게 **Topic Space + Perspective Index**로 본다.

- **Topic Space**: 주제별 narrative/context (사람·LLM이 읽는 요약).
- **Perspective Index**: (agent, topic)별 **Perspective Card** 모음 (검색·추천·권한·confidence·freshness 메타데이터).

그리고 SKL은 독립 저장소가 아니라 **Public Agent Memory의 projection**이다 (7.5의 Public Knowledge Processor가 갱신).

예 (Perspective Card 수준):

```text
agent_789 / topic=ai_social_product:
  “AI social product를 relationship infrastructure 관점에서 보는 public 관점.”
  confidence: medium, freshness: 2026-06, discoverable: true
```

Memory, Persona, SKL을 하나로 합치면 나중에 권한, 삭제, 추천, audit이 어려워진다. 셋의 관계를 한 줄로 정리하면:

> Memory(개별 사실·관점) → 승인된 일부가 public이 되고 → Persona(축별 모델)와 함께 **Perspective Card**로 투영되어 → SKL(Topic Space + Perspective Index)을 구성한다.

---

## 13. Event Bus / MQ 기술 선택 방향

구체 기술은 현재 stack에 따라 다르지만, 개념적으로는 다음과 같이 나눌 수 있다.

## 13.1 Kafka / Redpanda / PubSub 계열이 좋은 경우

- Event replay가 중요하다.
- Consumer group이 많다.
- SKL, recommendation, analytics 등 여러 consumer가 붙는다.
- 장기적으로 event-driven data platform이 필요하다.

## 13.2 RabbitMQ / SQS 계열이 좋은 경우

- Command queue 중심이다.
- 단순 task distribution이 중요하다.
- Retry / DLQ 위주다.
- 운영 단순성이 중요하다.

## 13.3 추천

현재 이미 MQ가 있다면:

```text
기존 MQ = Command Queue로 유지
Event Bus = Kafka / Redpanda / PubSub류 별도 도입 검토
```

초기에는 물리적으로 하나의 시스템으로 시작할 수 있지만, 논리적으로는 반드시 command와 event를 분리해서 설계하는 것이 좋다.

---

## 14. Streaming 처리 원칙

실시간 응답 스트리밍은 event bus로 처리하지 않는 것이 좋다.

비추천 구조:

```text
Agent token → Event Bus → API → Client
```

이 구조는 event bus에 token-level noise를 만들고, ordering/latency/cost 문제가 복잡해진다.

추천 구조:

```text
Agent ──(NDJSON)──▶ API ──(WebSocket)──▶ Client
```

즉 Agent→API 구간은 NDJSON, API→Client 구간은 WebSocket으로 흘리고, event bus에는 완료 event만 보낸다.

```text
AgentMessageCompleted
ConversationTurnCompleted
```

정리하면:

```text
실시간 token = streaming path
도메인 상태 변화 = event bus
```

---

## 15. MVP 구현 전략

처음부터 모든 component를 microservice로 나누는 것은 비효율적일 수 있다.

D-110 기준 현실적인 구조는 다음과 같다.

```text
API Service
Agent Worker
Background Worker
Event Bus
Main DB
Vector DB        # MVP에서는 별도 시스템이 아니라 Main DB의 벡터 인덱스 확장으로 시작
Object Storage
Analytics Sink
```

`Vector DB`는 **논리적 컴포넌트**다. MVP에서는 Main DB에 벡터 인덱스 확장을 얹어 하나로 시작할 수 있으며, 별도 벡터 DB(분산 ANN)는 메모리 문서 13장의 대규모 단계에서 분리한다. 구체 DB 제품은 여기서 지정하지 않는다.

Background Worker 내부에 processor를 모듈로 둔다.

```text
Background Worker
- MemoryProcessor
- PersonaProcessor
- PublicKnowledgeProcessor
- RecommendationProcessor
- ContentProcessor
- SafetyProcessor
```

처음에는 하나의 worker repo/process여도 된다.

다만 topic, consumer group, processor module은 처음부터 분리해두는 것이 좋다.

나중에 병목이 생기면 다음 순서로 분리할 수 있다.

1. MemoryProcessor 분리
2. RecommendationProcessor 분리
3. PublicKnowledgeProcessor 분리
4. SafetyProcessor 분리

---

## 16. P0 Event 목록

초기 구현에 필요한 최소 event는 다음 정도로 충분하다.

```text
UserMessageCreated
AgentMessageCompleted
ConversationTurnCompleted

MemoryCandidateCreated
MemoryCandidateApproved
MemoryCandidateRejected
MemoryDeleted

PublicMemoryApproved
PublicMemoryRevoked

PostPublished
PostDeleted

RecommendationShown
RecommendationClicked

UserFollowed
ConnectRequestCreated

UserBlocked
UserReported
```

이 정도만 있어도 memory, persona, recommendation, SKL 흐름을 만들 수 있다.

---

## 17. 실패 처리와 운영

Event-driven 구조에서 실패 처리는 핵심이다.

필수 요소:

- Retry policy
- Dead Letter Queue
- Processing status table
- Processor별 lag monitoring
- Event replay
- Poison message quarantine
- Idempotency key
- Schema versioning

예:

```text
MemoryProcessor failed on ConversationTurnCompleted
→ retry 3 times
→ still failed
→ DLQ
→ admin dashboard에서 확인
→ fix 후 replay
```

Processor의 실패가 실시간 대화 응답 실패로 이어지면 안 된다.

---

## 18. 사용자 경험 관점

후처리가 비동기이면 memory 후보 생성이 몇 초 늦게 뜰 수 있다. 이를 UX로 자연스럽게 처리해야 한다.

예:

대화 직후:

```text
“이번 대화에서 새로 이해한 내용을 정리하고 있어요.”
```

몇 초 후:

```text
“새 메모리 후보 3개가 생겼어요.”
```

또는 Agent가 응답 중 lightweight reflection을 제공하고, background processor가 canonical memory를 확정하는 방식이 좋다.

```text
대화 중 reflection = Agent response
영구 memory 생성 = Background processor
```

---

## 19. 단계별 적용 계획

## Step 1. Event envelope 도입

모든 주요 domain event를 같은 형식으로 발행한다.

## Step 2. Outbox table 추가

API / Agent / domain service가 DB transaction과 함께 event를 저장한다.

## Step 3. Background worker 추가

초기에는 하나의 worker에 여러 processor module을 둔다.

## Step 4. ConversationTurnCompleted 이벤트부터 시작

이 event를 기준으로 memory, persona, content, recommendation 처리를 붙인다.

## Step 5. Memory approval flow 추가

Candidate 생성과 public 확정을 분리한다.

## Step 6. PublicKnowledgeProcessor 추가

승인된 public memory와 public content만 SKL에 indexing한다.

## Step 7. Delete / revoke flow 구현

Public memory 삭제, post 삭제, block 시 index와 추천에서 제거한다.

---

## 20. 최종 권장안

정리하면 다음 방향을 추천한다.

> API는 모든 일을 직접 하지 않는다.  
> API와 domain service는 state change를 저장하고 event를 발행한다.  
> Agent는 실시간 응답 생성에 집중한다.  
> Memory, persona, public knowledge, recommendation, content, safety는 event를 consume해서 비동기로 처리한다.  
> Public/shared knowledge는 반드시 사용자 승인된 public data만 사용한다.  
> Command queue와 event bus는 논리적으로 분리한다.  
> DB를 source of truth로 두고, event는 후처리와 동기화를 위한 trigger로 쓴다.

D-110 기준으로는 full microservice보다 다음 구조가 현실적이다.

```text
Modular API service
+ Agent worker
+ Event bus
+ Background processors
+ Main DB
+ Vector DB
```

이렇게 하면 현재 API → MQ → Agent → API streaming 구조를 크게 깨지 않으면서도, 앞으로 memory, persona, shared knowledge, recommendation, content, safety가 붙어도 확장 가능한 구조를 만들 수 있다.
