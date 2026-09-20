"""Arithmetic over judgement. The software adds up; it does not decide.

The division of labour is the whole design. A researcher supplies a score and a
reason for each dimension; this module multiplies by weights nobody hid and
sorts the results the same way twice. There is no model in here, no heuristic,
and - deliberately - no reading of `PublicMetrics`. `score_opportunity` takes a
rubric and a scorecard and nothing else, so "higher views is a better
opportunity" is not a rule someone forgot to write: it is a rule that has no
input to be written from.

## Four things the result refuses to let you forget

`ScoreResult` carries the number *and* everything that qualifies it, in the
same object, into the same JSON file:

    missing_dimensions   rubric dimensions the scorecard never scored
    weight_covered       the fraction of rubric weight that was actually scored
    is_comparable        False whenever coverage is below 1.0
    caveat               a sentence, never empty, saying what the total is not

A composite mistaken for truth is the standard failure of every scoring system,
and it happens when the number travels and the qualifications do not. Here they
cannot separate: the caveat is a required field of the same frozen dataclass,
and it is written into the record.

There is no `confidence` field on a `ScoreResult`, on purpose. Confidence is a
property of the evidence behind a dossier (`ResearchConfidence`), and a
weighted mean of nine opinions is not evidence about anything. A scorecard
where every reason is "felt right" produces the same 4.2 as one where every
reason cites a measurement.

## Lower-is-better dimensions

`estimated_cost` is the obvious one: scoring it 5 means expensive, and a naive
weighted sum would reward that. A dimension declares `higher_is_better=False`
and the contribution is inverted against the scale once, in one place.

## Ties

`rank()` sorts by `(-weighted_total, opportunity_id)`. Two opportunities that
score identically come back in id order on every machine and in every process,
which is what makes a printed ranking reviewable. Ranking across two different
rubrics is refused rather than silently allowed - the numbers are not on the
same scale and the comparison would be meaningless.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any, ClassVar, Iterable, Sequence

from ai_platform.serde import as_date
from intelligence.research.common import (
    Evidence,
    assert_nonempty,
    assert_research_id,
    assert_slug,
    assert_text,
    evidence_tuple,
)
from intelligence.research.errors import ResearchError

KNOWN_DIMENSIONS: tuple[str, ...] = (
    "viewer_loop_strength",
    "channel_fit",
    "originality_space",
    "repeatability",
    "production_feasibility",
    "reusable_asset_value",
    "evidence_strength",
    "differentiation",
    "estimated_cost",
)
"""The nine the brief names. A rubric may use any subset, or others."""

CAVEAT = (
    "A weighted total of researcher judgement. It is not evidence, not "
    "confidence, and not a decision; read the per-dimension reasons before "
    "using it to order anything."
)


@dataclass(frozen=True)
class ScoringDimension:
    """One axis, its weight, its scale, and which end is good."""

    name: str
    weight: float
    scale_max: int = 5
    higher_is_better: bool = True
    description: str = ""

    def __post_init__(self) -> None:
        assert_slug(self.name, "dimension name")
        if isinstance(self.weight, bool) or not isinstance(self.weight, (int, float)):
            raise ResearchError(f"dimension {self.name!r}: weight must be a number")
        if self.weight <= 0:
            raise ResearchError(
                f"dimension {self.name!r}: weight {self.weight} must be positive. A "
                "dimension worth zero should be removed from the rubric, visibly."
            )
        object.__setattr__(self, "weight", float(self.weight))
        if isinstance(self.scale_max, bool) or not isinstance(self.scale_max, int):
            raise ResearchError(f"dimension {self.name!r}: scale_max must be a whole number")
        if self.scale_max < 2:
            raise ResearchError(
                f"dimension {self.name!r}: scale_max {self.scale_max} leaves nothing to score"
            )

    def contribution(self, score: int) -> float:
        """The score mapped onto 0..scale_max with the direction applied."""
        return float(self.scale_max - score) if not self.higher_is_better else float(score)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoringDimension:
        return cls(
            name=data["name"],
            weight=data["weight"],
            scale_max=data.get("scale_max", 5),
            higher_is_better=bool(data.get("higher_is_better", True)),
            description=data.get("description", ""),
        )


@dataclass(frozen=True)
class ScoringRubric:
    """A named, versioned set of dimensions and weights. Config, not opinion."""

    kind: ClassVar[str] = "rubric"

    id: str
    version: str
    purpose: str
    dimensions: tuple[ScoringDimension, ...]
    created: dt.date
    author: str
    notes: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "rubric")
        assert_text(self.version, "rubric version")
        assert_text(self.purpose, "rubric purpose")
        assert_text(self.author, "rubric author")
        if not isinstance(self.created, dt.date):
            raise ResearchError("a rubric must record the date it was written")
        assert_nonempty(self.dimensions, "dimensions", "a rubric with no dimensions scores nothing")
        names = [d.name for d in self.dimensions]
        if len(set(names)) != len(names):
            raise ResearchError(f"rubric {self.id!r}: duplicate dimension name")

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.dimensions)

    @property
    def total_weight(self) -> float:
        return sum(d.weight for d in self.dimensions)

    def dimension(self, name: str) -> ScoringDimension:
        for d in self.dimensions:
            if d.name == name:
                return d
        raise ResearchError(
            f"rubric {self.id!r} has no dimension {name!r}; it scores {', '.join(self.names)}"
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoringRubric:
        return cls(
            id=data["id"],
            version=data["version"],
            purpose=data["purpose"],
            dimensions=tuple(ScoringDimension.from_dict(d) for d in data["dimensions"]),
            created=as_date(data["created"], "created"),
            author=data["author"],
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class DimensionScore:
    """A number and the reason for it. The reason is not optional."""

    dimension: str
    score: int
    reason: str
    evidence: tuple[Evidence, ...] = ()

    def __post_init__(self) -> None:
        assert_slug(self.dimension, "score dimension")
        assert_text(self.reason, "score reason (why this number, in one sentence)")
        if isinstance(self.score, bool) or not isinstance(self.score, int):
            raise ResearchError(
                f"{self.dimension}: score must be a whole number on the rubric's scale, "
                f"got {self.score!r}"
            )
        if self.score < 0:
            raise ResearchError(f"{self.dimension}: score {self.score} is below zero")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DimensionScore:
        return cls(
            dimension=data["dimension"],
            score=data["score"],
            reason=data["reason"],
            evidence=evidence_tuple(data.get("evidence")),
        )


@dataclass(frozen=True)
class OpportunityScorecard:
    """One researcher's scores for one opportunity against one rubric."""

    kind: ClassVar[str] = "scorecard"

    id: str
    opportunity_id: str
    rubric_id: str
    scored_by: str
    scored_on: dt.date
    scores: tuple[DimensionScore, ...]
    note: str = ""

    def __post_init__(self) -> None:
        assert_research_id(self.id, "scorecard")
        assert_research_id(self.opportunity_id, "opportunity")
        assert_research_id(self.rubric_id, "rubric")
        assert_text(self.scored_by, "scored_by")
        if not isinstance(self.scored_on, dt.date):
            raise ResearchError("a scorecard must record the date it was scored")
        assert_nonempty(self.scores, "scores", "a scorecard with no scores is a blank form")
        names = [s.dimension for s in self.scores]
        if len(set(names)) != len(names):
            raise ResearchError(
                f"scorecard {self.id!r}: dimension scored twice. One of the two would "
                "silently win."
            )

    def by_dimension(self) -> dict[str, DimensionScore]:
        return {s.dimension: s for s in self.scores}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OpportunityScorecard:
        return cls(
            id=data["id"],
            opportunity_id=data["opportunity_id"],
            rubric_id=data["rubric_id"],
            scored_by=data["scored_by"],
            scored_on=as_date(data["scored_on"], "scored_on"),
            scores=tuple(DimensionScore.from_dict(s) for s in data["scores"]),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class ScoreResult:
    """The total, and everything that stops it from being read as a verdict."""

    opportunity_id: str
    rubric_id: str
    weighted_total: float
    weight_covered: float
    missing_dimensions: tuple[str, ...]
    contributions: tuple[tuple[str, float], ...]
    caveat: str = CAVEAT

    def __post_init__(self) -> None:
        assert_text(self.caveat, "score caveat")

    @property
    def is_comparable(self) -> bool:
        """Two totals may only be compared when both scored the whole rubric."""
        return self.weight_covered >= 1.0

    @property
    def has_gaps(self) -> bool:
        return bool(self.missing_dimensions)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScoreResult:
        return cls(
            opportunity_id=data["opportunity_id"],
            rubric_id=data["rubric_id"],
            weighted_total=data["weighted_total"],
            weight_covered=data["weight_covered"],
            missing_dimensions=tuple(data.get("missing_dimensions", ())),
            contributions=tuple((c[0], c[1]) for c in data.get("contributions", ())),
            caveat=data.get("caveat", CAVEAT),
        )


def _round(value: float) -> float:
    return round(value, 6)


def score_opportunity(rubric: ScoringRubric, card: OpportunityScorecard) -> ScoreResult:
    """Multiply, add, divide by the weight that was actually scored.

    The total is a weighted mean over the *scored* dimensions, normalised to
    the rubric's scale, so a partial scorecard is not penalised into looking
    bad - it is reported as incomplete instead. Iteration follows the rubric's
    declared order, so the arithmetic is bit-identical across runs.
    """
    if card.rubric_id != rubric.id:
        raise ResearchError(
            f"scorecard {card.id!r} was scored against rubric {card.rubric_id!r}, "
            f"not {rubric.id!r}"
        )
    scores = card.by_dimension()
    unknown = sorted(set(scores) - set(rubric.names))
    if unknown:
        raise ResearchError(
            f"scorecard {card.id!r} scores {', '.join(unknown)}, which rubric "
            f"{rubric.id!r} does not define. Add the dimension to the rubric, or fix "
            "the scorecard - a score against nothing cannot be weighted."
        )

    contributions: list[tuple[str, float]] = []
    missing: list[str] = []
    weighted_sum = 0.0
    weight_used = 0.0

    for dimension in rubric.dimensions:
        entry = scores.get(dimension.name)
        if entry is None:
            missing.append(dimension.name)
            continue
        if entry.score > dimension.scale_max:
            raise ResearchError(
                f"{dimension.name}: score {entry.score} exceeds the rubric's scale_max "
                f"of {dimension.scale_max}"
            )
        contribution = dimension.contribution(entry.score)
        contributions.append((dimension.name, _round(contribution * dimension.weight)))
        weighted_sum += contribution * dimension.weight
        weight_used += dimension.weight

    total = _round(weighted_sum / weight_used) if weight_used else 0.0
    covered = _round(weight_used / rubric.total_weight) if rubric.total_weight else 0.0
    return ScoreResult(
        opportunity_id=card.opportunity_id,
        rubric_id=rubric.id,
        weighted_total=total,
        weight_covered=covered,
        missing_dimensions=tuple(missing),
        contributions=tuple(contributions),
    )


def rank(results: Iterable[ScoreResult]) -> tuple[ScoreResult, ...]:
    """Order by total, break ties by id, and refuse to mix rubrics."""
    items = tuple(results)
    rubrics = {r.rubric_id for r in items}
    if len(rubrics) > 1:
        raise ResearchError(
            f"cannot rank across rubrics {sorted(rubrics)}: the totals are on different "
            "scales and the ordering would mean nothing"
        )
    return tuple(sorted(items, key=lambda r: (-r.weighted_total, r.opportunity_id)))


def score_all(
    rubric: ScoringRubric, cards: Sequence[OpportunityScorecard]
) -> tuple[ScoreResult, ...]:
    """Score a batch and rank it. A convenience over the two functions above."""
    return rank(score_opportunity(rubric, card) for card in cards)
