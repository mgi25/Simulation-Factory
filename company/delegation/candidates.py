"""Work the company knows about but has not chosen: the candidate register.

A candidate is the rung the first live-delegation pilot found missing. Company
OS could already turn *a task stated as a sentence* into a governed work order,
and could govern every stage after that. It had nothing to turn *an objective*
into a task, because it held no record of what work was worth doing. The
objective ladder in `objectives.py` declares the rung; this module fills it.

```
evidence a human already wrote down
    -> WorkCandidate            (this module: known, not chosen)
    -> planning decision        (planning.py: chosen, and why)
    -> work order               (company/engineering/intake.py: bounded)
```

## A candidate is not a work order, and the difference is the whole point

A work order carries authority: a scope somebody may write to, a budget
somebody may spend, an attempt somebody may take. A candidate carries none of
it. It is a claim that a piece of work exists and is worth considering, with
the evidence for that claim attached. Registering one authorizes nothing, costs
nothing and commits nobody, which is exactly why a register is safe to keep
broad while a work order must be kept narrow.

## Why evidence is required at construction

`docs/company_os_first_live_delegation_pilot.md` recorded that `evidence_refs`
elsewhere in the delegation package are hardcoded document paths that no module
ever opens - citations rather than evidence. That is tolerable for a scenario
fixture and intolerable here, because a register nobody can trace is a wish
list, and a wish list is how a company invents work for itself.

So `source_type` and `source_ref` are required, `evidence_refs` must be
non-empty, and `problem_statement` must be falsifiable by the same structural
test a work order's acceptance criteria face
(`company.engineering.criteria`). A candidate that cannot say what is wrong in
checkable terms is refused at construction rather than filtered later.

**This module still does not read the documents it cites.** It cannot: reading
a repository and deciding a sentence describes real work is discovery, which is
a separate capability with a separate contract at the bottom of this file. What
construction guarantees is that a human or a future discovery capability named
a source, and that the name is recorded next to the claim.

## Why status is a field and history is append-only

A candidate moves OPEN -> SELECTED -> COMPLETED, or sideways into DEFERRED,
BLOCKED or SUPERSEDED. None of those is an edit. `with_status` returns a new
record and `DelegationStore.append_candidate` writes it as the next version, so
"why did this stop being eligible" is answerable by listing a directory. The
register resolves the latest version per id when it is built.

## The states, and the two that are refusals rather than pauses

    OPEN        eligible for selection, if the constraints also pass
    SELECTED    a planning decision chose it; not selectable again
    DEFERRED    real work, consciously not now, with a reason
    BLOCKED     cannot proceed until something else does - and `blocked_by`
                must say what. A policy decision, a design decision and an
                unsatisfied dependency are all blockers, and none of them is
                an engineering task that a developer could pick up.
    SUPERSEDED  a later candidate replaced it; `superseded_by` must name it
    COMPLETED   the work happened

`BLOCKED` and `DEFERRED` exist so that honest classification has somewhere to
go. The temptation a register creates is to mark everything OPEN so the
company always looks like it has work; the constructor refusing a BLOCKED
candidate with no blocker is the smallest available guard against that.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.efficiency.profile import resource_profile
from company.engineering.criteria import is_falsifiable_criterion
from company.finance.money import Money

from .actions import ActionType, parse_action
from .common import (
    assert_day,
    assert_prose,
    assert_record_id,
    name_tuple,
    ref_tuple,
    text_tuple,
)
from .errors import DelegationError
from .policy import parse_risk


class CandidateStatus(str, Enum):
    """Where a candidate stands. Only OPEN is selectable."""

    OPEN = "open"
    SELECTED = "selected"
    DEFERRED = "deferred"
    BLOCKED = "blocked"
    SUPERSEDED = "superseded"
    COMPLETED = "completed"


SELECTABLE: frozenset[CandidateStatus] = frozenset({CandidateStatus.OPEN})
"""The one status a planner may choose from. Written down so it is checkable."""


class CandidateSource(str, Enum):
    """Where the claim that this work exists came from.

    A closed set, because "somebody thought of it" is not a source and an open
    vocabulary would let it become one.
    """

    REVIEWER_ADVISORY = "reviewer_advisory"
    VALIDATION_REPORT = "validation_report"
    DEFERRED_FOLLOWUP = "deferred_followup"
    KNOWN_DEFECT = "known_defect"
    MAINTENANCE_GAP = "maintenance_gap"
    STOPPED_WORK = "stopped_work"
    BACKLOG_ARTIFACT = "backlog_artifact"


def parse_status(value: Any, field: str = "status") -> CandidateStatus:
    if isinstance(value, CandidateStatus):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be a candidate status name, got {value!r}")
    try:
        return CandidateStatus(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in CandidateStatus)
        raise DelegationError(f"{field} must be one of: {allowed}") from exc


def parse_source(value: Any, field: str = "source_type") -> CandidateSource:
    if isinstance(value, CandidateSource):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be a candidate source name, got {value!r}")
    try:
        return CandidateSource(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in CandidateSource)
        raise DelegationError(
            f"{field}: {value!r} is not a recognised evidence source. Use one of: "
            f"{allowed}. A candidate with no recognised source is a wish, and the "
            "register does not hold wishes."
        ) from exc


@dataclass(frozen=True)
class WorkCandidate:
    """One known, evidence-backed piece of work the company has not chosen."""

    candidate_id: str
    title: str
    description: str
    capsule_id: str
    department: str
    source_type: CandidateSource
    source_ref: str
    problem_statement: str
    expected_value: str
    risk: Risk
    created_at: dt.date
    evidence_refs: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    allowed_write_scope: tuple[str, ...] = ()
    estimated_resource_profile: str = "consumer"
    estimated_cost: Money | None = None
    goal_tags: tuple[str, ...] = ()
    # The action classes doing this work would need approved. Empty means the
    # routine pair every code change needs, which `required_action_set` fills
    # in; naming anything else is how a candidate declares it is not routine.
    required_actions: tuple[ActionType, ...] = ()
    dependencies: tuple[str, ...] = ()
    blocked_by: tuple[str, ...] = ()
    status: CandidateStatus = CandidateStatus.OPEN
    supersedes: str = ""
    superseded_by: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", assert_record_id(self.candidate_id, "candidate_id")
        )
        for field in ("title", "description", "problem_statement", "expected_value"):
            object.__setattr__(
                self, field, assert_prose(getattr(self, field), f"candidate.{field}")
            )
        object.__setattr__(
            self, "capsule_id", assert_record_id(self.capsule_id, "candidate.capsule_id")
        )
        department = assert_prose(self.department, "candidate.department").lower()
        object.__setattr__(self, "department", department)
        object.__setattr__(
            self, "source_type", parse_source(self.source_type, "candidate.source_type")
        )
        object.__setattr__(
            self, "source_ref", assert_prose(self.source_ref, "candidate.source_ref")
        )
        object.__setattr__(self, "risk", parse_risk(self.risk, "candidate.risk"))
        object.__setattr__(
            self, "created_at", assert_day(self.created_at, "candidate.created_at")
        )
        object.__setattr__(
            self,
            "evidence_refs",
            ref_tuple(self.evidence_refs, "candidate.evidence_refs"),
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            text_tuple(self.acceptance_criteria, "candidate.acceptance_criteria", limit=16),
        )
        object.__setattr__(
            self,
            "allowed_write_scope",
            ref_tuple(self.allowed_write_scope, "candidate.allowed_write_scope"),
        )
        object.__setattr__(
            self, "goal_tags", name_tuple(self.goal_tags, "candidate.goal_tags")
        )
        object.__setattr__(
            self,
            "required_actions",
            tuple(
                sorted(
                    {
                        parse_action(item, "candidate.required_actions")
                        for item in (self.required_actions or ())
                    },
                    key=lambda item: item.value,
                )
            ),
        )
        object.__setattr__(
            self, "dependencies", name_tuple(self.dependencies, "candidate.dependencies")
        )
        object.__setattr__(
            self, "blocked_by", text_tuple(self.blocked_by, "candidate.blocked_by", limit=8)
        )
        object.__setattr__(self, "status", parse_status(self.status, "candidate.status"))
        try:
            profile = resource_profile(self.estimated_resource_profile or None)
        except Exception as exc:  # the profile registry owns the vocabulary
            raise DelegationError(
                f"candidate.estimated_resource_profile: {exc}"
            ) from exc
        object.__setattr__(self, "estimated_resource_profile", profile.name.value)
        if self.estimated_cost is not None and not isinstance(self.estimated_cost, Money):
            raise DelegationError("candidate.estimated_cost must be Money or None")
        for field in ("supersedes", "superseded_by", "notes"):
            value = getattr(self, field)
            if not isinstance(value, str):
                raise DelegationError(f"candidate.{field} must be text")
            object.__setattr__(self, field, value.strip())

        # --- the four refusals ---------------------------------------------
        if not self.evidence_refs:
            raise DelegationError(
                f"candidate {self.candidate_id}: evidence_refs is empty. A candidate "
                "with no traceable evidence is a wish, and the register exists so "
                "that the company cannot invent work for itself."
            )
        if not any(
            is_falsifiable_criterion(item) for item in (self.problem_statement,)
        ):
            raise DelegationError(
                f"candidate {self.candidate_id}: problem_statement names no subject a "
                "reviewer could check. Say what is wrong in terms somebody could "
                "confirm or refute, not the direction the fix would move in."
            )
        if self.status is CandidateStatus.BLOCKED and not self.blocked_by:
            raise DelegationError(
                f"candidate {self.candidate_id} is BLOCKED and names no blocker. A "
                "blocked candidate that does not say what it waits for cannot be "
                "unblocked by anyone."
            )
        if self.status is CandidateStatus.SUPERSEDED and not self.superseded_by:
            raise DelegationError(
                f"candidate {self.candidate_id} is SUPERSEDED and names no successor."
            )
        if self.status is CandidateStatus.OPEN and self.blocked_by:
            raise DelegationError(
                f"candidate {self.candidate_id} is OPEN and also names blockers "
                f"({', '.join(self.blocked_by)}). Open means selectable; a candidate "
                "waiting on something is BLOCKED, and calling it open is how a "
                "planner ends up choosing work that cannot start."
            )

    def required_action_set(self) -> tuple[ActionType, ...]:
        """What approving this work would actually take.

        A candidate that declares nothing still needs a work order approved and
        a code change approved; defaulting to the empty set would let a
        candidate pass a forbidden-action check by saying nothing at all.
        """
        if self.required_actions:
            return self.required_actions
        return (ActionType.APPROVE_WORK_ORDER, ActionType.APPROVE_CODE_CHANGE)

    @property
    def selectable(self) -> bool:
        """Status alone. Every other constraint is the planner's to apply."""
        return self.status in SELECTABLE

    def falsifiable_criteria(self) -> tuple[str, ...]:
        """The acceptance criteria a reviewer could actually mark pass or fail."""
        return tuple(
            item for item in self.acceptance_criteria if is_falsifiable_criterion(item)
        )

    def with_status(
        self, status: Any, *, blocked_by: Sequence[str] = (), superseded_by: str = ""
    ) -> "WorkCandidate":
        """The next version of this candidate. Never an edit of this one."""
        new_status = parse_status(status, "status")
        return replace(
            self,
            status=new_status,
            blocked_by=tuple(blocked_by)
            if blocked_by
            else (() if new_status is not CandidateStatus.BLOCKED else self.blocked_by),
            superseded_by=superseded_by or self.superseded_by,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "description": self.description,
            "capsule_id": self.capsule_id,
            "department": self.department,
            "source_type": self.source_type.value,
            "source_ref": self.source_ref,
            "problem_statement": self.problem_statement,
            "expected_value": self.expected_value,
            "risk": self.risk.value,
            "created_at": self.created_at.isoformat(),
            "evidence_refs": list(self.evidence_refs),
            "acceptance_criteria": list(self.acceptance_criteria),
            "allowed_write_scope": list(self.allowed_write_scope),
            "estimated_resource_profile": self.estimated_resource_profile,
            "estimated_cost": (
                self.estimated_cost.to_dict() if self.estimated_cost else None
            ),
            "goal_tags": list(self.goal_tags),
            "required_actions": [item.value for item in self.required_actions],
            "dependencies": list(self.dependencies),
            "blocked_by": list(self.blocked_by),
            "status": self.status.value,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "notes": self.notes,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


def candidate_from(values: Any) -> WorkCandidate:
    """Decode one candidate from a mapping, for a stored or seeded record."""
    if not isinstance(values, Mapping):
        raise DelegationError("a candidate must be a mapping")
    cost_raw = values.get("estimated_cost")
    cost = (
        Money.from_dict(dict(cost_raw), "candidate.estimated_cost")
        if isinstance(cost_raw, Mapping)
        else None
    )
    return WorkCandidate(
        candidate_id=str(values.get("candidate_id", "")),
        title=str(values.get("title", "")),
        description=str(values.get("description", "")),
        capsule_id=str(values.get("capsule_id", "")),
        department=str(values.get("department", "")),
        source_type=values.get("source_type", ""),
        source_ref=str(values.get("source_ref", "")),
        problem_statement=str(values.get("problem_statement", "")),
        expected_value=str(values.get("expected_value", "")),
        risk=values.get("risk", "low"),
        created_at=assert_day(values.get("created_at"), "candidate.created_at"),
        evidence_refs=tuple(values.get("evidence_refs", ())),
        acceptance_criteria=tuple(values.get("acceptance_criteria", ())),
        allowed_write_scope=tuple(values.get("allowed_write_scope", ())),
        estimated_resource_profile=str(
            values.get("estimated_resource_profile", "consumer")
        ),
        estimated_cost=cost,
        goal_tags=tuple(values.get("goal_tags", ())),
        required_actions=tuple(values.get("required_actions", ())),
        dependencies=tuple(values.get("dependencies", ())),
        blocked_by=tuple(values.get("blocked_by", ())),
        status=values.get("status", "open"),
        supersedes=str(values.get("supersedes", "") or ""),
        superseded_by=str(values.get("superseded_by", "") or ""),
        notes=str(values.get("notes", "") or ""),
    )


def candidates_from(values: Any) -> tuple[WorkCandidate, ...]:
    """Decode a list of candidates, for a seed file or a store listing."""
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise DelegationError("candidates must be a list of mappings")
    return tuple(candidate_from(item) for item in values)


@dataclass(frozen=True)
class CandidateRegister:
    """Every candidate the company holds, latest version of each.

    The register is built from an append-only history, so the same id may
    arrive several times. The last one wins, which is what makes a status
    change a new record rather than an edit.
    """

    candidates: tuple[WorkCandidate, ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.candidates, (str, bytes)) or not isinstance(
            self.candidates, (list, tuple)
        ):
            raise DelegationError("register takes a sequence of candidates")
        latest: dict[str, WorkCandidate] = {}
        for item in self.candidates:
            if not isinstance(item, WorkCandidate):
                raise DelegationError("every register entry must be a WorkCandidate")
            latest[item.candidate_id] = item
        object.__setattr__(
            self,
            "candidates",
            tuple(sorted(latest.values(), key=lambda item: item.candidate_id)),
        )

    def __len__(self) -> int:
        return len(self.candidates)

    def candidate(self, candidate_id: str) -> WorkCandidate | None:
        for item in self.candidates:
            if item.candidate_id == candidate_id:
                return item
        return None

    def open_candidates(self) -> tuple[WorkCandidate, ...]:
        return tuple(item for item in self.candidates if item.selectable)

    def for_capsule(self, capsule_id: str) -> tuple[WorkCandidate, ...]:
        """Every candidate this capsule owns, whatever its status."""
        identity = str(capsule_id).strip()
        return tuple(item for item in self.candidates if item.capsule_id == identity)

    def open_for_capsule(self, capsule_id: str) -> tuple[WorkCandidate, ...]:
        """The question a manager actually asks: what open work does X own?"""
        return tuple(item for item in self.for_capsule(capsule_id) if item.selectable)

    def by_status(self, status: Any) -> tuple[WorkCandidate, ...]:
        wanted = parse_status(status, "status")
        return tuple(item for item in self.candidates if item.status is wanted)

    def capsule_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.capsule_id for item in self.candidates}))

    def violations(self) -> tuple[str, ...]:
        """Contradictions across the register that no single record could see."""
        problems: list[str] = []
        known = {item.candidate_id for item in self.candidates}
        for item in self.candidates:
            for dependency in item.dependencies:
                if dependency not in known:
                    problems.append(
                        f"{item.candidate_id} depends on {dependency}, which the "
                        "register does not hold"
                    )
            if item.superseded_by and item.superseded_by not in known:
                problems.append(
                    f"{item.candidate_id} is superseded by {item.superseded_by}, "
                    "which the register does not hold"
                )
            if item.supersedes and item.supersedes not in known:
                problems.append(
                    f"{item.candidate_id} supersedes {item.supersedes}, which the "
                    "register does not hold"
                )
        return tuple(problems)

    def to_dict(self) -> dict[str, Any]:
        return {"candidates": [item.to_dict() for item in self.candidates]}


