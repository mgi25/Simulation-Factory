# Production integration gate

One question, answered deterministically:

> Is Company OS safe and complete enough to cross the production integration
> boundary?

```
Company OS evidence -> deterministic checks -> pass / fail / unknown
                    -> blockers -> ProductionIntegrationReadinessReport
```

It evaluates readiness. It does not wire Company OS into production, and a
`READY` report does not permit anybody else to either.

## From the command line

```
python -m company.integration check --repo-root .
python -m company.integration check --repo-root . --json
python -m company.integration check --repo-root . --suite-evidence suites.json
python -m company.integration policy
```

Exit code is the verdict: `0` READY, `1` BLOCKED, `2` INSUFFICIENT_EVIDENCE.
Nothing is written unless `--output-dir` is given.

## The four statuses

| Status | Means | Satisfies a required check |
|---|---|---|
| `pass` | the condition was checked and holds | yes |
| `fail` | the condition was checked and does not hold | no |
| `unknown` | the evidence could not be established | **no** |
| `not_applicable` | the hazard cannot arise in this checkout | yes, and allow-listed |

`unknown` is the one that does the work. A condition nobody has evidence for
blocks readiness exactly as a broken one does, and produces a blocker naming
what is missing.

`not_applicable` is the only non-blocking status that is not a proof, so a
check may return it only if `policy.NOT_APPLICABLE_ALLOWED` names it. Anything
else is coerced to `unknown`.

## Readiness

```
READY                 every required check is satisfied
BLOCKED               at least one required check failed
INSUFFICIENT_EVIDENCE nothing failed, some required evidence is missing
```

There is no readiness score, health score, percentage or weight. A number
would be optimised instead of the conditions, and it would let nine passes
hide one failure. `tests/test_company_integration_gate.py` asserts that no
such field exists in the report and no such identifier exists in the package.

## Required and advisory

The split is two frozen sets in `policy.py`. **Required** if the condition
failing would make it unsafe or dishonest to wire Company OS into production.
**Advisory** if it would make Company OS worse without making the boundary
unsafe. A check in neither set fails the run rather than defaulting to
advisory - an unclassified check that quietly stops blocking is the same as
having no gate.

## The nine categories

| Category | Asks |
|---|---|
| `architecture` | Is Company OS still removable, acyclic, and owned? |
| `execution` | Does every authority fail closed, and does nothing spawn? |
| `data` | Does every number carry provenance, and does missing stay missing? |
| `workforce` | Is employment authority granted by `permissions.yaml`, never taken? |
| `finance` | Can anything spend, and is an unmeasured cost treated as zero? |
| `analytics` | Do observation and learning stay apart? |
| `executive` | Can the CEO see the gaps, and is the view unable to act? |
| `health` | Did the suites run, and was anything new pulled in? |
| `production` | Can anything here publish, mutate or delete? |

## What the evidence is

| Kind | Strength |
|---|---|
| `repository` | re-derivable from the checkout: an AST walk, never an import |
| `contract` | the canonical YAML and the capsule seeds, read not restated |
| `probe` | a Company OS guard was driven to its edge and observed |
| `supplied` | the caller said so; only as good as the reporter named on it |

The gate does not run pytest. It holds no process-spawn authority - the same
rule it enforces over the rest of Company OS - so suite results are supplied
with `--suite-evidence` and the condition is `unknown` until they are. The
honest default for a company nobody has tested is BLOCKED.

## Supplied suite evidence

```json
{
  "max_age_days": 7,
  "results": [
    {
      "suite": "tests/test_company_runtime.py",
      "passed": true,
      "observed_on": "2026-09-17",
      "reported_by": "a session id or a CI run",
      "selected": 41,
      "failed": 0,
      "company_os": true
    }
  ]
}
```

`company_os: false` marks a production-environment suite, which keeps a
missing render dependency from reading as a defect in the control plane.
Results older than `max_age_days` go stale and stop counting as a pass. A
result marked `company_os: true` and reported failing blocks even when no
contract required that suite: the gate does not discard red evidence it was
handed.

## Which suites are required

Ask, rather than keeping a copy of the list:

```
python -m company.integration required-suites --repo-root . --json
```

The set is **derived on every run**, not read from a constant, from three
sources:

| Origin | What it means |
|---|---|
| `canonical` | `REQUIRED_SUITES` - the subsystems the gate's own checks depend on. A floor. |
| `capsule_contract` | a suite named in `capsule.tests` of a capsule **in force** - `active` or `needs_revalidation`. The contract asked for it. A capsule under suspicion is the last one whose tests you would stop running; only `superseded` and `retired` drop out. |
| `change_scope` | a suite reached by `--changed-path`: a capsule whose owned paths the change touches, or a Company OS test file the change edits. |

`REQUIRED_SUITES` was once the whole answer, and that was a fail-open hole: on
2026-09-24 a candidate reached READY while two tests declared by the active
`company-research-intelligence` capsule were failing, because neither name was
in the list. Appending the two names would have closed that instance and left
the hole.

**Change scope only widens.** There is no input to this command that makes the
gate ask for less, because a gate that gets cheaper when you describe the
change less fully is a gate with a dial on it.

**An underivable set is not an empty set.** Four things leave it unresolved: a
capsule store that cannot be read; one that holds no capsules; one that is
*structurally incomplete* (`integrity()` reports a capsule depending on one
that is no longer there, which is what a half-copied store looks like); and a
capsule naming something in `tests` that is not a suite path, such as a glob.
In every case the command exits 2, prints `UNRESOLVED`, and
`health.required_suites_pass` answers `unknown`. "I could not work out what
evidence I need" and "I have all the evidence I need" must never produce the
same verdict.

**Present and green is not observed.** A required result with `selected: 0`, or
an `observed_on` after the run date, is reported as *missing* rather than
counted as a pass.

## Freshness

A readiness verdict describes one tree. The report records its `as_of` date
and the commit and branch it was computed from - read straight out of `.git`
by `company.runtime.git_evidence`, with no subprocess - and
`report.stale_against(commit)` says why it no longer applies. Two runs on the
same day over an unchanged tree produce byte-identical canonical JSON and the
same `report_id`, which is what makes the store append-only without refusing
an honest re-run.

## Reports

`ReadinessReportStore(output_dir)` writes derived reports under a directory the
caller names. No database, no default location. An identical re-write is
accepted; a differing write under the same report id is refused.

## What this is not

This subsystem does not authorize production integration. Even a READY report
means only that the technical gate conditions are satisfied. Connecting
Company OS to production is a separate CEO decision - `permissions.yaml`
reserves `merge_major_architecture_rewrite` - and
`authorizes_production_integration` is False in every report this package can
construct.
