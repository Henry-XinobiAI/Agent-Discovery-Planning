# 합성 모집단 생성기 스펙 — 10만 유저, 구현이 같은 정답을 상대하도록

> `agent_discovery_redesign.md` §6-2·§9의 4번. 검증(§6)의 절반은 이 생성기다. **구현(R34)과 그 소스별 ablation(인기도만·content만·CF만·합친 랭커)이 똑같은 유저·topic·friend·대화 로그를 받고, 생성기만 아는 잠재 구조가 정답이 된다.** 실측 분포가 없는 값은 파라미터로 두고 베타 뒤 실측으로 교체한다.
>
> 초안 2026-09-08. 코드로 옮길 때 이 문서의 파라미터 이름을 그대로 쓴다.

---

## 0. 한눈에

- **입력**: topic-api 카탈로그 파일(`data/catalog_dist/catalog.json`, 3003 topic, 2959 부모 간선, 라벨 ko/en/ja), 파라미터 하나의 묶음(§2), 시드.
- **출력**: 유저·agent·공개된 topic row·friend 쌍·대화 로그·타입 ① 쿼리·정답, 전부 파일(§5). 같은 시드는 같은 출력.
- **적재 경로 둘**: (가) 우리 이벤트 그대로 발행해 워커가 받는다 — 이벤트 경로와 재조회까지 테스트. (나) 파일을 저장소에 직접 적재 — 빠른 반복. 두 경로의 결과 저장 상태는 같아야 한다(§6 검증 1).
- **규모**: `U`(유저 수) 하나로 조절. 10만에서 시작해 100만을 다시 만든다.
- **정답**: 군집 구조에서 나오는 "비슷한 사람들이 대화한 agent", "내 topic을 모두 가진 agent", 그리고 심어 둔 잠재 친화도. recall@10, NDCG@10, 커버리지 위반 수의 분모다.

---

## 1. 무엇을 닮게 만드나 — 실제 시스템의 모양

| 실제 | 생성기가 따르는 것 |
|---|---|
| 카탈로그 3003 topic, 54 상위 그룹, 최대 7단계(응답은 3단계) | 카탈로그 파일을 그대로 읽는다. topic id는 카탈로그 id 그대로(현재 3003개는 모두 32 hex이지만 타입은 `[A-Za-z0-9_-]{1,64}`라 형식을 가정하지 않는다). 군집의 선호는 **상위 그룹**(root부터 2단계) 단위로 정의하고 그 아래 leaf를 샘플링한다 |
| 유저 topic row: `score` 0~100 (facet 6개의 가중 평균에 spread 지수·coverage 페널티·confidence를 곱한 값), `visibility` 4값, `revision` | `score`는 0~100 실수(분포만 흉내, 공식은 재현하지 않음), `visibility`는 `private` 기본에서 공개된 것만 public/friends, 소량 hidden. `revision`은 쓰기마다 +1 |
| default private, 유저가 명시적으로 공개한다, 다시 비공개로 되돌릴 수 있다 | 공개 비율을 파라미터로, 비공개 전환 이벤트 스트림을 따로 생성 |
| agent id = user id에서 uuid5 | 같은 규칙. 네임스페이스는 생성기 상수(실제 값과 달라도 무해, 결정론적이면 충분) |
| friend: 요청·수락, 상한 5,000 | 무방향 쌍, 군집 안 확률 높게, degree 분포 긴 꼬리, 상한 적용 |
| 대화: 타인 agent와의 방이 생성되고(시작) 메시지가 오간다(turn) | (actor, owner) 쌍의 시작 사건과 turn 수, 시각 |
| 성숙도: topic은 `score`, agent는 컴포넌트 예정 | `topic_score`와 `topic_maturity` feature는 둘 다 `score/100`(topic 성숙도 컴포넌트가 생기기 전까지 같은 값으로 두는 이 스펙의 가정. 계약 §7은 `topic_maturity`를 임시값 → 컴포넌트로 적는다). `agent_maturity` = `min(1, 0.5·log1p(공개된 topic 수)/log1p(20) + 0.5·log1p(총 turn 수)/log1p(200))`, `users.parquet`의 컬럼 |

