# Phase A Discovery Checkpoint 15 — P2 matched benchmark real job preflight

Date: 2026-09-21

The P2 matched benchmark V2 request has been opened in the real Repository Architecture V1 Company OS state using exact validated P2 implementation commit:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

No benchmark model session had been launched at this checkpoint.

## Persisted job

- work order: `wo-token-efficiency-v4-p2-review-test-ownership-v2`
- state: `planning`
- developer attempts: 0
- work-order fingerprint: `a60db35afdf0ef3b`
- plan fingerprint: `12e6203ca8105f42`
- authorized branch: `eng-token-efficiency-v4-p2-review-test-ownership-v2`
- base commit: `619b2a0374ab935c1eb21b19517d3eeecc7d0b42`
- profile: `consumer`
- specialist domain: empty
- escalation: none
- max developer attempts: 1

Authorized paths, exactly:

1. `knowledge/company_os/capsules/seeds/company-engineering-execution.json`
2. `tests/test_company_os_capsules.py`

Required tests:

1. `tests/test_company_engineering_execution.py`
2. `tests/test_company_os_capsules.py`

## Runner doctor

Dedicated benchmark runner state:

`project-factory-runner-state/token-efficiency-v4-p2-benchmark`

Dedicated benchmark worktree root:

`project-factory-benchmark-worktrees/token-efficiency-v4-p2`

Doctor result: exit 0.

Backend:

- Claude Code available
- version 2.1.70
- developer backend: claude_code
- reviewer backend: claude_code
- standard model alias: sonnet
- strongest model alias: opus
- resource strategy enabled
- push enabled

Repository observed by runner:

- detached HEAD at exact P2 commit
- shared git common directory is the canonical Simulation Factory repository

## Resource exposure before launch

Consumer profile:

- one developer attempt
- one reviewer pass
- one session at a time
- standard model tier for routine work
- 1,800 second session wall ceiling
- advisory 40-turn ceiling
- advisory 1,000,000 cache-read ceiling
- nominal USD 3.00 provider cost-stop threshold per session
- four-stage job ceiling

Runner config retains one structured-report repair slot per model stage. P0 makes provider/backend stops terminal to automatic repair, but a successful session with malformed structured output may use one bounded repair session. Therefore the intended paid shape is one developer plus one reviewer; the theoretical report-format repair shape is at most two provider subprocesses in either model stage.

## Decision

The real job is eligible for one controlled `run-one` invocation.

Do not start a watcher in parallel. Do not run a second `run-one` automatically if this one stops. Preserve every numbered session artifact and inspect them before any correction or CEO decision.

No canonical merge, deployment, publishing or production integration is authorized.
