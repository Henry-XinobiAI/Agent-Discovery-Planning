# 후보 라이브러리·엔진 검증 — 계획이 가정한 대로 동작하나 (2026-09-08)

> **역할**: 재설계 §5-1이 A안 후보로 적은 Gorse, `implicit`, LightFM, OpenSearch와 B안의 PostgreSQL 역인덱스·동시 출현 CF를
> **같은 합성 데이터로 실제로 돌려 본 결과**다. 결정은 내리지 않는다 — O8·O11의 근거로 `decisions.md`가 인용한다.
> 재현 스크립트는 `spikes/2026-09-08_library_verification/`.

## 0. 한눈에

| 후보 | 계획의 가정 | 실측 | 판정 |
|---|---|---|---|
| `implicit` 0.7.3 | Python 3.14에서 쓸 수 있다 | cp314 wheel로 설치·임포트·ALS 학습 OK(macOS arm64에서 실행. manylinux x86_64·aarch64 cp314 wheel도 있어 컨테이너 이미지에 컴파일러가 필요 없다). 100k×100k·23만 nnz ALS fit **0.9 s(16 factor) ~ 11 s(64 factor)**, RSS ≤ 300 MB | **쓸 수 있다.** 비용은 무시할 수준 |
| LightFM 1.17 | `implicit`의 대안 | Python 3.14에서 **빌드 실패**(`setup.py`가 `__LIGHTFM_SETUP__` 속성을 설정하지 못함). 2021년 이후 릴리스 없음 | **후보에서 뺀다** |
| OpenSearch 2.19 (타입 ①②) | topic term 인덱스로 커버리지 정렬 가능 | nested + `function_score`로 커버리지 우선 정렬·friends 필터 모두 **위반 0건**. 10만 유저 p50 2.3 ms / p95 3.9 ms. 단 점수 설계에 함정 하나(§2-2), 그리고 zstd 버그(§2-3) | 동작한다. 그러나 같은 일을 PostgreSQL이 더 빠르고 단순하게 한다 |
| PostgreSQL 17 (타입 ①②, B안) | `(topic_id, tier, agent_id, 점수)` 역인덱스 + GROUP BY | 위반 0건. **p50 0.8 ms / p95 2.3 ms**, 36만 row 27 MB | 타입 ①②는 이것으로 충분하다 |
| `implicit` ALS (타입 ③ A안 라이브러리형) | CF 점수를 준다 | 스펙 대화율(유저당 3회)에서는 **인기도 순보다 못하다**(HR@10 0.6 % vs 0.9 %). 군집 신호는 잡는다(같은 군집 비율 0.19 vs 인기도 0.14). 대화율 10회에서 인기도와 동률 | 출시 시점 밀도에서 CF는 보조 feature다. 재설계 §2-3 "인기도 → content → CF" 순서가 맞다 |
| 동시 출현 아이템 이웃 (타입 ③ B안 CF) | 첫 구현 후보(O11) | **코사인 정규화 이웃은 무작위 수준**(HR@10 0.08 %/0.02 %). 정규화 없는 raw 카운트 + 인기도 tie-break는 λ=10에서 인기도와 동률, λ=3에서 ALS의 절반 | O11: 아이템 이웃을 하려면 정규화 없이. 그래도 ALS 16 factor가 더 낫고 더 싸다 |
| Gorse v0.5.11 (타입 ③ A안 서비스형) | MySQL/PostgreSQL data store + Redis cache store(R08 안) | **Redis cache store가 RediSearch(`FT._LIST`)를 요구한다** → ElastiCache/Valkey에서는 못 띄운다. MySQL cache store로는 뜬다. BPR fit 19 s, 그 뒤 **10만 유저 추천 생성 6분 49초**를 끝내자마자 다시 시작. RSS 514 MB. 서빙은 기본 설정에서 CF 대신 `latest` 폴백 — 원인 둘: **기본 `[recommend.ranker]`가 오프라인 캐시를 읽지 않고**, **MySQL multi-valued 인덱스가 `categories = []`인 행을 숨긴다**(§4-3). 둘을 고친 뒤 **서빙 HR@10 0.0006** = `implicit` ALS의 1/9, 인기도의 1/15 | **R08 안에서는 cache store를 MySQL/PostgreSQL로 둬야 하고**, 그러면 상시 재계산 사이클(binlog 없이 1.5분, 있으면 7분)에 cache 1,400만 행이다. 품질도 라이브러리형에 못 미친다. 채택 근거가 약해졌다 |

