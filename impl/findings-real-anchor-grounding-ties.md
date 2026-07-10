# Finding: real anchor grounding — exact-label homonym ties (2026-07-08)

**Status:** actioned — the recommended ladder is now implemented (redesigned Phase 8B, dormant). Remaining feed: Phase 9 (real-anchor eval) + post-memory-api 8B tuning.
**Repo:** bourbon-agent-recommendation-api. **memory-api:** `bc9110c` (dev, port-forward `localhost:3000`).

## What was tried

Exercised the `build-anchors` (LIVE capture) → `build-guards` (offline) → `eval run` loop against a
live memory-api, to freeze a **real** anchor fixture locally and confirm the offline pipeline runs on
real data (goal: "live pull → local freeze → verify in tests").

- Freeze tooling works end to end. `cli corpus build-anchors --memory-api-url http://localhost:3000`
  captured 25 real anchors into a valid `PinnedAnchorFixture` (provenance `memory_api_commit=bc9110c`).
- The offline pipeline runs on the real anchors (build-guards + eval run both execute).

## The finding

Running the offline pipeline on the real anchors, **97/136 scenarios fail grounding** with the
identical signature `top confidence=1.00, margin=0.00`. Root cause, quantified:

Of the 25 captured anchors, only **7 ground** under the offline linker (`reranker=None`). Partition of
the 18 failures:

- **16 = exact-label homonym ties.** The canonical entity IS an exact-label match, but the real index
  holds **2–9 entities sharing the same exact label** (categories, journals, list/translation
  articles, disambiguation items). Examples: `Artificial intelligence` ×9, `Astronomy` ×7,
  `Economics` ×5 (Q8134 + Q4530324 + Q3132462 + Q920400 + Q131273890), `Climate change` ×4,
  `Photography` ×3. The symbolic linker assigns confidence **1.0 to every exact-label match**, so
  `margin = top1 − top2 = 0` < the 0.15 adoption gate → `GroundingFailedError`.
- **2 = query/label mismatch.** Seed query carries a parenthetical the label lacks
  (`"Python (programming language)"` vs label `"Python"`, `"React (software)"` vs `"React"`) → 0 exact
  matches → gate fails.

The 7 that ground are the ones whose label is **unique** in the index: PostgreSQL, Kubernetes,
Cryptography, Blockchain, Natural language processing, Computer vision, Data science.

Full excluded list: `bourbon-agent-recommendation-api/tmp/excluded_homonym_ties.json` (scratch, uncommitted).

## Why this is correct behavior, not a bug

- Alpha symbolic grounding deliberately uses **no popularity/importance** signal, so it cannot rank
  one exact-label homonym over another.
- The intended tiebreak for exactly this case is the **LLM rerank fallback**. The offline eval runs
  `reranker=None` on purpose (deterministic, no-LLM, byte-identical baseline — the Phase 8A eval
  contract), so a tie is a **terminal** failure offline.
- Therefore these topics ground in the deployed service (rerank present) but not in offline eval.
- The hand-seeded manual corpus never exhibited this because each seed had exactly one exact match by
  construction — which is also why every manual-seed metric sits at the 1.0/0.0 ceiling. Real anchors
  are what supply genuine ambiguity ("real anchor = teeth").

## Consequence for the plan

- The committed **manual-seed offline gate stays green and remains the correct deterministic regression
  gate.** It was never red; the red run was a real-anchor experiment, not the committed corpus.
- Curating real anchors to a groundable subset yields only **7**, below the corpus builder's `>= 20`
  minimum. A green ≥20 **real-anchor** corpus is not reachable now without either changing eval/linker
  contracts (out of scope for a green restore) or a large hunt for unique-label topics.
- **Do NOT** (for a green restore): inject a reranker into eval (breaks eval determinism), or add an
  importance/pageview tiebreak to the linker (silently changes the adoption contract:
  "exact match ⇒ conf 1.0, margin gate blocks ambiguity"). Both are Phase 9/8B decisions to make
  alongside quality evaluation, not green-restore hacks.

