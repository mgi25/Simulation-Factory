"""Ordering recommendations, with the weights on the record.

## Why the weights are an argument and not a default

Any ordering of organizational changes encodes a preference: urgency over cost,
reversibility over impact. That preference belongs to the company, not to this
module, so `PriorityWeights` has no default - a caller who wants an order has to
say what they are optimising for, and the weights they supplied are stored on
the result. Somebody disagreeing with the order can see exactly which number to
argue with.

## A missing dimension stays missing

If nobody scored implementation cost, `total` is computed over the dimensions
that *were* supplied and `missing_dimensions` names the rest. The alternative -
substituting a neutral value - produces an order that looks complete and is
quietly wrong, and it is the failure mode that makes people distrust a ranking.
`is_complete` is the flag that keeps the two cases apart, and `rank` puts
complete priorities ahead of incomplete ones at equal totals rather than
pretending the comparison was fair.

## This is not a company score

It ranks one list of recommendations against one set of weights for one review.
It says nothing about a department, an employee or the company: those are
multi-objective and section 4 of the brief refuses to collapse them. A test
scans this package for a field that reads like an aggregate verdict.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .errors import OrgIntelligenceError

# The dimensions a priority may weigh. A closed vocabulary, so a typo produces
# an error rather than a dimension nobody weighted.
PRIORITY_DIMENSIONS: tuple[str, ...] = (
    "urgency",
    "expected_impact",
    "evidence_strength",
    "implementation_cost",
    "reversibility",
    "risk",
)


@dataclass(frozen=True)
class PriorityWeights:
    """What this company is optimising for, supplied rather than assumed."""

    weights: Any

    def __post_init__(self) -> None:
        raw = self.weights
        items = tuple(raw.items()) if isinstance(raw, Mapping) else tuple(raw or ())
        pairs: list[tuple[str, float]] = []
        for name, value in items:
            if name not in PRIORITY_DIMENSIONS:
                raise OrgIntelligenceError(
                    f"{name!r} is not a priority dimension. Known: "
                    + ", ".join(PRIORITY_DIMENSIONS)
                )
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise OrgIntelligenceError(f"weight for {name} must be a number")
            pairs.append((name, float(value)))
        if not pairs:
            raise OrgIntelligenceError(
                "supply at least one weight. An ordering with no stated preference is an "
                "opaque priority, which section 17 of the brief forbids"
            )
        if len({name for name, _ in pairs}) != len(pairs):
            raise OrgIntelligenceError("a dimension may be weighted once")
        object.__setattr__(self, "weights", tuple(sorted(pairs)))

    def get(self, dimension: str) -> float | None:
        for name, value in self.weights:
            if name == dimension:
                return value
        return None

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self.weights)

    def to_dict(self) -> dict[str, float]:
        return {name: value for name, value in self.weights}


@dataclass(frozen=True)
class DimensionValue:
    """One scored dimension, or the honest absence of one."""

    name: str
    value: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.name not in PRIORITY_DIMENSIONS:
            raise OrgIntelligenceError(
                f"{self.name!r} is not a priority dimension. Known: "
                + ", ".join(PRIORITY_DIMENSIONS)
            )
        if self.value is not None:
            if isinstance(self.value, bool) or not isinstance(self.value, (int, float)):
                raise OrgIntelligenceError(f"{self.name}: value must be a number or None")
            object.__setattr__(self, "value", float(self.value))
        if not isinstance(self.note, str):
            raise OrgIntelligenceError("dimension note must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "value": self.value, "note": self.note}


@dataclass(frozen=True)
class RecommendationPriority:
    """One recommendation's place in one ordering, with the arithmetic shown."""

    recommendation_id: str
    weights: PriorityWeights
    dimensions: tuple[DimensionValue, ...]
    total: float | None
    missing_dimensions: tuple[str, ...]

    @property
    def is_complete(self) -> bool:
        return not self.missing_dimensions

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "weights": self.weights.to_dict(),
            "dimensions": [item.to_dict() for item in self.dimensions],
            "total": self.total,
            "missing_dimensions": list(self.missing_dimensions),
            "is_complete": self.is_complete,
        }


def prioritise(
    recommendation_id: str,
    dimensions: Iterable[DimensionValue],
    weights: PriorityWeights,
) -> RecommendationPriority:
    """Weighted sum over supplied dimensions. Missing ones stay missing.

    Only weighted dimensions contribute; a dimension scored but not weighted is
    kept on the record and left out of the total, so the record shows what was
    measured and the total shows what was asked for.
    """
    if not isinstance(weights, PriorityWeights):
        raise OrgIntelligenceError("prioritise needs explicit PriorityWeights")
    supplied = tuple(dimensions)
    if len({item.name for item in supplied}) != len(supplied):
        raise OrgIntelligenceError(f"{recommendation_id}: a dimension may be scored once")
    scored = {item.name: item.value for item in supplied if item.value is not None}
    missing = tuple(name for name in weights.names if name not in scored)
    contributions = [
        value * scored[name] for name, value in weights.weights if name in scored
    ]
    return RecommendationPriority(
        recommendation_id=recommendation_id,
        weights=weights,
        dimensions=tuple(sorted(supplied, key=lambda item: item.name)),
        total=sum(contributions) if contributions else None,
        missing_dimensions=missing,
    )


def rank(priorities: Iterable[RecommendationPriority]) -> tuple[RecommendationPriority, ...]:
    """Highest total first, complete ones ahead of incomplete at equal totals.

    The id is the final tiebreak, so the same inputs always produce the same
    order - which is what makes a ranking reviewable rather than merely
    plausible.
    """
    return tuple(
        sorted(
            priorities,
            key=lambda item: (
                -(item.total if item.total is not None else float("-inf")),
                not item.is_complete,
                item.recommendation_id,
            ),
        )
    )
