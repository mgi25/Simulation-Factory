"""The deterministic driver: one function per stage, each one a recorded move.

This module is the loop. It holds no reasoning and it starts no process — it
takes the record that arrived, validates it against the work order, asks the
existing runtime to do the runtime's part, appends what happened, and moves the
job's state.

    open_job                 request + work order + plan + job, all persisted
    prepare_developer_session  -> a SessionPacket for an external session
    ingest_developer_result    <- a SessionReceipt, validated and recorded
    prepare_review_session     -> a read-only SessionPacket for the reviewer
    record_review              <- a ReviewerAttestation, adjudicated
    record_gate                <- a GateVerdict, read from the gate's own report
    publish_result             -> the CEO page
    record_decision            <- the CEO's answer, recorded and not acted on

## What is reused rather than rebuilt

Everything that already exists. `plan_task` classifies and routes;
`ManualExternalSessionAdapter` builds the packet, captures the immutable
authority snapshot, validates the receipt, writes the canonical usage record
and produces the compact handoff. This module adds no second execution path —
`prepare_developer_session` is thirty lines of which the important one is
`adapter.prepare(...)`.

## The one place authority is narrowed

`plan_task` is called twice, deliberately. The first call routes the work order
to an employee; the second is given
`EngineeringWorkOrder.employee_contract(config, employee)`, which is that
employee's canonical contract with `may_write` set to the work order's
authorized paths and `may_not_modify` set to its forbidden and protected ones.
`build_session_packet` then re-reads that contract and refuses a packet scope
outside it. The double call is the same idiom `company/runtime/execution_cli.py`
uses for its `--authority-override-file`; the difference is that here the
override is **derived from the work order** instead of supplied by whoever ran
the command.

## Why every stage takes a day

`on=` is passed in, never read from a clock. Two runs over the same evidence
must produce the same records, and a self-stamping record would give a work
order two fingerprints.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import datetime as dt
from pathlib import Path

from ai_platform.usage import Outcome
from company.config_types import CompanyConfig
from company.efficiency.profile import resource_profile
from company.runtime.context_assembly import ContextAssemblyPolicy
from company.runtime.context_expansion import ContextExpansionLedger
from company.runtime.execution_store import ExecutionStore
from company.runtime.lifecycle import TaskPlan, plan_task
from company.runtime.packets import ExecutorHint, SessionPacket
from company.runtime.receipts import ReceiptValidation, SessionReceipt, validate_receipt
from company.runtime.session_adapter import (
    IngestedSession,
    ManualExternalSessionAdapter,
    PreparedSession,
)
from company.runtime.usage_store import ResourceUsageStore

from .common import assert_day
from .decision import CEODecision
from .errors import AuthorityEscalation, EngineeringError
from .gate_evidence import GateVerdict
from .intake import IntakeAssessment, IntakeOutcome
from .lifecycle import EngineeringJob, JobState
from .plan import ImplementationPlan, derive_plan
from .result import EngineeringResult, ResultTest
from .review import EngineeringReview, ReviewerAttestation, ReviewOutcome, adjudicate
from .store import EngineeringRecordPointer, EngineeringStore
from .work_order import EngineeringWorkOrder


@dataclass(frozen=True)
class OpenedJob:
    """A persisted request, work order, plan and job, ready for a developer."""

    work_order: EngineeringWorkOrder
    plan: ImplementationPlan
    job: EngineeringJob
    request_pointer: EngineeringRecordPointer
    work_order_pointer: EngineeringRecordPointer
    plan_pointer: EngineeringRecordPointer
    job_pointer: EngineeringRecordPointer


@dataclass(frozen=True)
class DeveloperBriefing:
    """What an external developer session is handed, and where it was recorded."""

    work_order: EngineeringWorkOrder
    plan: TaskPlan
    prepared: PreparedSession
    employee: str
    job: EngineeringJob
    job_pointer: EngineeringRecordPointer
    ledger: ContextExpansionLedger

    @property
    def packet(self) -> SessionPacket:
        return self.prepared.packet


@dataclass(frozen=True)
class ReviewBriefing:
    """What an external reviewer session is handed: read-only, and someone else."""

    work_order: EngineeringWorkOrder
    plan: TaskPlan
    prepared: PreparedSession
    reviewer: str
    implementer: str
    job: EngineeringJob
    job_pointer: EngineeringRecordPointer
    ledger: ContextExpansionLedger

    @property
    def packet(self) -> SessionPacket:
        return self.prepared.packet


@dataclass(frozen=True)
class DeveloperResult:
    """One ingested developer attempt and the job state it produced.

    `job_pointer` is `None` exactly when the job did not move: the receipt's
    evidence envelope was rejected on its own shape
    (`validation.evidence_format_only`), so nothing here consumed the
    developer's attempt or left `developing`. The receipt itself is always
    persisted regardless - see `ManualExternalSessionAdapter.ingest` - so the
    rejection is in the audit history even though the job is not.
    """

    ingested: IngestedSession
    job: EngineeringJob
    job_pointer: EngineeringRecordPointer | None = None

    @property
    def receipt(self) -> SessionReceipt:
        return self.ingested.receipt

    @property
    def validation(self) -> ReceiptValidation:
        return self.ingested.validation

    @property
    def evidence_rejected(self) -> bool:
        """True when this receipt was refused for its evidence shape alone.

        A corrected receipt for the same implementation commit may be
        resubmitted through `ingest_developer_result` while this is true; the
        job is still `developing`.
        """
        return self.ingested.validation.evidence_format_only


@dataclass(frozen=True)
class ReviewResult:
    """One adjudicated review and the job state it produced."""

    review: EngineeringReview
    review_pointer: EngineeringRecordPointer
    attestation_pointer: EngineeringRecordPointer
    job: EngineeringJob
    job_pointer: EngineeringRecordPointer


# --- stage 1: intake ------------------------------------------------------


def open_job(
    store: EngineeringStore,
    assessment: IntakeAssessment,
    *,
    on: dt.date | None = None,
) -> OpenedJob:
    """Persist an authorized intake and open its job at `planning`.

    A decision-required assessment has no work order and therefore no job; the
    caller records the request and reports the decisions instead.
    """
    if assessment.outcome is not IntakeOutcome.AUTHORIZED or assessment.work_order is None:
        raise EngineeringError(
            "only an authorized intake opens a job; a decision-required assessment "
            "carries decisions for the CEO and no work order"
        )
    order = assessment.work_order
    day = assert_day(on or order.authorized_on, "on")
    request_pointer = store.append_request(assessment.request)
    order_pointer = store.put_work_order(order)
    plan = derive_plan(order, proposed_on=day)
    plan_pointer = store.append_plan(plan)
    job = EngineeringJob.open(order, on=day).advance(
        JobState.PLANNING,
        on=day,
        reason=f"implementation plan {plan.fingerprint()} derived from the work order",
        evidence_refs=(plan_pointer.record_ref, order_pointer.record_ref),
    )
    job_pointer = store.append_job(job)
    return OpenedJob(
        work_order=order,
        plan=plan,
        job=job,
        request_pointer=request_pointer,
        work_order_pointer=order_pointer,
        plan_pointer=plan_pointer,
        job_pointer=job_pointer,
    )


# --- stage 2: the developer session --------------------------------------


def _context_policy(order: EngineeringWorkOrder) -> ContextAssemblyPolicy:
    """The context policy this work order's resource profile asks for.

    The reasoning class already caps how many references a task may carry -
    twelve for a bounded change, twenty for specialist work. The profile caps
    it again, lower, and the smaller number wins. Without this the packet
    filled itself to the class ceiling with automatically selected capsules
    whatever the profile said, which is where most of the context in a routine
    job was actually coming from: not from what the work order asked for, but
    from the capsule graph's transitive dependencies filling the space left.
    """
    profile = resource_profile(order.resource_profile)
    # Specialist work gets the capsule graph even under a profile that would
    # otherwise withhold it. The graph is the point of specialist work, and a
    # job routed to the strongest model because it needs domain judgment is not
    # the job to economise on background.
    specialist = bool(order.specialist_domain) or order.escalation != "none"
    return ContextAssemblyPolicy(
        automatic_ref_ceiling=profile.context_ref_ceiling,
        include_dependencies=profile.include_capsule_dependencies or specialist,
    )


def prepare_developer_session(
    store: EngineeringStore,
    execution_store: ExecutionStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    config: CompanyConfig,
    *,
    on: dt.date,
    executor: ExecutorHint = ExecutorHint.UNSPECIFIED,
) -> DeveloperBriefing:
    """Route the work order, narrow the contract to it, and emit one packet."""
    order.assert_unchanged(job.work_order_fingerprint, "developer preparation")
    # Checked before anything is persisted. This function writes a packet and
    # an immutable authority snapshot, and a stage that is going to be refused
    # must leave neither behind.
    refusal = job.refusal(JobState.DEVELOPING)
    if refusal:
        raise EngineeringError(refusal)
    policy = _context_policy(order)
    routed = plan_task(order.task_specification(), config, context_policy=policy)
    if not routed.ready or routed.selected_employee is None:
        reason = routed.escalation.reason or "the work order could not be prepared"
        raise EngineeringError(
            f"work order {order.work_order_id} did not reach execution_prepared: {reason}"
        )
    employee = routed.selected_employee
    contract = order.employee_contract(config, employee)
    scoped = plan_task(
        order.task_specification(),
        config,
        employee_contract=contract,
        context_policy=policy,
    )
    prepared = ManualExternalSessionAdapter(execution_store).prepare(
        scoped,
        expected_branch=order.authorized_branch,
        path_scope=order.path_scope(),
        required_tests=order.required_tests,
        expected_base_commit=order.base_commit,
        executor=executor,
        employee_contract=contract,
    )
    moved = job.advance(
        JobState.DEVELOPING,
        on=on,
        reason=(
            f"packet {prepared.packet.fingerprint()} attempt {prepared.pointer.attempt} "
            f"issued to {employee}"
        ),
        evidence_refs=(prepared.pointer.record_ref, prepared.authority_pointer.record_ref),
    )
    pointer = store.append_job(moved)
    return DeveloperBriefing(
        work_order=order,
        plan=scoped,
        prepared=prepared,
        employee=employee,
        job=moved,
        job_pointer=pointer,
        ledger=execution_store.context_expansion_ledger(
            prepared.packet, packet_attempt=prepared.pointer.attempt
        ),
    )


def ingest_developer_result(
    store: EngineeringStore,
    execution_store: ExecutionStore,
    usage_store: ResourceUsageStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    config: CompanyConfig,
    receipt: SessionReceipt,
    *,
    on: dt.date,
    packet: SessionPacket | None = None,
    repo_dir: str | Path | None = None,
) -> DeveloperResult:
    """Validate and record one developer attempt through the existing runtime.

    The attempt is recorded whether or not it passes. A failed attempt moves
    the job to `testing` as well: the review stage is where a failure is
    adjudicated, because a receipt that fails validation still needs an
    independent reader to decide whether a correction is possible inside the
    same authorization.

    One case is deliberately not a failed attempt: a receipt whose only
    problem is the shape of its required-test evidence (a required suite
    folded into a combined command, or missing from the report entirely) is
    testimony about the *report*, not the work. Rejecting it must not spend
    the job's one shot at `developing` - that conflation is exactly the
    defect the first real dogfood found: an evidence-format refusal moved the
    job to `testing`, `developing` could not be re-entered because the
    attempt ceiling was already spent at packet issuance, and a corrected
    receipt for the same passing commit could never be ingested. So this
    function checks the ingested validation before touching the job's state:
    an evidence-format-only failure leaves the job in `developing`, recorded
    but unmoved, so a corrected receipt for the *same* implementation commit
    can be ingested again. A receipt claiming a different commit is refused
    outright rather than accepted as a "correction" - that would let a second
    implementation attempt through a channel meant only to fix a report.
    """
    order.assert_unchanged(job.work_order_fingerprint, "developer ingestion")
    if job.state is not JobState.DEVELOPING:
        raise EngineeringError(
            f"a developer receipt is ingested from developing, not from {job.state.value}"
        )
    contract = order.employee_contract(config, _implementer_of(order, config))
    # The same context policy the packet was built under. `ingest` re-plans and
    # compares the resulting context fingerprint against the packet's, so a
    # second plan assembled under different rules is a fingerprint mismatch and
    # a refused receipt - which is what the dogfood run found: the brief stage
    # narrowed context by the resource profile and this one did not.
    scoped = plan_task(
        order.task_specification(),
        config,
        employee_contract=contract,
        context_policy=_context_policy(order),
    )
    resolved = packet or _latest_packet(execution_store, order)
    prior_receipts = tuple(
        record
        for record in execution_store.receipts(order.work_order_id)
        if record.packet_fingerprint == resolved.fingerprint()
    )
    # Every prior receipt found here was, by construction, an
    # evidence-format-only rejection: the job is still `developing` (asserted
    # above), and that is the one outcome this function leaves it in.
    # Anything else - accepted or a genuine failure - would already have
    # advanced the job to `testing`, and this call would have raised above.
    if prior_receipts:
        expected_commit = prior_receipts[-1].commit_sha
        if expected_commit and receipt.commit_sha and receipt.commit_sha != expected_commit:
            raise EngineeringError(
                f"work order {order.work_order_id}: this packet already has a "
                f"rejected receipt for commit {expected_commit}; a corrected receipt "
                "must report that same commit. Reporting commit "
                f"{receipt.commit_sha} is a different implementation, which needs a "
                "new work order, not an evidence correction"
            )
    ingested = ManualExternalSessionAdapter(execution_store).ingest(
        scoped, resolved, receipt, usage_store, repo_dir=repo_dir
    )
    if ingested.validation.evidence_format_only:
        return DeveloperResult(ingested=ingested, job=job, job_pointer=None)
    moved = job.advance(
        JobState.TESTING,
        on=on,
        reason=(
            f"attempt {ingested.receipt.packet_attempt} recorded "
            f"{ingested.attempt.usage_record.outcome.value}"
            + ("" if ingested.accepted else f": {ingested.validation.reason()}")
        ),
        evidence_refs=(
            ingested.receipt_pointer.record_ref,
            ingested.attempt.usage_pointer.record_ref,
        ),
    )
    pointer = store.append_job(moved)
    return DeveloperResult(ingested=ingested, job=moved, job_pointer=pointer)


# --- stage 3: the review session -----------------------------------------


def prepare_review_session(
    store: EngineeringStore,
    execution_store: ExecutionStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    config: CompanyConfig,
    *,
    implementer: str,
    on: dt.date,
    executor: ExecutorHint = ExecutorHint.UNSPECIFIED,
) -> ReviewBriefing:
    """Route the review capability to a different employee and emit a read-only packet."""
    order.assert_unchanged(job.work_order_fingerprint, "review preparation")
    refusal = job.refusal(JobState.REVIEWING)
    if refusal:
        raise EngineeringError(refusal)
    policy = _context_policy(order)
    routed = plan_task(order.review_specification(), config, context_policy=policy)
    if not routed.ready or routed.selected_employee is None:
        reason = routed.escalation.reason or "no reviewer could be routed"
        raise EngineeringError(
            f"work order {order.work_order_id}: review routing failed: {reason}"
        )
    reviewer = routed.selected_employee
    if reviewer == implementer:
        raise AuthorityEscalation(
            f"the review capability {order.review_capability!r} routed to "
            f"{reviewer!r}, who implemented the work. Review must be an independent "
            "employee; staff the review capability separately."
        )
    contract = order.reviewer_contract(config, reviewer)
    scoped = plan_task(
        order.review_specification(),
        config,
        employee_contract=contract,
        context_policy=policy,
    )
    prepared = ManualExternalSessionAdapter(execution_store).prepare(
        scoped,
        expected_branch=order.authorized_branch,
        path_scope=None,  # read-only: an empty allow-list allows nothing
        required_tests=order.required_tests,
        expected_base_commit=order.base_commit,
        executor=executor,
        employee_contract=contract,
    )
    moved = job.advance(
        JobState.REVIEWING,
        on=on,
        reason=f"review packet issued to {reviewer} (implementer {implementer})",
        evidence_refs=(prepared.pointer.record_ref,),
    )
    pointer = store.append_job(moved)
    return ReviewBriefing(
        work_order=order,
        plan=scoped,
        prepared=prepared,
        reviewer=reviewer,
        implementer=implementer,
        job=moved,
        job_pointer=pointer,
        ledger=execution_store.context_expansion_ledger(
            prepared.packet, packet_attempt=prepared.pointer.attempt
        ),
    )


def record_review(
    store: EngineeringStore,
    execution_store: ExecutionStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    config: CompanyConfig,
    attestation: ReviewerAttestation,
    packet: SessionPacket,
    receipt: SessionReceipt,
    *,
    implementer: str,
    repo_root: str | Path,
    on: dt.date | None = None,
) -> ReviewResult:
    """Adjudicate one review and move the job by its verdict.

    `execution_store` is required rather than optional because the receipt is
    re-validated here, and a re-validation that sees less evidence than the
    original is not a check, it is a second, weaker opinion.

    PASS goes to the gate. CHANGES_REQUIRED goes back to `planning` while the
    work order's attempt ceiling allows it and no escalation is outstanding, and
    to `decision_required` otherwise. BLOCKED goes to `decision_required` when
    the reason is an authority matter and to `blocked` when it is not.

    Back to `planning` rather than `developing` because the correction has not
    been issued yet; `prepare_developer_session` issues it, and that is what
    spends an attempt.
    """
    order.assert_unchanged(job.work_order_fingerprint, "review")
    if job.state is not JobState.REVIEWING:
        raise EngineeringError(
            f"a review is recorded from reviewing, not from {job.state.value}"
        )
    day = assert_day(on or attestation.reviewed_on, "on")
    attestation_pointer = store.append_attestation(attestation)
    # Re-validated against the *same* evidence the adapter used at ingestion:
    # the authority snapshot for this packet attempt and the attempt's context
    # expansion ledger. Without them a receipt that legitimately references its
    # authority reads as referencing evidence nobody supplied, and every clean
    # attempt fails review for a reason that is about this function rather than
    # about the work.
    authority = execution_store.authority(
        packet.task_id, packet.fingerprint(), receipt.packet_attempt
    )
    ledger = execution_store.context_expansion_ledger(
        packet, packet_attempt=receipt.packet_attempt
    )
    validation = validate_receipt(
        packet,
        receipt,
        expansion_ledger=ledger,
        packet_attempt=receipt.packet_attempt or None,
        authority_fingerprint=authority.fingerprint() if authority is not None else "",
    )
    review = adjudicate(
        order,
        packet,
        receipt,
        validation,
        attestation,
        repo_root=repo_root,
        implementer=implementer,
        packet_attempt=receipt.packet_attempt,
        reviewer_capabilities=_capabilities_of(attestation.reviewer, config),
    )
    review_pointer = store.append_review(review)
    evidence = (attestation_pointer.record_ref, review_pointer.record_ref)

    if review.outcome is ReviewOutcome.PASS:
        moved = job.advance(
            JobState.GATE,
            on=day,
            reason=f"review {review.review_id} passed ({review.reviewer})",
            actor=review.reviewer,
            evidence_refs=evidence,
        )
    elif review.escalations:
        moved = job.requiring_decision(
            review.escalations,
            on=day,
            actor=review.reviewer,
            evidence_refs=evidence,
        )
    elif review.outcome is ReviewOutcome.CHANGES_REQUIRED and not job.exhausted:
        moved = job.advance(
            JobState.PLANNING,
            on=day,
            reason=(
                f"review {review.review_id} requires changes; "
                f"{job.corrections_remaining} authorized attempt(s) remain"
            ),
            actor=review.reviewer,
            evidence_refs=evidence,
        )
    elif review.outcome is ReviewOutcome.CHANGES_REQUIRED:
        # The explicit continuation state. Under a resource profile that
        # authorizes one developer attempt - which is what consumer mode is -
        # this is the ordinary end of a job whose review found something, and
        # it is reached *instead of* automatically spending another session.
        # Nothing here decides whether the work should continue; it records
        # that continuing needs an authorization the company does not hold.
        moved = job.requiring_decision(
            (
                f"the work order's {job.max_developer_attempts} authorized developer "
                "attempt(s) are spent and the review still requires changes; "
                "continuing needs either additional-attempt authorization on this "
                "work order or a new one",
            ),
            on=day,
            actor=review.reviewer,
            evidence_refs=evidence,
        )
    else:
        moved = job.advance(
            JobState.BLOCKED,
            on=day,
            reason=f"review {review.review_id} is blocked: "
            + "; ".join(item.summary for item in review.blocking_findings[:3]),
            actor=review.reviewer,
            evidence_refs=evidence,
        )
    job_pointer = store.append_job(moved)
    return ReviewResult(
        review=review,
        review_pointer=review_pointer,
        attestation_pointer=attestation_pointer,
        job=moved,
        job_pointer=job_pointer,
    )


# --- stage 4: the gate ----------------------------------------------------


def record_gate(
    store: EngineeringStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    verdict: GateVerdict,
    *,
    on: dt.date | None = None,
    implementation_commit: str = "",
) -> tuple[EngineeringJob, EngineeringRecordPointer, EngineeringRecordPointer]:
    """Record one gate verdict and move the job by it. READY is the only pass.

    `implementation_commit` is the commit the developer reported. A gate report
    computed at a different commit describes a different tree, so a READY
    verdict that is stale against the work under review does **not** advance
    the job: it blocks it and names the two commits. Without that check a
    verdict produced before the implementation landed would read as evidence
    for it, which is the most plausible way a gate gets silently satisfied.
    """
    order.assert_unchanged(job.work_order_fingerprint, "gate")
    if job.state is not JobState.GATE:
        raise EngineeringError(
            f"a gate verdict is recorded from gate, not from {job.state.value}. The "
            "gate runs after review passes."
        )
    if verdict.work_order_id != order.work_order_id:
        raise EngineeringError(
            f"the gate verdict names work order {verdict.work_order_id!r}, not "
            f"{order.work_order_id!r}"
        )
    day = assert_day(on or verdict.as_of, "on")
    gate_pointer = store.append_gate_verdict(verdict)
    stale = verdict.stale_against(implementation_commit)
    if stale:
        moved = job.advance(
            JobState.BLOCKED,
            on=day,
            reason=f"integration gate {verdict.report_id} does not describe this work: {stale}",
            evidence_refs=(gate_pointer.record_ref,),
        )
        job_pointer = store.append_job(moved)
        return moved, gate_pointer, job_pointer
    if verdict.readiness.permits_readiness:
        moved = job.advance(
            JobState.READY_FOR_APPROVAL,
            on=day,
            reason=(
                f"integration gate {verdict.report_id} is READY; the work is ready to "
                "be read, and is not approved"
            ),
            evidence_refs=(gate_pointer.record_ref,),
        )
    elif any(item.ceo_decision_required for item in verdict.blockers):
        moved = job.requiring_decision(
            tuple(
                item.reason for item in verdict.blockers if item.ceo_decision_required
            ),
            on=day,
            evidence_refs=(gate_pointer.record_ref,),
        )
    else:
        moved = job.advance(
            JobState.BLOCKED,
            on=day,
            reason=(
                f"integration gate {verdict.report_id} is {verdict.readiness.value}: "
                + "; ".join(verdict.blocker_summaries[:3] or ("required evidence is missing",))
            ),
            evidence_refs=(gate_pointer.record_ref,),
        )
    job_pointer = store.append_job(moved)
    return moved, gate_pointer, job_pointer


# --- stage 5: the CEO -----------------------------------------------------


def publish_result(
    store: EngineeringStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    *,
    receipt: SessionReceipt | None = None,
    review: EngineeringReview | None = None,
    gate: GateVerdict | None = None,
    suite_results: Sequence[ResultTest] = (),
    risks: Sequence[str] = (),
    decisions_required: Sequence[str] = (),
    evidence_refs: Sequence[str] = (),
) -> tuple[EngineeringResult, EngineeringRecordPointer]:
    """Assemble and persist the CEO page for the job's current state."""
    result = EngineeringResult.build(
        order,
        job,
        receipt=receipt,
        review=review,
        gate=gate,
        suite_results=suite_results,
        risks=risks,
        decisions_required=decisions_required,
        evidence_refs=evidence_refs,
    )
    return result, store.append_result(result)


