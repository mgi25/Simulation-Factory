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

## Why the required set is derived rather than written down

`REQUIRED_SUITES` used to be the whole answer, and that was a fail-open hole.
It is a hand-maintained list of eleven canonical subsystem suites; a capsule
can declare a test in `capsule.tests` and the gate would never ask about it.
That is not hypothetical - the P5 integration reached READY while two tests
declared by the active `company-research-intelligence` capsule were failing,
because neither name appeared in the list and nobody had to notice.

Appending those two names would have closed that instance and left the hole.
So the required set is now *derived*, by `resolve_required_suites`, from three
sources that each answer a different question:

* **canonical** (`REQUIRED_SUITES`) - the subsystems whose invariants the gate's
  own checks depend on. A floor. It is still written down because some of it
  (`tests/test_company_execution_transport.py`) is required by the gate and
  declared by no capsule.
* **capsules in force** (`capsule.tests`) - the tests the Company OS contract
  itself names. A capsule is the authoritative description of a subsystem; if
  it says a suite covers it, that suite is evidence the gate needs.

  "In force" is `active` **and `needs_revalidation`**, and the second one is
  not an oversight. `flag_capsule_for_revalidation()` is a supported operation;
  if it removed a capsule's suites from the required set, flagging a capsule
  would be a way to make the gate stop asking about exactly the subsystem
  somebody has just said they no longer trust. A contract under suspicion is
  still the contract. Only `superseded` and `retired` stop contributing, and
  change scope can still pull those back.
* **change scope** (`changed_paths`) - the suites a particular change reaches,
  including ones declared by a capsule that is *not* active, and Company OS
  test files the change edits directly.

Scope only ever **adds**. There is no path by which naming a narrow change
shrinks the required set below canonical-plus-active-capsules, because a gate
that can be made cheaper by describing the change less fully is a gate with a
dial on it.

## Why an underivable set is not an empty set

`RequiredSuites.unresolved` names every reason the set could not be fully
determined. It is not a warning. `health.required_suites_pass` answers
`unknown` while it is non-empty, because "I could not work out what evidence I
need" and "I have all the evidence I need" must never produce the same verdict.

Four things put an entry there, and the last two were found by review rather
than by design:

1. the capsule index would not load at all (`None`);
2. it loaded and holds no capsules - in a Company OS checkout that is a
   directory that was not found, pointed at the wrong place, or emptied, never
   a repository that genuinely declares no tests;
3. it loaded **partially**. The same argument as (2) applies with identical
   force to a store that lost half its files, and stopping at zero left that
   open. `CapsuleIndex.integrity()` with no store and no checkout reports
   dangling dependencies and duplicate path claims from the capsules' own
   declarations alone - a partial store almost always has a capsule depending
   on one that is no longer there - so a structurally broken index is refused
   rather than believed;
4. a capsule named something in `tests` that is not a usable suite path - a
   glob, a path outside `tests/`, something that is not a `.py` file. Dropping
   those silently would let one legal-looking capsule edit remove a suite from
   the required set with nothing to show for it.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.references import assert_reference, assert_text
from ai_platform.serde import as_date, read_json, to_jsonable
from ai_platform.serde import fingerprint as _fingerprint
from knowledge.company_os import RecordStatus
from knowledge.company_os.capsules import CapsuleIndex, normalise_path, path_related

from .dependencies import DependencyGraph
from .errors import IntegrationGateError
from .sources import COMPANY_OS_TEST_PREFIX, TEST_ROOT


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


# -- the derived required set ----------------------------------------------


class SuiteOrigin(Enum):
    """Why a suite is required. A reader disputing the set disputes an origin."""

    CANONICAL = "canonical"
    CAPSULE_CONTRACT = "capsule_contract"
    CHANGE_SCOPE = "change_scope"
    DEPENDENCY_OBSERVED = "dependency_observed"


