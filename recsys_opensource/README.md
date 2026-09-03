# 오픈소스 추천·평가·랭킹 도구 조사

> **문서 지위**: 기술 검토 자료이며 설계 정본이나 도입 결정이 아니다. 현재 제품 설계는
> [`recommendation_scoring_design.md`](../recommendation_scoring_design.md), 현재 가동 계약은
> [`recommendation_pipeline_design.md`](../recommendation_pipeline_design.md)가 소유한다.
> 이 디렉토리는 설계를 다시 유도하는 병렬 문서가 아니라 **판단의 근거 survey**다.
> 요구사항·채택·기각은 설계 문서를 고치고, 여기에는 도구의 계약·비용·반례를 남긴다.
>
> **증거 등급**: `문서`(공식 문서·저장소로 확인) · `실측`(실제로 실행해서 확인) · `판단`(의견) ·
> `열린 항목`(협의·측정·제품결정 대기).
> **두 등급을 섞지 않는다** — §8에 문서 근거 주장 다섯 개가 실행으로 뒤집힌 목록이 있다.
>
> 문서 조사 기준일 2026-08-28 · 실측 기준일 2026-09-01 (Gorse v0.5.11).
> 논의 기록은 [`recsys_adoption_discussion.md`](../recsys_adoption_discussion.md).

### 조사 장과 상태

| 장 | 문서 | 상태 | 쓰이는 자리 |
|---|---|---|---|
| CF·추천 도구 | [Gorse](gorse.md) · [Cornac](cornac.md) · [implicit](implicit.md) · [Surprise](surprise.md) | 1차 조사 완료 + Gorse는 실측 | §6·§7 |
| off-policy 평가 | [off_policy.md](off_policy.md) | 초안 | §9의 노출 계약을 **이 문서가 소유** |
| learned reranking | [ranking.md](ranking.md) | 초안 | §7의 rerank 층 |
| 집중도·공급 지표 | [concentration_metrics.md](concentration_metrics.md) | 초안 | §9의 hard capacity·집중도 |
| **저장소 규모·비용** | [storage_sizing.md](storage_sizing.md) | 초안 | §11의 카디널리티에 AWS 단가(도쿄·서울)를 붙이고 managed 대 자체 운영을 비교한다. **`gorse.md` §6-2가 비워 둔 칸** |
| **feedback 의미론** | [feedback_semantics.md](feedback_semantics.md) | 초안 | §4의 observed behavior를 실제로 엔진에 넣을 때. **`gorse.md` §7-5가 멈춘 지점**이고 `inbound_event_contract.md` §3-4의 투영 규칙 근거 |
| **retrieval·검색 색인** | **없음** | **빈칸** | §7-5. 이전 판에서 "현재 topic-api가 유계 후보를 만들므로 불필요"로 배제했으나 그 전제가 열렸다 |

---

## 1. 이 조사가 답하는 질문 — 표면이 둘이다

제품의 추천 표면은 둘이고, **recsys 관점에서 서로 다른 문제**다. 이 구분이 이 문서 전체의 축이다.

```text
표면 1   topic / context 질의 있음   →  그 주제를 잘 아는 agent
         질의가 있다. 검색에 가깝다.

표면 2   질의 없음                   →  이 사용자의 활동 기반으로 agent 여럿
         질의가 없다. 이것이 추천 시스템의 정확한 정의다.
```

`판단` **표면 2는 추천 라이브러리의 메인 API 그 자체다.** `recommend(user_id, N)` — Gorse의 제품
전체가 이것이고, implicit·Cornac의 기본 호출이 이것이다.

`판단` **표면 1은 아니다.** 추천 라이브러리는 요청 시점에 질의를 받지 않는다.

두 방향으로 틀릴 수 있다. 표면 2를 표면 1의 요구(요청별 권한 필터·임의 allowlist·질의 처리)에 맞추면
기성 도구를 못 쓰고, 표면 1을 표면 2에 맞추면 질의가 무시된다. **이전 판의 주된 오류가 전자였다** —
표면 1의 요구를 두 표면 모두의 요구로 다뤘다.

---

