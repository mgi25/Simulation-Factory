"""The readiness result model: four statuses, and no fifth thing that averages them.

## Why `unknown` is a status and not a missing check

The question this package answers is "may Company OS cross into production
yet". The dangerous answer is not "no". The dangerous answer is "the check did
not run, so nothing was reported, so the list looked clean". Every condition
the gate names therefore produces a `GateCheck` on every run, and a condition
whose evidence could not be established produces one with status `unknown` and
the missing evidence named. `unknown` never satisfies a required condition -
`GateStatus.satisfies_requirement` is the single place that is decided, and it
returns True for `pass` and `not_applicable` only.

## Why `not_applicable` is narrow

`not_applicable` means the hazard cannot exist here - a production root the
brief names that this repository does not contain, for instance. It is the one
status that is both non-blocking and not a proof, which makes it the obvious
loophole, so a check may only return it when the policy explicitly allows it
(`GatePolicy.not_applicable_allowed`). Anything else is coerced to `unknown`.

## Why there is no score

There is no readiness score, no health score, no percentage and no weight,
here or anywhere in the package. A number would be optimised instead of the
conditions, and it would let nine passes hide one failure. Readiness is
derived by `readiness_of`: `READY` only when every required check is satisfied,
`BLOCKED` when any required check failed, and `INSUFFICIENT_EVIDENCE` when
nothing failed but some required evidence could not be established.

## Why a READY report is not permission

`ProductionIntegrationReadinessReport.authorizes_production_integration` is a
field that is always False, and it is a field rather than a docstring so that
every consumer - the CLI, the canonical JSON, a future dashboard panel - has to
carry it. The gate reports that technical conditions are satisfied. Wiring
Company OS into production remains a separate CEO decision.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Any, Iterable

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, dumps, fingerprint, to_jsonable

from .errors import IntegrationGateError


GATE_CHECK_VERSION = 1
REPORT_SCHEMA_VERSION = 1

CHECK_ID = re.compile(r"[a-z][a-z0-9_]*\.[a-z][a-z0-9_]{2,63}")
MAX_DETAIL_CHARS = 2000
MAX_EVIDENCE_REFS = 24


class GateStatus(Enum):
    """The verdict on one readiness condition."""

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"

    @property
    def satisfies_requirement(self) -> bool:
        """Does this verdict let a *required* condition stop blocking?

        The whole safety property of the gate is this one method. `unknown`
        answers False, which is the line between a gate and a checklist.
        """
        return self in (GateStatus.PASS, GateStatus.NOT_APPLICABLE)


class GateCategory(Enum):
    """The readiness dimensions, each independent of the others.

    The value is also the check-id prefix, which is how a check is kept in the
    section a reader found it in.
    """

    ARCHITECTURE = "architecture"
    EXECUTION_SAFETY = "execution"
    DATA_EVIDENCE = "data"
    WORKFORCE = "workforce"
    FINANCE = "finance"
    ANALYTICS = "analytics"
    EXECUTIVE_VISIBILITY = "executive"
    TEST_BUILD_HEALTH = "health"
    PRODUCTION_BOUNDARY = "production"


class EvidenceKind(Enum):
    """Where a check's evidence came from, and therefore how strong it is.

    A reader who disagrees with a verdict needs to know what it rests on.
    `REPOSITORY` and `CONTRACT` are re-derivable from the checkout alone;
    `PROBE` ran a Company OS guard and observed what it did; `SUPPLIED` was
    handed to the gate by its caller and is only as good as the caller.
    """

    REPOSITORY = "repository"
    CONTRACT = "contract"
    PROBE = "probe"
    SUPPLIED = "supplied"


@dataclass(frozen=True)
class GateCheck:
    """One readiness condition, its verdict, and what a reader needs to act.

    The four status-specific fields are not optional decoration. A `fail` with
    no blocker reason is an assertion nobody can argue with, and an `unknown`
    with no missing evidence is a shrug; both are refused at construction.
    """

    check_id: str
    category: GateCategory
    status: GateStatus
    requirement: str
    detail: str
    evidence_kind: EvidenceKind
    evidence: tuple[str, ...] = ()
    blocker_reason: str = ""
    missing_evidence: tuple[str, ...] = ()
    remediation: str = ""
    not_applicable_reason: str = ""
    evidence_as_of: dt.date | None = None
    version: int = GATE_CHECK_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.check_id, str) or not CHECK_ID.fullmatch(self.check_id):
            raise IntegrationGateError(
                f"check_id {self.check_id!r} must be '<category>.<name>' in "
                "lowercase [a-z0-9_]"
            )
        for name, enum_type in (
            ("category", GateCategory),
            ("status", GateStatus),
            ("evidence_kind", EvidenceKind),
        ):
            if not isinstance(getattr(self, name), enum_type):
                raise IntegrationGateError(
                    f"{self.check_id}: {name} must be a {enum_type.__name__} value"
                )
        prefix = self.check_id.split(".", 1)[0]
        if prefix != self.category.value:
            raise IntegrationGateError(
                f"{self.check_id}: a check lives in the section its id names; "
                f"prefix {prefix!r} is not category {self.category.value!r}"
            )
        object.__setattr__(
            self, "requirement", _prose(self.requirement, f"{self.check_id}.requirement")
        )
        object.__setattr__(self, "detail", _prose(self.detail, f"{self.check_id}.detail"))
        object.__setattr__(self, "evidence", _refs(self.evidence, f"{self.check_id}.evidence"))
        object.__setattr__(
            self,
            "missing_evidence",
            _lines(self.missing_evidence, f"{self.check_id}.missing_evidence"),
        )
        if self.evidence_as_of is not None:
            object.__setattr__(
                self,
                "evidence_as_of",
                as_date(self.evidence_as_of, f"{self.check_id}.evidence_as_of"),
            )
        self._assert_status_fields()
        if self.version != GATE_CHECK_VERSION:
            raise IntegrationGateError(
                f"{self.check_id}: version must be {GATE_CHECK_VERSION}, got {self.version!r}"
            )

    def _assert_status_fields(self) -> None:
        if self.status is GateStatus.FAIL:
            if not self.blocker_reason.strip():
                raise IntegrationGateError(
                    f"{self.check_id}: a failed check must say why it blocks. A verdict "
                    "with no reason cannot be argued with and cannot be fixed."
                )
            if not self.remediation.strip():
                raise IntegrationGateError(
                    f"{self.check_id}: a failed check must name a remediation"
                )
        elif self.blocker_reason.strip():
            raise IntegrationGateError(
                f"{self.check_id}: only a failed check carries a blocker reason, "
                f"this one is {self.status.value}"
            )

        if self.status is GateStatus.UNKNOWN:
            if not self.missing_evidence:
                raise IntegrationGateError(
                    f"{self.check_id}: an unknown check must name the evidence it "
                    "could not establish, or it is indistinguishable from a pass "
                    "nobody looked at"
                )
            if not self.remediation.strip():
                raise IntegrationGateError(
                    f"{self.check_id}: an unknown check must name how to supply the "
                    "missing evidence"
                )
        elif self.missing_evidence:
            raise IntegrationGateError(
                f"{self.check_id}: only an unknown check carries missing evidence, "
                f"this one is {self.status.value}"
            )

        if self.status is GateStatus.NOT_APPLICABLE:
            if not self.not_applicable_reason.strip():
                raise IntegrationGateError(
                    f"{self.check_id}: a not-applicable check must say why the "
                    "condition cannot arise here"
                )
        elif self.not_applicable_reason.strip():
            raise IntegrationGateError(
                f"{self.check_id}: only a not-applicable check carries that reason"
            )

    @property
    def satisfied(self) -> bool:
        return self.status.satisfies_requirement

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class GateSection:
    """One readiness category's checks, in check-id order."""

    category: GateCategory
    checks: tuple[GateCheck, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.category, GateCategory):
            raise IntegrationGateError("section category must be a GateCategory value")
        checks = tuple(self.checks)
        for check in checks:
            if not isinstance(check, GateCheck):
                raise IntegrationGateError("a section holds GateCheck values")
            if check.category is not self.category:
                raise IntegrationGateError(
                    f"{check.check_id} is a {check.category.value} check and cannot sit "
                    f"in the {self.category.value} section"
                )
        seen = [check.check_id for check in checks]
        duplicates = sorted({item for item in seen if seen.count(item) > 1})
        if duplicates:
            raise IntegrationGateError(
                f"duplicate check id(s) in {self.category.value}: {', '.join(duplicates)}"
            )
        object.__setattr__(self, "checks", tuple(sorted(checks, key=lambda c: c.check_id)))

    def by_status(self, status: GateStatus) -> tuple[GateCheck, ...]:
        return tuple(check for check in self.checks if check.status is status)


