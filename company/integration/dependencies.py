"""What the repository's imports actually say, as a graph the gate can check.

## The hole this closes

P6A derived the required suite set from `capsule.tests`, which made the
contract the authority instead of a hand-maintained list. It left the obvious
next question open, and said so in `checks.py`:

    The real fix is to make `capsule.tests` a checked claim against the actual
    test-to-module dependency, which is P6B.

`capsule.tests` is a *declaration*. Nothing verified it against the repository.
A capsule could name a suite that imports nothing it owns, or own a package no
named suite reaches, and every gate run would pass. This module is the other
half: the import graph the declaration is checked against.

## What an edge means, and what it does not

An edge here is a **static import dependency** and nothing more. If
`tests/test_company_runtime.py` imports `company.runtime.routing`, then running
that suite loads that module. It does not follow that the suite exercises it,
asserts anything about it, or would go red if it broke.

The distinction is not pedantry, it is the whole reason this module is safe to
build a gate condition on. "Test imports module" is checkable from source with
no execution and no judgement. "Test proves module" is a claim about behaviour
that no import graph can support. Every name in `DependencyRelation`, and every
sentence this module puts in a gate report, says `observed` and `static`
because that is the claim the evidence carries.

## Why it is built from `GateScan` and not from the runner's map

`tools/engineering_runner/repo_map.py` also builds an import index, and reusing
it was the obvious move. It is forbidden: `company/**` importing
`tools.engineering_runner` is exactly what
`architecture.production_does_not_import_company_os` and its sibling exist to
prevent, and a dependency graph that breaks the architecture boundary in order
to describe it would be self-refuting.

The clean boundary turned out to already exist. `GateScan` parses every
production root, every Company OS root and every test on each run, and
`sources.py` already resolves relative imports against the importing file's own
package - the one thing the runner's parser did not do. So this module needs no
new parse, no serialized manifest, no cache and no staleness window: it is a
pure function of a scan the gate already performs. Evidence that is recomputed
from the tree cannot be stale.

The runner keeps its own map for its own job, which is localizing context for a
session, not gating an integration. Two parsers, one contract, and
`tests/test_company_dependency_graph.py` pins the resolution semantics of both
to the same cases - the same drift-test pattern the runner already uses for the
four control-plane contracts it restates.

## Four resolution rules, and why each is needed here

1. **Relative imports resolve against the importing package.** `from .suites
   import X` in `company/integration/__init__.py` is an edge to
   `company/integration/suites.py`. 965 imports in this repository are written
   this way; dropping them leaves `company/` almost edgeless.
2. **`from package import name` may name a module.** `from company.integration
   import suites` and `from company.integration import GateStatus` are the same
   syntax and different dependencies. Resolved by asking whether
   `company/integration/suites.py` exists, never by guessing from the name.
3. **Importing anything under a package imports the package.** `import a.b.c`
   executes `a/__init__.py` and `a/b/__init__.py`, so those are real edges.
   This is what makes a facade import reach the modules the facade re-exports,
   which is how most tests here reach most code.
4. **What cannot be resolved is named, never guessed.** A dynamic
   `importlib.import_module(name)` is recorded in `unresolved` with its line.
   There is no filename heuristic anywhere in this module: `test_foo.py` has no
   relationship to `foo.py` unless an import says so.

Rule 2 over-reports in one case, deliberately. If a package's `__init__`
binds a name that a sibling module also has - `core = 1` beside `core.py` -
then `from pkg import core` produces both edges, though only one of them runs.
Deciding which would mean executing the package. The extra edge can only add a
required suite or a recommended file, never remove one, so the error is in the
direction the rest of this design already chose.

## Two graphs in one package, and why they are not one graph

`graph.py` already builds an import graph, and this is not a second copy of
it. That one has **one node per subsystem** - `company/runtime`, not
`company/runtime/routing.py` - because the question it answers is whether the
control plane has a cycle in it, and a cycle is a property of subsystems.
Collapsing files into subsystems is exactly what makes that question cheap.

This module needs the opposite. "Which suites load this module" and "does this
capsule's declared test reach the code it owns" are file-level questions, and a
subsystem-level graph answers both with "yes, something in that subsystem
does", which is not an answer.

The two agree where they overlap. Both exclude `if TYPE_CHECKING:` imports from
the runtime graph and report them separately, for the same reason: a guarded
import never executes, so it cannot make one thing need another at run time,
and hiding it entirely would be the opposite mistake.

## Why the transitive closure is deliberately not a coverage claim

Rule 3 has a consequence worth stating plainly, because it decided the capsule
contract semantics in `audit_capsule_tests`. `company/runtime/__init__.py`
re-exports most of its package, so a test importing `company.runtime` reaches
nearly every module in it transitively. Those are true static dependencies -
the code is loaded - and they are useless as a coverage statement.

That is the evidence behind treating `capsule.tests` as a bounded witness set
rather than a complete dependent-test list. A complete list is not merely
inconvenient at eight items per capsule; through a package facade it is close
to "every Company OS suite", which describes nothing.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from knowledge.company_os.capsules import CapsuleIndex, normalise_path, path_related
from knowledge.company_os.records import RecordStatus

from .errors import IntegrationGateError
from .sources import COMPANY_OS_TEST_PREFIX, TEST_ROOT


# How far the closure walks before it reports itself bounded rather than
# complete. The graph is ~540 modules; a walk that has expanded this many
# without terminating has met something pathological, and a bounded answer
# that says it is bounded beats an unbounded one that hangs the gate.
MAX_CLOSURE_EXPANSIONS = 100_000

# The default ceiling on a single bounded query's answer. Repository
# intelligence returns slices, not maps - see `impact`.
DEFAULT_QUERY_LIMIT = 40

# The lifecycle states whose declarations still bind, mirroring
# `suites._IN_FORCE`. A capsule flagged for revalidation is under suspicion,
# which is the last moment to stop auditing it.
IN_FORCE_STATUSES: frozenset[RecordStatus] = frozenset(
    {RecordStatus.ACTIVE, RecordStatus.NEEDS_REVALIDATION}
)


class DependencyRelation(Enum):
    """How one thing is related to another, at the precision source can prove.

    The six values are deliberately not a severity ladder. `DECLARED` and
    `OBSERVED` answer different questions - what the contract says, and what
    the imports say - and the two disagreements between them
    (`DECLARED_NOT_OBSERVED`, `OBSERVED_NOT_DECLARED`) are findings to explain,
    not errors to fix by definition. A CLI test that drives a subprocess is
    declared and unobservable, and it is doing nothing wrong.
    """

    DIRECT_STATIC = "direct_static"
    TRANSITIVE_STATIC = "transitive_static"
    DECLARED_CONTRACT = "declared_contract"
    DECLARED_NOT_OBSERVED = "declared_not_observed"
    OBSERVED_NOT_DECLARED = "observed_not_declared"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class UnresolvedDependency:
    """One import this module refused to turn into an edge, and why.

    Kept rather than dropped because a graph that silently discards what it
    could not resolve reports the same shape as a graph with nothing to
    resolve, and only one of those is trustworthy.
    """

    path: str
    line: int
    detail: str
    reason: str

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


@dataclass(frozen=True)
class DependencyGraph:
    """Every repository-internal import edge, resolved to file paths.

    `edges` maps an importing path to the paths it imports directly. Only
    repository modules appear on either side: `import json` is not an edge
    because the standard library is not something a capsule can own or a test
    can be said to reach.
    """

    edges: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    type_checking_edges: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    unresolved: tuple[UnresolvedDependency, ...] = ()
    modules: tuple[str, ...] = ()
    parse_failures: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "modules", tuple(sorted(set(self.modules))))
        object.__setattr__(
            self, "edges", {k: tuple(sorted(set(v))) for k, v in sorted(self.edges.items())}
        )
        object.__setattr__(
            self,
            "type_checking_edges",
            {k: tuple(sorted(set(v))) for k, v in sorted(self.type_checking_edges.items())},
        )
        object.__setattr__(
            self,
            "unresolved",
            tuple(sorted(self.unresolved, key=lambda u: (u.path, u.line, u.detail))),
        )
        object.__setattr__(self, "parse_failures", tuple(sorted(set(self.parse_failures))))
        object.__setattr__(self, "_dependents_cache", {})

    # -- membership -------------------------------------------------------

    def __contains__(self, path: object) -> bool:
        return normalise_path(str(path)) in set(self.modules)

    def is_test(self, path: str) -> bool:
        return normalise_path(path).startswith(TEST_ROOT + "/")

    def is_company_os_test(self, path: str) -> bool:
        clean = normalise_path(path)
        return self.is_test(clean) and clean.rsplit("/", 1)[-1].startswith(
            COMPANY_OS_TEST_PREFIX
        )

    # -- forward edges ----------------------------------------------------

    def direct_dependencies(self, path: str) -> tuple[str, ...]:
        """The repository modules `path` imports itself."""
        return self.edges.get(normalise_path(path), ())

    def transitive_dependencies(self, path: str) -> tuple[str, ...]:
        """Everything `path` reaches through imports, excluding itself.

        Cycle-safe by construction: a breadth-first walk over a visited set
        terminates on any graph, including the import cycles this repository
        does contain between a package `__init__` and its own modules.
        """
        return self._closure(normalise_path(path), self.edges)

    # -- reverse edges ----------------------------------------------------

    def _dependents_index(self) -> Mapping[str, tuple[str, ...]]:
        cache = getattr(self, "_dependents_cache")
        if "index" not in cache:
            reverse: dict[str, set[str]] = {path: set() for path in self.modules}
            for importer, imported in self.edges.items():
                for target in imported:
                    reverse.setdefault(target, set()).add(importer)
            cache["index"] = {k: tuple(sorted(v)) for k, v in sorted(reverse.items())}
        return cache["index"]

    def direct_dependents(self, path: str) -> tuple[str, ...]:
        """Repository modules that import `path` themselves."""
        return self._dependents_index().get(normalise_path(path), ())

    def transitive_dependents(self, path: str) -> tuple[str, ...]:
        """Everything that reaches `path`, directly or through other modules."""
        return self._closure(normalise_path(path), self._dependents_index())

    # -- the two questions the audit asks ---------------------------------

    def tests_reaching(self, path: str, *, transitive: bool = True) -> tuple[str, ...]:
        """Test files whose imports statically reach `path`.

        Not "tests that cover `path`". See the module docstring: reaching a
        module means the suite loads it, which is a necessary condition for
        testing it and nowhere near a sufficient one.
        """
        source = (
            self.transitive_dependents(path) if transitive else self.direct_dependents(path)
        )
        return tuple(sorted(item for item in source if self.is_test(item)))

    def modules_reached_by(self, test: str, *, transitive: bool = True) -> tuple[str, ...]:
        """Repository modules one test file statically reaches."""
        clean = normalise_path(test)
        source = (
            self.transitive_dependencies(clean) if transitive else self.direct_dependencies(clean)
        )
        return tuple(sorted(item for item in source if not self.is_test(item)))

    def relation(self, test: str, path: str) -> DependencyRelation:
        """How `test` reaches `path`: directly, transitively, or not statically.

        The third answer is `UNRESOLVED`, not a "no relationship" value, and
        the difference is the whole subject of this module. A suite with no
        static path to a module may still exercise it - through a subprocess,
        a fixture file, a dynamic import, or by reading its source as text.
        What the import graph can say is that it found no static relationship,
        which is a statement about the evidence and not about the suite.

        Returning "none" here would let a caller conclude that a declared test
        does not test what it declares, from a graph that never had grounds
        for it. `audit_capsule_tests` reports exactly that case as
        `declared_not_observed`, and calls it a finding rather than a fault
        for the same reason.
        """
        clean_test, clean_path = normalise_path(test), normalise_path(path)
        if clean_path in self.direct_dependencies(clean_test):
            return DependencyRelation.DIRECT_STATIC
        if clean_path in self.transitive_dependencies(clean_test):
            return DependencyRelation.TRANSITIVE_STATIC
        return DependencyRelation.UNRESOLVED

    # -- bounded query surface --------------------------------------------

    def impact(self, path: str, *, limit: int = DEFAULT_QUERY_LIMIT) -> "ImpactSlice":
        """One bounded answer for one path. Never the whole graph.

        `limit` caps each list independently and the slice reports what it
        dropped, because a truncated answer that does not say it is truncated
        is a wrong answer.
        """
        if limit < 1:
            raise IntegrationGateError("impact limit must be at least 1")
        clean = normalise_path(path)
        direct_tests = self.tests_reaching(clean, transitive=False)
        all_tests = self.tests_reaching(clean, transitive=True)
        transitive_tests = tuple(t for t in all_tests if t not in set(direct_tests))
        dependents = tuple(
            item for item in self.direct_dependents(clean) if not self.is_test(item)
        )
        return ImpactSlice(
            path=clean,
            known=clean in self,
            direct_dependencies=_cap(self.direct_dependencies(clean), limit),
            direct_dependents=_cap(dependents, limit),
            direct_tests=_cap(direct_tests, limit),
            transitive_tests=_cap(transitive_tests, limit),
            considered=len(self.modules),
            truncated=tuple(
                sorted(
                    name
                    for name, values in (
                        ("direct_dependencies", self.direct_dependencies(clean)),
                        ("direct_dependents", dependents),
                        ("direct_tests", direct_tests),
                        ("transitive_tests", transitive_tests),
                    )
                    if len(values) > limit
                )
            ),
        )

    # -- identity ---------------------------------------------------------

    def fingerprint(self) -> str:
        """Stable identity of the graph, so a report can name the one it used."""
        return _fingerprint(
            {
                "modules": list(self.modules),
                "edges": {k: list(v) for k, v in self.edges.items()},
                "unresolved": [u.to_dict() for u in self.unresolved],
                "parse_failures": list(self.parse_failures),
            }
        )

    def summary(self) -> dict[str, object]:
        edge_count = sum(len(v) for v in self.edges.values())
        tests = [m for m in self.modules if self.is_test(m)]
        return {
            "modules": len(self.modules),
            "test_modules": len(tests),
            "edges": edge_count,
            "unresolved": len(self.unresolved),
            "parse_failures": len(self.parse_failures),
            "fingerprint": self.fingerprint(),
        }

    # -- internals --------------------------------------------------------

    def _closure(self, start: str, adjacency: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
        seen: set[str] = set()
        queue: deque[str] = deque(adjacency.get(start, ()))
        expansions = 0
        while queue and expansions < MAX_CLOSURE_EXPANSIONS:
            current = queue.popleft()
            expansions += 1
            if current in seen or current == start:
                continue
            seen.add(current)
            queue.extend(adjacency.get(current, ()))
        return tuple(sorted(seen))


def _cap(values: Sequence[str], limit: int) -> tuple[str, ...]:
    return tuple(values[:limit])


@dataclass(frozen=True)
class ImpactSlice:
    """One path's bounded neighbourhood, sized for a briefing rather than a map."""

    path: str
    known: bool
    direct_dependencies: tuple[str, ...] = ()
    direct_dependents: tuple[str, ...] = ()
    direct_tests: tuple[str, ...] = ()
    transitive_tests: tuple[str, ...] = ()
    considered: int = 0
    truncated: tuple[str, ...] = ()

    def returned(self) -> int:
        return (
            len(self.direct_dependencies)
            + len(self.direct_dependents)
            + len(self.direct_tests)
            + len(self.transitive_tests)
        )

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


