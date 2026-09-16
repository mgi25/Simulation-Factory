"""Descriptive analytics grouped by a tag somebody recorded. Association only.

## What this is for and what it keeps saying no to

Section 13 wants to know how deliverables sharing a format, a version, a camera
system or a theme actually performed. That is a useful question and a short
computation: group by the tag, summarise each group, report what is missing.

Every difficulty is in what must not come out of it. Three things, and all three
are the same mistake at different volumes:

- **No ranking.** `GroupedPerformance` has no `best`, no `worst`, no sort by
  value. Groups come back in tag order, always, because any other order is an
  opinion about which end is good.
- **No score.** No group gets a number combining its metrics. A format with
  strong retention and weak click-through is a format with strong retention and
  weak click-through; the composite that would let those cancel is exactly the
  thing constitution rule 3 forbids.
- **No causation.** `association_note` is attached to every grouping and says
  so. Videos with a cold-open hook did better *and* were mostly published in the
  same fortnight, mostly on the newer track, mostly at the shorter length -
  because that is how we actually work. Grouping cannot separate those.

## Groups too small to describe

`minimum_group_size` defaults to 3 and small groups are reported rather than
dropped: they appear with their statistics and a caveat naming the size. A group
of one is a deliverable, and a median over it is that deliverable's value wearing
the word median - so the caveat says so in those terms.

## Only explicit tags, and only where they were supplied

A deliverable with no tag on the grouping dimension goes to `untagged`, never to
a default bucket and never to an inferred one. `untagged` is part of the output
because a grouping over the 31 deliverables that happened to be tagged, out of
50, is a grouping that quietly chose its population.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from .baseline import MetricSummary, OutlierRule, summarise_metric
from .common import assert_tag, text_tuple
from .deliverable import AnalyzedDeliverable
from .errors import AnalyticsError
from .genome import FeatureDimension
from .metrics import MetricDefinition, MetricKind
from .observations import MetricObservation
from .windows import AgeWindow

ASSOCIATION_NOTE = (
    "association, not causation: these deliverables share a tag and also share "
    "whatever else was true of the period, the format and the audience they were "
    "made for. Grouping cannot separate the tag from the rest"
)

DEFAULT_MINIMUM_GROUP_SIZE = 3


class GroupBy(Enum):
    """The axes a grouping may use. Each resolves to something explicitly recorded."""

    FORMAT_ID = "format_id"
    VERSION = "version"
    HOOK_TYPE = "hook_type"
    CAMERA_STYLE = "camera_style"
    VISUAL_THEME = "visual_theme"
    RACE_LENGTH = "race_length"
    EVENT_DENSITY_BUCKET = "event_density_bucket"
    AUDIO_STYLE = "audio_style"
    FORMAT_FAMILY = "format_family"
    MECHANIC_FAMILY = "mechanic_family"

    @property
    def dimension(self) -> FeatureDimension | None:
        """The genome dimension this axis reads, or None for a deliverable field."""
        try:
            return FeatureDimension(self.value)
        except ValueError:
            return None


def group_value(deliverable: AnalyzedDeliverable, axis: GroupBy) -> str | None:
    """The tag this deliverable carries on `axis`, or None if it was never tagged.

    The only place a group key is derived, and it reads two things: a declared
    field of the deliverable, or a recorded genome tag. It does not read `title`,
    `notes`, or any production reference - see `genome.py` on why, and the suite
    for the grep that keeps it that way.
    """
    if not isinstance(deliverable, AnalyzedDeliverable):
        raise AnalyticsError(f"expected an AnalyzedDeliverable, got {type(deliverable).__name__}")
    if axis is GroupBy.FORMAT_ID:
        return deliverable.format_id
    if axis is GroupBy.VERSION:
        return deliverable.version or None
    dimension = axis.dimension
    if dimension is None:  # pragma: no cover - every non-field member has one
        raise AnalyticsError(f"grouping axis {axis.value!r} resolves to nothing")
    return deliverable.features.get(dimension)


@dataclass(frozen=True)
class PerformanceGroup:
    """One tag value, its members, and what was measured across them."""

    value: str
    member_ids: tuple[str, ...]
    summaries: tuple[MetricSummary, ...]
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", assert_tag(self.value, "group value"))
        object.__setattr__(self, "member_ids", tuple(sorted(set(self.member_ids))))
        object.__setattr__(
            self, "summaries", tuple(sorted(self.summaries, key=lambda s: s.metric.name))
        )
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "group caveats"))

    @property
    def size(self) -> int:
        return len(self.member_ids)

    def get(self, metric_name: str) -> MetricSummary | None:
        for summary in self.summaries:
            if summary.metric.name == metric_name:
                return summary
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "size": self.size,
            "member_ids": list(self.member_ids),
            "summaries": [s.to_dict() for s in self.summaries],
            "caveats": list(self.caveats),
        }


@dataclass(frozen=True)
class GroupedPerformance:
    """Groups in tag order, the untagged remainder, and the association note."""

    axis: GroupBy
    window: AgeWindow
    groups: tuple[PerformanceGroup, ...]
    untagged: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.axis, GroupBy):
            raise AnalyticsError(f"grouping axis must be a GroupBy, got {self.axis!r}")
        if not isinstance(self.window, AgeWindow):
            raise AnalyticsError(
                "a grouping must state the age window its readings were taken at"
            )
        object.__setattr__(
            self, "groups", tuple(sorted(self.groups, key=lambda g: g.value))
        )
        object.__setattr__(self, "untagged", tuple(sorted(set(self.untagged))))
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "grouping caveats"))

    @property
    def association_note(self) -> str:
        return ASSOCIATION_NOTE

    @property
    def sizes(self) -> dict[str, int]:
        return {group.value: group.size for group in self.groups}

    def get(self, value: str) -> PerformanceGroup | None:
        for group in self.groups:
            if group.value == value:
                return group
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis.value,
            "window": self.window.to_dict(),
            "groups": [g.to_dict() for g in self.groups],
            "untagged": list(self.untagged),
            "untagged_count": len(self.untagged),
            "association_note": self.association_note,
            "caveats": list(self.caveats),
        }


def group_performance(
    axis: GroupBy,
    deliverables: Iterable[AnalyzedDeliverable],
    observations: Iterable[MetricObservation],
    metrics: Iterable[MetricDefinition],
    window: AgeWindow,
    *,
    minimum_group_size: int = DEFAULT_MINIMUM_GROUP_SIZE,
    outlier_rules: Mapping[str, OutlierRule] | None = None,
) -> GroupedPerformance:
    """Group deliverables by an explicitly recorded tag and summarise each group.

    Deterministic: tag order in, tag order out, and no ranking anywhere. Money
    metrics are skipped rather than aggregated, for the reason
    `baseline.summarise_metric` gives.
    """
    if isinstance(minimum_group_size, bool) or not isinstance(minimum_group_size, int):
        raise AnalyticsError("minimum_group_size must be an integer")
    if minimum_group_size < 1:
        raise AnalyticsError("minimum_group_size must be at least 1")

    readings = tuple(observations)
    wanted = tuple(
        sorted((m for m in metrics if m.kind is not MetricKind.MONEY), key=lambda m: m.name)
    )
    rules = outlier_rules or {}

    buckets: dict[str, list[str]] = {}
    untagged: list[str] = []
    for deliverable in deliverables:
        value = group_value(deliverable, axis)
        if value is None:
            untagged.append(deliverable.deliverable_id)
        else:
            buckets.setdefault(value, []).append(deliverable.deliverable_id)

    groups: list[PerformanceGroup] = []
    for value in sorted(buckets):
        members = tuple(sorted(set(buckets[value])))
        caveats: list[str] = []
        if len(members) < minimum_group_size:
            caveats.append(
                f"{len(members)} deliverable(s), below the {minimum_group_size} this "
                "grouping treats as describable. A median over "
                f"{len(members)} is those deliverable(s)' value with the word median "
                "in front of it"
            )
        groups.append(
            PerformanceGroup(
                value=value,
                member_ids=members,
                summaries=tuple(
                    summarise_metric(
                        metric, members, readings, window, outlier_rule=rules.get(metric.name)
                    )
                    for metric in wanted
                ),
                caveats=tuple(caveats),
            )
        )

    caveats = [ASSOCIATION_NOTE]
    if untagged:
        caveats.append(
            f"{len(untagged)} deliverable(s) carry no {axis.value} tag and are in no "
            "group; the groups below describe the tagged population only"
        )
    return GroupedPerformance(
        axis=axis,
        window=window,
        groups=tuple(groups),
        untagged=tuple(untagged),
        caveats=tuple(caveats),
    )
