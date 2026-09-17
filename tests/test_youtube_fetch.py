"""The external fetcher, driven entirely from a scripted transport.

## What these tests are actually for

Every defect this package was rewritten to fix is a defect that only shows up
under a condition a happy-path test never reaches: a consent screen with a box
unticked, a browser asking for a favicon before the callback lands, a playlist
with more than fifty entries, a token that goes stale halfway through a
paginated walk, a provider quoting a credential back inside an error body. None
of those can be arranged against the real Google, and all of them can be
arranged against a table of scripted responses.

So `FakeTransport` answers by method and endpoint, with a queue per endpoint so
the second call to `playlistItems.list` can differ from the first. No test here
opens a socket, reads an environment variable belonging to a real project, or
needs a credential.

## Sentinels, because "no secret leaked" is otherwise unfalsifiable

The client secret, refresh token and access token used here are recognisable
strings. Asserting that a specific string is absent from a repr, a message, a
CLI transcript and a written artifact is a test that can fail; asserting that
"no secrets leak" is a sentence. Any new surface that grows a leak fails the
same assertion without anybody having to remember to extend it.

## This file may not import Company OS

`tools/` is a production root and `architecture.production_tests_independent`
requires that a production test module runs with `company/`, `ai_platform/`,
`knowledge/` and `intelligence/` removed from the checkout. One of the tests
below asserts that property over this file and the package it covers, by
reading the source rather than by trusting the convention.
"""

from __future__ import annotations

import ast
import datetime as dt
import itertools
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

import pytest

import tools.youtube_fetch as fetch_package
from tools.youtube_fetch.api import (
    ANALYTICS_API_METRICS,
    METRIC_TABLE,
    YouTubeReader,
)
from tools.youtube_fetch.artifact import (
    FetchRequest,
    assert_sanitized,
    fetch_artifact,
    write_artifact,
)
from tools.youtube_fetch.config import (
    ANALYTICS_SCOPE,
    DATA_SCOPE,
    REQUIRED_SCOPES,
    OAuthConfig,
)
from tools.youtube_fetch.errors import (
    ApiError,
    AuthorizationError,
    AuthorizationRevoked,
    ConfigurationError,
    InsufficientPermissions,
    MissingScopeError,
    QuotaExceeded,
    YouTubeFetchError,
)
from tools.youtube_fetch.__main__ import Stack, main
from tools.youtube_fetch.oauth import (
    LocalCallbackServer,
    OAuthClient,
    StoredGrant,
    TokenStore,
)
from tools.youtube_fetch.secrets_ import (
    FilePermissionProtector,
    SecretRedactor,
    WindowsDpapiProtector,
    decode_protected,
    encode_protected,
)
from tools.youtube_fetch.transport import (
    HttpResponse,
    InstrumentedTransport,
    endpoint_of,
)


# -- sentinels --------------------------------------------------------------

CLIENT_ID = "client-id.apps.googleusercontent.com"
CLIENT_SECRET = "SENTINEL-client-secret-a1b2c3d4"
REFRESH_TOKEN = "SENTINEL-refresh-token-e5f6a7b8"
ROTATED_REFRESH = "SENTINEL-rotated-refresh-99887766"
ACCESS_TOKEN = "SENTINEL-access-token-c9d0e1f2"
SECOND_ACCESS_TOKEN = "SENTINEL-second-access-token-33445566"
SENTINELS = (
    CLIENT_SECRET,
    REFRESH_TOKEN,
    ROTATED_REFRESH,
    ACCESS_TOKEN,
    SECOND_ACCESS_TOKEN,
)

REDIRECT_URI = "http://127.0.0.1:8731/oauth2/callback"
FIXED_NOW = dt.datetime(2026, 9, 17, 10, 0, tzinfo=dt.timezone.utc)
START_DATE = dt.date(2026, 9, 1)
END_DATE = dt.date(2026, 9, 16)

TOKEN_KEY = "POST https://oauth2.googleapis.com/token"
CHANNELS_KEY = "GET https://www.googleapis.com/youtube/v3/channels"
PLAYLIST_KEY = "GET https://www.googleapis.com/youtube/v3/playlistItems"
VIDEOS_KEY = "GET https://www.googleapis.com/youtube/v3/videos"
REPORTS_KEY = "GET https://youtubeanalytics.googleapis.com/v2/reports"

PACKAGE_DIR = Path(fetch_package.__file__).resolve().parent


# -- scripted transport -----------------------------------------------------


class FakeTransport:
    """Answers by `METHOD endpoint`, popping a queue so pages can differ."""

    def __init__(self) -> None:
        self.routes: dict[str, list[HttpResponse]] = {}
        self.calls: list[tuple[str, str, dict[str, str]]] = []

    def queue(self, key: str, status: int, payload: Any) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.routes.setdefault(key, []).append(HttpResponse(status, body, {}))

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        body: bytes | None = None,
        timeout: float = 30.0,
    ) -> HttpResponse:
        self.calls.append((method.upper(), url, dict(headers or {})))
        key = f"{method.upper()} {endpoint_of(url)}"
        queued = self.routes.get(key)
        if not queued:
            raise AssertionError(f"no scripted response for {key}")
        # The last response sticks, so an endpoint that should keep failing does.
        return queued.pop(0) if len(queued) > 1 else queued[0]

    def urls(self, key: str) -> list[str]:
        return [
            url
            for method, url, _headers in self.calls
            if f"{method} {endpoint_of(url)}" == key
        ]


def deterministic_clock() -> Callable[[], float]:
    counter = itertools.count()
    return lambda: next(counter) * 0.001


