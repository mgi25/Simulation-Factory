# Phase A Discovery Checkpoint 46 — P4A warm-snapshot ordering correction

Date: 2026-09-21

The first P4A cache-focused validation compiled successfully and produced:

- 23 passing cache tests;
- 1 failing cache test.

Failing test:

`test_content_addressed_cache_reuses_an_exact_tree_snapshot`

## Observed evidence

The second cache build reported:

- module hits: all modules;
- module misses: 0;
- snapshot hit: false;
- invalid entries: 1.

Therefore module-level content-addressed reuse was already correct. The exact-tree snapshot was being falsely rejected by validation.

## Root cause

The scoped source scan builds its entry list in configured root traversal order:

`company, tools, tests`

The serialized RepoMap stores modules in canonical globally sorted path order.

Snapshot validation compared the serialized module path sequence against the unsorted traversal-order sequence. For a valid tree this can differ (for example, `tests/...` sorts before `tools/...`), so a valid snapshot was marked invalid even though every content-addressed module entry matched.

## Correction

Snapshot membership validation now compares against the expected repository paths in canonical sorted order, matching RepoMap serialization.

Correction commit:

`9d3743073f4efefae120e311839189b526786a0e`

No cache key, authority rule, runner stage behavior, dependency, Company OS control-plane source, production simulation code or canonical branch changed.

## Decision

Re-run cache tests only first.

If green, run the P4A runner-focused suites.

No paid provider work is authorized.

No canonical merge, deployment, publishing or production integration is authorized.
