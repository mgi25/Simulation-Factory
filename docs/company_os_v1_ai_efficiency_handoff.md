# Handoff — Company OS v1, Workstream B (AI efficiency + knowledge primitives)

Shaped by `company/task_handoff.schema.yaml`. Everything an integration session
needs is here; no prior conversation is required.

```yaml
task_id: company-os-v1-ai-efficiency-phase-1
owner: ai_efficiency_platform_engineer
objective: >
  Build the minimum deterministic primitives that make future agent sessions
  token- and context-efficient: provider-agnostic task classes, a reference-only
  context manifest, a usage record that survives missing token counts, five
  knowledge record types with a decay model, a decision ledger, and no-subagent
  enforcement.
status: complete
next_owner: chief_architect (integration branch)
escalation:
  required: false
```

## What was built

| Module | Does |
|---|---|
| `ai_platform/resource_classes.py` | Classes A–F as capability requirements; `classify()` — a pure, total function over `TaskSignals` with an ordered rule tuple |
| `ai_platform/context_manifest.py` | `ContextRef` / `ContextManifest`: what a session is handed, as pointers with a measurable footprint |
| `ai_platform/usage.py` | `ResourceUsageRecord`, `UsageLedger`, `ResourceSummary` — telemetry that degrades to passes when a provider exposes no token counts |
| `ai_platform/policy.py` | `ExecutionPolicy`, `BOOTSTRAP_POLICY` — the two-key lock on nested agents |
| `ai_platform/references.py` | `assert_reference` — one guard that refuses content in a pointer field |
| `ai_platform/serde.py` | Canonical JSON: sorted keys, stable bytes, short fingerprints |
| `knowledge/company_os/records.py` | `Fact`, `Hypothesis`, `Decision`, `ExperimentLearning`, `FailureLearning` + `promote()` |
| `knowledge/company_os/freshness.py` | Four decay classes, staleness arithmetic, `today` always injected |
| `knowledge/company_os/ledger.py` | `KnowledgeStore` (a directory of JSON files) and `DecisionLedger` |

## Architecture in six lines

- A task gets a **class** (A–F) from deterministic signals, and the class sets a
  context-ref ceiling, a pass ceiling and whether evidence is required.
- It gets a **manifest** of references — never file contents — that validates
  against that ceiling and fingerprints stably for cache lookup.
- It produces a **usage record** keyed to the same `task_id`, carrying what we
  observe ourselves (passes, retries, rejections, cache hits) and whatever the
  provider happened to expose.
- Durable conclusions become **knowledge records** in a file store, with a
  decay class that makes "is this still true?" answerable.
- **Decisions** carry their own rollback and reconsideration conditions, and
  keep them through every status transition.
- Dependency direction: `knowledge.company_os → ai_platform`, and nothing
  imports production code or is imported by it.

## Invariants preserved

1. **No subagents.** `ExecutionPolicy` in bootstrap mode fixes `no_subagents`,
   `nested_agent_spawning`, `always_on_agents`, `max_concurrent_sessions` and
   `ceo_amendment`; any deviation raises at construction. Unknown config keys
   are refused, not ignored. Leaving bootstrap mode is the first key and naming
   the CEO approval is the second — neither alone opens anything. No resource
   class sets `allows_subagents`, and a usage record reporting a nested agent
   raises.
2. **Production independence.** Nothing under `ai_platform/` or
   `knowledge/` imports `race/`, `sloped/`, `marble3d/`, `engine/`, `modes/`,
   `powers/`, `godot/`, or any V30 path — and nothing there imports these.
   Deleting both trees leaves the repository running.
3. **Provider agnosticism.** No vendor or model name appears in the resource
   class table; a test asserts it. Counts are `units` with a declared
   `UsageUnit`, never `tokens`.
4. **Facts ≠ hypotheses ≠ decisions.** Five sibling types, no inheritance. A
   `Fact` with no evidence raises; `promote()` is the only crossing and demands
   a supported status plus evidence.
5. **Minimum relevant context.** A manifest holds references; embedding content
   in a `ref` is a construction error, and exceeding the class ceiling is a
   validation error.
