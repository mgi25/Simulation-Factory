"""Focused proofs for audited Company OS context expansion."""

from __future__ import annotations

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
    resource_class,
)
from ai_platform.serde import dumps, fingerprint
from company.runtime import (
    ContextExpansionDecision,
    ContextExpansionLedger,
    ContextExpansionRequest,
    ContextRequirements,
    ExecutionStore,
    ExecutorHint,
    ExpansionOutcome,
    LifecycleError,
    ManualExternalSessionAdapter,
    PathScope,
    ResourceUsageStore,
    SessionPacket,
    SessionReceipt,
    TaskSpecification,
    build_session_packet,
    contract_from_registry,
    decide_context_expansion,
    load_company_config,
    plan_task,
    validate_receipt,
)
from company.efficiency import EfficiencyStore


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "company-os-v1-context-expansion"
SHA = "c" * 40
INDEX_REF = ContextRef(
    ContextKind.FILE,
    "knowledge/company_os/capsules/index.py",
    "inspect exact capsule dependency registration",
)


def _plan(**changes: object):
    values: dict[str, object] = {
        "task_id": "context-expansion-test",
        "objective": "Add an audited context expansion boundary to Company OS.",
        "required_capabilities": ("software_architecture",),
        "deterministic_execution_possible": False,
        "context": ContextRequirements(
            refs=(
                ContextRef(
                    ContextKind.FILE,
                    "company/runtime/packets.py",
                    "initial session boundary",
                ),
            ),
            constraints=("Keep all context reference-only.",),
            acceptance_criteria=("Every expansion decision is auditable.",),
        ),
    }
    values.update(changes)
    return plan_task(TaskSpecification(**values), load_company_config(ROOT / "company"))


def _packet(**changes: object) -> SessionPacket:
    plan = changes.pop("plan", None) or _plan()
    packet = build_session_packet(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(),
        employee_contract=contract_from_registry("chief_architect", plan.config),
    )
    return replace(packet, **changes) if changes else packet


def _read_contract(plan=None, *paths: str) -> dict[str, object]:
    current = plan or _plan()
    contract = contract_from_registry("chief_architect", current.config)
    contract["may_read"] = list(
        paths
        or (
            "company/**",
            "knowledge/**",
            "tests/**",
            "ai_platform/**",
        )
    )
    return contract


def _request(
    packet: SessionPacket,
    *refs: ContextRef,
    request_id: str = "expansion-001",
    sequence: int = 1,
    reason: str = "Need the exact dependency registration used by capsule lookup.",
    required_to_continue: bool = True,
) -> ContextExpansionRequest:
    return ContextExpansionRequest(
        task_id=packet.task_id,
        packet_fingerprint=packet.fingerprint(),
        request_id=request_id,
        requested_refs=tuple(refs or (INDEX_REF,)),
        reason=reason,
        requesting_executor=ExecutorHint.CODEX,
        sequence=sequence,
        required_to_continue=required_to_continue,
    )


def _receipt(
    packet: SessionPacket,
    *,
    ledger: ContextExpansionLedger | None = None,
    used: tuple[str, ...] = (),
) -> SessionReceipt:
    values: dict[str, object] = {
        "task_id": packet.task_id,
        "packet_fingerprint": packet.fingerprint(),
        "outcome": Outcome.ACCEPTED,
        "summary": "Expansion boundary implemented and verified.",
        "branch": BRANCH,
        "commit_sha": SHA,
        "remote_branch_sha": SHA,
        "remote_verified": True,
        "working_tree_clean": True,
        "context_refs_used": used,
        "context_usage_reported": True,
    }
    if ledger is not None and ledger.decisions:
        values.update(
            expansion_ledger_fingerprint=ledger.fingerprint(),
            effective_context_fingerprint=ledger.effective_context_fingerprint,
        )
    return SessionReceipt(**values)


def _prepare_for_expansion(
    adapter: ManualExternalSessionAdapter,
    plan,
    contract: dict[str, object],
):
    return adapter.prepare(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(),
        employee_contract=contract,
    )


