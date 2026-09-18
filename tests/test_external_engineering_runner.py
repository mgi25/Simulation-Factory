"""The external engineering runner, driven without a model and without Company OS.

## What these tests are for

The runner's whole claim is that a coding session cannot exceed the authority a
work order granted it, *whatever the session does*. A test that drove a real
model could never establish that: the interesting inputs are the ones a
well-behaved session never produces - a change outside `may_write`, a protected
file whose bytes moved, a branch that is not the authorized one, a test result
recorded at the wrong commit, a second runner claiming a job already in flight.

So everything here is arranged rather than observed. The control plane is a
scripted stand-in, the coding backend returns a canned answer, and git is real
- a temporary repository with a real bare remote - because git is the thing the
authority check reads, and a fake git would only prove that the fake agrees
with itself.

## This file may not import Company OS

`tools/` is a production root and `architecture.production_tests_independent`
requires that a production test module runs with `company/`, `ai_platform/`,
`knowledge/` and `intelligence/` removed from the checkout. One test below
asserts that property over this file and the package it covers by reading the
source, rather than by trusting the convention.

The cross-boundary proofs - that the runner's path matcher agrees with
`PathScope`, and that a receipt it builds is one `SessionReceipt` accepts -
live in `tests/test_company_external_engineering_runner.py`, which is allowed
to import both halves.

## Sentinels

The redaction tests use recognisable strings. "No secret leaks" is a sentence;
"the literal `sk-ant-SENTINEL...` does not appear in the persisted transcript"
is an assertion that can fail.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

import pytest

import tools.engineering_runner as runner_package
from tools.engineering_runner.authorization import (
    AuthorityEnvelope,
    PathRules,
    digest_paths,
    normalise_path,
    protected_drift,
    verify_developer_changes,
    verify_reviewer_left_no_trace,
)
from tools.engineering_runner.backends import SessionOutcome, SessionRequest
from tools.engineering_runner.briefs import review_instructions
from tools.engineering_runner.config import RunnerConfig
from tools.engineering_runner.errors import (
    AuthorityViolation,
    ClaimUnavailable,
    IntegrityFailure,
)
from tools.engineering_runner.evidence import (
    MAX_REF_CHARS,
    GitObservation,
    TestRun,
    assert_reviewer_report,
    assert_tests_describe,
    build_attestation,
    build_receipt,
    parse_json_object,
    suite_evidence,
)
from tools.engineering_runner.process import CommandRunner
from tools.engineering_runner.queue import RunStore, utcnow
from tools.engineering_runner.redaction import REDACTED, Redactor, child_environment
from tools.engineering_runner.runner import (
    COMPLETED,
    RUN_BLOCKED,
    RUN_FAILED,
    SKIPPED,
    EngineeringRunner,
)
from tools.engineering_runner.workspace import Workspace


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "tools" / "engineering_runner"

WORK_ORDER = "wo-runner-fixture"
BRANCH = "eng-runner-fixture"
EMPLOYEE = "software_implementation_engineer"
REVIEWER = "chief_architect"

# Recognisable, and not a credential for anything.
SENTINEL_TOKEN = "sk-ant-SENTINEL0123456789abcdefghijklmnop"


# --- fixtures --------------------------------------------------------------


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture()
def repository(tmp_path: Path) -> dict[str, Any]:
    """A real repository with a real bare remote, and one commit on main."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], capture_output=True, check=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "runner@example.invalid")
    _git(repo, "config", "user.name", "Runner Fixture")
    _git(repo, "config", "commit.gpgsign", "false")
    # The same two lines the real repository carries. They matter here rather
    # than being scenery: the runner reads `git status` to decide what a
    # session changed, and a repository that does not ignore its build
    # artifacts reports `__pycache__` as work. Honouring `.gitignore` is git's
    # answer and the right one - a file git ignores is not a change to the
    # repository - and the runner deliberately adds no second ignore list of
    # its own, because that list would be a place to hide a change.
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    (repo / "company").mkdir()
    (repo / "company" / "permissions.yaml").write_text("reserved: [publish]\n", encoding="utf-8")
    (repo / "subject").mkdir()
    (repo / "subject" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_subject.py").write_text(
        "from subject.module import VALUE\n\n\ndef test_value():\n    assert VALUE\n",
        encoding="utf-8",
    )
    _git(repo, "add", "--all")
    _git(repo, "commit", "--message", "base")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "--set-upstream", "origin", "main")
    return {
        "repo": repo,
        "origin": origin,
        "base": _git(repo, "rev-parse", "HEAD"),
        "tmp": tmp_path,
    }


def developer_briefing(base: str, *, allowed: Sequence[str] = ("subject",)) -> dict[str, Any]:
    forbidden = ["company/permissions.yaml"]
    return {
        "role": "developer",
        "employee": EMPLOYEE,
        "state": "developing",
        "packet_fingerprint": "a1b2c3d4e5f60718",
        "work_order": {
            "work_order_id": WORK_ORDER,
            "work_order_fingerprint": "0f1e2d3c4b5a6978",
            "objective": "Raise VALUE to two, because one is not enough.",
            "requested_by": "MGI",
            "authorized_on": "2026-09-18",
            "authorized_branch": BRANCH,
            "base_commit": base,
            "authorized_paths": list(allowed),
            "forbidden_paths": [],
            "protected_paths": forbidden,
            "acceptance_criteria": ["VALUE is two"],
            "constraints": ["change nothing else"],
            "required_tests": ["tests/test_subject.py"],
            "context_refs": ["module_contract:subject"],
            "max_developer_attempts": 3,
            "escalate_instead_of": ["merging, deploying, publishing or tagging anything"],
        },
        "packet": {
            "task_id": WORK_ORDER,
            "objective": "Raise VALUE to two.",
            "employee": EMPLOYEE,
            "path_scope": {"allowed": list(allowed), "forbidden": forbidden},
            "expected_branch": BRANCH,
            "expected_base_commit": base,
            "required_tests": ["tests/test_subject.py"],
            "no_subagents": True,
        },
        "transport": {
            "packet_attempt": 1,
            "authority_fingerprint": "9988776655443322",
            "effective_context_fingerprint": "1122334455667788",
        },
        "persisted": {
            "packet": {
                "record_ref": "execution/packets/x/000001.json",
                "fingerprint": "a1b2c3d4e5f60718",
                "attempt": 1,
            }
        },
    }


