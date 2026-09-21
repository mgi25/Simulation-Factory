# Phase A Discovery Checkpoint 20 — review-separation YAML dependency dry run accepted

Date: 2026-09-21

The bounded repair request for the pre-existing review-separation test dependency was run through the full deterministic Company OS request/open-job path against a fresh disposable state directory. No model session was launched.

## Repair target

Base commit:

`615dfea4ddadc56bedc108d91aae1663448f9f94`

Work order:

`wo-token-efficiency-v4-review-separation-yaml-dependency`

Authorized branch:

`eng-token-efficiency-v4-review-separation-yaml-dependency`

Authorized writable path, exactly:

`tests/test_company_review_separation.py`

## Dry-run result

- outcome: authorized
- state: planning
- selected capsule: `company-engineering-execution`
- resource profile: consumer
- specialist domain: empty
- escalation: none
- work-order fingerprint: `cf8dfd25fb689055`

Required tests:

1. `tests/test_company_engineering_execution.py`
2. `tests/test_company_review_separation.py`

Context kept:

- `capsule:company-engineering-execution`
- `tests/test_company_review_separation.py`

The engineering-execution suite remains required deterministic evidence but is outside the writable scope, which is correct.

## Guardrails

The repair may only:

- remove the direct PyYAML import from `tests/test_company_review_separation.py`;
- use the repository's canonical `company.validation.yaml_subset.load_yaml_subset` loader;
- preserve all existing behavioral assertions.

It may not add PyYAML to dependency manifests, alter runtime behavior, change authority policy, modify capsule metadata, or touch production code.

## Accounting

This repair addresses pre-existing undeclared test dependency debt exposed by extended validation. Any provider usage for it must be reported separately from the P2 matched benchmark efficiency comparison.

## Decision

The repair is safe to open in the real Repository Architecture V1 state directory.

Before invoking a model:

1. confirm the work-order id is unused in the real state;
2. open the real job;
3. inspect persisted scope/fingerprint/status;
4. run engineering-runner doctor with fresh dedicated repair runner/worktree directories;
5. do not invoke `run-one` until those outputs are inspected.

No canonical merge, deployment, publishing or production integration is authorized.
