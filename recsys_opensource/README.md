# 오픈소스 추천 시스템 활용 검토

> **문서 지위**: 기술 검토 자료이며 설계 정본이나 도입 결정이 아니다. 현재 제품 설계는
> [`recommendation_scoring_design.md`](../recommendation_scoring_design.md), 현재 가동 계약은
> [`recommendation_pipeline_design.md`](../recommendation_pipeline_design.md)가 소유한다.
>
> 조사 기준일: 2026-08-28. 기능 주장은 각 프로젝트의 공식 문서와 공식 저장소를 우선해 확인했다.

## 1. 공통 도메인 모델

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

## 2. 공통 입력과 출력

### 2-1 입력

| 부류 | 우리 데이터 | 예시 |
|---|---|---|
| User feature | requester가 원하는 것 | 관심 topic, 선호 언어, 선호 대화 방식, sharable persona |
| Item feature | candidate agent가 제공하는 것 | 공개 전문 topic, 제공 언어, 응답 스타일, 활동성 |
| Interaction | requester와 agent 사이에서 일어난 것 | exposure, select, conversation start/depth, resolved, re-query |

상호작용의 원본 행은 학습값보다 넓어야 한다.

```json
{
  "requester_user_id": "user-a",
  "personal_agent_id": "agent-b",
  "event_type": "conversation_started",
  "value": 1.0,
  "occurred_at": "2026-08-28T12:00:00Z",
  "surface": "topic_search",
  "request_id": "...",
  "position": 2,
  "propensity": 0.18,
  "model_version": "..."
}
```

앞 다섯 값은 여러 도구가 학습에 읽을 수 있는 재료이고, 뒤 값들은 우리의 노출·off-policy 평가 계약이다.
라이브러리가 읽지 않더라도 원본 이벤트에서 버리면 안 된다.

### 2-2 출력

오픈소스 모델의 출력은 보통 풍부한 카드가 아니라 ID와 점수다.

```json
[
  {"personal_agent_id": "agent-b", "model_score": 0.81},
  {"personal_agent_id": "agent-c", "model_score": 0.67}
]
```

`owner_user_id`, matched topic, relation, catalogue description, owner note, match reason은 모델 출력이 아니다.
현재 discovery pipeline이 권한을 확인하고 근거를 조립해 최종 wire로 만든다. 모델 점수는 그 pipeline의
한 신호일 뿐 자격 판정을 대신하지 않는다.

## 3. topic·bio·traits와 visibility

### 3-1 역할별 feature

```text
requester-side                         candidate-side
seeks_topics                           provides_topics
preferred_languages                    provided_languages
preferred_styles                       provided_styles
interaction_history                    public bio/traits
```

`coffee`를 좋아하는 사람과 `coffee`를 잘 설명할 수 있는 사람은 같은 feature가 아니다. `seeks_topics`와
`provides_topics`를 분리하지 않으면 유사성을 궁합으로 오해한다. 원문 bio를 넣는다고 모델이 자동으로
의미를 이해하는 것도 아니다. 도구에 맞게 tag, 수치 feature 또는 별도 embedding으로 투영한다.

### 3-2 visibility는 feature weight가 아니라 gate다

| tier | 모델 입력 원칙 | 서빙 원칙 |
|---|---|---|
| `public` | candidate feature에 포함 가능 | 모든 requester에게 사용 가능 |
| `friends` | 전역 candidate feature·전역 캐시에 넣지 않음 | 관계 확인 후 후보 생성·rerank에서만 사용 |
| `private` | 타인 대상 candidate 학습에서 제외 | 소유자 자신의 query-side 개인화도 별도 정책 승인 시에만 사용 |

최종 응답에서 숨기기만 하면 충분하지 않다. 민감한 feature가 후보 생성이나 점수에 들어가면 순위 자체가
그 사실을 간접 노출할 수 있다.

```text
candidate sources
      ↓
requester-aware privacy/safety/self gate
      ↓
허용된 후보와 feature만 score
      ↓
exploration
      ↓
exposure log + response assembly
```

## 4. 하나의 요청을 네 도구가 읽는 방식

같은 사례를 먼저 고정하면 도구 차이가 선명해진다.

```text
requester Alice
  interests: coffee(public), hiking(friends), health(private)
  traits: 한국어 선호, 간결한 설명 선호

candidate Bob의 agent
  coffee(public), espresso(public), hiking(friends)
  영어·한국어 제공, 자세한 설명 성향

candidate Carol의 agent
  coffee(public), roasting(public)
  한국어 제공, 간결한 설명 성향

이번 요청
  topic="coffee", context="집에서 에스프레소를 시작하고 싶다"
```

