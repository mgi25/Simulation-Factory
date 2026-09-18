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

import json
import os
from pathlib import Path
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


def sanitize_json_file(path: Path, redactor: "Redactor") -> bool:
    """Rewrite a file a session wrote so it holds no credential. Reports whether it did.

    **Why this exists.** Every other thing a session produces reaches disk
    through `CommandRunner.run`, which scrubs on the way in. The report does
    not: the session writes it to a path the runner names, and the runner then
    builds the receipt, the attestation and the committed evidence out of it.
    That made it the one persisted developer channel where a credential quoted
    back in a summary would travel all the way into a Company OS record. It is
    scrubbed here, at the boundary, rather than at each of the places that read
    it - there is no arrangement of later code that can reintroduce the leak.

    **It uses the same `Redactor` as everything else**, deliberately. A second
    pattern set would drift from the first, and the first is the one the
    transcripts are checked against.

    The scrub runs over the file's text, so it also covers a file that does not
    parse. Every replacement substitutes a run of non-structural characters for
    a shorter one, so JSON that was valid stays valid; if a pathological input
    ever proved otherwise, the parsed-and-scrubbed form is written instead, and
    an unparseable file is left scrubbed as text for the caller to fail on.
    """
    try:
        original = path.read_text(encoding="utf-8")
    except OSError:
        return False
    scrubbed = redactor.scrub(original)
    if scrubbed != original:
        try:
            json.loads(original)
        except ValueError:
            pass
        else:
            try:
                json.loads(scrubbed)
            except ValueError:
                scrubbed = json.dumps(
                    _scrub_tree(json.loads(original), redactor), indent=2, sort_keys=True
                )
    if scrubbed == original:
        return False
    path.write_text(scrubbed, encoding="utf-8")
    return True


def _scrub_tree(value: object, redactor: "Redactor") -> object:
    """Every string in a decoded document, scrubbed, structure untouched."""
    if isinstance(value, str):
        return redactor.scrub(value)
    if isinstance(value, Mapping):
        return {str(key): _scrub_tree(item, redactor) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_tree(item, redactor) for item in value]
    return value


# --- what a child process is given -----------------------------------------
#
# An allowlist, because the alternative was measured and it failed. Forwarding
# `os.environ` and subtracting a few names handed every coding session this
# machine's BINANCE_API_SECRET and CLAUDE_CODE_MESSAGING_TOKEN, neither of
# which the session has any business holding: a denylist has to predict the
# names, and the operator adds new ones faster than the runner can learn them.
#
# Three groups, and a variable is forwarded only if it is in one of them.

# 1. The base safe environment: what a process needs to be a process. Paths,
#    the interpreter's own configuration, locale, and the machine's identity.
#    Nothing here carries an authorisation to do anything.
_BASE_ENVIRONMENT: frozenset[str] = frozenset(
    {
        # process and filesystem
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "DRIVERDATA",
        "TEMP",
        "TMP",
        "TMPDIR",
        # where a user's own configuration lives, which is where every backend
        # keeps the credentials it manages itself
        "HOME",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMDATA",
        "ALLUSERSPROFILE",
        "PUBLIC",
        # where installed software lives
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMW6432",
        "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)",
        "COMMONPROGRAMW6432",
        # machine identity and shape
        "OS",
        "USERNAME",
        "USERDOMAIN",
        "COMPUTERNAME",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        "PROCESSOR_IDENTIFIER",
        "PROCESSOR_LEVEL",
        "PROCESSOR_REVISION",
        # locale and terminal
        "LANG",
        "LANGUAGE",
        "LC_ALL",
        "LC_CTYPE",
        "TERM",
        "TZ",
        # the Python the runner and its tests run under
        "PYTHONPATH",
        "PYTHONHOME",
        "PYTHONUTF8",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONWARNINGS",
        "PYTHONHASHSEED",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
        # the Node a coding CLI runs under
        "NODE_PATH",
        "NODE_OPTIONS",
        "NVM_DIR",
        "NVM_BIN",
        "NPM_CONFIG_PREFIX",
        # git, which the runner drives for every stage
        "GIT_EXEC_PATH",
        "GIT_SSH",
        "GIT_SSH_COMMAND",
        "SSH_AUTH_SOCK",
        "SSH_AGENT_PID",
        # reaching the network at all, on a machine that goes through a proxy
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "ALL_PROXY",
    }
)

