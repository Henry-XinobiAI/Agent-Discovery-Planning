# 결정 레지스터

> **이 문서가 결정을 소유한다.** 설계 문서는 **설계**를 갖고 결정을 갖지 않는다. 어떤 문서의 본문이
> 이 레지스터와 다르게 읽히면 **이 레지스터가 맞고 그 문서가 낡은 것**이다.
>
> **왜 생겼나**: 2026-09-03 전수 감사에서 같은 사안이 문서마다 다르게 결정되어 있는 것이 여러 건
> 발견됐다. 가장 큰 것은 **Gorse 채택**이다 — `README.md`가 "도입 결정은
> `recommendation_scoring_design.md`가 소유한다"고 지정해 두었는데, 그 문서 §9-2는 기각으로,
> `recsys_opensource/`는 채택으로 적혀 있었다. 절을 고치는 것만으로는 다시 갈라진다. 결정의
> **소유가 한 곳**이어야 한다.
>
> **규칙 넷**
> ① 결정은 여기에만 적는다. 설계 문서는 `D**nn**`을 인용한다.
> ② 뒤집힌 결정은 설계 문서 **본문에서 삭제**하고 §2에 세 줄로 남긴다. 본문에 옛 결론을 남기지 않는다.
> ③ 결정되지 않은 것은 결정된 것처럼 쓰지 않는다. 문서 간 충돌은 결정 부재의 신호이므로 §3에 모은다.
> ④ 열린 항목은 각 문서가 갖되 **ID에 문서 접두사**를 붙인다(§5).
> ⑤ **각 결정에 출처를 적는다** — `오너`(오너가 직접 말한 것) · `승계`(이전 문서가 이미 결정으로
> 갖고 있던 것) · `분석`(이번 조사가 근거를 만들어 올린 것, **오너 확인 전**). 규칙 ③을 지키려면
> 셋이 같은 무게로 보여서는 안 된다.
>
> **마지막 갱신**: 2026-09-03

---

## 1. 현재 유효한 결정

### surface와 도메인

| # | 결정 | 근거·상세 | 출처 | 확정 |
|---|---|---|---|---|
| **D01** | **surface가 둘이다.** 쿼리가 있는 surface 1과 쿼리가 없는 surface 2는 다른 문제다 | `recsys_opensource/README.md` §1 | 승계 | 2026-09-01 |
| **D02** | **surface 2는 응답 형태가 다르다.** 기존 `/recommend`는 topic이 있는 경우로 한정한다 | D08 — surface 2에는 붙일 근거 topic이 없다 | 오너 | 2026-09-03 |
| **D03** | `UserId = requester_user_id`, `ItemId = personal_agent_id`(owner에서 결정론적 유도) | `recsys_opensource/README.md` §3 | 승계 | 2026-09-01 |
| **D04** | **visibility는 feature weight가 아니라 gate다.** 금지된 tier가 후보 생성이나 점수에 들어가면 순위 자체가 그 사실을 누설한다 | `recsys_opensource/README.md` §5 | 승계 | 2026-09-01 |
| **D05** | **self-exclusion은 우리 후처리로 한다.** 서버측 `exclude_user_ids` 요청은 철회했다 | `recommendation_pipeline_design.md` §1 | 승계 | 2026-08-24 |

### 엔진

| # | 결정 | 근거·상세 | 출처 | 확정 |
|---|---|---|---|---|
| **D06** | **Gorse를 채택한다.** surface 2는 통째로, surface 1은 후보 생성기로 | `recsys_opensource/README.md` §2·§6 · `gorse.md` §11 실측 | 오너 | 2026-09-03 |
| **D07** | **surface 1에서도 Gorse가 후보 소스다.** topic-api의 보유자 랭킹(`/topics/{id}/users`)을 후보 생성에 쓰지 않는다 | `gorse.md` §11-2 경로 C. topic-api의 100명 단일 컷이 **라벨별 100 컷으로 쪼개진다**(`cache_size`, `gorse.md` §12-2 — rev 1의 "상한이 사라진다"는 과장이었다). 대규모에서 성립하는지는 **C11** | 오너 | 2026-09-03 |
| **D08** | **미보유자 필터는 필수다.** 쿼리 topic을 증명 가능하게 보유하지 않은 후보는 근거를 붙일 수 없으므로 **응답을 만들 수 없다.** 판정은 Gorse 점수가 아니라 우리 데이터로 한다 | `gorse.md` §11-3 | 오너 | 2026-09-03 |
| **D09** | Gorse에 보내는 것은 **프로젝션**이고 원본은 우리 이벤트 스트림이다. Gorse store는 파생물이며 재실행으로 재구축 가능해야 한다 | `gorse.md` §8-1 · `inbound_event_contract.md` §3-4 | 승계 | 2026-09-01 |