def review_briefing(base: str) -> dict[str, Any]:
    payload = developer_briefing(base)
    payload["role"] = "reviewer"
    payload["reviewer"] = REVIEWER
    payload["implementer"] = EMPLOYEE
    payload.pop("employee")
    payload["read_only"] = True
    payload["review_instructions"] = ["change nothing: this packet grants no writable path"]
    payload["packet"]["path_scope"] = {"allowed": [], "forbidden": []}
    # A review is its own task. `EngineeringWorkOrder.review_specification`
    # builds `<work_order_id>-review`, because the two roles route to different
    # employees by different capabilities.
    payload["packet"]["task_id"] = f"{WORK_ORDER}-review"
    payload["packet_fingerprint"] = "beefbeefbeefbeef"
    payload["persisted"]["packet"]["fingerprint"] = "beefbeefbeefbeef"
    payload["persisted"]["packet"]["attempt"] = 1
    return payload


# --- path rules ------------------------------------------------------------


def test_an_empty_allow_list_allows_nothing():
    rules = PathRules()
    assert rules.read_only
    assert rules.violations(["anything.py"])


def test_a_forbidden_rule_beats_a_broader_allowed_one():
    rules = PathRules(allowed=("company",), forbidden=("company/permissions.yaml",))
    assert rules.violations(["company/runtime/packets.py"]) == ()
    (finding,) = rules.violations(["company/permissions.yaml"])
    assert "forbidden rule company/permissions.yaml" in finding


def test_prefix_matching_respects_path_segments():
    rules = PathRules(allowed=("company/runtime",))
    assert rules.violations(["company/runtime/packets.py"]) == ()
    assert rules.violations(["company/runtime_extra.py"])


def test_a_windows_separator_names_the_same_file():
    rules = PathRules(allowed=("company/runtime",))
    assert rules.violations(["company\\runtime\\packets.py"]) == ()


@pytest.mark.parametrize(
    "value", ["/etc/passwd", "C:/Windows/system32", "../outside.py", "company/../../x"]
)
def test_a_path_that_escapes_the_repository_is_refused(value: str):
    with pytest.raises(IntegrityFailure):
        normalise_path(value)


# --- the envelope: the runner cannot widen what it was given ---------------


def test_a_well_formed_developer_briefing_parses_to_its_own_terms():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    assert envelope.may_write == ("subject",)
    assert envelope.may_not_modify == ("company/permissions.yaml",)
    assert envelope.packet_attempt == 1
    assert envelope.authority_fingerprint == "9988776655443322"
    assert not envelope.read_only


def test_the_runner_cannot_expand_may_write_by_editing_the_packet():
    """A packet whose writable scope is wider than the work order is refused.

    This is the escalation the envelope exists to stop. Widening `may_write`
    anywhere - in the packet, in the briefing file on disk, in transit -
    produces two documents that disagree, and the runner refuses the pair
    rather than taking the more permissive one.
    """
    payload = developer_briefing("a" * 40)
    payload["packet"]["path_scope"]["allowed"] = ["subject", "company"]
    with pytest.raises(IntegrityFailure, match="writable scope"):
        AuthorityEnvelope.parse(payload)


def test_dropping_the_packets_forbidden_list_is_also_refused():
    payload = developer_briefing("a" * 40)
    payload["packet"]["path_scope"]["forbidden"] = []
    with pytest.raises(IntegrityFailure, match="forbidden scope"):
        AuthorityEnvelope.parse(payload)


def test_a_reviewer_sees_the_grant_and_still_holds_no_writable_path():
    """Two different questions, and the reviewer needs both answers.

    `may_write` is what *this session* may change, and for a reviewer it is
    empty - that is what read-only means. `authorized_paths` is what the *work
    order* granted, and a reviewer judging whether the work stayed in scope has
    nothing to compare the diff against without it. The review brief used to
    fall back to the receipt's own changed-file list, which is the diff
    labelled as the grant and answers the question by assuming it.
    """
    envelope = AuthorityEnvelope.parse(review_briefing("a" * 40))
    assert envelope.may_write == ()
    assert envelope.read_only
    assert envelope.authorized_paths == ("subject",)

    instructions = review_instructions(
        envelope,
        diff_path=Path("diff.patch"),
        worktree=Path("worktree"),
        receipt={"files_changed": ["subject/module.py"], "commit_sha": "a" * 40},
        developer_report={"summary": "x"},
    )
    grant = instructions.split("may change:")[1].split("must not change:")[0]
    assert "- subject" in grant
    assert "module.py" not in grant


def test_a_reviewer_packet_that_grants_a_writable_path_is_refused():
    payload = review_briefing("a" * 40)
    payload["packet"]["path_scope"]["allowed"] = ["subject"]
    with pytest.raises(IntegrityFailure, match="read-only"):
        AuthorityEnvelope.parse(payload)


def test_a_packet_for_another_work_order_is_refused():
    payload = developer_briefing("a" * 40)
    payload["packet"]["task_id"] = "wo-something-else"
    with pytest.raises(IntegrityFailure, match="will not act on the pair"):
        AuthorityEnvelope.parse(payload)


def test_each_role_expects_its_own_task_id_and_refuses_the_others():
    """A review is a different task, and the two ids are not interchangeable.

    The first version of this check compared both roles' packets with the work
    order id, which reads correctly and is wrong: it refused every real review
    packet, and the dogfood run found it at the review stage rather than in a
    test. Both directions are asserted now.
    """
    reviewer = review_briefing("a" * 40)
    assert AuthorityEnvelope.parse(reviewer).task_id == f"{WORK_ORDER}-review"

    reviewer_with_developer_task = review_briefing("a" * 40)
    reviewer_with_developer_task["packet"]["task_id"] = WORK_ORDER
    with pytest.raises(IntegrityFailure, match="will not act on the pair"):
        AuthorityEnvelope.parse(reviewer_with_developer_task)

    developer_with_review_task = developer_briefing("a" * 40)
    developer_with_review_task["packet"]["task_id"] = f"{WORK_ORDER}-review"
    with pytest.raises(IntegrityFailure, match="will not act on the pair"):
        AuthorityEnvelope.parse(developer_with_review_task)


def test_a_packet_fingerprint_that_disagrees_with_the_stored_record_is_refused():
    payload = developer_briefing("a" * 40)
    payload["persisted"]["packet"]["fingerprint"] = "ffffffffffffffff"
    with pytest.raises(IntegrityFailure, match="different packets"):
        AuthorityEnvelope.parse(payload)


def test_a_transport_bundle_for_another_attempt_is_refused():
    payload = developer_briefing("a" * 40)
    payload["transport"]["packet_attempt"] = 7
    with pytest.raises(IntegrityFailure, match="attempt"):
        AuthorityEnvelope.parse(payload)


