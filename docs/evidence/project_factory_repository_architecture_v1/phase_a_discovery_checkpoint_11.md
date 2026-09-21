# Phase A Discovery Checkpoint 11 — P2 runner-owned validation static check

Date: 2026-09-21

Token Efficiency V4 P2 is implemented on branch `project-factory-token-efficiency-v4-p2` at commit:

`619b2a0374ab935c1eb21b19517d3eeecc7d0b42`

P2 begins directly from the validated P1 implementation.

## Purpose

The historical high-cost developer session showed extensive turn multiplication. One confirmed duplication was that the developer brief instructed Claude to run the work order's deterministic tests itself and iterate until they passed, while the runner already executed the same required tests after the implementation commit.

P2 removes that duplication for the default consumer profile.

## Consumer execution boundary

Consumer developer sessions now expose:

- Read
- Write
- Edit
- Glob
- Grep

They do not expose:

- Bash
- TodoWrite

Required test commands remain in the briefing as acceptance evidence, but the briefing explicitly says the model must not execute them. The runner remains the deterministic validation owner and runs every required test after committing the model's bounded implementation.

Expanded/non-consumer work keeps the existing operator-configured developer tool surface, including Bash when configured. This preserves specialist implementation capability while reducing routine turn multiplication.

The applied boundary is persisted in `resources.json`:

- `available_tools`
- `deterministic_validation_owner: runner`
- `model_runs_required_tests: false`

## Focused deterministic validation

At exact P2 commit `619b2a0374ab935c1eb21b19517d3eeecc7d0b42`:

- compileall: PASS
- focused pytest selection: **422 passed / 0 failed**
- duration: 137.12 seconds
- model calls: **0**

The tests pin:

1. consumer removal of Bash/TodoWrite;
2. expanded preservation of shell capability;
3. monotonic tool reduction (P2 never adds an operator-removed tool);
4. required test visibility without model execution;
5. resources.json evidence of the applied boundary.

## Current decision

P2 static controls are green.

Before any paid benchmark, run the canonical 11 required Company OS suites and the integration readiness gate at the exact P2 commit. Only if those remain green may a controlled matched engineering benchmark be considered.

No canonical merge, production integration, deployment or publishing is authorized.
