# Phase A Discovery Checkpoint 36 — P3C focused validation exposed pytest bytecode contamination

Date: 2026-09-21

The first P3C focused-validation run compiled successfully but stopped with one failing external-runner regression test.

## P3C source under test

`78f15d422403623ce7790a0cf6f3527afc2dd4bd`

Focused result:

- 238 passed
- 1 failed
- failing test:
  `test_a_failing_required_test_produces_a_rejected_receipt_rather_than_a_pass`

Observed symptom:

- the scripted developer changed `subject/module.py` from `VALUE = 1` to `VALUE = 0`;
- the post-edit required suite was incorrectly recorded green;
- the resulting receipt therefore said `accepted` instead of `rejected`.

## Root cause

P3B introduced a required-test diagnostic before the provider session.

That diagnostic runs pytest at the immutable base checkout. Python may write timestamp-and-size validated `.pyc` files into the task worktree.

The regression fixture deliberately performs a same-size edit:

`VALUE = 1\n` -> `VALUE = 0\n`

If the post-edit deterministic pytest run starts inside the filesystem timestamp granularity window, CPython can reuse the base checkout's cached bytecode because both source size and coarse modification timestamp still match. The post-edit suite can therefore observe stale code and report a false green.

This is not a P3C semantic-context regression. It is a deterministic-validation isolation defect made reachable by the new pre-provider diagnostic.

## Correction

Runner deterministic pytest invocations now receive a unique temporary `PYTHONPYCACHEPREFIX` outside the task worktree.

Properties:

- every invocation gets a fresh cache directory;
- base-diagnostic bytecode cannot be reused by post-edit validation;
- the cache directory is deleted after the subprocess exits;
- no repository path or authority is widened;
- pytest argv and acceptance semantics are otherwise unchanged.

Correction commit:

`74db06df02fe96bbca1776776bf478a91ef0a26a`

P3C semantic compiler version remains 3.

## Current P3C diff from accepted P3B

The P3C delta remains confined to:

- `tools/engineering_runner/execution_context.py`
- `tools/engineering_runner/evidence.py`
- `tests/test_engineering_runner_execution_context.py`
- `tests/test_external_engineering_runner.py`

No Company OS authority, production simulation code, dependency manifest, reviewer policy or canonical branch is modified.

## Decision

Revalidate the previously failing regression test first.

Only if it passes should the complete focused P3C suite be rerun.

Do not proceed to matched-base preview, canonical 11-suite gate or any paid benchmark until focused validation is green.

No canonical merge, deployment, publishing or production integration is authorized.
