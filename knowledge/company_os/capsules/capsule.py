"""One capsule: what a session needs to work inside a boundary, and nothing else.

A future session asked to change `company/runtime/routing.py` has two ways to
learn what it may touch. It can read `company/`, `ai_platform/`, the tests and
the constitution - four thousand lines to establish six facts - or it can read
one capsule. This module is the second thing.

## What a capsule is

A boundary, described by pointers. Who owns it, what it is for, what goes in
and comes out, what it depends on, what must stay true, what it may read and
write, what it must never modify, which tests cover it, what is known to be
risky about it, and which knowledge records already decided things about it.

Every one of those is a line or a pointer. The capsule never carries the
contents of what it names, and `budget.py` makes that a construction error
rather than a convention.

## Four types, no hierarchy

`MODULE`, `SYSTEM`, `POLICY`, `PROJECT` are one dataclass and an enum, because
the alternative - a base class and four subclasses - would buy polymorphism
nobody calls and cost a reader one indirection per field. What the types do
differ in is what they must declare, and that lives in one table,
`_TYPE_REQUIREMENTS`, four rows long:

    MODULE   owns paths, and names a test. Code with no test reference is code
             the next session cannot verify it did not break.
    SYSTEM   names dependencies. A system with no parts is a module.
    POLICY   states invariants. A policy that constrains nothing is prose.
    PROJECT  owns paths. A project with no place in the repository is a plan.

## Knowledge links point at facts and decisions, never hypotheses

The four link fields are `facts`, `decisions`, `experiment_learnings` and
`failure_learnings`. There is deliberately no `hypotheses` field: a capsule is
handed to a session as authoritative context, and an open hypothesis is the one
record type that is explicitly not authoritative (constitution rule 16). A
guess that has earned its place goes through `promote()` and arrives as a fact.

For the same reason there is no prose "key decisions" field beside the
`decisions` id list. Rule 15 stores a canonical fact once; a summary of a
decision record inside a capsule is a second copy that will drift from the
first, and the drift is invisible because both look authoritative.

## Freshness

A capsule carries `last_reviewed` as well as `created`, and its recheck date is
derived from the review, because the question a capsule has to answer is "was
this checked against the code recently?" and not "when was it first written?".
The staleness arithmetic itself is the store's, unchanged - see
`knowledge/company_os/freshness.py`.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from enum import Enum
from typing import Any, ClassVar, Mapping

from ai_platform.serde import as_date, as_opt_date, as_tuple, dumps
from knowledge.company_os.capsules.budget import (
    DEFAULT_BUDGET,
    CapsuleBudget,
    CapsuleError,
    assert_line,
    assert_list,
    assert_pointer,
    assert_tag,
)
from knowledge.company_os.freshness import Freshness, default_recheck_on, is_stale
from knowledge.company_os.records import ID_PATTERN, RecordStatus


class CapsuleType(Enum):
    MODULE = "module"
    SYSTEM = "system"
    POLICY = "policy"
    PROJECT = "project"


# Type -> (the field it must fill, why). Four rows, checked in `__post_init__`.
# A fifth type means a fifth row, not a fifth class.
_TYPE_REQUIREMENTS: dict[CapsuleType, tuple[str, str]] = {
    CapsuleType.MODULE: (
        "owns_paths",
        "a module capsule must own at least one path, or it describes nothing",
    ),
    CapsuleType.SYSTEM: (
        "dependencies",
        "a system capsule must name its parts as capsule ids; a system with no "
        "parts is a module",
    ),
    CapsuleType.POLICY: (
        "invariants",
        "a policy capsule must state at least one invariant; a policy that "
        "constrains nothing is prose",
    ),
    CapsuleType.PROJECT: (
        "owns_paths",
        "a project capsule must own at least one path; a project with no place "
        "in the repository is a plan",
    ),
}

# MODULE is the one type with a second requirement: it must name a test.
_MODULE_REQUIRES_TEST = (
    "a module capsule must reference at least one test - a boundary nobody can "
    "check is a boundary the next session will cross without noticing"
)

# The knowledge link fields, paired with the record kind they resolve against.
KNOWLEDGE_FIELDS: tuple[tuple[str, str], ...] = (
    ("facts", "fact"),
    ("decisions", "decision"),
    ("experiment_learnings", "experiment_learning"),
    ("failure_learnings", "failure_learning"),
)

# The pointer-shaped fields, in the order `references()` returns them.
POINTER_FIELDS: tuple[str, ...] = (
    "owns_paths",
    "may_read",
    "may_write",
    "must_not_modify",
    "tests",
    "benchmarks",
    "dependencies",
    "facts",
    "decisions",
    "experiment_learnings",
    "failure_learnings",
)

# The one-line prose lists.
STATEMENT_FIELDS: tuple[str, ...] = ("inputs", "outputs", "invariants", "risks")

# Path-shaped fields, held to the larger `max_paths` allowance.
_PATH_FIELDS: tuple[str, ...] = ("owns_paths", "may_read", "may_write", "must_not_modify")


@dataclass(frozen=True)
class SourceDigest:
    """A path and the digest it had when the capsule was last reviewed.

    The capsule records what it was checked against. Comparing that with a
    digest observed later is how "its source path changed" becomes a fact
    rather than a feeling - see `Capsule.changed_sources`. Computing the
    observed digest is the caller's job, deliberately: this layer does not read
    the repository and does not shell out to git.
    """

    path: str
    digest: str

    def __post_init__(self) -> None:
        assert_pointer(self.path, "source_digest path")
        assert_line(self.digest, "source_digest digest", 128)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceDigest:
        return cls(path=data["path"], digest=data["digest"])


@dataclass(frozen=True)
class Capsule:
    """A bounded, authoritative, deliberately small description of one thing."""

    kind: ClassVar[str] = "capsule"

    id: str
    type: CapsuleType
    title: str
    purpose: str
    owner: str
    source: str
    created: dt.date
    last_reviewed: dt.date

    capabilities: tuple[str, ...] = ()
    owns_paths: tuple[str, ...] = ()
    may_read: tuple[str, ...] = ()
    may_write: tuple[str, ...] = ()
    must_not_modify: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()  # capsule ids, resolved by CapsuleIndex
    invariants: tuple[str, ...] = ()
    risks: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()
    benchmarks: tuple[str, ...] = ()
    facts: tuple[str, ...] = ()
    decisions: tuple[str, ...] = ()
    experiment_learnings: tuple[str, ...] = ()
    failure_learnings: tuple[str, ...] = ()
    source_digests: tuple[SourceDigest, ...] = ()

    freshness: Freshness = Freshness.SLOW_CHANGING
    recheck_on: dt.date | None = None
    status: RecordStatus = RecordStatus.ACTIVE
    revalidation_reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not ID_PATTERN.match(self.id):
            raise CapsuleError(
                f"capsule id {self.id!r} must be lowercase [a-z0-9._-], start "
                "alphanumeric, and be at most 80 characters - ids are also filenames"
            )
        if not isinstance(self.type, CapsuleType):
            raise CapsuleError(f"capsule {self.id!r}: type must be a CapsuleType")

        budget = DEFAULT_BUDGET
        assert_line(self.title, f"{self.id} title", budget.max_title_chars)
        assert_line(self.purpose, f"{self.id} purpose", budget.max_purpose_chars)
        assert_line(self.owner, f"{self.id} owner", budget.max_owner_chars)
        assert_line(self.source, f"{self.id} source", budget.max_owner_chars)

        assert_list(self.capabilities, f"{self.id}.capabilities", budget.max_list_items, assert_tag)
        for field in _PATH_FIELDS:
            assert_list(getattr(self, field), f"{self.id}.{field}", budget.max_paths, assert_pointer)
        for field in ("tests", "benchmarks", "dependencies"):
            assert_list(
                getattr(self, field), f"{self.id}.{field}", budget.max_list_items, assert_pointer
            )
        for field in STATEMENT_FIELDS:
            assert_list(
                getattr(self, field),
                f"{self.id}.{field}",
                budget.max_list_items,
                assert_line,
                budget.max_statement_chars,
            )
        for field, _kind in KNOWLEDGE_FIELDS:
            assert_list(
                getattr(self, field), f"{self.id}.{field}", budget.max_list_items, assert_pointer
            )

        links = self.knowledge_links()
        if len(links) > budget.max_knowledge_links:
            raise CapsuleError(
                f"{self.id}: {len(links)} knowledge links exceeds the "
                f"{budget.max_knowledge_links} a capsule may carry"
            )

        if self.id in self.dependencies:
            raise CapsuleError(f"{self.id}: a capsule cannot depend on itself")
        if self.last_reviewed < self.created:
            raise CapsuleError(
                f"{self.id}: last_reviewed {self.last_reviewed} precedes created {self.created}"
            )

        required_field, why = _TYPE_REQUIREMENTS[self.type]
        if not getattr(self, required_field):
            raise CapsuleError(f"{self.id} ({self.type.value}): {why}")
        if self.type is CapsuleType.MODULE and not self.tests:
            raise CapsuleError(f"{self.id} (module): {_MODULE_REQUIRES_TEST}")

        if self.recheck_on is None:
            object.__setattr__(
                self, "recheck_on", default_recheck_on(self.freshness, self.last_reviewed)
            )

        problems = budget_problems(self, budget)
        if problems:
            raise CapsuleError(f"capsule {self.id} exceeds its budget: " + "; ".join(problems))

    # -- measurement ------------------------------------------------------

    def size_chars(self) -> int:
        """The capsule's canonical JSON length - what a session pays to read it.

        Measured over the file rather than over the prose, because field names
        are read too, and because the number is then reproducible from the file
        alone by anyone, with no access to this code.
        """
        return len(dumps(self))

    def references(self) -> tuple[str, ...]:
        """Every pointer the capsule carries, in declared field order."""
        out: list[str] = []
        for field in POINTER_FIELDS:
            out.extend(getattr(self, field))
        return tuple(out)

    def knowledge_links(self) -> tuple[tuple[str, str], ...]:
        """Every knowledge link as (record kind, record id), in field order."""
        out: list[tuple[str, str]] = []
        for field, record_kind in KNOWLEDGE_FIELDS:
            out.extend((record_kind, value) for value in getattr(self, field))
        return tuple(out)

    def duplicate_references(self) -> tuple[str, ...]:
        """Pointers the capsule names more than once, sorted."""
        seen: dict[str, int] = {}
        for ref in self.references():
            seen[ref] = seen.get(ref, 0) + 1
        return tuple(sorted(ref for ref, count in seen.items() if count > 1))

    # -- freshness --------------------------------------------------------

    def is_stale(self, today: dt.date) -> bool:
        """True once the review has expired. Anchored on `last_reviewed`."""
        return is_stale(self.freshness, self.last_reviewed, self.recheck_on, today)

    def is_flagged(self) -> bool:
        return self.status is RecordStatus.NEEDS_REVALIDATION

    def changed_sources(self, observed: Mapping[str, str]) -> tuple[str, ...]:
        """Recorded paths whose digest no longer matches what the caller observed.

        A path absent from `observed` is reported too: a file the capsule claims
        and the caller could not digest has either moved or been deleted, and
        both mean the capsule describes something that is no longer there.
        """
        return tuple(
            sorted(
                entry.path
                for entry in self.source_digests
                if observed.get(entry.path) != entry.digest
            )
        )

    # -- serialisation ----------------------------------------------------

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Capsule:
        return cls(
            id=data["id"],
            type=CapsuleType(data["type"]),
            title=data["title"],
            purpose=data["purpose"],
            owner=data["owner"],
            source=data["source"],
            created=as_date(data["created"], "created"),
            last_reviewed=as_date(data["last_reviewed"], "last_reviewed"),
            capabilities=as_tuple(data.get("capabilities")),
            owns_paths=as_tuple(data.get("owns_paths")),
            may_read=as_tuple(data.get("may_read")),
            may_write=as_tuple(data.get("may_write")),
            must_not_modify=as_tuple(data.get("must_not_modify")),
            inputs=as_tuple(data.get("inputs")),
            outputs=as_tuple(data.get("outputs")),
            dependencies=as_tuple(data.get("dependencies")),
            invariants=as_tuple(data.get("invariants")),
            risks=as_tuple(data.get("risks")),
            tests=as_tuple(data.get("tests")),
            benchmarks=as_tuple(data.get("benchmarks")),
            facts=as_tuple(data.get("facts")),
            decisions=as_tuple(data.get("decisions")),
            experiment_learnings=as_tuple(data.get("experiment_learnings")),
            failure_learnings=as_tuple(data.get("failure_learnings")),
            source_digests=tuple(
                entry if isinstance(entry, SourceDigest) else SourceDigest.from_dict(entry)
                for entry in data.get("source_digests", ())
            ),
            freshness=Freshness(data.get("freshness", "slow_changing")),
            recheck_on=as_opt_date(data.get("recheck_on"), "recheck_on"),
            status=RecordStatus(data.get("status", "active")),
            revalidation_reason=data.get("revalidation_reason", ""),
        )


def budget_problems(capsule: Capsule, budget: CapsuleBudget) -> tuple[str, ...]:
    """Budget violations that are totals rather than per-field shapes.

    The per-field limits are enforced as each field is checked; these two can
    only be known once the capsule is whole.
    """
    problems: list[str] = []
    size = capsule.size_chars()
    if size > budget.max_capsule_chars:
        problems.append(
            f"{size} characters exceeds the {budget.max_capsule_chars}-character "
            "ceiling - a capsule this long is a second README"
        )
    count = len(capsule.references())
    if count > budget.max_references:
        problems.append(f"{count} references exceeds the {budget.max_references} allowed")
    return tuple(problems)


def flag_capsule_for_revalidation(capsule: Capsule, reason: str) -> Capsule:
    """Mark a capsule as needing a recheck, keeping every other field.

    Refused for a `PERMANENT` capsule, for the reason `flag_for_revalidation`
    refuses it for a record: if an invariant needs revalidating, the class was
    wrong, and a status change would hide the misclassification.
    """
    if capsule.freshness is Freshness.PERMANENT:
        raise CapsuleError(
            f"{capsule.id!r} is marked permanent. If it needs revalidation the class "
            "was wrong - supersede it with a correctly classified capsule."
        )
    assert_line(reason, "revalidation reason", DEFAULT_BUDGET.max_statement_chars)
    return replace(capsule, status=RecordStatus.NEEDS_REVALIDATION, revalidation_reason=reason)
