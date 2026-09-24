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

import ast
import datetime as dt
import io
import json
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path

import pytest

from company.engineering import __main__ as engineering_cli
from company.engineering.intake import CEORequest, IntakeOutcome, assess_request
from company.engineering.lifecycle import CEO_STATES, TERMINAL_STATES, JobState
from company.engineering.orchestrator import open_job, prepare_developer_session
from company.engineering.protected import DEFAULT_PROTECTED_PATHS
from company.engineering.review import ReviewerAttestation, deterministic_findings
from company.engineering.store import EngineeringStore
from company.engineering.transport import developer_briefing_payload
from company.integration.boundary import NETWORK_MODULES, PROCESS_MODULES
from company.integration.policy import DEFAULT_POLICY
from ai_platform.references import MAX_REF_CHARS as COMPANY_MAX_REF_CHARS
from company.engineering.review import FindingSeverity, ReviewOutcome
from company.integration.suites import REQUIRED_SUITES as GATE_REQUIRED_SUITES
from company.runtime.config import load_company_config
from company.runtime.execution_store import ExecutionStore
from company.runtime.packets import ExecutorHint
from company.engineering.work_order import _read_covers as company_read_covers
from company.runtime.path_scope import PathScope
from company.runtime.path_scope import normalise_path as company_normalise
from company.runtime.receipts import SessionReceipt, validate_receipt
from knowledge.company_os.capsules import CapsuleIndex

