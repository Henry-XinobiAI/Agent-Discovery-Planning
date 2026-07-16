# for/against stance retrieval — 설계 (임시 draft)

- **상태**: PROVISIONAL / 브레인스토밍 수렴본. 아직 writing-plans 미착수, 구현 미시작.
- **날짜**: 2026-07-16
- **범위**: Discovery의 for/against stance 판별을 memory-api Personal Entity 데이터로 어떻게 구현할지 + 필요한 cross-team 계약 요청.
- **관련**: Phase 10 real-edge 통합(competence/groundings → AgentTopicEdge 투영), Phase 8-3 stance normalizer, Phase 8-5 rich-reason(top-N async LLM slice 패턴), grounding-agent/reason-generator LLM-component 규율(단 여기선 symbolic floor가 없어 judge=유일 엔진 — §D4에서 구분).

---

## 1. 문제

`GET /{prefix}/personal/entities`(우리가 얘기하던 edge)가 각 에이전트의 토픽별 지식/입장을 준다. Discovery의 for/against는 "특정 명제에 대한 입장(favor/against)"이 필요한데, 응답이 주는 stance 신호는 `competence.sentiment`(극성) + `opinion_ratio` + `consistency` + `support_ids` 정도다.

**핵심 난점**: polarity(sentiment) 단독으로는 for/against를 못 정한다. sentiment는 "대상을 향한 감정 valence"이고 stance는 "명제 위에서의 방향"이라 자주 어긋난다(열정적 비판자 = 높은 engagement + against). 명제/축(axis)과 방향이 빠진 극성만으로는 방향 확정 불가.

**핵심 불변식 (설계 전체가 여기 달림)**: **sentiment는 stance verdict가 아니다. for/against verdict의 유일한 source는 Tier 2 LLM claim-judge다.** memory-api가 주는 topic-level stance는 verdict가 아니다 — stance 방향은 본질적으로 **query-axis-relative**인데(같은 topic이라도 "원전 확대"엔 against·"안전규제 강화"엔 for), 사전계산된 topic-level 값은 **axis-blind**라 verdict가 될 수 없다. 따라서 **Alpha에 live symbolic floor는 없다.** judge가 disabled/unavailable/degraded면 for/against는 후보를 반환하지 않고 **명시 사유와 함께 silence**한다(§D4). **sentiment→dir 합성 금지** — sentiment는 retrieval prior(Tier 1 랭킹)·evidence selection 전용.

## 2. 기각된 대안 (왜 안 되는지 기록)

aspect(토픽의 하위 논점) 단위로 매칭하려는 모든 시도가 같은 벽에 부딪힘 — **aspect는 open-vocabulary + many-expression-one-meaning이라, exact 키는 파편화하고 fuzzy 키는 토픽 내 변별력이 붕괴한다.**

- **새 aspect-QID 온톨로지 신설**: 토픽마다 aspect가 제각각 → 큐레이션/유지 비용 폭발. 파편화를 없애는 게 아니라 한 계단 아래로 relocate.
- **context-QID(문장이 함께 언급한 기존 Wikidata 개념)로 변별**: "climate change / global warming / carbon emissions / decarbonization / net zero"가 서로 다른 QID라, 같은 aspect 입장이어도 exact 겹침이 실패. Wikidata가 정리돼 있어도 many-to-one 문제는 그대로.
- **임베딩 유사도**: 한 토픽 안 aspect들은 공유 성분이 지배해 cosine이 좁은 고대역에 뭉침 → 변별력 없음.

**구조적 결론**: aspect 세밀도에는 공짜 discrete 키가 없다. aspect 단위 매칭을 하려면 "유지되는 정규화/클러스터링 레이어"라는 없앨 수 없는 비용이 따른다. 따라서 진짜 결정은 "어떤 인코딩이 파편화를 피하나"(→ 없음)가 아니라 **"Alpha가 그 비용을 감수하며 aspect 세밀도가 필요한가"**이다.

## 3. 확정 결정 (LOCK)

### D1. Alpha = topic 단위 for/against (aspect 온톨로지 없음)

- 키 = 깨끗한 Wikidata **topic QID 하나** → 파편화 문제 자체가 없음.
- 여기서 "topic 단위"는 **retrieval 앵커가 topic QID 하나**라는 뜻이다(사전계산된 topic-level stance 값이 아님). verdict는 Tier 2 judge가 **query-stance-relative**로 만든다 — 그래서 aspect 온톨로지 없이도 축 구분("원전 확대" vs "안전규제")이 judge 안에서 암묵적으로 처리된다(D2). 핵심 가치(지지자 vs 반대자 변별)는 judge가 담당.
- aspect가 실제로 필요한 유일 케이스("전반 반대지만 이 한 축만 찬성")는 niche → **Open Beta 명시 베팅으로 이월**. 추구 시 "memory-api가 소유하는 유지되는 per-topic aspect 정규화 레이어"로 비용을 눈 뜨고 인정하고 착수.

