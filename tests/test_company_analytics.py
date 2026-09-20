"""Company OS analytics: observations, experiments, and what may not be concluded.

The suite is organised by the thing being protected rather than by module,
because most of what this subsystem guarantees is a refusal and the refusals cut
across modules. The sections are:

    observations      immutable, dated, sourced, never overwritten
    metrics           one name, one meaning, one unit, one denominator
    provenance        our private data in, competitor private data out
    experiments       changed and locked, confounding, kill conditions
    comparison        window compatibility, rate denominators, unmatched metrics
    causality         the guard, from every angle we could find
    baselines         named populations and explicit exclusions
    grouping          association, never ranking, never inference
    postmortem        no failed video without learning
    learning          evidence, falsifiers, scope, the hypothesis lifecycle
    store             append-only and deterministic
    report            concise, deterministic, no score
    boundaries        imports, production isolation, the capsule
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import json
import re
from pathlib import Path

import pytest

from knowledge.company_os.records import Evidence

from company.analytics import (
    ALL_DIMENSIONS,
    CONSTRUCTION_ENFORCED,
    DEFAULT_REGISTRY,
    FIRST_7D,
    FIRST_24H,
    FIRST_30D,
    FIRST_HOUR,
    LIFETIME,
    STANDARD_AGE_WINDOWS,
    AgeWindow,
    AnalyticsError,
    AnalyticsHypothesis,
    AnalyticsLearning,
    AnalyticsStore,
    AnalyzedDeliverable,
    CausalAssessment,
    CompetitorPublicReference,
    ComparisonBasis,
    ContentFeatures,
    DataScope,
    DataSource,
    DateRange,
    DeliverableKind,
    DeliverableOutcome,
    DeliverablePostmortem,
    Direction,
    EvidenceRequired,
    EvidenceStrength,
    ExecutionRecordKind,
    ExecutionReference,
    Expectation,
    ExperimentResult,
    ExperimentSpecification,
    ExperimentStatus,
    FeatureDimension,
    FinanceRecordKind,
    FinanceReference,
    GroupBy,
    HypothesisState,
    KillCondition,
    LearningScope,
    LedgerViolation,
    MetricDefinition,
    MetricKind,
    MetricObservation,
    MetricRegistry,
    ObservationSeries,
    OutlierMethod,
    OutlierRule,
    OverclaimRefused,
    Provenance,
    ProvenanceViolation,
    ResearchRecordKind,
    ResearchReference,
    Variable,
    Verdict,
    build_baseline,
    build_report,
    check_integrity,
    compare_deliverables,
    evaluate_experiment,
    group_performance,
    group_value,
    observe,
    promote,
    summarise_metric,
)

UTC = dt.timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "company" / "analytics"


# --------------------------------------------------------------------------
# Fixtures: one control, one variant, and readings taken off a studio export
# --------------------------------------------------------------------------


def an_evidence(ref: str = "docs/exports/studio_2026_09_10.csv") -> Evidence:
    return Evidence(kind="document", ref=ref, note="authenticated export")


def a_provenance(source: DataSource = DataSource.OWN_STUDIO_EXPORT, **kwargs) -> Provenance:
    return Provenance(
        source=source,
        retrieved_by=kwargs.pop("retrieved_by", "studio csv export 2026-09-10"),
        evidence=kwargs.pop("evidence", (an_evidence(),)),
        **kwargs,
    )


def a_scope(**kwargs) -> DataScope:
    return DataScope(population=kwargs.pop("population", "all viewers"), **kwargs)


def a_deliverable(deliverable_id: str = "race-short-014", **kwargs) -> AnalyzedDeliverable:
    return AnalyzedDeliverable(
        deliverable_id=deliverable_id,
        kind=kwargs.pop("kind", DeliverableKind.SHORT),
        format_id=kwargs.pop("format_id", "race_short"),
        published_at=kwargs.pop("published_at", dt.datetime(2026, 9, 8, 12, 0, tzinfo=UTC)),
        **kwargs,
    )


@pytest.fixture
def control() -> AnalyzedDeliverable:
    return a_deliverable(
        "race-short-013",
        version="v30",
        published_at=dt.datetime(2026, 9, 1, 12, 0, tzinfo=UTC),
        features=ContentFeatures.from_labels({FeatureDimension.HOOK_TYPE: "slow_reveal"}),
    )


@pytest.fixture
def variant() -> AnalyzedDeliverable:
    return a_deliverable(
        "race-short-014",
        version="v31",
        experiment_id="exp-cold-open",
        features=ContentFeatures.from_labels({FeatureDimension.HOOK_TYPE: "cold_open"}),
    )


def readings(deliverable: AnalyzedDeliverable, apv: float, ctr: float, impressions: float | None,
             prefix: str) -> tuple[MetricObservation, ...]:
    at = deliverable.published_at + dt.timedelta(hours=20)
    return (
        observe(f"{prefix}-apv", deliverable, "average_percentage_viewed", apv, at,
                a_provenance(), a_scope(), denominator_value=42.0),
        observe(f"{prefix}-ctr", deliverable, "click_through_rate", ctr, at,
                a_provenance(), a_scope(), denominator_value=impressions),
        observe(f"{prefix}-views", deliverable, "views", 50000.0, at, a_provenance(), a_scope()),
    )


@pytest.fixture
def observations(control, variant) -> tuple[MetricObservation, ...]:
    return readings(control, 0.41, 0.061, 120000.0, "c") + readings(
        variant, 0.47, 0.068, 131000.0, "v"
    )


def a_specification(**kwargs) -> ExperimentSpecification:
    defaults = dict(
        experiment_id="exp-cold-open",
        objective="Find out whether a cold open holds more of the first day's audience.",
        hypothesis="A cold open raises average percentage viewed against the slow reveal.",
        basis=ComparisonBasis.MATCHED_PAIR,
        control_id="race-short-013",
        variant_ids=("race-short-014",),
        variables_changed=(
            Variable("hook_type", "Cold open replaces the slow reveal.", "slow_reveal", "cold_open"),
        ),
        variables_locked=(Variable("camera_style", "Chase rig unchanged from v30."),),
        primary_metrics=("average_percentage_viewed",),
        guardrail_metrics=("click_through_rate",),
        observation_window=FIRST_24H,
        minimum_sample=6,
        owner="MGI",
        created_on=dt.date(2026, 9, 5),
        expectations=(
            Expectation("average_percentage_viewed", Direction.UP,
                        "The hook lab suggested the drop is in the first three seconds."),
        ),
        kill_conditions=(
            KillCondition("kc-ctr-floor", "click_through_rate", Direction.DOWN, 0.05,
                          "Below a 5% CTR the format stops being promoted at all."),
        ),
    )
    defaults.update(kwargs)
    return ExperimentSpecification(**defaults)


def a_result(observations, specification=None, **kwargs) -> ExperimentResult:
    specification = specification or a_specification()
    comparison = compare_deliverables(
        "race-short-013", "race-short-014", observations, specification.observation_window
    )
    return evaluate_experiment(
        result_id=kwargs.pop("result_id", "res-cold-open-1"),
        specification=specification,
        comparison=comparison,
        observation_ids=[o.observation_id for o in observations],
        interpretation="APV moved up as predicted; the pairing is not a randomised split.",
        reviewed_on=dt.date(2026, 9, 10),
        guardrail_values=kwargs.pop("guardrail_values", {"click_through_rate": 0.068}),
        **kwargs,
    )


# --------------------------------------------------------------------------
# Observations: immutable, dated, and four readings stay four readings
# --------------------------------------------------------------------------


def test_an_observation_is_frozen(variant):
    reading = readings(variant, 0.47, 0.068, 131000.0, "v")[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        reading.value = 0.99


def test_four_snapshots_of_one_video_are_four_observations(variant):
    """Section 4: 1h, 24h, 7d and 30d readings coexist; none replaces another."""
    ages = {"first_hour": 0.5, "first_24h": 20, "first_7d": 100, "first_30d": 500}
    series = ObservationSeries.build(
        variant.deliverable_id,
        DEFAULT_REGISTRY.get("views"),
        [
            observe(f"obs-{label}", variant, "views", 1000.0 * (index + 1),
                    variant.published_at + dt.timedelta(hours=hours), a_provenance(), a_scope())
            for index, (label, hours) in enumerate(ages.items())
        ],
    )
    assert len(series) == 4
    assert [o.value for o in series] == [1000.0, 2000.0, 3000.0, 4000.0]
    assert series.at_window(FIRST_HOUR).value == 1000.0
    assert series.at_window(FIRST_24H).value == 2000.0
    assert series.earliest.value == 1000.0 and series.latest.value == 4000.0


def test_a_window_is_half_open_so_no_reading_is_counted_twice(variant):
    """Hour 24 belongs to day 2. A closed interval would double-count it."""
    at_24h = observe("obs-edge", variant, "views", 5.0,
                     variant.published_at + dt.timedelta(hours=24), a_provenance(), a_scope())
    assert at_24h.age_hours == 24.0
    assert not at_24h.in_window(FIRST_24H)
    assert at_24h.in_window(FIRST_7D)


def test_observed_at_must_carry_a_timezone(variant):
    with pytest.raises(AnalyticsError, match="no timezone"):
        observe("obs-naive", variant, "views", 1.0, dt.datetime(2026, 9, 9, 8, 0),
                a_provenance(), a_scope())


def test_observed_at_is_an_instant_not_a_day(variant):
    """A date would collapse the one-hour and twenty-hour readings into one."""
    with pytest.raises(AnalyticsError, match="collapse"):
        observe("obs-date", variant, "views", 1.0, dt.date(2026, 9, 9), a_provenance(), a_scope())


def test_a_reading_cannot_predate_publication(variant):
    with pytest.raises(AnalyticsError, match="before publication"):
        observe("obs-early", variant, "views", 1.0,
                dt.datetime(2026, 9, 1, tzinfo=UTC), a_provenance(), a_scope())


def test_an_unpublished_prototype_has_no_age_rather_than_age_zero():
    """None, not 0.0 - otherwise every prototype reading lands in the first hour."""
    prototype = AnalyzedDeliverable(
        deliverable_id="hook-lab-a",
        kind=DeliverableKind.PROTOTYPE,
        format_id="race_short",
    )
    reading = observe("obs-proto", prototype, "camera_cuts", 12.0,
                      dt.datetime(2026, 9, 9, tzinfo=UTC),
                      a_provenance(DataSource.OWN_PRODUCTION_MEASUREMENT), a_scope())
    assert reading.age_hours is None
    assert not any(reading.in_window(w) for w in STANDARD_AGE_WINDOWS)
    assert any("cannot be placed in an observation window" in c for c in reading.caveats)


def test_a_published_short_must_carry_a_publication_instant():
    with pytest.raises(AnalyticsError, match="published thing"):
        AnalyzedDeliverable(
            deliverable_id="race-short-020",
            kind=DeliverableKind.SHORT,
            format_id="race_short",
        )


def test_a_measurement_must_be_a_finite_number(variant):
    for bad in (float("nan"), float("inf")):
        with pytest.raises(AnalyticsError, match="finite"):
            observe("obs-bad", variant, "views", bad,
                    dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(), a_scope())
    with pytest.raises(AnalyticsError, match="not a number is a description"):
        observe("obs-text", variant, "views", "lots",
                dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(), a_scope())


def test_a_reading_needs_evidence():
    with pytest.raises(EvidenceRequired, match="somebody remembered"):
        Provenance(source=DataSource.OWN_STUDIO_EXPORT, retrieved_by="studio", evidence=())


def test_an_incomplete_reading_must_say_what_it_excludes():
    with pytest.raises(AnalyticsError, match="unknown with a number"):
        DataScope(population="all viewers", complete=False)
    partial = DataScope(population="all viewers", complete=False,
                        excludes=("viewers in the EU, withheld by consent settings",))
    assert any("incomplete reading" in c for c in partial.caveats)


# --------------------------------------------------------------------------
# Metrics: one name, one meaning, one unit, one denominator
# --------------------------------------------------------------------------


def test_every_standard_metric_declares_a_unit_and_a_definition():
    for name in DEFAULT_REGISTRY.names():
        definition = DEFAULT_REGISTRY.get(name)
        assert definition.unit.strip()
        assert len(definition.definition) > 30, name


def test_a_rate_must_name_its_denominator():
    with pytest.raises(AnalyticsError, match="must name its denominator"):
        MetricDefinition("made_up_rate", MetricKind.RATE, "fraction", "A rate with no base.")


def test_a_non_rate_may_not_carry_a_denominator():
    with pytest.raises(AnalyticsError, match="only meaningful for a rate"):
        MetricDefinition("views2", MetricKind.COUNT, "views", "A count of views.",
                         denominator="impressions")


def test_retention_does_not_mean_five_things():
    """The three retention-shaped metrics are three definitions, not one word."""
    names = [n for n in DEFAULT_REGISTRY.names() if "retention" in n or "percentage_viewed" in n]
    assert len(names) >= 3
    definitions = {DEFAULT_REGISTRY.get(n).definition for n in names}
    assert len(definitions) == len(names), "two retention metrics share a definition"
    apv = DEFAULT_REGISTRY.get("average_percentage_viewed")
    at_3s = DEFAULT_REGISTRY.get("retention_at_3s")
    assert apv.denominator != at_3s.denominator


def test_a_value_cannot_be_recorded_against_a_bare_unknown_name(variant):
    with pytest.raises(AnalyticsError, match="no definition for metric"):
        observe("obs-x", variant, "vibes", 1.0, dt.datetime(2026, 9, 9, tzinfo=UTC),
                a_provenance(), a_scope())


def test_one_metric_name_cannot_have_two_definitions():
    registry = MetricRegistry()
    with pytest.raises(AnalyticsError, match="already defined differently"):
        registry.register(
            MetricDefinition("views", MetricKind.COUNT, "views",
                             "Something entirely different that also got called views.")
        )


def test_registering_the_same_definition_twice_is_a_no_op():
    registry = MetricRegistry()
    registry.register(DEFAULT_REGISTRY.get("views"))
    assert "views" in registry


# --------------------------------------------------------------------------
# Provenance: our private data in, competitor private data out
# --------------------------------------------------------------------------


def test_our_own_authenticated_private_analytics_are_accepted(variant):
    for source in (DataSource.OWN_STUDIO_EXPORT, DataSource.OWN_ANALYTICS_API):
        reading = observe(f"obs-{source.value}", variant, "average_view_duration_seconds", 19.4,
                          dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(source), a_scope())
        assert reading.provenance.is_first_party


@pytest.mark.parametrize("source", [DataSource.PLATFORM_PUBLIC, DataSource.RESEARCH_REFERENCE])
def test_a_private_metric_from_a_public_source_is_refused(variant, source):
    """Nobody can read retention off a page, so a value here came from elsewhere."""
    with pytest.raises(ProvenanceViolation, match="private channel analytic"):
        observe("obs-leak", variant, "average_percentage_viewed", 0.5,
                dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(source), a_scope())


def test_a_public_metric_from_a_public_source_is_fine(variant):
    reading = observe("obs-public", variant, "likes", 900.0,
                      dt.datetime(2026, 9, 9, tzinfo=UTC),
                      a_provenance(DataSource.PLATFORM_PUBLIC), a_scope())
    assert reading.value == 900.0


def test_a_manual_entry_inherits_authority_and_never_grants_its_own(variant):
    with pytest.raises(ProvenanceViolation, match="transcribed from"):
        Provenance(source=DataSource.MANUAL_ENTRY, retrieved_by="typed in by hand",
                   evidence=(an_evidence(),))

    transcribed = Provenance(
        source=DataSource.MANUAL_ENTRY,
        retrieved_by="typed from the studio export",
        evidence=(an_evidence(),),
        transcribed_from=DataSource.OWN_STUDIO_EXPORT,
    )
    assert transcribed.is_first_party
    reading = observe("obs-manual", variant, "average_percentage_viewed", 0.47,
                      dt.datetime(2026, 9, 9, tzinfo=UTC), transcribed, a_scope())
    assert reading.value == 0.47

    borrowed = Provenance(
        source=DataSource.MANUAL_ENTRY,
        retrieved_by="typed off a competitor's page",
        evidence=(an_evidence("docs/research/dossier.md"),),
        transcribed_from=DataSource.PLATFORM_PUBLIC,
    )
    assert not borrowed.is_first_party
    with pytest.raises(ProvenanceViolation):
        observe("obs-borrowed", variant, "average_percentage_viewed", 0.9,
                dt.datetime(2026, 9, 9, tzinfo=UTC), borrowed, a_scope())


def test_a_manual_entry_chain_must_end_somewhere_real():
    with pytest.raises(ProvenanceViolation, match="actually read"):
        Provenance(source=DataSource.MANUAL_ENTRY, retrieved_by="typed",
                   evidence=(an_evidence(),), transcribed_from=DataSource.MANUAL_ENTRY)


def test_a_competitor_private_metric_has_nowhere_to_live():
    """Their public counts are citable; their retention is not observable by anyone."""
    with pytest.raises(ProvenanceViolation, match="cannot be attributed"):
        CompetitorPublicReference(
            dossier_ids=("dossier-rival-01",),
            public_metrics=("views", "average_percentage_viewed"),
        )
    allowed = CompetitorPublicReference(
        dossier_ids=("dossier-rival-01",), public_metrics=("views", "likes")
    )
    assert allowed.public_metrics == ("views", "likes")
    assert not hasattr(allowed, "value")


def test_a_deliverable_cannot_be_a_competitor():
    """No COMPETITOR kind: somebody else's video cannot become one of our records."""
    assert "competitor" not in {k.value for k in DeliverableKind}


