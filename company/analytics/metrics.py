"""What a metric name means, in one place, before anybody records a value.

## The problem this solves

"Retention was 41%" is four different claims. Average percentage viewed?
Percentage of viewers still watching at three seconds? At the end? Absolute
audience retention at the midpoint? Each is a real YouTube measurement, each is
a different number, and a layer that stores the word rather than the definition
will eventually compare two of them and report the difference as a result.

So a value cannot be recorded against a bare name. It is recorded against a
`MetricDefinition`, which carries the unit, the kind, and - for a rate - the
denominator the rate is over. `STANDARD_METRICS` is the registry; a caller with
a metric it does not contain registers a definition rather than passing a string.

## Rates carry their denominator, and it is not decoration

A click-through rate of 8% over 200 impressions and one of 8% over 2,000,000
impressions are the same number and not the same evidence. Section 24 asks for
rate comparison with an unknown denominator to be prevented, so a rate
observation may carry `denominator_value`, and `comparison.py` marks a rate pair
*not comparable* when either side is missing it. The honest path - supply the
impressions you already have - is one field; the dishonest path is closed.

## The private line, drawn by the definition rather than by the caller

`private=True` marks a metric that only authenticated access to our own channel
could produce. Nobody can read average view duration off a stranger's video
page, so a value claiming to be one is an inference wearing the clothes of an
observation. `assert_source_can_produce` refuses the combination at
construction, which is why `observations.py` needs no competitor check of its
own: the metric definition already knows.

`intelligence/research/snapshots.py` draws the same line from the other side -
it refuses private metric *names* on a public snapshot. The two checks are
deliberately independent rather than shared: analytics must not import research,
and a boundary guarded from both sides survives one side being rewritten.

## What is not here

No metric is derived from another. `average_percentage_viewed` is not computed
from `average_view_duration_seconds` and a video length, even though it could
be, because the platform computes it differently from how we would and the
recomputed number would silently disagree with the export it sits beside.
Analytics consumes measurements (section 15); arithmetic across metrics happens
only in a comparison, and only between readings of the same metric.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .common import DataSource, assert_prose, assert_tag
from .errors import AnalyticsError, ProvenanceViolation


class MetricKind(Enum):
    """What sort of quantity a value is, which decides what may be done to it.

    `RATE` requires a denominator. `MONEY` may be observed but never summed
    here - section 20 keeps money arithmetic in `company/finance`, and
    `baseline.py` refuses to aggregate a monetary metric rather than producing a
    second, subtly different, revenue total.
    """

    COUNT = "count"
    RATE = "rate"
    DURATION = "duration"
    FRACTION = "fraction"
    MONEY = "money"


@dataclass(frozen=True)
class MetricDefinition:
    """One metric, defined once, with its unit and its denominator."""

    name: str
    kind: MetricKind
    unit: str
    definition: str
    denominator: str = ""
    private: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", assert_tag(self.name, "metric name"))
        if not isinstance(self.kind, MetricKind):
            raise AnalyticsError(
                f"metric {self.name!r}: kind must be a MetricKind, got {self.kind!r}"
            )
        object.__setattr__(self, "unit", assert_prose(self.unit, "metric unit"))
        object.__setattr__(
            self, "definition", assert_prose(self.definition, "metric definition")
        )
        if not isinstance(self.private, bool):
            raise AnalyticsError(
                f"metric {self.name!r}: private must be a bool, got {self.private!r}"
            )
        if self.kind is MetricKind.RATE:
            if not self.denominator:
                raise AnalyticsError(
                    f"metric {self.name!r} is a rate and must name its denominator. "
                    "A rate whose denominator is unstated cannot be compared with "
                    "another rate of the same name, because nothing says they were "
                    "taken over the same thing"
                )
            assert_tag(self.denominator, f"metric {self.name} denominator")
        elif self.denominator:
            raise AnalyticsError(
                f"metric {self.name!r}: a denominator is only meaningful for a rate; "
                f"this metric is a {self.kind.value}"
            )

    @property
    def requires_first_party(self) -> bool:
        return self.private

    def assert_source_can_produce(self, source: DataSource, field_name: str) -> None:
        """Refuse a private metric attributed to a source that cannot see it.

        The message names the honest alternative, because the legitimate case -
        our own authenticated export - is real and is the one the caller
        probably wants.
        """
        if self.private and not source.is_first_party:
            raise ProvenanceViolation(
                f"{field_name}: {self.name!r} is a private channel analytic and "
                f"{source.value!r} cannot produce one. No public page shows it, for "
                "our videos or anybody else's, so a value here came from somewhere "
                "this record does not name. Only an authenticated export or API "
                "reading of our own channel may carry it."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "unit": self.unit,
            "definition": self.definition,
            "denominator": self.denominator,
            "private": self.private,
        }

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "metric") -> MetricDefinition:
        if not isinstance(data, dict):
            raise AnalyticsError(f"{field_name}: expected a metric object, got {data!r}")
        try:
            return cls(
                name=data["name"],
                kind=MetricKind(data["kind"]),
                unit=data["unit"],
                definition=data["definition"],
                denominator=data.get("denominator", ""),
                private=bool(data.get("private", False)),
            )
        except KeyError as exc:
            raise AnalyticsError(f"{field_name}: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"{field_name}: {exc}") from None


def _m(
    name: str,
    kind: MetricKind,
    unit: str,
    definition: str,
    denominator: str = "",
    private: bool = False,
) -> MetricDefinition:
    return MetricDefinition(name, kind, unit, definition, denominator, private)


# -- the registry ----------------------------------------------------------
#
# Platform metrics first, then the production measurements section 15 names.
# Every `definition` says which reading it is, in the words the export uses, so
# that a later reader can check the definition against the column it came from.

_PLATFORM_METRICS: tuple[MetricDefinition, ...] = (
    _m(
        "views",
        MetricKind.COUNT,
        "views",
        "Views counted by the platform over the observation window, as reported "
        "by the channel's own analytics.",
    ),
    _m(
        "impressions",
        MetricKind.COUNT,
        "impressions",
        "Times a thumbnail was shown to a signed-in viewer on a platform surface. "
        "Excludes external and embedded surfaces the platform does not count.",
        private=True,
    ),
    _m(
        "click_through_rate",
        MetricKind.RATE,
        "fraction of impressions, 0.0-1.0",
        "Views that came from a counted impression, divided by counted "
        "impressions. Not all views have an impression behind them, so this is "
        "not views divided by total views.",
        denominator="impressions",
        private=True,
    ),
    _m(
        "average_view_duration_seconds",
        MetricKind.DURATION,
        "seconds",
        "Mean watch time per view over the window: total watch time divided by "
        "views. Not the median, and not per viewer.",
        private=True,
    ),
    _m(
        "average_percentage_viewed",
        MetricKind.RATE,
        "fraction of video length, 0.0-1.0",
        "Mean share of the video watched per view, as the platform reports it. "
        "Distinct from average_view_duration_seconds divided by video length, "
        "which the platform does not compute the same way.",
        denominator="video_length_seconds",
        private=True,
    ),
    _m(
        "retention_at_3s",
        MetricKind.RATE,
        "fraction of views, 0.0-1.0",
        "Share of views still playing at the three-second mark, read off the "
        "absolute audience retention curve. One point on that curve and nothing "
        "else; it is not average_percentage_viewed.",
        denominator="views",
        private=True,
    ),
    _m(
        "retention_at_50pct",
        MetricKind.RATE,
        "fraction of views, 0.0-1.0",
        "Share of views still playing at the midpoint of the video, read off the "
        "absolute audience retention curve.",
        denominator="views",
        private=True,
    ),
    _m(
        "likes",
        MetricKind.COUNT,
        "likes",
        "Likes accumulated over the observation window.",
    ),
    _m(
        "comments",
        MetricKind.COUNT,
        "comments",
        "Comments left over the observation window, before moderation removals.",
    ),
    _m(
        "shares",
        MetricKind.COUNT,
        "shares",
        "Shares counted by the platform's own share action. Excludes links "
        "copied out of the address bar, which nothing can count.",
        private=True,
    ),
    _m(
        "subscribers_gained",
        MetricKind.COUNT,
        "subscribers",
        "Subscriptions the platform attributes to this deliverable over the "
        "window.",
        private=True,
    ),
    _m(
        "subscribers_lost",
        MetricKind.COUNT,
        "subscribers",
        "Unsubscriptions the platform attributes to this deliverable over the "
        "window. Recorded separately from subscribers_gained; a net figure hides "
        "which of the two moved.",
        private=True,
    ),
    _m(
        "estimated_revenue",
        MetricKind.MONEY,
        "reporting currency, minor units as reported",
        "Revenue the platform estimates for this deliverable over the window. "
        "Recorded here only as an observation with a finance reference beside "
        "it; every monetary calculation belongs to company/finance.",
        private=True,
    ),
    _m(
        "traffic_source_share",
        MetricKind.RATE,
        "fraction of views, 0.0-1.0",
        "Share of views from one named traffic surface. The surface is recorded "
        "in the observation's breakdown key, not in the metric name.",
        denominator="views",
        private=True,
    ),
)

_PRODUCTION_METRICS: tuple[MetricDefinition, ...] = (
    _m(
        "events_per_minute",
        MetricKind.RATE,
        "events per minute",
        "Race events per minute of finished cut, as counted by the production "
        "measurement that produced it. Consumed, never recomputed here.",
        denominator="cut_minutes",
        private=True,
    ),
    _m(
        "longest_dead_period_seconds",
        MetricKind.DURATION,
        "seconds",
        "Longest interval of the finished cut containing no counted event, from "
        "the same production measurement.",
        private=True,
    ),
    _m(
        "overtakes",
        MetricKind.COUNT,
        "overtakes",
        "Position changes counted by the production measurement over the whole "
        "race.",
        private=True,
    ),
    _m(
        "lead_changes",
        MetricKind.COUNT,
        "lead changes",
        "Changes of first place counted by the production measurement.",
        private=True,
    ),
    _m(
        "finish_spread_seconds",
        MetricKind.DURATION,
        "seconds",
        "Elapsed time between the first and last finisher, from the production "
        "measurement.",
        private=True,
    ),
    _m(
        "mobile_subject_fraction",
        MetricKind.FRACTION,
        "fraction of frame height, 0.0-1.0",
        "Median on-screen height of the tracked subject as a share of frame "
        "height, from the readability measurement.",
        private=True,
    ),
    _m(
        "camera_cuts",
        MetricKind.COUNT,
        "cuts",
        "Cuts in the finished edit, counted by the edit timeline rather than "
        "detected from frames.",
        private=True,
    ),
    _m(
        "camera_continuity_issues",
        MetricKind.COUNT,
        "issues",
        "Continuity defects the production QC pass flagged. The QC rule set that "
        "produced the count belongs in the observation's evidence.",
        private=True,
    ),
)

STANDARD_METRICS: dict[str, MetricDefinition] = {
    definition.name: definition
    for definition in (*_PLATFORM_METRICS, *_PRODUCTION_METRICS)
}


class MetricRegistry:
    """The definitions a session may record against.

    Starts from `STANDARD_METRICS` and accepts additions. A second definition
    for a name already present is refused unless it is identical, because the
    whole point of the registry is that one name means one thing.
    """

    def __init__(self, definitions: Iterable[MetricDefinition] | None = None) -> None:
        self._by_name: dict[str, MetricDefinition] = dict(STANDARD_METRICS)
        for definition in definitions or ():
            self.register(definition)

    def register(self, definition: MetricDefinition) -> MetricDefinition:
        if not isinstance(definition, MetricDefinition):
            raise AnalyticsError(
                f"expected a MetricDefinition, got {type(definition).__name__}"
            )
        existing = self._by_name.get(definition.name)
        if existing is not None and existing != definition:
            raise AnalyticsError(
                f"metric {definition.name!r} is already defined differently: "
                f"{existing.definition!r} against {definition.definition!r}. One name "
                "means one measurement; register the second reading under its own name"
            )
        self._by_name[definition.name] = definition
        return definition

    def get(self, name: str) -> MetricDefinition:
        try:
            return self._by_name[name]
        except KeyError:
            raise AnalyticsError(
                f"no definition for metric {name!r}. Register a MetricDefinition "
                "before recording a value against it - a bare name cannot say what "
                "unit it is in or what a rate is over. Known: "
                + ", ".join(sorted(self._by_name))
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))

    def private_names(self) -> tuple[str, ...]:
        return tuple(sorted(n for n, d in self._by_name.items() if d.private))


DEFAULT_REGISTRY = MetricRegistry()
