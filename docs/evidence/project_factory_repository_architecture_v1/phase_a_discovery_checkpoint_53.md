# Phase A Discovery Checkpoint 53 — P4C real-repository cache performance accepted

Date: 2026-09-21

P4C passed the real-repository committed-change cache benchmark at exact SHA:

`0cff265e5b92dc73c8ca1526da8664126d06af1b`

Canonical `main` remains:

`65df08a3e22d692d2783ab6004ce6f3d4046f54e`

No canonical merge occurred.

## Repository surface

Scoped Python modules:

`510`

All measurements used `identity_source: git_blob` on clean committed worktrees.

Every cached result was equivalent to a fresh deterministic RepoMap.

## Cold

- identity lookup: 0.063590 s
- cache build: 4.426638 s
- total: 4.490228 s
- fresh build: 4.466126 s
- hits: 0
- misses: 510
- snapshot hit: false
- equivalent: true

Cold overhead versus fresh is approximately 0.5%, effectively neutral for this sample while also populating reusable cache state.

## Exact warm

- identity lookup: 0.040527 s
- cache build: 0.040730 s
- total: 0.081257 s
- fresh build: 2.595824 s
- hits: 510
- misses: 0
- snapshot hit: true
- equivalent: true

Time reduction versus fresh:

`96.9%`

## Committed one-file change

Temporary committed benchmark head:

`ce53bfdb386066733b33cb16c5d01423c045299d`

- identity lookup: 0.061017 s
- cache build: 0.317517 s
- total: 0.378534 s
- fresh build: 10.320767 s
- hits: 509
- misses: 1
- snapshot hit: false
- equivalent: true

Time reduction versus fresh:

`96.3%`

Incremental improvement versus P4A's 13.020031 s:

`97.1%`

Incremental improvement versus P4B's 5.784761 s:

`93.5%`

## Structural result

P4C preserved all required invariants:

- clean committed source identity came from Git blobs;
- unchanged tree: exact snapshot reuse;
- changed committed tree: old snapshot refused;
- exactly one changed module reparsed;
- all 509 unchanged modules reused;
- changed tree fingerprint changed;
- cached map equals a fresh deterministic map.

The temporary benchmark worktree was removed after measurement.

## Decision

P4C's cache representation and Git-identity fast path are practically accepted.

Proceed with the remaining zero-provider static barrier:

1. complete runner-focused validation at the exact P4C SHA;
2. all 11 canonical Company OS suites;
3. integration gate READY with zero blockers.

Do not authorize paid provider benchmarking until all static barriers pass.

No canonical merge, deployment, publishing or production integration is authorized.
