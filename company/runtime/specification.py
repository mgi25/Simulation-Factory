"""Typed, provider-independent task and context requirements."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.references import assert_reference, assert_text
from ai_platform.resource_classes import ReasoningClass, Risk, TaskSignals

from .errors import LifecycleError


@dataclass(frozen=True)
class ContextRequirements:
    """References and criteria from which a manifest can be constructed."""

    refs: tuple[ContextRef, ...] = ()
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("refs", "constraints", "acceptance_criteria"):
            if not isinstance(getattr(self, name), tuple):
                raise LifecycleError(f"context.{name} must be a tuple")
        if any(not isinstance(ref, ContextRef) for ref in self.refs):
            raise LifecycleError("context.refs must contain ContextRef values")
        for name in ("constraints", "acceptance_criteria"):
            values = getattr(self, name)
            if any(not isinstance(item, str) or not item.strip() for item in values):
                raise LifecycleError(
                    f"context.{name} must contain only non-empty strings"
                )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ContextRequirements:
        unknown = sorted(set(data) - {"refs", "constraints", "acceptance_criteria"})
        if unknown:
            raise LifecycleError("unknown context field(s): " + ", ".join(unknown))
        raw_refs = data.get("refs", [])
        if not isinstance(raw_refs, list):
            raise LifecycleError("context.refs must be a list")
        refs = tuple(_context_ref(item, index) for index, item in enumerate(raw_refs))
        return cls(
            refs=refs,
            constraints=_string_tuple(data.get("constraints", []), "context.constraints"),
            acceptance_criteria=_string_tuple(
                data.get("acceptance_criteria", []), "context.acceptance_criteria"
            ),
        )


@dataclass(frozen=True)
class TaskSpecification:
    """The facts a deterministic planner is allowed to use."""

    task_id: str
    objective: str
    required_capabilities: tuple[str, ...]
    risk: Risk = Risk.LOW
    reversible: bool = True
    deterministic_execution_possible: bool = False
    canonical_knowledge_may_answer: bool = False
    evidence_required: bool = False
    context: ContextRequirements = field(default_factory=ContextRequirements)
    reasoning_class_ceiling: ReasoningClass = ReasoningClass.F
    requires_judgment: bool = False
    specialist_domain: str = ""
    novel: bool = False
    ceo_reserved: bool = False
    multi_perspective_requested: bool = False
    execution: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "task_id")
        assert_text(self.objective, "objective")
        capabilities = tuple(
            sorted(
                {
                    item.strip().casefold()
                    for item in self.required_capabilities
                    if isinstance(item, str) and item.strip()
                }
            )
        )
        if len(capabilities) != len(self.required_capabilities) or not capabilities:
            raise LifecycleError(
                "required_capabilities must be a non-empty collection of unique strings"
            )
        object.__setattr__(self, "required_capabilities", capabilities)
        if not isinstance(self.risk, Risk):
            raise LifecycleError("risk must be a Risk value")
        if not isinstance(self.reasoning_class_ceiling, ReasoningClass):
            raise LifecycleError("reasoning_class_ceiling must be a ReasoningClass value")
        if not isinstance(self.context, ContextRequirements):
            raise LifecycleError("context must be a ContextRequirements value")
        for field_name in (
            "reversible",
            "deterministic_execution_possible",
            "canonical_knowledge_may_answer",
            "evidence_required",
            "requires_judgment",
            "novel",
            "ceo_reserved",
            "multi_perspective_requested",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise LifecycleError(f"{field_name} must be a boolean")
        if not isinstance(self.specialist_domain, str):
            raise LifecycleError("specialist_domain must be a string")
        if not isinstance(self.execution, Mapping):
            raise LifecycleError("execution must be a mapping")
        object.__setattr__(self, "execution", dict(self.execution))

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> TaskSpecification:
        known = {
            "task_id",
            "objective",
            "required_capabilities",
            "risk",
            "reversible",
            "deterministic_execution_possible",
            "canonical_knowledge_may_answer",
            "evidence_required",
            "context",
            "reasoning_class_ceiling",
            "requires_judgment",
            "specialist_domain",
            "novel",
            "ceo_reserved",
            "multi_perspective_requested",
            "execution",
        }
        unknown = sorted(set(data) - known)
        if unknown:
            raise LifecycleError("unknown task field(s): " + ", ".join(unknown))
        context = data.get("context", {})
        if not isinstance(context, Mapping):
            raise LifecycleError("context must be a mapping")
        execution = data.get("execution", {})
        if not isinstance(execution, Mapping):
            raise LifecycleError("execution must be a mapping")
        return cls(
            task_id=_required_string(data, "task_id", "task"),
            objective=_required_string(data, "objective", "task"),
            required_capabilities=_string_tuple(
                data.get("required_capabilities"), "task.required_capabilities"
            ),
            risk=_enum(Risk, data.get("risk", Risk.LOW.value), "task.risk"),
            reversible=_boolean(data, "reversible", True),
            deterministic_execution_possible=_boolean(
                data, "deterministic_execution_possible", False
            ),
            canonical_knowledge_may_answer=_boolean(
                data, "canonical_knowledge_may_answer", False
            ),
            evidence_required=_boolean(data, "evidence_required", False),
            context=ContextRequirements.from_mapping(context),
            reasoning_class_ceiling=_enum(
                ReasoningClass,
                data.get("reasoning_class_ceiling", ReasoningClass.F.value),
                "task.reasoning_class_ceiling",
            ),
            requires_judgment=_boolean(data, "requires_judgment", False),
            specialist_domain=_optional_string(data, "specialist_domain", "task"),
            novel=_boolean(data, "novel", False),
            ceo_reserved=_boolean(data, "ceo_reserved", False),
            multi_perspective_requested=_boolean(
                data, "multi_perspective_requested", False
            ),
            execution=dict(execution),
        )

    def signals(self) -> TaskSignals:
        return TaskSignals(
            deterministic_solution_exists=self.deterministic_execution_possible,
            answer_in_canonical_knowledge=self.canonical_knowledge_may_answer,
            requires_judgment=self.requires_judgment,
            specialist_domain=self.specialist_domain,
            risk=self.risk,
            reversible=self.reversible,
            novel=self.novel,
            ceo_reserved=self.ceo_reserved,
            multi_perspective_requested=self.multi_perspective_requested,
        )


def _context_ref(value: Any, index: int) -> ContextRef:
    path = f"context.refs[{index}]"
    if not isinstance(value, Mapping):
        raise LifecycleError(f"{path} must be a mapping")
    unknown = sorted(set(value) - {"kind", "ref", "reason", "span", "digest"})
    if unknown:
        raise LifecycleError(f"{path} has unknown field(s): " + ", ".join(unknown))
    span = value.get("span")
    if span is not None:
        if (
            not isinstance(span, list)
            or len(span) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in span)
        ):
            raise LifecycleError(f"{path}.span must be [start, end]")
        parsed_span: tuple[int, int] | None = (span[0], span[1])
    else:
        parsed_span = None
    return ContextRef(
        kind=_enum(ContextKind, value.get("kind"), f"{path}.kind"),
        ref=_required_string(value, "ref", path),
        reason=_required_string(value, "reason", path),
        span=parsed_span,
        digest=_optional_string(value, "digest", path),
    )


def _required_string(data: Mapping[str, Any], field_name: str, path: str) -> str:
    value = data.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"{path}.{field_name} must be a non-empty string")
    return value.strip()


def _optional_string(data: Mapping[str, Any], field_name: str, path: str) -> str:
    value = data.get(field_name, "")
    if not isinstance(value, str):
        raise LifecycleError(f"{path}.{field_name} must be a string")
    return value


def _string_tuple(value: Any, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise LifecycleError(f"{path} must be a list of non-empty strings")
    return tuple(item.strip() for item in value)


def _boolean(data: Mapping[str, Any], field_name: str, default: bool) -> bool:
    value = data.get(field_name, default)
    if not isinstance(value, bool):
        raise LifecycleError(f"task.{field_name} must be a boolean")
    return value


def _enum(enum_type: type[Enum], value: Any, path: str) -> Any:
    if not isinstance(value, str):
        raise LifecycleError(f"{path} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in enum_type)
        raise LifecycleError(f"{path} must be one of: {allowed}") from exc
