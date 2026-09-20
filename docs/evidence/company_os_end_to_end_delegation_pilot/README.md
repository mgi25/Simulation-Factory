# Evidence — the first complete objective-to-result pilot

Every file here was produced by running the shipped code. Five real provider
sessions; total spend USD 2.375925 of a 6.00 envelope.

## By layer

| Layer | Files |
|---|---|
| **CEO** | `ceo_objective.json` — one objective, one envelope, nothing else |
| **EXECUTIVE** | `planning_brief.json` (3,245 chars — no source, no paths to read), `planner_prompt.txt`, `planner_session_raw.json`, `planning_run.json` |
| **MANAGEMENT** | `intake_attempts.json` (the fallback to the second candidate), `correction_authorization.json` (bounded correction 1 of 1) |
| **WORKER** | `dev1_receipt.json`, `correction_receipt.json` |
| **REVIEWER** | `review1_attestation.json`, `correction_attestation.json`, `review_result.json` |
| **DETERMINISTIC CONTROL** | `eligibility.json`, `intake_job.json`, `intake_result.json`, `receipt_result.json`, `runner_run.json`, `correction_runner_run.json`, `cto_integration_decision.json` |
| **AUTHORITY** | `pilot_activation.json` — objective-bound, expires 2026-09-27 |
| **TELEMETRY** | `telemetry.json` |

## The four refusals, all deterministic

1. **Intake refused the executive's first choice.** `intake_attempts.json`: the
   work order for `reserved-screening-negation-blindness` is titled "…reserved
   and **credential** screening…", and `screen_credentials()` fires on the word.
   The candidate describes a defect whose symptom blocks its own fix.
2. **Receipt validation refused developer attempt 1.** `dev1_receipt.json`:
   `outcome: rejected`, `remote_verified: false`. Caused by the orchestration
   running with `--no-push` — disclosed in §4 of the report.
3. **Review adjudication took the worse verdict.** `review_result.json`:
   attested `pass`, deterministic `changes_required`, three findings — one
   protocol, two genuine engineering advisories.
4. **`evaluate_live` refused the integration.** `cto_integration_decision.json`:
   the CTO holds `approve_integration_merge`, but its employee
   `chief_architect` reviewed this work, so the seat is disqualified. The COO
   lacks the grant. The chain reaches the CEO.

## The work

Corrected commit `477f9435e876` on `eng-auth-migration-correction`:

```python
# A backtick span that contains only word characters (no whitespace): `func_name`.
# Multi-word spans like `schema migration` are intentionally excluded so that
# trigger terms inside them still escalate as described work.
_QUOTED_IDENT = re.compile(r"`\w+`")
```

The first attempt used `` `[^`]+` ``, which the reviewer caught: it would have
silently dropped `` `schema migration` `` from routing. The correction narrowed
it to `\w+` and added 19 lines of tests pinning both directions.

## Reproducing without spending

`planner_session_raw.json`, both receipts and both attestations are the real
artefacts. The deterministic stages replay from them at zero model cost, which
is how the second state directory was validated after the branch was pushed.
