# Gorse 저장소 규모와 비용 — 20만에서 1억까지, 단계별로

> **결론**: 저장소는 **data store = MySQL, cache store = Valkey**로 시작하고, 규모는 **단계마다 노드만 바꿔**
> 따라간다(§8). 목표 유저 풀은 오너가 단계로 정했다(2026-09-07, `D26`) — **20만 → 100만 → 1천만, 최종
> 1억까지 대응**. 아키텍처가 바뀌는 지점은 하나뿐이고 이미 결정돼 있다: surface 1 후보 생성이 Gorse를 떠나
> 우리 인덱스로 가는 `D22`의 뒤집는 조건. 그 시점은 단계 이름이 아니라 **운영 계측**(master RSS·사이클 길이)이
> 정한다. 1천만부터는 surface 2가 전원이 아닌 **활성 창만** 담아야 하고(§7·§8), 1억은 그 연장이다.
>
> **1억 상한에서의 형태 비교**(§2–§5)는 그대로 둔다 — 계획이 마지막 단계까지 닿는지 보는 천장이다. 거기서
> 남는 사실: data store는 관계형, cache store는 Redis 계열이 모양에 맞고, Aurora를 cache store로 쓰는 조합만
> 명확히 틀렸다. DocumentDB는 **I/O-Optimized 스토리지 전제로만** 성립하고(Standard면 I/O 요금이 인스턴스보다
> 크다 — §4, 2026-09-04 재산정) 6-5·6-6이 기각한다 — 자체 MongoDB에서의 이전 경로가 아니고(6-5), `iac`에 그
> 제품군이 하나도 없다(6-6).
>
> **어디에 두는가**(§6): 이미 있는 MySQL·Valkey에 얹으면 현실적 규모 전부에서 **공유가 분리보다 싸다**(6-6).
> 그러므로 **분리의 근거는 비용이 아니라 실패 도메인**이다 — degrade해도 되는 Gorse를 degrade하면 안 되는
> 인스턴스에 넣지 않는다. **dev는 공유, prod는 분리**(6-6, 노드 크기는 §8). k8s에 직접 띄우는 안(6-1~6-5)은 작은
> 쪽 끝에서 절감액도 운영 부담도 0에 가깝고 이전 비용이 재계산 한 번이라 성립하지만, managed 대응물이 *같은*
> 엔진(MySQL·Valkey)을 골랐으므로 어느 쪽에서 시작해도 출구는 열려 있다(6-5의 두 규칙). 규모와 무관하게 남는
> 사실 하나는 **디스크 상주가 전량 RAM보다 한 자릿수 싸다**는 것이다.
>
> **문서 지위**: 조사 자료 + 단계 계획. 채택·기각은 `decisions.md`가 소유한다(`D22`·`D24`·`D26`; `STO-S1`은 D26을
> 가리킨다). [`gorse.md` §6-2](gorse.md)가 "1억 규모 PoC는 다음을 분리해 측정한다"로 축만 잡아두고 비워 둔 칸을
> 채운다.
>
> **증거 등급**: `문서`(AWS 공식 가격표·Price List API·Gorse 소스) · `실측`(인용 — 원본은
> [`gorse.md` §11–§12](gorse.md)) · `판단`(계산·의견) · `오너`(결정) · `열린 항목`.
>
> 가격은 **AWS Price List API에서 직접 추출**(조회 2026-09-03, 목록 갱신일 2026-08-31; DocumentDB I/O-Optimized
> 항목은 2026-09-04), us-east-1 · ap-northeast-1(도쿄) · ap-northeast-2(서울) 셋을 나란히 둔다. 재현 명령은 §10.

## 1. 저장소가 둘이고 워크로드가 반대다

| | data store | cache store |
|---|---|---|
| 담는 것 | User / Item / Feedback 원본 행 | 사용자별 top-K, item·user 이웃, ranker 출력 |
| 쓰기 | append (ingest) | **주기적 전면 덮어쓰기** (worker) |
| 읽기 | 학습 시 **전량 스캔** | 요청당 **키 하나 point read** |
| 규모 (1억 상한, 단계별은 §8) | feedback 20억 행 (`README.md` §11의 "평균 interaction 20개") | 100억 entry (`gorse.md` §6-2) |

`판단` **하나의 답이 나오지 않는다.** Redis가 cache store에서 최선이면서 data store에서는 실격이다 —
20억 feedback 행을 RAM에 두는 것은 논외다. 아래 비교를 두 축으로 나누는 이유다.

## 2. 규모 — `gorse.md` §6-2의 하한은 우리 ID 형식에서 3~4배가 된다

**이 절과 §4·§5는 1억 상한이다.** 단계별 값과 구성은 §8. 상한을 남기는 이유는 계획이 마지막 단계까지 닿는지 보기 위해서다.

`gorse.md` §6-2가 준 값은 `100,000,000 × top 100 = 100억 entry`, entry당 16 bytes 가정으로 **160 GB 하한**이다.

`판단` 그 16 bytes는 **정수 ID 가정**이다. 우리 `ItemId = personal_agent_id`는 UUID다.

```text
ZSET 하나 = 100 member × (36B id + score) ≈ 5.5 KB   ← listpack 인코딩
                                                        (100 < 128 entries, 36B < 64B value)
100,000,000 users × 5.5 KB                 ≈ 550 GB
+ 키 오버헤드 100M × ~100B                 ≈  10 GB
                                            ─────────
payload                                     ≈ 560 GB
+ replica 1개 (운영 최소)                   ≈ 1.1 TB 프로비저닝
```

`gorse.md` §8-2가 열거한 item neighbors · user neighbors · non-personalized 캐시는 위에 포함되지
않았다. 같은 절 말대로 K를 500으로 올리면 5배다.

data store는 별개로 feedback 20억 행 ≈ 인덱스 포함 **400~500 GB**.

## 3. 가격 — 리전별 단가

`문서` 서드파티 집계 사이트에는 리전별 값이 없어 공식 Price List API에서 직접 뽑았다.

### 3-1 ElastiCache 노드 — `cache.r6g.xlarge`(26.32 GiB)의 GB당 환산

| 엔진 | us-east-1 | ap-northeast-1 (도쿄) | ap-northeast-2 (서울) |
|---|---|---|---|
| Redis | $0.411/hr → **$11.40/GB·월** | $0.493/hr → **$13.67/GB·월** | $0.491/hr → **$13.62/GB·월** |
| Valkey | $0.3288/hr → **$9.12/GB·월** | $0.3944/hr → **$10.94/GB·월** | $0.3928/hr → **$10.89/GB·월** |
| Redis r6gd (티어링) | $0.781/hr → RAM $21.66, 총용량 **~$4.33** | $0.937/hr → RAM $25.99, 총용량 **~$5.20** | **제공되지 않음** |

★ **도쿄와 서울은 사실상 같다.** 서울이 0.4% 싸고, 둘 다 us-east-1 대비 **+20%**다. 리전 선택은
가격 문제가 아니다 — 아래 두 항목이 진짜 차이다.

