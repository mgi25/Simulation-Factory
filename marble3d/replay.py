"""The `marble3d` replay: a run, written down so it never has to be run again.

Deliberately **not** the production race replay schema, and not the lab's
either. `replay/` describes a race - ranks, checkpoints, a course made of
pieces - and this describes rigid bodies in a machine. Widening one to carry
the other would mean either changing a schema a shipped renderer reads, or
writing marble data into fields that mean something else. So this is a separate
format with its own name in its own field, and a reader can tell in one line
which kind of file it has.

## What it is for

Section 26 of the brief: once a seed is selected, the replay is the authority
and the renderer never re-simulates. That is not a convenience, it is the load
-bearing answer to the one thing the lab could not settle - whether Bullet is
deterministic *across machines*. If the pipeline selects a seed on one machine
and renders it on another by re-simulating, cross-machine determinism is a
correctness requirement and an unproven one. If it selects a seed, writes this
file, and ships the file, the renderer draws transforms and the question stops
being on the critical path.

So the file has to be sufficient on its own. It carries the machine's geometry
and every module's parameters, the static properties of every marble, the
physics settings that produced it, the pose *and* the velocities of every
marble at 60 Hz, the pose of every moving part, the events, and a summary.
Nothing a renderer needs is left to be recomputed.

## The digest

Every file carries a SHA-256 over the raw IEEE-754 bytes of the sampled state,
taken **before** the numbers are rounded for storage. That is what determinism
is judged on. Comparing the rounded JSON would answer a weaker question -
whether two runs agree to six decimal places - and a physics engine can diverge
in the sixteenth decimal on tick one and still agree to six places at tick two
hundred while being on a completely different trajectory by tick two thousand.
The digest cannot be fooled that way.

## Why velocities are stored

A renderer that only has positions has to difference them to get motion blur,
a camera lead or a squash, and differencing a 60 Hz signal amplifies exactly
the rounding this file applies. The velocities are what the engine had. They
cost a third of the file and they mean the renderer never has to reconstruct
physics from geometry.
"""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "MARBLE3D_FORMAT",
    "MARBLE3D_VERSION",
    "MarbleSample",
    "Frame",
    "Event",
    "MarbleInfo",
    "Replay",
    "write_replay",
    "read_replay",
]

MARBLE3D_FORMAT = "marble3d"
MARBLE3D_VERSION = 1

# Six decimals in world units is a micrometre at engine scale and 40 nanometres
# on the toy this models - four orders below anything a renderer can show and
# two below the collision margin. The digest, not this, is what determinism is
# judged on.
DECIMALS = 6

STATE_QUEUED = "queued"
STATE_RUNNING = "running"
STATE_FINISHED = "finished"
STATE_ESCAPED = "escaped"

AIRBORNE = ""


@dataclass(frozen=True)
class MarbleSample:
    marble_id: int
    position: tuple[float, float, float]
    orientation: tuple[float, float, float, float]   # x y z w, Bullet's order
    velocity: tuple[float, float, float]
    spin: tuple[float, float, float]                 # angular velocity, rad/s
    module: str
    state: str


@dataclass(frozen=True)
class Frame:
    time: float
    marbles: tuple[MarbleSample, ...]
    # Moving parts, by "module.actuator" name. Present so a renderer can draw a
    # gate or a paddle without evaluating an actuator - or owning one.
    actuators: dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]] = (
        field(default_factory=dict)
    )


@dataclass(frozen=True)
class Event:
    time: float
    kind: str
    data: dict[str, Any]


@dataclass(frozen=True)
class MarbleInfo:
    """What is true of a marble for the whole run, written down once."""

    marble_id: int
    radius: float
    mass: float
    start_index: int

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.marble_id,
            "radius": self.radius,
            "mass": self.mass,
            "start_index": self.start_index,
        }


