"""Immutable execution authority captured when a session packet is prepared.

The snapshot contains only the authority that can affect this execution.  It is
not an employee prompt, a copy of the registry, or a credential container.  A
context-expansion decision can therefore reproduce the preparation boundary
without accepting a mutable contract from the external executor.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from ai_platform.policy import SubagentPolicyViolation
from ai_platform.references import assert_reference
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .errors import LifecycleError
from .path_scope import normalise_path


AUTHORITY_SNAPSHOT_VERSION = 1
_FINGERPRINT = re.compile(r"[0-9a-f]{16}")


class AuthoritySource(str, Enum):
    """Where the effective preparation-time authority came from."""

    CANONICAL_CONTRACT = "canonical_contract"
    TEMPORARY_TASK_OVERRIDE = "temporary_task_override"


@dataclass(frozen=True)
class ExecutionAuthoritySnapshot:
    """The exact, minimal authority evidence for one packet attempt."""

    task_id: str
    employee: str
    packet_fingerprint: str
    contract_fingerprint: str
    packet_attempt: int
    source: AuthoritySource
    may_read: tuple[str, ...] = ()
    may_write: tuple[str, ...] = ()
    may_not_read: tuple[str, ...] = ()
    may_not_modify: tuple[str, ...] = ()
    autonomy_level: int | None = None
    no_subagents: bool = True
    version: int = AUTHORITY_SNAPSHOT_VERSION

    def __post_init__(self) -> None:
        assert_reference(self.task_id, "execution_authority.task_id")
        assert_reference(self.employee, "execution_authority.employee")
        _assert_fingerprint(
            self.packet_fingerprint, "execution_authority.packet_fingerprint"
        )
        _assert_fingerprint(
            self.contract_fingerprint, "execution_authority.contract_fingerprint"
        )
        if (
            isinstance(self.packet_attempt, bool)
            or not isinstance(self.packet_attempt, int)
            or self.packet_attempt < 1
        ):
            raise LifecycleError(
                "execution_authority.packet_attempt must be a positive integer"
            )
        if not isinstance(self.source, AuthoritySource):
            raise LifecycleError(
                "execution_authority.source must be an AuthoritySource value"
            )
        for name in ("may_read", "may_write", "may_not_read", "may_not_modify"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise LifecycleError(f"execution_authority.{name} must be a tuple")
            object.__setattr__(self, name, _normalised_paths(values, name))
        if self.autonomy_level is not None and (
            isinstance(self.autonomy_level, bool)
            or not isinstance(self.autonomy_level, int)
            or self.autonomy_level < 0
        ):
            raise LifecycleError(
                "execution_authority.autonomy_level must be null or a non-negative integer"
            )
        if self.no_subagents is not True:
            raise SubagentPolicyViolation(
                "execution_authority.no_subagents must be true"
            )
        expected_contract_fingerprint = _fingerprint(
            {
                "employee": self.employee,
                "may_read": self.may_read,
                "may_write": self.may_write,
                "may_not_read": self.may_not_read,
                "may_not_modify": self.may_not_modify,
                "autonomy_level": self.autonomy_level,
                "no_subagents": True,
            }
        )
        if self.contract_fingerprint != expected_contract_fingerprint:
            raise LifecycleError(
                "execution_authority.contract_fingerprint does not match its "
                "authority fields"
            )
        if self.version != AUTHORITY_SNAPSHOT_VERSION:
            raise LifecycleError(
                "execution_authority.version must be "
                f"{AUTHORITY_SNAPSHOT_VERSION}, got {self.version!r}"
            )

    @classmethod
    def from_contract(
        cls,
        *,
        task_id: str,
        employee: str,
        packet_fingerprint: str,
        packet_attempt: int,
        contract: Mapping[str, Any],
        source: AuthoritySource,
    ) -> "ExecutionAuthoritySnapshot":
        authority = authority_projection(contract, employee=employee)
        return cls(
            task_id=task_id,
            employee=employee,
            packet_fingerprint=packet_fingerprint,
            contract_fingerprint=_fingerprint(authority),
            packet_attempt=packet_attempt,
            source=source,
            may_read=authority["may_read"],
            may_write=authority["may_write"],
            may_not_read=authority["may_not_read"],
            may_not_modify=authority["may_not_modify"],
            autonomy_level=authority["autonomy_level"],
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def as_contract(self) -> dict[str, Any]:
        """Return only the fields the deterministic authority policies consume."""
        return {
            "employee_id": self.employee,
            "may_read": list(self.may_read),
            "may_write": list(self.may_write),
            "may_not_read": list(self.may_not_read),
            "may_not_modify": list(self.may_not_modify),
            "autonomy_level": self.autonomy_level,
            "no_subagents": True,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ExecutionAuthoritySnapshot":
        if not isinstance(data, Mapping):
            raise LifecycleError("execution authority snapshot must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise LifecycleError(
                "execution authority snapshot has unknown field(s): "
                + ", ".join(unknown)
            )
        source = data.get("source")
        if not isinstance(source, str):
            raise LifecycleError("execution_authority.source must be a string")
        try:
            parsed_source = AuthoritySource(source)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in AuthoritySource)
            raise LifecycleError(
                f"execution_authority.source must be one of: {allowed}"
            ) from exc
        autonomy = data.get("autonomy_level")
        return cls(
            task_id=_required_string(data, "task_id"),
            employee=_required_string(data, "employee"),
            packet_fingerprint=_required_string(data, "packet_fingerprint"),
            contract_fingerprint=_required_string(data, "contract_fingerprint"),
            packet_attempt=_integer(data.get("packet_attempt"), "packet_attempt"),
            source=parsed_source,
            may_read=_string_tuple(data.get("may_read"), "may_read"),
            may_write=_string_tuple(data.get("may_write"), "may_write"),
            may_not_read=_string_tuple(data.get("may_not_read"), "may_not_read"),
            may_not_modify=_string_tuple(data.get("may_not_modify"), "may_not_modify"),
            autonomy_level=(
                None if autonomy is None else _integer(autonomy, "autonomy_level")
            ),
            no_subagents=_boolean(data.get("no_subagents", True), "no_subagents"),
            version=_integer(
                data.get("version", AUTHORITY_SNAPSHOT_VERSION), "version"
            ),
        )


def authority_projection(
    contract: Mapping[str, Any], *, employee: str
) -> dict[str, Any]:
    """Extract and normalise authority without retaining unrelated contract text."""
    if not isinstance(contract, Mapping):
        raise LifecycleError("agent_contract must be a mapping")
    contract_employee = contract.get("employee_id")
    if contract_employee != employee:
        raise LifecycleError(
            f"employee contract {contract_employee!r} does not belong to {employee!r}"
        )
    autonomy = contract.get("autonomy_level")
    if autonomy is not None and (
        isinstance(autonomy, bool) or not isinstance(autonomy, int) or autonomy < 0
    ):
        raise LifecycleError(
            "agent_contract.autonomy_level must be a non-negative integer"
        )
    if contract.get("no_subagents") is not True:
        raise SubagentPolicyViolation("agent_contract.no_subagents must be true")
    return {
        "employee": employee,
        "may_read": _contract_paths(contract, "may_read"),
        "may_write": _contract_paths(contract, "may_write"),
        "may_not_read": _contract_paths(contract, "may_not_read"),
        "may_not_modify": _contract_paths(contract, "may_not_modify"),
        "autonomy_level": autonomy,
        "no_subagents": True,
    }


def _contract_paths(contract: Mapping[str, Any], field: str) -> tuple[str, ...]:
    values = contract.get(field, ())
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise LifecycleError(f"agent_contract.{field} must be a list of paths")
    return _normalised_paths(tuple(values), field)


def _normalised_paths(values: tuple[Any, ...], field: str) -> tuple[str, ...]:
    paths = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise LifecycleError(
                f"execution_authority.{field} must contain non-empty paths"
            )
        text = value.strip().replace("\\", "/")
        while text.endswith(("/**", "/*")):
            text = text.rsplit("/", 1)[0]
        paths.append(normalise_path(text, f"execution_authority.{field}"))
    return tuple(sorted(set(paths)))


def _assert_fingerprint(value: Any, field: str) -> None:
    if not isinstance(value, str) or not _FINGERPRINT.fullmatch(value):
        raise LifecycleError(f"{field} must be a 16-character lowercase hex digest")


def _required_string(data: Mapping[str, Any], field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise LifecycleError(f"execution_authority.{field} must be a non-empty string")
    return value


def _string_tuple(value: Any, field: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise LifecycleError(f"execution_authority.{field} must be a list of strings")
    return tuple(value)


def _integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LifecycleError(f"execution_authority.{field} must be an integer")
    return value


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise LifecycleError(f"execution_authority.{field} must be a boolean")
    return value


__all__ = [
    "AUTHORITY_SNAPSHOT_VERSION",
    "AuthoritySource",
    "ExecutionAuthoritySnapshot",
    "authority_projection",
]