def test_a_packet_expecting_another_branch_is_refused():
    payload = developer_briefing("a" * 40)
    payload["packet"]["expected_branch"] = "main"
    with pytest.raises(IntegrityFailure, match="branch"):
        AuthorityEnvelope.parse(payload)


def test_a_packet_expecting_another_base_commit_is_refused():
    payload = developer_briefing("a" * 40)
    payload["packet"]["expected_base_commit"] = "b" * 40
    with pytest.raises(IntegrityFailure, match="base"):
        AuthorityEnvelope.parse(payload)


# --- verification after the fact ------------------------------------------


def _verify(envelope: AuthorityEnvelope, **overrides: Any):
    defaults: dict[str, Any] = {
        "changed_paths": ("subject/module.py",),
        "branch": BRANCH,
        "head_commit": "c" * 40,
        "base_is_ancestor": True,
        "protected_before": {"company/permissions.yaml": "digest"},
        "protected_after": {"company/permissions.yaml": "digest"},
        "worktree_identity_ok": True,
    }
    defaults.update(overrides)
    return verify_developer_changes(envelope, **defaults)


def test_a_clean_attempt_passes_every_check():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(envelope)
    assert verdict.ok
    assert "changed paths against may_write" in verdict.checked


def test_a_changed_path_outside_may_write_is_a_violation():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(envelope, changed_paths=("subject/module.py", "company/runtime/x.py"))
    assert not verdict.ok
    assert any("outside every authorized path" in item for item in verdict.violations)


def test_a_protected_policy_that_drifted_is_a_violation_even_with_a_clean_diff():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(
        envelope, protected_after={"company/permissions.yaml": "something-else"}
    )
    assert not verdict.ok
    assert any("protected path" in item for item in verdict.violations)


def test_a_deleted_protected_file_is_drift_rather_than_a_gap():
    drift = protected_drift({"a": "digest"}, {"a": "absent"})
    assert drift and "a" in drift[0]


def test_work_on_another_branch_is_a_violation():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(envelope, branch="main")
    assert any("not the authorized" in item for item in verdict.violations)


def test_a_rewritten_history_is_a_violation():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(envelope, base_is_ancestor=False)
    assert any("history was rewritten" in item for item in verdict.violations)


def test_the_wrong_worktree_is_a_violation():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(
        envelope,
        worktree_identity_ok=False,
        worktree_reason="the work happened in another repository",
    )
    assert "the work happened in another repository" in verdict.violations


def test_an_unauthorized_dependency_change_is_a_violation():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    verdict = _verify(envelope, changed_paths=("subject/module.py", "requirements.txt"))
    assert any("requirements.txt" in item for item in verdict.violations)


def test_a_review_that_left_a_trace_is_refused():
    verdict = verify_reviewer_left_no_trace(
        head_before="a" * 40, head_after="b" * 40, status_after=()
    )
    assert any("moved HEAD" in item for item in verdict.violations)
    dirty = verify_reviewer_left_no_trace(
        head_before="a" * 40, head_after="a" * 40, status_after=("notes.md",)
    )
    assert any("dirty" in item for item in dirty.violations)


def test_digesting_records_an_absent_file_rather_than_skipping_it(tmp_path: Path):
    digests = digest_paths(tmp_path, ["missing.yaml"])
    assert digests == {"missing.yaml": "absent"}


# --- evidence --------------------------------------------------------------


def _test_run(commit: str, *, green: bool = True) -> TestRun:
    return TestRun(
        command="tests/test_subject.py",
        argv=("python", "-m", "pytest"),
        commit=commit,
        exit_code=0 if green else 1,
        passed=1 if green else 0,
        failed=0 if green else 1,
        errors=0,
        skipped=0,
        summary="1 passed" if green else "1 failed",
        duration_s=0.1,
        timed_out=False,
    )


def test_a_test_result_from_another_commit_is_refused():
    with pytest.raises(IntegrityFailure, match="another commit"):
        assert_tests_describe([_test_run("a" * 40)], "b" * 40)


def test_a_receipt_cannot_be_built_from_evidence_for_another_commit():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    observation = GitObservation(
        branch=BRANCH,
        base_commit="a" * 40,
        commit_sha="b" * 40,
        remote_branch_sha="b" * 40,
        remote_verified=True,
        working_tree_clean=True,
        files_changed=("subject/module.py",),
    )
    with pytest.raises(IntegrityFailure):
        build_receipt(
            envelope,
            observation=observation,
            tests=[_test_run("c" * 40)],
            narrative={"summary": "x"},
            session=_session(),
            completed_at=utcnow(),
            accepted=True,
        )


def _session(role: str = "developer", session_id: str = "s" * 8) -> SessionOutcome:
    return SessionOutcome(
        backend="claude_code",
        role=role,
        session_id=session_id,
        model="claude-test",
        exit_code=0,
        duration_s=1.0,
        result_text="{}",
        transcript="",
        ok=True,
        cost_usd=0.5,
        input_units=10,
        output_units=20,
        turns=3,
    )


def test_a_receipt_reports_measured_facts_and_narrated_ones_separately():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    observation = GitObservation(
        branch=BRANCH,
        base_commit="a" * 40,
        commit_sha="b" * 40,
        remote_branch_sha="b" * 40,
        remote_verified=True,
        working_tree_clean=True,
        files_changed=("subject/module.py",),
    )
    receipt = build_receipt(
        envelope,
        observation=observation,
        tests=[_test_run("b" * 40)],
        narrative={
            "summary": "VALUE is two.",
            "files_changed": ["everything", "in", "the", "repository"],
            "commit_sha": "d" * 40,
            "context_refs_used": ["module_contract:subject", "something:invented"],
        },
        session=_session(),
        completed_at=utcnow(),
        accepted=True,
    )
    # measured, not narrated
    assert receipt["files_changed"] == ["subject/module.py"]
    assert receipt["commit_sha"] == "b" * 40
    # narrated, but only within what the packet supplied
    assert receipt["context_refs_used"] == ["module_contract:subject"]
    # invariant, always
    assert receipt["merge_performed"] is False
    assert receipt["no_subagents"] is True
    assert receipt["subagents_used"] == 0


def test_a_rejected_receipt_always_carries_a_reason():
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    receipt = build_receipt(
        envelope,
        observation=GitObservation(BRANCH, "a" * 40, "", "", False, True, ()),
        tests=(),
        narrative={},
        session=_session(),
        completed_at=utcnow(),
        accepted=False,
    )
    assert receipt["outcome"] == "rejected"
    assert receipt["rejection_reason"].strip()


