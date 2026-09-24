"""The finance layer, tested on what it must refuse rather than what it computes.

The arithmetic here is small - additions, one division, a largest-remainder
split. What is not small is the set of wrong numbers this package must never
produce, and that is what most of these tests are about:

    test_a_float_never_becomes_money
    test_a_cost_without_evidence_cannot_be_created
    test_public_view_data_cannot_become_our_revenue
    test_an_unpriced_resource_is_unknown_not_free
    test_unknown_budget_consumption_is_not_zero
    test_margin_is_suppressed_when_an_input_is_missing
    test_a_recurring_paid_spend_is_ceo_reserved
    test_no_global_financial_health_score_field_exists
    test_the_ledger_refuses_a_silent_overwrite

Each names a specific way a financial report can be confidently wrong.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from ai_platform.serde import dumps
from company.finance import (
    AdjustmentKind,
    AllocationMethod,
    AllocationShare,
    Attribution,
    BudgetLine,
    ConsumptionState,
    CostAdjustment,
    CostCategory,
    CostRate,
    CostRecord,
    CurrencyMismatch,
    DeliverableEconomics,
    EvidenceOrigin,
    EvidenceRequired,
    FinanceError,
    FinanceStore,
    FinanceStoreError,
    FinancialPeriod,
    FinancialRecommendation,
    FinancialRecommendationType,
    InvestmentBasis,
    LabourRate,
    LedgerViolation,
    LimitKind,
    MeasureSource,
    Money,
    OutcomeCounts,
    RateCard,
    RateUnit,
    Recurrence,
    ResourceCostMapping,
    RevenueCategory,
    RevenueRecord,
    ReusableInvestment,
    ReuseEvent,
    SpendAuthorityViolation,
    SpendDecision,
    SpendPolicy,
    SpendProposal,
    SpendStatus,
    SubjectKind,
    SubjectRef,
    ai_cost_efficiency,
    allocate,
    assert_integrity,
    break_even,
    break_even_from_investment,
    check_integrity,
    compare_formats,
    consumption,
    deliverable_economics,
    format_economics,
    investment_economics,
    mappings_from_research_resource,
    mappings_from_usage,
    price_all,
    profitability,
    research_cost_efficiency,
    reserved_actions_for_spend,
    resolve,
    supersede,
    unallocated,
    unreserved_action,
)
from company.runtime.config import load_company_config
from knowledge.company_os.records import Alternative, Evidence

# Governed, but not part of the control plane. Restated here rather than
# imported so this required suite keeps its own import surface; every copy is
# pinned against `company.dashboard.builder.EXTERNAL_CAPSULES` in
# `tests/test_company_external_engineering_runner.py`.
EXTERNAL_CAPSULES = {"company-external-engineering-runner"}

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "company" / "finance"
REPO_ROOT = Path(__file__).resolve().parents[1]

TODAY = dt.date(2026, 9, 16)
JAN = dt.date(2026, 1, 15)


# -- fixtures and builders -------------------------------------------------


@pytest.fixture(scope="module")
def config():
    return load_company_config()


@pytest.fixture
def period() -> FinancialPeriod:
    return FinancialPeriod(
        period_id="2026-q1",
        label="2026 Q1",
        start=dt.date(2026, 1, 1),
        end=dt.date(2026, 3, 31),
        currency="EUR",
    )


def an_evidence(kind: str = "invoice", ref: str = "docs/invoices/2026-01.pdf") -> Evidence:
    return Evidence(kind=kind, ref=ref, note="")


def a_video(video_id: str = "race_short_014") -> SubjectRef:
    return SubjectRef(kind=SubjectKind.VIDEO, id=video_id)


def a_cost(**overrides) -> CostRecord:
    base = dict(
        cost_id="cost.001",
        incurred_on=JAN,
        amount=Money("120.00", "EUR"),
        category=CostCategory.RENDER,
        subject=a_video(),
        source="docs/invoices/2026-01.pdf",
        evidence=(an_evidence(),),
        recorded_by="mira",
        recorded_on=JAN,
    )
    base.update(overrides)
    return CostRecord(**base)


def a_revenue(**overrides) -> RevenueRecord:
    base = dict(
        revenue_id="rev.001",
        received_on=dt.date(2026, 2, 1),
        amount=Money("310.00", "EUR"),
        category=RevenueCategory.YOUTUBE_AD_REVENUE,
        subject=a_video(),
        source="youtube-analytics-export-2026-02",
        evidence=(an_evidence("analytics_export", "exports/yt/2026-02.csv"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 2, 2),
    )
    base.update(overrides)
    return RevenueRecord(**base)


def a_rate(**overrides) -> CostRate:
    base = dict(
        rate_id="rate.tokens.2026",
        provider="provider_a",
        category=CostCategory.AI_REASONING,
        unit=RateUnit.MILLION_TOKENS,
        amount=Money("3.00", "EUR"),
        effective_from=dt.date(2026, 1, 1),
        source="docs/pricing/provider_a-2026-01.md",
        evidence=(an_evidence("document", "docs/pricing/provider_a-2026-01.md"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 1, 1),
    )
    base.update(overrides)
    return CostRate(**base)


def a_proposal(**overrides) -> SpendProposal:
    base = dict(
        proposal_id="spend.001",
        service="provider_a_api",
        purpose="Price the research screening pass against a provider we already use.",
        category=CostCategory.API,
        recurrence=Recurrence.RECURRING,
        estimated_amount=Money("40.00", "EUR"),
        period="monthly",
        expected_benefit="Removes roughly two hours of manual screening per batch.",
        break_even_condition="Two batches a month at the measured manual minute rate.",
        kill_condition="Fewer than two batches a month for two consecutive months.",
        evidence=(an_evidence("document", "docs/research/screening-load.md"),),
        proposed_by="mira",
        proposed_on=JAN,
        alternatives=(Alternative(option="Keep screening manually", why_not="Costs more hours than it saves."),),
    )
    base.update(overrides)
    return SpendProposal(**base)


class FakeUsageRecord:
    """The attribute surface `mappings_from_usage` documents, and nothing else."""

    def __init__(self, **kwargs):
        self.task_id = kwargs.get("task_id", "task-014")
        self.input_units = kwargs.get("input_units", 200_000)
        self.output_units = kwargs.get("output_units", 40_000)
        self.usage_unit = kwargs.get("usage_unit", "token")
        self.tool_calls = kwargs.get("tool_calls", 20)
        self.duration_s = kwargs.get("duration_s", 91.5)
        self.outcome = kwargs.get("outcome", "accepted")
        self.reasoning_class = kwargs.get("reasoning_class", "deep")


class FakeResearchResource:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", "rr-001")
        self.batch_id = kwargs.get("batch_id", "batch-2026-01")
        self.tier = kwargs.get("tier", "screening")
        self.manual_minutes = kwargs.get("manual_minutes", 120)
        self.reasoning_units = kwargs.get("reasoning_units", 90_000)
        self.usage_unit = kwargs.get("usage_unit", "token")
        self.tool_calls = kwargs.get("tool_calls", 12)
        self.search_calls = kwargs.get("search_calls", 30)
        self.recorded_on = kwargs.get("recorded_on", JAN)


# --------------------------------------------------------------------------
# Money: exact, currency-bound, and impossible to build from a float
# --------------------------------------------------------------------------


def test_money_arithmetic_is_decimal_exact():
    """The failure float money has: a tenth plus two tenths."""
    tenth = Money("0.1", "EUR")
    assert tenth + Money("0.2", "EUR") == Money("0.3", "EUR")
    hundred_cents = Money("0.01", "EUR")
    running = Money.zero("EUR")
    for _ in range(100):
        running = running + hundred_cents
    assert running == Money("1", "EUR")
    assert running.amount == Decimal("1")


def test_a_float_never_becomes_money():
    with pytest.raises(FinanceError, match="float"):
        Money(0.1, "EUR")
    with pytest.raises(FinanceError, match="float"):
        Money("1", "EUR") * 1.5
    assert Money("1", "EUR") * Decimal("1.5") == Money("1.5", "EUR")


def test_mixed_currencies_are_refused_in_every_binary_operation():
    euros, dollars = Money("10", "EUR"), Money("10", "USD")
    for operation in (
        lambda: euros + dollars,
        lambda: euros - dollars,
        lambda: euros < dollars,
        lambda: euros.ratio_to(dollars),
    ):
        with pytest.raises(CurrencyMismatch):
            operation()


def test_a_currency_is_a_code_not_a_name_or_a_symbol():
    for bad in ("euros", "eur", "E", "", None, 12):
        with pytest.raises(FinanceError, match="currency code"):
            Money("1", bad)


def test_equal_amounts_have_one_serialization():
    """Trailing zeros and exponent notation are two spellings of one value."""
    assert Money("100.00", "EUR") == Money("1E+2", "EUR") == Money(100, "EUR")
    assert Money("100.00", "EUR").text == "100"
    assert Money("1E+2", "EUR").to_dict() == {"amount": "100", "currency": "EUR"}
    assert Money("0.000003", "EUR").text == "0.000003"


def test_a_split_sums_back_to_exactly_the_original():
    """Twenty euros over three projects is not 6.67 three times."""
    parts = Money("20.00", "EUR").split([1, 1, 1])
    assert parts == (Money("6.67", "EUR"), Money("6.67", "EUR"), Money("6.66", "EUR"))
    assert sum((part.amount for part in parts), Decimal(0)) == Decimal("20")
    weighted = Money("100.00", "EUR").split([5, 3, 2])
    assert sum((part.amount for part in weighted), Decimal(0)) == Decimal("100")
    assert Money("20.00", "EUR").split([1, 1, 1]) == parts  # deterministic


def test_a_split_is_exact_for_a_negative_total_too():
    """A credit distributed across projects must not gain or lose a cent either."""
    parts = Money("-20.00", "EUR").split([1, 1, 1])
    assert sum((part.amount for part in parts), Decimal(0)) == Decimal("-20")
    odd = Money("-0.05", "EUR").split([1, 1, 1])
    assert sum((part.amount for part in odd), Decimal(0)) == Decimal("-0.05")


def test_a_split_with_no_basis_is_refused():
    with pytest.raises(FinanceError, match="unallocated"):
        Money("20", "EUR").split([0, 0])
    with pytest.raises(FinanceError, match="at least one weight"):
        Money("20", "EUR").split([])


def test_money_times_money_has_no_meaning():
    with pytest.raises(FinanceError, match="no meaning"):
        Money("2", "EUR") * Money("3", "EUR")


# --------------------------------------------------------------------------
# Periods
# --------------------------------------------------------------------------


def test_a_period_that_runs_backwards_cannot_exist(period):
    with pytest.raises(FinanceError, match="runs backwards"):
        FinancialPeriod(
            period_id="bad",
            label="Backwards",
            start=dt.date(2026, 3, 31),
            end=dt.date(2026, 1, 1),
            currency="EUR",
        )
    assert period.days == 90
    assert period.contains(JAN) and not period.contains(dt.date(2026, 4, 1))


def test_a_period_refuses_an_amount_in_another_currency(period):
    with pytest.raises(FinanceError, match="does not match the reporting currency"):
        period.assert_currency_matches(Money("10", "USD"), "cost")


# --------------------------------------------------------------------------
# Cost records
# --------------------------------------------------------------------------


def test_a_cost_without_evidence_cannot_be_created():
    with pytest.raises(EvidenceRequired, match="somebody remembered"):
        a_cost(evidence=())


def test_a_cost_is_never_negative():
    with pytest.raises(FinanceError, match="CostAdjustment"):
        a_cost(amount=Money("-5", "EUR"))


def test_a_recurring_cost_must_name_what_recurs():
    with pytest.raises(FinanceError, match="must name its period"):
        a_cost(recurrence=Recurrence.RECURRING)
    assert a_cost(recurrence=Recurrence.RECURRING, recurrence_period="monthly")


def test_an_allocated_cost_carries_its_rule_and_a_direct_one_may_not():
    with pytest.raises(FinanceError, match="must name the rule"):
        a_cost(attribution=Attribution.ALLOCATED, parent_cost_id="cost.000")
    with pytest.raises(FinanceError, match="for allocated costs"):
        a_cost(allocation_method=AllocationMethod.EQUAL)


def test_allocation_is_transparent_and_exact():
    shared = a_cost(
        cost_id="cost.sub",
        amount=Money("20.00", "EUR"),
        category=CostCategory.SOFTWARE_SERVICE,
        subject=SubjectRef(kind=SubjectKind.COMPANY, id="simulation_factory"),
        recurrence=Recurrence.RECURRING,
        recurrence_period="monthly",
    )
    shares = tuple(
        AllocationShare(subject=SubjectRef(kind=SubjectKind.PROJECT, id=name))
        for name in ("race_shorts", "fight_shorts", "website", "research")
    )
    parts = allocate(shared, shares, AllocationMethod.EQUAL, basis="one share per project")
    assert len(parts) == 4
    assert sum((part.amount.amount for part in parts), Decimal(0)) == Decimal("20")
    for part in parts:
        assert part.attribution is Attribution.ALLOCATED
        assert part.allocation_method is AllocationMethod.EQUAL
        assert part.allocation_basis == "one share per project"
        assert part.parent_cost_id == "cost.sub"


def test_usage_based_allocation_records_the_weights_it_used():
    shared = a_cost(cost_id="cost.sub", amount=Money("100.00", "EUR"))
    shares = (
        AllocationShare(SubjectRef(SubjectKind.PROJECT, "a"), weight=7, basis="7 renders"),
        AllocationShare(SubjectRef(SubjectKind.PROJECT, "b"), weight=3, basis="3 renders"),
    )
    parts = allocate(shared, shares, AllocationMethod.USAGE_BASED, basis="renders run")
    assert [part.amount for part in parts] == [Money("70", "EUR"), Money("30", "EUR")]
    assert [part.allocation_basis for part in parts] == ["7 renders", "3 renders"]


def test_a_shared_cost_with_no_known_consumers_stays_unallocated():
    shared = a_cost(cost_id="cost.sub", amount=Money("20.00", "EUR"))
    with pytest.raises(FinanceError, match="stays unallocated"):
        allocate(shared, (), AllocationMethod.EQUAL, basis="equal")
    with pytest.raises(FinanceError, match="needs a real method"):
        allocate(
            shared,
            (AllocationShare(SubjectRef(SubjectKind.PROJECT, "a")),),
            AllocationMethod.NONE,
            basis="equal",
        )
    left = unallocated(shared, "nobody has recorded which projects use it")
    assert left.attribution is Attribution.UNALLOCATED
    assert left.allocation_method is AllocationMethod.NONE
    assert "unallocated: nobody has recorded" in left.notes


def test_a_correction_is_a_new_record_and_the_original_is_untouched():
    original = a_cost(amount=Money("50.00", "EUR"))
    credit = CostAdjustment(
        adjustment_id="adj.001",
        cost_id=original.cost_id,
        adjusted_on=dt.date(2026, 2, 1),
        amount=Money("12.00", "EUR"),
        adjustment_kind=AdjustmentKind.CREDIT,
        reason="Provider refunded the failed render batch.",
        evidence=(an_evidence("payment_statement", "docs/refunds/2026-02.pdf"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 2, 1),
    )
    assert credit.signed_amount == Money("-12", "EUR")
    assert original.amount == Money("50.00", "EUR")
    with pytest.raises(FinanceError, match="two minus signs"):
        CostAdjustment(
            adjustment_id="adj.002",
            cost_id=original.cost_id,
            adjusted_on=dt.date(2026, 2, 1),
            amount=Money("-12.00", "EUR"),
            adjustment_kind=AdjustmentKind.CREDIT,
            reason="Refund.",
            evidence=(an_evidence(),),
            recorded_by="mira",
            recorded_on=dt.date(2026, 2, 1),
        )


# --------------------------------------------------------------------------
# Revenue: ours only, and never inferred
# --------------------------------------------------------------------------


def test_revenue_requires_evidence():
    with pytest.raises(EvidenceRequired, match="read off a statement"):
        a_revenue(evidence=())


def test_public_view_data_cannot_become_our_revenue():
    """Section 4: never infer YouTube revenue from public views."""
    for kind in ("public_view_count", "public_estimate", "third_party_estimate", "scraped"):
        with pytest.raises(FinanceError, match="public or third-party"):
            a_revenue(evidence=(an_evidence(kind, "https://example.invalid/video"),))


def test_competitor_data_cannot_become_our_revenue():
    with pytest.raises(FinanceError, match="competitor data never becomes our revenue"):
        a_revenue(
            evidence=(an_evidence("competitor_observation", "research/ref-0012"),)
        )
    # And there is no way to even name a competitor as a revenue subject.
    assert not any(member.value == "competitor" for member in SubjectKind)


def test_revenue_needs_an_accounted_evidence_kind():
    with pytest.raises(FinanceError, match="accounted kind"):
        a_revenue(evidence=(an_evidence("document", "docs/notes.md"),))
    assert a_revenue(evidence=(an_evidence("payment_statement", "docs/pay/1.pdf"),))


def test_revenue_origin_has_no_public_member():
    assert {member.value for member in EvidenceOrigin} == {
        "own_authenticated",
        "own_supplied",
    }


def test_revenue_credited_to_an_external_reference_is_an_integrity_failure():
    theirs = a_revenue(
        revenue_id="rev.bad", subject=SubjectRef(SubjectKind.VIDEO, "ref_0012")
    )
    problems = check_integrity(
        revenue=(theirs,), external_reference_ids=("ref_0012",)
    )
    assert any("somebody else's video is never our revenue" in item for item in problems)


# --------------------------------------------------------------------------
# Rates: dated, never overwritten, never guessed
# --------------------------------------------------------------------------


def test_a_rate_is_refused_outside_its_effective_dates():
    rate = a_rate(effective_from=dt.date(2026, 1, 1), effective_to=dt.date(2026, 3, 31))
    assert rate.covers(JAN) and not rate.covers(dt.date(2026, 4, 1))
    with pytest.raises(FinanceError, match="restates history"):
        rate.price(1, on=dt.date(2026, 4, 1))


def test_rate_history_is_preserved_when_a_price_changes():
    january = a_rate(rate_id="rate.jan", amount=Money("3.00", "EUR"))
    april_draft = a_rate(
        rate_id="rate.apr",
        amount=Money("4.50", "EUR"),
        effective_from=dt.date(2026, 4, 1),
    )
    closed, opened = supersede(january, april_draft, last_day=dt.date(2026, 3, 31))
    card = RateCard((closed, opened))
    assert january.effective_to is None  # the original value is untouched
    assert closed.effective_to == dt.date(2026, 3, 31)
    assert opened.effective_from == dt.date(2026, 4, 1)
    assert opened.supersedes == "rate.jan"
    assert card.rate_for("provider_a", RateUnit.MILLION_TOKENS, on=JAN).amount == Money(
        "3.00", "EUR"
    )
    assert card.rate_for(
        "provider_a", RateUnit.MILLION_TOKENS, on=dt.date(2026, 5, 1)
    ).amount == Money("4.50", "EUR")
    assert len(card.history("provider_a", RateUnit.MILLION_TOKENS, CostCategory.AI_REASONING)) == 2


def test_two_prices_for_one_day_is_reported_not_resolved():
    left = a_rate(rate_id="rate.a")
    right = a_rate(rate_id="rate.b", amount=Money("5.00", "EUR"))
    card = RateCard((left, right))
    assert card.overlaps()
    with pytest.raises(FinanceError, match="not a tie this code may break"):
        card.rate_for("provider_a", RateUnit.MILLION_TOKENS, on=JAN)
    assert any("overlapping dates" in item for item in check_integrity(rates=(left, right)))


def test_a_rate_needs_a_source():
    with pytest.raises(EvidenceRequired, match="somebody recalled"):
        a_rate(evidence=())


def test_no_provider_price_is_hardcoded_in_the_package():
    """Section 5: pricing must be data, never a constant somebody typed in 2026.

    Scans for a `Money` built from a literal amount anywhere outside `money.py`,
    which is the type's own module. `Money.zero(currency)` is fine - a zero is
    not a price - and so is `Money(computed, currency)`. What this catches is
    `Money("3.00", "EUR")` appearing beside a provider name, which is how a
    price stops being data.
    """
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        if path.name == "money.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if getattr(node.func, "id", None) != "Money" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and first.value not in (0, "0"):
                pytest.fail(
                    f"{path.name} builds Money({first.value!r}); a price is a CostRate "
                    "record somebody supplied, not a literal in this package"
                )


# --------------------------------------------------------------------------
# Usage to cost: only with an explicit rate
# --------------------------------------------------------------------------


def test_usage_becomes_cost_only_with_a_supplied_rate():
    mappings = mappings_from_usage(
        FakeUsageRecord(),
        subject=a_video(),
        provider="provider_a",
        measured_on=JAN,
        id_prefix="map.task014",
    )
    by_id = {mapping.mapping_id: mapping for mapping in mappings}
    assert set(by_id) == {
        "map.task014.input_units",
        "map.task014.output_units",
        "map.task014.tool_calls",
    }
    card = RateCard((a_rate(),))
    priced = by_id["map.task014.input_units"].price(card)
    assert priced.is_priced
    assert priced.amount == Money("0.6", "EUR")  # 200k tokens at 3.00/M
    assert priced.rate_id == "rate.tokens.2026"


def test_an_unpriced_resource_is_unknown_not_free():
    """The single most expensive wrong number: an unpriced provider looking free."""
    mappings = mappings_from_usage(
        FakeUsageRecord(),
        subject=a_video(),
        provider="provider_without_a_price",
        measured_on=JAN,
        id_prefix="map.x",
    )
    result = price_all(mappings, RateCard((a_rate(),)), currency="EUR")
    assert not result.is_complete
    assert result.total == Money("0", "EUR")  # a floor, and is_complete says so
    assert len(result.unpriced) == 3
    assert all("no rate for provider_without_a_price" in item for item in result.missing)
    for item in result.unpriced:
        assert item.amount is None
        assert item.unpriced_reason is not None


def test_a_priced_usage_cannot_hold_both_an_amount_and_a_reason():
    mapping = ResourceCostMapping(
        mapping_id="map.1",
        resource_ref="task-014",
        measure="tokens",
        quantity=1000,
        unit=RateUnit.TOKEN,
        provider="provider_a",
        category=CostCategory.AI_REASONING,
        subject=a_video(),
        measured_on=JAN,
        measure_source=MeasureSource.USAGE_RECORD,
    )
    from company.finance.mapping import PricedUsage

    with pytest.raises(FinanceError, match="exactly one"):
        PricedUsage(
            mapping=mapping, amount=Money("1", "EUR"), rate_id="r", priced_on=JAN,
            unpriced_reason=None,
        ).__class__(
            mapping=mapping, amount=None, rate_id="", priced_on=JAN, unpriced_reason=None
        )


def test_a_character_count_is_not_priced_per_token():
    mappings = mappings_from_usage(
        FakeUsageRecord(usage_unit="character"),
        subject=a_video(),
        provider="provider_a",
        measured_on=JAN,
        id_prefix="map.c",
    )
    assert [m.unit for m in mappings] == [RateUnit.REQUEST]  # only tool calls survive


def test_a_measure_the_provider_did_not_expose_produces_no_mapping():
    mappings = mappings_from_usage(
        FakeUsageRecord(input_units=None, output_units=None, tool_calls=None),
        subject=a_video(),
        provider="provider_a",
        measured_on=JAN,
        id_prefix="map.none",
    )
    assert mappings == ()


def test_a_renamed_usage_attribute_fails_loudly():
    class Renamed:
        task_id = "t"
        input_tokens = 10  # the rename

    with pytest.raises(FinanceError, match="must expose"):
        mappings_from_usage(
            Renamed(), subject=a_video(), provider="p", measured_on=JAN, id_prefix="m"
        )


def test_research_resource_records_become_priceable_quantities():
    mappings = mappings_from_research_resource(
        FakeResearchResource(),
        subject=SubjectRef(SubjectKind.PROJECT, "research"),
        provider="provider_a",
        id_prefix="map.rr",
        labour_provider="role:researcher",
    )
    units = {mapping.mapping_id: mapping.unit for mapping in mappings}
    assert units == {
        "map.rr.reasoning_units": RateUnit.TOKEN,
        "map.rr.tool_calls": RateUnit.REQUEST,
        "map.rr.search_calls": RateUnit.REQUEST,
        "map.rr.manual_minutes": RateUnit.MINUTE,
    }
    labour = next(m for m in mappings if m.mapping_id == "map.rr.manual_minutes")
    assert labour.category is CostCategory.EMPLOYEE_TIME
    assert labour.provider == "role:researcher"


def test_manual_minutes_are_never_priced_at_the_ai_providers_rate():
    with pytest.raises(FinanceError, match="not billed at the AI provider"):
        mappings_from_research_resource(
            FakeResearchResource(),
            subject=SubjectRef(SubjectKind.PROJECT, "research"),
            provider="provider_a",
            id_prefix="map.rr",
        )


def test_research_cost_efficiency_uses_supplied_counts_only(period):
    view = research_cost_efficiency(
        period, Money("60.00", "EUR"), unique_candidates=120, screened_in=30
    )
    assert view["cost_per_unique_candidate"] == Money("0.5", "EUR")
    assert view["cost_per_screened_in_candidate"] == Money("2", "EUR")
    assert view["cost_per_promoted_source"] is None
    assert "promoted_sources" in view["unknown"]
    unpriced = research_cost_efficiency(period, None, unique_candidates=120)
    assert unpriced["cost_per_unique_candidate"] is None


# --------------------------------------------------------------------------
# Labour
# --------------------------------------------------------------------------


def test_a_labour_rate_needs_evidence_and_is_never_guessed():
    with pytest.raises(EvidenceRequired, match="section 21"):
        LabourRate(
            rate_id="lab.1",
            subject=SubjectRef(SubjectKind.DEPARTMENT, "research"),
            amount=Money("45.00", "EUR"),
            unit=RateUnit.HOUR,
            effective_from=JAN,
            source="docs/hr/rates.md",
            evidence=(),
            recorded_by="mira",
            recorded_on=JAN,
        )


def test_time_is_priced_per_unit_of_time():
    with pytest.raises(FinanceError, match="MINUTE or HOUR"):
        LabourRate(
            rate_id="lab.1",
            subject=SubjectRef(SubjectKind.DEPARTMENT, "research"),
            amount=Money("45.00", "EUR"),
            unit=RateUnit.TOKEN,
            effective_from=JAN,
            source="docs/hr/rates.md",
            evidence=(an_evidence("document", "docs/hr/rates.md"),),
            recorded_by="mira",
            recorded_on=JAN,
        )


def test_labour_minutes_price_against_an_hourly_rate():
    rate = LabourRate(
        rate_id="lab.researcher",
        subject=SubjectRef(SubjectKind.DEPARTMENT, "research"),
        amount=Money("60.00", "EUR"),
        unit=RateUnit.HOUR,
        effective_from=dt.date(2026, 1, 1),
        source="docs/hr/rates.md",
        evidence=(an_evidence("document", "docs/hr/rates.md"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 1, 1),
    )
    card = RateCard((rate.as_cost_rate(),))
    mapping = ResourceCostMapping(
        mapping_id="map.minutes",
        resource_ref="rr-001",
        measure="manual minutes",
        quantity=120,
        unit=RateUnit.MINUTE,
        provider="department:research",
        category=CostCategory.EMPLOYEE_TIME,
        subject=SubjectRef(SubjectKind.PROJECT, "research"),
        measured_on=JAN,
    )
    assert mapping.price(card).amount == Money("120", "EUR")  # 2 hours at 60/hour


# --------------------------------------------------------------------------
# Budgets
# --------------------------------------------------------------------------


def a_budget(period: FinancialPeriod, **overrides) -> BudgetLine:
    base = dict(
        budget_id="budget.render.q1",
        period=period,
        scope=a_video(),
        amount=Money("500.00", "EUR"),
        owner="mira",
        evidence=(an_evidence("document", "docs/budgets/2026-q1.md"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 1, 1),
        limit_kind=LimitKind.SOFT,
    )
    base.update(overrides)
    return BudgetLine(**base)


def test_budget_consumption_is_deterministic(period):
    budget = a_budget(period)
    costs = (a_cost(cost_id="c.1", amount=Money("120.00", "EUR")),
             a_cost(cost_id="c.2", amount=Money("80.00", "EUR")))
    result = consumption(budget, costs, costs_are_complete=True)
    assert result.actual == Money("200", "EUR")
    assert result.remaining == Money("300", "EUR")
    assert result.fraction_consumed == Decimal("0.4")
    assert result.state is ConsumptionState.UNDER
    assert result.counted_costs == 2


def test_unknown_budget_consumption_is_not_zero(period):
    """Section 15: unknown actual cost means unknown, not nothing spent."""
    result = consumption(a_budget(period), ())
    assert result.state is ConsumptionState.UNKNOWN
    assert result.actual is None
    assert result.remaining is None
    assert result.fraction_consumed is None
    assert not result.is_known
    assert not result.is_over  # unknown is not "under"
    assert any("unknown rather than" in item for item in result.missing)


def test_budget_consumption_refuses_to_convert_a_currency(period):
    with pytest.raises(FinanceError, match="[Nn]othing here converts"):
        consumption(
            a_budget(period),
            (a_cost(amount=Money("100", "USD")),),
            costs_are_complete=True,
        )


def test_a_cost_outside_the_budget_scope_is_listed_not_counted(period):
    other = a_cost(cost_id="c.other", subject=SubjectRef(SubjectKind.PROJECT, "website"))
    result = consumption(a_budget(period), (other,), costs_are_complete=True)
    assert result.actual == Money("0", "EUR")
    assert result.counted_costs == 0
    assert len(result.out_of_scope) == 1


def test_going_over_a_budget_is_reported(period):
    result = consumption(
        a_budget(period),
        (a_cost(amount=Money("600.00", "EUR")),),
        costs_are_complete=True,
    )
    assert result.state is ConsumptionState.OVER
    assert result.is_over
    assert result.remaining == Money("-100", "EUR")


# --------------------------------------------------------------------------
# Deliverable and format economics
# --------------------------------------------------------------------------


def test_direct_allocated_and_total_cost_are_separate(period):
    shared = a_cost(
        cost_id="cost.sub",
        amount=Money("20.00", "EUR"),
        subject=SubjectRef(SubjectKind.COMPANY, "simulation_factory"),
        category=CostCategory.SOFTWARE_SERVICE,
    )
    share = allocate(
        shared,
        (AllocationShare(a_video()), AllocationShare(SubjectRef(SubjectKind.VIDEO, "other"))),
        AllocationMethod.EQUAL,
        basis="one share each",
    )[0]
    summary = deliverable_economics(
        a_video(),
        period,
        costs=(a_cost(cost_id="c.direct", amount=Money("120.00", "EUR")), share),
        revenue=(a_revenue(),),
        outcomes=OutcomeCounts(accepted=1),
        costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert summary.direct_cost == Money("120", "EUR")
    assert summary.allocated_cost == Money("10", "EUR")
    assert summary.total_cost == Money("130", "EUR")
    assert summary.gross_revenue == Money("310", "EUR")
    assert summary.net_contribution == Money("180", "EUR")


def test_known_revenue_and_contribution_with_margin(period):
    summary = deliverable_economics(
        a_video(),
        period,
        costs=(a_cost(amount=Money("100.00", "EUR")),),
        revenue=(a_revenue(amount=Money("400.00", "EUR")),),
        costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert summary.net_contribution == Money("300", "EUR")
    assert summary.gross_margin == Decimal("0.75")
    assert summary.missing == ()


def test_margin_is_suppressed_when_an_input_is_missing(period):
    """Section 8: never report margin when required inputs are missing."""
    incomplete = deliverable_economics(
        a_video(),
        period,
        costs=(a_cost(),),
        revenue=(a_revenue(),),
        costs_are_complete=False,  # nobody asserted the costs are all in
        revenue_is_complete=True,
    )
    assert incomplete.gross_margin is None
    assert incomplete.net_contribution is None
    assert incomplete.missing

    no_revenue = deliverable_economics(
        a_video(), period, costs=(a_cost(),), costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert no_revenue.gross_margin is None
    assert any("no revenue recorded" in item for item in no_revenue.missing)


def test_an_adjustment_nets_against_the_cost_it_corrects(period):
    cost = a_cost(amount=Money("50.00", "EUR"))
    credit = CostAdjustment(
        adjustment_id="adj.1",
        cost_id=cost.cost_id,
        adjusted_on=dt.date(2026, 2, 1),
        amount=Money("12.00", "EUR"),
        adjustment_kind=AdjustmentKind.CREDIT,
        reason="Refund for the failed batch.",
        evidence=(an_evidence("payment_statement", "docs/refunds/1.pdf"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 2, 1),
    )
    summary = deliverable_economics(
        a_video(), period, costs=(cost,), adjustments=(credit,),
        revenue=(a_revenue(),), costs_are_complete=True, revenue_is_complete=True,
    )
    assert summary.adjustments == Money("-12", "EUR")
    assert summary.total_cost == Money("38", "EUR")


def test_failed_and_rejected_attempts_stay_in_the_totals(period):
    """Section 18: cost of learning is only honest if failures are counted."""
    costs = (
        a_cost(cost_id="c.accepted", amount=Money("100.00", "EUR")),
        a_cost(cost_id="c.rejected", amount=Money("60.00", "EUR")),
        a_cost(cost_id="c.abandoned", amount=Money("40.00", "EUR")),
    )
    summary = deliverable_economics(
        a_video(),
        period,
        costs=costs,
        revenue=(a_revenue(),),
        outcomes=OutcomeCounts(accepted=1, rejected=1, abandoned=1),
        costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert summary.total_cost == Money("200", "EUR")
    assert summary.outcomes.attempted == 3
    assert summary.cost_per_accepted_deliverable == Money("200", "EUR")


def test_cost_per_accepted_deliverable_needs_both_inputs(period):
    no_counts = deliverable_economics(
        a_video(), period, costs=(a_cost(),), revenue=(a_revenue(),),
        costs_are_complete=True, revenue_is_complete=True,
    )
    assert no_counts.cost_per_accepted_deliverable is None
    none_accepted = deliverable_economics(
        a_video(), period, costs=(a_cost(),), revenue=(a_revenue(),),
        outcomes=OutcomeCounts(rejected=3), costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert none_accepted.cost_per_accepted_deliverable is None


def test_a_mixed_gross_and_net_revenue_set_is_flagged(period):
    from company.finance import RevenueBasis

    summary = deliverable_economics(
        a_video(),
        period,
        costs=(a_cost(),),
        revenue=(
            a_revenue(revenue_id="r.1", basis=RevenueBasis.GROSS),
            a_revenue(revenue_id="r.2", basis=RevenueBasis.NET),
        ),
        costs_are_complete=True,
        revenue_is_complete=True,
    )
    assert summary.revenue_basis == ("gross", "net")
    assert any("ambiguous" in item for item in summary.caveats)


def a_summary(period, video_id, cost, revenue) -> DeliverableEconomics:
    return deliverable_economics(
        SubjectRef(SubjectKind.VIDEO, video_id),
        period,
        costs=(a_cost(cost_id=f"c.{video_id}", amount=cost,
                      subject=SubjectRef(SubjectKind.VIDEO, video_id)),),
        revenue=(a_revenue(revenue_id=f"r.{video_id}", amount=revenue,
                           subject=SubjectRef(SubjectKind.VIDEO, video_id)),),
        outcomes=OutcomeCounts(accepted=1),
        costs_are_complete=True,
        revenue_is_complete=True,
    )


def test_format_economics_carries_its_sample_size(period):
    summary = format_economics(
        "race_shorts",
        period,
        video_summaries=(
            a_summary(period, "v1", Money("100", "EUR"), Money("300", "EUR")),
            a_summary(period, "v2", Money("120", "EUR"), Money("260", "EUR")),
        ),
        experiment_cost=Money("50", "EUR"),
        failed_prototype_cost=Money("30", "EUR"),
    )
    assert summary.videos_produced == 2
    assert summary.sample_size == 2
    assert summary.total_cost == Money("300", "EUR")  # 220 + 50 + 30
    assert summary.total_revenue == Money("560", "EUR")
    assert summary.contribution == Money("260", "EUR")
    assert summary.average_cost_per_video == Money("150", "EUR")


def test_one_video_cannot_judge_a_format(period):
    """Section 9: do not rank formats from one video's outcome."""
    summary = format_economics(
        "race_shorts",
        period,
        video_summaries=(a_summary(period, "v1", Money("100", "EUR"), Money("900", "EUR")),),
    )
    assert summary.sample_size == 1
    assert any("only about this video" in item for item in summary.caveats)


