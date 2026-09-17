# Company OS v1 — production integration gate

Branch: `company-os-v1-production-integration-gate`
Base: `746b4b7d3fe8741e8708493eefc83e96ee137327`
Owns: `company/integration/`, `tests/test_company_integration_gate.py`

## What this phase built

`docs/company_os_v1_bootstrap.md` has always ended with an integration gate —
ten conditions Company OS must meet before it is introduced into the normal
production workflow. Until now that gate was a list in a document, which means
it was a thing somebody could believe they had satisfied.

This phase makes it a program:

```
Company OS evidence -> 38 deterministic checks -> pass / fail / unknown
                    -> blockers -> ProductionIntegrationReadinessReport
```

It evaluates readiness. It wires nothing, executes no production change, and
does not authorize integration. That remains a CEO decision.

## The three design decisions that matter

### Unknown is a status, and it blocks

The dangerous answer to "is Company OS ready" is not "no". It is "the check
did not run, so nothing was reported, so the list looked clean". Every
condition produces a `GateCheck` on every run; a condition whose evidence could
not be established produces one with status `unknown`, the missing evidence
named, and a blocker if the check is required.

`GateStatus.satisfies_requirement` is the single place this is decided and it
returns True for `pass` and `not_applicable` only. That one method is the
difference between a gate and a checklist.

### There is no score

No `readiness_score`, no `health_score`, no percentage, no weight — not in the
report, and not as an identifier anywhere in the package; two tests assert
both. A number would be optimised instead of the conditions, and it would let
nine passes hide one failure.

```
READY                  every required check is satisfied
BLOCKED                at least one required check failed
INSUFFICIENT_EVIDENCE  nothing failed, some required evidence is missing
```

### The gate does not run its own tests

`health.required_suites_pass` is required and its evidence is *supplied*. Two
reasons, and the second decides it:

1. This package holds no process-spawn authority. `production.no_publishing_capability`
   refuses `subprocess` across all of Company OS, and a gate that exempts
   itself from the rule it enforces is not a gate.
2. A check that runs its own evidence can never be `unknown`. The whole design
   rests on a required condition being able to say "nobody has shown me this".

So the honest default for a company nobody has tested is BLOCKED, and turning
that into a pass takes a named reporter and a dated run.

## Architecture

| Module | Holds |
|---|---|
| `model.py` | Four statuses, `GateCheck`, `GateSection`, `IntegrationBlocker`, the report |
| `policy.py` | The required/advisory split as two frozen sets, and the `not_applicable` allow-list |
| `sources.py` | Which roots are production, which are Company OS, parsed once per run |
| `graph.py` | `find_cycles` over a plain mapping, plus the capsule and import graphs |
| `boundary.py` | Import, write, network, spawn and delete findings, read off the AST |
| `probes.py` | Behavioural probes that drive a Company OS guard to its edge |
| `contracts.py` | Drift in `permissions.yaml`, the no-subagent chain, the gating claim |
| `suites.py` | Supplied test evidence, with freshness |
| `checks.py` | One function per condition |
| `report.py` | Assembly, blockers, rendering |
| `store.py` | Append-only reports under a caller-supplied directory |

## The nine categories, 34 required and 4 advisory checks

| Category | Required | Advisory |
|---|---|---|
| `architecture` | production does not import Company OS; production tests independent; no runtime import cycle; capsule graph acyclic; capsule graph integrity | subsystem ownership bounded |
| `execution` | read authority fails closed; write authority fails closed; authority snapshot immutable; receipt validation enforced; no-subagent runtime lock | — |
| `data` | private metric boundary; evidence required for claims; missing evidence stays unknown; audit records append-only | — |
| `workforce` | CEO-reserved actions present; restricted states cannot write production; advisory cannot self-approve | capability gaps visible |
| `finance` | no autonomous spend approval; recurring paid API spend reserved; unknown is not zero | — |
| `analytics` | causal overclaim refused; learning requires results; competitor private metrics unavailable | — |
| `executive` | dashboard available; missing and stale evidence visible; dashboard cannot approve | decision queue preserves source refs |
| `health` | required suites pass; sources parse; no new dependency; no network or model dependency | production failures separated |
| `production` | no publishing capability; no automatic production mutation; no production delete authority; integration remains disabled |  — |

