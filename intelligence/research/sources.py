"""What we found, where it is, what we may keep of it, and what we cannot know.

A `ResearchSource` is one external thing a researcher noticed: a competitor
video, a channel, an article, a platform changelog. It is the anchor of a
research thread - the reference cases and opportunity dossiers that follow all
point back at one.

## Rights are a status, not an intention

`RightsStatus` is the brief's section 2, and its four values are ordered by how
much of the source we hold:

    METADATA_ONLY            we recorded facts about it and nothing else
    LINK_ONLY                we hold a URL; the bytes stay where they are
    LOCAL_COPY_USER_PROVIDED the CEO supplied a file
    LOCAL_COPY_AUTHORIZED    a licence or an explicit permission covers a copy

The two copy statuses require a `local_copy_ref` *and* a `rights_basis` naming
who authorised it. The two non-copy statuses refuse a `local_copy_ref`
outright. That pair of rules is the whole anti-downloader design: there is no
status a caller can set that means "we have the file and nobody said we could",
so a downloader would have nowhere to write its result. Nothing in this package
fetches anything - the store is designed to work perfectly with a URL and a
handful of public numbers, which is the normal case.

## Public metrics are observations

`PublicMetrics` holds what a logged-out viewer can read off a page: views,
likes, comments, duration, subscriber count. Every field is optional, because
platforms hide different things on different days, and a metric nobody could
see is `None` rather than zero.

`NEVER_KNOWABLE` lists what public data structurally cannot tell us about
somebody else's video - retention curve, average percentage viewed, revenue,
traffic sources, and the causal reason a video performed. It is exposed as
`private_analytics_unavailable` on every source so the limitation travels with
the record instead of living in a README nobody re-reads. The brief's section
13 asks for exactly this, and `derive()` is where it would otherwise be
violated.

## Derivation refuses to invent

`derive()` returns a `DerivedMetrics` in which every ratio it could not compute
is `None` and is *named* in `unavailable`, with the input that was missing. It
is a pure function of the snapshot plus the publication date. There is no
`views_per_day` when the publication date is unknown, no engagement ratio when
views are zero, and no retention at any time.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar

from ai_platform.serde import as_date, as_opt_date, as_tuple
from intelligence.research.common import (
    ResearchConfidence,
    assert_reference,
    assert_research_id,
    assert_slug,
    assert_text,
    evidence_tuple,
)
from intelligence.research.errors import ResearchError
from intelligence.research.lifecycle import ResearchStage, StageTransition
from knowledge.company_os.records import Evidence

NEVER_KNOWABLE: tuple[str, ...] = (
    "audience_retention_curve",
    "average_percentage_viewed",
    "average_view_duration",
    "click_through_rate",
    "monetization_and_revenue",
    "traffic_sources",
    "causal_reason_for_performance",
)
"""What public data cannot tell us about somebody else's video.

