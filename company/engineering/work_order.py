"""The authorized engineering request, and the ceiling nothing below it may raise.

An `EngineeringWorkOrder` is the one authority record in this package. Every
later stage derives from it and none of them may exceed it: the plan is a
proposal against it, the session packet is built from it, the review is
adjudicated against it, and the CEO result reports it back unchanged.

## Why there is no `status` field

A work order is identified by `fingerprint()`, and that fingerprint is the
entire proof that the work order the reviewer read is the work order the CEO
authorized. A mutable field inside it would destroy that proof — the record
would hash differently at every stage and the check would have to be abandoned
or weakened to ignore the field.

So the lifecycle state lives in `EngineeringJob` (`lifecycle.py`), which points
at the work order by id and fingerprint. The work order holds only what was
true at authorization and stays true: objective, requester, scope, criteria,
ceilings, protected surface, day.

## The three things it authorizes, and the one it cannot

It authorizes **paths** (`authorized_paths`, and `forbidden_paths` on top),
**a branch** (`authorized_branch`, never `main`) and **an effort ceiling**
(`max_developer_attempts`, `reasoning_class_ceiling`).

It cannot authorize a CEO-reserved action. `permissions.yaml` reserves ten of
them and `build_session_packet` already refuses to package a CEO-reserved task;
intake stops before a work order exists (see `intake.py`), so there is no
reserved work order to refuse later.

## How it becomes work the existing runtime understands

Three derivations, and all three are the *narrowing* direction:

    task_specification()  -> company.runtime.TaskSpecification, for plan_task
    path_scope()          -> company.runtime.PathScope, for the packet
    employee_contract()   -> the task-scoped agent contract

`employee_contract` is the interesting one. `contract_from_registry` produces a
contract whose `may_write` is empty, which in Bootstrap Mode means read-only,
so a packet built from it can carry no writable path at all. This method fills
`may_write` from `authorized_paths` and `may_not_modify` from
`forbidden_paths` **plus every protected path**. `build_session_packet` then
re-reads that contract and refuses any scope outside it — so the work order
reaches the packet through the existing authority check rather than around it.

## Read authority is authority, so it lives here

`authorized_read_paths` and `forbidden_read_paths` are fields of the work order
for the same reason `authorized_paths` is: they are a grant, they travel into
the fingerprint, and a later stage must not be able to derive a different one.

The runtime has always *modelled* read authority — `ExecutionAuthoritySnapshot`
carries `may_read`/`may_not_read` and `context_expansion_policy` enforces them
— but nothing ever filled it, so every snapshot recorded `may_read: []` and
reading worked only because the external session already held the checkout.
That is possession, not authorization.

Both roles receive the **same** read scope and differ only in write scope:
**read is a property of the task, write is a property of the role.** A reviewer
unable to read what the developer was allowed to change could not review it.

Empty stays empty. A work order stored before these fields existed decodes to
`()`, and an empty `may_read` grants nothing rather than everything — the
reading `context_expansion_policy` already gives it.
"""

from __future__ import annotations

from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.resource_classes import ReasoningClass, Risk
from ai_platform.serde import fingerprint as _fingerprint
from ai_platform.serde import to_jsonable
from company.runtime.git_evidence import assert_branch_name, assert_git_sha
from company.runtime.lifecycle import contract_from_registry
from company.runtime.path_scope import PathScope, normalise_path
from company.efficiency.strategy import EscalationReason
from company.efficiency.profile import resource_profile
from company.runtime.specification import ContextRequirements, TaskSpecification

from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    assert_ref,
    positive_int,
    ref_tuple,
    text_tuple,
)
from .errors import AuthorityEscalation, EngineeringError
from .protected import ProtectedSurface


WORK_ORDER_VERSION = 1

# The authority fields added when read authority stopped being assumed. They
# are omitted from `fingerprint()` only when *all* of them are empty, which is
# the record that predates read authority. See `fingerprint`.
_READ_FIELDS = ("authorized_read_paths", "forbidden_read_paths")

# A branch an engineering job is never assigned. Integration is a CEO act that
# happens somewhere else, so the work is always on a branch of its own.
FORBIDDEN_BRANCHES = frozenset({"main", "master", "HEAD", "trunk"})

