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
import sys
import threading
import time
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
from tools.engineering_runner.backends import (
    ClaudeCodeBackend,
    SessionOutcome,
    SessionRequest,
    normalise_claude_usage,
)
from tools.engineering_runner.briefs import developer_instructions, review_instructions
from tools.engineering_runner.repo_map import build_repo_map
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
    declared_dependencies,
    dependencies_added,
    manifest_changes,
    parse_json_object,
    suite_evidence,
)
from tools.engineering_runner.evidence import _usage
from tools.engineering_runner.process import CommandResult, CommandRunner
from tools.engineering_runner.queue import LEASE_NAME, RunStore, utcnow
from tools.engineering_runner.redaction import (
    REDACTED,
    Redactor,
    child_environment,
    forwarded_names,
    sanitize_json_file,
)
from tools.engineering_runner.resources import (
    ResourceStrategy,
    failure_detail,
    summarise_command,
)
from tools.engineering_runner.runner import (
    COMPLETED,
    MAX_STAGES_PER_RUN,
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
    # The project's one dependency manifest. It is here rather than in the
    # tests that need it because `dependencies_added` is measured against the
    # authorized base commit, and a manifest that first appears in the attempt
    # would make every name in it an addition.
    (repo / "requirements.txt").write_text(BASE_REQUIREMENTS, encoding="utf-8")
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
        "efficiency": efficiency_block(),
    }


def efficiency_block(**changes: Any) -> dict[str, Any]:
    """The resource-strategy artifact, in the shape `company.engineering` emits.

    A real briefing always carries one, and the runner refuses a briefing that
    does not - so the fixture carries one too. A fixture that omitted it would
    be testing a payload production cannot produce.
    """
    block: dict[str, Any] = {
        "artifact_version": 1,
        "profile": "consumer",
        "model_tier": "standard",
        "escalation": "none",
        "reasoning_class": "C",
        "context_budget_chars": 32000,
        "checkpoint_threshold_chars": 22400,
        "checkpoint_rule": "continue_if_under_budget",
        "output_reduction": {
            "omit_passing_test_detail": True,
            "max_test_failure_lines": 50,
            "max_log_lines": 100,
            "omit_clean_git_detail": True,
            "scope_file_listings": True,
        },
        "resource_ceiling": {
            "max_turns": 40,
            "max_wall_seconds": 1800,
            "max_session_cost": "3.00",
            "cost_currency": "USD",
            "escalation_message": "Stop and report progress.",
        },
        "provider_count": 1,
        "parallel_sessions": 1,
        "packet_attempt": 1,
        "profile_terms": {
            "name": "consumer",
            "developer_attempts": 1,
            "stage_ceiling": 4,
            "context_ref_ceiling": 8,
        },
        "context": {"refs": ["module_contract:subject"], "ref_count": 1},
        "strategy_reason": "reasoning class C at risk medium is routine implementation",
    }
    block.update(changes)
    return block


def review_briefing(base: str, *, allowed: Sequence[str] = ("subject",)) -> dict[str, Any]:
    payload = developer_briefing(base, allowed=allowed)
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


def test_developer_instructions_work_with_no_repo_map_at_all():
    """A missing map degrades the briefing, never stops the session."""
    envelope = AuthorityEnvelope.parse(developer_briefing("a" * 40))
    instructions = developer_instructions(
        envelope, report_path=Path("report.json"), worktree=Path("worktree"), attempt=1, repo_map=None
    )
    assert "Authorized engineering work order" in instructions
    assert "Execution context" not in instructions


def test_review_instructions_work_with_no_repo_map_at_all():
    envelope = AuthorityEnvelope.parse(review_briefing("a" * 40))
    instructions = review_instructions(
        envelope,
        diff_path=Path("diff.patch"),
        worktree=Path("worktree"),
        receipt={"files_changed": ["subject/module.py"]},
        developer_report={"summary": "x"},
        repo_map=None,
    )
    assert "Independent review" in instructions
    assert "Execution context" not in instructions


def test_a_briefing_never_injects_the_whole_repo_map(tmp_path: Path):
    """The map itself, never handed to a session - only a bounded, ranked slice.

    Twenty unrelated modules exist in the map; the authorized one is the only
    file the briefing may name in full, and none of the other nineteen
    modules' own distinctive symbol names should leak into the text.
    """
    (tmp_path / "subject").mkdir()
    (tmp_path / "subject" / "module.py").write_text(
        "def authorized_marker_symbol():\n    return 1\n", encoding="utf-8"
    )
    unrelated_markers = []
    for index in range(19):
        marker = f"unrelated_marker_symbol_{index}"
        unrelated_markers.append(marker)
        (tmp_path / "subject" / f"other_{index}.py").write_text(
            f"def {marker}():\n    return {index}\n", encoding="utf-8"
        )
    repo_map = build_repo_map(tmp_path, roots=("subject",))
    assert len(repo_map.modules) == 20
    envelope = AuthorityEnvelope.parse(
        developer_briefing("a" * 40, allowed=["subject/module.py"])
    )
    instructions = developer_instructions(
        envelope,
        report_path=Path("report.json"),
        worktree=tmp_path,
        attempt=1,
        repo_map=repo_map,
    )
    assert "authorized_marker_symbol" in instructions
    leaked = [marker for marker in unrelated_markers if marker in instructions]
    assert leaked == [], f"unrelated modules leaked into the briefing: {leaked}"


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
    assert second.max_cost == first.max_cost
    assert second.timeout_s == first.timeout_s
    assert second.allowed_tools == first.allowed_tools
    assert second.disallowed_tools == first.disallowed_tools


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
    assert env["PYTHONIOENCODING"] == "utf-8"


def test_a_child_writes_utf8_that_survives_the_capture(tmp_path: Path):
    """The CEO page is evidence, and an em dash came back as a replacement char.

    Output is captured as UTF-8; a Python child on Windows writes its stdout in
    the console codepage unless told otherwise. `PYTHONIOENCODING` is what makes
    the capture round-trip, and it is set for every child rather than for the
    one call that noticed.
    """
    dash = chr(8212)
    program = "print('targeted: 1/1 " + dash + " 100 passed')"
    result = CommandRunner().run(
        [os.sys.executable, "-c", program], cwd=tmp_path, timeout_s=60
    )
    assert result.ok
    assert dash in result.stdout
    assert chr(65533) not in result.stdout  # U+FFFD, the replacement character


# --- the loop, with a scripted control plane ------------------------------