### D2. 2-tier retrieval

- **Tier 1 (memory-api, 인덱싱 가능, 온톨로지 불필요)**: `topic=Q` 필터 + `has_opinion`(opinion_ratio>0) + competence 서버 랭킹 + `limit=K`. → 수백만 edge가 아니라 "그 토픽에 실제 입장 있는 상위 K명". 여기 쓰는 신호는 memory-api가 이미 가진 것(sentiment, opinion_ratio, competence).
- **Tier 2 (Discovery, shortlist 위에서만)**: K명 각각의 claim + normalized user stance를 LLM에 넘겨 판정. aspect 판단을 키가 아니라 **LLM이 실제 claim을 읽고 암묵적으로** 수행 → 유지할 온톨로지 없음. Tier 1이 K로 좁혀놨기에 가능("어려운 semantic 판단을 bounded set에 격리").
- ⚠️ **summary-only는 판정 근거로 약함**: claim summary는 이미 LLM이 압축한 텍스트라 반어·인용·"남들은 X라지만 나는 Y" 같은 문장에서 stance nuance가 소실되고, provenance 원문 없이는 judge가 틀린다. → inline claim은 `text`에 더해 `statement_kind`·`epistemic`·`confidence`·`provenance_message_ids`(+가능하면 `support_snippet`/short quote window)를 함께 요구(§4-3·§D5).
- **verdict source는 judge 하나뿐**: Tier 1은 **stance-무관 후보 shortlist 생성**만(has_opinion + salience/competence 랭킹 + limit). stance 방향 판정은 전부 Tier 2 judge. → memory-api가 stance 방향을 알 필요 없음(ownership 선명).
- **왜 topic-level floor를 안 두나**: topic-level coarse stance는 axis-blind라(topic 자체 찬반) query-axis-relative judge보다 semantic으로 열등하다. floor를 두면 열등한 신호가 우월한 신호와 경쟁하고 ownership이 흐려진다 → floor 없음. (memory-api가 값싸게 topic-level hint를 주면 verdict가 아니라 **Tier 1 prior로만** 허용 — sentiment와 같은 지위.)

### D3. Tier 2는 "선택"이 아니라 "판정" (ordering contract 보존)

- LLM은 후보별 **판정만**: `{verdict: aligned | opposed | insufficient, evidence_stmt_ids, (선택)graded_confidence}`.
- 랭킹은 그 위에서 **여전히 결정적으로** competence + judge `graded_confidence`(= stance verdict confidence)로. LLM verdict는 **필터/주석**이지 scalar score가 아님. → "scalar score 없음 · 결정적 lexicographic ordering" 계약 유지.
- **불변식**:
  - LLM judge는 **후보 집합 밖 agent를 추가하지 못한다**(Tier 1 shortlist 내에서만 판정).
  - verdict=`insufficient` 후보는 for/against need에서 **drop**한다.
  - `evidence_stmt_ids`는 inline 제공된 statement id의 **subset이어야 한다**(firsthand-honesty). violation 시 degrade scope는 **후보 단위**(§D4).

### D4. judge = for/against의 유일 엔진 · 플래그 · judge-off silence

- **enhancement 아님, 유일 엔진**: floor가 없으므로 judge는 grounding-agent/reason-generator처럼 "symbolic floor 위 보강"이 **아니라** for/against 기능의 **유일한 구현체**다. 따라서 플래그(`STANCE_JUDGE_ENABLED` 류) 의미 = **"for/against 기능 on/off"**. dark-merge(코드 OFF로 머지)는 OK지만 **Alpha 배포는 judge를 ON으로 돌린다**(OFF ship = for/against 없는 Alpha).
- **judge OFF / unavailable / degraded → (b) 명시 silence** (결정): for/against verdict 없음 → `recommendations=[]` + `silence.silent=true` + `silence.reason`. **empty result와 구분되도록 사유를 남긴다**:
  - `stance_judge_disabled` — 플래그 OFF
  - `stance_judge_unavailable` / `stance_judge_failed` — 런타임 실패/degrade
  - `all_candidates_insufficient` — shortlist는 있었으나 전원 verdict=insufficient
  - (기존 `SilenceView(silent, reason)` 계약 재사용 — `serving.py`, 현행 `"no_candidates"`에 위 사유 추가)
