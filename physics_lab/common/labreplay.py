"""The lab time-series format: what a bowl run leaves behind.

Deliberately **not** the production race replay schema. The production schema
describes a race - ranks, checkpoints, finishing positions, a course made of
pieces - and this describes eight spheres in a bowl. Reusing it would mean
either widening it for an experiment that may be thrown away, or writing bowl
data into fields that mean something else. Neither is worth it, and the study
is over before anything downstream needs to read one of these.

One thing here is worth explaining. Every file carries a `digest` taken from
the raw IEEE-754 bytes of the sampled state, computed *before* the numbers are
rounded for storage. That is what the determinism investigation actually
compares. Comparing the rounded JSON would answer a weaker question - whether
two runs agree to nine decimal places - and a physics engine can fail
determinism in the sixteenth decimal on tick one and still be identical to nine
places at tick two hundred. The digest cannot be fooled that way.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from typing import Any, Iterable

__all__ = ["LabRun", "MarbleSample", "FrameSample", "LabEvent", "write_run", "read_run"]

LAB_REPLAY_VERSION = 1

# Enough to see a millimetre-scale divergence in the stored file. The digest,
# not this, is what determinism is judged on.
DECIMALS = 9

STATE_SURFACE = "surface"
STATE_FREE = "free"
STATE_DRAINED = "drained"
STATE_ESCAPED = "escaped"


@dataclass(frozen=True)
class MarbleSample:
    marble_id: int
    position: tuple[float, float, float]
    velocity: tuple[float, float, float]
    orientation: tuple[float, float, float, float]  # quaternion, x y z w
    spin: tuple[float, float, float]                # angular velocity, rad/s
    state: str


@dataclass(frozen=True)
class FrameSample:
    time: float
    marbles: tuple[MarbleSample, ...]


@dataclass(frozen=True)
class LabEvent:
    """Something that happened, at the tick it happened on.

    `kind` is one of a small closed set - collision, separated, landed,
    drained, escaped, failed - and the payload is whatever that kind needs.
    Kept as free-form data rather than a class per kind because the analysis
    reads them by kind and nothing else ever will.
    """

    time: float
    kind: str
    data: dict[str, Any]


@dataclass
class LabRun:
    approach: str
    seed: int
    physics_hz: int
    sample_hz: int
    benchmark: dict[str, Any]
    starts: list[dict[str, Any]]
    frames: list[FrameSample] = field(default_factory=list)
    events: list[LabEvent] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def digest(self) -> str:
        """A hash of every sampled float, from its raw bytes.

        Orientation and spin are included; state is not, because a state name
        is derived from the numbers and hashing it would only make the digest
        agree with itself more slowly.
        """
        hasher = hashlib.sha256()
        for frame in self.frames:
            hasher.update(struct.pack("<d", frame.time))
            for marble in frame.marbles:
                hasher.update(struct.pack("<i", marble.marble_id))
                hasher.update(struct.pack("<3d", *marble.position))
                hasher.update(struct.pack("<3d", *marble.velocity))
                hasher.update(struct.pack("<4d", *marble.orientation))
                hasher.update(struct.pack("<3d", *marble.spin))
        return hasher.hexdigest()

    def to_json(self) -> dict[str, Any]:
        return {
            "version": LAB_REPLAY_VERSION,
            "approach": self.approach,
            "seed": self.seed,
            "physics_hz": self.physics_hz,
            "sample_hz": self.sample_hz,
            "digest": self.digest(),
            "benchmark": self.benchmark,
            "starts": self.starts,
            "stats": self.stats,
            "frames": [
                {
                    "time": round(frame.time, DECIMALS),
                    "marbles": [
                        {
                            "id": marble.marble_id,
                            "position": [round(value, DECIMALS) for value in marble.position],
                            "velocity": [round(value, DECIMALS) for value in marble.velocity],
                            "orientation": [
                                round(value, DECIMALS) for value in marble.orientation
                            ],
                            "spin": [round(value, DECIMALS) for value in marble.spin],
                            "state": marble.state,
                        }
                        for marble in frame.marbles
                    ],
                }
                for frame in self.frames
            ],
            "events": [
                {"time": round(event.time, DECIMALS), "kind": event.kind, **event.data}
                for event in self.events
            ],
        }


def write_run(run: LabRun, path: str) -> str:
    """Write one run as JSON. No timestamps, no paths: same input, same bytes."""
    payload = json.dumps(run.to_json(), separators=(",", ":"), sort_keys=False)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")
    return path


def read_run(path: str) -> LabRun:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if int(raw.get("version", 0)) != LAB_REPLAY_VERSION:
        raise ValueError(f"{path}: lab replay version {raw.get('version')!r}, expected {LAB_REPLAY_VERSION}")
    frames = [
        FrameSample(
            time=float(frame["time"]),
            marbles=tuple(
                MarbleSample(
                    marble_id=int(marble["id"]),
                    position=tuple(float(value) for value in marble["position"]),
                    velocity=tuple(float(value) for value in marble["velocity"]),
                    orientation=tuple(float(value) for value in marble["orientation"]),
                    spin=tuple(float(value) for value in marble["spin"]),
                    state=str(marble["state"]),
                )
                for marble in frame["marbles"]
            ),
        )
        for frame in raw["frames"]
    ]
    events = [
        LabEvent(
            time=float(event["time"]),
            kind=str(event["kind"]),
            data={key: value for key, value in event.items() if key not in ("time", "kind")},
        )
        for event in raw["events"]
    ]
    run = LabRun(
        approach=str(raw["approach"]),
        seed=int(raw["seed"]),
        physics_hz=int(raw["physics_hz"]),
        sample_hz=int(raw["sample_hz"]),
        benchmark=dict(raw["benchmark"]),
        starts=list(raw["starts"]),
        frames=frames,
        events=events,
        stats=dict(raw.get("stats", {})),
    )
    run.stats.setdefault("stored_digest", raw.get("digest", ""))
    return run


def digest_of(frames: Iterable[FrameSample]) -> str:
    """The same hash `LabRun.digest` takes, for a bare frame sequence."""
    return LabRun("", 0, 0, 0, {}, [], list(frames)).digest()
