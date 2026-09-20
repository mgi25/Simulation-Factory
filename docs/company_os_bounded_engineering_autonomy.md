# Bounded routine engineering as an operating mode

**Status: implemented, tested, and NOT activated.** Activation is one CEO
decision, taken after reading this.

The successful discovery pilot proved the chain works once. This converts it
into the way the company normally runs an engineering objective — which changes
the question from *did it work* to *what can it never do*, because nobody will
be watching the next one.

---

## 1. What the CEO does, and stops doing

**Once per objective:** sign an `ObjectiveContract` — objective, success
criteria, department, budget, risk ceiling, allowed actions, forbidden actions,
expiry, correction ceiling, reporting requirements.

**Then nothing,** until a final report arrives. The CEO does not approve the
work order, the code change, the review outcome, the test progression or the
internal integration. That is the mode.

**There is no standing grant.** A contract expires. An expired contract
authorizes nothing, and `may_activate` refuses it before any request is
evaluated.

## 2. The two modes, and why there is no third

    SHADOW                        authority is calculated, nothing authorized
    BOUNDED_ROUTINE_ENGINEERING   ordinary engineering proceeds inside a contract

`company/delegation_policy.yaml` still reads `mode: shadow` and always will.
`shadow.py` probe 5 asserts on every run that a policy declaring anything else
is refused at construction, and that probe is the guarantee the CEO has been
measuring against since the beginning. Relaxing it to admit a second value
would remove the property rather than extend it.

So the operating mode lives in a **contract the CEO signs per objective**, not
in a file. There is no global switch to leave on, because there is no global
switch. `may_activate` takes the enabled modes as an argument defaulting to
shadow only — forgetting the argument enables nothing.

Three layers, each strictly narrower than the one above:

    delegation_policy.yaml   who could ever approve this
    ObjectiveContract        what this objective authorized
    evaluate_live            whether this specific request may proceed

## 3. Exactly what is delegated

| seat | may decide |
|---|---|
| Engineering Manager | `approve_code_change`, `approve_review_outcome`, `approve_test_progression`, `request_bounded_correction`, `stop_work_on_invalid_premise` |
| CTO | the above, plus `approve_integration_merge` to the internal target |
| Independent reviewer | nothing — it attests, holds no grant, manages nothing |
| Deterministic QA | nothing — it is unstaffable and cannot be overridden |

`CONTRACT_FORBIDDEN` is refused **at contract construction**, so a dangerous
contract never exists to be passed around: deployment, staging release,
production render, canonical merge, delegation-policy change, budget-policy
change, workforce state change, department budget allocation.

## 4. Management by exception

Routine conditions do not interrupt anyone. `company/delegation/exceptions.py`
already owns the closed set of conditions that reach the CEO, and this mode
adds one rule on top of it:

> **`NO_EXECUTABLE_WORK` is a result, not a question.**

The company looked at its register, found nothing it could start, looked for
new work under a bounded envelope, and still found nothing. There is no
decision to take mid-run — there is a report to read afterwards. Treating it as
an escalation would interrupt a person to tell them nothing happened, which is
precisely what management by exception exists to prevent.

`ESCALATED` is the different case: a decision is genuinely required and the
objective cannot proceed without it.

`ceo_action_required()` is **computed** from the terminal state and the
exceptions that fired. A report cannot claim nothing is needed while an
exception is outstanding, and it cannot be optimistic about its own headline.

## 5. The objective lifecycle

    PROPOSED -> AUTHORIZED -> PLANNING -> EXECUTING -> REVIEWING
             -> VALIDATING -> INTERNALLY_INTEGRATED -> COMPLETED

Terminal exits from any live state: `BLOCKED`, `ESCALATED`, `FAILED`,
`EXPIRED`. `NO_EXECUTABLE_WORK` is reachable **only from `PLANNING`**, because
it is what planning concluded and no later stage can discover it.

`REVIEWING -> EXECUTING` is the bounded correction. The state machine does not
count attempts; `pilot_correction.py` owns the ceiling, and a second answer to
that question would be a worse one.

Every move is an `ObjectiveTransition` with an actor, a reason and evidence.
Illegal moves raise rather than being recorded.

