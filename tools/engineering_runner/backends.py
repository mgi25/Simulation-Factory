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
than the only model the account has.

That refusal is also why `available()` is shaped the way it is. `codex exec`
writes its own prompt back to stdout and **exits 0 even when every request in
the session failed**, so the obvious probe - ask for a word, look for that word
- finds its own question and reports the backend working. It did, briefly, on a
machine where Codex could not complete a single call. The probe now asks for
something the prompt does not contain (a sum, not its answer) and checks the
provider's failure signatures explicitly, because an exit code that is always 0
says nothing. `launch` applies the same reading, and `EngineeringRunner` refuses
an unavailable backend before a stage rather than half-way through a work order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Mapping, Protocol, Sequence
import uuid

from .errors import BackendFailure, BackendUnavailable
from .exploration_telemetry import parse_exploration, parse_startup_context, split_result_envelope
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

# Codex writes its own prompt back to stdout under `User instructions:`, and it
# exits 0 even when every request in the session failed. So a probe that asks
# for a word and looks for that word in the output finds its own question and
# reports success - which is how this package briefly claimed a backend worked
# that could not complete a single call.
#
# The probe therefore asks for something the prompt does not contain: the sum
# is in the prompt, the answer is not. And the known failure signatures are
# checked explicitly, because an exit code that is always 0 says nothing.
CODEX_PROBE_PROMPT = (
    "Add 19 and 23. Reply with the word OK immediately followed by the result, "
    "as one token, and nothing else."
)
CODEX_PROBE_EXPECTED = "OK42"
_CODEX_FAILURE_MARKERS = ("stream error", "ERROR:", '"detail"')


