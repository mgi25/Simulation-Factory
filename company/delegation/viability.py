"""Execution viability: can this eligible candidate actually be worked on?

Eligibility answers "may the company choose this?". It does not answer "would
anything come of choosing it?", and those turned out to be different questions.

The final end-to-end pilot found the gap the expensive way. Deterministic
eligibility left exactly one candidate, planning selected it correctly, and
then normal intake refused the work order derived from it - the candidate is
`reserved-screening-negation-blindness`, its title names credential screening,
and `screen_credentials()` fires on the bare word. The defect blocked the
authorization of its own fix. Planning had already committed to the one rung
that does not look for anything else, so the run ended with a candidate the
company believed was workable and could not work on.

Bounded discovery existed for exactly this situation and was unreachable,
because the condition guarding it was `eligible == 0` rather than
`executable == 0`.

## What this module does, and what it refuses to do

For each eligible candidate it derives the bounded work order that candidate
would produce and runs **normal intake** over it, unchanged. A candidate is
EXECUTABLE when intake authorizes that proposal and NOT_EXECUTABLE otherwise,
with intake's own reason carried through.

Three things it deliberately does not do:

- **It does not weaken intake.** The dry run calls `assess_request` exactly as
  the real path does, with the same permissions and the same repository root. A
  candidate that intake refuses is refused here.
- **It does not rewrite candidates.** No retry with different wording, no
  scope trimming, no risk downgrade. If the objective text trips a screen, that
  is the answer, and the remedy is different work or a CEO decision - not a
  synonym.
- **It does not decide anything.** It produces verdicts. Planning reads them.

## Why the dry run is safe to do this early

`assess_request` is pure with respect to the store: it reads permissions and
the repository layout and returns an assessment. Nothing is written, no job is
opened, and no attempt is consumed. The cost is a few milliseconds per
candidate, paid once per planning run, against a developer session that costs
real money and was, in the pilot that motivated this, about to be spent on a
work order that could never have been authorized.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from .candidates import WorkCandidate
from .errors import DelegationError
from .objectives import PlanningEnvelope
from .planning import propose_work_order


BlockedAt = str
"""Where a candidate stopped: "proposal", "intake", or "" when it did not."""

PROPOSAL = "proposal"
INTAKE = "intake"


@dataclass(frozen=True)
class ViabilityVerdict:
    """One candidate, and whether work could actually start on it."""

    candidate_id: str
    executable: bool
    blocked_at: BlockedAt = ""
    intake_outcome: str = ""
    reason: str = ""
    proposal_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.executable, bool):
            raise DelegationError("viability.executable must be a bool")
        if self.executable and self.blocked_at:
            raise DelegationError(
                f"{self.candidate_id}: an executable candidate is not blocked at "
                f"{self.blocked_at}"
            )
        if not self.executable and not self.reason:
            raise DelegationError(
                f"{self.candidate_id}: a candidate refused for execution must say "
                "why. A refusal with no reason is not reviewable."
            )

    def line(self) -> str:
        """One line for the planning record, and for a human reading it."""
        if self.executable:
            return f"{self.candidate_id}: executable"
        where = f" at {self.blocked_at}" if self.blocked_at else ""
        return f"{self.candidate_id}: not executable{where} - {self.reason}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "executable": self.executable,
            "blocked_at": self.blocked_at,
            "intake_outcome": self.intake_outcome,
            "reason": self.reason,
            "proposal_id": self.proposal_id,
        }


def _reason_from(assessment: Any) -> str:
    """Intake's own words, not a paraphrase."""
    parts = [
        item.reason.strip()
        for item in getattr(assessment, "decisions", ())
        if getattr(item, "reason", "").strip()
    ]
    if parts:
        return "; ".join(parts)
    return f"intake returned {assessment.outcome.value} with no stated reason"


def assess_viability(
    candidate: WorkCandidate,
    envelope: PlanningEnvelope,
    *,
    permissions: Mapping[str, Any],
    repo_root: Any,
    proposed_by_seat: str,
    proposed_on: dt.date,
    planning_decision_id: str,
    requested_by: str,
    authorized_branch: str = "",
    base_commit: str = "",
) -> ViabilityVerdict:
    """Derive this candidate's work order and dry-run normal intake over it."""
    # Imported here rather than at module scope: `company.engineering.intake`
    # imports a good deal of the engineering package, and planning should not
    # pay that cost on every import of the delegation package. The dependency
    # itself is declared - `company-executive-delegation` lists
    # `company-engineering-execution` - and runs in that direction only.
    from company.engineering.intake import CEORequest, IntakeOutcome, assess_request

    if not isinstance(candidate, WorkCandidate):
        raise DelegationError("assess_viability takes a WorkCandidate")

    proposal_id = f"wo-{candidate.candidate_id}"[:64]
    try:
        proposal = propose_work_order(
            candidate,
            envelope,
            proposal_id=proposal_id,
            proposed_by_seat=proposed_by_seat,
            proposed_on=proposed_on,
            planning_decision_id=planning_decision_id,
            authorized_branch=authorized_branch,
            base_commit=base_commit,
        )
    except DelegationError as exc:
        return ViabilityVerdict(
            candidate_id=candidate.candidate_id,
            executable=False,
            blocked_at=PROPOSAL,
            reason=f"no bounded work order can be derived: {exc}",
            proposal_id=proposal_id,
        )

    payload = proposal.to_request_dict(requested_by=requested_by)
    try:
        assessment = assess_request(
            CEORequest.from_mapping(payload),
            permissions,
            repo_root=repo_root,
            authorized_on=proposed_on,
        )
    except Exception as exc:  # noqa: BLE001 - intake refuses in several ways
        return ViabilityVerdict(
            candidate_id=candidate.candidate_id,
            executable=False,
            blocked_at=INTAKE,
            reason=f"intake refused the derived request: {exc}",
            proposal_id=proposal_id,
        )

    if assessment.outcome is IntakeOutcome.AUTHORIZED:
        return ViabilityVerdict(
            candidate_id=candidate.candidate_id,
            executable=True,
            intake_outcome=assessment.outcome.value,
            proposal_id=proposal_id,
        )
    return ViabilityVerdict(
        candidate_id=candidate.candidate_id,
        executable=False,
        blocked_at=INTAKE,
        intake_outcome=assessment.outcome.value,
        reason=_reason_from(assessment),
        proposal_id=proposal_id,
    )


def assess_all(
    candidates: Sequence[WorkCandidate],
    envelope: PlanningEnvelope,
    **kwargs: Any,
) -> tuple[ViabilityVerdict, ...]:
    """`assess_viability` over a sequence, in order, sharing no state."""
    return tuple(assess_viability(item, envelope, **kwargs) for item in candidates)


def executable_ids(verdicts: Sequence[ViabilityVerdict]) -> tuple[str, ...]:
    return tuple(item.candidate_id for item in verdicts if item.executable)


def refusal_lines(verdicts: Sequence[ViabilityVerdict]) -> tuple[str, ...]:
    return tuple(item.line() for item in verdicts if not item.executable)


__all__ = [
    "INTAKE",
    "PROPOSAL",
    "ViabilityVerdict",
    "assess_all",
    "assess_viability",
    "executable_ids",
    "refusal_lines",
]