실제 유저 topic 샘플은 7계정 16항목(persona seeds)뿐이라 **유저당 topic 수, 공개 비율, 대화 빈도는 모두 가정**이다. §2의 기본값은 가정이고, 그 값이 결과를 얼마나 흔드는지 §6 검증 4에서 본다.

---

## 2. 파라미터

| 이름 | 기본 | 뜻 |
|---|---|---|
| `U` | 100,000 | 유저 수 |
| `seed` | 20260908 | 모든 난수의 시드 |
| `K` | 60 | persona 군집 수 (카탈로그 상위 그룹 54와 비슷한 자릿수, 그룹과 1:1은 아니다) |
| `cluster_size_alpha` | 1.1 | 군집 크기의 Zipf 지수. 큰 군집 몇 개와 작은 군집 여럿 |
| `secondary_clusters` | {0: 0.5, 1: 0.35, 2: 0.15} | 유저가 주 군집 외에 갖는 부 군집 수의 분포 |
| `topics_per_user` | 로그정규 median 8, σ 0.7, 상한 60 | 유저가 가진 topic 수(tier 무관) |
| `topic_zipf_alpha` | 1.0 | 군집 안에서 topic 인기의 Zipf 지수 |
| `off_cluster_topic_rate` | 0.15 | 군집 분포 밖에서 무작위로 뽑는 topic 비율 |
| `score_dist` | 베타(5, 2) × 100 | topic `score`. 실제 샘플이 76.4 같은 높은 값이라 위로 치우침 |
| `opener_rate` | 0.6 | 하나 이상의 topic을 공개한 유저 비율 |
| `tier_mix_of_opened` | public 0.4 / friends 0.2 / private 0.35 / hidden 0.05 | 공개한 유저의 topic별 tier 비율 (private = 공개하지 않은 것, hidden = 숨김). hidden이 있어야 hidden → 삭제 경로가 테스트된다 |
| `agent_discoverable_rule` | "public topic ≥ 1" + 예외 2% | agent 공개 여부. 예외는 규칙이 분리될 수 있음을 테스트 |
| `friend_degree` | 로그정규 median 25, σ 0.9, 상한 5,000 | 유저별 친구 수 |
| `friend_homophily` | 0.7 | 친구 중 같은 주 군집인 비율 |
| `affinity` | K×K 행렬: 대각 1.0, 부 군집 관계 0.5, 무작위 0.05, 노이즈 N(0, 0.1) | 요청자 군집 × agent 소유자 군집의 잠재 친화도 — **CF의 정답** |
| `conversation_rate` | 유저당 포아송 λ ∈ **{3, 10, 30}** (기간 90일). 검증은 세 값을 모두 돈다 | 타인 agent와 대화를 시작한 횟수. 3은 첫 초안의 추정치였고, 오너는 실제 값이 그보다 클 것으로 본다(2026-09-08: 다른 agent와 대화해 배우는 것이 핵심 feature). CF의 가치가 이 값에 가장 민감하다(`library_verification.md` §3). 실측이 오면 §8의 보정이 이 행을 갈아 끼운다 |
| `popularity_skew` | 2.0 | agent 인기의 power-law 지수. 대화 상대 선택에 친화도와 곱해진다 |
| `turns_per_conversation` | 기하 p=0.25, 상한 60 | 대화 하나의 turn 수. CF confidence의 입력(계약 §7 `cf_score`) |
| `revisit_rate` | 0.3 | 대화 중 "이미 대화한 쌍의 방을 다시 여는" 비율. §3-4. CF confidence의 입력 |
| `close_rate` | 0.1 | 생성 뒤 비공개 전환 이벤트를 받는 공개된 topic 비율 |
| `deactivate_rate` | 0.01 | 탈퇴 이벤트를 받는 유저 비율 |
| `explicit_queries` | 2,000 | 타입 ① free text 쿼리 수 |
| `query_topic_count` | {1: 0.5, 2: 0.35, 3: 0.15} | 쿼리 하나가 담는 topic 수 |
| `horizon_days` | 90 | 로그의 시간 범위 |

