# Persona 팀 데이터·API 요청서 (Discovery/agent-recommendation-api) — rev 13 (draft)

작성: 2026-08-13 · 상태: **내부 리뷰용 초안** (발신 전 리뷰 필요) · 개정 요지는 부록의 개정 이력 참조 (최근: rev 12 = topic 공개 모델 확정 + statement 본문은 내부 판정 전용 · rev 13 = owner별 상태 조회를 진단용 🟡로 강등)

> **검색 전제 (rev 7에서 확정):** topic 탐색은 **vector-free agentic search**다 — LLM이 query를 생성·확장·보정하며 persona의 **텍스트 검색**을 반복 호출하고, LLM이 후보를 판정한다. persona 쪽에 embedding/vector 인프라를 전제하는 요청은 이 문서에서 전부 "persona가 독립적으로 표현 공간을 갖게 될 경우의 선택적 최적화"로 강등했다. vector-free에서 recall을 지키는 책임 분담: persona = **검색 대상 텍스트 재료를 충실히**(name·aliases·search_aliases·description·keywords 전체가 검색 대상) + **다국어 search alias 생성**(P1 계약 ⑤ — "커피" 질의가 "coffee" topic을 찾는 1차 메커니즘), Discovery = **query expansion**(paraphrase·표현 변형; 번역은 보완), 검증 = P11 golden set(정답 label을 미리 확정해 둔 평가 기준 데이터).

> **선제 대응 문서.** 이 전환은 확정이 아니다. memory-api v2 이행 트랙(분석 문서·V2-1 요청서)은 **현 상태 그대로 유지**하고, 이 문서는 전환이 확정될 경우를 위한 사전 요청 목록이다.

## 0. 배경 — 아키텍처 전환의 이해

전달받은 변경:

- memory-api에는 **conversation만** 남는다. knowledge(공용 KG)·personal entity는 memory-api에서 빠진다.
- **persona 팀**이 memory-api(대화)를 source로 우리에게 필요한 데이터와 유저별 persona를 제공한다.
- 기존 knowledge(Wikidata anchor — 모든 유저가 공유하던, topic을 고정하는 공용 기준점)는 사라지고 유저별 **topic**이 생긴다. topic = 유저가 관심 갖고 자기 agent와의 대화에서 쌓은 지식·의견의 카테고리. **anchor 없음, 유저마다 generalized한 이름이 독립적으로 결정 → 파편화 가능.**
- 우리는 topic 탐색에 **agentic search**를 쓴다: client가 topic 지정 및/또는 대화 컨텍스트 제공 → query expansion → 복수 query로 topic 탐색 → 기존 recommend처럼 해당 주제로 대화할 agent, for/against/orthogonal 의견 agent 추천.
- persona는 유저별 성격/특성을 **HEXACO**로 추출; 추후 "주제 없이 성격이 맞는 유저 추천"에 필요.
- 지금은 **모든 것을 우선 요청해 둘 수 있는 단계** — 논의로 빠질 수 있음을 전제.

기본 제약: **모든 값은 대화에서 추출 가능한 것이어야 한다.** 이 문서의 모든 요청은 이 제약 안에 있다 (Wikipedia 카테고리 같은 외부-KG 유래 값은 요청하지 않는다).

**요청의 잠금 수준 — 이 문서를 읽는 법.** 우리는 기존 구현을 참고하되 **처음부터 새로 구현하는 것에 열려 있다.** 따라서 이 문서가 계약으로 잠그는 것은 목적 수준의 두 가지뿐이다: **(a) 신호의 축** — 깊이·일관성·근거량·최근성·경험·관계 같은 *어떤 종류의 값이 존재해야 하는가* — 와 **(b) 값의 의미 요건** — consistency의 정의, evidence unit의 중복 제거, `evidence_last_seen`의 파생 규칙처럼 *어떤 구현에서도 지켜져야 값이 안전한 성질*. 반면 **우리의 현행 공식과 파이프라인 구조**(maturity 가중, n/(n+4), 90일 반감기, facet round-robin — facet은 한 주제 안의 하위 갈래, round-robin은 갈래를 돌아가며 하나씩 뽑는 방식 — 등)는 우리가 재설계할 수 있는 부분이며 persona 쪽 제약이 아니다 — 본문에서 현행 소비처를 인용하는 것은 "이 축이 실제로 소비된다"는 증거이지, 그 공식대로 맞춰달라는 요구가 아니다. persona 팀이 같은 축을 더 잘 담는 다른 신호를 제안하면 환영한다.

용어 주의: **coverage와 orthogonal은 다른 것이고, orthogonal 안에서도 두 개념이 갈린다.** coverage는 현행 NeedType(depth/experience/for/against/coverage)에 있는 기존 기능 — "한 주제의 여러 갈래를 고루 아는 pool" — 이고 그 대체 계약이 P7이다. orthogonal("다른 관점의 의견")은 현행 코드에 없는 **Open Beta 신규 need**로 판정 설계는 추후다. 단 개념을 구분해야 한다: *contrasting topic*("원격근무"↔"사무실 근무" — topic 관계, P7 어휘 ⚪)과 *orthogonal viewpoint*(같은 명제를 생산성이 아니라 조직문화·보안 관점에서 말함 — evidence의 논점 차이)는 다르며, 후자를 가능하게 하는 **evidence primitive(우리가 조합해 쓰는, 상류가 제공하는 기본 연산)는 P5가 지금 확보한다** — 저장된 orthogonal 라벨이 아니라 검색·분류 재료를 요청하는 것이므로 신규 need를 선점 설계하는 것이 아니다.

### 0.0 확정된 전제 (2026-08-13 확인)

1. **대화 컨텍스트는 recommend 요청 body로 받는 것이 1안.** client가 이미 매 대화 컨텍스트를 들고 있으므로 그대로 보내면 되고, 우리가 memory-api에 conversation을 재요청하면 지연만 는다. 현행 `ContextMessage` 계약 유지. (memory-api conversation 조회는 fallback 옵션으로만 남긴다 — 이 문서에서는 요청하지 않는다.) 단, **context-only 요청은 현행 recommendation API 계약으로는 불가능**하다 — 이건 persona 요청이 아니라 우리 내부 작업이다 → P0.
2. **owner ↔ agent는 항상 1:1**이고, 추천 대상은 **항상 타 유저의 agent**다.
3. **HEXACO 매칭도 서빙 좌표계는 agent 공간 그대로다.** 각 유저의 agent가 주인의 HEXACO를 알고 계속 업데이트하며, 타 유저와 대화할 때 주인의 HEXACO를 모방해 응답한다(자신이 유저라고 말하지는 않음). 따라서 매칭의 *비교 축*은 유저 HEXACO지만 *추천되는 실체*는 그 유저의 agent — 우리 파이프라인의 owner_id→agent_id 파생 identity 층이 그대로 유효하다.
4. **persona 팀 제공 형태는 online HTTP API.**
5. **(2026-08-14 확인) 추출은 batch release가 아니라 유저별 상시 증분 처리다.** memory-api처럼 코퍼스 전체를 한 번에 굽는 것이 아니라, 유저가 서비스를 사용함에 따라 그 유저의 데이터가 그때그때(처리 window 단위 가능) 갱신된다. 갱신 중인 순간은 짧고, **갱신이 진행되는 동안에도 그 유저의 기존 값은 계속 조회된다.** 이 전제의 파생 결정: cross-endpoint snapshot pinning은 **철회**하고(전역 시점 고정은 release 없는 저장 모델에 MVCC — 과거 판본을 함께 보존하는 다중 버전 저장 — 류의 부담을 지우는 요구가 된다), 읽기 모델을 "각 단계는 최신 값 + 사라진 항목은 item별 제거"로 바꾼다 → P10-⑦.
6. **(2026-08-14 확인) 노출 결정 단위는 topic이고, 기본은 비공개다.** 유저는 자기 agent와 대화하며 지식·의견을 쌓고 이것이 topic별로 카테고리화된다. 유저가 **topic별로** 타 유저 공개 여부를 결정하며, **신규 topic의 기본값은 비공개 — 명시적으로 공개한 topic만** 검색·추천 대상이다. persona가 topic에 공개 여부 필드를 관리한다. 발언의 공개성은 **소속 topic을 승계**하는 파생값이다(발언 단위 독립 제어 없음). 파생 결정: 노출 3층(owner/topic/statement) 요청 철회 → P10-④, 신규 topic 원자적 공개 요건은 이 모델이 구조적으로 흡수 → P10-⑦-(b).
7. **(2026-08-14 확정) 발언 본문은 최종 유저에게 노출되지 않는다.** statement `text`는 우리 내부 stance 판정(LLM judge)의 재료일 뿐이고, 추천 응답이 요청 유저에게 제공하는 것은 추천 여부와 **요약·부연 수준의 이유**다 — **발언 원문 인용은 배제로 잠근다** (제품 결정). 파생 결정: `text`의 cross-user 노출용 정제 요구 철회(추출물 + 방향·강도 보존만 요구) → P5-④, statement 개별 억제·statement 단위 publishability 요구 철회.

### 0.1 이 전환이 우리 파이프라인에 주는 구조적 충격 — 한 문장

> **join key가 사라진다.** 지금 파이프라인 전체는 Wikidata QID(anchor)를 join key로 돈다 — grounding이 QID를 확정하고, edge(`anchor_id`)·stance evidence(`subject_qid`)·neighbor expansion·coverage facet 그룹핑이 전부 그 QID로 묶인다. topic이 유저별로 독립 명명되면 "같은 주제"가 **exact join이 아니라 유사도 판정**이 된다. 아래 요청의 절반은 이 판정을 가능/저렴/일관되게 만들기 위한 것이다.

### 0.2 우리가 소비하는 신호의 대응표

우리 랭킹은 scalar score가 없는 **순서 계약(ordering contract)**이다 — 점수를 합산하는 대신 단계별 규칙으로 순서를 정한다: **gate(문턱 — 통과 못 하면 후보 자체가 탈락) → filter → lexicographic(사전식 — 앞 기준이 같을 때만 다음 기준을 봄) → tiebreak(동률일 때만 가르는 마지막 기준)**. 아래가 그 입력 전부이고, 각각의 persona-시대 대응이 이 문서의 요청 번호다. (위 잠금 수준 원칙대로, 이 표의 "현재 신호" 열은 소비의 증거이지 보존 요구가 아니다 — 잠기는 것은 오른쪽의 축과 각 요청의 의미 요건이다.)

| 현재 신호 (코드 계약) | 지금까지의 출처 | persona 시대 대응 | 요청 |
|---|---|---|---|
| grounding: topic_text → QID 확정 | knowledge KG (exact-label + LLM rerank) | topic 탐색 (agentic search) | P1, P2, P6 |
| `maturity` = depth × (0.6 + 0.4×consistency) — **hard gate + 1차 정렬키** | personal entity competence | (owner, topic) competence 등가물 | P3 |
| `evidence_strength` = n/(n+4) — 밴드 내 2차 정렬키 | 근거 statement 수 | topic별 **evidence unit 수** (extractor 분할 성향 비오염) | P3 |
| `freshness` — 90일 반감기 decay | (v1/v2 모두 **잘못된 시계**를 읽고 있었음) | `evidence_last_seen` — 이번엔 처음부터 올바르게 | P3-③ |
| `experience_source_type`/`experience_specificity` — experience need 전용 | **계약에 자리만 있고 채워진 적 없음** | 1인칭 경험 provenance(유래 — 직접 겪었나, 배워서 아나) | P4 |
| stance evidence 검색 (`subject_qid` + owner shortlist + query bag) | personal statement 검색 (BM25) | evidence 검색 **2층** (발견층 + 본문층) | P5 |
| coverage: QID facet별 그룹핑 → round-robin (`_coverage_round_robin`) | edge가 놓인 QID = facet id | facet 분할은 **query-local로 우리가 소유** — persona에는 재료(관계)만 요청 | P7 |
| sparse pool의 neighbor 확장 (`expand_connections`, 직접 edge 부족 시) | knowledge graph의 인접 QID | **related-topic 확장** | P7 |
| `PersonaPrior` (optional·hollow guard — 힌트는 되지만 자격을 만들지는 못하는 "빈 보증" 신호·밴드 내 tiebreak 전용) | 미배선 (fixture만) | HEXACO 등 persona 신호 — **wire model(HTTP로 오가는 전송 형태)은 신규 설계** | P9 |
| `discoverable` (privacy-owned) | privacy 팀 (deferred) | 노출 가능 여부 — **공개 topic 단위 (유저 결정·기본 비공개)** | P10-④ |

---

## 1. 요청 목록

각 요청은 (왜 — 제품 관점) / (무엇 — 필드와 의미) / (계약 — 우리가 경험으로 배운 함정) 순서다. 우선순위: 🔴 없으면 해당 기능 자체가 없음 · 🟡 없으면 품질/비용이 크게 나빠짐 · ⚪ 예약 (지금 합의만, 구현은 추후).

### P0 🔴 [내부 작업 — persona 요청 아님] context-only 요청의 계약 변경

**이 문서의 제품 시나리오("topic 지정 또는 대화 컨텍스트 또는 둘 다")는 현행 우리 API 계약과 어긋난다.** `Query.topic_text`가 필수 nonblank(`Field(min_length=1)`)라서 context-only 요청은 지금 422다. 전환 시 우리 쪽 작업으로:

- `topic_text` 또는 `context_messages` 중 **최소 하나 필수**로 계약 변경 (둘 다 없으면 422).
- normalize/expansion 단계가 context에서 nonblank search intent를 생성하는 책임을 진다.

기존 API를 고치는 경로든 처음부터 새로 구현하는 경로든 이 계약이 출발점이다 — 재구현이라면 "변경"이 아니라 처음부터 이렇게 설계한다. persona 팀 발신 문서에는 이 항목을 넣지 않는다 — 여기 두는 이유는 발신 문서의 시나리오 서술과 우리 실제 API가 어긋나지 않게 이행 순서에 묶어두기 위해서다.

### P1 🔴 Topic 검색 primitive — agentic search의 발판이자 hot path(매 추천 요청마다 실행되는 가장 빈번한 경로)

**왜.** 유저가 "이 주제로 대화할 사람"을 찾을 때, 그 주제를 실제로 아는 유저를 찾는 것이 추천의 첫 단계다. topic이 유저별로 독립 명명되므로 "머신러닝"·"ML"·"기계학습"·"딥러닝 공부"가 네 유저에게 네 개의 다른 topic으로 존재할 수 있다. 우리는 query expansion으로 이 변형들을 생성해 검색한다. vector-free 전제(문서 머리)에서 **검색이 못 찾은 topic은 LLM rerank가 되살릴 수 없으므로**, recall의 방어선은 셋이다: 검색 대상 필드의 폭(계약 ⑥), 다국어 search alias 생성(계약 ⑤), expansion의 표현 다양성(우리 책임). (경험: 기존 stance evidence 검색이 BM25 단독이라 lexical-recall gap — query와 발언의 단어가 겹치지 않아 의미가 같아도 못 찾는 손실 — 이 측정 불가능한 맹점으로 남았다. 그래서 이번엔 recall을 P11 golden set으로 **측정 가능하게** 만드는 것까지가 요청이다.)

**단, P1은 후보 회수의 유일한 채널이 아니다 — topic-first 단일 회수는 legacy 구조다.** 현행 파이프라인은 "grounding → edge → evidence" 순서라 topic(anchor)을 먼저 확정한 owner만 evidence 단계에 도달했다. 이 순서를 그대로 이식하면 need별로 회수 불가능한 유저가 생긴다: 명제에 강한 의견이 있지만 topic competence 순위가 낮은 유저(for/against), 경험은 분명한데 일반 지식 depth가 낮은 유저(experience), topic 이름은 다르지만 중요한 하위 관점을 가진 유저(coverage). 새 설계의 후보 pool(모집된 후보 집합)은 **채널 union(합집합)**이다:

```
topic 검색(P1) ∪ evidence 발견(P5 층 1) ∪ related 확장(P7)
→ union·dedupe → P2 batch hydrate (미보강 key만)
→ 비싼 본문 fetch(P5 층 2)·judge는 hydrate된 union 이후에만
```

따라서 P1이 잠그는 것은 "topic 채널"의 계약이고, evidence 채널의 후보 발견은 P5 층 1이 담당하며, **어느 채널로 왔든 후보는 최종적으로 같은 `TopicCandidate` projection이 된다**. 여기서 **hydrate**는 좌표(owner, topic)뿐인 후보에 랭킹에 필요한 값을 채워 넣는 보강을 뜻하고, **projection**은 전체 필드 중 필요한 것만 추린 응답 형태를 뜻한다. 반환형 계약: P1 search hit는 **이미 완성된 TopicCandidate**(hydrate 불필요), P5/P7의 좌표-only hit만 P2 batch로 hydrate하고 **그 batch의 반환형도 TopicCandidate**다(상세형 TopicCard는 단건 GET 전용). evidence hit는 그 자체로는 랭킹 불가능하고, key별 단건 조회는 N+1(목록 1회 조회 후 항목마다 추가 조회가 N번 생기는 패턴)이므로 hydration은 batch 1회다.

**union의 provenance 규칙 (우리 내부 계약 — P0과 같은 층).** 같은 (owner, topic)이 세 채널에서 다 발견될 수 있는데, 단순 dedupe하면 "왜 후보가 됐는가"가 사라진다. union 후보는 채널별 유입 근거를 보존한다: `retrieval_reasons: [{channel: topic, matched_query_indices}, {channel: evidence, kind}, {channel: related, source_topic}]`. 이것이 있어야 direct/related 우선순위(related-only 후보가 core 후보로 오인되는 것 방지), 채널별 회수율 측정·cap 조정, 채널 제거 실험, decision log 기록이 가능하다. persona에 요구되는 것은 공통 구조가 아니라 **각 채널 응답이 이 근거를 구성할 최소 정보를 담는 것**뿐이다 — P1의 `matched_query_indices`, P5의 `kind`, P7의 `source_topic`(related 결과가 어느 topic에서 확장됐는지).

**무엇.**

```
POST /{tenant}/persona/topics/search
{
  "queries": ["기계학습", "머신러닝 모델 튜닝", ...],   # expansion 결과 복수 query, ANY-match(하나라도 걸리면 hit)
  "limit": 100,
  "per_owner_limit": 3,                                # 한 유저가 결과를 도배하지 않도록
  "owner_ids": null,                                   # null=전체(cross-user), 지정 시 그 유저들로 한정
  "filters": {                                         # 선택 — 계약 ⑦
    "min_evidence_count": 3, "min_depth": 0.5, "min_consistency": 0.5,
    "experience": "firsthand", "evidence_last_seen_after": "2026-02-01T00:00:00Z"
  }
}
→ { items: [TopicCandidate], next_cursor, truncated }
```

**`TopicCandidate`는 랭킹에 필요한 값을 전부 실은 cross-user 전용 projection이어야 한다** — 검색이 100건을 주는데 competence가 단건 조회에만 있으면 요청 1번 뒤 조회 100번(N+1)이 된다. 잠기는 요건은 "**한 채널 안에서 per-hit 추가 조회가 없다**(전체 요청의 왕복 수는 채널 수 + hydration 1회로 유계)"이고, **같은 projection을 P2 batch가 임의의 key 집합에 대해 반환**해야 다른 채널의 후보도 동일 shape로 합류한다. 아래 필드 구성은 그 요건을 채우는 구체 제안이다:

| 필드 | 출처 요청 |
|---|---|
| `owner_id`, `topic_id` | — (식별자, P2 계약 ① 좌표계) |
| `name`, `description`, `lang` (표현 언어; cross-user 공개 가능하게 정제된 것) | P2 / P10-⑤ / 계약 ⑤ |
| `matched_query_indices` | 아래 계약 ③ |
| `depth`, `consistency`, `evidence_count`, `evidence_last_seen` | P3 |
| `experience` (provenance별 bucket 집계) | P4 |
| `extraction_state`, `as_of`, `extraction_run_id`, `model_version` | P3 계약 / P8 |

**계약.**
1. **cross-user가 기본**이어야 한다. per-owner 조회만 있으면 우리는 전 유저를 순회해야 하고 그건 유저 수에 선형이다. (경험: v1/v2에서 cross-owner 조회가 없어서 별도 요청서(V2-1)를 써야 했다 — 이번엔 처음부터.) 검색 모집단은 **명시적으로 공개된 topic만**이다(§0.0-6·P10-④) — 우리 추천 pool의 상한은 검색 품질 이전에 공개 비율이 정한다.
2. **score는 version-scoped optional signal이다.** 두 가지 구분이 이 결정의 바탕이다: "score에 의존하지 않는다"와 "score를 받지 않는다"는 다른 결정이고(받되 의존하지 않을 수 있다), "보조 신호"라도 abstain(판단 보류)·fusion(채널 결과 통합)·pruning(후보 미리 쳐내기)에 쓰는 순간 행동을 바꾸므로 그 값은 계약이다. 정확한 구획:
   - **계약인 것**: 필드 shape·값 범위·의미·해석 가능한 component 구성(`lexical_match` 등), 그리고 `search_model_version` 동반.
   - **계약이 아닌 것**: 서로 다른 model version 사이의 숫자 비교 가능성 — 보장을 요구하지 않는다.
   - **우리 구현 선택인 것**: 실제로 ordering/abstain에 쓰는지. 쓴다면 **해당 version에서 calibration(점수가 실제 적중률과 맞는지의 검증)/eval을 통과한 뒤에만** (P11) — version이 바뀌면 재검증 전까지 사용 중단.
   - 결과 **순서**는 version과 무관하게 항상 제공되는 안정 계약이다.
3. **merge 정책은 우리가 소유한다 — persona에는 그것을 가능하게 하는 capability만 요청한다.** 복수 query의 단일 ANY-match top-N이면 강한 query 하나가 결과를 독점해 나머지 expansion query가 굶는다. 단 "query별 균등 quota"를 계약으로 요구하지도 않는다 — **expansion query는 품질이 균일하지 않고**(LLM이 만든 나쁜 확장에 동일 quota를 주면 recall은 늘어도 precision이 무너진다), 어느 query를 얼마나 신뢰할지는 expansion을 만든 우리만 안다. 요청하는 capability:
   - query별 **cap 설정 가능** (요청 파라미터), 또는 query별 **독립 검색 모드** (우리가 호출을 나눠 merge 소유 — 기본 선호).
   - 서버가 merge를 제공한다면 그 **정책과 query별 기여량을 응답에 공개**.
   - *observability(계측 가능성)*: 결과에 **`matched_query_indices`** — merge 정책과 무관하게 expansion coverage 측정에 필요하다. 관련도 score가 아니므로 계약 ②와 충돌하지 않는다.
4. 빈 결과와 "추출이 아직 안 됨"은 구분돼야 한다 — 서비스/코퍼스 수준은 P8, 유저 단위는 P2-④의 batch item `not_extracted`(rev 13: owner별 상태 조회는 파이프라인이 부르지 않는다).
5. **다국어 계약 — cross-lingual recall의 1차 메커니즘은 storage-side search alias 생성이다.** user-local generalized topic은 언어까지 파편화된다: 유저가 영어로만 대화해서 topic이 "coffee"로 저장됐다면, "커피"로 질의하는 유저는 그 topic을 영원히 못 찾는다 — **관측된 alias의 인덱싱만으로는 안 풀린다** (그 유저는 "커피"라고 말한 적이 없으므로 관측 alias가 없다). 요청:
   - **(a) search alias 생성(enrichment)**: topic 생성/갱신 시 name(+aliases)에서 **서비스 지원 언어(한국어·영어·일본어 등 — 언어 셋은 Q12)의 번역·표기 변형을 생성해 검색 인덱스에 포함**한다. "커피" 질의 → "coffee" topic이 직접 hit되는 것이 목표다. topic당 1회 생성이므로, 요청마다 우리가 번역을 추측하는 것보다 결정적이고 싸다.
   - (b) 관측 alias와 생성 alias의 **구분 유지**(`aliases` vs `search_aliases`) — 관측 alias는 유저 발화 유래라 정제 대상(P10-⑤)이고, 생성 alias는 name 파생이라 부담이 다르다. 표시·rerank에는 관측만, 검색에는 둘 다.
   - (c) `TopicCandidate`의 표현 언어(`lang`).
   - (d) recall을 검증할 cross-lingual golden case(P11) — "커피"→"coffee"류가 대표 케이스다.
   - 우리 query expansion의 번역은 **보완**으로 남는다(생성이 커버 못 하는 언어·신조어). semantic 검색이 로드맵에 오르면 그때 cross-lingual 매칭 동작을 계약에 추가한다.
6. **검색 대상 필드의 계약**: 검색은 **`name` + `aliases`(관측) + `search_aliases`(생성, 계약 ⑤) + `description`(+ 추출 keywords가 있다면 그것까지) 전체**를 대상으로 해야 한다. vector-free에서는 이 폭이 recall의 상한이다 — name만 검색되면 expansion을 아무리 잘해도 설명문에만 있는 표현의 topic은 영원히 안 잡힌다.
7. **원시 필드 필터**: `TopicCandidate`의 신호 필드에 대한 요청 파라미터 필터 — `min_evidence_count` / `min_depth` / `min_consistency` / `experience`(해당 provenance bucket 존재) / `evidence_last_seen_after` 류. 이유: need별 최소 요건이 다른데(experience need = 직접 경험 있는 유저만), 필터 없이 top-N을 받으면 게이트 탈락분만큼 실사용 후보가 줄고 **N등 밖의 요건 충족 후보는 회수 불가**다 — 대안이 overfetch뿐이라 비용 문제이기도 하다. 경계: **문턱값·조합 판정은 우리가 요청마다 보낸다** — persona에 maturity 같은 파생 판정을 요구하는 것이 아니라 원시 필드 비교만 요청한다(정책 소유권은 우리 쪽 유지). 필터는 pagination 안정성 계약(P10-①)과 함께 동작해야 한다.

### P2 🔴 Topic 카드 — 단건 조회 + union hydration batch

**왜.** 두 역할이 있다. ① rerank 판정("이게 정말 그 주제인가")과 추천 이유(reason) 생성에 topic의 **내용물**이 필요하다. (경험: grounding rerank의 판정 품질은 후보 payload의 정보량에 직접 비례했다 — v2 분석에서 `abstract`·`instance_of`를 잃는 것이 rerank 입력 손실이라 별도 복구 경로를 찾아야 했다.) ② **batch는 multi-channel hot path의 공식 hydration 단계다** — evidence/related 채널의 후보는 좌표만 갖고 유입되므로, union·dedupe(중복 제거) 후 살아남은 key들을 batch 1회로 `TopicCandidate` projection으로 보강한다 — P1 계약과 **같은 projection·같은 필드 의미**. 한 응답 안에서는 한 topic의 값들이 같은 추출 실행에서 나온 정합 상태여야 한다(vintage 값 동봉, P3-④) — 단 P1 검색 응답과 이 batch 사이의 시점 일치는 요구하지 않는다(최신 값 읽기, P10-⑦). 단건 GET은 디버깅·상세 표시용.