## Recommended behavior — grounding modes + fallback ladder (decided 2026-07-08)

Grounding is redesigned as a **precision core + fallback ladder**, each layer owning a distinct
meaning, log field, and eval treatment. Do NOT collapse distinct meanings into one `method` value or one gate.

**Each layer stamps a distinct `method` in the decision log** (the `method` field IS the mode — there is
no separate `grounding_mode`) — `symbolic` / `rerank` / `expansion` / `best_effort_substitution` — so logs and eval strata can tell
disambiguation from recall-recovery from best-effort substitution. `rerank` is NEVER reused for
expansion or substitution; each also has its own adoption gate.

```
query → [search-only symbolic grounding]   ← deterministic, no LLM (Alpha, now)
          │  adopt ONLY a unique exact-label match
          └─ fail (ambiguous or miss) → fallback ladder (LLM, Phase 8B — implemented, dormant):
               1. rerank                — answer IS in pool but tied → LLM picks intended QID   [disambiguation]
               2. query expansion       — no exact-label answer surfaced → LLM proposes SEARCH TERMS →
                                           re-search /knowledge/entities → re-ground             [recall recovery]
               3. substitution (opt-in) — still unrecoverable → adopt closest related, SIGNALED  [best-effort product]
               4. silence               — if substitution not enabled, fail honestly
```

### Shipped — discovery, deterministic, no LLM (search-only alignment) — ✅ (branch `feat/linker-search-only-grounding`)
- Grounding uses `/knowledge/entities` (search) only. suggest removed from grounding recall +
  confidence (measured recall contribution = 0; suggest = autocomplete per memory-api).
- Confidence: `exact(1.0)` vs `non-exact(0.55)`; retire the both-routes tier.
- **Symbolic adoption REQUIRES an exact-label winner.** Non-exact candidates are evidence/trace and
  rerank input only — **never adopted by symbolic grounding**. Closes the single-non-exact hole: a
  lone `0.55` candidate must NOT be adopted just because its single-candidate margin passes `0.15`.
  Net contract: *symbolic adopts iff there is a unique exact-label match.*
- Ambiguity (multi-exact tie) or miss → symbolic fails → fallback (prod) / terminal (offline eval).

### Next — memory-api, cheap high-leverage, no LLM
- `entity_repository.search` = `multi_match(fields=["label^3","aliases"]) × function_score(importance)`.
  Aliases ARE searched (verified: `SSJS` / `Escript` → Q2005 rank 0–1), but a common term buries the
  canonical entity: `"JavaScript"` → Q2005 absent from top-20 because 20+ entities whose *label*
  contains "JavaScript" win on `label^3` while Q2005 matches only on `aliases` (weight 1), and
  importance does not overcome the gap. Korean-only primary label compounds it (`Q2005 자바스크립트`;
  `자바스크립트` → Q2005 rank 1).
- Fix cheaply: raise the importance weight in `function_score` and/or raise the alias boost so
  high-importance canonical entities beat low-importance label-homonyms; address Korean-only labels
  (populate/boost English label or cross-language match). Consider exposing the existing (route-hidden)
  `search_grounding_candidates` as the grounding contract.
- **Do this first**, then re-measure real-anchor grounding — it may dissolve most misses without any
  discovery LLM work.

### Implemented (dormant) — discovery LLM fallback ladder (redesigned Phase 8B, Tracks 1–4 complete; injected, eval-deterministic-preserving)
This ladder is now **implemented in the code repo** (redesigned Phase 8B, Tracks 1–4 complete):
rerank② is **live in serving** (Phase 8A); expansion③ and substitution④ **shipped opt-in and
DORMANT** (default OFF via `EXPANSION_ENABLED` / `SUBSTITUTION_ENABLED`, wired only in the
composition root, never in eval → `baseline.json` byte-identical; quality measured only in injected
report-only eval strata). Each rung's technical description below is unchanged.
- **rerank (live in serving, 8A):** answer in pool, tied → LLM picks the intended QID → must clear
  `RERANK_*` gate; in-set qid only.
