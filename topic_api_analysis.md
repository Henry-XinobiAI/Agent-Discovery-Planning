# bourbon-topic-api 분석과 Discovery 방향 재정립

> **문서 지위**: 분석 기록 + 방향 결정 기록. **설계 문서가 아니다.**
> 이 문서는 `persona_topic_search_design.md`(rev 14)를 대체하기 위한 **재설계의 입력**이며,
> 재설계 결과가 나오면 그 문서가 새 정본이 된다.
>
> **작성 근거**: 2026-08-21, `../bourbon-topic-api`(HEAD `296723d`) 전수 읽기 + 테스트 실행 +
> 카탈로그 시드 실측. 대조 대상은 `../../iac`(origin/main `d364d3c`),
> `../bourbon-api`(origin/main `943b5f5`), `../bourbon-agent`(HEAD `18fbcac`).
>
> **표기 규율**: 모든 주장에 `검증됨`(코드/실측) · `가정`(명시된 추정) · `미확인`(확인 필요) 중
> 하나가 붙는다. 숫자는 전부 실측이며, 재현 방법은 부록 B에 있다.
> 추정을 실측으로 제시하지 않는다 — 이 문서 작성 중 그 실수를 한 번 했고 §2의 표가 그 교정 결과다.

---

## §0 한 페이지 요약

**무엇을 발견했나.** `bourbon-topic-api`는 이미 구현된 독립 마이크로서비스다. 큐레이션된
Wikidata 기반 토픽 카탈로그(2,605개)와 유저별 토픽 점수를 DynamoDB 2테이블에 두고,
"토픽 → 그 토픽을 가진 유저 랭킹"을 답한다. **OpenSearch를 쓰지 않는다.**

**우리 rev 14와의 관계.** rev 14는 "extractor가 bourbon-agent 안에 있고, 우리가 전용 테이블에
topic/claim을 소유하며, DynamoDB Streams로 AOSS에 색인하고, 요청마다 LLM으로 relevance를
판정한다"는 그림이었다. 그 전제 중 **어느 것도 현실과 맞지 않는다.** 저장·색인·판정의 주체가
topic-api로 옮겨갔다.

**확정된 방향.** topic-api를 **축(axis)** 으로 삼는다. 폐기가 아니라 **축의 이전**이다.
rev 14에서 저장소·색인·스트림·동시성 계약은 폐기하고, 규율(실패 의미, gate 직교성,
self-exclusion, 판정 입력 비신뢰)과 얇은 보정층(ordering 키, rerank)만 승계한다.
**병렬로 두 시스템을 굴리는 것은 금지한다.**

**가장 큰 리스크는 품질이 아니라 데이터다.** 프라이버시 정책상 유저 토픽은 private이 기본이고
유저가 직접 public으로 올려야 한다. 랭킹은 public 파티션만 읽는다. 따라서
`서빙 가능성 = 카탈로그 커버리지 × 공개 밀도`이고, **두 번째 항이 현재 0이다.**

**재설계가 답해야 하는 것**은 §13에 목록으로 있다.

---

## §1 bourbon-topic-api는 무엇인가 (검증됨)

### 1.1 정체와 스택

| 항목 | 내용 |
|---|---|
| 형태 | 독립 마이크로서비스. bourbon 호스트 `/api/svc/topic/` 뒤, edge-auth 사이드카 경유 |
| 스택 | FastAPI + DynamoDB(2테이블) + uv + structlog. **Python `>=3.14,<3.15`** |
| 문법 | PEP 758(`except A, B:` 괄호 없는 다중 예외) 실사용 — **3.13에서는 컴파일 실패** |
| 인증 | 코드 0줄. `bourbon.xinobi.ai/edge-auth` 라벨이 붙은 파드의 사이드카가 토큰 검증 후 `x-user-id` 주입, `Authorization`/`Cookie` 제거 |
| 규모 | Python ~11k줄 |
| 테스트 | **922 passed / 62 skipped / 1 failed**. 유일한 실패는 `tests/test_env.py`가 `LOG_LEVEL` 환경변수를 요구하는 것(`.env` 미생성). skip 62개는 DynamoDB 로컬 엔드포인트 미설정 |

`AWS_REGION`은 configmap에 고정(`ap-northeast-1`). botocore가 기본값을 갖지 않아 누락 시
클라이언트 생성 단계에서 `NoRegionError`로 죽는다.

### 1.2 두 워크로드

`SERVICE_ROLE`이 프로세스에 존재하는 라우터 집합을 결정한다(`api/depends/role.py`).

| 역할 | prefix | edge-auth | 게이트웨이 라우트 | 서비스 |
|---|---|---|---|---|
| `public` | `/api/svc/topic` | 있음 | 필요 | 읽기 7개 라우트 |
| `internal` | `/internal/topic` | **없음** | 없음 | score 주입 · 카탈로그 관리 · 공개 읽기 미러 |

쓰기 라우트는 public 워크로드에 **아예 마운트되지 않는다** — 게이트웨이 오설정으로도 노출
불가. 이 패턴은 우리가 dev 배포 경계(K1–K4)에서 고민한 것보다 깔끔하다.

internal 워크로드는 `/me/topics`를 **미러하지 않는다**: 그 라우트는 호출자 자신의 아이템을
읽는데 internal에는 호출자가 없다. 이 사실이 §6의 프라이버시 결론에서 결정적으로 쓰인다.

internal은 `AuthorizationPolicy`를 출하하지 않아 메시 내 어느 파드나 호출할 수 있다. 그 결과
`GET /users/{owner_id}/topics?visibility=friends`를 검증된 신원 없이 읽을 수 있고, README가
이를 "accepted risk"로 명시한다.

### 1.3 3층 구조

```
① 카탈로그 (토픽 DAG)        topic/catalog/*      DynamoDB: bourbon-topic-catalog-tokyo-{stage}
     PK=TOPIC#{id}  SK=META | PARENT#{parent_id}
     Wikidata에서 discover→review→apply로 큐레이션. 인메모리 그래프로 캐시(TTL 60s)

② 유저 토픽 아이템             topic/user_topics/*  DynamoDB: bourbon-user-topic-tokyo-{stage}
     PK=USER#{uuid}  SK=TOPIC#{id}
     score(0-100) · visibility(4단) · description(유저 취향) · score_inputs(facets/relation/confidence)
     GSI topic-score-index: PK={topic_id}#{visibility}  SK=score  KEYS_ONLY

③ 검색·랭킹                    topic/search/*
     텍스트→토픽: 인메모리 부분문자열 스캔        (§2.1)
     토픽→유저 : GSI 스트림 + threshold 병합      (§2.2)
```

`topic_id`는 불투명하다. `topic/catalog/ids.py`에서 생성하며 **표시 이름에서 파생하지 않는다** —
한 단어가 여러 개념을 가리키므로(커피 버번 / 위스키 버번) 이름 파생 식별자는 먼저 만들어진
개념이 이름을 독점하게 만든다. Wikidata 출처가 있으면 `uuid5(고정namespace, "wikidata:{qid}")`
로 **결정적**이고, 그룹 자체 토픽은 `uuid5(ns, "group:{key}")`, 운영자 수동 생성만
`uuid4().hex` **랜덤**이다.

`topic_visibility = {topic_id}#{visibility}`는 GSI 파티션 키이며 `visibility`를 쓰는 모든 곳에서
같이 쓴다. 파생을 `topic/dynamodb/keys.py` 한 곳에만 두는 이유는 **둘이 어긋나면 랭킹이 조용히
틀리기 때문**이다. 두 키 속성 중 하나라도 없는 아이템은 **에러 없이** 모든 랭킹에서 사라진다
(`scripts/dynamodb/backfill_index_key.py`가 보수하며, 인덱스보다 오래된 테이블에서는
**배포 전에** 돌려야 한다 — 배포가 먼저 착지하면 보수 불가한 아이템이 생긴다).

### 1.4 카탈로그 파이프라인

`python -m cli catalog` 3단계, 시드 디렉터리 하나 위에서 순서대로 돈다.

| 명령 | 읽는 것 | 쓰는 것 |
|---|---|---|
| `discover` | `groups.yaml`, knowledge API(bourbon-memory-api-v2 `/knowledge/*`), LLM 프록시 | `reviewed/{group_key}.yaml` |
| `review` | `reviewed/*.yaml` | 같은 파일 제자리 |
| `apply` | `groups.yaml`, `reviewed/*.yaml`, 카탈로그 테이블 | `--execute`에서 테이블 |