★ **Valkey가 Redis보다 정확히 20% 싸다.** 세 리전 모두 비율이 0.80으로 동일하다. §4의 1.1 TB
기준으로 월 $3,000 차이다. **다만 이 레버는 이미 당겨져 있다** — `iac`의 `elasticache-redis` 모듈이
`engine = "valkey"`로 고정되어 있고 현재 인스턴스는 전부 Valkey 9.1이다(§6-6). 따라서 §4의 Redis
행은 가상의 비교점이고, **우리의 실제 기준선은 Valkey 행**이다.

★ **r6gd 데이터 티어링이 서울에 없다.** `문서` 도쿄 24개 product entry, 서울 0개. §4에서 가장 싼
RAM 경로가 서울에서는 선택지가 아니다 — **리전이 아키텍처를 바꾼다.** 이미 도쿄를 쓰고 있으므로
현 시점 제약은 아니지만, 서울 이전이 논의되면 이 항목이 함께 열린다.

### 3-2 스토리지·I/O

| | us-east-1 | 도쿄 | 서울 |
|---|---|---|---|
| Aurora 스토리지 | $0.10/GB·월 | **$0.12** | **$0.12** |
| Aurora I/O-Optimized 스토리지 | $0.225/GB·월 | **$0.27** | **$0.27** |
| Aurora I/O | $0.20/백만 | **$0.24** | **$0.24** |
| DocumentDB 스토리지 | $0.10/GB·월 | **$0.12** | **$0.12** |
| DocumentDB I/O-Optimized 스토리지 | $0.30/GB·월 | **$0.36** | **$0.36** |
| DocumentDB I/O | $0.20/백만 | **$0.24** | **$0.24** |

스토리지·I/O는 도쿄와 서울이 **완전히 동일**하고, us-east-1 대비 정확히 +20%다.

★ **RAM이 디스크 스토리지의 약 114배다** (도쿄 Redis $13.67 ÷ $0.12). 리전을 바꿔도 이 비율은
그대로이고, 이 장의 결론은 여기서 나온다.

## 4. cache store 후보별

§2의 1.1 TB(560 GB payload + replica 1)를 §3-1·§3-2 단가에 대입한다 — **1억 상한에서의 형태 비교**이고 단계별 노드는 §8이다. **도쿄 기준**이고, 서울은
ElastiCache가 0.4% 싸고 스토리지·I/O는 동일하므로 r6gd 행을 빼면 같은 표다.

| | 도쿄 월 비용 `판단` | 판정 |
|---|---|---|
| **ElastiCache Redis (all-RAM)** | 1,126 GB × $13.67 ≈ **$15,400** | 지연은 최고(p99 <1 ms). 순수 RAM으로 1억을 담는 것이 가장 비싼 선택 |
| **ElastiCache Valkey (all-RAM)** | 1,126 GB × $10.94 ≈ **$12,300** | 같은 것을 20% 싸게. 엔진만 바꾸면 되고 스키마는 그대로다 |
| **ElastiCache r6gd (티어링)** | 1,126 GB × ~$5.20 ≈ **$5,900** | **이 워크로드에 정확히 맞는다** — 거대한 캐시 + 심한 편향 접근(1억 중 대부분이 비활성). **단, 서울에는 없다**(§3-1) |
| **DocumentDB** (I/O-Optimized) | 스토리지 2.2 TB × $0.36 ≈ **$790** + 인스턴스 $2,600~5,300(I/O-Optimized는 인스턴스 +10%) ≈ **$3,400~6,100**. **Standard 스토리지는 논외** — 스토리지는 $264지만 전면 refresh 1회당 I/O가 $2,600~12,000이라 월 $26,000~120,000 | `실측` S4·S9로 모양을 고쳤다(2026-09-04): 유저 1명의 top-100 = **문서 100개**(`documents` 컬렉션, `AddScores`가 건당 upsert), 문서 182 B + 인덱스 38 B. 10⁸ 유저 × 100 = **10¹⁰ 문서 ≈ 2.2 TB**(§2의 560 GB의 4배; replica는 스토리지를 공유하므로 ×2 없음). point read 1~5 ms — surface 2의 예산에서 문제 없음. **⚠ 형태 평가이지 채택 권고가 아니다 — 6-5·6-6이 기각한다** |
| **Aurora MySQL/PostgreSQL** | 스토리지는 같으나 **행 수가 100억** | `판단` **모양이 틀렸다.** sorted set을 `(name, member, score)` 행으로 펴면 100억 narrow row를 주기적으로 전면 재작성하게 되고, 인덱스 유지비와 (PostgreSQL이면) vacuum 부담이 여기서 터진다 |

I/O 산정 근거 `판단` (2026-09-04 재산정 — 이전 산정은 "유저당 문서 1개 + 배열 100개 × ~5 I/O = 5억 I/O/refresh ≈ $1,200/월"이었고,
모양이 틀려 삭제했다):

- **쓰기 패턴** `실측`(Gorse v0.5.11 `storage/cache/mongodb.go` · `worker/pipeline.go`): 유저 1명 refresh = `AddScores`가 건당
  `UpdateOne(upsert)` 100개를 `BulkWrite` 한 번에 → 이어서 `DeleteScores(Before: recommendTime)`로 밀려난 항목 삭제. 복합 인덱스 둘
  (`collection,subset,id` · `collection,subset,categories,is_hidden,score`)이 매 upsert마다 갱신된다.
- **과금 단위** `문서`(DocumentDB Pricing): 읽기 = 버퍼 캐시에 없는 8 KB 페이지 1개당 1 I/O, 쓰기 = 트랜잭션 로그 4 KB 단위당 1 I/O(4 KB 미만
  동시 쓰기는 엔진이 묶을 수 있음).
- **refresh 1회(10¹⁰ upsert)**: 읽기 — 인덱스 탐색 + 데이터 페이지, 2.2 TB 작업집합은 어떤 인스턴스의 버퍼 캐시에도 없으므로 upsert당
  1~3 I/O → **1~3×10¹⁰**. 쓰기 — 완전히 묶이면 upsert당 ~300 B → 0.7×10⁹, 안 묶이면 upsert+delete 각 1단위 → 2×10¹⁰. 합 **1.1~5×10¹⁰ I/O**
  × $0.24/백만 = **$2,600~12,000/refresh**.
- **월 횟수**: `[recommend] cache_expire` 기본 72h → 유저당 월 10회가 **하한**. `checkRecommendCacheOutOfDate` 5단계에서 마지막 refresh 뒤
  활동한 유저는 worker가 돌 때마다 다시 계산되므로 활성 유저는 그보다 잦다. 월 **$26,000~120,000** — 인스턴스 비용의 5~25배.
- **결론**: DocumentDB는 **I/O-Optimized 스토리지(I/O 무료, 스토리지 $0.36/GB, 인스턴스 +10%)로만** 성립한다. 표의 금액은 그 전제다.
  DocumentDB 5.0의 문서 압축(LZ4, 기본 꺼짐, 임계값 기본 2,032 B·최소 128 B)은 182 B 문서에 켤 수는 있지만 UUID 위주 필드라 이득을
  기대하지 않았고 산정에 넣지 않았다. **읽기 I/O 1~3의 폭은 실행으로만 좁혀진다**(S9와 같은 조건).

## 5. data store 후보별

