# Memory API Requirements for Agent Recommendation

## Purpose

This document defines the minimum contract `bourbon-memory-api` should provide so
`bourbon-agent-recommendation-api` can run the real candidate path without
reconstructing memory internals.

The service boundary is:

- `memory-api` owns memory facts and memory-derived read projections: personal
  entities, public grounding links, statements, statement kinds, timestamps,
  provenance, and salience components. It returns `owner_id`, never `agent_id`.
- `agent-recommendation-api` owns recommendation policy and request-time
  derivation: maturity, evidence strength, freshness score, experience ranking,
  stance matching, eligibility gates, ordering keys, the `owner_id -> agent_id`
  resolution (via `bourbon-api`), and final response assembly.

Memory API should not rank agents and should not return an `AgentTopicEdge`
directly. It should expose a bounded raw-signal projection that lets
agent-recommendation compute `AgentTopicEdge` candidates itself.

## What Memory API Already Provides

The public knowledge anchor path is already sufficient for recommendation.

`agent-recommendation-api` can use the existing knowledge routes as its
`KnowledgeEntityProvider` substrate:

- `GET /knowledge/entities`
- `GET /knowledge/entities/suggest`
- `GET /knowledge/entities/{qid}`
- `GET /knowledge/entities/{qid}/connections`
- `GET /knowledge/articles`

This supports:

```text
topic_text
  -> public entity search/suggest
  -> resolved QID anchor
  -> public neighbor expansion
```

No major additional memory-api work is required for public anchor grounding.

## What Agent Recommendation Computes

The recommendation pipeline ultimately needs internal `AgentTopicEdge`
candidates:

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

Those fields are not all Memory API responsibilities.

Memory API should provide only the raw material needed to derive them.
Agent Recommendation should compute the recommendation-facing values at request
time, because they depend on need type, thresholds, policy tuning, and the
user's stance reference.

`agent_id` is not a Memory API field. Memory returns `owner_id`; Agent
Recommendation resolves the owning user's personal agent through `bourbon-api`,
whose `agent_id` is a deterministic `uuid5` of the owner
(`personal_agent_id(owner_id)`). This assumes memory-api's `owner_id` is the
platform user id (i.e. `bourbon-api` `users.id`) — a shared-namespace assumption
to confirm with the memory team. Agent identity stays out of the memory contract,
the same way routing does.

`routing_target` is removed from the contract entirely — neither `memory-api` nor
`agent-recommendation-api` stores or returns it. Recommendation returns `agent_id`
(plus reasons/evidence refs); `bourbon-api` resolves dispatch from `agent_id` at
runtime (agents carry no endpoint field; routing is AMQP task-based on agent type
+ room context). See "Routing Target" below.

## Why Existing `/personal/groundings/{qid}` Is Not Enough

Memory API currently exposes a close but insufficient route:

```text
GET /personal/groundings/{qid}
```

It returns personal entities grounded to a public QID:

```text
qid -> owner_id -> PersonalEntitySummary
```

That is useful source material. It includes signals such as:

- `owner_id`
- personal entity id / label
- `knowledge_qid`
- grounding `confidence`
- grounding `margin`
- grounding `depth`
- `broader_qids`
- `pagerank`
- `salience`

But this is still a personal-entity grounding projection, not a recommendation
input projection. It omits the raw material needed to compute recommendation
features:

- grounding timestamps for freshness derivation
- salience component counts (already on `PersonalEntity`, not in this projection)
- statement counts by kind and epistemic type
- statement text/confidence/provenance for experience and stance derivation
- evidence refs for explanations, decision logs, and eval replay

## Required Memory API Addition

Memory API should expose an agent-recommendation-oriented raw signal projection
for a public QID.

Possible route names:

```text
GET /personal/agent-topic-signals/{qid}
```

or:

```text
GET /personal/groundings/{qid}/recommendation-signals
```

The response should be a paginated list of candidate owners with
memory-derived raw signals. It should not be `AgentTopicEdge` and should not
contain final recommendation scores.

Example shape:

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

The shape can be flattened if that better matches current API conventions. The
important part is ownership: all fields above are memory facts or bounded
memory-derived aggregations.

## Required Signal Groups

### 1. Candidate Identity

Required:

```text
owner_id
personal_entity_id
anchor_id / knowledge_qid
```

