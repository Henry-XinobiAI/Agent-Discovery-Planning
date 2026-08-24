# Agent 추천 파이프라인 재설계 — topic-api 소비 기반

> **문서 지위**: 설계 초안 (rev 1, 리뷰 대기). 입력 = `topic_api_analysis.md` **rev 5.1**
> (2026-08-24, topic-api HEAD `80c650f`). 이 문서가 확정되면
> `persona_topic_search_design.md`(rev 14)를 대체하는 새 정본이 된다.
>
> **범위**: 큰 그림의 파이프라인 — bourbon-agent의 요청을 받아 topic-api의 어느 endpoint에서
> 어떤 값을 가져와 추천 소스로 쓰는지, 각 단계의 동작·흐름·산출물. 구현 상세(코드 배치,
> 테스트 계획)는 확정 후 코드 repo `tasks/todo.md`로 간다.
>
> **표기**: 분석 문서와 동일 — `검증됨`/`가정`/`미확인`. 이 문서 고유의 **`결정`**(이 문서가
> 확정하려는 것)과 **`열린 결정`**(§9, 리뷰 안건)을 추가로 쓴다.

---

## §0 한 페이지 요약

```
bourbon-agent (recommend_agents tool)
   │  POST /recommend  {topic_text, lang, limit, requester_owner_id, …}
   ▼
S1 Expansion        자유 텍스트 → probe 목록 (작은 LLM 1회, 규칙 R1–R7)
   ▼                산출물: ExpansionResult
S2 Grounding        probe별 GET …/search/topics → is_match 트리 → 선별 → topic_id 1~3개 확정
   ▼                산출물: GroundingResult (outcome 4종)          [0건 → 422]
S3 Retrieval        topic_id별 GET …/topics/{id}/users?limit=100&visibility=public (병렬)
   ▼                산출물: TopicCandidates[] (matched 트리·score_detail·불완전성 플래그 원형 보존)
S4 Merge/Filter     owner 단위 RRF 병합 → self-exclusion → eligibility
   ▼                산출물: CandidatePool                           [0명 → 200+empty]
S5 Ordering         gate → lexicographic 정렬 키 → 결정적 tiebreak (scalar 노출 없음)
   ▼                산출물: OrderedCandidates
S6 Assembly         matched_topics 축약(distance·contribution 소비) + signals + 플래그 게이트
   │                산출물: RecommendResponse
   ▼
bourbon-agent      [topic-api 불능 → 503 / 정직한 empty → 200]
```

**골자**: 우리는 저장소 0의 **순수 소비자 + 얇은 보정층**이다(분석 §8.3-A). topic-api가
어휘(카탈로그)·저장·랭킹을 소유하고, 우리는 ⑴ 자유 텍스트를 카탈로그 어휘로 깎는 일(S1–S2),
⑵ 여러 topic의 랭킹을 한 추천으로 병합하는 일(S4–S5), ⑶ 실패를 정직하게 3분기하는 일(§4),
⑷ 근거를 사용자 언어로 조립하는 일(S6)을 소유한다.

**이 문서가 잠그지 않는 것**: expertise ordering 키의 식(facets 계약 미확정 — 분석 §11-18이
선행 조건), friends tier 사용(분석 §11-17), C단계 rerank 판정층의 진입 조건. 셋 다 슬롯만
설계에 남기고 식·값은 비워 둔다.

---

## §1 원칙 — 승계 규율과 안 하는 것

rev 14에서 승계한 규율(분석 §9의 승계 목록, 이 파이프라인에 결합되는 형태로):

| 규율 | 이 설계에서의 자리 |
|---|---|
| 실패 의미 3분기 (422 / 200+empty / 503) + 오귀속 금지 | §4 — 판정 지점을 단계에 고정 |
| ordering = lexicographic 계약, scalar 단일 점수 노출 금지 | S5 |
| self-exclusion 서버측 원칙 (지금은 우리 층) | S4 |
| 즐겨찾기 = tiebreak only, gate 우회 금지 | S5 |
| popularity prior 금지 | S5 (RRF는 topic별 순위 융합 — 전역 인기 항 없음) |
| 판정 입력 텍스트 전부 비신뢰 | S1·S2의 LLM 프롬프트 (카탈로그 라벨·유저 서술 모두) |
| gate 3종 직교 (maturity / safety / privacy) | privacy는 topic-api 구조가 보장(분석 §6), maturity는 §11-6 대기, safety는 타 팀 |
| best-effort 입력 선언 | 사슬 전체(deferq→extractor→topic-api)가 best-effort — freshness 가정 금지 |
| wire 계약: 응답 파싱은 실효 계약 기준·계약 테스트 payload를 consumer model에서 유도 금지 | §6 어댑터 |

