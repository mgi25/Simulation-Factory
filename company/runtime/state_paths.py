"""Shared primitives for append-only state under a caller-supplied directory.

Two histories now live under an explicit runtime state directory - the resource
usage ledger and the session execution history - and both need the same three
things: a filesystem-safe directory name per task, the next sequence number,
and a write that cannot overwrite a record that already exists.

Constitution rule 15 stores a canonical fact once. That applies to the code
that stores it: a second copy of the exclusive-create loop is a second place
for an overwrite bug to appear.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

from company.validation.errors import CompanyOSError


class StateStoreError(CompanyOSError):
    """A runtime state directory is missing, malformed, or unwritable."""


RECORD_NAME = re.compile(r"(?P<sequence>[0-9]{6,})\.json")


def task_directory_name(task_id: str) -> str:
    """A collision-free directory name that is still readable in a diff."""
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-.")[:48] or "task"
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def next_sequence(directory: Path) -> int:
    sequences = [
        int(match.group("sequence"))
        for path in directory.glob("*.json")
        if (match := RECORD_NAME.fullmatch(path.name))
    ]
    return max(sequences, default=0) + 1


def record_sort_key(path: Path) -> tuple[int, str]:
    match = RECORD_NAME.fullmatch(path.name)
    return (int(match.group("sequence")) if match else 2**63, path.name)


def sorted_records(directory: Path) -> tuple[Path, ...]:
    if not directory.exists():
        return ()
    return tuple(sorted(directory.glob("*.json"), key=record_sort_key))


def append_json_bytes(directory: Path, payload: bytes) -> Path:
    """Write `payload` to the next unused NNNNNN.json in `directory`.

    An existing record is never opened for write: the file is created with
    `O_EXCL`, and a name already taken advances the sequence rather than
    replacing anything. That is the whole no-silent-overwrite guarantee, and
    it is enforced by the filesystem rather than by a check-then-write race.
    """
    directory.mkdir(parents=True, exist_ok=True)
    sequence = next_sequence(directory)
    while True:
        path = directory / f"{sequence:06d}.json"
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
            )
        except FileExistsError:
            sequence += 1
            continue
        try:
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise StateStoreError(f"short write while appending {path}")
                offset += written
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path


def create_json_bytes_at_sequence(
    directory: Path, payload: bytes, sequence: int
) -> Path:
    """Create one exact sequenced record, refusing an existing slot.

    Paired append-only histories use this to give two records the same attempt
    identity without ever opening either record for overwrite.
    """
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise StateStoreError("record sequence must be a positive integer")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{sequence:06d}.json"
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0),
        )
    except FileExistsError as exc:
        raise StateStoreError(f"append-only record already exists: {path}") from exc
    try:
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise StateStoreError(f"short write while appending {path}")
            offset += written
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return path


def sequence_of(path: Path) -> int:
    match = RECORD_NAME.fullmatch(path.name)
    if match is None:
        raise StateStoreError(f"{path}: not a sequenced state record")
    return int(match.group("sequence"))