### 저장

| # | 결정 | 근거·상세 | 출처 | 확정 |
|---|---|---|---|---|
| **D10** | **우리는 공개 보유의 복제본을 유지한다.** 델타가 아니라 전체 집합 + `revision` | `inbound_event_contract.md` §2-⓵ (발신 측 수용 가능 확인) | 승계 | 2026-09-01 |
| **D11** | **복제본이 주지 못하는 값이 다섯 개다** — `owner_notes` · `relation` · `descriptions` · `deep_holdings_observed` · `ranking_contribution`. 앞의 넷은 topic-api가 답하는 **matched 트리**에서 오고 복제본은 평평한 목록이다. **따라서 최종 N명에 대한 topic-api 조회는 최적화가 아니라 필수다** | `recommendation_pipeline_design.md` §S6-5. 다섯 값이 사실이라는 것은 확인됐고 "그러므로 필수"는 이번 분석의 결론이다. **다만 다섯 값을 응답에서 빼기로 하더라도 호출은 남는다** — `inbound_event_contract.md` §4의 서빙 시점 재확인이 **같은 호출**이고 그쪽은 안전 요구다(D21) | **분석** | 2026-09-03 |
| **D12** | **공개 프로젝션만 받는다.** `friends`·`private` 보유는 애초에 받지 않는다 — 가장 강한 보호는 받지 않는 것이다 | `inbound_event_contract.md` §2-⓶ | 승계 | 2026-09-01 |
| **D13** | **원천 관측값을 받고 파생은 우리 feature 함수가 한다.** 상류가 계산한 판단값을 받지 않는다 | `inbound_event_contract.md` §2-⓷ | 승계 | 2026-09-01 |
| **D14** | **과거 로그의 `topic_id`를 재작성하지 않는다.** topic 병합·분할은 매핑 테이블로 해석한다 | `inbound_event_contract.md` §6 EVT-E6 | 승계 | 2026-09-01 |

### 행동 데이터와 feedback

| # | 결정 | 근거·상세 | 출처 | 확정 |
|---|---|---|---|---|
| **D15** | **`decision_id`는 우리가 응답에 실어 보낸 값을 그대로 돌려받는 것**이다. 발신 측이 만드는 값이 아니다 | `inbound_event_contract.md` §3-4. **소급 불가** | 승계 | 2026-09-01 |
| **D16** | **`auto_insert_user`·`auto_insert_item`을 끈다.** 그리고 프로젝션을 forward-write가 아니라 **우리 store에 대한 재실행 가능한 pass**로 만든다 | `recsys_opensource/feedback_semantics.md` §7-3 | **분석** | 2026-09-03 |
| **D18** | **추천으로 만나 써 본 상대도 다시 추천될 수 있어야 한다.** `enable_replacement = true`가 강제되고, 쿨다운·시간 감쇠는 Gorse가 주지 못하므로 우리 rerank가 소유한다 | `recsys_opensource/feedback_semantics.md` §2 | 오너 | 2026-09-03 |
| **D19** | **의미가 정해지지 않은 이벤트는 Gorse에 보내지 않는다.** 버킷 미지정은 중립이 아니라 조용한 제외다. 원본은 우리 스트림에 있으므로 늦게 프로젝션하는 비용이 없다 | `recsys_opensource/feedback_semantics.md` §6-1 | **분석** | 2026-09-03 |

### 실패 규율

