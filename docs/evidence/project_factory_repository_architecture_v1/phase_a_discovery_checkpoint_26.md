# Phase A Discovery Checkpoint 26 — P3A static gate harness import-path correction

Date: 2026-09-21

The first attempt to run the 11 canonical P3A suites did not execute any suite.

Observed error:

`ModuleNotFoundError: No module named 'company'`

The helper script was written under the system temporary directory and launched by filename. Python therefore placed the helper script directory on `sys.path`; the repository root was not importable even though PowerShell's current location was the validation worktree.

Classification:

- validation harness error;
- not a P3 implementation failure;
- zero canonical suites executed;
- integration gate did not run;
- no provider/model session used.

Correction:

Rerun the identical suite/gate procedure with the validation worktree explicitly present on `PYTHONPATH` for the helper process. Preserve exact P3 SHA `0be53a49b0f97a9c96fbe78bf1de018637c4621a`.

No code change, benchmark, canonical merge, deployment or publishing is authorized by this checkpoint.
