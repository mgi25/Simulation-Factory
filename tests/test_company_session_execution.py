"""Focused proofs for the Company OS external session execution boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path

import pytest

from ai_platform import (
    ContextKind,
    ContextRef,
    Outcome,
    ReferenceViolation,
    SubagentPolicyViolation,
    UsageUnit,
)
from ai_platform.serde import dumps
from company.runtime import (
    ContextRequirements,
    ExecutionStore,
    ExecutorHint,
    LifecycleError,
    ManualExternalSessionAdapter,
    PathScope,
    ReceiptUsage,
    ReportedTest,
    ResourceUsageStore,
    SessionPacket,
    SessionReceipt,
    TaskSpecification,
    build_session_packet,
    contract_from_registry,
    load_company_config,
    plan_task,
    validate_receipt,
)
from company.runtime.__main__ import main as runtime_main
from company.runtime.config import CompanyConfig
from company.runtime.git_evidence import (
    assert_branch_name,
    branch_head,
    is_git_sha,
    remote_branch_head,
    repository_findings,
)
from company.runtime.packets import COMPLETION_PROTOCOL
from company.validation.errors import ValidationError
from company.efficiency import (
    BenchmarkMode,
    EfficiencyStore,
    MeasurementSource,
    capture_tool_output,
    emit_execution_efficiency,
)


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "company-os-v1-session-execution"
SHA = "a" * 40
OTHER_SHA = "b" * 40
SCOPE = PathScope(
    allowed=("company/runtime/", "tests/"),
    forbidden=("race2/", "sloped/", "godot/"),
)


def _config() -> CompanyConfig:
    return load_company_config(ROOT / "company")


def _spec(**changes: object) -> TaskSpecification:
    values: dict[str, object] = {
        "task_id": "session-execution",
        "objective": "Hand a prepared task to an independent top-level session.",
        "required_capabilities": ("software_architecture",),
        "deterministic_execution_possible": True,
        "context": ContextRequirements(
            refs=(
                ContextRef(
                    ContextKind.MODULE_CONTRACT,
                    "company/README.md",
                    "Company OS dependency contract",
                ),
            ),
            constraints=("Do not modify production systems.",),
            acceptance_criteria=("The focused deterministic checks pass.",),
        ),
    }
    values.update(changes)
    return TaskSpecification(**values)


def _plan(**changes: object):
    return plan_task(_spec(**changes), _config())


def _writable_contract(*allowed: str) -> dict[str, object]:
    """An explicitly restricted test contract.

    `contract_from_registry` grants no writable path, and that is deliberate:
    Bootstrap Mode is fail-closed and real write authority is configured on
    purpose, later. A test that needs to package work therefore states its own
    narrow grant here, rather than the suite quietly widening a production
    contract to keep itself green.
    """
    contract = contract_from_registry("chief_architect", _config())
    contract["may_write"] = list(allowed or SCOPE.allowed)
    return contract


def _packet(**changes: object) -> SessionPacket:
    plan = changes.pop("plan", None) or _plan()
    kwargs: dict[str, object] = {
        "expected_branch": BRANCH,
        "path_scope": SCOPE,
        "required_tests": ("pytest tests/test_company_session_execution.py",),
        "employee_contract": _writable_contract(),
    }
    kwargs.update(changes)
    return build_session_packet(plan, **kwargs)


def _prepare(adapter: ManualExternalSessionAdapter, plan, **changes: object):
    """`adapter.prepare` with the writable test contract the scope requires."""
    kwargs: dict[str, object] = {
        "expected_branch": BRANCH,
        "path_scope": SCOPE,
        "employee_contract": _writable_contract(),
    }
    kwargs.update(changes)
    return adapter.prepare(plan, **kwargs)


def _receipt(packet: SessionPacket, **changes: object) -> SessionReceipt:
    values: dict[str, object] = {
        "task_id": packet.task_id,
        "packet_fingerprint": packet.fingerprint(),
        "outcome": Outcome.ACCEPTED,
        "summary": "Execution boundary implemented and pushed.",
        "branch": BRANCH,
        "commit_sha": SHA,
        "remote_branch_sha": SHA,
        "remote_verified": True,
        "working_tree_clean": True,
        "files_changed": ("company/runtime/packets.py",),
        "tests": (
            ReportedTest("pytest tests/test_company_session_execution.py", True, "24 passed"),
        ),
        "evidence": ("tests/test_company_session_execution.py",),
    }
    values.update(changes)
    return SessionReceipt(**values)


# --- packet -----------------------------------------------------------------


def test_packet_generation_is_deterministic_and_reference_only() -> None:
    first = _packet()
    second = _packet()

    assert first == second
    assert first.fingerprint() == second.fingerprint()
    assert first.employee == "chief_architect"
    assert first.expected_branch == BRANCH
    assert first.no_subagents is True
    assert set(COMPLETION_PROTOCOL) <= set(first.completion_protocol)
    assert "do not merge" in first.completion_protocol

    serialised = dumps(first)
    assert "def " not in serialised  # no source body reached the packet
    assert first.size_chars() < 2000
    for ref in first.context_refs:
        assert "\n" not in ref.ref and len(ref.ref) <= 200


def test_packet_cannot_carry_a_file_body_in_a_reference() -> None:
    packet = _packet()
    with pytest.raises(ReferenceViolation, match="embedded content"):
        replace(
            packet,
            context_refs=(
                ContextRef(ContextKind.FILE, "def leaked():\n    return True", "pasted"),
            ),
        )


def test_packet_preserves_the_explicit_context_fingerprints() -> None:
    plan = _plan()
    packet = _packet(plan=plan)

    assert plan.preparation is not None
    assert plan.context_plan is not None
    assert packet.context_fingerprint == plan.preparation.context_fingerprint
    assert packet.context_cache_key == plan.context_plan.cache_identity
    assert packet.explicit_context_refs == plan.context_plan.explicit_refs
    assert packet.automatic_context_refs == plan.context_plan.capsule_refs_accepted
    assert set(packet.explicit_context_refs) | set(packet.automatic_context_refs) <= set(
        packet.context_keys()
    )


def test_packet_round_trips_through_its_persisted_json() -> None:
    packet = _packet()
    decoded = SessionPacket.from_mapping(json.loads(dumps(packet)))

    assert decoded == packet
    assert decoded.fingerprint() == packet.fingerprint()


def test_executor_hint_is_metadata_and_not_part_of_the_work_identity() -> None:
    claude = _packet(executor=ExecutorHint.CLAUDE_CODE)
    codex = _packet(executor=ExecutorHint.CODEX)
    human = _packet(executor=ExecutorHint.HUMAN)

    assert claude.fingerprint() == codex.fingerprint() == human.fingerprint()
    assert claude.identity() == codex.identity()
    assert claude.executor is ExecutorHint.CLAUDE_CODE

    receipt = _receipt(claude, executor=ExecutorHint.CODEX)
    assert validate_receipt(claude, receipt).ok
    assert validate_receipt(codex, receipt).ok
    assert (
        validate_receipt(claude, receipt).failures
        == validate_receipt(human, replace(receipt, executor=ExecutorHint.HUMAN)).failures
    )


def test_packet_rejects_a_disabled_no_subagent_rule() -> None:
    with pytest.raises(SubagentPolicyViolation, match="packet.no_subagents must be true"):
        replace(_packet(), no_subagents=False)


def test_packet_refuses_a_ceo_reserved_task() -> None:
    with pytest.raises(LifecycleError, match="CEO-reserved"):
        _packet(plan=_plan(ceo_reserved=True))


def test_packet_is_never_built_for_an_unprepared_plan() -> None:
    escalated = _plan(required_capabilities=("software_architecture", "underwater_audio"))
    with pytest.raises(LifecycleError, match="not execution_prepared"):
        _packet(plan=escalated)


def test_packet_scope_cannot_exceed_the_employee_contract() -> None:
    config = _config()
    contract = contract_from_registry("chief_architect", config)
    contract["may_write"] = ["company/"]
    contract["may_not_modify"] = ["company/permissions.yaml"]
    plan = _plan()

    ok = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(allowed=("company/runtime/",)),
        employee_contract=contract,
    )
    assert ok.path_scope.allowed == ("company/runtime",)

    with pytest.raises(LifecycleError, match="outside chief_architect's may_write"):
        build_session_packet(
            plan,
            expected_branch=BRANCH,
            path_scope=PathScope(allowed=("sloped/",)),
            employee_contract=contract,
        )
    with pytest.raises(LifecycleError, match="may_not_modify"):
        build_session_packet(
            plan,
            expected_branch=BRANCH,
            path_scope=PathScope(allowed=("company/permissions.yaml",)),
            employee_contract=contract,
        )


def test_an_explicit_narrow_grant_packages_work_only_inside_its_boundary() -> None:
    """A contract may receive one writable path, and it bounds the packet exactly."""
    contract = _writable_contract("company/runtime/")
    plan = _plan()

    inside = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(allowed=("company/runtime/packets.py",)),
        employee_contract=contract,
    )
    assert inside.path_scope.allowed == ("company/runtime/packets.py",)

    # A sibling that merely shares a prefix is outside: matching is by segment.
    for outside in ("company/runtime_extra.py", "company/", "tests/", "sloped/"):
        with pytest.raises(LifecycleError, match="outside chief_architect's may_write"):
            build_session_packet(
                plan,
                expected_branch=BRANCH,
                path_scope=PathScope(allowed=(outside,)),
                employee_contract=contract,
            )


def test_a_broad_grant_cannot_reach_a_path_the_contract_protects() -> None:
    """Forbidden outranks allowed, and overlap in either direction is enough."""
    contract = _writable_contract("company/")
    contract["may_not_modify"] = ["company/permissions.yaml"]
    plan = _plan()

    # The protected file itself, and a rule broad enough to contain it.
    for reaching in ("company/permissions.yaml", "company/"):
        with pytest.raises(LifecycleError, match="may_not_modify"):
            build_session_packet(
                plan,
                expected_branch=BRANCH,
                path_scope=PathScope(allowed=(reaching,)),
                employee_contract=contract,
            )

    beside = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(allowed=("company/runtime/",)),
        employee_contract=contract,
    )
    assert beside.path_scope.allowed == ("company/runtime",)


def test_the_default_bootstrap_contract_grants_no_write_authority() -> None:
    """The real contract, unfilled: empty `may_write` means read-only, not unrestricted.

    This is the regression the fail-closed rule exists for. It uses the
    canonical config and `contract_from_registry` exactly as
    `build_session_packet` does when no contract is supplied, so it fails if
    bootstrap ever starts handing out a writable path by default *or* if the
    check ever starts reading an empty list as a wildcard again.
    """
    config = _config()
    contract = contract_from_registry("chief_architect", config)
    assert contract["may_write"] == []
    assert contract["may_not_modify"] == []

    plan = _plan()
    for writable in ("company/runtime/", "company/", "tests/", "intelligence/"):
        with pytest.raises(LifecycleError, match="grants no writable path"):
            build_session_packet(
                plan,
                expected_branch=BRANCH,
                path_scope=PathScope(allowed=(writable,)),
                employee_contract=contract,
            )

    # The same refusal when the contract is read from the registry rather than
    # passed in - the default path a caller takes without thinking about it.
    with pytest.raises(LifecycleError, match="grants no writable path"):
        build_session_packet(
            plan, expected_branch=BRANCH, path_scope=PathScope(allowed=("company/runtime/",))
        )


def test_the_default_bootstrap_contract_still_packages_read_only_work() -> None:
    """Fail-closed is not fail-useless: a read-only packet is still valid."""
    plan = _plan()
    packet = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(forbidden=("race2/", "sloped/")),
        employee_contract=contract_from_registry("chief_architect", _config()),
    )
    assert packet.path_scope.read_only
    assert packet.path_scope.allowed == ()

    # And so is a packet that names no scope at all.
    assert build_session_packet(plan, expected_branch=BRANCH).path_scope.read_only

    # It permits no change, which is what read-only has to mean downstream.
    verdict = validate_receipt(
        packet,
        _receipt(packet, files_changed=("company/runtime/packets.py",)),
    )
    assert not verdict.ok
    assert any("outside every allowed path" in failure for failure in verdict.failures)


def test_branch_and_sha_shapes_are_checked_at_construction() -> None:
    assert assert_branch_name(BRANCH, "branch") == BRANCH
    assert is_git_sha(SHA) and not is_git_sha("A" * 40) and not is_git_sha("abc")
    with pytest.raises(LifecycleError, match="not a usable branch name"):
        _packet(expected_branch="feature branch")
    with pytest.raises(LifecycleError, match="not a Git object name"):
        _packet(expected_base_commit="not-a-sha")


# --- path scope -------------------------------------------------------------


def test_allowed_paths_pass_and_forbidden_paths_fail() -> None:
    packet = _packet()
    allowed = validate_receipt(
        packet, _receipt(packet, files_changed=("company/runtime/packets.py", "tests/x.py"))
    )
    assert allowed.ok

    forbidden = validate_receipt(
        packet,
        _receipt(packet, files_changed=("company/runtime/packets.py", "sloped/cameras.py")),
    )
    assert not forbidden.ok
    assert any("forbidden rule sloped" in failure for failure in forbidden.failures)

    outside = validate_receipt(packet, _receipt(packet, files_changed=("tools/other.py",)))
    assert not outside.ok
    assert any("outside every allowed path" in failure for failure in outside.failures)


def test_a_packet_with_no_allowed_paths_permits_no_change() -> None:
    packet = _packet(path_scope=PathScope(forbidden=("race2/",)))
    assert packet.path_scope.read_only
    verdict = validate_receipt(packet, _receipt(packet, files_changed=("company/runtime/x.py",)))
    assert not verdict.ok


def test_path_rules_are_prefix_rules_and_separator_agnostic() -> None:
    packet = _packet()
    windows_spelling = _receipt(
        packet, files_changed=("company" + chr(92) + "runtime" + chr(92) + "packets.py",)
    )
    result = validate_receipt(packet, windows_spelling)
    assert result.ok
    assert result.path_verdict.paths == ("company/runtime/packets.py",)

    sibling = validate_receipt(
        packet, _receipt(packet, files_changed=("company/runtime_extra.py",))
    )
    assert not sibling.ok


# --- receipt validation -----------------------------------------------------


def test_a_valid_receipt_passes_every_check() -> None:
    packet = _packet()
    result = validate_receipt(packet, _receipt(packet))
    assert result.ok
    assert result.failures == ()


def test_malformed_sha_and_remote_mismatch_fail() -> None:
    packet = _packet()

    malformed = validate_receipt(packet, _receipt(packet, commit_sha="deadbeef"))
    assert any("not a Git object name" in failure for failure in malformed.failures)

    mismatch = validate_receipt(packet, _receipt(packet, remote_branch_sha=OTHER_SHA))
    assert any("does not equal the reported commit" in failure for failure in mismatch.failures)

    unverified = validate_receipt(packet, _receipt(packet, remote_verified=False))
    assert any("remote verification is not asserted" in f for f in unverified.failures)


def test_wrong_branch_merge_and_dirty_tree_fail() -> None:
    packet = _packet()
    wrong_branch = validate_receipt(packet, _receipt(packet, branch="main"))
    assert any("not the assigned branch" in failure for failure in wrong_branch.failures)

    merged = validate_receipt(packet, _receipt(packet, merge_performed=True))
    assert any("a merge was performed" in failure for failure in merged.failures)

    dirty = validate_receipt(packet, _receipt(packet, working_tree_clean=False))
    assert any("working tree is reported dirty" in failure for failure in dirty.failures)


def test_a_write_producing_accepted_result_must_prove_a_clean_tree() -> None:
    """The protocol ends in a clean tree, so silence about it is not completion."""
    packet = _packet()

    clean = validate_receipt(packet, _receipt(packet, working_tree_clean=True))
    assert clean.ok

    dirty = validate_receipt(packet, _receipt(packet, working_tree_clean=False))
    assert not dirty.ok
    assert any("working tree is reported dirty" in failure for failure in dirty.failures)

    unknown = validate_receipt(packet, _receipt(packet, working_tree_clean=None))
    assert not unknown.ok
    assert any("working tree status is unknown" in failure for failure in unknown.failures)

    # Still fatal when the packet is writable and the receipt names no file:
    # the grant alone is enough to have left something behind.
    no_files = validate_receipt(
        packet, _receipt(packet, working_tree_clean=None, files_changed=())
    )
    assert not no_files.ok
    assert any("working tree status is unknown" in failure for failure in no_files.failures)


def test_an_unknown_tree_is_only_a_warning_for_a_genuinely_read_only_result() -> None:
    """Nothing could be left dirty by a read-only packet that changed nothing."""
    read_only = build_session_packet(
        _plan(),
        expected_branch=BRANCH,
        path_scope=PathScope(forbidden=("race2/",)),
        required_tests=("pytest tests/test_company_session_execution.py",),
    )
    assert read_only.path_scope.read_only

    result = validate_receipt(
        read_only, _receipt(read_only, working_tree_clean=None, files_changed=())
    )
    assert result.ok
    assert any("does not report working tree status" in w for w in result.warnings)

    # A change reported under a read-only packet is write-producing anyway, so
    # the tree must be proven - on top of the scope failure the change earns.
    contradicted = validate_receipt(
        read_only,
        _receipt(read_only, working_tree_clean=None, files_changed=("company/runtime/x.py",)),
    )
    assert not contradicted.ok
    assert any("working tree status is unknown" in f for f in contradicted.failures)
    assert contradicted.warnings == ()


def test_required_tests_and_evidence_are_enforced_for_an_accepted_result() -> None:
    packet = _packet()
    missing = validate_receipt(packet, _receipt(packet, tests=()))
    assert any("required test(s) not reported" in failure for failure in missing.failures)

    failing = validate_receipt(
        packet,
        _receipt(
            packet,
            tests=(
                ReportedTest("pytest tests/test_company_session_execution.py", False, "1 failed"),
            ),
        ),
    )
    assert any("reported failing test(s)" in failure for failure in failing.failures)

    evidence_packet = _packet(plan=_plan(evidence_required=True))
    assert evidence_packet.evidence_required
    no_evidence = validate_receipt(
        evidence_packet,
        _receipt(evidence_packet, evidence=(), tests=()),
    )
    assert any("requires evidence" in failure for failure in no_evidence.failures)


def test_subagent_use_fails_validation_and_is_never_recorded(tmp_path: Path) -> None:
    packet = _packet()
    receipt = _receipt(packet, subagents_used=1)
    result = validate_receipt(packet, receipt)
    assert not result.ok
    assert any("nested agent" in failure for failure in result.failures)

    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    with pytest.raises(SubagentPolicyViolation):
        adapter.ingest(_plan(), packet, receipt, usage_store)

    # The evidence is kept; nothing downstream of it exists.
    assert len(store.attempts("session-execution")) == 1
    assert store.attempts("session-execution")[0].receipt.subagents_used == 1
    assert usage_store.records() == ()


def test_a_receipt_cannot_assert_authority_it_was_not_given() -> None:
    packet = _packet()
    base = json.loads(dumps(_receipt(packet)))

    for escalation in (
        {"autonomy_level": 5},
        {"ceo_approved": True},
        {"production_authority": True},
        {"employee": "ceo"},
        {"permissions": ["approved_operational_actions"]},
    ):
        with pytest.raises(ValidationError, match="does not grant authority"):
            SessionReceipt.from_mapping({**base, **escalation})

    with pytest.raises(ValidationError, match="no_subagents must be true"):
        SessionReceipt.from_mapping({**base, "no_subagents": False})

    with pytest.raises(SubagentPolicyViolation, match="does not amend"):
        replace(_receipt(packet), no_subagents=False)


def test_receipt_round_trips_through_its_persisted_json() -> None:
    packet = _packet()
    receipt = _receipt(
        packet,
        usage=ReceiptUsage(
            passes=1, retries=1, tool_calls=42, input_units=900, output_units=120,
            usage_unit=UsageUnit.TOKEN, duration_s=61.5,
        ),
    )
    assert SessionReceipt.from_mapping(json.loads(dumps(receipt))) == receipt


# --- ingestion, history, attempts -------------------------------------------


def test_ingestion_produces_one_usage_record_and_a_compact_handoff(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)

    prepared = _prepare(
        adapter,
        plan,
        required_tests=("pytest tests/test_company_session_execution.py",),
        executor=ExecutorHint.CLAUDE_CODE,
    )
    assert prepared.pointer.record_ref.startswith("execution/packets/")
    assert prepared.pointer.attempt == 1

    manifest_keys = plan.context_manifest.keys()
    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(
            prepared.packet,
            context_refs_used=manifest_keys,
            usage=ReceiptUsage(tool_calls=12, input_units=800, output_units=200,
                               usage_unit=UsageUnit.TOKEN),
        ),
        usage_store,
    )

    assert ingested.accepted
    assert ingested.validation.ok
    assert ingested.receipt_pointer.record_ref.startswith("execution/receipts/")

    record = ingested.attempt.usage_record
    assert record.outcome is Outcome.ACCEPTED
    assert record.context_fingerprint == prepared.packet.context_fingerprint
    assert record.context_cache_key == prepared.packet.context_cache_key
    assert record.context_refs_used == manifest_keys
    assert record.subagents_used == 0
    assert record.total_units == 1000

    handoff = ingested.attempt.handoff
    assert handoff.status.value == "completed"
    assert handoff.resource_usage.fingerprint == record.fingerprint()
    assert usage_store.load(handoff.resource_usage) == record
    assert ingested.receipt_pointer.record_ref in handoff.artifacts
    assert set(handoff.resource_usage.to_dict()) == {"record_ref", "fingerprint"}
    assert f"commit:{SHA}" in handoff.evidence


def test_ingestion_emits_observational_efficiency_with_provider_and_tool_facts(
    tmp_path: Path,
) -> None:
    plan = _plan(
        context=ContextRequirements(
            refs=(
                ContextRef(
                    ContextKind.FILE,
                    "company/runtime/session_adapter.py",
                    "the actual finalization boundary",
                ),
                ContextRef(
                    ContextKind.FILE,
                    "company/runtime/receipts.py",
                    "the selected provider-neutral receipt contract",
                ),
            ),
            acceptance_criteria=("Telemetry is observational.",),
        )
    )
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)
    used = next(
        ref.key
        for ref in prepared.packet.context_refs
        if ref.ref == "company/runtime/session_adapter.py"
    )
    tool_output = capture_tool_output(
        task_id=prepared.packet.task_id,
        command="pytest",
        exit_status=1,
        raw_output="one passed\none failed\n",
    )
    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(
            prepared.packet,
            context_refs_used=(used,),
            completed_at="2026-09-17T12:00:00+05:30",
            usage=ReceiptUsage(
                cache_hits=2,
                cache_misses=1,
                tool_calls=3,
                input_units=101,
                output_units=17,
                usage_unit=UsageUnit.TOKEN,
                provider="example-provider",
                model="example-model",
                provider_latency_ms=425,
                provider_cost="0.014",
                provider_cost_currency="USD",
            ),
        ),
        usage_store,
        tool_outputs=(tool_output,),
    )

    assert ingested.accepted and not ingested.telemetry_error
    assert ingested.efficiency_pointer is not None
    record = EfficiencyStore(tmp_path).records(prepared.packet.task_id)[0]
    assert record.mode is BenchmarkMode.REAL
    assert record.tokens.source is MeasurementSource.PROVIDER_REPORTED
    assert (record.tokens.input_tokens, record.tokens.output_tokens) == (101, 17)
    assert record.estimated_tokens is not None
    assert record.estimated_tokens.source is MeasurementSource.ESTIMATED
    assert record.provider == "example-provider" and record.model == "example-model"
    assert record.repository_references_selected == (
        "company/runtime/session_adapter.py",
        "company/runtime/receipts.py",
    )
    assert record.repository_files_read == ("company/runtime/session_adapter.py",)
    assert (record.cache_hits, record.cache_misses) == (2, 1)
    assert record.cache_identity == prepared.packet.context_cache_key
    assert record.context_bytes is None  # external ref resolution is not observable
    assert record.context_manifest_bytes is not None
    assert record.tool_output_bytes == record.tool_context_bytes
    assert record.tool_activity[0].name == "pytest"
    assert record.tool_activity[0].failure_count == 1
    assert record.outcome == "accepted"
    assert record.timestamp == "2026-09-17T12:00:00+05:30"
    retried = emit_execution_efficiency(
        plan=plan,
        packet=prepared.packet,
        packet_attempt=prepared.pointer.attempt,
        receipt=ingested.receipt,
        receipt_pointer=ingested.receipt_pointer,
        outcome=ingested.attempt.usage_record.outcome,
        state_dir=tmp_path,
        expansion_ledger=None,
        tool_outputs=(tool_output,),
    )
    assert retried.pointer == ingested.efficiency_pointer
    assert len(EfficiencyStore(tmp_path).records(prepared.packet.task_id)) == 1


def test_rejected_execution_still_emits_efficiency_and_missing_usage_stays_unavailable(
    tmp_path: Path,
) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)
    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(prepared.packet, files_changed=("sloped/cameras.py",)),
        ResourceUsageStore(tmp_path),
    )
    record = EfficiencyStore(tmp_path).records(prepared.packet.task_id)[0]
    assert not ingested.accepted
    assert record.outcome == "rejected"
    assert record.tokens.source is MeasurementSource.UNAVAILABLE
    assert record.estimated_tokens is not None


def test_provider_failure_retains_any_reported_usage(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)
    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(
            prepared.packet,
            outcome=Outcome.ABANDONED,
            summary="Provider failed before a deliverable was returned.",
            rejection_reason="provider transport failed",
            usage=ReceiptUsage(
                input_units=37,
                output_units=0,
                usage_unit=UsageUnit.TOKEN,
                provider="example-provider",
            ),
        ),
        ResourceUsageStore(tmp_path),
    )
    record = EfficiencyStore(tmp_path).records(prepared.packet.task_id)[0]
    assert not ingested.accepted
    assert record.outcome == "abandoned"
    assert record.tokens.source is MeasurementSource.PROVIDER_REPORTED
    assert record.tokens.total_tokens == 37


def test_telemetry_storage_failure_never_changes_execution_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from company.efficiency import emission

    plan = _plan()
    store = ExecutionStore(tmp_path)
    prepared = _prepare(ManualExternalSessionAdapter(store), plan)

    def fail_telemetry(*args: object, **kwargs: object) -> object:
        raise OSError("telemetry disk unavailable")

    monkeypatch.setattr(emission, "emit_execution_efficiency", fail_telemetry)
    ingested = ManualExternalSessionAdapter(store).ingest(
        plan,
        prepared.packet,
        _receipt(prepared.packet),
        ResourceUsageStore(tmp_path),
    )
    assert ingested.accepted
    assert ingested.attempt.usage_record.outcome is Outcome.ACCEPTED
    assert "telemetry disk unavailable" in ingested.telemetry_error
    assert ingested.efficiency_pointer is None

    failed_state = tmp_path / "failed"
    failed_plan = _plan(task_id="failed-telemetry")
    failed_store = ExecutionStore(failed_state)
    failed_prepared = _prepare(ManualExternalSessionAdapter(failed_store), failed_plan)
    failed = ManualExternalSessionAdapter(failed_store).ingest(
        failed_plan,
        failed_prepared.packet,
        _receipt(
            failed_prepared.packet,
            files_changed=("sloped/cameras.py",),
        ),
        ResourceUsageStore(failed_state),
    )
    assert not failed.accepted
    assert failed.attempt.usage_record.outcome is Outcome.REJECTED
    assert "telemetry disk unavailable" in failed.telemetry_error


def test_a_failed_receipt_is_recorded_as_a_rejected_attempt(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)

    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(prepared.packet, files_changed=("sloped/cameras.py",)),
        usage_store,
    )

    assert not ingested.accepted
    assert ingested.attempt.usage_record.outcome is Outcome.REJECTED
    assert "forbidden rule sloped" in ingested.attempt.usage_record.rejection_reason
    assert ingested.attempt.handoff.status.value == "blocked"


def test_retries_are_separate_attempts_and_the_rejected_one_is_retained(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)
    packet = prepared.packet

    first = adapter.ingest(
        plan, packet, _receipt(packet, files_changed=("godot/scene.tscn",)), usage_store
    )
    second = adapter.ingest(plan, packet, _receipt(packet, commit_sha=OTHER_SHA,
                                                   remote_branch_sha=OTHER_SHA), usage_store)

    attempts = store.attempts("session-execution")
    assert [record.attempt for record in attempts] == [1, 2]
    assert [record.outcome for record in attempts] == [Outcome.ACCEPTED, Outcome.ACCEPTED]
    assert first.receipt_pointer.record_ref != second.receipt_pointer.record_ref

    records = usage_store.records("session-execution")
    assert [record.outcome for record in records] == [Outcome.REJECTED, Outcome.ACCEPTED]
    assert usage_store.summarise("session-execution").passes_per_accepted == pytest.approx(2.0)

    history = store.history("session-execution")
    assert [item["attempt"] for item in history["attempts"]] == [1, 2]
    assert len(history["packets"]) == 1


def test_the_history_never_silently_overwrites_a_record(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)

    first_path = tmp_path / prepared.pointer.record_ref
    original = first_path.read_bytes()

    again = _prepare(adapter, plan)
    adapter.ingest(plan, prepared.packet, _receipt(prepared.packet), usage_store)
    adapter.ingest(plan, prepared.packet, _receipt(prepared.packet), usage_store)

    assert again.pointer.record_ref != prepared.pointer.record_ref
    assert first_path.read_bytes() == original
    assert len(store.packets("session-execution")) == 2
    assert len(store.attempts("session-execution")) == 2
    assert not hasattr(store, "update")
    assert not hasattr(store, "delete")


def test_ingestion_refuses_a_plan_that_is_not_the_packet_s_plan(tmp_path: Path) -> None:
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    packet = _packet()
    other_plan = _plan(task_id="a-different-task")

    with pytest.raises(LifecycleError, match="does not match the packet"):
        adapter.ingest(other_plan, packet, _receipt(packet), ResourceUsageStore(tmp_path))


def test_a_receipt_answering_another_packet_is_rejected(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)
    other = _packet(expected_branch="main")

    ingested = adapter.ingest(
        plan, prepared.packet, _receipt(other, branch="main"), ResourceUsageStore(tmp_path)
    )
    assert not ingested.accepted
    assert any("answers packet" in failure for failure in ingested.validation.failures)


def test_a_declared_dependency_raises_the_permissions_review_trigger(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)

    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(prepared.packet, dependencies_added=("pyyaml",)),
        ResourceUsageStore(tmp_path),
    )
    assert ingested.accepted
    assert ingested.attempt.handoff.escalation_required is True
    assert "architecture_and_security_review" in ingested.attempt.handoff.escalation_reason


def test_an_invented_next_owner_is_rejected_rather_than_raised(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare(adapter, plan)

    ingested = adapter.ingest(
        plan,
        prepared.packet,
        _receipt(prepared.packet, next_owner="acting_ceo"),
        ResourceUsageStore(tmp_path),
    )
    assert not ingested.accepted
    assert any("not an employee in the registry" in f for f in ingested.validation.failures)
    assert ingested.attempt.handoff.next_owner == ""
    assert len(store.attempts("session-execution")) == 1


def test_a_local_clone_can_contradict_a_remote_claim(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "refs" / "remotes" / "origin").mkdir(parents=True)
    (repo / ".git" / "refs" / "heads" / BRANCH).write_text(SHA + "\n", encoding="utf-8")
    (repo / ".git" / "refs" / "remotes" / "origin" / BRANCH).write_text(
        OTHER_SHA + "\n", encoding="utf-8"
    )

    plan = _plan()
    state = tmp_path / "state"
    adapter = ManualExternalSessionAdapter(ExecutionStore(state))
    prepared = _prepare(adapter, plan)
    usage_store = ResourceUsageStore(state)

    without_repo = adapter.ingest(plan, prepared.packet, _receipt(prepared.packet), usage_store)
    assert without_repo.accepted

    with_repo = adapter.ingest(
        plan, prepared.packet, _receipt(prepared.packet), usage_store, repo_dir=repo
    )
    assert not with_repo.accepted
    assert any("repository evidence" in f for f in with_repo.validation.failures)

# --- git evidence against a real repository ---------------------------------


def test_repository_evidence_reads_refs_without_a_subprocess(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / ".git" / "refs" / "heads").mkdir(parents=True)
    (repo / ".git" / "refs" / "remotes" / "origin").mkdir(parents=True)
    (repo / ".git" / "refs" / "heads" / "topic").write_text(SHA + "\n", encoding="utf-8")
    (repo / ".git" / "refs" / "remotes" / "origin" / "topic").write_text(
        SHA + "\n", encoding="utf-8"
    )

    assert branch_head(repo, "topic") == SHA
    assert remote_branch_head(repo, "topic") == SHA
    assert repository_findings(repo, "topic", SHA) == ()

    findings = repository_findings(repo, "topic", OTHER_SHA)
    assert any("the receipt reports" in finding for finding in findings)

    packed = tmp_path / "packed"
    (packed / ".git").mkdir(parents=True)
    (packed / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled fully-peeled sorted\n"
        f"{OTHER_SHA} refs/heads/topic\n",
        encoding="utf-8",
    )
    assert branch_head(packed, "topic") == OTHER_SHA


# --- the no-subagent chain, end to end --------------------------------------


def test_the_no_subagent_rule_holds_at_every_link(tmp_path: Path) -> None:
    config = _config()
    plan = _plan()
    packet = _packet(plan=plan)
    store = ExecutionStore(tmp_path)
    usage_store = ResourceUsageStore(tmp_path)

    assert config.org_registry["global_constraints"]["no_subagents"] is True
    assert config.permissions["bootstrap_defaults"]["no_subagents"] is True
    assert contract_from_registry("chief_architect", config)["no_subagents"] is True
    assert plan.policy.no_subagents is True
    assert plan.policy.allows_nested_agents is False
    assert plan.preparation is not None and plan.preparation.no_subagents is True
    assert packet.no_subagents is True

    ingested = ManualExternalSessionAdapter(store).ingest(
        plan, packet, _receipt(packet), usage_store
    )
    assert ingested.receipt.subagents_used == 0
    assert ingested.attempt.usage_record.subagents_used == 0


def test_bootstrap_contracts_still_reject_a_nested_agent_switch() -> None:
    config = _config()
    contract = contract_from_registry("chief_architect", config)
    contract["no_subagents"] = False
    with pytest.raises(ValidationError, match="agent_contract.no_subagents must be true"):
        plan_task(_spec(), config, employee_contract=contract)
    with pytest.raises(ValidationError, match="task.execution.subagents must be false"):
        plan_task(_spec(execution={"subagents": True}), config)


# --- production independence ------------------------------------------------


def test_company_os_remains_removable_and_production_does_not_import_it() -> None:
    offenders: list[str] = []
    for directory in ("sloped", "tools", "godot", "race2", "fight"):
        root = ROOT / directory
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if (
                "import company" in text
                or "from company" in text
                or "import ai_platform" in text
                or "from ai_platform" in text
                or "from knowledge.company_os" in text
            ):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_the_execution_layer_imports_no_provider_sdk_and_spawns_nothing() -> None:
    modules = (
        "packets.py",
        "receipts.py",
        "session_adapter.py",
        "execution_store.py",
        "git_evidence.py",
        "path_scope.py",
        "state_paths.py",
    )
    forbidden = (
        "import subprocess",
        "import anthropic",
        "import openai",
        "multiprocessing",
        "os.system",
        "popen",
        "asyncio",
    )
    for name in modules:
        text = (ROOT / "company" / "runtime" / name).read_text(encoding="utf-8").casefold()
        for token in forbidden:
            assert token not in text, f"{name} must not reference {token}"


# --- CLI --------------------------------------------------------------------


def test_packet_receipt_and_execution_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "cli-session",
                "objective": "Drive the execution boundary from the CLI.",
                "required_capabilities": ["software_architecture"],
                "deterministic_execution_possible": True,
                "context": {"acceptance_criteria": ["The packet is produced."]},
            }
        ),
        encoding="utf-8",
    )
    state = tmp_path / "state"

    # The CLI reads the registry contract, which in Bootstrap Mode grants no
    # writable path - so asking it for one is refused rather than served.
    assert (
        runtime_main(
            [
                "packet",
                str(task_file),
                "--branch",
                BRANCH,
                "--allow",
                "company/runtime/",
                "--state-dir",
                str(state),
            ]
        )
        == 2
    )
    refused = capsys.readouterr()
    assert "grants no writable path" in refused.err
    assert refused.out == ""

    assert (
        runtime_main(
            [
                "packet",
                str(task_file),
                "--branch",
                BRANCH,
                "--forbid",
                "sloped/",
                "--test",
                "pytest tests/test_company_session_execution.py",
                "--executor",
                "codex",
                "--state-dir",
                str(state),
            ]
        )
        == 0
    )
    built = json.loads(capsys.readouterr().out)
    assert built["packet"]["expected_branch"] == BRANCH
    assert built["packet"]["executor"] == "codex"
    assert built["packet"]["path_scope"]["allowed"] == []
    assert built["persisted"]["attempt"] == 1

    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(
        json.dumps(
            {
                "task_id": "cli-session",
                "packet_fingerprint": built["fingerprint"],
                "outcome": "accepted",
                "summary": "Done, pushed and verified.",
                "branch": BRANCH,
                "commit_sha": SHA,
                "remote_branch_sha": SHA,
                "remote_verified": True,
                "working_tree_clean": True,
                "files_changed": [],
                "tests": [
                    {
                        "command": "pytest tests/test_company_session_execution.py",
                        "passed": True,
                    }
                ],
                "evidence": ["tests/test_company_session_execution.py"],
            }
        ),
        encoding="utf-8",
    )
    assert runtime_main(["receipt", str(receipt_file), "--task", str(task_file),
                         "--state-dir", str(state)]) == 0
    ingested = json.loads(capsys.readouterr().out)
    assert ingested["accepted"] is True
    assert ingested["failures"] == []

    assert runtime_main(["execution", "--state-dir", str(state), "--task", "cli-session"]) == 0
    history = json.loads(capsys.readouterr().out)
    assert history["attempts"][0]["outcome"] == "accepted"
    assert history["attempts"][0]["subagents_used"] == 0


def test_the_cli_reports_a_rejected_attempt_with_a_non_zero_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    plan = _plan(task_id="cli-rejected")
    state = tmp_path / "state"
    store = ExecutionStore(state)
    packet = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=SCOPE,
        employee_contract=_writable_contract(),
    )
    store.append_packet(packet)

    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "cli-rejected",
                "objective": plan.specification.objective,
                "required_capabilities": ["software_architecture"],
                "deterministic_execution_possible": True,
                "context": {
                    "refs": [
                        {
                            "kind": "module_contract",
                            "ref": "company/README.md",
                            "reason": "Company OS dependency contract",
                        }
                    ],
                    "constraints": ["Do not modify production systems."],
                    "acceptance_criteria": ["The focused deterministic checks pass."],
                },
            }
        ),
        encoding="utf-8",
    )
    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(
        dumps(_receipt(packet, task_id="cli-rejected", files_changed=("race2/track.py",))),
        encoding="utf-8",
    )

    assert runtime_main(["receipt", str(receipt_file), "--task", str(task_file),
                         "--state-dir", str(state)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["accepted"] is False
    assert any("race2" in failure for failure in payload["failures"])


def test_runtime_state_is_never_written_into_the_repository(tmp_path: Path) -> None:
    plan = _plan()
    adapter = ManualExternalSessionAdapter(ExecutionStore(tmp_path))
    prepared = _prepare(adapter, plan)

    written = tmp_path / prepared.pointer.record_ref
    assert written.is_file()
    assert ROOT not in written.parents
    assert not (ROOT / "execution").exists()
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "state/" in gitignore


def test_deepcopy_of_the_config_is_not_needed_to_keep_packets_stable() -> None:
    config = _config()
    snapshot = deepcopy(config.org_registry)
    _packet()
    assert config.org_registry == snapshot
