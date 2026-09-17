"""Secret redaction and local refresh-token protection.

Access tokens are memory-only.  Refresh tokens are protected with Windows
DPAPI on Windows and a mode-0600 file in the user's config directory elsewhere.
No token value is included in an exception or telemetry record.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os
import re
from typing import Protocol


_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)(access_token|refresh_token|client_secret|authorization|code)"
    r"(\s*[:=]\s*)([^\s,&}\]]+)"
)
_BEARER = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._~+\-/=]+")


class SecretRedactor:
    def __init__(self, *values: str | None) -> None:
        self._values = tuple(
            sorted(
                {value for value in values if isinstance(value, str) and value},
                key=len,
                reverse=True,
            )
        )

    def redact(self, value: object) -> str:
        text = str(value)
        for secret in self._values:
            text = text.replace(secret, "[REDACTED]")
        text = _BEARER.sub("Bearer [REDACTED]", text)
        return _SENSITIVE_ASSIGNMENT.sub(r"\1\2[REDACTED]", text)


class TokenProtector(Protocol):
    name: str

    def protect(self, value: bytes) -> bytes: ...

    def unprotect(self, value: bytes) -> bytes: ...


class FilePermissionProtector:
    """Protection supplied by a user-only directory and a mode-0600 file."""

    name = "file_permissions"

    def protect(self, value: bytes) -> bytes:
        return value

    def unprotect(self, value: bytes) -> bytes:
        return value


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


class WindowsDpapiProtector:
    """Encrypt token bytes for the current Windows user via DPAPI."""

    name = "windows_dpapi"
    _flags = 0x01  # CRYPTPROTECT_UI_FORBIDDEN

    @staticmethod
    def _blob(value: bytes) -> tuple[_DataBlob, ctypes.Array[ctypes.c_char]]:
        buffer = ctypes.create_string_buffer(value)
        return _DataBlob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer

    def protect(self, value: bytes) -> bytes:
        incoming, keepalive = self._blob(value)
        outgoing = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        ok = crypt32.CryptProtectData(
            ctypes.byref(incoming),
            "Company OS YouTube refresh token",
            None,
            None,
            None,
            self._flags,
            ctypes.byref(outgoing),
        )
        del keepalive
        if not ok:
            raise OSError("Windows could not protect the refresh token")
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(outgoing.pbData)

    def unprotect(self, value: bytes) -> bytes:
        incoming, keepalive = self._blob(value)
        outgoing = _DataBlob()
        crypt32 = ctypes.windll.crypt32
        ok = crypt32.CryptUnprotectData(
            ctypes.byref(incoming), None, None, None, None, self._flags, ctypes.byref(outgoing)
        )
        del keepalive
        if not ok:
            raise OSError("Windows could not unlock the refresh token")
        try:
            return ctypes.string_at(outgoing.pbData, outgoing.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(outgoing.pbData)


def default_protector() -> TokenProtector:
    return WindowsDpapiProtector() if os.name == "nt" else FilePermissionProtector()


def encode_protected(protector: TokenProtector, value: str) -> str:
    return base64.b64encode(protector.protect(value.encode("utf-8"))).decode("ascii")


def decode_protected(protector: TokenProtector, value: str) -> str:
    return protector.unprotect(base64.b64decode(value.encode("ascii"))).decode("utf-8")


__all__ = [
    "FilePermissionProtector",
    "SecretRedactor",
    "TokenProtector",
    "WindowsDpapiProtector",
    "decode_protected",
    "default_protector",
    "encode_protected",
]
