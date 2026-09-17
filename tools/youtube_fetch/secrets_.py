"""Keeping the secret out of the sentence, and the refresh token off the disk.

## Two different jobs that are usually confused

Protecting a credential at rest and keeping it out of text are separate
problems, and this module does both because they fail together. A refresh token
encrypted with DPAPI and then printed in an exception message is not protected;
a redacted log line next to a world-readable token file is not protected either.
`TokenProtector` is the at-rest half, `SecretRedactor` is the in-text half, and
every module in this package holds both.

## Redaction is done by the raiser, with the values it can actually see

`SecretRedactor` is constructed with the exact secret values in scope at the
point of failure - the client secret always, plus the refresh token and access
token wherever they are held, plus the authorization code and PKCE verifier
during the exchange. Exact-value replacement is the only reliable part of this;
a provider is free to echo a credential back in any shape it likes.

The two patterns are a second line of defence, not the first. The assignment
pattern catches `refresh_token=ya29...` in a form-encoded body a provider quoted
back at us, and the bearer pattern catches an `Authorization` header that
reached a message some other way. They exist because the exact-value pass cannot cover a
credential this process never held - a rotated refresh token inside an error
body, say - and a partial defence at that point is much better than none.

The redactor sorts its values by length and replaces longest first, so a secret
that contains another secret as a prefix cannot leave the tail of the longer one
behind. It also ignores anything shorter than four characters: a two-character
"secret" would redact ordinary prose and make every message unreadable.

## Why the file is named `secrets_`

`secrets` is a standard-library module this package uses, for `token_urlsafe`
and `compare_digest`. A sibling module named `secrets.py` is fine under absolute
imports and a trap under anything doing a path-relative import - the sort of
failure that surfaces once, in production, as a `ModuleNotFoundError` in the
middle of an authorization flow. The trailing underscore costs nothing and
removes the shadow entirely.

## DPAPI is imported inside the function, not at the top of the file

`from ctypes import wintypes` at module scope raises `ImportError` on Linux and
macOS, which means the whole package - including the parts with nothing to do
with credentials - cannot be imported there and the test suite cannot even be
collected. That was a real defect in the version this one replaces. The Windows
handles are therefore resolved lazily, inside `_windows_crypto()`, the first
time somebody actually protects a value on Windows; `default_protector()`
chooses by `os.name` and nothing else in the package touches ctypes at all.

`WindowsDpapiProtector` also refuses to let an `OSError` escape. Windows reports
a DPAPI failure with OS-supplied text, and that text arrives at exactly the
moment we are holding a refresh token, so it becomes a typed, redacted
`TokenProtectionError` that names the operation and nothing else.
"""

from __future__ import annotations

import base64
import os
import re
from typing import Any, Protocol

from .errors import TokenProtectionError


_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(access_token|refresh_token|client_secret|authorization|code_verifier|code)"
    r"(\s*[:=]\s*)([^\s,&}\]]+)"
)
_BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+\-/=]+")

# An opaque credential sitting in text nobody here composed - a provider's
# `error_description` quoting back what the client sent, say. It cannot be
# matched against a known value, because the whole problem is that this process
# never held it, so it is matched on shape: a long unbroken run of token
# characters carrying both letters and digits.
#
# All three conditions are load-bearing. The length floor keeps `invalid_client`
# and `redirect_uri_mismatch` whole. Requiring a digit keeps every English word
# and every OAuth error code whole, because none of them contain one. Excluding
# `.` and `/` from the run means a scope URL is seen as its short segments -
# `googleapis`, `auth`, `readonly` - rather than as one long secret, while the
# opaque half of a real `ya29.a0AfH6...` access token is still caught.
_OPAQUE_TOKEN = re.compile(
    r"(?=[A-Za-z0-9_-]*[A-Za-z])(?=[A-Za-z0-9_-]*\d)[A-Za-z0-9_-]{16,}"
)

REDACTED = "[REDACTED]"

# Shorter than this and a "secret" is a word; redacting it would eat prose.
_MINIMUM_SECRET_LENGTH = 4


class SecretRedactor:
    """Replaces known secret values, then likely-looking ones, in any text."""

    def __init__(self, *values: str | None) -> None:
        self._values: tuple[str, ...] = tuple(
            sorted(
                {
                    value
                    for value in values
                    if isinstance(value, str) and len(value) >= _MINIMUM_SECRET_LENGTH
                },
                key=len,
                reverse=True,
            )
        )

    @property
    def values(self) -> tuple[str, ...]:
        """The exact values this redactor removes, longest first."""
        return self._values

    def with_values(self, *values: str | None) -> SecretRedactor:
        """A redactor that also knows these values, for a narrower scope."""
        return SecretRedactor(*self._values, *values)

    def redact(self, value: object) -> str:
        text = str(value)
        for secret in self._values:
            text = text.replace(secret, REDACTED)
        text = _BEARER.sub("Bearer " + REDACTED, text)
        return _SENSITIVE_ASSIGNMENT.sub(r"\1\2" + REDACTED, text)

    def scrub(self, value: object) -> str:
        """`redact`, plus anything merely shaped like a credential.

        For text this process did not compose and cannot vouch for: a provider's
        `error_description`, an HTTP error body. `redact` alone can only remove
        values we already hold, and the dangerous case is the one we do not - a
        rotated refresh token quoted back inside an error. Kept separate from
        `redact` because it is lossy: it will mask a long mixed-case identifier
        that happens not to be a secret, which is the right trade for untrusted
        text and the wrong one for a message we wrote ourselves.
        """
        return _OPAQUE_TOKEN.sub(REDACTED, self.redact(value))


