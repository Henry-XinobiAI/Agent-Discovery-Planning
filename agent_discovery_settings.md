# 설정 레지스터 — 모든 설정값의 이름, 뜻, 올리고 내릴 때의 효과

> R54(2026-09-12, R39 개정): **값은 코드가 갖고 이 문서는 뜻을 갖는다.** 설정의 지금 값은 코드 repo의 `agent_discovery/settings.py` 하나에 있고, 이 표는 그 필드들이 무엇을 정하는지와 값을 올리고 내릴 때 서비스에 무엇이 달라지는지를 갖는다. 이름은 양쪽이 같다 — 표의 이름이 곧 그 모듈의 필드 경로다(`rank.for_you.w_cf` = `Settings().rank.for_you.w_cf`). 다른 문서(계약·재설계·walkthrough·합성 스펙)는 값을 쓰지 않고 이 문서를 가리킨다.
>
> 값의 출처가 오너 결정이면 R 번호를 적었고, 코드의 필드도 같은 출처를 갖는다. R 번호가 없는 값은 분석이 정한 초기값이라 검증(재설계 §6)에서 바뀔 수 있다 — 바뀌면 코드가 바뀌고 근거는 검증 문서에 남는다. 이 표는 뜻이 달라질 때만 고친다.

## 0. 읽는 법

| 열 | 뜻 |
|---|---|
| 이름 | 코드의 설정 이름. 점(`.`)은 그룹이고, 그룹은 `settings.py`의 중첩 클래스다 |
| 뜻 | 이 값이 무엇을 정하나. 단위는 이름이나 이 열에 있다 |
| 올리면 / 내리면 | 값을 키우거나 줄일 때 서비스에 무엇이 달라지나 — 튜닝하는 사람이 이 열만 읽고 방향을 정할 수 있어야 한다 |
| 출처 | 값을 정한 결정 또는 문서. 코드의 필드도 같은 출처를 갖는다 |

**지금 값을 보려면** 코드 repo의 `agent_discovery/settings.py`를 읽는다. 절마다 그 절에 해당하는 클래스를 제목 아래에 적어 두었다.

---

## 1. 요청 파라미터의 기본값과 상한

> 값: `agent_discovery/settings.py` — `Request` · `Explicit` · `ByTopic` · `ForYou`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `request.lang_allowed` | `lang`에 허용하는 값. topic-api 카탈로그 라벨의 언어와 같다 | 값을 더하면 그 언어의 라벨이 카탈로그에 있어야 한다(없으면 전부 폴백). 목록 밖의 값은 422 | R40 |
| `request.lang_default` | `lang`이 없을 때의 응답 언어. 응답의 다국어 필드는 이 언어의 문자열 하나 | 폴백 순서는 요청 언어 → `en` → 있는 첫 값 → null. 기본값을 바꾸면 `lang` 없는 옛 클라이언트의 라벨 언어가 바뀐다 | R40, 계약 §2-4 |
| `explicit.max_results_default` | 타입 ① `max_results`를 안 보냈을 때 쓰는 값 | 올리면 bourbon-agent 카드에 더 많은 agent가 가고 hydration 호출이 는다 | 계약 §2-1 |
| `explicit.max_results_max` | 타입 ① `max_results` 상한 | 상한을 넘긴 요청은 422 | 계약 §2-1 |
| `by_topic.per_section_default` | 타입 ② 섹션당 agent 수 | 올리면 첫 화면이 길어지고 섹션당 인덱스 조회 `limit`이 커진다 | R30 |
| `by_topic.per_section_max` | 타입 ② `per_section` 상한 | — | R30 |
| `by_topic.sections_default` | 타입 ② 첫 화면의 섹션 수 (요청자 preference 점수 상위 N topic) | 올리면 요청 하나가 topic 수만큼 인덱스 쿼리를 더 한다(섹션마다 쿼리 하나) | R30 |
| `by_topic.sections_max` | 타입 ② `sections` 상한 | — | R30 |
| `for_you.limit_default` | 타입 ③ 한 페이지 크기 | 올리면 한 페이지가 pool(`cf.pool_k`)을 빨리 소진해 R28의 "소진 뒤 재등장"이 빨리 온다 | 계약 §2-3 |
| `for_you.limit_max` | 타입 ③ `limit` 상한 | — | 계약 §2-3 (값은 분석) |
| `by_topic.page_limit_default` | 타입 ② 섹션 한 개 페이지(`/by-topic/{topic_id}`)의 `limit` 기본 | — | 계약 §2-2 |
| `by_topic.page_limit_max` | 위 `limit` 상한 | — | 계약 §2-2 (값은 분석) |
| `explicit.topic_text_max_chars` | 타입 ① `topic_text` 길이 상한 | 넘기면 422. 올리면 LLM 개념 확장 입력이 길어진다 | 계약 §2-1 |
| `explicit.context_max_chars` | 타입 ① `context` 길이 상한 | 넘기면 422 | 계약 §2-1 |
| `explicit.topic_max` | 타입 ① free text에서 뽑는 topic 수 상한. 커버리지의 분모 | 올리면 "전부 가진 agent"가 드물어져 커버리지 정렬이 성겨진다 | R03 |

