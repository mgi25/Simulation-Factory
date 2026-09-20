# Phase A Discovery Checkpoint 04 — Non-atomic CEO decision recording

Date: 2026-09-21

## Finding

A CEO decision was submitted against
`wo-candidate-lifecycle-runtime-history` while the engineering job was still in
`planning`. The decision used verdict `reject`, which implies a transition to
`closed`.

The lifecycle correctly refused `planning -> closed`.

However, `company.engineering.orchestrator.record_decision` appends the
`CEODecision` before calling `decision.apply_to(job)`. Therefore an invalid
lifecycle application can leave a persisted CEO decision even though the job
snapshot does not advance.

## Impact

This is an audit-consistency defect. The append-only store can contain a decision
that was recorded but not successfully applied to the job state. Nothing was
merged, deployed, published, or executed, and no model session was started.

## Immediate recovery

Do not delete or rewrite the persisted record. Preserve it as evidence and append
a valid `planning -> blocked` job snapshot explaining that the immutable work
order is under-scoped and cannot satisfy its own acceptance criteria.

## Follow-up requirement

A later bounded fix should make decision recording atomic from the caller's
perspective: validate/apply the lifecycle move before appending the decision, or
otherwise persist an explicit failed-application record so decision history and
job history cannot appear inconsistent.

This checkpoint authorizes no runtime change by itself.