**안 하는 것** (분석 §8.2·§8.3): 병렬 두 시스템 금지 — 우리 topic 저장소·색인·스트림 없음.
NeedType 축·stance 파이프라인 삭제(1차 유형은 "이 topic을 가장 잘 아는 agent" 하나).
rollup 회피를 위한 재질의 없음(분석 §13-9 — rollup 응답도 정상 경로, 사후 판별·로깅만).
read-time 판정 gate 없음(C단계 rerank는 dormant 슬롯).

---

## §2 S0 — 요청 계약 (bourbon-agent → 우리)

현행 `Query`(코드 repo `discovery/structs/recommend.py`, 검증됨)에서 출발해 두 필드를 뺀다:

| 필드 | 처분 | 근거 |
|---|---|---|
| `topic_text` (min 1) | **유지** — S1의 입력 | |
| `need_type` | **삭제** | 1차 유형 단일화(분석 §13-1, rev 14 폐기 목록) |
| `proposition` | **삭제** | stance 파이프라인 폐기 |
| `lang` (기본 ko) | **유지** — S6에서 라벨 언어 선택에 사용 | internal 응답은 언어 맵이라 선택이 우리 몫(분석 §1.2) |
| `limit` (1–50, 기본 10) | **유지** — 최종 응답 개수. S3의 fan-out limit(100)과 무관 | |
| `eligibility_context` | **유지** — S4의 EligibilityProvider 입력 | Q12 stub 유지 |
| `context_messages` | **유지(선택)** — S1 expansion의 보조 문맥 | 원문은 파이프라인에 비전달(기존 규율) |
| `requester_owner_id` | **유지** — S4 self-exclusion의 대상 | real-edge 배포는 필수(기존 계약) |

`결정`: 요청 wire의 이름·모양은 위 삭제 2건 외 바꾸지 않는다 — bourbon-agent 쪽 변경을
최소화한다. 삭제 2건은 breaking이므로 스키마 버전 표기와 함께 bourbon-agent에 통지.

---

## §3 단계별 설계

각 단계는 `동작 → topic-api 호출 → 산출물 → 실패 → 계측` 순으로 쓴다. 산출물 타입 이름은
제안이며 코드 배치는 구현 계획의 몫.

### S1 Expansion — 자유 텍스트를 probe로

**동작**: `topic_text`(+선택적으로 `context_messages` 요약)를 작은 LLM 1회에 넣어
**probe 목록**을 만든다. 프롬프트 제약은 분석 §10-2의 R1–R7을 그대로 옮긴다:

- 명사구만, 긴 형태부터 점진 축소(R1), 조사·활용 제거(R2)
- ko·en 병렬 생성 + 한자어 동의어(R3) — 같은 개념의 언어 변형은 한 그룹으로 묶어 귀속 유지
- "Wikidata 항목명처럼 써라"(R4)
- 최소 길이: 영문 4자+/한글 2자+(R5), 공백 변형 생성 금지(R6)
- probe 수 상한: **6** (개념 최대 3 × 언어 최대 2 — `열린 결정` ②)

**topic-api 호출**: 없음 (LLM proxy만).

**산출물**: `ExpansionResult { probes: [{text, lang, concept_group, rank}], source: llm | fallback }`

**실패**: LLM 실패/timeout → **fallback = 정규화한 원문 1 probe**. 원문이 길면 S2에서 0건이
나고 422로 흐른다 — 이것이 올바른 의미다(expansion 실패를 500으로 오귀속하지 않는다).

**계측**: probe 수 분포, LLM 지연, fallback 비율.

### S2 Grounding — probe를 topic_id로

