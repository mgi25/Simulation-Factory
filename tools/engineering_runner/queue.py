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

## The lease is a directory, and owning it is one syscall

    <runner_dir>/runs/<work-order>/lease-000001/lease.json

Ownership of a work order is ownership of generation N, and generation N is
owned by whoever `os.mkdir`s `lease-<N>`. That call is atomic on every
supported platform: it creates the directory or it raises `FileExistsError`,
with nothing in between and no window for a second opinion. Exactly one
contender can create one name.

**This replaces an `O_EXCL` file, which was not enough.** `os.open(O_EXCL)`
creates the lease *empty* and the metadata is written after, so a contender
arriving in that gap read an unparseable file, concluded the holder was
broken, and took the lease a winner already held. Measured, eight threads
racing one never-before-seen work order produced four grants, not one. A
directory has no such gap: it is complete the instant it exists, and the
metadata inside it is a description of an ownership already held rather than
the thing that establishes it.

**Reclaiming is also a create, never an overwrite.** The old code decided a
lease was stale or released and then wrote over it - a check-then-act that
every contender passed at once, so a released lease had as many winners as
readers. Now a reclaimer creates the *next* generation. Everyone reads
generation G and everyone races to create G+1, and the filesystem picks one.

## The states a contender distinguishes, before it races

- **no lease at all** - generation 1 is free. Race for it.
- **held and fresh** - another runner is on it. `ClaimUnavailable`, and the
  watch loop moves to the next job. No race is entered.
- **held and stale** - the heartbeat is older than the lease window, so the
  holder crashed or was killed. Race for G+1, and record the reclamation,
  because "a run that never ended" and "a run that ended badly" are different
  facts and the outcome log should not merge them.
- **released** - the previous run finished. Race for G+1, silently.
- **unreadable** - there is a directory and no usable metadata inside it.
  This is *not* read as "therefore I won". A winner that has not yet written
  its metadata looks exactly like a crashed one, so the directory's own mtime
  decides: inside the lease window it is treated as **held** and the contender
  leaves, and only a generation that has sat without metadata for longer than
  a whole lease window is reclaimed. The safe answer is the one that refuses.

Losing the race is not a failure to handle later: `FileExistsError` from the
mkdir sends the contender back to re-read the state it raced on, where it now
finds a fresh holder and leaves. It never falls through to a claim.

Staleness is a heartbeat comparison rather than a liveness probe. Checking
whether a pid is alive is wrong across machines and wrong after pid reuse, and
a heartbeat that has stopped is the thing actually being asked about.

A `lease.json` sitting directly in the job directory is a lease written by the
runner that predates this layout. It is read as generation 0 - respected while
fresh, superseded by generation 1 - so an in-flight job from an older runner
is not claimed twice across the upgrade.

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
LEASE_DIR_PREFIX = "lease-"
OUTCOMES_DIR = "outcomes"
RUNS_DIR = "runs"

HELD = "held"
RELEASED = "released"

# How many times a contender that lost the mkdir will re-read and try again.
# Each loss means somebody else now holds the generation it wanted, so the
# re-read almost always ends in `ClaimUnavailable`; the bound exists so a
# pathological interleaving terminates rather than spinning.
_MAX_CLAIM_ATTEMPTS = 8