**합성 데이터 자체의 발견**: 스펙 §2 기본값으로 만든 정답(`affinity × pop`)은 너무 흐리다. 정답을 전부 아는 오라클조차 held-out 대화 상대를 top-10에 넣는 비율이 **1.9 %**다. CF 품질을 recall@10으로 구분하려면 §5-2의 조정이 필요하다.

## 1. 무엇을 어떻게 돌렸나

- **모집단**: `synthetic_population_spec.md` §2 기본값으로 U=100,000. 단순화: 카탈로그는 3,003개 합성 topic id를 54 그룹에 배분(실제 카탈로그 파일 대신), 유저 id는 정수(agent = 소유자 index), 이벤트 시퀀스 없이 최종 상태 + 대화 로그만. 결과: topic row 1,016,411 / 공개된 row(public+friends) 366,211 / discoverable agent 56,276 / 친구 간선 372만(대칭화 뒤 평균 degree 74.5 — 스펙의 median 25는 유저가 "고르는" 수라 대칭화하면 두 배가 된다) / 대화 300,082건(λ=3, 서로 다른 쌍 238,287, 대화 0건 유저 5,000) / λ=10 판은 998,591건.
- **타입 ①②**: 공개된 row를 PostgreSQL 테이블 하나와 OpenSearch nested 인덱스에 같이 넣고, 요청자 군집 선호에서 뽑은 topic 1~3개 쿼리 2,000건(타입 ①)과 topic 1개 쿼리 1,000건(타입 ②), 가장 흔한 topic 20개 쿼리 200건을 둘 다에 던졌다. 정답은 numpy로 따로 계산한 (커버 수 desc, 가중 합 desc) 목록. 검사 항목은 스펙 §4의 "friends row가 친구 아닌 요청자에게 나온 건수 0", 상위 20 안 커버 수 역전 0, 보유하지 않은 agent 반환 0.
- **타입 ③**: 서로 다른 상대가 2명 이상인 유저 5,000명을 뽑아 상대 하나를 숨기고(leave-one-out) 나머지로 학습. 지표는 숨긴 상대의 HR@10·NDCG@10, 스펙 §4의 "정답 목록 대비 recall@10"(오라클 top-10과의 겹침), 그리고 top-10 중 요청자와 같은 군집인 비율(군집 신호를 잡았는지). 후보는 discoverable agent만, 본인·이미 대화한 상대 제외.
- **환경**: macOS arm64, Docker Desktop VM 7.7 GB. OpenSearch 2.19.0 단일 노드 heap 1 GB, PostgreSQL 17, MySQL 8.4, `zhenghaoz/gorse-in-one:latest`(= v0.5.11, API v0.2.7).

## 2. 타입 ①② — OpenSearch vs PostgreSQL

### 2-1. 결과

| 쿼리 | n | PostgreSQL p50 / p95 | OpenSearch p50 / p95 | 위반(둘 다) |
|---|---|---|---|---|
| 타입 ① topic 1~3개 | 2,000 | 0.8 / 2.3 ms | 2.3 / 3.9 ms | friends 유출 0 · 커버리지 역전 0 · 미보유 0 |
| 타입 ② topic 1개 | 1,000 | 0.6 / 2.3 ms | 2.3 / 4.8 ms | 0 · 0 · 0 |
| 흔한 topic 20개 | 200 | 1.6 / 4.5 ms | 2.5 / 4.5 ms | 0 · 0 · 0 |
| 저장 크기 | | 27 MB (row 36만, B-tree 1개) | 16 MB (문서 59,191 + nested 36만) | |
| 정답 목록과 상위 20 겹침 | | 1.000 | 1.000 | |

PostgreSQL 쪽은 재설계 §5-2 표 그대로다:

