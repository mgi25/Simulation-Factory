"""P6C: the experience store - episodes, identity, capture, provenance, validity.

Every capture test drives a real engineering job through the real orchestrator
(`open_job` ... `record_decision`), so the episodes it indexes are built from
the canonical records the loop genuinely writes, not from hand-made JSON.
Retrieval, abstention and the authority invariant are in
`tests/test_company_experience_retrieval.py`.
"""

from __future__ import annotations

import ast
import datetime as dt
from dataclasses import replace
import inspect
import json
from pathlib import Path
import shutil

import pytest

from ai_platform.serde import dumps, to_jsonable
from ai_platform.usage import Outcome
from company.engineering import (
    DEFAULT_PROTECTED_PATHS,
    CEODecision,
    CEORequest,
    CEOVerdict,
    CriterionFinding,
    EngineeringStore,
    GateReadiness,
    GateVerdict,
    IntakeOutcome,
    JobState,
    ReviewOutcome,
    ReviewerAttestation,
    assess_request,
    ingest_developer_result,
    open_job,
    prepare_developer_session,
    prepare_review_session,
    record_decision,
    record_execution_stop,
    record_gate,
    record_review,
)
from company.experience import (
    DECISION_TIME_FIELDS,
    OUTCOME_FIELDS,
    CaptureRefused,
    EvidenceBasis,
    ExperienceConflict,
    GovernanceFacts,
    ExperienceEpisode,
    ExperienceError,
    ExperienceStore,
    Measurement,
    PrecedentClass,
    RepositoryView,
    ResourceObservation,
    Validity,
    assert_decision_time_only,
    attempt_cycles,
    build_episode,
    capture_settled,
    contract_digest,
    decision_features,
    evaluate_validity,
    governance_facts,
    governed_class,
    training_row,
    verify_features,
    verify_pointers,
)
from company.experience import __main__ as experience_cli
from company.experience.repository import capture_provenance, covers
from company.integration.policy import DEFAULT_POLICY
from company.runtime import (
    ExecutionStore,
    ExecutorHint,
    ReceiptUsage,
    ReportedTest,
    ResourceUsageStore,
    SessionReceipt,
    load_company_config,
)
from knowledge.company_os.capsules import CapsuleIndex
from knowledge.company_os.records import RecordStatus


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "company" / "experience"
SEEDS = ROOT / "knowledge" / "company_os" / "capsules" / "seeds"
DAY = dt.date(2026, 9, 18)
LATER = dt.date(2026, 9, 20)
SHA = "a" * 40
CHANGED = "company/engineering/verify.py"


# --- a real engineering job, driven through the real orchestrator --------------


def _config():
    return load_company_config(ROOT / "company")


def _index() -> CapsuleIndex:
    return CapsuleIndex.load(SEEDS)


def _fake_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in DEFAULT_PROTECTED_PATHS:
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# original {relative}\n", encoding="utf-8")
    (root / "company" / "engineering").mkdir(parents=True, exist_ok=True)
    (root / "company" / "engineering" / "seed.py").write_text("def seed():\n    return 1\n", encoding="utf-8")
    (root / CHANGED).write_text("def verify():\n    return True\n", encoding="utf-8")
    (root / "tests").mkdir(parents=True, exist_ok=True)
    (root / "tests" / "test_company_engineering_execution.py").write_text(
        "def test_seed():\n    assert True\n", encoding="utf-8"
    )
    return root


def _request(**changes) -> CEORequest:
    values = {
        "request_id": "req-exp-001",
        "objective": (
            "Give me a way to check whether the protected governance files have "
            "changed since an engineering work order was authorized."
        ),
        "requested_by": "MGI",
        "requested_on": DAY,
        "subsystem_hint": "company/engineering",
        "authorized_branch": "eng-exp-001",
    }
    values.update(changes)
    return CEORequest(**values)


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
        "files_changed": (CHANGED,),
        "tests": tuple(ReportedTest(command=c, passed=True, summary="ok") for c in packet.required_tests),
        "evidence": (CHANGED,),
        "usage": ReceiptUsage(passes=1),
        "executor": ExecutorHint.CLAUDE_CODE,
    }
    values.update(changes)
    return SessionReceipt(**values)


def _gate_report(readiness: GateReadiness) -> dict:
    required = sorted(DEFAULT_POLICY.required)
    status = {GateReadiness.READY: "pass", GateReadiness.BLOCKED: "fail"}[readiness]
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
    blockers = [] if readiness is GateReadiness.READY else [
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
        "source": {"repo_root": "repo", "source_commit": SHA, "source_branch": "eng-exp-001"},
        "sections": [{"category": "architecture", "checks": checks}],
    }


