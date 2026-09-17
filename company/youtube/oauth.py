"""OAuth 2.0 authorization-code and refresh-token flow for YouTube."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from typing import Callable, Mapping
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser

from .config import OAuthConfig
from .errors import AuthorizationError, AuthorizationRevoked, ConfigurationError
from .security import (
    SecretRedactor,
    TokenProtector,
    decode_protected,
    default_protector,
    encode_protected,
)
from .transport import HttpTransport


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


@dataclass(frozen=True)
class StoredGrant:
    refresh_token: str
    scopes: tuple[str, ...]


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_at: dt.datetime
    scopes: tuple[str, ...]

    def usable_at(self, now: dt.datetime) -> bool:
        return now + dt.timedelta(seconds=30) < self.expires_at


class TokenStore:
    """One local refresh grant, protected for the current OS user."""

    def __init__(self, path: str | Path, protector: TokenProtector | None = None) -> None:
        self.path = Path(path).expanduser().resolve()
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
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
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
                if written <= 0:
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
            if data.get("version") != 1:
                raise ValueError("unsupported token format")
            if data.get("protected_by") != self.protector.name:
                raise ValueError("token protection does not match this operating system")
            refresh = decode_protected(self.protector, str(data["refresh_token"]))
            scopes = tuple(str(scope) for scope in data.get("scopes", ()))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AuthorizationError(
                f"could not read the local refresh grant: {type(exc).__name__}"
            ) from None
        if not refresh:
            raise AuthorizationError("the local refresh grant is empty")
        return StoredGrant(refresh, scopes)


@dataclass(frozen=True)
class AuthorizationRequest:
    url: str
    state: str
    code_verifier: str


class OAuthClient:
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
        self.redactor = SecretRedactor(config.client_secret)

    def authorization_request(self) -> AuthorizationRequest:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
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
            revoked=False,
        )
        refresh = payload.get("refresh_token")
        if not isinstance(refresh, str) or not refresh:
            raise AuthorizationError(
                "Google returned no refresh token; revoke the app grant and authorize again"
            )
        scopes = _scopes(payload.get("scope")) or self.config.scopes
        self.token_store.save(StoredGrant(refresh, scopes))
        self._access = self._access_from(payload, scopes)
        return self._access

    def access_token(self, *, force_refresh: bool = False) -> str:
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
            revoked=True,
            extra_secrets=(grant.refresh_token,),
        )
        scopes = _scopes(payload.get("scope")) or grant.scopes
        rotated = payload.get("refresh_token")
        if isinstance(rotated, str) and rotated:
            self.token_store.save(StoredGrant(rotated, scopes))
        self._access = self._access_from(payload, scopes)
        return self._access.value

    def authorize_interactively(
        self,
        *,
        open_browser: bool = True,
        timeout: float = 180.0,
    ) -> AccessToken:
        request = self.authorization_request()
        callback = _LocalCallback(self.config.redirect_uri, request.state)
        def ready() -> None:
            if open_browser:
                if not webbrowser.open(request.url, new=1, autoraise=True):
                    print(request.url)
            else:
                print(request.url)

        code = callback.wait(timeout, ready=ready)
        return self.exchange_code(code, request.code_verifier)

    def _token_request(
        self,
        parameters: Mapping[str, str],
        *,
        revoked: bool,
        extra_secrets: tuple[str, ...] = (),
    ) -> dict[str, object]:
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
        if not 200 <= response.status < 300:
            reason = payload.get("error", "token_endpoint_error") if isinstance(payload, dict) else "token_endpoint_error"
            safe = SecretRedactor(self.config.client_secret, *extra_secrets).redact(reason)
            if revoked and reason == "invalid_grant":
                raise AuthorizationRevoked(
                    "the saved Google authorization was revoked or expired; run auth again"
                )
            raise AuthorizationError(f"OAuth token request failed ({response.status}): {safe}")
        if not isinstance(payload, dict):
            raise AuthorizationError("OAuth token response was not an object")
        return payload

    def _access_from(self, payload: Mapping[str, object], scopes: tuple[str, ...]) -> AccessToken:
        access = payload.get("access_token")
        expires = payload.get("expires_in")
        if not isinstance(access, str) or not access:
            raise AuthorizationError("OAuth token response omitted the access token")
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or expires <= 0:
            raise AuthorizationError("OAuth token response omitted a valid expiry")
        return AccessToken(access, self.now() + dt.timedelta(seconds=float(expires)), scopes)


class _LocalCallback:
    def __init__(self, redirect_uri: str, expected_state: str) -> None:
        parsed = urlparse(redirect_uri)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ConfigurationError(
                "interactive auth requires a loopback http YOUTUBE_REDIRECT_URI"
            )
        if parsed.port is None:
            raise ConfigurationError("loopback YOUTUBE_REDIRECT_URI must include a port")
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path or "/"
        self.expected_state = expected_state

    def wait(self, timeout: float, *, ready: Callable[[], None]) -> str:
        result: dict[str, str] = {}
        expected_path = self.path
        expected_state = self.expected_state

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
                parsed = urlparse(self.path)
                values = parse_qs(parsed.query)
                if parsed.path != expected_path:
                    self.send_error(404)
                    return
                state = values.get("state", [""])[0]
                if not secrets.compare_digest(state, expected_state):
                    result["error"] = "OAuth callback state did not match"
                    self.send_error(400)
                    return
                if values.get("error"):
                    result["error"] = "authorization was denied"
                    self.send_error(400)
                    return
                result["code"] = values.get("code", [""])[0]
                body = b"Authorization received. You may close this window."
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = HTTPServer((self.host, self.port), Handler)
        server.timeout = max(0.1, timeout)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()
        ready()
        thread.join(timeout + 1.0)
        server.server_close()
        if thread.is_alive():
            raise AuthorizationError("timed out waiting for the OAuth callback")
        if result.get("error"):
            raise AuthorizationError(result["error"])
        if not result.get("code"):
            raise AuthorizationError("OAuth callback did not contain an authorization code")
        return result["code"]


def _scopes(value: object) -> tuple[str, ...]:
    return tuple(str(value).split()) if isinstance(value, str) else ()


__all__ = [
    "AccessToken",
    "AuthorizationRequest",
    "OAuthClient",
    "StoredGrant",
    "TokenStore",
]
