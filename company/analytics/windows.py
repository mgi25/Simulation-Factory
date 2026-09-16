"""Two kinds of window, because analytics asks two different time questions.

## Age windows, for comparing videos with each other

The naive comparison is the wrong one. Video A published in March and video B
published in September have different calendar dates attached to every reading,
and comparing "A's views" with "B's views" compares a six-month-old number with
a one-week-old number. The fix is not a caveat, it is a different axis: both
videos get measured at *the same age*, and a `first_24h` reading is compared
only with another `first_24h` reading.

`AgeWindow` is that axis. It is a half-open interval of hours since publication,
and `MetricComparison` refuses a pair whose windows differ. That single refusal
removes the most common way a content analytics layer lies to its owner.

Half-open rather than closed on both ends, because `first_24h` and `day_2_to_7`
must not both contain hour 24. A closed interval would put one reading in two
windows and count it twice in any baseline that used both.

## Date ranges, for naming a population

Section 17 asks for a baseline over "the last 10 Shorts in Race format", and
that is a calendar question: which videos were published between these two
dates. `DateRange` answers it, and it exists separately rather than as a mode of
`AgeWindow` because conflating them is what produces a baseline whose members
were measured at four different ages.

## Comparability is a returned sentence, not a boolean

`AgeWindow.mismatch` and `DateRange.mismatch_caveat` return the sentence a
record has to carry, or an empty string. The caller cannot get a bare False and
forget to say why - the reason is the return value, so the only way to use the
check is to propagate the explanation.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from .common import assert_day, assert_prose, assert_tag
from .errors import AnalyticsError

# How far two date ranges' lengths may differ before a comparison between them
# carries a caveat. A quarter, matching `company/org_intelligence/window.py`, so
# the two subsystems do not disagree about what "similar length" means.
COMPARABLE_LENGTH_TOLERANCE = 0.25

HOURS_PER_DAY = 24


def _hours(value: Any, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AnalyticsError(f"{field_name}: expected a number of hours, got {value!r}")
    hours = float(value)
    if hours < 0:
        raise AnalyticsError(
            f"{field_name}: {hours} is negative; a reading cannot be taken before the "
            "thing it measures was published"
        )
    return hours


def _fmt(hours: float) -> str:
    return str(int(hours)) if hours == int(hours) else str(hours)


@dataclass(frozen=True)
class AgeWindow:
    """Hours since publication, half-open: `min_age_hours <= age < max_age_hours`.

    `max_age_hours` may be None, meaning "and everything after", which is what
    a lifetime-to-date reading actually is.
    """

    label: str
    min_age_hours: float
    max_age_hours: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "label", assert_tag(self.label, "age window label"))
        object.__setattr__(
            self, "min_age_hours", _hours(self.min_age_hours, "min_age_hours")
        )
        if self.max_age_hours is not None:
            object.__setattr__(
                self, "max_age_hours", _hours(self.max_age_hours, "max_age_hours")
            )
            if self.max_age_hours <= self.min_age_hours:
                raise AnalyticsError(
                    f"age window {self.label!r}: max_age_hours "
                    f"{self.max_age_hours} must be greater than min_age_hours "
                    f"{self.min_age_hours}; an empty window can hold no reading"
                )

    def contains(self, age_hours: float) -> bool:
        """Half-open on purpose: hour 24 belongs to day 2, not to the first day."""
        if age_hours < self.min_age_hours:
            return False
        return self.max_age_hours is None or age_hours < self.max_age_hours

    @property
    def is_open_ended(self) -> bool:
        return self.max_age_hours is None

    def mismatch(self, other: AgeWindow) -> str:
        """The sentence a comparison across these two windows must carry.

        Empty when the windows are identical. Anything else is a real
        difference - a 24-hour reading and a 30-day reading are two different
        measurements of two different things, and no tolerance makes them one.
        """
        if self == other:
            return ""
        return (
            f"observation windows differ: {self} against {other}; a metric read at "
            "one age is not a measurement of the same thing as the same metric read "
            "at another, so the difference between them is not a result"
        )

    def __str__(self) -> str:
        upper = "onwards" if self.max_age_hours is None else f"{_fmt(self.max_age_hours)}h"
        return f"{self.label} ({_fmt(self.min_age_hours)}h..{upper})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "min_age_hours": self.min_age_hours,
            "max_age_hours": self.max_age_hours,
        }

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "age_window") -> AgeWindow:
        if not isinstance(data, dict):
            raise AnalyticsError(
                f"{field_name}: expected an age window object, got {data!r}"
            )
        try:
            return cls(
                label=data["label"],
                min_age_hours=data["min_age_hours"],
                max_age_hours=data.get("max_age_hours"),
            )
        except KeyError as exc:
            raise AnalyticsError(f"{field_name}: missing {exc.args[0]!r}") from None


# The windows the brief names, plus the lifetime reading. Provided so that two
# sessions measuring "the first day" measure the same interval; a caller with a
# different cadence builds its own `AgeWindow` and nothing here objects.
FIRST_HOUR = AgeWindow("first_hour", 0.0, 1.0)
FIRST_24H = AgeWindow("first_24h", 0.0, 24.0)
FIRST_7D = AgeWindow("first_7d", 0.0, 7 * HOURS_PER_DAY)
FIRST_30D = AgeWindow("first_30d", 0.0, 30 * HOURS_PER_DAY)
LIFETIME = AgeWindow("lifetime", 0.0, None)

STANDARD_AGE_WINDOWS: tuple[AgeWindow, ...] = (
    FIRST_HOUR,
    FIRST_24H,
    FIRST_7D,
    FIRST_30D,
    LIFETIME,
)


def standard_age_window(label: str) -> AgeWindow:
    for window in STANDARD_AGE_WINDOWS:
        if window.label == label:
            return window
    raise AnalyticsError(
        f"unknown standard age window {label!r}; known: "
        + ", ".join(w.label for w in STANDARD_AGE_WINDOWS)
        + ". Build an AgeWindow directly for a cadence this list does not cover."
    )


@dataclass(frozen=True)
class DateRange:
    """A closed interval of calendar days, inclusive of both ends."""

    start: dt.date
    end: dt.date
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", assert_day(self.start, "range start"))
        object.__setattr__(self, "end", assert_day(self.end, "range end"))
        if self.end < self.start:
            raise AnalyticsError(
                f"impossible date range: {self.end.isoformat()} is before "
                f"{self.start.isoformat()}"
            )
        if self.label:
            assert_prose(self.label, "range label")

    @property
    def days(self) -> int:
        """Length in days, counting both ends. A one-day range is one day."""
        return (self.end - self.start).days + 1

    def contains(self, day: dt.date) -> bool:
        return self.start <= assert_day(day, "day") <= self.end

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    def comparable_to(self, other: DateRange) -> bool:
        longer, shorter = sorted((self.days, other.days), reverse=True)
        return (longer - shorter) / longer <= COMPARABLE_LENGTH_TOLERANCE

    def mismatch_caveat(self, other: DateRange) -> str:
        """The sentence a comparison across these two ranges must carry."""
        if self.comparable_to(other):
            return ""
        return (
            f"date ranges differ in length: {self.days} day(s) ({self}) against "
            f"{other.days} day(s) ({other}); counts over them are not equivalent "
            "measurements"
        )

    @property
    def limitation(self) -> str:
        return (
            f"covers only {self.start.isoformat()} to {self.end.isoformat()} "
            f"({self.days} day(s)); nothing here describes anything outside it"
        )

    def __str__(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "days": self.days,
            "label": self.label,
        }

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "date_range") -> DateRange:
        if not isinstance(data, dict):
            raise AnalyticsError(
                f"{field_name}: expected a date range object, got {data!r}"
            )
        try:
            return cls(
                start=data["start"], end=data["end"], label=data.get("label", "")
            )
        except KeyError as exc:
            raise AnalyticsError(f"{field_name}: missing {exc.args[0]!r}") from None
