# Objective-to-work planning and executive work selection

**Status: `OBJECTIVE_PLANNING_READY`.** Planning only. Nothing in this branch
runs a worker, activates the live delegation pilot, or touches canonical.

---

## 1. What was broken

The first live-delegation pilot stopped before spending anything, with
`OBJECTIVE_TO_WORK_PLANNING_GAP`. The evidence is
`docs/company_os_first_live_delegation_pilot.md`. What it found:

```
CEO objective
  -> deterministic intake
  -> "outcome": "authorized"
  -> the objective copied verbatim into the work order
  -> acceptance criterion: "The stated objective is implemented: <objective>"
  -> derived plan step: "Identify the smallest contract that the objective is
     missing, and state it before implementing it"
```

Intake bounded the *scope* correctly — capsule, paths, risk, tier — and then
handed the question of **what the work actually is** to the paid developer
session. The acceptance criterion could not be falsified by a reviewer or by
deterministic QA, so nothing downstream could catch it either.

That is not a missing feature. It is an inverted responsibility:

> A worker must never be responsible for deciding what strategic work the
> company should perform merely because the CEO objective is broad.

## 2. The three records, and why they are three

| | Answers | Carries authority? | Lives in |
|---|---|---|---|
| **Objective** | what should be true | no | `company/delegation/objectives.py` |
| **Candidate** | what work exists, and the evidence for it | **no** | `company/delegation/candidates.py` |
| **Work order** | what one person may do, to what, with what budget | **yes** | `company/engineering/work_order.py` |

The candidate is the rung that was missing. Keeping it separate from the work
order is the whole design: a register is safe to keep broad precisely because
registering a candidate authorizes nothing, costs nothing and commits nobody.
A work order must be kept narrow for the opposite reason.

```
CEO objective + planning envelope
    -> eligible_candidates()      ten deterministic constraints
    -> select_work()              one manager, one executive, one record
    -> propose_work_order()       narrowed, never widened
    -> assess_request()           deterministic intake, unchanged
    -> AUTHORIZED / DECISION_REQUIRED / PLANNING_REQUIRED
```

## 3. The candidate register

`WorkCandidate` is frozen, fingerprinted and refused at construction if it
cannot support its own claim. Four refusals:

- **no evidence** — `evidence_refs` must be non-empty. The pilot report found
  that `evidence_refs` elsewhere in this package are hardcoded document paths
  nothing ever opens. Tolerable in a fixture, intolerable in a backlog: a
  register nobody can trace is a wish list, and a wish list is how a company
  invents work for itself.
- **an unfalsifiable problem statement** — the same structural test a work
  order's acceptance criteria face (§6). Say what is wrong in terms somebody
  could confirm or refute, not the direction a fix would move in.
- **BLOCKED with no blocker** — a candidate waiting on something that does not
  say what cannot be unblocked by anyone.
- **OPEN with blockers** — open means selectable. The temptation a register
  creates is to mark everything OPEN so the company always looks busy; this is
  the smallest guard against it.

Six states: `OPEN`, `SELECTED`, `DEFERRED`, `BLOCKED`, `SUPERSEDED`,
`COMPLETED`. Only `OPEN` is selectable. A status change is **a new version, not
an edit** — `DelegationStore.append_candidate` writes it under the same
candidate directory, and `CandidateRegister` keeps the latest, so "why did this
stop being eligible" is a directory listing.

### Sources

`CandidateSource` is closed, because "somebody thought of it" is not a source
and an open vocabulary would let it become one: `reviewer_advisory`,
`validation_report`, `deferred_followup`, `known_defect`, `maintenance_gap`,
`stopped_work`, `backlog_artifact`.

### The capsule-owned backlog view

No capsule schema changed. The register indexes by `capsule_id`, so the
question a manager actually asks is one call:

```
python -m company.delegation candidates --capsule company-engineering-execution
```

## 4. Selection as an action

`ActionType.SELECT_WORK` is new, and it is the point of the whole pass: until
it existed, planning was not an act the authority model could represent, so it
could not be delegated, recorded, bounded or audited.

- **Autonomy rung 3**, the same as `approve_work_order`. A seat that may not
  approve a code change has no business deciding which code changes the company
  makes, and an employee capped below 3 (probation, shadow, dormant) cannot
  plan.
