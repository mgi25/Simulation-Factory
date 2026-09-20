# Executive planning, prioritization and bounded work discovery

**Status: `EXECUTIVE_PLANNING_READY`.** Planning only. No developer, no
reviewer, no live delegation, no merge to canonical.

---

## 1. What was still missing

The objective-planning foundation closed the gap between a CEO objective and an
executable work order — but only for one of the three cases it can produce.

| Case | Before | Now |
|---|---|---|
| exactly one eligible candidate | selected deterministically | unchanged, and now **provably** model-free |
| several eligible candidates | **escalated to a human** | one bounded executive session chooses |
| zero eligible candidates | `NO_ELIGIBLE_WORK_CANDIDATE` | bounded discovery may run first |

A planner that stops whenever it has options has not been delegated anything,
and a company that can only select from a register somebody else filled has no
way to fill it.

## 2. The ordering, which is the design

```
eligible_candidates()          deterministic, always first
  0 eligible  -> discovery, if an envelope authorizes it, else NO_ELIGIBLE
  1 eligible  -> select it. No model. The answer is arithmetic.
  2+ eligible -> ONE bounded executive session, then the deterministic refusals
```

`executive.should_ask_executive` is a named function rather than an `if` buried
in a branch, so *"did this run need a model"* is a question with a testable
answer — and `test_one_eligible_candidate_is_selected_without_any_model` passes
a planner that raises if it is ever called.

This matters more than it looks. The company runs on one consumer
subscription. A session spent confirming the only possible answer is the
clearest waste available to it, and the easiest to write by accident.

## 3. The executive planner

An **executive/management** function. It never implements anything. Its four
possible conclusions are `SELECT`, `DEFER`, `DISCOVER`, `ESCALATE`.

### What it is given, and what it is not

`PlanningBrief` is a closed set of fields assembled from records the company
already holds: the objective and its success metrics, the risk and budget
ceilings, the forbidden actions, and per candidate a title, problem statement,
expected value, risk, resource profile, estimated cost, capsule, dependencies,
acceptance criteria and evidence *references*.

It never receives source files, capsule bodies, a repository root, or a path it
could ask to have read. The real brief for the multi-candidate replay was
**2,876 characters**.

That is not only a cost decision. A planner holding the repository can justify
anything, and a selection justified by something the record does not contain
cannot be audited afterwards.

### Why `ReasoningClass.C`

Small reasoning, deliberately not the specialist tiers. The specialist tiers
exist for work whose difficulty is in the subject matter; this planner's
difficulty is in the trade-off, and the trade-off arrives already summarised. A
company that reaches for its strongest tier to rank three bullet points will
reach for it for everything.

### Why one session and no critic

`MAX_PLANNING_SESSIONS = 1`. No planner swarm, no second opinion, no adversarial
critic. A second session doubles the bill to arbitrate a disagreement nobody has
evidence is occurring, and the deterministic refusals below already catch the
failures a critic would look for. If later evidence shows a critic earns its
cost, that is a change to make with the evidence in hand.

## 4. The model proposes; the policy decides

Everything the planner returns is a **claim**. `assert_choice_within` checks
each claim against the records the planner was given, and **none of the seven
refusals is repaired**:

| Refusal | Why it is not repaired |
|---|---|
| a candidate id outside the eligible set | the reasoning was about something else; re-pointing it keeps the conclusion and discards the argument |
| a different objective than the brief | the answer is not to this question |
| risk above the envelope ceiling | a planner may not widen the ceiling it was given |
| spend above the envelope budget | same |
| an action the envelope forbids or the CEO reserves | authority is granted, never claimed by the thing that wants it |
| a decision name outside the closed set | there is no fifth conclusion |
| output that does not parse | a refusal, not a prompt to ask again |

A refused answer ends the run as `ESCALATED` with the refusal recorded — **and
the cost of the refused session is still recorded**, because a refusal is not
free.

One accommodation exists and is deliberate: a JSON object wrapped in a code
fence is unwrapped. That is *reading*, not repairing; everything above changes
what was said.

## 5. Bounded work discovery

Selection chooses among work the company knows about. Discovery is how the
register gets its first entry, and it is the more dangerous of the two by a
wide margin: selection is bounded by the register, discovery is bounded by
nothing until somebody bounds it.

### `discover_work` is its own action

Separate from `select_work` on purpose: **a seat that may choose from a list is
not automatically a seat that may write the list.**

