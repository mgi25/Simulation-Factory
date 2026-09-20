# Company OS — executive delegation and management by exception (shadow)

**Status: SHADOW_DELEGATION_READY.** The delegation model is built, validated
against five real jobs Company OS already ran, and **not activated**. Every
delegated approval it computes is advisory. The canonical CEO stop semantics
are unchanged and probed on every run.

- Branch: `company-os-v1-executive-delegation-shadow`
- Base: `company-os-v1-bootstrap` @ `7813424f934b446e120c771945e27f730da8628c`
- Operating mode: `SUPERVISED_REAL_ENGINEERING` — unchanged
- Autonomy status: `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING` — unchanged
- `main` and the canonical branch: untouched

---

## 1. Master plan vs. current architecture: what was reconciled

The master development plan (`docs/references/company/simulation_factory_master_development_plan.md`,
added with this phase) is the strategic baseline. Where it conflicts with the
architecture that has since been validated, the validated architecture wins and
the discrepancy is recorded. Six conflicts were found.

### 1.1 The plan draws a CFO. The registry has none, and this subsystem may not hire.

Plan §6 puts a COO, a CTO and a CFO in an executive office. `company/org_registry.yaml`
carries eleven employees, one of which (`studio_coo`) is in the `executive`
department. There is no CFO.

Creating one is `hire_or_remove_executive_role`, which `company/permissions.yaml`
reserves to the CEO and which `company/integration/contracts.py` requires to
stay reserved. **So the delegation policy declares the seat and leaves it
vacant.** `Hierarchy.standing("cfo")` returns `VACANT` with the reason, and
every request that would land there escalates past it.

Writing a CFO row into the registry would have been this subsystem performing a
CEO-reserved action in order to model the rule that it may not.

### 1.2 The plan draws an Engineering Manager. The registry has the CTO managing engineers directly.

Plan §6 puts department management between the executives and the workers.
`org_registry.yaml` has `software_implementation_engineer` and
`simulation_physics_engineer` reporting straight to `chief_architect`.

The policy declares `engineering_manager`, leaves it vacant, and
`Hierarchy.registry_conflicts()` reports exactly two conflicts — one per
engineer — naming both the declared chart and the registry edge. The conflicts
are *reported*, never resolved: a delegation policy that silently re-parented
the org chart would be changing the organization, which is a corporate action.

`python -m company.delegation policy` prints them:

```
REGISTRY CONFLICTS (2)
  - simulation_physics_engineer reports to engineering_manager, which no employee
    fills; in company/org_registry.yaml its employee simulation_physics_engineer
    reports to chief_architect
  - software_implementation_engineer reports to engineering_manager, which no
    employee fills; in company/org_registry.yaml its employee
    software_implementation_engineer reports to chief_architect
```

### 1.3 The plan makes COO, CTO and CFO peers. The registry puts the CTO under the COO.

`chief_architect.manager` is `studio_coo`. The declared chart follows the
registry: `cto` reports to `coo`. `cfo` — which has no registry row to preserve
— is attached the same way, so the chart has one spine and escalation has one
path. This is a deliberate deviation from the plan's peer layout in favour of
the edge the registry actually asserts.

### 1.4 The plan's CTO owns Architecture, AI Platform and Engineering. That is `chief_architect`.

No new role was invented. `cto` is filled by `chief_architect`, whose registry
mission is architecture, contracts, reversibility and maintainability, and who
already manages the implementation engineer, the physics engineer and the AI
efficiency engineer. The CTO seat is that span, named.

### 1.5 The plan's autonomy ladder is already canonical. It is reused, not restated.

Plan §22 defines levels 0–5, and `company/permissions.yaml` already carries
them with the per-state caps. The policy declares an `action_autonomy` map from
action type to rung and compares it against
`company.workforce.employment.state_authority_cap`, which reads those caps out
of the canonical file. Nothing about the ladder is duplicated here.

### 1.6 The plan's CEO-reserved list is already canonical, and it is read rather than copied.

Plan §22 names nine reserved decisions; `permissions.yaml` names ten.
`company/delegation/actions.py` maps action types onto those names and reads
the list at runtime. Dropping an entry from `permissions.yaml` un-reserves the
matching action type immediately, and `reservation_drift` reports it. Four more
actions are reserved by this package unconditionally — changing the delegation
policy, expanding authority, changing a governance policy, and `UNCLASSIFIED` —
because they are the ones that would let the model rewrite its own limits.

