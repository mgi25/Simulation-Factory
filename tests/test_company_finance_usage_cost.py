"""The usage-to-cost bridge, tested on the ways it could quietly invent money.

A usage record is a count. A cost is money. Everything between them is a place
where a plausible wrong number can be produced, and this file is a list of those
places:

    test_a_token_count_is_not_money
    test_without_a_rate_a_quantity_is_unpriced_not_free
    test_a_rate_in_the_wrong_unit_is_a_conflict_not_a_conversion
    test_two_rates_covering_one_day_conflict_rather_than_tie_break
    test_january_usage_keeps_januarys_price_after_february_arrives
    test_two_currencies_stay_two_numbers
    test_partial_cost_produces_no_cost_per_accepted_deliverable
    test_a_changed_rate_cannot_silently_overwrite_a_recorded_cost
    test_a_dry_run_writes_nothing

## The prices in this file are fixtures, not prices

Every provider here is named `fixture_provider_*`, every rate id starts
`fixture.`, and every source points into `docs/fixtures/`. None of these numbers
is any real vendor's price and none of them was looked up. That is enforced by
`test_fixture_pricing_is_obviously_not_authoritative`, because a synthetic price
that reads like a real one is how a test fixture becomes a quoted figure.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from ai_platform.context_manifest import ContextKind, ContextRef
from ai_platform.policy import SubagentPolicyViolation
from ai_platform.resource_classes import ReasoningClass
from ai_platform.usage import Outcome, ResourceUsageRecord, UsageUnit
from company.finance import (
    AttributionScope,
    ConflictKind,
    CostCategory,
    CostCompleteness,
    CostRate,
    CostRecord,
    CostableMeasure,
    FinanceError,
    FinanceStore,
    Money,
    RateCard,
    RateUnit,
    SubjectKind,
    SubjectRef,
    attribute_usage_costs,
    commit_attribution_costs,
    cost_per_accepted_deliverable,
    dogfood_report,
    load_rate_card,
    observe_usage,
    supersede,
)
from company.finance.__main__ import main as finance_main
from company.finance.usage_cost import MEASURE_UNITS
from company.runtime.execution_store import ExecutionStore
from company.runtime.packets import ExecutorHint, SessionPacket
from company.runtime.path_scope import PathScope
from company.runtime.receipts import ReceiptUsage, ReportedTest, SessionReceipt
from company.runtime.usage_store import ResourceUsageStore
from knowledge.company_os.records import Evidence

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "company" / "finance"
BRIDGE = PACKAGE_ROOT / "usage_cost.py"
REPO_ROOT = Path(__file__).resolve().parents[1]

JAN = dt.date(2026, 1, 15)
FEB = dt.date(2026, 2, 15)

# Everything below is invented. See the module docstring.
FIXTURE_SOURCE = "docs/fixtures/pricing/fixture_provider_a-2026-01.md"


# -- builders ---------------------------------------------------------------


def a_subject(video_id: str = "race_short_014") -> SubjectRef:
    return SubjectRef(kind=SubjectKind.VIDEO, id=video_id)


def fixture_evidence(ref: str = "resource_usage/task-014/000001.json") -> Evidence:
    return Evidence(kind="measurement", ref=ref, note="immutable resource usage record")


def a_fixture_rate(**overrides) -> CostRate:
    """A price nobody charges, for a provider that does not exist."""
    base = dict(
        rate_id="fixture.rate.tokens.2026",
        provider="fixture_provider_a",
        category=CostCategory.AI_REASONING,
        unit=RateUnit.MILLION_TOKENS,
        amount=Money("3.00", "EUR"),
        effective_from=dt.date(2026, 1, 1),
        source=FIXTURE_SOURCE,
        evidence=(Evidence(kind="document", ref=FIXTURE_SOURCE, note="fixture"),),
        recorded_by="mira",
        recorded_on=dt.date(2026, 1, 1),
        notes="fixture pricing: invented for tests, not any provider's price list",
    )
    base.update(overrides)
    return CostRate(**base)


def a_usage_record(**overrides) -> ResourceUsageRecord:
    base = dict(
        task_id="task-014",
        reasoning_class=ReasoningClass.D,
        outcome=Outcome.ACCEPTED,
        input_units=200_000,
        output_units=40_000,
        usage_unit=UsageUnit.TOKEN,
        tool_calls=20,
        duration_s=91.5,
    )
    base.update(overrides)
    return ResourceUsageRecord(**base)


def an_observation(record=None, **overrides):
    record = record if record is not None else a_usage_record()
    usage_ref = overrides.pop("usage_ref", "resource_usage/task-014/000001.json")
    base = dict(
        usage_ref=usage_ref,
        provider="fixture_provider_a",
        subject=a_subject(),
        measured_on=JAN,
        evidence=(fixture_evidence(usage_ref),),
        attempt=1,
        executor="claude_code",
    )
    base.update(overrides)
    return observe_usage(record, **base)


def a_run(observations=None, rates=None, as_of=JAN):
    observations = observations if observations is not None else [an_observation()]
    card = RateCard(rates if rates is not None else (a_fixture_rate(),))
    return attribute_usage_costs(observations, card, as_of=as_of)


def by_measure(run):
    return {item.measure: item for item in run.attributions}


# --------------------------------------------------------------------------
# Usage is not money
# --------------------------------------------------------------------------


def test_a_token_count_is_not_money():
    """The core rule: a measured quantity carries no amount until a rate is applied.

    An observation is built from a real record with 240,000 tokens on it, and
    holds no `Money` anywhere - only quantities, units and the provider whose
    price list would have to be supplied.
    """
    observation = an_observation()
    assert observation.has_costable_quantity
    quantities = {
        mapping.mapping_id.rsplit(".", 1)[-1]: mapping.quantity
        for mapping in observation.mappings
    }
    assert quantities["input_units"] == Decimal(200_000)
    for mapping in observation.mappings:
        assert not hasattr(mapping, "amount")
        assert not isinstance(mapping.quantity, Money)


def test_without_a_rate_a_quantity_is_unpriced_not_free():
    """The most expensive wrong number: an unpriced provider looking free."""
    run = a_run(rates=())
    assert run.completeness is CostCompleteness.UNPRICED
    assert run.known_cost == {}
    assert run.priced == ()
    for item in run.attributions:
        assert item.amount is None
        assert item.unpriced_reason is not None
        assert "never counted as zero" in str(item.unpriced_reason)
    assert run.missing_pricing


def test_an_explicit_rate_produces_a_deterministic_amount():
    """200,000 tokens at a fixture 3.00/M is 0.60, exactly, every time."""
    run = a_run()
    priced = by_measure(run)
    assert priced[CostableMeasure.INPUT_UNITS].amount == Money("0.6", "EUR")
    assert priced[CostableMeasure.OUTPUT_UNITS].amount == Money("0.12", "EUR")
    assert priced[CostableMeasure.INPUT_UNITS].rate_id == "fixture.rate.tokens.2026"
    assert run.known_cost == {"EUR": Money("0.72", "EUR")}


def test_the_measure_table_matches_what_mapping_actually_builds():
    """`MEASURE_UNITS` is documentation only if nothing checks it against reality."""
    observation = an_observation(include_duration=True)
    for mapping in observation.mappings:
        measure = CostableMeasure(mapping.mapping_id.rsplit(".", 1)[-1])
        assert MEASURE_UNITS[measure] == (mapping.unit, mapping.category)


def test_a_usage_record_with_no_costable_quantity_is_skipped_not_zeroed():
    """A provider that exposed nothing produces no cost, and says which record."""
    bare = a_usage_record(
        input_units=None, output_units=None, usage_unit=UsageUnit.UNKNOWN, tool_calls=None
    )
    run = a_run([an_observation(bare)])
    assert run.attributions == ()
    assert run.completeness is CostCompleteness.INSUFFICIENT_QUANTITY
    assert run.skipped == ("resource_usage/task-014/000001.json",)
    assert run.known_cost == {}
    assert any("no costable quantity" in item for item in run.missing_quantity)


def test_a_character_count_is_not_priced_per_token():
    """A unit conversion nobody supplied is not performed, it is left unpriced."""
    characters = a_usage_record(usage_unit=UsageUnit.CHARACTER)
    run = a_run([an_observation(characters)])
    measures = {item.measure for item in run.attributions}
    assert CostableMeasure.INPUT_UNITS not in measures
    assert CostableMeasure.TOOL_CALLS in measures


# --------------------------------------------------------------------------
# Rate resolution
# --------------------------------------------------------------------------


def test_a_rate_in_the_wrong_unit_is_a_conflict_not_a_conversion():
    """A render-minute price does not price a token count at any exchange rate."""
    wrong_unit = a_fixture_rate(
        rate_id="fixture.rate.render.2026", unit=RateUnit.RENDER_MINUTE
    )
    run = a_run(rates=(wrong_unit,))
    tokens = by_measure(run)[CostableMeasure.INPUT_UNITS]
    assert tokens.amount is None
    assert tokens.conflict is not None
    assert tokens.conflict.conflict is ConflictKind.UNIT_MISMATCH
    assert "render_minute" in tokens.conflict.detail
    assert "converts between units" in tokens.conflict.detail
    assert len(run.conflicts) == 2  # input and output units, same mismatch


def test_a_rate_outside_its_effective_dates_does_not_price_anything():
    """Section 3: a historical day takes a historical rate, or no rate at all."""
    february_only = a_fixture_rate(
        rate_id="fixture.rate.tokens.feb", effective_from=dt.date(2026, 2, 1)
    )
    run = a_run(rates=(february_only,))
    assert run.completeness is CostCompleteness.UNPRICED
    assert all("2026-01-15" in str(item.unpriced_reason) for item in run.unpriced)


def test_two_rates_covering_one_day_conflict_rather_than_tie_break():
    """Two recorded prices for one day is a correction somebody owes."""
    left = a_fixture_rate(rate_id="fixture.rate.a")
    right = a_fixture_rate(rate_id="fixture.rate.b", amount=Money("4.00", "EUR"))
    run = a_run(rates=(left, right))
    tokens = by_measure(run)[CostableMeasure.INPUT_UNITS]
    assert tokens.amount is None
    assert tokens.conflict is not None
    assert tokens.conflict.conflict is ConflictKind.OVERLAPPING_RATES
    assert "not a tie this code may break" in tokens.conflict.detail
    assert run.completeness is not CostCompleteness.COMPLETE


def test_january_usage_keeps_januarys_price_after_february_arrives():
    """Superseding a price must not restate what January cost."""
    old = a_fixture_rate(rate_id="fixture.rate.jan")
    new = a_fixture_rate(rate_id="fixture.rate.feb", amount=Money("9.00", "EUR"))
    closed, opened = supersede(old, new, last_day=dt.date(2026, 1, 31))
    card = RateCard((closed, opened))

    january = attribute_usage_costs([an_observation()], card, as_of=JAN)
    february = attribute_usage_costs(
        [an_observation(measured_on=FEB)], card, as_of=FEB
    )
    assert by_measure(january)[CostableMeasure.INPUT_UNITS].amount == Money("0.6", "EUR")
    assert by_measure(february)[CostableMeasure.INPUT_UNITS].amount == Money("1.8", "EUR")
    assert by_measure(january)[CostableMeasure.INPUT_UNITS].rate_id == "fixture.rate.jan"


def test_two_currencies_stay_two_numbers():
    """Nothing here converts a currency, so nothing here collapses two totals."""
    euro = a_fixture_rate(rate_id="fixture.rate.eur")
    dollar = a_fixture_rate(
        rate_id="fixture.rate.usd",
        provider="fixture_provider_b",
        amount=Money("5.00", "USD"),
    )
    second = an_observation(
        provider="fixture_provider_b",
        usage_ref="resource_usage/task-015/000001.json",
    )
    run = a_run([an_observation(), second], rates=(euro, dollar))
    assert set(run.known_cost) == {"EUR", "USD"}
    assert run.known_cost["EUR"] == Money("0.72", "EUR")
    assert run.known_cost["USD"] == Money("1.2", "USD")
    result = cost_per_accepted_deliverable(run)
    assert result.amount is None
    assert any("nothing here converts a currency" in item for item in result.missing)


def test_a_rate_card_loads_from_json_without_reaching_anywhere(tmp_path: Path):
    """Section 12: rate cards are files somebody wrote, never a price fetch."""
    path = tmp_path / "rates.json"
    path.write_text(
        '{"rates": [' + __import__("json").dumps(a_fixture_rate().to_dict()) + "]}",
        encoding="utf-8",
    )
    card = load_rate_card(path)
    assert len(card) == 1
    assert card.get("fixture.rate.tokens.2026") is not None
    run = a_run(rates=tuple(card))
    assert run.completeness is CostCompleteness.PARTIAL


def test_a_malformed_rate_card_is_refused_rather_than_partially_loaded(tmp_path: Path):
    path = tmp_path / "rates.json"
    path.write_text('[{"rate_id": "fixture.broken"}]', encoding="utf-8")
    with pytest.raises(FinanceError, match="does not decode"):
        load_rate_card(path)


# --------------------------------------------------------------------------
# Accepted, rejected, retried
# --------------------------------------------------------------------------


def _three_attempts():
    """One task: a rejection, a retry that was rejected, then an acceptance."""
    return [
        an_observation(
            a_usage_record(
                outcome=Outcome.REJECTED,
                rejection_reason="the merge apron still ejects orange",
                input_units=100_000,
                output_units=0,
                tool_calls=None,
            ),
            usage_ref="resource_usage/task-014/000001.json",
            attempt=1,
        ),
        an_observation(
            a_usage_record(
                outcome=Outcome.REJECTED,
                rejection_reason="guard wall height regressed",
                input_units=50_000,
                output_units=0,
                tool_calls=None,
                retries=2,
            ),
            usage_ref="resource_usage/task-014/000002.json",
            attempt=2,
        ),
        an_observation(
            a_usage_record(
                outcome=Outcome.ACCEPTED,
                input_units=150_000,
                output_units=0,
                tool_calls=None,
            ),
            usage_ref="resource_usage/task-014/000003.json",
            attempt=3,
        ),
    ]


def test_rejected_and_retried_attempts_keep_their_cost():
    """A rejected result consumed everything an accepted one would have."""
    run = a_run(_three_attempts())
    assert run.completeness is CostCompleteness.COMPLETE
    assert run.accepted_cost == {"EUR": Money("0.45", "EUR")}
    assert run.rejected_cost == {"EUR": Money("0.45", "EUR")}
    assert run.retry_bearing_attempts == 1
    assert run.retry_bearing_cost == {"EUR": Money("0.15", "EUR")}
    assert run.rework_cost == {"EUR": Money("0.45", "EUR")}
    assert run.known_cost == {"EUR": Money("0.9", "EUR")}


def test_cost_per_accepted_includes_the_attempts_it_took_by_default():
    """The question is what an accepted deliverable cost, rework included."""
    run = a_run(_three_attempts())
    everything = cost_per_accepted_deliverable(run)
    assert everything.amount == Money("0.9", "EUR")
    assert everything.scope is AttributionScope.ALL_ATTEMPTS
    assert everything.accepted_deliverables == 1

    accepted_only = cost_per_accepted_deliverable(
        run, scope=AttributionScope.ACCEPTED_ONLY
    )
    assert accepted_only.amount == Money("0.45", "EUR")
    assert accepted_only.amount < everything.amount


def test_retry_semantics_are_stated_rather_than_implied():
    run = a_run(_three_attempts())
    assert any("not a separable charge" in item for item in run.caveats)


# --------------------------------------------------------------------------
# Completeness gates the division
# --------------------------------------------------------------------------


def test_partial_cost_produces_no_cost_per_accepted_deliverable():
    """Dividing a floor by a count yields a unit cost that understates by the gap."""
    run = a_run()  # tool_calls have no request rate
    assert run.completeness is CostCompleteness.PARTIAL
    assert run.known_cost == {"EUR": Money("0.72", "EUR")}
    result = cost_per_accepted_deliverable(run)
    assert result.amount is None
    assert not result.is_known
    assert any(item.startswith("cost is partial") for item in result.missing)


def test_complete_cost_produces_cost_per_accepted_deliverable():
    tokens = a_fixture_rate()
    requests = a_fixture_rate(
        rate_id="fixture.rate.requests",
        category=CostCategory.API,
        unit=RateUnit.REQUEST,
        amount=Money("0.01", "EUR"),
    )
    run = a_run(rates=(tokens, requests))
    assert run.completeness is CostCompleteness.COMPLETE
    assert run.missing == ()
    result = cost_per_accepted_deliverable(run)
    assert result.amount == Money("0.92", "EUR")  # 0.60 + 0.12 tokens + 0.20 calls


def test_an_unstated_outcome_blocks_the_derived_accepted_count():
    """A count nobody can derive is unknown, not assumed to be one."""
    stateless = dataclasses.replace(an_observation(), outcome="")
    run = a_run([stateless])
    result = cost_per_accepted_deliverable(run)
    assert result.accepted_deliverables is None
    assert any("cannot be derived" in item for item in result.missing)


def test_an_explicit_deliverable_count_overrides_the_derived_one():
    tokens = a_fixture_rate()
    requests = a_fixture_rate(
        rate_id="fixture.rate.requests",
        category=CostCategory.API,
        unit=RateUnit.REQUEST,
        amount=Money("0.01", "EUR"),
    )
    run = a_run(rates=(tokens, requests))
    result = cost_per_accepted_deliverable(run, accepted_deliverables=2)
    assert result.amount == Money("0.46", "EUR")


def test_zero_accepted_deliverables_is_unknown_not_infinite():
    rejected = an_observation(
        a_usage_record(outcome=Outcome.REJECTED, rejection_reason="start bias too high")
    )
    run = a_run([rejected])
    result = cost_per_accepted_deliverable(run)
    assert result.amount is None
    assert any("nothing to divide by" in item for item in result.missing)


# --------------------------------------------------------------------------
# Descriptive views, and what they refuse to claim
# --------------------------------------------------------------------------


def test_context_expansion_is_described_never_blamed():
    """Section 8: attribution by expansion is accounting, not a causal finding."""
    expanded = a_usage_record(
        context_sources=("file:a.py", "file:b.py"),
        initial_context_sources=("file:a.py",),
        expanded_context_sources=("file:b.py",),
        expansion_count=1,
        required_expansion_count=1,
        expansion_chars=4200,
        expansion_ledger_fingerprint="0123456789abcdef",
    )
    run = a_run(
        [
            an_observation(expanded, usage_ref="resource_usage/task-014/000001.json"),
            an_observation(
                a_usage_record(), usage_ref="resource_usage/task-015/000001.json"
            ),
        ]
    )
    view = run.expansion_view
    assert view.attempts_with_expansion == 1
    assert view.attempts_requiring_expansion == 1
    assert view.expansion_chars == 4200
    assert view.accepted_with_expansion == 1
    assert view.known_cost_with_expansion == {"EUR": Money("0.72", "EUR")}
    assert view.known_cost_without_expansion == {"EUR": Money("0.72", "EUR")}
    assert "not what any of it caused" in view.caveat
    payload = view.to_dict()
    assert "caveat" in payload
    for key in payload:
        assert "caused_by" not in key and "attributable_to" not in key


def test_the_executor_and_class_views_rank_nothing():
    first = an_observation(usage_ref="resource_usage/task-014/000001.json")
    second = an_observation(
        a_usage_record(task_id="task-015", reasoning_class=ReasoningClass.B),
        usage_ref="resource_usage/task-015/000001.json",
        executor="codex",
    )
    run = a_run([first, second])
    classes = {group.key: group for group in run.by_reasoning_class}
    assert set(classes) == {"B", "D"}
    assert classes["D"].samples == 1
    assert classes["D"].unpriced == 1  # the tool calls
    executors = [group.key for group in run.by_executor]
    assert executors == sorted(executors)  # sorted by key, never by cost
    for group in run.by_executor:
        assert not hasattr(group, "rank")
        assert not hasattr(group, "score")


def test_provider_metadata_does_not_alter_the_arithmetic():
    """Section 16: the provider is a lookup key, never a branch in the logic."""
    amounts = []
    for provider, executor in (
        ("fixture_provider_a", "claude_code"),
        ("fixture_provider_b", "codex"),
        ("fixture_provider_c", "human"),
        ("fixture_provider_d", "future_adapter"),
    ):
        run = a_run(
            [an_observation(provider=provider, executor=executor)],
            rates=(a_fixture_rate(rate_id="fixture.rate.x", provider=provider),),
        )
        amounts.append(by_measure(run)[CostableMeasure.INPUT_UNITS].amount)
    assert amounts == [Money("0.6", "EUR")] * 4


def test_the_bridge_branches_on_no_provider_name():
    """Grep is the wrong tool for this; the AST is the right one."""
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    vendors = {
        "openai", "anthropic", "claude", "codex", "gpt", "gemini", "google",
        "mistral", "cohere", "llama", "claude_code",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            parts = [node.left, *node.comparators]
            for part in parts:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    assert part.value.lower() not in vendors, (
                        f"usage_cost.py compares against {part.value!r}; business logic "
                        "that branches by provider is a vendor-shaped code path"
                    )


# --------------------------------------------------------------------------
# Identity, replay and restatement
# --------------------------------------------------------------------------


def test_the_same_inputs_produce_the_same_attribution_id():
    first = a_run()
    second = a_run()
    assert first.run_id == second.run_id
    assert [item.attribution_id for item in first.attributions] == [
        item.attribution_id for item in second.attributions
    ]


def test_a_changed_rate_produces_a_distinct_identity_with_a_shared_lineage():
    cheap = a_run(rates=(a_fixture_rate(rate_id="fixture.rate.cheap"),))
    dear = a_run(
        rates=(a_fixture_rate(rate_id="fixture.rate.dear", amount=Money("6.00", "EUR")),)
    )
    left = by_measure(cheap)[CostableMeasure.INPUT_UNITS]
    right = by_measure(dear)[CostableMeasure.INPUT_UNITS]
    assert left.attribution_id != right.attribution_id
    assert left.lineage_id == right.lineage_id


def test_changed_evidence_produces_a_distinct_identity():
    """Section 14: changed evidence is a different claim about the same quantity."""
    original = a_run()
    amended = a_run(
        [
            an_observation(
                evidence=(
                    fixture_evidence(),
                    Evidence(kind="document", ref="docs/fixtures/correction.md"),
                )
            )
        ]
    )
    assert (
        by_measure(original)[CostableMeasure.INPUT_UNITS].attribution_id
        != by_measure(amended)[CostableMeasure.INPUT_UNITS].attribution_id
    )


def test_a_dry_run_writes_nothing(tmp_path: Path):
    store = FinanceStore(tmp_path)
    run = a_run()
    commit = commit_attribution_costs(
        run, store, recorded_by="mira", recorded_on=JAN, dry_run=True
    )
    assert commit.dry_run
    assert commit.written == 0
    assert commit.costs  # it still reports what it would have written
    assert list(tmp_path.rglob("*.json")) == []
    assert store.list("cost") == ()
    assert store.ledger() == ()


def test_a_committed_run_appends_cost_records(tmp_path: Path):
    store = FinanceStore(tmp_path)
    run = a_run()
    commit = commit_attribution_costs(run, store, recorded_by="mira", recorded_on=JAN)
    assert commit.written == 2  # the two priced token lines
    recorded = store.list("cost")
    assert len(recorded) == 2
    assert all(isinstance(item, CostRecord) for item in recorded)
    assert sum((item.amount for item in recorded[1:]), recorded[0].amount) == Money(
        "0.72", "EUR"
    )
    for item in recorded:
        assert item.resource_ref == "resource_usage/task-014/000001.json"
        assert item.evidence
        assert "fixture.rate.tokens.2026" in item.notes
    assert len(store.ledger()) == 2
    assert store.list("resource_cost_mapping")


def test_replaying_an_attribution_records_one_cost_not_two(tmp_path: Path):
    store = FinanceStore(tmp_path)
    commit_attribution_costs(a_run(), store, recorded_by="mira", recorded_on=JAN)
    second = commit_attribution_costs(
        a_run(), store, recorded_by="mira", recorded_on=JAN
    )
    assert second.written == 0
    assert len(second.unchanged) == 2
    assert len(store.list("cost")) == 2


def test_a_changed_rate_cannot_silently_overwrite_a_recorded_cost(tmp_path: Path):
    """The whole no-silent-restatement guarantee, end to end."""
    store = FinanceStore(tmp_path)
    commit_attribution_costs(
        a_run(rates=(a_fixture_rate(rate_id="fixture.rate.first"),)),
        store,
        recorded_by="mira",
        recorded_on=JAN,
    )
    dearer = a_run(
        rates=(
            a_fixture_rate(rate_id="fixture.rate.second", amount=Money("6.00", "EUR")),
        )
    )
    refused = commit_attribution_costs(
        dearer, store, recorded_by="mira", recorded_on=JAN
    )
    assert refused.written == 0
    assert len(refused.restatements) == 2
    assert "append-only" in str(refused.restatements[0])
    assert len(store.list("cost")) == 2  # unchanged

    allowed = commit_attribution_costs(
        dearer, store, recorded_by="mira", recorded_on=JAN, allow_restatement=True
    )
    assert allowed.written == 2
    recorded = {item.cost_id: item for item in store.list("cost")}
    assert len(recorded) == 4  # both the original pair and the superseding pair
    superseding = [item for item in recorded.values() if item.supersedes]
    assert len(superseding) == 2
    for item in superseding:
        assert recorded[item.supersedes].amount < item.amount


def test_an_unpriced_attribution_never_becomes_a_cost_record(tmp_path: Path):
    store = FinanceStore(tmp_path)
    commit = commit_attribution_costs(
        a_run(rates=()), store, recorded_by="mira", recorded_on=JAN
    )
    assert commit.costs == ()
    assert store.list("cost") == ()


def test_committing_needs_a_name(tmp_path: Path):
    with pytest.raises(FinanceError, match="recorded_by"):
        commit_attribution_costs(
            a_run(), FinanceStore(tmp_path), recorded_by="  ", recorded_on=JAN
        )


# --------------------------------------------------------------------------
# The dogfood chain: task -> packet -> receipt -> usage -> rate -> cost
# --------------------------------------------------------------------------


def a_packet(task_id: str = "task-014") -> SessionPacket:
    return SessionPacket(
        task_id=task_id,
        objective="Bridge measured usage to recorded cost",
        employee="finance_engineer",
        reasoning_class=ReasoningClass.D,
        resource_class="D",
        context_refs=(
            ContextRef(
                kind=ContextKind.MODULE_CONTRACT,
                ref="company/finance/rates.py",
                reason="the price records the bridge resolves",
            ),
        ),
        explicit_context_refs=("module_contract:company/finance/rates.py",),
        automatic_context_refs=(),
        context_fingerprint="0123456789abcdef",
        context_cache_key="fedcba9876543210",
        constraints=("no hardcoded provider pricing",),
        acceptance_criteria=("usage alone never becomes money",),
        path_scope=PathScope(allowed=("company/finance",)),
        expected_branch="company-os-v1-finance-cost-dogfood",
        executor=ExecutorHint.CLAUDE_CODE,
    )


def a_receipt(packet: SessionPacket, attempt: int, outcome: Outcome, **changes):
    values = dict(
        task_id=packet.task_id,
        packet_fingerprint=packet.fingerprint(),
        outcome=outcome,
        packet_attempt=attempt,
        summary="Bridge implemented and tested.",
        branch=packet.expected_branch,
        files_changed=("company/finance/usage_cost.py",),
        tests=(ReportedTest("pytest tests/test_company_finance_usage_cost.py", True, "ok"),),
        evidence=("tests/test_company_finance_usage_cost.py",),
        usage=ReceiptUsage(
            input_units=200_000,
            output_units=40_000,
            usage_unit=UsageUnit.TOKEN,
            tool_calls=20,
        ),
        executor=ExecutorHint.CLAUDE_CODE,
    )
    if outcome is Outcome.REJECTED:
        values["rejection_reason"] = "the first pass priced tool calls at the token rate"
    values.update(changes)
    return SessionReceipt(**values)


def build_dogfood_state(root: Path):
    """The real stores, the real record types, and one invented price list."""
    runtime_state = root / "runtime"
    packet = a_packet()
    execution = ExecutionStore(runtime_state)
    usage_store = ResourceUsageStore(runtime_state)

    rejected_usage = a_usage_record(
        outcome=Outcome.REJECTED,
        rejection_reason="the first pass priced tool calls at the token rate",
        input_units=100_000,
        output_units=20_000,
        tool_calls=8,
    )
    accepted_usage = a_usage_record(retries=1)
    for attempt, (usage, outcome) in enumerate(
        ((rejected_usage, Outcome.REJECTED), (accepted_usage, Outcome.ACCEPTED)), start=1
    ):
        execution.append_packet(packet)
        execution.append_receipt(a_receipt(packet, attempt, outcome))
        usage_store.append(usage)
    return runtime_state, usage_store, execution


def observations_from_store(usage_store: ResourceUsageStore, execution: ExecutionStore):
    records = usage_store.records("task-014")
    pointers = usage_store.pointers("task-014")
    receipts = {item.attempt: item.receipt for item in execution.attempts("task-014")}
    out = []
    for index, (record, pointer) in enumerate(zip(records, pointers), start=1):
        out.append(
            observe_usage(
                record,
                usage_ref=pointer.record_ref,
                usage_fingerprint=pointer.fingerprint,
                provider="fixture_provider_a",
                subject=a_subject(),
                measured_on=JAN,
                evidence=(fixture_evidence(pointer.record_ref),),
                attempt=index,
                executor=receipts[index].executor,
            )
        )
    return out


def test_the_whole_chain_from_a_packet_to_a_cost_record(tmp_path: Path):
    """Section 10: the shape the company actually runs, priced end to end."""
    _runtime, usage_store, execution = build_dogfood_state(tmp_path)
    observations = observations_from_store(usage_store, execution)
    assert [item.attempt for item in observations] == [1, 2]
    assert [item.executor for item in observations] == ["claude_code", "claude_code"]
    assert [item.outcome for item in observations] == ["rejected", "accepted"]
    assert all(item.usage_fingerprint for item in observations)

    tokens = a_fixture_rate()
    requests = a_fixture_rate(
        rate_id="fixture.rate.requests",
        category=CostCategory.API,
        unit=RateUnit.REQUEST,
        amount=Money("0.01", "EUR"),
    )
    run = attribute_usage_costs(observations, RateCard((tokens, requests)), as_of=JAN)
    assert run.completeness is CostCompleteness.COMPLETE

    # 120k + 240k tokens at 3.00/M, and 28 calls at 0.01
    assert run.known_cost == {"EUR": Money("1.36", "EUR")}
    assert run.accepted_cost == {"EUR": Money("0.92", "EUR")}
    assert run.rejected_cost == {"EUR": Money("0.44", "EUR")}

    finance = FinanceStore(tmp_path / "finance")
    commit = commit_attribution_costs(
        run, finance, recorded_by="mira", recorded_on=JAN
    )
    assert commit.written == 6
    costs = finance.list("cost")
    assert len(costs) == 6
    assert {item.category for item in costs} == {
        CostCategory.AI_REASONING,
        CostCategory.API,
    }

    report = dogfood_report(run)
    assert report.usage_records_inspected == 2
    assert report.priced == 6
    assert report.unpriced == 0
    assert report.accepted_deliverables == 1
    assert report.cost_per_accepted.amount == Money("1.36", "EUR")
    assert report.rework_cost == {"EUR": Money("0.44", "EUR")}
    assert report.missing == ()


def test_the_dogfood_report_answers_section_eighteen(tmp_path: Path):
    _runtime, usage_store, execution = build_dogfood_state(tmp_path)
    run = attribute_usage_costs(
        observations_from_store(usage_store, execution),
        RateCard((a_fixture_rate(),)),
        as_of=JAN,
    )
    payload = dogfood_report(run).to_dict()
    for key in (
        "usage_records_inspected",
        "priced",
        "unpriced",
        "known_cost",
        "accepted_cost",
        "rejected_cost",
        "cost_per_accepted",
        "missing",
    ):
        assert key in payload
    assert payload["unpriced"] == 2  # the two tool-call lines
    assert payload["completeness"] == "partial"
    assert payload["cost_per_accepted"]["amount"] is None
    assert payload["missing"]


def test_the_report_carries_no_global_efficiency_score():
    """Constitution rule 3: one number over these dimensions would be optimised."""
    run = a_run()
    payload = dogfood_report(run).to_dict()
    banned = ("score", "rating", "grade", "index", "efficiency", "rank")
    for key in payload:
        assert not any(word in key.lower() for word in banned), key


def test_the_cli_prices_a_real_usage_history(tmp_path: Path, capsys):
    """The operational path, including the part that must write nothing."""
    runtime, _usage, _execution = build_dogfood_state(tmp_path)
    rates = tmp_path / "rates.json"
    rates.write_text(
        __import__("json").dumps([a_fixture_rate().to_dict()]), encoding="utf-8"
    )
    finance_state = tmp_path / "finance"
    argv = [
        "--state-dir", str(finance_state),
        "usage-cost",
        "--usage-state", str(runtime),
        "--rate-card", str(rates),
        "--provider", "fixture_provider_a",
        "--subject", "video:race_short_014",
        "--measured-on", "2026-01-15",
        "--execution-state", str(runtime),
    ]
    assert finance_main(argv) == 1  # tool calls are unpriced, and it says so
    payload = __import__("json").loads(capsys.readouterr().out)
    assert payload["report"]["usage_records_inspected"] == 2
    assert payload["report"]["known_cost"] == {"EUR": "1.08"}
    assert payload["report"]["completeness"] == "partial"
    assert not finance_state.exists()

    assert finance_main(argv + ["--commit", "--recorded-by", "mira", "--dry-run"]) == 1
    dry = __import__("json").loads(capsys.readouterr().out)
    assert dry["commit"]["written"] == 0
    assert dry["commit"]["dry_run"] is True
    assert not finance_state.exists()

    assert finance_main(argv + ["--commit", "--recorded-by", "mira"]) == 1
    committed = __import__("json").loads(capsys.readouterr().out)
    assert committed["commit"]["written"] == 4
    assert len(FinanceStore(finance_state).list("cost")) == 4


def test_the_cli_refuses_to_commit_without_a_name(tmp_path: Path):
    runtime, _usage, _execution = build_dogfood_state(tmp_path)
    rates = tmp_path / "rates.json"
    rates.write_text(
        __import__("json").dumps([a_fixture_rate().to_dict()]), encoding="utf-8"
    )
    argv = [
        "--state-dir", str(tmp_path / "finance"),
        "usage-cost",
        "--usage-state", str(runtime),
        "--rate-card", str(rates),
        "--provider", "fixture_provider_a",
        "--subject", "video:race_short_014",
        "--measured-on", "2026-01-15",
        "--commit",
    ]
    assert finance_main(argv) == 1


# --------------------------------------------------------------------------
# Boundaries: what this task was told not to do
# --------------------------------------------------------------------------


def test_fixture_pricing_is_obviously_not_authoritative():
    """A synthetic price that reads like a real one becomes a quoted figure."""
    real_vendors = {
        "openai", "anthropic", "google", "mistral", "cohere", "meta", "azure",
        "aws", "bedrock", "vertex",
    }
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    # The scanners themselves hold the vendor names, so they are not scanned.
    scanner_names = {
        "test_fixture_pricing_is_obviously_not_authoritative",
        "test_the_bridge_branches_on_no_provider_name",
        "test_the_bridge_adds_no_dependency_and_no_production_import",
        "test_the_bridge_reaches_no_network_and_no_billing_provider",
    }
    scanners = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name in scanner_names
    ]
    assert len(scanners) == len(scanner_names), (
        "a scanner was renamed; the exclusion below would then silently stop "
        "checking part of this file"
    )
    skip = {id(child) for scanner in scanners for child in ast.walk(scanner)}
    for node in ast.walk(tree):
        if id(node) in skip:
            continue
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        lowered = node.value.lower()
        for vendor in real_vendors:
            assert vendor not in lowered, (
                f"this fixture names {vendor!r}; fixture pricing must not read as any "
                "real provider's price list"
            )
    for rate in (a_fixture_rate(),):
        assert rate.provider.startswith("fixture_provider")
        assert rate.rate_id.startswith("fixture.")
        assert "fixtures" in rate.source
        assert "fixture pricing" in rate.notes


def test_no_provider_price_is_hardcoded_in_the_bridge():
    """Section 4, checked on the module the brief names rather than promised."""
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Money":
            first = node.args[0] if node.args else None
            if isinstance(first, ast.Constant):
                pytest.fail(
                    f"usage_cost.py builds Money({first.value!r}); a price is a CostRate "
                    "somebody supplied, not a literal in this package"
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            assert node.value in (0, 1, 2, 3, 4), (
                f"usage_cost.py contains the bare number {node.value!r}; a magnitude "
                "in this module is either an index or a price that escaped the rate card"
            )


def test_the_bridge_reaches_no_network_and_no_billing_provider():
    banned_imports = {
        "requests", "urllib", "http", "socket", "stripe", "paypal", "boto3", "httpx",
    }
    banned_text = ("stripe", "paypal", "billing_api", "api_key", "bank_transfer")
    source = BRIDGE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        assert not (set(roots) & banned_imports), f"usage_cost.py imports {roots}"
    lowered = source.lower()
    for word in banned_text:
        assert word not in lowered, f"usage_cost.py mentions {word!r}"


def test_the_bridge_adds_no_dependency_and_no_production_import():
    stdlib = set(__import__("sys").stdlib_module_names)
    internal = {"ai_platform", "company", "knowledge"}
    production = {
        "race", "race2", "sloped", "marble3d", "rendering", "replay", "godot",
        "entities", "powers", "modes", "engine", "audio", "evaluation", "production",
        "intelligence", "tools",
    }
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        for root in roots:
            assert root not in production, f"usage_cost.py imports production {root}"
            assert root in stdlib | internal, f"{root} is a new dependency"


def test_the_bridge_itself_touches_no_filesystem_path():
    """Every write goes through the store a caller supplied, and only there.

    A module that can open a path of its own choosing is a module that can write
    outside the state directory somebody named, which is the failure
    `company/runtime/state_paths.py` was built to prevent. This one holds no path
    API at all: `commit_attribution_costs` takes the sink as an argument.
    """
    assert BRIDGE.parent == PACKAGE_ROOT
    tree = ast.parse(BRIDGE.read_text(encoding="utf-8"))
    filesystem_modules = {"os", "io", "shutil", "pathlib", "tempfile", "glob"}
    path_calls = {"open", "write_text", "read_text", "mkdir", "unlink", "rmtree"}
    for node in ast.walk(tree):
        roots: list[str] = []
        if isinstance(node, ast.Import):
            roots = [alias.name.split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots = [node.module.split(".")[0]]
        assert not (set(roots) & filesystem_modules), (
            f"usage_cost.py imports {roots}; the bridge writes through the store its "
            "caller supplied, never through a path of its own"
        )
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in path_calls, f"usage_cost.py calls {name}()"


def test_attribution_creates_no_spend_proposal_or_decision(tmp_path: Path):
    """Section 17: a rate card is price evidence, not spending authorisation."""
    store = FinanceStore(tmp_path)
    commit_attribution_costs(a_run(), store, recorded_by="mira", recorded_on=JAN)
    assert store.list("spend_proposal") == ()
    assert store.list("spend_decision") == ()
    assert store.list("budget") == ()
    source = BRIDGE.read_text(encoding="utf-8")
    for word in ("SpendProposal", "SpendDecision", "approve", "subscribe"):
        assert word not in source, f"the bridge mentions {word}"


def test_the_no_subagent_invariant_still_refuses_the_record():
    """A nested-agent attempt cannot be recorded, so it can never be priced."""
    with pytest.raises(SubagentPolicyViolation):
        a_usage_record(subagents_used=1)


def test_an_observation_without_evidence_is_refused():
    with pytest.raises(FinanceError, match="checkable measurement"):
        an_observation(evidence=())


def test_attribution_refuses_an_implicit_rate_card():
    with pytest.raises(FinanceError, match="implicit default rate card"):
        attribute_usage_costs([an_observation()], None, as_of=JAN)