class Flow:
    """One engineering job, moved stage by stage the way the runner moves it."""

    def __init__(self, tmp_path: Path, *, work_order_id: str = "wo-exp-001", **request_changes) -> None:
        self.repo = _fake_repo(tmp_path)
        self.state = tmp_path / "state"
        self.config = _config()
        assessment = assess_request(
            _request(**request_changes),
            self.config.permissions,
            repo_root=self.repo,
            capsule_index=_index(),
            work_order_id=work_order_id,
        )
        assert assessment.outcome is IntakeOutcome.AUTHORIZED, assessment.decisions
        self.store = EngineeringStore(self.state)
        self.execution = ExecutionStore(self.state)
        self.usage = ResourceUsageStore(self.state)
        opened = open_job(self.store, assessment, on=DAY)
        self.order = opened.work_order
        self.job = opened.job
        self.reviews = 0
        # A real checkout holds every suite the work order requires.
        for test in self.order.required_tests:
            target = self.repo / test
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")

    def brief(self, *, on: dt.date = DAY):
        briefing = prepare_developer_session(self.store, self.execution, self.order, self.job, self.config, on=on)
        self.packet, self.employee, self.job = briefing.packet, briefing.employee, briefing.job
        return briefing

    def develop(self, *, on: dt.date = DAY, **receipt_changes):
        self.brief(on=on)
        return self.submit(on=on, **receipt_changes)

    def submit(self, *, on: dt.date = DAY, **receipt_changes):
        developed = ingest_developer_result(
            self.store, self.execution, self.usage, self.order, self.job, self.config,
            _receipt(self.packet, **receipt_changes), on=on,
        )
        self.receipt = developed.receipt
        if developed.job_pointer is not None:
            self.job = developed.job
        return developed

    def review(self, verdict: ReviewOutcome = ReviewOutcome.PASS, *, on: dt.date = DAY, **changes):
        self.reviews += 1
        briefing = prepare_review_session(
            self.store, self.execution, self.order, self.job, self.config, implementer=self.employee, on=on
        )
        values = {
            "review_id": f"rev-{self.reviews:03d}",
            "work_order_id": self.order.work_order_id,
            "work_order_fingerprint": self.order.fingerprint(),
            "reviewer": "software_review_engineer",
            "packet_fingerprint": self.packet.fingerprint(),
            "receipt_fingerprint": self.receipt.fingerprint(),
            "verdict": verdict,
            "reviewed_on": on,
            "criteria": tuple(
                CriterionFinding(criterion=item, satisfied=True, evidence_ref=CHANGED)
                for item in self.order.acceptance_criteria
            ),
            "evidence": (CHANGED,),
            "changed_paths_reviewed": self.receipt.files_changed,
        }
        values.update(changes)
        reviewed = record_review(
            self.store, self.execution, self.order, briefing.job, self.config,
            ReviewerAttestation(**values), self.packet, self.receipt,
            implementer=self.employee, repo_root=self.repo, on=on,
        )
        self.job = reviewed.job
        return reviewed

    def gate(self, readiness: GateReadiness = GateReadiness.READY, *, on: dt.date = DAY):
        verdict = GateVerdict.from_report_mapping(
            _gate_report(readiness), work_order_id=self.order.work_order_id, report_digest="0" * 16
        )
        self.job, _gp, _jp = record_gate(
            self.store, self.order, self.job, verdict, on=on, implementation_commit=self.receipt.commit_sha
        )

    def decide(self, verdict: CEOVerdict, *, on: dt.date = LATER, rationale: str = "Decided by the CEO."):
        decision = CEODecision(
            decision_id=f"dec-{verdict.value}",
            work_order_id=self.order.work_order_id,
            work_order_fingerprint=self.order.fingerprint(),
            verdict=verdict,
            decided_by="MGI",
            decided_on=on,
            rationale=rationale,
            reviewed_state=self.job.state,
            required_changes=("do it differently",) if verdict is not CEOVerdict.APPROVE else (),
        )
        self.job, _dp, _jp = record_decision(self.store, self.order, self.job, decision)

    def stop(self, reason: str = "the provider session stopped", *, on: dt.date = DAY):
        self.job, _pointer = record_execution_stop(self.store, self.order, self.job, reason=reason, on=on)

    def view(self, **changes) -> RepositoryView:
        return RepositoryView(repo_root=self.repo, capsules=changes.get("capsules", _index()))


def _accepted(tmp_path: Path, **kwargs) -> Flow:
    flow = Flow(tmp_path, **kwargs)
    flow.develop()
    flow.review(ReviewOutcome.PASS)
    flow.gate(GateReadiness.READY)
    assert flow.job.state is JobState.READY_FOR_APPROVAL
    return flow


