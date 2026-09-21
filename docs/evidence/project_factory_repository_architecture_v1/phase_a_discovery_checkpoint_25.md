# Phase A Discovery Checkpoint 25 — P3A static validation accepted

Date: 2026-09-21

Token Efficiency V4 P3A has passed its focused static-validation boundary.

## Implementation branch

Branch:

`project-factory-token-efficiency-v4-p3`

Validated SHA:

`0be53a49b0f97a9c96fbe78bf1de018637c4621a`

Validated P2 base:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

GitHub branch state at checkpoint:

- P3 branch: `0be53a49b0f97a9c96fbe78bf1de018637c4621a`
- canonical `main`: `65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Focused validation

Compile:

- `tools/engineering_runner/execution_context.py`
- `tools/engineering_runner/briefs.py`
- `tools/engineering_runner/runner.py`

Result: PASS.

Focused tests:

- `tests/test_engineering_runner_execution_context.py`
- `tests/test_external_engineering_runner.py`
- `tests/test_company_external_engineering_runner.py`

Result:

- 230 passed
- exit 0
- duration 106.35 s

No provider/model session was used.

## Diff boundary

Exactly five files differ from P2 base:

1. `tests/test_engineering_runner_execution_context.py`
2. `tests/test_external_engineering_runner.py`
3. `tools/engineering_runner/briefs.py`
4. `tools/engineering_runner/execution_context.py`
5. `tools/engineering_runner/runner.py`

Diffstat:

- 473 insertions
- 5 deletions

No dependency manifest, production simulation code, Company OS authority policy, reviewer policy, or canonical branch was modified.

## P3A controls now pinned by tests

- deterministic multi-span semantic selection;
- maximum compiled-span count;
- hard compiled-span character budget;
- deterministic source-content digests;
- stable context fingerprint;
- persisted `execution-context.json`;
- resource evidence references the same context fingerprint;
- no manufactured semantic match;
- P2 generic excerpt fallback when the compiler finds no useful spans;
- required/read-only tests can inform context without widening `may_write`;
- consumer P2 tool restrictions remain intact.

## Decision

P3A is eligible for full Company OS static validation:

1. all 11 canonical required suites;
2. integration gate at exact P3 SHA.

Do not run a paid P3 benchmark until both are green.

No canonical merge, deployment, publishing or production integration is authorized.
