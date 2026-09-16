"""What to do about a gap, ranked - and never done automatically.

## The decision table

Section 5 of the workforce brief is four rules, and this module is those four
rules with the evidence attached:

| Situation | Recommendation |
|---|---|
| every required capability actively covered | `NO_ACTION` |
| nothing missing, dormant provider exists | `ACTIVATE_DORMANT_EMPLOYEE` |
| one-off or intermittent need | `TEMPORARY_SPECIALIST` |
| recurring need, adjacent employee exists | `RETRAIN_EMPLOYEE` |
| recurring need, nobody adjacent | `CREATE_CANDIDATE_ROLE` |

The expensive answer is last on purpose. A permanent role is the only option
that permanently increases the company's routine cost, so every cheaper answer
is checked first, and `rank_options` returns *all* of them with their scores so
a reviewer can see what was rejected rather than being handed a verdict.

## What "adjacent" means, and why it is not a judgement call

`CapabilityGraph.adjacent` returns capabilities one explicit relation hop from
the missing set. An employee who already provides one of those is a retraining
candidate. The relations are data in `capability_registry.json`, so adjacency is
reproducible and arguable - somebody can point at the edge they disagree with.
Nothing reads a description and decides two capabilities feel similar.

## This module recommends. It does not act.

Every `WorkforceProposal` is born `PROPOSED`, there is no `apply()`, and no
function here writes `org_registry.yaml`, changes an employment state, or
grants authority. `requires_ceo_approval` is computed from `permissions.yaml`
`ceo_reserved` - an executive hire is flagged, and the flag is advisory data on
a record a human reads.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .capabilities import CapabilityRegistry
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    evidence_tuple,
    id_tuple,
    optional_ref,
)
from .coverage import CoverageReport
from .errors import WorkforceError
from .gaps import CapabilityGap, NeedFrequency
from .roles import ApprovalState

EXECUTIVE_DEPARTMENT = "executive"


class Recommendation(Enum):
    USE_EXISTING_EMPLOYEE = "use_existing_employee"
    ACTIVATE_DORMANT_EMPLOYEE = "activate_dormant_employee"
    TEMPORARY_SPECIALIST = "temporary_specialist"
    CREATE_CANDIDATE_ROLE = "create_candidate_role"
    RETRAIN_EMPLOYEE = "retrain_employee"
    MERGE_ROLES = "merge_roles"
    ARCHIVE_ROLE = "archive_role"
    NO_ACTION = "no_action"


# What each recommendation needs before it can be written down at all.
_NEEDS_SUBJECTS = frozenset(
    {
        Recommendation.USE_EXISTING_EMPLOYEE,
        Recommendation.ACTIVATE_DORMANT_EMPLOYEE,
        Recommendation.RETRAIN_EMPLOYEE,
        Recommendation.MERGE_ROLES,
        Recommendation.ARCHIVE_ROLE,
    }
)

# Cost rank, cheapest first. Used to order equally-scored options so the
# ranking is total and the same inputs always produce the same first choice.
_COST_ORDER: dict[Recommendation, int] = {
    Recommendation.NO_ACTION: 0,
    Recommendation.USE_EXISTING_EMPLOYEE: 1,
    Recommendation.ACTIVATE_DORMANT_EMPLOYEE: 2,
    Recommendation.RETRAIN_EMPLOYEE: 3,
    Recommendation.TEMPORARY_SPECIALIST: 4,
    Recommendation.MERGE_ROLES: 5,
    Recommendation.ARCHIVE_ROLE: 6,
    Recommendation.CREATE_CANDIDATE_ROLE: 7,
}


@dataclass(frozen=True)
class ProposalOption:
    """One considered answer, whether or not it was chosen."""

    recommendation: Recommendation
    viable: bool
    reason: str
    subject_employee_ids: tuple[str, ...] = ()

    @property
    def sort_key(self) -> tuple[int, int, str]:
        return (
            0 if self.viable else 1,
            _COST_ORDER[self.recommendation],
            self.recommendation.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class WorkforceProposal:
    """A recommendation with its evidence. Reading it changes nothing."""

    proposal_id: str
    recommendation: Recommendation
    rationale: str
    proposed_on: dt.date
    gap_id: str = ""
    subject_employee_ids: tuple[str, ...] = ()
    role_specification_id: str = ""
    considered: tuple[ProposalOption, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    requires_ceo_approval: bool = False
    approval: ApprovalState = ApprovalState.PROPOSED
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.proposal_id, "proposal_id")
        if not isinstance(self.recommendation, Recommendation):
            raise WorkforceError("recommendation must be a Recommendation")
        assert_prose(self.rationale, f"proposal {self.proposal_id} rationale")
        object.__setattr__(
            self, "proposed_on", assert_day(self.proposed_on, "proposal proposed_on")
        )
        object.__setattr__(self, "gap_id", optional_ref(self.gap_id, "proposal gap_id"))
        object.__setattr__(
            self,
            "subject_employee_ids",
            id_tuple(self.subject_employee_ids, "proposal subject_employee_ids", sort=True),
        )
        object.__setattr__(
            self,
            "role_specification_id",
            optional_ref(self.role_specification_id, "proposal role_specification_id"),
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if not isinstance(self.approval, ApprovalState):
            raise WorkforceError("proposal approval must be an ApprovalState")
        if not isinstance(self.requires_ceo_approval, bool):
            raise WorkforceError("requires_ceo_approval must be a bool")
        if not isinstance(self.notes, str):
            raise WorkforceError("proposal notes must be a string")

        if self.recommendation in _NEEDS_SUBJECTS and not self.subject_employee_ids:
            raise WorkforceError(
                f"proposal {self.proposal_id}: {self.recommendation.value} must name the "
                "employee it is about"
            )
        if self.recommendation is Recommendation.MERGE_ROLES and len(self.subject_employee_ids) < 2:
            raise WorkforceError(
                f"proposal {self.proposal_id}: merging roles needs at least two of them"
            )
        if self.recommendation is Recommendation.ARCHIVE_ROLE and len(self.subject_employee_ids) != 1:
            raise WorkforceError(
                f"proposal {self.proposal_id}: archive exactly one role at a time"
            )
        if (
            self.recommendation is Recommendation.CREATE_CANDIDATE_ROLE
            and not self.role_specification_id
        ):
            raise WorkforceError(
                f"proposal {self.proposal_id}: proposing a permanent role means proposing a "
                "RoleSpecification. A department and a title are not a role"
            )
        if (
            self.recommendation
            in (Recommendation.CREATE_CANDIDATE_ROLE, Recommendation.TEMPORARY_SPECIALIST)
            and not self.gap_id
        ):
            raise WorkforceError(
                f"proposal {self.proposal_id}: bringing in new capacity requires the gap it "
                "answers. Constitution rule 17 - prove need before building"
            )

    @property
    def is_action(self) -> bool:
        return self.recommendation is not Recommendation.NO_ACTION

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkforceProposal:
        return cls(
            proposal_id=data["proposal_id"],
            recommendation=Recommendation(data["recommendation"]),
            rationale=data["rationale"],
            proposed_on=assert_day(data["proposed_on"], "proposed_on"),
            gap_id=data.get("gap_id", ""),
            subject_employee_ids=tuple(data.get("subject_employee_ids", ())),
            role_specification_id=data.get("role_specification_id", ""),
            considered=tuple(
                ProposalOption(
                    recommendation=Recommendation(item["recommendation"]),
                    viable=item["viable"],
                    reason=item["reason"],
                    subject_employee_ids=tuple(item.get("subject_employee_ids", ())),
                )
                for item in data.get("considered", ())
            ),
            evidence=evidence_tuple(data.get("evidence")),
            requires_ceo_approval=data.get("requires_ceo_approval", False),
            approval=ApprovalState(data.get("approval", ApprovalState.PROPOSED.value)),
            notes=data.get("notes", ""),
        )


def retraining_candidates(
    missing: tuple[str, ...], registry: CapabilityRegistry
) -> tuple[str, ...]:
    """Employees who provide a capability one explicit hop from what is missing.

    Restricted and archived employees are excluded by `providers()`, so a
    candidate under evaluation is never offered as the cheap answer to the gap
    they were brought in for.
    """
    if not missing:
        return ()
    known = tuple(item for item in missing if item in registry.graph)
    if not known:
        return ()
    adjacent = registry.graph.adjacent(known)
    found: set[str] = set()
    for capability_id in adjacent:
        resolved = registry.providers(capability_id)
        found.update(resolved.provided_by)
    return tuple(sorted(found))


def rank_options(
    gap: CapabilityGap, registry: CapabilityRegistry, report: CoverageReport | None = None
) -> tuple[ProposalOption, ...]:
    """Every answer considered for this gap, viable ones first, cheapest first.

    Returned in full rather than filtered: a reviewer who only sees the winner
    cannot tell whether the cheap options were considered and rejected or never
    looked at.
    """
    options: list[ProposalOption] = []
    dormant_providers = tuple(
        sorted({e for c in gap.covered_dormant for e in registry.providers(c).dormant_providers})
    )
    whole_role = (
        report.employees_covering_all(active_only=True) if report is not None else ()
    )

    options.append(
        ProposalOption(
            recommendation=Recommendation.NO_ACTION,
            viable=not gap.missing and not gap.covered_dormant,
            reason=(
                "every required capability has an active provider"
                if not gap.missing and not gap.covered_dormant
                else f"{len(gap.missing)} capability(s) missing, "
                f"{len(gap.covered_dormant)} covered only by dormant employees"
            ),
        )
    )
    options.append(
        ProposalOption(
            recommendation=Recommendation.USE_EXISTING_EMPLOYEE,
            viable=bool(whole_role) and not gap.missing,
            reason=(
                f"{whole_role[0]} already provides every required capability"
                if whole_role and not gap.missing
                else "no single existing employee provides the whole required set"
            ),
            subject_employee_ids=whole_role[:1],
        )
    )
    options.append(
        ProposalOption(
            recommendation=Recommendation.ACTIVATE_DORMANT_EMPLOYEE,
            viable=not gap.missing and bool(dormant_providers),
            reason=(
                "the company already employs this capability; it is dormant"
                if not gap.missing and dormant_providers
                else "activation cannot cover a capability nobody holds"
            ),
            subject_employee_ids=dormant_providers,
        )
    )

    retrainable = retraining_candidates(gap.missing, registry)
    recurring = gap.frequency.frequency is NeedFrequency.RECURRING
    options.append(
        ProposalOption(
            recommendation=Recommendation.RETRAIN_EMPLOYEE,
            viable=bool(gap.missing) and bool(retrainable) and recurring,
            reason=(
                "an existing employee covers capabilities adjacent to the missing set: "
                + ", ".join(retrainable)
                if retrainable
                else "nobody provides a capability adjacent to the missing set"
            ),
            subject_employee_ids=retrainable,
        )
    )
    options.append(
        ProposalOption(
            recommendation=Recommendation.TEMPORARY_SPECIALIST,
            viable=bool(gap.missing) and not recurring,
            reason=(
                f"the need was observed {gap.frequency.observed_occurrences} time(s) and is "
                f"recorded as {gap.frequency.frequency.value}; a temporary specialist ends "
                "with the task"
                if not recurring
                else "a recurring need is not answered by repeatedly hiring a temporary"
            ),
        )
    )
    options.append(
        ProposalOption(
            recommendation=Recommendation.CREATE_CANDIDATE_ROLE,
            viable=bool(gap.missing) and recurring and not retrainable,
            reason=(
                f"the need recurred {gap.frequency.observed_occurrences} times in "
                f"{gap.frequency.window_days} days and nobody adjacent can be retrained"
                if recurring and not retrainable
                else "a permanent role is the most expensive answer and a cheaper one applies"
            ),
        )
    )
    return tuple(sorted(options, key=lambda option: option.sort_key))


def propose_for_gap(
    gap: CapabilityGap,
    registry: CapabilityRegistry,
    *,
    proposal_id: str,
    proposed_on: dt.date,
    report: CoverageReport | None = None,
    role_specification_id: str = "",
    permissions: dict[str, Any] | None = None,
    department: str = "",
    extra_evidence: tuple[Evidence, ...] = (),
    notes: str = "",
) -> WorkforceProposal:
    """The deterministic recommendation for one proven gap.

    `role_specification_id` is required only when the table lands on
    `CREATE_CANDIDATE_ROLE`; the caller is told so by an exception rather than
    by a proposal that silently downgrades to something cheaper.
    """
    options = rank_options(gap, registry, report)
    chosen = next((option for option in options if option.viable), None)
    if chosen is None:
        raise WorkforceError(
            f"gap {gap.gap_id}: no recommendation applies. This is a bug in the gap "
            "record or in the decision table, not an organizational conclusion"
        )
    evidence = tuple(gap.evidence) + tuple(gap.frequency.evidence) + evidence_tuple(extra_evidence)
    rationale = f"{chosen.recommendation.value}: {chosen.reason}."
    if gap.missing:
        rationale += " Missing: " + ", ".join(gap.missing) + "."
    if gap.covered_dormant:
        rationale += " Dormant-only: " + ", ".join(gap.covered_dormant) + "."
    return WorkforceProposal(
        proposal_id=proposal_id,
        recommendation=chosen.recommendation,
        rationale=rationale,
        proposed_on=proposed_on,
        gap_id=gap.gap_id,
        subject_employee_ids=chosen.subject_employee_ids,
        role_specification_id=(
            role_specification_id
            if chosen.recommendation is Recommendation.CREATE_CANDIDATE_ROLE
            else ""
        ),
        considered=options,
        evidence=evidence,
        requires_ceo_approval=requires_ceo_approval(
            chosen.recommendation, department=department, permissions=permissions
        ),
        notes=notes,
    )


def requires_ceo_approval(
    recommendation: Recommendation,
    *,
    department: str = "",
    permissions: dict[str, Any] | None = None,
) -> bool:
    """Whether `permissions.yaml` reserves this decision for the CEO.

    Read from the permission file rather than hard-coded, so the answer changes
    when the CEO changes the reservation list and not when this module is
    edited. With no permissions supplied it fails closed for executive work.
    """
    if department != EXECUTIVE_DEPARTMENT:
        return False
    if recommendation not in (
        Recommendation.CREATE_CANDIDATE_ROLE,
        Recommendation.ARCHIVE_ROLE,
        Recommendation.MERGE_ROLES,
    ):
        return False
    if permissions is None:
        return True
    reserved = permissions.get("ceo_reserved", [])
    return "hire_or_remove_executive_role" in reserved


def record_decision(
    proposal: WorkforceProposal, *, decision: ApprovalState, by: str, reason: str
) -> WorkforceProposal:
    """Record what a human decided about a proposal. Still does not act.

    The returned proposal has a different `approval` value and nothing else. No
    employee is created, activated, retrained or archived by anything in this
    package; those are edits to `org_registry.yaml`, which this package never
    opens for write.
    """
    if not isinstance(decision, ApprovalState):
        raise WorkforceError("decision must be an ApprovalState")
    assert_prose(by, "decision by")
    assert_prose(reason, "decision reason")
    if proposal.approval in (ApprovalState.APPROVED, ApprovalState.REJECTED) and decision is not proposal.approval:
        raise WorkforceError(
            f"proposal {proposal.proposal_id} is already {proposal.approval.value}; "
            "record a new proposal citing this one rather than reversing it in place"
        )
    return replace(proposal, approval=decision)
