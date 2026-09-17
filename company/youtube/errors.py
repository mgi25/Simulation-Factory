"""Safe exception vocabulary for the YouTube connector."""

from __future__ import annotations


class YouTubeConnectorError(Exception):
    """Base error whose message is safe to show after redaction."""


class ConfigurationError(YouTubeConnectorError):
    """OAuth configuration is absent or invalid."""


class AuthorizationError(YouTubeConnectorError):
    """The one-time OAuth authorization flow failed."""


class AuthorizationRevoked(AuthorizationError):
    """Google rejected the stored refresh grant."""


class ApiError(YouTubeConnectorError):
    """A read-only YouTube API request failed."""


class EvidenceError(YouTubeConnectorError):
    """A provider response could not become trustworthy evidence."""


__all__ = [
    "ApiError",
    "AuthorizationError",
    "AuthorizationRevoked",
    "ConfigurationError",
    "EvidenceError",
    "YouTubeConnectorError",
]
