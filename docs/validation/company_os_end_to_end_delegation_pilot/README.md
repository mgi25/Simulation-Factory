# Validation — end-to-end delegation pilot

## Stage 1/2: executive planning into canonical

The delta `0b83aed..92b308c` is one commit touching only
`company/delegation/{__init__,__main__,actions,discovery,executive,planning_run}.py`,
`company/delegation_policy.yaml`, the executive-planning tests and its docs. No
`pilot_*.py`, no activation identifier in any module. The only textual match
for `PilotActivation` / `evaluate_live` / `PilotBoundaryViolation` anywhere in
the delta is inside the test that **asserts their absence**.

So no curation was needed: the candidate is `92b308c` itself, and the fast
forward was clean.

| | |
|---|---|
| focused suites | 795 passed |
| gate, real suite evidence | READY — 34 pass, 0 blockers |
| full suite (same tree) | 6 failed, 5008 passed |
| canonical after | `92b308c`, `mode: shadow`, zero pilot modules |

## Stage 3/4: composing planning with the live-delegation runtime

Ported from `19b1e0a`: the seven pilot modules, `PilotBoundaryViolation`, the
pilot tests, the design doc. Not ported: any objective-planning code (canonical
owns it now) and the docs-only `46c78d0` commit.

`README.md` and `delegation/__main__.py` were hand-reconciled, because both the
pilot and the planning work had edited them. The CLI now carries `candidates`,
`plan`, `plan-run`, `pilot-policy` and `pilot-simulate` together.

**One test failed the composition, and it was mine.** The executive-planning
suite asserted that no `pilot_*.py` existed beside the planning modules — true
of the branch it was written on, and the wrong assertion, because it failed for
the one composition it was meant to make safe. It now asserts what survives
composition: the planning layer never *reaches for* pilot code, and where the
pilot does exist it is inert (`evaluate_live` defaults to no activation).

| | |
|---|---|
| combined focused suites | 655 passed |
| the 11 gate-required suites | 809 passed, 0 failed |
| gate, real suite evidence | READY — 34 pass, 0 blockers |
| full suite | **6 failed, 5168 passed, 337 skipped** |

**Zero new regressions.** The six are the documented pre-existing set
(`test_sloped_v251_world.py` ×4, `test_sloped_v252_world.py`,
`test_neon_proof.py`) — missing gitignored render artefacts.

Deterministic controls confirmed before any spend: shadow remains the canonical
default, the pilot requires an explicit activation, `PROTECTED_REFS` still holds
`main`, `master` and `company-os-v1-bootstrap`, reviewer/manager separation and
the QA-override refusal are asserted by the pilot suite.
