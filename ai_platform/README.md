# AI Platform — Bootstrap Contract

The AI platform exists to deliver the highest accepted output quality with the minimum practical reasoning/context/tool cost.

## Hard constraint

**No subagents in Bootstrap Mode.**

A Codex, Claude Code, ChatGPT, or other agent session must execute its own bounded task. It may not spawn helper agents, child agents, swarms, or nested delegations.

When multiple perspectives are required, the orchestrating workflow invokes separate sessions sequentially and passes compact artifacts between them.

## Decision order

1. Can deterministic software do it?
2. Is the answer already in canonical knowledge/cache?
3. Can a bounded low-reasoning pass do it?
4. Is a specialist reasoning pass required?
5. Is deep reasoning justified by risk/value?
6. Only for rare major decisions: invoke multiple independent reviewers sequentially.

## Context policy

Each request should contain only:

- objective,
- relevant module contract,
- relevant files/diff,
- relevant tests/benchmarks,
- relevant current decision/experiment evidence,
- explicit constraints and acceptance criteria.

Never load the full company/repository history by default.

## Efficiency metrics

- resources per accepted deliverable,
- first-pass success,
- retries,
- duplicated context,
- cache/retrieval hit rate,
- unnecessary tool calls,
- rejected output cost,
- context supplied but unused.

## Future components

- task classifier/router,
- context compiler,
- knowledge retrieval/cache,
- resource telemetry,
- budget enforcement,
- employee evaluator,
- structured artifact validator.

Bootstrap implementation should stay provider-agnostic. Paid APIs are optional capacity, not an architectural requirement.
