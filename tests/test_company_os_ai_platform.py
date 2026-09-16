"""Focused tests for the AI platform primitives.

Seven invariants matter here, and each has a section below: classification is
deterministic, the escalation order is the one that was argued for, manifests
reference rather than embed, context budgets are enforced, usage records survive
a provider that exposes no token counts, rejections stay in the denominator, and
nothing in Bootstrap Mode can reach a nested agent.
"""

from __future__ import annotations

import itertools

import pytest

from ai_platform import (
    BOOTSTRAP_POLICY,
    RESOURCE_CLASSES,
    ContextKind,
    ContextManifest,
    ContextRef,
    ExecutionPolicy,
    Outcome,
    PolicyConfigError,
    ReasoningClass,
    ReferenceViolation,
    ResourceUsageRecord,
    Risk,
    SubagentPolicyViolation,
    TaskSignals,
    UsageLedger,
    UsageRecordError,
    UsageUnit,
    classify,
    escalate,
    resource_class,
)
from ai_platform.resource_classes import CLASS_ORDER, RULES


# --------------------------------------------------------------------------
# Resource classes are deterministic
# --------------------------------------------------------------------------


def test_every_class_is_defined_once_and_ordered():
    assert set(RESOURCE_CLASSES) == set(ReasoningClass)
    assert tuple(sorted(RESOURCE_CLASSES, key=lambda c: RESOURCE_CLASSES[c].rank)) == CLASS_ORDER
    depths = [RESOURCE_CLASSES[code].reasoning_depth for code in CLASS_ORDER]
    assert depths == sorted(depths), "cost must not decrease as the class rises"


def test_classification_is_stable_across_repeated_calls():
    signals = TaskSignals(specialist_domain="physics", risk=Risk.MEDIUM)
    first = classify(signals)
    for _ in range(256):
        again = classify(signals)
        assert again.code is first.code
        assert again.rule == first.rule


def test_classification_is_a_pure_function_of_the_signal_set():
    """Same field values, two independently built objects, one answer."""
    booleans = (False, True)
    for combo in itertools.product(booleans, repeat=6):
        (deterministic, canonical, judgment, reversible, novel, reserved) = combo
        kwargs = dict(
            deterministic_solution_exists=deterministic,
            answer_in_canonical_knowledge=canonical,
            requires_judgment=judgment,
            reversible=reversible,
            novel=novel,
            ceo_reserved=reserved,
        )
        assert classify(TaskSignals(**kwargs)).code is classify(TaskSignals(**kwargs)).code


def test_rules_are_an_ordered_tuple_with_a_total_floor():
    assert isinstance(RULES, tuple), "rule order is the policy; a mapping could reorder it"
    names = [name for name, _, _ in RULES]
    assert names[0] == "deterministic_software"
    assert names[1] == "canonical_knowledge_hit"
    assert RULES[-1][1](TaskSignals()) is True, "the last rule must match everything"
    assert RULES[-1][2] is ReasoningClass.C


def test_deterministic_and_retrieval_win_over_everything_above_them():
    """Constitution rule 4: cheap-and-exact beats expensive-and-plausible."""
    dangerous = dict(risk=Risk.CRITICAL, reversible=False, novel=True, requires_judgment=True)
    assert classify(TaskSignals(deterministic_solution_exists=True, **dangerous)).code is (
        ReasoningClass.A
    )
    assert classify(TaskSignals(answer_in_canonical_knowledge=True, **dangerous)).code is (
        ReasoningClass.B
    )


def test_high_risk_irreversible_never_routes_to_c():
    """The case the inverted rule order exists for (decision/classifier-order-inverts-below-b)."""
    signals = TaskSignals(requires_judgment=True, reversible=False, risk=Risk.HIGH)
    result = classify(signals)
    assert result.code is ReasoningClass.E
    assert result.rule == "deep_reasoning"

    assert classify(TaskSignals(risk=Risk.CRITICAL)).code is ReasoningClass.E
    assert classify(TaskSignals(risk=Risk.HIGH)).code is ReasoningClass.D
    assert classify(TaskSignals(specialist_domain="cinematography")).code is ReasoningClass.D


def test_unfilled_signals_fall_to_the_cheap_floor_not_the_expensive_one():
    result = classify(TaskSignals())
    assert result.code is ReasoningClass.C
    assert result.rule == "small_reasoning_floor"