@dataclass(frozen=True)
class IntegrationBlocker:
    """One reason Company OS may not cross the boundary yet.

    `resolved` is the field this class exists to protect. A blocker is resolved
    when evidence says so and not before, so setting it without
    `resolution_evidence` is refused: "probably fine" is not a resolution, and a
    blocker list that can be cleared by assertion is a list nobody should read.
    """

    blocker_id: str
    check_id: str
    category: GateCategory
    reason: str
    remediation: str
    evidence: tuple[str, ...] = ()
    owner: str = ""
    ceo_decision_required: bool = False
    resolved: bool = False
    resolution_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "blocker_id", assert_reference(self.blocker_id, "blocker_id"))
        if not isinstance(self.check_id, str) or not CHECK_ID.fullmatch(self.check_id):
            raise IntegrationGateError(
                f"blocker {self.blocker_id}: check_id {self.check_id!r} is malformed"
            )
        if not isinstance(self.category, GateCategory):
            raise IntegrationGateError(
                f"blocker {self.blocker_id}: category must be a GateCategory"
            )
        object.__setattr__(self, "reason", _prose(self.reason, f"blocker {self.blocker_id}.reason"))
        object.__setattr__(
            self, "remediation", _prose(self.remediation, f"blocker {self.blocker_id}.remediation")
        )
        object.__setattr__(
            self, "evidence", _refs(self.evidence, f"blocker {self.blocker_id}.evidence")
        )
        object.__setattr__(
            self,
            "resolution_evidence",
            _refs(self.resolution_evidence, f"blocker {self.blocker_id}.resolution_evidence"),
        )
        if not isinstance(self.owner, str):
            raise IntegrationGateError(f"blocker {self.blocker_id}: owner must be a string")
        if not isinstance(self.ceo_decision_required, bool):
            raise IntegrationGateError(
                f"blocker {self.blocker_id}: ceo_decision_required must be a bool"
            )
        if not isinstance(self.resolved, bool):
            raise IntegrationGateError(f"blocker {self.blocker_id}: resolved must be a bool")
        if self.resolved and not self.resolution_evidence:
            raise IntegrationGateError(
                f"blocker {self.blocker_id}: a blocker is resolved when evidence says so. "
                "Name the commit, test or record that proves it, or leave it open."
            )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


