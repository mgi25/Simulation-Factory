"""V22.1: the start as one continuous move, and where a time omission may hide.

V22 put 1.583 s of live mixing on screen where V21 had 0.683, and frame-by-frame
review said the join still reads as a jump. This module is the prototype that
went looking for why, and the answer is that **three things change at the join
and only one of them is the marbles**:

    replay 1.900 -> 5.833333, as V22 ships it

    the camera   jumps 5.374 layout units in one frame and pulls back 3.664,
                 against a largest legitimate step of 0.851 anywhere inside
                 either shot. The whole frame slides and rescales at once,
                 which is the signature of a cut
    the rotor    stops dead - it was turning at 13 rad/s, 2.07 revolutions a
                 second - and rises 1.193 sim units out of the drum
    the marbles  move up to 2.322 sim units, 1.91 marble diameters on screen

The marbles are the *smallest* of the three. A viewer who reports "the video
jumped" is reporting the camera and the rotor.

## The machine's own timeline, which is what the edit should be cut against

`ShuffleFloor` is not a mixer that runs until the floor opens. It is a five-beat
device, and every one of the beats is a pure function of `release_time`:

    0.300   the start gate opens; the field pours down the apron
    1.600   `rotor_start` - held until the whole field is in, so every racer
            gets the same number of degrees of rotor (see `shuffle.Rotor`)
    1.600 - 4.600   the mix: 13.0 rad/s, 6.21 revolutions, constant rate
    4.600 - 4.900   `spin_down` - the blades visibly decelerate to a stop
    5.200 - 5.900   `rotor_lift_time` - the paddle assembly rises out of the
            drum, 1.193 sim units, on a smoothstep
    5.900 - 6.100   nothing moves
    6.100   `gate_time` - the trapdoor opens

Beats four, five and six are the anticipation the brief asks for, and they are
already in the physics: the mixer winds down, the machine withdraws its own
blades, everything goes still, and then the floor goes. **V22 omits all three** -
1.900-5.833 lands 0.267 s before the trapdoor, with the blades already up.

## The one placement where an omission is free: inside the constant-rate spin

Between `rotor_start` and `rotor_stop` the rotor turns at exactly 13.0 rad/s, so
a blade's screen position is periodic. A revolution is

    2 * pi / 13.0 = 0.483322 s = 28.9993 frames at 60 fps

and 29 frames is 0.483333 s, which is **0.0085 degrees** of blade. Omit a whole
number of revolutions from inside that span and the four blades, the hub and the
paddle assembly's height are all continuous across the join to within a hundredth
of a degree - measured off the replay's own recorded actuator poses, not off the
law. The rotor keeps turning through the cut.

That is what `locked_gaps` solves and what every B-family plan uses. It costs
nothing, it needs no camera trick, and it removes the largest and fastest moving
object in the frame from the list of things that jump.

## Why there is no occlusion wipe here

Strategy B asked whether the camera could slide behind a paddle or the housing
rim and cut while the frame is obscured. Measured at the shipped start framing -
extent 14, fov 34, a 21.5-unit reach - it cannot:

* a blade projects as roughly 200 x 150 px on a 1080 x 1920 frame, which is two
  marbles' worth. Swept over four whole revolutions of phase, the best single
  frame covers **27.9%** of the field's projected area and never more - and that
  figure uses each blade's bounding rectangle, which over-states a thin blade
  seen at an angle;
* the chamber wall stands 0.62 layout units above a floor the lens is 10.8 units
  above. To put that rim between the lens and the field the elevation has to come
  down to a couple of degrees, at which point the shot is looking through the
  machine at the mountain and `cameras`' own clearance loop raises it back.

So the wipe is not available, and this module does not pretend otherwise. What it
does instead is make the *camera* continuous - `constant_rate_legs` hands the
second window an orbit and a dolly that begin exactly where the first window's
end, and ramp at the same rate - so that the only thing the join changes is the
replay clock. See `PLANS`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sloped import cameras, chase_camera, presentation

__all__ = [
    "FPS",
    "PLANS",
    "StartPlan",
    "blade_coverage",
    "build_start_track",
    "join_report",
    "locked_gaps",
    "plan_windows",
    "revolution_frames",
    "rotor_timeline",
    "snap",
]

FPS = 60

# The render the proofs are measured against, so a pixel figure here is the pixel
# a viewer sees. Same as `tools/sloped_v22.py`.
WIDTH, HEIGHT = 1080, 1920

# The lens both start windows use, and the bearing `chase_camera` stands it at.
START_LENS = "start"
START_BEARING = chase_camera.START_BEARING


def snap(seconds: float, fps: int = FPS) -> float:
    """The nearest real replay frame time.

    Every boundary in this module goes through here. A window edge that is not a
    frame is not an honest omission boundary - it is a number that `build_track`
    will round for you, somewhere you did not look.
    """
    return round(round(seconds * fps) / float(fps), 6)


def rotor_timeline(machine) -> dict[str, float]:
    """The five beats of `ShuffleFloor`, read off the module rather than typed."""
    start = machine.modules["start"]
    return {
        "release": float(start.release_time),
        "rotor_start": float(start.rotor_start),
        "rotor_stop": float(start.rotor_stop),
        "spin_down": float(start.SPIN_DOWN),
        "settled": float(start.rotor_stop + start.SPIN_DOWN),
        "lift_at": float(start.rotor_lift_time),
        "gate": float(start.gate_time),
        "rate": float(start.rotor_rate),
        "turns": float(start.rotor_turns),
    }


def revolution_frames(rate: float, fps: int = FPS) -> float:
    """Frames in one rotor revolution. 28.9993 at 13.0 rad/s and 60 fps."""
    return 2.0 * math.pi / float(rate) * float(fps)


def locked_gaps(rate: float, fps: int = FPS, most: int = 8) -> list[dict[str, float]]:
    """Omission lengths, in frames, that leave the blades where they were.

    A gap of `n` omitted frames advances a blade by `rate * n / fps` radians. The
    four blades are identical and 90 degrees apart, so any quarter turn would do
    in principle - but at 60 fps a quarter turn is 7.2498 frames and only whole
    revolutions land near an integer. The residual is reported rather than
    assumed: it is what `join_report` then checks against the recorded poses.
    """
    per = revolution_frames(rate, fps)
    out: list[dict[str, float]] = []
    for turns in range(1, most + 1):
        exact = turns * per
        frames = round(exact)
        out.append({
            "turns": float(turns),
            "frames": float(frames),
            "seconds": frames / float(fps),
            "error_deg": math.degrees(float(rate) * (frames - exact) / float(fps)),
        })
    return out


@dataclass(frozen=True)
class StartPlan:
    """One way to play replay 0.200 - 7.620 as the film's opening.

    `cut_at` is the last live frame before the omission and `resume_at` the first
    live frame after it; both `None` means the plan shows every frame.

    `orbit` and `dolly` are one leg per window - the bearing offset and the reach
    multiplier `cameras.build_track` ramps linearly across that window. **They
    are per-window rather than derived because the camera's continuity is a
    property to be measured, not one to be built in**: V22's legs really do end
    one window at +4 and start the next at 0, and a `StartPlan` that could not
    express that could not carry the control. `join_report` reports the step the
    legs produce; a continuity plan is one whose second leg opens on the value
    its first leg closed at.
    """

    name: str
    cut_at: float | None
    resume_at: float | None
    orbit: tuple[tuple[float, float], ...] | None
    dolly: tuple[tuple[float, float], ...] | None
    note: str = ""
    # **The elevation that stops the shot climbing a staircase.**
    #
    # `cameras.build_track` raises a cut's elevation, frame by frame, until the
    # sight line clears the ground by `SIGHT_MARGIN` - and it does it in whole
    # `LIFT_STEP` of 2 degrees, with no smoothing after. On the start lens's own
    # 16 degrees that loop engages part way through the shot and then keeps
    # engaging, and each engagement moves the lens 0.79 to 0.87 layout units in
    # a single frame. The delivered V22 start has **nine of them** - seven in the
    # first window, two in the second - and each one changes the picture about
    # ten times as much as an ordinary frame does.
    #
    # They are not the omission and this pass did not go looking for them; they
    # are why the start reads as unsteady quite apart from the join. Setting the
    # elevation to where the loop was taking it anyway - 30 degrees - means the
    # loop never runs, and the largest lens step anywhere in the start falls from
    # 0.837 units to 0.044. The framing is the same shot: 8 racers of 8 at 77 and
    # 82 px against 78 and 83.
    #
    # None leaves the lens's own 16, which is what the control needs.
    elevation: float | None = None
    live_from: float = 0.2
    # 7.62 is not a frame time - it is the boundary `chase_camera` takes over on,
    # and `build_track` keeps it as the window's `to` while rendering up to frame
    # 457 at 7.616667. Left exactly as production writes it so the handoff to the
    # chase is unchanged.
    tail_to: float = 7.62

    @property
    def omits(self) -> bool:
        return self.cut_at is not None and self.resume_at is not None

    def omitted(self) -> float:
        """Replay seconds between the two window edges, `cameras`' own measure.

        The same quantity the track's `omitted` field carries, so a figure here
        and a figure there are the same number. `omitted_frames` is the stricter
        reading: one frame of the span is the step playback would have taken
        anyway, and only the rest is replay nobody sees.
        """
        return 0.0 if not self.omits else round(self.resume_at - self.cut_at, 6)

    def omitted_frames(self) -> int:
        """Replay frames the plan never puts on screen."""
        return 0 if not self.omits else max(0, round(self.omitted() * FPS) - 1)

    def live(self) -> float:
        return round(self.tail_to - self.live_from - self.omitted(), 6)


def window_spans(plan: StartPlan) -> tuple[float, ...]:
    """How many seconds of screen each of this plan's windows holds."""
    if not plan.omits:
        return (round(plan.tail_to - plan.live_from, 6),)
    return (round(snap(plan.cut_at) - plan.live_from, 6),
            round(plan.tail_to - snap(plan.resume_at), 6))


