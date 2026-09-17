"""What this fetcher is allowed to ask Google for, and where it keeps the answer.

## Two scopes, and a type that cannot hold a third

`REQUIRED_SCOPES` is not a default that a caller may extend. It is the complete
requested set, and `OAuthConfig.__post_init__` refuses any other set outright.

The reason is that scope creep in an OAuth client is invisible in review: an
opt-in flag for the revenue scope reads as an option, and the consent screen the
operator clicks reads as a formality, but the effect is that a read-only
analytics tool holds a grant over revenue data forever afterwards. The previous
version of this package had exactly that flag. It is gone, along with the
constant behind it, and the shape of this dataclass is what keeps it gone: there
is no parameter to pass and no set of scopes other than these two that can be
constructed. A test asserts the set has not grown, which turns any future
addition into a failing build rather than a line in a diff.

Requesting less is refused for the same reason requesting more is: a config
holding only the Data scope would produce an artifact with no analytics in it
and no explanation of why, and "the numbers are missing" is a much worse failure
than "authorization refused".

## No secret has a default and no secret is in the repository

The client id, the client secret and the redirect URI come from the environment,
or from the Google client JSON file the console hands out - a path in
`YOUTUBE_CLIENT_CONFIG_FILE`, never its contents copied into source. Absent
configuration is a `ConfigurationError` naming the variables that are missing,
because the alternative - an empty-string default that reaches Google and comes
back as `invalid_client` - sends the operator looking at the wrong end.

`client_secret` is declared `field(repr=False)`. A frozen dataclass has a
generated `__repr__` that is reached by `str()`, by `%s`, by f-strings, by
`print()`, by pytest assertion rewriting and by every logging call that
interpolates an object, so a secret in the default repr is a secret in all of
them. `repr=False` closes all of those at once.

## Where the token lives

`default_token_path` follows the platform convention - `%LOCALAPPDATA%` on
Windows, `$XDG_CONFIG_HOME` (or `~/.config`) elsewhere - so the grant sits with
the other per-user credentials rather than in the repository, where it would be
one `git add -A` from being published. `YOUTUBE_TOKEN_FILE` overrides it, which
is what the tests use.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

from .errors import ConfigurationError


DATA_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"

# The complete requested set. Not a default, not a starting point: the whole of
# what this fetcher ever asks a Google account to consent to.
REQUIRED_SCOPES: tuple[str, ...] = (DATA_SCOPE, ANALYTICS_SCOPE)


def default_token_path(environment: Mapping[str, str] | None = None) -> Path:
    """Where the refresh grant lives for this operating system and user."""
    env = os.environ if environment is None else environment
    override = env.get("YOUTUBE_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        root = Path(env.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
        return root / "CompanyOS" / "youtube" / "token.json"
    root = Path(env.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return root / "company-os" / "youtube" / "token.json"


@dataclass(frozen=True)
class OAuthConfig:
    """One installed-app OAuth client, with the scope set pinned by construction."""

    client_id: str
    client_secret: str = field(repr=False)
    redirect_uri: str
    token_path: Path
    scopes: tuple[str, ...] = REQUIRED_SCOPES

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
        if tuple(self.scopes) != REQUIRED_SCOPES:
            raise ConfigurationError(
                "this fetcher requests exactly the two read-only scopes and no others: "
                + ", ".join(REQUIRED_SCOPES)
            )

    @classmethod
    def from_environment(
        cls, environment: Mapping[str, str] | None = None
    ) -> OAuthConfig:
        """Build from environment variables, or from the Google client JSON file."""
        env = os.environ if environment is None else environment
        file_values: dict[str, str] = {}
        config_path = env.get("YOUTUBE_CLIENT_CONFIG_FILE", "")
        if config_path:
            file_values = _read_google_client_file(Path(config_path).expanduser())
        return cls(
            client_id=env.get("YOUTUBE_CLIENT_ID") or file_values.get("client_id", ""),
            client_secret=(
                env.get("YOUTUBE_CLIENT_SECRET") or file_values.get("client_secret", "")
            ),
            redirect_uri=(
                env.get("YOUTUBE_REDIRECT_URI") or file_values.get("redirect_uri", "")
            ),
            token_path=default_token_path(env),
        )


def configuration_status(environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    """What an operator needs to know before running anything, with no secret in it.

    Deliberately reports three booleans and a path. Whether the client is
    configured, whether a grant exists and where it would be are the whole of
    what `status` can say without either touching the network or naming a value.
    """
    env = os.environ if environment is None else environment
    path = default_token_path(env)
    configured = False
    try:
        OAuthConfig.from_environment(env)
        configured = True
    except ConfigurationError:
        configured = False
    return {
        "oauth_client_configured": configured,
        "refresh_token_available": path.is_file(),
        "token_path": str(path),
        "requested_scopes": list(REQUIRED_SCOPES),
    }


def _read_google_client_file(path: Path) -> dict[str, str]:
    """Read the console's client JSON, reporting failures without quoting it."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ConfigurationError(
            f"could not read YOUTUBE_CLIENT_CONFIG_FILE ({type(exc).__name__})"
        ) from None
    block = data.get("installed") or data.get("web") if isinstance(data, dict) else None
    if not isinstance(block, dict):
        raise ConfigurationError(
            "YOUTUBE_CLIENT_CONFIG_FILE holds no installed/web OAuth client block"
        )
    redirects = block.get("redirect_uris") or []
    return {
        "client_id": str(block.get("client_id", "")),
        "client_secret": str(block.get("client_secret", "")),
        "redirect_uri": str(redirects[0]) if isinstance(redirects, list) and redirects else "",
    }


__all__ = [
    "ANALYTICS_SCOPE",
    "DATA_SCOPE",
    "REQUIRED_SCOPES",
    "OAuthConfig",
    "configuration_status",
    "default_token_path",
]
