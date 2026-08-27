# facets 소유권 분리 — 논의 기록 (rev 2, 2026-08-27)

> **문서 지위: 결정이 아니다.** 2026-08-26 대화에서 나온 구조 아이디어와, 그 판단에 필요한
> **검증된 사실**을 임시로 모아 둔 것이다. 어떤 항목도 확정이 아니고 어떤 코드도 이 문서를 근거로
> 바뀌지 않았다. **설계 정본은 `recommendation_pipeline_design.md` rev 5.8**이며, 이 문서가 정본과
> 어긋나면 정본이 맞다. 논의 후 결정이 생기면 그때 정본 §S3·§S4·§9(열린 결정)로 올리고 이 문서는
> 그 결정을 가리키는 기록으로 남긴다.
>
> **표기**: `사실`(상류 소스에서 `file:line`으로 확인) · `판단`(이 문서의 의견) · `열린 항목`(협의·측정 대기).
> 사실과 판단을 섞어 쓰지 않는다 — 이 문서의 유일한 지속 가치는 앞의 것이다.
>
> **자매 문서**: `service_boundary_discussion.md`(rev 1) — 같은 경계의 다른 절반이다. 이 문서는
> **지표 값을 누가 소유·저장·전달하는가**를 다루고, 그쪽은 **그 값으로 순위를 매기는 정책과 자연어
> 해석을 누가 갖는가**를 다룬다. 두 질문은 독립이다(그쪽 §4-2 표) — 값이 어디서 오든 정책은 소비자
> 쪽이고, 정책이 소비자 쪽이라는 것이 값도 소비자가 소유해야 한다는 뜻은 아니다.

---

## §1 논의된 아이디어

topic-api에서 **scoring을 읽기 경로에서 떼어내는** 구조.

- **topic-api** — 카탈로그 그래프 + grounding(이름→topic) + **멤버십·visibility**
  (누가 이 topic을 갖고 있고, 요청자가 봐도 되는가)
- **facet producer** — `(user, topic)`별 facets/성숙도를 **자기 DynamoDB에 직접 write하고 소유**
- **agent-discovery** — 둘을 **join**하고 **ordering을 소유**

즉 `score_detail`(그리고 §5의 이유로 `score`까지)이 topic-api에서 빠지고, agent-discovery는
producer 테이블에 **읽기 권한만** 갖는다. visibility는 계속 topic-api에서 온다.

---

## §2 사실 — 상류에서 확인한 것

이 절이 이 문서의 본체다. 판단이 바뀌어도 여기는 남는다.
(모든 인용은 `bourbon-topic-api` HEAD `9ee67f3` 기준, 2026-08-26 확인)

### 2-1 `사실` facets는 **이미** topic-api 밖에서 계산된다

`Facets`(`topic/structs.py:51-58`)는 knowledge·engagement·affinity·duration·recency 다섯 개이고 **전부
nullable**이다. `Relation`(`:61-66`)은 exact·ancestor·related 세 값.

- `api/routers/internal/users/router.py:85-92` — `PUT /internal/users/{user_id}/topics/{topic_id}/score`가
  `score` + `score_detail`을 **주입받는다**. 같은 파일 `:96-114`에 유저 단위 bulk 주입(`POST /{user_id}/scores`).
- `topic/structs.py:69-85` `ScoreDetail` docstring — "these come from **the producing pipeline**,
  and a user write must not be able to carry one."
- `topic/persona_topics/scoring.py:18` `topic_score(facets, confidence)`는 주어진 facets로 score를
  **재계산해 검증**하는 용도다(계산 원천이 아니다).

→ **"다른 컴포넌트가 계산한다"는 이미 현실이다.** 논의의 실제 내용은 *계산 위치*가 아니라
**저장 위치와 읽기 경로**다.

### 2-2 `사실` 저장 스키마 (`topic/connectors/dynamodb/keys.py`)

```
user topic table   PK  USER#{user_id}        SK  TOPIC#{topic_id}
  rank index (GSI)     rank_key = {topic_id}#{visibility}#{shard}    SK = score (N)
  holder index (GSI)   SK, PK
```

세 가지가 설계 판단으로 명시돼 있다.

