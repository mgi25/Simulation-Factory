# Autonomy readiness review, after the intake-classifier hardening pass

**Status: a review, not a job.** No developer/reviewer session ran for this document. It
synthesizes real supervised-run evidence already on record
([`docs/company_os_supervised_burnin.md`](company_os_supervised_burnin.md),
[`docs/company_os_supervised_burnin_correction.md`](company_os_supervised_burnin_correction.md),
[`docs/company_os_supervised_burnin_b_and_c.md`](company_os_supervised_burnin_b_and_c.md))
plus the deterministic classifier fix on a separate branch,
`company-os-v1-intake-classifier-negation-fix` @ `da4f3ce` (pushed, not merged;
`docs/company_os_intake_classifier_hardening.md` there has the fix's full technical
evidence — defect, root cause, fix, test matrix, before/after, regression results).

## 1. The named blocker: fixed and verified

`AUTONOMY_DECISION_BLOCKED_BY_INTAKE_CLASSIFIER_DEFECT` named one specific defect: the
intake classifier escalated a job to the architecture specialist tier when the objective
merely *prohibited* architecture-shaped work ("do not redesign the schema", "no migration
machinery"). That defect is now fixed on
`company-os-v1-intake-classifier-negation-fix` @ `da4f3ce`:

- 18 new deterministic tests covering negated-only, positive-control, mixed-clause, and
  normal-routine wording, plus a regression test using the exact historical objective text
  that produced the real false positive.
- Real CLI dry-run intake, same request, before/after: `specialist_domain` goes from
  `"architecture"` (unfixed, at `c78e444`) to `""` (fixed, at `80a1ee6`).
- A genuine specialist-positive objective still escalates correctly after the fix (real CLI
  dry-run: `"security"`, via `"authentication"`).
- Full repository suite: 4662 passed / 6 failed / 337 skipped on the fixed branch vs. 4644
  passed / 6 failed / 337 skipped on the unfixed base — the same 6 pre-existing,
  gitignored-artifact failures by name, **zero new regressions**.

## 2. A second, distinct classifier defect found while verifying the first

Building the required "positive/must-escalate" test cases surfaced a **false-negative**
gap, not covered by the fix above and not previously recorded anywhere in this program:
objectives that are genuinely specialist-shaped but use words absent from
`SPECIALIST_TRIGGERS` — bare `"architecture"` ("change system architecture"), any form of
`"deploy"`/`"deployment"` ("deploy the service") — **do not escalate at all**, before or
after the negation fix. This is a vocabulary-coverage gap, not a negation-scoping bug, and
closing it means adding trigger terms, which the CEO's brief for the hardening pass placed
out of scope ("do not change... specialist definitions"). It is recorded here, unresolved,
by design.

**Why this matters for the specific decision being made:** it does not compromise
containment — bounded write authority, reviewer independence, worst-verdict-wins, and gate
enforcement all apply identically regardless of which tier a job is classified into (a job
that under-escalates still goes through the same one-attempt, disjoint-review,
gated pipeline; it just may run on a cheaper model than the work deserves). But it is a
live, real, unresolved defect in the exact deterministic routing mechanism the CEO named as
the sole blocker, discovered in the course of hardening that same mechanism — and routine
autonomous engineering is precisely the mode in which no CEO reviews an objective's wording
before submission to notice the gap.

## 3. Autonomy-readiness matrix (14 control areas)

Evidence sources: `docs/company_os_supervised_burnin.md` (Dogfood #2 lineage note, Job A),
`docs/company_os_supervised_burnin_correction.md` (correction job),
`docs/company_os_supervised_burnin_b_and_c.md` (Job B, Job C stop), and
`docs/company_os_intake_classifier_hardening.md` on the fix branch (deterministic classifier
tests). Four real supervised jobs completed to date: Job A (rejected at review), the
correction (READY), Job B (READY), plus one real correctly-refused pre-flight (Job C).

| # | Control area | Verdict | Evidence |
|---|---|---|---|
| 1 | Deterministic intake/routing (capsule ownership, path scope derivation) | **PASS** | Every real job derived `authorized_paths`/`forbidden_paths` correctly from capsule ownership; the original burn-in's own job-sourcing step correctly refused to invent scope for the unowned `tools/engineering_runner` and returned `DECISION_REQUIRED` instead of guessing. |
| 2 | Bounded write authority | **PASS** | Zero unauthorized writes across Job A, the correction, and Job B — every `authority.json`/`read_only.json` checked, 0 violations each time. |
| 3 | Resource-profile enforcement | **PASS** | `consumer` profile and `model_tier: standard` held on every real job; no real session ever ran at an unauthorized tier (the classifier defect was caught by dry-run before any real submission, so it never caused a wrong tier to actually run). |
| 4 | One-attempt enforcement | **PASS** | Job A's one spent developer attempt correctly blocked any retry (stopped at `decision_required`); `max_developer_attempts: 1` respected on every job. |
| 5 | Receipt validation/prevalidation | **PASS** | Every real receipt this program was well-formed and accepted first try; the `b12caa8` malformed-receipt defense exists from Dogfood #1 but was not re-exercised by a fresh malformed receipt in these four jobs. |
| 6 | Reviewer independence | **PASS** | Disjoint employee capability and read-only packet on every job, 0 violations; Job A is a direct proof — the reviewer caught a real defect the developer and deterministic QA both missed. |
| 7 | Worst-verdict-wins adjudication | **PASS** | Job A: deterministic `pass` + attested `changes_required` → adjudicated `changes_required`, exactly per rule. |
| 8 | Deterministic QA | **PASS** | Exact pass counts recorded and cross-checked by the gate on every real job (140, 140, 158). |
| 9 | Integration-gate enforcement | **PASS** | Gate correctly refused to run on Job A (review not passed); correctly returned `READY` 11/11 only when review had passed (correction, Job B). |
| 10 | CEO approval stop | **PASS** | Every job stopped at `decision_required`/`ready_for_approval`; nothing merged anywhere without an explicit recorded CEO decision, this entire program. |
| 11 | Reliable external-runner telemetry | **PASS** | Real, provider-reported cost/tokens/turns for all 8 real sessions (4 jobs × developer+reviewer), `usage_source: model_usage_totals` every time, none estimated. |
| 12 | Automatic-continuation prevention | **PASS** | The original burn-in stopped the A→B→C batch after Job A's `changes_required` rather than auto-proceeding; this pass stopped Job C before submission rather than auto-continuing past a failed precondition. |
| 13 | Failure/refusal handling | **PASS** | Job A's review failure handled with no bypass or retry; Job C's schema pre-flight failure handled by refusing to fabricate an identifier rather than inventing one. |
| 14 | Specialist-classifier correctness after this fix | **PARTIAL** | The named negation false-positive is fixed and verified (§1). A second, distinct false-negative vocabulary-coverage gap in the same mechanism (§2) was found this pass and remains unresolved by design. |

**13 of 14 areas PASS. One, PARTIAL — the same mechanism the CEO named as the blocker,
now carrying a different, real defect than the one just fixed.**

## 4. Job C: recorded as a deferred design gap

**Status: `DEFERRED_DESIGN_GAP`.** Per the CEO's instruction, recorded and not
implemented: usage/cost event deduplication (the purpose behind Job C) requires a stable
identifier for "the same measured provider response/event," and the current
`ai_platform.usage.ResourceUsageRecord` carries none — `task_id` is shared by every
attempt of one work order, and the one identifier-shaped field nearby
(`UsageObservation.usage_ref`) is supplied by the caller from the store's file-sequence
position, not read from the record or the provider (full analysis:
[`docs/company_os_supervised_burnin_b_and_c.md`](company_os_supervised_burnin_b_and_c.md),
Part 3). No identifier was invented and the telemetry schema was not changed. This gap sits
outside the engineering-execution loop entirely (it is a finance/telemetry schema question,
not a control-plane defect), so it does not enter the readiness matrix above and does not
bear on the autonomy decision.

## 5. Aggregate program telemetry (unchanged by this pass — no session ran)

Real sessions across the whole program to date: Job A ($1.0636907499999999) + correction
($1.1758087499999998) + Job B ($0.5538657499999999) = **$2.7933652499999996**, 4 developer
attempts, 4 reviewer passes, 0 retries, 0 unauthorized writes, 0 automatic continuations.
This hardening pass added no real session and no cost.

## 6. Recommendation

**`NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`**

Not because the containment controls are weak — 13 of 14 areas pass on real, cumulative
evidence, including the exact defect this pass was chartered to fix. It is because
hardening that one mechanism surfaced a second, real, still-open defect *in that same
mechanism* (§2), and routine autonomous engineering is specifically the mode that removes
the human who would otherwise notice a mis-routed objective's wording. Recommending
`READY_FOR_CEO_DECISION_ON_ROUTINE_AUTONOMOUS_ENGINEERING` while a live routing defect sits
unresolved in the routing mechanism itself would understate what "the blocker is fixed"
should mean, even though nothing here suggests the accumulated supervised-job evidence
(§3, items 1–13) is thin — it is not.

**Recommended narrow next step (not undertaken in this pass, and not authorized by it):**
a dedicated, separately-scoped vocabulary-coverage review of `SPECIALIST_TRIGGERS` — is
"architecture" as a bare term too broad to add safely, does "deploy"/"deployment" need a
narrower phrase the way "governance" was narrowed to specific actions in the V3A fix — before
the autonomy decision is reconsidered. This is explicitly a future, separate CEO-authorized
pass, not a standing instruction to proceed.

## 7. Evidence paths

- `docs/company_os_autonomy_readiness_review.md` (this file)
- `docs/company_os_intake_classifier_hardening.md`,
  `company/engineering/intake.py`, `tests/test_company_engineering_execution.py` on
  `company-os-v1-intake-classifier-negation-fix` @ `da4f3ce` (pushed, not merged)
- `docs/company_os_supervised_burnin.md`, `docs/company_os_supervised_burnin_correction.md`,
  `docs/company_os_supervised_burnin_b_and_c.md` (this branch)

## 8. Confirmations

- `main` (`8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f`) and `company-os-v1-bootstrap`
  (`b84f8a75a2d4aaeefd88798f23bc5948e7d39195`) unchanged throughout this pass (checked via
  `git ls-remote origin` before the classifier fix branch was created and again before this
  document was pushed).
- No new real dogfood/engineering-execution job was started this pass. The classifier fix
  was implemented directly, not run through `company/engineering` + `tools/engineering_runner`
  as a work order.
- No orchestration subagents (`Agent`/`Task`/child/parallel workers) were used at any point
  in this pass. No separate model process ran either — unlike the prior jobs, this pass
  involved no developer or reviewer session at all.
- Autonomous engineering remains disabled. Nothing here enables it or is intended to.
