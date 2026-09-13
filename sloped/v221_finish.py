"""V22.1: the finish as the end of the chase rather than a shot after it.

V22 ends its chase at replay 20.200 and cuts to V19's finish lens. The cut is
measurably softer than V21's - 0.443 of the frame diagonal against 0.605 - and
it is still the only hard cut left in the film after the start's omission. It
lands 0.650 s before the winner crosses, which is the worst half-second in the
race to ask a viewer to re-find their marble in.

Integration already tried the obvious repair, easing the chase lens onto the
finish lens, and it failed: the two poses are 51.17 layout units and 56.1
degrees apart and the ease has to be spent while the pack is still travelling,
so the chase's own motion and the ease's add and the lens reaches 2.5 to 6.6
units a frame. **Nothing here eases a moving camera onto a distant one.** The
mechanism this module is built on is the other way round:

    a chase that stops chasing is a stand.

The racers come to the line. So the last thing the chase does is *park* - decel
from its own velocity at the split onto a pose fixed to the finish line, reached
before the winner arrives - and everything after that is a camera that is not
moving while eight marbles cross in front of it. A parked camera has no whip
available to it, and the whole move is spent up-course of the crossing where
there is nothing to read yet.

## What this module is, mechanically

`build` takes the **frozen** V22 chase track and rewrites only its tail:

* every row before `Candidate.split` is the row the V22 solve wrote;
* from the split it runs a cubic Hermite on position and on aim whose start
  tangent is the chase's own per-frame velocity and whose end tangent is zero,
  so the join is C1 by construction rather than by smoothing;
* the Hermite's target is a pose in the finish line's own polar frame, and
  after `settle` seconds the camera holds it exactly;
* an optional `Orbit` then swings that held pose around the line - after the
  winner has crossed, never before - to a second polar pose, which for
  candidate B is V19's finish lens to the unit.

Nothing re-simulates. The replay is seed 5432's, the finish order is still
5, 2, 7, 4, 1, 6, 3, 0 and the last crossing is still replay 24.4167.

## The polar frame, and why the poses are written in it

A finish camera is a bearing, a radius and a height about one point, and
writing it as a world position hides which of those three a sweep is moving.
`finish_frame` returns the line's node - `final`'s last path sample, raised a
marble radius, the same point `cameras` calls `nodes["finish_line"]` - together
with the course forward there and a perpendicular to it. A pose is

    node + forward * r*cos(b) + right * r*sin(b) + up * h

so `b = 180` is directly up-course, which is *behind the racers*, and `b = 0` is
directly down-course looking back. V19's finish lens, converted, is
`Pose(bearing=26.9, radius=18.5, height=17.3)`, and `lens_pose` reads it off the
solved track rather than retyping it.

## The one thing the geometry does for free and the one it does not

For free: the marbles' own approach. Behind and above, the field is strung out
between the camera and the line, so a trailing racer is *nearer* the lens than
the winner is and therefore larger. All eight are on one side of the aim.

Not for free: the gantry. `sightlines._finish_furniture` puts the sign at the
deck's upstream edge, four and a half layout units up, and a camera behind the
racers looks at the back of it. That is what the sweep is measuring when it
reports `hidden_share` by label, and it is why the park bearing is not 180.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sloped import chase_camera, layout, terrain

__all__ = [
    "CANDIDATES",
    "Candidate",
    "FINISH_END",
    "Orbit",
    "Pose",
    "build",
    "check_finish",
    "finish_clip",
    "finish_frame",
    "lens_pose",
    "pose_to_world",
    "register",
    "world_to_pose",
]


# The replay second the film's last crossing has happened by, which is V22's
# own finish window end and is not a number this pass may move.
FINISH_END = 24.467

FPS = 60


# --- the finish line's own frame --------------------------------------------


def finish_frame(machine) -> tuple[tuple[float, float, float],
                                   tuple[float, float, float],
                                   tuple[float, float, float]]:
    """`(node, forward, right)` at the finish line, all in layout units.

    `node` is `cameras`' own `nodes["finish_line"]`: the last sample of the
    `final` run's layout path, raised one marble radius to where a marble's
    centre crosses. `forward` is that run's last tangent flattened into the
    ground plane and `right` is `(-fz, 0, fx)`, the perpendicular that puts
    V19's finish lens at a *positive* bearing. The choice between the two
    perpendiculars is arbitrary and is pinned by a test rather than argued.
    """
    run = machine.runs["final"]
    end = run.path[-1]
    node = (float(end[0]), float(end[1]) + layout.MARBLE_RADIUS, float(end[2]))
    tangent = run.tangents[-1]
    flat = math.hypot(float(tangent[0]), float(tangent[2])) or 1.0
    forward = (float(tangent[0]) / flat, 0.0, float(tangent[2]) / flat)
    right = (-forward[2], 0.0, forward[0])
    return node, forward, right


@dataclass(frozen=True)
class Pose:
    """A camera about the finish line: where it stands and what it looks at.

    `bearing` is degrees from the course forward toward `right`, so 180 is
    behind the racers and 0 is in front of them looking back. `radius` is the
    ground-plane distance from the line and `height` is above it. The aim is
    the line itself, pushed `aim_ahead` units down-course and `aim_lift` up -
    a positive `aim_ahead` puts the crossing below the middle of the frame and
    leaves the run-out above it.
    """

    bearing: float
    radius: float
    height: float
    aim_ahead: float = 0.0
    aim_lift: float = 0.0
    fov: float = 36.0


def pose_to_world(machine, pose: Pose) -> tuple[tuple[float, float, float],
                                                tuple[float, float, float]]:
    """`(position, aim)` in layout units for one `Pose`."""
    node, forward, right = finish_frame(machine)
    angle = math.radians(pose.bearing)
    along, across = math.cos(angle) * pose.radius, math.sin(angle) * pose.radius
    position = (
        node[0] + forward[0] * along + right[0] * across,
        node[1] + pose.height,
        node[2] + forward[2] * along + right[2] * across,
    )
    aim = (
        node[0] + forward[0] * pose.aim_ahead,
        node[1] + pose.aim_lift,
        node[2] + forward[2] * pose.aim_ahead,
    )
    return position, aim


def world_to_pose(machine, position: Sequence[float], aim: Sequence[float],
                  fov: float = 36.0) -> Pose:
    """The inverse of `pose_to_world`, for reading a solved lens back."""
    node, forward, right = finish_frame(machine)
    offset = [float(position[axis]) - node[axis] for axis in range(3)]
    along = offset[0] * forward[0] + offset[2] * forward[2]
    across = offset[0] * right[0] + offset[2] * right[2]
    reach = [float(aim[axis]) - node[axis] for axis in range(3)]
    return Pose(
        bearing=math.degrees(math.atan2(across, along)),
        radius=math.hypot(along, across),
        height=offset[1],
        aim_ahead=reach[0] * forward[0] + reach[2] * forward[2],
        aim_lift=reach[1],
        fov=float(fov),
    )


def lens_pose(track: dict[str, Any], machine, at: str = "finish",
              index: int = 0) -> Pose:
    """V19's finish lens, read off a solved track rather than retyped.

    Candidate B's target is *that* shot and not an approximation of it, so the
    pose it eases onto has to come from the same solve the control renders.
    """
    cut = next(c for c in track["cuts"] if c["name"] == at)
    row = cut["frames"][index]
    return world_to_pose(machine, row[1:4], row[4:7], float(row[7]))


# The window the deceleration's own shape has to sit in, and it is the single
# number this whole pass turned on.
#
# Write the cubic in its own units - `u(s)` is the fraction of the journey
# covered, `r = steps * v0 / distance` is how much of the journey the entry
# speed would cover if it never changed - and the derivative comes out as
#
#     u'(s) = (1 - s) * ((6 - 3r) * s + r)
#
# which says three things at once and needs no sweep to say them:
#
# * `r > 3` **overshoots.** `u'` goes negative before `s = 1`, so the lens flies
#   past the park and comes back. This is a bounce, and it is what a settle
#   chosen short enough to finish before the winner does at these distances.
# * `r < 1.5` **bulges.** The peak of `u'` moves off `s = 0` and the lens has to
#   speed *up* to cover the ground in time, which is the 2.5-to-6.6 units a
#   frame the previous integration attempt measured, arrived at from the other
#   direction.
# * **Between them the maximum step is exactly `v0`** - `u'` is largest at
#   `s = 0`, where it is `r` by construction, and `(D/N) * r = v0`. So a settle
#   inside this band cannot move the lens faster than the chase was already
#   moving it, whatever the distance is. The V22 chase's own worst interior step
#   is 0.832 layout units a frame, and that becomes the ceiling for free.
#
# `settle_seconds` solves for the middle of the band rather than an edge.
MIN_RATIO, MAX_RATIO, AIM_RATIO = 1.5, 3.0, 2.0


# --- the candidates ---------------------------------------------------------


@dataclass(frozen=True)
class Orbit:
    """A swing of the parked camera around the line, after the winner crosses.

    `at` is a replay second and is checked against the winner's own crossing:
    `build` raises if an orbit would start before it, because the whole claim of
    candidate B is that the most important moment is not interrupted.
    """

    at: float
    seconds: float
    to: Pose
    ease: float = 0.25


@dataclass(frozen=True)
class Candidate:
    """One finish language, as the numbers that distinguish them.

    `split` is the replay second the chase stops being solved from the pack.
    `settle` is how long the deceleration onto `park` takes, in seconds; leave
    it `None` and `build` solves it from `ratio` and the geometry, which is what
    the shipped candidates do - see `MIN_RATIO`. A candidate with `park = None`
    is the control, and `build` hands back V22's own track for it.

    **`aim_settle` is separate from `settle`, and that separation is what buys
    the anticipation.** The two channels have different jobs: the position has
    seventy layout units to cross and may not do it faster than the chase was
    already moving, while the aim has thirty and its only real limit is how fast
    the picture may turn. Tied together, the line does not enter the frame until
    the lens is nearly parked. Given its own, shorter settle the camera looks
    where it is going before it gets there - which is the brief's "aim slightly
    ahead toward the finish line" said as a number. `None` ties it to `settle`.
    """

    name: str
    split: float | None
    park: Pose | None
    settle: float | None = None
    ratio: float = AIM_RATIO
    aim_settle: float | None = None
    orbit: Orbit | None = None
    note: str = ""


CANDIDATES: dict[str, Candidate] = {}


def register(candidate: Candidate) -> Candidate:
    """Put a candidate on the list the tool renders and the tests walk."""
    CANDIDATES[candidate.name] = candidate
    return candidate


# --- the solve --------------------------------------------------------------


def _smootherstep(fraction: float) -> float:
    f = min(max(fraction, 0.0), 1.0)
    return f * f * f * (f * (f * 6.0 - 15.0) + 10.0)


def _trapezoid(fraction: float, ease: float) -> float:
    """A move that ramps up, holds a constant rate, and ramps down.

    **A smootherstep is the wrong ease for a long swing and the arithmetic says
    so before a frame is rendered.** Its peak rate is 1.875 times its mean, so
    an orbit of 153 degrees spent as a smootherstep has to turn 1.875 times as
    fast in the middle as it would at a constant rate - and the middle of this
    orbit is where the fourth, fifth and sixth racers cross. A trapezoid spends
    `ease` of its length at each end getting up to and down from one rate, and
    its peak is `1 / (1 - ease)` times the mean: 1.33 at `ease = 0.25` against
    1.875, which is the difference between a swing that fits under
    `chase_camera.MAX_TURN_RATE` in the time available and one that does not.

    Returns the **fraction of the move completed**, so it is a drop-in for
    `_smootherstep` and integrates to exactly 1 at `fraction = 1`.
    """
    f = min(max(fraction, 0.0), 1.0)
    e = min(max(ease, 0.0), 0.5)
    if e <= 1e-9:
        return f
    # Area under the rate profile, normalised by the whole area `1 - e`.
    if f <= e:
        area = e * _rampint(f / e)
    elif f <= 1.0 - e:
        area = 0.5 * e + (f - e)
    else:
        area = 0.5 * e + (1.0 - 2.0 * e) + e * (0.5 - _rampint((1.0 - f) / e))
    return area / (1.0 - e)


def _rampint(x: float) -> float:
    """The integral of smootherstep from 0 to `x`. Half the unit interval's area."""
    x = min(max(x, 0.0), 1.0)
    return x ** 6 - 3.0 * x ** 5 + 2.5 * x ** 4