Alice가 Bob의 친구라면 discovery가 허용할 candidate material은 Bob의 public+friends다. Carol에게는
public만 읽는다. Alice의 `health(private)`는 Alice 자신의 개인화에 사용하도록 별도 승인을 받았더라도
Bob·Carol에게 전달되거나 그들이 candidate가 되는 이유로 설명되어서는 안 된다.

### Gorse가 읽는 것

```text
User Alice labels             Item Bob labels          Feedback
coffee, ko, concise           public coffee/espresso   Alice→Bob conversation_started
과거 agent 행동               ko/en, detailed          Alice→Carol selected
```

Gorse의 표준 사용자 추천은 이번 자연어 `context`를 받지 않는다. 평소 선호 후보를 만들고, discovery가
이번 요청 후보와 교집합/합집합을 만든다. friends hiking은 전역 Item label에 넣지 않는다.

### Cornac이 읽는 것

```text
UIR/UIRT 행                   user modality            item modality
Alice, BobAgent, 1.0, time   coffee/ko/concise        coffee/espresso/ko/en/detailed
Alice, CarolAgent, 0.4,time  ...                       coffee/roasting/ko/concise
```

여러 모델에서 interaction-only와 feature-aware 결과를 오프라인 비교한다. online API는 우리가 만든다.

### Surprise가 읽는 것

```text
Alice, BobAgent, explicit_rating=5
Alice, CarolAgent, explicit_rating=3
```

topic, context, bio, traits는 읽지 않는다. 실제 rating이 없다면 이 표 자체를 만들 수 없다.

### implicit이 읽는 것

```text
CSR[Alice, BobAgent]   = positive confidence 3.2
CSR[Alice, CarolAgent] = positive confidence 1.1
```

topic/bio는 행렬에 합성하지 않는다. discovery가 이번 요청에서 Bob·Carol을 허용한 뒤 두 ID에 대해서만
행동 기반 latent score를 계산한다.

## 5. 제품·프레임워크·라이브러리의 구성 차이

네 후보는 배포 단위가 같지 않다.

| 분류 | 도구 | 우리가 받는 것 | 우리가 추가로 만들어야 하는 것 |
|---|---|---|---|
| 운영 제품/서비스 | Gorse | DB schema, ingestion/recommend API, 학습 worker, cache, dashboard | sync adapter, auth/network, product gate, hydration, exposure log |
| 실험 프레임워크 | Cornac | dataset/split/model/metric orchestration, model zoo | snapshot job, request replay evaluator, artifact contract, online scorer |
| 알고리즘 라이브러리 | Surprise, implicit | in-process fit/predict/save/load API | event aggregation, ID map, training CLI, artifact registry, loader, fallback, serving integration |

### 서비스형: 네트워크 경계가 생긴다

```text
bourbon services ──HTTP──> Gorse server
       │                       │
       ├── catalogue sync ─────┤
       ├── feedback sync ──────┤
       └── recommend request ──┘
```

배포·DB migration·credential·timeout·retry·readiness·cache freshness가 설계 대상이다. 대신 학습 scheduler와
추천 API를 직접 만들지 않는다.

### 프레임워크형: production 경로 밖에 둔다

```text
event snapshot → evaluate/train CronJob(Cornac) → artifact/report
                                                   ↓
                                     우리 serving adapter가 선택적으로 소비
```

Cornac의 `Experiment` 결과가 곧 serving component는 아니다. 어떤 모델을 채택할지 답하고 artifact를 만드는
offline 도구다.

### 라이브러리형: 호출은 쉽지만 제품 경계는 우리가 만든다

```text
same repository
  cli/train.py       library.fit() → artifact
  scoring/model.py   artifact load → library.predict/recommend()
  stages/order.py    gate-approved candidates + score
```

별도 네트워크 서비스는 필요 없지만 모델 파일·ID map·동시 로딩·버전·rollback·cold start·메모리 제한을
직접 소유한다. “pip install이 된다”는 “운영 추천 시스템이 생긴다”는 뜻이 아니다.

## 6. 네 도구의 역할 비교

| 도구 | 형태 | 잘 맞는 자리 | bio/traits | 운영 서빙 | 1차 판단 |
|---|---|---|---|---|---|
| [Gorse](gorse.md) | Go 올인원 서비스 | 빠른 end-to-end baseline, public 후보 | JSON labels, tags/embedding | 자체 API·worker·cache | **조건부 후보** |
| [Cornac](cornac.md) | Python 실험 프레임워크 | 모델·modality 비교, 오프라인 평가 | feature/text/graph modality | 별도 adapter 필요 | **실험 하네스 후보** |
| [Surprise](surprise.md) | Python explicit-rating 라이브러리 | rating baseline·교육 | 지원하지 않음 | 직접 구축 | **제한적 기준선** |
| [implicit](implicit.md) | Python/Cython implicit-CF | 행동 행렬 기반 ALS/BPR baseline | 직접 지원하지 않음 | artifact adapter 필요 | **행동 모델 후보** |