---

## 2. Organization architecture found

Inventory of what already existed, before anything was written:

| Concern | Where it lives | Reused how |
|---|---|---|
| Employee registry, departments, manager edges, states | `company/org_registry.yaml` | Seats bind to rows; states drive availability |
| Autonomy levels, per-state caps, CEO-reserved list, review triggers | `company/permissions.yaml` | Read, never restated |
| Constitutional rules, amendment clause | `company/constitution.md` | Rules 2, 15, 18, 19 cited in code |
| Employment states and the authority cap | `company/workforce/employment.py` | `EmploymentState`, `state_authority_cap` imported |
| Management graph, span of control, depth | `company/org_intelligence/management.py` | Left alone — it analyses the registry; this models authority |
| Execution-time path/autonomy authority | `company/runtime/authority.py` | Left alone — different question (what a session may touch) |
| The CEO decision on engineering work | `company/engineering/decision.py` | Untouched, and probed every run |
| Work-order risk, reasoning class, resource profile | `company/engineering/work_order.py` | `Risk` reused from `ai_platform/resource_classes.py` |
| Money, budget lines, periods, unknown-is-not-zero | `company/finance/` | `Money` imported; the unknown rule mirrored |
| Append-only record stores with `O_EXCL` | `company/runtime/state_paths.py` | Reused directly, not reimplemented |
| Executive dashboard and decision queue | `company/dashboard/` | Left alone; `brief.py` is a model, not a second dashboard |
| Deterministic QA, review adjudication, integration gate | `company/engineering/review.py`, `company/integration/` | Represented as independent-control seats that never approve |

No parallel organization system was created. The one new thing is the
**seat**: a position in the management hierarchy, which is not the same object
as an employee row, and which is what makes a vacancy expressible.

---

## 3. Executive hierarchy implemented

```
ceo  (human, external to the registry)
  coo — studio_coo (active)
    cto — chief_architect (active)
      ai_platform_lead — ai_efficiency_platform_engineer (active)
      engineering_manager — VACANT
        software_implementation_engineer (dormant)
        simulation_physics_engineer (dormant)
    cfo — VACANT
    research_lead — research_opportunity_lead (dormant)
    content_strategy_lead — creative_format_director (dormant)
      visual_direction — visual_cinematography_director (dormant)
    production_lead — production_qc_lead (dormant)
    analytics_lead — analytics_experiment_scientist (dormant)
    people_lead — hr_org_intelligence_lead (dormant)
    integration_gate — deterministic, never fills
    deterministic_qa — deterministic, never fills
```

Five layers: CEO, executive, department management, workers, independent
controls. Every one of the eleven registry employees fills exactly one seat
(asserted by a test), and two seats are vacant by CEO reservation.

### The finding that matters most

**Three employees are `active`.** `studio_coo`, `chief_architect` and
`ai_efficiency_platform_engineer`. Everything else is `dormant`, and
constitution rule 18 — a defined employee is not a running employee — means a
dormant seat decides nothing.

So with the registry as it stands, the delegation model is much thinner than
the chart suggests: almost every path collapses onto the COO and the CTO. This
is not a defect in the model; it is the company's actual shape, made visible.
Activating delegation would mean deciding which dormant roles become active,
which is a CEO decision this phase deliberately does not pre-empt.

### The independent controls are code, not people

`integration_gate` and `deterministic_qa` are declared as seats so the layer is
represented, and are permanently vacant with no grant. They produce evidence
and they stop work. Neither ever approves, and neither is an employee that
could be asked to.

---

## 4. Delegation / authority model

An authority decision answers, deterministically:

```
decision:             APPROVED | REJECTED | ESCALATE
actor:                the seat that decided, or ceo
authority_source:     delegation_policy_v1
action:               one of a closed set
risk:                 low | medium | high | critical
budget_used / limit:  exact decimal Money, or absent
escalation_required:  bool
ceo_required:         bool
chain:                every seat passed, and why it was insufficient
```

### The order of the checks

1. **Reserved** — answered before anything is measured, so no record ever says
   a department lead was within budget for publishing a video.
2. **Scope** — does any grant in the chain hold this action at all?
3. **Self-approval** — a seat never decides a request it raised. Checked
   *before* the ceilings, so a seat cannot approve its own request by keeping
   it small.
