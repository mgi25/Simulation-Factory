"""How much of itself the company is willing to spend on one job.

A resource profile is the small set of ceilings that decide how a routine
engineering job is executed: how strong a model it may ask for, how many
automatic attempts it gets, how long one session may run, how much context it
may carry. It is the knob that was missing — before this module every job was
executed as though resources were unlimited, and the measured consequence was
that a routine work order selected the strongest model and read 2.1M cached
context units to add two fields to a dataclass.

## Why a profile and not a config flag

The individual ceilings are not independent. "One provider" and "no parallel
sessions" and "one developer attempt" and "standard model by default" are one
decision — *this company is running on one ordinary consumer subscription* —
expressed four times. Splitting them into four settings makes three-quarters
of a profile reachable, and a half-applied economy is the one that costs the
most: it narrows the context and then spends the saving on a retry.

So a profile is a named, frozen record, chosen by name, and every ceiling is
read from it.

## Why no provider quotas here

Not one number in this module comes from a subscription. There is no "45
messages per five hours", no token allowance, no request-per-minute figure.
Those belong to a vendor, they change without notice, and a company that
encodes them has to be rewritten when a plan is renamed.

What is here instead are **the company's own ceilings**: how many attempts the
company is willing to authorize automatically, how long the company is willing
to let one session run, how much a single session may cost the company. The
mapping from those onto whatever a provider actually meters is the runner's
job, at the edge, where the vendor already lives.

`session_cost_ceiling` is the one that looks like a quota and is not. It is
what the *company* decides a single session is worth, in its own accounting
currency; the plan it is bought under does not appear.

## What "enforced" means here, and what it does not

A profile states ceilings. Which ones can be *held* is a different question,
answered by `company.efficiency.budget.DIMENSIONS`, and the two must be read
together: a wall-clock ceiling is enforced by the process that launches the
session, a cost ceiling is enforced by the provider when the CLI exposes a
flag for it, and a turn ceiling is at present only advice, because no CLI this
company drives accepts one. Stating a limit is not imposing it, and this
module deliberately never claims otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Mapping

from .strategy import ModelTier


class ResourceProfileName(str, Enum):
    """The profiles the company knows. Two is the smallest honest number."""

    CONSUMER = "consumer"
    EXPANDED = "expanded"


DEFAULT_PROFILE_NAME = ResourceProfileName.CONSUMER


@dataclass(frozen=True)
class ResourceProfile:
    """One named set of ceilings for ordinary company operation.

    Every field is a Company-controlled quantity. None is a provider quota,
    and none names a vendor, a plan or a model.
    """

    name: ResourceProfileName

    # --- concurrency -----------------------------------------------------
    # How many providers may be engaged for one job, and how many model
    # sessions may be alive at once. Consumer mode is 1 and 1: a second
    # provider is a second bill, and a second session is the same bill twice.
    provider_count: int
    parallel_sessions: int

    # --- the automatic loop ----------------------------------------------
    # `developer_attempts` is the number of developer sessions the company
    # will spend without asking. `auto_continue_after_changes_required` is
    # whether a reviewer verdict of changes_required may start another one by
    # itself. Consumer mode is 1 and False, which together mean: one
    # implementation, one review, and then a person decides.
    developer_attempts: int
    reviewer_passes: int
    auto_continue_after_changes_required: bool

    # --- model strength ---------------------------------------------------
    # The tier a routine job gets, and whether anything stronger has to be
    # justified. `strongest_requires_escalation` does not remove the strongest
    # tier; it removes it as a *default*.
    routine_tier: ModelTier
    strongest_requires_escalation: bool

    # --- context ----------------------------------------------------------
    # The hard cap on how many references one packet may carry, and the
    # characters-per-reference figure the context budget is derived from.
    context_ref_ceiling: int
    chars_per_ref: int
    # Whether the capsule assembler may follow the capsule graph's dependency
    # edges and add them to the packet.
    #
    # This is the one context lever that is worth real material. A packet is
    # about 1.5 KB whatever it carries, because it carries *pointers*; what
    # costs is what a session then reads. Measured on this company's own
    # routine work order: the capsule that owns the subject is 3,661
    # characters and the five transitive dependencies the assembler added
    # behind it are 13,324 more. A bounded change to a known contract needs
    # the contract. It does not need the closure.
    #
    # `company.engineering.orchestrator` turns this back on for a job that
    # carries a specialist domain or an escalation, because specialist work is
    # exactly the case where the graph is the point.
    include_capsule_dependencies: bool

    # --- one session's lifetime -------------------------------------------
    # Wall seconds is enforceable by whoever launches the process. The turn
    # ceiling is advisory today. The cost ceiling is enforceable only when the
    # backend exposes a flag for it; the company states it either way.
    session_wall_seconds: int
    session_turn_ceiling: int
    session_cost_ceiling: Decimal | None
    cost_currency: str
    # A repository-exploration proxy, not a turn or a cost figure. Company OS
    # cannot see a file read or a grep - `tools/engineering_runner`'s backend
    # runs the CLI with `--output-format json`, which returns one final
    # envelope and no per-tool-call log, for every session this company has
    # ever recorded. What it *can* see is `cache_read_units`: context re-sent
    # on every turn, which grows with exactly what a session reads. Measured
    # on this company's own dogfood work order under Consumer Mode V1 - two
    # files changed, one developer attempt - the developer session alone read
    # 1,835,390 cache units. This ceiling is set below that measured number on
    # purpose, so a session that explores the way that one did is flagged
    # rather than accepted silently. It is POST_SESSION_OBSERVABLE, the same
    # class as the cost and token counts beside it: nothing stops the read
    # while it happens, and exceeding this is a fact about a session already
    # paid for, never an enforced limit.
    session_cache_read_ceiling: int

    # --- one job's lifetime -----------------------------------------------
    # How many runner stages one work order may consume before the runner
    # stops and hands back a checkpoint. A stage is developer, review or gate.
    stage_ceiling: int

    # The fraction of the context budget at which a session should checkpoint
    # and continue in a fresh session rather than growing.
    checkpoint_fraction: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, ResourceProfileName):
            raise ValueError("profile name must be a ResourceProfileName")
        for field_name in (
            "provider_count",
            "parallel_sessions",
            "developer_attempts",
            "reviewer_passes",
            "context_ref_ceiling",
            "chars_per_ref",
            "session_wall_seconds",
            "session_turn_ceiling",
            "session_cache_read_ceiling",
            "stage_ceiling",
        ):
            value = getattr(self, field_name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{self.name.value}.{field_name} must be a positive integer")
        if not isinstance(self.routine_tier, ModelTier):
            raise ValueError("routine_tier must be a ModelTier")
        if not isinstance(self.include_capsule_dependencies, bool):
            raise ValueError("include_capsule_dependencies must be a boolean")
        if self.session_cost_ceiling is not None:
            if not isinstance(self.session_cost_ceiling, Decimal):
                raise ValueError("session_cost_ceiling must be a Decimal or None")
            if self.session_cost_ceiling <= 0:
                raise ValueError("session_cost_ceiling must be positive when set")
            if not self.cost_currency.strip():
                raise ValueError("session_cost_ceiling requires a currency")
        if not 0.0 < self.checkpoint_fraction <= 1.0:
            raise ValueError("checkpoint_fraction must be in (0, 1]")

    @property
    def context_budget_chars(self) -> int:
        """The character ceiling a session's model-visible context should respect."""
        return self.context_ref_ceiling * self.chars_per_ref

    @property
    def checkpoint_threshold_chars(self) -> int:
        return int(self.context_budget_chars * self.checkpoint_fraction)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name.value,
            "provider_count": self.provider_count,
            "parallel_sessions": self.parallel_sessions,
            "developer_attempts": self.developer_attempts,
            "reviewer_passes": self.reviewer_passes,
            "auto_continue_after_changes_required": (
                self.auto_continue_after_changes_required
            ),
            "routine_tier": self.routine_tier.value,
            "strongest_requires_escalation": self.strongest_requires_escalation,
            "context_ref_ceiling": self.context_ref_ceiling,
            "context_budget_chars": self.context_budget_chars,
            "include_capsule_dependencies": self.include_capsule_dependencies,
            "session_wall_seconds": self.session_wall_seconds,
            "session_turn_ceiling": self.session_turn_ceiling,
            "session_cache_read_ceiling": self.session_cache_read_ceiling,
            "session_cost_ceiling": (
                str(self.session_cost_ceiling)
                if self.session_cost_ceiling is not None
                else None
            ),
            "cost_currency": self.cost_currency if self.session_cost_ceiling else "",
            "stage_ceiling": self.stage_ceiling,
            "checkpoint_threshold_chars": self.checkpoint_threshold_chars,
        }