네 번째로 `implicit`을 택한 이유는 역할 중복을 줄이기 위해서다. RecBole은 많은 모델을 제공하지만
Cornac과 모델 비교 프레임워크 역할이 겹친다. `implicit`은 대화 시작·재방문처럼 실제로 얻게 될
positive-only 행동을 작은 의존성과 명확한 sparse matrix 계약으로 다룬다.

## 7. 잠정 역할 분리와 그 이유

현재의 잠정안은 네 도구 중 하나를 “최종 승자”로 고르는 것이 아니다. 서로 다른 문제를 푸는 도구를 같은
자리에 놓지 않고, 각 도구가 가장 적은 왜곡으로 답할 수 있는 질문에 배치하는 것이다.

```text
행동 기반 첫 production challenger       implicit
모델·feature 후보의 offline 비교         Cornac
운영 플랫폼을 살 것인지에 대한 검증       Gorse
명시적 rating 모델의 sanity baseline     Surprise
```

이 역할은 제품 데이터와 운영 단계가 바뀌면 다시 검토한다. 특히 `implicit`은 지금 즉시 배선할 예약 모듈이
아니라, 정직한 행동 행렬을 만들 수 있게 되었을 때의 첫 후보라는 뜻이다.

### 7-1 implicit: 첫 행동 기반 모델 후보

`implicit`이 첫 후보인 이유는 현재 예상되는 feedback이 별점보다 positive-only 행동에 가깝기 때문이다.

```text
카드가 노출됨
  → 선택함
  → 대화를 시작함
  → 다시 방문함
  → 해결 또는 재질의가 관측됨
```

이 사건들은 “Alice가 Bob의 agent에 4점을 주었다”는 explicit rating이 아니다. 반면 requester–agent sparse
matrix로 투영하면 ALS·BPR 같은 collaborative baseline을 비교할 수 있다. `implicit`은 이 질문에 필요한
계약이 작고 명확하다.

```text
input  = requester × personal-agent sparse matrix
output = gate가 허용한 agent ID별 상대 점수
```

또한 `items=` 후보 제한을 통해 현재 discovery가 만든 candidate set 안에서만 점수를 계산할 수 있다. 기존
topic grounding과 visibility gate를 교체하지 않고 행동 신호 한 축만 추가하기 좋다.

하지만 다음 조건이 먼저 충족되어야 한다.

1. exposure와 positive 행동을 구분해 저장한다.
2. 이벤트의 중복과 funnel 이중 가산을 처리한다.
3. request 당시 실제로 노출 가능했던 후보 집합을 평가에 복원할 수 있다.
4. requester와 personal agent의 versioned ID map을 안정적으로 만든다.
5. cold requester·신규 agent가 충분히 많을 때 규칙 기반 fallback을 유지한다.

이 조건이 없으면 sparse matrix는 “좋아한 것”이 아니라 “우연히 관측된 것”을 학습한다. 따라서 첫 행동
모델이라는 표현은 도입 순서를 뜻하지, 지금부터 model artifact와 adapter를 미리 만들라는 뜻이 아니다.

### 7-2 Cornac: 실서비스 밖 모델 비교 도구

Cornac의 강점은 하나의 production endpoint를 빠르게 제공하는 것이 아니라, interaction-only 모델과
topic·bio·graph 같은 modality를 읽는 모델을 같은 평가 틀에서 비교하는 것이다.

```text
B0 현재 topic/RRF 규칙
B1 interaction-only BPR 또는 WMF
B2 B1 + public topic feature
B3 B2 + sharable bio/trait feature
```

이 순서로 비교하면 auxiliary feature가 실제로 추가 이득을 주었는지 알 수 있다. 처음부터 모든 feature를
넣으면 품질이 올라도 어느 입력이 기여했는지, privacy 비용을 정당화하는지 알 수 없다.

Cornac을 online request path가 아니라 offline evaluation/training 영역에 두는 이유는 다음과 같다.

- REST serving, ingestion, authorization, cache와 rollback을 제공하는 운영 제품이 아니다.
- Cornac의 catalogue-wide split과 metric만으로는 요청마다 candidate set이 바뀌는 현재 문제를 완전히
  평가할 수 없다.
- 일부 모델은 학습 의존성이 크며, serving image에 전체 실험 stack을 넣는 비용이 있다.
- 선택한 모델이 단순 factor matrix나 작은 scorer로 export 가능하면 production은 그 최소 artifact만 읽는
  편이 장애면과 공급망을 줄인다.

