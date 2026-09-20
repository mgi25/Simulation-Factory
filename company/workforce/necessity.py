"""Is this role still worth having? - answered with evidence, decided by a human.

## Nothing here archives anyone

`RoleNecessityReview` has no apply, no side effect, and a `requires_human_decision`
field that is `True` and cannot be set otherwise. The strongest thing this module
produces is a `WorkforceProposal` in the `PROPOSED` state, which is a record
someone reads.

That is not timidity, it is the rollback rule (constitution rule 10) meeting the
fact that the evidence here is thin by construction: an employee with zero tasks
in a review window might be redundant, or might be dormant on purpose, or might
own the one capability nobody has needed *yet*.

## The inversion that had to be built in

The signals below include both `DUPLICATE_CAPABILITY_COVERAGE` (an argument for
merging) and `UNIQUE_CAPABILITY_COVERAGE` / `CRITICAL_SINGLE_POINT_OF_FAILURE`
(an argument that archiving would remove a capability from the company
entirely). Those can fire on the same employee: someone whose three capabilities
are all duplicated except the one they are the sole provider of.

So `recommend()` refuses to return `ARCHIVE_ROLE` whenever a uniqueness signal is
present, no matter how many redundancy signals fired. An organizational analysis
that can recommend deleting the last provider of a core capability is worse than
no analysis, because it is confidently wrong in the direction that does damage.

## Thresholds are data

`NecessityPolicy` holds every number. None of them is a fact about the world;
they are the company's current opinion, in one place, so changing one is a
one-line diff rather than an argument with the code.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .capabilities import CapabilityRegistry, Criticality
from .common import (
    assert_day,
    assert_identifier,
    assert_prose,
    assert_record_id,
    evidence_tuple,
)
from .errors import WorkforceError
from .performance import CapabilityPerformance
from .proposals import Recommendation, WorkforceProposal


class NecessitySignal(Enum):
    NO_TASKS_IN_WINDOW = "no_tasks_in_window"
    DUPLICATE_CAPABILITY_COVERAGE = "duplicate_capability_coverage"
    UNIQUE_CAPABILITY_COVERAGE = "unique_capability_coverage"
    HIGH_REJECTION_RATE = "high_rejection_rate"
    HIGH_RESOURCE_COST = "high_resource_cost"
    REPEATED_ESCALATION = "repeated_escalation"
    CRITICAL_SINGLE_POINT_OF_FAILURE = "critical_single_point_of_failure"


# Signals that make archiving the role unsafe regardless of everything else.
PROTECTIVE_SIGNALS = frozenset(
    {
        NecessitySignal.UNIQUE_CAPABILITY_COVERAGE,
        NecessitySignal.CRITICAL_SINGLE_POINT_OF_FAILURE,
    }
)


class Direction(Enum):
    RETAIN = "retain"
    REVIEW = "review"
    CONSIDER_MERGE = "consider_merge"
    CONSIDER_ARCHIVE = "consider_archive"
    PROTECT = "protect"


@dataclass(frozen=True)
class NecessityPolicy:
    """Every threshold, in one place, because none of them is a law of nature."""

    rejection_rate_threshold: float = 0.5
    escalation_rate_threshold: float = 0.5
    minimum_observations: int = 3
    passes_per_accepted_threshold: float = 3.0

    def __post_init__(self) -> None:
        for name in (
            "rejection_rate_threshold",
            "escalation_rate_threshold",
            "passes_per_accepted_threshold",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
                raise WorkforceError(f"{name} must be a positive number")
        if isinstance(self.minimum_observations, bool) or self.minimum_observations < 1:
            raise WorkforceError("minimum_observations must be at least 1")


DEFAULT_POLICY = NecessityPolicy()


@dataclass(frozen=True)
class NecessityFinding:
    """One signal, what it was computed from, and which way it points."""

    signal: NecessitySignal
    direction: Direction
    detail: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.signal, NecessitySignal):
            raise WorkforceError("finding signal must be a NecessitySignal")
        if not isinstance(self.direction, Direction):
            raise WorkforceError("finding direction must be a Direction")
        assert_prose(self.detail, f"finding {self.signal.value} detail")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RoleNecessityReview:
    """What the evidence says about one role. A human decides what to do."""

    employee_id: str
    window_start: dt.date
    window_end: dt.date
    findings: tuple[NecessityFinding, ...] = ()
    recommendation: Recommendation = Recommendation.NO_ACTION
    summary: str = ""
    requires_human_decision: bool = True

    def __post_init__(self) -> None:
        assert_identifier(self.employee_id, "employee_id")
        object.__setattr__(self, "window_start", assert_day(self.window_start, "window_start"))
        object.__setattr__(self, "window_end", assert_day(self.window_end, "window_end"))
        if self.window_end < self.window_start:
            raise WorkforceError("review window ends before it starts")
        if not isinstance(self.findings, tuple) or any(
            not isinstance(item, NecessityFinding) for item in self.findings
        ):
            raise WorkforceError("findings must be a tuple of NecessityFinding")
        if not isinstance(self.recommendation, Recommendation):
            raise WorkforceError("recommendation must be a Recommendation")
        if self.requires_human_decision is not True:
            raise WorkforceError(
                "requires_human_decision is True for every necessity review. Removing a "
                "role is not a computation this package is allowed to conclude on its own"
            )
        if not isinstance(self.summary, str):
            raise WorkforceError("summary must be a string")
        if (
            self.recommendation is Recommendation.ARCHIVE_ROLE
            and self.protective_signals
        ):
            raise WorkforceError(
                f"{self.employee_id}: archive was recommended while {', '.join(self.protective_signals)} "
                "is present. Archiving the sole provider of a capability removes it from the "
                "company; that is not a redundancy finding"
            )

    @property
    def signals(self) -> tuple[str, ...]:
        return tuple(finding.signal.value for finding in self.findings)

    @property
    def protective_signals(self) -> tuple[str, ...]:
        return tuple(
            finding.signal.value
            for finding in self.findings
            if finding.signal in PROTECTIVE_SIGNALS
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def review_role(
    employee_id: str,
    registry: CapabilityRegistry,
    performances: Iterable[CapabilityPerformance],
    *,
    window_start: dt.date,
    window_end: dt.date,
    policy: NecessityPolicy = DEFAULT_POLICY,
    resource_cost_per_accepted: float | None = None,
    evidence: tuple[Evidence, ...] = (),
) -> RoleNecessityReview:
    """Compute the findings for one role over one window.

    `resource_cost_per_accepted` is passed in rather than computed, because the
    only honest source for it is the usage store and this module does not read
    the filesystem. `None` means nobody measured, and no finding is produced -
    an unmeasured cost is not a cheap one.
    """
    assert_identifier(employee_id, "employee_id")
    mine = [item for item in performances if item.employee_id == employee_id]
    capabilities = registry.employee_capabilities(employee_id)
    findings: list[NecessityFinding] = []

    attempted = sum(item.attempted for item in mine)
    if attempted == 0:
        findings.append(
            NecessityFinding(
                signal=NecessitySignal.NO_TASKS_IN_WINDOW,
                direction=Direction.REVIEW,
                detail=(
                    f"no task was recorded against {employee_id} between "
                    f"{window_start.isoformat()} and {window_end.isoformat()}. A dormant "
                    "employee costs nothing to keep, so this is a question, not a verdict"
                ),
                evidence=evidence,
            )
        )

    duplicated: list[str] = []
    unique: list[str] = []
    critical_sole: list[str] = []
    for capability_id in capabilities:
        if capability_id not in registry.graph:
            continue
        resolved = registry.providers(capability_id)
        others = tuple(item for item in resolved.provided_by if item != employee_id)
        if others:
            duplicated.append(capability_id)
        elif employee_id in resolved.provided_by:
            unique.append(capability_id)
            if resolved.capability.criticality in (Criticality.CORE, Criticality.IMPORTANT):
                critical_sole.append(capability_id)

    if duplicated:
        findings.append(
            NecessityFinding(
                signal=NecessitySignal.DUPLICATE_CAPABILITY_COVERAGE,
                direction=Direction.CONSIDER_MERGE,
                detail=(
                    "another employee already provides: " + ", ".join(sorted(duplicated))
                ),
            )
        )
    if unique:
        findings.append(
            NecessityFinding(
                signal=NecessitySignal.UNIQUE_CAPABILITY_COVERAGE,
                direction=Direction.PROTECT,
                detail=(
                    f"{employee_id} is the only provider of: " + ", ".join(sorted(unique))
                ),
            )
        )
    if critical_sole:
        findings.append(
            NecessityFinding(
                signal=NecessitySignal.CRITICAL_SINGLE_POINT_OF_FAILURE,
                direction=Direction.PROTECT,
                detail=(
                    "sole provider of core or important capability: "
                    + ", ".join(sorted(critical_sole))
                ),
            )
        )

    for item in mine:
        if item.attempted < policy.minimum_observations:
            continue
        rejection = item.rejection_rate
        if rejection is not None and rejection > policy.rejection_rate_threshold:
            findings.append(
                NecessityFinding(
                    signal=NecessitySignal.HIGH_REJECTION_RATE,
                    direction=Direction.REVIEW,
                    detail=(
                        f"{item.rejected} of {item.attempted} {item.capability_id} tasks were "
                        f"rejected ({rejection:.0%}, threshold {policy.rejection_rate_threshold:.0%})"
                    ),
                )
            )
        escalation = item.escalation_rate
        if escalation is not None and escalation > policy.escalation_rate_threshold:
            findings.append(
                NecessityFinding(
                    signal=NecessitySignal.REPEATED_ESCALATION,
                    direction=Direction.REVIEW,
                    detail=(
                        f"{item.escalations} of {item.attempted} {item.capability_id} tasks "
                        f"escalated ({escalation:.0%}). A role that escalates most of its work "
                        "may be scoped wrong rather than staffed wrong"
                    ),
                )
            )

    if (
        resource_cost_per_accepted is not None
        and resource_cost_per_accepted > policy.passes_per_accepted_threshold
    ):
        findings.append(
            NecessityFinding(
                signal=NecessitySignal.HIGH_RESOURCE_COST,
                direction=Direction.REVIEW,
                detail=(
                    f"{resource_cost_per_accepted:.2f} passes per accepted deliverable, over "
                    f"the {policy.passes_per_accepted_threshold:.2f} threshold"
                ),
            )
        )

    recommendation, summary = _conclude(employee_id, tuple(findings))
    return RoleNecessityReview(
        employee_id=employee_id,
        window_start=window_start,
        window_end=window_end,
        findings=tuple(findings),
        recommendation=recommendation,
        summary=summary,
    )


def _conclude(
    employee_id: str, findings: tuple[NecessityFinding, ...]
) -> tuple[Recommendation, str]:
    signals = {finding.signal for finding in findings}
    protective = signals & PROTECTIVE_SIGNALS
    if protective:
        return (
            Recommendation.NO_ACTION,
            f"{employee_id} is the sole provider of at least one capability; keep the role "
            "and consider a second provider instead",
        )
    if NecessitySignal.DUPLICATE_CAPABILITY_COVERAGE in signals and (
        NecessitySignal.NO_TASKS_IN_WINDOW in signals
    ):
        return (
            Recommendation.MERGE_ROLES,
            f"every capability {employee_id} holds is held elsewhere and no task was routed "
            "to it in the window; merging is worth considering",
        )
    if NecessitySignal.DUPLICATE_CAPABILITY_COVERAGE in signals:
        return (
            Recommendation.MERGE_ROLES,
            f"every capability {employee_id} holds is also held elsewhere",
        )
    if signals:
        return (
            Recommendation.NO_ACTION,
            f"{employee_id} raised {len(signals)} signal(s); none of them justifies a "
            "workforce change on its own",
        )
    return (Recommendation.NO_ACTION, f"nothing notable about {employee_id} in this window")


def review_to_proposal(
    review: RoleNecessityReview,
    *,
    proposal_id: str,
    proposed_on: dt.date,
    merge_with: tuple[str, ...] = (),
    evidence: tuple[Evidence, ...] = (),
) -> WorkforceProposal:
    """Turn a review into a proposal record. Still nobody is archived.

    `MERGE_ROLES` needs the roles it would merge with, which the review does not
    know: merging is a decision about a pair, and the review looked at one role.
    """
    assert_record_id(proposal_id, "proposal_id")
    subjects: tuple[str, ...] = ()
    if review.recommendation is Recommendation.MERGE_ROLES:
        if not merge_with:
            raise WorkforceError(
                f"{review.employee_id}: a merge proposal must name the role(s) to merge with"
            )
        subjects = (review.employee_id,) + tuple(merge_with)
    elif review.recommendation is Recommendation.ARCHIVE_ROLE:
        subjects = (review.employee_id,)
    return WorkforceProposal(
        proposal_id=proposal_id,
        recommendation=review.recommendation,
        rationale=review.summary or f"necessity review of {review.employee_id}",
        proposed_on=proposed_on,
        subject_employee_ids=subjects,
        evidence=tuple(evidence) + tuple(e for f in review.findings for e in f.evidence),
        notes="; ".join(review.signals),
    )