4. **Standing** — filled, active, and high enough on the autonomy ladder.
5. **Risk**, then **budget**.

### The grants

| Seat | May approve | Risk | Per decision | Budget scope |
|---|---|---|---|---|
| `engineering_manager` | code change, test progression, review outcome, bounded correction, stop work, work order | LOW | $25.00 | engineering-operations |
| `cto` | the above + integration merge, new dependency, operating spend | MEDIUM | $40.00 | engineering |
| `cfo` | operating spend, department allocation | MEDIUM | $50.00 | company-operating |
| `coo` | cross-department schedule, operating spend, render, research program, content experiment, workforce state, work order, stop work | MEDIUM | $50.00 | company-operating |
| `ai_platform_lead` | code change, test progression, operating spend, stop work | LOW | $10.00 | ai-platform |
| `research_lead` | research program, stop work | LOW | $6.00 | research |
| `content_strategy_lead` | content experiment, stop work | LOW | $6.00 | content |
| `production_lead` | production render, stop work | LOW | $5.00 | production |
| `analytics_lead` | content experiment, stop work | LOW | $4.00 | analytics |
| `people_lead` | non-executive workforce state change, stop work | LOW | $2.00 | people |
| `ceo` | — receives escalations; holds no grant | — | — | — |

### Four structural refusals, enforced at load

1. **A reserved action cannot be granted.** Refused with the canonical name.
2. **The CEO seat receives no grant.** It is where escalation terminates.
3. **A subordinate may not out-rank its manager** on risk or on budget —
   otherwise escalation would sometimes be a demotion.
4. **A granted action needs a declared autonomy rung**, so a probationary
   employee capped at 2 can never approve a code change.

### Reserved actions (14)

Ten read from `permissions.yaml`: publish a public video, large or recurring
paid API spend, delete important production or company data, merge a major
architecture rewrite, change the primary engine, hire or remove an executive
role, drop a content format, change the company mission, amend the
constitution, change the no-subagents policy.

Four reserved by this package whatever the file says: `change_delegation_policy`,
`expand_authority`, `change_governance_policy`, `unclassified`.

---

## 5. Escalation model

An action travels to the **lowest** seat that could decide it, never straight to
the CEO. Four failure modes are structurally prevented:

| Prevented | How |
|---|---|
| Self-approval beyond authority | A seat is skipped for its own request, before ceilings |
| Role impersonation | A seat naming an employee the registry lacks raises `AuthorityViolation` |
| Circular escalation | `Hierarchy` walks every chain at construction and refuses a loop or a chain deeper than 8 |
| Authority amplification | `expand_authority` and `change_delegation_policy` are reserved unconditionally |
| Subordinate overriding superior | A grant above its escalation target on risk or budget is refused at load |
| Downward escalation | A seat reporting to a lower layer is refused at construction |

`Insufficiency` records why each seat was passed: `no_grant`, `out_of_scope`,
`wrong_department`, `self_approval`, `seat_vacant`, `seat_dormant`,
`seat_restricted`, `autonomy_too_low`, `risk_above_ceiling`,
`budget_above_ceiling`, `budget_unknown`, `reserved_action`.

---

## 6. Budget / resource delegation

```
company-operating  $50.00
├── engineering           $22.00
│   ├── engineering-operations   $18.00
│   │   └── eng-routine-work-order  $5.00
│   └── engineering-architecture  $4.00
├── research  $6.00   ├── content   $6.00   ├── production $5.00
├── analytics $4.00   ├── ai-platform $4.00 ├── people    $2.00
└── executive $1.00
```

Three invariants:

- **A child may not exceed its parent.** Necessary, not sufficient.
- **Siblings may not sum past their parent.** This is the one that prevents
  unrestricted spend: eight departments each capped at the company ceiling are
  eight ways to spend the whole budget, and each passes a per-line check. The
  ladder refuses to be constructed that way.
- **An unknown ceiling is not an unlimited one.** A scope the ladder does not
  carry produces `known=False` and the request ESCALATES. This mirrors
  `company/finance/economics.py`, where a margin with nothing recorded is
  UNKNOWN rather than zero — the property the integration gate probes as
  `finance.unknown_is_not_zero`.

Consumption is passed in by the caller, never read here, so a budget answer is
a pure function of (ladder, consumption, request). The real numbers live in
`company/finance` and `company/efficiency`.

