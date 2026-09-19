"""Focused proofs for the company engineering execution loop.

The suite is organised by the property it protects, not by module:

- intake bounds a CEO objective, or stops with DECISION REQUIRED;
- routing is deterministic and the two engineering roles are disjoint;
- a developer cannot widen its own authority, in five different directions;
- review is distinct, and its PASS cannot rescue a failed deterministic check;
- the gate is distinct, is read rather than computed, and cannot be forged;
- a correction loop is bounded;
- the loop reaches `ready_for_approval` and integrates nothing;
- and the whole package still holds none of the capabilities the integration
  gate forbids.

The last group is why this file imports `company.integration`. The gate package
may not be imported by `company.engineering` — that would close a subsystem
cycle — so the equality between the engineering readiness mirror and the gate's
own `readiness_of` is pinned here, where importing both is allowed.
"""

from __future__ import annotations

import ast
import datetime as dt
from dataclasses import replace
import json
from pathlib import Path

import pytest

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.policy import SubagentPolicyViolation
from ai_platform.resource_classes import ReasoningClass, resource_class
from ai_platform.serde import dumps
from ai_platform.usage import Outcome
from company.engineering import (
    DEFAULT_PROTECTED_PATHS,
    NOT_AN_APPROVAL,
    AuthorityEscalation,
    CEODecision,
    CEORequest,
    CEOVerdict,
    CriterionFinding,
    EngineeringError,
    EngineeringJob,
    EngineeringResult,
    EngineeringReview,
    EngineeringStore,
    EngineeringWorkOrder,
    FindingSeverity,
    GateReadiness,
    GateVerdict,
    ImplementationPlan,
    IntakeOutcome,
    JobState,
    PlanStep,
    ProtectedSurface,
    ResultTest,
    ReviewFinding,
    ReviewOutcome,
    ReviewerAttestation,
    SelfApproval,
    SuiteScope,
    adjudicate,
    assess_request,
    derive_plan,
    ingest_developer_result,
    open_job,
    prepare_developer_session,
    prepare_review_session,
    publish_result,
    readiness_from,
    record_decision,
    record_gate,
    record_review,
)
from ai_platform.resource_classes import Risk
from company.efficiency.profile import CONSUMER, EXPANDED, resource_profile
from company.efficiency.strategy import EscalationReason, ModelTier, narrow_context_refs
from company.engineering.intake import (
    SPECIALIST_TRIGGERS,
    RoutingDerivation,
    derive_routing,
)
from company.engineering.lifecycle import ALLOWED_TRANSITIONS, MAIN_SEQUENCE
from company.engineering.transport import (
    ESCALATE_INSTEAD_OF,
    RESOURCE_STRATEGY_VERSION,
)
from company.integration.model import (
    EvidenceKind,
    GateCategory,
    GateCheck,
    GateStatus,
    readiness_of,
)
from company.integration.policy import DEFAULT_POLICY
from company.integration.sources import (
    module_imports,
    module_subsystem,
    parse_tree,
    subsystem_of,
)
from company.runtime import (
    ExecutionStore,
    ExecutorHint,
    ReceiptUsage,
    ReportedTest,
    ResourceUsageStore,
    SessionReceipt,
    load_company_config,
    match_capabilities,
)
from company.runtime.lifecycle import plan_task
from company.runtime.receipts import validate_receipt
from company.validation.errors import ValidationError
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.capsules.index import path_related


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "company" / "engineering"
DAY = dt.date(2026, 9, 18)
SHA = "a" * 40
OTHER_SHA = "b" * 40


def _config():
    return load_company_config(ROOT / "company")


def _index() -> CapsuleIndex:
    return CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")


def _fake_repo(tmp_path: Path) -> Path:
    """A checkout containing every protected path, so tampering is detectable.

    The real repository is never written to by these tests. The protected
    surface is about *bytes on disk*, so proving it catches a change needs a
    tree the test owns.
    """
    root = tmp_path / "repo"
    for relative in DEFAULT_PROTECTED_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# original {relative}\n", encoding="utf-8")
    (root / "company" / "engineering").mkdir(parents=True, exist_ok=True)
    (root / "company" / "engineering" / "seed.py").write_text("x = 1\n", encoding="utf-8")
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_company_engineering_execution.py").write_text(
        "def test_seed():\n    assert True\n", encoding="utf-8"
    )
    return root


# An objective that is plainly routine: it names no security, governance,
# architecture or concurrency work, so intake derives no specialist domain and
# the classifier floors it at C. Deliberately modelled on the real
# `attempts-remaining` dogfood job, which is the historical BEFORE case.
ROUTINE_OBJECTIVE = (
    "Add a field to the engineering result record reporting how many developer "
    "attempts remain, and show it on the page the CEO reads."
)


def _routine_request(**changes) -> CEORequest:
    values = {"objective": ROUTINE_OBJECTIVE}
    values.update(changes)
    return _request(**values)


def _request(**changes) -> CEORequest:
    values = {
        "request_id": "req-001",
        "objective": (
            "Give me a way to check whether the protected governance files have "
            "changed since an engineering work order was authorized."
        ),
        "requested_by": "MGI",
        "requested_on": DAY,
        "subsystem_hint": "company/engineering",
        "authorized_branch": "eng-req-001",
    }
    values.update(changes)
    return CEORequest(**values)


def _assessment(tmp_path: Path, **changes):
    return assess_request(
        _request(**changes),
        _config().permissions,
        repo_root=_fake_repo(tmp_path),
        capsule_index=_index(),
        work_order_id="wo-req-001",
    )


def _order(tmp_path: Path, **changes) -> EngineeringWorkOrder:
    assessment = _assessment(tmp_path)
    assert assessment.work_order is not None
    return replace(assessment.work_order, **changes) if changes else assessment.work_order


def _receipt(packet, **changes) -> SessionReceipt:
    values = {
        "task_id": packet.task_id,
        "packet_fingerprint": packet.fingerprint(),
        "outcome": Outcome.ACCEPTED,
        "summary": "Added the requested check and its tests.",
        "branch": packet.expected_branch,
        "commit_sha": SHA,
        "remote_branch_sha": SHA,
        "remote_verified": True,
        "working_tree_clean": True,
        "files_changed": ("company/engineering/verify.py",),
        "tests": tuple(
            ReportedTest(command=command, passed=True, summary="ok")
            for command in packet.required_tests
        ),
        "evidence": ("company/engineering/verify.py",),
        "usage": ReceiptUsage(passes=1),
        "executor": ExecutorHint.CLAUDE_CODE,
    }
    values.update(changes)
    return SessionReceipt(**values)


def _attestation(order, packet, receipt, **changes) -> ReviewerAttestation:
    values = {
        "review_id": "rev-001",
        "work_order_id": order.work_order_id,
        "work_order_fingerprint": order.fingerprint(),
        "reviewer": "chief_architect",
        "packet_fingerprint": packet.fingerprint(),
        "receipt_fingerprint": receipt.fingerprint(),
        "verdict": ReviewOutcome.PASS,
        "reviewed_on": DAY,
        "criteria": tuple(
            CriterionFinding(
                criterion=item,
                satisfied=True,
                evidence_ref="tests/test_company_engineering_execution.py",
            )
            for item in order.acceptance_criteria
        ),
        "evidence": ("company/engineering/verify.py",),
        "changed_paths_reviewed": receipt.files_changed,
    }
    values.update(changes)
    return ReviewerAttestation(**values)


def _gate_report(readiness: GateReadiness, *, commit: str = SHA) -> dict:
    """A minimal report shaped exactly like the gate's canonical JSON."""
    required = sorted(DEFAULT_POLICY.required)
    status = {
        GateReadiness.READY: "pass",
        GateReadiness.BLOCKED: "fail",
        GateReadiness.INSUFFICIENT_EVIDENCE: "unknown",
    }[readiness]
    checks = [
        {
            "check_id": check_id,
            "category": check_id.split(".", 1)[0],
            "status": "pass" if check_id != required[0] else status,
            "requirement": "r",
            "detail": "d",
            "evidence_kind": "repository",
        }
        for check_id in required
    ]
    blockers = (
        []
        if readiness is GateReadiness.READY
        else [
            {
                "blocker_id": "b1",
                "check_id": required[0],
                "category": required[0].split(".", 1)[0],
                "reason": "the first required condition did not hold",
                "remediation": "fix it",
                "resolved": False,
                "ceo_decision_required": False,
            }
        ]
    )
    return {
        "as_of": DAY.isoformat(),
        "policy_version": DEFAULT_POLICY.version,
        "report_id": f"integration-readiness-{DAY.isoformat()}-0123456789abcdef",
        "required_check_ids": required,
        "advisory_check_ids": sorted(DEFAULT_POLICY.advisory),
        "authorizes_production_integration": False,
        "schema_version": 1,
        "notes": [],
        "blockers": blockers,
        "source": {
            "repo_root": "repo",
            "source_commit": commit,
            "source_branch": "eng-req-001",
        },
        "sections": [{"category": "architecture", "checks": checks}],
    }


def _stores(state: Path):
    return EngineeringStore(state), ExecutionStore(state), ResourceUsageStore(state)


def _validation(run):
    """The receipt validation `record_review` performs, with the same evidence.

    A bare `validate_receipt(packet, receipt)` fails an honest receipt, because
    the receipt references the authority snapshot the adapter attached and a
    validation that was not given it reports the reference as unsupplied. That
    was a real defect in `record_review` before it was fixed; a test that
    re-validates has to supply the same evidence or it re-creates it.
    """
    packet, receipt = run["packet"], run["receipt"]
    authority = run["execution"].authority(
        packet.task_id, packet.fingerprint(), receipt.packet_attempt
    )
    return validate_receipt(
        packet,
        receipt,
        expansion_ledger=run["execution"].context_expansion_ledger(
            packet, packet_attempt=receipt.packet_attempt
        ),
        packet_attempt=receipt.packet_attempt or None,
        authority_fingerprint=authority.fingerprint() if authority else "",
    )


def _through_review(tmp_path: Path, *, request_changes=None, receipt_changes=None,
                    attestation_changes=None, review_verdict=ReviewOutcome.PASS,
                    tamper=None):
    """Intake through review, returning every record produced on the way."""
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    assessment = assess_request(
        _request(**(request_changes or {})),
        config.permissions,
        repo_root=repo,
        capsule_index=_index(),
        work_order_id="wo-req-001",
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    order = opened.work_order
    briefing = prepare_developer_session(
        store, execution, order, opened.job, config, on=DAY
    )
    receipt = _receipt(briefing.packet, **(receipt_changes or {}))
    developed = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, receipt, on=DAY
    )
    review_briefing = prepare_review_session(
        store, execution, order, developed.job, config,
        implementer=briefing.employee, on=DAY,
    )
    if tamper is not None:
        tamper(repo)
    attestation = _attestation(
        order, briefing.packet, developed.receipt,
        verdict=review_verdict, **(attestation_changes or {}),
    )
    reviewed = record_review(
        store, execution, order, review_briefing.job, config, attestation,
        briefing.packet, developed.receipt,
        implementer=briefing.employee, repo_root=repo, on=DAY,
    )
    return {
        "store": store, "execution": execution, "usage": usage, "config": config,
        "repo": repo, "state": state, "order": order,
        "employee": briefing.employee, "reviewer": review_briefing.reviewer,
        "packet": briefing.packet, "receipt": developed.receipt,
        "review": reviewed.review, "job": reviewed.job,
    }


def _drive(tmp_path: Path, *, readiness=GateReadiness.READY, **kwargs):
    """One whole loop: intake, develop, review, gate, CEO result."""
    run = _through_review(tmp_path, **kwargs)
    gate = None
    job = run["job"]
    if job.state is JobState.GATE:
        gate = GateVerdict.from_report_mapping(
            _gate_report(readiness),
            work_order_id=run["order"].work_order_id,
            report_digest="0" * 16,
        )
        job, _gate_pointer, _job_pointer = record_gate(
            run["store"], run["order"], job, gate, on=DAY,
            implementation_commit=run["receipt"].commit_sha,
        )
    result, _pointer = publish_result(
        run["store"], run["order"], job,
        receipt=run["receipt"], review=run["review"], gate=gate,
    )
    run.update(gate=gate, job=job, result=result)
    return run