# 2. The backend's own variables, named one at a time. A prefix rule was the
#    obvious shortcut and it is wrong: CLAUDE_CODE_MESSAGING_TOKEN shares a
#    prefix with every Claude Code setting and is exactly the credential the
#    review found being handed out.
_BACKEND_ENVIRONMENT: frozenset[str] = frozenset(
    {
        # Anthropic, for the `claude` backend
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_CUSTOM_HEADERS",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_SMALL_FAST_MODEL",
        "ANTHROPIC_DEFAULT_OPUS_MODEL",
        "ANTHROPIC_DEFAULT_SONNET_MODEL",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL",
        "CLAUDE_CODE_OAUTH_TOKEN",
        "CLAUDE_CONFIG_DIR",
        "CLAUDE_CODE_USE_BEDROCK",
        "CLAUDE_CODE_USE_VERTEX",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
        "MAX_THINKING_TOKENS",
        # OpenAI, for the `codex` backend
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "CODEX_HOME",
    }
)

# 3. Variables required only by a backend routed through a cloud provider, and
#    forwarded only when the switch that routes it there is actually set. An
#    AWS or GCP credential is a real credential; it travels when Claude Code is
#    configured to need it, not because it happened to be in the shell.
_BEDROCK_ENVIRONMENT: frozenset[str] = frozenset(
    {
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_PROFILE",
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_CONTAINER_CREDENTIALS_FULL_URI",
        "AWS_CONTAINER_AUTHORIZATION_TOKEN",
    }
)
_VERTEX_ENVIRONMENT: frozenset[str] = frozenset(
    {
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "CLOUD_ML_REGION",
    }
)

# Never forwarded, whatever else says so. These mark "you are already inside a
# Claude Code session", and a child that sees them refuses to start because
# nested sessions share runtime resources. Dropping them is what makes the
# child an independent session rather than a nested one, which is exactly the
# property the review stage needs. They are named rather than merely left off
# the allowlist, so that adding one of them later is a visible contradiction.
_NESTED_SESSION_MARKERS: frozenset[str] = frozenset(
    {
        "CLAUDECODE",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDE_CODE_SSE_PORT",
    }
)


def _truthy(source: Mapping[str, str], name: str) -> bool:
    for key, value in source.items():
        if key.upper() == name:
            return str(value).strip().lower() not in ("", "0", "false", "no")
    return False


def forwarded_names(environment: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Which of `environment`'s names a child would be given, sorted.

    Names, never values. This exists so that a test and a run record can both
    say what crossed the boundary without either of them handling what crossed
    it.
    """
    source = os.environ if environment is None else environment
    allowed = set(_BASE_ENVIRONMENT | _BACKEND_ENVIRONMENT)
    if _truthy(source, "CLAUDE_CODE_USE_BEDROCK"):
        allowed |= _BEDROCK_ENVIRONMENT
    if _truthy(source, "CLAUDE_CODE_USE_VERTEX"):
        allowed |= _VERTEX_ENVIRONMENT
    return tuple(
        sorted(
            name
            for name in source
            if name.upper() in allowed and name.upper() not in _NESTED_SESSION_MARKERS
        )
    )


def child_environment(environment: Mapping[str, str] | None = None) -> dict[str, str]:
    """The environment every process this runner starts gets.

    An allowlist of three classes - a base safe environment, the backend's own
    variables named one at a time, and a cloud provider's credentials only when
    the switch routing the backend through it is set - plus one value the
    runner sets itself.

    **Why an allowlist.** The runner's whole claim is that a coding session's
    authority is bounded, and an inherited environment *is* authority: it is
    where a process finds the keys to every service the operator uses, and none
    of them is in the work order. Forwarding `os.environ` minus three names
    handed each session credentials for services this repository has never
    heard of. The list here is the smallest one under which the runner, git,
    pytest, the Company OS CLI and a `claude` or `codex` session all still
    work; a backend that needs a name it does not have fails at its own
    `available()` probe, before a work order is claimed, which is the right way
    to find out.

    **What is deliberately not forwarded**, and is not missed: anything
    credential-shaped that is not a named backend variable, every editor and
    IDE integration variable, every session-marking variable, and everything
    else. Absence is the default, and a new credential in the operator's shell
    is not a change to this boundary.

    **`PYTHONIOENCODING` is set to UTF-8.** Output is captured as UTF-8, and on
    Windows a Python child writes its stdout in the console codepage unless
    told otherwise - so the CEO page came back with a replacement character
    wherever it had an em dash. The page is evidence; a page that cannot be
    read back exactly is worse evidence.
    """
    source = dict(os.environ if environment is None else environment)
    kept = {name: source[name] for name in forwarded_names(source)}
    kept["PYTHONIOENCODING"] = "utf-8"
    return kept


__all__ = [
    "REDACTED",
    "Redactor",
    "child_environment",
    "forwarded_names",
    "sanitize_json_file",
    "secret_values",
]
