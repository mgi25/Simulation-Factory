"""The queue in front of the research workflow: what to look for, and what turned up.

Phase 3 built the records that describe research once it is worth doing. This
is the cheap layer in front of them. A `DiscoveryCandidate` costs a URL and a
handful of public numbers; a `ReferenceCase` costs an analyst an afternoon. The
whole point of putting a queue between the two is that most candidates should
never reach the afternoon.

    DiscoveryQuery  what we went looking for, reusably
    DiscoveryCandidate  one thing that turned up, not yet a ResearchSource
    ScreeningDecision  a person deciding, with a reason, on a date

## A candidate is not a source, and the gap is deliberate

`ResearchSource` requires a `ResearchConfidence` - a level, a basis, and what
would overturn it. That is a judgement, and it is not one anybody can make
about the fortieth result of a search. A candidate requires none of it. The
cost of holding a candidate is therefore near zero, which is what makes it
affordable to hold a hundred and promote four.

## The software does not decide

There is no `auto_screen`. `screen_candidate` takes a person, a reason and a
date, and there is no path to `SCREENED_IN` that does not. The two helpers that
look like judgement - `excluded_by` and `within_freshness` - return facts about
a query the researcher wrote, and neither changes a state. Deciding whether
something is interesting is the part a person is for; the software's job is to
make sure the decision, its reason and its author survive.

## Canonical URL is checked, not trusted

A candidate's `canonical_url` and `external_id` are recomputed from
`original_url` at construction and compared. A record cannot carry a
hand-written canonical URL, because a hand-written one deduplicates against
nothing and a wrong one merges two videos.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar

from ai_platform.serde import as_date, as_opt_date, as_tuple
from intelligence.research.common import (
    Evidence,
    assert_nonempty,
    assert_reference,
    assert_research_id,
    assert_slugs,
    assert_text,
    evidence_tuple,
)
from intelligence.research.errors import ResearchError
from intelligence.research.provenance import (
    CaptureMethod,
    DiscoveryProvenance,
    merge_provenance,
)
from intelligence.research.snapshots import series_id
from intelligence.research.urls import ContentIdentity, assert_known_platform, canonicalize

LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
REGION_PATTERN = re.compile(r"^[A-Z]{2}$")
MAX_STATEMENT_CHARS = 240


def assert_line(value: str, field: str, limit: int = MAX_STATEMENT_CHARS) -> str:
    """A one-line phrase: a search term, an exclusion, an observed signal."""
    assert_text(value, field)
    if "\n" in value or "\r" in value:
        raise ResearchError(f"{field}: one line, not {value.count(chr(10)) + 1}")
    if len(value) > limit:
        raise ResearchError(
            f"{field}: {len(value)} characters exceeds the {limit}-character limit"
        )
    return value


def assert_lines(values: Any, field: str, limit: int = MAX_STATEMENT_CHARS) -> tuple[str, ...]:
    out = as_tuple(values)
    for index, value in enumerate(out):
        assert_line(value, f"{field}[{index}]", limit)
    return out


def assert_language(value: str, field: str) -> str:
    if value and not LANGUAGE_PATTERN.match(value):
        raise ResearchError(
            f"{field}: {value!r} is not a language tag such as 'en' or 'pt-BR'. "
            "Leave it empty when the language was not observed."
        )
    return value


def assert_region(value: str, field: str) -> str:
    if value and not REGION_PATTERN.match(value):
        raise ResearchError(
            f"{field}: {value!r} is not a two-letter region code such as 'BR'. "
            "Leave it empty when the region was not observed."
        )
    return value


def _assert_count(value: Any, field: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResearchError(f"{field} must be a whole number or None, got {value!r}")
    if value < 0:
        raise ResearchError(f"{field} cannot be negative, got {value}")


class QueryStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


@dataclass(frozen=True)
class DiscoveryQuery:
    """What we went looking for, stored so the next run is the same run.

    Reusable is the requirement that shapes this record. A query run twice must
    be recognisable as the same query, so it is an id-addressed file rather than
    a string typed into a terminal, and its window is `freshness_days` - a
    relative span - rather than a date that would silently mean something else
    next month.

    `terms` are free text because a search term is free text. Everything that
    will later be *compared* - format and mechanic tags - is a slug, so two
    researchers spell one concept one way.
    """

    kind: ClassVar[str] = "discovery_query"

    id: str
    platform: str
    objective: str
    terms: tuple[str, ...]
    created: dt.date
    author: str
    format_tags: tuple[str, ...] = ()
    mechanic_tags: tuple[str, ...] = ()
    language: str = ""
    region: str = ""
    freshness_days: int | None = None
    max_candidates: int | None = None
    exclusions: tuple[str, ...] = ()
    notes: str = ""
    status: QueryStatus = QueryStatus.ACTIVE

    def __post_init__(self) -> None:
        assert_research_id(self.id, "discovery query")
        assert_known_platform(self.platform, "query platform")
        assert_text(self.objective, "query objective (what we hope to learn)")
        assert_text(self.author, "query author")
        if not isinstance(self.created, dt.date):
            raise ResearchError("a discovery query must record the day it was written")
        object.__setattr__(self, "terms", assert_lines(self.terms, "terms", 120))
        assert_nonempty(
            self.terms,
            "terms",
            "a query with no search terms describes no search, and cannot be re-run",
        )
        object.__setattr__(self, "format_tags", assert_slugs(self.format_tags, "format_tags"))
        object.__setattr__(
            self, "mechanic_tags", assert_slugs(self.mechanic_tags, "mechanic_tags")
        )
        object.__setattr__(self, "exclusions", assert_lines(self.exclusions, "exclusions", 120))
        assert_language(self.language, "query language")
        assert_region(self.region, "query region")
        for field in ("freshness_days", "max_candidates"):
            value = getattr(self, field)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ResearchError(
                    f"{field} must be a whole number of at least 1, or None when the "
                    f"query sets no limit; got {value!r}"
                )

    def published_after(self, as_of: dt.date) -> dt.date | None:
        """The oldest publication date inside the freshness window, or None."""
        if self.freshness_days is None:
            return None
        return as_of - dt.timedelta(days=self.freshness_days)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryQuery:
        return cls(
            id=data["id"],
            platform=data["platform"],
            objective=data["objective"],
            terms=as_tuple(data.get("terms")),
            created=as_date(data["created"], "created"),
            author=data["author"],
            format_tags=as_tuple(data.get("format_tags")),
            mechanic_tags=as_tuple(data.get("mechanic_tags")),
            language=data.get("language", ""),
            region=data.get("region", ""),
            freshness_days=data.get("freshness_days"),
            max_candidates=data.get("max_candidates"),
            exclusions=as_tuple(data.get("exclusions")),
            notes=data.get("notes", ""),
            status=QueryStatus(data.get("status", "active")),
        )


class CandidateState(Enum):
    """Section 7 of the phase brief, as the six states a candidate can be in."""

    DISCOVERED = "discovered"
    QUEUED = "queued"
    SCREENED_IN = "screened_in"
    SCREENED_OUT = "screened_out"
    PROMOTED_TO_SOURCE = "promoted_to_source"
    ARCHIVED = "archived"


CANDIDATE_TRANSITIONS: dict[CandidateState, frozenset[CandidateState]] = {
    CandidateState.DISCOVERED: frozenset(
        {CandidateState.QUEUED, CandidateState.SCREENED_OUT, CandidateState.ARCHIVED}
    ),
    CandidateState.QUEUED: frozenset(
        {
            CandidateState.SCREENED_IN,
            CandidateState.SCREENED_OUT,
            CandidateState.ARCHIVED,
        }
    ),
    CandidateState.SCREENED_IN: frozenset(
        {
            CandidateState.PROMOTED_TO_SOURCE,
            CandidateState.SCREENED_OUT,
            CandidateState.ARCHIVED,
        }
    ),
    CandidateState.SCREENED_OUT: frozenset({CandidateState.ARCHIVED}),
    CandidateState.PROMOTED_TO_SOURCE: frozenset({CandidateState.ARCHIVED}),
    CandidateState.ARCHIVED: frozenset(),
}
"""`SCREENED_IN` may still go to `SCREENED_OUT`: a second look before promotion
is the cheap place to change your mind. Once promoted it may not, because the
source has its own lifecycle and a rejection recorded in two places is a
rejection recorded in neither."""

TERMINAL_CANDIDATE_STATES: frozenset[CandidateState] = frozenset(
    state for state, onward in CANDIDATE_TRANSITIONS.items() if not onward
)


def can_screen(current: CandidateState, target: CandidateState) -> bool:
    return target in CANDIDATE_TRANSITIONS[current]


def assert_screening(current: CandidateState, target: CandidateState) -> None:
    if can_screen(current, target):
        return
    allowed = sorted(s.value for s in CANDIDATE_TRANSITIONS[current])
    if not allowed:
        raise ResearchError(f"{current.value!r} is terminal; a candidate leaves it nowhere")
    raise ResearchError(
        f"cannot screen from {current.value!r} to {target.value!r}; "
        f"allowed from here: {', '.join(allowed)}"
    )


@dataclass(frozen=True)
class ScreeningDecision:
    """One signed screening step. The reason is the field that pays.

    Six weeks later the interesting question about a screened-out candidate is
    never which state it reached.
    """

    from_state: CandidateState
    to_state: CandidateState
    on: dt.date
    by: str
    reason: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        assert_text(self.by, "screening by (who made the call)")
        assert_text(self.reason, "screening reason")
        if not isinstance(self.on, dt.date):
            raise ResearchError("a screening decision must record the date it happened")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.from_state is self.to_state:
            raise ResearchError(
                f"screening from {self.from_state.value!r} to itself is not a decision"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScreeningDecision:
        return cls(
            from_state=CandidateState(data["from_state"]),
            to_state=CandidateState(data["to_state"]),
            on=as_date(data["on"], "on"),
            by=data["by"],
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
        )


# Fields a second discovery of the same video may fill in, but never change.
_FILLABLE: tuple[str, ...] = (
    "title",
    "creator",
    "creator_id",
    "published_on",
    "duration_seconds",
    "language",
    "region",
)


@dataclass(frozen=True)
class DiscoveryCandidate:
    """One external thing a query turned up. Cheap on purpose.

    Everything optional is optional because a discovery surface shows different
    things on different days, and an unknown field stays unknown rather than
    becoming a zero. `unknown_fields` names them, so a screener can see what
    they are deciding without.

    No public metrics live here. They live in the `SnapshotSeries` named by
    `series_id`, because a metric is an observation of a day and this record is
    not dated - see `snapshots.py`.
    """

    kind: ClassVar[str] = "discovery_candidate"

    id: str
    platform: str
    original_url: str
    canonical_url: str
    discovered_on: dt.date
    discovered_by: str
    capture_method: CaptureMethod
    evidence: Evidence
    provenance: tuple[DiscoveryProvenance, ...]
    external_id: str = ""
    title: str = ""
    creator: str = ""
    creator_id: str = ""
    published_on: dt.date | None = None
    duration_seconds: int | None = None
    language: str = ""
    region: str = ""
    tags: tuple[str, ...] = ()
    signals: tuple[str, ...] = ()
    state: CandidateState = CandidateState.DISCOVERED
    history: tuple[ScreeningDecision, ...] = ()
    rejection_reason: str = ""
    promoted_source_id: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "discovery candidate")
        assert_known_platform(self.platform, "candidate platform")
        assert_reference(self.original_url, "original_url")
        assert_reference(self.canonical_url, "canonical_url")
        assert_text(self.discovered_by, "discovered_by")
        if not isinstance(self.capture_method, CaptureMethod):
            raise ResearchError(
                f"candidate {self.id!r}: capture_method must be a CaptureMethod - how "
                "this reached us is part of what it is worth"
            )
        if not isinstance(self.evidence, Evidence):
            raise ResearchError(
                f"candidate {self.id!r}: an Evidence pointer records what was captured "
                "and where a reader can check it"
            )
        if not isinstance(self.discovered_on, dt.date):
            raise ResearchError("a candidate must record the day it was discovered")

        # The canonical URL is derived, never asserted. A hand-written one
        # deduplicates against nothing; a wrong one merges two videos into one.
        canonical = canonicalize(self.original_url)
        if canonical.platform != self.platform:
            raise ResearchError(
                f"candidate {self.id!r}: platform is {self.platform!r} but "
                f"{self.original_url!r} is a {canonical.platform!r} URL"
            )
        if canonical.url != self.canonical_url or canonical.external_id != self.external_id:
            raise ResearchError(
                f"candidate {self.id!r}: {self.original_url!r} canonicalizes to "
                f"{canonical.url!r} (id {canonical.external_id!r}), not to "
                f"{self.canonical_url!r} (id {self.external_id!r}). The canonical form "
                "is computed from the original, never typed beside it."
            )

        object.__setattr__(self, "provenance", tuple(self.provenance))
        assert_nonempty(
            self.provenance,
            "provenance",
            "name the discovery query that found this, so the queue keeps why we looked",
        )
        for entry in self.provenance:
            if not isinstance(entry, DiscoveryProvenance):
                raise ResearchError(f"candidate {self.id!r}: not a DiscoveryProvenance")
        first_seen = min(entry.discovered_on for entry in self.provenance)
        if self.discovered_on != first_seen:
            raise ResearchError(
                f"candidate {self.id!r}: discovered_on {self.discovered_on} is not the "
                f"earliest provenance date {first_seen}. First seen is derived from the "
                "queries that saw it, so the two cannot disagree."
            )

        if self.published_on is not None and self.published_on > self.discovered_on:
            raise ResearchError(
                f"candidate {self.id!r}: published_on {self.published_on} is after "
                f"discovered_on {self.discovered_on}"
            )
        _assert_count(self.duration_seconds, f"candidate {self.id!r} duration_seconds")
        assert_language(self.language, f"candidate {self.id!r} language")
        assert_region(self.region, f"candidate {self.id!r} region")
        object.__setattr__(self, "tags", assert_slugs(self.tags, "candidate tags"))
        object.__setattr__(self, "signals", assert_lines(self.signals, "candidate signals"))

        if self.history:
            expected = CandidateState.DISCOVERED
            for step in self.history:
                if step.from_state is not expected:
                    raise ResearchError(
                        f"candidate {self.id!r}: history jumps from {expected.value!r} to "
                        f"a decision that starts at {step.from_state.value!r}"
                    )
                expected = step.to_state
            if expected is not self.state:
                raise ResearchError(
                    f"candidate {self.id!r}: history ends at {expected.value!r} but state "
                    f"is {self.state.value!r}"
                )
        elif self.state is not CandidateState.DISCOVERED:
            raise ResearchError(
                f"candidate {self.id!r}: state {self.state.value!r} with no history. Use "
                "screen_candidate so every state change records who decided and why."
            )

        reached = {step.to_state for step in self.history} | {self.state}
        if CandidateState.SCREENED_OUT in reached:
            if not self.rejection_reason.strip():
                raise ResearchError(
                    f"candidate {self.id!r} was screened out with no rejection_reason. "
                    "The reason is the only part of a rejection worth keeping."
                )
            assert_line(self.rejection_reason, "rejection_reason")
        elif self.rejection_reason.strip():
            raise ResearchError(
                f"candidate {self.id!r}: rejection_reason is set on a candidate in "
                f"{self.state.value!r}, which was never screened out"
            )

        if self.promoted_source_id:
            assert_research_id(self.promoted_source_id, "promoted source")
            if CandidateState.PROMOTED_TO_SOURCE not in reached:
                raise ResearchError(
                    f"candidate {self.id!r}: promoted_source_id names a source but the "
                    f"candidate is {self.state.value!r}. Use promote_candidate."
                )
        elif self.state is CandidateState.PROMOTED_TO_SOURCE:
            raise ResearchError(
                f"candidate {self.id!r} is promoted but names no source id"
            )

    # -- identity ---------------------------------------------------------

    @property
    def identity(self) -> ContentIdentity:
        return ContentIdentity(
            platform=self.platform,
            external_id=self.external_id,
            canonical_url=self.canonical_url,
        )

    @property
    def series_id(self) -> str:
        """The `SnapshotSeries` holding this candidate's public readings."""
        return series_id(self.identity)

    @property
    def query_ids(self) -> tuple[str, ...]:
        out: list[str] = []
        for entry in self.provenance:
            if entry.query_id not in out:
                out.append(entry.query_id)
        return tuple(out)

    @property
    def unknown_fields(self) -> tuple[str, ...]:
        """What nobody has observed yet. Unknown, not zero and not empty string."""
        return tuple(
            name
            for name in _FILLABLE
            if getattr(self, name) in (None, "")
        )

    @property
    def is_screened_in(self) -> bool:
        return self.state is CandidateState.SCREENED_IN

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DiscoveryCandidate:
        return cls(
            id=data["id"],
            platform=data["platform"],
            original_url=data["original_url"],
            canonical_url=data["canonical_url"],
            discovered_on=as_date(data["discovered_on"], "discovered_on"),
            discovered_by=data["discovered_by"],
            capture_method=CaptureMethod(data["capture_method"]),
            evidence=Evidence.from_dict(data["evidence"]),
            provenance=tuple(
                DiscoveryProvenance.from_dict(p) for p in data.get("provenance", ())
            ),
            external_id=data.get("external_id", ""),
            title=data.get("title", ""),
            creator=data.get("creator", ""),
            creator_id=data.get("creator_id", ""),
            published_on=as_opt_date(data.get("published_on"), "published_on"),
            duration_seconds=data.get("duration_seconds"),
            language=data.get("language", ""),
            region=data.get("region", ""),
            tags=as_tuple(data.get("tags")),
            signals=as_tuple(data.get("signals")),
            state=CandidateState(data.get("state", "discovered")),
            history=tuple(ScreeningDecision.from_dict(h) for h in data.get("history", ())),
            rejection_reason=data.get("rejection_reason", ""),
            promoted_source_id=data.get("promoted_source_id", ""),
            notes=data.get("notes", ""),
        )


