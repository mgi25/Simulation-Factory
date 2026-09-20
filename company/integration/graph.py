"""Cycle detection over a plain mapping, and the two graphs the gate feeds it.

## Why the detector takes a mapping and not a repository

The architectural condition is "no forbidden dependency cycle". There are two
graphs it has to hold for - the capsule dependency graph, which is declared in
JSON, and the Company OS import graph, which is derived from source - and they
have nothing in common except their shape. So `find_cycles` takes
`{node: [node, ...]}` and knows nothing else, which is also what makes it
testable: a three-node cycle in a fixture proves the algorithm, and no fixture
has to reproduce the state of the real repository.

That matters here more than usual. At the time of writing, `company-runtime`
and `company-validation` declare each other, and a separate workstream is
removing that edge. A test asserting "the repository contains a cycle" would
pass today, fail the day the fix lands, and teach the next reader that the fix
broke something. The tests therefore prove the *detector* on synthetic graphs
and assert only the shape of the real result, so the same check turns green on
its own when the edge goes.

## Canonical output

A cycle has no first element, so one is chosen: the walk rotates each cycle to
start at its lexicographically smallest node and the list is sorted. Two runs
over the same graph produce the same tuples in the same order, which is what
lets a report be diffed.

Edges to nodes the graph does not define are ignored. A dangling dependency is
a real problem, but it is `CapsuleIndex.integrity`'s problem, and reporting it
twice in two vocabularies helps nobody.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from knowledge.company_os.capsules import CapsuleIndex

from .sources import SourceModule, module_imports, module_subsystem, subsystem_of


def find_cycles(graph: Mapping[str, Sequence[str]]) -> tuple[tuple[str, ...], ...]:
    """Every distinct cycle in `graph`, canonically rotated and sorted.

    Depth-first over sorted nodes and sorted edges. A self-loop is a cycle of
    one. The returned tuples do not repeat the entry node at the end; a cycle
    `a -> b -> a` is `("a", "b")`.
    """
    known = {str(node) for node in graph}
    colour: dict[str, int] = {}
    stack: list[str] = []
    found: set[tuple[str, ...]] = set()

    def walk(node: str) -> None:
        colour[node] = 1
        stack.append(node)
        for target in sorted({str(item) for item in graph.get(node, ())}):
            if target not in known:
                continue
            if colour.get(target, 0) == 1:
                found.add(_canonical(stack[stack.index(target) :]))
            elif colour.get(target, 0) == 0:
                walk(target)
        stack.pop()
        colour[node] = 2

    for node in sorted(known):
        if colour.get(node, 0) == 0:
            walk(node)
    return tuple(sorted(found))


def _canonical(cycle: Sequence[str]) -> tuple[str, ...]:
    items = tuple(cycle)
    pivot = items.index(min(items))
    return items[pivot:] + items[:pivot]


def render_cycle(cycle: Sequence[str]) -> str:
    """`a -> b -> a`: the form a reader can follow back to the two files."""
    items = list(cycle)
    return " -> ".join(items + [items[0]])


def capsule_dependency_graph(index: CapsuleIndex) -> dict[str, tuple[str, ...]]:
    """The declared capsule graph: what each capsule says it rests on."""
    return {capsule.id: tuple(capsule.dependencies) for capsule in index.all()}


def subsystem_import_graph(
    modules: Sequence[SourceModule], *, include_type_checking: bool = False
) -> dict[str, tuple[str, ...]]:
    """The Company OS import graph, one node per subsystem.

    `include_type_checking` is False by default because an import inside
    `if TYPE_CHECKING:` never executes: it cannot produce a circular-import
    error and it does not make one subsystem need the other at runtime. The
    checks report those edges separately rather than counting them here, so
    that a reader is told about the coupling without the gate calling it a
    cycle it is not.
    """
    graph: dict[str, set[str]] = {}
    for module in modules:
        source = subsystem_of(module.path)
        if not source:
            continue
        graph.setdefault(source, set())
        for ref in module_imports(module):
            if ref.type_checking and not include_type_checking:
                continue
            target = module_subsystem(ref.module)
            if target and target != source:
                graph[source].add(target)
    return {node: tuple(sorted(targets)) for node, targets in sorted(graph.items())}


def type_checking_edges(modules: Sequence[SourceModule]) -> tuple[str, ...]:
    """Subsystem edges that exist only inside `if TYPE_CHECKING:`, as references.

    Reported, not counted. These are the edges that make the runtime graph and
    the declared capsule graph disagree, and a reader chasing a capsule cycle
    that the import graph does not have needs to be pointed straight at them.
    """
    runtime = subsystem_import_graph(modules, include_type_checking=False)
    out: list[str] = []
    for module in modules:
        source = subsystem_of(module.path)
        if not source:
            continue
        for ref in module_imports(module):
            if not ref.type_checking:
                continue
            target = module_subsystem(ref.module)
            if target and target != source and target not in runtime.get(source, ()):
                out.append(f"{ref.reference()} ({source} -> {target})")
    return tuple(sorted(set(out)))


__all__ = [
    "capsule_dependency_graph",
    "find_cycles",
    "render_cycle",
    "subsystem_import_graph",
    "type_checking_edges",
]