| | 판정 |
|---|---|
| **Aurora PostgreSQL / MySQL** | `판단` **여기가 맞는다.** 학습이 feedback을 전량 스캔하고, 20억 행 순차 스캔은 관계형이 가장 낫다 |
| **DocumentDB** | 동작하지만 대량 스캔이 약하다 |
| **ElastiCache** | 실격 — 20억 행을 RAM에 두지 않는다 |

## 6. 어디에 둘 것인가 — 자체 운영 · 기존 managed 공유 · 전용 managed

세 선택지가 있고 §4·§5는 마지막 하나만 값을 매겼다. 6-1~6-5가 자체 운영을, 6-6이 공유를 다룬다.

`판단` **이 질문의 근거는 `gorse.md` §8-1이 이미 준다** — *"Gorse DB를 product source of truth로 만들지 않는다.
projection worker를 다시 실행해 재구축할 수 있어야 한다."* 두 저장소 모두 **파생물**이므로 내구성
요구가 원래 약하고, 같은 문서 §8-3은 장애 시 동작까지 정해두었다 — *"Gorse timeout/unavailable → 현재
topic/RRF ordering으로 계속, personalization absent 계측."* **전손이 데이터 사고가 아니라 품질
저하 사건이다.** 자체 운영을 검토할 자격이 여기서 나온다.

### 6-1 managed 프리미엄은 정확히 2배다

같은 노드를 EC2로 사는 값과 ElastiCache로 사는 값을 비교한다(도쿄).

| | 메모리 | 시간당 | 사용 가능 GB당 월 |
|---|---|---|---|
| EC2 `r6g.xlarge` | 32 GiB | $0.2432 | **$6.75** |
| ElastiCache `cache.r6g.xlarge` | 26.32 GiB (18% 예약) | $0.493 | **$13.67** |

★ **ElastiCache = EC2의 2.03배.** (EC2 쪽도 Redis fork·단편화 여유로 같은 26.32 GB만 쓴다고 두고
계산했다. 서울도 비율은 같다.)

`문서` EBS `gp3`: 도쿄 **$0.096/GB·월**, 서울 **$0.0912/GB·월** (3,000 초과 IOPS는 각각 $0.006 /
$0.0057). **서울이 5% 싼 유일한 항목**이고, 나머지는 전부 도쿄와 같거나 0.4% 차이다.

### 6-2 자체 운영 시 비용 (도쿄, 1.1 TB 기준)

| 구성 | 월 비용 `판단` | 비고 |
|---|---|---|
| **OSS Redis/Valkey on EC2 (all-RAM)** | `r6g.8xlarge`(256 GiB, 사용 200) × 6 ≈ **$8,500** | 스팟이면 ~**$2,600** |
| **MongoDB/PostgreSQL on EC2 + gp3 (디스크 상주)** | 인스턴스 `m6g.2xlarge` × 3 = $867 + gp3 560 GB = $54 ≈ **$920** | |
| (참고) managed ElastiCache Redis | $15,400 | §4 |
| (참고) managed r6gd 티어링 | $5,900 | §4 |
| (참고) managed DocumentDB (I/O-Optimized 필수) | $3,400~6,100 | §4 |

data store(feedback 20억 행, 500 GB)를 자체 운영하면 `r6g.4xlarge` × 2 + gp3 ≈ **$1,470**,
Aurora는 $3,000~5,000이다.

★ **디스크 상주 자체 운영이 managed all-RAM의 1/15이다.** 두 배수가 곱해진 결과다 — RAM→디스크(§4가
이미 보인 것)와 managed→자체(6-1의 2.03배).

★ **그러나 OSS에는 데이터 티어링이 없다.** r6gd의 NVMe 계층은 ElastiCache 전용 기능이고 Valkey OSS도
갖고 있지 않다. 즉 자체 운영은 **전량 RAM**과만 비교되며, **managed 티어링($5,900)이 자체 운영
온디맨드 RAM($8,500)보다 싸다.** 스팟을 써야만 자체 운영이 앞선다.

### 6-3 백업의 가치는 두 저장소에 비대칭이다

`판단` 볼륨 주기 백업은 **data store에는 값이 있고 cache store에는 거의 없다.**

- **cache store**: 복원해도 `cache_expire`만큼 낡아 있고, 어차피 재계산이 정답에 가깝다. 백업이
  아니라 **재계산 시간(§7)이 곧 RTO**다.
- **data store**: feedback 20억 행도 원리상 우리 DynamoDB에서 재프로젝션할 수 있지만 시간이 든다. 여기서는
  백업이 재구축 시간을 줄여 준다.

★ **따라서 자체 운영의 위험은 RPO가 아니라 RTO다.** managed는 손실을 불가능하게 만들지 않고 드물게
만든다. 물어야 할 것은 "얼마나 자주 잃는가"가 아니라 **"수 시간의 품질 저하 창(6-5의 재계산 열)을 견디는가"**이고,
`gorse.md` §8-3의 폴백이 실제로 구현되어 있다면 견딜 수 있다. 구현 전이라면 이 논의 전체가 이르다.

### 6-4 자체 운영이 실제로 청구하는 것

`판단` 절감은 실재하고, 노동도 실재한다. 이 조직의 맥락에서 특히 그렇다 — **어느 repo에도 CI/CD가
없고 배포는 손으로 `deploy.sh`를 돌린다.** 샤딩된 Redis 클러스터나 WAL 아카이빙 + **리허설된** PITR을
가진 PostgreSQL을 k8s에서 운영하는 것은 상시 부담이다: 오퍼레이터 업그레이드, 페일오버 시험,
리샤딩, 디스크 풀, OOMKill.

★ **EBS는 AZ에 묶인다.** PVC를 가진 파드는 같은 AZ로만 재스케줄된다. 다중 AZ 이중화는 EBS가 아니라
애플리케이션 계층 복제(Redis 클러스터 replica, PostgreSQL 스트리밍 복제)로 만들어야 하고, 이것이
managed와의 차이 중 k8s 고유의 항목이다.

★★ **그리고 이것이 결론이다. 자체 운영은 1억 규모에서만 값을 한다.** 월 $14,000은 대략 엔지니어
한 명이므로, 자체 운영이 그보다 적은 주의를 쓰면 이긴다. 그런데 §8의 단계표가 보이듯 **1차·2차(20만·100만)에서
managed는 월 $150~360이고 1천만에서도 $1,200~1,500이다.** 거기서 자체 운영이 아끼는 것은 월 $100~1,000 남짓이고,
그 돈으로 상시 운영 부담을 사는 것은 어떤 계산으로도 성립하지 않는다.

`판단` **정리**: 1억 전원 전제에서는 자체 운영이 자릿수로 이기지만, 그것은 마지막 단계의 천장이고 §8은 거기까지
단계로 간다 — 마지막 단계에서만 성립하는 최적화다. 다만 **디스크 상주(§4의 DocumentDB, 6-2의 MongoDB/PostgreSQL)가
전량 RAM보다 한 자릿수 싸다**는 사실은 규모와 무관하게 남으며, 그쪽이 먼저 검토할 축이다.

⚠ **위 문단은 운영 부담을 상수로 놓았다.** 그 가정은 작은 쪽 끝에서 깨지고, 거기서는 결론이
뒤집힌다 — 6-5가 그 경우를 다룬다.