## 2. 랭커 가중치

> 값: `agent_discovery/settings.py` — `Rank` · `RankExplicit` · `RankForYou`

가중치는 소스 안에서 0~1로 정규화된 feature에 곱한다. 없는 feature는 0이다(계약 §7). ①②와 ③은 가중 집합이 다르다.

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `rank.explicit.w_topic_score` | ①②의 2차 키: matched topic의 소유자 preference 강도 | 올리면 "그 topic을 강하게 가진" 소유자가 성숙도·인기도보다 앞선다. 1차 키(커버리지)는 가중과 무관 | walkthrough §3-4 예시 |
| `rank.explicit.w_topic_maturity` | ①②: matched topic 성숙도 최대 | 올리면 오래 다듬어진 topic의 agent가 앞선다. 컴포넌트 전까지 `score/100`과 같은 값이라 `w_topic_score`와 겹친다 | walkthrough §3-4 예시 |
| `rank.explicit.w_agent_maturity` | ①②: agent 성숙도 | 올리면 신규 agent가 뒤로 밀린다(콜드스타트 악화) | walkthrough §3-4 예시 |
| `rank.explicit.w_popularity` | ①②: 인기도(약한 가중) | 올리면 같은 커버리지 안에서 인기 agent가 앞선다. 크게 두면 ①②가 ③처럼 보인다 | walkthrough §3-4 예시 |
| `rank.for_you.w_popularity` | ③: 인기도 | 올리면 모두에게 비슷한 목록이 나간다(개인화 약화, 노출 편향 증가) | walkthrough §5-5 예시 |
| `rank.for_you.w_content` | ③: content 유사도(R25) | 올리면 내 topic과 겹치는 소유자가 앞선다 — "비슷한 사람" 쪽으로 기운다 | walkthrough §5-5 예시 |
| `rank.for_you.w_cf` | ③: CF 점수. **시작값 0.** `gate.*`가 올린다 | 사람이 직접 올리지 않는다(R35). 게이트가 올린 값은 결정 로그의 `implementation`(설정 해시)로 추적 | R35 |
| `rank.for_you.w_agent_maturity` | ③: agent 성숙도 | 올리면 신규 agent가 for-you에서 뒤로 밀린다. walkthrough §5-5 예시는 이 항을 0으로 두고 계산했다 | 분석 |
| `rank.for_you.w_cf_max` | 게이트가 `w_cf`를 올릴 때의 상한 | 올리면 CF가 이길 때 개인화가 강해지고, 로그가 얇은 유저에게는 노이즈가 커진다 | walkthrough §5-5 예시 |
| `rank.for_you.w_persona` | ③: `persona_similarity`(계약 §7, **R42 예약**). 요청자와 소유자의 HEXACO 성향 벡터 유사도. **시작값 0.** 입력 경로가 열리고(O20) 올리는 규칙이 정해질 때까지 0이다 | 올리면 topic이 달라도 성향이 맞는 소유자가 앞선다. 입력 경로가 없는 동안은 어떤 값이어도 효과가 없다(feature가 0). 사람이 임의로 올리는 값이 아니다 — 규칙은 O20 | R42 |
| `rank.recency_half_life_days` | `recency` feature의 반감기. 소유자의 마지막 topic 갱신이 이만큼 지나면 0.5, 그 두 배면 0.25다 (`0.5^(경과일/반감기)`) | 내리면 최근에 topic을 손본 소유자만 이 항의 값을 갖고 나머지는 빠르게 0에 수렴한다. 올리면 이 항이 거의 모두에게 1에 가까워져 `rank.w_recency`가 순서를 바꾸지 못한다. **이 행이 없으면 `rank.w_recency`는 아무 효과가 없다** — "얼마나 최근이면 1인가"를 정하지 않으면 `updated_at`을 0~1로 만들 수 없고, 코드에 반감기를 지어내면 설정의 집이 둘이 된다 | R19·R31, 값은 분석(확정은 1-9) |
| `rank.w_recency` | 모두: 소유자의 마지막 topic 갱신이 최근인가 | 올리면 오래 활동하지 않은 소유자의 agent가 더 내려간다. 하드 제외는 하지 않는다(R31) — 이 값이 그 대신이다 | R19·R31 |
| `rank.w_tier_is_friends` | 모두: 근거 row가 friends tier인가 | 올리면 친구에게만 공개한 topic으로 매칭된 agent가 앞선다. 측정 뒤 조정 | R32 |

