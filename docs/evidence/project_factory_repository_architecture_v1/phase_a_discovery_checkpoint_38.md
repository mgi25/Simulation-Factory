# Phase A Discovery Checkpoint 38 — P3C focused validation accepted

Date: 2026-09-21

Token Efficiency V4 P3C has passed focused static validation after both deterministic corrections.

## Exact source state

Branch:

`project-factory-token-efficiency-v4-p3`

Validated SHA:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Targeted regression validation

Dependency guard:

- 1 passed
- exit 0

Bytecode-cache isolation regression:

- 1 passed
- exit 0

The bytecode regression proves a failing same-size source edit is no longer masked by stale bytecode after the base diagnostic.

## Full focused validation

Suites:

- `tests/test_engineering_runner_execution_context.py`
- `tests/test_external_engineering_runner.py`
- `tests/test_company_external_engineering_runner.py`

Result:

- 239 passed
- exit 0
- duration 180.44 s

## P3C behavior under validation

P3C keeps P3B's failure-guided selection and changes only the deterministic representation of selected failing symbols:

1. resolve eligible failing AST symbols first;
2. if their complete bodies collectively fit the existing 3,200-character compiled-context budget, preserve them in full;
3. otherwise share the remaining budget deterministically across unresolved failing symbols;
4. only then use semantic ranking to fill spare slots.

The semantic compiler evidence version is 3.

Deterministic pytest invocations also use a fresh temporary `PYTHONPYCACHEPREFIX` outside the worktree to prevent cross-run bytecode contamination.

No provider/model session was used for this validation.

## Decision

P3C is eligible for a zero-provider matched-base preview against:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

The preview must prove:

- all 5 base failing node IDs are still discovered;
- all 5 are still failure-guided;
- the first compiled function contains both `order.authorized_paths` and `order.required_tests`;
- no wrong path is selected;
- compiled context remains within the existing 3,200-character budget.

Do not run the 11 canonical suites, integration gate, or any paid benchmark until that preview passes.

No canonical merge, deployment, publishing or production integration is authorized.
