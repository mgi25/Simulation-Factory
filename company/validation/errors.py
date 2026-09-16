"""Shared exceptions for Company OS loading and validation."""

from __future__ import annotations

from collections.abc import Iterable


class CompanyOSError(Exception):
    """Base class for deterministic Company OS failures."""


class YamlSubsetError(CompanyOSError):
    """Raised when a bootstrap file uses invalid or unsupported YAML."""


class ValidationError(CompanyOSError):
    """Raised with one or more actionable validation issues."""

    def __init__(self, issues: str | Iterable[str]) -> None:
        if isinstance(issues, str):
            normalized = (issues,)
        else:
            normalized = tuple(dict.fromkeys(str(issue) for issue in issues))
        if not normalized:
            normalized = ("validation failed",)
        self.issues = normalized
        message = "Company OS validation failed:\n" + "\n".join(
            f"- {issue}" for issue in normalized
        )
        super().__init__(message)
