"""The delegation policy: who may decide what, and the limits it cannot break.

A policy is a hierarchy, a budget ladder, and one grant per seat. It is loaded
from `company/delegation_policy.yaml` through the same restricted YAML subset
the four canonical bootstrap contracts use, so a policy file that needs a YAML
feature the loader does not support is refused rather than half-read.

## Four structural refusals

These are enforced when the policy is constructed, not when a request arrives.
A policy that could express them would already be wrong on disk, and the point
of a deterministic authority model is that the wrongness is visible in a diff.

**A reserved action cannot be granted.** `reserved_action_types` reads
`permissions.yaml`, and a grant naming one of those raises. This is the rule
that makes the reserved list mean something: without it, a policy could delegate
`publish_public_video` to a department lead and the canonical file would still
say, truthfully and uselessly, that the CEO reserved it.

**The CEO seat receives no grant.** The CEO is where escalation terminates, not
a seat this model delegates to. A grant for `ceo` would let the policy describe
the CEO approving something automatically, which is the exact shape of the
record this subsystem must never be able to write.

**A subordinate may not out-rank its manager.** A grant whose risk ceiling or
budget ceiling exceeds its escalation target is refused. Otherwise escalation
would sometimes be a *demotion* — an action too risky for the engineering
manager travelling up to a CTO who may approve less.

**A granted action needs a declared autonomy level.** `action_autonomy` maps
each action type onto a rung of the canonical ladder in `permissions.yaml`, and
`Hierarchy.standing` compares that against the seat holder employment state.
An action with no declared level would be approvable by a probationary employee.

## Why `mode` exists and has one legal value

`DelegationMode.SHADOW` is the only value this version accepts. `ENFORCING` is
declared so the activation path is a named thing with a defined meaning rather
than an unwritten future, and constructing a policy with it raises
`ShadowModeViolation`. Turning it on is `change_delegation_policy`, which this
package reserves to the CEO unconditionally — so the switch cannot be flipped by
anything this subsystem can do.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money
from company.validation.errors import YamlSubsetError
from company.validation.yaml_subset import load_yaml_subset

from .actions import ActionType, parse_action, reserved_action_types
from .budget import BudgetLadder, BudgetLevel, BudgetScope, money_from_text
from .common import assert_prose, assert_seat_id, name_tuple
from .errors import AuthorityViolation, DelegationError, ShadowModeViolation
from .org import Hierarchy, Seat, SeatKind


POLICY_VERSION = "delegation_policy_v1"

DEFAULT_POLICY_FILE = "delegation_policy.yaml"

RISK_ORDER: tuple[Risk, ...] = (Risk.LOW, Risk.MEDIUM, Risk.HIGH, Risk.CRITICAL)


def risk_rank(risk: Risk) -> int:
    return RISK_ORDER.index(risk)


def parse_risk(value: Any, field_name: str = "risk") -> Risk:
    if isinstance(value, Risk):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field_name} must be a risk name, got {value!r}")
    try:
        return Risk(value.strip().lower())
    except ValueError as exc:
        allowed = ", ".join(item.value for item in RISK_ORDER)
        raise DelegationError(f"{field_name} must be one of: {allowed}") from exc


class DelegationMode(str, Enum):
    """Whether a decision is advice or authority. One legal value in v1."""

    SHADOW = "shadow"
    ENFORCING = "enforcing"


@dataclass(frozen=True)
class DelegatedAuthority:
    """What one seat may decide, and the ceilings it may not cross."""

    seat: str
    action_types: frozenset[ActionType]
    max_risk: Risk
    per_decision_ceiling: Money
    budget_scope: str
    may_request_corrections: bool = True
    may_stop_work: bool = True
    rationale: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "seat", assert_seat_id(self.seat, "grant.seat"))
        if not isinstance(self.action_types, frozenset) or not self.action_types:
            raise DelegationError(
                f"grant for {self.seat}: action_types must be a non-empty frozenset. "
                "A seat that may decide nothing is a vacancy, not a grant."
            )
        for action in self.action_types:
            if not isinstance(action, ActionType):
                raise DelegationError(
                    f"grant for {self.seat}: {action!r} is not an ActionType"
                )
        object.__setattr__(self, "max_risk", parse_risk(self.max_risk, "grant.max_risk"))
        if not isinstance(self.per_decision_ceiling, Money):
            raise DelegationError(
                f"grant for {self.seat}: per_decision_ceiling must be Money"
            )
        if self.per_decision_ceiling.is_negative:
            raise DelegationError(
                f"grant for {self.seat}: a ceiling is not negative"
            )
        object.__setattr__(
            self, "budget_scope", assert_prose(self.budget_scope, "grant.budget_scope")
        )
        for flag in ("may_request_corrections", "may_stop_work"):
            if not isinstance(getattr(self, flag), bool):
                raise DelegationError(f"grant for {self.seat}: {flag} must be a boolean")
        object.__setattr__(
            self,
            "rationale",
            assert_prose(self.rationale, "grant.rationale") if self.rationale else "",
        )

    def covers(self, action: ActionType) -> bool:
        return action in self.action_types

    def to_dict(self) -> dict[str, Any]:
        return {
            "seat": self.seat,
            "action_types": sorted(item.value for item in self.action_types),
            "max_risk": self.max_risk.value,
            "per_decision_ceiling": self.per_decision_ceiling.to_dict(),
            "budget_scope": self.budget_scope,
            "may_request_corrections": self.may_request_corrections,
            "may_stop_work": self.may_stop_work,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class DelegationPolicy:
    """One versioned answer to "who may approve what, up to which limit"."""

    hierarchy: Hierarchy
    grants: tuple[DelegatedAuthority, ...]
    ladder: BudgetLadder
    action_autonomy: Mapping[str, int]
    mode: DelegationMode = DelegationMode.SHADOW
    version: str = POLICY_VERSION
    reporting_cadence: str = "per_objective_and_on_exception"
    source_ref: str = "company/delegation_policy.yaml"
    reserved: frozenset[ActionType] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not isinstance(self.hierarchy, Hierarchy):
            raise DelegationError("policy.hierarchy must be a Hierarchy")
        if not isinstance(self.ladder, BudgetLadder):
            raise DelegationError("policy.ladder must be a BudgetLadder")
        if self.version != POLICY_VERSION:
            raise DelegationError(
                f"policy.version must be {POLICY_VERSION!r}; a policy that names a "
                "version this code does not implement is refused rather than "
                "interpreted"
            )
        if not isinstance(self.mode, DelegationMode):
            raise DelegationError("policy.mode must be a DelegationMode")
        if self.mode is not DelegationMode.SHADOW:
            raise ShadowModeViolation(
                f"policy.mode is {self.mode.value!r}. This phase builds the delegation "
                "model in shadow: it calculates who would be authorized and records "
                "it, and the canonical CEO stop semantics stay in force. Switching "
                "the mode is change_delegation_policy, which is CEO-reserved."
            )
        reserved = reserved_action_types(self.hierarchy.permissions)
        object.__setattr__(self, "reserved", reserved)

        if not isinstance(self.action_autonomy, Mapping) or not self.action_autonomy:
            raise DelegationError("policy.action_autonomy must be a non-empty mapping")
        levels: dict[str, int] = {}
        for key, value in self.action_autonomy.items():
            action = parse_action(key, "action_autonomy key")
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise DelegationError(
                    f"action_autonomy[{action.value}] must be a non-negative integer "
                    "naming a rung of permissions.yaml autonomy_levels"
                )
            levels[action.value] = value
        object.__setattr__(self, "action_autonomy", dict(sorted(levels.items())))

        if not isinstance(self.grants, tuple):
            raise DelegationError("policy.grants must be a tuple")
        seen: set[str] = set()
        for grant in self.grants:
            if not isinstance(grant, DelegatedAuthority):
                raise DelegationError("every grant must be a DelegatedAuthority")
            if grant.seat in seen:
                raise DelegationError(
                    f"seat {grant.seat} carries two grants; one seat has one ceiling"
                )
            seen.add(grant.seat)
            seat = self.hierarchy.seat(grant.seat)
            if seat.kind is SeatKind.CEO:
                raise AuthorityViolation(
                    "the CEO seat receives no delegated grant. It is where escalation "
                    "terminates; a grant here would let this model describe the CEO "
                    "approving something without the CEO."
                )
            granted_reserved = sorted(
                action.value for action in grant.action_types & reserved
            )
            if granted_reserved:
                raise AuthorityViolation(
                    f"the policy grants {grant.seat} reserved action(s): "
                    + ", ".join(granted_reserved)
                    + ". A reserved decision is not delegable; removing it from "
                    "company/permissions.yaml is itself CEO-reserved."
                )
            missing = sorted(
                action.value
                for action in grant.action_types
                if action.value not in levels
            )
            if missing:
                raise DelegationError(
                    f"grant for {grant.seat} names action(s) with no declared autonomy "
                    "level: " + ", ".join(missing)
                )
            if self.ladder.scope(grant.budget_scope) is None:
                raise DelegationError(
                    f"grant for {grant.seat} decides against budget scope "
                    f"{grant.budget_scope!r}, which the ladder does not carry"
                )
        object.__setattr__(self, "_grants", {g.seat: g for g in self.grants})

        # A subordinate may not out-rank the seat it escalates to.
        for grant in self.grants:
            target = self._nearest_granted_superior(grant.seat)
            if target is None:
                continue
            if risk_rank(grant.max_risk) > risk_rank(target.max_risk):
                raise AuthorityViolation(
                    f"{grant.seat} may approve {grant.max_risk.value} risk and its "
                    f"escalation target {target.seat} only {target.max_risk.value}. "
                    "Escalation would be a demotion."
                )
            if grant.per_decision_ceiling > target.per_decision_ceiling:
                raise AuthorityViolation(
                    f"{grant.seat} may approve up to {grant.per_decision_ceiling} and "
                    f"its escalation target {target.seat} only "
                    f"{target.per_decision_ceiling}. A subordinate ceiling above its "
                    "superior is a policy a subordinate could use to overrule one."
                )
        object.__setattr__(
            self, "source_ref", assert_prose(self.source_ref, "policy.source_ref")
        )
        object.__setattr__(
            self,
            "reporting_cadence",
            assert_prose(self.reporting_cadence, "policy.reporting_cadence"),
        )

    # -- lookup ------------------------------------------------------------

    @property
    def _index(self) -> dict[str, DelegatedAuthority]:
        return getattr(self, "_grants")

    def grant(self, seat_id: str) -> DelegatedAuthority | None:
        return self._index.get(seat_id)

    def _nearest_granted_superior(self, seat_id: str) -> DelegatedAuthority | None:
        for candidate in self.hierarchy.superiors(seat_id):
            grant = self._index.get(candidate)
            if grant is not None:
                return grant
        return None

    def required_autonomy(self, action: ActionType) -> int:
        """The autonomy rung this action sits on, or the top of the ladder.

        An action the policy forgot to place is treated as needing the highest
        declared level rather than the lowest, so a missing entry fails closed.
        """
        declared = self.action_autonomy.get(action.value)
        if declared is not None:
            return int(declared)
        return max(self.action_autonomy.values(), default=5)

    def is_reserved(self, action: ActionType) -> bool:
        return action in self.reserved

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "mode": self.mode.value,
            "source_ref": self.source_ref,
            "reporting_cadence": self.reporting_cadence,
            "hierarchy": self.hierarchy.to_dict(),
            "grants": [grant.to_dict() for grant in self.grants],
            "ladder": self.ladder.to_dict(),
            "action_autonomy": dict(self.action_autonomy),
            "reserved": sorted(item.value for item in self.reserved),
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


# -- loading ----------------------------------------------------------------


def _seats_from(data: Mapping[str, Any]) -> tuple[Seat, ...]:
    declared = data.get("seats")
    if not isinstance(declared, Mapping):
        raise DelegationError("the policy file must carry a 'seats' mapping")
    seats: list[Seat] = []
    for seat_id in sorted(declared):
        row = declared[seat_id]
        if not isinstance(row, Mapping):
            raise DelegationError(f"seat {seat_id} must be a mapping")
        kind_name = str(row.get("kind", "")).strip()
        try:
            kind = SeatKind(kind_name)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in SeatKind)
            raise DelegationError(
                f"seat {seat_id}: kind must be one of: {allowed}"
            ) from exc
        seats.append(
            Seat(
                seat_id=str(seat_id),
                kind=kind,
                title=str(row.get("title", seat_id)),
                reports_to=str(row.get("reports_to", "") or ""),
                employee=str(row.get("employee", "") or ""),
                departments=name_tuple(
                    row.get("departments", ()), f"seat {seat_id} departments"
                ),
            )
        )
    return tuple(seats)


def _ladder_from(data: Mapping[str, Any]) -> BudgetLadder:
    declared = data.get("budget")
    if not isinstance(declared, Mapping):
        raise DelegationError("the policy file must carry a 'budget' mapping")
    currency = str(declared.get("currency", "")).strip()
    if not currency:
        raise DelegationError("budget.currency must name a currency, such as USD")
    scopes_raw = declared.get("scopes")
    if not isinstance(scopes_raw, Mapping):
        raise DelegationError("budget.scopes must be a mapping of scope id to ceiling")
    scopes: list[BudgetScope] = []
    for scope_id in sorted(scopes_raw):
        row = scopes_raw[scope_id]
        if not isinstance(row, Mapping):
            raise DelegationError(f"budget scope {scope_id} must be a mapping")
        level_name = str(row.get("level", "")).strip()
        try:
            level = BudgetLevel(level_name)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in BudgetLevel)
            raise DelegationError(
                f"budget scope {scope_id}: level must be one of: {allowed}"
            ) from exc
        scopes.append(
            BudgetScope(
                scope_id=str(scope_id),
                level=level,
                ceiling=money_from_text(
                    row.get("ceiling"), currency, f"budget scope {scope_id} ceiling"
                ),
                parent_id=str(row.get("parent", "") or ""),
                label=str(row.get("label", "") or ""),
            )
        )
    return BudgetLadder(tuple(scopes))


def _grants_from(data: Mapping[str, Any], currency: str) -> tuple[DelegatedAuthority, ...]:
    declared = data.get("grants")
    if not isinstance(declared, Mapping):
        raise DelegationError("the policy file must carry a 'grants' mapping")
    grants: list[DelegatedAuthority] = []
    for seat_id in sorted(declared):
        row = declared[seat_id]
        if not isinstance(row, Mapping):
            raise DelegationError(f"grant {seat_id} must be a mapping")
        actions = row.get("may_approve", ())
        if isinstance(actions, (str, bytes)) or not isinstance(actions, (list, tuple)):
            raise DelegationError(f"grant {seat_id}: may_approve must be a list")
        grants.append(
            DelegatedAuthority(
                seat=str(seat_id),
                action_types=frozenset(
                    parse_action(item, f"grant {seat_id} may_approve") for item in actions
                ),
                max_risk=parse_risk(row.get("max_risk"), f"grant {seat_id} max_risk"),
                per_decision_ceiling=money_from_text(
                    row.get("per_decision_ceiling"),
                    currency,
                    f"grant {seat_id} per_decision_ceiling",
                ),
                budget_scope=str(row.get("budget_scope", "")),
                may_request_corrections=bool(row.get("may_request_corrections", True)),
                may_stop_work=bool(row.get("may_stop_work", True)),
                rationale=str(row.get("rationale", "") or ""),
            )
        )
    return tuple(grants)


def load_delegation_policy(
    *,
    org_registry: Mapping[str, Any],
    permissions: Mapping[str, Any],
    policy_path: str | Path | None = None,
) -> DelegationPolicy:
    """Read the policy file and bind it to one registry and one permissions file.

    The registry and permissions are passed in rather than loaded here, so the
    caller decides which company a policy is being evaluated against — which is
    what lets a test reason about a hypothetical registry without writing one to
    disk, and what stops this module from quietly reading the canonical files
    when it was handed different ones.
    """
    path = (
        Path(policy_path)
        if policy_path is not None
        else Path(__file__).resolve().parents[1] / DEFAULT_POLICY_FILE
    )
    try:
        data = load_yaml_subset(path)
    except YamlSubsetError as exc:
        raise DelegationError(f"cannot load delegation policy: {exc}") from exc

    version = str(data.get("version", ""))
    if version != POLICY_VERSION:
        raise DelegationError(
            f"{path}: version is {version!r}, and this code implements "
            f"{POLICY_VERSION!r}"
        )
    mode_name = str(data.get("mode", "")).strip()
    try:
        mode = DelegationMode(mode_name)
    except ValueError as exc:
        raise DelegationError(
            f"{path}: mode must be one of: "
            + ", ".join(item.value for item in DelegationMode)
        ) from exc

    hierarchy = Hierarchy(
        seats=_seats_from(data),
        org_registry=org_registry,
        permissions=permissions,
    )
    ladder = _ladder_from(data)
    autonomy_raw = data.get("action_autonomy")
    if not isinstance(autonomy_raw, Mapping):
        raise DelegationError(
            "the policy file must carry an 'action_autonomy' mapping of action name "
            "to a rung of permissions.yaml autonomy_levels"
        )
    return DelegationPolicy(
        hierarchy=hierarchy,
        grants=_grants_from(data, ladder.currency),
        ladder=ladder,
        action_autonomy={str(k): v for k, v in autonomy_raw.items()},
        mode=mode,
        version=version,
        reporting_cadence=str(
            data.get("reporting_cadence", "per_objective_and_on_exception")
        ),
        source_ref=str(data.get("source_ref", "company/delegation_policy.yaml")),
    )


__all__ = [
    "DEFAULT_POLICY_FILE",
    "POLICY_VERSION",
    "RISK_ORDER",
    "DelegatedAuthority",
    "DelegationMode",
    "DelegationPolicy",
    "load_delegation_policy",
    "parse_risk",
    "risk_rank",
]
