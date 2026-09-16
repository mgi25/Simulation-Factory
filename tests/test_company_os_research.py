"""Focused tests for the Company OS research & intelligence subsystem.

The invariants worth a test here are the ones prose alone would not hold, and
almost all of them are a refusal:

- research cannot claim a number it did not measure (`Measurement`), and cannot
  derive one from inputs it does not have (`derive`);
- research cannot become permanent (`ResearchConfidence`), because it observes
  a moving world;
- a competitor's private analytics are neither required nor reachable;
- a local copy cannot exist without someone having authorised it;
- a reference case cannot exist without an originality boundary (rule 8);
- a video idea cannot pass itself off as a repeatable format;
- a composite score cannot travel without its coverage and its caveat;
- the workflow cannot reach a stage whose artefact does not exist;
- the store cannot silently replace anything.

Plus the branch guards: no production import in either direction, no new
dependency, and rule 2 exactly where it was.
"""

from __future__ import annotations

import ast
import dataclasses
import datetime as dt
import inspect
from pathlib import Path

import pytest

from ai_platform import ExecutionPolicy, SubagentPolicyViolation
from ai_platform.references import ReferenceViolation
from ai_platform.serde import dumps
from company.validation.errors import ValidationError
from company.validation.no_subagents import enforce_no_subagents
from intelligence.research import (
    CAVEAT,
    KNOWN_MECHANICS,
    NEVER_KNOWABLE,
    AudioAnalysis,
    CameraEditAnalysis,
    Complexity,
    ConfidenceLevel,
    CoreLoop,
    DimensionScore,
    DossierStatus,
    Evidence,
    ExperimentDefinition,
    FormatAnalysis,
    FormatClass,
    FormatFamily,
    HookAnalysis,
    Measurement,
    OpportunityDossier,
    OpportunityScorecard,
    OpportunityStage,
    OriginalityBoundary,
    PublicMetrics,
    ReferenceCase,
    ResearchConfidence,
    ResearchError,
    ResearchSource,
    ResearchStage,
    ResearchStore,
    RightsStatus,
    ScoringDimension,
    ScoringRubric,
    SourceQuality,
    SourceType,
    SuperiorityTarget,
    TargetStatus,
    TechnicalAnalysis,
    VideoIntelligenceDossier,
    VideoPlan,
    ViewerPsychology,
    VisualAnalysis,
    advance_source,
    derive,
    link_opportunity,
    link_reference_case,
    observation_evidence,
    rank,
    score_opportunity,
)
from intelligence.research.store import DEFAULT_ROOT
from knowledge.company_os import Freshness

REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "intelligence"

TODAY = dt.date(2026, 9, 16)


# --------------------------------------------------------------------------
# Builders
# --------------------------------------------------------------------------


def an_evidence(**overrides) -> Evidence:
    data = dict(kind="observation", ref="https://example.invalid/watch?v=abc", note="watched")
    data.update(overrides)
    return Evidence(**data)


def a_confidence(**overrides) -> ResearchConfidence:
    data = dict(
        level=ConfidenceLevel.MODERATE,
        basis="Three viewings of the public video, plus its visible comment themes.",
        freshness=Freshness.TIME_SENSITIVE,
        observed_on=TODAY,
        would_change_if=("The channel stops publishing this format for two months.",),
        evidence=(an_evidence(),),
        source_quality=SourceQuality.PLATFORM_PUBLIC,
        limitations=("Public metrics only; retention is not visible to us.",),
    )
    data.update(overrides)
    return ResearchConfidence(**data)


def a_measurement(**overrides) -> Measurement:
    data = dict(
        value=2.5,
        unit="seconds",
        method="Frame-counted from the public upload at 30 fps.",
        evidence=an_evidence(kind="measurement", ref="docs/validation/ref/hook_count.md"),
    )
    data.update(overrides)
    return Measurement(**data)


def a_source(**overrides) -> ResearchSource:
    data = dict(
        id="yt-competitor-marble-run",
        platform="youtube",
        reference="https://example.invalid/watch?v=abc",
        title="A marble run with an elimination twist",
        source_type=SourceType.COMPETITOR_VIDEO,
        observed_on=TODAY,
        rights=RightsStatus.LINK_ONLY,
        confidence=a_confidence(),
        discovered_by="research_opportunity_lead",
        creator="Some Channel",
        published_on=dt.date(2026, 8, 1),
    )
    data.update(overrides)
    return ResearchSource(**data)


