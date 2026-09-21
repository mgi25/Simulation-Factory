# Token Efficiency V4 P3C — Matched benchmark protocol

Date: 2026-09-21

## Purpose

Measure whether P3C's deterministic failure-guided semantic context reduces provider rediscovery versus the accepted P2 correction while restoring the same quality floor that P3B missed.

## Experimental control

This is a fresh work order. The failed P3B work order is not reused.

Do not leak the known P3B missing assertion into the new request. The P3C task keeps the same objective, acceptance criteria, task base, writable scope, resource profile and one-attempt ceiling used for the matched P3 benchmark.

Only benchmark identity, branch and validated runner source change.

## P2 comparison baseline

P2 correction developer:

- provider sessions: 1
- turns: 25
- cache read: 756,397
- cache creation: 39,802
- output: 13,056
- provider cost: USD 0.953491
- file reads: 11
- repeated file reads: 10
- searches: 7
- provider duration: 217.635 s
- Bash: 0
- model-run tests: 0
- git commands: 0
- MCP: 0

P2 quality result:

- one-file correction;
- six exact tuple expectations corrected;
- 207 engineering-execution tests passed;
- independent and deterministic review passed;
- canonical gate READY with zero blockers.

## P3B diagnostic result

P3B developer improved efficiency but failed quality:

- developer sessions: 1
- turns: 11
- cache read: 209,695
- cache creation: 24,701
- output: 4,671
- provider cost: USD 0.37606375
- file reads: 4
- repeated reads: 3
- searches: 0
- provider duration: 81.388 s

Its compiled first failing function was clipped before the second stale assertion, so the required suite ended at 206 passed / 1 failed.

P3B therefore remains a failed quality benchmark, not an accepted efficiency result.

## P3C matched task

Request:

`req-token-efficiency-v4-p3c-benchmark-contract-correction`

Work order:

`wo-token-efficiency-v4-p3c-benchmark-contract-correction`

Authorized branch:

`eng-token-efficiency-v4-p3c-benchmark-contract-correction`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Writable scope exactly:

`tests/test_company_engineering_execution.py`

P3C runner source:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Consumer profile, standard model tier, one developer attempt, no watcher in parallel.

## P3C pre-provider proof

At the immutable task base:

- 202 passed / 5 failed;
- five failing node IDs;
- 5/5 failure-guided targets;
- wrong paths: 0;
- compiled context: 3200 / 3200 chars;
- first failure-guided function exposes both `order.authorized_paths` and `order.required_tests`;
- provider cost for diagnosis: USD 0.

## Primary efficiency comparison

Compare developer session only against P2:

- paid provider sessions;
- turns;
- cache-read units;
- cache-creation units;
- output units;
- provider cost;
- file reads total;
- repeated file reads;
- searches total;
- provider duration.

Also record local pre-provider diagnostic duration separately.

Do not combine reviewer cost with developer efficiency when judging P3C context compilation. Report whole-run cost separately.

## Quality floor

P3C succeeds only if:

1. implementation changes only the authorized test file;
2. the engineering-execution suite passes;
3. the resulting diff covers the same six legitimate exact expectation changes as the accepted P2 correction, without weakening assertions;
4. reviewer attestation passes;
5. deterministic review passes;
6. all 11 canonical Company OS suites pass at the implementation commit;
7. integration gate READY with zero blockers.

If resource use falls but quality fails, P3C is not accepted.

## Interpretation

This remains a one-sample matched replay, not a causal estimate of average savings.

No canonical merge, deployment, publishing or production integration is authorized.