def test_a_competitor_reference_must_cite_a_dossier():
    with pytest.raises(AnalyticsError, match="rumour"):
        CompetitorPublicReference(dossier_ids=())


# --------------------------------------------------------------------------
# Experiments: what changed, what was held, and what stops it
# --------------------------------------------------------------------------


def test_an_experiment_must_name_what_it_changed():
    with pytest.raises(AnalyticsError, match="changed nothing"):
        a_specification(variables_changed=())


def test_changed_and_locked_are_distinct_and_may_not_overlap():
    spec = a_specification()
    assert {v.dimension for v in spec.variables_changed} == {"hook_type"}
    assert {v.dimension for v in spec.variables_locked} == {"camera_style"}
    with pytest.raises(AnalyticsError, match="both changed and locked"):
        a_specification(
            variables_locked=(Variable("hook_type", "Also claimed to be held still."),)
        )


def test_confounding_is_derived_from_the_count_and_cannot_be_declared():
    single = a_specification()
    assert not single.confounded
    assert single.primary_change.dimension == "hook_type"

    many = a_specification(
        variables_changed=(
            Variable("hook_type", "Cold open."),
            Variable("audio_style", "New bed."),
            Variable("race_length", "Shorter race."),
        ),
    )
    assert many.confounded
    assert many.primary_change is None
    assert "3 variables changed together" in many.confounding_reasons[0]
    assert "audio_style, hook_type, race_length" in many.confounding_reasons[0]
    assert many.to_dict()["confounded"] is True
    # There is no settable field that could disagree with the derivation.
    assert "confounded" not in {f.name for f in dataclasses.fields(many)}