def _capture(flow: Flow, **kwargs):
    return capture_settled(flow.state, flow.view(), captured_on=LATER, **kwargs)


def _only(flow: Flow, **kwargs) -> ExperienceEpisode:
    report = _capture(flow, **kwargs)
    assert len(report.captured) == 1, report.to_dict()
    return ExperienceStore(flow.state).get(report.captured[0].experience_id)


# --- capture: the eight cases the brief names ----------------------------------


def test_an_accepted_one_attempt_task_is_one_accepted_episode(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    assert episode.engineering_class() is PrecedentClass.ACCEPTED
    assert episode.work_order_id == "wo-exp-001"
    assert episode.packet_attempt == 1
    assert episode.outcome.files_changed == (CHANGED,)
    assert episode.outcome.review_outcome == "pass"
    assert episode.outcome.gate_readiness == "ready"
    assert episode.outcome.settled_state == "ready_for_approval"
    assert episode.outcome.recorded_outcome == "accepted"
    roles = {p.role for p in episode.evidence}
    assert {"work_order", "packet", "authority", "receipt", "usage", "review", "attestation", "gate_verdict", "job"} <= roles
    assert verify_pointers(episode, flow.state) == ()
    assert episode.decided_on == DAY and episode.settled_on == DAY


def test_an_accepted_task_after_a_correction_is_two_episodes_of_two_classes(tmp_path):
    flow = Flow(tmp_path, resource_profile="expanded")
    flow.develop()
    flow.review(ReviewOutcome.CHANGES_REQUIRED)
    assert flow.job.state is JobState.PLANNING
    flow.develop(on=LATER)
    flow.review(ReviewOutcome.PASS, on=LATER)
    flow.gate(on=LATER)
    report = _capture(flow)
    classes = {r.packet_attempt: r.precedent_class for r in report.captured}
    assert classes == {1: "correction", 2: "accepted"}
    ids = {r.experience_id for r in report.captured}
    assert len(ids) == 2, "two genuinely different attempts must stay two episodes"
    store = ExperienceStore(flow.state)
    first, second = sorted((store.get(i) for i in ids), key=lambda e: e.packet_attempt)
    assert first.settled_on == DAY and first.outcome.settled_state == "planning"
    assert second.decided_on == LATER and second.features.attempt == 2


def test_a_rejected_attempt_is_a_correction_and_never_accepted(tmp_path):
    flow = Flow(tmp_path)
    flow.develop()
    flow.review(ReviewOutcome.CHANGES_REQUIRED)
    assert flow.job.state is JobState.DECISION_REQUIRED
    episode = _only(flow)
    assert episode.engineering_class() is PrecedentClass.CORRECTION
    assert episode.outcome.review_outcome == "changes_required"


def test_a_blocked_gate_makes_the_attempt_a_correction(tmp_path):
    flow = Flow(tmp_path)
    flow.develop()
    flow.review(ReviewOutcome.PASS)
    flow.gate(GateReadiness.BLOCKED)
    episode = _only(flow)
    assert episode.outcome.gate_readiness == "blocked"
    assert episode.engineering_class() is PrecedentClass.CORRECTION


def test_an_incomplete_task_is_refused_until_it_settles(tmp_path):
    flow = Flow(tmp_path)
    flow.develop()
    assert flow.job.state is JobState.TESTING
    report = _capture(flow)
    assert report.captured == ()
    assert [(r.code, r.packet_attempt) for r in report.refused] == [("not_settled", 1)]


def test_a_stopped_session_settles_as_incomplete_history(tmp_path):
    flow = Flow(tmp_path)
    flow.brief()
    flow.stop()
    assert flow.job.state is JobState.DECISION_REQUIRED
    episode = _only(flow)
    assert episode.outcome.receipt_outcome == ""
    assert episode.receipt_fingerprint == ""
    assert episode.engineering_class() is PrecedentClass.INCOMPLETE


def test_missing_usage_telemetry_stays_unavailable_and_never_becomes_zero(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    resources = episode.resources
    assert resources.tokens_basis is EvidenceBasis.UNAVAILABLE
    assert resources.tokens_total is None and resources.tokens_input is None
    assert resources.cost_basis is EvidenceBasis.UNAVAILABLE and resources.cost_amount is None
    assert resources.duration_s is None and resources.duration_basis is EvidenceBasis.UNAVAILABLE
    assert resources.estimated_tokens_total is not None  # an estimate, labelled as one
    row = training_row(episode)
    assert row["basis"]["tokens"] == "unavailable"


def test_missing_optional_provider_fields_are_none_not_empty(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    assert episode.resources.provider is None
    assert episode.resources.model is None


def test_reported_provider_usage_is_observed_with_its_values(tmp_path):
    flow = Flow(tmp_path)
    from ai_platform.usage import UsageUnit

    flow.develop(
        usage=ReceiptUsage(
            passes=1, input_units=120, output_units=30, usage_unit=UsageUnit.TOKEN,
            duration_s=12.5, provider="anthropic", model="sonnet",
        )
    )
    flow.review(ReviewOutcome.PASS)
    flow.gate()
    resources = _only(flow).resources
    assert resources.tokens_basis is EvidenceBasis.OBSERVED
    assert (resources.tokens_input, resources.tokens_output, resources.tokens_total) == (120, 30, 150)
    assert resources.duration_s == 12.5 and resources.duration_basis is EvidenceBasis.OBSERVED
    assert (resources.provider, resources.model) == ("anthropic", "sonnet")


def test_missing_efficiency_telemetry_is_noted_not_invented(tmp_path):
    flow = _accepted(tmp_path)
    shutil.rmtree(flow.state / "execution" / "efficiency")
    episode = _only(flow)
    assert episode.pointer("efficiency") is None
    assert any("no efficiency record" in note for note in episode.notes)
    assert episode.resources.tokens_basis is EvidenceBasis.UNAVAILABLE
    assert episode.resources.estimated_tokens_total is None


def test_duplicate_ingestion_resolves_to_the_same_identity(tmp_path):
    flow = _accepted(tmp_path)
    first = _capture(flow)
    second = capture_settled(flow.state, flow.view(), captured_on=dt.date(2026, 9, 30))
    assert [r.experience_id for r in first.captured] == [r.experience_id for r in second.captured]
    assert [r.created for r in first.captured] == [True]
    assert [r.created for r in second.captured] == [False]
    files = list((flow.state / "experience" / "episodes").rglob("*.json"))
    assert len(files) == 1, "an idempotent re-capture writes nothing"
    stored = ExperienceStore(flow.state).episodes()[0]
    assert stored.provenance.captured_on == LATER, "the first capture is kept, never overwritten"


def test_a_conflicting_duplicate_is_refused_and_the_stored_episode_kept(tmp_path):
    flow = _accepted(tmp_path)
    original = _only(flow)
    before = {p: p.read_bytes() for p in (flow.state / "experience").rglob("*.json")}
    review_ref = original.pointer("review").record_ref
    path = flow.state / review_ref
    data = json.loads(path.read_text(encoding="utf-8"))
    data["unanswered_criteria"] = ["a criterion nobody answered"]
    path.write_text(json.dumps(data), encoding="utf-8")
    report = _capture(flow)
    assert [r.code for r in report.refused] == ["conflict"]
    assert "outcome" in report.refused[0].detail
    after = {p: p.read_bytes() for p in (flow.state / "experience").rglob("*.json")}
    assert after == before, "a refused conflict writes nothing"
    assert ExperienceStore(flow.state).get(original.experience_id) == original
    problems = verify_pointers(original, flow.state)
    assert len(problems) == 1 and problems[0].startswith(f"review {review_ref} changed")


def test_an_undecodable_work_order_is_refused_not_repaired(tmp_path):
    flow = _accepted(tmp_path)
    [ref] = [p for p in (flow.state / "engineering" / "work_orders").rglob("*.json")]
    data = json.loads(ref.read_text(encoding="utf-8"))
    data["max_developer_attempts"] = 3  # the historical pre-profile shape
    ref.write_text(json.dumps(data), encoding="utf-8")
    report = _capture(flow)
    assert report.captured == ()
    assert [r.code for r in report.refused] == ["work_order_undecodable"]


def test_capture_follows_the_jobs_own_links_not_positions(tmp_path):
    """An evidence-format rejection adds a receipt and a usage record that did
    not move the job; capture must pair the settling receipt with *its* usage
    record, which a positional join gets wrong."""
    flow = Flow(tmp_path)
    flow.brief()
    rejected = flow.submit(tests=())  # no required test reported: a format-only refusal
    assert rejected.evidence_rejected and flow.job.state is JobState.DEVELOPING
    flow.submit()
    flow.review(ReviewOutcome.PASS)
    flow.gate()
    episode = _only(flow)
    assert episode.outcome.evidence_format_rejections == 1
    assert episode.pointer("receipt").record_ref.endswith("000002.json")
    assert episode.pointer("usage").record_ref.endswith("000002.json")
    [cycle] = attempt_cycles(flow.job)
    assert cycle.receipt_ref.endswith("000002.json") and cycle.usage_ref.endswith("000002.json")


# --- identity and the store ----------------------------------------------------


def test_the_identity_is_derived_from_canonical_pointers_only(tmp_path):
    episode = _only(_accepted(tmp_path))
    assert set(episode.identity()) == {
        "schema", "work_order_id", "work_order_fingerprint", "packet_fingerprint", "packet_attempt", "receipt_fingerprint",
    }
    moved = replace(episode, provenance=replace(episode.provenance, captured_on=dt.date(2027, 1, 1)), source="elsewhere", experience_id="")
    assert moved.experience_id == episode.experience_id
    assert moved.content_fingerprint() == episode.content_fingerprint()
    other = replace(episode, packet_attempt=2, features=replace(episode.features, attempt=2), experience_id="")
    assert other.experience_id != episode.experience_id


def test_a_stored_id_that_disagrees_with_its_content_is_refused(tmp_path):
    episode = _only(_accepted(tmp_path))
    data = episode.to_dict()
    data["experience_id"] = "0" * 16
    with pytest.raises(ExperienceError, match="does not match"):
        ExperienceEpisode.from_mapping(data)
    data = episode.to_dict()
    data["approved"] = True
    with pytest.raises(ExperienceError, match="unknown field"):
        ExperienceEpisode.from_mapping(data)


def test_the_store_is_append_only_with_no_update_or_delete(tmp_path):
    public = {name for name in dir(ExperienceStore) if not name.startswith("_")}
    assert public == {"episodes", "get", "put", "scan"}
    tree = ast.parse((PACKAGE / "store.py").read_text(encoding="utf-8"))
    called = {
        getattr(node.func, "attr", getattr(node.func, "id", ""))
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }
    assert not called & {"write_text", "write_bytes", "unlink", "rmtree", "remove", "rename", "replace_file"}
    assert "create_json_bytes_at_sequence" in called


def test_a_corrupt_record_costs_one_episode_and_never_the_scan(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    store = ExperienceStore(flow.state)
    junk = store.root / "junk-000000000000"
    junk.mkdir(parents=True)
    (junk / "000001.json").write_text("{not json", encoding="utf-8")
    scan = store.scan()
    assert [e.experience_id for e in scan.episodes] == [episode.experience_id]
    assert len(scan.problems) == 1 and scan.available


def test_scan_order_is_deterministic(tmp_path):
    flow = Flow(tmp_path, resource_profile="expanded")
    flow.develop()
    flow.review(ReviewOutcome.CHANGES_REQUIRED)
    flow.develop(on=LATER)
    flow.review(ReviewOutcome.PASS, on=LATER)
    flow.gate(on=LATER)
    _capture(flow)
    first = [e.experience_id for e in ExperienceStore(flow.state).episodes()]
    second = [e.experience_id for e in ExperienceStore(flow.state).episodes()]
    assert first == second and len(first) == 2
    assert [e.packet_attempt for e in ExperienceStore(flow.state).episodes()] == [1, 2]


# --- decision time and outcome ---------------------------------------------------


def test_decision_time_and_outcome_fields_are_disjoint():
    assert not DECISION_TIME_FIELDS & OUTCOME_FIELDS
    assert {"files_changed", "review_outcome", "tokens_total", "gate_readiness"} <= OUTCOME_FIELDS


def test_the_feature_builder_cannot_see_an_outcome():
    """The signature is the guard: no parameter through which an outcome could arrive."""
    parameters = list(inspect.signature(decision_features).parameters)
    assert parameters == ["order", "attempt"]
    tree = ast.parse(inspect.getsource(decision_features))
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    # Every name the body can reach: the work order, the attempt number, and
    # the local plumbing. Nothing that could hold a receipt, a review, a gate
    # verdict, a usage record or a CEO decision.
    assert names <= {"order", "attempt", "capsules", "ref", "len", "tuple", "DecisionFeatures", "CAPSULE_REF_PREFIX", "int", "Any"}, names


def test_an_outcome_smuggled_into_features_is_refused(tmp_path):
    episode = _only(_accepted(tmp_path))
    features = to_jsonable(episode.features)
    assert_decision_time_only(features)
    with pytest.raises(ExperienceError, match="outcome fields: files_changed"):
        assert_decision_time_only({**features, "files_changed": [CHANGED]})
    with pytest.raises(ExperienceError, match="not known at decision time"):
        assert_decision_time_only({**features, "was_accepted": True})


def test_stored_features_recompute_exactly_from_the_work_order(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    assert verify_features(episode, flow.order) == ()
    tampered = replace(episode, features=replace(episode.features, required_tests=("tests/test_other.py",)), experience_id="")
    assert any("required_tests" in line for line in verify_features(tampered, flow.order))


def test_features_hold_no_derived_repository_state(tmp_path):
    """Capsule ownership and the import graph are query-time signals. A feature
    computed from them at capture would carry the outcome of any attempt that
    changed them, so the only capsules in the features are the ones the work
    order itself named when it was authorized."""
    flow = _accepted(tmp_path)
    features = to_jsonable(_only(flow).features)
    named = sorted(
        ref.ref.split(":", 1)[1]
        for ref in flow.order.context_refs
        if ref.kind.value == "module_contract"
    )
    assert features["capsule_ids"] == named
    assert "governed_by" not in json.dumps(features)


def test_a_training_row_separates_inputs_from_labels_and_invents_no_model(tmp_path):
    episode = _only(_accepted(tmp_path))
    row = training_row(episode)
    assert set(row["inputs"]) == {"features"}
    assert_decision_time_only(row["inputs"]["features"])
    assert {"action", "outcome", "resources", "engineering_class"} <= set(row["labels"])
    assert row["recommendation"]["recorded"] is False
    assert "model_version" not in json.dumps(row)


# --- observed, estimated, counterfactual ---------------------------------------


def test_history_refuses_a_counterfactual_measurement():
    base = ResourceObservation.unavailable()
    with pytest.raises(ExperienceError, match="counterfactual"):
        replace(base, cost_amount="0.10", cost_basis=EvidenceBasis.COUNTERFACTUAL)
    with pytest.raises(ExperienceError, match="counterfactual"):
        replace(base, duration_s=3.0, duration_basis=EvidenceBasis.COUNTERFACTUAL)


def test_a_gap_cannot_be_written_as_a_measurement_or_a_guess_as_an_observation():
    base = ResourceObservation.unavailable()
    with pytest.raises(ExperienceError, match="never zero"):
        replace(base, duration_basis=EvidenceBasis.OBSERVED)
    with pytest.raises(ExperienceError, match="cannot carry"):
        replace(base, duration_s=0.0)
    with pytest.raises(ExperienceError, match="needs a count"):
        replace(base, tokens_basis=EvidenceBasis.OBSERVED)
    with pytest.raises(ExperienceError):
        replace(base, provider="")


def test_counterfactual_values_live_only_in_labelled_measurements():
    measurement = Measurement(["a.py"], EvidenceBasis.COUNTERFACTUAL, "what would have been offered")
    assert measurement.to_dict()["basis"] == "counterfactual"
    with pytest.raises(ExperienceError):
        Measurement(None, EvidenceBasis.OBSERVED)
    with pytest.raises(ExperienceError):
        Measurement(3, EvidenceBasis.UNAVAILABLE)


# --- governance joined at read time --------------------------------------------


def test_a_ceo_rejection_downgrades_an_accepted_episode_without_rewriting_it(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    before = (flow.state / "experience").rglob("*.json")
    snapshot = {p: p.read_bytes() for p in before}
    flow.decide(CEOVerdict.REJECT, rationale="The approach duplicates an existing check.")
    facts = governance_facts(flow.state, episode)
    klass, reasons = governed_class(episode, facts)
    assert klass is PrecedentClass.CORRECTION
    assert any("reject" in reason for reason in reasons)
    assert {p: p.read_bytes() for p in (flow.state / "experience").rglob("*.json")} == snapshot
    # As of a day before the decision, it was still an accepted precedent.
    earlier = governance_facts(flow.state, episode, before=LATER)
    assert governed_class(episode, earlier)[0] is PrecedentClass.ACCEPTED


def test_a_ceo_approval_keeps_accepted_and_never_promotes_a_correction(tmp_path):
    accepted = _accepted(tmp_path / "a")
    episode = _only(accepted)
    accepted.decide(CEOVerdict.APPROVE)
    assert governed_class(episode, governance_facts(accepted.state, episode))[0] is PrecedentClass.ACCEPTED

    # The engineering loop already refuses to approve a job that is not ready,
    # so promotion is checked where it would happen: an approval handed to
    # the join, however it arrived, does not turn a correction into precedent.
    rejected = Flow(tmp_path / "b")
    rejected.develop()
    rejected.review(ReviewOutcome.CHANGES_REQUIRED)
    correction = _only(rejected)
    approving = GovernanceFacts(available=True, verdicts=(("approve", LATER, "accept it as it is"),))
    assert governed_class(correction, approving) == (PrecedentClass.CORRECTION, ())


# --- scoped validity ---------------------------------------------------------------


def test_a_fresh_capture_is_current(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    assert evaluate_validity(episode, flow.view()).status is Validity.CURRENT


def test_an_unrelated_repository_change_does_not_invalidate_experience(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    (flow.repo / "race").mkdir()
    (flow.repo / "race" / "course.py").write_text("LENGTH = 400\n", encoding="utf-8")
    (flow.repo / "company" / "engineering" / "seed.py").write_text("def seed():\n    return 2\n", encoding="utf-8")
    assert evaluate_validity(episode, flow.view()).status is Validity.CURRENT


def test_a_changed_files_later_content_does_not_invalidate_its_precedent(tmp_path):
    """Its content legitimately differs before and after integration."""
    flow = _accepted(tmp_path)
    episode = _only(flow)
    (flow.repo / CHANGED).write_text("def verify():\n    return False\n\ndef extra():\n    pass\n", encoding="utf-8")
    assert evaluate_validity(episode, flow.view()).status is Validity.CURRENT


def test_a_capsule_contract_change_makes_relevant_experience_stale(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    index = _index()
    capsule = index.get("company-engineering-execution")
    changed = CapsuleIndex(
        replace(c, invariants=c.invariants[:-1] + ("A replacement rule.",)) if c.id == capsule.id else c
        for c in index.all()
    )
    report = evaluate_validity(episode, flow.view(capsules=changed))
    assert report.status is Validity.STALE
    assert any("company-engineering-execution contract changed" in r for r in report.reasons)


def test_a_capsule_prose_edit_is_not_a_contract_change(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    index = _index()
    reworded = CapsuleIndex(
        replace(c, title="Engineering execution loop", last_reviewed=LATER) if c.id == "company-engineering-execution" else c
        for c in index.all()
    )
    assert contract_digest(reworded.get("company-engineering-execution")) == contract_digest(index.get("company-engineering-execution"))
    assert evaluate_validity(episode, flow.view(capsules=reworded)).status is Validity.CURRENT


def test_an_unrelated_capsule_change_leaves_experience_current(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    index = _index()
    anchored = {a.capsule_id for a in episode.provenance.capsules}
    other = next(c for c in index.all() if c.id not in anchored and c.status is RecordStatus.ACTIVE)
    changed = CapsuleIndex(
        replace(c, invariants=c.invariants[:-1] + ("A replacement rule.",)) if c.id == other.id else c
        for c in index.all()
    )
    assert evaluate_validity(episode, flow.view(capsules=changed)).status is Validity.CURRENT


def test_a_governance_move_on_an_anchored_path_is_stale(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    index = _index()
    extra = replace(index.get("company-runtime"), owns_paths=index.get("company-runtime").owns_paths + (CHANGED,))
    moved = CapsuleIndex(extra if c.id == extra.id else c for c in index.all())
    report = evaluate_validity(episode, flow.view(capsules=moved))
    assert report.status is Validity.STALE


def test_a_read_files_structure_is_anchored_and_its_body_is_not(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    view = flow.view()
    provenance = capture_provenance(
        view, captured_on=LATER, decision_capsules=(), changed=(CHANGED,), read=("company/engineering/seed.py",), tests=()
    )
    anchored = replace(episode, provenance=provenance)
    assert evaluate_validity(anchored, view).status is Validity.CURRENT
    seed = flow.repo / "company" / "engineering" / "seed.py"
    seed.write_text("def seed():\n    # a comment\n    return 99\n", encoding="utf-8")
    assert evaluate_validity(anchored, view).status is Validity.CURRENT
    seed.write_text("def seed():\n    return 1\n\ndef renamed():\n    return 2\n", encoding="utf-8")
    report = evaluate_validity(anchored, view)
    assert report.status is Validity.STALE and "changed structure" in report.reasons[0]


def test_a_removed_path_or_retired_capsule_invalidates(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    index = _index()
    retired = CapsuleIndex(
        replace(c, status=RecordStatus.RETIRED) if c.id == "company-engineering-execution" else c for c in index.all()
    )
    assert evaluate_validity(episode, flow.view(capsules=retired)).status is Validity.INVALID
    (flow.repo / CHANGED).unlink()
    report = evaluate_validity(episode, flow.view())
    assert report.status is Validity.INVALID and any("no longer exists" in r for r in report.reasons)


def test_a_changed_canonical_record_leaves_the_episode_unresolved(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    path = flow.state / episode.pointer("gate_verdict").record_ref
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    problems = verify_pointers(episode, flow.state)
    assert len(problems) == 1 and "changed" in problems[0]
    report = evaluate_validity(episode, flow.view(), pointer_problems=problems)
    assert report.status is Validity.INVALID


def test_no_capsule_store_means_invalid_not_current(tmp_path):
    flow = _accepted(tmp_path)
    episode = _only(flow)
    assert evaluate_validity(episode, RepositoryView(repo_root=flow.repo, capsules=None)).status is Validity.INVALID
    report = capture_settled(flow.state, RepositoryView(repo_root=flow.repo), captured_on=LATER)
    assert report.captured == () and {r.code for r in report.refused} == {"provenance_unavailable"}


@pytest.mark.parametrize(
    "rule, path",
    [
        ("company/engineering", "company/engineering/lifecycle.py"),
        ("company/engineering", "company/engineering"),
        ("company/engineering", "company/engineering_extra/x.py"),
        ("company/run", "company/runtime/x.py"),
        ("company/engineering/*.py", "company/engineering/lifecycle.py"),
        ("company/engineering/*.py", "company/engineering/sub/lifecycle.py"),
        ("intelligence/research/batch*.py", "intelligence/research/batch_one.py"),
        ("tests/test_company_*.py", "tests/test_company_runtime.py"),
        ("company/**", "company/runtime/x.py"),
        ("docs/evidence/reviews", "docs/evidence/reviews/a.md"),
    ],
)
def test_the_coverage_rule_is_the_runtimes_rule(rule, path):
    from company.engineering.work_order import _read_covers
    from company.runtime.context_expansion_policy import _covers

    assert covers(rule, path) == _covers(rule, path) == _read_covers(rule, path)


# --- the knowledge store is a different thing ------------------------------------


def test_capture_and_advice_never_touch_the_knowledge_store(tmp_path):
    records = ROOT / "knowledge" / "company_os" / "records"
    before = {p.relative_to(records).as_posix(): p.read_bytes() for p in records.rglob("*.json")}
    flow = _accepted(tmp_path)
    _only(flow)
    after = {p.relative_to(records).as_posix(): p.read_bytes() for p in records.rglob("*.json")}
    assert after == before


def test_no_experience_module_can_write_a_knowledge_record():
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("knowledge.company_os.ledger"), path.name
                names = {a.name for a in node.names}
                assert not names & {"KnowledgeStore", "DecisionLedger", "Fact", "FailureLearning", "Decision", "promote"}, (path.name, names)


# --- the package boundary ------------------------------------------------------------


_FORBIDDEN_IMPORT_ROOTS = {
    "subprocess", "multiprocessing", "pty", "socket", "http", "urllib", "requests", "httpx",
    "anthropic", "openai", "transformers", "torch", "numpy", "sklearn", "faiss", "chromadb",
    "sqlite3", "tools", "sentence_transformers",
}


def test_the_experience_package_holds_no_network_model_embedding_or_database():
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {a.name.split(".")[0] for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                roots = {(node.module or "").split(".")[0]} if node.level == 0 else set()
            else:
                continue
            assert not roots & _FORBIDDEN_IMPORT_ROOTS, (path.name, roots)
        text = path.read_text(encoding="utf-8").lower()
        assert "embedding(" not in text and "cosine" not in text


def test_the_experience_store_never_imports_the_gate():
    """The gate reads Company OS and is read by none of it - this package included.

    P6B's import graph lives in `company.integration`; a caller supplies it
    (`RepositoryView.graph_builder`) rather than this package reaching for it.
    """
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert not (node.module or "").startswith("company.integration"), path.name
            elif isinstance(node, ast.Import):
                assert not any(a.name.startswith("company.integration") for a in node.names), path.name


def test_nothing_else_in_company_os_depends_on_the_experience_store():
    roots = [ROOT / name for name in ("company", "ai_platform", "knowledge", "intelligence")]
    for root in roots:
        for path in root.rglob("*.py"):
            if PACKAGE in path.parents:
                continue
            text = path.read_text(encoding="utf-8")
            assert "company.experience" not in text and "from company import experience" not in text, path


# --- the command line ------------------------------------------------------------------


def test_the_capture_and_list_commands(tmp_path, capsys):
    flow = _accepted(tmp_path)
    assert experience_cli.main(["capture", "--state-dir", str(flow.state), "--repo-root", str(flow.repo), "--on", "2026-09-20"]) in (0,)
    report = json.loads(capsys.readouterr().out)
    # The CLI loads the capsule store from the repo root, which this fake repo
    # does not have: the honest answer is "no provenance", not a guess.
    assert report["counts"].get("refused:provenance_unavailable") == 1
    _capture(flow)
    assert experience_cli.main(["list", "--state-dir", str(flow.state)]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert [row["class"] for row in listing["episodes"]] == ["accepted"]
    episode_id = listing["episodes"][0]["experience_id"]
    assert experience_cli.main(["show", "--state-dir", str(flow.state), "--experience-id", episode_id]) == 0
    assert json.loads(capsys.readouterr().out)["experience_id"] == episode_id
    assert experience_cli.main(["show", "--state-dir", str(flow.state), "--experience-id", "0" * 16]) == 2