def test_comparing_formats_below_the_sample_floor_is_refused(period):
    left = format_economics(
        "race_shorts", period,
        video_summaries=(a_summary(period, "v1", Money("100", "EUR"), Money("900", "EUR")),),
    )
    right = format_economics(
        "fight_shorts", period,
        video_summaries=(a_summary(period, "v2", Money("100", "EUR"), Money("100", "EUR")),),
    )
    comparison = compare_formats(left, right, minimum_sample=5)
    assert not comparison.comparable
    assert len(comparison.reasons) == 2
    # And there is no winner to read off it.
    assert not hasattr(comparison, "winner")
    assert not hasattr(comparison, "ranking")


def test_amortization_happens_only_when_explicitly_configured(period):
    summaries = (a_summary(period, "v1", Money("100", "EUR"), Money("300", "EUR")),)
    unconfigured = format_economics(
        "race_shorts", period, video_summaries=summaries,
        reusable_investment_cost=Money("900", "EUR"),
    )
    assert unconfigured.amortized_reusable_cost is None
    assert any("no amortization horizon" in item for item in unconfigured.caveats)
    configured = format_economics(
        "race_shorts", period, video_summaries=summaries,
        reusable_investment_cost=Money("900", "EUR"), amortize_over=30,
    )
    assert configured.amortized_reusable_cost == Money("30", "EUR")
    assert any("explicit configuration" in item for item in configured.caveats)