### 6-5 작게 시작해 managed로 넘어간다면

`판단` 6-4는 "우리가 만들 규모에서 자체 운영이 아끼는 돈은 운영 부담을 살 만큼 크지 않다"로 끝났다.
그 문장은 **운영 부담을 상수로 놓았을 때만** 맞는다. 실제로는 절감액과 운영 부담이 **함께** 커지고,
작은 쪽 끝에서는 **둘 다 0에 가깝다.**

`문서` 소규모 ElastiCache 노드 단가(도쿄, Redis / Valkey는 20% 저렴):

| 노드 | 메모리 | 시간당 | 월 |
|---|---|---|---|
| `cache.t4g.small` | 1.37 GiB | $0.049 | $36 |
| `cache.t4g.medium` | 3.09 GiB | $0.098 | $72 |
| `cache.m6g.large` | 6.38 GiB | $0.191 | $139 |
| `cache.r6g.large` | 13.07 GiB | $0.247 | $180 |
| `cache.r6gd.xlarge` | 26.32 GiB | $0.937 | $684 ← **티어링 최소 크기** |

★ **데이터 티어링에는 하한이 있다.** r6gd의 가장 작은 노드가 26.32 GiB다. 캐시가 그보다 작으면
6-2에서 가장 싼 managed 안은 **선택지 자체가 아니고**, 비교 대상은 평범한 노드다.

#### 규모별 (도쿄, replica 포함, cache store만)

| `U_active` | 캐시 크기 (surface 2) | 자체 운영 | managed | 절감 | 운영 형태 | surface 1 재계산(`I_eligible` → item ×1.88, 첫 사이클, `GOR-X3`) |
|---|---|---|---|---|---|---|
| 10만 | 0.55 GB | **~$0** (기존 노드 여유) | $72 | $72 | 파드 하나 | 5만 → item 9.4만 → **~3분**, RAM 1.2 GB |
| 100만 | 5.5 GB | ~$0~180 | $279 | ~$100~280 | 파드 하나 | 50만 → item 94만 → **~30분**, RAM 8.2 GB |
| 1,000만 | 110 GB | ~$740 | $1,504 | ~$760 | 파드 여럿·복제 | 500만 → item 940만 → **3~9시간**, RAM 78 GB — **한 박스를 넘는다** |
| 1억(전원) | 1.1 TB | $8,500 | $15,400 | $6,900 | 샤딩·리샤딩 | 1억 → **Gorse 밖**(`D22`가 그 전에 뒤집는다) |

`판단` **비율은 어디서나 2배로 일정하지만**(6-1) **절대액과 운영 형태가 함께 움직인다.** 왼쪽 끝에서
자체 운영은 기존 Karpenter 노드의 여유에 파드 하나를 얹는 것이고, 클러스터링도 샤딩도 오퍼레이터도
필요 없다. 6-4가 경고한 부담은 오른쪽 두 행의 이야기다.

재계산 열은 **surface 1**(tags item-to-item)의 첫 사이클 = Push + 전 item 저장(`GOR-X3`: 저장 포함 1~3 ms/item, store 의존, Redis 미측정 — `S10`)이다. **surface 2**(유저별 CF 추천)의 재계산 시간은 이 문서가 재지 않았다 — `recsys_opensource/README.md` §11의 것이다.

★ **그리고 왼쪽 끝에서는 스팟 위에 둬도 된다.** `I_eligible` 5만이면 전손 복구가 몇 분이다. §7의 공식이
그대로 반대 방향으로 작동한다 — **재계산이 싸다는 것이 자체 운영을 안전하게 만드는 성질**이고, 그
성질은 규모와 함께 사라진다.

#### 이전 비용이 이례적으로 싸다

★★ 보통 "작게 자체 운영하다 나중에 managed로"가 실패하는 이유는 **데이터 중력**이다. 여기에는
그것이 없다. `gorse.md` §8-1이 Gorse DB를 source of truth로 두지 말라고 못박았고, 그래서 이전은
덤프·복원도 이중 쓰기도 정합성 창도 아니다.

```text
managed 인스턴스를 띄운다 → Gorse 설정을 그쪽으로 돌린다
→ projection worker를 다시 돌린다 → 전면 재계산 한 번을 기다린다
```

**이전 비용 = 재계산 한 번**이고, 그 창은 `gorse.md` §8-3의 폴백이 덮는다. 즉 **미루는 선택지를
들고 있는 값이 거의 0이다.**

#### 출구를 지키는 두 규칙

`판단` 그 값이 0인 것은 조건부이고, 조건은 둘 다 지금 정할 수 있다.

1. **Gorse 저장소에 원본을 절대 넣지 않는다.** `gorse.md` §8-1이 이미 요구하지만, 이제 두 번째
   이유가 생긴다 — 원본이 하나라도 들어가는 순간 데이터 중력이 생기고 위의 이전 경로가 사라진다.
2. **엔진은 managed 대응물이 *같은 것*인 쪽으로 고른다.** 자체 PostgreSQL → Aurora PostgreSQL은
   그대로 옮겨진다. 자체 Redis/Valkey → ElastiCache도 그렇다. **자체 MongoDB → DocumentDB는
   아니다** — DocumentDB는 MongoDB *호환*이지 MongoDB가 아니고, API·버전 간극이 있다.

   ★ **이것이 6-2의 최저가 안을 바꾼다.** 디스크 상주 cache store에서 MongoDB가 제일 싸 보였지만,
   "나중에 managed로"를 전제하면 **PostgreSQL이 더 싸다** — 월 몇십 달러 차이를 출구 비용으로 갚기
   때문이다.

#### 넘어가는 시점은 금액이 아니다

`판단` 트리거는 절감액이 아니라 **재계산 시간이 "잃어도 된다"를 지탱하지 못하게 되는 지점**이다.

```text
I_eligible   surface 1 item   재계산(첫 사이클)   master RAM   자체 운영 판정
     5만          9.4만          ~3분             1.2 GB     스팟 위 파드 하나로 충분
    50만           94만         ~30분             8.2 GB     자체 운영 유지, 스팟은 그만
   500만          940만        3~9시간            78 GB     ← 한 박스(64 GB)를 넘는다. 여기 오기 전에 D22의
                                                             뒤집는 조건(RSS·사이클 50%)이 먼저 발동한다
```

`판단` 즉 surface 1에서는 "잃어도 된다"가 깨지는 지점보다 **`D22`의 신호가 먼저 온다** — 자체 운영을 접는 판단과 Gorse를 떠나는
판단이 같은 계측 위에 있다. surface 2의 트리거는 여전히 재계산 시간이고, 그 값은 미측정이다(위 표 아래 주석).

`판단` 금액으로 트리거를 잡으면 늦는다 — 돈이 아파지는 시점(오른쪽 두 행)에는 이미 샤딩과 리샤딩을
운영하고 있다. **재계산 시간이 먼저 신호를 준다.**

### 6-6 이미 있는 managed에 얹는다면 — `iac` 실측

`사실` 새로 사올 필요가 없다. 도쿄 prod에 이미 다음이 있다(`iac/terraform/env/prod/main.tf`).