# -- construction -----------------------------------------------------------


def _dotted(path: str) -> str:
    dotted = path[:-3] if path.endswith(".py") else path
    dotted = dotted.replace("/", ".")
    if dotted.endswith(".__init__"):
        dotted = dotted[: -len(".__init__")]
    return dotted


def _ancestors(dotted: str) -> tuple[str, ...]:
    parts = dotted.split(".")
    return tuple(".".join(parts[:i]) for i in range(1, len(parts)))


_DYNAMIC_CALLS = ("import_module", "__import__")


def _dynamic_imports(path: str, tree: ast.AST) -> tuple[UnresolvedDependency, ...]:
    """Every dynamic import call in one file, recorded as unresolvable.

    A literal argument is *not* resolved into an edge. It would be right most
    of the time, and the one time it is wrong the graph would assert a
    dependency nobody wrote. Naming it unresolved costs a line in a report;
    guessing it costs the graph its meaning.
    """
    found: list[UnresolvedDependency] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name not in _DYNAMIC_CALLS:
            continue
        argument = ""
        if node.args and isinstance(node.args[0], ast.Constant):
            value = node.args[0].value
            if isinstance(value, str):
                argument = value
        found.append(
            UnresolvedDependency(
                path=path,
                line=node.lineno,
                detail=f"{name}({argument!r})" if argument else f"{name}(...)",
                reason=(
                    "a dynamic import is resolved at run time; a static graph that "
                    "guessed its target would assert an edge nobody wrote"
                ),
            )
        )
    return tuple(found)


