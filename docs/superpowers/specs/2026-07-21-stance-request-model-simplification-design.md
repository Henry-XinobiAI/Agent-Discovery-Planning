# Stance request-model simplification — design

**Date:** 2026-07-21
**Status:** design (pre-B6). Alpha is internal / pre-deployment, so the external contract is changed directly with **no compat alias**.

**Supersede scope** relative to `2026-07-20-agentic-stance-retrieval-design.md`. This document changes:

- **§D1 request normalization** — the `user_stance_ref` grammar and `UserStanceRef` become a single `proposition: str` field.
- **§D3 query-generation input** — `LLMStanceQueryGenerator.generate` drops `dir_`; its signature and direction handling change.
- **§D4 judge verdict + ranker adapter** — verdict becomes absolute (`supports | opposes | insufficient`), no `requested_direction`; the adapter maps by `need_type`, not by `aligned→user.dir`.
- related **vocabulary** (drop reasons, decision-log stance view) and the **eval adapter** (`EdgeMirrorStanceEvaluator`, corpus scenarios).

It leaves **unchanged**: §D2 eligibility-first, §D5 silence / insufficient-vs-error separation, and §D6 evidence-search retrieval contract. Those sections remain the source of record.

## Motivation

The for/against contract currently carries two direction-bearing inputs:

- `UserStanceRef.dir` — the user's *own* reference stance on an axis.
- `need_type` (FOR/AGAINST) — whether to find agents on the *same* or *opposite* side of that stance.

But the search/judge only ever consumes a single derived bit — the **target position on the proposition** (support it, or oppose it). `(dir, need_type)` is a redundant XOR encoding of that one bit:

| dir | need_type | target |
|-----|-----------|--------|
| for | for | supports P |
| against | against | supports P |
| for | against | opposes P |
| against | for | opposes P |

`dir` is used nowhere except to compute the target (and to be logged). **No expressiveness is lost by removing it:** a client wanting "agents who agree with me / disagree with me" computes `need_type` itself from `(my stance ⊕ same/opposite)` and sends the proposition. Only a redundant server-side field disappears.

Removing `dir` also collapses a chain of complexity that existed only to carry it: the `user_stance_ref` grammar (`axis=…; dir=…; text=…`), the `UserStanceRef` wrapper, and the Phase 8-3 free-form stance normalizer (whose whole job was extracting `axis` + `dir` from free text). With `dir` gone and the proposition passed directly, none of them has a remaining reason to exist.

It also makes the judge verdict **absolute with respect to the proposition** (`supports | opposes | insufficient`) instead of relative to a `requested_direction` — which removes, at the root, the aligned/opposed ambiguity and the double-encoded-direction hazard that the B5 review had to guard against.

## New request contract

```json
{
  "topic_text": "원자력 발전",
  "need_type": "against",
  "proposition": "원자력 발전 설비를 확대해야 한다."
}
```

- `topic_text` — unchanged: the groundable anchor (→ Wikidata QID → owner shortlist / search scope).
- `proposition` — **new top-level field**, replacing the `user_stance_ref` string. The claim the judge evaluates. Required and non-blank for a for/against need; absent/ignored for depth/experience/coverage.
- `need_type` — the **sole** direction: `for` = agents who **support** the proposition, `against` = agents who **oppose** it. (Non-stance need types unchanged.)

The proposition may be a full declarative sentence *or* a bare phrase ("원전 확대"); the judge handles both (it already caps/validates and judges from statement texts). The system does **not** rewrite a phrase into a sentence in the correctness path — if that need is confirmed later, an *optional* proposition rewriter can be added, off by default.

## Internal contract

- **`NormalizedQuery.proposition: str | None`** replaces `NormalizedQuery.user_stance`. Normalization for a for/against need = "require a non-blank `proposition`, carry it"; no grammar parsing, no LLM fallback. `normalize_query` stays **sync** (the async sibling existed only for the LLM normalizer and is removed).
- **Two distinct enums, deliberately not merged:**
  - **`StanceVerdictLabel`** = `supports | opposes | insufficient` — the *judge's* output, which must be able to say "I can't tell".
  - **`StancePosition(StrEnum)`** = `supports | opposes` — a *resolved* position on the proposition, the only thing a surviving candidate can carry. `insufficient` is a drop, never a stored position.

  Reusing `StanceVerdictLabel` on the `Candidate` would let `insufficient` leak into a served position; reusing the legacy `Stance` (for/against) would re-mix the for/against semantics `dir` removal just eliminated. So: **judge → `StanceVerdictLabel`; `Candidate` / `StanceView` → `StancePosition`.**