## 3. CF (`implicit` ALS)

> 값: `agent_discovery/settings.py` — `Cf`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `cf.factors` | ALS 잠재 차원 | 올리면 희소한 로그에서 나빠진다(검증 §3: 64f가 16f보다 전부 나쁨). 유저·대화가 크게 늘면 다시 잰다 | 검증 §3, R33 |
| `cf.regularization` | ALS 정규화 | 내리면 과적합, 올리면 인기도와 같아진다 | 검증 §3 |
| `cf.iterations` | ALS 반복 수 | 올리면 fit 시간이 비례해 늘고 품질은 수렴 뒤 그대로 | `implicit` 기본값 |
| `cf.confidence_alpha` | 학습 입력 confidence `1 + α·log(1 + turns) + β·reopen_count`의 α | 올리면 긴 대화가 짧은 대화보다 훨씬 강한 신호가 된다 | 식은 R16·계약 §7 `cf_score`, 값은 분석(walkthrough §5-3 예시와 같다) |
| `cf.confidence_beta` | 위 식의 β | 올리면 다시 찾은 대화가 강한 신호가 된다 | 식은 R16, 값은 분석 |
| `cf.pool_k` | 유저별 `cf_candidates`에 저장하는 후보 수(R20의 pool) | 올리면 항목이 커지고(K가 200이면 항목 하나가 약 12~13 KB) 구간 섞기의 재료가 늘어난다. 내리면 R28의 소진이 빨라진다 | R20 |
| `cf.overfetch_factor` | tier를 모르는 소스(외부 엔진)에서 `limit`의 몇 배를 받나. 지금 구현에는 그런 소스가 없다 | 올리면 필터 뒤 부족으로 재요청하는 일이 줄고 소스 비용이 는다 | 계약 §4-2 |

## 4. CF 가중 자동 게이트 (R35)

> 값: `agent_discovery/settings.py` — `Gate`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `gate.interval_hours` | 게이트 평가 주기(전역 학습과 같은 주기) | 내리면 `w_cf`가 더 자주 움직여 목록이 흔들린다 | R35(주기적), 값은 분석 |
| `gate.holdout_ratio` | 실제 로그 leave-one-out 평가에 쓰는 유저 비율 | 올리면 판정이 안정되고 평가 시간이 는다 | 분석 |
| `gate.min_hr_ratio` | ALS의 HR@10 / 인기도의 HR@10이 이 값 이상이어야 켠다 | 올리면 CF가 더 확실히 이길 때만 켜진다(λ=10 실측이 동률 근처라 1.0이 경계) | R35, 검증 §3 |
| `gate.min_cluster_gain` | ALS의 같은 군집 비율 / 인기도의 같은 군집 비율 하한 | 올리면 "개인화가 실제로 있나"를 더 엄격히 본다(λ=10 실측 2배) | R35, 검증 §3 |
| `gate.step` | 조건을 만족할 때 `w_cf`를 올리는 폭. 만족하지 못하면 같은 폭으로 내린다(0 아래로는 안 간다) | 올리면 빨리 켜지고 빨리 꺼진다 | 분석 |

