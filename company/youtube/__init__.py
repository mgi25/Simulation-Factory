"""Network-free ingestion of our own channel's API readings into analytics.

## Where the network went

An earlier version of this package held the OAuth client, the token store, the
HTTP transport and the API client, and it sat under `company/`. That put a
socket, a browser launch and a credential file inside the Company OS control
plane, which is required to hold none of the three. The integration gate said so
in the only way a gate can: `company/youtube/config.py` imported
`urllib.parse`, and the boundary check that forbids `urllib` anywhere under
`company/`, `ai_platform/`, `knowledge/` and `intelligence/` had to be weakened
to let it through.

The fix was not a better exception. Fetching is a production capability and now
lives in `tools/youtube_fetch/`, which holds the credentials, talks to Google,
and writes a sanitized artifact file. This package reads that file. The two
halves share no code, no process and no import edge, and the seam between them
is a document an operator can read before believing it.

    Google OAuth / YouTube APIs
            |   tools/youtube_fetch  (production, network allowed)
      sanitized artifact JSON on disk
            |   company/youtube      (Company OS, network-free)
    validated ingestion -> AnalyticsStore

## What this package guarantees

Everything a committed record contains is a function of what the pull measured,
never of when it was fetched or where the file sits. A re-import of the same
numbers writes nothing; a pull reporting a different number for the same window
is refused as a conflict instead of overwriting the earlier reading. A metric
the API did not report produces no observation and a named reason, never a zero.
A pull that came back short names the exact ids it is missing, and that gap
travels into the `DataScope` of every reading it produced.

## What it still is not

No fetching, no scheduling, no classification, no inference. Nothing here reads
a title to decide what a video is: which deliverable a video corresponds to, and
what kind and format it belongs to, are the operator's declaration. Money does
not appear in either half - there is no monetary metric in the vocabulary and no
scope that could read one.
"""

from .artifact import (
    ANALYTICS_SCOPE,
    DATA_SCOPE,
    REQUIRED_SCOPES,
    SUPPORTED_ARTIFACT_VERSION,
    artifact_digest,
    assert_no_credentials,
    parse_artifact,
    read_artifact,
    semantic_payload,
)
from .bridge import (
    METRIC_VOCABULARY,
    MetricMapping,
    artifact_excludes,
    build_deliverable,
    build_observation,
    build_scope,
    build_source,
    observation_id_for,
    observation_identity,
    reported_range,
    resolve_metric,
    window_close,
)
from .errors import ArtifactRejected, ArtifactUnreadable, YouTubeIngestionError
from .ingest import (
    CHANNEL_EVIDENCE_LEVEL,
    VIDEO_EVIDENCE_LEVEL,
    ApiCommitOutcome,
    ApiIngestionResult,
    ArtifactDescription,
    ChannelReport,
    DeliverableAssignment,
    UnassignedVideo,
    UnavailableReading,
    assignment_template,
    commit_ingestion,
    describe_artifact,
    ingest_artifact,
    load_assignments,
    unassigned_videos,
)
from .models import (
    ANALYTICS_SOURCE,
    CHANNEL_SOURCE,
    INTERVAL_SEMANTICS,
    VIDEO_SOURCE,
    AnalyticsEvidence,
    ApiCallTrace,
    ChannelEvidence,
    MetricReading,
    VideoEvidence,
    VideoRetrieval,
    YouTubeArtifact,
)
from .store import (
    CANONICAL_FIELDS,
    RECORD_KIND,
    SCHEMA_VERSION,
    YouTubeEvidencePointer,
    YouTubeEvidenceStore,
)

__all__ = [
    "ANALYTICS_SCOPE",
    "ANALYTICS_SOURCE",
    "CANONICAL_FIELDS",
    "CHANNEL_EVIDENCE_LEVEL",
    "CHANNEL_SOURCE",
    "DATA_SCOPE",
    "INTERVAL_SEMANTICS",
    "METRIC_VOCABULARY",
    "RECORD_KIND",
    "REQUIRED_SCOPES",
    "SCHEMA_VERSION",
    "SUPPORTED_ARTIFACT_VERSION",
    "VIDEO_EVIDENCE_LEVEL",
    "VIDEO_SOURCE",
    "AnalyticsEvidence",
    "ApiCallTrace",
    "ApiCommitOutcome",
    "ApiIngestionResult",
    "ArtifactDescription",
    "ArtifactRejected",
    "ArtifactUnreadable",
    "ChannelEvidence",
    "ChannelReport",
    "DeliverableAssignment",
    "MetricMapping",
    "MetricReading",
    "UnassignedVideo",
    "UnavailableReading",
    "VideoEvidence",
    "VideoRetrieval",
    "YouTubeArtifact",
    "YouTubeEvidencePointer",
    "YouTubeEvidenceStore",
    "YouTubeIngestionError",
    "artifact_digest",
    "artifact_excludes",
    "assert_no_credentials",
    "assignment_template",
    "build_deliverable",
    "build_observation",
    "build_scope",
    "build_source",
    "commit_ingestion",
    "describe_artifact",
    "ingest_artifact",
    "load_assignments",
    "observation_id_for",
    "observation_identity",
    "parse_artifact",
    "read_artifact",
    "reported_range",
    "resolve_metric",
    "semantic_payload",
    "unassigned_videos",
    "window_close",
]
