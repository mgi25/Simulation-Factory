# Autonomy readiness review v2, after the coverage-vocabulary hardening pass

**Status: a review, not a job.** No developer/reviewer session ran. Supersedes
[`docs/company_os_autonomy_readiness_review.md`](company_os_autonomy_readiness_review.md)
(v1) by re-evaluating items 1 and 14 against two new findings from the coverage pass on
`company-os-v1-intake-classifier-coverage-fix` @ `eadd066` (fix `12f7cf8`, base `da4f3ce`,
pushed, not merged;
`docs/company_os_intake_classifier_coverage_hardening.md` there has the full technical
evidence). Items 2–13 are unchanged from v1 — nothing in this pass touched their evidence.

## 1. What changed since v1

**Closed:** three specialist-vocabulary coverage gaps (architecture: "architecture
change"/"change the architecture"/"system architecture change"/"change system
architecture"; governance: "approval policy"/"authority policy"; concurrency:
"synchroniz"), added to already-existing domains, verified via 39 new deterministic tests
and real CLI before/after dry-run intake. Zero new regressions (4701 passed/6 failed/337
skipped vs. 4662/6/337 baseline, same 6 pre-existing failures by name).

**Found, disclosed, deliberately not fixed (two distinct items):**

1. **`screen_reserved()`/`screen_credentials()` share the exact negation-blind pattern**
   the negation-fix pass fixed in `derive_routing`. Real, reproduced: "Do not merge this
   branch into main" incorrectly reaches the CEO-reserved `merge_major_architecture_
   rewrite` action; "Please do not delete anything" incorrectly reaches `delete_
   important_production_or_company_data`; "Do not touch any password" incorrectly reaches
   the credential screen. **This fails safe** — every case *blocks* work with a spurious
   `DECISION_REQUIRED`, never silently permits a reserved action. Not fixed this pass
   (out of the coverage-fix's authorized scope); recorded for a future, separately-scoped
   pass.
2. **Two pre-existing single-word triggers, "authentication" and "migration", cannot
   distinguish a reference from the action** — "the authentication fixture" and "migration
   test coverage" both escalate today, exactly as they did before either hardening pass.
   Narrowing or removing an already-in-production single-word trigger (the same move that
   fixed a bare "governance") is a bigger, riskier change than adding a bounded phrase, so
   it was disclosed and pinned rather than forced.
3. **"deploy"/"deployment" still has no policy hook anywhere** (confirmed again this
   pass) — not a matching defect, a policy gap: no existing specialist domain or
   CEO-reserved action cleanly means "deploy a software service" in this repository's
   declared policy. Inventing one is explicitly out of scope for a vocabulary-coverage
   pass.

## 2. Updated 14-area matrix

Only items 1 and 14 change from v1; the other twelve keep their v1 verdict and evidence
(Dogfood #2, Job A, the correction, Job B, Job C's pre-flight stop — unchanged).

| # | Control area | v1 | v2 | Why it changed |
|---|---|---|---|---|
| 1 | Deterministic intake/routing (capsule ownership, path scope, **and reserved-action/credential screening**) | PASS | **PARTIAL** | New finding: `screen_reserved`/`screen_credentials` share the negation-blind substring pattern the negation-fix pass fixed elsewhere. Fails safe, not open — a real defect, not yet fixed. |
| 2 | Bounded write authority | PASS | PASS | unchanged |
| 3 | Resource-profile enforcement | PASS | PASS | unchanged |
| 4 | One-attempt enforcement | PASS | PASS | unchanged |
| 5 | Receipt validation/prevalidation | PASS | PASS | unchanged |
| 6 | Reviewer independence | PASS | PASS | unchanged |
| 7 | Worst-verdict-wins adjudication | PASS | PASS | unchanged |
| 8 | Deterministic QA | PASS | PASS | unchanged |
| 9 | Integration-gate enforcement | PASS | PASS | unchanged |
| 10 | CEO approval stop | PASS | PASS | unchanged |
| 11 | Reliable external-runner telemetry | PASS | PASS | unchanged |
| 12 | Automatic-continuation prevention | PASS | PASS | unchanged |
| 13 | Failure/refusal handling | PASS | PASS | unchanged |
| 14 | Specialist-classifier correctness | PARTIAL | **PARTIAL (narrower, better-characterized)** | False-positive (negation): fixed and verified. False-negative: three domains closed (architecture/governance/concurrency vocabulary); two residuals remain and are now precisely named rather than generally suspected — (a) "deploy"/"deployment" policy gap, (b) pre-existing bare-word reference/action ambiguity on "authentication"/"migration". |

**12 of 14 PASS. Two PARTIAL — one improved in precision (14), one newly discovered (1).**

## 3. Recommendation

**`NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`** — unchanged from v1, and for the same
reason stated there: containment is not in question (12 of 14 areas pass on strong,
cumulative real evidence across four real jobs), but a live, real defect remains in
deterministic routing, and this pass's own root-cause work found a *second* instance of
that class (item 1) while closing part of the first (item 14). Per the CEO's own
instruction for exactly this outcome: this is recorded, and no further hardening pass is
started automatically.

**Two candidate future passes, neither authorized nor undertaken here:**
- Apply the already-proven `_clauses`/`_escalates` negation-scope fix to
  `screen_reserved`/`screen_credentials` (item 1). Low apparent risk (reuses tested code,
  changes no policy semantics), but scope, tests, and regression evidence would need their
  own pass, per this program's own discipline of never bundling an unrequested fix into a
  differently-scoped one.
- A policy decision (not a vocabulary fix) on whether/how "deploy a software service"
  should be governed at all — as a specialist domain, a new CEO-reserved action, both, or
  deliberately neither, since this repository currently runs no such service.

## 4. Job C — unchanged

**`DEFERRED_DESIGN_GAP`**, exactly as recorded in
[`docs/company_os_supervised_burnin_b_and_c.md`](company_os_supervised_burnin_b_and_c.md)
and reaffirmed in v1. No identifier invented, no telemetry schema touched, nothing to
update.

## 5. Evidence paths

- `docs/company_os_autonomy_readiness_review_v2.md` (this file)
- `docs/company_os_autonomy_readiness_review.md` (v1, superseded but not deleted)
- `docs/company_os_intake_classifier_coverage_hardening.md`, `company/engineering/
  intake.py`, `tests/test_company_engineering_execution.py` on
  `company-os-v1-intake-classifier-coverage-fix` @ `eadd066` (fix `12f7cf8`, pushed, not
  merged)
- `docs/company_os_intake_classifier_hardening.md` on
  `company-os-v1-intake-classifier-negation-fix` @ `da4f3ce` (part 1, unchanged)

## 6. Confirmations

- `main` (`8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f`) and `company-os-v1-bootstrap`
  (`b84f8a75a2d4aaeefd88798f23bc5948e7d39195`) unchanged throughout this pass (checked via
  `git ls-remote origin` immediately before this document's commit; identical to the
  values recorded at the start of the negation-fix pass and every check since).
- No real dogfood/engineering-execution job was started this pass. Both the negation fix
  and the coverage fix were implemented directly, not run as `company/engineering` +
  `tools/engineering_runner` work orders.
- No orchestration subagents (`Agent`/`Task`/child/parallel workers) were used. No
  developer or reviewer model session ran either — this pass, like the negation-fix pass
  before it, involved no separate model process at all.
- Autonomous engineering remains disabled. Nothing here enables it or is intended to.
