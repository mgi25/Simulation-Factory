# Phase A Discovery Checkpoint 16 — P2 matched benchmark result and scope defect

Date: 2026-09-21

## Benchmark execution

Work order:

`wo-token-efficiency-v4-p2-review-test-ownership-v2`

Validated P2 runner base:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

Worker commit:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

The run used exactly one developer provider session and one reviewer provider session. No hidden provider retry occurred.

## Measured developer resources

Historical V2 planning-test ownership developer aggregate:

- provider sessions: 2
- turns: 46
- cache read: 2,111,924
- cache creation: 124,470
- output: 65,525
- provider cost: USD 3.4722695

P2 benchmark developer:

- provider sessions: 1
- turns: 10
- cache read: 156,514
- cache creation: 22,671
- output: 2,960
- provider cost: USD 0.29400075
- duration: 56.633 s
- Bash calls: 0
- test commands inside model: 0
- git commands inside model: 0
- MCP servers: 0
- available tools: Glob, Grep, Read, Edit, Write

Directional reduction versus the historical developer aggregate:

- provider sessions: 50.0%
- turns: 78.3%
- cache read: 92.6%
- cache creation: 81.8%
- output: 95.5%
- provider cost: 91.5%

These are one-sample directional measurements, not a causal estimate.

## Whole paid run

Developer + independent reviewer:

- provider sessions: 2
- turns: 15
- cache read: 203,564
- cache creation: 40,318
- output: 6,790
- provider cost: USD 0.5235945

Reviewer startup tools were Glob, Grep and Read; MCP servers were zero.

## Quality result

The worker changed exactly the two authorized files.

The capsule change was semantically narrow:

- only top-level field changed: `tests`
- added `tests/test_company_review_separation.py`
- capsule size: 3,708 characters, below the 3,800-character criterion

The capsule regression test added exactly the intended assertion.

However, deterministic runner validation correctly rejected the attempt because:

`tests/test_company_engineering_execution.py`

had five failures at the worker commit.

The failures are not an unrelated pre-existing failure. They are direct consequences of the new capsule `tests` entry because engineering intake and execution derive test authority from `capsule.tests`. Existing tests intentionally pin:

- the exact authorized path tuple;
- derived plan writing paths;
- packet scope;
- persisted execution authority `may_write`;
- the exact test tuple of the company-engineering-execution capsule.

Adding a second semantic test therefore requires updating those exact-contract assertions.

## Reviewer finding

The model reviewer returned PASS and described the failing engineering-execution suite as outside acceptance scope / likely pre-existing.

That interpretation was incorrect.

Company OS adjudication correctly took the worst of reviewer and deterministic evidence and returned `changes_required`.

This is evidence that the independent deterministic layer prevented an incorrect model-review PASS from advancing.

## Root cause

The benchmark work order was under-scoped.

It authorized:

1. the capsule seed;
2. the capsule regression test.

It did not authorize:

3. `tests/test_company_engineering_execution.py`

even though that suite is a required test and contains exact assertions whose expected values must change when the capsule's test list changes.

The model could not legally repair the failures because the needed third file was outside its write scope.

## Decision

Do not authorize another attempt on the existing work order. Its authorized scope cannot satisfy its own deterministic suite.

Create a new bounded correction work order from worker commit `287d690b7bf87c988edb3eb34d1f57a4dcec5ab1` that authorizes only:

`tests/test_company_engineering_execution.py`

The correction must update only assertions whose expected values legitimately change because the capsule now names `tests/test_company_review_separation.py`. It must not weaken assertions, widen runtime authority, alter production behavior, or modify the already-correct capsule metadata.

The P2 efficiency result is directionally successful, but P2 is not yet declared a quality-preserving benchmark win until the correction passes deterministic tests, independent review and the full integration gate.

No canonical merge, deployment, publishing or production integration is authorized.