_RECORD_NAME = re.compile(r"(?P<sequence>[0-9]{6,})\.json")
_LEASE_DIR_NAME = re.compile(r"lease-(?P<generation>[0-9]{6,})$")


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
    # Which `lease-<N>` directory this lease owns. The heartbeat and the
    # release write inside it, so a runner that was superseded cannot write
    # over the lease of the runner that superseded it.
    generation: int = 0

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
            "generation": self.generation,
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
            generation=int(data.get("generation", 0) or 0),
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
        """Where the *current* generation's metadata is, held or not."""
        directory = self.job_dir(work_order_id)
        generation = _highest_generation(directory)
        return _lease_file(directory, generation)

    def lease(self, work_order_id: str) -> Lease | None:
        """The current generation's lease, or None if there is none to read."""
        directory = self.job_dir(work_order_id)
        generation = _highest_generation(directory)
        if generation == 0 and not _lease_file(directory, 0).is_file():
            return None
        found = _read_lease(directory, generation)
        return found[0]

    def acquire(
        self, work_order_id: str, *, lease_seconds: float, stage: str = ""
    ) -> tuple[Lease, str]:
        """Take the lease, or raise. Returns the lease and how it was obtained.

        The claim is the `os.mkdir` and nothing else. Everything before it is
        a decision about whether to enter the race, and everything after it is
        a description of a race already won.
        """
        from .errors import ClaimUnavailable  # local: keeps the error graph one-way

        directory = self.job_dir(work_order_id)
        directory.mkdir(parents=True, exist_ok=True)
        for _ in range(_MAX_CLAIM_ATTEMPTS):
            generation = _highest_generation(directory)
            how = self._verdict(
                directory, generation, lease_seconds=lease_seconds, refuse=ClaimUnavailable
            )
            claimed = directory / f"{LEASE_DIR_PREFIX}{generation + 1:06d}"
            try:
                claimed.mkdir()
            except FileExistsError:
                # Somebody else created the generation this contender was
                # racing for. Re-read: they are now the fresh holder and the
                # next pass leaves. Never fall through into a claim.
                continue
            now = utcnow()
            reclaimed_from = ""
            if "stale" in how:
                existing = _read_lease(directory, generation)[0]
                reclaimed_from = existing.runner_id if existing else ""
            lease = Lease(
                work_order_id=work_order_id,
                runner_id=self._runner_id,
                pid=os.getpid(),
                host=self._host,
                state=HELD,
                acquired_at=now.isoformat(),
                heartbeat_at=now.isoformat(),
                stage=stage,
                run_sequence=self.next_run_sequence(work_order_id),
                reclaimed_from=reclaimed_from,
                generation=generation + 1,
            )
            # Only now, and only by the owner: the directory already says who
            # won, so this file cannot change the answer, only describe it.
            write_json(claimed / LEASE_NAME, lease.to_dict())
            return lease, how
        raise ClaimUnavailable(
            f"{work_order_id}: lost the claim race {_MAX_CLAIM_ATTEMPTS} times; "
            "another runner is working this job"
        )

    def _verdict(
        self,
        directory: Path,
        generation: int,
        *,
        lease_seconds: float,
        refuse: type[Exception],
    ) -> str:
        """Whether the next generation may be raced for, and how to say so.

        Raises `refuse` when it may not. This reads; it never writes, and it
        never decides a winner - the mkdir that follows does that.
        """
        if generation == 0 and not _lease_file(directory, 0).is_file():
            return "took a new lease"
        existing, readable = _read_lease(directory, generation)
        now = utcnow()
        if not readable:
            # A winner writing its metadata and a winner that died before
            # writing it look identical from here, so age decides. Inside the
            # window the safe answer is that somebody holds it.
            age = _directory_age_s(directory, generation, now)
            if age < lease_seconds:
                raise refuse(
                    f"lease generation {generation} exists with no readable metadata "
                    f"({age:.0f}s old); another runner is claiming it"
                )
            return f"reclaimed an unreadable lease ({age:.0f}s without metadata)"
        if existing is not None and existing.state == HELD:
            age = existing.age_s(now)
            if age < lease_seconds:
                raise refuse(
                    f"{existing.work_order_id} is held by runner {existing.runner_id} on "
                    f"{existing.host} (pid {existing.pid}), last heartbeat "
                    f"{age:.0f}s ago"
                )
            return (
                f"reclaimed a stale lease from {existing.runner_id} "
                f"({age:.0f}s without a heartbeat)"
            )
        return "took a released lease"

    def heartbeat(self, lease: Lease, *, stage: str = "") -> Lease:
        updated = _with(lease, heartbeat_at=utcnow().isoformat(), stage=stage or lease.stage)
        write_json(self._owned_path(updated), updated.to_dict())
        return updated

    def release(self, lease: Lease) -> Lease:
        released = _with(lease, state=RELEASED, heartbeat_at=utcnow().isoformat())
        write_json(self._owned_path(released), released.to_dict())
        return released

    def _owned_path(self, lease: Lease) -> Path:
        """The lease file of the generation this lease owns, not the newest one.

        A runner whose lease was reclaimed as stale keeps running until it
        notices. Addressing its own generation means its heartbeats and its
        release land in a directory nobody reads any more, instead of over the
        metadata of the runner that superseded it.
        """
        return _lease_file(self.job_dir(lease.work_order_id), lease.generation)

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
            if not child.is_dir():
                continue
            lease, _ = _read_lease(child, _highest_generation(child))
            if lease is not None and lease.work_order_id:
                found.add(lease.work_order_id)
        return tuple(sorted(found))


def _lease_file(directory: Path, generation: int) -> Path:
    """Generation N's metadata file. Generation 0 is the pre-directory layout."""
    if generation <= 0:
        return directory / LEASE_NAME
    return directory / f"{LEASE_DIR_PREFIX}{generation:06d}" / LEASE_NAME


def _highest_generation(directory: Path) -> int:
    """The newest generation anybody has created here, or 0 for none.

    0 also covers the pre-directory layout, whose lease file sits directly in
    the job directory - so a job left in flight by an older runner is read,
    not ignored.
    """
    if not directory.is_dir():
        return 0
    generations = [
        int(match.group("generation"))
        for child in directory.iterdir()
        if child.is_dir() and (match := _LEASE_DIR_NAME.fullmatch(child.name))
    ]
    return max(generations, default=0)


def _read_lease(directory: Path, generation: int) -> tuple[Lease | None, bool]:
    """Generation N's lease, and whether it could be read at all.

    The second value is the one that matters at a claim: "no lease here" and
    "a lease I cannot parse" are different facts, and collapsing them is how
    an empty file came to mean "therefore I won".
    """
    path = _lease_file(directory, generation)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        return None, False
    if not isinstance(data, Mapping):
        return None, False
    lease = Lease.from_mapping(data)
    if generation and not lease.generation:
        lease = _with(lease, generation=generation)
    return lease, True


def _directory_age_s(directory: Path, generation: int, now: dt.datetime) -> float:
    """How long generation N's directory has existed, by the filesystem's clock.

    Its own mtime rather than a written timestamp, because the case this
    answers is precisely the one where nothing was written.
    """
    if generation <= 0:
        target = _lease_file(directory, generation)
    else:
        target = directory / f"{LEASE_DIR_PREFIX}{generation:06d}"
    try:
        modified = dt.datetime.fromtimestamp(target.stat().st_mtime, dt.timezone.utc)
    except OSError:
        return float("inf")
    return (now - modified).total_seconds()


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
    "LEASE_DIR_PREFIX",
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
