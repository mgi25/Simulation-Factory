"""Parsing a coding session's `stream-json` transcript into exploration telemetry.

Imports nothing from Company OS - same boundary as the other
`tools.engineering_runner` test files. Fixtures are hand-built NDJSON lines
matching the exact shape a live probe of the installed Claude Code CLI
(2.1.70) produced, not this repository's own transcripts.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.engineering_runner.exploration_telemetry import (
    ExplorationTelemetry,
    files_read_never_changed,
    files_read_outside_neighborhood,
    parse_exploration,
    split_result_envelope,
)


def _line(**kwargs) -> str:
    return json.dumps(kwargs)


def _assistant(*blocks: dict) -> str:
    return _line(type="assistant", message={"content": list(blocks)})


def _tool_use(name: str, **input_kwargs) -> dict:
    return {"type": "tool_use", "name": name, "input": input_kwargs}


def _user_tool_result(content: str) -> str:
    return _line(type="user", message={"content": [{"type": "tool_result", "content": content}]})


RESULT_LINE = _line(
    type="result",
    subtype="success",
    is_error=False,
    num_turns=6,
    result="done",
    session_id="969224c7-da85-4887-b6b0-30b08690fbfa",
    total_cost_usd=0.0157,
    usage={"input_tokens": 34, "output_tokens": 669},
    modelUsage={"claude-haiku-4-5-20251001": {"inputTokens": 34, "outputTokens": 669}},
)

INIT_LINE = _line(
    type="system",
    subtype="init",
    cwd="/repo",
    session_id="969224c7-da85-4887-b6b0-30b08690fbfa",
    tools=["Read", "Grep"],
)


def _transcript(*lines: str) -> str:
    return "\n".join((INIT_LINE, *lines, RESULT_LINE)) + "\n"


def test_a_single_read_is_recorded_and_normalised_to_repo_relative(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Read", file_path=str(worktree / "tools" / "x.py")))
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.format == "stream_json"
    assert telemetry.file_reads_total == 1
    assert telemetry.file_reads_unique == 1
    assert telemetry.file_reads_repeated == 0
    assert telemetry.events[0].tool == "Read"
    assert telemetry.events[0].target == "tools/x.py"
    assert telemetry.events[0].repeat is False


def test_a_repeated_read_of_the_same_path_is_counted_as_repeated(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    target = str(worktree / "tools" / "x.py")
    transcript = _transcript(
        _assistant(_tool_use("Read", file_path=target)),
        _assistant(_tool_use("Read", file_path=target)),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.file_reads_total == 2
    assert telemetry.file_reads_unique == 1
    assert telemetry.file_reads_repeated == 1
    assert telemetry.events[1].repeat is True


def test_a_relative_read_path_is_kept_as_is(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(_assistant(_tool_use("Read", file_path="tools/x.py")))
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.events[0].target == "tools/x.py"


def test_an_absolute_read_outside_the_worktree_is_external(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    outside = tmp_path / "elsewhere" / "y.py"
    transcript = _transcript(_assistant(_tool_use("Read", file_path=str(outside))))
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.events[0].target == "<external>"


def test_grep_and_glob_are_counted_separately_and_summed(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Grep", pattern="class Foo")),
        _assistant(_tool_use("Glob", pattern="**/*.py")),
        _assistant(_tool_use("Grep", pattern="class Foo")),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.grep_total == 2
    assert telemetry.glob_total == 1
    assert telemetry.searches_total == 3
    assert telemetry.searches_repeated == 1


def test_bash_commands_are_reduced_to_a_category_never_the_command_text(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Bash", command="git status")),
        _assistant(_tool_use("Bash", command="python -m pytest tests/test_x.py")),
        _assistant(_tool_use("Bash", command="rm -rf build")),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.git_commands == 1
    assert telemetry.test_commands == 1
    assert telemetry.other_shell_commands == 1
    assert telemetry.bash_total == 3
    categories = {e.category for e in telemetry.events if e.tool == "Bash"}
    assert categories == {"git", "test", "other"}
    for event in telemetry.events:
        assert "git status" not in event.target
        assert "rm -rf" not in event.target


def test_a_tool_use_error_is_counted(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Read", path="wrong-param")),
        _user_tool_result("<tool_use_error>InputValidationError: bad</tool_use_error>"),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.tool_errors == 1


def test_a_plain_json_envelope_has_unsupported_format_not_zero_counts(tmp_path: Path) -> None:
    """A plain `--output-format json` (or any non-stream) transcript carries no
    tool-call trace at all - the counts must be `None` (UNAVAILABLE), not `0`
    (a measured, empty session)."""
    worktree = tmp_path / "repo"
    plain = json.dumps({"type": "result", "session_id": "x", "result": "done"})
    telemetry = parse_exploration(plain, worktree=worktree)
    assert telemetry.format == "unsupported"
    assert telemetry.file_reads_total is None
    assert telemetry.searches_total is None
    assert telemetry.events == ()


def test_empty_text_is_unsupported(tmp_path: Path) -> None:
    telemetry = parse_exploration("", worktree=tmp_path)
    assert telemetry.format == "unsupported"


def test_events_are_bounded_by_max_events(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    many = [_assistant(_tool_use("Read", file_path=f"tools/f{i}.py")) for i in range(600)]
    transcript = _transcript(*many)
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert telemetry.file_reads_total == 600
    assert len(telemetry.events) == 500


def test_split_result_envelope_finds_the_last_result_line_in_a_stream(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(_assistant(_tool_use("Read", file_path="x.py")))
    envelope = split_result_envelope(transcript)
    assert envelope["session_id"] == "969224c7-da85-4887-b6b0-30b08690fbfa"
    assert envelope["total_cost_usd"] == 0.0157
    assert envelope["modelUsage"]


def test_split_result_envelope_falls_back_to_a_single_json_object() -> None:
    plain = json.dumps({"session_id": "y", "total_cost_usd": 0.01, "is_error": False})
    envelope = split_result_envelope(plain)
    assert envelope["session_id"] == "y"


def test_split_result_envelope_of_unparseable_text_is_empty() -> None:
    assert split_result_envelope("not json at all") == {}


def test_metrics_dict_has_no_events_key() -> None:
    telemetry = ExplorationTelemetry(format="unsupported")
    assert "events" not in telemetry.metrics_dict()
    assert "events" in telemetry.to_dict()


def test_files_read_never_changed_excludes_changed_paths(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Read", file_path="a.py")),
        _assistant(_tool_use("Read", file_path="b.py")),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert files_read_never_changed(telemetry, changed_paths=["a.py"]) == ("b.py",)


def test_files_read_outside_neighborhood_excludes_known_paths(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    transcript = _transcript(
        _assistant(_tool_use("Read", file_path="a.py")),
        _assistant(_tool_use("Read", file_path="b.py")),
    )
    telemetry = parse_exploration(transcript, worktree=worktree)
    assert files_read_outside_neighborhood(telemetry, neighborhood_paths=["a.py"]) == ("b.py",)