| # | 결정 | 근거·상세 | 출처 | 확정 |
|---|---|---|---|---|
| **D20** | **저하는 허용하되 침묵하지 않는다. 거짓말은 금지한다.** 답을 만들 수 없으면 503, 덜 좋은 답이면 200 + 저하 선언, **"없다"는 실제로 보았을 때만** 한다 | 아래 표 | **분석**(위임) | 2026-09-03 |
| **D21** | **차단·삭제·철회 재확인만은 fail-closed다.** 재확인하지 못한 후보는 답에서 **뺀다**. 전부 빠지면 200 + `verification_unavailable`이며, 이것을 `no_public_holders`로 부르지 않는다 | `inbound_event_contract.md` §4 상단 등급 | **분석**(위임) | 2026-09-03 |

의존별 동작:

| 의존 | 실패 범위 | 동작 | 선언 |
|---|---|---|---|
| LLM (S1 expansion) | 전체 | verbatim probe 하나로 진행 | `expansion` |
| topic-api `/search/topics` (S2) | **전부** | **503** — 물어볼 topic이 없으면 Gorse에 물을 것도 없다 | — |
| topic-api `/search/topics` (S2) | 일부 group | 성공한 group으로 진행 | `grounding_partial` |
| **Gorse (S3)** | 전체 | **topic-api 보유자 랭킹으로 후보 생성** — 오늘 도는 경로를 fallback으로 유지 | `candidates_fallback` |
| topic-api hydrate (S4) | 후보 일부 | **그 후보를 뺀다**(D21). 잘라낸 나머지에서 채운다 | `verification_partial` |
| topic-api hydrate (S4) | 전부 | 200 + empty, 사유 `verification_unavailable` | — |
| 우리 복제본 (D10) | 전체 | 선필터 생략. hydrate가 판정을 대신한다 | `prefilter_skipped` |

★ **`D07`이 fail-closed의 원래 논거를 이미 없앴다.** 기준 문서 §4의 근거는 *"잘린 랭킹을 완전한 랭킹과
융합하면 아무도 계산하지 않은 순서가 나온다"*였고, 그것은 **남의 랭킹을 소비할 때** 생기는 문제다 —
101등인 사람이 *낮은* 것이 아니라 *없는* 것으로 들어오기 때문이다. 라벨별 가중합에는 랭킹 융합이
없다. 라벨 하나가 빠지면 **같은 함수를 더 적은 라벨 위에서 계산한 결과**이고, 그것은 "질문을 더 적게
읽은 순서"이지 망가진 순서가 아니다.

★ **오귀속 금지는 그대로 살아남는다.** 실제로 조회하지 못한 것을 "공개 보유자가 없다"로 답하는 것은
저하가 아니라 **거짓**이다. D21의 세 번째 사유 코드가 존재하는 이유가 이것 하나다.

`판단` **topic-api는 줄일 수 없는 유일한 hard dependency로 남는다** — 어휘(카탈로그)를 그들이
소유하므로 grounding을 대신할 것이 없다. 다만 D10이 `topic.changed`로 카탈로그도 복제하므로, 우리
검색 인덱스가 생기면(`SURV-R6`) 이 마지막 의존도 저하 가능해진다. 지금은 아니다.

`열린 항목` **D21은 두 가지 선행 작업을 강제한다.** ⑴ 순위를 자른 뒤 나머지를 들고 있어야
백필이 된다(현재 `ordering.py`가 `ranked[:max_results]`로 버린다). ⑵ `empty_reason`에 값이 하나
늘어나는 것은 **bourbon-agent와의 협의 대상**이다 — 그쪽이 `Literal`로 미러링하며 strict 파싱하므로
값 추가가 파괴적 변경이다. `D15`의 `decision_id`와 같은 급이다.

---

## 2. 뒤집힌 결정

`무엇이 → 무엇으로 → 왜`. **옛 결론은 설계 문서 본문에서 삭제한다.**

**2026-09-03: 아래 여덟 건의 본문 정리를 모두 마쳤다.** 마지막 열은 그때 무엇을 고쳤는지의 기록이고,
현재 그 위치에 옛 서술은 없다. 각 문서의 변경 이력이 상세를 갖는다.