## 2. 표면 × 층 — 도구 배치

비교 축은 "도구"가 아니라 **표면 × 층**이다. 같은 도구가 한 표면에서는 엔진이고 다른 표면에서는
오답이다.

| 층 | 표면 1 (질의 있음) | 표면 2 (질의 없음) |
|---|---|---|
| **grounding** | 우리 (자연어 → topic + 하위 라벨) | 해당 없음 |
| **후보 생성** | Gorse 라벨별 질의(§7-3) 또는 검색 색인(§7-5, 빈칸) | **Gorse** `recommend(user)` |
| **자격 gate** | 우리 (§9) | 우리 (§9) |
| **순위** | 우리 랭커 — coverage·depth·focus ([ranking.md](ranking.md)) | Gorse 순서 + 우리 후처리 |
| **탐색·노출 로그** | 우리 ([off_policy.md](off_policy.md)) | 우리 |
| **오프라인 비교** | Cornac · off-policy | Cornac · off-policy |

`판단` **표면 2에서 Gorse는 통째로 쓰고, 표면 1에서는 후보 생성기까지만 쓴다.** 근거는 §6·§7.

---

## 3. 공통 도메인 모델

현실의 엔티티는 모두 사용자지만 추천에서는 역할이 둘이다.

```text
requester User                         candidate Personal Agent
추천을 받는 사람                       추천되는 사람의 agent
원하는 topic·성향·행동 이력             제공 가능한 topic·성향·공개 정보
                    └──── 추천 ────┘
```

따라서 기본 표현은 같은 사람을 한 정적 feature로 두 번 읽는 대칭 user-to-user보다 다음의 비대칭
user-item 표현이다.

```text
UserId = requester_user_id
ItemId = personal_agent_id              # owner_user_id에서 고정식으로 유도
Interaction = requester가 agent를 노출·선택·대화·재방문한 사건
```

`private` interest는 소유자 자신의 추천에는 쓸 수 있어도 그 소유자를 타인에게 추천하는 근거가 되어서는
안 된다. `friends` interest는 requester와 owner의 관계에 따라 candidate 표현이 달라진다. 기본적인 대칭
유사도와 전역 캐시는 이 차이를 표현하지 못한다.

`열린 항목` **R1 — 표면 2가 `friends` 보유까지 근거로 삼는가.** `public`만이면 요청자별 변동이 없어
전역 item label로 충분하고 Gorse가 성립한다. `friends`까지면 전역 label에 요청자별 근거를 넣을 자리가
없고, 넘치게 받아 거르는 방법은 **빼는 것만 되고 더하는 건 안 되므로** friends 공개 후보가 누구에게도
나오지 않는다. **기술이 아니라 제품 결정이고, §6의 전제다.**

---

## 4. 세 데이터를 분리한다

```text
declared profile      사용자가 명시적으로 관리, 장기      cold start·장기 preference
ephemeral query intent  요청 한 건, 짧은 수명            표면 1의 후보 제약
observed behavior      실제 사건으로 append              별도 projection 후 학습
```

`판단` **이 분리가 표면 둘을 가르는 것과 같은 선이다.** 표면 1은 ephemeral query intent를 읽고,
표면 2는 declared profile + observed behavior를 읽는다.

이번 요청이 `topic=커피`라고 해서 사용자의 장기 interests에 커피가 추가되지 않는다. 추천 요청은
inference이고 profile mutation도 model update도 아니다.

```text
추천 요청              interaction 없음
실제 노출              exposure 분모, positive 아님
선택                   정의된 경우 positive 후보
대화·재방문·해결       aggregation 규칙 통과 후 학습 반영
"관심사에 추가" 명시    declared interests 변경
```

**금지**: `recommend(topic=X)` → `user.interests += X`, `exposed(agent)` → confidence += 1.
노출은 학습에 중요하지만 positive가 아니라 **선택 기회와 평가 분모**다.

---

## 5. visibility는 feature weight가 아니라 gate다