```sql
SELECT agent_id, count(*) AS cov, sum(w) AS s
FROM open_rows
WHERE topic_id = ANY(%s) AND agent_id <> %s
  AND (tier = 1 OR (tier = 2 AND agent_id = ANY(%s)))   -- %s = 요청자의 친구 목록(최대 5,000)
GROUP BY agent_id ORDER BY cov DESC, s DESC LIMIT 20
```

친구 목록 5,000개를 배열로 넘겨도 p95가 2.3 ms다. friends 필터는 인덱스 구조 그 자체라는 §5-2의 주장이 맞다.

### 2-2. OpenSearch로 커버리지 우선 정렬을 하려면 — 함정 하나

BM25 점수는 매칭 term 수가 아니라서 그대로 쓰면 커버리지 순이 안 된다. 실제로 동작한 형태는 topic마다 `nested` 절 하나(`public` row 또는 `friends` row ∧ `owner ∈ 친구 목록`), 절의 점수는 `function_score`로 그 row의 가중치 `w`로 **대체**(`boost_mode: replace`), 상위 `bool.should`가 절 점수를 합산. 그러면 점수 = 매칭 topic들의 `w` 합.

**여기서 `w`의 범위가 문제였다.** 첫 판은 `w ∈ [1, 2)`로 뒀고 "k개 매칭 = [k, 2k)"라 k=2의 [2, 4)와 k=3의 [3, 6)이 겹쳐, 점수 높은 topic 2개가 낮은 3개를 앞질렀다(300건 중 28 %에서 PostgreSQL과 순서가 갈렸다). `w ∈ [1, 1 + 1/k_max)`로 두면(k_max=3이니 `1 + score/101/3`) k개 매칭이 [k, k+1) 안에 갇혀 커버리지가 먼저다. 이 규칙은 계약 §7의 feature 가중 파일을 OpenSearch에 옮길 때도 그대로 적용된다: **커버리지 아래 단계의 점수 총합은 1 미만이어야 한다.**

### 2-3. OpenSearch 2.19 + Python 3.14 클라이언트 = 응답이 안 온다

`Accept-Encoding`에 `zstd`가 들어가면 OpenSearch 2.19.0의 netty `ZstdEncoder`가 `UnsupportedOperationException: Direct buffers not supported`를 던지고 **연결이 응답 없이 닫힌다**(curl로 `zstd`만 넣어도 5 s 타임아웃, `gzip`·`br`은 정상). Python 3.14는 표준 라이브러리에 `compression.zstd`가 있어서 **urllib3 2.x와 aiohttp 3.13이 기본으로 `zstd`를 포함한다** — 코드 repo의 aiohttp 3.13.3에서 `client_reqrep.py`의 `_gen_default_accept_encoding()`이 `HAS_ZSTD`면 `zstd`를 붙인다. OpenSearch를 쓴다면 클라이언트에 `Accept-Encoding: gzip`을 고정해야 한다. 이번 실측도 그렇게 해서 돌렸다. AWS OpenSearch Service의 빌드에서 같은지는 확인하지 않았다.

### 2-4. 판단 재료

타입 ①②에 OpenSearch가 주는 것은 없고(같은 정답, 3배 느림, 운영 컴포넌트 하나 추가, 점수 설계 함정, zstd 함정) PostgreSQL 역인덱스는 재설계 §5-2가 적은 대로 충분하다. OpenSearch가 다시 후보가 되는 지점은 §5-2 표의 "topic 벡터 kNN(필요할 때만)"이지 term 인덱스가 아니다.

## 3. 타입 ③ — CF가 이 밀도에서 무엇을 하나

### 3-1. 결과 (U=100k, 평가 유저 5,000, 후보 = discoverable 56,276)

**표를 읽기 전에 — 실험과 네 열의 뜻.** 유저 5,000명을 뽑아 각자가 실제로 대화한 상대 중 하나를 숨겼다. 나머지 대화 기록으로 학습한 뒤 각 방법에게 "이 유저에게 추천할 agent 10명"을 뽑게 했다. 후보는 공개된 agent 56,276명이고 본인과 이미 대화한 상대는 뺐다. 열 네 개는 각각 다른 질문에 답한다.

