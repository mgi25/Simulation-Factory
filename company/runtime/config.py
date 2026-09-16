"""Explicit loading of the four Company OS bootstrap configuration files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from company.validation.errors import YamlSubsetError
from company.validation.yaml_subset import load_yaml_subset


@dataclass(frozen=True)
class CompanyConfig:
    """In-memory bootstrap contracts with their source directory."""

    config_dir: Path
    org_registry: dict[str, Any]
    permissions: dict[str, Any]
    agent_contract_schema: dict[str, Any]
    task_handoff_schema: dict[str, Any]


def default_config_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def load_company_config(config_dir: str | Path | None = None) -> CompanyConfig:
    """Load exactly the four canonical bootstrap YAML files."""

    root = Path(config_dir) if config_dir is not None else default_config_dir()
    root = root.resolve()
    files = {
        "org_registry": "org_registry.yaml",
        "permissions": "permissions.yaml",
        "agent_contract_schema": "agent_contract.schema.yaml",
        "task_handoff_schema": "task_handoff.schema.yaml",
    }
    loaded: dict[str, dict[str, Any]] = {}
    for name, filename in files.items():
        path = root / filename
        loaded[name] = load_yaml_subset(path)
    try:
        return CompanyConfig(config_dir=root, **loaded)
    except TypeError as exc:  # Defensive guard if the explicit file map changes.
        raise YamlSubsetError(f"invalid Company OS config bundle: {exc}") from exc


def load_validated_company_config(
    config_dir: str | Path | None = None,
) -> CompanyConfig:
    """Load canonical files and enforce all bootstrap invariants."""

    config = load_company_config(config_dir)
    from company.validation.bootstrap import validate_bootstrap

    validate_bootstrap(config)
    return config