# --- 1. intake produces a bounded work order, or stops --------------------


def test_a_ceo_objective_produces_a_bounded_work_order(tmp_path):
    assessment = _assessment(tmp_path)
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    order = assessment.work_order
    assert order is not None
    # The CEO named no file. The scope came from the capsule that owns the
    # subject, plus the one test file that capsule declares - a work order that
    # requires a test to pass has to allow writing it.
    assert order.authorized_paths == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
    )
    assert assessment.derivation.selected_capsule_ids == ("company-engineering-execution",)
    assert order.required_tests == ("tests/test_company_engineering_execution.py",)
    assert order.acceptance_criteria
    assert assessment.derivation.criteria_derived is True


def test_a_required_test_is_always_inside_the_authorized_scope(tmp_path):
    """A criterion that cannot be satisfied inside the scope is not a criterion."""
    order = _order(tmp_path)
    scope = order.path_scope()
    for command in order.required_tests:
        assert scope.permits(command), command
        assert not scope.forbids(command), command


def test_intake_screens_every_ceo_reserved_action(tmp_path):
    assessment = _assessment(tmp_path)
    assert assessment.derivation.unscreened_reserved_actions == ()
    blocked = _assessment(
        tmp_path,
        objective="Publish the engineering result to the channel once it is done.",
    )
    assert blocked.outcome is IntakeOutcome.DECISION_REQUIRED
    assert blocked.work_order is None
    assert any(item.reserved_action == "publish_public_video" for item in blocked.decisions)


def test_intake_refuses_an_objective_that_names_credentials(tmp_path):
    blocked = _assessment(
        tmp_path,
        objective="Rotate the engineering oauth client secret and store the refresh token.",
    )
    assert blocked.outcome is IntakeOutcome.DECISION_REQUIRED
    assert any("credential material" in item.reason for item in blocked.decisions)


def test_an_unowned_subject_stops_rather_than_guessing_a_scope(tmp_path):
    blocked = _assessment(
        tmp_path,
        objective="Improve the flavour text of the trophy presentation.",
        subsystem_hint="",
    )
    assert blocked.outcome is IntakeOutcome.DECISION_REQUIRED
    assert any("no capsule owns the subject" in item.reason for item in blocked.decisions)
    assert all(item.options for item in blocked.decisions)


def test_a_ceo_scope_ceiling_narrows_and_never_widens(tmp_path):
    inside = _assessment(tmp_path, scope_ceiling=("company/engineering",))
    assert inside.work_order is not None
    assert inside.work_order.authorized_paths == ("company/engineering",)
    assert "tests/test_company_engineering_execution.py" not in (
        inside.work_order.authorized_paths
    )
    # A ceiling outside the owning capsule leaves nothing writable, and a
    # ceiling is never a selection signal, so it cannot reach another subsystem.
    outside = _assessment(tmp_path, scope_ceiling=("company/runtime",))
    assert outside.outcome is IntakeOutcome.DECISION_REQUIRED
    assert outside.derivation.selected_capsule_ids == (
        "company-engineering-execution",
    )
    assert any(
        "no writable path inside the requested ceiling" in item.reason
        for item in outside.decisions
    )


def test_a_ceiling_inside_the_owned_tree_keeps_the_smaller_of_the_two(tmp_path):
    narrowed = _assessment(tmp_path, scope_ceiling=("company/engineering/intake.py",))
    assert narrowed.work_order is not None
    assert narrowed.work_order.authorized_paths == ("company/engineering/intake.py",)


def test_intake_is_deterministic(tmp_path):
    first = _assessment(tmp_path)
    second = _assessment(tmp_path)
    assert first.work_order is not None and second.work_order is not None
    assert first.work_order.fingerprint() == second.work_order.fingerprint()


def test_the_derived_plan_names_the_stages_the_brief_asks_for(tmp_path):
    plan = derive_plan(_order(tmp_path), proposed_on=DAY)
    assert [step.step_id for step in plan.steps] == [
        "inspect", "locate-contract", "implement", "test", "run-suites",
        "gate-evidence", "review-evidence",
    ]
    assert plan.writing_paths == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
    )


# --- 2. routing is deterministic, and the two roles are disjoint ----------


def test_capability_routing_is_deterministic_and_separates_the_two_roles(tmp_path):
    config = _config()
    order = _order(tmp_path)
    implement = match_capabilities(list(order.implementation_capabilities), config)
    review = match_capabilities([order.review_capability], config)
    assert implement.eligible_employee_ids == ("software_implementation_engineer",)
    assert review.eligible_employee_ids == ("chief_architect",)
    assert set(implement.eligible_employee_ids).isdisjoint(review.eligible_employee_ids)
    again = match_capabilities(list(order.implementation_capabilities), config)
    assert again.eligible_employee_ids == implement.eligible_employee_ids


def test_a_work_order_cannot_name_one_capability_for_both_roles():
    with pytest.raises(EngineeringError, match="also an implementation capability"):
        EngineeringWorkOrder(
            work_order_id="wo-x",
            objective="o",
            requested_by="MGI",
            request_id="req-x",
            authorized_branch="eng-x",
            authorized_paths=("company/engineering",),
            acceptance_criteria=("c",),
            authorized_on=DAY,
            implementation_capabilities=("software_architecture",),
            review_capability="software_architecture",
        )


# --- 3. the authority ceiling --------------------------------------------


def test_authorized_paths_are_enforced_on_the_packet_scope(tmp_path):
    run = _through_review(tmp_path)
    scope = run["packet"].path_scope
    assert scope.allowed == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
    )
    assert scope.permits("company/engineering/verify.py")
    assert not scope.permits("company/runtime/packets.py")
    assert not scope.permits("tests/test_company_runtime.py")


def test_forbidden_and_protected_paths_are_enforced(tmp_path):
    scope = _order(tmp_path).path_scope()
    for path in (
        "company/permissions.yaml", "company/integration/policy.py",
        "company/constitution.md", "ai_platform/policy.py",
    ):
        assert scope.forbids(path), path
    verdict = scope.verdict(("company/permissions.yaml",))
    assert not verdict.ok
    assert verdict.forbidden_hits


def test_a_receipt_reporting_an_out_of_scope_change_is_rejected(tmp_path):
    run = _drive(tmp_path, receipt_changes={"files_changed": ("company/runtime/packets.py",)})
    assert run["review"].outcome is not ReviewOutcome.PASS
    assert run["job"].state is not JobState.READY_FOR_APPROVAL
    assert any("path scope" in item.summary for item in run["review"].findings)


def test_a_work_order_cannot_authorize_a_protected_path(tmp_path):
    with pytest.raises(EngineeringError, match="cannot authorize a protected path"):
        ProtectedSurface.capture(
            _fake_repo(tmp_path), authorized_paths=("company/permissions.yaml",)
        )


def test_a_work_order_with_no_writable_path_is_refused():
    with pytest.raises(EngineeringError, match="authorizes no engineering"):
        EngineeringWorkOrder(
            work_order_id="wo-x", objective="o", requested_by="MGI", request_id="req-x",
            authorized_branch="eng-x", authorized_paths=(),
            acceptance_criteria=("c",), authorized_on=DAY,
        )


def test_a_work_order_is_never_assigned_an_integration_branch():
    for branch in ("main", "master", "trunk"):
        with pytest.raises(AuthorityEscalation, match="integration branch"):
            EngineeringWorkOrder(
                work_order_id="wo-x", objective="o", requested_by="MGI",
                request_id="req-x", authorized_branch=branch,
                authorized_paths=("company/engineering",),
                acceptance_criteria=("c",), authorized_on=DAY,
            )


def test_the_context_ceiling_is_enforced(tmp_path):
    """An engineering task classifies as D, whose manifest ceiling is 20 refs."""
    order = _order(tmp_path)
    ceiling = resource_class(ReasoningClass.D).max_context_refs
    too_many = tuple(
        ContextRef(ContextKind.FILE, f"company/engineering/f{index}.py", "over budget")
        for index in range(ceiling + 1)
    )
    with pytest.raises(Exception, match="context budget"):
        plan_task(replace(order, context_refs=too_many).task_specification(), _config())


# --- 4. the developer cannot expand its own authority --------------------


def test_a_plan_cannot_propose_writing_outside_the_work_order(tmp_path):
    order = _order(tmp_path)
    plan = derive_plan(order, proposed_on=DAY)
    wider = replace(
        plan,
        steps=plan.steps
        + (
            PlanStep(
                step_id="widen",
                action="also relax the gate policy",
                touches=("company/integration/policy.py",),
                writes=True,
            ),
        ),
    )
    with pytest.raises(AuthorityEscalation, match="does not choose what"):
        wider.assert_within(order)


def test_a_read_only_plan_step_may_name_any_path(tmp_path):
    """Inspecting the repository is not an authority; writing to it is."""
    order = _order(tmp_path)
    plan = derive_plan(order, proposed_on=DAY)
    reading = replace(
        plan,
        steps=plan.steps
        + (
            PlanStep(
                step_id="read-gate",
                action="read the gate policy to learn what it requires",
                touches=("company/integration/policy.py",),
                writes=False,
            ),
        ),
    )
    assert reading.assert_within(order) is reading


def test_a_receipt_cannot_arrive_with_a_field_that_grants_anything(tmp_path):
    with pytest.raises(ValidationError, match="unknown field"):
        SessionReceipt.from_mapping(
            {
                "task_id": "wo-req-001",
                "packet_fingerprint": "0" * 16,
                "outcome": "accepted",
                "ceo_approved": True,
            }
        )


def test_an_attestation_cannot_arrive_with_a_field_that_grants_anything(tmp_path):
    order = _order(tmp_path)
    with pytest.raises(EngineeringError, match="unknown field"):
        ReviewerAttestation.from_mapping(
            {
                "review_id": "rev-x",
                "work_order_id": order.work_order_id,
                "work_order_fingerprint": order.fingerprint(),
                "reviewer": "chief_architect",
                "packet_fingerprint": "0" * 16,
                "receipt_fingerprint": "0" * 16,
                "verdict": "pass",
                "reviewed_on": DAY.isoformat(),
                "gate_passed": True,
            }
        )


def test_the_work_order_is_immutable_once_authorized(tmp_path):
    store = EngineeringStore(tmp_path / "state")
    order = _order(tmp_path)
    first = store.put_work_order(order)
    assert store.put_work_order(order).record_ref == first.record_ref
    widened = replace(order, authorized_paths=("company/engineering", "company/runtime"))
    with pytest.raises(AuthorityEscalation, match="immutable"):
        store.put_work_order(widened)


def test_every_later_stage_refuses_a_changed_work_order(tmp_path):
    order = _order(tmp_path)
    job = EngineeringJob.open(order, on=DAY)
    widened = replace(order, authorized_paths=("company/engineering", "company/runtime"))
    with pytest.raises(AuthorityEscalation, match="immutable"):
        widened.assert_unchanged(job.work_order_fingerprint, "test")


def test_a_refused_stage_persists_nothing(tmp_path):
    """A stage about to be refused must leave no packet and no authority record."""
    state = tmp_path / "state"
    config = _config()
    assessment = _assessment(tmp_path)
    store, execution, _usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(
        store, execution, opened.work_order, opened.job, config, on=DAY
    )
    before = len(execution.packet_records(opened.work_order.work_order_id))
    with pytest.raises(EngineeringError, match="not an allowed transition"):
        prepare_developer_session(
            store, execution, opened.work_order, briefing.job, config, on=DAY
        )
    after = len(execution.packet_records(opened.work_order.work_order_id))
    assert before == after == 1


# --- 5. the developer cannot approve itself ------------------------------


def test_the_implementer_cannot_review_its_own_work(tmp_path):
    run = _through_review(tmp_path)
    order, packet, receipt = run["order"], run["packet"], run["receipt"]
    self_review = _attestation(order, packet, receipt, reviewer=run["employee"])
    with pytest.raises(SelfApproval, match="cannot review it"):
        adjudicate(
            order, packet, receipt, _validation(run), self_review,
            repo_root=run["repo"], implementer=run["employee"],
            packet_attempt=receipt.packet_attempt,
        )


def test_a_review_record_naming_one_person_twice_cannot_be_constructed(tmp_path):
    run = _through_review(tmp_path)
    with pytest.raises(SelfApproval):
        replace(run["review"], reviewer=run["review"].implementer)