- **sparse index로 tier 경계를 만든다** — `rank_key` docstring: "a secondary index holds an item
  exactly when both of its key attributes are present, so leaving this off is what keeps an unranked
  tier out of the index." 즉 **인덱스 멤버십 == tier 경계**이고 쓰기와 원자적이다.
- **shard 세그먼트를 값 0으로 미리 넣어 뒀다** — `SOLE_SHARD = 0`: "The key format carries the segment
  so that widening it later replaces this constant's use rather than the stored format; until a
  per-topic shard count exists, **this is the one place that assumption lives**."
- `put_score`는 **`rank_key`를 건드리지 않는다**(`topic/storage/user_topics.py:349-372`) —
  "injection does not decide tiers, and a private item is not in the ranking index at all."
  첫 쓰기의 visibility 기본값은 **private**.

### 2-3 `사실` `/topics/{id}/users`는 두 갈래이고 비용 차가 크다

`topic/search/service.py:96-118`이 갈림길이다. `weights = SEARCH_DEFAULT_DECAY ** distance`
(`config.py:136`, 기본 `0.6`)를 subtree에 대해 만든 뒤:

- **`len(weights) == 1`**(활성 자손 없음) → `_rank_single`
  `topic/search/single.py:44-48` — "**Two reads, not one per row**: the index answers who and how much,
  and a single batch fills in what the index does not carry." GSI Query 1 + `BatchGetItem` 1.
  `single.py:89-90`에서 `exhaustive=True`·`truncated_descendants=0`을 **하드코딩**한다.
- **그 외** → `_rank_rollup`(`service.py:222-278`)
  - subtree topic **하나당 `TopicIndexStream`**, page_size = `limit × 4`(`service.py:46`)
  - `top_k` threshold 알고리즘이 후보 유저마다 **`list_for_user(user_id)`로 그 유저의 topic 파티션
    전체를 읽는다**(`service.py:238-247`, `storage/user_topics.py:92`), 동시성 16(`service.py:42`)
  - 예산(`config.py:139-142`): `SEARCH_MAX_DESCENDANTS=50` · `SEARCH_MAX_DEPTH=3` ·
    `SEARCH_MAX_GSI_ITEMS=20_000` · `SEARCH_MAX_USER_QUERIES=2_000`

→ 한 번의 호출이 **최악 51 스트림 + 2,000 per-user 파티션 읽기**다. `exhaustive=false`·
`descendants_dropped`가 존재하는 이유가 이것이다. 단 **이 숫자는 예산(상한)이지 실측이 아니다.**

`판단` **비싼 부분은 "정확한 score 정렬 top-k를 증명하는 것"이다.** 정렬이 우리 몫이 되면
그 threshold walk 전부가 불필요해진다.

`열린 항목` **우리 요청이 두 갈래 중 어디로 가는지도 아직 모른다.** curated Wikidata 트리에서
"coffee" 같은 개념은 자손을 가질 것 같지만, 확정 topic의 자손 유무 분포를 잰 적이 없다 — §7-1에
이것을 함께 넣어야 한다(자손 없는 topic만 온다면 지금 경로가 이미 왕복 2회이고
이 논의 전체의 동기가 약해진다).

### 2-4 `사실` id-only 멤버십 primitive는 있지만 route가 아니다

`topic/storage/user_topics.py:172-195` `holders_of(topic_id, limit, start_key)`:

- "Everyone holding *topic_id*, **at any tier**" — tier 필터가 없고 **visibility를 돌려주지도 않는다**
- **정렬이 없다** (holder index 키에 score가 없다)
- 호출자는 `topic/user_topics/migration.py:178`의 sweep **하나뿐**이고, 어떤 route에도 노출돼 있지 않다

→ "topic별 `(user_id, visibility)` 목록"은 **오늘의 계약에 없다.** 이 구조를 하려면 **새 route**가 필요하다.
그리고 랭킹 route와 달리 이 인덱스는 `private`까지 포함하므로, 새 route는 tier 필터를 가져야 한다.

### 2-5 `사실` 우리는 그들의 `score`도 `score_detail`도 쓰지 않는다

