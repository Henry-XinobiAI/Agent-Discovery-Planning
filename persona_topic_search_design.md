# Persona Topic Search — 신규 아키텍처 설계 (agent-recommendation 관점) — rev 5

작성: 2026-08-20 · 상태: **설계 기준 (초안)** — 2026-08-19 회의 결정 + 2026-08-20 설계 리뷰·외부 리뷰 반영. §5의 열린 결정이 닫힐 때마다 rev-up하고, 전부 닫히면 확정으로 승격한다. 개정 이력은 문서 끝.

> **이 문서의 역할.** persona-api 전환 트랙과 memory-api v2 마이그레이션이 **둘 다 폐기**된 뒤(2026-08-19),
> 그 자리를 대체하는 새 그림의 단일 기록이다. 여기 적힌 것은 두 층으로 나뉜다 —
> **§1 결정 사항**은 회의·리뷰에서 합의된 것이고, **§2–§4 스케치**는 그 결정을 구체화한 우리 설계 초안이다
> (extractor 팀·인프라 팀과의 협의에서 바뀔 수 있다). 폐기된 트랙과의 관계는 §7.

## 0. 확정된 체인

```
bourbon-api ──deferq 이벤트(RabbitMQ topic `deferq.events`)──▶ bourbon-agent
                                                                  │ persona extractor
                                                                  │ (대화를 보고 topic·claim 추출,
                                                                  │  산출물은 전부 영어)
                                                                  ▼
                                                      전용 저장소 (DynamoDB 권고 — §1-③)
                                                                  │
                                              스트림 기반 색인 파이프라인 (OSIS zero-ETL
                                              또는 자체 컨슈머 — 열린 질문 Q1)
                                                                  ▼
                                                      AOSS persona topic 인덱스
                                                                  ▲ 1차: query expansion 검색
agent-recommendation-api ─────────────────────────────────────────┤
                                                                  ▼ 2차: 저장소 재확인 (BatchGet)
                                                      전용 저장소 (같은 테이블)
```

- **extractor는 bourbon-agent 안에 산다.** bourbon-agent에는 이미 단일 테이블 DynamoDB 규율
  (`bourbon_agent/storage/dynamodb/keys.py`), 세션 경계, 그리고 추출이 쓰고 agent가 읽는
  `user_persona/` 모듈이 있다 — 기존 결을 따르는 배치다.
- **agent-recommendation은 두 단계로 읽는다.** 1차 = AOSS 인덱스에서 recall, 2차 = 저장소에서
  진실 재확인(visibility·gate 신호). 후보의 단위는 topic-owner 쌍이 아니라
  **`(owner, 매칭된 topic 집합)`**이다(§1-⑦) — anchor가 사라진 세계에서 need가 등가류 역할을 하고,
  한 owner의 여러 topic이 같은 need에 걸리는 것은 노이즈가 아니라 신호다. 인덱스는 추천 순서를
  결정하지 않는다 — ordering contract(gate→filter→lexicographic→tiebreak)는 그대로다.
- **1차 범위 (제품 결정, 2026-08-20 · rev 4에서 재축소).** 1차의 추천 유형은 **하나**다:
  "이 topic을 가장 잘 아는 agent 추천". 기존 need 축(depth/experience/for/against/coverage)은
  **1차에서 전부 폐기**한다 — for/against만 빼는 게 아니라 **need_type 축 자체가 1차 wire 계약에서
  사라진다**(내부적으로 단일 유형 고정). 추천 유형 체계는 persona가 실제로 제공하는 정보가 취합된
  뒤 **2차에서 새로 설계**한다(§5 Q8). 전환 전까지 기존 기능의 현행 소스는 memory-api다(§7).
  §2의 CLAIM# 아이템·claims 인덱스 확장 여지는 이 확장을 막지 않기 위해 남겨 둔다. 파급: 기존
  코드의 `NeedType`·stance 파이프라인(`STANCE_NEEDS`·judge 경로)은 전환 시 삭제 패스 대상이다.

## 1. 결정 사항 (2026-08-19 회의 + 2026-08-20 리뷰)

### ① extractor 배치 = bourbon-agent · 입력 데이터는 best-effort로 선언
bourbon-api가 발행하는 deferq 이벤트(`bourbon.message_created` 등)를 bourbon-agent가 소비해
추출한다. deferq는 **at-most-once**다(발행 실패는 로그만 남기고 삼킴 — bourbon-api
`websockets/handlers.py`·`agents/stream.py`, outbox 없음). 따라서:
- **우리가 소비하는 데이터는 best-effort다** — 유실된 발화가 첫/유일한 발화면 topic 자체가 없고,
  마지막 발화면 `evidence_count`·`last_evidence_at`이 실제보다 작다. 이를 무해하다고 단정하지
  않는다. 대신 **제품 결정으로 선언**한다: 추천 랭킹의 재료로서 best-effort persona를 수용한다.