| tier | 모델 입력 원칙 | 서빙 원칙 |
|---|---|---|
| `public` | candidate feature에 포함 가능 | 모든 requester에게 사용 가능 |
| `friends` | 전역 candidate feature·전역 캐시에 넣지 않음 | 관계 확인 후 후보 생성·rerank에서만 |
| `private` | 타인 대상 candidate 학습에서 제외 | 소유자 자신의 개인화도 별도 승인 시에만 |

최종 응답에서 숨기기만 하면 충분하지 않다. **금지된 feature가 후보 생성이나 점수에 들어가면 순위
자체가 그 사실을 간접 노출한다.** gate는 모델 뒤의 redaction이 아니라 모델 입력과 후보 집합을 정하는
앞단 계약이어야 한다.

`판단` **가장 강한 보호는 받지 않는 것이다.** 우리 색인·store에 공개 투영만 들어오면 "공개 → 비공개
전환"이 *집합에서 빠지는 것*으로 도착하고, 민감 데이터가 우리 쪽에 존재하지 않으므로 위 누출 경로가
구조적으로 닫힌다.

---

## 6. 표면 2 — Gorse

`판단` **표면 2는 Gorse가 하는 일 그 자체이므로 직접 만들 이유가 없다.**

```text
이벤트 → Gorse 에 user/item/feedback 적재
표면 2 → GET /api/recommend/{user}?n=20 → 본인·차단 후처리 제거 → 응답
```

우리가 만드는 것: 동기화 워커 · 얇은 클라이언트 · 후처리 필터.
우리가 **안** 만드는 것: 학습 scheduler · model artifact·refresh · serving API · cache · dashboard.

### 6-1 이전 판의 기각 사유 재평가

이전 판은 Gorse를 사실상 기각했다. 사유 셋 중 둘은 **표면 2에서 성립하지 않는다.**

| 이전 기각 사유 | 재평가 |
|---|---|
| 요청자별 공개 범위를 표현 못 함 | **표면 1의 요구였다.** 표면 2 근거를 `public`으로 한정하면 요청자별 변동이 없다. 물어보지도 않은 사용자에게 friends 공개 전문성을 근거로 대는 것은 표면 2에서 오히려 부적절할 수 있다 → **R1의 제품 결정 문제** |
| 1억 사용자 캐시 카디널리티 | **미래 규모를 현재 결정의 기각 사유로 썼다.** §11에서 별도로 다룬다 |
| 노출 스키마를 엔진이 소유 | **사실이지만 과장했다.** Gorse feedback(엔진의 학습 입력)과 우리 노출 스트림(우리의 측정)은 병존한다. 잃는 것은 Gorse 자신의 순서를 재현·오프폴리시 평가하는 능력이고, 이는 분석 능력의 손실이지 출시 블로커가 아니다 |

★ **규율: 미래 규모를 현재 결정의 기각 사유로 쓰지 않는다.**

### 6-2 남는 조건

- **R1이 `public`으로 결정되어야 한다**(§3). `friends`면 구조적으로 막힌다.
- 본인·차단 제외는 후처리. `실측` `/api/item-to-item/…?user-id=` 로 이력 있는 후보를 제외할 수
  있으므로 합성 피드백으로 self-exclusion을 넣을 여지도 있다.
- 노출 로그는 우리 형식으로 **병행 기록**한다(§9). 이것이 Gorse 채택을 되돌릴 수 있게 만드는 유일한 장치다.

---

## 7. 표면 1 — CF가 아니다

### 7-1 `실측` CF 라이브러리는 원리적으로 다른 것을 계산한다

topic × agent 행렬을 만들어 `implicit`의 BM25 item-item에 질의한 결과. 보유자: `bob`{coffee,espresso}
`carol`{coffee,roasting,drip} `dave`{drip} `erin`{hiking,photo} `generalist`{전부}.

| 질의 | implicit item-item | 올바른 정식화 (BM25 문서검색) |
|---|---|---|
| `coffee` | **generalist** 1.01 / bob .69 / carol .63 / erin .40 / dave .11 | **bob** .61 / carol .52 / generalist .37 / dave 0 / erin 0 |
| `drip` | **generalist** .82 / carol .64 / erin .40 / bob .29 / **dave .20(꼴찌)** | **dave .73** / carol .52 / generalist .37 / bob 0 |

