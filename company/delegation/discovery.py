"""Bounded work discovery: proposing candidates, never implementing them.

Selection chooses among work the company already knows about. Discovery is how
that register gets its first entry, and it is the more dangerous of the two by
a wide margin: selection is bounded by the register, and discovery is bounded
by nothing until somebody bounds it. A discovery capability with no envelope
reads whatever it likes, proposes whatever it notices, and turns every TODO
comment in the repository into work the company believes in.

So discovery here is permitted only when there is nothing eligible to select or
an authorized executive asks for it, it runs inside a `DiscoveryEnvelope` that
expires, it may read only the surfaces in `EvidenceSurface`, and its entire
output is a set of **proposed** candidates that a deterministic pass then
accepts or rejects one by one.

```
no eligible candidate
  -> DiscoveryEnvelope        what may be read, how much, until when
  -> proposed candidates      from a bounded reader or a bounded session
  -> validate_proposal()      thirteen checks, each named
  -> OPEN candidates          or rejections with reasons
```

## Why the evidence surfaces are a closed enum

"Read the repository and find something worth doing" is not a bounded
instruction, and the honest reason is not cost - it is that a proposal drawn
from arbitrary prose has no owner. Every surface below is a place where
somebody already wrote down that a problem exists, and attached their name to
it. A candidate traced to one of these can be argued with; a candidate traced
to a comment cannot.

`REPOSITORY_PROSE` is deliberately absent, and its absence is asserted by the
tests rather than left as a convention.

## Why validation is thirteen checks and not a score

The same reason eligibility is ten comparisons: a proposal that fails should
say which rule it broke, to somebody who can fix it. A confidence number
tells a reader that the system was unsure and nothing about what to do next.

**A rejected proposal is rejected.** It does not become a lower-priority
candidate, it does not get sent to a developer with a caveat, and it does not
get accepted because nothing else qualified. The whole point of the capability
is that "we found nothing defensible" stays available as an answer.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ai_platform.resource_classes import Risk
from ai_platform.serde import fingerprint as _fingerprint
from company.finance.money import Money

from .actions import ActionType, parse_action
from .candidates import (
    CandidateRegister,
    CandidateSource,
    CandidateStatus,
    WorkCandidate,
)
from .common import (
    assert_day,
    assert_named_person,
    assert_prose,
    assert_record_id,
    name_tuple,
    ref_tuple,
)
from .errors import AuthorityViolation, DelegationError
from .policy import parse_risk, risk_rank

MAX_DISCOVERY_CANDIDATES = 8
"""A hard ceiling no envelope may exceed.

