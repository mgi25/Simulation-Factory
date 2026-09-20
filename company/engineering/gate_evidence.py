"""The integration gate's verdict, read as evidence — never computed here.

`company/integration/` already answers "is Company OS safe to cross into
production?" with thirty-seven checks and a required/advisory split that cannot
be tuned without a visible diff. This package does not re-ask that question,
re-weight it, or wrap it. It reads the answer.

## Why reading rather than calling

Two reasons, and the second is the one that decides it.

The graph. `company/integration` already imports `company/dashboard`, and the
dashboard must show the engineering lifecycle, so
`company/dashboard -> company/engineering` is a necessary edge. An
`company/engineering -> company/integration` edge on top of that closes a cycle,
and `architecture.no_subsystem_import_cycle` is a required gate check. This
module imports nothing from the gate.

The governance. **Engineering holds no code that can produce a readiness
verdict**, so it cannot produce a favourable one. It parses a report the gate's
own unmodified CLI wrote:

    python -m company.integration check --repo-root . --json --suite-evidence suites.json > gate.json
    python -m company.engineering gate --gate-report gate.json ...

That is the same evidentiary standard the gate itself applies to test results,
for the same stated reason: a check that runs its own evidence can never be
`unknown`, and `unknown` is what does the work.

## What is kept, and what is deliberately dropped

`GateVerdict` keeps the readiness word, the gate's own `report_id`, the policy
version, the commit and branch it was computed from, its date, the blocker
list, and a digest of the exact bytes that were supplied. It drops the
thirty-seven check bodies: the CEO result needs to say READY or name the
blockers, and a reader who wants the detail has the report file, which is
stored alongside.

## How readiness is obtained

The gate's canonical JSON does not carry a `readiness` field: readiness is a
*derived* property of the report, and `to_jsonable` writes fields. The CLI
carries it out of band, as the exit code (0 READY, 1 BLOCKED, 2
INSUFFICIENT_EVIDENCE).

Trusting a supplied word would make the verdict forgeable, so `readiness_from`
re-derives it **from the report's own `required_check_ids` and check statuses**:
a required `fail` is BLOCKED, a required status that does not satisfy its
requirement is INSUFFICIENT_EVIDENCE, and everything else is READY. That is a
deliberate three-line mirror of `company.integration.model.readiness_of`, and
`tests/test_company_engineering_execution.py` pins the two against each other
over a real report so they cannot drift. It is a mirror rather than a call for
the graph reason above.

If a caller *also* supplies the readiness word (from the exit code),
`from_report_mapping` cross-checks it and refuses a mismatch, so the exit code
is verified rather than believed.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable

from .common import assert_day, assert_prose, assert_ref, text_tuple
from .errors import EngineeringError


GATE_VERDICT_VERSION = 1


class GateReadiness(str, Enum):
    """The gate's three verdicts, spelled exactly as it spells them."""

    READY = "ready"
    BLOCKED = "blocked"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"

    @property
    def permits_readiness(self) -> bool:
        """Only READY lets a work order reach ready_for_approval."""
        return self is GateReadiness.READY