---

## 3. 생성 순서

각 단계는 이전 단계의 출력만 읽는다. 단계마다 파일이 나오므로 중간부터 다시 돌릴 수 있다.

### 3-1. 군집과 topic 선호

1. 카탈로그를 읽어 상위 2단계 그룹 `G`와 각 그룹의 leaf 집합을 만든다.
2. 군집 `k`마다 그룹 선호 벡터를 뽑는다: 주 그룹 1~3개(가중 0.6~0.8), 나머지 그룹에 잔여를 Dirichlet로. 군집 안 topic 인기는 그룹 선호 × 그룹 내 Zipf.
3. 군집 크기를 `cluster_size_alpha`로 뽑아 `U`를 배분한다.

### 3-2. 유저와 topic

1. 유저 `u`: `user_id` = uuidv7(시드 기반 시각), 주 군집 1, 부 군집 0~2, `registered_at`(기간 안 균등).
2. topic 수를 뽑고, `off_cluster_topic_rate`만 무작위, 나머지는 (주 군집 0.7, 부 군집 0.3 — 부 군집이 없으면 주 군집 1.0)의 선호에서 Zipf 샘플링. 중복 제거.
3. topic마다 `score`, `updated_at`, `revision=1`.
4. `opener_rate`로 "공개하는 유저"를 정하고, 그 유저의 topic마다 `tier_mix_of_opened`로 tier. 나머지 유저는 전부 private.
5. `agent_id` = uuid5(NS, f"personal_agent:{user_id}"). `discoverable`은 규칙 + 예외.

### 3-3. friend

1. 유저별 degree를 뽑고, `friend_homophily`로 같은 주 군집에서 / 아니면 전체에서 상대를 뽑는다. 무방향, 자기 제외, 중복 제거, 상한.
2. 쌍마다 `accepted_at`(기간 안).

### 3-4. 대화 로그 — CF의 정답이 여기서 만들어진다

1. agent 인기 가중치 `pop[a]`를 power-law로 뽑는다(`discoverable=false`인 agent는 0).
2. 유저 `u`의 대화 수를 포아송으로 뽑고, 상대 agent를 확률 ∝ `affinity[cluster(u)][cluster(owner(a))] × pop[a] × open(a)`로 뽑는다. `open(a)` = 그 agent가 `u`에게 공개돼 있나(public이거나 friends이고 친구). 자기 자신 제외.
3. 대화마다 상대를 뽑기 전에 `revisit_rate` 확률로 "이미 대화한 쌍 중 하나의 방을 다시 연다"(같은 `room_id`를 다시 쓴다 — 이벤트로는 `message_created`만 나온다, R46)를 택하고, 아니면 2의 확률로 새 상대를 뽑는다. `started_at`, `turns`, `entry`(처음엔 전부 `"direct"` — 우리 추천이 없던 세상), `recommendation_id=null`.
4. turn을 `message_created` 이벤트로 펼친다(`room_id` = uuid5(actor, agent), `sender_type="user"`, `room_type="agent_dm"`).

### 3-5. 변화 이벤트 스트림

시간 순으로 섞어 하나의 이벤트 스트림을 만든다. 이것이 적재 경로 (가)의 입력이다.

| 사건 | 우리가 받는 이벤트 | 비율 |
|---|---|---|
| 가입 | `bourbon.user_registered` | 전 유저 |
| topic 동기화 | `bourbon.topics_updated` × 움직인 topic | 전 유저, topic마다 |
| tier 공개·비공개 전환 | visibility 변경 신호(임시 이름 `bourbon.user_topic_settings_updated`, R48) | 공개한 topic 전부 + `close_rate` |
| agent 공개 여부 | `bourbon.personal_agent_visibility_changed` | 규칙이 바뀌는 시점마다 |
| 친구 수락 | `bourbon.friendship_changed(accepted)` | 전 쌍 |
| 대화 시작 | 그 방의 첫 `bourbon.message_created`(`room_type=agent_dm`, R51) | 추천으로 시작된 대화만(R52) |
| turn | `bourbon.message_created` | 전 turn |
| 탈퇴 | `bourbon.user_deactivated` | `deactivate_rate` |

