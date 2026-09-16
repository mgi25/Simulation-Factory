"""Two deliverables, metric by metric, with every reason a pair does not compare.

## What a comparison is allowed to produce

A difference per metric, the metrics that exist on only one side, and the pairs
that share a name but cannot honestly be subtracted. That is all. There is no
`winner`, no aggregate, and no ordering of the two deliverables, for the reason
section 16 gives and constitution rule 3 repeats: a single number over several
dimensions gets optimised instead of the thing it stands for.

If a caller wants to know which video did better on average percentage viewed,
the answer is in `differences["average_percentage_viewed"]`. If they want to
know which video is *better*, this layer does not have that and says so.

## The three ways a pair fails to compare, all of them visible

1. **Different observation windows.** Video A read at 24 hours against video B
   read at 30 days is not a difference, it is two different measurements. The
   pair lands in `not_comparable` with the window mismatch.
2. **A rate with an unknown denominator.** 8% of 200 impressions and 8% of two
   million are the same number and different evidence, so a rate pair missing
   either denominator is not comparable (section 24). Supplying the impressions
   fixes it; nothing else does.
3. **Incompatible scope.** A complete reading against a partial one describes
   two populations. The pair still compares, because sometimes partial data is
   all there is, but the caveat rides along on the difference itself.

The first two are refusals, the third a caveat, and the split is deliberate:
1 and 2 make the subtraction meaningless, 3 makes it uncertain.

## Unmatched metrics stay visible

`only_in_a` and `only_in_b` are part of the result rather than filtered out.
A comparison over the four metrics both videos happen to have, when one of them
was measured on nine, is a comparison that has quietly chosen its evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .common import assert_prose
from .errors import AnalyticsError
from .experiments import Direction
from .metrics import MetricDefinition, MetricKind
from .observations import MetricObservation
from .windows import AgeWindow


@dataclass(frozen=True)
class MetricComparison:
    """One metric on both sides, or the reason it is not one metric on both sides."""

    metric: MetricDefinition
    window: AgeWindow
    value_a: float
    value_b: float
    comparable: bool
    reasons: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricDefinition):
            raise AnalyticsError("comparison metric must be a MetricDefinition")
        if not isinstance(self.window, AgeWindow):
            raise AnalyticsError("comparison window must be an AgeWindow")
        if not isinstance(self.comparable, bool):
            raise AnalyticsError("comparable must be a bool")
        if not self.comparable and not self.reasons:
            raise AnalyticsError(
                f"{self.metric.name}: an incomparable pair must say why, or the "
                "difference simply disappears from the report without explanation"
            )

    @property
    def difference(self) -> float | None:
        """B minus A, or None when the pair does not compare.

        None rather than a number with a warning attached, because a number is
        what gets copied into a summary and the warning is what gets left behind.
        """
        return self.value_b - self.value_a if self.comparable else None

    @property
    def relative_change(self) -> float | None:
        """Difference as a share of A, or None when A is zero or the pair fails."""
        if not self.comparable or self.value_a == 0:
            return None
        return (self.value_b - self.value_a) / abs(self.value_a)

    @property
    def direction(self) -> Direction | None:
        difference = self.difference
        if difference is None:
            return None
        if difference > 0:
            return Direction.UP
        if difference < 0:
            return Direction.DOWN
        return Direction.UNCHANGED

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.name,
            "window": self.window.to_dict(),
            "value_a": self.value_a,
            "value_b": self.value_b,
            "comparable": self.comparable,
            "difference": self.difference,
            "relative_change": self.relative_change,
            "direction": self.direction.value if self.direction else None,
            "reasons": list(self.reasons),
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class DeliverableComparison:
    """Every metric measured on both sides, and everything that did not line up."""

    deliverable_a: str
    deliverable_b: str
    window: AgeWindow
    comparisons: tuple[MetricComparison, ...]
    only_in_a: tuple[str, ...]
    only_in_b: tuple[str, ...]
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.deliverable_a == self.deliverable_b:
            raise AnalyticsError(
                f"{self.deliverable_a!r} compared with itself has no difference to report"
            )
        object.__setattr__(
            self,
            "comparisons",
            tuple(sorted(self.comparisons, key=lambda c: c.metric.name)),
        )
        object.__setattr__(self, "only_in_a", tuple(sorted(self.only_in_a)))
        object.__setattr__(self, "only_in_b", tuple(sorted(self.only_in_b)))

    @property
    def compared(self) -> tuple[MetricComparison, ...]:
        return tuple(c for c in self.comparisons if c.comparable)

    @property
    def not_comparable(self) -> tuple[MetricComparison, ...]:
        return tuple(c for c in self.comparisons if not c.comparable)

    @property
    def unmatched_metrics(self) -> tuple[str, ...]:
        return tuple(sorted(set(self.only_in_a) | set(self.only_in_b)))

    def get(self, metric_name: str) -> MetricComparison | None:
        for comparison in self.comparisons:
            if comparison.metric.name == metric_name:
                return comparison
        return None

    def differences(self) -> dict[str, float]:
        """Metric name to difference, for the pairs that actually compared."""
        return {c.metric.name: c.difference for c in self.compared if c.difference is not None}

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_a": self.deliverable_a,
            "deliverable_b": self.deliverable_b,
            "window": self.window.to_dict(),
            "comparisons": [c.to_dict() for c in self.comparisons],
            "compared_count": len(self.compared),
            "not_comparable_count": len(self.not_comparable),
            "only_in_a": list(self.only_in_a),
            "only_in_b": list(self.only_in_b),
            "caveats": list(self.caveats),
        }


def compare_deliverables(
    deliverable_a: str,
    deliverable_b: str,
    observations: Iterable[MetricObservation],
    window: AgeWindow,
    *,
    caveats: Iterable[str] = (),
) -> DeliverableComparison:
    """Compare two deliverables at one age, deterministically.

    Readings outside `window` are not consulted at all, rather than being used
    as a fallback: answering a question about the first 24 hours with a 30-day
    reading is the failure this function exists to prevent.
    """
    if deliverable_a == deliverable_b:
        raise AnalyticsError(
            f"{deliverable_a!r} compared with itself has no difference to report"
        )
    if not isinstance(window, AgeWindow):
        raise AnalyticsError(
            "compare_deliverables needs an AgeWindow - the age at which both sides "
            "are read, so that two videos published a month apart are compared at the "
            "same point in their lives"
        )

    side_a = _latest_in_window(deliverable_a, observations, window)
    side_b = _latest_in_window(deliverable_b, observations, window)
    shared = sorted(set(side_a) & set(side_b))

    comparisons = tuple(_compare_one(side_a[name], side_b[name], window) for name in shared)
    return DeliverableComparison(
        deliverable_a=deliverable_a,
        deliverable_b=deliverable_b,
        window=window,
        comparisons=comparisons,
        only_in_a=tuple(sorted(set(side_a) - set(side_b))),
        only_in_b=tuple(sorted(set(side_b) - set(side_a))),
        caveats=tuple(assert_prose(c, "comparison caveat") for c in caveats),
    )


def _compare_one(
    left: MetricObservation, right: MetricObservation, window: AgeWindow
) -> MetricComparison:
    reasons: list[str] = []
    caveats: list[str] = []

    if left.metric != right.metric:
        reasons.append(
            f"{left.metric.name} is defined differently on the two sides: "
            f"{left.metric.definition!r} against {right.metric.definition!r}. Two "
            "readings of two definitions share only a name"
        )

    # Both readings are already inside `window`, but they may sit at different
    # ages within it, and for an open-ended window that gap can be months.
    if left.age_hours is not None and right.age_hours is not None:
        gap = abs(left.age_hours - right.age_hours)
        span = None if window.is_open_ended else window.max_age_hours - window.min_age_hours
        if span is not None and gap > span / 2:
            caveats.append(
                f"readings sit {gap:.1f}h apart inside {window}; the difference "
                "includes whatever accumulated between them"
            )
        elif span is None and gap > 0:
            caveats.append(
                f"readings sit {gap:.1f}h apart inside an open-ended window; a "
                "lifetime count keeps growing, so the older reading has had longer"
            )
    else:
        reasons.append(
            "at least one reading has no age since publication, so the two cannot be "
            "placed at the same point in their deliverables' lives"
        )

    if left.metric.kind is MetricKind.RATE:
        missing = [
            name
            for name, side in (("a", left), ("b", right))
            if side.denominator_value is None
        ]
        if missing:
            reasons.append(
                f"{left.metric.name} is a rate over {left.metric.denominator} and "
                f"side {' and '.join(missing)} did not record it. The same percentage "
                "over two populations of unknown size is not a difference - supply "
                f"{left.metric.denominator} on both sides to compare them"
            )

    if left.breakdown != right.breakdown:
        reasons.append(
            f"{left.metric.name} was read over different slices: "
            f"{dict(left.breakdown) or 'the whole audience'} against "
            f"{dict(right.breakdown) or 'the whole audience'}"
        )

    for label, side in (("a", left), ("b", right)):
        for caveat in side.scope.caveats:
            caveats.append(f"side {label}: {caveat}")

    return MetricComparison(
        metric=left.metric,
        window=window,
        value_a=left.value,
        value_b=right.value,
        comparable=not reasons,
        reasons=tuple(reasons),
        caveats=tuple(caveats),
    )


def _latest_in_window(
    deliverable_id: str, observations: Iterable[MetricObservation], window: AgeWindow
) -> dict[str, MetricObservation]:
    """The last reading of each metric inside the window, keyed by metric name.

    Sorting by `(observed_at, observation_id)` before the fold makes the choice
    deterministic when two readings share an instant.
    """
    selected = sorted(
        (
            o
            for o in observations
            if o.deliverable_id == deliverable_id and o.in_window(window)
        ),
        key=lambda o: (o.observed_at, o.observation_id),
    )
    out: dict[str, MetricObservation] = {}
    for observation in selected:
        out[observation.metric.name] = observation
    return out
