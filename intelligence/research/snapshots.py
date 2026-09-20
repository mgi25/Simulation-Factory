"""Public numbers, dated, never overwritten - and the numbers we refuse to hold.

`PublicMetrics` in `sources.py` is one reading of a public page. This module is
what happens when somebody reads the page again next month.

## An observation is not an update

A view count is not a property of a video, it is a property of a video *on a
day*. Writing the new number over the old one destroys the only thing two
readings are good for, which is the difference between them. So a
`SnapshotSeries` appends, a duplicate reading is refused rather than merged,
and growth is a function of two snapshots rather than a field on one.

## The series is also the deduplication index

Its id is derived from the `ContentIdentity` - `platform` plus a digest of the
identity key - so the file name *is* the identity. Looking up "have we seen
this video before" is therefore opening one file by name, not scanning a
directory and comparing titles. A series carrying no snapshots is legitimate
and common: we found the video, nobody has recorded its numbers yet.

The id cannot be the external id, because record ids are filenames and
filenames here are lowercase; YouTube ids are case-sensitive, so `aB` and `Ab`
would collide into one candidate. The digest preserves the distinction, and the
platform prefix keeps the directory readable.

## What a snapshot may not contain

`PRIVATE_METRIC_FIELDS` is `NEVER_KNOWABLE` from `sources.py` plus the names
those metrics travel under in exports and spreadsheets. Any of them arriving in
an ingestion payload is refused by name, and `SourceQuality.FIRST_PARTY` is
refused on a public snapshot outright: a reading of a public surface is not
analytics, and the system has no authenticated channel data to be confused with
it. When that system exists it will be a different record type with a different
rights story, not a `note` field on this one.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar

from ai_platform.serde import fingerprint
from intelligence.research.common import (
    Evidence,
    SourceQuality,
    assert_research_id,
    assert_text,
)
from intelligence.research.errors import ResearchError
from intelligence.research.provenance import CaptureMethod
from intelligence.research.sources import NEVER_KNOWABLE, PublicMetrics
from intelligence.research.urls import ContentIdentity, assert_known_platform

PRIVATE_METRIC_FIELDS: tuple[str, ...] = NEVER_KNOWABLE + (
    "audience_retention",
    "average_view_percentage",
    "average_views_per_viewer",
    "cpm",
    "demographics",
    "estimated_revenue",
    "impressions",
    "impressions_click_through_rate",
    "returning_viewers",
    "revenue",
    "rpm",
    "subscriber_conversion",
    "subscribers_gained",
    "unique_viewers",
    "watch_time",
    "watch_time_hours",
)
"""Metric names a competitor's public page cannot show, under the names they
travel under. Section 5 of the phase brief: research on somebody else's channel
must not pretend it has these."""

_PRIVATE_STEMS: tuple[str, ...] = (
    "average_view",
    "click_through",
    "cpm",
    "demographic",
    "impression",
    "monetization",
    "percentage_viewed",
    "retention",
    "revenue",
    "rpm",
    "subscriber_conversion",
    "traffic_source",
    "unique_viewer",
    "watch_time",
)
"""Stems, so a renamed column is caught too. Held narrow on purpose:
`channel_subscribers` is public and must survive every one of them."""


def _normalise_metric_name(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in str(name).strip().lower())


def assert_public_metric_name(name: str, field: str) -> str:
    """Refuse a private channel analytic arriving as a public metric.

    The message names the alternative rather than only the prohibition, because
    the honest case - our own channel, our own analytics - is a real thing that
    this system genuinely cannot hold yet.
    """
    normalised = _normalise_metric_name(name)
    if normalised in {_normalise_metric_name(f) for f in PRIVATE_METRIC_FIELDS} or any(
        stem in normalised for stem in _PRIVATE_STEMS
    ):
        raise ResearchError(
            f"{field}: {name!r} is a private channel analytic. No public page shows it "
            "for somebody else's video, so a value here would be an inference wearing "
            "the clothes of an observation. Only our own authenticated channel data "
            "could carry it, and that is a separate system which does not exist yet."
        )
    return name


@dataclass(frozen=True)
class PublicSnapshot:
    """One dated reading of a public page, with what proves somebody read it.

    The numbers live in `PublicMetrics` (rule 15 - one source of truth for the
    shape of a public reading); this adds who read it, how, and the evidence
    pointer that makes the reading checkable.
    """

    metrics: PublicMetrics
    capture_method: CaptureMethod
    evidence: Evidence
    captured_by: str = ""
    source_quality: SourceQuality = SourceQuality.PLATFORM_PUBLIC
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.metrics, PublicMetrics):
            raise ResearchError("a public snapshot holds a PublicMetrics reading")
        if not isinstance(self.capture_method, CaptureMethod):
            raise ResearchError(
                "a public snapshot must say how it was captured; a number with no "
                "capture method does not say whether a human read the page or not"
            )
        if not isinstance(self.evidence, Evidence):
            raise ResearchError(
                "a public snapshot requires an Evidence pointer. Externally captured "
                "metrics are claims about a page on a day; without something a reader "
                "can check, the claim is unsourced."
            )
        if self.source_quality is SourceQuality.FIRST_PARTY:
            raise ResearchError(
                "a public snapshot is a reading of a public surface, not first-party "
                "analytics. Our own authenticated channel data belongs in a separate "
                "system with its own rights story, not in a competitor research record."
            )

    @property
    def observed_on(self) -> dt.date:
        return self.metrics.observed_on

    @property
    def key(self) -> tuple[str, str, str]:
        """Two snapshots with this key are one reading recorded twice."""
        return (
            self.metrics.observed_on.isoformat(),
            self.capture_method.value,
            self.evidence.ref,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublicSnapshot:
        return cls(
            metrics=PublicMetrics.from_dict(data["metrics"]),
            capture_method=CaptureMethod(data["capture_method"]),
            evidence=Evidence.from_dict(data["evidence"]),
            captured_by=data.get("captured_by", ""),
            source_quality=SourceQuality(data.get("source_quality", "platform_public")),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class PublicGrowth:
    """The difference between two readings, and what it could not be computed from.

    Every field that could not be derived is named in `unavailable` with the
    input that was missing, the same refusal `derive()` makes for a single
    snapshot. There is no growth rate over zero days and none from a count
    nobody recorded.
    """

    from_on: dt.date
    to_on: dt.date
    days: int
    views_gained: int | None = None
    views_per_day: float | None = None
    likes_gained: int | None = None
    comments_gained: int | None = None
    unavailable: tuple[str, ...] = ()
    never_knowable: tuple[str, ...] = NEVER_KNOWABLE


def growth_between(earlier: PublicSnapshot, later: PublicSnapshot) -> PublicGrowth:
    """Difference two readings. Pure, and silent about nothing.

    A negative gain is reported rather than refused: platforms revise counts
    downward, and a research store that cannot record that will quietly lose
    the one observation worth having.
    """
    if later.observed_on < earlier.observed_on:
        raise ResearchError(
            f"growth_between: {later.observed_on} is before {earlier.observed_on}; "
            "pass the readings in the order they were taken"
        )
    days = (later.observed_on - earlier.observed_on).days
    missing: list[str] = []

    gains: dict[str, int | None] = {}
    for field in ("views", "likes", "comments"):
        before = getattr(earlier.metrics, field)
        after = getattr(later.metrics, field)
        if before is None or after is None:
            which = "both readings" if before is None and after is None else (
                "the earlier reading" if before is None else "the later reading"
            )
            missing.append(f"{field}_gained: {field} not observed in {which}")
            gains[field] = None
        else:
            gains[field] = after - before

    views_per_day: float | None = None
    if gains["views"] is None:
        missing.append("views_per_day: view count not observed in both readings")
    elif days < 1:
        missing.append("views_per_day: both readings are from the same day")
    else:
        views_per_day = round(gains["views"] / days, 6)

    return PublicGrowth(
        from_on=earlier.observed_on,
        to_on=later.observed_on,
        days=days,
        views_gained=gains["views"],
        views_per_day=views_per_day,
        likes_gained=gains["likes"],
        comments_gained=gains["comments"],
        unavailable=tuple(missing),
    )


def series_id(identity: ContentIdentity) -> str:
    """The filename for one piece of external content. Deterministic.

    `platform-<digest>`: readable enough to scan a directory, and a digest
    rather than the external id because record ids are lowercase filenames and
    YouTube ids are case-sensitive.
    """
    return f"{identity.platform}-{fingerprint(identity.key)}"


@dataclass(frozen=True)
class SnapshotSeries:
    """One piece of external content, every public reading of it, and who is watching.

    Doubles as the deduplication index: `id` is derived from the identity, so
    "have we seen this before" is one file lookup. `candidate_ids` and
    `source_ids` are how a promoted candidate keeps its history - the series
    outlives the candidate, so promotion copies no numbers anywhere.
    """

    kind: ClassVar[str] = "snapshot_series"

    id: str
    platform: str
    canonical_url: str
    external_id: str = ""
    snapshots: tuple[PublicSnapshot, ...] = ()
    candidate_ids: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert_research_id(self.id, "snapshot series")
        assert_known_platform(self.platform, "series platform")
        assert_text(self.canonical_url, "series canonical_url")
        expected = series_id(self.identity)
        if self.id != expected:
            raise ResearchError(
                f"snapshot series id {self.id!r} does not match its own identity "
                f"{self.identity.key!r}, which is {expected!r}. The id is derived, not "
                "chosen - a hand-written one would break the deduplication index."
            )
        object.__setattr__(self, "snapshots", tuple(self.snapshots))
        seen: set[tuple[str, str, str]] = set()
        for snapshot in self.snapshots:
            if not isinstance(snapshot, PublicSnapshot):
                raise ResearchError(f"series {self.id!r}: not a PublicSnapshot")
            if snapshot.key in seen:
                raise ResearchError(
                    f"series {self.id!r}: two snapshots share {snapshot.key}. One "
                    "reading recorded twice is not two observations."
                )
            seen.add(snapshot.key)
        if list(self.snapshots) != sorted(self.snapshots, key=lambda s: s.key):
            raise ResearchError(
                f"series {self.id!r}: snapshots must be stored oldest first, so the "
                "file is the same two bytes whichever session wrote it"
            )
        for field in ("candidate_ids", "source_ids"):
            values = tuple(getattr(self, field))
            for value in values:
                assert_research_id(value, field.rstrip("s"))
            if len(set(values)) != len(values):
                raise ResearchError(f"series {self.id!r}: duplicate id in {field}")
            object.__setattr__(self, field, values)

    @property
    def identity(self) -> ContentIdentity:
        return ContentIdentity(
            platform=self.platform,
            external_id=self.external_id,
            canonical_url=self.canonical_url,
        )

    @property
    def latest(self) -> PublicSnapshot | None:
        return self.snapshots[-1] if self.snapshots else None

    @property
    def observed_days(self) -> tuple[dt.date, ...]:
        return tuple(s.observed_on for s in self.snapshots)

    def add(self, snapshot: PublicSnapshot) -> SnapshotSeries:
        """Append a reading. Refuses one already recorded; never replaces one."""
        if any(existing.key == snapshot.key for existing in self.snapshots):
            raise ResearchError(
                f"series {self.id!r} already holds the reading {snapshot.key}. A public "
                "metric is an observation of a day - record a new day, or cite "
                "different evidence, but do not overwrite what was seen."
            )
        merged = sorted((*self.snapshots, snapshot), key=lambda s: s.key)
        return SnapshotSeries(
            id=self.id,
            platform=self.platform,
            canonical_url=self.canonical_url,
            external_id=self.external_id,
            snapshots=tuple(merged),
            candidate_ids=self.candidate_ids,
            source_ids=self.source_ids,
        )

    def watching(self, *, candidate_id: str = "", source_id: str = "") -> SnapshotSeries:
        """Record that a candidate or a source is anchored on this content."""
        candidates = self.candidate_ids
        sources = self.source_ids
        if candidate_id and candidate_id not in candidates:
            candidates = (*candidates, candidate_id)
        if source_id and source_id not in sources:
            sources = (*sources, source_id)
        return SnapshotSeries(
            id=self.id,
            platform=self.platform,
            canonical_url=self.canonical_url,
            external_id=self.external_id,
            snapshots=self.snapshots,
            candidate_ids=candidates,
            source_ids=sources,
        )

    def growth(self) -> PublicGrowth | None:
        """Oldest reading to newest, or None when there is only one reading."""
        if len(self.snapshots) < 2:
            return None
        return growth_between(self.snapshots[0], self.snapshots[-1])

    @classmethod
    def for_identity(cls, identity: ContentIdentity, **kwargs: Any) -> SnapshotSeries:
        """Build an empty series for a piece of content. The normal entry point."""
        return cls(
            id=series_id(identity),
            platform=identity.platform,
            canonical_url=identity.canonical_url,
            external_id=identity.external_id,
            **kwargs,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SnapshotSeries:
        return cls(
            id=data["id"],
            platform=data["platform"],
            canonical_url=data["canonical_url"],
            external_id=data.get("external_id", ""),
            snapshots=tuple(PublicSnapshot.from_dict(s) for s in data.get("snapshots", ())),
            candidate_ids=tuple(data.get("candidate_ids", ())),
            source_ids=tuple(data.get("source_ids", ())),
        )
