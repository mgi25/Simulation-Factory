"""The two halves, run into each other over a real file on disk.

## Why this file exists at all

`tests/test_youtube_fetch.py` proves the fetcher writes what it says it writes.
`tests/test_company_youtube_connectivity.py` proves the ingester reads what it
says it reads. Both are written against the same paragraph of a design note,
and a paragraph is exactly the kind of interface that two correct halves can
disagree about: a field spelled `missing_video_ids` on one side and
`missing_ids` on the other passes both suites and fails in the only run that
matters.

So this file never builds an artifact by hand. It drives the real fetcher
against scripted Google responses, lets it write a real file, and hands that
file's path to the real ingester. The artifact format is not asserted here -
it is *used*, which is the only assertion that cannot drift.

## The three behaviours that only exist end to end

Replay, revision and incompleteness are all properties of two pulls, or of a
pull and a store. None of them can be demonstrated inside either half:

  * **Replay.** Two separate fetches, minutes apart, of the same window with the
    same numbers must produce byte-identical observations. That is a claim about
    the fetcher's clock *not* reaching the ingester's record, and it is only
    falsifiable if a real second fetch happens.
  * **Revision.** YouTube restates recent figures. The same window fetched again
    at a different number must be refused, not appended beside the first, and
    the store must be untouched afterwards.
  * **Incompleteness.** A short `videos.list` has to survive as far as a
    `DataScope(complete=False)` naming the exact id, through the artifact, the
    parser and the bridge.

## This module is named `test_company_*` deliberately

It imports Company OS, and `architecture.production_tests_independent` requires
every test that does to carry that prefix, so the production suite still runs
with the control plane removed. It also imports `tools.youtube_fetch`, which is
allowed in that direction: a Company OS test may read a production tool, and the
check that matters is the one that stops production depending on Company OS.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pytest

from company.analytics import AnalyticsStore, DeliverableKind
from company.analytics.errors import LedgerViolation
from company.youtube import (
    DeliverableAssignment,
    commit_ingestion,
    ingest_artifact,
    read_artifact,
)
from tools.youtube_fetch.api import ANALYTICS_API_METRICS, YouTubeReader
from tools.youtube_fetch.artifact import FetchRequest, fetch_artifact, write_artifact
from tools.youtube_fetch.config import REQUIRED_SCOPES, OAuthConfig
from tools.youtube_fetch.oauth import OAuthClient, StoredGrant, TokenStore
from tools.youtube_fetch.secrets_ import FilePermissionProtector
from tools.youtube_fetch.transport import (
    HttpResponse,
    InstrumentedTransport,
    endpoint_of,
)


UTC = dt.timezone.utc

CLIENT_SECRET = "SENTINEL-e2e-client-secret"
REFRESH_TOKEN = "SENTINEL-e2e-refresh-token"
ACCESS_TOKEN = "SENTINEL-e2e-access-token"
SENTINELS = (CLIENT_SECRET, REFRESH_TOKEN, ACCESS_TOKEN)

START = dt.date(2026, 9, 1)
END = dt.date(2026, 9, 16)
VIDEO_ID = "abcDEF_1"
SECOND_VIDEO_ID = "abcDEF_2"

TOKEN_KEY = "POST https://oauth2.googleapis.com/token"
CHANNELS_KEY = "GET https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_KEY = "GET https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_KEY = "GET https://www.googleapis.com/youtube/v3/videos"
REPORTS_KEY = "GET https://youtubeanalytics.googleapis.com/v2/reports"

# What the provider reports for the window, before any revision.
BASE_METRICS = {
    "views": 100,
    "estimatedMinutesWatched": 240,
    "averageViewDuration": 62,
    "averageViewPercentage": 45.6,
    "subscribersGained": 12,
    "subscribersLost": 3,
    "likes": 40,
    "comments": 5,
    "shares": 7,
}


class ScriptedTransport:
    """Answers by `METHOD endpoint`; the last queued response for a key sticks."""

    def __init__(self) -> None:
        self.routes: dict[str, list[HttpResponse]] = {}

    def queue(self, key: str, status: int, payload: Any) -> "ScriptedTransport":
        self.routes.setdefault(key, []).append(
            HttpResponse(status, json.dumps(payload).encode("utf-8"), {})
        )
        return self

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        key = f"{method.upper()} {endpoint_of(url)}"
        queued = self.routes.get(key)
        if not queued:
            raise AssertionError(f"no scripted response for {key}")
        return queued.pop(0) if len(queued) > 1 else queued[0]


def _channels() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": "UC-company",
                "snippet": {"title": "Simulation Factory"},
                "statistics": {
                    "subscriberCount": "1234",
                    "videoCount": "7",
                    "viewCount": "45678",
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU-company"}},
            }
        ]
    }


def _playlist(video_ids: Sequence[str]) -> dict[str, Any]:
    return {"items": [{"contentDetails": {"videoId": v}} for v in video_ids]}


def _videos(video_ids: Sequence[str]) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": video_id,
                "snippet": {
                    "title": f"Video {video_id}",
                    "publishedAt": "2026-09-10T08:00:00Z",
                },
                "contentDetails": {"duration": "PT1M2S"},
                "status": {"privacyStatus": "public", "uploadStatus": "processed"},
            }
            for video_id in video_ids
        ]
    }


def _reports(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "columnHeaders": [
            {"name": name, "columnType": "METRIC"} for name in ANALYTICS_API_METRICS
        ],
        "rows": [[values.get(name, 0) for name in ANALYTICS_API_METRICS]],
    }


def fetch_to_file(
    tmp_path: Path,
    destination: Path,
    *,
    fetched_at: dt.datetime,
    metrics: Mapping[str, Any] | None = None,
    playlist_ids: Sequence[str] = (VIDEO_ID,),
    returned_ids: Sequence[str] | None = None,
) -> Path:
    """Run the real fetcher against scripted Google responses and write the artifact."""
    token_path = tmp_path / f"token-{destination.stem}.json"
    config = OAuthConfig(
        client_id="client-id.apps.googleusercontent.com",
        client_secret=CLIENT_SECRET,
        redirect_uri="http://127.0.0.1:8731/oauth2/callback",
        token_path=token_path,
    )
    store = TokenStore(token_path, FilePermissionProtector())
    store.save(StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES))

    fake = ScriptedTransport()
    fake.queue(
        TOKEN_KEY,
        200,
        {
            "access_token": ACCESS_TOKEN,
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": " ".join(REQUIRED_SCOPES),
        },
    )
    fake.queue(CHANNELS_KEY, 200, _channels())
    fake.queue(PLAYLIST_KEY, 200, _playlist(playlist_ids))
    fake.queue(
        VIDEOS_KEY,
        200,
        _videos(playlist_ids if returned_ids is None else returned_ids),
    )
    fake.queue(REPORTS_KEY, 200, _reports(dict(BASE_METRICS, **(metrics or {}))))

    transport = InstrumentedTransport(fake)
    oauth = OAuthClient(config, transport, store, now=lambda: fetched_at)
    reader = YouTubeReader(oauth, transport)
    payload = fetch_artifact(
        reader,
        FetchRequest(
            start_date=START,
            end_date=END,
            video_limit=len(playlist_ids),
            video_analytics=True,
        ),
        fetched_at=fetched_at,
    )
    return write_artifact(payload, destination, secret_values=SENTINELS)


ASSIGNMENTS = {
    VIDEO_ID: DeliverableAssignment(
        deliverable_id="e2e-video-1",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    ),
    SECOND_VIDEO_ID: DeliverableAssignment(
        deliverable_id="e2e-video-2",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    ),
}


def ingest_file(path: Path, store: AnalyticsStore):
    artifact = read_artifact(path)
    result = ingest_artifact(artifact, assignments=ASSIGNMENTS)
    return result, commit_ingestion(result, store)


# -- the artifact the fetcher actually writes -------------------------------


def test_the_written_artifact_carries_no_credential_and_no_query_string(tmp_path):
    path = fetch_to_file(
        tmp_path, tmp_path / "pull.json", fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    )
    text = path.read_text(encoding="utf-8")
    for sentinel in SENTINELS:
        assert sentinel not in text, f"{sentinel} reached the artifact"
    assert "Authorization" not in text
    assert "Bearer" not in text

    payload = json.loads(text)
    assert payload["granted_scopes"] == sorted(REQUIRED_SCOPES)
    for call in payload["api_calls"]:
        assert "?" not in call["endpoint"], call["endpoint"]
        assert "access_token" not in call["endpoint"]


def test_the_fetcher_writes_a_file_the_ingester_reads_without_translation(tmp_path):
    """No field is renamed, defaulted or reshaped between the halves."""
    path = fetch_to_file(
        tmp_path, tmp_path / "pull.json", fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    )
    artifact = read_artifact(path)
    assert artifact.channel.channel_id == "UC-company"
    assert [video.video_id for video in artifact.videos] == [VIDEO_ID]
    assert artifact.video_retrieval.complete is True
    per_video = [report for report in artifact.analytics if report.video_id == VIDEO_ID]
    assert len(per_video) == 1
    assert per_video[0].metric("views").value == 100


def test_readings_land_as_interval_observations_with_api_provenance(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    path = fetch_to_file(
        tmp_path, tmp_path / "pull.json", fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    )
    result, outcome = ingest_file(path, store)

    assert outcome.conflicts == ()
    assert outcome.written
    observations = store.observations_for("e2e-video-1")
    assert observations

    for observation in observations:
        assert observation.breakdown == (("measurement", "interval"),)
        assert observation.provenance.source.value == "own_analytics_api"
        assert observation.provenance.is_first_party
        # The window closes at midnight UTC after its last day, not when we fetched.
        assert observation.observed_at == dt.datetime(2026, 9, 17, 0, 0, tzinfo=UTC)

    by_name = {o.metric.name: o.value for o in observations}
    assert by_name["views"] == 100
    assert by_name["watch_time_hours"] == pytest.approx(4.0)  # 240 minutes
    assert by_name["average_percentage_viewed"] == pytest.approx(0.456)


# -- replay, revision, completeness -----------------------------------------


def test_a_second_identical_pull_writes_nothing(tmp_path):
    """Two fetches an hour apart, same numbers: one set of observations."""
    store = AnalyticsStore(tmp_path / "state")
    first = fetch_to_file(
        tmp_path, tmp_path / "first.json", fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    )
    second = fetch_to_file(
        tmp_path, tmp_path / "second.json", fetched_at=dt.datetime(2026, 9, 17, 11, 30, tzinfo=UTC)
    )
    # Different files - the fetch instant is on the artifact and differs.
    assert first.read_text(encoding="utf-8") != second.read_text(encoding="utf-8")

    first_result, first_outcome = ingest_file(first, store)
    second_result, second_outcome = ingest_file(second, store)

    # Identity survives the difference: same ids, nothing new written.
    assert [o.observation_id for o in first_result.observations] == [
        o.observation_id for o in second_result.observations
    ]
    assert second_outcome.written == ()
    assert set(second_outcome.already_present) == set(first_outcome.written)
    assert second_outcome.conflicts == ()
    assert len(store.observations_for("e2e-video-1")) == len(first_outcome.written)


def test_a_revised_value_for_the_same_window_is_refused_and_writes_nothing(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    original = fetch_to_file(
        tmp_path, tmp_path / "original.json", fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
    )
    ingest_file(original, store)
    before = {o.observation_id: o.value for o in store.list("observation")}
    assert before

    revised = fetch_to_file(
        tmp_path,
        tmp_path / "revised.json",
        fetched_at=dt.datetime(2026, 9, 18, 10, 0, tzinfo=UTC),
        metrics={"views": 118},
    )
    with pytest.raises(LedgerViolation) as error:
        ingest_file(revised, store)
    assert "append-only" in str(error.value)

    after = {o.observation_id: o.value for o in store.list("observation")}
    assert after == before, "a refused conflict must leave the store untouched"
    views = [o for o in store.observations_for("e2e-video-1") if o.metric.name == "views"]
    assert len(views) == 1, "the contradiction must not sit beside the original"
    assert views[0].value == 100


def test_an_incomplete_pull_reaches_the_store_as_an_incomplete_scope(tmp_path):
    """videos.list drops one id; the exact id survives to DataScope.excludes."""
    store = AnalyticsStore(tmp_path / "state")
    path = fetch_to_file(
        tmp_path,
        tmp_path / "partial.json",
        fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
        playlist_ids=(VIDEO_ID, SECOND_VIDEO_ID),
        returned_ids=(VIDEO_ID,),
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["video_retrieval"]["complete"] is False
    assert payload["video_retrieval"]["missing_video_ids"] == [SECOND_VIDEO_ID]

    result, outcome = ingest_file(path, store)
    assert outcome.conflicts == ()
    observations = store.observations_for("e2e-video-1")
    assert observations
    for observation in observations:
        assert observation.scope.complete is False
        assert any(
            SECOND_VIDEO_ID in exclusion for exclusion in observation.scope.excludes
        ), observation.scope.excludes
        assert observation.caveats


def test_an_unavailable_metric_produces_no_observation_rather_than_a_zero(tmp_path):
    store = AnalyticsStore(tmp_path / "state")
    path = fetch_to_file(
        tmp_path,
        tmp_path / "sparse.json",
        fetched_at=dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC),
        metrics={"likes": None},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    readings = {
        m["name"]: m
        for report in payload["analytics"]
        if report["video_id"] == VIDEO_ID
        for m in report["metrics"]
    }
    assert readings["likes"]["available"] is False
    assert readings["likes"]["value"] is None
    assert readings["likes"]["unavailable_reason"]

    result, _outcome = ingest_file(path, store)
    reported = {item.metric: item.reason for item in result.unavailable}
    assert "likes" in reported
    assert reported["likes"]
    assert "likes" not in {
        o.metric.name for o in store.observations_for("e2e-video-1")
    }