`owner_id` is sufficient. `agent_id` is intentionally **not** required from
memory-api: memory has no agent concept, and the recommendation API's `agent_id`
is derivable from `owner_id` via `bourbon-api` (`personal_agent_id(owner_id)`, a
deterministic `uuid5`). Agent identity therefore stays out of the memory contract.

Do not include `agent_id` or `routing_target` in this contract. Agents and routing
are owned by `bourbon-api`, not `memory-api`.

### 2. Public Grounding Raw Facts

Required:

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

Recommendation will derive:

```text
freshness
grounding quality contribution
maturity contribution
evidence_strength contribution
```

Memory API should expose timestamps and grounding facts, not a freshness score
or final quality score.

### 3. Salience Raw Facts

Required (real field names on `PersonalEntity`):

```text
salience              (composite float score)
salience_owner_refs
salience_other_refs
salience_statements
salience_opinions
```

These already live on `PersonalEntity` as flat fields (not a nested object), but
are not currently surfaced in `PersonalEntitySummary`; the projection should
expose them. They are acceptable memory-derived aggregations because they describe
stored memory evidence, not recommendation policy.

Recommendation will decide how much these fields affect maturity, evidence
strength, and ordering.

### 4. Statement Evidence Raw Facts

Required:

```text
statements.total
statements.by_kind
statements.by_epistemic
statements.representative[]
```

Each representative statement should include:

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

Note vs. the current API: `StatementSummary` exposes this id as `id` (not
`statement_id`) and does not include `created_at`. The new projection should alias
it as `statement_id` (or keep `id`) and add `created_at`.

The projection should include enough representative statements for
agent-recommendation to derive:

```text
experience_source_type
experience_specificity
observed_stance
stance_axis
stance_summary
stance_confidence
```

Memory API should not compute those fields unless they already exist as stored
memory annotations. For the initial contract, raw statement evidence is
sufficient.

### 5. Evidence References

Required:

```text
evidence_refs: list[str]
```

These should identify the memory evidence behind the candidate. Acceptable
references include:

- statement ids
- provenance message ids
- stable memory refs that can be resolved later

These refs are needed for:

- recommendation reasons
- decision-log audit records
- debugging bad recommendations
- future eval replay

### 6. Visibility (deferred — not in the initial contract)

`memory-api` has no visibility/discoverability field on personal entities or
statements today, so it is **excluded from this contract**. Until memory models
such a fact, Agent Recommendation assumes every returned candidate is usable as
source material (treats memory visibility as implicitly `true`) and applies its
own eligibility gate on top. If memory later adds an exposure fact, it can be
introduced then as an optional raw annotation.

## What Memory API Should Not Own

### Maturity, Evidence Strength, and Freshness Score

Memory API should not return final:

```text
maturity
evidence_strength
freshness
maturity_band
```

Those values depend on recommendation policy:

- gate thresholds
- maturity bands
- need-specific ordering
- decay formulas
- evaluation ratchets
- future product tuning

The same raw memory facts may produce different ranking behavior for:

- depth
- experience
- for/against
- coverage

Memory API should expose raw evidence; agent-recommendation should calculate
policy scores.

### Experience Ranking Fields

Memory API should not return final:

```text
experience_source_type
experience_specificity
```

It should return experiential statements and provenance. Agent Recommendation
should decide whether those statements count as first-hand or second-hand
experience for the current need, and how specific that experience is.

### Stance Matching Fields

Memory API should not be required to return final:

```text
observed_stance
stance_axis
stance_summary
stance_confidence
```

For/against is relative to the user's request:

```text
need=for      -> same direction as user_stance.dir
need=against  -> opposite direction of user_stance.dir
```

Memory API should provide opinion/preference statements, statement confidence,
and provenance. Agent Recommendation should derive the observed stance and apply
the request-specific stance filter.

If Memory later stores stance annotations as memory facts, they can be added as
optional raw annotations. They should still not encode recommendation policy.

### Final Eligibility

Memory API should not decide the final recommendation eligibility verdict.

The initial contract exposes no memory visibility fact (see "Visibility" above),
so Agent Recommendation assumes candidates are usable and owns the eligibility
gate outright, combining:

- agent availability (via `bourbon-api`)
- product discoverability policy
- safety policy
- request-specific gates
- maturity and evidence thresholds

### Routing Target

`routing_target` is removed from the contract entirely — neither `memory-api` nor
`agent-recommendation-api` stores or returns it.