**무엇.**

```
GET  /{tenant}/persona/owners/{owner_id}/topics/{topic_id}      # 단건 → TopicCard (상세형)
POST /{tenant}/persona/topics/batch { keys: [{owner_id, topic_id}, ...] }
                                                                # hydration → TopicCandidate[] (P1과 동일 projection)
```

| 필드 | 의미 (요청하는 정의) | 용도 |
|---|---|---|
| `topic_id` | **불변 식별자** (계약 ① 좌표계) | join·캐시·decision log |
| `name` | generalized 이름 (현재 표기) | 표시·rerank |
| `aliases` | **관측** alias — 이 topic으로 병합/정규화된 과거 발화 표현들 (다른 언어 표현이 관측됐다면 포함) — cross-user 공개 가능하게 정제된 것만 (P10-⑤) | 검색 recall·동명이의 판별·rerank |
| `search_aliases` | **생성** alias — name 파생 다국어 번역·표기 변형 (P1 계약 ⑤). 유저 발화 유래가 아니므로 정제 부담이 다르다 | cross-lingual 검색 recall — "커피" 질의가 "coffee" topic을 찾는 경로 |
| `description` | 이 유저에게 이 topic이 무엇인지 1–3문장 — 위와 동일 정제 요건 | rerank 판정·reason 생성 |
| `keywords` 🟡 | 추출된 핵심어 (있다면) | 검색 대상 폭 확장 (P1 계약 ⑥) |
| `evidence_count`, `created_at`, `evidence_last_seen` 등 | P1 projection과 **같은 필드·같은 의미** (응답 내 정합 — 시점은 최신, P10-⑦) | 검증·디버깅 |

(subtopic/related 등 관계는 P7로 분리 — optional 필드가 아니라 별도 계약이다.)

**계약.**
1. **topic 식별자의 좌표계 확정**: 우리는 **`(owner_id, topic_id)` 복합 식별**을 전제로 요청한다 (topic은 유저별 독립 생성물이므로). persona 쪽이 tenant-전역 유일 id를 쓴다면 그것도 좋다 — 어느 쪽인지가 P5 scope·P6 similar·decision log 전부의 전제이므로 **양자택일을 계약 1번으로** 못박아 달라. 이 문서의 모든 route 스케치는 복합 식별 가정이다.
2. **생명주기**: persona 쪽에서 topic 병합·분할·개명이 일어난다면 **그때 id가 어떻게 되는지**(merge → 승계 id? redirect? tombstone — 삭제된 자리에 "여기 있었음" 표식만 남기는 방식?)를 계약으로. 우리 decision log는 topic 식별자를 영구 기록하므로, id가 조용히 재발급되면 감사 추적이 끊긴다.
3. `aliases`/`description`은 사적 대화 내용을 재구성할 수 있는 표면이다 — cross-user 응답에서의 정제 요건은 P10-⑤가 규정한다.
4. **batch의 부분 실패 계약** — hydration이 hot path가 된 만큼 필수다: 입력 key와 결과의 대응(입력 순서 보존 여부·중복 key 처리 명시), 한 key의 실패가 전체 batch를 죽이지 않을 것, 그리고 사라진 key의 **item별 outcome** — `ready` / `not_publishable` / `not_found` / `not_extracted`를 구분해서:

```json
{ "items": [
    { "key": {...}, "state": "ready", "topic": {...} },
    { "key": {...}, "state": "not_publishable" }
  ] }
```

   상태별 **소비자(우리) 행동까지 계약의 일부다**: `ready` = 사용 · `not_publishable` = 해당 후보만 제거하고 계속(철회 존중, 오류 아님) · `not_found` = 해당 후보만 제거하고 계속 — 유저별 상시 갱신 전제(§0.0-5)에서 검색과 조회 사이에 재추출이 끼는 것은 사고가 아니라 일상이고, run 중 후보 하나의 손실은 감수 가능한 피해다(P10-⑦) · `not_extracted` = 후보 제거하고 계속하되 decision log에 사유 기록(신규/미추출 유저 — 실패도 철회도 아니므로 지표에서 따로 센다).

### P3 🔴 (owner, topic) competence 등가물 — 게이트·정렬의 입력

**왜.** "이 주제로 대화해볼 만한 사람"의 실체는 *그 주제를 충분히 깊고 일관되게, 최근까지 다뤄온 사람*이다. 우리 게이트와 1차 정렬은 이 판정에 전적으로 의존한다. 대화에서 추출 가능한 형태로, 다음 세 축을 요청한다.

(표의 "우리 쪽 소비" 열은 현행 공식이다 — 우리는 이 공식들을 재설계할 수 있고, 잠그는 것은 축의 존재와 아래 ⚠·정의 블록의 **의미 요건**이다. 의미 요건은 공식과 무관하게 성립한다: 어떤 가중이든 consistency가 "생각을 바꾼 유저 페널티"면 안 되고, 어떤 정규화든 count가 extractor 분할 성향을 재면 안 되고, 어떤 decay든 시계가 실패 경로에 움직이면 안 된다.)

**무엇.** **P1 검색 결과(`TopicCandidate`)에 포함되는 것이 계약이다** (위치 확정 — N+1 방지). P2 카드에도 같은 값이 실린다.

| 필드 | 요청하는 정의 | 우리 쪽 소비 |
|---|---|---|
| ① `depth` (0–1) | 그 topic에서 유저 발화의 구체성/정교함 수준 | `maturity` 좌항 — **hard gate + 1차 정렬키(밴드)** |
| ① `consistency` (0–1) | **현재 active 주장 집합의 내부 정합성** (아래 ⚠ 참조) | `maturity` 우항 |
| ② `evidence_count` (int) | 현재 active 근거를 제공하는 **distinct source evidence unit 수** (아래 ⚠ 참조) | `evidence_strength` = n/(n+4) |
| ③ `evidence_last_seen` (timestamp) | **현재 active 근거 집합의 파생값** = max(said_at). 아래 정의 참조 | `freshness` 90일 반감기 |
| ④ `extraction_run_id`, `as_of`, `model_version` | 이 세 값이 나온 추출 실행의 식별 (아래 계약) | vintage 검증·decision log |
| ⑤ depth/consistency의 불확실성 — **필수** (형태는 택일: 축별 calibrated `confidence` / evidence coverage·sufficiency / 최소 `reliable\|insufficient\|unavailable` 상태) | 근거 1개에서 나온 depth 0.9와 장기간 여러 대화에서 나온 0.9를 동일 취급할 수 없다 — 어떤 새 구현이든 핵심 파생 신호에는 uncertainty가 붙어야 안전하다. `distinct_conversation_count`는 근거 분포를 보완할 뿐 **추출 모델 자체의 판정 불확실성은 대신하지 못한다** | gate/정렬의 안전 사용 전제 |

**⚠ ①-consistency의 정의가 gate의 의미를 결정한다.** "번복이 적을수록 높음"(시간 전체에 걸친 의견 불변성)으로 정의되면 **정상적인 의견 변화가 expertise 페널티**가 되고, 이 값은 hard gate에 들어가므로 생각을 바꾼 유저가 추천에서 구조적으로 배제된다. 우리는 **"현재 active 주장 집합의 내부 정합성"**(지금 서로 모순되는 주장을 동시에 갖고 있는가)으로 정의해줄 것을 권고하며, 어느 쪽 정의를 채택했는지를 계약 문서에 명시해달라고 요청한다.

**⚠ ②-evidence_count는 statement 수가 아니라 evidence unit 수여야 한다.** 추출 모델이 한 발화를 statement 1개로 자르느냐 5개로 자르느냐에 따라 값이 변하면, 우리는 유저의 근거량이 아니라 **extractor의 분할 성향**을 측정하게 된다 (이 값은 n/(n+4)로 정렬에 직결된다). 요청하는 정의: *현재 active 근거를 제공하는 distinct source evidence unit의 수 — 원 message id는 반환하지 않되 서버 내부에서 중복 제거한다.*

**③의 정의 — 이번 요청서에서 가장 공들여 합의하고 싶은 항목.** (경험: 우리는 v1부터 grounding 판정 시각을 evidence 시계로 오독해 freshness가 처음부터 틀린 입력을 읽고 있었고, 이를 v2 분석에서야 발견했다. 원인은 필드 이름·주석만 보고 **대입문** — 언제 갱신되는가 — 를 안 본 것이다. 그래서 이번엔 이름이 아니라 계산 규칙 자체를 계약으로 요청한다.)

**"갱신 이벤트"가 아니라 현재 active 근거 집합의 파생값으로 정의해달라:**

```
evidence_last_seen = max(said_at over currently-active qualifying evidence)
```

이 정의에서 따라 나오는 성질 — 이것들이 지켜지는지가 계약 검증 항목이다:

1. 최신 근거가 철회/삭제되면 값이 **그 이전 근거의 시각으로 뒤로 이동**한다. ("새 채택 시 갱신"만 잠그면 최신 근거를 지운 뒤에도 freshness가 높게 남는다 — 단조 증가 이벤트 의미론은 삭제 경로를 놓친다.)
2. active 근거가 전부 제거되면 **null**이 된다.
3. 새 근거가 없어도 supersede/삭제로 값이 재계산될 수 있다.
4. 추출 실패·아무것도 채택하지 않은 재평가는 값을 **바꾸지 않는다** (실패가 시계를 움직이면 v1의 `last_seen` 오류를 재생산하는 것이다).
5. `said_at`은 **persistence 시각이 아니라 발화 시각**: statement가 supersede 등으로 재저장되면 저장 시각은 갱신되지만 유저가 실제로 그 얘기를 한 시각은 아니다. (경험: memory-api v2도 같은 이유로 `Statement.created_at`을 recency에 쓰는 것을 자체 코드 주석으로 금지하고 있었다.)

이 정의에서 null은 "active 근거 없음" 단 하나를 뜻하게 된다 — "미계산"은 null이 아니라 ④의 `extraction_state`로 구분한다 (우리 쪽 decay는 null을 최대 패널티로 다루므로, 미계산이 null로 새면 정상 유저가 부당하게 가라앉는다).

**확장 축 (🟡 — "모든 것을 우선 요청" 단계이므로 함께 올린다).** topic은 지식만이 아니라 관심·의견·경험이 섞인 개념인데, 위 필수 축은 현행 competence(지식 중심)의 상속이다. 대화에서 추출 가능한 다음 축을 함께 요청한다 (전부 ④ vintage 계약 적용):

| 필드 | 의미 | 제품 근거 |
|---|---|---|
| `distinct_conversation_count` (또는 time-window coverage) | 근거가 몇 개의 서로 다른 대화/시기에서 나왔나 | **확장 축 중 최우선.** evidence 30개가 한 대화에서 나온 것과 6개월간 10개 대화에서 나온 것은 다른 사람이다 — `evidence_count`의 필수 보완이자 단일 대화 몰아치기에 대한 강건성 |
| `interest_strength` | 관심의 강도 | 지식은 얕아도 열의 높은 유저는 "함께 얘기할 상대"로 적합할 수 있다 — depth와 독립 축 |
| `knowledge_breadth` | topic의 여러 측면을 다룬 정도 | coverage 판정 보조 |
| `engagement_frequency` | 얼마나 자주 이야기하는가 | 최근성과 별개의 활성도 |
| `first_seen` | 최초 근거 시각 | `evidence_last_seen`과 쌍 — 관심의 지속 기간 |
| `trend` | 증가/유지/감소 | "요즘 빠져 있는" vs "예전에 했던" 구분 |
| `discussion_willingness` | "이 주제로 다른 사람과 얘기하고 싶다"는 명시/암시 신호 — 추출 가능하다면 | 추천 수락률에 직결되는, 대화만이 줄 수 있는 신호 |

확장 축의 **필드명은 지금 잠그지 않는다** — 다만 의미의 미정 지점을 persona 팀이 정의하도록 질문으로 보낸다(§4 Q10): frequency/trend의 기준 time window, interest가 발화량인지 명시 선호인지, willingness가 명시 발화와 추론을 구분하는지.

**계약.** ①②③이 같은 추출 실행에서 나온 값(동일 vintage)이어야 하며, **이를 산문이 아니라 값으로 검증 가능하게** ④(`extraction_run_id`/`as_of`/`model_version`)를 같은 projection에 실어달라. depth는 지난주 값, count는 오늘 값이 섞이면 gate와 정렬이 서로 다른 세계를 보는데, run_id가 있으면 우리가 이를 assert할 수 있다.

### P4 🟡 Experience provenance — "해본 사람" 신호

**왜.** "이 주제를 *실제로 겪어본* 사람과 대화하고 싶다"는 need(experience)는 depth와 다른 축이다 — 책으로 깊이 아는 사람 ≠ 직접 해본 사람. 우리 계약에는 이 자리가 처음부터 있었지만(`experience_source_type`/`experience_specificity`) **채워줄 상류가 지금까지 없어서 experience need가 사실상 depth의 변형으로 퇴화해 있었다.** 대화는 이 신호의 가장 좋은 소스다: "제가 해봤는데요"와 "책에서 봤는데요"는 발화에서 구분 가능하다.

