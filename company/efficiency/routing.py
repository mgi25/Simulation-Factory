"""Model routing policy: maps reasoning classes to model-tier recommendations.

This module produces a deterministic model routing recommendation from
the existing resource class system.  It never names a vendor model; it
names a **model tier** (deterministic, fast, capable, strong, multi_reviewer)
and the rule that selected it.

The mapping is:
    A  deterministic   → no model call; code resolves the task
    B  retrieval       → no model call; knowledge lookup resolves the task
    C  small_reasoning → fast tier (Haiku-class: cheap, low-latency)
    D  specialist      → capable tier (Sonnet-class: good reasoning, moderate cost)
    E  deep_reasoning  → strong tier (Opus-class: deep reasoning, high cost)
    F  multi_review    → strong tier, sequentially invoked N times

The primary metric is **resource cost per accepted engineering result**,
not tokens per individual call.  A cheaper model that fails and requires
a retry may cost more per accepted result than a stronger model that
succeeds on the first pass.  The routing policy records its expected
first-pass success rate for each tier so the cost-per-result can be
estimated before execution and measured after it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import ReasoningClass, RESOURCE_CLASSES, ResourceClass
from ai_platform.serde import to_jsonable


class ModelTier(str, Enum):
    """What kind of model a task needs — not which specific model."""

    DETERMINISTIC = "deterministic"
    RETRIEVAL = "retrieval"
    FAST = "fast"
    CAPABLE = "capable"
    STRONG = "strong"
    MULTI_REVIEWER = "multi_reviewer"


# Expected first-pass success rates by tier, based on structural analysis
# of Company OS engineering workloads.  These are starting estimates;
# real measurements replace them as executions accumulate.
_EXPECTED_FIRST_PASS_RATES: dict[ModelTier, float] = {
    ModelTier.DETERMINISTIC: 1.0,
    ModelTier.RETRIEVAL: 0.95,
    ModelTier.FAST: 0.70,
    ModelTier.CAPABLE: 0.85,
    ModelTier.STRONG: 0.92,
    ModelTier.MULTI_REVIEWER: 0.95,
}

# Relative cost per token (normalized to fast=1.0)
_RELATIVE_COST: dict[ModelTier, float] = {
    ModelTier.DETERMINISTIC: 0.0,
    ModelTier.RETRIEVAL: 0.0,
    ModelTier.FAST: 1.0,
    ModelTier.CAPABLE: 3.0,
    ModelTier.STRONG: 15.0,
    ModelTier.MULTI_REVIEWER: 15.0,
}


@dataclass(frozen=True)
class ModelRoutingRule:
    """One entry in the routing table: which tier a reasoning class maps to."""

    reasoning_class: ReasoningClass
    tier: ModelTier
    rule_name: str
    reason: str
    expected_first_pass_rate: float
    relative_cost_per_token: float
    max_context_refs: int

    def __post_init__(self) -> None:
        if not isinstance(self.reasoning_class, ReasoningClass):
            raise ValueError("reasoning_class must be a ReasoningClass")
        if not isinstance(self.tier, ModelTier):
            raise ValueError("tier must be a ModelTier")
        if not self.rule_name.strip():
            raise ValueError("rule_name is required")
        if not 0.0 <= self.expected_first_pass_rate <= 1.0:
            raise ValueError("expected_first_pass_rate must be between 0 and 1")
        if self.relative_cost_per_token < 0:
            raise ValueError("relative_cost_per_token must be non-negative")

    def expected_cost_per_accepted_result(self) -> float:
        """Expected cost per accepted result, accounting for retries.

        If first_pass_rate is 0.85 and cost_per_attempt is 3.0,
        expected attempts = 1/0.85 ≈ 1.18, so cost_per_result ≈ 3.53.
        """
        if self.expected_first_pass_rate <= 0:
            return float("inf")
        return self.relative_cost_per_token / self.expected_first_pass_rate

    def to_dict(self) -> dict[str, Any]:
        result = to_jsonable(self)
        result["expected_cost_per_accepted_result"] = round(
            self.expected_cost_per_accepted_result(), 3
        )
        return result


@dataclass(frozen=True)
class ModelRoutingPolicy:
    """The complete routing table, plus summary metrics."""

    rules: tuple[ModelRoutingRule, ...]
    version: int = 1

    def __post_init__(self) -> None:
        classes = [rule.reasoning_class for rule in self.rules]
        if len(set(classes)) != len(classes):
            raise ValueError("each reasoning class may appear at most once")

    def route(self, reasoning_class: ReasoningClass) -> ModelRoutingRule:
        for rule in self.rules:
            if rule.reasoning_class is reasoning_class:
                return rule
        raise ValueError(
            f"no routing rule for reasoning class {reasoning_class.value}"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "rules": [rule.to_dict() for rule in self.rules],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        """Key metrics across the routing table."""
        deterministic_classes = sum(
            1 for rule in self.rules
            if rule.tier in (ModelTier.DETERMINISTIC, ModelTier.RETRIEVAL)
        )
        model_classes = len(self.rules) - deterministic_classes
        avg_cost_per_result = (
            sum(rule.expected_cost_per_accepted_result() for rule in self.rules)
            / len(self.rules)
        ) if self.rules else 0.0
        return {
            "total_classes": len(self.rules),
            "deterministic_classes": deterministic_classes,
            "model_classes": model_classes,
            "average_expected_cost_per_accepted_result": round(avg_cost_per_result, 3),
        }


def _build_rule(code: ReasoningClass, tier: ModelTier, rule_name: str) -> ModelRoutingRule:
    rc = RESOURCE_CLASSES[code]
    return ModelRoutingRule(
        reasoning_class=code,
        tier=tier,
        rule_name=rule_name,
        reason=rc.intent,
        expected_first_pass_rate=_EXPECTED_FIRST_PASS_RATES[tier],
        relative_cost_per_token=_RELATIVE_COST[tier],
        max_context_refs=rc.max_context_refs,
    )


def default_routing_policy() -> ModelRoutingPolicy:
    """The V2 routing policy: deterministic first, then by reasoning depth."""
    return ModelRoutingPolicy(rules=(
        _build_rule(ReasoningClass.A, ModelTier.DETERMINISTIC, "class_a_deterministic"),
        _build_rule(ReasoningClass.B, ModelTier.RETRIEVAL, "class_b_retrieval"),
        _build_rule(ReasoningClass.C, ModelTier.FAST, "class_c_fast_model"),
        _build_rule(ReasoningClass.D, ModelTier.CAPABLE, "class_d_capable_model"),
        _build_rule(ReasoningClass.E, ModelTier.STRONG, "class_e_strong_model"),
        _build_rule(ReasoningClass.F, ModelTier.MULTI_REVIEWER, "class_f_multi_reviewer"),
    ))


__all__ = [
    "ModelRoutingPolicy",
    "ModelRoutingRule",
    "ModelTier",
    "default_routing_policy",
]
