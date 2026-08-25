# Agent 추천 파이프라인 재설계 — topic-api 소비 기반

> **문서 지위**: 설계 정본 (rev 5.7, 외부 리뷰 3회 반영). 입력 = `topic_api_analysis.md` **rev 8**
> (2026-08-25, topic-api HEAD `9ee67f3`) + bourbon-agent의 기왕 계약
> (`bourbon_agent/agents/personal_agent/recommendation/structs.py`, mock client가 지키는 중).
> `persona_topic_search_design.md`(rev 14)가 2026-08-24 `archive/`로 이동하며 이 문서가 그 자리를
> 대체하는 정본이 됐다(열린 결정은 §9에 잔존).
>
> **범위**: 큰 그림의 파이프라인 — bourbon-agent의 요청을 받아 topic-api의 어느 endpoint에서
> 어떤 값을 가져와 추천 소스로 쓰는지, 각 단계의 동작·흐름·산출물. **노출 표면**(internal-only·
> edge-auth 관례·배포 델타·surface 테스트)은 `serving_surface_design.md`가 소유한다.
> 구현은 `project-template-python`에서 신규 시작한다(2026-08-24 오너 결정 — 같은 문서 §1-4).
>
> **표기**: 분석 문서와 동일 — `검증됨`/`가정`/`미확인`. 이 문서 고유의 **`결정`**(이 문서가
> 확정하려는 것)과 **`열린 결정`**(§9, 리뷰 안건)을 추가로 쓴다.

---

## §0 한 페이지 요약

```
bourbon-agent (recommend_agents tool)
   │  POST /recommend  {topic(en canonical), context, max_results, requester_user_id, room_id}
   ▼
S1 Expansion        topic 원문 = 기본 probe + topic·context 기반 확장 (작은 LLM 1회, R1–R7)
   ▼                산출물: ExpansionResult (concept group이 probe를 소유 — 일급 객체)
S2 Grounding        probe별 GET …/search/topics → is_match 트리 → **concept_group당 정확히
   ▼                1 topic 확정** (못 고르면 ambiguous)
                    산출물: GroundingResult (outcome 4종)
                    [expansion 정상+전체 0건 → 422 / expansion 실패+fallback 0건 → 503]
S3 Retrieval        topic_id별 GET …/topics/{id}/users?limit=100&visibility=public (병렬)
   ▼                산출물: TopicCandidates[] (matched 트리·score_detail·불완전성 플래그 원형 보존)
S4 Merge/Filter     독립 concept group 간 RRF 병합 → stub 방어 필터 → exclusion → eligibility
   ▼                산출물: CandidatePool                           [0명 → 200+empty]
S5 Ordering         gate → lexicographic 정렬 키 → 결정적 tiebreak (scalar 노출 없음)
   ▼                산출물: OrderedCandidates
S6 Assembly         owner→agent id 변환(uuid5) + matched_topics 축약 + 플래그 게이트
   │                산출물: RecommendResponse (signals는 wire가 아니라 decision log)
   ▼
bourbon-agent      [topic-api 불능 → 503 / 정직한 empty → 200]
```

**골자**: 우리는 저장소 0의 **순수 소비자 + 얇은 보정층**이다(분석 §8.3-A). topic-api가
어휘(카탈로그)·저장·랭킹을 소유하고, 우리는 ⑴ 자유 텍스트를 카탈로그 어휘로 깎는 일(S1–S2),
⑵ 여러 topic의 랭킹을 한 추천으로 병합하는 일(S4–S5), ⑶ 실패를 정직하게 3분기하는 일(§4),
⑷ 근거를 사용자 언어로 조립하는 일(S6)을 소유한다.

