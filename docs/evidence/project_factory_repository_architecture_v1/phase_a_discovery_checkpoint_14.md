# Phase A Discovery Checkpoint 14 — P2 benchmark V2 deterministic dry run accepted

Date: 2026-09-21

The corrected matched-benchmark request was run through the full Company OS request/open-job path against a fresh disposable state directory using the exact validated P2 implementation commit:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

No model session was launched.

## Result

- intake exit: 0
- outcome: authorized
- state: planning
- resource profile: consumer
- specialist domain: empty
- escalation: none
- authorized branch: `eng-token-efficiency-v4-p2-review-test-ownership-v2`
- base commit: `619b2a0374ab935c1eb21b19517d3eeecc7d0b42`
- work-order fingerprint: `a60db35afdf0ef3b`

Selected capsules:

1. `company-knowledge-capsules`
2. `company-engineering-execution`

Authorized paths, exactly:

1. `knowledge/company_os/capsules/seeds/company-engineering-execution.json`
2. `tests/test_company_os_capsules.py`

Required tests:

1. `tests/test_company_engineering_execution.py`
2. `tests/test_company_os_capsules.py`

The narrower V2 objective removed the contradictory capsule-selection signal seen in the first benchmark request. The planner no longer derives a forbidden `knowledge` prefix that conflicts with the exact capsule seed path.

## Context narrowing observation

Four context references were considered and two were kept:

- kept: `capsule:company-knowledge-capsules`
- kept: `tests/test_company_os_capsules.py`
- dropped: `capsule:company-engineering-execution` because its owned source path is outside this metadata-only authorized scope
- dropped: `tests/test_company_engineering_execution.py` because it is outside the authorized write scope

This is acceptable for the benchmark because the exact target capsule seed file is itself an authorized readable/writable path and the required test remains runner-owned deterministic validation.

## Decision

The V2 benchmark request is safe to open in the real Repository Architecture V1 state directory.

Before any model invocation:

1. confirm the work-order id is unused in the real state;
2. open the real job;
3. inspect status;
4. run engineering-runner doctor using the dedicated benchmark runner/worktree directories;
5. do not start `run-one` until those outputs are inspected.

No canonical merge, deployment, publishing or production integration is authorized.