| 열 | 답하는 질문 | 읽는 법 |
|---|---|---|
| **HR@10** (hit rate) | 숨긴 상대가 추천 10명 안에 든 유저의 비율 | 인기도만 0.0090이면 5,000명 중 45명에게 맞혔다는 뜻. 56,276명 중 10명을 고르는 일이라 절대값은 작다. 무작위는 0.0002 |
| **NDCG@10** | HR과 같은 질문인데 순위를 본다 | 숨긴 상대가 1위면 1, 2위면 0.63, 10위면 0.29를 주고 평균. HR이 같아도 상위에 놓는 방법이 높다 |
| **recall@10 vs 정답 목록** | 생성기가 아는 진짜 정답 순위(군집 친화도 × 인기도) 상위 10명과 추천 10명이 얼마나 겹치나 | 오라클은 정답 자체라 1.000. 인기도만 0.276이면 정답 top-10의 2.8명을 맞혔다는 뜻. 스펙 §4가 ③ CF의 지표로 정한 값 |
| **같은 군집** | 추천 10명 중 요청자와 같은 persona 군집인 agent의 비율 | "개인화가 되고 있나"를 본다. 무작위는 약 0.10(군집 크기 분포 때문), 정답을 다 아는 오라클은 0.70 |

**상한을 먼저 본다.** 오라클조차 HR@10이 2 %다. 정답을 다 알아도 held-out 상대를 top-10에 넣는 비율이 그 정도라는 것은, 스펙 파라미터가 만드는 대화 상대 분포가 그만큼 넓다는 뜻이다. 그래서 HR은 절대값이 아니라 **인기도 대비**로, 그리고 **오라클을 상한**으로 놓고 읽는다.

λ=3 (스펙 기본. 학습 nnz 233,287, 밀도 2.3×10⁻⁵):

| 방법 | HR@10 | NDCG@10 | recall@10 vs 정답 목록 | top-10의 같은 군집 비율 | 비용 |
|---|---|---|---|---|---|
| 오라클 `affinity × pop` (정답 자체) | 0.0188 | 0.0106 | 1.000 | 0.695 | — |
| 인기도만 | 0.0090 | 0.0052 | 0.276 | 0.137 | 0 |
| 무작위 | 0.0002 | 0.0001 | 0.000 | 0.097 | — |
| B: 아이템 코사인 이웃 | 0.0008 | 0.0003 | 0.002 | 0.181 | 행렬곱 0.0 s |
| B: 동시 출현 raw 카운트 | 0.0012 | 0.0009 | 0.014 | 0.212 | 0.0 s |
| B: 동시 출현 + 인기도 tie-break | 0.0030 | 0.0016 | 0.080 | 0.230 | 0.0 s |
| A: `implicit` ALS 64f reg .05 | 0.0020 | 0.0011 | 0.051 | 0.148 | fit 7.5 s |
| **A: `implicit` ALS 16f reg .5** | **0.0054** | **0.0031** | **0.182** | 0.185 | **fit 0.9 s** |
| A: ALS 16f α=10 | 0.0060 | 0.0035 | 0.148 | 0.186 | fit 0.9 s |
| A: ALS 64f reg 5 α=10 | 0.0042 | 0.0023 | 0.096 | 0.198 | fit 8.2 s |
| A: ALS 16f + 인기도(z-합) | 0.0044 | 0.0024 | 0.109 | 0.197 | |

λ=10 (학습 nnz 723,983):

| 방법 | HR@10 | NDCG@10 | recall@10 vs 정답 | 같은 군집 |
|---|---|---|---|---|
| 오라클 | 0.0198 | 0.0126 | 1.000 | 0.701 |
| 인기도만 | 0.0112 | 0.0062 | 0.271 | 0.125 |
| B: 아이템 코사인 이웃 | 0.0002 | 0.0001 | 0.000 | 0.121 |
| B: 동시 출현 raw 카운트 | 0.0076 | 0.0042 | 0.187 | 0.325 |
| B: 동시 출현 + 인기도 tie-break | 0.0102 | 0.0056 | 0.273 | 0.308 |
| A: ALS 64f reg .05 | 0.0040 | 0.0021 | 0.107 | 0.243 |
| **A: ALS 16f reg .5** | **0.0096** | 0.0043 | **0.291** | 0.272 |
| A: ALS 16f α=10 | 0.0070 | 0.0044 | 0.238 | 0.293 |
| A: ALS 64f reg 5 α=10 | 0.0066 | 0.0037 | 0.156 | 0.277 |