def test_multi_perspective_is_reserved_and_sequential():
    reserved = classify(TaskSignals(ceo_reserved=True, reversible=False))
    assert reserved.code is ReasoningClass.F
    review = resource_class(ReasoningClass.F)
    assert review.independent_reviewers > 1
    assert review.reviewers_sequential is True
    assert review.allows_subagents is False


def test_escalation_walks_one_step_and_stops_at_f():
    assert escalate(ReasoningClass.A) is ReasoningClass.B
    assert escalate(ReasoningClass.D) is ReasoningClass.E
    assert escalate(ReasoningClass.F) is ReasoningClass.F


def test_no_class_names_a_provider():
    """Provider-agnostic: the table must not mention a vendor or a model."""
    banned = ("openai", "gpt", "claude", "anthropic", "gemini", "llama", "mistral", "o3")
    for cls in RESOURCE_CLASSES.values():
        haystack = f"{cls.name} {cls.intent}".lower()
        for token in banned:
            assert token not in haystack, f"{cls.code} names a provider: {token}"


# --------------------------------------------------------------------------
# Manifests reference, they do not embed
# --------------------------------------------------------------------------


def _manifest(**overrides) -> ContextManifest:
    base = dict(
        task_id="task-001",
        objective="Fix the merge apron so orange completes.",
        reasoning_class=ReasoningClass.D,
        module_contracts=(
            ContextRef(ContextKind.MODULE_CONTRACT, "sloped/README.md", "the course contract"),
        ),
        files=(ContextRef(ContextKind.FILE, "sloped/course.py", "holds the merge", (120, 180)),),
        tests=(ContextRef(ContextKind.TEST, "tests/test_sloped.py::test_merge", "the gate"),),
        acceptance_criteria=("orange completion >= 0.95 over 600 seeds",),
        constraints=("do not change the start geometry",),
    )
    base.update(overrides)
    return ContextManifest(**base)


def test_a_ref_that_contains_content_is_refused():
    pasted = "def merge(self):\n    return self.apron\n"
    with pytest.raises(ReferenceViolation, match="embedded content"):
        ContextRef(ContextKind.FILE, pasted, "pasted the function body")


def test_a_ref_longer_than_a_pointer_is_refused():
    with pytest.raises(ReferenceViolation, match="reference budget"):
        ContextRef(ContextKind.FILE, "x" * 400, "a paragraph wearing a path's clothes")


def test_a_ref_must_say_why_it_is_there():
    with pytest.raises(ReferenceViolation, match="must not be empty"):
        ContextRef(ContextKind.FILE, "sloped/course.py", "   ")


def test_manifest_stays_tiny_beside_what_it_points_at():
    """The whole request is smaller than one of the files it references."""
    manifest = _manifest()
    assert manifest.validate() == ()
    assert manifest.size_chars() < 600
    assert len(manifest.refs()) == 3


def test_duplicated_context_is_a_violation():
    duplicate = ContextRef(ContextKind.FILE, "sloped/course.py", "again")
    manifest = _manifest(
        files=(
            ContextRef(ContextKind.FILE, "sloped/course.py", "holds the merge"),
            duplicate,
        )
    )
    problems = manifest.validate()
    assert any("duplicated context" in p for p in problems)


def test_a_span_makes_a_distinct_ref_not_a_duplicate():
    manifest = _manifest(
        files=(
            ContextRef(ContextKind.FILE, "sloped/course.py", "the merge", (120, 180)),
            ContextRef(ContextKind.FILE, "sloped/course.py", "the fork", (400, 440)),
        )
    )
    assert manifest.validate() == ()


def test_a_manifest_cannot_file_a_file_under_facts():
    manifest = _manifest(facts=(ContextRef(ContextKind.FILE, "sloped/course.py", "misfiled"),))
    assert any("expected fact" in p for p in manifest.validate())


def test_the_class_context_budget_is_enforced():
    many = tuple(
        ContextRef(ContextKind.FILE, f"sloped/mod_{i}.py", f"file {i}") for i in range(10)
    )
    manifest = _manifest(reasoning_class=ReasoningClass.A, files=many)
    problems = manifest.validate()
    assert any("context budget" in p for p in problems)
    with pytest.raises(ValueError, match="invalid context manifest"):
        manifest.assert_valid()


