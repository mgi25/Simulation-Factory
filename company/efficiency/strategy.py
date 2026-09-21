"""Deterministic execution strategy selection by task complexity and risk.

Every engineering job the company issues carries an execution strategy in its
briefing. The strategy names the model tier the job should be run at, the
context budget the session should respect, the checkpoint rule that governs
fresh-context decisions, the ceilings on one session's lifetime, and the
output-reduction directives that bound what tool output enters model context.

The selection is deterministic: the same reasoning class, risk, escalation and
resource profile always produce the same strategy. Company OS *recommends*;
`tools/engineering_runner` validates the recommendation and applies whatever
part of it the backend can actually be held to. The company does not spawn a
session, so it cannot enforce one - and this module never pretends it does.

## Model tier

**Standard** is sufficient for routine C-class implementation: a bounded task,
low-to-medium risk, concrete acceptance criteria. **Strongest** is for class D
and above - specialist judgment, deep reasoning, multi-perspective review -
for HIGH and CRITICAL risk, for explicit escalation, and for a correction
attempt after a standard-tier attempt failed review. There is no tier below
standard: the quality constraint is hard.

The default used to be unreachable. `EngineeringWorkOrder.task_specification`
declared a specialist domain for every work order, so the classifier's
`specialist_reasoning` rule matched every job, every job was class D, and
strongest was the only tier production could produce. Fixing that - not
changing this table - is what made the cheap tier reachable.

## Context budget, and what it is derived from

The budget is a character ceiling on model-visible context. It is the number
of references the packet may carry, capped by the active resource profile,
times the per-capsule character ceiling the capsule layer already enforces.
A session approaching the ceiling checkpoints rather than growing.

## Checkpoint rule

A session checkpoints - saves progress, continues in a fresh context - when
accumulated context exceeds `checkpoint_threshold_chars`, the task is not in a
critical section, and at least one acceptance criterion has verifiable
progress. Starting fresh is cheap and safe once intermediate work is committed
and the remaining criteria are independent of the completed ones.

## Output reduction, and its honest boundary

The `reduce_*` functions here filter command output **the caller can see**.
A developer session's own tool output happens inside the external CLI, in a
process Company OS neither starts nor observes, so nothing in this module can
touch it. What these functions do reach is the output the *runner* captures
and puts back in front of a model: test runs, git status, gate reports. That
boundary is stated in `docs/company_os_consumer_resource_mode.md` and is not
papered over anywhere.

The rules: test output keeps failures and the summary and drops passing
detail; git output keeps changed paths and conflict markers and collapses a
clean tree to one line; log output keeps the last N lines plus every line
naming an error, failure or warning.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.resource_classes import ReasoningClass, Risk

if TYPE_CHECKING:  # the profile imports this module, so the arrow points one way
    from .profile import ResourceProfile


class ModelTier(str, Enum):
    """Which model strength the operator should apply."""

    ECONOMY = "economy"
    STANDARD = "standard"
    STRONGEST = "strongest"


@dataclass(frozen=True)
class AdaptiveRoutingDirective:
    """A cheaper-tier candidate, never an instruction to lower quality blindly."""

    eligible: bool
    downshift_tier: ModelTier
    static_reasons: tuple[str, ...]
    runtime_requirements: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "eligible": self.eligible,
            "downshift_tier": self.downshift_tier.value,
            "static_reasons": list(self.static_reasons),
            "runtime_requirements": list(self.runtime_requirements),
        }


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
    """Per-session ceilings, in Company terms, from the active resource profile.

    Every number here is the company's own. What can actually be *held* to a
    number is decided elsewhere - `company.efficiency.budget.DIMENSIONS` says
    which of these is live-enforceable, which is only observable afterwards,
    and which is neither. A ceiling and its enforceability are separate facts
    and are deliberately stored separately, because conflating them is how a
    company ends up believing a limit it never applied.
    """

    max_turns: int
    max_wall_seconds: int
    max_session_cost: str  # decimal string, or "" when the profile sets none
    cost_currency: str
    max_cache_read_units: int
    escalation_message: str

    @classmethod
    def from_profile(
        cls, profile: "ResourceProfile", *, is_review: bool = False
    ) -> "ResourceCeiling":
        """The profile's ceilings, halved for a review.

        A review reads a diff and answers criteria. It has never in this
        company's recorded history needed as long or cost as much as the
        implementation it judges, so giving it the same ceiling would state a
        limit that could not bind.
        """
        divisor = 2 if is_review else 1
        cost = profile.session_cost_ceiling
        return cls(
            max_turns=max(1, profile.session_turn_ceiling // divisor),
            max_wall_seconds=max(60, profile.session_wall_seconds // divisor),
            max_session_cost=str(cost / divisor) if cost is not None else "",
            cost_currency=profile.cost_currency if cost is not None else "",
            max_cache_read_units=max(
                1, profile.session_cache_read_ceiling // divisor
            ),
            escalation_message=(
                "Stop and report progress rather than exceeding these ceilings. "
                "An honest partial result with a checkpoint is cheaper than a "
                "complete one that ran out of budget."
            ),
        )


class EscalationReason(str, Enum):
    """Why a job was given the strongest tier despite classifying as routine."""

    NONE = "none"
    EXPLICIT = "explicit_escalation"
    CHEAPER_MODEL_FAILED = "cheaper_capable_model_failed"


@dataclass(frozen=True)
class ExecutionStrategy:
    """The complete execution strategy for one job, emitted in the briefing."""

    model_tier: ModelTier
    context_budget_chars: int
    checkpoint_threshold_chars: int
    checkpoint_rule: CheckpointRule
    output_reduction: OutputReductionDirective
    resource_ceiling: ResourceCeiling
    provider_count: int
    parallel_sessions: int
    profile_name: str
    escalation: EscalationReason
    strategy_reason: str
    adaptive_routing: AdaptiveRoutingDirective

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile_name,
            "model_tier": self.model_tier.value,
            "escalation": self.escalation.value,
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
                "max_wall_seconds": self.resource_ceiling.max_wall_seconds,
                "max_session_cost": self.resource_ceiling.max_session_cost,
                "cost_currency": self.resource_ceiling.cost_currency,
                "max_cache_read_units": self.resource_ceiling.max_cache_read_units,
                "escalation_message": self.resource_ceiling.escalation_message,
            },
            "provider_count": self.provider_count,
            "parallel_sessions": self.parallel_sessions,
            "strategy_reason": self.strategy_reason,
            "adaptive_routing": self.adaptive_routing.to_dict(),
        }


# --- strategy selection ---------------------------------------------------

# Reasoning classes that describe work a standard-tier model should not be
# asked to lead: specialist domain judgment and above. This is the list the
# classifier produces for genuinely complex architecture, for security and
# governance work, and for anything high-risk - see `ai_platform/README.md`
# and the rule table in `ai_platform.resource_classes.RULES`.
_SPECIALIST_CLASSES: frozenset[ReasoningClass] = frozenset(
    {ReasoningClass.D, ReasoningClass.E, ReasoningClass.F}
)


def select_strategy(
    reasoning_class: ReasoningClass,
    risk: Risk,
    *,
    evidence_required: bool = False,
    max_context_refs: int = 6,
    is_review: bool = False,
    profile: "ResourceProfile | None" = None,
    escalation: EscalationReason = EscalationReason.NONE,
    authorized_path_count: int = 0,
    required_test_count: int = 0,
    packet_attempt: int = 0,
    novel: bool = False,
    specialist_domain: str = "",
) -> ExecutionStrategy:
    """Select execution strategy deterministically from task properties.

    The tier rule, and the four ways to reach the strongest model:

    - **class D and above** - specialist judgment, deep reasoning or
      multi-perspective review. This is where genuinely complex architecture
      and security/governance work land, because that is what the classifier
      routes them to.
    - **HIGH or CRITICAL risk** - independently of class.
    - **explicit escalation** - a person asked for it.
    - **a cheaper capable model already failed** - a correction attempt after a
      standard-tier attempt did not satisfy review.

    Everything else is routine and gets the profile's routine tier. That is
    the whole cost lever, and before this milestone it could not be pulled:
    every engineering work order declared a specialist domain, so every job
    classified D and the standard tier was unreachable in production.

    `evidence_required` affects review depth, never model strength. A bounded
    C-class change that must cite its evidence is still a bounded C-class
    change.
    """
    from .profile import resource_profile

    active = profile if profile is not None else resource_profile()

    specialist = reasoning_class in _SPECIALIST_CLASSES
    dangerous = risk in (Risk.HIGH, Risk.CRITICAL)
    escalated = escalation is not EscalationReason.NONE
    needs_strongest = specialist or dangerous or escalated
    tier = ModelTier.STRONGEST if needs_strongest else active.routine_tier

    # The context budget is the smaller of what the task asked for and what
    # the profile allows. A packet that carries more refs than the profile's
    # ceiling is a packet the profile did not authorize, so the budget is
    # computed from the ceiling rather than from the request.
    effective_refs = min(max(max_context_refs, 1), active.context_ref_ceiling)
    context_budget = effective_refs * active.chars_per_ref
    if is_review:
        # A reviewer reads; it does not build up a working set.
        context_budget = int(context_budget * 0.6)
    checkpoint_threshold = int(context_budget * active.checkpoint_fraction)

    if is_review:
        checkpoint_rule = CheckpointRule.CONTINUE
    elif needs_strongest:
        checkpoint_rule = CheckpointRule.CHECKPOINT_ON_THRESHOLD
    else:
        checkpoint_rule = CheckpointRule.CONTINUE

    output_reduction = (
        OutputReductionDirective.full()
        if reasoning_class in (ReasoningClass.E, ReasoningClass.F)
        else OutputReductionDirective.standard()
    )
    ceiling = ResourceCeiling.from_profile(active, is_review=is_review)

    economy_checks = {
        "developer session": not is_review,
        "consumer profile": active.name.value == "consumer",
        "reasoning class C": reasoning_class is ReasoningClass.C,
        "low risk": risk is Risk.LOW,
        "no escalation": escalation is EscalationReason.NONE,
        "first attempt": packet_attempt == 1,
        "one writable path": authorized_path_count == 1,
        "one or two required tests": 1 <= required_test_count <= 2,
        "not novel": not novel,
        "no specialist domain": not specialist_domain.strip(),
        "standard recommended tier": tier is ModelTier.STANDARD,
    }
    economy_eligible = all(economy_checks.values())
    adaptive_routing = AdaptiveRoutingDirective(
        eligible=economy_eligible,
        downshift_tier=ModelTier.ECONOMY,
        static_reasons=tuple(
            name for name, passed in economy_checks.items() if passed
        ),
        runtime_requirements=(
            "base diagnostic ran",
            "base diagnostic found at least one failing required test",
            "every failure-symbol hint is present as a failure-guided compiled span",
            "operator did not pin a developer model",
        ),
    )

    reasons: list[str] = []
    if specialist:
        reasons.append(f"reasoning class {reasoning_class.value} requires specialist depth")
    if dangerous:
        reasons.append(f"risk {risk.value} requires careful analysis")
    if escalation is EscalationReason.EXPLICIT:
        reasons.append("the strongest tier was explicitly escalated for this job")
    if escalation is EscalationReason.CHEAPER_MODEL_FAILED:
        reasons.append(
            "a standard-tier attempt did not satisfy review, so the next attempt "
            "escalates"
        )
    if not needs_strongest:
        reasons.append(
            f"reasoning class {reasoning_class.value} at risk {risk.value} "
            f"is routine implementation; profile {active.name.value} runs it at "
            f"the {active.routine_tier.value} tier"
        )
    if evidence_required:
        reasons.append("evidence is required and affects review depth, not model tier")
    if is_review:
        reasons.append("review session: read-only with reduced context budget")
    if economy_eligible:
        reasons.append(
            "candidate for an economy downshift only if the runner's deterministic "
            "base diagnostic localizes every failure into compiled context"
        )

    return ExecutionStrategy(
        model_tier=tier,
        context_budget_chars=context_budget,
        checkpoint_threshold_chars=checkpoint_threshold,
        checkpoint_rule=checkpoint_rule,
        output_reduction=output_reduction,
        resource_ceiling=ceiling,
        provider_count=active.provider_count,
        parallel_sessions=active.parallel_sessions,
        profile_name=active.name.value,
        escalation=escalation,
        strategy_reason="; ".join(reasons),
        adaptive_routing=adaptive_routing,
    )


def reduce_test_output(raw: str, directive: OutputReductionDirective) -> str:
    """Deterministically filter test output before it enters model context.

    When ``omit_passing_test_detail`` is True, passing test lines are stripped
    and only failures, errors and the summary line are kept.  The result is
    always shorter or equal; it never adds content.
    """
    if not directive.omit_passing_test_detail:
        return raw
    lines = raw.splitlines()
    kept: list[str] = []
    for line in lines:
        lower = line.lower()
        is_important = (
            "fail" in lower
            or "error" in lower
            or "warning" in lower
            or lower.startswith("collected ")
            or lower.lstrip().startswith("=")
            or "passed" in lower and ("failed" in lower or "error" in lower)
        )
        if is_important:
            kept.append(line)
    if len(kept) > directive.max_test_failure_lines:
        kept = kept[: directive.max_test_failure_lines]
    if not kept:
        return "all tests passed" if lines else raw
    return "\n".join(kept)


def reduce_log_output(raw: str, directive: OutputReductionDirective) -> str:
    """Keep only the last N lines plus any line containing error/fail/warning."""
    lines = raw.splitlines()
    if len(lines) <= directive.max_log_lines:
        return raw
    important: list[str] = []
    for line in lines[: -directive.max_log_lines]:
        lower = line.lower()
        if "error" in lower or "fail" in lower or "warning" in lower:
            important.append(line)
    tail = lines[-directive.max_log_lines :]
    result = important + tail
    return "\n".join(result)


def reduce_git_output(raw: str, directive: OutputReductionDirective) -> str:
    """Reduce git status/diff output when clean detail is not needed."""
    if not directive.omit_clean_git_detail:
        return raw
    lines = raw.splitlines()
    if not lines:
        return raw
    # A clean working tree: reduce to one line
    for line in lines:
        if "nothing to commit" in line.lower() or "working tree clean" in line.lower():
            return "working tree clean"
    # Keep only changed-file lines and conflict markers
    kept: list[str] = []
    for line in lines:
        stripped = line.lstrip()
        if (
            stripped.startswith("M ")
            or stripped.startswith("A ")
            or stripped.startswith("D ")
            or stripped.startswith("?? ")
            or stripped.startswith("UU ")
            or stripped.startswith("AA ")
            or "conflict" in line.lower()
            or stripped.startswith("renamed:")
            or stripped.startswith("modified:")
            or stripped.startswith("new file:")
            or stripped.startswith("deleted:")
        ):
            kept.append(line)
    return "\n".join(kept) if kept else raw




# --- context narrowing ----------------------------------------------------
#
# The bug this replaces, stated precisely, because it is the kind that looks
# like it works: `scope_file_listing` was handed `ContextRef.key` values and
# compared them against authorized repository paths. A key is
# `"<kind>:<ref>"` - `test:tests/test_company_efficiency.py` - and no key can
# ever prefix-match `tests/`, so the filter returned the empty tuple for every
# job. The briefing then reported `context_refs_scoped: []` beside a packet
# still carrying all seven refs, and the record read as a 100% reduction that
# had removed nothing.
#
# The fix is not a better string comparison. It is to ask each reference what
# repository path it actually stands for, which is a different question per
# kind and cannot be answered by looking at the key at all.


def reference_repository_path(ref: ContextRef) -> str | None:
    """The repository path this reference stands for, or None if it has none.

    Three answers, and the third is the one that matters:

    - a **file**, **test** or **benchmark** ref names a path directly;
    - a **module contract** produced by the capsule layer names `capsule:<id>`,
      which is an identifier and not a path - it is resolved through the
      capsule's own `owns_paths` by `narrow_context_refs`, never here;
    - a **fact**, **decision** or **experiment** names a knowledge record,
      which has no repository path at all and must not be scored as one.

    Returning None for the last two is the whole point. A function that
    guessed a path for them would re-create the original defect with a
    friendlier shape.
    """
    if ref.kind in (ContextKind.FILE, ContextKind.TEST, ContextKind.BENCHMARK):
        text = ref.ref.strip().replace("\\", "/").strip("/")
        return text or None
    return None


def reference_capsule_id(ref: ContextRef) -> str | None:
    """The capsule a module-contract reference names, or None."""
    if ref.kind is not ContextKind.MODULE_CONTRACT:
        return None
    text = ref.ref.strip()
    if text.startswith("capsule:"):
        return text[len("capsule:") :].strip() or None
    return None


def path_touches_scope(path: str, scope: Sequence[str]) -> bool:
    """Whether one repository path is inside, or contains, an authorized path.

    Both directions count. A ref naming `company/efficiency` is relevant to a
    scope of `company/efficiency/profile.py`, and a ref naming
    `company/efficiency/profile.py` is relevant to a scope of
    `company/efficiency`. Only the first direction would be "inside the
    scope"; dropping the second would discard the directory-level module
    contract that is usually the most useful reference in the packet.
    """
    if not scope:
        return True
    subject = path.strip().replace("\\", "/").strip("/")
    if not subject:
        return False
    for raw in scope:
        allowed = str(raw).strip().replace("\\", "/").strip("/")
        if not allowed:
            continue
        if subject == allowed:
            return True
        if subject.startswith(allowed + "/"):
            return True
        if allowed.startswith(subject + "/"):
            return True
    return False


@dataclass(frozen=True)
class ContextNarrowing:
    """What narrowing kept, what it dropped, and why - so it can be measured.

    `dropped_reasons` is parallel to `dropped` and exists because a reduction
    nobody can explain is indistinguishable from a filter that is silently
    eating the packet, which is exactly the failure this replaces.
    """

    kept: tuple[ContextRef, ...]
    dropped: tuple[ContextRef, ...]
    dropped_reasons: tuple[str, ...]

    @property
    def considered(self) -> int:
        return len(self.kept) + len(self.dropped)

    def summary(self) -> dict[str, object]:
        return {
            "considered": self.considered,
            "kept": [ref.key for ref in self.kept],
            "dropped": [ref.key for ref in self.dropped],
            "dropped_reasons": list(self.dropped_reasons),
            "kept_count": len(self.kept),
            "dropped_count": len(self.dropped),
        }


def narrow_context_refs(
    refs: Sequence[ContextRef],
    authorized_paths: Sequence[str],
    *,
    capsule_paths: Mapping[str, Sequence[str]] | None = None,
    floor: int = 1,
) -> ContextNarrowing:
    """Keep the references that bear on the authorized scope; drop the rest.

    - A **path-bearing** ref is kept when its path touches the scope.
    - A **capsule** ref is kept when any path the capsule owns touches the
      scope. A capsule the caller supplied no paths for is kept: the company
      cannot prove a reference irrelevant using a map it does not have, and
      dropping on absent evidence is how narrowing turns into blindness.
    - A **knowledge** ref - fact, decision, experiment - is kept. It has no
      path, so path scope says nothing about it, and it was already selected
      for relevance by the capsule layer.

    `floor` guarantees a minimum number of surviving refs, in declaration
    order. A packet narrowed to nothing is not an economy; it is a session
    that has to rediscover its own subject.

    An empty `authorized_paths` narrows nothing, because a scope that
    authorizes no path is not a scope to filter against.
    """
    if not authorized_paths:
        return ContextNarrowing(kept=tuple(refs), dropped=(), dropped_reasons=())

    owned = {
        str(capsule_id): tuple(str(path) for path in paths)
        for capsule_id, paths in (capsule_paths or {}).items()
    }

    kept: list[ContextRef] = []
    dropped: list[ContextRef] = []
    reasons: list[str] = []

    for ref in refs:
        path = reference_repository_path(ref)
        if path is not None:
            if path_touches_scope(path, authorized_paths):
                kept.append(ref)
            else:
                dropped.append(ref)
                reasons.append(f"{ref.key}: {path} is outside the authorized scope")
            continue

        capsule_id = reference_capsule_id(ref)
        if capsule_id is not None:
            paths = owned.get(capsule_id)
            if paths is None:
                kept.append(ref)
                continue
            if any(path_touches_scope(item, authorized_paths) for item in paths):
                kept.append(ref)
            else:
                dropped.append(ref)
                reasons.append(
                    f"{ref.key}: capsule {capsule_id} owns no path in the "
                    "authorized scope"
                )
            continue

        kept.append(ref)

    if len(kept) < floor and dropped:
        restored = {ref.key for ref in dropped[: floor - len(kept)]}
        kept_keys = {ref.key for ref in kept} | restored
        # Re-derived in declaration order, so restoring a ref cannot reorder
        # the manifest the session reads.
        kept = [ref for ref in refs if ref.key in kept_keys]
        surviving = [
            (ref, reason)
            for ref, reason in zip(dropped, reasons)
            if ref.key not in restored
        ]
        dropped = [ref for ref, _ in surviving]
        reasons = [reason for _, reason in surviving]

    return ContextNarrowing(
        kept=tuple(kept), dropped=tuple(dropped), dropped_reasons=tuple(reasons)
    )


def scope_file_listing(
    paths: Sequence[str], allowed_paths: Sequence[str],
) -> tuple[str, ...]:
    """Keep only repository paths that fall inside the authorized scope.

    **This takes paths, never `ContextRef.key` values.** Passing keys here is
    the defect described above: every key carries a `<kind>:` prefix, nothing
    matches, and the caller records a total reduction that removed nothing.
    Use `narrow_context_refs` for references.
    """
    if not allowed_paths:
        return tuple(paths)
    return tuple(p for p in paths if path_touches_scope(p, allowed_paths))


__all__ = [
    "CheckpointRule",
    "ContextNarrowing",
    "EscalationReason",
    "ExecutionStrategy",
    "ModelTier",
    "OutputReductionDirective",
    "ResourceCeiling",
    "narrow_context_refs",
    "path_touches_scope",
    "reference_capsule_id",
    "reference_repository_path",
    "reduce_git_output",
    "reduce_log_output",
    "reduce_test_output",
    "scope_file_listing",
    "select_strategy",
]
