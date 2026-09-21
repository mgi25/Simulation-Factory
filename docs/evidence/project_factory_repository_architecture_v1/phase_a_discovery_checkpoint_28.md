# Phase A Discovery Checkpoint 28 — P3 matched benchmark dry run accepted

Date: 2026-09-21

The P3 matched benchmark request passed deterministic intake without launching a provider session.

## Runner source

Validated P3 runner:

`0be53a49b0f97a9c96fbe78bf1de018637c4621a`

## Work order

Work order:

`wo-token-efficiency-v4-p3-benchmark-contract-correction`

Fingerprint:

`b2a1147235541e8f`

Outcome:

`authorized`

State:

`planning`

Selected capsule:

`company-engineering-execution`

Resource profile:

`consumer`

Specialist domain:

empty

Escalation:

`none`

## Matched task boundary

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Authorized branch:

`eng-token-efficiency-v4-p3-benchmark-contract-correction`

Writable path, exactly:

`tests/test_company_engineering_execution.py`

Required deterministic test:

`tests/test_company_engineering_execution.py`

One developer attempt only.

This reproduces the P2 high-read correction task's material authority/test boundary while changing the runner implementation from P2 to validated P3.

## Benchmark-base inspection

The target expectations are dispersed across multiple test functions in the one authorized file, including:

- `test_a_ceo_objective_produces_a_bounded_work_order`
- `test_the_derived_plan_names_the_stages_the_brief_asks_for`
- `test_authorized_paths_are_enforced_on_the_packet_scope`
- `test_the_execution_history_is_append_only_and_provenanced`
- `test_the_engineering_package_is_owned_by_exactly_one_capsule`

This is the same semantic-rediscovery shape that produced the high-read P2 correction session.

## Decision

Before any provider spend, preview P3's actual compiled semantic spans against the task base commit using the validated P3 compiler code.

Do not open the real benchmark job or run `run-one` until the preview is inspected.

No canonical merge, deployment, publishing or production integration is authorized.