The rule for the split is written into `policy.py`: **required** if the
condition failing would make it unsafe or dishonest to cross the boundary;
**advisory** if it would make Company OS worse without making the boundary
unsafe. A check classified by neither set fails the run rather than
defaulting, because an unclassified check that quietly stops blocking is the
same as having no gate.

## Four kinds of evidence

| Kind | Strength |
|---|---|
| `repository` | re-derivable from the checkout: an AST walk, never an import |
| `contract` | the canonical YAML and the capsule seeds, read not restated |
| `probe` | a Company OS guard was driven to its edge and observed |
| `supplied` | the caller said so; only as good as the reporter named on it |

Nothing is imported to be inspected. Importing a production module would need
pygame and pymunk, and a gate that needs the production dependencies installed
is a gate that cannot run.

## The result on this branch's base

```
PRODUCTION INTEGRATION READINESS: BLOCKED
checks      33 pass, 2 fail, 3 unknown, 0 not_applicable   (with suite evidence supplied)

BLOCKERS (1)
  architecture.capsule_graph_acyclic [company-os-v1-runtime-validation-decouple]
    why  1 declared capsule cycle(s): company-runtime -> company-validation -> company-runtime
```

Every execution-safety, data, finance, analytics and production-boundary
condition passes. Production imports no Company OS package, no production test
does either, the Company OS *runtime* import graph is acyclic, and no Company
OS module can publish, spawn, delete or write into a production tree.

Without supplied suite evidence there is a second blocker,
`health.required_suites_pass`, which is the correct answer to "has anybody run
the tests".

### The runtime/validation cycle

The one real blocker is the declared cycle between the `company-runtime` and
`company-validation` **capsules**. `company-os-v1-runtime-validation-decouple`
is removing it, and the gate names that workstream as the owner — derived from
the finding, not asserted.

Worth recording, because the gate is the first thing to separate them: the
*declared* graph has the cycle, and the *runtime import* graph does not.
`company.runtime` imports `company.validation` at module level;
`company.validation` imports `company.runtime` only inside
`if TYPE_CHECKING:`, which never executes. `architecture.no_subsystem_import_cycle`
excludes those edges and passes; `architecture.capsule_graph_acyclic` reads
what the capsules declare and fails. Both are correct, and the difference is
exactly what the decouple has to reconcile.

No test in this phase requires the repository to contain the cycle. The cycle
detector is proved on synthetic graphs, and the repository-level test asserts
only the shape of the answer. Simulating the decouple — removing
`company-runtime` from `company-validation`'s dependencies in a copy of the
seeds — takes the report to `READY` with no blockers, so the check turns green
on its own when the fix lands.

## What the gate found that nobody was looking for

- **Seven Company OS modules have no capsule owner**: `company/workforce/`'s
  `__init__.py`, `__main__.py`, `common.py` and `errors.py` (the three
  workforce capsules each own specific files and nobody claimed the shared
  spine), plus three package markers. Advisory, not a blocker — an unowned
  module is a context-selection gap, not a safety one — but it is real, and it
  belongs to whoever next touches the workforce capsules.
- **Two bugs in the gate's own first draft**, both caught by running it against
  itself: `dataclasses.replace(snapshot, may_write=("sloped",))` read as a
  filesystem write into the race tree, and the dashboard probe asserted that
  *every* section reports missing over an empty state directory when two of
  them are built from the canonical contracts and legitimately have content.

## The write scan, and what it cannot see

Company OS writes constantly — every store puts JSON into a caller-supplied
state directory — so "does it write" is the wrong question and answers yes.
The question is whether a write is *aimed at* production, and the
deterministic form of that is a filesystem-mutating call with a constant
string argument under a production root.

Three calibration decisions:

- `Path("sloped/scale.py").write_text(...)` is caught by the constant on the
  receiver, not only on the call.
