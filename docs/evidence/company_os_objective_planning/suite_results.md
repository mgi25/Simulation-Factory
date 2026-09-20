# Test results

## Targeted

| Suite | Result |
|---|---|
| `tests/test_company_objective_planning.py` (new) | **91 passed** |
| `tests/test_company_delegation.py` | passed |
| `tests/test_company_delegation_pilot.py` | passed |
| `tests/test_company_engineering_execution.py` | passed |
| `tests/test_company_os_capsules.py` | passed |
| the five together | **648 passed** |

## Company OS

`-k "company_delegation or company_engineering or company_os or
objective_planning or workforce or org_intelligence"`

**1279 passed, 0 failed.**

## Full repository

```
6 failed, 5094 passed, 337 skipped in 626.00s
```

**Zero new regressions.** All six failures are the documented pre-existing set,
unchanged:

| Module | Failures | Cause |
|---|---|---|
| `tests/test_sloped_v251_world.py` | 4 | missing `output/sloped_race_v1/cameras_v221_5432.json` |
| `tests/test_sloped_v252_world.py` | 1 | same missing camera track |
| `tests/test_neon_proof.py` | 1 | gitignored render artefact |

`docs/company_os_v1_external_runner_hardening.md` §6 records the same six:
*"pre-existing failures | 6, unchanged: `test_neon_proof.py` and the two
`test_sloped_v25*_world.py` modules, all gitignored render artefacts."* None is
touched by this branch, which changes no rendering, race or `tools/` code.

## Integration gate

`python -m company.integration check --repo-root . --as-of 2026-09-20`

```
PRODUCTION INTEGRATION READINESS: INSUFFICIENT_EVIDENCE
checks      33 pass, 1 fail, 4 unknown, 0 not_applicable
BLOCKERS (1)
  health.required_suites_pass
    why  no reported run for tests/test_company_analytics.py; ...
```

The single blocker is the absence of `--suite-evidence`, which is a harness
input rather than a property of the code: a bare gate run has no record of
which suites were executed. Every structural check passes, including
`production.no_publishing_capability`, `health.no_new_dependency` and
`production.integration_remains_disabled`. Full report in
`integration_gate.txt`.
