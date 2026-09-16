"""One dated reading of one metric, immutable, and the series they form.

## The record that everything else rests on

An observation is a value, the metric definition that says what the value means,
the instant it was read, where it was read from, and what population it covers.
Every one of those is required, and none of them can be filled in later: the
dataclass is frozen and the store refuses a second write under the same id with
different bytes.

That is the whole of section 4. A video at one hour and the same video at thirty
days are two `MetricObservation` records with two ids. There is no update path,
no `latest` field to overwrite, and no upsert. The 24-hour view count stays
readable in September, which is what makes a retrospective worth running.

## What `age_hours` is for

An observation carries `observed_at` as an absolute instant, because that is
what was true. It carries `age_hours` because that is what is comparable: video
A's first day and video B's first day are the same measurement taken on two
different calendar dates.

`age_hours` is supplied by `observe()` from the deliverable's publication time
rather than stored by hand, so the two can never disagree. For an unpublished
prototype it is None - not zero - and `in_window` answers False for every age
window, because a prototype reading is not a reading at an age.

## Rate observations and their denominators

A rate carries `denominator_value` when the caller has it. It is optional
because it genuinely is sometimes unavailable, and refusing the observation
would lose a reading we did take. What is not optional is the consequence:
`comparison.py` marks a rate pair not comparable when either side lacks it, so
an unknown denominator costs the comparison rather than being quietly ignored.

## `ObservationSeries` sorts and refuses to average

The series is a view over observations of one deliverable and one metric. It
sorts by instant, exposes the readings in each age window, and has no `mean()`.
Averaging a view count at 1 hour with the same count at 30 days produces a
number that describes nothing; the series' job is to keep the snapshots apart,
and `baseline.py` is where a statistic over *different deliverables at the same
age* is computed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator, Mapping

from .common import (
    DataScope,
    Provenance,
    assert_deliverable_id,
    assert_instant,
    assert_prose,
    assert_record_id,
    assert_tag,
    record_to_dict,
)
from .deliverable import AnalyzedDeliverable
from .errors import AnalyticsError
from .metrics import DEFAULT_REGISTRY, MetricDefinition, MetricKind, MetricRegistry
from .windows import AgeWindow


@dataclass(frozen=True)
class MetricObservation:
    """One reading. Frozen, dated, sourced, and never edited.

    `breakdown` names the slice the reading covers when the metric is reported
    per surface or per segment - `{"traffic_source": "browse"}`. It is part of
    the identity of the reading: two observations of `traffic_source_share` with
    different breakdowns are two measurements, not a contradiction.
    """

    observation_id: str
    deliverable_id: str
    metric: MetricDefinition
    value: float
    observed_at: dt.datetime
    provenance: Provenance
    scope: DataScope
    age_hours: float | None = None
    denominator_value: float | None = None
    breakdown: tuple[tuple[str, str], ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "observation_id", assert_record_id(self.observation_id, "observation_id")
        )
        object.__setattr__(
            self, "deliverable_id", assert_deliverable_id(self.deliverable_id, "deliverable_id")
        )
        if not isinstance(self.metric, MetricDefinition):
            raise AnalyticsError(
                f"{self.observation_id}: metric must be a MetricDefinition, got "
                f"{type(self.metric).__name__}. A value recorded against a bare name "
                "cannot say what unit it is in"
            )
        object.__setattr__(self, "value", _number(self.value, "value"))
        object.__setattr__(
            self, "observed_at", assert_instant(self.observed_at, "observed_at")
        )
        if not isinstance(self.provenance, Provenance):
            raise AnalyticsError(
                f"{self.observation_id}: provenance must be a Provenance record"
            )
        if not isinstance(self.scope, DataScope):
            raise AnalyticsError(
                f"{self.observation_id}: scope must be a DataScope - a reading with no "
                "stated population cannot be compared with another"
            )
        if self.age_hours is not None:
            object.__setattr__(self, "age_hours", _age(self.age_hours))
        if self.denominator_value is not None:
            object.__setattr__(
                self, "denominator_value", _number(self.denominator_value, "denominator_value")
            )
            if self.denominator_value < 0:
                raise AnalyticsError(
                    f"{self.observation_id}: denominator_value cannot be negative"
                )
        object.__setattr__(self, "breakdown", _breakdown(self.breakdown))
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "note"))

        self.metric.assert_source_can_produce(
            self.provenance.effective_source,
            f"observation {self.observation_id}",
        )
        if self.provenance.is_external_subject and self.metric.private:
            raise AnalyticsError(  # pragma: no cover - the check above fires first
                f"{self.observation_id}: a private metric cannot describe an external "
                "subject"
            )
        if self.denominator_value is not None and self.metric.kind is not MetricKind.RATE:
            raise AnalyticsError(
                f"{self.observation_id}: denominator_value is only meaningful for a "
                f"rate; {self.metric.name!r} is a {self.metric.kind.value}"
            )

    # -- what this reading can and cannot support --------------------------

    @property
    def key(self) -> str:
        """The identity of the measurement, ignoring when it was taken.

        Two observations with the same key at different instants are a time
        series. Two with the same key at the same instant and different values
        are a contradiction, and `integrity.py` reports them as one.
        """
        slice_part = "".join(f"|{k}={v}" for k, v in self.breakdown)
        return f"{self.deliverable_id}:{self.metric.name}{slice_part}"

    @property
    def snapshot_key(self) -> str:
        return f"{self.key}@{self.observed_at.isoformat()}"

    @property
    def has_known_denominator(self) -> bool:
        """Only meaningful for a rate; True for everything else by definition."""
        return self.metric.kind is not MetricKind.RATE or self.denominator_value is not None

    @property
    def caveats(self) -> tuple[str, ...]:
        out = list(self.scope.caveats)
        if self.metric.kind is MetricKind.RATE and self.denominator_value is None:
            out.append(
                f"{self.metric.name} was recorded without its denominator "
                f"({self.metric.denominator}); the rate cannot be weighted or "
                "compared against another rate of the same name"
            )
        if self.age_hours is None:
            out.append(
                "no age since publication; this reading cannot be placed in an "
                "observation window or compared with a reading of another deliverable"
            )
        return tuple(out)

    def in_window(self, window: AgeWindow) -> bool:
        return self.age_hours is not None and window.contains(self.age_hours)

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["breakdown"] = {k: v for k, v in self.breakdown}
        return data

    @classmethod
    def from_dict(
        cls, data: Any, registry: MetricRegistry | None = None
    ) -> MetricObservation:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an observation object, got {data!r}")
        try:
            raw_metric = data["metric"]
            if isinstance(raw_metric, str):
                metric = (registry or DEFAULT_REGISTRY).get(raw_metric)
            else:
                metric = MetricDefinition.from_dict(raw_metric)
            breakdown = data.get("breakdown") or {}
            return cls(
                observation_id=data["observation_id"],
                deliverable_id=data["deliverable_id"],
                metric=metric,
                value=data["value"],
                observed_at=data["observed_at"],
                provenance=Provenance.from_dict(data["provenance"]),
                scope=DataScope.from_dict(data["scope"]),
                age_hours=data.get("age_hours"),
                denominator_value=data.get("denominator_value"),
                breakdown=tuple(sorted(breakdown.items()))
                if isinstance(breakdown, Mapping)
                else tuple(breakdown),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"observation: missing {exc.args[0]!r}") from None


def observe(
    observation_id: str,
    deliverable: AnalyzedDeliverable,
    metric: MetricDefinition | str,
    value: float,
    observed_at: Any,
    provenance: Provenance,
    scope: DataScope,
    *,
    denominator_value: float | None = None,
    breakdown: Mapping[str, str] | None = None,
    note: str = "",
    registry: MetricRegistry | None = None,
) -> MetricObservation:
    """Record one reading against a deliverable, deriving its age.

    The only constructor callers should normally use. It exists so that
    `age_hours` is computed from the deliverable's own publication instant
    rather than supplied alongside it - two fields that must agree, filled in by
    hand, eventually disagree.
    """
    if not isinstance(deliverable, AnalyzedDeliverable):
        raise AnalyticsError(
            f"expected an AnalyzedDeliverable, got {type(deliverable).__name__}"
        )
    definition = (
        metric
        if isinstance(metric, MetricDefinition)
        else (registry or DEFAULT_REGISTRY).get(metric)
    )
    moment = assert_instant(observed_at, "observed_at")
    return MetricObservation(
        observation_id=observation_id,
        deliverable_id=deliverable.deliverable_id,
        metric=definition,
        value=value,
        observed_at=moment,
        provenance=provenance,
        scope=scope,
        age_hours=deliverable.age_hours_at(moment),
        denominator_value=denominator_value,
        breakdown=tuple(sorted((breakdown or {}).items())),
        note=note,
    )


@dataclass(frozen=True)
class ObservationSeries:
    """Every reading of one metric on one deliverable, in the order taken.

    Deliberately has no `mean`, no `latest_value` shortcut that hides the age it
    came from, and no interpolation. Its job is to keep four snapshots as four
    snapshots.
    """

    deliverable_id: str
    metric: MetricDefinition
    observations: tuple[MetricObservation, ...]

    def __post_init__(self) -> None:
        if not self.observations:
            raise AnalyticsError(
                f"an observation series for {self.deliverable_id}:{self.metric.name} "
                "needs at least one reading; an empty series is a metric that was "
                "never measured, which is recorded as missing rather than as a series"
            )
        keys = {(o.deliverable_id, o.metric.name) for o in self.observations}
        if keys != {(self.deliverable_id, self.metric.name)}:
            raise AnalyticsError(
                f"series {self.deliverable_id}:{self.metric.name} was given readings of "
                + ", ".join(sorted(f"{d}:{m}" for d, m in keys))
                + "; a series holds one metric of one deliverable"
            )
        object.__setattr__(
            self,
            "observations",
            tuple(sorted(self.observations, key=lambda o: (o.observed_at, o.observation_id))),
        )

    @classmethod
    def build(
        cls, deliverable_id: str, metric: MetricDefinition, observations: Iterable[MetricObservation]
    ) -> ObservationSeries:
        selected = tuple(
            o
            for o in observations
            if o.deliverable_id == deliverable_id and o.metric.name == metric.name
        )
        return cls(deliverable_id, metric, selected)

    def __len__(self) -> int:
        return len(self.observations)

    def __iter__(self) -> Iterator[MetricObservation]:
        return iter(self.observations)

    @property
    def earliest(self) -> MetricObservation:
        return self.observations[0]

    @property
    def latest(self) -> MetricObservation:
        return self.observations[-1]

    def in_window(self, window: AgeWindow) -> tuple[MetricObservation, ...]:
        return tuple(o for o in self.observations if o.in_window(window))

    def at_window(self, window: AgeWindow) -> MetricObservation | None:
        """The last reading inside `window`, or None if there is none.

        The last rather than the first, because a window is an interval and the
        reading nearest its end is the one that describes the whole of it.
        Returns None rather than falling back to a neighbouring window, which
        would silently answer a question about hour 24 with a reading from hour 2.
        """
        readings = self.in_window(window)
        return readings[-1] if readings else None

    def growth_between(
        self, earlier: AgeWindow, later: AgeWindow
    ) -> tuple[float | None, tuple[str, ...]]:
        """Change in value between two windows, with what is missing.

        Returns `(None, reasons)` when either window has no reading, because a
        gap here is the answer rather than an obstacle to it.
        """
        missing: list[str] = []
        first = self.at_window(earlier)
        second = self.at_window(later)
        if first is None:
            missing.append(f"no {self.metric.name} reading in {earlier}")
        if second is None:
            missing.append(f"no {self.metric.name} reading in {later}")
        if first is None or second is None:
            return None, tuple(missing)
        return second.value - first.value, ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "deliverable_id": self.deliverable_id,
            "metric": self.metric.name,
            "count": len(self.observations),
            "observation_ids": [o.observation_id for o in self.observations],
        }


def _number(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticsError(
            f"{field_name}: expected a number, got {value!r}. A measurement that is "
            "not a number is a description, and belongs in a note"
        )
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        raise AnalyticsError(f"{field_name}: {value!r} is not a finite measurement")
    return number


def _age(value: Any) -> float:
    age = _number(value, "age_hours")
    if age < 0:
        raise AnalyticsError(
            f"age_hours: {age} is negative; a reading cannot be taken before the thing "
            "it measures was published"
        )
    return age


def _breakdown(value: Any) -> tuple[tuple[str, str], ...]:
    if not value:
        return ()
    items = value.items() if isinstance(value, Mapping) else value
    out: list[tuple[str, str]] = []
    for item in items:
        if not isinstance(item, tuple) or len(item) != 2:
            raise AnalyticsError(f"breakdown entry {item!r} must be a (key, value) pair")
        key, slice_value = item
        out.append(
            (assert_tag(key, "breakdown key"), assert_tag(slice_value, "breakdown value"))
        )
    return tuple(sorted(out))