def test_review_routing_cannot_select_the_implementer(tmp_path):
    config = _config()
    state = tmp_path / "state"
    store, execution, usage = _stores(state)
    opened = open_job(store, _assessment(tmp_path), on=DAY)
    briefing = prepare_developer_session(
        store, execution, opened.work_order, opened.job, config, on=DAY
    )
    developed = ingest_developer_result(
        store, execution, usage, opened.work_order, briefing.job, config,
        _receipt(briefing.packet), on=DAY,
    )
    with pytest.raises(AuthorityEscalation, match="who implemented the work"):
        prepare_review_session(
            store, execution, opened.work_order, developed.job, config,
            implementer="chief_architect", on=DAY,
        )


def test_the_reviewer_packet_grants_no_writable_path(tmp_path):
    run = _through_review(tmp_path)
    reviewer_packets = [
        record.packet
        for record in run["execution"].packet_records(f"{run['order'].work_order_id}-review")
    ]
    assert reviewer_packets
    assert all(packet.path_scope.read_only for packet in reviewer_packets)
    assert run["reviewer"] != run["employee"]


def test_an_unqualified_reviewer_blocks_the_review(tmp_path):
    run = _through_review(
        tmp_path, attestation_changes={"reviewer": "production_qc_lead"}
    )
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    finding = next(
        item for item in run["review"].findings
        if item.finding_id == "reviewer-not-qualified"
    )
    assert "does not hold the work order" in finding.summary


def test_a_reviewer_who_is_not_an_employee_blocks_the_review(tmp_path):
    """Unknown and unqualified used to be the same empty tuple, so unknown passed."""
    run = _through_review(
        tmp_path, attestation_changes={"reviewer": "nobody-employs-this-name"}
    )
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    finding = next(
        item for item in run["review"].findings
        if item.finding_id == "reviewer-not-qualified"
    )
    assert "holds no capability in the org registry" in finding.summary
    assert any("staffed" in item for item in run["review"].escalations)


def test_the_qualification_check_is_skipped_only_when_nobody_looked(tmp_path):
    run = _through_review(tmp_path)
    order, packet, receipt = run["order"], run["packet"], run["receipt"]
    attestation = _attestation(
        order, packet, receipt, review_id="rev-002", reviewer="production_qc_lead"
    )
    unchecked = adjudicate(
        order, packet, receipt, _validation(run), attestation,
        repo_root=run["repo"], implementer=run["employee"],
        packet_attempt=receipt.packet_attempt, reviewer_capabilities=None,
    )
    assert unchecked.outcome is ReviewOutcome.PASS
    checked = adjudicate(
        order, packet, receipt, _validation(run), attestation,
        repo_root=run["repo"], implementer=run["employee"],
        packet_attempt=receipt.packet_attempt, reviewer_capabilities=(),
    )
    assert checked.outcome is ReviewOutcome.BLOCKED


def test_a_targeted_test_is_one_the_work_order_required(tmp_path):
    """The scope heading comes from the work order, never from a suite name."""
    run = _drive(tmp_path)
    targeted = run["result"].tests_in(SuiteScope.TARGETED)
    assert [item.command for item in targeted] == list(run["order"].required_tests)
    for item in run["result"].tests_in(SuiteScope.COMPANY_OS):
        assert item.command not in run["order"].required_tests


# --- 6. review is distinct and cannot be talked into a pass -------------


def test_a_reviewer_pass_cannot_rescue_a_failed_deterministic_check(tmp_path):
    run = _drive(
        tmp_path,
        receipt_changes={
            "tests": (
                ReportedTest(
                    command="tests/test_company_engineering_execution.py",
                    passed=False, summary="2 failed",
                ),
            ),
        },
    )
    review = run["review"]
    assert review.attested_outcome is ReviewOutcome.PASS
    assert review.deterministic_outcome is not ReviewOutcome.PASS
    assert review.outcome is review.deterministic_outcome
    assert run["job"].state is not JobState.READY_FOR_APPROVAL


def test_a_reviewer_block_is_never_overridden_by_clean_code_checks(tmp_path):
    run = _drive(
        tmp_path,
        review_verdict=ReviewOutcome.BLOCKED,
        attestation_changes={
            "findings": (
                ReviewFinding(
                    finding_id="design-01",
                    severity=FindingSeverity.BLOCKING,
                    summary="the approach will not survive the next course change",
                ),
            )
        },
    )
    assert run["review"].deterministic_outcome is ReviewOutcome.PASS
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    assert run["job"].state is not JobState.READY_FOR_APPROVAL


def test_review_failure_prevents_readiness(tmp_path):
    """Changes required stops the job, and under consumer mode it stops it dead.

    The consumer resource profile authorizes one developer attempt, so a
    review that finds something has no second attempt to fall back on. The
    job moves to `decision_required` - the explicit continuation state -
    rather than spending another expensive session on its own initiative.
    """
    run = _drive(
        tmp_path,
        review_verdict=ReviewOutcome.CHANGES_REQUIRED,
        attestation_changes={
            "findings": (
                ReviewFinding(
                    finding_id="style-01",
                    severity=FindingSeverity.CHANGES_REQUIRED,
                    summary="name the helper for what it returns",
                ),
            )
        },
    )
    assert run["job"].state is JobState.DECISION_REQUIRED
    assert any(
        "additional-attempt authorization" in item
        for item in run["job"].pending_decisions
    )
    assert run["gate"] is None
    assert run["result"].status is not JobState.READY_FOR_APPROVAL


def test_consumer_mode_never_starts_a_second_developer_session_by_itself(tmp_path):
    """One developer attempt, one review, then a person decides.

    This is the retry burn stopped at its source. The measured failure mode was
    a work order permitting three automatic developer sessions, each one a full
    strongest-tier session, spent without anybody choosing to spend them.
    """
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    assessment = assess_request(
        _request(), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    order = assessment.work_order
    assert order.resource_profile == "consumer"
    assert order.max_developer_attempts == 1

    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(
        store, execution, order, opened.job, config, on=DAY
    )
    developed = ingest_developer_result(
        store, execution, usage, order, briefing.job, config,
        _receipt(briefing.packet), on=DAY,
    )
    review_briefing = prepare_review_session(
        store, execution, order, developed.job, config,
        implementer=briefing.employee, on=DAY,
    )
    reviewed = record_review(
        store, execution, order, review_briefing.job, config,
        _attestation(
            order, briefing.packet, developed.receipt,
            review_id="rev-000", verdict=ReviewOutcome.CHANGES_REQUIRED,
        ),
        briefing.packet, developed.receipt,
        implementer=briefing.employee, repo_root=repo, on=DAY,
    )
    assert reviewed.job.state is JobState.DECISION_REQUIRED
    assert reviewed.job.exhausted
    # And the next developer session is not merely discouraged, it is refused.
    with pytest.raises(EngineeringError, match="not an allowed transition"):
        prepare_developer_session(
            store, execution, order, reviewed.job, config, on=DAY
        )


def test_a_profile_is_the_ceiling_on_automatic_attempts(tmp_path):
    """A request cannot buy itself more automatic attempts by naming a number."""
    with pytest.raises(EngineeringError, match="consumer resource profile authorizes"):
        _request(max_developer_attempts=3)
    relaxed = _request(resource_profile="expanded", max_developer_attempts=3)
    assert relaxed.max_developer_attempts == 3
    with pytest.raises(EngineeringError, match="unknown resource profile"):
        _request(resource_profile="unlimited")


# --- receipt prevalidation: an evidence-format defect must not spend the ---
# --- one developer attempt. See docs/company_os_first_real_dogfood.md for --
# --- the run that found it. ------------------------------------------------

TWO_SUITES = (
    "company/engineering/tests/test_alpha.py",
    "company/engineering/tests/test_beta.py",
)


def _open_two_suite_job(tmp_path: Path):
    """A job briefed with two required suites, ready for a developer receipt."""
    assessment = _assessment(tmp_path)
    order = replace(assessment.work_order, required_tests=TWO_SUITES)
    assessment = replace(assessment, work_order=order)
    state = tmp_path / "state"
    config = _config()
    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(
        store, execution, order, opened.job, config, on=DAY
    )
    return store, execution, usage, config, order, briefing


def test_a_valid_receipt_still_behaves_exactly_as_before(tmp_path):
    """Requirement 1: the ordinary accepted path is untouched by prevalidation."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    result = ingest_developer_result(
        store, execution, usage, order, briefing.job, config,
        _receipt(briefing.packet), on=DAY,
    )
    assert result.evidence_rejected is False
    assert result.ingested.accepted
    assert result.job.state is JobState.TESTING
    assert result.job.developer_attempts == 1
    assert result.job_pointer is not None


def test_a_malformed_receipt_is_rejected_before_attempt_consumption(tmp_path):
    """Requirement 2: a receipt that cannot even be decoded never reaches the job."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    before = store.jobs(order.work_order_id)
    raw = briefing.packet.to_dict()  # the wrong shape entirely: a packet, not a receipt
    with pytest.raises(ValidationError):
        SessionReceipt.from_mapping(raw)
    after = store.jobs(order.work_order_id)
    assert after == before
    assert store.job(order.work_order_id).state is JobState.DEVELOPING
    assert store.job(order.work_order_id).developer_attempts == 1


def test_incomplete_required_suite_evidence_is_rejected_before_attempt_consumption(
    tmp_path,
):
    """Requirement 3: one of two required suites simply absent from the receipt."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    partial = _receipt(
        briefing.packet,
        tests=(ReportedTest(command=TWO_SUITES[0], passed=True, summary="ok"),),
    )
    result = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, partial, on=DAY
    )
    assert result.evidence_rejected is True
    assert result.validation.evidence_format_only is True
    assert result.job.state is JobState.DEVELOPING
    assert result.job.developer_attempts == 1
    assert result.job_pointer is None


def test_one_combined_receipt_for_two_required_suites_is_rejected_before_attempt_consumption(
    tmp_path,
):
    """Requirement 4: both suites really ran, but as one command, not two entries."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    combined = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(
                command="pytest " + " ".join(TWO_SUITES), passed=True, summary="ok"
            ),
        ),
    )
    result = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, combined, on=DAY
    )
    assert result.evidence_rejected is True
    assert "required test(s) not reported" in result.validation.reason()
    assert result.job.state is JobState.DEVELOPING
    assert result.job.developer_attempts == 1
    assert result.job_pointer is None


def test_a_corrected_receipt_for_the_same_commit_is_ingested_after_a_format_rejection(
    tmp_path,
):
    """Requirement 5: fixing only the report, not the work, is accepted."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    combined = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(
                command="pytest " + " ".join(TWO_SUITES), passed=True, summary="ok"
            ),
        ),
    )
    rejected = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, combined, on=DAY
    )
    assert rejected.job.state is JobState.DEVELOPING

    corrected = _receipt(briefing.packet)  # same commit; one entry per required suite
    fixed = ingest_developer_result(
        store, execution, usage, order, rejected.job, config, corrected, on=DAY
    )
    assert fixed.evidence_rejected is False
    assert fixed.ingested.accepted
    assert fixed.job.state is JobState.TESTING
    # The correction did not spend a second developer attempt: this job never
    # left `developing` for the first (rejected) receipt.
    assert fixed.job.developer_attempts == 1


def test_a_corrected_receipt_for_a_different_commit_is_refused(tmp_path):
    """Requirement 6: a different commit is a new attempt, not an evidence fix."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    combined = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(
                command="pytest " + " ".join(TWO_SUITES), passed=True, summary="ok"
            ),
        ),
    )
    rejected = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, combined, on=DAY
    )
    different_commit = _receipt(
        briefing.packet, commit_sha=OTHER_SHA, remote_branch_sha=OTHER_SHA
    )
    with pytest.raises(EngineeringError, match="different implementation"):
        ingest_developer_result(
            store, execution, usage, order, rejected.job, config,
            different_commit, on=DAY,
        )
    # Refused before it could touch the job: still developing, still one attempt.
    assert store.job(order.work_order_id).state is JobState.DEVELOPING
    assert store.job(order.work_order_id).developer_attempts == 1


