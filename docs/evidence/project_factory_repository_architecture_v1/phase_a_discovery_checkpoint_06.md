# Phase A Discovery Checkpoint 06 — Hidden Claude session spend and Token Efficiency V4

Date: 2026-09-21

## Trigger

After work order `wo-delegation-planning-test-ownership-v2` reached `ready_for_approval`, the operator observed that the run appeared to consume roughly 8% of the Claude Team-plan allowance. That observation did not fit the initial efficiency report, which showed only the final successful developer session.

A zero-model forensic audit of preserved runner artifacts identified the discrepancy.

## Preserved developer sessions

`developer-01/session-1.json`:

- ok: false
- stopped_reason: `error_max_budget_usd`
- provider cost: USD 3.0339530000000003
- cache read: 1,917,651
- cache creation: 85,218
- output: 61,693
- usage source: model usage totals; turn count unreliable after segment mismatch

`developer-01/session-2.json`:

- ok: true
- provider cost: USD 0.4383165
- cache read: 194,273
- cache creation: 39,252
- output: 3,832
- turns: 8

Aggregate developer stage:

- paid sessions: 2
- provider cost: USD 3.4722695
- cache read: 2,111,924
- cache creation: 124,470
- output: 65,525

The prior efficiency summary represented the later successful session and therefore materially understated the paid developer stage.

## Root cause confirmed from runner source

`EngineeringRunner._session_with_report` permits one structured-report repair retry.

For every internal session it preserves `session-N.json` and `session-N.transcript.txt`, but also rewrites generic `session.json` and `exploration.json`. Downstream stage-level measurement can therefore become last-session-wins.

The initial developer request receives `max_cost=applied["applied_cost_ceiling"]`.

The repair SessionRequest omits `max_cost`. `SessionRequest.max_cost` defaults to `0.0`, documented as no provider ceiling.

Therefore a session that already stopped at the provider budget ceiling can enter report-repair handling, and a repair request can be created without the original provider spend ceiling.

## Startup-context finding

The first preserved transcript's Claude system/init reported:

- model `claude-sonnet-4-6`
- permission mode `acceptEdits`
- a broad built-in tool surface beyond the runner's intended developer set
- connected MCP server `claude.ai Claude Docs` exposing eight MCP tools
- six skills
- first observed tool call: `ToolSearch`

The local CLI help distinguishes `--tools` (available built-in tool set) from `--allowedTools` (permission allowlist) and exposes `--strict-mcp-config`.

This establishes that permission restriction alone is not sufficient to minimize worker startup/tool context.

## Decision

Repository Architecture V1 enters blocking sub-phase **Agent Context and Token Efficiency V4**.

Until P0 passes deterministically:

- do not launch another paid Company OS Claude `run-one`;
- keep the V2 metadata work order frozen at `ready_for_approval`;
- keep the old lifecycle-history work order blocked;
- do not merge the rejected V1 metadata worker;
- do not change canonical main.

P0 priority:

1. truthful aggregation of every provider subprocess;
2. no automatic paid repair after a provider budget stop;
3. preserved/tightened ceilings on any explicitly authorized repair;
4. regression tests reproducing the historical failure shape.

Only after P0 should startup isolation, actual tool restriction, turn ceilings, deterministic external testing, live resource controls, and semantic context improvements be benchmarked.

## Relationship to prior efficiency findings

Earlier Repository Exploration Efficiency work remains valid as evidence that repository discovery can be improved, but any historical stage-level result that could contain multiple internal `session-N` files must be re-audited before being used as a total-cost benchmark.

No prior immutable evidence is deleted or rewritten. This checkpoint supersedes only the interpretation that a final stage session necessarily represented the full provider spend of that stage.