참조에 **줄번호를 쓰지 않는다** — 아래 다섯 칸이 적은 그날 이미 어긋나 있었다(2026-09-03 확인).
절 번호는 rev가 올라가도 참이다(`README.md`의 참조 규약과 같은 이유).

| 무엇이 | 무엇으로 | 왜·언제 | 정리한 곳 (2026-09-03 완료) |
|---|---|---|---|
| Gorse 기각 — *"현재 query형 파이프라인의 기본 선택은 아니다"* | **D06 채택** | 표준 endpoint로 topic별 후보 검색이 된다는 것이 실측으로 확인됨(`gorse.md` §11-1 M1). 2026-09-03 | `recommendation_scoring_design.md` §9-2 · §10-8 |
| Gorse 결과 **∩** topic grounding 후보 (재정렬기) | **D07 후보 소스** | 같은 M1. 교집합은 topic-api의 100명 컷을 그대로 물려받아 Gorse를 쓰는 이유가 사라진다. 2026-09-03 | `gorse.md` §6-1 · §7-4 · §9-B · §10 |
| *"우리 topic 저장소·인덱스·스트림 없음"* | **D10 복제본 유지** | 델타는 한 건만 유실돼도 영구히 어긋나고, 카운트·최근성은 우리 feature다. 2026-09-01 | `recommendation_pipeline_design.md` §0·§1 · `recommendation_scoring_design.md` §10-3 · 코드 레포 `docs/recsys-intent.md` |
| 이미 읽은 item 제외 = **read feedback 기준** | **모든 feedback 타입, 시간 하한 없이 영구** | v0.5.11 소스 확인. `enable_replacement`가 유일한 레버(D18). 2026-09-02 | `gorse.md` §6-1 표 |
| surface 2 캐시 payload **160 GB** | **560 GB** (UUID id 전제) | `storage_sizing.md` §2. 3.5× | `gorse.md` §6-2 · `recsys_opensource/README.md` §11 |
| `relation` enum **3값** (`exact`/`descendant`/`ancestor`) | **2값** | `ancestor`는 이 endpoint에서 생성될 수 없다. rev 5.9 | `recommendation_pipeline_design.md` 변경 이력 |
| surface별 **고정 가중치** | **surface를 입력으로 받는 LR → GBDT ranker** | 코드 분기가 아니라 함수 입력. scoring rev 3 | `README.md` §0 · `HOW_TO_READ.md` 읽는 순서 |
| S3 부분 실패·불완전성 플래그 → **503** | **저하 선언 후 계속** (D20) | 그 규칙은 *남의 랭킹을 소비할 때*의 것이었고, D07이 랭킹 소비를 없앴다. 2026-09-03 | `recommendation_pipeline_design.md` §4 · §S3 · `recommendation_scoring_design.md` §10-7 · `gorse.md` §8-3 |
| **`D17`** — `negative`는 명시적 거부에만 | **결정이 아니었다 → `C10` 열린 항목** | 오너가 *"앞으로 정해야할 부분"*이라고 열어 둔 것을 결정으로 올렸다(규칙 ③ 위반). 번호는 회수하지 않는다. 2026-09-03 | `decisions.md` §1 · `gorse.md` §7-5 |
| `degraded`를 wire에 실을지 | **필드 삭제 — 도달 불가** → **D20이 다시 도달 가능하게 만듦. 되살린다** | rev 5.5가 지운 이유가 "전부 503이라 발생할 수 없는 값"이었고 그 전제가 사라졌다. 2026-09-03 | `recommendation_pipeline_design.md` §9 ⑧ (열린 결정으로 남아 있음 — **D20·D21이 닫는다**) |

---

## 3. 결정이 없어서 문서가 갈라진 것

**충돌은 결정 부재의 신호다.** 아래는 "어느 쪽이 맞나"가 아니라 **"아직 정하지 않았다"**로 읽어야 한다.

### C1 — 실패 규율 → **D20·D21로 해소 (2026-09-03)**

