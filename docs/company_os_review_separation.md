# Independent engineering review

**Organizational fix: `REVIEW_SEPARATION_READY`.**
**The historical pilot keeps its classification: `END_TO_END_DELEGATION_ESCALATED_CORRECTLY`.**

One employee, one routing rule, and a rule that was not weakened.

---

## 1. What was actually wrong

The first end-to-end pilot completed every stage and escalated at integration.
The diagnosis in that report named the symptom — `chief_architect` was both the
reviewer and the CTO's employee — but not the mechanism. The mechanism is one
line:

```python
review_capability: str = "software_architecture"
```

Every work order asked for `software_architecture` review. Exactly one employee
held that capability. So every review in the company routed to the CTO's own
employee, which disqualified the CTO seat from approving that work's
integration, which sent every job to the CEO. Forever.

It was never a staffing accident. It was a default.

## 2. What changed

**One employee.** `software_review_engineer` — engineering, active, reporting
to the Engineering Manager, holding exactly one capability: `code_review`.

**One capability**, registered in the capability registry that already exists
(`company/workforce/capability_registry.json`, now 49 entries). No second
registry was created; the integrity check that flags employee capabilities the
registry does not define is what caught the omission.

**One seat.** `engineering_reviewer`, `kind: worker`, **no grant**. It attests;
it does not approve. A grant would have made it a second manager.

**One routing rule**, in intake rather than in the dataclass default:

```python
review_capability=(
    ARCHITECTURE_REVIEW_CAPABILITY
    if routing.specialist_domain in ARCHITECTURE_REVIEW_DOMAINS
    else CODE_REVIEW_CAPABILITY
),
```

Intake is where the specialist domain is known; a constructor default cannot
see it. The dataclass default stays `software_architecture`, which is the
cautious answer for a work order assembled by hand with nothing else said —
ask the architect.

`ARCHITECTURE_REVIEW_DOMAINS` is `{"architecture"}` alone. `security`,
`governance` and `concurrency` escalate the *implementation* tier; only
architecture changes who should read the diff.

## 3. Why no existing employee was used

Checked before hiring, and none fits without force-fitting:

| Employee | Why not |
|---|---|
| `software_implementation_engineer` | is the developer |
| `simulation_physics_engineer` | simulation/physics/fairness; no review capability |
| `ai_efficiency_platform_engineer` | context, retrieval, caching, telemetry; AI-platform domain |
| `production_qc_lead` | production QC, not engineering code review |
| `chief_architect` | the problem being fixed |

Giving one of the middle three a `code_review` capability it has no claim to
would have made the org chart say something untrue to make a pilot pass.

The new employee is `active` but unrouted when idle: no session exists because
an employee exists, and nothing costs anything until a work order routes to it.

## 4. The engineering chain now

```
Developer (software_implementation_engineer)
  -> Independent Reviewer (software_review_engineer)
  -> Engineering Manager (engineering_delivery_manager)
  -> Deterministic QA (code, unstaffed)
  -> CTO (chief_architect)
  -> bounded internal integration
```

CEO only for genuine exceptions.

## 5. The CTO after the change

Unchanged: still CTO, still holds `approve_integration_merge` at MEDIUM,
still holds `software_architecture`, still the escalation above the Engineering
Manager.

What changed is only *which* reviews reach it. Routine engineering review now
goes to the independent reviewer; architecture review still goes to the
architect — **and still costs the CTO its integration vote on that job.** That
is the rule working, not a problem to route around, and asking for the
architect is now a deliberate choice with a stated price.

## 6. The rule was not weakened

`evaluate` disqualifies any seat whose employee implemented or reviewed the
work, checked before any ceiling. Both directions are pinned:

```
reviewer = chief_architect        -> escalate, actor = ceo
reviewer = software_review_engineer -> approved, actor = cto
```

The COO was **not** given `approve_integration_merge`. That was the cheap way
to make the historical pilot pass, and it would have permanently widened
ordinary policy to close one job.

## 7. The historical pilot keeps its history

`chief_architect` really did review `wo-req-auth-migration-correction-01`.
Hiring a reviewer today does not change who reviewed it yesterday, so the CTO
remains disqualified for that job and it remains a CEO decision.