**원인**: item-item은 **동시 출현 유사도**를 계산한다. 질의가 실제로 묻는 것은 "이 주제 보유자들과
*비슷한* 사람"이고, `generalist`는 누구와도 비슷하므로 항상 이긴다. 교과서적 인기도 편향이다.

우리 질문은 "이 주제를 **대표하는** 사람"이고 그것은 **검색**이다 — 문서=agent(보유 주제 묶음),
단어=topic_id, 질의=확정 주제들. 그러면 미보유자 0점 · IDF가 희소 주제 전문가를 올림 · 길이
정규화가 generalist를 누름이 저절로 성립한다.

★ **규율: 라이브러리 함수 이름이 같아도 계산이 같지 않다.** `implicit`의 BM25는 *CF 가중치*이지
정보검색의 BM25가 아니다.

### 7-2 `실측` Gorse의 두 기성 경로는 둘 다 인기도를 준다

| 경로 | 결과 |
|---|---|
| `?category=<topic>` | 후보 집합은 **정확히** 좁혀진다. 그러나 `gen`(6주제·피드백 12건)이 `drip` 질의에서 `dave`(drip 전담·피드백 0건)를 이긴다 |
| 결합 태그 질의 (더미 topic item에 하위 라벨 전부) | `generalist` 1등, **찾으려던 `broad`(상위+하위 전부 보유)는 결과에서 누락** |

후자의 누락은 **질의와 태그 집합이 동일한 item이 이웃에서 제외되기** 때문이다. 질의 태그를 늘릴수록
정답이 제외될 확률이 올라간다.

`판단` 두 경로 모두 잠근 원칙("첫날 항으로 인기도를 쓰지 않는다")과 걸린다.

### 7-3 `실측` 성립하는 형태 — 라벨별 개별 질의 + 가중 합산

전제 둘: **하위 라벨 보유가 상위 라벨 보유를 함의한다**(제품 사실) · 질의 1회 오버헤드가 작다.

```text
grounding(우리) → 확정 topic + 하위 라벨들
   → 라벨마다 Gorse item-to-item 질의            실측 ~1.1 ms/호출
      (더미 topic item, 센티넬 태그 포함)
   → 가중 합산  상위≈0, 하위에 가중              ← 가중치가 우리 것이 된다
   → 후보 + coverage 점수
   → rerank(우리): coverage + depth + focus + 언어 + 활동성 + 권한
```

**동일 태그 제외가 두 가지로 해소된다.**

| 질의 | 센티넬 없음 | 센티넬 있음 |
|---|---|---|
| 상위 라벨 | 상위만 보유한 agent **누락** | 누락 없음 |
| 하위 라벨 | 누락 없음 (함의 때문에 태그 집합이 같아질 수 없다) | 누락 없음 |

센티넬은 어떤 agent도 갖지 않는 태그(`__QUERY__`)를 질의 item에 하나 넣는 것이다. 어떤 후보와도
매칭되지 않아 분자 기여가 0이고, 분모는 후보별 상수라 순서에 영향이 없다.

**가중치가 순서를 실제로 통제한다** (가중 합산 결과):

| 가중 | 결과 |
|---|---|
| 균등 (상위1·하위1×4) | **broad** 3.88 > partial 2.90 > narrow 2.32 > generalist 1.94 > parentonly 1.60 |
| 하위 강조 (상위1·하위3) | broad 10.44 > partial 7.03 > **generalist 5.21** > narrow 4.79 |
| 상위 강조 (상위4·하위1) | **parentonly 6.40** > broad 5.70 > narrow 5.56 > partial 5.43 |
| 좁은 질의 (coffee1·drip5) | **narrow 7.26** > partial 5.66 > broad 4.07 > generalist 2.03 |

★ `판단` **상위 라벨은 랭킹 신호가 아니라 recall 장치다.** 하위가 상위를 함의하므로 subtree 안
모두가 상위 라벨을 갖고, IDF가 낮아 변별력이 없다. 상위 가중을 올리면 **라벨 하나만 달린 가장 얕은
보유자가 1등**이 된다. 상위 질의는 후보를 긁어오는 데 쓰고 랭킹 가중은 하위에 준다.