def constant_rate_legs(
    spans: Sequence[float], travel: tuple[float, float],
) -> tuple[tuple[float, float], ...]:
    """Split one move across the windows so its **rate never changes**.

    Given the total travel a parameter makes over the whole start - the 36
    degrees of preview handoff, the 16 per cent of push-in - this hands each
    window the share its own length earns. Both windows then ramp at the same
    degrees a second, so the second window opens on the value the first closed
    at *and* carries on at the same speed.

    That is what makes the join disappear as a camera event rather than merely
    a small one: position is continuous because the legs meet, and velocity is
    continuous because the rate is shared. A lens that arrives at a boundary
    moving and leaves it moving the same way is not a lens anyone cut.
    """
    total = sum(spans)
    if total <= 0.0:
        return tuple((travel[0], travel[1]) for _ in spans)
    low, high = travel
    legs: list[tuple[float, float]] = []
    seen = 0.0
    for span in spans:
        start = low + (high - low) * (seen / total)
        seen += span
        legs.append((round(start, 6), round(low + (high - low) * (seen / total), 6)))
    return tuple(legs)


def plan_legs(plan: StartPlan) -> tuple[tuple[tuple[float, float], ...],
                                        tuple[tuple[float, float], ...]]:
    """This plan's orbit and dolly legs, computed if it did not name them."""
    spans = window_spans(plan)
    orbit = plan.orbit or constant_rate_legs(spans, ORBIT_TRAVEL)
    dolly = plan.dolly or constant_rate_legs(spans, DOLLY_TRAVEL)
    return orbit, dolly


