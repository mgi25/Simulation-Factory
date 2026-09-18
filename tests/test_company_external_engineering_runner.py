"""Where the two halves meet: the runner's copies, pinned to the originals.

The external runner may not import Company OS - `tools/` is a production root
and `architecture.production_does_not_import_company_os` is required - so it
restates four things the control plane owns: the path-scope semantics, the job
states it acts on, the suites the gate requires, and the shape of a receipt and
an attestation.

A restatement can drift. This module is the only place in the repository that
imports both halves, and its whole job is to make the drift fail a test instead
of failing a work order:

| the runner's copy | pinned against |
|---|---|
| `PathRules` | `company.runtime.path_scope.PathScope` |
| `normalise_path` | `company.runtime.path_scope.normalise_path` |
| `ACTIONABLE`, the state names | `company.engineering.lifecycle.JobState` |
| `REQUIRED_SUITES` | `company.integration.suites.REQUIRED_SUITES` |
| `build_receipt` | `SessionReceipt.from_mapping` + `validate_receipt` |
| `build_attestation` | `ReviewerAttestation.from_mapping` |
| `executor_hint` | `company.runtime.packets.ExecutorHint` |

It also holds the one regression this milestone must not cause: the policy the
CEO said not to weaken is still required, and still implemented with the same
refusals.

## Why the pins are tables rather than assertions about behaviour

`PathScope` and `PathRules` agree trivially on the easy cases. The table below
is all hard cases - a forbidden rule inside an allowed one, a prefix that is
not a segment boundary, a Windows separator, an empty allow-list - because
those are the ones where two implementations of the same rule actually part
company.
"""

from __future__ import annotations

import datetime as dt
import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

import pytest

from company.engineering import __main__ as engineering_cli
from company.engineering.intake import CEORequest, assess_request
from company.engineering.lifecycle import CEO_STATES, TERMINAL_STATES, JobState
from company.engineering.orchestrator import open_job, prepare_developer_session
from company.engineering.protected import DEFAULT_PROTECTED_PATHS
from company.engineering.review import ReviewerAttestation
from company.engineering.store import EngineeringStore
from company.engineering.transport import developer_briefing_payload
from company.integration.boundary import NETWORK_MODULES, PROCESS_MODULES
from company.integration.policy import DEFAULT_POLICY
from company.integration.suites import REQUIRED_SUITES as GATE_REQUIRED_SUITES
from company.runtime.config import load_company_config
from company.runtime.execution_store import ExecutionStore
from company.runtime.packets import ExecutorHint
from company.runtime.path_scope import PathScope
from company.runtime.path_scope import normalise_path as company_normalise
from company.runtime.receipts import SessionReceipt, validate_receipt
from knowledge.company_os.capsules import CapsuleIndex

from tools.engineering_runner.authorization import AuthorityEnvelope, PathRules
from tools.engineering_runner.authorization import normalise_path as runner_normalise
from tools.engineering_runner.backends import SessionOutcome, executor_hint
from tools.engineering_runner.evidence import (
    REQUIRED_SUITES as RUNNER_REQUIRED_SUITES,
)
from tools.engineering_runner.evidence import (
    GitObservation,
    TestRun,
    build_attestation,
    build_receipt,
)
from tools.engineering_runner import runner as runner_module


ROOT = Path(__file__).resolve().parents[1]
DAY = dt.date(2026, 9, 18)
SHA = "c" * 40
BASE = "d" * 40


# --- the path rules --------------------------------------------------------

# (allowed, forbidden, path). Every row is a case where a second
# implementation of the rule could plausibly disagree with the first.
SCOPE_CASES = (
    ((), (), "anything.py"),
    (("company",), (), "company/runtime/packets.py"),
    (("company/runtime",), (), "company/runtime_extra.py"),
    (("company",), ("company/permissions.yaml",), "company/permissions.yaml"),
    (("company",), ("company/permissions.yaml",), "company/permissions.yaml.bak"),
    (("company",), ("company",), "company/x.py"),
    (("company/runtime",), (), "company/runtime"),
    (("a", "b"), ("a/b",), "a/b/c.py"),
    (("tools/engineering_runner",), (), "tools/engineering_runner/runner.py"),
    (("tools",), (), "toolsmith/x.py"),
)


@pytest.mark.parametrize("allowed,forbidden,path", SCOPE_CASES)
def test_the_runners_path_rules_agree_with_the_packets_path_scope(allowed, forbidden, path):
    company = PathScope(allowed=tuple(allowed), forbidden=tuple(forbidden))
    runner = PathRules(allowed=tuple(allowed), forbidden=tuple(forbidden))
    assert runner.permits(path) == company.permits(path)
    assert runner.forbids(path) == company.forbids(path)
    assert bool(runner.violations([path])) == bool(company.verdict((path,)).failures())
    assert runner.read_only == company.read_only


