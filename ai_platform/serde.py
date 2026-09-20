"""One JSON encoder for the whole control plane, and no framework behind it.

Every structure in `ai_platform/` and `knowledge/company_os/` is a frozen
dataclass, and every one of them has to survive a round trip through a file
that a human, a diff and the next session can all read. That needs exactly
three things: a recursive encoder that knows dataclasses, enums and dates; a
canonical dump so two equal records produce two identical files; and a
fingerprint so a manifest can be used as a cache key.

Canonical means `sort_keys=True` and sorted set members. It is what makes a
record's file byte-stable across sessions, which is what makes git diffs of the
knowledge store mean something.

Decoding is deliberately *not* generic. Each record class writes its own
`from_dict`, because a reader with no context can follow fifteen explicit lines
faster than one reflective coercion table.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import enum
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def to_jsonable(value: Any) -> Any:
    """Convert dataclasses, enums, dates and containers to JSON-native types."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_jsonable(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, enum.Enum):
        return to_jsonable(value.value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(k): to_jsonable(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))}
    if isinstance(value, (set, frozenset)):
        return [to_jsonable(v) for v in sorted(value, key=str)]
    if isinstance(value, (list, tuple)):
        return [to_jsonable(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"not JSON-encodable: {type(value).__name__}")


def dumps(value: Any) -> str:
    """Canonical, diff-stable JSON text with a trailing newline."""
    return json.dumps(to_jsonable(value), sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def fingerprint(value: Any) -> str:
    """A short stable digest of `value`, for cache keys and change detection.

    Sixteen hex characters of SHA-256 over the canonical form: collision-proof
    enough for a store that will hold thousands of records, short enough to sit
    inline in a usage record.
    """
    canonical = json.dumps(
        to_jsonable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dumps(value), encoding="utf-8")
    return path


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def as_date(value: Any, field: str) -> dt.date:
    """Accept a date or an ISO-8601 date string; reject anything else."""
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        return dt.date.fromisoformat(value)
    raise TypeError(f"{field}: expected a date or ISO date string, got {value!r}")


def as_opt_date(value: Any, field: str) -> dt.date | None:
    return None if value is None else as_date(value, field)


def as_tuple(value: Any) -> tuple[str, ...]:
    """Normalise an optional sequence of strings into a tuple, preserving order."""
    if value is None:
        return ()
    if isinstance(value, str):
        raise TypeError(f"expected a sequence of strings, got the string {value!r}")
    return tuple(str(item) for item in value)
