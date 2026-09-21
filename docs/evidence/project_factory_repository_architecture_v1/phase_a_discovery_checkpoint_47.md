# Phase A Discovery Checkpoint 47 — P4A focused validation accepted

Date: 2026-09-21

P4A content-addressed repository-map caching has passed focused zero-provider validation.

## Exact source state

P4 branch:

`project-factory-token-efficiency-v4-p4`

Validated SHA:

`9d3743073f4efefae120e311839189b526786a0e`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Validation results

Compile:

- exit 0

Cache-focused suite:

- `tests/test_engineering_runner_repo_map.py`
- 24 passed
- exit 0
- duration 0.86 s

Runner-focused suites:

- `tests/test_external_engineering_runner.py`
- `tests/test_company_external_engineering_runner.py`
- `tests/test_engineering_runner_execution_context.py`
- 240 passed
- exit 0
- duration 264.28 s

## Cache behavior now covered

Focused tests prove:

- cold build records misses;
- exact repeated scoped tree reuses a complete snapshot;
- one source edit invalidates the tree snapshot;
- unchanged modules remain reusable by exact path+content identity;
- only the changed module must be reparsed in the one-file synthetic case;
- corrupt cache entries are treated as misses and rebuilt;
- changed source cannot reuse an old snapshot;
- developer and reviewer stages persist cache evidence;
- P3C execution-context behavior remains intact.

## Decision

P4A is eligible for a zero-provider measurement on the real repository.

Measure, at the exact P4A SHA:

1. cold repository-map build;
2. exact warm snapshot reuse;
3. one-file source invalidation in an isolated temporary worktree;
4. module hit/miss counts;
5. wall-clock duration for each case;
6. output equivalence between cached and fresh deterministic maps.

Do not run the canonical 11-suite gate or any paid benchmark until this real-repository measurement passes.

No canonical merge, deployment, publishing or production integration is authorized.