# -- payload builders -------------------------------------------------------


def token_payload(
    *,
    access: str = ACCESS_TOKEN,
    scope: str | None = None,
    refresh: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "access_token": access,
        "expires_in": 3600,
        "token_type": "Bearer",
        "scope": " ".join(REQUIRED_SCOPES) if scope is None else scope,
    }
    if refresh:
        payload["refresh_token"] = refresh
    return payload


def channels_payload(*, hidden_subscribers: bool = False) -> dict[str, Any]:
    statistics: dict[str, Any] = {
        "videoCount": "7",
        "viewCount": "45678",
    }
    if hidden_subscribers:
        statistics["hiddenSubscriberCount"] = True
    else:
        statistics["subscriberCount"] = "1234"
    return {
        "items": [
            {
                "id": "UC-company",
                "snippet": {"title": "Simulation Factory"},
                "statistics": statistics,
                "contentDetails": {"relatedPlaylists": {"uploads": "UU-company"}},
            }
        ]
    }


def playlist_payload(video_ids: Sequence[str], *, next_token: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "items": [{"contentDetails": {"videoId": video_id}} for video_id in video_ids]
    }
    if next_token:
        payload["nextPageToken"] = next_token
    return payload


def videos_payload(video_ids: Sequence[str]) -> dict[str, Any]:
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


def reports_payload(values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    headers = [{"name": name, "columnType": "METRIC"} for name in ANALYTICS_API_METRICS]
    if values is None:
        return {"columnHeaders": headers, "rows": []}
    return {
        "columnHeaders": headers,
        "rows": [[values.get(name, 0) for name in ANALYTICS_API_METRICS]],
    }


DEFAULT_METRIC_VALUES = {
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


# -- harness ----------------------------------------------------------------


@dataclass
class Harness:
    config: OAuthConfig
    fake: FakeTransport
    transport: InstrumentedTransport
    store: TokenStore
    oauth: OAuthClient
    reader: YouTubeReader

    def stack(self) -> Stack:
        return Stack(self.config, self.transport, self.oauth, self.reader)

    def script_happy_path(
        self,
        *,
        video_ids: Sequence[str] = ("abcDEF_1", "abcDEF_2"),
        returned_ids: Sequence[str] | None = None,
        metric_values: Mapping[str, Any] | None = None,
    ) -> None:
        self.fake.queue(TOKEN_KEY, 200, token_payload())
        self.fake.queue(CHANNELS_KEY, 200, channels_payload())
        self.fake.queue(PLAYLIST_KEY, 200, playlist_payload(video_ids))
        self.fake.queue(
            VIDEOS_KEY,
            200,
            videos_payload(video_ids if returned_ids is None else returned_ids),
        )
        self.fake.queue(
            REPORTS_KEY,
            200,
            reports_payload(
                DEFAULT_METRIC_VALUES if metric_values is None else metric_values
            ),
        )


def make_harness(tmp_path: Path, *, with_grant: bool = True) -> Harness:
    token_path = tmp_path / "token.json"
    config = OAuthConfig(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        token_path=token_path,
    )
    store = TokenStore(token_path, FilePermissionProtector())
    if with_grant:
        store.save(StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES))
    fake = FakeTransport()
    transport = InstrumentedTransport(fake, clock=deterministic_clock())
    oauth = OAuthClient(config, transport, store, now=lambda: FIXED_NOW)
    return Harness(config, fake, transport, store, oauth, YouTubeReader(oauth, transport))


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return make_harness(tmp_path)


def default_request(**overrides: Any) -> FetchRequest:
    values: dict[str, Any] = {
        "start_date": START_DATE,
        "end_date": END_DATE,
        "video_limit": 2,
    }
    values.update(overrides)
    return FetchRequest(**values)


def requested_ids(url: str) -> list[str]:
    """The `id` parameter of a videos.list call, as a list."""
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query).get("id", [""])[0].split(",")


def source_files() -> list[Path]:
    return sorted(PACKAGE_DIR.glob("*.py"))


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


# -- architecture -----------------------------------------------------------


COMPANY_OS_ROOTS = {"company", "ai_platform", "knowledge", "intelligence"}


def test_no_module_imports_company_os() -> None:
    for path in source_files():
        assert not (imported_roots(path) & COMPANY_OS_ROOTS), (
            f"{path.name} imports a Company OS root; tools/ is a production root"
        )


def test_this_test_module_imports_no_company_os() -> None:
    assert not (imported_roots(Path(__file__)) & COMPANY_OS_ROOTS)


def test_no_third_party_dependency_is_introduced() -> None:
    standard_library = set(getattr(__import__("sys"), "stdlib_module_names", ()))
    allowed = standard_library | {"tools", "pytest"}
    for path in source_files():
        unexpected = imported_roots(path) - allowed
        assert not unexpected, f"{path.name} imports non-stdlib {sorted(unexpected)}"


def test_ctypes_is_never_imported_at_module_scope() -> None:
    """Requirement 9: the package must import on Linux and macOS."""
    for path in source_files():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Import):
                assert all(
                    not alias.name.startswith("ctypes") for alias in node.names
                ), f"{path.name} imports ctypes at module scope"
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or not node.module.startswith("ctypes"), (
                    f"{path.name} imports from ctypes at module scope"
                )
        first_lines = path.read_text(encoding="utf-8").splitlines()
        assert not any(
            line.startswith("from ctypes") or line.startswith("import ctypes")
            for line in first_lines
        ), f"{path.name} has a module-level ctypes import"