def test_a_multi_variable_experiment_is_legal_and_says_so(observations):
    """Section 6: one primary change is supported, not required."""
    spec = a_specification(
        variables_changed=(
            Variable("hook_type", "Cold open."),
            Variable("audio_style", "New bed."),
        ),
    )
    result = a_result(observations, spec)
    assert result.confounders
    assert "2 variables changed" in result.causal.blockers[1]


def test_a_primary_metric_must_be_chosen_before_the_result():
    with pytest.raises(AnalyticsError, match="whichever metric moved"):
        a_specification(primary_metrics=())


def test_a_metric_cannot_be_both_primary_and_guardrail():
    with pytest.raises(AnalyticsError, match="second chance to look good"):
        a_specification(guardrail_metrics=("average_percentage_viewed",))


def test_an_expectation_about_an_unmeasured_metric_is_refused():
    with pytest.raises(AnalyticsError, match="cannot be wrong"):
        a_specification(
            expectations=(Expectation("likes", Direction.UP, "Felt likely."),)
        )


def test_a_matched_pair_needs_a_control():
    with pytest.raises(AnalyticsError, match="needs a control_id"):
        a_specification(control_id="")


def test_a_kill_condition_threshold_is_supplied_never_invented():
    with pytest.raises(AnalyticsError, match="opinion presented as company policy"):
        KillCondition("kc", "click_through_rate", Direction.DOWN, "low", "Too low.")
    condition = KillCondition("kc", "click_through_rate", Direction.DOWN, 0.05, "Floor.")
    assert condition.breached_by(0.04)
    assert not condition.breached_by(0.05)
    assert not condition.breached_by(0.06)


def test_a_kill_condition_must_name_a_side():
    with pytest.raises(AnalyticsError, match="no side to be on the wrong side of"):
        KillCondition("kc", "views", Direction.UNCHANGED, 1.0, "Neither up nor down.")


def test_kill_conditions_fire_and_appear_on_the_result(observations):
    spec = a_specification()
    result = a_result(observations, spec, guardrail_values={"click_through_rate": 0.04})
    assert result.kill_conditions_triggered
    assert "below the 0.05" in result.kill_conditions_triggered[0]
    assert result.guardrails_breached


def test_a_guardrail_with_no_value_is_missing_not_passing(observations):
    result = a_result(observations, a_specification(), guardrail_values={})
    guardrail = next(g for g in result.guardrail_outcomes if g.metric == "click_through_rate")
    assert guardrail.missing and guardrail.value is None and not guardrail.breached
    assert "click_through_rate" in result.missing_measures


# --------------------------------------------------------------------------
# Comparison: windows, denominators, and what stays visible
# --------------------------------------------------------------------------


def test_a_comparison_across_incompatible_windows_is_refused(control, variant):
    """Video A at 24h against video B at 30d is two measurements, not a difference."""
    early = observe("c-early", control, "views", 1000.0,
                    control.published_at + dt.timedelta(hours=2), a_provenance(), a_scope())
    late = observe("v-late", variant, "views", 9000.0,
                   variant.published_at + dt.timedelta(days=20), a_provenance(), a_scope())

    at_24h = compare_deliverables("race-short-013", "race-short-014", [early, late], FIRST_24H)
    assert at_24h.comparisons == ()
    assert at_24h.only_in_a == ("views",)
    assert at_24h.only_in_b == ()

    assert FIRST_24H.mismatch(FIRST_30D)
    assert "not a measurement of the same thing" in FIRST_24H.mismatch(FIRST_30D)
    assert FIRST_24H.mismatch(FIRST_24H) == ""


def test_a_rate_with_an_unknown_denominator_is_not_comparable(control, variant):
    """8% of 200 and 8% of two million are the same number and different evidence."""
    at = dt.timedelta(hours=20)
    left = observe("c-ctr", control, "click_through_rate", 0.06,
                   control.published_at + at, a_provenance(), a_scope(),
                   denominator_value=120000.0)
    right = observe("v-ctr", variant, "click_through_rate", 0.08,
                    variant.published_at + at, a_provenance(), a_scope())

    comparison = compare_deliverables("race-short-013", "race-short-014", [left, right], FIRST_24H)
    entry = comparison.get("click_through_rate")
    assert not entry.comparable
    assert entry.difference is None
    assert entry.relative_change is None
    assert "did not record it" in entry.reasons[0]
    assert "impressions" in entry.reasons[0]
    assert comparison.differences() == {}


def test_supplying_the_denominator_makes_the_rate_comparable(observations):
    comparison = compare_deliverables(
        "race-short-013", "race-short-014", observations, FIRST_24H
    )
    entry = comparison.get("click_through_rate")
    assert entry.comparable
    assert entry.difference == pytest.approx(0.007)
    assert entry.direction is Direction.UP


def test_unmatched_metrics_stay_visible(control, variant):
    at = dt.timedelta(hours=20)
    only_a = observe("c-likes", control, "likes", 40.0, control.published_at + at,
                     a_provenance(), a_scope())
    only_b = observe("v-shares", variant, "shares", 12.0, variant.published_at + at,
                     a_provenance(), a_scope())
    both_a = observe("c-views", control, "views", 100.0, control.published_at + at,
                     a_provenance(), a_scope())
    both_b = observe("v-views", variant, "views", 200.0, variant.published_at + at,
                     a_provenance(), a_scope())

    comparison = compare_deliverables(
        "race-short-013", "race-short-014", [only_a, only_b, both_a, both_b], FIRST_24H
    )
    assert comparison.only_in_a == ("likes",)
    assert comparison.only_in_b == ("shares",)
    assert comparison.unmatched_metrics == ("likes", "shares")
    assert "likes" in comparison.to_dict()["only_in_a"]


def test_a_partial_reading_carries_its_caveat_into_the_comparison(control, variant):
    at = dt.timedelta(hours=20)
    left = observe("c-views", control, "views", 100.0, control.published_at + at,
                   a_provenance(), a_scope())
    right = observe("v-views", variant, "views", 200.0, variant.published_at + at,
                    a_provenance(),
                    a_scope(complete=False, excludes=("views from embedded players",)))
    comparison = compare_deliverables("race-short-013", "race-short-014", [left, right], FIRST_24H)
    entry = comparison.get("views")
    assert entry.comparable, "a partial reading is a caveat, not a refusal"
    assert any("embedded players" in c for c in entry.caveats)


def test_a_comparison_produces_no_winner(observations):
    comparison = compare_deliverables(
        "race-short-013", "race-short-014", observations, FIRST_24H
    )
    serialised = comparison.to_dict()
    for banned in ("winner", "better", "best", "score", "rank"):
        assert banned not in json.dumps(serialised).lower(), banned


def test_a_deliverable_cannot_be_compared_with_itself(observations):
    with pytest.raises(AnalyticsError, match="no difference to report"):
        compare_deliverables("race-short-013", "race-short-013", observations, FIRST_24H)


def test_a_comparison_needs_an_explicit_window(observations):
    with pytest.raises(AnalyticsError, match="same point in their lives"):
        compare_deliverables("race-short-013", "race-short-014", observations, "first_24h")