def build_dependency_graph(scan) -> DependencyGraph:
    """Resolve every import in a `GateScan` into repository-internal edges.

    Deterministic and side-effect free: same scan, same graph, byte for byte.
    Nothing here reads the filesystem - the scan already did - so this cannot
    disagree with the tree the rest of the gate run is looking at.
    """
    modules = tuple(scan.production_modules) + tuple(scan.company_modules) + tuple(scan.test_modules)
    by_path = {normalise_path(m.path): m for m in modules}
    dotted_to_path = {_dotted(path): path for path in by_path}

    edges: dict[str, set[str]] = {path: set() for path in by_path}
    guarded: dict[str, set[str]] = {}
    unresolved: list[UnresolvedDependency] = []

    for path, module in sorted(by_path.items()):
        for ref in module.imports:
            targets = _resolve(ref, dotted_to_path)
            if not targets:
                continue
            sink = guarded.setdefault(path, set()) if ref.type_checking else edges[path]
            for target in targets:
                if target != path:
                    sink.add(target)
        unresolved.extend(_dynamic_imports(path, module.tree))

    return DependencyGraph(
        edges={k: tuple(sorted(v)) for k, v in edges.items() if v},
        type_checking_edges={k: tuple(sorted(v)) for k, v in guarded.items() if v},
        unresolved=tuple(unresolved),
        modules=tuple(by_path),
        parse_failures=tuple(scan.production_failures)
        + tuple(scan.company_failures)
        + tuple(scan.test_failures),
    )


