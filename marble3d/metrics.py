"""Reading a replay back: the numbers that say whether a run was any good.

Everything here takes a `Replay` and nothing else. That is the point of section
26 of the brief made into a module boundary: if a metric needs a physics world
to compute, then selecting a seed needs a physics world, and the pipeline that
was supposed to select on one machine and render on another has an engine in
the middle of it again. A metric that reads the file is a metric a curation
pass can run on a thousand files without a simulator.

`revolutions` is the one that carries the most weight, because it is the
measurement the physics lab used to reject the old architecture: the production
2D bowl managed a median of 0.46 revolutions before a racer drained and the
three prototypes managed 4.1 to 6.3. It is the difference between a marble that
orbits and a marble that falls in a hole.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from marble3d.replay import Replay, STATE_FINISHED

__all__ = ["Revolutions", "revolutions", "residence", "speed_profile", "summarise"]


@dataclass(frozen=True)
class Revolutions:
    marble_id: int
    turns: float
    seconds: float
    peak_radius: float
    entry_radius: float


def _axis_of(replay: Replay, module_id: str) -> tuple[float, float]:
    """The horizontal position of a module's own origin, from the replay.

    A bowl's axis is its module origin, and the module's world transform is in
    the file - so this needs neither the module class nor a machine, which is
    what makes the whole of this module importable without the engine.
    """
    for module in replay.machine.get("modules", []):
        if module.get("id") == module_id:
            position = module.get("transform", {}).get("position", [0.0, 0.0, 0.0])
            return (float(position[0]), float(position[2]))
    raise KeyError(f"replay has no module {module_id!r}; it has "
                   f"{[m.get('id') for m in replay.machine.get('modules', [])]}")


def revolutions(replay: Replay, module_id: str = "bowl") -> list[Revolutions]:
    """How far around the bowl each marble actually went, in turns.

    The unwrapped azimuth about the module's axis, accumulated only over the
    frames where the marble is inside that module and signed, so a marble that
    reverses direction after a collision has that subtracted rather than added.
    Counting absolute angle instead would let a marble rocking back and forth
    in one place report a dozen revolutions, which is the opposite of the thing
    being measured.
    """
    axis_x, axis_z = _axis_of(replay, module_id)
    accumulated: dict[int, float] = {}
    previous: dict[int, float] = {}
    seconds: dict[int, float] = {}
    peak: dict[int, float] = {}
    entry: dict[int, float] = {}
    step = 1.0 / replay.replay_fps

    for frame in replay.frames:
        for marble in frame.marbles:
            key = marble.marble_id
            if marble.module != module_id:
                previous.pop(key, None)
                continue
            dx = marble.position[0] - axis_x
            dz = marble.position[2] - axis_z
            radius = math.hypot(dx, dz)
            angle = math.atan2(dz, dx)
            if key not in accumulated:
                accumulated[key] = 0.0
                seconds[key] = 0.0
                peak[key] = radius
                entry[key] = radius
            else:
                if key in previous:
                    accumulated[key] += math.remainder(angle - previous[key], 2.0 * math.pi)
                    seconds[key] += step
            peak[key] = max(peak[key], radius)
            previous[key] = angle

    return [
        Revolutions(
            marble_id=key,
            turns=abs(accumulated[key]) / (2.0 * math.pi),
            seconds=seconds[key],
            peak_radius=peak[key],
            entry_radius=entry[key],
        )
        for key in sorted(accumulated)
    ]


def residence(replay: Replay) -> dict[str, dict[int, float]]:
    """Seconds each marble spent in each module, from the per-frame labels."""
    step = 1.0 / replay.replay_fps
    totals: dict[str, dict[int, float]] = {}
    for frame in replay.frames:
        for marble in frame.marbles:
            if not marble.module or marble.state == STATE_FINISHED:
                continue
            totals.setdefault(marble.module, {}).setdefault(marble.marble_id, 0.0)
            totals[marble.module][marble.marble_id] += step
    return totals


def speed_profile(replay: Replay) -> list[tuple[float, float, float]]:
    """(time, mean speed, top speed) over the marbles still running."""
    profile: list[tuple[float, float, float]] = []
    for frame in replay.frames:
        speeds = [
            math.dist(marble.velocity, (0.0, 0.0, 0.0))
            for marble in frame.marbles
            if marble.state != STATE_FINISHED
        ]
        if not speeds:
            continue
        profile.append((frame.time, sum(speeds) / len(speeds), max(speeds)))
    return profile


def entry_speeds(replay: Replay, module_id: str = "bowl") -> dict[int, float]:
    """Each marble's speed on the frame it first appears inside a module."""
    seen: dict[int, float] = {}
    for frame in replay.frames:
        for marble in frame.marbles:
            if marble.module == module_id and marble.marble_id not in seen:
                seen[marble.marble_id] = math.dist(marble.velocity, (0.0, 0.0, 0.0))
    return seen


def summarise(replay: Replay, bowl_id: str = "bowl") -> dict[str, Any]:
    """One row per run, for a batch table."""
    turns = revolutions(replay, bowl_id) if _has_module(replay, bowl_id) else []
    values = sorted(entry.turns for entry in turns)
    summary = replay.summary
    return {
        "seed": replay.seed,
        "finished": summary.get("finished"),
        "escaped": summary.get("escaped"),
        "unfinished": summary.get("unfinished"),
        "sim_seconds": summary.get("sim_seconds"),
        "wall_seconds": summary.get("wall_seconds"),
        "collisions": summary.get("collisions"),
        "top_speed": summary.get("top_speed"),
        "max_energy_rise": summary.get("max_energy_rise"),
        "worst_penetration": summary.get("worst_penetration"),
        "finish_order": summary.get("finish_order"),
        "revolutions_median": _median(values),
        "revolutions_min": values[0] if values else 0.0,
        "revolutions_max": values[-1] if values else 0.0,
        "digest": replay.digest(),
        "failure": summary.get("failure"),
    }


def _has_module(replay: Replay, module_id: str) -> bool:
    return any(module.get("id") == module_id for module in replay.machine.get("modules", []))


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])
