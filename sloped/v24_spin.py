"""Is the marble spinning, and can the picture say so?

**The diagnosis first, because it decides whether there is anything to draw.**
In the delivered V22.1 film the marbles look like they slide - most obviously
inside the ShuffleFloor mixer, where eight balls are stirred by a rotor and not
one of them appears to turn. The tempting reading is that the solver is not
rotating them. It is: this module measures the replay and finds every marble
turning, in every phase, at speeds that on the descent pass ninety radians a
second. `godot/scripts/sloped_race_scene.gd` then applies that rotation
correctly, straight onto the node it draws.

What fails is the *surface*. A uniformly coloured sphere is invariant under
every rotation there is, so a correct quaternion applied to a correct mesh
produces a picture in which rotation is unobservable in principle. The fix is
therefore a marking on the body and nothing else, and the number that says
whether a marking works is not an angular speed - it is how much of the
**visible face** changes from frame to frame, which is what `visible_change`
measures here and what a plain sphere scores exactly zero on.

**Every constant that shapes a marker is read out of the GDScript.**
`racer_visual.gd` is the one that paints the texture the renderer uses; a
second copy of `BAND_HALF` in Python would be a number that could drift away
from the thing it claims to describe while every test still passed. So the
values are parsed from the source file, and `coverage()` below is a twin of the
GDScript function that `tests/test_sloped_v24_spin.py` holds to it.

Nothing in this module writes a replay, and nothing in it can change one.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

import numpy as np

RACER_VISUAL = os.path.join(
    "godot", "assets", "marble_machine", "racers", "racer_visual.gd"
)

#: The phases the diagnosis is reported over, in **replay** seconds. They are
#: named for what the machine is doing, and the mixer is first because the
#: mixer is where the sliding was reported.
PHASES: tuple[tuple[str, float, float], ...] = (
    ("mixer", 1.00, 5.50),
    ("spin-down", 5.50, 6.00),
    ("release", 6.00, 7.00),
    ("descent", 7.00, 12.00),
    ("obstacle", 13.80, 15.10),
    ("fork", 15.10, 16.73),
    ("rolling", 17.00, 19.00),
    ("final", 19.00, 21.00),
)


# --- the marker, as the renderer defines it -------------------------------


def _source(path: str = RACER_VISUAL) -> str:
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def _scalar(text: str, name: str) -> float:
    found = re.search(rf"^const {name} := ([-0-9.]+)", text, re.M)
    if found is None:
        raise ValueError(f"racer_visual.gd has no const {name}")
    return float(found.group(1))


def _vector(text: str, name: str) -> np.ndarray:
    found = re.search(
        rf"^const {name} := Vector3\(([-0-9.]+), ([-0-9.]+), ([-0-9.]+)\)", text, re.M
    )
    if found is None:
        raise ValueError(f"racer_visual.gd has no Vector3 const {name}")
    raw = np.array([float(value) for value in found.groups()], dtype=float)
    return raw / np.linalg.norm(raw)


@dataclass(frozen=True)
class Marker:
    """The marker shapes, exactly as `racer_visual.gd` paints them."""

    ribbon_normal: np.ndarray
    meridian_normal: np.ndarray
    crescent_axis: np.ndarray
    crescent_bite: np.ndarray
    band_half: float
    meridian_half: float
    meridian_tilt: float
    crescent_cos: float
    crescent_bite_cos: float
    edge_soft: float
    tint: float

    @classmethod
    def load(cls, path: str = RACER_VISUAL) -> "Marker":
        text = _source(path)
        return cls(
            ribbon_normal=_vector(text, "RIBBON_NORMAL"),
            meridian_normal=_vector(text, "MERIDIAN_NORMAL"),
            crescent_axis=_vector(text, "CRESCENT_AXIS"),
            crescent_bite=_vector(text, "CRESCENT_BITE"),
            band_half=_scalar(text, "BAND_HALF"),
            meridian_half=_scalar(text, "MERIDIAN_HALF"),
            meridian_tilt=_scalar(text, "MERIDIAN_TILT"),
            crescent_cos=_scalar(text, "CRESCENT_COS"),
            crescent_bite_cos=_scalar(text, "CRESCENT_BITE_COS"),
            edge_soft=_scalar(text, "EDGE_SOFT"),
            tint=_scalar(text, "MARKER_TINT"),
        )


APPEARANCES = ("solid", "ribbon", "crescent", "meridian")


def _smoothstep(low: float, high: float, value: np.ndarray) -> np.ndarray:
    span = max(high - low, 1.0e-9)
    t = np.clip((value - low) / span, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def coverage(appearance: str, points: np.ndarray, marker: Marker) -> np.ndarray:
    """How much marker is at each direction, in 0..1. A pure function of shape.

    The twin of `racer_visual.coverage`. It takes a direction in the marble's
    **own** frame and nothing else: no time, no frame index, no velocity. That
    is the whole reason the visible marking cannot be a synthetic spin - there
    is no argument it could spin with.
    """
    points = np.atleast_2d(np.asarray(points, dtype=float))
    if appearance == "solid":
        return np.zeros(points.shape[0])
    if appearance == "ribbon":
        return _band(points, marker.ribbon_normal, marker.band_half, marker)
    if appearance == "crescent":
        cap = _cap(points, marker.crescent_axis, marker.crescent_cos, marker)
        bite = _cap(points, marker.crescent_bite, marker.crescent_bite_cos, marker)
        return np.clip(cap - bite, 0.0, 1.0)
    if appearance == "meridian":
        band = _band(points, marker.ribbon_normal, marker.band_half, marker)
        ring = _ring(
            points,
            marker.meridian_normal,
            marker.meridian_tilt,
            marker.meridian_half,
            marker,
        )
        return np.clip(band + ring, 0.0, 1.0)
    raise ValueError(f"unknown appearance {appearance!r}")


def _band(points: np.ndarray, normal: np.ndarray, half: float, marker: Marker):
    distance = np.abs(points @ normal)
    return 1.0 - _smoothstep(half, half + marker.edge_soft, distance)


def _ring(
    points: np.ndarray, normal: np.ndarray, tilt: float, half: float, marker: Marker
):
    distance = np.abs((points @ normal) - tilt)
    return 1.0 - _smoothstep(half, half + marker.edge_soft, distance)


def _cap(points: np.ndarray, axis: np.ndarray, reach: float, marker: Marker):
    return _smoothstep(reach - marker.edge_soft, reach + marker.edge_soft, points @ axis)


def direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Godot's `SphereMesh` UV layout, verified by `scripts/sphere_uv_check.gd`."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    return np.stack(
        [
            np.sin(2.0 * np.pi * u) * np.sin(np.pi * v),
            np.cos(np.pi * v),
            np.cos(2.0 * np.pi * u) * np.sin(np.pi * v),
        ],
        axis=-1,
    )


# --- quaternions ----------------------------------------------------------


def _as_array(replay: dict[str, Any], key: str) -> np.ndarray:
    """(frames, marbles, n) for one per-marble field of the replay."""
    frames = replay["frames"]
    return np.array(
        [[marble[key] for marble in frame["marbles"]] for frame in frames], dtype=float
    )


def rotate(quaternion: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Apply (x, y, z, w) to a stack of directions. The replay's own order."""
    x, y, z, w = quaternion
    vector = np.array([x, y, z], dtype=float)
    points = np.atleast_2d(np.asarray(points, dtype=float))
    return (
        points * (w * w - vector @ vector)
        + 2.0 * np.outer(points @ vector, vector)
        + 2.0 * w * np.cross(np.broadcast_to(vector, points.shape), points)
    )


