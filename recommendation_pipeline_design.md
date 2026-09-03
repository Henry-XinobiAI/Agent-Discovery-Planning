# Agent 추천 파이프라인 재설계 — topic-api 소비 기반

> **문서 지위**: 설계 정본 (rev 5.13, 외부 리뷰 5회 반영). **결정은 이 문서가 소유하지 않는다** —
> [`decisions.md`](decisions.md)가 소유하고 여기서는 `Dnn`을 인용한다.
> 입력 = `topic_api_analysis.md` **rev 8**
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
   │  POST /recommend  {topic(en canonical), context, lang, max_results, requester_user_id, room_id}
   ▼
S1 Expansion        topic 원문 = 기본 probe + topic·context 기반 확장 (작은 LLM 1회, R1–R7)
   ▼                산출물: ExpansionResult (concept group이 probe를 소유 — 일급 객체)
S2 Grounding        probe별 GET …/search/topics → is_match 트리 → **concept_group당 정확히
   ▼                1 topic 확정** (못 고르면 ambiguous)
                    산출물: GroundingResult (outcome 4종)
                    [expansion 정상+전체 0건 → 422 / expansion 실패+fallback 0건 → 503]
S3 Candidate        확정 topic을 **라벨별 개별 질의 + 가중합**으로 Gorse에 물어 후보를 만든다(D07)
   ▼                (Gorse 불능 → topic-api 보유자 랭킹으로 fallback, `candidates_fallback` 선언 — D20)
                    산출물: CandidateSet
S4 Merge/Filter     미보유자 필터(복제본 D10·D08) → stub 방어 → exclusion → eligibility
   ▼                산출물: CandidatePool                           [0명 → 200+empty]
S5 Ordering         gate → lexicographic 정렬 키 → 결정적 tiebreak (scalar 노출 없음)
   ▼                산출물: OrderedCandidates — **자르지 않는다**(S6의 백필 재료)
S6 Assembly         최종 N명 hydrate+재확인(topic-api /users/{id}/topics — D11·D21)
   │                → 탈락분 백필 → max_results로 절단 → owner→agent id 변환(uuid5)
   │                산출물: RecommendResponse — matched_topics(라벨·descriptions·relation)
   │                + owner_user_id + match_reason + owner_notes
   │                (signals는 wire가 아니라 decision log)
   │                ※ 아직 없는 것: decision_id(D15·임계경로) · degraded(D20으로 복귀 예정)
   │                  · empty_reason 세 번째 값(D21). 셋 다 bourbon-agent 협의 대상
   ▼
