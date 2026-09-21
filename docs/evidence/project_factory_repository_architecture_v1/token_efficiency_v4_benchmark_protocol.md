# Token Efficiency V4 Benchmark Protocol

Date: 2026-09-21  
Frozen before post-P0 paid optimization experiments.

## Objective

Measure total provider resources per **accepted, independently reviewed, integration-ready outcome**. Do not optimize prompt length or one successful internal session in isolation.

## Baseline evidence

The historical V2 planning-test ownership developer stage is a pathology baseline because its full internal session evidence is preserved.

Known developer totals:

- paid sessions: 2
- provider cost: USD 3.4722695
- cache read: 2,111,924
- cache creation: 124,470
- output: 65,525
- first session stop: error_max_budget_usd

The first session's exact unique/repeated repository-path counts are not frozen as authoritative because one diagnostic reparse used the operator checkout rather than the worker worktree for path normalization. Raw total tool-call count remains observable from the transcript.

The user-observed Claude Team-plan change of approximately 8% is contextual evidence, not a calibrated metric: the provider does not publish a simple conversion from the runner's API-equivalent USD field to the Team usage percentage.

## Quality constraints

Every matched experiment must preserve:

1. identical objective and acceptance criteria;
2. identical authority/path ceiling;
3. independent reviewer;
4. required deterministic tests;
5. full integration gate;
6. no subagents;
7. no automatic merge/deploy/publish;
8. no accepted outcome with unanswered criteria or blocking review finding.

A run that saves resources by failing quality is not an efficiency win.

## Required measurements

Per provider subprocess:

- session ID and role;
- model;
- stop reason;
- reliable model turns;
- input units;
- cache-read units;
- cache-creation units;
- output units;
- provider cost;
- available tool names from system/init where observable;
- connected MCP servers/plugins/skills where observable;
- file reads/searches/tool calls;
- test/shell commands.

Per stage and job:

- paid session count;
- aggregate resources across all subprocesses;
- retries/repairs and why they occurred;
- changed paths;
- tests;
- reviewer outcome/findings;
- integration readiness;
- actual Team-plan percentage before/after when the operator can observe it.

Unavailable values remain unavailable.

## Experiment order

Do not bundle multiple unmeasured mechanisms.

- E0: P0 accounting/retry correction; deterministic tests only, no paid benchmark required.
- E1: current/pinned Claude Code version with truthful accounting, otherwise unchanged.
- E2: startup isolation only.
- E3: exact --tools availability restriction and MCP isolation.
- E4: hard turn ceiling.
- E5: deterministic external test execution with compact failure evidence.
- E6: live stream resource guard if previous evidence justifies it.
- E7: semantic context compiler/ranking.
- E8: optional external preprocessing tools only for remaining measured gaps.

Proceed sequentially. One matched real task is sufficient to continue only when the direction is clear and quality is unchanged; otherwise repeat once. Do not run three samples by default when one or two already answer the question.

## Decision metrics

Primary:
- total provider/model resource consumption per accepted verified outcome;
- actual subscription-plan impact when observable.

Secondary:
- developer/reviewer turns;
- cache read/create;
- output;
- paid session count;
- unnecessary searches/repeated reads/tool calls;
- wall time.

Quality:
- acceptance criteria;
- review findings;
- deterministic test result;
- integration gate;
- escaped defect evidence if any.

## Stop rules

Stop an experiment immediately when:

- authority or protected-path behavior changes unexpectedly;
- a provider resource stop would cause automatic hidden spend;
- the quality chain regresses;
- telemetry cannot account for every paid subprocess;
- an external tool increases startup/tool-schema context without a compensating measured reduction.

The benchmark does not authorize canonical merge or production deployment.