from tools.engineering_runner.authorization import (
    REVIEW_TASK_SUFFIX,
    AuthorityEnvelope,
    PathRules,
)
from tools.engineering_runner.authorization import _read_covers as runner_read_covers
from tools.engineering_runner.authorization import normalise_path as runner_normalise
from tools.engineering_runner.backends import SessionOutcome, executor_hint
from tools.engineering_runner.evidence import (
    REQUIRED_SUITES as RUNNER_REQUIRED_SUITES,
)
from tools.engineering_runner.evidence import (
    FINDING_SEVERITIES,
    MAX_REF_CHARS,
    REVIEW_VERDICTS,
    assert_reviewer_report,
)
from tools.engineering_runner.evidence import (
    GitObservation,
    TestRun,
    build_attestation,
    build_receipt,
    dependencies_added,
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


# The read rule is duplicated for the same reason the write rule is, and it is
# the harder of the two: a read rule may carry a wildcard, because a capsule
# declares `company/*.yaml` to mean four files rather than a tree. A prefix
# test would match none of them, so the two halves are held to the same table.
READ_CASES = (
    ("company", "company/runtime/packets.py", True),
    ("company/runtime", "company/runtime_extra.py", False),
    ("company/*.yaml", "company/permissions.yaml", True),
    ("company/*.yaml", "company/runtime/state.yaml", False),
    ("company/*.yaml", "company/permissions.yaml.bak", False),
    ("company/workforce/*.py", "company/workforce/roles.py", True),
    ("company/workforce/*.py", "company/workforce/sub/roles.py", False),
    ("docs/evidence", "docs/evidence/x/RESULT.md", True),
    ("docs/evidence", "docs/evidence_other/RESULT.md", False),
    ("ai_platform", "ai_platform", True),
)


@pytest.mark.parametrize("rule,path,expected", READ_CASES)
def test_the_runners_read_rule_agrees_with_the_work_orders(rule, path, expected):
    assert runner_read_covers(rule, path) is expected
    assert company_read_covers(rule, path) is expected


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


def test_the_review_task_id_the_runner_expects_is_the_one_the_work_order_builds(briefing):
    """Pinned to `review_specification`, because the runner refuses any other id.

    The suffix is the separation of duties made visible in an identifier, and
    the runner restates it. A silent change to either side would make every
    review packet unparseable - which is exactly how the dogfood run failed
    before this pin existed.
    """
    order = briefing["order"]
    assert order.review_specification().task_id == (
        f"{order.work_order_id}{REVIEW_TASK_SUFFIX}"
    )


def test_the_runner_runs_exactly_the_suites_the_gate_requires():
    assert RUNNER_REQUIRED_SUITES == GATE_REQUIRED_SUITES


def test_the_review_contract_the_runner_enforces_is_the_one_company_os_enforces():
    """Three restatements, pinned. The first run lost a review to the first one."""
    assert MAX_REF_CHARS == COMPANY_MAX_REF_CHARS
    assert REVIEW_VERDICTS == {item.value for item in ReviewOutcome}
    assert FINDING_SEVERITIES == {item.value for item in FindingSeverity}


def test_a_review_the_runner_accepts_is_one_the_attestation_decodes(briefing):
    """Whatever passes the runner's check must survive `ReviewerAttestation`.

    The runner's check exists to spend a repair turn instead of a whole review
    session, so it is only worth having if it is not weaker than the contract
    it stands in for.
    """
    envelope = AuthorityEnvelope.parse(briefing["payload"])
    reported = {
        "verdict": "pass",
        "criteria": [
            {"criterion": item, "satisfied": True, "evidence_ref": "company/engineering"}
            for item in envelope.acceptance_criteria
        ],
        "findings": [
            {
                "finding_id": "nit-01",
                "severity": "advisory",
                "summary": "a nit",
                "evidence_ref": "company/engineering/attempt_ledger.py:1",
            }
        ],
        "evidence": ["company/engineering"],
        "changed_paths_reviewed": ["company/engineering/attempt_ledger.py"],
        "notes": "",
    }
    assert_reviewer_report(reported)
    decoded = ReviewerAttestation.from_mapping(
        build_attestation(
            envelope,
            review_id="rev-contract-01",
            reviewer="chief_architect",
            reviewed_packet_fingerprint=envelope.packet_fingerprint,
            receipt_fingerprint="1111222233334444",
            reviewed_on=DAY,
            reported=reported,
        )
    )
    assert decoded.verdict is ReviewOutcome.PASS
    assert len(decoded.criteria) == len(envelope.acceptance_criteria)


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


def _runner_receipt(
    briefing, *, dependencies: tuple[str, ...] = (), session: SessionOutcome | None = None
) -> dict:
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
        session=session or _session(),
        completed_at=dt.datetime(2026, 9, 18, tzinfo=dt.timezone.utc),
        accepted=True,
        dependencies_added=dependencies,
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



def test_exploration_telemetry_survives_the_receipt_round_trip(briefing):
    """Repository Exploration Efficiency V2: the three new usage fields are
    read by `evidence._usage`, accepted by `ReceiptUsage.from_mapping` as a
    known field rather than refused, and reach Company OS intact."""
    session = SessionOutcome(
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
        exploration={
            "format": "stream_json",
            "file_reads_total": 12,
            "file_reads_repeated": 3,
            "searches_total": 4,
        },
    )
    payload = _runner_receipt(briefing, session=session)
    receipt = SessionReceipt.from_mapping(payload)
    assert receipt.usage.repo_file_reads == 12
    assert receipt.usage.repeated_file_reads == 3
    assert receipt.usage.repo_searches == 4
    validation = validate_receipt(
        briefing["packet"],
        receipt,
        packet_attempt=1,
        authority_fingerprint=receipt.authority_fingerprint,
    )
    assert validation.failures == (), validation.failures


def test_a_dependency_the_runner_measures_is_one_company_os_blocks_on(briefing):
    """The field the runner now fills, read by the governance that was waiting for it.

    `dependencies_added` was hardcoded to `[]`, so an attempt could add a
    production dependency inside its authorized scope and this finding - which
    has existed the whole time, because `mandatory_review_triggers.new_dependency`
    in permissions.yaml makes a new dependency an architecture-and-security
    review - had nothing to fire on. The runner supplies no new policy here; it
    supplies the measurement the existing policy needed.
    """
    measured = dependencies_added("pymunk>=7.0\npytest>=8.0\n", "pymunk>=7.0\npytest>=8.0\nrequests>=2.31\n")
    assert measured == ("requests",)

    payload = _runner_receipt(briefing, dependencies=measured)
    receipt = SessionReceipt.from_mapping(payload)
    assert receipt.dependencies_added == ("requests",)
    validation = validate_receipt(
        briefing["packet"],
        receipt,
        packet_attempt=1,
        authority_fingerprint=receipt.authority_fingerprint,
    )
    findings = deterministic_findings(
        briefing["order"],
        briefing["packet"],
        receipt,
        validation,
        repo_root=briefing["repo"],
    )
    dependency = [item for item in findings if item.finding_id == "dependency-added"]
    assert len(dependency) == 1
    assert dependency[0].severity is FindingSeverity.BLOCKING
    assert "requests" in dependency[0].summary
    assert "architecture_and_security_review" in dependency[0].summary


def test_an_attempt_that_adds_no_dependency_raises_no_such_finding(briefing):
    payload = _runner_receipt(briefing)
    receipt = SessionReceipt.from_mapping(payload)
    validation = validate_receipt(
        briefing["packet"],
        receipt,
        packet_attempt=1,
        authority_fingerprint=receipt.authority_fingerprint,
    )
    findings = deterministic_findings(
        briefing["order"],
        briefing["packet"],
        receipt,
        validation,
        repo_root=briefing["repo"],
    )
    assert [item for item in findings if item.finding_id == "dependency-added"] == []

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


def test_the_runner_is_production_and_is_claimed_by_exactly_one_capsule():
    """It is production, on purpose. That is what lets it hold a subprocess.

    This assertion used to read the other way: no capsule may claim anything
    under `tools/`, because a claimed package would be "inside the control
    plane's declared surface while living outside its import boundary". The two
    halves of that sentence turned out to be separable, and separating them is
    what P5-R3 did.

    What `owns_paths` decides is which capsule a work order is derived from -
    who reviews a change, and what a developer session may write. What the
    import boundary decides is which packages may import which. A subsystem
    nobody owns gets no bounded work order and therefore no independent
    review, which is how the P5-R2 change to `authorization.py` reached this
    branch ungoverned. So the runner is owned and still external: no import was
    added in either direction, and
    `architecture.production_does_not_import_company_os` is still required.

    The old assertion never ran its own message - `capsule.capsule_id` does not
    exist, and the attribute error surfaced only when it first failed.
    """
    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    claims = sorted(
        (owned, capsule.id)
        for capsule in index.all()
        for owned in capsule.owns_paths
        if owned == "tools" or owned.startswith("tools/")
    )
    assert claims == [
        ("tools/engineering_runner", "company-external-engineering-runner"),
        # P6B. `architecture.governed_subsystem_ownership` found the second
        # one: `tests/test_company_youtube_end_to_end.py` imports
        # `tools/youtube_fetch`, so the Company OS contract depends on it, and
        # it had no owner. The same reasoning as the runner applies to it -
        # a subsystem nobody owns gets no bounded work order and no
        # independent review - and the same limit applies too: the claim is on
        # the package, never on `tools`.
        ("tools/youtube_fetch", "company-youtube-fetch-client"),
    ]


def test_owning_the_runner_did_not_put_it_inside_the_import_boundary():
    """Ownership is a governance record, not a membership claim.

    Both directions are read off the source here, because the gate check that
    proves the first one only runs inside the gate.
    """
    banned = ("company", "ai_platform", "knowledge", "intelligence")
    for path in sorted((ROOT / "tools" / "engineering_runner").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name.split(".")[0] not in banned, f"{path.name} imports {name}"

    for path in sorted((ROOT / "company" / "engineering").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                module = node.names[0].name
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
            else:
                continue
            assert not module.startswith("tools"), f"{path.name} imports {module}"


# Required suites restate the exemption rather than import the dashboard, to
# keep their own import surface small. Every restatement is listed here, and
# every one is compared against the single definition below.
_RESTATING_SUITES = (
    "tests/test_company_os_capsules.py",
    "tests/test_company_finance.py",
    "tests/test_company_org_intelligence.py",
)


def _declared_external_capsules(relative_path: str) -> set[str]:
    """The `EXTERNAL_CAPSULES` literal a suite declares, read without importing it."""
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "EXTERNAL_CAPSULES" for t in node.targets
        ):
            return set(ast.literal_eval(node.value))
    raise AssertionError(f"{relative_path} no longer declares EXTERNAL_CAPSULES")


def test_the_external_capsule_exemption_is_stated_once_and_agrees():
    """The capsule suite restates this set; the two copies are pinned here.

    `test_company_os_capsules.py` keeps its own import surface small on
    purpose, so it holds a literal rather than importing the dashboard. This
    module already imports both halves, so it is where the two are compared.
    """
    from company.dashboard.builder import EXTERNAL_CAPSULES

    assert EXTERNAL_CAPSULES == frozenset(
        {"company-external-engineering-runner", "company-youtube-fetch-client"}
    )
    for suite in _RESTATING_SUITES:
        assert _declared_external_capsules(suite) == set(EXTERNAL_CAPSULES), suite


# --- what ownership buys: a bounded work order for a runner change ---------


def _runner_request(**overrides):
    base = dict(
        request_id="runner-scope-probe",
        objective="Correct the read ceiling the runner carries into a session",
        requested_by="ceo",
        requested_on=dt.date(2026, 9, 24),
        capsule_hints=("company-external-engineering-runner",),
        authorized_branch="p5-runner-ownership-v1",
        base_commit="d7944aaceb901eabf1d962ac77463f47836dc790",
        max_developer_attempts=1,
    )
    base.update(overrides)
    return CEORequest(**base)


def _assess(request):
    config = load_company_config()
    return assess_request(request, config.permissions, repo_root=ROOT)


def test_company_os_can_now_derive_a_bounded_work_order_for_a_runner_change():
    """The refusal P5-R3 was opened to remove.

    Before the capsule existed this objective either produced DECISION
    REQUIRED - no capsule owns the subject - or, worse, matched
    `company-engineering-execution` on the token "engineering" and authorized
    `company/engineering` while forbidding `tools`, sending a developer to the
    wrong subsystem with the right one out of bounds.
    """
    assessment = _assess(_runner_request())
    assert assessment.outcome is IntakeOutcome.AUTHORIZED
    assert assessment.decisions == ()
    assert assessment.derivation.selected_capsule_ids == (
        "company-external-engineering-runner",
    )
    order = assessment.work_order
    assert order is not None
    assert "tools/engineering_runner" in order.authorized_paths


def test_that_work_order_authorizes_the_runner_and_nothing_else_in_tools():
    order = _assess(_runner_request()).work_order
    assert order is not None
    in_tools = [p for p in order.authorized_paths if p == "tools" or p.startswith("tools/")]
    assert in_tools == ["tools/engineering_runner"]
    scope = PathScope(allowed=order.authorized_paths, forbidden=order.forbidden_paths)
    assert scope.permits("tools/engineering_runner/authorization.py")
    for outside in (
        "tools/youtube_fetch/client.py",
        "tools/race2_render.py",
        "sloped/course.py",
    ):
        assert not scope.permits(outside), outside


def test_ownership_does_not_grant_authority_over_the_control_plane():
    """Owning a production path is not a licence to edit what governs it."""
    order = _assess(_runner_request()).work_order
    assert order is not None
    scope = PathScope(allowed=order.authorized_paths, forbidden=order.forbidden_paths)
    for protected in (
        "company/engineering/intake.py",
        "company/permissions.yaml",
        "company/constitution.md",
        "ai_platform/policy.py",
        "knowledge/company_os/capsules/seeds/company-engineering-execution.json",
    ):
        assert not scope.permits(protected), protected
    assert scope.forbids("company/engineering/intake.py")


def test_the_protected_surface_is_still_digested_for_a_runner_work_order():
    order = _assess(_runner_request()).work_order
    assert order is not None
    digested = {entry.path for entry in order.protected.entries}
    assert set(DEFAULT_PROTECTED_PATHS) <= digested
    assert "company/validation/no_subagents.py" in digested


def test_a_runner_work_order_carries_a_bounded_read_ceiling():
    """Read authority is derived, not assumed, and it is not the repository."""
    order = _assess(_runner_request()).work_order
    assert order is not None
    assert order.authorized_read_paths
    assert "tools/engineering_runner" in order.authorized_read_paths
    assert "." not in order.authorized_read_paths
    assert "tools" not in order.authorized_read_paths
    for rule in order.authorized_read_paths:
        assert not rule.startswith("sloped"), rule


def test_ownership_confers_no_production_authority():
    """A work order is not a publish button, and the capsule says so."""
    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    capsule = index.get("company-external-engineering-runner")
    assert any(
        "merges, deploys, publishes or uploads" in line for line in capsule.invariants
    )
    assert "production.no_publishing_capability" in DEFAULT_POLICY.required


def test_the_no_subagent_invariant_survives_the_new_capsule():
    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    capsule = index.get("company-external-engineering-runner")
    assert "bootstrap-forbids-nested-agents" in capsule.facts
    assert any("no-subagent" in line for line in capsule.invariants)
    order = _assess(_runner_request()).work_order
    assert order is not None
    assert "ai_platform/policy.py" in {entry.path for entry in order.protected.entries}


# --- the governed review of the P5-R2 read-authority change ----------------
#
# `tools/engineering_runner/authorization.py` gained its read ceiling in P5-R2,
# before any capsule owned the package, so the change never went through a
# bounded work order or an independent review. P5-R3 created the owner; these
# are the cases that review ran, kept as evidence rather than as prose.
#
# The behaviour they pin is one whole contract, including the part that is a
# limitation rather than a guarantee. An enforcement claim that is not true is
# worse than an absent one, so the limit is asserted too.


def _read_briefing(read_allowed=(), read_denied=(), refs=(), role="developer"):
    """One briefing payload, varying only the read ceiling and the context."""
    task = "wo-read-probe" + (REVIEW_TASK_SUFFIX if role == "reviewer" else "")
    return {
        "role": role,
        "employee": "dev-1",
        "packet_fingerprint": "f" * 16,
        "work_order": {
            "work_order_id": "wo-read-probe",
            "work_order_fingerprint": "a" * 16,
            "objective": "probe the read ceiling",
            "authorized_branch": "b",
            "base_commit": "c" * 40,
            "authorized_paths": ["tools/engineering_runner"],
            "forbidden_paths": [],
            "protected_paths": [],
            "required_tests": [],
            "acceptance_criteria": ["the ceiling is carried"],
            "authorized_read_paths": list(read_allowed),
            "forbidden_read_paths": list(read_denied),
        },
        "packet": {
            "task_id": task,
            "attempt": 1,
            "path_scope": (
                {"allowed": ["tools/engineering_runner"], "forbidden": []}
                if role == "developer"
                else {"allowed": [], "forbidden": []}
            ),
            "context_refs": [{"kind": "file", "ref": ref} for ref in refs],
        },
        "transport": {"authority_fingerprint": "d" * 16},
    }


def test_the_read_ceiling_reaches_the_envelope_and_is_serialised():
    envelope = AuthorityEnvelope.parse(
        _read_briefing(
            read_allowed=["tools/engineering_runner"],
            read_denied=["sloped"],
            refs=["tools/engineering_runner/runner.py"],
        )
    )
    assert envelope.may_read == ("tools/engineering_runner",)
    assert envelope.may_not_read == ("sloped",)
    summary = envelope.summary()
    assert summary["may_read"] == ["tools/engineering_runner"]
    assert summary["may_not_read"] == ["sloped"]


def test_both_roles_receive_the_same_read_scope_and_differ_only_in_write():
    shared = dict(read_allowed=["tools/engineering_runner"], refs=["tools/engineering_runner/runner.py"])
    developer = AuthorityEnvelope.parse(_read_briefing(role="developer", **shared))
    reviewer = AuthorityEnvelope.parse(_read_briefing(role="reviewer", **shared))
    assert developer.may_read == reviewer.may_read
    assert developer.may_not_read == reviewer.may_not_read
    assert developer.may_write == ("tools/engineering_runner",)
    assert reviewer.may_write == ()
    assert reviewer.read_only and not developer.read_only


def test_a_packet_carrying_context_outside_the_ceiling_is_refused():
    with pytest.raises(Exception, match="outside the work order's authorized_read_paths"):
        AuthorityEnvelope.parse(
            _read_briefing(read_allowed=["tools/engineering_runner"], refs=["sloped/course.py"])
        )


def test_a_denied_read_beats_an_allowed_one():
    """Forbidden wins on the read side too, and it wins over a broader allow."""
    with pytest.raises(Exception, match="forbids reading"):
        AuthorityEnvelope.parse(
            _read_briefing(
                read_allowed=["tools"],
                read_denied=["tools/engineering_runner"],
                refs=["tools/engineering_runner/runner.py"],
            )
        )


def test_a_read_rule_may_carry_a_wildcard_and_still_bind():
    AuthorityEnvelope.parse(
        _read_briefing(read_allowed=["company/*.yaml"], refs=["company/permissions.yaml"])
    )
    with pytest.raises(Exception, match="outside the work order's authorized_read_paths"):
        AuthorityEnvelope.parse(
            _read_briefing(read_allowed=["company/*.yaml"], refs=["company/runtime/state.yaml"])
        )


def test_an_empty_read_ceiling_skips_the_packet_check_and_that_is_the_limit():
    """The one asymmetry the review found, pinned so it stays deliberate.

    An absent ceiling grants no read authority - `context_expansion_policy`
    refuses a governed expansion outright when `may_read` is empty. The runner
    does not restate that refusal, because a work order stored before these
    fields existed decodes to `()` and refusing here would strand every one of
    them; P5-R2 required that adding the fields restamp nothing.

    So an empty ceiling means "unchecked here", not "unrestricted anywhere".
    The denial list still binds with no allow-list, which is what keeps the
    empty case from being a hole rather than a gap.
    """
    envelope = AuthorityEnvelope.parse(_read_briefing(read_allowed=[], refs=["sloped/secret.py"]))
    assert envelope.may_read == ()

    with pytest.raises(Exception, match="forbids reading"):
        AuthorityEnvelope.parse(
            _read_briefing(read_allowed=[], read_denied=["sloped"], refs=["sloped/secret.py"])
        )


def test_the_refusal_on_an_empty_contract_lives_where_enforcement_does():
    """The claim the previous test leans on, asserted rather than assumed."""
    from ai_platform import ContextKind, ContextRef
    from company.runtime.context_expansion_policy import _reference_problem
    from knowledge.company_os.capsules import CapsuleIndex

    index = CapsuleIndex.load(ROOT / "knowledge/company_os/capsules/seeds")
    ref = ContextRef(
        kind=ContextKind.FILE,
        ref="tools/engineering_runner/runner.py",
        reason="the file the probe asks to read",
    )
    assert _reference_problem(ref, (), (), index, ROOT) == (
        "employee may_read is empty; the contract grants no read authority"
    )
    # and a non-empty ceiling that covers it produces no problem at all
    assert _reference_problem(ref, ("tools/engineering_runner",), (), index, ROOT) == ""


def test_the_runner_does_not_claim_an_enforcement_it_cannot_perform():
    """The docstring says what it cannot do, and that sentence is the contract."""
    source = (ROOT / "tools/engineering_runner/authorization.py").read_text(encoding="utf-8")
    assert "cannot stop a process from" in source
    assert "no sandbox" in source


def test_no_broad_repository_read_claim_is_ever_produced():
    """The envelope carries the order's paths, never a root that means everything."""
    envelope = AuthorityEnvelope.parse(
        _read_briefing(
            read_allowed=["tools/engineering_runner"], refs=["tools/engineering_runner/runner.py"]
        )
    )
    for rule in envelope.may_read:
        assert rule not in (".", "/", "*", "**", "")
    assert envelope.may_read == ("tools/engineering_runner",)
