"""Neutral data contracts shared by Company OS loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CompanyConfig:
    """Raw bootstrap contracts together with their canonical source directory."""

    config_dir: Path
    org_registry: dict[str, Any]
    permissions: dict[str, Any]
    agent_contract_schema: dict[str, Any]
    task_handoff_schema: dict[str, Any]


__all__ = ["CompanyConfig"]
