"""The pull an imported number came off, identified by what it measured.

## A file has bytes to digest; an API response does not

`studio_source.py` can point at a file and a SHA-256 of its exact bytes, and
that digest is the whole of its guarantee: re-export, re-digest, and see whether
you are looking at the same file. An API pull has no such object. Two requests
made a minute apart return responses that differ in their latency, their byte
count, their quota headers and the instant they were made, and none of those
differences is a difference in what the channel measured.

So the identity of an API source is a digest over the artifact's *semantic
payload* - what the APIs reported - and everything describing the pull itself is
deliberately outside it. The consequence is the point: two pulls of the same
window that agree produce the same `source_id`, the same observations and the
same bytes, so a replay is a no-op rather than a second source record claiming
the same readings under a different name. A pull that disagrees produces a
different digest, and the disagreement surfaces as a conflict instead of an
overwrite.

## No `exported_at`, no `imported_at`, and that is the design

`StudioExportSource` carries both, because a human downloaded a file at a moment
and imported it at another, and those two moments are facts about a file that
exists. This record carries neither. A fetch instant stored here would travel
into every observation built off the source and make the second pull of an
unchanged window a different record - which is exactly the failure this layer
exists to prevent. When the reading was taken is answered by the window it
covers, which is on the record as `reported_range`, and the evidence envelope
under `company/youtube/store.py` keeps the fetch-time detail out of the ledger.

## Own channel, asserted deliberately, or no import

Section 2 of the brief draws the same line here as it does for Studio exports,
and for the same reason: private metrics exist in this package only because the
access was authenticated access to a channel we own. So this record refuses any
provenance whose source is not `OWN_ANALYTICS_API`, requires `channel_ref` to
name which channel of ours it is, and requires `granted_scopes` to record what
the pull was actually authorized to read. A scraped page with these numbers in
it cannot be given a source record, so it cannot reach the ingester.

`granted_scopes` is checked rather than merely recorded. The authority behind a
private reading is the grant, so an artifact produced under a grant this
ingester does not recognise is refused at the door. Widening the accepted set is
a review, not an import.

## A sibling of `StudioExportSource`, never a widening of it

The two records answer the same question about two different kinds of pull, and
the temptation is to add three optional fields to the Studio record and let it
serve both. That ends with a record where half the fields are None and no reader
can tell which half applies. They stay separate, they are stored under separate
kinds, and `studio_source.py` is untouched by this file existing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    DataSource,
    Provenance,
    assert_prose,
    assert_record_id,
    assert_ref,
    ref_tuple,
    text_tuple,
)
from .errors import AnalyticsError, ProvenanceViolation
from .studio_schema import TemporalSemantics
from .windows import DateRange

# Bumped when a change here would read the same artifact differently. Recorded
# on every source so a later reader can tell which parser produced a figure.
API_ARTIFACT_PARSER_VERSION = "youtube-api-artifact/1"

# Twelve hex characters name the pull in a note or an evidence reference;
# sixteen name it in a record id. Both are prefixes of the same digest, so a
# reader who has one can find the other.
SHORT_DIGEST_CHARS = 12
SOURCE_ID_DIGEST_CHARS = 16

# What every observation off an API pull says about where it came from. One
# sentence, in one place, because it is written into the ledger and a second
# wording would read as a second kind of pull.
EVIDENCE_NOTE = "YouTube Analytics API v2 reports.query artifact, ingested read-only"


@dataclass(frozen=True)
class ApiArtifactSource:
    """One analytics-API artifact, identified by what it measured, not when it was fetched.

    Immutable, like everything else this package stores. A second pull of the
    same window reporting the same numbers rebuilds an identical record; a pull
    that reports anything different is a different digest and therefore a
    different source.
    """

    source_id: str
    digest: str
    api: str
    channel_ref: str
    semantics: TemporalSemantics
    reported_range: DateRange
    provenance: Provenance
    granted_scopes: tuple[str, ...]
    complete: bool = True
    excludes: tuple[str, ...] = ()
    parser_version: str = API_ARTIFACT_PARSER_VERSION
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_id", assert_record_id(self.source_id, "source_id")
        )
        object.__setattr__(self, "digest", _digest(self.digest))
        object.__setattr__(self, "api", assert_prose(self.api, "api"))
        object.__setattr__(
            self, "channel_ref", assert_ref(self.channel_ref, "channel_ref")
        )
        object.__setattr__(
            self, "parser_version", assert_prose(self.parser_version, "parser_version")
        )
        object.__setattr__(
            self,
            "granted_scopes",
            ref_tuple(self.granted_scopes, "granted_scopes"),
        )
        object.__setattr__(self, "excludes", text_tuple(self.excludes, "excludes"))
        if self.note:
            object.__setattr__(self, "note", assert_prose(self.note, "source note"))

        if not self.granted_scopes:
            raise AnalyticsError(
                f"source {self.source_id}: an API pull is admissible because it was "
                "authorized, so the grant it ran under is recorded with it. A source "
                "with no granted scope cannot say what made its readings readable"
            )
        if not isinstance(self.provenance, Provenance):
            raise AnalyticsError(
                f"source {self.source_id}: provenance must be a Provenance record"
            )
        self._assert_first_party()

        if not isinstance(self.semantics, TemporalSemantics):
            raise AnalyticsError(
                f"source {self.source_id}: semantics must be a TemporalSemantics, got "
                f"{self.semantics!r}"
            )
        if self.semantics is TemporalSemantics.INTERVAL and not isinstance(
            self.reported_range, DateRange
        ):
            raise AnalyticsError(
                f"source {self.source_id}: an interval pull must say which days it "
                "covers. A measurement of a bounded stretch of time with no stated "
                "bounds is not a measurement of anything"
            )
        if not isinstance(self.complete, bool):
            raise AnalyticsError(
                f"source {self.source_id}: completeness must be a bool, got "
                f"{self.complete!r}"
            )
        if not self.complete and not self.excludes:
            raise AnalyticsError(
                f"source {self.source_id}: an incomplete pull must say what it is "
                "missing by name. 'partial' with no description is an unknown with a "
                "digest attached to it"
            )

    def _assert_first_party(self) -> None:
        """One deliberate assertion of ownership, or no import.

        `effective_source` is not consulted, for the reason `studio_source.py`
        gives: a manual entry transcribed off an API response is a person
        retyping numbers, and this parser reads an artifact. Only a record that
        says the numbers came off our own authenticated Analytics API pull is
        accepted, so there is no spelling of provenance under which somebody
        else's channel becomes admissible.
        """
        if self.provenance.source is not DataSource.OWN_ANALYTICS_API:
            raise ProvenanceViolation(
                f"source {self.source_id}: this ingester reads authenticated pulls of "
                f"our own channel, and {self.provenance.source.value!r} is not one. "
                f"Only {DataSource.OWN_ANALYTICS_API.value!r} may be ingested here. A "
                "public page, a third-party estimate or a competitor dashboard can "
                "carry the same metric names and none of the authority: those numbers "
                "belong in research, as public figures, with no private metric among "
                "them"
            )

    @property
    def short_digest(self) -> str:
        """Twelve hex characters: enough to name the pull in an id or a note."""
        return self.digest[:SHORT_DIGEST_CHARS]

    @property
    def coverage_key(self) -> str:
        """What this pull measures, as one string an observation id can hash.

        Only `INTERVAL` exists in this version: the Analytics API reports a
        bounded window and nothing else, and a cumulative total read off the
        Data API is a different reading with a different source record.
        """
        return f"interval@{self.reported_range}"

    @property
    def coverage_sentence(self) -> str:
        """The same thing in words, for the note on each observation."""
        return (
            f"measured over {self.reported_range} "
            f"({self.reported_range.days} day(s)) and nothing outside it"
        )

    def evidence(self) -> Evidence:
        """The pointer every observation off this pull carries.

        Content-addressed rather than a path, and that is the whole reason this
        method exists. A pointer naming the artifact file on disk would put the
        operator's filename into every observation, and two identical pulls
        written to two filenames would then be two different records of the same
        reading. The digest names the numbers; the file that happened to carry
        them is recorded in the evidence envelope instead.
        """
        return artifact_evidence(self.digest)

    def observation_provenance(self) -> Provenance:
        """The provenance every observation off this pull carries.

        The source's own evidence is replaced rather than appended to, so that
        whatever the caller pointed the *source record* at - a path, a ticket, a
        run id - cannot travel into an observation and make a replay produce
        different bytes. An observation cites the pull by what it measured.
        """
        return Provenance(
            source=self.provenance.source,
            retrieved_by=self.provenance.retrieved_by,
            evidence=(self.evidence(),),
            note=self.provenance.note,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "digest": self.digest,
            "api": self.api,
            "channel_ref": self.channel_ref,
            "semantics": self.semantics.value,
            "reported_range": self.reported_range.to_dict(),
            "provenance": self.provenance.to_dict(),
            "granted_scopes": list(self.granted_scopes),
            "complete": self.complete,
            "excludes": list(self.excludes),
            "parser_version": self.parser_version,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: Any) -> ApiArtifactSource:
        if not isinstance(data, dict):
            raise AnalyticsError(f"expected an api source object, got {data!r}")
        try:
            return cls(
                source_id=data["source_id"],
                digest=data["digest"],
                api=data["api"],
                channel_ref=data["channel_ref"],
                semantics=TemporalSemantics(data["semantics"]),
                reported_range=DateRange.from_dict(data["reported_range"]),
                provenance=Provenance.from_dict(data["provenance"]),
                granted_scopes=tuple(data.get("granted_scopes") or ()),
                complete=bool(data.get("complete", True)),
                excludes=tuple(data.get("excludes") or ()),
                parser_version=data.get("parser_version", API_ARTIFACT_PARSER_VERSION),
                note=data.get("note", ""),
            )
        except KeyError as exc:
            raise AnalyticsError(f"api source: missing {exc.args[0]!r}") from None
        except ValueError as exc:
            raise AnalyticsError(f"api source: {exc}") from None


def artifact_evidence(digest: str) -> Evidence:
    """The pointer a pull is cited by, built from its digest alone.

    A module function rather than only a method, because the ingester needs the
    identical pointer twice - once for the provenance it hands the source
    record, once for the provenance it stamps on every observation - and two
    spellings of it would put two subtly different citations in the ledger for
    one pull.
    """
    return Evidence(
        kind="external",
        ref=f"youtube-api:{_digest(digest)[:SHORT_DIGEST_CHARS]}",
        note=EVIDENCE_NOTE,
    )


def source_id_for(digest: str) -> str:
    """The record id a semantic digest produces. One spelling, in one place.

    Both halves of the ingester need this string - the bridge to build the
    record, the commit to look for one already stored - and two spellings of it
    would eventually disagree by a character and write the same pull twice.
    """
    return f"ya-{_digest(digest)[:SOURCE_ID_DIGEST_CHARS]}"


def _digest(value: Any) -> str:
    """A lowercase SHA-256 hex digest, or a refusal naming why it matters."""
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise AnalyticsError(
            f"digest: {value!r} is not a lowercase SHA-256 hex digest. The digest is "
            "what makes a second pull a replay rather than an overwrite"
        )
    return value
