# Validation evidence — organizational staffing (shadow)

Produced by running the code at `a9e25b7` on
`company-os-v1-management-staffing-shadow`. Nothing is estimated or
hand-written, and nothing here spent a model session.

| File | Command |
|---|---|
| `01-policy.json` | `python -m company.delegation --json policy` |
| `02-chart.txt` | `python -m company.delegation chart` |
| `03-replay.json` | `python -m company.delegation --json replay` |
| `04-shadow.json` | `python -m company.delegation --json shadow` |
| `05-replay.txt` | `python -m company.delegation replay` |
| `06-suite-evidence.json` | one `pytest` run per gate-required suite |
| `07-gate-report.txt` | `python -m company.integration check --suite-evidence 06-…` |
| `08-full-suite.txt` | `python -m pytest tests -q -p no:randomly` |
| `09-deployment-policy.txt` | `python -m company.delegation deployment` |
| `10-ceo-report.txt` | `python -m company.delegation report` |
| `11-control-probes.json` | the five counterfactual probes, replayed |

## Read these two together

**`03-replay.json`** — the five real jobs. All five resolve below the CEO, and
in every one the approving employee is neither the implementer nor the
reviewer. `registry_conflicts` in `01-policy.json` is now empty: the two the
previous phase reported were caused by the vacant Engineering Manager seat.

**`11-control-probes.json`** — five conditions under which the model must still
refuse, and does: a reviewer who would approve its own finding, a manager
overruling a failing check, an unclassified deployment, a spend four times the
company budget, and a seat widening its own ceiling. All five require the CEO.

The first file alone would only show that the model approves things. The second
is what makes "0 CEO escalations" mean something.

## The rest

**`04-shadow.json`** — the five stop-semantics probes, all holding. The
canonical CEO decision still names a human and still carries no merge
authority.

**`09-deployment-policy.txt`** — five deployment kinds classified, `activated:
false`, granted to no seat.

**`07-gate-report.txt`** — `READY`, 34 of 34 required checks, zero blockers.
The four advisory items are the ones that were already advisory.

**`08-full-suite.txt`** — 4845 passed, 6 failed; the same six pre-existing
production-render failures as the previous phase.

## What none of this is

Authority. Every decision in `03-replay.json` and `11-control-probes.json`
carries `"authorizes_action": false`, and `01-policy.json` reports
`"mode": "shadow"`. Staffing two seats changed who *would* decide. It did not
let anything decide.
