# Token Efficiency V4 P4 — Content-addressed deterministic cache

Date: 2026-09-21

## Objective

Reduce repeated deterministic repository-analysis work without caching authority, lifecycle state, test outcomes, model judgments or gate decisions.

P4 begins with the repository AST map because it is:

- deterministic;
- expensive enough to repeat across many stages and work orders;
- advisory only;
- safe to rebuild on a miss;
- independent of CEO-reserved authority.

## P4A scope

P4A caches the deterministic repository map under runner-owned state.

Source branch:

`project-factory-token-efficiency-v4-p4`

Parent accepted P3C runner:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

P4A cache root:

`<runner_dir>/cache/repo-map/`

The cache is disposable runner state. It is never stored in Company OS state and never written into the repository worktree.

## Content identity

A module cache key includes:

1. cache-format version;
2. repository-relative path;
3. exact source bytes.

Therefore a source edit, rename or parser-version bump cannot silently reuse an old module map.

An exact-tree fingerprint is computed from:

1. cache-format version;
2. configured repository-map roots;
3. ordered relative paths;
4. each module's content-addressed key.

## Two reuse layers

### Exact-tree snapshot

If the complete scoped tree fingerprint has been seen before, the complete RepoMap snapshot is reused.

No AST parse or reverse-index reconstruction is needed on this path.

### Per-module cache

If the tree changed, each unchanged module surface may still be reused by content identity.

Only changed/new modules are parsed again. Reverse test and production dependency indexes are then rebuilt deterministically from the resulting module set.

## Fail-closed / fallback behavior

The cache grants no authority.

A missing cache is a cold build.

A corrupt cache entry is a miss.

A cache I/O failure falls back to the existing fresh deterministic repository-map build.

If even the fresh map cannot be built, repository-map context remains unavailable exactly as before; work authority is unaffected.

## Evidence

Each developer/reviewer stage records:

- cache available;
- cache version;
- scoped tree fingerprint;
- module count;
- module hits;
- module misses;
- exact-tree snapshot hit;
- invalid cache entries.

This evidence is written beside the existing resource strategy evidence.

## Explicitly not cached in P4A

P4A does not cache:

- Company OS work orders or authority snapshots;
- base diagnostic pytest results;
- post-edit pytest results;
- session receipts;
- reviewer attestations;
- gate reports or readiness;
- provider/model outputs;
- execution-context bundles.

Those artifacts depend on execution state, task semantics or judgment and need a separate proof before any future cache can touch them.

## Acceptance floor

P4A must prove:

1. a cold tree builds a correct map and records misses;
2. an identical tree reuses an exact snapshot;
3. a one-file source edit invalidates the snapshot and re-parses only that module;
4. a corrupt cache entry is rebuilt rather than trusted;
5. runner developer/reviewer stages persist cache evidence;
6. no new dependency is added;
7. P3C semantic context behavior is unchanged;
8. the focused engineering-runner suites pass;
9. all canonical Company OS suites and the integration gate remain green before any paid benchmark.

No canonical merge, deployment, publishing or production integration is authorized.