| Seat | `select_work` | `discover_work` |
|---|---|---|
| `cto` | yes | yes |
| `engineering_manager` | yes | **no** |
| `coo` | yes | no |
| `research_lead` | no | yes |
| every worker seat | no | no |

The Engineering Manager selects and delivers; it does not invent the options it
will then choose between. The Research Lead — whose employee is
`research_opportunity_lead` and whose existing grant is
`approve_research_program` — may open a discovery run and holds no engineering
approval at all, so finding work and authorizing it stay in different hands.

That seat is **dormant**, so discovery is effectively the CTO's today.
Activating it is a CEO workforce decision, and this pass does not take it.

### The discovery envelope

Required at construction: an objective, a department, a non-empty capsule
allow-list, a non-empty surface allow-list, a risk ceiling, a budget, a
**required expiry**, a named authorizer, an authority source, and a candidate
ceiling of at most `MAX_DISCOVERY_CANDIDATES = 8`.

Three refusals: an empty capsule allow-list (*"not a small scope; an unstated
one"*), an empty surface allow-list (*"discovery with no declared surface is
repository exploration"*), and a ceiling above the hard maximum (*"a run that
returns twenty proposals has stopped choosing and started listing"*).

No standing grant. An expired envelope fails every proposal it produced.

### Allowed evidence surfaces

Nine, closed: validation reports, reviewer advisories, stopped-work reports,
deferred follow-ups, candidate-source documents, Company OS evidence records,
capsule metadata, test-failure evidence, known-defect records.

**There is no surface for the repository at large**, and its absence is
asserted by the tests rather than left as a convention. Every member is a place
where somebody already wrote down that a problem exists and attached their name
to it: a candidate traced to one of these can be argued with; a candidate
traced to a TODO comment cannot.

`SURFACE_SOURCES` additionally pins which provenance each surface may produce,
so a proposal cannot claim capsule metadata yielded a reviewer advisory.

### The one bounded reader

`capsule_revalidation_proposals` reads capsule metadata and proposes a
revalidation candidate for each allowed capsule the knowledge layer reports as
stale. It **reuses `CapsuleIndex.needing_revalidation`** rather than
re-deriving staleness from `recheck_on` — that function already weighs the
recheck date *and* the recorded source digests, so a capsule whose code changed
under it is stale even inside its window. Re-deriving it would have been a
second, worse answer to a question the knowledge layer already answers.

It opens at most one small JSON file per allowed capsule. It never opens a
source file, walks a tree, or reads prose.

## 6. Proposal validation — thirteen gates

A proposed candidate becomes `OPEN` only after passing every one:

`envelope_live`, `evidence_exists` (the file is on disk), `surface_allowed`,
`capsule_resolves`, `department_matches`, `problem_concrete`,
`criteria_falsifiable`, `write_scope_bounded` (inside the owning capsule),
`risk_classified`, `resource_profile_known`, `actions_permitted`,
`dependencies_represented`, `not_duplicate`.

**A rejected proposal is rejected.** It does not become a lower-priority
candidate, it does not reach a developer with a caveat, and it is not accepted
because nothing else qualified.

Two subtleties worth stating:

- **Duplicates compare write scope, not wording.** Two candidates proposing to
  change the same files in the same capsule are the same claim however
  differently they are phrased, and wording is the one thing a generated
  proposal varies freely.
- **`COMPLETED`, `SUPERSEDED` and `DEFERRED` do not block a new proposal.** The
  world moved on, and "not now" is not "never".

A run that exceeds its own candidate ceiling is **refused whole** rather than
trimmed to fit, because which ones to drop is the judgement the ceiling existed
to avoid. Two proposals in one run cannot both claim the same work: accepted
proposals join the comparison set as they are accepted.

## 7. The audit record

`PlanningRunRecord` is immutable and answers the CEO's four questions:

| Question | Field |
|---|---|
| what did management choose? | `selected_candidate_id`, `choice` |
| why? | `selection_reason`, `decision_reason`, and the planner's five reasoning fields |
| what other options existed? | `eligible_candidate_ids`, `rejected_candidates` (each with the named check it failed) |
| what did planning cost? | `session`, `planning_cost`, `model_used` |

Plus the objective intent digest, both seats and both employees, the authority
source, the policy version and fingerprint, discovery provenance (envelope id,
surfaces read, candidates proposed and rejected), and any refusal.

Four refusals at construction: a `SELECTED` run naming no candidate; a
selection outside the eligible set; a run that used a model and records no
session (*"planning whose cost is unrecorded is planning the company cannot
budget for"*); one employee in both planning seats.

**Unreported telemetry stays `None`, never 0.** Recording an unreported number
as zero is how a company convinces itself planning is free.

## 8. The CEO page

```
python -m company.delegation plan-run --objective-file obj.json [--discover] \
    [--planner-answer-file session.json]
```

```
OBJECTIVE            obj-intake-classifier-medium-2026-09-20
PLANNING STATUS      selected
ELIGIBLE WORK FOUND  2
CANDIDATES CONSIDERED 7 (5 rejected)
SELECTED WORK        Teach reserved and credential screening to respect negation
WHY SELECTED         Negation handling is a fundamental logical requirement...
DISCOVERY USED       no
EXECUTIVE            cto (chief_architect)
MANAGER              engineering_manager (engineering_delivery_manager)
EXPECTED VALUE       Fewer false CEO escalations on routine work...
RISK                 medium
PLANNING COST        0.028659 USD
READY FOR EXECUTION  yes
CEO DECISION NEEDED  no
```

No register internals unless asked for with `--json`.

## 9. The two replays

### The failed pilot's objective, at its original LOW ceiling

Discovery was authorized and ran over capsule metadata. **Nothing in the two
allowed capsules is stale**, so it proposed nothing, and the run returned
`no_eligible_work_candidate` at **zero model cost**.

The CEO learns something specific rather than nothing: two real engineering
candidates sit one rung above the LOW ceiling, one LOW-risk candidate is owned
by no capsule, and three are blocked on decisions nobody has taken. The
available actions are to raise the ceiling, give `tools/` an owner, or widen
discovery — not to send a developer off to find something to do.

**The orchestration session did not pick anything, the risk ceiling was not
quietly raised, and no vague work order was created.**

### The multi-candidate scenario, at MEDIUM

Two candidates eligible. Previously this escalated for want of a human
preference. Now one bounded executive session chose
`reserved-screening-negation-blindness` with **high** confidence, and the
deterministic contract accepted the answer:

> "Negation handling is a fundamental logical requirement. This candidate fixes
> a core bug where 'we will NOT do X' still triggers escalation for X. The
> auth-migration candidate addresses a narrower edge case. Negation is
> prerequisite correctness; context-detection is a refinement."

No worker involved. No CEO decision required.

## 10. The real session

One bounded provider session, the only model spend in this pass.

| | |
|---|---|
| model | `claude-haiku-4-5-20251001` (anthropic) |
| input / output | 9 / 2,612 tokens |
| cache creation / read | 12,472 / 0 |
| **cost** | **USD 0.028659** of a 1.50 ceiling |
| wall / turns / tool calls | 25.4 s / 1 / 0 |
| reasoning class | C |
| authority | none |

Run with `--max-budget-usd 1.50` — a ceiling the provider enforces rather than
one the session agrees to.

**One honest observation about that telemetry.** The brief is 2,876 characters
(~1,100 tokens), and the session billed 12,472 cache-creation tokens. The
difference is CLI scaffolding, not the brief. Bounding the planner's context
bought less than the numbers suggest, and any future work on planning cost
should start there rather than on trimming the brief further. That is recorded
here rather than quietly averaged away.

## 11. What this branch does not do

- **No developer, reviewer or worker session ran.** The only model process was
  the single executive planning session above.
- **No live delegation.** This branch carries no `pilot_*` module, no
  `PilotActivation` and no `evaluate_live`; a test asserts their absence.
  `mode: shadow` is unchanged.
- **Company OS still spawns nothing.** A test parses `discovery.py`,
  `executive.py` and `planning_run.py` for `subprocess`, `os.system`,
  `os.popen` and `multiprocessing`. The `ExecutivePlanner` protocol is a seam:
  how the text is produced is not this package's business, and keeping it out
  is what lets the contract be tested without spending anything.
- **No repository scanning capability was built.** Nine bounded surfaces and
  one reader over structured capsule metadata.
- **Nothing merged.** Canonical holds only the curated objective-planning
  foundation.

## 12. Known issues deliberately left alone

These stay visible and unfixed, exactly as recorded:

- reserved/credential negation blindness
- authentication/migration reference ambiguity
- provider-event identifier gap
- deployment action/table mismatch
- mixed-currency escalation gap

The first two are in the seeded register as OPEN MEDIUM-risk candidates, and
one of them is what the executive session selected — as *work to be done later*,
not work done here. Selecting a candidate is not implementing it.
