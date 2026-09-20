"""A capability gap: what we could not do, and the evidence that we could not.

Constitution rule 17 - *prove need before building* - is the reason this record
class is strict where most record classes are permissive. Three refusals carry
the rule:

1. **A gap with nothing missing is not a gap.** If every required capability
   has an active provider, construction fails. The only exception is a gap
   whose capabilities are all covered by *dormant* employees, which is a real
   workforce need with a cheap answer (activation), and the record keeps those
   two situations in separate fields so the proposal layer cannot confuse them.

2. **A gap without evidence is an opinion.** `evidence` must be non-empty, and
   so must the trigger's reference. "We should probably have a sound designer"
   is not a gap; "task X could not be routed on 2026-09-16, see the escalation"
   is.

3. **Frequency is supplied, never inferred.** `FrequencyEvidence` carries the
   caller's explicit claim *and* the observation count behind it, and the
   record checks the two agree: `RECURRING` with one observation is refused. So
   the code never decides that a need recurs - it only refuses to let someone
   say so without having counted.

`gap_from_coverage` is the only constructor most callers want. It derives the
covered/missing split from a `CoverageReport` rather than taking it as an
argument, so a gap cannot claim a capability is missing that the org registry
says is covered.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    id_tuple,
)
from .coverage import CoverageReport
from .errors import WorkforceError


class NeedFrequency(Enum):
    """How often the work that needs the missing capability actually arrives.

    The three values map one-to-one onto section 5 of the workforce brief:
    a one-off need buys a temporary specialist, a recurring need may justify a
    permanent role, and `INTERMITTENT` is the honest middle - observed more than
    once, not yet often enough to be a role.
    """

    ONE_OFF = "one_off"
    INTERMITTENT = "intermittent"
    RECURRING = "recurring"


class Urgency(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapStatus(Enum):
    OPEN = "open"
    PROPOSED = "proposed"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    WITHDRAWN = "withdrawn"


class TriggerKind(Enum):
    TASK = "task"
    PROJECT = "project"
    OPPORTUNITY = "opportunity"
    INCIDENT = "incident"


@dataclass(frozen=True)
class GapTrigger:
    """The specific thing that could not be done. A reference, not a feeling."""

    kind: TriggerKind
    ref: str
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TriggerKind):
            raise WorkforceError("gap trigger kind must be a TriggerKind")
        assert_ref(self.ref, "gap trigger ref")
        assert_prose(self.summary, "gap trigger summary")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GapTrigger:
        return cls(kind=TriggerKind(data["kind"]), ref=data["ref"], summary=data["summary"])


@dataclass(frozen=True)
class FrequencyEvidence:
    """An explicit frequency claim, and the counting that has to back it.

    The consistency rules are deliberately arithmetic rather than clever:

        ONE_OFF        exactly one observation
        INTERMITTENT   at least two
        RECURRING      at least three, inside a stated window, with evidence

    Three is a judgement, not a law of nature; it is stated here in one place so
    a company that disagrees changes one number rather than arguing with code
    scattered across the proposal layer.
    """

    frequency: NeedFrequency
    observed_occurrences: int
    window_days: int
    evidence: tuple[Evidence, ...] = ()
    note: str = ""

    RECURRING_MINIMUM = 3

    def __post_init__(self) -> None:
        if not isinstance(self.frequency, NeedFrequency):
            raise WorkforceError("frequency must be a NeedFrequency")
        for name in ("observed_occurrences", "window_days"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise WorkforceError(f"frequency {name} must be a non-negative integer")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if not isinstance(self.note, str):
            raise WorkforceError("frequency note must be a string")

        occurrences = self.observed_occurrences
        if self.frequency is NeedFrequency.ONE_OFF and occurrences != 1:
            raise WorkforceError(
                f"a one-off need was observed {occurrences} times; say which it is - "
                "the frequency drives temporary specialist versus permanent role"
            )
        if self.frequency is NeedFrequency.INTERMITTENT and occurrences < 2:
            raise WorkforceError(
                f"an intermittent need needs at least 2 observations, got {occurrences}"
            )
        if self.frequency is NeedFrequency.RECURRING:
            if occurrences < self.RECURRING_MINIMUM:
                raise WorkforceError(
                    f"a recurring need needs at least {self.RECURRING_MINIMUM} observations, "
                    f"got {occurrences}; the code will not decide that a need recurs"
                )
            if self.window_days <= 0:
                raise WorkforceError("a recurring need must state the window it recurred in")
            assert_evidence_backed(
                self.evidence,
                "recurring frequency evidence",
                "a permanent role is the most expensive answer available; it needs a "
                "pointer to the occurrences, not a count someone remembers",
            )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FrequencyEvidence:
        return cls(
            frequency=NeedFrequency(data["frequency"]),
            observed_occurrences=data["observed_occurrences"],
            window_days=data["window_days"],
            evidence=evidence_tuple(data.get("evidence")),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class CapabilityGap:
    """A proven inability, with everything a proposal needs to answer it."""

    gap_id: str
    required_capabilities: tuple[str, ...]
    covered_actively: tuple[str, ...]
    covered_dormant: tuple[str, ...]
    missing: tuple[str, ...]
    trigger: GapTrigger
    frequency: FrequencyEvidence
    urgency: Urgency
    business_impact: str
    observed_on: dt.date
    evidence: tuple[Evidence, ...] = ()
    workaround: str = ""
    status: GapStatus = GapStatus.OPEN
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.gap_id, "gap_id")
        for name in ("required_capabilities", "covered_actively", "covered_dormant", "missing"):
            object.__setattr__(self, name, id_tuple(getattr(self, name), f"gap {name}", sort=True))
        if not self.required_capabilities:
            raise WorkforceError(f"gap {self.gap_id}: at least one required capability")
        if not isinstance(self.trigger, GapTrigger):
            raise WorkforceError(f"gap {self.gap_id}: trigger must be a GapTrigger")
        if not isinstance(self.frequency, FrequencyEvidence):
            raise WorkforceError(f"gap {self.gap_id}: frequency must be a FrequencyEvidence")
        if not isinstance(self.urgency, Urgency):
            raise WorkforceError(f"gap {self.gap_id}: urgency must be an Urgency")
        if not isinstance(self.status, GapStatus):
            raise WorkforceError(f"gap {self.gap_id}: status must be a GapStatus")
        assert_prose(self.business_impact, f"gap {self.gap_id} business_impact")
        object.__setattr__(self, "observed_on", assert_day(self.observed_on, "gap observed_on"))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        for name in ("workaround", "notes"):
            if not isinstance(getattr(self, name), str):
                raise WorkforceError(f"gap {self.gap_id}: {name} must be a string")

        buckets = (
            set(self.covered_actively),
            set(self.covered_dormant),
            set(self.missing),
        )
        union: set[str] = set()
        for bucket in buckets:
            if union & bucket:
                raise WorkforceError(
                    f"gap {self.gap_id}: a capability cannot be in two coverage buckets: "
                    + ", ".join(sorted(union & bucket))
                )
            union |= bucket
        if union != set(self.required_capabilities):
            raise WorkforceError(
                f"gap {self.gap_id}: covered and missing must account for exactly the "
                "required capabilities"
            )

        assert_evidence_backed(
            self.evidence,
            f"gap {self.gap_id} evidence",
            "a gap is an observed inability. No gap exists because a job title sounds "
            "useful, so the record refuses to be written without a pointer to the failure",
        )
        if not self.missing and not self.covered_dormant:
            raise WorkforceError(
                f"gap {self.gap_id}: every required capability has an active provider, so "
                "there is no gap. Route the task instead of proposing a workforce change"
            )

    # -- reading ----------------------------------------------------------

    @property
    def is_activation_only(self) -> bool:
        """Nothing is missing; the company is simply not running what it has."""
        return not self.missing and bool(self.covered_dormant)

    @property
    def covered(self) -> tuple[str, ...]:
        return tuple(sorted(self.covered_actively + self.covered_dormant))

    def to_dict(self) -> dict[str, Any]:
        from ai_platform.serde import to_jsonable

        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CapabilityGap:
        return cls(
            gap_id=data["gap_id"],
            required_capabilities=tuple(data["required_capabilities"]),
            covered_actively=tuple(data.get("covered_actively", ())),
            covered_dormant=tuple(data.get("covered_dormant", ())),
            missing=tuple(data.get("missing", ())),
            trigger=GapTrigger.from_dict(data["trigger"]),
            frequency=FrequencyEvidence.from_dict(data["frequency"]),
            urgency=Urgency(data["urgency"]),
            business_impact=data["business_impact"],
            observed_on=assert_day(data["observed_on"], "observed_on"),
            evidence=evidence_tuple(data.get("evidence")),
            workaround=data.get("workaround", ""),
            status=GapStatus(data.get("status", GapStatus.OPEN.value)),
            notes=data.get("notes", ""),
        )


def gap_from_coverage(
    gap_id: str,
    report: CoverageReport,
    *,
    trigger: GapTrigger,
    frequency: FrequencyEvidence,
    urgency: Urgency,
    business_impact: str,
    observed_on: dt.date,
    evidence: tuple[Evidence, ...] = (),
    workaround: str = "",
    notes: str = "",
) -> CapabilityGap:
    """Build a gap whose coverage split is derived, not asserted.

    Raises rather than returning `None` when the report shows full active
    coverage: the caller asked for a gap record and there is no gap, and a
    silent `None` is how that turns into a hire proposal three functions later.
    """
    return CapabilityGap(
        gap_id=gap_id,
        required_capabilities=report.required,
        covered_actively=report.fully_covered,
        covered_dormant=report.partially_covered,
        missing=report.uncovered,
        trigger=trigger,
        frequency=frequency,
        urgency=urgency,
        business_impact=business_impact,
        observed_on=observed_on,
        evidence=evidence,
        workaround=workaround,
        notes=notes,
    )
