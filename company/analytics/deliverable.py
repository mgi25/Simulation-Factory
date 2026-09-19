"""The analytics identity of something we published, and nothing more.

## This is a reference, not a model of the thing

`sloped/`, `race2/` and `production/` already describe what a video is: its
track, its camera rig, its edit, its render settings. None of that is here and
none of it is imported. An `AnalyzedDeliverable` is the handle analytics needs
to attach observations to something and to find it again later - an id, what
family it belongs to, when it went out, and pointers back to the production
artefacts that made it.

The test that keeps it honest is simple: if a field would have to change
because the renderer changed, it does not belong here.

## Why `title` is display-only and carries a warning

A report that lists `race-short-014` four times is unreadable, so a human-facing
title earns its place. But a title is also the single most tempting input for
inference - it is right there, it looks descriptive, and a helper that derived
`format_family` from it would be wrong roughly as often as our naming was
casual.

So the title sits on the deliverable, `ContentFeatures` has no access to it, and
nothing in this package reads it except serialisation and the report's display
line. The grep test in the suite is what stops that changing quietly.

## Kinds

`DeliverableKind` covers what section 1 lists - a published video or Short, and
the unpublished things we still measure: a prototype, an experiment render, a
format version. The unpublished kinds are why `published_at` is optional, and
why `is_published` exists rather than callers testing the date themselves: a
prototype with no publication date is not a video whose date we forgot.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .common import (
    assert_deliverable_id,
    assert_instant,
    assert_prose,
    assert_tag,
    optional_instant,
    ref_tuple,
    record_to_dict,
    tag_tuple,
)
from .errors import AnalyticsError
from .genome import ContentFeatures


class DeliverableKind(Enum):
    """What kind of thing is being analysed.

    No COMPETITOR member, for the reason `company/finance/common.py` gives about
    its own subject kinds: the cheapest way to guarantee that somebody else's
    video never becomes one of our analysed deliverables is for our records to
    have no way to name one. A competitor's public numbers reach analytics as a
    `CompetitorPublicReference`, which cannot hold a private metric.
    """

    VIDEO = "video"
    SHORT = "short"
    PROTOTYPE = "prototype"
    EXPERIMENT_RENDER = "experiment_render"
    FORMAT_VERSION = "format_version"


@dataclass(frozen=True)
class AnalyzedDeliverable:
    """One thing we made, as analytics refers to it.

    `format_id` groups deliverables that are the same kind of thing made the
    same way; `version` distinguishes iterations within that. Both are tags
    rather than free text, because both are grouping keys.
    """

    deliverable_id: str
    kind: DeliverableKind
    format_id: str
    version: str = ""
    title: str = ""
    published_at: dt.datetime | None = None
    experiment_id: str = ""
    production_refs: tuple[str, ...] = ()
    features: ContentFeatures = field(default_factory=ContentFeatures)
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "deliverable_id",
            assert_deliverable_id(self.deliverable_id, "deliverable_id"),
        )
        if not isinstance(self.kind, DeliverableKind):
            raise AnalyticsError(
                f"deliverable kind must be a DeliverableKind, got {self.kind!r}. "
                "Known: " + ", ".join(sorted(k.value for k in DeliverableKind))
            )
        object.__setattr__(self, "format_id", assert_tag(self.format_id, "format_id"))
        if self.version:
            object.__setattr__(self, "version", assert_tag(self.version, "version"))
        if self.title:
            object.__setattr__(self, "title", assert_prose(self.title, "title"))
        object.__setattr__(
            self, "published_at", optional_instant(self.published_at, "published_at")
        )
        if self.experiment_id:
            object.__setattr__(
                self,
                "experiment_id",
                assert_deliverable_id(self.experiment_id, "experiment_id"),
            )
        object.__setattr__(
            self, "production_refs", ref_tuple(self.production_refs, "production_refs")
        )
        if not isinstance(self.features, ContentFeatures):
            raise AnalyticsError(
                "features must be a ContentFeatures built from explicitly recorded "
                f"tags, got {type(self.features).__name__}"
            )
        if self.notes:
            object.__setattr__(self, "notes", assert_prose(self.notes, "notes"))
        if self.published_at is None and self.kind in _MUST_BE_PUBLISHED:
            raise AnalyticsError(
                f"a {self.kind.value} is a published thing and must carry "
                "published_at; if it has not gone out yet it is a prototype or an "
                "experiment render, which are separate kinds"
            )

    @property
    def is_published(self) -> bool:
        return self.published_at is not None

    @property
    def group_key(self) -> str:
        """The exact grouping key. Two deliverables group together only if both parts match."""
        return f"{self.format_id}:{self.version}" if self.version else self.format_id

    def age_hours_at(self, instant: dt.datetime) -> float | None:
        """Hours between publication and `instant`, or None if unpublished.

        None rather than zero, because an unpublished deliverable does not have
        an age of nought - it does not have one at all, and a zero here would
        put every prototype reading into the first-hour window.
        """
        if self.published_at is None:
            return None
        moment = assert_instant(instant, "instant")
        if moment < self.published_at:
            raise AnalyticsError(
                f"{self.deliverable_id}: {moment.isoformat()} is before publication at "
                f"{self.published_at.isoformat()}; a reading cannot predate the thing "
                "it measures"
            )
        return (moment - self.published_at).total_seconds() / 3600.0

    def to_dict(self) -> dict[str, Any]:
        data = record_to_dict(self)
        data["kind"] = self.kind.value
        return data

    @classmethod
    def from_dict(cls, data: Any) -> AnalyzedDeliverable:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected a deliverable object, got {data!r}")
        try:
            return cls(
                deliverable_id=data["deliverable_id"],
                kind=DeliverableKind(data["kind"]),
                format_id=data["format_id"],
                version=data.get("version", ""),
                title=data.get("title", ""),
                published_at=data.get("published_at"),
                experiment_id=data.get("experiment_id", ""),
                production_refs=tuple(data.get("production_refs") or ()),
                features=ContentFeatures.from_dict(data.get("features")),
                notes=data.get("notes", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"deliverable: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"deliverable: {exc}") from None


_MUST_BE_PUBLISHED = frozenset({DeliverableKind.VIDEO, DeliverableKind.SHORT})
