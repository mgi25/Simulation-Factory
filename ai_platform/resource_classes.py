"""Six task classes, described by required capability and never by vendor.

`ai_platform/README.md` states a decision order: deterministic software, then
canonical knowledge, then a bounded low-reasoning pass, then a specialist, then
deep reasoning, and only for rare major decisions several independent reviewers.
This module is that order made executable, and nothing more.

## Why no model names

A class here says what a task *needs* - whether judgment is involved, how deep
it goes, how much context it may carry, how many passes it gets, whether it
must cite evidence. It never says who supplies that. The reason is the one in
constitution rule 13: no sacred technology. A router that hard-codes a model
name has to be rewritten when the model is replaced; a router that says
"specialist reasoning, medium context, evidence required" does not. Provider
selection is a separate, later, replaceable mapping - and deliberately not
part of this module.

## Why the order inverts after step 2

Steps 1 and 2 are absolute: if deterministic code can do it, reasoning is
waste, and if the answer is already canonical, rediscovering it is waste. That
is constitution rule 4, minimum sufficient intelligence, and nothing overrides
it.

Below that, the README's numbering is a checklist of increasing capability, not
an evaluation order. Asking "can a bounded low-reasoning pass do it?" first
would answer yes for a high-risk irreversible change, which is exactly the case
that needs a specialist. So once A and B have been ruled out, the predicates
are tested from the top down - F, then E, then D - and C is the floor that
catches everything else. Encoding it the other way would make the cheap class
the default for the dangerous task.

## Determinism

`classify` is a pure function of a frozen `TaskSignals`, evaluated against an
ordered tuple of rules where the first match wins. No dictionary iteration, no
clock, no randomness, no I/O. The same signals produce the same class and the
same rule name, in this session and in the next one - which is what makes a
routing decision auditable after the fact from its usage record.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ReasoningClass(Enum):
    """The six classes, in ascending cost order."""

    A = "A"  # deterministic / no reasoning
    B = "B"  # retrieval
    C = "C"  # small reasoning
    D = "D"  # specialist reasoning
    E = "E"  # deep reasoning
    F = "F"  # rare multi-perspective review


CLASS_ORDER: tuple[ReasoningClass, ...] = (
    ReasoningClass.A,
    ReasoningClass.B,
    ReasoningClass.C,
    ReasoningClass.D,
    ReasoningClass.E,
    ReasoningClass.F,
)


class ContextBudget(Enum):
    """How much supporting material a class may carry, in words not numbers."""

    NONE = "none"
    MINIMAL = "minimal"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class Risk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ResourceClass:
    """A capability requirement. Deliberately says nothing about who meets it."""

    code: ReasoningClass
    name: str
    intent: str
    requires_reasoning: bool
    reasoning_depth: int  # 0 none, 1 shallow, 2 specialist, 3 deep, 4 deep x N
    context_budget: ContextBudget
    max_context_refs: int  # the measurable form of "minimum relevant context"
    max_passes: int
    independent_reviewers: int
    reviewers_sequential: bool
    requires_evidence: bool
    escalates_to: ReasoningClass | None
    allows_subagents: bool = False  # constitution rule 2; never True

    @property
    def rank(self) -> int:
        return CLASS_ORDER.index(self.code)


# The table. Frozen values, declared once, read everywhere.
RESOURCE_CLASSES: dict[ReasoningClass, ResourceClass] = {
    ReasoningClass.A: ResourceClass(
        code=ReasoningClass.A,
        name="deterministic",
        intent="Executable code, a lookup table, or a schema check answers it exactly.",
        requires_reasoning=False,
        reasoning_depth=0,
        context_budget=ContextBudget.NONE,
        max_context_refs=6,
        max_passes=1,
        independent_reviewers=1,
        reviewers_sequential=True,
        requires_evidence=False,
        escalates_to=ReasoningClass.B,
    ),
    ReasoningClass.B: ResourceClass(
        code=ReasoningClass.B,
        name="retrieval",
        intent="The answer is already canonical; fetch and cite it rather than rederive it.",
        requires_reasoning=False,
        reasoning_depth=0,
        context_budget=ContextBudget.MINIMAL,
        max_context_refs=8,
        max_passes=1,
        independent_reviewers=1,
        reviewers_sequential=True,
        requires_evidence=True,
        escalates_to=ReasoningClass.C,
    ),
    ReasoningClass.C: ResourceClass(
        code=ReasoningClass.C,
        name="small_reasoning",
        intent="A bounded single pass over a known contract and a small diff.",
        requires_reasoning=True,
        reasoning_depth=1,
        context_budget=ContextBudget.SMALL,
        max_context_refs=12,
        max_passes=1,
        independent_reviewers=1,
        reviewers_sequential=True,
        requires_evidence=False,
        escalates_to=ReasoningClass.D,
    ),
    ReasoningClass.D: ResourceClass(
        code=ReasoningClass.D,
        name="specialist_reasoning",
        intent="Domain judgment - physics, cinematography, analytics - inside one module.",
        requires_reasoning=True,
        reasoning_depth=2,
        context_budget=ContextBudget.MEDIUM,
        max_context_refs=20,
        max_passes=2,
        independent_reviewers=1,
        reviewers_sequential=True,
        requires_evidence=True,
        escalates_to=ReasoningClass.E,
    ),
    ReasoningClass.E: ResourceClass(
        code=ReasoningClass.E,
        name="deep_reasoning",
        intent="High-risk, novel, or hard-to-reverse work where a wrong answer is expensive.",
        requires_reasoning=True,
        reasoning_depth=3,
        context_budget=ContextBudget.LARGE,
        max_context_refs=32,
        max_passes=2,
        independent_reviewers=1,
        reviewers_sequential=True,
        requires_evidence=True,
        escalates_to=ReasoningClass.F,
    ),
    ReasoningClass.F: ResourceClass(
        code=ReasoningClass.F,
        name="multi_perspective_review",
        intent=(
            "Rare major decisions: several independent reviewers, invoked one after "
            "another as separate sessions passing compact handoffs - never in parallel, "
            "never as spawned children."
        ),
        requires_reasoning=True,
        reasoning_depth=4,
        context_budget=ContextBudget.LARGE,
        max_context_refs=32,
        max_passes=1,  # per reviewer
        independent_reviewers=3,
        reviewers_sequential=True,
        requires_evidence=True,
        escalates_to=None,
    ),
}


def resource_class(code: ReasoningClass) -> ResourceClass:
    return RESOURCE_CLASSES[code]


def escalate(code: ReasoningClass) -> ReasoningClass:
    """One step up the ladder. F is the top and stays there."""
    return RESOURCE_CLASSES[code].escalates_to or code


@dataclass(frozen=True)
class TaskSignals:
    """What a router is allowed to know. Facts about the task, not guesses.

    Every field is supplied by the caller and every default is the cheap
    answer, so an unfilled signal set classifies as C rather than as E. A
    router that has to guess should be given better signals, not a bigger
    budget.
    """

    deterministic_solution_exists: bool = False
    answer_in_canonical_knowledge: bool = False
    requires_judgment: bool = False
    specialist_domain: str = ""
    risk: Risk = Risk.LOW
    reversible: bool = True
    novel: bool = False
    ceo_reserved: bool = False
    multi_perspective_requested: bool = False


@dataclass(frozen=True)
class Classification:
    """The routing decision, and the named rule that produced it."""

    resource_class: ResourceClass
    rule: str
    signals: TaskSignals

    @property
    def code(self) -> ReasoningClass:
        return self.resource_class.code


Rule = tuple[str, Callable[[TaskSignals], bool], ReasoningClass]

# Ordered. First match wins. A tuple, not a mapping, because the order *is* the
# policy and a mapping would let a later edit reorder it invisibly.
RULES: tuple[Rule, ...] = (
    (
        "deterministic_software",
        lambda s: s.deterministic_solution_exists,
        ReasoningClass.A,
    ),
    (
        "canonical_knowledge_hit",
        lambda s: s.answer_in_canonical_knowledge,
        ReasoningClass.B,
    ),
    (
        "multi_perspective_review",
        lambda s: s.multi_perspective_requested or (s.ceo_reserved and not s.reversible),
        ReasoningClass.F,
    ),
    (
        "deep_reasoning",
        lambda s: (
            s.risk is Risk.CRITICAL
            or (s.risk is Risk.HIGH and s.novel)
            or (not s.reversible and s.requires_judgment)
        ),
        ReasoningClass.E,
    ),
    (
        "specialist_reasoning",
        lambda s: bool(s.specialist_domain.strip()) or s.risk is Risk.HIGH,
        ReasoningClass.D,
    ),
    ("small_reasoning_floor", lambda s: True, ReasoningClass.C),
)


def classify(signals: TaskSignals) -> Classification:
    """Route a task to a class. Pure, total, and the same answer every time."""
    for rule_name, predicate, code in RULES:
        if predicate(signals):
            return Classification(RESOURCE_CLASSES[code], rule_name, signals)
    raise AssertionError("RULES must end in a total rule")  # pragma: no cover