def _claude_environment() -> dict[str, str]:
    """The isolated environment for Project Factory Claude Code sessions.

    Claude.ai-managed MCP servers are injected from the logged-in account and
    are not controlled by --strict-mcp-config. Claude Code 2.1.63+ provides
    ENABLE_CLAUDEAI_MCP_SERVERS=false specifically to opt out. Set it only on
    runner-launched Claude subprocesses so normal interactive Claude usage on
    the operator machine is unchanged.
    """
    environment = child_environment()
    environment["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"
    return environment


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
    # A per-session spend ceiling, in the provider's billing currency. Zero
    # means none was set. A backend that cannot pass it to the provider leaves
    # `cost_ceiling_enforced` False on the outcome rather than pretending.
    max_cost: float = 0.0


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
    # Cache *creation* is billed separately from cache reads and was never
    # captured, so every record understated what setting a session up cost.
    cache_creation_units: int | None = None
    # The provider's own turn count, under the provider's own name. It is not
    # a tool-call count and must never be recorded as one.
    turns: int | None = None
    # Which part of the envelope the token counts came from, and which metrics
    # this session could not vouch for.
    usage_source: str = ""
    unreliable: tuple[str, ...] = ()
    cost_ceiling_enforced: bool = False
    # Non-empty when the provider stopped the session at a ceiling rather than
    # the session finishing. Carried separately from `ok` so a reader can tell
    # "ran out of budget" from "failed", which are different problems with
    # different answers.
    stopped_reason: str = ""
    permission_denials: tuple[str, ...] = ()
    provider: str = ""
    # POST_SESSION_OBSERVABLE exploration counts (repo_file_reads, repo_searches,
    # ...), read from a `stream-json` transcript when the backend produced one.
    # `None` when the format did not carry a tool-call trace - see
    # `exploration_telemetry.ExplorationTelemetry`. The bounded, normalised
    # event list travels separately in `exploration_events`, so this small
    # dict is safe to fold into `to_dict()` without growing it unpredictably.
    exploration: Mapping[str, Any] | None = None
    exploration_events: tuple[Mapping[str, Any], ...] = ()
    # Bounded names from Claude Code's system/init event. This is how V4
    # verifies the startup context surface actually shrank after changing CLI
    # flags; a configured allow-list is not evidence of what the model saw.
    startup_context: Mapping[str, Any] | None = None

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
            "cache_creation_units": self.cache_creation_units,
            "turns": self.turns,
            "usage_source": self.usage_source,
            "unreliable": list(self.unreliable),
            "cost_ceiling_enforced": self.cost_ceiling_enforced,
            "stopped_reason": self.stopped_reason,
            "permission_denials": list(self.permission_denials),
            "result_chars": len(self.result_text),
            "exploration": dict(self.exploration) if self.exploration is not None else None,
            "startup_context": (
                dict(self.startup_context) if self.startup_context is not None else None
            ),
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
            env=_claude_environment(),
        )
        if not result.ok:
            return False, f"{path} --version exited {result.exit_code}"
        return True, result.stdout.strip()

    def launch(self, request: SessionRequest) -> SessionOutcome:
        argv = [
            self.executable(),
            "--print",
            # `stream-json` under `--print` requires `--verbose` or the CLI
            # refuses to start ("Error: When using --print,
            # --output-format=stream-json requires --verbose") - found by
            # probing the installed CLI, not documented in `--help`. The
            # switch from plain `json` is what makes `repo_file_reads` /
            # `repo_searches` observable post-session: see
            # `exploration_telemetry.py`. `_read` still recovers exactly the
            # old single-envelope shape via `split_result_envelope`, so
            # `normalise_claude_usage` below needed no change.
            "--output-format",
            "stream-json",
            "--verbose",
            "--session-id",
            request.session_id,
            "--no-session-persistence",
        ]
        if request.model:
            argv += ["--model", request.model]
        for directory in request.extra_dirs:
            argv += ["--add-dir", str(directory)]

        # V4 P1: permission is not context restriction. --allowedTools only
        # decides what may execute; --tools decides which built-in tools are
        # exposed to the model at all. Use the same bounded contract for both.
        # Strict MCP with an explicit empty config prevents user/global MCP
        # servers (for example Claude Docs) from joining an engineering
        # session merely because they are configured on the operator machine.
        if request.allowed_tools:
            argv += ["--tools", ",".join(request.allowed_tools)]
            argv += ["--allowedTools", " ".join(request.allowed_tools)]
        else:
            argv += ["--tools", ""]
        argv += [
            "--strict-mcp-config",
            "--mcp-config",
            '{"mcpServers":{}}',
        ]
        if request.disallowed_tools:
            argv += ["--disallowedTools", " ".join(request.disallowed_tools)]
        # A reviewer gets no writing tool at all, so `default` is right: there
        # is nothing to accept. A developer gets `acceptEdits`, because in
        # print mode an unanswered permission prompt is a denial and the run
        # would stall instead of failing.
        argv += ["--permission-mode", "default" if request.read_only else "acceptEdits"]
        # A real ceiling, applied by the provider rather than agreed to by the
        # session. It is the only live spend limit either CLI offers.
        if request.max_cost > 0:
            argv += ["--max-budget-usd", f"{request.max_cost:.4f}"]

        result = self._runner.run(
            argv,
            cwd=request.cwd,
            timeout_s=request.timeout_s,
            env=_claude_environment(),
            stdin=request.instructions,
        )
        return self._read(request, result)

    def _read(self, request: SessionRequest, result: CommandResult) -> SessionOutcome:
        payload = split_result_envelope(result.stdout)
        telemetry = parse_exploration(result.stdout, worktree=request.cwd)
        startup = parse_startup_context(result.stdout)
        session_id = str(payload.get("session_id", "")) or request.session_id
        if not _SESSION_ID.fullmatch(session_id):
            raise BackendFailure(
                f"the {self.name} session returned no usable session id; the run "
                "cannot be attributed and is not recorded as an attempt"
            )
        usage = normalise_claude_usage(payload)
        # A session the provider stopped at a ceiling reports `is_error: false`
        # and an `error_*` subtype, which is measured behaviour: probed at
        # `--max-budget-usd 0.0001`, the envelope came back
        # `{"subtype": "error_max_budget_usd", "is_error": false}` with an exit
        # code of 0. Reading only `is_error` would record a session cut off
        # part-way as a clean one, and the runner would then hand a half-done
        # attempt to a reviewer as though the developer had finished.
        stopped_at_ceiling = str(payload.get("subtype", "")).startswith("error")
        return SessionOutcome(
            backend=self.name,
            role=request.role,
            session_id=session_id,
            model=request.model or usage.model,
            provider="anthropic",
            exit_code=result.exit_code,
            duration_s=result.duration_s,
            result_text=self._redactor.scrub(payload.get("result", "")),
            transcript=result.stdout,
            ok=result.ok and not bool(payload.get("is_error")) and not stopped_at_ceiling,
            stopped_reason=str(payload.get("subtype", "")) if stopped_at_ceiling else "",
            cost_usd=usage.cost_usd,
            input_units=usage.input_units,
            output_units=usage.output_units,
            cache_read_units=usage.cache_read_units,
            cache_creation_units=usage.cache_creation_units,
            turns=usage.turns,
            usage_source=usage.source,
            unreliable=usage.unreliable,
            cost_ceiling_enforced=request.max_cost > 0,
            permission_denials=_denials(payload.get("permission_denials")),
            exploration=telemetry.metrics_dict(),
            exploration_events=tuple(e.to_dict() for e in telemetry.events),
            startup_context=startup or None,
        )


