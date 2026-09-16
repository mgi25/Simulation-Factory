"""Small development CLI for the Company OS runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from ai_platform.policy import SubagentPolicyViolation
from ai_platform.serde import to_jsonable
from company.validation.errors import CompanyOSError

from .config import load_validated_company_config
from .execution_store import ExecutionStore
from .lifecycle import plan_task
from .packets import ExecutorHint, build_session_packet
from .path_scope import PathScope
from .receipts import SessionReceipt
from .routing import match_capabilities
from .session_adapter import ManualExternalSessionAdapter
from .specification import TaskSpecification
from .usage_store import ResourceUsageStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m company.runtime")
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="directory containing the four Company OS bootstrap YAML files",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate bootstrap configuration")
    subparsers.add_parser("employees", help="list employees deterministically")
    match = subparsers.add_parser("match", help="match required capabilities")
    match.add_argument("capabilities", nargs="+", help="required capability names")
    plan = subparsers.add_parser("plan", help="plan a task from a JSON specification")
    plan.add_argument("task_file", type=Path, help="path to a JSON task specification")
    usage = subparsers.add_parser("usage", help="query persisted resource usage")
    usage.add_argument("state_dir", type=Path, help="explicit runtime state directory")
    usage.add_argument("--task", dest="task_id", help="limit the scope to one task ID")

    packet = subparsers.add_parser(
        "packet", help="build a session packet for an external top-level session"
    )
    packet.add_argument("task_file", type=Path, help="path to a JSON task specification")
    packet.add_argument("--branch", required=True, help="the branch the session is assigned")
    packet.add_argument("--allow", action="append", default=[], help="an allowed path prefix")
    packet.add_argument("--forbid", action="append", default=[], help="a forbidden path prefix")
    packet.add_argument("--test", action="append", default=[], help="a required test command")
    packet.add_argument("--base-commit", default="", help="the expected base commit SHA")
    packet.add_argument(
        "--executor",
        choices=[hint.value for hint in ExecutorHint],
        default=ExecutorHint.UNSPECIFIED.value,
        help="metadata only; no behaviour depends on it",
    )
    packet.add_argument(
        "--state-dir", type=Path, default=None, help="persist the packet to this outbox"
    )

    receipt = subparsers.add_parser(
        "receipt", help="validate and record a receipt returned by an external session"
    )
    receipt.add_argument("receipt_file", type=Path, help="path to a JSON session receipt")
    receipt.add_argument(
        "--task", dest="task_file", type=Path, required=True, help="the task specification"
    )
    receipt.add_argument(
        "--state-dir", type=Path, required=True, help="explicit runtime state directory"
    )

    execution = subparsers.add_parser(
        "execution", help="show the append-only execution history for one task"
    )
    execution.add_argument(
        "--state-dir", type=Path, required=True, help="explicit runtime state directory"
    )
    execution.add_argument("--task", dest="task_id", required=True, help="task ID")
    return parser


def _task_plan(task_file: Path, config_dir: Path | None):
    raw = json.loads(task_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("task specification must be a JSON object")
    return plan_task(
        TaskSpecification.from_mapping(raw), load_validated_company_config(config_dir)
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "execution":
            store = ExecutionStore(args.state_dir)
            print(json.dumps(store.history(args.task_id), indent=2, sort_keys=True))
            return 0

        if args.command == "packet":
            adapter_store = (
                ExecutionStore(args.state_dir) if args.state_dir is not None else None
            )
            plan = _task_plan(args.task_file, args.config_dir)
            scope = PathScope(allowed=tuple(args.allow), forbidden=tuple(args.forbid))
            packet = build_session_packet(
                plan,
                expected_branch=args.branch,
                path_scope=scope,
                required_tests=tuple(args.test),
                expected_base_commit=args.base_commit,
                executor=ExecutorHint(args.executor),
            )
            payload = {
                "packet": packet.to_dict(),
                "fingerprint": packet.fingerprint(),
                "size_chars": packet.size_chars(),
            }
            if adapter_store is not None:
                payload["persisted"] = adapter_store.append_packet(packet).to_dict()
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        if args.command == "receipt":
            raw = json.loads(args.receipt_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("session receipt must be a JSON object")
            receipt = SessionReceipt.from_mapping(raw)
            store = ExecutionStore(args.state_dir)
            packet = store.find_packet(receipt.task_id, receipt.packet_fingerprint)
            if packet is None:
                raise ValueError(
                    f"no persisted packet {receipt.packet_fingerprint} for task "
                    f"{receipt.task_id}; a receipt is only ingested against the packet "
                    "it answers"
                )
            plan = _task_plan(args.task_file, args.config_dir)
            ingested = ManualExternalSessionAdapter(store).ingest(
                plan, packet, receipt, ResourceUsageStore(args.state_dir)
            )
            print(
                json.dumps(
                    {
                        "accepted": ingested.accepted,
                        "attempt": ingested.receipt_pointer.attempt,
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

        if args.command == "usage":
            store = ResourceUsageStore(args.state_dir)
            records = store.records(args.task_id)
            print(
                json.dumps(
                    {
                        "records": [record.to_dict() for record in records],
                        "summary": to_jsonable(store.summarise(args.task_id)),
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        config = load_validated_company_config(args.config_dir)
        if args.command == "validate":
            count = len(config.org_registry["employees"])
            print(f"Company OS bootstrap configuration is valid ({count} employees).")
        elif args.command == "employees":
            for employee_id, employee in sorted(config.org_registry["employees"].items()):
                capabilities = ",".join(employee["capabilities"])
                print(
                    f"{employee_id}\t{employee['state']}\t{employee['department']}\t"
                    f"manager={employee['manager']}\tcapabilities={capabilities}"
                )
        elif args.command == "match":
            result = match_capabilities(args.capabilities, config)
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        elif args.command == "plan":
            raw = json.loads(args.task_file.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("task specification must be a JSON object")
            plan = plan_task(TaskSpecification.from_mapping(raw), config)
            print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    except (CompanyOSError, OSError, ValueError, SubagentPolicyViolation) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
