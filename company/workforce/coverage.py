"""Who can actually do the work, and who could if someone woke them up.

## The distinction the whole module exists for

Constitution rule 18: *a defined employee is not a running employee*. A dormant
`visual_cinematography_director` is a real organizational capability - the role
exists, the contract exists, activating it is a decision rather than a hire -
and it is zero execution capacity right now. Collapsing those two into one
boolean is how an organization concludes it needs to hire someone it already
employs.

So every answer here comes in two levels:

    ACTIVE        someone who is running today provides it
    DORMANT_ONLY  the company has it; nobody is currently running it
    UNCOVERED     nobody has it at all

and the aggregate `CoverageStatus` over a required set is `FULL` only when
every capability has an active provider. `PARTIAL` means at least one
capability is covered and at least one is not actively covered; the report
always carries the per-capability breakdown, because the aggregate alone can
never tell you which lever to pull.

## Single points of failure

A capability with exactly one organizational provider. Counted over active plus
dormant rather than active alone: the question a SPOF answers is "what happens
if this employee is archived", and a dormant provider does not make an
organization redundant, it makes it slow.

Employees in a restricted state - candidate, shadow, probation - are counted in
neither. `capabilities.CapabilityRegistry.providers` explains why: a candidate
being evaluated for a gap is not the answer to that gap.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .capabilities import CapabilityRegistry, Criticality, ResolvedCapability
from .errors import WorkforceError


class CoverageLevel(Enum):
    ACTIVE = "active"
    DORMANT_ONLY = "dormant_only"
    UNCOVERED = "uncovered"


class CoverageStatus(Enum):
    FULL = "fully_covered"
    PARTIAL = "partially_covered"
    NONE = "uncovered"


@dataclass(frozen=True)
class CapabilityCoverage:
    """One capability's answer, with the providers that justify it."""

    capability_id: str
    level: CoverageLevel
    criticality: Criticality
    active_providers: tuple[str, ...]
    dormant_providers: tuple[str, ...]
    restricted_providers: tuple[str, ...]

    @property
    def organizational_providers(self) -> tuple[str, ...]:
        return tuple(sorted(self.active_providers + self.dormant_providers))

    @property
    def is_single_point_of_failure(self) -> bool:
        return len(self.organizational_providers) == 1

    @property
    def covered_organizationally(self) -> bool:
        return bool(self.organizational_providers)

    @property
    def covered_actively(self) -> bool:
        return bool(self.active_providers)

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "level": self.level.value,
            "criticality": self.criticality.value,
            "active_providers": list(self.active_providers),
            "dormant_providers": list(self.dormant_providers),
            "restricted_providers": list(self.restricted_providers),
            "single_point_of_failure": self.is_single_point_of_failure,
        }


