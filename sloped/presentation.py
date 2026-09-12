"""The presentation layer over a locked master: one clock, and where things are.

V19 is the silent master and nothing in it may move - not the physics, not the
replay, not a camera pose, not the edit map. What a Short needs on top of it is
sound that lands on the right frame and a very few marks that sit on the right
pixel, and both of those need the same two answers:

* **When, in output seconds, did a physical thing happen?** The replay is a
  45-second record; the film is 19.15 s of it in eleven windows, and V20 pushes
  all of that later by a held opening frame. `Clock` is that composition, and it
  is the only place the three clocks meet.
* **Where on the delivered 1080x1920 frame is a marble?** `project` is Godot's
  own camera arithmetic, transcribed: `look_at(aim, UP)` gives a camera with no
  roll, `keep_aspect` is KEEP_HEIGHT so `fov` is the *vertical* angle, and the
  horizontal one follows from the aspect. It is checked against a rendered frame
  rather than trusted - see `tests/test_sloped_short.py`.

## Impacts are not large changes of velocity

The obvious reading of a replay frame is that a marble whose velocity jumped hit
something. It is wrong, and the distribution says so: the 90th percentile of
|dv| over 21 600 marble-frames is **4.088**, and gravity over one 60 Hz frame is
245.25 / 60 = **4.0875**. Nine tenths of the "impacts" in a naive reading are
marbles falling.

So the measure here is the change in velocity **that gravity does not explain**.
That is not a filtered version of `dv`; it is a different quantity - the
**impulse a surface applied** - and reading it that way settles what every
threshold in the sound design means:

* a marble in **free fall** touches nothing and scores near zero, however fast
  it is going;
* a marble **resting or rolling** is being held up, so it scores exactly the
  weight it is being held up by, 4.0875, which is why that is the median of the
  whole signal;
* an **impact** scores the impulse above that, so `impacts`' floor of 11 wu/s
  is "about two and a half times the marble's own weight" rather than a number
  somebody liked.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

__all__ = [
    "Clock",
    "Event",
    "HOLD_SECONDS",
    "GRAVITY",
    "impacts",
    "load",
    "project",
    "rolling",
    "screen_track",
]

# The held opening frame, in seconds. The brief allows 0.6 to 0.9; 0.70 is the
# middle of that and makes the finished film 19.87 s, inside the 19.8-20.2 the
# brief asks for with room under the 21 s ceiling.
HOLD_SECONDS = 0.70

# Simulation gravity, from the replay's own `units` block, in wu/s^2.
GRAVITY = 245.25

WIDTH = 1080
HEIGHT = 1920


# --- the clock --------------------------------------------------------------


@dataclass(frozen=True)
class Clock:
    """Replay seconds to finished-film seconds, through the edit and the hold.

    `segments` are the camera track's own edit map: `(out_from, out_to,
    replay_from, replay_to)`, slope one in every one of them. Replay time that
    no window covers is **not in the film** and has no output time at all -
    `at()` returns None for it, which is how three and a half seconds of mixing
    make no sound.
    """

    segments: tuple[tuple[float, float, float, float], ...]
    hold: float = HOLD_SECONDS
    fps: int = 60
    # How many frames the rendered master actually has. **Not the same as the
    # edit map's end.** `build_track` reports a duration of 19.15 s and the
    # renderer walks frames 0 to round(19.15 * 60) inclusive, which is 1150
    # frames - 19.1667 s. Taking the nominal figure instead makes the
    # soundtrack a frame shorter than the picture, which is exactly the kind of
    # drift that shows up as a click at the end of an export.
    master_frames: int = 1150

    @property
    def hold_frames(self) -> int:
        return int(round(self.hold * self.fps))

    @property
    def frames(self) -> int:
        """Frames in the finished film, held opening included."""
        return self.hold_frames + self.master_frames

    @property
    def duration(self) -> float:
        """The finished film's length, in seconds, to the frame."""
        return self.frames / float(self.fps)

    def at(self, replay: float) -> float | None:
        """Output seconds for a replay instant, or None if it was cut."""
        for out_from, out_to, replay_from, replay_to in self.segments:
            if replay_from - 1e-9 <= replay <= replay_to + 1e-9:
                return self.hold + out_from + (replay - replay_from)
        return None

    def replay_at(self, output: float) -> float | None:
        """The inverse: what the frame at this output second is showing."""
        inside = output - self.hold
        if inside < 0.0:
            # The hold shows the master's first frame, over and over.
            return self.segments[0][2]
        for out_from, out_to, replay_from, replay_to in self.segments:
            if out_from - 1e-9 <= inside <= out_to + 1e-9:
                return replay_from + (inside - out_from)
        return None

    def window(self, name_index: int) -> tuple[float, float]:
        """One window's output span, hold included."""
        segment = self.segments[name_index]
        return (self.hold + segment[0], self.hold + segment[1])


def load(
    replay_path: str,
    track_path: str,
    master_frames: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Clock]:
    """The replay, the camera track and the clock that joins them.

    `master_frames` is the rendered master's own frame count; without it the
    renderer's rule is reproduced - frames 0 to `round(duration * fps)`
    inclusive - which is what V19 has.
    """
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(track_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    segments = tuple(
        (
            float(row["out"][0]),
            float(row["out"][1]),
            float(row["replay"][0]),
            float(row["replay"][1]),
        )
        for row in track["edit"]
    )
    fps = int(track.get("fps", 60))
    if master_frames is None:
        master_frames = int(round(float(track["duration"]) * fps)) + 1
    return replay, track, Clock(segments, fps=fps, master_frames=master_frames)


# --- what happened ----------------------------------------------------------


@dataclass(frozen=True)
class Event:
    """One physical thing, at one output second, with a strength."""

    kind: str
    at: float                     # output seconds
    replay: float
    marble: int
    magnitude: float = 0.0        # wu/s of velocity gravity cannot explain
    where: tuple[float, float, float] = (0.0, 0.0, 0.0)   # simulation units
    module: str = ""
    detail: dict[str, Any] = field(default_factory=dict)


def residuals(replay: dict[str, Any], clock: Clock) -> list[Event]:
    """Every frame's contact impulse, unthinned: `|dv - g dt|`.

    Free fall scores near zero, a supported marble scores its own weight
    (4.0875 at 60 Hz) and a contact scores the impulse above that. Nothing is
    filtered here: this is the raw signal, and both the discrete impacts and the
    continuous rattle are read off it.
    """
    fps = float(replay.get("replay_fps", 60.0))
    drop = GRAVITY / fps
    out: list[Event] = []
    previous: dict[int, tuple[float, float, float]] = {}
    for frame in replay["frames"]:
        when = float(frame["t"])
        output = clock.at(when)
        for sample in frame["marbles"]:
            marble = int(sample["id"])
            velocity = tuple(float(value) for value in sample["v"])
            before = previous.get(marble)
            previous[marble] = velocity
            if before is None or output is None:
                continue
            residual = (
                velocity[0] - before[0],
                velocity[1] - before[1] + drop,
                velocity[2] - before[2],
            )
            magnitude = math.sqrt(sum(value * value for value in residual))
            if magnitude <= 0.0:
                continue
            out.append(
                Event(
                    kind="impact",
                    at=output,
                    replay=when,
                    marble=marble,
                    magnitude=magnitude,
                    where=tuple(float(value) for value in sample["p"]),
                    module=str(sample.get("in") or ""),
                )
            )
    out.sort(key=lambda event: event.at)
    return out


def contact_energy(
    replay: dict[str, Any], clock: Clock, ceiling: float = 11.0
) -> list[tuple[float, float]]:
    """Per output frame, `(output second, rattle)` in [0, 1] from small contacts.

    A marble riding a banked cradle is corrected by it a hundred times a second,
    and each correction is a real velocity change that gravity did not make. As
    *events* those are useless - at a floor of 6 wu/s the race has 83 of them a
    second, which is the arcade gunfire the brief forbids - but as a **texture**
    they are exactly the rattle the machine has. So everything under `ceiling`
    is summed per frame and drives the bed instead of firing a cue.
    """
    fps = float(replay.get("replay_fps", 60.0))
    drop = GRAVITY / fps
    rows: list[tuple[float, float]] = []
    previous: dict[int, tuple[float, float, float]] = {}
    for frame in replay["frames"]:
        when = float(frame["t"])
        output = clock.at(when)
        total = 0.0
        for sample in frame["marbles"]:
            marble = int(sample["id"])
            velocity = tuple(float(value) for value in sample["v"])
            before = previous.get(marble)
            previous[marble] = velocity
            if before is None:
                continue
            residual = (
                velocity[0] - before[0],
                velocity[1] - before[1] + drop,
                velocity[2] - before[2],
            )
            magnitude = math.sqrt(sum(value * value for value in residual))
            if magnitude < ceiling:
                total += magnitude
        if output is not None:
            rows.append((output, total))
    rows.sort()
    if not rows:
        return rows
    largest = max(row[1] for row in rows) or 1.0
    return [(when, value / largest) for when, value in rows]


def impacts(
    replay: dict[str, Any],
    clock: Clock,
    floor: float = 11.0,
    refractory: float = 0.11,
    per_window: int = 2,
    window: float = 0.05,
) -> list[Event]:
    """The contacts worth hearing as contacts: loud, isolated and rationed.

    Magnitude alone does not separate an event from a texture. At a floor of
    6 wu/s this race has 1594 contacts in 19 seconds, most of them a cradle
    correcting a marble that is doing nothing interesting, and a cue on each
    would be a rattle with no information in it.

    Three rules, in order, and each of them is about *isolation* rather than
    loudness:

    * `floor` - 11 wu/s is the 99th percentile of the raw signal, so what is
      left is already the top one per cent of contacts;
    * `refractory` - one cue per marble per 0.11 s, keeping the loudest in the
      span, because a marble that lands and settles does so over several frames
      and is one event to a listener;
    * `per_window` - at most two cues anywhere in any 0.05 s, loudest first, so
      eight marbles hitting a spinner at once become a chord rather than a wall.
    """
    candidates = [event for event in residuals(replay, clock) if event.magnitude >= floor]

    # One per marble per refractory span: keep the loudest, drop its neighbours.
    kept: list[Event] = []
    last: dict[int, Event] = {}
    for event in candidates:
        previous = last.get(event.marble)
        if previous is not None and event.at - previous.at < refractory:
            if event.magnitude > previous.magnitude:
                kept[kept.index(previous)] = event
                last[event.marble] = event
            continue
        kept.append(event)
        last[event.marble] = event

    # And a global ration, so a pile-up is a chord and not a wall.
    out: list[Event] = []
    bucket: list[Event] = []
    edge = None
    for event in sorted(kept, key=lambda one: one.at):
        if edge is None or event.at >= edge:
            if bucket:
                out.extend(sorted(bucket, key=lambda one: -one.magnitude)[:per_window])
            bucket = []
            edge = event.at + window
        bucket.append(event)
    if bucket:
        out.extend(sorted(bucket, key=lambda one: -one.magnitude)[:per_window])
    out.sort(key=lambda event: event.at)
    return out


def actuator_move(
    replay: dict[str, Any],
    clock: Clock,
    prefix: str,
    threshold: float = 0.05,
) -> float | None:
    """The output second a group of kinematic parts starts moving, or None.

    The start's mechanisms are in the replay as transforms, so the sound of a
    gate opening can be placed on the frame the gate opens rather than on a
    number somebody typed. On the selected seed `start.paddle` first moves at
    replay 0.317 and `start.panel` - the eighteen trapdoor slats - at 6.117.

    Motion is position change plus a rotation term, summed over the group: the
    paddles swing about their own hinges and barely translate, so a position
    test alone would miss them entirely.
    """
    frames = replay["frames"]
    previous = None
    for frame in frames:
        actuators = frame.get("actuators") or {}
        current = {
            name: value for name, value in actuators.items() if name.startswith(prefix)
        }
        if not current:
            return None
        if previous is not None:
            total = 0.0
            for name, value in current.items():
                before = previous.get(name)
                if before is None:
                    continue
                total += math.dist(before["p"], value["p"])
                dot = sum(a * b for a, b in zip(before["q"], value["q"]))
                total += (1.0 - abs(dot)) * 2.0
            if total > threshold:
                return clock.at(float(frame["t"]))
        previous = current
    return None


def omissions(clock: Clock) -> list[tuple[float, float]]:
    """Where the edit skips time: `(output second, replay seconds dropped)`.

    Read off the map rather than listed, so an edit that stops omitting
    something stops being told about it.
    """
    out: list[tuple[float, float]] = []
    for before, after in zip(clock.segments, clock.segments[1:]):
        dropped = after[2] - before[3]
        if dropped > 1e-6:
            out.append((clock.hold + after[0], dropped))
    return out


def rolling(replay: dict[str, Any], clock: Clock) -> list[tuple[float, float, float]]:
    """Per output frame: `(output second, mean speed, fastest speed)` in wu/s.

    The bed the impacts sit on. Speed rather than energy because what a rolling
    marble does to the ear is pitch and hiss, and both follow speed.
    """
    out: list[tuple[float, float, float]] = []
    for frame in replay["frames"]:
        output = clock.at(float(frame["t"]))
        if output is None:
            continue
        speeds = [
            math.sqrt(sum(float(value) ** 2 for value in sample["v"]))
            for sample in frame["marbles"]
            if sample.get("s") == "running"
        ]
        if not speeds:
            speeds = [0.0]
        out.append((output, sum(speeds) / len(speeds), max(speeds)))
    out.sort(key=lambda row: row[0])
    return out


# --- where it is on the frame ----------------------------------------------


def project(
    camera: Sequence[float],
    aim: Sequence[float],
    fov_deg: float,
    point: Sequence[float],
    width: int = WIDTH,
    height: int = HEIGHT,
) -> tuple[float, float, float] | None:
    """A layout-unit point as `(x px, y px, distance)`, or None if behind.

    Godot's `Camera3D` with the default `keep_aspect` keeps the **vertical**
    angle, so `fov` is the full vertical field and the horizontal one is
    `2*atan(tan(fov/2) * width/height)`. `look_at(aim, Vector3.UP)` leaves no
    roll, so the screen's right is horizontal.
    """
    forward = [aim[axis] - camera[axis] for axis in range(3)]
    reach = math.sqrt(sum(value * value for value in forward))
    if reach < 1e-9:
        return None
    forward = [value / reach for value in forward]
    # `cross(forward, world up)`, which for a camera looking down -Z gives +X.
    #
    # **`cameras.frame_report` writes this vector the other way round**, as
    # `(forward.z, 0, -forward.x)`, and is right to: it only ever asks whether
    # `abs(across)` is inside the half-angle, and flipping `right` flips `up`
    # with it, so both comparisons are unchanged. Placing a *pixel* is the first
    # thing here that can tell left from right, and the first rendered frame it
    # was checked against showed the mark on the wrong side of the marble.
    right = [-forward[2], 0.0, forward[0]]
    length = math.hypot(right[0], right[2])
    if length < 1e-9:
        right = [1.0, 0.0, 0.0]
        length = 1.0
    right = [right[0] / length, 0.0, right[2] / length]
    up = [
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    ]
    offset = [point[axis] - camera[axis] for axis in range(3)]
    depth = sum(offset[axis] * forward[axis] for axis in range(3))
    if depth <= 1e-6:
        return None
    across = sum(offset[axis] * right[axis] for axis in range(3)) / depth
    upward = sum(offset[axis] * up[axis] for axis in range(3)) / depth
    half_up = math.tan(math.radians(fov_deg) * 0.5)
    half_across = half_up * (width / height)
    return (
        (0.5 + 0.5 * across / half_across) * width,
        (0.5 - 0.5 * upward / half_up) * height,
        depth,
    )


def _camera_at(track: dict[str, Any], replay_second: float):
    """The pose the renderer would use, picked and blended exactly as it does."""
    chosen = track["cuts"][-1]
    for cut in track["cuts"]:
        if replay_second <= float(cut["to"]):
            chosen = cut
            break
    rows = chosen["frames"]
    first = float(rows[0][0])
    last = float(rows[-1][0])
    fps = float(track.get("fps", 60))
    at = (min(max(replay_second, first), last) - first) * fps
    low = min(max(int(math.floor(at)), 0), len(rows) - 1)
    high = min(low + 1, len(rows) - 1)
    blend = min(max(at - low, 0.0), 1.0)
    a, b = rows[low], rows[high]

    def mix(index: int) -> float:
        return a[index] + (b[index] - a[index]) * blend

    return (
        (mix(1), mix(2), mix(3)),
        (mix(4), mix(5), mix(6)),
        mix(7),
    )


def screen_pan(
    replay: dict[str, Any],
    track: dict[str, Any],
    events: Iterable["Event"],
    max_pan: float = 0.55,
) -> list[float]:
    """Where each event sits in the stereo field, from where it is on the frame.

    A contact is panned by the pixel it happened on, not by its world position:
    the camera swings round the course, so a marble on the left of the machine
    can be on the right of the picture, and the ear should agree with the eye.
    Events off the edge of the frame are clamped to the edge rather than pushed
    further, and anything behind the lens sits centre.
    """
    scale = float(replay.get("units", {}).get("render_scale", 0.57))
    out: list[float] = []
    for event in events:
        camera, aim, fov = _camera_at(track, event.replay)
        point = tuple(value * scale for value in event.where)
        placed = project(camera, aim, fov, point)
        if placed is None:
            out.append(0.0)
            continue
        offset = (placed[0] / WIDTH) * 2.0 - 1.0
        out.append(max(-1.0, min(1.0, offset)) * max_pan)
    return out


def screen_track(
    replay: dict[str, Any],
    track: dict[str, Any],
    clock: Clock,
    marble: int,
    window: tuple[float, float],
) -> list[tuple[float, float, float, float]]:
    """One marble's `(output second, x px, y px, radius px)` over a window.

    Output seconds, so a caller drawing on the finished film can index it
    directly. Frames where the marble is behind the lens are left out.
    """
    scale = float(replay.get("units", {}).get("render_scale", 0.57))
    radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    out: list[tuple[float, float, float, float]] = []
    for frame in replay["frames"]:
        when = float(frame["t"])
        output = clock.at(when)
        if output is None or not (window[0] <= output <= window[1]):
            continue
        sample = next(
            (one for one in frame["marbles"] if int(one["id"]) == marble), None
        )
        if sample is None:
            continue
        camera, aim, fov = _camera_at(track, when)
        point = tuple(float(sample["p"][axis]) * scale for axis in range(3))
        placed = project(camera, aim, fov, point)
        if placed is None:
            continue
        x, y, depth = placed
        half_up = math.tan(math.radians(fov) * 0.5)
        size = (radius / depth) / half_up * (HEIGHT * 0.5)
        out.append((output, x, y, size))
    return out
