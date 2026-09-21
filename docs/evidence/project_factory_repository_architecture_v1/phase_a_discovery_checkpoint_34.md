# Phase A Discovery Checkpoint 34 — P3B paid benchmark quality failure

Date: 2026-09-21

The first paid P3B matched benchmark completed one developer stage and one reviewer stage, then correctly stopped at `decision_required`.

## Work order

`wo-token-efficiency-v4-p3-benchmark-contract-correction`

Work-order fingerprint:

`b2a1147235541e8f`

Runner source:

`07429215cf171c78ae91a1a7a232047c5bd071da`

Task base:

`287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`

Implementation commit:

`be771009bff7c25e37b562ed64e13e79218e6018`

Changed paths:

- `tests/test_company_engineering_execution.py` only

Branch:

`eng-token-efficiency-v4-p3-benchmark-contract-correction`

## Lifecycle result

Run outcome: blocked.

Final state: `decision_required`.

Developer attempts used: 1 / 1.

Reviewer:

- attested verdict: `changes_required`
- deterministic verdict: `changes_required`

No gate stage ran.

The runner correctly stopped instead of opening another paid developer attempt.

## Diff comparison

The P3B implementation changed five exact regression locations:

1. authorized paths;
2. plan writing paths;
3. packet scope;
4. persisted authority;
5. capsule exact tests tuple.

The previously accepted P2 correction commit `615dfea4ddadc56bedc108d91aae1663448f9f94` changed those five locations plus a sixth assertion in the same first test function:

`order.required_tests`

The missing expected form is:

```python
assert order.required_tests == (
    "tests/test_company_engineering_execution.py",
    "tests/test_company_review_separation.py",
)
```

## Root-cause hypothesis to verify from local artifacts

P3B selected the correct first failing test function, but the failure-guided excerpt for that function was rendered through the older generic source-excerpt cap. The preview showed the first span ending before the `order.required_tests` assertion.

Therefore the current evidence supports this narrow hypothesis:

- failure-guided symbol selection worked;
- the failure-guided excerpt body was too short;
- pytest reports one node id per failing test function and stops at the first failed assertion in that function, so the second stale exact assertion was not independently discoverable from the base failure list.

Do not claim final causality until reviewer findings and execution-context evidence from the paid run are inspected.

## Decision

P3B is not accepted as quality-preserving from this benchmark.

Do not invoke `run-one` again on this work order.

Next actions:

1. extract developer/reviewer session telemetry;
2. inspect `execution-context.json`, `base-tests.json`, test evidence and reviewer findings;
3. quantify efficiency separately from quality;
4. if the root-cause hypothesis is confirmed, make a deterministic P3C correction that preserves more of an exact failing function within the existing global context budget;
5. validate and preview for free before any further paid benchmark.

No canonical merge, deployment, publishing or production integration is authorized.
