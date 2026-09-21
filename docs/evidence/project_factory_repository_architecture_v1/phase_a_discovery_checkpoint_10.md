# Phase A Discovery Checkpoint 10 — P1 measured startup surface

Date: 2026-09-21

A deliberately tiny paid Claude Code probe was run against the validated P1 implementation. It was not a Company OS work order and did not use `run-one`.

## Probe contract

The probe:

- used Claude Code 2.1.70;
- selected `claude-sonnet-4-6`;
- exposed the seven normal developer built-in tools through both `--tools` and `--allowedTools`;
- used strict empty MCP configuration;
- set `ENABLE_CLAUDEAI_MCP_SERVERS=false`;
- requested no tool calls, file inspection or repository modification;
- used `--max-budget-usd 0.10`;
- asked for the exact text `OK`.

## Observed system/init

Actual built-in tools:

- Bash
- Glob
- Grep
- Read
- Edit
- Write
- TodoWrite

MCP servers: **0**

Plugins: **0**

The init event still named six skills and four agent definitions, plus slash-command names. However, neither `Skill` nor `Task` was present in the actual available tool array. P1 therefore succeeded at eliminating those callable tool schemas from this session; the remaining names are treated as startup metadata until measured otherwise.

## Provider usage

The model made zero tool calls and the worktree remained unchanged.

Provider result:

- turns: **1**
- total cost: **USD 0.11184**
- model input: **3**
- model output: **4**
- cache read: **0**
- cache creation: **17,876**

The result subtype was `error_max_budget_usd` even though the assistant had already emitted `OK`. The requested budget ceiling was USD 0.10 but the completed first turn cost USD 0.11184.

This confirms an important resource-control property: `--max-budget-usd` is enforced at a provider/turn boundary and can overshoot the requested value. It must not be described as a penny-exact hard cap. P0 remains necessary because a budget stop must be terminal to automatic paid repair.

## Before/after startup surface

Historical pre-P1 session:

- broad built-in tool surface including ToolSearch, Skill, planning/worktree/notebook/user-question tools;
- eight Claude Docs MCP tools from one connected claude.ai MCP server;
- first observed tool call was ToolSearch.

Measured P1 probe:

- exactly seven requested built-in tools;
- zero MCP servers;
- zero plugins;
- zero tool calls.

Therefore P1 has achieved its primary startup-isolation objective.

## Encoding note

The local probe transcript was captured through Windows PowerShell `Tee-Object`, which wrote a UTF-16 BOM. A follow-up Python parser forced UTF-8 and raised `UnicodeDecodeError`. The visible stream-json output and provider result were unaffected. Future local parsers should detect BOMs or capture explicitly as UTF-8.

## Decision

P1 startup isolation is empirically verified.

The next optimization work should focus on the remaining measured cost drivers rather than further speculative MCP installation:

1. startup/context floor (17,876 cache-creation tokens for a one-turn no-tool probe);
2. turn multiplication in real engineering work;
3. deterministic testing outside the model loop;
4. compact semantic context and read/search reduction.

No canonical merge, production integration, deployment or publishing is authorized.