- **Granted to `engineering_manager`, `cto`, `coo`.** Not reserved — ordinary
  selection inside an envelope does not need the CEO.
- **Granted to no worker.** No worker seat holds any grant at all, which is the
  structural form of "workers execute, managers select".

A worker may still *raise* a selection request; `authority.evaluate` walks the
chain upward and the **manager** decides it. And a manager never decides its
own request — "a seat that signs its own work is not a control" — so a
selection raised by the Engineering Manager is decided by the CTO. That is the
target ownership chain falling out of machinery that already existed:

```
CEO objective -> COO / CTO -> Engineering Manager -> work order
```

## 5. Deterministic eligibility

Ten constraints, each named, each a comparison, in `ELIGIBILITY_CHECKS`. No
embeddings, no vector store, no similarity score, no model call.

| Check | Refuses |
|---|---|
| `department_permitted` | a department the envelope does not allow |
| `capsule_owned` | a capsule the index does not confirm — **fails closed** |
| `status_open` | anything not `OPEN`, naming the blocker |
| `risk_within_ceiling` | risk above the objective's ceiling |
| `cost_within_budget` | an estimate over budget, or in another currency |
| `no_forbidden_action` | an action the envelope forbids or the CEO reserves |
| `dependencies_satisfied` | a dependency that is not `COMPLETED` |
| `criteria_falsifiable` | no criterion a reviewer could mark pass or fail |
| `evidence_present` | no evidence refs |
| `goal_overlap` | declared categories that share nothing |

**`goal_overlap` compares declared categories only.** An earlier draft of this
module tokenized the objective's prose title and matched words against the
candidate's tags. That turned a constraint into a keyword filter and rejected
real work for not repeating the CEO's adjectives. If either side declares no
categories the check has nothing to compare and says so, rather than inventing
an affinity out of a sentence.

**Every candidate is measured and none is filtered away.** The rejected ones
are part of the answer: a planning decision that cannot say what it turned down
has not shown its work.

### Eligibility is deterministic; preference is not

`select_work` chooses the single eligible candidate, or the caller's explicit
`prefer_candidate_id` among several. With several eligible and no preference it
**escalates** rather than picking, because preferring one piece of work over
another on no stated grounds is a judgement the company has not delegated to
anything yet. A preference can never override a failed constraint.

`EXECUTIVE_CHOICE_CONTRACT` states what a model-assisted planner would have to
honour to make that judgement instead — inputs, the requirement that the choice
come from the eligible set, and that the planning session counts against the
objective budget. **Nothing calls it. No paid executive session ran in this
pass.**

## 6. The falsifiable-work-order rule

`company/engineering/criteria.py`. One structural question: *does this
objective name something, or only a direction?*

Three closed word lists (`STOPWORDS`, `GENERIC_VERBS`, `ABSTRACT_TERMS`) and one
phrase list (`DEFERRAL_PHRASES`). The check is: after removing the words that
carry no subject, is any subject left? There is no natural-language
understanding here and there should never be.

Three independent ways an objective earns its way through:

1. **It names a subject** — a content word survives the vocabulary.
2. **It carries explicit falsifiable acceptance criteria** — somebody did the
   specifying, whatever the title says.
3. **It is tied to a selected candidate** — the register validated the
   criteria and a planning decision recorded who chose it and why.

### Why a vocabulary and not something cleverer

Every more general alternative was worse. Requiring a file path refuses "add a
field to the engineering result record", which is a perfectly executable work
order the company has been accepting for months. Requiring a symbol refuses
everything written in prose. Scoring the sentence invents a number nobody can
reproduce.

The vocabulary is **this company's current opinion**, in the same sense that
`org_intelligence.ManagementPolicy`'s span of control is an opinion. Section 1
of `tests/test_company_objective_planning.py` pins it in **both** directions:
every objective the existing engineering suites already submit stays accepted,
and every refusal example from the pilot report stays refused. A vocabulary
change that breaks either direction fails there and gets argued about, rather
than being discovered in production.

## 7. `PLANNING_REQUIRED`

A third intake outcome, distinct from `DECISION_REQUIRED` because **the CEO is
not the one who has to act**: an executive or a manager has to select a
candidate first.

