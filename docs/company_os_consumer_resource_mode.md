# Consumer Resource Mode V1

**Branch** `company-os-v1-consumer-resource-mode`, based on
`eng-ai-resource-efficiency-v2-operational` at `5d73557`, which is the canonical
Company OS baseline `01a1638` plus the AI Resource Efficiency V2 wiring.
**Not merged. Not authorization to merge.**

The purpose is narrow: make the Company engineering runner safe to use again on
**one ordinary consumer AI subscription**. No new Company capabilities, no
Master Plan work, no new tooling. Execution economics only.

---

## 1. What was actually wrong

The AFTER validation of Efficiency V2 ran one real matched job and found four
things that source reading had not:

1. **The standard model tier was unreachable in production.**
   `EngineeringWorkOrder.task_specification` wrote a specialist domain into
   *every* work order. The classifier's `specialist_reasoning` rule fires on a
   non-empty specialist domain, so every engineering job the company could
   issue classified D, and D and above selects the strongest model.
   `company/engineering/intake.py` also hard-coded a class-D ceiling, and
   `company/efficiency/emission.py` selected its strategy from that *ceiling*
   rather than from the classification. Three independent paths, all arriving
   at "strongest".

2. **The strategy governed nothing.** It landed in `briefing.json` and stopped
   there. `tools/engineering_runner` had no reference to it.

3. **Context narrowing was inert and wrong.** `transport.py` fed
   `scope_file_listing` the `ContextRef.key` values, which are `"<kind>:<ref>"`.
   No key can prefix-match a repository path, so the filter returned the empty
   tuple for every job — recorded as `context_refs_scoped: []` beside a packet
   still carrying all seven references. A 100% reduction that had removed
   nothing.

4. **Output reduction never ran.** Its only caller had no production caller.

Plus a telemetry defect: the runner read session cost from
`total_cost_usd` (session total) and tokens and turns from the envelope's
top-level `usage` block and `num_turns` (**final segment**). In 1 of 19 real
sessions those disagreed, and the record said 1 turn / 66 output tokens for a
1032-second session that `modelUsage` in the same envelope put at 27,132 output
tokens and 4,276,831 cache reads.

And a budget layer built on that: `check_budget` was handed
`passes + retries` as a turn count, which the runner hard-codes to `1 + 0`,
against a ceiling of 80. All three of its dimensions were structurally
unreachable, so it always reported "within budget".

---

## 2. The consumer resource profile

`company/efficiency/profile.py`. Two named profiles; `consumer` is the default.

| | consumer | expanded |
|---|---|---|
| providers / parallel sessions | 1 / 1 | 1 / 1 |
| automatic developer attempts | **1** | 3 |
| reviewer passes | 1 | 2 |
| auto-continue after `changes_required` | **no** | yes |
| routine model tier | standard | standard |
| strongest requires escalation | **yes** | no |
| capsule dependency closure | **no** | yes |
| context reference ceiling | 8 | 20 |
| session wall clock | 1800 s | 3600 s |
| session turn ceiling (advisory) | 40 | 120 |
| session cost ceiling | 3.00 | 12.00 |
| runner stages per run | 4 | 12 |

**No number in this module comes from a subscription.** There is no message
allowance, no token quota, no request-per-minute figure. The ceilings are
Company quantities — how many attempts the company will authorize without
asking, how long it will let one session run, what it considers one session
worth. The mapping onto whatever a provider meters lives in
`tools/engineering_runner`, at the vendor edge.

A profile is chosen by name on the CEO request and recorded on the work order.
An unknown name is **refused**, never defaulted: a typo that silently selected
the cheap policy would record the company as having chosen it.

---

## 3. Routing: how the standard tier became reachable

The classifier was never wrong. What was wrong was what it was told.

- `EngineeringWorkOrder` now carries `specialist_domain` and `novel` as data,
  defaulting to `""` and `False`, instead of `task_specification` asserting a
  specialist domain for everybody.