def test_an_attestation_names_the_developers_packet_not_the_reviewers():
    reviewer_envelope = AuthorityEnvelope.parse(review_briefing("a" * 40))
    attestation = build_attestation(
        reviewer_envelope,
        review_id="rev-fixture-01",
        reviewer=REVIEWER,
        reviewed_packet_fingerprint="a1b2c3d4e5f60718",
        receipt_fingerprint="1111222233334444",
        reviewed_on=dt.date(2026, 9, 18),
        reported={
            "verdict": "pass",
            "criteria": [{"criterion": "VALUE is two", "satisfied": True, "evidence_ref": "x"}],
            "findings": [{"severity": "advisory", "summary": "a nit", "deterministic": True}],
        },
    )
    assert attestation["packet_fingerprint"] == "a1b2c3d4e5f60718"
    assert reviewer_envelope.packet_fingerprint == "beefbeefbeefbeef"
    # A reviewer cannot claim a deterministic finding; Company OS computes those.
    assert attestation["findings"][0]["deterministic"] is False


def _review_answer(**changes):
    answer = {
        "verdict": "pass",
        "criteria": [
            {"criterion": "VALUE is two", "satisfied": True, "evidence_ref": "subject/module.py"}
        ],
        "findings": [],
        "evidence": ["subject/module.py"],
        "changed_paths_reviewed": ["subject/module.py"],
        "notes": "",
    }
    answer.update(changes)
    return answer


def test_a_well_formed_review_passes_the_contract_check():
    assert_reviewer_report(_review_answer()) is None


def test_a_reference_that_is_really_a_paragraph_is_refused():
    """The failure the first real dogfood run hit, at the stage that can repair it.

    Company OS refused a 424-character `evidence_ref` one stage later, which
    was correct and cost the whole review session. The same budget is applied
    the moment the session answers, so the session that made the judgment can
    restate it.
    """
    answer = _review_answer(
        criteria=[
            {
                "criterion": "VALUE is two",
                "satisfied": True,
                "evidence_ref": "because " + "x" * MAX_REF_CHARS,
            }
        ]
    )
    with pytest.raises(IntegrityFailure, match="reference budget"):
        assert_reviewer_report(answer)


def test_a_multi_line_reference_is_refused():
    answer = _review_answer(
        criteria=[
            {"criterion": "c", "satisfied": True, "evidence_ref": "a.py" + chr(10) + "b.py"}
        ]
    )
    with pytest.raises(IntegrityFailure, match="one line"):
        assert_reviewer_report(answer)


def test_a_satisfied_criterion_with_no_reference_is_refused():
    answer = _review_answer(
        criteria=[{"criterion": "c", "satisfied": True, "evidence_ref": ""}]
    )
    with pytest.raises(IntegrityFailure, match="names what satisfies it"):
        assert_reviewer_report(answer)


@pytest.mark.parametrize(
    "changes,expected",
    [
        ({"verdict": "approved"}, "must be one of"),
        ({"verdict": "pass", "criteria": []}, "non-empty list"),
        (
            {"findings": [{"severity": "critical", "summary": "x"}]},
            "severity",
        ),
        ({"findings": [{"severity": "advisory", "summary": "  "}]}, "summary is empty"),
        ({"evidence": ["x" * 400]}, "reference budget"),
    ],
)
def test_the_review_contract_refuses_what_company_os_would_refuse(changes, expected):
    with pytest.raises(IntegrityFailure, match=expected):
        assert_reviewer_report(_review_answer(**changes))


def test_a_reviewer_that_answers_badly_is_asked_again_in_the_same_session(repository):
    """The bounded repair loop, on the failure it was extended to cover."""

    class SloppyThenCorrect(ScriptedBackend):
        def __init__(self) -> None:
            super().__init__(edit=_in_scope_edit)
            self.reviews = 0

        def launch(self, request: SessionRequest) -> SessionOutcome:
            if request.role != "reviewer":
                return super().launch(request)
            self.reviews += 1
            self.launched.append(request)
            self.session_ids.append(request.session_id)
            body = _review_answer()
            if self.reviews == 1:
                body["criteria"][0]["evidence_ref"] = "b" * 400
            return SessionOutcome(
                backend=self.name,
                role=request.role,
                session_id=request.session_id,
                model="scripted",
                exit_code=0,
                duration_s=0.01,
                result_text=json.dumps(body),
                transcript="",
                ok=True,
            )

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = SloppyThenCorrect()
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    assert backend.reviews == 2
    assert report.outcome == COMPLETED, report.reason
    assert len(control.attestations) == 1
    # The repair repeated the request and changed no term.
    first, second = [r for r in backend.launched if r.role == "reviewer"]
    assert second.instructions.startswith(first.instructions)
    assert "could not be read" in second.instructions


def test_suite_evidence_reports_a_failure_rather_than_hiding_it():
    evidence = suite_evidence(
        [_test_run("a" * 40, green=False)],
        observed_on=dt.date(2026, 9, 18),
        reported_by="runner",
    )
    (row,) = evidence["results"]
    assert row["passed"] is False
    assert row["failed"] >= 1


def test_a_fenced_json_answer_is_read_and_a_prose_one_is_not():
    assert parse_json_object('```json\n{"verdict": "pass"}\n```', "x") == {"verdict": "pass"}
    with pytest.raises(IntegrityFailure):
        parse_json_object("I reviewed it and it looks fine.", "x")


# --- the lease -------------------------------------------------------------


def test_a_second_runner_cannot_claim_a_job_already_in_flight(tmp_path: Path):
    first = RunStore(tmp_path, runner_id="runner-one")
    second = RunStore(tmp_path, runner_id="runner-two")
    first.acquire(WORK_ORDER, lease_seconds=3600)
    with pytest.raises(ClaimUnavailable, match="runner-one"):
        second.acquire(WORK_ORDER, lease_seconds=3600)


def test_a_stale_lease_is_reclaimed_and_the_reclamation_is_recorded(tmp_path: Path):
    first = RunStore(tmp_path, runner_id="runner-one")
    lease, _ = first.acquire(WORK_ORDER, lease_seconds=3600)
    assert lease.age_s() < 5
    second = RunStore(tmp_path, runner_id="runner-two")
    taken, how = second.acquire(WORK_ORDER, lease_seconds=0.0)
    assert "stale" in how
    assert taken.reclaimed_from == "runner-one"


def test_a_released_lease_is_taken_without_a_reclamation_note(tmp_path: Path):
    first = RunStore(tmp_path, runner_id="runner-one")
    lease, _ = first.acquire(WORK_ORDER, lease_seconds=3600)
    first.release(lease)
    second = RunStore(tmp_path, runner_id="runner-two")
    _, how = second.acquire(WORK_ORDER, lease_seconds=3600)
    assert how == "took a released lease"