Recommendation outputs `agent_id`. In `bourbon-api`, agents carry no endpoint,
room, or channel field: dispatch is AMQP task-based (routing key `agent.{type}`)
and resolved at call time from `agent_id` plus room context. A stored
`routing_target` would always be empty/unused, so the contract drops it and lets
`bourbon-api` resolve dispatch from `agent_id`.

Follow-up for agent-recommendation: `routing_target` is currently a required
field on `AgentTopicEdge` and `RecommendationItem`; removing it from the contract
implies dropping those fields from the edge and the response.

### Persona

Persona should be handled separately.

`PersonaPrior` exists in agent-recommendation, but Alpha ranking treats persona
as a no-op reserved slot. Persona does not need to be part of the initial
memory-api recommendation-signal projection.

A future persona contract can be discussed independently, for example:

```text
GET /agents/{agent_id}/persona-prior
```

## Why Memory API Should Provide This Projection

### 1. Memory API Owns the Source Data

The relevant source data lives in memory-api:

- `PersonalEntity`
- `GroundingLink`
- `Statement`
- statement kinds
- statement confidence
- salience components
- provenance message ids
- grounding timestamps

If agent-recommendation reconstructs these by making multiple low-level calls, it
becomes coupled to memory-api internals.

The desired dependency is:

```text
memory-api storage/internal models
  -> memory-api raw signal projection
  -> agent-recommendation policy/ranking
```

not:

```text
agent-recommendation
  -> many memory-api internals
  -> ad hoc reconstruction
```

### 2. QID-Level Aggregation Is More Efficient in Memory API

Without a dedicated projection, recommendation would need to do this:

```text
GET /personal/groundings/{qid}
  -> for each personal entity:
       fetch statements
       fetch provenance
       fetch statement-kind counts
       fetch grounding timestamps
       fetch salience components
```

That creates an N+1 fan-out pattern on the request path.

Memory API can aggregate these signals closer to its repositories and indices,
then return one bounded page of raw recommendation input signals.

### 3. It Preserves Ownership Boundaries

Memory API should own memory facts and memory-derived read projections.

Agent Recommendation should own:

- normalization into `AgentTopicEdge`
- maturity/evidence/freshness formulas
- experience derivation
- stance derivation and stance filtering
- gate thresholds
- lexicographic ranking
- decision-log records
- final API response shape

This keeps both services independently evolvable.

## Target Integration Flow

The intended real path becomes:

```text
1. agent-recommendation receives topic_text and need_type
2. agent-recommendation uses memory-api /knowledge/entities* to resolve QID
3. agent-recommendation asks memory-api for QID-level raw recommendation signals
4. agent-recommendation derives AgentTopicEdge fields from raw memory signals
5. agent-recommendation applies eligibility, gate, and ranking policy
6. agent-recommendation returns ranked agent_id list with reasons/evidence refs
```

In short:

```text
memory-api:
  "Here are the owners with memory evidence for QID Q42, plus the raw
   evidence needed to evaluate them."

agent-recommendation-api:
  "Given the user need and ranking policy, here is the ordered recommendation."
```

## Minimal Acceptance for Memory API

A first useful version should provide:

- QID input
- paginated list of candidate owners
- `owner_id`
- `personal_entity_id`
- `anchor_id` / `knowledge_qid`
- grounding source/confidence/margin/depth/method
- grounding broader_qids/pagerank
- grounding first_seen/last_seen
- salience score and component counts (`salience`, `salience_owner_refs`,
  `salience_other_refs`, `salience_statements`, `salience_opinions`)
- statement counts by kind and epistemic type
- representative statement evidence with text, confidence, kind, epistemic type,
  timestamps, and provenance message ids
- evidence refs

It explicitly excludes:

- `agent_id` (derived from `owner_id` via `bourbon-api`)
- `routing_target` (removed from the contract; `bourbon-api` resolves dispatch)
- memory visibility / discoverability (deferred until memory models it;
  agent-recommendation assumes `true`)

It can defer:

- final maturity score
- final evidence_strength score
- final freshness score
- final experience_source_type
- final experience_specificity
- final observed stance and stance confidence, if raw opinion/preference evidence
  is exposed first
- final eligibility verdict
- persona prior

## Summary

Memory API already provides the public knowledge substrate needed for topic
grounding. The missing piece is a QID-level, agent-recommendation-oriented raw
signal projection over personal knowledge.

Memory API should provide memory-derived candidate source material. Agent
Recommendation should transform that source material into `AgentTopicEdge`,
compute policy scores, derive experience and stance features, and rank agents.