class TokenProtector(Protocol):
    """At-rest protection for the one long-lived credential this fetcher keeps."""

    name: str

    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class FilePermissionProtector:
    """Protection supplied by a user-only directory and a mode-0600 file.

    This is not encryption and does not pretend to be. On a POSIX host the
    refresh token is readable by the account that owns it and by root, which is
    the same boundary already protecting the SSH key sitting next to it.
    Recording the protector's name in the stored file matters more than the
    protection itself: a token written under this scheme is then never silently
    handed to a different one.
    """

    name = "file_permissions"

    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


_WINDOWS_CRYPTO: dict[str, Any] = {}


def _windows_crypto() -> dict[str, Any]:
    """Resolve the DPAPI entry points, on Windows, on first use.

    Everything ctypes-shaped lives in here: the `wintypes` import, the blob
    structure whose fields need `wintypes.DWORD`, and the two DLL handles. The
    result is cached because building the structure type a second time would
    create two incompatible Python types for one C struct.
    """
    if os.name != "nt":
        raise TokenProtectionError(
            "Windows DPAPI token protection was requested on a non-Windows host"
        )
    if _WINDOWS_CRYPTO:
        return _WINDOWS_CRYPTO
    try:
        import ctypes
        from ctypes import wintypes

        class _DataBlob(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        _WINDOWS_CRYPTO.update(
            {
                "ctypes": ctypes,
                "blob": _DataBlob,
                "crypt32": ctypes.windll.crypt32,
                "kernel32": ctypes.windll.kernel32,
            }
        )
    except (ImportError, AttributeError, OSError) as exc:
        raise TokenProtectionError(
            "Windows token protection is unavailable on this host "
            f"({type(exc).__name__})"
        ) from None
    return _WINDOWS_CRYPTO


class WindowsDpapiProtector:
    """Encrypt token bytes for the current Windows user via DPAPI.

    The ciphertext is bound to the OS user, so a token file copied to another
    account or another machine decrypts for nobody - which is exactly the
    property wanted from a credential that never needs to travel.
    """

    name = "windows_dpapi"
    _flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN: never prompt, fail instead.

    def protect(self, value: bytes) -> bytes:
        api = _windows_crypto()
        return self._call(
            api,
            api["crypt32"].CryptProtectData,
            value,
            "Company OS YouTube refresh token",
            "protect the refresh token",
        )

    def unprotect(self, value: bytes) -> bytes:
        api = _windows_crypto()
        return self._call(
            api,
            api["crypt32"].CryptUnprotectData,
            value,
            None,
            "unlock the refresh token",
        )

    @staticmethod
    def _call(
        api: dict[str, Any],
        entry: Any,
        value: bytes,
        description: str | None,
        operation: str,
    ) -> bytes:
        ctypes = api["ctypes"]
        blob = api["blob"]
        buffer = ctypes.create_string_buffer(value, len(value))
        incoming = blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        outgoing = blob()
        try:
            ok = entry(
                ctypes.byref(incoming),
                description,
                None,
                None,
                None,
                WindowsDpapiProtector._flags,
                ctypes.byref(outgoing),
            )
        except OSError as exc:
            # The OS text can quote the payload back; only the type escapes.
            raise TokenProtectionError(
                f"Windows could not {operation} ({type(exc).__name__})"
            ) from None
        if not ok:
            raise TokenProtectionError(f"Windows could not {operation}")
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            api["kernel32"].LocalFree(outgoing.pbData)


def default_protector() -> TokenProtector:
    """DPAPI on Windows, file permissions everywhere else."""
    return WindowsDpapiProtector() if os.name == "nt" else FilePermissionProtector()


def encode_protected(protector: TokenProtector, value: str) -> str:
    """Protected bytes as base64 ASCII, because the token file is JSON."""
    return base64.b64encode(protector.protect(value.encode("utf-8"))).decode("ascii")


def decode_protected(protector: TokenProtector, value: str) -> str:
    """The inverse of `encode_protected`, with both failure modes typed."""
    try:
        raw = base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError):
        raise TokenProtectionError("the stored refresh grant is not valid base64") from None
    try:
        return protector.unprotect(raw).decode("utf-8")
    except UnicodeDecodeError:
        raise TokenProtectionError("the stored refresh grant did not decode as text") from None


__all__ = [
    "REDACTED",
    "FilePermissionProtector",
    "SecretRedactor",
    "TokenProtector",
    "WindowsDpapiProtector",
    "decode_protected",
    "default_protector",
    "encode_protected",
]