- `recommendation_pipeline_design.md` §4: 재료 하나가 빠진 순위는 *"완전한 결과의 품질 저하가 아니라
  **다른 랭킹**"*이므로 **503**. 불완전성 플래그도 같다.
- `recommendation_scoring_design.md` §10-7: 학습 계층 전체가 죽어도 추천은 나온다. 표의
  `topic-api 다운 → "지금과 같음, 후보가 없으면 추천이 없다"` 행은 **기준 문서가 하는 일을 잘못 적었다**
  (기준 문서는 503).
- `gorse.md` §8-3: *"Gorse timeout → 현재 topic/RRF ordering으로 계속"*.

**해소**: D20이 저하 선언을, D21이 재확인 fail-closed를 정했다. Gorse 장애는 topic-api 보유자
랭킹으로 후보를 만들어 `candidates_fallback`으로 선언한다 — 오늘 도는 경로를 지우지 않고 남기는
것이며, 그 경로가 topic당 100명 컷을 물려받는 것은 저하 모드로서 받아들인다. 세 문서의 서술을
D20 표에 맞춰 다시 쓴다.

### C2 — `decision_id`가 응답 wire에 없다 `열린 항목`

D15가 "우리가 실어 보낸 값을 돌려받는다"고 정했고 `HOW_TO_READ.md`가 임계경로로 표시했는데,
`recommendation_pipeline_design.md` §S6-4의 응답 계약에 필드가 없고 §9 열린 결정에도 없다.
bourbon-agent가 이 모델을 field-for-field 미러링하며 strict 파싱하므로 **협의가 필요한 변경**이다.

### C3 — visibility tier가 2단인가 3단인가

`recommendation_pipeline_design.md`·`recommendation_scoring_design.md`는 `public`/`friends`,
`inbound_event_contract.md`·`recsys_opensource/README.md`는 `public`/`friends`/`private`.
D12가 "받지 않는다"를 정했으므로 **받는 축과 상류에 존재하는 축을 구분해 쓰면 해소**되지만, 지금은
같은 단어가 두 뜻이다.

### C4 — `recommendable` opt-in이 닫혔는가

**EVT-E4를 재개방했다**(2026-09-03) — 축이 아직 안 정해진 것이 맞다. 아래가 그 근거다.

`inbound_event_contract.md` §6 EVT-E4는 **닫힘**이었고, 같은 문서 §3-3 본문은 *"agent 단위 공개 축이
이진일지 tier일지 surface별일지 아직 모른다"*, `recommendation_scoring_design.md` SCORE-Q11은
*"출시 전에 정한다"*. 세 서술이 같은 주에 쓰였다.

### C5 — RRF 식이 두 벌 → **해소 (2026-09-03)**

`Σ 1/(k + rank)` (§S4-1 정의)와 `Σ 1/(k + rank + 1)` (§S4 산출물·§S5 정렬 키)이 공존했다. 변경
이력에 식이 바뀐 기록이 없어 §S4-1의 누락으로 판단하고 `+1`로 통일했다(기준 문서 rev 5.13).

### C6 — `surface` 값 목록

`inbound_event_contract.md`는 2값(`topic_search`/`home`), `recommendation_scoring_design.md` §4는
4행, `recommendation_pipeline_design.md`의 요청 계약에는 필드가 없다. SCORE-Q7이 *"surface 목록의 확정은
기획 영역"*으로 열어 둔 것을 이벤트 계약이 닫아 버렸다.

**`EVT-E9`로 등록했다**(2026-09-03) — 이벤트 계약이 enum을 먼저 닫으면 소비자들이 그 목록을 읽기
시작하므로, 확정은 SCORE-Q7이 한다.

### C7 — catalogue projection 지연의 성격 `보류`

D07 이후 이 지연은 "순위 품질"이 아니라 **"가시성"** 문제가 된다 — 프로젝션이 밀린 agent는 순위가
나빠지는 게 아니라 **아예 나오지 않는다**. `gorse.md` §11-4의 `cache_expire` 기본 72h가 여기 직접
걸린다. 2026-09-03 보류. **실체는 `gorse.md` §12-3**(쿼리 item의 이웃 목록이 `cache_expire`마다만 재계산) — 해소 후보는 §12-4의 9(`GOR-X5`).