좁은 질의에서 좁고 깊은 전문가가 1등이 되는 것(마지막 행)이 **질의 구체성이 보존된다**는 증거다.
확장은 아래로만, 질의가 일반적인 만큼만 한다.

### 7-4 `실측` 이 형태로도 Gorse가 못 하는 것

| | 실측 |
|---|---|
| **깊이 표현** | 세 인코딩 전부 실패 — 객체 `{"coffee":5}`는 태그로 안 읽힘 · 반복 `["coffee"×5]`는 `["coffee"]`와 동점 · 별도 태그 `tea@L5`는 **역방향**(깊이 태그 없는 쪽이 위) |
| **focus** | "그 사람 보유 전체 중 이 subtree 비중"을 Gorse가 주지 않는다. 하위 강조 시 generalist가 narrow를 앞지르는 원인 |
| 미보유자 혼입 | 이웃 결과에 매칭 0인 후보가 기본값으로 섞인다 |
| `POST /api/session/recommend` | 이 빌드에서 모든 조합에 200 + `null` |

`판단` 앞의 둘은 **애초에 rerank에서 우리가 하기로 한 것**이므로 Gorse 쪽 미해결 제약은 사실상 없다.
깊이·focus는 우리 store에서 읽어 랭커 feature로 넣는다([ranking.md](ranking.md)).

`판단` **미보유자 혼입만 성격이 다르다 — 품질이 아니라 계약 문제다.** 우리 응답은 추천마다 근거
topic을 필수로 요구하므로 질의 topic을 보유하지 않은 후보는 **응답을 만들 수 없다.** 따라서 이 필터는
옵션이 아니라 **표면 1에서 Gorse가 후보를 추가할 수 있게 하는 전제**이고, 판정은 Gorse 점수가 아니라
우리 store의 `public_topics` 목록으로 한다. 상세는 [gorse.md §11-3](gorse.md).

### 7-5 `열린 항목` retrieval·검색 색인 — 조사 빈칸

7-1이 보인 올바른 정식화는 **역색인 + BM25**다. 7-3은 그것을 Gorse의 더미 item 트릭으로 얻는 경로이고,
직접 색인을 갖는 경로는 조사된 바 없다.

이전 판은 "현재 topic-api가 요청별 유계 후보를 만들기 때문에 조사 범위의 빈칸이 아니다"로 이 계열을
배제했다. **그 전제가 열렸다** — topic-api를 라벨·계층 제공자로 축소하는 안이 논의 중이다.
비교 대상: Lucene 계열 임베디드 · Postgres BM25 확장 · OpenSearch · Vespa.

`판단` 규모가 맞을 때까지는 클러스터를 사올 이유가 없고, BM25는 표준이라 나중에 갈아타기 쉽다.
다만 **비교표에 자리는 있어야 한다.**

---

## 8. `실측` 문서 근거가 뒤집힌 목록

Gorse v0.5.11을 실제로 실행해 확인. 이 목록이 §0의 증거 등급이 존재하는 이유다.

| # | 문서 근거 판단 | 실측 |
|---|---|---|
| 1 | 요청별 임의 후보 제한은 표준 endpoint에 없음 | **더미 topic item + 이웃 질의로 가능.** 숨긴 item(`IsHidden=true`)도 이웃이 계산·서빙된다 |
| 2 | (서술 없음) | **질의와 태그 집합이 같은 item은 이웃에서 제외된다.** 사양서로 예측 불가이고 이 용도에서 치명적이었다 |
| 3 | (서술 없음) | **이웃 갱신 주기를 지배하는 것은 `[recommend] cache_expire`다.** 기본 72h. 파이프라인이 60초마다 돌아도 이 값 전에는 재계산되지 않는다 |
| 4 | (서술 없음) | 재계산 비용 **≈10 ms/item**, 2,000개까지 선형. 상위 라벨을 다수가 공유하는 계층 편중이 비용을 키우지 않았다 |
| 5 | (서술 없음) | `--playground`는 **재시작마다 설정을 재생성하고 데이터를 재임포트**한다. 설정을 바꾸려면 playground 없이 띄운다 |

