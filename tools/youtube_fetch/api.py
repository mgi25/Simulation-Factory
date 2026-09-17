"""Reading the two YouTube APIs, and refusing to round a gap down to zero.

## A page is not a result, and fifty ids is not a list

`playlistItems.list` returns at most fifty items and a `nextPageToken`, and
`videos.list` accepts at most fifty ids per call. A reader that issues one call
for each and stops has not fetched "the recent videos" - it has fetched whatever
fitted in one page, and it says nothing about the difference. That silence is
the failure mode worth designing against, because the artifact it produces looks
exactly like a complete one.

So `recent_videos` follows `nextPageToken` until it has the requested number of
ids or the playlist is exhausted, chunks the id list into calls of at most
fifty, and then compares what it asked for against what came back. Any id that
`videos.list` did not return is recorded - the exact id, not a count - and the
listing is marked incomplete with a sentence saying why. Downstream, that
becomes a `DataScope` with a populated `excludes`; a count would become a
`DataScope` nobody can act on.

## An absent metric is absent, not zero

The Analytics API answers a query with no data by returning no rows. Reading
that as zeros produces numbers that are wrong in the most expensive possible
way: a zero looks like a measurement, survives every validator, and sits in a
chart next to real values. `MetricReading` therefore carries `available` and a
reason, and its value is `None` whenever `available` is false. Nothing in this
package can turn "we did not get this" into "this was zero".

## Failures become types here, before they leave

`_request` maps the provider's vocabulary onto this package's exceptions, once,
at the boundary. A 403 carries a `reason` in `error.errors[]` and the three that
matter mean three different things to an operator: `quotaExceeded` means wait,
`insufficientPermissions` means re-authorize, anything else means read the
message. A 401 means the bearer token went stale, which is worth exactly one
forced refresh; a second 401 is an authorization problem and pretending
otherwise would loop.

A 401 on page two of a paginated walk therefore aborts the whole fetch rather
than returning the pages already collected. Half a listing that presents itself
as a listing is the same defect as a zero that presents itself as a measurement.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.parse import urlencode

from .errors import (
    ApiError,
    AuthorizationError,
    InsufficientPermissions,
    QuotaExceeded,
)
from .oauth import OAuthClient
from .secrets_ import SecretRedactor
from .transport import HttpResponse, InstrumentedTransport


DATA_ROOT = "https://www.googleapis.com/youtube/v3"
ANALYTICS_ROOT = "https://youtubeanalytics.googleapis.com/v2"

CHANNELS_SOURCE = "youtube_data_api_v3.channels.list"
PLAYLIST_ITEMS_SOURCE = "youtube_data_api_v3.playlistItems.list"
VIDEOS_SOURCE = "youtube_data_api_v3.videos.list"
ANALYTICS_SOURCE = "youtube_analytics_api_v2.reports.query"

# Both APIs cap a page at fifty. The constant is named rather than inlined
# because the pagination and the chunking are the same limit seen twice.
MAX_PAGE_SIZE = 50

# (artifact name, API metric, unit, factor applied here).
# The factor exists so the artifact carries a value in the unit it names:
# averageViewPercentage arrives as 45.6 meaning 45.6%, and a "fraction" that
# reads 45.6 is a number waiting to be multiplied twice.
METRIC_TABLE: tuple[tuple[str, str, str, float], ...] = (
    ("views", "views", "views", 1.0),
    ("estimated_minutes_watched", "estimatedMinutesWatched", "minutes", 1.0),
    ("average_view_duration_seconds", "averageViewDuration", "seconds", 1.0),
    ("average_view_percentage", "averageViewPercentage", "fraction", 0.01),
    ("subscribers_gained", "subscribersGained", "subscribers", 1.0),
    ("subscribers_lost", "subscribersLost", "subscribers", 1.0),
    ("likes", "likes", "likes", 1.0),
    ("comments", "comments", "comments", 1.0),
    ("shares", "shares", "shares", 1.0),
)
ANALYTICS_API_METRICS: tuple[str, ...] = tuple(row[1] for row in METRIC_TABLE)

NO_ROWS_REASON = "API returned no rows for the requested range"
OMITTED_REASON = "API omitted this metric from the response"
NON_NUMERIC_REASON = "API returned a non-numeric value for this metric"


@dataclass(frozen=True)
class ChannelFacts:
    """The authenticated channel, as the Data API describes it."""

    channel_id: str
    channel_title: str
    subscriber_count: int | None
    subscriber_count_unavailable_reason: str
    video_count: int | None
    view_count: int | None
    uploads_playlist_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "channel_id": self.channel_id,
            "channel_title": self.channel_title,
            "subscriber_count": self.subscriber_count,
            "subscriber_count_unavailable_reason": self.subscriber_count_unavailable_reason,
            "video_count": self.video_count,
            "view_count": self.view_count,
            "uploads_playlist_id": self.uploads_playlist_id,
            "source": CHANNELS_SOURCE,
        }


@dataclass(frozen=True)
class ChannelResult:
    """The normalized channel and the response it was read from."""

    facts: ChannelFacts
    raw: dict[str, Any]


@dataclass(frozen=True)
class VideoFacts:
    """One upload, with the identity and status fields ingestion needs."""

    video_id: str
    channel_id: str
    title: str
    published_at: str
    duration: str | None
    duration_seconds: int | None
    privacy_status: str | None
    upload_status: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "video_id": self.video_id,
            "channel_id": self.channel_id,
            "title": self.title,
            "published_at": self.published_at,
            "duration": self.duration,
            "duration_seconds": self.duration_seconds,
            "privacy_status": self.privacy_status,
            "upload_status": self.upload_status,
            "source": VIDEOS_SOURCE,
        }


@dataclass(frozen=True)
class VideoListing:
    """What was asked for, what came back, and the exact difference between them."""

    requested: int
    videos: tuple[VideoFacts, ...]
    playlist_video_ids: tuple[str, ...]
    missing_video_ids: tuple[str, ...]
    pages_followed: int
    notes: tuple[str, ...]
    raw_playlist_pages: tuple[dict[str, Any], ...] = ()
    raw_video_pages: tuple[dict[str, Any], ...] = ()

    @property
    def complete(self) -> bool:
        return not self.missing_video_ids and not self.notes

    def retrieval_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "returned": len(self.videos),
            "complete": self.complete,
            "pages_followed": self.pages_followed,
            "missing_video_ids": list(self.missing_video_ids),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class MetricReading:
    """One metric, or one stated absence. Never a zero standing in for either."""

    name: str
    source_metric: str
    unit: str
    value: float | int | None
    available: bool
    unavailable_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_metric": self.source_metric,
            "unit": self.unit,
            "value": self.value,
            "available": self.available,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class AnalyticsReport:
    """One reports.query answer over one closed date interval."""

    channel_id: str
    video_id: str | None
    start_date: dt.date
    end_date: dt.date
    metrics: tuple[MetricReading, ...]
    raw: dict[str, Any]

    @property
    def excludes(self) -> tuple[str, ...]:
        return tuple(
            f"{reading.name}: {reading.unavailable_reason}"
            for reading in self.metrics
            if not reading.available
        )

    def to_dict(self) -> dict[str, Any]:
        excludes = self.excludes
        return {
            "channel_id": self.channel_id,
            "video_id": self.video_id,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            # This version queries closed date ranges only, so every report it
            # emits measures an interval. A cumulative reading would need a
            # different query and would carry a different tag.
            "temporal_semantics": "interval",
            "source": ANALYTICS_SOURCE,
            "complete": not excludes,
            "excludes": list(excludes),
            "metrics": [reading.to_dict() for reading in self.metrics],
        }


class YouTubeReader:
    """Read-only access to the Data and Analytics APIs for the authorized channel."""

    def __init__(
        self,
        oauth: OAuthClient,
        transport: InstrumentedTransport,
        *,
        page_size: int = MAX_PAGE_SIZE,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.oauth = oauth
        self.transport = transport
        self.page_size = max(1, min(int(page_size), MAX_PAGE_SIZE))
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self._channel: ChannelResult | None = None

    def channel(self, *, refresh: bool = False) -> ChannelResult:
        """The authenticated channel, fetched once per reader unless refreshed."""
        if self._channel is not None and not refresh:
            return self._channel
        raw = self._get_json(
            f"{DATA_ROOT}/channels",
            {"part": "snippet,statistics,contentDetails", "mine": "true"},
        )
        self._channel = ChannelResult(_channel_facts(raw), raw)
        return self._channel

    def recent_videos(self, limit: int = 10) -> VideoListing:
        """The most recent uploads, paginated to the requested count."""
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ApiError("the video limit must be a positive integer")
        channel = self.channel()
        playlist_id = channel.facts.uploads_playlist_id
        video_ids: list[str] = []
        playlist_pages: list[dict[str, Any]] = []
        notes: list[str] = []
        page_token = ""
        pages = 0
        while len(video_ids) < limit:
            parameters = {
                "part": "contentDetails",
                "playlistId": playlist_id,
                "maxResults": str(min(self.page_size, limit - len(video_ids))),
            }
            if page_token:
                parameters["pageToken"] = page_token
            page = self._get_json(f"{DATA_ROOT}/playlistItems", parameters)
            pages += 1
            playlist_pages.append(page)
            before = len(video_ids)
            for item in _items(page):
                details = item.get("contentDetails")
                video_id = str(details.get("videoId", "")) if isinstance(details, dict) else ""
                if video_id and video_id not in video_ids:
                    video_ids.append(video_id)
            page_token = str(page.get("nextPageToken") or "")
            if not page_token:
                break
            if len(video_ids) == before:
                # A page that advances the token without adding an id would
                # otherwise spin until the quota ran out.
                notes.append(
                    "playlistItems.list returned a page with no new video ids; "
                    "pagination stopped there"
                )
                break
        video_ids = video_ids[:limit]
        if len(video_ids) < limit:
            notes.append(
                f"the uploads playlist held {len(video_ids)} videos, fewer than the "
                f"{limit} requested"
            )

        found: dict[str, VideoFacts] = {}
        video_pages: list[dict[str, Any]] = []
        for chunk in _chunks(video_ids, MAX_PAGE_SIZE):
            page = self._get_json(
                f"{DATA_ROOT}/videos",
                {"part": "snippet,contentDetails,status", "id": ",".join(chunk)},
            )
            video_pages.append(page)
            for item in _items(page):
                facts = _video_facts(item, channel.facts.channel_id)
                if facts is not None:
                    found[facts.video_id] = facts

        missing = tuple(video_id for video_id in video_ids if video_id not in found)
        if missing:
            notes.append(
                f"videos.list did not return {len(missing)} of the "
                f"{len(video_ids)} listed videos: " + ", ".join(missing)
            )
        return VideoListing(
            requested=limit,
            videos=tuple(found[video_id] for video_id in video_ids if video_id in found),
            playlist_video_ids=tuple(video_ids),
            missing_video_ids=missing,
            pages_followed=pages,
            notes=tuple(notes),
            raw_playlist_pages=tuple(playlist_pages),
            raw_video_pages=tuple(video_pages),
        )

    def analytics(
        self,
        start_date: dt.date,
        end_date: dt.date,
        *,
        video_id: str | None = None,
    ) -> AnalyticsReport:
        """One closed-interval report, channel-wide or filtered to one video."""
        if start_date > end_date:
            raise ApiError("the analytics start date must not be after the end date")
        channel = self.channel()
        parameters = {
            "ids": "channel==MINE",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "metrics": ",".join(ANALYTICS_API_METRICS),
        }
        if video_id:
            parameters["filters"] = f"video=={video_id}"
        raw = self._get_json(f"{ANALYTICS_ROOT}/reports", parameters)
        return AnalyticsReport(
            channel_id=channel.facts.channel_id,
            video_id=video_id,
            start_date=start_date,
            end_date=end_date,
            metrics=_readings(raw),
            raw=raw,
        )

    # -- transport ---------------------------------------------------------

    def _get_json(self, url: str, parameters: Mapping[str, str]) -> dict[str, Any]:
        return _json_object(self._request(f"{url}?{urlencode(parameters)}"))

    def _request(self, url: str) -> HttpResponse:
        """One authorized GET, with exactly one forced refresh available to it."""
        token = self.oauth.access_token()
        response = self.transport.request("GET", url, headers=_headers(token))
        if response.status == 401:
            token = self.oauth.access_token(force_refresh=True)
            response = self.transport.request("GET", url, headers=_headers(token))
            if response.status == 401:
                raise AuthorizationError(
                    "YouTube rejected the access token twice, once after a forced "
                    "refresh; the stored grant is no longer usable"
                )
        if not response.ok:
            raise _failure(response, self.oauth.config.client_secret, token)
        return response


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def _failure(response: HttpResponse, *secrets_in_scope: str) -> ApiError:
    """Turn a provider refusal into the type that names the operator's next move."""
    reason, message = _error_detail(response)
    # `scrub`, not `redact`: the provider's `message` is free text that can echo
    # a request back verbatim, so it is treated as untrusted rather than merely
    # stripped of the values this process happens to be holding.
    safe = SecretRedactor(*secrets_in_scope).scrub(message or reason or "api_error")
    if response.status == 403 and reason == "quotaExceeded":
        return QuotaExceeded(
            "the YouTube API daily quota for this project is exhausted; the same "
            f"request will succeed after the quota resets ({safe})"
        )
    if response.status == 403 and reason in {
        "insufficientPermissions",
        "forbidden",
        "PERMISSION_DENIED",
    }:
        return InsufficientPermissions(
            "the stored grant does not cover this request; authorize again and accept "
            f"both read-only scopes ({safe})"
        )
    return ApiError(f"the YouTube API request failed ({response.status}): {safe}")


