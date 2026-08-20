# Persona Topic Search — 신규 아키텍처 설계 (agent-recommendation 관점) — rev 1

작성: 2026-08-20 · 상태: **설계 확정 기록** (2026-08-19 회의 결정 + 2026-08-20 설계 리뷰 합의) · 개정 이력은 문서 끝.

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
- **agent-recommendation은 두 단계로 읽는다.** 1차 = AOSS 인덱스에서 recall(후보 topic-owner 쌍),
  2차 = 저장소에서 진실 재확인(visibility·gate 신호). 인덱스는 추천 순서를 결정하지 않는다 —
  ordering contract(gate→filter→lexicographic→tiebreak)는 그대로다.

## 1. 결정 사항 (2026-08-19 회의 + 2026-08-20 리뷰)

### ① extractor 배치 = bourbon-agent
bourbon-api가 발행하는 deferq 이벤트(`bourbon.message_created` 등, at-most-once fire-and-forget)를
bourbon-agent가 소비해 추출한다. 이벤트 유실 시 그 발화의 추출만 빠진다 — 추출은 누적 통계라
개별 유실이 치명적이지 않고, 이 성질이 deferq의 전달 보증과 맞는다. (반대로 **색인**은 유실 =
영구 stale이라 deferq 경로를 쓰지 않는다 — ④.)

### ② 산출물은 영어 한정
topic label·claim proposition·alias 전부 영어. 따라서:
- **query expansion은 영어 변형 생성이다.** 한국어 need "재택근무"에서 `remote work / working from
  home / telecommuting / WFH`처럼 영어 내 동의 변형까지 LLM이 한 번에 생성한다. 단순 1:1 번역이
  아니다. named query로 어떤 변형이 맞았는지 회수한다(§3).
- recall 부담이 저장 시점(다국어 alias — 폐기된 트랙의 1순위 요구)에서 **질의 시점(번역·변형
  품질)**으로 이동한다. 질의 시점이 더 나은 자리다 — 저장된 alias 오류는 재추출 전까지 박제되지만
  질의 변형 오류는 요청 단위라 즉시 개선된다.
- 인덱스 analyzer가 영어로 단순화된다. nori 검증 불필요. memory-api의 `ANALYSIS_SETTINGS`
  (light_english stemmer + shingle 근접 부스트, `memory/search/analysis.py`)를 재사용한다.
- **eval은 번역 단계를 포함해야 한다**: golden set이 "한국어 need → 영어 topic" 경로를 통째로
  측정해야 낮은 recall이 검색 탓인지 변형 생성 탓인지 분리된다.

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
   추출된 파생물을 평문 저장하는 것이며, 노출 통제는 visibility 필드 + 2차 재확인이 담당한다.

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

### ⑥ visibility는 인덱스에 포함, count류는 제외
visibility와 count는 변경 빈도의 부류가 다르다: count는 **시스템 전체 메시지 볼륨**에 비례하고,
visibility는 **유저의 의도적 설정 행위**에 비례한다(문서 1건 재색인 — 유저가 껐다 켰다를 반복해도
단일 문서 upsert의 반복일 뿐이고, 남용 방어가 필요하면 자리는 저장 설계가 아니라 설정 변경
엔드포인트의 rate limit/debounce다).

인덱스에 넣는 이유는 성능이 아니라 안전과 recall이다:
- visibility가 인덱스에 없으면 1차가 private topic까지 후보로 끌어와 그 텍스트가 스코어링에
  참여한다. private 데이터가 검색 경로를 타는 것 자체를 줄인다.
- 후보 상한(⑦)을 걸 때 private이 섞인 풀에서 자르면 2차에서 살아남을 public 후보가 밀려나는
  recall 손실이 생긴다. pre-filter일수록 상한이 유효 후보에 쓰인다.

**불변식 (승계): 인덱스는 관대한 쪽으로만 stale해도 되고, 그것은 2차 읽기 시점 재확인이 잡는다.**
빠른 토글 중 위험한 방향(인덱스=public, 저장소=private)은 2차가 무조건 잡고, 안전한 방향은
몇 초의 recall 손실로 끝난다. 진실은 항상 저장소다.

### ⑦ 후보 폭주 대응 — 랜덤 샘플링 금지
후보가 폭주하면(예: 10만 topic-owner 쌍) 랜덤으로 남기지 않는다. 랜덤은 필터 전에 자르는 것이라
2차를 통과할 후보를 통과 못 할 후보와 같은 확률로 버린다. 순서:
1. **owner collapse.** 최종 추천은 owner당 한 슬롯(`_keep_one_edge_per_agent`)이므로 실제
   cardinality는 owner 수다. 1차에서 owner당 최고 히트 1개로 접는다.
2. **쿼리별 top-N.** expansion 쿼리마다 retrieval 순위 상위 N만 취한다. 검색 점수는 recall 채널의
   폭 제한이지 랭킹이 아니다 — ordering contract와 충돌하지 않는다.