def _resolve(ref, dotted_to_path: Mapping[str, str]) -> tuple[str, ...]:
    """Every repository path one import statement really depends on.

    Three sources, all of them things Python actually does at import time:
    the named module itself; every package above it, whose `__init__` runs;
    and, for `from X import a`, `X.a` when a module of that name exists.
    """
    found: set[str] = set()
    module = ref.module
    if not module:
        return ()
    if module in dotted_to_path:
        found.add(dotted_to_path[module])
    for ancestor in _ancestors(module):
        if ancestor in dotted_to_path:
            found.add(dotted_to_path[ancestor])
    for name in getattr(ref, "names", ()):
        candidate = f"{module}.{name}"
        if candidate in dotted_to_path:
            found.add(dotted_to_path[candidate])
    return tuple(sorted(found))


# -- the capsule/test contract audit ----------------------------------------


@dataclass(frozen=True)
class CapsuleTestFinding:
    """One capsule's declared tests measured against the import graph."""

    capsule_id: str
    status: str
    owned_paths: tuple[str, ...] = ()
    owned_modules: tuple[str, ...] = ()
    declared: tuple[str, ...] = ()
    declared_and_observed: tuple[str, ...] = ()
    declared_not_observed: tuple[str, ...] = ()
    observed_direct: tuple[str, ...] = ()
    observed_transitive: tuple[str, ...] = ()
    observed_not_declared: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()

    def has_witness(self) -> bool:
        """True when at least one declared suite statically reaches owned code.

        The contract this audit can actually check. See `audit_capsule_tests`
        for why it is a witness and not a coverage set.
        """
        return bool(self.declared_and_observed)

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CapsuleTestAudit:
    """Every in-force capsule's test declaration, checked against the graph."""

    findings: tuple[CapsuleTestFinding, ...] = ()
    graph_fingerprint: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "findings", tuple(sorted(self.findings, key=lambda f: f.capsule_id))
        )

    def get(self, capsule_id: str) -> "CapsuleTestFinding | None":
        for finding in self.findings:
            if finding.capsule_id == capsule_id:
                return finding
        return None

    def without_witness(self) -> tuple[CapsuleTestFinding, ...]:
        """Capsules owning Python code that no suite they name can be shown to load.

        The one condition in this audit worth a gate's attention. Three
        qualifiers, each of which a run against this repository showed to be
        load-bearing:

        * `owned_modules` non-empty. `company-bootstrap-policy` owns the
          constitution and five YAML schemas, `company-evidence-review` owns a
          docs directory, and `company-os-control-plane` is a SYSTEM capsule
          owning no path at all. No import can reach any of them, and demanding
          a static witness for a capsule that owns no Python would be demanding
          the impossible and calling the refusal a finding.
        * `declared` non-empty. A capsule declaring nothing is already refused
          at construction by `_MODULE_REQUIRES_TEST`; this check is not the
          place to re-litigate it.
        * no witness among the declared. One observed suite is enough. A
          capsule whose fourth declaration drives a CLI in a subprocess is not
          failing anything - see `audit_capsule_tests` on why this is a witness
          set and not a coverage set.

        All 19 capsules owning Python in this repository currently satisfy it.
        """
        return tuple(
            f
            for f in self.findings
            if f.owned_modules and f.declared and not f.has_witness()
        )

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


