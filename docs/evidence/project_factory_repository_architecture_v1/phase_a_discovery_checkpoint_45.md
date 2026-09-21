# Phase A Discovery Checkpoint 45 — P4A content-addressed cache implementation ready for focused validation

Date: 2026-09-21

P3 is closed at accepted P3C.

P4 starts as a separate branch and does not modify the accepted P3 branch.

## Branch

`project-factory-token-efficiency-v4-p4`

Base:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Current P4A SHA at this checkpoint:

`c6b8f9dca665b32ecd1a5192cd4bd4a4f88c0344`

## Changed paths from P3C

- `tools/engineering_runner/repo_map.py`
- `tools/engineering_runner/runner.py`
- `tests/test_engineering_runner_repo_map.py`
- `tests/test_external_engineering_runner.py`

No Company OS control-plane source, production simulation code, dependency manifest, governance file or canonical branch changed.

## Implementation

P4A adds:

- exact path+source-byte module cache keys;
- scoped tree fingerprints;
- exact-tree RepoMap snapshot reuse;
- per-module reuse across changed trees;
- corrupt-entry rebuild;
- runner-owned cache root under `runner_dir/cache/repo-map`;
- developer/reviewer cache evidence in `resources.json`.

P4A does not cache authority, test outcomes, review judgments or gate results.

## Tests added

Regression coverage now includes:

- exact-tree warm snapshot hit;
- one-file invalidation with one module miss;
- corrupt module recovery;
- stale snapshot refusal after source change;
- developer resource evidence;
- reviewer reuse of an exact scoped tree.

## Decision

Run zero-provider focused validation before any broader suite or benchmark.

No paid provider run is authorized at this checkpoint.

No canonical merge, deployment, publishing or production integration is authorized.
