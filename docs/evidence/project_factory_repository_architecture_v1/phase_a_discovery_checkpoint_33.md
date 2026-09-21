# Phase A Discovery Checkpoint 33 — P3B paid benchmark preflight accepted

Date: 2026-09-21

The real P3B matched benchmark work order has been persisted and verified before any provider session.

## Runner source

`project-factory-token-efficiency-v4-p3`

Exact runner SHA:

`07429215cf171c78ae91a1a7a232047c5bd071da`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Work order

Work order:

`wo-token-efficiency-v4-p3-benchmark-contract-correction`

Fingerprint:

`b2a1147235541e8f`

State:

`planning`

Developer attempts:

`0 / 1 used`

Corrections remaining:

`1`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Authorized branch:

`eng-token-efficiency-v4-p3-benchmark-contract-correction`

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

## Collision / state checks

Local benchmark branch: absent.

Remote benchmark branch: absent.

Benchmark runner root: absent.

Benchmark worktree root: absent.

The paid run therefore begins from a clean, unused benchmark state.

## Prior free proof

P3B already demonstrated at the immutable task base:

- base suite: 202 passed, 5 failed;
- all 5 failing node IDs extracted deterministically;
- all 5 exact test symbols precompiled;
- 5/5 failure-guided priority;
- wrong paths: 0;
- compiled context: 2990 / 3200 characters;
- provider cost for diagnosis: USD 0.

## Decision

Exactly one real `run-one` invocation is now authorized for the matched P3B benchmark.

Do not run a watcher in parallel.

After the run, do not invoke `run-one` again until the resulting state, provider sessions, compiled-context evidence, deterministic tests, review and usage telemetry have been inspected.

No canonical merge, deployment, publishing or production integration is authorized.
