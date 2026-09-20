"""Organizational change as an experiment specification, and its review.

## Small, reversible, measured

Constitution rule 10 says every organizational change must be reversible and
rule 9 says isolate the variables. An `OrganizationChangeProposal` is those two
rules as a record class: it cannot exist without a rollback, without success
metrics, without kill conditions, and without saying what does *not* change -
the field that stops a three-line proposal from quietly meaning a
reorganization.

`ChangeExperiment` adds the discipline that makes a later comparison mean
anything: one changed variable, an explicit list of locked ones, a baseline
window and an observation window. When those two windows differ materially in
length, the experiment records that in its own limitations rather than leaving
it for the reader to notice - section 1 of the brief, enforced at the one place
it actually matters.

## Nothing here implements anything

There is no apply, no writer, no rollback executor. `implemented_by` names a
person and refuses a machine; a proposal whose implementation would touch
`org_registry.yaml`, `permissions.yaml`, the constitution or the agent contract
schema must be CEO-reserved, and even then the record is a description of an
edit somebody else makes by hand.

## Causality is never claimed

`OrganizationChangeReview` carries a caveat that cannot be emptied and a
`claims_causality` property that is always `False`. A single before/after
comparison over an organization with one of everything is not a controlled
experiment and cannot become one by being written down carefully. Where the
review has one observation or none, the single-observation caveat is added by
the record itself, because the author who most needs that sentence is the one
least likely to write it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
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
from .recommendations import (
    CONSTITUTIONAL_POLICIES,
    Decision,
    RecommendationState,
    Reversibility,
    assert_policy_ids,
)
from .signals import Direction, Measurement
from .window import ReviewWindow

# The four files Company OS treats as canonical contracts. A record may describe
# an edit to one; nothing in this package may perform one.
CANONICAL_CONTRACTS = (
    "company/org_registry.yaml",
    "company/permissions.yaml",
    "company/constitution.md",
    "company/agent_contract.schema.yaml",
)

CAUSALITY_CAVEAT = (
    "a before/after difference over one organization is not a controlled result; "
    "this review reports what moved, not what caused it"
)

SINGLE_OBSERVATION_CAVEAT = (
    "one observation or fewer after the change: the difference and the noise are "
    "indistinguishable at this count"
)


class ApprovalAuthority(Enum):
    """Who has to say yes. Read off `permissions.yaml`, never widened here."""

    MANAGER = "manager"
    DEPARTMENT_LEAD = "department_lead"
    CEO = "ceo"


class ChangeOutcome(Enum):
    KEEP = "keep"
    REVERT = "revert"
    INVESTIGATE = "investigate"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


@dataclass(frozen=True)
class SuccessMetric:
    """What would count as this change having worked, stated before it starts."""

    metric_id: str
    description: str
    baseline: Measurement
    target_direction: Direction
    target_value: float | None = None

    def __post_init__(self) -> None:
        assert_record_id(self.metric_id, "metric_id")
        assert_prose(self.description, f"metric {self.metric_id} description")
        if not isinstance(self.baseline, Measurement):
            raise OrgIntelligenceError("metric baseline must be a Measurement")
        if not isinstance(self.target_direction, Direction):
            raise OrgIntelligenceError("metric target_direction must be a Direction")
        if self.target_value is not None:
            if isinstance(self.target_value, bool) or not isinstance(
                self.target_value, (int, float)
            ):
                raise OrgIntelligenceError("metric target_value must be a number or None")
            object.__setattr__(self, "target_value", float(self.target_value))
        if self.target_direction is Direction.NEITHER and self.target_value is not None:
            raise OrgIntelligenceError(
                f"metric {self.metric_id}: a target with no direction cannot be met or missed"
            )

    @property
    def has_baseline(self) -> bool:
        return self.baseline.measured

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["baseline"] = self.baseline.to_dict()
        base["has_baseline"] = self.has_baseline
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SuccessMetric:
        return cls(
            metric_id=data["metric_id"],
            description=data["description"],
            baseline=Measurement.from_dict(data.get("baseline", {})),
            target_direction=Direction(data["target_direction"]),
            target_value=data.get("target_value"),
        )


@dataclass(frozen=True)
class OrganizationChangeProposal:
    """A described, bounded, reversible organizational change. Nobody has made it."""

    proposal_id: str
    recommendation_ids: tuple[str, ...]
    what_changes: str
    what_does_not_change: str
    expected_benefit: str
    expected_implementation_cost: str
    reversibility: Reversibility
    rollback: str
    observation_window: ReviewWindow
    required_approval: ApprovalAuthority = ApprovalAuthority.MANAGER
    affected_subjects: tuple[str, ...] = ()
    success_metrics: tuple[SuccessMetric, ...] = ()
    kill_conditions: tuple[str, ...] = ()
    reconsider_if: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    requires_ceo_approval: bool = False
    reserved_actions: tuple[str, ...] = ()
    touches_policies: tuple[str, ...] = ()
    implementation_paths: tuple[str, ...] = ()
    implemented_by: str = "unassigned human owner"
    state: RecommendationState = RecommendationState.PROPOSED
    decision: Decision | None = None
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.proposal_id, "proposal_id")
        for name, kind in (
            ("reversibility", Reversibility),
            ("required_approval", ApprovalAuthority),
            ("state", RecommendationState),
        ):
            if not isinstance(getattr(self, name), kind):
                raise OrgIntelligenceError(f"change proposal {name} must be a {kind.__name__}")
        if not isinstance(self.observation_window, ReviewWindow):
            raise OrgIntelligenceError("observation_window must be a ReviewWindow")
        for name in (
            "what_changes",
            "what_does_not_change",
            "expected_benefit",
            "expected_implementation_cost",
            "rollback",
        ):
            assert_prose(getattr(self, name), f"change proposal {name}")
        assert_human(self.implemented_by, "change proposal implemented_by")
        object.__setattr__(
            self,
            "recommendation_ids",
            tuple(assert_record_id(item, "recommendation_id") for item in self.recommendation_ids or ()),
        )
        object.__setattr__(
            self,
            "affected_subjects",
            tuple(assert_ref(item, "affected subject") for item in self.affected_subjects or ()),
        )
        object.__setattr__(
            self,
            "implementation_paths",
            tuple(assert_ref(item, "implementation path") for item in self.implementation_paths or ()),
        )
        object.__setattr__(
            self,
            "reserved_actions",
            tuple(sorted(set(assert_ref(item, "reserved_action") for item in self.reserved_actions or ()))),
        )
        object.__setattr__(
            self,
            "touches_policies",
            assert_policy_ids(self.touches_policies, "change proposal touches_policies"),
        )
        object.__setattr__(self, "risks", text_tuple(self.risks, "change proposal risks"))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if not isinstance(self.requires_ceo_approval, bool):
            raise OrgIntelligenceError("requires_ceo_approval must be a bool")
        if not isinstance(self.notes, str):
            raise OrgIntelligenceError("change proposal notes must be a string")
        if not isinstance(self.success_metrics, tuple) or any(
            not isinstance(item, SuccessMetric) for item in self.success_metrics
        ):
            raise OrgIntelligenceError("success_metrics must be a tuple of SuccessMetric")

        if not self.recommendation_ids:
            raise OrgIntelligenceError(
                f"change proposal {self.proposal_id}: name the recommendation(s) it "
                "implements. A change with no recommendation behind it skipped the evidence"
            )
        assert_evidence_backed(
            self.evidence,
            f"change proposal {self.proposal_id} evidence",
            "a change proposal carries the evidence forward so it can be read alone",
        )
        if not self.success_metrics:
            raise OrgIntelligenceError(
                f"change proposal {self.proposal_id}: say how anyone would know this worked, "
                "before it starts. A change with no success metric cannot be reviewed later"
            )
        object.__setattr__(
            self,
            "kill_conditions",
            nonempty_text_tuple(
                self.kill_conditions,
                f"change proposal {self.proposal_id} kill_conditions",
                "state what would stop this mid-flight (constitution rule 10)",
            ),
        )
        object.__setattr__(
            self,
            "reconsider_if",
            nonempty_text_tuple(
                self.reconsider_if,
                f"change proposal {self.proposal_id} reconsider_if",
                "state what would make this worth revisiting after it is decided",
            ),
        )

        constitutional = set(self.touches_policies) & CONSTITUTIONAL_POLICIES
        contracts = tuple(
            path for path in self.implementation_paths if path in CANONICAL_CONTRACTS
        )
        if (constitutional or contracts) and not self.requires_ceo_approval:
            raise AdvisoryViolation(
                f"change proposal {self.proposal_id} would touch "
                + ", ".join(sorted(set(constitutional) | set(contracts)))
                + " without CEO approval. These are the company's canonical contracts; "
                "changing one is a CEO-reserved decision"
            )
        if self.reserved_actions and not self.requires_ceo_approval:
            raise AdvisoryViolation(
                f"change proposal {self.proposal_id}: reserves "
                + ", ".join(self.reserved_actions)
                + " but does not require CEO approval"
            )
        if self.requires_ceo_approval and self.required_approval is not ApprovalAuthority.CEO:
            raise AdvisoryViolation(
                f"change proposal {self.proposal_id}: CEO approval is required but the "
                f"approval authority says {self.required_approval.value}"
            )

        if self.decision is not None and not isinstance(self.decision, Decision):
            raise OrgIntelligenceError("change proposal decision must be a Decision")
        if self.state is not RecommendationState.PROPOSED and self.decision is None:
            raise AdvisoryViolation(
                f"change proposal {self.proposal_id} is {self.state.value} with nobody's "
                "name on it. This subsystem proposes; people decide"
            )
        if self.decision is not None and self.decision.state is not self.state:
            raise OrgIntelligenceError(
                f"change proposal {self.proposal_id}: state and decision disagree"
            )

    @property
    def touches_canonical_contract(self) -> bool:
        return any(path in CANONICAL_CONTRACTS for path in self.implementation_paths)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["observation_window"] = self.observation_window.to_dict()
        base["success_metrics"] = [metric.to_dict() for metric in self.success_metrics]
        base["touches_canonical_contract"] = self.touches_canonical_contract
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationChangeProposal:
        decision = data.get("decision")
        return cls(
            proposal_id=data["proposal_id"],
            recommendation_ids=tuple(data.get("recommendation_ids", ())),
            what_changes=data["what_changes"],
            what_does_not_change=data["what_does_not_change"],
            expected_benefit=data["expected_benefit"],
            expected_implementation_cost=data["expected_implementation_cost"],
            reversibility=Reversibility(data["reversibility"]),
            rollback=data["rollback"],
            observation_window=ReviewWindow.from_dict(data["observation_window"]),
            required_approval=ApprovalAuthority(
                data.get("required_approval", ApprovalAuthority.MANAGER.value)
            ),
            affected_subjects=tuple(data.get("affected_subjects", ())),
            success_metrics=tuple(
                SuccessMetric.from_dict(item) for item in data.get("success_metrics", ())
            ),
            kill_conditions=tuple(data.get("kill_conditions", ())),
            reconsider_if=tuple(data.get("reconsider_if", ())),
            risks=tuple(data.get("risks", ())),
            evidence=evidence_tuple(data.get("evidence")),
            requires_ceo_approval=data.get("requires_ceo_approval", False),
            reserved_actions=tuple(data.get("reserved_actions", ())),
            touches_policies=tuple(data.get("touches_policies", ())),
            implementation_paths=tuple(data.get("implementation_paths", ())),
            implemented_by=data.get("implemented_by", "unassigned human owner"),
            state=RecommendationState(data.get("state", RecommendationState.PROPOSED.value)),
            decision=Decision.from_dict(decision) if decision else None,
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ChangeExperiment:
    """One changed variable, everything else named and locked, two windows."""

    experiment_id: str
    change_proposal_id: str
    hypothesis: str
    changed_variable: str
    baseline_window: ReviewWindow
    observation_window: ReviewWindow
    rollback_condition: str
    locked_variables: tuple[str, ...] = ()
    baseline_metrics: tuple[SuccessMetric, ...] = ()
    baseline_evidence: tuple[Evidence, ...] = ()
    success_metrics: tuple[SuccessMetric, ...] = ()
    limitations: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.experiment_id, "experiment_id")
        assert_record_id(self.change_proposal_id, "change_proposal_id")
        for name in ("hypothesis", "changed_variable", "rollback_condition"):
            assert_prose(getattr(self, name), f"experiment {name}")
        for name in ("baseline_window", "observation_window"):
            if not isinstance(getattr(self, name), ReviewWindow):
                raise OrgIntelligenceError(f"experiment {name} must be a ReviewWindow")
        for name in ("baseline_metrics", "success_metrics"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(
                not isinstance(item, SuccessMetric) for item in values
            ):
                raise OrgIntelligenceError(f"experiment {name} must be a tuple of SuccessMetric")
        object.__setattr__(self, "baseline_evidence", evidence_tuple(self.baseline_evidence))
        if not isinstance(self.notes, str):
            raise OrgIntelligenceError("experiment notes must be a string")

        object.__setattr__(
            self,
            "locked_variables",
            nonempty_text_tuple(
                self.locked_variables,
                f"experiment {self.experiment_id} locked_variables",
                "constitution rule 9: name what was held still, or the comparison is "
                "between two different companies",
            ),
        )
        assert_evidence_backed(
            self.baseline_evidence,
            f"experiment {self.experiment_id} baseline_evidence",
            "a before/after with no recorded before is an after",
        )
        if not self.baseline_metrics:
            raise OrgIntelligenceError(
                f"experiment {self.experiment_id}: a baseline is measurements taken before "
                "the change, not a description of how things felt"
            )
        if not any(metric.has_baseline for metric in self.baseline_metrics):
            raise OrgIntelligenceError(
                f"experiment {self.experiment_id}: no baseline metric carries a measured "
                "value. Nothing later can be compared against it"
            )

        limitations = text_tuple(self.limitations, "experiment limitations")
        mismatch = self.baseline_window.mismatch_caveat(self.observation_window)
        if mismatch and mismatch not in limitations:
            limitations = limitations + (mismatch,)
        if CAUSALITY_CAVEAT not in limitations:
            limitations = limitations + (CAUSALITY_CAVEAT,)
        object.__setattr__(self, "limitations", limitations)

    @property
    def windows_comparable(self) -> bool:
        return self.baseline_window.comparable_to(self.observation_window)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["baseline_window"] = self.baseline_window.to_dict()
        base["observation_window"] = self.observation_window.to_dict()
        base["baseline_metrics"] = [metric.to_dict() for metric in self.baseline_metrics]
        base["success_metrics"] = [metric.to_dict() for metric in self.success_metrics]
        base["windows_comparable"] = self.windows_comparable
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ChangeExperiment:
        return cls(
            experiment_id=data["experiment_id"],
            change_proposal_id=data["change_proposal_id"],
            hypothesis=data["hypothesis"],
            changed_variable=data["changed_variable"],
            baseline_window=ReviewWindow.from_dict(data["baseline_window"]),
            observation_window=ReviewWindow.from_dict(data["observation_window"]),
            rollback_condition=data["rollback_condition"],
            locked_variables=tuple(data.get("locked_variables", ())),
            baseline_metrics=tuple(
                SuccessMetric.from_dict(item) for item in data.get("baseline_metrics", ())
            ),
            baseline_evidence=evidence_tuple(data.get("baseline_evidence")),
            success_metrics=tuple(
                SuccessMetric.from_dict(item) for item in data.get("success_metrics", ())
            ),
            limitations=tuple(data.get("limitations", ())),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class MetricComparison:
    """Expected against actual for one metric. `moved` is a direction, not a cause."""

    metric_id: str
    expected: Measurement
    actual: Measurement
    note: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.metric_id, "metric_id")
        for name in ("expected", "actual"):
            if not isinstance(getattr(self, name), Measurement):
                raise OrgIntelligenceError(f"comparison {name} must be a Measurement")
        if not isinstance(self.note, str):
            raise OrgIntelligenceError("comparison note must be a string")

    @property
    def delta(self) -> float | None:
        if not (self.expected.measured and self.actual.measured):
            return None
        return self.actual.value - self.expected.value

    @property
    def moved(self) -> str | None:
        """`improved`, `worsened`, `unchanged`, or `None` when nobody can tell."""
        delta = self.delta
        if delta is None:
            return None
        if delta == 0:
            return "unchanged"
        direction = self.actual.direction
        if direction is Direction.HIGHER_IS_WORSE:
            return "worsened" if delta > 0 else "improved"
        if direction is Direction.LOWER_IS_WORSE:
            return "improved" if delta > 0 else "worsened"
        return "changed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "expected": self.expected.to_dict(),
            "actual": self.actual.to_dict(),
            "delta": self.delta,
            "moved": self.moved,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricComparison:
        return cls(
            metric_id=data["metric_id"],
            expected=Measurement.from_dict(data.get("expected", {})),
            actual=Measurement.from_dict(data.get("actual", {})),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class OrganizationChangeReview:
    """What happened after a change. It never says the change caused it."""

    review_id: str
    experiment_id: str
    observed_window: ReviewWindow
    outcome: ChangeOutcome
    summary: str
    comparisons: tuple[MetricComparison, ...] = ()
    regressions: tuple[str, ...] = ()
    unintended_effects: tuple[str, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    limitations: tuple[str, ...] = ()
    observation_count: int | None = None
    learning_ref: str = ""
    reviewed_by: str = ""
    caveat: str = CAUSALITY_CAVEAT

    def __post_init__(self) -> None:
        assert_record_id(self.review_id, "review_id")
        assert_record_id(self.experiment_id, "experiment_id")
        if not isinstance(self.observed_window, ReviewWindow):
            raise OrgIntelligenceError("observed_window must be a ReviewWindow")
        if not isinstance(self.outcome, ChangeOutcome):
            raise OrgIntelligenceError("change review outcome must be a ChangeOutcome")
        assert_prose(self.summary, f"change review {self.review_id} summary")
        if not isinstance(self.comparisons, tuple) or any(
            not isinstance(item, MetricComparison) for item in self.comparisons
        ):
            raise OrgIntelligenceError("comparisons must be a tuple of MetricComparison")
        object.__setattr__(self, "regressions", text_tuple(self.regressions, "regressions"))
        object.__setattr__(
            self, "unintended_effects", text_tuple(self.unintended_effects, "unintended_effects")
        )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(
            self, "learning_ref", optional_ref(self.learning_ref, "learning_ref")
        )
        if self.reviewed_by:
            assert_human(self.reviewed_by, "change review reviewed_by")
        if self.observation_count is not None and (
            isinstance(self.observation_count, bool)
            or not isinstance(self.observation_count, int)
            or self.observation_count < 0
        ):
            raise OrgIntelligenceError("observation_count must be a non-negative integer or None")

        assert_evidence_backed(
            self.evidence,
            f"change review {self.review_id} evidence",
            "a review of a change points at what was measured after it",
        )
        if CAUSALITY_CAVEAT not in str(self.caveat):
            raise AdvisoryViolation(
                f"change review {self.review_id}: the causality caveat may be extended but "
                "not removed. A before/after over one organization is not a controlled "
                "result, whatever the outcome says"
            )

        limitations = text_tuple(self.limitations, "change review limitations")
        if self.observation_count is None or self.observation_count <= 1:
            if SINGLE_OBSERVATION_CAVEAT not in limitations:
                limitations = limitations + (SINGLE_OBSERVATION_CAVEAT,)
        if self.observed_window.limitation not in limitations:
            limitations = limitations + (self.observed_window.limitation,)
        object.__setattr__(self, "limitations", limitations)

    @property
    def claims_causality(self) -> bool:
        """Always `False`. Kept as a property so a caller can assert on it."""
        return False

    @property
    def improved(self) -> tuple[str, ...]:
        return tuple(item.metric_id for item in self.comparisons if item.moved == "improved")

    @property
    def worsened(self) -> tuple[str, ...]:
        return tuple(item.metric_id for item in self.comparisons if item.moved == "worsened")

    @property
    def unmeasured(self) -> tuple[str, ...]:
        return tuple(item.metric_id for item in self.comparisons if item.moved is None)

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["observed_window"] = self.observed_window.to_dict()
        base["comparisons"] = [item.to_dict() for item in self.comparisons]
        base.update(
            claims_causality=self.claims_causality,
            improved=list(self.improved),
            worsened=list(self.worsened),
            unmeasured=list(self.unmeasured),
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationChangeReview:
        return cls(
            review_id=data["review_id"],
            experiment_id=data["experiment_id"],
            observed_window=ReviewWindow.from_dict(data["observed_window"]),
            outcome=ChangeOutcome(data["outcome"]),
            summary=data["summary"],
            comparisons=tuple(
                MetricComparison.from_dict(item) for item in data.get("comparisons", ())
            ),
            regressions=tuple(data.get("regressions", ())),
            unintended_effects=tuple(data.get("unintended_effects", ())),
            evidence=evidence_tuple(data.get("evidence")),
            limitations=tuple(data.get("limitations", ())),
            observation_count=data.get("observation_count"),
            learning_ref=data.get("learning_ref", ""),
            reviewed_by=data.get("reviewed_by", ""),
            caveat=data.get("caveat", CAUSALITY_CAVEAT),
        )


def significant(
    recommendations: Iterable[Any],
    *,
    irreversible_is_significant: bool = True,
) -> tuple[Any, ...]:
    """Recommendations that need a change proposal rather than a note.

    Significant means one of three visible things: it is CEO-reserved, it is
    not simply reversible, or it touches a declared policy. All three are fields
    on the record, so a reader can check the classification rather than trusting
    it.
    """
    out = []
    for item in recommendations:
        reserved = bool(getattr(item, "requires_ceo_approval", False))
        policies = bool(getattr(item, "touches_policies", ()))
        reversibility = getattr(item, "reversibility", Reversibility.REVERSIBLE)
        hard = irreversible_is_significant and reversibility is not Reversibility.REVERSIBLE
        if reserved or policies or hard:
            out.append(item)
    return tuple(out)
