"""The failure vocabulary, chosen so that a caller can act on the answer.

## A string is not a failure mode

The rejected first version of this connector raised one `ApiError` for every
provider refusal, with the provider's sentence pasted into the message. That
reads fine in a terminal and is useless everywhere else: a quota refusal means
"come back tomorrow", a missing-permission refusal means "the grant is wrong,
re-authorize", and a revoked grant means "the stored refresh token is dead".
Those are three different operator actions and one exception type cannot tell
them apart, so the caller ends up matching on message text - which changes
whenever Google edits a sentence.

So each provider condition this fetcher can actually meet has a type, and the
mapping from HTTP status plus `error.errors[].reason` to that type happens once,
in `api.py`, before the failure leaves the module. `QuotaExceeded` and
`InsufficientPermissions` both descend from `ApiError`, and
`AuthorizationRevoked` and `MissingScopeError` both descend from
`AuthorizationError`, so a caller that only wants the coarse distinction still
gets it from one `except`.

## Every message here has already passed through redaction

These exceptions are raised in the presence of a client secret, a refresh token,
an access token, an authorization code and a PKCE verifier. Any of them can end
up in a provider error body, a traceback, a log line or a CI transcript, and a
leaked refresh token is a silent, long-lived compromise. The rule this module
depends on is that the *raiser* redacts, never the catcher: by the time a
`YouTubeFetchError` exists, `SecretRedactor` has already been over its text. A
handler can therefore print `str(exc)` without having to know what was in scope
where it was raised.

`TokenProtectionError` exists for the same reason. Windows DPAPI reports failure
as a bare `OSError` carrying OS-supplied text; letting that escape would put an
untyped, unredacted string on the operator's screen at exactly the moment they
are handling a refresh token.
"""

from __future__ import annotations


class YouTubeFetchError(Exception):
    """Base error whose message is safe to display: it is redacted at the raise."""


class ConfigurationError(YouTubeFetchError):
    """The OAuth client configuration is absent, incomplete or not usable."""


class AuthorizationError(YouTubeFetchError):
    """The authorization flow, or the use of a stored grant, failed."""


class AuthorizationRevoked(AuthorizationError):
    """Google rejected the stored refresh grant; the operator must authorize again."""


class MissingScopeError(AuthorizationError):
    """Consent came back without a scope this fetcher requires, so nothing was stored."""


class TokenProtectionError(AuthorizationError):
    """The OS could not protect or unlock the refresh token, reported without OS text."""


class ApiError(YouTubeFetchError):
    """A read-only YouTube API request failed."""


class QuotaExceeded(ApiError):
    """The project's daily quota is spent; the same request will succeed later."""


class InsufficientPermissions(ApiError):
    """The grant does not cover this request; re-authorizing is the only fix."""


__all__ = [
    "ApiError",
    "AuthorizationError",
    "AuthorizationRevoked",
    "ConfigurationError",
    "InsufficientPermissions",
    "MissingScopeError",
    "QuotaExceeded",
    "TokenProtectionError",
    "YouTubeFetchError",
]