# One ordinary consumer subscription, one provider, one session at a time.
#
# The numbers are read off the measured history rather than guessed. A
# developer session on this company's own work orders ran 200-1000 s and cost
# $1.41-$3.78; a review ran under 300 s and cost $0.30-$0.37. A wall ceiling of
# 1800 s therefore stops a session that has stopped making progress without
# cutting off one that is merely thorough, and a $3.00 session ceiling sits
# above every honest session this company has recorded and below the runaway
# that prompted this milestone.
CONSUMER = ResourceProfile(
    name=ResourceProfileName.CONSUMER,
    provider_count=1,
    parallel_sessions=1,
    developer_attempts=1,
    reviewer_passes=1,
    auto_continue_after_changes_required=False,
    routine_tier=ModelTier.STANDARD,
    strongest_requires_escalation=True,
    context_ref_ceiling=8,
    chars_per_ref=4_000,
    include_capsule_dependencies=False,
    session_wall_seconds=1_800,
    session_turn_ceiling=40,
    session_cache_read_ceiling=1_000_000,
    session_cost_ceiling=Decimal("3.00"),
    cost_currency="USD",
    stage_ceiling=4,
    checkpoint_fraction=0.7,
)


# What the company runs on when somebody has explicitly paid for more. Kept
# because "consumer" only means something if there is another answer, and
# because the correction loop the engineering brief describes is legitimate
# work when the resources for it exist.
EXPANDED = ResourceProfile(
    name=ResourceProfileName.EXPANDED,
    provider_count=1,
    parallel_sessions=1,
    developer_attempts=3,
    reviewer_passes=2,
    auto_continue_after_changes_required=True,
    routine_tier=ModelTier.STANDARD,
    strongest_requires_escalation=False,
    context_ref_ceiling=20,
    chars_per_ref=4_000,
    include_capsule_dependencies=True,
    session_wall_seconds=3_600,
    session_turn_ceiling=120,
    session_cache_read_ceiling=3_000_000,
    session_cost_ceiling=Decimal("12.00"),
    cost_currency="USD",
    stage_ceiling=12,
    checkpoint_fraction=0.7,
)