def test_format_economics_refuses_to_merge_two_periods(period):
    other = FinancialPeriod(
        period_id="2026-q2", label="2026 Q2", start=dt.date(2026, 4, 1),
        end=dt.date(2026, 6, 30), currency="EUR",
    )
    with pytest.raises(FinanceError, match="not merged silently"):
        format_economics(
            "race_shorts", other,
            video_summaries=(a_summary(period, "v1", Money("1", "EUR"), Money("1", "EUR")),),
        )


# --------------------------------------------------------------------------
# Profitability: qualified, never a verdict
# --------------------------------------------------------------------------


def test_profitability_is_stated_over_known_records(period):
    summary = profitability(
        "Race Shorts Q1",
        period,
        (a_summary(period, "v1", Money("100", "EUR"), Money("300", "EUR")),),
    )
    assert summary.known_revenue == Money("300", "EUR")
    assert summary.known_cost == Money("100", "EUR")
    assert summary.observed_contribution == Money("200", "EUR")
    assert summary.sample_size == 1
    assert "observed contribution" in summary.statement()
    assert not hasattr(summary, "is_profitable")


def test_an_incomplete_picture_is_never_called_profitable(period):
    partial = deliverable_economics(
        a_video(), period, costs=(a_cost(),), revenue=(a_revenue(),)
    )
    summary = profitability("Race Shorts Q1", period, (partial,))
    assert not summary.is_complete
    assert "missing" in summary.statement()
    assert "profitable" not in summary.statement().lower()