- `company.engineering.intake.derive_routing` decides them deterministically
  from the request: an explicitly named domain wins; otherwise the objective is
  matched against `SPECIALIST_TRIGGERS`, which names **kinds of work** —
  security, governance, architecture, concurrency — rather than subsystems.
  "Refactor the authentication flow" is security work wherever it lives; "add a
  field to a dataclass in company/security" is not. A table of sensitive
  directories would have classified the second as the first, which is how
  "every job is specialist" comes back under a new name.
- HIGH and CRITICAL risk reach specialist depth on their own.
- The reasoning-class ceiling is derived, not hard-coded. An irreversible
  request raises it to E, because `requires_judgment` is true for every
  engineering task and an irreversible one classifies E — a fixed D ceiling
  made `plan_task` refuse such a work order rather than downgrade it, which is
  the right refusal discovered at the wrong moment.
- `emission.py` selects its strategy from the **classification**, not the
  ceiling.

**The four routes to the strongest tier**, all preserved:

1. reasoning class D and above — specialist judgment, deep reasoning,
   multi-perspective review;
2. HIGH or CRITICAL risk, independently of class;
3. explicit escalation (`escalate_reasoning` on the request), recorded on the
   work order as an authorization;
4. **a cheaper capable model already failed** — a correction attempt after a
   standard-tier attempt did not satisfy review escalates automatically. That
   is evidence about this task, not a guess.

Governance is unchanged. The classifier, its inverted rule order, the
no-subagent lock, the separate reviewer, the integration gate and the CEO
approval boundary are all untouched.

---

## 4. Stopping the retry burn

Consumer mode authorizes **one developer attempt and one reviewer pass**.

A reviewer verdict of `changes_required` with no attempts left moves the job to
`decision_required` — an existing state, already in `CEO_STATES`, already
outside the set the runner acts on. Two independent guards, neither trusting
the other:

- Company OS refuses the `planning -> developing` transition on an exhausted
  work order, and `decision_required` cannot reach `developing` at all;
- the runner has no actionable state and stops.

The work order's message names what continuing needs: *additional-attempt
authorization on this work order, or a new one*. Nothing automatic follows.

A request cannot buy itself more automatic attempts by naming a number:
`max_developer_attempts` above the profile's is refused at construction.

---

## 5. Context: what was fixed, and what it is actually worth

### The reference/path bug

`company.efficiency.strategy` now answers a different question per reference
kind, because that is what the question actually is:

- **file / test / benchmark** — the reference *is* a repository path;
- **module contract** — the reference is `capsule:<id>`, an identifier. It is
  resolved through the capsule's own `owns_paths`, never by string-matching the
  key;
- **fact / decision / experiment** — a knowledge record with no repository path
  at all, which must not be scored as though it had one.

`narrow_context_refs` keeps a reference when its real path touches the
authorized scope in either direction, keeps a capsule when any path it owns
does, keeps a capsule the caller supplied no paths for (the company cannot
prove a reference irrelevant using a map it does not have), and guarantees a
floor so narrowing can never empty a packet.

**Narrowing happens at intake**, when the work order is built — not in the
briefing. So the work order, the packet, the briefing and the receipt all carry
one reference set, because there is only one. There is no calculated field
beside a wider packet. `context_refs_scoped` is gone.

### Measured, on the real BEFORE work order

Driven through real production intake against the real capsule index, with the
`attempts-remaining` objective the historical BEFORE job used. Sizes are
measured the same way on both sides — `json.dumps(..., sort_keys=True)` with
no indentation — because the runner writes its own copy indented and
comparing one against the other would measure the whitespace.

| | before (`5d73557`) | after | change |
|---|---|---|---|
| reasoning class | D | C | |
| model tier | strongest | standard | |
| packet references | 7 | 2 | −71% |
| packet size | 1,552 chars | 1,124 chars | −27.6% |
| context manifest | 858 chars | 430 chars | −49.9% |
| briefing JSON (compact) | 9,923 chars | 9,604 chars | −3.2% |
| **material the references point at** | **16,985 chars** | **3,661 chars** | **−78.4%** |
| automatic developer attempts | 3 | 1 | −67% |

**The honest reading of that table.** The reference/path fix changed *nothing*
for this job: all seven references were in scope, so narrowing dropped none of
them. The packet was never where the context was — a packet carries pointers
and weighs about 1.5 KB whatever it points at.

