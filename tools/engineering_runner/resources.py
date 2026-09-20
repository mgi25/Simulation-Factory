"""Reading the resource strategy Company OS recommends, and holding it to it.

Company OS decides how much of itself a job is worth: which model tier, how
long one session may run, what it may cost, how much context it may carry. It
cannot apply any of that, because it does not start processes. This module is
the other half - the runner's reader for that recommendation, and the place
where a tier becomes a vendor model name.

## Why the tier is a tier and not a model name

`company/efficiency` never names a model. Constitution rule 13: a router that
hard-codes a vendor is rewritten when the vendor changes one. So the strategy
says `standard` or `strongest`, and the mapping onto `--model` lives here, in
the adapter that already knows what a `--permission-mode` is. Changing
providers changes this file and nothing in the company.

The defaults are *aliases*, not pinned versions. `sonnet` and `opus` follow
whatever the account's latest of each is; a pinned id goes stale silently, and
a stale id is a session that fails at launch rather than one that runs cheaply.

## What this artifact may not do

It may only make a session smaller. There is no field in `ResourceStrategy`
that names a path, a branch, a tool or an employee, and `parse` refuses a
payload that carries one rather than ignoring it. An artifact that could widen
authority would be a second place a work order's scope is decided, and there is
exactly one.

`AuthorityEnvelope` is unaffected by anything here: it reads the same briefing
and refuses one whose packet scope is not the work order's authorized paths,
whatever this block says.

## What is enforced, and what is only carried

- `max_wall_seconds` is **enforced**: the runner passes it as the session's
  process timeout and terminates the child.
- `max_session_cost` is **enforced when the backend accepts a spend flag**.
  `ClaudeCodeBackend` does (`--max-budget-usd`); `CodexBackend` does not.
  `cost_ceiling_enforced` on the outcome records which happened, and the
  company's budget check reads it rather than assuming.
- `max_turns` is **advisory**. No CLI this runner drives accepts a turn
  ceiling. It is written into the session's instructions as guidance and
  nothing scores against it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from .errors import IntegrityFailure


# The artifact versions this runner knows how to read. A version outside this
# set is refused: reading a payload whose fields may have moved is how a
# ceiling silently becomes zero.
SUPPORTED_VERSIONS: frozenset[int] = frozenset({1})

STANDARD = "standard"
STRONGEST = "strongest"
TIERS: frozenset[str] = frozenset({STANDARD, STRONGEST})

# Aliases, so the account's current model of each strength is what runs.
DEFAULT_TIER_MODELS: Mapping[str, str] = {
    STANDARD: "sonnet",
    STRONGEST: "opus",
}

# Keys that would make this artifact an authorization. Their presence is an
# error rather than something to ignore, because a field nobody validates is
# how a scope gets widened by a payload that was never meant to carry one.
AUTHORITY_KEYS: frozenset[str] = frozenset(
    {
        "authorized_paths",
        "may_write",
        "may_not_modify",
        "forbidden_paths",
        "protected_paths",
        "path_scope",
        "authorized_branch",
        "base_commit",
        "allowed_tools",
        "disallowed_tools",
        "employee",
        "required_tests",
    }
)


@dataclass(frozen=True)
class ResourceStrategy:
    """One session's resource recommendation, validated and ready to apply."""

    artifact_version: int
    profile: str
    model_tier: str
    escalation: str
    reasoning_class: str
    max_wall_seconds: int
    max_session_cost: str
    cost_currency: str
    max_turns_advisory: int
    context_budget_chars: int
    checkpoint_threshold_chars: int
    context_ref_count: int
    strategy_reason: str
    raw: Mapping[str, Any] = field(default_factory=dict)

    def model_for(self, tier_models: Mapping[str, str] | None = None) -> str:
        return dict(tier_models or DEFAULT_TIER_MODELS).get(self.model_tier, "")

    def cost_ceiling(self) -> Decimal | None:
        if not self.max_session_cost:
            return None
        try:
            value = Decimal(self.max_session_cost)
        except InvalidOperation:
            return None
        return value if value > 0 else None

    def summary(self) -> dict[str, Any]:
        return {
            "artifact_version": self.artifact_version,
            "profile": self.profile,
            "model_tier": self.model_tier,
            "escalation": self.escalation,
            "reasoning_class": self.reasoning_class,
            "max_wall_seconds": self.max_wall_seconds,
            "max_session_cost": self.max_session_cost,
            "cost_currency": self.cost_currency,
            "max_turns_advisory": self.max_turns_advisory,
            "context_budget_chars": self.context_budget_chars,
            "context_ref_count": self.context_ref_count,
            "strategy_reason": self.strategy_reason,
        }

    @classmethod
    def parse(cls, payload: Mapping[str, Any]) -> "ResourceStrategy":
        """Read the `efficiency` block of a briefing, refusing an unusable one.

        Refused rather than defaulted, for the same reason `AuthorityEnvelope`
        refuses an inconsistent briefing: a runner that invents a ceiling when
        it cannot read one has invented a policy.
        """
        if not isinstance(payload, Mapping):
            raise IntegrityFailure("a briefing must be a JSON object")
        block = payload.get("efficiency")
        if not isinstance(block, Mapping):
            raise IntegrityFailure(
                "the briefing carries no resource strategy; this runner will not "
                "guess one, because a guessed ceiling is a policy nobody wrote"
            )

        present = AUTHORITY_KEYS & set(block)
        if present:
            raise IntegrityFailure(
                "the resource strategy carries authority-shaped field(s): "
                + ", ".join(sorted(present))
                + ". A resource strategy may only make a session smaller; scope "
                "comes from the work order and from nowhere else."
            )

        version = _integer(block.get("artifact_version"), "artifact_version")
        if version not in SUPPORTED_VERSIONS:
            known = ", ".join(str(item) for item in sorted(SUPPORTED_VERSIONS))
            raise IntegrityFailure(
                f"resource strategy artifact version {version} is not one this "
                f"runner reads (knows: {known})"
            )

        tier = str(block.get("model_tier", "")).strip().lower()
        if tier not in TIERS:
            raise IntegrityFailure(
                f"resource strategy names model tier {tier!r}; this runner knows "
                + ", ".join(sorted(TIERS))
            )

        ceiling = block.get("resource_ceiling")
        if not isinstance(ceiling, Mapping):
            raise IntegrityFailure("the resource strategy carries no resource_ceiling")

        wall = _integer(ceiling.get("max_wall_seconds"), "max_wall_seconds")
        if wall <= 0:
            raise IntegrityFailure("max_wall_seconds must be positive")
        turns = _integer(ceiling.get("max_turns", 0), "max_turns")

        cost = str(ceiling.get("max_session_cost", "") or "")
        if cost:
            try:
                if Decimal(cost) <= 0:
                    raise IntegrityFailure("max_session_cost must be positive when set")
            except InvalidOperation as exc:
                raise IntegrityFailure(
                    f"max_session_cost {cost!r} is not a decimal amount"
                ) from exc

        context = block.get("context")
        context = context if isinstance(context, Mapping) else {}
        refs = context.get("refs")
        ref_count = len(refs) if isinstance(refs, (list, tuple)) else 0

        return cls(
            artifact_version=version,
            profile=str(block.get("profile", "")),
            model_tier=tier,
            escalation=str(block.get("escalation", "none")),
            reasoning_class=str(block.get("reasoning_class", "")),
            max_wall_seconds=wall,
            max_session_cost=cost,
            cost_currency=str(ceiling.get("cost_currency", "") or ""),
            max_turns_advisory=max(turns, 0),
            context_budget_chars=_integer(
                block.get("context_budget_chars", 0), "context_budget_chars"
            ),
            checkpoint_threshold_chars=_integer(
                block.get("checkpoint_threshold_chars", 0), "checkpoint_threshold_chars"
            ),
            context_ref_count=ref_count,
            strategy_reason=str(block.get("strategy_reason", "")),
            raw=dict(block),
        )


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntegrityFailure(f"resource strategy {name} must be a number")
    return int(value)


