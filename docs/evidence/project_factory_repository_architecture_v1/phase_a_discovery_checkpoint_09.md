# Phase A Discovery Checkpoint 09 — Token Efficiency V4 P1 accepted

Date: 2026-09-21

P1 startup/context isolation is validated at commit:

`41b7f6df5fda38578c553db1114bdca2a2afb8d1`

## Validation

Focused deterministic validation:

- compileall: PASS
- focused pytest: **419 passed / 0 failed**
- model calls: **0**

Required Company OS suites:

- **11/11 green**
- suite exit code: **0**

Integration gate:

- report: `integration-readiness-2026-09-21-f842cafb8199d185`
- source commit: `41b7f6df5fda38578c553db1114bdca2a2afb8d1`
- blockers: **0**
- exit code: **0 / READY**
- production integration authorized: **false**

## MCP isolation finding

Claude Code 2.1.70 does not remove the account-managed `claude.ai Claude Docs` MCP server merely by combining an empty `--mcp-config` with `--strict-mcp-config`.

With runner-local environment variable:

`ENABLE_CLAUDEAI_MCP_SERVERS=false`

the same no-model CLI probe returned:

`No MCP servers configured.`

The variable is set only in Project Factory runner-launched Claude subprocesses, so normal interactive Claude usage is unaffected.

## P1 accepted controls

The validated P1 launcher now:

1. passes Company OS worker tools through `--tools` to restrict actual built-in tool availability;
2. independently passes the same contract through `--allowedTools` for permission;
3. uses strict empty configured MCP state;
4. opts out of account-injected Claude.ai MCP servers;
5. records bounded `system/init` startup evidence so the first paid experiment can prove the actual surface.

## Next experiment

P1 is eligible for exactly one tiny provider-capped startup-surface probe.

The probe is not a Company OS work order and not `run-one`. It must:

- make no repository edit;
- ask the model not to use tools;
- expose the normal bounded developer tool list so `system/init` can be inspected;
- use the strict/empty MCP controls and account-MCP opt-out;
- use a small provider cost ceiling;
- preserve the raw stream-json transcript locally;
- report actual tools, MCP servers, plugins, skills and provider usage.

Only after that evidence is read may a matched engineering benchmark be authorized.

No canonical merge, deployment, publishing or production integration is authorized.
