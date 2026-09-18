"""Deterministic execution strategy selection by task complexity and risk.

Every engineering job the company issues now carries an execution strategy in
its briefing.  The strategy determines the model tier the operator should apply,
the context budget the session should respect, the checkpoint rule that governs
fresh-context decisions, and the output-reduction directives that bound what
tool and test output enters the model's visible context.

The selection is deterministic: the same reasoning class, risk, and work order
properties always produce the same strategy.  The operator applies it using the
runner's existing ``--model`` and ``--max-turns`` flags; the company emits it
rather than enforcing it, because the runner is outside the capsule's writable
surface.

## Model tier

A *standard* tier is sufficient for routine C-class implementation jobs where
the task is bounded, low-to-medium risk, and the acceptance criteria are
concrete.  A *strongest* tier is required for D-class specialist reasoning,
high-risk or novel tasks, and any job whose evidence or review requirements
demand deep analysis.  There is no tier below standard: the quality constraint
is hard.

## Context budget

The budget is a character ceiling on total model-visible context per turn.  It
is derived from the reasoning class's ``max_context_refs`` and the empirical
ratio between reference count and resolved context size.  A session that
approaches the ceiling must checkpoint or start fresh rather than growing
unboundedly.

## Checkpoint rule

A session checkpoints (saves progress and starts a fresh context) when:

- accumulated context exceeds ``checkpoint_threshold_chars``, AND
- the task is not in a critical section (mid-test-run, mid-commit), AND
- at least one acceptance criterion has verifiable progress.

Starting fresh is cheaper and safe when the session has committed intermediate
work and the remaining criteria are independent of the completed ones.

## Output reduction

Tool output (test results, git status, file listings) is reduced before
entering model context by these deterministic rules:

- Test output: only failure lines and a pass/fail summary; passing test detail
  is omitted.
- Git output: only changed file paths and conflict markers; clean status is
  one line.
- File listings: only names matching the path scope; unrelated paths are
  omitted.
- Log output: only the last N lines where N is ``max_log_lines``, plus any
  line containing "error", "fail", or "warning".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ai_platform.resource_classes import ReasoningClass, Risk


class ModelTier(str, Enum):
    """Which model strength the operator should apply."""

    STANDARD = "standard"
    STRONGEST = "strongest"


class CheckpointRule(str, Enum):
    """When a session should start a fresh context."""

    CONTINUE = "continue_if_under_budget"
    CHECKPOINT_ON_THRESHOLD = "checkpoint_when_context_exceeds_threshold"
    FRESH_PER_CRITERION = "fresh_context_per_independent_criterion"


@dataclass(frozen=True)
class OutputReductionDirective:
    """Deterministic rules for reducing model-visible output."""

    omit_passing_test_detail: bool
    max_test_failure_lines: int
    max_log_lines: int
    omit_clean_git_detail: bool
    scope_file_listings: bool

    @classmethod
    def standard(cls) -> "OutputReductionDirective":
        return cls(
            omit_passing_test_detail=True,
            max_test_failure_lines=50,
            max_log_lines=100,
            omit_clean_git_detail=True,
            scope_file_listings=True,
        )

    @classmethod
    def full(cls) -> "OutputReductionDirective":
        return cls(
            omit_passing_test_detail=False,
            max_test_failure_lines=200,
            max_log_lines=500,
            omit_clean_git_detail=False,
            scope_file_listings=False,
        )


@dataclass(frozen=True)
class ResourceCeiling:
    """Per-job ceilings; the session stops or escalates before exceeding them."""

    max_turns: int
    max_tool_calls: int
    max_input_tokens_estimate: int
    escalation_message: str

    @classmethod
    def for_tier(cls, tier: ModelTier, reasoning_class: ReasoningClass) -> "ResourceCeiling":
        if tier is ModelTier.STRONGEST:
            return cls(
                max_turns=80,
                max_tool_calls=200,
                max_input_tokens_estimate=800_000,
                escalation_message=(
                    "This job has a strongest-tier resource ceiling. "
                    "Stop and report progress if approaching limits."
                ),
            )
        # Standard tier gets tighter ceilings to prevent runaway.
        if reasoning_class in (ReasoningClass.A, ReasoningClass.B):
            return cls(
                max_turns=20,
                max_tool_calls=60,
                max_input_tokens_estimate=200_000,
                escalation_message=(
                    "This is a lightweight job with tight resource limits. "
                    "Stop and escalate if the task is harder than expected."
                ),
            )
        return cls(
            max_turns=50,
            max_tool_calls=150,
            max_input_tokens_estimate=500_000,
            escalation_message=(
                "This job has a standard-tier resource ceiling. "
                "Stop and report progress if approaching limits."
            ),
        )


@dataclass(frozen=True)
class ExecutionStrategy:
    """The complete execution strategy for one job, emitted in the briefing."""

    model_tier: ModelTier
    context_budget_chars: int
    checkpoint_threshold_chars: int
    checkpoint_rule: CheckpointRule
    output_reduction: OutputReductionDirective
    resource_ceiling: ResourceCeiling
    provider_count: int  # always 1: one provider at a time
    strategy_reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "model_tier": self.model_tier.value,
            "context_budget_chars": self.context_budget_chars,
            "checkpoint_threshold_chars": self.checkpoint_threshold_chars,
            "checkpoint_rule": self.checkpoint_rule.value,
            "output_reduction": {
                "omit_passing_test_detail": self.output_reduction.omit_passing_test_detail,
                "max_test_failure_lines": self.output_reduction.max_test_failure_lines,
                "max_log_lines": self.output_reduction.max_log_lines,
                "omit_clean_git_detail": self.output_reduction.omit_clean_git_detail,
                "scope_file_listings": self.output_reduction.scope_file_listings,
            },
            "resource_ceiling": {
                "max_turns": self.resource_ceiling.max_turns,
                "max_tool_calls": self.resource_ceiling.max_tool_calls,
                "max_input_tokens_estimate": self.resource_ceiling.max_input_tokens_estimate,
                "escalation_message": self.resource_ceiling.escalation_message,
            },
            "provider_count": self.provider_count,
            "strategy_reason": self.strategy_reason,
        }


# --- strategy selection ---------------------------------------------------

# Empirical: each context ref resolves to roughly 4000 chars of capsule text
# on average, based on the DEFAULT_BUDGET.max_capsule_chars of 4000.
_CHARS_PER_REF = 4_000

# Context budget multiplier: the budget is max_context_refs * chars_per_ref,
# plus headroom for the packet itself and tool output.
_PACKET_HEADROOM = 10_000


def select_strategy(
    reasoning_class: ReasoningClass,
    risk: Risk,
    *,
    evidence_required: bool = False,
    max_context_refs: int = 6,
    is_review: bool = False,
) -> ExecutionStrategy:
    """Select execution strategy deterministically from task properties.

    The selection rule:
    - Strongest model for D+ reasoning, HIGH+ risk, or evidence-required tasks
    - Standard model for C-class routine implementation at LOW/MEDIUM risk
    - Reviews always use one tier lower resource ceiling than implementation
    """
    needs_strongest = (
        reasoning_class in (ReasoningClass.D, ReasoningClass.E, ReasoningClass.F)
        or risk in (Risk.HIGH, Risk.CRITICAL)
        or evidence_required
    )
    tier = ModelTier.STRONGEST if needs_strongest else ModelTier.STANDARD

    context_budget = max_context_refs * _CHARS_PER_REF + _PACKET_HEADROOM
    # Checkpoint at 70% of budget
    checkpoint_threshold = int(context_budget * 0.7)

    if is_review:
        # Reviews read but don't write; tighter budget, always checkpoint
        context_budget = int(context_budget * 0.6)
        checkpoint_threshold = int(context_budget * 0.7)
        checkpoint_rule = CheckpointRule.CONTINUE
    elif needs_strongest:
        checkpoint_rule = CheckpointRule.CHECKPOINT_ON_THRESHOLD
    else:
        checkpoint_rule = CheckpointRule.CHECKPOINT_ON_THRESHOLD

    output_reduction = (
        OutputReductionDirective.full()
        if reasoning_class in (ReasoningClass.E, ReasoningClass.F)
        else OutputReductionDirective.standard()
    )
    ceiling = ResourceCeiling.for_tier(tier, reasoning_class)

    reasons = []
    if needs_strongest:
        if reasoning_class in (ReasoningClass.D, ReasoningClass.E, ReasoningClass.F):
            reasons.append(f"reasoning class {reasoning_class.value} requires specialist depth")
        if risk in (Risk.HIGH, Risk.CRITICAL):
            reasons.append(f"risk {risk.value} requires careful analysis")
        if evidence_required:
            reasons.append("evidence-required task needs thorough verification")
    else:
        reasons.append(
            f"reasoning class {reasoning_class.value} at risk {risk.value} "
            "is routine implementation"
        )
    if is_review:
        reasons.append("review session: read-only with reduced context budget")

    return ExecutionStrategy(
        model_tier=tier,
        context_budget_chars=context_budget,
        checkpoint_threshold_chars=checkpoint_threshold,
        checkpoint_rule=checkpoint_rule,
        output_reduction=output_reduction,
        resource_ceiling=ceiling,
        provider_count=1,
        strategy_reason="; ".join(reasons),
    )


__all__ = [
    "CheckpointRule",
    "ExecutionStrategy",
    "ModelTier",
    "OutputReductionDirective",
    "ResourceCeiling",
    "select_strategy",
]