def register_from(values: Any) -> CandidateRegister:
    """Build a register from decoded mappings, seed file shape or bare list."""
    if isinstance(values, Mapping):
        values = values.get("candidates", ())
    return CandidateRegister(candidates_from(values))


SEED_PATH = Path(__file__).resolve().parent / "candidate_seeds.json"
"""The candidates the company has written down, shipped beside the policy."""


def load_seed_register(path: str | Path | None = None) -> CandidateRegister:
    """The seeded register, read from JSON.

    Every entry is transcribed from a document already in this repository, and
    the constructor's refusals apply to seeds exactly as to anything else - a
    seed with no evidence, or a BLOCKED seed naming no blocker, fails to load
    rather than being tolerated because it shipped with the package.
    """
    source = Path(path) if path is not None else SEED_PATH
    with open(source, encoding="utf-8") as handle:
        return register_from(json.load(handle))


# --- the discovery boundary ------------------------------------------------
#
# Selection chooses among candidates that exist. Discovery creates new ones.
# They are different capabilities with different risks: selection is bounded by
# the register, and discovery is bounded by nothing until somebody bounds it.
#
# This pass implements selection. What discovery gets here is the narrowest
# contract that lets a future research or planning capability submit a
# candidate without this module growing a repository scanner: one function that
# validates and stamps, and refuses anything that arrives already chosen.