@dataclass(frozen=True)
class SuiteRequirement:
    """One required suite and the full reason it is required.

    `origins` is a tuple rather than a single value because a suite is very
    often required twice over - canonical *and* declared by a capsule contract
    - and dropping one of the two reasons would make the set look more fragile
    than it is.

    The two capsule lists are kept apart because they are different claims.
    `capsule_ids` are capsules that *named* this suite in `capsule.tests`.
    `dependency_capsule_ids` are capsules whose owned code this suite imports,
    which is something the repository says and the capsule may know nothing
    about. Merging them was tried and produced report lines reading "declared
    by ai-platform" for a suite `ai-platform` has never mentioned - a false
    sentence in the one document a reader uses to dispute the set.
    """

    suite: str
    origins: tuple[SuiteOrigin, ...]
    capsule_ids: tuple[str, ...] = ()
    dependency_capsule_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "suite", assert_reference(self.suite, "suite"))
        origins = tuple(dict.fromkeys(self.origins))
        if not origins:
            raise IntegrationGateError(
                f"suite {self.suite}: a requirement with no origin is a requirement "
                "nobody can argue with"
            )
        for origin in origins:
            if not isinstance(origin, SuiteOrigin):
                raise IntegrationGateError(
                    f"suite {self.suite}: origins hold SuiteOrigin values"
                )
        object.__setattr__(self, "origins", origins)
        object.__setattr__(self, "capsule_ids", tuple(sorted(set(self.capsule_ids))))
        object.__setattr__(
            self,
            "dependency_capsule_ids",
            tuple(sorted(set(self.dependency_capsule_ids))),
        )

    def reason(self) -> str:
        parts = [origin.value for origin in self.origins]
        if self.capsule_ids:
            parts.append("declared by " + ", ".join(self.capsule_ids))
        if self.dependency_capsule_ids:
            parts.append(
                "imports code owned by " + ", ".join(self.dependency_capsule_ids)
            )
        return "; ".join(parts)

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class RequiredSuites:
    """The suites this run needs evidence for, and why it may not know them all.

    `unresolved` is the safety property. An empty `requirements` and an
    unreadable capsule index both produce a short list; only `unresolved`
    distinguishes "this repository genuinely requires little" from "I could not
    find out what it requires", and the gate must answer `unknown` for the
    second.
    """

    requirements: tuple[SuiteRequirement, ...] = ()
    unresolved: tuple[str, ...] = ()
    derived_from: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for item in self.requirements:
            if not isinstance(item, SuiteRequirement):
                raise IntegrationGateError(
                    "required suites hold SuiteRequirement values"
                )
        names = [item.suite for item in self.requirements]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise IntegrationGateError(
                "a suite appears twice in the required set: " + ", ".join(duplicates)
            )
        object.__setattr__(
            self, "requirements", tuple(sorted(self.requirements, key=lambda r: r.suite))
        )
        object.__setattr__(self, "unresolved", tuple(self.unresolved))
        object.__setattr__(self, "derived_from", tuple(sorted(set(self.derived_from))))

    def __len__(self) -> int:
        return len(self.requirements)

    def __iter__(self):
        return iter(self.requirements)

    def __contains__(self, suite: object) -> bool:
        return any(item.suite == suite for item in self.requirements)

    @property
    def resolved(self) -> bool:
        """True when nothing stopped the set being worked out in full."""
        return not self.unresolved

    def names(self) -> tuple[str, ...]:
        return tuple(item.suite for item in self.requirements)

    def get(self, suite: str) -> "SuiteRequirement | None":
        for item in self.requirements:
            if item.suite == suite:
                return item
        return None

    def by_origin(self, origin: SuiteOrigin) -> tuple[SuiteRequirement, ...]:
        return tuple(item for item in self.requirements if origin in item.origins)

    def fingerprint(self) -> str:
        """Stable identity of the set, so a report can say which set it used."""
        return _fingerprint(
            {
                "requirements": [item.to_dict() for item in self.requirements],
                "unresolved": list(self.unresolved),
                # The capsule ids the set was read off, not only the suites it
                # produced. A capsule can be deleted without changing any
                # surviving capsule's declarations, so a store that has quietly
                # lost one is internally consistent; what it is not is the same
                # store, and this is what says so.
                "derived_from": list(self.derived_from),
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


# Which capsule lifecycle states still bind. See the module docstring: a
# capsule flagged for revalidation is under suspicion, which is the last moment
# you would want to stop running its tests.
_IN_FORCE: frozenset[RecordStatus] = frozenset(
    {RecordStatus.ACTIVE, RecordStatus.NEEDS_REVALIDATION}
)

_GLOB_CHARS = ("*", "?", "[")


def _suite_path(reference: str) -> str:
    """The test *file* a capsule reference names, or "" when it names none.

    A capsule may write `tests/test_x.py::test_one`; suite evidence is reported
    per file, so the node id is dropped. Anything that is not a `.py` file
    under `tests/` is not a suite and is ignored rather than guessed at.
    """
    if any(char in reference for char in _GLOB_CHARS):
        return ""
    cleaned = normalise_path(reference)
    if not cleaned.endswith(".py"):
        return ""
    if not cleaned.startswith(TEST_ROOT + "/"):
        return ""
    if "/./" in cleaned or "/../" in cleaned:
        return ""
    return cleaned


def _is_company_os_test(suite: str) -> bool:
    return suite.rsplit("/", 1)[-1].startswith(COMPANY_OS_TEST_PREFIX)


def resolve_required_suites(
    index: "CapsuleIndex | None",
    *,
    changed_paths: Iterable[str] = (),
    canonical: Iterable[str] = REQUIRED_SUITES,
    graph: "DependencyGraph | None" = None,
) -> RequiredSuites:
    """Work out which suites this run needs evidence for.

    Deterministic and side-effect free: it reads an already-loaded capsule
    index, a list of changed paths and an already-built dependency graph, runs
    no tests, and touches no clock. The same inputs always give the same set,
    which is what lets the result be fingerprinted into a report.

    `index` is `None` when the caller could not load the capsule store; an
    *empty* index and a *structurally broken* one mean the same thing in
    practice. None of the three is treated as "no capsules declare anything":
    the canonical floor is still returned, and `unresolved` says the
    contract-declared part is unknown, which keeps
    `health.required_suites_pass` at `unknown`.

    ## The fourth source, and why it was needed

    P6A derived the set from three sources and reported, at the bottom of
    `python -m company.integration required-suites`, eleven Company OS suites
    that no capsule declared and the gate therefore never asked about. They
    could go red on a green gate.

    Appending eleven names to `REQUIRED_SUITES` would have closed that
    instance and restored the hand-maintained list P6A had just removed. The
    twelfth suite, written next month, would be undeclared again.

    `DEPENDENCY_OBSERVED` closes it as a class. A `test_company*` file whose
    own import statements name a module an in-force capsule owns is evidence
    the contract needs, whether or not a capsule got around to declaring it.
    On this repository that is exactly the eleven, and no twelfth: all 38
    Company OS suites reach owned code, and 27 were already required.

    It is derived, not listed, so it needs no maintenance. It cannot shrink
    the set - like every other source here it only ever adds. And it uses
    *direct* imports, not the transitive closure: through a package facade
    almost every suite reaches almost every module, which would make the
    origin true of everything and therefore say nothing.

    ## Why `graph=None` is unresolved rather than skipped

    Same argument as `index is None`, one source along. A caller with no
    dependency evidence has not learned that nothing is dependency-observed;
    they have learned nothing about it. Returning the narrower set silently
    would make omitting the graph the cheapest way to shrink the gate, which
    is the one property this function exists to deny.
    """
    origins: dict[str, list[SuiteOrigin]] = {}
    capsules: dict[str, set[str]] = {}
    reached: dict[str, set[str]] = {}
    unresolved: list[str] = []

    def require(suite: str, origin: SuiteOrigin, capsule_id: str = "") -> None:
        found = origins.setdefault(suite, [])
        if origin not in found:
            found.append(origin)
        if not capsule_id:
            return
        # Which list an id lands in is decided by the origin that supplied it,
        # not by the suite. The same capsule can legitimately appear in both:
        # `company-runtime` declares `tests/test_company_runtime.py` and that
        # suite also imports its code.
        bucket = reached if origin is SuiteOrigin.DEPENDENCY_OBSERVED else capsules
        bucket.setdefault(suite, set()).add(capsule_id)

    for suite in canonical:
        require(str(suite), SuiteOrigin.CANONICAL)

    changed = tuple(
        normalise_path(path) for path in changed_paths if str(path).strip()
    )

    if index is None:
        unresolved.append(
            "the capsule index could not be loaded, so the suites declared by the "
            "Company OS contract are unknown; only the canonical floor is required"
        )
    elif len(index) == 0:
        # An empty store and a store nobody could read are the same fact wearing
        # different clothes. A Company OS checkout has capsules; a directory
        # with none in it is a directory that was not found, pointed at the
        # wrong place, or emptied - never a repository that genuinely declares
        # no tests. Reading it as "nothing is required" is the fail-open this
        # whole function exists to close.
        unresolved.append(
            "the capsule store holds no capsules, so the suites declared by the "
            "Company OS contract are unknown; only the canonical floor is required"
        )
    else:
        # Structural integrity only: no knowledge store, no checkout, so this
        # stays a pure function of the index. A partial store shows up here as
        # a capsule depending on one that is no longer present.
        broken = index.integrity()
        if broken:
            unresolved.append(
                f"the capsule store is structurally incomplete ({len(broken)} "
                f"problem(s), first: {broken[0]}), so what the Company OS "
                "contract requires cannot be read off it"
            )
        for capsule in index.all():
            in_force = capsule.status in _IN_FORCE
            in_scope = bool(changed) and any(
                path_related(owned, path)
                for owned in capsule.owns_paths
                for path in changed
            )
            if not in_force and not in_scope:
                continue
            for reference in capsule.tests:
                suite = _suite_path(reference)
                if not suite:
                    unresolved.append(
                        f"{capsule.id}.tests names {reference!r}, which is not a "
                        "suite this gate can ask for evidence about; whatever it "
                        "covers is therefore unrequired"
                    )
                    continue
                if in_force:
                    require(suite, SuiteOrigin.CAPSULE_CONTRACT, capsule.id)
                if in_scope:
                    require(suite, SuiteOrigin.CHANGE_SCOPE, capsule.id)

    for path in changed:
        suite = _suite_path(path)
        if suite and _is_company_os_test(suite):
            require(suite, SuiteOrigin.CHANGE_SCOPE)

    unresolved.extend(
        _require_dependency_observed(index, graph, require)
    )

    return RequiredSuites(
        requirements=tuple(
            SuiteRequirement(
                suite=suite,
                origins=tuple(found),
                capsule_ids=tuple(sorted(capsules.get(suite, ()))),
                dependency_capsule_ids=tuple(sorted(reached.get(suite, ()))),
            )
            for suite, found in origins.items()
        ),
        unresolved=tuple(unresolved),
        derived_from=() if index is None else tuple(c.id for c in index.all()),
    )


def _require_dependency_observed(
    index: "CapsuleIndex | None",
    graph: "DependencyGraph | None",
    require,
) -> tuple[str, ...]:
    """Require every Company OS suite that imports code a capsule owns.

    Returns the reasons the dependency-derived part could not be worked out,
    so the caller can put them in `unresolved`. Three of them, and each is a
    different way of not knowing rather than a way of knowing nothing:

    * no graph was supplied at all;
    * the graph could not parse part of the tree, so a suite that reaches
      owned code may be sitting in the unparsed part;
    * there is no usable capsule index, so "owned" has no meaning here. That
      case is already unresolved for the contract-declared source; it is
      repeated rather than assumed, because the two could drift apart.
    """
    if graph is None:
        return (
            "no dependency evidence was supplied, so the Company OS suites that "
            "import capsule-owned code cannot be identified; only the declared "
            "sources are required",
        )
    if graph.parse_failures:
        return (
            f"the dependency graph could not parse {len(graph.parse_failures)} "
            f"file(s) (first: {graph.parse_failures[0]}), so a suite reaching "
            "capsule-owned code may not be visible in it",
        )
    if index is None or len(index) == 0:
        return (
            "the capsule store is unreadable or empty, so no path can be shown to "
            "be capsule-owned and the dependency-observed suites are unknown",
        )

    claims = [
        (normalise_path(path), capsule.id)
        for capsule in index.all()
        if capsule.status in _IN_FORCE
        for path in capsule.owns_paths
    ]
    for module in graph.modules:
        if not graph.is_company_os_test(module):
            continue
        owners = sorted(
            {
                capsule_id
                for reached in graph.modules_reached_by(module, transitive=False)
                for claim, capsule_id in claims
                if path_related(claim, reached)
            }
        )
        for capsule_id in owners:
            require(module, SuiteOrigin.DEPENDENCY_OBSERVED, capsule_id)
    return ()


def undeclared_company_os_suites(
    repo_root: Path | str, required: RequiredSuites
) -> tuple[str, ...]:
    """Company OS test files on disk that no contract asks for.

    Not used by any check, and deliberately so. A test nobody declared is not
    a test the contract requires, and inventing a requirement from a filename
    would make the required set depend on what happens to be in a directory
    rather than on what a capsule says. The gate's verdict stays derived from
    contracts.

    But an eleven-file blind spot that nothing ever prints is a blind spot
    that stays. This is the only I/O in the module, it is reached only from
    `python -m company.integration required-suites`, and what it reports is a
    gap in the *capsule contracts*, not a failure of the gate.
    """
    root = Path(repo_root)
    tests = root / TEST_ROOT
    if not tests.is_dir():
        return ()
    claimed = set(required.names())
    return tuple(
        sorted(
            f"{TEST_ROOT}/{path.name}"
            for path in tests.glob(f"{COMPANY_OS_TEST_PREFIX}*.py")
            if f"{TEST_ROOT}/{path.name}" not in claimed
        )
    )


__all__ = [
    "DEFAULT_MAX_EVIDENCE_AGE_DAYS",
    "REQUIRED_SUITES",
    "RequiredSuites",
    "SuiteEvidence",
    "SuiteOrigin",
    "SuiteRequirement",
    "SuiteResult",
    "resolve_required_suites",
    "undeclared_company_os_suites",
]
