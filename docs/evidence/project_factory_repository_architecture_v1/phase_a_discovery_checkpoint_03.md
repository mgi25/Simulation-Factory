# Phase A Discovery Checkpoint 03 — Planning test ownership gap

Date: 2026-09-21
Program branch baseline: a5f7505bcee46593816326c7bca7abc1b7a97395

## Finding

The bounded lifecycle-reconciliation request was authorized, but intake reduced
its write scope to `company/delegation/__main__.py` and substituted
`tests/test_company_delegation.py` as the required test.

The two regression suites named by the request,
`tests/test_company_objective_planning.py` and
`tests/test_company_executive_planning.py`, are the established suites for the
planning behaviors being changed, but the `company-executive-delegation`
capsule currently declares only `tests/test_company_delegation.py`.

## Why this matters

Running the under-scoped work order would either:
- leave the lifecycle fix without focused regression tests, or
- tempt the developer to touch test files outside its immutable work-order scope.

The defect was detected by deterministic intake and runner doctor before a model
session started, so measured model spend for this attempt is USD 0.00.

## Required correction

Treat the objective-planning and executive-planning suites as semantic tests of
the `company-executive-delegation` capsule by adding them to that capsule's
`tests` list, and pin that relationship in capsule tests.

This does not change runtime behavior, delegation authority, production code,
canonical main, or the ownership of the test files themselves.
