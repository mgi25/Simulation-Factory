"""The shape of the org chart, as facts rather than judgements.

## What this module will and will not say

It will say: `creative_format_director` has one direct report and a manager of
its own. That is a property of `org_registry.yaml`, checkable by anyone, and it
is what "duplicated management layer" means here.

It will not say that `creative_format_director` is a bad manager, an unnecessary
one, or one whose removal would help. A pass-through layer is sometimes exactly
right - it is how a specialism gets a reviewer who understands it - and nothing
in a graph can tell the two cases apart. The brief is explicit about this, and
so is the code: every function here returns a structural fact, and turning one
into a recommendation takes a finding with evidence a person supplied.

## Every threshold is an argument, not a constant

`ManagementPolicy` holds the span of control, the maximum depth and which
departments count as management. Six direct reports is not a fact about the
world; it is this company's current opinion, and the shipped registry sits
exactly on it. Putting it in a dataclass that the review then records means a
review nobody can reproduce is impossible: the number that produced the finding
is in the finding's own configuration.

## Depth in the presence of a cycle

`depth_of` returns `None` for anyone inside or below a manager cycle, rather
than a number or an exception. A cycle has no depth, an arbitrary number would
be a lie, and raising would stop a caller from reporting the cycle - which is
the one thing they actually need to hear.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from knowledge.company_os.records import Evidence

from .common import positive_int
from .errors import OrgIntelligenceError
from .signals import (
    Direction,
    Measurement,
    OrganizationalSignal,
    SignalType,
    SubjectKind,
)
from .window import ReviewWindow

# Where the org registry lives, used as the evidence pointer for every
# structural signal this module produces. A caller analysing a hypothetical
# registry passes its own path, so the evidence never points at a file the
# numbers did not come from.
DEFAULT_REGISTRY_REF = "company/org_registry.yaml"


@dataclass(frozen=True)
class ManagementPolicy:
    """Every threshold, visible, so a review can record what it used."""

    max_span_of_control: int = 6
    max_depth: int = 4
    management_departments: tuple[str, ...] = ("executive",)
    external_root: str = "ceo"

    def __post_init__(self) -> None:
        positive_int(self.max_span_of_control, "max_span_of_control")
        positive_int(self.max_depth, "max_depth")
        if not isinstance(self.management_departments, tuple) or any(
            not isinstance(item, str) or not item for item in self.management_departments
        ):
            raise OrgIntelligenceError("management_departments must be a tuple of names")
        if not isinstance(self.external_root, str) or not self.external_root.strip():
            raise OrgIntelligenceError(
                "external_root names who the top of the chart reports to, such as 'ceo'"
            )


DEFAULT_MANAGEMENT_POLICY = ManagementPolicy()


@dataclass(frozen=True)
class ManagementGraph:
    """The manager edges of one org registry. Read-only, by construction."""

    employees: tuple[str, ...]
    manager_of: Mapping[str, str]
    department_of: Mapping[str, str]
    external_root: str = "ceo"
    registry_ref: str = DEFAULT_REGISTRY_REF

    @classmethod
    def from_org_registry(
        cls,
        org_registry: Mapping[str, Any],
        *,
        policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY,
        registry_ref: str = DEFAULT_REGISTRY_REF,
    ) -> ManagementGraph:
        employees = org_registry.get("employees") if isinstance(org_registry, Mapping) else None
        if not isinstance(employees, Mapping):
            raise OrgIntelligenceError(
                "org_registry must be a mapping with an 'employees' mapping"
            )
        ids = tuple(sorted(str(key) for key in employees))
        return cls(
            employees=ids,
            manager_of={
                employee_id: str(employees[employee_id].get("manager", ""))
                for employee_id in ids
                if isinstance(employees[employee_id], Mapping)
            },
            department_of={
                employee_id: str(employees[employee_id].get("department", ""))
                for employee_id in ids
                if isinstance(employees[employee_id], Mapping)
            },
            external_root=policy.external_root,
            registry_ref=registry_ref,
        )

    # -- edges -------------------------------------------------------------

    def direct_reports(self, employee_id: str) -> tuple[str, ...]:
        return tuple(
            other for other in self.employees if self.manager_of.get(other) == employee_id
        )

    def span_of_control(self) -> tuple[tuple[str, int], ...]:
        """(employee, direct reports) for everyone who has any, sorted."""
        return tuple(
            (employee_id, len(self.direct_reports(employee_id)))
            for employee_id in self.employees
            if self.direct_reports(employee_id)
        )

    # -- structural facts --------------------------------------------------

    def orphans(self) -> tuple[str, ...]:
        """Employees who declare no manager at all."""
        return tuple(
            employee_id
            for employee_id in self.employees
            if not str(self.manager_of.get(employee_id, "")).strip()
        )

    def invalid_references(self) -> tuple[tuple[str, str], ...]:
        """(employee, manager) pairs whose manager is neither an employee nor the root."""
        return tuple(
            (employee_id, manager)
            for employee_id in self.employees
            if (manager := str(self.manager_of.get(employee_id, "")).strip())
            and manager != self.external_root
            and manager not in set(self.employees)
        )

    def cycles(self) -> tuple[tuple[str, ...], ...]:
        """Every manager cycle, each rotated to start at its smallest member.

        Rotating makes the output stable: the same cycle discovered from two
        different starting employees produces one entry, not two.
        """
        found: set[tuple[str, ...]] = set()
        known = set(self.employees)
        for start in self.employees:
            seen: list[str] = []
            current = start
            while current in known and current not in seen:
                seen.append(current)
                current = str(self.manager_of.get(current, "")).strip()
            if current in seen:
                cycle = seen[seen.index(current) :]
                pivot = cycle.index(min(cycle))
                found.add(tuple(cycle[pivot:] + cycle[:pivot]))
        return tuple(sorted(found))

    def in_cycle(self) -> frozenset[str]:
        """Everyone inside a cycle, or reporting up into one."""
        cyclic = {member for cycle in self.cycles() for member in cycle}
        if not cyclic:
            return frozenset()
        affected = set(cyclic)
        for employee_id in self.employees:
            seen: set[str] = set()
            current = employee_id
            while current in set(self.employees) and current not in seen:
                seen.add(current)
                if current in cyclic:
                    affected |= seen
                    break
                current = str(self.manager_of.get(current, "")).strip()
        return frozenset(affected)

    def depth_of(self, employee_id: str) -> int | None:
        """Hops from the external root. `None` inside or below a cycle.

        The root is depth 0 and is not an employee, so someone reporting
        straight to the CEO is depth 1.
        """
        if employee_id not in set(self.employees):
            raise OrgIntelligenceError(f"unknown employee {employee_id!r}")
        if employee_id in self.in_cycle():
            return None
        depth = 0
        current = employee_id
        known = set(self.employees)
        while current in known:
            depth += 1
            manager = str(self.manager_of.get(current, "")).strip()
            if not manager or manager == self.external_root:
                return depth
            current = manager
        return depth

    def depths(self) -> tuple[tuple[str, int | None], ...]:
        return tuple((employee_id, self.depth_of(employee_id)) for employee_id in self.employees)

    def managers_without_reports(
        self, policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY
    ) -> tuple[str, ...]:
        """Employees in a management department who manage nobody.

        Whether a role is managerial cannot be read off a manager edge - an
        employee with no reports simply has no reports. So the question is
        answered by declared department, which is explicit configuration.
        """
        wanted = set(policy.management_departments)
        return tuple(
            employee_id
            for employee_id in self.employees
            if self.department_of.get(employee_id, "") in wanted
            and not self.direct_reports(employee_id)
        )

    def oversized_spans(
        self, policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY
    ) -> tuple[tuple[str, int], ...]:
        return tuple(
            (employee_id, count)
            for employee_id, count in self.span_of_control()
            if count > policy.max_span_of_control
        )

    def excessive_depth(
        self, policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY
    ) -> tuple[tuple[str, int], ...]:
        return tuple(
            (employee_id, depth)
            for employee_id, depth in self.depths()
            if depth is not None and depth > policy.max_depth
        )

    def pass_through_managers(self) -> tuple[tuple[str, str], ...]:
        """(manager, its one report) where the manager also reports to someone.

        A layer with exactly one person under it and someone above it. A fact,
        not a verdict: it is how a specialism gets a reviewer who understands
        it, and it is also how an org chart grows a layer nobody needs. Which
        one it is takes evidence this graph does not hold.
        """
        out: list[tuple[str, str]] = []
        for employee_id in self.employees:
            reports = self.direct_reports(employee_id)
            manager = str(self.manager_of.get(employee_id, "")).strip()
            if len(reports) == 1 and manager:
                out.append((employee_id, reports[0]))
        return tuple(out)

    def to_dict(self) -> dict[str, Any]:
        return {
            "employees": list(self.employees),
            "manager_of": dict(sorted(self.manager_of.items())),
            "department_of": dict(sorted(self.department_of.items())),
            "external_root": self.external_root,
            "registry_ref": self.registry_ref,
            "cycles": [list(cycle) for cycle in self.cycles()],
            "depths": [[employee_id, depth] for employee_id, depth in self.depths()],
        }


def management_signals(
    graph: ManagementGraph,
    *,
    window: ReviewWindow,
    policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY,
    prefix: str = "sig-mgmt",
) -> tuple[OrganizationalSignal, ...]:
    """Every structural fact the graph supports, as signals, in a stable order.

    The evidence is the registry file itself, which is the honest pointer: a
    second person checks this by opening it. Nothing here is a bottleneck claim
    - `MANAGEMENT_SPAN` says a number crossed a configured line, and the line is
    carried on the measurement so the reader can disagree with it.
    """
    evidence = (
        Evidence(
            kind="document",
            ref=graph.registry_ref,
            note="manager edges read from the org registry",
        ),
    )
    out: list[OrganizationalSignal] = []

    for index, cycle in enumerate(graph.cycles(), start=1):
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-cycle-{index}",
                type=SignalType.MANAGEMENT_CYCLE,
                subject=cycle[0],
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail="manager cycle: " + " -> ".join(cycle + (cycle[0],)),
                measurement=Measurement(
                    value=float(len(cycle)), unit="employees_in_cycle"
                ),
                evidence=evidence,
                caveats=(
                    "a cycle has no depth; every employee inside or below it reports an "
                    "unmeasurable management depth",
                ),
            )
        )

    for employee_id, manager in graph.invalid_references():
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-invalid-ref-{employee_id.replace('_', '-')}",
                type=SignalType.INVALID_MANAGEMENT_REFERENCE,
                subject=employee_id,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=(
                    f"{employee_id} names {manager!r} as manager; that is neither an "
                    f"employee nor the external root {graph.external_root!r}"
                ),
                evidence=evidence,
                missing_measurements=("nothing to count: this is a broken reference",),
            )
        )

    for employee_id in graph.orphans():
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-orphan-{employee_id.replace('_', '-')}",
                type=SignalType.ORPHAN_ROLE,
                subject=employee_id,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=f"{employee_id} declares no manager",
                evidence=evidence,
                missing_measurements=("nothing to count: this is a missing reference",),
            )
        )

    for employee_id, count in graph.oversized_spans(policy):
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-span-{employee_id.replace('_', '-')}",
                type=SignalType.MANAGEMENT_SPAN,
                subject=employee_id,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=(
                    f"{employee_id} has {count} direct reports, above the configured "
                    f"span of {policy.max_span_of_control}"
                ),
                measurement=Measurement(
                    value=float(count),
                    unit="direct_reports",
                    threshold=float(policy.max_span_of_control),
                    direction=Direction.HIGHER_IS_WORSE,
                ),
                evidence=evidence,
                caveats=(
                    "span of control is a configured threshold, not a measured cost; "
                    "no coordination latency was observed here",
                ),
            )
        )

    for employee_id, depth in graph.excessive_depth(policy):
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-depth-{employee_id.replace('_', '-')}",
                type=SignalType.MANAGEMENT_DEPTH,
                subject=employee_id,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=(
                    f"{employee_id} sits {depth} hop(s) from {graph.external_root}, above "
                    f"the configured maximum of {policy.max_depth}"
                ),
                measurement=Measurement(
                    value=float(depth),
                    unit="hops_to_root",
                    threshold=float(policy.max_depth),
                    direction=Direction.HIGHER_IS_WORSE,
                ),
                evidence=evidence,
            )
        )

    for employee_id in graph.managers_without_reports(policy):
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-no-reports-{employee_id.replace('_', '-')}",
                type=SignalType.MANAGEMENT_BOTTLENECK,
                subject=employee_id,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=(
                    f"{employee_id} is in a management department "
                    f"({graph.department_of.get(employee_id, '')}) and has no direct reports"
                ),
                measurement=Measurement(value=0.0, unit="direct_reports"),
                evidence=evidence,
                caveats=(
                    "an executive with no reports may be an individual contributor by "
                    "design; this says nothing about whether the role is needed",
                ),
            )
        )

    for manager, report in graph.pass_through_managers():
        out.append(
            OrganizationalSignal(
                signal_id=f"{prefix}-passthrough-{manager.replace('_', '-')}",
                type=SignalType.DUPLICATED_MANAGEMENT_LAYER,
                subject=manager,
                subject_kind=SubjectKind.EMPLOYEE,
                window=window,
                detail=(
                    f"{manager} has exactly one direct report ({report}) and reports to "
                    f"{graph.manager_of.get(manager, '')}"
                ),
                measurement=Measurement(value=1.0, unit="direct_reports"),
                evidence=evidence,
                caveats=(
                    "a single-report layer is a shape, not a cost; whether it compresses "
                    "or multiplies coordination (constitution rule 19) is unmeasured here",
                ),
            )
        )

    return tuple(out)