def a_reference_case(**overrides) -> ReferenceCase:
    data = dict(
        id="rc-elimination-marble-run",
        source_id="yt-competitor-marble-run",
        title="Elimination marble run, read for its loop",
        analyst="research_opportunity_lead",
        created=TODAY,
        hook=HookAnalysis(
            opening_image="Sixteen marbles already moving, filling the frame.",
            premise_comprehension="The rule is legible without narration: last one left wins.",
            viewer_commitment="A viewer picks a colour in the first two seconds.",
        ),
        core_loop=CoreLoop(
            prediction="Which marble survives the next gate?",
            event="A gate closes on a group.",
            consequence="The field shrinks and the odds visibly change.",
            renewed_prediction="The viewer re-picks from the survivors.",
        ),
        psychology=ViewerPsychology(
            curiosity="The gate mechanism is not explained before it fires.",
            identification="Colour choice stands in for a team; no named characters.",
            suspense="Each gate is a countdown the viewer can see coming.",
            uncertainty="Outcomes look physical rather than authored.",
            anticipation="The funnel geometry telegraphs the next elimination.",
            payoff="A single marble crosses alone, held on screen.",
        ),
        visual=VisualAnalysis(
            hierarchy="Marbles are the brightest objects; the track is desaturated.",
            color="Six saturated hues against a grey machine.",
            materials="Glossy marbles, matte track - separation by finish, not only hue.",
            readability="Readable at phone size because the marbles are large in frame.",
            environment="A single enclosed hall; no distant landscape.",
            depth="Depth comes from stacked track levels rather than aerial perspective.",
        ),
        camera_edit=CameraEditAnalysis(
            shot_style="Chase framing, roughly level with the leaders.",
            continuity="Screen direction is held across every cut.",
            anticipation="The camera leads the pack into each gate.",
            orientation="A wide re-establishing shot after every elimination.",
            pacing="Cuts land on events, not on a metronome.",
        ),
        audio=AudioAnalysis(
            feedback="Each impact is individually audible.",
            escalation="The bed rises as the field shrinks.",
            payoff="Everything drops out on the final crossing.",
        ),
        format=FormatAnalysis(
            repeatability="The same machine is reused across dozens of uploads.",
            variation_potential="Gate rules and marble count are the visible variables.",
        ),
        technical=TechnicalAnalysis(
            estimated_complexity=Complexity.MODERATE,
            basis="We have already built gates, chase cameras and a contained hall.",
            reusable_components=("chase camera rig", "contained stage lighting"),
            likely_risks=("Elimination fairness is easy to get wrong.",),
        ),
        originality=OriginalityBoundary(
            must_not_copy=(
                "The specific machine geometry and its on-screen branding.",
                "The channel's title and thumbnail conventions.",
            ),
            transferable_principles=(
                "A shrinking field renews the viewer's question without narration.",
                "Separating subject from set by finish, not only by hue.",
            ),
            rationale=(
                "The geometry is their expression; a shrinking field is a mechanism "
                "that predates the channel."
            ),
        ),
        confidence=a_confidence(),
        strengths=("The premise is legible in under two seconds.",),
        weaknesses=("The middle repeats itself once the field stops shrinking fast.",),
        extractable_principles=("Tie each cut to an elimination, not to a beat.",),
        mechanics=("race", "elimination"),
    )
    data.update(overrides)
    return ReferenceCase(**data)


def a_family(**overrides) -> FormatFamily:
    data = dict(
        family_id="elimination_race",
        reusable_core_loop="A shrinking field of marbles crossing successive gates.",
        variable_dimensions=("gate rule", "field size", "course topology"),
        variation_space="Gate rules times course topologies gives dozens of episodes.",
        audience_question="Which colour survives?",
        differentiation="Our gates are physical consequences rather than authored cuts.",
        reusable_systems=("sloped course generator", "chase camera rig"),
        estimated_episodes=24,
    )
    data.update(overrides)
    return FormatFamily(**data)


def a_target(**overrides) -> SuperiorityTarget:
    data = dict(
        dimension="hook_clarity",
        intent="The premise must be legible before the first cut.",
        status=TargetStatus.QUALITATIVE,
    )
    data.update(overrides)
    return SuperiorityTarget(**data)


def an_opportunity(**overrides) -> OpportunityDossier:
    data = dict(
        id="op-elimination-race",
        title="Elimination race as a second format family",
        statement="A marble race whose field shrinks at each gate.",
        author="research_opportunity_lead",
        created=TODAY,
        format_class=FormatClass.NEW_FORMAT_FAMILY,
        viewer_question="Which colour survives the next gate?",
        core_entertainment_loop="Pick a colour, watch a gate fire, re-pick.",
        channel_fit="It reuses the sloped course and the chase camera we already ship.",
        originality_path="Our gates are physical outcomes of the course, not editing.",
        repeatability="One machine, many gate rules.",
        differentiation="Nobody in the reference set derives eliminations from physics.",
        production_complexity=Complexity.MODERATE,
        complexity_basis="Gate geometry is new; the course, camera and lighting are not.",
        evidence=(an_evidence(),),
        limitations=("One reference channel observed; no audience data of our own.",),
        confidence=a_confidence(),
        family=a_family(),
        source_ids=("yt-competitor-marble-run",),
        reference_case_ids=("rc-elimination-marble-run",),
        superiority_targets=(a_target(),),
        technical_risks=("Fairness of the gate under our physics is unproven.",),
        content_risks=("The format could read as derivative if the gates look authored.",),
    )
    data.update(overrides)
    return OpportunityDossier(**data)


def a_rubric(**overrides) -> ScoringRubric:
    data = dict(
        id="test-rubric",
        version="1",
        purpose="A three-dimension rubric for the tests.",
        author="research_opportunity_lead",
        created=TODAY,
        dimensions=(
            ScoringDimension(name="viewer_loop_strength", weight=3.0),
            ScoringDimension(name="repeatability", weight=2.0),
            ScoringDimension(name="estimated_cost", weight=1.0, higher_is_better=False),
        ),
    )
    data.update(overrides)
    return ScoringRubric(**data)


def a_scorecard(**overrides) -> OpportunityScorecard:
    data = dict(
        id="sc-elimination-race",
        opportunity_id="op-elimination-race",
        rubric_id="test-rubric",
        scored_by="research_opportunity_lead",
        scored_on=TODAY,
        scores=(
            DimensionScore(dimension="viewer_loop_strength", score=4, reason="The field shrinks."),
            DimensionScore(dimension="repeatability", score=5, reason="One machine, many rules."),
            DimensionScore(dimension="estimated_cost", score=2, reason="Course and camera exist."),
        ),
    )
    data.update(overrides)
    return OpportunityScorecard(**data)