def test_a_genuinely_failing_test_still_follows_the_existing_attempt_semantics(
    tmp_path,
):
    """Requirement 7: a real failure, reported in full, is not a format defect."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    genuinely_failed = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(command=TWO_SUITES[0], passed=True, summary="ok"),
            ReportedTest(command=TWO_SUITES[1], passed=False, summary="broke"),
        ),
    )
    result = ingest_developer_result(
        store, execution, usage, order, briefing.job, config,
        genuinely_failed, on=DAY,
    )
    assert result.evidence_rejected is False
    assert result.validation.evidence_format_only is False
    assert not result.ingested.accepted
    assert result.job.state is JobState.TESTING
    assert result.job.exhausted
    with pytest.raises(EngineeringError, match="not an allowed transition"):
        prepare_developer_session(store, execution, order, result.job, config, on=DAY)


def test_reviewer_failure_still_follows_existing_policy_after_the_fix(tmp_path):
    """Requirement 8: an unrelated stage - review - is unaffected."""
    run = _through_review(
        tmp_path, receipt_changes={}, review_verdict=ReviewOutcome.CHANGES_REQUIRED,
    )
    assert run["job"].state is JobState.DECISION_REQUIRED
    assert run["job"].exhausted


def test_no_automatic_retry_is_introduced_by_the_prevalidation_gate(tmp_path):
    """Requirement 9: rejection is a stop, never a new packet or a new job move."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    jobs_before = store.jobs(order.work_order_id)
    packets_before = execution.packet_records(order.work_order_id)
    combined = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(
                command="pytest " + " ".join(TWO_SUITES), passed=True, summary="ok"
            ),
        ),
    )
    ingest_developer_result(
        store, execution, usage, order, briefing.job, config, combined, on=DAY
    )
    assert store.jobs(order.work_order_id) == jobs_before
    assert execution.packet_records(order.work_order_id) == packets_before


def test_audit_history_records_the_rejection_and_the_correction(tmp_path):
    """Requirement 10: both the refused evidence and the accepted fix are on file."""
    store, execution, usage, config, order, briefing = _open_two_suite_job(tmp_path)
    combined = _receipt(
        briefing.packet,
        tests=(
            ReportedTest(
                command="pytest " + " ".join(TWO_SUITES), passed=True, summary="ok"
            ),
        ),
    )
    rejected = ingest_developer_result(
        store, execution, usage, order, briefing.job, config, combined, on=DAY
    )
    corrected = _receipt(briefing.packet)
    fixed = ingest_developer_result(
        store, execution, usage, order, rejected.job, config, corrected, on=DAY
    )
    stored = execution.receipts(order.work_order_id)
    assert len(stored) == 2
    assert stored[0].fingerprint() == rejected.receipt.fingerprint()
    assert stored[1].fingerprint() == fixed.receipt.fingerprint()
    assert stored[0].tests != stored[1].tests


def test_an_unanswered_acceptance_criterion_prevents_readiness(tmp_path):
    run = _through_review(tmp_path, attestation_changes={"criteria": ()})
    assert run["review"].unanswered_criteria
    assert run["review"].outcome is ReviewOutcome.CHANGES_REQUIRED


def test_a_satisfied_criterion_must_name_its_evidence():
    with pytest.raises(EngineeringError, match="names what satisfies it"):
        CriterionFinding(criterion="c", satisfied=True)


def test_an_attestation_cannot_claim_a_deterministic_finding():
    with pytest.raises(EngineeringError, match="cannot be marked deterministic"):
        ReviewerAttestation(
            review_id="rev-x", work_order_id="wo-x", work_order_fingerprint="0" * 16,
            reviewer="chief_architect", packet_fingerprint="0" * 16,
            receipt_fingerprint="0" * 16, verdict=ReviewOutcome.PASS, reviewed_on=DAY,
            findings=(
                ReviewFinding(
                    finding_id="f-1", severity=FindingSeverity.ADVISORY,
                    summary="s", deterministic=True,
                ),
            ),
        )


def test_a_review_outcome_cannot_be_set_independently_of_its_inputs(tmp_path):
    run = _through_review(tmp_path)
    with pytest.raises(EngineeringError, match="worst of the attested"):
        replace(run["review"], outcome=ReviewOutcome.PASS,
                deterministic_outcome=ReviewOutcome.BLOCKED)


# --- 7. protected policy cannot be weakened by the implementer ----------


def test_a_modified_protected_file_is_detected(tmp_path):
    repo = _fake_repo(tmp_path)
    surface = ProtectedSurface.capture(repo, authorized_paths=("company/engineering",))
    assert surface.verify(repo) == ()
    (repo / "company" / "permissions.yaml").write_text(
        "# weakened\nceo_reserved: []\n", encoding="utf-8"
    )
    assert any(
        "company/permissions.yaml was modified" in item for item in surface.verify(repo)
    )


def test_a_deleted_protected_file_is_a_finding(tmp_path):
    repo = _fake_repo(tmp_path)
    surface = ProtectedSurface.capture(repo, authorized_paths=("company/engineering",))
    (repo / "company" / "integration" / "policy.py").unlink()
    assert any("was deleted during execution" in item for item in surface.verify(repo))


def test_the_default_protected_surface_covers_the_gate_and_the_contracts():
    for expected in (
        "company/permissions.yaml", "company/constitution.md",
        "company/integration/policy.py", "company/integration/checks.py",
        "company/integration/suites.py", "ai_platform/policy.py",
        "company/validation/no_subagents.py", "company/org_registry.yaml",
    ):
        assert expected in DEFAULT_PROTECTED_PATHS


def test_a_stored_protected_surface_cannot_drop_a_default_path():
    surface = ProtectedSurface.capture(ROOT, authorized_paths=("company/engineering",))
    payload = surface.to_dict()
    payload["entries"] = [
        item for item in payload["entries"] if item["path"] != "company/permissions.yaml"
    ]
    with pytest.raises(EngineeringError, match="missing default protected path"):
        ProtectedSurface.from_mapping(payload)


def test_a_protected_change_escalates_to_the_ceo_rather_than_a_retry(tmp_path):
    """The receipt does not mention the edit. The digest does."""

    def weaken(repo: Path) -> None:
        (repo / "company" / "permissions.yaml").write_text(
            "ceo_reserved: []\n", encoding="utf-8"
        )

    run = _through_review(tmp_path, tamper=weaken)
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    assert run["job"].state is JobState.DECISION_REQUIRED
    assert any("CEO decision" in item for item in run["review"].escalations)
    assert any(
        item.finding_id.startswith("protected-") for item in run["review"].findings
    )


# --- 8. the gate is distinct, read, and unforgeable ---------------------


def test_engineering_imports_neither_the_gate_nor_the_dashboard():
    modules, failures = parse_tree(ROOT, ("company",))
    assert not failures
    engineering = [m for m in modules if subsystem_of(m.path) == "company/engineering"]
    assert engineering, "the engineering subsystem has no modules"
    for module in engineering:
        for ref in module_imports(module):
            target = module_subsystem(ref.module)
            assert target != "company/integration", (
                f"{ref.reference()} imports the gate, which closes a subsystem cycle"
            )
            assert target != "company/dashboard", ref.reference()


def test_the_readiness_mirror_agrees_with_the_gates_own_rule():
    required = sorted(DEFAULT_POLICY.required)
    for status in ("pass", "fail", "unknown", "not_applicable"):
        report = _gate_report(GateReadiness.READY)
        report["sections"][0]["checks"][0]["status"] = status
        checks = tuple(
            GateCheck(
                check_id=item["check_id"],
                category=GateCategory(item["check_id"].split(".", 1)[0]),
                status=GateStatus(item["status"]),
                requirement="r",
                detail="d",
                evidence_kind=EvidenceKind.REPOSITORY,
                blocker_reason=(
                    "the condition does not hold" if item["status"] == "fail" else ""
                ),
                missing_evidence=(
                    ("nobody has shown this",) if item["status"] == "unknown" else ()
                ),
                remediation=(
                    "establish the condition" if item["status"] != "pass" else ""
                ),
                not_applicable_reason=(
                    "the hazard cannot arise here"
                    if item["status"] == "not_applicable"
                    else ""
                ),
            )
            for item in report["sections"][0]["checks"]
        )
        assert readiness_from(report).value == readiness_of(
            checks, frozenset(required)
        ).value, status


def test_a_gate_report_claiming_to_authorize_integration_is_refused():
    report = _gate_report(GateReadiness.READY)
    report["authorizes_production_integration"] = True
    with pytest.raises(EngineeringError, match="claims to authorize"):
        GateVerdict.from_report_mapping(report, work_order_id="wo-req-001")


def test_a_reported_readiness_that_disagrees_with_the_report_is_refused():
    with pytest.raises(EngineeringError, match="The report decides"):
        GateVerdict.from_report_mapping(
            _gate_report(GateReadiness.BLOCKED),
            work_order_id="wo-req-001", reported_readiness="ready",
        )


def test_a_report_with_no_required_check_cannot_say_ready():
    report = _gate_report(GateReadiness.READY)
    report["required_check_ids"] = []
    with pytest.raises(EngineeringError, match="names no required check"):
        GateVerdict.from_report_mapping(report, work_order_id="wo-req-001")


def test_gate_failure_prevents_readiness(tmp_path):
    run = _drive(tmp_path, readiness=GateReadiness.BLOCKED)
    assert run["gate"].readiness is GateReadiness.BLOCKED
    assert run["job"].state is JobState.BLOCKED
    assert run["result"].status is JobState.BLOCKED
    assert run["result"].gate_blockers


def test_missing_gate_evidence_prevents_readiness(tmp_path):
    run = _drive(tmp_path, readiness=GateReadiness.INSUFFICIENT_EVIDENCE)
    assert run["gate"].readiness is GateReadiness.INSUFFICIENT_EVIDENCE
    assert run["job"].state is JobState.BLOCKED


def test_a_gate_verdict_from_another_commit_does_not_describe_this_work(tmp_path):
    run = _through_review(tmp_path)
    assert run["job"].state is JobState.GATE
    stale = GateVerdict.from_report_mapping(
        _gate_report(GateReadiness.READY, commit=OTHER_SHA),
        work_order_id=run["order"].work_order_id,
    )
    moved, _gate_pointer, _job_pointer = record_gate(
        run["store"], run["order"], run["job"], stale, on=DAY,
        implementation_commit=SHA,
    )
    assert moved.state is JobState.BLOCKED
    assert "does not describe this work" in moved.transitions[-1].reason


def test_the_gate_cannot_be_reached_before_review_passes(tmp_path):
    order = _order(tmp_path)
    job = EngineeringJob.open(order, on=DAY).advance(
        JobState.PLANNING, on=DAY, reason="planned"
    )
    verdict = GateVerdict.from_report_mapping(
        _gate_report(GateReadiness.READY), work_order_id=order.work_order_id
    )
    with pytest.raises(EngineeringError, match="after review passes"):
        record_gate(EngineeringStore(tmp_path / "gate-state"), order, job, verdict, on=DAY)


# --- 9. the bounded correction loop -------------------------------------