**이 표에 없는 값 셋**(1-8 구현에서 드러난 것, 코드에 있고 행이 되지 않은 이유가 각각 있다).

- **평가를 돌릴 최소 트래픽**은 `gate.*`가 아니라 `calibration.min_active_users`·`calibration.min_conversations`를 쓴다. walkthrough §8이 보정과 게이트를 **같은 하루 1회 배치**에 두고 "이보다 적으면 기본값 유지"를 한 규칙으로 말하므로, 같은 판단에 두 쌍의 숫자를 두지 않았다. 이 아래에서는 `w_cf`가 내려가지도 않는다 — "트래픽이 모자라다"와 "CF가 졌다"는 다른 사실이다.
- **`w_cf`의 상한**은 `rank.for_you.w_cf_max`(§2)다. 게이트가 그 위로 올리지 않고, 서빙이 읽을 때도 그 위의 값은 받지 않는다(손으로 고친 값이나 잘못된 쓰기가 feature 하나에 임의의 배수를 거는 것을 막는다).
- **HR@10·같은 군집 비율의 K = 10**은 코드 상수다. 이 숫자를 바꾸면 `gate.min_hr_ratio`·`gate.min_cluster_gain`이 무엇의 비율인지가 같이 바뀌므로, 설정으로 두면 임계 두 행의 뜻이 조용히 달라진다.

**`gate.min_cluster_gain`의 "같은 군집"은 실서비스에 입력이 없다** — 검증 §3-1은 합성 모집단의 persona 군집 라벨로 쟀지만, 이 서비스에는 그 라벨이 없다(R42로 persona를 읽지 않는다). 1-8 구현은 **가진 입력으로 같은 질문을 하는 대리 지표**를 쓴다: 추천된 소유자가 요청자 본인이 공개한 topic을 공개하고 있으면 "그 사람 취향 쪽"으로 센다. 요청자의 공개 row는 `visible_topic_rows`에 이미 있다(남들이 그 row로 그 사람을 찾는다) — R27이 저장하지 않는 "요청자 프로필"과는 다른 것이다.

먼저 시도했다가 버린 대리 지표도 적어 둔다. "요청자가 **이미 대화한 상대**가 공개한 topic과 겹치면"은 더 사려 깊어 보이지만 거의 아무것도 재지 못한다 — λ=10이면 이미 열 명과 대화했고 그 열 명의 topic 합집합은 그 사람이 관심 있는 것의 대부분이라, 인기도가 0.72를 받고 CF가 0.76을 받는다. 열 사람에게서 읽은 취향은 그 사람의 취향이 아니다.

**대리 지표의 눈금은 §3-1의 군집 라벨과 다르다.** persona 군집은 8개쯤의 굵은 분할이라 무작위 기저가 0.10이고 ALS가 0.27이었지만, topic 겹침은 훨씬 잘게 나뉘고 인기 소유자가 인기 topic을 갖는다 — 10만 실측에서 인기도 0.345, ALS 0.249로 **인기도가 더 높다**. 즉 `gate.min_cluster_gain`의 초기값은 지금의 대리 지표로는 넘길 수 없다. 1-9에서 이 지표를 §3-1의 군집 비율과 나란히 재고, 임계를 다시 정하거나 지표 자체를 계약에 명시하는 편이 낫다.

## 5. 인기도 (R29)