- seed qid에서 **아래로만**(`narrower`) 확장한다. seed 서브트리 밖은 후보에 들어오지 않는다.
- 값싼 카드 필터 → 상세 조회 → LLM 배치 분류(기본 `openai/gpt-5.6-luna`, confidence 임계 0.8).
- LLM에게 "카탈로그는 깊게 저장하지만 독자는 2단만 본다"를 미리 알려주고, 상위 레벨의 다른
  자식들 옆에서 노이즈로 읽히는 변종은 `too_specific`으로 떨어뜨린다.
- 동음이의 의심·중복 라벨·`min_importance` ±10% 경계·LLM parent와 기계적 parent 불일치는
  **항상 사람에게** 넘어간다.
- 재실행 안전: 사람의 결정은 다음 discover에서도 살아남는다. 캐시는 `dump_version`으로 스코프.
- `apply`는 `source.qid` 매칭으로 중복 대신 패치한다. **수동 생성 토픽은 qid가 없어 이 보호를
  받지 못한다** — 같은 개념이 나중에 import되면 topic_id가 둘이 되고, 정리 수단은 `merge`뿐이다.

### 1.5 페르소나 → 토픽 추출 (현재는 임시 형태)

`cli persona extract`. **이 CLI/마크다운 형태는 persona extractor 계약이 미정이라 임시로
만들어 둔 것이다**(담당자 확인, 2026-08-21).

```
persona markdown
 → ①signals   LLM 1회: evidence · 한국어 description · 영어 query_phrases 2~4개 · facets 5개
 → ②grounding internal GET /search/topics + 상세의 children. 활성만, dedupe, signal당 40개 캡
 → ③marking   LLM 1회/signal: 후보 목록에서 exact|ancestor|related + confidence + 한국어 description
                              **모델은 인덱스만 답한다** (id를 주면 그럴듯한 것을 발명하므로)
 → score = 존재하는 facet들의 등가중 평균 × relation할인(1.0/0.85/0.6) × confidence
```

- 출력은 **디스크 JSON**(`.persona_topics/`)뿐이다. 실 테이블 적재 경로는
  `scripts/dynamodb/seed_local.py`(loopback 전용) 하나이고, dev/prod에는
  `POST /internal/topic/scores/bulk`를 부를 주체가 **아직 없다**.
- 이 서비스는 **deferq/AMQP 의존이 전혀 없다** — 이벤트를 소비하지 않는다.
- `query_phrases`는 영어 한정이며 프롬프트가 "카탈로그가 라벨링하는 방식의 1–3단어 canonical
  name, 수식어 절대 금지"를 강제한다. `unmatched_signals`(어떤 후보도 살아남지 못한 signal)는
  "카탈로그 갭을 드러내기 위해" 보관되지만 **파일에만 남고 서비스는 읽지 않는다.**

---

## §2 검색은 어떻게 이뤄지는가 (OpenSearch 없음, 검증됨)

검색이 두 단계로 쪼개져 있고, **①은 검색 엔진이 아니며 ②는 텍스트를 보지 않는다.**

```
자유 텍스트 ──①─→ topic_id ──②─→ 랭킹된 유저들
```

### 2.1 ① 텍스트 → 토픽: 인메모리 부분문자열 스캔

`topic/catalog/graph.py:find_by_name`이 전부다.

```python
needle = normalize_search_text(query)        # lower() + 공백 전부 제거
for item in self._topics.values():           # 2,605개 선형 순회 (dict 삽입 순)
    if item.status is not active: continue
    hay = [labels.ko, labels.en, labels.ja] + item.aliases    # 최대 53개
    if any(needle in normalize_search_text(t) for t in hay):
        found.append(item)
    if len(found) >= limit: break             # limit = SEARCH_MAX_NAME_MATCHES(20)
```

토크나이저·형태소 분석·stemming·점수·순위가 **전부 없다.** 카탈로그 전체를 워커마다 메모리에
들고 `grep -i`를 돌린다.

작동하는 이유는 **Wikidata alias가 동의어 사전 역할을 하기 때문**이다. 실측: 그래프 2,605개에
**alias 66,349개**(토픽당 평균 25.5개). `programming language` 하나에 `computer language`,
`coding language`, `프로그래밍언어`, `컴퓨터 언어`, `プログラム言語`, `Proglang`, 오타인
`Programing language`까지 붙어 있다. 형태소 분석기가 할 일을 큐레이션된 목록이 대신한다.

**결정적 비대칭 — 방향.** `needle in haystack`에서 needle이 질의, haystack이 라벨이다.
즉 **질의가 라벨의 부분문자열이어야 한다.**

- `커피` ⊂ `드립 커피` → 매칭
- `드립 커피 추출` ⊄ 어떤 라벨도 → **0건**

**질의가 길어질수록 매칭 확률이 0으로 간다.** extractor 프롬프트가 `query_phrases`를 1–3단어
canonical name으로 못 박는 진짜 이유가 이것이다. 검색 엔진이 없으니 **질의를 라벨 모양으로
미리 깎아서** 넣어야 한다.

**실측** (`find_by_name` 로직을 실제 그래프 2,605개 + alias 66,349개에 그대로 적용.
`TopicGraph`가 topic_id로 dedupe하므로 중복 qid 12건을 접은 뒤의 수치다. 부록 B로 재현 가능):

| 질의 | 총 매칭 | 앞 20개(=서비스가 실제로 보는 것) 관찰 |
|---|---|---|
| `커피` | 8 | coffee, instant coffee, cold brew, specialty coffee … 정상 |
| `드립 커피` | 1 | drip coffee |
| `핸드드립 커피 추출법` | **0** | 긴 질의는 전무 |
| `machine learning` | 5 | machine learning, explainable AI, supervised/unsupervised, ensemble |
| `머신러닝` | 1 | machine learning (**alias에 있다**) |
| `기계학습` | 4 | machine learning, reinforcement/supervised/unsupervised learning |
| `python` / `파이썬` | 1 / 1 | Python (한국어 alias 작동) |
| `위스키` | 2 | whisky, malt whisky |
| `양자역학` | 1 | quantum mechanics |
| `quantum` | 6 | **첫 결과가 `crossword`** — alias `"Quantum puzzle"` 때문 |
| `database` | 5 | **첫 결과가 `blockchain`** — alias에 `distributed database` 류가 있음 |
| `ai` | **560 (캡 도달)** | 앞 20개: isekai, cryptocurrency, marketing, accounting, decision theory, viral marketing … **인공지능이 없다** |
| `kubernetes` / `쿠버네티스` | 0 / 0 | 카탈로그에 개념 자체가 없음 |
| `dynamodb` | 0 | 없음 |
| `observability` / `관측가능성` | 0 / 0 | 없음 |

읽어야 할 두 가지:

1. **한국어 alias 커버리지는 예상보다 좋다.** `머신러닝`·`파이썬`·`양자역학`이 다 걸린다.
   한국어 질의가 못 쓸 수준은 아니다. 다만 영어 alias가 더 두꺼우므로 expansion은 영어가 유리하다.
2. **짧은 질의가 치명적이다.** `ai`는 560개를 매칭하고(부분문자열이므로 is**ai**, m**ai**l 등),
   20개 캡을 채운 뒤 **관련도 순이 아니라 그래프 보관 순서**로 자른다. 인공지능이 그 안에
   들어올지는 운이다. `MIN_NAME_QUERY=2`가 있지만 2자로는 부족하다.
   `find_by_name`은 "제공할 relevance 순서가 없다"고 README가 인정한다.

### 2.2 ② 토픽 → 유저: GSI + threshold 병합

여기엔 텍스트가 없다. GSI 파티션 `{topic_id}#public`이 score 내림차순으로 정렬돼 있다.
**leaf와 rollup은 엔드포인트가 아니라 같은 서비스가 요청마다 고르는 두 전략이다**
(`topic/search/service.py`의 `if len(weights) == 1`).

```
질의 → topic_id 확정 → 서브트리 걷기 (max_depth=3, max_count=50)
  → 활성 자손 0            → leaf
  → 자손 있음 / 이름이 여러 토픽 매칭 → rollup
```