@pytest.mark.parametrize(
    "value",
    [
        "company/runtime/packets.py",
        "company\\runtime\\packets.py",
        "./company/runtime",
        "company//runtime",
        "company/runtime/",
    ],
)
def test_the_two_path_normalisers_produce_the_same_name(value: str):
    assert runner_normalise(value) == company_normalise(value, "path")


@pytest.mark.parametrize("value", ["/etc/passwd", "C:/Windows", "../x", "a/../b", ""])
def test_the_two_path_normalisers_refuse_the_same_names(value: str):
    with pytest.raises(Exception):
        runner_normalise(value)
    with pytest.raises(Exception):
        company_normalise(value, "path")


# --- the lifecycle ---------------------------------------------------------


def test_every_state_name_the_runner_holds_is_a_real_job_state():
    names = {
        runner_module.PLANNING,
        runner_module.DEVELOPING,
        runner_module.TESTING,
        runner_module.REVIEWING,
        runner_module.GATE,
        runner_module.READY_FOR_APPROVAL,
        runner_module.DECISION_REQUIRED,
        runner_module.BLOCKED,
        runner_module.FAILED,
        runner_module.CLOSED,
    }
    assert names == {state.value for state in JobState} - {JobState.REQUESTED.value}


def test_the_runner_acts_on_no_state_that_belongs_to_the_ceo():
    ceo = {state.value for state in CEO_STATES}
    terminal = {state.value for state in TERMINAL_STATES}
    assert not (runner_module.ACTIONABLE & ceo)
    assert not (runner_module.ACTIONABLE & terminal)


def test_the_runner_runs_exactly_the_suites_the_gate_requires():
    assert RUNNER_REQUIRED_SUITES == GATE_REQUIRED_SUITES


def test_every_executor_hint_the_runner_reports_is_a_real_one():
    for backend in ("claude_code", "codex", "something_else"):
        ExecutorHint(executor_hint(backend))


# --- the records -----------------------------------------------------------


def _fake_repo(tmp_path: Path) -> Path:
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


@pytest.fixture()
def briefing(tmp_path: Path) -> dict:
    """A real developer briefing, produced by the real orchestrator."""
    config = load_company_config(ROOT / "company")
    request = CEORequest(
        request_id="req-runner-pin",
        objective=(
            "Give me a way to check whether the protected governance files have "
            "changed since an engineering work order was authorized."
        ),
        requested_by="MGI",
        requested_on=DAY,
        subsystem_hint="company/engineering",
        authorized_branch="eng-runner-pin",
        base_commit=BASE,
    )
    assessment = assess_request(
        request,
        config.permissions,
        repo_root=_fake_repo(tmp_path),
        capsule_index=CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds"),
        work_order_id="wo-runner-pin",
    )
    assert assessment.work_order is not None
    state = tmp_path / "state"
    store = EngineeringStore(state)
    opened = open_job(store, assessment, on=DAY)
    developer = prepare_developer_session(
        store,
        ExecutionStore(state),
        opened.work_order,
        opened.job,
        config,
        on=DAY,
        executor=ExecutorHint.CLAUDE_CODE,
    )
    payload = json.loads(json.dumps(developer_briefing_payload(developer), default=str))
    return {
        "payload": payload,
        "state": state,
        "order": opened.work_order,
        "packet": developer.packet,
        "config": config,
        "repo": _fake_repo(tmp_path),
    }


def test_a_real_briefing_parses_into_an_envelope_with_the_same_ceiling(briefing):
    envelope = AuthorityEnvelope.parse(briefing["payload"])
    order = briefing["order"]
    assert envelope.may_write == tuple(sorted(order.authorized_paths))
    assert envelope.may_not_modify == tuple(
        sorted(set(order.forbidden_paths) | set(order.protected.paths))
    )
    assert envelope.work_order_fingerprint == order.fingerprint()
    assert envelope.packet_fingerprint == briefing["packet"].fingerprint()
    assert envelope.required_tests == tuple(order.required_tests)
    assert envelope.packet_attempt == 1


def _session() -> SessionOutcome:
    return SessionOutcome(
        backend="claude_code",
        role="developer",
        session_id="00000000-0000-4000-8000-000000000000",
        model="claude-test",
        provider="anthropic",
        exit_code=0,
        duration_s=2.0,
        result_text="",
        transcript="",
        ok=True,
        cost_usd=0.25,
        input_units=100,
        output_units=200,
        cache_read_units=50,
        turns=7,
    )