What produced the reduction is the profile's **capsule dependency switch**. The
assembler was following the capsule graph's dependency edges and adding the
transitive closure until the reasoning class's ceiling was reached: one owning
capsule of 3,661 characters, and five dependencies of 13,324 more behind it. A
bounded change to a known contract needs the contract; it does not need the
closure. Specialist work turns the closure back on, because the graph is the
point of specialist work.

**What none of this touches** is the largest number in the record: a developer
session read 2.08M cache units. That is the session exploring the repository
inside its own process, and no packet ceiling reaches it. The levers that do
are the model tier and the attempt count, both of which this milestone moves.

---

## 6. Session lifetime: exactly what is enforced

Claude Code 2.1.70 was inspected rather than assumed. **There is no
`--max-turns` flag.** There is `--max-budget-usd`, and it was probed for real:

```
$ echo "Say OK and nothing else." | claude --print --output-format json \
    --model sonnet --max-budget-usd 0.0001
{"type":"result","subtype":"error_max_budget_usd","is_error":false, ...
 "total_cost_usd":0.042284999999999996, ...}
```

It stops the session. Two things that probe established and no amount of
reading would have:

- it binds at **turn boundaries**, not mid-turn — the first turn's cost lands
  before the check, so a ceiling of $0.0001 was overshot to $0.042;
- a stopped session reports **`is_error: false`** with an `error_*` subtype and
  exit code 0. Reading only `is_error` would record a session cut off part-way
  as a clean one, and the runner would hand a half-finished attempt to a
  reviewer as though the developer had said it was done. The backend now reads
  the subtype and carries `stopped_reason` separately from `ok`.

| ceiling | status | held by |
|---|---|---|
| wall clock per session | **enforced** | the runner terminates the child process |
| session cost | **enforced**, at turn granularity | the provider, via `--max-budget-usd`, when the backend accepts one |
| automatic developer attempts | **enforced** | the Company OS job state machine refuses the transition |
| context references in a packet | **enforced** | the packet is built from the narrowed set; an over-budget packet is never issued |
| runner stages per run | **enforced** | the runner stops and checkpoints |
| model turns | **advisory only** | nothing. No backend accepts a turn ceiling, and the provider's own turn count was measured understating a session sixty-fold |
| tokens, cache reads | **observed after the fact** | nobody. Recorded, never called a limit |

### Checkpoints

A run that stops for any reason short of completion writes
`checkpoint.json` into its run directory: the work order, a summary of the
completed work, the commit and uncommitted paths, failing tests with their
failure detail, unresolved reviewer findings, and the context references.

It deliberately does **not** contain the previous conversation. Carrying the
transcript forward is what made a correction attempt cost more than the attempt
it corrected: the transcript is the expensive part and almost none of it is
load-bearing. The next session is a fresh one, started from this file and the
repository. Continuing needs an operator or CEO authorization; the checkpoint
authorizes nothing.

---

## 7. Telemetry

`normalise_claude_usage` in `tools/engineering_runner/backends.py`.

A Claude Code result envelope carries three accounts of one session:
`total_cost_usd` (whole session), `modelUsage[model]` (whole session, per
model), and `usage` with `num_turns` (**final segment**). Usually a session has
one segment and all three agree, which is why reading cost from the first and
tokens from the third worked for nineteen sessions.

**The rule now:** `modelUsage` summed across models is the session total and is
what is recorded. The top-level `usage` is compared against it. Agreement means
one segment and every figure describes it. Disagreement means `usage` is a
final segment, so `num_turns` describes that segment too, and turns are
**marked unreliable rather than reported**. Two session-total cost figures that
disagree mark the metric and carry the larger — **the smaller value is never
silently preferred**, because that would turn a measurement error into a
reported saving.

Re-run over all 19 stored real sessions: 18 agree, 1 is the known mismatch, and
it now recovers 27,132 output tokens (was 66) and 4,276,831 cache reads (was
121,579) and reports no turn count at all.