```
$ python -m company.engineering request --request-file <the pilot objective>
"outcome": "planning_required"
"reason": "this is an objective, not a work order: the objective defers the
   choice of work to whoever reads it next ('identify the specific work',
   'genuinely useful', 'already-existing', 'must identify'). Choosing which
   work advances an objective is a management decision; it is not the
   developer's to make because the sentence was broad"
```

Precedence: a **reserved action or a credential outranks a planning gap**. The
CEO hears about those, and telling the company to go and plan first would send
it round a loop ending in the same refusal. When both are true, the outcome is
`DECISION_REQUIRED` and the planning reason is recorded beside it.

`open_job` refuses a `planning_required` assessment, so no job, no packet and
no developer attempt can exist for an unplanned objective.

## 8. Work-order generation

`propose_work_order` inherits the objective id, candidate id, evidence
provenance, risk, budget, scope and acceptance criteria.

**Management may narrow. Every widening raises `AuthorityViolation`** — a wider
scope, an invented acceptance criterion, a risk above the candidate's
assessment, a budget above the envelope. The candidate and the envelope are the
two records the finished work will be reviewed against; a work order larger
than both is reviewable against nothing.

The proposal is not a work order. `to_request_dict()` produces the payload
deterministic intake reads, carrying `candidate_id` and `planning_decision_id`,
and intake may still refuse it.

## 9. The audit record

`PlanningDecisionRecord` answers one question: **why did the company choose
this work?** It carries the objective's `intent()` digest, so a decision taken
against one objective cannot be quietly re-attributed to an edited one —
editing a CEO objective is a new objective, and a selection made under the old
one says so.

Three refusals: a `SELECTED` record naming no candidate; a selection outside
the set that was evaluated; and one employee recorded in both the executive and
the manager seat, which is not two layers of review.

`candidate_ids_rejected` holds everything considered and not chosen — including
candidates that were *eligible* and passed over, which are the most interesting
rejections and the ones a naive implementation hides.

## 10. `NO_ELIGIBLE_WORK_CANDIDATE`

An outcome, not a failure. The defect being fixed was a system that produced
*something* for every objective because producing nothing felt like breakage.

A company with no eligible low-risk work should say so and let the CEO decide
whether to fund discovery, widen the envelope, or wait. What it must never do
is manufacture a vague work order so the pipeline has something to carry.

## 11. Selection is not discovery

| | Chooses among | Bounded by |
|---|---|---|
| **Selection** | candidates that already exist | the register — implemented here |
| **Discovery** | the repository, the world | nothing, until somebody bounds it |

This pass implements selection **fully** and gives discovery only the narrowest
contract that lets a future research or planning capability submit a candidate:
`propose_candidate()`, which takes a named proposer, applies every construction
refusal, and **rejects a submission that arrives `SELECTED`**. Discovery may say
"here is work"; only a planning decision may say "we are doing this one".
Collapsing the two would let the capability that invents work also choose it.

There is no repository scanner here, and adding one is a separate authorization.

## 12. The seeded register

Seven candidates, in `company/delegation/candidate_seeds.json`. Every one is
transcribed from a document already in this repository. Nothing was discovered
by scanning code and nothing was invented.

| Candidate | Status | Risk | Why it is classified that way |
|---|---|---|---|
| `reserved-screening-negation-blindness` | OPEN | medium | Real. MEDIUM because the current failure is *over*-escalation, which is fail-safe; trimming it trades a safety margin on the path that decides whether the CEO hears about something. |
| `auth-migration-classifier-ambiguity` | OPEN | medium | Same reason: narrowing a trigger narrows an escalation. |
| `runner-blocked-attempt-repo-dir` | OPEN | low | Genuinely routine — and **no capsule owns `tools/`**. `company-engineering-execution` lists `tools/**` under `must_not_modify`. Rejected on `capsule_owned`, which is the correct answer. |
| `deployment-policy-gap` | BLOCKED | high | A CEO policy decision. Inventing one in code would be the delegation model widening itself. |
| `provider-usage-event-identifier` | BLOCKED | medium | A design decision nobody has taken; needs a schema change, and it belongs to `ai_platform`, not engineering. |
| `runner-zero-required-tests-policy` | BLOCKED | medium | A policy decision about receipt evidence. Also unowned. |
| `intake-unfalsifiable-acceptance-criteria` | COMPLETED | low | Closed by this pass. Kept so the register can show what closing one looks like. |

