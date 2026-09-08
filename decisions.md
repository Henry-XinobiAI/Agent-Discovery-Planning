# 결정 레지스터 (재설계, 2026-09-08~)

> 결정은 이 문서만 갖는다. 설계 문서는 결정을 인용하되 새로 내리지 않는다. 정해지지 않은 것을 정해진 것처럼 쓰지 않는다. 이전 레지스터(D01–D26)는 `archive/2026-09-08_pre-redesign/decisions.md`에 있고 **유효하지 않다.**
>
> 출처: `오너` = 오너가 말함 · `분석` = 코드·문서에서 도출.

| # | 결정 | 출처 | 날짜 | 어디에 반영 |
|---|---|---|---|---|
| R01 | 이전 문서의 결정·제약을 전제하지 않는다. 전부 아카이브하고 새로 판단한다 | 오너 | 2026-09-08 | `archive/2026-09-08_pre-redesign/` |
| R02 | 추천은 세 타입: ① 자기 agent에게 free text topic + context로 명시 요청, ② 탐색 서브탭에서 내 topic으로 대화해 볼 타인 agent, ③ 탐색 메인에서 비슷한 사람들이 좋아한·내가 좋아할 agent | 오너 | 2026-09-08 | 재설계 §2 |
| R03 | 타입 ①은 뽑힌 topic(상한 3)을 모두 가진 agent가 먼저, 그다음 일부만 가진 agent. 1차 키 커버 수, 2차 키 점수 | 오너 | 2026-09-08 | 재설계 §2-1, 계약 §4-4 |
| R04 | 타입 ②는 topic별 섹션 목록 | 오너 | 2026-09-08 | 재설계 §2-2, 계약 §2-2 |
| R05 | 타입 ③은 상호작용 로그가 쌓이기 전까지 인기도로 시작해도 된다 | 오너 | 2026-09-08 | 재설계 §2-3 |
| R06 | topic·agent의 default는 private. 유저가 public/friends로 공개하고 다시 비공개로 되돌릴 수 있다. friends tier는 처음부터 후보에 든다 | 오너 | 2026-09-08 | 재설계 §3, 계약 §5 |
| R07 | 탐색 탭은 클라이언트가 `/api/svc/agent-discovery`를 직접 호출한다(topic-api의 `/api/svc/topic`과 같은 형태). 타입 ①은 bourbon-agent가 내부 API로 | 오너 | 2026-09-08 | 계약 §1 |
| R08 | 저장소는 MySQL, PostgreSQL, DynamoDB, Redis, OpenSearch 안에서. 다른 저장소 추가는 선호하지 않는다 | 오너 | 2026-09-08 | 재설계 §0·§5 |
| R09 | 오픈소스 중심안(A)과 직접 구현안(B)을 둘 다 만들고 10만 합성 유저로 지연 시간·비용·재계산·품질을 비교해 최종 선택한다. 섞을 수 있다 | 오너 | 2026-09-08 | 재설계 §5·§6, `synthetic_population_spec.md` |
| R10 | 추가할 이벤트는 agent-discovery-api에서 먼저 정의·발행·시험하고 그 뒤 발신 repo에 요청한다. 발행 repo가 그 지점에서 그 필드를 갖는지 먼저 검증한다 | 오너 | 2026-09-08 | 이벤트 정의서 §3·§4 |
| R11 | public agent와의 대화는 친구가 아니어도 시작할 수 있게 한다. 방법(방 종류)은 bourbon-api의 몫이고 DM이 유력 | 오너 | 2026-09-08 | 이벤트 정의서 §2-4 |
| R12 | 기존 `POST /recommend`의 필드명은 유지하지 않는다. 타입별로 route와 스키마를 나눈다 | 오너 | 2026-09-08 | 계약 머리말·§0 |
| R13 | 유저 규모는 20만 → 100만 → 1천만 → (1억) 단계로 대응한다. 처음부터 최대 규모를 요구하지 않는다 | 오너 | 2026-09-07 (재설계에서도 유효, 2026-09-08 재확인) | 재설계 §7 |
| R14 | topic 변경은 이미 있는 `bourbon.topics_updated`를 힌트로 받아 topic-api를 다시 조회한다. 스냅샷 이벤트를 새로 요청하지 않는다 | 분석 | 2026-09-08 | 이벤트 정의서 §2-1 |
| R15 | 대화 시작 이벤트는 bourbon-api가 방을 생성할 때 낸다(`agent_dm_opened`). turn은 이미 있는 `message_created`로 세고 새 turn 이벤트는 요청하지 않는다 | 분석 | 2026-09-08 | 이벤트 정의서 §2-4·§2-5 |
| R16 | 다른 유저의 agent와 대화해 배우는 것은 이 서비스의 핵심 feature다. 따라서 (a) 합성 스펙의 대화율 λ=3은 너무 작다고 보고 비교는 {3, 10, 30}을 모두 돈다, (b) CF가 배우는 신호는 "대화를 시작했다"가 아니라 turn 수·재방문으로 가중한 confidence다 | 오너 (a) · 분석 (b) | 2026-09-08 | 합성 스펙 §2·§7·§8, 계약 §7 `cf_score` |
| R17 | 요청자의 친구 집합은 `bourbon.friendship_changed`로 우리 저장소에 미러한다(요청 시 bourbon-api 조회·TTL 캐시는 쓰지 않는다). visibility 판정 `tier = public ∨ (tier = friends ∧ owner ∈ friends(요청자))`는 **후보 조회 쿼리 안에서** 한다 — 공개된 row 저장소를 읽는 소스(`topic_index`, `content_similarity`, PostgreSQL `popularity`, 이웃 테이블)는 술어를 쿼리에 넣어 `limit`만큼만 읽고, 요청자별 사전 계산은 배치 시점 친구 집합으로 후보를 제한한다. 넉넉히 가져와 뒤에서 거르는 것은 술어를 넣을 수 없는 소스(외부 엔진 등)만이다. 응답 직전 재확인(불변식 4)은 그대로 남는다 | 오너(방향) · 분석(근거: 타입 ①② 쿼리는 이미 그렇게 동작하고 친구 5,000 배열에서 p95 2.3 ms, `agent_discovery_walkthrough.md` §3-2) | 2026-09-08 | 계약 §4-2·§4-3·§5·§6, 재설계 §3-3, 이벤트 정의서 §2-7, walkthrough §1·§2-1·§5 |
| R18 | 저장소 배치. **조인·집계가 있는 집합은 PostgreSQL**(`open_topic_rows`, `friends`, `agents`, `interactions`와 turn 카운터, `popularity`, 이웃 테이블, `population_stats`). **단건 키 읽기·쓰기만 있고 보존 기간이 있는 집합은 DynamoDB**(`precomputed_for_you` PK `user_id`; 결정 로그 PK `recommendation_id` + 평가용 GSI `type, served_day` + TTL; `event_log` TTL 180일). **Redis는 deferq만** 쓰고 우리 데이터는 두지 않는다(인기도 sorted set·topic 목록 캐시 없음). 처음부터 이렇게 두고 규모에 따라 옮기지 않는다. 근거: Redis는 메모리를 선구매하고 DynamoDB는 사용량 과금이라 10만~100만 구간에서 한 자릿수 배 저렴, 결정 로그는 나중에 옮기면 과거분이 갈라짐, 플랫폼에 DynamoDB 운영 절차(IAM·dynamodb-local·배포)가 이미 있음. 감수: GetItem p50 3~5 ms(Redis 1 ms 미만), 결정 로그 집계는 SQL 대신 GSI Query·스캔 코드. Gorse 채택 시 그 자체 저장소(MySQL/PostgreSQL data·cache store)는 별개 | 오너 | 2026-09-08 | 계약 §4-2·§6·§8, 재설계 §5-1·§5-2·§6-1·§6-3·§7, 합성 스펙 §8-2, walkthrough §2·§5·§7 |
| R19 | 타입 ③ 사전 계산(`precomputed_for_you`)은 **활성 요청자에게만** 만든다. 활성 = `agents.last_active_at`이 창(파라미터, 예 30일) 안. `last_active_at`은 우리 자신의 신호 셋으로 갱신한다: 우리 API에 대한 요청, `agent_dm_opened`의 actor, `topics_updated`(자기 agent와 대화했다는 뜻). CF **학습**에는 비활성 유저의 대화도 그대로 쓴다(아이템 쪽 신호, 비용 없음) — 좁히는 것은 출력 루프와 DynamoDB 쓰기다. 오랜만에 돌아온 유저의 첫 요청은 항목이 없으므로 콜드스타트 경로(인기도 + content, `basis` = `popularity`/`content`)로 **완전한 목록**을 답하고, 그 요청이 `last_active_at`을 갱신해 다음 배치에 포함된다. 이 응답은 축소 응답이 아니다 — `degraded`에 `stale_precompute`를 넣지 않는다(그 값은 "있는데 오래됐다"). 타입 ②와 타입 ③의 인기도·content는 요청 시 계산이라 비활성과 무관하게 첫 요청에서 채워진다. **후보(소유자) 쪽은 활동 여부로 제외하지 않는다** — row는 유저가 공개한 것이고(불변식 1), 오래된 agent는 `recency`·`popularity` feature가 순위로 내린다. 하드 제외는 O17 | 오너 | 2026-09-08 | 계약 §2-3·§3-4·§6 `agents`·§7, 재설계 §2-3·§7, 합성 스펙 §8-1, walkthrough §2-1·§5-3·§5-6 |

