"""Execution strategy selection: the preference order for resolving a task.

The constitution (rule 4) and the work order constraints both state the same
preference:

    1. Deterministic computation (code, schema check, lookup table)
    2. Cached or retrieved knowledge (capsule hit, knowledge store)
    3. Lightweight reasoning (fast model, small context)
    4. Stronger reasoning only when justified (capable or strong model)

This module makes that preference executable.  Given a task's classification
and the available execution evidence, it selects the cheapest strategy that
is expected to succeed, and records the rule and evidence for that selection.

The headline metric is **resource cost per accepted engineering result**.
Each strategy carries an expected cost and first-pass rate; the
cost-per-accepted-result is cost / first_pass_rate.  A strategy that costs
less per call but fails more often may have a higher cost per accepted result.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.resource_classes import ReasoningClass, Classification
from ai_platform.serde import to_jsonable

from .routing import ModelRoutingPolicy, ModelRoutingRule, ModelTier, default_routing_policy


class StrategyKind(str, Enum):
    """The four strategy tiers in preference order."""

    DETERMINISTIC = "deterministic"
    CACHED_RETRIEVAL = "cached_retrieval"
    LIGHTWEIGHT_REASONING = "lightweight_reasoning"
    FULL_REASONING = "full_reasoning"


@dataclass(frozen=True)
class ExecutionStrategy:
    """One selected strategy for one task, with its evidence."""

    strategy: StrategyKind
    routing_rule: ModelRoutingRule
    selection_rule: str
    evidence: str
    expected_cost_per_accepted_result: float
    cache_eligible: bool
    context_refs_budget: int

    def __post_init__(self) -> None:
        if not isinstance(self.strategy, StrategyKind):
            raise ValueError("strategy must be a StrategyKind")
        if not isinstance(self.routing_rule, ModelRoutingRule):
            raise ValueError("routing_rule must be a ModelRoutingRule")
        if not self.selection_rule.strip():
            raise ValueError("selection_rule is required")
        if not self.evidence.strip():
            raise ValueError("evidence is required")
        if self.expected_cost_per_accepted_result < 0:
            raise ValueError("expected_cost_per_accepted_result must be non-negative")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def select_strategy(
    classification: Classification,
    *,
    routing_policy: ModelRoutingPolicy | None = None,
    has_cache_hit: bool = False,
    prior_attempts: int = 0,
) -> ExecutionStrategy:
    """Select the cheapest sufficient strategy for a classified task.

    The selection follows the constitution's preference order but adjusts
    for retry context: a task on its second attempt that failed with a
    lightweight model may be escalated to full reasoning.
    """
    policy = routing_policy or default_routing_policy()
    rule = policy.route(classification.code)

    if rule.tier in (ModelTier.DETERMINISTIC, ModelTier.RETRIEVAL):
        strategy = StrategyKind.DETERMINISTIC
        selection_rule = "class_a_b_deterministic_or_retrieval"
        evidence = (
            f"classification {classification.code.value} ({classification.rule}) "
            "requires no model reasoning"
        )
    elif has_cache_hit and prior_attempts == 0:
        strategy = StrategyKind.CACHED_RETRIEVAL
        selection_rule = "cache_hit_available"
        evidence = (
            f"cache hit for classification {classification.code.value}; "
            "context assembly can reuse cached result"
        )
    elif rule.tier is ModelTier.FAST and prior_attempts == 0:
        strategy = StrategyKind.LIGHTWEIGHT_REASONING
        selection_rule = "first_attempt_lightweight"
        evidence = (
            f"classification {classification.code.value} ({classification.rule}) "
            f"with tier {rule.tier.value}; first attempt uses lightweight reasoning"
        )
    elif rule.tier is ModelTier.FAST and prior_attempts > 0:
        # Escalate: a fast model that failed should try a capable model
        escalated = policy.route(ReasoningClass.D)
        strategy = StrategyKind.FULL_REASONING
        selection_rule = "retry_escalation_fast_to_capable"
        evidence = (
            f"classification {classification.code.value} failed {prior_attempts} "
            f"attempt(s) with tier {rule.tier.value}; escalating to "
            f"{escalated.tier.value} for retry"
        )
        rule = escalated
    else:
        strategy = StrategyKind.FULL_REASONING
        selection_rule = "classification_requires_full_reasoning"
        evidence = (
            f"classification {classification.code.value} ({classification.rule}) "
            f"requires tier {rule.tier.value}"
        )

    return ExecutionStrategy(
        strategy=strategy,
        routing_rule=rule,
        selection_rule=selection_rule,
        evidence=evidence,
        expected_cost_per_accepted_result=round(
            rule.expected_cost_per_accepted_result(), 3
        ),
        cache_eligible=has_cache_hit,
        context_refs_budget=rule.max_context_refs,
    )


@dataclass(frozen=True)
class CostPerAcceptedResult:
    """The headline metric: what one accepted engineering result actually cost.

    This is computed after execution, not predicted.  It includes the cost of
    all attempts (including failures) that led to the accepted result.
    """

    task_id: str
    total_attempts: int
    accepted_attempt: int
    total_input_tokens: int | None
    total_output_tokens: int | None
    total_cost_amount: str | None
    total_cost_currency: str
    model_tiers_used: tuple[str, ...]
    strategy_used: StrategyKind
    first_pass_success: bool

    def __post_init__(self) -> None:
        if not self.task_id.strip():
            raise ValueError("task_id is required")
        if self.total_attempts < 1:
            raise ValueError("total_attempts must be at least 1")
        if self.accepted_attempt < 1 or self.accepted_attempt > self.total_attempts:
            raise ValueError("accepted_attempt must be between 1 and total_attempts")

    @property
    def retry_overhead_pct(self) -> float:
        """What fraction of the total cost was retries (not the accepted attempt)."""
        if self.total_attempts <= 1:
            return 0.0
        return ((self.total_attempts - 1) / self.total_attempts) * 100.0

    def to_dict(self) -> dict[str, Any]:
        result = to_jsonable(self)
        result["retry_overhead_pct"] = round(self.retry_overhead_pct, 1)
        return result


def compute_cost_per_result(
    *,
    task_id: str,
    total_attempts: int,
    accepted_attempt: int,
    total_input_tokens: int | None = None,
    total_output_tokens: int | None = None,
    total_cost_amount: str | None = None,
    total_cost_currency: str = "",
    model_tiers_used: tuple[str, ...] = (),
    strategy_used: StrategyKind = StrategyKind.FULL_REASONING,
) -> CostPerAcceptedResult:
    """Build the headline metric from execution evidence."""
    return CostPerAcceptedResult(
        task_id=task_id,
        total_attempts=total_attempts,
        accepted_attempt=accepted_attempt,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_cost_amount=total_cost_amount,
        total_cost_currency=total_cost_currency,
        model_tiers_used=model_tiers_used,
        strategy_used=strategy_used,
        first_pass_success=accepted_attempt == 1,
    )


__all__ = [
    "CostPerAcceptedResult",
    "ExecutionStrategy",
    "StrategyKind",
    "compute_cost_per_result",
    "select_strategy",
]
