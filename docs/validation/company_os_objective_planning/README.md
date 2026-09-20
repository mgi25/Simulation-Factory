# Curation record — objective planning into canonical

The objective-planning branch descends from the isolated live-pilot lineage, so
it was **not** merged. This candidate was built from canonical
`45b4739091e4b8a7c38d13f6855cd1965e5790ca` and the planning functionality was
moved across file by file.

## What the pilot lineage added, and what crossed

| File | Origin | Crossed? |
|---|---|---|
| `company/delegation/pilot*.py` (7 modules) | live pilot | **no** |
| `tests/test_company_delegation_pilot.py` | live pilot | **no** |
| `company/delegation/errors.py` (`PilotBoundaryViolation`) | live pilot | **no** |
| `docs/company_os_delegated_engineering_pilot.md` | live pilot | **no** |
| `docs/validation/company_os_delegated_engineering_pilot/` | live pilot | **no** |
| `candidates.py`, `planning.py`, `planning_record.py`, `candidate_seeds.json` | planning | yes |
| `company/engineering/criteria.py` | planning | yes |
| `actions.py` (`SELECT_WORK`), `org.py`, `store.py`, `__init__.py` | planning | yes |
| `delegation_policy.yaml` (grants + autonomy rung) | planning | yes |
| `intake.py`, `engineering/__main__.py`, `orchestrator.py` | planning | yes |
| `tests/test_company_objective_planning.py` | planning | yes |
| `docs/company_os_objective_planning.md` + evidence | planning | yes |
| `docs/company_os_first_live_delegation_pilot.md` + evidence | pilot **documentation** | yes — docs only |

The failed-pilot report crossed because it is the evidence `criteria.py` and
`candidate_seeds.json` cite, and because a capability whose reason for existing
is undocumented invites its own removal. It is prose; it activates nothing.

## Coupling check

`candidates.py`, `planning.py`, `planning_record.py` and `criteria.py` import
`ai_platform`, `company.efficiency.profile`, `company.finance.money` and their
own package siblings. **None imports a `pilot_*` module, `PilotActivation`,
`evaluate_live` or `PilotBoundaryViolation`.** Their only mentions of the pilot
are docstring references to the report path. Planning was separable, and this
candidate is the proof.

Two files needed hand-porting rather than copying, because the pilot had also
edited them: `company/delegation/README.md` and `company/delegation/__main__.py`.
The canonical versions were taken and only the planning edits re-applied. The
resulting `__main__.py` contains zero occurrences of "pilot".

## Validation

| | |
|---|---|
| objective-planning + delegation + engineering | **423 passed** |
| the 11 gate-required suites | **809 passed, 0 failed** |
| integration gate, with real suite evidence | **READY — 34 pass, 0 blockers** |
| shadow probes | all pass; `mode: shadow` unchanged |

The one advisory FAIL (`architecture.subsystem_ownership_bounded`, 7 unclaimed
modules in `company/workforce/` and `knowledge/`) is pre-existing and identical
to the reading in `docs/validation/company_os_delegated_engineering_pilot/11-gate-report.txt`.
It is advisory, not required, and names no file this candidate touches.