- S4 RRF는 **rank만** 읽고 scalar score는 wire에도 나가지 않는다
  (구현 계획 §9 9행·13행, 정본 §S4-1·§S5).
- `score_detail`은 도메인에서 **불투명 dict이고 읽는 코드가 없다** — facets 계약이 열려 있어서다
  (`topic_api_analysis.md` §11-18, B2). S5 기본 `RrfOrdering`은 facet 이름을 하나도 읽지 않는다.

→ **facets를 topic-api가 안 주는 것 자체는 오늘 우리에게 손실이 0이다.**

### 2-6 `사실` 우리 쪽 timeout·재시도

`bourbon-agent-discovery-api/agent_discovery/config.py:59-60` —
`TOPIC_API_TIMEOUT_SECONDS = 3.0`(attempt 단위) · `TOPIC_API_MAX_ATTEMPTS = 3`.
transport는 timeout을 **재시도한다**.

`판단` 2-3의 rollup이 3s를 넘으면 우리가 **같은 비싼 쿼리를 3번** 던져 느린 상류에 부하를 3배로 얹는다.
S3에 대해서는 재시도를 1회로 줄이는 것이 맞아 보인다 — 이 문서의 결론과 **독립적으로** 성립하는 항목.

---

## §3 `판단` 이 구조가 해소하는 것 / 새로 여는 것

### 3-1 privacy 반론이 해소된다

별도 저장소로 랭킹을 빼는 안(=projection이 멤버십까지 갖는 안)의 치명적 문제는
**visibility 전파 지연이 유출 창**이라는 것이었다. 이 구조에서는 성립하지 않는다:
**인가 판단이 topic-api에 남고, producer 테이블은 권한의 원천이 아니라 enrichment**다.
유저가 private으로 바꾸면 topic-api가 그 `user_id`를 주지 않고, 우리는 그 사람의 facets를
**조회할 이유 자체가 없다.** facets 테이블이 낡아 있어도 유출 경로가 아니다.

**단 조건이 붙는다**(§6-3): 이 성질은 "우리 코드가 **항상 topic-api 목록에서 출발해** join한다"에
걸려 있다. facets 테이블을 topic 단독으로 순회하는 코드가 하나 생기면 게이트가 우회된다.

### 3-2 B2(facets 계약)가 열린다

facets를 우리가 직접 읽으면 `topic_api_analysis.md` §11-18 / B2가 풀리고, S5의
`OrderingStrategy` 슬롯이 실제로 채워질 수 있다(expertise 키 식을 우리가 정의).
**성능보다 이쪽이 이 방향의 강한 근거다.**

### 3-3 topic-api 쪽이 싸진다

2-3의 `판단`대로, 그들에게 남는 것이 멤버십뿐이면 threshold walk가 사라진다.

---

## §4 `판단` 하나 남는 어려운 문제 — 읽기를 어떻게 유계로 만드나

**읽기를 자르려면 순서가 필요하고, 순서는 score에 있고, tier 필터는 topic-api에 있다.**
topic-api는 **visibility를 파티션 키에 넣어**(2-2) 이 문제를 피했다 — 정렬과 인가가 같은 인덱스에
있으니 top-N이 곧 "보여줄 수 있는 top-N"이다. 둘을 쪼개면 그 성질이 깨진다.

| 모양 | 성립? | 이유 |
|---|---|---|
| ⓐ 멤버십 먼저 → 그 쌍들의 facets | ✗ | **자를 기준이 없다.** holder index는 무순서(2-4)라 `Limit`은 의미 없는 부분집합을 준다 |
| ⓑ facets 테이블에 tier를 넣는다 | ✗ | 인가가 두 곳이 된다 — §3-1의 유일한 안전 성질을 잃는다 |
| ⓒ **rank-then-authorize** | ○ | producer 인덱스에서 top-K를 먼저 읽고, 그 K개 `user_id`만 topic-api에 **일괄 인가 확인**. 확인은 `(user, topic)` 키 BatchGet이라 유계·저렴 |

ⓒ의 대가는 **under-fill**이다 — top-K 중 다수가 볼 수 없는 사람이면 결과가 모자란다.
K에 배수 + 한 라운드 추가로 관리 가능하고, **under-fill률 자체가 측정 대상**이다.
ⓒ에서 per-user 파티션 읽기는 0이 된다.

