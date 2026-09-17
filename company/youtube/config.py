"""Environment/local-file configuration without secret defaults."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from .errors import ConfigurationError


DATA_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"
MONETARY_SCOPE = "https://www.googleapis.com/auth/yt-analytics-monetary.readonly"
DEFAULT_SCOPES = (DATA_SCOPE, ANALYTICS_SCOPE)


def default_token_path(environment: Mapping[str, str] | None = None) -> Path:
    env = os.environ if environment is None else environment
    if env.get("YOUTUBE_TOKEN_FILE"):
        return Path(env["YOUTUBE_TOKEN_FILE"]).expanduser()
    if os.name == "nt":
        root = Path(env.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "CompanyOS" / "youtube" / "token.json"
    root = Path(env.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "company-os" / "youtube" / "token.json"


@dataclass(frozen=True)
class OAuthConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    token_path: Path
    scopes: tuple[str, ...] = DEFAULT_SCOPES

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("YOUTUBE_CLIENT_ID", self.client_id),
                ("YOUTUBE_CLIENT_SECRET", self.client_secret),
                ("YOUTUBE_REDIRECT_URI", self.redirect_uri),
            )
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            raise ConfigurationError("missing OAuth configuration: " + ", ".join(missing))
        parsed = urlparse(self.redirect_uri)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ConfigurationError("YOUTUBE_REDIRECT_URI must be an absolute http(s) URL")
        if any(scope not in {DATA_SCOPE, ANALYTICS_SCOPE, MONETARY_SCOPE} for scope in self.scopes):
            raise ConfigurationError("an unsupported YouTube OAuth scope was configured")
        if DATA_SCOPE not in self.scopes or ANALYTICS_SCOPE not in self.scopes:
            raise ConfigurationError("the read-only Data and Analytics scopes are both required")

    @classmethod
    def from_environment(
        cls,
        environment: Mapping[str, str] | None = None,
        *,
        include_monetary: bool = False,
    ) -> "OAuthConfig":
        env = os.environ if environment is None else environment
        file_values: dict[str, str] = {}
        config_path = env.get("YOUTUBE_CLIENT_CONFIG_FILE", "")
        if config_path:
            file_values = _read_google_client_file(Path(config_path).expanduser())
        scopes = DEFAULT_SCOPES + ((MONETARY_SCOPE,) if include_monetary else ())
        return cls(
            client_id=env.get("YOUTUBE_CLIENT_ID") or file_values.get("client_id", ""),
            client_secret=env.get("YOUTUBE_CLIENT_SECRET")
            or file_values.get("client_secret", ""),
            redirect_uri=env.get("YOUTUBE_REDIRECT_URI")
            or file_values.get("redirect_uri", ""),
            token_path=default_token_path(env),
            scopes=scopes,
        )


def configuration_status(environment: Mapping[str, str] | None = None) -> dict[str, object]:
    env = os.environ if environment is None else environment
    path = default_token_path(env)
    configured = False
    try:
        OAuthConfig.from_environment(env)
        configured = True
    except ConfigurationError:
        pass
    return {
        "oauth_client_configured": configured,
        "refresh_token_available": path.is_file(),
        "token_path": str(path),
    }


def _read_google_client_file(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(f"could not read YOUTUBE_CLIENT_CONFIG_FILE: {type(exc).__name__}") from None
    block = data.get("installed") or data.get("web") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        raise ConfigurationError("YOUTUBE_CLIENT_CONFIG_FILE has no installed/web OAuth client")
    redirects = block.get("redirect_uris") or []
    return {
        "client_id": str(block.get("client_id", "")),
        "client_secret": str(block.get("client_secret", "")),
        "redirect_uri": str(redirects[0]) if redirects else "",
    }


__all__ = [
    "ANALYTICS_SCOPE",
    "DATA_SCOPE",
    "DEFAULT_SCOPES",
    "MONETARY_SCOPE",
    "OAuthConfig",
    "configuration_status",
    "default_token_path",
]
