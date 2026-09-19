"""The review window: when the company was looked at, stated rather than implied.

Section 1 of the brief asks for an explicit window and then says why: *do not
compare metrics from unrelated time periods as though they are equivalent*. A
first-pass rate over a quiet fortnight and one over a release week are two
numbers with the same name, and an organization that averages them has measured
nothing.

So a window is a record class rather than a pair of loose dates, every signal
and every finding carries one, and `mismatch_caveat` exists to make the awkward
case visible instead of arithmetic: comparing a 14-day baseline with a 3-day
observation is allowed - sometimes it is all there is - but the resulting record
says so, in its own limitations, where the next reader will see it.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from .common import assert_day, assert_prose
from .errors import OrgIntelligenceError

# How far two windows' lengths may differ before a comparison between them
# carries a caveat. A quarter, not a law of nature; it is here so a company
# that disagrees changes one number.
COMPARABLE_LENGTH_TOLERANCE = 0.25


@dataclass(frozen=True)
class ReviewWindow:
    """A closed interval of days, inclusive of both ends."""

    start: dt.date
    end: dt.date
    label: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", assert_day(self.start, "window start"))
        object.__setattr__(self, "end", assert_day(self.end, "window end"))
        if self.end < self.start:
            raise OrgIntelligenceError(
                f"impossible review window: {self.end.isoformat()} is before "
                f"{self.start.isoformat()}"
            )
        if self.label:
            assert_prose(self.label, "window label")

    @property
    def days(self) -> int:
        """Length in days, counting both ends. A one-day window is one day."""
        return (self.end - self.start).days + 1

    def contains(self, day: dt.date) -> bool:
        return self.start <= assert_day(day, "day") <= self.end

    def overlaps(self, other: ReviewWindow) -> bool:
        return self.start <= other.end and other.start <= self.end

    def comparable_to(self, other: ReviewWindow) -> bool:
        """Are these two windows close enough in length to compare directly?"""
        longer, shorter = sorted((self.days, other.days), reverse=True)
        return (longer - shorter) / longer <= COMPARABLE_LENGTH_TOLERANCE

    def mismatch_caveat(self, other: ReviewWindow) -> str:
        """The sentence a record must carry when the two windows differ. Empty if not."""
        if self.comparable_to(other):
            return ""
        return (
            f"window lengths differ: {self.days} day(s) "
            f"({self.start.isoformat()}..{self.end.isoformat()}) against {other.days} day(s) "
            f"({other.start.isoformat()}..{other.end.isoformat()}); rates over them are not "
            "equivalent measurements"
        )

    @property
    def limitation(self) -> str:
        """What every record computed over this window is limited to."""
        return (
            f"observed only between {self.start.isoformat()} and {self.end.isoformat()} "
            f"({self.days} day(s)); nothing here describes the company outside it"
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
    def from_dict(cls, data: dict[str, Any]) -> ReviewWindow:
        return cls(
            start=assert_day(data["start"], "window start"),
            end=assert_day(data["end"], "window end"),
            label=data.get("label", ""),
        )
