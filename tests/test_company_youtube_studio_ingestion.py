"""YouTube Studio CSV export to auditable observation, and everything refused.

The suite is organised by the claim being protected rather than by module,
because almost everything this layer guarantees is a refusal:

    ownership        our own authenticated export, or no import at all
    reading          UTF-8, BOM, row numbers, header names kept verbatim
    schema           exact recognition, unknown columns reported not guessed
    values           integers, decimals, percentages, durations, and blanks
    locale           an ambiguous number is refused rather than chosen
    identity         a video id resolves a row; a title never does
    time             what a reading covers, and cumulative against interval
    money            finance-routed, never an analytics revenue figure
    idempotence      replay writes nothing, a disagreement is a conflict
    dry run          the result is complete and the disk is untouched
    diagnostics      file, row, column, reason - and not the rest of the row
    boundaries       no network, no API, no OAuth, no scraper, no production
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

import pytest

from knowledge.company_os.records import Evidence

from company.analytics import (
    STANDARD_STUDIO_SCHEMAS,
    STUDIO_VIDEO_DAILY_V1,
    STUDIO_VIDEO_TOTALS_V1,
    AnalyticsError,
    AnalyticsStore,
    AnalyzedDeliverable,
    ColumnMapping,
    DataScope,
    DataSource,
    DateRange,
    DeliverableKind,
    DOT_DECIMAL,
    EN_US_GROUPED,
    EURO_GROUPED,
    IngestionIssueKind,
    IssueSeverity,
    LedgerViolation,
    MetricKind,
    NumberFormat,
    Provenance,
    ProvenanceViolation,
    StudioExportRejected,
    StudioExportSource,
    StudioValueError,
    TemporalSemantics,
    ValueFormat,
    VideoIdentityMapping,
    check_integrity,
    commit_ingestion,
    describe_export,
    digest_bytes,
    ingest_studio_export,
    load_video_mapping,
    read_export,
    recognise_schema,
)
from company.analytics.studio_values import parse_cell

UTC = dt.timezone.utc
REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "company" / "analytics"
STUDIO_MODULES = sorted(PACKAGE.glob("studio_*.py"))

VIDEO_14 = "dQw4w9WgXcQ"
VIDEO_15 = "aBcD3fGh1Jk"
CHANNEL = "docs/company/our_channel.md"
EXPORTED_AT = dt.datetime(2026, 9, 10, 18, 0, tzinfo=UTC)
IMPORTED_AT = dt.datetime(2026, 9, 10, 18, 5, tzinfo=UTC)
PUBLISHED_AT = dt.datetime(2026, 9, 8, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------
# Fixtures: small synthetic exports. No real channel, no real video, no real
# numbers - section 24 asks for exactly that, and a fixture that were real
# would put private analytics in the repository.
# --------------------------------------------------------------------------

TOTALS_HEADER = (
    "Content,Video title,Video publish time,Duration,Views,Watch time (hours),"
    "Impressions,Impressions click-through rate (%),Average view duration,"
    "Average percentage viewed (%),Likes,Comments added,Shares,"
    "Subscribers gained,Subscribers lost,Subscribers,"
    "Your estimated revenue (USD)"
)

TOTALS_TOTAL_ROW = "Total,,,,52000,410.5,910000,5.7,0:18,61.2,1200,84,40,95,8,87,12.55"
TOTALS_ROW_14 = (
    f"{VIDEO_14},Marble race 14,2026-09-08,0:30,50000,400.0,900000,5.8,0:18,"
    "60.5,1180,80,38,90,7,83,12.10"
)


def write_csv(tmp_path: Path, name: str, text: str, *, bom: bool = False) -> Path:
    path = tmp_path / name
    path.write_bytes((("﻿" if bom else "") + text).encode("utf-8"))
    return path


def totals_csv(tmp_path: Path, *rows: str, bom: bool = False, name: str = "Table data.csv") -> Path:
    body = "\n".join((TOTALS_HEADER, *rows)) + "\n"
    return write_csv(tmp_path, name, body, bom=bom)


@pytest.fixture
def export(tmp_path: Path) -> Path:
    return totals_csv(tmp_path, TOTALS_TOTAL_ROW, TOTALS_ROW_14, bom=True)


def a_provenance(source: DataSource = DataSource.OWN_STUDIO_EXPORT, **kwargs) -> Provenance:
    return Provenance(
        source=source,
        retrieved_by=kwargs.pop("retrieved_by", "studio csv export 2026-09-10"),
        evidence=kwargs.pop(
            "evidence",
            (Evidence(kind="document", ref="exports/studio.csv", note="own channel"),),
        ),
        **kwargs,
    )


def a_mapping(**kwargs) -> VideoIdentityMapping:
    return VideoIdentityMapping(
        channel_ref=kwargs.pop("channel_ref", CHANNEL),
        entries=kwargs.pop("entries", ((VIDEO_14, "race-short-014"),)),
        **kwargs,
    )


def a_deliverable(deliverable_id: str = "race-short-014", **kwargs) -> AnalyzedDeliverable:
    return AnalyzedDeliverable(
        deliverable_id=deliverable_id,
        kind=kwargs.pop("kind", DeliverableKind.SHORT),
        format_id=kwargs.pop("format_id", "race_short"),
        published_at=kwargs.pop("published_at", PUBLISHED_AT),
        **kwargs,
    )


def ingest(path: Path, **kwargs):
    defaults = dict(
        source_id="ys-2026-09-10",
        provenance=a_provenance(),
        channel_ref=CHANNEL,
        mapping=a_mapping(),
        exported_at=EXPORTED_AT,
        imported_at=IMPORTED_AT,
        deliverables=(a_deliverable(),),
        semantics=TemporalSemantics.CUMULATIVE_TO_INSTANT,
    )
    defaults.update(kwargs)
    return ingest_studio_export(path, **defaults)


def value_of(result, metric: str) -> float:
    for observation in result.observations:
        if observation.metric.name == metric:
            return observation.value
    raise AssertionError(f"no {metric} observation in {[o.metric.name for o in result.observations]}")


def kinds(result) -> set[IngestionIssueKind]:
    return {issue.kind for issue in result.issues}


# --------------------------------------------------------------------------
# Ownership: our own authenticated export, or no import at all
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source",
    [
        DataSource.PLATFORM_PUBLIC,
        DataSource.RESEARCH_REFERENCE,
        DataSource.OWN_ANALYTICS_API,
        DataSource.OWN_PRODUCTION_MEASUREMENT,
    ],
)
def test_only_an_own_studio_export_may_be_ingested(export, source):
    with pytest.raises(ProvenanceViolation, match="own_studio_export"):
        ingest(export, provenance=a_provenance(source))


def test_a_competitor_export_with_our_exact_columns_is_still_refused(export):
    """Section 2 and 18: the columns are not what makes a file admissible."""
    with pytest.raises(ProvenanceViolation) as exc:
        ingest(
            export,
            provenance=a_provenance(
                DataSource.PLATFORM_PUBLIC, retrieved_by="socialblade estimate for a rival"
            ),
        )
    assert "competitor" in str(exc.value)
    assert "scraped" in str(exc.value)


def test_a_manual_transcription_cannot_launder_a_public_source(export):
    """MANUAL_ENTRY inherits authority elsewhere; here it is simply not a file read."""
    with pytest.raises(ProvenanceViolation):
        ingest(
            export,
            provenance=a_provenance(
                DataSource.MANUAL_ENTRY, transcribed_from=DataSource.OWN_STUDIO_EXPORT
            ),
        )


def test_the_export_must_name_which_channel_of_ours_it_is(export):
    with pytest.raises(AnalyticsError, match="channel_ref"):
        ingest(export, channel_ref="", mapping=a_mapping())


def test_a_mapping_for_another_channel_is_refused(export):
    with pytest.raises(StudioExportRejected, match="two channels"):
        ingest(export, mapping=a_mapping(channel_ref="docs/company/other_channel.md"))


def test_private_metrics_survive_the_import_because_the_source_is_first_party(export):
    result = ingest(export)
    private = [o for o in result.observations if o.metric.private]
    assert private, "the export carries private analytics and they were all dropped"
    assert all(o.provenance.is_first_party for o in private)


# --------------------------------------------------------------------------
# Reading: UTF-8, a byte-order mark, row numbers, header names
# --------------------------------------------------------------------------


def test_a_byte_order_mark_does_not_become_part_of_the_first_header(tmp_path):
    marked = read_export(totals_csv(tmp_path, TOTALS_ROW_14, bom=True))
    plain = read_export(totals_csv(tmp_path, TOTALS_ROW_14, name="plain.csv"))
    assert marked.header[0] == "Content"
    assert marked.header == plain.header


def test_the_digest_is_over_the_exact_bytes_including_the_mark(tmp_path):
    path = totals_csv(tmp_path, TOTALS_ROW_14, bom=True)
    assert read_export(path).digest == digest_bytes(path.read_bytes())


def test_header_names_are_kept_exactly_as_the_export_spelled_them(tmp_path):
    export = read_export(totals_csv(tmp_path, TOTALS_ROW_14))
    assert "Impressions click-through rate (%)" in export.header
    assert export.header == tuple(TOTALS_HEADER.split(","))


def test_row_numbers_are_the_lines_of_the_file(tmp_path):
    export = read_export(totals_csv(tmp_path, TOTALS_TOTAL_ROW, TOTALS_ROW_14))
    assert [row.row_number for row in export.rows] == [2, 3]


def test_blank_lines_are_not_rows(tmp_path):
    path = write_csv(tmp_path, "gap.csv", f"{TOTALS_HEADER}\n\n{TOTALS_ROW_14}\n\n")
    assert [row.row_number for row in read_export(path).rows] == [3]


def test_the_input_file_is_never_modified(export):
    before = export.read_bytes()
    ingest(export)
    assert export.read_bytes() == before


def test_a_file_that_is_not_utf8_is_refused_by_name(tmp_path):
    path = tmp_path / "latin.csv"
    path.write_bytes(f"{TOTALS_HEADER}\n{TOTALS_ROW_14}\n".encode("utf-16"))
    with pytest.raises(StudioExportRejected, match="not UTF-8"):
        read_export(path)


def test_a_repeated_header_is_refused_rather_than_resolved(tmp_path):
    path = write_csv(tmp_path, "twice.csv", "Content,Views,Views\nx,1,2\n")
    with pytest.raises(StudioExportRejected, match="repeats the column"):
        read_export(path)


def test_a_row_of_the_wrong_width_is_reported_against_its_own_line(tmp_path):
    result = ingest(totals_csv(tmp_path, TOTALS_ROW_14, "short,row"))
    malformed = result.issues_of(IngestionIssueKind.MALFORMED_ROW)
    assert [issue.row_number for issue in malformed] == [3]
    assert result.rows_accepted == 1


# --------------------------------------------------------------------------
# Schema: exact recognition, and columns nobody decided about
# --------------------------------------------------------------------------


def test_the_two_shipped_schemas_are_recognised_from_their_headers():
    assert recognise_schema(TOTALS_HEADER.split(",")) is STUDIO_VIDEO_TOTALS_V1
    assert recognise_schema(["Date", "Content", "Views"]) is STUDIO_VIDEO_DAILY_V1


def test_recognition_is_deterministic_over_repeated_calls():
    header = TOTALS_HEADER.split(",")
    assert {recognise_schema(header).schema_id for _ in range(20)} == {
        "studio_video_totals_v1"
    }


def test_a_date_column_rules_out_the_per_video_totals_schema():
    """Reading per-day rows as whole-video totals would multiply every count."""
    assert not STUDIO_VIDEO_TOTALS_V1.matches(["Date", "Content", "Views"])
    assert STUDIO_VIDEO_DAILY_V1.matches(["Date", "Content", "Views"])


def test_an_unrecognised_header_is_refused_and_says_so(tmp_path):
    path = write_csv(tmp_path, "other.csv", "Alpha,Beta\n1,2\n")
    with pytest.raises(StudioExportRejected, match="no Studio export schema recognises"):
        read_export(path) and recognise_schema(read_export(path).header)


def test_two_schemas_matching_one_file_is_an_error_not_a_ranking():
    twin = STUDIO_VIDEO_TOTALS_V1
    with pytest.raises(StudioExportRejected, match="more than one"):
        recognise_schema(TOTALS_HEADER.split(","), (twin, twin))


def test_a_header_is_matched_exactly_and_never_approximately(tmp_path):
    """A space-padded column is unknown, not a near-miss that quietly imports."""
    header = TOTALS_HEADER.replace(",Likes,", ",Likes ,", 1)
    result = ingest(write_csv(tmp_path, "padded.csv", f"{header}\n{TOTALS_ROW_14}\n"))
    assert "Likes " in result.unknown_columns
    assert not [o for o in result.observations if o.metric.name == "likes"]


def test_a_padded_required_header_stops_the_file_being_recognised(tmp_path):
    """The loud failure: a renamed identity column is not a schema we know."""
    header = TOTALS_HEADER.replace("Content", "Content ", 1)
    with pytest.raises(StudioExportRejected, match="matched exactly"):
        ingest(write_csv(tmp_path, "padded_id.csv", f"{header}\n{TOTALS_ROW_14}\n"))


def test_an_unknown_column_is_reported_and_read_from_never(tmp_path):
    header = f"{TOTALS_HEADER},Some new Studio column"
    row = f"{TOTALS_ROW_14},41"
    result = ingest(write_csv(tmp_path, "new.csv", f"{header}\n{row}\n"))
    assert result.unknown_columns == ("Some new Studio column",)
    issue = result.issues_of(IngestionIssueKind.UNKNOWN_COLUMN)[0]
    assert issue.column == "Some new Studio column"
    assert issue.severity is IssueSeverity.WARNING
    assert "41" not in issue.reason


def test_every_unmapped_column_states_why_it_is_unmapped():
    for schema in STANDARD_STUDIO_SCHEMAS:
        for column in schema.columns:
            if not column.is_mapped:
                assert len(column.unmapped_reason) > 30, column.header


def test_the_net_subscriber_column_is_deliberately_not_mapped():
    """The registry splits gained from lost; splitting a net figure would invent."""
    column = STUDIO_VIDEO_TOTALS_V1.mapping_for("Subscribers")
    assert not column.is_mapped
    assert "net" in column.unmapped_reason
    assert {"subscribers_gained", "subscribers_lost"} <= {
        c.metric for c in STUDIO_VIDEO_TOTALS_V1.mapped_columns
    }


def test_a_column_may_not_claim_a_metric_of_an_incompatible_shape():
    with pytest.raises(AnalyticsError, match="cannot supply"):
        ColumnMapping("Views", ValueFormat.PERCENTAGE, "views")
    with pytest.raises(AnalyticsError, match="cannot supply"):
        ColumnMapping("Average view duration", ValueFormat.PERCENTAGE,
                      "average_view_duration_seconds")


def test_a_column_with_no_metric_must_give_a_reason():
    with pytest.raises(AnalyticsError, match="must say"):
        ColumnMapping("Mystery", ValueFormat.INTEGER)


# --------------------------------------------------------------------------
# Values: one conversion per shape, and no silent coercion
# --------------------------------------------------------------------------


def test_an_integer_column_reads_a_whole_count(export):
    assert value_of(ingest(export), "views") == 50000.0


def test_a_decimal_column_keeps_the_unit_the_column_is_already_in(export):
    """Watch time in hours stays hours; the metric name carries the unit."""
    result = ingest(export)
    assert value_of(result, "watch_time_hours") == 400.0
    watch = [o for o in result.observations if o.metric.name == "watch_time_hours"][0]
    assert watch.metric.unit == "hours"


def test_a_percentage_column_becomes_the_fraction_the_metric_is_defined_over(export):
    result = ingest(export)
    assert value_of(result, "click_through_rate") == 0.058
    assert value_of(result, "average_percentage_viewed") == 0.605
    ctr = [o for o in result.observations if o.metric.name == "click_through_rate"][0]
    assert ctr.metric.kind is MetricKind.RATE
    assert "0.0-1.0" in ctr.metric.unit


def test_a_percentage_viewed_above_one_hundred_survives_the_studio_door_too(tmp_path):
    """The looping-Short reading, arriving as a CSV cell instead of as JSON.

    `average_percentage_viewed` is reached from two directions - a Studio export
    and the Analytics API - and a ceiling restored on one side would be a defect
    the other side's tests could not see. The live pull that exposed this came
    through the API; this is the same number through the export.
    """
    row = TOTALS_ROW_14.replace(",0:18,60.5,", ",0:18,118.41,")
    result = ingest(totals_csv(tmp_path, row))
    assert value_of(result, "average_percentage_viewed") == pytest.approx(1.1841)
    assert parse_cell("118.41%", ValueFormat.PERCENTAGE, DOT_DECIMAL) == pytest.approx(1.1841)
    assert parse_cell("200", ValueFormat.PERCENTAGE, DOT_DECIMAL) == 2.0


def test_a_share_of_a_population_above_one_hundred_is_still_refused(tmp_path):
    """Lifting the cap for one metric did not lift it for click-through rate.

    More clicks than impressions is an export defect or a column read into the
    wrong metric, and either way it is not a reading.
    """
    row = TOTALS_ROW_14.replace(",900000,5.8,", ",900000,140.0,")
    result = ingest(totals_csv(tmp_path, row))
    assert "click_through_rate" not in {o.metric.name for o in result.observations}
    refused = [
        i for i in result.issues if i.kind is IngestionIssueKind.OBSERVATION_REFUSED
    ]
    assert refused and "unbounded_above" in refused[0].reason


def test_a_trailing_percent_sign_is_accepted_and_a_misplaced_one_is_not():
    assert parse_cell("12.4%", ValueFormat.PERCENTAGE, DOT_DECIMAL) == 0.124
    with pytest.raises(StudioValueError, match="other than the end"):
        parse_cell("1%2", ValueFormat.PERCENTAGE, DOT_DECIMAL)


def test_a_clock_duration_becomes_seconds(export):
    assert value_of(ingest(export), "average_view_duration_seconds") == 18.0
    assert parse_cell("1:02:03", ValueFormat.DURATION_CLOCK, DOT_DECIMAL) == 3723.0
    assert parse_cell("00:00:17", ValueFormat.DURATION_CLOCK, DOT_DECIMAL) == 17.0


def test_a_duration_that_is_not_a_clock_reading_is_refused():
    for text in ("17s", "0:75", "17", "0:17.5"):
        with pytest.raises(StudioValueError):
            parse_cell(text, ValueFormat.DURATION_CLOCK, DOT_DECIMAL)


def test_a_fractional_value_in_a_count_column_is_refused_not_rounded():
    with pytest.raises(StudioValueError, match="fractional part"):
        parse_cell("12.5", ValueFormat.INTEGER, DOT_DECIMAL)


def test_a_rate_arrives_with_the_denominator_from_its_own_column(export):
    result = ingest(export)
    ctr = [o for o in result.observations if o.metric.name == "click_through_rate"][0]
    assert ctr.denominator_value == 900000.0
    apv = [o for o in result.observations if o.metric.name == "average_percentage_viewed"][0]
    assert apv.denominator_value == 30.0  # the Duration column, read as seconds


def test_a_rate_whose_denominator_is_blank_is_still_recorded_with_its_caveat(tmp_path):
    row = TOTALS_ROW_14.replace(",900000,", ",,")
    result = ingest(totals_csv(tmp_path, row))
    ctr = [o for o in result.observations if o.metric.name == "click_through_rate"][0]
    assert ctr.denominator_value is None
    assert any("cannot be weighted" in caveat for caveat in ctr.caveats)


# --------------------------------------------------------------------------
# Blank is not zero
# --------------------------------------------------------------------------


def test_a_blank_cell_produces_no_observation_and_no_zero(tmp_path):
    row = TOTALS_ROW_14.replace(",1180,", ",,")  # Likes
    result = ingest(totals_csv(tmp_path, row))
    assert "likes" not in {o.metric.name for o in result.observations}
    blank = [i for i in result.issues_of(IngestionIssueKind.BLANK_VALUE) if i.column == "Likes"]
    assert blank and blank[0].row_number == 2
    assert blank[0].severity is IssueSeverity.NOTE


def test_an_explicit_zero_is_a_measurement_and_is_recorded(tmp_path):
    row = TOTALS_ROW_14.replace(",1180,", ",0,")
    result = ingest(totals_csv(tmp_path, row))
    assert value_of(result, "likes") == 0.0


def test_blank_and_zero_are_not_the_same_import(tmp_path):
    blank = ingest(totals_csv(tmp_path, TOTALS_ROW_14.replace(",1180,", ",,"), name="b.csv"))
    zero = ingest(totals_csv(tmp_path, TOTALS_ROW_14.replace(",1180,", ",0,"), name="z.csv"))
    assert len(zero.observations) == len(blank.observations) + 1


# --------------------------------------------------------------------------
# Locale: an ambiguous number is refused rather than chosen
# --------------------------------------------------------------------------


def test_a_grouped_number_is_ambiguous_under_the_default_format(tmp_path):
    row = TOTALS_ROW_14.replace(",50000,", ',"50,000",')
    result = ingest(totals_csv(tmp_path, row))
    issue = result.issues_of(IngestionIssueKind.AMBIGUOUS_NUMBER)[0]
    assert issue.column == "Views"
    assert issue.raw_value == "50,000"
    assert "factor of a thousand" in issue.reason
    assert "views" not in {o.metric.name for o in result.observations}


def test_the_same_number_reads_once_a_format_is_declared(tmp_path):
    row = TOTALS_ROW_14.replace(",50000,", ',"50,000",')
    result = ingest(totals_csv(tmp_path, row), number_format=EN_US_GROUPED)
    assert value_of(result, "views") == 50000.0
    assert not result.issues_of(IngestionIssueKind.AMBIGUOUS_NUMBER)


def test_the_two_locales_read_the_same_text_as_different_numbers():
    assert parse_cell("1.234", ValueFormat.DECIMAL, DOT_DECIMAL) == 1.234
    assert parse_cell("1.234", ValueFormat.INTEGER, EURO_GROUPED) == 1234.0


def test_grouping_is_verified_rather_than_stripped():
    with pytest.raises(StudioValueError, match="not grouped in thousands"):
        parse_cell("1.2345", ValueFormat.DECIMAL, EURO_GROUPED)


def test_the_number_format_that_read_the_file_is_recorded_on_the_source(export):
    assert ingest(export).source.number_format_name == "dot_decimal"
    assert ingest(export, number_format=EURO_GROUPED).source.number_format_name == (
        "euro_grouped"
    )


def test_a_format_cannot_use_one_character_for_both_roles():
    with pytest.raises(AnalyticsError, match="cannot read any number"):
        NumberFormat("broken", ".", ".")


# --------------------------------------------------------------------------
# Identity: a video id resolves a row, and a title never does
# --------------------------------------------------------------------------


def test_an_explicit_mapping_resolves_a_row_to_a_deliverable(export):
    result = ingest(export)
    assert result.deliverable_ids == ("race-short-014",)
    assert all(o.deliverable_id == "race-short-014" for o in result.observations)


def test_an_unmapped_video_is_reported_and_nothing_is_invented(tmp_path):
    row = TOTALS_ROW_14.replace(VIDEO_14, VIDEO_15)
    result = ingest(totals_csv(tmp_path, row))
    assert not result.observations
    assert [u.video_id for u in result.unresolved_videos] == [VIDEO_15]
    assert result.unresolved_videos[0].row_numbers == (2,)
    assert result.issues_of(IngestionIssueKind.UNRESOLVED_DELIVERABLE)


def test_the_title_of_an_unresolved_video_is_labelled_a_hint(tmp_path):
    row = TOTALS_ROW_14.replace(VIDEO_14, VIDEO_15)
    unresolved = ingest(totals_csv(tmp_path, row)).unresolved_videos[0]
    assert unresolved.title_hint == "Marble race 14"
    assert "title_hint" in unresolved.to_dict()


def test_a_title_in_the_identity_column_is_not_an_identity(tmp_path):
    row = TOTALS_ROW_14.replace(VIDEO_14, "Marble race 14", 1)
    result = ingest(totals_csv(tmp_path, row))
    assert not result.observations
    issue = result.issues_of(IngestionIssueKind.MISSING_VIDEO_ID)[0]
    assert "not an identity" in issue.reason
    assert issue.row_number == 2


def test_a_mapping_keyed_by_title_is_refused():
    with pytest.raises(AnalyticsError, match="not a YouTube video id"):
        VideoIdentityMapping(CHANNEL, (("Marble race 14", "race-short-014"),))


def test_two_videos_may_not_map_to_one_deliverable():
    with pytest.raises(AnalyticsError, match="more than one video id"):
        VideoIdentityMapping(
            CHANNEL, ((VIDEO_14, "race-short-014"), (VIDEO_15, "race-short-014"))
        )


def test_the_totals_row_is_not_a_video(export):
    result = ingest(export)
    aggregate = result.issues_of(IngestionIssueKind.AGGREGATE_ROW)
    assert [i.row_number for i in aggregate] == [2]
    assert value_of(result, "views") == 50000.0  # the video, not the 52000 total


def test_a_video_the_mapping_knows_but_the_store_does_not_is_reported(export):
    result = ingest(export, deliverables=())
    assert not result.observations
    issue = result.issues_of(IngestionIssueKind.MISSING_DELIVERABLE_RECORD)[0]
    assert issue.video_id == VIDEO_14
    assert "race-short-014" in issue.reason


def test_the_observation_retains_video_id_row_and_file(export):
    observation = ingest(export).observations[0]
    assert VIDEO_14 in observation.note
    assert "row 3" in observation.note
    assert "ys-2026-09-10" in observation.note
    trail = [e.note for e in observation.provenance.evidence]
    assert any("row 3" in note and "sha256:" in note for note in trail)


def test_one_row_per_video_per_window(tmp_path):
    result = ingest(totals_csv(tmp_path, TOTALS_ROW_14, TOTALS_ROW_14))
    duplicate = result.issues_of(IngestionIssueKind.DUPLICATE_ROW)
    assert [i.row_number for i in duplicate] == [3]
    assert result.rows_accepted == 1


# --------------------------------------------------------------------------
# Time: what a reading covers, honestly
# --------------------------------------------------------------------------


def test_a_cumulative_export_reads_at_the_instant_it_was_taken(export):
    result = ingest(export)
    assert all(o.observed_at == EXPORTED_AT for o in result.observations)
    assert all(o.age_hours == 54.0 for o in result.observations)


def test_a_cumulative_export_may_not_also_claim_a_date_range(export):
    with pytest.raises(StudioExportRejected, match="cumulative export"):
        ingest(export, reported_range=DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 10)))


def test_an_interval_export_must_say_which_days_it_covers(export):
    with pytest.raises(StudioExportRejected, match="which days"):
        ingest(export, semantics=TemporalSemantics.INTERVAL, reported_range=None)


def test_a_totals_export_refuses_to_guess_what_it_covers(export):
    with pytest.raises(StudioExportRejected, match="cannot say which this is"):
        ingest(export, semantics=None)


def daily_csv(tmp_path: Path, *rows: str, name: str = "Chart data.csv") -> Path:
    header = "Date,Content,Video title,Views,Likes"
    return write_csv(tmp_path, name, "\n".join((header, *rows)) + "\n")


def ingest_daily(path: Path, **kwargs):
    defaults = dict(
        reported_range=DateRange(dt.date(2026, 9, 9), dt.date(2026, 9, 11)),
        reporting_offset_minutes=0,
        semantics=None,
    )
    defaults.update(kwargs)
    return ingest(path, **defaults)


def test_a_per_day_row_is_measured_over_its_own_day(tmp_path):
    path = daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
    result = ingest_daily(path)
    views = [o for o in result.observations if o.metric.name == "views"][0]
    assert views.value == 12000.0
    # The instant the day's measurement closed, in the declared reporting zone.
    assert views.observed_at == dt.datetime(2026, 9, 10, 0, 0, tzinfo=UTC)
    assert "measured during 2026-09-09" in views.note


def test_a_per_day_report_needs_the_timezone_its_days_begin_in(tmp_path):
    path = daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
    with pytest.raises(StudioExportRejected, match="reporting timezone"):
        ingest_daily(path, reporting_offset_minutes=None)


def test_the_reporting_timezone_moves_the_day_boundary(tmp_path):
    path = daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
    shifted = ingest_daily(path, reporting_offset_minutes=-5 * 60)
    views = [o for o in shifted.observations if o.metric.name == "views"][0]
    assert views.observed_at == dt.datetime(2026, 9, 10, 5, 0, tzinfo=UTC)


def test_a_day_outside_the_declared_range_is_refused(tmp_path):
    path = daily_csv(tmp_path, f"2026-10-01,{VIDEO_14},Marble race 14,12000,300")
    result = ingest_daily(path)
    assert not result.observations
    assert result.issues_of(IngestionIssueKind.DATE_OUTSIDE_RANGE)[0].row_number == 2


def test_an_ambiguous_date_spelling_is_refused(tmp_path):
    path = daily_csv(tmp_path, f"09/10/2026,{VIDEO_14},Marble race 14,12000,300")
    result = ingest_daily(path)
    issue = result.issues_of(IngestionIssueKind.UNREADABLE_DATE)[0]
    assert "different day in different countries" in issue.reason


def test_a_reading_cannot_predate_the_video_it_measures(tmp_path):
    path = daily_csv(tmp_path, f"2026-09-01,{VIDEO_14},Marble race 14,12000,300")
    result = ingest_daily(
        path, reported_range=DateRange(dt.date(2026, 9, 1), dt.date(2026, 9, 11))
    )
    assert not result.observations
    assert result.issues_of(IngestionIssueKind.READING_BEFORE_PUBLICATION)


# --------------------------------------------------------------------------
# Snapshot against interval: section 12, kept apart by identity
# --------------------------------------------------------------------------


def test_an_interval_reading_carries_a_slice_a_cumulative_one_does_not(tmp_path, export):
    cumulative = ingest(export).observations[0]
    daily = ingest_daily(
        daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
    ).observations[0]
    assert cumulative.breakdown == ()
    assert daily.breakdown == (("measurement", "interval"),)


def test_views_through_a_day_and_views_during_it_are_different_measurements(tmp_path, export):
    cumulative = [o for o in ingest(export).observations if o.metric.name == "views"][0]
    interval = [
        o
        for o in ingest_daily(
            daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
        ).observations
        if o.metric.name == "views"
    ][0]
    assert cumulative.key != interval.key
    assert cumulative.snapshot_key != interval.snapshot_key


def test_an_interval_reading_is_kept_out_of_a_baseline(tmp_path, export):
    """`baseline.py` excludes any sliced reading; interval readings are sliced."""
    from company.analytics import DEFAULT_REGISTRY, FIRST_30D, summarise_metric

    interval = ingest_daily(
        daily_csv(tmp_path, f"2026-09-09,{VIDEO_14},Marble race 14,12000,300")
    ).observations
    cumulative = ingest(export).observations

    views = DEFAULT_REGISTRY.get("views")
    assert summarise_metric(views, ["race-short-014"], interval, FIRST_30D).count == 0
    assert summarise_metric(views, ["race-short-014"], cumulative, FIRST_30D).count == 1


def test_a_range_export_of_the_totals_report_is_also_an_interval(export):
    result = ingest(
        export,
        semantics=TemporalSemantics.INTERVAL,
        reported_range=DateRange(dt.date(2026, 9, 9), dt.date(2026, 9, 10)),
    )
    assert all(o.breakdown == (("measurement", "interval"),) for o in result.observations)
    assert "2026-09-09..2026-09-10" in result.observations[0].note


# --------------------------------------------------------------------------
# Money: finance-routed, never an analytics revenue figure
# --------------------------------------------------------------------------


def test_a_monetary_column_produces_no_observation(export):
    result = ingest(export)
    assert "Your estimated revenue (USD)" in result.monetary_columns
    assert "estimated_revenue" not in {o.metric.name for o in result.observations}
    assert not [o for o in result.observations if o.metric.kind is MetricKind.MONEY]


def test_a_monetary_column_is_reported_as_needing_finance_ingestion(export):
    issue = ingest(export).issues_of(IngestionIssueKind.MONETARY_COLUMN)[0]
    assert issue.column == "Your estimated revenue (USD)"
    assert "finance" in issue.reason


def test_the_monetary_value_is_not_even_quoted_in_the_diagnostic(export):
    """Section 25: an amount nobody needed to read does not reach a log."""
    issue = ingest(export).issues_of(IngestionIssueKind.MONETARY_COLUMN)[0]
    assert issue.raw_value == ""
    assert "12.10" not in str(issue)


def test_a_schema_may_not_map_a_monetary_column_to_a_metric():
    with pytest.raises(AnalyticsError, match="monetary column carries no analytics metric"):
        ColumnMapping("Your estimated revenue (USD)", ValueFormat.DECIMAL,
                      "estimated_revenue", monetary=True)


def test_the_money_metric_cannot_be_mapped_at_all():
    with pytest.raises(AnalyticsError, match="monetary metric"):
        ColumnMapping("Your estimated revenue (USD)", ValueFormat.DECIMAL,
                      "estimated_revenue")


def test_the_ingester_creates_no_finance_record_of_any_kind():
    source = "\n".join(path.read_text(encoding="utf-8") for path in STUDIO_MODULES)
    for forbidden in ("RevenueRecord", "CostRecord", "ProfitabilitySummary", "Money("):
        assert forbidden not in source, forbidden
    assert "company.finance" not in source


def test_no_finance_state_is_written_by_a_commit(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    written = {path.name for path in (tmp_path / "state").iterdir()}
    assert written == {"deliverables", "observations", "studio_sources", "ledger"}


# --------------------------------------------------------------------------
# Idempotence, conflict, and no silent overwrite
# --------------------------------------------------------------------------


def test_observation_ids_are_deterministic(export):
    first = [o.observation_id for o in ingest(export).observations]
    second = [o.observation_id for o in ingest(export).observations]
    assert first == second
    assert all(re.fullmatch(r"ys-[0-9a-f]{12}-[0-9a-f]{16}", i) for i in first)


def test_the_id_is_derived_from_the_file_digest(tmp_path, export):
    other = totals_csv(tmp_path, TOTALS_ROW_14, name="other.csv")
    assert ingest(export).source.digest != ingest(other).source.digest
    assert {o.observation_id for o in ingest(export).observations}.isdisjoint(
        {o.observation_id for o in ingest(other).observations}
    )


def test_replaying_the_same_export_writes_nothing_the_second_time(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    first = commit_ingestion(ingest(export), store)
    assert first.written and first.source_recorded

    replay = commit_ingestion(ingest(export), store)
    assert replay.wrote_nothing
    assert set(replay.already_present) == set(first.written)
    assert not replay.conflicts
    assert len(store.list("observation")) == len(first.written)


def test_a_replay_at_a_later_import_time_is_still_a_replay(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    later = ingest(export, imported_at=IMPORTED_AT + dt.timedelta(days=3))
    outcome = commit_ingestion(later, store)
    assert outcome.wrote_nothing
    assert store.get("studio_source", "ys-2026-09-10").imported_at == IMPORTED_AT


def test_a_second_export_disagreeing_about_one_reading_is_a_conflict(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)

    corrected = totals_csv(
        tmp_path, TOTALS_ROW_14.replace(",50000,", ",51000,"), name="corrected.csv"
    )
    result = ingest(corrected, source_id="ys-2026-09-10b")
    with pytest.raises(LedgerViolation, match="One of the two is wrong"):
        commit_ingestion(result, store)


def test_a_refused_conflict_writes_nothing_at_all(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    before = set(store.ids("observation"))

    corrected = totals_csv(
        tmp_path, TOTALS_ROW_14.replace(",50000,", ",51000,"), name="corrected.csv"
    )
    with pytest.raises(LedgerViolation):
        commit_ingestion(ingest(corrected, source_id="ys-b"), store)
    assert set(store.ids("observation")) == before


def test_a_conflict_may_be_skipped_but_never_overwrites(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    original = store.list("observation")

    corrected = totals_csv(
        tmp_path, TOTALS_ROW_14.replace(",50000,", ",51000,"), name="corrected.csv"
    )
    outcome = commit_ingestion(
        ingest(corrected, source_id="ys-b"), store, allow_conflicts=True
    )
    assert outcome.conflicts
    values = {o.value for o in store.list("observation") if o.metric.name == "views"}
    assert values == {50000.0}
    assert len(store.list("observation")) >= len(original)


def test_one_source_id_cannot_describe_two_files(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    other = totals_csv(tmp_path, TOTALS_ROW_14, name="other.csv")
    with pytest.raises(LedgerViolation, match="already recorded describing a different"):
        commit_ingestion(ingest(other), store)


def test_the_store_refuses_a_rewritten_observation(tmp_path, export):
    """The append-only guard underneath, independent of the ingester's check."""
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    result = ingest(export)
    store.put_all(result.observations)
    observation = result.observations[0]
    changed = type(observation)(
        **{**{f: getattr(observation, f) for f in observation.to_dict()}, "value": 1.0}
    )
    with pytest.raises(LedgerViolation):
        store.put(changed)


