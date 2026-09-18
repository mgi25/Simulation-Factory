"""Which resource limits the company can hold, and which it can only observe.

This module exists because the previous one lied by omission. It compared a
session against four ceilings and reported "within budget", and three of the
four comparisons could not fail:

- `turns` was handed `receipt.usage.passes + receipt.usage.retries`, which the
  runner hard-codes to `1 + 0`, against a ceiling of 80;
- `input_tokens` was handed `usage.input_units`, which for a cached Claude
  Code session is the *uncached* input of the final request - around 40 - and
  was compared against 800,000;
- `tool_calls` was `num_turns` under a different name.

A check that cannot fail is worse than no check. It produces a record saying
the budget was respected, and the next reader believes it.

## The three classes

Every budget dimension is now declared as exactly one of:

`LIVE_ENFORCEABLE`
    Something stops the session when the value is reached, while it runs. The
    wall-clock ceiling qualifies because the runner owns the child process and
    kills it. A session cost ceiling qualifies *only when the backend exposes
    a flag for it*, which is a per-backend fact the runner supplies, not an
    assumption this module may make.

`POST_SESSION_OBSERVABLE`
    The value is known truthfully, but only after the session has finished.
    Tokens, cache reads and cost are of this kind. They are worth recording,
    worth comparing against a ceiling, and must never be described as limits:
    exceeding one is a fact about a session that has already been paid for.

`UNAVAILABLE`
    The company has no trustworthy value at all, for any session, by
    construction. `repo_file_reads` and `repo_searches` are here: every
    backend this company drives (`tools/engineering_runner/backends.py`,
    `ClaudeCodeBackend.launch`) runs the CLI with `--output-format json`,
    which returns one final result envelope and never a per-tool-call log.
    There is no record, in any stored session, of which files a developer or
    reviewer read or what it searched for - not a defect to fix, a fact about
    the artifact the provider emits in this mode.

## What check_budget is for, now

It compares what is known against what was stated, labels every dimension with
its class, and refuses to score a dimension whose value the telemetry marked
unreliable. `BudgetCheck.enforced_violations` is the only property that may be
read as "a limit was broken"; `observed_violations` is a measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum

from .strategy import ExecutionStrategy


class Enforceability(str, Enum):
    """How much authority a stated ceiling actually carries."""

    LIVE_ENFORCEABLE = "live_enforceable"
    POST_SESSION_OBSERVABLE = "post_session_observable"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class BudgetDimension:
    """One measurable quantity, its ceiling, and what the company can do about it."""

    name: str
    enforceability: Enforceability
    note: str


# The table. Declared once, read everywhere, and deliberately not derived from
# whatever happens to be present in a receipt - a dimension's class is a fact
# about the execution plane, not about one record.
DIMENSIONS: tuple[BudgetDimension, ...] = (
    BudgetDimension(
        name="wall_seconds",
        enforceability=Enforceability.LIVE_ENFORCEABLE,
        note=(
            "the runner owns the session's child process and terminates it at "
            "the timeout; this is enforced by the operating system, not by the "
            "session agreeing to stop"
        ),
    ),
    BudgetDimension(
        name="session_cost",
        enforceability=Enforceability.LIVE_ENFORCEABLE,
        note=(
            "enforced by the backend when it exposes a per-session spend flag "
            "and the runner passes it; the runner reports which backends did, "
            "and a backend that did not downgrades this to observation"
        ),
    ),
    BudgetDimension(
        name="developer_attempts",
        enforceability=Enforceability.LIVE_ENFORCEABLE,
        note=(
            "the job state machine refuses the transition; an exhausted work "
            "order cannot re-enter developing without a new authorization"
        ),
    ),
    BudgetDimension(
        name="context_refs",
        enforceability=Enforceability.LIVE_ENFORCEABLE,
        note=(
            "the packet is built with the narrowed reference set, so an "
            "over-budget packet is never issued rather than issued and scored"
        ),
    ),
    BudgetDimension(
        name="context_chars",
        enforceability=Enforceability.POST_SESSION_OBSERVABLE,
        note=(
            "the packet's own size is known when it is built, but what the "
            "session then read into its context is not visible to the company"
        ),
    ),
    BudgetDimension(
        name="input_tokens",
        enforceability=Enforceability.POST_SESSION_OBSERVABLE,
        note="reported by the provider when the session ends",
    ),
    BudgetDimension(
        name="output_tokens",
        enforceability=Enforceability.POST_SESSION_OBSERVABLE,
        note="reported by the provider when the session ends",
    ),
    BudgetDimension(
        name="cache_read_units",
        enforceability=Enforceability.POST_SESSION_OBSERVABLE,
        note=(
            "reported by the provider when the session ends; the profile now "
            "states a real ceiling for it (session_cache_read_ceiling) because "
            "this is the dimension a routine job's repository exploration "
            "actually shows up in - a bounded change reading far more cache "
            "than the packet it was given, turn over turn"
        ),
    ),
    BudgetDimension(
        name="model_turns",
        enforceability=Enforceability.POST_SESSION_OBSERVABLE,
        note=(
            "no backend this company drives accepts a turn ceiling, so this "
            "can never be an enforced_violation; but the provider's count is "
            "now cross-checked at read time (modelUsage against the envelope's "
            "top-level usage) and marked in receipt.usage.unreliable_metrics "
            "when the two disagree, so a session not so marked has a "
            "trustworthy value worth comparing against the strategy's "
            "advisory ceiling"
        ),
    ),
    BudgetDimension(
        name="repo_file_reads",
        enforceability=Enforceability.UNAVAILABLE,
        note=(
            "no stored session, of any age, carries a per-tool-call log; "
            "see the UNAVAILABLE class note above. Declared so a reader of "
            "this table sees the gap named rather than the dimension simply "
            "missing"
        ),
    ),
    BudgetDimension(
        name="repo_searches",
        enforceability=Enforceability.UNAVAILABLE,
        note=(
            "same as repo_file_reads: a grep or glob issued inside a coding "
            "session leaves no trace this company can read"
        ),
    ),
)

DIMENSIONS_BY_NAME = {dimension.name: dimension for dimension in DIMENSIONS}


def dimension(name: str) -> BudgetDimension:
    try:
        return DIMENSIONS_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(f"unknown budget dimension {name!r}") from exc


@dataclass(frozen=True)
class DimensionResult:
    """One dimension scored, or explicitly not scored and why."""

    name: str
    enforceability: Enforceability
    ceiling: str
    observed: str
    exceeded: bool
    scored: bool
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "enforceability": self.enforceability.value,
            "ceiling": self.ceiling,
            "observed": self.observed,
            "exceeded": self.exceeded,
            "scored": self.scored,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class BudgetCheck:
    """Every dimension's result, split by whether a breach means anything."""

    results: tuple[DimensionResult, ...]

    @property
    def enforced_violations(self) -> tuple[str, ...]:
        """Breaches of limits something actually holds. A real failure."""
        return tuple(
            result.detail
            for result in self.results
            if result.exceeded
            and result.enforceability is Enforceability.LIVE_ENFORCEABLE
        )

    @property
    def observed_violations(self) -> tuple[str, ...]:
        """Ceilings passed that nothing was stopping. A measurement, not a fault."""
        return tuple(
            result.detail
            for result in self.results
            if result.exceeded
            and result.enforceability is Enforceability.POST_SESSION_OBSERVABLE
        )

    @property
    def unscored(self) -> tuple[str, ...]:
        return tuple(result.name for result in self.results if not result.scored)

    @property
    def within_budget(self) -> bool:
        """True when nothing that could be enforced was broken.

        Deliberately not "nothing exceeded anything". A session that read more
        tokens than the strategy hoped is over an estimate, not over a limit,
        and reporting it as a violation would make every real breach easier to
        ignore.
        """
        return not self.enforced_violations

    @property
    def exceeded(self) -> bool:
        return not self.within_budget

    def to_dict(self) -> dict[str, object]:
        return {
            "within_budget": self.within_budget,
            "enforced_violations": list(self.enforced_violations),
            "observed_violations": list(self.observed_violations),
            "unscored": list(self.unscored),
            "dimensions": [result.to_dict() for result in self.results],
        }


