"""The feature tags a deliverable is grouped by, supplied and never inferred.

## Why this is a closed set of dimensions with open values

Section 14 names eight dimensions and says the tags must be supplied. Both
halves matter, and they pull in opposite directions, so they are enforced
differently.

The *dimensions* are closed. If a caller can invent a dimension then `hook` and
`hook_type` become two axes describing one thing, and a grouped report shows
each of them over half the population. Adding a ninth dimension is a code change
somebody reviews.

The *values* are open, because the vocabulary of hook styles is the thing we are
still discovering and freezing it now would be guessing at the answer. They are
held to tag shape - lowercase, underscore-joined - so that `cold_open` and
`Cold Open` cannot become two groups.

## Why there is no inference, and how that is proved

There is no title on a `ContentFeatures`, no description, and no code path from
text to tag. A feature is what somebody recorded about how the deliverable was
actually made; a feature read off a title is a guess about how it was made,
carrying the authority of a record.

The prohibition is structural rather than documented: `from_labels` takes a
mapping of dimension to tag and there is no other constructor. A caller holding
only a title has nothing to pass. `tests/test_company_analytics.py` closes the
loop by grepping the package for any read of a deliverable's title outside
serialisation, so a future convenience helper cannot quietly open the door.

## Coverage is reported, not filled in

`missing_dimensions` names the axes a deliverable was never tagged on. A
grouped report uses it to say "42 deliverables, 11 of them untagged for
event_density_bucket" rather than dropping the eleven and reporting a cleaner
number over a population nobody described.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from .common import assert_tag
from .errors import AnalyticsError


class FeatureDimension(Enum):
    """The axes a deliverable may be tagged on. Closed; see the module docstring."""

    HOOK_TYPE = "hook_type"
    CAMERA_STYLE = "camera_style"
    VISUAL_THEME = "visual_theme"
    RACE_LENGTH = "race_length"
    EVENT_DENSITY_BUCKET = "event_density_bucket"
    AUDIO_STYLE = "audio_style"
    FORMAT_FAMILY = "format_family"
    MECHANIC_FAMILY = "mechanic_family"


ALL_DIMENSIONS: tuple[FeatureDimension, ...] = tuple(FeatureDimension)


@dataclass(frozen=True)
class ContentFeatures:
    """What a deliverable was made of, as tags somebody recorded.

    Stored as a sorted tuple of pairs rather than a dict so the record is
    hashable, frozen and serialises in one order regardless of how it was built.
    """

    labels: tuple[tuple[FeatureDimension, str], ...] = ()

    def __post_init__(self) -> None:
        seen: dict[FeatureDimension, str] = {}
        for item in self.labels:
            if not isinstance(item, tuple) or len(item) != 2:
                raise AnalyticsError(
                    f"feature label {item!r} must be a (FeatureDimension, tag) pair"
                )
            dimension, value = item
            if not isinstance(dimension, FeatureDimension):
                raise AnalyticsError(
                    f"feature dimension must be a FeatureDimension, got {dimension!r}. "
                    "Known: " + ", ".join(d.value for d in ALL_DIMENSIONS)
                )
            tag = assert_tag(value, f"feature {dimension.value}")
            if dimension in seen and seen[dimension] != tag:
                raise AnalyticsError(
                    f"feature {dimension.value} was given two values, "
                    f"{seen[dimension]!r} and {tag!r}. One deliverable has one tag per "
                    "dimension; two values would put it in two groups of one report"
                )
            seen[dimension] = tag
        object.__setattr__(
            self, "labels", tuple(sorted(seen.items(), key=lambda kv: kv[0].value))
        )

    @classmethod
    def from_labels(cls, labels: Mapping[Any, str]) -> ContentFeatures:
        """The only constructor that takes loose input, and it takes tags.

        Accepts a dimension either as a `FeatureDimension` or as its value
        string, because a caller decoding JSON has the latter. It does not
        accept anything that is not already a dimension name, so a title cannot
        arrive here under a different label.
        """
        if not isinstance(labels, Mapping):
            raise AnalyticsError(
                f"content features must be a mapping of dimension to tag, got "
                f"{type(labels).__name__}. Features are recorded, never derived from "
                "a title or a description"
            )
        out: list[tuple[FeatureDimension, str]] = []
        for key, value in labels.items():
            out.append((_dimension(key), value))
        return cls(tuple(out))

    def get(self, dimension: FeatureDimension) -> str | None:
        for known, value in self.labels:
            if known is dimension:
                return value
        return None

    @property
    def dimensions(self) -> tuple[FeatureDimension, ...]:
        return tuple(dimension for dimension, _ in self.labels)

    @property
    def missing_dimensions(self) -> tuple[FeatureDimension, ...]:
        """Axes this deliverable was never tagged on, in declaration order."""
        present = set(self.dimensions)
        return tuple(d for d in ALL_DIMENSIONS if d not in present)

    def __bool__(self) -> bool:
        return bool(self.labels)

    def to_dict(self) -> dict[str, str]:
        return {dimension.value: value for dimension, value in self.labels}

    @classmethod
    def from_dict(cls, data: Any, field_name: str = "features") -> ContentFeatures:
        if data is None:
            return cls()
        if not isinstance(data, Mapping):
            raise AnalyticsError(
                f"{field_name}: expected a mapping of dimension to tag, got {data!r}"
            )
        return cls.from_labels(data)


def _dimension(key: Any) -> FeatureDimension:
    if isinstance(key, FeatureDimension):
        return key
    try:
        return FeatureDimension(key)
    except ValueError:
        raise AnalyticsError(
            f"unknown feature dimension {key!r}. The dimensions are closed so that two "
            "names cannot describe one axis; known: "
            + ", ".join(d.value for d in ALL_DIMENSIONS)
        ) from None