def a_video_dossier(**overrides) -> VideoIntelligenceDossier:
    data = dict(
        id="vid-elimination-pilot",
        video_id="elimination_pilot_01",
        format_family="elimination_race",
        objective="Test whether a shrinking field holds attention past the mid-point.",
        author="research_opportunity_lead",
        created=TODAY,
        known_weakness="V24's middle section loses churn between the fork and the merge.",
        hypothesis="An elimination at the mid-point renews the viewer's question.",
        plan=VideoPlan(
            hook="Sixteen marbles released into a visible funnel.",
            viewer_commitment="Colour separation inside the first second.",
            middle_rhythm="A gate every four seconds, each visibly telegraphed.",
            payoff="The last marble crosses alone, held for a full second.",
            visual="Locked style rules; marbles are the only saturated objects.",
            camera="Chase rig, screen direction held across every cut.",
            audio="Impacts individually audible; bed rises as the field shrinks.",
        ),
        experiment=ExperimentDefinition(
            question="Does a mid-point elimination raise churn in the second half?",
            predicted_observation="Churn in seconds 8-14 rises above the V24 baseline.",
            method="Compare churn per second against the V24 master on the same seed.",
            variables_changed=("gate_rule", "field_size"),
            variables_locked=("course_topology", "camera_rig", "lighting", "seed"),
        ),
        superiority_targets=(a_target(),),
        kill_conditions=(
            "Gate fairness varies by more than two points between colours over 600 seeds.",
            "The mid-point elimination is not readable at phone size.",
        ),
        confidence=a_confidence(),
        cost_estimate=Complexity.MODERATE,
        cost_basis="One new gate system; every other subsystem is reused.",
    )
    data.update(overrides)
    return VideoIntelligenceDossier(**data)


# --------------------------------------------------------------------------
# Sources, rights, and what we are never allowed to know
# --------------------------------------------------------------------------


def test_a_valid_source_needs_only_a_reference_and_an_observation_date():
    source = a_source(published_on=None, metrics=None)
    assert source.metrics is None
    assert source.stage is ResearchStage.DISCOVERED
    assert source.derived().views_per_day is None


def test_an_invalid_source_is_refused_on_id_reference_and_chronology():
    with pytest.raises(ResearchError):
        a_source(id="Not An Id")
    with pytest.raises(ReferenceViolation):
        a_source(reference="")
    with pytest.raises(ResearchError):
        a_source(published_on=TODAY + dt.timedelta(days=1))


def test_optional_public_metrics_stay_optional_all_the_way_down():
    bare = PublicMetrics(observed_on=TODAY)
    assert bare.present == ()
    assert set(bare.absent) == {
        "views",
        "likes",
        "comments",
        "duration_seconds",
        "channel_subscribers",
    }
    source = a_source(metrics=bare)
    assert dumps(source)  # a snapshot of nothing still round-trips
    assert ResearchSource.from_dict(
        __import__("json").loads(dumps(source))
    ).metrics.views is None


def test_a_negative_public_count_is_refused():
    with pytest.raises(ResearchError):
        PublicMetrics(observed_on=TODAY, views=-1)


def test_a_local_copy_requires_a_pointer_and_someone_who_authorised_it():
    with pytest.raises(ResearchError, match="local_copy_ref"):
        a_source(rights=RightsStatus.LOCAL_COPY_AUTHORIZED)
    with pytest.raises(ResearchError, match="rights_basis"):
        a_source(
            rights=RightsStatus.LOCAL_COPY_USER_PROVIDED,
            local_copy_ref="exports/reference/clip.mp4",
        )
    ok = a_source(
        rights=RightsStatus.LOCAL_COPY_USER_PROVIDED,
        local_copy_ref="exports/reference/clip.mp4",
        rights_basis="The CEO supplied the file on 2026-09-16.",
    )
    assert ok.holds_local_copy


def test_a_link_only_source_may_not_claim_a_local_file():
    """There is no status meaning 'we have the bytes and nobody said we could'."""
    with pytest.raises(ResearchError, match="holds no local copy"):
        a_source(rights=RightsStatus.LINK_ONLY, local_copy_ref="exports/reference/clip.mp4")
    with pytest.raises(ResearchError):
        a_source(rights=RightsStatus.METADATA_ONLY, local_copy_ref="exports/reference/clip.mp4")


def test_competitor_private_analytics_are_never_required_and_never_present():
    source = a_source()
    assert "audience_retention_curve" in source.private_analytics_unavailable
    assert "monetization_and_revenue" in source.private_analytics_unavailable

    metric_fields = {f.name for f in dataclasses.fields(PublicMetrics)}
    for forbidden in NEVER_KNOWABLE:
        assert forbidden not in metric_fields

    # ... and the whole record set is buildable without any of them.
    assert dumps(source)
    assert a_source(source_type=SourceType.OWN_VIDEO).private_analytics_unavailable == ()


def test_the_never_knowable_list_travels_inside_the_derived_object():
    derived = a_source().derived()
    assert derived.never_knowable == NEVER_KNOWABLE
    assert not hasattr(derived, "retention")


# --------------------------------------------------------------------------
# Derivation: missing data stays missing
# --------------------------------------------------------------------------


def test_derivation_computes_only_what_the_inputs_support():
    metrics = PublicMetrics(
        observed_on=dt.date(2026, 9, 11), views=100_000, likes=4_000, comments=250
    )
    derived = derive(metrics, dt.date(2026, 9, 1))
    assert derived.age_days == 10
    assert derived.views_per_day == 10_000.0
    assert derived.likes_per_1k_views == 40.0
    assert derived.comments_per_1k_views == 2.5
    assert derived.unavailable == ()


def test_no_fake_derived_metric_when_an_input_is_missing():
    metrics = PublicMetrics(observed_on=dt.date(2026, 9, 11), views=100_000)
    derived = derive(metrics, None)
    assert derived.age_days is None
    assert derived.views_per_day is None
    assert derived.likes_per_1k_views is None
    joined = " | ".join(derived.unavailable)
    assert "age_days: publication date unknown" in joined
    assert "views_per_day: age unknown" in joined
    assert "likes_per_1k_views: like count not observed" in joined
    assert set(derived.missing) == {
        "age_days",
        "views_per_day",
        "likes_per_1k_views",
        "comments_per_1k_views",
    }


