# Phase A Discovery Checkpoint 02 — Candidate lifecycle persistence gap

Date: 2026-09-21
Program branch baseline: 23b41893895418d24d059f9a114a8109bc5e4f84

## Finding

The first Repository Architecture V1 Company OS work order,
`wo-capsule-ownership-semantic-review`, completed successfully and was approved by
the CEO. The engineering job is closed and its implementation is integrated into
the program branch.

However, objective planning still sees
`capsule-ownership-semantic-review` as OPEN because planning constructs its
register only from `company/delegation/candidate_seeds.json`.

The delegation model itself defines candidate history as append-only:
`OPEN -> SELECTED -> COMPLETED`, with later versions stored through
`DelegationStore.append_candidate` and the latest version winning. The CLI
planning path currently does not read that history.

## Why this matters

A repeated `plan-run` can select work that has already been completed. That is
both a correctness defect and an AI-efficiency defect: it can launch duplicate
developer/reviewer sessions and spend model budget on an accepted outcome the
company already has.

This was discovered before a second paid worker session was started.

## Evidence

- `company/delegation/candidates.py`: status transitions are append-only and only
  OPEN is selectable.
- `company/delegation/store.py`: `DelegationStore.register()` exposes the latest
  stored candidate version.
- `company/delegation/__main__.py`: `_register_for` currently returns only
  `load_seed_register(...)`; `plan-run` has no state-dir input.
- `company/delegation/candidate_seeds.json`: the completed candidate is still
  represented as OPEN in the seed snapshot.
- The CEO-approved engineering job is closed in the local Company OS engineering
  state; no second worker has been launched.

## Required behavior

When a caller explicitly supplies a delegation state directory, objective
planning must resolve candidates from the seed snapshot plus the latest persisted
candidate versions, with persisted versions winning for the same candidate id.

With no state directory, existing seed-only behavior must remain unchanged.

This checkpoint does not authorize a broad planning redesign, a new persistence
layer, a candidate-schema migration, or any change to canonical main.
