# The bounded live-delegation pilot

**Status: ready for a CEO activation decision. Not activated.**

This document describes a pilot that moves **one** class of decision from
shadow authority to real delegated authority: routine, low-risk engineering
management approval. Everything else stays exactly where it was.

Nothing in this branch is active. The canonical Company OS
(`company-os-v1-bootstrap`) still runs in shadow, `main` is untouched, and the
pilot requires a separate CEO decision to switch on.

---

## 1. What changed, and what did not

| | Before | After this branch |
|---|---|---|
| Canonical policy mode | `shadow` | `shadow` — unchanged |
| `DelegationPolicy` accepts `enforcing`? | no | no — unchanged |
| Shadow probes | 5/5 enforced | 5/5 enforced |
| Default answer with no activation | advice | advice |
| Live authority | none | 2 seats, 7 actions, inside a signed envelope |
| `main` | not writable by the model | not writable, now also structurally protected |

The important row is the fourth. Making the code canonical did **not** make any
decision live, and the next section explains why that is a structural property
rather than a configuration choice.

---

## 2. Why shadow stays the default

The obvious implementation was to add `LIVE_PILOT` to `DelegationMode` and
relax the check in `DelegationPolicy.__post_init__`. That was rejected.

`shadow.py` probe 5 asserts, on every run, that a policy declaring
`mode=enforcing` is refused at construction. Relaxing that check to admit a
third value would have made the canonical policy *able* to leave shadow mode —
the precise property the CEO asked to preserve. A pilot that works by loosening
the guarantee it is being measured against is not a pilot.

So the canonical policy is untouched, and the pilot is a **layer above it**:

```
evaluate_live(request, policy)                     -> advice.  authorizes nothing.
evaluate_live(request, policy, activation=None)    -> advice.  authorizes nothing.
evaluate_live(request, policy, activation=<act>)   -> may authorize, inside the envelope.
```

The default is shadow because the default argument is `None`. There is no flag
to leave set wrongly, because there is no flag. Importing the pilot changes
nothing; constructing a `PilotActivation` changes nothing; only passing one to
`evaluate_live` decides anything, and that has to happen at a call site a
reviewer can see.

`PilotMode` is a separate enum from `DelegationMode` for the same reason: one
describes what a *record* was produced under, and a store may legitimately hold
both kinds.

---

## 3. The floor rule

This is the single property that separates a pilot from a bypass:

> **A pilot gate can only make the answer narrower.**

`evaluate_live` computes the canonical shadow answer first and treats it as the
floor. It can turn an APPROVED into an ESCALATE. It can never:

- approve something the shadow calculation escalated
- move the approving seat
- lower `ceo_required` from `True` to `False`

Three layers enforce it. `evaluate_live` returns the shadow answer unchanged
whenever shadow escalated. `LivePilotDecision.__post_init__` refuses to
construct an object that violates it, so a hand-built decision cannot smuggle
one past. `LivePilotDecisionRecord.__post_init__` refuses to store one.

---

## 4. The live action set

Seven actions, two seats. Both sets are **subsets** of what
`company/delegation_policy.yaml` already grants, and the tests assert that
subset relation per action, so the pilot can never be wider than the policy.

### Engineering Manager (`engineering_delivery_manager`), ceiling LOW risk

| Action | Why it is routine |
|---|---|
| `approve_work_order` | opening bounded low-risk work |
| `approve_code_change` | the ordinary unit of engineering delivery |
| `approve_review_outcome` | accepting an independent reviewer's verdict |
| `approve_test_progression` | continuation *to* deterministic QA |
| `request_bounded_correction` | one correction after `changes_required` |
| `stop_work_on_invalid_premise` | stopping can only narrow what happens |

The Engineering Manager may **not**: approve their own implementation, override
a reviewer verdict, override deterministic QA, change authority or policy,
approve architecture / security / governance work, approve deployment or
publishing, exceed the envelope's budget or risk ceiling, or decide any
integration at all.

### CTO (`chief_architect`), ceiling MEDIUM risk

The manager's set, plus `approve_integration_merge` — bounded internal
integration onto the pilot branch and nowhere else.

MEDIUM risk only because `delegation_policy.yaml` already grants
`cto.max_risk: medium`. `_seat_ceiling` takes the **minimum** of the pilot
ceiling and the policy grant, so narrowing the YAML narrows the pilot without
this code changing.