def record_decision(
    store: EngineeringStore,
    order: EngineeringWorkOrder,
    job: EngineeringJob,
    decision: CEODecision,
) -> tuple[EngineeringJob, EngineeringRecordPointer, EngineeringRecordPointer]:
    """Record the CEO's answer and move the job. Nothing is integrated."""
    order.assert_unchanged(job.work_order_fingerprint, "CEO decision")
    decision_pointer = store.append_decision(decision)
    moved = decision.apply_to(job)
    job_pointer = store.append_job(moved)
    return moved, decision_pointer, job_pointer


# --- internals ------------------------------------------------------------


def _capabilities_of(employee: str, config: CompanyConfig) -> tuple[str, ...]:
    """What the registry says this employee can do; empty for a name it never heard of.

    Empty is the honest answer for an unknown employee, and `adjudicate` reads
    it as blocking rather than as "not checked" - the two used to be the same
    value, which let an attestation name anybody.
    """
    employees = config.org_registry.get("employees", {})
    record = employees.get(employee, {}) if isinstance(employees, Mapping) else {}
    values = record.get("capabilities", ()) if isinstance(record, Mapping) else ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        return ()
    return tuple(str(item).casefold() for item in values)


def _implementer_of(order: EngineeringWorkOrder, config: CompanyConfig) -> str:
    """Re-route the work order to learn which employee its packet was issued to.

    Routing does not depend on the context policy, but planning under a
    different one assembles a different manifest, and an assembly that can fail
    here for a reason routing does not care about is a needless second way for
    this to break. It is given the same policy as every other call.
    """
    routed = plan_task(
        order.task_specification(), config, context_policy=_context_policy(order)
    )
    if routed.selected_employee is None:
        raise EngineeringError(
            f"work order {order.work_order_id}: no employee holds "
            + ", ".join(order.implementation_capabilities)
        )
    return routed.selected_employee


def _latest_packet(
    execution_store: ExecutionStore, order: EngineeringWorkOrder
) -> SessionPacket:
    """The most recent packet issued for this work order, by its own history."""
    records = execution_store.packet_records(order.work_order_id)
    if not records:
        raise EngineeringError(
            f"work order {order.work_order_id} has no issued packet; prepare a "
            "developer session before ingesting a receipt"
        )
    completed = {
        item.receipt.packet_attempt
        for item in execution_store.attempts(order.work_order_id)
        if item.receipt.packet_attempt
    }
    incomplete = tuple(item for item in records if item.attempt not in completed)
    return (incomplete or records)[-1].packet


def accepted(result: DeveloperResult) -> bool:
    """Whether the recorded attempt was accepted by the runtime's own validation."""
    return result.ingested.attempt.usage_record.outcome is Outcome.ACCEPTED


__all__ = [
    "DeveloperBriefing",
    "DeveloperResult",
    "OpenedJob",
    "ReviewBriefing",
    "ReviewResult",
    "accepted",
    "ingest_developer_result",
    "open_job",
    "prepare_developer_session",
    "prepare_review_session",
    "publish_result",
    "record_decision",
    "record_gate",
    "record_review",
]