ALS fit은 λ=10에서도 1.8 s(16f) / 11 s(64f), 프로세스 RSS 300 MB 이하. 재계산 비용은 논점이 아니다.

**λ=10 표의 행을 읽으면:**

- **인기도만**: 맞히는 능력(HR 0.0112)은 가장 높지만 개인화(같은 군집 0.125)는 거의 없다. 인기 agent는 누구에게나 인기라 held-out 상대로도 자주 나온다.
- **ALS 16f reg .5**: HR은 인기도와 거의 같고(0.0096), 정답 목록 겹침은 더 높고(0.291), 같은 군집은 두 배(0.272). "인기도만큼 맞히면서 그 사람 취향 쪽으로 기울었다." λ=10에서 CF를 켤 만하다고 한 근거가 이 행이다.
- **동시 출현 + 인기도 tie-break**: ALS 16f와 거의 같은 프로필. 라이브러리 없이도 비슷하게 갈 수 있다는 뜻인데, 인기도 tie-break를 빼면(raw 카운트 행) HR이 0.0076으로 떨어진다.
- **아이템 코사인 이웃**: 전부 무작위 수준. 코사인 정규화가 인기도를 지워 "한 번 같이 나타난 희귀 쌍"을 1위로 올린다.
- **ALS 64f**: 16f보다 전부 나쁘다. 데이터가 희소할수록 차원을 줄여야 한다.

> **이 표는 이 스파이크의 생성기로 잰 값이다**(2026-09-12, 1-8 구현에서 확인). `spikes/2026-09-08_library_verification/gen.py`는 자기 모집단을 직접 만들고, 그 뒤 1-6에서 `synthetic/`(합성 스펙 §3)이 들어왔다. **지금 생성기로 다시 재면 CF가 더 나쁘다**: 이 파일의 `cf_eval.py`를 오늘 만든 10만 모집단에 그대로 돌리면 λ=10에서 ALS 16f가 HR@10 **0.0068**, 인기도 **0.0150**(위 표는 0.0096 대 0.0112)이다. 비율로 0.86 → 0.45. 구현 쪽 요인 둘은 확인했고 둘 다 이 차이를 만들지 않는다 — R16의 turn 가중 confidence는 이 스파이크의 "방마다 1" 카운트보다 **낫고**(0.51 대 0.44), 서빙이 쓰는 fold-in(`recalculate_user`)은 학습된 user factor 대비 3 %쯤만 잃는다. 남는 설명은 모집단이다. 어느 쪽 분포가 실제에 가까운지는 1-9에서 정한다. 그때까지 이 표의 절대값은 **이 생성기에 한한 값**으로 읽는다.

λ=3 표는 같은 순서인데 모든 CF가 인기도 아래에 있다는 점만 다르다. ALS 16f가 인기도의 60 %(HR 0.0054 vs 0.0090)까지 오고, 같은 군집 비율은 인기도보다 높다(0.185 vs 0.137).

### 3-2. 결과가 뜻하는 것