**leaf** (`topic/search/single.py`) — 파티션 하나가 후보 전체다. 상위 `limit`행을 읽고(score 0을
만나면 그 아래는 전부 0이므로 즉시 종료) 본문을 BatchGet 한 번으로 채운다. 라운드트립 2회,
`exhaustive=True`가 **항상** 보장된다(병합이 없으니 근사가 아니라 정답). decay 없음.

**rollup** (`topic/search/service.py:_rank_rollup` + `topic/search/threshold.py`) —
서브트리의 토픽마다 파티션이 따로 있으므로 정렬된 스트림 N개를 병합한다. 유저 점수는 가중 합:

```
weight = SEARCH_DEFAULT_DECAY(0.6) ^ 질의 토픽으로부터의 거리
유저 총점 = Σ weight[t] × score[유저, t]   for t ∈ 서브트리 ∩ 유저 보유
```

Fagin TA 계열 알고리즘:
1. 스트림의 `bound` = 아직 안 읽은 유저가 그 토픽에서 가질 수 있는 최대 점수(첫 읽기 전 ∞)
2. `T = Σ weight × bound` = 미발견 유저의 총점 상한
3. 확정된 k번째 점수가 `T`를 **엄격히** 넘으면 중단(등호에서 멈추면 tie-break가 뒤집을 수 있음)
4. 아니면 `T`에 가장 크게 기여하는 스트림에서 다음 페이지를 읽고 2로

그리고 비싼 단계가 하나 더 있다. 스트림은 "유저 U가 토픽 t에서 몇 점"만 알려주므로 총점을
알려면 **U의 파티션 전체를 강한 일관성으로 다시 읽는다**(`resolve` → `list_for_user`,
`ConsistentRead=True`). 이것이 rollup 비용의 대부분이다.

**중요한 방향성**: 서브트리 걷기는 **아래로만** 간다. 드립커피만 보유한 유저는 "커피" 질의에
나오지만, 커피만 보유한 유저는 "드립커피" 질의에 **나오지 않는다.** extractor가 넓은 토픽과
좁은 토픽에 동시에 붙이는 이유가 이것이고, 이는 **적재 계약의 핵심 항목**이다(§11-2).

**불완전성 3종 플래그** — 삼키면 안 된다:
- `exhaustive=false`: 읽기 예산이 먼저 소진돼 증명이 실패. 꼬리가 빠져 있을 수 있음
- `truncated_descendants`: depth/count 상한이 잘라낸 자손 수. 여러 루트면 상한이 아니라 **상한의 상한**
- `unranked_topics`: 이름이 매칭했으나 예산이 닿지 못한 루트 수

**페이징이 없다.** 양쪽 경로가 같은 resume 계약을 못 내서 일단 뺐다(README 명시). 즉
top-`limit`(≤100) 밖은 존재하지 않는 것으로 취급해야 한다.

**leaf 경로의 stale 처리** — §6에서 프라이버시 문제로 다시 다룬다. GSI 행은 남았는데 본문의
visibility가 public이 아닐 때, 낡은 본문 대신 **인덱스에서 유도한 stub**을 답한다
(`single.py:_ranked`). 본문 필드는 보호되지만 `user_id`와 `score`는 나간다.
rollup 경로는 강한 일관성 테이블 읽기에서 다시 필터하므로 이 문제가 없다.

---

## §3 카탈로그의 실체 (실측)

정본은 `catalog_seeds/reviewed/*.yaml` 27개 파일이며 git에 커밋돼 있다. `apply`가 topic_id를
qid에서 파생하므로 **DB를 보지 않아도 이 파일들이 곧 카탈로그다.**

```
그룹 27  ·  채택 행 2,617  ·  고유 qid 2,605  ·  탈락 10,151  ·  pending 0
dump_version 20260802
깊이:  d0(seed) 170  ·  d1 2,180  ·  d2 267
판정자: 사람 1,818  ·  LLM 799
alias 총 66,694개 (토픽당 평균 25.5)
```

**탈락률 79.5%** (10,151 / 12,768). 카탈로그의 좁음은 Wikidata 커버리지가 아니라
`min_importance`·`max_generality`·`too_specific` 컷의 결과다.

행 2,617 vs 고유 qid 2,605의 차이는 **12개 qid가 두 그룹에 동시 채택**되었기 때문이다
(decision theory·game theory: business-money+science / blockchain: business-money+computing /
esports: games+sports / medical physics: health+science / musical·twist: music+performing-arts 등).
README의 "2605 topics"와 일치한다.

### 3.1 그룹별 분포

| 그룹 | 채택 | 탈락 | 그룹 | 채택 | 탈락 |
|---|---|---|---|---|---|
| health | **517** | 212 | food-drink | 52 | 721 |
| music | **444** | 235 | history | 42 | 461 |
| sports | 248 | 262 | mobility | 37 | 775 |
| places | 213 | 939 | business-money | 35 | 140 |
| society-politics | 204 | 165 | books | 32 | 242 |
| visual-arts | 159 | 149 | language-education | 29 | **1,033** |
| science | 98 | 98 | space | 15 | 131 |
| computing | 78 | **608** | fashion-beauty | 12 | 317 |
| philosophy-religion | 73 | 478 | comics-anime | 9 | 65 |
| games | 68 | 186 | architecture-design | 7 | 191 |
| performing-arts | 61 | 51 | internet-culture | 6 | 248 |
| military | 58 | **1,269** | knowledge-info | **5** | 39 |
| nature-environment | 58 | 486 | people | **1** | 31 |
| screen | 56 | 619 | | | |

health + music + sports = 1,209개로 **전체의 46%**. computing + knowledge-info +
business-money + language-education을 모두 합쳐 **147개**.

### 3.2 지식 도메인의 실제 내용

**computing (78개 전부)**
```
▸ artificial intelligence [24] — AI agent, ChatGPT, GitHub Copilot, LLaMA, Midjourney, Sora,
    Qwen, Grok, Manus, DALL-E, AlexNet, machine learning, NLP, RAG, GNN, reinforcement/
    supervised/unsupervised learning, ensemble learning, explainable AI, generative AI, GPT,
    machine translation, OpenAI Codex
▸ operating system [7] — Android, Windows, macOS, Unix, Palm OS, BlackBerry OS, RTOS
▸ database [2] — relational database, blockchain
▸ programming language [0]   ▸ software [0]   ▸ computer hardware [0]
▸ computer security [0]      ▸ robotics [0]
(언어 37개는 별도 부모: Python, Java, JavaScript, Rust, Go, C++, C#, TypeScript, SQL,
 Haskell, Clojure, Erlang, Scala, Swift, Ruby, PHP, Perl, Lua, COBOL, Fortran, ALGOL, ...)
```
없는 것: **cloud, AWS, Kubernetes, DevOps, distributed systems, API design, observability,
networking, compiler, data engineering, web/frontend/backend 전부.** 608개가 탈락했다.

**knowledge-info (5개, 전부 기관)**: library / archives / encyclopedia / museum / information.
지식 **영역**이 아니라 지식을 보관하는 **장소**다.

**science (98개, 반대로 촘촘)**: physics 19 / chemistry 23 / mathematics 23 / statistics 4 /
materials science 5 + quantum mechanics, biochemistry, thermodynamics. 학문 분류로는 쓸 만하다.

**language-education (29개)**: 12개가 자연어 이름(Arabic, Hebrew, Russian, Indonesian, Sioux…),
education은 자식 0. 탈락 1,033개.

**business-money (35개)**: economics 13 + marketing 6 + accounting 3 + cryptocurrency 2 +
finance 1. 실무 어휘(세무·조직·HR·프로덕트)는 없다.

전문성 어휘가 **원리적으로** 못 들어가는 게 아니다 — science와 AI가 촘촘한 것이 반례다.
**seed 선택의 결과**이므로 `groups.yaml` 수정으로 고칠 수 있다.

### 3.3 카탈로그에 없는 토픽은 어떻게 처리되나

3단 완충이 있다.

1. **근사 grounding (대부분 여기서 처리됨).** marking은 `exact`만이 아니라 `ancestor`(0.85)와
   `related`(0.6)를 허용하고, grounding이 검색 히트의 **조상과 한 단계 자식까지** 후보로 모은다.
   따라서 카탈로그에 없는 니치 관심사는 사라지지 않고 **상위 개념으로 흡수되며 점수만 할인**된다.
   `persona_seeds/user01.json`이 드립커피 88.7 + 커피 76.2를 **둘 다** 가진 것이 그 결과다.
   → **정밀도를 잃고 살아남는 것이 기본 동작이다.**
