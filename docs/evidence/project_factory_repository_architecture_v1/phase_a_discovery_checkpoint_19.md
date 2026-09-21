# Phase A Discovery Checkpoint 19 — extended P2 validation exposed undeclared PyYAML test dependency

Date: 2026-09-21

The P2 benchmark correction reached `ready_for_approval` with integration gate report:

`integration-readiness-2026-09-21-baa5829b6a7b362f`

Gate blockers: 0.

Correction implementation commit:

`615dfea4ddadc56bedc108d91aae1663448f9f94`

The additional non-canonical validation requested for:

`tests/test_company_review_separation.py`

did not execute. Collection stopped with:

`ModuleNotFoundError: No module named 'yaml'`

## Classification

This is not a failure of the P2 runner boundary and not a failure of the correction implementation.

The test file itself directly imports third-party `yaml` / PyYAML, while:

- repository `requirements.txt` does not declare PyYAML;
- Company OS's canonical configuration path deliberately uses `company.validation.yaml_subset.load_yaml_subset`;
- the Company OS validation capsule explicitly states that the YAML reader is a deliberate subset and no PyYAML dependency enters the control plane.

Installing PyYAML into the validation environment would hide the undeclared-dependency defect and would make the semantic-test relationship depend on an environment package the repository does not declare.

## Required repair

Repair only `tests/test_company_review_separation.py`:

1. remove `import yaml`;
2. import `load_yaml_subset` from `company.validation.yaml_subset`;
3. load `company/org_registry.yaml` through `load_yaml_subset`;
4. leave all behavioral assertions unchanged.

The canonical loader already parses `org_registry.yaml` for Company OS runtime configuration.

## Benchmark accounting

This dependency repair is pre-existing test debt exposed by the new semantic-test relationship. Its provider cost, if any, must be reported separately from the P2 matched benchmark efficiency comparison.

The P2 benchmark/correction provider measurements remain unchanged.

## Additional observation

A second `run-one` invoked after the correction job was already `ready_for_approval` performed zero stages and returned successfully. Status then displayed the same result fingerprint twice. Record this as a separate idempotency/evidence-list observation; do not modify the current accepted correction while closing the semantic-test dependency issue.

No canonical merge, deployment, publishing or production integration is authorized.
