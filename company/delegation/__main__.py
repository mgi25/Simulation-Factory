"""The command surface. Five commands, none of which decides anything.

    python -m company.delegation policy   [--json]
    python -m company.delegation evaluate --request-file r.json [--consumed-file c.json]
    python -m company.delegation replay   [--json]
    python -m company.delegation shadow   [--json]
    python -m company.delegation chart    [--json]
    python -m company.delegation deployment [--json]
    python -m company.delegation report   [--json]

`policy` loads the delegation policy against the canonical bootstrap contracts
and prints the seats, their standing and the conflicts between the declared
chart and `company/org_registry.yaml`. `chart` prints the same hierarchy as an
indented tree, which is the fastest way to see which seats are vacant.

`evaluate` answers one request. `replay` runs the five historical scenarios in
`scenarios.py` and reports where the model agrees with what really happened.
Neither spends anything, opens a session, or writes to a state directory.

`shadow` runs the five probes in `shadow.py` against the canonical CEO decision
record and this package, and exits non-zero if any of them no longer holds.
It is the command to run before trusting anything the others print.

## Exit codes

0 when the command answered, 1 when it answered ESCALATE or found a failing
shadow condition or a replay disagreement, 2 on malformed input. A caller can
branch on the answer without parsing prose, the same convention
`python -m company.engineering` uses.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import datetime as dt
import json
from pathlib import Path
import sys
from typing import Any

from ai_platform.serde import to_jsonable
from company.finance.money import Money
from company.runtime.config import load_company_config
from company.validation.errors import CompanyOSError
from knowledge.company_os.capsules import CapsuleIndex

from .actions import ActionType, parse_action, reservation_drift
from .candidates import CandidateStatus, load_seed_register
from .authority import AuthorityRequest, Decision, evaluate
from .errors import DelegationError
from .exceptions import classify
from .org import CEO_SEAT, SeatKind
from .policy import DelegationPolicy, load_delegation_policy, parse_risk
from .deployment import DEPLOYMENT_POLICY, policy_table
from .metrics import DecisionOutcome, ManagementReport, measure, spend_of
from .scenarios import CONTROL_SCENARIOS, SCENARIOS, replay, summarise
from .objectives import Objective, ObjectiveLevel, PlanningEnvelope
from .planning import eligible_candidates, propose_work_order, select_work
from .planning_record import PlanningOutcome
from .store import DelegationStore
from .shadow import verify_shadow_mode


_ANSWERED = 0
_ESCALATED = 1
_REFUSED = 2


def build_parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="python -m company.delegation")
    root.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="directory holding the four Company OS bootstrap YAML files",
    )
    root.add_argument(
        "--policy-file",
        type=Path,
        default=None,
        help="the delegation policy to load (default company/delegation_policy.yaml)",
    )
    root.add_argument("--json", action="store_true", help="emit JSON instead of text")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("policy", help="load the policy and report seats and conflicts")
    commands.add_parser("chart", help="print the hierarchy as a tree")
    commands.add_parser("replay", help="run the historical scenarios")
    commands.add_parser("shadow", help="probe that the CEO stop semantics still hold")
    commands.add_parser(
        "deployment", help="print the deployment policy model (granted to nobody)"
    )
    commands.add_parser(
        "report", help="the management-by-exception report over the replay"
    )

    candidates_cmd = commands.add_parser(
        "candidates", help="the work candidate register, and what each one is blocked on"
    )
    candidates_cmd.add_argument("--capsule", default="", help="only this capsule")
    candidates_cmd.add_argument(
        "--status", default="", help="only this status (open, blocked, ...)"
    )
    candidates_cmd.add_argument("--seed-file", default="", help="an alternate register")

    plan_cmd = commands.add_parser(
        "plan",
        help="select one candidate for a CEO objective and record the decision",
    )
    plan_cmd.add_argument("--objective-file", required=True)
    plan_cmd.add_argument("--seed-file", default="")
    plan_cmd.add_argument("--state-dir", default="", help="persist the decision here")
    plan_cmd.add_argument("--prefer", default="", help="choose among eligible candidates")
    plan_cmd.add_argument("--as-of", default="", help="the day, YYYY-MM-DD")

    evaluate_cmd = commands.add_parser("evaluate", help="answer one authority request")
    evaluate_cmd.add_argument("--request-file", type=Path, required=True)
    evaluate_cmd.add_argument("--consumed-file", type=Path, default=None)
    return root


def _load_policy(args: argparse.Namespace) -> DelegationPolicy:
    config = load_company_config(args.config_dir)
    return load_delegation_policy(
        org_registry=config.org_registry,
        permissions=config.permissions,
        policy_path=args.policy_file,
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DelegationError(f"cannot read {path}: {exc}") from exc


def _request_from(data: Any) -> AuthorityRequest:
    if not isinstance(data, dict):
        raise DelegationError("a request file must hold a JSON object")
    amount = data.get("amount")
    return AuthorityRequest(
        request_id=str(data.get("request_id", "")),
        action=parse_action(data.get("action"), "request.action"),
        requesting_seat=str(data.get("requesting_seat", "")),
        department=str(data.get("department", "")),
        risk=parse_risk(data.get("risk", "low"), "request.risk"),
        objective_id=str(data.get("objective_id", "") or ""),
        work_order_id=str(data.get("work_order_id", "") or ""),
        budget_scope=str(data.get("budget_scope", "") or ""),
        amount=Money.from_dict(dict(amount), "request.amount") if amount else None,
        summary=str(data.get("summary", "") or ""),
        reversible=bool(data.get("reversible", True)),
        evidence_refs=tuple(data.get("evidence_refs", ())),
        write_scope=tuple(data.get("write_scope", ())),
    )


def _consumed_from(data: Any) -> dict[str, Money]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise DelegationError("a consumption file must hold a JSON object")
    return {
        str(key): Money.from_dict(dict(value), f"consumed[{key}]")
        for key, value in data.items()
    }


def _cmd_policy(args: argparse.Namespace) -> int:
    policy = _load_policy(args)
    standings = policy.hierarchy.standings()
    conflicts = policy.hierarchy.registry_conflicts()
    drift = reservation_drift(policy.hierarchy.permissions)
    payload = {
        "policy_version": policy.version,
        "mode": policy.mode.value,
        "policy_fingerprint": policy.fingerprint(),
        "seats": [item.to_dict() for item in standings],
        "grants": [item.to_dict() for item in policy.grants],
        "reserved": sorted(item.value for item in policy.reserved),
        "registry_conflicts": list(conflicts),
        "reservation_drift": {
            "ok": drift.ok,
            "released": list(drift.released),
            "unmapped": list(drift.unmapped),
        },
        "budget": policy.ladder.to_dict(),
    }
    if args.json:
        print(json.dumps(to_jsonable(payload), indent=2, sort_keys=True))
        return _ANSWERED if drift.ok else _ESCALATED
    print(f"policy {policy.version} mode={policy.mode.value} "
          f"fingerprint={policy.fingerprint()}")
    print("")
    print("SEATS")
    for item in standings:
        grant = policy.grant(item.seat.seat_id)
        limit = f" up to {grant.per_decision_ceiling}" if grant else " no grant"
        print(
            f"  {item.seat.seat_id:<34} {item.availability.value:<15}{limit}"
        )
    print("")
    print(f"RESERVED ({len(policy.reserved)})")
    for name in sorted(item.value for item in policy.reserved):
        print(f"  {name}")
    print("")
    print(f"REGISTRY CONFLICTS ({len(conflicts)})")
    for item in conflicts:
        print(f"  - {item}")
    if not drift.ok:
        print("")
        print("RESERVATION DRIFT")
        for item in drift.released:
            print(f"  - {item}")
        return _ESCALATED
    return _ANSWERED


def _cmd_chart(args: argparse.Namespace) -> int:
    policy = _load_policy(args)
    hierarchy = policy.hierarchy

    lines: list[str] = []

    def walk(seat_id: str, depth: int) -> None:
        standing = hierarchy.standing(seat_id)
        seat = standing.seat
        marker = "" if standing.can_decide else f"  [{standing.availability.value}]"
        role = "" if seat.kind is SeatKind.CEO else f" ({seat.kind.value})"
        lines.append("  " * depth + f"{seat.seat_id}{role}{marker}")
        for child in hierarchy.direct_reports(seat_id):
            walk(child, depth + 1)

    walk(CEO_SEAT, 0)
    if args.json:
        print(json.dumps(to_jsonable(hierarchy.to_dict()), indent=2, sort_keys=True))
        return _ANSWERED
    print("\n".join(lines))
    return _ANSWERED


def _cmd_evaluate(args: argparse.Namespace) -> int:
    policy = _load_policy(args)
    request = _request_from(_read_json(args.request_file))
    consumed = _consumed_from(
        _read_json(args.consumed_file) if args.consumed_file else None
    )
    decision = evaluate(request, policy, consumed=consumed)
    report = classify(decision)
    payload = {
        "decision": decision.to_dict(),
        "exceptions": report.to_dict(),
    }
    if args.json:
        print(json.dumps(to_jsonable(payload), indent=2, sort_keys=True))
    else:
        print(f"decision:            {decision.decision.value}")
        print(f"actor:               {decision.actor}")
        print(f"authority_source:    {decision.authority_source}")
        print(f"action:              {decision.action.value}")
        print(f"risk:                {decision.risk.value}")
        if decision.budget is not None:
            print(f"budget:              {decision.budget.reason}")
        print(f"escalation_required: {str(decision.escalation_required).lower()}")
        print(f"ceo_required:        {str(decision.ceo_required).lower()}")
        print(f"reason:              {decision.reason}")
        if decision.chain:
            print("chain:")
            for step in decision.chain:
                print(f"  {step.seat}: {step.insufficiency.value} — {step.detail}")
        if report.exceptions:
            print("exceptions:")
            for item in report.exceptions:
                print(f"  [{item.exception_class.value}] {item.detail}")
    return _ANSWERED if decision.decision is Decision.APPROVED else _ESCALATED


def _cmd_replay(args: argparse.Namespace) -> int:
    policy = _load_policy(args)
    results = replay(policy)
    summary = summarise(results)
    if args.json:
        print(json.dumps(to_jsonable(summary), indent=2, sort_keys=True))
    else:
        print(
            f"{summary['matching_expectation']}/{summary['scenarios']} scenarios match "
            "the expected direction"
        )
        print("")
        for item in results:
            flag = "ok " if item.matches_expectation else "DIFF"
            print(f"[{flag}] {item.scenario.scenario_id}: {item.scenario.label}")
            print(f"        owner={item.owning_seat} "
                  f"decision={item.decision.decision.value} "
                  f"ceo_required={str(item.decision.ceo_required).lower()} "
                  f"(history: {str(item.scenario.actual_ceo_involved).lower()})")
            print(f"        {item.decision.reason}")
    return _ANSWERED if not summary["disagreements"] else _ESCALATED


def _cmd_shadow(args: argparse.Namespace) -> int:
    report = verify_shadow_mode()
    if args.json:
        print(json.dumps(to_jsonable(report.to_dict()), indent=2, sort_keys=True))
    else:
        print(report.render())
    return _ANSWERED if report.enforced else _ESCALATED


def _cmd_deployment(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(to_jsonable(DEPLOYMENT_POLICY.to_dict()), indent=2, sort_keys=True))
    else:
        print(policy_table())
        print("")
        print("Granted to no seat in this version. Classifying what authority a")
        print("deployment would need and granting it are two CEO decisions, and")
        print("only the first has been taken.")
    return _ANSWERED


def _cmd_report(args: argparse.Namespace) -> int:
    policy = _load_policy(args)
    historical = [
        DecisionOutcome(decision=item.decision, exceptions=item.exceptions)
        for item in replay(policy, scenarios=SCENARIOS)
    ]
    controls = [
        DecisionOutcome(decision=item.decision, exceptions=item.exceptions)
        for item in replay(policy, scenarios=CONTROL_SCENARIOS)
    ]
    metrics = measure(
        historical,
        spend=spend_of(historical, policy.ladder.currency),
        budget=policy.ladder.scope("engineering-operations").ceiling
        if policy.ladder.scope("engineering-operations")
        else None,
    )
    report = ManagementReport(
        programme="Engineering reliability validation (five real jobs, replayed)",
        metrics=metrics,
        outcomes=(
            "Three clean engineering jobs shipped to ready_for_approval",
            "One reviewer-found defect corrected through a second bounded work order",
            "One job stopped at pre-flight on a premise that turned out to be false",
        ),
        next_action=(
            "Run the model in shadow beside live work before any authority is granted"
        ),
        control_metrics=measure(controls),
    )
    if args.json:
        print(json.dumps(to_jsonable(report.to_dict()), indent=2, sort_keys=True))
    else:
        print(report.render())
    return _ANSWERED if metrics.ceo_decisions_required == 0 else _ESCALATED


def _register_for(args: argparse.Namespace):
    return load_seed_register(args.seed_file or None)


def _cmd_candidates(args: argparse.Namespace) -> int:
    """The backlog view a manager asks for: what open work does this capsule own?"""
    register = _register_for(args)
    rows = (
        register.for_capsule(args.capsule) if args.capsule else register.candidates
    )
    if args.status:
        wanted = CandidateStatus(args.status)
        rows = tuple(item for item in rows if item.status is wanted)
    lines = [f"WORK CANDIDATE REGISTER ({len(rows)} of {len(register)})"]
    if args.capsule:
        lines.append(f"  capsule {args.capsule}")
    lines.append("")
    for item in rows:
        lines.append(f"{item.candidate_id}")
        lines.append(
            f"  {item.status.value:10} {item.risk.value:7} {item.department:12} "
            f"{item.capsule_id}"
        )
        lines.append(f"  {item.title}")
        lines.append(f"  source    {item.source_type.value} <- {item.source_ref}")
        for blocker in item.blocked_by:
            lines.append(f"  BLOCKED   {blocker}")
        lines.append("")
    problems = register.violations()
    if problems:
        lines.append("REGISTER VIOLATIONS")
        lines.extend(f"  {item}" for item in problems)
    print("\n".join(lines).rstrip())
    return _ANSWERED


def _objective_and_envelope(
    data: Mapping[str, Any]
) -> tuple[Objective, PlanningEnvelope, dict[str, Any]]:
    """Read one CEO objective file into the two records planning needs."""
    envelope_raw = data.get("envelope")
    if not isinstance(envelope_raw, Mapping):
        raise DelegationError("the objective file needs an envelope")
    envelope = PlanningEnvelope(
        objective_id=str(data.get("objective_id", "")),
        budget=Money.from_dict(dict(envelope_raw.get("budget", {})), "budget"),
        budget_scope=str(envelope_raw.get("budget_scope", "")),
        risk_ceiling=parse_risk(envelope_raw.get("risk_ceiling")),
        allowed_departments=tuple(envelope_raw.get("allowed_departments", ())),
        forbidden_actions=tuple(
            parse_action(name) for name in envelope_raw.get("forbidden_actions", ())
        ),
        success_metrics=tuple(envelope_raw.get("success_metrics", ())),
    )
    objective = Objective(
        objective_id=str(data.get("objective_id", "")),
        level=ObjectiveLevel.CEO_OBJECTIVE,
        title=str(data.get("title", "")),
        owner_seat=str(data.get("owner_seat", "ceo")),
        set_by=str(data.get("set_by", "")),
        set_on=dt.date.fromisoformat(str(data.get("set_on"))),
        department=(envelope.allowed_departments or ("engineering",))[0],
        success_metrics=envelope.success_metrics,
        evidence_refs=tuple(data.get("evidence_refs", ())),
        envelope=envelope,
    )
    return objective, envelope, dict(data.get("planners", {}))


def _cmd_plan(args: argparse.Namespace) -> int:
    """CEO objective -> eligible candidates -> one selection, recorded.

    Planning only. Nothing here runs a work order, spends anything, or writes
    to a branch; the strongest thing it produces is a proposal a deterministic
    intake may still refuse.
    """
    policy = _load_policy(args)
    with open(args.objective_file, encoding="utf-8") as handle:
        data = json.load(handle)
    objective, envelope, planners = _objective_and_envelope(data)
    register = _register_for(args)
    day = dt.date.fromisoformat(args.as_of) if args.as_of else objective.set_on
    # Ownership is read from the capsule index, never from the register: a
    # candidate naming a capsule that does not exist is exactly the case the
    # capsule_owned check has to catch, and letting the register vouch for its
    # own capsule ids would make the check vacuous.
    owned = CapsuleIndex.load().ids()
    reserved = tuple(action for action in ActionType if policy.is_reserved(action))

    result = select_work(
        register,
        objective,
        envelope,
        planning_decision_id=str(data.get("planning_decision_id", "plan-" + objective.objective_id)),
        executive_seat=str(planners.get("executive_seat", "cto")),
        executive_employee=str(planners.get("executive_employee", "chief_architect")),
        manager_seat=str(planners.get("manager_seat", "engineering_manager")),
        manager_employee=str(planners.get("manager_employee", "engineering_delivery_manager")),
        policy_version=policy.version,
        policy_fingerprint=policy.fingerprint(),
        recorded_on=day,
        capsule_ids=owned,
        reserved_actions=reserved,
        objective_goal_tags=tuple(data.get("goal_tags", ())),
        prefer_candidate_id=args.prefer,
    )

    payload: dict[str, Any] = result.to_dict()
    if result.outcome is PlanningOutcome.SELECTED:
        candidate = register.candidate(result.record.selected_candidate_id)
        proposal = propose_work_order(
            candidate,
            envelope,
            proposal_id=f"wo-{candidate.candidate_id}"[:64],
            proposed_by_seat=result.record.manager_seat,
            proposed_on=day,
            planning_decision_id=result.record.planning_decision_id,
        )
        payload["proposal"] = proposal.to_dict()
        payload["work_order_request"] = proposal.to_request_dict(
            requested_by=result.record.manager_employee
        )
    if args.state_dir:
        store = DelegationStore(args.state_dir)
        for item in register.candidates:
            store.append_candidate(item)
        pointer = store.append_planning_decision(result.record)
        payload["persisted"] = pointer.to_dict()
    print(json.dumps(to_jsonable(payload), indent=2, sort_keys=True))
    if result.outcome is PlanningOutcome.SELECTED:
        return _ANSWERED
    if result.outcome is PlanningOutcome.ESCALATED:
        return _ESCALATED
    return _ESCALATED


_COMMANDS = {
    "policy": _cmd_policy,
    "deployment": _cmd_deployment,
    "report": _cmd_report,
    "chart": _cmd_chart,
    "evaluate": _cmd_evaluate,
    "replay": _cmd_replay,
    "shadow": _cmd_shadow,
    "candidates": _cmd_candidates,
    "plan": _cmd_plan,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except (CompanyOSError, DelegationError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return _REFUSED


if __name__ == "__main__":  # pragma: no cover - module entry point
    raise SystemExit(main())