def test_an_import_leaves_the_store_internally_consistent(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    assert check_integrity(store) == ()


# --------------------------------------------------------------------------
# Dry run: the result is complete and the disk is untouched
# --------------------------------------------------------------------------


def test_a_dry_run_produces_the_observations_without_a_store(export):
    result = ingest(export)
    assert result.observations
    assert result.rows_read == 2 and result.rows_accepted == 1


def test_parsing_never_touches_a_state_directory(tmp_path, export):
    state = tmp_path / "state"
    ingest(export)
    assert not state.exists()


def test_the_dry_run_result_is_exactly_what_a_commit_writes(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    result = ingest(export)
    outcome = commit_ingestion(result, store)
    assert set(outcome.written) == {o.observation_id for o in result.observations}


def test_the_cli_dry_run_writes_nothing(tmp_path, export, capsys):
    from company.analytics.__main__ import main

    state = tmp_path / "state"
    AnalyticsStore(state).put(a_deliverable())
    mapping = tmp_path / "video_map.json"
    mapping.write_text(
        json.dumps({"channel_ref": CHANNEL, "videos": {VIDEO_14: "race-short-014"}}),
        encoding="utf-8",
    )
    argv = [
        "studio-import", str(export), "--mapping", str(mapping),
        "--source-id", "ys-cli", "--channel-ref", CHANNEL,
        "--exported-at", "2026-09-10T18:00:00+00:00",
        "--semantics", "cumulative_to_instant", "--state-dir", str(state),
    ]
    assert main(argv) == 0
    assert capsys.readouterr().out.count("nothing was written") == 1
    assert not (state / "observations").exists()

    assert main(argv + ["--commit"]) == 0
    assert (state / "observations").is_dir()
    assert len(AnalyticsStore(state).list("observation")) == 11


def test_the_cli_inspect_verb_writes_nothing_and_needs_no_provenance(export, capsys):
    from company.analytics.__main__ import main

    assert main(["studio-inspect", str(export)]) == 0
    printed = capsys.readouterr().out
    assert "studio_video_totals_v1" in printed
    assert "monetary columns need finance ingestion" in printed


def test_the_cli_refuses_to_commit_without_somewhere_to_write(tmp_path, export, capsys):
    from company.analytics.__main__ import main

    mapping = tmp_path / "video_map.json"
    mapping.write_text(
        json.dumps({"channel_ref": CHANNEL, "videos": {VIDEO_14: "race-short-014"}}),
        encoding="utf-8",
    )
    code = main([
        "studio-import", str(export), "--mapping", str(mapping),
        "--source-id", "ys-cli", "--channel-ref", CHANNEL,
        "--exported-at", "2026-09-10T18:00:00+00:00",
        "--semantics", "cumulative_to_instant", "--commit",
    ])
    assert code == 2
    assert "nowhere to append" in capsys.readouterr().out


# --------------------------------------------------------------------------
# Diagnostics: precise, and no wider than they need to be
# --------------------------------------------------------------------------


def test_a_parse_failure_names_the_file_row_column_and_raw_value(tmp_path):
    row = TOTALS_ROW_14.replace(",50000,", ",fifty thousand,")
    result = ingest(totals_csv(tmp_path, row))
    issue = result.issues_of(IngestionIssueKind.UNPARSEABLE_VALUE)[0]
    assert issue.row_number == 2
    assert issue.column == "Views"
    assert issue.raw_value == "fifty thousand"
    assert issue.video_id == VIDEO_14
    assert result.source.source_ref.endswith("Table data.csv")


def test_a_diagnostic_does_not_carry_the_rest_of_the_row(tmp_path):
    row = TOTALS_ROW_14.replace(",50000,", ",fifty thousand,")
    issue = ingest(totals_csv(tmp_path, row)).issues_of(
        IngestionIssueKind.UNPARSEABLE_VALUE
    )[0]
    rendered = str(issue)
    for other in ("900000", "1180", "12.10", "Marble race 14"):
        assert other not in rendered


def test_a_long_cell_is_truncated_in_a_diagnostic(tmp_path):
    row = TOTALS_ROW_14.replace(",50000,", f",{'9' * 300}x,")
    issue = ingest(totals_csv(tmp_path, row)).issues_of(
        IngestionIssueKind.UNPARSEABLE_VALUE
    )[0]
    assert len(issue.raw_value) <= 63 and issue.raw_value.endswith("...")


def test_the_result_reports_what_was_not_imported_as_well_as_what_was(tmp_path):
    header = f"{TOTALS_HEADER},Brand new column"
    rows = (
        f"{TOTALS_TOTAL_ROW},1",
        f"{TOTALS_ROW_14.replace(',1180,', ',,')},2",
        f"{TOTALS_ROW_14.replace(VIDEO_14, VIDEO_15)},3",
    )
    result = ingest(write_csv(tmp_path, "mixed.csv", "\n".join((header, *rows)) + "\n"))
    assert kinds(result) >= {
        IngestionIssueKind.AGGREGATE_ROW,
        IngestionIssueKind.BLANK_VALUE,
        IngestionIssueKind.UNRESOLVED_DELIVERABLE,
        IngestionIssueKind.UNKNOWN_COLUMN,
        IngestionIssueKind.MONETARY_COLUMN,
        IngestionIssueKind.UNMAPPED_COLUMN,
    }
    assert result.rows_read == 3 and result.rows_accepted == 1
    assert result.rows_rejected == 2


def test_the_rendered_summary_is_counts_and_references(export):
    rendered = ingest(export).render()
    assert "rows        2 read, 1 accepted" in rendered
    assert "sha256:" in rendered
    for reading in ("50000", "900000", "1180"):
        assert reading not in rendered


def test_no_import_can_report_only_that_it_succeeded(export):
    result = ingest(export)
    assert hasattr(result, "rows_read") and hasattr(result, "rows_accepted")
    assert "successful" not in result.render().lower()


# --------------------------------------------------------------------------
# The source record: pointers, never contents
# --------------------------------------------------------------------------


def test_the_source_record_carries_no_cell_of_data(export):
    encoded = json.dumps(ingest(export).source.to_dict())
    for reading in ("50000", "900000", "1180", "12.10", "Marble race 14"):
        assert reading not in encoded


def test_the_source_record_round_trips_through_the_store(tmp_path, export):
    store = AnalyticsStore(tmp_path / "state")
    store.put(a_deliverable())
    commit_ingestion(ingest(export), store)
    stored = store.get("studio_source", "ys-2026-09-10")
    assert isinstance(stored, StudioExportSource)
    assert stored.to_dict() == ingest(export).source.to_dict()
    assert stored.header[0] == "Content"


def test_the_source_names_the_parser_that_read_it(export):
    assert ingest(export).source.parser_version.startswith("studio-csv/")


def test_no_export_file_is_copied_into_the_repository():
    for path in (REPO_ROOT / "company").rglob("*.csv"):
        raise AssertionError(f"an export was committed: {path}")


# --------------------------------------------------------------------------
# Dashboard compatibility: ingested readings are ordinary observations
# --------------------------------------------------------------------------


def test_the_dashboard_reads_ingested_observations_like_any_other(tmp_path, export):
    from company.dashboard import CompanyStatePaths
    from company.dashboard.builder import _Reader

    paths = CompanyStatePaths.from_root(tmp_path / "company-state")
    store = AnalyticsStore(paths.analytics)
    store.put(a_deliverable())
    written = commit_ingestion(ingest(export), store).written

    result = _Reader(paths, dt.date(2026, 9, 17), REPO_ROOT).analytics()
    assert result.section.availability.value != "missing"
    assert not result.section.integrity_issues
    assert len(result.records["observation"]) == len(written)
    assert {o.deliverable_id for o in result.records["observation"]} == {"race-short-014"}


def test_an_ingested_observation_is_a_plain_metric_observation(export):
    from company.analytics import MetricObservation

    assert all(isinstance(o, MetricObservation) for o in ingest(export).observations)


def test_a_snapshot_over_many_observations_of_one_deliverable_keeps_them_apart(tmp_path):
    """Once a defect in company/dashboard, reproduced here without any import.

    `builder._record_id` used to read `deliverable_id` before `observation_id`,
    and a `MetricObservation` carries both - so every observation was keyed by
    the deliverable it is about, and a second reading of the same video
    collided. Two hand-built observations were enough to raise it, so it was
    never something the Studio import introduced; it was what the import ran
    into as soon as a snapshot was built over real analytics state.

    The dashboard now identifies a record by the field its store writes it
    under, so the readings stay apart. Kept as the import's own guard on the
    boundary it depends on.
    """
    from company.analytics import observe
    from company.dashboard import CompanyStatePaths, SourceSubsystem, build_snapshot

    paths = CompanyStatePaths.from_root(tmp_path / "company-state")
    store = AnalyticsStore(paths.analytics)
    deliverable = a_deliverable()
    store.put(deliverable)
    at = dt.datetime(2026, 9, 10, 18, tzinfo=UTC)
    for name, metric, value in (("a", "views", 50000.0), ("b", "likes", 1180.0)):
        store.put(
            observe(f"obs-{name}", deliverable, metric, value, at,
                    a_provenance(), DataScope(population="all viewers"))
        )
    snapshot = build_snapshot(sources=paths, as_of=dt.date(2026, 9, 17), repo_root=REPO_ROOT)
    keys = {r.key for r in snapshot.source_refs
            if r.subsystem is SourceSubsystem.ANALYTICS and r.kind == "observation"}
    assert keys == {"analytics:observation:obs-a", "analytics:observation:obs-b"}


# --------------------------------------------------------------------------
# Boundaries: nothing fetches, nothing scrapes, nothing new is imported
# --------------------------------------------------------------------------


def _studio_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in STUDIO_MODULES)


@pytest.mark.parametrize(
    "forbidden",
    ["socket", "urllib", "http.client", "requests", "httpx", "aiohttp", "ssl", "webbrowser"],
)
def test_the_ingester_cannot_make_a_network_call(forbidden):
    pattern = re.compile(rf"^\s*(from|import)\s+{re.escape(forbidden)}\b", re.MULTILINE)
    assert not pattern.search(_studio_source()), forbidden


@pytest.mark.parametrize(
    "forbidden",
    ["oauth", "access_token", "refresh_token", "client_secret", "api_key",
     "googleapis", "selenium", "playwright", "webdriver", "beautifulsoup",
     "urlopen", "def scrape", "fetch("],
)
def test_there_is_no_api_client_no_oauth_and_no_scraper(forbidden):
    """The names such machinery would have to use, none of which appears."""
    assert forbidden not in _studio_source().lower(), forbidden


def test_the_ingester_holds_no_credential_state():
    for name in ("password", "secret", "credential", "bearer", "token"):
        assert name not in _studio_source().lower(), name


def _imported_roots(path: Path) -> set[str]:
    """Top-level packages a module imports, read from its syntax tree.

    Parsed rather than matched with a regular expression, because prose in a
    docstring - "from opposite sides", "import the file by hand" - looks exactly
    like an import statement to a line-based pattern.
    """
    import ast

    roots: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_the_studio_modules_import_only_the_standard_library_and_company_os():
    allowed = {
        "__future__", "ai_platform", "collections", "company", "csv", "dataclasses",
        "datetime", "decimal", "enum", "hashlib", "io", "json", "knowledge",
        "pathlib", "re", "typing",
    }
    for path in STUDIO_MODULES:
        assert _imported_roots(path) <= allowed, path.name


def test_the_ingester_adds_no_third_party_dependency():
    declared = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    for package in ("pandas", "google-api", "oauth", "requests"):
        assert package not in declared


def test_the_ingester_touches_no_production_package():
    production = (
        "race2", "sloped", "marble3d", "engine", "modes", "powers", "godot",
        "production", "rendering", "replay", "race", "entities", "audio", "tools",
    )
    pattern = re.compile(
        r"^\s*(from|import)\s+(" + "|".join(production) + r")\b", re.MULTILINE
    )
    assert not pattern.search(_studio_source())


def test_the_no_nested_agent_invariant_is_untouched():
    pattern = re.compile(r"spawn_agent|child_agent|nested_delegation", re.IGNORECASE)
    assert not pattern.search(_studio_source())


# --------------------------------------------------------------------------
# The capsule
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seeds():
    from knowledge.company_os.capsules import SEED_ROOT, CapsuleIndex

    return CapsuleIndex.load(SEED_ROOT)


def test_the_analytics_capsule_still_fits_its_budget(seeds):
    from knowledge.company_os.capsules import DEFAULT_BUDGET

    capsule = seeds.get("company-analytics-experiments")
    assert capsule.size_chars() <= DEFAULT_BUDGET.max_capsule_chars
    assert capsule.owns_paths == ("company/analytics",)


def test_the_capsule_names_the_studio_import(seeds):
    capsule = seeds.get("company-analytics-experiments")
    joined = " ".join(capsule.inputs + capsule.outputs + (capsule.purpose,)).lower()
    assert "studio" in joined
    assert "tests/test_company_youtube_studio_ingestion.py" in capsule.tests


def test_the_capsule_dependencies_are_unchanged(seeds):
    capsule = seeds.get("company-analytics-experiments")
    assert capsule.dependencies == ("ai-platform", "company-knowledge-store")
    closure = seeds.dependency_closure("company-analytics-experiments")
    assert "company-analytics-experiments" not in closure


def test_the_control_plane_dependency_count_is_unchanged(seeds):
    control_plane = seeds.get("company-os-control-plane")
    assert len(control_plane.dependencies) <= 8
    assert "company-analytics-experiments" not in control_plane.dependencies


def test_the_seed_index_is_still_consistent(seeds):
    assert seeds.integrity() == ()


# --------------------------------------------------------------------------
# Downstream: a real import has to survive the read model
#
# Two exports of one video are the ordinary case - a video is read at a day and
# again three days later - and they produce two observations that share a
# deliverable_id. The CEO dashboard keys its source references by record
# identity, so this is the path that broke when it identified an observation by
# the deliverable it names. Ingestion owns neither the key nor the fix; this
# proves the pipeline end to end so the boundary cannot regress unnoticed.
# --------------------------------------------------------------------------


def test_two_studio_exports_of_one_video_reach_the_dashboard(tmp_path):
    from company.analytics.store import AnalyticsStore
    from company.dashboard import (Availability, CompanyStatePaths, SourceSubsystem,
                                   build_snapshot)

    paths = CompanyStatePaths.from_root(tmp_path / "company-state")
    store = AnalyticsStore(paths.analytics)
    store.put(a_deliverable())

    day_two = totals_csv(tmp_path, TOTALS_TOTAL_ROW, TOTALS_ROW_14, name="day-two.csv")
    day_five = totals_csv(
        tmp_path,
        "Total,,,,71000,590.5,1210000,5.9,0:18,61.4,1510,96,52,120,9,111,17.40",
        f"{VIDEO_14},Marble race 14,2026-09-08,0:30,69000,580.0,1200000,6.0,0:18,"
        "60.9,1490,92,50,115,8,107,17.05",
        name="day-five.csv",
    )
    later = EXPORTED_AT + dt.timedelta(days=3)
    first = ingest(day_two, source_id="ys-2026-09-10")
    second = ingest(day_five, source_id="ys-2026-09-13", exported_at=later,
                    imported_at=later + dt.timedelta(minutes=5))

    commit_ingestion(first, store)
    commit_ingestion(second, store)

    stored = store.list("observation")
    views = [o for o in stored if o.metric.name == "views"]
    assert len(views) == 2, "two exports of one video are two readings"
    assert {o.deliverable_id for o in views} == {"race-short-014"}
    assert len({o.observation_id for o in views}) == 2
    assert {o.value for o in views} == {50000.0, 69000.0}

    snapshot = build_snapshot(sources=paths, as_of=dt.date(2026, 9, 17), repo_root=REPO_ROOT)

    refs = [r for r in snapshot.source_refs
            if r.subsystem is SourceSubsystem.ANALYTICS and r.kind == "observation"]
    assert len(refs) == len(stored)
    assert len({r.key for r in refs}) == len(refs), "no reading was collapsed onto another"
    assert {r.record_id for r in refs} == {o.observation_id for o in stored}
    assert all(r.record_id.startswith("ys-") for r in refs)
    assert snapshot.section("analytics").availability is Availability.AVAILABLE
    assert not snapshot.unresolved_integrity_issues