def audit_capsule_tests(
    graph: DependencyGraph, index: "CapsuleIndex | None"
) -> CapsuleTestAudit:
    """Measure `capsule.tests` against what the imports show, per capsule.

    ## What `capsule.tests` is taken to mean, and why

    A **bounded witness set**, not a complete dependent-test list. Three pieces
    of repository evidence decide it, and none of them is a preference:

    * `capsule.py` states the MODULE requirement as "names a test", singular -
      "code with no test reference is code the next session cannot verify it
      did not break". The requirement is existence of a witness.
    * `budget.py` caps every list at eight items and gives the reason: a
      capsule stops being cheaper than the code it summarises if it grows.
      Eight is not a limit a complete list happens to exceed; it is the limit
      that makes a capsule a capsule.
    * The graph itself. Because a package `__init__` re-exports its modules,
      the transitive dependent set of a single Company OS module is most of
      the Company OS suite list. A "complete" declaration would be a copy of
      `tests/` in every capsule.

    So this audit never asks whether `capsule.tests` is exhaustive. It asks
    whether each declaration is *true* - does that suite reach that code - and
    reports the disagreements in both directions without ruling on them.

    `declared_not_observed` is a finding, not a fault. A suite may drive the
    CLI in a subprocess, read fixture files, or scan source text as a string;
    all three are real tests of the capsule's code and none of them is an
    import. `observed_not_declared` is likewise not a to-do list: most entries
    are integration suites that legitimately reach many capsules.
    """
    if index is None:
        return CapsuleTestAudit(graph_fingerprint=graph.fingerprint())
    findings: list[CapsuleTestFinding] = []
    for capsule in index.all():
        if capsule.status not in IN_FORCE_STATUSES:
            continue
        owned = tuple(
            path
            for path in graph.modules
            if any(path_related(claim, path) for claim in capsule.owns_paths)
        )
        declared: list[str] = []
        unresolved: list[str] = []
        for reference in capsule.tests:
            suite = _suite_reference(reference)
            if suite:
                declared.append(suite)
            else:
                unresolved.append(reference)

        direct: set[str] = set()
        transitive: set[str] = set()
        for path in owned:
            direct.update(graph.tests_reaching(path, transitive=False))
            transitive.update(graph.tests_reaching(path, transitive=True))
        transitive -= direct
        observed = direct | transitive

        declared_set = set(declared)
        findings.append(
            CapsuleTestFinding(
                capsule_id=capsule.id,
                status=capsule.status.value,
                owned_paths=tuple(normalise_path(p) for p in capsule.owns_paths),
                owned_modules=tuple(sorted(owned)),
                declared=tuple(sorted(declared_set)),
                declared_and_observed=tuple(sorted(declared_set & observed)),
                declared_not_observed=tuple(sorted(declared_set - observed)),
                observed_direct=tuple(sorted(direct)),
                observed_transitive=tuple(sorted(transitive)),
                observed_not_declared=tuple(sorted(observed - declared_set)),
                unresolved=tuple(sorted(unresolved)),
            )
        )
    return CapsuleTestAudit(
        findings=tuple(findings), graph_fingerprint=graph.fingerprint()
    )