class Readiness(Enum):
    """The gate's verdict. Three states, derived, never scored."""

    READY = "ready"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


def readiness_of(checks: Iterable[GateCheck], required: frozenset[str]) -> Readiness:
    """Derive readiness from the required checks alone. The only place it is decided.

    A required `fail` outranks a required `unknown`, because a known defect is
    more actionable than a missing measurement and the caller should see it
    named first. Neither is `READY`.
    """
    statuses = [check.status for check in checks if check.check_id in required]
    if any(status is GateStatus.FAIL for status in statuses):
        return Readiness.BLOCKED
    if any(not status.satisfies_requirement for status in statuses):
        return Readiness.INSUFFICIENT_EVIDENCE
    return Readiness.READY


@dataclass(frozen=True)
class EvidenceSource:
    """What the report was computed from, so a later reader can date it."""

    repo_root: str
    source_commit: str = ""
    source_branch: str = ""
    state_dir: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "repo_root", assert_reference(self.repo_root, "repo_root"))
        for name in ("source_commit", "source_branch", "state_dir"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise IntegrationGateError(f"evidence source {name} must be a string")
            if value:
                assert_reference(value, f"evidence_source.{name}")


@dataclass(frozen=True)
class ProductionIntegrationReadinessReport:
    """Every readiness condition, its verdict, and what still blocks the boundary.

    `authorizes_production_integration` is always False and is checked to be
    False at construction. A READY report says the technical gate conditions
    hold; it does not connect anything, and it is not the CEO approval that
    `permissions.yaml` reserves.
    """

    as_of: dt.date
    source: EvidenceSource
    policy_version: int
    sections: tuple[GateSection, ...]
    blockers: tuple[IntegrationBlocker, ...] = ()
    required_check_ids: tuple[str, ...] = ()
    advisory_check_ids: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    authorizes_production_integration: bool = False
    schema_version: int = REPORT_SCHEMA_VERSION
    report_id: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", as_date(self.as_of, "as_of"))
        if not isinstance(self.source, EvidenceSource):
            raise IntegrationGateError("report source must be an EvidenceSource")
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise IntegrationGateError("policy_version must be an integer")
        sections = tuple(self.sections)
        for section in sections:
            if not isinstance(section, GateSection):
                raise IntegrationGateError("report sections must be GateSection values")
        categories = [section.category.value for section in sections]
        if len(set(categories)) != len(categories):
            raise IntegrationGateError("a report holds one section per category")
        object.__setattr__(
            self, "sections", tuple(sorted(sections, key=lambda s: s.category.value))
        )
        object.__setattr__(
            self,
            "blockers",
            tuple(sorted(self.blockers, key=lambda b: (b.category.value, b.check_id))),
        )
        object.__setattr__(self, "required_check_ids", tuple(sorted(set(self.required_check_ids))))
        object.__setattr__(self, "advisory_check_ids", tuple(sorted(set(self.advisory_check_ids))))
        object.__setattr__(self, "notes", _lines(self.notes, "notes"))
        if self.authorizes_production_integration is not False:
            raise IntegrationGateError(
                "a readiness report never authorizes production integration; that "
                "decision is CEO-reserved (permissions.yaml) and lives outside this "
                "subsystem"
            )
        if self.schema_version != REPORT_SCHEMA_VERSION:
            raise IntegrationGateError(
                f"schema_version must be {REPORT_SCHEMA_VERSION}, got {self.schema_version!r}"
            )
        object.__setattr__(self, "report_id", self._derive_id())

    # -- derived ----------------------------------------------------------

    def _derive_id(self) -> str:
        payload = {key: value for key, value in to_jsonable(self).items() if key != "report_id"}
        return f"integration-readiness-{self.as_of.isoformat()}-{fingerprint(payload)}"

    def checks(self) -> tuple[GateCheck, ...]:
        return tuple(check for section in self.sections for check in section.checks)

    def check(self, check_id: str) -> GateCheck:
        for candidate in self.checks():
            if candidate.check_id == check_id:
                return candidate
        raise IntegrationGateError(f"no check {check_id!r} in this report")

    @property
    def readiness(self) -> Readiness:
        return readiness_of(self.checks(), frozenset(self.required_check_ids))

    def required_checks(self) -> tuple[GateCheck, ...]:
        required = set(self.required_check_ids)
        return tuple(c for c in self.checks() if c.check_id in required)

    def advisory_checks(self) -> tuple[GateCheck, ...]:
        advisory = set(self.advisory_check_ids)
        return tuple(c for c in self.checks() if c.check_id in advisory)

    def unknowns(self) -> tuple[GateCheck, ...]:
        """Every unknown, required or advisory, because a gap is worth seeing."""
        return tuple(c for c in self.checks() if c.status is GateStatus.UNKNOWN)

    def advisory_findings(self) -> tuple[GateCheck, ...]:
        """Advisory checks that did not pass. Visible, and deliberately not blocking."""
        return tuple(c for c in self.advisory_checks() if not c.satisfied)

    def open_blockers(self) -> tuple[IntegrationBlocker, ...]:
        return tuple(blocker for blocker in self.blockers if not blocker.resolved)

    def stale_against(self, source_commit: str) -> str:
        """Why this report no longer describes `source_commit`, or an empty string.

        A readiness verdict is a statement about one tree. After an
        architectural change it is history, not evidence, so a consumer asks
        this before believing it.
        """
        if not self.source.source_commit:
            return (
                "this report did not record a source commit, so it cannot be shown to "
                "describe any particular tree"
            )
        if not source_commit:
            return "no current commit was supplied to compare against"
        if source_commit != self.source.source_commit:
            return (
                f"the report describes {self.source.source_commit}, the tree is at "
                f"{source_commit}; re-run the gate"
            )
        return ""

    def canonical_json(self) -> str:
        return dumps(self)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


def _prose(value: Any, field_name: str) -> str:
    try:
        text = assert_text(value, field_name)
    except ValueError as exc:
        raise IntegrationGateError(str(exc)) from exc
    if len(text) > MAX_DETAIL_CHARS:
        raise IntegrationGateError(
            f"{field_name}: {len(text)} characters exceeds the {MAX_DETAIL_CHARS}-character "
            "budget. A finding names what it found and points at it; it does not paste it."
        )
    return text


def _refs(values: Any, field_name: str) -> tuple[str, ...]:
    items = _sequence(values, field_name)
    if len(items) > MAX_EVIDENCE_REFS:
        raise IntegrationGateError(
            f"{field_name}: {len(items)} references exceeds {MAX_EVIDENCE_REFS}. "
            "Name the first few and the count, not every one."
        )
    try:
        return tuple(
            assert_reference(item, f"{field_name}[{index}]") for index, item in enumerate(items)
        )
    except ValueError as exc:
        raise IntegrationGateError(str(exc)) from exc


def _lines(values: Any, field_name: str) -> tuple[str, ...]:
    items = _sequence(values, field_name)
    return tuple(_prose(item, f"{field_name}[{index}]") for index, item in enumerate(items))


def _sequence(values: Any, field_name: str) -> tuple[Any, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)):
        raise IntegrationGateError(f"{field_name}: expected a sequence, got a string")
    return tuple(values)


__all__ = [
    "CHECK_ID",
    "GATE_CHECK_VERSION",
    "REPORT_SCHEMA_VERSION",
    "EvidenceKind",
    "EvidenceSource",
    "GateCategory",
    "GateCheck",
    "GateSection",
    "GateStatus",
    "IntegrationBlocker",
    "ProductionIntegrationReadinessReport",
    "Readiness",
    "readiness_of",
]