def test_acceptance_criteria_are_required():
    assert any("acceptance criteria" in p for p in _manifest(acceptance_criteria=()).validate())


def test_fingerprint_is_stable_and_content_sensitive():
    assert _manifest().fingerprint() == _manifest().fingerprint()
    assert _manifest().fingerprint() != _manifest(objective="Something else entirely").fingerprint()


def test_unused_context_is_measurable():
    manifest = _manifest()
    used = manifest.keys()[:1]
    assert len(manifest.unused(used)) == 2
    assert manifest.utilisation(used) == pytest.approx(1 / 3)
    assert manifest.utilisation(manifest.keys()) == 1.0


# --------------------------------------------------------------------------
# Usage records work without token counts
# --------------------------------------------------------------------------


def test_a_record_is_valid_with_no_provider_numbers_at_all():
    record = ResourceUsageRecord(
        task_id="task-001",
        reasoning_class=ReasoningClass.C,
        outcome=Outcome.ACCEPTED,
    )
    assert record.has_unit_accounting is False
    assert record.total_units is None
    assert record.tool_calls is None
    assert record.duration_s is None


def test_the_primary_metric_survives_missing_token_counts():
    ledger = UsageLedger()
    ledger.add(
        ResourceUsageRecord(
            task_id="task-001",
            reasoning_class=ReasoningClass.C,
            outcome=Outcome.REJECTED,
            rejection_reason="missed the acceptance criterion on orange completion",
        )
    )
    ledger.add(
        ResourceUsageRecord(
            task_id="task-001",
            reasoning_class=ReasoningClass.D,
            outcome=Outcome.ACCEPTED,
            retries=1,
        )
    )
    summary = ledger.summarise()
    assert summary.units is None and summary.units_per_accepted is None
    assert summary.passes_per_accepted == pytest.approx(2.0), "rejections stay in the denominator"
    assert summary.rejected_passes == 1
    assert summary.first_pass_success_rate == pytest.approx(0.0)


def test_unit_accounting_is_used_when_every_record_supplies_it():
    ledger = UsageLedger()
    for _ in range(2):
        ledger.add(
            ResourceUsageRecord(
                task_id="task-002",
                reasoning_class=ReasoningClass.C,
                outcome=Outcome.ACCEPTED,
                input_units=1000,
                output_units=200,
                usage_unit=UsageUnit.TOKEN,
                tool_calls=3,
                duration_s=1.5,
            )
        )
    summary = ledger.summarise()
    assert summary.unit is UsageUnit.TOKEN
    assert summary.units == 2400
    assert summary.units_per_accepted == pytest.approx(1200.0)
    assert summary.tool_calls == 6
    assert summary.duration_s == pytest.approx(3.0)
    assert summary.first_pass_success_rate == pytest.approx(1.0)


def test_mixed_units_refuse_to_be_added_up():
    ledger = UsageLedger()
    ledger.add(
        ResourceUsageRecord(
            task_id="a",
            reasoning_class=ReasoningClass.C,
            outcome=Outcome.ACCEPTED,
            input_units=10,
            usage_unit=UsageUnit.TOKEN,
        )
    )
    ledger.add(
        ResourceUsageRecord(
            task_id="b",
            reasoning_class=ReasoningClass.C,
            outcome=Outcome.ACCEPTED,
            input_units=40,
            usage_unit=UsageUnit.CHARACTER,
        )
    )
    summary = ledger.summarise()
    assert summary.unit is UsageUnit.UNKNOWN
    assert summary.units is None
    assert summary.passes_per_accepted == pytest.approx(1.0)


def test_a_bare_number_without_a_unit_is_refused():
    with pytest.raises(UsageRecordError, match="not a measurement"):
        ResourceUsageRecord(
            task_id="a",
            reasoning_class=ReasoningClass.C,
            outcome=Outcome.ACCEPTED,
            input_units=100,
        )


def test_a_rejection_must_explain_itself():
    with pytest.raises(UsageRecordError, match="rejection_reason"):
        ResourceUsageRecord(
            task_id="a", reasoning_class=ReasoningClass.C, outcome=Outcome.REJECTED
        )


