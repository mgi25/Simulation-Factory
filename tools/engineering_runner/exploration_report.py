"""What the stored receipts can honestly say about repository exploration.

## The measurement this milestone opens with

The brief asks to measure historical sessions before building anything. What
is actually stored, for every session this company has ever run, is one
`receipt.json` per developer attempt (`usage.model_turns`, `usage.cache_hits`,
`usage.cache_creation_units`, `files_changed`) and one runner-written
`session.json` per stage otherwise (reviewer, gate). Neither is a transcript:
`tools/engineering_runner/backends.py` runs the coding CLI with
`--output-format json`, which returns one final result envelope, so no stored
session anywhere names which file it read or what it searched for. This
module reads exactly what is there and refuses to invent the rest - see
`company.efficiency.budget`'s `repo_file_reads` / `repo_searches` dimensions,
declared UNAVAILABLE for the same reason.

## Reliability, per field

- `model_turns`, `cache_read_units`, `cache_creation_units`, `output_units`,
  `cost_usd`: RELIABLE when `unreliable_metrics` is empty for that session,
  PARTIAL (recorded but flagged) otherwise. The normaliser that produces
  `unreliable_metrics` is `tools/engineering_runner/backends.py`'s
  `normalise_claude_usage`.
- `files_touched`: RELIABLE - measured from git by `evidence.py`, not
  self-reported.
- anything about *which* files were read, or how many times, or what was
  searched for: UNAVAILABLE. A reviewer's own `evidence` list sometimes names
  a grep or a full-file read in prose (see `briefs.py`'s
  `REVIEW_REPORT_FIELDS`), but that is the model's self-report, not a
  measurement, and this module does not parse it into a count - doing so
  would launder an unreliable number into one that looks reliable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


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
    path: Path, *, label: str, role: str
) -> AttemptMeasurement | None:
    """A stage's runner-written `session.json`, used when no receipt exists."""
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
        files_touched=None,
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
    """Walk known runner-state directories for every `receipt.json` / `session.json`.

    Each `run_state_dirs` entry is a `runner_dir` (`config.py`'s term for
    where `tools/engineering_runner/queue.py`'s `RunStore` writes leases, run
    records and session transcripts) - in every stored instance on this
    machine, an operator-chosen path outside this repository and outside
    git, though nothing in `config.py` requires that. A missing directory is
    skipped rather than raised: this is measurement over whatever evidence a
    machine happens to hold, not a required input.
    """
    found: list[AttemptMeasurement] = []
    for base in run_state_dirs:
        if not base.is_dir():
            continue
        receipted_dirs: set[Path] = set()
        for receipt_path in sorted(base.rglob("receipt.json")):
            stage_dir = receipt_path.parent
            role = _role_from_dirname(stage_dir.name)
            label = str(stage_dir.relative_to(base)).replace("\\", "/")
            measurement = measure_receipt(receipt_path, label=label, role=role)
            if measurement is not None:
                found.append(measurement)
                receipted_dirs.add(stage_dir)
        for session_path in sorted(base.rglob("session.json")):
            stage_dir = session_path.parent
            if stage_dir in receipted_dirs:
                continue
            role = _role_from_dirname(stage_dir.name)
            label = str(stage_dir.relative_to(base)).replace("\\", "/")
            measurement = measure_session_telemetry(session_path, label=label, role=role)
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
    "discover_measurements",
    "measure_receipt",
    "measure_session_telemetry",
    "summarise",
]
