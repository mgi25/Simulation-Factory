# Workforce and HR — Company OS v1

The deterministic answer to six questions:

- what capabilities does the company have?
- what does a task require?
- where are the gaps?
- is a new employee actually necessary?
- should the need be temporary or permanent?
- can a candidate be evaluated safely before production access?

Standard library only. No database, no embeddings, no external service, no model
call. Nothing here imports production code and no production module imports it
(`company/README.md`, dependency rule).

## What it cannot do

By construction, not by policy:

- **It cannot hire, fire, activate or archive anyone.** No module writes
  `org_registry.yaml`, `permissions.yaml`, or any schema. The strongest output is
  a record in the `PROPOSED` state.
- **It cannot grant authority.** A restricted role's contract emits an empty
  `may_write` whatever the proposal requested, and every cap is read from
  `permissions.yaml` rather than from a constant in this package.
- **It cannot decide a need recurs.** Frequency is supplied by a caller with a
  count and pointers; the code only refuses a claim nobody counted.
- **It has no global employee score.** Performance is scoped to
  `(employee, capability)` and a test scans every dataclass here for a field
  that looks like an aggregate verdict.

## The flow

```
capability registry ──> coverage ──> gap ──> proposal ──> role specification
                                                              │
                                              evaluation ─────┤
                                                  shadow ─────┤
                                               employment  <──┘
                                                  │
                        performance ──> necessity ──> proposal (merge/archive)
```

Each arrow is a function, each box is a frozen dataclass that refuses to be
constructed without what it needs, and every step stops at a record a human
reads.

## Definitions versus state

`company/workforce/*.py` and `capability_registry.json` are **definitions**: they
live in git and change when the company decides it works differently.

Everything `WorkforceStore` writes is **state**: gaps that were observed,
proposals that were made, evaluations that were run. State goes under a
`state_dir` the caller supplies. There is no default location, for the reason
`company/runtime/usage_store.py` gives: a store with a default writes somewhere
by accident.

## The capability model

`capability_registry.json` holds 43 capabilities and 33 explicit relations.
Relations are data — nothing reads a description and guesses an edge.

| Kind | Meaning | Acyclic? |
|---|---|---|
| `comprises` | a broad capability decomposes into narrower ones | yes |
| `requires` | cannot be exercised without the other | yes |
| `related_to` | symmetric adjacency, used to find retraining candidates | no |

The cycle check follows the semantics: `related_to` is symmetric, so every edge
in it is a two-cycle and checking would be noise.

A capability record has no `provided_by` field. Providers are derived from
`org_registry.yaml` on demand, so the capability model cannot go stale against
the workforce (constitution rule 15).

## Three distinctions the code refuses to collapse

**Active capacity is not organizational capability.** A dormant
`visual_cinematography_director` is a real capability the company holds and zero
execution capacity today. `CoverageLevel` has `ACTIVE`, `DORMANT_ONLY` and
`UNCOVERED` for exactly this, and the dormant case produces
`activate_dormant_employee`, never a hire.

**A restricted employee is neither.** Candidate, shadow and probation are
counted separately again: answering "do we need a hire" with the candidate being
evaluated for that gap is circular.

**Rejection is not an employment state.** `EmploymentState.REJECTED` has no
`org_registry.yaml` equivalent, because a rejected candidate never became an
employee. `integrity.py` checks that every *other* state does have one, so the
two vocabularies cannot drift.

## The lifecycle

```
candidate ──> shadow ──> probation ──> active ──> dormant ──> archived
    │            │            │                      ↑           │
    └────────────┴────────────┴──> rejected          └───────────┘
                                                    (reactivation decision)
```

`candidate -> active` is not an edge, so it cannot be reached by supplying more
evidence. Gates are keyed by the whole edge:

| Edge | Required evidence |
|---|---|
| `candidate -> shadow` | `role_approval` |
| `shadow -> probation` | `candidate_evaluation` |
| `probation -> active` | `shadow_comparison` **and** `probation_review` |
| `dormant -> active` | `activation_decision` |
| `archived -> dormant` | `reactivation_decision` |

## CEO-reserved decisions

Unchanged. `permissions.yaml` reserves executive hire and removal, org
restructuring, mission changes and production-authority expansion; this package
reads that list rather than repeating it, and flags a proposal that touches one.

## Command line

Read-only, by design — there is no `hire`, `activate` or `archive` verb.

```
python -m company.workforce coverage cinematography --expand
python -m company.workforce spof
python -m company.workforce graph cinematography
python -m company.workforce integrity
```

## Tests

`tests/test_company_workforce.py`. Four of them assert an *absence* — no global
score, no company-contract write, no production import, no new dependency —
because a rule that lives only in a docstring comes back.