1. **오라클의 상한이 1.9 %인 이유.** 스펙 §2의 `affinity`(대각 1.0 / 부 군집 0.5 / 나머지 0.05 + N(0, 0.1) 노이즈)와 Pareto(2) 인기도가 만드는 대화 상대 분포가 그만큼 넓다. 상한을 올리는 조정은 §5-2와 스펙 §7에 있다.
2. **스펙 밀도(λ=3)에서는 어떤 CF도 인기도를 못 넘는다.** 유저당 서로 다른 상대 2.4명, 아이템 10만 개면 학습 신호가 너무 적다. ALS 16 factor가 인기도의 60 %까지 오고, 군집 신호는 인기도보다 뚜렷하게 잡는다(0.185 vs 0.137). 즉 **CF는 인기도 위에 얹는 개인화 feature이고 단독 후보 소스가 아니다** — 재설계 §2-3의 "인기도 → content 유사 → CF 누적" 순서가 데이터로 확인됐다.
3. **λ=10이 되면 ALS 16f와 "동시 출현 + 인기도"가 인기도와 동률**이면서 군집 비율은 두 배다(0.27~0.31 vs 0.125). 개인화가 비용 없이 붙는 시점이 그 근처다. 실서비스 대화율이 어디인지가 CF의 가치를 정한다 — 스펙 §7 "실측 없음"이 여기 직결된다.
4. **아이템 코사인 이웃은 이 밀도에서 무작위 수준이고, 데이터가 늘어도(λ=10) 그대로다.** 코사인 정규화가 인기도를 완전히 지워 "한 번 같이 나타난 희귀 쌍"이 1위가 된다. O11의 "아이템 기반 이웃"을 하려면 정규화 없는 raw 카운트여야 하고, 그것도 ALS 16f보다 못하거나 같다.
5. **factor 수는 작아야 한다.** 64 factor는 16 factor의 절반 이하다(λ=3에서 0.20 % vs 0.54 %). 희소할수록 강한 정규화·작은 차원이다. ALS 파라미터는 실데이터에서 다시 잡아야 하지만 방향은 이것이다.
6. **콜드스타트**: λ=3에서 유저 5 %가 대화 0건이라 CF 점수가 없다. 그 유저에게는 인기도와 content만 남는다 — 스펙 §4 "③ 콜드스타트 별도 집계" 항목이 필요한 이유.

### 3-3. 판단 재료

- **O11**(B안 CF 첫 구현): 측정으로는 "행렬 분해"가 답이고, 그 행렬 분해를 `implicit`로 하면 A안(라이브러리형)이다. B안의 CF를 고집할 이유는 "라이브러리 의존 없음" 하나뿐이고, 값은 λ=3에서 ALS의 절반이다.
- **O8**(A안 엔진): 라이브러리형은 비용이 0에 가깝고(fit 1 s, 300 MB, wheel 설치) 우리 랭커 안에 feature 하나로 들어간다. 서비스형(Gorse)은 §4.

## 4. Gorse v0.5.11 — 이 모양(아이템 = personal agent 10만, 피드백 = 대화 시작)에서

아카이브 `recsys_opensource/gorse.md` §11~§12의 실측은 item-to-item tags 경로였다. 이번은 재설계가 Gorse에 맡기려는 **`[recommend.collaborative]` 경로**다.

### 4-1. R08 저장소 제약과 충돌한다

`cache_store = "redis://…"`로 띄우면 초기화에서 죽는다:

```
failed to init database: ERR unknown command 'FT._LIST'   (storage/cache.(*Redis).Init:107)
```

`FT._LIST`는 RediSearch 모듈 명령이다. v0.5의 Redis cache store는 **Redis Stack**을 전제하고, ElastiCache(Redis·Valkey)는 모듈을 지원하지 않는다. R08 안에서 남는 cache store는 MySQL/PostgreSQL이고, 아카이브 실측(X4~X6)이 MongoDB를 cache store로 쓴 이유("저장이 빨라서")가 그대로 비용으로 돌아온다.

### 4-2. MySQL cache store로 돌린 결과

| 단계 | 값 |
|---|---|
| 적재 (REST, 5,000건 배치) | 유저 10만 2.0 s · 아이템 10만 30 s · 피드백 233,287건 9.9 s |
| Load Dataset | 3 s |
| Train Collaborative Filtering Model (BPR 100 epoch) | **19 s**. 내부 평가 NDCG@10 0.127 / Recall@10 0.244 — Gorse 자체 샘플 평가라 §3 표와 비교 불가 |
| Generate recommendation (10만 유저 랭킹·캐시 저장) | **6분 49초**(MySQL binlog 켜짐, 기본값). `--skip-log-bin`으로 다시 띄운 두 번째 실행은 **1분 27초~1분 54초** |
| 그 다음 | 완료 직후 **바로 다음 사이클**을 시작해 다시 10만 유저를 돈다(`collaborative filtering dataset not changed`인데도). 상시 재계산 |
| 컨테이너 RSS | Gorse 514 MB, MySQL 769 MB(적재 전 668 MB) |
| `GET /api/recommend/{user}?n=10` | p50 2.5 ms / p95 5.3 ms |

