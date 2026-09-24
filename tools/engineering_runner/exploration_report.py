"""What the stored receipts can honestly say about repository exploration.

## The measurement Repository Exploration Efficiency V1 opened with

V1's brief asked to measure historical sessions before building anything, and
found that every stored session before it - one `receipt.json` per developer
attempt, one runner-written `session.json` per other stage - carried no record
of which file a session read or what it searched for, because
`ClaudeCodeBackend.launch` ran the CLI with `--output-format json`, a single
final envelope. That measurement was declared UNAVAILABLE, permanently,
"unless the launch mode itself changes".

## What Repository Exploration Efficiency V2 changed

The launch mode changed: `backends.py` now runs `--output-format stream-json
--verbose` (probed live against the installed CLI, not assumed - see
`exploration_telemetry.py`), and a stage now writes a companion
`exploration.json` alongside `session.json` holding the session's own bounded,
normalised tool-call trace. `discover_exploration` below reads that file the
same way `discover_measurements` reads a receipt: present values only,
`None` left as `None`, never imputed as zero. A run from before this change,
or from the `codex` backend, simply has no `exploration.json` and is skipped -
that absence is the honest UNAVAILABLE case, not a zero.

## Reliability, per field

- `model_turns`, `cache_read_units`, `cache_creation_units`, `output_units`,
  `cost_usd`: RELIABLE when `unreliable_metrics` is empty for that session,
  PARTIAL (recorded but flagged) otherwise. The normaliser that produces
  `unreliable_metrics` is `tools/engineering_runner/backends.py`'s
  `normalise_claude_usage`.
- `files_touched`: RELIABLE - measured from git by `evidence.py`, not
  self-reported.
- `file_reads_total` / `_unique` / `_repeated`, `searches_total` /
  `_repeated`, `git_commands`, `other_shell_commands`: RELIABLE when
  `exploration.json`'s `format` is `stream_json` - read from the session's own
  transcript, not self-reported prose. UNAVAILABLE (not zero) when the format
  is `unsupported` or the file does not exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class AttemptMeasurement:
    """One stored attempt, read from its own receipt or runner telemetry."""

    label: str
    role: str
    model_turns: int | None
    cache_read_units: int | None
    cache_creation_units: int | None
    output_units: int | None
    cost_usd: float | None
    files_touched: int | None
    unreliable_metrics: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "role": self.role,
            "model_turns": self.model_turns,
            "cache_read_units": self.cache_read_units,
            "cache_creation_units": self.cache_creation_units,
            "output_units": self.output_units,
            "cost_usd": self.cost_usd,
            "files_touched": self.files_touched,
            "unreliable_metrics": list(self.unreliable_metrics),
        }

    @property
    def cache_read_per_file(self) -> float | None:
        """Exploration cost per file actually changed - a proxy, not a count.

        A high value does not prove wasted reads; a bounded change to a
        heavily-depended-on module legitimately needs more context than one
        that touches nothing else reads. It is the number this milestone's
        own ceiling (`company.efficiency.profile.ResourceProfile.
        session_cache_read_ceiling`) is a blunt version of.
        """
        if self.cache_read_units is None or not self.files_touched:
            return None
        return round(self.cache_read_units / self.files_touched, 1)


def _read_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


def measure_receipt(path: Path, *, label: str, role: str = "developer") -> AttemptMeasurement | None:
    """A developer (or reviewer, if one wrote a receipt) stage's `receipt.json`."""
    data = _read_json(path)
    usage = data.get("usage")
    if not isinstance(usage, Mapping):
        return None
    files = data.get("files_changed")
    cost = usage.get("provider_cost")
    return AttemptMeasurement(
        label=label,
        role=role,
        model_turns=_int(usage.get("model_turns")),
        cache_read_units=_int(usage.get("cache_hits")),
        cache_creation_units=_int(usage.get("cache_creation_units")),
        output_units=_int(usage.get("output_units")),
        cost_usd=float(cost) if isinstance(cost, (str, int, float)) and cost != "" else None,
        files_touched=len(files) if isinstance(files, Sequence) else None,
        unreliable_metrics=tuple(str(x) for x in usage.get("unreliable_metrics", ())),
    )


