# Phase A Discovery Checkpoint 52 — P4C Git-identity focused validation accepted

Date: 2026-09-21

P4C has passed the narrow zero-provider validation for its Git-blob identity fast path.

## Exact source state

P4 branch:

`project-factory-token-efficiency-v4-p4`

Validated SHA:

`0cff265e5b92dc73c8ca1526da8664126d06af1b`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Validation results

Compile:

- exit 0

Repository-map cache suite:

- 25 passed
- exit 0
- duration 1.05 s

Runner cache-evidence tests:

- 3 passed
- exit 0
- duration 24.23 s

The runner tests prove clean developer/reviewer worktrees report:

`identity_source: git_blob`

and continue to preserve the existing content-addressed cache evidence.

## Decision

P4C is eligible for the real-repository committed-change benchmark.

The benchmark must match the runner's actual clean-worktree boundary:

1. measure a cold build on the clean P4C checkout using tracked Git blob identities;
2. measure an exact warm reuse on the same clean tree;
3. create an isolated temporary worktree at the same P4C SHA;
4. modify exactly one scoped Python file;
5. commit that change locally so the worktree is clean and Git assigns a new blob id;
6. measure the incremental cache path using Git blob identities;
7. compare every cached result against a fresh deterministic RepoMap;
8. remove the temporary worktree after measurement.

Hard correctness requirements remain:

- cached map equals fresh map;
- exact warm: 510/510 hits, snapshot hit true;
- committed one-file change: snapshot hit false, 509/510 hits, exactly 1 miss;
- changed tree fingerprint differs.

Performance is measured, not used to relax correctness. The practical target is to eliminate P4B's remaining incremental regression.

No paid provider work is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