def unrotate(quaternion: np.ndarray, points: np.ndarray) -> np.ndarray:
    """World directions into the marble's own frame."""
    x, y, z, w = quaternion
    return rotate(np.array([-x, -y, -z, w]), points)


def angle_between(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """The rotation, in radians, taking one orientation to another.

    `abs` on the dot product is the short path, which is what Godot's
    `Quaternion.slerp` takes and therefore what the renderer actually shows.
    """
    dot = np.abs(np.sum(first * second, axis=-1))
    return 2.0 * np.arccos(np.clip(dot, -1.0, 1.0))


# --- the diagnosis --------------------------------------------------------


@dataclass
class PhaseStats:
    name: str
    start: float
    end: float
    spin_median: float
    spin_p95: float
    spin_max: float
    step_median: float
    step_p95: float
    step_max: float
    turns_per_second: float

    def to_json(self) -> dict[str, Any]:
        return {
            "phase": self.name,
            "replay_from": self.start,
            "replay_to": self.end,
            "spin_rad_s": {
                "median": round(self.spin_median, 4),
                "p95": round(self.spin_p95, 4),
                "max": round(self.spin_max, 4),
            },
            "step_deg_per_frame": {
                "median": round(self.step_median, 4),
                "p95": round(self.step_p95, 4),
                "max": round(self.step_max, 4),
            },
            "turns_per_second_median": round(self.turns_per_second, 4),
        }


def angular_stats(
    replay: dict[str, Any], phases: Sequence[tuple[str, float, float]] = PHASES
) -> list[PhaseStats]:
    """What the solver actually did to each marble's orientation, by phase.

    Two independent measures, because they check each other. `w` is the angular
    velocity PyBullet reported; the step is the angle between the recorded
    orientations of consecutive frames. If the replay's quaternions were stale
    or constant the step would be zero while `w` stayed large, which is exactly
    the failure this brief had to rule out before any repaint.
    """
    fps = float(replay["replay_fps"])
    spin = np.linalg.norm(_as_array(replay, "w"), axis=2)
    quaternions = _as_array(replay, "q")
    step = np.degrees(angle_between(quaternions[:-1], quaternions[1:]))
    out: list[PhaseStats] = []
    for name, start, end in phases:
        low = max(0, int(round(start * fps)))
        high = min(step.shape[0], int(round(end * fps)))
        if high <= low:
            continue
        window_spin = spin[low:high].ravel()
        window_step = step[low:high].ravel()
        out.append(
            PhaseStats(
                name=name,
                start=start,
                end=end,
                spin_median=float(np.median(window_spin)),
                spin_p95=float(np.percentile(window_spin, 95)),
                spin_max=float(window_spin.max()),
                step_median=float(np.median(window_step)),
                step_p95=float(np.percentile(window_step, 95)),
                step_max=float(window_step.max()),
                turns_per_second=float(np.median(window_spin)) / (2.0 * math.pi),
            )
        )
    return out


def nyquist_report(replay: dict[str, Any]) -> dict[str, Any]:
    """Does the replay sample rotation fast enough to be drawn honestly?

    The renderer slerps between recorded frames and Godot's slerp takes the
    **short** path. If a marble ever turned more than 180 degrees between two
    replay frames, the short path would be the wrong way round and the film
    would show a marble rolling backwards - a real artefact, and one that a
    plain sphere hides completely. So it is checked rather than assumed.
    """
    quaternions = _as_array(replay, "q")
    step = np.degrees(angle_between(quaternions[:-1], quaternions[1:]))
    over = int((step > 180.0).sum())
    where = int(step.argmax())
    return {
        "samples": int(step.size),
        "max_deg_per_frame": float(step.max()),
        "at_replay_second": round(
            (where // step.shape[1]) / float(replay["replay_fps"]), 4
        ),
        "over_180_deg": over,
        "aliased": over > 0,
    }


# --- what the camera can actually see -------------------------------------


def _hemisphere(count: int = 2048) -> np.ndarray:
    """A near-uniform set of directions on the sphere (Fibonacci)."""
    index = np.arange(count, dtype=float) + 0.5
    z = 1.0 - 2.0 * index / count
    radius = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    theta = np.pi * (1.0 + 5.0**0.5) * index
    return np.stack([radius * np.cos(theta), radius * np.sin(theta), z], axis=1)


_SAMPLES = _hemisphere()


def visible_change(
    appearance: str,
    before: np.ndarray,
    after: np.ndarray,
    eye: np.ndarray,
    marker: Marker,
    samples: np.ndarray = _SAMPLES,
) -> float:
    """How much of the marble's visible face changed marker between two frames.

    **This is the readability number, and it is the only one that matters.** An
    angular speed says the body turned; this says the picture did. Points are
    taken on the lit hemisphere facing `eye`, weighted by how much of the disc
    each one covers (`n . eye`, which is the foreshortening), carried into the
    marble's own frame by each frame's orientation, and asked what marker they
    land on. `solid` returns exactly 0.0 for every pair of frames in the race,
    which is the whole diagnosis in one value.
    """
    eye = np.asarray(eye, dtype=float)
    norm = np.linalg.norm(eye)
    if norm < 1.0e-9:
        return 0.0
    eye = eye / norm
    facing = samples @ eye
    lit = facing > 0.0
    if not lit.any():
        return 0.0
    weight = facing[lit]
    front = samples[lit]
    first = coverage(appearance, unrotate(before, front), marker)
    second = coverage(appearance, unrotate(after, front), marker)
    return float((weight * np.abs(first - second)).sum() / weight.sum())


def camera_positions(track: dict[str, Any]) -> list[tuple[float, np.ndarray]]:
    """(replay second, camera position) for every frame of the cut list."""
    out: list[tuple[float, np.ndarray]] = []
    for cut in track["cuts"]:
        for frame in cut["frames"]:
            out.append((float(frame[0]), np.array(frame[1:4], dtype=float)))
    return out


def readability(
    replay: dict[str, Any],
    track: dict[str, Any],
    appearance: str,
    window: tuple[float, float],
    marker: Marker,
    render_scale: float | None = None,
) -> dict[str, Any]:
    """Visible marker change per frame, over one window, from the real camera.

    The camera track is in layout units and the replay is in simulation units,
    so the marble is carried up by `units.render_scale` before the direction to
    the camera is taken - the same single conversion the renderer applies, and
    for the same reason.
    """
    if render_scale is None:
        render_scale = float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    quaternions = _as_array(replay, "q")
    positions = _as_array(replay, "p") * render_scale
    eyes = dict(
        (round(when, 6), where)
        for when, where in camera_positions(track)
    )
    low = max(0, int(round(window[0] * fps)))
    high = min(quaternions.shape[0] - 1, int(round(window[1] * fps)))
    values: list[float] = []
    for index in range(low, high):
        when = round(index / fps, 6)
        eye = eyes.get(when)
        if eye is None:
            continue
        for marble in range(quaternions.shape[1]):
            values.append(
                visible_change(
                    appearance,
                    quaternions[index, marble],
                    quaternions[index + 1, marble],
                    eye - positions[index, marble],
                    marker,
                )
            )
    if not values:
        return {"appearance": appearance, "samples": 0}
    array = np.array(values)
    return {
        "appearance": appearance,
        "samples": int(array.size),
        "median": round(float(np.median(array)), 6),
        "p95": round(float(np.percentile(array, 95)), 6),
        "max": round(float(array.max()), 6),
        # The share of frames in which the marking says nothing at all. A
        # single great circle has an axis it can turn about invisibly; this
        # counts how often the race actually puts a marble on it.
        "quiet_share": round(float((array < 0.002).mean()), 6),
    }


# --- the edit boundary ----------------------------------------------------


def omissions(track: dict[str, Any]) -> list[dict[str, Any]]:
    """Every place the film skips replay time, from the camera track's own edit."""
    edit = track.get("edit") or []
    found: list[dict[str, Any]] = []
    for first, second in zip(edit, edit[1:]):
        gap = float(second["replay"][0]) - float(first["replay"][1])
        if gap > 1.0e-6:
            found.append(
                {
                    "out_second": float(first["out"][1]),
                    "replay_before": float(first["replay"][1]),
                    "replay_after": float(second["replay"][0]),
                    "omitted": round(gap, 6),
                }
            )
    return found


def boundary_report(
    replay: dict[str, Any], before: float, after: float, render_scale: float | None = None
) -> dict[str, Any]:
    """What each marble does across one cut: how far it moves, how far it turns.

    Both, together, because only the pair answers the question. Orientation
    alone always jumps across an omission - 1.95 s of mixing is 1.95 s of
    tumbling - and that on its own is not a fault, it is what a cut is. The
    fault would be an orientation jump at an instant where *position* is
    continuous, because then the marking would be the only thing that moved and
    the cut would read as the marbles flinching rather than as an edit.
    """
    if render_scale is None:
        render_scale = float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    quaternions = _as_array(replay, "q")
    positions = _as_array(replay, "p")
    low = int(round(before * fps))
    high = int(round(after * fps))
    low = min(max(low, 0), quaternions.shape[0] - 1)
    high = min(max(high, 0), quaternions.shape[0] - 1)
    turn = np.degrees(angle_between(quaternions[low], quaternions[high]))
    move = np.linalg.norm(positions[high] - positions[low], axis=1)
    # What one ordinary frame of this moment costs, as the yardstick. A jump
    # the size of a frame is not a jump.
    frame_turn = np.degrees(angle_between(quaternions[low], quaternions[low + 1]))
    return {
        "replay_before": before,
        "replay_after": after,
        "turn_deg": [round(float(value), 3) for value in turn],
        "turn_deg_median": round(float(np.median(turn)), 3),
        "turn_deg_max": round(float(turn.max()), 3),
        "move_sim": [round(float(value), 4) for value in move],
        "move_sim_median": round(float(np.median(move)), 4),
        "move_layout_median": round(float(np.median(move)) * render_scale, 4),
        "one_frame_turn_deg_median": round(float(np.median(frame_turn)), 3),
        # A marble's own radius is 0.5 sim units, so a move of 1.0 is a whole
        # diameter: the plain sphere was never hiding a still picture here.
        "moved_over_one_radius": int((move > 0.5).sum()),
    }


#: The start actuators whose pose has to match across a cut for the *machine*
#: to look continuous. The rotor is the one the shipped boundary was locked on:
#: it turns 4.0346 revolutions across the omission, so the blades land 12.4
#: degrees from where they left.
MACHINE_KEYS = tuple(f"start.rotor{index}" for index in range(4))


def machine_mismatch(
    replay: dict[str, Any], before: float, after: float,
    keys: Sequence[str] = MACHINE_KEYS,
) -> float:
    """The worst pose error, in degrees, any locked actuator has across a cut.

    This is the constraint a candidate boundary has to keep. The rotor does not
    turn at a constant rate - it spins up through the mixer and is all but
    stopped by 5 s - so sliding the window is *not* free: the number of
    revolutions inside it changes, and with it how far the blades are from
    where the previous shot left them.
    """
    fps = float(replay["replay_fps"])
    frames = replay["frames"]
    low = min(max(int(round(before * fps)), 0), len(frames) - 1)
    high = min(max(int(round(after * fps)), 0), len(frames) - 1)
    worst = 0.0
    for key in keys:
        first = frames[low]["actuators"].get(key)
        second = frames[high]["actuators"].get(key)
        if first is None or second is None:
            continue
        worst = max(
            worst,
            float(
                np.degrees(
                    angle_between(
                        np.array(first["q"], dtype=float),
                        np.array(second["q"], dtype=float),
                    )
                )
            ),
        )
    return worst


def boundary_visible(
    replay: dict[str, Any],
    appearance: str,
    before: float,
    after: float,
    eye: np.ndarray,
    marker: Marker,
    render_scale: float | None = None,
) -> list[float]:
    """Per marble, how much of the visible face changes marker across a cut.

    The same measure as `visible_change` inside a shot, so the two are directly
    comparable: a cut whose value sits inside the ordinary per-frame spread is
    a cut the marking does not expose, and one far above it is a jump.
    """
    if render_scale is None:
        render_scale = float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    quaternions = _as_array(replay, "q")
    positions = _as_array(replay, "p") * render_scale
    low = min(max(int(round(before * fps)), 0), quaternions.shape[0] - 1)
    high = min(max(int(round(after * fps)), 0), quaternions.shape[0] - 1)
    return [
        visible_change(
            appearance,
            quaternions[low, marble],
            quaternions[high, marble],
            np.asarray(eye, dtype=float) - positions[high, marble],
            marker,
        )
        for marble in range(quaternions.shape[1])
    ]


def scan_boundary(
    replay: dict[str, Any],
    before: float,
    after: float,
    reach: float = 0.50,
    step: float | None = None,
) -> list[dict[str, Any]]:
    """Candidate omissions of the **same length**, scored on what they join.

    The existing cut is phase-locked on the rotor, and the rotor's period is
    what makes the machine match across it. This slides both ends together, so
    every candidate omits exactly as much replay time as the shipped one and
    the film's duration, pacing and every downstream time are untouched. What
    changes is only which two instants are joined.
    """
    fps = float(replay["replay_fps"])
    if step is None:
        step = 1.0 / fps
    out: list[dict[str, Any]] = []
    # **Whole frames, counted as frames.** Stepping in seconds and rounding
    # never lands exactly on the shipped boundary, so the one candidate the
    # scan exists to compare against would be missing from its own results.
    stride = max(1, int(round(step * fps)))
    span = int(round(reach * fps))
    first_frame = int(round(before * fps))
    for shift in range(-span, span + 1, stride):
        offset = shift / fps
        shifted_before = round(before + offset, 6)
        shifted_after = round(after + offset, 6)
        if first_frame + shift >= 0:
            report = boundary_report(replay, shifted_before, shifted_after)
            report["offset"] = round(offset, 6)
            report["machine_mismatch_deg"] = round(
                machine_mismatch(replay, shifted_before, shifted_after), 4
            )
            # The marble that moves least while turning most is the one the
            # marking exposes: a ball that holds its place across the cut and
            # changes face is the only thing in frame that jumped.
            turn = np.array(report["turn_deg"])
            move = np.array(report["move_sim"])
            report["stillest_move_sim"] = round(float(move.min()), 4)
            report["turn_of_stillest_deg"] = round(float(turn[move.argmin()]), 3)
            out.append(report)
        offset = round(offset + step, 6)
    return out


def load_replay(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def load_track(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


# --- where a marble lands on screen ---------------------------------------


def project(
    point: np.ndarray,
    eye: np.ndarray,
    aim: np.ndarray,
    fov_deg: float,
    width: int,
    height: int,
) -> tuple[float, float, float]:
    """A layout-unit point to a pixel, the way the render's camera frames it.

    `course_scene` sets `keep_aspect = KEEP_HEIGHT`, so the camera track's
    `fov` is the **vertical** angle and the horizontal one follows from the
    aspect ratio. Getting that backwards puts a crop in the wrong place on a
    1080x1920 frame by a factor of nearly two, which is the whole picture.
    """
    eye = np.asarray(eye, dtype=float)
    forward = np.asarray(aim, dtype=float) - eye
    forward = forward / np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
    right = right / np.linalg.norm(right)
    up = np.cross(right, forward)
    offset = np.asarray(point, dtype=float) - eye
    depth = float(offset @ forward)
    if depth <= 1.0e-6:
        return float("nan"), float("nan"), depth
    half = math.tan(math.radians(fov_deg) * 0.5)
    ndc_y = float(offset @ up) / depth / half
    ndc_x = float(offset @ right) / depth / (half * (width / height))
    return (ndc_x + 1.0) * 0.5 * width, (1.0 - ndc_y) * 0.5 * height, depth


def field_box(
    replay: dict[str, Any],
    track: dict[str, Any],
    replay_second: float,
    width: int,
    height: int,
    render_scale: float | None = None,
) -> tuple[int, int, int, int]:
    """The pixel box the eight marbles occupy at one replay instant."""
    if render_scale is None:
        render_scale = float(replay["units"]["render_scale"])
    fps = float(replay["replay_fps"])
    index = min(max(int(round(replay_second * fps)), 0), len(replay["frames"]) - 1)
    frame = None
    for cut in track["cuts"]:
        for row in cut["frames"]:
            if abs(float(row[0]) - replay_second) < 0.5 / fps:
                frame = row
                break
        if frame is not None:
            break
    if frame is None:
        raise ValueError(f"replay second {replay_second} is not in this camera track")
    eye = np.array(frame[1:4], dtype=float)
    aim = np.array(frame[4:7], dtype=float)
    fov = float(frame[7])
    radius = float(replay["marbles"][0].get("radius", 0.5)) * render_scale
    xs: list[float] = []
    ys: list[float] = []
    for marble in replay["frames"][index]["marbles"]:
        centre = np.array(marble["p"], dtype=float) * render_scale
        x, y, depth = project(centre, eye, aim, fov, width, height)
        if math.isnan(x):
            continue
        # The ball's own width in pixels, so the box holds whole marbles.
        span = radius / depth / math.tan(math.radians(fov) * 0.5) * height
        xs += [x - span, x + span]
        ys += [y - span, y + span]
    if not xs:
        raise ValueError("no marble is in front of the camera at that instant")
    return int(min(xs)), int(min(ys)), int(math.ceil(max(xs))), int(math.ceil(max(ys)))


def saturation(
    appearance: str, marker: Marker, angles: Sequence[float] = (1, 2, 5, 10, 20, 30, 45, 60, 90, 120, 150, 180)
) -> list[tuple[float, float]]:
    """Visible marker change against the angle turned, averaged over axes.

    **The curve flattens above about 25 degrees**, and that single fact settles
    what can and cannot be done about an edit boundary. Below it the measure is
    nearly linear in the angle, which is why an ordinary frame of the mixer -
    two or three degrees - reads as a marble turning rather than as a marble
    jumping. Above it the marking is simply somewhere else on the ball, and a
    further ninety degrees adds nothing a viewer can see.

    So a cut that omits 1.95 s of mixing turns every marble far past the point
    where more rotation is visible, and **no whole-frame slide of that cut can
    reduce the orientation discontinuity** - every candidate is saturated. What
    a better boundary can fix is a different thing: whether a marble changes
    face while holding its position, which is the case that reads as a fault
    rather than as a cut.
    """
    eye = np.array([0.0, 0.0, 6.0])
    rest = np.array([0.0, 0.0, 0.0, 1.0])
    axes = [
        np.array(axis, dtype=float) / np.linalg.norm(axis)
        for axis in ((1, 0, 0), (0, 1, 0), (0, 0, 1), (1, 1, 1), (0.7, -0.5, 0.5))
    ]
    out: list[tuple[float, float]] = []
    for degrees in angles:
        half = math.radians(float(degrees)) * 0.5
        values = [
            visible_change(
                appearance, rest,
                np.array([*(axis * math.sin(half)), math.cos(half)]), eye, marker,
            )
            for axis in axes
        ]
        out.append((float(degrees), float(np.mean(values))))
    return out
