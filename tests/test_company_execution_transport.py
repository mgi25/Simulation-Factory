"""End-to-end proofs for the audited file and CLI execution transport."""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from ai_platform import ContextKind, ContextRef, Outcome
from ai_platform.serde import dumps
from company.runtime import (
    AuthoritySource,
    ContextExpansionRequest,
    ContextRequirements,
    ExecutionAuthoritySnapshot,
    ExecutionStore,
    ExecutorHint,
    ExpansionOutcome,
    ManualExternalSessionAdapter,
    PathScope,
    ResourceUsageStore,
    SessionReceipt,
    TaskSpecification,
    contract_from_registry,
    load_company_config,
    plan_task,
)
from company.runtime.__main__ import build_parser, main as runtime_main
from company.runtime.errors import LifecycleError


ROOT = Path(__file__).resolve().parents[1]
BRANCH = "company-os-v1-execution-transport"
SHA = "d" * 40
INDEX_PATH = "knowledge/company_os/capsules/index.py"
INDEX_KEY = f"file:{INDEX_PATH}"


def _plan(task_id: str = "execution-transport"):
    return plan_task(
        TaskSpecification(
            task_id=task_id,
            objective="Exercise the audited manual external-executor transport.",
            required_capabilities=("software_architecture",),
            deterministic_execution_possible=False,
            context=ContextRequirements(
                refs=(
                    ContextRef(
                        ContextKind.FILE,
                        "company/runtime/packets.py",
                        "initial packet boundary",
                    ),
                ),
                constraints=("Do not modify production systems.",),
                acceptance_criteria=("The audited transport succeeds.",),
            ),
        ),
        load_company_config(ROOT / "company"),
    )


def _contract(plan, *, may_read=(), may_write=(), may_not_read=(), may_not_modify=()):
    contract = contract_from_registry(plan.selected_employee, plan.config)
    contract.update(
        may_read=list(may_read),
        may_write=list(may_write),
        may_not_read=list(may_not_read),
        may_not_modify=list(may_not_modify),
    )
    return contract


def _request(packet, *, attempt: int, ref: str = INDEX_PATH, sequence: int = 1):
    return ContextExpansionRequest(
        task_id=packet.task_id,
        packet_fingerprint=packet.fingerprint(),
        request_id=f"context-a{attempt:06d}-r{sequence:06d}",
        requested_refs=(
            ContextRef(
                ContextKind.FILE,
                ref,
                "Need exact dependency registration for the focused change.",
            ),
        ),
        reason="Need exact dependency registration for the focused change.",
        requesting_executor=ExecutorHint.CODEX,
        sequence=sequence,
        required_to_continue=True,
        packet_attempt=attempt,
    )


def test_authority_snapshot_is_deterministic_minimal_and_persisted(
    tmp_path: Path,
) -> None:
    plan = _plan()
    contract = _contract(
        plan,
        may_read=(INDEX_PATH, "company/runtime"),
        may_write=("company/runtime/authority.py",),
        may_not_read=("company/org_intelligence",),
        may_not_modify=("company/runtime/secrets.py",),
    )
    contract["mission"] = "irrelevant prompt text must not enter authority evidence"
    adapter = ManualExternalSessionAdapter(ExecutionStore(tmp_path))
    prepared = adapter.prepare(
        plan,
        expected_branch=BRANCH,
        path_scope=PathScope(
            allowed=("company/runtime/authority.py",),
            forbidden=("company/runtime/secrets.py",),
        ),
        employee_contract=contract,
    )

    snapshot = prepared.authority
    assert snapshot.source is AuthoritySource.TEMPORARY_TASK_OVERRIDE
    assert snapshot.packet_attempt == prepared.pointer.attempt == 1
    assert snapshot.packet_fingerprint == prepared.packet.fingerprint()
    assert snapshot.no_subagents is True
    assert "mission" not in snapshot.to_dict()
    assert "irrelevant" not in dumps(snapshot)
    assert ExecutionAuthoritySnapshot.from_mapping(snapshot.to_dict()) == snapshot
    reordered = replace(snapshot, may_read=tuple(reversed(snapshot.may_read)))
    assert snapshot.fingerprint() == reordered.fingerprint()
    assert prepared.authority_pointer.attempt == prepared.pointer.attempt
    assert prepared.authority_pointer.record_ref.startswith("execution/authorities/")
    assert ExecutionStore(tmp_path).authorities(plan.specification.task_id) == (
        snapshot,
    )