def _error_detail(response: HttpResponse) -> tuple[str, str]:
    """The provider's machine-readable reason and its human sentence, if any."""
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return "", ""
    error = value.get("error") if isinstance(value, dict) else None
    if not isinstance(error, dict):
        return "", ""
    reason = ""
    errors = error.get("errors")
    if isinstance(errors, list):
        for entry in errors:
            if isinstance(entry, dict) and entry.get("reason"):
                reason = str(entry["reason"])
                break
    if not reason and error.get("status"):
        reason = str(error["status"])
    return reason, str(error.get("message") or "")


def _json_object(response: HttpResponse) -> dict[str, Any]:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError("the YouTube API returned a body that is not JSON") from None
    if not isinstance(value, dict):
        raise ApiError("the YouTube API returned a JSON value that is not an object")
    return value


# -- normalization ---------------------------------------------------------


def _items(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = value.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _chunks(values: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _optional_count(value: object) -> int | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        count = int(str(value))
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


def _channel_facts(raw: Mapping[str, Any]) -> ChannelFacts:
    items = _items(raw)
    if len(items) != 1:
        raise ApiError(
            "the authenticated account must expose exactly one YouTube channel; "
            f"channels.list returned {len(items)}"
        )
    item = items[0]
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    statistics = item.get("statistics") if isinstance(item.get("statistics"), dict) else {}
    content = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
    playlists = content.get("relatedPlaylists") if isinstance(content, dict) else {}
    playlists = playlists if isinstance(playlists, dict) else {}
    channel_id = str(item.get("id", ""))
    title = str(snippet.get("title", ""))
    uploads = str(playlists.get("uploads", ""))
    if not channel_id or not title or not uploads:
        raise ApiError("channels.list omitted the channel identity or uploads playlist")
    hidden = bool(statistics.get("hiddenSubscriberCount"))
    subscribers = None if hidden else _optional_count(statistics.get("subscriberCount"))
    reason = ""
    if hidden:
        reason = "the channel hides its subscriber count"
    elif subscribers is None:
        reason = "channels.list returned no usable subscriber count"
    return ChannelFacts(
        channel_id=channel_id,
        channel_title=title,
        subscriber_count=subscribers,
        subscriber_count_unavailable_reason=reason,
        video_count=_optional_count(statistics.get("videoCount")),
        view_count=_optional_count(statistics.get("viewCount")),
        uploads_playlist_id=uploads,
    )


def _video_facts(item: Mapping[str, Any], channel_id: str) -> VideoFacts | None:
    """A video, or `None` when the item cannot identify itself.

    An unusable item is dropped rather than raised on, so that one malformed
    entry cannot fail a whole fetch. It then shows up as a missing id in
    `video_retrieval`, which is exactly what it is.
    """
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    content = item.get("contentDetails") if isinstance(item.get("contentDetails"), dict) else {}
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    video_id = str(item.get("id", ""))
    title = str(snippet.get("title", ""))
    published = snippet.get("publishedAt")
    if not video_id or not title or not isinstance(published, str) or not published:
        return None
    duration = content.get("duration")
    duration_text = str(duration) if duration else None
    return VideoFacts(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        published_at=utc_timestamp(published),
        duration=duration_text,
        duration_seconds=_duration_seconds(duration_text) if duration_text else None,
        privacy_status=(
            str(status.get("privacyStatus")) if status.get("privacyStatus") else None
        ),
        upload_status=(
            str(status.get("uploadStatus")) if status.get("uploadStatus") else None
        ),
    )


def utc_timestamp(value: str) -> str:
    """One spelling for one instant, so two halves of the boundary agree.

    The Data API writes RFC 3339 with a trailing `Z`; the artifact writes every
    timestamp as an explicit UTC offset. Both parse to the same instant, but a
    file that mixes the two spellings makes a byte comparison of two identical
    pulls fail for a reason that has nothing to do with the numbers.
    """
    text = value.strip()
    candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError:
        return text
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat()


_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?"
    r"(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _duration_seconds(value: str) -> int | None:
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return (
        parts["days"] * 86400
        + parts["hours"] * 3600
        + parts["minutes"] * 60
        + parts["seconds"]
    )


def _readings(raw: Mapping[str, Any]) -> tuple[MetricReading, ...]:
    """Map one reports.query answer onto the metric vocabulary, absences included."""
    headers = raw.get("columnHeaders")
    rows = raw.get("rows")
    names = (
        [str(header.get("name", "")) for header in headers if isinstance(header, dict)]
        if isinstance(headers, list)
        else []
    )
    row: list[Any] = []
    if isinstance(rows, list) and rows and isinstance(rows[0], list):
        row = list(rows[0])
    values = {name: row[index] for index, name in enumerate(names) if index < len(row)}
    readings: list[MetricReading] = []
    for name, source_metric, unit, factor in METRIC_TABLE:
        raw_value = values.get(source_metric)
        if raw_value is None or isinstance(raw_value, bool):
            readings.append(
                MetricReading(
                    name,
                    source_metric,
                    unit,
                    None,
                    False,
                    NO_ROWS_REASON if not row else OMITTED_REASON,
                )
            )
            continue
        try:
            number = float(raw_value) * factor
        except (TypeError, ValueError):
            readings.append(
                MetricReading(name, source_metric, unit, None, False, NON_NUMERIC_REASON)
            )
            continue
        readings.append(
            MetricReading(name, source_metric, unit, _number(number, unit, factor), True)
        )
    return tuple(readings)


def _number(number: float, unit: str, factor: float) -> float | int:
    """Keep whole counts whole; keep converted values floating and stable."""
    if factor == 1.0 and unit not in {"fraction"} and float(number).is_integer():
        return int(number)
    # Binary floating point turns 45.6 * 0.01 into 0.45600000000000002, which
    # would make two identical pulls serialize differently.
    return round(number, 10)


__all__ = [
    "ANALYTICS_API_METRICS",
    "ANALYTICS_ROOT",
    "ANALYTICS_SOURCE",
    "CHANNELS_SOURCE",
    "DATA_ROOT",
    "MAX_PAGE_SIZE",
    "METRIC_TABLE",
    "PLAYLIST_ITEMS_SOURCE",
    "VIDEOS_SOURCE",
    "AnalyticsReport",
    "ChannelFacts",
    "ChannelResult",
    "MetricReading",
    "VideoFacts",
    "VideoListing",
    "YouTubeReader",
    "utc_timestamp",
]