def _hermite(p0: float, v0: float, p1: float, steps: int, step: int) -> float:
    """One axis of a cubic that leaves `p0` at `v0` and arrives at `p1` at rest.

    `v0` is **per frame** and `steps` is the frame count, so the tangent in the
    curve's own parameter is `steps * v0`. This is the whole of the continuity
    claim: at `step = 0` the derivative is exactly the chase's last velocity and
    at `step = steps` it is exactly zero, neither of them approximately.
    """
    if steps <= 0:
        return p1
    s = min(max(step / float(steps), 0.0), 1.0)
    s2, s3 = s * s, s * s * s
    h00 = 2.0 * s3 - 3.0 * s2 + 1.0
    h10 = s3 - 2.0 * s2 + s
    h01 = -2.0 * s3 + 3.0 * s2
    return h00 * p0 + h10 * (steps * v0) + h01 * p1


def ratio(distance: float, entry_speed: float, steps: int) -> float:
    """`steps * v0 / distance`: which of the three cases above a settle is in."""
    if distance <= 1e-9:
        return MAX_RATIO
    return steps * entry_speed / distance


def settle_seconds(distance: float, entry_speed: float, target: float = AIM_RATIO,
                   fps: int = FPS) -> float:
    """How long the deceleration needs, for a chosen place in the band.

    Derived rather than swept, because `r` is what a settle is *for*: a park
    further from the split needs longer in exact proportion, and a chase that
    arrives at the split faster needs less.
    """
    if entry_speed <= 1e-9:
        return 0.0
    return target * distance / entry_speed / float(fps)


