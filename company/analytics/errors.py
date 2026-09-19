"""One exception per failure class, so a caller can tell bad data from a lie.

The split matters here for the same reason it matters in finance, with one
addition. A malformed observation is a data problem somebody repairs. An
overclaim is not: it is a record that would read as knowledge while resting on
nothing, and code that catches it and continues has published the overclaim.

`OverclaimRefused` is therefore its own type and is raised at construction. The
whole purpose of this subsystem is that a number it reports can be traced to a
reading somebody took, and a conclusion it reports can be traced to a design
that could have produced it. A caller that wants the conclusion anyway has to
weaken the claim, not catch an exception.
"""

from __future__ import annotations

from company.validation.errors import CompanyOSError, ValidationError


class AnalyticsError(CompanyOSError, ValueError):
    """An analytics record that would mislead the company if it were stored."""


class ProvenanceViolation(AnalyticsError):
    """A measurement claimed a source that could not have produced it.

    Separate because there is no repair that keeps the number. A retention
    figure attributed to a public page reading is not a retention figure with a
    bad citation - nobody can read retention off a public page, so the value
    itself came from somewhere else, and the honest fix is to delete it or name
    the authenticated export it really came from.
    """


class EvidenceRequired(AnalyticsError):
    """An observation, a result or a learning pointed at nothing checkable.

    Section 24: no learning without evidence. A statement with no pointer
    behind it is something somebody believed after watching a video, and a
    company that plans on those is guessing with a changelog.
    """


class OverclaimRefused(AnalyticsError):
    """A record tried to conclude more than its design can support.

    The three shapes this takes: a causal claim from a comparison that did not
    control assignment, a durable learning that generalises from one
    observation, and a hypothesis promoted to supported without an experiment
    result behind it. All three are refused at construction rather than flagged
    in a field, because a flagged overclaim still reads as a conclusion.
    """


class LedgerViolation(AnalyticsError):
    """Recorded observation history was about to be overwritten.

    Section 4: a video at one hour and the same video at thirty days are two
    observations, not one observation that changed. This fires when the same
    record id is written twice with different bytes, which is the only way the
    file-backed store can lose a reading somebody actually took.
    """


class StudioExportRejected(AnalyticsError):
    """A Studio export file may not be ingested at all.

    Whole-file refusals rather than row ones: an export whose provenance does
    not assert our own channel, a header no schema recognises, a declaration of
    what the file covers that the file contradicts. A row-level defect becomes a
    diagnostic on the ingestion result instead; this is the class of problem
    where reading on would produce records nobody could trace to a real reading.
    """


class StudioValueError(AnalyticsError):
    """One cell could not honestly become a number.

    Raised per cell and normally caught: `studio_ingest.py` turns it into a row
    diagnostic naming the file, the row, the column and the reason, and produces
    no observation for that cell. Empty, malformed and locale-ambiguous cells
    all arrive here, and none of them leaves as a zero.

    `ambiguous` separates the cell nobody can read from the cell that reads two
    ways. They need different fixes - a correction against a declared number
    format - so the ingester reports them as different kinds of problem rather
    than as one bucket of bad cells.
    """

    def __init__(self, message: str, *, ambiguous: bool = False) -> None:
        super().__init__(message)
        self.ambiguous = ambiguous


class AnalyticsIntegrityError(ValidationError):
    """One or more cross-record analytics invariants are broken, reported together."""