**무엇.** (owner, topic) 단위, **P1 projection에 포함**. 현행 계약을 복제한 단일 enum(`firsthand | secondhand | null`)은 요청하지 않는다 — 같은 주제에 대해 직접 운영 경험과 책·강의 학습을 *동시에* 가진 유저가 정상이고, 단일 enum은 어느 하나가 다른 하나의 근거를 지워버린다. **provenance별 집계**(유래별로 나눈 구획 — 아래 표의 bucket)로 요청한다:

```json
"experience": {
  "firsthand":  { "evidence_count": 5, "specificity": 0.86, "confidence": 0.91, "last_seen": "..." },
  "secondhand": { "evidence_count": 8, "specificity": 0.64, "confidence": 0.88, "last_seen": "..." }
}
```

| bucket 내 필드 | 의미 |
|---|---|
| `evidence_count` | 해당 provenance의 근거 unit 수 (P3-② dedup 규칙 동일) |
| `specificity` (0–1) | 경험 발화의 구체성 (일화·수치·고유 상황 포함 정도) |
| `confidence` | provenance 판정의 추출 confidence |
| `last_seen` | 해당 provenance 근거의 최신 발화 시각 (P3-③ 파생 규칙 동일) |
| `breadth` 🟡 | 서로 다른 경험 상황/기간의 수 |

**계약.** ① bucket은 해당 provenance의 active 근거가 있을 때만 존재한다 — 기존의 "null ↔ specificity 동반" 불변식은 *bucket 부재 = 필드 전무*라는 bucket 단위 규약으로 대체된다 (근거 없는 bucket에 specificity만 있는 상태는 불가). ② 근거량·최근성이 bucket별로 있는 이유: 상위 라벨만으로는 **한 번의 모호한 "해봤다"와 반복된 구체 경험을 구분하지 못한다** — experience need가 depth와 독립 축이 되려면 경험 자체에 근거량·최근성·다양성이 필요하다.

### P5 🔴 Evidence 검색 — 후보 발견층과 본문층

**왜.** "이 주장에 찬성/반대하는 사람과 얘기해보고 싶다"를 서빙하려면, 저장된 stance 라벨이 아니라 **질의 시점의 명제에 대해** 각 유저의 실제 발언을 모아 판정해야 한다. 이것은 현행 구현의 유산이 아니라 문제 자체의 성질이다 — 같은 topic이라도 명제가 다르면 stance가 다르므로("원격근무" topic에서 "생산성에 좋다"와 "신입 육성에 좋다"는 별개 명제), stance를 미리 저장하는 어떤 설계도 명제 공간을 다 커버할 수 없다. 그래서 재구현하더라도 query-time 판정은 유지되고, 그 judge의 입력이 이 검색 결과다.

그리고 evidence 검색은 판정 근거이기만 한 것이 아니라 **후보 회수 채널**이기도 하다 (P1의 union 구조). 후보만 필요한 시점과 본문 텍스트가 필요한 시점은 privacy·비용 프로파일이 다르므로 **두 층으로 요청한다**.

**무엇 — 층 1: 후보 발견 (cross-user, 본문 없음).** topic 순위와 무관하게 "이 명제/경험에 관해 말한 적 있는 유저"를 회수한다:

```
POST /{tenant}/persona/evidence/search
{
  "queries": ["...", ...],           # 또는 "proposition": "..."
  "kinds": ["claim", "experience"],  # 회수 채널 선택 (stance/experience/orthogonal용)
  "limit": 200,
  "per_owner_limit": 5
}
→ { "items": [
      { "statement_id": "opaque-id", "owner_id": "...", "topic_id": "...",
        "kind": "claim", "epistemic": "asserted", "said_at": "...",
        "matched_query_indices": [0, 2] }
    ] }                                # text 없음 — 좌표 + 식별자
```

**발견층 hit에 `statement_id`가 있어야 두 층이 연결된다.** 좌표(owner, topic)만 반환하고 본문층이 같은 query로 재검색하면, per_owner_limit·인덱스 변경 때문에 **발견층에서 잡힌 evidence가 본문층에서 돌아온다는 보장이 없다** — 후보로 회수한 이유와 실제 judge 입력이 달라지고, decision log가 "무엇을 발견해서 이 후보를 넣었는가"를 기록할 수 없다. 그래서 본문층에는 재검색과 별도로 **ID batch fetch**가 필요하다:

```
POST /{tenant}/persona/statements/batch
{ "statement_ids": ["..."] }
→ { "items": [
      { "statement_id": "...", "state": "ready", "statement": { ...층 2와 동일 필드 (text 포함) } },
      { "statement_id": "...", "state": "not_publishable" }
    ] }
```

부분 실패 계약은 P2 계약 ④와 동일(입력 ID별 outcome·대응 규칙·부분 결과·`not_found`는 해당 항목만 제거하고 계속). 유저별 상시 갱신(§0.0-5)에서 발견층과 이 fetch 사이에 그 유저의 재추출이 끼면 ID가 사라질 수 있고 그것은 정상 경로다. 🟡 다만 **재추출 후에도 같은 발언이 같은 `statement_id`를 유지**하면 이 손실 창 자체가 줄어든다 — 요구가 아니라 있으면 좋은 성질로 전달한다. 발견분의 정확한 fetch는 이 batch가 담당하고, 아래의 scoped search는 shortlist에 대한 **추가** evidence 채움 용도로 유지한다.

- text를 싣지 않으므로 본문층보다 노출 표면이 좁다 — 단 owner/topic/kind/said_at 좌표 자체도 민감 정보다: 요청하는 것은 **같은 publishability·동의 경계 안에서의 더 작은 projection**이지, 더 낮은 privacy 등급이 아니다 (§4 Q8).
- **명제↔발언의 어휘 격차가 이 층의 최대 recall 위험이다.** vector-free 전제에서 1차 대응은 우리의 의견 어휘 bag expansion이지만, expansion에도 한계가 있다 — persona가 언젠가 semantic 검색에 투자한다면 **topic 검색보다 이 층이 먼저**라고 본다 (§4 Q4). 그때까지의 방어선은 statement의 검색 대상 텍스트를 충실히 하는 것과 P11 recall 측정이다.
- orthogonal viewpoint 회수의 재료가 이 층이다 (§0 용어 주의): kind·epistemic(단정/추측/인용 같은, 발언의 인식적 성격) 분류가 있으면 "같은 명제, 다른 논점"의 후보를 저장 라벨 없이 회수할 수 있다.

**무엇 — 층 2: 본문 fetch (scoped).** union으로 확정된 shortlist에 대해서만:

```
POST /{tenant}/persona/statements/search
{
  "scopes": [                        # 권한·비용 경계가 이 필드 하나 — 채널 union 결과에서 확보한 쌍으로 구성
    {"owner_id": "A", "topic_ids": ["T1", "T2"]},
    {"owner_id": "B", "topic_ids": ["T9"]}
  ],
  "queries": ["...", ...],           # 의견 어휘 bag, ANY-match
  "per_owner_limit": 10
}
→ owner별 그룹: [{ owner_id, statements: [
     { statement_id, text, said_at, topic_id, kind, confidence } ] }]
```

응답 statement의 최소 필드:

| 필드 | 요건 |
|---|---|
| `statement_id` | **불변 opaque 식별자** — 원 message id가 아니고 역산 불가라, 유저 경계를 넘어 전달·기록해도 원 대화 좌표가 새지 않는다. 없으면 우리 decision log가 "어느 근거로 판정했는가"를 남길 수 없고, 삭제·철회 전파(P10-④)를 검증할 수도 없다. 우리 edge 계약의 `evidence_refs` 자리가 이 id를 담는다 |
| `text` | 계약 ④ — 추출된 근거문, 주장의 방향·강도 보존 |
| `said_at` | **발화 시각** (P3-③ 성질 5와 동일 근거) |
| `topic_id` | scope 내 어느 topic에 걸렸는지 |
| `kind` | **enum 값과 의미를 계약 문서에 명시** (주장/선호/경험담 등 — judge 프롬프트가 kind별로 가중을 달리할 수 있어야 한다) |
| `epistemic` 🟡 | 발언의 인식적 성격 (단정/추측/인용/과거 의견 등) — stance 판정의 강도와 orthogonal 논점 분류에 쓰인다 |
| `confidence` | 추출 confidence |

**계약.**
1. **scope는 단일 필드**: 이전 초안은 `topic_scope`(쌍 목록)와 `owner_ids`를 이중으로 받았는데, 그러면 어느 필드가 권한·비용 경계인지 불명확하다. `scopes` 하나로 통합 — owner 집합은 `scopes`의 owner들로 유도되고, **scope 밖 검색은 없다** (경험: shortlist 밖 전역 검색은 privacy 경계이기도 하고 비용 폭주 경로이기도 하다). 좌표계는 P2 계약 ① 전제.
2. **공개 topic 소속의 active 발언만 반환한다는 보장** — 발언의 공개성은 소속 topic의 공개 여부를 승계한다(§0.0-6·P10-④). 검색과 **ID batch fetch 양쪽 모두**, 발견층(층 1)과 본문층(층 2) **모두** 동일하다 — 비공개 topic의 발언이 발언 검색 경로로 새면 topic 단위 공개 결정이 무의미해진다. batch에서 비공개 전환분은 P2 계약 ④와 같은 item별 `not_publishable`로 (opaque id를 알고 있다는 것이 읽을 권리가 아니다 — privacy 검사는 read-time 최신, P10-⑦).
3. `per_owner_limit` 필수 — 비용 상한(cost cap)이지 overfetch(필요분보다 넉넉히 미리 가져오기)가 아니다.
4. **`text`의 정의를 계약으로**: `text`는 최종 유저에게 노출되지 않는다(§0.0-7 — 추천 이유는 요약·부연만, 원문 인용 배제). 따라서 노출용 정제는 요구하지 않고, 요건은 둘이다: ① 원 대화 전문이 아니라 **추출된 근거문**이면 충분하다 — 원 message id·conversation 좌표 등 원문 provenance는 응답에 포함하지 않는다(경계를 필요 이상 넓히지 않음, P10-⑤), ② 추출·요약 과정에서 **주장의 방향과 강도는 보존** (stance judge의 입력이므로 중립화 과정에서 stance가 뭉개지면 판정 자체가 불가능해진다). `statement_id`는 decision log의 대체 식별자로서 반드시 필요하다.
5. 🟡 **semantic 검색 지원** — vector-free 전제에서 필수 요청은 아니다. 단 persona가 semantic 투자를 하게 되면 우선순위는 층 1(명제↔발언 격차) > topic 검색이라는 의견을 전달한다 (§4 Q4).
6. 🟡 **동일 owner 내 논점 중복 제거 옵션** (`distinct_viewpoints` 류) — 한 유저가 같은 논점을 20번 말한 것과 서로 다른 논점 5개를 말한 것을 구분해 fetch할 수 있으면 judge 입력의 정보 밀도가 오른다. orthogonal 판정의 재료이기도 하다.
7. ⚪ (judge 비용 절감용, 추후) (owner, topic)별 **의견 요약 1–2문장** — judge 입력을 원문 N개에서 요약+대표발언으로 줄일 수 있다 (경험: judge 입력 감축이 per_owner 40→10으로 유의미한 비용 차이를 만들었다). evidence 간 batch similarity도 같은 ⚪ 층.

### P6 🔴 파편화 대응 — "같은 주제" 판정의 소유권

**왜.** 이 전환의 최대 리스크다. "머신러닝을 아는 유저 전부"를 못 모으면 추천 pool 자체가 새는 것이고, 반대로 과병합하면 엉뚱한 사람이 추천된다. 이 판정을 **누가 소유하는가**를 지금 정해야 한다. 두 가지 형태 중 하나(또는 둘 다)를 요청한다:

- **A안 — persona가 canonical topic space를 만든다**: 유저별 topic 위에 cross-user cluster id(canonical topic)를 부여. 우리는 cluster id로 exact join을 회복한다. 우리에게 가장 좋지만 persona 쪽 부담이 크고, 병합 오류가 생기면 우리가 개별 복구할 수 없다.
- **B안 — 판정은 우리가, 재료는 persona가**: "같은 주제" 판정(임계값·rerank)을 Discovery가 소유한다. vector-free 전제에서 primitive는 별도 endpoint가 아니라 **P1 텍스트 검색의 agentic 반복 호출**이다 — 찾은 topic의 `aliases`·`description`을 다음 query 재료로 되먹여 파편들을 회수한다. persona에 요구되는 것은 그 재료의 충실함(P2 필드·P1 계약 ⑥)이다.

**우리 권고: B를 기본으로, A를 로드맵으로.** agentic search 전제라면 B가 우리 파이프라인과 자연스럽고, A는 persona 쪽 클러스터링 품질이 검증된 뒤에 얹는 게 안전하다. **A의 필드 자리를 지금 예약하지는 않는다** — canonicalization의 생성·merge·split·version 의미가 확정되지 않은 상태의 예약 필드는, "예약 hook은 같은 질문이 유지될 때만 additive"라는 우리 자신의 교훈에 걸린다. 대신 로드맵 질문(§4 Q3)으로만 남긴다.

