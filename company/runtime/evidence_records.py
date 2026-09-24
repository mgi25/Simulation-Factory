"""Typed execution evidence with a deterministic identity per event.

An attempt produces a stream of things that happened: suites ran, a commit was
made, a gate was evaluated, a reviewer answered, a measurement was taken. Today
each of those is recorded in its own shape by whichever module made it, and
nothing they produce has a stable per-event identifier - which is why a
resource record cannot be joined to the run that caused it, and why the same
event arriving twice cannot be recognised as the same event.

This module is the one typed shape for all of them, and the identity rule is
the point of it.

## Why the identity is derived and not allocated

A UUID is unique and says nothing. Two records for the same observation get two
ids, so a retry, a replay or a re-export silently doubles the evidence. So
`record_id` is a fingerprint over the record's own **semantic** fields, and a
re-derivation of the same observation produces the same id.

## Why `sequence` is part of the identity anyway

Pure content-addressing has the opposite failure: two genuinely distinct events
that happen to describe the same thing - the same suite run twice in one
attempt, once before the fix and once after - would collide into one record and
one of them would vanish. `sequence` is the caller's monotonic counter within
an attempt, and it is inside the identity precisely so that "the same thing
observed twice" stays two records while "the same observation re-derived"
stays one.

## Why `duration_s` is not part of the identity

Because it is a measurement of the machine, not of the event. Including it
would make a re-run of an identical, deterministic observation produce a
different id every time - which is the same failure as a UUID, arrived at by
accident. Volatile fields are carried, reported and excluded from
`identity()`; `payload_digest` carries the rest of the detail without
letting it move the id.

## Why the ledger is append-only and refuses a contradiction

`EvidenceLedger.add` refuses a second record with the same `record_id` and a
different body. That is the one check that makes a derived id useful: an id
that can be re-derived is only trustworthy if the thing behind it cannot change
underneath. Re-adding a byte-identical record is a no-op, so an idempotent
re-export is free.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, fingerprint, to_jsonable

from .errors import LifecycleError


EVIDENCE_RECORD_VERSION = 1

_MAX_DETAIL_CHARS = 2000


class ExecutionEvidenceKind(Enum):
    """What kind of thing was observed. One value per shape of evidence."""

    SUITE_RUN = "suite_run"
    COMMAND = "command"
    GIT_STATE = "git_state"
    GATE_REPORT = "gate_report"
    REVIEW = "review"
    MEASUREMENT = "measurement"
    CONTEXT_ASSEMBLY = "context_assembly"


class EvidenceOutcome(Enum):
    """The verdict, including the one that blocks.

    `UNKNOWN` exists for the same reason it exists in the integration gate: an
    observation that could not be made must not be recordable as a pass.
    """

    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"

    @property
    def satisfies(self) -> bool:
        return self is EvidenceOutcome.PASS


@dataclass(frozen=True)
class ExecutionEvidence:
    """One recorded observation from one attempt, with a re-derivable identity."""

    kind: ExecutionEvidenceKind
    subject: str
    outcome: EvidenceOutcome
    observed_on: dt.date
    reported_by: str
    attempt_id: str
    sequence: int
    commit: str = ""
    detail: str = ""
    payload_digest: str = ""
    duration_s: float = 0.0
    selected: int = 0
    failed: int = 0

    def __post_init__(self) -> None:
        for name, enum_type in (("kind", ExecutionEvidenceKind), ("outcome", EvidenceOutcome)):
            if not isinstance(getattr(self, name), enum_type):
                raise LifecycleError(f"execution evidence {name} must be a {enum_type.__name__}")
        object.__setattr__(self, "subject", assert_reference(self.subject, "subject"))
        object.__setattr__(
            self, "reported_by", assert_reference(self.reported_by, "reported_by")
        )
        object.__setattr__(
            self, "attempt_id", assert_reference(self.attempt_id, "attempt_id")
        )
        object.__setattr__(self, "observed_on", as_date(self.observed_on, "observed_on"))
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int):
            raise LifecycleError(f"{self.subject}: sequence must be an integer")
        if self.sequence < 0:
            raise LifecycleError(f"{self.subject}: sequence must not be negative")
        if self.commit:
            assert_reference(self.commit, f"{self.subject} commit")
        if self.detail:
            assert_text(self.detail, f"{self.subject} detail")
            if len(self.detail) > _MAX_DETAIL_CHARS:
                raise LifecycleError(
                    f"{self.subject}: {len(self.detail)} characters of detail exceeds "
                    f"the {_MAX_DETAIL_CHARS} a record may carry. Store the body and "
                    "reference it; payload_digest is the pointer."
                )
        if self.payload_digest and len(self.payload_digest) not in (16, 64):
            raise LifecycleError(
                f"{self.subject}: payload_digest is a fingerprint (16) or a full "
                f"SHA-256 (64), not {len(self.payload_digest)} characters"
            )
        for name in ("selected", "failed"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise LifecycleError(f"{self.subject}: {name} must be a non-negative integer")
        if isinstance(self.duration_s, bool) or not isinstance(self.duration_s, (int, float)):
            raise LifecycleError(f"{self.subject}: duration_s must be a number")
        if self.duration_s < 0:
            raise LifecycleError(f"{self.subject}: duration_s must not be negative")
        if self.outcome is EvidenceOutcome.PASS and self.failed:
            raise LifecycleError(
                f"{self.subject}: recorded as passing with {self.failed} failure(s). "
                "An observation is green or it is not."
            )
        if self.outcome is EvidenceOutcome.UNKNOWN and not self.detail:
            raise LifecycleError(
                f"{self.subject}: an unknown outcome must say what could not be "
                "observed; an unexplained unknown is a shrug"
            )

    # -- identity ---------------------------------------------------------

    def identity(self) -> dict[str, Any]:
        """The semantic fields. Volatile measurements are deliberately absent.

        `duration_s` is excluded - it describes the machine, not the event.
        `selected`/`failed` are included: they are what was observed, and two
        runs of one suite that disagree about them are two different facts.
        """
        return {
            "version": EVIDENCE_RECORD_VERSION,
            "kind": self.kind.value,
            "subject": self.subject,
            "outcome": self.outcome.value,
            "observed_on": self.observed_on.isoformat(),
            "reported_by": self.reported_by,
            "attempt_id": self.attempt_id,
            "sequence": self.sequence,
            "commit": self.commit,
            "payload_digest": self.payload_digest,
            "selected": self.selected,
            "failed": self.failed,
        }

    def record_id(self) -> str:
        """A re-derivable identifier for this exact observation."""
        return fingerprint(self.identity())

    def reference(self) -> str:
        return f"{self.kind.value}:{self.subject} {self.outcome.value} at {self.observed_on.isoformat()}"

    def to_dict(self) -> dict[str, Any]:
        return {**to_jsonable(self), "record_id": self.record_id()}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ExecutionEvidence":
        if not isinstance(data, Mapping):
            raise LifecycleError("execution evidence is read from a mapping")
        known = set(cls.__dataclass_fields__) | {"record_id"}
        unknown = sorted(set(data) - known)
        if unknown:
            raise LifecycleError(
                "execution evidence has unknown field(s): "
                + ", ".join(unknown)
                + ". Records are read against a fixed schema so an unexpected key "
                "cannot quietly change what was claimed."
            )
        record = cls(
            kind=ExecutionEvidenceKind(str(data.get("kind", ""))),
            subject=str(data.get("subject", "")),
            outcome=EvidenceOutcome(str(data.get("outcome", ""))),
            observed_on=as_date(data.get("observed_on"), "observed_on"),
            reported_by=str(data.get("reported_by", "")),
            attempt_id=str(data.get("attempt_id", "")),
            sequence=int(data.get("sequence", 0)),
            commit=str(data.get("commit", "")),
            detail=str(data.get("detail", "")),
            payload_digest=str(data.get("payload_digest", "")),
            duration_s=float(data.get("duration_s", 0.0)),
            selected=int(data.get("selected", 0)),
            failed=int(data.get("failed", 0)),
        )
        supplied = str(data.get("record_id", ""))
        if supplied and supplied != record.record_id():
            raise LifecycleError(
                f"{record.subject}: the supplied record_id {supplied} does not match "
                f"the one its own fields derive ({record.record_id()}). The id is "
                "derived so it can be checked; a mismatch is a changed record."
            )
        return record


@dataclass
class EvidenceLedger:
    """Append-only typed evidence for one attempt, addressed by derived id."""

    attempt_id: str
    records: dict[str, ExecutionEvidence] = field(default_factory=dict)

    def __post_init__(self) -> None:
        assert_reference(self.attempt_id, "ledger attempt_id")

    def __len__(self) -> int:
        return len(self.records)

    def __iter__(self):
        return iter(self.ordered())

    def __contains__(self, record_id: object) -> bool:
        return record_id in self.records

    def add(self, record: ExecutionEvidence) -> str:
        """Append a record and return its id. Idempotent; refuses a rewrite."""
        if not isinstance(record, ExecutionEvidence):
            raise LifecycleError("an evidence ledger holds ExecutionEvidence values")
        if record.attempt_id != self.attempt_id:
            raise LifecycleError(
                f"this ledger is for attempt {self.attempt_id!r} and the record is "
                f"for {record.attempt_id!r}; evidence from another attempt describes "
                "another run"
            )
        record_id = record.record_id()
        existing = self.records.get(record_id)
        if existing is not None and existing != record:
            raise LifecycleError(
                f"{record_id}: a record with this identity is already held and its "
                "body differs. A derived id is only useful while what is behind it "
                "cannot change; store the new observation with the next sequence."
            )
        self.records[record_id] = record
        return record_id

    def extend(self, records: Iterable[ExecutionEvidence]) -> tuple[str, ...]:
        return tuple(self.add(record) for record in records)

    def get(self, record_id: str) -> ExecutionEvidence | None:
        return self.records.get(record_id)

    def ordered(self) -> tuple[ExecutionEvidence, ...]:
        """Records in a stable order: sequence, then kind, then subject."""
        return tuple(
            sorted(
                self.records.values(),
                key=lambda r: (r.sequence, r.kind.value, r.subject),
            )
        )

    def of_kind(self, kind: ExecutionEvidenceKind) -> tuple[ExecutionEvidence, ...]:
        return tuple(r for r in self.ordered() if r.kind is kind)

    def failures(self) -> tuple[ExecutionEvidence, ...]:
        return tuple(r for r in self.ordered() if r.outcome is EvidenceOutcome.FAIL)

    def unknowns(self) -> tuple[ExecutionEvidence, ...]:
        return tuple(r for r in self.ordered() if r.outcome is EvidenceOutcome.UNKNOWN)

    def complete(self) -> bool:
        """True only when nothing is failing and nothing is unobserved."""
        return not self.failures() and not self.unknowns()

    def fingerprint(self) -> str:
        return fingerprint([record.identity() for record in self.ordered()])

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "fingerprint": self.fingerprint(),
            "records": [record.to_dict() for record in self.ordered()],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EvidenceLedger":
        ledger = cls(attempt_id=str(data.get("attempt_id", "")))
        entries = data.get("records", ())
        if isinstance(entries, (str, bytes)) or not isinstance(entries, (list, tuple)):
            raise LifecycleError("an evidence ledger is read from a list of records")
        ledger.extend(ExecutionEvidence.from_dict(entry) for entry in entries)
        return ledger


__all__ = [
    "EVIDENCE_RECORD_VERSION",
    "ExecutionEvidenceKind",
    "EvidenceLedger",
    "EvidenceOutcome",
    "ExecutionEvidence",
]
