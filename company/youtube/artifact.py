"""Reading the artifact strictly, and digesting what it actually measured.

## Strict on the way in, because there is no way back

The artifact is written by a program Company OS does not contain, running with
credentials Company OS never sees. Everything downstream of this module - the
source record, the observations, the ledger - treats it as first-party
authenticated evidence, which is the strongest claim this company makes about a
number. The place to earn that claim is here, once, at the boundary.

So the parser is deliberately unforgiving. A key it does not recognise is a
refusal rather than a field it ignores, because an ignored key is a statement
the fetcher made and the ingester silently dropped. A version it does not know
is a refusal, because a schema change it cannot see is exactly the thing that
turns a percentage into a fraction. A grant it does not recognise is a refusal,
because the authority behind a private metric is the grant.

`assert_no_credentials` walks the parsed object for key names that should not
exist anywhere in a sanitized artifact. It matches keys rather than text, so a
video whose title mentions an access token is fine and an object that actually
carries one is not. It is a second line behind the fetcher's redaction, and it
is cheap: a leak here would be copied into an append-only evidence store, which
is the one place a secret must never land.

## The digest describes the measurement, not the pull

`semantic_payload` is the artifact minus everything that describes the act of
fetching: `fetched_at`, the producer and its version, the per-call telemetry and
the preserved `raw` responses. What remains is what the APIs said - the channel,
the videos, how complete the retrieval was, and the analytics rows - plus the
grant that made it readable.

`artifact_digest` is SHA-256 over that, and it is the identity of the pull. Two
fetches of the same window that agree digest the same, so the second import is a
replay that writes nothing; a fetch that disagrees digests differently and
arrives as a conflict rather than an overwrite. Leaving `fetched_at` in would
have made every re-pull a new source record claiming the same readings, and
leaving `latency_ms` in would have made the ledger sensitive to network weather.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from .errors import ArtifactRejected, ArtifactUnreadable
from .models import (
    AnalyticsEvidence,
    ApiCallTrace,
    ChannelEvidence,
    MetricReading,
    VideoEvidence,
    VideoRetrieval,
    YouTubeArtifact,
)

# The artifact schema this parser understands. A different number is refused by
# name rather than read hopefully: a field that changed meaning between versions
# is invisible to a parser that just looks for the keys it knows.
SUPPORTED_ARTIFACT_VERSION = 1

# The two read-only grants a pull may run under. Spelled out here rather than
# imported from `tools/youtube_fetch`, because the two halves share no code by
# design - and a constant duplicated across a boundary that is checked from both
# sides is a boundary, while a constant imported across it is a dependency.
DATA_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
REQUIRED_SCOPES: tuple[str, ...] = (DATA_SCOPE, ANALYTICS_SCOPE)

# Top-level keys the artifact may carry. `raw` is optional; everything else is
# required, and anything not listed is refused.
_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "artifact_version",
        "producer",
        "producer_version",
        "fetched_at",
        "granted_scopes",
        "channel",
        "videos",
        "video_retrieval",
        "analytics",
        "api_calls",
    }
)
_OPTIONAL_KEYS: frozenset[str] = frozenset({"raw"})

# Key names that cannot appear in a sanitized artifact at any depth. Matched on
# the key, never on a value, so prose is never mistaken for a secret.
_CREDENTIAL_KEYS: frozenset[str] = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_id",
        "client_secret",
        "code_challenge",
        "code_verifier",
        "id_token",
        "refresh_token",
    }
)

# Fields of the artifact that describe the fetch rather than the measurement,
# and are therefore outside the digest. See the module docstring.
_NON_SEMANTIC_FIELDS: tuple[str, ...] = ("fetched_at", "producer", "producer_version")


def read_artifact(path: str | Path) -> YouTubeArtifact:
    """Read one artifact file. Unreadable is a different failure from invalid."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise ArtifactUnreadable(f"cannot read {source}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise ArtifactUnreadable(
            f"{source} is not UTF-8 text ({exc.reason} at byte {exc.start}); the "
            "fetcher writes canonical UTF-8 JSON, so re-run the fetch rather than "
            "transcoding what is here"
        ) from exc
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ArtifactUnreadable(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ArtifactRejected(
            f"{source}: an artifact is a JSON object, got {type(data).__name__}"
        )
    return parse_artifact(data)


def parse_artifact(mapping: Mapping[str, Any]) -> YouTubeArtifact:
    """Validate one artifact mapping into records, or refuse it by name."""
    if not isinstance(mapping, Mapping):
        raise ArtifactRejected(f"an artifact is a JSON object, got {mapping!r}")
    assert_no_credentials(mapping)

    keys = set(mapping)
    missing = sorted(_REQUIRED_KEYS - keys)
    if missing:
        raise ArtifactRejected(
            "artifact: missing " + ", ".join(missing) + ". Every one of them is part "
            "of what makes a reading traceable, so an artifact without them is not a "
            "partial artifact, it is a different document"
        )
    unknown = sorted(keys - _REQUIRED_KEYS - _OPTIONAL_KEYS)
    if unknown:
        raise ArtifactRejected(
            "artifact: unrecognised key(s) " + ", ".join(unknown) + ". A key this "
            "parser does not know is a statement the fetcher made and the ingester "
            "would silently drop; teach the parser or remove the key"
        )

    version = mapping["artifact_version"]
    if version != SUPPORTED_ARTIFACT_VERSION:
        raise ArtifactRejected(
            f"artifact: version {version!r} was written for a different reader; this "
            f"one understands version {SUPPORTED_ARTIFACT_VERSION}"
        )

    scopes = _string_tuple(mapping["granted_scopes"], "granted_scopes")
    _assert_read_only_grant(scopes)

    channel = _channel(mapping["channel"])
    videos = tuple(_video(item) for item in _sequence(mapping["videos"], "videos"))
    retrieval = _retrieval(mapping["video_retrieval"])
    if retrieval.returned != len(videos):
        raise ArtifactRejected(
            f"video_retrieval: says {retrieval.returned} video(s) were returned while "
            f"the artifact carries {len(videos)}. The count and the list disagree, and "
            "neither can be trusted to say what the pull actually saw"
        )
    reports = tuple(
        _report(item) for item in _sequence(mapping["analytics"], "analytics")
    )
    calls = tuple(_call(item) for item in _sequence(mapping["api_calls"], "api_calls"))

    for report in reports:
        if report.channel_id != channel.channel_id:
            raise ArtifactRejected(
                f"analytics: a row set for channel {report.channel_id!r} is in an "
                f"artifact authenticated against {channel.channel_id!r}. One pull "
                "reads one channel; two in one file makes every reading in it "
                "ambiguous about whose it is"
            )

    raw = mapping.get("raw")
    if raw is not None and not isinstance(raw, dict):
        raise ArtifactRejected(
            f"raw: expected the preserved provider responses as an object, got "
            f"{type(raw).__name__}"
        )

    return YouTubeArtifact(
        artifact_version=version,
        producer=_text(mapping["producer"], "producer"),
        producer_version=_text(mapping["producer_version"], "producer_version"),
        fetched_at=mapping["fetched_at"],
        granted_scopes=scopes,
        channel=channel,
        videos=videos,
        video_retrieval=retrieval,
        analytics=reports,
        api_calls=calls,
        raw=raw,
    )


def semantic_payload(artifact: YouTubeArtifact) -> dict[str, Any]:
    """What the APIs reported, with everything about the fetch removed.

    The basis of the digest, and therefore of the source id, the evidence
    reference and every claim of replay-identity this layer makes. Exactly:
    the artifact version, the grant, the channel, the videos, the retrieval
    completeness and the analytics rows. Deliberately absent: `fetched_at`, the
    producer and its version, `api_calls` and `raw`.
    """
    payload = artifact.normalized()
    for field_name in _NON_SEMANTIC_FIELDS:
        payload.pop(field_name, None)
    return payload


def artifact_digest(artifact: YouTubeArtifact) -> str:
    """SHA-256 over the semantic payload, lowercase hex. The pull's identity.

    Canonical JSON - sorted keys, no insignificant whitespace - so that two
    artifacts saying the same thing in a different key order digest the same.
    """
    canonical = json.dumps(
        semantic_payload(artifact),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_no_credentials(value: Any, path: str = "artifact") -> None:
    """Refuse an artifact carrying a key that could hold a secret, at any depth."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.strip().lower() in _CREDENTIAL_KEYS:
                raise ArtifactRejected(
                    f"{path}: the key {key!r} must never appear in a sanitized "
                    "artifact. Company OS appends what it ingests to an append-only "
                    "evidence store, which is the last place a credential can be "
                    "removed from. The value is not quoted here, deliberately"
                )
            assert_no_credentials(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            assert_no_credentials(item, f"{path}[{index}]")


def _assert_read_only_grant(scopes: tuple[str, ...]) -> None:
    """Exactly the two read-only grants, no more and no fewer.

    Requirement 7 from the reading side. The fetcher requests two scopes and
    refuses to store a grant that is missing either; this end refuses an
    artifact produced under anything wider. Together they mean that widening
    what this company can do to its own channel is a review of two files, not a
    flag somebody passes.
    """
    missing = [scope for scope in REQUIRED_SCOPES if scope not in scopes]
    if missing:
        raise ArtifactRejected(
            "granted_scopes: the pull was not granted " + ", ".join(missing) + ". A "
            "private reading is admissible because the access was authorized; a "
            "reading taken without the grant that makes it readable is not"
        )
    extra = sorted(set(scopes) - set(REQUIRED_SCOPES))
    if extra:
        raise ArtifactRejected(
            "granted_scopes: this ingester admits pulls made under exactly the two "
            "read-only grants, and this one also holds " + ", ".join(extra) + ". A "
            "wider grant is a different kind of access to our own channel and wants a "
            "review, not a silent import"
        )


def _channel(data: Any) -> ChannelEvidence:
    mapping = _object(data, "channel")
    return ChannelEvidence(
        channel_id=mapping.get("channel_id"),
        channel_title=_text(mapping.get("channel_title", ""), "channel.channel_title"),
        subscriber_count=mapping.get("subscriber_count"),
        video_count=mapping.get("video_count"),
        view_count=mapping.get("view_count"),
        uploads_playlist_id=mapping.get("uploads_playlist_id", ""),
        subscriber_count_unavailable_reason=mapping.get(
            "subscriber_count_unavailable_reason", ""
        ),
        source=mapping.get("source", ChannelEvidence.source),
    )


def _video(data: Any) -> VideoEvidence:
    mapping = _object(data, "videos[]")
    return VideoEvidence(
        video_id=mapping.get("video_id"),
        channel_id=mapping.get("channel_id"),
        title=_text(mapping.get("title", ""), "videos[].title"),
        published_at=mapping.get("published_at"),
        duration=mapping.get("duration"),
        duration_seconds=mapping.get("duration_seconds"),
        privacy_status=mapping.get("privacy_status"),
        upload_status=mapping.get("upload_status"),
        source=mapping.get("source", VideoEvidence.source),
    )


def _retrieval(data: Any) -> VideoRetrieval:
    mapping = _object(data, "video_retrieval")
    return VideoRetrieval(
        requested=mapping.get("requested"),
        returned=mapping.get("returned"),
        complete=mapping.get("complete", True),
        pages_followed=mapping.get("pages_followed", 1),
        missing_video_ids=_string_tuple(
            mapping.get("missing_video_ids") or (), "video_retrieval.missing_video_ids"
        ),
        notes=_string_tuple(mapping.get("notes") or (), "video_retrieval.notes"),
    )


def _report(data: Any) -> AnalyticsEvidence:
    mapping = _object(data, "analytics[]")
    metrics = tuple(
        _metric(item) for item in _sequence(mapping.get("metrics") or (), "metrics")
    )
    return AnalyticsEvidence(
        channel_id=mapping.get("channel_id"),
        video_id=mapping.get("video_id"),
        start_date=mapping.get("start_date"),
        end_date=mapping.get("end_date"),
        metrics=metrics,
        temporal_semantics=mapping.get("temporal_semantics", ""),
        complete=mapping.get("complete", True),
        excludes=_string_tuple(mapping.get("excludes") or (), "analytics[].excludes"),
        source=mapping.get("source", AnalyticsEvidence.source),
    )


def _metric(data: Any) -> MetricReading:
    mapping = _object(data, "analytics[].metrics[]")
    return MetricReading(
        name=_text(mapping.get("name", ""), "metric name"),
        source_metric=_text(mapping.get("source_metric", ""), "metric source_metric"),
        unit=_text(mapping.get("unit", ""), "metric unit"),
        value=mapping.get("value"),
        available=mapping.get("available"),
        unavailable_reason=mapping.get("unavailable_reason", ""),
    )


def _call(data: Any) -> ApiCallTrace:
    mapping = _object(data, "api_calls[]")
    return ApiCallTrace(
        method=_text(mapping.get("method", ""), "api_calls[].method"),
        endpoint=_text(mapping.get("endpoint", ""), "api_calls[].endpoint"),
        status=mapping.get("status"),
        response_bytes=mapping.get("response_bytes", 0),
        latency_ms=mapping.get("latency_ms", 0),
        succeeded=mapping.get("succeeded", True),
        error_kind=mapping.get("error_kind", ""),
    )


def _object(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ArtifactRejected(
            f"{field_name}: expected an object, got {type(value).__name__}"
        )
    return value


def _sequence(value: Any, field_name: str) -> Iterable[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise ArtifactRejected(
            f"{field_name}: expected a list, got {type(value).__name__}"
        )
    return value


def _text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactRejected(f"{field_name}: expected text, got {value!r}")
    return value


def _string_tuple(value: Any, field_name: str) -> tuple[str, ...]:
    for item in _sequence(value, field_name):
        if not isinstance(item, str):
            raise ArtifactRejected(
                f"{field_name}: expected a list of strings, found {item!r}"
            )
    return tuple(value)


__all__ = [
    "ANALYTICS_SCOPE",
    "DATA_SCOPE",
    "REQUIRED_SCOPES",
    "SUPPORTED_ARTIFACT_VERSION",
    "artifact_digest",
    "assert_no_credentials",
    "parse_artifact",
    "read_artifact",
    "semantic_payload",
]
