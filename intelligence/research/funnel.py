"""What each stage of research costs, so the expensive ones are reached on purpose.

Six tiers, cheapest first. The ordering is the whole design: a URL comparison
costs nothing, a reference analysis costs an analyst an afternoon, and the only
way the second number stays affordable is if most candidates never reach it.

    T0  identity            dedupe on platform + external id
    T1  public metadata     title, dates, public counts - one capture
    T2  screening           a person deciding, with a reason
    T3  reference analysis  the nine-section ReferenceCase
    T4  opportunity dossier evidence, limitations, format family
    T5  prototype           a recommendation the creative team acts on

## This module schedules nothing

`next_tier` returns a description of what would come next. It does not run it,
and there is no function here that does. That is deliberate and it is the
brief: the system must make it possible to stop a low-value candidate early,
which means every tier boundary is a place a person chooses to spend, not a
place a pipeline continues by default.

The tiers map onto states that already exist - `CandidateState` for the first
three, `ResearchStage` for the rest - rather than adding a parallel field that
could disagree with them. A tier is therefore derived, never stored, and cannot
drift from the record it describes.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from intelligence.research.discovery import CandidateState
from intelligence.research.errors import ResearchError
from intelligence.research.lifecycle import ResearchStage


class CostTier(Enum):
    IDENTITY = "t0_identity"
    PUBLIC_METADATA = "t1_public_metadata"
    SCREENING = "t2_screening"
    REFERENCE_ANALYSIS = "t3_reference_analysis"
    OPPORTUNITY_DOSSIER = "t4_opportunity_dossier"
    PROTOTYPE_RECOMMENDATION = "t5_prototype_recommendation"


@dataclass(frozen=True)
class TierSpec:
    """One tier: what it costs, what it produces, and when to stop here."""

    tier: CostTier
    order: int
    purpose: str
    produces: str
    stop_rule: str
    needs_judgement: bool


TIERS: tuple[TierSpec, ...] = (
    TierSpec(
        tier=CostTier.IDENTITY,
        order=0,
        purpose="Reduce a URL to a platform and an external id.",
        produces="A ContentIdentity, and a merge into an existing candidate if we have one.",
        stop_rule="Stop when the identity is already in the queue - re-analysis buys nothing.",
        needs_judgement=False,
    ),
    TierSpec(
        tier=CostTier.PUBLIC_METADATA,
        order=1,
        purpose="Record what a public page showed on one day.",
        produces="A DiscoveryCandidate and a dated PublicSnapshot.",
        stop_rule="Stop when the candidate is outside the query's window or its exclusions.",
        needs_judgement=False,
    ),
    TierSpec(
        tier=CostTier.SCREENING,
        order=2,
        purpose="A person decides whether this is worth an analyst's afternoon.",
        produces="A ScreeningDecision with a reason, an author and a date.",
        stop_rule="Screen out here. This is the last tier where rejection is nearly free.",
        needs_judgement=True,
    ),
    TierSpec(
        tier=CostTier.REFERENCE_ANALYSIS,
        order=3,
        purpose="Read the reference for its loop, its psychology and its craft.",
        produces="A ReferenceCase, including its originality boundary.",
        stop_rule="Stop if the loop turns out to be one the portfolio already runs.",
        needs_judgement=True,
    ),
    TierSpec(
        tier=CostTier.OPPORTUNITY_DOSSIER,
        order=4,
        purpose="State what we could make, with evidence and named limitations.",
        produces="An OpportunityDossier, and a scorecard against a rubric.",
        stop_rule="Stop if the dossier cannot name a format family or a viewer question.",
        needs_judgement=True,
    ),
    TierSpec(
        tier=CostTier.PROTOTYPE_RECOMMENDATION,
        order=5,
        purpose="Recommend building something, to a named reviewer.",
        produces="A source at PROTOTYPE_RECOMMENDED, with the thread behind it.",
        stop_rule="The end of research. Everything past here is production spend.",
        needs_judgement=True,
    ),
)

_BY_TIER: dict[CostTier, TierSpec] = {spec.tier: spec for spec in TIERS}

# A candidate's state says how far the cheap half of the funnel got.
_CANDIDATE_TIERS: dict[CandidateState, CostTier] = {
    CandidateState.DISCOVERED: CostTier.PUBLIC_METADATA,
    CandidateState.QUEUED: CostTier.PUBLIC_METADATA,
    CandidateState.SCREENED_IN: CostTier.SCREENING,
    CandidateState.SCREENED_OUT: CostTier.SCREENING,
    CandidateState.PROMOTED_TO_SOURCE: CostTier.SCREENING,
    CandidateState.ARCHIVED: CostTier.IDENTITY,
}

# A source's stage says how far the expensive half got.
_STAGE_TIERS: dict[ResearchStage, CostTier] = {
    ResearchStage.DISCOVERED: CostTier.PUBLIC_METADATA,
    ResearchStage.SCREENED: CostTier.SCREENING,
    ResearchStage.REFERENCE_ANALYZED: CostTier.REFERENCE_ANALYSIS,
    ResearchStage.OPPORTUNITY_CREATED: CostTier.OPPORTUNITY_DOSSIER,
    ResearchStage.REVIEWED: CostTier.OPPORTUNITY_DOSSIER,
    ResearchStage.PROTOTYPE_RECOMMENDED: CostTier.PROTOTYPE_RECOMMENDATION,
    ResearchStage.REJECTED: CostTier.SCREENING,
}


def spec(tier: CostTier) -> TierSpec:
    if tier not in _BY_TIER:
        raise ResearchError(f"unknown cost tier {tier!r}")
    return _BY_TIER[tier]


def tier_of_candidate(state: CandidateState) -> CostTier:
    """The most expensive tier a candidate in this state has been through."""
    return _CANDIDATE_TIERS[state]


def tier_of_source(stage: ResearchStage) -> CostTier:
    """The most expensive tier a source at this stage has been through."""
    return _STAGE_TIERS[stage]


def next_tier(tier: CostTier) -> TierSpec | None:
    """What the next tier would cost. Describes; never runs anything.

    Returns None at the end of the funnel. Nothing in this package calls it in
    a loop, and nothing should: the gap between two tiers is where a person
    decides whether the next one is worth paying for.
    """
    current = spec(tier)
    for candidate in TIERS:
        if candidate.order == current.order + 1:
            return candidate
    return None


def describe_funnel() -> tuple[str, ...]:
    """The funnel as one line per tier, cheapest first. For the CLI and reviews."""
    return tuple(
        f"{s.tier.value}  {s.purpose}  -> {s.produces}  [stop: {s.stop_rule}]"
        for s in TIERS
    )
