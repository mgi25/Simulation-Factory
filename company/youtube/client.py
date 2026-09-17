"""Read-only YouTube Data API and Analytics API client."""

from __future__ import annotations

import datetime as dt
import json
import re
from typing import Any, Callable, Mapping
from urllib.parse import urlencode

from .errors import ApiError, EvidenceError
from .models import (
    AnalyticsEvidence,
    ChannelEvidence,
    MetricReading,
    RetrievedEvidence,
    VideoEvidence,
)
from .oauth import OAuthClient
from .security import SecretRedactor
from .transport import ApiCallTrace, HttpResponse, InstrumentedTransport


DATA_ROOT = "https://www.googleapis.com/youtube/v3"
ANALYTICS_ROOT = "https://youtubeanalytics.googleapis.com/v2"

_METRICS: tuple[tuple[str, str, str, float], ...] = (
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
ANALYTICS_API_METRICS = tuple(metric[1] for metric in _METRICS)


class YouTubeClient:
    def __init__(
        self,
        oauth: OAuthClient,
        transport: InstrumentedTransport,
        *,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.oauth = oauth
        self.transport = transport
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))

    def channel(self) -> RetrievedEvidence:
        start = len(self.transport.traces)
        retrieved = self.now()
        raw = self._get_json(
            f"{DATA_ROOT}/channels",
            {"part": "snippet,statistics,contentDetails", "mine": "true"},
        )
        channel = _channel(raw, retrieved)
        return RetrievedEvidence(
            "channel", channel, raw, retrieved, self._traces_since(start)
        )

    def recent_videos(self, limit: int = 10) -> RetrievedEvidence:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise EvidenceError("video limit must be between 1 and 50")
        start = len(self.transport.traces)
        retrieved = self.now()
        channel_raw = self._get_json(
            f"{DATA_ROOT}/channels",
            {"part": "snippet,statistics,contentDetails", "mine": "true"},
        )
        channel = _channel(channel_raw, retrieved)
        playlist_raw = self._get_json(
            f"{DATA_ROOT}/playlistItems",
            {
                "part": "contentDetails",
                "playlistId": channel.uploads_playlist_id,
                "maxResults": str(limit),
            },
        )
        video_ids = tuple(
            str(item.get("contentDetails", {}).get("videoId", ""))
            for item in _items(playlist_raw)
            if item.get("contentDetails", {}).get("videoId")
        )
        videos_raw: dict[str, Any] = {"items": []}
        if video_ids:
            videos_raw = self._get_json(
                f"{DATA_ROOT}/videos",
                {"part": "snippet,contentDetails,status", "id": ",".join(video_ids)},
            )
        by_id = {
            str(item.get("id", "")): _video(item, channel.channel_id, retrieved)
            for item in _items(videos_raw)
        }
        videos = tuple(by_id[video_id] for video_id in video_ids if video_id in by_id)
        raw = {
            "channels.list": channel_raw,
            "playlistItems.list": playlist_raw,
            "videos.list": videos_raw,
        }
        return RetrievedEvidence(
            "videos", videos, raw, retrieved, self._traces_since(start)
        )

    def video(self, video_id: str) -> RetrievedEvidence:
        if not video_id.strip():
            raise EvidenceError("video_id is required")
        start = len(self.transport.traces)
        retrieved = self.now()
        channel_result = self.channel()
        raw = self._get_json(
            f"{DATA_ROOT}/videos",
            {"part": "snippet,contentDetails,status", "id": video_id},
        )
        items = _items(raw)
        if not items:
            raise EvidenceError(f"YouTube returned no video for id {video_id!r}")
        channel = channel_result.normalized
        if not isinstance(channel, ChannelEvidence):  # pragma: no cover - type guard
            raise EvidenceError("channel normalization failed")
        video = _video(items[0], channel.channel_id, retrieved)
        return RetrievedEvidence(
            "videos",
            (video,),
            {"channels.list": channel_result.raw, "videos.list": raw},
            retrieved,
            self._traces_since(start),
        )

    def analytics(
        self,
        start_date: dt.date,
        end_date: dt.date,
        *,
        video_id: str | None = None,
    ) -> RetrievedEvidence:
        if start_date > end_date:
            raise EvidenceError("analytics start date must not be after end date")
        start = len(self.transport.traces)
        retrieved = self.now()
        channel_result = self.channel()
        channel = channel_result.normalized
        if not isinstance(channel, ChannelEvidence):  # pragma: no cover - type guard
            raise EvidenceError("channel normalization failed")
        parameters = {
            "ids": "channel==MINE",
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "metrics": ",".join(ANALYTICS_API_METRICS),
        }
        if video_id:
            parameters["filters"] = f"video=={video_id}"
        raw = self._get_json(f"{ANALYTICS_ROOT}/reports", parameters)
        normalized = _analytics(
            raw,
            channel_id=channel.channel_id,
            start_date=start_date,
            end_date=end_date,
            video_id=video_id,
            retrieved_at=retrieved,
        )
        return RetrievedEvidence(
            "analytics",
            normalized,
            {"channels.list": channel_result.raw, "reports.query": raw},
            retrieved,
            self._traces_since(start),
        )

    def _get_json(self, url: str, parameters: Mapping[str, str]) -> dict[str, Any]:
        response = self._request("GET", f"{url}?{urlencode(parameters)}")
        return _json_object(response)

    def _request(self, method: str, url: str) -> HttpResponse:
        if method != "GET":
            raise ApiError("YouTube API operations are read-only GET requests")
        token = self.oauth.access_token()
        response = self.transport.request(
            method,
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        if response.status == 401:
            token = self.oauth.access_token(force_refresh=True)
            response = self.transport.request(
                method,
                url,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
        if not 200 <= response.status < 300:
            reason = _api_reason(response)
            raise ApiError(
                f"YouTube API request failed ({response.status}): "
                + SecretRedactor(token).redact(reason)
            )
        return response

    def _traces_since(self, index: int) -> tuple[ApiCallTrace, ...]:
        return tuple(self.transport.traces[index:])


def _json_object(response: HttpResponse) -> dict[str, Any]:
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ApiError("YouTube API returned invalid JSON") from None
    if not isinstance(value, dict):
        raise ApiError("YouTube API returned a non-object response")
    return value


def _api_reason(response: HttpResponse) -> str:
    try:
        value = json.loads(response.body.decode("utf-8"))
        error = value.get("error", {}) if isinstance(value, dict) else {}
        if isinstance(error, dict):
            return str(error.get("message") or error.get("status") or "api_error")
    except (UnicodeDecodeError, ValueError):
        pass
    return "api_error"


def _items(value: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = value.get("items", [])
    return [item for item in items if isinstance(item, dict)] if isinstance(items, list) else []


def _optional_count(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        result = int(str(value))
    except ValueError:
        return None
    return result if result >= 0 else None


def _channel(raw: Mapping[str, Any], retrieved_at: dt.datetime) -> ChannelEvidence:
    items = _items(raw)
    if len(items) != 1:
        raise EvidenceError("authenticated account must expose exactly one YouTube channel")
    item = items[0]
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    playlists = item.get("contentDetails", {}).get("relatedPlaylists", {})
    channel_id = str(item.get("id", ""))
    title = str(snippet.get("title", "")) if isinstance(snippet, dict) else ""
    uploads = str(playlists.get("uploads", "")) if isinstance(playlists, dict) else ""
    if not channel_id or not title or not uploads:
        raise EvidenceError("channel response omitted identity or uploads playlist")
    hidden = bool(statistics.get("hiddenSubscriberCount")) if isinstance(statistics, dict) else False
    return ChannelEvidence(
        channel_id=channel_id,
        channel_title=title,
        subscriber_count=(
            None if hidden else _optional_count(statistics.get("subscriberCount"))
        ),
        video_count=_optional_count(statistics.get("videoCount")),
        view_count=_optional_count(statistics.get("viewCount")),
        uploads_playlist_id=uploads,
        retrieved_at=retrieved_at,
        subscriber_count_unavailable_reason=(
            "subscriber count is hidden by the channel" if hidden else ""
        ),
    )


def _video(item: Mapping[str, Any], channel_id: str, retrieved_at: dt.datetime) -> VideoEvidence:
    snippet = item.get("snippet", {})
    content = item.get("contentDetails", {})
    status = item.get("status", {})
    video_id = str(item.get("id", ""))
    title = str(snippet.get("title", "")) if isinstance(snippet, dict) else ""
    published = snippet.get("publishedAt") if isinstance(snippet, dict) else None
    if not video_id or not title or not isinstance(published, str):
        raise EvidenceError("video response omitted id, title, or publication time")
    duration = content.get("duration") if isinstance(content, dict) else None
    return VideoEvidence(
        video_id=video_id,
        channel_id=channel_id,
        title=title,
        published_at=published,
        duration=str(duration) if duration else None,
        duration_seconds=_duration_seconds(str(duration)) if duration else None,
        privacy_status=(str(status.get("privacyStatus")) if status.get("privacyStatus") else None),
        upload_status=(str(status.get("uploadStatus")) if status.get("uploadStatus") else None),
        retrieved_at=retrieved_at,
    )


_DURATION = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?$"
)


def _duration_seconds(value: str) -> int | None:
    match = _DURATION.fullmatch(value)
    if match is None:
        return None
    parts = {name: int(number or 0) for name, number in match.groupdict().items()}
    return parts["days"] * 86400 + parts["hours"] * 3600 + parts["minutes"] * 60 + parts["seconds"]


def _analytics(
    raw: Mapping[str, Any],
    *,
    channel_id: str,
    start_date: dt.date,
    end_date: dt.date,
    video_id: str | None,
    retrieved_at: dt.datetime,
) -> AnalyticsEvidence:
    headers = raw.get("columnHeaders", [])
    rows = raw.get("rows", [])
    names = [
        str(header.get("name", ""))
        for header in headers
        if isinstance(header, dict)
    ] if isinstance(headers, list) else []
    row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], list) else []
    values = {name: row[index] for index, name in enumerate(names) if index < len(row)}
    readings: list[MetricReading] = []
    empty_reason = "API returned no rows for the requested range"
    for name, source, unit, factor in _METRICS:
        raw_value = values.get(source)
        if raw_value is None or isinstance(raw_value, bool):
            readings.append(
                MetricReading(
                    name,
                    source,
                    unit,
                    None,
                    False,
                    empty_reason if not row else "API omitted this metric",
                )
            )
            continue
        try:
            number = float(raw_value) * factor
        except (TypeError, ValueError):
            readings.append(
                MetricReading(name, source, unit, None, False, "API returned a non-numeric value")
            )
            continue
        value: float | int = int(number) if unit not in {"minutes", "seconds", "fraction"} and number.is_integer() else number
        readings.append(MetricReading(name, source, unit, value, True))
    return AnalyticsEvidence(
        channel_id, start_date, end_date, video_id, tuple(readings), retrieved_at
    )


__all__ = ["ANALYTICS_API_METRICS", "YouTubeClient"]