# The reasoning classes an engineering work order may name as its ceiling.
# A and B mean "no reasoning needed", which is not an engineering job; F is the
# rare multi-perspective review of a major decision, which is not one either.
ALLOWED_CEILINGS = (ReasoningClass.C, ReasoningClass.D, ReasoningClass.E)

# The domain that routes an implementation task to specialist reasoning.
#
# This constant used to be written into *every* work order's task
# specification. The classifier's `specialist_reasoning` rule fires on a
# non-empty specialist domain, so every engineering job the company could
# issue classified D, and D and above is what selects the strongest model.
# Class C - the bounded single pass over a known contract, which is what most
# engineering work actually is - was unreachable in production.
#
# It is now the value a work order carries only when the work genuinely needs
# domain judgment, and `company.engineering.intake` decides that from the
# request rather than asserting it for everyone.
SPECIALIST_DOMAIN = "software_engineering"

# Three automatic developer attempts was the old default, chosen when nobody
# was counting what an attempt cost. The resource profile sets this now; the
# constant remains the ceiling for a work order that names no profile.
DEFAULT_MAX_DEVELOPER_ATTEMPTS = 3


CODE_REVIEW_CAPABILITY = "code_review"
"""Ordinary engineering review: does this change do what the order asked?

What `company/engineering/intake.py` asks for on every work order it derives
that the routing did not call architectural. Before the independent reviewer
existed, every work order asked for `software_architecture`, and because
`chief_architect` was the only employee holding it, every review routed to the
CTO's own employee - which then disqualified the CTO from approving that work's
integration. The first end-to-end pilot escalated to the CEO on exactly that,
and would have done so on every job forever.

**The choice is made in intake, not by this dataclass default.** Intake is
where the specialist domain is known, and a constructor default cannot see it.
The default below stays `software_architecture`, which is the cautious answer
for a work order assembled by hand with nothing else said: ask the architect.
See `docs/company_os_review_separation.md`.
"""

ARCHITECTURE_REVIEW_CAPABILITY = "software_architecture"
"""Specialist review, for work whose difficulty is in the design.

Still routed to `chief_architect`, and still worth the CTO's time. The cost is
that the CTO then cannot approve that job's integration, which is the rule
working rather than a problem to route around.
"""

# The specialist domains whose review genuinely needs the architect rather than
# an ordinary code reviewer. `security`, `governance` and `concurrency` escalate
# their *implementation* tier; only architecture changes who should read the
# diff.
ARCHITECTURE_REVIEW_DOMAINS: frozenset[str] = frozenset({"architecture"})


