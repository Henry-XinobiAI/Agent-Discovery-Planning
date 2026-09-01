# 추천 집중도·공급 측 지표 정의

> **결론**: Gini 하나로 “공정하다”를 판정하지 않는다. 노출 집중, catalogue coverage, owner workload를
> 서로 다른 분모로 측정한다. **hard capacity는 gate**, soft distribution은 rank 뒤 정책, 이 문서의 지표는
> 관측과 정책 평가다. 소유 설계는
> [`recommendation_scoring_design.md` §7-3·D7](../recommendation_scoring_design.md)이다.

## 1. 왜 requester 지표만으로 부족한가

추천 대상은 무한 재고 item이 아니라 사람이 소유한 personal agent다. 한 owner에게 품질 신호가 몰려도 그
사람이 동시에 처리할 수 있는 대화에는 한계가 있다. requester click/resolution만 최적화하면 인기 owner의
부하와 신규 owner의 발견 가능성을 악화시킬 수 있다.

다음 셋을 분리한다.

```text
hard unavailable / privacy / opt-out  → gate에서 제거
soft workload / concentration         → rank 뒤 정책이 조정할 수 있음
분포가 어떻게 변했는가               → 이 문서의 지표
```

## 2. 공통 집계 단위

집계마다 다음 축을 명시한다.

- window: 일/주, UTC 경계
- surface: topic_search/home 등을 섞지 않음
- population: **그 기간에 최소 한 번 eligible했던 owner/agent** 또는 전체 recommendable catalogue
- unit: impression, top-1, selected, conversation_started, resolved
- identity: personal agent와 owner 양쪽. 한 owner가 agent 여러 개를 가지면 workload는 owner로 합친다.

eligible하지 않았던 owner를 분모에 넣고 coverage가 낮다고 말하면 gate 정책을 ranker 결함으로 오귀속한다.
반대로 recommendable catalogue 전체 coverage는 opt-in 제품 지표로 별도 보존할 수 있다.

## 3. 핵심 지표

### 3-1 Top-share

```text
top_1pct_exposure_share
  = exposure가 많은 상위 1% owner의 exposure 합 / 전체 exposure
```

가장 설명하기 쉽고 알람에 적합하다. owner 수가 적은 surface에서는 top-1/top-10 share도 함께 낸다.

### 3-2 HHI와 effective number

owner `i`의 노출 점유율을 `pᵢ`라 하면:

```text
HHI = Σ pᵢ²
effective_owners = 1 / HHI
```

모두 균등하면 effective owners가 실제 owner 수에 가깝고 한 명에게 몰리면 1에 가까워진다. 서로 다른
catalogue 크기의 surface를 비교할 때 raw HHI와 `effective_owners / eligible_owners`를 함께 본다.

### 3-3 Gini

노출 수 배열의 불균등을 0(균등)~1(집중)로 표현한다. 0 노출 owner를 포함할지에 따라 값이 크게 달라지므로
population 정의를 metric name/metadata에 넣는다.

### 3-4 Coverage

```text
eligible_coverage = 기간 중 1회 이상 노출된 owner / 기간 중 1회 이상 eligible했던 owner
catalogue_coverage = 기간 중 1회 이상 노출된 owner / recommendable opt-in owner
```

첫 값은 rank/policy를, 둘째는 retrieval·catalogue·opt-in까지 포함한 제품 표면을 본다.

### 3-5 Workload saturation

```text
owner_active_conversations / owner_declared_or_inferred_capacity
capacity_rejection_rate
over_capacity_attempt_count
```

capacity 정보가 없다면 active conversation count와 p95만 관측하고 임계값을 발명하지 않는다. soft 상한과
hard 상한을 같은 이름으로 부르지 않는다.

## 4. 작은 예시

한 시간 동안 eligible owner가 A/B/C/D이고 노출이 `[70, 20, 10, 0]`이면:

```text
top-1 share       = 0.70
HHI               = 0.70² + 0.20² + 0.10² = 0.54
effective owners  = 1 / 0.54 ≈ 1.85
eligible coverage = 3 / 4 = 0.75
```

이 값만으로 A를 강제로 내리지는 않는다. A가 유일하게 요청 topic을 충족했을 수도 있다. topic/surface별
cohort와 requester outcome을 함께 보고 정책을 정한다.

## 5. 필요한 이벤트

```json
{
  "decision_id": "dec-123",
  "surface": "topic_search",
  "personal_agent_id": "agent-b",
  "owner_user_id": "owner-b",
  "eligible": true,
  "shown": true,
  "position": 1,
  "capacity_state": "available",
  "ranker_version": "lr-7",
  "policy_version": "explore-3",
  "occurred_at": "2026-08-31T12:00:00Z"
}
```

후보 전체 event가 너무 크면 decision row에 eligible IDs를 압축 저장하고 노출 행은 별도로 둘 수 있다.
어느 형태든 “노출 0”과 “eligible 아니었음”을 복원할 수 있어야 한다.

## 6. 정책과의 경계

| 필요 | 위치 | 이유 |
|---|---|---|
| privacy·safety·self·opt-out | hard gate | 점수와 교환 불가 |
| 동시 대화 hard capacity | hard gate | 실제 서비스 불가능 |
| 인기 쏠림 완화 | rank 뒤 정책 또는 constrained reranking | 품질과 trade-off를 명시적으로 평가 |
| 탐색 슬롯 | logging policy | propensity가 있어야 효과 평가 가능 |
| 집중도 계산 | offline/stream aggregate | serving 판정과 분리 |

ranker feature로 `current_load`를 넣는 것만으로 hard capacity를 보장하지 못한다. 충분히 큰 다른 feature가
금지선을 넘길 수 있기 때문이다.

## 7. 최소 대시보드

surface·일 단위로 다음을 한 화면에 둔다.

1. top-1/top-10/top-1% exposure share
2. HHI, effective owner ratio, Gini
3. eligible/catalogue coverage
4. owner active conversation p50/p95/max와 capacity rejection rate
5. requester resolution/re-query 지표
6. ranker·policy version과 exploration rate

집중도만 낮추고 requester outcome이 무너지거나, requester outcome만 올리고 workload가 포화되면 둘 다
채택 실패다.

## 8. 구현과 검증

수십 줄의 순수 집계 함수로 시작할 수 있고 별도 추천 패키지가 필요 없다.

- `[1,1,1,1]`, `[4,0,0,0]`, 빈 집합 fixture로 극단값을 고정한다.
- agent→owner 합산 전후 값을 둘 다 테스트한다.
- eligible population에 privacy 탈락자가 들어가지 않는지 고정한다.
- 같은 event 재처리 시 중복 집계되지 않도록 decision/impression ID로 dedupe한다.
- window가 덜 닫힌 현재 시간대는 finalized window와 구분한다.

임계값은 첫 분포를 보기 전에 발명하지 않는다. 단, hard capacity와 recommendable opt-out은 통계 임계값이
아니라 제품 계약이므로 출시 전에 별도로 결정한다.