---

## §5 `판단` 키 설계 초안 (producer 테이블)

접근 패턴을 먼저 고정하고 거기서 유도한 것.

| | 무엇을 | 필요한 키 |
|---|---|---|
| **R1** | topic T의 상위 K명 (ⓒ의 앞단) | topic 파티션 + **score 정렬** |
| **R2** | 이미 아는 `(topic, user)` 쌍들의 facets | `(user, topic)` point get |
| **R3** | 한 유저의 전 topic (producer·persona 쪽) | user 파티션 |
| **W** | `(user, topic)` upsert · 한 유저 batch | user 파티션 |

```
Table: <producer>_user_topic_facets        (producer 소유 · agent-discovery는 read-only)

  PK   USER#{user_id}
  SK   TOPIC#{topic_id}

  score        N   producer의 스칼라 (facets에서 계산)
  facets       M   knowledge·engagement·affinity·duration·recency (전부 nullable — 상류 `Facets`와 같은 모양)
  confidence   N
  relation     S   exact | ancestor | related — topic이 그것을 만든 증거와 어떤 관계인가
  updated_at   S   ISO8601 — join의 staleness 신호
  rank_pk      S   "{topic_id}#{shard}"   ← rankable할 때만 쓴다 (sparse)

GSI: topic-rank
  PK   rank_pk           SK  score (N, ScanIndexForward=False)
  projection  INCLUDE [facets, confidence, relation, updated_at]
```

판단이 갈리는 곳만 근거를 적는다.

1. **score는 base SK가 아니라 GSI SK에 둔다.** `PK=TOPIC#, SK={score}#{user_id}`면 R1이 base 쿼리
   한 방이 되지만 score가 바뀔 때마다 **delete+put**이고(SK 변경) 원자적이지 않으며 옛 score를
   알아야 한다. R2도 불가능해진다. **GSI SK는 base item을 update하면 DynamoDB가 옮겨 준다** —
   가변 값을 정렬 키에 두는 문제가 GSI에서는 생기지 않는다. base를 `(USER, TOPIC)`으로 두는
   결정적 이유.
2. **`rank_pk`를 sparse로.** 2-2의 기법을 그대로 쓴다 — 속성을 안 쓰면 인덱스에 없다. score 0이나
   confidence 바닥을 **삭제 없이** 랭킹에서 빼는 방법이고, "랭킹 대상인가"의 결정권이 producer에 남는다.
   (topic-api도 score 0을 만나면 walk를 끝낸다 — 0은 결과가 아니라는 같은 판단.)
3. **`#{shard}`를 첫날부터 0으로.** 근거는 2-2의 `SOLE_SHARD` 주석 그대로 — 나중에 넣으면 인덱스
   전체 재작성이다. **단 샤드 함수는 `user_id` 기준**이어야 한다(topic 기준은 인기 topic의 쓰기 편중을
   전혀 못 나눈다). 그 순간 R1은 **S개 쿼리 + 머지**가 되니, S=1이어도 리더는 "S개 스트림을 머지하는
   함수" 모양으로 둔다(topic-api `TopicIndexStream`이 그 모양).
4. **projection은 `INCLUDE`.** facets가 작으니(정수 5개+2) 인덱스에 실으면 **R1이 왕복 1회**로 끝난다 —
   지금 topic-api가 왕복 2회인 이유(2-3의 `single.py:44-48`)가 사라지는 유일한 지점. `ALL`이 아닌 이유는
   producer가 큰 필드를 더할 때 쓰기 증폭이 조용히 따라오지 않게 + "읽기 경로가 필요한 것"이 목록으로
   드러나게.
5. **visibility는 넣지 않는다.** §3-1·§4-ⓑ.
6. **v1에 rollup 행을 만들지 않는다.** 넣으려면 `SK=ROLLUP#{topic_id}` 같은 두 번째 종류가 필요하고
   (R2는 정확한 행을, R1은 합산 행을 원한다), **producer가 카탈로그 그래프를 알아야** 하고 카탈로그
   배포마다 재빌드가 생긴다. 대신 discovery가 subtree fan-out을 하면 그래프는 topic-api에 남고
   **카탈로그 변경이 즉시 정확**하다(지금 그들이 읽기 시점에 계산하는 이유와 같다). 위 모양은 rollup을
   나중에 **additive**하게 얹을 수 있다.
