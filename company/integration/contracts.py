"""What the canonical contracts have to still say, read rather than restated.

Three conditions in the gate are about declarations rather than behaviour: the
CEO-reserved actions, the no-subagent chain, and the statement that Company OS
is not wired to production yet. All three are already written down somewhere
canonical, so this module reads those files and reports drift. It defines no
authority of its own.

## Why the gate names a required subset and not the whole list

`permissions.yaml` reserves ten decisions. The gate depends on eight of them,
one per hazard it is supposed to be closing - publishing, recurring spend,
deletion, an architecture merge, an executive hire, the mission, the
constitution and the subagent rule. Those eight are required to be present.
The other two are strategy, and the gate has no opinion about them.

A reserved list that has *grown* is not drift: reserving more decisions cannot
make the boundary less safe, so an unrecognised entry is reported and not
failed. A reserved list that has *shrunk* past one of the eight is exactly the
change that would let a future phase publish a video without asking, and it
fails.

## Why the no-subagent chain is checked in seven places and not one

Constitution rule 2 is the one rule whose amendment is itself CEO-reserved, and
it is represented in the constitution, in `permissions.yaml` twice, in
`org_registry.yaml` twice, in the employee contract schema, in the platform
policy and in a knowledge record. Any single one of those could be edited
without the others noticing. The chain check asks all of them, and reports
each link that has gone missing by name, because "the no-subagent rule is
still enforced somewhere" is not the claim the constitution makes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


# The reserved decisions this gate depends on, and the hazard each one closes.
REQUIRED_RESERVED_ACTIONS: dict[str, str] = {
    "publish_public_video": "publishing is the production-boundary hazard",
    "large_or_recurring_paid_api_spend": "recurring paid API spend stays CEO-reserved",
    "delete_important_production_or_company_data": "no autonomous delete authority",
    "merge_major_architecture_rewrite": "wiring Company OS in is an architecture merge",
    "hire_or_remove_executive_role": "no autonomous reorganization",
    "change_company_mission": "the mission is not a configuration value",
    "amend_constitution": "the constitutional rules are not editable by a session",
    "change_no_subagents_policy": "constitution rule 2 is amended by the CEO",
}

# Review triggers the gate cites as evidence for its own conditions.
REQUIRED_REVIEW_TRIGGERS: tuple[str, ...] = (
    "new_dependency",
    "production_publish_request",
)


@dataclass(frozen=True)
class ChainLink:
    """One place the no-subagent rule is represented, and whether it still is."""

    name: str
    reference: str
    present: bool
    detail: str


@dataclass(frozen=True)
class ContractDrift:
    """What a contract check found, in the two directions that matter."""

    missing: tuple[str, ...] = ()
    unrecognised: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing


def reserved_action_drift(permissions: Mapping[str, Any]) -> ContractDrift:
    """Compare `permissions.yaml`'s reserved list with the eight the gate needs."""
    declared = permissions.get("ceo_reserved", ())
    if isinstance(declared, (str, bytes)) or not isinstance(declared, (list, tuple)):
        return ContractDrift(
            missing=("permissions.yaml ceo_reserved is not a list of action names",),
            evidence=("company/permissions.yaml",),
        )
    present = {str(item) for item in declared}
    missing = tuple(
        f"{action} is no longer CEO-reserved ({why})"
        for action, why in sorted(REQUIRED_RESERVED_ACTIONS.items())
        if action not in present
    )
    unrecognised = tuple(sorted(present - set(REQUIRED_RESERVED_ACTIONS)))
    return ContractDrift(
        missing=missing, unrecognised=unrecognised, evidence=("company/permissions.yaml",)
    )


def review_trigger_drift(permissions: Mapping[str, Any]) -> ContractDrift:
    """The mandatory review triggers the gate's own conditions rest on."""
    declared = permissions.get("mandatory_review_triggers", {})
    if not isinstance(declared, Mapping):
        return ContractDrift(
            missing=("permissions.yaml mandatory_review_triggers is not a mapping",),
            evidence=("company/permissions.yaml",),
        )
    missing = tuple(
        f"{trigger} is no longer a mandatory review trigger"
        for trigger in REQUIRED_REVIEW_TRIGGERS
        if trigger not in declared
    )
    return ContractDrift(missing=missing, evidence=("company/permissions.yaml",))