# --------------------------------------------------------------------------
# Causality: the guard, from every angle
# --------------------------------------------------------------------------


def test_the_default_is_no_causal_claim(observations):
    result = a_result(observations)
    assert result.causal_claim_supported is False
    assert result.causal.blockers
    assert "observed association only" in result.causal.statement


def test_one_video_doing_better_does_not_prove_the_change_caused_it(observations):
    """The headline guard. APV moved the predicted way; nothing is attributable."""
    result = a_result(observations)
    assert result.verdict is Verdict.SUPPORTS_HYPOTHESIS
    assert result.causal_claim_supported is False
    assert "assignment was not controlled" in result.causal.blockers[0]
    assert "association only" in result.summary_line()


@pytest.mark.parametrize(
    "basis",
    [ComparisonBasis.SINGLE_DELIVERABLE, ComparisonBasis.OBSERVATIONAL,
     ComparisonBasis.MATCHED_PAIR],
)
def test_no_uncontrolled_design_can_ever_support_a_causal_claim(basis):
    assessment = CausalAssessment(
        basis=basis, sample_size=10_000, minimum_sample=1, changed_variable_count=1
    )
    assert assessment.causal_claim_supported is False
    assert assessment.statement == assessment.association_statement


def test_a_randomised_split_can_support_one_and_the_wording_stays_qualified():
    assessment = CausalAssessment(
        basis=ComparisonBasis.RANDOMIZED_SPLIT,
        sample_size=40,
        minimum_sample=20,
        changed_variable_count=1,
    )
    assert assessment.causal_claim_supported is True
    assert assessment.blockers == ()
    assert "within this randomised split" in assessment.statement
    assert "not a general claim" in assessment.statement
    assert "caused" not in assessment.statement


@pytest.mark.parametrize(
    "kwargs,fragment",
    [
        (dict(changed_variable_count=2), "2 variables changed"),
        (dict(changed_variable_count=0), "nothing to attribute to"),
        (dict(sample_size=3), "below the 20"),
        (dict(uncompared_primary_metrics=("average_percentage_viewed",)), "never compared"),
        (dict(unresolved_confounders=("published in a promotion week",)), "unresolved confounder"),
    ],
)
def test_each_condition_alone_blocks_the_causal_claim(kwargs, fragment):
    base = dict(
        basis=ComparisonBasis.RANDOMIZED_SPLIT,
        sample_size=40,
        minimum_sample=20,
        changed_variable_count=1,
    )
    base.update(kwargs)
    assessment = CausalAssessment(**base)
    assert assessment.causal_claim_supported is False
    assert any(fragment in blocker for blocker in assessment.blockers)


def test_causal_claim_supported_is_derived_and_has_no_field_to_set():
    fields = {f.name for f in dataclasses.fields(CausalAssessment)}
    assert "causal_claim_supported" not in fields
    assert isinstance(
        type(CausalAssessment).__dict__.get("causal_claim_supported")
        or CausalAssessment.causal_claim_supported,
        property,
    )


def test_a_causal_assessment_never_says_the_word_caused():
    for basis in ComparisonBasis:
        assessment = CausalAssessment(
            basis=basis, sample_size=40, minimum_sample=1, changed_variable_count=1
        )
        assert "caused" not in assessment.statement.lower()
        assert "proves" not in assessment.statement.lower()


def test_association_is_represented_separately_from_a_causal_claim(observations):
    result = a_result(observations)
    serialised = result.to_dict()["causal"]
    assert serialised["causal_claim_supported"] is False
    assert serialised["blockers"]
    assert "observed association only" in serialised["statement"]


def test_an_insufficient_sample_forces_the_verdict_regardless_of_the_numbers(observations):
    """Below the pre-declared minimum, no clarity in the data buys a conclusion."""
    spec = a_specification(minimum_sample=50)
    result = a_result(observations, spec)
    assert result.verdict is Verdict.INSUFFICIENT_EVIDENCE
    assert any("below the 50" in b for b in result.causal.blockers)


def test_a_conclusive_verdict_under_the_minimum_cannot_be_constructed(observations):
    result = a_result(observations)
    with pytest.raises(OverclaimRefused, match="Below the evidence condition"):
        dataclasses.replace(
            result,
            verdict=Verdict.SUPPORTS_HYPOTHESIS,
            causal=CausalAssessment(
                basis=ComparisonBasis.MATCHED_PAIR,
                sample_size=6,
                minimum_sample=50,
                changed_variable_count=1,
            ),
        )


def test_a_missing_primary_metric_yields_inconclusive_not_a_guess(control, variant):
    at = dt.timedelta(hours=20)
    observations = (
        observe("c-views", control, "views", 100.0, control.published_at + at,
                a_provenance(), a_scope()),
        observe("v-views", variant, "views", 200.0, variant.published_at + at,
                a_provenance(), a_scope()),
        *(observe(f"filler-{i}", control, "likes", float(i), control.published_at + at,
                  a_provenance(), a_scope()) for i in range(4)),
    )
    spec = a_specification(minimum_sample=6)
    result = a_result(observations, spec)
    assert result.verdict is Verdict.INCONCLUSIVE
    assert "average_percentage_viewed" in result.missing_measures
    outcome = next(o for o in result.primary_outcomes if o.metric == "average_percentage_viewed")
    assert outcome.observed is None and outcome.matched_expectation is None


def test_a_result_must_say_what_would_change_the_conclusion(observations):
    result = a_result(observations)
    assert result.what_would_change_it
    with pytest.raises(AnalyticsError, match="no falsifier"):
        dataclasses.replace(result, what_would_change_it=())


def test_a_result_must_name_its_observations(observations):
    result = a_result(observations)
    with pytest.raises(EvidenceRequired, match="impression"):
        dataclasses.replace(result, observation_ids=(), sample_size=0)


def test_sample_size_must_match_the_observations_named(observations):
    result = a_result(observations)
    with pytest.raises(AnalyticsError, match="not what was hoped for"):
        dataclasses.replace(result, sample_size=999)


def test_reading_a_different_window_after_the_fact_is_refused(observations):
    """How a null result becomes a positive one, closed off."""
    spec = a_specification(observation_window=FIRST_24H)
    late = compare_deliverables("race-short-013", "race-short-014", observations, FIRST_30D)
    with pytest.raises(AnalyticsError, match="before the experiment ran"):
        evaluate_experiment(
            result_id="res-x", specification=spec, comparison=late,
            observation_ids=("c-apv",), interpretation="Looks better at 30 days.",
            reviewed_on=dt.date(2026, 9, 10),
        )


def test_the_verdict_is_deterministic(observations):
    first = a_result(observations)
    second = a_result(observations)
    assert first.to_dict() == second.to_dict()


def test_a_result_that_does_not_support_the_hypothesis_says_so(control, variant):
    at = dt.timedelta(hours=20)
    down = (
        observe("c-apv", control, "average_percentage_viewed", 0.55, control.published_at + at,
                a_provenance(), a_scope(), denominator_value=42.0),
        observe("v-apv", variant, "average_percentage_viewed", 0.40, variant.published_at + at,
                a_provenance(), a_scope(), denominator_value=42.0),
    )
    spec = a_specification(minimum_sample=2)
    result = a_result(down, spec)
    assert result.verdict is Verdict.DOES_NOT_SUPPORT
    assert result.causal_claim_supported is False


# --------------------------------------------------------------------------
# Baselines: named populations, explicit exclusions
# --------------------------------------------------------------------------


def a_population(count: int = 6) -> tuple[tuple[AnalyzedDeliverable, ...], tuple[MetricObservation, ...]]:
    deliverables, observations = [], []
    for index in range(count):
        deliverable = a_deliverable(
            f"race-short-{index:03d}",
            published_at=dt.datetime(2026, 8, 1 + index, 12, 0, tzinfo=UTC),
            features=ContentFeatures.from_labels(
                {FeatureDimension.HOOK_TYPE: "cold_open" if index % 2 else "slow_reveal"}
            ),
        )
        deliverables.append(deliverable)
        observations.append(
            observe(f"obs-{index:03d}", deliverable, "views", 1000.0 + index * 100,
                    deliverable.published_at + dt.timedelta(hours=20), a_provenance(), a_scope())
        )
    return tuple(deliverables), tuple(observations)