# --- deterministic output reduction --------------------------------------
#
# The honest boundary, stated once: **Company OS cannot compress the tool
# output inside a coding session.** That output is produced and consumed
# entirely within the external CLI's own process, in a conversation this
# runner never sees. Nothing in this repository can shrink it.
#
# What the runner *can* reduce is the output it captures itself and then puts
# back in front of a model - a test run, a git status, a gate report going into
# a reviewer's brief. That is what these functions do, and it is the whole
# claim.


def summarise_command(
    command: str,
    *,
    exit_code: int,
    stdout: str,
    max_failure_lines: int = 40,
    timed_out: bool = False,
) -> str:
    """One line for a success; the failure detail, bounded, for a failure.

    A passing command's output tells a model nothing it does not already learn
    from "it passed", and a 900-line green pytest run is 900 lines of context
    bought for one bit of information.
    """
    if timed_out:
        return f"{command}: timed out"
    if exit_code == 0:
        tail = _summary_line(stdout)
        return f"{command}: ok" + (f" ({tail})" if tail else "")
    return f"{command}: exit {exit_code}\n" + failure_detail(
        stdout, max_lines=max_failure_lines
    )


def failure_detail(stdout: str, *, max_lines: int = 40) -> str:
    """The lines that say what failed, and none of the ones that say what passed.

    Deterministic and order-preserving: a line is kept when it carries a
    failure marker, and the first `max_lines` kept lines are returned. No
    ranking, no truncation in the middle of a traceback line, nothing that
    would make the same output summarise two ways.
    """
    markers = (
        "fail",
        "error",
        "assert",
        "traceback",
        "exception",
        "no tests ran",
        "timed out",
    )
    kept: list[str] = []
    for line in stdout.splitlines():
        lowered = line.lower()
        if any(marker in lowered for marker in markers):
            kept.append(line.rstrip())
            if len(kept) >= max_lines:
                kept.append(f"... (truncated at {max_lines} lines)")
                break
    if not kept:
        tail = stdout.splitlines()[-max_lines:]
        return "\n".join(line.rstrip() for line in tail)
    return "\n".join(kept)


def _summary_line(stdout: str) -> str:
    for line in reversed(stdout.splitlines()):
        stripped = line.strip().strip("=").strip()
        if stripped and ("passed" in stripped or "no tests ran" in stripped):
            return stripped[:120]
    return ""


__all__ = [
    "AUTHORITY_KEYS",
    "DEFAULT_TIER_MODELS",
    "STANDARD",
    "STRONGEST",
    "SUPPORTED_VERSIONS",
    "TIERS",
    "ResourceStrategy",
    "failure_detail",
    "summarise_command",
]
