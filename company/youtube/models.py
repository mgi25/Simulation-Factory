"""What the artifact says, as records that cannot hold a contradiction.

## These are the fetcher's words, checked rather than trusted

`tools/youtube_fetch/` runs outside Company OS, holds the credentials, talks to
Google, and writes a JSON file. This package reads that file. The two halves
share no code and no process, which is the whole point of the split - but it
also means the artifact is an input from outside, and an input from outside is
validated at the boundary or it is not validated at all.

So every record here re-checks the invariants the fetcher is supposed to
maintain, at construction, and refuses the artifact rather than repairing it. A
metric marked available with no value is not a metric with a missing field: it
is two statements that contradict each other, and there is no way to tell which
one is the lie. The same goes for a subscriber count that is absent with no
reason given, and for an API trace whose endpoint still carries a query string -
that one is a privacy invariant, because a query string is where an access token
travels.

## No `retrieved_at` on a reading

The old connector stamped every normalized record with the instant it was
retrieved. That instant then travelled into the observations built from it, and
two identical pulls became two different records of the same reading. The
artifact carries exactly one fetch instant, at the top, and nothing built from a
reading may read it: `bridge.py` derives `observed_at` from the window the
reading covers. The absence of the field here is what makes that hard to get
wrong later.

## Unavailable is a state, not a zero

`MetricReading` can say a metric is unavailable, and when it does it holds no
value and carries a reason. Nothing in this package converts that to zero, and
nothing can: the value field is None, the record refuses to be built with a
value beside `available=False`, and `bridge.py` produces no observation for it.
Rule 4 of the analytics package - unknown stays unknown - enforced by having
nowhere to put the zero.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from ai_platform.serde import to_jsonable

from .errors import ArtifactRejected

# The API names this version knows how to read. Recorded on the records rather
# than assumed, so an artifact produced by some later endpoint cannot arrive
# wearing the authority of this one.
CHANNEL_SOURCE = "youtube_data_api_v3.channels.list"
VIDEO_SOURCE = "youtube_data_api_v3.videos.list"
ANALYTICS_SOURCE = "youtube_analytics_api_v2.reports.query"

# The only temporal semantics the Analytics API emits here: a bounded window.
# A cumulative total is a different reading off a different endpoint, and
# admitting it silently would turn "views during one week" into "views since
# publication" - the exact confusion `studio_schema.TemporalSemantics` exists
# to prevent.
INTERVAL_SEMANTICS = "interval"


@dataclass(frozen=True)
class ChannelEvidence:
    """The channel the pull was authenticated against, as the Data API reported it."""

    channel_id: str
    channel_title: str
    subscriber_count: int | None
    video_count: int | None
    view_count: int | None
    uploads_playlist_id: str
    subscriber_count_unavailable_reason: str = ""
    source: str = CHANNEL_SOURCE

    def __post_init__(self) -> None:
        _identifier(self.channel_id, "channel.channel_id")
        if (self.subscriber_count is None) != bool(
            self.subscriber_count_unavailable_reason
        ):
            raise ArtifactRejected(
                "channel: a hidden subscriber count carries the reason it is hidden, "
                "and a present one carries no reason. This artifact says "
                f"subscriber_count={self.subscriber_count!r} beside "
                f"{self.subscriber_count_unavailable_reason!r}, which are two "
                "statements that cannot both be true"
            )
        for name in ("subscriber_count", "video_count", "view_count"):
            _optional_count(getattr(self, name), f"channel.{name}")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class VideoEvidence:
    """One video's identity. Not its performance - that is an analytics reading."""

    video_id: str
    channel_id: str
    title: str
    published_at: dt.datetime
    duration: str | None = None
    duration_seconds: int | None = None
    privacy_status: str | None = None
    upload_status: str | None = None
    source: str = VIDEO_SOURCE

    def __post_init__(self) -> None:
        _identifier(self.video_id, "video.video_id")
        _identifier(self.channel_id, "video.channel_id")
        object.__setattr__(
            self, "published_at", _instant(self.published_at, "video.published_at")
        )
        _optional_count(self.duration_seconds, "video.duration_seconds")

    @property
    def production_ref(self) -> str:
        """How analytics refers back to the platform object."""
        return f"youtube:video:{self.video_id}"

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class MetricReading:
    """One metric the Analytics API was asked for, available or explicitly not."""

    name: str
    source_metric: str
    unit: str
    value: float | int | None
    available: bool
    unavailable_reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise ArtifactRejected(
                f"metric {self.name!r}: availability must be a bool, got "
                f"{self.available!r}"
            )
        if self.available and self.value is None:
            raise ArtifactRejected(
                f"metric {self.name!r}: an available metric carries the value that "
                "was read. A metric the API did not report is unavailable, with the "
                "reason recorded, and never a zero"
            )
        if self.available and self.unavailable_reason:
            raise ArtifactRejected(
                f"metric {self.name!r}: an available metric carries no unavailability "
                f"reason, and this one carries {self.unavailable_reason!r}"
            )
        if not self.available:
            if self.value is not None:
                raise ArtifactRejected(
                    f"metric {self.name!r}: an unavailable metric cannot also carry "
                    f"the value {self.value!r}"
                )
            if not self.unavailable_reason:
                raise ArtifactRejected(
                    f"metric {self.name!r}: unavailability needs a reason. 'Not there' "
                    "with no explanation is indistinguishable from nobody having asked"
                )
        if self.value is not None and (
            isinstance(self.value, bool) or not isinstance(self.value, (int, float))
        ):
            raise ArtifactRejected(
                f"metric {self.name!r}: {self.value!r} is not a number. A measurement "
                "that is not a number is a description"
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class AnalyticsEvidence:
    """One `reports.query` row set: one subject, one window, several metrics."""

    channel_id: str
    video_id: str | None
    start_date: dt.date
    end_date: dt.date
    metrics: tuple[MetricReading, ...]
    temporal_semantics: str = INTERVAL_SEMANTICS
    complete: bool = True
    excludes: tuple[str, ...] = ()
    source: str = ANALYTICS_SOURCE

    def __post_init__(self) -> None:
        _identifier(self.channel_id, "analytics.channel_id")
        if self.video_id is not None:
            _identifier(self.video_id, "analytics.video_id")
        object.__setattr__(
            self, "start_date", _day(self.start_date, "analytics.start_date")
        )
        object.__setattr__(self, "end_date", _day(self.end_date, "analytics.end_date"))
        object.__setattr__(self, "metrics", tuple(self.metrics))
        object.__setattr__(self, "excludes", tuple(self.excludes))
        if self.start_date > self.end_date:
            raise ArtifactRejected(
                f"analytics: {self.end_date.isoformat()} is before "
                f"{self.start_date.isoformat()}; that is not a window"
            )
        if self.temporal_semantics != INTERVAL_SEMANTICS:
            raise ArtifactRejected(
                f"analytics: {self.temporal_semantics!r} is not a reading this "
                f"ingester knows how to place in time. Only {INTERVAL_SEMANTICS!r} is "
                "emitted by this version, and a cumulative total imported as an "
                "interval would read as a week's views when it is a lifetime's"
            )
        names = [metric.name for metric in self.metrics]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ArtifactRejected(
                "analytics: the metric(s) " + ", ".join(duplicates) + " appear twice "
                "in one window. Two readings of one metric over one window are a "
                "contradiction, and picking one would be a guess about which"
            )
        if not isinstance(self.complete, bool):
            raise ArtifactRejected(
                f"analytics: completeness must be a bool, got {self.complete!r}"
            )
        if not self.complete and not self.excludes:
            raise ArtifactRejected(
                "analytics: an incomplete reading must say what it excludes, by name. "
                "'Partial' with no description is an unknown with a number attached"
            )

    @property
    def subject_ref(self) -> str:
        """What this row set describes: one video, or the channel as a whole."""
        return (
            f"youtube:video:{self.video_id}"
            if self.video_id
            else f"youtube:channel:{self.channel_id}"
        )

    def metric(self, name: str) -> MetricReading:
        for metric in self.metrics:
            if metric.name == name:
                return metric
        raise KeyError(name)

    @property
    def unavailable(self) -> tuple[MetricReading, ...]:
        return tuple(metric for metric in self.metrics if not metric.available)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class VideoRetrieval:
    """Whether the video list is the whole list, and which ids are missing if not.

    The ids rather than a count, because a count tells a reader that something
    is wrong and nothing about what. `missing_video_ids` is what reaches the
    `DataScope` of every observation built off this artifact, so the gap is
    recorded in the store beside the readings rather than in a log nobody keeps.
    """

    requested: int
    returned: int
    complete: bool = True
    pages_followed: int = 1
    missing_video_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("requested", "returned", "pages_followed"):
            _count(getattr(self, name), f"video_retrieval.{name}")
        object.__setattr__(self, "missing_video_ids", tuple(self.missing_video_ids))
        object.__setattr__(self, "notes", tuple(self.notes))
        if not isinstance(self.complete, bool):
            raise ArtifactRejected(
                f"video_retrieval: completeness must be a bool, got {self.complete!r}"
            )
        if not self.complete and not (self.missing_video_ids or self.notes):
            raise ArtifactRejected(
                "video_retrieval: an incomplete retrieval names the ids it did not "
                "get, or says in words why it stopped. Incompleteness with neither is "
                "a warning nobody can act on"
            )
        if self.complete and (self.missing_video_ids or self.notes):
            raise ArtifactRejected(
                "video_retrieval: a retrieval that is missing ids or carries notes "
                "about what it could not do is not complete, whatever the flag says"
            )

    @property
    def shortfall_sentence(self) -> str:
        """What the gap is, in the words an observation's scope will carry."""
        if not self.missing_video_ids:
            return ""
        return (
            f"videos.list did not return {len(self.missing_video_ids)} of "
            f"{self.requested} requested videos: "
            + ", ".join(self.missing_video_ids)
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class ApiCallTrace:
    """One request the fetcher made, with nothing in it that could identify a caller.

    `endpoint` is scheme, host and path. The query string is stripped by the
    fetcher and refused here if it survived, because that is where an access
    token rides. No headers, no bodies, no response text: the trace answers
    "what did this pull cost and did it work", and nothing else.
    """

    method: str
    endpoint: str
    status: int
    response_bytes: int = 0
    latency_ms: int = 0
    succeeded: bool = True
    error_kind: str = ""

    def __post_init__(self) -> None:
        if "?" in self.endpoint or "#" in self.endpoint:
            raise ArtifactRejected(
                f"api_calls: {self.endpoint!r} still carries a query string. An "
                "endpoint is recorded as scheme, host and path precisely so that an "
                "access_token parameter cannot be written into an evidence record"
            )
        _count(self.status, "api_calls.status")
        _count(self.response_bytes, "api_calls.response_bytes")
        _count(self.latency_ms, "api_calls.latency_ms")
        if not isinstance(self.succeeded, bool):
            raise ArtifactRejected(
                f"api_calls: succeeded must be a bool, got {self.succeeded!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class YouTubeArtifact:
    """One sanitized pull: what was read, under what grant, and how complete it is."""

    artifact_version: int
    producer: str
    producer_version: str
    fetched_at: dt.datetime
    granted_scopes: tuple[str, ...]
    channel: ChannelEvidence
    videos: tuple[VideoEvidence, ...]
    video_retrieval: VideoRetrieval
    analytics: tuple[AnalyticsEvidence, ...] = ()
    api_calls: tuple[ApiCallTrace, ...] = ()
    raw: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "fetched_at", _instant(self.fetched_at, "fetched_at")
        )
        object.__setattr__(self, "granted_scopes", tuple(self.granted_scopes))
        object.__setattr__(self, "videos", tuple(self.videos))
        object.__setattr__(self, "analytics", tuple(self.analytics))
        object.__setattr__(self, "api_calls", tuple(self.api_calls))

    @property
    def channel_ref(self) -> str:
        """Which channel of ours this is, as an analytics reference."""
        return f"youtube:channel:{self.channel.channel_id}"

    @property
    def complete(self) -> bool:
        """Did this pull get everything it asked for, videos and analytics alike?"""
        return self.video_retrieval.complete and all(
            report.complete for report in self.analytics
        )

    def video(self, video_id: str) -> VideoEvidence | None:
        for video in self.videos:
            if video.video_id == video_id:
                return video
        return None

    def normalized(self) -> dict[str, Any]:
        """Everything the APIs reported, without the pull's own telemetry.

        This is what the evidence envelope stores as `normalized` and what the
        semantic digest is taken over, minus the two fields `artifact.py`
        removes there. Kept as one method so the two cannot drift.
        """
        return {
            "artifact_version": self.artifact_version,
            "producer": self.producer,
            "producer_version": self.producer_version,
            "fetched_at": self.fetched_at.isoformat(),
            "granted_scopes": list(self.granted_scopes),
            "channel": self.channel.to_dict(),
            "videos": [video.to_dict() for video in self.videos],
            "video_retrieval": self.video_retrieval.to_dict(),
            "analytics": [report.to_dict() for report in self.analytics],
        }

    def to_dict(self, *, include_raw: bool = False) -> dict[str, Any]:
        data = self.normalized()
        data["api_calls"] = [call.to_dict() for call in self.api_calls]
        if include_raw and self.raw is not None:
            data["raw"] = self.raw
        return data


def _instant(value: Any, field_name: str) -> dt.datetime:
    """A timezone-aware moment, normalised to UTC. A naive one is refused."""
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            value = dt.datetime.fromisoformat(text)
        except ValueError as exc:
            raise ArtifactRejected(
                f"{field_name}: {value!r} is not an ISO 8601 timestamp: {exc}"
            ) from exc
    if not isinstance(value, dt.datetime):
        raise ArtifactRejected(
            f"{field_name}: expected a timestamp, got {type(value).__name__}"
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ArtifactRejected(
            f"{field_name}: {value.isoformat()} has no timezone. The same wall clock "
            "is a different instant in every office that reports it"
        )
    return value.astimezone(dt.timezone.utc)


def _day(value: Any, field_name: str) -> dt.date:
    """A calendar day. A datetime is refused rather than truncated to its date."""
    if isinstance(value, dt.datetime):
        raise ArtifactRejected(
            f"{field_name}: {value.isoformat()} is an instant, and a window boundary "
            "is a day. Truncating it here would silently move the boundary for every "
            "timezone east of UTC"
        )
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ArtifactRejected(
                f"{field_name}: {value!r} is not an ISO 8601 date: {exc}"
            ) from exc
    raise ArtifactRejected(
        f"{field_name}: expected a date, got {type(value).__name__}"
    )


def _identifier(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactRejected(
            f"{field_name}: a platform id is required, got {value!r}. A title is "
            "never an identity, because it can change without the thing changing"
        )
    return value


def _count(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ArtifactRejected(
            f"{field_name}: expected a whole non-negative count, got {value!r}"
        )
    return value


def _optional_count(value: Any, field_name: str) -> int | None:
    return None if value is None else _count(value, field_name)


__all__ = [
    "ANALYTICS_SOURCE",
    "CHANNEL_SOURCE",
    "INTERVAL_SEMANTICS",
    "VIDEO_SOURCE",
    "AnalyticsEvidence",
    "ApiCallTrace",
    "ChannelEvidence",
    "MetricReading",
    "VideoEvidence",
    "VideoRetrieval",
    "YouTubeArtifact",
]
