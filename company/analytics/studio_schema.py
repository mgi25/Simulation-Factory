"""Which Studio report a file is, and what each of its columns means.

## Why this is a table and not a parser

A YouTube Studio export is not one format. The videos table, the day-by-day
chart data and the traffic-source breakdown are different reports with different
columns, and each of them changes spelling between product versions and between
locales. The tempting shape is one function with a long chain of `if "views" in
header.lower()` branches, and that function is wrong the first time a column is
renamed: it keeps working, quietly, against a column that now means something
else.

So recognition is a table. A `StudioExportSchema` names the exact headers it
requires, the exact headers that rule it out, and one `ColumnMapping` per column
it understands. `recognise_schema` matches on those exact strings and refuses
when nothing matches or when two schemas do. There is no similarity score, no
lowercasing, no stripping - a header this table does not contain is reported as
unknown, and section 4 of the brief gets its refusal rather than a guess.

Exact matching has a cost, and it is the right cost: an export with a trailing
space in a header fails loudly on the day it arrives, instead of importing a
column nobody checked.

## Why an unmapped column must give a reason

`ColumnMapping.metric` may be empty, and then `unmapped_reason` is required. The
field exists because "we did not map this" and "we deliberately do not map this"
look identical in a diff and are opposite facts. `Subscribers` is the clearest
case: Studio reports a net figure, the registry deliberately keeps
`subscribers_gained` and `subscribers_lost` apart, and mapping the net column to
either one would be a fabrication. The reason field is where that decision
lives, and the ingestion result reports it to the caller rather than dropping
the column silently.

## Why a mapping cannot mix units

`assert_compatible` refuses a percentage column pointed at a count, a clock
duration pointed at a rate, and a decimal pointed at a count. The metric
registry already says what unit a metric is in; this is where a column claims to
supply it, and the two have to agree at construction rather than at the moment
somebody compares two numbers that were never the same quantity.

Money is refused outright: a monetary column carries no metric at all. Finance
owns money (`company/finance`), and an analytics ingester that produced revenue
figures would be a second answer to a question that already has an owner. The
mapping classifies the column, the result reports it as finance-routed, and no
observation is made.

## Snapshot against interval

`TemporalSemantics` is the distinction section 12 asks for: views *through* day
seven and views *during* day seven are two measurements, and averaging them is
nonsense. A per-day schema fixes the semantics to `INTERVAL` because its rows
are bounded by construction. The videos table cannot: the same columns are
emitted for a lifetime total and for a total over a chosen date range, so the
file genuinely does not know, and the source record makes the caller declare it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from .common import assert_prose, assert_tag
from .errors import AnalyticsError, StudioExportRejected
from .metrics import DEFAULT_REGISTRY, MetricKind, MetricRegistry
from .studio_values import ValueFormat

# The longest a raw CSV header may be before this layer treats it as content
# rather than a column name.
MAX_HEADER_CHARS = 200

# What a Studio videos table puts in its identity column for the totals row.
# Compared case-insensitively, because that row is an aggregate whichever way
# the product spells it, and ingesting it as a video would invent a deliverable.
AGGREGATE_ROW_LABELS: tuple[str, ...] = ("total", "totals")


class TemporalSemantics(Enum):
    """Whether a row totals everything so far, or only a bounded window.

    `CUMULATIVE_TO_INSTANT` is a running total read at a moment: lifetime views
    as they stood when the export was taken. `INTERVAL` is a measurement of a
    bounded stretch of calendar time and nothing outside it.
    """

    CUMULATIVE_TO_INSTANT = "cumulative_to_instant"
    INTERVAL = "interval"

    @property
    def measurement_tag(self) -> str:
        """The breakdown value that keeps the two kinds of reading apart.

        Cumulative readings carry no breakdown, because a running total read at
        an age is what every hand-recorded observation in this package already
        is, and giving them a slice would make an imported reading incomparable
        with a typed one. An interval reading carries `measurement=interval`,
        which puts it in a different `MetricObservation.key` - so it is never
        compared against a cumulative reading, never enters a baseline, and
        never collides with one in the contradictory-snapshot check.
        """
        return "" if self is TemporalSemantics.CUMULATIVE_TO_INSTANT else "interval"


def assert_header(value: Any, field_name: str) -> str:
    """A raw CSV header, kept exactly as the export spelled it."""
    if not isinstance(value, str) or not value.strip():
        raise AnalyticsError(f"{field_name}: a column header is required, got {value!r}")
    if "\n" in value or "\r" in value:
        raise AnalyticsError(
            f"{field_name}: a column header is one line; this is {value!r}"
        )
    if len(value) > MAX_HEADER_CHARS:
        raise AnalyticsError(
            f"{field_name}: {len(value)} characters is not a column name, it is "
            "content"
        )
    return value


@dataclass(frozen=True)
class ColumnMapping:
    """One export column, and the canonical metric it supplies - or why it does not.

    `denominator_header` names the column holding the base of a rate. It is how
    a click-through rate arrives with its impressions attached, which is what
    lets `comparison.py` compare it with another one later.
    """

    header: str
    value_format: ValueFormat
    metric: str = ""
    denominator_header: str = ""
    monetary: bool = False
    unmapped_reason: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "header", assert_header(self.header, "column header"))
        if not isinstance(self.value_format, ValueFormat):
            raise AnalyticsError(
                f"column {self.header!r}: value_format must be a ValueFormat, got "
                f"{self.value_format!r}"
            )
        if not isinstance(self.monetary, bool):
            raise AnalyticsError(
                f"column {self.header!r}: monetary must be a bool, got {self.monetary!r}"
            )
        if self.metric:
            object.__setattr__(self, "metric", assert_tag(self.metric, "column metric"))
        if self.denominator_header:
            object.__setattr__(
                self,
                "denominator_header",
                assert_header(self.denominator_header, "denominator header"),
            )
        if self.monetary and self.metric:
            raise AnalyticsError(
                f"column {self.header!r}: a monetary column carries no analytics "
                "metric. Money belongs to company/finance, and an analytics ingester "
                "that produced a revenue figure would be a second answer to a "
                "question that already has an owner"
            )
        if not self.metric and not self.unmapped_reason:
            raise AnalyticsError(
                f"column {self.header!r}: a column with no canonical metric must say "
                "why. 'Not mapped yet' and 'deliberately not mapped' look identical "
                "in a diff and are opposite facts"
            )
        if self.unmapped_reason:
            object.__setattr__(
                self,
                "unmapped_reason",
                assert_prose(self.unmapped_reason, "unmapped_reason"),
            )
        self.assert_compatible()

    @property
    def is_mapped(self) -> bool:
        return bool(self.metric)

    def assert_compatible(self, registry: MetricRegistry | None = None) -> None:
        """Refuse a column whose shape cannot supply the metric it claims.

        Runs at construction against the default registry and is re-runnable
        against another, for the same reason `CompetitorPublicReference` exposes
        its check: a caller with its own registry gets the same refusal.
        """
        if not self.metric:
            if self.denominator_header:
                return
            return
        definition = (registry or DEFAULT_REGISTRY).get(self.metric)
        if definition.kind is MetricKind.MONEY:
            raise AnalyticsError(
                f"column {self.header!r}: {self.metric!r} is a monetary metric, and "
                "this ingester records no money at all. Finance owns it; mark the "
                "column monetary instead, and it will be reported as needing finance "
                "ingestion"
            )
        allowed = _COMPATIBLE.get(self.value_format, frozenset())
        if definition.kind not in allowed:
            raise AnalyticsError(
                f"column {self.header!r} is read as a {self.value_format.value} and "
                f"cannot supply {self.metric!r}, which is a "
                f"{definition.kind.value} in {definition.unit!r}. A conversion "
                "between them would be a unit change nothing in the file authorised"
            )
        if self.denominator_header and definition.kind is not MetricKind.RATE:
            raise AnalyticsError(
                f"column {self.header!r}: a denominator column is only meaningful "
                f"for a rate; {self.metric!r} is a {definition.kind.value}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "header": self.header,
            "value_format": self.value_format.value,
            "metric": self.metric,
            "denominator_header": self.denominator_header,
            "monetary": self.monetary,
            "unmapped_reason": self.unmapped_reason,
        }


# Which metric kinds each column shape may supply. A count has to arrive as a
# whole number, a clock duration has to land on a duration, and a percentage has
# to land on something defined over 0.0-1.0.
_COMPATIBLE: dict[ValueFormat, frozenset[MetricKind]] = {
    ValueFormat.INTEGER: frozenset({MetricKind.COUNT, MetricKind.DURATION}),
    ValueFormat.DECIMAL: frozenset(
        {MetricKind.DURATION, MetricKind.FRACTION, MetricKind.RATE}
    ),
    ValueFormat.PERCENTAGE: frozenset({MetricKind.RATE, MetricKind.FRACTION}),
    ValueFormat.DURATION_CLOCK: frozenset({MetricKind.DURATION}),
    ValueFormat.DATE_ISO: frozenset(),
    ValueFormat.TEXT: frozenset(),
}


@dataclass(frozen=True)
class StudioExportSchema:
    """One recognised Studio report: how to identify it, and what it contains."""

    schema_id: str
    report_name: str
    video_id_header: str
    columns: tuple[ColumnMapping, ...]
    required_headers: tuple[str, ...]
    forbidden_headers: tuple[str, ...] = ()
    title_header: str = ""
    date_header: str = ""
    fixed_semantics: TemporalSemantics | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "schema_id", assert_tag(self.schema_id, "schema_id"))
        object.__setattr__(self, "report_name", assert_prose(self.report_name, "schema report_name"))
        object.__setattr__(
            self,
            "video_id_header",
            assert_header(self.video_id_header, "video_id_header"),
        )
        if self.title_header:
            object.__setattr__(
                self, "title_header", assert_header(self.title_header, "title_header")
            )
        if self.date_header:
            object.__setattr__(
                self, "date_header", assert_header(self.date_header, "date_header")
            )
        object.__setattr__(self, "columns", tuple(self.columns))
        if not self.columns:
            raise AnalyticsError(
                f"schema {self.schema_id!r} maps no columns, so it could only ever "
                "recognise a file and read nothing out of it"
            )
        for column in self.columns:
            if not isinstance(column, ColumnMapping):
                raise AnalyticsError(
                    f"schema {self.schema_id!r}: columns must be ColumnMapping "
                    f"records, got {type(column).__name__}"
                )
        headers = [column.header for column in self.columns]
        duplicates = sorted({h for h in headers if headers.count(h) > 1})
        if duplicates:
            raise AnalyticsError(
                f"schema {self.schema_id!r}: {', '.join(duplicates)} is mapped more "
                "than once, so a cell would have two meanings"
            )
        object.__setattr__(
            self,
            "required_headers",
            tuple(assert_header(h, "required header") for h in self.required_headers),
        )
        if not self.required_headers:
            raise AnalyticsError(
                f"schema {self.schema_id!r} requires no header, so it would match "
                "every file including an empty one"
            )
        object.__setattr__(
            self,
            "forbidden_headers",
            tuple(assert_header(h, "forbidden header") for h in self.forbidden_headers),
        )
        clash = set(self.required_headers) & set(self.forbidden_headers)
        if clash:
            raise AnalyticsError(
                f"schema {self.schema_id!r}: {', '.join(sorted(clash))} is both "
                "required and forbidden, so nothing can match it"
            )
        known = self.known_headers
        for header in self.required_headers:
            if header not in known:
                raise AnalyticsError(
                    f"schema {self.schema_id!r}: requires {header!r}, which it does "
                    "not name as an identity column or map as a column"
                )
        for column in self.columns:
            if column.denominator_header and column.denominator_header not in known:
                raise AnalyticsError(
                    f"schema {self.schema_id!r}: column {column.header!r} takes its "
                    f"denominator from {column.denominator_header!r}, which this "
                    "schema does not contain"
                )
        if self.fixed_semantics is not None and not isinstance(
            self.fixed_semantics, TemporalSemantics
        ):
            raise AnalyticsError(
                f"schema {self.schema_id!r}: fixed_semantics must be a "
                f"TemporalSemantics, got {self.fixed_semantics!r}"
            )
        if self.date_header and self.fixed_semantics is not TemporalSemantics.INTERVAL:
            raise AnalyticsError(
                f"schema {self.schema_id!r}: a per-day report measures a bounded day, "
                "so its semantics are INTERVAL and are not the caller's to declare"
            )

    @property
    def known_headers(self) -> frozenset[str]:
        """Every header this schema understands, mapped or identity."""
        identity = {self.video_id_header, self.title_header, self.date_header}
        return frozenset(
            {header for header in identity if header}
            | {column.header for column in self.columns}
        )

    @property
    def requires_reporting_timezone(self) -> bool:
        """A per-day report needs to know where a day starts and ends."""
        return bool(self.date_header)

    @property
    def mapped_columns(self) -> tuple[ColumnMapping, ...]:
        return tuple(column for column in self.columns if column.is_mapped)

    @property
    def monetary_columns(self) -> tuple[str, ...]:
        return tuple(column.header for column in self.columns if column.monetary)

    @property
    def unmapped_columns(self) -> tuple[str, ...]:
        return tuple(
            column.header
            for column in self.columns
            if not column.is_mapped and not column.monetary
        )

    def mapping_for(self, header: str) -> ColumnMapping | None:
        for column in self.columns:
            if column.header == header:
                return column
        return None

    def matches(self, header: Iterable[str]) -> bool:
        present = set(header)
        if not set(self.required_headers) <= present:
            return False
        return not (set(self.forbidden_headers) & present)

    def missing_headers(self, header: Iterable[str]) -> tuple[str, ...]:
        present = set(header)
        return tuple(h for h in self.required_headers if h not in present)

    def unknown_headers(self, header: Iterable[str]) -> tuple[str, ...]:
        """Headers in the file this schema does not understand, in file order.

        Reported rather than discarded, and never guessed at. A new Studio
        column shows up here on the first import after it appears, which is the
        signal that the table in this module needs a decision.
        """
        known = self.known_headers
        return tuple(h for h in header if h not in known)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "report_name": self.report_name,
            "video_id_header": self.video_id_header,
            "title_header": self.title_header,
            "date_header": self.date_header,
            "required_headers": list(self.required_headers),
            "forbidden_headers": list(self.forbidden_headers),
            "fixed_semantics": (
                self.fixed_semantics.value if self.fixed_semantics else None
            ),
            "columns": [column.to_dict() for column in self.columns],
        }


def _mapped(header: str, value_format: ValueFormat, metric: str, **kwargs: Any) -> ColumnMapping:
    return ColumnMapping(header=header, value_format=value_format, metric=metric, **kwargs)


def _unmapped(header: str, value_format: ValueFormat, reason: str, **kwargs: Any) -> ColumnMapping:
    return ColumnMapping(
        header=header, value_format=value_format, unmapped_reason=reason, **kwargs
    )


def _money(header: str) -> ColumnMapping:
    return ColumnMapping(
        header=header,
        value_format=ValueFormat.DECIMAL,
        monetary=True,
        unmapped_reason=(
            "a monetary column; company/finance owns money, so this is reported as "
            "needing finance ingestion and no analytics observation is made"
        ),
    )


# -- the recognised reports ------------------------------------------------
#
# Two, deliberately. They are the two shapes this phase can read honestly: a
# per-video table whose coverage the caller declares, and a per-video-per-day
# table whose coverage each row carries. A third report is a third entry here
# with its own columns, not a flag on one of these.

_VIDEO_ID = "Content"
_VIDEO_TITLE = "Video title"
_DATE = "Date"

_COMMON_COUNTS: tuple[ColumnMapping, ...] = (
    _mapped("Views", ValueFormat.INTEGER, "views"),
    _mapped("Impressions", ValueFormat.INTEGER, "impressions"),
    _mapped("Likes", ValueFormat.INTEGER, "likes"),
    _mapped("Comments added", ValueFormat.INTEGER, "comments"),
    _mapped("Shares", ValueFormat.INTEGER, "shares"),
    _mapped("Subscribers gained", ValueFormat.INTEGER, "subscribers_gained"),
    _mapped("Subscribers lost", ValueFormat.INTEGER, "subscribers_lost"),
    _mapped("Watch time (hours)", ValueFormat.DECIMAL, "watch_time_hours"),
    _mapped(
        "Average view duration",
        ValueFormat.DURATION_CLOCK,
        "average_view_duration_seconds",
    ),
    _mapped(
        "Impressions click-through rate (%)",
        ValueFormat.PERCENTAGE,
        "click_through_rate",
        denominator_header="Impressions",
    ),
    _unmapped(
        "Subscribers",
        ValueFormat.INTEGER,
        "Studio's net subscriber figure. The registry keeps subscribers_gained and "
        "subscribers_lost apart because a net number hides which of the two moved, "
        "and splitting one net figure into two would be a fabrication",
    ),
    _money("Your estimated revenue (USD)"),
    _money("RPM (USD)"),
    _money("CPM (USD)"),
)

STUDIO_VIDEO_TOTALS_V1 = StudioExportSchema(
    schema_id="studio_video_totals_v1",
    report_name="YouTube Studio, Content tab, per-video table export (Table data.csv)",
    video_id_header=_VIDEO_ID,
    title_header=_VIDEO_TITLE,
    required_headers=(_VIDEO_ID, "Views"),
    # A file with a Date column is a per-day report whatever else it carries, and
    # reading its rows as whole-video totals would multiply every count by the
    # number of days. Forbidding the header here is what makes recognition
    # decidable without ranking two candidate schemas against each other.
    forbidden_headers=(_DATE,),
    columns=_COMMON_COUNTS
    + (
        _mapped(
            "Average percentage viewed (%)",
            ValueFormat.PERCENTAGE,
            "average_percentage_viewed",
            denominator_header="Duration",
        ),
        _unmapped(
            "Duration",
            ValueFormat.DURATION_CLOCK,
            "the video's own length: a property of the deliverable rather than a "
            "reading taken at a time, recorded here only as the denominator of "
            "average_percentage_viewed",
        ),
        _unmapped(
            "Video publish time",
            ValueFormat.TEXT,
            "an identity attribute of the deliverable. Publication time is recorded "
            "on AnalyzedDeliverable by whoever published it, and a second copy here "
            "would be a second answer about when a video went out",
        ),
    ),
)

STUDIO_VIDEO_DAILY_V1 = StudioExportSchema(
    schema_id="studio_video_daily_v1",
    report_name="YouTube Studio, per-video day-by-day export (Chart data.csv)",
    video_id_header=_VIDEO_ID,
    title_header=_VIDEO_TITLE,
    date_header=_DATE,
    required_headers=(_DATE, _VIDEO_ID, "Views"),
    fixed_semantics=TemporalSemantics.INTERVAL,
    columns=_COMMON_COUNTS,
)

STANDARD_STUDIO_SCHEMAS: tuple[StudioExportSchema, ...] = (
    STUDIO_VIDEO_TOTALS_V1,
    STUDIO_VIDEO_DAILY_V1,
)


def recognise_schema(
    header: Iterable[str], schemas: Iterable[StudioExportSchema] | None = None
) -> StudioExportSchema:
    """The one schema whose required and forbidden headers this file satisfies.

    Refuses on nothing matching and on more than one matching. The second
    refusal is the important one: a tie would have to be broken by a rule, every
    such rule is a preference dressed as a fact, and the honest answer when two
    descriptions of a file both fit is that the descriptions need fixing.
    """
    columns = tuple(header)
    candidates = [
        schema
        for schema in (schemas if schemas is not None else STANDARD_STUDIO_SCHEMAS)
        if schema.matches(columns)
    ]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise StudioExportRejected(
            "no Studio export schema recognises this file. Its headers are "
            + ", ".join(repr(c) for c in columns[:12])
            + (", ..." if len(columns) > 12 else "")
            + ". Headers are matched exactly, so a renamed or space-padded column "
            "does not match - add the report to company/analytics/studio_schema.py "
            "with a decision for every column rather than relaxing the match"
        )
    raise StudioExportRejected(
        "this file matches more than one Studio export schema ("
        + ", ".join(schema.schema_id for schema in candidates)
        + "). Two schemas that both fit one file cannot both be describing it; "
        "give one of them a header the other forbids"
    )