def test_a_baseline_names_its_population():
    deliverables, observations = a_population()
    baseline = build_baseline(
        baseline_id="baseline-race-short-aug",
        population="the six Race Shorts published in August 2026",
        member_ids=[d.deliverable_id for d in deliverables],
        published_range=DateRange(dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
        window=FIRST_24H,
        metrics=[DEFAULT_REGISTRY.get("views")],
        observations=observations,
    )
    assert baseline.size == 6
    assert len(baseline.member_ids) == 6
    assert baseline.get("views").median == 1250.0
    assert "2026-08-01..2026-08-31" in baseline.limitation


def test_a_baseline_without_members_is_refused():
    with pytest.raises(AnalyticsError, match="remembered normal"):
        build_baseline(
            baseline_id="b", population="the usual", member_ids=[],
            published_range=DateRange(dt.date(2026, 8, 1), dt.date(2026, 8, 31)),
            window=FIRST_24H, metrics=[], observations=[],
        )


def test_a_member_with_no_reading_is_counted_not_dropped():
    deliverables, observations = a_population()
    summary = summarise_metric(
        DEFAULT_REGISTRY.get("views"),
        [d.deliverable_id for d in deliverables] + ["race-short-099"],
        observations,
        FIRST_24H,
    )
    assert summary.count == 6
    assert summary.missing_members == ("race-short-099",)
    assert summary.coverage == "6 of 7 member(s) measured"


def test_outliers_are_surfaced_but_not_silently_removed():
    deliverables, observations = a_population()
    extreme = a_deliverable("race-short-099",
                            published_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=UTC))
    observations = observations + (
        observe("obs-099", extreme, "views", 900000.0,
                extreme.published_at + dt.timedelta(hours=20), a_provenance(), a_scope()),
    )
    members = [d.deliverable_id for d in deliverables] + ["race-short-099"]

    summary = summarise_metric(DEFAULT_REGISTRY.get("views"), members, observations, FIRST_24H)
    assert "race-short-099" in summary.outlier_ids
    assert summary.excluded_ids == ()
    assert summary.count == 7, "the outlier is still in the statistics"


def test_removing_an_outlier_requires_an_explicit_written_rule():
    deliverables, observations = a_population()
    extreme = a_deliverable("race-short-099",
                            published_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=UTC))
    observations = observations + (
        observe("obs-099", extreme, "views", 900000.0,
                extreme.published_at + dt.timedelta(hours=20), a_provenance(), a_scope()),
    )
    members = [d.deliverable_id for d in deliverables] + ["race-short-099"]

    rule = OutlierRule(
        method=OutlierMethod.EXPLICIT_IDS,
        rationale="A re-upload double-counted this Short's first day in the export.",
        excluded_ids=("race-short-099",),
    )
    summary = summarise_metric(
        DEFAULT_REGISTRY.get("views"), members, observations, FIRST_24H, outlier_rule=rule
    )
    assert summary.excluded_ids == ("race-short-099",)
    assert summary.count == 6
    assert "re-upload double-counted" in summary.to_dict()["exclusion_rule"]["statement"]
    assert any("re-upload" in c for c in summary.caveats)


def test_an_exclusion_with_no_rule_cannot_be_constructed():
    with pytest.raises(AnalyticsError, match="nobody can reproduce"):
        summary_type = __import__(
            "company.analytics.baseline", fromlist=["MetricSummary"]
        ).MetricSummary
        summary_type(
            metric=DEFAULT_REGISTRY.get("views"), count=1, mean=1.0, median=1.0,
            minimum=1.0, maximum=1.0, excluded_ids=("race-short-099",),
        )


def test_an_outlier_rule_needs_a_threshold_the_caller_supplied():
    with pytest.raises(AnalyticsError, match="does not choose one"):
        OutlierRule(method=OutlierMethod.IQR, rationale="Standard fence.")


def test_a_rate_summary_says_its_mean_is_unweighted():
    deliverable = a_deliverable("race-short-001")
    reading = observe("obs-ctr", deliverable, "click_through_rate", 0.06,
                      deliverable.published_at + dt.timedelta(hours=20),
                      a_provenance(), a_scope(), denominator_value=1000.0)
    summary = summarise_metric(
        DEFAULT_REGISTRY.get("click_through_rate"), ["race-short-001"], [reading], FIRST_24H
    )
    assert any("unweighted" in c for c in summary.caveats)
    assert any("impressions" in c for c in summary.caveats)


def test_analytics_refuses_to_aggregate_money():
    """Section 20: a mean revenue here would be a second total disagreeing with finance."""
    with pytest.raises(AnalyticsError, match="does not aggregate money"):
        summarise_metric(
            DEFAULT_REGISTRY.get("estimated_revenue"), ["race-short-001"], [], FIRST_24H
        )


# --------------------------------------------------------------------------
# Grouping: association, never ranking, never inference
# --------------------------------------------------------------------------


def test_grouping_uses_only_explicitly_recorded_tags():
    deliverables, observations = a_population()
    grouped = group_performance(
        GroupBy.HOOK_TYPE, deliverables, observations, [DEFAULT_REGISTRY.get("views")],
        FIRST_24H, minimum_group_size=2,
    )
    assert [g.value for g in grouped.groups] == ["cold_open", "slow_reveal"]
    assert grouped.sizes == {"cold_open": 3, "slow_reveal": 3}


def test_an_untagged_deliverable_goes_to_untagged_not_a_default_bucket():
    deliverables, observations = a_population()
    untagged = a_deliverable("race-short-099",
                             published_at=dt.datetime(2026, 8, 20, 12, 0, tzinfo=UTC))
    grouped = group_performance(
        GroupBy.HOOK_TYPE, list(deliverables) + [untagged], observations,
        [DEFAULT_REGISTRY.get("views")], FIRST_24H, minimum_group_size=2,
    )
    assert grouped.untagged == ("race-short-099",)
    assert "race-short-099" not in {m for g in grouped.groups for m in g.member_ids}
    assert any("carry no hook_type tag" in c for c in grouped.caveats)


def test_a_group_is_never_ranked_and_never_scored():
    deliverables, observations = a_population()
    grouped = group_performance(
        GroupBy.HOOK_TYPE, deliverables, observations, [DEFAULT_REGISTRY.get("views")],
        FIRST_24H, minimum_group_size=2,
    )
    assert [g.value for g in grouped.groups] == sorted(g.value for g in grouped.groups)
    text = json.dumps(grouped.to_dict()).lower()
    for banned in ("winner", "best", "worst", "rank", "score"):
        assert banned not in text, banned


def test_every_grouping_carries_the_association_note():
    deliverables, observations = a_population()
    grouped = group_performance(
        GroupBy.FORMAT_ID, deliverables, observations, [DEFAULT_REGISTRY.get("views")],
        FIRST_24H, minimum_group_size=2,
    )
    assert "association, not causation" in grouped.association_note
    assert grouped.association_note in grouped.caveats


def test_a_group_below_the_minimum_size_says_so():
    deliverables, observations = a_population(count=2)
    grouped = group_performance(
        GroupBy.HOOK_TYPE, deliverables, observations, [DEFAULT_REGISTRY.get("views")],
        FIRST_24H,
    )
    for group in grouped.groups:
        assert any("word median in front of it" in c for c in group.caveats)


def test_a_title_is_never_read_as_a_feature():
    """Structural: ContentFeatures takes tags, and a title is not one."""
    titled = a_deliverable("race-short-100", title="Cold open switchyard chaos!")
    assert titled.features.labels == ()
    assert group_value(titled, GroupBy.HOOK_TYPE) is None
    with pytest.raises(AnalyticsError, match="unknown feature dimension"):
        ContentFeatures.from_labels({"title": "cold_open"})
    with pytest.raises(AnalyticsError, match="mapping of dimension to tag"):
        ContentFeatures.from_labels("Cold open switchyard chaos!")


def test_no_module_reads_a_title_for_analysis():
    """The grep that stops a future convenience helper opening the door."""
    allowed = {
        "deliverable.py",  # declares and validates the field
        "__init__.py",     # package docstring explains why
        "genome.py",       # docstring explains why
        "README.md",
    }
    pattern = re.compile(r"\.title\b|\btitle\s*=|\[.title.\]")
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name in allowed:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            assert not pattern.search(line), f"{path.name}:{number} reads a title: {line.strip()}"


def test_feature_dimensions_are_closed():
    assert len(ALL_DIMENSIONS) == 8
    with pytest.raises(AnalyticsError, match="dimensions are closed"):
        ContentFeatures.from_labels({"hook": "cold_open"})


def test_a_tag_is_normalised_shape_so_two_spellings_cannot_be_two_groups():
    with pytest.raises(AnalyticsError, match="grouping keys"):
        ContentFeatures.from_labels({FeatureDimension.HOOK_TYPE: "Cold Open"})


def test_missing_dimensions_are_reported():
    features = ContentFeatures.from_labels({FeatureDimension.HOOK_TYPE: "cold_open"})
    assert FeatureDimension.HOOK_TYPE not in features.missing_dimensions
    assert FeatureDimension.AUDIO_STYLE in features.missing_dimensions
    assert len(features.missing_dimensions) == 7


# --------------------------------------------------------------------------
# Postmortem: no failed video without learning
# --------------------------------------------------------------------------


