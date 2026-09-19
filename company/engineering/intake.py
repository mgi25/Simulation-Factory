"""Turning "Build X" into a bounded work order, deterministically, or stopping.

This is the stage the CEO actually touches. Everything it does is plain code:
a token match, a capsule lookup, a set intersection. No model runs here, and
that is the point — the boundary that decides what a request is *allowed* to
touch must be reproducible, and a reproducible boundary cannot be a judgment.

## Where the scope comes from

The CEO does not enumerate files. The capsule layer already does: every
Company OS subsystem has a capsule declaring `owns_paths`, `may_write`,
`must_not_modify` and `tests`. So intake matches the objective against the
capsule index and **reads the scope out of the capsule that owns the subject**.

    "Build X in the engineering loop"
        -> tokens {build, x, engineering, loop}
        -> TaskQuery(paths=..., capsule_ids=...) -> select_capsules
        -> capsule company-engineering-execution
        -> authorized_paths  = its owns_paths and its declared test files,
                               narrowed by any CEO ceiling
        -> forbidden_paths   = its must_not_modify
        -> required_tests    = its tests

This is retrieval, not invention (constitution rule 4). The company already
wrote down who owns what; intake looks it up. A subsystem with no capsule is
not guessed at — it produces DECISION REQUIRED.

## The two screens that run before anything else

**Reserved actions.** `permissions.yaml` reserves ten decisions to the CEO.
`RESERVED_TRIGGERS` maps trigger terms onto those action names, and a hit stops
intake with DECISION REQUIRED naming the reserved action. The action list is
read from `permissions.yaml` rather than restated, so a reserved action added
there and not screened here is *reported* as unscreened instead of silently
passing.

**Credentials.** An objective that mentions a token, a secret, an API key or
OAuth stops as well. Section 6 of the engineering brief makes credential access
an escalation, and the cheapest reliable way to hold that line is to refuse to
build a work order for it.

## Derived acceptance criteria are visible, not silent

If the CEO states acceptance criteria, those are the criteria. If not, intake
derives them from the owning capsule's *declared* invariants and tests and sets
`criteria_derived`. The CEO result prints them under the work order, so what
the company decided "done" means is on the page the CEO approves — which is the
difference between deriving a proposal and inventing authority.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import re
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.resource_classes import ReasoningClass, Risk
from ai_platform.serde import to_jsonable
from company.efficiency.profile import resource_profile
from company.efficiency.strategy import EscalationReason, narrow_context_refs
from company.runtime.path_scope import normalise_path
from knowledge.company_os.capsules import CapsuleIndex, TaskQuery, select_capsules

from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    positive_int,
    ref_tuple,
    text_tuple,
)
from .errors import EngineeringError
from .protected import ProtectedSurface
from .work_order import (
    DEFAULT_MAX_DEVELOPER_ATTEMPTS,
    EngineeringWorkOrder,
)


# Terms in an objective that mean the work needs specialist domain judgment
# rather than a bounded pass over a known contract. A hit sets the work order's
# `specialist_domain`, which is what routes the job to reasoning class D and
# therefore to the strongest model tier.
#
# The table is deliberately small and deliberately about *kinds of work*, not
# about subsystems. "Refactor the authentication flow" is security work
# wherever it lives; "add a field to a dataclass in company/security" is not.
# A list of sensitive directories would have classified the second as the
# first, which is how the previous behaviour - every job is specialist -
# would come back under a new name.
SPECIALIST_TRIGGERS: Mapping[str, tuple[str, ...]] = {
    "security": (
        "authentication",
        "authorisation",
        "authorization",
        "cryptograph",
        "encrypt",
        "sandbox escape",
        "privilege",
        "vulnerabilit",
        "exploit",
    ),
    "governance": (
        "governance policy",
        "governance rules",
        "governance model",
        "permissions policy",
        "protected policy",
        "constitution",
        "approval boundary",
        "separation of duties",
    ),
    "architecture": (
        "rewrite",
        "re-architect",
        "rearchitect",
        "redesign",
        "new subsystem",
        "breaking change",
        "schema change",
        "protocol change",
        # Breaking migration/schema/storage-format/wire-protocol coverage.
        # These name kinds of structural breakage, never a bare "migrate",
        # "migration", "schema", "protocol", or "format" - a job that merely
        # *mentions* one of those nouns ("show migration status on a
        # dashboard", "document the current schema") must stay routine, so
        # every phrase here pairs the noun with what makes it breaking.
        "migrate the",
        "database migration",
        "schema migration",
        "storage-format migration",
        "storage format migration",
        "serialization-format migration",
        "serialization format migration",
        "replace the serialization format",
        "wire protocol",
        "wire-protocol",
        "backward-incompatible",
        "breaks compatibility",
    ),
    "concurrency": (
        "concurren",
        "race condition",
        "deadlock",
        "locking",
        "atomicit",
        "thread saf",
    ),
}

# Terms that mean the work has no precedent to follow. `novel` combined with
# HIGH risk is what the classifier reads as deep reasoning.
NOVEL_TRIGGERS: tuple[str, ...] = (
    "from scratch",
    "greenfield",
    "no precedent",
    "first of its kind",
    "prototype a new",
    "invent",
)

# Trigger terms for the CEO-reserved decisions in company/permissions.yaml.
# The keys must be action names that appear in `permissions.yaml: ceo_reserved`;
# `unscreened_reserved_actions` reports any reserved action this map omits.
RESERVED_TRIGGERS: Mapping[str, tuple[str, ...]] = {
    "publish_public_video": ("publish", "upload", "go live", "release the video"),
    "large_or_recurring_paid_api_spend": (
        "paid api",
        "subscription",
        "buy credits",
        "increase the budget",
    ),
    "delete_important_production_or_company_data": (
        "delete",
        "erase",
        "wipe",
        "purge",
        "drop the database",
    ),
    "merge_major_architecture_rewrite": ("merge", "land on main", "rewrite the architecture"),
    "change_primary_engine": ("replace godot", "switch engine", "change the engine"),
    "hire_or_remove_executive_role": ("hire", "fire", "promote", "archive the role"),
    "drop_entire_content_format": ("drop the format", "cancel the format", "stop making"),
    "change_company_mission": ("change the mission", "new mission"),
    "amend_constitution": ("amend the constitution", "change the constitution"),
    "change_no_subagents_policy": (
        "subagent",
        "sub-agent",
        "subagents",
        "child agent",
        "agent swarm",
        "parallel agents",
    ),
}

CREDENTIAL_TRIGGERS: tuple[str, ...] = (
    "api key",
    "client secret",
    "credential",
    "oauth",
    "password",
    "refresh token",
    "secret",
    "service account",
)

_TOKEN = re.compile(r"[a-z0-9]+")
_MIN_TOKEN_CHARS = 4

# Tokens that match many capsules and therefore select nothing useful.
_STOPWORDS = frozenset(
    {
        "about",
        "add",
        "also",
        "build",
        "change",
        "company",
        "create",
        "from",
        "into",
        "make",
        "more",
        "must",
        "next",
        "over",
        "should",
        "that",
        "the",
        "their",
        "then",
        "this",
        "uses",
        "using",
        "with",
        "work",
        "would",
    }
)


class IntakeOutcome(str, Enum):
    AUTHORIZED = "authorized"
    DECISION_REQUIRED = "decision_required"


@dataclass(frozen=True)
class DecisionRequired:
    """One reason the company stopped instead of inventing authority."""

    reason: str
    question: str
    reserved_action: str = ""
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", assert_prose(self.reason, "decision.reason"))
        object.__setattr__(
            self, "question", assert_prose(self.question, "decision.question")
        )
        if not isinstance(self.reserved_action, str):
            raise EngineeringError("decision.reserved_action must be a string")
        object.__setattr__(
            self, "options", text_tuple(self.options, "decision.options", limit=8)
        )

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class CEORequest:
    """What the CEO asked for, recorded exactly as asked."""

    request_id: str
    objective: str
    requested_by: str
    requested_on: dt.date
    subsystem_hint: str = ""
    capsule_hints: tuple[str, ...] = ()
    scope_ceiling: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    authorized_branch: str = ""
    base_commit: str = ""
    max_developer_attempts: int = 0  # 0 means "whatever the resource profile allows"
    risk: Risk = Risk.MEDIUM
    reversible: bool = True
    # The CEO may name a specialist domain outright. Left empty, intake derives
    # one from the objective, and most objectives derive nothing - which is the
    # routine case and the one that reaches the cheaper model tier.
    specialist_domain: str = ""
    novel: bool = False
    # An explicit request for the strongest tier, recorded as an authorization.
    # This is the escape hatch: a CEO who knows a job is harder than it reads
    # says so here, and the routing does not have to guess.
    escalate_reasoning: bool = False
    resource_profile: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "request_id", assert_record_id(self.request_id, "request_id")
        )
        object.__setattr__(self, "objective", assert_prose(self.objective, "objective"))
        object.__setattr__(
            self, "requested_by", assert_named_person(self.requested_by, "requested_by")
        )
        object.__setattr__(
            self, "requested_on", assert_day(self.requested_on, "requested_on")
        )
        for name in ("subsystem_hint", "authorized_branch", "base_commit", "notes"):
            if not isinstance(getattr(self, name), str):
                raise EngineeringError(f"{name} must be a string")
        object.__setattr__(
            self, "capsule_hints", ref_tuple(self.capsule_hints, "capsule_hints", limit=8)
        )
        object.__setattr__(
            self,
            "scope_ceiling",
            tuple(
                sorted(
                    {
                        normalise_path(item, f"scope_ceiling[{index}]")
                        for index, item in enumerate(self.scope_ceiling or ())
                    }
                )
            ),
        )
        object.__setattr__(
            self,
            "acceptance_criteria",
            text_tuple(self.acceptance_criteria, "acceptance_criteria", limit=24),
        )
        object.__setattr__(
            self, "constraints", text_tuple(self.constraints, "constraints", limit=24)
        )
        try:
            profile = resource_profile(self.resource_profile or None)
        except ValueError as exc:
            raise EngineeringError(str(exc)) from exc
        object.__setattr__(self, "resource_profile", profile.name.value)
        # An unset attempt count takes the profile's. A set one is still
        # checked against the profile, so a request cannot buy itself more
        # automatic attempts than the profile authorizes by naming a number.
        attempts = self.max_developer_attempts or profile.developer_attempts
        object.__setattr__(
            self,
            "max_developer_attempts",
            positive_int(attempts, "max_developer_attempts", maximum=8),
        )
        if self.max_developer_attempts > profile.developer_attempts:
            raise EngineeringError(
                f"max_developer_attempts {self.max_developer_attempts} exceeds the "
                f"{profile.developer_attempts} the {profile.name.value} resource "
                "profile authorizes"
            )
        if not isinstance(self.risk, Risk):
            raise EngineeringError("risk must be a Risk value")
        if not isinstance(self.reversible, bool):
            raise EngineeringError("reversible must be a boolean")
        if not isinstance(self.specialist_domain, str):
            raise EngineeringError("specialist_domain must be a string")
        object.__setattr__(self, "specialist_domain", self.specialist_domain.strip())
        for name in ("novel", "escalate_reasoning"):
            if not isinstance(getattr(self, name), bool):
                raise EngineeringError(f"{name} must be a boolean")

    def tokens(self) -> tuple[str, ...]:
        """The objective and hints as deterministic, de-noised match tokens."""
        text = " ".join((self.objective, self.subsystem_hint)).lower()
        found = {
            token
            for token in _TOKEN.findall(text.replace("/", " ").replace("_", " ").replace("-", " "))
            if len(token) >= _MIN_TOKEN_CHARS and token not in _STOPWORDS
        }
        return tuple(sorted(found))

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "CEORequest":
        if not isinstance(data, Mapping):
            raise EngineeringError("a CEO request must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError(
                "CEO request has unknown field(s): " + ", ".join(unknown)
            )
        risk = data.get("risk", Risk.MEDIUM.value)
        if not isinstance(risk, (str, Risk)):
            raise EngineeringError("risk must be a string")
        try:
            parsed_risk = risk if isinstance(risk, Risk) else Risk(risk)
        except ValueError as exc:
            allowed = ", ".join(item.value for item in Risk)
            raise EngineeringError(f"risk must be one of: {allowed}") from exc
        return cls(
            request_id=str(data.get("request_id", "")),
            objective=str(data.get("objective", "")),
            requested_by=str(data.get("requested_by", "")),
            requested_on=assert_day(data.get("requested_on"), "requested_on"),
            subsystem_hint=str(data.get("subsystem_hint", "")),
            capsule_hints=_strings(data.get("capsule_hints"), "capsule_hints"),
            scope_ceiling=_strings(data.get("scope_ceiling"), "scope_ceiling"),
            acceptance_criteria=_strings(
                data.get("acceptance_criteria"), "acceptance_criteria"
            ),
            constraints=_strings(data.get("constraints"), "constraints"),
            authorized_branch=str(data.get("authorized_branch", "")),
            base_commit=str(data.get("base_commit", "")),
            max_developer_attempts=int(data.get("max_developer_attempts", 0)),
            risk=parsed_risk,
            reversible=bool(data.get("reversible", True)),
            specialist_domain=str(data.get("specialist_domain", "")),
            novel=bool(data.get("novel", False)),
            escalate_reasoning=bool(data.get("escalate_reasoning", False)),
            resource_profile=str(data.get("resource_profile", "")),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class ScopeDerivation:
    """How the scope was reached, so the CEO can check the reasoning by hand."""

    matched_tokens: tuple[str, ...] = ()
    selected_capsule_ids: tuple[str, ...] = ()
    selection_reasons: tuple[str, ...] = ()
    owns_paths: tuple[str, ...] = ()
    ceiling_applied: tuple[str, ...] = ()
    authorized_paths: tuple[str, ...] = ()
    forbidden_paths: tuple[str, ...] = ()
    required_tests: tuple[str, ...] = ()
    criteria_derived: bool = False
    unscreened_reserved_actions: tuple[str, ...] = ()
    specialist_domain: str = ""
    specialist_reason: str = ""
    novel: bool = False
    escalation: str = "none"
    reasoning_class_ceiling: str = ""
    resource_profile: str = ""
    context_refs_considered: int = 0
    context_refs_kept: int = 0
    context_refs_dropped: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)


@dataclass(frozen=True)
class IntakeAssessment:
    """The result of intake: a work order, or the decisions that block one."""

    request: CEORequest
    outcome: IntakeOutcome
    derivation: ScopeDerivation
    work_order: EngineeringWorkOrder | None = None
    decisions: tuple[DecisionRequired, ...] = ()

    def __post_init__(self) -> None:
        if self.outcome is IntakeOutcome.AUTHORIZED:
            if self.work_order is None:
                raise EngineeringError("an authorized intake must carry a work order")
            if self.decisions:
                raise EngineeringError(
                    "an authorized intake cannot also require a CEO decision"
                )
        elif self.work_order is not None or not self.decisions:
            raise EngineeringError(
                "a decision-required intake carries decisions and no work order"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request": self.request.to_dict(),
            "outcome": self.outcome.value,
            "derivation": self.derivation.to_dict(),
            "work_order": self.work_order.to_dict() if self.work_order else None,
            "work_order_fingerprint": (
                self.work_order.fingerprint() if self.work_order else ""
            ),
            "decisions": [item.to_dict() for item in self.decisions],
        }


def reserved_actions(permissions: Mapping[str, Any]) -> tuple[str, ...]:
    """The CEO-reserved action names, read from `permissions.yaml`."""
    values = permissions.get("ceo_reserved", ())
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise EngineeringError("permissions.ceo_reserved must be a list of action names")
    return tuple(sorted(str(item) for item in values))


def screen_reserved(objective: str, permissions: Mapping[str, Any]) -> tuple[DecisionRequired, ...]:
    """Every CEO-reserved action the objective's wording reaches."""
    text = objective.lower()
    declared = set(reserved_actions(permissions))
    hits: list[DecisionRequired] = []
    for action in sorted(declared):
        triggers = RESERVED_TRIGGERS.get(action, ())
        matched = tuple(term for term in triggers if term in text)
        if not matched:
            continue
        hits.append(
            DecisionRequired(
                reason=(
                    f"the objective's wording reaches the CEO-reserved action "
                    f"{action!r} ({', '.join(matched)})"
                ),
                question=(
                    f"{action} is reserved to the CEO by company/permissions.yaml. "
                    "Restate the objective without it, or take the decision directly."
                ),
                reserved_action=action,
            )
        )
    return tuple(hits)


