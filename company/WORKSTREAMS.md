# Company OS v1 — Parallel Workstreams

Base branch: `company-os-v1-bootstrap`

Race/V30 development continues on its own branches. Do not merge Company OS into those branches during bootstrap.

## Global rules for every coding session

- NO SUBAGENTS.
- No child-agent spawning.
- No autonomous parallel workers.
- Minimum relevant context only.
- Deterministic code before LLM logic.
- Small coherent diffs.
- Do not refactor production systems unless the assigned task explicitly requires an interface.
- Run focused tests before broad tests.
- End with a compact handoff.

## Workstream A — Codex: Core Company Runtime

Suggested branch: `company-os-v1-core-runtime`

Own initially:
- `company/runtime/`
- `company/validation/`
- focused tests for company contracts

First target:
1. Load/validate org_registry, permissions, agent contract, and handoff artifacts.
2. Reject any employee contract with `no_subagents != true` in Bootstrap Mode.
3. Resolve employee capability → eligible roles without invoking an LLM.
4. Keep dependencies standard-library-first unless clearly justified.
5. Provide small deterministic CLI/tests.

Do not edit production Race/Fight/Godot paths.

## Workstream B — Claude Code: AI Efficiency + Knowledge Primitives

Suggested branch: `company-os-v1-ai-efficiency`

Own initially:
- `ai_platform/` except README
- `knowledge/company_os/`
- focused tests for AI-efficiency/knowledge primitives

First target:
1. Define task complexity/budget classes without provider-specific model names.
2. Implement context-manifest structures (references to relevant files/facts, not full repo dumps).
3. Implement deterministic resource-usage record structures.
4. Implement fact/hypothesis/decision knowledge records with freshness/recheck metadata.
5. Enforce no nested-agent/subagent execution in config/contracts.

Do not edit production Race/Fight/Godot paths.

## Integration

Only the bootstrap integration branch should modify shared root contracts:
- `company/org_registry.yaml`
- `company/permissions.yaml`
- `company/*.schema.yaml`
- `company/constitution.md`

Workstreams submit compact handoffs containing:
- objective
- files changed
- tests
- invariants preserved
- risks
- resource notes
- recommended next integration step