따라서 Cornac은 먼저 “어떤 모델과 modality가 가치가 있는가”에 답한다. 선택된 모델을 어떤 runtime으로
서빙할지는 그 다음의 별도 결정이다. Cornac에서 이긴 모델이 반드시 Cornac runtime으로 production에
들어가야 하는 것은 아니다.

### 7-3 Gorse: 모델보다 운영 플랫폼의 가치를 검증

Gorse는 네 후보 중 유일하게 data API, worker, recommendation API, cache, dashboard를 포함하는 운영
제품에 가깝다. 그래서 비교 질문도 “ALS와 BPR 중 무엇이 더 좋은가”보다 넓다.

```text
우리가 직접 만드는 비용
  feedback ingestion + 학습 scheduling + serving API
  + cache + model refresh + dashboard/A/B 연결

Gorse를 운영하는 비용
  catalogue/feedback sync + DB/cache 운영 + network/auth
  + 우리 visibility gate와 Gorse cache의 정합성
```

Gorse를 지금 기본안으로 두지 않는 이유는 현재 어려운 문제가 추천 서버의 부재보다 제품별 candidate
계약에 있기 때문이다.

- 표준 recommendation API는 이번 요청의 자연어 `topic`과 `context`를 그대로 받아 grounding하지 않는다.
- `friends` interest는 requester마다 허용 여부가 달라 전역 item label과 전역 cache에 안전하게 넣기 어렵다.
- topic grounding, self-exclusion, owner-note 접근 제어와 최종 설명 조립은 여전히 discovery가 해야 한다.
- Gorse를 붙여도 catalogue sync와 feedback projection이라는 새로운 일관성 경계가 생긴다.

따라서 다음과 같은 징후가 나타날 때 별도 PoC의 가치가 커진다.

1. 모델 학습보다 scheduler, cache, dashboard와 model lifecycle 운영 비용이 더 커진다.
2. 여러 surface가 같은 feedback store와 general recommendation API를 요구한다.
3. 작은 in-process model의 artifact 배포와 rollback이 반복적으로 병목이 된다.
4. Gorse가 제공하는 운영 기능을 쓰고도 requester-aware gate를 앞뒤에서 정확히 유지할 수 있다.

이때 평가할 것은 단순 offline NDCG만이 아니다. 우리 자체 구성과 비교한 운영 인력, 장애면, freshness,
privacy invalidation 지연, A/B 실행 비용까지 포함한다.

### 7-4 Surprise: explicit rating 기준선

Surprise는 사용 범위를 스스로 explicit rating으로 제한한다. 따라서 다음과 같은 실제 제품 사건이 생겼을
때 의미가 있다.

```text
“이 agent의 답변이 얼마나 도움이 되었나요?” 1..5
“이 agent를 다시 추천받고 싶나요?” 1..5
```

이런 값이 있다면 GlobalMean·BaselineOnly·KNN·SVD를 짧은 코드로 비교해 복잡한 행동 모델이 기본 rating
예측보다 정말 나은지 확인할 수 있다. 구현이 단순하고 알고리즘이 잘 알려져 있어 sanity baseline으로
좋다.

반대로 선택, 대화 시작, 재방문을 임의의 별점으로 바꾸면 Surprise를 사용할 수는 있지만 질문을 왜곡한다.
노출되지 않은 agent를 낮은 별점으로 취급할 수도 없고, topic·bio·visibility feature도 직접 읽지 않는다.
그러므로 실제 explicit rating 계약이 생기기 전에는 production 후보가 아니라 비교용 도구로 한정한다.

자발적으로 rating을 남긴 사용자만의 표본 선택 편향도 별도로 다룬다. rating RMSE가 좋아졌다는 사실만으로
전체 추천 요청의 ranking이 좋아졌다고 결론내리지 않는다.

### 7-5 도구와 무관하게 우리 제품이 계속 소유할 것

다음 책임은 라이브러리의 기능 부족 때문에 임시로 남는 것이 아니다. 제품 의미와 권한을 정하는 계약이므로
어떤 도구를 선택해도 우리 시스템이 소유한다.

| 책임 | 왜 모델이나 외부 추천 서비스에 넘길 수 없는가 |
|---|---|
| requester-aware visibility | `friends`는 requester–owner 관계에 따라 달라지고 `private`은 타인 추천 근거가 되어서는 안 됨 |
| topic grounding | 자연어 요청을 catalogue topic과 `grounded/failed/ambiguous`로 확정하는 제품 의미가 있음 |
| self-exclusion | 같은 사람이 requester와 candidate 양쪽 역할에 존재하므로 ID·owner 관계를 알아야 함 |
| safety·eligibility | 차단, 삭제, 정책 변경은 학습 점수보다 먼저 적용되어야 함 |
| final response assembly | matched topic, relation, description, owner note와 설명은 모델의 ID·score 출력에 없음 |
| exposure semantics | 무엇을 실제 노출로 셀지, 후보 집합·position·propensity·model version을 어떻게 남길지는 제품 실험 계약임 |

