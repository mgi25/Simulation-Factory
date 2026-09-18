"""The runner's own state: who is working on what, and what happened.

There is deliberately no work queue here. Company OS already holds one - a
job's `JobState` is exactly "what does this work order need next" - and a
second list of pending items would be a second source of truth that can
disagree with the first. The runner reads the lifecycle and acts on it.

What the runner does need, and Company OS must not hold, is execution-plane
state: which process is currently working a job, whether the last run finished
or died, and where the transcripts went. That lives here.

    <runner_dir>/runs/<work-order>/lease.json          the current holder
    <runner_dir>/runs/<work-order>/outcomes/000001.json append-only history
    <runner_dir>/runs/<work-order>/run-000001/...       one run's artifacts

## The lease, and the three states it distinguishes

A lease file is created with `O_EXCL`, so two processes racing for the same
work order cannot both believe they won - the filesystem decides, not a
check-then-write. Once it exists it is read rather than assumed:

- **held and fresh** - another runner is on it. `ClaimUnavailable`, and the
  watch loop moves to the next job.
- **held and stale** - the heartbeat is older than the lease window, so the
  holder crashed or was killed. The lease is reclaimed and the reclamation is
  recorded, because "a run that never ended" and "a run that ended badly" are
  different facts and the outcome log should not merge them.
- **released** - the previous run finished. Reclaimed silently.

Staleness is a heartbeat comparison rather than a liveness probe. Checking
whether a pid is alive is wrong across machines and wrong after pid reuse, and
a heartbeat that has stopped is the thing actually being asked about.

## Why the outcome log is append-only and the lease is not

An outcome is history: it says a run happened and how it ended, and rewriting
one would erase a fact. A lease is a current position: it has no history worth
keeping, and appending to it would mean reading a directory to answer "is
anyone working on this right now". `append_json` is the same exclusive-create
loop `company/runtime/state_paths.py` uses, restated because this package may
not import it.

## Directory names mirror Company OS

`task_directory_name` produces the same `<slug>-<digest12>` shape
`company/runtime/state_paths.py` does, so an operator holding a Company OS
record directory can find the runner's directory for the same work order
without a lookup table. The algorithm is restated, not imported, for the same
reason everything else here is.
"""

from __future__ import annotations

from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import socket
from typing import Any, Mapping
import uuid


LEASE_NAME = "lease.json"
OUTCOMES_DIR = "outcomes"
RUNS_DIR = "runs"

HELD = "held"
RELEASED = "released"

_RECORD_NAME = re.compile(r"(?P<sequence>[0-9]{6,})\.json")


def task_directory_name(task_id: str) -> str:
    """A filesystem-safe directory name that is still readable in a listing."""
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", task_id).strip("-.")[:48] or "task"
    digest = hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:12]
    return f"{slug}-{digest}"


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def append_json(directory: Path, payload: Mapping[str, Any]) -> Path:
    """Write the next `NNNNNN.json` in `directory`, never replacing one."""
    directory.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    sequence = _next_sequence(directory)
    while True:
        path = directory / f"{sequence:06d}.json"
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            )
        except FileExistsError:
            sequence += 1
            continue
        try:
            offset = 0
            while offset < len(body):
                offset += os.write(descriptor, body[offset:])
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return path


