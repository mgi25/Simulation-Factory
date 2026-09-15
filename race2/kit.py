"""The vocabulary Race #2's courses are written in.

Three things live here and nothing else: how a run is specified, how a module
frame is derived from two world points, and the control-point helpers that let
a folded course be typed as turns and ramps rather than as a list of numbers.

## Runs are specified, not placed

`sloped.track.TrackRun` takes a spec dictionary - name, role, profile scale,
bank gain, bank ceiling, control points - and builds the channel at those world
coordinates. Race #1 keeps its specs in `sloped.layout` because they are a
transcription of a drawn asset and the transcription is the contract. Race #2
has no drawn asset to transcribe, so a spec is written by `run_spec` and the
control points are the only coordinates anyone types.

## Width is profile scale, and that is a decision

A run's `scale` multiplies the whole cross-section - the clear width, the
cradle radius, the floor drop and the guard height together. So a run at scale
2.6 is 4.9 layout units of clear width with a cradle 0.52 deep across its half
width: a dished raceway a field of eight can spread across and bank off the
sides of, not a flat pan. That is wanted. A flat pan lets a marble wander
between the walls and tick off each one - `marble3d.modules.base` records the
finding that put a cradle in the channel in the first place - and a dish that
is proportionally as shallow as Race #1's is one a marble can still climb at
racing speed.

The alternative, a flat floor at a fixed guard height, would need a second
cross-section function, a second `surface_point`, a second containment number
and a second set of probes. Scale needs none of those, because every one of
them already reads `self.scale`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from marble3d.geometry import Transform, basis_from_forward_up

from sloped.scale import to_sim_point

__all__ = [
    "Vec3",
    "DEFAULT_BANK_GAIN",
    "DEFAULT_BANK_MAX",
    "run_spec",
    "Frame",
    "frame_towards",
    "lerp",
    "ease",
    "ramp_controls",
    "arc_controls",
    "hairpin_controls",
    "plan_length",
]

Vec3 = tuple[float, float, float]

# The two numbers every Race #2 run inherits from the approved channel.
#
# The bank a curve solves for is `gain * curvature`, and 3.4 is what put a
# hero-width channel's banked turns where the drawn asset had them on Race #1's
# `leg1`. A course with tighter turns than Race #1's wants the same gain and
# reaches the ceiling sooner, which is the correct behaviour: a tighter turn
# should bank harder, and the ceiling is what stops it banking past the point
# where a slow marble slides down the inside.
DEFAULT_BANK_GAIN = 3.4
DEFAULT_BANK_MAX = 28.0


def run_spec(
    name: str,
    controls: Sequence[Sequence[float]],
    scale: float = 1.0,
    bank_gain: float = DEFAULT_BANK_GAIN,
    bank_max: float = DEFAULT_BANK_MAX,
    role: str = "long",
    **extra: Any,
) -> dict[str, Any]:
    """One run, in the shape `sloped.track.TrackRun` reads.

    `extra` reaches `sloped.pathing.build_path` for the fields a join uses -
    `entry_bank_deg`, `exit_bank_deg`, `bank_ease_ends`, `entry_flare`,
    `exit_flare`, `design_speed`. They are optional there and optional here.
    """
    points = [tuple(float(v) for v in point) for point in controls]
    if len(points) < 4:
        raise ValueError(
            f"run {name!r}: a Catmull-Rom needs four control points, not {len(points)}"
        )
    spec: dict[str, Any] = {
        "name": name,
        "role": role,
        "scale": float(scale),
        "bank_gain": float(bank_gain),
        "bank_max": float(bank_max),
        "controls": tuple(points),
    }
    spec.update(extra)
    return spec


# --- module frames ---------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """A right-handed frame on the ground plane: forward, up, across.

    Modules that are not runs - the start shelf, a splitter wedge, a catch
    apron - are authored in their own (along, up, across) coordinates and
    placed by one of these. `up` is world +Y always: a start shelf is level
    whatever the channel under it is doing, and a wedge that tipped with the
    local bank would be a wedge whose nose height nobody wrote down.
    """

    origin: Vec3
    forward: Vec3
    across: Vec3
    up: Vec3 = (0.0, 1.0, 0.0)

    def place(self, along: float, up: float, across: float) -> Vec3:
        """A point in the module's own coordinates, as a world layout point."""
        return (
            self.origin[0] + self.forward[0] * along + self.up[0] * up + self.across[0] * across,
            self.origin[1] + self.forward[1] * along + self.up[1] * up + self.across[1] * across,
            self.origin[2] + self.forward[2] * along + self.up[2] * up + self.across[2] * across,
        )

    def sim(self, along: float, up: float, across: float) -> Vec3:
        return to_sim_point(self.place(along, up, across))

    def yaw(self) -> float:
        """The heading, measured the way `Socket.heading` measures one."""
        return math.atan2(-self.forward[2], self.forward[0])

    def transform(self, along: float = 0.0, up: float = 0.0, across: float = 0.0) -> Transform:
        return Transform(
            position=self.sim(along, up, across),
            rotation=basis_from_forward_up(self.forward, self.up),
        )