def test_a_missing_snapshot_names_every_metric_it_could_not_derive():
    derived = derive(None, dt.date(2026, 9, 1))
    assert derived.computed == ()
    assert len(derived.unavailable) == 4
    assert all("no metrics snapshot" in reason for reason in derived.unavailable)


def test_zero_views_produce_no_ratio_rather_than_a_zero():
    metrics = PublicMetrics(observed_on=dt.date(2026, 9, 11), views=0, likes=0)
    derived = derive(metrics, dt.date(2026, 9, 1))
    assert derived.likes_per_1k_views is None
    assert any("zero views" in reason for reason in derived.unavailable)


def test_less_than_a_day_of_exposure_yields_no_rate():
    metrics = PublicMetrics(observed_on=dt.date(2026, 9, 1), views=5_000)
    derived = derive(metrics, dt.date(2026, 9, 1))
    assert derived.age_days == 0
    assert derived.views_per_day is None
    assert any("less than one full day" in reason for reason in derived.unavailable)


def test_derivation_is_a_property_of_the_snapshot_not_of_today():
    source = a_source(
        observed_on=dt.date(2026, 9, 11),
        metrics=PublicMetrics(observed_on=dt.date(2026, 9, 11), views=100_000),
        published_on=dt.date(2026, 9, 1),
    )
    assert source.derived() == source.derived()
    assert source.derived().views_per_day == 10_000.0


# --------------------------------------------------------------------------
# Confidence and limitations are first class
# --------------------------------------------------------------------------


def test_research_confidence_may_never_be_permanent():
    with pytest.raises(ResearchError, match="may not be permanent"):
        a_confidence(freshness=Freshness.PERMANENT)


def test_a_finding_must_name_what_would_overturn_it():
    with pytest.raises(ResearchError, match="would_change_if"):
        a_confidence(would_change_if=())


def test_confidence_above_weak_must_cite_something():
    with pytest.raises(ResearchError, match="no evidence"):
        a_confidence(level=ConfidenceLevel.STRONG, evidence=())
    assert a_confidence(level=ConfidenceLevel.WEAK, evidence=()).evidence == ()


def test_confidence_and_limitations_survive_a_round_trip(tmp_path):
    store = ResearchStore(tmp_path)
    source = a_source(
        confidence=a_confidence(
            limitations=("Public metrics only.", "One observation, one day."),
            contradictory_evidence=(an_evidence(note="A similar format underperformed."),),
            sample_size=3,
        )
    )
    store.add(source)
    back = store.get("source", source.id)
    assert back.confidence.limitations == source.confidence.limitations
    assert back.confidence.contradictory_evidence == source.confidence.contradictory_evidence
    assert back.confidence.sample_size == 3
    assert back.confidence.is_contested


def test_a_recheck_date_is_derived_from_the_freshness_class():
    confidence = a_confidence(freshness=Freshness.TIME_SENSITIVE)
    assert confidence.recheck_on == TODAY + dt.timedelta(days=30)


def test_a_sample_size_must_be_a_real_sample():
    with pytest.raises(ResearchError):
        a_confidence(sample_size=0)


# --------------------------------------------------------------------------
# A number needs evidence
# --------------------------------------------------------------------------


def test_a_measurement_without_evidence_cannot_be_built():
    with pytest.raises(ResearchError, match="requires an Evidence pointer"):
        Measurement(value=2.5, unit="seconds", method="counted", evidence=None)


def test_a_measurement_records_its_unit_and_method():
    m = a_measurement()
    assert m.unit == "seconds"
    assert m.method
    with pytest.raises(ResearchError):
        a_measurement(value="fast")


def test_no_record_exposes_a_bare_float_for_the_outside_world():
    """Every reference number is a Measurement, so none can be typed in blind."""
    for cls in (HookAnalysis, CoreLoop, CameraEditAnalysis, SuperiorityTarget):
        for field in dataclasses.fields(cls):
            annotation = str(field.type)
            assert "float" not in annotation, f"{cls.__name__}.{field.name}"


# --------------------------------------------------------------------------
# Reference cases
# --------------------------------------------------------------------------


def test_a_reference_case_requires_an_originality_boundary():
    with pytest.raises(ResearchError, match="must_not_copy"):
        a_reference_case(
            originality=OriginalityBoundary(
                must_not_copy=(),
                transferable_principles=("A shrinking field renews the question.",),
                rationale="Everything here is mechanism.",
            )
        )
    with pytest.raises(ResearchError, match="transferable_principles"):
        a_reference_case(
            originality=OriginalityBoundary(
                must_not_copy=("Their machine geometry.",),
                transferable_principles=(),
                rationale="Nothing to take.",
            )
        )


def test_a_reference_case_must_name_a_weakness():
    with pytest.raises(ResearchError, match="admiration"):
        a_reference_case(weaknesses=())


def test_every_psychology_lever_must_be_answered():
    with pytest.raises(ReferenceViolation, match="identification"):
        ViewerPsychology(
            curiosity="x",
            identification="",
            suspense="x",
            uncertainty="x",
            anticipation="x",
            payoff="x",
        )


def test_mechanics_tags_are_open_but_spelled_one_way():
    case = a_reference_case(mechanics=("race", "elimination", "tower_defence"))
    assert case.novel_mechanics == ("tower_defence",)
    assert set(KNOWN_MECHANICS) >= {"race", "fight", "survival"}
    with pytest.raises(ResearchError, match="snake_case"):
        a_reference_case(mechanics=("Tower Defence",))


def test_a_reference_measurement_is_optional_and_evidenced_when_present():
    plain = a_reference_case()
    assert plain.hook.seconds_to_premise is None
    measured = a_reference_case(
        hook=HookAnalysis(
            opening_image="Sixteen marbles already moving.",
            premise_comprehension="Legible without narration.",
            viewer_commitment="A viewer picks a colour immediately.",
            seconds_to_premise=a_measurement(),
        )
    )
    assert measured.hook.seconds_to_premise.evidence.ref


