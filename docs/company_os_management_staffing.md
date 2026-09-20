# Company OS — organizational staffing and delegation activation preparation

**Status: MANAGEMENT_SHADOW_READY.** The two vacancies the shadow evaluation
found are staffed, separation of duties is enforced deterministically, the
deployment policy is modelled, and **delegation is still not activated**. Every
approval this model computes remains advisory.

- Branch: `company-os-v1-management-staffing-shadow`
- Base: `company-os-v1-executive-delegation-shadow` @ `830a3e4`
- Canonical: `company-os-v1-bootstrap` @ `7813424` — untouched
- Operating mode: `SUPERVISED_REAL_ENGINEERING` — unchanged
- Autonomy status: `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING` — unchanged

**The headline:** all five historical jobs now resolve below the CEO —
**0 CEO decisions, 0 CEO notifications** — while all five control probes still
correctly require the CEO. Separation of duties holds in every case.

---

## A. Resulting organization hierarchy

```
ceo  (human, external to the registry)
├── cfo — finance_operations_lead (active, NEW)
└── coo — studio_coo (active)
    ├── cto — chief_architect (active)
    │   ├── ai_platform_lead — ai_efficiency_platform_engineer (active)
    │   └── engineering_manager — engineering_delivery_manager (active, NEW)
    │       ├── software_implementation_engineer (dormant)
    │       └── simulation_physics_engineer (dormant)
    ├── analytics_lead — analytics_experiment_scientist (dormant)
    ├── content_strategy_lead — creative_format_director (dormant)
    │   └── visual_direction — visual_cinematography_director (dormant)
    ├── people_lead — hr_org_intelligence_lead (dormant)
    ├── production_lead — production_qc_lead (dormant)
    ├── research_lead — research_opportunity_lead (dormant)
    ├── integration_gate (deterministic, never filled)
    └── deterministic_qa (deterministic, never filled)
```

Thirteen employees, five active. **Registry conflicts: 0** — the two the
previous phase reported were caused by the vacant Engineering Manager seat, and
staffing it closed both.

Measured after the change: no manager cycles, no orphans, no invalid
references. COO span of control 6 (at its configured threshold). Maximum depth
4 (at its configured ceiling, not over it).

### Chief Architect is not collapsed into management

`chief_architect` remains the **independent technical control** — it performs
architecture review, and `company/engineering/work_order.py` still routes review
by the `software_architecture` capability. It also fills the `cto` seat, which
is higher *technical* authority. Those two facts coexist safely because
separation of duties is checked **per decision, against the employee**, not by
giving the reviewer its own box on the chart:

> When `chief_architect` reviewed a job, the `cto` seat it fills is
> disqualified from approving that job's outcome.

That is why the Engineering Manager had to be a different employee, and why a
reviewer seat was deliberately *not* added — the reviewer is routed per work
order by capability and is not a position.

---

## B. Engineering Manager staffing decision: **new role**

No existing employee could safely fill it, and the brief says not to force-fit:

| Candidate | Why not |
|---|---|
| `chief_architect` | It is the reviewer and the CTO. Using it recreates the exact conflict this phase exists to remove. |
| `software_implementation_engineer` | The implementer. It would approve its own work. |
| `simulation_physics_engineer` | Also an implementer, and its capabilities are simulation/physics/fairness/benchmarks — no management capability. |
| `studio_coo` | The COO seat, a layer up, and already at its span threshold. |
| `ai_efficiency_platform_engineer` | AI platform, not engineering delivery. |
| `hr_org_intelligence_lead` | People. It recommends org changes; it does not run engineering. |

**Created: `engineering_delivery_manager`** — department `engineering`, manager
`chief_architect`, state `active`, capabilities `delivery_management` and
`escalation`.

The capability list is the control. It carries **no** implementation, test or
architecture capability, so the canonical capability routing can never send it
work to implement or review. The separation is structural, not a convention
somebody has to remember, and `test_the_engineering_manager_seat_is_filled_by_a_role_that_cannot_implement`
asserts the absence.

`software_implementation_engineer` and `simulation_physics_engineer` were
re-parented to it. `ai_efficiency_platform_engineer` was **not** — it is AI
platform work, not engineering delivery, and stays under the CTO.

## C. CFO staffing decision: **new role**

No existing employee has any financial capability. `company/finance/` is a
built subsystem with no owner in the registry — that is the gap, and it is
worth naming.

**Created: `finance_operations_lead`** — department `executive`, manager `ceo`,
state `active`, capabilities `budget_control` and `cost_analysis`.

Two notes:

- **There is no `finance` department.** `company/validation/bootstrap.py`
  declares eight and finance is not among them, so the CFO sits in `executive`
  like the COO. Its *authority domain* is all eight departments, because it
  holds budget ceilings across the company.
