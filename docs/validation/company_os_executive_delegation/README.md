# Validation evidence — executive delegation (shadow)

Everything here was produced by running the code at `99bb1f9` on
`company-os-v1-executive-delegation-shadow`. Nothing is estimated, hand-written
or backfilled, and nothing here spent a model session.

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

## What they show

**`04-shadow.json` — the important one.** Five probes against the canonical
`company/engineering/decision.py` and this package: a CEO decision still names a
human, an approval still carries no merge authority, only `ready_for_approval`
can be approved, no delegation record can claim to have acted, and a policy
cannot leave shadow mode. All five hold.

**`03-replay.json`** — five real jobs replayed. 5/5 match the expected
direction, `disagreements` is empty. The three clean engineering jobs are
approved at `cto` with no management exception; Job A escalates on
self-approval plus a spent attempt ceiling; Job C's stop is handled at `coo`.

**`07-gate-report.txt`** — `READY`. 34 of 34 required checks pass, zero
blockers. The four advisory items are pre-existing: seven `company/workforce`
and `knowledge` modules no capsule claims, and three conditions that need a
state directory or a classified production run nobody supplied.

**`08-full-suite.txt`** — 4800 passed, 6 failed, all six pre-existing
production-render tests that also fail on the base commit.

## What they are not

None of this is authority. A replay result saying `cto` *would* have approved
Dogfood #2 is a statement about a policy file, not a decision — and
`03-replay.json` carries `"authorizes_action": false` on every one of them.