# --------------------------------------------------------------------------
# Opportunities: evidence, format family, superiority targets
# --------------------------------------------------------------------------


def test_an_opportunity_must_link_evidence():
    with pytest.raises(ResearchError, match="rule 7"):
        an_opportunity(evidence=())


def test_an_opportunity_must_state_its_limitations():
    with pytest.raises(ResearchError, match="limitations"):
        an_opportunity(limitations=())


def test_a_repeatable_format_must_describe_its_family():
    with pytest.raises(ResearchError, match="describes no FormatFamily"):
        an_opportunity(format_class=FormatClass.NEW_FORMAT_FAMILY, family=None)
    with pytest.raises(ResearchError, match="describes no FormatFamily"):
        an_opportunity(format_class=FormatClass.FORMAT_EXTENSION, family=None)


def test_a_single_video_may_not_smuggle_in_a_format_family():
    with pytest.raises(ResearchError, match="classified single_video"):
        an_opportunity(format_class=FormatClass.SINGLE_VIDEO, family=a_family())
    lone = an_opportunity(format_class=FormatClass.SINGLE_VIDEO, family=None)
    assert not lone.is_repeatable_format


def test_a_family_must_say_what_varies_between_episodes():
    with pytest.raises(ResearchError, match="variable_dimensions"):
        a_family(variable_dimensions=())
    with pytest.raises(ResearchError, match="does not describe a family"):
        a_family(estimated_episodes=1)


def test_superiority_targets_separate_measured_qualitative_and_unknown():
    measured = a_target(status=TargetStatus.MEASURED, reference_observation=a_measurement())
    assert measured.reference_observation.value == 2.5

    with pytest.raises(ResearchError, match="no reference_observation"):
        a_target(status=TargetStatus.MEASURED)

    with pytest.raises(ResearchError, match="makes it measured"):
        a_target(status=TargetStatus.QUALITATIVE, reference_observation=a_measurement())

    with pytest.raises(ResearchError, match="measurement_plan"):
        a_target(status=TargetStatus.UNKNOWN_PENDING_MEASUREMENT)

    pending = a_target(
        status=TargetStatus.UNKNOWN_PENDING_MEASUREMENT,
        measurement_plan="Frame-count the reference's first cut on a captured still sequence.",
    )
    assert pending.reference_observation is None


def test_the_dossier_separates_measured_targets_from_the_honest_backlog():
    dossier = an_opportunity(
        superiority_targets=(
            a_target(dimension="hook_clarity", status=TargetStatus.MEASURED,
                     reference_observation=a_measurement()),
            a_target(
                dimension="event_density",
                status=TargetStatus.UNKNOWN_PENDING_MEASUREMENT,
                measurement_plan="Count events per ten seconds on a captured still sequence.",
            ),
            a_target(dimension="mobile_readability"),
        )
    )
    assert [t.dimension for t in dossier.measured_targets] == ["hook_clarity"]
    assert [t.dimension for t in dossier.pending_measurement] == ["event_density"]


def test_two_targets_may_not_claim_one_dimension():
    with pytest.raises(ResearchError, match="same dimension"):
        an_opportunity(superiority_targets=(a_target(), a_target()))


def test_a_prototype_recommendation_needs_a_named_reviewer():
    with pytest.raises(ResearchError, match="name the reviewer"):
        an_opportunity(stage=OpportunityStage.PROTOTYPE_RECOMMENDED)
    with pytest.raises(ResearchError, match="acceptance criterion"):
        an_opportunity(
            stage=OpportunityStage.PROTOTYPE_RECOMMENDED,
            reviewed_by="studio_coo",
            reviewed_on=TODAY,
            superiority_targets=(),
        )
    approved = an_opportunity(
        stage=OpportunityStage.PROTOTYPE_RECOMMENDED,
        reviewed_by="studio_coo",
        reviewed_on=TODAY,
    )
    assert approved.reviewed_by == "studio_coo"


def test_no_code_path_promotes_an_opportunity_from_a_score():
    """The brief says do not automatically approve prototypes.

    Two halves, and both are absences. The scoring module cannot name an
    opportunity stage, so no total can be turned into one; and the opportunity
    module ships no transition helper at all, so the only way a dossier reaches
    `prototype_recommended` is a person typing it into the constructor - which
    then demands a reviewer and a date.
    """
    import intelligence.research.opportunity as opportunity
    import intelligence.research.scoring as scoring

    scoring_text = Path(inspect.getfile(scoring)).read_text(encoding="utf-8")
    for forbidden in ("OpportunityStage", "PROTOTYPE_RECOMMENDED", "approve"):
        assert forbidden not in scoring_text, forbidden

    transitions = [
        name
        for name, obj in vars(opportunity).items()
        if inspect.isfunction(obj) and obj.__module__ == opportunity.__name__
    ]
    assert transitions == []


# --------------------------------------------------------------------------
# Scoring
# --------------------------------------------------------------------------


def test_scoring_is_deterministic_and_normalised_to_the_scale():
    rubric, card = a_rubric(), a_scorecard()
    first = score_opportunity(rubric, card)
    second = score_opportunity(rubric, card)
    assert first == second
    assert dumps(first) == dumps(second)
    # (4*3 + 5*2 + (5-2)*1) / 6 == 25/6
    assert first.weighted_total == pytest.approx(25 / 6, abs=1e-6)
    assert first.weight_covered == 1.0
    assert first.is_comparable


def test_a_lower_is_better_dimension_is_inverted_once():
    rubric = a_rubric()
    cheap = score_opportunity(
        rubric,
        a_scorecard(
            scores=(DimensionScore(dimension="estimated_cost", score=0, reason="Reuses everything."),)
        ),
    )
    dear = score_opportunity(
        rubric,
        a_scorecard(
            id="sc-dear",
            scores=(DimensionScore(dimension="estimated_cost", score=5, reason="A new engine."),),
        ),
    )
    assert cheap.weighted_total > dear.weighted_total