def screen_credentials(objective: str) -> tuple[DecisionRequired, ...]:
    text = objective.lower()
    matched = tuple(term for term in CREDENTIAL_TRIGGERS if term in text)
    if not matched:
        return ()
    return (
        DecisionRequired(
            reason="the objective names credential material: " + ", ".join(matched),
            question=(
                "Credential access is an escalation, not a work-order scope. Authorize "
                "it explicitly and separately, or restate the objective without it."
            ),
        ),
    )


def assess_request(
    request: CEORequest,
    permissions: Mapping[str, Any],
    *,
    repo_root: Path | str,
    capsule_index: CapsuleIndex | None = None,
    work_order_id: str = "",
    authorized_on: dt.date | None = None,
) -> IntakeAssessment:
    """Derive one bounded work order from one CEO request, or say why not.

    Deterministic and offline: the only I/O is loading the capsule seeds and
    digesting the protected surface.
    """
    index = capsule_index if capsule_index is not None else CapsuleIndex.load()
    unscreened = tuple(
        action for action in reserved_actions(permissions) if action not in RESERVED_TRIGGERS
    )
    blocking = screen_reserved(request.objective, permissions) + screen_credentials(
        request.objective
    )
    tokens = request.tokens()

    selection = select_capsules(
        index,
        TaskQuery(
            paths=_path_signals(request, tokens),
            capabilities=tokens,
            capsule_ids=request.capsule_hints,
            include_dependencies=False,
            max_capsules=3,
        ),
    )
    missing_hints = tuple(item for item in request.capsule_hints if item not in index)
    if missing_hints:
        blocking += (
            DecisionRequired(
                reason="the request names capsule(s) that do not exist: "
                + ", ".join(missing_hints),
                question="Name an existing capsule, or drop the hint and let intake match.",
                options=index.ids()[:8],
            ),
        )

    capsules = selection.capsules
    tests = tuple(sorted({path for capsule in capsules for path in capsule.tests}))
    # The capsule's own test files join the writable set. A work order whose
    # acceptance criteria require a declared test to pass, and whose scope
    # forbids writing that test, is incoherent: the criterion is unreachable as
    # soon as the change needs a new case. Only the *declared* files are added,
    # never the `tests/` tree, so the grant stays as narrow as the capsule is.
    owns = tuple(
        sorted(
            {
                normalise_path(_strip_glob(path), "capsule.owns_paths")
                for capsule in capsules
                for path in capsule.owns_paths
            }
            | {normalise_path(path, "capsule.tests") for path in tests}
        )
    )
    authorized = _narrow(owns, request.scope_ceiling)
    forbidden = tuple(
        sorted(
            {
                normalise_path(_strip_glob(path), "capsule.must_not_modify")
                for capsule in capsules
                for path in capsule.must_not_modify
            }
            - set(authorized)
        )
    )
    if not capsules:
        blocking += (
            DecisionRequired(
                reason=(
                    "no capsule owns the subject of this objective, so the company "
                    "cannot derive a bounded scope for it"
                ),
                question=(
                    "Name the subsystem this belongs to (subsystem_hint), or the capsule "
                    "that owns it (capsule_hints)."
                ),
                options=index.ids()[:8],
            ),
        )
    elif not authorized:
        blocking += (
            DecisionRequired(
                reason=(
                    "the matched capsule(s) "
                    + ", ".join(selection.ids())
                    + " declare no writable path inside the requested ceiling"
                ),
                question=(
                    "Widen scope_ceiling, or authorize a different subsystem. A work "
                    "order with no writable path authorizes no engineering."
                ),
                options=owns[:8] or ("the matched capsules own no path at all",),
            ),
        )

    criteria = request.acceptance_criteria
    derived = not criteria
    if derived and capsules:
        criteria = _derive_criteria(request, capsules, tests)

    # Computed once and read twice. Both are pure functions of what is already
    # in hand, so a second call would agree - but a derivation that says one
    # thing and a work order that carries another is the exact failure this
    # milestone found in the briefing, and the way to not have it is to not
    # have two answers.
    routing = derive_routing(request)
    narrowing = _narrow_refs(selection, tests, authorized)
    derivation = ScopeDerivation(
        matched_tokens=tokens,
        selected_capsule_ids=selection.ids(),
        selection_reasons=tuple(
            f"{match.capsule.id}: {match.reason_text()}" for match in selection.matches
        ),
        owns_paths=owns,
        ceiling_applied=request.scope_ceiling,
        authorized_paths=authorized,
        forbidden_paths=forbidden,
        required_tests=tests,
        criteria_derived=derived,
        unscreened_reserved_actions=unscreened,
        specialist_domain=routing.specialist_domain,
        specialist_reason=routing.reason,
        novel=routing.novel,
        escalation=routing.escalation.value,
        reasoning_class_ceiling=routing.reasoning_class_ceiling.value,
        resource_profile=request.resource_profile,
        context_refs_considered=narrowing.considered,
        context_refs_kept=len(narrowing.kept),
        context_refs_dropped=narrowing.dropped_reasons,
    )

    if blocking:
        return IntakeAssessment(
            request=request,
            outcome=IntakeOutcome.DECISION_REQUIRED,
            derivation=derivation,
            decisions=tuple(dict.fromkeys(blocking)),
        )

    surface = ProtectedSurface.capture(repo_root, authorized_paths=authorized)
    order = EngineeringWorkOrder(
        work_order_id=work_order_id or f"wo-{request.request_id}",
        objective=request.objective,
        requested_by=request.requested_by,
        request_id=request.request_id,
        authorized_branch=request.authorized_branch or f"eng-{request.request_id}",
        authorized_paths=authorized,
        acceptance_criteria=criteria,
        authorized_on=authorized_on or request.requested_on,
        forbidden_paths=forbidden,
        constraints=request.constraints,
        context_refs=narrowing.kept,
        required_tests=tests,
        protected=surface,
        base_commit=request.base_commit,
        max_developer_attempts=request.max_developer_attempts,
        reasoning_class_ceiling=routing.reasoning_class_ceiling,
        risk=request.risk,
        reversible=request.reversible,
        specialist_domain=routing.specialist_domain,
        novel=routing.novel,
        escalation=routing.escalation.value,
        resource_profile=request.resource_profile,
    )
    return IntakeAssessment(
        request=request,
        outcome=IntakeOutcome.AUTHORIZED,
        derivation=derivation,
        work_order=order,
    )


