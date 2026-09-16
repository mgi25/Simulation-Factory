"""The one door metadata comes through, and the only adapter behind it so far.

An `IngestionEnvelope` is what an external capture looks like before this
package believes any of it: a platform, a URL, a day, how it was captured, an
evidence pointer, and a payload of fields somebody read off a public page.

    envelope -> platform payload schema -> DiscoveryCandidate + PublicSnapshot

The envelope exists so that the browser extension nobody has written, the
YouTube Data API adapter nobody has written, and the researcher with a
spreadsheet all arrive at the same place through the same validation. The
researcher with a spreadsheet works today; that is the cheap adapter, and it is
the one this phase ships.

## The payload is validated, not trusted

A free-form `dict` here would undo the entire type discipline of phase 3, so
the payload is checked against a schema before it becomes anything:

- an **unknown key is refused**, because a typo that is silently dropped is a
  metric a researcher believes they recorded and did not;
- a **private channel analytic is refused by name** (section 5) - retention,
  revenue, RPM, traffic sources, impressions - because no public page shows
  them for somebody else's video;
- every value is parsed to its type, so a view count that arrived as "1.2M"
  fails here rather than becoming a float three modules later.

There is no key that names a file, a download, or a local copy. That is not an
omission: `RightsStatus` requires a named authoriser for a local copy, and an
ingestion payload cannot supply one, so ingestion has no path to producing one.

## No network, again

Nothing in this module opens a URL, and the URL in an envelope is canonicalized
by string rules only. `CaptureMethod.PLATFORM_API` records that a *person*
exported rows from an API console; it does not call one.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from ai_platform.serde import as_date, fingerprint, read_json
from intelligence.research.common import (
    Evidence,
    assert_reference,
    assert_research_id,
    assert_slug,
    assert_text,
)
from intelligence.research.discovery import (
    DiscoveryCandidate,
    assert_language,
    assert_line,
    assert_region,
)
from intelligence.research.errors import ResearchError
from intelligence.research.provenance import CaptureMethod, DiscoveryProvenance
from intelligence.research.snapshots import (
    PublicSnapshot,
    assert_public_metric_name,
)
from intelligence.research.sources import PublicMetrics
from intelligence.research.urls import (
    ContentIdentity,
    assert_known_platform,
    canonicalize,
)


def _as_line(value: Any, field_name: str) -> str:
    return assert_line(str(value), field_name)


def _as_count(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResearchError(
            f"{field_name}: expected a whole number, got {value!r}. A count that "
            "arrived as text ('1.2M', '12,043') is a count nobody has parsed - parse "
            "it where it was captured, so the rounding is visible there."
        )
    if value < 0:
        raise ResearchError(f"{field_name}: a public count cannot be negative, got {value}")
    return value


def _as_date(value: Any, field_name: str) -> dt.date:
    return as_date(value, field_name)


def _as_language(value: Any, field_name: str) -> str:
    return assert_language(str(value), field_name)


def _as_region(value: Any, field_name: str) -> str:
    return assert_region(str(value), field_name)


def _as_slugs(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ResearchError(f"{field_name}: expected a list of tags, got the string {value!r}")
    return tuple(assert_slug(str(item), field_name) for item in value)


def _as_lines(value: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(value, str):
        raise ResearchError(f"{field_name}: expected a list, got the string {value!r}")
    return tuple(_as_line(item, field_name) for item in value)


PUBLIC_VIDEO_PAYLOAD: Mapping[str, Callable[[Any, str], Any]] = {
    "title": _as_line,
    "creator": _as_line,
    "creator_id": _as_line,
    "published_on": _as_date,
    "duration_seconds": _as_count,
    "views": _as_count,
    "likes": _as_count,
    "comments": _as_count,
    "channel_subscribers": _as_count,
    "language": _as_language,
    "region": _as_region,
    "tags": _as_slugs,
    "signals": _as_lines,
    "note": _as_line,
}
"""Everything a logged-out viewer can read off a video page, and nothing else.

