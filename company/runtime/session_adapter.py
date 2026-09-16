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
from pathlib import Path
from typing import Any

from ai_platform.usage import Outcome

from .attempts import AttemptReport, AttemptResult, finalise_attempt
from .errors import LifecycleError
from .execution_store import ExecutionRecordPointer, ExecutionStore
from .git_evidence import repository_findings
from .lifecycle import TaskPlan
from .packets import ExecutorHint, SessionPacket, build_session_packet
from .path_scope import PathScope
from .receipts import ReceiptValidation, SessionReceipt, validate_receipt
from .usage_store import ResourceUsageStore


@dataclass(frozen=True)
class PreparedSession:
    """A packet, and where it was written for an external session to collect."""

    packet: SessionPacket
    pointer: ExecutionRecordPointer


@dataclass(frozen=True)
class IngestedSession:
    """One returned attempt: the evidence, the verdict, and what was recorded."""

    receipt: SessionReceipt
    receipt_pointer: ExecutionRecordPointer
    validation: ReceiptValidation
    attempt: AttemptResult

    @property
    def accepted(self) -> bool:
        return self.attempt.usage_record.outcome is Outcome.ACCEPTED


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
        return PreparedSession(packet=packet, pointer=self.store.append_packet(packet))

    def ingest(
        self,
        plan: TaskPlan,
        packet: SessionPacket,
        receipt: SessionReceipt,
        usage_store: ResourceUsageStore,
        *,
        repo_dir: str | Path | None = None,
    ) -> IngestedSession:
        """Validate one receipt and record the attempt it describes.

        `repo_dir` is optional and additive: when a local clone is available,
        the receipt's branch and remote claims are compared with the refs that
        clone actually holds, and any disagreement joins the validation
        failures. Without it the shape checks still run, so ingestion works on
        a machine that has never seen the repository.
        """
        _assert_plan_matches_packet(plan, packet)

        pointer = self.store.append_receipt(receipt)
        plan.policy.assert_no_subagents(receipt.subagents_used)

        validation = _widen(
            validate_receipt(packet, receipt),
            _owner_failures(plan, receipt) + _repository_failures(receipt, repo_dir),
        )
        report = _attempt_report(plan, packet, receipt, validation, pointer)
        attempt = finalise_attempt(plan, report, usage_store)
        return IngestedSession(
            receipt=receipt,
            receipt_pointer=pointer,
            validation=validation,
            attempt=attempt,
        )


def _widen(validation: ReceiptValidation, failures: tuple[str, ...]) -> ReceiptValidation:
    if not failures:
        return validation
    return replace(validation, failures=validation.failures + failures)


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
) -> AttemptReport:
    outcome = receipt.outcome if validation.ok else Outcome.REJECTED
    rejection_reason = ""
    if outcome is Outcome.REJECTED:
        rejection_reason = (
            receipt.rejection_reason.strip()
            if validation.ok
            else validation.reason()
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


__all__ = [
    "IngestedSession",
    "ManualExternalSessionAdapter",
    "PreparedSession",
]
