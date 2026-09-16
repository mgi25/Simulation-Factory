"""The compact packet a prepared task hands to an independent top-level session.

Everything before this module is internal: a specification is classified, an
employee is selected, and context is bounded. A `SessionPacket` is where that
work leaves the process. It is a *transport* boundary, and a transport boundary
is not an authorisation one. Nothing a packet carries may exceed what the
employee contract, `company/permissions.yaml` and the task specification
already allow, which is why building one re-reads the contract instead of
trusting the plan that produced it.

## Reference-only, for the same reason a manifest is

Every pointer in a packet passes `ai_platform.references.assert_reference` by
construction: the context refs are `ContextRef` values, and the paths, tests
and branch have guards of their own. A packet therefore stays in the low
thousands of characters while the material it points at runs to hundreds of
thousands. `size_chars()` reports the former, so the ratio can be watched
rather than assumed.

## Why the executor hint is outside the fingerprint

A packet may name the tool expected to run it - `claude_code`, `codex`, a
human. That name is metadata: no behaviour in this package reads it, and
`fingerprint()` is computed over the packet *without* it. The same work
prepared for two tools therefore has one identity, and a receipt from either
answers the same packet. Were the hint inside the fingerprint, changing who
runs a task would silently make it a different task.

## The completion protocol

A packet always carries `COMPLETION_PROTOCOL`, so a session holding only the
packet still knows the terms: implement, test, commit, push the assigned
branch, verify the exact remote SHA, never merge, return a compact handoff. A
packet may add steps. It may not drop one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.policy import SubagentPolicyViolation
from ai_platform.references import assert_reference, assert_text
from ai_platform.resource_classes import ReasoningClass
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .errors import LifecycleError
from .git_evidence import assert_branch_name, assert_git_sha
from .path_scope import PathScope, normalise_path


PACKET_VERSION = 1

COMPLETION_PROTOCOL: tuple[str, ...] = (
    "implement the objective, changing only allowed paths",
    "run every required test and report the result",
    "commit the work",
    "push the assigned branch",
    "verify the exact remote SHA matches the local commit",
    "do not merge",
    "return a compact handoff receipt",
)

_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


class ExecutorHint(str, Enum):
    """Who is expected to run the packet. Metadata, and nothing else.

    No code branches on this value. It exists so a history can answer "what ran
    this?" without the runtime acquiring a vendor-shaped code path.
    """

    UNSPECIFIED = "unspecified"
    CLAUDE_CODE = "claude_code"
    CODEX = "codex"
    HUMAN = "human"
    FUTURE_ADAPTER = "future_adapter"


@dataclass(frozen=True)
class SessionPacket:
    """What an external session is given, as pointers and terms - never bodies."""

    task_id: str
    objective: str
    employee: str
    reasoning_class: ReasoningClass
    resource_class: str
    context_refs: tuple[ContextRef, ...]
    explicit_context_refs: tuple[str, ...]
    automatic_context_refs: tuple[str, ...]
    context_fingerprint: str
    context_cache_key: str
    constraints: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    path_scope: PathScope
    expected_branch: str
    expected_base_commit: str = ""
    required_tests: tuple[str, ...] = ()
    evidence_required: bool = False
    completion_protocol: tuple[str, ...] = COMPLETION_PROTOCOL
    no_subagents: bool = True
    executor: ExecutorHint = ExecutorHint.UNSPECIFIED
    version: int = PACKET_VERSION

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "packet.task_id")
        assert_text(self.objective, "packet.objective")
        assert_reference(self.employee, "packet.employee")
        if not isinstance(self.reasoning_class, ReasoningClass):
            raise LifecycleError("packet.reasoning_class must be a ReasoningClass value")
        if not isinstance(self.resource_class, str) or not self.resource_class.strip():
            raise LifecycleError("packet.resource_class must be a non-empty string")
        if not isinstance(self.context_refs, tuple) or any(
            not isinstance(ref, ContextRef) for ref in self.context_refs
        ):
            raise LifecycleError("packet.context_refs must be ContextRef values")

        keys = tuple(ref.key for ref in self.context_refs)
        if len(set(keys)) != len(keys):
            raise LifecycleError("packet.context_refs must not repeat a reference")
        for name in ("explicit_context_refs", "automatic_context_refs"):
            _assert_reference_tuple(getattr(self, name), f"packet.{name}")
        explicit = set(self.explicit_context_refs)
        automatic = set(self.automatic_context_refs)
        if explicit & automatic:
            raise LifecycleError(
                "packet context cannot be both explicit and automatic: "
                + ", ".join(sorted(explicit & automatic))
            )
        unknown = (explicit | automatic) - set(keys)
        if unknown:
            raise LifecycleError(
                "packet explicit/automatic context names a reference the packet does "
                "not carry: " + ", ".join(sorted(unknown))
            )

        for name in ("context_fingerprint", "context_cache_key"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _FINGERPRINT.fullmatch(value):
                raise LifecycleError(
                    f"packet.{name} must be a 16-character lowercase hex digest"
                )

        _assert_text_tuple(self.constraints, "packet.constraints")
        _assert_text_tuple(self.acceptance_criteria, "packet.acceptance_criteria")
        if not self.acceptance_criteria:
            raise LifecycleError(
                "packet.acceptance_criteria is required: a session cannot be held to "
                "criteria it was never given"
            )
        if not isinstance(self.path_scope, PathScope):
            raise LifecycleError("packet.path_scope must be a PathScope value")

        assert_branch_name(self.expected_branch, "packet.expected_branch")
        if self.expected_base_commit:
            assert_git_sha(self.expected_base_commit, "packet.expected_base_commit")
        _assert_reference_tuple(self.required_tests, "packet.required_tests")

        if not isinstance(self.evidence_required, bool):
            raise LifecycleError("packet.evidence_required must be a boolean")
        _assert_text_tuple(self.completion_protocol, "packet.completion_protocol")
        missing = tuple(
            step for step in COMPLETION_PROTOCOL if step not in self.completion_protocol
        )
        if missing:
            raise LifecycleError(
                "packet.completion_protocol is missing standard step(s): "
                + "; ".join(missing)
            )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "packet.no_subagents must be true; constitution rule 2 is amended by "
                "the CEO, not by a field in a packet"
            )
        if not isinstance(self.executor, ExecutorHint):
            raise LifecycleError("packet.executor must be an ExecutorHint value")
        if self.version != PACKET_VERSION:
            raise LifecycleError(
                f"packet.version must be {PACKET_VERSION}, got {self.version!r}"
            )

    def context_keys(self) -> tuple[str, ...]:
        return tuple(ref.key for ref in self.context_refs)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def identity(self) -> dict[str, Any]:
        """The packet minus the executor hint: the identity of the work itself."""
        return {key: value for key, value in self.to_dict().items() if key != "executor"}

    def fingerprint(self) -> str:
        return _fingerprint(self.identity())

    def size_chars(self) -> int:
        """What the packet itself costs - not what it points at."""
        total = len(self.task_id) + len(self.objective) + len(self.employee)
        total += sum(len(text) for text in self.constraints)
        total += sum(len(text) for text in self.acceptance_criteria)
        total += sum(len(text) for text in self.completion_protocol)
        total += sum(len(text) for text in self.required_tests)
        total += sum(len(text) for text in self.path_scope.allowed)
        total += sum(len(text) for text in self.path_scope.forbidden)
        for ref in self.context_refs:
            total += len(ref.key) + len(ref.reason) + len(ref.digest)
        return total

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "SessionPacket":
        """Decode a persisted packet, refusing any field the schema does not name."""
        if not isinstance(data, Mapping):
            raise LifecycleError("packet must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise LifecycleError("unknown packet field(s): " + ", ".join(unknown))
        scope = data.get("path_scope", {})
        if not isinstance(scope, Mapping):
            raise LifecycleError("packet.path_scope must be a mapping")
        return cls(
            task_id=_string(data, "task_id"),
            objective=_string(data, "objective"),
            employee=_string(data, "employee"),
            reasoning_class=_enum(
                ReasoningClass, data.get("reasoning_class"), "reasoning_class"
            ),
            resource_class=_string(data, "resource_class"),
            context_refs=tuple(
                _context_ref(item, index)
                for index, item in enumerate(
                    _sequence(data.get("context_refs"), "context_refs")
                )
            ),
            explicit_context_refs=_string_tuple(
                data.get("explicit_context_refs"), "explicit_context_refs"
            ),
            automatic_context_refs=_string_tuple(
                data.get("automatic_context_refs"), "automatic_context_refs"
            ),
            context_fingerprint=_string(data, "context_fingerprint"),
            context_cache_key=_string(data, "context_cache_key"),
            constraints=_string_tuple(data.get("constraints"), "constraints"),
            acceptance_criteria=_string_tuple(
                data.get("acceptance_criteria"), "acceptance_criteria"
            ),
            path_scope=PathScope(
                allowed=_string_tuple(scope.get("allowed"), "path_scope.allowed"),
                forbidden=_string_tuple(scope.get("forbidden"), "path_scope.forbidden"),
            ),
            expected_branch=_string(data, "expected_branch"),
            expected_base_commit=_optional_string(data, "expected_base_commit"),
            required_tests=_string_tuple(data.get("required_tests"), "required_tests"),
            evidence_required=_boolean(data, "evidence_required", False),
            completion_protocol=_string_tuple(
                data.get("completion_protocol", COMPLETION_PROTOCOL),
                "completion_protocol",
            ),
            no_subagents=_boolean(data, "no_subagents", True),
            executor=_enum(
                ExecutorHint,
                data.get("executor", ExecutorHint.UNSPECIFIED.value),
                "executor",
            ),
            version=_integer(data.get("version", PACKET_VERSION), "version"),
        )


def build_session_packet(
    plan: Any,
    *,
    expected_branch: str,
    path_scope: PathScope | None = None,
    required_tests: tuple[str, ...] = (),
    expected_base_commit: str = "",
    executor: ExecutorHint = ExecutorHint.UNSPECIFIED,
    employee_contract: Mapping[str, Any] | None = None,
) -> SessionPacket:
    """Turn one prepared `TaskPlan` into a packet without widening its authority.

    Three refusals live here rather than in the dataclass, because each needs
    the plan around it:

    - a plan that is not `execution_prepared` has no packet, an escalated one
      included;
    - a CEO-reserved task is never packaged for a worker, because
      `permissions.yaml` reserves the decision and a transport layer does not
      un-reserve it;
    - an allowed path outside the employee contract's `may_write`, or inside
      its `may_not_modify`, is refused: a packet cannot grant what the contract
      withholds.
    """
    from .lifecycle import contract_from_registry  # local import: avoids a cycle

    if not getattr(plan, "ready", False) or plan.preparation is None:
        state = getattr(getattr(plan, "state", None), "value", "unknown")
        raise LifecycleError(
            f"task {plan.specification.task_id} is {state}, not execution_prepared; "
            "only a prepared task can be packaged"
        )
    if plan.specification.ceo_reserved:
        raise LifecycleError(
            f"task {plan.specification.task_id} is CEO-reserved and is escalated, not "
            "packaged; permissions.yaml reserves the decision to the CEO"
        )
    manifest = plan.context_manifest
    context_plan = plan.context_plan
    if manifest is None or context_plan is None:
        raise LifecycleError(
            f"task {plan.specification.task_id}: a packet requires an assembled context"
        )

    scope = path_scope if path_scope is not None else PathScope()
    contract = (
        employee_contract
        if employee_contract is not None
        else contract_from_registry(plan.selected_employee, plan.config)
    )
    _assert_scope_within_contract(scope, contract, plan.selected_employee)

    return SessionPacket(
        task_id=plan.specification.task_id,
        objective=plan.specification.objective,
        employee=plan.selected_employee,
        reasoning_class=plan.classification.code,
        resource_class=plan.classification.resource_class.name,
        context_refs=manifest.refs(),
        explicit_context_refs=context_plan.explicit_refs,
        automatic_context_refs=context_plan.capsule_refs_accepted,
        context_fingerprint=plan.preparation.context_fingerprint,
        context_cache_key=plan.preparation.context_cache_key,
        constraints=manifest.constraints,
        acceptance_criteria=manifest.acceptance_criteria,
        path_scope=scope,
        expected_branch=expected_branch,
        expected_base_commit=expected_base_commit,
        required_tests=tuple(required_tests),
        evidence_required=plan.preparation.evidence_required,
        no_subagents=plan.preparation.no_subagents,
        executor=executor,
    )


def _assert_scope_within_contract(
    scope: PathScope, contract: Mapping[str, Any], employee: str
) -> None:
    may_write = _contract_paths(contract, "may_write")
    may_not_modify = _contract_paths(contract, "may_not_modify")
    issues: list[str] = []
    for path in scope.allowed:
        blocked = [
            rule
            for rule in may_not_modify
            if path == rule or path.startswith(rule + "/") or rule.startswith(path + "/")
        ]
        if blocked:
            issues.append(
                f"{path} reaches {employee}'s may_not_modify ({', '.join(sorted(blocked))})"
            )
        if may_write and not any(
            path == rule or path.startswith(rule + "/") for rule in may_write
        ):
            issues.append(f"{path} is outside {employee}'s may_write")
    if issues:
        raise LifecycleError(
            "packet path scope exceeds the employee contract: " + "; ".join(sorted(issues))
        )


def _contract_paths(contract: Mapping[str, Any], field: str) -> tuple[str, ...]:
    values = contract.get(field, []) if isinstance(contract, Mapping) else []
    if not isinstance(values, (list, tuple)):
        raise LifecycleError(f"agent_contract.{field} must be a list of paths")
    return tuple(
        normalise_path(item, f"agent_contract.{field}")
        for item in values
        if isinstance(item, str) and item.strip()
    )


def _assert_reference_tuple(values: Any, field: str) -> None:
    if not isinstance(values, tuple):
        raise LifecycleError(f"{field} must be a tuple")
    for index, value in enumerate(values):
        assert_reference(value, f"{field}[{index}]")


def _assert_text_tuple(values: Any, field: str) -> None:
    if not isinstance(values, tuple) or any(
        not isinstance(value, str) or not value.strip() for value in values
    ):
        raise LifecycleError(f"{field} must be a tuple of non-empty strings")


def _string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"packet.{field} must be a non-empty string")
    return value


def _optional_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field, "")
    if not isinstance(value, str):
        raise LifecycleError(f"packet.{field} must be a string")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise LifecycleError(f"packet.{field} must be a list of strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise LifecycleError(f"packet.{field} must be a list of non-empty strings")
    return tuple(value)


def _sequence(value: Any, field: str) -> tuple[Any, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise LifecycleError(f"packet.{field} must be a list")
    return tuple(value)


def _boolean(data: Mapping[str, Any], field: str, default: bool) -> bool:
    value = data.get(field, default)
    if not isinstance(value, bool):
        raise LifecycleError(f"packet.{field} must be a boolean")
    return value


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LifecycleError(f"packet.{field} must be an integer")
    return value


def _enum(enum_type: type[Enum], value: Any, field: str) -> Any:
    if not isinstance(value, str):
        raise LifecycleError(f"packet.{field} must be a string")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(str(item.value) for item in enum_type)
        raise LifecycleError(f"packet.{field} must be one of: {allowed}") from exc


def _context_ref(value: Any, index: int) -> ContextRef:
    field = f"packet.context_refs[{index}]"
    if not isinstance(value, Mapping):
        raise LifecycleError(f"{field} must be a mapping")
    unknown = sorted(set(value) - {"kind", "ref", "reason", "span", "digest"})
    if unknown:
        raise LifecycleError(f"{field} has unknown field(s): " + ", ".join(unknown))
    span = value.get("span")
    if span is not None:
        if (
            not isinstance(span, (list, tuple))
            or len(span) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in span)
        ):
            raise LifecycleError(f"{field}.span must be [start, end]")
        span = (span[0], span[1])
    digest = value.get("digest", "")
    if not isinstance(digest, str):
        raise LifecycleError(f"{field}.digest must be a string")
    return ContextRef(
        kind=_enum(ContextKind, value.get("kind"), f"context_refs[{index}].kind"),
        ref=_string(value, "ref"),
        reason=_string(value, "reason"),
        span=span,
        digest=digest,
    )


__all__ = [
    "COMPLETION_PROTOCOL",
    "PACKET_VERSION",
    "ExecutorHint",
    "SessionPacket",
    "build_session_packet",
]
