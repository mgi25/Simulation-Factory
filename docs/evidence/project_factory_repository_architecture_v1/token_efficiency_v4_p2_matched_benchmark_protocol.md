# Token Efficiency V4 P2 matched engineering benchmark

Date: 2026-09-21

## Purpose

Measure whether P0-P2 materially reduce provider resources on a real bounded Company OS job without weakening the quality chain.

This benchmark intentionally mirrors the historical two-file capsule metadata plus capsule regression-test shape that produced the expensive planning-test ownership run, while making a distinct useful change.

## Work order

Request:

`req-token-efficiency-v4-p2-review-test-ownership`

Planned work order:

`wo-token-efficiency-v4-p2-review-test-ownership`

Authorized worker branch:

`eng-token-efficiency-v4-p2-review-test-ownership`

Base:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

Authorized paths:

1. `knowledge/company_os/capsules/seeds/company-engineering-execution.json`
2. `tests/test_company_os_capsules.py`

The intended change is one new semantic-test reference plus one regression assertion. No runtime code is authorized.

## Historical developer comparison

The historical V2 planning-test ownership developer stage ultimately used two provider sessions:

- session 1: 38 turns, USD 3.033953, 1,917,651 cache read, 85,218 cache creation, 61,693 output;
- session 2: 8 turns, USD 0.4383165, 194,273 cache read, 39,252 cache creation, 3,832 output.

Aggregate developer baseline:

- provider sessions: 2
- turns: 46 where reported by the preserved result envelopes
- provider cost: USD 3.4722695
- cache read: 2,111,924
- cache creation: 124,470
- output: 65,525

The tasks are comparable in shape, not byte-identical. Do not claim a causal percentage from one sample.

## P2 expectations to verify, not assume

Developer session:

- one provider session unless a real structured-report repair is necessary;
- startup tools exactly Read, Write, Edit, Glob, Grep;
- MCP servers zero;
- Bash absent;
- TodoWrite absent;
- ToolSearch absent;
- no test command executed inside the model session;
- no git commit/push executed by the model;
- runner-owned required tests execute after the implementation commit.

Reviewer remains independent and read-only.

## Required quality evidence

The benchmark is valid only if all of the following hold:

1. scope contains exactly the two authorized paths;
2. capsule prose/semantic fields other than `tests` remain unchanged;
3. capsule canonical size is <= 3800 characters;
4. `tests/test_company_os_capsules.py` passes through the work order's deterministic runner validation;
5. after the job, `tests/test_company_review_separation.py` passes independently;
6. independent reviewer does not report a changes-required or blocking finding;
7. all 11 required suites pass;
8. integration gate is READY with zero blockers;
9. no canonical merge, deployment, publishing or production integration occurs.

A resource reduction with failed quality is not an efficiency win.

## Measurements

Enumerate every `session-N.json`; never use only the mutable `session.json` alias.

Per session:

- role;
- stop reason;
- model;
- turns;
- provider cost;
- input;
- cache read;
- cache creation;
- output;
- startup tools;
- MCP servers;
- plugins;
- skills;
- exploration tool calls, reads and searches.

Per stage/job:

- paid session count;
- aggregate provider resources;
- runner-owned test results;
- reviewer verdict/findings;
- gate readiness.

When observable, record the Claude Team-plan percentage before and after as contextual evidence only; do not translate it into API-equivalent dollars.

## Contamination controls

Before opening the work order:

- no other `tools.engineering_runner watch` process may be running against the same Company OS state;
- use a dedicated runner-state directory and dedicated runner worktree root;
- execute the runner from the exact P2 implementation worktree;
- do not run a second benchmark automatically after a stop.

## Decision rule

One clean run is sufficient to establish direction when quality is fully green and the reduction is large. Repeat once only if the result is ambiguous.

No benchmark result authorizes merge to main.