### C8 — owner 쪽 행동 이벤트가 없다 `열린 항목`

퍼널 전체가 requester 키다. 추천받은 쪽의 거절·무응답을 나르는 이벤트가 없어 `C10`의 `negative`에 넣을
후보가 사실상 비어 있다. **버킷 배정은 나중에 바꿔도 소급되지만 이벤트 자체는 소급이 안 된다** —
D15와 같은 성질이다.

### C9 — `/recommend`의 지연 예산이 없다 `열린 항목`

목표 p50/p95/p99가 코드·설정·문서 어디에도 없다. `RECOMMEND_DEADLINE_SECONDS = 20.0` 하나뿐이고
스스로 "provisional"이라고 적혀 있다. D11이 최종 N명 조회를 필수로 만들었으므로 예산이 없으면 그
왕복 수를 판단할 근거가 없다.

### C10 — `negative`에 무엇을 넣는가 `열린 항목`

**2026-09-03 D17을 내렸다.** 규칙 ③ 위반이었다 — 오너가 *"싫어요에 해당하는 데이터 이벤트는
고민을 해봐야해. 아직 모든 feedback을 확정한게 아니니 앞으로 정해야할 부분"*이라고 **열어 둔 것**을
결정으로 올려 두었다. `feedback_semantics.md` `FBK-F2`도 같은 것을 열어 두고 있었으므로 두 문서가
어긋나 있었다.

**정해진 것은 기전뿐이다**(결정이 아니라 사실): `negative`는 `enable_replacement`와 무관하게
**영구 제외**다(`feedback_semantics.md` §2-5, v0.5.11 소스 확인). 그래서 이 항목은 되돌릴 수 없는
성질을 가지며, **정할 때까지 아무것도 negative로 보내지 않는다**(`D19`가 이미 그렇게 시킨다).

`판단` 지금 후보로 보이는 것들 중 `requery.other_agent`처럼 **가장 negative처럼 보이는 항목이
가장 넣으면 안 되는 항목**이다. C8(owner 쪽 행동 이벤트 없음)이 닫히기 전에는 명시적 거부 신호
자체가 사실상 없다.

### C11 — 1억 규모에서 surface 1의 후보 생성 도구 `열린 항목`

`D07`은 합성 6명 실측 위에서 Gorse tags item-to-item을 후보 소스로 정했다. 소스를 읽으니(`gorse.md`
§12-1) 두 가지가 규모에 걸린다 — **라벨별 100 컷이 깊은 사람부터 자르고**(§12-2), **매 사이클 전면 HNSW
빌드를 master 한 프로세스가 든다**(§12-3). 6명에서는 원리상 보이지 않는 종류다.

갈래는 둘이다. ⑴ **Gorse에 남고 보완** — 다중 라벨+센티넬(1) · 전용 인스턴스(7) · 쿼리 item 재생성(9) ·
뜨거운 라벨 샤딩(3). ⑵ **surface 1 후보를 우리 인덱스로**(5) — `D07` 재개방, `SURV-R6`의 빈칸을 채우는
것. surface 2는 어느 쪽이든 Gorse다.

**닫는 것**: `GOR-X3`(빌드 곡선 → 임계값 `N*`) · `GOR-X1`·`X4`(컷 안 깊은 사람 비율). 열 가지 후보와
실험 설계는 `gorse.md` §12-4·§12-5. **⑵는 오너 결정이다.** 2026-09-03.

**출시 전에는 닫을 수 없다**(2026-09-03, 오너 — `I_eligible`에 표본이 없다). 그래서 이 항목은 "어느 갈래"가
아니라 **"어느 갈래로 시작하고 무엇이 뒤집는가"**로 좁힌다:
- **시작(제안)**: ⑴ — Gorse + 전용 인스턴스(7) + 쿼리 item 재생성(9). 내부 규모에서 동작이 확인된 쪽이고,
  S3이 단계 경계라 소스 교체가 S1·S2·S4–S6에 닿지 않는다(**S3을 port로 유지하는 것이 조건**).
