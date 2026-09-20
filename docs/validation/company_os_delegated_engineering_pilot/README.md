# Evidence — the bounded live-delegation pilot

Produced on 2026-09-20 from `company-os-v1-delegated-engineering-pilot`, whose
parent is the canonical `company-os-v1-bootstrap` at `45b4739`.

**Nothing here activated anything.** Every artifact is the output of a
read-only command or a test run. No work order ran, no branch moved, no money
was spent, and the pilot is not switched on in canonical.

| File | Command |
|---|---|
| `01-pilot-policy.txt` | `python -m company.delegation pilot-policy` |
| `02-pilot-policy.json` | `python -m company.delegation --json pilot-policy` |
| `03-pilot-simulation.txt` | `python -m company.delegation pilot-simulate` |
| `04-pilot-simulation.json` | `python -m company.delegation --json pilot-simulate` |
| `05-shadow-probes.txt` | `python -m company.delegation shadow` |
| `06-canonical-policy.json` | `python -m company.delegation --json policy` |
| `07-pilot-tests.txt` | `python -m pytest tests/test_company_delegation_pilot.py -q -p no:randomly` |
| `08-focused-suites.txt` | the six focused suites, `-q -p no:randomly` |
| `09-full-suite.txt` | `python -m pytest -q -p no:randomly` |
| `10-suite-evidence.json` | each required suite run individually, real numbers |
| `11-gate-report.txt` | `python -m company.integration check --suite-evidence 10-…` |

## What to read first

**`05-shadow-probes.txt`** — `SHADOW MODE: ENFORCED`, 5 of 5. The canonical
policy still refuses to leave shadow mode, and this is the probe that would
break first if the pilot had been built by loosening that guarantee. It was
not: the pilot is a layer above the canonical policy, not a mode inside it.

**`01-pilot-policy.txt`** — the whole delegated surface on one page. Two seats,
seven actions, one integration branch, three protected refs, and the line
`activated in canonical: NO`.

**`03-pilot-simulation.txt`** — the answer to "would this have worked?".

- Routine historical work: **4 of 5 proceeded internally, 0 CEO decisions.**
- The fifth, `burnin-job-c`, escalates and is reported under
  `DIVERGED FROM SHADOW` with its reason: the CTO filed that request, so the
  chain lands on the COO, who holds no live authority in a pilot the CEO
  bounded to two seats. That is the pilot being narrow, not wrong, and it is
  printed rather than smoothed over.
- All five original control probes still require the CEO.
- Five new probes: four refuse (failed QA, `main`, an expired envelope, a
  second correction) and one succeeds (integration onto the pilot branch).
  The success case is load-bearing — without it the `main` probe would prove
  only that *something* refused, not that the branch was what refused.
- `SHADOW REMAINS THE DEFAULT`: the same scenarios with no activation
  authorize 0 actions.

**`11-gate-report.txt`** — `READY`, 34 of 34 required checks, zero blockers.
The single advisory failure, `architecture.subsystem_ownership_bounded`, is
pre-existing and fails identically on the parent commit; it is not caused by
this branch.

## Suites

`07` — 159 new tests, all passing. `08` — the six focused suites, 755 passing,
unchanged from the parent. `09` — the full suite: **5004 passed, 6 failed**,
against the parent's 4845 passed and the same 6 failures. 4845 + 159 = 5004, so
every new test passed and nothing regressed.

The 6 failures are the known Godot-and-render-artifact set
(`test_a_missing_godot_is_reported_rather_than_raised` and five
`sloped_v25*_world` tests needing render outputs that are not in git). The
failing test names are byte-identical between the two runs.

## What is still true after all of this

- Canonical Company OS runs in shadow. Default behaviour is unchanged.
- `main` was never touched.
- Public deployment and publishing remain CEO-reserved; no pilot seat holds
  either.
- No subagents were used.
- The pilot awaits a separate CEO activation decision.
