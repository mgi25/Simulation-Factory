# Phase A Discovery Checkpoint 51 — P4C Git-identity fast path ready for validation

Date: 2026-09-21

P4B improved the one-file incremental cache path from 13.020031 s to 5.784761 s but remained 23.5% slower than a fresh 4.685559 s build.

## P4C source

Branch:

`project-factory-token-efficiency-v4-p4`

Current SHA:

`0cff265e5b92dc73c8ca1526da8664126d06af1b`

P4C delta from P4B is confined to:

- `tools/engineering_runner/repo_map.py`
- `tools/engineering_runner/runner.py`
- `tools/engineering_runner/workspace.py`
- `tests/test_engineering_runner_repo_map.py`
- `tests/test_external_engineering_runner.py`

No Company OS authority source, production simulation code, dependency manifest, governance file or canonical branch changed.

## Fast-path design

The runner now asks its existing Workspace Git boundary for tracked Python blob identities.

The fast path is enabled only when:

1. the task worktree is clean;
2. Git returns a non-empty tracked path -> blob id mapping.

Git blob ids are content-addressed. On this path the repository-map cache can compare exact content identities without reopening every unchanged source file.

Cache keys still include:

- cache-format version;
- repository-relative path;
- exact content identity.

P4C cache-format version is 3.

## Fallback

If the worktree is dirty, Git identity retrieval fails, or no tracked blob map is available, the runner uses the P4B filesystem-content path.

The cache remains advisory and cannot widen authority or block a task merely because caching is unavailable.

## Evidence

Developer/reviewer `resources.json` now records:

`identity_source: git_blob`

or:

`identity_source: filesystem`

alongside snapshot and module hit/miss evidence.

## New proof coverage

Tests require:

- trusted identity maps can reuse unchanged ModuleMaps without reading unchanged source files;
- clean runner developer stages report `git_blob`;
- clean runner reviewer stages report `git_blob`;
- existing snapshot/invalidation/corruption behavior remains intact.

## Decision

Validate zero-provider in this order:

1. compile;
2. repository-map cache suite;
3. runner cache-evidence tests / focused runner suite if needed;
4. only after green, repeat the real-repository benchmark using a committed one-file change so the measurement matches the runner's actual clean-worktree execution boundary.

No paid provider work is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