2. **아무것도 못 붙으면 `unmatched_signals`.** 파일에만 남고 서비스는 읽지 않는다. 조용한 손실.
3. **그 유저는 그 주제에 대해 검색에 존재하지 않는다.** GSI에 행이 없으므로 leaf든 rollup이든
   나오지 않고 **에러도 없다.**

카탈로그 확장 경로:

| 경로 | id | 성격 |
|---|---|---|
| seed 추가 → discover → review → apply | `uuid5(ns,"wikidata:{qid}")` **결정적** | 정규 경로. 재실행 안전, 캐시 TTL 후 반영 |
| `POST /internal/topic/catalog/topics` | `uuid4().hex` **랜덤** | qid 없음, `origin=curated`, 루트 생성 가능, 중복 이름 검사 없음 |
| `groups.yaml`의 `topic:` 블록 | `uuid5(ns,"group:{key}")` | **현재 선언한 그룹 없음** |

**없는 경로: 유저/에이전트가 토픽을 제안하는 길.** `TopicOrigin.user`에
"No route writes this any more: the user proposal endpoint is gone"이 남아 있다 —
있었고 **의도적으로 제거**됐다. 카탈로그 확장은 전부 사람이 도는 오프라인 루프다.

---

## §4 전문성 vs 관심 — 3층 분해

담당자 판단(2026-08-21): *"topic이 preference 쪽에서 추출되고 많이 정제된 카탈로그로
서빙되다보니 전문성 보다는 관심 도메인 정도의 분류라 다양한 축의 agent 추천에는 조금 한계가
있을 수 있을거 같기도 합니다만 첫 토픽기반 추천에는 적당할거 같아요"*

이 진단은 맞고, **세 층 모두에서** 그렇다. 층을 나누는 것이 중요한 이유는 **고칠 수 있는 층과
없는 층이 다르기 때문**이다.

| 층 | 상태 | 고칠 수 있나 |
|---|---|---|
| **어휘** | §3.1–3.2. 관심 도메인 분류. science·AI만 예외적으로 촘촘 | ✅ `groups.yaml` seed 확장. 코드 변경 0 |
| **점수 공식** | facets 5개 중 **4개가 관심·애착**(engagement/affinity/duration/recency), 전문성은 `knowledge` 하나. **등가중 평균**(`fmean`) × relation할인 × confidence | ✅ `score_inputs`에 원 facets가 남아 있어 재가중 가능 |
| **근거 출처** | persona **자기 서술**. 프롬프트도 "`knowledge` = 문장이 드러내는 전문성의 깊이". 외부 검증(대화 근거·기여·타인 확인) 없음 | ❌ 구조적으로 없음 |

### 4.1 점수 공식 문제는 1차의 문제다

담당자는 이 한계를 "다양한 축"(=2차 need_type) 문제로 보았으나, **우리 1차 스코프가 이미
"가장 잘 아는 agent"이므로 축이 전문성이다.** 등가중 평균의 결과:

| | knowledge | engagement | affinity | duration | recency | score |
|---|---|---|---|---|---|---|
| 깊이 아는 사람 | **95** | 30 | 30 | 30 | 50 | **47** |
| 열심히 즐기는 사람 | 40 | 95 | 95 | 90 | 100 | **84** |

**애호가가 전문가를 거의 2배로 이긴다.** topic-api의 `score`를 정렬 키로 그대로 쓰면
**1차부터 어긋난다.**

### 4.2 해결책과 걸림돌

`ScoreInputs`는 원 facets를 그대로 보관하고, 설계 의도가 명시적이다 — *"점수는 하나의 숫자이고
그 자체로는 왜인지 말하지 않는다. 입력을 함께 실어 두는 것이 읽는 쪽이 값을 재계산하고
**이견을 낼 수 있게** 한다."* 따라서 우리는 그들의 scalar를 재해석하는 게 아니라
**원자료로 돌아가 우리 정렬 키를 만든다.**

