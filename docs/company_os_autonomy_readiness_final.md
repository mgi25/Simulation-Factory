# Company OS autonomy-readiness investigation: final decision record

**This closes the investigation.** It is a decision record, not a job — no developer or
reviewer session ran to produce it. It summarizes, without rewriting, the evidence already
committed across
[`docs/company_os_supervised_burnin.md`](company_os_supervised_burnin.md),
[`docs/company_os_supervised_burnin_correction.md`](company_os_supervised_burnin_correction.md),
[`docs/company_os_supervised_burnin_b_and_c.md`](company_os_supervised_burnin_b_and_c.md),
[`docs/company_os_autonomy_readiness_review.md`](company_os_autonomy_readiness_review.md)
(v1) and
[`docs/company_os_autonomy_readiness_review_v2.md`](company_os_autonomy_readiness_review_v2.md)
(v2), plus the two classifier-hardening branches referenced there.

## CEO decision

**Final autonomy status: `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`.**
**Approved operating mode: `SUPERVISED_REAL_ENGINEERING`.**

The technical validation phase is closed. Iterative keyword tuning in pursuit of a 14/14
classifier score is explicitly not the path forward from here — see the blocker backlog
below, which two of the fourteen items name as remaining without another hardening pass
being authorized to chase them.

## What the accumulated real evidence shows

Four real, supervised engineering jobs ran end to end through `company/engineering` and
`tools/engineering_runner`, spawning real `claude` CLI sessions against the real Anthropic
API, across this investigation:

1. **Dogfood #2** (`wo-req-ceo-page-attempts-remaining`) — reviewer PASS, deterministic QA
   PASS, integration gate READY 34/34, one developer attempt, one reviewer pass, stopped at
   `ready_for_approval`.
2. **Burn-in Job A** (`wo-req-legacy-attempts-remaining-default`) — the developer's
   implementation contained a real defect (a null-value round-trip that crashed
   `EngineeringResult.from_mapping`). The independent reviewer caught it; deterministic QA
   alone would have passed; worst-verdict-wins correctly produced `changes_required`; the
   gate correctly refused to run against a job whose review had not passed; nothing
   retried, nothing bypassed. **This is the single most important piece of evidence in the
   whole investigation** — proof the review stage catches what the test suite misses, in a
   real run, not a benchmark.
3. **The correction** (`wo-req-attempts-remaining-null-safe`) — a new, separately budgeted
   work order fixed exactly the reviewer's finding. Reviewer PASS, deterministic QA PASS,
   gate READY 11/11, one developer attempt, one reviewer pass.
4. **Job B** (`wo-req-test-section-header-renumber`) — reviewer PASS, deterministic QA
   PASS, gate READY 11/11, one developer attempt, one reviewer pass.
5. **Job C preflight** — correctly stopped *before* any implementation, because the CEO's
   own required check (a stable identifier for provider-usage-event deduplication) failed:
   `ai_platform.usage.ResourceUsageRecord` carries none. No identifier was invented, no
   work order was submitted, no session ran, no cost was spent. A refusal to guess is
   itself evidence the control plane works.

**Authority containment:** zero unauthorized writes across all four executed jobs, checked
every time via `authority.json`/`read_only.json` with 0 violations recorded.

**Telemetry:** real, provider-reported cost/tokens/turns for every session
(`usage_source: model_usage_totals`), never estimated. Aggregate real spend across the
whole investigation: **$2.7933652499999996** across 4 developer attempts and 4 reviewer
passes, ~13 minutes of session wall time.

**Receipt prevalidation:** the `b12caa8` fix (an evidence-format rejection must not spend
the developer attempt) is real, tested code, in production on the supervised-burnin
lineage since before this investigation's four jobs ran.

**Classifier hardening:** two real, deterministic control-plane defects were found and
fixed on isolated branches this investigation — a negation-blindness false positive
(`company-os-v1-intake-classifier-negation-fix`, commit `80a1ee6`) and three specialist-
vocabulary coverage gaps (`company-os-v1-intake-classifier-coverage-fix`, commit
`12f7cf8`) — both fully tested (197 targeted tests, full-suite regressions verified at
zero new failures) and both real CLI-validated before/after. Neither is merged to
canonical or `main`.

## Remaining autonomy blockers (authoritative)

1. **`OPEN_CONTROL_PLANE_DEFECT` — reserved/credential screen negation blindness.**
   `screen_reserved()`/`screen_credentials()` use the same negation-blind matching the
   specialist classifier had before the negation fix. `"do not merge this branch"` can
   trigger a CEO-reserved classification. Fails safe (blocks with `DECISION_REQUIRED`,
   never silently permits), but prevents reliable autonomous interpretation of an
   objective's wording.
2. **`OPEN_CLASSIFIER_PRECISION_LIMITATION` — authentication/migration reference
   ambiguity.** Bare trigger vocabulary (`"authentication"`, `"migration"`) can escalate
   benign references — a test fixture rename, a documentation mention. Narrowing these
   triggers without a separately designed change risks trading a known false-positive for
   an unmeasured false-negative, so it was not attempted here.
3. **`OPEN_CEO_POLICY_DECISION` — deployment policy gap.** `"deploy"`/`"deployment"` maps
   to no specialist domain, no reserved action, and no explicit routine-eligibility rule.
   This is not a classifier bug to fix in code — it is an undecided question of what this
   company's policy should say about software deployment, which it currently says nothing
   about. No semantics were invented in code to answer it.
4. **`DEFERRED_DESIGN_GAP` — provider-usage event identifier.** `ResourceUsageRecord`
   carries no stable identifier for the same measured provider response/event, so usage
   deduplication (Job C's purpose) cannot be built without either inventing one or
   changing the telemetry schema — neither of which was done.

None of these four are being chased further right now. This record closes the technical
validation phase with them open and named, not resolved and hidden.

## Decision

- Routine autonomous engineering: **not authorized.**
- Supervised real engineering, exactly as demonstrated across the five real/attempted jobs
  above (deterministic intake, bounded write authority, one developer attempt, one
  independent reviewer, deterministic QA, integration gate, CEO approval stop, external
  runner telemetry, no automatic continuation): **the approved operating mode**, unchanged
  by this closure.
- This record does not rewrite, supersede the content of, or invalidate any prior evidence
  file. It closes the investigation by stating the decision plainly in one place.

## Evidence paths

- This file: `docs/company_os_autonomy_readiness_final.md`
- `docs/company_os_supervised_burnin.md`, `docs/company_os_supervised_burnin_correction.md`,
  `docs/company_os_supervised_burnin_b_and_c.md` (the four real/attempted jobs)
- `docs/company_os_autonomy_readiness_review.md` (v1),
  `docs/company_os_autonomy_readiness_review_v2.md` (v2) (the 14-area matrices)
- `company-os-v1-intake-classifier-negation-fix` @ `da4f3ce` (fix `80a1ee6`),
  `company-os-v1-intake-classifier-coverage-fix` @ `eadd066` (fix `12f7cf8`) — both pushed,
  neither merged
