"""Production read-only connectivity for a Company's own YouTube channel.

The connector keeps OAuth grants outside Git, performs only GET requests to
the Data and Analytics APIs, preserves raw and normalized evidence separately,
and can bridge per-video analytics into the existing append-only analytics
store.  It does not classify Shorts, recommend changes, or mutate YouTube.
"""

from .bridge import AnalyticsCommit, build_deliverable, commit_analytics
from .client import ANALYTICS_API_METRICS, YouTubeClient
from .config import (
    ANALYTICS_SCOPE,
    DATA_SCOPE,
    DEFAULT_SCOPES,
    MONETARY_SCOPE,
    OAuthConfig,
    configuration_status,
)
from .errors import (
    ApiError,
    AuthorizationError,
    AuthorizationRevoked,
    ConfigurationError,
    EvidenceError,
    YouTubeConnectorError,
)
from .models import (
    AnalyticsEvidence,
    ChannelEvidence,
    MetricReading,
    RetrievedEvidence,
    VideoEvidence,
)
from .oauth import AccessToken, OAuthClient, StoredGrant, TokenStore
from .store import YouTubeEvidencePointer, YouTubeEvidenceStore
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
    "AccessToken",
    "AnalyticsCommit",
    "AnalyticsEvidence",
    "ApiCallTrace",
    "ApiError",
    "AuthorizationError",
    "AuthorizationRevoked",
    "ChannelEvidence",
    "ConfigurationError",
    "DATA_SCOPE",
    "DEFAULT_SCOPES",
    "EvidenceError",
    "HttpResponse",
    "HttpTransport",
    "InstrumentedTransport",
    "MONETARY_SCOPE",
    "MetricReading",
    "OAuthClient",
    "OAuthConfig",
    "RetrievedEvidence",
    "StoredGrant",
    "TokenStore",
    "UrllibTransport",
    "VideoEvidence",
    "YouTubeClient",
    "YouTubeConnectorError",
    "YouTubeEvidencePointer",
    "YouTubeEvidenceStore",
    "build_deliverable",
    "commit_analytics",
    "configuration_status",
]
