"""The organizational review: what was looked at, when, with which numbers.

## The window is the record's reason for existing

Everything else here could plausibly live as arguments to a function. The window
could not: a review that does not state its period produces findings nobody can
reproduce, compare or retire. Two first-pass rates with the same name and
different periods are two different measurements, and the only defence against
quietly averaging them is that every record in this package carries the interval
it came from and the review says which interval that was.

## Configuration is recorded, not restated

`OrganizationalReview.configuration` is rendered from the policy objects that
actually ran (`common.rendered_configuration`), rather than typed in by the
author. A review that says the recurrence bar was three while the run used four
is worse than a review with no configuration at all, because it looks checkable.

## Exclusions are first-class

`ReviewScope.exclusions` exists so the shape of the sample is visible. A review
of "the company" that quietly skipped the two dormant departments is a review of
something else, and the difference between scoped and complete is the difference
between a finding and a sampling artefact.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from ai_platform.serde import to_jsonable
from knowledge.company_os.records import Evidence

from .common import (
    assert_day,
    assert_evidence_backed,
    assert_prose,
    assert_record_id,
    assert_ref,
    evidence_tuple,
    text_tuple,
)
from .errors import OrgIntelligenceError
from .window import ReviewWindow


@dataclass(frozen=True)
class ReviewScope:
    """What the review covered, and what it deliberately did not."""

    departments: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    workflows: tuple[str, ...] = ()
    exclusions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in ("departments", "roles", "capabilities", "workflows"):
            object.__setattr__(
                self,
                name,
                tuple(assert_ref(item, f"scope {name}") for item in getattr(self, name) or ()),
            )
        object.__setattr__(self, "exclusions", text_tuple(self.exclusions, "scope exclusions"))

    @property
    def is_whole_company(self) -> bool:
        """No department, role, capability or workflow filter was applied."""
        return not (self.departments or self.roles or self.capabilities or self.workflows)

    @property
    def subjects(self) -> tuple[str, ...]:
        return tuple(
            sorted(set(self.departments + self.roles + self.capabilities + self.workflows))
        )

    def to_dict(self) -> dict[str, Any]:
        base = to_jsonable(self)
        base["is_whole_company"] = self.is_whole_company
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewScope:
        return cls(
            departments=tuple(data.get("departments", ())),
            roles=tuple(data.get("roles", ())),
            capabilities=tuple(data.get("capabilities", ())),
            workflows=tuple(data.get("workflows", ())),
            exclusions=tuple(data.get("exclusions", ())),
        )


@dataclass(frozen=True)
class OrganizationalReview:
    """One pass over the organization, bounded in time and in scope."""

    review_id: str
    objective: str
    window: ReviewWindow
    created: dt.date
    reviewer: str
    scope: ReviewScope = field(default_factory=ReviewScope)
    evidence: tuple[Evidence, ...] = ()
    configuration: tuple[tuple[str, str], ...] = ()
    limitations: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_record_id(self.review_id, "review_id")
        assert_prose(self.objective, f"review {self.review_id} objective")
        assert_prose(self.reviewer, f"review {self.review_id} reviewer")
        if not isinstance(self.window, ReviewWindow):
            raise OrgIntelligenceError("review window must be a ReviewWindow")
        if not isinstance(self.scope, ReviewScope):
            raise OrgIntelligenceError("review scope must be a ReviewScope")
        object.__setattr__(self, "created", assert_day(self.created, "review created"))
        object.__setattr__(self, "evidence", evidence_tuple(self.evidence))
        if not isinstance(self.notes, str):
            raise OrgIntelligenceError("review notes must be a string")

        pairs: list[tuple[str, str]] = []
        for item in self.configuration or ():
            if not isinstance(item, tuple) or len(item) != 2:
                raise OrgIntelligenceError(
                    "review configuration is a sequence of (name, value) pairs; use "
                    "common.rendered_configuration so it cannot disagree with the run"
                )
            pairs.append((assert_ref(item[0], "configuration name"), str(item[1])))
        if len({name for name, _ in pairs}) != len(pairs):
            raise OrgIntelligenceError("review configuration names a setting twice")
        object.__setattr__(self, "configuration", tuple(sorted(pairs)))

        if self.created < self.window.start:
            raise OrgIntelligenceError(
                f"review {self.review_id}: created {self.created.isoformat()} before its own "
                f"window opens on {self.window.start.isoformat()}"
            )
        assert_evidence_backed(
            self.evidence,
            f"review {self.review_id} evidence",
            "a review points at what it read - the registries, the records, the reports. "
            "Without that nobody can repeat it",
        )

        limitations = text_tuple(self.limitations, "review limitations")
        if self.window.limitation not in limitations:
            limitations = limitations + (self.window.limitation,)
        if self.scope.exclusions:
            excluded = "excluded from this review: " + "; ".join(self.scope.exclusions)
            if excluded not in limitations:
                limitations = limitations + (excluded,)
        if not self.configuration:
            limitations = limitations + (
                "no thresholds were recorded, so the findings cannot be reproduced against "
                "the configuration that produced them",
            )
        object.__setattr__(self, "limitations", limitations)

    @property
    def configuration_map(self) -> dict[str, str]:
        return {name: value for name, value in self.configuration}

    def to_dict(self) -> dict[str, Any]:
        return {
            "review_id": self.review_id,
            "objective": self.objective,
            "window": self.window.to_dict(),
            "created": self.created.isoformat(),
            "reviewer": self.reviewer,
            "scope": self.scope.to_dict(),
            "evidence": [to_jsonable(item) for item in self.evidence],
            "configuration": [[name, value] for name, value in self.configuration],
            "limitations": list(self.limitations),
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OrganizationalReview:
        return cls(
            review_id=data["review_id"],
            objective=data["objective"],
            window=ReviewWindow.from_dict(data["window"]),
            created=assert_day(data["created"], "created"),
            reviewer=data["reviewer"],
            scope=ReviewScope.from_dict(data.get("scope", {})),
            evidence=evidence_tuple(data.get("evidence")),
            configuration=tuple(
                (item[0], item[1]) for item in data.get("configuration", ())
            ),
            limitations=tuple(data.get("limitations", ())),
            notes=data.get("notes", ""),
        )