class ScriptedControlPlane:
    """A stand-in that answers like `company.engineering` and records what it was asked."""

    def __init__(
        self,
        base: str,
        *,
        states: list[str],
        allowed: Sequence[str] = ("subject",),
        efficiency: Mapping[str, Any] | None = None,
    ) -> None:
        self.base = base
        self.states = states
        self.allowed = tuple(allowed)
        # What the real control plane varies per work order: the resource
        # strategy. A stand-in with a fixed one could not exercise routing.
        self.efficiency = dict(efficiency or {})
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
        return _reply(self._brief(developer_briefing(self.base, allowed=self.allowed)))

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
        return _reply(self._brief(review_briefing(self.base, allowed=self.allowed)))

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

    def _brief(self, payload: dict[str, Any]) -> dict[str, Any]:
        for key, value in self.efficiency.items():
            if isinstance(value, Mapping) and isinstance(payload["efficiency"].get(key), dict):
                payload["efficiency"][key].update(value)
            else:
                payload["efficiency"][key] = value
        return payload

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

    def __init__(
        self,
        *,
        edit: Any = None,
        report: Mapping[str, Any] | None = None,
        exploration: Mapping[str, Any] | None = None,
        exploration_events: tuple[Mapping[str, Any], ...] = (),
    ) -> None:
        self.name = "claude_code"
        self.edit = edit
        self.report = report
        self.exploration = exploration
        self.exploration_events = exploration_events
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
            exploration=self.exploration,
            exploration_events=self.exploration_events,
        )


def _runner(
    repository: dict[str, Any],
    backend: ScriptedBackend,
    control: ScriptedControlPlane,
    **settings: Any,
):
    tmp = repository["tmp"]
    config = RunnerConfig(
        repo_root=repository["repo"],
        state_dir=tmp / "state",
        runner_dir=tmp / "runner",
        worktree_root=tmp / "worktrees",
        push=True,
        **settings,
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


def _adds_a_dependency(worktree: Path) -> None:
    _in_scope_edit(worktree)
    (worktree / "requirements.txt").write_text(
        BASE_REQUIREMENTS + "requests>=2.31\n", encoding="utf-8"
    )


def _bumps_a_version(worktree: Path) -> None:
    _in_scope_edit(worktree)
    (worktree / "requirements.txt").write_text(
        BASE_REQUIREMENTS.replace("pytest>=8.0", "pytest>=8.2"), encoding="utf-8"
    )


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

    # A work order with three authorized attempts is not a consumer-mode work
    # order: consumer mode authorizes one, and the first changes_required is
    # already the last. The loop under test is the expanded profile's, so the
    # briefing carries the expanded profile's terms - including a stage ceiling
    # that has room for it.
    control = ScriptedControlPlane(
        repository["base"],
        states=["planning"],
        efficiency={
            "profile": "expanded",
            "profile_terms": {
                "name": "expanded",
                "developer_attempts": 3,
                "stage_ceiling": 12,
                "context_ref_ceiling": 20,
            },
        },
    )
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


# --- the backends ----------------------------------------------------------

# A real `codex exec` session on a CLI older than the only model the account
# has. Kept verbatim (minus the timestamps) because every property this test
# asserts is a property of exactly this output: the prompt is echoed back, the
# process exits 0, and the refusal is only in the body.
CODEX_REFUSED_TRANSCRIPT = """
OpenAI Codex v0.42.0 (research preview)
--------
workdir: C:/repo
model: gpt-5.6-sol
provider: openai
approval: never
sandbox: read-only
--------
User instructions:
Add 19 and 23. Reply with the word OK immediately followed by the result, as one token, and nothing else.

stream error: unexpected status 400 Bad Request: {"detail":"The 'gpt-5.6-sol' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again."}; retrying 1/5 in 197ms
ERROR: unexpected status 400 Bad Request: {"detail":"The 'gpt-5.6-sol' model requires a newer version of Codex. Please upgrade to the latest app or CLI and try again."}
"""


class CannedRunner(CommandRunner):
    """A command runner that answers with a fixed transcript and exit code."""

    def __init__(self, stdout: str, exit_code: int = 0) -> None:
        super().__init__()
        self._stdout = stdout
        self._exit_code = exit_code
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, *, cwd, timeout_s, env=None, stdin=None):
        from tools.engineering_runner.process import CommandResult

        self.calls.append(tuple(str(item) for item in argv))
        return CommandResult(
            argv=tuple(str(item) for item in argv),
            cwd=str(cwd),
            exit_code=self._exit_code,
            stdout=self._stdout,
            stderr="",
            duration_s=0.01,
        )


def test_a_refused_codex_session_is_not_reported_as_an_available_backend():
    """The false positive this test exists for was real, and shipped for an hour.

    `codex exec` writes its own prompt back under `User instructions:` and
    exits 0 even when every request in the session was refused. A probe that
    asked for a word and looked for that word therefore found its own question
    and reported the backend working - on a machine where it could not complete
    a single call.
    """
    from tools.engineering_runner.backends import (
        CODEX_PROBE_EXPECTED,
        CODEX_PROBE_PROMPT,
        CodexBackend,
    )

    # The transcript contains the prompt, and does not contain the answer.
    assert CODEX_PROBE_PROMPT in CODEX_REFUSED_TRANSCRIPT
    assert CODEX_PROBE_EXPECTED not in CODEX_REFUSED_TRANSCRIPT.replace(" ", "")

    runner = CannedRunner(CODEX_REFUSED_TRANSCRIPT, exit_code=0)
    backend = CodexBackend(runner, executable="python")
    available, detail = backend.available()
    assert available is False
    assert "400" in detail or "newer version" in detail


def test_a_codex_session_that_answers_the_probe_is_available():
    from tools.engineering_runner.backends import CodexBackend

    lines = ["User instructions:", "Add 19 and 23...", "", "codex", "OK42"]
    runner = CannedRunner(chr(10).join(lines))
    available, detail = backend_detail = CodexBackend(runner, executable="python").available()
    assert available is True, detail
    assert backend_detail[1]


def test_a_refused_codex_session_raises_rather_than_returning_an_outcome():
    from tools.engineering_runner.backends import CodexBackend
    from tools.engineering_runner.errors import BackendFailure

    runner = CannedRunner(CODEX_REFUSED_TRANSCRIPT, exit_code=0)
    backend = CodexBackend(runner, executable="python")
    with pytest.raises(BackendFailure, match="did not complete"):
        backend.launch(
            SessionRequest(
                role="reviewer",
                cwd=Path.cwd(),
                instructions="review this",
                timeout_s=60,
                read_only=True,
            )
        )


def test_the_runner_refuses_to_start_a_stage_on_an_unavailable_backend(repository):
    class Unavailable(ScriptedBackend):
        def available(self) -> tuple[bool, str]:
            return False, "the CLI is older than the only model this account has"

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    report = _runner(repository, Unavailable(), control).run_one(WORK_ORDER)
    assert report.outcome == RUN_FAILED
    assert "older than the only model" in report.reason
    assert control.receipts == []


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
        # stdlib, and the right type for money: a session cost ceiling
        # compared as a float would round a cent into a breach.
        "decimal",
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


# --- the lease, under real contention --------------------------------------
#
# The claim used to be that `O_EXCL` made the lease exclusive. It did not, and
# the way to find that out was never a sequential call - every sequential call
# passed. These run real simultaneous contenders and count grants, because the
# defect only exists in the window between two operations and a test that never
# opens that window cannot see it.
#
# Measured on the code these replaced, 20 trials x 8 threads: 75 grants where
# 20 were expected for a never-before-seen work order, 160 for a released one,
# 160 for a stale one, and 157 for one whose metadata did not parse.