@dataclass(frozen=True)
class NormalisedUsage:
    """One session's resource usage, read from the whole session's totals."""

    cost_usd: float | None
    input_units: int | None
    output_units: int | None
    cache_read_units: int | None
    cache_creation_units: int | None
    turns: int | None
    model: str
    source: str
    unreliable: tuple[str, ...]


def normalise_claude_usage(payload: Mapping[str, Any]) -> NormalisedUsage:
    """Read session totals from a Claude Code result envelope, not a segment.

    ## The defect this replaces

    The envelope carries three accounts of one session and they are not the
    same account:

    - `total_cost_usd` - the **whole session**;
    - `modelUsage[model]` - the **whole session**, per model;
    - `usage` - the **final segment**, and `num_turns` with it.

    Usually the session has one segment and the three agree, which is why the
    old code read cost from the first and tokens from the third for nineteen
    sessions without anybody noticing. In the twentieth they did not agree:
    `usage` said 66 output tokens and 121,579 cache reads over 1 turn, while
    `modelUsage` in the same envelope said 27,132 and 4,276,831 - a session of
    48 billed requests over 1032 seconds recorded as one turn. Turns were
    understated about sixty times and output about four hundred, silently, and
    the cost stayed right so the record looked plausible.

    ## The rule

    `modelUsage`, summed across models, is the session total and is what is
    recorded. The top-level `usage` is then compared against it: agreement
    means the session had one segment and every figure describes it; a
    disagreement means `usage` is a final segment, so `num_turns` describes
    that segment too and **turns is marked unreliable rather than reported**.

    The smaller value is never silently preferred. Where only `usage` exists -
    an envelope with no `modelUsage` at all - it is used and its source is
    recorded as `envelope_usage`, so a later reader can tell the two apart
    without reopening the transcript.
    """
    usage = payload.get("usage") if isinstance(payload.get("usage"), Mapping) else {}
    model_usage = (
        payload.get("modelUsage")
        if isinstance(payload.get("modelUsage"), Mapping)
        else {}
    )
    cost = _number(payload.get("total_cost_usd"))
    turns = _integer(payload.get("num_turns"))
    model = sorted(model_usage)[0] if model_usage else ""

    if not model_usage:
        # Nothing to cross-check against. The figures are taken as given and
        # labelled as what they are.
        return NormalisedUsage(
            cost_usd=cost,
            input_units=_integer(usage.get("input_tokens")),
            output_units=_integer(usage.get("output_tokens")),
            cache_read_units=_integer(usage.get("cache_read_input_tokens")),
            cache_creation_units=_integer(usage.get("cache_creation_input_tokens")),
            turns=turns,
            model=model,
            source="envelope_usage",
            unreliable=("model_turns",) if turns is None else (),
        )

    totals = _sum_model_usage(model_usage)
    segment_output = _integer(usage.get("output_tokens"))
    segment_cache_read = _integer(usage.get("cache_read_input_tokens"))
    agrees = (
        segment_output is not None
        and segment_cache_read is not None
        and segment_output == totals["output"]
        and segment_cache_read == totals["cache_read"]
    )

    unreliable: list[str] = []
    if not agrees:
        # `usage` describes a final segment, so `num_turns` does too. The
        # session's real turn count is not in this envelope at all.
        unreliable.append("model_turns")
        turns = None

    model_cost = totals["cost"]
    if cost is not None and model_cost is not None and not _close(cost, model_cost):
        # Two session-total cost figures that disagree. Neither is preferred;
        # the metric is marked and the larger is carried so an under-report
        # cannot pass as a saving.
        unreliable.append("session_cost")
        cost = max(cost, model_cost)
    elif cost is None:
        cost = model_cost

    return NormalisedUsage(
        cost_usd=cost,
        input_units=totals["input"],
        output_units=totals["output"],
        cache_read_units=totals["cache_read"],
        cache_creation_units=totals["cache_creation"],
        turns=turns,
        model=model,
        source="model_usage_totals" if agrees else "model_usage_totals:segment_mismatch",
        unreliable=tuple(sorted(set(unreliable))),
    )