def frame_towards(origin: Sequence[float], target: Sequence[float]) -> Frame:
    """A level frame at `origin` whose forward points at `target` in plan.

    The pitch is dropped deliberately. Everything that uses one of these - a
    shelf, a wedge, an apron lip - is built level and measured from the ground,
    and a frame that tipped with the local grade would put a wedge's nose at a
    height nobody wrote down.
    """
    dx = float(target[0]) - float(origin[0])
    dz = float(target[2]) - float(origin[2])
    span = math.hypot(dx, dz)
    if span < 1e-9:
        raise ValueError("a frame needs two points that differ in plan")
    forward = (dx / span, 0.0, dz / span)
    # across = up x forward, so (forward, up, across) is right-handed and
    # +across is to the *left* of travel. Stated rather than left to be
    # inferred, because a bay numbering that runs the wrong way is a fairness
    # result with its sign silently flipped.
    across = (-forward[2], 0.0, forward[0])
    return Frame(tuple(float(v) for v in origin), forward, across)


# --- control-point helpers -------------------------------------------------


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def ease(t: float) -> float:
    t = min(max(t, 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def plan_length(points: Sequence[Sequence[float]]) -> float:
    """Horizontal distance along a control polygon, in layout units."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.hypot(float(b[0]) - float(a[0]), float(b[2]) - float(a[2]))
    return total


def ramp_controls(
    start: Sequence[float],
    end: Sequence[float],
    count: int = 6,
    bow: float = 0.0,
) -> list[Vec3]:
    """A straight descent from `start` to `end`, optionally bowed sideways.

    `bow` is the lateral offset at the midpoint, in layout units, positive to
    the left of travel. A run with no bow has zero curvature and therefore zero
    bank, which is right for a straight and wrong for a connector that has to
    hand a banked run over to a level one.
    """
    sx, sy, sz = (float(v) for v in start)
    ex, ey, ez = (float(v) for v in end)
    dx, dz = ex - sx, ez - sz
    span = math.hypot(dx, dz) or 1.0
    left = (-dz / span, 0.0, dx / span)
    out: list[Vec3] = []
    for step in range(count):
        t = step / (count - 1)
        swing = bow * math.sin(math.pi * t)
        out.append(
            (
                lerp(sx, ex, t) + left[0] * swing,
                lerp(sy, ey, t),
                lerp(sz, ez, t) + left[2] * swing,
            )
        )
    return out


def arc_controls(
    centre: Sequence[float],
    radius: float,
    from_deg: float,
    to_deg: float,
    top: float,
    bottom: float,
    count: int = 8,
) -> list[Vec3]:
    """A circular turn in plan, descending linearly from `top` to `bottom`.

    Angles are read the way a plan drawing is read: zero along +X, growing
    toward +Z. The height falls with the angle, which at constant radius is the
    same thing as falling with arc length.
    """
    out: list[Vec3] = []
    for step in range(count):
        t = step / (count - 1)
        angle = math.radians(lerp(from_deg, to_deg, t))
        out.append(
            (
                float(centre[0]) + radius * math.cos(angle),
                lerp(top, bottom, t),
                float(centre[2]) + radius * math.sin(angle),
            )
        )
    return out


def hairpin_controls(
    entry: Sequence[float],
    heading_deg: float,
    radius: float,
    turn_deg: float,
    drop: float,
    count: int = 9,
) -> list[Vec3]:
    """A turn of `turn_deg` beginning at `entry` on `heading_deg`.

    The sign of `turn_deg` is the sense: positive turns toward +across, which
    under `frame_towards`' convention is to the left of travel. The turn centre
    is solved from the entry point and heading rather than typed, because a
    hairpin whose centre is typed is a hairpin whose entry tangent does not
    match the run feeding it - and a tangent discontinuity at a seam is a
    marble thrown at a wall.
    """
    heading = math.radians(heading_deg)
    forward = (math.cos(heading), 0.0, math.sin(heading))
    left = (-forward[2], 0.0, forward[0])
    sign = 1.0 if turn_deg >= 0.0 else -1.0
    centre = (
        float(entry[0]) + left[0] * radius * sign,
        0.0,
        float(entry[2]) + left[2] * radius * sign,
    )
    start_angle = math.atan2(float(entry[2]) - centre[2], float(entry[0]) - centre[0])
    out: list[Vec3] = []
    for step in range(count):
        t = step / (count - 1)
        angle = start_angle + math.radians(turn_deg) * t
        out.append(
            (
                centre[0] + radius * math.cos(angle),
                float(entry[1]) - drop * t,
                centre[2] + radius * math.sin(angle),
            )
        )
    return out


# --- serpentine authoring --------------------------------------------------
#
# A folded course is a sequence of straights and turns, and typing it as
# control points is how a course acquires a kink nobody meant. These build the
# polyline instead, tangent-continuous at every joint by construction: a turn
# begins on the heading the straight before it ended on, and a straight begins
# on the heading the turn before it ended on.
#
# The spacing is what makes the result usable as *run* controls rather than as
# a drawing. `sloped.pathing.smooth_path` duplicates the end controls, so a
# run's entry tangent is the direction of its first control span and its exit
# tangent the direction of its last. Cutting a polyline whose controls are
# evenly spaced therefore gives two runs whose headings agree at the cut to
# within the local turn rate - which on a straight is exactly, and in a turn is
# one control's worth of arc.


def serpentine(
    start: Sequence[float],
    heading_deg: float,
    segments: Sequence[tuple],
    straight_step: float = 3.6,
    turn_step_deg: float = 11.0,
) -> list[Vec3]:
    """A tangent-continuous polyline from straights and turns.

    Each segment is `("straight", length, drop)` or `("turn", radius, degrees,
    drop)`, and the polyline carries the running heading from one to the next.
    Positive degrees turn toward the left of travel, which is the same sense
    `hairpin_controls` uses and the same sense `frame_towards` calls +across.
    """
    point = (float(start[0]), float(start[1]), float(start[2]))
    heading = math.radians(float(heading_deg))
    out: list[Vec3] = [point]
    for segment in segments:
        kind = segment[0]
        if kind == "straight":
            _name, length, drop = segment
            steps = max(1, int(round(float(length) / straight_step)))
            forward = (math.cos(heading), 0.0, math.sin(heading))
            for step in range(1, steps + 1):
                t = step / steps
                out.append(
                    (
                        point[0] + forward[0] * float(length) * t,
                        point[1] - float(drop) * t,
                        point[2] + forward[2] * float(length) * t,
                    )
                )
            point = out[-1]
        elif kind == "turn":
            _name, radius, degrees, drop = segment
            radius = float(radius)
            degrees = float(degrees)
            sign = 1.0 if degrees >= 0.0 else -1.0
            forward = (math.cos(heading), 0.0, math.sin(heading))
            left = (-forward[2], 0.0, forward[0])
            centre = (
                point[0] + left[0] * radius * sign,
                0.0,
                point[2] + left[2] * radius * sign,
            )
            start_angle = math.atan2(point[2] - centre[2], point[0] - centre[0])
            steps = max(2, int(round(abs(degrees) / turn_step_deg)))
            base_y = point[1]
            for step in range(1, steps + 1):
                t = step / steps
                angle = start_angle + math.radians(degrees) * t
                out.append(
                    (
                        centre[0] + radius * math.cos(angle),
                        base_y - float(drop) * t,
                        centre[2] + radius * math.sin(angle),
                    )
                )
            point = out[-1]
            heading += math.radians(degrees)
        else:
            raise ValueError(f"unknown segment {kind!r}")
    return out


def cut(master: Sequence[Sequence[float]], breaks: Sequence[int]) -> list[list[Vec3]]:
    """Split a polyline into runs that share their end controls.

    Sharing rather than abutting is what makes the seam exact in position: both
    runs pass through the shared control, because `smooth_path` duplicates the
    end controls and a Catmull-Rom so padded starts and finishes exactly on
    them. The heading agrees to one control span, which on a straight is exact.
    """
    points = [tuple(float(v) for v in point) for point in master]
    edges = [0] + [int(b) for b in breaks] + [len(points) - 1]
    if any(b <= a for a, b in zip(edges, edges[1:])):
        raise ValueError(f"breaks must increase and lie inside the polyline: {edges}")
    if edges[-1] >= len(points):
        raise ValueError("a break past the end of the polyline")
    return [points[a : b + 1] for a, b in zip(edges, edges[1:])]