def propose_candidate(
    *,
    candidate_id: str,
    title: str,
    description: str,
    capsule_id: str,
    department: str,
    source_type: Any,
    source_ref: str,
    problem_statement: str,
    expected_value: str,
    risk: Any,
    created_at: dt.date,
    evidence_refs: Sequence[str],
    proposed_by: str,
    acceptance_criteria: Sequence[str] = (),
    allowed_write_scope: Sequence[str] = (),
    estimated_resource_profile: str = "consumer",
    estimated_cost: Money | None = None,
    goal_tags: Sequence[str] = (),
    required_actions: Sequence[Any] = (),
    dependencies: Sequence[str] = (),
    blocked_by: Sequence[str] = (),
    status: Any = CandidateStatus.OPEN,
    supersedes: str = "",
    notes: str = "",
) -> WorkCandidate:
    """The one way a discovery capability adds work to the register.

    It takes a proposer and refuses `SELECTED`. Discovery may say "here is
    work"; only a planning decision may say "we are doing this one", and a
    submission that arrived pre-selected would be a discovery capability
    quietly promoting itself into management.
    """
    who = assert_prose(proposed_by, "proposed_by")
    wanted = parse_status(status, "status")
    if wanted is CandidateStatus.SELECTED:
        raise DelegationError(
            "a proposed candidate may not arrive SELECTED. Discovery finds work; "
            "selecting it is a planning decision recorded by "
            "company/delegation/planning.py, and collapsing the two would let the "
            "capability that invents work also choose it."
        )
    note = notes.strip()
    stamped = f"proposed_by {who}" if not note else f"{note} (proposed_by {who})"
    return WorkCandidate(
        candidate_id=candidate_id,
        title=title,
        description=description,
        capsule_id=capsule_id,
        department=department,
        source_type=source_type,
        source_ref=source_ref,
        problem_statement=problem_statement,
        expected_value=expected_value,
        risk=risk,
        created_at=created_at,
        evidence_refs=tuple(evidence_refs),
        acceptance_criteria=tuple(acceptance_criteria),
        allowed_write_scope=tuple(allowed_write_scope),
        estimated_resource_profile=estimated_resource_profile,
        estimated_cost=estimated_cost,
        goal_tags=tuple(goal_tags),
        required_actions=tuple(required_actions),
        dependencies=tuple(dependencies),
        blocked_by=tuple(blocked_by),
        status=wanted,
        supersedes=supersedes,
        notes=stamped,
    )


__all__ = [
    "SELECTABLE",
    "CandidateRegister",
    "CandidateSource",
    "CandidateStatus",
    "WorkCandidate",
    "candidate_from",
    "candidates_from",
    "parse_source",
    "parse_status",
    "propose_candidate",
    "SEED_PATH",
    "load_seed_register",
    "register_from",
]