@dataclass(frozen=True)
class EngineeringWorkOrder:
    """One authorized engineering request. Immutable, and the authority ceiling."""

    work_order_id: str
    objective: str
    requested_by: str
    request_id: str
    authorized_branch: str
    authorized_paths: tuple[str, ...]
    acceptance_criteria: tuple[str, ...]
    authorized_on: dt.date
    implementation_capabilities: tuple[str, ...] = ("software_implementation",)
    review_capability: str = ARCHITECTURE_REVIEW_CAPABILITY
    forbidden_paths: tuple[str, ...] = ()
    # The read ceiling, derived from the owning capsules' declared `may_read`
    # together with the paths this task must necessarily inspect. Empty means
    # empty: a work order authorized before this field existed grants no read
    # scope rather than an unrestricted one.
    authorized_read_paths: tuple[str, ...] = ()
    # Read denials, which outrank the grant above wherever the two meet.
    forbidden_read_paths: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    context_refs: tuple[ContextRef, ...] = ()
    required_tests: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    protected: ProtectedSurface = field(default_factory=ProtectedSurface)
    base_commit: str = ""
    repository: str = "Simulation Factory"
    max_developer_attempts: int = DEFAULT_MAX_DEVELOPER_ATTEMPTS
    reasoning_class_ceiling: ReasoningClass = ReasoningClass.D
    risk: Risk = Risk.MEDIUM
    reversible: bool = True
    evidence_required: bool = True
    # The signals the classifier reads, carried on the work order instead of
    # asserted by `task_specification`. Empty and False are the routine case,
    # which is the whole point: routine work must be able to look routine.
    specialist_domain: str = ""
    novel: bool = False
    # Why the strongest tier was chosen despite a routine classification. A
    # value here is an authorization, so it lives in the work order and travels
    # into its fingerprint rather than being decided at briefing time.
    escalation: str = "none"
    # Which resource profile this job runs under. Names a profile in
    # `company.efficiency.profile`; an unknown name is refused at construction.
    resource_profile: str = "consumer"
    version: int = WORK_ORDER_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "work_order_id", assert_record_id(self.work_order_id, "work_order_id")
        )
        object.__setattr__(self, "objective", assert_prose(self.objective, "objective"))
        object.__setattr__(
            self, "requested_by", assert_named_person(self.requested_by, "requested_by")
        )
        object.__setattr__(
            self, "request_id", assert_record_id(self.request_id, "request_id")
        )
        object.__setattr__(
            self, "repository", assert_ref(self.repository, "repository")
        )
        branch = assert_branch_name(self.authorized_branch, "authorized_branch")
        if branch in FORBIDDEN_BRANCHES:
            raise AuthorityEscalation(
                f"authorized_branch {branch!r} is an integration branch. Engineering "
                "work is assigned its own branch; merging is a CEO decision."
            )
        object.__setattr__(self, "authorized_branch", branch)

        object.__setattr__(
            self,
            "authorized_paths",
            _path_tuple(self.authorized_paths, "authorized_paths"),
        )
        if not self.authorized_paths:
            raise EngineeringError(
                "authorized_paths is empty: an engineering work order that grants no "
                "writable path authorizes no engineering. An inspection-only request "
                "is a research task, not a work order."
            )
        object.__setattr__(
            self, "forbidden_paths", _path_tuple(self.forbidden_paths, "forbidden_paths")
        )
        object.__setattr__(
            self,
            "authorized_read_paths",
            _path_tuple(self.authorized_read_paths, "authorized_read_paths"),
        )
        object.__setattr__(
            self,
            "forbidden_read_paths",
            _path_tuple(self.forbidden_read_paths, "forbidden_read_paths"),
        )
        # A path the work order requires to be changed and forbids to be read
        # is an incoherent grant: the work cannot be done and the contradiction
        # would be resolved by whichever guard happened to run first. Refuse it
        # here instead, the way `ProtectedSurface.capture` refuses a path that
        # is both protected and authorized.
        unreadable = sorted(
            f"{rule} may not be read but must be written ({denial})"
            for rule in self.authorized_paths
            for denial in self.forbidden_read_paths
            if _read_overlaps(denial, rule)
        )
        if unreadable:
            raise AuthorityEscalation(
                "forbidden_read_paths reach a writable path: " + "; ".join(unreadable)
            )
        object.__setattr__(
            self,
            "acceptance_criteria",
            text_tuple(self.acceptance_criteria, "acceptance_criteria", limit=24),
        )
        if not self.acceptance_criteria:
            raise EngineeringError(
                "acceptance_criteria is required: nobody can review work against "
                "criteria that were never stated (constitution, Reference superiority)"
            )
        object.__setattr__(
            self, "constraints", text_tuple(self.constraints, "constraints", limit=24)
        )
        object.__setattr__(
            self, "required_tests", ref_tuple(self.required_tests, "required_tests", limit=24)
        )
        object.__setattr__(
            self, "evidence_refs", ref_tuple(self.evidence_refs, "evidence_refs", limit=24)
        )
        object.__setattr__(
            self,
            "implementation_capabilities",
            _capability_tuple(
                self.implementation_capabilities, "implementation_capabilities"
            ),
        )
        if not self.implementation_capabilities:
            raise EngineeringError("implementation_capabilities must name at least one")
        review = assert_record_id(self.review_capability, "review_capability")
        if review in self.implementation_capabilities:
            raise EngineeringError(
                f"review_capability {review!r} is also an implementation capability. "
                "One employee would then be eligible for both roles, and the review "
                "would not be independent."
            )
        object.__setattr__(self, "review_capability", review)

        if not isinstance(self.context_refs, tuple) or any(
            not isinstance(ref, ContextRef) for ref in self.context_refs
        ):
            raise EngineeringError("context_refs must be a tuple of ContextRef values")
        keys = [ref.key for ref in self.context_refs]
        duplicates = sorted({key for key in keys if keys.count(key) > 1})
        if duplicates:
            raise EngineeringError(
                "context_refs repeats a reference: " + ", ".join(duplicates)
            )
        if not isinstance(self.protected, ProtectedSurface):
            raise EngineeringError("protected must be a ProtectedSurface value")
        reaching = sorted(
            f"{rule} reaches protected path {self.protected.covers(rule)}"
            for rule in self.authorized_paths
            if self.protected.covers(rule)
        )
        overlapping = sorted(
            f"authorized {rule} contains protected {path}"
            for rule in self.authorized_paths
            for path in self.protected.paths
            if path.startswith(rule + "/")
        )
        if reaching or overlapping:
            raise AuthorityEscalation(
                "authorized_paths reach the protected governance surface: "
                + "; ".join(reaching + overlapping)
            )
        if self.base_commit:
            try:
                assert_git_sha(self.base_commit, "base_commit")
            except Exception as exc:  # LifecycleError, kept as one error type here
                raise EngineeringError(str(exc)) from exc
        object.__setattr__(self, "authorized_on", assert_day(self.authorized_on, "authorized_on"))
        object.__setattr__(
            self,
            "max_developer_attempts",
            positive_int(self.max_developer_attempts, "max_developer_attempts", maximum=8),
        )
        if not isinstance(self.reasoning_class_ceiling, ReasoningClass):
            raise EngineeringError("reasoning_class_ceiling must be a ReasoningClass")
        if self.reasoning_class_ceiling not in ALLOWED_CEILINGS:
            allowed = ", ".join(item.value for item in ALLOWED_CEILINGS)
            raise EngineeringError(
                f"reasoning_class_ceiling {self.reasoning_class_ceiling.value!r} is not "
                f"an engineering class; allowed: {allowed}"
            )
        if not isinstance(self.specialist_domain, str):
            raise EngineeringError("specialist_domain must be a string")
        object.__setattr__(self, "specialist_domain", self.specialist_domain.strip())
        if not isinstance(self.novel, bool):
            raise EngineeringError("novel must be a boolean")
        try:
            escalation = EscalationReason(str(self.escalation or "").strip() or "none")
        except ValueError as exc:
            allowed = ", ".join(item.value for item in EscalationReason)
            raise EngineeringError(f"escalation must be one of: {allowed}") from exc
        object.__setattr__(self, "escalation", escalation.value)
        # Refused, never defaulted: a work order naming a profile the company
        # does not have was authorized against a policy nobody wrote.
        try:
            profile = resource_profile(self.resource_profile)
        except ValueError as exc:
            raise EngineeringError(str(exc)) from exc
        object.__setattr__(self, "resource_profile", profile.name.value)
        if self.max_developer_attempts > profile.developer_attempts:
            raise EngineeringError(
                f"max_developer_attempts {self.max_developer_attempts} exceeds the "
                f"{profile.developer_attempts} the {profile.name.value} resource "
                "profile authorizes; raise the profile or lower the attempts"
            )
        if not isinstance(self.risk, Risk):
            raise EngineeringError("risk must be a Risk value")
        for name in ("reversible", "evidence_required"):
            if not isinstance(getattr(self, name), bool):
                raise EngineeringError(f"{name} must be a boolean")
        if self.version != WORK_ORDER_VERSION:
            raise EngineeringError(
                f"work order version must be {WORK_ORDER_VERSION}, got {self.version!r}"
            )

    # --- identity ----------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return to_jsonable(self)

    def fingerprint(self) -> str:
        """The immutability proof every later stage compares against.

        An empty read field is omitted, so that a work order authorized before
        read authority existed keeps the fingerprint it was stored with. The
        alternative was worse than it sounds: adding the fields changed the
        identity of every historical record, which meant a completed job could
        no longer have a decision recorded against it - its stage referenced a
        digest the work order no longer produced.

        Absent and empty already mean the same thing here, because an empty
        read scope grants nothing, so hashing them the same asserts nothing
        new. And a record stripped of the fields to chase an old digest is
        strictly *less* privileged than one carrying them, so this is not a
        route to forging authority - only to forfeiting it.
        """
        record = to_jsonable(self)
        # All of them or none. Dropping an empty `forbidden_read_paths` beside
        # a granted `authorized_read_paths` would restamp every work order
        # authorized *during* this milestone, which is the same failure one
        # step smaller - a record carrying read authority must hash the way it
        # hashed when it was stored.
        if not any(record.get(field) for field in _READ_FIELDS):
            record = {key: value for key, value in record.items() if key not in _READ_FIELDS}
        return _fingerprint(record)

    # --- derivations, all of them narrowing --------------------------------

    def path_scope(self) -> PathScope:
        """The write boundary the packet declares: granted paths, and everything off."""
        return PathScope(
            allowed=self.authorized_paths,
            forbidden=self.forbidden_paths + self.protected.paths,
        )

    def task_specification(self) -> TaskSpecification:
        """The work order expressed as the runtime's own task contract."""
        return TaskSpecification(
            task_id=self.work_order_id,
            objective=self.objective,
            required_capabilities=self.implementation_capabilities,
            risk=self.risk,
            reversible=self.reversible,
            evidence_required=self.evidence_required,
            requires_judgment=True,
            specialist_domain=self.specialist_domain,
            novel=self.novel,
            context=ContextRequirements(
                refs=self.context_refs,
                constraints=self.constraints,
                acceptance_criteria=self.acceptance_criteria,
            ),
            reasoning_class_ceiling=self.reasoning_class_ceiling,
            ceo_reserved=False,
            execution={"resource_profile": self.resource_profile},
        )

    def review_specification(self, reviewer_objective: str = "") -> TaskSpecification:
        """The same work order, routed to the review capability instead.

        A separate specification rather than a flag, because the two tasks have
        different required capabilities and therefore route to different
        employees. That difference *is* the separation of duties.
        """
        objective = reviewer_objective.strip() or (
            f"Independently review the implementation of work order "
            f"{self.work_order_id} against its acceptance criteria."
        )
        return TaskSpecification(
            task_id=f"{self.work_order_id}-review",
            objective=objective,
            required_capabilities=(self.review_capability,),
            risk=self.risk,
            reversible=self.reversible,
            evidence_required=True,
            requires_judgment=True,
            specialist_domain=self.specialist_domain,
            novel=self.novel,
            context=ContextRequirements(
                refs=self.context_refs,
                constraints=self.constraints,
                acceptance_criteria=self.acceptance_criteria,
            ),
            reasoning_class_ceiling=self.reasoning_class_ceiling,
            ceo_reserved=False,
            execution={"resource_profile": self.resource_profile},
        )

    def employee_contract(self, config: Any, employee: str) -> dict[str, Any]:
        """The canonical contract, narrowed to exactly this work order's scope.

        The registry contract grants no writable path; this fills `may_write`
        from the work order and `may_not_modify` from its forbidden and
        protected paths. `build_session_packet` re-reads the result, so the
        packet's scope is checked against the work order rather than asserted
        by it.
        """
        contract = contract_from_registry(employee, config)
        contract["may_write"] = list(self.authorized_paths)
        contract["may_not_modify"] = sorted(
            set(self.forbidden_paths) | set(self.protected.paths)
        )
        contract["may_read"] = list(self.authorized_read_paths)
        contract["may_not_read"] = list(self.forbidden_read_paths)
        contract["required_tests"] = list(self.required_tests)
        return contract

    def reviewer_contract(self, config: Any, employee: str) -> dict[str, Any]:
        """A read-only contract: a reviewer inspects, and changes nothing.

        `may_write` stays empty, which in Bootstrap Mode means the only packet
        this contract can carry is a read-only one.

        The read scope is the *same* one the developer held, because that is
        exactly the material under review: the files the work order authorized,
        the tests it required, the evidence it named and the capsule context it
        was given. Narrowing it below the developer's would leave the reviewer
        judging work it was not allowed to look at.
        """
        contract = contract_from_registry(employee, config)
        contract["may_not_modify"] = sorted(
            set(self.authorized_paths)
            | set(self.forbidden_paths)
            | set(self.protected.paths)
        )
        contract["may_read"] = list(self.authorized_read_paths)
        contract["may_not_read"] = list(self.forbidden_read_paths)
        return contract

    def assert_unchanged(self, fingerprint: str, stage: str) -> None:
        """Refuse to continue against a work order that is not the authorized one."""
        if fingerprint != self.fingerprint():
            raise AuthorityEscalation(
                f"{stage}: work order {self.work_order_id} has fingerprint "
                f"{self.fingerprint()}, and the stage references {fingerprint}. The "
                "authorized work order is immutable; a changed one is a new request."
            )

    # --- decoding ----------------------------------------------------------

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "EngineeringWorkOrder":
        """Decode a stored work order, refusing any field the schema does not name."""
        if not isinstance(data, Mapping):
            raise EngineeringError("a work order must be a mapping")
        unknown = sorted(set(data) - set(cls.__dataclass_fields__))
        if unknown:
            raise EngineeringError(
                "work order has unknown field(s): "
                + ", ".join(unknown)
                + ". A work order is an authority record; a field outside the schema "
                "is refused rather than ignored."
            )
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            objective=str(data.get("objective", "")),
            requested_by=str(data.get("requested_by", "")),
            request_id=str(data.get("request_id", "")),
            authorized_branch=str(data.get("authorized_branch", "")),
            authorized_paths=_sequence(data.get("authorized_paths"), "authorized_paths"),
            acceptance_criteria=_sequence(
                data.get("acceptance_criteria"), "acceptance_criteria"
            ),
            authorized_on=assert_day(data.get("authorized_on"), "authorized_on"),
            implementation_capabilities=_sequence(
                data.get("implementation_capabilities"), "implementation_capabilities"
            ),
            review_capability=str(
                data.get("review_capability", ARCHITECTURE_REVIEW_CAPABILITY)
            ),
            forbidden_paths=_sequence(data.get("forbidden_paths"), "forbidden_paths"),
            # Absent on a record stored before read authority existed. `()` is
            # the fail-closed reading and the only safe default: an empty
            # `may_read` grants nothing, so an old work order cannot acquire a
            # read scope simply by being decoded by newer code.
            authorized_read_paths=_sequence(
                data.get("authorized_read_paths"), "authorized_read_paths"
            ),
            forbidden_read_paths=_sequence(
                data.get("forbidden_read_paths"), "forbidden_read_paths"
            ),
            constraints=_sequence(data.get("constraints"), "constraints"),
            context_refs=tuple(
                _context_ref(item, index)
                for index, item in enumerate(_sequence_any(data.get("context_refs")))
            ),
            required_tests=_sequence(data.get("required_tests"), "required_tests"),
            evidence_refs=_sequence(data.get("evidence_refs"), "evidence_refs"),
            protected=ProtectedSurface.from_mapping(data.get("protected", {"entries": []})),
            base_commit=str(data.get("base_commit", "")),
            repository=str(data.get("repository", "Simulation Factory")),
            max_developer_attempts=_int(
                data.get("max_developer_attempts", DEFAULT_MAX_DEVELOPER_ATTEMPTS),
                "max_developer_attempts",
            ),
            reasoning_class_ceiling=_reasoning_class(
                data.get("reasoning_class_ceiling", ReasoningClass.D.value)
            ),
            specialist_domain=str(data.get("specialist_domain", "")),
            novel=_bool(data.get("novel", False), "novel"),
            escalation=str(data.get("escalation", "none") or "none"),
            resource_profile=str(data.get("resource_profile", "consumer") or "consumer"),
            risk=_risk(data.get("risk", Risk.MEDIUM.value)),
            reversible=_bool(data.get("reversible", True), "reversible"),
            evidence_required=_bool(data.get("evidence_required", True), "evidence_required"),
            version=_int(data.get("version", WORK_ORDER_VERSION), "version"),
        )