| 이름 | 사양 | 크기 | 월 (인스턴스) |
|---|---|---|---|
| `bourbon-main-mysql-tokyo-prod` | MySQL 8.4.10, `db.r8g.large`, **Multi-AZ**, gp3 | 2 vCPU / 16 GiB | $419 |
| `bourbon-redis-tokyo-prod` | **Valkey** 9.1, `cache.m7g.large` × 2, Multi-AZ | 6.38 GiB | $236 |
| `pensieve-pg-tokyo-prod` | PostgreSQL 18.4, `db.t4g.small`, Multi-AZ | 2 GiB | — |
| `bourbon-rabbitmq-tokyo-prod` | Amazon MQ | — | — |

`문서` RDS gp3 스토리지(도쿄): Single-AZ **$0.138/GB·월**, **Multi-AZ $0.276/GB·월**.
DocumentDB 계열은 **아직 하나도 없다** — 도입하면 새 제품군이 늘어난다.

★ **Gorse의 두 저장소가 모두 여기에 얹힌다.** Gorse는 MySQL을 data store로, Valkey/Redis를 cache
store로 지원한다. deferq가 이미 Valkey를 DB 인덱스로 나눠 쓰는 것과 같은 방식이다.

#### 돈으로는 공유가 이긴다

feedback `N` GB를 얹을 때(도쿄):

```text
공유   (기존 Multi-AZ MySQL)   0.276 × N
분리   (별도 db.t4g.small Single-AZ)   36.5 + 0.138 × N
                                    → 교차점 N ≈ 264 GB (feedback 약 12억 행)
```

`판단` 즉 **현실적인 규모 전부에서 공유가 싸다.** feedback 5 GB면 공유 월 $1.4, 분리 월 $37이다.
**그러므로 분리의 근거는 비용일 수 없다.** 다른 데 있어야 하고, 있다.

#### MySQL을 함께 쓰면 다른 서비스에 무엇이 가는가

`iac` 주석이 이 인스턴스의 여유를 직접 계산해 두었다 — *"16 GB total − ~75% innodb_buffer_pool −
OS overhead ≈ ~3 GB free"*. **버퍼 풀 약 12 GiB, vCPU 2개**가 공유 자원이다.

| 경로 | 판정 |
|---|---|
| **버퍼 풀 오염** | `판단` **생각보다 낫다.** InnoDB의 mid-point insertion(`innodb_old_blocks_pct` 기본 37)이 전면 스캔을 old sublist에 가둬 hot 페이지 축출을 막는다. Gorse의 학습 스캔은 이 방어를 받는다 |
| **I/O 대역** | `판단` **방어가 없다.** gp3 기본 3,000 IOPS / 125 MiB/s. 200 GB 스캔이면 볼륨 처리량을 ~27분 포화시키고, 같은 볼륨의 bourbon-api가 그대로 느낀다 |
| **CPU** | `판단` **방어가 없다.** `db.r8g.large`는 **vCPU 2개**다. 대량 스캔과 OLTP가 2코어를 나눈다 |
| **백업·복원** | ★ **가장 조용하고 가장 아프다.** 아래 |
| **Multi-AZ 배수** | 얹은 스토리지는 $0.276/GB — **필요 없는 이중화를 파생 데이터가 상속한다** |

★ **백업이 문제인 이유는 §6-3의 정확한 반대편이다.** 이 인스턴스는 `backup_retention_period = 7`,
`deletion_protection = true`, `skip_final_snapshot = false`로 귀하게 다뤄진다. 거기에 **백업할 필요가
없는 파생 데이터**(§6-3) 수백 GB를 얹으면 백업 창과 PITR 복원 시간이 함께 길어진다. **원본을 가진
인스턴스의 RTO를 파생물이 갉아먹는다.**

★★ **그래서 공유의 진짜 비용은 돈이 아니라 실패 도메인이다.** `gorse.md` §8-3이 정한 대로 Gorse는
없어도 제품이 degrade만 한다. 그 **degrade 가능한 것을 degrade 불가능한 인스턴스 안에 넣으면**,
Gorse의 배치 워크로드가 bourbon-api의 장애 경로가 된다. 성질이 정반대인 둘을 한 실패 도메인에 묶는
셈이고, 이것이 이 절 전체의 결론이다.

#### Valkey를 함께 쓰면

- 용량: `cache.m7g.large` × 2 = **6.38 GiB**. §6-5 표로 **`U_active` 10만이면 0.55 GB로 들어가고,
  100만이면 5.5 GB로 인스턴스를 채운다.** 여유는 대략 100만 사용자에서 끝난다 — 그리고 surface 1 이웃 캐시(§8-1, item당
  ~80건)가 같은 노드에 더해지면 그보다 훨씬 일찍 끝난다. dev는 데이터가 작아 문제없고, prod는 어차피 분리한다.
- `판단` **단일 스레드 경합.** Valkey는 샤드당 명령 실행이 단일 스레드다. Gorse의 전면 refresh는
  수십만 키 쓰기 버스트이고, 그동안 같은 노드의 다른 명령이 밀린다 — deferq의 폴링을 포함해서.
- ⚠ `열린 항목` **축출 정책이 deferq를 깨뜨릴 수 있다.** 모듈이 parameter group을 지정하지 않아
  기본값을 쓴다. ElastiCache 기본은 `volatile-lru`로 알려져 있고(**확인 필요**) TTL 없는 키는 축출
  대상이 아니다. deferq의 스케줄 키도 Gorse 캐시도 TTL이 없을 것이므로, 메모리가 차면 축출이 아니라
  **쓰기 실패**가 난다. 그리고 **deferq에는 재시도도 DLQ도 없다** — 실패한 스케줄 쓰기는 그 refresh의
  영구 유실이다. 얹기 전에 `maxmemory-policy`와 현재 사용률을 반드시 본다.

#### 권고

`판단`

- **dev는 공유한다.** SLA가 없고, S1·S6을 실측하는 가장 값싼 길이다. 다만 dev MySQL은
  `db.t4g.small`(2 GiB)이라 feedback이 조금만 쌓여도 버퍼 풀을 넘는다 — **기능 확인용이지 성능
  측정용이 아니다**는 뜻이기도 하다.
- **prod는 분리한다.** 돈 때문이 아니라(공유가 더 싸다) 실패 도메인 때문이다. 별도 `db.t4g.small` MySQL
  Single-AZ 월 **$36.5** + 별도 Valkey — **노드 크기는 §8-2가 단계별로 정한다**(1차 `cache.m6g.large`, 합쳐 월 ~$150).
  이 절의 첫 안이었던 `cache.t4g.small` × 2($57, 합 $94)는 surface 1 이웃 캐시(§8-1)를 모르던 값이라 1차부터 모자란다.
  **월 $150 남짓으로 blast radius를 산다.**
- 그리고 이 분리는 6-5의 출구 규칙과도 맞는다 — **별도 인스턴스여야 통째로 버리거나 옮길 수 있다.**
  공유하면 파생 데이터가 원본 인스턴스에 섞이고, 그 순간 6-5의 "이전 비용 = 재계산 한 번"이 사라진다.

## 7. 그러나 병목은 저장소가 아니다

