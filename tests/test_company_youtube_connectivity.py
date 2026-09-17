"""Ingesting a sanitized YouTube API artifact, with no network anywhere in reach.

Everything here reads a JSON fixture built in-process. Nothing imports
`tools.youtube_fetch`, which is the production half holding the credentials, and
nothing imports the integration gate's internals: the boundary is checked
through `company.integration.boundary`, the public surface, so this file keeps
working when the gate is rewritten.

The four properties these tests are really about:

* a reading from a bounded API window can never collide with a cumulative
  Studio reading of the same video and metric,
* two pulls of the same numbers produce byte-identical records, so a replay
  writes nothing,
* a revised number is a conflict that writes nothing rather than a second row,
* what the pull did not get is named, and what the API did not report stays
  unavailable instead of becoming a zero.
"""

from __future__ import annotations

import copy
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

import pytest

from company.analytics import (
    AnalyticsStore,
    ApiArtifactSource,
    DataScope,
    DataSource,
    DeliverableKind,
    LedgerViolation,
    Provenance,
    observe,
)
from company.integration.boundary import (
    NETWORK_MODULES,
    PROCESS_MODULES,
    forbidden_import_violations,
)
from company.integration.sources import parse_tree
from company.youtube import (
    ArtifactRejected,
    ArtifactUnreadable,
    DeliverableAssignment,
    YouTubeEvidenceStore,
    artifact_digest,
    build_deliverable,
    commit_ingestion,
    describe_artifact,
    ingest_artifact,
    parse_artifact,
    read_artifact,
)
from company.analytics.studio_ingest import IngestionIssueKind, IssueSeverity
from company.youtube.store import CANONICAL_FIELDS
from knowledge.company_os.records import Evidence

UTC = dt.timezone.utc
ROOT = Path(__file__).resolve().parents[1]

DATA_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"

# Import roots no Company OS module may reach for. `ctypes` is on the list
# because the Windows credential protector used to import it, and it is every
# capability at once.
FORBIDDEN_ROOTS = NETWORK_MODULES | PROCESS_MODULES | frozenset({"ctypes"})

ASSIGNMENTS = {
    "abcDEF_1": DeliverableAssignment(
        deliverable_id="test-1",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    )
}


# -- fixtures --------------------------------------------------------------


def reading(name, source_metric, unit, value, *, available=True, reason=""):
    return {
        "name": name,
        "source_metric": source_metric,
        "unit": unit,
        "value": value,
        "available": available,
        "unavailable_reason": reason,
    }


def default_metrics(views=100):
    return [
        reading("views", "views", "views", views),
        reading(
            "estimated_minutes_watched", "estimatedMinutesWatched", "minutes", 90.0
        ),
        reading(
            "comments",
            "comments",
            "comments",
            None,
            available=False,
            reason="API returned no rows for the requested range",
        ),
    ]


def artifact_mapping(
    *,
    fetched_at="2026-09-17T10:00:00+00:00",
    latency_ms=37,
    metrics=None,
    scopes=(DATA_SCOPE, ANALYTICS_SCOPE),
    retrieval=None,
    analytics_complete=True,
    analytics_excludes=(),
    video_id="abcDEF_1",
    extra_reports=(),
):
    """One artifact exactly as section 1 of the contract describes it."""
    return {
        "artifact_version": 1,
        "producer": "tools.youtube_fetch",
        "producer_version": "1.0",
        "fetched_at": fetched_at,
        "granted_scopes": list(scopes),
        "channel": {
            "channel_id": "UC-company",
            "channel_title": "Simulation Factory",
            "subscriber_count": 1234,
            "subscriber_count_unavailable_reason": "",
            "video_count": 7,
            "view_count": 45678,
            "uploads_playlist_id": "UU-company",
            "source": "youtube_data_api_v3.channels.list",
        },
        "videos": [
            {
                "video_id": "abcDEF_1",
                "channel_id": "UC-company",
                "title": "Test 1",
                "published_at": "2026-09-10T08:00:00+00:00",
                "duration": "PT1M2S",
                "duration_seconds": 62,
                "privacy_status": "public",
                "upload_status": "processed",
                "source": "youtube_data_api_v3.videos.list",
            }
        ],
        "video_retrieval": retrieval
        or {
            "requested": 1,
            "returned": 1,
            "complete": True,
            "pages_followed": 1,
            "missing_video_ids": [],
            "notes": [],
        },
        "analytics": [
            {
                "channel_id": "UC-company",
                "video_id": video_id,
                "start_date": "2026-09-01",
                "end_date": "2026-09-16",
                "temporal_semantics": "interval",
                "source": "youtube_analytics_api_v2.reports.query",
                "complete": analytics_complete,
                "excludes": list(analytics_excludes),
                "metrics": default_metrics() if metrics is None else metrics,
            },
            *extra_reports,
        ],
        "api_calls": [
            {
                "method": "GET",
                "endpoint": "https://youtubeanalytics.googleapis.com/v2/reports",
                "status": 200,
                "response_bytes": 412,
                "latency_ms": latency_ms,
                "succeeded": True,
                "error_kind": "",
            }
        ],
    }


