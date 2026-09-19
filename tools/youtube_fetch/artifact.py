"""The file that crosses the boundary, and the check that it is safe to cross it.

## Why a file exists at all

Company OS is network-free by policy, and the check that enforces it is one of
the required gates. That leaves exactly one way for a number Google holds to
become a number the analytics store holds: this package fetches it, writes a
sanitized JSON file, and `company/youtube` reads that file with no idea a
network exists. The file is the interface. Both halves are written against the
same written specification, and the specification is what makes the boundary
reviewable - somebody can open the artifact, read every field, and see that no
credential is in it.

## What the artifact deliberately does not contain

No access token, no refresh token, no client id or secret, no `Authorization`
header, no authorization code, no PKCE verifier, no `state`. `endpoint` in
`api_calls` is scheme, host and path with the query string removed, because the
query string is where the credentials live.

`assert_sanitized` enforces that before a single byte is written, and it is
deliberately a structural check rather than a habit: it walks the serialized
payload for the secret values this process is holding, for any key named after a
credential, and for a bearer prefix, and it refuses to write on a hit. A review
that depends on nobody ever adding a field is not a review.

## An aborted fetch and an incomplete one are different things

Nothing is written until the whole fetch has succeeded. A failure at any point -
a quota refusal, a 401 on page two, a malformed channel response - leaves no
file, which means no partially-observed interval can ever reach the analytics
store and no observation has to be retracted later.

A fetch that *finished* while knowing what it did not get is a different case
and is written, with `video_retrieval.complete` false, the exact missing ids,
and a sentence per gap. Ingestion turns that into a `DataScope` whose `excludes`
name the gap. Suppressing the file instead would lose nine good videos to
protect against one missing one, and - worse - would leave no record that the
tenth was ever expected. The refusal to write is about evidence we could not
establish; the recorded gap is about evidence we established the absence of.

## Fetch time is recorded, and it identifies nothing

`fetched_at` is in the artifact because an operator needs to know how old the
numbers are. It is deliberately not part of anything downstream that determines
identity: two pulls of the same interval must produce the same observation ids,
or a replay becomes a contradiction. The artifact's own semantic digest, taken
on the Company OS side, excludes it for the same reason.
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .api import AnalyticsReport, VideoListing, YouTubeReader
from .errors import YouTubeFetchError
from .transport import ApiCallTrace


ARTIFACT_VERSION = 1
PRODUCER = "tools.youtube_fetch"
PRODUCER_VERSION = "1.0"

# Keys that may never appear anywhere in a written artifact, at any depth.
FORBIDDEN_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "client_secret",
        "authorization",
        "code_verifier",
        "code_challenge",
    }
)


@dataclass(frozen=True)
class FetchRequest:
    """What the operator asked this pull to cover."""

    start_date: dt.date
    end_date: dt.date
    video_limit: int = 10
    video_analytics: bool = False
    include_raw: bool = False

    def __post_init__(self) -> None:
        if self.start_date > self.end_date:
            raise YouTubeFetchError("the analytics start date must not be after the end date")
        if self.video_limit < 1:
            raise YouTubeFetchError("the video limit must be at least 1")


def fetch_artifact(
    reader: YouTubeReader,
    request: FetchRequest,
    *,
    granted_scopes: Sequence[str] | None = None,
    fetched_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Run the whole pull and assemble the artifact, or raise and write nothing.

    `granted_scopes` defaults to what the OAuth client holds *after* the pull,
    which is what the provider last said the grant covers - asking beforehand
    would report the stored copy, which is one refresh out of date.
    """
    channel = reader.channel()
    listing = reader.recent_videos(request.video_limit)
    reports: list[AnalyticsReport] = [
        reader.analytics(request.start_date, request.end_date)
    ]
    if request.video_analytics:
        for video in listing.videos:
            reports.append(
                reader.analytics(
                    request.start_date, request.end_date, video_id=video.video_id
                )
            )
    return build_artifact(
        channel_raw=channel.raw,
        channel=channel.facts.to_dict(),
        listing=listing,
        reports=tuple(reports),
        traces=tuple(reader.transport.traces),
        granted_scopes=(
            reader.oauth.granted_scopes() if granted_scopes is None else granted_scopes
        ),
        include_raw=request.include_raw,
        fetched_at=fetched_at,
    )