7. **키 모듈 규율을 그대로 가져온다** — `topic/connectors/dynamodb/keys.py`처럼 한 모듈이 모든 키를
   만들고 prefix를 소유하고 세그먼트의 구분자를 거절한다. 소비자가 둘 이상인 테이블이면 더 필요하다.

### 5-1 이 스키마가 강제하는 결정: `score`도 함께 옮겨야 한다

GSI SK에 score가 없으면 R1이 성립하지 않고, 그러면 §4의 ⓐ밖에 남지 않는다.
그리고 그게 오히려 일관된다 — `ScoreDetail`을 score 옆에 둔 설계 의도가 "짝이 안 맞으면 **보인다**"
(2-1)였으니, 둘을 갈라 두면 topic-api에 **입력이 사라진 score**가 남고 아무도 검증할 수 없다.
둘을 함께 옮기면 topic-api는 **카탈로그 + 멤버십 + visibility**만 갖고, 그 랭킹 route는 멤버십 route가
된다. **즉 이 키 설계를 고르는 것이 곧 그 소유권 결정을 고르는 것이다.**

`열린 항목` 그들의 공개 `/search/users`는 여전히 랭킹이 필요하다 — **우리 편의로 그들 기능을 지우는
것이 아닌지**가 협의 항목이다.

---

## §6 `판단` 명시적으로 잃거나 옮겨오는 것

1. **score ↔ 입력의 검증 가능성** — §5-1. `score_detail`만 빼면 사라진다.
2. **rollup 의미가 우리 것이 된다** — decay 0.6 · depth 3 · 다중 부모 처리를 우리가 정의한다.
   **정본 §S3·§S4 계약 변경**이고 최적화가 아니다.
3. **안전 성질이 join 방향에 걸린다** — §3-1의 조건. 이 repo 규율대로면 문서가 아니라 **구조로 강제**해야
   한다(예: facets 포트가 `(user_id, topic_id)` **쌍 목록만** 받고 topic 단독 조회를 제공하지 않는 형태).
   그리고 IAM은 여전히 "볼 수 없는 사람의 성숙도까지 읽을 수 있는" 상태라 least-privilege 관점의 별도 항목이다.
4. **staleness가 관측 대상이 된다** — 두 저장소를 join하니 "멤버인데 facets 행 없음"과 "facets가 낡음"이
   생긴다. 전자는 기존 판단을 그대로 쓴다(`evidence=None`처럼 **없는 근거에 0을 채우지 않는다**).
   후자는 `updated_at`이 있어야 구별된다.
5. **`relation` vs 우리 `distance`** — subtree fan-out을 하면 distance를 그래프에서 직접 계산하는데
   producer의 `relation`(exact·ancestor·related)도 같은 축을 말한다. **같은 것을 두 곳에서 판정**하게
   되니(구현 계획 §10-19에서 probe `lang`을 지운 것과 같은 종류) 어느 쪽이 진실인지 미리 정해야 한다.

---

## §7 열린 항목과 착수 자격

### 7-1 이 방향을 시작할 자격을 주는 것

**측정값 셋이다.** 지금 전부 없다(셋째는 계측 자체가 없다).

- S3 지연(`retrieval.completed`의 `elapsed_ms`)
- `exhaustive=false` 발생률 = "rollup이 예산에 닿는가"
- **확정 topic의 자손 유무 분포** = "우리 요청이 두 갈래 중 어디로 가는가"(2-3의 `열린 항목`) —
  이건 지금 계측에 없다

계측은 코드에 들어가 있으나(`bourbon-agent-discovery-api` PR 3) **실행 이력이 없고**, 카탈로그 규모도
작아서 2-3의 예산은 **상한이지 실측이 아니다**. §11 평가 트랙에서 tool loop를 두고 정한 규율
("계측이 유일한 블로커, 계측 없이 아키텍처를 바꾸지 않는다")을 여기에도 같게 적용한다.