★ **규율: 문서에 없는 동작은 문서가 아니라 실행이 답한다.** 2·3은 서술 자체가 없었고, 둘 다 채택
판단을 바꾸는 크기였다.

★ **규율: 같은 증상에 두 원인 후보가 있으면 값싼 쪽(캐시)을 먼저 배제한다.** 신규 item이 안 보이는
것을 알고리즘 성질(중복 태그 접힘)로 추정했으나 틀렸고, 원인은 3이었다. 알고리즘이면 설계를 바꾸게
되고 캐시면 값 하나를 바꾼다.

---

## 9. 도구와 무관하게 우리 제품이 계속 소유할 것

다음 책임은 라이브러리의 기능 부족 때문에 임시로 남는 것이 아니다. 제품 의미와 권한을 정하는 계약이므로
어떤 도구를 선택해도 우리 시스템이 소유한다.

| 책임 | 왜 모델이나 외부 추천 서비스에 넘길 수 없는가 |
|---|---|
| requester-aware visibility | `friends`는 requester–owner 관계에 따라 달라지고 `private`은 타인 추천 근거가 되어서는 안 됨 |
| topic grounding | 자연어 요청을 catalogue topic과 `grounded/failed/ambiguous`로 확정하는 제품 의미가 있음 |
| self-exclusion | 같은 사람이 requester와 candidate 양쪽 역할에 존재하므로 ID·owner 관계를 알아야 함 |
| safety·eligibility | 차단, 삭제, 정책 변경은 학습 점수보다 먼저 적용되어야 함 |
| recommendable opt-in | public topic 보유와 모르는 사람에게 추천되는 데 동의한 것은 다른 계약임 |
| hard capacity | 실제로 새 대화를 받을 수 없는 owner는 큰 선호 점수로 되살아나면 안 됨 |
| 재추천 간격·시간 감쇠 | Gorse의 replacement는 되돌아올 수 있게 하는 스위치와 **상수 감쇠**까지고 시간 축이 없다 — 어제 만난 상대와 석 달 전 만난 상대를 구분하지 못한다([`feedback_semantics.md`](feedback_semantics.md) §2-4) |
| final response assembly | matched topic, relation, description, owner note와 설명은 모델의 ID·score 출력에 없음 |
| exposure semantics | 무엇을 실제 노출로 셀지, 후보 집합·position·conditional propensity·ranker/policy version을 어떻게 남길지는 제품 실험 계약임 |

Gorse는 feedback을 저장할 수 있고 다른 도구도 event를 입력으로 받을 수 있다. 하지만 "저장할 수 있다"와
"노출의 의미를 소유한다"는 다르다. **전체 노출 계약은 [`off_policy.md` §3](off_policy.md)이 소유한다** —
여기서 필드를 다시 정의하지 않는다.

`판단` 표면이 둘이 되면서 이 표에 축이 하나 붙는다. **두 표면의 피드백이 한 곳으로 모여야 한다** —
표면마다 다른 엔진을 쓰면 학습 루프가 갈라진다. 원본은 우리 스트림 하나이고 Gorse에는 투영만 보낸다.

---

## 10. 도구에 따라 달라지는 운영 책임

| 운영 책임 | Gorse | Cornac | implicit | Surprise |
|---|---|---|---|---|
| feedback ingestion/store | 제공 기능 활용 가능 | 직접 구축 | 직접 구축 | 직접 구축 |
| 학습 scheduler/worker | 제공 | 직접 구축 | 직접 구축 | 직접 구축 |
| model artifact와 refresh | 플랫폼 흐름 활용 | 직접 계약 | 직접 계약 | 직접 계약 |
| online recommendation API | 제공 | 직접 구축 | 직접 구축 | 직접 구축 |
| raw↔integer ID map | 내부 소유 | artifact와 함께 관리 | 반드시 직접 관리 | trainset/artifact와 관리 |
| cache와 dashboard | 제공 기능 있음 | 직접 구축/외부 도구 | 직접 구축/외부 도구 | 직접 구축/외부 도구 |
| **이웃 갱신 주기** | **`cache_expire` 설정 하나** (`실측`) | 해당 없음 | 직접 구축 | 직접 구축 |