`topics_updated`와 `settings_updated`는 **힌트**이므로 생성기는 재조회에 답할 **topic-api 목(mock) 서버**(`GET /users/{id}/topics?visibility=…`)도 같이 제공한다 — 파일에서 그 유저의 현재 row를 돌려주는 작은 HTTP 서버. 이벤트 시각 이후 상태를 답하도록 시각을 인자로 받는다.

### 3-6. 타입 ① 쿼리

1. `explicit_queries`개. 요청자는 무작위 유저. topic 1~3개를 요청자 군집 선호에서 뽑는다.
2. free text는 라벨 조합 템플릿: ko `"{라벨1}하면서 {라벨2}"`, `"{라벨1} 잘 아는 사람"`, `"{라벨1}, {라벨2} 같이 좋아하는"` 등 10여 개 + 라벨은 `aliases`에서 무작위로 바꿔 넣기. en도 같은 수.
3. 정답: 뽑힌 topic id 집합, 그리고 그 시점의 공개된 row에서 계산한 **커버리지 순 agent 목록**(요청자에게 공개된 것만, 본인 제외).

LLM 확장은 비용이 있으므로 검증에서는 **쿼리 200개만** 실제 LLM을 통과시켜 text → topic 정확도를 재고, 나머지 1,800개는 topic id로 직접 넣어 인덱싱·정렬 부분만 잰다. text → topic 단계는 인덱스와 무관하므로 이렇게 갈라도 측정이 흔들리지 않는다.

---

## 4. 정답 정의

| 타입 | 정답 | 지표 |
|---|---|---|
| ① | 요청자에게 공개된 agent를 (커버 topic 수 desc, **계약 §7 feature의 같은 가중 파일로 낸 점수** desc)로 정렬한 목록 | 커버리지 위반 0건(상위 k에서 커버 수가 역전된 쌍), recall@10. NDCG는 같은 가중 파일을 쓸 때만 |
| ② | 섹션 topic마다 그 topic을 요청자에게 공개해 둔 agent를 같은 가중 파일의 점수 desc | 섹션별 recall@`per_section`, 순서 일치율(같은 가중 파일일 때만) |
| ③ CF | 요청자 `u`에 대해 `affinity[cluster(u)][cluster(owner(a))] × pop[a]`가 큰 순, 공개된 것만, 이미 대화한 것 제외(R28) | recall@10, NDCG@10 |
| ③ content | `u`의 topic 집합과 겹침이 큰 소유자의 agent — R25의 IDF·계층 감쇠(생성기는 실물 카탈로그 파일을 읽으므로 parent edge를 함께 적재한다, R26) | recall@10, 같은 군집 비율. **"content만" 단독 행**을 인기도만·CF만과 같은 표에 둔다 |
| ③ 콜드스타트 | 대화 0건인 유저에 대해 위 ③ 정답 | 같은 지표, 별도 집계 |
| 필터 | friends tier row가 친구 아닌 요청자에게 나온 건수 | **0건** (하나라도 있으면 실패) |
| 비공개 전환 | `close_rate` 이벤트 뒤 그 row가 결과에 나온 건수 | 0건 (재조회 지연 시간 안에서는 허용, 지연 시간 기록) |
| 탈퇴 | 탈퇴 유저의 agent가 결과에 나온 건수 | 0건 |

정답은 생성기가 파일로 낸다. 평가기는 **결정 로그 `ranked`(섞기 전 순서, R20)**와 이 파일만 비교한다 — 응답 본문은 구간 안에서 섞여 있어 정확도 지표의 입력이 아니다.

---

## 5. 출력 파일

디렉터리 `synthetic/<run_id>/`, 형식은 parquet(테이블)과 jsonl(이벤트 스트림). `run_id` = 파라미터 해시 + 시드.