PROFILES: Mapping[ResourceProfileName, ResourceProfile] = {
    ResourceProfileName.CONSUMER: CONSUMER,
    ResourceProfileName.EXPANDED: EXPANDED,
}


def resource_profile(name: str | ResourceProfileName | None = None) -> ResourceProfile:
    """Look one up by name. An unknown name is refused, never defaulted.

    Defaulting an unrecognised profile to the cheap one would be the friendly
    behaviour and the wrong one: a typo in a work order would silently pick a
    policy nobody asked for, and the record would say the company had chosen it.
    """
    if name is None or name == "":
        return PROFILES[DEFAULT_PROFILE_NAME]
    if isinstance(name, ResourceProfileName):
        return PROFILES[name]
    try:
        key = ResourceProfileName(str(name).strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ResourceProfileName)
        raise ValueError(
            f"unknown resource profile {name!r}; the company knows: {allowed}"
        ) from exc
    return PROFILES[key]


def profile_names() -> tuple[str, ...]:
    return tuple(item.value for item in ResourceProfileName)


__all__ = [
    "CONSUMER",
    "DEFAULT_PROFILE_NAME",
    "EXPANDED",
    "PROFILES",
    "ResourceProfile",
    "ResourceProfileName",
    "profile_names",
    "resource_profile",
]