🟡 **선택적 최적화 — `/topics/similar`**: persona가 (독립적 이유로) 재사용 가능한 topic representation을 갖게 되면, 반복 텍스트 검색을 한 번의 이웃 조회로 대체할 수 있다:

```
POST /{tenant}/persona/topics/similar
{ "source": {"owner_id": "...", "topic_id": "..."}, "limit": 50, "per_owner_limit": 3 }
→ { items: [TopicCandidate] }                     # P1과 같은 projection
```

이 경우의 계약: 순서 제공 + score는 version-scoped optional(P1 계약 ②와 동일), cross-user 기본, per_owner_limit, 결정적 순서(P10-①).

### P7 🔴 Topic 관계 계약 — coverage·sparse 확장의 대체

**왜.** 현행 파이프라인에서 QID는 join key만이 아니라 **구조**였다. 두 기능이 그 구조에 얹혀 있다:

1. **coverage need**: "한 주제의 여러 갈래를 고루 아는 pool"을 만들 때, 후보를 facet(현행: edge가 놓인 QID)별로 그룹핑해 round-robin으로 갈래당 한 명씩 뽑는다. facet id가 없으면 coverage는 그룹핑할 축 자체가 없다.
2. **sparse 확장**: 직접 edge가 부족한 주제에서 knowledge graph의 인접 QID로 pool을 넓힌다. 관계 그래프가 없으면 sparse 주제는 그냥 빈 추천이 된다.

QID·KG가 사라지면 이 둘이 같이 사라진다. P2의 optional 필드가 아니라 **별도 계약**으로 요청한다.

**facet 분할의 소유권 — 이 요청서의 결정 사항.** 유저별 topic처럼 **facet도 독립 생성물**이다: Jin의 "배포 자동화"와 Mina의 "CI/CD 운영"은 같은 갈래지만 같은 id일 수 없다. owner-local facet id는 cross-owner coverage 그룹핑에 못 쓰고, cross-owner에서 통하는 facet id를 요구하는 순간 그것은 **canonical facet space** — P6에서 로드맵으로 미룬 A안과 같은 전역 정규화를 뒷문으로 요구하는 것이다. 그래서 안정적 facet_id 요청은 **철회**하고 소유권을 이렇게 정한다:

> **주제 내 다양성 확보는 Discovery가 query-time에 소유한다.** 매 요청에서 채널 union이 모은 `TopicCandidate` pool 위에서 우리가 그 자리에서 판정한다 — 구현은 현행처럼 갈래 분류 후 round-robin일 수도 있고, facet 개념 없이 **semantic diversity 최적화**일 수도 있다. vector-free 전제에서의 기본 계획: **후보 20–50개의 name+description+관계를 LLM batch 1회에 넣어 "같은 갈래끼리 묶고 서로 다른 갈래를 표시"** — 후보마다 호출하거나 전 pair를 비교할 필요가 없다. persona에게 요청하는 것은 판정 **재료**(관계·설명문)뿐이다. P6에서 "같은 주제" 판정을 우리가 소유(B안)하기로 한 것과 같은 원칙이고, canonical facet space는 canonical topic space와 **같은 로드맵 질문**(§4 Q3)이다.

트레이드오프를 알고 선택한다: query-time 판정은 요청마다 비용이 들고 동일 요청 간 경계가 완전히 결정적이지 않다. 그래도 미확정 전역 정규화에 지금 의존하는 것보다 낫다 — coverage 품질이 persona 클러스터링의 미래 품질에 인질로 잡히지 않는다.

**무엇.** topic 간 관계를 조회 가능한 형태로:

| 항목 | 요청 |
|---|---|
| 관계 종류 | 최소 `subtopic_of` / `related` 2종. ⚪ `contrasting`(대비 관점)은 orthogonal need의 미래 입력으로 어휘에 자리만 |
| 관계 메타 | 관계별 `confidence` + `extraction_run_id`/`model_version` (P3-④와 같은 이유) |
| related 확장 | sparse 주제에서 "인접 topic을 아는 다른 유저들"로 pool을 넓히는 경로 — related 관계 기반 검색이 P1에 얹히는지, 별도 endpoint인지는 persona 팀 설계에 맡기되 **가능해야 한다는 요건**은 계약으로 |
| batch similarity 🟡 (조건부) | 필수 요청이 아니다 — 표현 공간이 없는 persona에게 similarity matrix를 요구하는 것은 우리 coverage를 위해 새 semantic subsystem을 만들라는 요청이 된다(vector-free 전제). 다양성 판정의 기본 계획은 위의 LLM batch 1회다. 요청은 capability 형태로만: *"재사용 가능한 topic representation을 갖게 된다면 후보 집합의 semantic redundancy/diversity를 batch로 평가할 primitive(matrix든 sparse 이웃이든)를 제공할 수 있는가?"* **제공된다면 행동을 결정하는 값이므로 안정 의미 계약 필수**: 값 범위·방향, 대칭성, self-similarity 규약, 누락/비공개/삭제 key 표현, 입력 순서↔좌표 대응, 판본 선언(P10-③), cross-language 동작, version 간 비교 불가 명시, 동일 version 내 calibration 또는 threshold 권고. embedding 자체의 wire 노출은 요청하지 않는다 |

**계약.**
1. 관계는 유저별 topic 위에 걸리므로 (owner, topic) 좌표계(P2-①)를 따른다.
2. **P6 similar와 P7 related는 다른 것이고, 이 구분이 계약이어야 한다**: similar = *같은 주제의 다른 표현* (파편 병합 후보 — pool에 합류), related = *인접한 다른 주제* (확장 후보 — sparse일 때만, `via` 표시와 함께 합류). 두 API의 의미가 겹치면 같은 topic이 병합 경로와 확장 경로로 두 번 들어오는 중복 확장이 생긴다. (현행 코드도 direct edge와 neighbor 유입을 `via`로 구분하고 direct가 선점한다 — 같은 구분이 topic 세계에도 필요하다.)
3. orthogonal의 **판정 설계**는 추후다 — 단 P7이 예약하는 것은 *contrasting topic* 관계 어휘(⚪)뿐이고, *orthogonal viewpoint*(같은 명제·다른 논점)의 회수 재료는 P5(층 1의 kind·epistemic·semantic 검색, 층 2의 논점 중복 제거)가 **지금** 확보한다. 저장된 orthogonal 라벨은 어느 쪽에서도 요청하지 않는다.

### P8 상태·실패 구분 — 빈 것과 없는 것 (서비스 상태 🔴 · owner별 상태 🟡)

**왜.** (경험: memory-api v2 dev에서 코퍼스가 안 만들어진 상태가 `200 {items:[], total:0}`으로 왔고, 우리 파이프라인은 이를 "후보 0개"로 읽어 호출자에게 **422 — 당신의 요청이 grounding에 실패했다**를 돌려줬다. 상류 데이터 부재가 호출자 탓으로 귀속된 것이다. 이걸 사후에 배포 preflight(배포 전 사전 점검)로 막아야 했다.) 새 환경 배포·인덱스 재구축·추출 파이프라인 장애 같은 **서비스 수준 부재**를 "후보 0개"로 오독하지 않기 위한 표면이다. 추천 hot path가 아니라 **배포 preflight·장애 진단**용이다.

**무엇.**

1. 🔴 **서비스/코퍼스 상태**: `GET /{tenant}/persona/status` — 우리 배포 preflight와 degradation 판단(상류가 준비 안 됐을 때 기능을 줄여 계속 동작할지의 판단; 주기 갱신 캐시로 소비 — 요청마다 호출하지 않는다)이 본다:

```json
{ "source_owner_count": 1500,        # 대화 데이터가 존재하는 owner 수
  "extracted_owner_count": 1234,     # 추출이 완료된 owner 수
  "publishable_owner_count": 1180,   # 공개 topic을 1개 이상 가진 owner 수
  "publishable_topic_count": 8400,   # 공개 topic 총수 — 기본 비공개 모델에서 추천 pool의 상한 관측용 (§0.0-6)
  "conversation_watermark": "2026-08-13T02:00:00Z",     # 어느 시점 대화까지 반영됐나
  "indexes": { "topics": "ready", "statements": "ready", "hexaco": "building" } }
```

2. 🟡 **owner별 상태 — 진단용 (파이프라인 비호출)**: 추천 파이프라인에는 이 조회를 부를 지점이 없다 — 후보는 검색으로 유입되고, 검색에 안 잡힌 유저는 추천이 안 될 뿐이며, 기본 비공개 모델(§0.0-6)에서 pending 유저와 "공개 topic 0개" 유저는 우리 행동상 동일하다(둘 다 검색 비노출·부정 결과 캐시 없음 → 영구 배제 메커니즘 없음). 파이프라인이 필요로 하던 것은 batch item별 `not_extracted`(P2-④)와 "갱신 중 기존 값 서빙"(P10-⑦-(c))으로 이미 확보됐다. 남는 용도 둘: **"이 유저는 왜 추천이 안 되나" 진단**(지원·디버깅), 그리고 **P9가 위임한 진행 상태(pending/failed) enum의 좌석**. topic은 ready인데 statement 인덱스나 HEXACO는 pending일 수 있으므로 데이터 종류별로:

```json
{ "owner_id": "...",
  "topics":     {"state": "ready",   "as_of": "..."},
  "statements": {"state": "pending"},
  "hexaco":     {"state": "none"} }
```

P1/P6의 `TopicCandidate`에는 해당 데이터 종류의 `extraction_state`/`as_of`만 싣고, 전체 상태는 이 조회로.

**계약.** "이 유저는 topic이 0개다(ready, 정상)"와 "이 유저는 아직 추출이 안 됐다(pending)"가 **wire에서 구분**되기만 하면 형태는 무엇이든 좋다 — 이 구분은 endpoint 등급과 무관한 **상태값의 의미 계약**이고, 이 상태가 나타나는 모든 자리(owner별 조회·batch item state)에 동일 적용된다. 그리고 유저별 상시 갱신 전제에서 `pending`은 **최초 추출 전에만** 쓰여야 한다 — 이미 데이터가 있는 유저의 주기 갱신 중에는 `ready` 유지 + 기존 값 서빙(§0.0-5·P10-⑦-(c))이며, 갱신마다 pending으로 돌아가면 그 유저가 주기적으로 추천에서 증발한다.

### P9 🟡 HEXACO + InteractionStyle — 지금은 계약 예약, 소비는 추후

**왜.** "특정 주제 없이 성격이 맞는 유저 추천"은 추후 surface다. 정확한 현재 상태: 우리 쪽에 optional persona provider의 **접합부(seam — 구현을 갈아 끼울 수 있게 만들어 둔 경계)는 존재**하지만(gate가 agent별 단건 호출, None 허용·degradable — 없으면 그 신호 없이 계속 동작), 현행 `PersonaPrior` v0에는 HEXACO 축이 없고(`prior_stance`/`stable_traits`/`expertise_claims`뿐, agent 좌표계) 랭킹은 이를 **밴드 내 tiebreak로만** 소비한다(hollow guard — 밴드 승격 불가). 따라서 **HEXACO wire model·요청자↔후보 pair 비교·batch provider·ranking objective는 전부 신규 설계**다 — "배선이 싸다"가 아니라 "붙일 seam이 있다"가 맞는 서술이다. 지금 요청하는 것은 그 설계의 원자료 계약이다.

서빙 의미(확정 전제 §0.0-3): 타 유저의 agent는 주인의 HEXACO를 모방해 응답하므로, "성격이 맞는 상대 추천"의 비교 축은 **유저 HEXACO 쌍**(요청 유저 ↔ 후보 유저)이고 추천되는 실체는 후보 유저의 agent다. 즉 우리는 매 요청에서 **요청 유저 본인 + 후보 shortlist 전원**의 HEXACO가 필요하다.

**무엇.**

```
GET  /{tenant}/persona/owners/{owner_id}/hexaco
POST /{tenant}/persona/hexaco/batch { owner_ids: [...] }     # shortlist 비교용 — 단건 N회 왕복 방지
→ { axes: {H,E,X,A,C,O: 0–1}, facets: {...}?,
    confidence: {축/facet별 0–1 또는 evidence_count},
    state: "ready" | "insufficient" | "none",
    model_version: "...", extraction_run_id: "...", as_of: timestamp }
```

**InteractionStyle — HEXACO와 별도 축으로 함께 요청한다.** HEXACO는 성격 모델이지 "이 agent와 대화가 잘 맞는가"의 직접 신호가 아니다. 대화에서 현실적으로 추출 가능하고, agent가 owner의 대화 방식을 모방한다는 제품 전제(§0.0-3)에 오히려 더 가까운 특성들이 있다: directness · verbosity · formality · warmth/empathy · assertiveness · challenge/debate tolerance · conflict style · uncertainty tolerance · 선호 언어·답변 길이 · 질문/설명 성향. 이들은 성격의 *추정*이 아니라 대화 행동의 *관측*이라 추출 신뢰도도 높을 것으로 기대한다.

단 이 특성들은 **맥락 의존적일 수 있다** — directness·formality·verbosity는 고정 성격이라기보다 언어·상대·topic에 따라 달라진다. 그래서 owner당 단일 scalar shape로 지금 잠그지 않고, 표현 방식을 persona 팀이 제안하도록 질문한다(§4 Q9): global baseline인지, 언어별 값인지, context별 분산/범위를 함께 주는지, 최근 행동 가중이 있는지.

