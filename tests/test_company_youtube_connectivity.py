"""Read-only YouTube connectivity without live Google credentials."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qs, urlparse

import pytest

from company.analytics import AnalyticsStore, DeliverableKind
from company.integration.checks import _unapproved_network_imports, _youtube_write_capability
from company.integration.sources import parse_tree
from company.youtube import (
    ANALYTICS_API_METRICS,
    ANALYTICS_SCOPE,
    DATA_SCOPE,
    DEFAULT_SCOPES,
    MONETARY_SCOPE,
    AnalyticsEvidence,
    ApiError,
    AuthorizationRevoked,
    ConfigurationError,
    HttpResponse,
    InstrumentedTransport,
    MetricReading,
    OAuthClient,
    OAuthConfig,
    StoredGrant,
    TokenStore,
    VideoEvidence,
    YouTubeClient,
    YouTubeEvidenceStore,
    build_deliverable,
    commit_analytics,
)
from company.youtube.security import FilePermissionProtector, SecretRedactor


UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 17, 10, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


class FakeTransport:
    def __init__(self, *responses: HttpResponse) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def request(self, method, url, *, headers=None, body=None, timeout=30.0):
        self.requests.append(
            {"method": method, "url": url, "headers": headers or {}, "body": body}
        )
        if not self.responses:
            raise AssertionError("unexpected HTTP request")
        return self.responses.pop(0)


def response(status: int, value: object) -> HttpResponse:
    return HttpResponse(status, json.dumps(value).encode("utf-8"), {})


def config(tmp_path: Path, scopes=DEFAULT_SCOPES) -> OAuthConfig:
    return OAuthConfig(
        "client-id.apps.googleusercontent.com",
        "fake-client-secret",
        "http://127.0.0.1:8765/oauth2callback",
        tmp_path / "youtube-token.json",
        scopes,
    )


def token_store(tmp_path: Path) -> TokenStore:
    return TokenStore(tmp_path / "youtube-token.json", FilePermissionProtector())


def oauth_with_grant(tmp_path: Path, fake: FakeTransport) -> OAuthClient:
    store = token_store(tmp_path)
    store.save(StoredGrant("fake-refresh-token", DEFAULT_SCOPES))
    return OAuthClient(config(tmp_path), fake, store, now=lambda: NOW)


def channel_payload(*, hidden: bool = False) -> dict[str, object]:
    return {
        "items": [
            {
                "id": "UC-company",
                "snippet": {"title": "Simulation Factory"},
                "statistics": {
                    "subscriberCount": "1234",
                    "hiddenSubscriberCount": hidden,
                    "videoCount": "7",
                    "viewCount": "45678",
                },
                "contentDetails": {"relatedPlaylists": {"uploads": "UU-company"}},
            }
        ]
    }


def access_payload(token="fake-access-token", expires=3600):
    return {
        "access_token": token,
        "expires_in": expires,
        "scope": " ".join(DEFAULT_SCOPES),
        "token_type": "Bearer",
    }


def test_missing_oauth_configuration_names_fields_without_values(tmp_path):
    with pytest.raises(ConfigurationError) as error:
        OAuthConfig.from_environment({"YOUTUBE_TOKEN_FILE": str(tmp_path / "token.json")})
    assert "YOUTUBE_CLIENT_ID" in str(error.value)
    assert "client-id.apps" not in str(error.value)


def test_authorization_url_is_pkce_offline_and_read_only(tmp_path):
    oauth = OAuthClient(config(tmp_path), FakeTransport(), token_store(tmp_path))
    request = oauth.authorization_request()
    query = parse_qs(urlparse(request.url).query)
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert query["code_challenge_method"] == ["S256"]
    assert set(query["scope"][0].split()) == set(DEFAULT_SCOPES)
    assert MONETARY_SCOPE not in query["scope"][0]
    assert all("upload" not in scope and "force-ssl" not in scope for scope in DEFAULT_SCOPES)
    assert request.state and request.code_verifier


def test_monetary_scope_is_optional_and_still_read_only(tmp_path):
    value = config(tmp_path, DEFAULT_SCOPES + (MONETARY_SCOPE,))
    assert value.scopes == (DATA_SCOPE, ANALYTICS_SCOPE, MONETARY_SCOPE)


def test_code_exchange_normalizes_and_persists_only_refresh_grant(tmp_path):
    fake = FakeTransport(
        response(
            200,
            {
                **access_payload(),
                "refresh_token": "fake-refresh-token",
            },
        )
    )
    store = token_store(tmp_path)
    oauth = OAuthClient(config(tmp_path), fake, store, now=lambda: NOW)
    token = oauth.exchange_code("fake-code", "fake-verifier")
    assert token.value == "fake-access-token"
    assert store.load().refresh_token == "fake-refresh-token"
    persisted = store.path.read_text(encoding="utf-8")
    assert "fake-access-token" not in persisted
    assert "fake-client-secret" not in persisted


def test_refresh_grant_obtains_access_without_reauthorization(tmp_path):
    fake = FakeTransport(response(200, access_payload()))
    oauth = oauth_with_grant(tmp_path, fake)
    assert oauth.access_token() == "fake-access-token"
    body = fake.requests[0]["body"].decode("utf-8")
    assert "grant_type=refresh_token" in body


def test_expired_in_memory_access_token_is_refreshed(tmp_path):
    clock = [NOW]
    fake = FakeTransport(
        response(200, access_payload("access-one", expires=60)),
        response(200, access_payload("access-two", expires=3600)),
    )
    store = token_store(tmp_path)
    store.save(StoredGrant("fake-refresh-token", DEFAULT_SCOPES))
    oauth = OAuthClient(config(tmp_path), fake, store, now=lambda: clock[0])
    assert oauth.access_token() == "access-one"
    clock[0] += dt.timedelta(seconds=40)
    assert oauth.access_token() == "access-two"
    assert len(fake.requests) == 2


def test_revoked_refresh_grant_has_actionable_secret_free_error(tmp_path):
    fake = FakeTransport(response(400, {"error": "invalid_grant"}))
    oauth = oauth_with_grant(tmp_path, fake)
    with pytest.raises(AuthorizationRevoked) as error:
        oauth.access_token()
    assert "run auth again" in str(error.value)
    assert "fake-refresh-token" not in str(error.value)


def test_channel_normalization_preserves_hidden_as_unavailable(tmp_path):
    fake = FakeTransport(response(200, access_payload()), response(200, channel_payload(hidden=True)))
    instrumented = InstrumentedTransport(fake)
    result = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW).channel()
    channel = result.normalized
    assert channel.channel_id == "UC-company"
    assert channel.channel_title == "Simulation Factory"
    assert channel.subscriber_count is None
    assert channel.subscriber_count_unavailable_reason
    assert channel.video_count == 7
    assert channel.view_count == 45678
    assert result.api_calls[-1].response_bytes
    assert "?" not in result.api_calls[-1].endpoint


def test_recent_video_normalization_includes_duration_and_status(tmp_path):
    fake = FakeTransport(
        response(200, access_payload()),
        response(200, channel_payload()),
        response(200, {"items": [{"contentDetails": {"videoId": "abcDEF_1"}}]}),
        response(
            200,
            {
                "items": [
                    {
                        "id": "abcDEF_1",
                        "snippet": {"title": "Test 1", "publishedAt": "2026-09-10T08:00:00Z"},
                        "contentDetails": {"duration": "PT1M2S"},
                        "status": {"privacyStatus": "public", "uploadStatus": "processed"},
                    }
                ]
            },
        ),
    )
    instrumented = InstrumentedTransport(fake)
    result = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW).recent_videos(1)
    video = result.normalized[0]
    assert video.video_id == "abcDEF_1"
    assert video.duration == "PT1M2S"
    assert video.duration_seconds == 62
    assert video.privacy_status == "public"
    assert video.upload_status == "processed"


def test_analytics_parser_normalizes_units_and_all_requested_metrics(tmp_path):
    headers = [{"name": name, "dataType": "FLOAT"} for name in ANALYTICS_API_METRICS]
    fake = FakeTransport(
        response(200, access_payload()),
        response(200, channel_payload()),
        response(
            200,
            {
                "columnHeaders": headers,
                "rows": [[100, 90, 54, 75.5, 4, 1, 8, 2, 3]],
            },
        ),
    )
    instrumented = InstrumentedTransport(fake)
    result = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW).analytics(
        dt.date(2026, 9, 1), dt.date(2026, 9, 16), video_id="abcDEF_1"
    )
    report = result.normalized
    assert report.channel_id == "UC-company"
    assert report.video_id == "abcDEF_1"
    assert report.metric("views").value == 100
    assert report.metric("estimated_minutes_watched").value == 90.0
    assert report.metric("average_view_percentage").value == pytest.approx(0.755)
    assert all(metric.available for metric in report.metrics)


def test_empty_analytics_rows_are_unavailable_not_zero(tmp_path):
    fake = FakeTransport(
        response(200, access_payload()),
        response(200, channel_payload()),
        response(200, {"columnHeaders": [], "rows": []}),
    )
    instrumented = InstrumentedTransport(fake)
    report = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW).analytics(
        dt.date(2026, 9, 1), dt.date(2026, 9, 2)
    ).normalized
    assert all(not metric.available and metric.value is None for metric in report.metrics)
    assert all(metric.unavailable_reason for metric in report.metrics)


def test_api_error_and_bearer_value_are_redacted(tmp_path):
    fake = FakeTransport(
        response(200, access_payload("sensitive-access")),
        response(403, {"error": {"message": "Bearer sensitive-access denied"}}),
    )
    instrumented = InstrumentedTransport(fake)
    client = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW)
    with pytest.raises(ApiError) as error:
        client.channel()
    assert "sensitive-access" not in str(error.value)
    assert "[REDACTED]" in str(error.value)
    assert instrumented.traces[-1].succeeded is False


def test_redactor_covers_assignments_and_known_values():
    text = "client_secret=alpha Authorization: Bearer beta refresh_token=gamma"
    redacted = SecretRedactor("alpha", "beta", "gamma").redact(text)
    assert all(secret not in redacted for secret in ("alpha", "beta", "gamma"))


def test_evidence_store_preserves_raw_normalized_and_secret_free_telemetry(tmp_path):
    fake = FakeTransport(response(200, access_payload()), response(200, channel_payload()))
    instrumented = InstrumentedTransport(fake)
    result = YouTubeClient(oauth_with_grant(tmp_path, instrumented), instrumented, now=lambda: NOW).channel()
    pointer = YouTubeEvidenceStore(tmp_path / "state").append(result)
    record = YouTubeEvidenceStore(tmp_path / "state").records()[0]
    assert pointer.record_ref.startswith("youtube/evidence/")
    assert record["raw"] == channel_payload()
    assert record["normalized"]["channel_id"] == "UC-company"
    serialized = json.dumps(record)
    assert "fake-access-token" not in serialized
    assert "fake-refresh-token" not in serialized
    assert "Authorization" not in serialized


def test_per_video_analytics_enters_existing_analytics_store(tmp_path):
    report = AnalyticsEvidence(
        channel_id="UC-company",
        start_date=dt.date(2026, 9, 1),
        end_date=dt.date(2026, 9, 16),
        video_id="abcDEF_1",
        metrics=(
            MetricReading("views", "views", "views", 100, True),
            MetricReading("estimated_minutes_watched", "estimatedMinutesWatched", "minutes", 90.0, True),
            MetricReading("comments", "comments", "comments", None, False, "API omitted this metric"),
        ),
        retrieved_at=NOW,
    )
    video = VideoEvidence(
        "abcDEF_1",
        "UC-company",
        "Test 1",
        dt.datetime(2026, 9, 10, 8, 0, tzinfo=UTC),
        "PT1M",
        60,
        "public",
        "processed",
        NOW,
    )
    deliverable = build_deliverable(
        video,
        deliverable_id="test-1",
        kind=DeliverableKind.SHORT,
        format_id="marble_race",
    )
    store = AnalyticsStore(tmp_path / "state")
    committed = commit_analytics(
        store, report, video, deliverable, evidence_ref="youtube/evidence/000001.json"
    )
    observations = store.observations_for("test-1")
    assert {item.metric.name for item in observations} == {"views", "watch_time_hours"}
    assert next(item for item in observations if item.metric.name == "watch_time_hours").value == 1.5
    assert committed.unavailable_metrics == ("comments",)
    assert all(item.provenance.source.value == "own_analytics_api" for item in observations)


def test_production_gate_allows_only_reviewed_connector_network_imports(tmp_path):
    modules, failures = parse_tree(ROOT, ("company",))
    assert failures == ()
    assert _unapproved_network_imports(modules) == ()
    assert _youtube_write_capability(modules) == ()

    bad = tmp_path / "company" / "other"
    bad.mkdir(parents=True)
    (bad / "network.py").write_text("import urllib.request\n", encoding="utf-8")
    bad_modules, failures = parse_tree(tmp_path, ("company",))
    assert failures == ()
    assert _unapproved_network_imports(bad_modules)


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