def test_missing_dimensions_are_visible_and_mark_the_total_incomparable():
    result = score_opportunity(
        a_rubric(),
        a_scorecard(
            scores=(
                DimensionScore(dimension="viewer_loop_strength", score=4, reason="Shrinking field."),
            )
        ),
    )
    assert result.missing_dimensions == ("repeatability", "estimated_cost")
    assert result.has_gaps
    assert result.weight_covered == 0.5
    assert not result.is_comparable


def test_every_score_records_a_reason():
    with pytest.raises(ReferenceViolation, match="reason"):
        DimensionScore(dimension="channel_fit", score=3, reason="")


def test_a_score_outside_the_rubric_is_refused_in_both_directions():
    with pytest.raises(ResearchError, match="does not define"):
        score_opportunity(
            a_rubric(),
            a_scorecard(
                scores=(DimensionScore(dimension="vibes", score=5, reason="Felt right."),)
            ),
        )
    with pytest.raises(ResearchError, match="exceeds the rubric"):
        score_opportunity(
            a_rubric(),
            a_scorecard(
                scores=(
                    DimensionScore(dimension="repeatability", score=9, reason="Very repeatable."),
                )
            ),
        )


def test_a_composite_cannot_travel_without_its_caveat():
    result = score_opportunity(a_rubric(), a_scorecard())
    assert result.caveat == CAVEAT
    assert "not evidence" in result.caveat
    assert "not confidence" in result.caveat
    assert "caveat" in dumps(result)
    # and it carries no confidence of its own to be mistaken for one
    assert "confidence" not in {f.name for f in dataclasses.fields(result)}


def test_scoring_cannot_see_public_metrics_at_all():
    """'Higher views is better' is not a rule someone forgot - it has no input."""
    params = set(inspect.signature(score_opportunity).parameters)
    assert params == {"rubric", "card"}
    import intelligence.research.scoring as scoring

    text = Path(inspect.getfile(scoring)).read_text(encoding="utf-8")
    for forbidden in ("PublicMetrics", "views", "DerivedMetrics"):
        assert forbidden not in text.split('"""')[2], forbidden


def test_ties_break_deterministically_by_id():
    rubric = a_rubric()
    cards = [
        a_scorecard(id="sc-b", opportunity_id="op-b"),
        a_scorecard(id="sc-a", opportunity_id="op-a"),
        a_scorecard(id="sc-c", opportunity_id="op-c"),
    ]
    ordered = rank(score_opportunity(rubric, c) for c in cards)
    assert [r.opportunity_id for r in ordered] == ["op-a", "op-b", "op-c"]


def test_ranking_across_rubrics_is_refused():
    one = score_opportunity(a_rubric(), a_scorecard())
    other_rubric = a_rubric(id="other-rubric")
    two = score_opportunity(
        other_rubric, a_scorecard(id="sc-2", opportunity_id="op-2", rubric_id="other-rubric")
    )
    with pytest.raises(ResearchError, match="different scales"):
        rank([one, two])


def test_a_rubric_states_its_weights_explicitly():
    with pytest.raises(ResearchError, match="weight"):
        ScoringDimension(name="channel_fit", weight=0)
    assert a_rubric().total_weight == 6.0
    assert a_rubric().names == ("viewer_loop_strength", "repeatability", "estimated_cost")


def test_a_scorecard_cannot_score_one_dimension_twice():
    with pytest.raises(ResearchError, match="scored twice"):
        a_scorecard(
            scores=(
                DimensionScore(dimension="repeatability", score=1, reason="a"),
                DimensionScore(dimension="repeatability", score=5, reason="b"),
            )
        )


# --------------------------------------------------------------------------
# Lifecycle
# --------------------------------------------------------------------------


def _step(source, to_stage, reason, **kw):
    return advance_source(source, to_stage, on=TODAY, by="research_opportunity_lead",
                          reason=reason, **kw)


def test_the_research_lifecycle_runs_from_discovery_to_a_recommendation():
    source = a_source()
    source = _step(source, ResearchStage.SCREENED, "Format is adjacent to ours.")
    source = link_reference_case(source, "rc-elimination-marble-run")
    source = _step(source, ResearchStage.REFERENCE_ANALYZED, "Case file written.")
    source = link_opportunity(source, "op-elimination-race")
    source = _step(source, ResearchStage.OPPORTUNITY_CREATED, "Dossier written.")
    source = _step(source, ResearchStage.REVIEWED, "COO reviewed the dossier.")
    source = _step(source, ResearchStage.PROTOTYPE_RECOMMENDED, "Approved for a prototype.")

    assert source.stage is ResearchStage.PROTOTYPE_RECOMMENDED
    assert len(source.history) == 5
    assert [s.to_stage.value for s in source.history] == [
        "screened",
        "reference_analyzed",
        "opportunity_created",
        "reviewed",
        "prototype_recommended",
    ]
    assert all(step.reason for step in source.history)


def test_a_stage_cannot_be_skipped():
    with pytest.raises(ResearchError, match="cannot go from"):
        _step(a_source(), ResearchStage.REVIEWED, "Looks good.")


def test_a_stage_cannot_be_entered_without_the_artefact_it_names():
    source = _step(a_source(), ResearchStage.SCREENED, "Worth a look.")
    with pytest.raises(ResearchError, match="reference_case_ids"):
        _step(source, ResearchStage.REFERENCE_ANALYZED, "Analyzed it, honest.")

    source = link_reference_case(source, "rc-elimination-marble-run")
    source = _step(source, ResearchStage.REFERENCE_ANALYZED, "Case file written.")
    with pytest.raises(ResearchError, match="opportunity_ids"):
        _step(source, ResearchStage.OPPORTUNITY_CREATED, "Dossier exists somewhere.")


