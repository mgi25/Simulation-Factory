# company/delegation — executive delegation and management by exception (shadow)

The CEO should set objectives, constraints, budgets and risk tolerance, and
then receive outcomes and exceptions. This subsystem models everything in
between: which seat owns an action, whether that seat can decide it, where it
escalates when it cannot, and which of the results the CEO has to see.

**It decides nothing.** Every record refuses to claim authority to act, the
policy refuses to leave shadow mode, and `shadow.py` probes the canonical CEO
stop semantics on every run. The record that closes an engineering job is still
`company/engineering/decision.py`, still requires a named human, and still
carries no merge authority.

## The shape of one answer

```
ACTION
  -> is it CEO-reserved?            (read from company/permissions.yaml)
  -> walk the chain upward (with the CFO spliced in for money):
       does this seat hold the action?
       is it this seat's own request?
       did its employee implement or review the work?
       would it overrule an independent control?
       is the seat filled, active, and high enough on the autonomy ladder?
       is the risk inside its ceiling?
       is the amount inside its per-decision ceiling and every budget rung?
  -> stop at the FIRST seat that can decide
  -> otherwise ESCALATE, with every seat it passed and why
```

## Modules

| File | What it holds |
|---|---|
| `actions.py` | the closed action set; which are CEO-reserved, read from `permissions.yaml` |
| `org.py` | seats, who fills them, and which can decide anything today |
| `policy.py` | grants, ceilings, and the four structural refusals; loads the YAML |
| `budget.py` | company → department → program → work order, with the sibling sum |
| `deployment.py` | five deployment kinds, classified, and granted to nobody |
| `metrics.py` | management-by-exception counts and the CEO report |
| `authority.py` | `evaluate`: one request, one deterministic answer, and the chain |
| `exceptions.py` | the closed set of conditions under which the CEO hears about it |
| `objectives.py` | the objective ladder, intent digests, and the planning envelope |
| `candidates.py` | the work candidate register: known work, its evidence, and its status |
| `planning.py` | ten deterministic eligibility checks, selection, and work-order proposals |
| `planning_record.py` | the auditable answer to "why did the company choose this work?" |
| `record.py` | the auditable decision row |
| `store.py` | append-only history under a caller-named state directory |
| `brief.py` | the CEO view: outcome, cost, decisions held internally, escalations |
| `scenarios.py` | five real jobs, replayed against the model |
| `shadow.py` | proof on every run that the canonical gate is still the only gate |

## Commands

```
python -m company.delegation candidates # the work candidate register
python -m company.delegation plan       # CEO objective -> one selected candidate
python -m company.delegation policy     # seats, grants, reserved set, conflicts
python -m company.delegation chart      # the hierarchy as a tree
python -m company.delegation deployment # the deployment policy model
python -m company.delegation report     # management-by-exception over the replay
python -m company.delegation evaluate --request-file r.json
python -m company.delegation replay     # the five historical scenarios
python -m company.delegation shadow     # the five stop-semantics probes
```

Exit codes: 0 answered, 1 escalated or a failing condition, 2 malformed input.

## Planning: choosing the work, not only approving it

Until `select_work` existed, choosing which work advances a CEO objective was
not an act this model could represent, so it could not be delegated, recorded
or audited. `docs/company_os_objective_planning.md` has the design;
`docs/company_os_first_live_delegation_pilot.md` has the failure that motivated
it - an intake that authorized a broad objective and left the developer to work
out what the task was.

```
CEO objective + envelope
  -> eligible_candidates()   ten comparisons, no judgement, nothing filtered away
  -> select_work()           one eligible candidate, or ESCALATE, or
                             NO_ELIGIBLE_WORK_CANDIDATE - never invented work
  -> propose_work_order()    narrowed from the candidate, never widened
  -> company.engineering.intake
```

`SELECT_WORK` sits at autonomy rung 3 and is granted to `engineering_manager`,
`cto` and `coo`. No worker seat holds it, or any other grant. A worker may
raise a selection; the chain decides it one layer up, and a manager never
decides its own request.

## What this subsystem cannot do

- It cannot hire. `cfo` and `engineering_manager` are now filled, by explicit
  CEO authorization recorded in `docs/company_os_management_staffing.md`. This
  subsystem did not create them and cannot create another:
  `hire_or_remove_executive_role` stays reserved.
- It cannot deploy. `deployment.py` classifies what authority each of the five
  deployment kinds would need; the policy grants none of it, and a grant naming
  a deployment action is refused at load.
- It cannot let one employee be two controls. A seat is disqualified from
  deciding work its own employee implemented or reviewed, checked before any
  ceiling.
- It cannot delegate a reserved action. A grant naming one is refused at load.
- It cannot invent work. A candidate with no evidence, or whose problem
  statement names no checkable subject, is refused at construction, and
  `select_work` returns `NO_ELIGIBLE_WORK_CANDIDATE` rather than manufacturing
  something when nothing qualifies.
- It cannot discover work. `propose_candidate` is the only way in, it needs a
  named proposer, and it refuses a submission that arrives already `SELECTED`.
  There is no repository scanner here.
- It cannot widen itself. `change_delegation_policy` and `expand_authority` are
  reserved by this package unconditionally, whatever `permissions.yaml` says.
- It cannot merge, deploy, publish, spawn a process, read an environment
  variable or delete anything. `tests/test_company_delegation.py` section 16
  asserts each of those against the package source.

## Where the design is written down

`docs/company_os_executive_delegation.md` — the hierarchy, the authority model,
the escalation rules, the budget ladder, the exception classes, the objective
ladder, shadow-mode semantics, the CEO experience, the master-plan
reconciliation, and the future activation path.
