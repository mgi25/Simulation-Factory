"""Proof, on every run, that this phase changed nothing about who may approve.

The risk of building a delegation model is not that it decides wrongly. It is
that it decides *at all* before anybody authorized it to. So this module does
not describe shadow mode — it probes for it, the way
`company/integration/probes.py` probes the boundary conditions it is asked to
guarantee, by calling the canonical code and checking that it still refuses.

Five conditions, and what each one would look like if it broke:

1. **The CEO decision still names a human.** `CEODecision` would accept
   `decided_by="company_os"` and this subsystem could write its own approval.
2. **An approval still carries no merge authority.** `authorizes_merge=True`
   would construct, and an approved job would look like permission to integrate.
3. **Only `ready_for_approval` can be approved.** A job could be approved out
   of `blocked` or `failed`.
4. **No delegation record can claim to have acted.** `authorizes_action=True`
   or `shadow=False` would construct.
5. **The policy cannot leave shadow mode.** A policy with
   `mode=ENFORCING` would construct.

`verify_shadow_mode` returns a report rather than raising, so a caller can print
it; `assert_shadow_mode` raises. Both run the same five probes, and the tests
run them against the canonical modules rather than against a fixture, because a
fixture would prove only that the fixture is safe.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import datetime as dt
from typing import Any

from .errors import ShadowModeViolation


@dataclass(frozen=True)
class ShadowCheck:
    """One condition, whether it holds, and the evidence for the answer."""

    check_id: str
    holds: bool
    detail: str
    evidence: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "holds": self.holds,
            "detail": self.detail,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class ShadowReport:
    """Every condition, and the single answer a stop condition quotes."""

    checks: tuple[ShadowCheck, ...]

    @property
    def enforced(self) -> bool:
        return all(item.holds for item in self.checks)

    @property
    def failures(self) -> tuple[ShadowCheck, ...]:
        return tuple(item for item in self.checks if not item.holds)

    def to_dict(self) -> dict[str, Any]:
        return {
            "shadow_mode_enforced": self.enforced,
            "checks": [item.to_dict() for item in self.checks],
        }

    def render(self) -> str:
        lines = [
            "SHADOW MODE: " + ("ENFORCED" if self.enforced else "NOT ENFORCED"),
            "",
        ]
        for item in self.checks:
            lines.append(f"  [{'ok' if item.holds else 'FAIL'}] {item.check_id}")
            lines.append(f"        {item.detail}")
        return "\n".join(lines)


def _refuses(call: Callable[[], object], expected: type[BaseException]) -> str:
    """Empty if the call raised `expected`; otherwise what went wrong instead."""
    try:
        call()
    except expected:
        return ""
    except BaseException as exc:  # noqa: BLE001 - any other error is also a finding
        return f"raised {type(exc).__name__} instead of {expected.__name__}: {exc}"
    return f"was accepted, and should have raised {expected.__name__}"


def _ceo_decision_names_a_human() -> ShadowCheck:
    from company.engineering.common import AUTOMATIC_MARKERS, assert_named_person
    from company.engineering.errors import EngineeringError

    problems = []
    for marker in sorted(AUTOMATIC_MARKERS)[:5]:
        outcome = _refuses(
            lambda marker=marker: assert_named_person(marker, "decided_by"),
            EngineeringError,
        )
        if outcome:
            problems.append(f"a decision decided_by {marker!r} {outcome}")
    try:
        assert_named_person("the CEO", "decided_by")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a named human decider was refused: {exc}")
    return ShadowCheck(
        check_id="ceo_decision_names_a_human",
        holds=not problems,
        detail=(
            "; ".join(problems[:2])
            if problems
            else "a CEO decision signed by an automatic marker is still refused, and a "
            "named human is still accepted"
        ),
        evidence="company/engineering/common.py assert_named_person",
    )


def _approval_carries_no_merge_authority() -> ShadowCheck:
    from company.engineering.decision import CEODecision, CEOVerdict
    from company.engineering.errors import EngineeringError
    from company.engineering.lifecycle import JobState

    def build(**overrides: Any) -> CEODecision:
        fields: dict[str, Any] = {
            "decision_id": "shadow-probe-decision",
            "work_order_id": "shadow-probe-work-order",
            "work_order_fingerprint": "0" * 16,
            "verdict": CEOVerdict.APPROVE,
            "decided_by": "the CEO",
            "decided_on": dt.date(2026, 9, 20),
            "rationale": "a probe that constructs a decision and never stores one",
            "reviewed_state": JobState.READY_FOR_APPROVAL,
        }
        fields.update(overrides)
        return CEODecision(**fields)

    problems = []
    outcome = _refuses(lambda: build(authorizes_merge=True), EngineeringError)
    if outcome:
        problems.append(f"a decision claiming merge authority {outcome}")
    try:
        approved = build()
        if approved.authorizes_merge is not False:
            problems.append("a default approval reported merge authority")
    except BaseException as exc:  # noqa: BLE001
        problems.append(f"a well-formed approval was refused: {exc}")
    return ShadowCheck(
        check_id="approval_carries_no_merge_authority",
        holds=not problems,
        detail=(
            "; ".join(problems[:2])
            if problems
            else "a recorded CEO approval still carries no merge authority, and one "
            "claiming it is still refused"
        ),
        evidence="company/engineering/decision.py CEODecision.authorizes_merge",
    )


def _only_ready_for_approval_can_be_approved() -> ShadowCheck:
    from company.engineering.decision import CEODecision, CEOVerdict
    from company.engineering.errors import EngineeringError
    from company.engineering.lifecycle import JobState

    blocked_states = (JobState.BLOCKED, JobState.FAILED, JobState.REVIEWING)
    problems = []
    for state in blocked_states:
        outcome = _refuses(
            lambda state=state: CEODecision(
                decision_id="shadow-probe-decision",
                work_order_id="shadow-probe-work-order",
                work_order_fingerprint="0" * 16,
                verdict=CEOVerdict.APPROVE,
                decided_by="the CEO",
                decided_on=dt.date(2026, 9, 20),
                rationale="a probe that never stores anything",
                reviewed_state=state,
            ),
            EngineeringError,
        )
        if outcome:
            problems.append(f"approving a job in {state.value} {outcome}")
    return ShadowCheck(
        check_id="only_ready_for_approval_can_be_approved",
        holds=not problems,
        detail=(
            "; ".join(problems[:2])
            if problems
            else "approving a job that is not ready_for_approval is still refused in "
            f"{len(blocked_states)} probed states"
        ),
        evidence="company/engineering/decision.py CEODecision.__post_init__",
    )


def _delegation_record_cannot_act() -> ShadowCheck:
    from ai_platform.resource_classes import Risk

    from .authority import AuthorityDecision, Decision
    from .errors import AuthorityViolation
    from .record import ExecutiveDecisionRecord

    def record(**overrides: Any) -> ExecutiveDecisionRecord:
        fields: dict[str, Any] = {
            "decision_id": "shadow-probe-record",
            "recorded_on": dt.date(2026, 9, 20),
            "objective_id": "",
            "work_order_id": "",
            "department": "engineering",
            "requesting_role": "software_implementation_engineer",
            "approving_role": "chief_architect",
            "authority_source": "delegation_policy_v1",
            "action": "approve_code_change",
            "risk": Risk.LOW,
            "decision": Decision.APPROVED,
            "reason": "a probe that constructs a record and never stores one",
            "escalation_target": "",
            "ceo_required": False,
            "policy_version": "delegation_policy_v1",
            "policy_fingerprint": "0" * 16,
            "request_fingerprint": "0" * 16,
        }
        fields.update(overrides)
        return ExecutiveDecisionRecord(**fields)

    problems = []
    outcome = _refuses(lambda: record(authorizes_action=True), AuthorityViolation)
    if outcome:
        problems.append(f"a record claiming it authorizes the action {outcome}")
    outcome = _refuses(lambda: record(shadow=False), ShadowModeViolation)
    if outcome:
        problems.append(f"a record claiming it left shadow mode {outcome}")
    outcome = _refuses(
        lambda: record(approving_role="ceo"), AuthorityViolation
    )
    if outcome:
        problems.append(f"a record writing a CEO approval {outcome}")
    outcome = _refuses(
        lambda: AuthorityDecision(
            request_id="shadow-probe",
            decision=Decision.APPROVED,
            actor="chief_architect",
            authority_source="delegation_policy_v1",
            action="approve_code_change",
            risk=Risk.LOW,
            escalation_required=False,
            ceo_required=False,
            reason="a probe",
            authorizes_action=True,
        ),
        AuthorityViolation,
    )
    if outcome:
        problems.append(f"a decision claiming authority to act {outcome}")
    return ShadowCheck(
        check_id="delegation_record_cannot_act",
        holds=not problems,
        detail=(
            "; ".join(problems[:2])
            if problems
            else "a delegation decision and a stored record both refuse to claim "
            "authority to act, and both refuse to leave shadow mode"
        ),
        evidence="company/delegation/record.py, company/delegation/authority.py",
    )


def _policy_cannot_leave_shadow() -> ShadowCheck:
    from .budget import BudgetLadder, BudgetLevel, BudgetScope
    from .org import Hierarchy, Seat, SeatKind
    from .policy import DelegationMode, DelegationPolicy

    def build() -> DelegationPolicy:
        hierarchy = Hierarchy(
            seats=(
                Seat(seat_id="ceo", kind=SeatKind.CEO, title="CEO", reports_to=""),
                Seat(
                    seat_id="probe_seat",
                    kind=SeatKind.EXECUTIVE,
                    title="Probe",
                    reports_to="ceo",
                ),
            ),
            org_registry={"employees": {}},
            permissions={"ceo_reserved": [], "autonomy_levels": {}},
        )
        ladder = BudgetLadder(
            (
                BudgetScope(
                    scope_id="probe-company",
                    level=BudgetLevel.COMPANY,
                    ceiling={"amount": "1.00", "currency": "USD"},
                ),
            )
        )
        return DelegationPolicy(
            hierarchy=hierarchy,
            grants=(),
            ladder=ladder,
            action_autonomy={"approve_code_change": 3},
            mode=DelegationMode.ENFORCING,
        )

    outcome = _refuses(build, ShadowModeViolation)
    return ShadowCheck(
        check_id="policy_cannot_leave_shadow",
        holds=not outcome,
        detail=(
            f"an enforcing policy {outcome}"
            if outcome
            else "a policy declaring mode=enforcing is still refused at construction"
        ),
        evidence="company/delegation/policy.py DelegationPolicy.__post_init__",
    )


CHECKS: tuple[Callable[[], ShadowCheck], ...] = (
    _ceo_decision_names_a_human,
    _approval_carries_no_merge_authority,
    _only_ready_for_approval_can_be_approved,
    _delegation_record_cannot_act,
    _policy_cannot_leave_shadow,
)


def verify_shadow_mode() -> ShadowReport:
    """Run every probe. Returns a report; never raises for a failing condition."""
    results: list[ShadowCheck] = []
    for check in CHECKS:
        try:
            results.append(check())
        except BaseException as exc:  # noqa: BLE001 - a probe that dies is a finding
            results.append(
                ShadowCheck(
                    check_id=getattr(check, "__name__", "unknown").lstrip("_"),
                    holds=False,
                    detail=f"the probe raised {type(exc).__name__}: {exc}",
                    evidence="company/delegation/shadow.py",
                )
            )
    return ShadowReport(tuple(results))


def assert_shadow_mode() -> ShadowReport:
    """The same probes, as an assertion. Raises on the first failing condition."""
    report = verify_shadow_mode()
    if not report.enforced:
        names = ", ".join(item.check_id for item in report.failures)
        raise ShadowModeViolation(
            "the canonical CEO stop semantics are no longer enforced: "
            + names
            + ". This phase is advisory, and an advisory subsystem running beside a "
            "weakened gate is the failure it exists to prevent."
        )
    return report


__all__ = [
    "CHECKS",
    "ShadowCheck",
    "ShadowReport",
    "assert_shadow_mode",
    "verify_shadow_mode",
]
