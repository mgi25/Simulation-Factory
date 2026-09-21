# Phase A Discovery Checkpoint 35 — P3B efficiency measured; P3C correction selected

Date: 2026-09-21

The first paid P3B matched benchmark did not meet the quality floor, but it produced useful efficiency evidence and a narrow deterministic root cause.

## P3B implementation result

Runner source:

`07429215cf171c78ae91a1a7a232047c5bd071da`

Implementation commit:

`be771009bff7c25e37b562ed64e13e79218e6018`

Changed path:

`tests/test_company_engineering_execution.py` only.

Post-implementation required suite:

- 206 passed
- 1 failed
- failing assertion: `order.required_tests` in `test_a_ceo_objective_produces_a_bounded_work_order`

The accepted P2 correction commit `615dfea4ddadc56bedc108d91aae1663448f9f94` changed six exact tuple assertions. P3B changed five. The missing sixth assertion is inside the same first failure-guided function.

## P3B developer efficiency

P2 correction developer baseline:

- sessions: 1
- turns: 25
- cache read: 756,397
- cache creation: 39,802
- output: 13,056
- provider cost: USD 0.953491
- file reads: 11
- repeated reads: 10
- searches: 7
- provider duration: 217.635 s

P3B developer:

- sessions: 1
- turns: 11
- cache read: 209,695
- cache creation: 24,701
- output: 4,671
- provider cost: USD 0.37606375
- file reads: 4
- repeated reads: 3
- searches: 0
- provider duration: 81.388 s
- local pre-provider diagnostic: 24.138 s

Directional reductions before quality acceptance:

- turns: 56.0% lower
- provider cost: 60.6% lower
- cache read: 72.3% lower
- cache creation: 37.9% lower
- output: 64.2% lower
- file reads: 63.6% lower
- repeated reads: 70.0% lower
- searches: 100% lower
- provider duration: 62.6% lower
- provider + local diagnostic duration: 51.5% lower than the P2 provider duration

These are efficiency signals only; P3B is not accepted as quality-preserving because the required suite failed.

## Root cause confirmed

P3B correctly extracted five base failing node IDs and selected all five exact AST test symbols.

The first compiled failure-guided span was clipped at 600 characters and ended before the stale `order.required_tests` assertion.

Therefore:

- failure-guided symbol selection worked;
- the generic excerpt cap hid a second relevant assertion later in the same function;
- pytest emitted one failing node id for that function because execution stopped at its first stale assertion.

## Reviewer cost observation

The reviewer stage used two successful provider sessions:

- session 1: 24 turns, USD 0.74001975
- session 2: 10 turns, USD 0.25606025

Reviewer aggregate:

- 34 turns
- USD 0.99608

The runner only launches the second successful session in the bounded structured-report repair path, so this is a separate reviewer/report-efficiency issue and must not be conflated with P3C developer-context work.

Whole P3B run:

- provider sessions: 3
- total turns: 45
- total provider cost: USD 1.37214375
- cache read: 844,640
- cache creation: 76,511
- output: 18,856

The whole run is not an efficiency win because quality failed and reviewer repair dominated cost.

## P3C decision

P3C keeps the same global context budgets and authority boundaries.

For deterministic failure-guided symbols:

1. resolve all eligible failing AST symbols first;
2. if their complete bodies collectively fit the existing 3,200-character compiled-context budget, include those bodies in full;
3. otherwise divide the remaining budget deterministically across the unresolved failing symbols;
4. only after failure-guided spans are allocated may semantic ranking fill spare slots;
5. do not widen authority or add provider/model work.

Semantic compiler evidence version advances to 3.

No additional paid benchmark is authorized until P3C passes focused tests, the matched-base free preview proves the complete first function includes `order.required_tests`, and the full 11-suite gate is green.

No canonical merge, deployment, publishing or production integration is authorized.