def test_request_and_decision_are_deterministic_and_reference_only() -> None:
    packet = _packet()
    request = _request(packet)
    same = _request(packet)

    first = decide_context_expansion(packet, request, _read_contract(), repo_root=ROOT)
    second = decide_context_expansion(packet, same, _read_contract(), repo_root=ROOT)

    assert request == same
    assert request.fingerprint() == same.fingerprint()
    assert request.requested_kinds == (ContextKind.FILE,)
    assert first == second
    assert first.outcome is ExpansionOutcome.APPROVED
    assert first.approved_refs == (INDEX_REF,)
    assert INDEX_REF.reason in dumps(request)
    assert "class CapsuleIndex" not in dumps(request)


def test_reason_is_required_and_need_more_context_is_not_a_reason() -> None:
    packet = _packet()
    with pytest.raises(LifecycleError, match="missing fact"):
        _request(packet, reason="need more context")
    with pytest.raises(LifecycleError, match="missing fact"):
        _request(
            packet,
            ContextRef(ContextKind.FILE, INDEX_REF.ref, "need more context"),
        )
    with pytest.raises(LifecycleError, match="compact line"):
        _request(packet, reason="x" * 501)


def test_file_content_cannot_be_embedded_in_an_expansion_request() -> None:
    packet = _packet()
    with pytest.raises(ReferenceViolation, match="embedded content"):
        _request(
            packet,
            ContextRef(
                ContextKind.FILE,
                "def leaked():\n    return True",
                "inspect an exact helper",
            ),
        )


def test_packet_identity_stays_fixed_while_effective_context_changes() -> None:
    packet = _packet()
    before = packet.fingerprint()
    initial_context = packet.context_fingerprint
    decision = decide_context_expansion(
        packet, _request(packet), _read_contract(), repo_root=ROOT
    )
    ledger = ContextExpansionLedger.for_packet(packet).with_decision(decision)

    assert packet.fingerprint() == before
    assert packet.context_fingerprint == initial_context
    assert decision.previous_context_fingerprint == initial_context
    assert ledger.effective_context_fingerprint != initial_context
    assert ledger.effective_keys(packet) == packet.context_keys() + (INDEX_REF.key,)


def test_already_present_and_duplicate_expansions_do_not_add_a_ref_twice() -> None:
    packet = _packet()
    initial_request = _request(
        packet,
        packet.context_refs[0],
        reason="Need to recheck whether the initial packet contains this boundary.",
    )
    already = decide_context_expansion(
        packet, initial_request, _read_contract(), repo_root=ROOT
    )
    assert already.outcome is ExpansionOutcome.ALREADY_PRESENT
    assert already.approved_refs == ()
    assert already.already_present_refs == (packet.context_refs[0].key,)

    first = decide_context_expansion(
        packet, _request(packet), _read_contract(), repo_root=ROOT
    )
    ledger = ContextExpansionLedger.for_packet(packet).with_decision(first)
    duplicate = decide_context_expansion(
        packet,
        _request(packet, request_id="expansion-002", sequence=2),
        _read_contract(),
        ledger=ledger,
        repo_root=ROOT,
    )
    complete = ledger.with_decision(duplicate)
    assert duplicate.outcome is ExpansionOutcome.ALREADY_PRESENT
    assert complete.approved_refs == (INDEX_REF,)