def plan_windows(plan: StartPlan) -> tuple[tuple, ...]:
    """The `cameras` edit entries this plan is, ready for `build_track`.

    One window if the plan omits nothing, two if it does. The overrides are
    V21.2's start lens with `chase_camera`'s bearing, plus this plan's legs.
    """
    base = {"fixed_heading": True, "bearing": START_BEARING}
    if plan.elevation is not None:
        base["elevation"] = plan.elevation
    orbit, dolly = plan_legs(plan)
    if not plan.omits:
        return ((START_LENS, plan.live_from, plan.tail_to,
                 {**base, "orbit": tuple(orbit[0]), "dolly": tuple(dolly[0])}),)
    return (
        (START_LENS, plan.live_from, snap(plan.cut_at),
         {**base, "orbit": tuple(orbit[0]), "dolly": tuple(dolly[0])}),
        (START_LENS, snap(plan.resume_at), plan.tail_to,
         {**base, "orbit": tuple(orbit[1]), "dolly": tuple(dolly[1])}),
    )


def build_start_track(
    replay: dict[str, Any],
    machine,
    plan: StartPlan,
    fps: int = FPS,
) -> dict[str, Any]:
    """A `cameras`-schema track holding only this plan's start windows.

    Solved through `cameras.build_track` with the production start lens, so the
    renderer, `check_track`, `frame_report` and `readability` all read it with no
    change - and so a proof clip of the opening is the opening, not a mock-up.
    """
    lens = next(cut for cut in cameras.SECTIONS if cut.name == START_LENS)
    return cameras.build_track(
        replay, machine, sections=(lens,), fps=fps, edit=plan_windows(plan)
    )