def _suite_reference(reference: str) -> str:
    """The test file a capsule reference names, or "" when it names none.

    Same rule as `suites._suite_path`, restated rather than imported to keep
    this module a pure graph consumer; `tests/test_company_dependency_graph.py`
    pins the two to the same cases.
    """
    if any(char in reference for char in ("*", "?", "[")):
        return ""
    cleaned = normalise_path(reference)
    if not cleaned.endswith(".py"):
        return ""
    if not cleaned.startswith(TEST_ROOT + "/"):
        return ""
    if "/./" in cleaned or "/../" in cleaned:
        return ""
    return cleaned


# -- governed production subsystems (the P6A B2 residual) -------------------


@dataclass(frozen=True)
class GovernedSubsystem:
    """Production code the Company OS contract depends on, and who owns it.

    `tools/engineering_runner/` is production by root, and Company OS governs
    it: a capsule holds its write authority and the gate requires its suites.
    `sloped/` is production and Company OS governs nothing about it. Telling
    those two apart without naming either one is what this type is for.
    """

    package: str
    modules: tuple[str, ...]
    company_os_tests: tuple[str, ...]
    owning_capsules: tuple[str, ...]

    @property
    def owned(self) -> bool:
        return bool(self.owning_capsules)

    def to_dict(self) -> dict[str, object]:
        return to_jsonable(self)