def test_read_authority_fails_closed_and_never_changes_write_scope() -> None:
    packet = _packet()
    original_scope = packet.path_scope

    contract = _read_contract()
    contract["may_read"] = []
    empty = decide_context_expansion(packet, _request(packet), contract, repo_root=ROOT)
    outside = decide_context_expansion(
        packet,
        _request(packet),
        _read_contract(None, "company/**"),
        repo_root=ROOT,
    )
    forbidden_contract = _read_contract()
    forbidden_contract["may_not_read"] = [INDEX_REF.ref]
    forbidden = decide_context_expansion(
        packet, _request(packet), forbidden_contract, repo_root=ROOT
    )
    yaml_ref = ContextRef(
        ContextKind.FILE,
        "company/org_registry.yaml",
        "inspect the exact employee registry names",
    )
    wildcard = decide_context_expansion(
        packet,
        _request(packet, yaml_ref),
        _read_contract(None, "company/*.yaml"),
        repo_root=ROOT,
    )

    assert empty.outcome is ExpansionOutcome.REJECTED
    assert "may_read is empty" in empty.rejected_refs[0].reason
    assert outside.outcome is ExpansionOutcome.REJECTED
    assert "outside employee may_read" in outside.rejected_refs[0].reason
    assert forbidden.outcome is ExpansionOutcome.REJECTED
    assert "may_not_read" in forbidden.rejected_refs[0].reason
    assert wildcard.outcome is ExpansionOutcome.APPROVED
    assert packet.path_scope == original_scope
    assert packet.path_scope.read_only


def test_context_ceiling_is_an_explicit_rejection_without_reclassification() -> None:
    packet = _packet()
    ceiling = resource_class(packet.reasoning_class).max_context_refs
    refs = tuple(
        ContextRef(
            ContextKind.FILE, f"company/runtime/ref_{index}.py", f"initial {index}"
        )
        for index in range(ceiling)
    )
    full = replace(
        packet,
        context_refs=refs,
        explicit_context_refs=tuple(ref.key for ref in refs),
        automatic_context_refs=(),
        context_fingerprint=fingerprint(refs),
    )
    decision = decide_context_expansion(
        full, _request(full), _read_contract(), repo_root=ROOT
    )

    assert decision.outcome is ExpansionOutcome.REJECTED
    assert f"ceiling of {ceiling} refs" in decision.rejected_refs[0].reason
    assert "not silently reclassified" in decision.rejected_refs[0].reason
    assert full.reasoning_class == packet.reasoning_class


def test_broad_path_prefers_a_capsule_but_narrow_file_remains_exact() -> None:
    packet = _packet()
    initial = (packet.context_refs[-1],)
    lean_packet = replace(
        packet,
        context_refs=initial,
        explicit_context_refs=(initial[0].key,),
        automatic_context_refs=(),
        context_fingerprint=fingerprint(initial),
    )
    broad = ContextRef(
        ContextKind.FILE,
        "knowledge/company_os/capsules",
        "inspect the capsule subsystem contract",
    )
    broad_decision = decide_context_expansion(
        lean_packet, _request(lean_packet, broad), _read_contract(), repo_root=ROOT
    )
    narrow_decision = decide_context_expansion(
        lean_packet, _request(lean_packet), _read_contract(), repo_root=ROOT
    )

    assert broad_decision.approved_refs[0].kind is ContextKind.MODULE_CONTRACT
    assert broad_decision.approved_refs[0].ref == "capsule:company-knowledge-capsules"
    assert narrow_decision.approved_refs == (INDEX_REF,)