```
GET /{tenant}/persona/owners/{owner_id}/interaction-style     # + batch (HEXACO와 동일 형태)
→ { traits: {directness: ..., verbosity: ..., ...},
    confidence: {...}, state, model_version, extraction_run_id, as_of }
```

**계약.** (HEXACO·InteractionStyle 공통)
1. **축별(가능하면 facet별) confidence 또는 근거량** — 대화 3turn짜리 유저의 HEXACO와 3천turn 유저의 HEXACO는 신뢰도가 다르다. 점수만 오면 우리가 이를 구분할 수 없다.
2. **`none`과 `insufficient`의 구분** (wire enum과 동일 용어) — 추출 자체가 없는 것(`none`)과 대화량이 부족해 판정 불가한 것(`insufficient`)은 다르게 다뤄야 한다 (P8과 같은 원리). `pending`/`failed`는 이 응답의 enum이 아니라 **P8의 owner 상태 조회에만 존재**한다 — 진행 상태와 판정 결과를 한 enum에 섞지 않는다.
3. `model_version` + `extraction_run_id` 필수 — 추출 모델이 바뀌면 전 유저 점수가 일제히 이동한다. 버전 없이 시계열 비교하면 유저가 변한 것처럼 보인다.
4. `as_of` — P3-③과 같은 이유.
5. **노출·사용 동의 정책** — HEXACO는 성격 프로파일이라 topic보다 민감하다. 유저가 자신의 HEXACO가 매칭에 쓰이는 것에 동의했는지를 persona 쪽이 어느 층에서 보장하는지 계약에 명시 (P10-④의 특수 사례).
6. ⚪ 매칭 함수(어떤 HEXACO 조합이 "잘 맞는" 것인가)는 **자동으로 성립하는 가정이 아니다** — 유사성이 좋은 축과 상보성이 좋은 축이 다를 수 있다. 별도 product/eval 문제로 명시하고, topic 추천 tie-break 활용도 **실험 전 가정**으로만 둔다. 지금은 원자료 계약만. (모방 충실도 — agent가 주인 HEXACO를 얼마나 잘 재현하는가 — 는 persona 팀 소관 품질 지표로 보고 이 요청서 범위 밖에 둔다.)

### P10 🔴 운영 계약 — 모든 endpoint 공통

전부 v1→v2 이행에서 실제로 문제가 됐던 것들이다. 개별 endpoint보다 이 공통 계약의 합의가 더 오래 간다.

1. **Pagination — 조회 성격별로 다르게**:
   - *inventory/batch 조회* (owner의 topic 목록 등): `{items, limit, offset, total, truncated}` — `total`은 정확값, 정렬은 결정적(동률 시 안정 tiebreak 명시). (경험: v2 `entities_grounded_to`는 offset 하드코딩·total 폐기 상태였고 이를 사후 요청으로 복구해야 했다.)
   - *ranked 검색* (P1/P5/P6): exact total을 요구하지 않는다 — ranked text 검색에서 total은 행동을 바꾸지 않고, 필요한 것은 **pagination 진행 중의 결과 안정성**뿐이다. `limit` + `next_cursor`(또는 `truncated`), 그리고 같은 질의의 **결정적 순서**(동률 시 안정 tiebreak). 코퍼스가 상시 갱신되므로(§0.0-5) cursor 진행 중의 완전한 순서 고정은 요구하지 않는다 — 중복·누락을 최소화하는 cursor/search-after면 충분하다.
2. **Null 규약**: `null` 직렬화 vs 키 부재 vs 필드별 의미("없음"/"미계산")를 계약 문서에 명시. (경험: ExcludeNoneRoute + null 의미 미정의 조합이 두 번의 오독을 만들었다.)
3. **버전 선언**: 응답에 `extraction_run_id`/`model_version`(+`as_of`). 우리 decision log는 provider version을 필수 기록하며 "provider 종류에서 버전을 추론하지 않는다"가 규율이다 — 상류가 버전을 선언해줘야 이 기록이 참이 된다.
4. **노출 제어 — 결정 단위는 topic (제품 확정, §0.0-6)**: 유저가 topic별로 공개 여부를 결정하고 기본은 비공개다. owner 단위 노출은 "모든 topic 비공개"의 파생이고, 발언의 공개성은 소속 topic을 승계하는 파생값이다 — 발언 단위 독립 제어는 요청하지 않는다. 계약 요청:
   - persona API는 **명시적으로 공개된 topic과 그 소속 발언만** 반환한다 — 응답 전 필터링 (우리에게 도달한 것은 공개분뿐). topic 검색·batch·발언 검색·본문 fetch **전 표면 동일**.
   - **삭제·철회·공개↔비공개 전환의 전파 시점** 명시 (즉시? 다음 갱신 주기?). 유저가 지운 대화의 흔적이 추천 이유로 계속 나오면 안 된다. 특히 공개 플래그는 topic에 살지만 발언 검색은 statement 인덱스를 타므로, **전환이 양쪽 인덱스에 함께 반영**돼야 한다 (P10-⑦-(b)).
   - 요청 body에 **requester owner 사전 제외**(self-exclusion) 지원 여부 — 지원되면 좋지만, **우리 downstream self-exclusion은 그와 무관하게 계속 강제**한다 (defense in depth — 같은 보호를 여러 층에 겹쳐 두는 다층 방어).
   - 우리 계약에는 privacy-owned `discoverable` 자리가 이미 있다 — persona 필터링과 이중이어도 유지한다.
5. **Cross-user 응답은 전용 최소 projection으로**: owner 본인용 응답 모델을 cross-user 조회에 재사용하지 말 것. (경험: v1 personal entity의 본인용 모델에는 서사적 필드가 있어 cross-owner로 나가면 과노출이었고, 전용 최소 shape를 별도 요청해야 했다.) P1의 `TopicCandidate` 필드 목록이 그 최소 shape 제안이고, **`aliases`/`description`(공개 topic의 표시 표면 — 추천 이유에 나갈 수 있다)은 노출 가능하게 정제된 값만, 원 message id·conversation 좌표는 반환 금지, 대체 식별자는 opaque `statement_id`**가 요건이다. statement `text`는 최종 유저에게 노출되지 않으므로(§0.0-7) 노출용 정제 대상이 아니다 — 요건은 P5-④.
6. **빈 결과 ≠ 이용 불가**: P8과 동일 — 모든 endpoint에서 일관되게.
7. **읽기 모델 — 각 호출은 최신 값을 읽는다. snapshot pinning(한 번의 추천 처리 — 이하 run — 가 도는 동안 읽는 데이터 판본을 하나로 고정하는 것)은 요청하지 않는다.** 근거 둘: ① persona는 batch release가 아니라 유저별 상시 증분 갱신(§0.0-5)이라, 전역 시점 고정 요구는 release 경계가 없는 저장 모델에 다중 버전 보존(MVCC류)을 우리 편의로 강제하는 것이 된다 — "의미를 잠그고 구현을 잠그지 않는다"는 이 문서의 잠금 원칙 위반. ② run 중 어긋남의 실제 피해는 "후보 하나가 판정에서 빠지거나 순위가 약간 달라짐"이 전부다 — 추천은 유일 정답 조회가 아니고, 소비 시점(추천받은 유저가 실제로 대화 시작)에는 어차피 다음 갱신이 반영된 세계이며, run 자체가 초 단위다. pinning이 막던 것을 대체하는 계약:
   - (a) **각 단계는 그 시점의 최신 값을 읽고, 처리 중 사라진 key는 item별 명시 상태로 돌아온다** — `not_found`(재추출 등으로 소멸)·`not_publishable`(비공개 전환). 우리는 어느 쪽이든 **그 후보만 제거하고 계속** 진행한다 (P2-④·P5 batch).
   - (b) **모든 중간 상태는 유효한 상태여야 한다** — 이것이 시점 고정을 대체하는 실제 요건이다. 두 조항으로 나뉜다:
     - *기존 topic에의 evidence 증분 반영*: 언제 읽어도 "조금 덜 최신일 뿐인 유효한 프로필"이므로 아무 요구가 없다 — 최신 값 그대로.
     - *신규 topic*: 생성 중인 topic이 미완성 집계값으로 노출되는 문제(절반 처리된 depth/consistency로 P1 `filters`가 오판, 부분 증거로 stance 판정)는 **기본 비공개 + 명시적 공개 모델(§0.0-6)이 구조적으로 막는다** — 유저가 공개를 켜는 시점에는 최초 추출이 끝나 있다. 남는 요건은 한 줄: **공개 플래그 전환(공개↔비공개 양방향)이 topic 검색과 발언 검색 양쪽 표면에 일관되게 반영**될 것 — 공개를 켰는데 발언 인덱스는 아직이거나, 껐는데 발언 쪽만 남는 반쪽 상태 금지 (전파 시점은 Q5).
   - (c) **갱신 진행 중에도 그 유저의 기존 값은 계속 조회된다** (2026-08-14 persona 팀 확인 — 계약으로 기록). 갱신 중 데이터가 잠깐 사라지면 그 유저가 주기적으로 추천에서 증발한다 (P8 `pending` 규약과 짝).
   - (d) privacy는 이 모델에서 자연 성립한다 — 원래도 publishability는 read-time 최신 검사가 요건이었고(④), 이제 모든 읽기가 최신이므로 "pin된 과거 판본이 철회 항목을 노출"하는 충돌 자체가 없다.
   - 🟡 재추출을 넘는 `statement_id` 지속성(같은 발언 = 같은 id)은 (a)의 손실 창을 줄이는 개선 — 요구가 아니라 희망 사항 (P5).
8. **접근 경계는 승계가 아니라 결정**: persona API는 recommendation API보다 민감한 표면이다 — 전체 유저의 topic 검색, 타 유저의 stance 근거문, HEXACO batch가 전부 bulk-read다. 외부 ingress가 없어도 **임의의 in-cluster workload가 전 유저의 추출 데이터를 수집할 수 있는가**가 새로 생기는 질문이고, 현행 "in-cluster 무인증 + 네트워크 경계"를 자동 승계하면 이 threat model 검토가 통째로 생략된다. bearer 강제를 주장하는 것이 아니다 — 결론이 다시 "네트워크 경계 단독"일 수 있다. 다만 다음을 **명시적으로 합의**해야 한다: (a) 호출 workload allowlist 또는 service identity, (b) tenant별 접근 통제, (c) batch 크기 상한, (d) cross-user 조회 audit(어느 workload가 누구 데이터를 읽었나), (e) NetworkPolicy/mTLS 등 실제 경계의 소유자.

### P11 품질·평가 지원 — schema 밖의 계약 (핵심은 🔴 출시 게이트)

**왜.** 좋은 성능은 wire schema만으로 검증할 수 없다. (경험 두 가지: 우리 eval 하네스(평가를 실행하는 틀)는 HTTP 어댑터를 타지 않아 어댑터 회귀를 구조적으로 볼 수 없었고, stance 검색의 lexical-recall gap은 전용 recall eval을 따로 설계해서야 측정 가능해졌다. schema가 맞아도 품질은 따로 재야 한다.) 그리고 **vector-free 전제에서는 평가가 부가 기능이 아니라 기능의 일부다** — query expansion과 검색 대상 텍스트가 recall의 전부이므로, golden evaluation 없이는 "기능이 목표 성능으로 동작하는가"를 판단할 수단 자체가 없다.

**등급.**
- 🔴 **출시 게이트** (이것 없이 API는 만들 수 있지만 출시 판단은 불가): frozen corpus/snapshot · HTTP 계약 fixture · "query → relevant owner/topic" label 기반 need별·채널별 recall 측정 · 추출·요약 전후 stance 보존 평가 · 핵심 신호(depth/consistency) confidence calibration.
- 🟡 **운영 개선**: shadow/overlap 기간(shadow — 신버전을 응답에 반영하지 않고 병행 실행해 구버전과 비교하는 기간) · fragmentation 추세 측정 · 장기 deprecation 프로세스.

**소유권을 먼저 가른다** — persona 팀이 검색 golden set까지 만들면 자기 검색기를 자기 기준으로 평가하는 순환이 생긴다 (우리가 계약 테스트에서 잠근 것과 같은 순환이다):

- **persona 소유**: 추출 precision, confidence calibration, 추출·요약 전후 의미 보존.
- **Discovery/product 소유**: "추천 query → relevant owner/topic" relevance label, need별 recall, 최종 ranking 품질.
- **공동**: frozen corpus, cross-lingual case, fragmentation case, 버전 overlap snapshot.

**persona에 요청하는 것.**

| 항목 | 왜 |
|---|---|
| 독립 작성된 대표 fixture (endpoint별 응답 JSON) | 우리 계약 테스트가 consumer model에서 payload를 유도하는 순환을 피한다 (우리 쪽 잠근 규율) |
| 평가 가능한 **frozen snapshot** (corpus 고정본) | 우리가 paraphrase·cross-lingual golden set을 만들어 P1 recall·query expansion 품질을 **독립 측정**할 기반 — label은 우리/공동 소유 |
| topic fragmentation/과병합 측정치 | P6 병합 판정 임계값을 우리가 잡을 근거 |
| statement 추출·요약 전후 stance 보존 평가 | P5-④ 요건("주장의 방향·강도 보존")이 실제로 지켜지는지 — 지켜지지 않으면 judge 전체가 무효 |
| depth·HEXACO 등 confidence의 calibration 자료 | confidence를 gate 보정에 쓰려면 그 값이 calibrated인지 알아야 한다 (P3-⑤가 필수가 된 만큼 이 짝도 필수에 가깝다) |
| 모델 버전 교체 시 shadow/overlap 기간 + 신구 동일-owner 비교 snapshot | 전 유저 점수가 일제히 이동하는 이벤트를 우리 지표 회귀와 구분 (P3-④·P9 계약의 운영 짝) |
| breaking semantic change·deprecation 통지 규약 | 필드 의미가 조용히 바뀌는 것이 가장 비싼 장애다 — 이 문서의 절반이 그 사후 수습 경험에서 나왔다 |