도입 판단에서 실제로 비교할 부분은 이 표다. 앞 절의 제품 책임은 없앨 수 없지만, 이 운영 책임은 플랫폼을
채택해 줄일 수도 있고 작은 library adapter로 직접 소유할 수도 있다.

다만 "제공"은 "무료"가 아니다. Gorse를 선택하면 자체 구현 코드는 줄어도 별도 DB·cache·worker의 배포,
network auth, schema sync, retry, readiness와 version 호환 책임이 생긴다.

---

## 11. 규모 — 표면마다 병목이 다르다

"사용자가 1억 명이다"만으로 크기를 정할 수 없다. 네 cardinality를 따로 측정한다.

이 절은 크기를 센다. 그 크기에 AWS 단가를 붙이고 backend 넷을 비교한 것은
[`storage_sizing.md`](storage_sizing.md)이고, 그 문서의 결론은 **1억 전제에서 병목이 저장소
비용이 아니라 아래의 재계산 시간**이라는 것이다.

```text
U_registered   전체 가입자                          최대 100,000,000
U_active       학습 기간에 유효 행동이 있는 requester
I_eligible     현재 추천 가능한 personal agent
I_request      한 요청에서 grounding·gate를 통과한 후보    수십~수천
```

### 표면 2의 병목 — 캐시 카디널리티

Gorse는 사용자별 추천을 미리 계산해 캐시한다.

```text
100,000,000 users × cached top 100 = 10,000,000,000 entries
entry 당 16 bytes 가정만 해도 160 GB (row/key/index/replication 제외)
```

`판단` **완화 경로는 전원을 넣지 않는 것이다** — 최근 활동 사용자만 projection하고 장기 비활성은
Gorse 밖 cold-start 규칙으로 둔다. lazy projection은 첫 요청 지연·삭제 동기화 비용을 만드므로
full / active-window / on-demand 세 가지를 1%→10%→목표로 부하 시험한다.

### 표면 1의 병목 — 재계산 시간

```text
반영 지연 = max( cache_expire, 전면 재계산 시간 )
전면 재계산 ≈ 10 ms × 전체 item 수      (`실측`, 2,000개까지 선형. 증분 갱신 없음)
```

선형 가정 하 대략치 — **1만 ≈ 100초 · 10만 ≈ 17분 · 100만 ≈ 3시간.**

`열린 항목` **2,000개 너머는 미검증.** 태그 유사도의 후보 생성은 흔한 태그 하나 안에서 보유자 수에
이차적일 수 있고, 이 실험은 상위 라벨당 보유자 250명까지만 갔다. **목표 규모에서 재계산 시간을
실측하기 전에는 `cache_expire` 하한을 약속할 수 없다.**

### 신선도의 두 등급

| 무엇의 신선도인가 | 판정 |
|---|---|
| 새 topic 학습 · 보유 강도 변화 | **`cache_expire`로 조절.** 분~십수분 지연은 문제가 아니다 |
| 차단 · 삭제 · 추천 자격 상실 | **캐시에 의존하지 않는다.** 우리 store에서 서빙 시점에 읽고, 최종 N명을 원본으로 재확인한다 |

`판단` 후자는 정보 유출 문제가 아니다 — §5의 원칙(공개 투영만 받는다)이 그것을 이미 닫는다.
남는 것은 **"이 사람을 이 사람에게 보여주지 않는다"**이고, 하류의 내용 gating이 대신할 수 없다.

### CF 모델을 쓰게 될 때의 메모리 하한

```text
factor 64, float32:  user 1억 25.6 GB + item 1억 25.6 GB = 51.2 GB (runtime overhead 전)
평균 interaction 20개면 nnz=20억, CSR value+col index 만 약 16 GB
```

`판단` 등록 사용자 전부를 dense factor row로 만드는 것은 기본안이 아니다. `U_active=1천만`,
`I_eligible=5백만`, factor 64면 factor 하한은 약 3.84 GB로 줄어든다. **"가입자 1억"과 "모델 row 1억"은
같은 결정이 아니다.**

