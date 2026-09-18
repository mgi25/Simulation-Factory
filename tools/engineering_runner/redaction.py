"""Removing credentials from text before it is written down.

The runner persists three kinds of text it did not write: a coding session's
stdout, a subprocess's stderr, and a git remote URL. All three can quote a
credential back - an `https://user:token@github.com/...` remote, an API key a
session printed while debugging, a token in an error body - and all three are
written to disk under the runner directory.

## Why this is not `tools/youtube_fetch/secrets_.SecretRedactor`

That redactor exists to protect *one* long-lived credential the fetcher holds
on purpose, and importing it here would make the engineering runner depend on
the whole YouTube package's import graph - `urllib`, an OAuth client and a
DPAPI binding - to reuse forty lines. The jobs are also different: this one
never holds a secret, it only removes ones that arrive in text from elsewhere,
so it works from patterns and from the environment rather than from values a
caller supplies.

## What is redacted

1. Values of environment variables whose *name* looks like a credential. The
   name is the reliable signal: `ANTHROPIC_API_KEY` is a secret whatever its
   value looks like, and a value-only scan cannot know that.
2. Credentials embedded in a URL's userinfo, which is how a git remote leaks.
3. `key = value` assignments whose key looks like a credential.
4. Bearer tokens, and the well-known vendor key prefixes.

Short values are left alone. A two-character environment variable called `KEY`
would otherwise turn every occurrence of those two characters into a redaction
marker, which destroys the transcript to protect nothing.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Mapping


REDACTED = "[redacted]"

# Below this length a "secret" is more likely to be a word that appears in
# ordinary text than a credential.
_MINIMUM_SECRET_LENGTH = 8

# Environment variable names that hold a credential. Matched case-insensitively
# as a whole-name substring, so ANTHROPIC_API_KEY, GH_TOKEN and
# AWS_SECRET_ACCESS_KEY are all caught by three entries.
_SECRET_NAME_PARTS: tuple[str, ...] = (
    "api_key",
    "apikey",
    "auth",
    "credential",
    "key",
    "passwd",
    "password",
    "secret",
    "session_key",
    "token",
)

# Names that contain one of the parts above and are not secrets. Without this,
# PATH-like variables whose name merely contains "key" are redacted out of
# every transcript.
_SECRET_NAME_EXCEPTIONS: frozenset[str] = frozenset(
    {
        "KEYBOARD",
        "KEYMAP",
        "MONKEYPATCH",
        "PYTHONHASHSEED",
    }
)

_URL_USERINFO = re.compile(r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*://)[^/\s@]+@")
_ASSIGNMENT = re.compile(
    r"(?i)\b([a-z0-9_.-]*(?:api[_-]?key|token|secret|password|passwd|credential)"
    r"[a-z0-9_.-]*)(\s*[=:]\s*\"?)([^\s\"',;]{6,})"
)
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{10,}")
_VENDOR_KEY = re.compile(
    r"\b(?:sk-ant-[A-Za-z0-9_-]{10,}|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|ya29\.[A-Za-z0-9_-]{10,}|AIza[A-Za-z0-9_-]{20,})"
)


def _looks_secret(name: str) -> bool:
    upper = name.upper()
    if upper in _SECRET_NAME_EXCEPTIONS:
        return False
    lower = name.casefold()
    return any(part in lower for part in _SECRET_NAME_PARTS)


def secret_values(environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Every environment value worth removing, longest first.

    Longest first matters: a short secret that is a substring of a long one
    would otherwise be replaced inside it, leaving a fragment of the long one
    in the text.
    """
    source = os.environ if environment is None else environment
    values = {
        value
        for name, value in source.items()
        if _looks_secret(name)
        and isinstance(value, str)
        and len(value.strip()) >= _MINIMUM_SECRET_LENGTH
    }
    return tuple(sorted((value.strip() for value in values), key=len, reverse=True))


class Redactor:
    """Removes known values, then anything shaped like a credential."""

    def __init__(self, *values: str, environment: Mapping[str, str] | None = None) -> None:
        known = {
            value.strip()
            for value in values
            if isinstance(value, str) and len(value.strip()) >= _MINIMUM_SECRET_LENGTH
        }
        known.update(secret_values(environment))
        self._values: tuple[str, ...] = tuple(sorted(known, key=len, reverse=True))

    @property
    def values(self) -> tuple[str, ...]:
        return self._values

    def with_values(self, *values: str) -> "Redactor":
        return Redactor(*self._values, *values, environment={})

    def __call__(self, value: object) -> str:
        return self.scrub(value)

    def scrub(self, value: object) -> str:
        text = str(value)
        for secret in self._values:
            if secret:
                text = text.replace(secret, REDACTED)
        text = _URL_USERINFO.sub(lambda m: f"{m.group('scheme')}{REDACTED}@", text)
        text = _VENDOR_KEY.sub(REDACTED, text)
        text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
        return _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)

    def scrub_all(self, values: Iterable[object]) -> tuple[str, ...]:
        return tuple(self.scrub(item) for item in values)


def child_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment every process this runner starts gets.

    Two changes to the inherited one, and both are about the child rather than
    about secrets - they live here because this module already owns the one
    question "what environment does a child get", and two answers to that
    question is how something ends up somewhere nobody looked.

    **`CLAUDECODE` and its companions are dropped.** They mark "you are already
    inside a Claude Code session". A runner started from an ordinary shell does
    not have them; a runner started from inside one does, and the child then
    refuses to launch because nested sessions share runtime resources. Dropping
    them is what makes the child an independent session rather than a nested
    one, which is exactly the property the review stage needs.

    **`PYTHONIOENCODING` is set to UTF-8.** Output is captured as UTF-8, and on
    Windows a Python child writes its stdout in the console codepage unless
    told otherwise - so the CEO page came back with a replacement character
    wherever it had an em dash. The page is evidence; a page that cannot be
    read back exactly is worse evidence.
    """
    source = dict(os.environ if environment is None else environment)
    for name in ("CLAUDECODE", "CLAUDE_CODE_SSE_PORT", "CLAUDE_CODE_ENTRYPOINT"):
        source.pop(name, None)
    source["PYTHONIOENCODING"] = "utf-8"
    return source


__all__ = [
    "REDACTED",
    "Redactor",
    "child_environment",
    "secret_values",
]