def test_canonical_and_temporary_sources_do_not_change_packet_identity(
    tmp_path: Path,
) -> None:
    plan = _plan("authority-sources")
    adapter = ManualExternalSessionAdapter(ExecutionStore(tmp_path))
    canonical = adapter.prepare(
        plan, expected_branch=BRANCH, executor=ExecutorHint.CODEX
    )
    temporary = adapter.prepare(
        plan,
        expected_branch=BRANCH,
        executor=ExecutorHint.CLAUDE_CODE,
        employee_contract=_contract(plan, may_read=(INDEX_PATH,)),
    )

    assert canonical.authority.source is AuthoritySource.CANONICAL_CONTRACT
    assert temporary.authority.source is AuthoritySource.TEMPORARY_TASK_OVERRIDE
    assert canonical.packet.fingerprint() == temporary.packet.fingerprint()
    assert canonical.authority.fingerprint() != temporary.authority.fingerprint()
    assert canonical.authority.packet_attempt == 1
    assert temporary.authority.packet_attempt == 2


def test_multiple_attempts_use_matching_authority_and_keep_rejections(
    tmp_path: Path,
) -> None:
    plan = _plan("multiple-authority-attempts")
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    denied = adapter.prepare(
        plan,
        expected_branch=BRANCH,
        employee_contract=_contract(plan, may_read=()),
    )
    allowed = adapter.prepare(
        plan,
        expected_branch=BRANCH,
        employee_contract=_contract(plan, may_read=(INDEX_PATH,)),
    )
    assert denied.packet.fingerprint() == allowed.packet.fingerprint()

    first = adapter.expand_context(
        denied.packet, _request(denied.packet, attempt=1), repo_root=ROOT
    )
    second = adapter.expand_context(
        allowed.packet, _request(allowed.packet, attempt=2), repo_root=ROOT
    )

    assert first.decision.outcome is ExpansionOutcome.REJECTED
    assert "may_read is empty" in first.decision.rejected_refs[0].reason
    assert second.decision.outcome is ExpansionOutcome.APPROVED
    assert first.decision.authority_fingerprint == denied.authority.fingerprint()
    assert second.decision.authority_fingerprint == allowed.authority.fingerprint()
    assert first.decision.authority_fingerprint != second.decision.authority_fingerprint
    assert first.ledger.approved_refs == ()
    assert second.ledger.approved_refs[0].key == INDEX_KEY
    history = store.history(plan.specification.task_id)
    assert [item["outcome"] for item in history["context_expansions"]["decisions"]] == [
        "rejected",
        "approved",
    ]


def test_executor_request_schema_cannot_carry_authority() -> None:
    raw = {
        "task_id": "schema-guard",
        "packet_fingerprint": "a" * 16,
        "request_id": "context-a000001-r000001",
        "requested_refs": [
            {
                "kind": "file",
                "ref": INDEX_PATH,
                "reason": "Need exact dependency registration for the focused change.",
            }
        ],
        "reason": "Need exact dependency registration for the focused change.",
        "requesting_executor": "human",
        "sequence": 1,
        "required_to_continue": True,
        "packet_attempt": 1,
        "may_read": ["production"],
    }
    with pytest.raises(LifecycleError, match="unknown field.*may_read"):
        ContextExpansionRequest.from_mapping(raw)
    with pytest.raises(SystemExit):
        build_parser().parse_args(
            [
                "context-decide",
                "--state-dir",
                "state",
                "--task",
                "schema-guard",
                "--request",
                "context-a000001-r000001",
                "--authority-override-file",
                "fake.json",
            ]
        )