def _path_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise EngineeringError(f"{field_name} must be a list of repository paths")
    if len(values) > 32:
        raise EngineeringError(
            f"{field_name}: {len(values)} paths exceeds the 32 a work order may name. "
            "A scope that needs more than 32 rules is not a bounded scope."
        )
    paths = {
        normalise_path(item, f"{field_name}[{index}]")
        for index, item in enumerate(values)
    }
    return tuple(sorted(paths))


def _read_covers(rule: str, path: str) -> bool:
    """Whether `rule` grants `path`, wildcards included.

    Deliberately the same reading `company.runtime.context_expansion_policy`
    uses, because a rule that means one thing when the scope is derived and
    another when the scope is enforced is not a rule.
    """
    if any(token in rule for token in "*?["):
        return PurePosixPath(path).match(rule)
    return path == rule or path.startswith(rule + "/")


def _read_overlaps(rule: str, path: str) -> bool:
    """Whether `rule` and `path` touch at all, in either direction.

    A denial covering a subdirectory of a granted tree still touches it, and so
    does a denial the granted rule sits inside. Both directions count, because
    a denial that only half-applies is a denial nobody can reason about.
    """
    if _read_covers(rule, path) or _read_covers(path, rule):
        return True
    wildcard = min(
        (position for token in ("*", "?", "[") if (position := rule.find(token)) >= 0),
        default=-1,
    )
    if wildcard < 0:
        return False
    prefix = rule[:wildcard].rstrip("/")
    return bool(prefix) and _read_covers(path, prefix)