> 값: `agent_discovery/settings.py` — `Popularity`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `popularity.window_days` | 세는 기간 | 올리면 옛 인기가 오래 남는다 | R29 |
| `popularity.half_life_days` | 시간 감쇠 반감기 | 내리면 최근 며칠의 대화가 지배한다(유행에 민감) | R29 |
| `popularity.use_confidence` | 대화 시작을 1로 세지 않고 `cf.confidence_*`와 같은 식으로 가중 | 끄면 짧은 대화 여러 번이 긴 대화 한 번을 이긴다 | R29 |
| `popularity.refresh_minutes` | 워커가 `popularity` 표를 다시 만드는 주기. 한 사이클은 `interactions` ⋈ `room_turns` 집계 SQL 한 문장이다 | 내리면 새 대화가 인기도에 빨리 반영되고 그만큼 집계가 자주 돈다. 반감기가 7일이라 30분의 지연은 점수를 눈에 띄게 바꾸지 않는다 | R29, 값은 분석 |
| `popularity.new_agent_prior` | 대화 0건 agent에게 주는 사전값(정규화 뒤 0~1 기준) | 올리면 신규 agent가 인기 목록에 섞여 들어간다(콜드스타트 완화, 품질 노이즈 증가) | R29(부스트 있음), 값은 분석 |

## 6. 타입 ③ 갱신 (R19·R36)

> 값: `agent_discovery/settings.py` — `CfCandidates` · `Sweep` · `Fit`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `cf_candidates.ttl_hours` | 이 시간이 지난 항목은 "읽혔거나 활동한" 유저의 다음 스윕에서 다시 만든다. DynamoDB TTL이 아니다(항목은 지우지 않는다) | 내리면 스윕당 갱신 대상이 늘어 DynamoDB 쓰기가 는다. 올리면 새 대화가 목록에 늦게 반영된다(단, 새 대화가 있으면 TTL과 무관하게 갱신) | R36 |
| `sweep.interval_minutes` | `refresh_cf_candidates` 스윕 주기 | 내리면 돌아온 유저의 두 번째 방문이 더 빨리 새 목록을 본다. 사이클마다 PostgreSQL 조회 1회 | R36 |
| `sweep.max_users_per_cycle` | 한 스윕이 다시 만드는 유저 수 상한(`last_active_at` 내림차순) | 올리면 한 사이클의 행렬곱·쓰기가 커진다. 상한에 걸린 유저는 다음 사이클로 밀린다(조건은 그대로 참) | R36 |
| `fit.interval_hours` | `fit_cf_model` 전역 학습 주기 | 내리면 새 agent의 factor가 빨리 생긴다(그 전까지 새 agent는 CF 후보에 없다). 10만×10만에서 fit 1~2 s라 비용은 논점이 아니다 | R36 |
| `cf_candidates.stale_days` | `computed_at`이 이보다 오래되면 응답에 `degraded: ["cf_candidates_stale"]` | 내리면 오래 안 온 유저의 첫 요청이 더 자주 축소 응답으로 표시된다. 서빙 자체는 그대로 한다(R19) | R36 |

## 7. 구간 섞기 (R20)

> 값: `agent_discovery/settings.py` — `Shuffle`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `shuffle.bands` | 구간의 누적 상한. `[5, 20, 50]`이면 1~5위, 6~20위, 21~50위 안에서만 섞고 마지막 상한 뒤는 섞지 않는다 | 첫 구간을 넓히면 1위권이 더 자주 바뀐다(탐색 증가, 정확도 표시 감소). 정확도(재설계 §6-3)는 섞기 전 순서로 재므로 지표에는 영향이 없다 | R20 |

## 8. content 유사도 (R25·R26)

> 값: `agent_discovery/settings.py` — `Content` · `Catalog`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `content.decay_per_hop` | 카탈로그 계층에서 1 hop 떨어진 일치의 가중 | 올리면 넓은 상위 topic만 겹쳐도 점수가 커진다(정밀도 하락). topic-api 검색 설정과 같은 값에서 시작 | R25 |
| `content.max_hops` | 이 hop을 넘는 관계는 0 | 올리면 거의 모든 topic이 서로 관련 있게 되어 content가 인기도처럼 된다 | R25 |
| `content.idf` | 흔한 topic의 겹침을 `log(전체 소유자 수 / 그 topic을 가진 소유자 수)`로 낮춘다 | 끄면 모두가 가진 topic이 점수를 지배한다 | R25 |
| `catalog.path` | 빌드 때 topic-api repo에서 같은 경로로 복사한 카탈로그 파일. `built_at`을 결정 로그에 기록 | 파일이 바뀌면 재배포. 모르는 topic_id가 오면 정확 일치만 적용하고 `catalog.unknown_topic_count` 지표로 남긴다 | R26 |