# --- what the join does ----------------------------------------------------


def _qrot(q: Sequence[float], v: Sequence[float]) -> tuple[float, float, float]:
    x, y, z, w = q
    cx, cy, cz = y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0]
    dx, dy, dz = y * cz - z * cy, z * cx - x * cz, x * cy - y * cx
    return (v[0] + 2.0 * (w * cx + dx),
            v[1] + 2.0 * (w * cy + dy),
            v[2] + 2.0 * (w * cz + dz))


def _frames_by_time(replay: dict[str, Any]) -> dict[float, dict[str, Any]]:
    return {round(float(frame["t"]), 6): frame for frame in replay["frames"]}


def _chamber_centre(frame: dict[str, Any]) -> tuple[float, float, float]:
    """The rotor hub, as the mean of the four blade centres. Exact by symmetry."""
    points = [frame["actuators"][f"start.rotor{i}"]["p"] for i in range(4)]
    return tuple(sum(p[axis] for p in points) / 4.0 for axis in range(3))


def _blade_angle(frame: dict[str, Any], centre: Sequence[float], index: int = 0) -> float:
    point = frame["actuators"][f"start.rotor{index}"]["p"]
    return math.degrees(math.atan2(point[0] - centre[0], point[2] - centre[2])) % 360.0


def _radius_px(depth: float, fov: float, height: int, scale: float) -> float:
    """A marble's projected radius, in pixels, at this depth."""
    return 0.5 * scale / depth * (height / 2.0) / math.tan(math.radians(fov) / 2.0)


def blade_coverage(
    row: Sequence[float],
    frame: dict[str, Any],
    scale: float,
    width: int = WIDTH,
    height: int = HEIGHT,
    samples: int = 11,
) -> dict[int, float]:
    """What fraction of each marble's projected disc a blade stands in front of.

    Each blade is its own oriented box, projected corner by corner and tested as
    the hull's bounding rectangle - which *over*-states a thin blade seen at an
    angle, so a low number here is a strong statement and a high one is a weak
    one. Depth-tested, so a blade behind a marble does not count.
    """
    camera, aim, fov = tuple(row[1:4]), tuple(row[4:7]), float(row[7])
    half = (0.725, 0.25, 0.05)
    boxes: list[tuple[float, float, float, float, float]] = []
    for index in range(4):
        pose = frame["actuators"].get(f"start.rotor{index}")
        if pose is None:
            continue
        origin = [value * scale for value in pose["p"]]
        corners = []
        for sx in (-1.0, 1.0):
            for sy in (-1.0, 1.0):
                for sz in (-1.0, 1.0):
                    world = _qrot(pose["q"], (sx * half[0], sy * half[1], sz * half[2]))
                    corners.append(tuple(origin[a] + world[a] for a in range(3)))
        shots = [presentation.project(camera, aim, fov, c, width, height) for c in corners]
        shots = [s for s in shots if s is not None]
        if len(shots) < 8:
            continue
        boxes.append((
            min(s[0] for s in shots), max(s[0] for s in shots),
            min(s[1] for s in shots), max(s[1] for s in shots),
            min(s[2] for s in shots),
        ))
    out: dict[int, float] = {}
    for marble in frame["marbles"]:
        point = [value * scale for value in marble["p"]]
        shot = presentation.project(camera, aim, fov, point, width, height)
        if shot is None:
            continue
        radius = _radius_px(shot[2], fov, height, scale)
        inside = total = 0
        span = (samples - 1) / 2.0
        for i in range(samples):
            for j in range(samples):
                dx = (i - span) / span * radius
                dy = (j - span) / span * radius
                if dx * dx + dy * dy > radius * radius:
                    continue
                total += 1
                x, y = shot[0] + dx, shot[1] + dy
                for x0, x1, y0, y1, depth in boxes:
                    if depth < shot[2] and x0 <= x <= x1 and y0 <= y <= y1:
                        inside += 1
                        break
        out[int(marble["id"])] = inside / total if total else 0.0
    return out