- **뒤집는 조건**: 출시 후 우리 복제본(`D10`)에서 센 `I_eligible`이 X3의 `N*`에 접근하면 ⑵로. 계측은
  topic-api 협의 없이 우리 것으로 된다(`gorse.md` §12-5 X2(b)).
- **지금 정할 것**: 위 시작안을 받는가, 그리고 `N*`의 여유율(예: 50% 도달 시 착수).

---

## 4. 승격된 항목

| 항목 | 이전 성격 | 지금 | 왜 |
|---|---|---|---|
| `SURV-R4` — §7-3 형태의 실제 보유 데이터 품질 | 채택 판단용 측정 | **배포 전 게이트** | D07이 후보 생성 전체를 이 방식에 맡긴다. 지금 근거는 합성 6명 fixture에서 확인한 메커니즘뿐이다 |
| `STO-S8` — 공용 Valkey `maxmemory-policy` | 얹기 전 확인 | 그대로 | TTL 없는 키가 차면 축출이 아니라 쓰기 실패이고 deferq에 재시도가 없다 |

---

## 5. 열린 항목 레지스터 지도와 ID 규약

**규약**: 열린 항목 ID에 문서 접두사를 붙인다. 지금 `R1`이 세 문서에서 서로 다른 것을 가리키고
`Q11`·`Q12`가 두 벌이었다. `Q12`는 **폐기된 archive 레지스터**를 기준 문서와 분석 문서가 인용하고 있었고, 2026-09-03 네 곳 모두 `EVT-E4`로 바꿨다.

| 접두사 | 문서 | 레지스터 |
|---|---|---|
| `PIPE-` | `recommendation_pipeline_design.md` §9 | 열린 결정 ①–⑪ · **본문 인라인 ⑫(§S3 끝)·⑬(§S6)** |
| `SCORE-` | `recommendation_scoring_design.md` §11·§12 | N1–N5 · D1–D8 · Q1–Q14 |
| `SURF-` | `serving_surface_design.md` §7 | ①–④ (전부 해소, 보류 2건은 §4-2·§4-5) |
| `EVT-` | `inbound_event_contract.md` §6 | E1–E9 (rev 2에서 E7–E9 추가) |
| `SURV-` | `recsys_opensource/README.md` §13 | R1–R11 |
| `GOR-` | `recsys_opensource/gorse.md` §12-5 · §11-3·§11-4 | **X1–X5**(실험) · 무번호 2건 |
| `STO-` | `recsys_opensource/storage_sizing.md` §9 | S1–S8 |
| `FBK-` | `recsys_opensource/feedback_semantics.md` §8 | F1–F10 |

`gorse.md` §11-1의 **M1–M5는 레지스터가 아니라 실측 발견 목록**이다. rev 1에서 "이름을 바꾼다"고
적었으나 **철회한다** — 인용이 열다섯 곳이고 개명 비용이 혼동 비용보다 크다. 대신 §11-1이 제목에서
`실측 발견`임을 밝히고, 이 지도에 `MEAS-` 접두사를 등록하지 않는 것으로 구분한다.

`recsys_adoption_discussion.md`·`service_boundary_discussion.md`·`facets_ownership_split_discussion.md`는
**논의 기록이므로 레지스터를 갖지 않는다.** 그 안의 E·R·F 항목은 걷어내고 "이 논의의 결론은 X §N으로
갔다"만 남긴다(규칙 ④).

---

## 6. 이 문서가 하지 않는 것

- **설계를 담지 않는다.** 각 결정의 근거와 전개는 근거 열이 가리키는 문서가 소유한다.
- **열린 항목을 소유하지 않는다.** §5의 지도만 갖는다. 예외는 §3 — 문서 간 충돌은 어느 한 문서의
  것이 아니므로 여기서 센다.
- **역사를 서술하지 않는다.** §2는 `무엇이 → 무엇으로 → 왜` 세 칸이고, 어떻게 그 결론에 이르렀는지는
  `recsys_adoption_discussion.md`가 갖는다.
