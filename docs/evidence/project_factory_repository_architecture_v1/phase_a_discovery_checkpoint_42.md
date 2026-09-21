# Phase A Discovery Checkpoint 42 — P3C paid run not started; status exit semantics corrected

Date: 2026-09-21

The first P3C paid-run launch wrapper stopped before invoking the engineering runner.

## What happened

The wrapper executed:

`python -m company.engineering status`

for work order:

`wo-token-efficiency-v4-p3c-benchmark-contract-correction`

The command printed a valid persisted job in state:

`planning`

with:

- work-order fingerprint `237e2a9d7a69c0dd`;
- developer attempts: 0;
- no reviews, results, attestations or gate verdicts.

The wrapper then incorrectly treated the command's nonzero exit as an inability to read the work order and stopped.

## CLI contract

`company.engineering status` intentionally returns:

- 0 only when the job is `ready_for_approval`;
- 1 when the job exists but is stopped/not yet ready (including `planning`);
- 2 when the input or move is refused/malformed.

Therefore exit 1 with a valid `planning` payload is expected and is not an error.

## Spend / lifecycle impact

No `tools.engineering_runner run-one` invocation occurred.

Consequently:

- provider sessions launched: 0;
- developer attempts consumed: 0;
- work order remains in `planning`;
- benchmark branch/worktree creation did not start;
- no paid benchmark evidence was produced.

## Correction

The paid-run wrapper must validate the parsed status payload itself:

- work-order id matches;
- state is `planning`;
- developer attempts are 0;
- work-order fingerprint is `237e2a9d7a69c0dd`.

It must treat status exit 2 as refusal, but must not require exit 0 while the job is still in `planning`.

No canonical merge, deployment, publishing or production integration is authorized.
