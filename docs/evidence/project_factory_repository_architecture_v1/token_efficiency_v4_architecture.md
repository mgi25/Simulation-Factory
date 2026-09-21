# Agent Context and Token Efficiency V4

Date: 2026-09-21  
Parent program: Repository Architecture V1  
Status: blocking sub-phase; paid Company OS Claude runs frozen until P0 passes.

## Why this phase exists

Repository Architecture V1 originally treated AI efficiency as a combination of model routing, bounded context, repository navigation, attempt limits, and telemetry. Those controls remain useful, but the V2 planning-test ownership run exposed a lower-level execution defect.

One Company OS developer attempt contained two paid Claude subprocesses:

| session | outcome | cost USD | cache read | cache create | output |
|---|---|---:|---:|---:|---:|
| developer session-1 | error_max_budget_usd | 3.0339530 | 1,917,651 | 85,218 | 61,693 |
| developer session-2 | success | 0.4383165 | 194,273 | 39,252 | 3,832 |
| **developer total** | | **3.4722695** | **2,111,924** | **124,470** | **65,525** |

The normal efficiency report surfaced the successful later session rather than the full paid stage. The reviewer subsequently added further model usage. This explains why provider-plan consumption could be materially larger than the prior report implied.

The first session also exposed a broad Claude startup surface in system/init: built-in tools beyond the intended worker set, ToolSearch and Skill surfaces, and the connected claude.ai Claude Docs MCP server. The runner uses --allowedTools, which controls permission, but does not currently use --tools to make the unused built-in tools unavailable.

## Confirmed P0 defects

### 1. Internal repair sessions are paid sessions

`EngineeringRunner._session_with_report` permits one internal report-repair retry. A Company OS developer attempt is therefore not equivalent to one provider model session.

Resource policy and telemetry must account for the actual provider subprocess boundary.

### 2. Repair loses the provider cost ceiling

The initial developer SessionRequest includes:

`max_cost=applied["applied_cost_ceiling"]`

The repair SessionRequest reconstructs most fields but omits `max_cost`. SessionRequest defaults `max_cost` to `0.0`, which means no provider ceiling is passed.

A budget-stopped session can therefore be followed by an automatically launched repair session whose provider spend is not capped by the original ceiling.

### 3. Generic telemetry is last-session-wins

Each internal session is preserved as `session-N.json` and `session-N.transcript.txt`, but the same loop also rewrites:

- `session.json`
- `exploration.json`

A later repair therefore replaces the generic stage view. Receipt construction and exploration reporting can consequently describe only the final internal session while an earlier paid session remains present but unaggregated.

### 4. Permission restriction is not context restriction

The observed Claude system/init exposed substantially more tools than the worker intended, plus an unrelated connected MCP server. V4 will distinguish:

- what tools exist in model context;
- what tools are permitted to execute;
- which MCP/customization surfaces load at startup.

Company OS should be the worker's context authority.

## Target execution architecture

```text
Company OS immutable work order
          |
          v
deterministic preflight/compiler
  - authority and exact writable paths
  - exact relevant files/symbols/tests
  - bounded context evidence
          |
          v
isolated Claude developer
  - exact available tool set
  - no unrelated MCP/customizations
  - provider spend ceiling
  - hard turn ceiling where supported
  - one paid session by default
          |
          v
deterministic runner validation
  - scope/diff checks
  - required tests
  - dependency checks
          |
      pass|fail
          |  +-- fail -> compact evidence -> explicit bounded correction decision
          v
independent isolated reviewer
  - exact diff
  - acceptance criteria
  - deterministic evidence
          |
          v
full integration gate
          |
          v
CEO decision
```

## Implementation sequence

### P0A — truthful session accounting

Change the evidence model so every `session-N` subprocess contributes to stage totals. Preserve individual evidence and add an aggregate rather than relying on a mutable last-session alias.

Required aggregate dimensions:

- paid session count;
- provider cost;
- input units;
- cache-read units;
- cache-creation units;
- output units;
- model turns when reliable;
- reliability flags;
- provider stop reasons;
- exploration/tool-call totals where compatible.

Never turn an unavailable value into zero.

### P0B — repair/budget semantics

A provider resource stop is not a malformed report and must not automatically trigger report repair.

For any explicitly authorized repair:

- copy or tighten `max_cost`;
- copy or tighten timeout;
- preserve model/tool restrictions;
- record the second paid session before launch;
- make stage-total budget semantics explicit.

A budget-stop should checkpoint/escalate, not silently spend again.

### P0C — regression tests

Add deterministic tests that construct the historical shape:

1. first backend session returns `error_max_budget_usd`;
2. report is absent/invalid;
3. old behavior would launch session 2;
4. new behavior stops without a second backend launch.

Add a second fixture for a legitimate report-format repair and assert every resource ceiling is preserved and both sessions are aggregated if that repair is explicitly permitted.

No live Claude call is required for P0 tests.

### P1 — startup isolation and true tool minimization

After P0 is accepted, pin/probe a current Claude Code binary and record supported flags.

Then test, one lever at a time:

1. isolated/safe startup after auditing required instructions;
2. `--tools` exact worker tool set;
3. `--allowedTools` exact permission set;
4. `--strict-mcp-config` with no unrelated MCP servers;
5. no unnecessary skills/plugins/auto-memory/project customization.

Do not replace the default Claude system prompt until the cheaper isolation controls have been measured.

### P2 — turn and live-resource controls

Where supported, impose a hard `--max-turns` circuit breaker derived from the resource profile. A turn limit is a stop/escalation mechanism, never permission to accept incomplete work.

Only after static controls are measured should the subprocess boundary be changed to consume stream-json incrementally for live resource enforcement.

### P3 — deterministic testing boundary

Move routine deterministic validation out of the model loop:

Claude edits -> runner runs required tests -> pass proceeds; failure is reduced to bounded, failure-relevant evidence before an explicit correction.

This reduces paid shell/test round trips without weakening tests.

### P4 — semantic context compiler

Evolve the current AST map rather than immediately adding an always-on MCP.

Candidate design:

- seed authorized/changed paths and symbols named in the objective/criteria;
- build local symbol/import/reverse-import/test-reference relationships;
- rank by deterministic weighted graph or personalized PageRank;
- emit exact symbol slices under an actual token budget;
- use structural search/LSP/tree-sitter only when the repository language/task shape justifies it.

External tools such as Aider-style repo-map ranking, ast-grep, Serena or RTK are experiments, not defaults. Prefer local preprocessing that does not add tool schemas to every Claude turn.

### P5 — reviewer efficiency

Reviewer independence remains mandatory. Reduce only redundant context:

- exact diff;
- exact criteria;
- deterministic test/gate evidence;
- bounded blast-radius/context references;
- minimal read-only tool set.

## Non-goals

V4 does not:

- remove independent review to save tokens;
- skip required deterministic tests or the integration gate;
- downgrade authority checks;
- merge to main;
- deploy or publish;
- activate new workforce roles;
- install a suite of MCP servers speculatively;
- optimize a headline prompt-size number while increasing total job resources.

## Exit condition

V4 exits the blocking phase only after P0 is deterministically green and the benchmark protocol records a trustworthy baseline. Paid matched experiments may then proceed sequentially under CEO control.