def _path_signals(request: CEORequest, tokens: Sequence[str]) -> tuple[str, ...]:
    """Path-shaped signals for capsule selection: the hint, and token directories.

    `scope_ceiling` is deliberately **not** a signal. A ceiling exists to
    narrow, and feeding it to the selector made it widen: a request ceilinged
    to `company/runtime` selected the runtime capsule, whose owned paths then
    survived the narrowing, and the CEO's upper bound had chosen the subject.
    A ceiling now only ever removes paths (`_narrow`); pointing at a subsystem
    is what `subsystem_hint` and `capsule_hints` are for.
    """
    signals = set()
    if request.subsystem_hint.strip():
        signals.add(normalise_path(request.subsystem_hint, "subsystem_hint"))
    signals.update(f"company/{token}" for token in tokens)
    return tuple(sorted(signals))


def _narrow(paths: Sequence[str], ceiling: Sequence[str]) -> tuple[str, ...]:
    """Keep only what the CEO's ceiling allows; an absent ceiling narrows nothing.

    Both containment directions are kept, and both are narrowings: a ceiling
    that contains an owned path keeps the owned path, and a ceiling *inside* an
    owned path keeps the ceiling, which is the smaller of the two. Nothing
    outside the owned set is ever produced, so this cannot widen.
    """
    if not ceiling:
        return tuple(sorted(set(paths)))
    kept = {
        path
        for path in paths
        for rule in ceiling
        if path == rule or path.startswith(rule + "/")
    }
    kept.update(
        rule for rule in ceiling for path in paths if rule.startswith(path + "/")
    )
    return tuple(sorted(kept))