| 파일 | 행 | 10만에서의 크기(추정) |
|---|---|---|
| `params.json` | 1 | — |
| `clusters.parquet` | K | — |
| `users.parquet` | U | `user_id, agent_id, primary_cluster, secondary_clusters, registered_at, discoverable, agent_maturity, deactivated_at` |
| `user_topics.parquet` | U × 평균 topic 수 ≈ 100만 | `user_id, topic_id, score, visibility, revision, updated_at` |
| `friends.parquet` | U × E[degree]/2 ≈ 125만(중앙값 기준)~190만(로그정규 평균 기준) | `user_low, user_high, accepted_at` |
| `conversations.parquet` | U × λ ≈ 30만 | `room_id, actor_user_id, owner_user_id, agent_id, started_at, turns, reopened` |
| `events.jsonl` | ≈ 450만~500만 건: registered 10만 + topics_updated ≈100만 + visibility 변경 신호 ≈40만(공개한 topic + 비공개 전환) + agent 공개 여부 ≈6만 + friendship ≈125만~190만 + room_created ≈30만 + message_created ≈120만(turn 평균 4) + deactivated 1천 | 시간순. 이벤트 이름과 payload는 `agent_discovery_events.md` 그대로 |
| `queries.parquet` | 2,000 | `query_id, requester, lang, text, topic_ids` |
| `truth_*.parquet` | 타입별 | §4 |
| `topic_api_stub/` | — | 재조회 목 서버가 읽는 유저별 현재 row 스냅샷 |

100만에서는 위 행 수가 10배, `events.jsonl`은 4,500만~5,000만 건 정도. 생성 시간 목표는 10만 5분 이내, 100만 1시간 이내(단일 프로세스, numpy 벡터화).

---

## 6. 검증 — 생성기 자체가 맞는지

1. **두 적재 경로의 결과 일치**: (가) 이벤트 리플레이 뒤 저장소 상태 == (나) 직접 적재 상태. row 단위 diff 0.
2. **불변식**: 저장소에 private/hidden row 없음, 탈퇴 유저 row 없음, `discoverable=false` 소유자의 row 없음. 직접 적재 (나)도 같은 조건으로 걸러 넣는다: `user_topics.parquet`에서 visibility ∈ {public, friends}이고 소유자의 `discoverable=true`이고 `deactivated_at`이 null인 행만 `visible_topic_rows`로.
3. **분포 재현**: 생성된 topic 수·degree·대화 수의 분포가 파라미터와 일치(KS 검정 또는 퍼센타일 비교).
4. **민감도**: `opener_rate`, `affinity` 노이즈, `off_cluster_topic_rate`를 ±50% 흔들어 §4 지표가 어떻게 움직이는지 표로 남긴다. 가정이 결과를 지배하는 파라미터를 알아 두어야 베타 뒤 어느 실측을 먼저 넣을지 정할 수 있다.
5. **재현성**: 같은 `params.json`과 시드로 두 번 생성해 파일 해시가 같다.

---

## 7. 열린 항목