def _decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def check_budget(
    strategy: ExecutionStrategy,
    *,
    wall_seconds: float | None = None,
    session_cost: str | Decimal | None = None,
    cost_ceiling_enforced: bool = False,
    context_chars: int | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_units: int | None = None,
    model_turns: int | None = None,
    unreliable: frozenset[str] | set[str] | tuple[str, ...] = (),
) -> BudgetCheck:
    """Score one finished session against the strategy it was issued.

    Every keyword is optional and `None` means "the company has no value",
    which is recorded as unscored rather than silently passed. `unreliable`
    names dimensions the telemetry layer marked untrustworthy; those are not
    scored either, because a check against a number known to be wrong is the
    defect this module was written to remove.

    `cost_ceiling_enforced` is supplied by whoever launched the session and
    says whether the backend was actually given the spend flag. Without it the
    cost ceiling is downgraded to an observation, because a limit nobody
    passed to the provider did not bind anything.

    `model_turns` is `receipt.usage.model_turns` - already captured, already
    named, already excluded from `unreliable_metrics` when the provider's two
    turn counts disagreed. Pass it through and it is scored like any other
    POST_SESSION_OBSERVABLE dimension; leave it `None` (the caller did not
    have it, or marked it unreliable) and it stays unscored, same as before.
    """
    ceiling = strategy.resource_ceiling
    untrusted = frozenset(unreliable)
    results: list[DimensionResult] = []

    def score(
        name: str,
        ceiling_value: object,
        observed: object,
        exceeded: bool,
        *,
        enforceability: Enforceability | None = None,
        detail: str = "",
    ) -> None:
        spec = dimension(name)
        klass = enforceability or spec.enforceability
        scored = observed is not None and name not in untrusted
        if not scored:
            reason = (
                f"{name}: marked unreliable by telemetry"
                if name in untrusted
                else f"{name}: no value supplied"
            )
            results.append(
                DimensionResult(
                    name=name,
                    enforceability=klass,
                    ceiling=str(ceiling_value),
                    observed="",
                    exceeded=False,
                    scored=False,
                    detail=reason,
                )
            )
            return
        results.append(
            DimensionResult(
                name=name,
                enforceability=klass,
                ceiling=str(ceiling_value),
                observed=str(observed),
                exceeded=exceeded,
                scored=True,
                detail=detail or f"{name} {observed} against ceiling {ceiling_value}",
            )
        )

    over_wall = (
        wall_seconds is not None and float(wall_seconds) > ceiling.max_wall_seconds
    )
    score(
        "wall_seconds",
        ceiling.max_wall_seconds,
        None if wall_seconds is None else round(float(wall_seconds), 3),
        over_wall,
        detail=(
            f"the session ran {float(wall_seconds):.0f}s against a "
            f"{ceiling.max_wall_seconds}s ceiling"
            if over_wall
            else ""
        ),
    )

    cost_limit = _decimal(ceiling.max_session_cost)
    observed_cost = _decimal(session_cost)
    over_cost = (
        cost_limit is not None and observed_cost is not None and observed_cost > cost_limit
    )
    score(
        "session_cost",
        ceiling.max_session_cost or "none",
        None if observed_cost is None else str(observed_cost),
        over_cost,
        enforceability=(
            Enforceability.LIVE_ENFORCEABLE
            if cost_ceiling_enforced
            else Enforceability.POST_SESSION_OBSERVABLE
        ),
        detail=(
            f"the session cost {observed_cost} {ceiling.cost_currency} against a "
            f"{ceiling.max_session_cost} ceiling"
            if over_cost
            else ""
        ),
    )

    score(
        "context_chars",
        strategy.context_budget_chars,
        context_chars,
        context_chars is not None and context_chars > strategy.context_budget_chars,
    )
    score("input_tokens", "observation only", input_tokens, False)
    score("output_tokens", "observation only", output_tokens, False)

    over_cache = (
        cache_read_units is not None
        and cache_read_units > ceiling.max_cache_read_units
    )
    score(
        "cache_read_units",
        ceiling.max_cache_read_units,
        cache_read_units,
        over_cache,
        detail=(
            f"the session read {cache_read_units} cache units against a "
            f"{ceiling.max_cache_read_units} ceiling - repository exploration, "
            "not the packet, is almost certainly why"
            if over_cache
            else ""
        ),
    )

    over_turns = model_turns is not None and model_turns > ceiling.max_turns
    score(
        "model_turns",
        ceiling.max_turns,
        model_turns,
        over_turns,
        detail=(
            f"the session ran {model_turns} turns against a {ceiling.max_turns} "
            "advisory ceiling; nothing stopped it, because no backend this "
            "company drives accepts a turn ceiling"
            if over_turns
            else ""
        ),
    )

    # Declared, never scorable: see Enforceability.UNAVAILABLE above. Recorded
    # so a reader of one BudgetCheck sees the gap stated, not just absent.
    score("repo_file_reads", "not observable", None, False)
    score("repo_searches", "not observable", None, False)

    return BudgetCheck(results=tuple(results))


def should_checkpoint(
    strategy: ExecutionStrategy,
    *,
    context_chars: int,
    in_critical_section: bool = False,
    has_committed_progress: bool = False,
) -> bool:
    """Whether the session should checkpoint based on context growth.

    True when context exceeds the checkpoint threshold, the session is not in
    a critical section, and there is committed progress that survives a fresh
    start. Without committed progress a checkpoint throws the work away, which
    costs more than continuing.
    """
    if in_critical_section:
        return False
    if context_chars < strategy.checkpoint_threshold_chars:
        return False
    return has_committed_progress


__all__ = [
    "DIMENSIONS",
    "DIMENSIONS_BY_NAME",
    "BudgetCheck",
    "BudgetDimension",
    "DimensionResult",
    "Enforceability",
    "check_budget",
    "dimension",
    "should_checkpoint",
]