def _strip_glob(value: str) -> str:
    text = value.strip().replace("\\", "/")
    while text.endswith(("/**", "/*")):
        text = text.rsplit("/", 1)[0]
    return text or value


def _derive_criteria(
    request: CEORequest, capsules: Sequence[Any], tests: Sequence[str]
) -> tuple[str, ...]:
    """Criteria assembled from statements the company already made, not invented.

    One completion criterion naming the objective, one per declared invariant of
    the owning capsules, and one requiring the declared tests to pass. Every
    line after the first is a quotation of an existing capsule field, which is
    why this is retrieval and the CEO result labels it as derived.
    """
    criteria = [f"The stated objective is implemented: {request.objective}"]
    for capsule in capsules[:1]:
        for invariant in capsule.invariants[:6]:
            criteria.append(f"{capsule.id} invariant still holds: {invariant}")
    if tests:
        criteria.append("Every declared test passes: " + ", ".join(tests))
    return tuple(criteria[:24])


@dataclass(frozen=True)
class RoutingDerivation:
    """What the request routes to, and the sentence that says why.

    Derived, recorded, and visible on the CEO page - the same discipline the
    acceptance criteria follow. A routing decision nobody can read is a
    routing decision nobody can correct.
    """

    specialist_domain: str
    novel: bool
    escalation: EscalationReason
    reasoning_class_ceiling: ReasoningClass
    reason: str


