"""Turning the text in one cell into a number, or refusing to.

## The cell is text, and text is not a measurement

A CSV holds characters. `1,234` is five characters and a convention, and the
convention is not in the file. An English-locale YouTube Studio export writes
one thousand two hundred and thirty-four that way; a German-locale export writes
`1.234` for the same number, and writes `1,234` to mean one and a bit. A parser
that picks a reading and carries on is not being lenient. It is wrong in
silence, by a factor of a thousand, in a number somebody will later plan around.

So there is no guessing here. A `NumberFormat` says which character is the
decimal point and which - if any - groups the thousands; the format that did the
reading is recorded on the source record beside the file digest; and a cell the
declared format cannot read without choosing on the caller's behalf is refused
with the reason and the fix. `DOT_DECIMAL` is the default because it is what an
English Studio export emits, and under it a comma is refused rather than ignored.

## Blank is not zero, and this module will not pretend otherwise

`parse_cell` refuses an empty cell rather than returning 0.0, because a video
with no impressions reported and a video with zero impressions are different
facts and only one of them is a measurement. The caller turns that refusal into
a row diagnostic and produces no observation. Section 7 of the brief, enforced
by there being no code path that could do anything else.

## Shape is declared per column, and checked against the metric

`ValueFormat` says what shape a cell has, not what the metric means.
`studio_schema.py` pairs the two and refuses the combinations that would mix
units - a percentage landing on a count, a clock duration landing on a rate - so
each column's conversion is visible in the schema rather than buried in a branch
here.

The one conversion this module performs is percent to fraction, because the
canonical rate metrics are expressed with `1.0` meaning 100% and the column
header says `(%)`. It divides by one hundred and nothing else: `118.41%` becomes
`1.1841`, not `1.0`. Whether a metric may sit above full scale is declared on
the metric (`unbounded_above`) and checked when the observation is built, and
clamping here would destroy the reading before anything got the chance to.
Everything else is read in the unit the column already carries: a watch time in
hours stays hours, and it is the metric definition's job to say so.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from .errors import AnalyticsError, StudioValueError

# The characters that could be a decimal point or a group separator depending on
# whose keyboard produced the file. Under a format that declares no grouping
# separator, any of these other than the declared decimal point is a refusal.
_SEPARATORS = (",", ".", " ", " ", " ", "'")

# The longest cell text quoted back in a diagnostic. Enough to see the defect,
# short enough that an error message never becomes a copy of the export.
MAX_QUOTED_CHARS = 60

SECONDS_PER_MINUTE = 60
SECONDS_PER_HOUR = 3600


class ValueFormat(Enum):
    """The shape of the text in a column, independent of what it measures."""

    INTEGER = "integer"
    DECIMAL = "decimal"
    PERCENTAGE = "percentage"
    DURATION_CLOCK = "duration_clock"
    DATE_ISO = "date_iso"
    TEXT = "text"

    @property
    def is_numeric(self) -> bool:
        return self in _NUMERIC


_NUMERIC = frozenset(
    {
        ValueFormat.INTEGER,
        ValueFormat.DECIMAL,
        ValueFormat.PERCENTAGE,
        ValueFormat.DURATION_CLOCK,
    }
)


@dataclass(frozen=True)
class NumberFormat:
    """Which character is the decimal point, and which groups the thousands.

    `thousands_separator` is `None` for "no grouping separator was declared",
    which is not the same as `""`: under `None` every grouping character is
    refused as ambiguous, because the caller has not said what one would mean.
    """

    name: str
    decimal_separator: str = "."
    thousands_separator: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise AnalyticsError(
                "a number format must be named, so that a source record can say "
                "which one read the file"
            )
        if self.decimal_separator not in (".", ","):
            raise AnalyticsError(
                f"number format {self.name!r}: the decimal separator must be '.' or "
                f"',', got {self.decimal_separator!r}"
            )
        if self.thousands_separator is not None:
            if self.thousands_separator not in _SEPARATORS:
                raise AnalyticsError(
                    f"number format {self.name!r}: {self.thousands_separator!r} is "
                    "not a thousands separator this parser recognises"
                )
            if self.thousands_separator == self.decimal_separator:
                raise AnalyticsError(
                    f"number format {self.name!r}: the decimal and thousands "
                    f"separators are both {self.decimal_separator!r}, which cannot "
                    "read any number"
                )

    @property
    def describes_grouping(self) -> bool:
        return self.thousands_separator is not None

    def __str__(self) -> str:
        if self.thousands_separator is None:
            return f"{self.name} (decimal {self.decimal_separator!r}, no grouping)"
        return (
            f"{self.name} (decimal {self.decimal_separator!r}, "
            f"thousands {self.thousands_separator!r})"
        )


# The English Studio export: a dot decimal point and no grouping. Under this
# format a comma is refused rather than read, which is the whole of section 8.
DOT_DECIMAL = NumberFormat("dot_decimal", ".", None)

# The same export with grouped thousands - `1,234.56`.
EN_US_GROUPED = NumberFormat("en_us_grouped", ".", ",")

# A European-locale export - `1.234,56`.
EURO_GROUPED = NumberFormat("euro_grouped", ",", ".")

# A comma decimal point with no grouping - `1,5` is one and a half.
COMMA_DECIMAL = NumberFormat("comma_decimal", ",", None)

STANDARD_NUMBER_FORMATS: dict[str, NumberFormat] = {
    fmt.name: fmt
    for fmt in (DOT_DECIMAL, EN_US_GROUPED, EURO_GROUPED, COMMA_DECIMAL)
}


def number_format(name: str) -> NumberFormat:
    try:
        return STANDARD_NUMBER_FORMATS[name]
    except KeyError:
        raise AnalyticsError(
            f"unknown number format {name!r}; known: "
            + ", ".join(sorted(STANDARD_NUMBER_FORMATS))
        ) from None


def quote_cell(text: Any) -> str:
    """The cell text as a diagnostic may carry it: trimmed, and truncated.

    Section 16 asks a failure to name the cell rather than dump the row, and
    section 25 asks the same thing of privacy. One value, capped.
    """
    if not isinstance(text, str):
        return repr(text)
    body = text.strip()
    if len(body) <= MAX_QUOTED_CHARS:
        return body
    return body[:MAX_QUOTED_CHARS] + "..."


def is_blank(text: Any) -> bool:
    """A cell holding nothing. Not a zero, and never converted into one."""
    return not isinstance(text, str) or not text.strip()


def parse_cell(text: str, value_format: ValueFormat, fmt: NumberFormat) -> float:
    """The number this cell holds, or a `StudioValueError` saying why it holds none.

    Never returns for a blank cell. `is_blank` is the caller's check, and a
    blank arriving here is a caller that decided an empty cell was a zero.
    """
    if not value_format.is_numeric:
        raise StudioValueError(
            f"a {value_format.value} column is not read as a number, so its cells "
            "do not become metric values"
        )
    if is_blank(text):
        raise StudioValueError(
            "the cell is empty; an empty cell is a measurement that was not "
            "reported, which is recorded as missing rather than as zero"
        )
    body = text.strip()
    if value_format is ValueFormat.DURATION_CLOCK:
        return _clock_seconds(body)
    if value_format is ValueFormat.PERCENTAGE:
        # Divided as a decimal rather than as a float. `5.8 / 100.0` in binary
        # floating point is 0.057999999999999996, which is a second rounding of
        # a number the export stated exactly; `Decimal("5.8") / 100` converts to
        # the float nearest 0.058, which is what the file said.
        return float(Decimal(_normalised(_strip_percent(body), fmt)) / 100)
    if "%" in body:
        raise StudioValueError(
            f"{quote_cell(body)!r} carries a percent sign in a column this schema "
            "reads as a plain number; the mapping and the export disagree about "
            "what the cell means"
        )
    number = float(_normalised(body, fmt))
    if value_format is ValueFormat.INTEGER and number != int(number):
        raise StudioValueError(
            f"{quote_cell(body)!r} has a fractional part in a column this schema "
            "reads as a whole count; rounding it here would invent a precision the "
            "export did not report"
        )
    return number


def parse_iso_day(text: str) -> tuple[int, int, int]:
    """`YYYY-MM-DD` as a (year, month, day) triple, or a refusal.

    Exactly one accepted spelling. `09/10/2026` is September the tenth to one
    half of the world and the ninth of October to the other, and a date column
    that guessed would move a whole day of readings by a month.
    """
    body = text.strip()
    parts = body.split("-")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not an ISO 8601 date. This parser reads "
            "YYYY-MM-DD and nothing else, because a slash-separated date names a "
            "different day in different countries"
        )
    if (len(parts[0]), len(parts[1]), len(parts[2])) != (4, 2, 2):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not a zero-padded YYYY-MM-DD date"
        )
    return int(parts[0]), int(parts[1]), int(parts[2])


# -- internals -------------------------------------------------------------


def _strip_percent(body: str) -> str:
    """Remove one trailing percent sign, which the column is allowed to carry."""
    if body.endswith("%"):
        return body[:-1].strip()
    if "%" in body:
        raise StudioValueError(
            f"{quote_cell(body)!r} carries a percent sign somewhere other than the "
            "end, so what it is a percentage of is not readable from the cell"
        )
    return body


def _clock_seconds(body: str) -> float:
    """`0:17`, `00:00:17` and `1:02:03` as seconds. Anything else is refused."""
    parts = body.split(":")
    if len(parts) not in (2, 3) or not all(part.isdigit() for part in parts):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not a clock duration. This column is read as "
            "H:MM:SS or MM:SS; a bare number of seconds belongs in a column the "
            "schema maps as an integer, so that the unit stays visible"
        )
    values = [int(part) for part in parts]
    labels = ("minutes", "seconds") if len(values) == 3 else ("seconds",)
    for label, value in zip(labels, values[1:]):
        if value > 59:
            raise StudioValueError(
                f"{quote_cell(body)!r} reports {value} {label}, which is not a clock "
                "reading"
            )
    if len(values) == 2:
        return float(values[0] * SECONDS_PER_MINUTE + values[1])
    return float(
        values[0] * SECONDS_PER_HOUR + values[1] * SECONDS_PER_MINUTE + values[2]
    )


def _normalised(body: str, fmt: NumberFormat) -> str:
    """The cell rewritten as a plain `[-]digits[.digits]` string, or a refusal.

    A string rather than a number, so that a caller which needs exact decimal
    arithmetic - the percent conversion - can have it, and one which does not
    can call `float` on the result.
    """
    sign = ""
    if body.startswith("-"):
        sign, body = "-", body[1:].strip()
    elif body.startswith("+"):
        body = body[1:].strip()
    if not body:
        raise StudioValueError("the cell holds a sign and no digits")

    stray = [
        character
        for character in _SEPARATORS
        if character in body
        and character != fmt.decimal_separator
        and character != fmt.thousands_separator
    ]
    # A stray separator is only *ambiguous* when what surrounds it is digits.
    # `1,234` reads two ways and needs a declared format; `fifty thousand` reads
    # no ways at all, and calling it ambiguous would send somebody to fix a
    # locale setting over a cell that is simply not a number.
    if stray and not _digits_only(body):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not a number under the declared format {fmt}"
        )
    if stray:
        raise StudioValueError(
            f"{quote_cell(body)!r} contains {stray[0]!r}, which the declared number "
            f"format {fmt} does not define. Under some conventions it is a decimal "
            "point and under others a thousands separator, and the two readings "
            "differ by a factor of a thousand - declare the export's number format, "
            "or correct the cell",
            ambiguous=True,
        )

    whole, separator, fraction = body.partition(fmt.decimal_separator)
    if separator and fmt.decimal_separator in fraction:
        raise StudioValueError(
            f"{quote_cell(body)!r} has more than one {fmt.decimal_separator!r}, so "
            "it is not a number under the declared format"
        )
    digits = _ungrouped(whole, fmt, body)
    if separator:
        if not fraction.isdigit():
            raise StudioValueError(
                f"{quote_cell(body)!r} has no digits after its decimal point"
            )
        digits = f"{digits}.{fraction}"
    return f"{sign}{digits}"


def _digits_only(body: str) -> bool:
    """Is this digits and separators, and nothing else?"""
    stripped = body
    for character in _SEPARATORS:
        stripped = stripped.replace(character, "")
    return stripped.isdigit()


def _ungrouped(whole: str, fmt: NumberFormat, body: str) -> str:
    """The integer part with its declared grouping removed, the grouping checked.

    The grouping is verified rather than stripped. `1.2345` under a European
    format is not one and a bit, and it is not twelve thousand three hundred and
    forty-five either - it is a cell nobody should read without looking at it.
    """
    if fmt.thousands_separator is None or fmt.thousands_separator not in whole:
        if not whole.isdigit():
            raise StudioValueError(
                f"{quote_cell(body)!r} is not a number under the declared format {fmt}"
            )
        return whole
    groups = whole.split(fmt.thousands_separator)
    if not all(group.isdigit() for group in groups):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not a number under the declared format {fmt}"
        )
    if not 1 <= len(groups[0]) <= 3 or any(len(group) != 3 for group in groups[1:]):
        raise StudioValueError(
            f"{quote_cell(body)!r} is not grouped in thousands under the declared "
            f"format {fmt}, so its separator is not the one that was declared"
        )
    return "".join(groups)