def _live_spans(plan: StartPlan) -> list[tuple[float, float]]:
    if not plan.omits:
        return [(plan.live_from, plan.tail_to)]
    return [(plan.live_from, plan.cut_at), (plan.resume_at, plan.tail_to)]


def _last_collision_gap(replay: dict[str, Any], beats: dict[str, float]) -> float:
    """Seconds from the last marble-on-marble hit in the chamber to the trapdoor."""
    gate = beats.get("gate", 6.1)
    hits = [float(e["t"]) for e in replay.get("events", ())
            if e.get("kind") == "collision" and float(e["t"]) < gate]
    return round(gate - max(hits), 4) if hits else 0.0


def _anticipation(plan: StartPlan, beats: dict[str, float]) -> dict[str, float]:
    """How much of each beat the plan actually plays.

    The three beats between `rotor_stop` and `gate_time` are what makes the
    trapdoor land, so a plan is scored on how many of their seconds reach the
    screen rather than on how long its shot is.
    """
    if not beats:
        return {}
    gate = beats["gate"]

    def shown(low: float, high: float) -> float:
        return round(sum(max(0.0, min(end, high) - max(start, low))
                         for start, end in _live_spans(plan)), 4)

    return {
        "pour": shown(beats["release"], beats["rotor_start"]),
        "mixing": shown(beats["rotor_start"], beats["rotor_stop"]),
        "spin_down": shown(beats["rotor_stop"], beats["settled"]),
        "blade_lift": shown(beats["lift_at"], gate),
        "still": shown(beats["settled"], gate),
        "to_gate": shown(beats["rotor_stop"], gate),
    }


