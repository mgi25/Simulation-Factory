# Phase A Discovery Checkpoint 48 — P4A real-repository measurement exposes incremental-cache performance defect

Date: 2026-09-21

P4A passed the structural real-repository cache measurement at exact SHA:

`9d3743073f4efefae120e311839189b526786a0e`

## Repository measurement

Scoped Python modules:

`510`

Repository-map serialized size:

`2,615,977 chars`

### Cold

- cached path: 7.279697 s
- fresh build: 4.813767 s
- module hits: 0
- module misses: 510
- snapshot hit: false
- cached result equals fresh result: true

The cold cache population is expected to cost more than a fresh build because it both builds and persists reusable evidence.

### Exact warm

- cached path: 0.114604 s
- fresh build: 2.359180 s
- module hits: 510
- module misses: 0
- snapshot hit: true
- cached result equals fresh result: true
- time reduction versus fresh: 95.1%

This proves exact-tree reuse is both correct and practically valuable.

### One-file changed

- cached path: 13.020031 s
- fresh build: 4.359222 s
- module hits: 509
- module misses: 1
- snapshot hit: false
- cached result equals fresh result: true
- module reuse: 99.80%
- cached time reduction versus fresh: -198.7%

The structural invalidation contract passed, but the incremental path is not practically acceptable yet.

## Root cause selected for correction

P4A stores each module surface as a separate JSON object.

On a changed tree the cache reads/parses up to hundreds of small per-module JSON files in order to recover the unchanged module maps. On this OneDrive-hosted repository, that filesystem/JSON overhead dominates the AST work the cache was intended to avoid.

This is a cache representation defect, not a content-identity or correctness defect.

## P4B direction

Keep exact path+source-byte content identities and exact-tree snapshots.

Add one validated previous-snapshot manifest containing:

- the previous tree's ordered path -> content-key mapping;
- the complete RepoMap for that exact tree.

On a changed tree:

1. calculate current exact content keys;
2. load one prior manifest/snapshot;
3. reuse a previous ModuleMap only when both path and content key match;
4. parse only changed/new modules;
5. rebuild reverse indexes deterministically;
6. publish the new exact-tree snapshot and latest manifest atomically.

Per-module objects may remain as a fallback/content store, but the normal incremental path must not require hundreds of small cache-file reads.

## Decision

Do not run the 11 canonical suites yet.

First make the incremental cache practically useful while preserving the already-proven content-addressed correctness guarantees.

No paid provider run is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