- 파생 규율: **gate 튜닝은 undercount에 견고해야 한다** — 임계값 하나 차이로 노출이 갈리는
  설계(경계 과신)를 피하고, 임계는 보수적으로 잡는다.
- 유실 복구(outbox·watermark 재대사·sweep)와 `(message_id, extractor_version)` 멱등 추출은
  **bourbon-api/extractor 팀 소관**이다 — 외부 리뷰의 해당 지적은 그쪽에 전달한다(§5 Q6).
  복구가 생기면 위 선언을 rev-up으로 되돌리면 된다.
- (대조: **색인**은 유실 = 영구 stale이라 deferq 경로를 쓰지 않는다 — ④.)

### ② 산출물은 영어 한정
topic label·claim proposition·alias 전부 영어. 따라서:
- **query expansion은 영어 변형 생성이다.** 한국어 need "재택근무"에서 `remote work / working from
  home / telecommuting / WFH`처럼 영어 내 동의 변형까지 LLM이 한 번에 생성한다. 단순 1:1 번역이
  아니다. 변형마다 `_msearch` 독립 검색이라 어떤 변형이 맞았는지는 응답 단위로 회수된다(§3).
- recall 부담이 저장 시점(다국어 alias — 폐기된 트랙의 1순위 요구)에서 **질의 시점(번역·변형
  품질)**으로 이동한다. 질의 시점이 더 나은 자리다 — 저장된 alias 오류는 재추출 전까지 박제되지만
  질의 변형 오류는 요청 단위라 즉시 개선된다.
- 인덱스 analyzer가 영어로 단순화된다. nori 검증 불필요. memory-api의 `ANALYSIS_SETTINGS`
  (light_english stemmer + shingle 근접 부스트, `memory/search/analysis.py`)를 재사용한다.
- **eval은 3층이다** (E2E 하나로는 번역 실패와 검색 실패가 안 갈린다):
  ⑴ 한국어 need → 영어 expansion 변형 품질, ⑵ 정답 영어 query → 검색 recall, ⑶ 전체 E2E.
  golden set은 세 층을 모두 커버한다.

### ③ 저장소 = DynamoDB, **전용 테이블** (우리 권고 — extractor 팀 확정 대기)
회의에서는 DynamoDB or MySQL이 열려 있었다. 우리 권고는 DynamoDB이고 근거는:
- **색인 전달 보증.** MySQL 경로의 "이벤트 발행 → 우리가 색인"은 deferq가 at-most-once라
  outbox/재대사를 우리가 소유해야 한다. DynamoDB 스트림 기반은 at-least-once + 아이템 단위 순서
  보장 + 백필이 관리형으로 온다.
- **2차 필터의 모양.** (owner, topic) key 기반 BatchGet 형태다 — DynamoDB의 자연 패턴.
- **기존 패턴.** bourbon-agent의 storage/dynamodb 세션·키 규율을 그대로 탄다.

단 **bourbon-agent의 기존 단일 테이블(`bourbon-agent-tokyo-{stage}`)에 넣지 않는다**.
전용 테이블(가칭 `bourbon-persona-tokyo-{stage}`, iac 소유)로 분리하는 이유:
1. 색인 파이프라인은 테이블 단위다 — 같은 테이블이면 agent 내부 상태까지 파이프라인에 흘러든다.
2. agent-recommendation의 읽기 권한이 이 데이터에만 스코프된다.
3. bourbon-agent 테이블의 문서는 zlib+AES-GCM 암호화가 규칙(`storage/crypto`)인데 색인 대상은
   평문이어야 한다. **"이 테이블은 평문 + KMS at-rest" 를 의도적 결정으로 기록한다** — 대화에서
   추출된 파생물을 평문 저장하는 것이며, 노출 통제는 TOPICSEARCH# projection(⑥) + 2차 재확인이
   담당한다.

### ④ 색인 계약 — 파이프라인 기술보다 한 층 위에서 잠근다
인프라 논의(OSIS zero-ETL vs 자체 스트림 컨슈머)와 무관하게 불변인 것만 잠근다:
1. 1차 검색 대상은 **AOSS의 persona topic 인덱스**다. AOSS 컬렉션 그룹(`{stage}-aoss-tokyo`,
   type=SEARCH)은 이미 iac에 있고, agent-recommendation용 IRSA 데이터 접근 권한 추가가 필요하다(Q4).