**이 문서가 잠그지 않는 것**: expertise ordering 키의 식(facets 계약 미확정 — 분석 §11-18이
선행 조건), friends tier 사용(분석 §11-17 — rev 5.6: 상류 지원 예고로 성격이 "우리가 교차
필터"에서 "상류 계약 소비"로 바뀜), C단계 rerank 판정층의 진입 조건. 셋 다 슬롯만
설계에 남기고 식·값은 비워 둔다.

---

## §1 원칙 — 승계 규율과 안 하는 것

rev 14에서 승계한 규율(분석 §9의 승계 목록, 이 파이프라인에 결합되는 형태로):

| 규율 | 이 설계에서의 자리 |
|---|---|
| 실패 의미 3분기 (422 / 200+empty / 503) + 오귀속 금지 | §4 — 판정 지점을 단계에 고정 |
| ordering = lexicographic 계약, scalar 단일 점수 노출 금지 | S5 |
| self-exclusion·제외 집합 = **우리 후처리로 확정**(2026-08-24 결정 — countable 목록·fan-out 100이라 오버헤드 무시 가능) | S4 |
| 즐겨찾기 = tiebreak only, gate 우회 금지 | S5 — 단 **dormant 슬롯**: 현 파이프라인에 즐겨찾기 데이터 공급처가 없다. provider가 생길 때까지 이 키는 비활성 |
| popularity prior 금지 | S5 (RRF는 topic별 순위 융합 — 전역 인기 항 없음) |
| 판정 입력 텍스트 전부 비신뢰 | S1·S2의 LLM 프롬프트 (카탈로그 라벨·유저 서술 모두) |
| gate 3종 직교 (maturity / safety / privacy) | privacy는 topic-api 구조가 **대부분** 보장하나 leaf stub 구멍이 남아 있다(분석 §6.3 — §11-4 **블로커** 승격). 근본 수정은 topic-api, 우리는 S4의 stub 방어 필터를 임시 방어로 병행. maturity는 §11-6 대기, safety는 타 팀 |
| best-effort 입력 선언 | 사슬 전체(deferq→extractor→topic-api)가 best-effort — freshness 가정 금지 |
| wire 계약: 응답 파싱은 실효 계약 기준·계약 테스트 payload를 consumer model에서 유도 금지 | §6 어댑터 |

**안 하는 것** (분석 §8.2·§8.3): 병렬 두 시스템 금지 — 우리 topic 저장소·색인·스트림 없음.
NeedType 축·stance 파이프라인 삭제(1차 유형은 "이 topic을 가장 잘 아는 agent" 하나).
rollup 회피를 위한 재질의 없음(분석 §13-9 — rollup 응답도 정상 경로, 사후 판별·로깅만).
read-time 판정 gate 없음(C단계 rerank는 dormant 슬롯).

---

## §2 S0 — 요청 계약 (bourbon-agent → 우리)

`결정`(rev 2): **wire를 bourbon-agent가 이미 잡아놓은 계약에 맞춘다** — 그쪽 mock client가
이 계약을 지키고 있고 "real API가 생기면 tool 배선은 그대로, client 구현만 교체"가 명시
의도다(`recommendation/client.py` docstring, 검증됨). 어차피 우리 wire는 need_type·proposition
삭제로 깨지므로, 필드명까지 옮기는 비용이 지금이 가장 싸다.

| 필드 (bourbon-agent 계약) | 의미·우리 단계 | 비고 |
|---|---|---|
| `topic: str` | **en canonical noun phrase 기본** — S1의 기본 probe이자 확장의 축 | 모델이 추출·번역. tool 스키마 설명에 "English canonical noun phrase" 명시(그쪽 프롬프트 1줄). 근거: en label 2,605/2,605(100%)·alias 77%가 라틴·topic-api 자신의 extractor도 query_phrases를 영어 한정으로 못 박음(분석 §1.5) — 전부 실측/검증됨 |
| `context: str \| None` | S1 확장의 보조 문맥 (단일 문자열) | 구 context_messages(리스트)를 대체. 원문은 S1 밖으로 비전달(기존 규율 유지) |
| `max_results: int = 3` | 최종 응답 개수 (구 limit) | 모델이 못 고름 — 그쪽 handler가 고정. S3 fan-out limit(100)과 무관 |
| `requester_user_id: UUID` | S4 self-exclusion 대상 (구 requester_owner_id) | handler가 task payload에서 채움 — 모델 공급 신원 비신뢰(그쪽 규율, 우리 규율과 일치) |
| `room_id: UUID` | 지금은 로깅만 | 오너 의도(협의 2026-08-24): "방 관련 정보를 더 요청할 수 있는 키". **in-room 제외는 defer 합의** — OBT까지는 내 에이전트가 추천하는 구조라 같은 방 상황이 사실상 없음. 단 추후 `room_members`가 오면 requester와 **같은 제외 집합**으로 처리하도록 S4를 집합 인터페이스로 설계해 둔다 |

**삭제**: `need_type`·`proposition`(1차 유형 단일화·stance 폐기), **`lang`**(불필요해짐 —
S6에서 matched_topics에 ko·en 라벨을 병기해 보내면 최종 발화는 bourbon-agent 모델이 대화
언어로 렌더한다). `eligibility_context`는 wire에서 빼고 우리 내부에서 room_id·requester로
구성(Q12 stub 유지).

**응답 쪽 간극 — 협의 결과(2026-08-24, §9-⑨)**: 그들의 `RecommendedAgent`
`{id, name, description, expertise[], match_reason}`에서 `name` = 추천되는 user(owner)의
이름, `description` = personal agent에서는 **현재 항상 NULL**(추후 채워질 수 있고, 기획이
노출하지 않기로 하면 응답에는 불필요 — 단 "추천 판단에만 필요한 정보"가 될 수는 있다).
**hydration 책임 — rev 5.5에서 "추후 기획 결정"에서 S6 선행 블로커로 승격**(외부 리뷰
3차 수용): bourbon-agent의 현재 wire는 strict 모델에 `name: str`·`description: str`이
**필수**라(`recommendation/structs.py:31-34`, 검증됨), 책임이 정해지기 전에는 S6이 유효한
응답을 만들 수 없다 — 후속 제품 결정이 아니라 **구현·통합 테스트를 막는 선행 결정**이다.
옵션과 권고(§9-⑨): **권고 = (b)** bourbon-agent가 agent ID로 hydration + 우리 wire 축소,
차선 = (c) 그쪽 wire의 name/description nullable화, **배제** = (a) 우리가 bourbon-api를
직접 호출(hot path 의존 신설)과 `description=""` 채우기(타입만 통과시키는 가짜 계약).
이 문서의 설계는 (b)/(c) 어느 쪽이 되든 성립하도록 우리 산출물을 `id`(**agent** — S6-0
변환 후. rev 5.5 정정: 구판의 "owner" 표기는 S6-0과 자기모순) + `expertise` 재료(matched
topic 라벨 ko·en) + `match_reason` 재료(대표 topic·기여 요지)로 고정해 둔다.

---

## §3 단계별 설계

각 단계는 `동작 → topic-api 호출 → 산출물 → 실패 → 계측` 순으로 쓴다. 산출물 타입 이름은
제안이며 코드 배치는 구현 계획의 몫.

### S1 Expansion — topic을 축으로 probe 만들기

**동작** (rev 2 재서술):

1. **`topic` 원문은 항상 probe다** — LLM 산출과 무관하게 probe 목록에 무조건 포함한다.
   topic이 en canonical로 오는 계약(§2)이므로 원문 자체가 이미 좋은 probe이고, LLM 실패
   fallback과 같은 경로가 된다(별도 fallback 분기 불필요).
2. 작은 LLM 1회가 **`topic` + `context`**를 입력으로 확장 probe를 만든다. context는 topic의
   중의성 해소와 구체화에만 쓴다(예: topic "python" + context가 뱀 이야기면 동물 쪽으로).
3. **프롬프트에 topic-api가 topic을 만들고 매핑하는 방식을 설명 블록으로 내장한다** —
   규칙을 아는 자만 쓸 수 있는 레버(분석 §2.1)를 LLM에게 그대로 준다:
   - 카탈로그 = 큐레이션된 Wikidata 항목 집합. 각 topic은 ko/en/ja label + Wikidata alias
     (≤50, 77%가 영어)를 가진다
   - 매칭 = 정규화(소문자화+공백 제거+**NFC**) 후 **probe가 label/alias의 substring**이어야
     한다 — probe가 label보다 길면 절대 못 맞는다. **단 latin probe는 substring만으로 부족하고
     단어 시작이어야 한다**(rev 5.6 — topic-api `42f59bf`): `tent`는 `content`에 안 걸린다.
     CJK probe는 substring 그대로다(`위스키` ⊂ `싱글몰트위스키`)
   - **관련도 서열 있음**(rev 5.6, 구 "순위 없음"): label > alias, 그 안에서 exact > 단어시작 >
     substring 순으로 **정렬한 뒤** 캡 20을 적용한다. 캡이 자르는 것은 **상류 tier에서 후순위인
     매치**이지 의미상 약한 매치가 아니다 — 둘은 같지 않다: label 단어시작이 alias exact를
     이기므로 **의미상 강한 약어 매치가 무관한 label 뒤로 밀린다**(`ai` → 인공지능 16위,
     분석 §2.1 rev 8). 약어는 풀어서 보내는 편이 안전하다
   - 따라서: Wikidata 항목명처럼 쓸 것(R4), 명사구만·긴 형태부터 축소(R1), 조사·활용
     제거(R2), 영문 4자+/한글 2자+(R5), 공백 변형 금지(R6)
   이 설명은 정적 프롬프트로 안전하다 — 매칭 **규칙**은 안정적이고 배포마다 움직이는 것은
   **어휘**뿐이다(분석 §2.1).
4. **언어 배분 = en 우선·ko 보조**(R3 재서술, 실측 근거): en ⊇ ko가 다수지만 12쌍 중 4쌍은
   ko가 en이 놓치는 topic을 잡았다(hiking 0 vs 등산 2, cooking, investment, 기계학습 —
   실물 카탈로그 실측). probe는 인메모리 검색+캐시라 한계 비용이 0에 가까우므로 ko를
   버리지 않는다. 상한 6 = **원문 1 + en 확장 ≤3 + ko 변형 ≤2**, 결과는 S2에서 qid union.
5. **길이 가드 — verbatim도 예외 없음**(rev 5): R5 미달(영문 <4자·한글 <2자) 또는 100자
   초과(topic-api `NameQuery` max_length=100 — 넘겨 보내면 그쪽 422를 우리가 맞는다)인
   probe는 **전송하지 않는다.** 원문 probe도 같은 가드를 통과해야 한다 — 원문이라는 이유로
   R5를 우회하면 topic="AI" 같은 입력이 캡 노이즈를 그대로 부른다. 가드를 통과한 probe가
   0개면 판단에 도달할 수 없는 상태다(→ §4의 unavailable 경로). 요청 wire 자체에도 상한을
   둔다: `topic` ≤200자·`context` ≤2,000자(`열린 결정` ⑪).

**topic-api 호출**: 없음 (LLM proxy만).

**산출물**(rev 5.5 — concept group을 일급 객체로. 구판의 `probe.concept_group` 필드는
"probe는 정확히 한 그룹"을 검증에 맡겼는데, 그룹을 컨테이너로 두면 구조가 보장한다):

```
ExpansionResult {
  groups: [ { group_id, intent,        # intent = 이 그룹이 겨냥하는 의미 축(자유 서술, 로그용)
              probes: [{text, lang, rank, origin: verbatim | llm}] } ],
  degraded: bool
}
```

**concept group 생성 계약**(rev 5.5 신설 — S2의 그룹당 1 topic과 S4의 그룹 간 RRF가 전부
이 계약 위에 선다. 이게 틀리면 같은 개념이 독립 신호처럼 이중 가산된다):

- **정의**: 그룹 = **독립적인 의미 축**. 언어·표기·broad/narrow는 그룹 경계가 아니다 —
  같은 의미의 en/ko/광의/협의 probe는 반드시 **같은** 그룹에 속한다(프롬프트에 명시).
- **verbatim probe는 주 개념 그룹 소속** — 원문 topic이 겨냥하는 개념의 그룹에 넣는다.
- **구조 검증**(S1 출력에서 코드로 강제 — LLM 출력을 신뢰하지 않는다): ⑴ probe는 정확히
  한 그룹(위 shape가 구조로 보장), ⑵ **정규화 기준 동일 probe의 그룹 간 중복 금지**,
  ⑶ 그룹 수 ≤ 3(`열린 결정` ②의 "확정 topic ≤3"과 같은 값·같은 안건), ⑷ 그룹당 probe ≥ 1.
- **malformed 출력**(그룹 간 중복 probe·빈 그룹·상한 초과·파싱 불가): 그 LLM 출력을
  **통째로 버리고** degraded 경로로 진행한다 — 원문 probe 1개짜리 단일 그룹(C4 규율:
  판단에 도달하지 못한 출력을 고쳐 쓰지 않는다). 부분 구제(살릴 그룹만 살리기)는 하지
  않는다 — 중복이 있었다는 사실 자체가 그룹 경계 전체를 불신하게 만든다.

**실패**: LLM 실패/timeout → probe = 원문 1개로 진행(`degraded=true`). **degraded 상태의
0건은 422가 아니다** — expansion이 살아 있었다면 발견했을 topic일 수 있으므로, 판단에
도달하지 못한 것으로 보고 §4의 unavailable(503) 경로로 보낸다(C4 규율: 재시도 기준은
"판단에 도달했는가"). degraded 상태에서 원문 probe가 exact hit를 냈을 때만 degraded 성공.

**계측**: probe 수 분포, 언어별 히트 기여(en/ko probe 각각이 확정 topic을 몇 번 맞췄나 —
배분 6=1+3+2의 조정 근거), LLM 지연, degraded 비율.

### S2 Grounding — probe를 topic_id로

**동작**: probe마다 topic 검색을 **병렬** 호출하고, 응답 트리에서 **`is_match=true` 노드만**
후보로 수집한다(조상 scaffolding을 결과로 취급하지 않는다 — topic-api 자신의 후보 조립도
같은 규칙이다, 분석 §2.2). topic_id 기준 union하되 **어느 probe가 맞췄는지 귀속을 유지**한다.

선별 — **concept_group당 정확히 1 topic**(rev 5, 외부 리뷰 수용):

1. **rule pass**: probe별 매치 수가 캡(20)에 닿았으면 그 probe의 매치는 신뢰 하향 — 단
   **rev 5.6에서 근거가 약해졌다**: 상류가 관련도 순으로 정렬한 뒤 자르므로 캡 도달이 곧
   "상위 20개가 노이즈"를 뜻하지 않는다(`ai`는 560→62로 줄고 인공지능이 16위로 들어온다,
   분석 §2.1 rev 8). 캡 도달은 이제 **"probe가 넓다"**는 신호로만 읽고, 하향 폭은 eval로
   정한다. exact-label 일치(정규화 기준 라벨==probe)는 후보 집합을 exact/non-exact로 나눈다 —
   **약어 probe는 alias exact라서 이 분기를 못 탄다**(위 §S1 매칭 규칙).
2. **그룹당 1 확정**: 각 concept_group에서 topic 하나만 확정한다. **exact 후보 집합이
   non-exact보다 우선하되, exact가 복수면 context로 판별한다(LLM)** — exact 단독 승자
   가드가 아니다: 같은 label의 동음이의 topic이 실존하고(topic-api id 설계의 근거 자체가
   "커피 버번 vs 위스키 버번", 우리 real-anchor 이력도 동음이의 tie로 7/25만 grounding),
   exact라는 이유로 자동 확정하면 그 tie를 그대로 되밟는다.
3. **그룹 내에서 하나를 못 고르면 그 그룹은 `ambiguous`** — 여러 해석을 섞어 랭킹하지
   않는다. 같은 그룹의 복수 topic을 유지하는 fallback은 두지 않는다(부모+자식을 함께
   확정하면 부모 rollup이 자식 보유자를 이미 접어 올린 위에 자식 leaf가 또 잡아 **같은
   근거를 이중 보상**한다 — 이 규칙 하나가 조상 판별 로직 자체를 불필요하게 만든다.
   검색 트리의 중첩은 관계의 증거일 뿐, depth 접힘·다중 부모 때문에 비중첩이 무관계의
   증거가 아니므로 트리로 조상을 판별하려 해서는 안 된다 — 분석 §2.2 rev 5.1).
4. 확정 topic 수 = 살아남은 그룹 수(≤3).
   (`열린 결정` ⑥: 2의 context 판별 LLM을 A단계 초기부터 켤지 — ambiguous 비율 측정 후.)

**topic-api 호출**: `GET /api/internal/svc/topic/search/topics?q={probe}&limit=20` × probe 수.
짧은 TTL 캐시(키 = normalize(probe), TTL은 그들 배포 주기보다 짧게 — 분석 §13-8,
`열린 결정` ⑦).

**산출물**: `GroundingResult { topics: [{topic_id, labels(3언어 맵), matched_probes[],
exact_label: bool}], outcome: grounded | failed | ambiguous | unavailable }`
— outcome 4종은 C4 실패 계약을 승계한다.

**실패 — expansion 상태와 결합해 귀속**(rev 5): ⑴ expansion 정상 완료 + 전 probe 0건 →
`failed` → **422**, 사유 코드 `grounding_failed`(rev 5.5에서 축소: substring 검색과 유한한
확장이 증명하는 것은 "유효 probe로 grounding하지 못했다"까지다 — "카탈로그에 그 topic이
없다"는 주장하지 않는다).
⑵ expansion degraded(LLM 실패) 상태에서 fallback 0건 또는 유효 probe 0개 → `unavailable`
→ **503**(판단에 도달하지 못함 — 422로 내면 호출자 탓 오귀속). ⑶ 모든 그룹이 ambiguous →
`ambiguous` → 422(구분 코드).
topic-api 5xx/timeout → `unavailable` → **503**.

**계측**: probe 0건율(= 카탈로그 커버리지 지표, 분석 §12.3), 후보 수→확정 수, exact-label
비율, unmatched probe의 **digest·길이·언어·귀속**(원문은 남기지 않는다 — rev 5.7 정정).
probe는 topic/context 파생이라 관심사·개인정보가 실릴 수 있고, 일반 로그에 예외를 두면 그
예외가 규칙을 먹는다. 원문이 카탈로그 개선(seed 요청 채널, 분석 §8.3-B)에 정말 필요해지면
**접근제어·보존기간·샘플링·기본 OFF를 가진 별도 measurement sink**로 분리한다.

### S3 Retrieval — topic_id별 후보 유저 수집

**동작**: 확정 topic마다 유저 랭킹을 **병렬** 호출한다. **항상 `limit=100`**(컷 한계 (a)안 —
분석 §9: 컷은 그들 score로 일어나고 페이징이 없으므로, 최대로 받아 우리 층의 재량을 확보한다.
만료 조건 계측 동봉). **`visibility=public` 단독** — rev 5.6: 상류에 friends 지원이 예고돼
있으므로(전언 2026-08-25: requester 신원이 실리면 public+friends, 없으면 public 단독 — 분석
§6.1·§11-17) 이 값은 **provider에 하드코딩하지 않고 호출 인자로 둔다.** 지금 보내는 값은 public
하나이고, 아이템 tier 검증도 "public 고정"이 아니라 **"요청한 tier 집합 안"**으로 읽는다.
friends 실사용은 상류 계약 확정 후이며, 그때 **S3 캐시 키에 requester가 들어가야 한다**(같은
topic도 requester마다 다른 랭킹이 되므로 — 현재 키 설계의 전제가 깨진다).

응답에서 보존하는 것(어댑터가 버리지 않는다):

- `items[].user_id`, `score`(그들의 감쇠 합산 총점 — 참고값, 우리 wire에 비노출)
- `items[].matched[]` **트리 원형**: topic·item(descriptions·blocks의 `score_detail` 포함)·
  `distance`(부호 그대로)·`contribution`·children
- 불완전성 플래그: `exhaustive`, `descendants_dropped`, `topics_dropped`

**topic-api 호출**: `GET /api/internal/svc/topic/topics/{topic_id}/users?limit=100&visibility=public`
× 확정 topic 수(≤3). (id 리스트 라우트는 **A단계에서 쓰지 않기로 재평가** — 분석 §11-16
rev 6: 다중 id 병합은 그들 score를 cross-topic 가중에 재유입시키고, 병합 후 top-100 컷이라
per-topic 100×N보다 후보 풀이 좁으며, rollup 경로를 강제한다. per-topic fan-out + S4 RRF가
의미·후보 풀·비용·exhaustive 전부에서 우월. 재검토 조건은 분석 §11-16.)

**산출물**: `TopicCandidates { topic_id, users: [{...위 보존 필드..., deep_holdings_observed}],
flags: {exhaustive, descendants_dropped, topics_dropped} }`
— `deep_holdings_observed` = **그 유저의** matched 트리에 `distance > 0` 존재(rev 5.7: topic
단위 bool에서 **유저 단위**로 내렸다. 값이 원래 유저의 트리에서 계산되고, topic 단위 bool은
유저 단위 값의 `any()`로 언제든 얻지만 역은 불가능하다. 아래 "비율" 계측은 두 단위 모두에서
정의되므로 세밀한 쪽에 둔다). 어느 단위에서 읽어도 **rollup 여부의 충분조건일 뿐
필요조건이 아니다**(rollup을 탔어도 root topic만 보유한 유저들이면 전부 distance 0,
빈 결과에서는 판별 불가) — 그래서 "was_rollup"이라 부르지 않는다. 정확한 경로 계측이
필요해지면 topic-api에 `strategy` 응답 필드를 요청한다(분석 §11-19, 낮음). 분기용이 아니라
계측·비용 귀속용.

**실패 — 초기엔 fail-closed**(rev 5, 외부 리뷰 수용 — `열린 결정` ① 해소):

- **404**(캐시된 id가 배포 사이 카탈로그에서 소멸 — merge는 resolve가 승계 topic으로
  따라가므로 드묾, drop/비활성이 남는 경우): **카탈로그 시점이 바뀌었다는 신호**로 다룬다
  (rev 5.5에서 범위 명확화 — key 하나만 갈아끼우면 서로 다른 카탈로그 시점의 결과가 한
  응답에 섞인다). 관련 캐시를 무효화하고 **S2 전체를 재실행**한 뒤, 이미 받아 둔 S3 결과를
  **전부 버리고 S3 전체를 1회 재실행**한다. 재실행은 요청당 1회 — 그 뒤에도 실패하면
  아래 규칙.
- **확정 topic 중 하나라도 최종 실패**(5xx/timeout, 재grounding 후 404) → **503.**
  topic 하나가 빠진 RRF는 "완전한 결과의 품질 저하"가 아니라 **다른 랭킹**이다. 조용히
  topic을 버리면 전부 소멸 시 200+empty로 "공개 보유자 없음" 오귀속까지 일어난다.
  부분 성공("성공분 + degraded 표시")은 concept-group 의미와 bourbon-agent의 degraded
  wire가 정해진 뒤 재개방할 계약으로 미룬다.
- **불완전성 플래그도 같은 규칙이다**(rev 5.5 — 외부 리뷰 3차 수용, 분석 §10-7의 "품질
  저하 취급"을 초기 정책에서 뒤집음): `exhaustive=false`의 실제 의미는 "원래 결과에
  들어가야 할 유저가 꼬리에서 빠졌을 수 있음"(그쪽 소스 주석, 검증됨)이고, rank 기반
  RRF에서 이것도 정확히 **다른 랭킹**이다. `exhaustive=false` 또는
  `truncated_descendants > 0` → **503**. 단일 id 질의라 `unranked_topics`는 계약상 0 —
  0이 아니면 계약 위반으로 역시 503. 채널 전체 소실보다 심각도는 낮고(꼬리 불확실성)
  현 카탈로그 규모에서 드물 것이므로 초기 비용은 작다. 부분 결과 허용은 위와 같은
  명시적 degraded wire 계약에 묶어 재개방한다 — **decision log에만 남기고 200을 주는
  것은 정직한 성공이 아니다.**

**계측**: "grounded인데 공개 보유자 0" 비율(= 공개 밀도 지표), 플래그 3종 분포, topic당
반환 유저 수 분포(100 근접 = 컷 경계 접근 — (a)안 만료 감시), `deep_holdings_observed` 비율
(rev 5.5 정정 — "rollup 비율"은 바로 위에서 측정 불가로 결론냈다. 정확한 경로 계측은 §11-19).

### S4 Merge & Filter — owner 단위 병합

**동작**:

1. **RRF 병합 — 독립 concept group 간에만**: 그룹당 topic이 1이므로(S2) 그룹별 순위를
   `Σ 1/(k + rank_g(u))`(k는 `열린 결정` ③, 표준 60 제안)로 owner 단위 융합. topic-api의
   `score` 절대값을 섞지 않고 **순위만** 쓴다 — 점수 의미(관심 편향, 분석 §4)와 topic 간
   스케일 차이를 우리가 재해석하지 않기 위해서다. S2의 그룹당-1 규칙이 지켜져야 이 합산이
   "여러 **독립** 관심 축에 걸린 owner가 위로 온다"는 의미를 가진다 — 같은 개념의
   broad+narrow를 둘 다 확정하면 이 단계가 같은 근거를 이중 보상하게 된다(S2-3).
2. **group contribution 병합**: owner별로 topic마다 {topic_id, contribution, distance,
   score_detail?, descriptions?}를 모은다 — S6의 재료. `contribution`은 topic-api의 값이라
   구현에서는 `ranking_contribution`으로 옮긴다(우리 RRF 기여인 `rrf_share`와 한 타입 안에서
   섞이지 않게 — 어댑터가 외부 이름을 내부 의미로 번역한다).
2-1. **stub 방어 필터**(rev 5, 임시 방어): 대표 매치 item의 `created_at`/`updated_at`이
   null이면 그 후보-topic 쌍을 버린다. 세 writer 전부가 timestamps를 심으므로(검증됨)
   null은 인덱스 유래 stub(= 철회 직후 stale 행)의 강한 신호다. **계약이 아니라
   휴리스틱이다** — 모델은 nullable을 허용하므로: 보안 보장은 topic-api의 leaf 수정
   (분석 §11-4 블로커)이고, 이 필터는 그때까지의 fail-closed 방어이며, 정상 legacy
   item의 오탈락 가능성이 있어 **탈락 건수를 별도 telemetry로 센다.**
3. **exclusion — 집합 인터페이스로 설계**(협의 2026-08-24 반영): 제외는 단일 id가 아니라
   `excluded: set[UUID]`로 받는다. 지금 채워지는 것은 `{requester_user_id}` 하나지만,
   in-room 제외가 defer에서 풀려 bourbon-agent가 `room_members`를 보내게 되면 **같은
   집합에 합류**시키는 것으로 끝난다 — 새 단계·새 분기 없이. **서버측 `exclude_user_ids`
   요청은 철회**(2026-08-24 결정, 분석 §11-5 철회): fan-out 100 대비 최종 max_results 3이라
   cap 손실 논거가 소멸했고, 제외 목록은 countable이라 후처리 오버헤드가 무시 가능하다.
   제외는 전적으로 이 단계(우리 층)의 일이다. **만료 조건**(rev 5): 이 결정은 제외
   집합이 fan-out(100×그룹 수) 대비 무시 가능한 크기일 때 유효하다 — room_members가 커지
   거나 real eligibility가 활성화되어 top-100이 대량 소모되기 시작하면(계측: 제외·필터
   탈락 비율) overfetch 또는 서버측 필터를 재논의한다. eligibility 활성화 gate의 선행
   조건으로 이 재논의를 건다.
4. **eligibility**: `EligibilityPolicy.is_eligible`(현 AllowAll stub 유지, Q12) — S4가 순수
   함수라 **동기 술어**다(rev 5.7 정정: rev 5.6까지의 `EligibilityProvider.check`는 async
   provider 모양이어서 순수 함수 안에서 호출할 수 없었다. 실제 eligibility 원천이 생기면
   조회는 조립 함수가 비동기로 하고 그 결과를 이 정책에 넘긴다 — S4를 async로 바꾸지 않는다).

**topic-api 호출**: 없음.

**산출물**: `CandidatePool { candidates: [{user_id, rrf_score, group_contributions: [...]}] }`
(rev 5.7 개명: `rrf_rank` → `rrf_score` — 이 값은 순위가 아니라 `Σ 1/(k+rank+1)` **합**이고,
S5의 1키가 그것을 내림차순으로 읽는다. §S5·§9의 금지는 scalar의 **노출**이지 내부 존재가
아니다. `evidences` → `group_contributions` — 영어로 evidence는 불가산이고, 이 항목은
"한 그룹이 이 후보 점수에 기여한 내용"이라 contribution이 타입 전체를 더 잘 말한다) —
`degraded` 필드는 rev 5.5에서 **삭제**: S3의 부분 실패·불완전 플래그가 전부 503이 된 뒤로는
도달 불가능한 값이다. 품질 신호는 decision log가 소유하고, 필드는 degraded wire 재개방
결정과 함께 재정의한다.

**실패**: 병합 후 0명 → **200 + empty**("topic은 있으나 공개 보유자 없음" — §4. cold-start의
정상 경로다, 분석 §6.4).

**계측**: 병합 전→후 후보 수, self-exclusion 제거 수, 다중 topic 매칭 owner 비율.

### S5 Ordering — 정렬과 tiebreak

**동작**: lexicographic 정렬 키(분석 §9의 ordering 계약 재해석):

```
gate(현 A단계: privacy=public tier 소비 + S4 stub 방어 — §11-4 해소 전에는 "구조
     보장"이 아니다(rev 5.5, §1의 약화 서술과 동기화), maturity=§11-6 대기로 비활성)
  → 1키: 정렬 전략 슬롯 (기본 전략 = RRF 점수 `Σ 1/(k+rank+1)` 내림차순)
  → 2키: 즐겨찾기 tiebreak (승계 — gate 우회 금지, 동순위에서만. **dormant**: 공급처가
        아직 없다 — §1)
  → 3키: user_id bytes (결정적 — topic-api와 같은 규율)
```

**전략 슬롯**: expertise ordering 키(facets 기반)는 **facets 계약 확정(분석 §11-18)이 선행
조건**이므로 지금은 식을 잠그지 않는다. 슬롯의 계약만 잠근다 — 입력은 S4의 group
contribution(원형 score_detail 포함), 출력은 전순서(total order), **facet 필드 이름에 하드바인딩 금지**(모르는
facet 무시, 기대 facet 부재는 null 처우 규칙으로 — 분석 §13-3). 기본 전략(RRF)은 facets를
전혀 읽지 않으므로 dummy 기간에도 안전하다.

**산출물**: `OrderedCandidates` (상위 `max_results`개로 절단).

**계측**: 전략 교체 시 A/B 근거용 — 기본 전략과 후보 전략의 순위 불일치도(단, **실데이터
주입 후에만 의미** — 분석 §12.3 주의).

### S6 Assembly — 응답 조립

**동작**:

0. **owner → agent id 변환**(rev 5 · rev 5.2에서 고정 계약으로 명문화): topic-api가 주는
   것은 user_id(=owner)이고 bourbon-agent가 기대하는 `RecommendedAgent.id`는 agent ID다.
   변환 규칙은 **bourbon-api가 지정한 고정(fixed) 계약**이며, 기존 memory-api 체인 버전도
   같은 방식으로 구현했다. 정의처 = `bourbon_api/personal_agents/__init__.py`:
   - `AGENT_NAMESPACE = uuid5(NAMESPACE_DNS, "agent.bourbon.xinobi.net")`
     = `43d67b39-e156-5cfe-ba68-55c0f82fe30b`
   - `personal_agent_id(user_id) = uuid5(AGENT_NAMESPACE, f"personal_agent:{user_id}")`
   - known vector: `00000000-0000-0000-0000-000000000001` →
     `2d4342c6-0ca2-5ef3-b5e4-5c6aaeb6d5e3`

   2026-08-24 세 repo에서 동일 공식 재검증(검증됨) — bourbon-api 정의처 · bourbon-agent
   `utils/ids.py` · 우리 `discovery/providers/identity_uuid5.py`(consumer-side known-vector
   pin 테스트 = `tests/providers/test_identity_uuid5.py`). bourbon-api docstring이
   "deliberately stage-independent"를 선언하고 값이 이미 `Agent.id` DB PK로 적재돼 있어
   사실상 불변이다. 구 레지스터 B1(producer-side pin 요청)은 **발신하지 않기로 결정**
   (2026-08-24, 오너 확인) — 이 명문화로 갈음. 경위는
   `archive/bourbon_api_discovery_open_requests.md`.
   owner_id는 내부(제외·hydration·decision log)에 유지하고 wire에는 agent ID만 나간다.
   남는 seam은 변환이 아니라 **"그 agent가 실제 존재·활성인가"의 존재 확인**이며 hydration
   경로(§9-⑨)와 같은 협의 묶음이다.
1. **matched_topics 축약**(분석 §13-2의 답): owner별 **대표 topic = 최종 RRF 합에 가장
   크게 기여한 독립 concept group의 topic**(= reciprocal-rank 기여 최대 — 순위 기반이라
   topic 간 비교 가능). raw `contribution`은 topic 간 선택에 쓰지 않고 **그 topic 내부의
   점수 설명 표시에만** 쓴다 — "topic 간 score 스케일을 비교하지 않는다"는 RRF 근거와
   일관되게. 대표 외 그룹은 개수와 라벨만 요약. 계층 문맥은 matched 트리의 `distance`로
   복원한다 — 노드 위치가 아니라(분석 §2.2 rev 5.1: depth 2는 조상 사슬만 접는다).
2. **라벨 언어**: `lang` 필드는 wire에서 빠졌다(§2). matched_topics에 **ko·en 라벨을
   병기**해 보내고, 최종 발화 언어는 bourbon-agent 모델이 대화 언어로 고른다 — 유저가
   프로필 화면에서 보는 라벨(topic-api의 pick 규칙)과 갈라지지 않도록 라벨 원문은
   topic-api의 것을 그대로 쓴다(축 이전의 근거 1).
3. **signals는 wire가 아니다**(rev 5 정정 — rev 1이 wire 정의에 signals를 실어 자기모순).
   플래그·deep_holdings_observed·degraded는 **decision log 전용** 내부 신호다. reason
   generator는 OFF 유지(기존).
4. **응답 wire — bourbon-agent 모델로의 변환표**(rev 5): 후보별로
   `id` = agent ID(위 0의 uuid5 변환) · `expertise` = 대표+요약 topic 라벨(ko·en) ·
   `match_reason` 재료 = 대표 topic·기여 요지. `name`·`description`은 hydration 결정(§9-⑨ — **S6 선행 블로커**: 결정 전에는 strict wire를 채울 수 없어 S6 구현·통합 테스트 불가)
   에 따름 — 단 그들 strict 모델의 `description: str`(non-nullable)은 "현재 항상 NULL"인
   데이터 현실과 충돌하므로 어느 경로든 그쪽 모델이 한 번 움직여야 한다(nullable 또는
   빈 문자열 관례). **scalar 점수 비노출**(순위가 곧 응답 순서).

**산출물**: `RecommendResponse`.

**계측**: 분석 §12.3의 5종을 이 단계에서 최종 집계·로깅.

---

## §4 실패 의미 3분기 — 판정 지점 고정

분석 §10-3·§13-4의 답. topic-api는 "매칭 0건"과 "보유자 0명"을 모두 200+빈 배열로 답하므로
**구분은 우리 단계가 만든다**:

| 상황 | 판정 단계 | wire |
|---|---|---|
| expansion **정상** + 전 probe 0건 (카탈로그에 topic 없음) | S2 (`failed`) | **422** |
| expansion **degraded** + fallback 0건/유효 probe 0개 | S1→S2 (`unavailable`) | **503** (422 금지 — 판단 미도달) |
| 모든 concept group이 판별 불가 | S2 (`ambiguous`) | **422** (구분 코드) |
| topic 있으나 공개 보유자 0 / 필터 후 0 | S4 | **200 + empty** |
| topic-api 불능 (5xx/timeout) | S2/S3 (`unavailable`) | **503** |
| S3에서 확정 topic 일부 실패 (404 재grounding 후 포함) | S3 | **503** (fail-closed — 부분 RRF는 다른 랭킹) |

오귀속 금지의 축: **"카탈로그에 없다"고 말할 자격은 expansion이 정상 완료됐을 때만
생긴다**(C4 규율 — 판단에 도달했는가). 어댑터 파싱 실패는 계약 위반 로깅 + 503 — 422로
위장하지 않는다.

---

## §5 산출물 요약

| 단계 | 산출물 | 소비자 |
|---|---|---|
| S1 | `ExpansionResult` (concept groups ⊃ probes + 귀속) | S2, 계측 |
| S2 | `GroundingResult` (topic 1~3 + outcome) | S3, §4 판정, 계측 |
| S3 | `TopicCandidates[]` (유저+matched 트리 원형+플래그) | S4, 계측 |
| S4 | `CandidatePool` (RRF 점수 + group contribution 병합) | S5 |
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

> **2026-08-24 재해석 (rev 5.3)**: 구현은 `project-template-python`에서 **신규 시작**한다
> (오너 결정 — `serving_surface_design.md` §1-4). 아래 표의 "유지"는 "신규 구현으로 포팅",
> "삭제"는 "포팅하지 않음"으로 읽는다 — 신규 구현에는 삭제 패스가 없다.

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

포팅의 실행 순서는 신규 구현의 계획에서 정한다(그릇 결정 = `serving_surface_design.md` §7-③).

---

## §8 분석 §13 질문과의 대응

| §13 질문 | 이 문서의 답 |
|---|---|
| 1 호출 형태·컴포넌트 소유 | §0·§3·§7 |
| 2 병합 규칙·대표 topic | S4 RRF(독립 그룹 간, 순위만) · S6 대표=RRF 기여 최대 그룹(contribution은 표시 전용) |
| 3 ordering 키 식 | **부분** — 슬롯 계약만(S5). 식은 §11-18 확정 후 |
| 4 실패 3분기 판정 지점 | §4 — expansion 상태와 결합(정상+0건만 422, degraded+0건은 503), S3는 fail-closed |
| 5 eligibility 결합 지점 | S4 사후 필터 — exclusion과 함께 우리 후처리로 확정(분석 §11-5 철회). 단 만료 조건 있음(S4 — eligibility 활성화 gate에 overfetch/서버측 재논의 선행) |
| 6 rerank 진입 조건 | **미정** — C단계 dormant 슬롯만 (§9-⑥와 별개) |
| 7 어댑터 경계 | §6 |
| 8 캐시 | §6 — /search/topics만, 짧은 TTL |
| 9 rollup 수용 | S3 — 그대로 수용. `deep_holdings_observed`는 충분조건 계측(정확한 경로는 §11-19 strategy 필드 요청 후) |
| 10 cold-start UX | **부분** — 200+empty의 wire는 정직한 빈 배열 + 사유 코드. tool 발화·카드 hydration은 bourbon-agent 협의(§9-⑨) |

---

## §9 열린 결정 (리뷰 안건)

1. ~~S3 부분 실패 규칙~~ — **rev 5에서 해소: 초기 fail-closed 확정**(확정 topic 하나라도
   실패 → 503). 부분 성공은 degraded wire·concept-group 의미가 자리잡은 뒤 재개방할 계약.
2. **probe 수 상한(6)·grounding limit(20)·확정 topic 수(1~3)** — 기본값 제안. 측정 후 조정.
3. **RRF k=60** — 표준값 제안.
4. **matched_topics wire 모양** — distance 부호를 그대로 노출할지, 우리 wire로 단순화
   (예: 대표 topic + "하위 topic n개 포함")할지.
5. **expansion LLM 모델·예산** — 기존 proxy 경유 flash-lite 계열 제안 (~500–1000 input tokens).
6. **S2 LLM rerank를 A단계 초기부터 켤지** — 대안: exact-label rule만으로 시작하고 ambiguous
   비율을 측정한 뒤 켠다. (판정층 §13-6과는 별개 — 이것은 topic 선별, 그것은 후보 재정렬.)
7. **/search/topics 캐시 TTL** — 제안 5분 (그들 배포 주기 대비 충분히 짧음).
8. **200+empty의 사유 코드 체계** — "no_public_holders" / "degraded" 구분을 wire에 실을지.
11. **요청 wire 길이 상한 값** (rev 5) — `topic` ≤200자·`context` ≤2,000자 제안. probe
   ≤100자는 topic-api `NameQuery`와 동기라 제안이 아니라 제약.
9. **응답 카드 hydration 책임** (rev 3 협의 → **rev 5.5에서 S6 선행 블로커로 승격**) —
   bourbon-agent strict wire가 `name`·`description`을 필수로 요구해(§2), 결정 전에는 S6
   구현·통합 테스트가 불가능하다. name=owner 이름·description=personal agent 현재 NULL.
   옵션: (a) 우리가 채움 → bourbon-api 직접 호출 의존성 신설 — **배제 권고**,
   **(b) bourbon-agent가 agent ID로 hydration + 우리 wire 축소 — 권고**, (c) 그쪽 wire
   nullable화 — 차선. `description=""` 채우기는 가짜 계약이라 금지. **bourbon-agent 오너와
   협의해 코드 골격 전에 확정할 것.** description이 "추천 판단 입력"이 될 가능성(오너
   언급)은 열어 둔다.
10. **probe 언어 배분(원문1+en3+ko2)** (rev 2) — 실측 12쌍 기준 제안값. S1 계측(언어별 히트
   기여)으로 조정.

---

## §10 구조 원칙 — 파이프라인은 조립, 단계는 부품 (rev 5.4)

이 문서의 S1–S6은 **현재 목표하는 추천 형태 하나**의 파이프라인이다. 새로운 추천 형태
(로드맵상 후보: for/against, push 모드, orthogonal 서빙)가 들어오면 다른 파이프라인을 탈 수
있고, 그때 단계 일부는 공유될 것이다. 아직 어느 것도 결정되지 않았으므로, 신규 구현
(`bourbon-agent-discovery-api`)은 **그 가능성이 싸게 열리는 구조까지만** 지금 만들고
그 이상의 추상화는 만들지 않는다.

**규칙 (결정):**

1. **단계 = typed 입출력 부품, 외부 의존은 주입된 port로.** §5의 단계별 산출물 타입이 곧
   모듈 경계다 — 단계끼리 내부를 import하지 않고 산출물 타입으로만 대화한다. S1–S3은
   LLM·HTTP를 호출하므로 "순수 부품"이 아니다(rev 5.5 정정) — 이들은 **typed component
   with injected ports**이고, **순수성은 선별·병합·정렬 함수에만 요구**한다(S2 선별 rule
   pass·S4 RRF 병합·S5 정렬 키 — 이쪽이 단위 테스트의 본체다).
2. **파이프라인 = 명시적 조립 함수 하나.** 흐름 제어(재grounding 1회, fail-closed 분기,
   §4 귀속 판정)는 전부 조립 함수에 두고 단계 안에 흩어놓지 않는다. 새 추천 형태 =
   `pipelines/`에 조립 함수 하나 추가.
3. **wire 계약은 파이프라인 소속, HTTP 표현은 api/ 소속**(rev 5.5 명확화). 파이프라인은
   transport 무관 command/result를 소유하고, 실제 Pydantic HTTP wire 모델과 wire ↔ domain
   변환은 `api/`가 갖는다. 단계 산출물 타입(`domain/`)과는 분리 — 새 파이프라인이 다른
   wire를 가져도 부품이 흔들리지 않는다.
4. **배선은 composition root에서만**(기존 phase5 규율 승계). provider 주입도 파이프라인
   단위로 한다.
5. **decision log·계측은 단계 키로** 남긴다 — 새 파이프라인이 관측을 공짜로 얻는다.

```
agent_discovery/
  domain/          # 단계 공유 타입 (§5 산출물 — transport 무관)
  stages/          # 부품: expansion, grounding, retrieval, merge, ranking, assembly
  pipelines/       # 조립: topic_recommend.py (= 이 문서의 S1–S6 배선).
                   # transport 무관 command/result 소유
  providers/       # 주입되는 port: topic-api client, LLM 등 외부 의존
api/               # Pydantic HTTP wire 모델 + wire ↔ domain 변환만 —
                   # 단계는 FastAPI를 모른다(기존 규율 승계)
```

**안 하는 것 (anti-goal, 결정):** pipeline registry · 추상 `Pipeline` base class · 추천
형태에 대한 strategy dispatch · wire의 `pipeline_id`/`recommendation_type` 필드 · config로
단계 순서를 조립하는 DAG. 두 번째 파이프라인이 실물로 없을 때 만든 추상화는 변주 축을
틀리게 찍는다("예약 hook은 같은 질문이 유지될 때만 additive" — stance normalizer를 구현
후 제거한 전례).

**재검토 조건:** 이 절의 결정은 "두 번째 파이프라인이 아직 없다"는 전제 위에서만 유효하다.
두 번째 추천 형태가 **제품으로 확정되는 시점**에 이 절을 다시 열어, 실물 두 개를 놓고
공유 부품 목록과 분기 지점을 다시 긋는다. 그 전에 "미래 대비"를 이유로 한 선제 추상화는
이 절이 거절 근거다.

## 변경 이력

- **2026-08-25 rev 5.7** — **구현 설계안(코드 repo `tasks/todo.md` rev 10)의 이름 감사 역반영.**
  설계 판단은 하나도 바꾸지 않았고, 이름과 한 값의 **소속 단위**만 고쳤다. ⑴ **§S2 계측 — unmatched
  probe의 원문 기록을 폐기**하고 digest·길이·언어·귀속만 남긴다. 이것은 구현 설계안이 이 문서를
  이기고 있던 유일한 지점이었다(그 문서 §10-7이 "정본을 고쳐야 한다"고 기록해 둔 빚). ⑵ **§S3 산출물
  — `deep_holdings_observed`를 topic 단위에서 유저 단위로** 내렸다(값이 유저의 트리에서 계산되고,
  topic 단위는 `any()`로 파생된다). ⑶ **§S4-2 개명** — `evidence 병합` → `group contribution 병합`,
  `contribution`이 구현에서 `ranking_contribution`이 되는 이유 명시(우리 `rrf_share`와의 혼동 차단).
  ⑷ **§S4 산출물 개명** — `rrf_rank` → `rrf_score`(합이지 순위가 아니다. scalar 금지는 **노출**
  규칙이라 무관), `evidences` → `group_contributions`. ⑸ **§S4-4 개명·정정** —
  `EligibilityProvider.check`(async) → `EligibilityPolicy.is_eligible`(동기 술어). S4를 순수 함수로
  잠근 이 문서가 그 안에서 await할 수 없는 port를 예시하고 있었다. ⑹ §S5 전략 슬롯 입력과 §단계
  산출물 요약표의 같은 어휘 동기화. 구현 쪽 이름 감사의 전체 표와 유지 결정은 `tasks/todo.md`
  rev 9·10 변경 이력에 있다.

- **2026-08-25 rev 5.6** — **상류 검색 전제 동기화**(외부 리뷰 P1-3 수용 — 분석 rev 8과 같은
  브랜치). topic-api `42f59bf`가 `find_by_name`에 관련도 서열을 도입해, 이 문서가 **S1 프롬프트에
  내장하는 매칭 규칙**과 **S2 rule pass의 캡 해석**이 거짓이 됐다. 설계 판단은 바꾸지 않고
  사실만 고쳤다: ⑴ §S1-3 규칙 블록 — latin probe는 substring이 아니라 **단어 시작**이어야 하고
  (`tent` ⊄ `content`), CJK는 substring 유지, 정규화에 NFC 추가, "관련도 순위 없음" → **서열
  있음**(label > alias · exact > 단어시작 > substring, 정렬 후 캡). ⑵ §S2 rule pass — 캡 도달을
  "상위 20개가 노이즈"로 읽던 근거가 약해졌으므로(`ai` 560→62, 인공지능 16위) **"probe가 넓다"
  신호로만** 읽고 하향 폭은 eval로 정하도록 좁힘. 새로 드러난 것: **약어 probe는 alias exact라
  exact-label 분기를 못 탄다** → §S1에 "약어는 풀어서 보낸다"를 명시(R1–R7의 정식 "약어 확장"
  규칙 신설과 약어 fixture eval은 후속). 미변경: R5 길이 가드·R6 공백 변형 금지는 그대로 두되,
  상류가 두 spacing을 모두 시도하게 됐으므로(`red wine` → `Redwine`) **R6는 재검토 대상**으로만
  적어 둔다 — 규칙 완화는 측정 뒤에 결정한다. ⑶ **friends tier 예고**(전언 2026-08-25): 상류가
  friends를 지원할 예정이고 방향은 "requester 신원이 실리면 public+friends, 없으면 public
  단독"이다. 설계 판단은 바꾸지 않되(Alpha는 public 단독) **되돌리기 쉬운 형태**로 고쳤다 —
  §S3의 `visibility=public`을 provider 하드코딩이 아니라 **호출 인자**로 두고, 아이템 tier
  검증을 "요청한 tier 집합 안"으로 읽는다. 함께 기록한 파급: friends가 켜지면 같은 topic도
  requester마다 다른 랭킹이므로 **S3 캐시 키에 requester가 들어가야 한다**(현재 키 전제가 깨짐).
- **2026-08-24 rev 1** — 최초 작성. 입력 = `topic_api_analysis.md` rev 5.1. 큰 그림
  파이프라인(S1–S6)·단계별 topic-api endpoint·산출물·실패 3분기 판정 지점·§13 질문 대응을
  담고, expertise 키 식·friends tier·C단계 rerank는 슬롯으로 비워 둠. 리뷰 대기.
- **2026-08-24 rev 2** — 리뷰 1차 반영. ⑴ **S0를 bourbon-agent의 기왕 계약으로 교체**
  (`topic`/`context`/`max_results=3`/`requester_user_id`/`room_id` — 그쪽 mock client가 지키는
  계약이고 "tool 배선 불변·client만 교체"가 명시 의도). `lang`·`eligibility_context`를
  wire에서 제거. 응답 카드 hydration 간극을 §9-⑨로. ⑵ **topic은 en canonical 기본** —
  실측 근거(en label 100%·alias 77% 라틴·topic-api extractor의 영어 한정 query_phrases).
  ⑶ **S1 재서술**: topic 원문은 항상 probe(origin=verbatim, fallback 분기 통합), 확장 입력 =
  topic+context, **프롬프트에 topic-api의 topic 생성·매핑 방식 설명 블록 내장**(규칙은
  안정적·어휘만 배포 단위 변동이라 정적 프롬프트로 안전), 언어 배분 = en 우선·ko 보조
  (12쌍 실측: 4쌍에서 ko가 en이 놓친 topic을 잡음 — hiking 0 vs 등산 2 등), 상한 6 =
  원문1+en3+ko2. ⑷ S6 라벨은 ko·en 병기로 변경(렌더는 bourbon-agent 모델).
- **2026-08-24 rev 3** — bourbon-agent 오너와의 계약 협의 반영(전언). ⑴ `room_id`의 의도 =
  "방 관련 정보를 더 요청할 수 있는 키". ⑵ **in-room 제외는 defer 합의**(OBT까지 같은 방
  상황 희박) — 단 S4의 제외를 `excluded: set[UUID]` 인터페이스로 설계해, 추후 bourbon-agent가
  `room_members`를 보내면 requester와 같은 집합에 합류시키는 것으로 끝나게 함(서버측
  `exclude_user_ids` 요청과도 같은 모양). ⑶ **카드 hydration은 기획 의존·추후 결정**으로
  확인 — name=owner 이름, description=personal agent 현재 항상 NULL(채워질 수 있음, "추천
  판단에만 필요한 정보"일 가능성 포함). (a) 우리가 채우면 bourbon-api 직접 호출 의존성
  신설 / (b) bourbon-agent가 채움 — 우리 산출물은 양쪽에서 성립하도록 고정(§9-⑨).
- **2026-08-24 rev 4** — exclusion·라우트 결정 2건. ⑴ **`exclude_user_ids` 서버측 요청 철회**
  (사용자 결정): 제외는 S4 우리 후처리로 확정 — fan-out 100·max_results 3이라 cap 손실
  논거 소멸, 제외 목록은 countable. 집합 인터페이스(rev 3)는 그대로. ⑵ **id 리스트 랭킹
  라우트는 A단계 불사용으로 재평가**(분석 §11-16 rev 6과 동기화): 그들 score의 cross-topic
  재유입·병합 후 컷·rollup 경로 강제 — per-topic fan-out + RRF 유지, S3의 "생기면 교체"
  문구 삭제.
- **2026-08-24 rev 5** — 외부 리뷰 2회(P1 5건·P2 6건 + 정밀화 4건) 반영. 핵심 =
  **concept_group을 파이프라인 전체의 명시 계약으로 승격**: S2는 그룹당 정확히 1 topic
  (exact 집합 우선·exact 복수는 context 판별 — 단독 승자 가드 철회, 동음이의 이력 근거),
  못 고르면 ambiguous, 그룹 내 복수 유지 fallback 없음(broad+narrow 이중 보상 차단 —
  조상 판별 로직 자체가 불필요해짐), S4 RRF는 독립 그룹 간만. 그 외: ⑴ 프라이버시 —
  §1에서 "구조 보장" 약화(leaf stub, 분석 §11-4 블로커 승격), S4에 stub 방어 필터
  (timestamps-null 휴리스틱 — 계약 아님·오탈락 telemetry 동반) 신설. ⑵ S6 — owner→agent
  uuid5 변환(양 repo 동일 공식 검증) + 존재 확인 seam, signals를 wire에서 삭제(rev 1
  자기모순 정정), bourbon-agent strict 모델로의 변환표와 description nullable 충돌 명기,
  대표 topic = RRF 기여 최대 그룹(contribution은 표시 전용). ⑶ 귀속 — expansion 상태와
  결합한 3분기(degraded+0건 = 503, 정상+0건만 422), probe 길이 가드(≤100자·R5를 verbatim에도
  적용). ⑷ S3 fail-closed 확정(404는 캐시 무효화+재grounding 1회 후) — 열린 결정 ① 해소.
  ⑸ was_rollup → deep_holdings_observed 개명(충분조건 명기), 즐겨찾기 tiebreak dormant 명기,
  exclusion 후처리 결정에 만료 조건 부착.
- **2026-08-24 rev 5.1** — 지위 갱신(설계 내용 불변). `persona_topic_search_design.md`(rev 14)를
  `archive/`로 보내며 이 문서를 정본으로 승격. 헤더의 입력 표기를 분석 rev 7로 동기화(rev 5와
  같은 커밋 `93e819d`에서 함께 개정된 문서라 내용상 이미 rev 7 기준이었다).
- **2026-08-24 rev 5.5** — 외부 리뷰 3차(P1 4건·P2 6건) 반영. ⑴ **완전성 정책**(P1-1):
  `exhaustive=false`·`truncated_descendants>0`도 503 — 꼬리 소실도 rank 기반 RRF에선 다른
  랭킹이며, decision log에만 남는 degraded 200은 정직한 성공이 아니다(분석 §10-7의 초기
  정책을 뒤집음). 파생: `CandidatePool.degraded` 삭제(도달 불가). ⑵ **hydration을 S6 선행
  블로커로 승격**(P1-3): bourbon-agent strict wire의 name/description 필수 확인 — 권고 (b)
  그쪽 hydration + wire 축소, 차선 (c) nullable화, (a)·`""` 배제. §2의 `id`(owner) 오기를
  agent로 정정. ⑶ **concept group 생성 계약 신설**(P1-4): 그룹=독립 의미 축(언어·광협
  변형은 경계 아님), 그룹을 일급 객체로(ExpansionResult.groups), 구조 검증 4종(중복
  금지·상한 3=②·비어있음 금지), malformed는 통째로 degraded. ⑷ 404 재실행 범위 = S2 전체
  + S3 전체 1회(카탈로그 시점 혼합 금지), 422 사유를 `grounding_failed`로 축소, S5 privacy
  문구를 §1과 동기화(stale), 계측 "rollup 비율"→`deep_holdings_observed` 비율(stale),
  §10을 "typed component with injected ports"로 재서술 + `domain/` 추가 + wire/HTTP 소속
  구분. serving_surface_design.md rev 3(신뢰 경계 threat model)과 동기.
- **2026-08-24 rev 5.4** — §10 신설(구조 원칙): 파이프라인=명시적 조립 함수·단계=typed
  순수 부품·wire는 파이프라인 소속·composition root 배선·단계 키 계측. anti-goal(registry·
  추상 base·wire 형태 필드·config DAG)과 재검토 조건(두 번째 추천 형태의 제품 확정 시)을
  함께 잠금 — 새로운 추천 형태가 다른 파이프라인을 탈 가능성을 싸게 열어두되 프레임워크는
  만들지 않는다.
- **2026-08-24 rev 5.3** — 노출 표면 소유권 분리: internal-only·edge-auth 관례 채택·배포
  델타는 신설 `serving_surface_design.md`로. 구현을 `project-template-python`에서 신규
  시작한다는 오너 결정에 따라 §7 처분표를 "포팅한다/포팅하지 않는다"로 재해석(범위 문구의
  "코드 repo tasks/todo.md" 행선도 이 결정에 종속 — 그릇 결정은 같은 문서 §7-③).
- **2026-08-24 rev 5.2** — S6-0을 **고정 계약 명문화**로 승격: owner→agent uuid5 파생은
  bourbon-api 지정 fixed 계약(namespace 상수값·known vector·세 repo 재검증·우리 쪽 pin
  테스트 경로 명기). 구 레지스터 B1(bourbon-api producer-side pin 요청)은 발신하지 않기로
  결정(오너 확인)하고 레지스터를 `archive/`로 종결 — B2는 호출자가 bourbon-agent로 바뀐
  새 wire 계약(`requester_user_id`)으로 대체됨.
