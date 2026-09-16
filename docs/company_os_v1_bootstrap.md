# Company OS v1 — Bootstrap Development Specification

## Goal

Introduce the corporate control plane for Simulation Factory while Race/Fight/V30 development continues independently.

Company OS is developed in parallel and is **not connected to production execution until its integration gate passes**.

## v1 scope

### Foundation
- constitution
- org registry
- permissions/autonomy
- employee contract
- compact handoff contract
- no-subagent policy

### AI efficiency
- deterministic-first task policy
- minimum-relevant-context compiler
- retrieval/cache before reasoning
- resource telemetry
- budget classes
- provider-agnostic execution contracts

### Engineering governance
- module capsules
- architecture ownership
- test/benchmark registry
- technical-debt and organizational-debt ledgers
- AI-code-readability checks

### Research
- YouTube/trend/reference discovery
- opportunity dossier
- research confidence/freshness
- originality review
- reference superiority contract

### Content lifecycle
- Video Intelligence Dossier
- format portfolio: Race, Fight, future formats
- experiment definition
- production/QC
- postmortem
- learning promotion

### Organization
- capability graph
- capability-gap detection
- hire proposal
- agent builder/evaluation
- shadow/probation/active/dormant/archive lifecycle
- employee performance evidence

### Corporate improvement
- workflow review
- role overlap/redundancy review
- resource-efficiency audit
- technology radar
- company versioning/rollback

## Not in early bootstrap

- always-on autonomous swarms
- subagents
- automatic public publishing
- automatic large paid API spend
- uncontrolled employee creation
- engine migration
- broad refactor of existing Race/Fight/V30 code
- production modules importing company code

## Development sequence

1. Contracts and invariants.
2. Validation/tests for those contracts.
3. AI resource telemetry + context compiler.
4. Knowledge/decision primitives.
5. Engineering module capsules.
6. Research/opportunity pipeline.
7. Video dossier/experiment/postmortem pipeline.
8. Dynamic workforce.
9. CEO dashboard.
10. Integration gate with existing production.

## Integration gate

Company OS may be introduced into normal production workflow only when:

- existing Race/Fight workflows remain independently runnable,
- no production module depends on Company OS,
- no-subagent enforcement exists in development/employee contracts,
- task/handoff validation works,
- bounded context assembly works,
- resource telemetry works,
- org/permission validation works,
- tests pass,
- rollback is documented,
- CEO approves the integration.

## Performance philosophy

Do not optimize for "fewest tokens" in isolation.
Optimize total resources per accepted result.

A slightly larger single correct pass is preferred over repeated short failed passes.

## Parallel development rule

Parallel developers must own non-overlapping paths or work on separate branches/worktrees. Shared schemas/contracts are changed only through the bootstrap integration branch and reviewed before downstream work rebases.
