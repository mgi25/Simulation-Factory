"""Launching a coding session, without letting the vendor shape the runner.

`EngineeringRunner` knows there is such a thing as a session that is given a
`SessionRequest` and returns a `SessionOutcome`. It does not know what a
`--permission-mode` is, which CLI takes `-p` and which takes `exec`, or that
one of them writes JSON to stdout and another writes a log. That is the whole
reason this module exists.

    EngineeringRunner
        |
        v
    CodingBackend        (protocol: name, available(), launch(request))
        |-- ClaudeCodeBackend
        '-- CodexBackend

## What a backend is not allowed to be

A backend does not compose the work. It receives the instructions the runner
built from the Company OS packet and passes them through. There is no
vendor-specific prompt here, no "you are a senior engineer" preamble, no
retry-with-a-nudge: a backend that improved the brief would be a second place
where the work order is interpreted, and there is exactly one.

## Session identity, and why it is not a formality

Review has to be a different session from development. `SessionOutcome.session_id`
is what makes that checkable rather than assumed, and the two Claude sessions
get distinct pre-assigned UUIDs, `--no-session-persistence`, and no resume
flag - so neither can reach the other's conversation even by accident. The
runner asserts the two ids differ before it will submit an attestation.

## The nested-session problem, and where it is solved

A runner started from inside a Claude Code session inherits `CLAUDECODE`, and
the child refuses to start. `redaction.child_environment` drops it, which is
what makes the child an independent process rather than a nested one. It is in
the redaction module because that module already owns "what environment does a
child get", and having two answers to that question is how a credential ends
up somewhere nobody looked.

## On CodexBackend

The adapter is here because one backend proves nothing about whether the
protocol is vendor-neutral, and because writing the second one is what
discovers the assumptions the first one baked in. It is **not** claimed to
work: on the machine this milestone was built on, `codex exec` reached the
provider and was refused for every model offered - the installed CLI is older
than the only model the account has. `available()` therefore probes rather
than asserts, and `EngineeringRunner` refuses a backend that reports
unavailable rather than discovering it half-way through a work order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence
import uuid

from .errors import BackendFailure, BackendUnavailable
from .process import CommandResult, CommandRunner, resolve_executable
from .redaction import Redactor, child_environment


CLAUDE_CODE = "claude_code"
CODEX = "codex"

# `ExecutorHint` in company/runtime/packets.py, by value. The runner passes one
# of these to `--executor` so the execution history can answer "what ran this?".
EXECUTOR_HINTS: Mapping[str, str] = {
    CLAUDE_CODE: "claude_code",
    CODEX: "codex",
}

_SESSION_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@dataclass(frozen=True)
class SessionRequest:
    """One session to launch: where, with what instructions, and how bounded."""

    role: str
    cwd: Path
    instructions: str
    timeout_s: float
    allowed_tools: tuple[str, ...] = ()
    disallowed_tools: tuple[str, ...] = ()
    model: str = ""
    read_only: bool = False
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    # Directories outside `cwd` the session may read and write. Exactly one use:
    # the run directory, so a report or a diff can be exchanged without putting
    # an untracked file inside the task worktree - which would show up in
    # `git status` and be swept into the commit the authority check reads.
    extra_dirs: tuple[Path, ...] = ()


@dataclass(frozen=True)
class SessionOutcome:
    """What a launched session cost, said, and was."""

    backend: str
    role: str
    session_id: str
    model: str
    exit_code: int
    duration_s: float
    result_text: str
    transcript: str
    ok: bool
    cost_usd: float | None = None
    input_units: int | None = None
    output_units: int | None = None
    cache_read_units: int | None = None
    turns: int | None = None
    permission_denials: tuple[str, ...] = ()
    provider: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "role": self.role,
            "session_id": self.session_id,
            "model": self.model,
            "provider": self.provider,
            "exit_code": self.exit_code,
            "duration_s": round(self.duration_s, 3),
            "ok": self.ok,
            "cost_usd": self.cost_usd,
            "input_units": self.input_units,
            "output_units": self.output_units,
            "cache_read_units": self.cache_read_units,
            "turns": self.turns,
            "permission_denials": list(self.permission_denials),
            "result_chars": len(self.result_text),
        }


class CodingBackend(Protocol):
    """Anything that can be handed a `SessionRequest` and return an outcome."""

    name: str

    def available(self) -> tuple[bool, str]: ...

    def launch(self, request: SessionRequest) -> SessionOutcome: ...


class ClaudeCodeBackend:
    """Claude Code in headless print mode, one process per session."""

    name = CLAUDE_CODE

    def __init__(
        self,
        runner: CommandRunner,
        *,
        executable: str = "claude",
        redactor: Redactor | None = None,
    ) -> None:
        self._runner = runner
        self._executable_name = executable
        self._redactor = redactor or Redactor()
        self._resolved = ""

    def executable(self) -> str:
        if not self._resolved:
            self._resolved = resolve_executable(self._executable_name)
        return self._resolved

    def available(self) -> tuple[bool, str]:
        try:
            path = self.executable()
        except Exception as exc:  # noqa: BLE001 - reported, never raised from a probe
            return False, str(exc)
        result = self._runner.run(
            [path, "--version"],
            cwd=Path.cwd(),
            timeout_s=120.0,
            env=child_environment(),
        )
        if not result.ok:
            return False, f"{path} --version exited {result.exit_code}"
        return True, result.stdout.strip()

    def launch(self, request: SessionRequest) -> SessionOutcome:
        argv = [
            self.executable(),
            "--print",
            "--output-format",
            "json",
            "--session-id",
            request.session_id,
            "--no-session-persistence",
        ]
        if request.model:
            argv += ["--model", request.model]
        for directory in request.extra_dirs:
            argv += ["--add-dir", str(directory)]
        if request.allowed_tools:
            argv += ["--allowedTools", " ".join(request.allowed_tools)]
        if request.disallowed_tools:
            argv += ["--disallowedTools", " ".join(request.disallowed_tools)]
        # A reviewer gets no writing tool at all, so `default` is right: there
        # is nothing to accept. A developer gets `acceptEdits`, because in
        # print mode an unanswered permission prompt is a denial and the run
        # would stall instead of failing.
        argv += ["--permission-mode", "default" if request.read_only else "acceptEdits"]

        result = self._runner.run(
            argv,
            cwd=request.cwd,
            timeout_s=request.timeout_s,
            env=child_environment(),
            stdin=request.instructions,
        )
        return self._read(request, result)

    def _read(self, request: SessionRequest, result: CommandResult) -> SessionOutcome:
        payload: dict[str, Any] = {}
        text = result.stdout.strip()
        if text.startswith("{"):
            try:
                loaded = json.loads(text)
                payload = loaded if isinstance(loaded, Mapping) else {}
            except json.JSONDecodeError:
                payload = {}
        usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
        model_usage = (
            payload.get("modelUsage")
            if isinstance(payload.get("modelUsage"), Mapping)
            else {}
        )
        session_id = str(payload.get("session_id", "")) or request.session_id
        if not _SESSION_ID.fullmatch(session_id):
            raise BackendFailure(
                f"the {self.name} session returned no usable session id; the run "
                "cannot be attributed and is not recorded as an attempt"
            )
        return SessionOutcome(
            backend=self.name,
            role=request.role,
            session_id=session_id,
            model=request.model or (sorted(model_usage)[0] if model_usage else ""),
            provider="anthropic",
            exit_code=result.exit_code,
            duration_s=result.duration_s,
            result_text=self._redactor.scrub(payload.get("result", "")),
            transcript=result.stdout,
            ok=result.ok and not bool(payload.get("is_error")),
            cost_usd=_number(payload.get("total_cost_usd")),
            input_units=_integer(usage.get("input_tokens")),
            output_units=_integer(usage.get("output_tokens")),
            cache_read_units=_integer(usage.get("cache_read_input_tokens")),
            turns=_integer(payload.get("num_turns")),
            permission_denials=_denials(payload.get("permission_denials")),
        )


class CodexBackend:
    """Codex in `exec` mode. Implemented, probed, and not claimed to work.

    Kept deliberately thin for the same reason `ClaudeCodeBackend` is: the
    instructions arrive on stdin and nothing here adds to them. What differs is
    only the shape of the command line and the fact that Codex enforces
    read-only at the sandbox rather than through a tool list, which is a
    stronger guarantee than the Claude backend can give and is the reason the
    second adapter is worth having at all.
    """

    name = CODEX

    def __init__(
        self,
        runner: CommandRunner,
        *,
        executable: str = "codex",
        redactor: Redactor | None = None,
    ) -> None:
        self._runner = runner
        self._executable_name = executable
        self._redactor = redactor or Redactor()
        self._resolved = ""

    def executable(self) -> str:
        if not self._resolved:
            self._resolved = resolve_executable(self._executable_name)
        return self._resolved

    def available(self) -> tuple[bool, str]:
        """Probe with a one-line prompt, because `--version` proves nothing.

        A Codex CLI that is installed, authenticated and simply older than the
        only model the account may use answers `--version` perfectly and fails
        every request. The probe therefore asks for one token of real output.
        """
        try:
            path = self.executable()
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)
        result = self._runner.run(
            [path, "exec", "--sandbox", "read-only", "--skip-git-repo-check", "-"],
            cwd=Path.cwd(),
            timeout_s=180.0,
            env=child_environment(),
            stdin="Reply with exactly: READY",
        )
        if not result.ok or "READY" not in result.stdout:
            detail = _codex_refusal(result) or f"exit {result.exit_code}"
            return False, detail
        return True, "codex exec answered a probe"

    def launch(self, request: SessionRequest) -> SessionOutcome:
        argv = [
            self.executable(),
            "exec",
            "--sandbox",
            "read-only" if request.read_only else "workspace-write",
            "--cd",
            str(request.cwd),
            "-",
        ]
        if request.model:
            argv[2:2] = ["--model", request.model]
        result = self._runner.run(
            argv,
            cwd=request.cwd,
            timeout_s=request.timeout_s,
            env=child_environment(),
            stdin=request.instructions,
        )
        if not result.ok:
            raise BackendFailure(
                f"codex exec exited {result.exit_code}: "
                f"{_codex_refusal(result) or result.stderr.strip()[:400]}"
            )
        return SessionOutcome(
            backend=self.name,
            role=request.role,
            session_id=request.session_id,
            model=request.model,
            provider="openai",
            exit_code=result.exit_code,
            duration_s=result.duration_s,
            result_text=self._redactor.scrub(result.stdout[-8000:]),
            transcript=result.stdout,
            ok=True,
        )


def build_backend(
    name: str, runner: CommandRunner, *, redactor: Redactor | None = None
) -> CodingBackend:
    if name == CLAUDE_CODE:
        return ClaudeCodeBackend(runner, redactor=redactor)
    if name == CODEX:
        return CodexBackend(runner, redactor=redactor)
    raise BackendUnavailable(
        f"{name!r} is not a coding backend this runner implements; available: "
        + ", ".join(sorted((CLAUDE_CODE, CODEX)))
    )


def executor_hint(backend_name: str) -> str:
    return EXECUTOR_HINTS.get(backend_name, "future_adapter")


def _number(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _denials(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    rendered: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            rendered.append(str(item.get("tool_name") or item.get("tool") or item))
        else:
            rendered.append(str(item))
    return tuple(rendered[:32])


def _codex_refusal(result: CommandResult) -> str:
    for line in reversed(result.stdout.splitlines()):
        if "detail" in line or "ERROR:" in line:
            return line.strip()[:400]
    return ""


__all__ = [
    "CLAUDE_CODE",
    "CODEX",
    "ClaudeCodeBackend",
    "CodexBackend",
    "CodingBackend",
    "SessionOutcome",
    "SessionRequest",
    "build_backend",
    "executor_hint",
]
