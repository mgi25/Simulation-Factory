"""What "normal" is for a named population, and the rule any exclusion followed.

## A baseline names its members or it is a memory

Section 17 is the whole design brief for this module: *do not compare one video
against a vaguely remembered normal*. So a `FormatBaseline` carries the ids of
every deliverable in it, the date range they were published in, and the age
window their readings were taken at. A caller can reconstruct exactly which
numbers produced the median, which is what separates a baseline from a feeling
about how things usually go.

The population definition is required input, not a derived label.
`build_baseline` takes the members; it does not go looking for "the last ten
Shorts", because "last" depends on a cutoff date and a format filter that the
caller has to state anyway.

## Statistics that refuse rather than guess

`MetricSummary` reports count, mean, median, minimum and maximum - and the
number of members that had no reading at all. Three things it will not do:

- **It will not aggregate money.** Section 20 keeps monetary arithmetic in
  `company/finance`; a mean revenue computed here would be a second answer that
  disagrees with finance's in whatever way currency and allocation differ.
- **It will not pool rates with unknown denominators.** A mean of four
  percentages is only the population rate if all four were over equal
  denominators, and when the denominators are missing nobody can know. The
  summary reports the unweighted mean *and* says it is unweighted, or refuses if
  no denominators are present at all.
- **It will not silently drop a member.** A deliverable with no reading is
  counted in `missing_members`, so a median over six of ten members reads as a
  median over six of ten.

## Outliers are surfaced, and removing one costs a written rule

Section 18. `MetricSummary` always reports the outliers it found by the stated
detection rule, and always computes over the full set. A caller who wants them
gone passes an `OutlierRule`, which is a record carrying a method, a threshold
and a rationale - so the exclusion appears in the serialised summary and a later
reader can see both that it happened and why. There is no boolean that drops
points without leaving a trace.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from .common import (
    assert_prose,
    assert_record_id,
    assert_tag,
    record_to_dict,
    text_tuple,
)
from .errors import AnalyticsError
from .metrics import MetricDefinition, MetricKind
from .observations import MetricObservation
from .windows import AgeWindow, DateRange


class OutlierMethod(Enum):
    """How an outlier was identified. Named, because the method changes the answer."""

    IQR = "iqr"
    STANDARD_DEVIATION = "standard_deviation"
    EXPLICIT_IDS = "explicit_ids"


@dataclass(frozen=True)
class OutlierRule:
    """An exclusion, written down before it is applied.

    There is no way to exclude a point without one of these, and it requires a
    rationale, because "we dropped the one that did well" and "we dropped the
    one where the export double-counted a re-upload" are the same operation and
    very different claims.
    """

    method: OutlierMethod
    rationale: str
    threshold: float | None = None
    excluded_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.method, OutlierMethod):
            raise AnalyticsError(
                f"outlier method must be an OutlierMethod, got {self.method!r}"
            )
        object.__setattr__(
            self, "rationale", assert_prose(self.rationale, "outlier rationale")
        )
        if self.method is OutlierMethod.EXPLICIT_IDS:
            object.__setattr__(
                self,
                "excluded_ids",
                tuple(assert_record_id(i, "excluded id") for i in self.excluded_ids),
            )
            if not self.excluded_ids:
                raise AnalyticsError(
                    "an explicit-ids outlier rule must name the ids it excludes"
                )
            if self.threshold is not None:
                raise AnalyticsError(
                    "an explicit-ids outlier rule takes no threshold; it names its "
                    "exclusions directly"
                )
        else:
            if self.threshold is None:
                raise AnalyticsError(
                    f"a {self.method.value} outlier rule needs a threshold the caller "
                    "supplied - this code does not choose one, because the choice "
                    "decides which points survive"
                )
            if isinstance(self.threshold, bool) or not isinstance(self.threshold, (int, float)):
                raise AnalyticsError("outlier threshold must be a number")
            object.__setattr__(self, "threshold", float(self.threshold))
            if self.threshold <= 0:
                raise AnalyticsError("outlier threshold must be positive")
            if self.excluded_ids:
                raise AnalyticsError(
                    f"a {self.method.value} rule computes its exclusions; naming ids as "
                    "well would let the two disagree"
                )

    def statement(self) -> str:
        if self.method is OutlierMethod.EXPLICIT_IDS:
            return (
                f"excluded by id ({', '.join(self.excluded_ids)}): {self.rationale}"
            )
        return f"excluded by {self.method.value} beyond {self.threshold}: {self.rationale}"

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["method"] = self.method.value
        data["statement"] = self.statement()
        return data

    @classmethod
    def from_dict(cls, data: Any) -> OutlierRule:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an outlier rule object, got {data!r}")
        try:
            return cls(
                method=OutlierMethod(data["method"]),
                rationale=data["rationale"],
                threshold=data.get("threshold"),
                excluded_ids=tuple(data.get("excluded_ids") or ()),
            )
        except KeyError as exc:
            raise AnalyticsError(f"outlier rule: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"outlier rule: {exc}") from None


@dataclass(frozen=True)
class MetricSummary:
    """Descriptive statistics over one metric, with everything they exclude."""

    metric: MetricDefinition
    count: int
    mean: float | None
    median: float | None
    minimum: float | None
    maximum: float | None
    missing_members: tuple[str, ...] = ()
    outlier_ids: tuple[str, ...] = ()
    excluded_ids: tuple[str, ...] = ()
    exclusion_rule: OutlierRule | None = None
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.metric, MetricDefinition):
            raise AnalyticsError("summary metric must be a MetricDefinition")
        object.__setattr__(self, "missing_members", tuple(sorted(self.missing_members)))
        object.__setattr__(self, "outlier_ids", tuple(sorted(self.outlier_ids)))
        object.__setattr__(self, "excluded_ids", tuple(sorted(self.excluded_ids)))
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "summary caveats"))
        if self.excluded_ids and self.exclusion_rule is None:
            raise AnalyticsError(
                f"{self.metric.name}: {len(self.excluded_ids)} value(s) were excluded "
                "with no rule recorded. An exclusion without a written rule is a "
                "number nobody can reproduce"
            )

    @property
    def coverage(self) -> str:
        total = self.count + len(self.missing_members)
        return f"{self.count} of {total} member(s) measured"

    def to_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric.name,
            "unit": self.metric.unit,
            "count": self.count,
            "mean": self.mean,
            "median": self.median,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "coverage": self.coverage,
            "missing_members": list(self.missing_members),
            "outlier_ids": list(self.outlier_ids),
            "excluded_ids": list(self.excluded_ids),
            "exclusion_rule": self.exclusion_rule.to_dict() if self.exclusion_rule else None,
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class FormatBaseline:
    """What normal looks like for a population somebody named."""

    baseline_id: str
    population: str
    member_ids: tuple[str, ...]
    published_range: DateRange
    window: AgeWindow
    summaries: tuple[MetricSummary, ...]
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "baseline_id", assert_record_id(self.baseline_id, "baseline_id")
        )
        object.__setattr__(
            self, "population", assert_prose(self.population, "baseline population")
        )
        object.__setattr__(self, "member_ids", tuple(sorted(set(self.member_ids))))
        if not self.member_ids:
            raise AnalyticsError(
                f"{self.baseline_id}: a baseline must name its members. A baseline "
                "whose population is unstated is the remembered normal this record "
                "exists to replace"
            )
        if not isinstance(self.published_range, DateRange):
            raise AnalyticsError(f"{self.baseline_id}: published_range must be a DateRange")
        if not isinstance(self.window, AgeWindow):
            raise AnalyticsError(
                f"{self.baseline_id}: window must be an AgeWindow - members published on "
                "different days are only comparable at the same age"
            )
        object.__setattr__(
            self, "summaries", tuple(sorted(self.summaries, key=lambda s: s.metric.name))
        )
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "baseline caveats"))

    @property
    def size(self) -> int:
        return len(self.member_ids)

    def get(self, metric_name: str) -> MetricSummary | None:
        for summary in self.summaries:
            if summary.metric.name == metric_name:
                return summary
        return None

    @property
    def limitation(self) -> str:
        return (
            f"{self.size} deliverable(s) published {self.published_range}, read at "
            f"{self.window}. Describes that population and no other"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": self.baseline_id,
            "population": self.population,
            "member_ids": list(self.member_ids),
            "size": self.size,
            "published_range": self.published_range.to_dict(),
            "window": self.window.to_dict(),
            "summaries": [s.to_dict() for s in self.summaries],
            "limitation": self.limitation,
            "caveats": list(self.caveats),
        }

    @classmethod
    def from_dict(cls, data: Any, metrics: Mapping[str, MetricDefinition]) -> FormatBaseline:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a baseline object, got {data!r}")
        try:
            summaries = []
            for raw in data.get("summaries") or ():
                definition = metrics.get(raw["metric"])
                if definition is None:
                    raise AnalyticsError(
                        f"baseline {data['baseline_id']}: no definition supplied for "
                        f"metric {raw['metric']!r}"
                    )
                summaries.append(
                    MetricSummary(
                        metric=definition,
                        count=raw["count"],
                        mean=raw.get("mean"),
                        median=raw.get("median"),
                        minimum=raw.get("minimum"),
                        maximum=raw.get("maximum"),
                        missing_members=tuple(raw.get("missing_members") or ()),
                        outlier_ids=tuple(raw.get("outlier_ids") or ()),
                        excluded_ids=tuple(raw.get("excluded_ids") or ()),
                        exclusion_rule=(
                            OutlierRule.from_dict(raw["exclusion_rule"])
                            if raw.get("exclusion_rule")
                            else None
                        ),
                        caveats=tuple(raw.get("caveats") or ()),
                    )
                )
            return cls(
                baseline_id=data["baseline_id"],
                population=data["population"],
                member_ids=tuple(data["member_ids"]),
                published_range=DateRange.from_dict(data["published_range"]),
                window=AgeWindow.from_dict(data["window"]),
                summaries=tuple(summaries),
                caveats=tuple(data.get("caveats") or ()),
            )
        except KeyError as exc:
            raise AnalyticsError(f"baseline: missing {exc.args[0]!r}") from None


def summarise_metric(
    metric: MetricDefinition,
    member_ids: Iterable[str],
    observations: Iterable[MetricObservation],
    window: AgeWindow,
    *,
    outlier_rule: OutlierRule | None = None,
) -> MetricSummary:
    """Descriptive statistics for one metric over a named population.

    Refuses to aggregate money (section 20). Reports the unweighted nature of a
    rate mean rather than pretending to a population rate it cannot compute.
    """
    if metric.kind is MetricKind.MONEY:
        raise AnalyticsError(
            f"{metric.name} is a monetary metric and analytics does not aggregate "
            "money. company/finance owns currency, allocation and what is still "
            "unpaid; a mean computed here would be a second total that disagrees with "
            "the first. Reference the finance records instead"
        )

    members = tuple(sorted(set(member_ids)))
    if not members:
        raise AnalyticsError(
            f"{metric.name}: a summary needs a named population; an unnamed one is the "
            "remembered normal a baseline exists to replace"
        )

    by_member = _latest_per_member(metric, members, observations, window)
    missing = tuple(m for m in members if m not in by_member)
    values = {m: o.value for m, o in by_member.items()}

    caveats: list[str] = []
    if metric.kind is MetricKind.RATE:
        without = sorted(m for m, o in by_member.items() if o.denominator_value is None)
        if without and len(without) == len(by_member):
            caveats.append(
                f"no member recorded {metric.denominator}; this is the unweighted mean "
                "of member rates, which is not the rate over the population and cannot "
                "be compared with one"
            )
        elif without:
            caveats.append(
                f"{len(without)} of {len(by_member)} member(s) recorded no "
                f"{metric.denominator} ({', '.join(without)}); the mean is unweighted"
            )
        else:
            caveats.append(
                "mean is the unweighted mean of member rates; weight by "
                f"{metric.denominator} for the population rate"
            )
    for member, observation in sorted(by_member.items()):
        for caveat in observation.scope.caveats:
            caveats.append(f"{member}: {caveat}")

    outliers = _detect_outliers(values, outlier_rule)
    excluded = outliers if outlier_rule is not None else ()
    kept = {m: v for m, v in values.items() if m not in set(excluded)}

    if outlier_rule is not None:
        caveats.append(outlier_rule.statement())

    numbers = sorted(kept.values())
    return MetricSummary(
        metric=metric,
        count=len(numbers),
        mean=statistics.fmean(numbers) if numbers else None,
        median=statistics.median(numbers) if numbers else None,
        minimum=min(numbers) if numbers else None,
        maximum=max(numbers) if numbers else None,
        missing_members=missing,
        outlier_ids=outliers,
        excluded_ids=excluded,
        exclusion_rule=outlier_rule,
        caveats=tuple(dict.fromkeys(caveats)),
    )


def build_baseline(
    baseline_id: str,
    population: str,
    member_ids: Iterable[str],
    published_range: DateRange,
    window: AgeWindow,
    metrics: Iterable[MetricDefinition],
    observations: Iterable[MetricObservation],
    *,
    outlier_rules: Mapping[str, OutlierRule] | None = None,
    caveats: Iterable[str] = (),
) -> FormatBaseline:
    """A baseline over an explicitly named population. Deterministic."""
    members = tuple(sorted(set(member_ids)))
    readings = tuple(observations)
    rules = outlier_rules or {}
    summaries = tuple(
        summarise_metric(
            metric, members, readings, window, outlier_rule=rules.get(metric.name)
        )
        for metric in sorted(metrics, key=lambda m: m.name)
        if metric.kind is not MetricKind.MONEY
    )
    return FormatBaseline(
        baseline_id=baseline_id,
        population=population,
        member_ids=members,
        published_range=published_range,
        window=window,
        summaries=summaries,
        caveats=tuple(caveats),
    )


def _latest_per_member(
    metric: MetricDefinition,
    members: tuple[str, ...],
    observations: Iterable[MetricObservation],
    window: AgeWindow,
) -> dict[str, MetricObservation]:
    wanted = set(members)
    selected = sorted(
        (
            o
            for o in observations
            if o.deliverable_id in wanted
            and o.metric.name == metric.name
            and not o.breakdown
            and o.in_window(window)
        ),
        key=lambda o: (o.observed_at, o.observation_id),
    )
    out: dict[str, MetricObservation] = {}
    for observation in selected:
        out[observation.deliverable_id] = observation
    return out


def _detect_outliers(
    values: Mapping[str, float], rule: OutlierRule | None
) -> tuple[str, ...]:
    """Outliers by the stated rule, or by the default IQR fence for reporting.

    With no rule, a 1.5x IQR fence is used *only to report* which members are
    unusual - nothing is dropped. The fence is the conventional one and it is
    named in the summary, so a reader knows which definition produced the list.
    """
    if not values:
        return ()
    if rule is not None and rule.method is OutlierMethod.EXPLICIT_IDS:
        return tuple(sorted(set(rule.excluded_ids) & set(values)))

    numbers = sorted(values.values())
    if len(numbers) < 4:
        return ()

    if rule is not None and rule.method is OutlierMethod.STANDARD_DEVIATION:
        mean = statistics.fmean(numbers)
        deviation = statistics.pstdev(numbers)
        if deviation == 0:
            return ()
        limit = rule.threshold or 0.0
        return tuple(
            sorted(m for m, v in values.items() if abs(v - mean) > limit * deviation)
        )

    quartiles = statistics.quantiles(numbers, n=4, method="inclusive")
    spread = quartiles[2] - quartiles[0]
    if spread == 0:
        return ()
    factor = rule.threshold if rule is not None and rule.threshold else 1.5
    low = quartiles[0] - factor * spread
    high = quartiles[2] + factor * spread
    return tuple(sorted(m for m, v in values.items() if v < low or v > high))