@dataclass(frozen=True)
class CoverageReport:
    """The answer to 'can we do this work, and with whom'."""

    required: tuple[str, ...]
    coverages: tuple[CapabilityCoverage, ...]

    def __post_init__(self) -> None:
        if not self.required:
            raise WorkforceError("a coverage report needs at least one required capability")
        by_id = {coverage.capability_id for coverage in self.coverages}
        if by_id != set(self.required):
            raise WorkforceError(
                "coverage report must carry exactly one coverage per required capability"
            )

    # -- the three buckets ------------------------------------------------

    @property
    def fully_covered(self) -> tuple[str, ...]:
        """Capabilities an active employee provides right now."""
        return tuple(c.capability_id for c in self.coverages if c.level is CoverageLevel.ACTIVE)

    @property
    def partially_covered(self) -> tuple[str, ...]:
        """Capabilities the company has, but only in dormant employees."""
        return tuple(
            c.capability_id for c in self.coverages if c.level is CoverageLevel.DORMANT_ONLY
        )

    @property
    def uncovered(self) -> tuple[str, ...]:
        return tuple(c.capability_id for c in self.coverages if c.level is CoverageLevel.UNCOVERED)

    # -- provider views ---------------------------------------------------

    @property
    def active_employees(self) -> tuple[str, ...]:
        return tuple(sorted({e for c in self.coverages for e in c.active_providers}))

    @property
    def dormant_employees(self) -> tuple[str, ...]:
        return tuple(sorted({e for c in self.coverages for e in c.dormant_providers}))

    @property
    def single_points_of_failure(self) -> tuple[str, ...]:
        return tuple(c.capability_id for c in self.coverages if c.is_single_point_of_failure)

    @property
    def status(self) -> CoverageStatus:
        if not self.uncovered and not self.partially_covered:
            return CoverageStatus.FULL
        if self.fully_covered or self.partially_covered:
            return CoverageStatus.PARTIAL
        return CoverageStatus.NONE

    def get(self, capability_id: str) -> CapabilityCoverage:
        for coverage in self.coverages:
            if coverage.capability_id == capability_id:
                return coverage
        raise WorkforceError(f"{capability_id!r} is not in this coverage report")

    def providers_of(self, capability_id: str) -> tuple[str, ...]:
        return self.get(capability_id).organizational_providers

    def employees_covering_all(self, *, active_only: bool = False) -> tuple[str, ...]:
        """Employees who single-handedly provide every required capability.

        Sorted, active first. `active_only` is what "use an existing employee"
        actually means: a dormant employee who covers everything is an
        *activation*, not a routing decision, and returning them here would let
        the proposal layer answer a real workforce question with "do nothing".
        """
        candidates = set(self.active_employees) | set(self.dormant_employees)
        full = {
            employee
            for employee in candidates
            if all(employee in c.organizational_providers for c in self.coverages)
        }
        active = sorted(full & set(self.active_employees))
        if active_only:
            return tuple(active)
        return tuple(active + sorted(full - set(self.active_employees)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "required": list(self.required),
            "status": self.status.value,
            "fully_covered": list(self.fully_covered),
            "partially_covered": list(self.partially_covered),
            "uncovered": list(self.uncovered),
            "active_employees": list(self.active_employees),
            "dormant_employees": list(self.dormant_employees),
            "single_points_of_failure": list(self.single_points_of_failure),
            "coverages": [coverage.to_dict() for coverage in self.coverages],
        }


def coverage_of(resolved: ResolvedCapability) -> CapabilityCoverage:
    if resolved.active_providers:
        level = CoverageLevel.ACTIVE
    elif resolved.dormant_providers:
        level = CoverageLevel.DORMANT_ONLY
    else:
        level = CoverageLevel.UNCOVERED
    return CapabilityCoverage(
        capability_id=resolved.capability_id,
        level=level,
        criticality=resolved.capability.criticality,
        active_providers=resolved.active_providers,
        dormant_providers=resolved.dormant_providers,
        restricted_providers=resolved.restricted_providers,
    )


def assess_coverage(
    required_capabilities: Iterable[str],
    registry: CapabilityRegistry,
    *,
    expand: bool = False,
) -> CoverageReport:
    """Coverage for an explicit required set, in sorted capability order.

    `expand=True` pulls in everything the required capabilities comprise and
    require, which is how a task that asks for `cinematography` finds out that
    nobody covers `occlusion_analysis`. It is off by default: expanding a
    requirement silently would turn one honest gap into four invented ones.
    """
    required = tuple(sorted({str(item) for item in required_capabilities}))
    if not required:
        raise WorkforceError("at least one required capability is needed")
    unknown = [item for item in required if item not in registry.graph]
    if unknown:
        raise WorkforceError(
            "unknown capabilities: " + ", ".join(unknown) + " - register a capability "
            "before requiring it, so a typo cannot become a hiring proposal"
        )
    if expand:
        required = registry.graph.expand(required)
    return CoverageReport(
        required=required,
        coverages=tuple(coverage_of(registry.providers(item)) for item in required),
    )


def organization_single_points_of_failure(
    registry: CapabilityRegistry,
    *,
    minimum_criticality: Criticality = Criticality.IMPORTANT,
) -> tuple[CapabilityCoverage, ...]:
    """Every capability with exactly one organizational provider, worst first.

    `minimum_criticality` keeps the list readable: a single provider for an
    exploratory capability is a fact, not a risk.
    """
    order = {
        Criticality.CORE: 0,
        Criticality.IMPORTANT: 1,
        Criticality.SUPPORTING: 2,
        Criticality.EXPLORATORY: 3,
    }
    threshold = order[minimum_criticality]
    found = [
        coverage
        for coverage in (coverage_of(item) for item in registry.resolved())
        if coverage.is_single_point_of_failure and order[coverage.criticality] <= threshold
    ]
    return tuple(sorted(found, key=lambda c: (order[c.criticality], c.capability_id)))


def uncovered_critical_capabilities(registry: CapabilityRegistry) -> tuple[str, ...]:
    """Core capabilities with no provider at all. An integrity failure, not a gap."""
    return tuple(
        resolved.capability_id
        for resolved in registry.resolved()
        if resolved.capability.criticality is Criticality.CORE and not resolved.provided_by
    )
