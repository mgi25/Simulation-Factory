# Phase A Discovery Checkpoint 39 — P3C matched-base preview accepted

Date: 2026-09-21

Token Efficiency V4 P3C has passed the zero-provider matched-base preview.

## Exact source state

P3 branch:

`project-factory-token-efficiency-v4-p3`

Validated SHA:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Matched-base diagnostic

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Required suite:

`tests/test_company_engineering_execution.py`

Observed result:

- exit 1
- 202 passed
- 5 failed
- five failing node IDs extracted

## Failure-guided coverage

Expected failing target functions: 5.

Found: 5/5.

Missing: none.

Extra failure hints: none.

Failure-guided compiled targets: 5/5.

Wrong paths: none.

## Compiled-context budget

- span count: 6 / 6
- compiled characters: 3200 / 3200
- global compiled-context budget unchanged

Failure-guided spans:

1. `test_a_ceo_objective_produces_a_bounded_work_order` — 837 chars
2. `test_the_derived_plan_names_the_stages_the_brief_asks_for` — 434 chars
3. `test_authorized_paths_are_enforced_on_the_packet_scope` — 443 chars
4. `test_the_execution_history_is_append_only_and_provenanced` — 818 chars
5. `test_the_engineering_package_is_owned_by_exactly_one_capsule` — 482 chars

The spare sixth slot was filled by ordinary semantic ranking.

## Critical P3C proof

The first failure-guided function now includes both:

- `assert order.authorized_paths == (...)`
- `assert order.required_tests == (...)`

This is the exact assertion P3B hid behind its 600-character generic excerpt cap and subsequently failed to update during the paid benchmark.

Therefore the matched-base preview demonstrates that P3C removes the known P3B context omission without increasing the global 3,200-character compiled-context budget or adding provider work.

## Decision

P3C is eligible for the final zero-provider static barrier:

1. all 11 canonical Company OS required suites green at the exact P3C SHA;
2. integration gate READY with zero blockers at that exact SHA.

Do not authorize another paid matched benchmark until both pass.

No canonical merge, deployment, publishing or production integration is authorized.