Not a cost control. A discovery run that returns twenty proposals has stopped
choosing and started listing, and a manager handed twenty is back where the
company started: holding an objective and no decision.
"""


class EvidenceSurface(str, Enum):
    """Where discovery may look. Closed, and short on purpose.

    Every member is a place a person already recorded that a problem exists.
    There is no member for repository source or prose, because a proposal drawn
    from a comment has no author to argue with.
    """

    VALIDATION_REPORT = "validation_report"
    REVIEWER_ADVISORY = "reviewer_advisory"
    STOPPED_WORK_REPORT = "stopped_work_report"
    DEFERRED_FOLLOWUP = "deferred_followup"
    CANDIDATE_SOURCE_DOCUMENT = "candidate_source_document"
    COMPANY_OS_EVIDENCE_RECORD = "company_os_evidence_record"
    CAPSULE_METADATA = "capsule_metadata"
    TEST_FAILURE_EVIDENCE = "test_failure_evidence"
    KNOWN_DEFECT_RECORD = "known_defect_record"


# Which candidate source each surface may legitimately produce. A proposal
# whose declared source does not match the surface it came from is claiming a
# provenance it does not have.
SURFACE_SOURCES: dict[EvidenceSurface, frozenset[CandidateSource]] = {
    EvidenceSurface.VALIDATION_REPORT: frozenset(
        {CandidateSource.VALIDATION_REPORT, CandidateSource.KNOWN_DEFECT}
    ),
    EvidenceSurface.REVIEWER_ADVISORY: frozenset({CandidateSource.REVIEWER_ADVISORY}),
    EvidenceSurface.STOPPED_WORK_REPORT: frozenset({CandidateSource.STOPPED_WORK}),
    EvidenceSurface.DEFERRED_FOLLOWUP: frozenset({CandidateSource.DEFERRED_FOLLOWUP}),
    EvidenceSurface.CANDIDATE_SOURCE_DOCUMENT: frozenset(
        {
            CandidateSource.BACKLOG_ARTIFACT,
            CandidateSource.DEFERRED_FOLLOWUP,
            CandidateSource.KNOWN_DEFECT,
        }
    ),
    EvidenceSurface.COMPANY_OS_EVIDENCE_RECORD: frozenset(
        {CandidateSource.VALIDATION_REPORT, CandidateSource.BACKLOG_ARTIFACT}
    ),
    EvidenceSurface.CAPSULE_METADATA: frozenset({CandidateSource.MAINTENANCE_GAP}),
    EvidenceSurface.TEST_FAILURE_EVIDENCE: frozenset({CandidateSource.KNOWN_DEFECT}),
    EvidenceSurface.KNOWN_DEFECT_RECORD: frozenset({CandidateSource.KNOWN_DEFECT}),
}


def parse_surface(value: Any, field: str = "evidence_surface") -> EvidenceSurface:
    if isinstance(value, EvidenceSurface):
        return value
    if not isinstance(value, str):
        raise DelegationError(f"{field} must be an evidence surface name, got {value!r}")
    try:
        return EvidenceSurface(value)
    except ValueError as exc:
        allowed = ", ".join(item.value for item in EvidenceSurface)
        raise DelegationError(
            f"{field}: {value!r} is not a surface discovery may read. Use one of: "
            f"{allowed}. Reading the repository at large is not a surface, and "
            "adding one here is a CEO decision rather than an implementation "
            "detail."
        ) from exc


@dataclass(frozen=True)
class DiscoveryEnvelope:
    """What one discovery run may read, propose, and cost - and until when."""

    envelope_id: str
    objective_id: str
    department: str
    allowed_capsules: tuple[str, ...]
    allowed_surfaces: tuple[EvidenceSurface, ...]
    risk_ceiling: Risk
    budget: Money
    expires_on: dt.date
    authorized_by: str
    authority_source: str
    forbidden_actions: tuple[ActionType, ...] = ()
    max_candidates: int = 3

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "envelope_id", assert_record_id(self.envelope_id, "envelope_id")
        )
        object.__setattr__(
            self,
            "objective_id",
            assert_record_id(self.objective_id, "discovery.objective_id"),
        )
        object.__setattr__(
            self,
            "department",
            assert_prose(self.department, "discovery.department").lower(),
        )
        object.__setattr__(
            self,
            "allowed_capsules",
            name_tuple(self.allowed_capsules, "discovery.allowed_capsules"),
        )
        object.__setattr__(
            self,
            "allowed_surfaces",
            tuple(
                sorted(
                    {
                        parse_surface(item, "discovery.allowed_surfaces")
                        for item in (self.allowed_surfaces or ())
                    },
                    key=lambda item: item.value,
                )
            ),
        )
        object.__setattr__(
            self, "risk_ceiling", parse_risk(self.risk_ceiling, "discovery.risk_ceiling")
        )
        if not isinstance(self.budget, Money):
            raise DelegationError("discovery.budget must be Money")
        object.__setattr__(
            self, "expires_on", assert_day(self.expires_on, "discovery.expires_on")
        )
        object.__setattr__(
            self,
            "authorized_by",
            assert_named_person(self.authorized_by, "discovery.authorized_by"),
        )
        object.__setattr__(
            self,
            "authority_source",
            assert_prose(self.authority_source, "discovery.authority_source"),
        )
        object.__setattr__(
            self,
            "forbidden_actions",
            tuple(
                sorted(
                    {
                        parse_action(item, "discovery.forbidden_actions")
                        for item in (self.forbidden_actions or ())
                    },
                    key=lambda item: item.value,
                )
            ),
        )
        if (
            isinstance(self.max_candidates, bool)
            or not isinstance(self.max_candidates, int)
            or not 1 <= self.max_candidates <= MAX_DISCOVERY_CANDIDATES
        ):
            raise DelegationError(
                f"discovery.max_candidates must be between 1 and "
                f"{MAX_DISCOVERY_CANDIDATES}; a run that returns more has stopped "
                "choosing and started listing"
            )

        # --- the three refusals --------------------------------------------
        if not self.allowed_capsules:
            raise DelegationError(
                f"{self.envelope_id}: no capsules are allowed, so this envelope "
                "authorizes discovery over nothing in particular. An empty "
                "allow-list is not a small scope; it is an unstated one."
            )
        if not self.allowed_surfaces:
            raise DelegationError(
                f"{self.envelope_id}: no evidence surfaces are allowed. Discovery "
                "with no declared surface is repository exploration."
            )

    def expired_on(self, day: dt.date) -> bool:
        return assert_day(day, "day") > self.expires_on

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "objective_id": self.objective_id,
            "department": self.department,
            "allowed_capsules": list(self.allowed_capsules),
            "allowed_surfaces": [item.value for item in self.allowed_surfaces],
            "risk_ceiling": self.risk_ceiling.value,
            "budget": self.budget.to_dict(),
            "expires_on": self.expires_on.isoformat(),
            "authorized_by": self.authorized_by,
            "authority_source": self.authority_source,
            "forbidden_actions": [item.value for item in self.forbidden_actions],
            "max_candidates": self.max_candidates,
        }

    def fingerprint(self) -> str:
        return _fingerprint(self.to_dict())


class ProposalCheck(str, Enum):
    """The thirteen gates a proposed candidate passes before it is OPEN."""

    ENVELOPE_LIVE = "envelope_live"
    EVIDENCE_EXISTS = "evidence_exists"
    SURFACE_ALLOWED = "surface_allowed"
    CAPSULE_RESOLVES = "capsule_resolves"
    DEPARTMENT_MATCHES = "department_matches"
    PROBLEM_CONCRETE = "problem_concrete"
    CRITERIA_FALSIFIABLE = "criteria_falsifiable"
    WRITE_SCOPE_BOUNDED = "write_scope_bounded"
    RISK_CLASSIFIED = "risk_classified"
    RESOURCE_PROFILE_KNOWN = "resource_profile_known"
    ACTIONS_PERMITTED = "actions_permitted"
    DEPENDENCIES_REPRESENTED = "dependencies_represented"
    NOT_DUPLICATE = "not_duplicate"


PROPOSAL_CHECKS: tuple[ProposalCheck, ...] = tuple(ProposalCheck)

ACTIVE_STATUSES: frozenset[CandidateStatus] = frozenset(
    {CandidateStatus.OPEN, CandidateStatus.SELECTED, CandidateStatus.BLOCKED}
)
"""What counts as an existing claim for the duplicate check.