Gorse는 feedback을 저장할 수 있고 다른 도구도 event를 입력으로 받을 수 있다. 하지만 “저장할 수 있다”와
“노출의 의미를 소유한다”는 다르다. 예를 들어 다음 행에서 라이브러리가 학습에 읽는 것은 앞부분 일부일
수 있지만, 뒤의 값이 없으면 우리는 추천 결과를 공정하게 평가하거나 재현할 수 없다.

```json
{
  "requester_user_id": "alice",
  "personal_agent_id": "agent-bob",
  "event_type": "exposed",
  "request_id": "…",
  "candidate_set_version": "…",
  "position": 2,
  "propensity": 0.18,
  "model_version": "implicit-2026-08-28.1",
  "feature_version": "features-v4"
}
```

visibility도 최종 응답에서 비밀 필드를 지우는 문제만이 아니다. 금지된 feature가 candidate generation이나
score에 들어갔다면 순위 자체가 그 정보를 간접 노출할 수 있다. gate는 모델 뒤의 redaction이 아니라 모델
입력과 후보 집합을 정하는 앞단 계약이어야 한다.

### 7-6 도구에 따라 달라지는 운영 책임

반면 다음 책임은 어느 도구를 택하느냐에 따라 직접 구축하거나 제품 기능을 이용할 수 있다.

| 운영 책임 | Gorse | Cornac | implicit | Surprise |
|---|---|---|---|---|
| feedback ingestion/store | 제공 기능 활용 가능 | 직접 구축 | 직접 구축 | 직접 구축 |
| 학습 scheduler/worker | 제공 | 직접 구축 | 직접 구축 | 직접 구축 |
| model artifact와 refresh | 플랫폼 흐름 활용 | 직접 계약 | 직접 계약 | 직접 계약 |
| online recommendation API | 제공 | 직접 구축 | 직접 구축 | 직접 구축 |
| raw↔integer ID map | 내부 소유 | artifact와 함께 관리 | 반드시 직접 관리 | trainset/artifact와 관리 |
| cache와 dashboard | 제공 기능 있음 | 직접 구축/외부 도구 | 직접 구축/외부 도구 | 직접 구축/외부 도구 |

도입 판단에서 실제로 비교할 부분은 이 표다. 앞 절의 제품 책임은 없앨 수 없지만, 이 운영 책임은 플랫폼을
채택해 줄일 수도 있고 작은 library adapter로 직접 소유할 수도 있다.

다만 “제공”은 “무료”가 아니다. Gorse를 선택하면 자체 구현 코드는 줄어도 별도 DB·cache·worker의 배포,
network auth, schema sync, retry, readiness와 version 호환 책임이 생긴다. 반대로 library는 설치는 쉽지만
artifact registry, atomic refresh, fallback과 monitoring을 우리가 만들어야 한다.

### 7-7 단계별 판단 순서

현재 데이터 성숙도에서는 다음 순서가 합리적이다.

```text
1. 제품 계약
   exposure/feedback 의미, candidate set, visibility, deletion을 먼저 고정

2. 규칙 기준선
   현재 topic/RRF ordering과 평가 harness를 재현 가능하게 만듦

3. 첫 행동 challenger
   implicit ALS/item-item을 동일 request candidate set에서 비교

4. 모델·feature 탐색
   Cornac으로 interaction-only와 public modality의 추가 이득을 분리

5. 운영 플랫폼 판단
   학습·배포·cache 운영이 병목일 때 Gorse PoC

6. explicit rating이 생긴 경우
   Surprise 기준선으로 행동 모델의 복잡성이 실제 가치가 있는지 확인
```

이 순서를 지키면 도구가 데이터 의미를 정하는 일을 피할 수 있다. 반대로 도구를 먼저 고르면 Gorse의 label,
Surprise의 rating, implicit의 confidence에 맞춰 제품 사건을 억지로 변형하게 된다.

### 7-8 요청별 후보 제한 비교

추천에 넣지 말아야 할 대상을 다루는 방법은 세 종류다.

```text
전역 제외       누구에게도 추천하지 않음             deleted/disabled/legal hold
requester 제외  이 requester에게만 추천하지 않음      self/block/friends visibility
후보 allowlist   이번 요청에서 허용된 pool만 점수화    grounded topic candidates
```

네 도구의 기본 지원은 다음과 같다.