- **"topic discussers fallback" 금지**: stance 미평가 후보를 stance recommendation으로 반환하지 않는다. degrade라 표시해도 downstream이 for/against 결과로 소비하면 **"response never lies" 위반**. 관측성은 `silence.reason` + decision log로 해결한다.
- **serve는 sync 유지, judge는 shortlist만 async**: Phase 8-5 `generate_reasons_async`가 top-N만 await하는 shape 재사용.
- **eval**: for/against **verdict 품질은 judge stratum(비결정적)에서만** 측정. 결정적 gate는 배관만(stub judge: shortlist retrieval·insufficient→drop·`silence.reason`·non-stance 질의 불변). gate에 judge 안 넣음.
- **firsthand-honesty 가드 + degrade scope**: `evidence_stmt_ids`는 inline 제공된 statement id의 subset이어야 한다. **violation은 기본적으로 해당 candidate verdict만 invalid로 처리한다(→ `insufficient`/drop). judge 응답 전체 shape이 깨진 경우에만 batch degrade로 간주한다.** (후보 단위 격리 — 한 모델 실수가 전체 for/against silence로 번지는 것 방지. batch degrade는 §D4의 `stance_judge_failed` silence로 이어짐.)

### D5. payload shape — claim summary + metadata/snippet은 Tier 1 응답에 옵트인 inline (N+1 회피)

- `GET .../{qid}`에 담는 것만으로는 **후보당 1콜 = 여전히 K× round-trip(N+1)**. → 한 단계 위로.
- **Tier 1 list/search 응답에 claim summary + metadata/snippet(§4-3: statement_kind·epistemic·confidence·provenance_message_ids·support_snippet)을 옵트인 inline** → Tier 2가 추가 round-trip 0으로 in-hand 데이터만으로 판정. "Tier 1이 모든 fan-out 흡수, Tier 2엔 fan-out 없음"을 HTTP 레이어까지 유지.
- `/statements`(전량·페이지네이션)와 `/{qid}`(상세)는 drill-down / fallback 경로로 남김. 핫 패스만 inline claims 사용.

## 4. memory-api 계약 요청 (cross-team)

aspect 온톨로지 큐레이션은 **요청하지 않는다.** 요청 목록:

1. **Tier 1 retrieval**: `topic` 필터 + `has_opinion`(opinion_ratio>0) + competence 서버 랭킹 + `limit`. (토픽 retrieval의 자연스러운 확장.)
2. **stance verdict는 요청하지 않는다 (ownership 경계)**: stance 방향은 query-axis-relative라 **Discovery 소유**다. memory-api는 **query-무관 신호만** 제공한다 — statements(opinion/experiential/preference) + metadata(§4-3) + retrieval prior(salience, competence, opinion_ratio, sentiment). `stance_dir`은 **필수 계약에서 제외**. (선택) memory-api가 값싸게 topic-level stance hint를 계산하면 Discovery가 **Tier 1 prior로만** 쓸 수 있음 — verdict로는 절대 안 씀.
3. **claim inline (옵트인, 판정 근거 강화)**: list/search에 `include_claims=true` 류 파라미터 + **엔티티당 top-M 상한** + **stance-bearing claim 우선**(sentiment/competence를 먹인 support_ids 쪽). `text`만이 아니라 `statement_kind`·`epistemic`·`confidence`·`provenance_message_ids`(+가능하면 `support_snippet`/short quote window)까지. summary-only는 반어·인용에서 judge를 틀리게 함.

## 5. Open items (다음 결정)

- **K 크기 / batch shape**: Tier 2가 감당할 shortlist 크기(수십), 후보 판정을 per-candidate vs 소배치. `/statements` fallback 병렬화.
- **silence.reason 최종 taxonomy 확정**: `stance_judge_disabled` / `stance_judge_unavailable` / `stance_judge_failed` / `all_candidates_insufficient` + 기존 `no_candidates`의 최종 이름·중복 정리(serving 계약).
- **multi-proposition 결합 의미론** (원래 논점, Alpha 필요 여부 재검토): 질의에 명제 여러 개일 때 AND 전부일치 / coverage 부분일치 / round-robin. Alpha가 single이면 이월.
- **payload 상한 M 값** + 옵트인 파라미터 최종 이름(memory-api와 협의).
- **confidence 명명 분리 (계약 시)**: 여러 confidence가 등장하므로 이름을 구분한다 — `statement_confidence`(claim 단위), `competence.*`(competence vector), judge `graded_confidence`(stance verdict 신뢰도 = 사실상의 stance confidence), (선택) optional topic-level hint의 confidence(Tier 1 prior 한정). 같은 `confidence` 이름 재사용 금지.

## 6. Phase 10 정합

이 설계는 Phase 10(competence/groundings → AgentTopicEdge 투영 + translation layer)의 stance 축을 구체화한다. 진짜 갭으로 찍어둔 "eligibility + stance axis/dir/confidence + evidence-ref 노출" 중 **stance·evidence-ref**를 다룸. eligibility 노출은 별도 트랙.