**동작**: probe마다 topic 검색을 **병렬** 호출하고, 응답 트리에서 **`is_match=true` 노드만**
후보로 수집한다(조상 scaffolding을 결과로 취급하지 않는다 — topic-api 자신의 후보 조립도
같은 규칙이다, 분석 §2.2). topic_id 기준 union하되 **어느 probe가 맞췄는지 귀속을 유지**한다.

선별(후보 → 확정 1~3개):

1. **rule pass**: probe별 매치 수가 캡(20)에 닿았으면 그 probe의 매치는 신뢰 하향(분석 §2.1
   `ai` 사례 — 캡 도달은 노이즈 신호). exact-label 일치(정규화 기준 라벨==probe)는 신뢰 상향.
2. **LLM rerank 1회**: 후보 topic들의 {labels, is_match 트리의 조상 문맥}을 주고 `topic_text`
   원문과의 관련도로 상위 1~3개 선별. **exact-label winner 명시 가드** 승계(기존
   grounding-mode 규율) — exact 일치가 있으면 LLM이 뒤집지 못한다.
   (`열린 결정` ⑥: A단계 초기에 이 LLM 호출을 켤지, rule pass만으로 시작할지.)

**topic-api 호출**: `GET /api/internal/svc/topic/search/topics?q={probe}&limit=20` × probe 수.
짧은 TTL 캐시(키 = normalize(probe), TTL은 그들 배포 주기보다 짧게 — 분석 §13-8,
`열린 결정` ⑦).

**산출물**: `GroundingResult { topics: [{topic_id, labels(3언어 맵), matched_probes[],
exact_label: bool}], outcome: grounded | failed | ambiguous | unavailable }`
— outcome 4종은 C4 실패 계약을 승계한다.

**실패**: 전 probe 0건 → `failed` → **422** ("카탈로그에 그 topic이 없다" — §4).
후보는 있으나 선별 신뢰 미달 → `ambiguous` → 422(구분 코드).
topic-api 5xx/timeout → `unavailable` → **503**.

**계측**: probe 0건율(= 카탈로그 커버리지 지표, 분석 §12.3), 후보 수→확정 수, exact-label
비율, unmatched probe의 원문 기록(→ seed 요청 채널의 근거 데이터, 분석 §8.3-B).

### S3 Retrieval — topic_id별 후보 유저 수집

**동작**: 확정 topic마다 유저 랭킹을 **병렬** 호출한다. **항상 `limit=100`**(컷 한계 (a)안 —
분석 §9: 컷은 그들 score로 일어나고 페이징이 없으므로, 최대로 받아 우리 층의 재량을 확보한다.
만료 조건 계측 동봉). **`visibility=public` 단독**(분석 §11-17 — friends는 제품 결정 대기).

응답에서 보존하는 것(어댑터가 버리지 않는다):

- `items[].user_id`, `score`(그들의 감쇠 합산 총점 — 참고값, 우리 wire에 비노출)
- `items[].matched[]` **트리 원형**: topic·item(descriptions·blocks의 `score_detail` 포함)·
  `distance`(부호 그대로)·`contribution`·children
- 불완전성 플래그: `exhaustive`, `descendants_dropped`, `topics_dropped`

**topic-api 호출**: `GET /api/internal/svc/topic/topics/{topic_id}/users?limit=100&visibility=public`
× 확정 topic 수(≤3). (id 리스트 라우트가 생기면 — 분석 §11-16 — 이 단계만 1호출로 교체된다.
그때까지 병합은 S4의 우리 RRF.)

**산출물**: `TopicCandidates { topic_id, users: [...위 보존 필드...],
flags: {exhaustive, descendants_dropped, topics_dropped}, was_rollup: bool }`
— `was_rollup`은 사후 판별(응답 matched에 `distance > 0` 존재 — 분석 §8.3-A). 분기용이
아니라 계측·비용 귀속용.

**실패**: topic 1개의 404(배포 사이 카탈로그 변경으로 id 소멸 — 드묾) → 그 topic만 탈락,
로깅. 부분 5xx/timeout → `열린 결정` ①(제안: 성공분으로 진행 + 응답 내부 품질 표시 + 로깅,
**전부** 실패 시에만 503). `exhaustive=false` → 탈락시키지 않고 로깅 + 품질 표시(A단계는
게이트 아님 — 분석 §10-7).