def test_the_correction_loop_is_bounded_by_the_work_order(tmp_path):
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    # The expanded profile is the one that authorizes an automatic correction
    # loop at all. Under consumer mode there is nothing to bound: the first
    # changes_required is already the last.
    assessment = assess_request(
        _request(resource_profile="expanded", max_developer_attempts=2),
        config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    order = opened.work_order
    assert order.max_developer_attempts == 2
    job = opened.job
    failing = {
        "tests": (
            ReportedTest(
                command="tests/test_company_engineering_execution.py",
                passed=False, summary="1 failed",
            ),
        ),
    }
    states = []
    for attempt in range(2):
        briefing = prepare_developer_session(store, execution, order, job, config, on=DAY)
        assert briefing.job.developer_attempts == attempt + 1
        developed = ingest_developer_result(
            store, execution, usage, order, briefing.job, config,
            _receipt(briefing.packet, **failing), on=DAY,
        )
        review_briefing = prepare_review_session(
            store, execution, order, developed.job, config,
            implementer=briefing.employee, on=DAY,
        )
        reviewed = record_review(
            store, execution, order, review_briefing.job, config,
            _attestation(
                order, briefing.packet, developed.receipt,
                review_id=f"rev-{attempt:03d}", verdict=ReviewOutcome.CHANGES_REQUIRED,
            ),
            briefing.packet, developed.receipt,
            implementer=briefing.employee, repo_root=repo, on=DAY,
        )
        job = reviewed.job
        states.append(job.state)
    assert states[0] is JobState.PLANNING
    assert states[1] is JobState.DECISION_REQUIRED
    assert job.exhausted
    assert any(
        "authorized developer attempt(s) are spent" in item
        for item in job.pending_decisions
    )
    # Two independent guards. From `decision_required` a developer session is
    # not reachable at all, and even from `planning` the spent ceiling refuses.
    with pytest.raises(EngineeringError, match="not an allowed transition"):
        prepare_developer_session(store, execution, order, job, config, on=DAY)
    forced = replace(job, state=JobState.PLANNING, pending_decisions=(),
                     transitions=job.transitions[:-1] + (
                         replace(job.transitions[-1], to_state=JobState.PLANNING),))
    assert forced.exhausted
    assert "used all" in forced.refusal(JobState.DEVELOPING)
    with pytest.raises(EngineeringError, match="used all"):
        prepare_developer_session(store, execution, order, forced, config, on=DAY)


def test_only_issuing_a_packet_spends_a_developer_attempt():
    entering = [
        state for state, targets in ALLOWED_TRANSITIONS.items()
        if JobState.DEVELOPING in targets
    ]
    assert entering == [JobState.PLANNING]


def test_a_job_cannot_carry_more_attempts_than_the_work_order_allows(tmp_path):
    order = _order(tmp_path)
    job = EngineeringJob.open(order, on=DAY)
    with pytest.raises(EngineeringError, match="exceeds the authorized ceiling"):
        replace(job, developer_attempts=order.max_developer_attempts + 1)


def test_the_state_machine_has_no_unbounded_loop():
    """Every cycle in the machine passes through `developing`, which is bounded."""
    for state, targets in ALLOWED_TRANSITIONS.items():
        assert state not in targets, f"{state.value} loops to itself"
    assert ALLOWED_TRANSITIONS[JobState.FAILED] == frozenset()
    assert ALLOWED_TRANSITIONS[JobState.CLOSED] == frozenset()


# --- 10. DECISION REQUIRED ----------------------------------------------


def test_a_decision_required_stop_must_name_its_reasons(tmp_path):
    job = EngineeringJob.open(_order(tmp_path), on=DAY)
    with pytest.raises(EngineeringError, match="at least one reason"):
        job.requiring_decision((), on=DAY)
    stopped = job.requiring_decision(("the objective needs a business decision",), on=DAY)
    assert stopped.state is JobState.DECISION_REQUIRED
    assert stopped.pending_decisions == ("the objective needs a business decision",)
    assert stopped.awaits_ceo


def test_a_new_dependency_is_an_escalation_and_not_a_correction(tmp_path):
    run = _drive(tmp_path, receipt_changes={"dependencies_added": ("requests>=2",)})
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    assert run["job"].state is JobState.DECISION_REQUIRED
    assert any(
        "architecture_and_security_review" in item for item in run["review"].escalations
    )
    assert run["result"].decisions_required


# --- 11. the happy path reaches ready_for_approval, and integrates nothing


def test_the_whole_loop_reaches_ready_for_approval(tmp_path):
    run = _drive(tmp_path)
    job, result = run["job"], run["result"]
    assert job.state is JobState.READY_FOR_APPROVAL
    assert result.status is JobState.READY_FOR_APPROVAL
    assert result.ready
    assert result.review_outcome is ReviewOutcome.PASS
    assert result.gate_readiness is GateReadiness.READY
    assert result.commit_sha == SHA
    assert result.remote_verified
    assert result.changed_files == ("company/engineering/verify.py",)
    visited = [transition.to_state for transition in job.transitions]
    for stage in MAIN_SEQUENCE:
        assert stage in visited, stage


def test_a_successful_workflow_does_not_merge(tmp_path):
    run = _drive(tmp_path)
    assert run["receipt"].merge_performed is False
    assert run["result"].merge_performed is False
    assert run["result"].authorizes_merge is False
    assert JobState.CLOSED not in [t.to_state for t in run["job"].transitions]


def test_a_receipt_reporting_a_merge_blocks_the_job(tmp_path):
    run = _drive(tmp_path, receipt_changes={"merge_performed": True})
    assert run["review"].outcome is ReviewOutcome.BLOCKED
    assert run["job"].state is JobState.DECISION_REQUIRED


def test_no_job_state_means_approved():
    for state in JobState:
        for word in ("approved", "merged", "published", "deployed"):
            assert word not in state.value, state
    assert JobState.READY_FOR_APPROVAL.value == "ready_for_approval"
    assert ALLOWED_TRANSITIONS[JobState.CLOSED] == frozenset()


def test_ready_for_approval_is_not_read_as_approval(tmp_path):
    run = _drive(tmp_path)
    job = run["job"]
    assert job.state is JobState.READY_FOR_APPROVAL
    assert job.approved is False
    assert job.awaits_ceo
    rendered = run["result"].render_text()
    assert "READY_FOR_APPROVAL" in rendered
    assert NOT_AN_APPROVAL in rendered
    assert "[APPROVE]" in rendered and "[REQUEST CHANGES]" in rendered


def test_a_result_cannot_claim_readiness_the_records_do_not_support(tmp_path):
    run = _drive(tmp_path)
    with pytest.raises(EngineeringError, match="Readiness is derived"):
        replace(run["result"], gate_readiness=GateReadiness.BLOCKED)


# --- 12. the CEO decision is recorded, never executed -------------------


def test_an_approval_is_recorded_and_performs_nothing(tmp_path):
    run = _drive(tmp_path)
    order = run["order"]
    decision = CEODecision(
        decision_id="dec-001",
        work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(),
        verdict=CEOVerdict.APPROVE,
        decided_by="MGI",
        decided_on=DAY,
        rationale="Read the result; the scope and the tests match the request.",
        reviewed_state=JobState.READY_FOR_APPROVAL,
    )
    moved, _dp, _jp = record_decision(run["store"], order, run["job"], decision)
    assert moved.state is JobState.CLOSED
    assert decision.authorizes_merge is False
    assert run["store"].decisions(order.work_order_id)[-1].verdict is CEOVerdict.APPROVE
    assert run["store"].integrity(order.work_order_id) == ()


def test_a_decision_cannot_claim_merge_authority(tmp_path):
    order = _order(tmp_path)
    with pytest.raises(EngineeringError, match="never carries merge authority"):
        CEODecision(
            decision_id="dec-x", work_order_id=order.work_order_id,
            work_order_fingerprint=order.fingerprint(), verdict=CEOVerdict.APPROVE,
            decided_by="MGI", decided_on=DAY, rationale="r",
            reviewed_state=JobState.READY_FOR_APPROVAL, authorizes_merge=True,
        )


def test_a_decision_must_name_a_person_and_not_the_system(tmp_path):
    order = _order(tmp_path)
    for name in ("system", "company_os", "claude", "codex", "automated"):
        with pytest.raises(EngineeringError, match="is not a person"):
            CEODecision(
                decision_id="dec-x", work_order_id=order.work_order_id,
                work_order_fingerprint=order.fingerprint(), verdict=CEOVerdict.REJECT,
                decided_by=name, decided_on=DAY, rationale="r",
                reviewed_state=JobState.BLOCKED,
            )


def test_a_job_that_is_not_ready_cannot_be_approved(tmp_path):
    order = _order(tmp_path)
    with pytest.raises(EngineeringError, match="cannot be approved"):
        CEODecision(
            decision_id="dec-x", work_order_id=order.work_order_id,
            work_order_fingerprint=order.fingerprint(), verdict=CEOVerdict.APPROVE,
            decided_by="MGI", decided_on=DAY, rationale="r",
            reviewed_state=JobState.BLOCKED,
        )


def test_request_changes_returns_the_job_to_planning(tmp_path):
    run = _drive(tmp_path)
    order = run["order"]
    decision = CEODecision(
        decision_id="dec-002", work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(),
        verdict=CEOVerdict.REQUEST_CHANGES, decided_by="MGI", decided_on=DAY,
        rationale="Narrow the helper.", reviewed_state=JobState.READY_FOR_APPROVAL,
        required_changes=("split the helper in two",),
    )
    moved, _dp, _jp = record_decision(run["store"], order, run["job"], decision)
    assert moved.state is JobState.PLANNING


def test_a_decision_taken_on_a_stale_state_is_refused(tmp_path):
    run = _drive(tmp_path)
    order = run["order"]
    decision = CEODecision(
        decision_id="dec-003", work_order_id=order.work_order_id,
        work_order_fingerprint=order.fingerprint(), verdict=CEOVerdict.REJECT,
        decided_by="MGI", decided_on=DAY, rationale="r",
        reviewed_state=JobState.BLOCKED,
    )
    with pytest.raises(EngineeringError, match="re-read the result"):
        record_decision(run["store"], order, run["job"], decision)


# --- 13. records are immutable and provenanced --------------------------


def test_the_execution_history_is_append_only_and_provenanced(tmp_path):
    run = _drive(tmp_path)
    execution, order, packet = run["execution"], run["order"], run["packet"]
    history = execution.history(order.work_order_id)
    assert history["packets"] and history["attempts"]
    attempt = history["attempts"][0]
    assert attempt["authority_fingerprint"]
    assert attempt["packet_fingerprint"] == packet.fingerprint()
    assert attempt["subagents_used"] == 0
    authority = execution.authority(
        order.work_order_id, packet.fingerprint(), attempt["packet_attempt"]
    )
    assert authority is not None
    assert authority.may_write == (
        "company/engineering",
        "tests/test_company_engineering_execution.py",
    )
    assert "company/permissions.yaml" in authority.may_not_modify


def test_a_second_write_never_replaces_a_record(tmp_path):
    run = _drive(tmp_path)
    store, order = run["store"], run["order"]
    before = len(store.jobs(order.work_order_id))
    store.append_job(run["job"])
    after = store.jobs(order.work_order_id)
    assert len(after) == before + 1
    assert after[-1].fingerprint() == run["job"].fingerprint()


def test_the_store_reports_a_contradiction_rather_than_hiding_it(tmp_path):
    run = _drive(tmp_path)
    store, order = run["store"], run["order"]
    assert store.integrity(order.work_order_id) == ()
    store.append_review(replace(run["review"], work_order_fingerprint="0" * 16))
    assert any(
        "references work order" in item for item in store.integrity(order.work_order_id)
    )


def test_a_receipt_claiming_a_nested_agent_cannot_pass(tmp_path):
    run = _through_review(tmp_path)
    packet = run["packet"]
    validation = validate_receipt(packet, _receipt(packet, subagents_used=2))
    assert any("nested agent" in item for item in validation.failures)
    with pytest.raises(SubagentPolicyViolation):
        _receipt(packet, no_subagents=False)


# --- 14. the package holds none of the capabilities the gate forbids ----


def _package_trees():
    for path in sorted(PACKAGE.glob("*.py")):
        yield path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_no_publishing_or_process_capability_is_introduced():
    forbidden_modules = {
        "subprocess", "multiprocessing", "pty", "socket", "http", "urllib",
        "requests", "httpx", "ftplib", "smtplib", "asyncio", "ssl",
    }
    forbidden_calls = {
        "system", "popen", "fork", "forkpty", "execv", "execve", "execl",
        "spawnv", "spawnl", "posix_spawn",
    }
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert alias.name.split(".")[0] not in forbidden_modules, (
                        f"{path.name}:{node.lineno} imports {alias.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert node.module.split(".")[0] not in forbidden_modules, (
                    f"{path.name}:{node.lineno} imports from {node.module}"
                )
            elif isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert name not in forbidden_calls, (
                    f"{path.name}:{node.lineno} calls {name}"
                )


def test_no_credential_is_read_by_this_package():
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                raise AssertionError(f"{path.name}:{node.lineno} reads the environment")
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None)
                assert name not in ("getenv", "expandvars"), f"{path.name}:{node.lineno}"
    from company.engineering.intake import CREDENTIAL_TRIGGERS

    assert "oauth" in CREDENTIAL_TRIGGERS and "secret" in CREDENTIAL_TRIGGERS