---

## 2. Persona endpoint 전반에 대한 의견 (요청이 아니라 제안)

- **리소스 계층 제안**: `/{tenant}/persona/…` 아래 `owners/{owner_id}/topics`, `owners/{owner_id}/hexaco`, `owners/{owner_id}/interaction-style`, `topics/search`(cross-user), `topics/batch`(hydration), `evidence/search`(발견층), `statements/batch`(발견분 정확 fetch), `statements/search`(본문층 추가 채움), `status`. (+ 표현 공간이 생길 경우의 조건부: `topics/similar`, `topics/similarity-matrix`.) cross-user 검색류는 POST(body에 query bag), 단건 조회는 GET, 다건 상세·shortlist 비교는 batch POST.
- **owner_id 좌표계를 유지해달라**: 본질 이유는 매핑 계약의 수다 — persona의 source가 memory-api(대화)이고 추천 실체(agent)가 owner에서 파생되므로, persona가 memory-api와 같은 owner 좌표계를 쓰면 시스템 전체에 id 매핑이 하나도 늘지 않는다. 자체 user id를 쓰면 매핑 계약·불일치 가능성이 하나 더 생긴다. (우리 쪽에 owner_id → agent_id 일방향 파생 층이 이미 있다는 것은 부수 이점이다.)
- **읽기 전용 보장**: 우리 호출로 persona 쪽 상태가 생성/변경되지 않아야 한다 (경험: 상류 스토리지가 읽기 경로에서 lazy-create 가능한지를 코드로 검증해야 했던 적이 있다 — 계약 문서에 한 줄이면 그 검증이 불필요해진다).
- **인증·테넌시**: 현행 규약(in-cluster 무인증 + 네트워크 경계)의 **자동 승계를 전제하지 않는다** — persona 표면은 더 민감하므로 P10-⑧의 threat model 항목을 합의한 뒤 결정. tenant prefix 규약(현행 `/{tenant}/…`)의 승계 여부도 함께 확인.
- **품질·평가 지원은 P11로 분리** — fixture·golden set·calibration·shadow 기간 등 schema 밖 계약.

## 3. 요청에서 의도적으로 뺀 것

- **popularity 계열** (조회수·언급량 순위 등): 우리 원칙상 popularity prior는 랭킹에 들어가지 않는다. 요청하면 언젠가 쓰게 된다.
- **저장된 stance 라벨**: stance는 query-time judge 소관. persona가 opinion을 추출하더라도 우리는 라벨이 아니라 **근거 statement**(P5)를 요청한다.
- **score의 cross-version 안정성 보장**: score 자체는 받는다(P1 계약 ② — version-scoped optional signal). 요청하지 않는 것은 *서로 다른 model version 사이의 숫자 비교 가능성*이다 — 이 보장을 요구하는 순간 persona의 모델 교체가 우리 breaking change가 된다.
- **conversation 원문 접근**: 우리에게 필요한 것은 추출물이지 원 대화가 아니다. 경계를 넓히지 않는다. 대화 컨텍스트는 client가 요청 body로 준다(§0.0-1) — memory-api conversation 조회 경로도 요청하지 않는다.
- **`canonical_topic_id` 자리 예약**: rev 2까지 있었으나 철회 — merge/split/version 의미가 미정인 예약 필드는 우리 자신의 교훈("예약 hook은 같은 질문이 유지될 때만 additive")에 걸린다. 로드맵 질문(Q3)으로 대체.
- **orthogonal need의 계약**: 현행 코드에 없는 신규 product need — P7의 관계 어휘에 ⚪ 자리만 두고, 설계 후 후속 요청.
- **statement `text`의 노출용 정제**: rev 11까지 요구했으나 철회(§0.0-7) — 발언 본문은 내부 판정 전용이고 최종 유저에게는 요약·부연 수준의 추천 이유만 나간다(**원문 인용 배제로 잠금** — 우리 쪽 응답 규율). statement 단위 publishability·개별 억제도 같은 이유로 비요청.

## 4. 열린 질문 — persona 팀에 물을 것 (요청서에 질문으로 포함)

(내부 전제 질문 4건은 2026-08-13 확인 완료 → §0.0으로 이동.)

- Q1. topic의 생명주기 — 병합/분할/개명이 일어나는지, 그때 topic 식별자는 어떻게 되는지 (P2 계약 ②). 그리고 식별자 좌표계는 (owner_id, topic_id) 복합인지 tenant-전역 유일인지 (P2 계약 ①).
- Q2. 추출 주기 — ~~실시간 인접인지 배치인지~~ **유저별 상시 증분으로 확인** (§0.0-5). 남는 질문: 처리 window 크기와 `as_of`/`conversation_watermark` lag의 기대 범위 (P8).
- Q3. cross-user 정규화(canonical **topic + facet** space)의 로드맵이 있는지 — 있다면 우리의 query-local facet 분류(P7)와 같은-주제 판정(P6 B안)을 단계적으로 대체할 수 있다.
- Q4. semantic 검색/표현 공간에 대한 독립적 계획이 있는지 — 있다면 우리 의견은 투자 순서가 **evidence 발견층(P5 층 1) > topic 검색**이라는 것이고, 그때 batch similarity(P7)·`/topics/similar`(P6)·cross-lingual 매칭이 선택적 최적화로 활성화된다. 없다면 이들은 전부 비요청이다.
- Q5. 삭제·철회·**공개↔비공개 전환(양방향)**의 전파 시점 — 즉시인지 다음 갱신 주기인지, 그리고 topic 검색과 statement 검색 **양쪽 인덱스에 함께** 반영되는지 (P10-④·P10-⑦-(b)). `statement_id`(P5)로 우리가 전파를 검증할 수 있는지.
- Q6. statement `text`의 형태 — 원 발화 그대로인지 추출·요약된 근거문인지 무엇을 계획 중인지, 추출·요약 시 주장의 방향·강도 보존이 가능한지 (P5-④; 노출용 정제는 §0.0-7로 비요청).
- Q7. 접근 경계 — P10-⑧의 5개 항목(workload identity·tenant 통제·batch 상한·audit·경계 소유자)에 대한 persona 팀의 계획.
- Q8. evidence 발견층(P5 층 1)의 projection 경계 — **같은 publishability·동의 경계 안에서** 본문층보다 작은 projection(좌표만)으로 운용하는 것이 맞는지, persona 쪽 필터링 층이 두 층을 동일하게 다루는지.
- Q9. InteractionStyle — 어디까지 추출 가능한지, 그리고 **표현 shape**: global baseline / 언어별 / context별 분산·범위 / 최근 가중 중 무엇이 현실적인지 (P9) — 가능 범위와 shape에 따라 매칭 설계가 달라진다.
- Q10. P3 확장 축의 의미 정의 제안 — `engagement_frequency`/`trend`의 기준 time window와 변화량 정의, `interest_strength`가 발화량 기반인지 명시적 선호 기반인지, `discussion_willingness`가 명시 발화와 추론을 구분하는지 (필드명은 우리가 잠그지 않는다 — 의미를 persona 팀이 제안해달라).
- Q11. ~~snapshot의 원자성~~ **해소 (rev 11)** — snapshot pinning 철회(P10-⑦)로 질문 자체가 사라졌다. rev 12에서 남은 확인 항목은 Q5로 합류: 공개 플래그 전환의 양방향 인덱스 전파 (P10-⑦-(b)).
- Q12. **search alias 생성의 언어 셋** (P1 계약 ⑤) — 서비스 지원 언어(한국어·영어·일본어 등)가 어디서 결정되는지(tenant 설정? 고정 목록?), 생성 시점(topic 생성/개명 시 1회?), 그리고 생성 품질을 P11 cross-lingual golden case로 함께 검증할 수 있는지.

## 5. 요약 — 한 장

| # | 요청 | 우선순위 | 없으면 |
|---|---|---|---|
| P0 | (내부) context-only 요청 계약 변경 | 🔴 | 제품 시나리오와 우리 API가 어긋남 |
| P1 | cross-user topic 검색 (text 검색·대상 필드 계약·**다국어 search alias 생성**·원시 필드 필터) — `TopicCandidate` projection | 🔴 | 추천 pool 구성 불가 / N+1 / 언어가 다르면 못 찾음 / 요건 미달 후보가 top-N을 잠식 |
| P2 | topic 카드 + **union hydration batch** (불변 id·aliases·description·keywords) | 🔴 | rerank·reason 품질 붕괴 / evidence 채널 후보가 랭킹 불가 |
| P3 | depth·consistency(+**필수 uncertainty**)·evidence_count·**evidence_last_seen**(active 집합 파생값) + vintage 값 + 확장 축 🟡 | 🔴 | gate·정렬 입력 없음 = 추천 없음 |
| P4 | experience **provenance별 집계** (firsthand/secondhand bucket — 단일 enum 철회) | 🟡 | experience need가 depth 변형으로 퇴화 / 병행 경험 유저의 근거 소실 |
| P5 | evidence 검색 **2층** — 발견층(`statement_id` 포함, 본문 없음) + 본문층(ID batch fetch + scoped search) | 🔴 | for/against·experience·orthogonal의 후보 회수가 topic 순위에 종속 + 발견↔judge 입력 단절 |
| P6 | 파편화: 판정=우리(agentic 반복 검색), 재료=persona — `/similar`는 🟡 조건부 | 🔴 | pool 누수 또는 과병합 |
| P7 | topic 관계 계약; 다양성 판정 = LLM batch 1회(우리) — batch similarity는 🟡 조건부 | 🔴 | coverage need·sparse 주제 추천 소멸 |
| P8 | 상태·실패 구분 — 서비스 상태 🔴 + owner별 상태 🟡(진단용·파이프라인 비호출) | 🔴/🟡 | 상류 부재가 호출자 422로 귀속 (재발) / "왜 추천 안 되나" 진단 불가 |
| P9 | HEXACO + **InteractionStyle** 원자료 (confidence·insufficient 구분·동의 정책) | 🟡 | 추후 surface 차단; 단 소비 설계는 전부 신규 |
| P10 | 운영 계약 (pagination 이원화·null·버전·**공개 topic 단위 노출**·최신 값 읽기·**공개 전환 양방향 전파**·접근 경계) | 🔴 | v1→v2에서 겪은 함정 전부 재발 + 공개 전환의 반쪽 반영(숨긴 topic의 발언이 발언 검색에 잔존) |
| P11 | 품질·평가 지원 — **출시 게이트**(frozen corpus·fixture·recall label·추출 전후 stance 보존·calibration) + 운영 개선 🟡 | 🔴/🟡 | vector-free에서 "목표 성능 달성" 판단 수단 자체가 없음 |

## 6. 발신 형태 (예고 — 내용 확정 후 분리)

이 파일은 **내부 작업본**이다. 내용이 확정되면 발신 전에 두 문서로 분리한다:

1. **persona 팀용 본문**: 제품 목표 → 필수 capability와 의미 계약(잠금 수준 원칙 포함) → illustrative API shape(강제 아님을 명시) → 열린 질문. 현행 공식·과거 장애 사례·우리 코드 인용은 싣지 않는다 — persona 팀이 "legacy 구조 복제가 목표"라고 오독하는 것을 막기 위해서다.
2. **내부 부록** (비발신): §0.2 대응표, 현행 공식, 경험 인용, P0, migration 영향.

분리는 내용 확정 후의 기계적 작업이므로 지금은 이 계획만 기록한다.

## 부록 — 개정 이력

