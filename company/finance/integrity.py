"""What no single record can notice about itself.

Every record class in this package refuses the failures it can see from the
inside: a cost with no evidence, a negative rate, an approval signed by a
machine. This module reports the rest - the ones that need two records, or a
record and the permissions file, or a record and something only the caller
knows.

## It reports, it does not raise

`check_integrity` returns a sorted tuple of problem strings, and a caller that
wants an exception calls `assert_integrity`. That is the shape
`company/org_intelligence/integrity.py` and `company/workforce/integrity.py`
already use, and the reason is the same: a state directory with four problems
should report four, not the first one alphabetically.

## The three checks that need a caller's knowledge

Three failures cannot be seen from the records alone, so each takes an argument:

    external_reference_ids   which subject ids name somebody else's video or
                             channel - the research subsystem knows, finance
                             does not. Revenue against one of them is section
                             4's competitor failure.
    known_resource_ids       which usage and research record ids exist. A
                             mapping pointing at a task nobody measured is a
                             cost attributed to a measurement that is not there.
    permissions              the ceo_reserved list, so the rename detector can
                             notice if paid spend stops being reserved.

Each defaults to None meaning "not supplied", and a check that was not given its
input says so rather than passing silently.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable, Mapping

from .budget import BudgetLine
from .costs import (
    PAID_EXTERNAL_CATEGORIES,
    Attribution,
    CostAdjustment,
    CostRecord,
    Recurrence,
)
from .errors import FinanceIntegrityError
from .investment import ReuseEvent, ReusableInvestment
from .mapping import ResourceCostMapping
from .proposals import (
    PAID_SPEND_RESERVED_ACTION,
    SpendDecision,
    SpendProposal,
    SpendStatus,
    unreserved_action,
)
from .rates import CostRate, RateCard
from .revenue import PUBLIC_EVIDENCE_KINDS, RevenueRecord


def check_integrity(
    *,
    costs: Iterable[CostRecord] = (),
    adjustments: Iterable[CostAdjustment] = (),
    revenue: Iterable[RevenueRecord] = (),
    rates: Iterable[CostRate] = (),
    budgets: Iterable[BudgetLine] = (),
    mappings: Iterable[ResourceCostMapping] = (),
    investments: Iterable[ReusableInvestment] = (),
    reuse_events: Iterable[ReuseEvent] = (),
    proposals: Iterable[SpendProposal] = (),
    decisions: Iterable[SpendDecision] = (),
    external_reference_ids: Iterable[str] | None = None,
    known_resource_ids: Iterable[str] | None = None,
    permissions: Mapping[str, Any] | None = None,
) -> tuple[str, ...]:
    """Every cross-record financial problem, sorted. Empty means nothing found."""
    costs = tuple(costs)
    adjustments = tuple(adjustments)
    revenue = tuple(revenue)
    rates = tuple(rates)
    budgets = tuple(budgets)
    mappings = tuple(mappings)
    investments = tuple(investments)
    reuse_events = tuple(reuse_events)
    proposals = tuple(proposals)
    decisions = tuple(decisions)

    problems: list[str] = []
    problems.extend(_duplicate_ids(costs, revenue, rates, budgets, proposals, investments))
    problems.extend(_currency_mixing(costs, revenue, budgets))
    problems.extend(_allocation_consistency(costs))
    problems.extend(_adjustment_targets(costs, adjustments))
    problems.extend(_rate_overlaps(rates))
    problems.extend(_budget_scope(budgets, costs))
    problems.extend(_investment_events(investments, reuse_events))
    problems.extend(_spend_authority(proposals, decisions))
    problems.extend(_recurring_paid_costs(costs, proposals))
    problems.extend(_revenue_origin(revenue, external_reference_ids))
    problems.extend(_mapping_resources(mappings, known_resource_ids))
    if permissions is not None:
        problems.extend(_permissions_still_reserve(permissions))
    return tuple(sorted(set(problems)))


def assert_integrity(**kwargs: Any) -> None:
    """Raise `FinanceIntegrityError` with every problem, or return."""
    problems = check_integrity(**kwargs)
    if problems:
        raise FinanceIntegrityError(
            f"{len(problems)} financial integrity problem(s):\n- " + "\n- ".join(problems)
        )


# -- individual checks ------------------------------------------------------


def _duplicate_ids(*groups: Iterable[Any]) -> list[str]:
    """One id used twice is one of the two records nobody will ever read."""
    problems: list[str] = []
    for group in groups:
        seen: dict[str, str] = {}
        for record in group:
            kind = getattr(record, "kind", type(record).__name__)
            record_id = _identity(record)
            if record_id in seen:
                problems.append(
                    f"duplicate {kind} id {record_id!r}: two records claim it, and a "
                    "file-backed store keeps whichever was written first"
                )
            seen[record_id] = kind
    return problems


def _identity(record: Any) -> str:
    for name in (
        "cost_id",
        "revenue_id",
        "rate_id",
        "budget_id",
        "proposal_id",
        "investment_id",
        "adjustment_id",
        "mapping_id",
        "event_id",
        "decision_id",
    ):
        value = getattr(record, name, None)
        if isinstance(value, str) and value:
            return value
    return repr(record)


def _currency_mixing(
    costs: Iterable[CostRecord],
    revenue: Iterable[RevenueRecord],
    budgets: Iterable[BudgetLine],
) -> list[str]:
    """A subject whose records are in two currencies cannot be summed at all."""
    by_subject: dict[str, set[str]] = defaultdict(set)
    for cost in costs:
        by_subject[cost.subject.key].add(cost.currency)
    for record in revenue:
        by_subject[record.subject.key].add(record.currency)
    problems = [
        f"subject {subject} has records in {', '.join(sorted(currencies))}; no summary "
        "can add them, and nothing here converts a currency"
        for subject, currencies in sorted(by_subject.items())
        if len(currencies) > 1
    ]
    for budget in budgets:
        if budget.currency != budget.period.currency:
            problems.append(
                f"budget {budget.budget_id!r} is in {budget.currency} but reports in "
                f"period currency {budget.period.currency}"
            )
    return problems


def _allocation_consistency(costs: Iterable[CostRecord]) -> list[str]:
    """An allocated share must point at a parent, and must not exceed it."""
    by_id = {cost.cost_id: cost for cost in costs}
    shares: dict[str, list[CostRecord]] = defaultdict(list)
    problems: list[str] = []
    for cost in costs:
        if cost.attribution is not Attribution.ALLOCATED:
            continue
        parent = by_id.get(cost.parent_cost_id)
        if parent is None:
            problems.append(
                f"cost {cost.cost_id!r} is a share of {cost.parent_cost_id!r}, which is "
                "not among the records supplied"
            )
            continue
        if parent.currency != cost.currency:
            problems.append(
                f"cost {cost.cost_id!r} is in {cost.currency} but shares a parent in "
                f"{parent.currency}"
            )
            continue
        shares[cost.parent_cost_id].append(cost)
    for parent_id, group in sorted(shares.items()):
        parent = by_id[parent_id]
        allocated = group[0].amount
        for share in group[1:]:
            allocated = allocated + share.amount
        if allocated > parent.amount:
            problems.append(
                f"cost {parent_id!r} is {parent.amount} but its shares total {allocated}; "
                "an allocation cannot distribute more than there was"
            )
    return problems


def _adjustment_targets(
    costs: Iterable[CostRecord], adjustments: Iterable[CostAdjustment]
) -> list[str]:
    by_id = {cost.cost_id: cost for cost in costs}
    problems: list[str] = []
    for adjustment in adjustments:
        target = by_id.get(adjustment.cost_id)
        if target is None:
            problems.append(
                f"adjustment {adjustment.adjustment_id!r} corrects cost "
                f"{adjustment.cost_id!r}, which is not among the records supplied"
            )
            continue
        if target.currency != adjustment.currency:
            problems.append(
                f"adjustment {adjustment.adjustment_id!r} is in {adjustment.currency} "
                f"against a cost in {target.currency}"
            )
        if adjustment.adjusted_on < target.incurred_on:
            problems.append(
                f"adjustment {adjustment.adjustment_id!r} is dated "
                f"{adjustment.adjusted_on.isoformat()}, before the cost it corrects "
                f"({target.incurred_on.isoformat()})"
            )
    return problems


def _rate_overlaps(rates: Iterable[CostRate]) -> list[str]:
    """Two prices for one provider, unit and day is a correction somebody owes."""
    listed = tuple(rates)
    if not listed:
        return []
    try:
        return list(RateCard(listed).overlaps())
    except Exception as exc:  # duplicate rate ids surface here as one problem
        return [f"rate card cannot be built: {exc}"]


def _budget_scope(
    budgets: Iterable[BudgetLine], costs: Iterable[CostRecord]
) -> list[str]:
    """A budget whose period excludes every cost against its scope is misaligned."""
    problems: list[str] = []
    listed = tuple(costs)
    for budget in budgets:
        in_scope = [cost for cost in listed if cost.subject.key == budget.scope.key]
        if not in_scope:
            continue
        in_period = [cost for cost in in_scope if budget.period.contains(cost.incurred_on)]
        if not in_period:
            problems.append(
                f"budget {budget.budget_id!r} covers {budget.scope.key} over "
                f"{budget.period.period_id}, and all {len(in_scope)} cost(s) against that "
                "scope fall outside the period - the budget or the costs are on the wrong "
                "window"
            )
        if budget.category is not None:
            wrong = [
                cost.cost_id
                for cost in in_period
                if cost.category is not budget.category
            ]
            if len(wrong) == len(in_period) and wrong:
                problems.append(
                    f"budget {budget.budget_id!r} is for {budget.category.value} and every "
                    f"cost against {budget.scope.key} in its period is another category"
                )
    return problems


def _investment_events(
    investments: Iterable[ReusableInvestment], events: Iterable[ReuseEvent]
) -> list[str]:
    known = {item.investment_id for item in investments}
    problems: list[str] = []
    for event in events:
        if event.investment_id not in known:
            problems.append(
                f"reuse event {event.event_id!r} names investment "
                f"{event.investment_id!r}, which is not among the records supplied"
            )
    by_id = {item.investment_id: item for item in investments}
    for event in events:
        investment = by_id.get(event.investment_id)
        if investment is None or event.cost_avoided is None:
            continue
        if event.cost_avoided.currency != investment.currency:
            problems.append(
                f"reuse event {event.event_id!r} saves {event.cost_avoided.currency} "
                f"against an investment in {investment.currency}"
            )
        if event.occurred_on < investment.created_on:
            problems.append(
                f"reuse event {event.event_id!r} is dated before the investment it reuses "
                f"was created ({investment.created_on.isoformat()})"
            )
    return problems


def _spend_authority(
    proposals: Iterable[SpendProposal], decisions: Iterable[SpendDecision]
) -> list[str]:
    """CEO-reserved spend approved by nobody, or by somebody who is not the CEO."""
    by_id = {proposal.proposal_id: proposal for proposal in proposals}
    problems: list[str] = []
    approvals_by_proposal: dict[str, list[SpendDecision]] = defaultdict(list)
    for decision in decisions:
        if decision.proposal_id not in by_id:
            problems.append(
                f"spend decision {decision.decision_id!r} decides proposal "
                f"{decision.proposal_id!r}, which is not among the records supplied"
            )
            continue
        if decision.status is SpendStatus.APPROVED:
            approvals_by_proposal[decision.proposal_id].append(decision)
    for proposal_id, approvals in sorted(approvals_by_proposal.items()):
        proposal = by_id[proposal_id]
        if not proposal.requires_ceo_approval:
            continue
        if not any(decision.is_ceo for decision in approvals):
            problems.append(
                f"spend proposal {proposal_id!r} is CEO-reserved and its approval(s) "
                + ", ".join(sorted(decision.decision_id for decision in approvals))
                + " are not marked as the CEO's. Finance records the approval it was "
                "given; it cannot supply the one that was required"
            )
        for decision in approvals:
            if decision.is_ceo and not decision.evidence:
                problems.append(
                    f"spend decision {decision.decision_id!r} claims CEO approval with no "
                    "decision evidence"
                )
    return problems


def _recurring_paid_costs(
    costs: Iterable[CostRecord], proposals: Iterable[SpendProposal]
) -> list[str]:
    """Recurring money to an outside provider with no reserved-action proposal.

    The failure this catches is a subscription that started without ever being
    proposed: the cost records show it recurring, and nothing in the proposal set
    flags it as the CEO-reserved action permissions.yaml says it is.
    """
    flagged_services = {
        proposal.service
        for proposal in proposals
        if PAID_SPEND_RESERVED_ACTION in proposal.reserved_actions
    }
    problems: list[str] = []
    seen: set[str] = set()
    for cost in costs:
        if cost.recurrence is not Recurrence.RECURRING:
            continue
        if cost.category not in PAID_EXTERNAL_CATEGORIES:
            continue
        if cost.source in flagged_services or cost.subject.id in flagged_services:
            continue
        key = f"{cost.source}/{cost.subject.key}"
        if key in seen:
            continue
        seen.add(key)
        problems.append(
            f"cost {cost.cost_id!r} is recurring {cost.category.value} spend to "
            f"{cost.source!r} with no spend proposal flagging "
            f"{PAID_SPEND_RESERVED_ACTION}. Recurring paid spend is CEO-reserved"
        )
    return problems


def _revenue_origin(
    revenue: Iterable[RevenueRecord], external_reference_ids: Iterable[str] | None
) -> list[str]:
    """Revenue credited to somebody else's video, and evidence that is not ours."""
    listed = tuple(revenue)
    problems: list[str] = []
    for record in listed:
        kinds = {item.kind for item in record.evidence}
        public = sorted(kinds & PUBLIC_EVIDENCE_KINDS)
        if public:  # pragma: no cover - the constructor refuses this first
            problems.append(
                f"revenue {record.revenue_id!r} is backed by public evidence "
                f"({', '.join(public)}); revenue is never inferred from public data"
            )
    if external_reference_ids is None:
        if listed:
            problems.append(
                f"{len(listed)} revenue record(s) supplied with no external reference "
                "ids, so revenue credited to a competitor's video cannot be detected. "
                "Pass the research layer's reference ids to check it"
            )
        return problems
    external = set(external_reference_ids)
    for record in listed:
        if record.subject.id in external:
            problems.append(
                f"revenue {record.revenue_id!r} is credited to {record.subject.key}, which "
                "is an external reference - somebody else's video is never our revenue "
                "(brief section 4)"
            )
    return problems


def _mapping_resources(
    mappings: Iterable[ResourceCostMapping], known_resource_ids: Iterable[str] | None
) -> list[str]:
    if known_resource_ids is None:
        return []
    known = set(known_resource_ids)
    return [
        f"resource cost mapping {mapping.mapping_id!r} prices resource "
        f"{mapping.resource_ref!r}, which is not among the usage or research records "
        "supplied"
        for mapping in mappings
        if mapping.resource_ref not in known
    ]


def _permissions_still_reserve(permissions: Mapping[str, Any]) -> list[str]:
    """The rename detector: paid spend must still be CEO-reserved.

    If `permissions.yaml` stops naming `large_or_recurring_paid_api_spend`,
    `reserved_actions_for_spend` quietly stops flagging anything and no test
    fails. This is what makes that visible.
    """
    missing = unreserved_action(permissions)
    if not missing:
        return []
    return [
        "permissions.yaml ceo_reserved does not name "
        + ", ".join(missing)
        + ", so no spend proposal will be flagged as CEO-reserved. Either the action was "
        "renamed or the reservation was dropped"
    ]
