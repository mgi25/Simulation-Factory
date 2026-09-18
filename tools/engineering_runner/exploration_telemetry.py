"""Reading a coding session's own account of what it explored.

## The change this module makes possible

Repository Exploration Efficiency V1 declared `repo_file_reads` and
`repo_searches` UNAVAILABLE, "by construction, permanently, unless the launch
mode itself changes" (`repo_map.py`'s original docstring). The launch mode
changed: the installed Claude Code CLI (2.1.70) supports
`--output-format stream-json`, probed live rather than assumed from
documentation. Under `--print` it additionally requires `--verbose` or the
CLI refuses to start - `Error: When using --print, --output-format=stream-json
requires --verbose` - a fact only a live probe found, since nothing in
`--help` says so.

With that flag, stdout is newline-delimited JSON: one `system`/`init` message,
one message per model turn (`assistant`, carrying `tool_use` content blocks;
`user`, carrying the matching `tool_result`), and exactly one final `result`
message with the same shape `backends.normalise_claude_usage` already reads
from plain `--output-format json` - probed and confirmed byte-for-byte on the
same fields (`session_id`, `usage`, `modelUsage`, `total_cost_usd`,
`num_turns`, `is_error`, `subtype`, `permission_denials`). So
`normalise_claude_usage` needed no change at all: `split_result_envelope`
below finds that one line and hands it over unmodified.

## What is kept, and what is not

Only normalised events: a tool name, a category, and - for `Read`, `Grep` and
`Glob` - a repository-relative path or a search pattern, in call order. Never
kept: full tool output, file contents, raw Bash command text, or the
assistant's own prose. A `Bash` call is reduced to a category
(`git` / `test` / `search` / `other`) precisely because the brief asks for
"shell command category", not the command - the category is what a routine
job's exploration profile needs, and the command text is exactly the kind of
thing a session might paste a credential or a file's content into.

`CommandRunner.run` already scrubs the whole of `stdout` before this module
ever sees it (`process.py`), so nothing here re-implements redaction; it reads
text that has already crossed that boundary.

## Why this needed no change to `process.py`

`CommandRunner.run` calls `subprocess.run(capture_output=True)` and returns
only once the process exits - true before this module existed and still true.
Switching the CLI to `stream-json` changes the *shape* of the one string that
comes back at the end (many JSON lines instead of one JSON object), not *when*
it comes back. Real per-event, mid-session observation would need incremental
reads from a live pipe, which is a materially bigger change to the one
subprocess boundary this package has - and the brief asks for the smallest
safe additive mechanism, with live enforcement explicitly secondary. So this
module produces `POST_SESSION_OBSERVABLE` telemetry, and nothing here claims
more than that.

## Path normalisation is best-effort, not a validator

`authorization.normalise_path` raises on an absolute path, because a scope
rule must name one unambiguous repository location. This module is reading a
session's own free-form tool arguments, not a scope rule - a path outside the
worktree, or one Python's `Path` cannot parse, is recorded as external rather
than raised, because a telemetry gap must never abort a real session.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

EXTERNAL = "<external>"

_GIT_MARKERS = ("git ",)
_TEST_MARKERS = ("pytest", "unittest", "-m pytest")
_SEARCH_MARKERS = ("grep ", "rg ", "find ", "grep\t")

# How many normalised events are kept verbatim. Well past what a routine
# session's exploration actually produces (V1's matched job ran 27 developer
# turns in total); a ceiling is stated anyway so a pathological session cannot
# turn this into an unbounded write.
MAX_EVENTS = 500


@dataclass(frozen=True)
class ExplorationEvent:
    """One tool call, reduced to what is safe and useful to keep."""

    order: int
    tool: str  # "Read" | "Grep" | "Glob" | "Bash" | "Other"
    category: str  # Bash only: "git" | "test" | "search" | "other"; else ""
    target: str  # normalised repo-relative path (Read) or pattern (Grep/Glob)
    repeat: bool  # this (tool, target) pair was already seen earlier this session

    def to_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "tool": self.tool,
            "category": self.category,
            "target": self.target,
            "repeat": self.repeat,
        }


@dataclass(frozen=True)
class ExplorationTelemetry:
    """One session's exploration, as counts plus a bounded, normalised trace.

    Every count is `int | None`: `None` means the session's transcript could
    not be read as `stream-json` (a different backend, an older CLI, a plain
    `--output-format json` session) and the value is truly UNAVAILABLE, not
    zero. A `0` means the format parsed and the count is genuinely zero. This
    is the same discipline `company.efficiency.budget.check_budget` already
    holds every other dimension to - "a missing value is never a zero".
    """

    format: str  # "stream_json" | "unsupported"
    events: tuple[ExplorationEvent, ...] = ()
    file_reads_total: int | None = None
    file_reads_unique: int | None = None
    file_reads_repeated: int | None = None
    grep_total: int | None = None
    glob_total: int | None = None
    searches_total: int | None = None
    searches_repeated: int | None = None
    git_commands: int | None = None
    test_commands: int | None = None
    other_shell_commands: int | None = None
    bash_total: int | None = None
    tool_errors: int | None = None

    def metrics_dict(self) -> dict[str, Any]:
        """The small summary - no events, safe to embed in `SessionOutcome.to_dict()`."""
        return {
            "format": self.format,
            "file_reads_total": self.file_reads_total,
            "file_reads_unique": self.file_reads_unique,
            "file_reads_repeated": self.file_reads_repeated,
            "grep_total": self.grep_total,
            "glob_total": self.glob_total,
            "searches_total": self.searches_total,
            "searches_repeated": self.searches_repeated,
            "git_commands": self.git_commands,
            "test_commands": self.test_commands,
            "other_shell_commands": self.other_shell_commands,
            "bash_total": self.bash_total,
            "tool_errors": self.tool_errors,
            "events_recorded": len(self.events),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self.metrics_dict(), "events": [e.to_dict() for e in self.events]}


def _relativize(raw: str, root: Path) -> str:
    """A repository-relative POSIX path, or `EXTERNAL` - never a raised error."""
    if not raw:
        return ""
    text = str(raw).replace("\\", "/")
    try:
        candidate = Path(raw)
        if candidate.is_absolute():
            resolved = candidate.resolve()
            root_resolved = root.resolve()
            try:
                return resolved.relative_to(root_resolved).as_posix()
            except ValueError:
                return EXTERNAL
        return text
    except (OSError, ValueError):
        return EXTERNAL


def _bash_category(command: str) -> str:
    lowered = command.lower().strip()
    if lowered.startswith(_GIT_MARKERS) or lowered == "git":
        return "git"
    if any(marker in lowered for marker in _TEST_MARKERS):
        return "test"
    if any(lowered.startswith(marker) for marker in _SEARCH_MARKERS):
        return "search"
    return "other"


def _iter_result_lines(text: str) -> list[Mapping[str, Any]]:
    lines: list[Mapping[str, Any]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or not stripped.startswith("{"):
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            lines.append(parsed)
    return lines


def split_result_envelope(text: str) -> dict[str, Any]:
    """The final `result` message of a `stream-json` transcript, or the whole
    text parsed as one object - whichever shape `text` actually is.

    This is the seam that keeps `backends.normalise_claude_usage` unchanged:
    both shapes converge here on the same envelope dict, probed identical on
    every field that function reads.
    """
    lines = _iter_result_lines(text)
    for line in reversed(lines):
        if line.get("type") == "result":
            return dict(line)
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            loaded = json.loads(stripped)
        except json.JSONDecodeError:
            return {}
        return dict(loaded) if isinstance(loaded, Mapping) else {}
    return {}


def parse_exploration(text: str, *, worktree: Path) -> ExplorationTelemetry:
    """Read a session's transcript for its tool calls, or say the format is unsupported.

    `worktree` is the session's own `cwd` (`SessionRequest.cwd`), used to turn
    an absolute `file_path` back into the repository-relative path a briefing
    would recognise - the same root the session itself was launched in, not a
    value re-derived from the transcript.
    """
    lines = _iter_result_lines(text)
    has_stream_shape = any(line.get("type") in ("assistant", "user", "system") for line in lines)
    if not lines or not has_stream_shape:
        return ExplorationTelemetry(format="unsupported")

    events: list[ExplorationEvent] = []
    seen: set[tuple[str, str]] = set()
    grep_total = glob_total = read_total = bash_total = 0
    git_commands = test_commands = other_shell = 0
    searches_repeated = reads_repeated = 0
    tool_errors = 0
    order = 0

    for line in lines:
        if line.get("type") == "user":
            content = line.get("message", {})
            content = content.get("content") if isinstance(content, Mapping) else None
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, Mapping) and block.get("type") == "tool_result":
                        payload = block.get("content")
                        text_payload = payload if isinstance(payload, str) else json.dumps(payload)
                        if "tool_use_error" in text_payload or "InputValidationError" in text_payload:
                            tool_errors += 1
            continue
        if line.get("type") != "assistant":
            continue
        message = line.get("message", {})
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, Mapping) or block.get("type") != "tool_use":
                continue
            name = str(block.get("name", ""))
            raw_input = block.get("input")
            raw_input = raw_input if isinstance(raw_input, Mapping) else {}
            order += 1
            if name == "Read":
                target = _relativize(str(raw_input.get("file_path", "")), worktree)
                key = (name, target)
                repeat = key in seen
                seen.add(key)
                read_total += 1
                reads_repeated += 1 if repeat else 0
                events.append(ExplorationEvent(order, "Read", "", target, repeat))
            elif name in ("Grep", "Glob"):
                target = str(raw_input.get("pattern", ""))
                key = (name, target)
                repeat = key in seen
                seen.add(key)
                if name == "Grep":
                    grep_total += 1
                else:
                    glob_total += 1
                searches_repeated += 1 if repeat else 0
                events.append(ExplorationEvent(order, name, "", target, repeat))
            elif name == "Bash":
                command = str(raw_input.get("command", ""))
                category = _bash_category(command)
                bash_total += 1
                if category == "git":
                    git_commands += 1
                elif category == "test":
                    test_commands += 1
                elif category == "other":
                    other_shell += 1
                events.append(ExplorationEvent(order, "Bash", category, "", False))
            else:
                events.append(ExplorationEvent(order, name or "Other", "", "", False))

    unique_reads = len({e.target for e in events if e.tool == "Read"})
    searches_total = grep_total + glob_total
    return ExplorationTelemetry(
        format="stream_json",
        events=tuple(events[:MAX_EVENTS]),
        file_reads_total=read_total,
        file_reads_unique=unique_reads,
        file_reads_repeated=reads_repeated,
        grep_total=grep_total,
        glob_total=glob_total,
        searches_total=searches_total,
        searches_repeated=searches_repeated,
        git_commands=git_commands,
        test_commands=test_commands,
        other_shell_commands=other_shell,
        bash_total=bash_total,
        tool_errors=tool_errors,
    )


def files_read_never_changed(
    telemetry: ExplorationTelemetry, *, changed_paths: Sequence[str]
) -> tuple[str, ...]:
    """Paths the session read (per its own transcript) but never touched.

    A read-heavy, write-light session is not automatically wasteful - a
    reviewer is read-only by design - so this is reported as a fact for
    `exploration_report.py` to summarise, never as a violation.
    """
    changed = set(changed_paths)
    read = {e.target for e in telemetry.events if e.tool == "Read" and e.target and e.target != EXTERNAL}
    return tuple(sorted(read - changed))


def files_read_outside_neighborhood(
    telemetry: ExplorationTelemetry, *, neighborhood_paths: Sequence[str]
) -> tuple[str, ...]:
    """Paths the session read that the deterministic neighborhood never named.

    Not a defect measure by itself: the neighborhood is bounded and a real
    task legitimately reaches outside it. It is the number this milestone's
    execution-context bundle is meant to shrink over successive jobs.
    """
    known = set(neighborhood_paths)
    read = {e.target for e in telemetry.events if e.tool == "Read" and e.target and e.target != EXTERNAL}
    return tuple(sorted(read - known))


__all__ = [
    "EXTERNAL",
    "MAX_EVENTS",
    "ExplorationEvent",
    "ExplorationTelemetry",
    "files_read_never_changed",
    "files_read_outside_neighborhood",
    "parse_exploration",
    "split_result_envelope",
]
