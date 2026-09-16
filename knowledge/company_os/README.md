# Company OS knowledge store

Five record types, four decay classes, one directory of JSON files. No database,
no embeddings, no index. Everything here is `dataclasses` and `json`.

## Where records live

```
knowledge/company_os/records/<kind>/<id>.json
```

`<kind>` is one of `fact`, `hypothesis`, `decision`, `experiment_learning`,
`failure_learning`. `<id>` is lowercase `[a-z0-9._-]`, because it is also the
filename. Files are written with sorted keys, so they diff cleanly and two
sessions writing different records never conflict.

## The five types

| Type | Answers | Required beyond the common fields |
|---|---|---|
| `Fact` | What is true, and how do we know? | `evidence` (≥1), `freshness` |
| `Hypothesis` | What might be true, and how would we find out? | `rationale`, `predicted_observation`, `test_plan` |
| `Decision` | What did we choose, and how do we undo it? | `why`, `alternatives` (≥1), `risks`, `reconsider_if` (≥1), `rollback` |
| `ExperimentLearning` | What did one run teach? | `variables_changed` (≥1), `variables_locked`, `observation`, `learning`, `evidence` |
| `FailureLearning` | What broke, and what catches it next time? | `root_cause`, `detection`, `prevention`, `evidence` |

Common to all: `id`, `source`, `created`, `status`, and the optional link fields
`related_tasks`, `related_commits`, `related_experiments`, `contradicts`.

## Fact is not Hypothesis, structurally

The two types do not share a base class and cannot be substituted:

- a `Fact` with empty `evidence` raises — the error tells you to record a
  `Hypothesis` instead;
- a `Hypothesis` has `predicted_observation` and `test_plan`, which a `Fact`
  has no field for;
- a `Hypothesis` has no `freshness` class, because "is it still true?" does not
  apply to something never asserted true. It has `status` instead: `open`,
  `supported`, `falsified`, `abandoned`.

`promote(hypothesis, evidence=…, freshness=…, created=…, source=…)` is the only
crossing, and it requires `status == supported` **and** non-empty evidence. The
resulting `Fact` carries `derived_from`, and the hypothesis stays in the store.

## Freshness and recheck

| Class | Default recheck | Use for |
|---|---|---|
| `permanent` | never | invariants — physics, constitutional rules |
| `slow_changing` | 365 days | architecture boundaries, measured constants, module contracts |
| `time_sensitive` | 30 days | platform behaviour, audience patterns, provider limits |
| `experimental` | 14 days | one run, one branch, conditions not repeated |

`recheck_on` is derived from `created` at construction time when not supplied,
so every decaying record carries an explicit date in its file. An explicit
`recheck_on` always wins.

```python
store.stale(today=date(2026, 9, 16))       # past the recheck date
store.needing_revalidation()               # stale + already flagged
flag_for_revalidation(record, "reason")    # -> status needs_revalidation
```

Flagging a `permanent` record raises. If an invariant needs revalidation the
class was wrong, and the fix is a superseding record rather than a status change
that hides the misclassification.

## Decisions

`DecisionLedger` wraps the store with three transitions:

```python
ledger.reconsider(id, reason)   # -> under_reconsideration
ledger.roll_back(id, reason)    # -> rolled_back
ledger.supersede(id, successor) # -> superseded, with superseded_by
```

All three change `status` and add a reason. None of them touch `why`,
`evidence`, `alternatives`, `risks`, `reconsider_if` or `rollback` — the ledger
records what was believed at the time, and a ledger that rewrites its own
history is a worse version of the git log.

## Writing a record

```python
from datetime import date
from knowledge.company_os import Evidence, Fact, Freshness, KnowledgeStore

store = KnowledgeStore()                      # defaults to records/ beside this file
store.add(Fact(
    id="marble-scale-similarity",
    statement="Simulating at 1.754386x authored size is geometrically similar …",
    evidence=(Evidence("document", "sloped/scale.py", "the derivation"),),
    source="marble-sloped-race-v1",
    created=date(2026, 9, 16),
    freshness=Freshness.PERMANENT,
))
```

`store.add` refuses to overwrite an existing record unless you pass
`overwrite=True`; the normal way to change a claim is a new record that
supersedes the old one.

## Evidence is a pointer

`Evidence(kind, ref, note)` — `ref` is a path, a test node id, a commit sha or a
URL, held to the same one-line reference budget as a context manifest
(`ai_platform/references.py`). Pasting a measurement's output into a record
would make the store as expensive to read as the thing it replaces.
