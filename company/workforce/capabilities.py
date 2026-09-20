"""What the company can do, named once, related explicitly.

## Why a capability record carries no provider list

`org_registry.yaml` already says which employee has which capability. The
obvious capability record would repeat that as a `provided_by` list, and the
two would be consistent for about a week. Constitution rule 15: a canonical
fact is stored once and retrieved.

So `Capability` has no `provided_by` field. Providers are *derived* from the
org registry by `CapabilityRegistry.providers()`, and `ResolvedCapability` is
the view that carries them. The registry cannot go stale against the org
registry, because there is nothing in it to go stale.

What the capability record does own is what the org registry has no place for:
the human-readable definition, the domain, how critical the capability is, and
the relations between capabilities.

## Three relation kinds, two of them acyclic

    COMPRISES   a broad capability decomposes into narrower ones
                (cinematography comprises framing, camera_continuity, ...)
    REQUIRES    a capability cannot be exercised without another
    RELATED_TO  symmetric adjacency, used to find retraining candidates

`COMPRISES` and `REQUIRES` are directed and must be acyclic: a capability that
comprises itself through a chain is a modelling error, and one that requires
itself can never be satisfied. `RELATED_TO` is symmetric, so a cycle in it is
the normal case and checking for one would be noise. That is the whole content
of "detect cycles where the chosen relationship semantics require acyclicity" -
the check follows the semantics rather than being applied uniformly and wrongly.

Nothing here infers a relation. Relations are data, loaded from
`capability_registry.json`, and no function in this module reads a description
to guess an edge.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.serde import read_json, to_jsonable

from .common import assert_identifier, assert_prose, id_tuple
from .errors import WorkforceError

DEFAULT_REGISTRY_PATH = Path(__file__).resolve().parent / "capability_registry.json"


class Criticality(Enum):
    """How much the company loses when nobody can do this.

    `CORE` is the one with teeth: a core capability with no provider is an
    integrity failure, not a backlog item.
    """

    CORE = "core"
    IMPORTANT = "important"
    SUPPORTING = "supporting"
    EXPLORATORY = "exploratory"


class CapabilityStatus(Enum):
    ACTIVE = "active"
    PROPOSED = "proposed"
    DEPRECATED = "deprecated"


class RelationKind(Enum):
    COMPRISES = "comprises"
    REQUIRES = "requires"
    RELATED_TO = "related_to"

    @property
    def acyclic(self) -> bool:
        return self is not RelationKind.RELATED_TO

    @property
    def symmetric(self) -> bool:
        return self is RelationKind.RELATED_TO


@dataclass(frozen=True)
class Capability:
    """One named thing the company can do, defined independently of who does it."""

    capability_id: str
    name: str
    description: str
    domain: str
    criticality: Criticality = Criticality.SUPPORTING
    status: CapabilityStatus = CapabilityStatus.ACTIVE
    # Role or task types that have been *explicitly registered* as needing this.
    # Never inferred: an empty tuple means nobody wrote it down, not that
    # nothing needs the capability.
    required_by: tuple[str, ...] = ()
    notes: str = ""

    def __post_init__(self) -> None:
        assert_identifier(self.capability_id, "capability_id")
        assert_prose(self.name, f"capability {self.capability_id} name")
        assert_prose(self.description, f"capability {self.capability_id} description")
        assert_identifier(self.domain, f"capability {self.capability_id} domain")
        if not isinstance(self.criticality, Criticality):
            raise WorkforceError(
                f"capability {self.capability_id}: criticality must be a Criticality"
            )
        if not isinstance(self.status, CapabilityStatus):
            raise WorkforceError(
                f"capability {self.capability_id}: status must be a CapabilityStatus"
            )
        object.__setattr__(
            self,
            "required_by",
            id_tuple(
                self.required_by,
                f"capability {self.capability_id} required_by",
                sort=True,
            ),
        )
        if not isinstance(self.notes, str):
            raise WorkforceError(f"capability {self.capability_id}: notes must be a string")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Capability:
        return cls(
            capability_id=data["capability_id"],
            name=data["name"],
            description=data["description"],
            domain=data["domain"],
            criticality=Criticality(data.get("criticality", Criticality.SUPPORTING.value)),
            status=CapabilityStatus(data.get("status", CapabilityStatus.ACTIVE.value)),
            required_by=tuple(data.get("required_by", ())),
            notes=data.get("notes", ""),
        )


@dataclass(frozen=True)
class CapabilityRelation:
    """One explicit edge. Data, never inference."""

    kind: RelationKind
    source: str
    target: str
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.kind, RelationKind):
            raise WorkforceError("relation kind must be a RelationKind")
        assert_identifier(self.source, "relation source")
        assert_identifier(self.target, "relation target")
        if self.source == self.target:
            raise WorkforceError(
                f"relation {self.kind.value} {self.source!r} -> itself is not a relation"
            )
        if not isinstance(self.note, str):
            raise WorkforceError("relation note must be a string")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CapabilityRelation:
        return cls(
            kind=RelationKind(data["kind"]),
            source=data["source"],
            target=data["target"],
            note=data.get("note", ""),
        )


@dataclass(frozen=True)
class ResolvedCapability:
    """A capability plus the providers derived from the org registry.

    This is where `provided_by` lives, and it is a view rather than a record:
    it is computed on demand and never written to disk, so it cannot disagree
    with `org_registry.yaml`.
    """

    capability: Capability
    provided_by: tuple[str, ...]
    active_providers: tuple[str, ...]
    dormant_providers: tuple[str, ...]
    restricted_providers: tuple[str, ...]

    @property
    def capability_id(self) -> str:
        return self.capability.capability_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability": to_jsonable(self.capability),
            "provided_by": list(self.provided_by),
            "active_providers": list(self.active_providers),
            "dormant_providers": list(self.dormant_providers),
            "restricted_providers": list(self.restricted_providers),
        }


@dataclass(frozen=True)
class CapabilityGraph:
    """Capabilities and their explicit relations, with the cycle check on load."""

    capabilities: tuple[Capability, ...]
    relations: tuple[CapabilityRelation, ...] = ()
    _by_id: dict[str, Capability] = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self) -> None:
        by_id: dict[str, Capability] = {}
        for capability in self.capabilities:
            if not isinstance(capability, Capability):
                raise WorkforceError("capabilities must be Capability records")
            if capability.capability_id in by_id:
                raise WorkforceError(
                    f"duplicate capability id {capability.capability_id!r}: one name must "
                    "have one definition, or coverage answers depend on load order"
                )
            by_id[capability.capability_id] = capability
        object.__setattr__(self, "_by_id", by_id)

        for relation in self.relations:
            if not isinstance(relation, CapabilityRelation):
                raise WorkforceError("relations must be CapabilityRelation records")
            for role, capability_id in (
                ("source", relation.source),
                ("target", relation.target),
            ):
                if capability_id not in by_id:
                    raise WorkforceError(
                        f"relation {relation.kind.value} names unknown capability "
                        f"{capability_id!r} as {role}"
                    )
        cycles = self.cycles()
        if cycles:
            rendered = "; ".join(" -> ".join(cycle) for cycle in cycles)
            raise WorkforceError(f"capability relation cycle detected: {rendered}")

    # -- lookup -----------------------------------------------------------

    def __len__(self) -> int:
        return len(self._by_id)

    def __contains__(self, capability_id: object) -> bool:
        return capability_id in self._by_id

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_id))

    def get(self, capability_id: str) -> Capability:
        try:
            return self._by_id[capability_id]
        except KeyError:
            raise WorkforceError(f"unknown capability {capability_id!r}") from None

    def sorted_capabilities(self) -> tuple[Capability, ...]:
        return tuple(self._by_id[key] for key in sorted(self._by_id))

    def by_domain(self, domain: str) -> tuple[Capability, ...]:
        return tuple(c for c in self.sorted_capabilities() if c.domain == domain)

    def by_criticality(self, criticality: Criticality) -> tuple[Capability, ...]:
        return tuple(c for c in self.sorted_capabilities() if c.criticality is criticality)

    # -- traversal --------------------------------------------------------

    def edges(self, kind: RelationKind) -> dict[str, tuple[str, ...]]:
        """Adjacency for one relation kind, symmetric kinds expanded both ways."""
        out: dict[str, list[str]] = {key: [] for key in self._by_id}
        for relation in self.relations:
            if relation.kind is not kind:
                continue
            out[relation.source].append(relation.target)
            if kind.symmetric:
                out[relation.target].append(relation.source)
        return {key: tuple(sorted(set(value))) for key, value in out.items()}

    def descendants(
        self, capability_id: str, kind: RelationKind = RelationKind.COMPRISES
    ) -> tuple[str, ...]:
        """Everything reachable from `capability_id` along `kind`, sorted.

        Breadth-first with a visited set, so it terminates even on the cyclic
        `RELATED_TO` kind - which is exactly why the cycle check is per kind
        and the traversal is not.
        """
        self.get(capability_id)
        adjacency = self.edges(kind)
        seen: set[str] = set()
        frontier = list(adjacency[capability_id])
        while frontier:
            current = frontier.pop()
            if current in seen or current == capability_id:
                continue
            seen.add(current)
            frontier.extend(adjacency[current])
        return tuple(sorted(seen))

    def ancestors(
        self, capability_id: str, kind: RelationKind = RelationKind.COMPRISES
    ) -> tuple[str, ...]:
        self.get(capability_id)
        return tuple(
            sorted(
                other
                for other in self._by_id
                if other != capability_id and capability_id in self.descendants(other, kind)
            )
        )

    def expand(self, capability_ids: Iterable[str]) -> tuple[str, ...]:
        """A required set plus everything it comprises and requires.

        Used when a task names `cinematography` and the honest question is
        whether anyone can do the narrower things it decomposes into.
        """
        out: set[str] = set()
        for capability_id in capability_ids:
            out.add(self.get(capability_id).capability_id)
            out.update(self.descendants(capability_id, RelationKind.COMPRISES))
            out.update(self.descendants(capability_id, RelationKind.REQUIRES))
        return tuple(sorted(out))

    def adjacent(self, capability_ids: Iterable[str]) -> tuple[str, ...]:
        """Capabilities one explicit hop away, over every relation kind.

        This is the retraining question: someone who already does the
        neighbours of a missing capability is a cheaper answer than a hire.
        """
        wanted = {self.get(capability_id).capability_id for capability_id in capability_ids}
        out: set[str] = set()
        for kind in RelationKind:
            adjacency = self.edges(kind)
            for capability_id in wanted:
                out.update(adjacency[capability_id])
            for source, targets in adjacency.items():
                if wanted.intersection(targets):
                    out.add(source)
        return tuple(sorted(out - wanted))

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Every cycle in the acyclic-by-semantics relation kinds, sorted.

        Depth-first with an explicit stack: a capability graph is small, but a
        recursive walk over loaded data is a stack overflow waiting for a bad
        file.
        """
        found: set[tuple[str, ...]] = set()
        for kind in RelationKind:
            if not kind.acyclic:
                continue
            adjacency = self.edges(kind)
            colour: dict[str, int] = {key: 0 for key in adjacency}
            for start in sorted(adjacency):
                if colour[start]:
                    continue
                path: list[str] = []
                stack: list[tuple[str, int]] = [(start, 0)]
                while stack:
                    node, index = stack.pop()
                    if index == 0:
                        if colour[node] == 2:
                            continue
                        colour[node] = 1
                        path.append(node)
                    targets = adjacency[node]
                    if index < len(targets):
                        stack.append((node, index + 1))
                        nxt = targets[index]
                        if colour[nxt] == 1:
                            found.add(tuple(path[path.index(nxt) :] + [nxt]))
                        elif colour[nxt] == 0:
                            stack.append((nxt, 0))
                    else:
                        colour[node] = 2
                        path.pop()
        return tuple(sorted(found))