RACE_TRIALS = 20
RACE_CONTENDERS = 8


def _contend(root: Path, *, lease_seconds: float = 3600.0, contenders: int = RACE_CONTENDERS):
    """Let `contenders` threads reach `acquire` together. Returns the winners."""
    barrier = threading.Barrier(contenders)
    won: list[str] = []
    lock = threading.Lock()

    def claim(index: int) -> None:
        store = RunStore(root, runner_id=f"contender-{index}")
        barrier.wait()
        try:
            lease, _ = store.acquire(WORK_ORDER, lease_seconds=lease_seconds)
        except ClaimUnavailable:
            return
        with lock:
            won.append(lease.runner_id)

    threads = [threading.Thread(target=claim, args=(i,)) for i in range(contenders)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return won


def _trials(tmp_path: Path, prepare, *, lease_seconds: float = 3600.0) -> list[int]:
    """`RACE_TRIALS` independent races over a freshly prepared runner directory."""
    counts = []
    for trial in range(RACE_TRIALS):
        root = tmp_path / f"trial-{trial:03d}"
        root.mkdir()
        prepare(root)
        counts.append(len(_contend(root, lease_seconds=lease_seconds)))
    return counts


def _backdate(store: RunStore, hours: float = 3.0) -> None:
    """Make the current holder's heartbeat old, without waiting for a clock.

    Not `lease_seconds=0`: that makes the winner's own brand-new lease stale
    too, so each contender supersedes the last and the count measures the
    clock rather than the lock.
    """
    path = store.lease_path(WORK_ORDER)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["heartbeat_at"] = (utcnow() - dt.timedelta(hours=hours)).isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")


def test_many_contenders_for_a_new_work_order_produce_exactly_one_winner(tmp_path: Path):
    counts = _trials(tmp_path, lambda root: None)
    assert counts == [1] * RACE_TRIALS, counts
    assert sum(counts) == RACE_TRIALS


def test_a_fresh_lease_admits_no_additional_winner(tmp_path: Path):
    def prepare(root: Path) -> None:
        RunStore(root, runner_id="holder").acquire(WORK_ORDER, lease_seconds=3600)

    counts = _trials(tmp_path, prepare)
    assert counts == [0] * RACE_TRIALS, counts


def test_a_released_lease_admits_exactly_one_new_winner(tmp_path: Path):
    def prepare(root: Path) -> None:
        store = RunStore(root, runner_id="holder")
        lease, _ = store.acquire(WORK_ORDER, lease_seconds=3600)
        store.release(lease)

    counts = _trials(tmp_path, prepare)
    assert counts == [1] * RACE_TRIALS, counts


def test_a_stale_lease_admits_exactly_one_reclaimer(tmp_path: Path):
    def prepare(root: Path) -> None:
        store = RunStore(root, runner_id="holder")
        store.acquire(WORK_ORDER, lease_seconds=3600)
        _backdate(store)

    counts = _trials(tmp_path, prepare)
    assert counts == [1] * RACE_TRIALS, counts


@pytest.mark.parametrize("body", ["", "{ not json", "[]", "null"])
def test_a_lease_whose_metadata_cannot_be_read_is_held_rather_than_won(
    tmp_path: Path, body: str
):
    """The crash case, and the one the old code got backwards.

    An empty or unparseable lease is exactly what a winner looks like in the
    instant before it writes its metadata. Reading that as "the holder is
    broken, therefore I won" is what let eight threads all claim one work
    order. Inside the lease window the answer is that somebody holds it.
    """

    def prepare(root: Path) -> None:
        store = RunStore(root, runner_id="holder")
        store.acquire(WORK_ORDER, lease_seconds=3600)
        store.lease_path(WORK_ORDER).write_text(body, encoding="utf-8")

    counts = _trials(tmp_path, prepare)
    assert counts == [0] * RACE_TRIALS, counts


def test_a_lease_that_has_sat_without_metadata_for_a_whole_window_is_reclaimed_once(
    tmp_path: Path,
):
    """And the recovery rule is not "never": a crash must not wedge a job forever.

    `lease_seconds` measured against the directory's own mtime, because the
    case being answered is precisely the one where nothing was written.
    """

    def prepare(root: Path) -> None:
        store = RunStore(root, runner_id="holder")
        store.acquire(WORK_ORDER, lease_seconds=3600)
        owned = store.lease_path(WORK_ORDER).parent
        owned.joinpath(LEASE_NAME).unlink()
        # Age the directory rather than shrinking the window: a window small
        # enough to age this one ages the winner's own lease too, and the count
        # would then measure the clock instead of the lock.
        old = (utcnow() - dt.timedelta(hours=3)).timestamp()
        os.utime(owned, (old, old))

    counts = _trials(tmp_path, prepare)
    assert counts == [1] * RACE_TRIALS, counts


def test_ownership_is_the_directory_and_the_metadata_only_describes_it(tmp_path: Path):
    """An empty ownership directory nobody wrote into still excludes everyone.

    This is the property the fix rests on: the claim is one `mkdir`, so there
    is no instant at which a work order is owned and the filesystem does not
    say so.
    """
    store = RunStore(tmp_path, runner_id="runner-one")
    lease, _ = store.acquire(WORK_ORDER, lease_seconds=3600)
    owned = store.lease_path(WORK_ORDER).parent
    assert owned.name == "lease-000001"
    assert lease.generation == 1

    (store.job_dir(WORK_ORDER) / "lease-000002").mkdir()
    with pytest.raises(ClaimUnavailable, match="no readable metadata"):
        RunStore(tmp_path, runner_id="runner-two").acquire(WORK_ORDER, lease_seconds=3600)


def test_a_superseded_runner_cannot_write_over_the_lease_that_replaced_it(tmp_path: Path):
    """A stale holder keeps running until it notices. It must not scribble.

    Its heartbeat and its release address the generation it owns, which nobody
    reads any more - not the generation of the runner that took the job.
    """
    first = RunStore(tmp_path, runner_id="runner-one")
    lease, _ = first.acquire(WORK_ORDER, lease_seconds=3600)
    _backdate(first)
    second = RunStore(tmp_path, runner_id="runner-two")
    taken, how = second.acquire(WORK_ORDER, lease_seconds=3600)
    assert "stale" in how and taken.reclaimed_from == "runner-one"

    first.heartbeat(lease, stage="still going")
    first.release(lease)

    current = second.lease(WORK_ORDER)
    assert current is not None
    assert current.runner_id == "runner-two"
    assert current.state == "held"


def test_a_lease_written_by_the_previous_layout_is_respected_then_superseded(
    tmp_path: Path,
):
    """An upgrade must not claim a job an older runner is still working."""
    store = RunStore(tmp_path, runner_id="runner-two")
    job = store.job_dir(WORK_ORDER)
    job.mkdir(parents=True)
    legacy = {
        "work_order_id": WORK_ORDER,
        "runner_id": "runner-one",
        "pid": 4321,
        "host": "old-machine",
        "state": "held",
        "acquired_at": utcnow().isoformat(),
        "heartbeat_at": utcnow().isoformat(),
    }
    (job / "lease.json").write_text(json.dumps(legacy), encoding="utf-8")

    with pytest.raises(ClaimUnavailable, match="runner-one"):
        store.acquire(WORK_ORDER, lease_seconds=3600)

    legacy["heartbeat_at"] = (utcnow() - dt.timedelta(hours=3)).isoformat()
    (job / "lease.json").write_text(json.dumps(legacy), encoding="utf-8")
    taken, how = store.acquire(WORK_ORDER, lease_seconds=3600)
    assert "stale" in how
    assert taken.generation == 1


def test_separate_processes_racing_one_runner_directory_produce_one_winner(tmp_path: Path):
    """Threads prove the syscall is atomic; processes prove the claim it backs.

    Each child blocks on a file that does not exist yet, so they reach
    `acquire` together rather than in start-up order.
    """
    root = tmp_path / "runner"
    root.mkdir()
    go = tmp_path / "go"
    script = tmp_path / "contend.py"
    script.write_text(
        "import sys, time\n"
        f"sys.path.insert(0, {str(REPO_ROOT)!r})\n"
        "from pathlib import Path\n"
        "from tools.engineering_runner.queue import RunStore\n"
        "from tools.engineering_runner.errors import ClaimUnavailable\n"
        f"go = Path({str(go)!r})\n"
        "deadline = time.monotonic() + 60\n"
        "while not go.exists() and time.monotonic() < deadline:\n"
        "    pass\n"
        f"store = RunStore(Path({str(root)!r}), runner_id=sys.argv[1])\n"
        "try:\n"
        f"    store.acquire({WORK_ORDER!r}, lease_seconds=3600)\n"
        "except ClaimUnavailable:\n"
        "    print('LOST')\n"
        "else:\n"
        "    print('WON')\n",
        encoding="utf-8",
    )
    children = [
        subprocess.Popen(
            [sys.executable, str(script), f"process-{index}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index in range(6)
    ]
    time.sleep(1.5)
    go.write_text("go", encoding="utf-8")
    results = [child.communicate(timeout=120) for child in children]
    for out, err in results:
        assert "Traceback" not in err, err
    assert [out.strip() for out, _ in results].count("WON") == 1


def test_a_job_the_ceo_already_holds_runs_no_stage(repository):
    """`ready_for_approval` is not actionable, so a completed job is not re-run."""
    control = ScriptedControlPlane(repository["base"], states=["ready_for_approval"])
    backend = ScriptedBackend(edit=_in_scope_edit)
    runner = _runner(repository, backend, control)

    report = runner.run_one(WORK_ORDER)
    assert report.stages == ()
    assert backend.launched == []
    assert report.final_state == "ready_for_approval"


# --- what a child process is given -----------------------------------------


CREDENTIAL_SHAPED = {
    "BINANCE_API_KEY": "SYNTHETIC-binance-key-0123456789",
    "BINANCE_API_SECRET": "SYNTHETIC-binance-secret-0123456789",
    "CLAUDE_CODE_MESSAGING_TOKEN": "SYNTHETIC-messaging-token-0123456789",
    "GITHUB_TOKEN": "SYNTHETIC-github-token-0123456789",
    "STRIPE_SECRET_KEY": "SYNTHETIC-stripe-key-0123456789",
}


def test_an_unrelated_credential_is_not_given_to_a_coding_session():
    """The finding, restated as a test. None of these is in any work order."""
    env = child_environment({"PATH": "/x", **CREDENTIAL_SHAPED})
    for name in CREDENTIAL_SHAPED:
        assert name not in env
    assert env["PATH"] == "/x"


def test_a_claude_code_prefix_is_not_a_reason_to_forward_a_variable():
    """Why the backend list is names and not a prefix.

    `CLAUDE_CODE_MESSAGING_TOKEN` shares its prefix with every Claude Code
    setting and is a credential; `CLAUDE_CODE_OAUTH_TOKEN` shares it and is the
    backend's own. A prefix rule cannot tell them apart, so there is none.
    """
    env = child_environment(
        {
            "CLAUDE_CODE_MESSAGING_TOKEN": "SYNTHETIC-messaging-0123456789",
            "CLAUDE_CODE_OAUTH_TOKEN": "SYNTHETIC-oauth-0123456789",
        }
    )
    assert "CLAUDE_CODE_MESSAGING_TOKEN" not in env
    assert "CLAUDE_CODE_OAUTH_TOKEN" in env


def test_the_backends_own_authentication_still_reaches_it():
    """Removing an auth variable the backend needs would break every session."""
    source = {
        "ANTHROPIC_API_KEY": "SYNTHETIC-anthropic-0123456789",
        "ANTHROPIC_BASE_URL": "https://example.invalid",
        "OPENAI_API_KEY": "SYNTHETIC-openai-0123456789",
        "CLAUDE_CONFIG_DIR": "/config",
    }
    env = child_environment(source)
    assert set(source) <= set(env)


@pytest.mark.parametrize(
    "switch, name",
    [
        ("CLAUDE_CODE_USE_BEDROCK", "AWS_SECRET_ACCESS_KEY"),
        ("CLAUDE_CODE_USE_VERTEX", "GOOGLE_APPLICATION_CREDENTIALS"),
    ],
)
def test_a_cloud_credential_travels_only_when_the_backend_is_routed_through_it(
    switch: str, name: str
):
    """A real credential, forwarded because a configuration needs it - not because
    it was in the shell."""
    secret = {name: "SYNTHETIC-cloud-credential-0123456789"}
    assert name not in child_environment(dict(secret))
    assert name in child_environment({switch: "1", **secret})
    assert name not in child_environment({switch: "0", **secret})


def test_the_child_keeps_what_a_process_needs_to_be_a_process():
    source = {
        "PATH": "/x",
        "SYSTEMROOT": r"C:\Windows",
        "USERPROFILE": r"C:\Users\someone",
        "APPDATA": r"C:\Users\someone\AppData\Roaming",
        "HOME": "/home/someone",
        "TEMP": "/tmp",
        "COMSPEC": r"C:\Windows\system32\cmd.exe",
        "PATHEXT": ".COM;.EXE;.CMD",
        "VIRTUAL_ENV": "/venv",
    }
    assert set(source) <= set(child_environment(source))


def test_forwarded_names_reports_names_and_never_values():
    names = forwarded_names({"PATH": "/x", **CREDENTIAL_SHAPED})
    assert names == ("PATH",)


def test_a_real_child_process_cannot_see_an_unrelated_credential(
    tmp_path: Path, monkeypatch
):
    """End to end, through the one function that spawns anything.

    The child prints the *names* it was given, never a value, and the variable
    is set on this process only for the duration of the test.
    """
    monkeypatch.setenv("SYNTHETIC_TRADING_API_KEY", "SYNTHETIC-value-0123456789")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://example.invalid")
    script = tmp_path / "names.py"
    script.write_text(
        "import os\nprint('\\n'.join(sorted(os.environ)))\n", encoding="utf-8"
    )
    result = CommandRunner().run(
        [sys.executable, str(script)], cwd=tmp_path, timeout_s=120
    )
    seen = set(result.stdout.split())
    assert "SYNTHETIC_TRADING_API_KEY" not in seen
    assert "ANTHROPIC_BASE_URL" in seen
    assert "PATH" in seen


# --- dependencies, measured rather than reported ---------------------------


BASE_REQUIREMENTS = "pymunk>=7.0\npygame>=2.6\npytest>=8.0\n"


def test_no_dependency_change_adds_nothing():
    assert dependencies_added(BASE_REQUIREMENTS, BASE_REQUIREMENTS) == ()


def test_a_reordered_requirements_file_adds_nothing():
    shuffled = "\n".join(reversed(BASE_REQUIREMENTS.strip().splitlines())) + "\n"
    assert shuffled != BASE_REQUIREMENTS
    assert dependencies_added(BASE_REQUIREMENTS, shuffled) == ()


def test_raising_a_version_floor_is_not_a_new_dependency():
    """Otherwise every routine bump becomes an architecture-and-security review."""
    bumped = BASE_REQUIREMENTS.replace("pygame>=2.6", "pygame>=2.7")
    assert dependencies_added(BASE_REQUIREMENTS, bumped) == ()


@pytest.mark.parametrize(
    "line, expected",
    [
        ("requests>=2.31\n", "requests"),
        ("uvicorn[standard]>=0.30\n", "uvicorn"),
        ('httpx>=0.27 ; python_version >= "3.11"\n', "httpx"),
        ("  # a comment\nrich==13.7.0\n", "rich"),
        ("mylib @ https://example.invalid/mylib.whl\n", "mylib"),
    ],
)
def test_a_new_requirement_is_detected_however_it_is_written(line: str, expected: str):
    assert dependencies_added(BASE_REQUIREMENTS, BASE_REQUIREMENTS + line) == (expected,)


def test_a_pip_option_line_is_not_read_as_a_dependency():
    added = dependencies_added(
        BASE_REQUIREMENTS, BASE_REQUIREMENTS + "--index-url https://example.invalid\n-r dev.txt\n"
    )
    assert added == ()


def test_the_two_facts_are_kept_apart():
    """A manifest that changed and a dependency that was added are not the same
    claim, and the policy treats them differently: scope answers the first and
    `mandatory_review_triggers.new_dependency` answers the second."""
    bumped = BASE_REQUIREMENTS.replace("pytest>=8.0", "pytest>=8.2")
    changes = manifest_changes(
        {"requirements.txt": BASE_REQUIREMENTS}, {"requirements.txt": bumped}
    )
    assert changes["manifests_changed"] == ["requirements.txt"]
    assert changes["dependencies_added"] == []


def test_a_new_dependency_reaches_the_receipt_the_runner_hands_over(repository):
    """The whole path: a session edits the manifest inside its grant, and the
    governed field is measured from git rather than taken from the report."""
    control = ScriptedControlPlane(
        repository["base"], states=["planning"], allowed=("subject", "requirements.txt")
    )
    backend = ScriptedBackend(edit=_adds_a_dependency)
    runner = _runner(repository, backend, control)

    runner.run_one(WORK_ORDER)

    receipt = control.receipts[0]
    assert receipt["dependencies_added"] == ["requests"]
    assert "requirements.txt" in receipt["files_changed"]


def test_an_authorized_manifest_change_that_adds_nothing_is_still_measured(repository):
    """Measured, and the answer is honestly empty - not silently accepted."""
    control = ScriptedControlPlane(
        repository["base"], states=["planning"], allowed=("subject", "requirements.txt")
    )
    backend = ScriptedBackend(edit=_bumps_a_version)
    runner = _runner(repository, backend, control)

    runner.run_one(WORK_ORDER)

    receipt = control.receipts[0]
    assert receipt["dependencies_added"] == []
    assert "requirements.txt" in receipt["files_changed"]
    stage = next((runner.config.runner_dir).glob("runs/*/run-*/developer*/dependencies.json"))
    assert json.loads(stage.read_text(encoding="utf-8")) == {
        "manifests_changed": ["requirements.txt"],
        "dependencies_added": [],
    }


def test_an_unauthorized_manifest_change_is_still_blocked_by_scope(repository):
    """Measuring dependencies did not open a path around `may_write`.

    The grant here does not include `requirements.txt`, so the attempt is
    refused before anything is committed and nothing is measured at all.
    """
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(edit=_adds_a_dependency)
    runner = _runner(repository, backend, control)

    report = runner.run_one(WORK_ORDER)

    assert report.outcome == RUN_BLOCKED
    receipt = control.receipts[0]
    assert receipt["outcome"] == "rejected"
    assert "requirements.txt" in receipt["rejection_reason"]
    assert receipt["dependencies_added"] == []


# --- the developer report is scrubbed where it lands ------------------------


def test_a_credential_in_a_developer_report_never_reaches_the_receipt(repository):
    """The one persisted developer channel that was not going through a redactor.

    Everything else a session produces reaches disk through `CommandRunner`,
    which scrubs on the way in. The report is written by the session to a path
    the runner names, and the receipt, the attestation and the committed
    evidence are all built out of it.
    """
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = ScriptedBackend(
        edit=_in_scope_edit,
        report={
            "outcome": "accepted",
            "summary": f"VALUE is two now; the key I found was {SENTINEL_TOKEN}",
            "invariants_preserved": ["nothing else moved"],
            "unresolved_risks": [f"an operator had ANTHROPIC_API_KEY={SENTINEL_TOKEN} set"],
            "evidence": ["subject/module.py"],
            "context_refs_used": ["module_contract:subject"],
            "notes": "the diff is one line",
        },
    )
    runner = _runner(repository, backend, control)

    runner.run_one(WORK_ORDER)

    persisted = next((runner.config.runner_dir).glob("runs/*/run-*/developer*/report.json"))
    receipt = control.receipts[0]
    for text in (persisted.read_text(encoding="utf-8"), json.dumps(receipt)):
        assert SENTINEL_TOKEN not in text
        assert REDACTED in text
    # and the diagnostics that were never the problem are still readable
    assert "VALUE is two now" in receipt["summary"]
    assert receipt["notes"] == "the diff is one line"
    assert receipt["invariants_preserved"] == ["nothing else moved"]


def test_sanitizing_a_report_leaves_it_parseable(tmp_path: Path):
    report = tmp_path / "report.json"
    report.write_text(
        json.dumps({"summary": f"used {SENTINEL_TOKEN}", "evidence": ["a.py"]}),
        encoding="utf-8",
    )
    assert sanitize_json_file(report, Redactor(environment={})) is True
    decoded = json.loads(report.read_text(encoding="utf-8"))
    assert SENTINEL_TOKEN not in json.dumps(decoded)
    assert decoded["evidence"] == ["a.py"]


def test_a_report_with_nothing_to_remove_is_left_exactly_as_it_was(tmp_path: Path):
    report = tmp_path / "report.json"
    body = json.dumps({"summary": "raised VALUE to two", "evidence": ["subject/module.py"]})
    report.write_text(body, encoding="utf-8")
    assert sanitize_json_file(report, Redactor(environment={})) is False
    assert report.read_text(encoding="utf-8") == body


# --- consumer resource mode: telemetry ------------------------------------
#
# The two envelope shapes, in the exact form the provider writes them, copied
# from real stored sessions including the numbers.


def _envelope(*, num_turns, usage, model_usage=None, cost=None):
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "num_turns": num_turns,
        "result": "done",
        "session_id": "03dff822-7d61-4865-b0b5-2efe8a35ab40",
        "usage": usage,
    }
    if cost is not None:
        payload["total_cost_usd"] = cost
    if model_usage is not None:
        payload["modelUsage"] = model_usage
    return payload


AGREEING_ENVELOPE = _envelope(
    num_turns=39,
    cost=1.740796,
    usage={
        "input_tokens": 40,
        "cache_creation_input_tokens": 75106,
        "cache_read_input_tokens": 2083217,
        "output_tokens": 9183,
    },
    model_usage={
        "claude-opus-4-6[1m]": {
            "inputTokens": 40,
            "outputTokens": 9183,
            "cacheReadInputTokens": 2083217,
            "cacheCreationInputTokens": 75106,
            "costUSD": 1.740796,
        }
    },
)

# The real one that broke the old reader. `usage` describes the final segment
# of a 1032-second session of 48 billed requests; `modelUsage` describes the
# whole thing; `total_cost_usd` agrees with `modelUsage`.
SEGMENT_ENVELOPE = _envelope(
    num_turns=1,
    cost=3.78449925,
    usage={
        "input_tokens": 3,
        "cache_creation_input_tokens": 33224,
        "cache_read_input_tokens": 121579,
        "output_tokens": 66,
    },
    model_usage={
        "claude-opus-4-6[1m]": {
            "inputTokens": 53,
            "outputTokens": 27132,
            "cacheReadInputTokens": 4276831,
            "cacheCreationInputTokens": 154803,
            "costUSD": 3.78449925,
        }
    },
)


def test_usage_is_read_from_session_totals_not_a_final_segment():
    """The measured defect, and the shape that produced it.

    One envelope, three accounts of the same session. Reading cost from the
    session-total field and tokens from the final-segment one agreed for
    nineteen sessions and then understated the twentieth by four hundred times.
    """
    usage = normalise_claude_usage(SEGMENT_ENVELOPE)
    assert usage.output_units == 27132, "the segment said 66"
    assert usage.cache_read_units == 4276831, "the segment said 121,579"
    assert usage.cache_creation_units == 154803
    assert usage.cost_usd == pytest.approx(3.78449925)
    assert usage.source == "model_usage_totals:segment_mismatch"


def test_a_turn_count_that_describes_one_segment_is_not_reported():
    """Not silently corrected, and not silently used: marked and withheld.

    The session's real turn count is not anywhere in this envelope. The old
    reader reported 1 for a session of 48 billed requests. Reporting nothing
    and saying why is the only honest answer available.
    """
    usage = normalise_claude_usage(SEGMENT_ENVELOPE)
    assert usage.turns is None
    assert "model_turns" in usage.unreliable


def test_an_agreeing_envelope_reports_its_turn_count():
    usage = normalise_claude_usage(AGREEING_ENVELOPE)
    assert usage.turns == 39
    assert usage.unreliable == ()
    assert usage.source == "model_usage_totals"
    assert usage.output_units == 9183


def test_cache_creation_is_captured():
    """It is billed separately from cache reads and was never recorded."""
    for envelope in (AGREEING_ENVELOPE, SEGMENT_ENVELOPE):
        assert normalise_claude_usage(envelope).cache_creation_units


def test_the_smaller_value_is_never_silently_preferred():
    """Two session totals that disagree mark the metric; they do not pick one.

    Preferring the smaller would turn a measurement error into a reported
    saving, which is the failure this whole milestone exists to avoid.
    """
    envelope = dict(SEGMENT_ENVELOPE)
    envelope["total_cost_usd"] = 0.01
    usage = normalise_claude_usage(envelope)
    assert "session_cost" in usage.unreliable
    assert usage.cost_usd == pytest.approx(3.78449925)


def test_an_envelope_without_model_usage_is_labelled_as_such():
    envelope = _envelope(num_turns=4, usage={"input_tokens": 1, "output_tokens": 2})
    usage = normalise_claude_usage(envelope)
    assert usage.source == "envelope_usage"
    assert usage.output_units == 2


def test_turns_are_never_recorded_as_tool_calls():
    """Two different quantities, and conflating them invented a measurement."""
    outcome = SessionOutcome(
        backend="claude_code", role="developer", session_id="s", model="m",
        exit_code=0, duration_s=1.0, result_text="", transcript="", ok=True,
        turns=39, input_units=40, output_units=9183, cache_creation_units=75106,
    )
    usage = _usage(outcome)
    assert "tool_calls" not in usage
    assert usage["model_turns"] == 39
    assert usage["cache_creation_units"] == 75106


# --- consumer resource mode: the resource strategy artifact ---------------


def test_the_runner_refuses_a_briefing_with_no_resource_strategy(repository):
    payload = developer_briefing(repository["base"])
    payload.pop("efficiency")
    with pytest.raises(IntegrityFailure, match="no resource strategy"):
        ResourceStrategy.parse(payload)


def test_the_runner_refuses_an_artifact_version_it_cannot_read(repository):
    payload = developer_briefing(repository["base"])
    payload["efficiency"]["artifact_version"] = 99
    with pytest.raises(IntegrityFailure, match="artifact version 99"):
        ResourceStrategy.parse(payload)


def test_the_runner_refuses_a_tier_it_does_not_know(repository):
    payload = developer_briefing(repository["base"])
    payload["efficiency"]["model_tier"] = "cheapest"
    with pytest.raises(IntegrityFailure, match="model tier"):
        ResourceStrategy.parse(payload)


def test_a_resource_strategy_may_not_carry_authority(repository):
    """The governance property: this artifact can only make a session smaller.

    Refused rather than ignored. A field nobody validates is how a scope gets
    widened by a payload that was never meant to carry one, and ignoring it
    leaves the widening sitting in a file somebody later decides to read.
    """
    for key in ("authorized_paths", "may_write", "allowed_tools", "authorized_branch"):
        payload = developer_briefing(repository["base"])
        payload["efficiency"][key] = ["anything"]
        with pytest.raises(IntegrityFailure, match="authority-shaped"):
            ResourceStrategy.parse(payload)


def test_the_operator_does_not_restate_the_model_for_every_job(repository):
    """The tier becomes a model in the runner, and only in the runner."""
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    assert report.outcome == COMPLETED, report.reason

    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert developer.model == "sonnet", "the standard tier, resolved by the runner"
    assert developer.timeout_s == 1800.0, "the strategy's wall ceiling, not the config's"
    assert developer.max_cost == pytest.approx(3.00)

    applied = json.loads(
        (Path(report.run_dir) / "developer-01" / "resources.json").read_text("utf-8")
    )
    assert applied["model_source"] == "tier:standard"
    assert applied["timeout_source"] == "resource_strategy"
    assert applied["cost_ceiling_enforced"] is True
    assert any("max_turns" in line for line in applied["not_enforced"])


def test_the_strongest_tier_resolves_to_the_stronger_model(repository):
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(
        repository["base"], states=["planning"], efficiency={"model_tier": "strongest"}
    )
    runner = _runner(repository, backend, control)
    runner.run_one(WORK_ORDER)
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert developer.model == "opus"


def test_an_explicit_operator_model_still_wins(repository):
    """A recommendation is a recommendation. The operator can pin one."""
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control, developer_model="haiku")
    runner.run_one(WORK_ORDER)
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert developer.model == "haiku"


def test_a_strategy_cannot_buy_a_session_more_time_than_the_runner_allows(repository):
    """The ceiling only ever tightens.

    A briefing that asked for a longer session than the operator started the
    runner with would be a Company OS record widening a runner setting, which
    is the direction authority must never travel.
    """
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(
        repository["base"],
        states=["planning"],
        efficiency={"resource_ceiling": {"max_wall_seconds": 999999}},
    )
    runner = _runner(repository, backend, control)
    runner.run_one(WORK_ORDER)
    developer = [item for item in backend.launched if item.role == "developer"][0]
    assert developer.timeout_s == 3600.0, "the runner config's own ceiling"


class _Recorder:
    def __init__(self):
        self.calls: list[list[str]] = []

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        return CommandResult(
            argv=tuple(argv),
            cwd=".",
            exit_code=0,
            stdout=json.dumps(
                {"session_id": "03dff822-7d61-4865-b0b5-2efe8a35ab40", "result": "ok"}
            ),
            stderr="",
            duration_s=0.1,
        )


def test_a_spend_ceiling_reaches_the_command_line():
    """The one live spend limit either CLI offers, actually passed."""
    recorder = _Recorder()
    backend = ClaudeCodeBackend(recorder, executable=sys.executable)
    backend._resolved = sys.executable
    outcome = backend.launch(
        SessionRequest(
            role="developer", cwd=Path("."), instructions="x",
            timeout_s=60.0, max_cost=1.5,
        )
    )
    argv = recorder.calls[0]
    assert "--max-budget-usd" in argv
    assert argv[argv.index("--max-budget-usd") + 1] == "1.5000"
    assert outcome.cost_ceiling_enforced is True


def test_no_spend_ceiling_means_no_flag_and_no_claim_of_one():
    recorder = _Recorder()
    backend = ClaudeCodeBackend(recorder, executable=sys.executable)
    backend._resolved = sys.executable
    outcome = backend.launch(
        SessionRequest(role="developer", cwd=Path("."), instructions="x", timeout_s=60.0)
    )
    assert "--max-budget-usd" not in recorder.calls[0]
    assert outcome.cost_ceiling_enforced is False


# --- consumer resource mode: checkpoints ----------------------------------


def test_a_run_that_stops_short_leaves_a_checkpoint_and_not_a_transcript(repository):
    """What the next fresh session needs, and nothing that makes it expensive.

    The continuation must be a *fresh* session. Carrying the previous
    conversation is what made a correction attempt cost more than the attempt
    it corrected: the transcript is the expensive part and almost none of it
    is load-bearing.
    """
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    control.review_outcome = "changes_required"
    control.max_attempts = 1  # what the consumer profile authorizes
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    assert report.outcome == RUN_BLOCKED, report.reason
    assert report.final_state == "decision_required"

    checkpoint_path = Path(report.run_dir) / "checkpoint.json"
    assert checkpoint_path.is_file()
    checkpoint = json.loads(checkpoint_path.read_text("utf-8"))

    assert checkpoint["work_order"]["work_order_id"] == WORK_ORDER
    assert checkpoint["work_order"]["acceptance_criteria"]
    assert checkpoint["work_order"]["authorized_paths"]
    assert checkpoint["completed_work"]["files_changed"]
    assert checkpoint["git"]["commit_sha"]
    assert "failing_tests" in checkpoint
    assert "unresolved_reviewer_findings" in checkpoint
    assert checkpoint["context_refs"]
    assert "fresh session" in checkpoint["next_session"]

    # And none of the expensive parts.
    text = json.dumps(checkpoint)
    assert "scripted transcript" not in text
    assert "transcript" not in checkpoint
    assert len(text) < 8000, "a checkpoint that is not compact is a transcript"


def test_one_developer_attempt_is_not_followed_by_a_second(repository):
    """The retry burn, stopped where the money is actually spent.

    Company OS refuses the transition, so the runner has no actionable state
    to act on and stops. Neither half is trusted to do it alone.
    """
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    control.review_outcome = "changes_required"
    control.max_attempts = 1
    runner = _runner(repository, backend, control)
    runner.run_one(WORK_ORDER)
    developer_sessions = [item for item in backend.launched if item.role == "developer"]
    assert len(developer_sessions) == 1


def test_the_profile_stage_ceiling_tightens_the_run(repository):
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    applied = json.loads(
        (Path(report.run_dir) / "developer-01" / "resources.json").read_text("utf-8")
    )
    assert applied["stage_limit"] == 4, "the consumer profile's stage ceiling"
    assert applied["stage_limit"] < MAX_STAGES_PER_RUN


def test_a_session_with_exploration_telemetry_gets_an_exploration_json(repository):
    """Repository Exploration Efficiency V2: the backend's own bounded trace
    is written beside `session.json`, never folded into it."""
    exploration = {
        "format": "stream_json",
        "file_reads_total": 4,
        "file_reads_unique": 3,
        "file_reads_repeated": 1,
        "searches_total": 2,
    }
    events = (
        {"order": 1, "tool": "Read", "category": "", "target": "subject/module.py", "repeat": False},
    )
    backend = ScriptedBackend(edit=_in_scope_edit, exploration=exploration, exploration_events=events)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    exploration_path = Path(report.run_dir) / "developer-01" / "exploration.json"
    assert exploration_path.is_file()
    written = json.loads(exploration_path.read_text("utf-8"))
    assert written["file_reads_total"] == 4
    assert written["events"][0]["target"] == "subject/module.py"


def test_no_exploration_json_is_written_when_the_backend_gave_no_trace(repository):
    """A backend that never produced exploration telemetry writes nothing -
    UNAVAILABLE stays absent, not an empty file pretending to be a measurement."""
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    exploration_path = Path(report.run_dir) / "developer-01" / "exploration.json"
    assert not exploration_path.exists()


# --- consumer resource mode: output reduction -----------------------------


def test_a_successful_command_is_one_line_and_a_failing_one_is_its_failure():
    """The honest half of output reduction: what the runner itself captures.

    Company OS cannot compress the tool output inside a coding session - that
    happens in the external CLI's own process, in a conversation nothing here
    observes. What the runner captures and puts back in front of a model is a
    different thing, and it is the only thing these reduce.
    """
    green = "\n".join(f"tests/test_{index}.py ...." for index in range(200))
    green += "\n==== 812 passed in 44.10s ===="
    summary = summarise_command("pytest", exit_code=0, stdout=green)
    assert "\n" not in summary
    assert "812 passed" in summary
    assert len(summary) * 50 < len(green)

    red = green + "\nFAILED tests/test_7.py::test_value - assert 1 == 2"
    detail = summarise_command("pytest", exit_code=1, stdout=red)
    assert "FAILED tests/test_7.py::test_value" in detail
    assert "tests/test_0.py ...." not in detail


def test_failure_detail_is_bounded_and_order_preserving():
    stdout = "\n".join(f"FAILED case {index}" for index in range(200))
    detail = failure_detail(stdout, max_lines=10)
    lines = detail.splitlines()
    assert len(lines) == 11
    assert lines[0] == "FAILED case 0"
    assert "truncated" in lines[-1]


def test_a_passing_test_run_carries_no_failure_detail(repository):
    backend = ScriptedBackend(edit=_in_scope_edit)
    control = ScriptedControlPlane(repository["base"], states=["planning"])
    runner = _runner(repository, backend, control)
    report = runner.run_one(WORK_ORDER)
    runs = json.loads(
        (Path(report.run_dir) / "developer-01" / "tests.json").read_text("utf-8")
    )["runs"]
    assert runs
    assert all(run["failure_detail"] == "" for run in runs)


def test_a_budget_stopped_stage_never_spawns_an_automatic_repair_session(repository):
    """Regression for the V4 hidden-spend incident.

    A provider resource stop is a backend stop, not malformed report JSON. The
    runner persists that paid session and stops; it must not consume the one
    structured-report repair slot.
    """

    class BudgetStopped(ScriptedBackend):
        def launch(self, request: SessionRequest) -> SessionOutcome:
            self.launched.append(request)
            self.session_ids.append(request.session_id)
            return SessionOutcome(
                backend=self.name,
                role=request.role,
                session_id=request.session_id,
                model="scripted",
                provider="anthropic",
                exit_code=0,
                duration_s=0.01,
                result_text="",
                transcript="stopped",
                ok=False,
                cost_usd=3.0,
                input_units=10,
                output_units=100,
                cache_read_units=1000,
                cache_creation_units=200,
                stopped_reason="error_max_budget_usd",
                cost_ceiling_enforced=True,
            )

    control = ScriptedControlPlane(repository["base"], states=["planning"])
    backend = BudgetStopped()
    report = _runner(repository, backend, control).run_one(WORK_ORDER)

    developer = [request for request in backend.launched if request.role == "developer"]
    assert len(developer) == 1
    assert report.outcome == RUN_FAILED
    assert "error_max_budget_usd" in report.reason

    stage = Path(report.run_dir) / "developer-01"
    assert (stage / "session-1.json").is_file()
    assert not (stage / "session-2.json").exists()
    sessions = json.loads((stage / "sessions.json").read_text("utf-8"))
    assert sessions["paid_session_count"] == 1


def test_usage_aggregates_every_paid_session_in_the_stage():
    first = SessionOutcome(
        backend="claude_code",
        role="developer",
        session_id="00000000-0000-4000-8000-000000000001",
        model="sonnet",
        provider="anthropic",
        exit_code=0,
        duration_s=2.0,
        result_text="",
        transcript="",
        ok=True,
        cost_usd=3.0,
        input_units=10,
        output_units=100,
        cache_read_units=1000,
        cache_creation_units=200,
        turns=3,
        cost_ceiling_enforced=True,
        exploration={
            "file_reads_total": 2,
            "file_reads_repeated": 1,
            "searches_total": 1,
        },
    )
    second = SessionOutcome(
        backend="claude_code",
        role="developer",
        session_id="00000000-0000-4000-8000-000000000002",
        model="sonnet",
        provider="anthropic",
        exit_code=0,
        duration_s=1.0,
        result_text="",
        transcript="",
        ok=True,
        cost_usd=0.5,
        input_units=5,
        output_units=50,
        cache_read_units=250,
        cache_creation_units=75,
        turns=2,
        cost_ceiling_enforced=True,
        exploration={
            "file_reads_total": 1,
            "file_reads_repeated": 0,
            "searches_total": 0,
        },
    )

    usage = _usage(second, sessions=(first, second))
    assert usage["passes"] == 2
    assert usage["retries"] == 1
    assert usage["provider_cost"] == "3.500000"
    assert usage["input_units"] == 15
    assert usage["output_units"] == 150
    assert usage["cache_hits"] == 1250
    assert usage["cache_creation_units"] == 275
    assert usage["model_turns"] == 5
    assert usage["repo_file_reads"] == 3
    assert usage["repeated_file_reads"] == 1
    assert usage["repo_searches"] == 1


def test_a_session_stopped_at_its_spend_ceiling_is_not_a_successful_session():
    """Measured, not assumed: the provider reports `is_error: false` for this.

    Probed against the real CLI at `--max-budget-usd 0.0001`, the envelope came
    back `{"subtype": "error_max_budget_usd", "is_error": false}` and exit code
    0. Reading only `is_error` would record a session cut off part-way as a
    clean one, and the runner would hand a half-finished attempt to a reviewer
    as though the developer had said it was done.
    """
    recorder = _Recorder()
    recorder.run = lambda argv, **kwargs: CommandResult(
        argv=tuple(argv),
        cwd=".",
        exit_code=0,
        stdout=json.dumps(
            {
                "type": "result",
                "subtype": "error_max_budget_usd",
                "is_error": False,
                "num_turns": 1,
                "session_id": "d5555fc0-e7de-42da-9dd4-6a5fd48c7d40",
                "total_cost_usd": 0.042285,
                "usage": {"input_tokens": 0, "output_tokens": 0},
                "modelUsage": {
                    "claude-sonnet-4-6": {
                        "inputTokens": 2,
                        "outputTokens": 4,
                        "cacheCreationInputTokens": 6748,
                        "costUSD": 0.042285,
                    }
                },
            }
        ),
        stderr="",
        duration_s=2.5,
    )
    backend = ClaudeCodeBackend(recorder, executable=sys.executable)
    backend._resolved = sys.executable
    outcome = backend.launch(
        SessionRequest(
            role="developer", cwd=Path("."), instructions="x",
            timeout_s=60.0, max_cost=0.0001,
        )
    )
    assert outcome.ok is False
    assert outcome.stopped_reason == "error_max_budget_usd"
    assert outcome.cost_usd == pytest.approx(0.042285)