def _runner_receipt(briefing) -> dict:
    envelope = AuthorityEnvelope.parse(briefing["payload"])
    changed = (f"{envelope.may_write[0]}/verify.py",)
    tests = tuple(
        TestRun(
            command=command,
            argv=("python", "-m", "pytest", command),
            commit=SHA,
            exit_code=0,
            passed=1,
            failed=0,
            errors=0,
            skipped=0,
            summary="1 passed",
            duration_s=1.0,
            timed_out=False,
        )
        for command in envelope.required_tests
    )
    return build_receipt(
        envelope,
        observation=GitObservation(
            branch=envelope.authorized_branch,
            base_commit=envelope.base_commit,
            commit_sha=SHA,
            remote_branch_sha=SHA,
            remote_verified=True,
            working_tree_clean=True,
            files_changed=changed,
        ),
        tests=tests,
        narrative={
            "outcome": "accepted",
            "summary": "Added the check the objective asked for, and its tests.",
            "invariants_preserved": ["company/runtime is untouched"],
            "unresolved_risks": [],
            "evidence": [changed[0]],
            "context_refs_used": list(envelope.context_refs[:1]),
            "notes": "",
        },
        session=_session(),
        completed_at=dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc),
        accepted=True,
    )


def test_a_receipt_the_runner_builds_is_one_company_os_accepts(briefing):
    """The whole handoff, end to end, without a model and without a subprocess."""
    payload = _runner_receipt(briefing)
    receipt = SessionReceipt.from_mapping(payload)
    validation = validate_receipt(
        briefing["packet"],
        receipt,
        packet_attempt=1,
        authority_fingerprint=receipt.authority_fingerprint,
    )
    assert validation.failures == (), validation.failures
    assert receipt.no_subagents is True
    assert receipt.merge_performed is False


def test_the_receipt_command_now_reports_the_fingerprint_an_attestation_needs(
    briefing, tmp_path, monkeypatch
):
    """The one field this milestone added to Company OS, exercised through the CLI.

    Before it, the digest an attestation has to name was computed inside the
    store and printed nowhere, so preparing a review meant opening a Python
    session to recompute it by hand. That was the last per-job manual step
    that had nothing to do with judgment.
    """
    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(json.dumps(_runner_receipt(briefing)), encoding="utf-8")
    monkeypatch.chdir(ROOT)
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = engineering_cli.main(
            [
                "receipt",
                "--work-order",
                "wo-runner-pin",
                "--receipt-file",
                str(receipt_file),
                "--state-dir",
                str(briefing["state"]),
            ]
        )
    emitted = json.loads(buffer.getvalue())
    assert code == 0, emitted
    assert emitted["accepted"] is True
    fingerprint = emitted["receipt_fingerprint"]
    assert len(fingerprint) == 16 and all(char in "0123456789abcdef" for char in fingerprint)

    stored = ExecutionStore(briefing["state"]).receipts("wo-runner-pin")[-1]
    assert stored.fingerprint() == fingerprint

    # and the attestation the runner builds from it decodes
    envelope = AuthorityEnvelope.parse(briefing["payload"])
    attestation = build_attestation(
        replace(envelope, packet_fingerprint="0000111122223333"),
        review_id="rev-runner-pin-01",
        reviewer="chief_architect",
        reviewed_packet_fingerprint=envelope.packet_fingerprint,
        receipt_fingerprint=fingerprint,
        reviewed_on=DAY,
        reported={
            "verdict": "pass",
            "criteria": [
                {"criterion": item, "satisfied": True, "evidence_ref": "company/engineering"}
                for item in envelope.acceptance_criteria
            ],
            "findings": [
                {"severity": "advisory", "summary": "a nit worth recording", "deterministic": True}
            ],
            "evidence": ["company/engineering"],
            "changed_paths_reviewed": ["company/engineering/verify.py"],
            "notes": "",
        },
    )
    decoded = ReviewerAttestation.from_mapping(attestation)
    assert decoded.packet_fingerprint == envelope.packet_fingerprint
    assert decoded.receipt_fingerprint == fingerprint
    assert all(not item.deterministic for item in decoded.findings)


# --- the policy this milestone was told not to weaken ---------------------


def test_no_publishing_capability_is_still_a_required_gate_check():
    assert "production.no_publishing_capability" in DEFAULT_POLICY.required
    assert "production.no_publishing_capability" not in DEFAULT_POLICY.advisory
    assert "production.no_publishing_capability" not in DEFAULT_POLICY.not_applicable_allowed


def test_the_refusals_behind_that_check_are_unchanged():
    """The set is asserted by value, so removing one is a failing test.

    An exemption would most plausibly arrive as a quiet edit to one of these
    frozensets rather than as a change to the policy, because the policy is the
    obvious place to look.
    """
    assert PROCESS_MODULES == frozenset({"multiprocessing", "pty", "subprocess"})
    for name in ("socket", "urllib", "requests", "http", "httpx"):
        assert name in NETWORK_MODULES


def test_the_runner_is_not_a_company_os_module_and_is_not_claimed_by_a_capsule():
    """It is production, on purpose. That is what lets it hold a subprocess.

    If a capsule ever claimed `tools/engineering_runner`, the package would be
    inside the control plane's declared surface while living outside its import
    boundary, and the two statements would contradict each other.
    """
    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    for capsule in index.all():
        for owned in capsule.owns_paths:
            assert not owned.startswith("tools/"), f"{capsule.capsule_id} claims {owned}"