def derive_routing(request: CEORequest) -> RoutingDerivation:
    """Decide the classifier signals for one request, deterministically.

    The rule, in order:

    1. A specialist domain the CEO named is the specialist domain.
    2. Otherwise the objective is matched against `SPECIALIST_TRIGGERS`, which
       names kinds of work - security, governance, architecture, concurrency -
       that need domain judgment whatever subsystem they touch.
    3. HIGH or CRITICAL risk needs specialist depth on its own; the classifier
       already routes it to D or E and this only records the reason.
    4. Everything else has no specialist domain, classifies C, and runs at the
       profile's routine tier.

    Nothing here consults a model, a clock or the filesystem: the same request
    routes the same way in this session and the next, which is what makes the
    decision auditable after the fact.
    """
    # `notes` is explanatory metadata the CEO attaches for humans, not part of
    # the requested work, so it must never silently raise the model tier: a
    # note that says "the previous request was misclassified as governance"
    # would otherwise retrigger the exact misclassification it describes.
    text = request.objective.lower()
    novel = request.novel or any(term in text for term in NOVEL_TRIGGERS)

    domain = request.specialist_domain
    reason = ""
    if domain:
        reason = f"the request named the specialist domain {domain!r}"
    else:
        for name, terms in SPECIALIST_TRIGGERS.items():
            hit = next((term for term in terms if term in text), "")
            if hit:
                domain = name
                reason = f"the objective names {hit!r}, which is {name} work"
                break
    if not domain and request.risk in (Risk.HIGH, Risk.CRITICAL):
        domain = "high_risk_change"
        reason = f"risk {request.risk.value} needs specialist depth whatever the subject"
    if not domain:
        reason = (
            "the objective names no security, governance, architecture or "
            "concurrency work and the risk is not high, so this is routine "
            "implementation"
        )

    escalation = (
        EscalationReason.EXPLICIT if request.escalate_reasoning else EscalationReason.NONE
    )
    if request.escalate_reasoning and not domain:
        domain = "explicit_escalation"
        reason = "the request explicitly escalated this job to the strongest tier"

    # The ceiling is the highest class the work order authorizes, not the class
    # it will be. It has to sit above whatever the classifier will produce, or
    # `plan_task` refuses the job rather than downgrading it - which is the
    # right refusal and the wrong moment to discover it.
    ceiling = ReasoningClass.D
    if request.risk is Risk.CRITICAL or (request.risk is Risk.HIGH and novel):
        ceiling = ReasoningClass.E
    elif not request.reversible:
        # `requires_judgment` is True for every engineering task, so an
        # irreversible one classifies E by the deep_reasoning rule.
        ceiling = ReasoningClass.E

    return RoutingDerivation(
        specialist_domain=domain,
        novel=novel,
        escalation=escalation,
        reasoning_class_ceiling=ceiling,
        reason=reason,
    )