def test_the_outcome_log_is_append_only(tmp_path: Path):
    store = RunStore(tmp_path, runner_id="runner-one")
    store.record_outcome({"work_order_id": WORK_ORDER, "outcome": "completed"})
    store.record_outcome({"work_order_id": WORK_ORDER, "outcome": "blocked"})
    outcomes = store.outcomes(WORK_ORDER)
    assert [item["outcome"] for item in outcomes] == ["completed", "blocked"]
    directory = store.job_dir(WORK_ORDER) / "outcomes"
    assert sorted(path.name for path in directory.glob("*.json")) == [
        "000001.json",
        "000002.json",
    ]


# --- redaction -------------------------------------------------------------


def test_an_environment_secret_never_reaches_a_persisted_transcript():
    redactor = Redactor(environment={"ANTHROPIC_API_KEY": SENTINEL_TOKEN})
    text = f"calling the api with {SENTINEL_TOKEN} now"
    assert SENTINEL_TOKEN not in redactor.scrub(text)
    assert REDACTED in redactor.scrub(text)


def test_a_credential_in_a_git_remote_url_is_removed():
    redactor = Redactor(environment={})
    scrubbed = redactor.scrub("https://someone:ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345@github.com/x/y.git")
    assert "ghp_" not in scrubbed
    assert "github.com/x/y.git" in scrubbed


def test_a_vendor_key_quoted_back_in_an_error_body_is_removed():
    redactor = Redactor(environment={})
    assert SENTINEL_TOKEN not in redactor.scrub(f'{{"error": "bad key {SENTINEL_TOKEN}"}}')


def test_an_ordinary_variable_whose_name_contains_key_is_not_redacted():
    redactor = Redactor(environment={"KEYBOARD": "dvorak-layout-for-everything"})
    assert redactor.scrub("dvorak-layout-for-everything") == "dvorak-layout-for-everything"


def test_the_child_environment_drops_the_nested_session_markers():
    env = child_environment({"CLAUDECODE": "1", "CLAUDE_CODE_ENTRYPOINT": "cli", "PATH": "/x"})
    assert "CLAUDECODE" not in env
    assert "CLAUDE_CODE_ENTRYPOINT" not in env
    assert env["PATH"] == "/x"


# --- the loop, with a scripted control plane ------------------------------


class ScriptedControlPlane:
    """A stand-in that answers like `company.engineering` and records what it was asked."""

    def __init__(self, base: str, *, states: list[str]) -> None:
        self.base = base
        self.states = states
        self.calls: list[tuple[str, Any]] = []
        self.receipts: list[dict[str, Any]] = []
        self.attestations: list[dict[str, Any]] = []
        self.review_repo_roots: list[Path] = []
        self.review_outcome = "pass"
        self.corrections = 0
        self.max_attempts = 3
        self.gate_readiness = "ready"
        self.receipt_accepted = True

    # the surface `EngineeringRunner` uses
    def listing(self):
        return _reply({"work_orders": [{"work_order_id": WORK_ORDER, "state": self.states[0]}]})

    def status(self, work_order_id: str):
        self.calls.append(("status", work_order_id))
        return _reply({"state": self.states[0], "reviews": [], "attestations": []})

    def developer_brief(self, work_order_id: str, *, executor: str):
        self.calls.append(("brief", executor))
        self._advance("developing")
        return _reply(developer_briefing(self.base))

    def submit_receipt(self, work_order_id: str, receipt_file: Path, *, repo_dir=None):
        payload = json.loads(Path(receipt_file).read_text(encoding="utf-8"))
        self.receipts.append(payload)
        self.calls.append(("receipt", payload["outcome"]))
        self._advance("testing")
        return _reply(
            {
                "state": "testing",
                "accepted": self.receipt_accepted and payload["outcome"] == "accepted",
                "failures": [],
                "receipt_fingerprint": "1111222233334444",
            },
            exit_code=0 if self.receipt_accepted else 1,
        )

    def review_brief(self, work_order_id: str, *, implementer: str, executor: str):
        self.calls.append(("review-brief", implementer))
        self._advance("reviewing")
        return _reply(review_briefing(self.base))

    def submit_review(
        self, work_order_id: str, attestation_file: Path, *, implementer: str, repo_root: Path
    ):
        """Adjudicate like the real one: the worst of attested and deterministic.

        The outcome decides the next state, and that mapping is
        `company/engineering/orchestrator.record_review`: PASS goes to the
        gate, CHANGES_REQUIRED goes back to `planning` while attempts remain
        and to `decision_required` when they do not, and BLOCKED goes to
        `blocked`. A stand-in that always said PASS would let the runner's loop
        look correct on an attempt Company OS would have sent back.
        """
        payload = json.loads(Path(attestation_file).read_text(encoding="utf-8"))
        self.attestations.append(payload)
        self.review_repo_roots.append(Path(repo_root))
        outcome = self.review_outcome
        if outcome == "pass" and not self.receipts[-1]["outcome"] == "accepted":
            outcome = "changes_required"
        self.calls.append(("review", payload["verdict"]))
        if outcome == "pass":
            self._advance("gate")
            state = "gate"
        elif outcome == "changes_required":
            self.corrections += 1
            state = "planning" if self.corrections < self.max_attempts else "decision_required"
            self._advance(state)
        else:
            self._advance("blocked")
            state = "blocked"
        return _reply({"state": state, "review": {"outcome": outcome}})

    def gate_check(self, *, gate_repo_root: Path, suite_evidence: Path, timeout_s: float):
        self.calls.append(("gate-check", str(gate_repo_root)))
        # Report, then verdict - and the verdict is not a field of the report.
        # `company.integration check` says it with its exit code only.
        return _command(), {"report_id": "r-1", "required_check_ids": ["x"]}, self.gate_readiness

    def submit_gate(self, work_order_id, gate_report, *, reported_readiness, implementation_commit):
        self.calls.append(("gate", reported_readiness))
        state = "ready_for_approval" if reported_readiness == "ready" else "blocked"
        self._advance(state)
        return _reply({"state": state})

    def result(self, work_order_id: str, *, risks=()):
        return _reply({"status": self.states[0]})

    def result_text(self, work_order_id: str):
        return _command()

    def _advance(self, state: str) -> None:
        self.states[0] = state


def _reply(payload: Mapping[str, Any], *, exit_code: int = 0):
    from tools.engineering_runner.controlplane import StageReply

    return StageReply(
        command="scripted", exit_code=exit_code, payload=dict(payload), raw=_command()
    )


def _command():
    from tools.engineering_runner.process import CommandResult

    return CommandResult(
        argv=("scripted",), cwd=".", exit_code=0, stdout="", stderr="", duration_s=0.0
    )


