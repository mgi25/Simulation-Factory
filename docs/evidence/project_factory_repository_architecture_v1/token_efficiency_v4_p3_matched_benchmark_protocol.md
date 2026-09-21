# Token Efficiency V4 P3 — Matched benchmark protocol

Date: 2026-09-21

## Purpose

Measure whether P3's deterministic multi-span read-once context compiler reduces semantic rediscovery compared with the previously observed P2 high-read correction session, while preserving the same quality floor.

## Comparison baseline

P2 correction work order:

`wo-token-efficiency-v4-p2-benchmark-contract-correction`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

P2 correction developer telemetry:

- provider sessions: 1
- turns: 25
- cache read: 756,397
- cache creation: 39,802
- output: 13,056
- provider cost: USD 0.953491
- file reads: 11
- repeated reads: 10
- searches: 7
- Bash: 0
- model-run tests: 0
- git commands: 0
- MCP: 0

The P2 implementation reached a one-file correction commit, passed 207 engineering-execution tests, passed independent and deterministic review, and reached integration READY with zero blockers.

## P3 matched task

Use the same objective and same task base commit.

Writable scope, exactly:

`tests/test_company_engineering_execution.py`

One developer attempt.

P3 runner source:

`0be53a49b0f97a9c96fbe78bf1de018637c4621a`

Consumer profile, standard model tier.

No watcher in parallel.

## Primary efficiency metrics

Compare developer session only:

- paid provider session count;
- turns;
- cache-read units;
- cache-creation units;
- output units;
- provider cost;
- file reads total;
- repeated file reads;
- searches total.

Also record compiled-context evidence:

- compiler version;
- context fingerprint;
- compiled span count;
- rendered chars;
- truncation flag;
- selected span paths/symbols.

## Quality floor

P3 is not accepted from efficiency alone.

Required:

1. implementation changes only the authorized test file;
2. engineering-execution suite passes;
3. exact assertions remain exact;
4. reviewer attestation passes;
5. deterministic review passes;
6. all 11 canonical Company OS suites pass at the P3 benchmark implementation;
7. integration gate READY with zero blockers.

If P3 uses fewer resources but fails quality, the benchmark is not a success.

## Interpretation

This is a one-sample matched replay, not a causal estimate of average savings.

The strongest useful evidence would be:

- fewer repeated reads;
- fewer searches;
- materially lower cache-read units and/or turns;
- same or lower provider cost;
- unchanged quality outcome.

Do not count unrelated dependency-repair work in this comparison.

No canonical merge, deployment, publishing or production integration is authorized.