2. 색인은 **DynamoDB 스트림 기반, at-least-once, 아이템 단위 순서 보장, 최종 일관**이다.
   2차 재확인 설계는 이 성질만 전제한다.
3. **인덱스 매핑과 문서 모양(doc contract)은 파이프라인이 아니라 agent-recommendation이 소유한다.**
   파이프라인 구현자가 문서 모양을 결정하게 두면 색인 기술 교체가 우리 검색 코드 변경이 된다.
   문서 계약을 우리가 쥐면 OSIS↔자체 컨슈머 교체가 우리에게 무사건이다.

### ⑤ 변경 주기 분리는 **저장 아이템에서** 강제한다
스트림 기반 색인은 **아이템 단위**로 재색인한다. `evidence_count`가 검색 텍스트와 같은 아이템에
있으면 count가 1 오를 때마다 문서 전체가 재색인된다 — 인덱스 매핑에서 count를 빼도 재색인은
일어난다. 따라서 "자주 변하는 값은 색인하지 않는다"는 매핑 규칙이 아니라 **아이템 분리**(§2:
TOPIC# vs TOPICSTAT#)로만 실현된다. 이 분리는 extractor의 저장 스키마 요건이므로 인프라 논의를
기다리지 않고 **지금 잠근다**.

### ⑥ private은 색인하지 않는다 — TOPICSEARCH# projection (rev 3에서 결정 변경)
**rev 1은 "TOPIC# 전체를 색인하고 visibility 필드로 필터"였다. 외부 리뷰를 받아 뒤집는다** —
필터는 응답 유출은 막지만 다음 둘을 못 막는다:
1. **색인 자체.** private label·description·aliases가 AOSS `_source`와 역색인에 존재한다. AOSS는
   문서 단위 접근 제어가 없어 보호가 쿼리 규율뿐이고(필터 절 하나 빠뜨리면 유출), 현행 iac의
   AOSS는 public network access 허용 + dev human role 전체 데이터 권한이라 **사람이 대시보드로
   읽을 수 있는 저장소**다. private 파생 텍스트를 거기 두지 않는다.
2. **전환 시 삭제.** visibility가 private으로 바뀌어도 필터 모델에서는 문서 필드만 바뀌고 텍스트는
   물리적으로 남는다. 파이프라인 조건 필터로 걸러도 이미 색인된 문서를 지우는 이벤트가 없어
   stale public 문서가 영구히 남는다.

**구조: publish 가능 ⇔ 검색 projection 아이템 존재.** extractor가 publish 가능한 topic에만
`TOPICSEARCH#` 아이템을 만들고(§2), private 전환·삭제 시 그 아이템을 지운다(TOPIC#과
`transact_write`로 동기). 색인 파이프라인에는 **TOPICSEARCH#만** 흘린다. 그러면 private 전환 =
아이템 삭제 = 스트림 REMOVE = 색인 문서 삭제가 파이프라인의 **기본 동작**(create/update/delete
미러링)으로 따라온다 — 조건부 액션 같은 기교가 불필요하다. friend 등 tier 구분이 검색 대상에
생기면 projection에 tier 필드를 남겨 필터한다(부재=비공개, 필드=tier 구분).

count류는 여전히 색인 제외(⑤). visibility 토글 반복은 아이템 생성/삭제의 반복일 뿐이며 유저
행위 빈도라 비용은 소음 수준이고, 남용 방어의 자리는 저장 설계가 아니라 설정 변경 엔드포인트의
rate limit/debounce다.

**불변식 (승계): 인덱스는 관대한 쪽으로만 stale해도 되고, 그것은 2차 읽기 시점 재확인이 잡는다.**
전환 직후 위험한 방향(색인에 잔존, 저장소=private)은 2차가 무조건 잡고, 안전한 방향(삭제 전파
지연으로 후보 누락)은 몇 초의 recall 손실로 끝난다. 진실은 항상 저장소다.

### ⑦ 후보 단위 = (owner, topic 집합) · 대표 선정은 gate 뒤 — 랜덤 샘플링 금지 (rev 3에서 정정)
**rev 1의 "1차에서 owner당 최고 히트 1개로 collapse"는 결함이었다**(외부 리뷰 지적): gate 신호는
인덱스에 없으므로 retrieval 1위 topic이 gate에서 탈락하면, gate를 통과했을 2위 topic이 collapse에서
이미 버려져 owner가 통째로 사라진다. 검색기는 maturity나 대표 topic을 결정할 자격이 없다 —
기존 코드가 agent dedupe를 gate·ordering **뒤**에 두는 이유와 같다.

정정된 흐름:
1. **self-exclusion을 검색 쿼리에서.** `owner_id != requester` 필터를 1차 쿼리에 넣는다 —
   cap보다 앞에 공짜로 적용된다.
2. **1차는 owner당 top-K topic을 유지한다** (K는 eval로 결정, BatchGet 비용과 연동 — §4).
   후보 단위는 `(owner, 매칭된 topic 집합)`이다.
3. **쿼리별 top-N.** expansion 쿼리마다 retrieval 순위 상위 N만 취한다(`_msearch` 독립 검색 — §3).
   검색 점수는 recall 채널의 폭 제한이지 랭킹이 아니다.
4. **2차 hydration/gate 뒤에** need별 ordering → owner당 최종 1 topic(`_keep_one_edge_per_agent`
   상당) 선정. 대표 topic 선정은 ranking 단계의 일이다.
5. 그래도 넘치면 마지막에 캡 — 이 시점의 꼬리는 모든 expansion 쿼리가 낮게 평가한 것들이다.
   **랜덤 샘플링 금지**: 필터 전에 자르는 것이라 2차를 통과할 후보를 같은 확률로 버린다.

**owner 수준 gate의 기본 의미론 = any-pass**: 매칭된 topic 집합 중 gate를 통과하는 topic이
하나라도 있으면 owner는 살아남고, 통과한 topic들만 ordering에 들어간다. **topic 간 evidence
합산 같은 집계는 별도 열린 결정**(§5 Q7)이다 — 조용히 sum을 도입하면 immature topic 두 개가
mature owner 하나로 합쳐지는, 옛 maturity gate가 의도적으로 막았던 경로가 열린다.

### ⑧ 1차 검색 = BM25 + query expansion. 벡터는 measure-first로 유예
사내에서 실증된 OpenSearch 스택은 BM25-only다(bourbon-memory-api `memory/search/` — analyzer,
RRF fusion, AOSS 특이사항까지 해결돼 있고 knn/embedding은 전사 0건). 현행 AOSS 컬렉션 그룹은
type=SEARCH라 k-NN 벡터 인덱스가 안 되고(VECTORSEARCH 타입 필요), 스트림 파이프라인에는 embedding
계산 지점이 없어 벡터를 넣는 순간 자체 인덱서가 부활한다. 따라서:
- 1차 릴리스 = BM25 + 영어 query expansion. 소스 병합이 필요하면 memory-api의 RRF
  (`memory/search/fusion.py` — 점수 비교 없이 rank만)를 재사용.
- 벡터 채널 = 별도 VECTORSEARCH 컬렉션 + 자체 색인 경로가 필요한 **유예 트랙**. §2-② recall 측정이
  부족을 증명할 때만 착수한다. **측정 없이 기본 경로로 승격 금지** (승계 규율).

### ⑨ 아이템 스키마 = 서비스 간 계약
extractor(bourbon-agent)가 쓰고 agent-recommendation이 직접 읽으므로 DynamoDB 아이템 모양이
두 서비스 사이의 wire contract다. HTTP API처럼 관리한다: 아이템에 `schema_version` 속성, 양쪽
리포에 같은 fixture로 계약 테스트, 필드 추가는 additive-only, 제거는 협의. **계약 테스트 payload를
consumer model에서 유도하지 않는다** (승계 규율) — 기준은 extractor가 실제로 쓴 아이템이다.

### ⑩ 1차 클라이언트 계약 — bourbon-agent 정렬 (2026-08-20)
클라이언트가 확정됐다: bourbon-agent의 personal agent가 `recommend_agents` tool로 호출한다
(bourbon-agent #142 — Protocol 시임 `AgentRecommendationClient` + mock, 실 API 착지 시 교체).
mock과의 대조에서 합의/유지할 것:

- **신뢰 모델 일치 (유지).** requester metadata는 handler가 task payload에서 채우고 모델은 못
  넣는다 — 우리 `requester_owner_id`(on_behalf_of claim) 정의와 동일. self-exclusion 전제 성립.
- **`matched_topics` (확정).** mock의 `expertise: list[str]` 자리는 **이 요청에 매칭된 topic
  label 집합**(2차 gate 통과분, 대표 topic 먼저)으로 확정. 능력 태그("research"/"teaching" 류)는
  persona 추출물에서 나올 수 없는 값이라 계약에서 제외. **owner의 전체 topic 목록 금지** —
  매칭 집합만 보낸다(요청 관련성 + 최소 노출). label 언어(현재 영어)는 Q3.
- **`name`/`description`은 우리 응답이 아니다 (열림 — Q10, 기획 gate).** agent 표시 데이터는
  bourbon-api 레지스트리 소관. 실사: personal agent의 `name`은 owner 유저 이름 복사본이고
  `description`은 **항상 NULL**(채우는 경로 없음 — `personal_agents/service.py`). bourbon-agent
  팀도 확인(2026-08-20): "지금은 비어 있고 공개 시점엔 채워야 할 것 같다. 기획안이 description을
  안 보여주면 응답엔 불필요"— 즉 **응답에 무엇이 실릴지는 기획안(추천 카드에 뿌릴 데이터)이
  결정**하고, 그 전까지 기본안은 클라이언트 hydration(우리는 `agent_id` + `matched_topics`만).
  후보 소스 정리: name ← bourbon-api `agents.name` / description ← bourbon-agent 자기 store의
  sharable persona(bio) — bourbon-api에는 채울 데이터가 없다.
- **실패 의미론을 접지 않는다.** 클라이언트는 422 `grounding_failed`(모델이 topic을 고쳐 재호출
  가능)·422 ambiguous·503 unavailable(재시도/불가 안내)·200+빈 목록(진짜 없음)을 구분해야 한다.
  현행 mock 배선은 전부 "unavailable"로 접는다 — 연동 시 분기 요청.
- **`need_type` 필드 불필요** — 1차 범위 축소(§0)로 소멸.
- **`room_id`는 우리 계약 밖 (확정 — 2026-08-20 bourbon-agent 확인).** 그쪽 답: "방 관련 정보를
  더 요청할 수 있어서 넣었다" — 즉 현재 정의된 동작이 없는 예비 필드다. 동작 없는 필드는 계약
  부채이므로 우리 요청 스키마에 넣지 않는다. room 맥락이 실제로 필요해지는 날, 그 동작에 맞는
  필드(`eligibility_context` 또는 제외 목록)를 그때 추가한다.
- **room 내 agent 제외 — deferred (2026-08-20 합의).** 1차 시나리오는 DM에서 자기 personal
  agent가 추천하는 것이라 "같은 방의 타인 agent" 케이스 자체가 없다 → OBT까지 보류. **재개
  트리거 = group room에서의 추천 도입.** 그때를 위한 메모 둘: ⑴ 충돌 확률은 균등하지 않다 —
  같은 방 멤버는 topic이 상관되어 있어(같은 관심사로 모인 방) 추천 충돌은 무작위 가정보다
  **높게** 나온다. ⑵ 제외는 응답 후 클라이언트 필터가 아니라 **cap 앞 서버 측**이어야 한다
  (후필터는 `max_results`를 깎는다 — self-exclusion과 같은 이유). 형태는 room_members 통째가
  아니라 **제외할 owner id 목록**(`exclude_owner_ids` 류)으로 받는다.
- **`context`는 가능하면 실제 대화 턴으로.** 모델이 쓴 요약 문자열보다 task payload의
  `context_messages`(구조화된 턴)가 grounding 재료로 낫다.

## 2. 저장 스키마 스케치 (extractor에 거는 요구 — 초안)

```
PK=USER#<owner_uuid>  SK=TOPIC#<topic_id>        ← 원본 topic (private 포함, 색인 안 됨)
  schema_version, topic_id, owner_id
  label_en, description_en, aliases_en: [..]
  visibility                                      ← 진실 (2차 재확인이 읽는 값)
  structure (parent/child topic ids 등 — extractor 설계에 따름)
  updated_at

PK=USER#<owner_uuid>  SK=TOPICSEARCH#<topic_id>  ← 검색 projection (§1-⑥) — publish 가능할 때만
  schema_version, topic_id, owner_id              존재. TOPIC#과 transact_write로 동기.
  label_en                                        ← 검색 대상
  description_en                                  ← 검색 대상 (회수 품질의 핵심 재료)
  aliases_en: [..]                                ← 검색 대상 (영어 내 동의 변형)
  (선택) tier                                     ← friend 등 tier 구분이 생기면
  (선택) search_eligible류 저빈도 파생 플래그      ← 임계 통과 시에만 바뀌는 값만 허용
  updated_at

PK=USER#<owner_uuid>  SK=TOPICSTAT#<topic_id>    ← 카운터 아이템 (고빈도, 색인 제외)
  schema_version
  evidence_count (종류별 개수·종류별 최신 시각 등 — 우리가 요구하는 gate 신호)
  last_evidence_at

PK=USER#<owner_uuid>  SK=CLAIM#<topic_id>#<claim_id>  ← claim (1차 범위 밖 — §0. 색인 제외)
  schema_version, proposition_en, stance/condition 등 — extractor 설계에 따름
```

- TOPICSEARCH#(색인 대상)와 TOPICSTAT#(고빈도)의 분리가 §1-⑤의, TOPIC#(원본)과 TOPICSEARCH#
  (publish projection)의 분리가 §1-⑥의 물리적 실현이다. extractor가 evidence를 볼 때마다 갱신하는
  것은 STAT 아이템뿐이라 색인 파이프라인이 조용하다.
- **owner↔agent 매핑·활성 상태**: 후보 owner를 agent로 해석하는 값(현행은 bourbon-api의 결정적
  `personal_agent_id` 파생)과 owner/agent 활성 여부는 이 테이블이 아니라 eligibility 확인의 몫이다 —
  탈퇴·비활성 owner 처리는 기존 파이프라인의 eligibility 단계가 담당하고, 스키마에 넣지 않는 대신
  여기서 그 경계를 명시한다.
- 필드 상세(어떤 gate 신호를 어떤 이름으로)는 extractor 설계가 나오면 이 문서 rev-up으로 계약화한다.
  여기서 잠그는 것은 **분리 원칙·projection 존재 규칙·schema_version**이지 필드 목록이 아니다.

## 3. 인덱스 설계 스케치 (문서 계약 = 우리 소유)

- 인덱스: `persona-topics-{stage}` (1차). 소스는 **TOPICSEARCH# 아이템만**(§1-⑥) — 인덱스에 있는
  문서는 정의상 publish 가능하다. claims 인덱스는 1차 범위 밖(§0).
- `_id = <owner_id>:<topic_id>` — 아이템 upsert/삭제가 문서 upsert/삭제로 멱등 매핑.
- 필드: `owner_id`(keyword), `topic_id`(keyword), `label_en`/`description_en`/`aliases_en`
  (text — memory-api `ANALYSIS_SETTINGS` 재사용: light_english stemmer + shingles), (선택) `tier`
  (keyword, 필터 전용), `updated_at`. **count류·gate 신호 없음** (§1-⑤).
- 질의: **expansion 변형마다 독립 검색**을 `_msearch`로 한 번에 보낸다 — 변형별 top-N(§1-⑦-3)과
  변형 귀속이 응답 단위로 자연히 나온다. (rev 2까지의 "한 bool + named query + 변형별 top-N"은
  성립하지 않는 조합이었다 — 한 bool의 size 컷은 전체 점수 기준이고 `matched_queries`는 귀속만
  알려준다.) 병합은 RRF/round-robin(`memory/search/fusion.py` — 점수 비교 없이 rank만).
  `owner_id != requester` self-exclusion 필터를 모든 서브 쿼리에 포함(§1-⑦-1).
- 검색 점수는 응답·랭킹에 쓰지 않는다. 변형별 top-N 컷에만 쓴다.
- 클라이언트·재연결·AOSS 특이사항(`_stats` 없음 등)은 memory-api
  `memory/search/opensearch_client.py`·`index_family.py` 패턴을 따른다.

## 4. 2차 필터 (읽기 시점 재확인) — BatchGet 계약 (rev 3에서 잠금)

1차 결과 (owner, topic) 쌍들로 저장소를 BatchGet(쌍당 TOPIC# + TOPICSTAT# 2아이템)한다.
판정 규칙:
- **visibility 재확인 — 무조건.** 인덱스에 있었다는 사실(=TOPICSEARCH# 존재의 잔상)을 신뢰하지
  않고 TOPIC#의 visibility로 판정한다(정확성/안전).
- **gate 신호 적용.** maturity 등 ordering contract의 gate 입력은 STAT 아이템 값으로만 판정한다.
  owner 수준은 any-pass가 기본(§1-⑦).
- TOPIC#이 사라졌으면(재추출·삭제) 후보 탈락 — 인덱스의 잔상은 여기서 걸러진다.

BatchGetItem 계약 (bourbon-agent `storage/dynamodb/batch.py`의 처리와 동형):
- **chunk = 후보 50쌍** — API 한도는 요청당 100아이템이고 쌍당 2아이템이다.
- 응답은 순서가 없다 → **key 기준 재결합**.
- **`UnprocessedKeys` ≠ 없는 아이템.** throttling 시 HTTP 200과 함께 일부 key만 돌아온다.
  bounded retry(지수 backoff) 후에도 남으면 그 후보를 조용히 탈락시키지 않는다 —
  **후보 탈락이 아니라 fail-loud(503 unavailable)**. throttling을 조용한 recall 손실로 바꾸면
  상류 장애가 호출자 탓으로 귀속된다(승계 규율: unavailable을 실패로 오귀속 금지).
- **일관성 분할: TOPIC#(visibility 판정)은 `ConsistentRead=true`, TOPICSTAT#(카운터)는 eventual.**
  BatchGet 기본값은 eventual이라 방금 private으로 바뀐 topic을 잠시 public으로 읽을 수 있다 —
  privacy 판정에만 strong을 쓰고, 카운터의 1초 staleness는 무의미하므로 RCU 2배를 지불하지
  않는다. (같은 요청 안에서 테이블별 ConsistentRead 지정이 가능하다.)

## 5. 열린 질문

| # | 질문 | 소유 | 상태 |
|---|---|---|---|
| Q1 | 색인 파이프라인: OSIS zero-ETL vs 자체 스트림 컨슈머 (비용 — OSIS는 파이프라인당 최소 OCU 상시 과금 / 운영 소유). 참고: Lambda 컨슈머는 스트림 배치 윈도우(최대 300초) 안에서 같은 key의 마지막 이미지만 upsert하는 이벤트 합치기가 부수적으로 따라오고, OSIS는 선언형 프로세서라 이런 debounce가 불가 — 단 토글류는 같은 `_id` 덮어쓰기라 비용이 소음 수준이므로 **결정 조건은 아니다** (1순위 방어선은 어차피 설정 변경 API의 rate limit — §1-⑥) | 인프라 협의 | 열림 |
| Q2 | OSIS 선택 시 SK 패턴 선택 색인(TOPICSEARCH#만) 가능 여부 — 불가하면 projection **테이블 분리**가 fallback (TOPICSEARCH#를 별도 테이블로 빼면 파이프라인은 테이블 전체 미러) | 인프라 협의 | 열림 (Q1에 종속) |
| Q3 | 영어 topic label·claim의 표시 시점 번역 — 한국어 유저에게 보여줄 추천 이유에 영어 label이 박힌다. 누가 언제 번역하나 | 제품 | 열림 |
| Q4 | iac: agent-recommendation의 AOSS 데이터 접근(IRSA) 추가 + 컬렉션 선택(기존 `bourbon-aoss-tokyo-{stage}` vs 신규) | 우리 + iac | 열림 |
| Q5 | 저장소 DynamoDB 확정 (우리 권고 §1-③ — MySQL 최종 폐기 확인) | extractor 팀 | 권고 전달 대기 |
| Q6 | deferq 유실 복구(outbox·watermark 재대사·sweep)와 `(message_id, extractor_version)` 멱등 추출 — 외부 리뷰 지적 전달. 복구가 생기면 §1-①의 best-effort 선언을 되돌린다 | bourbon-api / extractor 팀 | 전달 대기 |
| Q7 | owner 수준 gate의 집계 의미론 — 기본은 any-pass(§1-⑦). topic 간 evidence 합산 등 진짜 집계를 도입할지, 한다면 need별로 어떤 연산인지 | 우리 (eval 선행) | 열림 |
| Q8 | **추천 유형(need_type) 체계 전체 재설계** — persona가 실제 제공하는 정보가 취합된 뒤, 새 구조 위에서 2차 추천 유형(경험·stance·coverage 상당 포함 여부, claims 인덱스 여부)을 새로 디자인 | 우리 + 제품 | 열림 (1차 이후) |
| Q9 | iac 선행조건: 전용 테이블 생성 + **DynamoDB Streams 설정**(현행 `modules/dynamodb`에 stream 설정 없음) + OSIS 선택 시 초기 백필용 PITR·export S3 | iac | 열림 (Q1의 선행) |
| Q10 | 응답의 agent 표시 데이터(`name`/`description`) — **기획안(추천 카드에 뿌릴 데이터)이 선행 결정** (2026-08-20 bourbon-agent 합의). 그 전까지 기본안 = 클라이언트 hydration, 우리는 `agent_id`+`matched_topics`만(§1-⑩). description 소스 후보는 bourbon-agent sharable persona(bio) — bourbon-api엔 데이터 없음 | 기획 → 우리 + bourbon-agent | 열림 (기획 대기) |

## 6. 폐기 트랙에서 승계하는 불변식

폐기된 persona-api 트랙(로컬 태그 `discarded/persona-api-ownership-split`의 `persona_source_review.md`)
에서 전제(persona-api·MySQL 직접 읽기)와 무관하게 유효한 규율만 골라 승계한다:

1. **읽기 시점 재확인** — 인덱스는 관대한 쪽으로만 stale 허용, 진실은 저장소 (→ §1-⑥, §4)
2. **변경 주기 분리** — 고빈도 카운터는 검색 인덱스의 일이 아니다. 단, 이제 매핑이 아니라
   저장 아이템에서 강제한다 (→ §1-⑤)
3. **measure-first** — 벡터 채널은 측정 없이 기본 경로로 승격 금지 (→ §1-⑧)
4. **검색 점수는 랭킹이 아니다** — retrieval 폭 제한에만 사용 (→ §1-⑦, §3)
5. **DynamoDB vector search 기각** — TopK 100 상한·equality 전용 필터 등 구조적 제약. 새 그림도
   벡터를 DynamoDB에 두지 않는다 (재제안 방지용 기록)
6. **계약 테스트 payload를 consumer model에서 유도 금지** (→ §1-⑨)
7. **unavailable을 호출자 실패로 오귀속 금지** — 상류 부재/장애(BatchGet UnprocessedKeys 잔존 등)는
   후보 탈락이 아니라 503 fail-loud (→ §4)

승계하지 **않는** 것: 다국어 alias 저장 요구(→ 영어 한정 + 질의 시점 변형으로 대체, §1-②),
audience별 벡터 재료 규칙(벡터 자체가 유예), persona MySQL 스키마 실사 결과 전체(저장소가 바뀜).

## 7. 이전 트랙과의 관계

- persona-api 전환 트랙·memory-api v2 마이그레이션은 2026-08-19 폐기. 경위는 별도 PR
  (`docs/discard-persona-api-track`)의 archive masthead와 로컬 태그 `discarded/*`에 있다.
- **memory-api는 여전히 현행 데이터 소스다.** 이 문서의 체인이 배포되기 전까지 Discovery의
  edge/stance 소스는 현행 memory-api 계약 그대로이고, `memory_api_discovery_open_requests.md`의
  R1–R7도 유효하다. 이 문서는 **전환 후** 그림이다.

---

## 개정 이력

- **rev 1 (2026-08-20)** — 최초 작성. 2026-08-19 회의 결정(extractor는 bourbon-agent에 배치,
  산출물 영어 한정, OpenSearch 1차 + 저장소 2차) + 2026-08-20 설계 리뷰 합의(DynamoDB 전용 테이블
  권고, TOPIC#/TOPICSTAT# 아이템 분리, visibility 인덱스 포함, 랜덤 샘플링 금지, BM25 우선·벡터
  유예, 문서 계약 소유)를 기록. 열린 질문 Q1–Q5.
- **rev 2 (2026-08-20)** — Q1에 파이프라인별 이벤트 합치기 비교 주석 추가(Lambda=배치 윈도우로
  부수적 debounce, OSIS=불가하나 결정 조건 아님 — 방어선 1순위는 API 층).
- **rev 3 (2026-08-20)** — 외부 리뷰 반영. 상태를 "설계 기준 (초안)"으로 강등. **결정 변경 2건**:
  ⑥ visibility 필드 필터 → TOPICSEARCH# publish projection(private은 색인 자체를 안 함, 전환 =
  아이템 삭제 = 색인 삭제), ⑦ 1차 owner당 1-collapse(결함) → `(owner, top-K topic 집합)` 후보 +
  대표 선정은 gate·ordering 뒤 + any-pass 기본. 그 외: ① 유실 무해 단정 삭제 → best-effort 제품
  선언 + gate 튜닝 undercount 견고성(복구는 extractor 팀 소관, Q6), §0에 1차 범위 명시(topic 기반
  owner 발견 — stance·경험 회수는 Q8), §3을 `_msearch` 독립 검색 + RRF로 정정(한 bool + 변형별
  top-N은 성립 안 함), §4 BatchGet 계약 잠금(50쌍 chunk·UnprocessedKeys≠부재·fail-loud 503·
  TOPIC#만 ConsistentRead), self-exclusion을 1차 쿼리로 전진, eval 3층 분리, Q6–Q9 추가
  (iac streams/PITR 선행조건 포함), 승계 불변식에 오귀속 금지 추가.
- **rev 4 (2026-08-20)** — 1차 범위 재축소: 추천 유형은 "이 topic을 가장 잘 아는 agent" 하나,
  **need_type 축 자체를 1차에서 폐기**(체계 재설계는 Q8 — persona 정보 취합 후). §1-⑩ 신설:
  bourbon-agent 클라이언트 계약 정렬 — `matched_topics` 확정(매칭 집합만·대표 우선·전체 목록
  금지), name/description은 클라이언트 hydration 기본안(Q10), 실패 의미론 분기 요구, room_id는
  계약 밖, context는 실제 턴 권장.
- **rev 5 (2026-08-20)** — bourbon-agent 팀 회신 반영: room_id는 동작 없는 예비 필드로 확인 →
  계약 제외 확정. room 내 agent 제외는 deferred(1차 = DM 내 personal agent 추천이라 케이스 부재,
  재개 트리거 = group room 추천) + 재개 시 메모 2건(충돌 확률은 topic 상관으로 상승·제외는 cap 앞
  서버 측 `exclude_owner_ids`). Q10을 기획 gate로 갱신(description 실사: bourbon-api에선 personal
  agent에 항상 NULL, 소스 후보 = sharable persona).