| metric | reliability |
|---|---|
| cost | **reliable**; cross-checked against `modelUsage`, marked when the two disagree |
| input / output tokens | **reliable**; session totals, cross-checked |
| cache read | **reliable**; session totals, cross-checked |
| cache creation | **now captured**; was never recorded at all |
| model turns | **reliable only when the envelope is single-segment**; withheld and marked otherwise |

`tool_calls` is no longer set from `num_turns`. They are different quantities,
they were measured differing, and writing one into the other made a number
nobody had measured look measured. The turn count travels as `model_turns`.
Reliability metadata is persisted on the receipt (`usage_source`,
`unreliable_metrics`, `cost_ceiling_enforced`).

**Known limitations.** A single-segment envelope's `num_turns` is still the
provider's own count and nothing independent verifies it. `num_turns ≈ tool
calls + 1` on this company's records, but that is a calibration, not a
contract, and nothing depends on it.

---

## 8. Budget semantics

`company/efficiency/budget.py` declares every dimension as exactly one of
`LIVE_ENFORCEABLE`, `POST_SESSION_OBSERVABLE` or `UNAVAILABLE`, and the table
above is that declaration.

- `BudgetCheck.enforced_violations` is the only property that may be read as "a
  limit was broken".
- `observed_violations` is a measurement. A session that read more tokens than
  the strategy hoped is over an estimate, not over a limit, and reporting it as
  a violation would make every real breach easier to ignore.
- A dimension the telemetry marked unreliable is **not scored**. A check
  against a number known to be wrong is the defect this module exists to
  remove.
- A cost ceiling the runner did not pass to the provider is downgraded to an
  observation, because a limit nobody applied did not bind anything.

`passes + retries` and `input_units`-as-total-context are gone.

---

## 9. The model-tier handoff

The smallest protocol that works: **one JSON object inside a briefing the
runner already fetches, validates and acts on.** No new command, no new file,
no new directory.

Company OS emits a `tier` — `standard` or `strongest` — and never a model name.
`tools/engineering_runner/resources.py` maps a tier onto `--model`, using
**aliases** (`sonnet`, `opus`) so the account's current model of each strength
is what runs and a renamed model does not silently break a launch. Changing
provider changes that one file and nothing in the company.

The runner **validates** the artifact before acting: unknown version refused,
unknown tier refused, missing artifact refused. The runner does not guess a
ceiling, because a guessed ceiling is a policy nobody wrote.

**The artifact cannot widen authority.** It carries a tier, four ceilings and a
set of output filters — no path, no branch, no tool, no employee. A payload
carrying an authority-shaped key is **refused**, not ignored, because a field
nobody validates is how a scope gets widened by a payload never meant to carry
one. `AuthorityEnvelope` is unaffected by any of it and still refuses a
briefing whose packet scope is not the work order's authorized paths.

Ceilings only ever tighten. A briefing asking for a longer session than the
operator started the runner with is capped at the runner's own setting: a
Company OS record may not widen a runner setting.

The operator does not restate the model tier per job. `developer_model` left
empty means "take the recommendation"; setting it pins the session and the
recommendation is recorded and not applied.

`tools/` does not import Company OS. The boundary the integration gate
machine-checks is unchanged.

---

## 10. Test and tool output — where the boundary is

**Company OS cannot compress the tool output inside a coding session.** That
output is produced and consumed entirely within the external CLI's own process,
in a conversation nothing in this repository observes. No claim is made that it
can, anywhere.

What the runner *can* reduce is output it captures itself and then puts back in
front of a model. That is done deterministically:

- a passing command becomes one line with its summary — a green 900-line pytest
  log is 900 lines of context bought for one bit of information;
- a failing command exposes its failure lines first, bounded and
  order-preserving, so the same output never summarises two ways;
- `TestRun.failure_detail` is populated only when a run is not green.

---

## 11. What was not changed

No subagents. No automatic merge, deploy, publish or tag. The CEO approval
boundary, the separate reviewer, the integration gate, protected-policy
integrity and the Company-OS-cannot-spawn-processes boundary are all exactly as
they were. `tools/` does not import `company/`. No capsule was given ownership
of `tools/**`.

---

## 12. What this does not promise

Not every engineering job fits inside a consumer subscription, and nothing here
claims one does. The goal is to maximise accepted engineering work per ordinary
consumer resource window — by not selecting the strongest model for routine
work, not spending a second session nobody asked for, not pointing a bounded
change at a capsule closure it does not need, and not believing a budget check
that cannot fail.

---

## 13. The matched real job, and what it actually saved

One routine job, the same `attempts-remaining` objective the historical BEFORE
run used, through real production intake and the real runner. Work order
`wo-ceo-2026-09-18-attempts-remaining-consumer`, branch
`eng-attempts-remaining-consumer`, commit `8dde0876`. **Reviewer PASS, gate
READY 11/11, `ready_for_approval`, one developer attempt.**

Intake classified it routine with no prompting: `specialist_domain: ""`,
profile `consumer`, one authorized attempt, reason recorded as *"the objective
names no security, governance, architecture or concurrency work and the risk is
not high, so this is routine implementation"*. The runner resolved
`tier:standard` to `sonnet`, applied a 1800 s wall ceiling and a $3.00 provider
spend ceiling, and wrote both beside the stage.

### The defect the run found

The first attempt was refused by the control plane after the work was finished,
committed, tested and pushed:

```
the supplied plan does not match the packet:
context b2655e65812a5d67 against packet 491e65227d33fd85
```

The brief stage narrowed context by the resource profile and the receipt stage
re-planned without it, so `ManualExternalSessionAdapter.ingest` compared two
manifests assembled under different rules. Same shape as the seven defects the
first dogfood found — an assumption about the other side of a boundary,
invisible to any amount of testing one half. Fixed by giving every `plan_task`
call in the subsystem the same policy, with a behavioural test and a source
guard, both of which fail when the defect is reintroduced.

The run also demonstrated the checkpoint: 4,008 characters holding the work
order, the completed work, the commit, the uncommitted paths, failing tests,
unresolved findings and the context references — and no transcript.

### Measured, against both historical runs of the same objective

| | BEFORE `01a1638` | AFTER-V2 `5d73557` | consumer |
|---|---|---|---|
| model | opus | opus | **sonnet** |
| authorized attempts | 3 | 3 | **1** |
| developer cost | $1.2719 | $1.7408 | $1.6406 |
| reviewer cost | $0.3598 | $0.3376 | $0.2956 |
| **job cost** | **$1.6317** | **$2.0784** | **$1.9362** |
| turns | 45 | 51 | 46 |
| output tokens | 9,194 | 11,787 | 14,143 |
| cache read | 1,488,091 | 2,226,932 | 1,913,995 |
| cache creation | not captured | not captured | 100,065 |
| reviewer verdict | pass | pass | pass |
| gate | ready | ready | ready |

**The model-tier lever is much weaker on this workload than its price
difference suggests, and the run says so plainly.** Against the immediately
preceding baseline the job cost 6.8% less; against the original BEFORE it cost
18.7% *more*. The cheaper model did not do the same work more cheaply — it did
more work: 39 turns and 11,020 output tokens against BEFORE's 29 and 5,821, on
the same objective. Price per token fell and token count rose.

**And one sample per condition proves less than it looks.** The two historical
runs are the *same task on the same model* and their developer sessions differ
by 37% ($1.27 against $1.74). That spread is larger than either difference
claimed above. Nothing here establishes a per-session cost saving.

**What is durable is structural, not per-session:**

- **Attempts: 3 → 1.** The worst case is what this milestone exists for. The
  Efficiency V2 build burned ~201 recorded turns and ~13.2M cache-read units
  across repeated developer and reviewer attempts on one work order. A first
  attempt that satisfies review costs the same either way; a first attempt that
  does not now costs one session and a decision instead of three sessions.
- **Referenced material: 16,985 → 3,661 characters.** Not the packet — what the
  packet points at.
- **A live per-session spend ceiling**, which did not exist before in any form.
- **Telemetry that can be believed**, including 100,065 cache-creation units
  that were previously invisible. The zeros in the historical columns are
  "never captured", not "none".

The `attempts_remaining` change the job delivered is on `eng-attempts-remaining-consumer`
and is **not merged**; it is the validation artifact, not part of this milestone.