### 4-3. 서빙이 폴백을 돌려줬다 — 원인 둘, 둘 다 문서에 없다

생성 완료 뒤 `GET /api/recommend/u123?n=5`가 `u99999, u99998, …`(타임스탬프가 전부 같아 id 역순인 **`latest` 폴백**)을 돌려줬고, 5,000명 평가의 HR@10은 무작위 수준(0.0002)이었다. MySQL cache에는 유저당 `recommend` 100행·`collaborative-filtering` 약 127행(합계 1,390만 행)이 정상적으로 있었다. 원인은 두 겹이었고, v0.5.11 소스와 MySQL general log·`EXPLAIN`으로 확인했다.

**원인 ① 기본 ranker 설정이 오프라인 캐시를 읽지 않는다** (`logics/recommend.go` `Recommender.Recommend`, `config/config.go` 기본값)

- `[recommend.ranker] type`의 기본값은 `"none"`이고, 이때 온라인 경로는 **오프라인 `recommend` 캐시를 읽지 않고** `ranker.recommenders`를 순서대로 돈다. 그 기본값이 `["latest"]`다. 즉 기본 설정에서는 worker가 만든 유저별 추천이 서빙에 한 번도 쓰이지 않는다.
- 오프라인 추천을 서빙하려면 `type = "fm"`(클릭 예측 ranker 학습이 추가로 필요)이거나, `type = "none"`에 `recommenders = ["collaborative"]`처럼 캐시 컬렉션을 읽는 recommender를 명시해야 한다.
- **설정을 바꾸면 설정 해시가 바뀌어 캐시 전체가 GC로 비워지고 10만 유저를 다시 돈다.** 그 사이 응답은 폴백이다.

**원인 ② MySQL cache store의 multi-valued 인덱스가 `categories = []`인 행을 숨긴다** (`storage/cache/sql.go` `Init`·`SearchScores`)

- Gorse는 MySQL에 `ALTER TABLE documents ADD INDEX idx_collection_subset_categories (collection, subset, (CAST(categories AS CHAR(255) ARRAY)))`를 만든다. MySQL의 multi-valued 인덱스는 **빈 JSON 배열에 대해 인덱스 레코드를 만들지 않으므로**, `categories`가 `[]`인 행은 이 인덱스를 타는 쿼리에서 존재하지 않는 것처럼 보인다.
- 서버의 쿼리 `SELECT … WHERE collection = 'collaborative-filtering' AND subset = '<user>' AND is_hidden = false ORDER BY score DESC LIMIT 100`은 `EXPLAIN`에서 그 인덱스를 고른다. 같은 조건에 `FORCE INDEX (PRIMARY)`를 붙이면 102행, 인덱스를 타면 **0행**. 그래서 `collaborative` recommender가 빈 결과를 내고 폴백으로 넘어갔다.
- 아이템에 `Categories`를 하나라도 주면 피할 수 있다. 우리 모양(agent에는 카테고리가 없다)에서는 기본값 그대로 쓰면 걸린다. 인덱스를 지우면 서빙되지만 **Gorse는 시작할 때마다 이 인덱스를 다시 만든다**(실측: 재시작 뒤 다시 폴백, 다시 지우면 다시 서빙).

**둘을 고친 뒤의 서빙 결과** (같은 5,000명 leave-one-out, §3과 같은 정답):

| | HR@10 | NDCG@10 | 지연 시간 p50 / p95 |
|---|---|---|---|
| Gorse BPR (`collaborative`, 기본 하이퍼파라미터, 100 epoch) | **0.0006** | 0.0005 | 5.2 / 15.0 ms |
| 참고: `implicit` ALS 16f (§3-1) | 0.0054 | 0.0031 | — |
| 참고: 인기도만 | 0.0090 | 0.0052 | — |