def join_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    plan: StartPlan,
    machine=None,
) -> dict[str, Any]:
    """Everything the join changes, measured off the track and the replay.

    Nothing here is a model of the physics: the rotor figures come from the
    recorded actuator poses, the marble figures from the recorded positions, and
    the camera figures from the solved track's own rows.
    """
    scale = float(replay["units"]["render_scale"])
    frames = _frames_by_time(replay)
    beats = rotor_timeline(machine) if machine is not None else {}
    report: dict[str, Any] = {
        "plan": plan.name,
        "note": plan.note,
        "duration": float(track["duration"]),
        "live": plan.live(),
        "omitted": plan.omitted(),
        "omitted_frames": plan.omitted_frames(),
        "omissions": 1 if plan.omits else 0,
        "output_frames": sum(len(cut["frames"]) for cut in track["cuts"]),
        "windows": [{"replay": [float(cut["from"]), float(cut["to"])],
                     "frames": len(cut["frames"])} for cut in track["cuts"]],
        "beats": beats,
        "last_collision_to_gate": _last_collision_gap(replay, beats),
        "live_anticipation": _anticipation(plan, beats),
    }

    # The largest step the lens takes *inside* a shot, which is the yardstick any
    # step across the join has to be read against.
    inside = 0.0
    for cut in track["cuts"]:
        rows = cut["frames"]
        for a, b in zip(rows, rows[1:]):
            inside = max(inside, math.dist(a[1:4], b[1:4]))
    report["camera_step_inside"] = round(inside, 4)

    if not plan.omits:
        report.update({
            "camera_step_join": 0.0,
            "camera_reach_change": 0.0,
            "aim_step_join": 0.0,
            "rotor": {"phase_error_deg": 0.0, "lift_change": 0.0,
                      "inside_constant_rate": True},
            "marbles": {"max_sim": 0.0, "mean_sim": 0.0, "max_px": 0.0,
                        "mean_px": 0.0, "max_diameters": 0.0, "per_marble": {}},
            "coverage": {"mean": 0.0, "worst_mover": 0.0, "per_marble": {}},
        })
        return report

    before = track["cuts"][0]["frames"][-1]
    after = track["cuts"][1]["frames"][0]
    report["camera_step_join"] = round(math.dist(before[1:4], after[1:4]), 4)
    report["camera_reach_change"] = round(
        math.dist(after[1:4], after[4:7]) - math.dist(before[1:4], before[4:7]), 4)
    report["aim_step_join"] = round(math.dist(before[4:7], after[4:7]), 4)

    low = frames[snap(plan.cut_at)]
    high = frames[snap(plan.resume_at)]

    # **The rotor, measured rather than modelled.** One frame of normal playback
    # advances a blade by `rate / fps` radians; the join should advance it by the
    # same amount and no more. The residual is the phase error.
    centre = _chamber_centre(low)
    turned = (_blade_angle(high, centre) - _blade_angle(low, centre)) % 360.0
    expected = math.degrees(beats.get("rate", 13.0) / FPS) % 360.0
    report["rotor"] = {
        "phase_error_deg": round(((turned - expected + 180.0) % 360.0) - 180.0, 4),
        "lift_change": round(high["actuators"]["start.rotor0"]["p"][1]
                             - low["actuators"]["start.rotor0"]["p"][1], 4),
        "inside_constant_rate": bool(
            beats and beats["rotor_start"] <= plan.cut_at
            and plan.resume_at <= beats["rotor_stop"] + 1e-9),
    }

    # The marbles, in the world and on the screen. The screen figure uses each
    # side's own camera row, so it is what the viewer's eye actually sees jump.
    lows = {int(m["id"]): m["p"] for m in low["marbles"]}
    highs = {int(m["id"]): m["p"] for m in high["marbles"]}
    per: dict[int, dict[str, float]] = {}
    for marble in sorted(lows):
        one = presentation.project(before[1:4], before[4:7], before[7],
                                   [v * scale for v in lows[marble]], WIDTH, HEIGHT)
        two = presentation.project(after[1:4], after[4:7], after[7],
                                   [v * scale for v in highs[marble]], WIDTH, HEIGHT)
        pixels = math.dist(one[:2], two[:2]) if one and two else 0.0
        radius = _radius_px(one[2], before[7], HEIGHT, scale) if one else 1.0
        per[marble] = {
            "sim": round(math.dist(lows[marble], highs[marble]), 4),
            "px": round(pixels, 1),
            "diameters": round(pixels / (2.0 * radius), 3),
        }
    report["marbles"] = {
        "max_sim": round(max(v["sim"] for v in per.values()), 4),
        "mean_sim": round(sum(v["sim"] for v in per.values()) / len(per), 4),
        "max_px": round(max(v["px"] for v in per.values()), 1),
        "mean_px": round(sum(v["px"] for v in per.values()) / len(per), 1),
        "max_diameters": round(max(v["diameters"] for v in per.values()), 3),
        "per_marble": per,
    }
    coverage = blade_coverage(before, low, scale)
    report["coverage"] = {
        "mean": round(sum(coverage.values()) / len(coverage), 4) if coverage else 0.0,
        "worst_mover": round(coverage.get(max(per, key=lambda k: per[k]["px"]), 0.0), 4),
        "per_marble": {k: round(v, 4) for k, v in coverage.items()},
    }
    return report


# --- the plans -------------------------------------------------------------