def test_package_imports_cleanly_and_exposes_the_contract_names() -> None:
    for name in (
        "YouTubeReader",
        "OAuthClient",
        "LocalCallbackServer",
        "TokenStore",
        "SecretRedactor",
        "WindowsDpapiProtector",
        "FilePermissionProtector",
        "fetch_artifact",
        "write_artifact",
        "REQUIRED_SCOPES",
    ):
        assert hasattr(fetch_package, name), name


def test_the_package_does_no_logging_of_its_own() -> None:
    """No log call can leak a credential if there is no log call."""
    for path in source_files():
        assert "logging" not in imported_roots(path), path.name


# -- requirement 7: the scope set cannot grow -------------------------------


def test_requested_scope_set_is_exactly_two() -> None:
    assert REQUIRED_SCOPES == (DATA_SCOPE, ANALYTICS_SCOPE)
    assert len(REQUIRED_SCOPES) == 2


def test_no_monetary_scope_survives_anywhere_in_the_package() -> None:
    """The constant, the flag and the parameter are gone, not merely unused."""
    assert not hasattr(fetch_package, "MONETARY_SCOPE")
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        for banned in (
            "MONETARY_SCOPE",
            "include_monetary",
            "--include-monetary-scope",
            "yt-analytics-monetary",
        ):
            assert banned not in text, f"{path.name} still carries {banned}"


