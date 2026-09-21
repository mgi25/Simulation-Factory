# Phase A Discovery Checkpoint 50 — P4B cache-focused validation accepted

Date: 2026-09-21

P4B's consolidated repository-map cache representation has passed cache-focused zero-provider validation.

## Exact source state

P4 branch:

`project-factory-token-efficiency-v4-p4`

Validated SHA:

`13810d16690fea7cf9662ca1a09de46bc08aeb65`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Validation

Compile:

- exit 0

Repository-map cache suite:

- `tests/test_engineering_runner_repo_map.py`
- 24 passed
- exit 0
- duration 1.15 s

## What this validates

P4B preserves the P4 cache contract after replacing the hundreds-of-small-files incremental path with a consolidated prior-snapshot manifest.

The tests continue to prove:

- cold build correctness;
- exact-tree snapshot reuse;
- one-file invalidation;
- reuse of unchanged modules;
- stale snapshot refusal;
- corrupt cache recovery;
- deterministic equality with a fresh repository map.

## Decision

Repeat the exact same real-repository benchmark used for P4A:

1. cold build;
2. exact warm reuse;
3. one-file source change in an isolated temporary worktree.

Compare P4B directly with P4A's measured baseline:

- P4A cold cached path: 7.279697 s;
- P4A exact warm cached path: 0.114604 s;
- P4A one-file changed cached path: 13.020031 s;
- P4A one-file fresh path: 4.359222 s;
- P4A one-file reuse: 509/510 modules.

P4B must preserve structural correctness and remove the practical incremental slowdown before broader runner-focused or canonical validation resumes.

No paid provider work is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