**`CURRENT_JOB_REQUIRES_FINAL_ALTERNATE_INTEGRATION_AUTHORITY`** — and the
smallest already-legitimate authority able to approve it is the CEO. There is
no other: the Engineering Manager and the COO hold no integration grant, and
granting one to close a single job is the widening that was refused above.

So the pilot stays `END_TO_END_DELEGATION_ESCALATED_CORRECTLY`. That is the
correct outcome, not a residual failure.

### The evidence is still valid, and nothing was re-run

| | |
|---|---|
| stored `review_capability` | `software_architecture` — the value it was created with |
| recomputed work-order fingerprint | `2095f4034cdc7955` |
| fingerprint the review record cites | `2095f4034cdc7955` — **match** |
| store integrity | clean |

Changing a default does not rewrite stored records. The completed
implementation, both reviews and the QA evidence all remain semantically and
cryptographically valid, so **no paid session was re-run and this pass spent
USD 0.00.**

## 8. The future path, which is the point

`test_a_future_job_completes_without_the_ceo` drives the whole chain
deterministically: intake derives `code_review`, the implementation routes to
the developer, the review routes to the reviewer, and then
`approve_code_change`, `approve_test_progression`, `approve_review_outcome` and
`approve_integration_merge` are each **approved below the CEO**, with the
integration decided by the `cto`.

Historical replay: all five recorded scenarios still match their recorded
direction, all still resolved below the CEO.

## 9. Two operational lessons, kept as lessons

**`--no-push`.** The receipt contract requires the authorized branch to be
verifiable on the remote. With push disabled, `remote_verified` is always false
and every attempt is rejected *after* its session has been paid for. The pilot
lost USD 0.86 that way. `EngineeringRunner._preflight` now refuses the run
before anything starts:

```
outcome: blocked
reason : --no-push is incompatible with the receipt contract: the completion
         protocol requires the authorized branch to be verifiable on the
         remote, so every attempt would be rejected after its session had
         already been paid for.
```

The session cost is spent before the receipt is validated, so this is the only
place it can be caught cheaply. Company OS was not redesigned to hide the
mistake.

**The pinned model.** The company's strategy recommended the strongest tier and
the operator pinned Sonnet. The runner already recorded that honestly as
`model_source: operator`. Nothing changed; it stays visible.

## 10. `WorkOrderProposal` carries its checkout

Verified as correct and now covered by two tests in
`tests/test_company_objective_planning.py`: a proposal carries
`authorized_branch` and `base_commit` through to the intake request, and one
built without them says so with empty strings rather than inventing a branch.

**Production-worthy finding, not canonicalized here.** It ships on this branch
with the rest of the change set and is ready for a future curation pass.

## 11. Tests that changed, and why

Five references and one count moved, all of them encoding the old organization:

| Where | Was | Now |
|---|---|---|
| `test_company_engineering_execution.py` ×3 | attestations by `chief_architect` | `software_review_engineer` |
| `test_company_engineering_execution.py` | reviewer-is-implementer probe used `chief_architect` | `software_review_engineer`, so the collision it tests still happens |
| `test_company_engineering_execution.py` | `eligible_employee_ids == ("chief_architect",)` | `("software_review_engineer",)` |
| `test_company_delegation.py` | `len(employees) == 13` | `== 14`, plus an assertion naming the new employee |

One reference at `test_company_engineering_execution.py:1207` was deliberately
left as `chief_architect`: it is a constructor-validation fixture about
deterministic findings, and has nothing to do with routing.

Three assertions in the new suite were also corrected while writing it, and the
corrections are worth recording because each was me being imprecise rather than
the system misbehaving: a refusal can name the reviewer seat as `actor` with
`authorizes_action` false; a reviewer may legitimately *raise* a request the
CFO then approves; and a management override of an independent control is
refused in two shapes — `ESCALATE` where the seat holds the action, `REJECTED`
where it does not. The invariant that covers all of it is the one now asserted:
**the reviewer is never the seat that authorizes anything.**

## 12. What did not happen

- Canonical is untouched at `92b308c`, still `mode: shadow`.
- `main` is untouched at `8b1022a`.
- No paid session ran. USD 0.00 this pass.
- No authority was widened; the COO gained nothing.
- The separation-of-duties rule is unchanged.
- No new objective was started, and no live delegation was activated.