def test_config_refuses_a_scope_set_that_grew(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        OAuthConfig(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            token_path=tmp_path / "token.json",
            scopes=REQUIRED_SCOPES
            + ("https://www.googleapis.com/auth/yt-analytics-monetary.readonly",),
        )


def test_config_refuses_a_scope_set_that_shrank(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        OAuthConfig(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            token_path=tmp_path / "token.json",
            scopes=(DATA_SCOPE,),
        )


def test_authorization_url_requests_exactly_the_two_scopes(harness: Harness) -> None:
    """Spelled out rather than compared to the constant.

    Asserting the URL against `REQUIRED_SCOPES` would pass however that tuple
    changed, which makes it a restatement rather than a check. The two strings
    are written here so that widening the grant has to be done twice, in two
    files, by someone who meant it.
    """
    request = harness.oauth.authorization_request()
    from urllib.parse import parse_qs, urlparse

    query = parse_qs(urlparse(request.url).query)
    assert query["scope"][0].split() == [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]


def test_oauth_client_has_no_monetary_parameter() -> None:
    import inspect

    signature = inspect.signature(OAuthConfig.from_environment)
    assert "include_monetary" not in signature.parameters


# -- requirement 10: granted scopes verified before anything is stored ------


def test_exchange_stores_the_grant_when_both_scopes_are_granted(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    harness.fake.queue(TOKEN_KEY, 200, token_payload(refresh=REFRESH_TOKEN))
    token = harness.oauth.exchange_code("auth-code", "verifier")
    assert token.scopes == REQUIRED_SCOPES
    assert harness.store.exists()
    assert harness.store.load().refresh_token == REFRESH_TOKEN


def test_missing_scope_raises_and_stores_nothing(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    harness.fake.queue(
        TOKEN_KEY, 200, token_payload(scope=DATA_SCOPE, refresh=REFRESH_TOKEN)
    )
    with pytest.raises(MissingScopeError) as caught:
        harness.oauth.exchange_code("auth-code", "verifier")
    assert ANALYTICS_SCOPE in str(caught.value)
    assert not harness.store.exists(), "a partial consent must leave no stored grant"
    assert REFRESH_TOKEN not in str(caught.value)


def test_missing_scope_is_an_authorization_error(tmp_path: Path) -> None:
    assert issubclass(MissingScopeError, AuthorizationError)


# -- requirement 11: the callback server keeps serving ----------------------


class ScriptedCallbackServer:
    """Stands in for `HTTPServer`, replaying request paths into the handler."""

    def __init__(self, callback: LocalCallbackServer, paths: Iterable[str]) -> None:
        self.callback = callback
        self.paths = list(paths)
        self.responses: list[tuple[int, bytes]] = []
        self.timeout = 0.0
        self.closed = False

    def handle_request(self) -> None:
        if self.paths:
            self.responses.append(self.callback.handle_path(self.paths.pop(0)))

    def server_close(self) -> None:
        self.closed = True


def test_a_favicon_request_does_not_consume_the_callback(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    request = harness.oauth.authorization_request()
    callback = LocalCallbackServer(REDIRECT_URI, request.state)
    server = ScriptedCallbackServer(
        callback,
        [
            "/favicon.ico",
            "/",
            f"/oauth2/callback?state={request.state}&code=the-authorization-code",
        ],
    )
    code = callback.wait(
        100.0,
        server_factory=lambda: server,
        clock=itertools.count().__next__,
    )
    assert code == "the-authorization-code"
    assert [status for status, _body in server.responses] == [404, 404, 200]
    assert callback.ignored_paths == ["/favicon.ico", "/"]
    assert server.closed

    # ... and the authorization completes on the code that survived.
    harness.fake.queue(TOKEN_KEY, 200, token_payload(refresh=REFRESH_TOKEN))
    token = harness.oauth.exchange_code(code, request.code_verifier)
    assert token.scopes == REQUIRED_SCOPES
    assert harness.store.exists()


def test_the_callback_server_times_out_without_a_callback(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    request = harness.oauth.authorization_request()
    callback = LocalCallbackServer(REDIRECT_URI, request.state)
    server = ScriptedCallbackServer(callback, ["/favicon.ico"])
    with pytest.raises(AuthorizationError) as caught:
        callback.wait(
            2.0, server_factory=lambda: server, clock=itertools.count().__next__
        )
    assert "timed out" in str(caught.value)
    assert server.closed


def test_a_mismatched_state_is_refused(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    request = harness.oauth.authorization_request()
    callback = LocalCallbackServer(REDIRECT_URI, request.state)
    status, _body = callback.handle_path("/oauth2/callback?state=forged&code=abc")
    assert status == 400
    assert callback.finished
    with pytest.raises(AuthorizationError):
        callback.wait(
            2.0,
            server_factory=lambda: ScriptedCallbackServer(callback, []),
            clock=itertools.count().__next__,
        )
    assert not harness.store.exists()


def test_a_loopback_redirect_is_required(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError):
        LocalCallbackServer("https://example.com/callback", "state")


# -- requirement 15: typed failures -----------------------------------------


def test_invalid_grant_on_refresh_raises_authorization_revoked(harness: Harness) -> None:
    harness.fake.queue(
        TOKEN_KEY,
        400,
        {"error": "invalid_grant", "error_description": f"token {REFRESH_TOKEN} revoked"},
    )
    with pytest.raises(AuthorizationRevoked) as caught:
        harness.oauth.access_token()
    assert_no_sentinel(str(caught.value))


def test_invalid_grant_on_exchange_raises_authorization_revoked(tmp_path: Path) -> None:
    harness = make_harness(tmp_path, with_grant=False)
    harness.fake.queue(TOKEN_KEY, 400, {"error": "invalid_grant"})
    with pytest.raises(AuthorizationRevoked):
        harness.oauth.exchange_code("stale-code", "verifier")
    assert not harness.store.exists()


def test_quota_exceeded_is_typed(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(
        CHANNELS_KEY,
        403,
        {
            "error": {
                "code": 403,
                "message": "The request cannot be completed because you have exceeded your quota.",
                "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}],
            }
        },
    )
    with pytest.raises(QuotaExceeded) as caught:
        harness.reader.channel()
    assert isinstance(caught.value, ApiError)
    assert_no_sentinel(str(caught.value))


def test_insufficient_permissions_is_typed(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(["abcDEF_1"]))
    harness.fake.queue(VIDEOS_KEY, 200, videos_payload(["abcDEF_1"]))
    harness.fake.queue(
        REPORTS_KEY,
        403,
        {
            "error": {
                "code": 403,
                "message": "Request had insufficient authentication scopes.",
                "errors": [{"reason": "insufficientPermissions"}],
            }
        },
    )
    with pytest.raises(InsufficientPermissions) as caught:
        harness.reader.analytics(START_DATE, END_DATE)
    assert "authorize again" in str(caught.value)


def test_a_401_on_a_later_page_forces_one_refresh_then_raises(harness: Harness) -> None:
    """Requirement 15: the second page must not be quietly dropped."""
    first_page = [f"vid{index:03d}" for index in range(50)]
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(TOKEN_KEY, 200, token_payload(access=SECOND_ACCESS_TOKEN))
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(first_page, next_token="p2"))
    harness.fake.queue(PLAYLIST_KEY, 401, {"error": {"code": 401, "message": "expired"}})

    with pytest.raises(AuthorizationError) as caught:
        harness.reader.recent_videos(60)

    assert not isinstance(caught.value, AuthorizationRevoked)
    # Exactly one forced refresh: two token calls, the second after the 401.
    assert len(harness.fake.urls(TOKEN_KEY)) == 2
    # The retry really was a retry of page two, not a restart.
    playlist_urls = harness.fake.urls(PLAYLIST_KEY)
    assert len(playlist_urls) == 3
    assert "pageToken=p2" in playlist_urls[1]
    assert "pageToken=p2" in playlist_urls[2]
    assert_no_sentinel(str(caught.value))


def test_a_401_that_a_refresh_fixes_is_retried_transparently(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(TOKEN_KEY, 200, token_payload(access=SECOND_ACCESS_TOKEN))
    harness.fake.queue(CHANNELS_KEY, 401, {"error": {"code": 401}})
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    channel = harness.reader.channel()
    assert channel.facts.channel_id == "UC-company"
    assert len(harness.fake.urls(TOKEN_KEY)) == 2
    authorizations = [
        headers.get("Authorization")
        for method, url, headers in harness.fake.calls
        if endpoint_of(url).endswith("/channels")
    ]
    assert authorizations == [
        f"Bearer {ACCESS_TOKEN}",
        f"Bearer {SECOND_ACCESS_TOKEN}",
    ]


# -- requirement 6: pagination and completeness -----------------------------


def test_pagination_follows_the_next_page_token(harness: Harness) -> None:
    first_page = [f"vid{index:03d}" for index in range(50)]
    second_page = [f"vid{index:03d}" for index in range(50, 60)]
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(first_page, next_token="p2"))
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(second_page))
    harness.fake.queue(VIDEOS_KEY, 200, videos_payload(first_page))
    harness.fake.queue(VIDEOS_KEY, 200, videos_payload(second_page))

    listing = harness.reader.recent_videos(60)

    assert listing.pages_followed == 2
    assert len(listing.videos) == 60
    assert listing.complete
    assert listing.missing_video_ids == ()
    # videos.list is called in chunks of at most fifty ids.
    video_urls = harness.fake.urls(VIDEOS_KEY)
    assert len(video_urls) == 2
    assert requested_ids(video_urls[0]) == first_page
    assert requested_ids(video_urls[1]) == second_page
    assert [video.video_id for video in listing.videos] == first_page + second_page


def test_pagination_stops_when_the_playlist_is_exhausted(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(["a1", "a2"]))
    harness.fake.queue(VIDEOS_KEY, 200, videos_payload(["a1", "a2"]))

    listing = harness.reader.recent_videos(10)

    assert listing.pages_followed == 1
    assert len(listing.videos) == 2
    assert not listing.complete
    assert listing.missing_video_ids == ()
    assert any("fewer than the 10 requested" in note for note in listing.notes)


def test_a_partial_videos_response_records_the_exact_missing_ids(
    harness: Harness,
) -> None:
    """Requirement 6: the ids, not a count."""
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(["keep1", "gone1", "gone2"]))
    harness.fake.queue(VIDEOS_KEY, 200, videos_payload(["keep1"]))

    listing = harness.reader.recent_videos(3)

    assert listing.missing_video_ids == ("gone1", "gone2")
    assert not listing.complete
    retrieval = listing.retrieval_dict()
    assert retrieval["requested"] == 3
    assert retrieval["returned"] == 1
    assert retrieval["complete"] is False
    assert retrieval["missing_video_ids"] == ["gone1", "gone2"]
    assert any("gone1, gone2" in note for note in retrieval["notes"])


def test_a_video_item_that_cannot_identify_itself_becomes_a_missing_id(
    harness: Harness,
) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(["ok1", "broken"]))
    harness.fake.queue(
        VIDEOS_KEY,
        200,
        {
            "items": videos_payload(["ok1"])["items"]
            + [{"id": "broken", "snippet": {"title": ""}}]
        },
    )
    listing = harness.reader.recent_videos(2)
    assert listing.missing_video_ids == ("broken",)


# -- unavailable is not zero ------------------------------------------------


def test_an_unavailable_metric_is_not_zero(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(REPORTS_KEY, 200, reports_payload(None))

    report = harness.reader.analytics(START_DATE, END_DATE)

    assert len(report.metrics) == len(METRIC_TABLE)
    for reading in report.metrics:
        assert reading.available is False
        assert reading.value is None
        assert reading.unavailable_reason
    payload = report.to_dict()
    assert payload["complete"] is False
    assert len(payload["excludes"]) == len(METRIC_TABLE)
    assert all(metric["value"] is None for metric in payload["metrics"])
    assert 0 not in [metric["value"] for metric in payload["metrics"]]


def test_a_present_metric_carries_its_declared_unit(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(REPORTS_KEY, 200, reports_payload(DEFAULT_METRIC_VALUES))

    report = harness.reader.analytics(START_DATE, END_DATE, video_id="abcDEF_1")
    readings = {reading.name: reading for reading in report.metrics}

    assert readings["views"].value == 100
    assert readings["views"].unit == "views"
    assert readings["estimated_minutes_watched"].value == 240
    assert readings["average_view_duration_seconds"].value == 62
    # 45.6 per cent is emitted as the fraction the artifact says it is.
    assert readings["average_view_percentage"].unit == "fraction"
    assert readings["average_view_percentage"].value == pytest.approx(0.456)
    assert report.to_dict()["complete"] is True
    assert report.to_dict()["video_id"] == "abcDEF_1"
    assert report.to_dict()["temporal_semantics"] == "interval"


def test_a_hidden_subscriber_count_is_null_with_a_reason(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload(hidden_subscribers=True))
    facts = harness.reader.channel().facts
    assert facts.subscriber_count is None
    assert facts.subscriber_count_unavailable_reason


# -- the artifact -----------------------------------------------------------


def test_the_artifact_matches_the_agreed_shape(harness: Harness, tmp_path: Path) -> None:
    harness.script_happy_path()
    payload = fetch_artifact(
        harness.reader, default_request(), fetched_at=FIXED_NOW
    )

    assert payload["artifact_version"] == 1
    assert payload["producer"] == "tools.youtube_fetch"
    assert payload["producer_version"] == "1.0"
    assert payload["fetched_at"] == FIXED_NOW.isoformat()
    assert payload["granted_scopes"] == sorted(REQUIRED_SCOPES)

    channel = payload["channel"]
    assert channel["channel_id"] == "UC-company"
    assert channel["channel_title"] == "Simulation Factory"
    assert channel["subscriber_count"] == 1234
    assert channel["subscriber_count_unavailable_reason"] == ""
    assert channel["uploads_playlist_id"] == "UU-company"
    assert channel["source"] == "youtube_data_api_v3.channels.list"

    video = payload["videos"][0]
    assert set(video) == {
        "video_id",
        "channel_id",
        "title",
        "published_at",
        "duration",
        "duration_seconds",
        "privacy_status",
        "upload_status",
        "source",
    }
    assert video["duration_seconds"] == 62
    assert video["source"] == "youtube_data_api_v3.videos.list"
    # The API writes `...Z`; the artifact writes one spelling of UTC.
    assert video["published_at"] == "2026-09-10T08:00:00+00:00"

    retrieval = payload["video_retrieval"]
    assert set(retrieval) == {
        "requested",
        "returned",
        "complete",
        "pages_followed",
        "missing_video_ids",
        "notes",
    }
    assert retrieval["complete"] is True

    report = payload["analytics"][0]
    assert report["video_id"] is None
    assert report["start_date"] == START_DATE.isoformat()
    assert report["end_date"] == END_DATE.isoformat()
    assert report["temporal_semantics"] == "interval"
    assert report["source"] == "youtube_analytics_api_v2.reports.query"
    metric = report["metrics"][0]
    assert set(metric) == {
        "name",
        "source_metric",
        "unit",
        "value",
        "available",
        "unavailable_reason",
    }

    call = payload["api_calls"][0]
    assert set(call) == {
        "method",
        "endpoint",
        "status",
        "response_bytes",
        "latency_ms",
        "succeeded",
        "error_kind",
    }
    assert "raw" not in payload

    written = write_artifact(
        payload, tmp_path / "out" / "artifact.json", secret_values=SENTINELS
    )
    reloaded = json.loads(written.read_text(encoding="utf-8"))
    assert reloaded == payload


def test_raw_is_included_only_when_asked_for(harness: Harness) -> None:
    harness.script_happy_path()
    payload = fetch_artifact(
        harness.reader, default_request(include_raw=True), fetched_at=FIXED_NOW
    )
    assert set(payload["raw"]) == {
        "channels.list",
        "playlistItems.list",
        "videos.list",
        "reports.query",
    }
    assert isinstance(payload["raw"]["playlistItems.list"], list)


def test_every_endpoint_in_the_artifact_has_lost_its_query_string(
    harness: Harness,
) -> None:
    harness.script_happy_path()
    payload = fetch_artifact(harness.reader, default_request(), fetched_at=FIXED_NOW)
    endpoints = [call["endpoint"] for call in payload["api_calls"]]
    assert endpoints, "the artifact records the calls it made"
    for endpoint in endpoints:
        assert "?" not in endpoint
        assert "access_token" not in endpoint
    assert "https://www.googleapis.com/youtube/v3/channels" in endpoints


def test_the_artifact_carries_no_credential(harness: Harness, tmp_path: Path) -> None:
    harness.script_happy_path()
    payload = fetch_artifact(
        harness.reader, default_request(include_raw=True), fetched_at=FIXED_NOW
    )
    written = write_artifact(
        payload, tmp_path / "artifact.json", secret_values=harness.oauth.secret_values()
    )
    text = written.read_text(encoding="utf-8")
    assert_no_sentinel(text)
    for forbidden in ("Authorization", "Bearer ", "client_secret", "refresh_token"):
        assert forbidden not in text


def test_the_sanitizer_refuses_a_payload_holding_a_secret() -> None:
    with pytest.raises(YouTubeFetchError):
        assert_sanitized({"channel": {"note": ACCESS_TOKEN}}, SENTINELS)


def test_the_sanitizer_refuses_a_credential_shaped_key() -> None:
    with pytest.raises(YouTubeFetchError) as caught:
        assert_sanitized({"raw": {"token": {"refresh_token": "anything"}}}, ())
    assert "refresh_token" in str(caught.value)


def test_the_sanitizer_refuses_an_endpoint_with_a_query_string() -> None:
    with pytest.raises(YouTubeFetchError):
        assert_sanitized(
            {"api_calls": [{"endpoint": "https://example.com/v3/videos?id=1"}]}, ()
        )


def test_the_sanitizer_refuses_a_bearer_header() -> None:
    with pytest.raises(YouTubeFetchError):
        assert_sanitized({"api_calls": [{"note": "Bearer abc123"}]}, ())


# -- no artifact on a failed fetch ------------------------------------------


def test_a_failed_fetch_writes_no_artifact(harness: Harness, tmp_path: Path) -> None:
    destination = tmp_path / "artifact.json"
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(
        CHANNELS_KEY,
        403,
        {"error": {"code": 403, "errors": [{"reason": "quotaExceeded"}]}},
    )
    code = main(
        ["fetch", "--out", str(destination)],
        environment={},
        out=lambda _line: None,
        stack_factory=harness.stack,
    )
    assert code == 2
    assert not destination.exists()


def test_a_401_during_pagination_writes_no_artifact(
    harness: Harness, tmp_path: Path
) -> None:
    destination = tmp_path / "artifact.json"
    first_page = [f"vid{index:03d}" for index in range(50)]
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(TOKEN_KEY, 200, token_payload(access=SECOND_ACCESS_TOKEN))
    harness.fake.queue(CHANNELS_KEY, 200, channels_payload())
    harness.fake.queue(PLAYLIST_KEY, 200, playlist_payload(first_page, next_token="p2"))
    harness.fake.queue(PLAYLIST_KEY, 401, {"error": {"code": 401}})

    code = main(
        ["fetch", "--out", str(destination), "--videos", "60"],
        environment={},
        out=lambda _line: None,
        stack_factory=harness.stack,
    )
    assert code == 2
    assert not destination.exists()


def test_an_incomplete_pull_is_written_with_the_gap_recorded(
    harness: Harness, tmp_path: Path
) -> None:
    """A recorded gap is evidence; a suppressed file is not."""
    destination = tmp_path / "artifact.json"
    harness.script_happy_path(
        video_ids=("keep1", "gone1"), returned_ids=("keep1",)
    )
    code = main(
        ["fetch", "--out", str(destination), "--videos", "2"],
        environment={},
        out=lambda _line: None,
        stack_factory=harness.stack,
    )
    assert code == 0
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["video_retrieval"]["complete"] is False
    assert payload["video_retrieval"]["missing_video_ids"] == ["gone1"]
    assert payload["video_retrieval"]["notes"]


def test_require_complete_turns_a_gap_into_a_refusal_to_write(
    harness: Harness, tmp_path: Path
) -> None:
    destination = tmp_path / "artifact.json"
    harness.script_happy_path(video_ids=("keep1", "gone1"), returned_ids=("keep1",))
    code = main(
        ["fetch", "--out", str(destination), "--videos", "2", "--require-complete"],
        environment={},
        out=lambda _line: None,
        stack_factory=harness.stack,
    )
    assert code == 2
    assert not destination.exists()


# -- requirement 8 and 12: secrets never surface ----------------------------


def assert_no_sentinel(text: str) -> None:
    for sentinel in SENTINELS:
        assert sentinel not in text, f"{sentinel} leaked"


def test_no_secret_appears_in_a_repr_or_a_str(harness: Harness) -> None:
    grant = StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES)
    token = harness.oauth.authorization_request()
    assert_no_sentinel(repr(harness.config))
    assert_no_sentinel(str(harness.config))
    assert_no_sentinel(f"{harness.config}")
    assert_no_sentinel(repr(grant))
    assert_no_sentinel(str(grant))
    assert_no_sentinel(repr(token))

    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.oauth.access_token()
    access = harness.oauth._access
    assert access is not None and access.value == ACCESS_TOKEN
    assert_no_sentinel(repr(access))
    assert_no_sentinel(str(access))
    assert_no_sentinel(repr(harness.oauth.granted_scopes()))


def test_a_token_endpoint_error_cannot_quote_a_secret_back(harness: Harness) -> None:
    harness.fake.queue(
        TOKEN_KEY,
        400,
        {
            "error": "invalid_client",
            "error_description": (
                f"client_secret={CLIENT_SECRET} and refresh_token={REFRESH_TOKEN} "
                "were rejected"
            ),
        },
    )
    with pytest.raises(AuthorizationError) as caught:
        harness.oauth.access_token()
    assert_no_sentinel(str(caught.value))
    assert "[REDACTED]" in str(caught.value)


def test_a_token_endpoint_error_cannot_quote_a_bare_credential_back(tmp_path: Path) -> None:
    """The leak the `key=value` case above cannot detect.

    `_SENSITIVE_ASSIGNMENT` catches `refresh_token=...` because the key is right
    there. A provider that writes the same value as prose - "rejected for
    <token>" - defeats it, and on the authorization-code exchange there is no
    stored refresh token to seed the exact-value pass with either, so neither
    existing defence applies. This is the case that has to be matched on shape.
    """
    unheld = "1ZZrotated0refresh9token8xyz"  # never stored, never passed in
    harness = make_harness(tmp_path, with_grant=False)
    harness.fake.queue(
        TOKEN_KEY,
        400,
        {
            "error": "invalid_client",
            "error_description": f"the grant issued as {unheld} was rejected",
        },
    )
    with pytest.raises(AuthorizationError) as caught:
        harness.oauth.exchange_code("an-authorization-code", "a-code-verifier")
    message = str(caught.value)
    assert unheld not in message, message
    assert "[REDACTED]" in message
    # The diagnosis an operator needs survives the scrub.
    assert "invalid_client" in message
    assert not harness.store.exists()


def test_scrubbing_untrusted_text_leaves_diagnosis_intact() -> None:
    """The scrub is worth nothing if it eats the message it is protecting."""
    from tools.youtube_fetch.secrets_ import SecretRedactor

    redactor = SecretRedactor(CLIENT_SECRET)
    for kept in (
        "invalid_client: Client authentication failed",
        "redirect_uri_mismatch",
        "unauthorized_client",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
        "the daily quota for this project is exhausted",
        "video abcDEF_1 in playlist UU-company",
    ):
        assert redactor.scrub(kept) == kept, kept
    for masked in ("ya29.a0AfH6SMBx7K2LqQ9vTn3wZ", "1//0gAbCdEf12GhIjKlMnOp"):
        assert "[REDACTED]" in redactor.scrub(masked), masked


def test_an_api_error_cannot_quote_the_bearer_token_back(harness: Harness) -> None:
    harness.fake.queue(TOKEN_KEY, 200, token_payload())
    harness.fake.queue(
        CHANNELS_KEY,
        400,
        {
            "error": {
                "code": 400,
                "message": f"Authorization: Bearer {ACCESS_TOKEN} is malformed",
            }
        },
    )
    with pytest.raises(ApiError) as caught:
        harness.reader.channel()
    assert_no_sentinel(str(caught.value))


def test_an_os_error_from_the_protector_carries_no_os_text(tmp_path: Path) -> None:
    """Requirement 12: an OS failure while holding a token reports its type only."""

    class BrokenProtector:
        # The same name, so the store gets past the scheme check and actually
        # reaches `unprotect` - which is where the OS error comes from.
        name = "file_permissions"

        def protect(self, value: bytes) -> bytes:  # pragma: no cover - unused here
            return value

        def unprotect(self, value: bytes) -> bytes:
            raise OSError(f"the user profile holding {REFRESH_TOKEN} is corrupt")

    TokenStore(tmp_path / "token.json", FilePermissionProtector()).save(
        StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES)
    )
    with pytest.raises(AuthorizationError) as caught:
        TokenStore(tmp_path / "token.json", BrokenProtector()).load()
    assert_no_sentinel(str(caught.value))
    assert "OSError" in str(caught.value)


def test_a_malformed_stored_grant_is_typed() -> None:
    from tools.youtube_fetch.errors import TokenProtectionError

    with pytest.raises(TokenProtectionError):
        decode_protected(FilePermissionProtector(), "not base64 at all !!!")


@pytest.mark.skipif(os.name == "nt", reason="Windows does have DPAPI")
def test_asking_for_dpapi_off_windows_is_typed_not_an_import_error() -> None:
    from tools.youtube_fetch.errors import TokenProtectionError

    with pytest.raises(TokenProtectionError):
        WindowsDpapiProtector().protect(b"payload")


@pytest.mark.skipif(os.name != "nt", reason="DPAPI exists only on Windows")
def test_a_failing_dpapi_call_is_typed_and_redacted() -> None:
    from tools.youtube_fetch.errors import TokenProtectionError
    from tools.youtube_fetch.secrets_ import _windows_crypto

    api = dict(_windows_crypto())

    def raising(*_args: Any) -> int:
        raise OSError(f"CryptProtectData failed while holding {REFRESH_TOKEN}")

    with pytest.raises(TokenProtectionError) as caught:
        WindowsDpapiProtector._call(
            api, raising, b"payload", None, "protect the refresh token"
        )
    assert_no_sentinel(str(caught.value))
    assert "CryptProtectData" not in str(caught.value)

    with pytest.raises(TokenProtectionError):
        WindowsDpapiProtector._call(
            api, lambda *_args: 0, b"payload", None, "protect the refresh token"
        )


def test_no_secret_reaches_the_cli_output(harness: Harness, tmp_path: Path) -> None:
    lines: list[str] = []
    environment = {
        "YOUTUBE_CLIENT_ID": CLIENT_ID,
        "YOUTUBE_CLIENT_SECRET": CLIENT_SECRET,
        "YOUTUBE_REDIRECT_URI": REDIRECT_URI,
        "YOUTUBE_TOKEN_FILE": str(tmp_path / "token.json"),
    }
    assert main(["status"], environment=environment, out=lines.append) in (0, 1)

    harness.script_happy_path()
    assert (
        main(
            ["fetch", "--out", str(tmp_path / "artifact.json"), "--videos", "2"],
            environment=environment,
            out=lines.append,
            stack_factory=harness.stack,
        )
        == 0
    )
    assert_no_sentinel("\n".join(lines))
    assert any("Artifact written" in line for line in lines)


def test_the_cli_top_level_handler_redacts_the_message(tmp_path: Path) -> None:
    lines: list[str] = []

    def exploding_stack() -> Stack:
        raise ApiError(f"the provider said client_secret={CLIENT_SECRET} is wrong")

    code = main(
        ["fetch", "--out", str(tmp_path / "artifact.json")],
        environment={"YOUTUBE_CLIENT_SECRET": CLIENT_SECRET},
        out=lines.append,
        stack_factory=exploding_stack,
    )
    assert code == 2
    assert_no_sentinel("\n".join(lines))
    assert "[REDACTED]" in "\n".join(lines)


def test_nothing_is_logged_during_a_whole_fetch(
    harness: Harness, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    harness.script_happy_path()
    with caplog.at_level(logging.DEBUG):
        payload = fetch_artifact(
            harness.reader, default_request(include_raw=True), fetched_at=FIXED_NOW
        )
        write_artifact(
            payload, tmp_path / "artifact.json", secret_values=SENTINELS
        )
    assert_no_sentinel("\n".join(record.getMessage() for record in caplog.records))


def test_the_redactor_removes_the_longest_value_first() -> None:
    redactor = SecretRedactor("abcd", "abcdefgh", None, "xy")
    assert redactor.redact("abcdefgh and abcd") == "[REDACTED] and [REDACTED]"
    # A two-character value would redact prose, so it is ignored.
    assert "xy" in redactor.redact("the xylophone")


# -- token protection -------------------------------------------------------


def test_file_permission_protector_round_trip() -> None:
    protector = FilePermissionProtector()
    encoded = encode_protected(protector, REFRESH_TOKEN)
    assert REFRESH_TOKEN not in encoded or encoded != REFRESH_TOKEN
    assert decode_protected(protector, encoded) == REFRESH_TOKEN


@pytest.mark.skipif(os.name != "nt", reason="DPAPI exists only on Windows")
def test_windows_dpapi_round_trip() -> None:
    protector = WindowsDpapiProtector()
    protected = protector.protect(REFRESH_TOKEN.encode("utf-8"))
    assert REFRESH_TOKEN.encode("utf-8") not in protected
    assert protector.unprotect(protected).decode("utf-8") == REFRESH_TOKEN


@pytest.mark.skipif(os.name != "nt", reason="DPAPI exists only on Windows")
def test_a_token_store_round_trips_through_dpapi(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json", WindowsDpapiProtector())
    store.save(StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES))
    assert REFRESH_TOKEN not in (tmp_path / "token.json").read_text(encoding="utf-8")
    assert store.load().refresh_token == REFRESH_TOKEN


def test_the_token_file_never_holds_the_token_in_the_clear(tmp_path: Path) -> None:
    store = TokenStore(tmp_path / "token.json", FilePermissionProtector())
    store.save(StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES))
    stored = json.loads((tmp_path / "token.json").read_text(encoding="utf-8"))
    assert stored["protected_by"] == "file_permissions"
    assert stored["refresh_token"] != REFRESH_TOKEN
    assert stored["scopes"] == list(REQUIRED_SCOPES)


def test_a_token_written_by_another_protector_is_refused(tmp_path: Path) -> None:
    TokenStore(tmp_path / "token.json", FilePermissionProtector()).save(
        StoredGrant(REFRESH_TOKEN, REQUIRED_SCOPES)
    )

    class OtherProtector:
        name = "some_other_scheme"

        def protect(self, value: bytes) -> bytes:  # pragma: no cover - unused
            return value

        def unprotect(self, value: bytes) -> bytes:  # pragma: no cover - unused
            return value

    with pytest.raises(AuthorizationError):
        TokenStore(tmp_path / "token.json", OtherProtector()).load()
