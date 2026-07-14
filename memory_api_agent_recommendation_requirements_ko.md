# Agent Recommendation을 위한 Memory API 요구사항

## 목적

이 문서는 `bourbon-agent-recommendation-api`가 real candidate path를 실행할 때
memory 내부를 직접 재구성하지 않도록, `bourbon-memory-api`가 제공해야 하는 최소
계약을 정의한다.

서비스 경계는 다음과 같다.

- `memory-api`는 memory fact와 memory-derived read projection을 소유한다. 여기에는
  personal entity, public grounding link, statement, statement kind, timestamp,
  provenance, salience component가 포함된다. `owner_id`는 반환하지만 `agent_id`는
  반환하지 않는다.
- `agent-recommendation-api`는 추천 정책과 request-time derivation을 소유한다. 여기에는
  maturity, evidence strength, freshness score, experience ranking, stance matching,
  eligibility gate, ordering key, (`bourbon-api`를 통한) `owner_id -> agent_id` 해석,
  최종 응답 조립이 포함된다.

Memory API는 agent를 rank하면 안 되고 `AgentTopicEdge`를 직접 반환하면 안 된다.
대신 agent-recommendation이 `AgentTopicEdge` 후보를 직접 계산할 수 있도록 bounded
raw-signal projection을 제공해야 한다.

## 현재 Memory API가 이미 제공하는 것

public knowledge anchor 경로는 존재하지만, 안정적인 grounding recall을 위해 entity search relevance 개선이 필요하다.

`agent-recommendation-api`는 기존 knowledge route를 `KnowledgeEntityProvider`
substrate로 그대로 사용할 수 있다.

- `GET /knowledge/entities`
- `GET /knowledge/entities/suggest`
- `GET /knowledge/entities/{qid}`
- `GET /knowledge/entities/{qid}/connections`
- `GET /knowledge/articles`

이 API들은 다음 흐름을 지원한다.

```text
topic_text
  -> public entity search/suggest
  -> resolved QID anchor
  -> public neighbor expansion
```

따라서 public anchor grounding 쪽에는 큰 추가 작업이 필요하지 않다.