def no_subagent_chain(repo_root: Path | str, config: Any) -> tuple[ChainLink, ...]:
    """Every representation of constitution rule 2, and whether it is still there."""
    root = Path(repo_root)
    permissions = _mapping(getattr(config, "permissions", None))
    registry = _mapping(getattr(config, "org_registry", None))
    schema = _mapping(getattr(config, "agent_contract_schema", None))

    defaults = _mapping(permissions.get("bootstrap_defaults"))
    constraints = _mapping(registry.get("global_constraints"))
    required_fields = schema.get("required_fields", ())
    required_names = (
        {str(item) for item in required_fields}
        if isinstance(required_fields, (list, tuple))
        else set()
    )
    schema_template = _mapping(schema.get("template"))

    links = [
        _link(
            "constitution rule 2",
            "company/constitution.md",
            _constitution_states_the_rule(root),
            "the constitution no longer states the no-subagent rule",
        ),
        _link(
            "permissions bootstrap default",
            "company/permissions.yaml",
            defaults.get("no_subagents") is True,
            f"bootstrap_defaults.no_subagents is {defaults.get('no_subagents')!r}, not True",
        ),
        _link(
            "permissions reserved amendment",
            "company/permissions.yaml",
            "change_no_subagents_policy" in set(map(str, permissions.get("ceo_reserved", ()) or ())),
            "change_no_subagents_policy is no longer CEO-reserved",
        ),
        _link(
            "org registry constraint",
            "company/org_registry.yaml",
            constraints.get("no_subagents") is True,
            f"global_constraints.no_subagents is {constraints.get('no_subagents')!r}, not True",
        ),
        _link(
            "org registry spawning constraint",
            "company/org_registry.yaml",
            constraints.get("nested_agent_spawning") is False,
            f"global_constraints.nested_agent_spawning is "
            f"{constraints.get('nested_agent_spawning')!r}, not False",
        ),
        _link(
            "employee contract requirement",
            "company/agent_contract.schema.yaml",
            "no_subagents" in required_names,
            "the employee contract schema no longer requires no_subagents",
        ),
        _link(
            "employee contract template",
            "company/agent_contract.schema.yaml",
            schema_template.get("no_subagents") is True,
            f"the contract template sets no_subagents to "
            f"{schema_template.get('no_subagents')!r}, not True",
        ),
        _link(
            "knowledge record",
            "knowledge/company_os/records/fact/bootstrap-forbids-nested-agents.json",
            (
                root
                / "knowledge/company_os/records/fact/bootstrap-forbids-nested-agents.json"
            ).is_file(),
            "the bootstrap-forbids-nested-agents fact is no longer in the knowledge store",
        ),
    ]
    return tuple(links)


def _link(name: str, reference: str, present: bool, failure: str) -> ChainLink:
    return ChainLink(
        name=name,
        reference=reference,
        present=bool(present),
        detail="present" if present else failure,
    )


def _constitution_states_the_rule(repo_root: Path) -> bool:
    """Does the constitution still contain a no-subagent rule?

    Matched on the two words that cannot be removed without changing the rule,
    rather than on the sentence, so that rewording it does not read as deleting
    it and deleting it cannot read as rewording.
    """
    path = repo_root / "company/constitution.md"
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8").casefold()
    return "no subagents" in text or "no-subagent" in text


def integration_still_gated(capsule_invariants: tuple[str, ...]) -> tuple[bool, str]:
    """Does the control-plane capsule still say Company OS is unconnected?

    The claim lives in the capsule because that is what a future session is
    given as context. If it is deleted, the next session reads a control plane
    with no statement that it is unwired, which is the moment the gate exists
    to catch.
    """
    for invariant in capsule_invariants:
        text = invariant.casefold()
        if "integration gate" in text and "production" in text:
            return True, invariant
    return (
        False,
        "the control-plane capsule no longer states that Company OS stays unconnected "
        "to production execution until the integration gate passes",
    )


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "REQUIRED_RESERVED_ACTIONS",
    "REQUIRED_REVIEW_TRIGGERS",
    "ChainLink",
    "ContractDrift",
    "integration_still_gated",
    "no_subagent_chain",
    "reserved_action_drift",
    "review_trigger_drift",
]