- `destination.rename("sloped/x")` is caught: a variable receiver counts,
  because that is the write the scan exists to find.
- `dataclasses.replace(...)`, `text.replace("sloped/", "")` and
  `names.remove("keep")` are not caught. `replace`, `remove` and `copy` are
  ordinary methods of ordinary values, and `str.replace` appears in every
  path-normalising function in this repository. They require a filesystem
  module in front of them. The blind spot is accepted deliberately: a false
  blocker on a string method would make the whole gate ignorable.

What this cannot see is a production path assembled at runtime from variables.
Three other required conditions cover that case — no network, no process
spawn, no delete — which together mean a Company OS module cannot publish,
shell out or destroy regardless of what path it computes.

## Production roots

Declared in `sources.DECLARED_PRODUCTION_ROOTS`, then intersected with the
checkout. The brief names `race2/`, which this repository does not contain; it
is reported as absent rather than invented as a pass. Fifteen roots are
declared, fourteen exist here, plus `main.py` and `race_main.py`.

## The capsule

`company-production-integration-gate` — a module capsule owning
`company/integration`, 3426 of its 4000 characters.

The control plane is at its eight-dependency limit, so the gate is reached
transitively: `company-os-control-plane -> company-ceo-dashboard ->
company-production-integration-gate`. That edge is a composition edge on a
system capsule ("what is the executive surface made of"), and it records the
route the readiness report will reach the CEO by. It is **not** an import:
`company/dashboard/` does not import `company/integration/`, and a test asserts
that no Company OS subsystem does. Adding the edge introduces no cycle, which
another test asserts directly.

`company-ceo-dashboard` is now at 8/8 dependencies itself, so the next capsule
that needs reaching from the control plane will need a different route.

## Freshness

A readiness verdict describes one tree. The report records `as_of`, the source
commit and the branch — read straight out of `.git` by
`company.runtime.git_evidence`, no subprocess — and `stale_against(commit)`
says why an older report no longer applies. Supplied suite results carry their
own run date and stop counting as a pass after `max_age_days`.

`as_of` is a date, not a clock reading, which is what makes two runs on the
same day over an unchanged tree produce byte-identical canonical JSON and the
same `report_id`. A wall-clock timestamp would make every run a new document
and every honest re-run a store conflict.

## Using it

```
python -m company.integration check --repo-root .
python -m company.integration check --repo-root . --suite-evidence suites.json --json
python -m company.integration policy
```

Exit code is the verdict: `0` READY, `1` BLOCKED, `2` INSUFFICIENT_EVIDENCE.
Nothing is written unless `--output-dir` is given.

## What a READY report does not mean

It means the technical gate conditions are satisfied. It does not connect
anything, and it is not the approval `permissions.yaml` reserves:
`merge_major_architecture_rewrite` is CEO-reserved, and wiring Company OS into
production is a separate future phase.

`ProductionIntegrationReadinessReport.authorizes_production_integration` is a
field rather than a docstring so that every consumer has to carry it, it is
always False, and a report constructed with it True is refused.

## Tests

`tests/test_company_integration_gate.py`, 88 tests, in two kinds kept apart.
The detectors are driven by synthetic fixtures in `tmp_path` — a three-node
cycle, a production module importing the control plane, a Company OS module
writing into `sloped/` — so none of them depends on the state of this
repository. The repository-level tests exercise determinism, the policy being
total, and the gate holding none of the authority it checks for: the same
conditions it applies to every other subsystem, applied to itself.

## Open risks

- The dashboard→gate capsule edge is a declared route, not a code dependency.
  If the dashboard never surfaces readiness, the edge should be re-examined
  rather than left as decoration.
- Suite evidence is supplied, so that condition is only as strong as the
  reporter named on it. The gate records who said so and when; it cannot check.
- Two concurrent workstreams share this base. Adding a capsule required editing
  the two hard-coded assertions in `tests/test_company_os_capsules.py`
  (`len(seeds) == 17` and the id tuple), which is a likely rebase conflict with
  any other branch that also adds one.
