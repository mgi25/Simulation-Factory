"""Execution policy, and the two-key lock on nested agents.

Constitution rule 2 and `permissions.yaml: ceo_reserved.change_no_subagents_policy`
say the same thing from two directions: in Bootstrap Mode nothing spawns a child
agent, and the rule itself is the CEO's to change. A prose rule is followed
until it is forgotten. This module makes it a construction error.

## The lock

`ExecutionPolicy` defaults to the bootstrap position - `no_subagents=True`,
`nested_agent_spawning=False`, one session at a time - and in bootstrap mode
those are not defaults, they are the only permitted values. There is no flag,
no environment variable and no config key that relaxes them while `mode` stays
`"bootstrap"`. Leaving bootstrap mode is the first key; naming the CEO approval
in `ceo_amendment` is the second. Neither key alone opens anything, and both
of them are recorded in the policy object that the run is executed under, so
the amendment appears in the artefact rather than in someone's memory.

## Why `from_mapping` is strict

The realistic way a nested agent gets silently enabled is not a call to a
constructor - it is a YAML file that grows a key nobody validates. So loading a
policy from a mapping rejects unknown keys outright. A config that says
`allow_subagents: true` fails to load; it does not load and quietly do nothing.

## Multi-perspective work

Class F exists because rare major decisions deserve independent reviewers, and
that is exactly the shape of task someone would reach for parallel agents to
serve. `assert_sequential` is the reminder in executable form: reviewers are
separate sessions invoked one after another, passing the compact handoff of
`company/task_handoff.schema.yaml` between them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

BOOTSTRAP_MODE = "bootstrap"


class SubagentPolicyViolation(RuntimeError):
    """An attempt to enable, record or execute nested agent spawning."""


class PolicyConfigError(ValueError):
    """A policy mapping that cannot be trusted - unknown or mistyped keys."""


@dataclass(frozen=True)
class ExecutionPolicy:
    """How a session is allowed to spend resources, and what it may not spawn."""

    mode: str = BOOTSTRAP_MODE

    # The locked block. In bootstrap mode these values are fixed.
    no_subagents: bool = True
    nested_agent_spawning: bool = False
    always_on_agents: bool = False
    max_concurrent_sessions: int = 1

    # The efficiency block, mirroring `agent_contract.schema.yaml: token_policy`.
    deterministic_first: bool = True
    retrieval_before_reasoning: bool = True
    minimum_relevant_context: bool = True
    prefer_single_pass: bool = True
    multi_perspective_is_sequential: bool = True

    # The second key. Empty in bootstrap mode, always.
    ceo_amendment: str = ""

    def __post_init__(self) -> None:
        if self.max_concurrent_sessions < 1:
            raise PolicyConfigError("max_concurrent_sessions must be at least 1")
        if self.mode == BOOTSTRAP_MODE:
            self._assert_bootstrap_lock()
        elif self.nested_agent_spawning or not self.no_subagents:
            if not self.ceo_amendment.strip():
                raise SubagentPolicyViolation(
                    "enabling nested agents outside bootstrap mode still requires "
                    "ceo_amendment naming the approval "
                    "(permissions.yaml: ceo_reserved.change_no_subagents_policy)"
                )

    def _assert_bootstrap_lock(self) -> None:
        locked = (
            ("no_subagents", self.no_subagents, True),
            ("nested_agent_spawning", self.nested_agent_spawning, False),
            ("always_on_agents", self.always_on_agents, False),
            ("max_concurrent_sessions", self.max_concurrent_sessions, 1),
            ("ceo_amendment", self.ceo_amendment, ""),
        )
        for name, actual, required in locked:
            if actual != required:
                raise SubagentPolicyViolation(
                    f"bootstrap mode fixes {name}={required!r}, got {actual!r}. "
                    "Constitution rule 2 is amended by the CEO, not by a config value."
                )

    @property
    def allows_nested_agents(self) -> bool:
        """True only when both keys are turned: out of bootstrap, and amended."""
        return (
            self.mode != BOOTSTRAP_MODE
            and self.nested_agent_spawning
            and not self.no_subagents
            and bool(self.ceo_amendment.strip())
        )

    def assert_no_subagents(self, observed: int = 0) -> None:
        """Raise if any nested agent was used under a policy that forbids them."""
        if observed and not self.allows_nested_agents:
            raise SubagentPolicyViolation(
                f"{observed} nested agent(s) used under policy mode {self.mode!r}, "
                "which forbids them"
            )

    def assert_sequential(self, reviewers: int) -> None:
        """Raise if more than one reviewer would run at once."""
        if reviewers > 1 and self.multi_perspective_is_sequential:
            if self.max_concurrent_sessions > 1:
                raise SubagentPolicyViolation(
                    f"{reviewers} reviewers must be invoked sequentially, but "
                    f"max_concurrent_sessions={self.max_concurrent_sessions}"
                )

    def amended(self, mode: str, ceo_amendment: str, **changes: Any) -> ExecutionPolicy:
        """The only supported way out of the locked block, and it is explicit."""
        return replace(self, mode=mode, ceo_amendment=ceo_amendment, **changes)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> ExecutionPolicy:
        """Load a policy from config, rejecting anything not in the schema.

        Unknown keys are the silent-enable vector, so they are fatal rather
        than ignored.
        """
        known = {field for field in cls.__dataclass_fields__}
        unknown = sorted(set(data) - known)
        if unknown:
            raise PolicyConfigError(
                f"unknown execution policy key(s): {', '.join(unknown)}. "
                "A policy key that is not in the schema is not honoured; it is refused."
            )
        typed: dict[str, Any] = {}
        for key, value in data.items():
            expected = cls.__dataclass_fields__[key].type
            if expected == "bool" and not isinstance(value, bool):
                raise PolicyConfigError(f"{key}: expected a boolean, got {value!r}")
            if expected == "int" and not isinstance(value, int):
                raise PolicyConfigError(f"{key}: expected an integer, got {value!r}")
            if expected == "str" and not isinstance(value, str):
                raise PolicyConfigError(f"{key}: expected a string, got {value!r}")
            typed[key] = value
        return cls(**typed)


BOOTSTRAP_POLICY = ExecutionPolicy()
"""The policy every Company OS session runs under until the CEO says otherwise."""
