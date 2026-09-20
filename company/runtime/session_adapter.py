"""The first execution adapter, and deliberately the smallest one that works.

`ManualExternalSessionAdapter` writes a packet to an outbox and later reads a
receipt back. That is the entire contract. It does not start a process, call an
API, import a vendor SDK, or know the name of any tool - a hint may say
`claude_code` or `codex`, and nothing here reads it.

That is a design position, not a gap. In Bootstrap Mode the executor is an
independent top-level session a human starts; making the runtime able to launch
one would build, in order, a launcher, a supervisor and a scheduler - the exact
shape constitution rule 2 forbids and rule 17 says to prove the need for first.
The boundary that is actually needed is a serialised request and a validated
reply, and this is it.

## What ingestion guarantees

One returned receipt produces, in order:

1. the receipt persisted, valid or not, at its own attempt number;
2. a `ReceiptValidation` against the packet - path scope, git evidence shape,
   required tests, evidence, branch;
3. one canonical `ResourceUsageRecord`, through the existing `finalise_attempt`;
4. one compact `HandoffArtifact` pointing at that record and at the receipt.

A receipt that fails validation is recorded as a **rejected** attempt rather
than discarded, with the failures as its rejection reason. A later attempt
lands beside it as a new record, never over it. A claim of `subagents_used > 0`
is the one case that stops the pipeline after step 1: the evidence is kept, and
nothing downstream is allowed to exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from typing import Any

from ai_platform.usage import Outcome
from knowledge.company_os.capsules import CapsuleIndex

from .attempts import AttemptReport, AttemptResult, finalise_attempt
from .authority import AuthoritySource, ExecutionAuthoritySnapshot
from .context_expansion import (
    ContextExpansionDecision,
    ContextExpansionLedger,
    ContextExpansionRequest,
)
from .context_expansion_policy import decide_context_expansion
from .errors import LifecycleError
from .execution_store import ExecutionRecordPointer, ExecutionStore, PacketRecord
from .git_evidence import repository_findings
from .lifecycle import TaskPlan, contract_from_registry
from .packets import ExecutorHint, SessionPacket, build_session_packet
from .path_scope import PathScope
from .receipts import ReceiptValidation, SessionReceipt, validate_receipt
from .usage_store import ResourceUsageStore


def authority_for(
    plan: TaskPlan,
    packet: SessionPacket,
    *,
    packet_attempt: int,
    employee_contract: Mapping[str, Any] | None = None,
) -> ExecutionAuthoritySnapshot:
    """The authority snapshot one packet attempt would be prepared under.

    Computing it does not persist it. `prepare` writes what this returns, and a
    caller that is not persisting anything - the CLI building a packet with no
    outbox - can still show the operator the fingerprint and source of the grant
    it just handed out. Both go through here so the two can never disagree about
    which source a contract came from.
    """
    contract = (
        employee_contract
        if employee_contract is not None
        else contract_from_registry(plan.selected_employee, plan.config)
    )
    return ExecutionAuthoritySnapshot.from_contract(
        task_id=packet.task_id,
        employee=packet.employee,
        packet_fingerprint=packet.fingerprint(),
        packet_attempt=packet_attempt,
        contract=contract,
        source=(
            AuthoritySource.TEMPORARY_TASK_OVERRIDE
            if employee_contract is not None
            else AuthoritySource.CANONICAL_CONTRACT
        ),
    )


@dataclass(frozen=True)
class PreparedSession:
    """A packet, and where it was written for an external session to collect."""

    packet: SessionPacket
    pointer: ExecutionRecordPointer
    authority: ExecutionAuthoritySnapshot
    authority_pointer: ExecutionRecordPointer


@dataclass(frozen=True)
class IngestedSession:
    """One returned attempt: the evidence, the verdict, and what was recorded."""

    receipt: SessionReceipt
    receipt_pointer: ExecutionRecordPointer
    validation: ReceiptValidation
    attempt: AttemptResult
    efficiency_pointer: ExecutionRecordPointer | None = None
    telemetry_error: str = ""

    @property
    def accepted(self) -> bool:
        return self.attempt.usage_record.outcome is Outcome.ACCEPTED


@dataclass(frozen=True)
class ExpandedSession:
    """One persisted request, its persisted decision, and the resulting ledger."""

    request: ContextExpansionRequest
    request_pointer: ExecutionRecordPointer
    decision: ContextExpansionDecision
    decision_pointer: ExecutionRecordPointer
    ledger: ContextExpansionLedger


class ManualExternalSessionAdapter:
    """Serialise a prepared task out; validate and record what comes back."""

    def __init__(self, store: ExecutionStore) -> None:
        self.store = store

    def prepare(
        self,
        plan: TaskPlan,
        *,
        expected_branch: str,
        path_scope: PathScope | None = None,
        required_tests: tuple[str, ...] = (),
        expected_base_commit: str = "",
        executor: ExecutorHint = ExecutorHint.UNSPECIFIED,
        employee_contract: Mapping[str, Any] | None = None,
    ) -> PreparedSession:
        """Build one packet from a prepared plan and persist it to the outbox."""
        packet = build_session_packet(
            plan,
            expected_branch=expected_branch,
            path_scope=path_scope,
            required_tests=required_tests,
            expected_base_commit=expected_base_commit,
            executor=executor,
            employee_contract=employee_contract,
        )
        pointer = self.store.append_packet(packet)
        authority = authority_for(
            plan,
            packet,
            packet_attempt=pointer.attempt,
            employee_contract=employee_contract,
        )
        authority_pointer = self.store.append_authority(authority)
        return PreparedSession(
            packet=packet,
            pointer=pointer,
            authority=authority,
            authority_pointer=authority_pointer,
        )

    def ingest(
        self,
        plan: TaskPlan,
        packet: SessionPacket,
        receipt: SessionReceipt,
        usage_store: ResourceUsageStore,
        *,
        repo_dir: str | Path | None = None,
        expansion_ledger: ContextExpansionLedger | None = None,
        tool_outputs: tuple[Any, ...] = (),
    ) -> IngestedSession:
        """Validate one receipt and record the attempt it describes.

        `repo_dir` is optional and additive: when a local clone is available,
        the receipt's branch and remote claims are compared with the refs that
        clone actually holds, and any disagreement joins the validation
        failures. Without it the shape checks still run, so ingestion works on
        a machine that has never seen the repository.
        """
        _assert_plan_matches_packet(plan, packet)
        packet_record = self._resolve_packet_record(packet, receipt.packet_attempt)
        authority = self.store.authority(
            packet.task_id, packet.fingerprint(), packet_record.attempt
        )
        ledger = expansion_ledger or self.store.context_expansion_ledger(
            packet, packet_attempt=packet_record.attempt
        )
        receipt = _associate_receipt(
            receipt,
            packet_attempt=packet_record.attempt,
            authority=authority,
            ledger=ledger,
        )
        pointer = self.store.append_receipt(receipt)
        plan.policy.assert_no_subagents(receipt.subagents_used)
        validation = _widen(
            validate_receipt(
                packet,
                receipt,
                expansion_ledger=ledger,
                packet_attempt=packet_record.attempt,
                authority_fingerprint=(
                    authority.fingerprint() if authority is not None else ""
                ),
            ),
            _owner_failures(plan, receipt) + _repository_failures(receipt, repo_dir),
        )
        usable_ledger = _ledger_for_recording(packet, ledger)
        report = _attempt_report(
            plan, packet, receipt, validation, pointer, usable_ledger
        )
        attempt = finalise_attempt(
            plan, report, usage_store, expansion_ledger=usable_ledger
        )
        efficiency_pointer = None
        telemetry_error = ""
        try:
            # Imported only at finalization so the core runtime remains usable
            # without importing optional reporting code during preparation.
            # Efficiency is an execution-store extension. Resolve it only
            # after canonical finalization so runtime keeps a one-way static
            # dependency graph and remains usable without the extension.
            emitter = import_module(
                "company.efficiency.emission"
            ).emit_execution_efficiency
            emission = emitter(
                plan=plan,
                packet=packet,
                packet_attempt=packet_record.attempt,
                receipt=receipt,
                receipt_pointer=pointer,
                outcome=attempt.usage_record.outcome,
                state_dir=self.store.state_dir,
                expansion_ledger=usable_ledger,
                tool_outputs=tool_outputs,
            )
            efficiency_pointer = emission.pointer
        except Exception as exc:  # observational telemetry cannot replace the result
            telemetry_error = f"{type(exc).__name__}: {exc}"
        return IngestedSession(
            receipt=receipt,
            receipt_pointer=pointer,
            validation=validation,
            attempt=attempt,
            efficiency_pointer=efficiency_pointer,
            telemetry_error=telemetry_error,
        )

    def expand_context(
        self,
        packet: SessionPacket,
        request: ContextExpansionRequest,
        *,
        capsule_index: CapsuleIndex | None = None,
        repo_root: str | Path | None = None,
    ) -> ExpandedSession:
        """Persist and decide one request using only preparation-time authority."""
        request_pointer = self.store.append_context_expansion_request(request)
        return self.decide_context(
            packet,
            request,
            request_pointer=request_pointer,
            capsule_index=capsule_index,
            repo_root=repo_root,
        )

    def decide_context(
        self,
        packet: SessionPacket,
        request: ContextExpansionRequest,
        *,
        request_pointer: ExecutionRecordPointer | None = None,
        capsule_index: CapsuleIndex | None = None,
        repo_root: str | Path | None = None,
    ) -> ExpandedSession:
        """Decide a persisted request from its immutable authority snapshot."""
        stored = self.store.find_context_expansion_request(
            request.task_id, request.request_id
        )
        if stored is None or stored != request:
            raise LifecycleError(
                "context expansion request must be persisted unchanged before decision"
            )
        if any(
            decision.request_id == request.request_id
            for decision in self.store.context_expansion_decisions(request.task_id)
        ):
            raise LifecycleError(
                f"context expansion request {request.request_id!r} already has a decision"
            )
        record = self.store.find_packet_record(
            request.task_id,
            request.packet_fingerprint,
            attempt=request.packet_attempt,
        )
        if record is None or record.packet != packet:
            raise LifecycleError(
                "context expansion request does not match a persisted packet attempt"
            )
        authority = self.store.authority(
            request.task_id, request.packet_fingerprint, request.packet_attempt
        )
        if authority is None:
            raise LifecycleError(
                "context expansion is denied: the packet attempt has no immutable "
                "execution authority snapshot"
            )
        ledger = self.store.context_expansion_ledger(
            packet, packet_attempt=request.packet_attempt
        )
        decision = decide_context_expansion(
            packet,
            request,
            authority.as_contract(),
            ledger=ledger,
            capsule_index=capsule_index,
            repo_root=repo_root,
            authority_fingerprint=authority.fingerprint(),
        )
        decision_pointer = self.store.append_context_expansion_decision(decision)
        pointer = request_pointer or _request_pointer(self.store, request)
        return ExpandedSession(
            request=request,
            request_pointer=pointer,
            decision=decision,
            decision_pointer=decision_pointer,
            ledger=ledger.with_decision(decision),
        )

    def _resolve_packet_record(
        self, packet: SessionPacket, requested_attempt: int
    ) -> PacketRecord:
        if requested_attempt:
            record = self.store.find_packet_record(
                packet.task_id, packet.fingerprint(), attempt=requested_attempt
            )
            if record is None:
                raise LifecycleError(
                    f"no persisted packet attempt {requested_attempt} matches receipt"
                )
            return record
        records = tuple(
            record
            for record in self.store.packet_records(packet.task_id)
            if record.packet.fingerprint() == packet.fingerprint()
        )
        if not records:
            pointer = self.store.append_packet(packet)
            return PacketRecord(pointer.attempt, pointer, packet)
        completed = {
            item.receipt.packet_attempt
            for item in self.store.attempts(packet.task_id)
            if item.receipt.packet_attempt
        }
        incomplete = tuple(
            record for record in records if record.attempt not in completed
        )
        return (incomplete or records)[-1]


def _widen(
    validation: ReceiptValidation, failures: tuple[str, ...]
) -> ReceiptValidation:
    if not failures:
        return validation
    # An owner or repository-evidence failure is a real defect, never a
    # formatting one, so a receipt widened this way can no longer be
    # `evidence_format_only` even if `validate_receipt` found nothing but the
    # required-test evidence gap on its own.
    return replace(
        validation,
        failures=validation.failures + failures,
        evidence_format_only=False,
    )


def _associate_receipt(
    receipt: SessionReceipt,
    *,
    packet_attempt: int,
    authority: ExecutionAuthoritySnapshot | None,
    ledger: ContextExpansionLedger,
) -> SessionReceipt:
    """Attach stored evidence when omitted; preserve supplied values for validation."""
    changes: dict[str, Any] = {}
    if receipt.packet_attempt == 0:
        changes["packet_attempt"] = packet_attempt
    if authority is not None and not receipt.authority_fingerprint:
        changes["authority_fingerprint"] = authority.fingerprint()
    if ledger.decisions:
        if not receipt.expansion_ledger_fingerprint:
            changes["expansion_ledger_fingerprint"] = ledger.fingerprint()
        if not receipt.effective_context_fingerprint:
            changes["effective_context_fingerprint"] = (
                ledger.effective_context_fingerprint
            )
    return replace(receipt, **changes) if changes else receipt


def _request_pointer(
    store: ExecutionStore, request: ContextExpansionRequest
) -> ExecutionRecordPointer:
    pointer = store.context_expansion_request_pointer(
        request.task_id, request.request_id
    )
    if pointer is None:
        raise LifecycleError(
            f"context expansion request {request.request_id!r} is not persisted"
        )
    return pointer


def _known_owners(plan: TaskPlan) -> set[str]:
    return set(plan.config.org_registry["employees"]) | {"ceo"}


def _owner_failures(plan: TaskPlan, receipt: SessionReceipt) -> tuple[str, ...]:
    """A receipt may name the next owner; it may not invent one.

    The handoff schema already refuses an unknown employee. Catching it here
    turns what would be an exception mid-ingestion into an ordinary rejected
    attempt, so the receipt that caused it still lands in the history.
    """
    if receipt.next_owner and receipt.next_owner not in _known_owners(plan):
        return (
            f"next_owner {receipt.next_owner!r} is not an employee in the registry",
        )
    return ()


def _repository_failures(
    receipt: SessionReceipt, repo_dir: str | Path | None
) -> tuple[str, ...]:
    if repo_dir is None or not receipt.branch:
        return ()
    return tuple(
        f"repository evidence: {finding}"
        for finding in repository_findings(
            repo_dir, receipt.branch, receipt.commit_sha, receipt.remote_branch_sha
        )
    )


def _assert_plan_matches_packet(plan: TaskPlan, packet: SessionPacket) -> None:
    """Refuse to record an attempt against a plan that is not the packet's plan.

    A packet is persisted; a plan is rebuilt. If the two disagree - a different
    task, a different owner, or a context manifest that has since changed - the
    usage record would describe context the session never received.
    """
    if not plan.ready or plan.preparation is None:
        raise LifecycleError(
            f"task {plan.specification.task_id} is {plan.state.value}, not "
            "execution_prepared; it cannot ingest a result"
        )
    mismatches = []
    if plan.specification.task_id != packet.task_id:
        mismatches.append(
            f"task {plan.specification.task_id!r} against packet {packet.task_id!r}"
        )
    if plan.selected_employee != packet.employee:
        mismatches.append(
            f"employee {plan.selected_employee!r} against packet {packet.employee!r}"
        )
    if plan.preparation.context_fingerprint != packet.context_fingerprint:
        mismatches.append(
            f"context {plan.preparation.context_fingerprint} against packet "
            f"{packet.context_fingerprint}"
        )
    if mismatches:
        raise LifecycleError(
            "the supplied plan does not match the packet: " + "; ".join(mismatches)
        )


def _attempt_report(
    plan: TaskPlan,
    packet: SessionPacket,
    receipt: SessionReceipt,
    validation: ReceiptValidation,
    pointer: ExecutionRecordPointer,
    expansion_ledger: ContextExpansionLedger | None,
) -> AttemptReport:
    outcome = receipt.outcome if validation.ok else Outcome.REJECTED
    rejection_reason = ""
    if outcome is Outcome.REJECTED:
        rejection_reason = (
            receipt.rejection_reason.strip() if validation.ok else validation.reason()
        ) or "the returned receipt did not satisfy the packet"

    evidence = list(receipt.evidence)
    if receipt.commit_sha:
        commit_ref = f"commit:{receipt.commit_sha}"
        if commit_ref not in evidence:
            evidence.append(commit_ref)

    artifacts = list(receipt.artifacts)
    if pointer.record_ref not in artifacts:
        artifacts.append(pointer.record_ref)

    # `ResourceUsageRecord` refuses context the manifest never supplied, and a
    # rejected attempt must still be recordable, so the report carries only the
    # refs the packet actually contained. Validation reports the rest.
    supplied = set(packet.context_keys())
    if expansion_ledger is not None:
        supplied.update(ref.key for ref in expansion_ledger.approved_refs)
    refs_used = tuple(ref for ref in receipt.context_refs_used if ref in supplied)

    escalation_reason = ""
    if receipt.dependencies_added:
        escalation_reason = (
            "new dependency declared ("
            + ", ".join(receipt.dependencies_added)
            + "); permissions.yaml requires architecture_and_security_review"
        )

    notes = receipt.notes
    if receipt.invariants_preserved:
        invariants = "invariants preserved: " + "; ".join(receipt.invariants_preserved)
        notes = f"{notes}\n{invariants}".strip() if notes else invariants

    usage = receipt.usage
    return AttemptReport(
        outcome=outcome,
        result=receipt.summary,
        evidence=tuple(evidence),
        artifacts=tuple(artifacts),
        changed=tuple(receipt.files_changed),
        unchanged=(),
        tests=receipt.test_commands,
        risks=tuple(receipt.unresolved_risks),
        context_refs_used=refs_used,
        context_usage_reported=(
            receipt.context_usage_reported or bool(receipt.context_refs_used)
        ),
        next_owner=(
            receipt.next_owner if receipt.next_owner in _known_owners(plan) else ""
        ),
        escalation_reason=escalation_reason,
        passes=usage.passes,
        retries=usage.retries,
        cache_hits=usage.cache_hits,
        retrieval_hits=usage.retrieval_hits,
        subagents_used=receipt.subagents_used,
        tool_calls=usage.tool_calls,
        input_units=usage.input_units,
        output_units=usage.output_units,
        usage_unit=usage.usage_unit,
        duration_s=usage.duration_s,
        rejection_reason=rejection_reason,
        notes=notes,
    )


def _ledger_for_recording(
    packet: SessionPacket, ledger: ContextExpansionLedger
) -> ContextExpansionLedger | None:
    """Invalid foreign history rejects a receipt but must not abort its audit record."""
    try:
        ledger.assert_for_packet(packet)
    except LifecycleError:
        return None
    return ledger


__all__ = [
    "ExpandedSession",
    "IngestedSession",
    "ManualExternalSessionAdapter",
    "PreparedSession",
]