def write_artifact(path: Path, mapping) -> Path:
    path.write_text(
        json.dumps(mapping, sort_keys=True, ensure_ascii=False), encoding="utf-8"
    )
    return path


def ingest(mapping, **kwargs):
    return ingest_artifact(
        parse_artifact(mapping), assignments=ASSIGNMENTS, **kwargs
    )


def observation_named(result, metric: str):
    return next(o for o in result.observations if o.metric.name == metric)


# -- the artifact is validated, not trusted --------------------------------


def test_a_well_formed_artifact_becomes_records():
    artifact = parse_artifact(artifact_mapping())
    assert artifact.channel_ref == "youtube:channel:UC-company"
    assert artifact.video("abcDEF_1").duration_seconds == 62
    assert artifact.complete is True
    assert artifact.analytics[0].metric("views").value == 100
    assert artifact.analytics[0].unavailable[0].name == "comments"


def test_an_unrecognised_top_level_key_is_refused_rather_than_ignored():
    mapping = artifact_mapping()
    mapping["estimated_revenue"] = {"amount": 12}
    with pytest.raises(ArtifactRejected) as error:
        parse_artifact(mapping)
    assert "estimated_revenue" in str(error.value)


def test_an_artifact_version_this_parser_does_not_know_is_refused():
    mapping = artifact_mapping()
    mapping["artifact_version"] = 2
    with pytest.raises(ArtifactRejected):
        parse_artifact(mapping)


def test_a_grant_wider_or_narrower_than_the_two_read_only_scopes_is_refused():
    narrow = artifact_mapping(scopes=(DATA_SCOPE,))
    with pytest.raises(ArtifactRejected) as missing:
        parse_artifact(narrow)
    assert "yt-analytics.readonly" in str(missing.value)

    wide = artifact_mapping(
        scopes=(
            DATA_SCOPE,
            ANALYTICS_SCOPE,
            "https://www.googleapis.com/auth/yt-analytics-monetary.readonly",
        )
    )
    with pytest.raises(ArtifactRejected) as extra:
        parse_artifact(wide)
    assert "monetary" in str(extra.value)


def test_an_endpoint_that_kept_its_query_string_is_refused():
    mapping = artifact_mapping()
    mapping["api_calls"][0]["endpoint"] = (
        "https://youtubeanalytics.googleapis.com/v2/reports?access_token=secret"
    )
    with pytest.raises(ArtifactRejected) as error:
        parse_artifact(mapping)
    assert "query string" in str(error.value)


def test_a_credential_key_at_any_depth_is_refused_without_quoting_the_value():
    mapping = artifact_mapping()
    mapping["raw"] = {"reports.query": {"refresh_token": "sensitive-value"}}
    with pytest.raises(ArtifactRejected) as error:
        parse_artifact(mapping)
    assert "refresh_token" in str(error.value)
    assert "sensitive-value" not in str(error.value)


def test_an_available_metric_with_no_value_is_a_contradiction():
    mapping = artifact_mapping(
        metrics=[reading("views", "views", "views", None, available=True)]
    )
    with pytest.raises(ArtifactRejected):
        parse_artifact(mapping)


def test_a_missing_file_is_a_different_failure_from_a_bad_one(tmp_path):
    with pytest.raises(ArtifactUnreadable):
        read_artifact(tmp_path / "absent.json")
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ArtifactUnreadable):
        read_artifact(bad)


# -- requirement 4: an interval reading cannot collide with a cumulative one --


