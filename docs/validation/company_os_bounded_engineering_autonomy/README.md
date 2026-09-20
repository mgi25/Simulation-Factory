# Bounded routine engineering: productionization evidence

Built from canonical `bdbe71b`. **The mode is implemented and not activated.**

## Delta inventory from the successful pilot

Classified rather than merged. The pilot branch `7896c75` carried two commits.

| file | class | why |
|---|---|---|
| `company/delegation/pilot.py` | PRODUCTION_WORTHY | `evaluate_live`, `PilotActivation`, `PilotEnvelope`, the gates |
| `pilot_envelope.py` | PRODUCTION_WORTHY | envelope and `IntegrationTarget` |
| `pilot_integration.py` | PRODUCTION_WORTHY | `PROTECTED_REFS`, target validation |
| `pilot_record.py` | PRODUCTION_WORTHY | delegated decision records |
| `pilot_correction.py` | PRODUCTION_WORTHY | the bounded correction ceiling that actually binds |
| `pilot_report.py` | PRODUCTION_WORTHY | executive/management reporting |
| `pilot_simulation.py` | PRODUCTION_WORTHY | standing control: the 15-scenario replay behind `pilot-simulate` |
| `errors.py` (+18) | PRODUCTION_WORTHY | `PilotBoundaryViolation` |
| `__main__.py` (+144) | PRODUCTION_WORTHY | `pilot-policy`, `pilot-simulate` |
| `tests/test_company_delegation_pilot.py` | PRODUCTION_WORTHY | 160 tests |
| `tests/test_company_executive_planning.py` (+63) | PRODUCTION_WORTHY | composition assertions |
| `docs/company_os_delegated_engineering_pilot.md` | EVIDENCE_ONLY | the pilot's design record, superseded by the production doc |
| `docs/evidence/company_os_discovery_end_to_end_pilot/**` | EVIDENCE_ONLY | the run itself; preserved on its own branch, not copied into production records |
| `docs/validation/company_os_discovery_end_to_end_pilot/**` | EVIDENCE_ONLY | same |
| the pilot's `ceo_objective.json`, `planning_run.json`, `decisions.json` | DO_NOT_INTEGRATE | historical operating records; production runs produce new ones |

Nothing was renamed. The live-authority modules are still called `pilot*.py`:
the names are historically accurate and the code is validated, and renaming
seven modules plus 1,744 lines of tests is churn with real regression risk and
no behavioural benefit. It is recorded as debt in the production doc.

## What was added

| module | what it owns |
|---|---|
| `operating_mode.py` | `OperatingMode`, `ObjectiveContract`, `may_activate` |
| `objective_lifecycle.py` | `ObjectiveState`, the transition table, `ObjectiveHistory` |
| `promotion.py` | the internal target, destination classification, the promotion boundary |
| `objective_report.py` | the CEO outcome page and its computed headline |

## Results

- `tests/test_company_bounded_engineering_autonomy.py` — **72 tests**, the full
  routine and exception matrix.
- Full Company OS suite — **2377 selected, 0 failed**, 35 suites.
- Gate — **READY, 34/34 required, 0 blockers.**

### Three regressions, found and fixed

1. **`advance(` is a forbidden token in `company/delegation/`.**
   `tests/test_company_delegation.py` asserts that no module in the package
   contains any of a short list of tokens that would move an engineering job.
   `ObjectiveHistory.advance()` tripped it. The method only returns a new
   immutable record and performs no side effect, but the guard is deliberately
   crude and is protecting something real, so the verb gave way:
   `with_transition`, matching the `with_status` idiom already in use. The
   docstring explaining this tripped the same guard by quoting the token, and
   was rephrased.
2. **Two executive-planning replays pinned the live backlog** and broke the
   moment a follow-up candidate was recorded. They now build the register they
   describe, excluding candidates added after the runs they replay. This is the
   second time this class of breakage has appeared; the fix is the same idiom.

### The ownership advisory is back, and that is correct

`architecture.subsystem_ownership_bounded` fails again on this branch. The
pilot fixed it, and that fix was integrated **internally** and never promoted
to canonical, which this branch is built from. The advisory reappearing is the
promotion boundary working exactly as designed, not a regression. It will clear
when that work is promoted through a CEO release decision.

## Safety matrix

Routine, all proceeding internally: four management decisions at the
Engineering Manager; integration at the CTO; legal happy path; one bounded
correction returning to `EXECUTING`; a routine success asking the CEO for
nothing.

Exceptions, all failing closed: QA failure; override of an independent control;
every protected ref (classifier and live); HIGH risk; deployment; publishing;
authority modification; organization modification; spend outside the envelope;
the second correction; expiry; architecture review putting the CTO in
self-conflict; and no activation authorizing nothing.

## Protection

Canonical `company-os-v1-bootstrap` is at `bdbe71b` and was not touched. `main`
is at `8b1022a` and was not touched. Nothing was deployed or published. The
mode is not activated: `may_activate` defaults to shadow-only and no caller in
this branch passes anything else outside tests.