def _capsule_paths(selection: Any) -> dict[str, tuple[str, ...]]:
    """Every selected capsule's owned paths, for reference narrowing.

    Read from the capsules already in hand. Nothing is loaded, so narrowing
    costs no I/O and cannot disagree with the selection it narrows.
    """
    owned: dict[str, tuple[str, ...]] = {}
    for match in getattr(selection, "matches", ()):  # pragma: no branch
        capsule = match.capsule
        owned[capsule.id] = tuple(
            _strip_glob(path) for path in capsule.owns_paths
        ) + tuple(_strip_glob(path) for path in capsule.tests)
    return owned


def _all_refs(selection: Any, tests: Sequence[str]) -> tuple[ContextRef, ...]:
    """The capsules as module contracts, and the declared tests as test refs."""
    refs = list(selection.refs())
    seen = {ref.key for ref in refs}
    for path in tests:
        ref = ContextRef(
            kind=ContextKind.TEST,
            ref=path,
            reason="declared test of the owning capsule",
        )
        if ref.key not in seen:
            refs.append(ref)
            seen.add(ref.key)
    return tuple(refs[:12])


def _narrow_refs(
    selection: Any, tests: Sequence[str], authorized: Sequence[str]
):
    """Narrow the candidate references to the ones the scope actually bears on.

    This is where the narrowing *happens*, rather than where it is reported.
    The previous implementation computed a scoped list in the briefing and
    sent the packet the unnarrowed one, so the record claimed a reduction the
    session never received. Narrowing here means the work order, the packet,
    the briefing and the receipt all carry the same references, because there
    is only one set.
    """
    return narrow_context_refs(
        _all_refs(selection, tests),
        tuple(authorized),
        capsule_paths=_capsule_paths(selection),
        floor=1,
    )


def _context_refs(
    selection: Any, tests: Sequence[str], authorized: Sequence[str]
) -> tuple[ContextRef, ...]:
    """The narrowed reference set alone, for a caller that wants only that."""
    return _narrow_refs(selection, tests, authorized).kept


def _strings(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EngineeringError(f"{field_name} must be a list")
    return tuple(str(item) for item in value)


__all__ = [
    "CREDENTIAL_TRIGGERS",
    "NOVEL_TRIGGERS",
    "RESERVED_TRIGGERS",
    "SPECIALIST_TRIGGERS",
    "RoutingDerivation",
    "derive_routing",
    "CEORequest",
    "DecisionRequired",
    "IntakeAssessment",
    "IntakeOutcome",
    "ScopeDerivation",
    "assess_request",
    "reserved_actions",
    "screen_credentials",
    "screen_reserved",
]