def measure_session_telemetry(
    path: Path, *, label: str, role: str, files_touched: int | None = None
) -> AttemptMeasurement | None:
    """One runner-written provider session.

    Numbered `session-N.json` files are authoritative when present because a
    single stage may launch more than one paid provider subprocess.
    """
    data = _read_json(path)
    if not data:
        return None
    return AttemptMeasurement(
        label=label,
        role=role,
        model_turns=_int(data.get("turns")),
        cache_read_units=_int(data.get("cache_read_units")),
        cache_creation_units=_int(data.get("cache_creation_units")),
        output_units=_int(data.get("output_units")),
        cost_usd=_float(data.get("cost_usd")),
        files_touched=files_touched,
        unreliable_metrics=tuple(str(x) for x in data.get("unreliable", ())),
    )


def _int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _role_from_dirname(name: str) -> str:
    if name.startswith("reviewer"):
        return "reviewer"
    if name.startswith("gate"):
        return "gate"
    return "developer"


def discover_measurements(run_state_dirs: Sequence[Path]) -> tuple[AttemptMeasurement, ...]:
    """Measure every paid provider subprocess exactly once.

    New and historical runner stages preserve numbered `session-N.json`
    artifacts. Those are authoritative over the mutable `session.json` alias
    and over a receipt aggregate: counting the aggregate plus its components
    would double count, while counting only the final alias can hide an
    expensive earlier repair session.
    """
    found: list[AttemptMeasurement] = []
    for base in run_state_dirs:
        if not base.is_dir():
            continue

        numbered_stage_dirs: set[Path] = set()
        for session_path in sorted(base.rglob("session-*.json")):
            suffix = session_path.stem.removeprefix("session-")
            if not suffix.isdigit():
                continue
            stage_dir = session_path.parent
            numbered_stage_dirs.add(stage_dir)
            role = _role_from_dirname(stage_dir.name)
            label = (
                str(stage_dir.relative_to(base)).replace("\\", "/")
                + "/"
                + session_path.stem
            )
            changes = _read_json(stage_dir / "changes.json")
            changed = changes.get("changed", ()) if isinstance(changes, Mapping) else ()
            files_touched = len(changed) if isinstance(changed, Sequence) else None
            measurement = measure_session_telemetry(
                session_path,
                label=label,
                role=role,
                files_touched=files_touched,
            )
            if measurement is not None:
                found.append(measurement)

        receipted_dirs: set[Path] = set()
        for receipt_path in sorted(base.rglob("receipt.json")):
            stage_dir = receipt_path.parent
            if stage_dir in numbered_stage_dirs:
                continue
            role = _role_from_dirname(stage_dir.name)
            label = str(stage_dir.relative_to(base)).replace("\\", "/")
            measurement = measure_receipt(receipt_path, label=label, role=role)
            if measurement is not None:
                found.append(measurement)
                receipted_dirs.add(stage_dir)

        for session_path in sorted(base.rglob("session.json")):
            stage_dir = session_path.parent
            if stage_dir in numbered_stage_dirs or stage_dir in receipted_dirs:
                continue
            role = _role_from_dirname(stage_dir.name)
            label = str(stage_dir.relative_to(base)).replace("\\", "/")
            measurement = measure_session_telemetry(session_path, label=label, role=role)
            if measurement is not None:
                found.append(measurement)
    return tuple(found)


@dataclass(frozen=True)
class ExplorationMeasurement:
    """One stage's own exploration trace, read from its `exploration.json`."""

    label: str
    role: str
    format: str
    file_reads_total: int | None
    file_reads_unique: int | None
    file_reads_repeated: int | None
    searches_total: int | None
    searches_repeated: int | None
    git_commands: int | None
    test_commands: int | None
    other_shell_commands: int | None
    files_read_never_changed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "role": self.role,
            "format": self.format,
            "file_reads_total": self.file_reads_total,
            "file_reads_unique": self.file_reads_unique,
            "file_reads_repeated": self.file_reads_repeated,
            "searches_total": self.searches_total,
            "searches_repeated": self.searches_repeated,
            "git_commands": self.git_commands,
            "test_commands": self.test_commands,
            "other_shell_commands": self.other_shell_commands,
            "files_read_never_changed": list(self.files_read_never_changed),
        }