def write_json(path: Path, payload: Mapping[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def write_text(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@dataclass(frozen=True)
class Lease:
    """Who holds a work order right now, and since when."""

    work_order_id: str
    runner_id: str
    pid: int
    host: str
    state: str
    acquired_at: str
    heartbeat_at: str
    stage: str = ""
    run_sequence: int = 0
    reclaimed_from: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "work_order_id": self.work_order_id,
            "runner_id": self.runner_id,
            "pid": self.pid,
            "host": self.host,
            "state": self.state,
            "acquired_at": self.acquired_at,
            "heartbeat_at": self.heartbeat_at,
            "stage": self.stage,
            "run_sequence": self.run_sequence,
            "reclaimed_from": self.reclaimed_from,
        }

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "Lease":
        return cls(
            work_order_id=str(data.get("work_order_id", "")),
            runner_id=str(data.get("runner_id", "")),
            pid=int(data.get("pid", 0) or 0),
            host=str(data.get("host", "")),
            state=str(data.get("state", HELD)),
            acquired_at=str(data.get("acquired_at", "")),
            heartbeat_at=str(data.get("heartbeat_at", "")),
            stage=str(data.get("stage", "")),
            run_sequence=int(data.get("run_sequence", 0) or 0),
            reclaimed_from=str(data.get("reclaimed_from", "")),
        )

    def age_s(self, now: dt.datetime | None = None) -> float:
        try:
            beat = dt.datetime.fromisoformat(self.heartbeat_at)
        except ValueError:
            return float("inf")
        if beat.tzinfo is None:
            beat = beat.replace(tzinfo=dt.timezone.utc)
        return ((now or utcnow()) - beat).total_seconds()


class RunStore:
    """Leases, run directories and the outcome log, under one runner directory."""

    def __init__(self, runner_dir: Path, *, runner_id: str = "") -> None:
        self._root = Path(runner_dir).resolve()
        self._runner_id = runner_id or str(uuid.uuid4())
        self._host = socket.gethostname()

    @property
    def root(self) -> Path:
        return self._root

    @property
    def runner_id(self) -> str:
        return self._runner_id

    def job_dir(self, work_order_id: str) -> Path:
        return self._root / RUNS_DIR / task_directory_name(work_order_id)

    def lease_path(self, work_order_id: str) -> Path:
        return self.job_dir(work_order_id) / LEASE_NAME

    def lease(self, work_order_id: str) -> Lease | None:
        path = self.lease_path(work_order_id)
        if not path.is_file():
            return None
        try:
            return Lease.from_mapping(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, ValueError, OSError):
            return None

    def acquire(
        self, work_order_id: str, *, lease_seconds: float, stage: str = ""
    ) -> tuple[Lease, str]:
        """Take the lease, or raise. Returns the lease and how it was obtained."""
        from .errors import ClaimUnavailable  # local: keeps the error graph one-way

        directory = self.job_dir(work_order_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / LEASE_NAME
        now = utcnow()
        fresh = Lease(
            work_order_id=work_order_id,
            runner_id=self._runner_id,
            pid=os.getpid(),
            host=self._host,
            state=HELD,
            acquired_at=now.isoformat(),
            heartbeat_at=now.isoformat(),
            stage=stage,
            run_sequence=self.next_run_sequence(work_order_id),
        )
        try:
            descriptor = os.open(
                path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
            )
        except FileExistsError:
            existing = self.lease(work_order_id)
            if existing is None:
                how = "reclaimed an unreadable lease"
            elif existing.state == HELD and existing.age_s(now) < lease_seconds:
                raise ClaimUnavailable(
                    f"{work_order_id} is held by runner {existing.runner_id} on "
                    f"{existing.host} (pid {existing.pid}), last heartbeat "
                    f"{existing.age_s(now):.0f}s ago"
                )
            elif existing.state == HELD:
                how = (
                    f"reclaimed a stale lease from {existing.runner_id} "
                    f"({existing.age_s(now):.0f}s without a heartbeat)"
                )
                fresh = _with(fresh, reclaimed_from=existing.runner_id)
            else:
                how = "took a released lease"
            write_json(path, fresh.to_dict())
            return fresh, how
        else:
            os.close(descriptor)
            write_json(path, fresh.to_dict())
            return fresh, "took a new lease"

    def heartbeat(self, lease: Lease, *, stage: str = "") -> Lease:
        updated = _with(lease, heartbeat_at=utcnow().isoformat(), stage=stage or lease.stage)
        write_json(self.lease_path(lease.work_order_id), updated.to_dict())
        return updated

    def release(self, lease: Lease) -> Lease:
        released = _with(lease, state=RELEASED, heartbeat_at=utcnow().isoformat())
        write_json(self.lease_path(lease.work_order_id), released.to_dict())
        return released

    def next_run_sequence(self, work_order_id: str) -> int:
        directory = self.job_dir(work_order_id) / OUTCOMES_DIR
        return _next_sequence(directory)

    def run_dir(self, work_order_id: str, sequence: int) -> Path:
        return self.job_dir(work_order_id) / f"run-{sequence:06d}"

    def record_outcome(self, payload: Mapping[str, Any]) -> Path:
        work_order_id = str(payload.get("work_order_id", ""))
        return append_json(self.job_dir(work_order_id) / OUTCOMES_DIR, payload)

    def outcomes(self, work_order_id: str) -> tuple[dict[str, Any], ...]:
        directory = self.job_dir(work_order_id) / OUTCOMES_DIR
        if not directory.is_dir():
            return ()
        records: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json"), key=_sequence_key):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, Mapping):
                records.append(dict(data))
        return tuple(records)

    def known_work_orders(self) -> tuple[str, ...]:
        directory = self._root / RUNS_DIR
        if not directory.is_dir():
            return ()
        found: set[str] = set()
        for child in directory.iterdir():
            lease_file = child / LEASE_NAME
            if not lease_file.is_file():
                continue
            try:
                data = json.loads(lease_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(data, Mapping) and data.get("work_order_id"):
                found.add(str(data["work_order_id"]))
        return tuple(sorted(found))


def _with(lease: Lease, **changes: Any) -> Lease:
    data = lease.to_dict()
    data.update(changes)
    return Lease.from_mapping(data)


def _next_sequence(directory: Path) -> int:
    if not directory.is_dir():
        return 1
    sequences = [
        int(match.group("sequence"))
        for path in directory.glob("*.json")
        if (match := _RECORD_NAME.fullmatch(path.name))
    ]
    return max(sequences, default=0) + 1


def _sequence_key(path: Path) -> tuple[int, str]:
    match = _RECORD_NAME.fullmatch(path.name)
    return (int(match.group("sequence")) if match else 2**63, path.name)


__all__ = [
    "HELD",
    "LEASE_NAME",
    "OUTCOMES_DIR",
    "RELEASED",
    "RUNS_DIR",
    "Lease",
    "RunStore",
    "append_json",
    "task_directory_name",
    "utcnow",
    "write_json",
    "write_text",
]