`gorse.md` §12-5 `GOR-X3`의 실측(5×10⁵까지, 8 jobs)을 위로 늘린다. `D24` 뒤 item = agent × 최상위 topic(합성 배수 1.88).

```text
정상 사이클 ≈ 0.4 ms × item        `실측` Push + item당 캐시 확인 3회 읽기. 증분 갱신 없음
첫 사이클   ≈ 1~3 ms × item        `실측` 전 item 저장이 지배 — store 의존(MongoDB 1.1, sqlite 1.8~3.3, Redis 미측정)
master RAM  ≈ 0.42 GB + 8.3 KB × item

agent 500만 → item 940만   정상 1시간 · 첫 3~9시간 · RAM 78 GB   ← 64 GB 박스를 넘는다
agent 1억   → item 1.9억   정상 21시간 · RAM 1.6 TB              ← 한 프로세스에 없다
```

`판단` **어떤 저장소를 골라도 이것은 고쳐지지 않는다.** master 한 프로세스가 매 사이클 전체 HNSW를 다시 짓고(`gorse.md`
§12-3), 반영 지연 = `max(cache_expire, 사이클 길이)`다. 캐시를 담을 곳이 부족한 것이 아니라 **캐시를 채우는 프로세스가 하나**다.
그래서 surface 1은 어느 단계에서 Gorse를 떠나고(`D22` — 시점은 RSS·사이클 계측), 그 전까지는 §8의 단계표대로 박스만 키운다.

surface 2(유저별 CF 추천)는 worker가 유저 단위로 나눠 계산하므로 같은 벽이 아니지만, **전원을 넣으면 재계산이 신선도 창을 넘는다**는
`README.md` §11의 지적은 그대로다(같은 질문이 `SURV-R3`으로 등록돼 있다). 완화는 저장소가 아니라 **담을 인구**(활성 창)이고, §8이
1천만 단계에서 그것을 필수로 둔다.

## 8. 단계별 구성 — 20만 → 100만 → 1천만 → 1억 (`D26`, 오너 2026-09-07)

`오너` **`D26`**: 목표 유저 풀은 **단계적**이다: **1차 20만, 이어 100만, 1천만, 최종 1억까지 대응 가능해야 한다.** 유저가 공개 보유자인
비율, 활성 비율, agent당 최상위 topic 수(item 배수)는 **Closed·Open Beta 뒤에 실측**한다 — 그래서 `N*`도 그때 정한다(`decisions.md`
D22·C11). 그 전까지 이 절은 **상한**으로 계획한다: 유저 수 = `I_eligible` = `U_active`, item 배수 1.88(`GOR-X6` 합성값).
실값이 나오면 표의 왼쪽 열만 바뀌고 오른쪽(구성·전환)은 그대로다.

★ **단계 이름은 계획의 단위이고, 단계 경계는 계측이 정한다.** 아래 표의 "20만"은 노드를 미리 골라 두는 기준이지 전환 시점이
아니다. 전환은 8-3의 신호로만 한다.

### 8-1 단계마다 커지는 것

| 단계 (유저) | surface 1 item (×1.88) | master RAM (`X3`) | 정상 사이클 (8 jobs) | surface 1 캐시 in Valkey `판단` · `S10` | surface 2 캐시 (5.5 KB/유저, §2) | feedback 행 (20/유저) |
|---|---|---|---|---|---|---|
| **20만** | 38만 | 3.5 GB | 2.5분 | 4~6 GB — id 64 B 미만이면 1.5~2.5 GB | 1.1 GB | 400만 |
| **100만** | 190만 | 16 GB | 13분 | 19~30 GB — 압축 id면 8~12 GB | 5.5 GB | 2천만 |
| **1천만** | 1,900만 | **156 GB — 단일 박스 불가** | 2시간 | **Gorse 밖**(`D22` 발동 뒤) | 55 GB → replica 포함 110 GB | 2억 |
| **1억** | — | — | — | — | 550 GB → 1.1 TB (§2) | 20억 (§5) |

surface 1 캐시 열의 근거: `GOR-X3`에서 item당 ~80건이 **첫 사이클에 한 번** 쓰이고, 우리는 그중 쿼리 item 수천 개의 목록만 읽는다.
나머지는 Gorse가 만들고 아무도 읽지 않는 메모리다. 건당 크기는 Redis에서 **미측정**이라 `판단`으로 적었다 — `D24`의 id
`agent_id#top_topic_id`가 UUID 둘이면 약 73 B로 Redis listpack 임계(64 B)를 넘어 skiplist 인코딩이 되고, 그것이 건당 오버헤드를
2~3배로 키운다. **id 1바이트가 80 × N배로 곱해진다.** `cache_size`를 줄이는 것은 답이 아니다 — 전역이라 쿼리 item의 100-cut도
같이 줄어든다(`gorse.md` §12-4 행 4). id 형식은 `S12`.

### 8-2 단계별 구성 (prod, 도쿄) `판단`

dev는 모든 단계에서 기존 MySQL·Valkey를 공유한다(6-6). prod는 분리하고, **엔진은 바꾸지 않고 노드만 바꾼다.** Gorse는 surface별
배포 둘(`D22`의 전용 인스턴스 + surface 2)이 **같은 MySQL의 다른 스키마, 같은 Valkey의 다른 DB 인덱스**를 쓴다.

| 단계 | data store (MySQL) | cache store (Valkey) | Gorse master 파드 | 월 (인스턴스) | 비고 |
|---|---|---|---|---|---|
| **20만** | `db.t4g.small` Single-AZ, $36.5 | `cache.m6g.large` 6.4 GiB, ~$111 | surface 1 4 GB · surface 2 소형 | **~$150** | `cache.t4g.small`(1.37 GiB)은 surface 1 캐시 때문에 1차부터 모자란다 — 6-6의 $94 안을 이것으로 바꾼다 |
| **100만** | `t4g.small`~`medium`, $36.5~73 | `cache.r6g.xlarge` 26 GiB, ~$288 | surface 1 16 GB | **~$325~360** | 코드 변경 0 — 노드 교체 + 재계산 한 번(6-5) |
| **전환** | — | — | surface 1 파드 제거 | — | **`D22` 발동**: surface 1 후보를 우리 인덱스로(`gorse.md` §12-4의 5). 신호는 8-3 |
| **1천만** | `db.r6g.large`급 또는 Aurora 검토 (feedback 2억 행) | `cache.r6gd` 티어링, 110 GB, ~$1,200(Valkey) | surface 2만 | **~$1,400~1,700** | **활성 창 projection 필수** — 전원 재계산이 신선도 창을 넘는다(§7). r6gd는 도쿄만(§3-1, `S5`) |
| **1억** | Aurora $3,000~5,000 (§6-2) | 티어링 1.1 TB $5,900 (§4) 또는 활성 창으로 1천만 규모 유지 | surface 2만 | §4 | 병목은 저장소가 아니라 인구(§7). §2–§5의 상한 비교가 여기다 |

★ **1억에서 $15,400이던 것이 1천만에서 $1,200~1,500이 된다.** `README.md` §11이 CF 모델 메모리에 대해 한 말이 저장소에도 그대로
적용된다 — *"'가입자 1억'과 '모델 row 1억'은 같은 결정이 아니다."* 1천만 이상에서 답은 저장소가 아니라 **담을 인구**다.

