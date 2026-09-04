# 문서 읽는 순서

목적별로 진입점이 다르다. 아래 다섯 갈래 중 하나를 고른다.
문서 지도(무엇이 active이고 무엇이 보관인가)는 [`README.md`](README.md)가 소유한다.

| 갈래 | 언제 |
|---|---|
| [A](#a-전체-그림) | 처음 오는 사람. 이 제품이 무엇이고 지금 뭘 만드는지 |
| [B](#b-recsys-도입-논의) | 오픈소스 추천 도입 논의를 따라잡고 싶을 때 |
| [C](#c-타-팀에-보낼-때) | 협의·발신 |
| [D](#d-도구-판단의-근거) | "왜 이 도구인가"를 확인할 때 |
| [E](#e-topic-api-경계-논쟁) | 서비스 경계 |

---

## A. 전체 그림

```text
0. decisions.md                       ★ 지금 유효한 결정 전부. 다른 문서와 어긋나면 이쪽이 맞다
1. README.md                          프레이밍 4차 · 문서 지도 · §4 제품 불변식
2. recommendation_pipeline_design.md  ★ 설계 기준 문서 — 지금 실제로 도는 것
                                        §0 요약 → S1–S6 → §9 열린 결정
3. serving_surface_design.md          노출 표면 · 위협 모델
4. recommendation_scoring_design.md   ★ 가려는 곳 — 신호 4종을 하나의 랭커에 (surface = 입력)
                                        §1 한 문장 → §2 다섯 단계 → §11 지금/나중
```

**2와 4의 관계가 핵심이다.** 2는 *현재*, 4는 *미래*이고, 둘이 어긋나면 **2가 맞다.**
4의 §13("이 문서가 하지 않은 것")만 봐도 상태가 잡힌다.

시간이 없으면 **2의 §0과 4의 §1·§11** 세 절이면 된다.

---

## B. recsys 도입 논의

30분 코스. 이 순서가 가장 빠르다.

```text
1. recsys_opensource/README.md  §1–§2      ← 여기서 시작
     §1  surface가 둘이고 서로 다른 문제다
     §2  surface × 층 배치표                    ← 한 장으로 전체 그림

2. recsys_opensource/README.md  §6–§7
     §6  surface 2 = Gorse, 그리고 이전 기각 사유 재평가
     §7  surface 1 = CF 가 아니다(§7-1 실측) → 성립하는 형태(§7-3)

3. recsys_opensource/README.md  §8
     문서 근거가 실행에 뒤집히거나 넓혀진 다섯          ← 왜 증거 등급을 나눴는가

4. inbound_event_contract.md               무엇을 받아야 하나
```

더 볼 시간이 있으면:

```text
5. recsys_opensource/gorse.md §11    실측 상세 (원점수표 · 가중치 4종 · 신선도 측정)
6. recsys_adoption_discussion.md     어떻게 여기 왔나
                                     특히 §8 버린 논지
```

`판단` **6의 §8을 권한다.** 결론만 보면 "Gorse 쓰자"로 읽히는데, 그것은 **한 번 기각했다가 되살린
결론**이고 왜 그랬는지가 다음 판단에 쓰인다. 판단이 다섯 번 뒤집힌 기록이다.

### 이 갈래에서 헷갈리기 쉬운 것

- **surface 1과 surface 2를 섞어 읽지 않는다.** 같은 도구가 한 surface에서는 엔진이고 다른 surface에서는 오답이다.
  `recsys_opensource/README.md` §2 표가 그 축이다.
- **`문서` 근거와 `실측`을 구분한다.** `recsys_opensource/gorse.md`는 §1–§10이 문서 근거, §11이 실측, §12가 소스 근거 + 실험(X1–X6)이고,
  §11이 앞 절 다섯 개를 뒤집는다. §6-1·§6-2·§9에 ⚠ 포인터가 있다.
- **R1이 열려 있다.** "surface 2가 `friends` 보유까지 근거로 삼는가"가 §6 전체의 전제다.
  `public`만이면 Gorse가 성립하고 `friends`까지면 구조적으로 막힌다.

---

## C. 타 팀에 보낼 때

| 상대 | 문서 | 진입점 |
|---|---|---|
| **bourbon-agent** | `inbound_event_contract.md` | §2 원칙 넷 → §3-4 행동 이벤트 → §6 협의 상태 |
| topic-api | `inbound_event_contract.md` §3-1 + `service_boundary_discussion.md` | 카탈로그 이벤트 · 경계 배경 |
| 노출 필드 협의 | `recsys_opensource/off_policy.md` §3 | decision · 노출 · 보상 행 |

`inbound_event_contract.md`는 **논의 기록을 읽지 않아도 되게** 썼다 — 배너에 범위와 지위가 있고
§6에 `EVT-E1`–`E9` 상태가 표로 있다.

★ **E1(`decision_id` 회신)이 임계경로다.** 소급 불가 항목이므로 가장 먼저 닫는다.

---

## D. 도구 판단의 근거

```text
recsys_opensource/README.md §2 배치표에서 관심 있는 칸을 찾고
   → 그 칸의 도구 문서로
```

| 문서 | 무엇 | 상태 |
|---|---|---|
| `recsys_opensource/gorse.md` | 올인원 엔진 | §1–§10 `문서` · **§11 `실측`** · §12 `소스` + 실험 `GOR-X1`–`X6` |
| `recsys_opensource/implicit.md` | CF 라이브러리 | 문서 조사 |
| `recsys_opensource/cornac.md` | 실험 하네스 | 문서 조사 |
| `recsys_opensource/surprise.md` | explicit rating | 문서 조사. 현재 비활성 — rating 계약이 생기면 |
| `recsys_opensource/ranking.md` | LR → GBDT 재순위 | 초안 |
| `recsys_opensource/off_policy.md` | 반사실 평가 | 초안. **노출 필드 계약을 소유** |
| `recsys_opensource/concentration_metrics.md` | 집중도·공급 지표 | 초안 |
| `recsys_opensource/storage_sizing.md` | 저장소 규모·비용 (1억 전제) · managed 대 자체 운영 | 초안. **결론은 §6·§7이 아니라 `recsys_opensource/README.md` §11(규모)에 걸린다** |
| `recsys_opensource/feedback_semantics.md` | feedback 타입 → 엔진 동작 | 초안. `문서`(v0.5.11 **소스 독해**) — `gorse.md` §11 실측과 등급이 다르다 |

`recsys_opensource/README.md` §9(우리가 계속 소유할 것)와 §10(도구별 운영 책임)이 도입 판단에서
실제로 비교할 두 표다.

---

## E. topic-api 경계 논쟁

```text
service_boundary_discussion.md        해석 · 순위 정책의 소유
facets_ownership_split_discussion.md  값의 소유            ← 같은 경계의 다른 절반
```

⚠ **이 둘은 "topic-api가 후보를 공급한다"를 전제로 쓰였다.** B 갈래의 논의에서 topic-api를
라벨·계층 제공자로 축소하는 안이 나왔으므로, 그 방향이 채택되면 **두 문서의 전제가 함께 열린다.**
지금 읽는다면 그 점을 알고 읽는다.

상류 사실 자체는 `topic_api_analysis.md`가 소유한다(전수 분석·실측·열린 질문 §11).

---

## 문서 지위 읽는 법

이 repo의 문서는 지위가 다르고, **첫 배너에 적혀 있다.**

| 지위 | 뜻 |
|---|---|
| **결정 레지스터** | `decisions.md` 하나뿐. **결정에 관해서는 어떤 문서보다 우선한다** |
| **설계 기준 문서** | 지금 가동 중인 것을 서술. 설계에 관해 다른 문서와 어긋나면 이쪽이 맞다 |
| **설계 제안** | 가려는 곳. 코드가 이것을 근거로 바뀌지 않았다 |
| **논의 기록** | 결정이 아니다. `사실` 절만 판단 변경에도 살아남는다 |
| **조사 자료** | 도구의 계약·비용·반례. 채택·기각은 설계 문서가 소유 |
| **📦 보관됨** | `archive/`. 히스토리 기록이며 현재 계약이 아니다 |

표기 관례: `사실`(소스·실행으로 확인) · `판단`(의견) · `열린 항목`(협의·측정 대기) ·
`문서`/`실측`(증거 등급, `recsys_opensource/`에서 사용).

**참조 규약**: 살아 있는 문서를 가리킬 때 rev를 적지 않는다. 버전은 파일 첫 줄에 있고, 참조에 적으면
한쪽이 올라갈 때마다 나머지가 stale해지는 연쇄만 생긴다. 좁게 가리킬 때는 rev 대신 **절 번호**를 쓴다.

---

## 지금 열려 있는 것

읽고 나서 "그래서 다음은 뭔가"에 답하는 자리들.

| 어디 | 무엇 |
|---|---|
| **`decisions.md` §3** | **결정이 없어서 문서가 갈라진 자리 C1–C12.** 여기부터 본다 — 충돌은 결정 부재의 신호다 |
| **`decisions.md` §5** | 열린 항목 레지스터가 어느 문서에 있는지의 지도 + ID 접두사 규약 |
| `recommendation_scoring_design.md` §11–§12 | N1–N5(지금 만들 것) · D1–D8(나중에 정할 것) · Q1–Q14 |
| `inbound_event_contract.md` §6 | `EVT-E1`–`E9` 협의 상태. **E1이 임계경로** |
| `recsys_opensource/README.md` §13 | `SURV-R1`–`R11`. **R1은 여전히 surface 2의 전제**(friends까지 근거로 삼으면 전역 label이 성립하지 않는다). **R4는 배포 전 게이트로 승격**(`decisions.md` §4) |
| `recsys_opensource/gorse.md` §12 | **1억 규모에서 깨지는 것 둘과 개선 후보 열한 가지 + 실험 `GOR-X1`–`X6`(전부 완료).** 7·9는 `D22`, 1은 `D23`, 11은 `D24`. 남은 결정은 `N*`. **실행 순서·상태는 §12-6** |
| ~~`recsys_adoption_discussion.md` §9~~ | **레지스터가 아니다**(`decisions.md` §5). 논의 기록이고 번호가 `SURV-R`과 겹치되 뜻이 다르다 |
| 코드 repo `tasks/todo.md` | 구현 plan의 단일 소스 (이 repo에 병렬 plan을 두지 않는다) |