def a_postmortem(**kwargs) -> DeliverablePostmortem:
    defaults = dict(
        postmortem_id="pm-014",
        deliverable_id="race-short-014",
        outcome=DeliverableOutcome.BELOW_EXPECTATION,
        expected="The hook lab predicted first-day APV above 0.50.",
        observation_ids=("v-apv",),
        what_worked=("The switchyard read clearly on a phone.",),
        what_failed=("APV came in at 0.47, below the 0.50 the lab predicted.",),
        written_on=dt.date(2026, 9, 10),
        author="MGI",
        next_hypothesis_id="hyp-002",
    )
    defaults.update(kwargs)
    return DeliverablePostmortem(**defaults)


def test_a_failed_video_still_produces_learning():
    postmortem = a_postmortem()
    assert postmortem.outcome is DeliverableOutcome.BELOW_EXPECTATION
    assert postmortem.is_disappointment
    assert postmortem.next_hypothesis_id == "hyp-002"
    assert "hypothesis hyp-002" in postmortem.summary_line()


def test_a_postmortem_with_neither_learning_nor_hypothesis_is_refused():
    with pytest.raises(AnalyticsError, match="taught nothing"):
        a_postmortem(next_hypothesis_id="", durable_learning_id="")


def test_a_postmortem_must_name_its_evidence():
    with pytest.raises(EvidenceRequired, match="recollection"):
        a_postmortem(observation_ids=(), experiment_result_ids=())


def test_a_below_expectation_outcome_must_say_what_went_wrong():
    with pytest.raises(AnalyticsError, match="silence is not"):
        a_postmortem(what_failed=(), unresolved_questions=())


def test_a_postmortem_separates_theories_from_findings():
    """`not_supported_by_evidence` is where the plausible-but-unevidenced goes."""
    postmortem = a_postmortem(
        not_supported_by_evidence=(
            "The thumbnail may have been the real problem - nothing measured says so.",
        ),
    )
    assert postmortem.not_supported_by_evidence
    assert "thumbnail" not in " ".join(postmortem.what_failed)


def test_a_postmortem_compares_expectation_with_result():
    """Section 21: the pre-video expectation is quoted, not recomputed."""
    research = ResearchReference(
        kind=ResearchRecordKind.VIDEO_INTELLIGENCE_DOSSIER,
        record_ids=("dossier-hook-01",),
        expectation="Cold opens held 12 points more APV across the sampled channels.",
    )
    postmortem = a_postmortem(research_refs=(research,))
    assert postmortem.research_refs[0].expectation.startswith("Cold opens held")
    assert postmortem.expected != postmortem.research_refs[0].expectation


# --------------------------------------------------------------------------
# Learning and hypotheses
# --------------------------------------------------------------------------


def a_learning(**kwargs) -> AnalyticsLearning:
    defaults = dict(
        learning_id="learn-001",
        statement="A cold open holds more of the first day on Race Shorts.",
        scope=LearningScope.ONE_FORMAT,
        strength=EvidenceStrength.WEAK,
        what_would_overturn=("A matched pair at the same window showing no APV difference.",),
        created_on=dt.date(2026, 9, 10),
        evidence=(an_evidence(),),
        observation_ids=("v-apv",),
    )
    defaults.update(kwargs)
    return AnalyticsLearning(**defaults)


def test_a_learning_requires_evidence():
    with pytest.raises(EvidenceRequired, match="house style"):
        a_learning(evidence=())


def test_a_learning_must_cite_records_not_only_a_document():
    with pytest.raises(EvidenceRequired, match="claim about a document"):
        a_learning(observation_ids=(), result_ids=(), postmortem_ids=())


def test_a_learning_must_say_what_would_overturn_it():
    with pytest.raises(AnalyticsError, match="never rechecked"):
        a_learning(what_would_overturn=())


def test_a_single_observation_cannot_support_a_universal_claim():
    """Section 24, in the shape it actually arrives in."""
    with pytest.raises(OverclaimRefused, match="narrow the scope"):
        a_learning(
            scope=LearningScope.ALL_FORMATS,
            strength=EvidenceStrength.SINGLE_OBSERVATION,
        )
    narrow = a_learning(
        scope=LearningScope.ONE_DELIVERABLE, strength=EvidenceStrength.SINGLE_OBSERVATION
    )
    assert narrow.scope is LearningScope.ONE_DELIVERABLE


@pytest.mark.parametrize(
    "scope,strength,allowed",
    [
        (LearningScope.ONE_DELIVERABLE, EvidenceStrength.SINGLE_OBSERVATION, True),
        (LearningScope.ONE_FORMAT, EvidenceStrength.SINGLE_OBSERVATION, False),
        (LearningScope.FORMAT_FAMILY, EvidenceStrength.WEAK, False),
        (LearningScope.ALL_FORMATS, EvidenceStrength.MODERATE, False),
        (LearningScope.ALL_FORMATS, EvidenceStrength.STRONG, True),
    ],
)
def test_scope_is_paired_with_evidence_strength(scope, strength, allowed):
    if allowed:
        assert a_learning(scope=scope, strength=strength).scope is scope
    else:
        with pytest.raises(OverclaimRefused):
            a_learning(scope=scope, strength=strength)


def test_a_learning_cannot_claim_causation_without_a_result():
    with pytest.raises(OverclaimRefused, match="established by a design"):
        a_learning(causal_claim=True)


def test_a_qualified_statement_carries_its_scope_and_strength():
    learning = a_learning()
    assert "[one_format, weak evidence, association]" in learning.qualified_statement


def test_the_hypothesis_lifecycle_moves_only_along_declared_transitions():
    hypothesis = AnalyticsHypothesis(
        hypothesis_id="hyp-001",
        statement="A cold open raises first-day APV.",
        rationale="The hook lab found the drop is in the first three seconds.",
        proposed_on=dt.date(2026, 9, 1),
        owner="MGI",
    )
    assert hypothesis.state is HypothesisState.PROPOSED

    with pytest.raises(AnalyticsError, match="not a legal transition"):
        hypothesis.transition(HypothesisState.SUPPORTED)

    testing = hypothesis.transition(HypothesisState.TESTING, experiment_ids=("exp-cold-open",))
    assert testing.state is HypothesisState.TESTING

    superseded = testing.transition(HypothesisState.SUPERSEDED)
    assert superseded.state.is_settled
    with pytest.raises(AnalyticsError, match="not a legal transition"):
        superseded.transition(HypothesisState.TESTING)


def test_a_hypothesis_cannot_be_marked_supported_by_hand():
    with pytest.raises(OverclaimRefused, match="goes through promote"):
        AnalyticsHypothesis(
            hypothesis_id="hyp-001",
            statement="A cold open raises first-day APV.",
            rationale="Because it feels right.",
            proposed_on=dt.date(2026, 9, 1),
            owner="MGI",
            state=HypothesisState.SUPPORTED,
        )


def test_promotion_requires_a_supporting_result(observations):
    hypothesis = AnalyticsHypothesis(
        hypothesis_id="hyp-001",
        statement="A cold open raises first-day APV on Race Shorts.",
        rationale="The hook lab found the drop is in the first three seconds.",
        proposed_on=dt.date(2026, 9, 1),
        owner="MGI",
    ).transition(HypothesisState.TESTING, experiment_ids=("exp-cold-open",))

    inconclusive = a_result(observations, a_specification(minimum_sample=50))
    with pytest.raises(OverclaimRefused, match="as hypothetical as it was"):
        promote(hypothesis, inconclusive, "learn-001", LearningScope.ONE_FORMAT,
                EvidenceStrength.WEAK, ("A matched pair showing no difference.",),
                dt.date(2026, 9, 10))

    supporting = a_result(observations)
    promoted, learning = promote(
        hypothesis, supporting, "learn-001", LearningScope.ONE_FORMAT,
        EvidenceStrength.WEAK, ("A matched pair showing no difference.",),
        dt.date(2026, 9, 10),
    )
    assert promoted.state is HypothesisState.SUPPORTED
    assert promoted.result_ids == ("res-cold-open-1",)
    assert learning.source_hypothesis_id == "hyp-001"
    assert learning.causal_claim is False, "an uncontrolled result cannot promote to causation"
    assert any("assignment was not controlled" in l for l in learning.limitations)


def test_a_promoted_learning_inherits_the_results_caveats(observations):
    hypothesis = AnalyticsHypothesis(
        hypothesis_id="hyp-001",
        statement="A cold open raises first-day APV on Race Shorts.",
        rationale="The hook lab.",
        proposed_on=dt.date(2026, 9, 1),
        owner="MGI",
    ).transition(HypothesisState.TESTING, experiment_ids=("exp-cold-open",))
    _, learning = promote(
        hypothesis, a_result(observations), "learn-001", LearningScope.ONE_FORMAT,
        EvidenceStrength.WEAK, (), dt.date(2026, 9, 10),
    )
    assert learning.what_would_overturn, "falls back to the result's own falsifiers"
    assert learning.observation_ids