| 도구 | 전역 제외 | 이미 본 항목 제외 | arbitrary denylist | arbitrary candidate allowlist |
|---|---|---|---|---|
| Gorse | `IsHidden` | read feedback | 표준 recommend API에는 없음 | category까지만, 임의 ID pool은 없음 |
| Cornac | 외부 snapshot/gate | `recommend(remove_seen=True)` | pool에서 외부 제거 | `rank(item_indices=...)` |
| Surprise | 외부 snapshot/gate | online에서는 외부 결정 | 예측 전 외부 제거 | 허용된 pair만 `predict()` |
| implicit | 학습/serving 외부 gate | `filter_already_liked_items` | `filter_items` | `items` |

지원 여부와 권한 책임은 다르다. Cornac과 implicit이 후보 배열을 받더라도 그 ID가 왜 허용되는지는 모른다.
Surprise도 허용된 pair만 예측할 수 있지만 pool은 호출자가 만든다. Gorse의 category는 coarse taxonomy이지
requester별 friends/block 집합이 아니다.

우리 online 경로의 기본 원칙은 denylist보다 allowlist다.

```text
권장
  모든 제품 gate를 통과한 candidate IDs
    → 모델에 이 pool만 전달

비권장
  모델의 전체 catalogue
    - 기억하고 있는 금지 목록
```

denylist는 새 제외 규칙을 누락하면 금지 candidate가 살아난다. allowlist는 현재 요청에서 명시적으로
허용하지 않은 candidate가 기본적으로 모델에 들어가지 않는다. 따라서 exact pool 제한을 지원하는
`implicit.items`와 Cornac `item_indices`는 이 시스템과 잘 맞는다.

Gorse를 사용할 때는 coarse recommendation을 충분히 overfetch한 뒤 우리 gate와 교집합할 수 있지만, 상위
결과가 모두 탈락하면 허용 가능한 뒤쪽 item을 복구하지 못한다. 이는 보안 우회는 아니어도 결과 수와 recall을
낮춘다. exact candidate reranking이 핵심이면 Gorse 표준 endpoint의 구조적 제약으로 PoC에 기록한다.

빈 allowlist에서 전체 catalogue 추천으로 fallback하는 것은 네 도구 모두 금지한다. 빈 값은 “추천할 것이
없다”가 아니라 “이번 요청에서 허용된 것이 없다”는 권한 결과일 수 있기 때문이다.

### 7-9 전체 사용자 pool이 1억일 때의 확장성

“사용자가 1억 명이다”만으로 학습 크기를 정할 수 없다. 최소 네 cardinality를 따로 측정한다.

```text
U_registered   전체 가입자                         최대 100,000,000
U_active       학습 기간에 유효 행동이 있는 requester
I_eligible     현재 추천 가능한 personal agent
I_request      한 요청에서 grounding·gate를 통과한 후보
```

모든 가입자가 personal agent를 하나씩 가진 최악의 경우 `U_registered=I_eligible=1억`이다. 그러나 online
요청이 1억 후보를 모두 점수화해서는 안 된다. topic grounding과 gate가 `I_request`를 수십~수천으로 먼저
줄이는 two-stage 구조가 확장성의 핵심이다.

```text
1억 candidate catalogue
  → topic/index retrieval
  → visibility/safety/self gate
  → request candidate 100~1,000
  → personalization rerank
  → top 10~20
```

#### 단순 메모리 하한

matrix factorization을 `float32`, latent factor 64개로 가정하면 factor 배열만 다음 크기다.

```text
user factors = 100,000,000 × 64 × 4 bytes = 25.6 GB
item factors = 100,000,000 × 64 × 4 bytes = 25.6 GB
합계         = 51.2 GB (decimal, runtime overhead 전)
```

factor 128개면 합계는 102.4 GB다. 여기에 sparse interaction matrix, ID map, bias, optimizer/work buffer,
train/test copy와 Python/native object overhead가 붙는다.

active requester 한 명당 nonzero interaction이 평균 20개면 `nnz=20억`이다. CSR을 value `float32` + column
index `int32`로만 잡아도 nonzero 영역이 약 16 GB이고 row pointer가 추가된다. 실제 event 원본, 정렬·집계
중간 파일과 학습 복제본은 이보다 크다. 이는 정확한 capacity estimate가 아니라 **최소 배열 하한**이다.

따라서 등록 사용자 1억을 전부 dense factor row로 만드는 것은 기본안이 아니다.

- 최근 학습 window에 실제 행동이 있는 `U_active`만 collaborative model에 넣는다.
- 추천 자격과 최소 활동 기준을 만족하는 `I_eligible`만 item map에 넣는다.
- cold requester/agent는 topic·content 규칙과 exploration으로 처리한다.
- 삭제·visibility는 active snapshot과 online gate에서 별도로 강제한다.
- 전체 catalogue retrieval과 작은 pool reranking을 분리한다.