- **It reports to the CEO, not the COO.** That is where the master plan puts
  it, and it is also what keeps the COO's span at 6 rather than pushing it to 7
  and over the configured threshold. Both reasons are recorded in the test.

### Why both roles are `active` and not `dormant`

The brief asks for "dormant/zero-cost" roles. Those are two different
properties, and only one of them is available:

- `company/workforce/employment.py: state_authority_cap` gives a **dormant
  employee autonomy 0**. A dormant Engineering Manager can approve nothing, so
  it would take nothing off the CEO — the entire purpose of the seat.
- An **active** role costs zero when nothing is routed to it. Constitution rule
  18 is about *running*, not about being available, and an authority decision
  here is a deterministic calculation that spawns nothing.

So both are `active`, and
`test_staffing_introduced_no_session_or_process_capability` asserts the package
still contains no process, session or subprocess capability. The other nine
employees remain dormant and still decide nothing, which is separately
asserted.

---

## D. Deployment policy model — built, granted to nobody

`company/delegation/deployment.py`. One word became five acts, because they had
five different blast radii and classifying them together meant either blocking
the harmless one or permitting the irreversible one.

| Kind | Classification | Reversible | Action |
|---|---|---|---|
| `local_integration` | ROUTINE_DELEGATABLE | yes | `approve_local_integration` |
| `canonical_merge` | EXECUTIVE_APPROVAL | yes | `approve_canonical_merge` |
| `staging_release` | EXECUTIVE_APPROVAL | yes | `approve_staging_release` |
| `public_deployment` | **CEO_RESERVED** | no | `approve_deployment` |
| `content_publishing` | **CEO_RESERVED** | no | `publish_public_video` |
| `unknown` | **CEO_RESERVED** | no | `approve_deployment` |

- **Reversibility is what decides the line.** The two irreversible kinds are
  CEO-reserved; the three reversible ones are not.
- **`content_publishing` follows `permissions.yaml`** rather than restating it:
  its rule carries `reserved_as: publish_public_video`, and a test asserts that
  name is still in the canonical reserved list.
- **`UNKNOWN` is a member of the enum, not a fallback branch**, so it appears
  in the table a reader checks and `classify` has no default arm that could
  quietly acquire a laxer answer.
- **Nothing is activated.** `DeploymentPolicy.activated` refuses to be `True`,
  every `DeploymentDecision` carries `authorized=False`, and
  `DelegationPolicy` now **raises** if any grant names a deployment action. A
  deployment request therefore still fails closed to the CEO — asserted for
  every one of the four deployment action types.

This closes the *documentation* half of the known deployment blocker. It does
not close the authority half, and it is not meant to.

---

## E. Separation-of-duty rules

Checked in `evaluate`, **before the ceilings**, so a disqualified approver
cannot become qualified by the request being small.

| Rule | Mechanism | Insufficiency |
|---|---|---|
| A seat may not approve its own request | seat identity | `self_approval` |
| The implementer may not approve its own work | seat's **employee** vs `request.implementer` | `implementer_is_approver` |
| The reviewer may not be the managerial approver | seat's **employee** vs `request.reviewer` | `reviewer_is_approver` |
| No delegated seat may overrule an independent control | `request.overrides_independent_control` disqualifies **every** non-CEO seat | `would_override_independent_control` |
| A manager may not alter its own authority | `expand_authority` is reserved unconditionally | `reserved_action` |
| An executive may not approve its own authority expansion | same | `reserved_action` |
| Escalation always moves upward | `Hierarchy` refuses a seat reporting to a lower layer, at construction | — |
| No circular approval path | `Hierarchy` walks every chain at construction and refuses a repeat | — |

`implementer` and `reviewer` name **employees**, not seats, because both are
routed per work order by capability and neither is a position on the chart.

A separation breach is rarely the last step in a chain — the request keeps
climbing past the disqualified seat and usually stops somewhere else for an
unrelated reason. So `classify` scans the **whole chain** for separation, not
just its end; otherwise the CEO would be told "the COO does not hold this
action" with no mention that the seat which does hold it was the reviewer.

---

## F. Engineering delegation chain

```
software_implementation_engineer   (implements; no grant)
        ↓
chief_architect                    (independent review — a control, not a seat in this chain)
        ↓
engineering_manager                LOW risk, ≤ $25.00, engineering-operations
        ↓
cto                                MEDIUM risk, ≤ $40.00, engineering
        ↓
coo                                cross-department coordination
        ↓
ceo                                reserved decisions and genuine exceptions
```

- A routine LOW-risk change stops at `engineering_manager`.
- MEDIUM risk passes it and reaches `cto` — unless `chief_architect` reviewed
  the job, in which case the CTO seat is disqualified and it escalates.