# --------------------------------------------------------------------------
# AI cost efficiency
# --------------------------------------------------------------------------


def test_ai_cost_is_absent_without_pricing(period):
    """Section 19: do not infer money from token counts without a RateCard."""
    view = ai_cost_efficiency(
        period,
        {"accepted": Money("12.00", "EUR"), "rejected": None, "abandoned": Money("2", "EUR")},
        OutcomeCounts(accepted=4, rejected=2, abandoned=1),
    )
    assert view["total_cost"] is None  # one unknown makes the total unknown
    assert view["cost_per_accepted_task"] is None
    assert view["accepted_cost"] == Money("12.00", "EUR")
    assert view["unknown"] == ("rejected",)


def test_ai_cost_per_accepted_and_rejected_task_when_everything_is_priced(period):
    view = ai_cost_efficiency(
        period,
        {
            "accepted": Money("12.00", "EUR"),
            "rejected": Money("6.00", "EUR"),
            "abandoned": Money("2.00", "EUR"),
        },
        OutcomeCounts(accepted=4, rejected=2, abandoned=1),
    )
    assert view["total_cost"] == Money("20", "EUR")
    assert view["cost_per_accepted_task"] == Money("5", "EUR")
    assert view["cost_per_rejected_task"] == Money("3", "EUR")
    assert view["unknown"] == ()