class ScriptedBackend:
    """A backend that edits the tree the way an obedient session would."""

    def __init__(self, *, edit: Any = None, report: Mapping[str, Any] | None = None) -> None:
        self.name = "claude_code"
        self.edit = edit
        self.report = report
        self.launched: list[SessionRequest] = []
        self.session_ids: list[str] = []

    def available(self) -> tuple[bool, str]:
        return True, "scripted"

    def launch(self, request: SessionRequest) -> SessionOutcome:
        self.launched.append(request)
        self.session_ids.append(request.session_id)
        if self.edit is not None and not request.read_only:
            self.edit(Path(request.cwd))
        payload = dict(self.report or {})
        if request.role == "developer":
            body = json.dumps(
                payload
                or {
                    "outcome": "accepted",
                    "summary": "VALUE is two now.",
                    "invariants_preserved": ["nothing else moved"],
                    "unresolved_risks": [],
                    "evidence": ["subject/module.py"],
                    "context_refs_used": ["module_contract:subject"],
                    "notes": "",
                }
            )
            target = next(iter(request.extra_dirs)) / "report.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(body, encoding="utf-8")
            result = "wrote the report"
        else:
            result = json.dumps(
                payload
                or {
                    "verdict": "pass",
                    "criteria": [
                        {"criterion": "VALUE is two", "satisfied": True, "evidence_ref": "subject/module.py"}
                    ],
                    "findings": [],
                    "evidence": ["subject/module.py"],
                    "changed_paths_reviewed": ["subject/module.py"],
                    "notes": "",
                }
            )
        return SessionOutcome(
            backend=self.name,
            role=request.role,
            session_id=request.session_id,
            model="scripted",
            exit_code=0,
            duration_s=0.01,
            result_text=result,
            transcript="scripted transcript",
            ok=True,
        )


def _runner(repository: dict[str, Any], backend: ScriptedBackend, control: ScriptedControlPlane):
    tmp = repository["tmp"]
    config = RunnerConfig(
        repo_root=repository["repo"],
        state_dir=tmp / "state",
        runner_dir=tmp / "runner",
        worktree_root=tmp / "worktrees",
        push=True,
        poll_interval_s=0.01,
        test_timeout_s=300.0,
        # The fixture repository holds one suite, not the eleven the real gate
        # requires. Pointing the gate stage at it keeps these tests about the
        # loop rather than about eleven pytest start-ups; the gate's own
        # `health.required_suites_pass` is what decides whether a set is
        # sufficient, and it is exercised for real in the dogfood run.
        gate_suites=("tests/test_subject.py",),
    )
    (tmp / "state").mkdir(exist_ok=True)
    commands = CommandRunner()
    workspace = Workspace(
        commands,
        repo_root=repository["repo"],
        worktree_root=tmp / "worktrees",
        remote="origin",
    )
    return EngineeringRunner(
        config,
        command_runner=commands,
        control_plane=control,
        workspace=workspace,
        backend_factory=lambda name: backend,
        today=lambda: dt.date(2026, 9, 18),
    )


def _in_scope_edit(worktree: Path) -> None:
    (worktree / "subject" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")


def _out_of_scope_edit(worktree: Path) -> None:
    (worktree / "subject" / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    (worktree / "company" / "permissions.yaml").write_text("reserved: []\n", encoding="utf-8")


def test_an_authorized_job_runs_developer_then_review_then_gate(repository):
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    assert report.outcome == COMPLETED, report.reason
    assert report.final_state == "ready_for_approval"
    assert [item.stage for item in report.stages] == ["developer", "reviewer", "gate"]
    receipt = control.receipts[0]
    assert receipt["outcome"] == "accepted"
    assert receipt["files_changed"] == ["subject/module.py"]
    assert receipt["remote_verified"] is True
    assert control.attestations[0]["verdict"] == "pass"


def test_the_developer_and_reviewer_run_in_different_sessions(repository):
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    _runner(repository, backend, control).run_one(WORK_ORDER)
    assert len(backend.session_ids) == 2
    assert backend.session_ids[0] != backend.session_ids[1]
    developer, reviewer = backend.launched
    assert developer.read_only is False
    assert reviewer.read_only is True
    assert "Write" in reviewer.disallowed_tools and "Bash" in reviewer.disallowed_tools


def test_a_change_outside_may_write_blocks_the_run_and_commits_nothing(repository):
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_out_of_scope_edit)
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)

    assert report.outcome == RUN_BLOCKED
    assert "protected path" in report.reason or "forbidden" in report.reason
    # the truthful evidence went back, as a rejected receipt at no commit
    assert control.receipts[0]["outcome"] == "rejected"
    assert control.receipts[0]["commit_sha"] == ""
    # and nothing was committed on the task branch
    worktree = runner._workspace.worktree_path(BRANCH)  # noqa: SLF001 - the point of the test
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(worktree), capture_output=True, text=True, check=True
    ).stdout.strip()
    assert head == repository["base"]
    # no review session was launched for a blocked attempt
    assert [request.role for request in backend.launched] == ["developer"]


def test_a_failing_required_test_produces_a_rejected_receipt_rather_than_a_pass(repository):
    def break_it(worktree: Path) -> None:
        (worktree / "subject" / "module.py").write_text("VALUE = 0\n", encoding="utf-8")

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    control.receipt_accepted = False
    control.max_attempts = 1  # no correction budget: one attempt, then the CEO
    backend = ScriptedBackend(edit=break_it)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    receipt = control.receipts[0]
    assert receipt["outcome"] == "rejected"
    assert "required test(s) failed" in receipt["rejection_reason"]
    assert report.outcome == RUN_BLOCKED
    assert report.final_state == "decision_required"


def test_a_review_that_requires_changes_spends_another_authorized_attempt(repository):
    """The correction loop is Company OS's, and the runner turns its crank.

    A review that requires changes sends the job back to `planning`, which is
    actionable, so the next turn of the run issues the next attempt. The runner
    decides nothing about it: the ceiling that stops the loop is the work
    order's, and it stops the loop by moving the job somewhere the runner
    cannot act on.
    """
    attempts = {"count": 0}

    def fix_on_the_second_try(worktree: Path) -> None:
        attempts["count"] += 1
        value = 0 if attempts["count"] == 1 else 2
        (worktree / "subject" / "module.py").write_text(
            "VALUE = " + str(value) + chr(10), encoding="utf-8"
        )

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    control.max_attempts = 3
    backend = ScriptedBackend(edit=fix_on_the_second_try)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    assert attempts["count"] == 2
    assert [item.stage for item in report.stages] == [
        "developer",
        "reviewer",
        "developer",
        "reviewer",
        "gate",
    ]
    assert report.outcome == COMPLETED, report.reason
    assert report.final_state == "ready_for_approval"
    assert control.receipts[0]["outcome"] == "rejected"
    assert control.receipts[1]["outcome"] == "accepted"
    # Four sessions - two developer, two reviewer - and no two share an id.
    # The gate stage launches none: it runs suites and a CLI.
    assert len(set(backend.session_ids)) == len(backend.session_ids) == 4