def screen_candidate(
    candidate: DiscoveryCandidate,
    to_state: CandidateState,
    *,
    on: dt.date,
    by: str,
    reason: str,
    evidence: tuple[Evidence, ...] = (),
    rejection_reason: str = "",
    promoted_source_id: str = "",
) -> DiscoveryCandidate:
    """Move a candidate, appending a signed decision. A person, always.

    There is no variant of this that decides for itself. Nothing in this
    package reads a candidate's numbers and concludes it is interesting -
    section 7 of the brief draws that line, and it is the same line
    `score_opportunity` draws for prioritisation: the software adds up and
    keeps the record, the researcher supplies the judgement.

    The two states that carry a consequence collect it in the same call, so no
    intermediate record exists claiming to be screened out with no reason or
    promoted to nothing. `promotion.promote_candidate` supplies the source id.
    """
    assert_screening(candidate.state, to_state)
    if to_state is CandidateState.PROMOTED_TO_SOURCE and not promoted_source_id:
        raise ResearchError(
            f"candidate {candidate.id!r} cannot be promoted without the id of the "
            "source it became. Use promotion.promote_candidate, which builds both."
        )
    changes: dict[str, Any] = {
        "state": to_state,
        "history": (
            *candidate.history,
            ScreeningDecision(
                from_state=candidate.state,
                to_state=to_state,
                on=on,
                by=by,
                reason=reason,
                evidence=evidence,
            ),
        ),
    }
    if to_state is CandidateState.SCREENED_OUT:
        changes["rejection_reason"] = rejection_reason or reason
    if promoted_source_id:
        changes["promoted_source_id"] = promoted_source_id
    return replace(candidate, **changes)


