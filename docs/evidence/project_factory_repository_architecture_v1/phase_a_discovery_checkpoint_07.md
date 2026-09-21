# Phase A Discovery Checkpoint 07 — Token Efficiency V4 P0 accepted

Date: 2026-09-21

## Scope

P0 of Agent Context and Token Efficiency V4 was implemented on branch `project-factory-token-efficiency-v4-p0` at commit:

`278b5bef76e4dc0aa13273b135e80841b0e9e5d5`

No Claude or other model call was used to implement the P0 code or validate it after the P0 branch was created.

## What P0 changes

P0 addresses the hidden-spend incident recorded in Checkpoint 06.

The implementation:

- treats every `session-N` provider subprocess as separately preserved evidence;
- aggregates stage usage across all paid provider subprocesses rather than reporting only the final successful repair session;
- preserves numbered exploration artifacts instead of allowing a mutable alias to hide earlier exploration;
- refuses automatic structured-report repair after a provider/backend stop such as `error_max_budget_usd`;
- preserves the original provider cost ceiling, timeout, model and tool restrictions on a legitimate report-format repair;
- records a durable Company OS execution stop as `decision_required`, so a restarted runner/watch loop cannot silently launch another paid session against the same in-flight work;
- adds deterministic regression coverage for the historical two-session failure shape and aggregate accounting.

## Focused validation

The operator tested the detached P0 worktree at the exact implementation commit.

- `python -m compileall company/engineering tools/engineering_runner -q`: PASS.
- focused pytest selection: **415 passed / 0 failed** in 113.22 s.

The focused selection covered:

- external engineering runner;
- engineering-runner exploration reporting;
- Company OS engineering execution;
- Company OS external engineering runner.

## Canonical required suites

All 11 required Company OS suites passed at the same commit:

1. `tests/test_company_analytics.py` — 160 passed
2. `tests/test_company_dashboard.py` — 32 passed
3. `tests/test_company_execution_transport.py` — 14 passed
4. `tests/test_company_finance.py` — 123 passed
5. `tests/test_company_integration_gate.py` — 88 passed
6. `tests/test_company_org_intelligence.py` — 119 passed
7. `tests/test_company_os_ai_platform.py` — 46 passed
8. `tests/test_company_os_capsules.py` — 66 passed
9. `tests/test_company_os_knowledge.py` — 26 passed
10. `tests/test_company_runtime.py` — 22 passed
11. `tests/test_company_workforce.py` — 93 passed

Result: **11/11 green**, exit code 0.

## Integration gate

The integration gate was run with supplied suite evidence and the Repository Architecture V1 company-state directory.

- report: `integration-readiness-2026-09-21-7a960a5bb2280774`
- source commit: `278b5bef76e4dc0aa13273b135e80841b0e9e5d5`
- blockers: **0**
- gate exit code: **0 / READY**
- `authorizes_production_integration`: **false**

Advisory checks with unknown evidence remain visible but are not required blockers.

## Decision

P0 acceptance criteria are satisfied.

The paid-run freeze imposed specifically because P0 accounting/retry safety was unproven may now be lifted **only for controlled P1 matched experiments after P1 static controls are implemented and deterministically validated**. This checkpoint does not authorize an immediate live model run.

P1 begins from the exact validated P0 commit and targets Claude startup/context isolation:

1. actual built-in tool availability restriction, not permission-only restriction;
2. strict MCP isolation;
3. elimination of unrelated startup tool/plugin/skill surfaces where supported;
4. hard model-turn circuit breaker if supported by the pinned Claude Code binary;
5. measurement of `system/init` before any broader semantic-context changes.

No canonical merge, production integration, deployment or publishing is authorized by this checkpoint.
