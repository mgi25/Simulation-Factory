# Phase A Discovery Checkpoint 21 — review-separation YAML dependency real-job preflight

Date: 2026-09-21

The bounded repair for the pre-existing undeclared PyYAML test dependency is opened in the real Repository Architecture V1 Company OS state.

## Persisted job

- work order: `wo-token-efficiency-v4-review-separation-yaml-dependency`
- state: `planning`
- developer attempts: 0
- work-order fingerprint: `cf8dfd25fb689055`
- plan fingerprint: `7d0261d7a005e599`
- authorized branch: `eng-token-efficiency-v4-review-separation-yaml-dependency`
- base commit: `615dfea4ddadc56bedc108d91aae1663448f9f94`
- resource profile: `consumer`
- specialist domain: empty
- escalation: none
- writable path, exactly: `tests/test_company_review_separation.py`

Required tests:

1. `tests/test_company_engineering_execution.py`
2. `tests/test_company_review_separation.py`

## Runner doctor

Doctor exit: 0.

Repository observed by runner:

- detached HEAD: `615dfea4ddadc56bedc108d91aae1663448f9f94`
- backend: Claude Code 2.1.70
- standard model alias: sonnet
- resource strategy enabled
- push enabled

Dedicated runner state:

`project-factory-runner-state/review-separation-yaml-dependency`

Dedicated worktree root:

`project-factory-benchmark-worktrees/review-separation-yaml-dependency`

## Accounting rule

This job repairs pre-existing test dependency debt exposed by extended validation. Its provider usage is tracked separately and must not be folded into the P2 matched benchmark efficiency comparison.

## Decision

The job is eligible for exactly one `run-one`.

Do not start a watcher in parallel. Do not automatically invoke a second run if the job stops. Preserve numbered provider-session evidence before any follow-up.

No canonical merge, deployment, publishing or production integration is authorized.