- **Judge verdict:** `LLMStanceJudge.judge(*, proposition, statements) -> StanceVerdict | None` — **no `requested_dir`**. The verdict is the person's relation to the proposition, full stop.
- **B6 filter (verdict → position):** map `supports → StancePosition.SUPPORTS`, `opposes → StancePosition.OPPOSES`; keep a candidate iff its position is the one `need_type` requires (`for → SUPPORTS`, `against → OPPOSES`); `insufficient` (or the wrong position) is a drop. No `aligned→user.dir` / `opposite(user.dir)` mapping.
- **`Candidate` query-time fields:** `stance_proposition: str | None`, `stance_position: StancePosition | None`, `stance_confidence: float | None`. (`stance_axis`/`stance_dir` renamed/retyped accordingly. All `None` until an evaluator runs → `stance_unevaluated` drop, unchanged.)
- **Response `StanceView { proposition: str, position: StancePosition }`** replaces `{ axis, dir }`.
- **Ranker drop reasons:** `stance_unevaluated`, `wrong_stance` (position ≠ the one `need_type` requires), `low_stance_confidence`. **`off_axis` is removed entirely** — there is no separate axis-match step; the judge subsumes "is this even about the proposition" via `insufficient`. (This supersedes the earlier `off_axis → off_proposition` rename idea: with `dir` gone and no axis-match, the concept disappears rather than being renamed.)
- **B4 query generator:** `generate(*, topic, proposition)` — `dir_` removed. Symmetric neutral/support/oppose search-phrase generation is unchanged (still symmetric; the direction to *keep* is decided later by `need_type` on the verdict, not at generation).

## Removed

- `Query.user_stance_ref` and the `axis=…; dir=…; text=…` grammar (`_parse_user_stance_ref`, `_ALLOWED_KEYS`, `_require_directional`).
- `UserStanceRef` struct (dir, raw `text`, query-side parse `confidence` — all gone; no requester-stance audit field).
- `StanceNormalizer` Protocol, `LLMStanceNormalizer` (`stance_normalize.py`), `STANCE_NORMALIZER_ENABLED`, and `normalize_query_async` + its pipeline/composition-root plumbing. **This deletes the shipped-but-dormant Phase 8-3 feature**, whose sole purpose (free-text → axis+dir) no longer exists.
- `requested_dir` (B5) and the double-encode guards / direction-neutral-proposition prompt guard that only mattered because a second direction field existed. (The proposition is still a neutral claim, but there is no longer a competing direction field to conflict with it.)
- `off_axis` drop reason (ranker + gate + decision-log vocabulary + tests).
- `Scenario.expected_axis` (struct field + JSON) — a normalization-result check with nothing left to check.

## Preserved