def test_an_interval_reading_and_a_cumulative_one_have_different_keys():
    """The same video and the same metric, measured two incompatible ways."""
    artifact = parse_artifact(artifact_mapping())
    result = ingest_artifact(artifact, assignments=ASSIGNMENTS)
    api_views = observation_named(result, "views")

    deliverable = build_deliverable(
        artifact.video("abcDEF_1"),
        deliverable_id="test-1",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    )
    studio_views = observe(
        "studio-views-1",
        deliverable,
        "views",
        100,
        dt.datetime(2026, 9, 17, 9, 0, tzinfo=UTC),
        Provenance(
            source=DataSource.OWN_STUDIO_EXPORT,
            retrieved_by="youtube studio csv export, downloaded by hand",
            evidence=(
                Evidence(kind="document", ref="exports/videos.csv", note="sha256:abc"),
            ),
        ),
        DataScope(population="all viewers counted by the channel's own export"),
    )

    assert api_views.deliverable_id == studio_views.deliverable_id
    assert api_views.metric.name == studio_views.metric.name
    assert api_views.key != studio_views.key
    assert api_views.key.endswith("|measurement=interval")
    assert studio_views.breakdown == ()


# -- requirement 5: identity is content, so a replay is a no-op -------------


def test_observation_identity_ignores_the_file_and_the_fetch_instant(tmp_path):
    first = ingest(artifact_mapping())
    second = ingest(artifact_mapping(fetched_at="2026-09-18T23:59:00+00:00", latency_ms=910))

    assert [o.observation_id for o in first.observations] == [
        o.observation_id for o in second.observations
    ]
    assert first.source.source_id == second.source.source_id
    assert first.source.digest == second.source.digest
    assert [o.to_dict() for o in first.observations] == [
        o.to_dict() for o in second.observations
    ]


def test_observed_at_is_when_the_window_closed_not_when_we_looked():
    result = ingest(artifact_mapping())
    views = observation_named(result, "views")
    assert views.observed_at == dt.datetime(2026, 9, 17, 0, 0, tzinfo=UTC)
    assert views.provenance.evidence[0].ref.startswith("youtube-api:")
    assert "2026-09-17T10:00" not in json.dumps(views.to_dict())