Not a TODO list. These are private to the channel that owns the video, and a
research system that leaves room for them will eventually have one filled in by
inference. Recording them as permanently unavailable is the honest shape.
"""


class RightsStatus(Enum):
    METADATA_ONLY = "metadata_only"
    LINK_ONLY = "link_only"
    LOCAL_COPY_USER_PROVIDED = "local_copy_user_provided"
    LOCAL_COPY_AUTHORIZED = "local_copy_authorized"


COPY_STATUSES: frozenset[RightsStatus] = frozenset(
    {RightsStatus.LOCAL_COPY_USER_PROVIDED, RightsStatus.LOCAL_COPY_AUTHORIZED}
)


class SourceType(Enum):
    """Our taxonomy of what a source *is* - unlike `platform`, which is theirs."""

    COMPETITOR_VIDEO = "competitor_video"
    OWN_VIDEO = "own_video"
    CHANNEL = "channel"
    PLAYLIST = "playlist"
    ARTICLE = "article"
    PLATFORM_DOCUMENTATION = "platform_documentation"
    COMMUNITY_DISCUSSION = "community_discussion"
    DATASET = "dataset"
    OTHER = "other"


@dataclass(frozen=True)
class PublicMetrics:
    """One snapshot of a public surface, on one day. Every field optional.

    `observed_on` is required and the rest are not, because the record's job is
    to say *when someone looked*, and a snapshot with nothing in it still says
    that the page showed nothing. Counts may not be negative; a hidden count is
    `None`.
    """

    observed_on: dt.date
    views: int | None = None
    likes: int | None = None
    comments: int | None = None
    duration_seconds: int | None = None
    channel_subscribers: int | None = None
    note: str = ""

    _COUNTS: ClassVar[tuple[str, ...]] = ("views", "likes", "comments", "duration_seconds", "channel_subscribers")

    def __post_init__(self) -> None:
        if not isinstance(self.observed_on, dt.date):
            raise ResearchError("public metrics must record the date they were observed")
        for field in self._COUNTS:
            value = getattr(self, field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ResearchError(f"{field} must be a whole number or None, got {value!r}")
            if value < 0:
                raise ResearchError(f"{field} cannot be negative, got {value}")

    @property
    def present(self) -> tuple[str, ...]:
        return tuple(f for f in self._COUNTS if getattr(self, f) is not None)

    @property
    def absent(self) -> tuple[str, ...]:
        return tuple(f for f in self._COUNTS if getattr(self, f) is None)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PublicMetrics:
        return cls(
            observed_on=as_date(data["observed_on"], "observed_on"),
            views=data.get("views"),
            likes=data.get("likes"),
            comments=data.get("comments"),
            duration_seconds=data.get("duration_seconds"),
            channel_subscribers=data.get("channel_subscribers"),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class DerivedMetrics:
    """Ratios that the inputs actually supported, and a list of the ones missing.

    `unavailable` names each metric that could not be computed and the input
    that was absent. A reader therefore sees the difference between "engagement
    is low" and "we never saw the like count", which is the difference the
    brief's section 8 is asking for.

    `never_knowable` repeats `NEVER_KNOWABLE` into the serialized object on
    purpose: a derived-metrics blob read six months from now should not need
    this module in scope to know what it is not allowed to contain.
    """

    age_days: int | None = None
    views_per_day: float | None = None
    likes_per_1k_views: float | None = None
    comments_per_1k_views: float | None = None
    unavailable: tuple[str, ...] = ()
    never_knowable: tuple[str, ...] = NEVER_KNOWABLE

    DERIVABLE: ClassVar[tuple[str, ...]] = ("age_days", "views_per_day", "likes_per_1k_views", "comments_per_1k_views")

    @property
    def computed(self) -> tuple[str, ...]:
        return tuple(name for name in self.DERIVABLE if getattr(self, name) is not None)

    @property
    def missing(self) -> tuple[str, ...]:
        return tuple(name for name in self.DERIVABLE if getattr(self, name) is None)


def _round(value: float) -> float:
    """Six decimals, so two machines agree on the text of the same ratio."""
    return round(value, 6)


def derive(
    metrics: PublicMetrics | None,
    published_on: dt.date | None,
    *,
    as_of: dt.date | None = None,
) -> DerivedMetrics:
    """Compute only what the inputs support; name everything else as missing.

    `as_of` defaults to the snapshot's own observation date rather than today,
    so a derivation is a property of the snapshot and re-running it next month
    returns the same numbers.
    """
    if metrics is None:
        return DerivedMetrics(
            unavailable=(
                "age_days: no metrics snapshot",
                "views_per_day: no metrics snapshot",
                "likes_per_1k_views: no metrics snapshot",
                "comments_per_1k_views: no metrics snapshot",
            )
        )

    when = as_of or metrics.observed_on
    missing: list[str] = []

    age_days: int | None = None
    if published_on is None:
        missing.append("age_days: publication date unknown")
    elif published_on > when:
        missing.append("age_days: publication date is after the observation date")
    else:
        age_days = (when - published_on).days

    views_per_day: float | None = None
    if metrics.views is None:
        missing.append("views_per_day: view count not observed")
    elif age_days is None:
        missing.append("views_per_day: age unknown")
    elif age_days < 1:
        missing.append("views_per_day: less than one full day of exposure")
    else:
        views_per_day = _round(metrics.views / age_days)

    likes_per_1k: float | None = None
    comments_per_1k: float | None = None
    if metrics.views is None:
        missing.append("likes_per_1k_views: view count not observed")
        missing.append("comments_per_1k_views: view count not observed")
    elif metrics.views == 0:
        missing.append("likes_per_1k_views: zero views, no ratio exists")
        missing.append("comments_per_1k_views: zero views, no ratio exists")
    else:
        if metrics.likes is None:
            missing.append("likes_per_1k_views: like count not observed")
        else:
            likes_per_1k = _round(1000.0 * metrics.likes / metrics.views)
        if metrics.comments is None:
            missing.append("comments_per_1k_views: comment count not observed")
        else:
            comments_per_1k = _round(1000.0 * metrics.comments / metrics.views)

    return DerivedMetrics(
        age_days=age_days,
        views_per_day=views_per_day,
        likes_per_1k_views=likes_per_1k,
        comments_per_1k_views=comments_per_1k,
        unavailable=tuple(missing),
    )


@dataclass(frozen=True)
class ResearchSource:
    """One external thing we noticed, and the thread that grows out of it.

    `stage` and `history` make this the anchor of the lifecycle in
    `lifecycle.py`: the reference cases and dossiers that follow are linked
    from here, and the stage cannot advance past them without them. See
    `lifecycle.advance_source`.
    """

    kind: ClassVar[str] = "source"

    id: str
    platform: str
    reference: str
    title: str
    source_type: SourceType
    observed_on: dt.date
    rights: RightsStatus
    confidence: ResearchConfidence
    discovered_by: str
    creator: str = ""
    published_on: dt.date | None = None
    metrics: PublicMetrics | None = None
    local_copy_ref: str = ""
    rights_basis: str = ""
    notes: str = ""
    tags: tuple[str, ...] = ()
    stage: ResearchStage = ResearchStage.DISCOVERED
    history: tuple[StageTransition, ...] = ()
    reference_case_ids: tuple[str, ...] = ()
    opportunity_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert_research_id(self.id, "source")
        assert_slug(self.platform, "platform")
        assert_reference(self.reference, "source reference")
        assert_text(self.title, "source title")
        assert_text(self.discovered_by, "discovered_by")
        if not isinstance(self.observed_on, dt.date):
            raise ResearchError("a source must record the date it was observed")
        if self.published_on is not None and self.published_on > self.observed_on:
            raise ResearchError(
                f"source {self.id!r}: published_on {self.published_on} is after "
                f"observed_on {self.observed_on}"
            )
        if self.metrics is not None and self.metrics.observed_on < self.observed_on:
            raise ResearchError(
                f"source {self.id!r}: the metrics snapshot predates the source's own "
                "observation date - record the snapshot under the day it was taken"
            )
        object.__setattr__(self, "tags", tuple(assert_slug(t, "source tag") for t in self.tags))

        if self.rights in COPY_STATUSES:
            if not self.local_copy_ref.strip():
                raise ResearchError(
                    f"source {self.id!r}: rights {self.rights.value!r} claims a local copy "
                    "but names no local_copy_ref. Point at the file, or use link_only."
                )
            assert_reference(self.local_copy_ref, "local_copy_ref")
            if not self.rights_basis.strip():
                raise ResearchError(
                    f"source {self.id!r}: rights {self.rights.value!r} requires a "
                    "rights_basis naming who authorised the copy. Nothing in this "
                    "package fetches media; a copy exists because a person supplied it."
                )
        elif self.local_copy_ref.strip():
            raise ResearchError(
                f"source {self.id!r}: rights {self.rights.value!r} holds no local copy, "
                f"yet local_copy_ref is set to {self.local_copy_ref!r}. Set the rights "
                "status that matches what we actually hold."
            )

        for field, prefix in (("reference_case_ids", "reference_case"), ("opportunity_ids", "opportunity")):
            ids = as_tuple(getattr(self, field))
            for value in ids:
                assert_research_id(value, prefix)
            if len(set(ids)) != len(ids):
                raise ResearchError(f"source {self.id!r}: duplicate id in {field}")
            object.__setattr__(self, field, ids)

        if self.history:
            expected = ResearchStage.DISCOVERED
            for step in self.history:
                if step.from_stage is not expected:
                    raise ResearchError(
                        f"source {self.id!r}: history jumps from {expected.value!r} to a "
                        f"transition that starts at {step.from_stage.value!r}"
                    )
                expected = step.to_stage
            if expected is not self.stage:
                raise ResearchError(
                    f"source {self.id!r}: history ends at {expected.value!r} but stage is "
                    f"{self.stage.value!r}"
                )
        elif self.stage is not ResearchStage.DISCOVERED:
            raise ResearchError(
                f"source {self.id!r}: stage {self.stage.value!r} with no history. Use "
                "lifecycle.advance_source so every stage change records who and why."
            )

    @property
    def private_analytics_unavailable(self) -> tuple[str, ...]:
        """What we do not and will not know about this source.

        Empty for our own videos, where first-party analytics exist elsewhere.
        For anybody else's, this is the permanent list.
        """
        if self.source_type is SourceType.OWN_VIDEO:
            return ()
        return NEVER_KNOWABLE

    @property
    def holds_local_copy(self) -> bool:
        return self.rights in COPY_STATUSES

    def derived(self, *, as_of: dt.date | None = None) -> DerivedMetrics:
        return derive(self.metrics, self.published_on, as_of=as_of)

    def with_metrics(self, metrics: PublicMetrics) -> ResearchSource:
        """Attach a newer snapshot. The old one is not merged into the new one."""
        return replace(self, metrics=metrics)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResearchSource:
        return cls(
            id=data["id"],
            platform=data["platform"],
            reference=data["reference"],
            title=data["title"],
            source_type=SourceType(data["source_type"]),
            observed_on=as_date(data["observed_on"], "observed_on"),
            rights=RightsStatus(data["rights"]),
            confidence=ResearchConfidence.from_dict(data["confidence"]),
            discovered_by=data["discovered_by"],
            creator=data.get("creator", ""),
            published_on=as_opt_date(data.get("published_on"), "published_on"),
            metrics=(
                None if data.get("metrics") is None else PublicMetrics.from_dict(data["metrics"])
            ),
            local_copy_ref=data.get("local_copy_ref", ""),
            rights_basis=data.get("rights_basis", ""),
            notes=data.get("notes", ""),
            tags=as_tuple(data.get("tags")),
            stage=ResearchStage(data.get("stage", "discovered")),
            history=tuple(StageTransition.from_dict(h) for h in data.get("history", ())),
            reference_case_ids=as_tuple(data.get("reference_case_ids")),
            opportunity_ids=as_tuple(data.get("opportunity_ids")),
        )


def observation_evidence(source: ResearchSource, note: str = "") -> Evidence:
    """The `Evidence` pointer a downstream record uses to cite this source."""
    return Evidence(kind="observation", ref=source.reference, note=note or source.title)