- `approve_architecture_redesign` is CEO-reserved and cannot be granted at all.

## G. Financial delegation chain

```
work-order budget  →  program budget  →  department budget  →  CFO  →  CEO
```

Money does **not** escalate along the reporting line. The CFO reports to the
CEO and sits beside the operating executives, so a spend that outgrows a
department would never reach it by walking managers upward. The policy declares
this explicitly:

```yaml
functional_authority:
  approve_operating_spend: [cfo]
  allocate_department_budget: [cfo]
```

`effective_chain` splices those seats in just below the CEO. A functional seat
whose grant does not cover the action is **refused at load** — a stop that
cannot decide only lengthens the chain.

**The COO's spend grant was removed.** It sat lower in the reporting line than
the CFO and would have taken every company-wide spend request first, leaving
the CFO reachable only in theory. The COO coordinates operations; money is the
CFO's domain.

Ceilings are unchanged and remain at consumer-subscription scale: company
$50.00/month, engineering $22.00, engineering-operations $18.00. Sibling
ceilings still may not sum past their parent, and an unknown ceiling still
escalates rather than counting as unlimited. `change_budget_policy` is granted
to **no seat**.

---

## H. Historical shadow results

| Scenario | Approving seat | Approving employee | CEO required | Separation |
|---|---|---|---|---|
| Dogfood #2 | `engineering_manager` | `engineering_delivery_manager` | **no** | ok |
| Job A (reviewer found a defect) | `engineering_manager` | `engineering_delivery_manager` | **no** | ok |
| Correction job | `engineering_manager` | `engineering_delivery_manager` | **no** | ok |
| Job B | `engineering_manager` | `engineering_delivery_manager` | **no** | ok |
| Job C (pre-flight stop) | `coo` | `studio_coo` | **no** | ok |

**5/5 match the expected direction.** In every case the approving employee is
neither the implementer (`software_implementation_engineer`) nor the reviewer
(`chief_architect`).

### What changed for Job A, and why

Before staffing, Job A escalated to the CEO. `chief_architect` had reviewed the
work *and* filled the only seat with authority over a review outcome, so
self-approval forced it upward and nothing above held the action.

With the Engineering Manager staffed, the review outcome is decided by
`engineering_delivery_manager` — a different employee, holding neither
implementation nor review capability. The CEO is not involved.

The exhausted attempt ceiling is no longer treated as an exception either, and
that change is deliberate: one work order, one attempt, a reviewer finding a
real defect, and a second bounded work order that fixes it is *what actually
happened* between Job A and the correction job, and both runs were clean.
`REPEATED_EXECUTION_FAILURE` now fires when a **second** work order on the same
objective has already been spent, or when the decision needed the CEO anyway.
Both directions are tested.

### Job C

`stop_work_on_invalid_premise` is decided at `coo` — one level up from the
`cto` that raised it, because a seat never decides its own request. The stop is
*confirmed* by another seat, which is cheap and still never reaches the CEO.
This is the one scenario where history also did not involve the CEO, and the
model agrees.

### Control probes — the number that makes the above mean something

Five counterfactual probes, clearly marked `historical=False`, never run:

| Probe | Result | Reason |
|---|---|---|
| Medium-risk review outcome whose only competent seat is the reviewer | CEO | `separation_of_duty` |
| A manager setting aside a failing QA run | CEO | `separation_of_duty` |
| A deployment nobody classified | CEO | `authority_exceeded` |
| A $200 spend against a $50 company budget | CEO (stopped at `cfo`) | `budget_ceiling_exceeded` |
| A manager widening its own ceiling | CEO | `reserved_action` |

**5/5 correctly required the CEO.** Staffing did not make the model permissive;
it made it route correctly.

---

## I. CEO escalation count and reasons

**Historical replay: 0 CEO decisions required, 0 CEO notifications, 0 total
CEO attention.** No escalation reasons, because there were none.

That is the correct number *for these five jobs* — three were clean runs, one
was an ordinary correction, and one was a department stopping its own work. It
is not evidence that the model cannot escalate, which is what the control
probes are for.

## J. Management-by-exception metrics

`company/delegation/metrics.py` keeps three counts apart, because collapsing
them is how a delegation model flatters itself:

- **`ceo_decisions_required`** — no seat below the CEO could decide it. The CEO
  must *decide*.
- **`ceo_notifications`** — a seat below the CEO decided it and something still
  raises an exception. The CEO must *know*; nothing waits on them.
- **`ceo_attention`** — the union. The number to watch over time, because work
  can be moved from the first bucket into the second without improving
  anything.

