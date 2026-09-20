"""Shadow employment: read, recommend, compare - never write.

A shadow does the incumbent's task alongside the incumbent and its output is
compared rather than shipped. That is the whole mechanism, and it exists so
`permissions.yaml`'s `production_write_requires: [evaluation_pass,
explicit_permission, tests]` has something to be satisfied *by*.

## Three refusals at construction

`ShadowAssignment` will not be built with a non-empty `may_write`, with
`production_write` anything but `False`, or with an autonomy level above the
shadow cap in `permissions.yaml`. All three are checked when the record is
made, not when it is used: an assignment that merely *describes* production
write is a document that will eventually be handed to something that acts on it.

The paths a shadow may read are a list, because minimum relevant context
(constitution rule 5) applies to an evaluation as much as to a task.

## Compatible with SessionPacket, deliberately not wired to it

`session_packet_ref` is a reference slot and nothing in this module imports
`company.runtime.packets`. The external session boundary is another workstream's
path; when the two meet, a shadow run becomes a packet whose scope is this
assignment's `may_read` and whose write scope is empty, and the only change here
is that something fills in the ref. Wiring execution now would put two
workstreams in the same file for no capability gained today.

## The comparison records dimensions, not a score

`ShadowComparison.verdict` is one of four words and the dimensions carry the
detail. There is no aggregate number, for the reason in
`performance.py`: a shadow can be better at architecture and worse at visual
review in the same run, and one number would erase exactly the information the
hiring decision needs.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_identifier,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    id_tuple,
    optional_ref,
    text_tuple,
)
from .employment import (
    PRODUCTION_WRITE_ACTIONS,
    EmploymentState,
    assert_authority,
    assert_may_not_write_production,
)
from .errors import AuthorityViolation, WorkforceError


class ComparisonVerdict(Enum):
    CANDIDATE_BETTER = "candidate_better"
    EQUIVALENT = "equivalent"
    BASELINE_BETTER = "baseline_better"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class ShadowAssignment:
    """One shadow run: what it may read, what it compares against, and no writes."""

    assignment_id: str
    candidate_id: str
    baseline_employee_id: str
    task_ref: str
    capabilities: tuple[str, ...]
    may_read: tuple[str, ...]
    objective: str
    assigned_on: dt.date
    may_write: tuple[str, ...] = ()
    may_recommend: bool = True
    autonomy_level: int = 1
    production_write: bool = False
    session_packet_ref: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.assignment_id, "assignment_id")
        assert_identifier(self.candidate_id, "candidate_id")
        assert_identifier(self.baseline_employee_id, "baseline_employee_id")
        assert_ref(self.task_ref, "shadow task_ref")
        assert_prose(self.objective, "shadow objective")
        object.__setattr__(
            self, "assigned_on", assert_day(self.assigned_on, "shadow assigned_on")
        )
        object.__setattr__(
            self, "capabilities", id_tuple(self.capabilities, "shadow capabilities", sort=True)
        )
        object.__setattr__(self, "may_read", text_tuple(self.may_read, "shadow may_read"))
        object.__setattr__(self, "may_write", text_tuple(self.may_write, "shadow may_write"))
        object.__setattr__(
            self,
            "session_packet_ref",
            optional_ref(self.session_packet_ref, "session_packet_ref"),
        )
        if not self.capabilities:
            raise WorkforceError(
                f"shadow {self.assignment_id}: name the capabilities being evaluated, or the "
                "comparison proves nothing in particular"
            )
        if not self.may_read:
            raise WorkforceError(
                f"shadow {self.assignment_id}: a shadow that may read nothing cannot work"
            )
        if self.candidate_id == self.baseline_employee_id:
            raise WorkforceError(
                f"shadow {self.assignment_id}: the candidate cannot be its own baseline"
            )
        for name in ("may_recommend", "production_write"):
            if not isinstance(getattr(self, name), bool):
                raise WorkforceError(f"shadow {name} must be a bool")
        if not isinstance(self.notes, str):
            raise WorkforceError("shadow notes must be a string")

        if self.production_write is not False:
            raise AuthorityViolation(
                f"shadow {self.assignment_id}: production_write must be False. A shadow "
                "reads, recommends and is compared; it does not ship"
            )
        if self.may_write:
            raise AuthorityViolation(
                f"shadow {self.assignment_id}: may_write must be empty, got "
                + ", ".join(self.may_write)
                + ". Shadow output is compared against the incumbent, not merged"
            )
        assert_may_not_write_production(
            EmploymentState.SHADOW, tuple(self.may_write) + tuple(self.capabilities)
        )

    def check_authority(self, permissions: dict[str, Any]) -> None:
        """Verify the level against permissions.yaml. Separate because it needs them."""
        assert_authority(EmploymentState.SHADOW, self.autonomy_level, permissions)

    @property
    def grants_production_write(self) -> bool:
        return False

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShadowAssignment:
        return cls(
            assignment_id=data["assignment_id"],
            candidate_id=data["candidate_id"],
            baseline_employee_id=data["baseline_employee_id"],
            task_ref=data["task_ref"],
            capabilities=tuple(data["capabilities"]),
            may_read=tuple(data["may_read"]),
            objective=data["objective"],
            assigned_on=assert_day(data["assigned_on"], "assigned_on"),
            may_write=tuple(data.get("may_write", ())),
            may_recommend=data.get("may_recommend", True),
            autonomy_level=data.get("autonomy_level", 1),
            production_write=data.get("production_write", False),
            session_packet_ref=data.get("session_packet_ref", ""),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class ComparisonDimension:
    """One named axis the two results were compared on."""

    name: str
    candidate: str
    baseline: str
    verdict: ComparisonVerdict
    note: str = ""

    def __post_init__(self) -> None:
        assert_identifier(self.name, "comparison dimension name")
        assert_prose(self.candidate, f"{self.name} candidate result")
        assert_prose(self.baseline, f"{self.name} baseline result")
        if not isinstance(self.verdict, ComparisonVerdict):
            raise WorkforceError("dimension verdict must be a ComparisonVerdict")
        if not isinstance(self.note, str):
            raise WorkforceError("dimension note must be a string")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ComparisonDimension:
        return cls(
            name=data["name"],
            candidate=data["candidate"],
            baseline=data["baseline"],
            verdict=ComparisonVerdict(data["verdict"]),
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class ShadowComparison:
    """What the shadow run showed, per dimension, with pointers to both results."""

    comparison_id: str
    assignment_id: str
    candidate_result_ref: str
    baseline_result_ref: str
    verdict: ComparisonVerdict
    evaluator: str
    on: dt.date
    dimensions: tuple[ComparisonDimension, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    candidate_usage_ref: str = ""
    baseline_usage_ref: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.comparison_id, "comparison_id")
        assert_record_id(self.assignment_id, "assignment_id")
        assert_ref(self.candidate_result_ref, "candidate_result_ref")
        assert_ref(self.baseline_result_ref, "baseline_result_ref")
        assert_prose(self.evaluator, "comparison evaluator")
        object.__setattr__(self, "on", assert_day(self.on, "comparison date"))
        if not isinstance(self.verdict, ComparisonVerdict):
            raise WorkforceError("comparison verdict must be a ComparisonVerdict")
        if not isinstance(self.dimensions, tuple) or any(
            not isinstance(item, ComparisonDimension) for item in self.dimensions
        ):
            raise WorkforceError("dimensions must be a tuple of ComparisonDimension")
        names = [dimension.name for dimension in self.dimensions]
        if len(set(names)) != len(names):
            raise WorkforceError("a comparison dimension may only be judged once")
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        for name in ("candidate_usage_ref", "baseline_usage_ref"):
            object.__setattr__(self, name, optional_ref(getattr(self, name), name))
        if not isinstance(self.notes, str):
            raise WorkforceError("comparison notes must be a string")
        if self.verdict is not ComparisonVerdict.INCONCLUSIVE and not self.dimensions:
            raise WorkforceError(
                f"comparison {self.comparison_id}: a verdict of {self.verdict.value!r} needs "
                "at least one named dimension. An unexplained verdict is a preference"
            )

    def dimension(self, name: str) -> ComparisonDimension:
        for dimension in self.dimensions:
            if dimension.name == name:
                return dimension
        raise WorkforceError(f"{name!r} was not compared in {self.comparison_id}")

    @property
    def stronger_dimensions(self) -> tuple[str, ...]:
        return tuple(
            d.name for d in self.dimensions if d.verdict is ComparisonVerdict.CANDIDATE_BETTER
        )

    @property
    def weaker_dimensions(self) -> tuple[str, ...]:
        return tuple(
            d.name for d in self.dimensions if d.verdict is ComparisonVerdict.BASELINE_BETTER
        )

    def as_evidence(self) -> Evidence:
        """The `shadow_comparison` evidence the probation -> active gate requires."""
        return Evidence(
            kind="shadow_comparison",
            ref=self.comparison_id,
            note=f"{self.verdict.value} over {len(self.dimensions)} dimension(s)",
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ShadowComparison:
        return cls(
            comparison_id=data["comparison_id"],
            assignment_id=data["assignment_id"],
            candidate_result_ref=data["candidate_result_ref"],
            baseline_result_ref=data["baseline_result_ref"],
            verdict=ComparisonVerdict(data["verdict"]),
            evaluator=data["evaluator"],
            on=assert_day(data["on"], "on"),
            dimensions=tuple(
                ComparisonDimension.from_dict(item) for item in data.get("dimensions", ())
            ),
            evidence=evidence_tuple(data.get("evidence")),
            candidate_usage_ref=data.get("candidate_usage_ref", ""),
            baseline_usage_ref=data.get("baseline_usage_ref", ""),
            notes=data.get("notes", ""),
        )


def shadow_scope_violations(
    assignment: ShadowAssignment, requested_writes: tuple[str, ...]
) -> tuple[str, ...]:
    """Paths or actions a shadow run tried to write that it may not.

    Reports instead of raising, so a review can list everything a run attempted
    rather than stopping at the first one. Everything is a violation: the
    shadow's write scope is empty by construction.
    """
    out = [
        f"{assignment.assignment_id}: shadow attempted to write {item!r}"
        for item in requested_writes
    ]
    forbidden = PRODUCTION_WRITE_ACTIONS.intersection(requested_writes)
    out.extend(
        f"{assignment.assignment_id}: shadow attempted production authority {item!r}"
        for item in sorted(forbidden)
    )
    return tuple(out)
