# Phase A Discovery Checkpoint 37 — P3C stdlib dependency-guard correction

Date: 2026-09-21

The second P3C focused-validation run proved the bytecode-cache isolation fix worked:

- `test_a_failing_required_test_produces_a_rejected_receipt_rather_than_a_pass`: PASS
- full focused suite: 238 passed, 1 failed

The remaining failure was:

`test_the_runner_adds_no_dependency`

Reason:

`tools/engineering_runner/evidence.py` now imports Python stdlib module `tempfile`, but the test's explicit standard-library allowlist did not yet include `tempfile`.

This is a test-harness allowlist omission, not a third-party dependency addition.

Correction:

- add `tempfile` to the stdlib allowlist in `tests/test_external_engineering_runner.py`
- no runner behavior, authority, dependency manifest, Company OS policy, production simulation code or reviewer policy changed.

Correction commit:

`1705720eb9fac38990639c82477fbfbc2f55aa7e`

Next validation order:

1. dependency-guard test;
2. pycache regression test;
3. complete P3C focused suite.

Do not proceed to preview, canonical suites, gate or paid benchmark until the focused suite is green.

No canonical merge, deployment, publishing or production integration is authorized.
