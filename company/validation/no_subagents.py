"""Bootstrap-mode enforcement for nested or autonomous worker switches."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any

from .errors import ValidationError


_REQUIRED_TRUE = {"no_subagents"}
_REQUIRED_FALSE = {
    "subagents",
    "allow_subagents",
    "enable_subagents",
    "child_agents",
    "child_agent_spawning",
    "child_workers",
    "allow_child_workers",
    "enable_child_workers",
    "spawn_child_workers",
    "nested_delegation",
    "allow_nested_delegation",
    "enable_nested_delegation",
    "nested_agent_spawning",
    "autonomous_workers",
    "autonomous_worker_spawning",
    "worker_spawning",
    "always_on_agents",
}


def collect_no_subagent_violations(value: Any, *, path: str = "config") -> list[str]:
    """Return violations found in mapping keys, recursively and deterministically."""

    issues: list[str] = []
    _collect(value, path, issues)
    return issues


def enforce_no_subagents(value: Any, *, path: str = "config") -> None:
    """Reject explicit switches that weaken Bootstrap's no-subagent invariant."""

    issues = collect_no_subagent_violations(value, path=path)
    if issues:
        raise ValidationError(issues)


def _collect(value: Any, path: str, issues: list[str]) -> None:
    if isinstance(value, Mapping):
        for raw_key in sorted(value, key=lambda item: str(item)):
            nested = value[raw_key]
            key = _normalize_key(str(raw_key))
            nested_path = f"{path}.{raw_key}"
            if key in _REQUIRED_TRUE and nested is not True:
                issues.append(f"{nested_path} must be true in Bootstrap Mode")
            elif key in _REQUIRED_FALSE and nested is not False:
                issues.append(f"{nested_path} must be false in Bootstrap Mode")
            _collect(nested, nested_path, issues)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, nested in enumerate(value):
            _collect(nested, f"{path}[{index}]", issues)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