3. 그래도 넘치면 마지막에 캡 — 이 시점의 꼬리는 모든 expansion 쿼리가 낮게 평가한 것들이다.

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

## 2. 저장 스키마 스케치 (extractor에 거는 요구 — 초안)

```
PK=USER#<owner_uuid>  SK=TOPIC#<topic_id>        ← 검색 아이템 (저빈도)
  schema_version, topic_id, owner_id
  label_en                                        ← 검색 대상
  description_en                                  ← 검색 대상 (회수 품질의 핵심 재료)
  aliases_en: [..]                                ← 검색 대상 (영어 내 동의 변형)
  visibility                                      ← 색인 포함 (§1-⑥)
  structure (parent/child topic ids 등 — extractor 설계에 따름)
  updated_at

PK=USER#<owner_uuid>  SK=TOPICSTAT#<topic_id>    ← 카운터 아이템 (고빈도, 색인 제외)
  schema_version
  evidence_count (종류별 개수·종류별 최신 시각 등 — 우리가 요구하는 gate 신호)
  last_evidence_at

PK=USER#<owner_uuid>  SK=CLAIM#<topic_id>#<claim_id>  ← claim (2차/근거 제시용, 1차 색인 제외)
  schema_version, proposition_en, stance/condition 등 — extractor 설계에 따름
```

- TOPIC#와 TOPICSTAT#의 분리가 §1-⑤의 물리적 실현이다. extractor가 evidence를 볼 때마다 갱신하는
  것은 STAT 아이템뿐이라 색인 파이프라인이 조용하다.
- 필드 상세(어떤 gate 신호를 어떤 이름으로)는 extractor 설계가 나오면 이 문서 rev-up으로 계약화한다.
  여기서 잠그는 것은 **분리 원칙과 schema_version**이지 필드 목록이 아니다.

## 3. 인덱스 설계 스케치 (문서 계약 = 우리 소유)

- 인덱스: `persona-topics-{stage}` (1차). claims 인덱스는 2단계.
- `_id = <owner_id>:<topic_id>` — 아이템 upsert가 문서 upsert로 멱등 매핑.
- 필드: `owner_id`(keyword), `topic_id`(keyword), `label_en`/`description_en`/`aliases_en`
  (text — memory-api `ANALYSIS_SETTINGS` 재사용: light_english stemmer + shingles), `visibility`
  (keyword, 필터 전용), `updated_at`. **count류·gate 신호 없음** (§1-⑤).
- 질의: expansion 변형들을 **named query**로 묶은 bool — 응답의 `matched_queries`로 어떤 변형이
  맞았는지 무료로 회수. `visibility` pre-filter. owner collapse(§1-⑦-1)는 `collapse` 또는
  `terms` aggregation + top_hits — AOSS 지원 여부에 따라 선택.
- 검색 점수는 응답·랭킹에 쓰지 않는다. 쿼리별 top-N 컷에만 쓴다.
- 클라이언트·재연결·AOSS 특이사항(`_stats` 없음 등)은 memory-api
  `memory/search/opensearch_client.py`·`index_family.py` 패턴을 따른다.

## 4. 2차 필터 (읽기 시점 재확인)

1차 결과 (owner, topic) 쌍들로 저장소를 BatchGet(TOPIC# + TOPICSTAT#, 100개 단위)한다:
- **visibility 재확인 — 무조건.** 인덱스 값은 신뢰하지 않는다(정확성/안전).
- **gate 신호 적용.** maturity 등 ordering contract의 gate 입력은 STAT 아이템 값으로만 판정한다
  (성능·기밀상 인덱스에 없음).
- 아이템이 사라졌으면(재추출·삭제) 후보 탈락 — 인덱스의 잔상은 여기서 걸러진다.

## 5. 열린 질문

| # | 질문 | 소유 | 상태 |
|---|---|---|---|
| Q1 | 색인 파이프라인: OSIS zero-ETL vs 자체 스트림 컨슈머 (비용 — OSIS는 파이프라인당 최소 OCU 상시 과금 / 운영 소유) | 인프라 협의 | 열림 |
| Q2 | OSIS 선택 시 SK 패턴 선택 색인(TOPIC#만) 가능 여부 — 불가하면 검색/카운터 **테이블 2분할**이 fallback | 인프라 협의 | 열림 (Q1에 종속) |
| Q3 | 영어 topic label·claim의 표시 시점 번역 — 한국어 유저에게 보여줄 추천 이유에 영어 label이 박힌다. 누가 언제 번역하나 | 제품 | 열림 |
| Q4 | iac: agent-recommendation의 AOSS 데이터 접근(IRSA) 추가 + 컬렉션 선택(기존 `bourbon-aoss-tokyo-{stage}` vs 신규) | 우리 + iac | 열림 |
| Q5 | 저장소 DynamoDB 확정 (우리 권고 §1-③ — MySQL 최종 폐기 확인) | extractor 팀 | 권고 전달 대기 |

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
