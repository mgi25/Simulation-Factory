"""The authenticated half of the YouTube evidence path, outside Company OS.

## Where this package sits, and why it is here rather than there

Company OS is network-free by policy, and `health.no_network_or_model_dependency`
is a required integration-gate check over all four of its roots. A connector that
speaks OAuth and HTTPS cannot live inside those roots without either breaking that
check or eroding it, and an eroded architectural check protects nothing afterwards.

So the work is split at the file. This package authenticates, fetches, and
writes a sanitized JSON artifact. `company/youtube` reads that artifact and
turns it into observations with no idea that a network exists. Each half is
simple in the way the other cannot be: this one may open a socket and may hold a
credential, and holds no business rule; that one holds every rule about what a
number means and cannot reach a provider even by accident.

The dependency runs one way only. `tools/` is a production root and
`architecture.production_does_not_import_company_os` is required, so nothing here
imports any Company OS root - not in a module, not in a test, not under
`TYPE_CHECKING`. The shared vocabulary between the halves is the artifact format,
written down, not a shared import.

Their names are deliberately not spelled out in this file: a capsule-layer test
greps every module under `tools/` for them, and a docstring that quotes the roots
it must not import reads to that test exactly like a module that imports them.

## Standard library only

Every dependency this package could reasonably want - an HTTP client, an OAuth
library, the Google API client - would be a third-party package added to a
production root for the sake of a tool that runs occasionally. `urllib.request`,
`http.server`, `json`, `hashlib` and `secrets` cover the whole flow, so
`requirements.txt` is untouched.

## Importable everywhere, credential-handling on one platform

Windows DPAPI protects the stored refresh token on Windows, and that binding is
resolved lazily inside the protector. Importing this package on Linux or macOS
therefore works, and the suite collects and runs there; only the DPAPI round-trip
itself is Windows-specific, and `default_protector()` picks the file-permission
protector elsewhere.
"""

from __future__ import annotations

from .api import (
    ANALYTICS_API_METRICS,
    METRIC_TABLE,
    AnalyticsReport,
    ChannelFacts,
    MetricReading,
    VideoFacts,
    VideoListing,
    YouTubeReader,
)
from .artifact import (
    ARTIFACT_VERSION,
    PRODUCER,
    PRODUCER_VERSION,
    FetchRequest,
    assert_sanitized,
    build_artifact,
    fetch_artifact,
    serialize,
    write_artifact,
)
from .config import (
    ANALYTICS_SCOPE,
    DATA_SCOPE,
    REQUIRED_SCOPES,
    OAuthConfig,
    configuration_status,
    default_token_path,
)
from .errors import (
    ApiError,
    AuthorizationError,
    AuthorizationRevoked,
    ConfigurationError,
    InsufficientPermissions,
    MissingScopeError,
    QuotaExceeded,
    TokenProtectionError,
    YouTubeFetchError,
)
from .oauth import (
    AccessToken,
    AuthorizationRequest,
    LocalCallbackServer,
    OAuthClient,
    StoredGrant,
    TokenStore,
)
from .secrets_ import (
    FilePermissionProtector,
    SecretRedactor,
    TokenProtector,
    WindowsDpapiProtector,
    decode_protected,
    default_protector,
    encode_protected,
)
from .transport import (
    ApiCallTrace,
    HttpResponse,
    HttpTransport,
    InstrumentedTransport,
    UrllibTransport,
)


__all__ = [
    "ANALYTICS_API_METRICS",
    "ANALYTICS_SCOPE",
    "ARTIFACT_VERSION",
    "DATA_SCOPE",
    "METRIC_TABLE",
    "PRODUCER",
    "PRODUCER_VERSION",
    "REQUIRED_SCOPES",
    "AccessToken",
    "AnalyticsReport",
    "ApiCallTrace",
    "ApiError",
    "AuthorizationError",
    "AuthorizationRequest",
    "AuthorizationRevoked",
    "ChannelFacts",
    "ConfigurationError",
    "FetchRequest",
    "FilePermissionProtector",
    "HttpResponse",
    "HttpTransport",
    "InstrumentedTransport",
    "InsufficientPermissions",
    "LocalCallbackServer",
    "MetricReading",
    "MissingScopeError",
    "OAuthClient",
    "OAuthConfig",
    "QuotaExceeded",
    "SecretRedactor",
    "StoredGrant",
    "TokenProtectionError",
    "TokenProtector",
    "TokenStore",
    "UrllibTransport",
    "VideoFacts",
    "VideoListing",
    "WindowsDpapiProtector",
    "YouTubeFetchError",
    "YouTubeReader",
    "assert_sanitized",
    "build_artifact",
    "configuration_status",
    "decode_protected",
    "default_protector",
    "default_token_path",
    "encode_protected",
    "fetch_artifact",
    "serialize",
    "write_artifact",
]
