"""The command surface. One command per stage, and none of them integrates.

    python -m company.engineering request  --request-file r.json --state-dir S --repo-root .
    python -m company.engineering brief    --work-order WO --state-dir S
    python -m company.engineering receipt  --work-order WO --receipt-file x.json --state-dir S
    python -m company.engineering review-brief --work-order WO --implementer E --state-dir S
    python -m company.engineering review   --work-order WO --attestation-file a.json --state-dir S
    python -m company.engineering gate     --work-order WO --gate-report g.json --state-dir S
    python -m company.engineering execution-stop --work-order WO --reason R --state-dir S
    python -m company.engineering result   --work-order WO --state-dir S
    python -m company.engineering decide   --work-order WO --decision-file d.json --state-dir S
    python -m company.engineering status   --work-order WO --state-dir S
    python -m company.engineering verify   --work-order WO --state-dir S --repo-root .

`--state-dir` is always explicit and never defaulted: engineering state is
company state, and a command that picks its own directory writes history
somewhere nobody looks.

The exit code is the stage's answer, so a script can branch on it without
parsing prose: 0 when the stage advanced, 1 when it stopped on evidence
(decision required, review not passed, gate not ready), 2 on a malformed input
or an illegal move. `result` exits 0 only when the job is `ready_for_approval`.

## Three commands that write nothing

`status`, `verify` and `result` read. `result` appends the CEO page it renders,
because the page the CEO was shown is itself evidence; `--no-store` prints it
without recording. `verify` never writes and never moves the job: a drift check
is an observation, and an observation that could block a job would block work
review has not looked at yet. Nothing in this module merges, pushes, publishes
or deploys, and `gate` cannot evaluate the gate — it reads a report `python -m
company.integration check --json` wrote.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any

from ai_platform.policy import SubagentPolicyViolation
from ai_platform.serde import to_jsonable
from company.runtime.config import load_validated_company_config
from company.runtime.execution_store import ExecutionStore
from company.runtime.packets import ExecutorHint
from company.runtime.receipts import SessionReceipt
from company.runtime.usage_store import ResourceUsageStore
from company.validation.errors import CompanyOSError

from .decision import CEODecision
from .errors import EngineeringError
from .gate_evidence import GateVerdict
from .intake import CEORequest, IntakeOutcome, assess_request
from .lifecycle import JobState
from .orchestrator import (
    ingest_developer_result,
    open_job,
    prepare_developer_session,
    prepare_review_session,
    publish_result,
    record_decision,
    record_execution_stop,
    record_gate,
    record_review,
)
from .result import EngineeringResult
from .review import ReviewOutcome, ReviewerAttestation
from .store import EngineeringStore
from .transport import developer_briefing_payload, review_briefing_payload
from .verify import DriftStatus, verify_all, verify_work_order

# Exit codes. Distinct from each other so a caller can branch on the stage's
# answer rather than on its text.
_ADVANCED = 0
_STOPPED = 1
_REFUSED = 2


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m company.engineering")
    root.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="directory holding the four Company OS bootstrap YAML files",
    )
    commands = root.add_subparsers(dest="command", required=True)

    request = commands.add_parser(
        "request", help="assess one CEO request and open a job, or report decisions"
    )
    request.add_argument("--request-file", type=Path, required=True)
    request.add_argument("--state-dir", type=Path, required=True)
    request.add_argument("--repo-root", type=Path, default=Path("."))
    request.add_argument("--work-order-id", default="")
    request.add_argument("--as-of", type=dt.date.fromisoformat, default=None)

    brief = commands.add_parser(
        "brief", help="issue one developer packet for an external session"
    )
    _common(brief)
    brief.add_argument(
        "--executor",
        choices=[hint.value for hint in ExecutorHint],
        default=ExecutorHint.UNSPECIFIED.value,
        help="metadata only; no behaviour depends on it",
    )

    receipt = commands.add_parser(
        "receipt",
        help=(
            "validate and record one developer receipt; a receipt rejected for "
            "its required-test evidence shape alone (evidence_rejected: true) "
            "leaves the job in developing so a corrected receipt for the same "
            "commit can be resubmitted here without spending another attempt"
        ),
    )
    _common(receipt)
    receipt.add_argument("--receipt-file", type=Path, required=True)
    receipt.add_argument(
        "--repo-dir",
        type=Path,
        default=None,
        help="a local clone, so branch and remote claims are checked against real refs",
    )

    review_brief = commands.add_parser(
        "review-brief", help="issue one read-only review packet to a different employee"
    )
    _common(review_brief)
    review_brief.add_argument("--implementer", required=True)
    review_brief.add_argument(
        "--executor",
        choices=[hint.value for hint in ExecutorHint],
        default=ExecutorHint.UNSPECIFIED.value,
    )

    review = commands.add_parser("review", help="adjudicate one reviewer attestation")
    _common(review)
    review.add_argument("--attestation-file", type=Path, required=True)
    review.add_argument("--implementer", required=True)
    review.add_argument("--repo-root", type=Path, default=Path("."))

    gate = commands.add_parser(
        "gate", help="record the integration gate's own report as this job's evidence"
    )
    _common(gate)
    gate.add_argument(
        "--gate-report",
        type=Path,
        required=True,
        help="JSON written by `python -m company.integration check --json`",
    )
    gate.add_argument(
        "--reported-readiness",
        default="",
        help="the gate CLI's verdict, cross-checked against the report itself",
    )
    gate.add_argument(
        "--implementation-commit",
        default="",
        help="the commit the gate must describe; default is the developer's reported commit",
    )

    execution_stop = commands.add_parser(
        "execution-stop",
        help="record that an external model/backend stopped and require a CEO decision",
    )
    _common(execution_stop)
    execution_stop.add_argument("--reason", required=True)

    result = commands.add_parser("result", help="render the CEO page for this job")
    _common(result)
    result.add_argument("--json", action="store_true")
    result.add_argument(
        "--no-store", action="store_true", help="print the page without recording it"
    )
    result.add_argument(
        "--risk", action="append", default=[], help="one remaining uncertainty"
    )

    decide = commands.add_parser("decide", help="record one CEO decision")
    _common(decide)
    decide.add_argument("--decision-file", type=Path, required=True)

    status = commands.add_parser("status", help="show one job's state and history")
    _common(status)

    verify = commands.add_parser(
        "verify",
        help="re-read a work order's protected governance surface; writes nothing",
    )
    verify.add_argument("--state-dir", type=Path, required=True)
    verify.add_argument("--repo-root", type=Path, default=Path("."))
    verify.add_argument("--as-of", type=dt.date.fromisoformat, default=None)
    verify.add_argument(
        "--work-order",
        dest="work_order_id",
        default="",
        help="one work order; omitted checks every work order the store holds",
    )
    verify.add_argument("--json", action="store_true")

    listing = commands.add_parser("list", help="every work order this state directory holds")
    listing.add_argument("--state-dir", type=Path, required=True)
    return root


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--work-order", dest="work_order_id", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--as-of", type=dt.date.fromisoformat, default=None)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _dispatch(args)
    except (CompanyOSError, SubagentPolicyViolation, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return _REFUSED


def _dispatch(args: argparse.Namespace) -> int:
    handlers = {
        "request": _request,
        "brief": _brief,
        "receipt": _receipt,
        "review-brief": _review_brief,
        "review": _review,
        "gate": _gate,
        "execution-stop": _execution_stop,
        "result": _result,
        "decide": _decide,
        "status": _status,
        "verify": _verify,
        "list": _list,
    }
    return handlers[args.command](args)


def _emit(payload: Any) -> None:
    print(json.dumps(to_jsonable(payload), indent=2, sort_keys=True))


def _day(args: argparse.Namespace, fallback: dt.date) -> dt.date:
    return args.as_of or fallback


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EngineeringError(f"{path}: expected a JSON object")
    return data


def _order_and_job(args: argparse.Namespace):
    store = EngineeringStore(args.state_dir)
    order = store.work_order(args.work_order_id)
    if order is None:
        raise EngineeringError(
            f"no work order {args.work_order_id!r} in {args.state_dir}. Run `request` "
            "first, or check the id with `list`."
        )
    job = store.job(args.work_order_id)
    if job is None:
        raise EngineeringError(f"work order {args.work_order_id} has no job record")
    return store, order, job


# --- stages ---------------------------------------------------------------


def _request(args: argparse.Namespace) -> int:
    config = load_validated_company_config(args.config_dir)
    request = CEORequest.from_mapping(_load(args.request_file))
    assessment = assess_request(
        request,
        config.permissions,
        repo_root=args.repo_root,
        work_order_id=args.work_order_id,
        authorized_on=args.as_of or request.requested_on,
    )
    store = EngineeringStore(args.state_dir)
    if assessment.outcome in (
        IntakeOutcome.DECISION_REQUIRED,
        IntakeOutcome.PLANNING_REQUIRED,
    ):
        pointer = store.append_request(assessment.request)
        _emit(
            {
                "outcome": assessment.outcome.value,
                "request": pointer.to_dict(),
                "derivation": assessment.derivation.to_dict(),
                "decisions": [item.to_dict() for item in assessment.decisions],
            }
        )
        return _STOPPED
    opened = open_job(store, assessment, on=args.as_of or request.requested_on)
    _emit(
        {
            "outcome": assessment.outcome.value,
            "work_order_id": opened.work_order.work_order_id,
            "work_order_fingerprint": opened.work_order.fingerprint(),
            "state": opened.job.state.value,
            "derivation": assessment.derivation.to_dict(),
            "work_order": opened.work_order.to_dict(),
            "plan": opened.plan.to_dict(),
            "persisted": {
                "request": opened.request_pointer.to_dict(),
                "work_order": opened.work_order_pointer.to_dict(),
                "plan": opened.plan_pointer.to_dict(),
                "job": opened.job_pointer.to_dict(),
            },
        }
    )
    return _ADVANCED


def _brief(args: argparse.Namespace) -> int:
    config = load_validated_company_config(args.config_dir)
    store, order, job = _order_and_job(args)
    briefing = prepare_developer_session(
        store,
        ExecutionStore(args.state_dir),
        order,
        job,
        config,
        on=_day(args, order.authorized_on),
        executor=ExecutorHint(args.executor),
    )
    _emit(developer_briefing_payload(briefing))
    return _ADVANCED


def _receipt(args: argparse.Namespace) -> int:
    config = load_validated_company_config(args.config_dir)
    store, order, job = _order_and_job(args)
    receipt = SessionReceipt.from_mapping(_load(args.receipt_file))
    outcome = ingest_developer_result(
        store,
        ExecutionStore(args.state_dir),
        ResourceUsageStore(args.state_dir),
        order,
        job,
        config,
        receipt,
        on=_day(args, order.authorized_on),
        repo_dir=args.repo_dir,
    )
    _emit(
        {
            "work_order_id": order.work_order_id,
            "state": outcome.job.state.value,
            "accepted": outcome.ingested.accepted,
            "evidence_rejected": outcome.evidence_rejected,
            "packet_attempt": outcome.receipt.packet_attempt,
            "failures": list(outcome.validation.failures),
            "warnings": list(outcome.validation.warnings),
            "receipt_ref": outcome.ingested.receipt_pointer.record_ref,
            # The digest a later attestation has to name. It is computed while
            # the receipt is stored and was, until now, the one identifier a
            # caller could not obtain from this command line, so preparing a
            # review meant computing it by hand in a Python session. Printing
            # a value the store already holds grants nothing and removes a
            # manual step from every review.
            "receipt_fingerprint": outcome.ingested.receipt_pointer.fingerprint,
            "usage_record": outcome.ingested.attempt.usage_pointer.to_dict(),
            "handoff": to_jsonable(outcome.ingested.attempt.handoff),
        }
    )
    return _ADVANCED if outcome.ingested.accepted else _STOPPED


def _review_brief(args: argparse.Namespace) -> int:
    config = load_validated_company_config(args.config_dir)
    store, order, job = _order_and_job(args)
    briefing = prepare_review_session(
        store,
        ExecutionStore(args.state_dir),
        order,
        job,
        config,
        implementer=args.implementer,
        on=_day(args, order.authorized_on),
        executor=ExecutorHint(args.executor),
    )
    _emit(review_briefing_payload(briefing))
    return _ADVANCED


def _review(args: argparse.Namespace) -> int:
    config = load_validated_company_config(args.config_dir)
    store, order, job = _order_and_job(args)
    execution_store = ExecutionStore(args.state_dir)
    attestation = ReviewerAttestation.from_mapping(_load(args.attestation_file))
    packet = _packet_by_fingerprint(execution_store, order, attestation.packet_fingerprint)
    receipt = _receipt_by_fingerprint(
        execution_store, order, attestation.receipt_fingerprint
    )
    outcome = record_review(
        store,
        execution_store,
        order,
        job,
        config,
        attestation,
        packet,
        receipt,
        implementer=args.implementer,
        repo_root=args.repo_root,
        on=_day(args, attestation.reviewed_on),
    )
    _emit(
        {
            "work_order_id": order.work_order_id,
            "state": outcome.job.state.value,
            "review": outcome.review.to_dict(),
            "persisted": {
                "attestation": outcome.attestation_pointer.to_dict(),
                "review": outcome.review_pointer.to_dict(),
                "job": outcome.job_pointer.to_dict(),
            },
        }
    )
    return _ADVANCED if outcome.review.outcome is ReviewOutcome.PASS else _STOPPED


def _gate(args: argparse.Namespace) -> int:
    store, order, job = _order_and_job(args)
    verdict = GateVerdict.from_report_path(
        args.gate_report,
        work_order_id=order.work_order_id,
        reported_readiness=args.reported_readiness,
    )
    receipts = ExecutionStore(args.state_dir).receipts(order.work_order_id)
    commit = args.implementation_commit or (
        receipts[-1].commit_sha if receipts else ""
    )
    moved, gate_pointer, job_pointer = record_gate(
        store,
        order,
        job,
        verdict,
        on=_day(args, verdict.as_of),
        implementation_commit=commit,
    )
    _emit(
        {
            "work_order_id": order.work_order_id,
            "state": moved.state.value,
            "implementation_commit": commit,
            "stale": verdict.stale_against(commit),
            "gate": verdict.to_dict(),
            "persisted": {
                "gate_verdict": gate_pointer.to_dict(),
                "job": job_pointer.to_dict(),
            },
        }
    )
    return _ADVANCED if moved.state is JobState.READY_FOR_APPROVAL else _STOPPED


def _execution_stop(args: argparse.Namespace) -> int:
    store, order, job = _order_and_job(args)
    moved, job_pointer = record_execution_stop(
        store,
        order,
        job,
        reason=args.reason,
        on=_day(args, dt.date.today()),
    )
    _emit(
        {
            "work_order_id": order.work_order_id,
            "state": moved.state.value,
            "reason": args.reason,
            "persisted": {"job": job_pointer.to_dict()},
        }
    )
    return _STOPPED


def _result(args: argparse.Namespace) -> int:
    store, order, job = _order_and_job(args)
    receipts = ExecutionStore(args.state_dir).receipts(order.work_order_id)
    parts = {
        "receipt": receipts[-1] if receipts else None,
        "review": store.review(order.work_order_id),
        "gate": store.gate_verdict(order.work_order_id),
        "risks": tuple(args.risk),
    }
    if args.no_store:
        result = EngineeringResult.build(order, job, **parts)
        pointer = None
    else:
        result, pointer = publish_result(store, order, job, **parts)
    if args.json:
        payload = result.to_dict()
        if pointer is not None:
            payload["persisted"] = pointer.to_dict()
        _emit(payload)
    else:
        print(result.render_text(), end="")
        if pointer is not None:
            print(f"recorded    {pointer.record_ref}")
    return _ADVANCED if result.status is JobState.READY_FOR_APPROVAL else _STOPPED


def _decide(args: argparse.Namespace) -> int:
    store, order, job = _order_and_job(args)
    decision = CEODecision.from_mapping(_load(args.decision_file))
    moved, decision_pointer, job_pointer = record_decision(store, order, job, decision)
    _emit(
        {
            "work_order_id": order.work_order_id,
            "state": moved.state.value,
            "verdict": decision.verdict.value,
            "decided_by": decision.decided_by,
            "authorizes_merge": decision.authorizes_merge,
            "note": (
                "recorded. Nothing was merged, deployed or published: Company OS holds "
                "no capability to do any of them."
            ),
            "persisted": {
                "decision": decision_pointer.to_dict(),
                "job": job_pointer.to_dict(),
            },
        }
    )
    return _ADVANCED


def _status(args: argparse.Namespace) -> int:
    store = EngineeringStore(args.state_dir)
    history = store.history(args.work_order_id)
    history["integrity"] = list(store.integrity(args.work_order_id))
    _emit(history)
    job = store.job(args.work_order_id)
    if job is None:
        return _REFUSED
    return _ADVANCED if job.state is JobState.READY_FOR_APPROVAL else _STOPPED


def _verify(args: argparse.Namespace) -> int:
    """Answer the drift question without completing a review, and without writing."""
    store = EngineeringStore(args.state_dir)
    day = args.as_of or dt.date.today()
    if args.work_order_id:
        reports = (
            verify_work_order(
                store, args.work_order_id, repo_root=args.repo_root, on=day
            ),
        )
    else:
        reports = verify_all(store, repo_root=args.repo_root, on=day)
    if args.json:
        _emit({"reports": [item.to_dict() for item in reports]})
    elif not reports:
        print(f"no work order is stored under {args.state_dir}")
    else:
        for item in reports:
            print(item.render_text(), end="")
    if any(item.status is DriftStatus.DRIFTED for item in reports):
        return _STOPPED
    if not reports or any(item.status is DriftStatus.UNKNOWN for item in reports):
        return _REFUSED
    return _ADVANCED


def _list(args: argparse.Namespace) -> int:
    store = EngineeringStore(args.state_dir)
    rows = []
    for work_order_id in store.work_order_ids():
        job = store.job(work_order_id)
        order = store.work_order(work_order_id)
        rows.append(
            {
                "work_order_id": work_order_id,
                "state": job.state.value if job else "",
                "objective": order.objective if order else "",
                "developer_attempts": job.developer_attempts if job else 0,
                "awaits_ceo": job.awaits_ceo if job else False,
            }
        )
    _emit({"work_orders": rows})
    return _ADVANCED


def _packet_by_fingerprint(execution_store: ExecutionStore, order, fingerprint: str):
    for record in execution_store.packet_records(order.work_order_id):
        if record.packet.fingerprint() == fingerprint:
            return record.packet
    raise EngineeringError(
        f"the attestation answers packet {fingerprint}, which is not in this work "
        f"order's execution history"
    )


def _receipt_by_fingerprint(execution_store: ExecutionStore, order, fingerprint: str):
    for candidate in execution_store.receipts(order.work_order_id):
        if candidate.fingerprint() == fingerprint:
            return candidate
    raise EngineeringError(
        f"the attestation reviews receipt {fingerprint}, which is not in this work "
        f"order's execution history"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