예를 들어 `U_active=1천만`, `I_eligible=5백만`, factor 64면 factor 하한은 약 3.84 GB로 줄어든다. 이 수치도
운영 가능성을 보장하지는 않지만, “가입자 1억”과 “모델 row 1억”이 같은 결정이 아님을 보여준다.

#### 요청당 1억 점수화는 별도 문제다

factor가 메모리에 들어가도 요청마다 1억 item과 dot product를 계산하면 안 된다. factor 64 기준 한 요청이
약 64억 개의 곱셈 누산 후보를 만든다. ANN은 전역 nearest-neighbor retrieval을 줄일 수 있지만
requester별 `friends/private/block` 권한을 자동으로 해결하지 않는다.

현재 구조에서는 topic-api/discovery가 의미와 권한으로 후보를 줄인 뒤 recsys가 작은 allowlist만 rerank한다.
이 순서라면 모델 선택보다 retrieval index, gate latency와 candidate fan-out이 먼저 capacity test 대상이다.

#### 네 도구의 1억 규모 역할

| 도구 | 1억 등록 사용자에서 현실적인 역할 | 주된 병목/한계 |
|---|---|---|
| Gorse | cluster PoC로 ingestion·offline cache·serving 운영 검증 | 모든 사용자 결과 cache의 cardinality, DB/cache, refresh 시간 |
| Cornac | active cohort/sample의 모델·modality 비교 | model별 메모리 편차, 공통 distributed training 계약 부재 |
| Surprise | explicit-rating 표본의 sanity baseline | Python trainset와 catalogue-wide pair 생성, content/implicit 부재 |
| implicit | active sparse cohort의 ALS/item-item challenger와 작은 pool rerank | 단일 artifact의 user/item factors·CSR·ID map 메모리 |

#### 공통 샤딩 전략

“추천 시스템을 샤딩한다”는 표현을 저장·서빙·학습으로 나눠야 한다.

| 층 | 가능한 shard key | 판단 |
|---|---|---|
| source event | `hash(requester_user_id)` + time partition | 독립 append·집계가 가능해 가장 직접적 |
| requester profile/history | `hash(requester_user_id)` | 한 requester의 history를 한 home shard에서 읽음 |
| candidate catalogue/topic index | `topic_id` 또는 `hash(personal_agent_id)` | topic retrieval과 ID lookup 목적을 분리할 수 있음 |
| factor serving | user/item ID hash | 동일 model version의 factor 배열을 나눠 저장 가능 |
| model training | user/item block | 단순 독립 학습이 아니라 전역 factor를 교환하는 분산 알고리즘 필요 |

권장 online 형태는 다음과 같다.

```text
requester_user_id
  → user-factor home shard

grounding·gate가 만든 candidate IDs 100~1,000
  → item-factor shard별 batch
  → 같은 model_version의 factor 조회
  → shard별 partial scores
  → deterministic merge/top-K
```

factor serving은 비교적 샤딩하기 쉽다. user factor 한 개와 허용 candidate의 item factor만 읽고, 각 shard의
점수를 같은 좌표계에서 비교할 수 있다. 다음 불변식이 필요하다.

- 모든 factor shard가 같은 `model_version`, factor 차원과 ID-map version을 사용한다.
- rollout 중 old/new factor를 섞지 않는다. request가 읽을 version을 먼저 고정한다.
- item 이동·재샤딩 중 중복과 누락을 막고 checksum/row count를 검증한다.
- shard timeout을 낮은 점수로 읽지 않는다. personalization signal absent 또는 요청 실패 정책으로 보낸다.
- privacy gate를 통과한 ID만 shard lookup 대상이 된다.

반면 user를 N개로 나눠 `implicit`/Cornac/Surprise model N개를 독립 학습한 뒤 점수를 합치는 것은 일반적인
해법이 아니다. matrix factorization의 latent 좌표계는 학습마다 회전·부호·scale이 달라질 수 있어 shard A의
`0.8`과 shard B의 `0.8`이 같은 척도가 아니다. candidate를 item shard로 나눠 독립 학습하면 한 requester의
cross-shard 행동도 끊어진다.

```text
잘못된 기본안
  users 0..9M   → model A
  users 10..19M → model B
  model A/B 점수를 그대로 merge

가능한 예외
  tenant·법적 region·catalogue가 실제로 분리되어
  shard 사이 추천과 점수 비교가 제품상 존재하지 않음
```

전역 collaborative signal을 유지하는 학습 샤딩은 user/item factor를 block으로 나누고 ALS iteration마다 서로
교환하는 **분산 학습 알고리즘**의 문제다. 선택한 library 주변에 임의로 추가할 작은 adapter가 아니다. 단일
node capacity를 넘으면 distributed ALS/embedding platform을 새로운 솔루션 후보로 올려 같은 평가를 다시
한다.

