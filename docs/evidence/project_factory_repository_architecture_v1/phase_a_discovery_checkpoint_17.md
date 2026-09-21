# Phase A Discovery Checkpoint 17 — P2 benchmark correction dry run accepted

Date: 2026-09-21

The bounded correction request for the P2 matched benchmark was run through the full deterministic Company OS request/open-job path against a fresh disposable state directory. No model session was launched.

## Correction target

Base commit:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Work order:

`wo-token-efficiency-v4-p2-benchmark-contract-correction`

Authorized branch:

`eng-token-efficiency-v4-p2-benchmark-contract-correction`

Authorized path, exactly:

`tests/test_company_engineering_execution.py`

## Dry-run result

- outcome: authorized
- state: planning
- selected capsule: `company-engineering-execution`
- required tests: `tests/test_company_engineering_execution.py`
- resource profile: consumer
- specialist domain: empty
- escalation: none
- work-order fingerprint: `396b138eac4f4dde`

The request therefore has the minimum writable authority needed to repair the five exact-contract assertions revealed by the first P2 benchmark attempt.

## Guardrails

The correction request requires:

- only the one engineering-execution test file may change;
- exact tuple assertions remain exact;
- no containment/subset weakening;
- capsule metadata remains untouched;
- runtime behavior remains untouched;
- no dependency or governance change;
- deterministic test execution remains runner-owned under P2.

## Decision

The correction request is safe to open in the real Repository Architecture V1 state directory.

Before invoking a model:

1. confirm the correction work-order id is unused in real state;
2. open the real correction job;
3. inspect persisted status/fingerprint/scope;
4. run engineering-runner doctor with a fresh dedicated correction runner/worktree root;
5. do not run `run-one` until those outputs are inspected.

No canonical merge, deployment, publishing or production integration is authorized.