def build_artifact(
    *,
    channel_raw: Mapping[str, Any],
    channel: Mapping[str, Any],
    listing: VideoListing,
    reports: Sequence[AnalyticsReport],
    traces: Sequence[ApiCallTrace] = (),
    granted_scopes: Sequence[str] = (),
    include_raw: bool = False,
    fetched_at: dt.datetime | None = None,
) -> dict[str, Any]:
    """Assemble the artifact payload from already-fetched parts."""
    stamped = fetched_at or dt.datetime.now(dt.timezone.utc)
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=dt.timezone.utc)
    payload: dict[str, Any] = {
        "artifact_version": ARTIFACT_VERSION,
        "producer": PRODUCER,
        "producer_version": PRODUCER_VERSION,
        "fetched_at": stamped.isoformat(),
        "granted_scopes": sorted(str(scope) for scope in granted_scopes),
        "channel": dict(channel),
        "videos": [video.to_dict() for video in listing.videos],
        "video_retrieval": listing.retrieval_dict(),
        "analytics": [report.to_dict() for report in reports],
        "api_calls": [trace.to_dict() for trace in traces],
    }
    if include_raw:
        # Omitted entirely rather than written empty: a present-but-empty `raw`
        # reads as "the provider sent nothing", which is a different claim.
        payload["raw"] = {
            "channels.list": dict(channel_raw),
            "playlistItems.list": [dict(page) for page in listing.raw_playlist_pages],
            "videos.list": [dict(page) for page in listing.raw_video_pages],
            "reports.query": [dict(report.raw) for report in reports],
        }
    return payload


def serialize(payload: Mapping[str, Any]) -> str:
    """Canonical UTF-8 JSON with sorted keys, so two identical pulls are one file."""
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def assert_sanitized(payload: Mapping[str, Any], secret_values: Iterable[str] = ()) -> None:
    """Refuse to hand over an artifact that carries a credential.

    Three passes, because three different mistakes produce a leak: a value this
    process holds getting copied into a field, a provider response echoing a
    credential under its own key name, and a URL reaching `endpoint` with its
    query string attached.
    """
    text = serialize(payload)
    for secret in secret_values:
        if isinstance(secret, str) and len(secret) >= 4 and secret in text:
            raise YouTubeFetchError(
                "refusing to write the artifact: it contains a value this process "
                "holds as a secret"
            )
    if "Bearer " in text:
        raise YouTubeFetchError(
            "refusing to write the artifact: it contains a bearer credential"
        )
    offending = sorted(_forbidden_keys(payload))
    if offending:
        raise YouTubeFetchError(
            "refusing to write the artifact: credential-shaped keys present: "
            + ", ".join(offending)
        )
    for call in payload.get("api_calls", []):
        endpoint = str(call.get("endpoint", "")) if isinstance(call, Mapping) else ""
        if "?" in endpoint:
            raise YouTubeFetchError(
                "refusing to write the artifact: an api_calls endpoint kept its query string"
            )


def write_artifact(
    payload: Mapping[str, Any],
    path: str | Path,
    *,
    secret_values: Iterable[str] = (),
) -> Path:
    """Sanitize, then write. The order is the whole point of the function."""
    assert_sanitized(payload, secret_values)
    destination = Path(path).expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(serialize(payload), encoding="utf-8")
    return destination


def _forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                found.add(str(key))
            found |= _forbidden_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            found |= _forbidden_keys(item)
    return found


__all__ = [
    "ARTIFACT_VERSION",
    "FORBIDDEN_KEYS",
    "PRODUCER",
    "PRODUCER_VERSION",
    "FetchRequest",
    "assert_sanitized",
    "build_artifact",
    "fetch_artifact",
    "serialize",
    "write_artifact",
]