**계측**: "grounded인데 공개 보유자 0" 비율(= 공개 밀도 지표), 플래그 3종 분포, topic당
반환 유저 수 분포(100 근접 = 컷 경계 접근 — (a)안 만료 감시), rollup 비율.

### S4 Merge & Filter — owner 단위 병합

**동작**:

1. **RRF 병합**: topic별 순위를 `Σ 1/(k + rank_t(u))`(k는 `열린 결정` ③, 표준 60 제안)로
   owner 단위 융합. topic-api의 `score` 절대값을 섞지 않고 **순위만** 쓴다 — 점수 의미
   (관심 편향, 분석 §4)와 topic 간 스케일 차이를 우리가 재해석하지 않기 위해서다.
   여러 topic에 걸린 owner가 자연히 위로 온다.
2. **evidence 병합**: owner별로 topic마다 {topic_id, contribution, distance, score_detail?,
   descriptions?}를 모은다 — S6의 재료.
3. **self-exclusion**: `requester_owner_id` 제거(기존 구현 승계). fan-out이 100이라 cap 손실
   문제는 실질 완화되지만 서버측 `exclude_user_ids`(분석 §11-5)는 계속 요청한다.
4. **eligibility**: `EligibilityProvider.check`(현 AllowAll stub 유지, Q12).

**topic-api 호출**: 없음.

**산출물**: `CandidatePool { candidates: [{user_id, rrf_rank, evidences: [...]}],
degraded: bool (S3 부분 실패·플래그 반영) }`

**실패**: 병합 후 0명 → **200 + empty**("topic은 있으나 공개 보유자 없음" — §4. cold-start의
정상 경로다, 분석 §6.4).

**계측**: 병합 전→후 후보 수, self-exclusion 제거 수, 다중 topic 매칭 owner 비율.

### S5 Ordering — 정렬과 tiebreak

**동작**: lexicographic 정렬 키(분석 §9의 ordering 계약 재해석):

```
gate(현 A단계: privacy=구조 보장, maturity=§11-6 대기로 비활성)
  → 1키: 정렬 전략 슬롯 (기본 전략 = RRF 순위)
  → 2키: 즐겨찾기 tiebreak (승계 — gate 우회 금지, 동순위에서만)
  → 3키: user_id bytes (결정적 — topic-api와 같은 규율)
```

**전략 슬롯**: expertise ordering 키(facets 기반)는 **facets 계약 확정(분석 §11-18)이 선행
조건**이므로 지금은 식을 잠그지 않는다. 슬롯의 계약만 잠근다 — 입력은 S4의 evidence(원형
score_detail 포함), 출력은 전순서(total order), **facet 필드 이름에 하드바인딩 금지**(모르는
facet 무시, 기대 facet 부재는 null 처우 규칙으로 — 분석 §13-3). 기본 전략(RRF)은 facets를
전혀 읽지 않으므로 dummy 기간에도 안전하다.

**산출물**: `OrderedCandidates` (상위 `limit`개로 절단).

**계측**: 전략 교체 시 A/B 근거용 — 기본 전략과 후보 전략의 순위 불일치도(단, **실데이터
주입 후에만 의미** — 분석 §12.3 주의).

### S6 Assembly — 응답 조립

**동작**:

1. **matched_topics 축약**(분석 §13-2의 답): owner별 **대표 topic = contribution 최대**인
   evidence. 대표 외 topic은 개수와 라벨만 요약. 계층 문맥은 matched 트리의 `distance`로
   복원한다 — 노드 위치가 아니라(분석 §2.2 rev 5.1: depth 2는 조상 사슬만 접는다).
2. **라벨 언어 선택**: internal 응답은 3언어 맵이므로 `lang` 요청값으로 우리가 고른다.
   fallback 규칙은 topic-api의 `pick`과 동일(요청어 → en → 없음)로 맞춘다 — 유저가 프로필
   화면에서 보는 라벨과 추천 이유의 라벨이 갈라지지 않게(축 이전의 근거 1).