- **query expansion:** miss → the LLM proposes **search terms** (distinctive alias / other-language
  label / synonyms), NOT anchors. Re-search `/knowledge/entities`; the final QID comes from the
  search result and must clear the gate + map to the original topic. The LLM never picks the QID
  directly — it only suggests queries. (E.g. `"JavaScript"` → `"자바스크립트"` → Q2005 recovered at rank
  1.) Runs BEFORE substitution.
- **substitution (opt-in product decision):** answer unrecoverable → adopt the closest related anchor only
  with explicit honesty signals: `method="best_effort_substitution"`, expose original_topic + adopted
  substitute anchor, decision-log `substitution_used` / `original_topic` / `substitute_anchor_qid` / `substitution_reason`.
  Distinct `method`, distinct gate — never folded into `method="rerank"`. Preferred direction: allow,
  but as the LAST resort after expansion, always signaled.

### Eval
- Deterministic gold gate stays as-is (manual-seed, `reranker=None`) = regression floor.
- Real-anchor: disambiguation / expansion-recovery / substitution each a **separate stratum**, judged by
  B2 / human — not by the deterministic gate. Reintroduce the homonym-tie set as a dedicated stratum.

### Sequencing (2026-07-08 plan → current status)
1. ✅ discovery search-only alignment (deterministic, small) — **shipped**.
2. memory-api relevance / alias / cross-language fix — highest ROI; coordinate with their team. **(still pending — their team)**
3. re-measure real-anchor grounding — after step 2.
4. ✅ discovery LLM ladder: rerank → expansion → substitution — **shipped** (Tracks 1–4; rerank live, expansion/substitution dormant/default-OFF).

**Remaining now (2026-07-09):** the ladder _implementation_ (steps 1 & 4) is done. What is left is **measurement + memory-api-gated tuning** — step 2 (memory-api relevance, their team) → step 3 (re-measure real-anchor) → Phase 9 (real-anchor eval into CI) → 8B tuning (thresholds + expansion stratum). This matches the agreed Phase 9 → Phase 10 → 8B-tuning order in `11-phase-8-9-roadmap.md`.

## Spike findings — rerank feasibility + ambiguity behavior (2026-07-08)

Two throwaway probes (scripts in `bourbon-agent-recommendation-api/tmp/`, uncommitted) ran the
**shipped** `LLMReranker` (Phase 8A) against real data — live memory-api + e3llm-api proxy
(`google/gemini-3.1-flash-lite`) — to de-risk rerank hardening before building any eval stratum.

### Spike 1 — rerank on the real homonym ties (`rerank_spike.py`)
Fed the 18 excluded real-anchor queries (16 homonym exact-label ties + 2 in-pool label mismatches)
through `rerank()` and compared the pick to the seed's intended canonical QID.

- **18/18 chose the intended canonical QID**, confidence **0.85–0.98**, margin **0.80–0.97** — all
  clear the `RERANK_*` gate comfortably. Even the worst ties resolved (Artificial intelligence ×9 →
  Q11660, Astronomy ×7 → Q333, Economics ×5 → Q8134).
- **Feasibility: proven.** The LLM separates the canonical concept from the journal / category /
  list-article / sub-topic homonyms.
- **Gate is conservative** (winner ~0.95 vs runner-up ~0.01) — no retune needed for clean cases.
- **Projection is sufficient**: it disambiguated **byte-identical labels** (9× "Artificial
  intelligence") from `label` + `description` alone — no projection enrichment required.
- **Key reframe: the serving path *can* recover these.** All 18 are *in-pool* recoveries (the answer
  is in the candidate set), and the serving path injects a reranker (8A). So the offline
  "**7/25 ground**" was a `reranker=None` **eval artifact** — not evidence that serving cannot ground
  them. This spike shows the mechanism works **under the tested proxy model**
  (`google/gemini-3.1-flash-lite`); the deployed serving default may differ (some planning docs still
  cite `gemini-2.5-flash`), so read this as "mechanism validated," not a production-quality
  measurement. True query-expansion cases (answer *absent* from the pool) = **0** in this corpus;
  that class is exactly what the memory-api relevance fix targets.

### Spike 2 — rerank on genuinely ambiguous topics (`rerank_spike_ambiguous.py`)
Live-captured 8 multi-sense topics (Mercury, Java, Amazon, Python, Apple, Mars, Jaguar, Turkey) —
no single intended sense by construction — to probe the gate's blind spot (it can reject a
low-margin result but **cannot catch a confident-wrong pick**).