def _sum_model_usage(model_usage: Mapping[str, Any]) -> dict[str, Any]:
    """Sum every model's block. A session may legitimately use more than one."""
    fields = {
        "input": "inputTokens",
        "output": "outputTokens",
        "cache_read": "cacheReadInputTokens",
        "cache_creation": "cacheCreationInputTokens",
    }
    totals: dict[str, Any] = {name: 0 for name in fields}
    totals["cost"] = None
    seen = {name: False for name in fields}
    for block in model_usage.values():
        if not isinstance(block, Mapping):
            continue
        for name, key in fields.items():
            value = _integer(block.get(key))
            if value is not None:
                totals[name] += value
                seen[name] = True
        cost = _number(block.get("costUSD"))
        if cost is not None:
            totals["cost"] = (totals["cost"] or 0.0) + cost
    for name in fields:
        if not seen[name]:
            totals[name] = None
    return totals


def _close(left: float, right: float) -> bool:
    """Equal to the cent, which is the resolution anybody acts on."""
    return abs(left - right) <= max(0.01, abs(right) * 0.001)


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
            stdin=CODEX_PROBE_PROMPT,
        )
        failure = _codex_failure(result.stdout)
        if failure:
            return False, failure
        if not result.ok:
            return False, f"codex exec exited {result.exit_code}"
        if CODEX_PROBE_EXPECTED not in result.stdout.replace(" ", ""):
            return False, (
                "codex exec produced no answer to the probe; the session ran and "
                "returned nothing usable"
            )
        return True, "codex exec answered a probe that its own echo cannot satisfy"

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
        failure = _codex_failure(result.stdout)
        if failure or not result.ok:
            raise BackendFailure(
                f"codex exec did not complete: {failure or result.stderr.strip()[:400]}"
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


def _codex_failure(output: str) -> str:
    """The provider's own refusal, or an empty string.

    Read from stdout rather than from the exit code, because `codex exec`
    returns 0 after a session in which every request was refused.
    """
    for line in reversed(output.splitlines()):
        if any(marker in line for marker in _CODEX_FAILURE_MARKERS):
            return line.strip()[:400]
    return ""


__all__ = [
    "CLAUDE_CODE",
    "CODEX",
    "CODEX_PROBE_EXPECTED",
    "CODEX_PROBE_PROMPT",
    "ClaudeCodeBackend",
    "CodexBackend",
    "CodingBackend",
    "SessionOutcome",
    "SessionRequest",
    "build_backend",
    "executor_hint",
]
