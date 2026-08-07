# Finding: the agentic grounder's "abstain" is mostly a dropped `qid` field (2026-08-06)

**Status:** open — blocks the C4 grounding-agent turn-on gate. No deployment is affected: the dev overlay does not set `GROUNDING_AGENT_ENABLED`, so the grounder is off in dev and prod. The measurement enabled it locally (measurement activation, `.env`).
**Update 2026-08-07:** the root cause is narrower than first written — the wire schema lists only `confidence` and `confidence_rationale` as `required` and gives `qid` a `"default": null`, so a submission without `qid` is schema-valid and the model is complying, not malfunctioning. See [Root cause](#root-cause-the-wire-schema-marks-qid-optional-added-2026-08-07). That promotes the two-tool split from hardening to the actual fix and puts the planned step order under review. Step 1 (outcome types + gate reasons) is implemented — code `d615391`, branch `feat/grounder-outcome-types`.
**Repo:** bourbon-agent-recommendation-api @ `e8bb0b0`. **memory-api:** dev, port-forwarded to `localhost:8080`, tenant prefix `demo`. **Model:** `google/gemini-3.1-flash-lite` via the e3llm-api proxy.

## What was tried

Ran `e2e-recommend` against the real dev corpus with `GROUNDING_AGENT_ENABLED=on` and
`REAL_EDGE_ENABLED=true`, to measure how often module ① resolves a Korean topic. Six topics, one
synthetic conversation fixture each, replayed N times per fixture.

**Configuration in force** (all code defaults except the two flags above; recorded because the
numbers are meaningless without it): `GROUNDING_AGENT_MAX_CALLS=5`, `GROUNDING_AGENT_CONF_MIN=0.70`,
`GROUNDING_AGENT_GET_CONNECTIONS_ENABLED=false` (so the agent had three usable tools, not four),
`GROUNDING_CONTEXT_MAX_MESSAGES=30` (never binding — the fixtures are 10 and 20 turns),
`STANCE_JUDGE_ENABLED=off`, `REASON_GENERATOR_ENABLED=off`, `STAGE` unset.

## The finding

**36% of runs ended in `GroundingFailedError: agentic grounder abstained`, and almost none of them
were the model declining.** The model searched, fetched the entity, and submitted a grounding that
named the right QID in its own `reason` and `evidence_qids` — while omitting the `qid` field itself.

Paced sweep (6 topics x 6 runs, 4s apart, stderr captured):

| topic | n | adopted | abstain (clean) | abstain (proxy error) | resolved |
| --- | --- | --- | --- | --- | --- |
| 커피 | 6 | 0 | 6 | 0 | — |
| 마이크로서비스 | 6 | 6 | 0 | 0 | `Q18344624` x6 |
| 자바스크립트 | 6 | 2 | 4 | 0 | `Q2005` x2 |
| 파이썬 | 6 | 5 | 1 | 0 | `Q28865` x5 |
| 제주 흑돼지 | 6 | 6 | 0 | 0 | `Q6176553` x6 |
| 한강 | 6 | 4 | 2 | 0 | `Q55500` x4 |
| **total** | **36** | **23** | **13 (36%)** | **0** | |

`proxy error = 0/36` matters: the grounder degrades an LLM transport failure to the same `None` as an
abstain, so without separating them the rate would have been unattributable.

An earlier unpaced sweep over the **same six fixtures** did not separate them, so it is recorded only
for sample size and to make the 53-adopted figure below traceable — **do not quote it as a rate**
(8 runs per topic, no pacing, stderr discarded):

| topic | n | adopted | abstain (unclassified) |
| --- | --- | --- | --- |
| 커피 | 8 | 0 | 8 |
| 마이크로서비스 | 8 | 8 | 0 |
| 자바스크립트 | 8 | 4 | 4 |
| 파이썬 | 8 | 5 | 3 |
| 제주 흑돼지 | 8 | 8 | 0 |
| 한강 | 8 | 5 | 3 |
| **total** | **48** | **30** | **18** |

The two sweeps agree on the shape (커피 worst, 마이크로서비스 and 제주 흑돼지 clean), which is what
first suggested the cause was not transient load.

### The trace

Replaying the agent's ReAct loop turn by turn on the 커피 fixture, every single time:

```
step 0: search_entities {"queries": ["커피"]}   -> Q8486 first of 20
step 1: get_entity {"qid": "Q8486"}            -> detail=Q8486, membership set = {Q8486}
step 2: submit_grounding {"reason": "...corresponds to the general entity for coffee (Q8486).",
                          "confidence": 1, "evidence_qids": ["Q8486"], ...}
        -> ValidationError: abstain (qid is None) requires abstain_reason
        -> silent None
```

Same pattern reproduced on the 자바스크립트 and 한강 fixtures. **Whenever `qid` was present, the
4-part adoption gate passed on every attempt** (membership / confidence / self-citation /
cited-subset all true), and `confidence` arrived as `1.0` every time.

**The call budget was never the constraint.** Every observed agentic success took exactly three steps
— `search_entities`, one `get_entity`, `submit_grounding` — out of `MAX_CALLS=5`. Two spare turns
already exist for a repair turn to use, which is why step 2 of the plan below needs no new budget.

### Root cause: the wire schema marks `qid` optional (added 2026-08-07)

The original write-up below explained why a missing `qid` *reads as* an abstain. It did not ask why
the model omits it in the first place. Dumping the tool spec the model actually receives answers
that, and the answer is not a model defect:

```json
"required": ["confidence", "confidence_rationale"]
```

```json
"qid": { "anyOf": [{"type": "string"}, {"type": "null"}], "default": null }
```

`submit_grounding` tells the model that **two fields are required**. `qid`, `reason`,
`evidence_qids`, `supporting_observations` and `abstain_reason` are all optional, and `qid` carries
`"default": null`. A submission without `qid` is therefore **schema-valid**: the model complied with
the contract it was given. "The model dropped a field" understates it — the schema does not merely
permit the omission, it offers `null` as the default.

The real contract — `qid` present ⟹ `reason` + evidence; `qid` absent ⟹ `abstain_reason` — lives
**only** in the Python `model_validator`, which never crosses the wire. What does cross the wire
teaches `qid=null` as a meaningful choice three separate times: the schema default, the tool
description (*"or abstain with qid=null"*), and the system prompt (*"To abstain, submit_grounding
with qid=null and an abstain_reason"*). Nothing on the wire says `qid` is normally required. The only
counter-signal is prose in the description, and prose does not beat a schema constraint.

This is consistent with every measurement: judgement was never wrong (**0 QID drift in 53 adopted
runs**), `confidence` — the only required number — was always populated, and the thinner fixture
failed more often, which is what "converge to the minimal schema-valid object" would look like. The
fixture correlation is *consistent with* this mechanism, not proof of it.

**Consequence for the plan:** the two-tool split (`submit_grounding` with `qid` required /
`submit_abstain` with `abstain_reason` required) is the actual fix, not hardening applied after one.
It makes the `required` list itself the contract, so omission becomes structurally impossible. The
repair turn is a mitigation — and one that has to argue against a schema-valid output while the
validator's own message points the wrong way (see the sequence note below).

### Why it reads as an abstain

`GroundingAgentFinal.qid` is `str | None = None` (`discovery/structs/grounding.py`), so **omitting the
field is indistinguishable from deliberately abstaining**. The model validator then demands an
`abstain_reason`, raises, and `_finish` catches it with a bare `except Exception: return None`
(`discovery/grounding_agent.py`). Nothing is logged.

`LLMGrounder.ground` and `_finish` have **eight** `return None` paths between them. Four log
(`grounding_agent_proxy_error`, `grounding_agent_cap_reached`, `grounding_agent_abstain`,
`grounding_agent_gate_failed`) and **four are entirely silent**:

| silent path | trigger |
| --- | --- |
| `if not calls` | no tool call under `tool_choice="required"`, or a malformed tool-call shape (`_parse_tool_calls` returns `None`) |
| `json.JSONDecodeError` | tool-call `arguments` is not JSON |
| `not isinstance(args, dict)` | `arguments` is JSON but not an object |
| `except Exception` in `_finish` | the final fails `GroundingAgentFinal` validation — **this defect** |

**An operator reading the run report sees "abstained" for all eight.** That is how the first two
diagnoses of this measurement — a prompt-quality problem, then proxy contention — both went wrong.
The absence of any `grounding_agent_*` event is itself the signal that one of the four silent paths
fired; that is the cheapest way to recognize this defect today.

### The dominant variable is the conversation, not the topic

Two 커피 fixtures, identical topic string, both plainly about coffee:

| fixture | turns | runs | adopted | abstain |
| --- | --- | --- | --- | --- |
| `fx-b92afba35cdd` | 20 | 16 | 11 | 5 (31%) |
| `fx-cba0cda7b7b8` | 10 | 14 | 0 | 14 (100%) |

The 10-turn one is arguably *more* specific (프렌치 프레스, 중남미 원두 다크 로스팅, 로스팅 후 3–7일).
Nothing in the input explains the difference. **One fixture per topic therefore cannot separate topic
difficulty from fixture difficulty**, and the per-topic column above must not be read as a per-topic
rate.

(A third 20-turn 커피 fixture, `fx-aa65fb208cc8`, held message text byte-identical to
`fx-b92afba35cdd` — the generator produced the same conversation twice — and adopted on its single
run. Fixture ids are listed for the record only: `artifacts/` is gitignored, so none of these files
survives. The reproduction section below regenerates equivalents.)

### Two things that held up

- **No QID drift in 53 adopted runs** (30 in the unpaced sweep + 23 in the paced one). The failure
  mode is silence, never a wrong anchor. This is conditional on runs where a `qid` was actually
  submitted — the rest adopted nothing, so drift is undefined for them.
- **The agentic path finds anchors symbolic grounding cannot.** For 한강, `POST /knowledge/entities/search`
  returns a Joseon-era official and a trot singer in its top 3 — no river. The agent reached
  `Q55500` (Han River) on its own searches. Symbolic exact-label matching is structurally unable to
  ground any of the six topics: they are Korean, and the labels are English.

## Consequence for the plan

**`GROUNDING_AGENT_CONF_MIN` tuning is meaningless until this is fixed.** Confidence arrives as `1.0`
on every observed submission; the gate is not what is rejecting these.

The fix needs an internal contract change. `Grounder` currently returns `GroundingResult | None`
(`discovery/linker.py`), which is why the linker cannot tell the two failures apart, and
`GroundingTrajectory` is attached only to a successful `GroundingResult`, so a failed run's trajectory
is discarded entirely. **The external `/recommend` contract does not change; the `Grounder` -> `Linker`
contract does.**

Two layers of state, and they are not the same set:

- `_finish`: `adopted` / `explicit_abstain` / `adoption_gate_rejected` / **`repairable_invalid`**
- `Grounder` final: `adopted` / `explicit_abstain` / `adoption_gate_rejected` / **`protocol_failure`**

`repairable_invalid` is an intermediate state, not a failure: it is promoted to `protocol_failure`
only when the `GROUNDING_AGENT_MAX_CALLS` budget runs out. Splitting the types this way makes cap
handling fall out as "close the last `repairable_invalid` as `protocol_failure`" rather than a
separate branch.

`adoption_gate_rejected` must **not** be merged into `explicit_abstain`. Neither is repairable, but
"the model withheld judgement" and "the system refused to adopt" are different events to an operator,
and the latter's rate is the key input to `CONF_MIN` tuning. Its detail reasons map 1:1 onto the five
conjuncts of `gate_ok`, and the conjunct order is the contract order:

`qid_not_observed` -> `confidence_below_min` -> `self_citation_missing` -> `evidence_outside_observed`
-> `supporting_observation_blank`

Collected as a `tuple[AdoptionGateFailure, ...]` holding **every** failing reason, not the first: they
are cheap booleans, and simultaneous failures are real information — self-citing an unobserved QID
yields `qid_not_observed` and `evidence_outside_observed` together.

### Planned sequence

1. Outcome types + the five gate reasons — **external behavior preserved**, existing grounder tests
   green unmodified. The harness already exists: `tests/test_grounding_agent.py`'s `_ToolScriptClient`
   scripts a sequence of tool-call responses through `wrapper.set_client`, so the observed failure
   replays as `[get_entity, submit-without-qid, submit-with-qid]`. Its existing
   `test_membership_guard_rejects_unobserved_qid` submits an unobserved QID that self-cites, which is
   exactly the two-reason case — extend it rather than inventing a new one.
2. Repair turn: on an invalid final, return a structured `{field, type, message}` error as a tool
   result (not the raw pydantic text, which echoes the submission back into the prompt) and let the
   model resubmit inside the existing call budget. No separate `MAX_REPAIRS` in v1 — observe
   `repair_attempted` / `repair_succeeded` / cap cause and decide from the distribution.
3. Structured failure attributes, log events, E2E rendering. The reason code and failed trajectory
   ride as **exception attributes, never in the message** — `api/errors.py` puts `str(exc)` straight
   into the 422 body, and `GroundingFailedError.considered` is the existing precedent for a structured
   field that stays out of it. Fold in a rendering gap that exists independently of this defect: on a
   **successful** agentic run the trajectory is already carried in the decision log
   (`discovery/structs/decision_log.py`), and `cli/e2e/report.py` prints only `len(steps)` — the steps
   themselves are discarded by the renderer, not missing from the data.
4. Split the final tool in two: `submit_grounding` (`qid` required) and `submit_abstain`
   (`abstain_reason` required). **This is the real fix** — it makes omission structurally unable to
   impersonate an abstain. Marking a nullable field `required` in JSON Schema is weaker; models keep
   omitting it. Repair still earns its place afterwards as resilience against malformed output, but
   a 36% omission rate must not be carried into serving promotion on repair alone. Step 4 changes the
   tool surface, so it needs its own re-measurement.
5. Re-measure.

#### Sequence under review: step 4 may belong before step 2 (2026-08-07)

The root-cause section above changes the standing of steps 2 and 4. Step 4 removes the cause; step 2
compensates for it. The current order therefore ships the mitigation first and the fix second, and
two concrete facts argue against that:

- **The repair message has to argue against a schema-valid output.** For this exact defect the
  validator produces `[{"type": "value_error", "loc": [], "msg": "abstain (qid is None) requires
  abstain_reason"}]` — no field name, and a message that instructs the model to **add an
  `abstain_reason`** rather than restore the `qid`. Forwarded as-is it would convert a recoverable
  omission into a genuine abstain, and the abstain rate would then look legitimate while the defect
  persisted. Step 2 therefore has to author its own message for a case step 4 deletes outright.
- **Both steps change the tool surface, so both need their own re-measurement.** Doing 4 first
  collapses that to one measurement of the shape we intend to keep, and lets step 2 be measured
  against genuinely malformed output rather than against this defect.

Not yet decided — step 2 is smaller and reversible, whereas step 4 touches the loop's terminal
branch (two tool names to recognize instead of one), splits `GroundingAgentFinal` into two models,
and rewrites the abstain instructions in the system prompt. Schema translation is *not* a risk
there: `convert_schema` only flattens the Pydantic `anyOf: [T, null]` optional pattern to Gemini's
`nullable` and rejects genuine multi-member unions, and two single-model tools introduce neither.
What is settled: **step 1 precedes both** (done, code `d615391`), and repair survives either order as
resilience against malformed output.

Practical note for whichever comes first: `ValidationError.errors()` must be called with
`include_url=False, include_input=False, include_context=False`. The default output embeds the whole
submitted object (model-generated text, echoed back into the prompt) plus a pydantic docs URL, and
its `ctx` holds a `ValueError` instance that makes `json.dumps` raise outright.

### What not to do

**Do not fall back to symbolic on abstain.** With context present the linker is terminal by design
(`discovery/linker.py`) — a context-blind symbolic adopt must never resurrect a QID a context-aware
agent rejected. It would also be useless here: none of the six topics has an exact-label match, so
symbolic produces no winner at all.

### Re-measurement design

Success rate alone is not enough. Record: first-submission success rate, repair attempt and recovery
rate, explicit abstain rate, residual protocol-failure rate, mean call count and added latency, and
QID drift among adopted runs. Use **at least three fixtures per topic** — see the two 커피 fixtures
above.

## Adjacent observations from the same runs

Not part of this finding, recorded here only because they came out of the same dev measurement and
otherwise live nowhere durable. Each deserves its own investigation before being acted on.

- **The 커피 run served entirely from neighbor expansion.** The adopted anchor `Q8486` has **zero**
  owners in the `demo` tenant (verified directly: `GET /demo/personal/entities/Q8486` returns
  `items: []`). Every candidate came from expanded neighbors, and the single survivor sat on
  `Q5398530` (Geisha coffee). So for this topic the whole result rests on the neighbor cap ordering
  contract ([04. retrieval](04-retrieval.md)) — the path the eval corpus never exercises.
- **`Q46` (Europe) appeared as a neighbor of coffee.** It was dropped at maturity 0.05, i.e. **by
  competence, not by relevance** — nothing in the pipeline rejects a topically drifted neighbor. A
  mature owner on `Q46` would have been recommended for a coffee question.
- **The 마이크로서비스 anchor projected nothing despite matching owners.** `Q18344624` matched two
  owners and projected zero: memory-api returned `competence: null` for both
  (`skipped_competence_none=2`, confirmed by direct query). Competence coverage in the demo tenant is
  partial — 19/25 and 13/18 entities for the two owners sampled — so "anchor has owners" does not
  imply "anchor has edges".

## Reproduction

1. Port-forward dev memory-api to `localhost:8080` and e3llm-api to `localhost:8000`.
2. `.env`: `MEMORY_API_PREFIX=demo`, `REAL_EDGE_ENABLED=true`, `GROUNDING_AGENT_ENABLED=true`, `STAGE` unset.
3. `python -m cli e2e-recommend create --topic "커피" --scenario depth --turns 10 --lang ko --requester-owner-id <owner> --yes`
4. Replay the fixture N times with `e2e-recommend run --fixture <path>`, capturing stderr, and classify
   each outcome by which `grounding_agent_*` event appears. **No event at all means one of the four
   silent paths**, which is the signature of this defect. **Pace the replays** (a few seconds apart):
   an unpaced loop against a single local proxy measures its own contention, and a transport failure
   is indistinguishable from an abstain unless `grounding_agent_proxy_error` is being captured.
5. To see which one, mirror the loop: script the same system prompt and `TOOL_SPECS` through
   `wrapper.complete_with_tools`, execute each call with `run_tool`, and validate the final against
   `GroundingAgentFinal` yourself, printing each turn. Until step 3 of the plan above lands, the run
   report cannot show this.

### Finding a usable owner and topic in the `demo` tenant

Non-obvious, and every step above needs it — `--requester-owner-id` must name an owner that actually
exists in the tenant.

- `GET /demo/admin/conversations/participants` lists participant ids (56 at the time; 39 of them own
  personal entities). Conversation participants and personal-entity owners are **not** the same set,
  so confirm per candidate.
- `GET /demo/personal/entities?owner_id=<id>` defaults to `with_statements_only=true` and returned
  **zero** for owners that do have entities. Pass `with_statements_only=false` when enumerating.
- `POST /demo/personal/entities/search` with plain `queries` returned empty for ordinary terms; it is
  not a usable discovery route here. Enumerate per owner instead, or use
  `GET /demo/personal/entities/clusters/{qid}/owners` once a QID is known.
- To pick a topic that will actually produce a recommendation rather than a silence, compute the
  projection the adapter will: `maturity = depth * (0.6 + 0.4 * consistency)` from each entity's
  `competence`, and require it to clear `MATURITY_MIN` (0.45). Scanning the tenant this way found
  `gRPC` (`Q26356541`) with three owners above the floor, which is why it is the fixed topic for the
  deployed-HTTP acceptance — it also has a unique exact label, so it grounds symbolically with the
  agent off.

Raw sweep data and the loop-mirroring probe were session scratch and are not committed; the tables
above and this procedure are the durable record.
