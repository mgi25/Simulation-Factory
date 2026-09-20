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

## A ceiling is a claim about the metric, and one of ours was wrong

A rate is capped at 1.0 because a share of a population cannot exceed the
population - `retention_at_3s` above 1.0 would mean more views still playing
than there were views. That reasoning is right for every rate here except one,
and `average_percentage_viewed` was carrying the cap anyway, as prose in its
unit string: "fraction of video length, 0.0-1.0".

It is not bounded by 1.0. Its denominator is the length of the video, not a
population, and a viewer who replays or loops a Short accumulates watch time
past the end of it. The first real pull of our own channel returned 118.41% for
a Short, which the fetcher correctly carried through as 1.1841 - a number the
documented contract called impossible. Clamping it to 1.0 would have destroyed
the only interesting thing the reading said, which is that the video is watched
more than once per view.

So the ceiling is now declared rather than described. `unbounded_above` lifts it
for the metrics where the numerator can lap the denominator, `maximum` derives
it, and `MetricObservation` checks a value against it at construction. The
assumption that was wrong is now a field somebody has to change on purpose,
rather than a sentence a later reader could restore by agreeing with it.

The floor stays at zero for everything except money, where a refund or a
downward revision is a real negative amount.

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


# The kinds whose 1.0 means "all of the denominator", and which therefore have a
# full scale a reading could in principle pass. A count or a duration has no such
# point, which is why `unbounded_above` is refused on one.
_FULL_SCALE_KINDS = frozenset({MetricKind.RATE, MetricKind.FRACTION})

# The kinds whose sign carries information. Money is the only one: a refund, a
# chargeback or a downward revision is a real negative amount, and a floor of
# zero here would turn the correction into a refusal.
_SIGNED_KINDS = frozenset({MetricKind.MONEY})


@dataclass(frozen=True)
class MetricDefinition:
    """One metric, defined once, with its unit and its denominator."""

    name: str
    kind: MetricKind
    unit: str
    definition: str
    denominator: str = ""
    private: bool = False
    unbounded_above: bool = False

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
        if not isinstance(self.unbounded_above, bool):
            raise AnalyticsError(
                f"metric {self.name!r}: unbounded_above must be a bool, got "
                f"{self.unbounded_above!r}"
            )
        if self.unbounded_above and self.kind not in _FULL_SCALE_KINDS:
            raise AnalyticsError(
                f"metric {self.name!r}: unbounded_above says a value may pass full "
                f"scale, and a {self.kind.value} has no full scale to pass. Only a "
                "rate or a fraction, whose 1.0 means 'all of the denominator', can "
                "declare it"
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

    @property
    def minimum(self) -> float | None:
        """The floor a reading may not go below, or None where a sign is a fact."""
        return None if self.kind in _SIGNED_KINDS else 0.0

    @property
    def maximum(self) -> float | None:
        """The ceiling a reading may not pass, or None where there is no ceiling.

        A rate or a fraction is capped at 1.0 by default, because its 1.0 is
        "all of the denominator" and a share of a population cannot exceed the
        population. `unbounded_above` lifts that cap for the metrics where the
        numerator can lap the denominator instead - see
        `average_percentage_viewed`, where a viewer who replays a Short
        accumulates watch time past the end of it.
        """
        if self.kind not in _FULL_SCALE_KINDS or self.unbounded_above:
            return None
        return 1.0

    def assert_value_in_range(self, value: float, field_name: str) -> None:
        """Refuse a reading outside what this metric can mean.

        Both messages name the metric rather than the bound alone, because the
        useful question on a failure is which definition is wrong: the reading,
        or the ceiling somebody assumed it had.
        """
        if self.minimum is not None and value < self.minimum:
            raise AnalyticsError(
                f"{field_name}: {value} is below {self.minimum} and {self.name!r} is "
                f"a {self.kind.value} that cannot be negative. A negative here is an "
                "arithmetic slip or a sign convention this record does not declare"
            )
        if self.maximum is not None and value > self.maximum:
            raise AnalyticsError(
                f"{field_name}: {value} is above {self.maximum} and {self.name!r} is "
                f"a share of {self.denominator or 'its population'}, which cannot "
                "exceed it. If this platform reading genuinely can pass full scale - "
                "as average_percentage_viewed does when a view loops - the metric "
                "declares unbounded_above rather than the value being clamped"
            )

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
            "unbounded_above": self.unbounded_above,
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
                unbounded_above=bool(data.get("unbounded_above", False)),
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
    unbounded_above: bool = False,
) -> MetricDefinition:
    return MetricDefinition(
        name, kind, unit, definition, denominator, private, unbounded_above
    )


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
        "fraction of video length; 1.0 is 100% and is not the ceiling",
        "Mean share of the video watched per view, as the platform reports it. "
        "1.0 means the average view lasted exactly one length of the video. "
        "Values above 1.0 are valid and are not a defect: a looping or replayed "
        "view accumulates watch time past the end, so the mean watch duration "
        "can exceed the duration of the video. A Shorts pull returned 118.41%. "
        "Distinct from average_view_duration_seconds divided by video length, "
        "which the platform does not compute the same way.",
        denominator="video_length_seconds",
        unbounded_above=True,
        private=True,
    ),
    _m(
        "watch_time_hours",
        MetricKind.DURATION,
        "hours",
        "Total hours watched over the observation window, in the hours the export "
        "reports rather than converted to seconds. Named for its unit because it "
        "sits beside average_view_duration_seconds, and a total in one unit next "
        "to a mean in another is how a watch time gets divided by sixty.",
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