## 9. 워커·적재

> 값: `agent_discovery/settings.py` — `Refresh` · `Attribution` · `RoomTurns` · `Friends` · `TopicApi` · `DynamoDb`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `refresh.debounce_seconds` | `topics_updated`·visibility 변경 신호(R48)를 유저 단위로 모아 재조회 1회로 만드는 대기 시간 | 올리면 topic-api 재조회 횟수가 줄고 반영이 늦어진다 | 이벤트 정의서 §2-1("수 초"), 값은 분석 |
| `refresh.debounce_max_wait_seconds` | 이벤트가 계속 와도 이 시간 안에는 한 번 재조회한다(trailing debounce의 상한) | 없으면 계속 미뤄질 수 있다. 내리면 재조회가 잦아진다 | 이벤트 정의서 §2-1 |
| `refresh.max_attempts` | 재조회 task 한 건을 몇 번까지 다시 시도하나. 시도 사이는 1·2·4·8초로 늘어나는 대기 | 올리면 topic-api가 잠깐 죽어도 이벤트를 덜 잃지만, 워커의 task 예산과 파드 종료 유예(§11)가 같이 늘어난다 | 분석(현행 `INGEST_MAX_ATTEMPTS`) |
| `refresh.attempt_timeout_seconds` | 한 번의 시도(topic-api 재조회 1회 + PostgreSQL 트랜잭션 1회) 전체에 주는 시간 | 내리면 느린 응답을 일찍 포기해 다음 시도로 넘어가고, 올리면 한 번의 시도가 예산을 더 먹는다. **워커의 topic-api 호출은 재시도를 하지 않으므로**(1-4c에서 정함 — 사다리는 이 표의 것 하나뿐이다) 한 번의 시도는 `topic_api.timeout_ms` 1회 + 트랜잭션 1회이고, 초기값은 그 둘에 여유가 있게 잡았다 | 분석(현행 `INGEST_TIMEOUT_SECONDS`) |
| `attribution.window_hours` | 클라이언트의 어트리뷰션 보고(계약 §2-5)와 대화의 첫 메시지를 같은 `(actor, owner)` 쌍으로 잇는 최대 간격 | 늘리면 오래된 카드에서 시작한 대화도 추천으로 잡히고, 줄이면 늦게 연 대화가 `direct`가 된다 | R47, 값은 분석 |
| `attribution.predicted_room_ttl_hours` | 추천으로 나간 카드의 예측 room id를 얼마나 들고 있나(R51) | 올리면 늦게 시작된 대화도 소유자를 찾지만 항목이 오래 남는다. 내리면 그 밖에서 시작된 대화는 기록되지 않는다 — `attribution.window_hours`보다 짧으면 보고는 있는데 소유자를 모르는 방이 생긴다 |
| `room_turns.orphan_ttl_days` | `interactions` 행이 없는 `room_turns`(우리 서비스 이전에 열린 방, 놓친 시작)를 정리하기까지의 기간 | 짧으면 우리가 예측하지 않은 방의 turn을 일찍 잃고, 길면 고아 행이 쌓인다 | R49, 값은 분석 |
| `friends.tombstone_ttl_days` | 끊긴 친구관계를 이벤트 순서 비교용으로 얼마나 더 들고 있나(R50) | 올리면 뒤늦게 재발행된 옛 `accepted`도 계속 걸러낸다. 내리면 그 창 밖의 옛 이벤트가 친구관계를 되살린다. 스윕은 다른 보존 항목들과 함께 뒤에 온다 — 그때까지 tombstone은 쌓이기만 한다 |
| `topic_api.timeout_ms` | 재조회·요청자 프로필(R27)·hydration 호출 한 번의 타임아웃(시도 1회, 재시도는 `TOPIC_API_MAX_ATTEMPTS`) | 내리면 `hydration_partial`이 늘고 p95가 짧아진다. 초기값은 현행 서비스의 값이고, 실측(1-9) 전에 줄이면 근거 없이 사용자 경로를 조이는 셈이라 그대로 둔다. 1-4c에서 다시 봤고 이 값은 그대로 둔다 — 재조회를 워커가 하게 되면서 이 타임아웃 × 시도 수가 `refresh.attempt_timeout_seconds` 안에 들어가야 했는데, 사용자 경로의 이 값을 조이는 대신 **워커 쪽 시도 수를 1로 두어** 사다리를 하나로 만들었다(중첩 재시도는 느린 upstream의 부하를 두 수의 곱만큼 늘린다). `TOPIC_API_MAX_ATTEMPTS`는 API 프로세스의 것으로 남는다 | 분석(현행 `TOPIC_API_TIMEOUT_SECONDS`), 확정은 검증 1-9 |
| `dynamodb.table_name` | 서비스 소유 테이블 하나(R44). key space는 계약 §6-1. **이름은 환경마다 다르므로 값의 집이 배포 표면이다** — `config.py`의 `StorageSettings.DYNAMODB_TABLE_NAME`이고 매니페스트가 고정한다 | — | R44 |
| `dynamodb.log_shards` | 결정 로그 GSI 파티션 키와 `event_log` 파티션 키의 shard 수(`hash(id) % N`) | 올리면 하루치 쓰기가 더 넓게 퍼지고 읽기가 N개 Query를 병합한다. 늘려도 옛 항목은 이동하지 않는다(옛 shard < 새 N). 내리지 않는다 — 내리면 읽기가 옛 shard를 훑지 않는다 | R44, 값은 분석 |