def test_cli_dogfood_packet_authority_expansion_receipt_usage_history(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "cli-dogfood-transport",
                "objective": "Run the real missing-index external-session pattern.",
                "required_capabilities": ["software_architecture"],
                "deterministic_execution_possible": False,
                "context": {
                    "refs": [
                        {
                            "kind": "file",
                            "ref": "company/runtime/packets.py",
                            "reason": "initial packet boundary",
                        }
                    ],
                    "constraints": ["Do not modify production systems."],
                    "acceptance_criteria": ["The CLI audit chain succeeds."],
                },
            }
        ),
        encoding="utf-8",
    )
    override = tmp_path / "authority.json"
    override.write_text(
        json.dumps(
            {
                "may_read": [INDEX_PATH],
                "may_write": [],
                "may_not_read": [],
                "may_not_modify": [],
            }
        ),
        encoding="utf-8",
    )
    state = tmp_path / "state"

    assert (
        runtime_main(
            [
                "packet",
                str(task_file),
                "--branch",
                BRANCH,
                "--executor",
                "codex",
                "--authority-override-file",
                str(override),
                "--state-dir",
                str(state),
            ]
        )
        == 0
    )
    prepared = json.loads(capsys.readouterr().out)
    packet_fingerprint = prepared["fingerprint"]
    authority_fingerprint = prepared["authority"]["fingerprint"]
    assert prepared["authority"]["source"] == "temporary_task_override"
    assert prepared["transport"]["authority_fingerprint"] == authority_fingerprint
    assert "may_read" not in prepared["transport"]
    assert prepared["transport"]["no_subagents"] is True

    assert (
        runtime_main(
            [
                "context-request",
                "--state-dir",
                str(state),
                "--task",
                "cli-dogfood-transport",
                "--kind",
                "file",
                "--ref",
                INDEX_PATH,
                "--reason",
                "Need exact dependency registration for the focused change.",
                "--required",
                "--executor",
                "claude_code",
            ]
        )
        == 0
    )
    requested = json.loads(capsys.readouterr().out)
    request_id = requested["request"]["request_id"]
    assert requested["request"]["no_subagents"] is True

    assert (
        runtime_main(
            [
                "context-decide",
                "--state-dir",
                str(state),
                "--task",
                "cli-dogfood-transport",
                "--request",
                request_id,
                "--repo-root",
                str(ROOT),
            ]
        )
        == 0
    )
    decided = json.loads(capsys.readouterr().out)
    assert decided["decision"]["outcome"] == "approved"
    assert decided["decision"]["authority_fingerprint"] == authority_fingerprint
    assert decided["decision"]["no_subagents"] is True
    assert (
        ExecutionStore(state).packets("cli-dogfood-transport")[0].fingerprint()
        == packet_fingerprint
    )

    receipt_file = tmp_path / "receipt.json"
    receipt_file.write_text(
        json.dumps(
            {
                "task_id": "cli-dogfood-transport",
                "packet_fingerprint": packet_fingerprint,
                "outcome": "accepted",
                "summary": "CLI expansion completed, pushed, and verified.",
                "branch": BRANCH,
                "commit_sha": SHA,
                "remote_branch_sha": SHA,
                "remote_verified": True,
                "working_tree_clean": True,
                "files_changed": [],
                "evidence": ["tests/test_company_execution_transport.py"],
                "context_refs_used": [
                    prepared["packet"]["context_refs"][0]["kind"]
                    + ":"
                    + prepared["packet"]["context_refs"][0]["ref"],
                    INDEX_KEY,
                ],
                "context_usage_reported": True,
                "executor": "human",
                "subagents_used": 0,
            }
        ),
        encoding="utf-8",
    )
    assert (
        runtime_main(
            [
                "receipt",
                str(receipt_file),
                "--task",
                str(task_file),
                "--state-dir",
                str(state),
            ]
        )
        == 0
    )
    ingested = json.loads(capsys.readouterr().out)
    assert ingested["accepted"] is True
    assert ingested["failures"] == []

    receipt = ExecutionStore(state).receipts("cli-dogfood-transport")[0]
    assert receipt.packet_attempt == 1
    assert receipt.authority_fingerprint == authority_fingerprint
    assert receipt.expansion_ledger_fingerprint
    assert (
        receipt.effective_context_fingerprint
        == decided["effective_context_fingerprint"]
    )
    assert receipt.subagents_used == 0
    usage = ResourceUsageStore(state).records("cli-dogfood-transport")[0]
    assert usage.expanded_context_sources == (INDEX_KEY,)
    assert usage.required_expansion_count == 1
    assert usage.subagents_used == 0

    assert (
        runtime_main(
            [
                "execution",
                "--state-dir",
                str(state),
                "--task",
                "cli-dogfood-transport",
            ]
        )
        == 0
    )
    history = json.loads(capsys.readouterr().out)
    assert history["packets"][0]["attempt"] == 1
    assert history["authorities"][0]["fingerprint"] == authority_fingerprint
    assert history["context_expansions"]["requests"][0]["request_id"] == request_id
    assert history["context_expansions"]["decisions"][0]["outcome"] == "approved"
    assert (
        history["effective_contexts"][0]["fingerprint"]
        == decided["effective_context_fingerprint"]
    )
    assert history["attempts"][0]["outcome"] == "accepted"
    assert history["attempts"][0]["authority_fingerprint"] == authority_fingerprint
    assert history["usage_references"][0]["record_ref"].startswith("resource_usage/")


