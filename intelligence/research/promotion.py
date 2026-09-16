"""The one gate between a cheap candidate and an expensive research thread.

`promote_candidate` is the only function in this package that turns a
`DiscoveryCandidate` into a `ResearchSource`, and it is a function rather than a
method so the refusal is in one readable place:

- the candidate must be **screened in**. A screened-out candidate cannot become
  a source at all, and a candidate nobody has screened cannot either;
- the researcher supplies the `ResearchConfidence` and the `RightsStatus`. They
  are judgements, and there is no default that could be honest;
- the `DiscoveryOrigin` carries the original URL, the canonical URL, the capture
  method and every query that found it, so promotion loses nothing;
- public readings are not copied. They live in the `SnapshotSeries`, which is
  keyed on the content identity and therefore already belongs to the source.

## The screening decision is not asked for twice

A promoted source arrives at `ResearchStage.SCREENED`, not `DISCOVERED`, and it
arrives with the screener's own reason and date on the transition. The
candidate queue's `SCREENED_IN` and the source lifecycle's `SCREENED` are the
same judgement - somebody looked and thought it was worth an analyst's time -
and making a researcher record it twice would cost a second decision to learn
nothing. Without this the cost tier moves *backwards* on promotion, which is
how the duplication was found.

## Why rights cannot loosen here

`RightsStatus` already refuses a local copy without a named authoriser, and
this function adds nothing that could satisfy that requirement on a caller's
behalf. Promotion moves a link and some public numbers into a different record
type; it does not acquire anything, and there is no argument that would make it
do so. `LINK_ONLY` is the default because it is what the discovery queue
actually holds.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from intelligence.research.common import (
    Evidence,
    ResearchConfidence,
    assert_research_id,
    assert_text,
)
from intelligence.research.discovery import (
    CandidateState,
    DiscoveryCandidate,
    screen_candidate,
)
from intelligence.research.errors import ResearchError
from intelligence.research.lifecycle import ResearchStage, advance_source
from intelligence.research.provenance import DiscoveryOrigin
from intelligence.research.snapshots import SnapshotSeries
from intelligence.research.sources import (
    COPY_STATUSES,
    ResearchSource,
    RightsStatus,
    SourceType,
)


@dataclass(frozen=True)
class PromotionResult:
    """The new source, the candidate that now points at it, and its readings.

    All three are returned because all three changed. A promotion that returned
    only the source would leave the candidate claiming to be screened in, and
    the next scheduled query would offer it for promotion again.
    """

    source: ResearchSource
    candidate: DiscoveryCandidate
    series: SnapshotSeries | None = None


def promote_candidate(
    candidate: DiscoveryCandidate,
    *,
    source_id: str,
    source_type: SourceType,
    confidence: ResearchConfidence,
    promoted_by: str,
    on: dt.date,
    reason: str,
    rights: RightsStatus = RightsStatus.LINK_ONLY,
    series: SnapshotSeries | None = None,
    title: str = "",
    notes: str = "",
    tags: tuple[str, ...] = (),
    local_copy_ref: str = "",
    rights_basis: str = "",
) -> PromotionResult:
    """Turn a screened-in candidate into a research source. The only path there.

    Raises rather than returning anything partial. The two refusals worth
    knowing: a candidate that was screened out cannot be promoted by any
    argument combination, and a source cannot be built without a title - a
    thread nobody can name is a thread nobody will find.
    """
    assert_research_id(source_id, "source")
    assert_text(promoted_by, "promoted_by")
    assert_text(reason, "promotion reason")

    if candidate.state is CandidateState.SCREENED_OUT:
        raise ResearchError(
            f"candidate {candidate.id!r} was screened out ({candidate.rejection_reason!r}) "
            "and cannot be promoted. Screening out is a decision with an author and a "
            "date; promoting past it would erase both. Record a new candidate citing "
            "this one if the judgement has changed."
        )
    if candidate.state is not CandidateState.SCREENED_IN:
        raise ResearchError(
            f"candidate {candidate.id!r} is {candidate.state.value!r}; only a "
            "screened-in candidate can be promoted. Screening is where a person "
            "decides, and promotion is what that decision buys."
        )

    source_title = title or candidate.title
    if not source_title.strip():
        raise ResearchError(
            f"candidate {candidate.id!r} has no title and none was supplied. A research "
            "source is the anchor of a thread, and an unnamed thread is unfindable."
        )

    if rights in COPY_STATUSES and not (local_copy_ref.strip() and rights_basis.strip()):
        raise ResearchError(
            f"promotion to rights {rights.value!r} needs both a local_copy_ref and a "
            "rights_basis naming who authorised the copy. Nothing in the ingestion "
            "layer fetches media - a local copy exists because a person supplied it."
        )

    metrics = None
    if series is not None:
        if series.identity.key != candidate.identity.key:
            raise ResearchError(
                f"series {series.id!r} holds {series.identity.key!r}, not the candidate's "
                f"{candidate.identity.key!r}"
            )
        latest = series.latest
        if latest is not None:
            if latest.observed_on < candidate.discovered_on:
                raise ResearchError(
                    f"the newest reading in {series.id!r} is from {latest.observed_on}, "
                    f"before the candidate was discovered on {candidate.discovered_on}. "
                    "Record a reading under the day it was taken."
                )
            metrics = latest.metrics

    screened = [
        step for step in candidate.history if step.to_state is CandidateState.SCREENED_IN
    ]
    screened_step = screened[-1] if screened else None

    origin = DiscoveryOrigin(
        candidate_id=candidate.id,
        platform=candidate.platform,
        original_url=candidate.original_url,
        canonical_url=candidate.canonical_url,
        capture_method=candidate.capture_method,
        provenance=candidate.provenance,
        external_id=candidate.external_id,
        screened_by=screened_step.by if screened_step else "",
        screened_on=screened_step.on if screened_step else None,
    )

    source = ResearchSource(
        id=source_id,
        platform=candidate.platform,
        reference=candidate.canonical_url,
        title=source_title,
        source_type=source_type,
        observed_on=candidate.discovered_on,
        rights=rights,
        confidence=confidence,
        discovered_by=candidate.discovered_by,
        creator=candidate.creator,
        published_on=candidate.published_on,
        metrics=metrics,
        local_copy_ref=local_copy_ref,
        rights_basis=rights_basis,
        notes=notes or candidate.notes,
        tags=candidate.tags + tuple(t for t in tags if t not in candidate.tags),
        origin=origin,
    )

    # The screener already decided this was worth an analyst's time, with a
    # reason and a date. Carry that decision rather than asking for it again.
    source = advance_source(
        source,
        ResearchStage.SCREENED,
        on=screened_step.on if screened_step else on,
        by=screened_step.by if screened_step else promoted_by,
        reason=screened_step.reason if screened_step else reason,
        evidence=(
            Evidence(
                kind="observation",
                ref=candidate.canonical_url,
                note=f"promoted from discovery candidate {candidate.id}",
            ),
        ),
    )

    promoted = screen_candidate(
        candidate,
        CandidateState.PROMOTED_TO_SOURCE,
        on=on,
        by=promoted_by,
        reason=reason,
        promoted_source_id=source_id,
    )
    updated_series = None if series is None else series.watching(source_id=source_id)
    return PromotionResult(source=source, candidate=promoted, series=updated_series)