def test_the_package_names_no_absolute_or_production_path():
    """No path-shaped string constant is absolute or points into production.

    Docstrings are `ast.Constant` too, so only single-line strings that look
    like a path are considered: one segment separator, no spaces. Prose about
    `sloped/` in a comment is not a write into it.
    """
    for path, tree in _package_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            value = node.value
            if len(value) < 4 or "\n" in value or " " in value or "/" not in value:
                continue
            assert not value.startswith("/"), f"{path.name}:{node.lineno} {value!r}"
            for root in ("sloped/", "race/", "godot/", "tools/", "production/",
                         "marble3d/", "engine/", "rendering/"):
                assert not value.startswith(root), (
                    f"{path.name}:{node.lineno} {value!r}"
                )


def test_the_escalation_list_covers_every_situation_the_brief_names():
    for phrase in (
        "architecture", "dependency", "credential", "widening the objective",
        "protected governance", "business question", "destructive", "merging",
    ):
        assert any(phrase in item for item in ESCALATE_INSTEAD_OF), phrase


def test_the_youtube_subsystem_is_untouched_by_this_milestone():
    modules, _failures = parse_tree(ROOT, ("company",))
    engineering = [m for m in modules if subsystem_of(m.path) == "company/engineering"]
    for module in engineering:
        for ref in module_imports(module):
            assert module_subsystem(ref.module) != "company/youtube", ref.reference()
    for path, _tree in _package_trees():
        assert "youtube" not in path.read_text(encoding="utf-8").lower(), path.name


def test_the_engineering_package_is_owned_by_exactly_one_capsule():
    index = _index()
    owners = [
        capsule.id
        for capsule in index.all()
        if any(path_related(claim, "company/engineering") for claim in capsule.owns_paths)
    ]
    assert owners == ["company-engineering-execution"]
    capsule = index.get("company-engineering-execution")
    assert capsule.tests == ("tests/test_company_engineering_execution.py",)
    assert len(dumps(capsule)) <= 4000


# --- 15. EngineeringResult.developer_attempts_remaining -----------------


def test_developer_attempts_remaining_field_and_rendering(tmp_path):
    """The result carries attempts_remaining from the job and renders it beside used."""
    # Under the consumer profile max_developer_attempts is 1. Before the first
    # packet is issued the job is in PLANNING with 0 attempts consumed and 1
    # remaining - exactly the non-zero remaining case the test needs.
    order = _order(tmp_path)
    job = (
        EngineeringJob.open(order, on=DAY)
        .advance(JobState.PLANNING, on=DAY, reason="planned")
    )
    assert job.developer_attempts == 0
    assert job.corrections_remaining == 1

    result = EngineeringResult.build(order, job)

    # Field value comes directly from job.corrections_remaining, not reimplemented.
    assert result.developer_attempts_remaining == job.corrections_remaining

    # Rendered page shows the new field beside the existing one.
    page = result.render_text()
    assert "developer attempts: 0  remaining: 1" in page

    # Round-trip through to_dict and from_mapping.
    data = result.to_dict()
    assert data["developer_attempts_remaining"] == 1
    restored = EngineeringResult.from_mapping(data)
    assert restored.developer_attempts_remaining == 1


def test_developer_attempts_remaining_null_and_absent_cases(tmp_path):
    """from_mapping treats a JSON-null value and an absent key identically (both -> None),
    while an explicit 0 is distinguishable, and to_dict/from_mapping round-trips all four cases."""
    order = _order(tmp_path)
    job = EngineeringJob.open(order, on=DAY).advance(JobState.PLANNING, on=DAY, reason="planned")
    base_result = EngineeringResult.build(order, job)

    # Build a base mapping we can manipulate.
    base_data = base_result.to_dict()

    # Case 1: absent key -> None.
    data_absent = {k: v for k, v in base_data.items() if k != "developer_attempts_remaining"}
    assert "developer_attempts_remaining" not in data_absent
    restored_absent = EngineeringResult.from_mapping(data_absent)
    assert restored_absent.developer_attempts_remaining is None

    # Case 2: explicit JSON null (the bug: previously raised TypeError) -> None.
    data_null = {**base_data, "developer_attempts_remaining": None}
    restored_null = EngineeringResult.from_mapping(data_null)
    assert restored_null.developer_attempts_remaining is None

    # Case 3: explicit 0 -> 0, distinguishable from None.
    data_zero = {**base_data, "developer_attempts_remaining": 0}
    restored_zero = EngineeringResult.from_mapping(data_zero)
    assert restored_zero.developer_attempts_remaining == 0
    assert restored_zero.developer_attempts_remaining is not None

    # Null round-trip: None persists through to_dict (as JSON null) and back.
    result_none = EngineeringResult.build(order, job)
    # Patch the dict to simulate a persisted None.
    patched = {**result_none.to_dict(), "developer_attempts_remaining": None}
    assert EngineeringResult.from_mapping(patched).developer_attempts_remaining is None

    # render_text shows 'unknown' for None and the integer for non-None.
    page_none = restored_null.render_text()
    assert "remaining: unknown" in page_none
    page_zero = restored_zero.render_text()
    assert "remaining: 0" in page_zero


# --- 16. the CEO surface ------------------------------------------------


def test_the_result_page_answers_every_question_the_brief_lists(tmp_path):
    run = _drive(tmp_path)
    rendered = run["result"].render_text()
    for heading in (
        "WORK ORDER", "STATUS", "IMPLEMENTATION", "TESTS", "REVIEW", "GATE",
        "RISKS", "DECISIONS REQUIRED", "CEO OPTIONS",
    ):
        assert heading in rendered, heading
    assert run["order"].objective in rendered
    assert SHA in rendered


def test_the_result_groups_tests_by_the_question_they_answer(tmp_path):
    run = _drive(tmp_path)
    result = replace(
        run["result"],
        tests=run["result"].tests
        + (
            ResultTest(
                command="tests/", passed=True, scope=SuiteScope.FULL_SUITE,
                summary="4177 passed, 6 pre-existing failures",
            ),
        ),
    )
    rendered = result.render_text()
    assert "targeted:" in rendered
    assert "affected Company OS" in rendered
    assert "full repository suite: 1/1 passed" in rendered


def test_an_empty_test_scope_reads_as_none_reported_and_never_as_passing(tmp_path):
    run = _drive(tmp_path)
    assert "full repository suite: none reported" in run["result"].render_text()


def test_the_history_is_readable_as_one_serialisable_object(tmp_path):
    run = _drive(tmp_path)
    history = run["store"].history(run["order"].work_order_id)
    assert history["state"] == "ready_for_approval"
    assert history["reviews"][0]["implementer"] != history["reviews"][0]["reviewer"]
    assert history["gate_verdicts"][0]["readiness"] == "ready"
    assert history["work_order"]["fingerprint"] == run["order"].fingerprint()
    json.dumps(history)


def test_every_record_round_trips_through_its_own_decoder(tmp_path):
    run = _drive(tmp_path)
    order = run["order"]
    for record, decoder in (
        (order, EngineeringWorkOrder.from_mapping),
        (run["job"], EngineeringJob.from_mapping),
        (run["review"], EngineeringReview.from_mapping),
        (run["gate"], GateVerdict.from_mapping),
        (run["result"], EngineeringResult.from_mapping),
        (derive_plan(order, proposed_on=DAY), ImplementationPlan.from_mapping),
    ):
        again = decoder(json.loads(dumps(record)))
        assert again.fingerprint() == record.fingerprint(), type(record).__name__


# --- 17. the CEO dashboard surface --------------------------------------
#
# The CEO already has a read-only projection and a brief. These tests hold the
# engineering section to the two properties that matter: every lifecycle state
# is visible, and the projection cannot act.


def _snapshot(state: Path):
    from company.dashboard.brief import build_brief
    from company.dashboard.builder import CompanyStatePaths, build_snapshot

    snapshot = build_snapshot(
        sources=CompanyStatePaths.flat(state), as_of=DAY, repo_root=ROOT
    )
    return snapshot, build_brief(snapshot)


def test_every_lifecycle_state_is_a_dashboard_dimension(tmp_path):
    run = _drive(tmp_path)
    snapshot, _brief = _snapshot(run["state"])
    section = snapshot.section("engineering")
    names = {item.name for item in section.dimensions}
    for state in JobState:
        assert f"jobs_{state.value}" in names, state
    values = {item.name: item.value for item in section.dimensions}
    assert values["jobs_ready_for_approval"] == 1
    assert values["work_orders"] == 1
    assert values["awaiting_ceo"] == 1
    assert values["developer_attempts"] == 1
    assert values["reviews_independent"] is True


def test_a_ready_job_reaches_the_ceo_decision_queue_and_the_brief(tmp_path):
    run = _drive(tmp_path)
    snapshot, brief = _snapshot(run["state"])
    items = [
        item for item in snapshot.decision_queue
        if item.source_subsystem.value == "engineering"
    ]
    assert len(items) == 1
    item = items[0]
    assert item.current_state == "ready_for_approval"
    assert item.reserved_actions == ("merge_major_architecture_rewrite",)
    assert "nothing is merged" in item.why_ceo_attention
    assert item.evidence_refs
    assert any(run["order"].objective[:40] in line for line in brief.decisions)


def test_the_projection_reports_zero_authorized_merges(tmp_path):
    run = _drive(tmp_path)
    snapshot, _brief = _snapshot(run["state"])
    section = snapshot.section("engineering")
    merges = next(item for item in section.dimensions if item.name == "merges_authorized")
    assert merges.value == 0
    assert merges.known is True
    assert "structurally zero" in merges.note.lower()


def test_a_blocked_job_is_an_attention_item_rather_than_a_silent_state(tmp_path):
    run = _drive(tmp_path, readiness=GateReadiness.BLOCKED)
    assert run["job"].state is JobState.BLOCKED
    snapshot, _brief = _snapshot(run["state"])
    items = [
        item for item in snapshot.attention_items if item.category == "engineering"
    ]
    assert len(items) == 1
    assert items[0].level.value == "blocked"
    assert items[0].resolves_when


def test_the_snapshot_over_a_real_run_has_no_integrity_issue(tmp_path):
    run = _drive(tmp_path)
    snapshot, _brief = _snapshot(run["state"])
    assert snapshot.unresolved_integrity_issues == ()
    assert snapshot.section("engineering").availability.value == "available"


def test_an_empty_store_reports_missing_rather_than_zero(tmp_path):
    """No work order is unknown, not a company with nothing to do."""
    (tmp_path / "empty").mkdir()
    snapshot, _brief = _snapshot(tmp_path / "empty")
    section = snapshot.section("engineering")
    assert section.availability.value == "missing"
    assert "engineering:no_work_orders" in section.missing


def test_the_dashboard_projection_cannot_act_on_a_work_order():
    """A read model with a verb is a read model that can be talked into using it."""
    import company.dashboard as dashboard

    forbidden = ("approve", "reject", "merge", "decide", "advance", "close", "publish")
    for name in dir(dashboard):
        assert not any(name.lower().startswith(verb) for verb in forbidden), name


def test_a_revalidation_without_the_authority_evidence_fails_an_honest_receipt(tmp_path):
    """The defect the review stage had: less evidence is not a stricter check."""
    run = _through_review(tmp_path)
    bare = validate_receipt(run["packet"], run["receipt"])
    assert any("authority evidence" in item for item in bare.failures)
    assert _validation(run).ok


# --- efficiency directives in briefings ------------------------------------

from company.engineering.transport import developer_briefing_payload, review_briefing_payload


