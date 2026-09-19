# The second real Company OS engineering dogfood

**Date:** 2026-09-19
**Branch (Company OS state, this report, the reliability fix):** `company-os-v1-dogfood-receipt-prevalidation`, based on `company-os-v1-first-real-dogfood` @ `834e7b1`
**Branch (developer's implementation, pushed and unmerged):** `eng-ceo-page-attempts-remaining` @ `7a594d28fe9d0d8c77b14a846e8d53bc4a4b08db`
**Authorization:** one supervised, single-attempt, one-provider, one-reviewer-pass work order, run through the external engineering runner. Autonomous Company OS engineering remains PAUSED and was not touched. Not authorization to merge either branch.

---

## 1. Why this run exists

The first real dogfood ([`docs/company_os_first_real_dogfood.md`](company_os_first_real_dogfood.md)) found one
reliability defect: a receipt refused only for the *shape* of its required-test evidence (suites
folded into one combined command) was indistinguishable, to the attempt budget, from a failed
implementation. Refusing it moved the job `developing -> testing` and spent the work order's one
developer attempt; a corrected receipt for the same passing commit could never be re-ingested,
because ingestion only accepts a receipt while the job is `developing`.

This run had two purposes: fix that defect narrowly, and use the fixed runtime for a second
supervised job — this time through the **external engineering runner** rather than interactively,
so the run would carry real provider telemetry, which the first run could not.

## 2. Preserving the first dogfood

Nothing under `docs/company_os_first_real_dogfood.md` or
`docs/evidence/company_os_first_real_dogfood/` was touched. `company-os-v1-first-real-dogfood`
stays at `834e7b1`, unmodified. The reliability fix and this run both live on a new branch created
from that commit.

## 3. The reliability fix

Root cause: `ingest_developer_result` (`company/engineering/orchestrator.py`) advanced the job
`developing -> testing` unconditionally, whatever the receipt's `IngestedSession.validation`
said — the docstring even stated it plainly: *"the attempt is recorded whether or not it
passes."* `_attempt_report` (`company/runtime/session_adapter.py`) turns any validation failure
into `Outcome.REJECTED` regardless of what the receipt claimed, so a combined-command receipt and
a genuinely broken implementation produced the identical job transition.

**Fix**, commit [`b12caa8`](https://github.com/mgi25/Simulation-Factory/commit/b12caa8ff45fe986e94cdf670ca768b99c385ed9)
on `company-os-v1-dogfood-receipt-prevalidation`:

- `ReceiptValidation` (`company/runtime/receipts.py`) gains `evidence_format_only: bool`, true
  exactly when the receipt's *only* failure is the required-test evidence gap (`_accepted_failures`
  now returns that gap separately from every substantive failure — a dirty tree, a wrong branch, a
  reported failing test, a missing summary). `ManualExternalSessionAdapter._widen`
  (`company/runtime/session_adapter.py`) clears the flag if it later adds an owner or
  repository-evidence failure, so it can never survive being widened by something real.
- `ingest_developer_result` checks the flag before calling `job.advance(TESTING, ...)`. An
  evidence-format-only rejection **records the receipt** (the audit trail is unchanged — a
  rejected attempt was always persisted) but returns the job **unmoved**, still `developing`, so a
  corrected receipt for the same packet can be ingested again without spending a second attempt.
- A receipt naming a *different* commit than the one already on file for this packet is refused
  outright — the correction channel exists to fix a report, not to smuggle a second implementation
  attempt past a one-attempt work order.
- `DeveloperResult.job_pointer` is now `EngineeringRecordPointer | None`, `None` exactly when
  nothing was appended to the job store; a new `evidence_rejected` property exposes the flag to
  callers, and the CLI's `receipt` command reports it.

Ten focused tests in `tests/test_company_engineering_execution.py` pin the invariant: a valid
receipt is unaffected; a malformed receipt never reaches the job; a receipt missing one of two
required suites, and one reporting both as a single combined command, are both refused without
moving the job or spending the attempt; a corrected receipt for the same commit is then accepted;
a "corrected" receipt for a different commit is refused; a genuinely failing test still spends the
attempt exactly as before; review policy, no-retry and the audit trail are each checked directly.

Required suites: 789 passed. Full suite: 6 failed / 4642 passed / 337 skipped — the same six known
gitignored-artifact / Godot-render failures as every prior baseline, zero new.

## 4. Telemetry check (before running the second job)

`tools/engineering_runner/backends.py`'s `ClaudeCodeBackend.launch` already invokes
`claude --print --output-format stream-json --verbose ...` and reads token/cost/model/turn counts
from the provider's own envelope in `_read`/`normalise_claude_usage`. This is the Repository
Exploration Efficiency V2 fix, already on the canonical lineage this branch descends from. `python
-m tools.engineering_runner doctor` confirmed the installed backend (`claude_code`, Claude Code
`2.1.70`) is available before the run. No telemetry gap needed to be worked around, and none was
estimated over.

## 5. The second work order

| | |
|---|---|
| **Work order** | `wo-req-ceo-page-attempts-remaining` (`9e0f02d3fa64c6de`) |
| **Request** | `req-ceo-page-attempts-remaining` (`fc04ea843fb7b621`) |
| **Objective** | The CEO result page reports developer attempts *used* but never attempts *remaining* against the work order's own ceiling, forcing the reader to subtract two numbers by hand. Add a field to `EngineeringResult` for attempts remaining, sourced from the job's existing `EngineeringJob.corrections_remaining`, and show it on the page. |
| **Why not the first dogfood's task** | Different subsystem behaviour (a reporting gap on the CEO page, not a CLI authority-echo gap), different files, different capsule context. |
| **Risk / reversible** | LOW / yes |
| **Capsule** | `company-engineering-execution`, matched by path — *"owns company/engineering for task path company/engineering"* |
| **Authorized paths** | `company/engineering`, `tests/test_company_engineering_execution.py` |
| **Forbidden paths** | `company/constitution.md`, `company/integration`, `company/permissions.yaml`, `company/runtime`, `sloped`, `tools`, plus the ten protected governance files |
| **Specialist domain** | none — routine implementation |
| **Reasoning class ceiling** | D; resolved tier **standard** |
| **Resource profile** | `consumer` — 1 provider, 1 developer attempt, 1 reviewer pass, no auto-continue |
| **Required tests** | `tests/test_company_engineering_execution.py` (one suite; reported as its own receipt entry, satisfying the per-suite evidence requirement trivially since there is only one) |

This is a genuine, previously-unaddressed gap in the *canonical* `company/engineering/result.py` —
every earlier "attempts remaining" implementation lives on unmerged `eng-attempts-remaining*`
benchmark branches and was never part of the lineage this work order builds on.

Considered and rejected: fixing the `_blocked_attempt` / `--repo-dir` inconsistency recorded as a
follow-up in `external-runner-hardening-stop-condition` (`tools/engineering_runner/runner.py`'s
authority-violation path omits `repo_dir` from `submit_receipt`, unlike the ordinary developer-stage
path). No capsule owns `tools/engineering_runner` — `assess_request` correctly refuses an unowned
subject with `DECISION_REQUIRED` rather than guessing a scope — so that fix cannot go through
deterministic Company OS intake/routing at all, and authoring new capsule ownership is exactly the
kind of architecture change this run was told not to do.

### Authority granted

Developer: `ExecutionAuthoritySnapshot` `27d8ea77636dc419`, source `temporary_task_override`,
`may_write` exactly `company/engineering` and `tests/test_company_engineering_execution.py`,
`no_subagents: true`. Reviewer: a second snapshot for `chief_architect`, `may_write: []` (read-only
packet).

## 6. Execution, through the external runner

`python -m tools.engineering_runner run-one wo-req-ceo-page-attempts-remaining` — one run, one
lease, no retries, `claude_code` backend for both roles, `--push` on (the default).

**Lifecycle, six transitions, one developer attempt:**

```
requested   -> planning     : implementation plan 8f63c1b1404b92b0 derived from the work order
planning    -> developing   : packet 9ef0951b60f7fbe7 attempt 1 issued to software_implementation_engineer
developing  -> testing      : attempt 1 recorded accepted
testing     -> reviewing    : review packet issued to chief_architect (implementer software_implementation_engineer)
reviewing   -> gate         : review rev-wo-req-ceo-page-attempts-remaining-01 passed (chief_architect)
gate        -> ready_for_approval : integration gate integration-readiness-2026-09-19-4042a9b35ac14439 is READY
```

No receipt rejection occurred this run — the developer session reported its one required suite as
its own receipt entry on the first try, so the new prevalidation path was not exercised here (it
is exercised by the ten unit tests in §3 instead). `developer_attempts` ended at 1 of 1 authorized;
`corrections_remaining` is 0, correctly, because the one attempt succeeded rather than because it
was spent on a format defect.

### What the developer did

Commit [`7a594d28`](https://github.com/mgi25/Simulation-Factory/commit/7a594d28fe9d0d8c77b14a846e8d53bc4a4b08db)
on `eng-ceo-page-attempts-remaining`, pushed and remote-verified, two files:

- `company/engineering/result.py` — added `developer_attempts_remaining: int` to
  `EngineeringResult`, populated in `build()` as `job.corrections_remaining` (no arithmetic
  reimplemented), rendered on the CEO page as `developer attempts: N  remaining: M`.
- `tests/test_company_engineering_execution.py` — one new test,
  `test_developer_attempts_remaining_field_and_rendering`, covering the field's value, the render
  string and the `to_dict`/`from_mapping` round trip.

139 tests passed (138 pre-existing + 1 new), reported as one receipt entry against the one required
suite. Disclosed risk: a result record serialized before this change deserializes with
`developer_attempts_remaining=0` via the `from_mapping` default, which the developer flagged
unprompted as needing a reviewer's judgment on whether historical records matter.

### What the reviewer found

`chief_architect`, disjoint from the implementer, read-only packet, full diff plus the file and
test regions changed. Verdict **PASS**, all five acceptance criteria satisfied with a named
evidence reference each. Two advisory findings, both cosmetic or already disclosed: two test
sections in the file are both numbered "15" (pre-existing collision, not introduced here), and the
same `from_mapping` default-zero risk the developer had already named. Deterministic QA agreed:
attested `pass`, deterministic `pass`, adjudicated outcome `pass` — no override needed this time
(contrast with the first dogfood, where deterministic QA *overrode* an attested pass).

### The gate

Run from its own CLI against real suite evidence: **11/11 required Company OS suites green**
(1,013 tests across the required suites, individually reported — `tests/test_company_analytics.py`
160, `test_company_dashboard.py` 32, `test_company_execution_transport.py` 14, and so on).
`integration-readiness-2026-09-19-4042a9b35ac14439`: 34/34 required checks pass, 0 blockers, the
same one pre-existing advisory FAIL (`architecture.subsystem_ownership_bounded`, unrelated,
untouched by this change) and three advisory UNKNOWNs that need a populated `--state-dir` for
decisions/workforce/production-suite evidence this run did not supply. `authorizes_production_integration:
false`, as always — the gate cannot authorize a merge into `main`.

## 7. Where it stopped

```
STATUS
  READY_FOR_APPROVAL

DECISIONS REQUIRED
  none

CEO OPTIONS
  [APPROVE]  [REQUEST CHANGES]  [REJECT]
  READY FOR CEO APPROVAL is a request to be read, not an approval. Nothing here merges,
  deploys or publishes, and Company OS holds no capability to.
```

No CEO decision was recorded. `eng-ceo-page-attempts-remaining` is pushed and **not merged**
anywhere; `git merge-base --is-ancestor origin/eng-ceo-page-attempts-remaining origin/main` and the
same check against `company-os-v1-dogfood-receipt-prevalidation` both report `NO`. `main` stayed at
`8b1022a` throughout — this run never fetched, rebased onto, or wrote to it.

The runner did not retry the developer session, did not re-run review, did not create a second
work order, did not escalate to a specialist tier, and did not request automatic remediation. It
ran exactly one work order and stopped.

## 8. Telemetry (real, this time)

| | developer | reviewer |
|---|---|---|
| backend / role | `claude_code` | `claude_code` |
| model | `sonnet` (standard tier) | `sonnet` |
| provider | `anthropic` | `anthropic` |
| duration | 355.3 s | 51.2 s |
| model turns | 40 | 5 |
| input tokens | 46 | 7 |
| output tokens | 16,410 | 2,312 |
| cache creation tokens | 77,125 | 24,333 |
| cache read tokens | 2,057,370 | 53,152 |
| cost | **$1.921196** | **$0.236492** |
| usage source | `model_usage_totals` (session-total, cross-checked) | `model_usage_totals` |
| cost ceiling enforced | yes | yes |
| unreliable metrics | none | none |
| repo file reads / repeated / searches | 13 / 10 / 2 | not applicable (read-only review packet) |
| subagents used | 0 | 0 |

Total measured cost for this job: **$2.157688**. Both figures are read from the provider's own
`stream-json` envelope, not estimated from packet bytes — the gap the first dogfood reported
(`tokens.source: unavailable`) does not appear anywhere in this run's receipts.

## 9. Assessment

| Question | Answer |
|---|---|
| 1. Receipt-prevalidation fix works? | **YES** — proven by the ten unit tests; not organically exercised by this clean run, which is itself informative (a careful session did not trip the defect this fix targets). |
| 2. Evidence-format rejection consumes an implementation attempt? | **NO** — an evidence-format-only rejection leaves `developer_attempts` and the job's state untouched; only a genuine outcome (accepted, or a substantively failed receipt) advances the job. |
| 3. Second real implementation succeeded? | YES — one attempt, accepted, all five acceptance criteria met. |
| 4. Reviewer behaved correctly? | YES — independent employee, read-only packet, PASS with two disclosed advisory findings, deterministic QA agreed. |
| 5. Deterministic QA behaved correctly? | YES — recomputed the same verdict as the attestation; worst-verdict-wins logic was available and not needed. |
| 6. Integration gate behaved correctly? | YES — 34/34 required, 0 blockers, `authorizes_production_integration: false`, same pre-existing advisory gaps as the untouched baseline. |
| 7. External runner telemetry captured reliably? | YES — real tokens, turns, cost and duration for both sessions, `usage_source: model_usage_totals`, nothing marked unreliable. |
| 8. Authority remained bounded? | YES — developer `may_write` exactly the two authorized paths; reviewer `may_write: []`; no file outside `company/engineering` and its own test touched; `main` untouched. |
| 9. Automatic continuation prevented? | YES — the run stopped at `ready_for_approval` with no decision recorded; nothing merged, deployed or published. |
| 10. Manual workaround required? | NO — no receipt rejection, no repair loop, no intervention of any kind. |

**Readiness classification: READY_FOR_MORE_SUPERVISED_REAL_JOBS.**

Not `READY_TO_CONSIDER_SEPARATE_CEO_DECISION_ON_ROUTINE_AUTONOMOUS_ENGINEERING` — one clean run
through the runner shows the pipeline and the new prevalidation logic both hold up under
supervision; it does not by itself retire [[consumer-resource-mode-stop-condition]]'s standing
concern (live repository exploration dominating resource use on a routine job), which this task
was too small to stress, and this run's own developer session still read 13 files with 10
repeats against a two-file change. That question needs its own matched measurement, not an
inference from a job this bounded. Autonomous Company OS engineering remains PAUSED.

## Evidence

Everything below is under `docs/evidence/company_os_second_real_dogfood/`.

| Artifact | Path |
|---|---|
| CEO request | `inputs/request.json` |
| Runner run summary | `runner/run_summary.json` |
| Developer briefing / receipt / receipt reply / session telemetry | `runner/developer_briefing.json`, `runner/developer_receipt.json`, `runner/developer_receipt_out.json`, `runner/developer_session.json` |
| Reviewer briefing / attestation / session telemetry | `runner/reviewer_briefing.json`, `runner/reviewer_attestation.json`, `runner/reviewer_session.json` |
| Integration gate report / per-suite evidence | `runner/gate_report.json`, `runner/gate_suites.json` |
| Company OS state (requests, work order, plan, jobs x6, receipts, attestations, reviews, gate verdict, results x2, authorities, resource usage) | `company_os_records/engineering/`, `company_os_records/execution/`, `company_os_records/resource_usage/` (named apart from `state/` only to clear this repository's blanket `.gitignore` rule for that name; the content is the runner's `--state-dir` output, unmodified) |
