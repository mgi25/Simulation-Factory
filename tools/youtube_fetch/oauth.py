"""The authorization-code flow, the stored grant, and the loopback that receives it.

## The grant is checked before it is kept, not after

Google is free to return fewer scopes than were asked for: the consent screen
has checkboxes, and an operator who clears one still completes the flow. The
version this replaces stored the refresh token first and discovered the gap
later, at the point where an analytics call came back 403 - by which time the
machine held a long-lived grant that could not do the job, and the operator's
next move was to debug an API error rather than to re-consent.

So `exchange_code` compares the *granted* scope set against `REQUIRED_SCOPES`
and raises `MissingScopeError` **before** `TokenStore.save` is reached. A
partial consent therefore leaves no trace on disk at all: the next run finds no
grant, says so, and asks for authorization again, which is the correct and
obvious repair.

## The callback server serves until it hears what it is waiting for

`handle_request()` handles *one* request. A browser opening the consent page
commonly asks for `/favicon.ico` first, and a server that handles one request
consumes the favicon, closes, and reports a timeout while the real callback -
carrying the authorization code - arrives at a closed port. The operator then
authorizes again, and again, and eventually concludes the tool is broken.

`LocalCallbackServer` therefore loops against a monotonic deadline and stops on
one condition only: the expected path arrived. Everything else gets a 404 and
the loop continues. `handle_path` holds that decision as a pure function of the
request line, which is what makes the behaviour testable without opening a
socket: the test drives it with a favicon and then the real callback, and
asserts the authorization still completes.

`state` is compared with `secrets.compare_digest`, and PKCE is unconditional -
the verifier never leaves this process and the challenge is what travels - so a
callback forged by another local process cannot complete the exchange.

## Two fields that are never in a repr

`StoredGrant.refresh_token` and `AccessToken.value` are `field(repr=False)`. A
frozen dataclass's generated `__repr__` is what `str()`, f-strings, `print()`,
logging interpolation and pytest's assertion rewriting all reach, so a
credential visible to `repr` is a credential visible to all of them. Suppressing
it once covers every one of those surfaces.

Every error raised here is redacted first, with the values in scope where it is
raised - the client secret always, and the code, verifier or refresh token where
the failure involves one. A token endpoint that quotes a request parameter back
in its error body is ordinary behaviour, not an edge case.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import secrets
import time
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse

from .config import REQUIRED_SCOPES, OAuthConfig
from .errors import (
    AuthorizationError,
    AuthorizationRevoked,
    ConfigurationError,
    MissingScopeError,
    TokenProtectionError,
)
from .secrets_ import (
    SecretRedactor,
    TokenProtector,
    decode_protected,
    default_protector,
    encode_protected,
)
from .transport import HttpTransport


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"

# An access token is refreshed this far before it expires, so a long paginated
# walk cannot have one go stale between two pages of the same listing.
EXPIRY_MARGIN_SECONDS = 60


@dataclass(frozen=True)
class StoredGrant:
    """The one long-lived credential this fetcher keeps, and what it covers."""

    refresh_token: str = field(repr=False)
    scopes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccessToken:
    """A short-lived bearer token. Memory only; never written anywhere."""

    value: str = field(repr=False)
    expires_at: dt.datetime
    scopes: tuple[str, ...] = ()

    def usable_at(self, now: dt.datetime) -> bool:
        return now + dt.timedelta(seconds=EXPIRY_MARGIN_SECONDS) < self.expires_at


@dataclass(frozen=True)
class AuthorizationRequest:
    """The URL the operator opens, plus the two values that must not travel with it."""

    url: str
    state: str = field(repr=False)
    code_verifier: str = field(repr=False)


class TokenStore:
    """One local refresh grant, protected for the current OS user.

    The file is written to a temporary name with mode 0600 and then renamed, so
    a crash mid-write cannot leave a half-token in place, and no moment exists
    where the file is on disk with default permissions.
    """

    def __init__(self, path: str | Path, protector: TokenProtector | None = None) -> None:
        self.path = Path(path).expanduser()
        self.protector = protector or default_protector()

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, grant: StoredGrant) -> None:
        if not grant.refresh_token:
            raise AuthorizationError("Google did not return a refresh token")
        payload = {
            "version": 1,
            "protected_by": self.protector.name,
            "refresh_token": encode_protected(self.protector, grant.refresh_token),
            "scopes": list(grant.scopes),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            # Windows has no POSIX mode; the DPAPI binding is the protection there.
            pass
        temporary = self.path.with_name(f".{self.path.name}.{secrets.token_hex(6)}.tmp")
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            0o600,
        )
        try:
            data = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
            offset = 0
            while offset < len(data):
                written = os.write(descriptor, data[offset:])
                if written <= 0:  # pragma: no cover - defensive
                    raise OSError("short write while saving the refresh grant")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def load(self) -> StoredGrant:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError("unsupported token format")
            if data.get("protected_by") != self.protector.name:
                raise ValueError("token protection does not match this operating system")
            refresh = decode_protected(self.protector, str(data["refresh_token"]))
            scopes = tuple(str(scope) for scope in data.get("scopes", ()))
        except TokenProtectionError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            # The file holds a protected credential; only the failure type escapes.
            raise AuthorizationError(
                f"could not read the local refresh grant ({type(exc).__name__}); "
                "run `python -m tools.youtube_fetch auth` again"
            ) from None
        if not refresh:
            raise AuthorizationError("the local refresh grant is empty")
        return StoredGrant(refresh, scopes)


class LocalCallbackServer:
    """A loopback listener that waits for one specific path and 404s everything else."""

    def __init__(self, redirect_uri: str, expected_state: str) -> None:
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ConfigurationError(
                "interactive auth requires a loopback http YOUTUBE_REDIRECT_URI"
            )
        if parsed.port is None:
            raise ConfigurationError("the loopback YOUTUBE_REDIRECT_URI must include a port")
        self.host: str = parsed.hostname
        self.port: int = parsed.port
        self.expected_path: str = parsed.path or "/"
        self.expected_state = expected_state
        self.code: str = ""
        self.failure: str = ""
        self.ignored_paths: list[str] = []

    @property
    def finished(self) -> bool:
        """True once the expected path has been seen, however it turned out."""
        return bool(self.code) or bool(self.failure)

    def handle_path(self, raw_path: str) -> tuple[int, bytes]:
        """Classify one request line. The whole callback decision lives here.

        Returns the status and body to send. Only the expected path can end the
        wait; a favicon, a probe or a stray bookmark gets a 404 and leaves the
        server listening for the callback that matters.
        """
        parsed = urlparse(raw_path)
        if parsed.path != self.expected_path:
            self.ignored_paths.append(parsed.path)
            return 404, b"Not found. This port is waiting for a Google OAuth callback."
        values = parse_qs(parsed.query)
        state = values.get("state", [""])[0]
        if not secrets.compare_digest(state, self.expected_state):
            self.failure = "the OAuth callback state did not match the request"
            return 400, b"State mismatch. Nothing was stored."
        if values.get("error"):
            # The provider's error slug is a fixed vocabulary, not free text.
            self.failure = "authorization was denied at the Google consent screen"
            return 400, b"Authorization denied. Nothing was stored."
        code = values.get("code", [""])[0]
        if not code:
            self.failure = "the OAuth callback carried no authorization code"
            return 400, b"No authorization code. Nothing was stored."
        self.code = code
        return 200, b"Authorization received. You may close this window."

    def wait(
        self,
        timeout: float,
        *,
        ready: Callable[[], None] = lambda: None,
        server_factory: Callable[[], Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> str:
        """Serve requests until the callback arrives or the deadline passes."""
        server = (server_factory or self._http_server)()
        try:
            ready()
            deadline = clock() + max(0.1, timeout)
            while not self.finished:
                remaining = deadline - clock()
                if remaining <= 0:
                    break
                # A short per-request timeout is what lets the deadline be real:
                # a single long block would ignore it until the request returned.
                server.timeout = min(1.0, max(0.05, remaining))
                server.handle_request()
        finally:
            server.server_close()
        if self.failure:
            raise AuthorizationError(self.failure)
        if not self.code:
            raise AuthorizationError(
                "timed out waiting for the Google OAuth callback on "
                f"{self.host}:{self.port}{self.expected_path}"
            )
        return self.code

    def _http_server(self) -> HTTPServer:
        callback = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - the stdlib chooses this name
                status, body = callback.handle_path(self.path)
                self.send_response(status)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                # The request line holds the authorization code.
                return

        return HTTPServer((self.host, self.port), Handler)


class OAuthClient:
    """Authorization-code exchange and refresh, with every failure typed and redacted."""

    def __init__(
        self,
        config: OAuthConfig,
        transport: HttpTransport,
        token_store: TokenStore | None = None,
        *,
        now: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self.token_store = token_store or TokenStore(config.token_path)
        self.now = now or (lambda: dt.datetime.now(dt.timezone.utc))
        self._access: AccessToken | None = None
        self._granted_scopes: tuple[str, ...] = ()

    @property
    def redactor(self) -> SecretRedactor:
        """Seeded with everything secret this client is currently holding."""
        return SecretRedactor(
            self.config.client_secret,
            self._access.value if self._access is not None else None,
        )

    def secret_values(self) -> tuple[str, ...]:
        """Every secret this client is holding, for a sanitizer to prove absent."""
        return self.redactor.values

    def authorization_request(self) -> AuthorizationRequest:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
            .rstrip(b"=")
            .decode("ascii")
        )
        query = urlencode(
            {
                "client_id": self.config.client_id,
                "redirect_uri": self.config.redirect_uri,
                "response_type": "code",
                "scope": " ".join(self.config.scopes),
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "consent",
                "state": state,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
        return AuthorizationRequest(f"{AUTHORIZATION_ENDPOINT}?{query}", state, verifier)

    def exchange_code(self, code: str, code_verifier: str) -> AccessToken:
        """Trade the callback code for tokens, verifying consent before storing it."""
        if not code.strip():
            raise AuthorizationError("the OAuth callback did not contain a code")
        payload = self._token_request(
            {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self.config.redirect_uri,
            },
            extra_secrets=(code, code_verifier),
        )
        granted = scopes_of(payload.get("scope"))
        missing = tuple(scope for scope in REQUIRED_SCOPES if scope not in granted)
        if missing:
            # Nothing has been written yet, and nothing will be: a partial grant
            # leaves the machine exactly as it was before the flow started.
            raise MissingScopeError(
                "Google granted "
                + (", ".join(granted) if granted else "no scopes")
                + "; this fetcher cannot run without "
                + ", ".join(missing)
                + ". Authorize again and accept every requested permission."
            )
        refresh = payload.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            raise AuthorizationError(
                "Google returned no refresh token; revoke this app's access in your "
                "Google account and authorize again"
            )
        self.token_store.save(StoredGrant(refresh, granted))
        self._granted_scopes = granted
        self._access = self._access_from(payload, granted)
        return self._access

    def access_token(self, *, force_refresh: bool = False) -> str:
        """The cached bearer token, refreshing it when it is stale or forced."""
        now = self.now()
        if not force_refresh and self._access is not None and self._access.usable_at(now):
            return self._access.value
        grant = self.token_store.load()
        payload = self._token_request(
            {
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "refresh_token": grant.refresh_token,
                "grant_type": "refresh_token",
            },
            extra_secrets=(grant.refresh_token,),
        )
        scopes = scopes_of(payload.get("scope")) or grant.scopes
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated and rotated != grant.refresh_token:
            self.token_store.save(StoredGrant(rotated, scopes))
        self._granted_scopes = scopes
        self._access = self._access_from(payload, scopes)
        return self._access.value

    def granted_scopes(self) -> tuple[str, ...]:
        """What the current grant actually covers, for the artifact to record."""
        if self._granted_scopes:
            return self._granted_scopes
        if self.token_store.exists():
            return self.token_store.load().scopes
        return ()

    def authorize_interactively(
        self,
        *,
        open_browser: bool = True,
        timeout: float = 180.0,
        announce: Callable[[str], None] = print,
        server_factory: Callable[[], Any] | None = None,
    ) -> AccessToken:
        """Run the one-time consent flow and return the first access token."""
        request = self.authorization_request()
        callback = LocalCallbackServer(self.config.redirect_uri, request.state)

        def ready() -> None:
            if open_browser and webbrowser.open(request.url, new=1, autoraise=True):
                announce("A browser window was opened for Google authorization.")
                return
            announce("Open this URL in a browser to authorize:")
            announce(request.url)

        code = callback.wait(timeout, ready=ready, server_factory=server_factory)
        return self.exchange_code(code, request.code_verifier)

    def _token_request(
        self,
        parameters: Mapping[str, str],
        *,
        extra_secrets: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        redactor = self.redactor.with_values(*extra_secrets)
        response = self.transport.request(
            "POST",
            TOKEN_ENDPOINT,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            body=urlencode(parameters).encode("utf-8"),
        )
        try:
            payload = json.loads(response.body.decode("utf-8")) if response.body else {}
        except (UnicodeDecodeError, ValueError):
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        if not 200 <= response.status < 300:
            reason = str(payload.get("error") or "token_endpoint_error")
            description = str(payload.get("error_description") or "")
            if reason == "invalid_grant":
                raise AuthorizationRevoked(
                    "Google rejected the authorization (invalid_grant): the grant was "
                    "revoked, expired, or already used. Run `auth` again."
                )
            # `scrub`, not `redact`: `error_description` is free text from the
            # provider and may quote back a credential this process never held,
            # which no list of known values can remove.
            detail = redactor.scrub(f"{reason}: {description}" if description else reason)
            raise AuthorizationError(f"the OAuth token request failed ({response.status}): {detail}")
        if not payload:
            raise AuthorizationError("the OAuth token response was not a JSON object")
        return payload

    def _access_from(
        self, payload: Mapping[str, Any], scopes: tuple[str, ...]
    ) -> AccessToken:
        access = payload.get("access_token")
        expires = payload.get("expires_in")
        if not isinstance(access, str) or not access:
            raise AuthorizationError("the OAuth token response omitted the access token")
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or expires <= 0:
            raise AuthorizationError("the OAuth token response omitted a valid expiry")
        return AccessToken(
            access, self.now() + dt.timedelta(seconds=float(expires)), scopes
        )


def scopes_of(value: object) -> tuple[str, ...]:
    """Google returns the granted scopes as one space-separated string."""
    return tuple(str(value).split()) if isinstance(value, str) else ()


__all__ = [
    "AUTHORIZATION_ENDPOINT",
    "TOKEN_ENDPOINT",
    "AccessToken",
    "AuthorizationRequest",
    "LocalCallbackServer",
    "OAuthClient",
    "StoredGrant",
    "TokenStore",
    "scopes_of",
]