- 유저당 topic 수, 공개 비율, 대화 빈도의 **실측**은 없다. 베타 뒤 topic-api와 bourbon-api에서 세 분포를 뽑아 §2를 갈아 끼운다.
- 한국어·영어 외 라벨(ja)은 쿼리에 쓰지 않는다. 다국어 요청자는 범위 밖.
- `entry`가 전부 `"direct"`인 세상이라 "추천이 대화를 만들었나"는 이 데이터로 잴 수 없다. 그 지표는 실서비스 로그의 몫이다.
- topic-api 목 서버의 응답 지연 시간을 실제와 얼마로 맞출지. 우선 5 ms 고정.
- **정답의 선명도** (`library_verification.md` §3-2·§5-2, 2026-09-08 실측): §2 기본값의 `affinity`와 Pareto(2) 인기도로는 정답을 전부 아는 오라클도 held-out 대화 상대를 top-10에 1.9 %만 넣는다. 방법 간 차이가 0.1 % 단위로 갈리므로 `affinity` 비대각·노이즈를 줄이거나 ③ CF 지표를 "오라클 top-10과의 겹침"으로 고정해야 한다. 어느 쪽이든 §4에 적는다.
- **대화율은 §2에서 {3, 10, 30} 세 값으로 돈다.** CF의 값이 λ=3 "인기도의 60 %"에서 λ=10 "인기도와 동률 + 군집 신호 두 배"로 바뀌었다. 오너는 실제 값이 3보다 클 것으로 본다. 실측이 오면 §8이 이 값을 대신한다.
- **친구 degree의 정의**: §2의 median 25는 유저가 고르는 수다. 무방향 대칭화 뒤 평균 degree는 약 74가 된다. 어느 쪽을 실측과 맞출지 명시한다.
- **CF 신호의 정의**: 이 문서의 대화 로그는 "시작했다"를 1로 센다. 배움이 목표인 서비스에서는 turn 수와 재방문이 더 강한 신호다. 정답 정의 §4 ③ CF는 그대로 두되(친화도가 정답), 평가되는 구현은 계약 §7 `cf_score`의 confidence 가중을 쓴다.
- **persona(HEXACO) 벡터**(R42·O20): 지금 군집은 topic 선호만 갖는다. O20이 열리면 군집마다 25 facet 평균 벡터를 두고 유저별 노이즈와 confidence·관측 수를 더해 ablation 표에 "persona만" 행을 만든다. 그 전에는 생성하지 않는다 — 구현의 `persona_similarity`가 0인 동안 정답만 있으면 표가 오해를 낳는다.

---

## 8. 실측 보정 — 파라미터를 이벤트에서 자동으로 갱신한다

§2의 값 대부분은 추정이다. 서비스가 돌기 시작하면 우리가 이미 받는 이벤트에서 같은 값을 잴 수 있으므로, **생성기 파라미터를 사람이 다시 적는 대신 주기적으로 계산해 갈아 끼우는 단계**를 둔다. 같은 계산이 CF 가중 자동 게이트(R35)의 근거도 된다.

### 8-1. 무엇을 어디서 재나

| §2 파라미터 | 재는 값 | 소스 (이미 우리 저장소에 있는 것) |
|---|---|---|
| `conversation_rate` λ | 유저별 최근 90일 대화 시작 횟수의 평균과 분포. Poisson이 맞는지는 평균/분산 비로 확인하고, 과분산이면 음이항으로 바꾼다 | `interactions` (계약 §6, `(actor_user_id, owner_user_id, room_id)`, `room_created`로 채움) |
| `revisit_rate` | 재방문은 이벤트로 받지 않는다(R46). 잴 때는 `message_created`가 마지막 turn 뒤 하루 이상 지나 같은 방에 다시 온 횟수 / 전체 대화 수 | turn 카운터의 갱신 시각 |
| `turns_per_conversation` | room당 `message_created` 수의 분포 | turn 카운터 (이벤트 정의서 §2-5) |
| `popularity_skew` | agent별 대화 시작 횟수의 순위-빈도 기울기 | 같은 테이블을 owner로 집계 |
| `topics_per_user`, `opener_rate`, `tier_mix_of_opened` | 유저별 공개된 row 수, 공개한 유저 비율, tier 비율 | `visible_topic_rows` — 단, private/hidden은 우리 저장소에 없으므로 `topics_per_user` 전체는 topic-api 내부 read로만 잴 수 있다 |
| `friend_degree`, `friend_homophily` | degree 분포 (homophily는 군집 라벨이 없어 실측 불가 — 유지) | `friends` 미러에서(R17) |
| `agent_discoverable_rule` 예외율 | discoverable인데 public row 없는 agent 비율 | `agents` × `visible_topic_rows` |
| `deactivate_rate` | 기간 내 탈퇴 / 등록 | `user_deactivated`, `user_registered` |
| `activity` (R19 갱신 비용의 입력) | `last_active_at` 기준 1·7·30일 활성 유저 비율(하루에 읽는 유저 비율이 스윕 쓰기 비용을 정한다)과 "마지막 활동 이후 경과일" 분포. TTL·스윕 상한(R36, 설정 레지스터)을 조정하는 재료 | `agents.last_active_at`, `agents.cf_candidates_computed_at` |