3. **signals**: always-on 승계(플래그·rollup 여부·degraded를 내부 신호로). reason generator는
   OFF 유지(기존).
4. **응답 wire**: 후보별 {owner_id, matched_topics(대표+요약), signals}. **scalar 점수
   비노출**(순위가 곧 응답 순서).

**산출물**: `RecommendResponse`.

**계측**: 분석 §12.3의 5종을 이 단계에서 최종 집계·로깅.

---

## §4 실패 의미 3분기 — 판정 지점 고정

분석 §10-3·§13-4의 답. topic-api는 "매칭 0건"과 "보유자 0명"을 모두 200+빈 배열로 답하므로
**구분은 우리 단계가 만든다**:

| 상황 | 판정 단계 | wire |
|---|---|---|
| 카탈로그에 topic 없음 (전 probe 0건) | S2 (`failed`) | **422** |
| grounding 신뢰 미달 | S2 (`ambiguous`) | **422** (구분 코드) |
| topic 있으나 공개 보유자 0 / 필터 후 0 | S4 | **200 + empty** |
| topic-api 불능 (S2·S3 전면 5xx/timeout) | S2/S3 (`unavailable`) | **503** |
| S3 부분 실패 | S3→S4 | 200 + degraded 표시 (`열린 결정` ①) |

오귀속 금지: expansion LLM 실패는 fallback으로 흡수(S1), 어댑터 파싱 실패는 503이 아니라
계약 위반 로깅 + 503(topic-api 응답이 계약을 깼다는 뜻이므로) — 422로 위장하지 않는다.

---

## §5 산출물 요약

| 단계 | 산출물 | 소비자 |
|---|---|---|
| S1 | `ExpansionResult` (probes + 귀속) | S2, 계측 |
| S2 | `GroundingResult` (topic 1~3 + outcome) | S3, §4 판정, 계측 |
| S3 | `TopicCandidates[]` (유저+matched 트리 원형+플래그) | S4, 계측 |
| S4 | `CandidatePool` (RRF 순위 + evidence 병합) | S5 |
| S5 | `OrderedCandidates` | S6 |
| S6 | `RecommendResponse` | bourbon-agent |

decision log(기존 규율)는 단계마다 산출물 요지를 남긴다 — expansion probe, grounded topic,
플래그, 병합 전후 수, 최종 순위 근거.

---

## §6 topic-api 의존 표면과 어댑터 경계

**호출하는 endpoint 전부** (internal 표면, 메시 내 직접 호출 — 게이트웨이 불요, 분석 §7-3):

| endpoint | 단계 | 파라미터 | 캐시 |
|---|---|---|---|
| `GET /api/internal/svc/topic/search/topics` | S2 | `q`(probe), `limit=20` | 짧은 TTL (⑦) |
| `GET /api/internal/svc/topic/topics/{id}/users` | S3 | `limit=100`, `visibility=public` | 없음 (유저 데이터 — 신선도 우선) |

쓰기 endpoint는 호출하지 않는다. `/search/users`(이름→유저 직행)도 쓰지 않는다 — grounding
선별을 우리가 소유하기 위해 두 단계를 분리한다(분석 §10-2 R7).

**어댑터 경계**(분석 §13-7): topic-api 응답의 wire 모델 → 우리 도메인 타입 변환은 provider
모듈 한 곳. 계약 테스트는 **실제 응답 payload 고정본**에서 (consumer model 유도 금지 — wire
규율). composition root는 real provider만. `score_detail`(facets)은 **불투명 dict로 통과** —
필드명 하드바인딩 금지(분석 §11-18 대기), S5 전략 슬롯만 해석 시도.

**버전 감지**: 산출물의 `built_at`/`dump_version`은 응답에 없으므로(분석 §13-8) 캐시는 짧은
TTL로만. 계약 drift는 계약 테스트 + 파싱 실패 로깅으로 잡는다.

---

## §7 기존 discovery/ 코드와의 매핑

