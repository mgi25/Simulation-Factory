# Simulation Factory Company OS

The `company/` tree is the control plane for Simulation Factory.

It may inspect, plan, validate, route work to, and report on production systems.
Production systems MUST NOT depend on `company/`.

## Bootstrap operating mode

- Human owner = CEO.
- No subagents, child agents, worker swarms, or nested agent spawning.
- One invoked session performs its assigned task directly.
- Specialists may be invoked sequentially by a top-level workflow using compact handoff artifacts.
- Independent top-level tasks with isolated ownership may run concurrently.
- Prefer deterministic software over LLM reasoning.
- Retrieve known facts instead of rediscovering them.
- Supply minimum relevant context.
- Optimize total resources per accepted result, not raw token count.
- New roles are dormant until needed and must pass evaluation before production authority.
- Existing Race/Fight/V30 development remains independent until Company OS reaches its integration gate.

## Dependency rule

Allowed:
`company -> production systems`

Forbidden:
`production systems -> company`

Company OS must be removable without preventing simulation, rendering, tests, or existing production workflows from operating.

## Initial directories

- `org_registry.yaml` — workforce source of truth.
- `permissions.yaml` — autonomy and CEO-reserved decisions.
- `agent_contract.schema.yaml` — minimum contract for every employee.
- `task_handoff.schema.yaml` — compact inter-role artifact.
- `constitution.md` — non-negotiable operating principles.
- `WORKSTREAMS.md` — parallel development ownership.