`affinity`, `K`, `cluster_size_alpha`, `off_cluster_topic_rate`는 잠재 구조라 직접 잴 수 없다. 대신 §6 검증 4의 민감도 표로 남기고, 실측 가능한 파라미터가 바뀐 뒤 CF 지표가 합성과 실제 로그에서 같은 방향으로 움직이는지로 간접 확인한다.

### 8-2. 두 방식 — 이벤트를 다시 읽기 vs 통계를 미리 쌓기

| | (가) 원본 이벤트를 주기적으로 다시 집계 | (나) 이벤트 도착 시 카운터를 갱신하고 주기적으로 요약 |
|---|---|---|
| 저장 | 이벤트 원본 보관 필요. 10만 유저에 450만~500만 건/90일, 이후 비례 증가 | `interactions`·turn 카운터·`popularity`는 계약 §6이 **이미** 요구하는 테이블이다. 추가는 요약 스냅샷 하나 |
| 정확도 | 어떤 통계도 사후에 새로 뽑을 수 있다 | 미리 정한 통계만. 새 통계가 필요하면 그때부터 쌓인다 |
| 비용 | 집계 배치가 이벤트 수에 비례 | 요약은 유저 수에 비례하는 GROUP BY 하나 |
| 권고 | 보조 | **기본**. 계약 §6 테이블 위에 요약만 얹는다 |

(나)를 기본으로 하고, 원본 이벤트는 worker가 받는 그대로 append-only 테이블에 남기되(`event_log`: 이벤트 이름, `occurred_at`, 페이로드 JSON — 유저가 쓴 문장·이메일은 애초에 페이로드에 없다) 보존 기간을 두어 (가)의 재집계를 가능하게 한다. `event_log`는 단건 append와 보존 기간만 있으므로 **DynamoDB에 TTL 180일**로 둔다(R18). 요약 테이블 `population_stats`와 그 입력(`interactions` 등)은 집계·조인이 있으므로 PostgreSQL이다.

### 8-3. 요약 테이블과 주기

`population_stats(snapshot_date, window_days, param, value_json)` 한 테이블. 하루 한 번 worker의 주기 작업이 `window_days=90`으로 §8-1의 값을 계산해 한 줄씩 넣는다. `value_json`은 평균 하나가 아니라 **퍼센타일(p10/p50/p90/p99)과 샘플 수**를 함께 담아, 생성기가 Poisson 대신 경험 분포를 직접 쓸 수 있게 한다. 개인 식별자는 요약에 들어가지 않는다.

같은 작업이 `params_measured.json`(§5 출력 형식의 `params.json`과 같은 스키마)을 낸다. 생성기는 `--params params_measured.json`으로 받고, 검증 프로토콜(재설계 §6)은 실측 파일로 다시 돈다. 실측이 없는 파라미터는 §2의 기본값이 남고 파일에 `source: "default"`로 표시된다.

### 8-4. 자동으로 바뀌면 안 되는 것

- **정답 정의(§4)와 시드는 파라미터가 아니다.** 보정은 §2의 값만 바꾼다.
- 한 검증 안의 모든 ablation은 **같은 `params_measured.json` 스냅샷**을 봐야 한다. 매일 갱신되는 값을 검증 도중에 바꾸지 않는다. 스냅샷 날짜를 결과에 적는다.
- 샘플이 작을 때(활성 유저 1,000명 미만 또는 대화 시작 5,000건 미만)는 파일을 내지 않고 기본값을 유지한다. 임계값은 R37(설정 레지스터 `calibration.*`).
- 우리 추천이 시작된 뒤의 로그에는 노출 편향이 있다(§7 `entry`). `entry`별로 나눠 요약하고, 생성기의 `entry="direct"` 세상에 맞추는 λ는 **`entry=direct`인 대화 시작만**으로 잰다. 추천이 만든 대화 시작은 별도 값(`conversation_rate_via_recommend`)으로 남겨 추천 효과 측정에 쓴다.
