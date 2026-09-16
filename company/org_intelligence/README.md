# Organizational Intelligence — Company OS v1

Company OS can already tell you what capabilities exist, where the gaps are, who
is dormant, what a task cost and whether a research batch saturated. This is the
layer that steps back and asks the question none of those can:

> is the company itself organized well?

Standard library only. No database, no embeddings, no external service, no model
call. Nothing here imports production code.

## What it cannot do

By construction, not by policy:

- **It cannot reorganize the company.** No module writes `org_registry.yaml`,
  `permissions.yaml`, `constitution.md` or `agent_contract.schema.yaml`. The
  strongest output is a record in the `PROPOSED` state. A test parses every
  module in this package looking for a writer of those four files.
- **It cannot approve itself.** `APPROVED` requires a `Decision`, and a decision
  requires a name that is not `automatic`, `system`, `org_intelligence` or any
  of the rest. `AdvisoryViolation` is a distinct exception type so that catching
  it and carrying on is visible in the code.
- **It cannot optimise away a constitutional rule.** `simplify_workflow` and
  `automate_deterministic_step` cannot touch the no-subagent policy, the
  mission, the constitution or CEO authority at any efficiency. Those are
  CEO-reserved changes wearing a workflow tweak's clothes, and the constructor
  refuses them.
- **It has no company score.** Not `company_health_score`, not a department
  grade, not a manager rating. A test scans every dataclass here for a field
  that reads like an aggregate verdict.
- **It cannot invent a number.** A measurement with no value is a legal record;
  a signal carrying one must name what could not be counted.

## The loop

```
evidence ──> signals ──> findings ──> recommendations ──> change proposal
                                                                │
                                                    human / CEO decision
                                                                │
                                          (implementation happens elsewhere)
                                                                │
                            change experiment ──> post-change review ──> learning
```

This phase stops at the decision. Nothing below the dotted line is executed by
anything in this package.

## Evidence in, nothing recomputed

| Source | What is read | Owner |
|---|---|---|
| `CoverageReport` | single points of failure, dormant-only capabilities | `company/workforce/coverage.py` |
| `CapabilityGap` | occurrence counts and their frequency claim | `company/workforce/gaps.py` |
| `CapabilityPerformance` | rejection, escalation, first-pass rates | `company/workforce/performance.py` |
| `RoleNecessityReview` | role overlap, roles with no routed work | `company/workforce/necessity.py` |
| `OrganizationalDebt` | the existing debt ledger, read not duplicated | `company/workforce/debt.py` |
| `ResourceUsageRecord` / `ResourceSummary` | passes per accepted, retries, unused context | `ai_platform/usage.py` |
| a research `BatchReport` | duplication, concentration, screening and promotion yield | `intelligence/research/` |
| `org_registry.yaml` | manager edges, depth, span | the root contract, read-only |

Every number above is computed once, by the layer that owns it. This package
reads answers and says what they mean for the organization. The research report
is read **duck-typed** — `company/org_intelligence` imports nothing from
`intelligence/`, so the boundary stays one-way and the attribute list in
`ResearchEvidence.from_batch_report` is the whole contract.

## The three distinctions the code refuses to collapse

**A signal is not a finding.** `role_overlap` means two roles declare the same
capabilities. Whether one of them should go takes a finding, and a finding takes
evidence, limitations, counterevidence and a statement of what would change it.

**A dormant capability is not a gap.** `signals_from_coverage` emits
`DORMANT_CAPABILITY`, never a missing one, and the recommendation vocabulary
maps it to `activate_dormant_employee`. The cheap answer cannot become a hire by
passing through this layer (constitution rule 18).

**A window is part of a measurement.** Two first-pass rates with the same name
over different periods are two different numbers. Every signal, finding and
review carries the interval it came from, and a change experiment whose baseline
and observation windows differ materially in length records that in its own
limitations.

## Thresholds are data

Four policy dataclasses — `ManagementPolicy`, `WorkforcePolicy`,
`ResourcePolicy`, `ResearchPolicy` — hold every number. None is a fact about the
world; they are the company's current opinion, in one place.
`rendered_configuration` renders the ones that actually ran onto the review, so
a review that nobody can reproduce against its own thresholds cannot be written.

```
python -m company.org_intelligence policy
```

## CEO-reserved decisions

`ceo_reserved_actions` maps a recommendation onto `permissions.yaml`'s own
`ceo_reserved` list rather than repeating it. With no permissions supplied it
fails closed. `unreserved_actions` runs the check the other way — mapped actions
the permission file no longer names — which is the failure mode the workforce
capsule flags as a risk: rename a key and the flagging stops without anything
going red. `integrity.py` reports it.

This package never edits `permissions.yaml` and never redefines CEO authority.

## The no-subagent policy

Treated as constitutional. This subsystem may observe that the policy exists. It
may not recommend bypassing it as an efficiency move — `ORDINARY_OPTIMIZATION_TYPES`
crossed with `CONSTITUTIONAL_POLICIES` raises. A proposal to change it is
representable, and it is CEO-reserved by the data model, not by a comment.

## Definitions versus state

`company/org_intelligence/*.py` is a **definition**: it lives in git and changes
when the company decides it analyses itself differently. Everything
`OrgIntelligenceStore` writes is **state**, under a `state_dir` the caller
supplies. There is no default location, for the reason
`company/runtime/usage_store.py` gives: a store with a default writes somewhere
by accident.

The store differs from the workforce store in one deliberate way: **no silent
overwrite**. Identical bytes are a no-op, different bytes under the same id
raise, and replacing takes `replace=True` so the overwrite appears in the
calling code. A workforce gap legitimately changes state; an organizational
signal is an observation of a moment, and writing over one loses what the review
was for.

## Command line

Read-only, by design — there is no `merge`, `archive` or `approve` verb.

```
python -m company.org_intelligence management --verbose
python -m company.org_intelligence policy
python -m company.org_intelligence check <state_dir>
```

## Tests

`tests/test_company_org_intelligence.py`. Seven of them assert an *absence* — no
company score, no contract writer, no production import, no new dependency, no
self-approval, no automatic causality claim, no untouched constitution — because
a rule that lives only in a docstring comes back.
