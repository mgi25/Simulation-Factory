"""The research thread's state machine, and the gates between its stages.

Section 11 of the phase brief:

    DISCOVERED -> SCREENED -> REFERENCE_ANALYZED -> OPPORTUNITY_CREATED
               -> REVIEWED -> PROTOTYPE_RECOMMENDED / REJECTED

The stages are not decoration. Three of them are gated on an artefact existing,
which is what makes this a workflow rather than a label:

| Entering | Requires |
|---|---|
| `REFERENCE_ANALYZED` | at least one linked `ReferenceCase` |
| `OPPORTUNITY_CREATED` | at least one linked `OpportunityDossier` |
| `PROTOTYPE_RECOMMENDED` | a linked dossier, and a named reviewer |

So a thread cannot arrive at "reference analyzed" without an analysis, and
cannot arrive at a prototype recommendation without the evidence package the
creative team is supposed to receive. The workflow produces that package; it
does not produce production work, and nothing in this module imports anything
that renders.

## Rejection is terminal, and so is recommendation

`REJECTED` has no outgoing transitions. Reopening a rejected thread is a new
source record citing the old one, not a status flipped back - the store is
append-oriented (`docs/company_os_v1_bootstrap.md`), and a thread that can
oscillate loses the one thing its history was for. `PROTOTYPE_RECOMMENDED` may
only go on to `REJECTED`, because a recommendation can be killed later and a
kill that cannot be recorded would be recorded nowhere.

## Every transition is signed

`StageTransition` requires the day, the person and the reason. The reason field
is the one that pays: six weeks later the interesting question about a rejected
thread is never which stage it reached.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any

from ai_platform.serde import as_date
from intelligence.research.common import assert_text, evidence_tuple
from intelligence.research.errors import ResearchError
from knowledge.company_os.records import Evidence


class ResearchStage(Enum):
    DISCOVERED = "discovered"
    SCREENED = "screened"
    REFERENCE_ANALYZED = "reference_analyzed"
    OPPORTUNITY_CREATED = "opportunity_created"
    REVIEWED = "reviewed"
    PROTOTYPE_RECOMMENDED = "prototype_recommended"
    REJECTED = "rejected"


ALLOWED_TRANSITIONS: dict[ResearchStage, frozenset[ResearchStage]] = {
    ResearchStage.DISCOVERED: frozenset({ResearchStage.SCREENED, ResearchStage.REJECTED}),
    ResearchStage.SCREENED: frozenset(
        {ResearchStage.REFERENCE_ANALYZED, ResearchStage.REJECTED}
    ),
    ResearchStage.REFERENCE_ANALYZED: frozenset(
        {ResearchStage.OPPORTUNITY_CREATED, ResearchStage.REJECTED}
    ),
    ResearchStage.OPPORTUNITY_CREATED: frozenset(
        {ResearchStage.REVIEWED, ResearchStage.REJECTED}
    ),
    ResearchStage.REVIEWED: frozenset(
        {ResearchStage.PROTOTYPE_RECOMMENDED, ResearchStage.REJECTED}
    ),
    ResearchStage.PROTOTYPE_RECOMMENDED: frozenset({ResearchStage.REJECTED}),
    ResearchStage.REJECTED: frozenset(),
}

TERMINAL_STAGES: frozenset[ResearchStage] = frozenset(
    stage for stage, onward in ALLOWED_TRANSITIONS.items() if not onward
)


@dataclass(frozen=True)
class StageTransition:
    """One signed step. Reasons are required; evidence is welcome."""

    from_stage: ResearchStage
    to_stage: ResearchStage
    on: dt.date
    by: str
    reason: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        assert_text(self.by, "transition by (who made the call)")
        assert_text(self.reason, "transition reason")
        if not isinstance(self.on, dt.date):
            raise ResearchError("a stage transition must record the date it happened")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if self.from_stage is self.to_stage:
            raise ResearchError(
                f"transition from {self.from_stage.value!r} to itself is not a transition"
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StageTransition:
        return cls(
            from_stage=ResearchStage(data["from_stage"]),
            to_stage=ResearchStage(data["to_stage"]),
            on=as_date(data["on"], "on"),
            by=data["by"],
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
        )


def can_transition(current: ResearchStage, target: ResearchStage) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def assert_transition(current: ResearchStage, target: ResearchStage) -> None:
    if can_transition(current, target):
        return
    allowed = sorted(s.value for s in ALLOWED_TRANSITIONS[current])
    if not allowed:
        raise ResearchError(
            f"{current.value!r} is terminal. Record a new source that cites this one "
            "rather than reopening a closed thread."
        )
    raise ResearchError(
        f"cannot go from {current.value!r} to {target.value!r}; "
        f"allowed from here: {', '.join(allowed)}"
    )


_GATES: dict[ResearchStage, tuple[str, str]] = {
    ResearchStage.REFERENCE_ANALYZED: (
        "reference_case_ids",
        "link the ReferenceCase before calling the reference analyzed",
    ),
    ResearchStage.OPPORTUNITY_CREATED: (
        "opportunity_ids",
        "link the OpportunityDossier this thread produced",
    ),
    ResearchStage.PROTOTYPE_RECOMMENDED: (
        "opportunity_ids",
        "a prototype is recommended on a dossier, not on a hunch",
    ),
}


def advance_source(
    source: Any,
    to_stage: ResearchStage,
    *,
    on: dt.date,
    by: str,
    reason: str,
    evidence: tuple[Evidence, ...] = (),
) -> Any:
    """Move a source to the next stage, appending a signed transition.

    Returns a new source; the history is appended to and never rewritten. The
    gate checks read the source's own link fields, so "we analyzed the
    reference" and "there is a reference case" cannot disagree.
    """
    assert_transition(source.stage, to_stage)
    gate = _GATES.get(to_stage)
    if gate is not None:
        field, why = gate
        if not getattr(source, field):
            raise ResearchError(
                f"source {source.id!r} cannot enter {to_stage.value!r} with an empty "
                f"{field}: {why}."
            )
    if to_stage is ResearchStage.PROTOTYPE_RECOMMENDED and not by.strip():
        raise ResearchError("a prototype recommendation must name the reviewer making it")
    step = StageTransition(
        from_stage=source.stage,
        to_stage=to_stage,
        on=on,
        by=by,
        reason=reason,
        evidence=evidence,
    )
    return replace(source, stage=to_stage, history=(*source.history, step))


def _link(source: Any, field: str, record_id: str) -> Any:
    existing = getattr(source, field)
    if record_id in existing:
        return source
    return replace(source, **{field: (*existing, record_id)})


def link_reference_case(source: Any, reference_case_id: str) -> Any:
    """Attach a reference case to the thread. Idempotent, order-preserving."""
    return _link(source, "reference_case_ids", reference_case_id)


def link_opportunity(source: Any, opportunity_id: str) -> Any:
    """Attach an opportunity dossier to the thread. Idempotent."""
    return _link(source, "opportunity_ids", opportunity_id)