def measure_exploration(
    path: Path, *, label: str, role: str, changed_paths: Sequence[str] = ()
) -> ExplorationMeasurement | None:
    """One stage's `exploration.json`, cross-referenced against what it changed.

    `changed_paths` is the developer stage's own measured `files_changed`
    (from `changes.json`, read by git - never self-reported). A reviewer
    stage changes nothing by construction, so an empty sequence there simply
    means every read the reviewer made counts as "never changed", which is
    exactly true of a read-only session.
    """
    data = _read_json(path)
    if not data:
        return None
    events = data.get("events", ())
    read_targets = tuple(
        str(e.get("target", ""))
        for e in events
        if isinstance(e, Mapping) and e.get("tool") == "Read" and e.get("target")
    )
    changed = set(changed_paths)
    never_changed = tuple(sorted({t for t in read_targets if t not in changed and t != "<external>"}))
    return ExplorationMeasurement(
        label=label,
        role=role,
        format=str(data.get("format", "unsupported")),
        file_reads_total=_int(data.get("file_reads_total")),
        file_reads_unique=_int(data.get("file_reads_unique")),
        file_reads_repeated=_int(data.get("file_reads_repeated")),
        searches_total=_int(data.get("searches_total")),
        searches_repeated=_int(data.get("searches_repeated")),
        git_commands=_int(data.get("git_commands")),
        test_commands=_int(data.get("test_commands")),
        other_shell_commands=_int(data.get("other_shell_commands")),
        files_read_never_changed=never_changed,
    )


def discover_exploration(run_state_dirs: Sequence[Path]) -> tuple[ExplorationMeasurement, ...]:
    """Measure each preserved session exploration trace exactly once.

    V4 writes `exploration-N.json` beside every numbered session. Older
    stages have only the mutable `exploration.json` alias; that legacy file is
    used only when no numbered exploration artifacts exist for the stage.
    """
    found: list[ExplorationMeasurement] = []
    for base in run_state_dirs:
        if not base.is_dir():
            continue

        numbered_stage_dirs: set[Path] = set()
        for exploration_path in sorted(base.rglob("exploration-*.json")):
            suffix = exploration_path.stem.removeprefix("exploration-")
            if not suffix.isdigit():
                continue
            stage_dir = exploration_path.parent
            numbered_stage_dirs.add(stage_dir)
            role = _role_from_dirname(stage_dir.name)
            label = (
                str(stage_dir.relative_to(base)).replace("\\", "/")
                + "/"
                + exploration_path.stem
            )
            changes = _read_json(stage_dir / "changes.json")
            changed_paths = changes.get("changed", ()) if isinstance(changes, Mapping) else ()
            measurement = measure_exploration(
                exploration_path, label=label, role=role, changed_paths=changed_paths
            )
            if measurement is not None:
                found.append(measurement)

        for exploration_path in sorted(base.rglob("exploration.json")):
            stage_dir = exploration_path.parent
            if stage_dir in numbered_stage_dirs:
                continue
            role = _role_from_dirname(stage_dir.name)
            label = str(stage_dir.relative_to(base)).replace("\\", "/")
            changes = _read_json(stage_dir / "changes.json")
            changed_paths = changes.get("changed", ()) if isinstance(changes, Mapping) else ()
            measurement = measure_exploration(
                exploration_path, label=label, role=role, changed_paths=changed_paths
            )
            if measurement is not None:
                found.append(measurement)
    return tuple(found)


def _avg(values: Sequence[float | int | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def _max(values: Sequence[float | int | None]) -> float | int | None:
    present = [v for v in values if v is not None]
    return max(present) if present else None


def summarise(measurements: Sequence[AttemptMeasurement]) -> dict[str, object]:
    """Aggregate only over values actually present. A missing value is never a zero."""
    developer = [m for m in measurements if m.role == "developer"]
    reviewer = [m for m in measurements if m.role == "reviewer"]
    return {
        "sessions_measured": len(measurements),
        "sessions_with_unreliable_metrics": sum(
            1 for m in measurements if m.unreliable_metrics
        ),
        "developer": {
            "count": len(developer),
            "avg_model_turns": _avg([m.model_turns for m in developer]),
            "max_model_turns": _max([m.model_turns for m in developer]),
            "avg_cache_read_units": _avg([m.cache_read_units for m in developer]),
            "max_cache_read_units": _max([m.cache_read_units for m in developer]),
            "avg_cache_read_per_file": _avg([m.cache_read_per_file for m in developer]),
        },
        "reviewer": {
            "count": len(reviewer),
            "avg_model_turns": _avg([m.model_turns for m in reviewer]),
            "avg_cache_read_units": _avg([m.cache_read_units for m in reviewer]),
        },
        "attempts": [m.to_dict() for m in measurements],
    }


__all__ = [
    "AttemptMeasurement",
    "ExplorationMeasurement",
    "discover_exploration",
    "discover_measurements",
    "measure_exploration",
    "measure_receipt",
    "measure_session_telemetry",
    "summarise",
]