def test_developer_briefing_carries_a_resource_strategy_artifact(tmp_path):
    """The briefing carries one validated artifact, and it can only narrow.

    This is the whole Company-OS-to-runner protocol for execution economics.
    It is checked for the fields the runner reads, and - the part that is
    governance rather than efficiency - for the fields it must never contain.
    """
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    assessment = assess_request(
        _request(), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(
        store, execution, opened.work_order, opened.job, config, on=DAY,
    )
    payload = developer_briefing_payload(briefing)
    eff = payload["efficiency"]

    assert eff["artifact_version"] == RESOURCE_STRATEGY_VERSION
    assert eff["profile"] == "consumer"
    assert eff["model_tier"] in ("standard", "strongest")
    assert eff["provider_count"] == 1
    assert eff["parallel_sessions"] == 1
    assert eff["resource_ceiling"]["max_wall_seconds"] > 0
    assert eff["resource_ceiling"]["max_session_cost"]
    assert eff["context"]["narrowed_at"] == "intake"
    assert eff["context"]["ref_count"] == len(briefing.packet.context_refs)
    assert eff["strategy_reason"]

    # Governance: the artifact carries no authority of any kind. A resource
    # strategy that could name a path would be a second place a scope is set.
    forbidden = {
        "authorized_paths", "may_write", "forbidden_paths", "path_scope",
        "authorized_branch", "protected_paths", "allowed_tools",
    }
    assert not forbidden & set(eff)

    # And it says plainly which of its ceilings anybody actually holds.
    assert eff["enforcement"]["advisory_only"]
    assert any("max_turns" in line for line in eff["enforcement"]["advisory_only"])


def test_a_routine_request_reaches_the_standard_tier(tmp_path):
    """The whole cost lever, end to end, through real production intake.

    Not a unit test of `select_strategy`: that always could return STANDARD.
    This drives a real CEO request through `assess_request`,
    `prepare_developer_session` and `developer_briefing_payload`, which is the
    path that could not produce a standard-tier recommendation before.
    """
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    assessment = assess_request(
        _routine_request(), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.work_order.specialist_domain == ""
    assert "routine implementation" in assessment.derivation.specialist_reason

    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)

    briefing = prepare_developer_session(
        store, execution, opened.work_order, opened.job, config, on=DAY,
    )
    payload = developer_briefing_payload(briefing)
    assert briefing.packet.reasoning_class is ReasoningClass.C
    assert payload["efficiency"]["model_tier"] == "standard"
    assert payload["efficiency"]["escalation"] == "none"


def test_a_governance_request_reaches_the_strongest_tier(tmp_path):
    """And the same path still routes real risk upward."""
    repo = _fake_repo(tmp_path)
    state = tmp_path / "state"
    config = _config()
    assessment = assess_request(
        _request(
            objective=(
                "Rewrite the governance approval boundary so a protected policy "
                "file cannot be changed without a separate reviewer."
            ),
        ),
        config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-002",
    )
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.work_order.specialist_domain
    store, execution, usage = _stores(state)
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(
        store, execution, opened.work_order, opened.job, config, on=DAY,
    )
    payload = developer_briefing_payload(briefing)
    assert briefing.packet.reasoning_class is ReasoningClass.D
    assert payload["efficiency"]["model_tier"] == "strongest"


def test_a_high_risk_request_reaches_the_strongest_tier(tmp_path):
    repo = _fake_repo(tmp_path)
    config = _config()
    assessment = assess_request(
        _routine_request(risk=Risk.HIGH), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-003",
    )
    order = assessment.work_order
    assert order.specialist_domain == "high_risk_change"
    store, execution, usage = _stores(tmp_path / "state")
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(store, execution, order, opened.job, config, on=DAY)
    assert developer_briefing_payload(briefing)["efficiency"]["model_tier"] == "strongest"


def test_an_explicit_escalation_reaches_the_strongest_tier(tmp_path):
    repo = _fake_repo(tmp_path)
    config = _config()
    assessment = assess_request(
        _routine_request(escalate_reasoning=True), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-004",
    )
    order = assessment.work_order
    assert order.escalation == "explicit_escalation"
    store, execution, usage = _stores(tmp_path / "state")
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(store, execution, order, opened.job, config, on=DAY)
    payload = developer_briefing_payload(briefing)
    assert payload["efficiency"]["model_tier"] == "strongest"
    assert payload["efficiency"]["escalation"] == "explicit_escalation"


def test_a_correction_attempt_escalates_because_the_cheaper_model_failed(tmp_path):
    """The fourth route to the strongest tier, and the only one that is earned.

    A second attempt exists only because a standard-tier session was reviewed
    and found wanting. That is evidence about this task, not a guess.
    """
    repo = _fake_repo(tmp_path)
    config = _config()
    assessment = assess_request(
        _routine_request(resource_profile="expanded", max_developer_attempts=2),
        config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-005",
    )
    order = assessment.work_order
    store, execution, usage = _stores(tmp_path / "state")
    opened = open_job(store, assessment, on=DAY)

    first = prepare_developer_session(store, execution, order, opened.job, config, on=DAY)
    assert developer_briefing_payload(first)["efficiency"]["model_tier"] == "standard"

    developed = ingest_developer_result(
        store, execution, usage, order, first.job, config,
        _receipt(first.packet), on=DAY,
    )
    review_briefing = prepare_review_session(
        store, execution, order, developed.job, config,
        implementer=first.employee, on=DAY,
    )
    reviewed = record_review(
        store, execution, order, review_briefing.job, config,
        _attestation(
            order, first.packet, developed.receipt,
            review_id="rev-000", verdict=ReviewOutcome.CHANGES_REQUIRED,
        ),
        first.packet, developed.receipt,
        implementer=first.employee, repo_root=repo, on=DAY,
    )
    assert reviewed.job.state is JobState.PLANNING

    second = prepare_developer_session(store, execution, order, reviewed.job, config, on=DAY)
    payload = developer_briefing_payload(second)
    assert payload["efficiency"]["packet_attempt"] == 2
    assert payload["efficiency"]["model_tier"] == "strongest"
    assert payload["efficiency"]["escalation"] == "cheaper_capable_model_failed"



# --- 18. real context narrowing -----------------------------------------


def test_context_refs_are_narrowed_against_the_real_repository_path(tmp_path):
    """The reference/path bug, fixed where it can be seen.

    `ContextRef.key` is `"<kind>:<ref>"`. Comparing that against an authorized
    path never matches, so the old filter dropped everything and the briefing
    reported a reduction it had not performed. Narrowing now resolves each
    reference to the repository path it actually stands for.
    """
    inside = ContextRef(
        kind=ContextKind.TEST,
        ref="tests/test_company_engineering_execution.py",
        reason="declared test of the owning capsule",
    )
    outside = ContextRef(
        kind=ContextKind.TEST,
        ref="tests/test_arena_layout.py",
        reason="a test belonging to another subsystem entirely",
    )
    scope = ("company/engineering", "tests/test_company_engineering_execution.py")

    result = narrow_context_refs((inside, outside), scope)
    assert inside in result.kept
    assert outside in result.dropped
    assert result.dropped_reasons

    # The exact failure being prevented: the key form matches nothing.
    assert not any(
        key.startswith(path)
        for key in (inside.key, outside.key)
        for path in scope
    )


def test_a_capsule_reference_is_narrowed_by_what_the_capsule_owns(tmp_path):
    """A module contract names an id, not a path, and is resolved through it."""
    relevant = ContextRef(
        kind=ContextKind.MODULE_CONTRACT,
        ref="capsule:company-engineering-execution",
        reason="owns the subject of this objective",
    )
    irrelevant = ContextRef(
        kind=ContextKind.MODULE_CONTRACT,
        ref="capsule:company-finance",
        reason="matched a token and owns nothing here",
    )
    owned = {
        "company-engineering-execution": ("company/engineering",),
        "company-finance": ("company/finance",),
    }
    result = narrow_context_refs(
        (relevant, irrelevant), ("company/engineering",), capsule_paths=owned
    )
    assert result.kept == (relevant,)
    assert result.dropped == (irrelevant,)

    # A capsule the caller supplied no paths for survives: the company cannot
    # prove a reference irrelevant with a map it does not have.
    unknown = narrow_context_refs(
        (relevant, irrelevant), ("company/engineering",), capsule_paths={}
    )
    assert len(unknown.kept) == 2


def test_narrowing_never_empties_a_packet():
    stray = ContextRef(
        kind=ContextKind.FILE, ref="sloped/cameras.py", reason="unrelated"
    )
    result = narrow_context_refs((stray,), ("company/engineering",), floor=1)
    assert result.kept == (stray,)
    assert result.dropped == ()


def test_the_packet_the_session_receives_is_the_narrowed_one(tmp_path):
    """Not a calculated field beside a wider packet: the same set, everywhere.

    The work order, the packet, the briefing and the strategy artifact all
    report one reference list, because narrowing happens once, at intake.
    """
    repo = _fake_repo(tmp_path)
    config = _config()
    assessment = assess_request(
        _request(), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    order = assessment.work_order
    store, execution, usage = _stores(tmp_path / "state")
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(store, execution, order, opened.job, config, on=DAY)
    payload = developer_briefing_payload(briefing)

    order_keys = [ref.key for ref in order.context_refs]
    packet_keys = [ref.key for ref in briefing.packet.context_refs]

    # The work order's narrowed references are the packet's explicit ones.
    # Order is the manifest's group order - contracts, then tests - not the
    # order they were supplied in, so this is a subset check by identity.
    assert set(order_keys) <= set(packet_keys)
    assert payload["work_order"]["context_refs"] == order_keys
    assert payload["efficiency"]["context"]["refs"] == packet_keys
    assert payload["efficiency"]["context"]["work_order_refs"] == order_keys
    assert len(packet_keys) <= CONSUMER.context_ref_ceiling

    # And there is no second, wider set anywhere in the briefing.
    assert "context_refs_scoped" not in payload

    assert assessment.derivation.context_refs_kept == len(order_keys)
    assert assessment.derivation.context_refs_considered >= len(order_keys)


def test_the_profile_ceiling_bounds_automatic_context():
    """Most of a routine packet is automatic capsules, not what the order asked for.

    The work order supplied two references and the assembler returned seven:
    five were capsules it selected itself, following the capsule graph's
    dependencies until the reasoning class's ceiling was reached. That is
    where a routine job's context actually comes from, and it is what the
    profile ceiling now bounds - below the class ceiling, and only ever the
    automatic half.
    """
    from company.runtime.context_assembly import ContextAssemblyPolicy, assemble_context
    from ai_platform.resource_classes import TaskSignals, classify
    from company.runtime.specification import ContextRequirements, TaskSpecification

    explicit = ContextRef(
        kind=ContextKind.MODULE_CONTRACT,
        ref="capsule:company-engineering-execution",
        reason="owns the subject",
    )
    spec = TaskSpecification(
        task_id="wo-ceiling",
        objective="Add a field to the engineering result record.",
        required_capabilities=("software_implementation",),
        requires_judgment=True,
        context=ContextRequirements(
            refs=(explicit,),
            acceptance_criteria=("the field is present and rendered",),
        ),
    )
    classification = classify(TaskSignals(requires_judgment=True))
    assert classification.code is ReasoningClass.C
    class_ceiling = classification.resource_class.max_context_refs

    index = _index()
    unbounded = assemble_context(spec, classification, capsule_index=index)
    bounded = assemble_context(
        spec,
        classification,
        capsule_index=index,
        policy=ContextAssemblyPolicy(automatic_ref_ceiling=2),
    )

    assert len(bounded.manifest.refs()) == 2
    assert len(bounded.manifest.refs()) < len(unbounded.manifest.refs())
    assert bounded.plan.manifest_size_chars < unbounded.plan.manifest_size_chars
    assert 2 < class_ceiling, "the cap must be the smaller of the two to prove anything"

    rejected = bounded.plan.capsule_refs_rejected
    assert any(item.stage == "resource_ceiling" for item in rejected)
    assert any("caller ceiling" in item.reason for item in rejected)

    # The explicit reference survives whatever the ceiling says. A reference
    # the work order named is authoritative; dropping it to save money is how
    # a session ends up rediscovering its own subject.
    assert explicit.key in bounded.manifest.keys()


def test_an_explicit_reference_is_never_dropped_by_a_profile_ceiling():
    from company.runtime.context_assembly import ContextAssemblyPolicy, assemble_context
    from ai_platform.resource_classes import TaskSignals, classify
    from company.runtime.specification import ContextRequirements, TaskSpecification

    refs = (
        ContextRef(
            kind=ContextKind.MODULE_CONTRACT,
            ref="capsule:company-engineering-execution",
            reason="owns the subject",
        ),
        ContextRef(
            kind=ContextKind.TEST,
            ref="tests/test_company_engineering_execution.py",
            reason="declared test",
        ),
        ContextRef(
            kind=ContextKind.FILE,
            ref="company/engineering/result.py",
            reason="the file being changed",
        ),
    )
    spec = TaskSpecification(
        task_id="wo-explicit",
        objective="Add a field to the engineering result record.",
        required_capabilities=("software_implementation",),
        requires_judgment=True,
        context=ContextRequirements(
            refs=refs, acceptance_criteria=("the field is rendered",)
        ),
    )
    classification = classify(TaskSignals(requires_judgment=True))
    assembled = assemble_context(
        spec,
        classification,
        capsule_index=_index(),
        policy=ContextAssemblyPolicy(automatic_ref_ceiling=1),
    )
    for ref in refs:
        assert ref.key in assembled.manifest.keys()


# --- 19. the routing derivation is deterministic and readable -------------


def test_routing_is_a_pure_function_of_the_request():
    request = _request()
    assert derive_routing(request) == derive_routing(request)


def test_every_specialist_trigger_routes_to_its_own_domain():
    for domain, terms in SPECIALIST_TRIGGERS.items():
        for term in terms:
            routed = derive_routing(
                _request(objective=f"Please handle the {term} problem in the loop.")
            )
            assert routed.specialist_domain == domain, (term, routed)


# --- 13a. routing precision: a bare "governance" noun is not governance work --


def test_a_harmless_governance_mention_stays_routine():
    """Naming the noun "governance" is not the same as doing governance work.

    Regression for the V3A false positive: `intake.py` used to trigger the
    governance specialist on the bare substring "governance" anywhere in the
    objective, so a page that merely *displays* governance activity routed to
    the strongest tier. The fix narrows the trigger table to specific
    governance actions (`approval boundary`, `permissions policy`, ...).
    """
    routed = derive_routing(
        _request(objective="Show governance activity on the CEO page.")
    )
    assert routed.specialist_domain == ""
    assert "routine implementation" in routed.reason, routed.reason


@pytest.mark.parametrize(
    "objective",
    [
        "Display governance events alongside attempts.",
        "Document the governance result.",
    ],
)
def test_other_harmless_governance_mentions_stay_routine(objective):
    routed = derive_routing(_request(objective=objective))
    assert routed.specialist_domain == "", (objective, routed)


def test_governance_mention_in_notes_does_not_route():
    """`notes` is explanatory metadata, not requested work.

    A note explaining a *past* misclassification must not retrigger it: notes
    are never consulted for routing, only `objective` and the explicit fields
    (`specialist_domain`, `escalate_reasoning`, `risk`, `reversible`).
    """
    routed = derive_routing(
        _routine_request(
            notes=(
                "The previous request was incorrectly classified as governance "
                "work and escalated to the strongest tier by mistake."
            )
        )
    )
    assert routed.specialist_domain == "", routed
    assert "routine implementation" in routed.reason, routed.reason


@pytest.mark.parametrize(
    "objective",
    [
        "Modify the approval boundary so a second reviewer is required.",
        "Change the permissions policy for reserved actions.",
        "Amend the constitution's rule about subagents.",
        "Change separation of duties between developer and reviewer roles.",
        "Change protected policy so the gate file cannot be hand-edited.",
        "Change the governance rules for who can approve a merge.",
    ],
)
def test_genuine_governance_actions_still_route_to_specialist(objective):
    routed = derive_routing(_request(objective=objective))
    assert routed.specialist_domain == "governance", (objective, routed)
    assert "which is governance work" in routed.reason, routed.reason


def test_explicit_specialist_domain_is_authoritative_over_text():
    """The CEO-named domain wins even when the objective text is routine."""
    routed = derive_routing(
        _routine_request(specialist_domain="governance")
    )
    assert routed.specialist_domain == "governance"
    assert "named the specialist domain" in routed.reason


def test_explicit_escalation_routes_without_needing_trigger_text():
    routed = derive_routing(_routine_request(escalate_reasoning=True))
    assert routed.specialist_domain == "explicit_escalation"
    assert routed.escalation is EscalationReason.EXPLICIT
    assert "explicitly escalated" in routed.reason


@pytest.mark.parametrize("risk", [Risk.HIGH, Risk.CRITICAL])
def test_high_or_critical_risk_still_routes_to_specialist_depth(risk):
    """Bounded routine text must not suppress genuine risk-based escalation."""
    routed = derive_routing(_routine_request(risk=risk))
    assert routed.specialist_domain == "high_risk_change", routed
    assert risk.value in routed.reason


def test_an_irreversible_request_raises_its_own_ceiling():
    """Deep reasoning needs a ceiling that permits it, or the job is refused.

    `requires_judgment` is True for every engineering task, so an irreversible
    one classifies E. A hard-coded D ceiling would make `plan_task` refuse the
    work order rather than downgrade it - the right refusal, discovered at the
    wrong moment.
    """
    routed = derive_routing(_request(reversible=False))
    assert routed.reasoning_class_ceiling is ReasoningClass.E
    assert derive_routing(_request()).reasoning_class_ceiling is ReasoningClass.D


# --- 13b. routine-eligibility guard: breaking migration/schema/storage-format/
#          wire-protocol work is not routine, whatever else the objective says --


@pytest.mark.parametrize(
    "objective",
    [
        "Document the current schema.",
        "Display protocol status on the CEO page.",
        "Add tests for the existing serialization format.",
        "Show migration status on a dashboard.",
        "Add schema information to a report.",
        "Rename a field in documentation.",
    ],
)
def test_harmless_schema_protocol_format_mentions_stay_routine(objective):
    """Naming schema/protocol/migration/format in passing is not breaking work.

    Regression for the operational-readiness gap: the old table matched bare
    "migrate"/"migration", so a dashboard that merely *displays* migration
    status routed to the strongest tier. The fix pairs each noun with what
    makes it breaking, so a routine mention stays routine.
    """
    routed = derive_routing(_request(objective=objective))
    assert routed.specialist_domain == "", (objective, routed)
    assert "routine implementation" in routed.reason, routed.reason


def test_routine_objective_with_breaking_change_mentioned_only_in_notes_stays_routine():
    """`notes` never influences routing - not even breaking-change wording.

    Same guarantee `[[company-os-read-efficiency-v3a-stop-condition]]` pinned
    for "governance", extended to the new breaking-change phrases: a note that
    explains a *past* schema migration must not retrigger specialist routing.
    """
    routed = derive_routing(
        _routine_request(
            notes=(
                "This follows up on the database migration that made a "
                "backward-incompatible schema change last quarter."
            )
        )
    )
    assert routed.specialist_domain == "", routed
    assert "routine implementation" in routed.reason, routed.reason


@pytest.mark.parametrize(
    "objective",
    [
        "Migrate the database schema to an incompatible layout.",
        "Make a breaking schema change.",
        "Change the wire protocol in a backward-incompatible way.",
        "Migrate the persisted storage format.",
        "Replace the serialization format used for stored records.",
        "Introduce a backward-incompatible API contract.",
    ],
)
def test_breaking_migration_schema_protocol_changes_route_to_architecture(objective):
    routed = derive_routing(_request(objective=objective))
    assert routed.specialist_domain == "architecture", (objective, routed)
    assert "which is architecture work" in routed.reason, routed.reason


@pytest.mark.parametrize(
    "objective",
    [
        "Modify the approval boundary so a second reviewer is required.",
        "Refactor the authentication flow.",
        "Fix a race condition in the developer lock.",
        "Rewrite the intake matching engine.",
    ],
)
def test_other_specialist_domains_are_unaffected_by_the_breaking_change_table(objective):
    """Security, governance, concurrency and the rest of architecture still route.

    The breaking-change additions live inside the architecture trigger table
    alongside the pre-existing terms, so this pins that none of the other
    domains, or architecture's own older triggers, lost coverage.
    """
    routed = derive_routing(_request(objective=objective))
    assert routed.specialist_domain != "", (objective, routed)


def test_explicit_specialist_domain_still_wins_over_a_breaking_change_objective():
    routed = derive_routing(
        _request(
            objective="Migrate the database schema to an incompatible layout.",
            specialist_domain="governance",
        )
    )
    assert routed.specialist_domain == "governance"
    assert "named the specialist domain" in routed.reason


def test_explicit_escalation_still_wins_over_a_routine_looking_objective():
    routed = derive_routing(_routine_request(escalate_reasoning=True))
    assert routed.specialist_domain == "explicit_escalation"


@pytest.mark.parametrize("risk", [Risk.HIGH, Risk.CRITICAL])
def test_high_or_critical_risk_routing_is_unaffected_by_the_breaking_change_table(risk):
    routed = derive_routing(_routine_request(risk=risk))
    assert routed.specialist_domain == "high_risk_change", routed


def test_state_c_routine_eligibility_requires_no_breaking_change_trigger():
    """State C (routine autonomous engineering) reads eligibility from one place.

    A request that satisfies every other routine condition - LOW risk,
    reversible, no reserved action, no credential, no explicit escalation or
    domain - still lands on reasoning class D, not the routine floor C, the
    moment its objective describes a breaking migration/schema/storage-format/
    protocol change. This is `classify()` in `ai_platform.resource_classes`
    acting on `derive_routing`'s own `specialist_domain` output: one engine,
    not a second eligibility check bolted on beside it.
    """
    from ai_platform.resource_classes import TaskSignals, classify

    routine = derive_routing(_routine_request())
    routine_classification = classify(
        TaskSignals(
            requires_judgment=True,
            specialist_domain=routine.specialist_domain,
            risk=Risk.LOW,
            reversible=True,
        )
    )
    assert routine_classification.code is ReasoningClass.C
    assert routine_classification.rule == "small_reasoning_floor"

    breaking = derive_routing(
        _request(objective="Migrate the persisted storage format.")
    )
    breaking_classification = classify(
        TaskSignals(
            requires_judgment=True,
            specialist_domain=breaking.specialist_domain,
            risk=Risk.LOW,
            reversible=True,
        )
    )
    assert breaking_classification.code is ReasoningClass.D
    assert breaking_classification.rule == "specialist_reasoning"


def test_every_stage_plans_under_the_same_context_policy(tmp_path):
    """The defect a live run found and no test had.

    `ManualExternalSessionAdapter.ingest` re-plans the task and compares the
    resulting context fingerprint with the packet's. The brief stage narrowed
    context by the resource profile and the receipt stage did not, so the two
    plans assembled different manifests and every real receipt was refused:
    `context b2655e65 against packet 491e6522`. The work was done, committed
    and pushed, and the lifecycle would not accept it.
    """
    repo = _fake_repo(tmp_path)
    config = _config()
    assessment = assess_request(
        _routine_request(), config.permissions, repo_root=repo,
        capsule_index=_index(), work_order_id="wo-req-001",
    )
    order = assessment.work_order
    store, execution, usage = _stores(tmp_path / "state")
    opened = open_job(store, assessment, on=DAY)
    briefing = prepare_developer_session(store, execution, order, opened.job, config, on=DAY)

    # The packet carries the narrowed context.
    assert len(briefing.packet.context_refs) == len(order.context_refs)

    # A plan built without the policy would assemble a wider manifest and a
    # different fingerprint - which is exactly what made the receipt fail.
    from company.engineering.orchestrator import _context_policy
    from company.runtime.lifecycle import plan_task

    contract = order.employee_contract(config, briefing.employee)
    unpoliced = plan_task(order.task_specification(), config, employee_contract=contract)
    assert unpoliced.preparation.context_fingerprint != briefing.packet.context_fingerprint
    policed = plan_task(
        order.task_specification(), config, employee_contract=contract,
        context_policy=_context_policy(order),
    )
    assert policed.preparation.context_fingerprint == briefing.packet.context_fingerprint

    # And the real ingestion path agrees, end to end.
    developed = ingest_developer_result(
        store, execution, usage, order, briefing.job, config,
        _receipt(briefing.packet), on=DAY,
    )
    assert developed.job.state is JobState.TESTING


def test_no_engineering_stage_plans_without_a_context_policy():
    """A source guard, because the behavioural one only covers the paths it walks.

    Every `plan_task` call in this subsystem must pass `context_policy`. One
    that does not assembles context under different rules from the packet it
    is being compared against, and the failure surfaces as a refused receipt
    two stages later, after a session has already been paid for.
    """
    source = (ROOT / "company" / "engineering" / "orchestrator.py").read_text(
        encoding="utf-8"
    )
    tree = ast.parse(source)
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "plan_task"
    ]
    assert calls, "the guard is watching a function nobody calls"
    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords}
        assert "context_policy" in keywords, (
            f"plan_task at line {call.lineno} plans without a context policy"
        )

