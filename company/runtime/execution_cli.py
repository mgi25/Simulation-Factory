"""CLI parser and handlers for the manual execution transport."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.serde import to_jsonable

from .config import load_validated_company_config
from .context_expansion import ContextExpansionRequest
from .execution_store import ExecutionStore, PacketRecord
from .lifecycle import contract_from_registry, plan_task
from .packets import ExecutorHint, build_session_packet
from .path_scope import PathScope
from .receipts import SessionReceipt
from .session_adapter import ManualExternalSessionAdapter
from .specification import TaskSpecification
from .transport import SessionTransportBundle
from .usage_store import ResourceUsageStore


COMMANDS = frozenset(
    {"packet", "receipt", "context-request", "context-decide", "execution"}
)
_OVERRIDE_FIELDS = frozenset(
    {"may_read", "may_write", "may_not_read", "may_not_modify", "autonomy_level"}
)


def add_parsers(subparsers: Any) -> None:
    packet = subparsers.add_parser(
        "packet", help="build a session packet for an external top-level session"
    )
    packet.add_argument(
        "task_file", type=Path, help="path to a JSON task specification"
    )
    packet.add_argument(
        "--branch", required=True, help="the branch the session is assigned"
    )
    packet.add_argument(
        "--allow", action="append", default=[], help="an allowed path prefix"
    )
    packet.add_argument(
        "--forbid", action="append", default=[], help="a forbidden path prefix"
    )
    packet.add_argument(
        "--test", action="append", default=[], help="a required test command"
    )
    packet.add_argument(
        "--base-commit", default="", help="the expected base commit SHA"
    )
    packet.add_argument(
        "--executor",
        choices=[hint.value for hint in ExecutorHint],
        default=ExecutorHint.UNSPECIFIED.value,
        help="metadata only; no behaviour depends on it",
    )
    packet.add_argument(
        "--state-dir", type=Path, default=None, help="persist the packet to this outbox"
    )
    packet.add_argument(
        "--authority-override-file",
        type=Path,
        default=None,
        help="preparation-time JSON authority override; never accepted by expansion commands",
    )

    receipt = subparsers.add_parser(
        "receipt", help="validate and record a receipt returned by an external session"
    )
    receipt.add_argument(
        "receipt_file", type=Path, help="path to a JSON session receipt"
    )
    receipt.add_argument(
        "--task",
        dest="task_file",
        type=Path,
        required=True,
        help="the task specification",
    )
    receipt.add_argument(
        "--state-dir", type=Path, required=True, help="explicit runtime state directory"
    )
    receipt.add_argument(
        "--attempt",
        type=int,
        default=None,
        help="packet attempt; default is the latest matching incomplete attempt",
    )

    context_request = subparsers.add_parser(
        "context-request",
        help="persist a bounded request for one additional context ref",
    )
    context_request.add_argument("--state-dir", type=Path, required=True)
    context_request.add_argument("--task", dest="task_id", required=True)
    context_request.add_argument("--attempt", type=int, default=None)
    context_request.add_argument(
        "--kind", choices=[kind.value for kind in ContextKind], required=True
    )
    context_request.add_argument("--ref", dest="context_ref", required=True)
    context_request.add_argument("--reason", required=True)
    context_request.add_argument("--required", action="store_true")
    context_request.add_argument(
        "--executor",
        choices=[hint.value for hint in ExecutorHint],
        default=ExecutorHint.UNSPECIFIED.value,
    )

    context_decide = subparsers.add_parser(
        "context-decide", help="decide a stored request from immutable authority"
    )
    context_decide.add_argument("--state-dir", type=Path, required=True)
    context_decide.add_argument("--task", dest="task_id", required=True)
    context_decide.add_argument("--request", dest="request_id", required=True)
    context_decide.add_argument("--repo-root", type=Path, default=None)

    execution = subparsers.add_parser(
        "execution", help="show the append-only execution history for one task"
    )
    execution.add_argument(
        "--state-dir", type=Path, required=True, help="explicit runtime state directory"
    )
    execution.add_argument("--task", dest="task_id", required=True, help="task ID")


def handle(args: argparse.Namespace) -> int | None:
    if args.command not in COMMANDS:
        return None
    if args.command == "execution":
        return _execution(args)
    if args.command == "context-request":
        return _context_request(args)
    if args.command == "context-decide":
        return _context_decide(args)
    if args.command == "packet":
        return _packet(args)
    return _receipt(args)


def _task_plan(
    task_file: Path,
    config_dir: Path | None,
    *,
    employee_contract: dict[str, object] | None = None,
):
    raw = json.loads(task_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task specification must be a JSON object")
    return plan_task(
        TaskSpecification.from_mapping(raw),
        load_validated_company_config(config_dir),
        employee_contract=employee_contract,
    )


def _temporary_authority(plan: object, override_file: Path) -> dict[str, object]:
    raw = json.loads(override_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("authority override must be a JSON object")
    unknown = sorted(set(raw) - _OVERRIDE_FIELDS)
    if unknown:
        raise ValueError(
            "authority override has unknown/non-authority field(s): "
            + ", ".join(unknown)
        )
    employee = getattr(plan, "selected_employee", None)
    config = getattr(plan, "config", None)
    if not isinstance(employee, str) or config is None:
        raise ValueError("authority override requires a prepared employee selection")
    contract = contract_from_registry(employee, config)
    contract.update(raw)
    return contract


def _select_packet(
    store: ExecutionStore, task_id: str, attempt: int | None
) -> PacketRecord:
    records = store.packet_records(task_id)
    if attempt is not None:
        record = next((item for item in records if item.attempt == attempt), None)
        if record is None:
            raise ValueError(f"no packet attempt {attempt} for task {task_id}")
        return record
    completed = {
        item.receipt.packet_attempt
        for item in store.attempts(task_id)
        if item.receipt.packet_attempt
    }
    incomplete = tuple(item for item in records if item.attempt not in completed)
    if not incomplete:
        raise ValueError(
            f"task {task_id} has no incomplete packet attempt; pass --attempt explicitly"
        )
    return incomplete[-1]


def _select_receipt_packet(
    store: ExecutionStore,
    task_id: str,
    fingerprint: str,
    attempt: int | None,
) -> PacketRecord | None:
    if attempt is not None:
        return store.find_packet_record(task_id, fingerprint, attempt=attempt)
    completed = {
        item.receipt.packet_attempt
        for item in store.attempts(task_id)
        if item.receipt.packet_attempt
    }
    candidates = tuple(
        item
        for item in store.packet_records(task_id)
        if item.packet.fingerprint() == fingerprint and item.attempt not in completed
    )
    return candidates[-1] if candidates else None


def _execution(args: argparse.Namespace) -> int:
    store = ExecutionStore(args.state_dir)
    history = store.history(args.task_id)
    history["usage_references"] = [
        pointer.to_dict()
        for pointer in ResourceUsageStore(args.state_dir).pointers(args.task_id)
    ]
    print(json.dumps(history, indent=2, sort_keys=True))
    return 0


def _context_request(args: argparse.Namespace) -> int:
    store = ExecutionStore(args.state_dir)
    record = _select_packet(store, args.task_id, args.attempt)
    authority = store.authority(
        args.task_id, record.packet.fingerprint(), record.attempt
    )
    if authority is None:
        raise ValueError(f"packet attempt {record.attempt} has no authority snapshot")
    decisions = tuple(
        item
        for item in store.context_expansion_decisions(args.task_id)
        if item.packet_attempt == record.attempt
        and item.packet_fingerprint == record.packet.fingerprint()
    )
    requests = tuple(
        item
        for item in store.context_expansion_requests(args.task_id)
        if item.packet_attempt == record.attempt
        and item.packet_fingerprint == record.packet.fingerprint()
    )
    decided = {item.request_id for item in decisions}
    pending = tuple(
        item.request_id for item in requests if item.request_id not in decided
    )
    if pending:
        raise ValueError(
            "decide the pending context request before creating another: "
            + ", ".join(pending)
        )
    sequence = len(decisions) + 1
    request = ContextExpansionRequest(
        task_id=args.task_id,
        packet_fingerprint=record.packet.fingerprint(),
        request_id=f"context-a{record.attempt:06d}-r{sequence:06d}",
        requested_refs=(
            ContextRef(
                kind=ContextKind(args.kind),
                ref=args.context_ref,
                reason=args.reason,
            ),
        ),
        reason=args.reason,
        requesting_executor=ExecutorHint(args.executor),
        sequence=sequence,
        required_to_continue=args.required,
        packet_attempt=record.attempt,
    )
    pointer = store.append_context_expansion_request(request)
    print(
        json.dumps(
            {"request": request.to_dict(), "persisted": pointer.to_dict()},
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _context_decide(args: argparse.Namespace) -> int:
    store = ExecutionStore(args.state_dir)
    request = store.find_context_expansion_request(args.task_id, args.request_id)
    if request is None:
        raise ValueError(
            f"no context expansion request {args.request_id!r} for task {args.task_id}"
        )
    record = store.find_packet_record(
        args.task_id,
        request.packet_fingerprint,
        attempt=request.packet_attempt,
    )
    if record is None:
        raise ValueError("context request names a missing packet attempt")
    expanded = ManualExternalSessionAdapter(store).decide_context(
        record.packet, request, repo_root=args.repo_root
    )
    print(
        json.dumps(
            {
                "decision": expanded.decision.to_dict(),
                "persisted": expanded.decision_pointer.to_dict(),
                "effective_context_fingerprint": (
                    expanded.ledger.effective_context_fingerprint
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _packet(args: argparse.Namespace) -> int:
    adapter_store = (
        ExecutionStore(args.state_dir) if args.state_dir is not None else None
    )
    plan = _task_plan(args.task_file, args.config_dir)
    contract = None
    if args.authority_override_file is not None:
        contract = _temporary_authority(plan, args.authority_override_file)
        plan = _task_plan(args.task_file, args.config_dir, employee_contract=contract)
    scope = PathScope(allowed=tuple(args.allow), forbidden=tuple(args.forbid))
    if adapter_store is not None:
        prepared = ManualExternalSessionAdapter(adapter_store).prepare(
            plan,
            expected_branch=args.branch,
            path_scope=scope,
            required_tests=tuple(args.test),
            expected_base_commit=args.base_commit,
            executor=ExecutorHint(args.executor),
            employee_contract=contract,
        )
        packet = prepared.packet
    else:
        packet = build_session_packet(
            plan,
            expected_branch=args.branch,
            path_scope=scope,
            required_tests=tuple(args.test),
            expected_base_commit=args.base_commit,
            executor=ExecutorHint(args.executor),
            employee_contract=contract,
        )
    payload = {
        "packet": packet.to_dict(),
        "fingerprint": packet.fingerprint(),
        "size_chars": packet.size_chars(),
    }
    if adapter_store is not None:
        ledger = adapter_store.context_expansion_ledger(
            packet, packet_attempt=prepared.pointer.attempt
        )
        payload["persisted"] = prepared.pointer.to_dict()
        payload["authority"] = {
            "record_ref": prepared.authority_pointer.record_ref,
            "fingerprint": prepared.authority.fingerprint(),
            "source": prepared.authority.source.value,
        }
        payload["transport"] = SessionTransportBundle.create(
            packet,
            prepared.pointer,
            prepared.authority,
            prepared.authority_pointer,
            ledger,
        ).to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _receipt(args: argparse.Namespace) -> int:
    raw = json.loads(args.receipt_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("session receipt must be a JSON object")
    receipt = SessionReceipt.from_mapping(raw)
    store = ExecutionStore(args.state_dir)
    record = _select_receipt_packet(
        store,
        receipt.task_id,
        receipt.packet_fingerprint,
        args.attempt or (receipt.packet_attempt or None),
    )
    if record is None:
        raise ValueError(
            f"no incomplete persisted packet {receipt.packet_fingerprint} for task "
            f"{receipt.task_id}; pass --attempt to select an earlier attempt explicitly"
        )
    receipt = replace(receipt, packet_attempt=record.attempt)
    plan = _task_plan(args.task_file, args.config_dir)
    ingested = ManualExternalSessionAdapter(store).ingest(
        plan, record.packet, receipt, ResourceUsageStore(args.state_dir)
    )
    print(
        json.dumps(
            {
                "accepted": ingested.accepted,
                "attempt": ingested.receipt_pointer.attempt,
                "packet_attempt": ingested.receipt.packet_attempt,
                "failures": list(ingested.validation.failures),
                "warnings": list(ingested.validation.warnings),
                "receipt_ref": ingested.receipt_pointer.record_ref,
                "usage_record": ingested.attempt.usage_pointer.to_dict(),
                "handoff": to_jsonable(ingested.attempt.handoff),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if ingested.accepted else 1


__all__ = ["COMMANDS", "add_parsers", "handle"]