def test_receipt_with_unapproved_context_is_rejected_under_stored_authority(
    tmp_path: Path,
) -> None:
    plan = _plan("unapproved-context")
    store = ExecutionStore(tmp_path)
    adapter = ManualExternalSessionAdapter(store)
    prepared = adapter.prepare(
        plan,
        expected_branch=BRANCH,
        employee_contract=_contract(plan, may_read=()),
    )
    receipt = SessionReceipt(
        task_id=prepared.packet.task_id,
        packet_fingerprint=prepared.packet.fingerprint(),
        outcome=Outcome.ACCEPTED,
        summary="Claims context that was never approved.",
        branch=BRANCH,
        commit_sha=SHA,
        remote_branch_sha=SHA,
        remote_verified=True,
        working_tree_clean=True,
        context_refs_used=(INDEX_KEY,),
        context_usage_reported=True,
    )
    ingested = adapter.ingest(
        plan, prepared.packet, receipt, ResourceUsageStore(tmp_path)
    )
    assert not ingested.accepted
    assert any(
        "neither the packet nor an approved expansion" in failure
        for failure in ingested.validation.failures
    )


def test_transport_modules_launch_nothing_and_import_no_provider_or_network_sdk() -> (
    None
):
    text = "\n".join(
        (ROOT / "company" / "runtime" / name).read_text(encoding="utf-8").casefold()
        for name in (
            "authority.py",
            "transport.py",
            "execution_store.py",
            "execution_cli.py",
            "session_adapter.py",
            "context_expansion.py",
            "context_expansion_policy.py",
            "__main__.py",
        )
    )
    for token in (
        "import subprocess",
        "import anthropic",
        "import openai",
        "import requests",
        "multiprocessing",
        "os.system",
        "popen",
        "asyncio",
    ):
        assert token not in text


# --- The CLI write-scope path -------------------------------------------------
#
# `--authority-override-file` is the only way `python -m company.runtime packet`
# can hand out a writable path: `contract_from_registry` produces an empty
# `may_write`, and `_assert_scope_within_contract` reads empty as "grants
# nothing". That worked from the day the audited transport landed and was never
# covered, so the CLI read as if it could not grant write scope at all. These
# tests pin the behaviour in both directions.


def _cli_task_file(tmp_path: Path, task_id: str) -> Path:
    task_file = tmp_path / f"{task_id}.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "objective": "Exercise the CLI write-scope path end to end.",
                "required_capabilities": [
                    "software_implementation",
                    "test_engineering",
                ],
                "deterministic_execution_possible": False,
                "context": {
                    "refs": [
                        {
                            "kind": "file",
                            "ref": "company/runtime/packets.py",
                            "reason": "initial packet boundary",
                        }
                    ],
                    "constraints": ["Do not modify production systems."],
                    "acceptance_criteria": ["The CLI write-scope path succeeds."],
                },
            }
        ),
        encoding="utf-8",
    )
    return task_file