def collapse_read_rules(rules: Any) -> tuple[str, ...]:
    """Drop every rule another rule already covers, keeping coverage identical.

    Three capsules may each declare up to twelve read paths, so an un-collapsed
    union overruns the thirty-two a work order may name — measured at 35 for the
    widest real three-capsule selection. Collapsing brings the same selection to
    22 without removing a single readable path, because a rule is only dropped
    when another rule in the set already grants everything it grants.

    Public because the derivation in `intake` and the tests that check it must
    agree on what "the same scope" means.
    """
    kept = sorted({str(rule) for rule in rules if str(rule).strip()})
    return tuple(
        rule
        for rule in kept
        if not any(other != rule and _read_covers(other, rule) for other in kept)
    )


def _capability_tuple(values: Any, field_name: str) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise EngineeringError(f"{field_name} must be a list of capability names")
    names = {
        assert_record_id(item, f"{field_name}[{index}]")
        for index, item in enumerate(values)
    }
    return tuple(sorted(names))


def _sequence(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EngineeringError(f"{field_name} must be a list")
    return tuple(str(item) for item in value)


def _sequence_any(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)) or not isinstance(value, (list, tuple)):
        raise EngineeringError("context_refs must be a list")
    return tuple(value)


def _context_ref(value: Any, index: int) -> ContextRef:
    path = f"context_refs[{index}]"
    if not isinstance(value, Mapping):
        raise EngineeringError(f"{path} must be a mapping")
    extra = sorted(set(value) - {"kind", "ref", "reason", "span", "digest"})
    if extra:
        raise EngineeringError(f"{path} has unknown field(s): " + ", ".join(extra))
    span = value.get("span")
    parsed: tuple[int, int] | None = None
    if span is not None:
        if (
            not isinstance(span, (list, tuple))
            or len(span) != 2
            or any(isinstance(item, bool) or not isinstance(item, int) for item in span)
        ):
            raise EngineeringError(f"{path}.span must be [start, end]")
        parsed = (span[0], span[1])
    kind = value.get("kind")
    if not isinstance(kind, str):
        raise EngineeringError(f"{path}.kind must be a string")
    try:
        context_kind = ContextKind(kind)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ContextKind)
        raise EngineeringError(f"{path}.kind must be one of: {allowed}") from exc
    try:
        return ContextRef(
            kind=context_kind,
            ref=str(value.get("ref", "")),
            reason=str(value.get("reason", "")),
            span=parsed,
            digest=str(value.get("digest", "")),
        )
    except ValueError as exc:
        raise EngineeringError(f"{path}: {exc}") from exc


def _int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EngineeringError(f"{field_name} must be an integer")
    return value


def _bool(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise EngineeringError(f"{field_name} must be a boolean")
    return value


def _reasoning_class(value: Any) -> ReasoningClass:
    if not isinstance(value, str):
        raise EngineeringError("reasoning_class_ceiling must be a string")
    try:
        return ReasoningClass(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in ReasoningClass)
        raise EngineeringError(
            f"reasoning_class_ceiling must be one of: {allowed}"
        ) from exc


def _risk(value: Any) -> Risk:
    if not isinstance(value, str):
        raise EngineeringError("risk must be a string")
    try:
        return Risk(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in Risk)
        raise EngineeringError(f"risk must be one of: {allowed}") from exc


__all__ = [
    "ALLOWED_CEILINGS",
    "DEFAULT_MAX_DEVELOPER_ATTEMPTS",
    "FORBIDDEN_BRANCHES",
    "SPECIALIST_DOMAIN",
    "WORK_ORDER_VERSION",
    "EngineeringWorkOrder",
]
