"""What the first live pull of our own channel taught us, kept falsifiable.

The connector was written, reviewed and tested against scripted responses, and
then pointed at the real Physics Loop channel. It worked - OAuth, both APIs, a
sanitized artifact, ingestion - and in working it produced three facts no
scripted fixture had thought to produce. This module is those facts, written
down as tests so that the next person to tidy up cannot quietly undo them.

## 1. A percentage viewed of 118.41

`averageViewPercentage` came back as `118.41` for a Short. That is not a
provider bug and not a parse error: a viewer who lets a Short loop accumulates
watch time past the end of it, so the mean watch duration can exceed the
duration of the video. The fetcher normalized it correctly to `1.1841`.

What was wrong was the contract underneath. `average_percentage_viewed`
described itself as "fraction of video length, 0.0-1.0", so the only reading in
the pull that said something interesting was the one the documentation called
impossible. Nothing clamped it - the clamp had simply never been written - which
means the defect was latent rather than harmless: the next person to "fix" the
inconsistency had a sentence in the registry telling them to clamp.

The ceiling is now a declared field (`unbounded_above`) rather than prose, and
these tests pin the four values across the whole path: fetcher, artifact,
bridge, observation, store and comparison.

## 2. A channel-wide report is evidence, not a deliverable

A pull asks `reports.query` for the channel as well as for each video, so the
artifact carries one row set with no video id. The ledger was right to refuse
it - an observation is recorded against a deliverable and the channel is not one
- but it refused it as an *error*, which made a correct, expected, every-single-
pull outcome look like a failure. And an error nobody can fix is an error
everybody learns to ignore.

The fix is not a deliverable id of `"channel"`. That would put a total into the
same population as the videos it totals, and every later average would count the
week twice. The two levels are separated instead: retained as evidence, named in
the result, and reported as the same `AGGREGATE_ROW` note the Studio importer
gives a "Total" row.

## 3. Nothing knows which video is which deliverable

54 readings parsed, 0 observations committed, because no mapping exists between
a YouTube video id and a Company OS deliverable. That refusal is the layer
working. What was missing was the way *out* of it, so there is now a template
generator - and the template's placeholders are refused by the loader, because a
file full of `REPLACE_WITH_DELIVERABLE_ID` that validated would attach a week of
real readings to a deliverable nobody ever made.

## The fixture is synthetic, and deliberately so

`tests/fixtures/youtube_looping_short_artifact.json` reproduces the *shape* the
live pull exposed - four videos spanning 45.6%, 100%, 118.41% and 200%, plus a
channel-wide row set - under a made-up channel id with made-up figures. The real
pull's numbers are private channel analytics and are not needed to hold the
semantics still. It carries no credential, no token and no real identifier.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from company.analytics import (
    AnalyticsStore,
    DataScope,
    DataSource,
    DeliverableKind,
    MetricKind,
    Provenance,
    observe,
)
from company.analytics.comparison import compare_deliverables
from company.analytics.errors import AnalyticsError
from company.analytics.metrics import STANDARD_METRICS, MetricDefinition
from company.analytics.studio_ingest import IngestionIssueKind, IssueSeverity
from company.analytics.windows import FIRST_30D
from knowledge.company_os.records import Evidence
from company.youtube import (
    CHANNEL_EVIDENCE_LEVEL,
    VIDEO_EVIDENCE_LEVEL,
    ArtifactRejected,
    DeliverableAssignment,
    YouTubeEvidenceStore,
    commit_ingestion,
    ingest_artifact,
    read_artifact,
)
from company.youtube.ingest import (
    ASSIGNMENT_PLACEHOLDER_PREFIX,
    assignment_template,
    load_assignments,
    unassigned_videos,
)


FIXTURE = Path(__file__).parent / "fixtures" / "youtube_looping_short_artifact.json"

# The four values the live run made us care about, as (video id, fraction, what
# the provider's own percentage was). 118.41 is the one that was actually
# observed; the other three bracket it.
APV_CASES = (
    ("apvUnderOne", 0.456, 45.6),
    ("apvExactlyOne", 1.0, 100.0),
    ("apvLooped1184", 1.1841, 118.41),
    ("apvDoubled200", 2.0, 200.0),
)

# A deliverable id is lowercase by construction and a YouTube video id is
# case-sensitive, so the two cannot be the same string. The mapping is spelled
# out here for the same reason the real one is operator-supplied: nothing
# derives one identifier from the other.
DELIVERABLE_OF = {
    "apvUnderOne": "fixture-apv-under-one",
    "apvExactlyOne": "fixture-apv-exactly-one",
    "apvLooped1184": "fixture-apv-looped",
    "apvDoubled200": "fixture-apv-doubled",
}

ASSIGNMENTS = {
    video_id: DeliverableAssignment(
        deliverable_id=DELIVERABLE_OF[video_id],
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    )
    for video_id, _fraction, _percent in APV_CASES
}

UTC = dt.timezone.utc


@pytest.fixture()
def artifact():
    return read_artifact(FIXTURE)


@pytest.fixture()
def result(artifact):
    return ingest_artifact(artifact, assignments=ASSIGNMENTS)


def apv_observation(result, video_id):
    """The average_percentage_viewed observation for one fixture video."""
    deliverable = DELIVERABLE_OF[video_id]
    matches = [
        o
        for o in result.observations
        if o.deliverable_id == deliverable
        and o.metric.name == "average_percentage_viewed"
    ]
    assert len(matches) == 1, f"expected one APV reading for {video_id}"
    return matches[0]


# -- finding 1: the metric's own contract ---------------------------------


def test_average_percentage_viewed_declares_no_ceiling():
    """The corrected contract, at its source.

    The old unit string said "0.0-1.0". If somebody restores that, they have to
    restore `unbounded_above=False` with it, and every test below fails.
    """
    apv = STANDARD_METRICS["average_percentage_viewed"]
    assert apv.unbounded_above is True
    assert apv.maximum is None
    assert apv.minimum == 0.0
    assert "0.0-1.0" not in apv.unit
    assert "1.0" in apv.unit


def test_a_share_of_a_population_still_has_a_ceiling():
    """Lifting the cap for one metric did not lift it for the rest.

    `retention_at_3s` is views-still-playing over views, and more views still
    playing than there were views is arithmetic, not a looping viewer.
    """
    for name in ("retention_at_3s", "retention_at_50pct", "click_through_rate"):
        metric = STANDARD_METRICS[name]
        assert metric.unbounded_above is False
        assert metric.maximum == 1.0


def test_money_is_the_only_metric_that_may_go_negative():
    """A refund is a real negative amount; negative views are a slip."""
    assert STANDARD_METRICS["estimated_revenue"].minimum is None
    assert STANDARD_METRICS["views"].minimum == 0.0
    assert STANDARD_METRICS["average_percentage_viewed"].minimum == 0.0


def test_unbounded_above_is_refused_on_a_kind_with_no_full_scale():
    """A count has no 1.0 to pass, so the flag is meaningless on one."""
    with pytest.raises(AnalyticsError) as error:
        MetricDefinition(
            "made_up_count",
            MetricKind.COUNT,
            "things",
            "A count that claims it can pass full scale.",
            unbounded_above=True,
        )
    assert "full scale" in str(error.value)


def test_the_declared_bound_round_trips_through_serialization():
    apv = STANDARD_METRICS["average_percentage_viewed"]
    assert apv.to_dict()["unbounded_above"] is True
    assert MetricDefinition.from_dict(apv.to_dict()) == apv


def test_a_metric_with_a_ceiling_refuses_a_value_above_it():
    """The check exists, so the lifted cap is a decision and not an oversight."""
    with pytest.raises(AnalyticsError) as error:
        observe(
            "obs-over-ceiling",
            _deliverable(),
            "retention_at_3s",
            1.2,
            dt.datetime(2026, 9, 17, tzinfo=UTC),
            _provenance(),
            _scope(),
            denominator_value=1000.0,
        )
    assert "unbounded_above" in str(error.value)


def test_a_negative_reading_is_refused():
    with pytest.raises(AnalyticsError) as error:
        observe(
            "obs-negative",
            _deliverable(),
            "views",
            -1.0,
            dt.datetime(2026, 9, 17, tzinfo=UTC),
            _provenance(),
            _scope(),
        )
    assert "cannot be negative" in str(error.value)


# -- finding 1: the four values, end to end -------------------------------


@pytest.mark.parametrize("video_id,fraction,percent", APV_CASES)
def test_the_artifact_carries_the_fraction_the_provider_meant(
    artifact, video_id, fraction, percent
):
    """45.6 -> 0.456 and 118.41 -> 1.1841: one division, no ceiling."""
    report = next(r for r in artifact.analytics if r.video_id == video_id)
    reading = report.metric("average_view_percentage")
    assert reading.unit == "fraction"
    assert reading.value == pytest.approx(fraction)
    assert reading.value == pytest.approx(percent / 100.0)


@pytest.mark.parametrize("video_id,fraction,percent", APV_CASES)
def test_every_value_survives_into_an_observation(
    result, video_id, fraction, percent
):
    """The value the provider reported, unchanged, in the ledger record."""
    observation = apv_observation(result, video_id)
    assert observation.value == pytest.approx(fraction)
    assert observation.value * 100 == pytest.approx(percent)


def test_the_looping_short_is_not_clamped(result):
    """The live finding, stated as the thing that must not happen.

    A clamp would make this equal 1.0, and the reading would then say the Short
    is watched exactly once through - which is the opposite of what it says.
    """
    looped = apv_observation(result, "apvLooped1184")
    assert looped.value == pytest.approx(1.1841)
    assert looped.value > 1.0
    exactly_one = apv_observation(result, "apvExactlyOne")
    assert looped.value != exactly_one.value


@pytest.mark.parametrize("video_id,fraction,percent", APV_CASES)
def test_every_value_survives_a_store_round_trip(
    tmp_path, result, video_id, fraction, percent
):
    """Committed, read back off disk, still the number the provider reported."""
    store = AnalyticsStore(tmp_path / "state")
    commit_ingestion(result, store)
    stored = {
        o.deliverable_id: o
        for o in store.list("observation")
        if o.metric.name == "average_percentage_viewed"
    }
    assert stored[DELIVERABLE_OF[video_id]].value == pytest.approx(fraction)


def _apv_difference(result, video_a, video_b):
    """The APV comparison between two fixture videos, through the public API."""
    comparison = compare_deliverables(
        DELIVERABLE_OF[video_a],
        DELIVERABLE_OF[video_b],
        result.observations,
        FIRST_30D,
    )
    return next(
        c for c in comparison.comparisons
        if c.metric.name == "average_percentage_viewed"
    )


def test_values_above_and_below_full_scale_compare_correctly(result):
    """Downstream analysis has to order them, not just hold them.

    A looping Short against one people leave early is the comparison this
    metric exists for, and it has to come out as +0.7281 rather than as a pair
    of numbers one of which was flattened to 1.0.
    """
    difference = _apv_difference(result, "apvUnderOne", "apvLooped1184")
    assert difference.comparable, difference.reasons
    assert difference.value_a == pytest.approx(0.456)
    assert difference.value_b == pytest.approx(1.1841)
    assert difference.difference == pytest.approx(1.1841 - 0.456)
    assert difference.relative_change == pytest.approx((1.1841 - 0.456) / 0.456)


def test_a_doubled_short_beats_a_looping_one(result):
    """Ordering holds above full scale, where a clamp would tie them at 1.0."""
    difference = _apv_difference(result, "apvLooped1184", "apvDoubled200")
    assert difference.comparable, difference.reasons
    assert difference.difference == pytest.approx(2.0 - 1.1841)
    assert difference.direction is not None and difference.difference > 0


# -- finding 2: channel-wide analytics ------------------------------------


def test_the_channel_wide_report_is_retained_as_evidence(result):
    """Named, with its window and its metrics, at the channel level."""
    assert len(result.channel_reports) == 1
    report = result.channel_reports[0]
    assert report.subject_ref == "youtube:channel:UCtestCHANNELtestCHANNEL"
    assert report.channel_id == "UCtestCHANNELtestCHANNEL"
    assert report.window == "2026-09-10..2026-09-16"
    assert "average_view_percentage" in report.metric_names
    assert result.channel_readings == report.reading_count == 3


def test_the_channel_wide_report_is_not_an_observation(result):
    """No observation anywhere is about the channel, under any id."""
    assert result.observations
    for observation in result.observations:
        assert "channel" not in observation.deliverable_id.lower()
        assert "UCtestCHANNEL" not in observation.deliverable_id
    assert {d.deliverable_id for d in result.deliverables} == set(DELIVERABLE_OF.values())
    assert len(result.deliverables) == len(APV_CASES)


def test_no_fake_deliverable_id_is_invented(tmp_path, result):
    """The store, after a real commit, holds four deliverables and no channel."""
    store = AnalyticsStore(tmp_path / "state")
    commit_ingestion(result, store)
    ids = set(store.ids("deliverable"))
    assert ids == set(DELIVERABLE_OF.values())
    assert "channel" not in ids
    assert "UCtestCHANNELtestCHANNEL" not in ids


def test_the_channel_report_is_a_note_not_an_error(result):
    """It happens on every pull and is correct, so it cannot be an error.

    The same kind and severity the Studio importer gives a 'Total' row: the two
    importers see the same thing through different doors.
    """
    aggregate = result.issues_of(IngestionIssueKind.AGGREGATE_ROW)
    assert len(aggregate) == 1
    assert aggregate[0].severity is IssueSeverity.NOTE
    assert "channel" in aggregate[0].reason
    assert not [
        i
        for i in result.issues
        if i.kind is IngestionIssueKind.MISSING_VIDEO_ID and not i.video_id
    ]


def test_a_fully_assigned_pull_reports_no_errors(result):
    """The end the operator actually needs: everything mapped, nothing wrong.

    Before this change the channel row set made `errors` non-empty on every
    pull, so the CLI returned 1 even when the import was perfect.
    """
    assert result.errors == ()
    assert result.observations
    assert result.channel_reports


def test_the_two_evidence_levels_are_distinguishable_in_json(result):
    """A consumer of to_dict() can tell them apart without reading our fields."""
    data = result.to_dict()
    assert data["evidence_levels"] == {
        CHANNEL_EVIDENCE_LEVEL: 3,
        VIDEO_EVIDENCE_LEVEL: result.readings_accepted,
    }
    assert len(data["channel_evidence"]) == 1
    assert data["channel_evidence"][0]["evidence_level"] == CHANNEL_EVIDENCE_LEVEL
    assert data["channel_evidence"][0]["channel_id"] == "UCtestCHANNELtestCHANNEL"


def test_the_channel_numbers_survive_in_the_evidence_envelope(tmp_path, artifact):
    """'Retained' has to mean the values are recoverable, not just counted.

    The result object prints no reading, by design. The envelope is where the
    channel's own figures actually live, and this is the test that says so.
    """
    store = YouTubeEvidenceStore(tmp_path / "state")
    store.append(artifact, ingested_from=str(FIXTURE))
    record = store.records()[0]
    assert "youtube:channel:UCtestCHANNELtestCHANNEL" in record["identity"][
        "analytics_subjects"
    ]
    channel_rows = [
        r for r in record["normalized"]["analytics"] if r["video_id"] is None
    ]
    assert len(channel_rows) == 1
    apv = next(
        m
        for m in channel_rows[0]["metrics"]
        if m["name"] == "average_view_percentage"
    )
    assert apv["value"] == pytest.approx(0.7194)


def test_the_render_says_the_channel_report_was_kept(result):
    text = result.render()
    assert "channel evidence" in text
    assert "not written as observations" in text


# -- finding 3: the assignment workflow -----------------------------------


def test_an_unmapped_pull_commits_nothing(artifact):
    """54 readings parsed, 0 observations: the live result, in miniature."""
    unmapped = ingest_artifact(artifact, assignments={})
    assert unmapped.readings_read == 15
    assert unmapped.readings_accepted == 0
    assert unmapped.observations == ()
    assert set(unmapped.unassigned_videos) == {v for v, _f, _p in APV_CASES}
    # and the channel report is still classified, not counted as a failure
    assert len(unmapped.channel_reports) == 1


def test_the_template_is_keyed_by_the_real_video_ids(artifact):
    template = assignment_template(artifact)
    assert set(template) == {v for v, _f, _p in APV_CASES}
    for entry in template.values():
        assert set(entry) == {"deliverable_id", "kind", "format_id"}
        assert all(
            value.startswith(ASSIGNMENT_PLACEHOLDER_PREFIX) for value in entry.values()
        )


def test_the_template_infers_nothing_from_a_title(artifact):
    """Every title in the fixture is different; every template entry is not."""
    titles = {v.title for v in artifact.videos}
    assert len(titles) == len(APV_CASES)
    entries = [
        json.dumps(entry, sort_keys=True)
        for entry in assignment_template(artifact).values()
    ]
    assert len(set(entries)) == 1


def test_an_unedited_template_is_refused(artifact):
    """The generated file cannot be imported until a person has filled it in."""
    with pytest.raises(ArtifactRejected) as error:
        load_assignments(assignment_template(artifact))
    assert ASSIGNMENT_PLACEHOLDER_PREFIX in str(error.value)


def test_a_half_filled_template_is_refused(artifact):
    """A valid `kind` is not enough; the deliverable id is the dangerous field."""
    half = assignment_template(artifact)
    for entry in half.values():
        entry["kind"] = "short"
        entry["format_id"] = "marble_race"
    with pytest.raises(ArtifactRejected) as error:
        load_assignments(half)
    assert "deliverable_id" in str(error.value)


def test_a_filled_template_loads(artifact):
    filled = {
        video_id: {
            "deliverable_id": f"fixture-{video_id}",
            "kind": "short",
            "format_id": "marble_race",
        }
        for video_id in assignment_template(artifact)
    }
    loaded = load_assignments(filled)
    assert set(loaded) == {v for v, _f, _p in APV_CASES}
    assert loaded["apvLooped1184"].kind is DeliverableKind.SHORT


def test_the_template_leaves_out_what_is_already_assigned(artifact):
    one = {"apvLooped1184": ASSIGNMENTS["apvLooped1184"]}
    assert "apvLooped1184" not in assignment_template(artifact, one)
    assert set(assignment_template(artifact, one)) == {
        v for v, _f, _p in APV_CASES if v != "apvLooped1184"
    }
    assert "apvLooped1184" not in {v.video_id for v in unassigned_videos(artifact, one)}


def test_the_documented_template_is_a_file_the_loader_accepts():
    """The example in docs/ cannot drift from the schema the code reads.

    Its keys are placeholders, so it assigns nothing real; what it proves is
    that the shape a reader copies out of the documentation is the shape
    `load_assignments` takes.
    """
    documented = Path(__file__).parents[1] / "docs" / "youtube_assignments_template.json"
    loaded = load_assignments(json.loads(documented.read_text(encoding="utf-8")))
    assert loaded
    for video_id, assignment in loaded.items():
        assert "VIDEO_ID" in video_id, "the example keys must stay placeholders"
        assert assignment.deliverable_id
        assert isinstance(assignment.kind, DeliverableKind)
        assert assignment.format_id


def test_the_unassigned_listing_carries_what_a_person_needs(artifact):
    """An operator cannot recognise a video from eleven characters."""
    pending = unassigned_videos(artifact)
    assert len(pending) == len(APV_CASES)
    looped = next(v for v in pending if v.video_id == "apvLooped1184")
    assert looped.title
    assert looped.published_at.startswith("2026-")
    assert looped.duration == "PT21S"


# -- helpers ---------------------------------------------------------------


def _deliverable():
    from company.analytics import AnalyzedDeliverable

    return AnalyzedDeliverable(
        deliverable_id="bounds-probe",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
        published_at=dt.datetime(2026, 9, 10, tzinfo=UTC),
    )


def _provenance():
    return Provenance(
        source=DataSource.OWN_ANALYTICS_API,
        retrieved_by="a bounds test",
        evidence=(Evidence(kind="document", ref="tests/bounds", note="a bounds test"),),
    )


def _scope():
    return DataScope(population="every viewer counted for the probe")