def test_requests_and_all_decisions_are_append_only_history(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare_for_expansion(
        adapter, plan, _read_contract(plan, INDEX_REF.ref)
    )
    packet = prepared.packet
    original_fingerprint = packet.fingerprint()

    denied = adapter.expand_context(
        packet,
        _request(
            packet,
            ContextRef(
                ContextKind.FILE,
                "race2/track.py",
                "inspect an explicitly out-of-scope production file",
            ),
        ),
        repo_root=ROOT,
    )
    approved = adapter.expand_context(
        packet,
        _request(packet, request_id="expansion-002", sequence=2),
        repo_root=ROOT,
    )

    assert denied.decision.outcome is ExpansionOutcome.REJECTED
    assert approved.decision.outcome is ExpansionOutcome.APPROVED
    assert len(store.context_expansion_requests(packet.task_id)) == 2
    assert len(store.context_expansion_decisions(packet.task_id)) == 2
    assert denied.request_pointer.record_ref != approved.request_pointer.record_ref
    assert denied.decision_pointer.record_ref != approved.decision_pointer.record_ref
    assert "execution/context_expansions/" in approved.decision_pointer.record_ref
    assert packet.fingerprint() == original_fingerprint
    history = store.history(packet.task_id)["context_expansions"]
    assert [item["outcome"] for item in history["decisions"]] == [
        "rejected",
        "approved",
    ]
    ingested = adapter.ingest(
        plan,
        packet,
        _receipt(
            packet,
            ledger=approved.ledger,
            used=(packet.context_keys()[0], INDEX_REF.key),
        ),
        ResourceUsageStore(tmp_path),
    )
    assert ingested.accepted
    telemetry = EfficiencyStore(tmp_path).records(packet.task_id)[0]
    assert (
        telemetry.context_expansion_requests,
        telemetry.context_expansion_approvals,
        telemetry.context_expansion_denials,
    ) == (2, 1, 1)


def test_receipt_refuses_unapproved_context_and_a_foreign_ledger() -> None:
    packet = _packet()
    unapproved = _receipt(packet, used=(INDEX_REF.key,))
    validation = validate_receipt(packet, unapproved)
    assert any(
        "neither the packet nor an approved expansion" in item
        for item in validation.failures
    )

    foreign_packet = replace(packet, task_id="another-task")
    foreign = ContextExpansionLedger.for_packet(foreign_packet)
    validation = validate_receipt(packet, _receipt(packet), expansion_ledger=foreign)
    assert any("another task or packet" in item for item in validation.failures)


def test_dogfood_missing_index_case_is_approved_linked_and_measured(
    tmp_path: Path,
) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare_for_expansion(adapter, plan, _read_contract(plan))
    packet = prepared.packet
    packet_fingerprint = packet.fingerprint()
    assert INDEX_REF.key not in packet.context_keys()
    expanded = adapter.expand_context(
        packet,
        _request(packet),
        repo_root=ROOT,
    )
    assert expanded.decision.outcome is ExpansionOutcome.APPROVED
    assert packet.fingerprint() == packet_fingerprint

    used = (packet.context_keys()[0], INDEX_REF.key)
    ingested = adapter.ingest(
        plan,
        packet,
        _receipt(packet, ledger=expanded.ledger, used=used),
        ResourceUsageStore(tmp_path),
    )
    record = ingested.attempt.usage_record

    assert ingested.accepted
    assert record.initial_context_sources == packet.context_keys()
    assert record.expanded_context_sources == (INDEX_REF.key,)
    assert record.rejected_expansion_sources == ()
    assert record.initial_context_fingerprint == packet.context_fingerprint
    assert (
        record.effective_context_fingerprint
        == expanded.ledger.effective_context_fingerprint
    )
    assert record.expansion_ledger_fingerprint == expanded.ledger.fingerprint()
    assert record.initial_context_sufficient is False
    assert record.expansion_count == 1
    assert record.required_expansion_count == 1
    assert record.expansion_chars > 0
    assert record.initial_ref_count == len(packet.context_keys())
    assert record.expanded_ref_count == 1
    assert record.rejected_expansion_ref_count == 0
    assert record.used_initial_ref_count == 1
    assert record.used_expansion_ref_count == 1
    assert record.unused_initial_ref_count == len(packet.context_keys()) - 1
    assert record.unused_expansion_refs == ()
    assert record.unused_expansion_ref_count == 0
    assert record.context_precision == pytest.approx(2 / len(record.context_sources))


def test_rejected_expansions_flow_into_usage_without_becoming_context(
    tmp_path: Path,
) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    denied_contract = _read_contract(plan)
    denied_contract["may_read"] = []
    packet = _prepare_for_expansion(adapter, plan, denied_contract).packet
    expanded = adapter.expand_context(
        packet,
        _request(packet),
        repo_root=ROOT,
    )
    receipt = _receipt(packet, ledger=expanded.ledger, used=())
    ingested = adapter.ingest(plan, packet, receipt, ResourceUsageStore(tmp_path))

    record = ingested.attempt.usage_record
    assert record.expanded_context_sources == ()
    assert record.rejected_expansion_sources == (INDEX_REF.key,)
    assert record.expansion_count == 0
    assert record.initial_context_sufficient is True


def test_helpful_approved_context_does_not_claim_initial_context_was_insufficient(
    tmp_path: Path,
) -> None:
    plan = _plan()
    adapter = ManualExternalSessionAdapter(ExecutionStore(tmp_path))
    packet = _prepare_for_expansion(adapter, plan, _read_contract(plan)).packet
    expanded = adapter.expand_context(
        packet,
        _request(packet, required_to_continue=False),
        repo_root=ROOT,
    )
    ingested = adapter.ingest(
        plan,
        packet,
        _receipt(packet, ledger=expanded.ledger),
        ResourceUsageStore(tmp_path),
    )
    record = ingested.attempt.usage_record
    assert record.expansion_count == 1
    assert record.required_expansion_count == 0
    assert record.initial_context_sufficient is True


def test_context_precision_is_absent_when_executor_does_not_report_usage(
    tmp_path: Path,
) -> None:
    plan = _plan()
    packet = _packet(plan=plan)
    adapter = ManualExternalSessionAdapter(ExecutionStore(tmp_path))
    receipt = replace(_receipt(packet), context_usage_reported=False)
    ingested = adapter.ingest(plan, packet, receipt, ResourceUsageStore(tmp_path))
    record = ingested.attempt.usage_record
    assert record.context_precision is None
    assert record.used_initial_ref_count is None
    assert record.used_expansion_ref_count is None
    assert record.unused_initial_ref_count is None
    assert record.unused_expansion_refs is None


def test_request_decision_and_usage_round_trip_through_json(tmp_path: Path) -> None:
    plan = _plan()
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = _prepare_for_expansion(adapter, plan, _read_contract(plan))
    packet = prepared.packet
    request = _request(packet)
    decision = decide_context_expansion(
        packet,
        request,
        prepared.authority.as_contract(),
        repo_root=ROOT,
        authority_fingerprint=prepared.authority.fingerprint(),
    )
    assert ContextExpansionRequest.from_mapping(json.loads(dumps(request))) == request
    assert (
        ContextExpansionDecision.from_mapping(json.loads(dumps(decision))) == decision
    )

    store.append_context_expansion_request(request)
    store.append_context_expansion_decision(decision)
    assert store.context_expansion_requests(packet.task_id) == (request,)
    assert store.context_expansion_decisions(packet.task_id) == (decision,)


def test_no_subagent_rule_holds_at_every_expansion_boundary() -> None:
    packet = _packet()
    request = _request(packet)
    decision = decide_context_expansion(
        packet, request, _read_contract(), repo_root=ROOT
    )
    ledger = ContextExpansionLedger.for_packet(packet).with_decision(decision)
    assert request.no_subagents is decision.no_subagents is ledger.no_subagents is True
    with pytest.raises(SubagentPolicyViolation, match="must be true"):
        replace(request, no_subagents=False)
    with pytest.raises(SubagentPolicyViolation, match="must be true"):
        replace(decision, no_subagents=False)
    with pytest.raises(SubagentPolicyViolation, match="must be true"):
        replace(ledger, no_subagents=False)


def test_expansion_module_has_no_provider_network_or_agent_launcher_imports() -> None:
    text = "\n".join(
        (ROOT / "company/runtime" / name).read_text(encoding="utf-8").casefold()
        for name in ("context_expansion.py", "context_expansion_policy.py")
    )
    for token in (
        "import subprocess",
        "import anthropic",
        "import openai",
        "multiprocessing",
        "os.system",
        "popen",
        "asyncio",
        "import requests",
        "import chromadb",
        "import faiss",
    ):
        assert token not in text
