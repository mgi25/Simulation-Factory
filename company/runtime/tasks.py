"""Typed task assignments and compact handoff artifact validation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from ai_platform.references import assert_reference
from company.validation.errors import ValidationError
from company.validation.no_subagents import collect_no_subagent_violations


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETE = "complete"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

    @classmethod
    def parse(cls, value: Any, *, path: str, issues: list[str]) -> "TaskStatus":
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError:
                pass
        issues.append(
            f"{path} must be one of: " + ", ".join(status.value for status in cls)
        )
        return cls.PENDING


@dataclass(frozen=True)
class TaskAssignment:
    task_id: str
    owner: str
    objective: str
    status: TaskStatus
    required_capabilities: tuple[str, ...]
    execution: Mapping[str, Any]

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        known_employee_ids: set[str] | None = None,
    ) -> "TaskAssignment":
        issues: list[str] = []
        task_id = _required_string(data, "task_id", "task", issues)
        owner = _required_string(data, "owner", "task", issues)
        objective = _required_string(data, "objective", "task", issues)
        status = TaskStatus.parse(data.get("status"), path="task.status", issues=issues)
        capabilities = _string_list(
            data.get("required_capabilities"), "task.required_capabilities", issues
        )
        execution = data.get("execution", {})
        if not isinstance(execution, Mapping):
            issues.append("task.execution must be a mapping")
            execution = {}
        if known_employee_ids is not None and owner and owner not in known_employee_ids:
            issues.append(f"task.owner references unknown employee {owner!r}")
        if "no_subagents" in data:
            issues.extend(
                collect_no_subagent_violations(
                    {"no_subagents": data["no_subagents"]}, path="task"
                )
            )
        issues.extend(collect_no_subagent_violations(execution, path="task.execution"))
        if issues:
            raise ValidationError(issues)
        return cls(
            task_id=task_id,
            owner=owner,
            objective=objective,
            status=status,
            required_capabilities=tuple(
                sorted({capability.casefold() for capability in capabilities})
            ),
            execution=dict(execution),
        )


@dataclass(frozen=True)
class UsageRecordPointer:
    """Compact handoff link to the one canonical detailed usage record."""

    record_ref: str
    fingerprint: str

    def __post_init__(self) -> None:
        assert_reference(self.record_ref, "resource_usage.record_ref")
        if not re.fullmatch(r"[0-9a-f]{16}", self.fingerprint):
            raise ValueError(
                "resource_usage.fingerprint must be a 16-character lowercase hex digest"
            )

    def to_dict(self) -> dict[str, str]:
        return {
            "record_ref": self.record_ref,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], issues: list[str]
    ) -> "UsageRecordPointer | None":
        record_ref = _required_string(data, "record_ref", "handoff.resource_usage", issues)
        fingerprint = _required_string(
            data, "fingerprint", "handoff.resource_usage", issues
        )
        unknown = sorted(set(data) - {"record_ref", "fingerprint"})
        if unknown:
            issues.append(
                "handoff.resource_usage has unknown field(s): " + ", ".join(unknown)
            )
        if not record_ref or not fingerprint:
            return None
        try:
            return cls(record_ref=record_ref, fingerprint=fingerprint)
        except ValueError as exc:
            issues.append(str(exc))
            return None


@dataclass(frozen=True)
class HandoffArtifact:
    task_id: str
    owner: str
    objective: str
    status: TaskStatus
    result: str
    evidence: tuple[str, ...]
    artifacts: tuple[str, ...]
    changed: tuple[str, ...]
    unchanged: tuple[str, ...]
    tests: tuple[str, ...]
    risks: tuple[str, ...]
    resource_usage: UsageRecordPointer
    next_owner: str
    escalation_required: bool
    escalation_reason: str

    @classmethod
    def from_mapping(
        cls,
        data: Mapping[str, Any],
        schema: Mapping[str, Any],
        *,
        known_employee_ids: set[str] | None = None,
    ) -> "HandoffArtifact":
        issues: list[str] = []
        required = schema.get("required_fields")
        if not isinstance(required, list) or any(not isinstance(item, str) for item in required):
            issues.append("task_handoff.schema.required_fields must be a list of strings")
            required = []
        for field in required:
            if field not in data:
                issues.append(f"handoff.{field} is required")

        task_id = _required_string(data, "task_id", "handoff", issues)
        owner = _required_string(data, "owner", "handoff", issues)
        objective = _required_string(data, "objective", "handoff", issues)
        result = _string(data.get("result"), "handoff.result", issues)
        status = TaskStatus.parse(data.get("status"), path="handoff.status", issues=issues)
        final_statuses = {TaskStatus.COMPLETE, TaskStatus.COMPLETED}
        if status in final_statuses and not result.strip():
            issues.append("handoff.result must be non-empty for a completed handoff")

        list_values = {
            field: _string_list(data.get(field, []), f"handoff.{field}", issues)
            for field in ("evidence", "artifacts", "changed", "unchanged", "tests", "risks")
        }
        next_owner = _string(data.get("next_owner"), "handoff.next_owner", issues)
        if known_employee_ids is not None:
            allowed = known_employee_ids | {"ceo"}
            if owner and owner not in allowed:
                issues.append(f"handoff.owner references unknown employee {owner!r}")
            if next_owner and next_owner not in allowed:
                issues.append(f"handoff.next_owner references unknown employee {next_owner!r}")

        resource_usage = data.get("resource_usage")
        if not isinstance(resource_usage, Mapping):
            issues.append("handoff.resource_usage must be a mapping")
            resource_usage = {}
        usage_pointer = UsageRecordPointer.from_mapping(resource_usage, issues)

        escalation = data.get("escalation")
        if not isinstance(escalation, Mapping):
            issues.append("handoff.escalation must be a mapping")
            escalation = {}
        escalation_required = escalation.get("required")
        if not isinstance(escalation_required, bool):
            issues.append("handoff.escalation.required must be a boolean")
            escalation_required = False
        escalation_reason = _string(
            escalation.get("reason"), "handoff.escalation.reason", issues
        )
        if escalation_required and not escalation_reason.strip():
            issues.append("handoff.escalation.reason is required when escalation is required")

        execution = data.get("execution")
        if execution is not None:
            if not isinstance(execution, Mapping):
                issues.append("handoff.execution must be a mapping when provided")
            else:
                issues.extend(
                    collect_no_subagent_violations(execution, path="handoff.execution")
                )
        if issues:
            raise ValidationError(issues)
        assert usage_pointer is not None
        return cls(
            task_id=task_id,
            owner=owner,
            objective=objective,
            status=status,
            result=result,
            evidence=tuple(list_values["evidence"]),
            artifacts=tuple(list_values["artifacts"]),
            changed=tuple(list_values["changed"]),
            unchanged=tuple(list_values["unchanged"]),
            tests=tuple(list_values["tests"]),
            risks=tuple(list_values["risks"]),
            resource_usage=usage_pointer,
            next_owner=next_owner,
            escalation_required=escalation_required,
            escalation_reason=escalation_reason,
        )


def _required_string(
    data: Mapping[str, Any], field: str, path: str, issues: list[str]
) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{path}.{field} must be a non-empty string")
        return ""
    return value.strip()


def _string(value: Any, path: str, issues: list[str]) -> str:
    if not isinstance(value, str):
        issues.append(f"{path} must be a string")
        return ""
    return value


def _string_list(value: Any, path: str, issues: list[str]) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        issues.append(f"{path} must be a list of non-empty strings")
        return []
    return value