The CTO may **not**: approve work they independently reviewed, change authority
or policy, approve any CEO-reserved action, approve public deployment or
publishing, or approve major architecture, security or governance work.

### Nobody else

`PILOT_SEATS` has exactly two keys. The COO, CFO and every department lead hold
**no** live authority, at any risk, for any action. Section 9 records what that
costs.

---

## 5. The integration target

`deployment.py` already classified the *act* — `LOCAL_INTEGRATION` is
routine-delegatable, reversible, "merging reviewed work into its own branch".
What it never named was a **place**, and a pilot that leaves that blank permits
`main` by omission.

`pilot_integration.py` supplies the noun:

```
target   company-os-v1-delegated-engineering-pilot-integration
kind     internal_branch
undone by deleting the branch; nothing builds on it
```

`PROTECTED_REFS` is `{main, master, company-os-v1-bootstrap}` and is a **module
constant, not configuration**. Everything else in this package loads from YAML
so the CEO can change it without a code change; this is deliberately the
opposite, because a configurable protected-branch list is one a future policy
edit can empty. Adding a branch is a source change, a review and a test.

`main` is protected because the CEO said so. `company-os-v1-bootstrap` is
protected because moving it is `approve_canonical_merge`, which `deployment.py`
classifies as EXECUTIVE_APPROVAL rather than routine, and which this pilot
grants to nobody.

A target that is not an internal branch, or declares itself irreversible, or
names a protected ref, is refused at construction.

**The pilot decides; it does not merge.** Nothing in these seven modules
imports `subprocess`, `socket`, `urllib`, `os` or `shutil`, opens a file, or
invokes git — asserted over the parsed AST in section 13 of the test file, the
same guarantee `production.no_publishing_capability` asserts across Company OS.

---

## 6. The CEO objective envelope

`PlanningEnvelope` already carried budget, risk ceiling, allowed departments,
forbidden actions, success metrics and an optional deadline. Two things were
missing, and both matter only once the envelope authorizes rather than
annotates.

**An allow-list.** The planning envelope has a *deny*-list of actions. That is
safe while nothing happens and unsafe the moment something does: a deny-list
authorizes every action nobody thought to forbid, including every action added
to `ActionType` after the envelope was signed. A pilot built on one would
silently widen itself with the next commit. `PilotEnvelope.allowed_actions` is
a closed set.

**Required expiry.** `deadline` is optional, and for a plan that is right. For
delegated authority it is the opposite: an envelope with no expiry is a standing
grant. `expires_on` is required, checked against the day the decision is taken,
and an expired envelope **escalates** rather than erroring — the work is still
legitimate, the authority to approve it without the CEO is what ran out.

The full envelope:

| Field | Purpose |
|---|---|
| `objective` / `plan.objective_id` | what this authority is for |
| `success_criteria`, `plan.success_metrics` | what done looks like |
| `plan.budget`, `plan.budget_scope` | the money ceiling |
| `plan.risk_ceiling` | the risk ceiling |
| `plan.allowed_departments` | who may act |
| `allowed_actions` | the closed set of action classes |
| `plan.forbidden_actions` | explicit exclusions |
| `integration_target` | where work may be accepted |
| `expires_on` | when the authority stops |
| `max_corrections_per_work_order` | the retry ceiling |
| `authorized_by` | the named human who signed it |

Refused at construction: an empty allow-list; an allow-list naming a
self-reserved action; an envelope that both allows and forbids the same action;
authority outliving the objective deadline; a signature by `company_os`,
`system` or `automatic`.

Refused at activation, against the loaded policy: an allow-list overlapping
`permissions.yaml`'s reserved set, or naming anything in
`PILOT_FORBIDDEN_ACTIONS`. Two layers, because the first cannot be bypassed by
hand-constructing an envelope and the second stays authoritative about the
canonical file.

This is how the CEO says *"do X within these limits"* instead of approving each
work order.

---

## 7. Bounded correction

The target behaviour:

```
developer -> reviewer says changes_required -> Engineering Manager authorizes
ONE bounded correction -> corrected implementation -> independent reviewer
-> deterministic QA -> management approval
```

The CEO is not involved because the first attempt had an ordinary fixable
defect. But an unbounded retry loop with a manager's name on it is how a
consumer subscription is spent overnight, so the ceiling comes from
`company/efficiency/profile.py`, and it is stricter than it looks:

```
CONSUMER.developer_attempts = 1
CONSUMER.reviewer_passes = 1
CONSUMER.auto_continue_after_changes_required = False
```

**`developer_attempts = 1` means there is no second attempt on the same work
order to authorize.** The bounded correction is therefore a *new bounded work
order*, which is exactly how the burn-in phase actually did it —
`burnin-correction` in `scenarios.py` is a second work order, not a retry.

**`auto_continue_after_changes_required = False` is left alone.** The pilot does
not flip it and does not route around it. The profile says continuation is not
*automatic*; what the pilot changes is who supplies the non-automatic decision.
In shadow that was the CEO; in the pilot it is the Engineering Manager, making
an explicit, recorded, counted authorization. A flag that says "not automatic"
is satisfied by a named seat deciding. It would not be satisfied by the code
deciding, which is why `authorize_correction` refuses to produce an
authorization that names no seat.

The ceiling is `min(envelope, profile)`. Neither can widen the other: an
envelope asking for three corrections on a consumer subscription gets one, and
the expanded profile does not override a CEO who asked for one. **The second
correction on a work order reaches the CEO** as exceptional spend.

The ledger is immutable — a refused authorization cannot leave a count
incremented behind it.

---

## 8. The live decision record

A CEO reads this six months later and asks: *why did this proceed without me?*
The record is adequate only if the answer is complete without opening the code,
the policy or the git history.

`ExecutiveDecisionRecord` carries most of it but hard-refuses `shadow=False`,
by design, so that no shadow record can be mistaken for a live one. Relaxing
that would make every historical record's guarantee retroactively weaker:
"nothing in this store ever claimed authority" would become "nothing claimed
authority unless it did". So `LivePilotDecisionRecord` is a second class, and
the old guarantee survives untouched.

Fields: `decision_id`, `recorded_on`, `objective_id`, `work_order_id`,
`department`, `requesting_seat`, `requesting_employee`, `approving_seat`,
`approving_employee`, `reviewer`, `implementer`, `action`, `risk`, `decision`,
`reason`, `authority_source`, `ceo_required`, `mode`, `policy_version`,
`policy_fingerprint`, `envelope_id`, `envelope_fingerprint`, `activation_id`,
`escalation_chain`, `escalation_target`, `budget_used`, `budget_limit`,
`budget_scope`, `integration_branch`, `gates_checked`, `gates_failed`,
`exception_classes`, `evidence_refs`, `request_fingerprint`,
`authorizes_action`.

**Seats and employees are separate fields on purpose.** `approving_seat` is
`engineering_manager`; `approving_employee` is `engineering_delivery_manager`.
The audit question — *was the approver a different person from the reviewer?* —
is only answerable from the second, and collapsing them would make a genuine
conflict of interest invisible the moment somebody changed who sits in a seat.
The record refuses to construct when the approving employee is also the
reviewer or the implementer.

`record.explain()` renders the answer in prose.

---

## 9. What the historical replay found

Ten recorded scenarios plus five new probes, all replayed under live-pilot
semantics. `python -m company.delegation pilot-simulate`.

**Routine historical work: 4 of 5 proceeded internally, 0 CEO decisions.**
`dogfood-2`, `burnin-job-a`, `burnin-correction` and `burnin-job-b` all
approved by the Engineering Manager with no CEO involvement.

**Two findings worth the CEO's attention:**

### 9.1 A gate that would have sent every reviewer-found defect to the CEO

The first implementation required `review_passed is True` to approve a review
*outcome*. Job A's reviewer said `changes_required` — and the routine
management act on that verdict is to accept it and authorize a correction. The
original gate escalated it, which would have defeated Phase 8 entirely.

Corrected: approving a review **outcome** requires that a review *ran*, not
that it passed. `None` is still refused — a manager cannot approve the outcome
of a review that has not happened. Setting a verdict aside remains
`overrides_independent_control`, which no seat may do.

This is the one case where the replay found a real defect rather than
confirming a design, and it was found by history rather than by a test the
author wrote.

### 9.2 Job C escalates under the pilot, and that is correct

`burnin-job-c` is a `stop_work_on_invalid_premise` **requested by the CTO**. The
CTO is therefore disqualified from approving their own request, the chain lands
on the **COO** — who holds the action canonically and holds no live authority in
this pilot, because Phase 4 named two seats and the COO is not one of them.

