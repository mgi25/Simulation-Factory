# Phase A Discovery Checkpoint 08 — P1 startup isolation static validation

Date: 2026-09-21

## Implementation

Token Efficiency V4 P1 is implemented on:

- branch: `project-factory-token-efficiency-v4-p1`
- commit: `41b7f6df5fda38578c553db1114bdca2a2afb8d1`

It begins directly from the validated P0 implementation.

## Controls added

P1 distinguishes tool availability from tool permission.

Claude Code receives the Company OS worker tool contract through:

- `--tools`: built-in tools exposed to the model;
- `--allowedTools`: tools permitted to execute.

The backend also launches with:

- `--strict-mcp-config`;
- an explicit empty MCP configuration;
- `ENABLE_CLAUDEAI_MCP_SERVERS=false` in the runner-created Claude subprocess environment only.

The latter is necessary because a live no-model CLI probe established that Claude Code 2.1.70 still connected the account-managed `claude.ai Claude Docs` server when only strict empty MCP configuration was supplied.

With `ENABLE_CLAUDEAI_MCP_SERVERS=false`, the same probe returned:

`No MCP servers configured.`

P1 additionally preserves bounded `system/init` startup evidence in each Claude session record:

- model;
- permission mode;
- exposed tool names;
- MCP server names/status;
- plugin names;
- skill names.

This allows the first controlled model experiment to prove the actual startup surface rather than infer it from command-line arguments.

## Deterministic validation

At exact P1 commit `41b7f6df5fda38578c553db1114bdca2a2afb8d1`:

- compileall: PASS;
- focused runner/engineering pytest selection: **419 passed / 0 failed** in 104.24 seconds;
- model calls used: **0**.

## Installed Claude Code capability probe

Installed CLI:

`2.1.70 (Claude Code)`

Its actual `--help` exposes:

- `--allowedTools`;
- `--disallowedTools`;
- `--mcp-config`;
- `--strict-mcp-config`;
- `--tools`.

It does **not** expose `--max-turns` or `--safe-mode`. V4 therefore will not assume those controls exist on this binary. A CLI upgrade, if evaluated later, is a separate measured experiment.

## Current decision

P1 static controls are green, but no paid benchmark is authorized yet.

Before any model invocation, run the 11 required Company OS suites and integration readiness gate at the exact P1 commit. Only if those remain green may V4 perform a tiny, bounded startup-surface model probe to inspect the real `system/init` surface.

No `run-one` engineering job is authorized by this checkpoint.