## 열린 항목 (결정 대기)

| # | 항목 | 누가 |
|---|---|---|
| O1 | agent 공개 여부의 필드: `enabled` 재사용인지 새 필드인지 | 오너 / bourbon-api |
| O2 | 재조회 tier 범위: public·friends만 저장하고 요청자 자신의 topic은 요청 시 조회(권고) vs private까지 소유자 키 아래 미러 | 오너 |
| O3 | `recommendation_id`를 클라이언트가 대화 시작 요청에 실어 주는 변경을 지금 요청 범위에 넣는가 | 오너 |
| O4 | 인기도 정의(기간, 대화 시작만/지속 포함, 신규 부스트) | 오너 |
| O5 | "맞음/안 맞음" 표시의 유무와 축 | 오너 |
| O6 | 명시 피드백(좋아요/숨기기)의 유무 | 오너 |
| O7 | 재활성 이벤트가 없다 — **탈퇴 뒤** 돌아온 유저를 어떻게 아는가(`user_registered`가 다시 나오나). "오래 안 쓰다 돌아온" 유저는 R19의 `last_active_at`이 우리 신호로 잡으므로 이 항목은 탈퇴·재활성만 남는다 | bourbon-api 확인 |
| O8 | A안의 엔진: Gorse(서비스형) vs `implicit`(라이브러리형). recsys 라이브러리 사용은 A안으로 분류한다. **근거(2026-09-08, `library_verification.md`)**: LightFM은 Python 3.14에서 빌드 실패라 후보에서 뺐다. `implicit` ALS는 10만×10만에서 fit 1~11 s·RSS 300 MB. Gorse v0.5.11은 Redis cache store에 RediSearch를 요구해 R08 안에서는 MySQL/PostgreSQL cache store만 가능하고, 그때 10만 유저 상시 재계산 사이클(1.5~7분)에 cache 1,400만 행. 기본 설정에서는 CF가 서빙되지 않는 원인 둘(§4-3)이 있고, 고친 뒤 서빙 HR@10 0.0006은 `implicit` ALS(0.0054)의 1/9 | 비교 설계 시 |
| O9 | 타입 ② 섹션 크기와 페이지(섹션당 몇 명, 한 화면에 몇 섹션) | 오너 |
| ~~O10~~ | ~~요청자의 친구 집합을 요청 시 bourbon-api에서 조회하나 `friendship_changed`로 미러하나~~ → **R17로 닫힘**(2026-09-08, 미러) | — |
| O11 | 타입 ③ B안 CF의 첫 구현: 아이템 기반 이웃 vs 행렬 분해. **근거(2026-09-08, `library_verification.md` §3)**: 스펙 밀도(λ=3)에서 코사인 정규화 이웃은 무작위 수준, 정규화 없는 동시 출현은 ALS 16f의 절반, 어느 CF도 인기도를 넘지 못한다. λ=10에서 ALS 16f와 동시 출현+인기도가 인기도와 동률이 되며 군집 신호는 두 배 | 합성 데이터 측정 후 |
| O12 | friends tier 근거의 후보를 랭커에서 올릴지(`tier_is_friends` 가중) | 오너 |
| O13 | 타입 ③ 사전 계산의 갱신 주기와 `stale_precompute` 기준 | 비교 설계 시 |
| O14 | **CF 가중을 켜는 기준을 자동 판정으로 두는가.** 제안: 배치가 주기적으로 ALS를 학습해 실로그 leave-one-out에서 인기도와 비교하고, HR@10과 군집 다양성에서 이길 때만 랭커의 `cf_score` 가중을 0에서 올린다. λ 추정으로 시점을 정하지 않는다. 근거 `library_verification.md` §3 | 오너 |
| O15 | **배움을 위한 탐색(exploration) 항을 랭커 목표에 넣는가.** 추천이 만든 대화를 CF가 다시 배우는 노출 편향이 있고, 목표가 "새 지식을 만나게 하기"면 인기도·유사도만으로는 같은 사람만 보인다. 결정 로그의 `entry`·`recommendation_id`로 보정 가능 | 오너 |
| O16 | **파라미터 자동 보정의 주기·샘플 임계값·보존 기간**(합성 스펙 §8). 제안: 하루 1회, 90일 창, 활성 유저 1,000명·대화 시작 5,000건 미만이면 기본값 유지, `event_log` 보존 180일 | 오너 / 구현 시 |
| O17 | **오래 활동하지 않은 소유자의 agent를 후보에서 하드 제외하는가.** R19는 제외하지 않고 `recency`·`popularity`로 순위만 내린다. agent는 소유자 없이도 대화하므로 "오래 안 들어온 사람의 agent는 추천하지 않는다"가 제품 의도인지는 오너 판단. 하기로 하면 후보 조회 술어에 `last_active_at` 조건 하나 | 오너 |