### 8-3 전환은 무엇이 정하는가

세 종류의 전환이 있고 신호가 다 다르다.

1. **노드 교체**(20만 → 100만, 1천만 안에서의 증설): 신호는 **cache store 메모리 사용률**과 **master RSS**(파드 요청 대비). 비용은
   재계산 한 번이다(6-5 "이전 비용이 이례적으로 싸다") — 파생물이므로 덤프·복원이 없다.
2. **surface 1이 Gorse를 떠나는 것**(`D22`): `N*`가 없는 동안 **master RSS ≥ 박스의 50% ∨ 정상 사이클 ≥ 가시성 목표(C7)의 50%**.
   `N*`가 정해지면 `I_eligible × item 배수 ≥ 0.5·N*`로 읽는다 — 같은 조건의 두 표기다(`decisions.md` D22 주석). 상한 가정에서는
   100만 단계 안에서 온다. 실값(베타 뒤)이 나오면 유저 수로 다시 말할 수 있다.
3. **surface 2가 전원에서 활성 창으로**(1천만): 신호는 **유저 추천 재계산 시간이 `cache_expire`를 넘는가**(§7·`SURV-R3`). 이 값은
   이 문서가 재지 않았다 — `README.md` §11의 부하 시험(full / active-window / on-demand)이 답한다.

### 8-4 지금 해둬야 나중에 설정 변경만으로 넘어가는 것

1. **surface 1 item id를 64 B 아래로**(`S12`) — 1차에서 노드 한 등급, 2차에서 두 등급 차이다. store는 파생물이라 나중에 바꿀 수는
   있지만 S3의 id 역매핑(`D24`)이 걸리므로 먼저 정한다. **결정은 `decisions.md`에 적는다(D24 보완).**
2. **배포·스키마·DB 인덱스를 surface별로 분리** — 2번 전환에서 surface 1만 떼어낼 수 있어야 한다.
3. **전환 신호를 첫날부터 계측** — `I_eligible`(주간, `gorse.md` X2(b)), item 수, master RSS, 정상 사이클 길이, cache store 메모리,
   `U_active`. 8-3의 세 신호가 전부 이 여섯 숫자다.
4. **Gorse store에 원본을 넣지 않는다**(6-5의 규칙 1) — 매 단계의 이전 비용이 "재계산 한 번"으로 남는 조건.
5. **엔진은 managed 대응물이 같은 것**(6-5의 규칙 2) — MySQL·Valkey는 이미 그렇다. DocumentDB·MongoDB를 끼우지 않는다.

### 8-5 이 계획의 빈 실측

| | 무엇을 정하나 | 항목 |
|---|---|---|
| Redis/Valkey에서 item당 캐시 크기와 정상 사이클의 확인 3회 비용 | 1차·2차 cache store 노드 크기 | `S10` |
| MySQL data store가 5×10⁵ item에서 REST를 막지 않는가 | 1차·2차 공통(sqlite는 막았다 — `GOR-X3`) | `S11` |
| 공유 Valkey의 `maxmemory-policy`·사용률 | dev 공유의 안전 | `S8` |
| surface 2 유저 추천 재계산 시간 | 3번 전환 시점 | `SURV-R3`·`README.md` §11 |

## 9. 열린 항목

**ID 접두사는 `STO-`다**(`decisions.md` §5).

| # | 항목 | 성격 | 상태 |
|---|---|---|---|
| **S1** | `U_active`·`I_eligible` 목표값 | 제품·측정 | **오너 입력 → `D26`(2026-09-07)**: 유저 풀 **20만 → 100만 → 1천만, 최종 1억 대응**(§8). 공개 보유·활성 비율과 item 배수는 **Closed·Open Beta 뒤 실측** — 그때까지 상한(유저 수 = `I_eligible` = `U_active`, 배수 1.88)으로 계획한다. `SURV-R8`과 같은 질문 |
| S2 | Gorse가 SQL/document backend에서 cache store를 **실제로 어떤 스키마로** 쓰는가 | 실측 | **MongoDB는 확인**(S4·S9 — `documents` 컬렉션, 이웃 1건 = 문서 1개). **SQL/Aurora는 미확인** — §4의 Aurora 판정이 여기에 걸린다 |
| S3 | 리전 단가 | 확인 | **닫힘(§3).** 도쿄·서울 동일 수준, us-east-1 대비 +20% |
| S4 | `gorse.md` §8-2의 neighbor·fallback 캐시가 §2 산정에 더하는 양 | 측정 | **일부 실측(`GOR-X3`, 2026-09-04)**: surface 1 인스턴스의 item 이웃 캐시는 **item당 ~80건**(sqlite ~210 B/건, 5×10⁵에서 7.8 GB). 10⁸ item이면 ~8×10⁹건 — Redis 단가는 미측정. **MongoDB 7 실측**: 논리 182 B/건, 디스크는 WiredTiger 압축으로 ~33 B/건(이 압축률은 DocumentDB에 적용되지 않는다 — 엔진이 다르다). Gorse의 MongoDB 캐시는 **이웃 1건 = 문서 1개**라 §4 DocumentDB 행의 옛 "유저당 문서 1개 + 배열 100개" 가정과 모양이 달랐고, **§4는 2026-09-04 이 모양으로 재산정했다**(스토리지 4배, Standard I/O는 인스턴스의 5~25배 → I/O-Optimized 필수). master RAM은 별도로 **≈ 8.3 KB/item** |
| S5 | 서울 이전 시 r6gd 부재를 무엇으로 대체하는가 | 설계 | **조건부.** 도쿄를 쓰는 동안은 열리지 않는다(§3-1) |
| S6 | 디스크 상주 cache store가 견디는 QPS | 측정 | **§4·§6-2의 최저가 안이 전부 여기 걸린다.** 인덱스는 RAM에 들어가지만 working set을 벗어난 읽기는 gp3 IOPS를 친다 |
| S7 | Gorse 불능 폴백(`candidates_fallback` — topic-api 보유자 랭킹, `D20`)이 실제로 구현되어 있는가 | 확인 | **자체 운영 검토의 전제**(§6-3) |
| S8 | 공용 Valkey의 `maxmemory-policy`와 현재 사용률 | 확인 | **얹기 전 필수**(§6-6). TTL 없는 키가 차면 축출이 아니라 쓰기 실패이고, deferq에는 재시도가 없다 |
| **S9** | **DocumentDB가 Gorse v0.5.11의 MongoDB 백엔드 연산을 지원하는가** | 문서 대조 (실행 아님) | **2026-09-04 대조 완료 — 아래 표.** cache store는 **5.0에서 대시보드 시계열 하나만 깨지고**(`$top`, 8.0.1+에서만 지원) 추천 경로는 전부 지원. data store는 **5.0 이상 필수**(`$text`·text index·`$meta`가 3.6/4.0에 없음). Elastic cluster는 data store 불가(text 계열), cache store는 5.0과 같은 조건(대시보드 시계열만 깨짐). **실제 클러스터에서 한 번 돌려 보기 전까지는 문서상 판정이다.** 로컬 `mongo:7`로는 동작·성능 확인(`gorse.md` §12-5 X3 store 변인): 저장 1.1 ms/item(sqlite의 1.6×), 정상 사이클 동일. 기동 시 빈 `BulkWrite` 오류 로그 1건(무해) |
| **S10** | Redis/Valkey cache store에서 surface 1 이웃 캐시의 **item당 크기**와 정상 사이클의 확인 3회 읽기 비용 | 실측 (`GOR-X3` store 변인의 Redis 행, 미실행) | **§8 1차·2차 노드 크기가 여기 걸린다.** 지금 값은 `판단`(10~16 KB/item, id 64 B 미만이면 4~6 KB). 하네스는 `gorse.md` §12-5 X3에 인라인 |
| **S11** | MySQL data store가 5×10⁵ item에서 REST를 막지 않는가 | 실측 | sqlite는 분 단위로 막았다(`GOR-X3`). MySQL은 다를 것으로 보지만 미측정 — §8 1차·2차 공통 전제 |
| **S12** | surface 1 item id를 **64 B 미만**으로 하는가 (`D24`의 `agent_id#top_topic_id`는 UUID 둘이면 ~73 B) | **결정** (`decisions.md`, D24 보완) | id 1바이트 = 80 × N 바이트. Redis listpack 임계를 넘으면 건당 2~3배(§8-1). S3의 id 역매핑에 닿으므로 1차 전에 정한다 |