def test_rejection_is_terminal():
    source = _step(a_source(), ResearchStage.REJECTED, "Not adjacent to our channel.")
    with pytest.raises(ResearchError, match="terminal"):
        _step(source, ResearchStage.SCREENED, "Second thoughts.")


def test_a_recommendation_can_still_be_killed_later():
    source = a_source()
    source = _step(source, ResearchStage.SCREENED, "Adjacent.")
    source = link_reference_case(source, "rc-elimination-marble-run")
    source = _step(source, ResearchStage.REFERENCE_ANALYZED, "Written.")
    source = link_opportunity(source, "op-elimination-race")
    source = _step(source, ResearchStage.OPPORTUNITY_CREATED, "Written.")
    source = _step(source, ResearchStage.REVIEWED, "Reviewed.")
    source = _step(source, ResearchStage.PROTOTYPE_RECOMMENDED, "Approved.")
    killed = _step(source, ResearchStage.REJECTED, "Prototype missed its fairness target.")
    assert killed.stage is ResearchStage.REJECTED
    assert len(killed.history) == 6


def test_history_and_stage_cannot_disagree():
    with pytest.raises(ResearchError, match="no history"):
        a_source(stage=ResearchStage.REVIEWED)


def test_linking_is_idempotent_and_order_preserving():
    source = link_reference_case(a_source(), "rc-a")
    source = link_reference_case(source, "rc-b")
    source = link_reference_case(source, "rc-a")
    assert source.reference_case_ids == ("rc-a", "rc-b")


def test_the_workflow_produces_an_evidence_package_not_production_work():
    import intelligence.research.lifecycle as lifecycle

    text = Path(inspect.getfile(lifecycle)).read_text(encoding="utf-8")
    for forbidden in ("render", "godot", "subprocess", "sloped"):
        assert forbidden not in text.lower().split('"""')[2], forbidden


# --------------------------------------------------------------------------
# The store
# --------------------------------------------------------------------------


def _populate(root) -> ResearchStore:
    store = ResearchStore(root)
    source = a_source()
    source = _step(source, ResearchStage.SCREENED, "Adjacent to our format.")
    source = link_reference_case(source, "rc-elimination-marble-run")
    source = _step(source, ResearchStage.REFERENCE_ANALYZED, "Case file written.")
    source = link_opportunity(source, "op-elimination-race")
    source = _step(source, ResearchStage.OPPORTUNITY_CREATED, "Dossier written.")
    store.add(source)
    store.add(a_reference_case())
    store.add(an_opportunity())
    store.add(a_rubric())
    store.add(a_scorecard())
    store.add(a_video_dossier())
    return store


def test_every_record_type_round_trips_through_the_store(tmp_path):
    store = _populate(tmp_path)
    assert store.get("source", "yt-competitor-marble-run").stage is ResearchStage.OPPORTUNITY_CREATED
    assert store.get("reference_case", "rc-elimination-marble-run").mechanics == ("race", "elimination")
    assert store.get("opportunity", "op-elimination-race").family.family_id == "elimination_race"
    assert store.get("rubric", "test-rubric").total_weight == 6.0
    assert store.get("scorecard", "sc-elimination-race").rubric_id == "test-rubric"
    assert store.get("video_dossier", "vid-elimination-pilot").format_family == "elimination_race"
    assert len(store.load_all()) == 6


def test_serialization_is_byte_stable(tmp_path):
    store = ResearchStore(tmp_path)
    path = store.add(an_opportunity())
    first = path.read_text(encoding="utf-8")
    store.add(OpportunityDossier.from_dict(__import__("json").loads(first)), overwrite=True)
    assert path.read_text(encoding="utf-8") == first
    assert dumps(an_opportunity()) == first


def test_the_store_refuses_a_silent_overwrite(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_source())
    with pytest.raises(ResearchError, match="already exists"):
        store.add(a_source())
    store.add(a_source(title="A corrected title"), overwrite=True)
    assert store.get("source", "yt-competitor-marble-run").title == "A corrected title"


def test_load_order_is_deterministic(tmp_path):
    store = ResearchStore(tmp_path)
    for suffix in ("c", "a", "b"):
        store.add(a_source(id=f"src-{suffix}"))
    assert [s.id for s in store.load_all("source")] == ["src-a", "src-b", "src-c"]