> **Update 2026-07-14 (감사 `bc9110c`→`2f268fe`):**
> - **Superseded:** `GET /knowledge/entities/suggest`가 **삭제됨**(memory-api #87) — substrate 목록에서 제거.
>   grounding은 이를 쓴 적 없음(search-only)이라 recall 영향 없음.
> - **Shipped:** 위의 "search relevance 개선 필요" 단서는 **대부분 해소**됨(아래 §"공개 엔티티 검색 relevance"
>   Update 참조). `GET /knowledge/entities`가 이제 `context=`(sense 편향)·`types=`(`instance_of` 클래스
>   필터) 파라미터도 받는다.
## Agent Recommendation이 계산하는 것

추천 파이프라인은 최종적으로 내부 `AgentTopicEdge` 후보가 필요하다.

```text
agent_id
anchor_id
maturity
evidence_strength
freshness
experience_source_type
experience_specificity
observed_stance
stance_axis
stance_summary
stance_confidence
evidence_refs
discoverable
```

하지만 이 필드 전체가 Memory API의 책임은 아니다.

Memory API는 이 값을 도출하는 데 필요한 raw material만 제공해야 한다.
Agent Recommendation은 need type, threshold, policy tuning, 사용자의 stance reference에
따라 request time에 recommendation-facing value를 계산해야 한다.

`agent_id`는 Memory API의 필드가 아니다. Memory는 `owner_id`를 반환하고, Agent
Recommendation은 `bourbon-api`를 통해 해당 owner의 personal agent를 해석한다. 그
`agent_id`는 owner에 대한 결정적 `uuid5`(`personal_agent_id(owner_id)`)다. 이는
memory-api의 `owner_id`가 플랫폼 user id(즉 `bourbon-api` `users.id`)와 동일하다는 전제
위에 성립하며 — 계약 확정 전 memory 팀과 확인해야 하는 shared-namespace 가정이다. 따라서
agent 식별자는 routing과 마찬가지로 memory 계약 밖에 둔다.

`routing_target`은 계약에서 완전히 제거한다 — `memory-api`도 `agent-recommendation-api`도
저장/반환하지 않는다. recommendation은 `agent_id`(및 reasons/evidence refs)를 반환하고,
`bourbon-api`가 런타임에 `agent_id`로부터 dispatch를 해석한다(agent는 endpoint 필드를
갖지 않으며, 라우팅은 agent type + room context 기반 AMQP task다). 아래 "Routing Target" 참조.

## 왜 기존 `/personal/groundings/{qid}`만으로는 부족한가

Memory API에는 현재 가까운 route가 있다.

```text
GET /personal/groundings/{qid}
```

이 API는 특정 public QID에 grounded된 personal entity들을 반환한다.

```text
qid -> owner_id -> PersonalEntitySummary
```

이것은 좋은 source material이다. 포함되는 신호는 대략 다음과 같다.

- `owner_id`
- personal entity id / label
- `knowledge_qid`
- grounding `confidence`
- grounding `margin`
- grounding `depth`
- `broader_qids`
- `pagerank`
- `salience`

하지만 이것은 recommendation input projection이 아니라 personal-entity grounding
projection이다. recommendation feature 계산에 필요한 raw material이 빠져 있다.

- freshness derivation을 위한 grounding timestamp
- salience component count (`PersonalEntity`에는 있으나 이 projection엔 없음)
- statement kind / epistemic type별 count
- experience와 stance derivation을 위한 statement text/confidence/provenance
- explanation, decision log, eval replay를 위한 evidence refs


> **Update 2026-07-14 (#64 competence vector):** 위 "빠져 있음" 목록은 **부분 실현**됨. memory-api가
> Discovery용 `Competence` 벡터를 `PersonalEntity`에 추가(→`PersonalEntitySummary`/`GroundingMatch`로 노출):
> `{frequency, breadth, depth, consistency, sentiment + depth/consistency_rationale, aspects_covered,
> open_questions, persona_blurb, support_ids}` + Tier-2 `degree`/`hands_on_ratio`/`last_seen`/`opinion_ratio`.
> 이로써 freshness source(`last_seen`)·statement-kind/experiential 비중(`hands_on_ratio`)·evidence
> refs(`support_ids`)가 커버됨. 단 이것만으로 `AgentTopicEdge`가 되지는 않음 — 아래 "추가 필요" Update 참조.
## 공개 엔티티 검색 relevance — grounding recall (2026-07-10 추가)

> **Update 2026-07-14 — 대부분 해소(감사).** 아래 근본원인(canonical 매몰)은 **다국어 인덱스 overwrite
> 버그**였고, fix + 전체 재색인됨(#78): 다국어 인덱스(EN/KO/JA) + 전언어 `names` recall 필드 +
> `SEARCH_EXCLUDED_CLASS_QIDS` meta-page 제외. 실측: `JavaScript`→Q2005 rank 1, `TypeScript`→Q978185 rank 1,
> disambiguation/Category 페이지 강등. 아래 요구 대비: cross-language recall ✅, demote-disambiguation ✅;
> 랭킹은 아직 튜닝 전 BM25(memory-api 후속). **아래 §"범위 밖 — context 미포함" 노트는 이제 반대가 됨:**
> context disambiguation이 검색-레이어 bias로 배포됨 — `context=`(prose `should` boost 0.5) +
> `types=`(positive `instance_of` 필터). 상세: `impl/findings-real-anchor-grounding-ties.md`
> "Update (2026-07-14)". **남은 ask:** query-time relevance/`_score`를 `EntitySummary`에 실어주는 projection
> (linker tie margin용).

Agent-recommendation의 grounding은 주제 텍스트를 `GET /knowledge/entities` 검색으로 QID에 매핑하는
데서 시작한다. 그런데 이 검색이 **명백한 정본(canonical) 엔티티를 상위에 올리지 못하는** 경우가 있어
grounding이 시작부터 실패한다. 이는 아래 personal signal projection과 **독립된 별개 요구**다.

### 증상 (localhost:3000 실측, 2026-07-10)

| 쿼리 | 원하는 정본 | 실제 top | 결과 |
|---|---|---|---|
| `JavaScript` | JS 언어 (Q2005, label "자바스크립트") | "JavaScript framework/library/engine/syntax"… | 정본 **top-50 밖 (완전 누락)** |
| `TypeScript` | TS 언어 (Q978185, imp 0.456) | rank 1 = disambiguation 페이지 (Q64624307, imp 0.281) | 정본 rank 2 |
| `Python` | Python 언어 (Q28865) | 같은 label "Python" 다수(언어/미사일/신화/뱀속) | rank 1은 맞으나 importance만으로 갈림 |

- `q=자바스크립트`(한국어)로 치면 Q2005가 rank 1 → JavaScript 누락은 순수 **cross-language** 문제.
- Q2005의 importance(0.488)가 상위 결과들(0.24–0.40)보다 높은데도 누락 → 순위를 지배하는 건 importance가
  아니라 label 매칭.
- 맥락어를 붙여도 안 됨: `q=python language`가 되는 건 "language"가 label에 없어 무력 + 원래 importance로
  1위였을 뿐이고, `q=javascript programming language`는 오히려 일반 "programming language" 개념을
  끌어옴(Q2005 여전히 누락).

### 원인 (현 스코어링)
`multi_match(fields=["label^3","aliases"]) × function_score(importance)`, sort `_score`. importance =
오프라인 위키 인기도 blend(pageview .5 / pagerank .3 / sitelink .2).
- **label 3배 vs alias 1배 비대칭** → 정본 label이 비-쿼리 언어면(쿼리어가 alias로만 매칭) label에 쿼리어를
  담은 엔티티들에 밀림.
- **importance는 배수라 구제 못 함** → 더 유명한 정본이 텍스트 점수 낮으면 밀림(TypeScript).
- entity 인덱스에 CJK analyzer 없음, 다국어 `labels` 맵은 저장되나 색인 안 됨.
- 응답에 `categories`/`description`이 오지만(disambiguation 페이지는 `Disambiguation pages`로 명확히
  태깅) **랭킹이 활용 안 함**.

### 요구
bare 쿼리로도 명백한 정본이 상위에 오도록 **검색 recall/ranking을 개선**한다(구현 방식은 memory-api 팀
판단). 방향 예시(택1 이상):
- cross-language / alias-only 정본 recall 보강 — 다국어 label 색인, alias 가중 상향, exact surface-form 보너스.
- disambiguation / `Template:` / `Category:` 류 문서 demote(이미 `categories`에 표시됨).

### 범위 밖 — context disambiguation은 이 요구에 포함하지 않음
동음이의(`Python` 언어 vs 뱀)에서 **어느 sense인지** 고르는 것은 맥락이 필요하며, 이 검색 요구에 넣지 않는다.
- 후보만 잘 recall되면(위 요구), sense 선택은 호출자(agent-recommendation)의 rerank가 맥락으로 수행 가능.
- 또한 memory-api는 이미 **ingest 경로에 맥락 기반 disambiguator** `Grounder.ground(mention, *, context=)`를
  갖고 있음(현재 오프라인 전용, `/personal/groundings` edge를 만든 바로 그것). 단 이 candidate 단계도 위와
  **같은 lexical recall**을 쓰므로 위 검색 개선이 이것의 선결이기도 함. 이를 read 엔드포인트로 노출하는 건
  별도 논의. 상세·근거: `impl/findings-real-anchor-grounding-ties.md`.

### Acceptance (검색 relevance)
- `JavaScript`, `TypeScript` 같은 흔한 tech 쿼리에서 **정본 엔티티가 상위(예: top-3)에 노출**.
- disambiguation / Template / Category 문서가 실제 개념보다 위에 오지 않음.

## Memory API에 추가로 필요한 것

Memory API는 public QID에 대해 agent-recommendation용 raw signal projection을
제공해야 한다.

가능한 route 이름:

```text
GET /personal/agent-topic-signals/{qid}
```

또는:

```text
GET /personal/groundings/{qid}/recommendation-signals
```

응답은 memory-derived raw signal을 가진 candidate owner의 paginated list여야 한다.
`AgentTopicEdge`가 아니어야 하며, 최종 recommendation score를 포함하지 않아야 한다.

예상 shape:

```json
{
  "owner_id": "owner-uuid",
  "personal_entity_id": "entity-uuid",
  "anchor_id": "Q42",

  "grounding": {
    "source": "wikidata",
    "confidence": 0.87,
    "margin": 0.21,
    "depth": 5,
    "method": "llm-disambig",
    "broader_qids": ["Q1"],
    "pagerank": 0.03,
    "first_seen": "2026-06-01T00:00:00Z",
    "last_seen": "2026-07-01T00:00:00Z"
  },

  "salience": 12.4,
  "salience_owner_refs": 3,
  "salience_other_refs": 1,
  "salience_statements": 7,
  "salience_opinions": 2,

  "statements": {
    "total": 7,
    "by_kind": {
      "declarative": 3,
      "procedural": 1,
      "experiential": 1,
      "preference": 2,
      "intention": 0
    },
    "by_epistemic": {
      "fact": 5,
      "opinion": 2
    },
    "representative": [
      {
        "statement_id": "statement-uuid-1",
        "text": "I tried X in production.",
        "predicate": null,
        "epistemic": "fact",
        "statement_kind": "experiential",
        "confidence": 0.92,
        "valid_time": null,
        "created_at": "2026-06-15T00:00:00Z",
        "provenance_message_ids": ["message-uuid-1"]
      }
    ]
  },

  "evidence_refs": [
    "statement:statement-uuid-1",
    "message:message-uuid-1"
  ]
}
```

현재 API convention에 더 잘 맞는다면 shape는 flat하게 바꿀 수 있다. 중요한 것은
ownership이다. 위 필드는 모두 memory fact이거나 bounded memory-derived aggregation이다.


> **Update 2026-07-14 (#64) — 이 추가는 부분 shipped·남은 ask 재정의.** memory-api의 cross-owner grounding
> 검색이 이미 존재: `GET /personal/groundings/{qid}?owner_ids=…`(생략 시 전 owner)
> → `Page[GroundingMatch]{owner_id, entity: PersonalEntitySummary}`, 그리고 `PersonalEntitySummary`가 이제
> `Competence` 벡터 + Tier-2 신호(#64)를 보유. 아래 "recommendation-signals" shape의 상당수(grounding
> facts, statement-kind counts, experiential 비중, `last_seen`, `support_ids`)가 이 라우트로 **이미
> 제공**됨 — 별도 `/recommendation-signals` 엔드포인트는 불필요할 수 있음.
> - **Superseded:** 독립 라우트 제안(기존 `/personal/groundings/{qid}` + competence projection 선호).
> - **남은 ask (memory-api):** query-time relevance `_score` projection(tie margin); `support_ids`의
>   evidence-ref **노출·dereference 계약**(statement/message id·tenant/owner 경계).
> - **남은 작업 (discovery/bourbon-api/persona, memory-api 아님):** **competence→`AgentTopicEdge` translation
>   layer** + 진짜 갭 — eligibility(discoverable/privacy/safety)·stance axis/dir/confidence(`sentiment`은
>   stance 축 아님). `agent_id`는 owner_id 파생 유지.
## 필요한 signal 그룹

### 1. Candidate 식별 정보

필수:

```text
owner_id
personal_entity_id
anchor_id / knowledge_qid
```

`owner_id`만으로 충분하다. `agent_id`는 memory-api의 필수 항목이 **아니다**: memory에는
agent 개념이 없고, recommendation API의 `agent_id`는 `bourbon-api`를 통해 `owner_id`에서
파생 가능하다(`personal_agent_id(owner_id)`, 결정적 `uuid5`). 따라서 agent 식별자는 memory
계약 밖에 둔다.

이 계약에는 `agent_id`도 `routing_target`도 포함하지 않는다. agent와 라우팅은 `memory-api`가
아니라 `bourbon-api`가 소유한다.

### 2. Public Grounding Raw Facts

필수:

```text
grounding.source
grounding.confidence
grounding.margin
grounding.depth
grounding.method
grounding.broader_qids
grounding.pagerank
grounding.first_seen
grounding.last_seen
```

Recommendation은 이를 이용해 다음을 도출한다.

```text
freshness
grounding quality contribution
maturity contribution
evidence_strength contribution
```

Memory API는 timestamp와 grounding fact를 노출해야 하며, freshness score나 최종 quality
score를 제공하면 안 된다.

### 3. Salience Raw Facts

필수 (`PersonalEntity`의 실제 필드명):

```text
salience              (합성 float 점수)
salience_owner_refs
salience_other_refs
salience_statements
salience_opinions
```

이 값들은 이미 `PersonalEntity`에 flat 필드로 존재하지만(중첩 객체가 아님) 현재
`PersonalEntitySummary`에는 노출되지 않는다. projection이 이를 노출해야 한다. 저장된
memory evidence를 설명하는 값이므로 recommendation policy가 아니라 허용 가능한
memory-derived aggregation이다.

Recommendation은 이 필드들이 maturity, evidence strength, ordering에 얼마나 영향을
줄지 결정한다.

### 4. Statement Evidence Raw Facts

필수:

```text
statements.total
statements.by_kind
statements.by_epistemic
statements.representative[]
```

각 representative statement는 다음을 포함해야 한다.

```text
statement_id
text
predicate
epistemic
statement_kind
confidence
valid_time
created_at
provenance_message_ids
```

현재 API와 비교: `StatementSummary`는 이 id를 `statement_id`가 아니라 `id`로 노출하며
`created_at`은 포함하지 않는다. 새 projection은 이를 `statement_id`로 alias(또는 `id` 유지)
하고 `created_at`을 추가해야 한다.

projection은 agent-recommendation이 다음 값을 도출할 수 있을 만큼 충분한 representative
statement를 포함해야 한다.

```text
experience_source_type
experience_specificity
observed_stance
stance_axis
stance_summary
stance_confidence
```

Memory API는 이 필드들이 이미 저장된 memory annotation으로 존재하는 경우가 아니라면
직접 계산하면 안 된다. 초기 계약에서는 raw statement evidence만으로 충분하다.

### 5. Evidence References

필수:

```text
evidence_refs: list[str]
```

이 값은 후보를 뒷받침하는 memory evidence를 식별해야 한다.

허용 가능한 reference:

- statement id
- provenance message id
- 나중에 resolve 가능한 stable memory ref

필요한 이유:

- recommendation reason
- decision-log audit record
- 잘못된 추천 디버깅
- future eval replay

### 6. Visibility (보류 — 초기 계약에 미포함)

`memory-api`에는 현재 personal entity/statement에 visibility/discoverability 필드가
없으므로 **이 계약에서 제외한다**. memory가 그런 fact를 모델링하기 전까지, Agent
Recommendation은 반환된 모든 후보를 source material로 사용 가능하다고 가정하고(memory
visibility를 암묵적으로 `true`로 취급) 그 위에 자체 eligibility gate를 적용한다. 향후
memory가 exposure fact를 추가하면 그때 optional raw annotation으로 도입할 수 있다.

## Memory API가 소유하면 안 되는 것

### Maturity, Evidence Strength, Freshness Score

Memory API는 최종 값으로 다음을 반환하면 안 된다.

```text
maturity
evidence_strength
freshness
maturity_band
```

이 값들은 recommendation policy에 따라 달라진다.

- gate threshold
- maturity band
- need-specific ordering
- decay formula
- eval ratchet
- future product tuning

같은 raw memory fact라도 다음 need에 따라 다르게 해석될 수 있다.

- depth
- experience
- for/against
- coverage

따라서 memory-api는 raw evidence를 제공하고, agent-recommendation이 policy score를
계산해야 한다.

### Experience Ranking Fields

Memory API는 최종 값으로 다음을 반환하면 안 된다.

```text
experience_source_type
experience_specificity
```

Memory API는 experiential statement와 provenance를 반환해야 한다. Agent Recommendation은
현재 need에서 그 statement가 first-hand인지 second-hand인지, 그리고 experience가 얼마나
specific한지 결정해야 한다.

### Stance Matching Fields

Memory API는 최종 값으로 다음을 반환할 필요가 없다.

```text
observed_stance
stance_axis
stance_summary
stance_confidence
```

for/against는 사용자 요청에 상대적이다.

```text
need=for      -> user_stance.dir와 같은 방향
need=against  -> user_stance.dir의 반대 방향
```

Memory API는 opinion/preference statement, statement confidence, provenance를 제공해야
한다. Agent Recommendation은 observed stance를 도출하고 request-specific stance filter를
적용해야 한다.

향후 Memory가 stance annotation을 memory fact로 저장하게 되면 optional raw annotation으로
추가할 수 있다. 그래도 recommendation policy를 encode하면 안 된다.

### Final Eligibility

Memory API는 최종 recommendation eligibility verdict를 결정하면 안 된다.

초기 계약은 memory visibility fact를 노출하지 않으므로(위 "Visibility" 참조), Agent
Recommendation은 후보가 사용 가능하다고 가정하고 eligibility gate를 전적으로 소유하며 다음을
결합한다.

- agent availability (`bourbon-api`를 통해)
- product discoverability policy
- safety policy
- request-specific gate
- maturity와 evidence threshold

### Routing Target

`routing_target`은 계약에서 완전히 제거한다 — `memory-api`도 `agent-recommendation-api`도
저장/반환하지 않는다.

Recommendation은 `agent_id`를 반환한다. `bourbon-api`에서 agent는 endpoint/room/channel
필드를 갖지 않는다: dispatch는 AMQP task 기반(routing key `agent.{type}`)이며 호출 시점에
`agent_id`와 room context로 해석된다. 저장된 `routing_target`은 항상 빈 값/미사용이 되므로
계약에서 제거하고 `bourbon-api`가 `agent_id`로부터 dispatch를 해석하게 한다.

agent-recommendation 후속: `routing_target`은 현재 `AgentTopicEdge`와 `RecommendationItem`의
필수 필드다. 계약에서 제거하면 edge와 응답에서 해당 필드를 제거해야 한다.

### Persona

Persona는 별도 주제로 다룬다.

`PersonaPrior`는 agent-recommendation에 존재하지만, Alpha ranking에서는 no-op reserved
slot이다. 따라서 초기 memory-api recommendation-signal projection에 persona를 포함할
필요는 없다.

향후 persona 계약은 독립적으로 논의할 수 있다.

```text
GET /agents/{agent_id}/persona-prior
```

## 왜 Memory API가 이 Projection을 제공해야 하는가

### 1. Memory API가 원천 데이터를 소유한다

필요한 원천 데이터는 memory-api 내부에 있다.

- `PersonalEntity`
- `GroundingLink`
- `Statement`
- statement kind
- statement confidence
- salience component
- provenance message id
- grounding timestamp

agent-recommendation이 이 값을 여러 low-level call로 직접 재구성하면 memory-api 내부에
결합된다.

원하는 의존 방향은 다음이다.

```text
memory-api storage/internal models
  -> memory-api raw signal projection
  -> agent-recommendation policy/ranking
```

아래 구조는 피해야 한다.

```text
agent-recommendation
  -> many memory-api internals
  -> ad hoc reconstruction
```

### 2. QID 단위 집계는 Memory API 쪽이 더 효율적이다

전용 projection이 없으면 recommendation은 다음 fan-out을 수행해야 한다.

```text
GET /personal/groundings/{qid}
  -> for each personal entity:
       fetch statements
       fetch provenance
       fetch statement-kind counts
       fetch grounding timestamps
       fetch salience components
```

이는 request path에서 N+1 fan-out을 만든다.

Memory API는 자기 repository와 index 가까이에서 이 signal들을 집계한 뒤, bounded page
하나로 raw recommendation input signal을 반환할 수 있다.

### 3. Ownership Boundary를 보존한다

Memory API는 memory fact와 memory-derived read projection을 소유해야 한다.

Agent Recommendation은 다음을 소유해야 한다.

- `AgentTopicEdge`로의 normalization
- maturity/evidence/freshness formula
- experience derivation
- stance derivation과 stance filtering
- gate threshold
- lexicographic ranking
- decision-log record
- final API response shape

이렇게 나누면 두 서비스가 독립적으로 진화할 수 있다.

## 목표 Integration Flow

실제 경로는 다음이 된다.

```text
1. agent-recommendation receives topic_text and need_type
2. agent-recommendation uses memory-api /knowledge/entities* to resolve QID
3. agent-recommendation asks memory-api for QID-level raw recommendation signals
4. agent-recommendation derives AgentTopicEdge fields from raw memory signals
5. agent-recommendation applies eligibility, gate, and ranking policy
6. agent-recommendation returns ranked agent_id list with reasons/evidence refs
```

요약하면:

```text
memory-api:
  "QID Q42에 대해 memory evidence가 있는 owners와 그들을 평가하는 데 필요한
   raw evidence는 이렇다."

agent-recommendation-api:
  "사용자 need와 ranking policy를 적용하면 추천 순서는 이렇다."
```

## Memory API 최소 Acceptance

첫 유용한 버전은 다음을 제공해야 한다.

- QID input
- paginated list of candidate owners
- `owner_id`
- `personal_entity_id`
- `anchor_id` / `knowledge_qid`
- grounding source/confidence/margin/depth/method
- grounding broader_qids/pagerank
- grounding first_seen/last_seen
- salience score와 component count (`salience`, `salience_owner_refs`,
  `salience_other_refs`, `salience_statements`, `salience_opinions`)
- statement kind와 epistemic type별 count
- text, confidence, kind, epistemic type, timestamp, provenance message id를 포함한
  representative statement evidence
- evidence refs

명시적으로 제외하는 것:

- `agent_id` (`bourbon-api`를 통해 `owner_id`에서 파생)
- `routing_target` (계약에서 제거; `bourbon-api`가 dispatch 해석)
- memory visibility / discoverability (memory가 모델링하기 전까지 보류;
  agent-recommendation은 `true`로 가정)

미룰 수 있는 것:

- final maturity score
- final evidence_strength score
- final freshness score
- final experience_source_type
- final experience_specificity
- final observed stance와 stance confidence
  - 단, 이를 미룬다면 raw opinion/preference evidence는 먼저 노출해야 한다.
- final eligibility verdict
- persona prior

## 요약

Memory API는 topic grounding에 필요한 public knowledge substrate를 제공한다. 단 공개 엔티티 **검색
relevance**에 gap이 있어(cross-language/alias 정본 누락 — 위 "공개 엔티티 검색 relevance" 섹션), 그
개선이 grounding recall의 선결이다.

부족한 것은 personal knowledge 위에서 QID별 agent-recommendation-oriented raw signal
projection을 제공하는 것이다.

Memory API는 memory-derived candidate source material을 제공하고, Agent Recommendation은
그 source material을 `AgentTopicEdge`로 변환한 뒤 policy score를 계산하고 experience와
stance feature를 도출한 다음 agent를 rank해야 한다.