@dataclass(frozen=True)
class GateBlocker:
    """One reason the gate did not say READY."""

    blocker_id: str
    check_id: str
    reason: str
    ceo_decision_required: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "blocker_id", assert_ref(self.blocker_id, "blocker.blocker_id")
        )
        object.__setattr__(self, "check_id", assert_ref(self.check_id, "blocker.check_id"))
        object.__setattr__(self, "reason", assert_prose(self.reason, "blocker.reason"))
        if not isinstance(self.ceo_decision_required, bool):
            raise EngineeringError("blocker.ceo_decision_required must be a boolean")

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class GateVerdict:
    """One integration gate report, kept as engineering evidence."""

    work_order_id: str
    report_id: str
    readiness: GateReadiness
    as_of: dt.date
    policy_version: int
    source_commit: str = ""
    source_branch: str = ""
    blockers: tuple[GateBlocker, ...] = ()
    unknown_check_ids: tuple[str, ...] = ()
    report_digest: str = ""
    report_ref: str = ""
    authorizes_production_integration: bool = False
    version: int = GATE_VERDICT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "work_order_id", assert_ref(self.work_order_id, "gate.work_order_id")
        )
        object.__setattr__(self, "report_id", assert_ref(self.report_id, "gate.report_id"))
        if not isinstance(self.readiness, GateReadiness):
            raise EngineeringError("gate.readiness must be a GateReadiness value")
        object.__setattr__(self, "as_of", assert_day(self.as_of, "gate.as_of"))
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise EngineeringError("gate.policy_version must be an integer")
        for name in ("source_commit", "source_branch", "report_digest", "report_ref"):
            if not isinstance(getattr(self, name), str):
                raise EngineeringError(f"gate.{name} must be a string")
        if not isinstance(self.blockers, tuple) or any(
            not isinstance(item, GateBlocker) for item in self.blockers
        ):
            raise EngineeringError("gate.blockers must hold GateBlocker values")
        object.__setattr__(
            self,
            "unknown_check_ids",
            text_tuple(self.unknown_check_ids, "gate.unknown_check_ids", limit=64),
        )
        if self.authorizes_production_integration is not False:
            raise EngineeringError(
                "a gate verdict never authorizes production integration; the gate's own "
                "report says so and this record does not get to disagree"
            )
        if self.readiness is GateReadiness.READY and self.blockers:
            raise EngineeringError(
                "a READY gate report carries no blocker; a verdict with both is not a "
                "faithful copy of any report the gate can produce"
            )
        if self.version != GATE_VERDICT_VERSION:
            raise EngineeringError(
                f"gate.version must be {GATE_VERDICT_VERSION}, got {self.version!r}"
            )

    @property
    def blocker_summaries(self) -> tuple[str, ...]:
        return tuple(f"{item.check_id}: {item.reason}" for item in self.blockers)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        return _fingerprint(self)

    def stale_against(self, commit: str) -> str:
        """Why this verdict no longer describes the checkout, or an empty string."""
        if not commit or not self.source_commit:
            return ""
        if commit == self.source_commit:
            return ""
        return (
            f"the gate verdict was computed at {self.source_commit} and the checkout is "
            f"at {commit}; re-run the gate"
        )

    # --- reading a report the gate wrote -----------------------------------

    @classmethod
    def from_report_mapping(
        cls,
        data: Mapping[str, Any],
        *,
        work_order_id: str,
        report_ref: str = "",
        report_digest: str = "",
        reported_readiness: str = "",
    ) -> "GateVerdict":
        """Parse one `ProductionIntegrationReadinessReport` as canonical JSON.

        The report's own shape is trusted only as far as its named fields. A
        report with no `required_check_ids`, or one that claims to authorize
        production integration, is refused rather than coerced.
        """
        if not isinstance(data, Mapping):
            raise EngineeringError("a gate report must be a JSON object")
        parsed = readiness_from(data)
        if reported_readiness:
            try:
                claimed = GateReadiness(reported_readiness)
            except ValueError as exc:
                allowed = ", ".join(item.value for item in GateReadiness)
                raise EngineeringError(
                    f"reported gate readiness {reported_readiness!r} is not one of: "
                    f"{allowed}"
                ) from exc
            if claimed is not parsed:
                raise EngineeringError(
                    f"the caller reports the gate said {claimed.value!r} and the "
                    f"report's own required checks say {parsed.value!r}. The report "
                    "decides."
                )
        if data.get("authorizes_production_integration") not in (False, None):
            raise EngineeringError(
                "the supplied gate report claims to authorize production integration. "
                "No report the gate can construct does; this one is not trustworthy."
            )
        source = data.get("source", {})
        if not isinstance(source, Mapping):
            raise EngineeringError("gate report source must be an object")
        raw_blockers = data.get("blockers", ())
        if isinstance(raw_blockers, (str, bytes)) or not isinstance(
            raw_blockers, (list, tuple)
        ):
            raise EngineeringError("gate report blockers must be a list")
        blockers = tuple(
            GateBlocker(
                blocker_id=str(item.get("blocker_id", "")),
                check_id=str(item.get("check_id", "")),
                reason=str(item.get("reason", "")),
                ceo_decision_required=bool(item.get("ceo_decision_required", False)),
            )
            for item in raw_blockers
            if isinstance(item, Mapping) and not item.get("resolved", False)
        )
        policy_version = data.get("policy_version", 0)
        if isinstance(policy_version, bool) or not isinstance(policy_version, int):
            raise EngineeringError("gate report policy_version must be an integer")
        return cls(
            work_order_id=work_order_id,
            report_id=str(data.get("report_id", "")),
            readiness=parsed,
            as_of=assert_day(data.get("as_of"), "gate.as_of"),
            policy_version=policy_version,
            source_commit=str(source.get("source_commit", "")),
            source_branch=str(source.get("source_branch", "")),
            blockers=blockers,
            unknown_check_ids=_unknown_check_ids(data),
            report_digest=report_digest,
            report_ref=report_ref,
        )

    @classmethod
    def from_report_path(
        cls,
        path: Path | str,
        *,
        work_order_id: str,
        report_ref: str = "",
        reported_readiness: str = "",
    ) -> "GateVerdict":
        """Read a gate report from disk, digesting the exact bytes supplied."""
        target = Path(path)
        try:
            payload = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise EngineeringError(f"cannot read gate report {target}: {exc}") from exc
        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise EngineeringError(
                f"{target}: not a JSON gate report ({exc}). `python -m company.integration "
                "check --json` writes one."
            ) from exc
        return cls.from_report_mapping(
            data,
            work_order_id=work_order_id,
            report_ref=report_ref or target.name,
            report_digest=_fingerprint(payload),
            reported_readiness=reported_readiness,
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "GateVerdict":
        """Decode a stored `GateVerdict` — not a gate report. See `from_report_mapping`."""
        if not isinstance(data, Mapping):
            raise EngineeringError("a gate verdict must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError(
                "gate verdict has unknown field(s): " + ", ".join(unknown)
            )
        readiness = data.get("readiness")
        if not isinstance(readiness, str):
            raise EngineeringError("gate.readiness must be a string")
        try:
            parsed = GateReadiness(readiness)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in GateReadiness)
            raise EngineeringError(f"gate.readiness must be one of: {allowed}") from exc
        raw_blockers = data.get("blockers", ())
        if isinstance(raw_blockers, (str, bytes)) or not isinstance(
            raw_blockers, (list, tuple)
        ):
            raise EngineeringError("gate.blockers must be a list")
        blockers = []
        for index, item in enumerate(raw_blockers):
            if not isinstance(item, Mapping):
                raise EngineeringError(f"gate.blockers[{index}] must be a mapping")
            extra = sorted(
                set(item) - {"blocker_id", "check_id", "reason", "ceo_decision_required"}
            )
            if extra:
                raise EngineeringError(
                    f"gate.blockers[{index}] has unknown field(s): " + ", ".join(extra)
                )
            blockers.append(
                GateBlocker(
                    blocker_id=str(item.get("blocker_id", "")),
                    check_id=str(item.get("check_id", "")),
                    reason=str(item.get("reason", "")),
                    ceo_decision_required=bool(item.get("ceo_decision_required", False)),
                )
            )
        unknown_ids = data.get("unknown_check_ids", ())
        if isinstance(unknown_ids, (str, bytes)) or not isinstance(
            unknown_ids, (list, tuple)
        ):
            raise EngineeringError("gate.unknown_check_ids must be a list")
        version = data.get("version", GATE_VERDICT_VERSION)
        if isinstance(version, bool) or not isinstance(version, int):
            raise EngineeringError("gate.version must be an integer")
        policy_version = data.get("policy_version", 0)
        if isinstance(policy_version, bool) or not isinstance(policy_version, int):
            raise EngineeringError("gate.policy_version must be an integer")
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            report_id=str(data.get("report_id", "")),
            readiness=parsed,
            as_of=assert_day(data.get("as_of"), "gate.as_of"),
            policy_version=policy_version,
            source_commit=str(data.get("source_commit", "")),
            source_branch=str(data.get("source_branch", "")),
            blockers=tuple(blockers),
            unknown_check_ids=tuple(str(item) for item in unknown_ids),
            report_digest=str(data.get("report_digest", "")),
            report_ref=str(data.get("report_ref", "")),
            authorizes_production_integration=bool(
                data.get("authorizes_production_integration", False)
            ),
            version=version,
        )