The company ceiling is set at consumer-subscription scale — $50.00 monthly —
rather than at what the company could afford, preserving the master plan's
objective that Company OS runs on roughly one ordinary consumer AI
subscription. For scale: the entire supervised burn-in to date, four developer
attempts and four reviewer passes across three real jobs, cost **$2.79**.

Money is `company.finance.money.Money`: exact decimal, refuses to add two
currencies. Policy amounts are quoted strings, because an unquoted `25.00`
reaches the loader as a float and a budget is not a float.

---

## 7. Objective hierarchy and the planning envelope

```
CEO objective -> program -> department goal -> work order -> task
```

A level cannot be skipped: a work order hanging straight off a CEO objective
has no department that owns it, which is how a company loses track of why it is
doing something.

### Preventing uncontrolled goal mutation

A CEO objective computes an **intent digest** over the title, the success
metrics and the envelope. Every child records the digest of the parent it was
derived from. `lineage_violations` recomputes and compares.

If the CEO objective is edited, every decomposition below it is now derived
from something that no longer exists, and says so:

> `prog-shorts-hooks` was derived from `obj-grow-shorts` at intent `1a2b…`, and
> that objective now reads `9f8e…`. The objective above it changed after it was
> decomposed; a changed CEO intent is a new objective, not an edit.

The digest deliberately excludes the date, the evidence references and the
owning seat: correcting a date is not a change of intent, and a digest that
cried wolf would stop being read.

### The planning envelope

`objective, success metrics, deadline, budget, risk ceiling, allowed
departments, forbidden actions, reporting cadence.`

Inside it, an executive plans freely — there is no field that says *how*.
`envelope_violations(plan, envelope)` returns every way a plan leaves it:
overspend, a forbidden action, a department outside the list, risk above the
ceiling, a deadline overrun, or a plan written against an older envelope.

A non-empty result is an **escalation**, never a licence to widen the envelope.
`PlanningEnvelope` has no method that returns a bigger one — which is why
`envelope_violations` returns strings and not a revised envelope.

---

## 8. Management by exception

`ExceptionClass` is closed. Thirteen members:

| Class | Raised when |
|---|---|
| `authority_exceeded` | the chain ran out, or the action is outside every grant |
| `budget_ceiling_exceeded` | a rung was breached, or the ceiling is unknown |
| `risk_ceiling_exceeded` | above every delegated risk ceiling |
| `reserved_action` | CEO-reserved, by the canonical list or by this package |
| `policy_conflict` | supplied by the caller |
| `strategic_conflict` | supplied by the caller |
| `repeated_execution_failure` | the attempt ceiling is spent |
| `unresolved_dispute` | a reviewer and a manager disagree, with the detail |
| `security_or_governance_event` | a governance action, a security event, or a protected-surface change |
| `major_architecture_decision` | architecture redesign, engine change, new dependency — whatever the diff |
| `unclassified_high_risk` | the action carries no classification, so its risk is unmeasured |
| `envelope_breach` | the plan left its envelope |
| `vacant_authority` | the seat that should have decided does not exist |

**Routine success raises none of them.** A LOW-risk approved change, inside
budget, inside the envelope, with a passing review, produces `()`. This is
asserted by `test_routine_success_raises_no_exception`, and if that test ever
needs updating to accommodate a new class, the new class is wrong.

### `vacant_authority` is this phase's own finding

Not in the brief. An action that escalates only because the seat that should
have taken it does not exist is a different management problem from one that
escalates because it was genuinely too big. Merging the two would hide the org
gap behind a budget number.

---

## 9. Executive decision record

Immutable, fingerprinted, append-only. Fields: `decision_id`, `recorded_on`,
`objective_id`, `work_order_id`, `department`, `requesting_role`,
`approving_role`, `authority_source`, `action`, `risk`, `decision`, `reason`,
`escalation_target`, `ceo_required`, `policy_version`, `policy_fingerprint`,
`request_fingerprint`, `budget_used`, `budget_limit`, `budget_scope`,
`exception_classes`, `evidence_refs`, `shadow`, `authorizes_action`.

- `shadow` refuses to be `False`. `authorizes_action` refuses to be `True`.
  Together they mean a stored delegation history is safe to keep, and cannot be
  mistaken later for a record of something that happened.
