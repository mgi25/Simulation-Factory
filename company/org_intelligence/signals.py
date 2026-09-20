"""An observed organizational signal: one number, where it came from, and
everything about it that nobody measured.

## A signal is not a conclusion

This is the lowest layer, and it is deliberately dumb. `role_overlap` means two
roles declare the same capabilities; it does not mean one of them should go.
`high_escalation_rate` means most of a role's work escalated; it does not mean
the role is staffed wrong - it may be scoped wrong, or be the escalation path
itself. Turning a signal into a claim is `findings.py`, and it takes more than
one signal to do it.

## The missing half is a field

`Measurement` carries `value=None` when nobody measured, and the signal then
*must* name what is missing. That asymmetry is the point: a rate that could not
be computed and a rate that came out zero are different facts, and a structure
that encodes them the same way loses the difference forever.
`ai_platform/usage.py` made the same argument about token counts; the
consequence here is that a signal with no number is still a legitimate, storable
record - it says "we looked and could not tell", which is worth knowing.

## Small samples keep their caveat

A first-pass rate over three tasks is a real number and a weak one. Rather than
suppressing it - which loses the observation - or reporting it plainly - which
launders it - a measurement below `minimum_sample` forces a caveat onto the
signal at construction. It cannot be dropped by a caller who did not think about
it, because the caller never wrote it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    text_tuple,
)
from .errors import OrgIntelligenceError
from .window import ReviewWindow


class SignalType(Enum):
    """What was observed. Section 2 of the brief, one value each."""

    CAPABILITY_GAP_FREQUENCY = "capability_gap_frequency"
    DORMANT_CAPABILITY = "dormant_capability"
    CRITICAL_SINGLE_POINT_FAILURE = "critical_single_point_failure"
    ROLE_OVERLAP = "role_overlap"
    ROLE_UNUSED = "role_unused"
    HIGH_REJECTION_RATE = "high_rejection_rate"
    HIGH_ESCALATION_RATE = "high_escalation_rate"
    POOR_FIRST_PASS_RATE = "poor_first_pass_rate"
    HIGH_RESOURCE_PER_ACCEPTANCE = "high_resource_per_acceptance"
    REPEATED_RETRY_PATTERN = "repeated_retry_pattern"
    CONTEXT_EXPANSION_PRESSURE = "context_expansion_pressure"
    MANUAL_REPEAT_WORK = "manual_repeat_work"
    MANAGEMENT_BOTTLENECK = "management_bottleneck"
    APPROVAL_BOTTLENECK = "approval_bottleneck"
    STALE_CONTRACT = "stale_contract"
    CONTRACT_BLOAT = "contract_bloat"
    RESEARCH_QUERY_DUPLICATION = "research_query_duplication"
    RESEARCH_CREATOR_CONCENTRATION = "research_creator_concentration"
    LOW_RESEARCH_YIELD = "low_research_yield"
    MANAGEMENT_DEPTH = "management_depth"
    MANAGEMENT_SPAN = "management_span"
    MANAGEMENT_CYCLE = "management_cycle"
    INVALID_MANAGEMENT_REFERENCE = "invalid_management_reference"
    ORPHAN_ROLE = "orphan_role"
    DUPLICATED_MANAGEMENT_LAYER = "duplicated_management_layer"
    UNUSED_CAPABILITY = "unused_capability"


class SubjectKind(Enum):
    """What the subject id names, so a reader never has to guess."""

    EMPLOYEE = "employee"
    CAPABILITY = "capability"
    DEPARTMENT = "department"
    WORKFLOW = "workflow"
    APPROVAL_STEP = "approval_step"
    CAPSULE = "capsule"
    CONTRACT = "contract"
    RESEARCH_BATCH = "research_batch"
    POLICY = "policy"
    ORGANIZATION = "organization"


class Direction(Enum):
    """Which way is bad for this measurement. Without it a threshold is ambiguous."""

    HIGHER_IS_WORSE = "higher_is_worse"
    LOWER_IS_WORSE = "lower_is_worse"
    NEITHER = "neither"


SMALL_SAMPLE_CAVEAT = (
    "sample of {sample} is below the {minimum} this measurement needs to be read "
    "as a rate; treat it as an observation, not a level"
)


@dataclass(frozen=True)
class Measurement:
    """One number, its unit, what it was compared against, and its sample size.

    Every field may be absent. The default `Measurement()` is the honest record
    of having looked at something we cannot yet count, and it is legal.
    """

    value: float | None = None
    unit: str = ""
    threshold: float | None = None
    direction: Direction = Direction.NEITHER
    sample_size: int | None = None
    minimum_sample: int = 0

    def __post_init__(self) -> None:
        for name in ("value", "threshold"):
            raw = getattr(self, name)
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise OrgIntelligenceError(f"measurement {name} must be a number or None")
            object.__setattr__(self, name, float(raw))
        if not isinstance(self.direction, Direction):
            raise OrgIntelligenceError("measurement direction must be a Direction")
        if self.value is not None and not str(self.unit).strip():
            raise OrgIntelligenceError(
                "a measured value needs a unit; a bare float is not a measurement"
            )
        for name in ("sample_size", "minimum_sample"):
            raw = getattr(self, name)
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise OrgIntelligenceError(f"measurement {name} must be a non-negative integer")
        if self.threshold is not None and self.direction is Direction.NEITHER:
            raise OrgIntelligenceError(
                "a threshold without a direction cannot be read: say which side is worse"
            )

    @property
    def measured(self) -> bool:
        return self.value is not None

    @property
    def compared(self) -> bool:
        return self.value is not None and self.threshold is not None

    @property
    def breaches_threshold(self) -> bool | None:
        """`None` when there is nothing to compare - never `False` by default."""
        if not self.compared:
            return None
        if self.direction is Direction.HIGHER_IS_WORSE:
            return self.value > self.threshold
        if self.direction is Direction.LOWER_IS_WORSE:
            return self.value < self.threshold
        return None

    @property
    def small_sample(self) -> bool | None:
        if self.sample_size is None or not self.minimum_sample:
            return None
        return self.sample_size < self.minimum_sample

    @property
    def caveat(self) -> str:
        if self.small_sample:
            return SMALL_SAMPLE_CAVEAT.format(
                sample=self.sample_size, minimum=self.minimum_sample
            )
        return ""

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base.update(
            measured=self.measured,
            compared=self.compared,
            breaches_threshold=self.breaches_threshold,
            small_sample=self.small_sample,
        )
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Measurement:
        return cls(
            value=data.get("value"),
            unit=data.get("unit", ""),
            threshold=data.get("threshold"),
            direction=Direction(data.get("direction", Direction.NEITHER.value)),
            sample_size=data.get("sample_size"),
            minimum_sample=data.get("minimum_sample", 0),
        )


@dataclass(frozen=True)
class OrganizationalSignal:
    """One observation about the company, with its evidence and its absences."""

    signal_id: str
    type: SignalType
    subject: str
    subject_kind: SubjectKind
    window: ReviewWindow
    detail: str
    measurement: Measurement = field(default_factory=Measurement)
    evidence: tuple[Evidence, ...] = ()
    missing_measurements: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        assert_record_id(self.signal_id, "signal_id")
        if not isinstance(self.type, SignalType):
            raise OrgIntelligenceError("signal type must be a SignalType")
        if not isinstance(self.subject_kind, SubjectKind):
            raise OrgIntelligenceError("signal subject_kind must be a SubjectKind")
        if not isinstance(self.window, ReviewWindow):
            raise OrgIntelligenceError("signal window must be a ReviewWindow")
        if not isinstance(self.measurement, Measurement):
            raise OrgIntelligenceError("signal measurement must be a Measurement")
        assert_ref(self.subject, f"signal {self.signal_id} subject")
        assert_prose(self.detail, f"signal {self.signal_id} detail")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        object.__setattr__(
            self,
            "missing_measurements",
            text_tuple(self.missing_measurements, "missing_measurements"),
        )
        object.__setattr__(self, "caveats", text_tuple(self.caveats, "caveats"))
        object.__setattr__(
            self,
            "source_refs",
            tuple(assert_ref(item, "signal source_ref") for item in self.source_refs or ()),
        )

        assert_evidence_backed(
            self.evidence,
            f"signal {self.signal_id} evidence",
            "a signal is something that was observed. Without a pointer to the "
            "observation it is a guess wearing a measurement's clothes",
        )
        if not self.measurement.measured and not self.missing_measurements:
            raise OrgIntelligenceError(
                f"signal {self.signal_id}: no value was measured and nothing was named as "
                "missing. Say what could not be counted - an absent number is a fact "
                "about the instruments, not a zero"
            )
        caveat = self.measurement.caveat
        if caveat and caveat not in self.caveats:
            object.__setattr__(self, "caveats", self.caveats + (caveat,))

    @property
    def measured(self) -> bool:
        return self.measurement.measured

    @property
    def breaches_threshold(self) -> bool | None:
        return self.measurement.breaches_threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "type": self.type.value,
            "subject": self.subject,
            "subject_kind": self.subject_kind.value,
            "window": self.window.to_dict(),
            "detail": self.detail,
            "measurement": self.measurement.to_dict(),
            "evidence": [to_jsonable(item) for item in self.evidence],
            "missing_measurements": list(self.missing_measurements),
            "caveats": list(self.caveats),
            "source_refs": list(self.source_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationalSignal:
        return cls(
            signal_id=data["signal_id"],
            type=SignalType(data["type"]),
            subject=data["subject"],
            subject_kind=SubjectKind(data["subject_kind"]),
            window=ReviewWindow.from_dict(data["window"]),
            detail=data["detail"],
            measurement=Measurement.from_dict(data.get("measurement", {})),
            evidence=evidence_tuple(data.get("evidence")),
            missing_measurements=tuple(data.get("missing_measurements", ())),
            caveats=tuple(data.get("caveats", ())),
            source_refs=tuple(data.get("source_refs", ())),
        )


def signals_of(
    signals: tuple[OrganizationalSignal, ...], *types: SignalType
) -> tuple[OrganizationalSignal, ...]:
    """Every signal of one of `types`, in the order given. A filter, not a rank."""
    wanted = frozenset(types)
    return tuple(signal for signal in signals if signal.type in wanted)