---

## 12. 단계별 판단 순서

```text
0. 제품 결정         R1 (표면 2 의 friends 포함 여부) 을 먼저 닫는다
                     이것이 §6 의 전제다

1. 노출 계약          exposure/decision 스키마를 고정하고 기록을 시작한다
                     off_policy.md §3 이 소유.  나중에 만들 수 없는 유일한 항목

2. 표면 2            Gorse 적재 + 클라이언트 + 후처리 필터
                     기성 기능만으로 처음부터 끝까지 선다

3. 표면 1            grounding + 라벨별 질의 + 가중 합산 (§7-3)
                     rerank 는 규칙으로 시작

4. 랭커              라벨이 쌓이면 LR → GBDT (ranking.md)
                     coverage · depth · focus 를 feature 로

5. 평가              Cornac 비교 + off-policy 추정
                     "다른 순서였으면" 에 답할 수 있게 된다

6. 재검토            retrieval 색인 직접 소유 (§7-5)
                     후보 pool 이 커지거나 벡터 검색이 필요해지면
```

`판단` **1을 2·3보다 먼저 두는 이유는 소급 불가이기 때문이다.** 모델도 색인도 다시 만들 수 있지만
지난달 노출은 그때 기록하지 않으면 복구할 수 없다. 그리고 이 기록이 있어야 §6의 Gorse 채택이
되돌릴 수 있는 결정이 된다.

---

## 13. 열린 항목

| # | 항목 | 성격 | 상태 |
|---|---|---|---|
| **R1** | 표면 2가 `friends` 보유까지 근거로 삼는가 | 제품 결정 | **미정. §6의 전제** |
| R2 | 표면 1이 `friends` 보유까지 포함하는가 | 제품 결정 | 미정. `public`만이면 배치 색인으로 충분 |
| R3 | 목표 규모에서 재계산 시간 (§11) | 측정 | 2,000개까지만 검증 |
| R4 | 실제 보유 데이터에서 §7-3 형태의 품질 | 측정 | fixture는 합성 6명. 메커니즘 대조까지만 유효 |
| R5 | 두 표면의 피드백을 한 스트림으로 모으는 방법 | 설계 | 미설계 |
| R6 | retrieval 색인 직접 소유 시의 비교표 (§7-5) | 조사 | 빈칸 |
| R7 | 상위 라벨 가중을 0으로 둘 때 recall 손실 | 측정 | §7-3 판단의 검증 |

---

## 14. 이 문서가 하지 않은 것

- **도구를 도입하지 않았다.** §6·§7은 판단이고 선택이 아니다. 채택·기각은 설계 문서가 소유한다.
- **실제 데이터로 재보지 않았다.** §7의 실측은 합성 fixture(6~19 item)이고 **메커니즘 대조**까지만
  유효하다. 품질 주장이 아니다.
- **노출 필드를 정의하지 않았다.** [`off_policy.md` §3](off_policy.md)이 소유한다.
- **R1을 답하지 않았다.** 답이 없으면 §6은 조건부 판단이다.
- **retrieval 계열을 조사하지 않았다**(§7-5). 이전 판의 배제 전제가 열렸다는 것까지만 기록했다.
- **어느 팀에도 발신하지 않았다.**

## 15. 공식 자료

- [Gorse](https://github.com/gorse-io/gorse) · [data model](https://gorse.io/docs/concepts/data-source) ·
  [pipeline](https://gorse.io/docs/concepts/pipeline) · [item-to-item](https://gorse.io/docs/concepts/recommenders/item-to-item)
- [Cornac](https://github.com/PreferredAI/cornac) · [data/modalities](https://cornac.readthedocs.io/en/stable/api_ref/data.html)
- [implicit](https://github.com/benfred/implicit) · [model API](https://benfred.github.io/implicit/api/models/recommender_base.html)
- [Surprise](https://github.com/NicolasHug/Surprise) · [top-N FAQ](https://surprise.readthedocs.io/en/stable/FAQ.html)
