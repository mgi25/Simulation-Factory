"""What to do about a finding - proposed, never done, and never self-approved.

## The three refusals

**It cannot act.** There is no `apply`, no writer, no side effect. The strongest
object this module produces is a frozen record in the `PROPOSED` state.
`merge_roles` is a sentence; merging roles is a human editing
`org_registry.yaml`, and this package never opens that file.

**It cannot approve itself.** `APPROVED` and `REJECTED` require a `Decision`,
and a decision requires a name that is not `automatic`, `system`,
`org_intelligence` or any of the rest (`common.AUTOMATIC_MARKERS`). A
recommendation that arrives approved with nobody's name on it is refused at
construction, and `integrity.py` refuses it again for records that came from a
file rather than a constructor.

**It cannot optimise away a constitutional rule.** `simplify_workflow` and
`automate_deterministic_step` are ordinary efficiency moves; the no-subagent
policy, the mission, the constitution and CEO authority are not available to
them at any efficiency. A recommendation of an ordinary type that touches one of
those raises `AdvisoryViolation` - not because the change is unthinkable, but
because it is a CEO decision wearing a workflow tweak's clothes.

## Reuse over reinvention

Seven of these types already mean something in `company/workforce/proposals.py`.
`WORKFORCE_EQUIVALENT` maps them, and a recommendation of one of those types
must point at the workforce record it consumes. So "the company should activate
someone" is one concept with one meaning, computed by the layer that owns it
(constitution rule 15), and this layer is the one that noticed.

## CEO reservation is read, not remembered

`ceo_reserved_actions` computes candidate reserved actions from a data table and
then intersects them with `permissions.yaml`'s own `ceo_reserved` list. With no
permissions supplied it fails closed and returns every candidate.
`unreserved_actions` reports the opposite direction - mapping entries the
permission file no longer names - which is the failure the workforce capsule
flags as a risk: rename the key and the flagging silently stops.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, Iterable, Mapping

from ai_platform.serde import to_jsonable
from company.workforce.proposals import Recommendation as WorkforceRecommendation
from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_evidence_backed,
    assert_human,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    nonempty_text_tuple,
    optional_ref,
    text_tuple,
)
from .errors import AdvisoryViolation, OrgIntelligenceError


class RecommendationType(Enum):
    """Section 5 of the brief, one value each."""

    NO_ACTION = "no_action"
    GATHER_MORE_EVIDENCE = "gather_more_evidence"
    INVESTIGATE = "investigate"
    ACTIVATE_DORMANT_EMPLOYEE = "activate_dormant_employee"
    RETRAIN_EMPLOYEE = "retrain_employee"
    TEMPORARY_SPECIALIST = "temporary_specialist"
    CREATE_CANDIDATE_ROLE = "create_candidate_role"
    MERGE_ROLES = "merge_roles"
    SPLIT_ROLE = "split_role"
    ARCHIVE_ROLE = "archive_role"
    CHANGE_MANAGER = "change_manager"
    SIMPLIFY_WORKFLOW = "simplify_workflow"
    REMOVE_APPROVAL_STEP = "remove_approval_step"
    ADD_APPROVAL_GATE = "add_approval_gate"
    AUTOMATE_DETERMINISTIC_STEP = "automate_deterministic_step"
    ADD_BENCHMARK = "add_benchmark"
    REVALIDATE_CONTRACT = "revalidate_contract"
    REVALIDATE_CAPSULE = "revalidate_capsule"
    REDUCE_CONTEXT = "reduce_context"
    REVISE_BUDGET = "revise_budget"


class RecommendationState(Enum):
    """Where a recommendation is. Never what it may do."""

    PROPOSED = "proposed"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    IMPLEMENTED_ELSEWHERE = "implemented_elsewhere"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Reversibility(Enum):
    REVERSIBLE = "reversible"
    REVERSIBLE_WITH_COST = "reversible_with_cost"
    IRREVERSIBLE = "irreversible"


# The types whose meaning already lives in company/workforce/proposals.py.
# Same word, same decision; this layer noticed it, that layer defines it.
WORKFORCE_EQUIVALENT: dict[RecommendationType, WorkforceRecommendation] = {
    RecommendationType.NO_ACTION: WorkforceRecommendation.NO_ACTION,
    RecommendationType.ACTIVATE_DORMANT_EMPLOYEE: (
        WorkforceRecommendation.ACTIVATE_DORMANT_EMPLOYEE
    ),
    RecommendationType.RETRAIN_EMPLOYEE: WorkforceRecommendation.RETRAIN_EMPLOYEE,
    RecommendationType.TEMPORARY_SPECIALIST: WorkforceRecommendation.TEMPORARY_SPECIALIST,
    RecommendationType.CREATE_CANDIDATE_ROLE: WorkforceRecommendation.CREATE_CANDIDATE_ROLE,
    RecommendationType.MERGE_ROLES: WorkforceRecommendation.MERGE_ROLES,
    RecommendationType.ARCHIVE_ROLE: WorkforceRecommendation.ARCHIVE_ROLE,
}

# Types that need a workforce record underneath them. NO_ACTION is excluded:
# recommending nothing consumes nothing.
_NEEDS_WORKFORCE_RECORD = frozenset(WORKFORCE_EQUIVALENT) - {RecommendationType.NO_ACTION}

# Types that must name what they are about.
_NEEDS_SUBJECTS = frozenset(
    {
        RecommendationType.ACTIVATE_DORMANT_EMPLOYEE,
        RecommendationType.RETRAIN_EMPLOYEE,
        RecommendationType.MERGE_ROLES,
        RecommendationType.SPLIT_ROLE,
        RecommendationType.ARCHIVE_ROLE,
        RecommendationType.CHANGE_MANAGER,
        RecommendationType.SIMPLIFY_WORKFLOW,
        RecommendationType.REMOVE_APPROVAL_STEP,
        RecommendationType.ADD_APPROVAL_GATE,
        RecommendationType.AUTOMATE_DETERMINISTIC_STEP,
        RecommendationType.REVALIDATE_CONTRACT,
        RecommendationType.REVALIDATE_CAPSULE,
        RecommendationType.REDUCE_CONTEXT,
        RecommendationType.REVISE_BUDGET,
    }
)

# Recommending nothing needs no kill condition; everything else does.
_NEEDS_NO_KILL_CONDITIONS = frozenset({RecommendationType.NO_ACTION})

# Ordinary efficiency moves. None of them may reach a constitutional policy.
ORDINARY_OPTIMIZATION_TYPES = frozenset(
    {
        RecommendationType.SIMPLIFY_WORKFLOW,
        RecommendationType.REMOVE_APPROVAL_STEP,
        RecommendationType.AUTOMATE_DETERMINISTIC_STEP,
        RecommendationType.REDUCE_CONTEXT,
        RecommendationType.REVISE_BUDGET,
    }
)

# Policy identifiers a record may declare it would touch, and the
# permissions.yaml ceo_reserved action each one maps to.
POLICY_RESERVED_ACTIONS: dict[str, str] = {
    "no_subagents": "change_no_subagents_policy",
    "company_mission": "change_company_mission",
    "constitution": "amend_constitution",
    "primary_engine": "change_primary_engine",
    "content_format": "drop_entire_content_format",
    "architecture": "merge_major_architecture_rewrite",
    "recurring_paid_api_spend": "large_or_recurring_paid_api_spend",
    "production_data": "delete_important_production_or_company_data",
    "public_publication": "publish_public_video",
}

# The policies no efficiency argument may reach. Constitution rules 1 and 2 and
# the amendment clause: changing any of these is a CEO decision by definition.
CONSTITUTIONAL_POLICIES = frozenset(
    {"no_subagents", "company_mission", "constitution", "ceo_authority"}
)

# Role-shaped changes that become CEO-reserved when the subject is an executive.
_EXECUTIVE_TYPES = frozenset(
    {
        RecommendationType.CREATE_CANDIDATE_ROLE,
        RecommendationType.ARCHIVE_ROLE,
        RecommendationType.MERGE_ROLES,
        RecommendationType.SPLIT_ROLE,
        RecommendationType.CHANGE_MANAGER,
    }
)

EXECUTIVE_DEPARTMENT = "executive"
EXECUTIVE_RESERVED_ACTION = "hire_or_remove_executive_role"


def assert_policy_ids(values: Iterable[str], field: str) -> tuple[str, ...]:
    """Policy ids come from a closed vocabulary, so a typo cannot dodge a gate.

    `no_subagent` would otherwise be a policy nobody reserves, and the record
    that carried it would pass every check this module makes.
    """
    known = set(POLICY_RESERVED_ACTIONS) | CONSTITUTIONAL_POLICIES
    out: list[str] = []
    for value in values or ():
        if value not in known:
            raise OrgIntelligenceError(
                f"{field}: {value!r} is not a known policy id. Known: "
                + ", ".join(sorted(known))
            )
        out.append(value)
    if len(set(out)) != len(out):
        raise OrgIntelligenceError(f"{field}: duplicate policy ids")
    return tuple(out)


def ceo_reserved_actions(
    recommendation_type: RecommendationType,
    *,
    touches_policies: Iterable[str] = (),
    subject_departments: Iterable[str] = (),
    permissions: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """The `ceo_reserved` action ids this change would trigger, sorted.

    Read from `permissions.yaml` rather than hard-coded, so the answer changes
    when the CEO changes the reservation list and not when this module is
    edited. With no permissions supplied it fails closed and returns every
    candidate.
    """
    candidates: set[str] = set()
    for policy in touches_policies or ():
        action = POLICY_RESERVED_ACTIONS.get(policy)
        if action:
            candidates.add(action)
    if recommendation_type in _EXECUTIVE_TYPES and EXECUTIVE_DEPARTMENT in set(
        subject_departments or ()
    ):
        candidates.add(EXECUTIVE_RESERVED_ACTION)
    if permissions is None:
        return tuple(sorted(candidates))
    reserved = set(permissions.get("ceo_reserved", ()) or ())
    return tuple(sorted(candidates & reserved))


def unreserved_actions(permissions: Mapping[str, Any]) -> tuple[str, ...]:
    """Mapped actions that `permissions.yaml` no longer reserves, sorted.

    The rename detector. If `ceo_reserved` stops naming `change_no_subagents_policy`,
    nothing in `ceo_reserved_actions` fails - it just quietly stops flagging.
    This function makes that visible, and `integrity.py` reports it.
    """
    reserved = set(permissions.get("ceo_reserved", ()) or ())
    mapped = set(POLICY_RESERVED_ACTIONS.values()) | {EXECUTIVE_RESERVED_ACTION}
    return tuple(sorted(mapped - reserved))


@dataclass(frozen=True)
class Decision:
    """Who decided, when, and why. The name may not be a machine."""

    state: RecommendationState
    by: str
    on: dt.date
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, RecommendationState):
            raise OrgIntelligenceError("decision state must be a RecommendationState")
        if self.state is RecommendationState.PROPOSED:
            raise OrgIntelligenceError(
                "PROPOSED is where a recommendation starts, not something anybody decides"
            )
        assert_human(self.by, "decision by")
        object.__setattr__(self, "on", assert_day(self.on, "decision on"))
        assert_prose(self.reason, "decision reason")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Decision:
        return cls(
            state=RecommendationState(data["state"]),
            by=data["by"],
            on=assert_day(data["on"], "decision on"),
            reason=data["reason"],
        )


@dataclass(frozen=True)
class OrganizationalRecommendation:
    """A proposed organizational change. Reading it changes nothing."""

    recommendation_id: str
    type: RecommendationType
    finding_ids: tuple[str, ...]
    rationale: str
    expected_benefit: str
    expected_cost: str
    risk: RiskLevel
    reversibility: Reversibility
    follow_up_measurement: str
    subjects: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    kill_conditions: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    requires_ceo_approval: bool = False
    reserved_actions: tuple[str, ...] = ()
    touches_policies: tuple[str, ...] = ()
    workforce_record_refs: tuple[str, ...] = ()
    state: RecommendationState = RecommendationState.PROPOSED
    decision: Decision | None = None
    review_id: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.recommendation_id, "recommendation_id")
        for name, kind in (
            ("type", RecommendationType),
            ("risk", RiskLevel),
            ("reversibility", Reversibility),
            ("state", RecommendationState),
        ):
            if not isinstance(getattr(self, name), kind):
                raise OrgIntelligenceError(f"recommendation {name} must be a {kind.__name__}")
        for name in ("rationale", "expected_benefit", "expected_cost", "follow_up_measurement"):
            assert_prose(getattr(self, name), f"recommendation {name}")
        object.__setattr__(
            self,
            "finding_ids",
            tuple(assert_record_id(item, "finding_id") for item in self.finding_ids or ()),
        )
        object.__setattr__(
            self,
            "subjects",
            tuple(assert_ref(item, "recommendation subject") for item in self.subjects or ()),
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(
            self, "kill_conditions", text_tuple(self.kill_conditions, "kill_conditions")
        )
        object.__setattr__(
            self,
            "dependencies",
            tuple(assert_ref(item, "recommendation dependency") for item in self.dependencies or ()),
        )
        object.__setattr__(
            self,
            "workforce_record_refs",
            tuple(assert_ref(item, "workforce_record_ref") for item in self.workforce_record_refs or ()),
        )
        object.__setattr__(
            self,
            "touches_policies",
            assert_policy_ids(self.touches_policies, "recommendation touches_policies"),
        )
        object.__setattr__(
            self,
            "reserved_actions",
            tuple(sorted(set(assert_ref(item, "reserved_action") for item in self.reserved_actions or ()))),
        )
        object.__setattr__(self, "review_id", optional_ref(self.review_id, "review_id"))
        if not isinstance(self.requires_ceo_approval, bool):
            raise OrgIntelligenceError("requires_ceo_approval must be a bool")
        if not isinstance(self.notes, str):
            raise OrgIntelligenceError("recommendation notes must be a string")

        if not self.finding_ids:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: name the finding it answers. "
                "A recommendation with no finding underneath it is a preference"
            )
        assert_evidence_backed(
            self.evidence,
            f"recommendation {self.recommendation_id} evidence",
            "every recommendation is evidence-backed; the evidence is normally the "
            "finding's own, carried forward so the record stands on its own",
        )
        if self.type in _NEEDS_SUBJECTS and not self.subjects:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: {self.type.value} must name what "
                "it is about"
            )
        if self.type is RecommendationType.MERGE_ROLES and len(self.subjects) < 2:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: merging roles needs at least two"
            )
        if self.type in _NEEDS_WORKFORCE_RECORD and not self.workforce_record_refs:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: {self.type.value} already means "
                "something in company/workforce; point at the record this consumes rather "
                "than recomputing it here (constitution rule 15)"
            )
        if self.type not in _NEEDS_NO_KILL_CONDITIONS:
            object.__setattr__(
                self,
                "kill_conditions",
                nonempty_text_tuple(
                    self.kill_conditions,
                    f"recommendation {self.recommendation_id} kill_conditions",
                    "say what would make this the wrong move, before anybody starts it",
                ),
            )

        constitutional = set(self.touches_policies) & CONSTITUTIONAL_POLICIES
        if constitutional and self.type in ORDINARY_OPTIMIZATION_TYPES:
            raise AdvisoryViolation(
                f"recommendation {self.recommendation_id}: {self.type.value} would touch "
                + ", ".join(sorted(constitutional))
                + ". These are constitutional, not efficiency dials. Propose the change as "
                "a CEO-reserved organizational change, or do not propose it"
            )
        if constitutional and not self.requires_ceo_approval:
            raise AdvisoryViolation(
                f"recommendation {self.recommendation_id}: touching "
                + ", ".join(sorted(constitutional))
                + " requires CEO approval (constitution, amendment clause)"
            )
        if self.reserved_actions and not self.requires_ceo_approval:
            raise AdvisoryViolation(
                f"recommendation {self.recommendation_id}: reserves "
                + ", ".join(self.reserved_actions)
                + " but does not require CEO approval"
            )

        if self.decision is not None and not isinstance(self.decision, Decision):
            raise OrgIntelligenceError("recommendation decision must be a Decision")
        decided = self.state in (
            RecommendationState.APPROVED,
            RecommendationState.REJECTED,
            RecommendationState.SUPERSEDED,
            RecommendationState.IMPLEMENTED_ELSEWHERE,
        )
        if decided and self.decision is None:
            raise AdvisoryViolation(
                f"recommendation {self.recommendation_id} is {self.state.value} with nobody's "
                "name on it. Organizational Intelligence does not approve its own "
                "recommendations; a decision names the person who made it"
            )
        # Checked before the state/decision match, because a proposed record
        # carrying any decision at all is wrong whichever state that decision
        # names, and the specific message is the useful one.
        if self.state is RecommendationState.PROPOSED and self.decision is not None:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: a proposed recommendation carries "
                "no decision"
            )
        if self.decision is not None and self.decision.state is not self.state:
            raise OrgIntelligenceError(
                f"recommendation {self.recommendation_id}: state {self.state.value} does not "
                f"match its decision ({self.decision.state.value})"
            )

    @property
    def is_action(self) -> bool:
        return self.type not in (
            RecommendationType.NO_ACTION,
            RecommendationType.GATHER_MORE_EVIDENCE,
        )

    @property
    def workforce_equivalent(self) -> WorkforceRecommendation | None:
        return WORKFORCE_EQUIVALENT.get(self.type)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["workforce_equivalent"] = (
            self.workforce_equivalent.value if self.workforce_equivalent else None
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationalRecommendation:
        decision = data.get("decision")
        return cls(
            recommendation_id=data["recommendation_id"],
            type=RecommendationType(data["type"]),
            finding_ids=tuple(data.get("finding_ids", ())),
            rationale=data["rationale"],
            expected_benefit=data["expected_benefit"],
            expected_cost=data["expected_cost"],
            risk=RiskLevel(data["risk"]),
            reversibility=Reversibility(data["reversibility"]),
            follow_up_measurement=data["follow_up_measurement"],
            subjects=tuple(data.get("subjects", ())),
            evidence=evidence_tuple(data.get("evidence")),
            kill_conditions=tuple(data.get("kill_conditions", ())),
            dependencies=tuple(data.get("dependencies", ())),
            requires_ceo_approval=data.get("requires_ceo_approval", False),
            reserved_actions=tuple(data.get("reserved_actions", ())),
            touches_policies=tuple(data.get("touches_policies", ())),
            workforce_record_refs=tuple(data.get("workforce_record_refs", ())),
            state=RecommendationState(data.get("state", RecommendationState.PROPOSED.value)),
            decision=Decision.from_dict(decision) if decision else None,
            review_id=data.get("review_id", ""),
            notes=data.get("notes", ""),
        )


def record_decision(
    recommendation: OrganizationalRecommendation,
    *,
    state: RecommendationState,
    by: str,
    on: dt.date,
    reason: str,
) -> OrganizationalRecommendation:
    """Record what a person decided. Still nothing is implemented.

    The returned record has a different `state` and a `decision` and nothing
    else. No role is merged, archived, retrained or reassigned by anything in
    this package; those are edits to files it never opens for write.
    """
    decision = Decision(state=state, by=by, on=on, reason=reason)
    if recommendation.decision is not None and recommendation.state is not state:
        raise OrgIntelligenceError(
            f"recommendation {recommendation.recommendation_id} is already "
            f"{recommendation.state.value}; record a new recommendation citing this one "
            "rather than reversing it in place"
        )
    return replace(recommendation, state=state, decision=decision)