class CapabilityRegistry:
    """The capability graph plus the org registry it derives providers from.

    Two arguments, deliberately. Splitting the definition (this package's data)
    from the workforce (`org_registry.yaml`) is what lets the capability model
    be edited without touching the shared root contract, and what stops this
    module from ever needing to write one.
    """

    ACTIVE_STATES = frozenset({"active"})
    DORMANT_STATES = frozenset({"dormant"})
    RESTRICTED_STATES = frozenset({"candidate", "shadow", "probation"})
    EXCLUDED_STATES = frozenset({"archived"})

    def __init__(self, graph: CapabilityGraph, org_registry: Mapping[str, Any]) -> None:
        if not isinstance(graph, CapabilityGraph):
            raise WorkforceError("graph must be a CapabilityGraph")
        employees = org_registry.get("employees") if isinstance(org_registry, Mapping) else None
        if not isinstance(employees, Mapping):
            raise WorkforceError("org_registry must be a mapping with an 'employees' mapping")
        self.graph = graph
        self._employees: dict[str, dict[str, Any]] = {
            str(employee_id): dict(employee)
            for employee_id, employee in sorted(employees.items(), key=lambda kv: str(kv[0]))
            if isinstance(employee, Mapping)
        }

    @classmethod
    def load(
        cls,
        org_registry: Mapping[str, Any],
        registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    ) -> CapabilityRegistry:
        return cls(load_capability_graph(registry_path), org_registry)

    # -- employees --------------------------------------------------------

    @property
    def employee_ids(self) -> tuple[str, ...]:
        return tuple(self._employees)

    def employee_state(self, employee_id: str) -> str:
        try:
            return str(self._employees[employee_id].get("state", ""))
        except KeyError:
            raise WorkforceError(f"unknown employee {employee_id!r}") from None

    def employee_capabilities(self, employee_id: str) -> tuple[str, ...]:
        try:
            employee = self._employees[employee_id]
        except KeyError:
            raise WorkforceError(f"unknown employee {employee_id!r}") from None
        raw = employee.get("capabilities", [])
        return tuple(sorted(str(item) for item in raw if isinstance(item, str)))

    def employee_manager(self, employee_id: str) -> str:
        try:
            return str(self._employees[employee_id].get("manager", ""))
        except KeyError:
            raise WorkforceError(f"unknown employee {employee_id!r}") from None

    # -- derived providers ------------------------------------------------

    def providers(self, capability_id: str) -> ResolvedCapability:
        """Who provides one capability, split by what their state actually means.

        `active` is execution capacity now. `dormant` is organizational
        capability that a decision could wake up. `restricted` - candidate,
        shadow, probation - is neither: those employees are being evaluated,
        and counting them as coverage would answer "do we need a hire?" with
        the very person whose evaluation has not finished.
        """
        self.graph.get(capability_id)
        active: list[str] = []
        dormant: list[str] = []
        restricted: list[str] = []
        for employee_id in self._employees:
            if capability_id not in self.employee_capabilities(employee_id):
                continue
            state = self.employee_state(employee_id)
            if state in self.ACTIVE_STATES:
                active.append(employee_id)
            elif state in self.DORMANT_STATES:
                dormant.append(employee_id)
            elif state in self.RESTRICTED_STATES:
                restricted.append(employee_id)
        return ResolvedCapability(
            capability=self.graph.get(capability_id),
            provided_by=tuple(sorted(active + dormant)),
            active_providers=tuple(sorted(active)),
            dormant_providers=tuple(sorted(dormant)),
            restricted_providers=tuple(sorted(restricted)),
        )

    def resolved(self) -> tuple[ResolvedCapability, ...]:
        return tuple(self.providers(capability_id) for capability_id in self.graph.ids())

    def unregistered_employee_capabilities(self) -> tuple[tuple[str, str], ...]:
        """(employee_id, capability) pairs the capability registry does not define."""
        out: list[tuple[str, str]] = []
        for employee_id in self._employees:
            for capability_id in self.employee_capabilities(employee_id):
                if capability_id not in self.graph:
                    out.append((employee_id, capability_id))
        return tuple(sorted(out))

    def unused_capabilities(self) -> tuple[str, ...]:
        """Defined capabilities nobody in the org registry provides."""
        return tuple(
            capability_id
            for capability_id in self.graph.ids()
            if not self.providers(capability_id).provided_by
        )


def load_capability_graph(path: str | Path = DEFAULT_REGISTRY_PATH) -> CapabilityGraph:
    """Load the versioned capability definitions. Standard library JSON only."""
    source = Path(path)
    if not source.is_file():
        raise WorkforceError(f"capability registry not found at {source}")
    data = read_json(source)
    if not isinstance(data, Mapping):
        raise WorkforceError(f"{source}: a capability registry is a JSON object")
    if data.get("version") != 1:
        raise WorkforceError(f"{source}: capability registry version must be 1")
    capabilities = tuple(Capability.from_dict(item) for item in data.get("capabilities", ()))
    relations = tuple(CapabilityRelation.from_dict(item) for item in data.get("relations", ()))
    return CapabilityGraph(capabilities=capabilities, relations=relations)


def graph_to_dict(graph: CapabilityGraph) -> dict[str, Any]:
    """The canonical on-disk shape, for a round trip that is byte-stable."""
    return {
        "version": 1,
        "capabilities": [to_jsonable(c) for c in graph.sorted_capabilities()],
        "relations": [
            to_jsonable(r)
            for r in sorted(graph.relations, key=lambda r: (r.kind.value, r.source, r.target))
        ],
    }