def _override_file(tmp_path: Path, name: str, payload: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _packet_argv(task_file: Path, *extra: str) -> list[str]:
    return ["packet", str(task_file), "--branch", BRANCH, *extra]


def test_cli_packet_without_an_override_is_still_the_read_only_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Omitting the argument must not change what the CLI did before."""
    task_file = _cli_task_file(tmp_path, "cli-scope-readonly")

    assert runtime_main(_packet_argv(task_file)) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["packet"]["path_scope"] == {"allowed": [], "forbidden": []}
    assert payload["packet"]["employee"] == "software_implementation_engineer"
    assert payload["fingerprint"]


def test_cli_packet_accepts_an_override_and_carries_the_bounded_write_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    task_file = _cli_task_file(tmp_path, "cli-scope-granted")
    override = _override_file(
        tmp_path,
        "authority.json",
        {
            "may_read": ["company/runtime"],
            "may_write": ["tests/test_company_execution_transport.py"],
            "may_not_read": [],
            "may_not_modify": ["company/permissions.yaml"],
        },
    )
    state = tmp_path / "state"

    assert (
        runtime_main(
            _packet_argv(
                task_file,
                "--allow",
                "tests/test_company_execution_transport.py",
                "--authority-override-file",
                str(override),
                "--state-dir",
                str(state),
            )
        )
        == 0
    )

    payload = json.loads(capsys.readouterr().out)
    assert payload["packet"]["path_scope"] == {
        "allowed": ["tests/test_company_execution_transport.py"],
        "forbidden": [],
    }
    # The grant is recorded as an override, never as the canonical contract.
    assert (
        payload["authority"]["source"] == AuthoritySource.TEMPORARY_TASK_OVERRIDE.value
    )
    snapshot = ExecutionStore(state).authority(
        "cli-scope-granted", payload["fingerprint"], 1
    )
    assert snapshot is not None
    assert snapshot.may_write == ("tests/test_company_execution_transport.py",)
    assert snapshot.fingerprint() == payload["authority"]["fingerprint"]


def test_cli_packet_refuses_a_path_the_override_does_not_grant(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The ceiling is `may_write` itself: an unnamed path is outside it."""
    task_file = _cli_task_file(tmp_path, "cli-scope-ceiling")
    override = _override_file(
        tmp_path, "narrow.json", {"may_write": ["tests/test_company_runtime.py"]}
    )

    assert (
        runtime_main(
            _packet_argv(
                task_file,
                "--allow",
                "company/runtime",
                "--authority-override-file",
                str(override),
            )
        )
        == 2
    )
    assert (
        "outside software_implementation_engineer's may_write"
        in capsys.readouterr().err
    )


def test_cli_packet_refuses_a_granted_path_that_reaches_may_not_modify(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`may_not_modify` outranks `may_write` through the CLI too."""
    task_file = _cli_task_file(tmp_path, "cli-scope-protected")
    override = _override_file(
        tmp_path,
        "conflicting.json",
        {"may_write": ["company"], "may_not_modify": ["company/permissions.yaml"]},
    )

    assert (
        runtime_main(
            _packet_argv(
                task_file,
                "--allow",
                "company",
                "--authority-override-file",
                str(override),
            )
        )
        == 2
    )
    assert "reaches software_implementation_engineer's may_not_modify" in (
        capsys.readouterr().err
    )


def test_cli_packet_refuses_an_override_carrying_a_non_authority_field(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """An override may move authority and nothing else - not identity."""
    task_file = _cli_task_file(tmp_path, "cli-scope-invalid")
    override = _override_file(
        tmp_path,
        "invalid.json",
        {"may_write": ["tests"], "employee_id": "chief_architect"},
    )

    assert (
        runtime_main(
            _packet_argv(
                task_file,
                "--allow",
                "tests",
                "--authority-override-file",
                str(override),
            )
        )
        == 2
    )
    assert "unknown/non-authority field(s): employee_id" in capsys.readouterr().err


def test_cli_packet_refuses_a_missing_override_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A named-but-absent grant is an error, never a silent read-only packet."""
    task_file = _cli_task_file(tmp_path, "cli-scope-missing")

    assert (
        runtime_main(
            _packet_argv(
                task_file,
                "--allow",
                "tests",
                "--authority-override-file",
                str(tmp_path / "absent.json"),
            )
        )
        == 2
    )
    assert "absent.json" in capsys.readouterr().err


def test_cli_packet_write_scope_leaves_the_other_commands_alone(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """No expansion or ingestion command grew an authority argument."""
    assert runtime_main(["validate"]) == 0
    assert "configuration is valid" in capsys.readouterr().out
    for argv in (
        [
            "context-request",
            "--state-dir",
            str(tmp_path),
            "--task",
            "t",
            "--kind",
            "file",
            "--ref",
            INDEX_PATH,
            "--reason",
            "r",
        ],
        ["receipt", "r.json", "--task", "t.json", "--state-dir", str(tmp_path)],
    ):
        with pytest.raises(SystemExit):
            build_parser().parse_args([*argv, "--authority-override-file", "a.json"])