Also reported: total decisions, resolved internally, approved/rejected/escalated,
approving seat counts, and a per-`ExceptionClass` reason count in severity
order. No aggregate verdict or health score — `company/dashboard/integrity.py`
refuses that class of field by name, and a test asserts none appears here.

## K. Example CEO executive report

`python -m company.delegation report`:

```
OBJECTIVE / PROGRAM
  Engineering reliability validation (five real jobs, replayed)

MANAGEMENT BY EXCEPTION
  total decisions          5
  resolved internally      5/5
  CEO decisions required   0
  CEO notifications        0
  CEO attention (total)    0

  approved 5   rejected 0   escalated 0

APPROVING SEATS
  engineering_manager      4
  coo                      1

ESCALATION REASONS
  none

RESOURCE SPEND
  4.9510532499999996 USD / 18 USD

OUTCOMES
  - Three clean engineering jobs shipped to ready_for_approval
  - One reviewer-found defect corrected through a second bounded work order
  - One job stopped at pre-flight on a premise that turned out to be false

NEXT ACTION
  Run the model in shadow beside live work before any authority is granted

CONTROL PROBES (counterfactual, never run)
  5 probes, 5 correctly required the CEO
  Reported so that a clean programme cannot be mistaken for a model
  that approves everything.
```

The spend figure is the sum of the real provider-reported costs of the four
jobs that ran, against the engineering-operations ceiling.

---

## L. Files changed

**New**
- `company/delegation/deployment.py` — the deployment policy model
- `company/delegation/metrics.py` — management-by-exception metrics and report
- `docs/company_os_management_staffing.md` — this document
- `docs/validation/company_os_management_staffing/` — evidence

**Changed**
- `company/org_registry.yaml` — two roles added, two engineers re-parented
- `company/workforce/capability_registry.json` — three capabilities registered
- `company/delegation_policy.yaml` — seats filled, functional authority, COO spend grant removed, deployment rungs declared
- `company/delegation/actions.py` — three deployment action types
- `company/delegation/authority.py` — separation of duties, effective chain
- `company/delegation/policy.py` — functional authority, deployment refusal
- `company/delegation/exceptions.py` — `separation_of_duty`, refined repeated-failure trigger, duplicate collapse
- `company/delegation/scenarios.py` — implementer/reviewer, control scenarios
- `company/delegation/__init__.py`, `__main__.py` — exports and two commands
- `knowledge/company_os/capsules/seeds/company-executive-delegation.json`
- `tests/test_company_delegation.py`, `tests/test_company_org_intelligence.py`

**Unchanged:** `company/permissions.yaml`, `company/constitution.md`,
`company/engineering/`, `company/integration/`, `company/runtime/`,
`company/finance/`, `company/dashboard/`.

---

## N. Remaining blockers — none resolved here

| Blocker | Status |
|---|---|
| Reserved/credential screening negation blindness | Untouched. `company/engineering/intake.py` not modified. |
| Authentication/migration classifier ambiguity | Untouched, and still inherited: the same classifier would classify a delegated request. |
| Provider usage event-id gap | Untouched. `budget.py` still takes consumption from its caller rather than reading a usage store, precisely because per-event identity is unreliable. |
| Deployment policy gap | **Half closed, deliberately.** The policy model exists; no authority is granted. A deployment still fails closed to the CEO. |

---

## R. Final status: `MANAGEMENT_SHADOW_READY`

**Can historical routine work now be resolved without CEO involvement while
maintaining separation of duties? Yes.**

All five historical jobs resolve below the CEO. In every one, the approving
employee is neither the implementer nor the reviewer. The four engineering jobs
stop at the Engineering Manager; the pre-flight stop is confirmed one level up
at the COO. Zero CEO decisions, zero CEO notifications.

And the model still refuses: all five control probes require the CEO, for four
different named reasons.

**Delegation is not activated.** Every decision is advisory, every record
refuses to claim authority to act, `mode` is `shadow` and cannot be anything
else, and the canonical CEO stop semantics are probed on every run.

### Activation path from here

1. **Run the model in shadow beside live work.** Five replayed jobs are
   validation, not a burn-in. The disagreement rate should be measured, not
   argued.
2. **Decide which dormant roles become active.** Nine of thirteen are dormant,
   so most non-engineering paths still collapse onto the COO.
3. **Decide whether to grant deployment authority**, using the policy model
   this phase built. `local_integration` is the only kind classified as
   routinely delegatable.
4. **Close the classifier blocker**, because a classifier that misreads a
   request also misroutes a delegated one.
5. **Then** a CEO-authorized `change_delegation_policy` may set `mode` to
   `enforcing` — which will also require deciding what an enforcing decision is
   allowed to *do*, since today it is structurally incapable of doing anything.

Autonomy status is unchanged: `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`.