# **What the whole start move is, end to end**, and therefore what
# `constant_rate_legs` has to divide between the windows.
#
# The bearing offset opens at `cameras.V22_START_ORBIT`'s -36, because that is
# the preview handoff: the preview's reverse dolly arrives down the corridor's
# own axis and the chase stands at 230, and V22's finding is that the live start
# shot is the cheap place to spend the 36 degrees between them. It closes at +4,
# which is where V21.2's start lens closes - `cameras.SECTIONS`' `start` cut is
# `orbit=(-6.0, 4.0)` - so the launch is framed on the pose that was proved for
# it. The push-in is that same cut's `dolly=(0.10, -0.06)`, unchanged.
#
# Neither end is new. All this pass does is spend them at one rate.
ORBIT_TRAVEL = (-36.0, 4.0)
DOLLY_TRAVEL = (0.10, -0.06)

# V22's own legs, so the control is the control. The first window orbits -36 to
# +4 and dollies +0.10 to -0.06; the second starts over at the lens's own -6 and
# +0.10, and that restart is where the 5.374-unit lens jump comes from.
_V22_ORBIT = ((-36.0, 4.0), (-6.0, 4.0))
_V22_DOLLY = ((0.10, -0.06), (0.10, -0.06))

PLANS: dict[str, StartPlan] = {
    # The control: exactly what V22 ships, rebuilt from the same edit entries.
    "v22": StartPlan(
        name="v22", cut_at=1.9, resume_at=5.833333,
        orbit=_V22_ORBIT, dolly=_V22_DOLLY,
        note="control - V22 as delivered, 3.933 s omitted across a stopped rotor"),
    # Strategy A: keep more live replay, leave the far side where it is. The
    # rotor still stops and lifts across the join; this family exists to show
    # that more live time in front of a cut does not fix the cut.
    "a22": StartPlan(
        name="a22", cut_at=2.2, resume_at=5.833333,
        orbit=_V22_ORBIT, dolly=_V22_DOLLY,
        note="A - 2.000 s live before the omission"),
    "a25": StartPlan(
        name="a25", cut_at=2.5, resume_at=5.833333,
        orbit=_V22_ORBIT, dolly=_V22_DOLLY,
        note="A - 2.300 s live before the omission"),
    "a28": StartPlan(
        name="a28", cut_at=2.8, resume_at=5.833333,
        orbit=_V22_ORBIT, dolly=_V22_DOLLY,
        note="A - 2.600 s live before the omission"),
    # Strategy B: the omission moved inside the constant-rate spin and cut to a
    # whole number of revolutions, with the lens continuous through it. The
    # number after `b` is the omitted frames: 29 frames is one revolution.
    "b58": StartPlan(
        name="b58", elevation=30.0, cut_at=2.333333, resume_at=3.316667,
        orbit=None, dolly=None,
        note="B - 2 rotor revolutions omitted (0.967 s), lens continuous"),
    "b87": StartPlan(
        name="b87", elevation=30.0, cut_at=2.2, resume_at=3.666667,
        orbit=None, dolly=None,
        note="B - 3 rotor revolutions omitted (1.450 s), lens continuous"),
    "b116": StartPlan(
        name="b116", elevation=30.0, cut_at=2.05, resume_at=4.0,
        orbit=None, dolly=None,
        note="B - 4 rotor revolutions omitted (1.933 s), lens continuous"),
    "b145": StartPlan(
        name="b145", elevation=30.0, cut_at=2.016667, resume_at=4.45,
        orbit=None, dolly=None,
        note="B - 5 rotor revolutions omitted (2.417 s), lens continuous"),
    # The ablation: B's placement with V22's discontinuous camera legs, so the
    # camera's share of the jump can be read off two clips rather than argued.
    "b116_jumpcam": StartPlan(
        name="b116_jumpcam", elevation=30.0, cut_at=2.05, resume_at=4.0,
        orbit=_V22_ORBIT, dolly=_V22_DOLLY,
        note="ablation - B's join with V22's camera legs"),
    # Strategy C, the control at the other end: every frame, nothing omitted.
    "c": StartPlan(
        name="c", elevation=30.0, cut_at=None, resume_at=None,
        orbit=None, dolly=None,
        note="C - no omission, replay 0.200-7.620 entire"),
}