# --------------------------------------------------------------------------
# References: boundaries that carry no arithmetic
# --------------------------------------------------------------------------


def test_a_finance_reference_carries_no_money():
    reference = FinanceReference(
        kind=FinanceRecordKind.DELIVERABLE_ECONOMICS,
        record_ids=("econ-race-short-014",),
        note="Cost and revenue for this Short.",
    )
    fields = {f.name for f in dataclasses.fields(FinanceReference)}
    assert fields == {"kind", "record_ids", "note"}
    text = json.dumps(reference.to_dict()).lower()
    for banned in ("amount", "currency", "total", "margin", "profit"):
        assert banned not in text, banned


def test_analytics_imports_no_finance_research_or_usage_module():
    """The reference-only boundary, proved from the import graph."""
    forbidden = re.compile(
        r"^\s*(from|import)\s+(company\.finance|company\.org_intelligence|"
        r"company\.workforce|intelligence|ai_platform\.usage)\b",
        re.MULTILINE,
    )
    for path in sorted(PACKAGE.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not forbidden.search(source), f"{path.name} imports across a reference boundary"


def test_a_reference_must_name_at_least_one_record():
    with pytest.raises(AnalyticsError, match="not evidence of anything"):
        FinanceReference(kind=FinanceRecordKind.COST_RECORD, record_ids=())
    with pytest.raises(AnalyticsError, match="not evidence of anything"):
        ResearchReference(kind=ResearchRecordKind.OPPORTUNITY_DOSSIER, record_ids=())
    with pytest.raises(AnalyticsError, match="at least one record"):
        ExecutionReference(kind=ExecutionRecordKind.SESSION_RECEIPT, record_ids=())


def test_an_execution_reference_carries_no_counts():
    reference = ExecutionReference(
        kind=ExecutionRecordKind.RESOURCE_USAGE_RECORD, record_ids=("usage-0007",)
    )
    fields = {f.name for f in dataclasses.fields(ExecutionReference)}
    assert fields == {"kind", "record_ids", "note"}
    for banned in ("tokens", "retries", "minutes", "expansions"):
        assert banned not in json.dumps(reference.to_dict()).lower()


def test_a_money_metric_is_observable_but_never_aggregated():
    """Section 2 allows revenue as an observation; section 20 keeps the maths in finance."""
    assert DEFAULT_REGISTRY.get("estimated_revenue").kind is MetricKind.MONEY
    with pytest.raises(AnalyticsError, match="does not aggregate money"):
        summarise_metric(DEFAULT_REGISTRY.get("estimated_revenue"), ["x"], [], FIRST_24H)


# --------------------------------------------------------------------------
# Store: append-only and deterministic
# --------------------------------------------------------------------------


def test_the_store_refuses_a_silent_overwrite(tmp_path, variant):
    store = AnalyticsStore(tmp_path / "state")
    reading = observe("obs-1", variant, "views", 1000.0,
                      dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(), a_scope())
    store.put(reading)

    store.put(reading)  # byte-identical replay is a no-op

    revised = observe("obs-1", variant, "views", 2000.0,
                      dt.datetime(2026, 9, 9, tzinfo=UTC), a_provenance(), a_scope())
    with pytest.raises(LedgerViolation, match="append-only"):
        store.put(revised)
    assert store.get("observation", "obs-1").value == 1000.0


def test_a_later_reading_is_a_new_record_not_an_edit(tmp_path, variant):
    store = AnalyticsStore(tmp_path / "state")
    for label, hours, value in (("1h", 1, 500.0), ("24h", 20, 4000.0), ("30d", 700, 90000.0)):
        store.put(
            observe(f"obs-{label}", variant, "views", value,
                    variant.published_at + dt.timedelta(hours=hours), a_provenance(), a_scope())
        )
    assert store.ids("observation") == ("obs-1h", "obs-24h", "obs-30d")
    assert [o.value for o in store.observations_for("race-short-014")] == [500.0, 4000.0, 90000.0]


def test_the_ledger_records_every_observation_in_arrival_order(tmp_path, variant):
    store = AnalyticsStore(tmp_path / "state")
    for index in range(3):
        store.put(
            observe(f"obs-{index}", variant, "views", float(index),
                    variant.published_at + dt.timedelta(hours=index + 1),
                    a_provenance(), a_scope())
        )
    ledger = store.ledger()
    assert [entry["record_id"] for entry in ledger] == ["obs-0", "obs-1", "obs-2"]
    assert all(entry["kind"] == "observation" for entry in ledger)
    assert all(entry["fingerprint"] for entry in ledger)


def test_serialisation_is_deterministic_and_round_trips(tmp_path, control, variant, observations):
    store = AnalyticsStore(tmp_path / "state")
    specification = a_specification()
    result = a_result(observations, specification)
    store.put_all([control, variant, *observations, specification, result])

    again = AnalyticsStore(tmp_path / "state")
    assert again.get("observation", "c-apv").to_dict() == observations[0].to_dict()
    assert again.get("experiment", "exp-cold-open").to_dict() == specification.to_dict()
    assert again.get("result", "res-cold-open-1").to_dict() == result.to_dict()
    assert again.get("deliverable", "race-short-014").to_dict() == variant.to_dict()


def test_the_store_needs_an_explicit_directory():
    with pytest.raises(Exception, match="explicit non-empty path"):
        AnalyticsStore("   ")


def test_an_unknown_record_type_names_what_is_storable(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    with pytest.raises(Exception, match="not a storable analytics record"):
        store.put(object())


# --------------------------------------------------------------------------
# Integrity: what one record cannot see about another
# --------------------------------------------------------------------------


def test_two_values_for_the_same_snapshot_are_a_contradiction(tmp_path, variant):
    store = AnalyticsStore(tmp_path / "state")
    store.put(variant)
    at = dt.datetime(2026, 9, 9, tzinfo=UTC)
    store.put(observe("obs-a", variant, "views", 1000.0, at, a_provenance(), a_scope()))
    store.put(observe("obs-b", variant, "views", 1700.0, at, a_provenance(), a_scope()))

    problems = check_integrity(store)
    assert any("different values recorded for the same metric" in p for p in problems)
    assert any("obs-a, obs-b" in p for p in problems)


def test_a_learning_citing_a_missing_result_is_reported(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_learning(result_ids=("res-nowhere",), observation_ids=()))
    assert any("cannot be rechecked" in p for p in check_integrity(store))


def test_a_hypothesis_supported_by_a_non_supporting_result_is_reported(
    tmp_path, control, variant, observations
):
    store = AnalyticsStore(tmp_path / "state")
    weak = a_result(observations, a_specification(minimum_sample=50))
    assert weak.verdict is Verdict.INSUFFICIENT_EVIDENCE

    hypothesis = AnalyticsHypothesis(
        hypothesis_id="hyp-001",
        statement="A cold open raises first-day APV.",
        rationale="The hook lab.",
        proposed_on=dt.date(2026, 9, 1),
        owner="MGI",
        state=HypothesisState.SUPPORTED,
        experiment_ids=("exp-cold-open",),
        result_ids=("res-cold-open-1",),
    )
    store.put_all([control, variant, *observations, a_specification(minimum_sample=50),
                   weak, hypothesis])
    assert any("no result it cites" in p for p in check_integrity(store))


def test_a_clean_store_reports_nothing(tmp_path, control, variant, observations):
    store = AnalyticsStore(tmp_path / "state")
    store.put_all([control, variant, *observations, a_specification(), a_result(observations)])
    assert check_integrity(store) == ()


def test_the_construction_enforced_table_is_accurate():
    """Every row names a real exception type exported from the package."""
    assert len(CONSTRUCTION_ENFORCED) >= 6
    for description, exception in CONSTRUCTION_ENFORCED:
        assert isinstance(description, str) and description.strip()
        assert issubclass(exception, Exception)


# --------------------------------------------------------------------------
# Report: concise, deterministic, no score
# --------------------------------------------------------------------------


def a_full_store(tmp_path, control, variant, observations) -> AnalyticsStore:
    store = AnalyticsStore(tmp_path / "state")
    specification = a_specification(status=ExperimentStatus.OBSERVING)
    store.put_all([control, variant, *observations, specification,
                   a_result(observations, specification)])
    store.put(
        AnalyticsHypothesis(
            hypothesis_id="hyp-002",
            statement="A shorter race raises completion on mobile.",
            rationale="The pacing lab suggested the middle third is where viewers leave.",
            proposed_on=dt.date(2026, 9, 10),
            owner="MGI",
        )
    )
    store.put(a_learning())
    return store


def test_the_report_answers_the_seven_questions(tmp_path, control, variant, observations):
    store = a_full_store(tmp_path, control, variant, observations)
    report = build_report(store, dt.date(2026, 9, 10))

    assert report.deliverable_count == 2 and report.observation_count == 6
    assert report.coverage
    assert any("hook_type" in v for v in report.variables_changed)
    assert any("exp-cold-open" in e for e in report.active_experiments)
    assert any("exp-cold-open" in r for r in report.completed_results)
    assert report.learnings
    assert any("hyp-002" in n for n in report.next_to_test)
    assert report.not_concluded


def test_the_report_surfaces_a_supported_hypothesis_with_no_causal_claim(
    tmp_path, control, variant, observations
):
    """The distinction most likely to be lost, kept on the page."""
    store = a_full_store(tmp_path, control, variant, observations)
    report = build_report(store, dt.date(2026, 9, 10))
    assert any(
        "supports_hypothesis, but no causal claim" in item for item in report.not_concluded
    )


def test_the_report_is_deterministic(tmp_path, control, variant, observations):
    store = a_full_store(tmp_path, control, variant, observations)
    first = build_report(store, dt.date(2026, 9, 10))
    second = build_report(store, dt.date(2026, 9, 10))
    assert first.to_dict() == second.to_dict()
    assert first.render() == second.render()


def test_the_report_is_concise_and_caps_its_lists(tmp_path, variant):
    store = AnalyticsStore(tmp_path / "state")
    store.put(variant)
    for index in range(40):
        store.put(
            observe(f"obs-{index:03d}", variant, "views", float(index),
                    variant.published_at + dt.timedelta(hours=index + 1),
                    a_provenance(), a_scope())
        )
    report = build_report(store, dt.date(2026, 9, 10))
    serialised = report.to_dict()
    assert serialised["measured"]["observations"] == 40
    assert len(json.dumps(serialised)) < 20_000, "a report is a page, not a dump"
    assert "obs-017" not in json.dumps(serialised), "raw observations do not reach the page"


def test_the_report_reports_missing_coverage(tmp_path, control, variant, observations):
    store = AnalyticsStore(tmp_path / "state")
    lonely = a_deliverable("race-short-099",
                           published_at=dt.datetime(2026, 9, 2, 12, 0, tzinfo=UTC))
    store.put_all([control, variant, lonely, *observations])
    report = build_report(store, dt.date(2026, 9, 10))
    views = next(c for c in report.coverage if c.metric == "views")
    assert "race-short-099" in views.deliverables_missing


# --------------------------------------------------------------------------
# No score, anywhere
# --------------------------------------------------------------------------


_SCORE_SHAPED = re.compile(
    r"(^|_)(score|rating|grade|rank|ranking|index|winner|best|worst|overall|composite)($|_)"
)

_RECORD_TYPES = [
    AnalyzedDeliverable, MetricObservation, MetricDefinition, ExperimentSpecification,
    ExperimentResult, CausalAssessment, DeliverablePostmortem, AnalyticsLearning,
    AnalyticsHypothesis, FinanceReference, ResearchReference, ExecutionReference,
    CompetitorPublicReference, Variable, Expectation, KillCondition, OutlierRule,
]


@pytest.mark.parametrize("record_type", _RECORD_TYPES, ids=lambda t: t.__name__)
def test_no_record_carries_a_score_shaped_field(record_type):
    """Section 26 and constitution rule 3, enforced against the next helper too."""
    for field in dataclasses.fields(record_type):
        assert not _SCORE_SHAPED.search(field.name), f"{record_type.__name__}.{field.name}"


def test_no_module_defines_a_global_content_score():
    pattern = re.compile(
        r"def\s+\w*(score|rank|rating|grade)\w*\s*\(|"
        r"^\s*(content|video|format|channel|quality)_score\s*[:=]",
        re.MULTILINE | re.IGNORECASE,
    )
    for path in sorted(PACKAGE.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not pattern.search(source), f"{path.name} defines a score"


# --------------------------------------------------------------------------
# Boundaries: production isolation and dependencies
# --------------------------------------------------------------------------


_PRODUCTION_PACKAGES = (
    "race2", "sloped", "marble3d", "engine", "modes", "powers", "godot",
    "production", "rendering", "replay", "race", "entities", "audio", "tools",
)


def test_analytics_imports_no_production_module():
    pattern = re.compile(
        r"^\s*(from|import)\s+(" + "|".join(_PRODUCTION_PACKAGES) + r")\b", re.MULTILINE
    )
    for path in sorted(PACKAGE.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert not pattern.search(source), f"{path.name} imports production"


def test_no_production_module_imports_analytics():
    pattern = re.compile(r"^\s*(from|import)\s+company\.analytics\b", re.MULTILINE)
    for package in _PRODUCTION_PACKAGES:
        root = REPO_ROOT / package
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            assert not pattern.search(path.read_text(encoding="utf-8")), path


def test_analytics_uses_only_the_standard_library_and_company_os():
    """No new dependency. Everything imported is stdlib or already in the tree.

    The four roots the Studio import added - csv, decimal, hashlib, io - are all
    standard library. Read from the syntax tree rather than matched line by
    line, because a docstring sentence beginning "from opposite sides" is not an
    import, and a pattern that cannot tell the difference fails on prose.
    """
    allowed_roots = {
        "__future__", "ai_platform", "collections", "company", "csv", "dataclasses",
        "datetime", "decimal", "enum", "hashlib", "io", "json", "knowledge",
        "pathlib", "re", "statistics", "typing", "argparse", "sys", "abc", "math",
        "itertools", "functools",
    }
    for path in sorted(PACKAGE.glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert roots <= allowed_roots, f"{path.name} imports {sorted(roots)}"


def test_the_only_company_os_imports_are_the_two_shared_utilities():
    """Keeps the org-intelligence -> analytics capsule edge acyclic."""
    pattern = re.compile(r"^\s*from\s+company\.([\w.]+)\s+import", re.MULTILINE)
    seen = set()
    for path in sorted(PACKAGE.glob("*.py")):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            seen.add(match.group(1))
    assert seen <= {"runtime.state_paths", "validation.errors"}, seen


def test_no_subagent_machinery_appears_anywhere():
    """The bootstrap invariant, untouched by this phase."""
    pattern = re.compile(r"subagent|spawn_agent|child_agent|nested_delegation", re.IGNORECASE)
    for path in sorted(PACKAGE.glob("*.py")):
        assert not pattern.search(path.read_text(encoding="utf-8")), path.name


# --------------------------------------------------------------------------
# The capsule: size, reachability, and the dependency limit it must not break
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeds():
    from knowledge.company_os.capsules import SEED_ROOT, CapsuleIndex

    return CapsuleIndex.load(SEED_ROOT)


def test_the_analytics_capsule_is_within_budget(seeds):
    from knowledge.company_os.capsules import DEFAULT_BUDGET

    capsule = seeds.get("company-analytics-experiments")
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert capsule.owns_paths == ("company/analytics",)
    assert capsule.tests == (
        "tests/test_company_analytics.py",
        "tests/test_company_youtube_studio_ingestion.py",
    )


def test_the_capsule_is_cheaper_than_the_package_it_describes(seeds):
    """The whole point of a capsule, as a number."""
    package_chars = sum(
        len(path.read_text(encoding="utf-8")) for path in PACKAGE.glob("*.py")
    )
    assert package_chars / seeds.get("company-analytics-experiments").size_chars() >= 5


def test_the_control_plane_reaches_analytics_without_a_direct_dependency(seeds):
    """Section 28: the control plane is full at eight, so the edge is transitive."""
    control_plane = seeds.get("company-os-control-plane")
    assert len(control_plane.dependencies) <= 8
    assert "company-analytics-experiments" not in control_plane.dependencies

    closure = seeds.dependency_closure("company-os-control-plane")
    assert "company-analytics-experiments" in closure

    org = seeds.get("company-organizational-intelligence")
    assert "company-analytics-experiments" in org.dependencies
    assert "company/analytics/*.py" in org.may_read


def test_no_capsule_exceeds_the_dependency_limit(seeds):
    from knowledge.company_os.capsules import DEFAULT_BUDGET

    for capsule in seeds.all():
        assert len(capsule.dependencies) <= DEFAULT_BUDGET.max_list_items, capsule.id


def test_the_capsule_graph_has_no_cycle_through_analytics(seeds):
    """Analytics depends only on layers that cannot depend back on it."""
    analytics = seeds.get("company-analytics-experiments")
    assert analytics.dependencies == ("ai-platform", "company-knowledge-store")
    reachable = seeds.dependency_closure("company-analytics-experiments")
    assert "company-analytics-experiments" not in reachable
    assert "company-organizational-intelligence" not in reachable


def test_the_seed_index_is_internally_consistent(seeds):
    assert seeds.integrity() == ()
    assert "company-analytics-experiments" in seeds.ids()