def queue_candidate(
    candidate: DiscoveryCandidate, *, on: dt.date, by: str, reason: str
) -> DiscoveryCandidate:
    """Accept a candidate into the screening queue. Tier 1 to tier 2."""
    return screen_candidate(candidate, CandidateState.QUEUED, on=on, by=by, reason=reason)


def candidate_conflicts(
    existing: DiscoveryCandidate, incoming: DiscoveryCandidate
) -> tuple[str, ...]:
    """Fields where a second sighting disagrees with the first, sorted.

    Reported rather than resolved. A title that changed is a fact about the
    channel; a duration that changed is usually a capture error. Neither is
    something this layer should silently pick a winner for.
    """
    out = []
    for name in _FILLABLE:
        before = getattr(existing, name)
        after = getattr(incoming, name)
        if before in (None, "") or after in (None, ""):
            continue
        if before != after:
            out.append(f"{name}: {before!r} != {after!r}")
    return tuple(sorted(out))


def merge_candidates(
    existing: DiscoveryCandidate, incoming: DiscoveryCandidate
) -> DiscoveryCandidate:
    """Fold a re-discovery into the candidate we already hold.

    Three rules, and the third is the one that matters:

    - provenance is unioned, so every query that found it is kept (section 4);
    - unknown fields are filled in, because an unknown was never a value;
    - **a known field is never overwritten.** The first sighting is what we
      actually saw first, and screening state survives re-discovery untouched -
      otherwise a scheduled query would quietly resurrect a rejected candidate.
    """
    if existing.identity.key != incoming.identity.key:
        raise ResearchError(
            f"cannot merge {incoming.id!r} into {existing.id!r}: they are different "
            f"content ({incoming.identity.key!r} vs {existing.identity.key!r})"
        )
    fills = {
        name: getattr(incoming, name)
        for name in _FILLABLE
        if getattr(existing, name) in (None, "") and getattr(incoming, name) not in (None, "")
    }
    provenance = merge_provenance(existing.provenance, incoming.provenance)
    tags = existing.tags + tuple(t for t in incoming.tags if t not in existing.tags)
    signals = existing.signals + tuple(s for s in incoming.signals if s not in existing.signals)
    return replace(
        existing,
        provenance=provenance,
        discovered_on=min(entry.discovered_on for entry in provenance),
        tags=tags,
        signals=signals,
        **fills,
    )


def excluded_by(query: DiscoveryQuery, candidate: DiscoveryCandidate) -> str:
    """The query's own exclusion term that appears in the title, or "".

    Advisory. It reports what the researcher's own exclusion list matches; it
    does not screen anything out, and a match is not a verdict.
    """
    haystack = candidate.title.lower()
    if not haystack:
        return ""
    for term in query.exclusions:
        if term.lower() in haystack:
            return term
    return ""


def within_freshness(
    query: DiscoveryQuery, candidate: DiscoveryCandidate, as_of: dt.date
) -> bool | None:
    """Is the candidate inside the query's freshness window?

    `None` means the question cannot be answered: the query set no window, or
    the publication date was never observed. It is deliberately not `False` -
    "too old" and "we do not know how old" are different facts, and collapsing
    them is how an unknown becomes a rejection.
    """
    cutoff = query.published_after(as_of)
    if cutoff is None or candidate.published_on is None:
        return None
    return candidate.published_on >= cutoff
