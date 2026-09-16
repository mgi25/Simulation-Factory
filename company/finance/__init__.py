"""Company OS finance: what things cost, what they earned, and what is unknown.

The deterministic financial evidence layer. It records money and computes over
what was recorded. It does not forecast, does not estimate, and does not spend.

## What it answers

What did a video cost? How much of that was AI? What did it earn? What is the
margin - or which measurement is missing so there is no margin to report? When
does a reusable tool pay for itself, and is that observed or assumed? Should a
recurring API subscription go to the CEO?

## Four rules the whole package is built on

1. **Unknown stays unknown.** Every figure is a number, or `None` with a reason
   in a `missing` tuple. A gap never becomes a zero, because a zero cost reads
   as free and a zero consumption reads as an untouched budget.
2. **Money is Decimal and carries its currency.** No float arithmetic anywhere,
   and no conversion between currencies - that needs a dated exchange-rate
   observation nobody has supplied.
3. **Evidence or no record.** A cost, a revenue line, a price and a budget all
   refuse construction without a pointer to something a second person can check.
4. **Append-only.** A correction is a new record that supersedes an old one.
   Nothing recorded is edited, so what the company believed in March is still
   readable in September.

## What it deliberately does not have

No `profit_score`, no `format_score`, no `company_financial_health` - section 23
and constitution rule 3. Financial metrics stay separate dimensions because the
company's actual objective, long-term profitable audience growth, is not one
number and a single number would be optimised instead of it.

No payment execution, no subscription creation, no permission change. Finance
records a `SpendProposal` and the evidence behind it; `permissions.yaml` says
`large_or_recurring_paid_api_spend` is CEO-reserved, and a human decides.

## Where the measurements come from

`ai_platform.usage.ResourceUsageRecord` and the research subsystem's
`ResearchResourceRecord` already count tokens, tool calls and minutes. This
package never recounts them (constitution rule 15) and never imports them
either: `mapping.py` reads a documented attribute set off whatever object it is
handed, so the boundary stays one-way and the measuring subsystems can move
without this one noticing.
"""

from .budget import (
    BudgetConsumption,
    BudgetLine,
    ConsumptionState,
    LimitKind,
    consumption,
)
from .common import AUTOMATIC_MARKERS, SubjectKind, SubjectRef
from .costs import (
    PAID_EXTERNAL_CATEGORIES,
    AdjustmentKind,
    AllocationMethod,
    AllocationShare,
    Attribution,
    CostAdjustment,
    CostCategory,
    CostRecord,
    Recurrence,
    Variability,
    allocate,
    unallocated,
)
from .economics import (
    DeliverableEconomics,
    DeliverableOutcome,
    FormatComparison,
    FormatEconomics,
    OutcomeCounts,
    ProfitabilitySummary,
    ai_cost_efficiency,
    compare_formats,
    deliverable_economics,
    format_economics,
    profitability,
    research_cost_efficiency,
)
from .errors import (
    CurrencyMismatch,
    EvidenceRequired,
    FinanceError,
    FinanceIntegrityError,
    LedgerViolation,
    SpendAuthorityViolation,
)
from .integrity import assert_integrity, check_integrity
from .investment import (
    Basis as InvestmentBasis,
    BreakEvenResult,
    InvestmentEconomics,
    InvestmentStatus,
    ReusableInvestment,
    ReuseEvent,
    break_even,
    break_even_from_investment,
    investment_economics,
)
from .labour import LABOUR_UNITS, LabourRate
from .mapping import (
    MeasureSource,
    PricedUsage,
    PricedUsageSet,
    ResourceCostMapping,
    mappings_from_research_resource,
    mappings_from_usage,
    price_all,
)
from .money import DEFAULT_QUANTUM, Money, assert_currency, total
from .period import FinancialPeriod, assert_comparable, same_period
from .proposals import (
    PAID_SPEND_RESERVED_ACTION,
    ResolvedProposal,
    SpendDecision,
    SpendPolicy,
    SpendProposal,
    SpendStatus,
    reserved_actions_for_spend,
    resolve,
    unreserved_action,
)
from .rates import (
    UNIT_EQUIVALENCE,
    CostRate,
    RateCard,
    RateUnit,
    UnpricedReason,
    supersede,
)
from .recommendations import (
    ORG_INTELLIGENCE_EQUIVALENT,
    FinancialRecommendation,
    FinancialRecommendationType,
)
from .revenue import (
    ACCOUNTED_EVIDENCE_KINDS,
    PUBLIC_EVIDENCE_KINDS,
    Basis as RevenueBasis,
    EvidenceOrigin,
    RevenueCategory,
    RevenueRecord,
    basis_mix,
)
from .store import FinanceStore, FinanceStoreError

__all__ = [
    # money and periods
    "Money",
    "DEFAULT_QUANTUM",
    "assert_currency",
    "total",
    "FinancialPeriod",
    "same_period",
    "assert_comparable",
    # subjects
    "SubjectKind",
    "SubjectRef",
    "AUTOMATIC_MARKERS",
    # costs
    "CostRecord",
    "CostAdjustment",
    "CostCategory",
    "Recurrence",
    "Variability",
    "Attribution",
    "AllocationMethod",
    "AllocationShare",
    "AdjustmentKind",
    "PAID_EXTERNAL_CATEGORIES",
    "allocate",
    "unallocated",
    # revenue
    "RevenueRecord",
    "RevenueCategory",
    "RevenueBasis",
    "EvidenceOrigin",
    "PUBLIC_EVIDENCE_KINDS",
    "ACCOUNTED_EVIDENCE_KINDS",
    "basis_mix",
    # rates and mapping
    "CostRate",
    "RateCard",
    "RateUnit",
    "UnpricedReason",
    "UNIT_EQUIVALENCE",
    "supersede",
    "LabourRate",
    "LABOUR_UNITS",
    "ResourceCostMapping",
    "MeasureSource",
    "PricedUsage",
    "PricedUsageSet",
    "price_all",
    "mappings_from_usage",
    "mappings_from_research_resource",
    # budgets
    "BudgetLine",
    "BudgetConsumption",
    "ConsumptionState",
    "LimitKind",
    "consumption",
    # economics
    "DeliverableEconomics",
    "DeliverableOutcome",
    "OutcomeCounts",
    "deliverable_economics",
    "FormatEconomics",
    "FormatComparison",
    "format_economics",
    "compare_formats",
    "ProfitabilitySummary",
    "profitability",
    "ai_cost_efficiency",
    "research_cost_efficiency",
    # investment
    "ReusableInvestment",
    "ReuseEvent",
    "InvestmentStatus",
    "InvestmentEconomics",
    "InvestmentBasis",
    "investment_economics",
    "BreakEvenResult",
    "break_even",
    "break_even_from_investment",
    # governance
    "SpendProposal",
    "SpendDecision",
    "SpendPolicy",
    "SpendStatus",
    "ResolvedProposal",
    "resolve",
    "reserved_actions_for_spend",
    "unreserved_action",
    "PAID_SPEND_RESERVED_ACTION",
    "FinancialRecommendation",
    "FinancialRecommendationType",
    "ORG_INTELLIGENCE_EQUIVALENT",
    # store and integrity
    "FinanceStore",
    "FinanceStoreError",
    "check_integrity",
    "assert_integrity",
    # errors
    "FinanceError",
    "CurrencyMismatch",
    "EvidenceRequired",
    "LedgerViolation",
    "SpendAuthorityViolation",
    "FinanceIntegrityError",
]