def test_used_context_must_have_been_supplied():
    with pytest.raises(UsageRecordError, match="used context not present"):
        ResourceUsageRecord(
            task_id="a",
            reasoning_class=ReasoningClass.C,
            outcome=Outcome.ACCEPTED,
            context_sources=("file:a.py",),
            context_refs_used=("file:b.py",),
        )


def test_a_usage_record_closes_the_loop_on_a_manifest():
    manifest = _manifest().assert_valid()
    record = ResourceUsageRecord(
        task_id=manifest.task_id,
        reasoning_class=manifest.reasoning_class,
        outcome=Outcome.ACCEPTED,
        context_sources=manifest.keys(),
        context_refs_used=manifest.keys()[:2],
        context_fingerprint=manifest.fingerprint(),
        cache_hits=1,
    )
    assert record.unused_context == manifest.unused(manifest.keys()[:2])
    assert UsageLedger([record]).cache_hit_rate() == pytest.approx(1.0)


# --------------------------------------------------------------------------
# Bootstrap Mode forbids subagents
# --------------------------------------------------------------------------


def test_the_default_policy_is_the_bootstrap_position():
    policy = ExecutionPolicy()
    assert policy.no_subagents is True
    assert policy.nested_agent_spawning is False
    assert policy.always_on_agents is False
    assert policy.max_concurrent_sessions == 1
    assert policy.allows_nested_agents is False
    assert BOOTSTRAP_POLICY == policy


@pytest.mark.parametrize(
    "override",
    [
        {"no_subagents": False},
        {"nested_agent_spawning": True},
        {"always_on_agents": True},
        {"max_concurrent_sessions": 4},
        {"ceo_amendment": "approved in a chat message"},
    ],
)
def test_bootstrap_mode_cannot_be_relaxed_by_any_single_flag(override):
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(**override)


def test_leaving_bootstrap_mode_alone_does_not_unlock_nested_agents():
    """The first key without the second opens nothing."""
    with pytest.raises(SubagentPolicyViolation, match="ceo_amendment"):
        ExecutionPolicy(mode="amended", no_subagents=False, nested_agent_spawning=True)


def test_both_keys_are_required_and_are_recorded_in_the_artifact():
    policy = ExecutionPolicy(
        mode="amended",
        no_subagents=False,
        nested_agent_spawning=True,
        ceo_amendment="CEO approval 2026-09-16, recorded in decision/nested-agents-v2",
    )
    assert policy.allows_nested_agents is True
    assert "CEO approval" in policy.ceo_amendment


def test_an_unknown_config_key_is_refused_rather_than_ignored():
    """The realistic silent-enable vector is a YAML key nobody validates."""
    with pytest.raises(PolicyConfigError, match="allow_subagents"):
        ExecutionPolicy.from_mapping({"mode": "bootstrap", "allow_subagents": True})


def test_a_config_mapping_round_trips_the_bootstrap_position():
    policy = ExecutionPolicy.from_mapping(
        {"mode": "bootstrap", "no_subagents": True, "nested_agent_spawning": False}
    )
    assert policy == BOOTSTRAP_POLICY


def test_a_mistyped_config_value_is_refused():
    with pytest.raises(PolicyConfigError, match="expected a boolean"):
        ExecutionPolicy.from_mapping({"no_subagents": "true"})


def test_a_usage_record_cannot_report_a_nested_agent():
    with pytest.raises(SubagentPolicyViolation, match="constitution rule 2"):
        ResourceUsageRecord(
            task_id="a",
            reasoning_class=ReasoningClass.F,
            outcome=Outcome.ACCEPTED,
            subagents_used=1,
        )


def test_no_resource_class_permits_subagents():
    assert all(cls.allows_subagents is False for cls in RESOURCE_CLASSES.values())
    assert all(cls.reviewers_sequential is True for cls in RESOURCE_CLASSES.values())


def test_reviewers_must_be_invoked_sequentially():
    BOOTSTRAP_POLICY.assert_sequential(3)  # one at a time is fine
    parallel = ExecutionPolicy(mode="amended", max_concurrent_sessions=3, ceo_amendment="x")
    with pytest.raises(SubagentPolicyViolation, match="sequentially"):
        parallel.assert_sequential(3)