## 6. Where work lands, and the line it does not cross

**Internal engineering integration** — one branch,
`company-os-v1-engineering-integration`. One, not one per objective: branch
sprawl makes "what has the company actually built" unanswerable, which is the
question this whole layer exists to keep answerable. Objectives are separated
by their records, not their refs.

**Canonical / production promotion** — no path exists. No seat, no ceiling and
no contract shape in this mode reaches it. `may_integrate` classifies canonical
as `Destination.CANONICAL` and refuses it as *promotion, not routine
engineering*. An unrecognised ref classifies as `UNKNOWN` and is refused rather
than guessed at.

### How internally integrated work becomes releasable later

Nothing automatic. Reaching `INTERNALLY_INTEGRATED` makes work *eligible to be
proposed*, and `promotion_readiness` answers only "would this be sane to
propose". An actual promotion requires, and this capability is **not
implemented here**:

1. a CEO decision at release or program level, not per change;
2. a batch of internally integrated work, not one commit;
3. the production integration gate READY with zero blockers;
4. a fast-forward onto canonical — no force, no squash, no merge commit.

## 7. Resource control

Unchanged, and still built for one consumer subscription:

| eligible & executable | what happens |
|---|---|
| 0 | bounded discovery, then stop if still nothing |
| 1 | deterministic selection, no model |
| 2+ | at most one bounded executive planning session |

The discovery pilot spent **USD 0.00 on planning** because one candidate was
executable. `CostBreakdown` records planning, developer, review and correction
separately against the authorized budget, and overspend forces the report
headline.

## 8. Carried-forward limitations

| limitation | classification | why |
|---|---|---|
| Reserved/credential screening negation blindness | **FAIL_SAFE** | It refuses its own fix's work order, so the failure mode is *too much* escalation, never too little. Weakening it to make routine autonomy convenient would trade a safe failure for an unsafe one. Not touched. |
| Provider usage event-id design gap | **OPERATIONAL_LIMITATION** | No field in `ResourceUsageRecord` is a stable per-event id, so cost attribution is per session rather than per event. Costs are still recorded and still bounded; the objective total is correct. Blocked on a schema decision nobody has taken. |
| Mixed-currency escalation gap | **OPERATIONAL_LIMITATION** | Every budget in the company is USD and `Money` refuses cross-currency arithmetic, so the gap is unreachable today rather than fixed. It becomes real the day a second currency appears. |
| Deployment / action mapping gap | **FAIL_SAFE** | `approve_deployment` sits in `action_autonomy` and in **no grant**, so a deployment request escalates with nowhere to stop. A gap that fails towards the CEO is the correct shape for an action the company has no policy for. |

None is **BLOCKING**. The first and last are the system working.

## 9. Follow-up candidates, recorded not implemented

- `capsule-ownership-semantic-review` — LOW. `intelligence/__init__.py` is
  owned by `company-knowledge-capsules` for test-constraint reasons rather than
  semantic ones; the natural owners carry exact-equality assertions that bar
  additions. Raised by the reviewer as an advisory on work it passed.
- **Module naming.** The validated live-authority runtime is still called
  `pilot*.py`. The names are historically accurate and the code is validated;
  renaming seven modules and 1,744 lines of tests is churn with real regression
  risk and no behavioural benefit, so it was **not** done here. It is real debt
  and should be a candidate of its own before a third capability builds on
  these names.

## 10. What was proved before asking for activation

72 tests in `tests/test_company_bounded_engineering_autonomy.py`.

**Routine:** four management decisions stop at the Engineering Manager;
integration stops at the CTO; the happy path is legal end to end; one bounded
correction returns to `EXECUTING`; a routine success asks the CEO for nothing.

**Exceptions, all failing closed:** QA failure; override of an independent
control; every protected ref, both at the destination classifier and live;
HIGH risk; deployment; publishing; authority modification; organization
modification; spend outside the envelope; the second correction; an expired
objective; architecture review still putting the CTO in self-conflict; and —
with no activation — nothing authorized at all.

**Limitations, asserted rather than assumed:** credential screening still
refuses its own candidate; `tools/` was not given an owner; the deployment
action is still granted to nobody.
