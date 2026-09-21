# Phase A Discovery Checkpoint 49 — P4B consolidated incremental cache ready for validation

Date: 2026-09-21

The P4A real-repository benchmark proved exact warm snapshot reuse was valuable but exposed a severe incremental representation cost: 509/510 module reuse still took 13.020031 s versus a 4.359222 s fresh build.

## P4B source

Branch:

`project-factory-token-efficiency-v4-p4`

Current SHA:

`13810d16690fea7cf9662ca1a09de46bc08aeb65`

Parent accepted P3C remains:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

## Representation change

P4B keeps the same exact content identities:

- cache-format version;
- repository-relative path;
- exact source bytes;
- exact scoped-tree fingerprint.

It replaces the normal incremental per-module-file recovery path with two records:

1. exact-tree snapshot:
   `snapshots/<tree-fingerprint>.json`
2. latest manifest:
   `latest.json`

The latest manifest contains:

- cache version;
- previous exact tree fingerprint;
- scoped roots;
- path -> exact content-key mapping.

On a changed tree the runner:

1. computes the current exact content keys;
2. loads one latest manifest;
3. loads one previous exact snapshot;
4. reuses a ModuleMap only when path and exact content key both match;
5. reparses changed/new modules;
6. rebuilds reverse indexes deterministically;
7. writes the new exact snapshot and latest manifest atomically.

The normal path therefore no longer opens hundreds of per-module JSON cache files.

## Corruption behavior

A corrupt latest manifest is a cache miss.

If the exact snapshot is unavailable and the latest manifest is corrupt, P4B performs a full deterministic rebuild and rewrites valid cache state.

Authority, tests, receipts, model outputs, reviewer judgments and gate outcomes remain uncached.

## Decision

Validate in this order:

1. compile;
2. repository-map cache tests;
3. if green, repeat the same real-repository cold / exact-warm / one-file-changed benchmark.

Do not run the broader runner-focused suites or canonical gate until the incremental measurement is no longer a practical regression.

No paid provider run is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