- **rev 1**: 최초 초안 (P1–P9).
- **rev 2**: 내부 전제 4건 확정 반영 (§0.0), HEXACO batch 추가.
- **rev 3**: 외부 리뷰 1차 반영 — ① coverage/orthogonal 누락 → P7 신설 + 용어 분리, ② context-only 계약 → P0(내부 작업) 신설, ③ N+1 → P3 위치를 P1 `TopicCandidate`로 확정, ④ cross-user 공개 경계 → publishability 3층·정제 요건·전파 시점(P10-④·P5-④), ⑤ topic 식별자 좌표계 확정 요구(P2-①), ⑥ `canonical_topic_id` 예약 철회, ⑦ expansion 공정성(`matched_query_indices`), ⑧ vintage를 값으로(run_id)·consistency 정의 경고, ⑨ P8 데이터종류별 상태 + corpus snapshot, ⑩ pagination 이원화(cursor), ⑪ P9(HEXACO)를 "seam은 있으나 설계는 신규"로 정정. 리뷰의 코드 인용 4건은 `ranking.py`(_coverage_round_robin)·`retrieval.py`(_expand_neighbors)·`persona.py`(PersonaPrior v0)·`gate.py`(단건 호출)에서 직접 검증함.
- **rev 4**: 외부 리뷰 2차 반영 — ① P7의 안정적 facet_id 요청 철회 (canonical facet space의 뒷문 요구였음) → **facet 분할은 Discovery가 query-local로 소유**로 결정, canonical topic+facet space는 Q3 로드맵으로 통합, P6 similar(병합)/P7 related(확장) 의미 구분을 계약으로, ② `evidence_last_seen`을 갱신 이벤트에서 **active 집합의 파생값**(max said_at)으로 재정의 — 삭제·철회 시 후퇴/전무 시 null/실패 시 불변, ③ `statement_count` → `evidence_count`(distinct source evidence unit — extractor 분할 성향 비오염), ④ P5 scope를 `scopes` 단일 필드로 통합 + 응답에 opaque `statement_id`(decision log 근거 기록·삭제 전파 검증) + active·publishable 보장, ⑤ 접근 경계 자동 승계 철회 → P10-⑦ threat model 5항목 + Q7, ⑥ P1 공정성을 correctness(a/b)와 observability(indices)로 분리, ⑦ P8 카운트를 `source/extracted/publishable_owner_count`로 개명(eligibility 용어 충돌 회피), ⑧ P9 enum 용어 통일(`none`) + pending/failed는 P8 전용 명시, ⑨ 다국어 계약 신설(P1-⑤ cross-lingual + `lang`).
- **rev 5**: 잠금 수준 재조정 — 기존 구현에 억지로 맞춘 제약을 만들지 않는다는 방침 반영. §0에 "요청의 잠금 수준" 원칙 신설: 계약은 (a) 신호의 축 + (b) 값의 의미 요건뿐이고, 현행 공식(maturity 가중·n/(n+4)·90일 반감기)과 파이프라인 구조(facet round-robin)는 재설계 가능 영역으로 명시. P7 다양성 판정을 구현 중립으로(갈래 round-robin 또는 semantic diversity 최적화 — 어느 쪽이든 persona 요청 동일), P5 query-time stance를 구현 유산이 아니라 문제 성질(명제 공간은 저장 불가)로 재서술, P1 projection 필드를 "1왕복 요건 + 구체 제안"으로, P0을 재구현 경로 포함으로, §2 owner 좌표계 요청을 본질 이유(매핑 계약 수)로 재서술.
- **rev 6**: 외부 리뷰 3차 반영 — ① **topic-first 단일 후보 회수가 마지막 legacy 구조였음을 인정** → 후보 pool을 채널 union(P1 topic ∪ P5 발견층 ∪ P7 related)으로 재정의, P5를 2층(후보 발견 cross-user 무본문 / 본문 fetch scoped)으로 재구성, ② scalar score 전면 비노출 철회 → "순서만 안정 계약, score는 비계약 보조 신호(component·calibration·version 동반)"로 좁게 계약, ③ P3 확장 축 🟡 신설(distinct_conversation_count 최우선·interest·breadth·frequency·first_seen·trend·discussion_willingness), P4에 경험 근거량·confidence·최근성·breadth 추가, ④ P7에 batch similarity primitive 🔴 추가(다양성 판정 소유의 전제 — embedding 노출은 비요청), ⑤ orthogonal을 contrasting topic(P7 어휘 ⚪)과 orthogonal viewpoint(P5 재료 지금 확보)로 분리, ⑥ P9에 InteractionStyle 병설, ⑦ P11 품질·평가 지원 신설(§2 fixture 항목 흡수), ⑧ §6 발신 형태(본문/내부 부록 분리 계획) 신설, Q8·Q9 추가.
- **rev 7**: 외부 리뷰 4차 + **vector-free 검색 전제 확정** 반영 — ① 문서 머리에 검색 전제 신설(vector-free agentic; recall 책임 분담 = persona 텍스트 재료 / 우리 query expansion / P11 검증), ② union 후보 hydration 확정: P2 batch가 multi-channel hot path의 공식 hydration 단계로 승격(모든 채널 후보가 같은 `TopicCandidate` projection으로 합류), "hot path 1왕복"을 "채널 내 per-hit N+1 없음"으로 정정, ③ union provenance 규칙(`retrieval_reasons` — 채널별 유입 근거 보존, P7 related에 `source_topic`) 내부 계약 신설, ④ P10-⑦ cross-endpoint **snapshot pinning**(선택적 snapshot_id 입력·만료 시 명시적 오류·차선은 불일치 탐지 재시도), ⑤ score를 "비계약 보조 신호"에서 **version-scoped optional signal**로 정정(shape·의미·version=계약 / cross-version 비교=비보장 / 사용=우리 선택 + 해당 version calibration 통과 후) — P6·§3의 stale 문구 동기화, ⑥ **batch similarity 🔴→🟡 조건부 강등**: 근거("persona는 표현 공간을 어차피 갖는다")가 vector-free 전제에서 오류로 판명 — 다양성 판정 기본 계획은 후보 20–50개 LLM batch 1회, capability-형태 질문으로 전환(제공 시 의미 계약 목록은 유지), P6 `/topics/similar`도 조건부 최적화로 강등, P1 `mode` 필드 제거 + **검색 대상 필드 계약**(name+aliases+description+keywords) 신설, cross-lingual recall 책임을 query expansion으로 이동, ⑦ P3-⑤ uncertainty **필수화**(calibrated confidence / evidence coverage / 상태 enum 중 택일) + 확장 축 의미 질문 Q10, ⑧ P11 평가 소유권 3분할(persona=추출 precision·calibration·정제 보존 / 우리=relevance label·need별 recall·ranking 품질 / 공동=frozen corpus·cross-lingual·fragmentation·overlap snapshot), ⑨ Q8을 "낮은 privacy 등급"에서 "같은 publishability·동의 경계 안의 더 작은 projection"으로 정정, 개정 이력 시간순 재정렬.
- **rev 8**: 외부 리뷰 5차 반영 — ① **발견층↔본문층 연결**: 발견층 hit에 opaque `statement_id`(+`epistemic`·`matched_query_indices`·`snapshot_id`) 포함, `POST /statements/batch`(ID 정확 fetch) 신설 — 재검색만으로는 발견한 evidence가 judge 입력으로 돌아온다는 보장이 없고 decision log 연결도 불가했다, ② **content snapshot과 privacy 상태 분리**(P10-⑦): 내용·신호는 pinned, publishability·동의·차단은 read-time 최신 — 철회 항목은 과거 snapshot에서도 비반환, 사라진 key는 `not_publishable` 명시 상태로 + snapshot 원자성 질문(Q11: 독립 파이프라인이면 release_id/version vector), ③ **experience 단일 enum 철회** → provenance별 집계(firsthand/secondhand bucket, 각자 count·specificity·confidence·last_seen) — 병행 경험 유저에서 한 provenance가 다른 쪽 근거를 지우는 legacy 제약 제거, null↔specificity 불변식은 bucket 단위 규약으로 대체, ④ **P11 등급 분리**: 출시 게이트 🔴(frozen corpus·fixture·need별 recall label·정제 stance 보존·calibration — vector-free에서 평가는 기능의 일부) / 운영 개선 🟡(shadow·fragmentation 추세·deprecation), ⑤ P2 batch **부분 실패 계약**(item별 outcome: ready/not_publishable/not_found/not_extracted·순서·중복 규약), ⑥ P1 merge 정책 재작업: "query별 균등 quota"도 요구하지 않음(나쁜 확장에 동일 quota면 precision 붕괴) → query별 cap/독립 검색 capability + 서버 merge 시 정책·기여량 공개, ⑦ InteractionStyle 맥락 의존성 — 단일 scalar로 잠그지 않고 표현 shape를 Q9로 확장. **정합 수정(6차 리뷰)**: 반환형 계약 명문화(P1 hit=완성형 TopicCandidate·P2 batch=TopicCandidate·단건 GET만 TopicCard), run 최초 snapshot 획득 절차(P8 status 1회 → 전 fan-out 전달), statements/batch에 item별 outcome + "pinned 발견 ID의 not_found = 무결성 위반" 규칙, P1 표의 experience를 bucket projection으로 동기화, batch 상태별 소비자 행동 명시(not_extracted 포함), ranked 검색 근거에서 ANN 문구 제거(vector-free 정합), 접근 경계 참조 ⑦→⑧ 정정.
- **rev 9**: **다국어 search alias 생성(enrichment) 요청 신설** — 관측 alias 인덱싱만으로는 "유저가 영어로만 말해 'coffee'로 저장된 topic을 '커피'로 찾는" 시나리오가 안 풀린다(그 언어의 관측 alias가 존재하지 않음). cross-lingual recall의 1차 메커니즘을 query-side 번역(우리 expansion, 요청마다 추측)에서 **storage-side 생성 alias**(topic당 1회, 결정적)로 이동: P1 계약 ⑤ 재작성("커피"→"coffee" 예시·관측/생성 구분·지원 언어 셋은 Q12), P2에 `search_aliases` 필드 신설(관측 `aliases`와 분리 — 정제 부담이 다름), 계약 ⑥ 검색 대상에 포함, 문서 머리 책임 분담 갱신(expansion의 번역은 보완으로), Q12 신설.
- **rev 10**: P1 계약 ⑦ **원시 필드 필터** 신설 — need별 최소 요건(`min_evidence_count`·`min_depth`·`min_consistency`·`experience` bucket 존재·`evidence_last_seen_after`)을 요청 파라미터로 걸러 받는다. 필터 없이는 게이트 탈락분만큼 top-N의 실사용 후보가 줄고 N등 밖의 요건 충족 후보는 회수 불가(대안이 overfetch뿐). 경계 유지: 문턱값·조합 판정(maturity류)은 우리 소유 — persona에는 원시 필드 비교만 요청.
- **rev 11**: **유저별 상시 증분 갱신 전제 확정(§0.0-5) → snapshot pinning 철회.** persona는 batch release가 아니라 유저별 그때그때 처리이므로 전역 시점 고정 요구는 release 없는 저장 모델에 MVCC류 부담을 강제하는 것(잠금 원칙 위반)이고, run 중 어긋남의 실제 피해는 "후보 하나 손실" 수준 — 소비 시점에는 어차피 다음 갱신이 반영된 세계다. 대체 읽기 모델(P10-⑦ 재작성): (a) 각 단계는 최신 값, 사라진 key는 item별 `not_found`/`not_publishable` → **그 후보만 제거하고 계속**(P2-④·P5의 "무결성 위반 → 재시작" 규칙 삭제), (b) **모든 중간 상태는 유효해야 한다** — 기존 topic의 evidence 증분은 무규약(항상 유효), **신규 topic은 evidence 처리 완료 후 모든 조회 표면에 한 묶음으로 원자적 공개**(절반 처리된 집계값으로 filters 오판·부분 증거 stance 판정 방지), (c) 갱신 중에도 기존 값 계속 조회(2026-08-14 확인 — P8 `pending`은 최초 추출 전에만), (d) privacy read-time 검사는 자연 성립(pin-철회 충돌 자체가 소멸). `statement_id`의 재추출 간 지속성은 🟡 희망 사항으로 강등. wire 스케치 전체에서 `snapshot_id` 제거, Q11 해소(신규 확인 항목: 원자적 공개 보장 가능 여부), Q2 부분 해소, P8에 "갱신 중 pending 회귀 금지" 규약 추가, P10-①에서 snapshot 안정성 문구를 cursor 최소 보장으로 완화.
- **rev 12**: **topic 공개 모델 확정(§0.0-6·7) 반영.** 제품 확정 둘: ① 노출 결정 단위 = topic(유저별 공개 선택, **기본 비공개** — 명시 공개분만 검색·추천 대상, persona가 공개 필드 관리), ② **발언 본문은 최종 유저 비노출**(내부 judge 재료 — 추천 이유는 요약·부연만, **원문 인용 배제로 잠금**). 파생 수정: (a) P10-④ 노출 3층 철회 → topic 단위 확정(owner층=파생, statement층=topic 승계) + 공개 전환의 topic/statement 양쪽 인덱스 동시 반영 요건, (b) P5-④ `text` 노출용 정제 요구 철회 → "추출된 근거문 + 방향·강도 보존"만 잔존, P5-② 경계를 "공개 topic 소속 발언"으로 정밀화, (c) P10-⑦-(b) 신규 topic 원자적 공개 요건은 기본 비공개 모델이 구조적으로 흡수 → "공개 플래그 양방향 일관 전파" 한 줄로 축소(Q5 합류, Q11 갱신), (d) P10-⑤에서 `text`를 노출 정제 대상에서 제외(`aliases`/`description`은 유지 — 추천 이유에 나갈 수 있는 표면), (e) P1 계약 ①에 "검색 모집단 = 공개 topic만 — pool 상한은 공개 비율" 명시, P8 status에 `publishable_topic_count` 추가, §3에 비요청 항목(노출용 정제·statement 단위 publishability) 기록.
- **rev 13**: **P8 owner별 상태 조회를 🟡 진단용으로 강등** (서비스 상태는 🔴 유지). 근거: 추천 파이프라인에 이 조회를 부를 지점이 없다 — 후보는 검색 유입이고, 기본 비공개 모델에서 pending 유저와 "공개 topic 0개" 유저는 우리 행동상 동일(검색 비노출·부정 캐시 없음 → "신규 유저 영구 배제" 논거 소멸), 파이프라인 필요분은 batch item `not_extracted`(P2-④)와 갱신 중 기존 값 서빙(P10-⑦-(c))으로 이미 확보. 남는 용도 = 진단("왜 추천 안 되나") + P9 진행 상태 enum의 좌석. pending 의미 계약(최초 추출 전에만·ready/0개와 구분)은 등급과 무관하게 유지 — 상태가 나타나는 모든 자리에 적용.
