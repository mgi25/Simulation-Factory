"""Test results the gate is told about, because it will not run them itself.

## Why the gate does not shell out to pytest

Two reasons, and the second is the one that decides it. First, this package
holds no process-spawn authority - `production.no_publishing_capability`
refuses `subprocess` across all of Company OS, and a gate that exempts itself
from the rule it enforces is not a gate. Second, a check that runs its own
evidence can never be `unknown`, and the entire design rests on a required
condition being able to say "nobody has shown me this".

So suite results are *supplied*. The caller runs pytest, records what
happened, and hands the gate a file. `health.required_suites_pass` is
`unknown` until they do, and a required unknown blocks readiness, which means
the honest default for a company nobody has tested is BLOCKED rather than
READY.

## Why supplied evidence carries a reporter and a date

Evidence that cannot be dated cannot go stale, and evidence with no reporter
cannot be questioned. `SuiteResult` requires both, and `stale_entries` reports
anything older than the report's freshness window rather than silently
accepting a green run from three architectural changes ago.

## Why a suite is named by its path

`tests/test_company_runtime.py` is a pointer a reader can run. A label like
"runtime suite" is not.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, read_json, to_jsonable

from .errors import IntegrationGateError


# How long a recorded suite run stays evidence. A week is long enough to cover
# a review cycle and short enough that an architectural change invalidates it.
DEFAULT_MAX_EVIDENCE_AGE_DAYS = 7

# The Company OS suites the integration gate requires. Each one is the named
# test registry entry of a bounded subsystem; between them they cover every
# subsystem whose invariants the required checks depend on.
REQUIRED_SUITES: tuple[str, ...] = (
    "tests/test_company_analytics.py",
    "tests/test_company_dashboard.py",
    "tests/test_company_execution_transport.py",
    "tests/test_company_finance.py",
    "tests/test_company_integration_gate.py",
    "tests/test_company_org_intelligence.py",
    "tests/test_company_os_ai_platform.py",
    "tests/test_company_os_capsules.py",
    "tests/test_company_os_knowledge.py",
    "tests/test_company_runtime.py",
    "tests/test_company_workforce.py",
)


@dataclass(frozen=True)
class SuiteResult:
    """One recorded test run, and who says so."""

    suite: str
    passed: bool
    observed_on: dt.date
    reported_by: str
    selected: int = 0
    failed: int = 0
    note: str = ""
    company_os: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "suite", assert_reference(self.suite, "suite"))
        object.__setattr__(self, "reported_by", assert_reference(self.reported_by, "reported_by"))
        object.__setattr__(self, "observed_on", as_date(self.observed_on, "observed_on"))
        for name in ("passed", "company_os"):
            if not isinstance(getattr(self, name), bool):
                raise IntegrationGateError(f"suite {self.suite}: {name} must be a bool")
        for name in ("selected", "failed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise IntegrationGateError(
                    f"suite {self.suite}: {name} must be a non-negative integer"
                )
        if self.passed and self.failed:
            raise IntegrationGateError(
                f"suite {self.suite}: reported as passing with {self.failed} failure(s). "
                "A run is green or it is not; the count is what a reader checks."
            )
        if self.note:
            assert_text(self.note, f"suite {self.suite} note")

    def age_days(self, as_of: dt.date) -> int:
        return (as_of - self.observed_on).days

    def reference(self) -> str:
        outcome = "passed" if self.passed else f"failed ({self.failed})"
        return f"{self.suite} {outcome} on {self.observed_on.isoformat()}"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "SuiteResult":
        if not isinstance(data, Mapping):
            raise IntegrationGateError("a suite result must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise IntegrationGateError(
                "suite result has unknown field(s): "
                + ", ".join(unknown)
                + ". Supplied evidence is read against a fixed schema so that an "
                "unexpected key cannot quietly change what was claimed."
            )
        return cls(
            suite=str(data.get("suite", "")),
            passed=bool(data.get("passed", False)),
            observed_on=as_date(data.get("observed_on"), "observed_on"),
            reported_by=str(data.get("reported_by", "")),
            selected=int(data.get("selected", 0)),
            failed=int(data.get("failed", 0)),
            note=str(data.get("note", "")),
            company_os=bool(data.get("company_os", True)),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class SuiteEvidence:
    """Every supplied run, indexed by suite."""

    results: tuple[SuiteResult, ...] = ()
    max_age_days: int = DEFAULT_MAX_EVIDENCE_AGE_DAYS

    def __post_init__(self) -> None:
        results = tuple(self.results)
        for result in results:
            if not isinstance(result, SuiteResult):
                raise IntegrationGateError("suite evidence holds SuiteResult values")
        names = [result.suite for result in results]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise IntegrationGateError(
                "two results were supplied for the same suite: " + ", ".join(duplicates)
            )
        if isinstance(self.max_age_days, bool) or not isinstance(self.max_age_days, int):
            raise IntegrationGateError("max_age_days must be an integer")
        if self.max_age_days < 0:
            raise IntegrationGateError("max_age_days must not be negative")
        object.__setattr__(self, "results", tuple(sorted(results, key=lambda r: r.suite)))

    def __bool__(self) -> bool:
        return bool(self.results)

    def get(self, suite: str) -> SuiteResult | None:
        for result in self.results:
            if result.suite == suite:
                return result
        return None

    def missing(self, required: Iterable[str] = REQUIRED_SUITES) -> tuple[str, ...]:
        return tuple(suite for suite in sorted(required) if self.get(suite) is None)

    def failing(self, required: Iterable[str] = REQUIRED_SUITES) -> tuple[SuiteResult, ...]:
        wanted = set(required)
        return tuple(r for r in self.results if r.suite in wanted and not r.passed)

    def stale(
        self, as_of: dt.date, required: Iterable[str] = REQUIRED_SUITES
    ) -> tuple[SuiteResult, ...]:
        wanted = set(required)
        return tuple(
            r
            for r in self.results
            if r.suite in wanted and r.age_days(as_of) > self.max_age_days
        )

    def production_results(self) -> tuple[SuiteResult, ...]:
        """Runs the caller marked as production-environment rather than Company OS."""
        return tuple(r for r in self.results if not r.company_os)

    @classmethod
    def from_path(cls, path: Path | str) -> "SuiteEvidence":
        """Load a supplied evidence file: a list of results, or an object holding one."""
        data = read_json(Path(path))
        if isinstance(data, Mapping):
            entries = data.get("results", ())
            max_age = data.get("max_age_days", DEFAULT_MAX_EVIDENCE_AGE_DAYS)
        else:
            entries = data
            max_age = DEFAULT_MAX_EVIDENCE_AGE_DAYS
        if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
            raise IntegrationGateError(
                f"{path}: expected a list of suite results, or an object with a "
                "'results' list"
            )
        return cls(
            results=tuple(SuiteResult.from_dict(entry) for entry in entries),
            max_age_days=int(max_age),
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


__all__ = [
    "DEFAULT_MAX_EVIDENCE_AGE_DAYS",
    "REQUIRED_SUITES",
    "SuiteEvidence",
    "SuiteResult",
]
