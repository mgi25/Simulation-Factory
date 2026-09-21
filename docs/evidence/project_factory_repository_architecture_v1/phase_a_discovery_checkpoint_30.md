# Phase A Discovery Checkpoint 30 — P3B focused validation accepted

Date: 2026-09-21

Token Efficiency V4 P3B passed focused static validation.

## Exact source state

Branch:

`project-factory-token-efficiency-v4-p3`

Validated SHA:

`f58c2c8a34a0827a6cc304d298b61e29fd0765d3`

Validated P2 base:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

Remote verification:

- branch head matches the validated SHA;
- branch is 16 commits ahead of P2 base, 0 behind;
- the diff remains confined to the same five runner/context/test files.

## Focused validation

Compile result: PASS.

Focused suites:

- `tests/test_engineering_runner_execution_context.py`
- `tests/test_external_engineering_runner.py`
- `tests/test_company_external_engineering_runner.py`

Result:

- 236 passed
- exit 0
- duration 105.05 s

No provider/model session was used.

## P3B behavior under test

P3B extends P3A with bounded failure-guided context:

- a fresh developer stage may run at most 2 required deterministic suites before provider launch;
- each pre-provider diagnostic is capped at 180 seconds;
- failing pytest node IDs are parsed deterministically;
- parsed failures are mapped to exact AST symbols;
- those symbols receive first priority in the compiled context budget;
- only already-eligible context paths can be selected;
- failure hints cannot widen write authority;
- if no useful failure hint exists, P3A/P2 fallback behavior remains;
- required tests still run after implementation at the implementation commit.

Compiler evidence version is 2.

## Decision

P3B is eligible for another zero-provider matched-benchmark context preview against task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

The preview must:

1. run `tests/test_company_engineering_execution.py` at the immutable task base;
2. observe the expected base failures;
3. extract the failing node IDs;
4. compile their exact test symbols first;
5. prove all five benchmark target functions are present;
6. remain within the hard 6-span / 3200-character context budget.

Do not run a paid benchmark until that preview passes and P3B subsequently passes the 11 canonical suites plus integration gate.

No canonical merge, deployment, publishing or production integration is authorized.
