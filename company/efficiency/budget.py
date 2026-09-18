"""Enforceable resource budget for one execution session.

A budget is derived from an ``ExecutionStrategy`` and checked against
observable session metrics.  The check is deterministic: exceeding a ceiling
produces an ``BudgetExceeded`` with the specific limit and current value,
which the briefing instructs the session to treat as a stop-and-escalate
signal rather than a suggestion.

## What is enforced vs. what is operator-applied

The **context budget** and **resource ceiling** are emitted in the briefing
as operator directives.  Company OS cannot enforce them inside an external
session it does not control; the runner applies them with its ``--max-turns``
flag and its context-window monitoring.  The **budget check** in this module
runs at finalization to measure whether the ceiling was respected, and records
the answer in the efficiency telemetry.

## Why advisory limits failed

The recorded BEFORE baseline shows every job used the strongest model and
accumulated 1.3M–2.5M cached context units.  No advisory limit was in the
execution path.  The enforced ceiling is a stated number in the briefing JSON,
and the finalization check records whether it was respected.
"""

from __future__ import annotations

from dataclasses import dataclass

from .strategy import ExecutionStrategy, ResourceCeiling


@dataclass(frozen=True)
class BudgetCheck:
    """Result of checking one session against its resource budget."""

    within_budget: bool
    context_chars_used: int | None
    context_budget_chars: int
    turns_used: int | None
    max_turns: int
    tool_calls_used: int | None
    max_tool_calls: int
    input_tokens_used: int | None
    max_input_tokens: int
    violations: tuple[str, ...]

    @property
    def exceeded(self) -> bool:
        return not self.within_budget


def check_budget(
    strategy: ExecutionStrategy,
    *,
    context_chars: int | None = None,
    turns: int | None = None,
    tool_calls: int | None = None,
    input_tokens: int | None = None,
) -> BudgetCheck:
    """Check observable session metrics against the strategy's budget."""
    ceiling = strategy.resource_ceiling
    violations: list[str] = []

    if context_chars is not None and context_chars > strategy.context_budget_chars:
        violations.append(
            f"context {context_chars} chars exceeds budget of "
            f"{strategy.context_budget_chars} chars"
        )
    if turns is not None and turns > ceiling.max_turns:
        violations.append(
            f"{turns} turns exceeds ceiling of {ceiling.max_turns}"
        )
    if tool_calls is not None and tool_calls > ceiling.max_tool_calls:
        violations.append(
            f"{tool_calls} tool calls exceeds ceiling of {ceiling.max_tool_calls}"
        )
    if input_tokens is not None and input_tokens > ceiling.max_input_tokens_estimate:
        violations.append(
            f"{input_tokens} input tokens exceeds ceiling of "
            f"{ceiling.max_input_tokens_estimate}"
        )

    return BudgetCheck(
        within_budget=len(violations) == 0,
        context_chars_used=context_chars,
        context_budget_chars=strategy.context_budget_chars,
        turns_used=turns,
        max_turns=ceiling.max_turns,
        tool_calls_used=tool_calls,
        max_tool_calls=ceiling.max_tool_calls,
        input_tokens_used=input_tokens,
        max_input_tokens=ceiling.max_input_tokens_estimate,
        violations=tuple(violations),
    )


def should_checkpoint(
    strategy: ExecutionStrategy,
    *,
    context_chars: int,
    in_critical_section: bool = False,
    has_committed_progress: bool = False,
) -> bool:
    """Whether the session should checkpoint based on context growth.

    Returns True when:
    - Context exceeds the checkpoint threshold, AND
    - The session is not in a critical section, AND
    - There is committed progress that survives a fresh start.
    """
    if in_critical_section:
        return False
    if context_chars < strategy.checkpoint_threshold_chars:
        return False
    return has_committed_progress


__all__ = [
    "BudgetCheck",
    "check_budget",
    "should_checkpoint",
]