## 10. 실측 보정 (R37) 과 보존

> 값: `agent_discovery/settings.py` — `Calibration` · `EventLog` · `DecisionLog`

| 이름 | 뜻 | 올리면 / 내리면 | 출처 |
|---|---|---|---|
| `calibration.interval_hours` | `population_stats`·`params_measured.json` 갱신 주기 | — | R37 |
| `calibration.window_days` | 분포를 재는 창 | 올리면 옛 분포가 섞이고 샘플이 늘어 안정적이다 | R37 |
| `calibration.min_active_users` | 이보다 적으면 파일을 내지 않고 기본값 유지 | 올리면 실측 전환이 늦어진다 | R37 |
| `calibration.min_conversations` | 창 안 대화 시작 수 하한(같은 규칙) | — | R37 |
| `event_log.ttl_days` | DynamoDB `event_log` 보존(이벤트 리플레이·보정용) | 올리면 저장 비용이 비례해 는다 | R18·R37 |
| `decision_log.ttl_days` | 결정 로그 보존 | 오프라인 평가 기간보다 짧으면 정답 로그가 사라진다. 보정 창(`calibration.window_days`)의 4배로 시작 | 계약 §8, 값은 분석 |

## 11. 코드와의 관계

- 설정 클래스는 하나(`agent_discovery/settings.py`)이고 이 표의 그룹이 중첩 필드가 된다. **값은 그쪽에 있고 이 표에는 없다**(R54). 필드마다 설명과 출처가 있어야 하고, 그 규칙은 코드 쪽 테스트가 지킨다 — 이 문서를 읽는 테스트는 없다.
- 표와 코드의 설명이 다르면, 뜻은 이 표가 맞고 값은 코드가 맞다. 이름이 갈라지면 알려 주는 것이 없으므로 이름을 바꿀 때는 양쪽을 같이 고친다.
- 게이트가 바꾸는 값(`rank.for_you.w_cf`)만 런타임에 움직인다. 나머지는 배포 시점 값이다. `rank.for_you.w_persona`는 O20이 규칙을 정하기 전까지 0으로 고정된 예약 자리다(R42).
- 워커의 task 예산은 이 표에서 계산한다: 최악의 재조회 한 건 = `refresh.max_attempts` × `refresh.attempt_timeout_seconds` + 시도 사이 대기의 합. 여기서 deferq의 task 타임아웃·드레인·파드 종료 유예가 차례로 나오므로(`worker/budget.py`), 위 두 값을 고치면 배포 매니페스트의 `terminationGracePeriodSeconds`도 같이 움직인다.
- 결정 로그의 `implementation`은 이 설정의 해시를 포함해, 어느 값으로 답했는지 나중에 알 수 있게 한다(계약 §8).
