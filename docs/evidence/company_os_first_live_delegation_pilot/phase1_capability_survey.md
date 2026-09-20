# Phase 1 — objective-to-work planning capability survey

The question Phase 1 asks is narrow and answerable: can an executive or manager
inside Company OS take a CEO *objective*, inspect organizational or backlog
evidence, **choose** appropriate work, and turn that choice into a work order —
without a human or the outer orchestration session making the choice?

Each row below was checked by reading the module and, where a CLI exists, by
running it. Raw outputs are the sibling files in this directory.

## What exists

| Capability | Where | Status |
|---|---|---|
| Objective ladder CEO→program→department goal→work order→task | `company/delegation/objectives.py` | **exists** |
| Intent fingerprint, lineage violation detection | `objectives.Objective.intent`, `lineage_violations` | **exists** |
| Planning envelope + `envelope_violations` | `objectives.PlanningEnvelope` | **exists** |
| Level-safe child construction | `objectives.decompose` | **exists** |
| Objective sentence → bounded, scoped, routed work order | `company/engineering/intake.py` | **exists** |
| Capsule-derived scope, forbidden paths, required tests, routing tier | `intake.derive_routing`, `ScopeDerivation` | **exists** |
| Live approval of an existing work order under a signed envelope | `company/delegation/pilot.py` `evaluate_live` | **exists** |
| Seats to decide (`cto` active $40, `engineering_manager` active $25, `coo` active $50) | `company/org_registry.yaml` | **exists** |

## What is missing

### 1. `decompose()` is a constructor, not a planner

```python
def decompose(parent, *, objective_id, title, owner_seat, set_by, set_on,
              department="", success_metrics=(), evidence_refs=()) -> Objective
```

The caller supplies the title, the department, the success metrics and the
evidence refs. The function computes exactly one thing by itself: the level, one
rung below the parent. **What the work is arrives as an argument.** There is no
input from which a title could be derived, because the function is passed no
repository, no capsule index, no findings and no backlog.

### 2. `evidence_refs` are citations, never readable evidence

Throughout `company/delegation/scenarios.py` the evidence refs are hardcoded
strings such as `("docs/company_os_supervised_burnin.md",)`. No Company OS
module opens them. They are provenance labels attached by whoever wrote the
record; nothing in the system can read a document and extract a candidate task
from it.

### 3. No backlog exists to inspect

`knowledge/company_os/capsules/capsule.py` declares the full capsule field set.
It has `risks`, `failure_learnings`, `invariants` and `decisions` — all prose
sentences for a reader. It has **no** `backlog`, `deferred_followups`,
`known_debt`, or `open_advisories` field. There is no registry anywhere of
"work that is known to be worth doing", so there is nothing for an executive to
select *from*.

### 4. No action in the closed action set means "choose work"

All 35 members of `ActionType` are approve / change / stop verbs
(`canonical_action_set.txt`). `approve_work_order` approves one that already
exists. Running `python -m company.delegation pilot-policy` confirms the live
pilot grants `cto` and `engineering_manager` exactly seven actions, every one of
them an approval, a bounded-correction request, or a stop. **Planning is not a
modelled act**, so it cannot be delegated, recorded, or audited.

### 5. `org_intelligence` reasons about the org, not the codebase

Its own README states the question it answers: *"is the company itself organized
well?"* Its loop is `evidence → signals → findings → recommendations → change
proposal`, its recommendation vocabulary is `merge_roles`,
`simplify_workflow`, `automate_deterministic_step` and workforce state changes,
and its evidence is supplied by a human (`prioritise` operates "over supplied
dimensions"; `workforce_evidence` computes "across the supplied gaps"). It
produces organizational change proposals that stop at `PROPOSED` awaiting a
named human. It never emits an engineering work order.

## The empirical probe — and the failure mode it exposes

The CEO objective was submitted verbatim to deterministic intake:

```
python -m company.engineering request \
  --request-file phase1_probe_request.json \
  --state-dir <tmp> --repo-root . --as-of 2026-09-20
```

Intake did **not** refuse it. It returned:

```json
"outcome": "authorized"
```

It routed to capsule `company-engineering-execution`, derived authorized paths
`company/engineering` and `tests/test_company_engineering_execution.py`,
classified the work `low` risk, `consumer` profile, reasoning ceiling `D`, no
specialist escalation — a clean STANDARD-tier authorization.

But the work order it persisted carries the CEO's objective **verbatim** as its
own objective, and its first acceptance criterion is:

> "The stated objective is implemented: Improve the reliability or
> maintainability of the Company OS engineering system by completing one
> genuinely useful, already-existing LOW-risk engineering improvement. The
> company must identify the specific work itself from real repository evidence."

That criterion is unfalsifiable. No reviewer and no deterministic QA can decide
whether it is met, because it never names a behaviour.

The derived plan makes the displacement explicit. Step `locate-contract` reads:

> "Identify the smallest contract that the objective is missing, and state it
> before implementing it"

**Company OS does not select the work. It bounds the scope and hands the
selection to the paid developer session.**

This is the exact substitution Phase 1 forbids, with one correction to the
CEO's framing: the risk was that the *outer orchestration session* would
silently act as management. In fact the system pushes the planning decision
*downward* onto the worker instead. Either way no executive or management layer
plans, no planning decision is recorded, and the choice of work would be made by
an unsupervised session against an unreviewable acceptance criterion.

## Verdict

**OBJECTIVE_TO_WORK_PLANNING_GAP.**

Company OS can convert *a task stated as a sentence* into a governed work order,
and can govern every step after that. It cannot convert *an objective* into a
task. The rung between `ceo_objective` and `work_order` exists as a data
structure and is empty as a capability.

Stopped before any paid developer or reviewer execution. Spend: $0.00 of $6.00.