걸림돌: `score_inputs`가 **랭킹 응답(`MatchedTopicResponse`)에 없다**(전수 확인). 현재 받을 수
있는 곳은 `GET /internal/topic/users/{owner_id}/topics`(`InternalUserTopicListResponse`)뿐이라
owner당 추가 호출(N+1)이 된다. **internal 역할 한정으로 랭킹 응답에 필드 하나 추가**하면
해결되고, 그들이 이미 세워 둔 근거("internal 호출자는 서비스, facets는 파이프라인이 자기 출력을
검증할 때 필요한 것")와 정확히 같은 논리다. → §11-3

---

## §5 성능·지연·비용 비교 — rev 14 계획 vs topic-api

### 5.1 측정 가정

**검증됨**: DynamoDB 모듈은 `PAY_PER_REQUEST`(`iac terraform/modules/dynamodb/main.tf:2`) —
읽기 증폭이 곧 달러. AOSS `bourbon-aoss-tokyo-dev`는 이미 존재하며 공유 그룹 `dev-aoss-tokyo`에
**min 2 indexing + 2 search OCU / max 16+16**(`iac terraform/env/dev/main.tf:352-376`), type SEARCH.
topic-api 상한: `SEARCH_MAX_GSI_ITEMS=20000`, `SEARCH_MAX_USER_QUERIES=2000`,
`SEARCH_MAX_DESCENDANTS=50`, `SEARCH_MAX_DEPTH=3`, `SEARCH_MAX_NAME_MATCHES=20`,
`_QUERY_CONCURRENCY=16`, `_STREAM_PAGE_FACTOR=4`, `CATALOG_CACHE_TTL=60`.
워커는 pod당 1개(`WEB_CONCURRENCY=limits.cpu=1000m`), prod HPA 2–5.

**가정**: user topic 아이템 ≈0.5KB, 유저당 topic 20개(파티션 ≈10KB), GSI KEYS_ONLY 행 ≈0.14KB,
강한 읽기 1 RCU=4KB / eventual=8KB. rev 14의 N·K는 문서가 "eval로 결정"으로 열어 뒀으므로
변형 4개 × top-50 → owner top-K=3 → 후보 ~180쌍으로 잡았다.

**미확인**: OCU/RCU 단가는 대략치. 정확한 청구는 Tokyo 요율 확인 필요.

### 5.2 지연

| 경로 | DDB 라운드트립 | LLM | p50 추정 | p99 성격 |
|---|---|---|---|---|
| topic-api **leaf** | **2** | 없음 | **10–25ms** | 안정. exact |
| topic-api **rollup** | 스트림 페이지 **순차** 20–250회 + resolve 웨이브 | 없음 | 250–450ms | **초 단위**(1.5–3s), 답은 `exhaustive=false` |
| rev 14 계획 | AOSS 1 + BatchGet 2단(chunk 병렬) | **요청당 판정 1회** | 40–80ms(검색부) **+ 300–1500ms(LLM)** | LLM 지배 |

rollup의 `top_k`는 **한 번에 한 스트림, 한 페이지씩 순차로** 읽는다. 스트림이 31개면 최소 31회
순차 왕복이고, threshold 수렴은 모든 스트림의 bound가 함께 내려가야 진행되므로 서브트리가
넓을수록 느려진다(주석도 "a wide descendant set converges slowly"로 인정).

→ **topic-api는 최악이 나쁘고 rev 14는 평균이 나쁘다.**

### 5.3 읽기 비용 (RCU/요청)

| | 전형 | 상한 |
|---|---|---|
| topic-api leaf | **≈3 RCU** | ~13 (limit 100) |
| topic-api rollup | ~630 RCU (스트림 20 · 후보 유저 200 가정) | **≈6,350 RCU** (GSI 20,000행 ≈350 + resolve 2,000×3) |
| rev 14 계획 | **≈60 RCU** (1단계 45 + 2단계 15) | ≈60 RCU (N·K로 구조적 고정) |

**leaf의 3 RCU는 우리가 상상했던 어떤 구조보다 싸다** — 이 비교의 가장 중요한 발견.

트래픽과 무관한 고정 읽기: 카탈로그 캐시가 60초마다 **테이블 전체 Scan**
(`topic/catalog/repository.py:52-70`), 워커마다 독립. ~5,000 아이템 ≈2.5MB → ~313 RCU/워커/분.
달러로는 미미하지만 **재적재가 락 아래 블로킹**(`topic/catalog/cache.py:44-70`)이라
**60초마다 규칙적인 p99 스파이크**가 있다. stale-while-revalidate가 아니다.
(적재 실패 시에는 stale을 서빙하고 다음 시도를 한 TTL 뒤로 미룬다 — 이 부분은 올바르다.)

### 5.4 LLM 비용 — 결정적 축

| | LLM이 언제 도는가 | 요청당 토큰 | 규모 특성 |
|---|---|---|---|
| topic-api | **write-time**(persona 변경 시): signal 1 call + signal마다 marking 1 call ≈ 4–6 calls, 후보 40개 프롬프트 → 대략 20–40k input tokens | **0** | persona 변경 횟수 비례 |
| rev 14 | **read-time**(매 요청): 후보 ~60개 × 300토큰 ≈ **12–24k input tokens** | 12–24k | **질의 횟수 비례** |

persona가 한 번 바뀌는 사이 관련 질의가 Q회면 rev 14의 LLM 지출은 **Q배**다. Discovery는 읽기가
쓰기보다 훨씬 잦으므로 Q≫1이고, 상수배가 아니라 스케일 차이다.

**단, "read-time LLM 0"은 우리에게 선택지가 아니다.** topic-api가 read-time LLM을 안 쓸 수 있는
이유는 질의가 이미 카탈로그 어휘로 들어온다고 가정하기 때문이고, 그 정규화 부담을 write-time으로
옮겼다(§2.1). Discovery의 요청은 자유 서술이므로 **expansion 1회는 불가피**하다
(~500–1000 input tokens, 100–300ms). 현실적 하한은 "expansion 1회"이고, rev 14의 판정층은 그 위에
**선택적으로** 얹는 12–24k 토큰이다.

### 5.5 고정 인프라 비용

| | 증분 고정비 |
|---|---|
| topic-api | **0** (DDB 온디맨드만. 테이블·GSI는 iac 추가 필요하나 유휴 비용 없음) |
| rev 14 | AOSS 4 OCU 하한은 **이미 지출 중**(pensieve·bourbon 공유) → 인덱스 추가의 증분은 스토리지 + OCU 여유분. 진짜 증분은 **스트림 파이프라인**: OSIS면 최소 1 Ingestion OCU 상시, Lambda 컨슈머면 거의 0 |

rev 14에 유리한 정정 하나: AOSS 신설 비용을 우려했으나 컬렉션은 이미 있고 하한도 이미 낸다.
불리한 사실 하나: **Q1(OSIS vs Lambda)은 비용 축에서 답이 난다** — 상시 OCU를 사는 OSIS는
이 데이터량에 과하다.

### 5.6 확장 한계

- `find_by_name`은 **O(전체 토픽) 선형 스캔**이고 이벤트 루프 안에서 CPU를 쓴다. 2,605개에서는
  몇 ms지만 10만 규모면 질의당 100–400ms 블로킹이고 워커는 pod당 1개다. 매칭 0건 질의가 최악
  (전체 스캔). **여기가 AOSS가 실제로 필요해지는 지점이며, 색인 대상은 유저 아이템이 아니라
  카탈로그다**(정적, 하루 몇 번 변경 → 스트림 파이프라인 불필요).
- 20개 캡을 통과하는 순서가 관련도가 아니다(§2.1 `ai` 사례).
- 형태소 분석·동의어 확장 없음. decay는 **DAG 거리**만 알고 요청 의도를 모른다.

---

## §6 프라이버시 모델 — 노출 면적을 결정한다

### 6.1 정책 (오너 확인, 2026-08-21)

**유저 토픽 visibility의 기본값은 `private`이며, 이는 우리 서비스의 프라이버시 정책이다.
유저가 직접 public으로 올려야 한다.** 이것은 구현 기본값이 아니라 정책이다.

코드가 이를 강제하는 방식(검증됨):

1. 랭킹은 `RANKED_TIER = public` 파티션 **하나만** 읽는다(`topic/visibility/tiers.py`).
2. score 주입(`put_score`)은 첫 쓰기에서 `visibility = if_not_exists(..., private)` — 주석:
   *"A topic the user has never configured must not become searchable by everyone."*
3. **주입 경로는 visibility를 쓸 수 없다.** `ScoreRequest`는 `{score, score_updated_at,
   score_inputs}`뿐이고 internal 라우터 어디에도 visibility 쓰기가 없다(전수 확인).
4. 올릴 수 있는 건 `PATCH /me/topics/{id}` 하나이고 **edge-auth로 검증된 본인만** 부른다.
   internal에 `/me` 미러가 없다.
5. 반대로 `TopicSettingsPatch`는 `score`를 받지 않는다 — 유저 쓰기가 점수를 나를 수 없다.
   두 writer가 disjoint 속성만 건드리고 `updated_at`만 겹친다(LWW가 올바른 의미).

tier는 독립 플래그가 아니라 **계열**이다: `public ⊂ friends ⊂ private ⊂ hidden`.
`hidden`은 삭제 대신 치우는 것(삭제 라우트 없음)이며 `/me/topics`에만 나온다.
친구 관계는 이 서비스가 저장하지 않는다 — `friends`는 클라이언트가 보내는 라벨이다.

### 6.2 결과

**의존이 우리 밖으로 나간다.** 필요한 API는 다 있다(`GET /me/topics`,
`PATCH /me/topics/{id}` `{"visibility":"public"}`). 없는 건 **그것을 호출하는 클라이언트
화면**이고, topic-api 레포에도 우리 레포에도 없다. → Discovery 출시가 앱 딜리버러블에 걸린다.

**비용**: `{topic_id}#public` 파티션이 희소해진다. 카탈로그와 점수가 완벽해도 토글한 유저가
임계 아래면 빈 결과다. **지배적 리스크가 카탈로그 어휘가 아니라 cold start로 바뀐다.**

**이득**: 유저가 **무엇을** 공개하기로 골랐는지가 그 자체로 신호다. "양자역학"을 공개한 사람은
"그 주제로 찾아와도 된다"는 의사를 표현한 것이고, 추천 표면이 원하는 것은 정확히
**아는 것 + 응할 의사**의 결합이다. facets에서 짜내려던 competence 신호보다 오히려 정직한 축이고,
후보 풀 자체가 이미 걸러진 상태로 온다.

**부수 효과**: 우리 응답의 `matched_topics`는 구조적으로 공개된 것만 담는다. rev 14가
TOPICSEARCH#·visibility 재확인·TOCTOU에 많은 지면을 쓴 이유가 이 보장이었는데, GSI 파티션이
그것을 구조로 준다. 우리 쪽 걱정 항목 하나가 사라진다.

### 6.3 leaf 경로의 구멍 (정책이므로 지적 대상)

rollup은 안전하다 — `_ranked_in_subtree`가 **강한 일관성 테이블 읽기**에서
`visibility is public`을 다시 확인하므로 비공개로 바꾼 아이템은 총점에 0으로 기여하고
유저가 탈락한다.

leaf(`topic/search/single.py:_ranked`)는 다르다. GSI 행은 남았고 본문이 이미 public이 아닐 때,
낡은 본문 대신 **인덱스에서 유도한 stub**을 답한다. 본문 필드(description 등)는 보호되지만
**`user_id`와 `score`는 그대로 나간다.**

private이 단순 기본값이면 GSI 전파 지연 동안의 사소한 staleness다. 그러나 **공개가 유저의
명시적 행위인 정책**이라면 "이 유저가 이 토픽을 보유하고 점수가 S다"라는 **소속 사실 자체가
보호 대상**이다. 고치는 방법은 간단하다 — stub을 만들지 말고 그 행을 결과에서 제외
(rollup이 이미 그렇게 한다). → §11-4

### 6.4 서빙 가능성은 곱셈이다

```
서빙 가능성 = 카탈로그 커버리지 × 공개 밀도
              (질의→토픽 매칭률)   (그 토픽을 공개한 owner 수)
```

두 번째 항이 **현재 0**이다(prod 적재 호출자 없음, 토글 UI 없음). 따라서 지금 잴 수 있는 것은
첫 항뿐이고, 그것만으로 "1차에 적당한가"를 답할 수 없다. 대신 **출시 수용 기준을 지금
정의할 수 있다** → §12.

Alpha는 내부 대상이므로 **내부 코호트에게 토글을 요청하는 것이 정당한 부트스트랩**이다.

### 6.5 별도 위험: 데모 모드

`DEMO_SAMPLE_USERS=true`는 **검증된 caller id를 해시 스탠드인으로 대체**한다. 실데이터
환경에서 켜면 모든 호출자에게 남의 계정을 보여준다. 기본 off, k8s 미설정, README도 경고.
이 규율이 유지되는지 계속 확인해야 한다.

---

## §7 배포·운영 상태 (검증됨) — 지금은 dev에도 뜨지 않는다

| # | 갭 | 근거 | 소관 |
|---|---|---|---|
| 1 | **iac에 테이블이 없다** — `bourbon-user-topic-*`, `bourbon-topic-catalog-*`, `topic-score-index` 어디에도 없음. dev configmap은 존재하지 않는 테이블을 가리킴 → 전 호출 `ResourceNotFoundException` | iac origin/main `d364d3c` 전수 grep | 인프라 |
| 2 | **IRSA 권한 2중 부족** — `bourbon-app`의 DynamoDB 문장은 `bourbon-agent` 테이블 ARN 1개 + `/index/*`로 한정. 액션 목록에 **`dynamodb:Scan`이 없고** 카탈로그 로드는 Scan | `iac terraform/modules/iam/service/service_roles.tf:116-132` / `topic/catalog/repository.py:52-70` | 인프라 |
| 3 | **게이트웨이 미등록** — bourbon-api dispatch에 `/api/svc/topic/` 블록 없음 → public 워크로드 외부 도달 불가 | bourbon-api origin/main `k8s/base/api-svc-dispatch.yaml` | bourbon-api |
| 4 | **prod 적재 호출자 부재** — `cli persona extract`는 디스크에만 쓴다. `POST /internal/topic/scores/bulk`를 부를 주체 미정 | §1.5 | extractor |
| 5 | **internal `AuthorizationPolicy` 없음** — 메시 내 누구나 호출 가능 | README 명시(accepted risk) | topic-api |
| 6 | **공개 토글 UI 없음** — §6.2 | 두 레포 모두 부재 | 앱/클라이언트 |

우리는 internal을 호출하므로 3번은 우리 게이트가 아니다. **4번과 6번이 우리 출시의 실질
게이트**이고, 1·2번은 그보다 먼저 온다.

운영 특성(고장은 아니지만 알아야 할 것): 60초 블로킹 카탈로그 Scan(§5.3), 워커 pod당 1개 +
CPU 바운드 `find_by_name`(§5.6), rollup 상한이 큼(§5.3), 인덱스 키 누락 아이템이 조용히
사라짐(§1.3).

---

## §8 확정된 방향 — 축의 이전

### 8.1 결정: topic-api를 축(axis)으로 삼는다

**근거 두 개.** 순서가 중요하다 — 첫째가 담당자 근거이고 더 강하다.

1. **유저에게 보이는 라벨의 일치** (담당자, 2026-08-21). 유저는 자기 프로필에서 topic-api의
   라벨(ko/en/ja 큐레이션, 2단 트리, 이미지)을 본다. 추천 이유(`matched_topics`)가 우리가 따로
   뽑은 어휘로 나오면 **같은 개념이 화면에서 두 이름으로 존재**한다. 내부 구현 세부가 아니라
   제품 결함이고, 한번 노출되면 되돌리기 어렵다. 우리가 rev 12–13에서 잠근 용어 규율
   ("이름 ≠ 의미", 소유권은 생애주기로)을 제품 표면에 적용한 것과 같은 결론이다.
2. **공통 축 없이는 사람을 서로 순위 매길 수 없다.** 개방 어휘에서는 유저 A의 "커피 핸드드립"과
   B의 "드립 커피"가 다른 문자열이고, 비교하려면 read-time에 동의어를 해소해야 한다 —
   그것이 rev 14의 판정층이 필요했던 이유다. **rev 14의 read-time LLM은 정밀도를 위한 사치가
   아니라 개방 어휘를 택한 대가였다.** 카탈로그는 그 해소를 적재 시점에 사람 리뷰까지 붙여
   끝내므로 read-time LLM 없이 랭킹이 성립한다. 이것은 더 싼 것이 아니라 **문제를 더 잘 쪼갠 것**이다.

카탈로그가 추가로 주는 것: 동명이의 통제, 계층 → rollup/decay, 재추출을 넘어 안정적인 id,
`score_inputs`로 감사 가능한 점수, popularity 항이 없는 순수 per-user facet 점수
(우리 reputation 원칙과 충돌 없음).

### 8.2 금지: 병렬 두 시스템

같은 페르소나 위에 두 extractor, 두 저장소, 두 랭킹 의미, 두 visibility 모델, 두 id 공간을
두는 것. 쓰기 비용이 두 배가 되고, 두 경로의 결과를 **합칠 수 없다**(카탈로그 경로의 scalar와
우리 경로의 LLM verdict는 비교 대상이 아니다). "둘 다"는 **비대칭적으로만** 성립한다 —
하나는 축, 하나는 보정.

### 8.3 3단 계획

**A (지금) — 순수 소비, 저장소 0.**
expansion(작은 LLM 1회) → `GET /internal/topic/search/topics` → **구체 토픽 2–3개를 병렬 leaf
조회** → 우리 후처리(self-exclusion, eligibility, cap, `matched_topics` 조립, 실패 3분기).
목적은 기능이 아니라 **측정**(§12).

넓은 토픽 하나로 rollup을 부르는 것보다 낫다: 싸고(3 RCU×3), 지연이 평탄하고(병렬 2 RTT),
`exhaustive=True`가 보장되고, 어느 확장어가 맞았는지 귀속이 응답 단위로 남는다 —
rev 14 §3의 "변형별 `_msearch` 독립 검색 + RRF"와 정확히 같은 모양이다. 병합 규칙은 우리가 정한다.

**B (측정이 부족하다고 말하면) — 우리 코드가 아니라 카탈로그를 늘린다.**
computing/science seed 확장 + `min_importance` 하향 제안. `groups.yaml` 한 파일이고 수혜자가
우리만이 아니다. **코드 없이 얻는 recall이 가장 싼 recall이다.**

**C (그래도 남는 갭에만) — 보정층 두 개.**
① **rerank(gate 아님)**: 이미 랭킹된 top-20에만 판정층. LLM ~6k 토큰, +200–400ms.
   rev 14 §1-⑪의 tiered judging 레버와 같은 취지이며 원안의 1/3 이하 비용.
② **unmatched 채널**: 카탈로그로 표현 안 되는 질의를 버리지 않고 기록 → seed 후보로 환류.
   정말 필요해지면 그때 보조 인덱스. 그 인덱스도 **유저 아이템이 아니라 "카탈로그로 못 잡힌
   관심사"만** 담으므로 스트림·epoch·TOCTOU는 여전히 불필요하다.

---

## §9 rev 14 처분 — 폐기 / 승계

| rev 14 항목 | 처분 | 이유 |
|---|---|---|
| §2 전용 테이블 + 아이템 5종 스키마 | **폐기** | 저장 주체가 topic-api |
| 3-item transaction · `publication_epoch` · `judge_revision` · `claim_digest` | **폐기** | 우리가 쓰지 않으므로 동시성 계약의 주체가 아님 |
| TOPICSEARCH# projection / 전역 discoverable 계약 | **폐기** | GSI 파티션 `{topic_id}#public`이 같은 일을 함 |
| §4 2단계 both-strong BatchGet 계약 | **폐기** | 읽기 주체가 topic-api. rollup이 이미 강한 일관 재확인 |
| 스트림 색인 파이프라인 (Q1·Q2·Q9) | **폐기** | 색인할 우리 데이터가 없음 |
| extractor 협의 Q5·Q13·Q14 | **폐기** | extractor가 존재하고 우리 소관이 아님 |
| AOSS 인덱스 신설 | **유예** | 카탈로그 2,605개 동안 정당화 안 됨. 필요해지면 **카탈로그만** 색인 |
| §1-⑪ relevance 판정층 | **승계, gate→rerank로 격하** | top-20 재정렬 |
| 실패 의미 3분기(422 / 200+empty / 503) + 오귀속 금지 | **승계** | topic-api는 매칭 0건도 `200 + 빈 items`로 답한다 → **우리가 구분해야 함** |
| ordering contract (gate→filter→tiebreak) | **승계, 재해석** | 아래 |
| self-exclusion · 즐겨찾기=tiebreak only · popularity prior 금지 | **승계** | topic-api에 self-exclusion 없음 |
| 판정 입력 텍스트 전부 비신뢰 취급 | **승계** | 카탈로그 description·유저 description 모두 대화/LLM 유래 |
| gate 3종 직교(maturity/safety/privacy) | **승계** | privacy는 §6이 구조로 보장, maturity 입력은 §11-3 미해결 |

**ordering contract의 재해석 — 그리고 그 위의 정정.**
우리는 "scalar score 금지"를 잠갔고 topic-api는 scalar를 준다. 그 규율의 실질은 "gate를 점수로
사고팔지 말라"이며 여전히 유효하다. 그래서 형태는 `gate(우리) → 정렬 키 → 우리 결정적 tiebreak`.

**단, 그 정렬 키는 topic-api의 `score`가 아니다.** §4.1에서 보인 대로 그 점수는 관심 강도이고
우리 질문은 전문성이다. 따라서 **facets 원자료에서 우리 정렬 키를 우리가 만든다.**
(이 문서 작성 중 "그들의 score를 정렬 키로 쓴다"고 먼저 적었다가 §4.1의 계산으로 철회했다.
재설계는 철회된 쪽을 되살리지 말 것.)
→ **ordering 키의 소유권은 우리에게 있다.**

---

## §10 우리(agent-recommendation-api)가 소유하는 것

1. **어댑터 + 계약 테스트** — topic-api 응답 스키마 변화를 조용히 먹지 않도록.
   우리 wire-contract 규율(계약 테스트 payload를 consumer model에서 유도 금지)이 그대로 적용된다.
2. **expansion 규칙** — 짧은 canonical 명사구(1–3단어), 수식어 금지, **영어 우선**(alias가 영어에
   가장 두꺼움), **2자 이하 확장어 금지**(§2.1 `ai`가 560건을 매칭하고 캡을 무관한 것으로 채운다),
   다어절 선호.
3. **실패 의미 3분기** — `/search/topics` 결과로 "토픽이 없다"(→422)와 "토픽은 있으나 공개
   보유자 0"(→200+empty)을 우리가 갈라야 한다. topic-api는 둘 다 200+빈 items로 답한다.
4. **ordering 키** — facets 기반 전문성 가중(§9).
5. **self-exclusion** — topic-api에 없다. 서버측이 아니면 정확성 손실(§11-5).
6. **eligibility (Q12)** — `AllowAllEligibilityProvider`는 여전히 stub. topic-api는 이것을 모른다.
7. **불완전성 플래그 로깅·게이트** — `exhaustive=false` / `unranked_topics>0` /
   `truncated_descendants>0`를 품질 저하로 다룬다.
8. **leaf 우선 fan-out + 병합(RRF)** — §8.3-A.

---

## §11 열린 질문 (수요일 논의 안건, 우선순위 순)

| # | 질문 | 소관 | 성격 |
|---|---|---|---|
| 1 | **공개 토글 UI의 소유자와 일정.** 그리고 공개 대상에 LLM이 쓴 `description`(그 유저에 대한 한 문장)이 포함되는지, 유저가 편집 가능한지(`PATCH`가 `description`도 받는다) | 앱 + 기획 | **블로커** |
| 2 | **넓은 토픽 + 좁은 토픽 동시 부착을 계약으로.** 서브트리 걷기는 아래로만 간다(§2.2) — "커피"만 붙은 유저는 "드립커피" 질의에 안 나온다. 지금은 프롬프트가 강제하나 **프롬프트는 계약이 아니다.** 놓치면 우리 코드로 복구 불가 | extractor | **비가역** |
| 3 | **`score_inputs`를 랭킹 응답(`MatchedTopicResponse`)에 추가 (internal 한정).** 전문성 재가중의 전제. 필드 하나. 아니면 owner당 N+1 호출 | topic-api | 높음 |
| 4 | **leaf 경로 stub이 `user_id`+`score`를 공개하는 문제**(§6.3). 정책상 소속 사실도 보호 대상 | topic-api | 높음 |
| 5 | **self-exclusion / `exclude_user_ids`를 서버측 cap 앞에.** 편의가 아니라 정확성 — `limit=20`을 받아 우리가 자신을 빼면 19개가 되고 20번째 후보는 애초에 오지 않는다. 일반화하면 in-room 제외도 같은 파라미터로 처리 | topic-api | 높음 |
| 6 | **maturity gate의 입력.** 우리 gate 입력인 "근거 개수"가 topic-api에 없다. 대용은 `facets.knowledge` + `confidence` + `score_updated_at`인데 "얼마나 깊은가"와 "LLM이 얼마나 확신하나"는 다른 것이다. gate를 무엇 위에 세울지 지금 정해야 뒤집지 않는다 | 우리 + extractor | 중간 |
| 7 | **철회 경로.** 유저가 다시 private으로 내리면 GSI에서 빠지므로 절반은 정책이 해결한다. 남는 것은 "관심이 식었는데 유저가 안 내린 경우"를 extractor가 어떻게 다루는가(score 0 주입? `removed_topics` 반영?) | extractor | 중간 |
| 8 | **`find_by_name` 정렬 근거.** 20개 캡 통과 순서가 dict 삽입 순이다. exact label 일치 우선 + `importance` 내림차순만으로도 크게 달라진다. README도 "this service has none to give"로 인정 | topic-api | 중간 |
| 9 | **토큰 단위 매칭.** 질의가 라벨의 부분문자열이어야 하는 제약으로 긴 질의가 항상 0건이다. 질의를 공백으로 쪼개 하나라도 걸리면 후보로 두는 것만으로 recall이 오른다 | topic-api | 중간 |
| 10 | **페이징 복귀** — 현재 top-`limit`(≤100) 밖은 존재하지 않는 것으로 취급해야 한다 | topic-api | 낮음 |
| 11 | **`unmatched_signals` 노출** — 이미 "카탈로그 갭을 드러내기 위해" 만든 필드인데 파일에 갇혀 있다. seed 제안의 근거 데이터 | extractor | 낮음 |
| 12 | 배포 게이트 §7의 1·2·5 | 인프라 / topic-api | 배포 시점 |
| 13 | 카탈로그 캐시 stale-while-revalidate (60초 p99 스파이크) | topic-api | 낮음 |

1·2는 **extractor 계약이 열려 있는 지금만 싸게 들어간다.** 나중에 바꾸려면 재추출과 데이터
마이그레이션이다.

---

## §12 측정 계획

### 12.1 지금 잴 수 있는 것 — 카탈로그 커버리지

eval 코퍼스의 질의·앵커를 2,605개 카탈로그에 대조해 다음을 낸다:

- **exact 매칭률** — 질의가 토픽 라벨/alias에 직접 걸리는 비율
- **ancestor-only 매칭률** — 상위 개념으로만 흡수되는 비율(정밀도 손실을 안고 살아남는 경우)
- **전무율** — 어떤 토픽에도 안 걸리는 비율
- **캡 오염률** — 20개 캡에 걸리면서 상위 20개에 관련 토픽이 없는 비율(`ai` 유형)

이것이 "1차에 적당한가"를 감이 아니라 수치로 답한다. 재현 스크립트는 부록 B.

### 12.2 아직 잴 수 없는 것 — 공개 밀도

prod 적재 호출자도 토글 UI도 없어 현재 0이다. 대신 **출시 수용 기준을 지금 정의한다**:

- 질의당 gate 통과 공개 owner **하한**(예: ≥3). 미달이면 200+empty로 정직하게 답하고
  노이즈를 서빙하지 않는다
- 그 하한에서 역산한 부트스트랩 규모: 내부 코호트 몇 명 × 몇 토픽

### 12.3 런타임 계측기 (A단계에서 반드시 넣을 것)

- expansion 결과의 `/search/topics` 0건 비율 = **카탈로그 커버리지 지표**
- 매칭됐으나 공개 보유자 0 비율 = **공개 밀도 지표**
- `exhaustive` / `unranked_topics` / `truncated_descendants` 분포
- 우리 ordering 키와 topic-api `score` 순위의 불일치도(전문성 재가중이 실제로 순위를 바꾸는지)

---

## §13 재설계가 답해야 할 질문 (Fable 입력)

이 문서는 사실과 결정을 담았고, **설계는 하지 않았다.** 새 설계가 답해야 하는 것:

1. **호출 형태.** expansion → `/search/topics` → leaf fan-out → 병합의 각 단계를 어떤 컴포넌트가
   소유하는가. 기존 `discovery/` 구조(grounding / ranking / recommendation 단계 분리)의 어디에
   매핑되는가. NeedType·stance 파이프라인은 삭제 대상이다.
2. **병합 규칙.** 여러 leaf 결과를 owner 단위로 합칠 때 RRF인가 다른 것인가. topic별 기여도를
   어떻게 `matched_topics`로 축약하는가(대표 topic 선택 규율 — rev 14가 ranking 단계로 잠근 것).
3. **ordering 키의 정확한 식.** facets 5개에서 전문성 키를 어떻게 만드는가.
   `knowledge` 단독? 가중합? `confidence`를 곱하는가? relation 할인을 유지하는가?
   그리고 그 식이 **gate와 섞이지 않는다**는 것을 어떻게 구조로 보장하는가.
4. **실패 3분기의 판정 지점.** `/search/topics` 0건 → 422를 어디서 판정하는가.
   expansion이 여러 변형을 냈고 일부만 0건일 때의 규칙.
5. **eligibility(Q12)의 결합 지점.** topic-api는 eligibility를 모른다. leaf 결과를 받은 뒤
   필터하면 cap이 깎인다(§11-5와 같은 문제). 서버측 파라미터가 없을 때의 차선책.
6. **rerank 진입 조건.** C단계 판정층을 언제 켜는가. 항상? 특정 신호에서만?
   그 신호를 무엇으로 측정하는가.
7. **어댑터 경계.** topic-api 응답 모델을 우리 도메인 타입으로 어디서 변환하는가.
   composition root 규율(real provider만)과 어떻게 맞추는가.
8. **캐시.** 카탈로그는 하루 몇 번 변한다. `/search/topics` 결과를 우리가 캐시할 수 있는가.
   할 수 있다면 무효화 신호는 무엇인가.

---

## 부록 A — 근거 인덱스

`../bourbon-topic-api` (HEAD `296723d`):

| 주장 | 위치 |
|---|---|
| 역할별 라우터 마운트 | `api/depends/role.py` |
| leaf 경로 · stub 처리 | `topic/search/single.py` |
| rollup · 서브트리 · 분기 | `topic/search/service.py` |
| threshold 알고리즘 | `topic/search/threshold.py` |
| 스트림 bound | `topic/search/streams.py` |
| `find_by_name` · normalize · descendants | `topic/catalog/graph.py` |
| 카탈로그 Scan | `topic/catalog/repository.py:52-70` |
| 카탈로그 캐시(블로킹 재적재·stale 서빙) | `topic/catalog/cache.py:44-70` |
| id 파생 규칙 | `topic/catalog/ids.py` |
| GSI 쿼리 · `put_score` · `patch_settings` | `topic/user_topics/repository.py` |
| `RANKED_TIER` · tier 계열 | `topic/visibility/tiers.py` |
| facets · `ScoreInputs` · `Visibility` | `topic/structs.py` |
| 점수 공식 | `topic/persona_topics/scoring.py` |
| 후보 조립(3패스 캡) | `topic/persona_topics/candidates.py` |
| 병합 · `removed_topics` · `extras` | `topic/persona_topics/merge.py` |
| 추출 구조체 · `unmatched_signals` | `topic/persona_topics/structs.py` |
| LLM 프롬프트(signals / marking) | `cli/persona_topics/stages.py` |
| 추출 오케스트레이션 | `cli/persona_topics/extract.py` |
| `score_inputs` 노출 범위 | `api/routers/internal/structs.py` |
| 랭킹 응답(= `score_inputs` 없음) | `api/routers/search/structs.py` |
| score 주입 라우트 | `api/routers/internal/scores/router.py` |
| 카탈로그 관리 라우트 | `api/routers/internal/catalog/router.py` |
| 설정 기본값 | `topic/config.py` |
| 워커 수 · HPA | `k8s/overlays/*/deployment-patch.yaml`, `k8s/base/hpa.yaml` |

`../../iac` (origin/main `d364d3c`):

| 주장 | 위치 |
|---|---|
| DynamoDB 온디맨드 · GSI 정의 방식 | `terraform/modules/dynamodb/main.tf` |
| AOSS 컬렉션 그룹 · OCU 한도 | `terraform/env/dev/main.tf:352-376` |
| `bourbon-app` IRSA DynamoDB 권한 | `terraform/modules/iam/service/service_roles.tf:116-132` |
| 토픽 테이블 부재 | 전수 grep 결과 없음 |

`../bourbon-api` (origin/main `943b5f5`): `k8s/base/api-svc-dispatch.yaml` — `/api/svc/topic/` 미등록.
`../bourbon-agent` (HEAD `18fbcac`): topic-api 참조 0건. 페르소나는 `SHARABLE`/`PRIVATE` 2슬롯 ×
(bio/traits/preferences) 텍스트.

## 부록 B — 실측 재현

`bourbon-topic-api` 루트에서 `uv run --frozen python - <<'PY' ... PY`로 붙여 실행한다.
카탈로그 시드만 읽으므로 DB·네트워크가 필요 없다. `TopicGraph`가 topic_id로 dedupe하는 것을
같은 방식으로 재현하기 위해 qid 기준으로 접는다.

```python
import yaml
from pathlib import Path
from collections import Counter

def norm(v): return "".join(v.lower().split())      # normalize_search_text 와 동일

rows, seen, topics = [], set(), []
for p in sorted(Path("catalog_seeds/reviewed").glob("*.yaml")):
    d = yaml.safe_load(p.read_text())
    for c in (d.get("decided") or []):
        rows.append((d["group_key"], c["qid"], bool(c.get("include")),
                     c.get("distance"), c.get("decided_by")))
        if not c.get("include") or c["qid"] in seen: continue
        seen.add(c["qid"])
        l = c.get("labels") or {}
        topics.append((l.get("ko"), l.get("en"), l.get("ja"), c.get("aliases") or []))

kept = [r for r in rows if r[2]]
print(f"groups={len({r[0] for r in rows})} kept_rows={len(kept)} "
      f"unique_qid={len(seen)} dropped={len(rows)-len(kept)} "
      f"aliases={sum(len(t[3]) for t in topics)}")
print("depth:", Counter(r[3] for r in kept), " decided_by:", Counter(r[4] for r in kept))
print("per group:", Counter(r[0] for r in kept).most_common())

LIMIT = 20                                            # SEARCH_MAX_NAME_MATCHES
def find(q):
    n, hits, total = norm(q), [], 0
    for ko, en, ja, al in topics:                     # dict 삽입 순 = 그래프 순
        if any(n in norm(x) for x in [x for x in (ko, en, ja) if x] + al):
            total += 1
            if len(hits) < LIMIT: hits.append(en or ko or "?")
    return hits, total

for q in ["커피", "드립 커피", "핸드드립 커피 추출법", "machine learning", "머신러닝",
          "기계학습", "kubernetes", "ai", "quantum", "python", "dynamodb",
          "database", "위스키", "양자역학", "observability"]:
    h, t = find(q)
    print(f"{q:22} total={t:<5}{'CAP' if t > LIMIT else '   '}  first: {', '.join(h[:6])}")
```

§12.1의 커버리지 측정은 위 `find`에 eval 코퍼스의 질의 목록을 넣고, 결과를
exact / ancestor-only / 전무 / 캡 오염으로 분류하면 된다. ancestor-only 판정에는
부모 엣지가 필요하므로 `broader_qids`와 `placement`를 함께 읽어야 한다.

---

## 변경 이력

- **2026-08-21 초판** — `bourbon-topic-api` HEAD `296723d` 전수 분석. §2.1 표는 최초 작성 시
  추정값을 실측으로 제시한 오류를 발견해 실제 실행 결과로 교체했다(`머신러닝` 0→1,
  `machine learning` 3→5, `ai` 캡 20→총 560 및 상위 20개 전부 무관). 또한 첫 실측이
  리뷰 파일 행(2,617)을 순회해 중복 qid를 이중 계산했으므로, `TopicGraph`와 동일하게
  dedupe한 2,605개 기준으로 다시 측정했다(`ai` 562→560, `database` 6→5). §9의 ordering 키 항목도
  작성 중 "topic-api score를 정렬 키로" → "facets에서 우리가 만든다"로 철회·정정했다.
