"""Every cross-record invariant, checked in one pass and reported together.

The record classes each refuse what they can see on their own. What none of them
can see is the other records and the registries: a finding cannot know whether
its signals exist, a recommendation cannot know whether its subject is an
employee, and a change proposal cannot know whether the recommendation it
implements was ever written down.

So this module takes everything and returns *every* problem, sorted, in the
style `company/validation/bootstrap.py` established. A session repairing an
organizational review learns the whole shape of the problem rather than its
first line.

Three of the checks are reachable only by records that arrived some way other
than a constructor - an older file, a hand-edited JSON, another tool - and those
are the ones worth reading twice:

    _self_approved          a recommendation or proposal in a decided state
                            with nobody's name on it
    _constitutional_gate    a no-subagent or mission change with no CEO flag
    _contract_mutation      an implementation path pointing at a canonical
                            company contract without CEO reservation

Each is refused at construction too. Checking twice is not redundancy here: the
constructor protects the code, and this protects the store.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .change import (
    CANONICAL_CONTRACTS,
    ApprovalAuthority,
    ChangeExperiment,
    OrganizationChangeProposal,
    OrganizationChangeReview,
)
from .errors import OrgIntelligenceIntegrityError
from .findings import OrganizationalFinding
from .management import (
    DEFAULT_MANAGEMENT_POLICY,
    ManagementGraph,
    ManagementPolicy,
)
from .recommendations import (
    CONSTITUTIONAL_POLICIES,
    OrganizationalRecommendation,
    RecommendationState,
    unreserved_actions,
)
from .review import OrganizationalReview
from .signals import OrganizationalSignal

_DECIDED_STATES = frozenset(
    {
        RecommendationState.APPROVED,
        RecommendationState.REJECTED,
        RecommendationState.SUPERSEDED,
        RecommendationState.IMPLEMENTED_ELSEWHERE,
    }
)


def check_integrity(
    *,
    org_registry: Mapping[str, Any] | None = None,
    permissions: Mapping[str, Any] | None = None,
    capability_ids: Iterable[str] = (),
    reviews: Iterable[OrganizationalReview] = (),
    signals: Iterable[OrganizationalSignal] = (),
    findings: Iterable[OrganizationalFinding] = (),
    recommendations: Iterable[OrganizationalRecommendation] = (),
    change_proposals: Iterable[OrganizationChangeProposal] = (),
    experiments: Iterable[ChangeExperiment] = (),
    change_reviews: Iterable[OrganizationChangeReview] = (),
    management_policy: ManagementPolicy = DEFAULT_MANAGEMENT_POLICY,
) -> tuple[str, ...]:
    """Return every integrity problem found, sorted. Empty means clean."""
    review_records = tuple(reviews)
    signal_records = tuple(signals)
    finding_records = tuple(findings)
    recommendation_records = tuple(recommendations)
    proposal_records = tuple(change_proposals)
    experiment_records = tuple(experiments)
    change_review_records = tuple(change_reviews)

    issues: list[str] = []
    issues += _duplicate_ids(
        review_records,
        signal_records,
        finding_records,
        recommendation_records,
        proposal_records,
        experiment_records,
        change_review_records,
    )
    issues += _windows(review_records, signal_records, finding_records)
    issues += _evidence(signal_records, finding_records, recommendation_records)
    issues += _references(
        review_records,
        signal_records,
        finding_records,
        recommendation_records,
        proposal_records,
        experiment_records,
        change_review_records,
    )
    issues += _subjects(
        org_registry, capability_ids, signal_records, recommendation_records, proposal_records
    )
    issues += _self_approved(recommendation_records, proposal_records)
    issues += _constitutional_gate(recommendation_records, proposal_records)
    issues += _contract_mutation(proposal_records)
    issues += _lifecycle(recommendation_records, proposal_records)
    if org_registry is not None:
        issues += _management(org_registry, management_policy)
    if permissions is not None:
        issues += _permission_drift(permissions)
    return tuple(sorted(dict.fromkeys(issues)))


def assert_integrity(**kwargs: Any) -> None:
    """Raise `OrgIntelligenceIntegrityError` with every issue, or return."""
    issues = check_integrity(**kwargs)
    if issues:
        raise OrgIntelligenceIntegrityError(issues)


# -- the checks ------------------------------------------------------------


def _duplicate_ids(*groups: tuple[Any, ...]) -> list[str]:
    fields = (
        "review_id",
        "signal_id",
        "finding_id",
        "recommendation_id",
        "proposal_id",
        "experiment_id",
    )
    issues: list[str] = []
    for group in groups:
        seen: dict[str, int] = {}
        for record in group:
            for name in fields:
                value = getattr(record, name, None)
                if isinstance(value, str) and value:
                    seen[value] = seen.get(value, 0) + 1
                    break
        for value, count in sorted(seen.items()):
            if count > 1:
                issues.append(f"duplicate record id {value!r} appears {count} times")
    return issues


def _windows(
    reviews: tuple[OrganizationalReview, ...],
    signals: tuple[OrganizationalSignal, ...],
    findings: tuple[OrganizationalFinding, ...],
) -> list[str]:
    issues: list[str] = []
    for record, label, window in (
        [(item, f"review {item.review_id}", item.window) for item in reviews]
        + [(item, f"signal {item.signal_id}", item.window) for item in signals]
        + [(item, f"finding {item.finding_id}", item.window) for item in findings]
    ):
        if window.end < window.start:
            issues.append(f"{label}: impossible window {window}")
    by_id = {item.review_id: item for item in reviews}
    for finding in findings:
        review = by_id.get(finding.review_id) if finding.review_id else None
        if review is None:
            continue
        if not finding.window.overlaps(review.window):
            issues.append(
                f"finding {finding.finding_id}: window {finding.window} lies outside its "
                f"review's window {review.window}"
            )
    return issues


def _evidence(
    signals: tuple[OrganizationalSignal, ...],
    findings: tuple[OrganizationalFinding, ...],
    recommendations: tuple[OrganizationalRecommendation, ...],
) -> list[str]:
    issues: list[str] = []
    for signal in signals:
        if not signal.evidence:
            issues.append(f"signal {signal.signal_id}: no evidence")
    for finding in findings:
        if not finding.evidence:
            issues.append(f"finding {finding.finding_id}: no evidence")
        if not finding.signal_ids:
            issues.append(f"finding {finding.finding_id}: no supporting signal")
    for recommendation in recommendations:
        if not recommendation.evidence:
            issues.append(f"recommendation {recommendation.recommendation_id}: no evidence")
    return issues


def _references(
    reviews: tuple[OrganizationalReview, ...],
    signals: tuple[OrganizationalSignal, ...],
    findings: tuple[OrganizationalFinding, ...],
    recommendations: tuple[OrganizationalRecommendation, ...],
    proposals: tuple[OrganizationChangeProposal, ...],
    experiments: tuple[ChangeExperiment, ...],
    change_reviews: tuple[OrganizationChangeReview, ...],
) -> list[str]:
    review_ids = {item.review_id for item in reviews}
    signal_ids = {item.signal_id for item in signals}
    finding_ids = {item.finding_id for item in findings}
    recommendation_ids = {item.recommendation_id for item in recommendations}
    proposal_ids = {item.proposal_id for item in proposals}
    experiment_ids = {item.experiment_id for item in experiments}

    issues: list[str] = []
    for finding in findings:
        if finding.review_id and reviews and finding.review_id not in review_ids:
            issues.append(
                f"finding {finding.finding_id}: review {finding.review_id!r} is not present"
            )
        if signals:
            for signal_id in finding.signal_ids:
                if signal_id not in signal_ids:
                    issues.append(
                        f"finding {finding.finding_id}: signal {signal_id!r} is not present"
                    )
    for recommendation in recommendations:
        for finding_id in recommendation.finding_ids:
            if findings and finding_id not in finding_ids:
                issues.append(
                    f"recommendation {recommendation.recommendation_id}: finding "
                    f"{finding_id!r} is not present"
                )
    for proposal in proposals:
        for recommendation_id in proposal.recommendation_ids:
            if recommendations and recommendation_id not in recommendation_ids:
                issues.append(
                    f"change proposal {proposal.proposal_id}: recommendation "
                    f"{recommendation_id!r} is not present"
                )
    for experiment in experiments:
        if proposals and experiment.change_proposal_id not in proposal_ids:
            issues.append(
                f"experiment {experiment.experiment_id}: change proposal "
                f"{experiment.change_proposal_id!r} is not present"
            )
    for review in change_reviews:
        if experiments and review.experiment_id not in experiment_ids:
            issues.append(
                f"change review {review.review_id}: experiment "
                f"{review.experiment_id!r} is not present"
            )
    return issues


def _known_employees(org_registry: Mapping[str, Any] | None) -> frozenset[str]:
    if not isinstance(org_registry, Mapping):
        return frozenset()
    employees = org_registry.get("employees")
    if not isinstance(employees, Mapping):
        return frozenset()
    return frozenset(str(key) for key in employees)


def _subjects(
    org_registry: Mapping[str, Any] | None,
    capability_ids: Iterable[str],
    signals: tuple[OrganizationalSignal, ...],
    recommendations: tuple[OrganizationalRecommendation, ...],
    proposals: tuple[OrganizationChangeProposal, ...],
) -> list[str]:
    """Unknown employees and capabilities, where the caller supplied a registry.

    A subject is checked only when it *looks* like one of the two kinds we can
    check: an employee subject on a signal, or a bare identifier elsewhere. A
    scope like `chief_architect/software_architecture` is split on the slash,
    because that is how `workforce_evidence` writes a performance scope.
    """
    employees = _known_employees(org_registry)
    capabilities = frozenset(str(item) for item in capability_ids)
    issues: list[str] = []
    if not employees:
        return issues

    from .signals import SubjectKind

    for signal in signals:
        if signal.subject_kind is SubjectKind.EMPLOYEE:
            name = signal.subject.split("/", 1)[0]
            if name not in employees:
                issues.append(
                    f"signal {signal.signal_id}: unknown employee {name!r}"
                )
        if (
            signal.subject_kind is SubjectKind.CAPABILITY
            and capabilities
            and _is_bare_identifier(signal.subject)
            and signal.subject not in capabilities
        ):
            issues.append(f"signal {signal.signal_id}: unknown capability {signal.subject!r}")
    for recommendation in recommendations:
        for subject in recommendation.subjects:
            name = subject.split("/", 1)[0]
            if _looks_like_employee(name, employees, capabilities):
                continue
            if name in employees or name in capabilities:
                continue
            issues.append(
                f"recommendation {recommendation.recommendation_id}: subject {subject!r} "
                "is neither a known employee nor a known capability"
            )
    for proposal in proposals:
        for subject in proposal.affected_subjects:
            name = subject.split("/", 1)[0]
            if _looks_like_employee(name, employees, capabilities):
                continue
            if name in employees or name in capabilities:
                continue
            issues.append(
                f"change proposal {proposal.proposal_id}: affected subject {subject!r} is "
                "neither a known employee nor a known capability"
            )
    return issues


def _is_bare_identifier(value: str) -> bool:
    """True for a snake_case name - the shape an employee or capability id has.

    A subject carrying a slash, a dot, a dash or a hash is a record id, a path
    or a workflow name, and holding those against the org registry would force
    every workflow to be an employee. The check exists to catch a misspelled
    role, not to narrow what a subject may be.
    """
    return bool(value) and not any(mark in value for mark in ("/", ".", "-", ":", "#", " "))


def _looks_like_employee(
    name: str, employees: frozenset[str], capabilities: frozenset[str]
) -> bool:
    if name in employees or name in capabilities:
        return True
    return not _is_bare_identifier(name)


def _self_approved(
    recommendations: tuple[OrganizationalRecommendation, ...],
    proposals: tuple[OrganizationChangeProposal, ...],
) -> list[str]:
    issues: list[str] = []
    for recommendation in recommendations:
        if recommendation.state in _DECIDED_STATES and recommendation.decision is None:
            issues.append(
                f"recommendation {recommendation.recommendation_id}: {recommendation.state.value} "
                "with no decision. Organizational Intelligence never approves its own work"
            )
        decision = recommendation.decision
        if decision is not None and decision.state is not recommendation.state:
            issues.append(
                f"recommendation {recommendation.recommendation_id}: state "
                f"{recommendation.state.value} contradicts decision {decision.state.value}"
            )
    for proposal in proposals:
        if proposal.state is not RecommendationState.PROPOSED and proposal.decision is None:
            issues.append(
                f"change proposal {proposal.proposal_id}: {proposal.state.value} with no "
                "decision. This subsystem proposes; people decide"
            )
    return issues


def _constitutional_gate(
    recommendations: tuple[OrganizationalRecommendation, ...],
    proposals: tuple[OrganizationChangeProposal, ...],
) -> list[str]:
    issues: list[str] = []
    for recommendation in recommendations:
        touched = set(recommendation.touches_policies) & CONSTITUTIONAL_POLICIES
        if touched and not recommendation.requires_ceo_approval:
            issues.append(
                f"recommendation {recommendation.recommendation_id}: touches "
                + ", ".join(sorted(touched))
                + " without requires_ceo_approval"
            )
        if recommendation.reserved_actions and not recommendation.requires_ceo_approval:
            issues.append(
                f"recommendation {recommendation.recommendation_id}: names reserved actions "
                "without requires_ceo_approval"
            )
    for proposal in proposals:
        touched = set(proposal.touches_policies) & CONSTITUTIONAL_POLICIES
        if touched and not proposal.requires_ceo_approval:
            issues.append(
                f"change proposal {proposal.proposal_id}: touches "
                + ", ".join(sorted(touched))
                + " without requires_ceo_approval"
            )
        if proposal.requires_ceo_approval and proposal.required_approval is not (
            ApprovalAuthority.CEO
        ):
            issues.append(
                f"change proposal {proposal.proposal_id}: CEO-reserved but the approval "
                f"authority says {proposal.required_approval.value}"
            )
    return issues


def _contract_mutation(proposals: tuple[OrganizationChangeProposal, ...]) -> list[str]:
    issues: list[str] = []
    for proposal in proposals:
        touched = [
            path for path in proposal.implementation_paths if path in CANONICAL_CONTRACTS
        ]
        if touched and not proposal.requires_ceo_approval:
            issues.append(
                f"change proposal {proposal.proposal_id}: would mutate "
                + ", ".join(sorted(touched))
                + " without CEO approval"
            )
    return issues


def _lifecycle(
    recommendations: tuple[OrganizationalRecommendation, ...],
    proposals: tuple[OrganizationChangeProposal, ...],
) -> list[str]:
    issues: list[str] = []
    for recommendation in recommendations:
        if (
            recommendation.state is RecommendationState.PROPOSED
            and recommendation.decision is not None
        ):
            issues.append(
                f"recommendation {recommendation.recommendation_id}: proposed, yet carries a "
                "decision"
            )
    for proposal in proposals:
        if proposal.state is RecommendationState.PROPOSED and proposal.decision is not None:
            issues.append(
                f"change proposal {proposal.proposal_id}: proposed, yet carries a decision"
            )
    return issues


def _management(org_registry: Mapping[str, Any], policy: ManagementPolicy) -> list[str]:
    graph = ManagementGraph.from_org_registry(org_registry, policy=policy)
    issues: list[str] = []
    for cycle in graph.cycles():
        issues.append("manager cycle: " + " -> ".join(cycle + (cycle[0],)))
    for employee_id, manager in graph.invalid_references():
        issues.append(
            f"{employee_id}: manager {manager!r} is neither an employee nor the external "
            f"root {graph.external_root!r}"
        )
    return issues


def _permission_drift(permissions: Mapping[str, Any]) -> list[str]:
    """Reserved actions this package maps to that `permissions.yaml` no longer names.

    The failure the workforce capsule flags as a risk: rename a key in
    `ceo_reserved` and the flagging stops without anything going red. Reported
    as an issue rather than raised, because the permission file is the authority
    - the mapping is what needs updating, and a person does that.
    """
    missing = unreserved_actions(permissions)
    if not missing:
        return []
    return [
        "permissions.yaml ceo_reserved does not name "
        + ", ".join(missing)
        + "; recommendations mapped to those actions will not be flagged"
    ]