def test_integrity_finds_dangling_links_in_both_directions(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(link_reference_case(a_source(), "rc-missing"))
    store.add(a_reference_case(source_id="src-missing"))
    store.add(a_scorecard())
    issues = {str(i) for i in store.integrity()}
    assert any("unknown reference case 'rc-missing'" in i for i in issues)
    assert any("unknown source 'src-missing'" in i for i in issues)
    assert any("unknown opportunity 'op-elimination-race'" in i for i in issues)
    assert any("unknown rubric 'test-rubric'" in i for i in issues)


def test_a_well_formed_thread_has_no_integrity_issues(tmp_path):
    store = _populate(tmp_path)
    assert store.integrity() == ()


def test_a_thread_assembles_the_evidence_package(tmp_path):
    store = _populate(tmp_path)
    thread = store.thread("yt-competitor-marble-run")
    assert thread["source"][0].id == "yt-competitor-marble-run"
    assert [c.id for c in thread["reference_cases"]] == ["rc-elimination-marble-run"]
    assert [o.id for o in thread["opportunities"]] == ["op-elimination-race"]
    assert [s.id for s in thread["scorecards"]] == ["sc-elimination-race"]


def test_stale_research_is_found_by_its_own_recheck_date(tmp_path):
    store = _populate(tmp_path)
    assert store.stale(TODAY) == ()
    stale = store.stale(TODAY + dt.timedelta(days=31))
    assert {r.kind for r in stale} == {"source", "reference_case", "opportunity", "video_dossier"}
    assert "rubric" not in {r.kind for r in stale}


def test_the_shipped_rubric_loads_and_is_well_formed():
    rubric = ResearchStore(DEFAULT_ROOT).get("rubric", "opportunity-v1")
    assert rubric.version == "1"
    assert "estimated_cost" in rubric.names
    assert rubric.dimension("estimated_cost").higher_is_better is False
    assert all(d.weight > 0 for d in rubric.dimensions)


# --------------------------------------------------------------------------
# Video intelligence dossier
# --------------------------------------------------------------------------


def test_a_variable_cannot_be_both_changed_and_locked():
    with pytest.raises(ResearchError, match="both changed and locked"):
        ExperimentDefinition(
            question="Does the gate help?",
            predicted_observation="Churn rises.",
            method="Compare against V24.",
            variables_changed=("gate_rule", "seed"),
            variables_locked=("seed", "camera_rig"),
        )


def test_an_experiment_must_name_both_lists():
    with pytest.raises(ResearchError, match="re-render"):
        ExperimentDefinition(
            question="q",
            predicted_observation="p",
            method="m",
            variables_changed=(),
            variables_locked=("seed",),
        )
    with pytest.raises(ResearchError, match="attributed"):
        ExperimentDefinition(
            question="q",
            predicted_observation="p",
            method="m",
            variables_changed=("gate_rule",),
            variables_locked=(),
        )


def test_kill_conditions_are_required_and_retained(tmp_path):
    with pytest.raises(ResearchError, match="kill condition agreed"):
        a_video_dossier(kill_conditions=())
    store = ResearchStore(tmp_path)
    store.add(a_video_dossier())
    back = store.get("video_dossier", "vid-elimination-pilot")
    assert back.kill_conditions == a_video_dossier().kill_conditions
    assert len(back.kill_conditions) == 2


def test_a_video_dossier_must_name_a_superiority_target():
    with pytest.raises(ResearchError, match="acceptance criterion"):
        a_video_dossier(superiority_targets=())


def test_changed_and_locked_variables_survive_a_round_trip(tmp_path):
    store = ResearchStore(tmp_path)
    store.add(a_video_dossier())
    changed, locked = store.get("video_dossier", "vid-elimination-pilot").changed_and_locked
    assert changed == ("gate_rule", "field_size")
    assert locked == ("course_topology", "camera_rig", "lighting", "seed")
    assert not set(changed) & set(locked)


def test_a_cost_estimate_needs_a_basis():
    with pytest.raises(ResearchError, match="cost_basis"):
        a_video_dossier(cost_estimate=Complexity.HIGH, cost_basis="")
    assert a_video_dossier(cost_estimate=Complexity.UNKNOWN, cost_basis="").cost_estimate


def test_the_dossier_is_not_connected_to_production():
    dossier = a_video_dossier(status=DossierStatus.READY_FOR_PRODUCTION)
    assert dossier.status is DossierStatus.READY_FOR_PRODUCTION
    import intelligence.research.video_dossier as module

    text = Path(inspect.getfile(module)).read_text(encoding="utf-8")
    for forbidden in ("sloped", "race", "godot", "render"):
        assert forbidden not in text.lower().split('"""')[2], forbidden


# --------------------------------------------------------------------------
# Guards
# --------------------------------------------------------------------------


_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "ai_platform",
        "argparse",
        "dataclasses",
        "datetime",
        "enum",
        "intelligence",
        "json",
        "knowledge",
        "pathlib",
        "re",
        "sys",
        "typing",
    }
)

_PRODUCTION_DIRS = (
    "audio",
    "engine",
    "entities",
    "evaluation",
    "marble3d",
    "modes",
    "powers",
    "production",
    "race",
    "rendering",
    "replay",
    "sloped",
    "tools",
)


def test_the_research_package_imports_nothing_from_production_and_adds_no_dependency():
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                roots = [(node.module or "").split(".")[0]]
            else:
                continue
            for root in roots:
                assert root in _ALLOWED_IMPORTS, f"{path.name} imports {root!r}"


def test_no_production_module_imports_the_research_layer():
    for directory in _PRODUCTION_DIRS:
        base = REPO_ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            assert "intelligence.research" not in text, path
            assert "from intelligence" not in text, path


def test_this_branch_changed_no_race_fight_or_v30_code():
    """The research subsystem is additive: it owns intelligence/ and one test."""
    import subprocess

    diff = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if diff.returncode != 0:
        pytest.skip("no origin/main to compare against")
    touched = [line for line in diff.stdout.splitlines() if line.strip()]
    for path in touched:
        assert not path.startswith(tuple(f"{d}/" for d in _PRODUCTION_DIRS)), path


def test_the_no_subagent_rule_is_exactly_where_it_was():
    """This branch added a research store; it did not touch rule 2."""
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(no_subagents=False)
    with pytest.raises(SubagentPolicyViolation):
        ExecutionPolicy(nested_agent_spawning=True)
    with pytest.raises(ValidationError):
        enforce_no_subagents({"no_subagents": False})
    assert ExecutionPolicy().no_subagents is True


def test_nothing_in_the_package_reaches_the_network_or_a_model():
    banned = (
        "urllib",
        "requests",
        "httpx",
        "http.client",
        "socket",
        "selenium",
        "playwright",
        "yt_dlp",
        "youtube",
        "openai",
        "anthropic",
        "webbrowser",
    )
    for path in sorted(PACKAGE.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert not name.startswith(banned), f"{path.name} imports {name!r}"


def test_evidence_refs_stay_pointers_not_pasted_content():
    with pytest.raises(ReferenceViolation):
        an_evidence(ref="line one\nline two")
    with pytest.raises(ReferenceViolation):
        a_source(reference="x" * 400)


def test_the_source_helper_produces_a_citable_pointer():
    evidence = observation_evidence(a_source())
    assert evidence.kind == "observation"
    assert evidence.ref == "https://example.invalid/watch?v=abc"