어느 프로젝트도 이름만 보고 “1억 지원” 또는 “불가”로 결론내리지 않는다. 다음 실측 gate를 둔다.

1. 1%, 10%, 목표 active snapshot으로 data volume을 단계 확대한다.
2. peak RSS/GPU memory, train wall time, artifact 크기와 load/swap 시간을 기록한다.
3. 요청 pool 10/100/1,000에서 p50/p95/p99 scoring latency를 잰다.
4. cold ID 비율과 model score coverage를 측정한다.
5. Gorse는 user당 cache K에 따른 총 cache entry·refresh lag를 별도 측정한다.
6. 목표 active 규모가 단일 node 예산을 넘으면 샤딩을 즉흥 구현하지 않고 distributed 모델/feature store를
   별도 후보군으로 다시 평가한다.

## 8. 권장 구성

```text
online
  topic-api/discovery candidate generation
    → requester-aware gate
    → model artifact의 personalization score
    → 표면별 가중합
    → exploration
    → 우리 exposure log와 응답

offline
  append-only exposure/feedback
    → 공용 feature extractor
    → implicit 또는 작은 자체 모델 학습
    → Cornac으로 대안 비교
    → versioned artifact
```

- **첫 행동 모델**: `implicit` ALS/BPR와 현재 규칙을 동일한 시간 분할에서 비교한다.
- **모델 탐색**: auxiliary feature가 실제 이득을 보일 때 Cornac modality 모델을 추가한다.
- **Gorse PoC**: 모델보다 운영 플랫폼의 가치가 더 큰지 검증할 때 수행한다.
- **Surprise**: 명시적 평가값 계약이 생기지 않는 한 교육·sanity baseline으로 제한한다.

어느 도구도 requester-aware visibility 판정, topic grounding, self-exclusion, owner note 접근 제어,
노출의 제품적 의미를 소유하지 않는다(§7-5). Gorse처럼 feedback 저장과 추천 API를 제공하는 도구에 저장을
맡길 수는 있지만, 무엇을 노출로 셀지와 후보 집합·position·propensity·model version을 남기는 규격은 우리
계약이다.

## 9. 공통 PoC 합격선

1. 시간 기준 train/validation/test 분할을 쓴다.
2. 동일한 request candidate set을 모든 challenger에 넘긴다.
3. public-only 기준선과 requester-aware friends augmentation을 따로 측정한다.
4. private feature가 candidate 학습 snapshot·artifact에 없음을 구조적으로 검사한다.
5. NDCG/Recall만 보지 않고 false adoption, regression, 집중도, cold-start coverage를 본다.
6. 모델·feature 버전, 후보 집합, surface, position, propensity가 exposure 행에 남는다.
7. artifact 부재·손상 시 현재 규칙 기반 ordering으로 열화한다.

## 10. 공통 데이터 계약 예시

도구별 adapter가 같은 원천을 다르게 읽도록 원본 계약과 학습 projection을 분리한다.

```python
@dataclass(frozen=True, slots=True)
class Exposure:
    request_id: str
    requester_user_id: UUID
    personal_agent_id: UUID
    surface: str
    position: int
    propensity: float
    candidate_source: tuple[str, ...]
    topic_ids: tuple[str, ...]
    model_version: str | None
    feature_version: str
    occurred_at: datetime

@dataclass(frozen=True, slots=True)
class Feedback:
    request_id: str
    requester_user_id: UUID
    personal_agent_id: UUID
    event_type: str
    value: float | None
    topic_id: str | None
    occurred_at: datetime
```

그 위에 도구별 projection을 둔다.

```text
to_gorse_feedback(events)       → Gorse Feedback JSON
to_cornac_uirt(events)          → (user, item, confidence, timestamp)
to_surprise_rating(events)      → 실제 explicit rating만 (user, item, rating)
to_implicit_csr(events)         → CSR + versioned ID maps
```

projection 함수가 원본을 삭제하거나 덮어쓰지 않는다. 학습 식이 바뀌면 같은 원본에서 새 feature version을
재생성한다.

## 11. 공식 자료

- [Gorse data model](https://gorse.io/docs/concepts/data-source),
  [pipeline](https://gorse.io/docs/concepts/pipeline)
- [Cornac repository](https://github.com/PreferredAI/cornac),
  [data and modalities](https://cornac.readthedocs.io/en/stable/api_ref/data.html)
- [Surprise repository](https://github.com/NicolasHug/Surprise),
  [top-N example](https://surprise.readthedocs.io/en/stable/FAQ.html)
- [implicit repository](https://github.com/benfred/implicit),
  [model API](https://benfred.github.io/implicit/api/models/recommender_base.html)
