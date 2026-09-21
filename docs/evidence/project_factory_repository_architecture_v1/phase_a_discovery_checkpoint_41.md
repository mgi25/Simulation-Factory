# Phase A Discovery Checkpoint 41 — P3C paid benchmark preflight accepted

Date: 2026-09-21

The fresh P3C matched benchmark work order has been persisted and verified before any provider session.

## Exact source state

P3C runner branch:

`project-factory-token-efficiency-v4-p3`

Validated runner SHA:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Fresh P3C work order

Work order:

`wo-token-efficiency-v4-p3c-benchmark-contract-correction`

Fingerprint:

`237e2a9d7a69c0dd`

State:

`planning`

Developer attempts:

`0 / 1 used`

Corrections remaining:

`1`

Plan fingerprint:

`ead9dbc81635867c`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Authorized branch:

`eng-token-efficiency-v4-p3c-benchmark-contract-correction`

Authorized writable path, exactly:

`tests/test_company_engineering_execution.py`

Required deterministic test:

`tests/test_company_engineering_execution.py`

Resource profile:

`consumer`

Specialist domain:

empty

Escalation:

`none`

## Collision / storage checks

Local benchmark branch: absent.

Remote benchmark branch: absent.

Benchmark runner root: absent.

Benchmark worktree root: absent.

The paid run therefore begins from a clean, unused benchmark state.

## Experimental-control note

The fresh P3C request preserves the same matched task objective, acceptance criteria, immutable task base, writable scope and one-attempt ceiling. It does not disclose the known P3B-missed `order.required_tests` assertion.

## Decision

Exactly one real `run-one` invocation is now authorized for the P3C matched benchmark.

Do not run a watcher in parallel.

Do not invoke `run-one` again after this invocation until the resulting lifecycle state, provider-session telemetry, compiled-context evidence, deterministic tests, review verdict and gate evidence have been inspected.

No canonical merge, deployment, publishing or production integration is authorized.
