# Finding: real anchor grounding — exact-label homonym ties (2026-07-08)

**Status:** open finding / feeds Phase 9 (real-anchor eval) and Phase 8B (grounding policy).
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
meaning, log field, and eval treatment. Do NOT collapse them into one `method` / one gate.

**Each layer stamps a distinct `method` / `grounding_mode` in the decision log** —
`symbolic` / `rerank` / `expansion` / `best_effort_proxy` — so logs and eval strata can tell
disambiguation from recall-recovery from best-effort substitution. `rerank` is NEVER reused for
expansion or proxy; each also has its own adoption gate.

```
query → [search-only symbolic grounding]   ← deterministic, no LLM (Alpha, now)
          │  adopt ONLY a unique exact-label match
          └─ fail (ambiguous or miss) → fallback ladder (LLM, Phase 8B/9):
               1. rerank          — answer IS in pool but tied → LLM picks intended QID   [disambiguation]
               2. query expansion — answer NOT in pool → LLM proposes SEARCH TERMS →
                                     re-search /knowledge/entities → re-ground             [recall recovery]
               3. proxy (opt-in)  — still unrecoverable → adopt closest related, SIGNALED  [best-effort product]
               4. silence         — if proxy not enabled, fail honestly
```

### Now — discovery, deterministic, no LLM (search-only alignment; `tasks/todo.md`)
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

### Later — discovery LLM fallback ladder (Phase 8B/9; injected, eval-deterministic-preserving)
- **rerank (built, 8A):** answer in pool, tied → LLM picks the intended QID → must clear `RERANK_*`
  gate; in-set qid only.
- **query expansion:** miss → the LLM proposes **search terms** (distinctive alias / other-language
  label / synonyms), NOT anchors. Re-search `/knowledge/entities`; the final QID comes from the
  search result and must clear the gate + map to the original topic. The LLM never picks the QID
  directly — it only suggests queries. (E.g. `"JavaScript"` → `"자바스크립트"` → Q2005 recovered at rank
  1.) Runs BEFORE proxy.
- **proxy (opt-in product decision):** answer unrecoverable → adopt the closest related anchor only
  with explicit honesty signals: `grounding_mode="best_effort_proxy"`, expose original_topic + adopted
  proxy anchor, decision-log `proxy_used` / `original_topic` / `proxy_anchor_qid` / `proxy_reason`.
  Distinct `method`, distinct gate — never folded into `method="rerank"`. Preferred direction: allow,
  but as the LAST resort after expansion, always signaled.

### Eval
- Deterministic gold gate stays as-is (manual-seed, `reranker=None`) = regression floor.
- Real-anchor: disambiguation / expansion-recovery / proxy each a **separate stratum**, judged by
  B2 / human — not by the deterministic gate. Reintroduce the homonym-tie set as a dedicated stratum.

### Sequencing
1. discovery search-only alignment (deterministic, small) — now.
2. memory-api relevance / alias / cross-language fix — highest ROI; coordinate with their team.
3. re-measure real-anchor grounding.
4. discovery LLM ladder: rerank → expansion → proxy (in that order), with quality eval.