- `requesting_role == approving_role` raises.
- An `APPROVED` record with `approving_role == "ceo"` raises.
- The **policy fingerprint** is stored, not the policy: an audit can say "these
  four decisions were taken under a policy that no longer exists".
- `ceo_required` and `decision` are both recorded because they are not
  redundant: ESCALATE with `ceo_required=False` is a real state — the action
  went up one level and a manager took it — and that is the number this whole
  phase is trying to produce.

The store reuses `company/runtime/state_paths.append_json_bytes` (`O_EXCL`
create), so a second write never replaces a first. Decisions group by
objective; one with no objective lands in `unattributed/`, which is
deliberately ugly. `integrity()` reports contradictions and repairs none.

---

## 10. CEO reporting model

```
OBJECTIVE
  Grow Simulation Factory monthly Shorts views to 100k

STATUS
  On track

WORK COMPLETED
  - 12 experiments
  - 7 videos

BEST RESULT
  Opening-hook variant B, +8.2% retention

AI COST
  18.42 USD / 50 USD

EXECUTIVE DECISIONS
  23 handled internally

CEO ESCALATIONS
  0

NEXT ACTION
  Continue the winning format for two weeks
```

`decisions_handled_internally` counts decisions that stayed below the CEO,
including escalations that stopped at a manager. The cost line says `unknown`
when nothing was measured, never `$0.00` — the same rule
`company/finance` applies, in a friendlier font. A portfolio total containing
an unknown is unknown.

This is a **model**, not a renderer of record. `company/dashboard/` is already
the executive view and the gate requires that it cannot approve
(`executive.dashboard_cannot_approve`). Wiring the brief into the dashboard is
an integration step for the phase that activates delegation, when the counts
mean something operational.

---

## 11. Historical shadow evaluation

Five real jobs, replayed against the model. No session ran, nothing was spent,
no stored record was read or written, no historical document was edited. Each
scenario is transcribed from the report named in its `evidence` field, and the
tests assert the transcribed costs against the totals those reports state.

| Scenario | Real cost | Model owner | Model answer | CEO needed | Expected | Match |
|---|---|---|---|---|---|---|
| Dogfood #2 — attempts-remaining on the CEO page | $2.157688 | `cto` | APPROVED | no | no | ✅ |
| Job A — reviewer found a real round-trip defect | $1.0636907 | `ceo` | ESCALATE | yes | yes | ✅ |
| Correction job — null-safe attempts-remaining | $1.1758087 | `cto` | APPROVED | no | no | ✅ |
| Job B — test section-header renumbering | $0.5538657 | `cto` | APPROVED | no | no | ✅ |
| Job C — stopped at the schema pre-flight | $0 | `coo` | APPROVED | no | no | ✅ |

**5/5 match the expected direction.** All five actually stopped at a CEO gate in
history; the model says four of them did not need to.

### What each replay revealed

**Dogfood #2, the correction job and Job B** — clean low-risk engineering work
inside budget — are approved at `cto` with **zero** management exceptions. They
pass the vacant `engineering_manager` seat, which is named in the chain. Had
that seat been filled, all three would have stopped one level lower.

**Job A** escalates, and the reason is the most interesting output of the
phase:

> `cto` holds this action and raised the request, so it does not decide it; the
> chain stopped at `coo`: `coo` may not approve `approve_review_outcome`.

In the real Job A the reviewer was `chief_architect`, who fills the `cto` seat
— **the only seat with authority over an engineering review outcome**. The
self-approval rule therefore forces it upward, and no seat above holds the
action. Its exceptions are `authority_exceeded` and
`repeated_execution_failure` (the one authorized attempt was spent).

This is a real organizational finding, not a modelling artefact: in the
canonical registry, the employee who reviews engineering work is also the
employee who would approve the review. Filling `engineering_manager` separates
them; leaving it vacant means every reviewer-found defect reaches the CEO.

**Job C** — stopping work on a premise that turned out to be false — is
approved at `coo` and never reaches the CEO, which matches history exactly
(Job C is the one scenario where the CEO genuinely was not involved). It
escalates one level from `cto` because of the same self-approval rule. Having a
stop *confirmed* one level up is cheap and still never reaches the CEO, so the
uniform rule was kept rather than carved out for one action type.

---

## 12. Shadow-mode semantics

The risk of building a delegation model is not that it decides wrongly. It is
that it decides *at all* before anyone authorized it to. So shadow mode is
probed, not described. `python -m company.delegation shadow`:

```
SHADOW MODE: ENFORCED

  [ok] ceo_decision_names_a_human
  [ok] approval_carries_no_merge_authority
  [ok] only_ready_for_approval_can_be_approved
  [ok] delegation_record_cannot_act
  [ok] policy_cannot_leave_shadow
```

The first three call the **canonical** `company/engineering/decision.py` and
check that it still refuses: an approval signed `company_os`, an approval
claiming `authorizes_merge`, an approval of a job that is not
`ready_for_approval`. The last two check this package.

`DelegationMode.ENFORCING` exists so the activation path is a named thing with
a defined meaning, and constructing a policy with it raises
`ShadowModeViolation`. The shipped `company/delegation_policy.yaml` says
`mode: shadow`, and a test asserts the file never says `enforcing`.

---

## 13. Known blockers — none resolved, interactions recorded

| # | Blocker | Interaction with this phase |
|---|---|---|
| 1 | Reserved/credential screening negation blindness | **None.** `company/engineering/intake.py` is untouched. No delegation code reads credentials, and a test asserts the package never touches `environ` or `getenv`. |
| 2 | Authentication/migration reference ambiguity | **None.** No authentication or migration surface is touched. Worth noting: the same intake classifier that misreads "redesign"/"migration" is what would classify a delegated request, so activating delegation does not fix it and inherits it. |
| 3 | **Deployment policy gap** | **Directly touched, deliberately left open.** `approve_deployment` is granted to no seat *and* reserved by nobody, so a deployment request is REJECTED and carried to the CEO as an unclassified escalation. That is the correct fail-closed behaviour and it is asserted by `test_the_deployment_gap_is_visible_in_the_canonical_policy`. It is not a deployment policy. Writing one is a CEO decision. |
| 4 | Provider usage event-id gap | **None resolved, and one consequence recorded.** `budget.py` takes consumption from its caller and opens no usage store, precisely because per-event usage identity is unreliable. A delegated budget check is therefore only as accurate as the totals handed to it, and the gap means those totals cannot be de-duplicated per event. This is Job C's finding, unchanged. |

---

## 14. Future activation path

Activation is **not** a code change to this package. In order:

1. **Fill the vacant seats, or decide not to.** `cfo` and
   `engineering_manager` are `hire_or_remove_executive_role` — CEO-reserved.
   Until `engineering_manager` is filled, the reviewer and the approving
   manager are the same employee and every reviewer-found defect reaches the
   CEO (§11).
2. **Decide which dormant roles become active.** Three of eleven employees are
   active. Delegation to a dormant seat is delegation to nobody.
3. **Write a deployment policy**, or keep `approve_deployment` escalating.
4. **Run the model in shadow beside real jobs** for enough jobs that the
   disagreement rate is measured rather than argued. This phase validated
   against five historical jobs; that is validation, not a burn-in.
5. **Close blocker 1**, because a classifier that misreads a request also
   misroutes a delegated one.
6. **Then, and only then**, a CEO-authorized `change_delegation_policy` flips
   `mode` to `enforcing` — which will also require deciding what an enforcing
   `AuthorityDecision` is allowed to *do*, since today it is structurally
   incapable of doing anything.

Nothing in steps 1–5 is performed by this subsystem.

---

## 15. Files

**New**

- `company/delegation/` — 16 modules and a README
- `company/delegation_policy.yaml` — the versioned policy
- `knowledge/company_os/capsules/seeds/company-executive-delegation.json`
- `tests/test_company_delegation.py` — 105 tests
- `docs/company_os_executive_delegation.md` — this document
- `docs/references/company/simulation_factory_master_development_plan.md` — the master
  plan, extracted from the `.docx` and committed for future reference

**Changed**

- Nothing. No canonical file was modified. `company/org_registry.yaml`,
  `company/permissions.yaml`, `company/constitution.md`,
  `company/engineering/`, `company/integration/` and `company/runtime/` are
  byte-identical to `7813424`.

---

## 16. Verdict

**SHADOW_DELEGATION_READY.**

The model is deterministic, its refusals are structural rather than
conventional, it agrees with five real jobs on every one, and it cannot
authorize anything. It is ready to be *run in shadow beside real work*, which
is the next step, and it is not ready to execute authority, which is the step
after that and a CEO decision.

Autonomy status is unchanged:
`NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`.
