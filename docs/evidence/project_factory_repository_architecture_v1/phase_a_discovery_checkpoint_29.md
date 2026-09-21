# Phase A Discovery Checkpoint 29 — P3A preview rejected; P3B failure-guided context selected

Date: 2026-09-21

The first free matched-benchmark context preview intentionally stopped before any provider spend.

## Preview result

Validated P3A compiler source:

`0be53a49b0f97a9c96fbe78bf1de018637c4621a`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Compiled spans:

- count: 6
- compiled characters: 2458 / 3200
- expected target functions found: 2 / 5
- unexpected path selections: 0
- preview exit: 2

Found target functions:

- `test_a_ceo_objective_produces_a_bounded_work_order`
- `test_authorized_paths_are_enforced_on_the_packet_scope`

Missed target functions:

- `test_the_derived_plan_names_the_stages_the_brief_asks_for`
- `test_the_execution_history_is_append_only_and_provenanced`
- `test_the_engineering_package_is_owned_by_exactly_one_capsule`

Four of six slots were consumed by generic governance/context matches.

## Interpretation

P3A's global token-overlap ranker is too shallow for a correction whose exact failing assertions are distributed across a large test file. Tuning stop words or weights against this benchmark would risk overfitting.

## P3B design decision

For a developer stage with required deterministic tests:

1. before launching the provider, run the required test suite(s) once at the immutable task base checkout;
2. persist the base-test diagnostic evidence;
3. deterministically parse failing pytest node IDs;
4. map those node IDs to AST test symbols;
5. prioritize those exact symbols in the compiled context;
6. then fill any remaining context slots with P3A semantic ranking;
7. preserve the same hard context budget and authority/path filters;
8. keep Read available as fallback;
9. still rerun every required test after implementation at the implementation commit.

If the base suite is green or cannot provide node IDs, fall back to P3A/P2 behavior. A diagnostic failure does not widen authority and does not itself block the work order.

## Why this is preferable

This moves repair diagnosis into deterministic local computation rather than paid semantic rediscovery. It should improve both provider efficiency and repair accuracy while preserving or strengthening the quality floor.

The added local test runtime must be measured alongside provider savings.

No provider benchmark, canonical merge, deployment, publishing or production integration is authorized until P3B is statically validated and the free preview covers the target failures.