def governed_production_subsystems(
    graph: DependencyGraph,
    index: "CapsuleIndex | None",
    *,
    company_os_roots: Iterable[str],
    production_roots: Iterable[str],
) -> tuple[GovernedSubsystem, ...]:
    """Production packages a Company OS suite statically reaches, and their owners.

    ## The residual this closes

    P6A could not make a capsule *disappearing* fail the gate in general.
    Deleting a capsule removes its `owns_paths` too, so 21 of the 22 leave an
    unclaimed Company OS module behind - but `company-external-engineering-runner`
    owns `tools/engineering_runner`, which is a *production* root, and
    `_unclaimed_company_modules` only walks the four Company OS roots. Delete
    that capsule and nothing in the repository looks wrong.

    Hard-coding the capsule id was available and rejected: it fixes one
    instance of a class, and the class is "a subsystem the contract depends on
    quietly loses its contract". The general form needs a source of truth for
    "Company OS governs this" that survives the capsule being deleted, which is
    exactly what an import graph is. A production package that a `test_company*`
    suite imports is governed *by the tests*, and deleting a capsule does not
    delete the imports.

    Run against this repository the rule finds two packages, which is the
    evidence that it generalises: the external runner, and `tools/youtube_fetch`,
    which `tests/test_company_youtube_end_to_end.py` reaches and which no
    capsule owns. The second was not known before this rule existed.

    Intentionally unowned production code is not flagged, because no Company OS
    suite imports it - `sloped/`, `race/`, `engine/` and the rest of the
    simulation tree appear nowhere in the result.
    """
    company_roots = tuple(company_os_roots)
    prod_roots = tuple(production_roots)
    owned_by: dict[str, set[str]] = {}
    if index is not None:
        for capsule in index.all():
            if capsule.status not in IN_FORCE_STATUSES:
                continue
            for claim in capsule.owns_paths:
                owned_by.setdefault(normalise_path(claim), set()).add(capsule.id)

    reached: dict[str, set[str]] = {}
    for test in graph.modules:
        if not graph.is_company_os_test(test):
            continue
        for target in graph.modules_reached_by(test, transitive=True):
            root = target.split("/", 1)[0]
            if root in company_roots or root not in prod_roots:
                continue
            reached.setdefault(_package_of(target), set()).add(test)

    subsystems: list[GovernedSubsystem] = []
    for package, tests in sorted(reached.items()):
        owners = sorted(
            {
                capsule_id
                for claim, ids in owned_by.items()
                if path_related(claim, package)
                for capsule_id in ids
            }
        )
        subsystems.append(
            GovernedSubsystem(
                package=package,
                modules=tuple(
                    sorted(m for m in graph.modules if path_related(package, m))
                ),
                company_os_tests=tuple(sorted(tests)),
                owning_capsules=tuple(owners),
            )
        )
    return tuple(subsystems)


def _package_of(path: str) -> str:
    """The top two path segments: `tools/engineering_runner/x.py` -> `tools/engineering_runner`.

    A subsystem here is a package directory, not a file, because a capsule
    claims `tools/engineering_runner` and the question is whether *that* is
    still governed - not whether each file under it is named separately.
    """
    parts = normalise_path(path).split("/")
    return "/".join(parts[:2]) if len(parts) > 2 else "/".join(parts[:-1]) or parts[0]


__all__ = [
    "DEFAULT_QUERY_LIMIT",
    "IN_FORCE_STATUSES",
    "CapsuleTestAudit",
    "CapsuleTestFinding",
    "DependencyGraph",
    "DependencyRelation",
    "GovernedSubsystem",
    "ImpactSlice",
    "UnresolvedDependency",
    "audit_capsule_tests",
    "build_dependency_graph",
    "governed_production_subsystems",
]