# Statuses that let a *required* condition stop blocking. The mirror of
# `company.integration.model.GateStatus.satisfies_requirement`, pinned against
# the real thing by tests/test_company_engineering_execution.py.
_SATISFYING_STATUSES = frozenset({"pass", "not_applicable"})


def readiness_from(data: Mapping[str, Any]) -> GateReadiness:
    """Derive the gate's verdict from its own report, by its own rule.

    A required `fail` outranks a required `unknown`, for the reason
    `readiness_of` gives: a known defect is more actionable than a missing
    measurement. A required check the report does not contain counts as
    unsatisfied, which is the honest reading of a condition nobody answered.
    """
    required = data.get("required_check_ids", ())
    if isinstance(required, (str, bytes)) or not isinstance(required, (list, tuple)):
        raise EngineeringError(
            "a gate report must carry required_check_ids; without them no required "
            "condition can be identified and no verdict can be read"
        )
    wanted = {str(item) for item in required}
    if not wanted:
        raise EngineeringError(
            "the gate report names no required check. A report with no required "
            "condition cannot say READY about anything."
        )
    statuses: dict[str, str] = {}
    sections = data.get("sections", ())
    if isinstance(sections, (list, tuple)):
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            checks = section.get("checks", ())
            if not isinstance(checks, (list, tuple)):
                continue
            for check in checks:
                if isinstance(check, Mapping):
                    statuses[str(check.get("check_id", ""))] = str(
                        check.get("status", "")
                    )
    observed = {name: statuses.get(name, "") for name in sorted(wanted)}
    if any(status == "fail" for status in observed.values()):
        return GateReadiness.BLOCKED
    if any(status not in _SATISFYING_STATUSES for status in observed.values()):
        return GateReadiness.INSUFFICIENT_EVIDENCE
    return GateReadiness.READY


def _unknown_check_ids(data: Mapping[str, Any]) -> tuple[str, ...]:
    """Every check the report marked `unknown`, whatever section it sat in."""
    found: set[str] = set()
    sections = data.get("sections", ())
    if isinstance(sections, (list, tuple)):
        for section in sections:
            if not isinstance(section, Mapping):
                continue
            checks = section.get("checks", ())
            if not isinstance(checks, (list, tuple)):
                continue
            for check in checks:
                if isinstance(check, Mapping) and check.get("status") == "unknown":
                    found.add(str(check.get("check_id", "")))
    return tuple(sorted(item for item in found if item))


__all__ = [
    "GATE_VERDICT_VERSION",
    "GateBlocker",
    "GateReadiness",
    "GateVerdict",
    "readiness_from",
]
