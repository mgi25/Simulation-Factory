"""What we changed, what we held still, and what would make us stop - written first.

## The specification exists to be written before the result

Every field here is answerable before a single view is counted, and that is the
point. A hypothesis recalled after seeing the numbers is a description of the
numbers; kill conditions invented after a bad week are a rationalisation.
`ExperimentSpecification` is a record with a `created_on`, stored append-only,
so what we said we were testing is still readable next to what we found.

Section 27 is the sharpest case: kill conditions must exist before result
review, and their thresholds are explicit input. Nothing here invents a number.
A `KillCondition` names a metric, a direction and a value the caller supplied,
because a threshold this code chose would be this code's opinion presented as
the company's policy.

## Changed and locked are different fields, and both are required

`variables_changed` says what we varied. `variables_locked` says what we
deliberately held constant. A reader needs both: "we changed the hook" means one
thing when the camera, theme and length were pinned, and almost nothing when
they were free to drift.

Locked is not "everything not listed as changed". It is what somebody actually
held, and the gap between the two is where confounding lives.

## Confounding is derived, not declared

`confounded` is a property, not a field a caller sets. It is True when more than
one variable changed, and the reasons name them. That way an experiment cannot
describe itself as clean; the count of what it varied decides.

Section 6 asks that one primary change be *supported* rather than required, so a
multi-variable experiment is legal - it is simply an experiment that says, in
its own serialised form, that causal attribution between its variables is not
available from it.

## Expectations are hypotheses and stay on this side of the line

`Expectation` carries a direction and optionally a range. It is stored on the
specification, never on an observation, and `results.py` reads it only to ask
"did the measurement move the way we guessed". Section 7: an expectation that
leaked into the observation record would be a prediction that later reads as a
measurement.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    assert_tag,
    evidence_tuple,
    ref_tuple,
    record_to_dict,
    tag_tuple,
    text_tuple,
)
from .errors import AnalyticsError
from .metrics import DEFAULT_REGISTRY, MetricRegistry
from .windows import AgeWindow


class Direction(Enum):
    """Which way a metric is expected, or observed, to move."""

    UP = "up"
    DOWN = "down"
    UNCHANGED = "unchanged"

    @property
    def opposite(self) -> Direction:
        if self is Direction.UP:
            return Direction.DOWN
        if self is Direction.DOWN:
            return Direction.UP
        return Direction.UNCHANGED


class ComparisonBasis(Enum):
    """How a comparison was constructed, which bounds what it can conclude.

    This is the single most consequential enum in the subsystem: `results.py`
    reads it to decide whether a causal claim is available at all, and only the
    last member can ever make one.

    `SINGLE_DELIVERABLE` - one thing measured, nothing to compare it with.
    `OBSERVATIONAL` - two things we made at different times. Everything differs:
        the audience, the season, what the platform was promoting that week.
    `MATCHED_PAIR` - a control and a variant, built deliberately, with one
        primary change and the rest declared locked. Better evidence, still not
        random assignment: the two still went out to different moments.
    `RANDOMIZED_SPLIT` - the platform assigned viewers to variants at random
        within one audience and one period. The only design where the difference
        between arms is attributable to the arms.
    """

    SINGLE_DELIVERABLE = "single_deliverable"
    OBSERVATIONAL = "observational"
    MATCHED_PAIR = "matched_pair"
    RANDOMIZED_SPLIT = "randomized_split"

    @property
    def controls_assignment(self) -> bool:
        """Was assignment to the arms controlled rather than observed?"""
        return self is ComparisonBasis.RANDOMIZED_SPLIT


class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    OBSERVING = "observing"
    COMPLETE = "complete"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class Variable:
    """One thing that was varied or held, named on a closed-ish axis.

    `dimension` is a tag rather than a `FeatureDimension`, because an experiment
    can legitimately vary something the content genome does not tag - the
    publication hour, the thumbnail, the title treatment. `description` says what
    the change actually was, in the words somebody would use to reproduce it.
    """

    dimension: str
    description: str
    from_value: str = ""
    to_value: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", assert_tag(self.dimension, "variable dimension"))
        object.__setattr__(
            self, "description", assert_prose(self.description, "variable description")
        )
        if self.from_value:
            object.__setattr__(self, "from_value", assert_tag(self.from_value, "from_value"))
        if self.to_value:
            object.__setattr__(self, "to_value", assert_tag(self.to_value, "to_value"))

    def to_dict(self) -> dict[str, Any]:
        return record_to_dict(self)

    @classmethod
    def from_dict(cls, data: Any) -> Variable:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a variable object, got {data!r}")
        try:
            return cls(
                dimension=data["dimension"],
                description=data["description"],
                from_value=data.get("from_value", ""),
                to_value=data.get("to_value", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"variable: missing {exc.args[0]!r}") from None


@dataclass(frozen=True)
class Expectation:
    """What we guessed would happen, before it did.

    A direction is required; a range is optional, because "we expect average
    percentage viewed to improve" is an honest hypothesis and "we expect it to
    improve by 4 to 7 points" is a more falsifiable one. Neither is a
    measurement, and `results.py` is the only module that reads either.
    """

    metric: str
    direction: Direction
    rationale: str
    low: float | None = None
    high: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", assert_tag(self.metric, "expectation metric"))
        if not isinstance(self.direction, Direction):
            raise AnalyticsError(
                f"expectation direction must be a Direction, got {self.direction!r}"
            )
        object.__setattr__(
            self, "rationale", assert_prose(self.rationale, "expectation rationale")
        )
        for name in ("low", "high"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise AnalyticsError(f"expectation {name} must be a number, got {value!r}")
            if value is not None:
                object.__setattr__(self, name, float(value))
        if self.low is not None and self.high is not None and self.high < self.low:
            raise AnalyticsError(
                f"expectation range for {self.metric}: high {self.high} is below low "
                f"{self.low}"
            )
        if self.direction is Direction.UNCHANGED and (
            self.low is not None or self.high is not None
        ):
            if self.low is None or self.high is None:
                raise AnalyticsError(
                    f"expectation for {self.metric}: an 'unchanged' expectation with a "
                    "bound needs both bounds - the band it is expected to stay inside"
                )

    @property
    def has_range(self) -> bool:
        return self.low is not None or self.high is not None

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["direction"] = self.direction.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> Expectation:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an expectation object, got {data!r}")
        try:
            return cls(
                metric=data["metric"],
                direction=Direction(data["direction"]),
                rationale=data["rationale"],
                low=data.get("low"),
                high=data.get("high"),
            )
        except KeyError as exc:
            raise AnalyticsError(f"expectation: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"expectation: {exc}") from None


@dataclass(frozen=True)
class KillCondition:
    """A threshold, supplied by the caller, that stops the experiment.

    `breached_by` is the whole of the logic and it is four lines, because the
    only hard part was deciding not to invent the number. `direction` says which
    side is bad: a retention floor is breached below its threshold, a cost
    ceiling above it.
    """

    condition_id: str
    metric: str
    direction: Direction
    threshold: float
    rationale: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "condition_id", assert_record_id(self.condition_id, "condition_id")
        )
        object.__setattr__(self, "metric", assert_tag(self.metric, "kill condition metric"))
        if self.direction not in (Direction.DOWN, Direction.UP):
            raise AnalyticsError(
                f"kill condition {self.condition_id}: direction must be UP (breached "
                "above the threshold) or DOWN (breached below it); 'unchanged' names "
                "no side to be on the wrong side of"
            )
        if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)):
            raise AnalyticsError(
                f"kill condition {self.condition_id}: threshold must be a number the "
                "caller supplied. This code does not choose thresholds - a number it "
                "invented would be its opinion presented as company policy"
            )
        object.__setattr__(self, "threshold", float(self.threshold))
        object.__setattr__(
            self, "rationale", assert_prose(self.rationale, "kill condition rationale")
        )

    def breached_by(self, value: float) -> bool:
        if self.direction is Direction.DOWN:
            return value < self.threshold
        return value > self.threshold

    def statement(self, value: float) -> str:
        side = "below" if self.direction is Direction.DOWN else "above"
        return (
            f"{self.metric} at {value} is {side} the {self.threshold} "
            f"{side}-threshold set on {self.condition_id}: {self.rationale}"
        )

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["direction"] = self.direction.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> KillCondition:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a kill condition object, got {data!r}")
        try:
            return cls(
                condition_id=data["condition_id"],
                metric=data["metric"],
                direction=Direction(data["direction"]),
                threshold=data["threshold"],
                rationale=data["rationale"],
            )
        except KeyError as exc:
            raise AnalyticsError(f"kill condition: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"kill condition: {exc}") from None


@dataclass(frozen=True)
class ExperimentSpecification:
    """What is being tested, stated before the answer is known."""

    experiment_id: str
    objective: str
    hypothesis: str
    basis: ComparisonBasis
    variant_ids: tuple[str, ...]
    variables_changed: tuple[Variable, ...]
    variables_locked: tuple[Variable, ...]
    primary_metrics: tuple[str, ...]
    observation_window: AgeWindow
    minimum_sample: int
    owner: str
    created_on: dt.date
    control_id: str = ""
    secondary_metrics: tuple[str, ...] = ()
    guardrail_metrics: tuple[str, ...] = ()
    expectations: tuple[Expectation, ...] = ()
    kill_conditions: tuple[KillCondition, ...] = ()
    caveats: tuple[str, ...] = ()
    status: ExperimentStatus = ExperimentStatus.DRAFT
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "experiment_id", assert_record_id(self.experiment_id, "experiment_id")
        )
        object.__setattr__(self, "objective", assert_prose(self.objective, "objective"))
        object.__setattr__(self, "hypothesis", assert_prose(self.hypothesis, "hypothesis"))
        if not isinstance(self.basis, ComparisonBasis):
            raise AnalyticsError(
                f"{self.experiment_id}: basis must be a ComparisonBasis, got "
                f"{self.basis!r}. Known: "
                + ", ".join(sorted(b.value for b in ComparisonBasis))
            )
        object.__setattr__(
            self,
            "variant_ids",
            ref_tuple(self.variant_ids, "variant_ids", validator=_deliverable_id),
        )
        object.__setattr__(self, "variables_changed", _variables(self.variables_changed, "changed"))
        object.__setattr__(self, "variables_locked", _variables(self.variables_locked, "locked"))
        object.__setattr__(
            self, "primary_metrics", tag_tuple(self.primary_metrics, "primary_metrics")
        )
        object.__setattr__(
            self, "secondary_metrics", tag_tuple(self.secondary_metrics, "secondary_metrics")
        )
        object.__setattr__(
            self, "guardrail_metrics", tag_tuple(self.guardrail_metrics, "guardrail_metrics")
        )
        if not isinstance(self.observation_window, AgeWindow):
            raise AnalyticsError(
                f"{self.experiment_id}: observation_window must be an AgeWindow - the "
                "age at which every arm is read, so that two videos published a month "
                "apart are compared at the same point in their lives"
            )
        if isinstance(self.minimum_sample, bool) or not isinstance(self.minimum_sample, int):
            raise AnalyticsError(
                f"{self.experiment_id}: minimum_sample must be an integer the caller "
                "supplied - the evidence condition below which the result is "
                "insufficient rather than negative"
            )
        if self.minimum_sample < 1:
            raise AnalyticsError(
                f"{self.experiment_id}: minimum_sample must be at least 1; an "
                "experiment that can conclude from no observations concludes from "
                "nothing"
            )
        object.__setattr__(self, "owner", assert_prose(self.owner, "owner"))
        object.__setattr__(self, "created_on", assert_day(self.created_on, "created_on"))
        if self.control_id:
            object.__setattr__(self, "control_id", _deliverable_id(self.control_id, "control_id"))
        object.__setattr__(self, "expectations", _expectations(self.expectations))
        object.__setattr__(self, "kill_conditions", _kill_conditions(self.kill_conditions))
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "caveats"))
        if not isinstance(self.status, ExperimentStatus):
            raise AnalyticsError(
                f"{self.experiment_id}: status must be an ExperimentStatus, got "
                f"{self.status!r}"
            )
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

        if not self.variables_changed:
            raise AnalyticsError(
                f"{self.experiment_id}: an experiment must name at least one variable "
                "it changed. An experiment that changed nothing is an observation of "
                "the status quo, and belongs in a baseline rather than here"
            )
        if not self.primary_metrics:
            raise AnalyticsError(
                f"{self.experiment_id}: an experiment must name at least one primary "
                "metric, chosen before the result - otherwise whichever metric moved "
                "becomes the one it was about"
            )
        overlap = {v.dimension for v in self.variables_changed} & {
            v.dimension for v in self.variables_locked
        }
        if overlap:
            raise AnalyticsError(
                f"{self.experiment_id}: "
                + ", ".join(sorted(overlap))
                + " is listed as both changed and locked. One of the two is wrong, and "
                "which one decides whether this experiment is confounded"
            )
        for group, label in (
            (self.secondary_metrics, "secondary"),
            (self.guardrail_metrics, "guardrail"),
        ):
            clash = set(group) & set(self.primary_metrics)
            if clash:
                raise AnalyticsError(
                    f"{self.experiment_id}: "
                    + ", ".join(sorted(clash))
                    + f" is both a primary and a {label} metric; a metric that is "
                    "both is a primary metric with a second chance to look good"
                )
        if self.basis is ComparisonBasis.SINGLE_DELIVERABLE and len(self.variant_ids) > 1:
            raise AnalyticsError(
                f"{self.experiment_id}: a single-deliverable basis names one variant, "
                f"got {len(self.variant_ids)}. Two deliverables compared is an "
                "observational comparison at least"
            )
        if self.basis is not ComparisonBasis.SINGLE_DELIVERABLE and not self.variant_ids:
            raise AnalyticsError(
                f"{self.experiment_id}: a {self.basis.value} experiment must name the "
                "deliverables it compares"
            )
        if self.control_id and self.control_id in self.variant_ids:
            raise AnalyticsError(
                f"{self.experiment_id}: {self.control_id!r} is named as both the "
                "control and a variant; a deliverable compared with itself has no "
                "difference to report"
            )
        if self.basis is ComparisonBasis.MATCHED_PAIR and not self.control_id:
            raise AnalyticsError(
                f"{self.experiment_id}: a matched pair needs a control_id. The pairing "
                "is the whole of what makes it better evidence than an observational "
                "comparison"
            )
        unknown = {e.metric for e in self.expectations} - set(
            self.primary_metrics + self.secondary_metrics + self.guardrail_metrics
        )
        if unknown:
            raise AnalyticsError(
                f"{self.experiment_id}: expectation(s) about "
                + ", ".join(sorted(unknown))
                + ", which the experiment does not measure. Add the metric or drop the "
                "expectation; a prediction about something unmeasured cannot be wrong"
            )

    # -- what the design does and does not support -------------------------

    @property
    def confounded(self) -> bool:
        """Derived from the count of changed variables. Never set by a caller."""
        return len(self.variables_changed) > 1

    @property
    def confounding_reasons(self) -> tuple[str, ...]:
        """Why causal attribution between the changed variables is unavailable."""
        if not self.confounded:
            return ()
        names = ", ".join(sorted(v.dimension for v in self.variables_changed))
        return (
            f"{len(self.variables_changed)} variables changed together ({names}); a "
            "difference in the result cannot be attributed to any one of them",
        )

    @property
    def primary_change(self) -> Variable | None:
        """The single changed variable, or None when more than one moved."""
        return self.variables_changed[0] if len(self.variables_changed) == 1 else None

    @property
    def all_metrics(self) -> tuple[str, ...]:
        seen = dict.fromkeys(
            self.primary_metrics + self.secondary_metrics + self.guardrail_metrics
        )
        return tuple(seen)

    @property
    def arms(self) -> tuple[str, ...]:
        """Control first when there is one, then the variants, in given order."""
        return ((self.control_id,) if self.control_id else ()) + self.variant_ids

    def expectation_for(self, metric: str) -> Expectation | None:
        for expectation in self.expectations:
            if expectation.metric == metric:
                return expectation
        return None

    def assert_metrics_defined(self, registry: MetricRegistry | None = None) -> None:
        """Every named metric resolves to a definition. Optional, and explicit.

        Not run at construction: a specification may legitimately be written
        before a bespoke metric is registered. A caller that wants the check runs
        it, and gets the registry's message naming what is known.
        """
        known = registry or DEFAULT_REGISTRY
        for name in self.all_metrics:
            known.get(name)

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["basis"] = self.basis.value
        data["status"] = self.status.value
        data["confounded"] = self.confounded
        data["confounding_reasons"] = list(self.confounding_reasons)
        return data

    @classmethod
    def from_dict(cls, data: Any) -> ExperimentSpecification:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an experiment object, got {data!r}")
        try:
            return cls(
                experiment_id=data["experiment_id"],
                objective=data["objective"],
                hypothesis=data["hypothesis"],
                basis=ComparisonBasis(data["basis"]),
                variant_ids=tuple(data.get("variant_ids") or ()),
                variables_changed=tuple(
                    Variable.from_dict(v) for v in data.get("variables_changed") or ()
                ),
                variables_locked=tuple(
                    Variable.from_dict(v) for v in data.get("variables_locked") or ()
                ),
                primary_metrics=tuple(data.get("primary_metrics") or ()),
                observation_window=AgeWindow.from_dict(data["observation_window"]),
                minimum_sample=data["minimum_sample"],
                owner=data["owner"],
                created_on=data["created_on"],
                control_id=data.get("control_id", ""),
                secondary_metrics=tuple(data.get("secondary_metrics") or ()),
                guardrail_metrics=tuple(data.get("guardrail_metrics") or ()),
                expectations=tuple(
                    Expectation.from_dict(e) for e in data.get("expectations") or ()
                ),
                kill_conditions=tuple(
                    KillCondition.from_dict(k) for k in data.get("kill_conditions") or ()
                ),
                caveats=tuple(data.get("caveats") or ()),
                status=ExperimentStatus(data.get("status", "draft")),
                evidence=evidence_tuple(data.get("evidence")),
            )
        except KeyError as exc:
            raise AnalyticsError(f"experiment: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"experiment: {exc}") from None


def _deliverable_id(value: Any, field_name: str) -> str:
    from .common import assert_deliverable_id

    return assert_deliverable_id(value, field_name)


def _variables(value: Any, label: str) -> tuple[Variable, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Variable)):
        raise AnalyticsError(f"variables_{label} must be a sequence of Variable records")
    out: list[Variable] = []
    seen: set[str] = set()
    for item in value:
        variable = item if isinstance(item, Variable) else Variable.from_dict(item)
        if variable.dimension in seen:
            raise AnalyticsError(
                f"variables_{label}: {variable.dimension!r} is listed twice; one "
                "dimension is one entry, or the count of what changed is wrong"
            )
        seen.add(variable.dimension)
        out.append(variable)
    return tuple(out)


def _expectations(value: Any) -> tuple[Expectation, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, Expectation)):
        raise AnalyticsError("expectations must be a sequence of Expectation records")
    out: list[Expectation] = []
    seen: set[str] = set()
    for item in value:
        expectation = item if isinstance(item, Expectation) else Expectation.from_dict(item)
        if expectation.metric in seen:
            raise AnalyticsError(
                f"two expectations for {expectation.metric!r}; a metric expected to "
                "move two ways cannot be wrong"
            )
        seen.add(expectation.metric)
        out.append(expectation)
    return tuple(out)


def _kill_conditions(value: Any) -> tuple[KillCondition, ...]:
    if not value:
        return ()
    if isinstance(value, (str, bytes, KillCondition)):
        raise AnalyticsError("kill_conditions must be a sequence of KillCondition records")
    out: list[KillCondition] = []
    seen: set[str] = set()
    for item in value:
        condition = item if isinstance(item, KillCondition) else KillCondition.from_dict(item)
        if condition.condition_id in seen:
            raise AnalyticsError(f"duplicate kill condition id {condition.condition_id!r}")
        seen.add(condition.condition_id)
        out.append(condition)
    return tuple(out)