# --------------------------------------------------------------------------
# Reusable investment and break-even
# --------------------------------------------------------------------------


def an_investment(**overrides) -> ReusableInvestment:
    base = dict(
        investment_id="inv.camera_rig",
        subject=SubjectRef(SubjectKind.TOOL, "chase_camera"),
        cost=Money("900.00", "EUR"),
        created_on=dt.date(2026, 1, 5),
        purpose="A reusable chase-camera rig shared by every race format.",
        evidence=(an_evidence("commit", "ebb70b9"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 1, 5),
    )
    base.update(overrides)
    return ReusableInvestment(**base)


def a_reuse(event_id: str, avoided: Money | None = None) -> ReuseEvent:
    return ReuseEvent(
        event_id=event_id,
        investment_id="inv.camera_rig",
        occurred_on=dt.date(2026, 2, 1),
        used_by=a_video(),
        recorded_by="mira",
        recorded_on=dt.date(2026, 2, 1),
        cost_avoided=avoided,
        measurement_ref="docs/validation/camera-rig-timing.md" if avoided else "",
        evidence=(an_evidence("measurement", "docs/validation/camera-rig-timing.md"),)
        if avoided
        else (),
    )


def test_an_unmeasured_reuse_counts_as_a_reuse_and_saves_nothing():
    """Section 10: do not invent cost saved."""
    economics = investment_economics(
        an_investment(), (a_reuse("e.1"), a_reuse("e.2", Money("200", "EUR"))),
        maintenance_cost=Money("0", "EUR"),
    )
    assert economics.reuse_count == 2
    assert economics.measured_reuse_count == 1
    assert economics.unmeasured_reuse_count == 1
    assert economics.measured_cost_avoided == Money("200", "EUR")
    assert any("recorded no measured cost avoided" in item for item in economics.missing)


def test_a_claimed_saving_needs_a_measurement():
    with pytest.raises(FinanceError, match="measurement_ref"):
        ReuseEvent(
            event_id="e.x",
            investment_id="inv.camera_rig",
            occurred_on=dt.date(2026, 2, 1),
            used_by=a_video(),
            recorded_by="mira",
            recorded_on=dt.date(2026, 2, 1),
            cost_avoided=Money("200", "EUR"),
        )


def test_an_investment_with_no_reuse_is_unmeasured_not_worthless():
    economics = investment_economics(an_investment())
    assert economics.basis is InvestmentBasis.UNKNOWN
    assert not economics.broke_even
    assert any("unmeasured, not zero" in item for item in economics.missing)


def test_break_even_from_measured_reuse_is_labelled_measured():
    economics = investment_economics(
        an_investment(),
        tuple(a_reuse(f"e.{n}", Money("200", "EUR")) for n in range(3)),
        maintenance_cost=Money("0", "EUR"),
    )
    assert economics.measured_cost_avoided == Money("600", "EUR")
    result = break_even_from_investment(economics, FinancialPeriod(
        period_id="2026-q1", label="2026 Q1", start=dt.date(2026, 1, 1),
        end=dt.date(2026, 3, 31), currency="EUR",
    ))
    assert result.basis is InvestmentBasis.MEASURED
    assert not result.is_hypothetical
    assert result.periods_to_break_even == Decimal("4.5")  # 900 / 200
    assert "MEASURED" in result.statement()


def test_break_even_carries_the_investments_own_gaps_into_its_caveats():
    """An unmeasured reuse makes the saving a floor, and the payback optimistic."""
    economics = investment_economics(
        an_investment(),
        (a_reuse("e.1", Money("300", "EUR")), a_reuse("e.2")),  # one unmeasured
    )
    result = break_even_from_investment(
        economics,
        FinancialPeriod(
            period_id="2026-q1", label="2026 Q1", start=dt.date(2026, 1, 1),
            end=dt.date(2026, 3, 31), currency="EUR",
        ),
    )
    assert result.basis is InvestmentBasis.MEASURED
    assert any("recorded no measured cost avoided" in item for item in result.caveats)
    assert any("no maintenance cost supplied" in item for item in result.caveats)


def test_a_hypothetical_break_even_says_so_in_its_own_statement():
    """Section 11: break-even based on hypotheses must be labelled hypothetical."""
    result = break_even(
        "provider_a monthly subscription",
        upfront_cost=Money("0", "EUR"),
        recurring_cost=Money("40.00", "EUR"),
        assumed_saving_per_period=Money("120.00", "EUR"),
        assumptions=("mira estimates two hours saved per batch at the recorded rate",),
        horizon_periods=12,
    )
    assert result.is_hypothetical
    assert "HYPOTHETICAL" in result.statement()
    assert result.net_per_period == Money("80", "EUR")
    assert result.net_over_horizon == Money("960", "EUR")
    assert any("hypothetical until the saving is measured" in c for c in result.caveats)


def test_an_assumption_must_name_who_supplied_it():
    with pytest.raises(FinanceError, match="unattributed hypothesis"):
        break_even(
            "provider_a",
            upfront_cost=Money("0", "EUR"),
            assumed_saving_per_period=Money("120.00", "EUR"),
        )


def test_measured_and_assumed_savings_are_never_blended():
    result = break_even(
        "chase camera rig",
        upfront_cost=Money("900.00", "EUR"),
        measured_saving_per_period=Money("200.00", "EUR"),
        assumed_saving_per_period=Money("500.00", "EUR"),
        assumptions=("mira hopes for 500 once the rig is used on fight shorts",),
    )
    assert result.basis is InvestmentBasis.MEASURED
    assert result.saving_per_period == Money("200.00", "EUR")
    assert any("was supplied and not used" in item for item in result.unused_inputs)


def test_break_even_with_no_saving_is_unknown_not_infinite():
    result = break_even("a tool nobody measured", upfront_cost=Money("900", "EUR"))
    assert result.basis is InvestmentBasis.UNKNOWN
    assert result.periods_to_break_even is None
    assert "cannot be computed" in result.statement()


def test_a_cost_that_never_pays_back_says_so():
    result = break_even(
        "an expensive subscription",
        upfront_cost=Money("100", "EUR"),
        recurring_cost=Money("50.00", "EUR"),
        measured_saving_per_period=Money("20.00", "EUR"),
    )
    assert result.periods_to_break_even is None
    assert any("never recovered" in item for item in result.caveats)


# --------------------------------------------------------------------------
# Spend governance
# --------------------------------------------------------------------------


def test_a_spend_proposal_cannot_execute_anything():
    """Section 12: finance must not pay, subscribe, or change a permission."""
    proposal = a_proposal()
    for forbidden in ("pay", "execute", "subscribe", "approve", "charge", "grant", "purchase"):
        assert not hasattr(proposal, forbidden), f"SpendProposal.{forbidden} exists"
    source = (PACKAGE_ROOT / "proposals.py").read_text(encoding="utf-8")
    for banned in ("import requests", "import urllib", "import http", "subprocess"):
        assert banned not in source


def test_a_proposal_is_born_proposed_and_cannot_approve_itself():
    with pytest.raises(SpendAuthorityViolation, match="born PROPOSED"):
        a_proposal(status=SpendStatus.APPROVED)


def test_a_recurring_paid_spend_is_ceo_reserved(config):
    """permissions.yaml reserves it; this reads that file rather than deciding."""
    actions = reserved_actions_for_spend(
        CostCategory.API,
        Recurrence.RECURRING,
        Money("40.00", "EUR"),
        permissions=config.permissions,
    )
    assert actions == ("large_or_recurring_paid_api_spend",)
    proposal = a_proposal().with_reservation(permissions=config.permissions)
    assert proposal.requires_ceo_approval
    assert proposal.reserved_actions == ("large_or_recurring_paid_api_spend",)


def test_reservation_fails_closed_with_no_permissions():
    assert reserved_actions_for_spend(
        CostCategory.API, Recurrence.RECURRING, Money("1.00", "EUR")
    ) == ("large_or_recurring_paid_api_spend",)
    assert reserved_actions_for_spend(
        CostCategory.API, Recurrence.RECURRING, Money("1.00", "EUR"),
        permissions={"ceo_reserved": []},
    ) == ()


def test_an_absent_threshold_does_not_weaken_the_recurrence_gate(config):
    """Section 13: do not invent what large means; recurrence still reserves."""
    policy = SpendPolicy()
    assert not policy.has_threshold
    assert policy.exceeds_threshold(Money("10000", "EUR")) is None
    assert reserved_actions_for_spend(
        CostCategory.API, Recurrence.RECURRING, Money("1.00", "EUR"),
        policy=policy, permissions=config.permissions,
    ) == ("large_or_recurring_paid_api_spend",)


def test_a_configured_threshold_reserves_a_large_one_time_spend(config):
    policy = SpendPolicy(
        approval_threshold=Money("100.00", "EUR"),
        source="docs/company/spend-policy.md decision of 2026-01-10",
    )
    assert reserved_actions_for_spend(
        CostCategory.API, Recurrence.ONE_TIME, Money("500.00", "EUR"),
        policy=policy, permissions=config.permissions,
    ) == ("large_or_recurring_paid_api_spend",)
    assert reserved_actions_for_spend(
        CostCategory.API, Recurrence.ONE_TIME, Money("5.00", "EUR"),
        policy=policy, permissions=config.permissions,
    ) == ()


def test_a_threshold_without_provenance_is_refused():
    with pytest.raises(FinanceError, match="this package invented"):
        SpendPolicy(approval_threshold=Money("100.00", "EUR"))


def test_reserved_actions_require_the_approval_flag():
    with pytest.raises(SpendAuthorityViolation, match="does not require CEO approval"):
        a_proposal(reserved_actions=("large_or_recurring_paid_api_spend",))


def test_finance_does_not_approve_itself():
    for machine in ("system", "automatic", "finance", "company_os"):
        with pytest.raises(FinanceError, match="not a person"):
            SpendDecision(
                decision_id="dec.1",
                proposal_id="spend.001",
                status=SpendStatus.APPROVED,
                decided_by=machine,
                decided_on=TODAY,
                reason="Approved.",
                evidence=(an_evidence("document", "docs/decisions/1.md"),),
            )


def test_an_approval_by_the_wrong_person_leaves_the_proposal_blocked(config):
    proposal = a_proposal().with_reservation(permissions=config.permissions)
    decision = SpendDecision(
        decision_id="dec.1",
        proposal_id=proposal.proposal_id,
        status=SpendStatus.APPROVED,
        decided_by="mira",
        decided_on=TODAY,
        reason="Looks worth it for the screening load.",
        evidence=(an_evidence("document", "docs/decisions/1.md"),),
        is_ceo=False,
    )
    resolved = resolve(proposal, (decision,))
    assert not resolved.is_approved
    assert any("CEO-reserved" in item for item in resolved.blocked_reasons)

    ceo = SpendDecision(
        decision_id="dec.2",
        proposal_id=proposal.proposal_id,
        status=SpendStatus.APPROVED,
        decided_by="the ceo",
        decided_on=TODAY,
        reason="Approved for one quarter, reviewed in April.",
        evidence=(an_evidence("document", "docs/decisions/2.md"),),
        is_ceo=True,
    )
    assert resolve(proposal, (decision, ceo)).is_approved


def test_a_ceo_approval_needs_decision_evidence(config):
    proposal = a_proposal().with_reservation(permissions=config.permissions)
    with pytest.raises(EvidenceRequired, match="approval nobody can produce"):
        SpendDecision(
            decision_id="dec.3",
            proposal_id=proposal.proposal_id,
            status=SpendStatus.APPROVED,
            decided_by="the ceo",
            decided_on=TODAY,
            reason="Fine.",
            is_ceo=True,
        )


def test_the_shipped_permissions_still_reserve_paid_spend(config):
    """The rename detector: if ceo_reserved drops the action, this fails."""
    assert unreserved_action(config.permissions) == ()
    assert "large_or_recurring_paid_api_spend" in config.permissions["ceo_reserved"]
    assert check_integrity(permissions=config.permissions, external_reference_ids=()) == ()


def test_a_dropped_reservation_is_reported():
    problems = check_integrity(
        permissions={"ceo_reserved": ["publish_public_video"]},
        external_reference_ids=(),
    )
    assert any("does not name large_or_recurring_paid_api_spend" in p for p in problems)


def test_a_proposal_must_name_an_alternative():
    with pytest.raises(FinanceError, match="decision already taken"):
        a_proposal(alternatives=())


# --------------------------------------------------------------------------
# Recommendations: advisory, with handoff
# --------------------------------------------------------------------------


def a_recommendation(**overrides) -> FinancialRecommendation:
    base = dict(
        recommendation_id="fr.001",
        type=FinancialRecommendationType.REVIEW_SUBSCRIPTION,
        subject=SubjectRef(SubjectKind.SERVICE, "provider_a_api"),
        rationale="Recurring spend with no recorded reuse in two periods.",
        evidence=(an_evidence("measurement", "docs/finance/q1-review.md"),),
        recommended_by="mira",
        recommended_on=TODAY,
    )
    base.update(overrides)
    return FinancialRecommendation(**base)


def test_a_recommendation_changes_nothing():
    recommendation = a_recommendation()
    for forbidden in ("apply", "execute", "pay", "approve", "implement"):
        assert not hasattr(recommendation, forbidden)


def test_an_overlapping_type_hands_off_to_organizational_intelligence():
    """Section 24: prefer reference/handoff over a conflicting vocabulary."""
    with pytest.raises(FinanceError, match="two vocabularies"):
        a_recommendation(type=FinancialRecommendationType.REVISE_BUDGET)
    handed = a_recommendation(
        type=FinancialRecommendationType.REVISE_BUDGET, handoff_to="revise_budget"
    )
    assert handed.hands_off_to_org_intelligence
    assert not a_recommendation().hands_off_to_org_intelligence


def test_a_non_overlapping_type_may_not_claim_a_handoff():
    with pytest.raises(FinanceError, match="no organizational-intelligence equivalent"):
        a_recommendation(handoff_to="revise_budget")


def test_the_handoff_targets_are_real_org_intelligence_types():
    from company.org_intelligence.recommendations import RecommendationType
    from company.finance import ORG_INTELLIGENCE_EQUIVALENT

    known = {item.value for item in RecommendationType}
    assert set(ORG_INTELLIGENCE_EQUIVALENT.values()) <= known


def test_recommending_a_spend_must_point_at_the_proposal(config):
    with pytest.raises(FinanceError, match="must reference the SpendProposal"):
        a_recommendation(type=FinancialRecommendationType.APPROVE_SPEND)
    reserved = a_recommendation(
        type=FinancialRecommendationType.APPROVE_SPEND, spend_proposal_id="spend.001"
    ).with_reservation(permissions=config.permissions)
    assert reserved.requires_ceo_approval
    assert reserved.reserved_actions == ("large_or_recurring_paid_api_spend",)


# --------------------------------------------------------------------------
# The multi-objective guard
# --------------------------------------------------------------------------


def test_no_global_financial_health_score_field_exists():
    """Section 23, enforced rather than described.

    A single number for a format, a video or the company erases exactly the
    information a decision needs, and the north star - long-term profitable
    audience growth - is not reducible to one.
    """
    import company.finance as package

    banned = ("score", "rating", "grade", "health", "overall", "roi", "index")
    offenders = []
    for name in dir(package):
        obj = getattr(package, name)
        if not dataclasses.is_dataclass(obj) or not isinstance(obj, type):
            continue
        for field in dataclasses.fields(obj):
            if any(word in field.name.lower() for word in banned):
                offenders.append(f"{name}.{field.name}")
    assert offenders == []


def test_no_module_defines_a_score_function_or_constant():
    banned = ("score", "_rank", "health_index", "roi_of")
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                assert not any(word in node.name.lower() for word in banned), (
                    f"{path.name}: {node.name} reads as a single-number verdict"
                )


def test_no_employee_value_score_exists():
    """Section 21: employee performance and cost remain separate."""
    from company.finance import LabourRate as Rate

    fields = {field.name for field in dataclasses.fields(Rate)}
    for banned in ("performance", "acceptance_rate", "value", "score", "output"):
        assert not any(banned in name for name in fields), (
            f"LabourRate carries {banned}; cost and performance must not meet"
        )


# --------------------------------------------------------------------------
# The store: append-only, deterministic, no silent overwrite
# --------------------------------------------------------------------------


def test_records_round_trip_through_the_store(tmp_path, period):
    store = FinanceStore(tmp_path)
    records = (period, a_cost(), a_revenue(), a_rate(), a_proposal(), an_investment())
    store.put_all(records)
    assert store.get("cost", "cost.001") == a_cost()
    assert store.get("revenue", "rev.001") == a_revenue()
    assert store.get("rate", "rate.tokens.2026") == a_rate()
    assert store.get("period", "2026-q1") == period
    assert store.ids("cost") == ("cost.001",)


def test_every_storable_record_type_round_trips(tmp_path, period):
    """One case per storable kind, because a to_dict is easy to leave broken.

    An earlier version of this package encoded most records through the shared
    helper and left one calling a name that no longer existed. Nothing caught it
    until a store write touched that one type, so this walks the store's own
    kind table rather than a list somebody remembers to extend.
    """
    from company.finance.store import _KINDS

    adjustment = CostAdjustment(
        adjustment_id="adj.round",
        cost_id="cost.001",
        adjusted_on=dt.date(2026, 2, 1),
        amount=Money("12.00", "EUR"),
        adjustment_kind=AdjustmentKind.CREDIT,
        reason="Provider refunded the failed render batch.",
        evidence=(an_evidence("payment_statement", "docs/refunds/1.pdf"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 2, 1),
    )
    mapping = ResourceCostMapping(
        mapping_id="map.round",
        resource_ref="task-014",
        measure="input tokens",
        quantity=Decimal("200000"),
        unit=RateUnit.TOKEN,
        provider="provider_a",
        category=CostCategory.AI_REASONING,
        subject=a_video(),
        measured_on=JAN,
    )
    labour = LabourRate(
        rate_id="lab.round",
        subject=SubjectRef(SubjectKind.DEPARTMENT, "research"),
        amount=Money("60.00", "EUR"),
        unit=RateUnit.HOUR,
        effective_from=JAN,
        source="docs/hr/rates.md",
        evidence=(an_evidence("document", "docs/hr/rates.md"),),
        recorded_by="mira",
        recorded_on=JAN,
    )
    decision = SpendDecision(
        decision_id="dec.round",
        proposal_id="spend.001",
        status=SpendStatus.REJECTED,
        decided_by="the ceo",
        decided_on=TODAY,
        reason="Not enough batches a month to pay for it.",
    )
    records = (
        period,
        a_cost(),
        adjustment,
        a_revenue(),
        a_rate(),
        labour,
        mapping,
        a_budget(period),
        an_investment(),
        a_reuse("e.round"),
        a_proposal(),
        decision,
        a_recommendation(),
    )
    store = FinanceStore(tmp_path)
    covered = set()
    for record in records:
        store.put(record)
        kind = record.kind
        directory, id_field, _decode = _KINDS[kind]
        covered.add(kind)
        assert store.get(kind, getattr(record, id_field)) == record
    assert covered == set(_KINDS), f"untested kinds: {sorted(set(_KINDS) - covered)}"


def test_serialization_is_canonical_and_byte_stable(tmp_path):
    store = FinanceStore(tmp_path)
    path = store.put(a_cost())
    first = path.read_text(encoding="utf-8")
    assert first == dumps(a_cost().to_dict())
    assert first.endswith("\n")
    # An equal record written again produces identical bytes, not an error.
    assert store.put(a_cost()) == path
    assert path.read_text(encoding="utf-8") == first
    # And the amount is text, so no float ever round-tripped through it.
    assert '"amount": "120"' in first


def test_the_ledger_refuses_a_silent_overwrite(tmp_path):
    """Section 16: a correction is a new record, never an edit."""
    store = FinanceStore(tmp_path)
    store.put(a_cost(amount=Money("120.00", "EUR")))
    with pytest.raises(LedgerViolation, match="append-only"):
        store.put(a_cost(amount=Money("999.00", "EUR")))
    # The original number survives.
    assert store.get("cost", "cost.001").amount == Money("120", "EUR")


def test_the_overwrite_message_names_what_changed(tmp_path):
    store = FinanceStore(tmp_path)
    store.put(a_cost())
    with pytest.raises(LedgerViolation, match="amount"):
        store.put(a_cost(amount=Money("999.00", "EUR")))


def test_the_event_ledger_records_every_money_record_in_order(tmp_path, period):
    store = FinanceStore(tmp_path)
    store.put(period)  # not money-bearing
    store.put(a_cost(cost_id="c.1"))
    store.put(a_revenue(revenue_id="r.1"))
    store.put(a_cost(cost_id="c.2"))
    entries = store.ledger()
    assert [entry["record_id"] for entry in entries] == ["c.1", "r.1", "c.2"]
    assert [entry["kind"] for entry in entries] == ["cost", "revenue", "cost"]
    assert all(len(entry["fingerprint"]) == 16 for entry in entries)


def test_the_store_needs_an_explicit_directory():
    with pytest.raises(FinanceStoreError, match="explicit non-empty path"):
        FinanceStore("   ")


def test_an_unknown_record_type_is_refused(tmp_path):
    with pytest.raises(FinanceStoreError, match="not a storable finance record"):
        FinanceStore(tmp_path).put(object())


def test_a_malformed_stored_record_names_the_file(tmp_path):
    store = FinanceStore(tmp_path)
    path = store.put(a_cost())
    path.write_text('{"cost_id": "cost.001"}', encoding="utf-8")
    with pytest.raises(FinanceStoreError, match="does not decode"):
        store.get("cost", "cost.001")


# --------------------------------------------------------------------------
# Integrity
# --------------------------------------------------------------------------


def test_a_duplicate_financial_record_id_is_reported():
    problems = check_integrity(
        costs=(a_cost(cost_id="c.1"), a_cost(cost_id="c.1", amount=Money("9", "EUR"))),
        external_reference_ids=(),
    )
    assert any("duplicate cost id" in item for item in problems)


def test_mixed_currency_records_for_one_subject_are_reported():
    problems = check_integrity(
        costs=(a_cost(cost_id="c.1"), a_cost(cost_id="c.2", amount=Money("10", "USD"))),
        external_reference_ids=(),
    )
    assert any("no summary can add them" in item for item in problems)


def test_an_orphan_allocation_share_is_reported():
    orphan = a_cost(
        cost_id="c.share",
        attribution=Attribution.ALLOCATED,
        allocation_method=AllocationMethod.EQUAL,
        allocation_basis="one share each",
        parent_cost_id="c.missing",
    )
    problems = check_integrity(costs=(orphan,), external_reference_ids=())
    assert any("not among the records supplied" in item for item in problems)


def test_shares_cannot_exceed_the_cost_they_come_from():
    parent = a_cost(cost_id="c.parent", amount=Money("20", "EUR"))
    share = a_cost(
        cost_id="c.share",
        amount=Money("30", "EUR"),
        attribution=Attribution.ALLOCATED,
        allocation_method=AllocationMethod.MANUAL,
        allocation_basis="somebody typed 30",
        parent_cost_id="c.parent",
    )
    problems = check_integrity(costs=(parent, share), external_reference_ids=())
    assert any("cannot distribute more than there was" in item for item in problems)


def test_recurring_paid_spend_without_a_flagged_proposal_is_reported():
    """Section 26: recurring paid spend lacking a reserved-action flag."""
    subscription = a_cost(
        cost_id="c.sub",
        category=CostCategory.SOFTWARE_SERVICE,
        recurrence=Recurrence.RECURRING,
        recurrence_period="monthly",
        source="provider_b_invoices",
    )
    problems = check_integrity(costs=(subscription,), external_reference_ids=())
    assert any("Recurring paid spend is CEO-reserved" in item for item in problems)


def test_a_mapping_pointing_at_an_unknown_resource_is_reported():
    mapping = ResourceCostMapping(
        mapping_id="map.1",
        resource_ref="task-does-not-exist",
        measure="tokens",
        quantity=1000,
        unit=RateUnit.TOKEN,
        provider="provider_a",
        category=CostCategory.AI_REASONING,
        subject=a_video(),
        measured_on=JAN,
    )
    problems = check_integrity(
        mappings=(mapping,), known_resource_ids=("task-014",), external_reference_ids=()
    )
    assert any("not among the usage or research records" in item for item in problems)


def test_an_unsupplied_external_reference_set_is_reported_not_passed():
    """A check that could not run says so; it does not pass silently."""
    problems = check_integrity(revenue=(a_revenue(),))
    assert any("no external reference ids" in item for item in problems)
    # With no revenue there is nothing that could be misattributed, so the
    # check has nothing to warn about rather than warning on principle.
    assert check_integrity(costs=(a_cost(),)) == ()


def test_assert_integrity_reports_every_problem_at_once():
    with pytest.raises(Exception) as excinfo:
        assert_integrity(
            costs=(a_cost(cost_id="c.1"), a_cost(cost_id="c.1")),
            revenue=(a_revenue(),),
        )
    assert "financial integrity problem" in str(excinfo.value)


def test_a_clean_set_reports_nothing(period, config):
    assert check_integrity(
        costs=(a_cost(),),
        revenue=(a_revenue(),),
        rates=(a_rate(),),
        budgets=(a_budget(period),),
        external_reference_ids=("ref_0012",),
        known_resource_ids=(),
        permissions=config.permissions,
    ) == ()


# --------------------------------------------------------------------------
# Boundaries: no production, no new dependencies, no subagents
# --------------------------------------------------------------------------


def test_finance_imports_no_production_module():
    production = {
        "race", "race2", "sloped", "marble3d", "rendering", "replay", "godot",
        "entities", "powers", "modes", "engine", "audio", "evaluation",
        "production", "intelligence", "tools",
    }
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            assert not (set(roots) & production), f"{path.name} imports production code"


def test_finance_depends_on_no_other_company_os_subsystem():
    """What keeps the capsule edge org-intelligence -> finance acyclic."""
    forbidden = {
        "company.org_intelligence",
        "company.workforce",
        "intelligence.research",
    }
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                for banned in forbidden:
                    assert not node.module.startswith(banned), (
                        f"{path.name} imports {node.module}; finance would then be both "
                        "above and below organizational intelligence"
                    )


def test_no_dependency_is_added():
    """Standard library, plus what the control plane already imports."""
    allowed_third_party: set[str] = set()
    internal = {"ai_platform", "company", "knowledge"}
    stdlib = set(__import__("sys").stdlib_module_names)
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            for root in roots:
                assert root in stdlib | internal | allowed_third_party, (
                    f"{path.name} imports {root}, which is a new dependency"
                )


def test_nothing_here_reaches_the_network_or_a_payment_provider():
    """The DO-NOT-BUILD list, checked rather than promised."""
    banned_imports = {"requests", "urllib", "http", "socket", "stripe", "paypal", "sqlite3"}
    banned_text = ("stripe", "paypal", "iban", "card_number", "bank_transfer")
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            roots: list[str] = []
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                roots = [node.module.split(".")[0]]
            assert not (set(roots) & banned_imports), f"{path.name} imports {roots}"
        lowered = source.lower()
        for banned in banned_text:
            assert banned not in lowered, f"{path.name} mentions {banned}"


def test_the_no_subagents_rule_is_untouched(config):
    assert config.permissions["bootstrap_defaults"]["no_subagents"] is True
    assert "change_no_subagents_policy" in config.permissions["ceo_reserved"]
    constitution = (REPO_ROOT / "company" / "constitution.md").read_text(encoding="utf-8")
    assert "subagent" in constitution.lower()


# --------------------------------------------------------------------------
# The capsule graph
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def capsules():
    from knowledge.company_os.capsules.index import SEED_ROOT, CapsuleIndex

    return CapsuleIndex.load(SEED_ROOT)


def test_the_finance_capsule_is_inside_the_character_ceiling(capsules):
    from knowledge.company_os.capsules.budget import DEFAULT_BUDGET

    capsule = capsules.get("company-finance")
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert capsule.owns_paths == ("company/finance",)
    assert "tests/test_company_finance.py" in capsule.tests


def test_the_control_plane_keeps_exactly_eight_direct_dependencies(capsules):
    """Finance was added transitively; the control plane's own list is untouched."""
    control_plane = capsules.get("company-os-control-plane")
    assert len(control_plane.dependencies) <= 8
    assert "company-finance" not in control_plane.dependencies


def test_the_dependency_closure_reaches_finance(capsules):
    """Via organizational intelligence, which may consume financial evidence."""
    closure = capsules.dependency_closure("company-os-control-plane")
    assert "company-finance" in closure
    # The external engineering runner is governed by a capsule but is not a
    # member of the control plane: it owns a path under a production root, so
    # an edge reaching it would declare the control plane rests on production.
    # `company.dashboard.builder.EXTERNAL_CAPSULES` is where that is stated.
    assert closure == tuple(
        sorted(set(capsules.ids()) - {"company-os-control-plane"} - EXTERNAL_CAPSULES)
    )
    org = capsules.get("company-organizational-intelligence")
    assert "company-finance" in org.dependencies


def test_finance_adds_no_dependency_cycle(capsules):
    """Finance depends only on leaves, so nothing can reach back to it.

    The one cycle in the seed graph is company-runtime <-> company-validation,
    which predates this package and is recorded as a known risk on the control
    plane capsule itself. This asserts that finance is in no cycle at all.
    """
    graph = {capsule.id: set(capsule.dependencies) for capsule in capsules.all()}
    reachable: set[str] = set()
    frontier = list(graph["company-finance"])
    while frontier:
        current = frontier.pop()
        if current in reachable or current not in graph:
            continue
        reachable.add(current)
        frontier.extend(graph[current])
    assert "company-finance" not in reachable
    assert reachable == {"ai-platform", "company-knowledge-store"}


def test_finance_writes_no_company_contract_file():
    """Advisory only: nothing here writes permissions, the registry or the constitution."""
    reserved = ("permissions.yaml", "org_registry.yaml", "constitution.md",
                "agent_contract.schema")
    writers = ("write_text(", "open(", "write_bytes(", "unlink(")
    for path in sorted(PACKAGE_ROOT.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        if any(name in source for name in reserved):
            assert not any(writer in source for writer in writers), (
                f"{path.name} names a company contract file and writes files"
            )