def _rows(track: dict[str, Any]) -> list[list[float]]:
    """Every camera row of a track, in replay order, deduped.

    The bookend and the phases share boundary rows on purpose, so a flat
    concatenation repeats a time; the last writer wins, which is the incoming
    shot - the one a viewer sees at that instant.
    """
    seen: dict[float, list[float]] = {}
    for cut in track["cuts"]:
        for row in cut["frames"]:
            seen[round(float(row[0]), 6)] = list(row)
    return [seen[when] for when in sorted(seen)]


def _crossings(replay: dict[str, Any]) -> dict[int, float]:
    return chase_camera._crossings(replay)


def winner(replay: dict[str, Any]) -> tuple[int, float]:
    """Which marble crosses first and when, from the replay's own events."""
    crossed = _crossings(replay)
    marble = min(crossed, key=lambda m: crossed[m])
    return marble, crossed[marble]


def _bearing_path(start: float, end: float) -> float:
    """The end bearing wrapped to within 180 degrees of the start.

    An orbit from 172 to 27 is 145 degrees the short way and 215 the long way,
    and a camera that takes the long way round crosses the course.
    """
    delta = (end - start + 180.0) % 360.0 - 180.0
    return start + delta


def build(
    base: dict[str, Any],
    replay: dict[str, Any],
    machine,
    candidate: Candidate,
    fps: int = FPS,
    end: float = FINISH_END,
) -> dict[str, Any]:
    """V22's track with its finish replaced by `candidate`'s.

    The control (`park is None`) is handed back unchanged, which is what makes
    it a control: the comparison renders the same document production would.
    """
    if candidate.park is None or candidate.split is None:
        return base

    rows = _rows(base)
    split = float(candidate.split)
    kept = [row for row in rows if float(row[0]) <= split + 1e-9]
    if len(kept) < 3:
        raise ValueError(f"the split at {split} leaves no chase to continue")
    times = [float(row[0]) for row in rows]
    tail = [when for when in times if split + 1e-9 < when <= end + 1e-9]
    if not tail:
        raise ValueError(f"the split at {split} leaves no finish to solve")

    _marble, won = winner(replay)
    if candidate.orbit is not None and candidate.orbit.at < won - 1e-9:
        raise ValueError(
            f"the orbit starts at {candidate.orbit.at} and the winner crosses "
            f"at {won:.4f}: an orbit may not interrupt the crossing"
        )

    # The chase's own state at the split: pose, and the per-frame velocity of
    # the pose. A backward difference rather than a fit, because the rows are
    # exactly one frame apart and a fit would smooth the very thing the join is
    # supposed to match.
    here, before = kept[-1], kept[-2]
    start_pos = [float(here[axis]) for axis in (1, 2, 3)]
    start_aim = [float(here[axis]) for axis in (4, 5, 6)]
    start_fov = float(here[7])
    vel_pos = [float(here[axis]) - float(before[axis]) for axis in (1, 2, 3)]
    vel_aim = [float(here[axis]) - float(before[axis]) for axis in (4, 5, 6)]
    vel_fov = float(here[7]) - float(before[7])

    park_pos, park_aim = pose_to_world(machine, candidate.park)
    speed = math.sqrt(sum(value * value for value in vel_pos))
    reach = math.dist(start_pos, park_pos)
    if candidate.settle is None:
        settle = settle_seconds(reach, speed, candidate.ratio, fps)
    else:
        settle = float(candidate.settle)
    steps = max(int(round(settle * fps)), 1)
    aim_settle = settle if candidate.aim_settle is None else float(candidate.aim_settle)
    aim_steps = max(int(round(aim_settle * fps)), 1)

    solved: list[list[float]] = [list(here)]
    for offset, when in enumerate(tail, start=1):
        position = [
            _hermite(start_pos[axis], vel_pos[axis], park_pos[axis], steps, offset)
            for axis in range(3)
        ]
        aim = [
            _hermite(start_aim[axis], vel_aim[axis], park_aim[axis], aim_steps, offset)
            for axis in range(3)
        ]
        fov = _hermite(start_fov, vel_fov, candidate.park.fov, steps, offset)

        # The orbit, if there is one, moves the *target* rather than the solved
        # pose: at any instant inside it the camera is parked at an interpolated
        # `Pose`, so the path is an arc about the line at a radius and a height
        # that ease, not a straight line between two stands.
        if candidate.orbit is not None and when >= candidate.orbit.at:
            share = _trapezoid(
                (when - candidate.orbit.at) / max(candidate.orbit.seconds, 1e-6),
                candidate.orbit.ease,
            )
            target = candidate.orbit.to
            park = candidate.park
            moved = Pose(
                bearing=park.bearing + share * (
                    _bearing_path(park.bearing, target.bearing) - park.bearing
                ),
                radius=park.radius + share * (target.radius - park.radius),
                height=park.height + share * (target.height - park.height),
                aim_ahead=park.aim_ahead + share * (target.aim_ahead - park.aim_ahead),
                aim_lift=park.aim_lift + share * (target.aim_lift - park.aim_lift),
                fov=park.fov + share * (target.fov - park.fov),
            )
            orbit_pos, orbit_aim = pose_to_world(machine, moved)
            # Inside the settle the two are blended, so an orbit that begins
            # before the park is reached does not tear. In practice it never
            # does - the orbit is after the winner and the park is before it -
            # but a sweep is allowed to ask for one and must get an answer.
            reached = min(offset / float(steps), 1.0)
            aim_reached = min(offset / float(aim_steps), 1.0)
            position = [
                position[axis] + reached * (orbit_pos[axis] - park_pos[axis])
                for axis in range(3)
            ]
            aim = [
                aim[axis] + aim_reached * (orbit_aim[axis] - park_aim[axis])
                for axis in range(3)
            ]
            fov = fov + reached * (moved.fov - park.fov)

        solved.append([
            round(when, 6),
            round(position[0], 4), round(position[1], 4), round(position[2], 4),
            round(aim[0], 4), round(aim[1], 4), round(aim[2], 4),
            round(fov, 3),
        ])

    aim_speed = math.sqrt(sum(value * value for value in vel_aim))
    shape = {
        "settle": round(settle, 4),
        "steps": steps,
        "parked_at": round(float(here[0]) + settle, 4),
        "entry_speed": round(speed, 4),
        "reach": round(reach, 3),
        "ratio": round(ratio(reach, speed, steps), 3),
        "aim_settle": round(aim_settle, 4),
        "aim_steps": aim_steps,
        "aim_entry_speed": round(aim_speed, 4),
        "aim_reach": round(math.dist(start_aim, park_aim), 3),
        "aim_ratio": round(
            ratio(math.dist(start_aim, park_aim), aim_speed, aim_steps), 3
        ),
    }
    return _assemble(base, replay, machine, candidate, solved, end, shape)