- **Abstention is opportunistic, not reliable.** Only **Mercury** abstained (planet Q308 vs element
  Q925 tied at 0.45/0.35 → margin 0.10 < gate → `grounding_failed`). The other six **confidently
  picked** one sense (0.70–0.95, gate PASS): Python → language (Q28865), Mars → planet (Q111),
  Apple → company (Q312), etc. Java/Jaguar/Amazon are just as "ambiguous" to a human, yet the model
  committed. (Turkey was lost to a proxy disconnect — inconclusive.)
- **But no arbitrary / nonsense confident-wrong.** Every confident pick was a **defensible dominant
  sense**. The residual risk is not "wrong about the world" but "**global dominant sense ≠ this
  user's local intent**" (a user meaning Jaguar-the-car gets jaguar-the-animal, gate can't catch it).
- **This is an inherent limit of context-free grounding, not a rerank defect.** With only a topic
  string and no user context, picking the dominant sense is the reasonable default.

### Contract to surface (product decision)
**Rerank grounds to the dominant sense on an ambiguous topic; the margin gate is NOT a reliable
ambiguity safeguard** — it catches ambiguity only when the model happens to spread its confidence
(Mercury), not when it commits to a dominant sense (Java/Jaguar). Mitigation is **user
disambiguation** (a parenthetical like `Python (programming language)`, which rerank handles well —
Spike 1) or **future context-passing**, NOT a rerank redesign. For Alpha the dominant-sense default
is acceptable, but the team must not rely on the gate to prevent confident sense-mismatches.