- **Edge / memory-owned fields are untouched (LOCK):** `AgentTopicEdge.stance_axis`, `observed_stance`, `stance_confidence`, and the `SOURCE_OWNER` map. These are the agent-side stance memory owns; they are a different concept from the query-time proposition.
- **`EdgeMirrorStanceEvaluator`** stays an eval-only compatibility adapter reproducing for/against behavior with no live judge. Its mapping is updated to the new fields **and gains an explicit proposition-match guard** — necessary because removing `off_axis` deletes the ranker's old `candidate.stance_axis == query axis` check, and the deterministic gate has no live judge to subsume "is this even about the proposition" via `insufficient`. Contract:
  - **Mirror only when `edge.stance_axis == query.proposition`.** (In eval the proposition is the axis-id string — see the corpus migration — so this is an exact string match, the deterministic stand-in for the judge's relevance test.)
  - On a mismatch, leave the query-time stance fields `None` → the ranker drops the candidate as `stance_unevaluated` (exactly as before, when a different-axis edge failed the old axis check).
  - Convert the observed stance explicitly: `observed_stance=FOR → StancePosition.SUPPORTS`, `AGAINST → StancePosition.OPPOSES`; copy `edge.stance_confidence` unchanged.
  - **Test:** a candidate whose `edge.stance_axis` differs from the scenario's proposition is dropped `stance_unevaluated`, and the recommendation output is identical to the pre-change baseline.

  This removes `off_axis` from the *production* ranker (relevance there is the real judge's `insufficient`) while keeping the eval gate's relevance discrimination intact.
- Judge input bounds, firsthand-honesty (evidence-id subset + ≥1 cited id for a positional verdict), single-owner/entity guard, None≠insufficient, `_insufficient()` factory — all retained from B5.

## Impact on already-committed work (this branch, unmerged)

- **B5** (`d82af5e`) — judge rewritten: verdict `supports/opposes`, drop `requested_dir`, drop the direction-neutrality double-encode guard; prompt simplified to "does this person support or oppose this proposition?". Simpler than the committed version.
- **B4** (`95aebf0`) — `generate` drops `dir_`.
- **B3** (`f70ddfd`) — `Candidate` stance fields renamed/retyped; ranker reads `stance_position`, drops `off_axis`; serving `StanceView`; decision-log stance view. `EdgeMirrorStanceEvaluator` updated.

Because these are unmerged, they are amended forward by new commits on the branch rather than rewritten history.

## Sequencing & guardrails

Two reviewable commits (each compiles + full suite + gate green):

- **C1 — judge/query-gen vocabulary (dormant components).** B5 verdict `supports/opposes` + drop `requested_dir`; B4 drop `dir_`; `StanceVerdictLabel` values. Self-contained (both components are dormant and standalone).
- **C2 — request + pipeline model (atomic).** `Query.proposition`; drop `user_stance_ref`/grammar/`UserStanceRef`/normalizer/`STANCE_NORMALIZER_ENABLED`/async normalize; `NormalizedQuery.proposition`; `Candidate.stance_proposition`/`stance_position`; ranker filter by `need_type` vs `position` (drop `off_axis`); `StanceView {proposition, position}`; decision-log; `EdgeMirrorStanceEvaluator` (with the proposition-match guard above); eval corpus (see migration below); README / OpenAPI examples / parser error messages; all tests. Atomic because the contract change spans these together.

### Eval corpus migration (part of C2)

`eval/corpus/fixtures/scenarios.json` and the `Scenario` struct + builder carry the old model and must migrate together:

- **Remove `Scenario.expected_axis`** (and the `expected_axis` JSON field). It existed to check the *normalization* result against an input axis; with no grammar to parse there is nothing to compare, so the builder uses `scenario.proposition` directly.
- **`user_stance_ref` string → `proposition`** on each stance scenario. In eval the proposition is the **axis-id string** (e.g. `"axis:Q28865"`), not a natural-language sentence — this is what the `EdgeMirrorStanceEvaluator` proposition-match guard compares against `edge.stance_axis`, so the deterministic outcomes are preserved. (Natural-language propositions only reach the real LLM judge in production.)
- **`need_type` via the XOR** of the old `(dir, need_type)`: new `need_type = for` iff the old target was *supports*, else `against`. The stance gold's required position is then read straight from the new `need_type` (`for → SUPPORTS`, `against → OPPOSES`), with no separate axis comparison.
- **Verified baseline preservation:** every stance scenario in the current corpus has `dir=for`, and with `dir=for` the XOR target is *supports* iff `need_type=for` — so the new `need_type` **equals the old `need_type` for all 41 stance scenarios** (`for,for`=21 → `for`; `against,for`=20 → `against`). No outcome moves; the migration is a pure rename/reshape, which is why the gate stays byte-identical.

**Baseline requirement:** the deterministic eval gate reads metrics only (`grounding_top1/top3`, `ambiguous_fallback_rate`, hard gates), none of which depend on the stance-field names or the dir-vs-position encoding. The migration MUST keep the gate **PASS / EXIT 0 / baseline byte-identical** (no `--update-baseline`); the for/against corpus scenarios keep their expected outcomes because the `EdgeMirrorStanceEvaluator` mapping is faithful. This is the primary verification gate for C2.

**Legacy-name sweep (C2 acceptance):** grep the whole repo — including OpenAPI/README/example payloads, parser error strings, decision-log schema, and `eval/corpus/fixtures/*.json` — to confirm no user-side `axis` / `dir` / `user_stance_ref` / `expected_axis` naming survives. Edge/source-owner `stance_axis` is the only `*axis*` name that legitimately remains.