bourbon-agent      [grounding 불능 → 503 / 정직한 empty → 200 + 사유 3종]
```

**골자**: topic-api가 **어휘(카탈로그)**를 소유하고 우리는 그 어휘로 자유 텍스트를 깎는다. 후보
생성은 `D07` 이후 Gorse가, 공개 보유의 복제본은 `D10`으로 우리가 갖는다 — rev 5.13 이전의 "저장소 0의
순수 소비자"는 더 이상 참이 아니다. 우리는 우리는 ⑴ 자유 텍스트를 카탈로그 어휘로 깎는 일(S1–S2),
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
| popularity prior 금지 | S5. **S3에서도 유지된다** — Gorse 라벨별 질의의 원점수는 `매칭 여부 × 1/‖d‖`이고 전역 인기 항이 없다(`gorse.md` §11-2). `?category=` 경로는 인기도 순이라 **쓰지 않는다** |
| 판정 입력 텍스트 전부 비신뢰 | S1·S2의 LLM 프롬프트 (카탈로그 라벨·유저 서술 모두) |
| gate 3종 직교 (maturity / safety / privacy) | privacy는 topic-api 구조가 **대부분** 보장하나 leaf stub 구멍이 남아 있다(분석 §6.3 — §11-4 **블로커** 승격). 근본 수정은 topic-api, 우리는 S4의 stub 방어 필터를 임시 방어로 병행. maturity는 §11-6 대기, safety는 타 팀 |
| best-effort 입력 선언 | 사슬 전체(deferq→extractor→topic-api)가 best-effort — freshness 가정 금지 |
| wire 계약: 응답 파싱은 실효 계약 기준·계약 테스트 payload를 consumer model에서 유도 금지 | §6 어댑터 |

**안 하는 것** (분석 §8.2·§8.3): **카탈로그 어휘의 두 번째 원본을 만들지 않는다** — topic의 뜻과
계층을 정하는 것은 topic-api이고 우리가 갖는 것은 그 투영이다(`D10`). rev 5.13 이전 이 자리에 있던
"우리 topic 저장소·색인·스트림 없음"은 `D10`으로 뒤집혔다 — 카운트·최근성은 우리 feature이고
(`D13`), 델타가 아니라 전체 집합을 받으므로 한 건 유실이 영구 불일치가 되지 않는다.
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

**삭제**: `need_type`·`proposition`(1차 유형 단일화·stance 폐기). `eligibility_context`는 wire에서
빼고 우리 내부에서 room_id·requester로 구성(Q12 stub 유지).

**되살아난 것 — `lang`**(rev 5.8): rev 5까지의 삭제 근거는 "우리는 **재료**만 보내고 최종 발화는
bourbon-agent 모델이 대화 언어로 렌더한다"였고, 재료(ko·en 라벨 병기)만 보내는 한 그 근거는 지금도
맞다. 바뀐 것은 우리가 보내는 것이다 — S6이 `match_reason` **문장**을 쓰기로 하면(§S6-4 응답 wire
변환표) 문장 생성 자체가 언어 의존이 되고, 그 언어는 요청이 말해 주는 수밖에 없다. 그래서
`lang: "en" | "ko"`, 기본 `en`으로 되살린다. **라벨은 여전히 두 언어를 병기**한다(축소가 아니라
추가다 — 호출자가 자기 모델로 문장을 다시 쓸 때 재료가 그대로 필요하다). 쓸 문장이 없는 언어 값은
파이프라인 전에 422이고, 언어 추가는 템플릿 추가만으로 additive다.

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
topic 라벨 ko·en) + `match_reason` 재료(대표 topic·기여 요지)로 고정해 둔다(rev 5.8: `match_reason`은
재료에서 **문장**까지로 넓어졌다 — §S6-4). `expertise` 재료도 넓어졌다 — rev 5.8에서 각 topic의
카탈로그 `descriptions`, rev 5.11에서 `owner_notes`(같은 절).

**(b)를 실행 가능하게 만드는 값 — `owner_user_id` 노출**(`결정` rev 5.8, 오너 결정 2026-08-27):
(b)는 "agent ID로 hydration"인데 **그 조회 경로가 어느 repo에도 없다**. `agent_id =
uuid5(_AGENT_NAMESPACE, f"personal_agent:{user_id}")`는 단방향이고 bourbon-agent도 같은 **정방향**
함수만 갖는다(`bourbon_agent/utils/ids.py:16-17`, 검증됨). 카드의 `name`은 agent 행이 아니라
**owner의 이름**인데 bourbon-api `agents.name`·`agents.description`은 둘 다 nullable이고 personal
agent는 비어 있는 게 정상이다(`bourbon_api/agents/models.py:27-32`, 검증됨). 즉 agent_id만 받은
쪽은 무엇으로도 사람에 도달할 수 없어서, (b)는 값이 하나 빠진 상태로는 권고가 아니라 막힌 길이었다.
그래서 응답에 `owner_user_id`를 싣는다. **이것은 (c)로의 전환이 아니다** — `name`·`description`은
계속 우리 것이 아니고, 우리가 주는 것은 호출자가 자기 소유 데이터를 찾아갈 수 있는 키까지다.

`비용`(명시): `(id, owner_user_id)` 쌍은 **그 자체로 매핑 테이블**이다 — 한 번 새면 이후 agent_id
하나로 사람을 특정할 수 있는 자료가 남는다. internal prefix는 edge-auth를 건너뛰고 body의
`requester_user_id`는 아무도 검증하지 않는 주장이므로, 지금 이 값의 보호막은 **네트워크 경계
단독**이다(`serving_surface_design.md` §1-3).

`계약` 필드명은 `owner_user_id`(요청 body의 `requester_user_id`와 혼동을 피하고 bourbon-api 어휘와
일치). **nullable로 선언하고 지금은 항상 채운다** — privacy 게이트가 켜지면 어떤 요청자에게는 이
값을 주지 않아야 하고, 그때 호출자 파서를 깨지 않는 유일한 모양이 nullable이다. 그 날의 의미도
정확히 nullable이 말하는 것이다: "누구인지는 항상 알 수 있는 것이 아니다". 이 필드는 privacy
게이트를 켤 때 **첫 재검토 대상**이며, 그 조건을 코드 주석에 남긴다(조건이 문서에만 있으면 조건이
사라져도 아무도 이 필드를 빼지 못한다).

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

### S3 Candidate — 확정 topic으로 후보 만들기

**동작** (`D07`, rev 5.13): 확정 topic들을 **라벨별 개별 질의 + 가중합**으로 Gorse에 묻는다
(`recsys_opensource/gorse.md` §11-2 경로 C). 라벨마다 센티넬 태그를 넣은 질의 item의 이웃을 묻고,
상위 라벨은 **recall 장치**로, 하위 라벨은 **랭킹 가중**으로 쓴다. 호출당 약 1.1 ms이므로 라벨이
열 개가 되어도 문제가 없다.

**이 단계가 topic-api의 컷을 벗어나는 이유가 `D07`의 전부다.** 보유자 랭킹은 그들 score로 상위
100명에서 잘리고 페이징이 없어서, 그 주제를 가장 깊게 아는 사람이 컷 밖에 있으면 어떤 방법으로도
꺼낼 수 없었다.

**Gorse 불능**: topic-api 보유자 랭킹으로 후보를 만들고 `candidates_fallback`을 선언한다(`D20`).
그 경로는 위의 100명 컷을 그대로 물려받으며, **저하 모드로서 받아들인다.**

**미보유자는 S4가 거른다**(`D08`) — Gorse 이웃 결과에는 매칭 0인 후보가 기본으로 섞이고
(`gorse.md` §11-3), 그런 후보에는 붙일 근거 topic이 없어 **응답을 만들 수 없다.** 판정은 Gorse
점수가 아니라 우리 복제본으로 한다(`D10`) — 원점수는 `매칭 여부 × 1/‖d‖`라 임계값이 후보의 보유
폭에 따라 움직인다.

`열린 항목` **PIPE-⑫ 필터의 위치.** S3 끝인가 S4인가. 앞이면 뒤따르는 처리량이 줄고, 뒤면 제외
카운트가 decision log 한 곳에 모인다.

---

**fallback 경로와 S6 hydrate의 tier 규율** (rev 5.6, 두 경로에 그대로 적용): 상류에 friends 지원이 예고돼
있으므로(전언 2026-08-25: requester 신원이 실리면 public+friends, 없으면 public 단독 — 분석
§6.1·§11-17) 이 값은 **provider에 하드코딩하지 않고 호출 인자로 둔다.** 지금 보내는 값은 public
하나이고, 아이템 tier 검증도 "public 고정"이 아니라 **"요청한 tier 집합 안"**으로 읽는다.
friends 실사용은 상류 계약 확정 후이며, 그때 **S3 캐시 키에 requester가 들어가야 한다**(같은
topic도 requester마다 다른 랭킹이 되므로 — 현재 키 설계의 전제가 깨진다). **rev 5.11 — 그 결함의
등급이 올라갔다**: 응답에 보유자가 쓴 문장이 실리므로(`owner_notes`, §S6-5) 같은 캐시 키 버그의
증상이 "틀린 순위"에서 **"friends 전용 문장을 남에게 노출"**로 바뀐다. friends 채택은 상류 지원을
본 뒤 결정하되(오너 결정 2026-08-27), 그 판단에 이 항목이 포함된다.

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
**실패는 `D20`이 소유한다** (rev 5.13). rev 5.5~5.12의 "확정 topic 하나라도 실패하면 503,
불완전성 플래그도 같은 규칙" 규정은 삭제됐다.

★ **그 규정의 근거가 `D07`로 사라졌다.** 근거는 *"잘린 랭킹을 완전한 랭킹과 융합하면 아무도
계산하지 않은 순서가 나온다"*였고, 그것은 **남의 랭킹을 rank 위치로 융합할 때**의 문제다 — 101등인
사람이 *낮은* 것이 아니라 *없는* 것으로 들어오기 때문이다. 라벨별 가중합에는 랭킹 융합이 없다.
라벨 하나가 빠지면 **같은 함수를 더 적은 라벨 위에서 계산한 결과**이고, 그것은 "질문을 더 적게 읽은
순서"이지 망가진 순서가 아니다.

★ **살아남는 것은 오귀속 금지다.** 조회하지 못한 것을 "공개 보유자 없음"으로 답하는 것은 저하가
아니라 **거짓**이고, 그래서 `D21`이 세 번째 사유 코드(`verification_unavailable`)를 둔다.

fallback 경로에서 topic-api의 불완전성 플래그(`exhaustive=false`, `truncated_descendants > 0`)를
읽으면 **그 topic의 기여만 빼고 `grounding_partial`을 선언**한다 — 이미 저하 모드이므로 503으로
격상하지 않는다. `unranked_topics`는 단일 id 질의에서 계약상 0이고, 0이 아니면 계약 위반이므로
**503**이다(저하가 아니라 상류가 약속을 깬 것).

**계측**: "grounded인데 공개 보유자 0" 비율(= 공개 밀도 지표), 플래그 3종 분포, topic당
반환 유저 수 분포(100 근접 = 컷 경계 접근 — (a)안 만료 감시), `deep_holdings_observed` 비율
(rev 5.5 정정 — "rollup 비율"은 바로 위에서 측정 불가로 결론냈다. 정확한 경로 계측은 §11-19).

### S4 Merge & Filter — owner 단위 병합

**동작**:

1. **RRF 병합 — 독립 concept group 간에만**: 그룹당 topic이 1이므로(S2) 그룹별 순위를
   `Σ 1/(k + rank_g(u) + 1)`(rank는 0-based, k는 `열린 결정` ③, 표준 60 제안)로 owner 단위 융합. **rev 5.13 정정** — 이 자리에만 `+1`이 빠져 있었고 §S4 산출물·§S5 정렬 키와 어긋났다. topic-api의
   `score` 절대값을 섞지 않고 **순위만** 쓴다 — 점수 의미(관심 편향, 분석 §4)와 topic 간
   스케일 차이를 우리가 재해석하지 않기 위해서다. S2의 그룹당-1 규칙이 지켜져야 이 합산이
   "여러 **독립** 관심 축에 걸린 owner가 위로 온다"는 의미를 가진다 — 같은 개념의
   broad+narrow를 둘 다 확정하면 이 단계가 같은 근거를 이중 보상하게 된다(S2-3).
2. **group contribution 병합**: owner별로 topic마다 {topic_id, contribution, distance,
   score_detail?, owner_notes}를 모은다 — S6의 재료. 카탈로그 `descriptions`는 여기서 모으지 않는다
   (rev 5.11 정정 — rev 5.8까지 이 목록의 `descriptions?`는 보유자가 쓴 문장과 구분되지 않았다): 그
   값은 **확정 topic**에서 오므로 S6가 grounding 결과에서 직접 읽는다. `contribution`은 topic-api의 값이라
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

**산출물**: `OrderedCandidates` — **절단하지 않는다**(rev 5.13). 절단은 S6이 재확인을 끝낸 뒤에
한다: `D21`이 재확인에 실패한 후보를 빼고 **뒤에서 채우도록** 요구하는데, 여기서 자르면 채울 재료가
없다. rev 5.12까지 이 자리에 있던 `ranked[:max_results]`가 그 재료를 버리고 있었다.

**계측**: 전략 교체 시 A/B 근거용 — 기본 전략과 후보 전략의 순위 불일치도(단, **실데이터
주입 후에만 의미** — 분석 §12.3 주의).

### S6 Assembly — hydrate · 재확인 · 응답 조립

**동작**:

−1. **hydrate + 재확인**(rev 5.13 신설 — `D11`·`D21`): 상위 후보부터 `GET /users/{id}/topics`로
   **그 사람이 지금 무엇을 공개하고 있는지**를 읽는다. 한 호출이 두 가지를 동시에 한다:
   - **복제본이 주지 못하는 값**(`D11`) — `owner_notes`·`relation`·`descriptions`·
     `deep_holdings_observed`·`ranking_contribution`. 앞의 넷은 응답이 주는 **트리**에서 오고
     복제본은 평평한 목록이라 담을 자리가 없다.
   - **차단·삭제·철회의 서빙 시점 재확인**(`inbound_event_contract.md` §4 상단 등급).

   **읽지 못한 후보는 답에서 뺀다**(`D21` — 이것만은 fail-closed다). 빠진 자리는 `OrderedCandidates`의
   뒤에서 채우고, `verification_partial`을 선언한다. **전부 못 읽으면** 200 + empty이며 사유는
   `verification_unavailable`이다 — 조회하지 못한 것을 "공개 보유자 없음"으로 부르지 않는다.

   `열린 항목` **PIPE-⑬ 몇 명을 읽을 것인가.** `max_results`만 읽으면 탈락 시 왕복이 한 번 더 필요하고,
   여유분을 함께 읽으면 버리는 왕복이 생긴다. `D20`의 지연 예산(`decisions.md` §3-C9)이 정해야 한다.

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
   owner_id는 내부(제외·decision log)에 유지한다. **wire에는 agent ID와 함께 `owner_user_id`도
   나간다**(rev 5.8 — §9-⑨의 hydration 결정: agent→owner 역방향 조회 경로가 없어서 (b)가 이 값
   없이는 실행 불가능하다). rev 5.7까지 이 줄은 "wire에는 agent ID만"이었다.
   남는 seam은 변환이 아니라 **"그 agent가 실제 존재·활성인가"의 존재 확인**이며 hydration
   경로(§9-⑨)와 같은 협의 묶음이다.
1. **matched_topics 축약**(분석 §13-2의 답): owner별 **대표 topic = 최종 RRF 합에 가장
   크게 기여한 독립 concept group의 topic**(= reciprocal-rank 기여 최대 — 순위 기반이라
   topic 간 비교 가능). raw `contribution`은 topic 간 선택에 쓰지 않고 **그 topic 내부의
   점수 설명 표시에만** 쓴다 — "topic 간 score 스케일을 비교하지 않는다"는 RRF 근거와
   일관되게. 대표 외 그룹도 rev 5.8부터 라벨·카탈로그 설명·`relation`을 온전히 싣는다(rev 5.11
   정정 — 이 줄에 rev 5.7까지의 "개수와 라벨만 요약"이 남아 있었다). 계층 문맥은 matched 트리의 `distance`로
   복원한다 — 노드 위치가 아니라(분석 §2.2 rev 5.1: depth 2는 조상 사슬만 접는다).
2. **라벨 언어**: matched_topics에 **ko·en 라벨을 병기**해 보내고, 최종 발화 언어는 bourbon-agent
   모델이 대화 언어로 고른다 — 유저가 프로필 화면에서 보는 라벨(topic-api의 pick 규칙)과 갈라지지
   않도록 라벨 원문은 topic-api의 것을 그대로 쓴다(축 이전의 근거 1). 병기는 그대로 두고, 요청의
   `lang`은 **우리가 쓰는 문장(`match_reason`)에만** 적용된다(rev 5.8 — §2 "되살아난 것"). rev 5.7
   까지 이 줄은 "`lang` 필드는 wire에서 빠졌다"였다.
3. **signals는 wire가 아니다**(rev 5 정정 — rev 1이 wire 정의에 signals를 실어 자기모순).
   플래그·deep_holdings_observed·degraded는 **decision log 전용** 내부 신호다. reason
   generator는 OFF 유지(기존).
4. **응답 wire — bourbon-agent 모델로의 변환표**(rev 5, rev 5.8에서 네 값 추가): 후보별로
   `id` = agent ID(위 0의 uuid5 변환) · `owner_user_id` = 그 agent의 owner(**rev 5.8 신규** —
   §9-⑨, hydration 키) · `expertise` = 대표+요약 topic 라벨(ko·en) + **각 topic의 카탈로그
   `descriptions`(ko·en)**(rev 5.8 신규 — 상류가 검색 응답에 이미 같이 주는 값이라 새 호출 0.
   이것은 **주제**의 설명이고 agent 설명이 아니므로 `matched_topics` 안에 둬서 오독을 구조로 막는다)
   + **각 topic의 `owner_notes`**(rev 5.11 신규 — 보유자가 그 주제에 대해 쓴 문장 그대로, 요약 없이
   list. 계약은 §S6-5)
   · **`relation`**(rev 5.8 신규 · rev 5.9에서 `exact`/`descendant` **2값**으로 정정 — §9-④)
   · `match_reason` = **우리가 쓰는 결정적 템플릿 문장**(rev 5.8: 재료만이 아니라 문장까지. 근거는 §2 "되살아난 것" — 문장이 이상하면 relation이나
   대표 topic 선택이 이상한 것이므로 이 문장 자체가 계측이다. LLM 요약 문장은 ⑴ 피추천자 설명이
   실제로 존재하는지의 계측 ⑵ 남이 쓴 텍스트를 요약해 내보내는 것의 privacy 판정 뒤로 미룬다 —
   **rev 5.11 정정**: 미룬 것은 **요약** 경로 하나다. 원문을 그대로 싣는 것은 §S6-5에서 채택했고, 요약이
   아니므로 ⑴은 그 경로에 필요하지 않다).
   `name`·`description`은 계속 **우리 것이 아니다**(§9-⑨ (b)) — 그들 strict 모델의
   `description: str`(non-nullable)은 "현재 항상 NULL"인 데이터 현실과 충돌하므로 어느 경로든 그쪽
   모델이 한 번 움직여야 한다(nullable 또는 빈 문자열 관례). **scalar 점수 비노출**(순위가 곧 응답
   순서).

5. **`owner_notes` — 보유자가 그 주제에 대해 쓴 문장, 그대로**(rev 5.11 신규, 오너 결정 2026-08-27).
   §S6-4의 `match_reason`이 **우리** 문장인 것과 달리 이것은 **그 사람의** 문장이고, 우리는 옮기기만 한다.
   privacy 근거는 **동의의 입자 크기**다: `visibility`는 프로필 전체가 아니라 **그 item(주제별 보유)
   하나**에 붙어 있고(`UserTopicItem`에 `visibility`와 `descriptions`가 같은 객체로 있다), 우리가 요청하는
   tier는 `public`이므로 "공개로 표시된 문장을 공개한다"가 된다.

   ⒜ **각 note는 자기 topic을 갖는다** — `{topic_id, labels(ko·en), text(ko·en)}`. note는 확정 topic이
      아니라 **matched 트리의 노드**에 붙어 있고, `matched_topics[]` 항목의 `topic_id`·`labels`는 **확정
      topic**의 것이다(§S6-1). 둘은 다를 수 있다 — 확정 `커피`, note는 자손 `드립 커피` — 그래서 note를
      항목 라벨 옆에 그냥 놓으면 **자손의 문장이 상위 주제의 것으로 읽힌다.** rev 5.8 ⑵가 배치로 막은
      오독의 같은 변종이고, 같은 방법(구조)으로 막는다. note의 topic이 항목의 topic과 같아도 값은 중복해서
      싣는다 — "비어 있으면 부모와 같다"는 규칙은 읽는 쪽이 틀릴 여지를 남긴다.
   ⒝ **항목당 최대 3개 · 순서는 대표 노드 규칙 재사용 + 결정적 tiebreak** — `ranking_contribution`
      내림차순 → `distance` 오름차순(= S3의 대표 노드 선택 규칙) → **`topic_id`**(rev 5.12 추가). 새 정렬
      규칙을 만들지 않는 것이 요점이지만, **상한이 순서를 wire에서 관측 가능하게 만든다**: 두 키가 완전히
      같은 노드가 넷이면 어느 셋이 나가는지가 상류의 순회 순서로 결정되고, 그건 계약이 아니다(§10 원칙 ·
      구현 repo rev 31의 같은 결함). 세 번째 키는 우리가 읽는 값이라 그 의존을 끊는다. 정확한 계약은
      **"note를 가진 노드만 남긴 뒤 같은 규칙으로 정렬"**이다 — 대표 노드가 note를 안 쓴 경우가 있으므로
      "`owner_notes[0]`은 항상 대표 노드"라고 쓸 수 없다. 상한에 걸려 잘린 수는 계측.
   ⒞ **ko·en 병기** — 라벨과 같은 관례다(§S6-2). `UserTopicItem.descriptions`는 열린 언어 맵이라 **ja 단독
      note가 가능하고 그것은 wire에서 사라진다.** 존재 계측(`holder_description_present`)은 **모든 언어**를
      세므로(그게 "재료가 있는가"의 올바른 정의다) 두 값은 어긋날 수 있다 → **언어 때문에 탈락한 note 수를
      따로 센다.** 그 수가 유의미해지면 그때 고칠 것은 wire 모양이고, 계측이 아니다.
   ⒟ **길이 상한 없음, 원문 그대로**(오너 결정 2026-08-27) — 상류가 이미 짧게 만들어 넣는다는 전제다.
      자르는 것은 남의 문장을 왜곡하는 것이라 상한보다 나쁘다. 다만 **우리 쪽에 강제 장치가 없는 상류
      보장**이므로 길이를 계측한다(문서로 쓴 불변식은 강제가 아니다) — 전제가 깨지면 응답 크기보다 로그가
      먼저 말해야 한다. 최악 크기는 `matched_topics` 3 × note 3 = **9개**다. **계측은 상한 통과분만 본다**
      (rev 5.12 명시): 상한 밖으로 밀린 긴 note는 안 보이므로, 이 값이 정확히 재는 것은 **우리가 싣는
      양**이고 상류 전제는 그것을 통해 간접적으로 감시된다.
   ⒠ **이름** — 형제로 `descriptions`(카탈로그)가 있으므로 **명사를 다르게** 둔다. `owner_descriptions`는
      한 단어 차이라 가드가 약하고, `user_`는 이 wire에서 요청자·owner·agent 셋 다 될 수 있다. `note`는
      "사람이 쓴 산문"이라는 사실을 이름이 말한다.

   ⒡ **철회된 보유의 문장은 나가지 않는다**(rev 5.12 신설 — 구현 자체 리뷰에서 **실제로 샜다**).
      §S4-2-1의 stub 방어는 **대표 노드 하나**의 timestamps만 읽는데 note는 트리 전체에서 오므로, 대표
      노드가 건강하면 **철회된 형제 노드의 문장이 그 건강함에 업혀 나갔다.** 이건 이 값의 privacy 근거가
      자기 축에서 무너지는 것이다 — 동의는 `visibility`가 붙은 **그 보유**의 것이고, timestamps가 사라진
      보유는 상류가 "철회로 남은 행"을 보여주는 방식이다. 비대칭도 나빴다: 대표 노드가 stub이면 S4가 쌍
      전체를 버리므로 **비대표 노드일 때만** 샜다. 그래서 note는 timestamps 없는 노드를 **먼저** 거절한다.
      계측은 **이유별 3종**이 되고(철회·언어·상한) 순서가 있다 — 신뢰할 수 없는 행을 "언어 손실"로 세면
      읽는 사람을 **엉뚱한 것을 넓히도록** 보낸다. 그리고 보유자가 쓴 노드는 **정확히 한 칸**에 들어간다
      (보낸 것 · 철회 · 언어 · 상한): 같은 트리 위의 독립 술어 넷은 한 노드를 두 번 세거나 안 세면서도
      네 숫자가 전부 답처럼 보이게 한다.

   **신뢰 경계**: 이 값은 우리 wire에서 **처음으로 나가는 공격자 제어 자유 텍스트**다 — 그 외에는 우리
   것이거나 큐레이션된 카탈로그 텍스트다. 호출자가 이것을 자기 LLM 대화에 넣으므로 prompt injection
   표면이고, **완화 책임은 bourbon-agent가 진다**(오너 결정 2026-08-27). 우리 몫은 경계를 명시해서 넘기는
   것 하나다: 스키마 필드 설명에 user-authored·untrusted를 적는다. `visibility=public`은 privacy 질문에
   답하지만 이 질문에는 답하지 않는다.

   **원문이 도메인에 들어온다 — 구현 규율의 반전**(코드 repo `tasks/todo.md` §9 25행 "피추천자가 쓴 텍스트는
   도메인에도 들이지 않는다"). 근거 둘 중 "소비자가 없는 원문 필드는 예약 hook"은 소비자가 생겨 소멸하고,
   "제3자 텍스트가 로그·예외·Sentry로 새는 경로"는 **거부 사유에서 방어 요구사항으로 내려온다**: 파싱 실패
   로그의 pydantic `input` · 우리 예외 메시지 · `ErrorResponse` 세 곳에 이 값이 실리지 않는 것이 이 변경의
   실제 분량이다.

   **wire에 내는 것 ≠ repo에 커밋하는 것**(rev 5.9 규율 유지): dev 실캡처 fixture의 보유자 문장은 계속
   placeholder다. 전자는 owner가 public으로 표시한 값을 소비자에게 보내는 것이고, 후자는 git 이력에 영구
   보존하는 것이라 동의 범위가 다르다. 테스트 데이터는 합성 문장을 쓴다.

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
| topic 있으나 공개 보유자 0 / 필터 후 0 | S4 | **200 + empty** (`no_public_holders` / `all_candidates_filtered`) |
| **최종 N명을 하나도 재확인하지 못함** (rev 5.13 · `D21`) | S6 | **200 + empty** (`verification_unavailable` — "없다"가 아니라 "보지 못했다") |
| **grounding 불능** (`/search/topics` 전부 5xx/timeout) | S2 (`unavailable`) | **503** — 물어볼 topic이 없으면 후보를 만들 수 없다 |
| **Gorse 불능** (rev 5.13 · `D20`) | S3 | **200** + `candidates_fallback` — topic-api 보유자 랭킹으로 후보 생성 |
| **확정 topic 일부만 grounding 성공** (rev 5.13 · `D20`) | S2 | **200** + `grounding_partial` — 라벨별 가중합에는 랭킹 융합이 없어 "더 적게 읽은 순서"다 |
| **보유 근거가 랭킹 범위를 벗어남**(item 있는 노드의 distance < 0 — rev 5.9) | provider(client) | **503** (구조적 불변식 위반 · §9-④) |

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
| `GET /api/internal/svc/topic/users/{id}/topics` | **S6** (rev 5.13) | `visibility` | **없음** — 서빙 시점 재확인이 목적이므로 캐시하면 목적이 사라진다(`D21`) |
| `GET /api/internal/svc/topic/topics/{id}/users` | S3 **fallback 전용** | `limit=100`, `visibility` | 없음 (유저 데이터 — 신선도 우선) |

rev 5.13에서 세 번째 행이 **정상 경로에서 빠지고 fallback으로 내려갔다**(`D07`). 두 번째 행이 그
자리를 대신하되 목적이 다르다 — 후보를 **찾는** 읽기가 아니라 최종 N명을 **확인하는** 읽기다.

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
   rev 5.13 정정: 이 중 **그룹 수 ≤ 3은 이미 구조 검증이고 위반하면 fail-closed 저하**다(§S1).
   조정 대상은 나머지 둘이다.
3. **RRF k=60** — 표준값 제안.
4. ~~matched_topics wire 모양~~ — **rev 5.8에서 해소, rev 5.9에서 2값으로 정정**: 정수 `distance`는
   wire에 내지 않고, 그것에서 파생한 **`relation` enum `exact`/`descendant`**(0 / >0)를 응답
   프로젝션에서 만들어 보낸다. 근거는 "카드가 인쇄할 수 있는 값이어야 한다"는 것 — `2`는 topic-api가
   자기 트리에 노드를 놓는 방식이고 호출자가 행동할 수 없다. 어휘는 **우리 것**이다: topic-api에도
   `Relation` enum이 있지만 세 번째 값이 `related`이고 우리 `descendant`와 같은 것이 아니라, 그쪽
   철자에 맞추는 것은 뜻이 아니라 단어를 맞추는 일이 된다(어휘 수렴은 호출자 확인 항목). 이 값은
   **사람별**이다 — 같은 topic이라도 A는 `exact`, B는 `descendant`일 수 있다.

   `검증됨`(2026-08-27, 외부 리뷰 4차 · topic-api `9ee67f3`) **`ancestor`는 이 endpoint에서 생성될 수
   없다.** rev 5.8이 3값으로 쓴 것은 오류였다. 근거 사슬: ⑴ `distances`는
   `graph.descendants(topic_id, …)`로만 만들어져 전부 0 이상(`topic/search/service.py:171-190`)
   ⑵ 유저 항목은 `_ranked_in_subtree`가 `item.topic_id in weights`로 걸러내고 `weights` 키 =
   `distances` 키(`service.py:220`) ⑶ 음수는 `topic_id not in distances`일 때의 `_above(...)`뿐이고
   (`service.py:331`) 그 노드는 item이 없다. 즉 **item을 가진 노드의 distance는 항상 ≥ 0**이고 음수는
   구조 설명 header 전용이다.

   `결정`(rev 5.9) 그래서 ⑴ enum은 2값 ⑵ "더 넓은 주제를 보유한다"는 문장도 삭제 ⑶ **item을 가진 노드가
   음수 distance로 오면 provider가 fail-closed로 거절**한다(`UpstreamContractViolation` → 503). 이것은
   불완전성이 아니라 **구조적 불변식 위반**이다 — 융합·`relation`·우리가 쓰는 문장이 모두 "보유 근거 =
   topic + descendants"를 읽으므로, ancestor 보유를 descendant로 답하는 것은 빠진 이유가 아니라 **틀린
   이유**가 된다. ancestor 보유자까지 추천하려는 제품 요구가 생기면 그것은 enum 문제가 아니라
   **topic-api 랭킹 범위를 넓히는 별도 설계**이고, 그때 이 거절이 그것을 크게 알린다.

   `결정`(rev 5.10, 외부 리뷰 5차) **거절은 두 층이고, 나누는 기준은 귀속이다.** rev 5.9의 ⑶은 상류 경로만
   덮었다 — 우리 코드가 음수 attribution을 만들면 투영이 조용히 `descendant`를 답했다. 그래서: **상류가
   음수 item을 보냄 → provider `UpstreamContractViolation` → 503**(그들의 계약 위반) · **우리가 음수
   attribution을 만듦 → 도메인 타입이 `ValueError` → 500**(우리 결함) · 관계를 명명하는 함수도 단어를
   고르지 않고 거절한다(두 가드 뒤라 도달 불가지만, 도달 불가의 대안이 "안전"이 아니라 "`descendant`를
   답한다"이므로 남긴다). **상류의 값을 나르는 중간 타입(`HoldingEvidence`·`GroupContribution`)에는 넣지
   않는다** — 거기서 거절하면 상류의 계약 위반이 우리 500으로 기록돼 §S1 계측의 귀속 규율(우리 잘못을
   상류 장애로, 또는 그 반대로 세지 않는다)을 어긴다.

   `규율` **상류 fixture는 그 endpoint의 의미 계약이 아니다.** rev 5.8의 오류는 우리 fixture(topic-api의
   `SearchResponse` **컴포넌트 예시**)의 item 노드에 우리가 음수를 심어 만든 테스트에서 나왔다. shape
   검증에는 유효하지만 "그 값이 이 endpoint에서 나온다"의 증거로는 쓸 수 없다. 의미 계약은 **랭킹 코드**나
   **실제 캡처한 응답**에서 읽는다(구현 repo에 dev 실캡처 fixture 추가 — 보유자 2명·item 노드 distance
   `[0, 1]`).
5. **expansion LLM 모델·예산** — 기존 proxy 경유 flash-lite 계열 제안 (~500–1000 input tokens).
6. **S2 LLM rerank를 A단계 초기부터 켤지** — 대안: exact-label rule만으로 시작하고 ambiguous
   비율을 측정한 뒤 켠다. (판정층 §13-6과는 별개 — 이것은 topic 선별, 그것은 후보 재정렬.)
7. **/search/topics 캐시 TTL** — 제안 5분 (그들 배포 주기 대비 충분히 짧음).
8. ~~**200+empty의 사유 코드 체계**~~ — **rev 5.13 해소**: `D20`·`D21`이 세 값으로 확정했다
   (`no_public_holders` / `all_candidates_filtered` / `verification_unavailable`). `degraded`는 별도
   필드로 복귀한다 — rev 5.5가 도달 불가로 지웠고 그 전제가 `D20`으로 사라졌다. **값 추가는
   bourbon-agent 협의 대상**이다(`Literal` strict 파싱). 원래 질문: — "no_public_holders" / "degraded" 구분을 wire에 실을지.
11. **요청 wire 길이 상한 값** (rev 5) — `topic` ≤200자·`context` ≤2,000자 제안. probe
   ≤100자는 topic-api `NameQuery`와 동기라 제안이 아니라 제약.
9. **응답 카드 hydration 책임** (rev 3 협의 → **rev 5.5에서 S6 선행 블로커로 승격**) —
   bourbon-agent strict wire가 `name`·`description`을 필수로 요구해(§2), 결정 전에는 S6
   구현·통합 테스트가 불가능하다. name=owner 이름·description=personal agent 현재 NULL.
   옵션: (a) 우리가 채움 → bourbon-api 직접 호출 의존성 신설 — **배제 권고**,
   **(b) bourbon-agent가 agent ID로 hydration + 우리 wire 축소 — 권고**, (c) 그쪽 wire
   nullable화 — 차선. `description=""` 채우기는 가짜 계약이라 금지. description이 "추천 판단
   입력"이 될 가능성(오너 언급)은 열어 둔다.
   **rev 5.8 부분 해소**: (b)로 가되 (b)가 전제한 agent→owner 조회 경로가 존재하지 않으므로 응답에
   `owner_user_id`를 싣는다(오너 결정 2026-08-27 — 근거·비용·계약은 §2 아래 문단). 남는 열린 항목은
   **그쪽 strict 모델의 `name`·`description`**이다: 우리는 그 두 값을 보내지 않으므로 bourbon-agent가
   nullable화하거나 owner 조회로 채워야 하고, 그건 그쪽 코드의 변경이다.
   **rev 5.11 주의**: `owner_notes`(§S6-5)는 이 간극을 메우지 않는다. 그것은 **주제에 대한** 문장이고
   `description`은 **agent에 대한** 것이라, 카드가 전자를 후자 자리에 넣으면 rev 5.8 ⑵가 구조로 막은
   오독이 호출자 쪽에서 재발한다.
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

**2026-09-03 rev 5.13** — 결정 소유를 [`decisions.md`](decisions.md)로 넘기고, `D07`(Gorse가 후보
소스)·`D10`(공개 보유 복제본)·`D20`·`D21`(실패 규율)을 본문에 반영했다. 뒤집힌 서술은 표시하지 않고
**삭제**했다 — 제자리에 경고만 달아 두는 방식이 `gorse.md` §6-1에서 실제로 오독을 만들었다.

⑴ **S3이 Retrieval에서 Candidate로 바뀌었다**(`D07`). 후보는 Gorse에 라벨별 개별 질의 + 가중합으로
묻고, `/topics/{id}/users`는 **fallback 전용**으로 내려갔다. 이 단계가 존재하는 이유는 그들 랭킹이
상위 100명에서 잘리고 페이징이 없다는 것 — 가장 깊게 아는 사람이 컷 밖이면 꺼낼 방법이 없었다.

⑵ **S3의 fail-closed 규정(rev 5.5~5.12)을 삭제했다**(`D20`). 근거는 *"잘린 랭킹을 완전한 랭킹과
융합하면 아무도 계산하지 않은 순서가 나온다"*였고, 그것은 rank 위치로 융합할 때의 문제다. 라벨별
가중합에는 랭킹 융합이 없어 라벨 하나가 빠지면 **더 적게 읽은 순서**이지 망가진 순서가 아니다.
**오귀속 금지는 그대로 살아남았다** — 보지 못한 것을 "없다"고 하지 않는다.

⑶ **hydrate + 재확인을 S6에 신설했다**(`D11`·`D21`). 복제본이 담지 못하는 다섯 값(`owner_notes`·
`relation`·`descriptions`·`deep_holdings_observed`·`ranking_contribution`)과 차단·삭제·철회의 서빙
시점 재확인이 **같은 호출**에서 온다. 읽지 못한 후보는 빼고 뒤에서 채운다.

⑷ **S5가 절단을 멈췄다.** ⑶의 백필에는 잘라낸 나머지가 필요한데 `ranked[:max_results]`가 그것을
버리고 있었다. 절단은 재확인 뒤 S6이 한다.

⑸ **§1의 "우리 topic 저장소·색인·스트림 없음"을 `D10`으로 대체**했다. 남는 규율은 좁아졌다 —
**카탈로그 어휘의 두 번째 원본을 만들지 않는다.**

⑹ **§4 실패 표를 다시 썼다** — `verification_unavailable`, `candidates_fallback`,
`grounding_partial` 세 줄이 늘고 `S3 부분 실패 → 503` 줄이 빠졌다.

⑺ 부수 정정: §0 요약에 `lang`과 S6의 rev 5.8 값 넷 + `owner_notes`가 빠져 있었다(HOW_TO_READ가
"시간 없으면 §0만 읽어라"로 안내하는 블록이다). §S4-1의 RRF 식에만 `+1`이 없어 §S4 산출물·§S5와
어긋났다. `열린 결정` ⑧을 `D20`·`D21`이 닫았고, ②의 세 값 중 "그룹 수 ≤ 3"은 이미 구조 검증임을
명기했다.

- **2026-08-27 rev 5.12** — **`owner_notes`에 두 가지를 더한다: 철회 방어와 결정적 tiebreak**(구현 자체
  리뷰 · §S6-5 ⒝·⒟·⒡). rev 5.11이 계약을 다 적었다고 생각했지만 둘이 비어 있었고, 첫째는 **실제로 새고
  있었다.**
  ★**기존 방어가 "대표 노드"만 읽는데 새 값이 "트리 전체"에서 오면, 그 방어는 새 값에 대해 없는 것이다.**
  §S4-2-1의 stub 필터는 대표 노드의 timestamps만 보고, note는 트리 전체에서 온다 — 그래서 대표 노드가
  건강하면 **철회된 형제의 문장이 그 건강함에 업혀** wire까지 갔다(재현: contribution 90 살아 있는 노드 +
  50 timestamps-null 노드 → 문장 둘 다 응답). 이 값의 privacy 근거가 **자기 축에서** 무너지는 것이다:
  동의는 `visibility`가 붙은 그 보유의 것이고, timestamps 소실은 상류가 철회를 보여주는 방식이다.
  ★**상한은 순서를 계약으로 만든다.** 두 정렬 키가 완전히 같으면 어느 셋이 나가는지가 **상류의 순회
  순서**로 정해졌다(`['a','b','c','d']`→abc, 역순→dcb). rev 5.11이 "새 정렬 규칙을 만들지 않는다"를
  옳게 지켰지만, 그 규칙이 **1개 선택**에는 충분하고 **N개 중 3개 선택**에는 부족했다 — 세 번째 키(`topic_id`)를
  넣는다.
  둘의 결과로 드롭 계측이 **이유별 3종**(철회·언어·상한)이 되고 **순서**가 생긴다: 신뢰할 수 없는 행을
  언어 손실로 세면 읽는 사람이 wire를 넓히려 든다. 그리고 노드는 **정확히 한 칸**에 들어간다 — 독립 술어
  넷은 한 노드를 두 번 세거나 안 세면서 네 숫자가 전부 답처럼 보이게 한다.
  ⒟에 한계도 명시했다: 길이 계측은 **상한 통과분만** 본다.

- **2026-08-27 rev 5.11** — **보유자가 쓴 문장을 원문 그대로 wire에 싣는다**(`owner_notes`, 오너 결정).
  rev 5.8이 보류한 것은 **LLM 요약 경로**였고, 그 보류가 선택지를 좁게 봤다: 원문 통과는 요약보다 **더**
  안전하다 — 남의 글이 우리 문장으로 바뀌지 않으니 귀속이 흐려지지 않고, 호출·지연·환각이 없고, 보류
  조건 ⑴("요약할 재료가 있는가"의 계측)이 아예 필요 없다. privacy 근거는 **동의의 입자 크기**다:
  `visibility`는 프로필이 아니라 그 주제별 보유 하나에 붙어 있고, 우리는 `public`만 요청한다.
  ★**값을 놓기 전에 "그 값이 무엇에 붙어 있었는지"를 확인한다.** note는 확정 topic이 아니라 matched 트리의
  **노드**에 붙어 있어서, 확정 topic으로 만들어진 `matched_topics[]` 밑에 그냥 넣으면 자손의 문장이 상위
  주제의 것으로 읽힌다. 그래서 note마다 자기 `topic_id`·`labels`를 동봉한다 — rev 5.8 ⑵가 배치로 막은
  오독의 같은 변종을 같은 방법으로 막는 것이다.
  나머지 계약은 §S6-5: 항목당 3개 상한 + **대표 노드 선택 규칙 재사용**(새 정렬 규칙을 만들지 않는다) ·
  ko·en 병기 + **언어 탈락 수 계측**(존재 계측은 모든 언어를 세므로 두 값이 어긋날 수 있다) · **길이 상한
  없음**(상류가 짧게 만든다는 전제 — 강제 장치가 없으니 길이를 계측한다) · 이름은 `owner_notes`(형제
  `descriptions`와 명사를 다르게).
  **책임 두 개를 명시적으로 넘긴다**(오너 결정): prompt injection 완화는 bourbon-agent — 우리 몫은 스키마에
  untrusted를 적는 것 · friends tier 채택은 상류 지원을 본 뒤. 후자에는 **등급 승격**이 딸린다 — S3 캐시 키에
  requester가 없는 기존 결함의 증상이 "틀린 순위"에서 "friends 전용 문장 노출"로 바뀐다(§S3).
  구현 규율로는 코드 repo §9 25행의 반전이고, 실제 분량은 wire 필드가 아니라 **로그·예외·Sentry 세 경로
  방어**다. rev 5.9의 fixture 규율은 유지된다: **wire에 내는 것 ≠ repo에 커밋하는 것.**

- **2026-08-27 rev 5.10** — **음수 distance 거절을 두 층으로 나눈다**(외부 리뷰 5차, P2 1건 수용). rev 5.9의
  "provider가 거절한다"는 **상류 경로에만** 참이었다: 우리 코드가 음수 attribution을 만들면 투영 함수가
  조용히 `descendant`를 답했고, 그것은 이 트랙이 없애려던 바로 그 **틀린 이유**다. 기준은 **귀속**이다 —
  그들의 답변이면 503, 우리가 만든 값이면 500, 그리고 상류의 값을 나르는 중간 타입에는 가드를 넣지 않는다
  (넣으면 그들의 계약 위반이 우리 결함으로 기록된다). 상세는 §9-④의 `결정`(rev 5.10).

- **2026-08-27 rev 5.9** — **`relation`을 2값으로 정정**(외부 리뷰 4차, P2 1건 수용). rev 5.8이 하루도 안
  돼 틀린 것을 고친다: `ancestor`는 `/topics/{id}/users`에서 **생성될 수 없는 값**이었다. topic-api 랭킹은
  보유 근거를 "조회 topic + descendants"로만 만들고(근거 3단계는 §9-④에 `file:line`으로), 음수 distance는
  item이 없는 구조 header 전용이다. 그래서 ⑴ enum 2값 ⑵ ancestor 문장 삭제 ⑶ item 있는 노드가 음수로 오면
  **provider fail-closed 503**(§4 표에 행 추가) — 불완전성이 아니라 구조적 불변식 위반이고, 랭킹 범위를
  넓히려면 그건 별도 설계다.
  ★**상류의 컴포넌트 예시 fixture는 그 endpoint의 의미 계약이 아니다.** rev 5.8의 오류는 우리가 그
  fixture의 item 노드에 음수를 **직접 심어** 만든 테스트에서 나왔다 — shape 검증에는 유효하지만 "이 값이
  실제로 온다"의 증거가 아니다. 의미 계약은 랭킹 코드나 실제 캡처에서 읽는다. 구현 repo에 dev 실캡처를
  fixture로 넣었고(보유자 2명 · item 노드 distance `[0, 1]`), 캡처는 보유자가 쓴 문장만 placeholder로
  치환했다(그 텍스트를 fixture로 커밋하는 것은 같은 유출을 느린 경로로 하는 것이다).

- **2026-08-27 rev 5.8** — **응답 wire를 네 값 넓힌다.** 계기는 dev 배포(2026-08-26) 후 확인된 연동
  블로커다: bourbon-agent의 `RecommendedAgent`가 `name`·`description`을 strict 필수로 요구하는데 우리
  wire는 `{id, matched_topics[]}`뿐이라 호출자가 우리 응답을 자기 모델에 넣는 것 자체가 검증에서
  터졌다. 네 값 중 셋은 **추가**이고 하나는 **잠근 결정의 반전**이다.
  ⑴ **`owner_user_id` 노출**(오너 결정 2026-08-27 — §9-⑨, §S6-0). 이것이 반전이다: rev 5.7까지
  "owner 신원은 wire에 안 나간다"였다. 뒤집은 이유는 §9-⑨의 권고 (b)("bourbon-agent가 agent ID로
  hydration")가 **존재하지 않는 조회 경로를 전제**하고 있었다는 것 — uuid5는 단방향이고 양쪽 repo에
  정방향 함수만 있으며, 카드의 `name`은 agent 행이 아니라 owner의 이름이다. 값이 하나 빠진 (b)는
  권고가 아니라 막힌 길이었다. 비용(`(id, owner_user_id)` 쌍 = 그 자체로 매핑 테이블 · 보호막은 지금
  네트워크 경계 단독)과 계약(nullable · privacy 게이트 켤 때 첫 재검토 대상)을 §9-⑨ 아래에 명문화했다.
  ⑵ **카탈로그 `descriptions`를 `matched_topics` 안으로** — 상류가 검색 응답에 이미 같이 주는 값이라
  새 호출 0. 위치가 계약이다: 주제의 설명이 agent의 설명으로 읽히는 오독을 shape으로 막는다.
  ⑶ **`relation` enum 신설로 §9-④ 해소** — 정수 `distance`는 계속 wire 밖이고, `exact`/`descendant`/
  `ancestor`를 파생해 보낸다. 어휘는 우리 것(topic-api의 `related` ≠ 우리 `descendant`).
  ⑷ **`match_reason`을 재료가 아니라 문장으로**, 그래서 **`lang`이 되살아났다**(§2). rev 5의 `lang`
  삭제 근거는 "우리는 재료만 보낸다"였고 그 전제가 바뀐 것이다 — 문장 생성은 언어 의존이고 그 언어는
  요청만 알려줄 수 있다. 라벨 ko·en 병기는 그대로 두므로 축소가 아니라 추가다. 결정적 템플릿으로 두는
  이유는 **문장 자체가 계측**이라서다(문장이 이상하면 relation이나 대표 topic 선택이 이상한 것).
  구현은 코드 repo PR 8(`feat/recommend-card-material`)이고, 이 문서가 먼저 고쳐진 뒤 `owner_user_id`
  코드가 들어간다 — 잠근 결정을 코드가 먼저 뒤집는 순서를 만들지 않기 위해서다.

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