### Infra note (separate from grounding quality)
Both port-forwarded endpoints showed transient `RemoteProtocolError: Server disconnected` /
`All connection attempts failed` (Turkey's rerank degraded to `None`). In production a proxy failure
makes `rerank` return `None` → `grounding_failed` (works as designed, but **depresses the grounding
success rate**) — an ops/reliability item for Phase 10.

### Implications
- **Not a blocker for building the rerank stratum** (no arbitrary confident-wrong observed in this
  8-topic probe). Whether to *accept* the dominant-sense default is a **separate product decision** —
  this spike does not settle it, and 8 topics is not enough to conclude no redesign is ever needed.
- The **rerank stratum must test both behaviors**: canonical-pick on dominant-sense ties (Spike 1
  set) **and** abstain on balanced ambiguity (a **Mercury-style** case). But don't hard-code the live
  model abstaining on Mercury as gold — that's model/snapshot-dependent. Pin the *deterministic*
  regression with a **fake reranker returning spread scores** (margin < gate → `grounding_failed`);
  keep the live-model behavior on Mercury-style topics as a **report-only observation** in the
  non-deterministic stratum.
- Rerank stratum stays **non-deterministic / injected-reranker / B2-or-human judged**, separate from
  the deterministic manual-seed gold gate (which keeps `reranker=None`).

## Memory-api public search relevance — live findings (2026-07-10)

The Spikes above probe **rerank** (choosing among *recalled* candidates). This section probes the step
*before* it — **`/knowledge/entities` search recall/ranking** — because some real anchors fail to ground
for a reason rerank cannot fix: the canonical entity never enters the candidate set. Tested live against
`localhost:3000`.

### What came back (3 examples)

| query | wanted (canonical) | actual top results | outcome |
|---|---|---|---|
| `JavaScript` | JS language (Q2005, label "자바스크립트") | "JavaScript framework / library / engine / syntax" … | canonical **absent from top-50** |
| `TypeScript` | TS language (Q978185, imp 0.456) | rank 1 = a **disambiguation page** (Q64624307, imp 0.281) | canonical at rank 2 |
| `Python` | Python language (Q28865) | many exact-label "Python" (language / missile / Delphi dragon / snake genus) | rank 1 correct, but by importance alone |

- `q=자바스크립트` (Korean) returns Q2005 at rank 1 → the JavaScript miss is purely **cross-language**.
- Q2005's importance (0.488) is higher than every result shown (0.24–0.40), yet it is buried → ranking is
  dominated by label match, not importance.
- Adding context words does NOT help: `q=python language` "works" only because "language" matches no label
  (inert) and importance already ranked the language #1; `q=javascript programming language` instead pulls
  in generic "programming language" entities and Q2005 stays absent.

### Root cause (current scoring)
`entity_repository.py`: `multi_match(fields=["label^3","aliases"]) × function_score(importance)`, sort
`_score` desc. `importance` = offline wiki-popularity blend (pageview .5 / pagerank .3 / sitelink_count .2).
- **label^3 vs alias^1 asymmetry** → a canonical entity whose label is in another language (query word only
  in `aliases`) loses to any entity carrying the query word in its label.
- **importance is a multiplier, not a rescue** → a higher-importance canonical entity loses when its text
  score is lower (TypeScript).
- **no CJK analyzer** on the entity index; the multilingual `labels` map is stored but not indexed.
- `categories` / `description` ARE returned (a disambiguation page is cleanly tagged `Disambiguation pages`)
  but the **ranking does not use them**.

### Two distinct problems — do not conflate
- **(A) context-independent recall/ranking bug** — JavaScript (cross-language burial), TypeScript
  (disambiguation page #1). A bare query should surface the canonical entity; it doesn't. **Fixable in
  memory-api ranking alone**, no context anywhere. → this is the ask in
  `memory_api_agent_recommendation_requirements*.md` ("공개 엔티티 검색 relevance").
- **(B) context-dependent sense selection** — Python homonyms. Choosing language-vs-snake genuinely needs
  context; the bare `q` interface cannot express intent (see Spike 2's dominant-sense finding). This is NOT
  a memory-api ranking ask.

### Write-side already has context-aware disambiguation (but offline-only)
memory-api's **ingest/build** path has `Grounder.ground(mention, *, context=...)`
(`memory/knowledge/personal/grounding.py`): it feeds the surrounding text + a rich candidate projection
(description / types / abstract) to an LLM, applies a score+margin gate, and returns the best QID. It is
what created the `/personal/groundings` edges. Two caveats for reuse:
- **No request-serving endpoint** — it runs only in the offline per-owner build. Exposing it would be a thin
  HTTP wrapper (the method is self-contained), at the cost of one LLM round-trip per call.
- **Its candidate step reuses the SAME lexical recall** (`label^3` + aliases + `description^0.5`). So problem
  (A) is a prerequisite even for it — if Q2005 isn't recalled, the LLM can't pick it. Context disambiguation
  only helps (B), never (A).

### Consequence for our contract (decision)
Sense selection (B) needs context, but `/recommend` grounding sees only `topic_text` today (the `context`
dict on `Query` is eligibility-scoped and never reaches grounding). So (B) is blocked at our entry
regardless of memory-api. Plan:
- **Reserve an optional natural-language `topic_context` on `/recommend`** — the shape memory-api's grounder
  expects (free text = "the sentence/context the topic arose in", NOT a structured type hint). Additive hook
  now; consume it at rerank-tuning / Phase 10. See [01](01-data-contracts.md),
  [11 §8-7](11-phase-8-9-roadmap.md).
- **Where (B) is resolved is deferred (B-vs-C):** (B) our own rerank consumes `topic_context`; (C) memory-api
  exposes its `Grounder` as a read endpoint and we call it. C's pull: the `/personal/groundings` edges were
  grounded by that same `Grounder`, so grounding the query the same way maximizes QID join-consistency
  (relevant at Phase 10 real edge). The `topic_context` hook is agnostic to B/C — it just carries context
  inward.

**Net asks:** memory-api → **(A) only** (search recall/ranking; prerequisite for everything). discovery →
reserve `topic_context`, decide B-vs-C at Phase 10.