Gorse의 CF는 같은 데이터에서 `implicit` ALS의 1/9, 인기도의 1/15다. Gorse 내부 평가가 보고한 Recall@10 0.24는 샘플링한 negative에 대한 값이라 이 표와 비교할 수 없다.

**첫 시도가 남긴 것.** 첫 실행은 VM 7.7 GB에 컨테이너 넷을 올려 VM이 죽었고, 두 번째는 binlog가 켜진 MySQL에 1,390만 행을 7분마다 다시 쓰다 호스트 디스크(Docker.raw 67 GB)를 채웠다. `--skip-log-bin`으로 새로 띄우면 10만 유저 재생성 사이클이 **1분 27초~1분 54초**로 줄었다(§4-2의 6분 49초는 binlog 비용이 포함된 값). Gorse의 운영 비용은 "컴포넌트 하나 더"가 아니라 cache store 크기·재계산 사이클·문서에 없는 기본값 둘이다. 아카이브 §11의 "문서에 없는 동작은 실행이 답한다" 사례가 둘 더 늘었다.

### 4-4. 아카이브 사실 중 이번 모양에도 그대로인 것

- 요청자별 friends/private 필터는 없다 → 엔진 결과를 받아 우리가 거르고 부족하면 더 받는다(§11-3).
- 증분 갱신이 없다. 신선도 = 사이클 길이. 이번 모양에서 사이클은 "10만 유저 전부 다시 랭킹"이라 **7분**이고 유저 수에 비례한다.
- master 한 프로세스가 데이터셋을 메모리에 들고 있다(§12-1 S9).

## 5. 이 문서가 바꾸는 것

### 5-1. 문서 갱신 제안

- **재설계 §5-1 표**: LightFM 삭제. Gorse 행의 저장소를 "MySQL/PostgreSQL data store **+ MySQL/PostgreSQL cache store**(Redis는 Redis Stack 필요, ElastiCache 불가)"로. OpenSearch 행에 "term 인덱스 용도로는 PostgreSQL이 더 낫다(검증 §2), kNN 용도만 남김".
- **`decisions.md`** O8·O11에 이 문서를 근거로 단다(결정은 오너).
- **계약 §7 feature 가중**: 커버리지 아래 단계 점수의 총합 < 1 규칙(§2-2)을 불변식으로.
- **코드 repo**: OpenSearch를 쓰게 되면 aiohttp 세션에 `Accept-Encoding: gzip` 고정(§2-3).

### 5-2. 합성 스펙에 넣을 것 (§7 "열린 항목")

- 정답의 선명도. 지금 파라미터로는 오라클 HR@10이 1.9 %라 방법 간 차이가 0.1 % 단위에서 갈린다. 후보: `affinity` 비대각 0.05 → 0.01, 노이즈 σ 0.1 → 0.03, 또는 recall@10을 "오라클 top-10과의 겹침"으로만 재기(이 문서가 그렇게 했다). 어느 쪽이든 §4 정답 정의에 적어야 두 구현안이 같은 기준을 본다.
- 대화율 λ를 3과 10 둘로 돌리는 것을 프로토콜에 넣는다. CF의 값이 λ에 따라 "인기도의 60 %"에서 "인기도와 동률 + 개인화"로 바뀌므로, 실측 λ가 오기 전엔 둘을 다 봐야 한다.
- 친구 degree 정의: "유저가 고르는 수"(median 25)인지 "대칭화 뒤 degree"(평균 74)인지 명시.

### 5-3. 하지 않은 것

- 실제 카탈로그 파일·라벨·LLM text→topic 단계. 이 문서는 인덱싱·정렬·CF만 잰다.
- 동시성 부하(요청은 전부 순차). p50/p95는 단일 클라이언트 값이다.
- Gorse의 user-to-user·popular recommender, BPR 하이퍼파라미터 탐색(`model_search`), `type = "fm"` ranker.
- PostgreSQL pgvector / OpenSearch kNN(content 유사 유저). 재설계가 "필요할 때만"으로 둔 항목.
- 100만 유저. 스펙 §7 staged scale의 다음 단계.
