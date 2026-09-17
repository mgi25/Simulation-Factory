"""One exception per failure class, for a layer that only ever reads a file.

The vocabulary here is short because the surface is. Everything that can fail
while talking to Google - an expired grant, a revoked refresh token, a quota, a
missing permission - fails in `tools/youtube_fetch/`, outside Company OS, and
never reaches this package. What arrives here is an artifact file on disk that
either parses into a trustworthy record or does not.

The two ways it does not are different problems with different fixes, so they
are different types. `ArtifactUnreadable` is the file: absent, unreadable, not
UTF-8, not JSON. Somebody re-runs the fetch. `ArtifactRejected` is the contents:
a version this parser does not know, a metric marked available with no value, an
endpoint with its query string still attached, a grant this ingester does not
admit. Nobody re-runs anything - the artifact is wrong, and importing it would
put a number into the ledger with nothing behind it.

Both subclass `company.analytics.errors.AnalyticsError`, which is a `ValueError`
and a `CompanyOSError`. That is deliberate rather than incidental: a caller
already catching analytics errors around an import keeps working, and an
ingestion failure is an analytics failure - it is a reading that did not become
a record.
"""

from __future__ import annotations

from company.analytics.errors import AnalyticsError


class YouTubeIngestionError(AnalyticsError):
    """An analytics-API artifact could not become trustworthy evidence."""


class ArtifactUnreadable(YouTubeIngestionError):
    """The artifact file is missing, unreadable, or not the JSON it claims to be."""


class ArtifactRejected(YouTubeIngestionError):
    """The artifact parsed, and what it says disqualifies it from being ingested.

    A whole-file refusal rather than a row one. A defect in a single metric
    reading becomes a diagnostic on the ingestion result and costs that one
    observation; this is the class of problem where reading on would produce
    records nobody could trace back to a reading somebody took.
    """


__all__ = [
    "ArtifactRejected",
    "ArtifactUnreadable",
    "YouTubeIngestionError",
]