@dataclass
class Replay:
    seed: int
    physics_hz: int
    replay_fps: int
    units: dict[str, Any]
    config: dict[str, Any]
    machine: dict[str, Any]
    marbles: list[MarbleInfo] = field(default_factory=list)
    frames: list[Frame] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)

    # --- the digest ------------------------------------------------------

    def digest(self) -> str:
        """SHA-256 of every sampled float, from its raw bytes.

        Position, orientation, velocity and spin are included; the module name
        and the state are not, because both are derived from the numbers and
        hashing them would only make the digest agree with itself more slowly.
        """
        hasher = hashlib.sha256()
        for frame in self.frames:
            hasher.update(struct.pack("<d", frame.time))
            for marble in frame.marbles:
                hasher.update(struct.pack("<i", marble.marble_id))
                hasher.update(struct.pack("<3d", *marble.position))
                hasher.update(struct.pack("<4d", *marble.orientation))
                hasher.update(struct.pack("<3d", *marble.velocity))
                hasher.update(struct.pack("<3d", *marble.spin))
        return hasher.hexdigest()

    def event_digest(self) -> str:
        """A separate hash over the event stream, kinds and order included.

        Two runs can agree on every sampled pose and still disagree about which
        pair of marbles touched first between two samples, so the event order
        is checked as its own thing rather than being assumed to follow.
        """
        hasher = hashlib.sha256()
        for event in self.events:
            hasher.update(struct.pack("<d", event.time))
            hasher.update(event.kind.encode("utf-8"))
            hasher.update(json.dumps(event.data, sort_keys=True).encode("utf-8"))
        return hasher.hexdigest()

    # --- serialisation ---------------------------------------------------

    def to_json(self) -> dict[str, Any]:
        return {
            "format": MARBLE3D_FORMAT,
            "version": MARBLE3D_VERSION,
            "seed": self.seed,
            "physics_hz": self.physics_hz,
            "replay_fps": self.replay_fps,
            "digest": self.digest(),
            "event_digest": self.event_digest(),
            "units": self.units,
            "config": self.config,
            "environment": self.environment,
            "machine": self.machine,
            "marbles": [marble.to_json() for marble in self.marbles],
            "frames": [
                {
                    "t": round(frame.time, DECIMALS),
                    "marbles": [
                        {
                            "id": marble.marble_id,
                            "p": [round(value, DECIMALS) for value in marble.position],
                            "q": [round(value, DECIMALS) for value in marble.orientation],
                            "v": [round(value, DECIMALS) for value in marble.velocity],
                            "w": [round(value, DECIMALS) for value in marble.spin],
                            "in": marble.module,
                            "s": marble.state,
                        }
                        for marble in frame.marbles
                    ],
                    "actuators": {
                        name: {
                            "p": [round(value, DECIMALS) for value in pose[0]],
                            "q": [round(value, DECIMALS) for value in pose[1]],
                        }
                        for name, pose in frame.actuators.items()
                    },
                }
                for frame in self.frames
            ],
            "events": [
                {"t": round(event.time, DECIMALS), "kind": event.kind, **event.data}
                for event in self.events
            ],
            "summary": self.summary,
        }


def write_replay(replay: Replay, path: str) -> str:
    """Write one run as JSON. No timestamps, no paths: same input, same bytes."""
    payload = json.dumps(replay.to_json(), separators=(",", ":"), sort_keys=False)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
        handle.write("\n")
    return path


def read_replay(path: str) -> Replay:
    with open(path, "r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if raw.get("format") != MARBLE3D_FORMAT:
        raise ValueError(
            f"{path}: format {raw.get('format')!r}, expected {MARBLE3D_FORMAT!r}. "
            "This is not a marble3d replay - the race replay schema is a different file."
        )
    if int(raw.get("version", 0)) != MARBLE3D_VERSION:
        raise ValueError(f"{path}: marble3d replay version {raw.get('version')!r}, expected {MARBLE3D_VERSION}")

    frames = [
        Frame(
            time=float(frame["t"]),
            marbles=tuple(
                MarbleSample(
                    marble_id=int(marble["id"]),
                    position=tuple(float(value) for value in marble["p"]),
                    orientation=tuple(float(value) for value in marble["q"]),
                    velocity=tuple(float(value) for value in marble["v"]),
                    spin=tuple(float(value) for value in marble["w"]),
                    module=str(marble.get("in", AIRBORNE)),
                    state=str(marble.get("s", STATE_RUNNING)),
                )
                for marble in frame["marbles"]
            ),
            actuators={
                name: (
                    tuple(float(value) for value in pose["p"]),
                    tuple(float(value) for value in pose["q"]),
                )
                for name, pose in frame.get("actuators", {}).items()
            },
        )
        for frame in raw["frames"]
    ]
    events = [
        Event(
            time=float(event["t"]),
            kind=str(event["kind"]),
            data={key: value for key, value in event.items() if key not in ("t", "kind")},
        )
        for event in raw["events"]
    ]
    replay = Replay(
        seed=int(raw["seed"]),
        physics_hz=int(raw["physics_hz"]),
        replay_fps=int(raw["replay_fps"]),
        units=dict(raw.get("units", {})),
        config=dict(raw.get("config", {})),
        machine=dict(raw.get("machine", {})),
        marbles=[
            MarbleInfo(
                marble_id=int(marble["id"]),
                radius=float(marble["radius"]),
                mass=float(marble["mass"]),
                start_index=int(marble.get("start_index", marble["id"])),
            )
            for marble in raw.get("marbles", [])
        ],
        frames=frames,
        events=events,
        summary=dict(raw.get("summary", {})),
        environment=dict(raw.get("environment", {})),
    )
    replay.summary.setdefault("stored_digest", raw.get("digest", ""))
    replay.summary.setdefault("stored_event_digest", raw.get("event_digest", ""))
    return replay


def digest_of(frames: Iterable[Frame]) -> str:
    """The digest of a bare frame sequence, for tests that never write a file."""
    return Replay(0, 0, 0, {}, {}, {}, frames=list(frames)).digest()


def poses_at(replay: Replay, frame_index: int) -> dict[int, tuple[Sequence[float], Sequence[float]]]:
    """Marble poses at one frame, which is all a renderer actually needs."""
    frame = replay.frames[frame_index]
    return {marble.marble_id: (marble.position, marble.orientation) for marble in frame.marbles}
