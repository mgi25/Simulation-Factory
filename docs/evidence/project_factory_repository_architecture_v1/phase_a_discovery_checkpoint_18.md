# Phase A Discovery Checkpoint 18 — P2 correction real-job preflight

Date: 2026-09-21

The bounded correction work order has been opened in the real Repository Architecture V1 state.

## Persisted correction job

- work order: `wo-token-efficiency-v4-p2-benchmark-contract-correction`
- state: `planning`
- developer attempts: 0
- work-order fingerprint: `396b138eac4f4dde`
- plan fingerprint: `a065bbd014c45615`
- authorized branch: `eng-token-efficiency-v4-p2-benchmark-contract-correction`
- correction base: `287d690b7bf87c988edb3eb34d1f57a4dcec5ab1`
- resource profile: `consumer`
- specialist domain: empty
- required test: `tests/test_company_engineering_execution.py`
- authorized writable path, exactly: `tests/test_company_engineering_execution.py`

The runner checkout itself remains detached at validated P2 commit `619b2a0374ab935c1eb21b19517d3eeecc7d0b42`. This is intentional: runner code executes from validated P2 while its workspace layer creates the authorized correction worktree from the worker base commit above.

## Runner doctor

Doctor exit: 0.

Backend:

- Claude Code 2.1.70 available
- developer/reviewer backend: claude_code
- standard model alias: sonnet
- resource strategy enabled
- push enabled

Dedicated correction runner state:

`project-factory-runner-state/token-efficiency-v4-p2-correction`

Dedicated correction worktree root:

`project-factory-benchmark-worktrees/token-efficiency-v4-p2-correction`

No correction worker branch existed on the remote at preflight time; the runner may create and push it if the bounded implementation succeeds.

## Decision

The correction is eligible for exactly one `run-one` invocation.

Do not start a watcher in parallel. Do not automatically invoke a second run if the correction stops. Preserve and inspect numbered provider-session evidence before any further action.

After a successful correction, independently validate:

1. `tests/test_company_engineering_execution.py`
2. `tests/test_company_os_capsules.py`
3. `tests/test_company_review_separation.py`
4. all 11 required Company OS suites
5. integration gate READY with zero blockers

No canonical merge, deployment, publishing or production integration is authorized.