**Honest classification was the hard part.** Four of seven are not routine
low-risk engineering and say so. A register that marked them OPEN would make
the demonstration look better and the company worse.

## 13. The failed pilot objective, replayed

Planning only. No worker session ran.

**Under the original LOW ceiling:**

```
DECISION: no_eligible_work_candidate

  auth-migration-classifier-ambiguity        rejected: risk_within_ceiling
  deployment-policy-gap                      rejected: status_open, risk_within_ceiling
  intake-unfalsifiable-acceptance-criteria   rejected: status_open
  provider-usage-event-identifier            rejected: department_permitted, status_open, risk_within_ceiling
  reserved-screening-negation-blindness      rejected: risk_within_ceiling
  runner-blocked-attempt-repo-dir            rejected: capsule_owned
  runner-zero-required-tests-policy          rejected: capsule_owned, status_open, risk_within_ceiling
```

This is the honest answer and a useful one. The CEO learns something specific:
**two real engineering candidates sit one rung above the LOW ceiling, and one
LOW-risk candidate is owned by no capsule.** The decision available is to raise
the ceiling, give `tools/` an owner, or fund discovery — not to send a
developer off to find something to do.

**Raising the ceiling to MEDIUM** makes two candidates eligible, and the system
**escalates rather than guessing** between them. With a named preference it
selects, records the decision, derives a bounded work order, and deterministic
intake returns `authorized` — scoped to the candidate's declared paths.

### The replay that proved the candidate was real

Selecting `reserved-screening-negation-blindness` produces a work order whose
title is *"Teach reserved and credential screening to respect negation"*.
Intake refuses it:

```
"the objective names credential material: credential"
```

The word `credential` matched, in an objective about the screening code
itself. **That is the exact defect the candidate describes, catching the work
order that proposes to fix it.** It is the best evidence in this bundle that
the register holds real problems, and it is preserved in
`docs/evidence/company_os_objective_planning/`.

## 14. The deterministic controls are not vacancies

The pilot report listed `deterministic_qa` and `integration_gate` as vacant
seats. Verified: **the architecture was already correct and the reporting was
not.**

Both are `independent_control` seats at `LAYER_RANK` 0, holding no grant, never
a stop on an escalation path. Deterministic QA is `company/engineering/review.py`
computing a verdict; the integration gate is that gate's own CLI producing a
report. Both are code, both already run, and staffing either would replace a
reproducible check with somebody's opinion.

The one thing that was wrong: `org.py` reported their emptiness with the same
sentence it uses for an unfilled management post — *"creating one is
`hire_or_remove_executive_role`, which is CEO-reserved"* — which reads as a
hiring gap. `Seat.is_deterministic_control` now names the case and the standing
explains it. **No availability value, no authority mapping and no escalation
behaviour changed**; these seats held no authority before and hold none now.
`test_planning_does_not_wait_for_a_control_seat_to_be_filled` pins that a full
planning pass reaches a selection with both empty.

No fake employees were created.

## 15. The CEO experience

Before, a broad objective produced a work order and a bill. Now it produces one
of three answers, none of which is a developer guessing:

- **a selection** — with the candidate, the evidence, who chose it, what was
  rejected and why, and a bounded work order ready for intake;
- **`no_eligible_work_candidate`** — with every candidate and the named check
  each one failed;
- **an escalation** — when several candidates are equally eligible, or when a
  preference conflicts with a constraint.

```
python -m company.delegation candidates [--capsule X] [--status open]
python -m company.delegation plan --objective-file obj.json [--prefer ID]
```

Exit codes follow the package convention: 0 answered, 1 escalated or nothing
eligible, 2 malformed input.

## 16. What this pass did not do

- No live delegation pilot ran and no `PilotActivation` was created.
- No paid developer, reviewer or executive session ran. Zero model spend.
- Canonical delegation mode is unchanged (`shadow`).
- `main` and `company-os-v1-bootstrap` are untouched.
- No merge, no deployment, no publishing.
- No discovery capability was built — only its submission contract.