Deliberately platform-neutral: these are the fields YouTube, TikTok and
Instagram all put on the page, and a platform that shows something genuinely
different registers its own schema rather than widening this one."""

# The fields that belong in a dated reading rather than on the candidate.
_SNAPSHOT_KEYS: tuple[str, ...] = (
    "views",
    "likes",
    "comments",
    "duration_seconds",
    "channel_subscribers",
)

_PAYLOAD_SCHEMAS: dict[str, Mapping[str, Callable[[Any, str], Any]]] = {}


def register_payload_schema(
    platform: str, schema: Mapping[str, Callable[[Any, str], Any]]
) -> None:
    """Give a platform its own payload vocabulary."""
    assert_slug(platform, "payload schema platform")
    _PAYLOAD_SCHEMAS[platform] = dict(schema)


def unregister_payload_schema(platform: str) -> None:
    _PAYLOAD_SCHEMAS.pop(platform, None)


def payload_schema_for(platform: str) -> Mapping[str, Callable[[Any, str], Any]]:
    """A platform's schema, or the public-video vocabulary every platform shares."""
    return _PAYLOAD_SCHEMAS.get(platform, PUBLIC_VIDEO_PAYLOAD)


def validate_payload(
    platform: str, payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Parse a payload against its platform schema. Unknown in, error out."""
    if not isinstance(payload, Mapping):
        raise ResearchError(f"payload must be a mapping, got {type(payload).__name__}")
    schema = payload_schema_for(platform)
    out: dict[str, Any] = {}
    for key in sorted(payload):
        value = payload[key]
        if value is None:
            # An explicitly absent field stays absent rather than becoming zero.
            continue
        parser = schema.get(key)
        if parser is None:
            # Private first, so the researcher is told *why* rather than "unknown".
            assert_public_metric_name(key, f"payload key {key!r}")
            raise ResearchError(
                f"payload key {key!r} is not part of the {platform!r} public schema: "
                f"{', '.join(sorted(schema))}. An unrecognised key is refused rather "
                "than dropped, because a silently dropped field is a metric somebody "
                "believes they recorded."
            )
        out[key] = parser(value, f"payload {key}")
    return out


@dataclass(frozen=True)
class IngestionEnvelope:
    """Metadata captured outside this system, before this system believes it.

    One shape for every future connector. `evidence_ref` is required and not
    defaulted: an externally captured number without something a reader can
    check is an assertion, and the rest of this package refuses those already.
    """

    platform: str
    url: str
    captured_at: dt.date
    capture_method: CaptureMethod
    evidence_ref: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    evidence_kind: str = "observation"
    captured_by: str = ""
    query_id: str = ""
    rank: int | None = None
    note: str = ""

    def __post_init__(self) -> None:
        assert_known_platform(self.platform, "envelope platform")
        assert_reference(self.url, "envelope url")
        assert_reference(self.evidence_ref, "envelope evidence_ref")
        assert_text(self.evidence_kind, "envelope evidence_kind")
        if not isinstance(self.captured_at, dt.date):
            raise ResearchError("an ingestion envelope must record the day it was captured")
        if not isinstance(self.capture_method, CaptureMethod):
            raise ResearchError(
                "an ingestion envelope must say how the metadata was captured"
            )
        if self.query_id:
            assert_research_id(self.query_id, "discovery query")
        canonical = canonicalize(self.url)
        if canonical.platform != self.platform:
            raise ResearchError(
                f"envelope says platform {self.platform!r} but {self.url!r} is a "
                f"{canonical.platform!r} URL"
            )
        object.__setattr__(self, "payload", validate_payload(self.platform, self.payload))

    @property
    def canonical(self):
        return canonicalize(self.url)

    @property
    def identity(self) -> ContentIdentity:
        return self.canonical.identity

    @property
    def evidence(self) -> Evidence:
        return Evidence(kind=self.evidence_kind, ref=self.evidence_ref, note=self.note)

    @property
    def has_metrics(self) -> bool:
        return any(key in self.payload for key in _SNAPSHOT_KEYS)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> IngestionEnvelope:
        return cls(
            platform=data["platform"],
            url=data["url"],
            captured_at=as_date(data["captured_at"], "captured_at"),
            capture_method=CaptureMethod(data["capture_method"]),
            evidence_ref=data["evidence_ref"],
            payload=data.get("payload", {}),
            evidence_kind=data.get("evidence_kind", "observation"),
            captured_by=data.get("captured_by", ""),
            query_id=data.get("query_id", ""),
            rank=data.get("rank"),
            note=data.get("note", ""),
        )


def candidate_id_for(identity: ContentIdentity) -> str:
    """A candidate's id, derived from its identity so re-ingestion is idempotent.

    Same digest rule as `snapshots.series_id`, and for the same reason: record
    ids are lowercase filenames and external ids are not.
    """
    return f"cand-{identity.platform}-{fingerprint(identity.key)}"


@dataclass(frozen=True)
class Ingested:
    """What one envelope became: a candidate, and a reading if it carried one."""

    candidate: DiscoveryCandidate
    snapshot: PublicSnapshot | None = None


def ingest_envelope(
    envelope: IngestionEnvelope,
    *,
    discovered_by: str,
    candidate_id: str = "",
    query_id: str = "",
) -> Ingested:
    """Map a validated envelope onto a candidate and, if present, one reading.

    The metrics do not land on the candidate. They land in a `PublicSnapshot`
    dated `captured_at`, because a view count is an observation of a day and the
    candidate is not dated - see `snapshots.py`.
    """
    assert_text(discovered_by, "discovered_by")
    query = query_id or envelope.query_id
    if not query:
        raise ResearchError(
            "an envelope must name the discovery query that found it, either on the "
            "envelope or at the call. Provenance is what lets a candidate found by "
            "three queries be recognised as found by three queries."
        )
    canonical = envelope.canonical
    payload = envelope.payload
    published_on = payload.get("published_on")
    if published_on is not None and published_on > envelope.captured_at:
        raise ResearchError(
            f"payload published_on {published_on} is after the capture date "
            f"{envelope.captured_at}; one of the two was read wrong"
        )

    candidate = DiscoveryCandidate(
        id=candidate_id or candidate_id_for(canonical.identity),
        platform=envelope.platform,
        original_url=canonical.original,
        canonical_url=canonical.url,
        external_id=canonical.external_id,
        discovered_on=envelope.captured_at,
        discovered_by=discovered_by,
        capture_method=envelope.capture_method,
        evidence=envelope.evidence,
        provenance=(
            DiscoveryProvenance(
                query_id=query,
                discovered_on=envelope.captured_at,
                rank=envelope.rank,
                note=envelope.note,
            ),
        ),
        title=payload.get("title", ""),
        creator=payload.get("creator", ""),
        creator_id=payload.get("creator_id", ""),
        published_on=published_on,
        duration_seconds=payload.get("duration_seconds"),
        language=payload.get("language", ""),
        region=payload.get("region", ""),
        tags=payload.get("tags", ()),
        signals=payload.get("signals", ()),
        notes=payload.get("note", ""),
    )

    snapshot: PublicSnapshot | None = None
    if envelope.has_metrics:
        snapshot = PublicSnapshot(
            metrics=PublicMetrics(
                observed_on=envelope.captured_at,
                views=payload.get("views"),
                likes=payload.get("likes"),
                comments=payload.get("comments"),
                duration_seconds=payload.get("duration_seconds"),
                channel_subscribers=payload.get("channel_subscribers"),
                note=payload.get("note", ""),
            ),
            capture_method=envelope.capture_method,
            evidence=envelope.evidence,
            captured_by=envelope.captured_by or discovered_by,
        )
    return Ingested(candidate=candidate, snapshot=snapshot)


def envelopes_from_json(data: Any) -> tuple[IngestionEnvelope, ...]:
    """One envelope or a list of them, from already-parsed JSON."""
    if isinstance(data, Mapping):
        if "envelopes" in data:
            data = data["envelopes"]
        else:
            return (IngestionEnvelope.from_dict(data),)
    if not isinstance(data, list):
        raise ResearchError(
            "an ingestion file is one envelope object, a list of them, or an object "
            f"with an 'envelopes' list; got {type(data).__name__}"
        )
    return tuple(IngestionEnvelope.from_dict(entry) for entry in data)


def load_envelopes(path: Path | str) -> tuple[IngestionEnvelope, ...]:
    """Read envelopes from a JSON file on disk. The cheap adapter, entire.

    This is the whole manual ingestion path: a researcher reads a public page,
    writes what they saw into a JSON file, and runs one command. No browser, no
    client, no key. It is the first adapter because it is the one that lets real
    research start today, and because every later connector has to produce the
    same envelope anyway.
    """
    return envelopes_from_json(read_json(Path(path)))