A COMPLETED or SUPERSEDED candidate does not block a new proposal about the
same subject, because the world moved on. A DEFERRED one does not either: the
company said not now, not never.
"""


@dataclass(frozen=True)
class ProposalVerdict:
    """One proposed candidate, measured. Accepted means every check passed."""

    candidate_id: str
    accepted: bool
    passed: tuple[ProposalCheck, ...]
    failed: tuple[ProposalCheck, ...]
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "accepted": self.accepted,
            "passed": [item.value for item in self.passed],
            "failed": [item.value for item in self.failed],
            "reasons": list(self.reasons),
        }


def _subject_of(candidate: WorkCandidate) -> frozenset[str]:
    """The write scope a duplicate check compares on.

    Two candidates proposing to change the same files about the same capsule
    are the same claim however differently they are worded, and wording is the
    one thing a generated proposal can vary freely.
    """
    return frozenset(candidate.allowed_write_scope)


def validate_proposal(
    candidate: WorkCandidate,
    envelope: DiscoveryEnvelope,
    *,
    surface: Any,
    register: CandidateRegister,
    capsule_paths: dict[str, tuple[str, ...]],
    today: dt.date,
    reserved_actions: Sequence[ActionType] = (),
    repo_root: str | Path | None = None,
) -> ProposalVerdict:
    """Thirteen deterministic checks. Anything less than all of them is a reject.

    `capsule_paths` maps a capsule id to the paths it owns, supplied by the
    caller from the capsule index. A capsule the caller cannot describe fails
    `capsule_resolves` rather than being trusted.
    """
    if not isinstance(candidate, WorkCandidate):
        raise DelegationError("validate_proposal takes a WorkCandidate")
    if not isinstance(envelope, DiscoveryEnvelope):
        raise DelegationError("validate_proposal takes a DiscoveryEnvelope")
    wanted_surface = parse_surface(surface, "surface")
    passed: list[ProposalCheck] = []
    failed: list[ProposalCheck] = []
    reasons: list[str] = []

    def record(check: ProposalCheck, ok: bool, why: str) -> None:
        if ok:
            passed.append(check)
        else:
            failed.append(check)
            reasons.append(f"{check.value}: {why}")

    record(
        ProposalCheck.ENVELOPE_LIVE,
        not envelope.expired_on(today),
        f"the discovery envelope expired on {envelope.expires_on.isoformat()} and "
        f"today is {today.isoformat()}; the work may still be real, the authority "
        "to propose it without asking is what ran out",
    )
    root = Path(repo_root) if repo_root is not None else None
    if root is None:
        record(
            ProposalCheck.EVIDENCE_EXISTS,
            bool(candidate.evidence_refs),
            "no evidence refs",
        )
    else:
        missing = [
            ref for ref in candidate.evidence_refs if not (root / ref).exists()
        ]
        record(
            ProposalCheck.EVIDENCE_EXISTS,
            bool(candidate.evidence_refs) and not missing,
            "evidence that does not exist: " + ", ".join(missing)
            if missing
            else "no evidence refs",
        )
    record(
        ProposalCheck.SURFACE_ALLOWED,
        wanted_surface in set(envelope.allowed_surfaces)
        and candidate.source_type in SURFACE_SOURCES.get(wanted_surface, frozenset()),
        f"{wanted_surface.value} is not an allowed surface for this envelope, or "
        f"source {candidate.source_type.value} is not a provenance that surface "
        "can produce",
    )
    owns = capsule_paths.get(candidate.capsule_id)
    record(
        ProposalCheck.CAPSULE_RESOLVES,
        owns is not None and candidate.capsule_id in set(envelope.allowed_capsules),
        f"{candidate.capsule_id} is not a capsule this envelope allows, or the "
        "capsule index does not describe it",
    )
    record(
        ProposalCheck.DEPARTMENT_MATCHES,
        candidate.department == envelope.department,
        f"{candidate.department} is not {envelope.department}",
    )
    # The candidate constructor already refused an unfalsifiable problem
    # statement, so reaching here means it held. Re-checked anyway: a proposal
    # that arrived as a decoded mapping may have bypassed nothing, but this
    # module should not depend on which door it came through.
    from company.engineering.criteria import is_falsifiable_criterion

    record(
        ProposalCheck.PROBLEM_CONCRETE,
        is_falsifiable_criterion(candidate.problem_statement),
        "the problem statement names no subject a reviewer could check",
    )
    record(
        ProposalCheck.CRITERIA_FALSIFIABLE,
        bool(candidate.falsifiable_criteria()),
        "no acceptance criterion could be marked pass or fail",
    )
    if owns:
        outside = sorted(
            path
            for path in candidate.allowed_write_scope
            if not any(path == own or path.startswith(own.rstrip("/") + "/") for own in owns)
        )
    else:
        outside = list(candidate.allowed_write_scope)
    record(
        ProposalCheck.WRITE_SCOPE_BOUNDED,
        bool(candidate.allowed_write_scope) and not outside,
        "the write scope is empty, or reaches outside the owning capsule: "
        + ", ".join(outside),
    )
    record(
        ProposalCheck.RISK_CLASSIFIED,
        risk_rank(candidate.risk) <= risk_rank(envelope.risk_ceiling),
        f"{candidate.risk.value} exceeds the discovery ceiling "
        f"{envelope.risk_ceiling.value}",
    )
    record(
        ProposalCheck.RESOURCE_PROFILE_KNOWN,
        bool(candidate.estimated_resource_profile),
        "no resource profile",
    )
    needed = set(candidate.required_action_set())
    blocked = sorted(
        item.value
        for item in needed & (set(envelope.forbidden_actions) | set(reserved_actions))
    )
    record(
        ProposalCheck.ACTIONS_PERMITTED,
        not blocked,
        "the work needs action(s) the envelope forbids or the CEO reserves: "
        + ", ".join(blocked),
    )
    unknown_deps = [
        item for item in candidate.dependencies if register.candidate(item) is None
    ]
    record(
        ProposalCheck.DEPENDENCIES_REPRESENTED,
        not unknown_deps,
        "depends on candidates the register does not hold: " + ", ".join(unknown_deps),
    )
    subject = _subject_of(candidate)
    clash = [
        item.candidate_id
        for item in register.candidates
        if item.candidate_id != candidate.candidate_id
        and item.status in ACTIVE_STATUSES
        and item.capsule_id == candidate.capsule_id
        and subject
        and _subject_of(item) & subject
    ]
    if register.candidate(candidate.candidate_id) is not None:
        clash.append(candidate.candidate_id)
    record(
        ProposalCheck.NOT_DUPLICATE,
        not clash,
        "an active candidate already claims this work: " + ", ".join(sorted(set(clash))),
    )

    return ProposalVerdict(
        candidate_id=candidate.candidate_id,
        accepted=not failed,
        passed=tuple(passed),
        failed=tuple(failed),
        reasons=tuple(reasons),
    )


@dataclass(frozen=True)
class DiscoveryResult:
    """What one discovery run produced, accepted and rejected alike."""

    envelope_id: str
    objective_id: str
    verdicts: tuple[ProposalVerdict, ...] = ()
    accepted: tuple[WorkCandidate, ...] = ()
    surfaces_read: tuple[EvidenceSurface, ...] = ()
    notes: str = ""

    @property
    def found_anything(self) -> bool:
        return bool(self.accepted)

    def accepted_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.accepted)

    def rejected_ids(self) -> tuple[str, ...]:
        return tuple(item.candidate_id for item in self.verdicts if not item.accepted)

    def to_dict(self) -> dict[str, Any]:
        return {
            "envelope_id": self.envelope_id,
            "objective_id": self.objective_id,
            "verdicts": [item.to_dict() for item in self.verdicts],
            "accepted": [item.to_dict() for item in self.accepted],
            "surfaces_read": [item.value for item in self.surfaces_read],
            "notes": self.notes,
        }


def run_discovery(
    proposals: Sequence[tuple[WorkCandidate, Any]],
    envelope: DiscoveryEnvelope,
    *,
    register: CandidateRegister,
    capsule_paths: dict[str, tuple[str, ...]],
    today: dt.date,
    reserved_actions: Sequence[ActionType] = (),
    repo_root: str | Path | None = None,
) -> DiscoveryResult:
    """Validate a set of proposals against one envelope.

    `proposals` pairs each candidate with the surface it was drawn from, so a
    proposal cannot claim a provenance the run did not actually read. This
    function does no reading of its own: whoever produced the proposals - a
    deterministic reader, or one bounded executive session - is the thing
    bounded by `allowed_surfaces`, and this is the gate their output passes.
    """
    if not isinstance(envelope, DiscoveryEnvelope):
        raise DelegationError("run_discovery takes a DiscoveryEnvelope")
    if len(proposals) > envelope.max_candidates:
        raise AuthorityViolation(
            f"{envelope.envelope_id}: {len(proposals)} proposals against a ceiling "
            f"of {envelope.max_candidates}. A discovery run that exceeded its own "
            "ceiling is not trimmed to fit; the whole run is refused, because "
            "which ones to drop is the judgement the ceiling existed to avoid."
        )
    verdicts: list[ProposalVerdict] = []
    accepted: list[WorkCandidate] = []
    surfaces: list[EvidenceSurface] = []
    # Accepted proposals join the comparison set as they are accepted, so two
    # proposals in one run that claim the same work cannot both get through.
    running = register
    for candidate, surface in proposals:
        verdict = validate_proposal(
            candidate,
            envelope,
            surface=surface,
            register=running,
            capsule_paths=capsule_paths,
            today=today,
            reserved_actions=reserved_actions,
            repo_root=repo_root,
        )
        verdicts.append(verdict)
        read = parse_surface(surface, "surface")
        if read not in surfaces:
            surfaces.append(read)
        if verdict.accepted:
            accepted.append(candidate)
            running = CandidateRegister(running.candidates + (candidate,))
    return DiscoveryResult(
        envelope_id=envelope.envelope_id,
        objective_id=envelope.objective_id,
        verdicts=tuple(verdicts),
        accepted=tuple(accepted),
        surfaces_read=tuple(surfaces),
    )


# --- one bounded reader ----------------------------------------------------
#
# Discovery needs something that produces proposals. A model is one option and
# is authorized by Phase 12 of the objective; a deterministic reader over a
# structured surface is cheaper, reproducible, and the right default when the
# surface is already machine-readable.
#
# This is that reader, and it is deliberately the narrowest useful one: capsule
# revalidation. A capsule declares `recheck_on`; once that date passes, the
# capsule is making claims nobody has confirmed since. That is a maintenance
# gap a person wrote down, the check is a date comparison, and the resulting
# problem statement names a file and a date rather than a direction.
#
# It reads at most one small JSON file per allowed capsule. It does not open a
# source file, walk a tree, or read prose.


def capsule_revalidation_proposals(
    envelope: DiscoveryEnvelope,
    index: Any,
    *,
    today: dt.date,
    seed_dir: str = "knowledge/company_os/capsules/seeds",
) -> tuple[tuple[WorkCandidate, EvidenceSurface], ...]:
    """Propose a revalidation candidate for each allowed capsule that is stale.

    Staleness is not recomputed here. `CapsuleIndex.needing_revalidation` already
    owns that question - it weighs the recheck date *and* the recorded source
    digests, so a capsule whose code changed under it is stale even inside its
    window. Re-deriving it from `recheck_on` alone would be a second, worse
    answer to a question the knowledge layer already answers.

    An empty result means every allowed capsule is still trustworthy, which is
    a real answer and, in a well-maintained repository, the common one.
    """
    if EvidenceSurface.CAPSULE_METADATA not in set(envelope.allowed_surfaces):
        return ()
    allowed = set(envelope.allowed_capsules)
    out: list[tuple[WorkCandidate, EvidenceSurface]] = []
    for capsule_id in index.needing_revalidation(today):
        if capsule_id not in allowed:
            continue
        capsule = index.get(capsule_id)
        if capsule is None:
            continue
        seed = f"{seed_dir}/{capsule_id}.json"
        tests = tuple(getattr(capsule, "tests", ()) or ())
        out.append(
            (
                WorkCandidate(
                    candidate_id=f"revalidate-{capsule_id}"[:64],
                    title=f"Revalidate capsule {capsule_id}",
                    description=(
                        f"{capsule_id} is past the freshness the knowledge layer "
                        "computes for it."
                    ),
                    capsule_id=capsule_id,
                    department=envelope.department,
                    source_type=CandidateSource.MAINTENANCE_GAP,
                    source_ref=seed,
                    problem_statement=(
                        f"{seed} is reported stale by "
                        f"CapsuleIndex.needing_revalidation on "
                        f"{today.isoformat()}, so the capsule states facts nobody "
                        "has confirmed against the code it describes."
                    ),
                    expected_value=(
                        "A capsule a session can be handed instead of the "
                        "subsystem, rather than one whose freshness lapsed."
                    ),
                    risk=Risk.LOW,
                    created_at=today,
                    evidence_refs=(seed,),
                    acceptance_criteria=(
                        f"Every fact in {seed} is confirmed against the code it "
                        "describes, or corrected.",
                        f"{seed} records a last_reviewed of {today.isoformat()} and "
                        "source_digests matching the files it names.",
                    )
                    + ((f"{tests[0]} passes.",) if tests else ()),
                    allowed_write_scope=(seed,),
                    estimated_resource_profile="consumer",
                    goal_tags=("maintenance", "capsule", "freshness"),
                ),
                EvidenceSurface.CAPSULE_METADATA,
            )
        )
        if len(out) >= envelope.max_candidates:
            break
    return tuple(out)


# --- a second bounded reader -----------------------------------------------
#
# The capsule reader answers "is anything stale?". In a well-maintained
# repository the honest answer is usually no, and the final end-to-end pilot
# ended with discovery reachable and nothing to read. That is a gap in coverage
# rather than in the architecture: the company runs a deterministic gate that
# already records, in machine-readable form, the maintenance findings it will
# not block on. Those are advisory precisely because nobody has been asked to
# fix them, which is the definition of known work nobody has chosen.
#
# This reader turns a failing ADVISORY gate check into a candidate. It reads
# one report that the caller already produced. It does not run the gate, walk
# the repository, or read prose, and it refuses to propose anything from a
# REQUIRED check - a failing required check is a blocker, and routing a blocker
# into the work register would let the company schedule around something that
# is supposed to stop it.


# Which advisory checks this reader knows how to turn into bounded work, and
# where the work would be written. A check absent from this table produces no
# candidate: a finding the reader cannot scope is a finding a person should
# read, not one to hand a developer a write scope for.
_ADVISORY_WORK: dict[str, dict[str, Any]] = {
    "architecture.subsystem_ownership_bounded": {
        "capsule_id": "company-knowledge-capsules",
        "write_scope": ("knowledge/company_os/capsules/seeds",),
        "title": "Declare capsule ownership for the modules no capsule claims",
        "goal_tags": ("maintenance", "architecture", "ownership"),
        "expected_value": (
            "Every module resolves to an owning capsule, so a session handed a "
            "capsule is handed all of the code that capsule is responsible for."
        ),
        "criteria": (
            "Every module named in the finding is listed in the owns_paths of "
            "exactly one capsule seed.",
            "python -m company.integration check --repo-root . reports "
            "architecture.subsystem_ownership_bounded as passing.",
            "No module is claimed by two capsules.",
        ),
    },
}


def gate_advisory_proposals(
    envelope: DiscoveryEnvelope,
    report: Mapping[str, Any],
    *,
    today: dt.date,
    report_ref: str,
) -> tuple[tuple[WorkCandidate, EvidenceSurface], ...]:
    """Propose one candidate per failing ADVISORY gate check this reader scopes.

    `report` is the gate's own JSON, produced by the caller. Required checks are
    skipped whatever their status, and a finding carrying no evidence produces
    nothing, because a problem statement that cannot name a file is a direction.
    """
    if EvidenceSurface.VALIDATION_REPORT not in set(envelope.allowed_surfaces):
        return ()
    allowed = set(envelope.allowed_capsules)
    required = set(report.get("required_check_ids") or ())
    out: list[tuple[WorkCandidate, EvidenceSurface]] = []
    for section in report.get("sections") or ():
        for check in section.get("checks") or ():
            check_id = str(check.get("check_id", ""))
            if check.get("status") != "fail" or check_id in required:
                continue
            shape = _ADVISORY_WORK.get(check_id)
            if shape is None:
                continue
            if shape["capsule_id"] not in allowed:
                continue
            evidence = tuple(str(item) for item in (check.get("evidence") or ()))
            if not evidence:
                continue
            detail = str(check.get("detail", "")).strip()
            out.append(
                (
                    WorkCandidate(
                        candidate_id=f"gate-{check_id.replace('.', '-')}"[:64],
                        title=shape["title"],
                        description=(
                            f"The production integration gate reports {check_id} "
                            "as failing. It is advisory, so it blocks nothing and "
                            "nobody has been asked to fix it."
                        ),
                        capsule_id=shape["capsule_id"],
                        department=envelope.department,
                        source_type=CandidateSource.VALIDATION_REPORT,
                        source_ref=report_ref,
                        problem_statement=(
                            f"{check_id} fails in {report_ref} on "
                            f"{today.isoformat()}: {detail}"
                        ),
                        expected_value=shape["expected_value"],
                        risk=Risk.LOW,
                        created_at=today,
                        evidence_refs=(report_ref,) + evidence[:4],
                        acceptance_criteria=tuple(shape["criteria"]),
                        allowed_write_scope=tuple(shape["write_scope"]),
                        estimated_resource_profile="consumer",
                        goal_tags=tuple(shape["goal_tags"]),
                    ),
                    EvidenceSurface.VALIDATION_REPORT,
                )
            )
            if len(out) >= envelope.max_candidates:
                return tuple(out)
    return tuple(out)


__all__ = [
    "ACTIVE_STATUSES",
    "gate_advisory_proposals",
    "MAX_DISCOVERY_CANDIDATES",
    "PROPOSAL_CHECKS",
    "SURFACE_SOURCES",
    "DiscoveryEnvelope",
    "DiscoveryResult",
    "EvidenceSurface",
    "ProposalCheck",
    "ProposalVerdict",
    "parse_surface",
    "capsule_revalidation_proposals",
    "run_discovery",
    "validate_proposal",
]