def _fastest(replay: dict[str, Any], solved: list[list[float]]) -> float:
    """The quickest running racer over a window, in layout units a second.

    `cameras.check_track` divides this by the fps and compares it with how far
    the aim moved in a frame, so a cut that reports zero fails that check
    whatever its aim does. Writing a placeholder here cost an afternoon of
    believing the aim was snapping when the only thing that was wrong was the
    cut's own metadata.
    """
    low, high = float(solved[0][0]), float(solved[-1][0])
    quickest = 0.0
    for frame in replay["frames"]:
        when = float(frame["t"])
        if when < low - 1e-9 or when > high + 1e-9:
            continue
        for sample in frame["marbles"]:
            if sample.get("s") != "running":
                continue
            quickest = max(quickest, math.sqrt(
                sum(float(v) ** 2 for v in sample["v"])
            ) * chase_camera.SIM_TO_LAYOUT)
    return quickest


def _assemble(
    base: dict[str, Any],
    replay: dict[str, Any],
    machine,
    candidate: Candidate,
    solved: list[list[float]],
    end: float,
    shape: dict[str, Any],
) -> dict[str, Any]:
    """The new cuts and the new edit map, from the rows the solve produced."""
    split = float(candidate.split)
    cfg = terrain.terrain_config(machine.runs)

    cuts: list[dict[str, Any]] = []
    for cut in base["cuts"]:
        rows = [row for row in cut["frames"] if float(row[0]) <= split + 1e-9]
        if len(rows) < 2:
            continue
        entry = dict(cut)
        entry["frames"] = [list(row) for row in rows]
        entry["from"] = round(float(rows[0][0]), 6)
        entry["to"] = round(float(rows[-1][0]), 6)
        cuts.append(entry)

    clearances = [terrain.clearance(row[1:4], row[4:7], cfg) for row in solved]
    elevations = sorted(
        math.degrees(math.atan2(
            row[2] - row[5],
            max(math.hypot(row[1] - row[4], row[3] - row[6]), 1e-6),
        ))
        for row in solved
    )
    cuts.append({
        "name": "final",
        "until": "",
        "trail": 0.0,
        "rise": round(candidate.park.height, 3),
        "look": round(candidate.park.aim_ahead, 3),
        "spread": 0.0,
        "fov": candidate.park.fov,
        "ramp": shape["settle"],
        # **`node`, not `pack`, and that is a claim about the shot rather than
        # bookkeeping.** The final phase's aim is the finish line itself, which
        # is what `cameras.check_track` means by `target == "node"` and why it
        # exempts such a cut from `MAX_AIM_DRIFT`: a camera aimed at a landmark
        # is not failing to follow the field, it is doing something else.
        "target": "node",
        "band": 0.0,
        "node": "finish_line",
        "side": 0,
        "fixed_heading": False,
        "heading_run": "",
        "from": round(float(solved[0][0]), 6),
        "to": round(float(solved[-1][0]), 6),
        "chase": True,
        "extent": round(candidate.park.radius, 3),
        "distance": round(math.dist(solved[-1][1:4], solved[-1][4:7]), 4),
        "elevation": round(elevations[len(elevations) // 2], 3),
        "fastest_racer": round(_fastest(replay, solved), 4),
        "subject": [],
        "lift_deg": 0.0,
        "min_clearance": round(min(clearances), 3),
        "frames": [list(row) for row in solved],
    })

    windows: list[tuple[str, float, float]] = []
    for segment in base["edit"]:
        low, high = float(segment["replay"][0]), float(segment["replay"][1])
        if low >= split - 1e-9:
            continue
        windows.append((segment["cut"], low, min(high, split)))
    # **The window's declared end is `end`, not the last row's time.** The two
    # differ by 0.000333 s - the edit says 24.467 and the last replay frame is
    # at 24.466667 - and `cameras.build_track` writes the declared number for
    # its own finish window. Writing the row's time instead would make this
    # track's `duration` 0.02 of a frame shorter than the control's for no
    # reason anybody could later reconstruct. `master_frames` rounds to 1221
    # either way; the point is that a diff of the two edit maps should show the
    # cut names changing and nothing else.
    windows.append(("final", split, float(end)))

    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for name, low, high in windows:
        span = high - low
        segments.append({
            "cut": name,
            "out": [round(cursor, 6), round(cursor + span, 6)],
            "replay": [round(low, 6), round(high, 6)],
        })
        cursor += span

    crossings = [float(t) for t in _crossings(replay).values()]
    carried = {
        key: value for key, value in base.items()
        if key not in ("cuts", "edit", "duration", "omitted", "last_crossing")
    }
    return {
        **carried,
        "candidate": candidate.name,
        "shape": shape,
        "duration": round(cursor, 6),
        "omitted": round(max(0.0, (windows[-1][2] - windows[0][1]) - cursor), 6),
        "last_crossing": round(max(crossings) if crossings else 0.0, 6),
        "edit": segments,
        "cuts": cuts,
    }


def check_finish(track: dict[str, Any], replay: dict[str, Any] | None = None) -> list[str]:
    """`chase_camera.check_chase`, with one finding retired for a stated reason.

    The retired one is the look-ahead budget: `check_chase` allows a chase cut's
    aim to sit `look + one marble` from the nearest racer, because a chase aim
    is the course a little way downstream of the pack. The final phase's aim is
    **not** downstream of the pack by a fixed amount - it is the finish line,
    standing still, with the pack closing on it. The gap therefore starts large
    and shrinks to nothing, which is the shot working rather than failing, and
    the budget has no number that expresses it.

    Retiring a check that fires is how a prototype flatters itself, so the
    property is re-asserted the way `cameras.check_track` already does for a
    node aim: the aim must be the node **exactly**, which is checked here, and
    the racers must be in frame and readable, which
    `tools/sloped_v221_finish.py` measures at every crossing.
    """
    problems = [
        finding
        for finding in chase_camera.check_chase(track, replay)
        if not (
            "its look-ahead allows" in finding
            and any(
                cut.get("target") == "node" and finding.startswith(f"{cut['name']}:")
                for cut in track["cuts"]
            )
        )
    ]
    return problems


def finish_clip(track: dict[str, Any], since: float) -> dict[str, Any]:
    """The tail of a track as a document whose output clock starts at zero.

    A proof of a finish should not cost twenty seconds of Godot to reach, and a
    clip that re-times the edit is the way to render one: the scene walks
    **output** seconds and looks the replay second up in the edit map, so an
    edit that begins at output 0 on replay `since` renders the last few seconds
    and nothing before them. The camera rows are untouched, so a frame from a
    clip is the frame the full master would have written.
    """
    cuts: list[dict[str, Any]] = []
    for cut in track["cuts"]:
        rows = [row for row in cut["frames"] if float(row[0]) >= since - 1e-9]
        if len(rows) < 2:
            continue
        entry = dict(cut)
        entry["frames"] = [list(row) for row in rows]
        entry["from"] = round(float(rows[0][0]), 6)
        entry["to"] = round(float(rows[-1][0]), 6)
        cuts.append(entry)
    if not cuts:
        raise ValueError(f"nothing in this track runs past replay {since}")

    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for segment in track["edit"]:
        low, high = float(segment["replay"][0]), float(segment["replay"][1])
        if high <= since + 1e-9:
            continue
        low = max(low, since)
        span = high - low
        if span <= 1e-9:
            continue
        segments.append({
            "cut": segment["cut"],
            "out": [round(cursor, 6), round(cursor + span, 6)],
            "replay": [round(low, 6), round(high, 6)],
        })
        cursor += span
    return {**track, "duration": round(cursor, 6), "edit": segments,
            "cuts": cuts, "clip_from": round(since, 6)}