### 7-2 협의가 필요한 항목

| # | 항목 | 상대 |
|---|---|---|
| F1 | `score_detail`만 옮기나, **`score`까지** 옮기나 (§5-1) | topic-api · producer |
| F2 | 멤버십 route의 모양 — tier 포함 `(user_id, visibility)` + **일괄 인가 확인**(§4-ⓒ) | topic-api |
| F3 | rollup 소유자 — producer 사전 계산 vs discovery fan-out (§5-6) | 3자 |
| F4 | 그들 공개 `/search/users`의 랭킹 유지 방식 (§5-1 열린 항목) | topic-api |
| F5 | facets 테이블 IAM 범위와 join 방향 강제 (§6-3) | producer · 우리 |

### 7-3 이 문서와 독립적으로 성립하는 것

결론이 어느 쪽이든 하는 것이 낫다고 보는 항목 — **여기에 묶지 않는다**.

- **S3 캐시**(우리 repo, `(topic_id, tiers)` 짧은 TTL) — 지금 캐시는 S2(probe→topics)에만 있고
  **비싼 쪽인 S3에는 없다**. 인기 topic의 rollup 반복이 사라진다. 되돌리기 쉽다.
- **S3 재시도 1회** — 2-6.
- **"근사 top-N으로 충분한가"를 topic-api에 묻기** — 2-5대로 우리는 정확한 score를 버리고 rank만 쓴다.
  예산을 낮춘 모드가 있으면 이 구조 없이도 크게 싸진다. 네 항목 중 **가장 값싼 구조 변경**.

### 7-4 답이 뒤집히는 조건

**Push 모드 / Open Beta.** 요청당 ≤3 topic이 아니라 "유저마다 상시 후보 생성"이 되면 per-request
rollup은 어떻게 튜닝해도 안 맞고, 그때는 이 구조가 아니라 **discovery가 소유하는 read model**
(우리 ordering으로 미리 계산)이 맞다 — "남의 테이블 직접 읽기"가 아니라 **이벤트로 받아 우리가 물리는**
것이고, 그러면 staleness·privacy 전파가 명시적으로 우리 책임이 된다.

---

## §8 이 문서가 하지 않은 것

- 코드 변경 **없음**. `bourbon-agent-discovery-api`의 PR 3(T3·T4·T5)은 이 논의와 **독립**이다.
- 정본(`recommendation_pipeline_design.md`) 변경 **없음**. §6-2의 계약 변경은 결정 후에 올린다.
- `topic_api_analysis.md` §11(열린 질문) 갱신 **없음** — F1–F5가 확정 요청이 되면 그때 그쪽 레지스터로.
- producer·topic-api 어느 팀에도 **발신하지 않았다**.

## 변경 이력

- **2026-08-26 rev 1** — 신설. 2026-08-26 대화(facets 소유권 분리)의 사실·판단·열린 항목을 임시 기록.
  §2는 `bourbon-topic-api` HEAD `9ee67f3`에서 `file:line`으로 확인한 것이고, 대화 중 **내가 두 번 틀렸다가
  코드를 더 읽고 정정한 지점**이 두 곳 있다: ⑴ `/topics/{id}/users`를 "왕복 2회"로 단정했는데 자손이 있으면
  `_rank_rollup`(2-3)이다 ⑵ "leaf면 완전성 플래그가 항상 0이라 우리 fail-closed가 발화 불가"라고 판단했는데
  `service.py:116`이 `_rank_single` 결과에 walk 예산 초과(`truncated`)를 덮어쓰므로 발화한다.
  ★**남의 서비스 비용을 추정할 때는 route → dispatch → 저장 계층까지 따라 읽는다** — 진입점 docstring만
  읽으면 두 갈래 중 싼 쪽을 전체로 착각한다.
- **2026-08-27 rev 2** — 자매 문서 `service_boundary_discussion.md`(rev 1) 상호 참조 추가. 내용 변경은
  없다. 추가한 이유는 그 문서 §4-2에서 이 경계가 **값의 소유**와 **순위 정책의 소유** 둘로 갈리는데,
  링크가 한 방향뿐이면 이 문서가 경계 전체를 소유하는 것처럼 읽히기 때문이다.