6. **Rollback always.** `Decision` requires a `rollback` plan and at least one
   `reconsider_if`; the ledger's three transitions change `status` and add a
   reason, never rewriting what was recorded.
7. **Shared contracts untouched.** No file under `company/` was modified.

## Tests

`tests/test_company_os_ai_platform.py` (43) and
`tests/test_company_os_knowledge.py` (26).

```
69 passed in 0.19s
```

Repo-wide collection after the change: 3035 tests collected, no errors.

The seven required proofs and where they live:

| Proof | Test |
|---|---|
| Resource classes are deterministic | `test_classification_is_stable_across_repeated_calls`, `test_classification_is_a_pure_function_of_the_signal_set`, `test_rules_are_an_ordered_tuple_with_a_total_floor` |
| Manifests reference rather than embed | `test_a_ref_that_contains_content_is_refused`, `test_a_ref_longer_than_a_pointer_is_refused`, `test_manifest_stays_tiny_beside_what_it_points_at` |
| Fact and hypothesis stay distinct | `test_the_two_types_are_siblings_not_a_hierarchy`, `test_a_fact_without_evidence_is_refused_and_named_a_hypothesis`, `test_promotion_is_the_only_crossing_and_it_demands_evidence` |
| Stale time-sensitive knowledge is detectable | `test_time_sensitive_knowledge_goes_stale_and_permanent_never_does`, `test_a_sweep_finds_the_stale_records_and_orders_them_by_due_date` |
| Decision reconsideration/rollback fields retained | `test_reconsideration_retains_every_field_the_decision_recorded`, `test_rollback_retains_the_plan_it_executed` |
| Usage records work without token counts | `test_a_record_is_valid_with_no_provider_numbers_at_all`, `test_the_primary_metric_survives_missing_token_counts` |
| Bootstrap policy forbids subagents | `test_bootstrap_mode_cannot_be_relaxed_by_any_single_flag`, `test_an_unknown_config_key_is_refused_rather_than_ignored`, `test_a_usage_record_cannot_report_a_nested_agent` |

## Dependencies

None added. Standard library only — `dataclasses`, `enum`, `json`, `hashlib`,
`datetime`, `pathlib`, `re`. `requirements.txt` is unchanged. No paid API, no
agent framework, no vector store.

## Risks and open questions

1. **The classifier's signals are asserted, not measured.** `classify()` is
   deterministic given `TaskSignals`, but nothing yet checks that a caller
   filled them honestly. A caller who sets `deterministic_solution_exists=True`
   for a task that needs judgment gets class A and a wrong answer cheaply. The
   mitigation is downstream: the rule name is carried in every `Classification`
   and should be written into the usage record, so a misrouted class is visible
   in the ledger afterwards.
2. **The class constants are judgement, not measurement.** `max_context_refs`
   and `max_passes` were set from the README's intent, not from observed data.
   They are a starting calibration and should be revisited once the ledger holds
   real tasks — that is what `hypothesis/context-utilisation-predicts-retries`
   is for.
3. **`resources_per_accepted` charges every pass in the scope to the accepted
   deliverables.** That is deliberate (a rejection is a cost), but it makes the
   number sensitive to how a scope is drawn. Compare like-scoped ledgers only.
4. **Contradiction detection is declared, not derived.** `store.contradictions()`
   surfaces what an author already noticed. Finding contradictions between two
   sentences is a reasoning task and is out of scope here.
5. **No retrieval by meaning.** A session that does not know a record exists
   will not find it by id. See `decision/knowledge-store-is-files` for the
   reconsideration triggers.
6. **Overlap to confirm at integration.** Workstream A owns "reject any employee
   contract with `no_subagents != true`". This branch deliberately did not touch
   employee-contract validation — `ExecutionPolicy` governs task execution, not
   contracts. Integration should confirm the two meet and do not duplicate.

## Recommended next integration step

Wire `Classification.rule` and `ContextManifest.fingerprint()` into whatever the
core runtime uses to dispatch a task, and persist one `ResourceUsageRecord` per
task. Until a record is written per task, every efficiency metric in
`ai_platform/README.md` has a structure and no data.

## Rollback

Delete `ai_platform/*.py` (leaving `README.md`), `knowledge/`, and the two test
files. Nothing else in the repository imports them.
