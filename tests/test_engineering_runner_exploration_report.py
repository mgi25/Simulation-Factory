"""Measuring stored sessions honestly: present values only, nothing invented.

Imports nothing from Company OS - same boundary as
`test_engineering_runner_repo_map.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.engineering_runner.exploration_report import (
    discover_exploration,
    discover_measurements,
    measure_exploration,
    measure_receipt,
    measure_session_telemetry,
    summarise,
)


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_measure_receipt_reads_the_real_shape(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    _write_json(
        receipt,
        {
            "files_changed": ["a.py", "b.py"],
            "usage": {
                "model_turns": 39,
                "cache_hits": 1_835_390,
                "cache_creation_units": 71_558,
                "output_units": 11_020,
                "provider_cost": "1.640637",
                "unreliable_metrics": [],
            },
        },
    )
    measurement = measure_receipt(receipt, label="run-000001/developer-01")
    assert measurement is not None
    assert measurement.model_turns == 39
    assert measurement.cache_read_units == 1_835_390
    assert measurement.files_touched == 2
    assert measurement.cost_usd == 1.640637
    assert measurement.cache_read_per_file == round(1_835_390 / 2, 1)
    assert measurement.unreliable_metrics == ()


def test_measure_receipt_returns_none_without_a_usage_block(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    _write_json(receipt, {"files_changed": ["a.py"]})
    assert measure_receipt(receipt, label="x") is None


def test_measure_receipt_is_missing_file_safe(tmp_path: Path) -> None:
    assert measure_receipt(tmp_path / "nope.json", label="x") is None


def test_cache_read_per_file_is_none_without_files_touched(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    _write_json(receipt, {"usage": {"cache_hits": 100}})
    measurement = measure_receipt(receipt, label="x")
    assert measurement is not None
    assert measurement.cache_read_per_file is None


def test_measure_session_telemetry_reads_the_runner_shape(tmp_path: Path) -> None:
    session = tmp_path / "session.json"
    _write_json(
        session,
        {
            "turns": 12,
            "cache_read_units": 40_000,
            "cache_creation_units": 5_000,
            "output_units": 900,
            "cost_usd": 0.31,
            "unreliable": ["model_turns"],
        },
    )
    measurement = measure_session_telemetry(session, label="run-000003/reviewer-01", role="reviewer")
    assert measurement is not None
    assert measurement.role == "reviewer"
    assert measurement.model_turns == 12
    assert measurement.unreliable_metrics == ("model_turns",)


def test_discover_measurements_prefers_receipt_over_session_telemetry(tmp_path: Path) -> None:
    """A stage with both files (the developer stage always has both) is
    counted once, from the receipt - the richer, files_changed-bearing record."""
    base = tmp_path / "runner-state"
    stage = base / "runs" / "wo-x" / "run-000001" / "developer-01"
    _write_json(
        stage / "receipt.json",
        {"files_changed": ["a.py"], "usage": {"model_turns": 10, "cache_hits": 1}},
    )
    _write_json(stage / "session.json", {"turns": 999, "cache_read_units": 999})

    measurements = discover_measurements([base])
    assert len(measurements) == 1
    assert measurements[0].model_turns == 10


def test_discover_measurements_falls_back_to_session_json_for_reviewer_stages(
    tmp_path: Path,
) -> None:
    base = tmp_path / "runner-state"
    dev_stage = base / "runs" / "wo-x" / "run-000001" / "developer-01"
    review_stage = base / "runs" / "wo-x" / "run-000003" / "reviewer-01"
    _write_json(
        dev_stage / "receipt.json",
        {"files_changed": ["a.py"], "usage": {"model_turns": 10, "cache_hits": 1}},
    )
    _write_json(review_stage / "session.json", {"turns": 5, "cache_read_units": 200})

    measurements = discover_measurements([base])
    roles = sorted(m.role for m in measurements)
    assert roles == ["developer", "reviewer"]


def test_discover_measurements_skips_a_missing_directory(tmp_path: Path) -> None:
    assert discover_measurements([tmp_path / "does-not-exist"]) == ()


def test_summarise_never_imputes_a_missing_value_as_zero(tmp_path: Path) -> None:
    base = tmp_path / "runner-state"
    stage_a = base / "runs" / "wo-x" / "run-000001" / "developer-01"
    stage_b = base / "runs" / "wo-y" / "run-000001" / "developer-01"
    _write_json(
        stage_a / "receipt.json",
        {"files_changed": ["a.py"], "usage": {"model_turns": 10, "cache_hits": 100}},
    )
    _write_json(
        stage_b / "receipt.json",
        {"files_changed": ["a.py"], "usage": {}},
    )
    measurements = discover_measurements([base])
    summary = summarise(measurements)
    # Only one of the two developer attempts reported turns; the average is
    # over that one value, not diluted by treating the other as a zero.
    assert summary["developer"]["avg_model_turns"] == 10
    assert summary["developer"]["count"] == 2


def test_measure_exploration_reads_the_runner_shape(tmp_path: Path) -> None:
    exploration = tmp_path / "exploration.json"
    _write_json(
        exploration,
        {
            "format": "stream_json",
            "file_reads_total": 10,
            "file_reads_unique": 7,
            "file_reads_repeated": 3,
            "searches_total": 4,
            "searches_repeated": 1,
            "git_commands": 2,
            "test_commands": 1,
            "other_shell_commands": 0,
            "events": [
                {"order": 1, "tool": "Read", "category": "", "target": "a.py", "repeat": False},
                {"order": 2, "tool": "Read", "category": "", "target": "b.py", "repeat": False},
            ],
        },
    )
    measurement = measure_exploration(exploration, label="developer-01", role="developer")
    assert measurement is not None
    assert measurement.format == "stream_json"
    assert measurement.file_reads_total == 10
    assert measurement.file_reads_repeated == 3
    assert measurement.files_read_never_changed == ("a.py", "b.py")


def test_measure_exploration_excludes_changed_paths_from_never_changed(tmp_path: Path) -> None:
    exploration = tmp_path / "exploration.json"
    _write_json(
        exploration,
        {
            "format": "stream_json",
            "events": [
                {"order": 1, "tool": "Read", "category": "", "target": "a.py", "repeat": False},
                {"order": 2, "tool": "Read", "category": "", "target": "b.py", "repeat": False},
            ],
        },
    )
    measurement = measure_exploration(
        exploration, label="developer-01", role="developer", changed_paths=["a.py"]
    )
    assert measurement is not None
    assert measurement.files_read_never_changed == ("b.py",)


def test_measure_exploration_excludes_external_paths_from_never_changed(tmp_path: Path) -> None:
    exploration = tmp_path / "exploration.json"
    _write_json(
        exploration,
        {
            "format": "stream_json",
            "events": [
                {"order": 1, "tool": "Read", "category": "", "target": "<external>", "repeat": False},
            ],
        },
    )
    measurement = measure_exploration(exploration, label="x", role="developer")
    assert measurement is not None
    assert measurement.files_read_never_changed == ()


def test_measure_exploration_of_an_unsupported_format_has_none_counts(tmp_path: Path) -> None:
    exploration = tmp_path / "exploration.json"
    _write_json(exploration, {"format": "unsupported", "events": []})
    measurement = measure_exploration(exploration, label="x", role="developer")
    assert measurement is not None
    assert measurement.file_reads_total is None
    assert measurement.searches_total is None


def test_measure_exploration_is_missing_file_safe(tmp_path: Path) -> None:
    assert measure_exploration(tmp_path / "nope.json", label="x", role="developer") is None


def test_discover_exploration_cross_references_changes_json(tmp_path: Path) -> None:
    base = tmp_path / "runner-state"
    stage = base / "runs" / "wo-x" / "run-000001" / "developer-01"
    _write_json(
        stage / "exploration.json",
        {
            "format": "stream_json",
            "file_reads_total": 2,
            "events": [
                {"order": 1, "tool": "Read", "category": "", "target": "a.py", "repeat": False},
                {"order": 2, "tool": "Read", "category": "", "target": "b.py", "repeat": False},
            ],
        },
    )
    _write_json(stage / "changes.json", {"changed": ["a.py"]})

    measurements = discover_exploration([base])
    assert len(measurements) == 1
    assert measurements[0].role == "developer"
    assert measurements[0].files_read_never_changed == ("b.py",)


def test_discover_exploration_skips_a_missing_directory(tmp_path: Path) -> None:
    assert discover_exploration([tmp_path / "does-not-exist"]) == ()


def test_summarise_counts_unreliable_sessions(tmp_path: Path) -> None:
    base = tmp_path / "runner-state"
    stage = base / "runs" / "wo-x" / "run-000001" / "developer-01"
    _write_json(
        stage / "receipt.json",
        {
            "files_changed": ["a.py"],
            "usage": {"model_turns": 1, "unreliable_metrics": ["model_turns"]},
        },
    )
    summary = summarise(discover_measurements([base]))
    assert summary["sessions_with_unreliable_metrics"] == 1