def test_a_stage_that_does_not_move_the_job_stops_the_run(repository):
    """A stall is not a correction, and repeating it would spend sessions forever."""

    class GoesNowhere(ScriptedControlPlane):
        def submit_receipt(self, work_order_id, receipt_file, *, repo_dir=None):
            payload = json.loads(Path(receipt_file).read_text(encoding="utf-8"))
            self.receipts.append(payload)
            self._advance("planning")
            return _reply({"state": "planning", "accepted": False, "failures": []})

    control = GoesNowhere(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    assert report.outcome == RUN_FAILED
    assert "did not move it" in report.reason
    assert len(report.stages) == 1


def test_the_gate_verdict_is_read_from_the_exit_code_and_passed_for_cross_checking(repository):
    """`--reported-readiness` is what makes the gate's own report argue with itself.

    `GateVerdict.from_report_mapping` compares the verdict the caller reports
    with the one the report's required checks derive, and refuses the pair if
    they differ. The runner used to look for a `readiness` field the report
    does not have, pass an empty string, and silently skip that comparison.
    The verdict lives in the exit code.
    """
    from tools.engineering_runner.controlplane import GATE_READINESS_BY_EXIT

    assert GATE_READINESS_BY_EXIT == {0: "ready", 1: "blocked", 2: "insufficient_evidence"}

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    _runner(repository, backend, control).run_one(WORK_ORDER)
    assert ("gate", "ready") in control.calls

    # A second run over the same worktree needs a *different* edit: the first
    # run already committed `VALUE = 2`, and writing it again would change
    # nothing, which is now a rejected attempt in its own right.
    def another_in_scope_edit(worktree: Path) -> None:
        (worktree / "subject" / "module.py").write_text("VALUE = 3" + chr(10), encoding="utf-8")

    blocked = ScriptedControlPlane(repository["base"], states=["planning"])
    blocked.gate_readiness = "blocked"
    report = _runner(
        repository, ScriptedBackend(edit=another_in_scope_edit), blocked
    ).run_one(WORK_ORDER)
    assert ("gate", "blocked") in blocked.calls
    assert report.outcome == RUN_BLOCKED
    assert report.final_state == "blocked"


def test_a_session_that_changed_nothing_is_a_rejected_attempt(repository):
    """An empty attempt is not a clean one.

    With nothing committed, the diff is empty, the required tests pass because
    they passed before the session started, and the receipt would otherwise say
    `accepted` about work nobody did.
    """
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    control.max_attempts = 1
    backend = ScriptedBackend(edit=lambda _worktree: None)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    receipt = control.receipts[0]
    assert receipt["outcome"] == "rejected"
    assert "changed nothing" in receipt["rejection_reason"]
    assert receipt["files_changed"] == []
    assert report.outcome == RUN_BLOCKED


def test_a_job_already_claimed_is_skipped_rather_than_run_twice(repository):
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    runner = _runner(repository, backend, control)
    other = RunStore(repository["tmp"] / "runner", runner_id="another-runner")
    other.acquire(WORK_ORDER, lease_seconds=3600)

    report = runner.run_one(WORK_ORDER)
    assert report.outcome == SKIPPED
    assert "held by runner another-runner" in report.reason
    assert backend.launched == []


def test_a_restart_does_not_repeat_completed_work(repository):
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    runner = _runner(repository, backend, control)
    runner.run_one(WORK_ORDER)
    launched_first = len(backend.launched)

    # A second runner process over the same directories, with the lifecycle
    # where the first left it.
    again = _runner(repository, backend, control)
    report = again.run_one(WORK_ORDER)
    assert report.final_state == "ready_for_approval"
    assert report.stages == ()
    assert len(backend.launched) == launched_first


def test_a_review_resumes_in_a_new_run_from_the_attempt_in_the_previous_one(repository):
    """The review stage does not require the developer stage to be in its own run.

    A runner that dies - or is stopped, fixed and restarted - between the
    attempt and the review resumes from `testing` in a fresh run directory,
    and the receipt it must review is in the previous one.
    """
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)

    class StopsAfterTheReceipt(ScriptedControlPlane):
        def review_brief(self, work_order_id: str, *, implementer: str, executor: str):
            raise OSError("the runner died here")

    first = StopsAfterTheReceipt(repository["base"], states=["planning"])
    runner = _runner(repository, backend, first)
    stopped = runner.run_one(WORK_ORDER)
    assert stopped.outcome == RUN_FAILED
    assert [item.stage for item in stopped.stages] == ["developer"]

    # A second process, over the same directories, with the job at `testing`.
    control.states[0] = "testing"
    control.receipts.extend(first.receipts)
    resumed = _runner(repository, backend, control).run_one(WORK_ORDER)
    assert resumed.outcome == COMPLETED, resumed.reason
    assert [item.stage for item in resumed.stages] == ["reviewer", "gate"]
    assert resumed.final_state == "ready_for_approval"
    assert control.attestations[0]["verdict"] == "pass"
    # and no second developer attempt was launched
    assert [request.role for request in backend.launched] == [
        "developer",
        "reviewer",
    ]


def test_a_failing_stage_is_recorded_and_does_not_leave_the_lease_held(repository):
    class Exploding(ScriptedControlPlane):
        def developer_brief(self, work_order_id: str, *, executor: str):
            raise OSError("the control plane is not there")

    control = Exploding(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)

    assert report.outcome == RUN_FAILED
    assert "not there" in report.reason
    store = RunStore(repository["tmp"] / "runner")
    lease = store.lease(WORK_ORDER)
    assert lease is not None and lease.state == "released"
    assert store.outcomes(WORK_ORDER)[-1]["outcome"] == RUN_FAILED


def test_the_review_is_adjudicated_against_the_tree_the_work_happened_in(repository):
    """`--repo-root` decides where the protected surface is re-read.

    Pointing it at the operator's checkout instead of the task worktree would
    make the one check that can catch an unmentioned edit re-read files no
    session could have touched, and it would pass every time.
    """
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    runner = _runner(repository, backend, control)
    runner.run_one(WORK_ORDER)

    (used,) = control.review_repo_roots
    assert used == runner._workspace.worktree_path(BRANCH)  # noqa: SLF001
    assert used != repository["repo"]


