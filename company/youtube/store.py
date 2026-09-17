"""The artifact as it was ingested, kept whole, under one digest.

## Why the raw responses are kept at all

The analytics store holds readings: a number, a metric definition, a window, a
provenance. It deliberately holds no provider payload, because a store of
readings that also holds the JSON they came out of is two stores that can
disagree. But somebody eventually asks the question the readings cannot answer -
"what exactly did the API say" - and an ingester that discarded the answer has
made its own figures uncheckable.

So this is the other half: an append-only envelope of the artifact as it was
ingested, written with `O_EXCL` through `company.runtime.state_paths`, under a
directory the caller names. The analytics ledger cites it by digest, never by
path, so moving this directory cannot invalidate an observation.

## One digest, over a basis that is written down

The record this file replaces fingerprinted the envelope, inserted the result
into the envelope as `evidence_id`, and then fingerprinted the envelope *again*
for the pointer it returned. The second fingerprint covered a dict that now
contained the first, so one record carried two different digests and neither
described the other. A reader checking the pointer against the file would have
found a mismatch and had no way to tell which was wrong.

There is now one digest, computed once, over an explicit list of fields:

    schema_version, kind, source, artifact_digest, date_range, identity,
    normalized, raw, api_calls, ingested_from

That list is `CANONICAL_FIELDS`, and it is the whole envelope minus
`evidence_id` itself - which is exactly why `evidence_id` cannot be in the
basis, and why it is inserted after the digest is taken rather than before. The
same value is the record's `evidence_id` and the returned pointer's
`fingerprint`, so the two agree by construction rather than by being computed
the same way twice.

Credentials and authenticated headers are excluded from the basis by
construction rather than by filtering: they are never in the artifact, because
`tools/youtube_fetch` strips query strings and never writes a token, and
`company/youtube/artifact.py` refuses an artifact whose keys say otherwise. The
basis can therefore include `raw` and `api_calls` in full, which is what makes
the envelope worth keeping.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_platform.serde import dumps, fingerprint
from company.runtime.state_paths import append_json_bytes, sorted_records

from .artifact import artifact_digest
from .models import YouTubeArtifact

# The envelope schema. Bumped from the connector's version 1, whose records
# carried a per-call retrieval shape this layer no longer produces.
SCHEMA_VERSION = 2

# What kind of thing an envelope holds. One kind now: a whole sanitized pull,
# rather than the three separate channel/videos/analytics records the connector
# appended one at a time.
RECORD_KIND = "youtube_api_artifact"

# The fields the evidence digest is taken over: the whole envelope except the
# id the digest produces. Written down here so that a later reader can recompute
# it, and so that adding a field to the envelope is a deliberate decision about
# whether it belongs in the record's identity.
CANONICAL_FIELDS: tuple[str, ...] = (
    "schema_version",
    "kind",
    "source",
    "artifact_digest",
    "date_range",
    "identity",
    "normalized",
    "raw",
    "api_calls",
    "ingested_from",
)


@dataclass(frozen=True)
class YouTubeEvidencePointer:
    """Where an envelope landed and what it hashes to.

    `fingerprint` is the same value the record carries as `evidence_id` minus
    its `youtube-` prefix. A caller holding this pointer can find the file and
    check it without re-deriving anything.
    """

    record_ref: str
    fingerprint: str
    evidence_id: str
    kind: str = RECORD_KIND


class YouTubeEvidenceStore:
    """Append-only envelopes of ingested artifacts, under a caller-supplied root."""

    def __init__(self, state_dir: str | Path) -> None:
        if isinstance(state_dir, str) and not state_dir.strip():
            raise ValueError("state_dir must be an explicit non-empty path")
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.root = self.state_dir / "youtube" / "evidence"

    def append(
        self, artifact: YouTubeArtifact, *, ingested_from: str = ""
    ) -> YouTubeEvidencePointer:
        """Write one envelope. The digest is computed once and used twice."""
        envelope: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "kind": RECORD_KIND,
            "source": artifact.producer,
            "artifact_digest": artifact_digest(artifact),
            "date_range": _date_range(artifact),
            "identity": _identity(artifact),
            "normalized": artifact.normalized(),
            "raw": artifact.raw,
            "api_calls": [call.to_dict() for call in artifact.api_calls],
            "ingested_from": ingested_from,
        }
        digest = fingerprint({key: envelope[key] for key in CANONICAL_FIELDS})
        evidence_id = f"youtube-{digest}"
        envelope["evidence_id"] = evidence_id
        path = append_json_bytes(self.root, dumps(envelope).encode("utf-8"))
        return YouTubeEvidencePointer(
            record_ref=path.relative_to(self.state_dir).as_posix(),
            fingerprint=digest,
            evidence_id=evidence_id,
        )

    def records(self) -> tuple[dict[str, Any], ...]:
        """Every envelope, in the order it was appended."""
        return tuple(
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted_records(self.root)
        )


def _date_range(artifact: YouTubeArtifact) -> dict[str, str] | None:
    """The span the analytics rows cover, or None when the pull read none."""
    if not artifact.analytics:
        return None
    return {
        "start": min(r.start_date for r in artifact.analytics).isoformat(),
        "end": max(r.end_date for r in artifact.analytics).isoformat(),
    }


def _identity(artifact: YouTubeArtifact) -> dict[str, Any]:
    """Which channel and which videos this envelope is about."""
    return {
        "channel_id": artifact.channel.channel_id,
        "video_ids": [video.video_id for video in artifact.videos],
        "analytics_subjects": [report.subject_ref for report in artifact.analytics],
    }


__all__ = [
    "CANONICAL_FIELDS",
    "RECORD_KIND",
    "SCHEMA_VERSION",
    "YouTubeEvidencePointer",
    "YouTubeEvidenceStore",
]