So Job C resolved internally under shadow and escalates under the pilot. That
is the pilot being narrow, not wrong. Widening it to cover the COO would grant
live authority that was not delegated, so the divergence is **reported** rather
than smoothed over — `PILOT_EXPECTATION` records it with its reason, and
`diverged_from_shadow` keeps it visible in every summary.

### 9.3 Controls and probes

All five original control probes still require the CEO: reviewer-as-approver,
overriding an independent control, an unknown deployment class, 200 USD against
an 18 USD envelope, and a seat asking to widen itself.

Five new probes, four of which must refuse:

| Probe | Result | Sole objection |
|---|---|---|
| QA failed, progression requested | CEO | `qa_not_passed` |
| Integration onto `main` | CEO | `protected_ref` |
| Integration onto the pilot branch | **internal, CTO** | — |
| Expired envelope, legitimate work | CEO | `envelope_expired` |
| Second bounded correction | CEO | `correction_ceiling` |

The third one is the only probe here meant to *succeed*, and it is load-bearing:
without it the `main` probe proves only that something refused, not that the
branch was what refused. A pilot that blocked every integration would pass the
`main` probe for entirely the wrong reason.

**Shadow default:** the same five scenarios with no activation authorize
nothing, in shadow mode, 0/5.

---

## 10. The CEO report

`PilotRunReport.render()`, in the section order from the brief: OBJECTIVE,
OUTCOME, WORK ORDERS COMPLETED, INTERNAL DECISIONS, MANAGER APPROVALS,
EXECUTIVE APPROVALS, CEO DECISIONS REQUIRED, EXCEPTIONS, COST, FINAL RESULT.

`EXCEPTIONS` sits directly beneath `CEO DECISIONS REQUIRED` on purpose. Zero CEO
decisions is good news only if the exception list is also empty; a run with zero
CEO decisions *and* four exceptions means something was swallowed. The two are
printed together so they cannot be read apart.

`simulation_report()` is deliberately a different function. A simulation has no
cost, no completed work orders and no final result, and printing zeroes into
those fields would read like a pilot that ran and achieved nothing. It ends with
`NO REAL WORK ORDER RAN`.

---

## 11. Commands

```
python -m company.delegation pilot-policy      # the action set, seats, protected refs
python -m company.delegation pilot-simulate    # the full historical replay
python -m company.delegation shadow            # canonical stop semantics, still 5/5
```

Both new commands are read-only and neither activates anything.
`pilot-policy` prints `activated in canonical: NO`.

---

## 12. Known limitations, carried forward unfixed

Per the CEO's instruction not to silently fix unrelated issues:

1. **Reserved/credential screening negation blindness.** The intake classifier's
   `screen_reserved` path shares the negation bug fixed elsewhere in
   `da4f3ce`; disclosed in the coverage-fix stop condition, not fixed.
2. **Authentication/migration reference ambiguity.** Wording like "redesign" or
   "migration" anywhere in a request still forces the architecture-specialist
   tier, and "governance" as a noun still forces the strongest tier.
3. **Provider event-id design gap.** No field in `ResourceUsageRecord` is a
   stable per-event id, so usage records cannot be deduplicated reliably.

Found by this phase and also **not** fixed here, because fixing either means
editing canonical grants or the deployment table, which is a CEO policy
decision:

4. **`approve_local_integration` is granted to nobody.** `deployment.py`
   classifies it as routine-delegatable and `delegation_policy.yaml` grants it
   to no seat, while the CTO is granted `approve_integration_merge`, which has
   no row in the deployment table at all. The pilot uses the granted action and
   classifies by deployment *kind* derived from the target, so neither gap
   blocks it — but the two files disagree about what an integration is.
5. **A mixed-currency request raises rather than escalating.** The canonical
   budget ladder refuses to compare across currencies instead of picking a
   rate, so such a request never reaches a decision. Arguably correct; recorded
   because it is a different failure mode from every other refusal here.

Deployment policy is now explicitly modelled by the management layer.
**Public deployment and public publishing remain CEO-reserved**, and no pilot
seat holds either.

---

## 13. What has not happened

- No real paid developer or reviewer work order ran.
- No public deployment or publishing is enabled anywhere.
- `main` is untouched.
- Live delegation is **not** activated in the canonical Company OS.
- No subagents were used.

The pilot branch is ready for a separate CEO activation decision.