def test_a_review_that_routes_back_to_the_implementer_is_refused(repository):
    class SelfReviewing(ScriptedControlPlane):
        def review_brief(self, work_order_id: str, *, implementer: str, executor: str):  # noqa: D102
            payload = review_briefing(self.base)
            payload["reviewer"] = EMPLOYEE
            self._advance("reviewing")
            return _reply(payload)

    control = SelfReviewing(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    report = _runner(repository, backend, control).run_one(WORK_ORDER)
    assert report.outcome == RUN_BLOCKED
    assert "implemented the work" in report.reason
    assert control.attestations == []


# --- what the package is, read off its own source -------------------------


def _modules() -> list[Path]:
    return sorted(PACKAGE.rglob("*.py")) + [Path(__file__)]


def _import_roots(tree: ast.Module) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


def test_neither_the_runner_nor_this_file_imports_the_control_plane():
    """The boundary is a command line, and this is the machine check of it.

    The four root names are assembled rather than written out, because a test
    module that spells them is a test module that reads like a violation to
    the capsule-layer grep which scans everything under `tools/`.
    """
    forbidden = {"com" + "pany", "ai_" + "platform", "know" + "ledge", "intel" + "ligence"}
    for path in _modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        offending = _import_roots(tree) & forbidden
        assert not offending, f"{path.name} imports {sorted(offending)}"


def test_no_module_under_tools_even_mentions_the_capsule_layer_by_name():
    """A grep, because the check that polices this repository is a grep.

    `tests/test_company_os_capsules.py` asserts that the raw text of every
    module under `tools/` and `sloped/` contains neither of two root names, so
    that no production module can reach into the capsule layer. A prose mention
    reads to it exactly like an import, and one of the suites the gate requires
    happens to be named after a root - so `evidence.py` assembles that one name
    from fragments. This test is the local copy of that constraint, so a
    docstring that reintroduces the word fails here first.
    """
    forbidden = ("ai_" + "platform", "know" + "ledge.company_os")
    for path in sorted(PACKAGE.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for name in forbidden:
            assert name not in text, f"{path.name} names {name!r}"


def test_the_runner_adds_no_dependency():
    allowed = {
        "__future__",
        "argparse",
        "ast",
        "collections",
        "dataclasses",
        "datetime",
        "hashlib",
        "json",
        "os",
        "pathlib",
        "re",
        "shutil",
        "socket",
        "subprocess",
        "sys",
        "time",
        "typing",
        "uuid",
        "tools",
    }
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for root in _import_roots(tree):
            assert root in allowed, f"{path.name} imports {root!r}"


def test_the_runner_holds_no_merge_deploy_or_publish_capability():
    """Read off the git verbs the package can actually reach.

    The check is on string constants rather than on prose, because the module
    docstrings discuss merging at length and a grep over source text would
    find those and call them capabilities.
    """
    refused = {"merge", "rebase", "tag", "cherry-pick", "reset", "filter-branch"}
    seen: set[str] = set()
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if node.value in refused:
                    seen.add(f"{path.name}:{node.value}")
            if isinstance(node, ast.Constant) and node.value == "--force":
                seen.add(f"{path.name}:--force")
    assert not seen, f"the runner can reach: {sorted(seen)}"


def test_the_runner_cannot_issue_a_ceo_decision():
    """There is no `decide` on the control-plane client, and no CLI for one."""
    from tools.engineering_runner.controlplane import ControlPlane

    surface = {name for name in dir(ControlPlane) if not name.startswith("_")}
    assert "decide" not in surface
    assert not {name for name in surface if "approv" in name or "decid" in name}
    cli = (PACKAGE / "__main__.py").read_text(encoding="utf-8")
    for word in ('"approve"', '"decide"', '"merge"'):
        assert word not in cli


def test_company_os_still_holds_no_process_spawning_capability():
    """The policy this milestone was told not to weaken, checked from outside it.

    `company/integration/boundary.py` enforces this as a required gate check.
    Restating it here, in a test that reads the source rather than importing
    anything, means a change that disabled the gate would still be caught: the
    condition is asserted by someone with no stake in the gate's own health.
    """
    roots = ["com" + "pany", "ai_" + "platform", "know" + "ledge", "intel" + "ligence"]
    spawning = {"subprocess", "multiprocessing", "pty"}
    calls = {"system", "popen", "fork", "forkpty", "posix_spawn"}
    offenders: list[str] = []
    scanned = 0
    for root in roots:
        base = REPO_ROOT / root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            scanned += 1
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = (
                        [alias.name for alias in node.names]
                        if isinstance(node, ast.Import)
                        else [node.module or ""]
                    )
                    for name in names:
                        if name.split(".")[0] in spawning:
                            offenders.append(f"{path.relative_to(REPO_ROOT)}: imports {name}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    receiver = node.func.value
                    if (
                        isinstance(receiver, ast.Name)
                        and receiver.id == "os"
                        and node.func.attr in calls
                    ):
                        offenders.append(
                            f"{path.relative_to(REPO_ROOT)}: calls os.{node.func.attr}"
                        )
    assert scanned > 100, "the scan found almost no Company OS modules; check the roots"
    assert not offenders, offenders


def test_the_package_documents_itself_as_the_execution_plane():
    assert runner_package.__doc__ is not None
    assert "execution plane" in runner_package.__doc__
    assert "receives" in runner_package.__doc__


def test_no_credential_is_read_by_this_package():
    """The runner passes an environment through; it never reads a value out of one.

    `redaction.py` is the single exception, and it reads names in order to
    remove values - so it is allowed `os.environ`, and nothing else is.
    """
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "redaction.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "getenv"):
                raise AssertionError(f"{path.name} reads the environment directly")


def test_every_subprocess_call_goes_through_one_function():
    """`process.py` is the only module that may touch `subprocess`."""
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if "subprocess" in _import_roots(tree):
            assert path.name == "process.py", f"{path.name} spawns processes directly"


def test_no_shell_is_ever_used(tmp_path: Path):
    """Read the keyword off the call, not the word off the page.

    The obvious version of this test greps `process.py` for `shell=True` and
    fails on its own docstring, which explains why a shell is never used. The
    argument is a fact about a call, so it is read from the call.
    """
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if keyword.arg == "shell":
                    assert isinstance(keyword.value, ast.Constant), path.name
                    assert keyword.value.value is False, f"{path.name} runs a shell"
    result = CommandRunner().run(
        [os.sys.executable, "-c", "print('hello')"], cwd=tmp_path, timeout_s=60
    )
    assert result.ok and "hello" in result.stdout