def test_re_ingesting_the_same_pull_writes_nothing(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    result = ingest(artifact_mapping())
    first = commit_ingestion(result, store)
    assert len(first.written) == 2
    assert first.source_recorded is True
    assert first.deliverables_written == ("test-1",)

    ledger_before = store.ledger()
    second = commit_ingestion(ingest(artifact_mapping()), store)
    assert second.wrote_nothing
    assert set(second.already_present) == set(first.written)
    assert store.ledger() == ledger_before


def test_a_second_file_of_the_same_pull_is_the_same_reading(tmp_path):
    """Different file, different fetch instant, identical numbers."""
    store = AnalyticsStore(tmp_path / "state")
    write_artifact(tmp_path / "first.json", artifact_mapping())
    write_artifact(
        tmp_path / "second.json",
        artifact_mapping(fetched_at="2026-09-20T04:05:06+00:00", latency_ms=1200),
    )

    first = ingest_artifact(
        read_artifact(tmp_path / "first.json"), assignments=ASSIGNMENTS
    )
    commit_ingestion(first, store)
    before = {i: store.get("observation", i).to_dict() for i in store.ids("observation")}

    second = ingest_artifact(
        read_artifact(tmp_path / "second.json"), assignments=ASSIGNMENTS
    )
    outcome = commit_ingestion(second, store)

    assert outcome.wrote_nothing
    assert len(outcome.already_present) == 2
    assert store.ids("api_source") == (first.source.source_id,)
    assert {
        i: store.get("observation", i).to_dict() for i in store.ids("observation")
    } == before


def test_a_revised_value_is_a_conflict_that_writes_nothing(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    commit_ingestion(ingest(artifact_mapping()), store)
    stored_ids = store.ids("observation")
    ledger_before = store.ledger()

    revised = ingest(artifact_mapping(metrics=default_metrics(views=118)))
    with pytest.raises(LedgerViolation) as error:
        commit_ingestion(revised, store)
    assert "100" in str(error.value) and "118" in str(error.value)

    views = next(
        store.get("observation", i)
        for i in store.ids("observation")
        if store.get("observation", i).metric.name == "views"
    )
    assert views.value == 100.0
    assert store.ids("observation") == stored_ids
    assert store.ledger() == ledger_before
    assert len(store.ids("api_source")) == 1


def test_a_recorded_source_round_trips_through_the_store(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    result = ingest(artifact_mapping())
    commit_ingestion(result, store)
    stored = store.get("api_source", result.source.source_id)
    assert isinstance(stored, ApiArtifactSource)
    assert stored.to_dict() == result.source.to_dict()
    assert stored.granted_scopes == (DATA_SCOPE, ANALYTICS_SCOPE)
    assert stored.coverage_key == "interval@2026-09-01..2026-09-16"


# -- requirement 6: what is missing is named, and never zero ----------------


def test_an_incomplete_retrieval_names_the_exact_missing_ids():
    mapping = artifact_mapping(
        retrieval={
            "requested": 10,
            "returned": 1,
            "complete": False,
            "pages_followed": 2,
            "missing_video_ids": ["ghiJKL_2", "mnoPQR_3"],
            "notes": ["playlistItems.list listed ids videos.list did not return"],
        }
    )
    result = ingest(mapping)
    scope = observation_named(result, "views").scope
    assert scope.complete is False
    assert any(
        "ghiJKL_2, mnoPQR_3" in text and "2 of 10" in text for text in scope.excludes
    )
    assert result.source.complete is False
    assert scope.limitations == (
        "YouTube Analytics data can be delayed or revised after retrieval.",
    )


def test_an_incomplete_analytics_row_set_marks_every_reading_it_produced():
    result = ingest(
        artifact_mapping(
            analytics_complete=False,
            analytics_excludes=("traffic from embedded players was not returned",),
        )
    )
    scope = observation_named(result, "views").scope
    assert scope.complete is False
    assert scope.excludes == (
        "youtube:video:abcDEF_1: traffic from embedded players was not returned",
    )


def test_an_unavailable_metric_produces_no_observation_and_no_zero():
    result = ingest(artifact_mapping())
    assert {o.metric.name for o in result.observations} == {
        "views",
        "watch_time_hours",
    }
    assert [u.metric for u in result.unavailable] == ["comments"]
    assert result.unavailable[0].reason == "API returned no rows for the requested range"
    assert all(o.value != 0 for o in result.observations)
    assert result.readings_read == 3
    assert result.readings_accepted == 2


def test_an_incomplete_pull_is_visible_before_anything_is_committed(tmp_path):
    mapping = artifact_mapping(
        retrieval={
            "requested": 3,
            "returned": 1,
            "complete": False,
            "pages_followed": 1,
            "missing_video_ids": ["ghiJKL_2", "mnoPQR_3"],
            "notes": [],
        }
    )
    description = describe_artifact(parse_artifact(mapping))
    assert description.complete is False
    assert any("ghiJKL_2" in text for text in description.excludes)
    rendered = description.render()
    assert "100" not in rendered  # no reading is ever printed
    assert "comments" in rendered  # but the unavailable metric is named


# -- the vocabulary, and what falls outside it -----------------------------


def test_watch_time_is_converted_from_the_minutes_the_api_reported():
    result = ingest(artifact_mapping())
    watch = observation_named(result, "watch_time_hours")
    assert watch.value == pytest.approx(1.5)
    assert "dividing by 60" in watch.note


def test_a_percentage_reading_carries_the_video_length_as_its_denominator():
    result = ingest(
        artifact_mapping(
            metrics=[
                reading(
                    "average_view_percentage",
                    "averageViewPercentage",
                    "fraction",
                    0.755,
                )
            ]
        )
    )
    percentage = observation_named(result, "average_percentage_viewed")
    assert percentage.denominator_value == 62.0
    assert percentage.has_known_denominator


def test_an_unknown_metric_name_is_reported_rather_than_guessed_at():
    result = ingest(
        artifact_mapping(
            metrics=[reading("estimated_revenue", "estimatedRevenue", "usd", 4.2)]
        )
    )
    assert result.observations == ()
    assert result.unknown_metrics == ("estimated_revenue",)
    assert result.warnings and "no registry metric" in result.warnings[0].reason


def test_a_channel_wide_row_set_and_an_unassigned_video_are_reported(tmp_path):
    """Two refusals that look alike and are not.

    Neither produces an observation, and that is where the resemblance ends. An
    unassigned video is a gap somebody has to close: a mapping is missing, and
    until it arrives real readings have nowhere to go. A channel-wide row set is
    not a gap at all - it is a correct measurement at a level this ledger does
    not record, it arrives on every single pull, and no assignment will ever
    make it into a deliverable. So one is an error and the other is a note, and
    the channel's numbers are retained as evidence rather than dropped.

    `tests/test_company_youtube_live_findings.py` has the rest of it; this is
    the part that belongs beside the other ingestion refusals.
    """
    result = ingest(artifact_mapping(video_id=None))
    assert result.observations == ()
    assert result.errors == ()
    assert len(result.channel_reports) == 1
    assert result.channel_reports[0].subject_ref.startswith("youtube:channel:")
    note = result.issues_of(IngestionIssueKind.AGGREGATE_ROW)[0]
    assert note.severity is IssueSeverity.NOTE
    assert "channel-wide" in note.reason

    unassigned = ingest_artifact(parse_artifact(artifact_mapping()), assignments={})
    assert unassigned.observations == ()
    assert unassigned.unassigned_videos == ("abcDEF_1",)
    assert unassigned.errors and "no assignment" in unassigned.errors[0].reason


# -- requirement 13: the evidence envelope carries one digest ---------------


def test_the_evidence_envelope_is_digested_once_over_a_written_down_basis(tmp_path):
    artifact = parse_artifact(artifact_mapping())
    pointer = YouTubeEvidenceStore(tmp_path / "state").append(
        artifact, ingested_from="pulls/2026-09-17.json"
    )
    record = YouTubeEvidenceStore(tmp_path / "state").records()[0]

    assert pointer.record_ref.startswith("youtube/evidence/")
    assert record["evidence_id"] == f"youtube-{pointer.fingerprint}"
    assert set(record) == set(CANONICAL_FIELDS) | {"evidence_id"}

    from ai_platform.serde import fingerprint

    basis = {key: record[key] for key in CANONICAL_FIELDS}
    assert fingerprint(basis) == pointer.fingerprint
    assert record["artifact_digest"] == artifact_digest(artifact)
    assert record["normalized"]["channel"]["channel_id"] == "UC-company"


def test_the_semantic_digest_ignores_the_pull_and_notices_the_numbers():
    base = parse_artifact(artifact_mapping())
    same_numbers = parse_artifact(
        artifact_mapping(fetched_at="2027-01-01T00:00:00+00:00", latency_ms=5)
    )
    different_numbers = parse_artifact(
        artifact_mapping(metrics=default_metrics(views=101))
    )
    assert artifact_digest(base) == artifact_digest(same_numbers)
    assert artifact_digest(base) != artifact_digest(different_numbers)


# -- the boundary this whole rewrite exists to restore ----------------------


def test_company_youtube_imports_no_network_module():
    modules, failures = parse_tree(ROOT, ("company",))
    assert failures == ()
    youtube = [m for m in modules if m.path.startswith("company/youtube/")]
    assert len(youtube) >= 6
    assert (
        forbidden_import_violations(
            youtube, FORBIDDEN_ROOTS, "Company OS holds no network capability"
        )
        == ()
    )


def test_no_credential_or_token_file_is_tracked():
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True
    ).stdout.splitlines()
    forbidden_names = re.compile(
        r"(^|/)(\.env($|\.)|client_secret[^/]*\.json$|youtube-token[^/]*\.json$|token\.json$)",
        re.IGNORECASE,
    )
    assert not [path for path in tracked if forbidden_names.search(path)]
    api_key = re.compile(r"AIza[0-9A-Za-z_-]{30,}")
    assert not [
        path
        for path in tracked
        if Path(ROOT / path).is_file()
        and api_key.search(Path(ROOT / path).read_text(encoding="utf-8", errors="ignore"))
    ]


def test_gitignore_covers_local_youtube_secrets():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", ".secrets/", "client_secret*.json", "youtube-token*.json"):
        assert pattern in ignored


def test_the_fixture_in_this_file_is_the_artifact_the_contract_describes():
    """A guard on the tests themselves: a fixture that drifts proves nothing."""
    mapping = artifact_mapping()
    assert copy.deepcopy(mapping) == mapping
    assert set(mapping) == {
        "artifact_version",
        "producer",
        "producer_version",
        "fetched_at",
        "granted_scopes",
        "channel",
        "videos",
        "video_retrieval",
        "analytics",
        "api_calls",
    }
    assert "?" not in mapping["api_calls"][0]["endpoint"]