**S9 상세 — Gorse v0.5.11 `storage/cache/mongodb.go`·`storage/data/mongodb.go`가 쓰는 연산 vs AWS 문서
[Supported MongoDB APIs](https://docs.aws.amazon.com/documentdb/latest/developerguide/mongo-apis.html)·[Text search](https://docs.aws.amazon.com/documentdb/latest/developerguide/text-search.html)** (2026-09-04 열람):

| Gorse가 쓰는 것 | 어디서 | 3.6 | 4.0 | 5.0 | 8.0 | Elastic |
|---|---|---|---|---|---|---|
| `create`·`createIndexes`(compound·unique·sparse) · `find`·`update`(upsert)·`delete` · `BulkWrite` · `count` | cache·data 전부 | ✓ | ✓ | ✓ | ✓ | ✓ |
| `$eq $in $lt $lte $gt $gte $ne $or $all` · `$set $setOnInsert $inc $min $max` | cache·data | ✓ | ✓ | ✓ | ✓ | ✓ |
| `ScanScores` = `Find({})` 전체 커서 | cache GC(매 사이클) | ✓ | ✓ | ✓ | ✓ | ✓ |
| `$match $group $project $sort $multiply $divide` | cache `GetTimeSeriesPoints` | ✓ | ✓ | ✓ | ✓ | ✓ |
| `$floor $toLong $toDate` | 같은 곳 | ✗ | ✓ | ✓ | ✓ | ✓ |
| **`$top`** (누산자, MongoDB 5.2+) | 같은 곳 | ✗ | ✗ | **✗** | ✓ (8.0.1+) | ✗ |
| **text index**(`Comment` 등 `[recommend.search] columns`) · `$text`/`$search` · `$meta: textScore` | data `Reconcile`·`SearchItems` | ✗ | ✗ | ✓ | ✓ | ✗ |

- **`$top`이 깨뜨리는 것은 master 대시보드의 `/api/dashboard/timeseries/{name}` 하나다**(`master/rest.go:776`). 시계열
  *쓰기*(`AddTimeSeriesPoints`, BulkWrite upsert)는 되고, item-to-item·추천·GC는 이 함수를 쓰지 않는다. 5.0에서 그래프가
  비는 것을 감수하면 cache store로는 동작한다. 8.0.1+면 문제 없다.
- **data store를 DocumentDB에 두려면 5.0 이상**이다. 3.6/4.0에서는 text index 생성이 실패하는데, `Reconcile`은 background
  goroutine에서 로그만 남기므로(`master/tasks.go:62`) 기동은 되고 `/api/search`만 안 된다. DocumentDB text index 제약도
  적용된다 — 컬렉션당 하나, **영어만**, 배열 필드 불가(`columns`에 `item.Labels.*`를 넣으면 실패), 대소문자 무시.
- 운영 주의(문서상): TLS 필수라 `FROM scratch` 이미지에 CA 번들을 마운트하고 URI에 `tls=true&tlsCAFile=`를 넣어야 한다.
  retryable writes 지원 여부는 버전별로 확인하고, 안 되면 URI에 `retryWrites=false`.
- **이 표는 실행이 아니다.** §8의 규율("문서에 없는 동작은 실행이 답한다")대로, DocumentDB가 후보로 살아나면 실제 클러스터에
  10⁵ item으로 X3 하네스를 한 번 돌리는 것이 판정이다. 로컬 MongoDB로는 성능만 대리 측정할 수 있고 호환성은 대리가 안 된다.

`판단` **S2는 `README.md` §8의 규율이 그대로 적용되는 자리다** — *"문서에 없는 동작은 문서가 아니라 실행이
답한다."* §4의 Aurora 항목은 sorted set을 행으로 편다는 가정 위에 서 있고, 그 가정 자체가 아직
실행으로 확인되지 않았다.

## 10. 출처와 재현

§3의 모든 숫자는 AWS Price List API(공개, 인증 불필요)에서 나왔다. 리전 코드만 바꾸면 재현된다.

```bash
# ElastiCache 노드 — 엔진·리전별 시간당 단가
curl -s "https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonElastiCache/current/ap-northeast-1/index.json" \
| jq -r '(.terms.OnDemand | to_entries
          | map({(.key): (.value | to_entries[0].value.priceDimensions | to_entries[0].value.pricePerUnit.USD)})
          | add) as $od
         | .products | to_entries[]
         | select(.value.attributes.instanceType == "cache.r6g.xlarge")
         | "\(.value.attributes.instanceType) \(.value.attributes.cacheEngine) \(.value.attributes.memory) $\($od[.key])"'
```

Aurora와 DocumentDB는 같은 형태로 `AmazonRDS` · `AmazonDocDB` 가격표를 읽고 `usagetype`으로 고른다 —
`APN1-Aurora:StorageUsage` · `:StorageIOUsage` · `:IO-OptimizedStorageUsage`, DocumentDB는
`APN1-StorageUsage` · `APN1-StorageIOUsage` · `APN1-IO-OptimizedStorageUsage`.

`실측` r6gd 부재 확인도 같은 파일에서 나온다: 도쿄 가격표에 `r6gd` product entry가 24개, 서울에 0개.

배경 문서:

- [Amazon ElastiCache Pricing](https://aws.amazon.com/elasticache/pricing/)
- [ElastiCache 데이터 티어링](https://aws.amazon.com/blogs/database/scale-your-amazon-elasticache-for-redis-clusters-at-a-lower-cost-with-data-tiering/)
- [Amazon DocumentDB Pricing](https://aws.amazon.com/documentdb/pricing/)
- [Amazon DocumentDB — 컬렉션 수준 문서 압축](https://docs.aws.amazon.com/documentdb/latest/developerguide/doc-compression.html) (§4 재산정에서 압축을 제외한 근거)
- [Amazon Aurora Pricing](https://aws.amazon.com/rds/aurora/pricing/)