| 현행 | 처분 |
|---|---|
| `api/` 라우터·에러 매핑·request_id | **유지** (요청 wire에서 need_type·proposition 삭제) |
| `discovery/pipeline.py` 오케스트레이션 | **유지·개조** — 단계 구성 교체 |
| `expansion.py` | **개조** — R1–R7 프롬프트로 |
| `linker.py`·`rerank.py` (2-tier EL) | **개조** — S2 선별로 (exact-label 가드 승계) |
| `grounding_agent.py`·`grounding_tools.py` | **교체** — memory 앵커 grounding → topic 검색 grounding |
| `retrieval.py`·`providers/`(memory-api) | **교체** — topic-api provider 신설 |
| `self_exclusion.py`·`exclusion.py` | **유지** (S4) |
| `gate.py` | **유지·휴면** — maturity 입력 확정(§11-6) 대기 |
| `ranking.py` | **개조** — RRF + lexicographic + 전략 슬롯 |
| `stance*.py`·need_type 경로 | **삭제** |
| `serving.py`·`decision_log*`·`observability/`·`llm/` | **유지** |
| eval 코퍼스 | **재작성** — 기존 질의·앵커는 memory 앵커 세계의 어휘(분석 §12.1 주의) |

삭제·교체의 실행 순서는 구현 계획(`tasks/todo.md`)에서.

---

## §8 분석 §13 질문과의 대응

| §13 질문 | 이 문서의 답 |
|---|---|
| 1 호출 형태·컴포넌트 소유 | §0·§3·§7 |
| 2 병합 규칙·대표 topic | S4 RRF(순위만) · S6 대표=contribution 최대 |
| 3 ordering 키 식 | **부분** — 슬롯 계약만(S5). 식은 §11-18 확정 후 |
| 4 실패 3분기 판정 지점 | §4 (probe 일부만 0건 = 나머지로 진행, 전부 0건만 422) |
| 5 eligibility 결합 지점 | S4 사후 필터 + fan-out 100으로 cap 손실 완화 (서버측 파라미터는 계속 요청) |
| 6 rerank 진입 조건 | **미정** — C단계 dormant 슬롯만 (§9-⑥와 별개) |
| 7 어댑터 경계 | §6 |
| 8 캐시 | §6 — /search/topics만, 짧은 TTL |
| 9 rollup 수용 | S3 — 그대로 수용, `was_rollup` 사후 판별은 계측 전용 |
| 10 cold-start UX | **부분** — 200+empty의 wire는 정직한 빈 배열 + 사유 코드. tool 발화는 bourbon-agent 협의 필요 |

---

## §9 열린 결정 (리뷰 안건)

1. **S3 부분 실패 규칙** — 제안: 성공분으로 진행 + degraded 표시, 전면 실패만 503.
   반론 여지: 부분 결과가 "왜곡된 랭킹"일 수 있음(한 topic이 통째로 빠지면 그 topic 전문가가
   전부 누락).
2. **probe 수 상한(6)·grounding limit(20)·확정 topic 수(1~3)** — 기본값 제안. 측정 후 조정.
3. **RRF k=60** — 표준값 제안.
4. **matched_topics wire 모양** — distance 부호를 그대로 노출할지, 우리 wire로 단순화
   (예: 대표 topic + "하위 topic n개 포함")할지.
5. **expansion LLM 모델·예산** — 기존 proxy 경유 flash-lite 계열 제안 (~500–1000 input tokens).
6. **S2 LLM rerank를 A단계 초기부터 켤지** — 대안: exact-label rule만으로 시작하고 ambiguous
   비율을 측정한 뒤 켠다. (판정층 §13-6과는 별개 — 이것은 topic 선별, 그것은 후보 재정렬.)
7. **/search/topics 캐시 TTL** — 제안 5분 (그들 배포 주기 대비 충분히 짧음).
8. **200+empty의 사유 코드 체계** — "no_public_holders" / "degraded" 구분을 wire에 실을지.

---

## 변경 이력

- **2026-08-24 rev 1** — 최초 작성. 입력 = `topic_api_analysis.md` rev 5.1. 큰 그림
  파이프라인(S1–S6)·단계별 topic-api endpoint·산출물·실패 3분기 판정 지점·§13 질문 대응을
  담고, expertise 키 식·friends tier·C단계 rerank는 슬롯으로 비워 둠. 리뷰 대기.
