"""Racing camera rigs: what the lens is doing, and who it is doing it to.

V28's camera answers "where should the lens be for this event". This one
answers **"where is the lens now, given where it was"**, which is a different
question and the reason the V28 film reads as coverage rather than as a race.

Three parts, and they are deliberately separate so a second course can reuse
them:

    active_pack     who the camera is attached to        - a race question
    Rig             how a lens stands relative to them   - a camera question
    build_track     the two, integrated over time        - the film

## The active pack

The viewer picked a colour and we do not know which. That single fact rules out
following the leader: a leader-locked camera abandons seven of the eight
marbles the opening asked the viewer to care about, and it abandons them
exactly when the interesting thing is happening behind. So the camera is
attached to a **group**, defined once and measured rather than described:

> The active pack is the leader, plus every racer within `PACK_GAP` of the
> leader **in course arc length**, floored at `PACK_MIN` racers and capped at
> `PACK_MAX`.

- **Arc length, not world distance.** On a folded course a racer eight world
  units from the leader can be a leg behind them. Gaps are measured along the
  spine, which is how a race measures them.
- **The floor is what handles an escape.** If the leader breaks clear while
  five fight behind, the gap test alone would return a single racer and the
  camera would frame an empty leader. The floor of three means the anchor sits
  *between* the leader and the chasers and the frame widens to hold both -
  which is the honest answer to a question the brief poses and does not settle:
  it neither abandons the leader nor pretends the fight is not the story.
- **The cap is what stops one tail racer destroying the framing.** A field
  strung over forty units solved for at 34% of frame width puts the lens
  eighty units out, and V28 recorded exactly that failure.

`race2.flow` reports how often the floor and the cap bind, so what the rule
costs is visible rather than assumed.

## Rigs

A `Rig` is six numbers and a name. It says how far behind the pack the lens
trails **along the spine**, how far out it stands, how much it adds to the
rail's height, how far ahead it looks, what lens it uses and how big the pack
should be in frame. Everything else - which way is out, how high is clear - is
the rail's, already solved against the course.

That division is what makes the rigs reusable. `chase_rear_3q` on a different
course is the same six numbers against that course's rail.

## Smoothing: critically damped, on the rig's own parameters

Nothing here smooths a world position after the fact. The springs run on

    s_cam    where the lens is along the course
    reach    how far out it stands
    lift     how much above the rail it sits
    fov      the lens
    aim      the point it is looking at

and the world position is **constructed** from the smoothed values. The
difference matters: smoothing a solved world position lets the lens leave the
rail - which is the one place the course is known to be clear - and pulls it
across geometry on every corner. Smoothing the arc length keeps the lens on the
rail by construction and still removes every step.

The spring is the standard implicit critically-damped integrator: unconditionally
stable, no overshoot, no ringing, and a closed form per frame, so the track is a
pure function of the replay and two runs agree to the byte.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field, replace
from typing import Any, Sequence

from sloped.scale import SIM_TO_LAYOUT

from race2.spine import Rail, Spine, camera_rail

__all__ = [
    "Rig",
    "RIGS",
    "Shot",
    "Plan",
    "PackTrack",
    "active_pack",
    "build_track",
    "write_track",
    "PACK_GAP",
    "PACK_MIN",
    "PACK_MAX",
]

# --- the active pack ---------------------------------------------------------

# How far behind the leader, in layout units of course arc, a racer may be and
# still be part of the contest the camera is filming. 4.5 is about eight marble
# diameters, and on the switchyard's 176 units it is a thirty-ninth of the
# course - close enough that a viewer reads the two as racing each other.
#
# 6.0 and a cap of five were tried first and cost racer size for nothing: the
# wider pack is more strung out, the rig has to trail further to keep its back
# marker in front of the lens, and the racers came out at 80 pixels against 85.
# No other measure moved. The tighter group is the same contest filmed closer.
PACK_GAP = 4.5
# Never fewer than this many, whatever the gaps: see the module docstring on
# what happens when a leader escapes.
PACK_MIN = 3
# And never more, whatever the gaps: a frame solved for eight abreast is a frame
# of eight dots.
PACK_MAX = 4

FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920

# The marble, in layout units, for the framing solve.
MARBLE_RADIUS = 0.285


def horizontal_half_angle(fov_deg: float) -> float:
    """The horizontal half-angle of the portrait delivery frame."""
    return math.atan(
        math.tan(math.radians(fov_deg) * 0.5) * (FRAME_WIDTH / FRAME_HEIGHT)
    )


def active_pack(
    order: Sequence[int],
    arcs: dict[int, float],
    gap: float = PACK_GAP,
    least: int = PACK_MIN,
    most: int = PACK_MAX,
) -> list[int]:
    """Which racers the camera is attached to, in rank order.

    `order` is the race's own sticky ranking - the one with `LEAD_MARGIN`
    hysteresis, so it does not swap twice a frame on marbles that are level -
    and `arcs` is each racer's progress along the spine.
    """
    ranked = [m for m in order if m in arcs]
    if not ranked:
        return []
    front = arcs[ranked[0]]
    chosen = [m for m in ranked if front - arcs[m] <= gap]
    if len(chosen) < least:
        chosen = ranked[:least]
    return chosen[:most]


# --- rigs --------------------------------------------------------------------


@dataclass(frozen=True)
class Rig:
    """How one kind of racing shot stands relative to the pack."""

    name: str
    # Layout units of course arc the lens trails the pack by. **This is the
    # number that preserves screen direction through a switchback**: the lens
    # is behind the pack *on the course*, so when the course reverses the lens
    # reverses with it and the racers still recede from frame.
    trail: float
    # Nominal stand-off from the channel. The rail is solved at this reach, so
    # it is also the closest the lens will come.
    reach: float
    # Added to the rail's height. Negative lowers the shot toward the racers.
    lift: float = 0.0
    # Layout units ahead of the pack that the look-ahead point sits at.
    lead: float = 11.0
    # How much of the aim is that point rather than the pack itself.
    look_ahead: float = 0.28
    fov: float = 35.0
    # What fraction of frame width the framed group should span.
    target_width: float = 0.34
    # How many racers, in rank order, the framing solve keeps on screen. The
    # active pack by default; the whole field for the opening, where the promise
    # being made is that all eight are there and one of them is yours.
    frame_count: int = PACK_MAX
    # An azimuth this shot holds instead of the rail's, in degrees **relative to
    # the course's own downhill direction**, handed back to the rail over
    # `azimuth_blend` seconds. `None` means ride the rail from the first frame.
    #
    # **One shot needs this and the reason is the starting grid.** The rail
    # stands the lens downhill of the channel, which is the direction the
    # switchyard's eight bays are spread along - so the opening frame of the
    # first build was eight marbles in a line receding from the lens, one behind
    # another, which is the exact opposite of what PICK A COLOUR needs. A
    # quarter turn off the rail puts the row across the frame, and the blend
    # back to the rail is the opening camera move rather than a correction.
    azimuth_hold: float | None = None
    azimuth_blend: float = 1.6
    # How far the framing solve may pull back, as a multiple of `reach`. The
    # rail is solved at the nominal, so the floor is 1.0 - closer than that and
    # the clearance the rail proved no longer applies. The ceiling is per rig
    # because the opening needs a different one: **eight marbles abreast on an
    # 8.2-unit bay row simply do not fit inside 1.75 times a nine-unit reach**,
    # and no choice of lens changes that - if a row that wide fills 80% of a
    # 1080 frame then each 0.57-unit marble is 64 pixels, and the only question
    # is whether the solve is allowed to stand far enough back to deliver it.
    reach_span: tuple[float, float] = (1.0, 1.75)
    # Whether the reach is **authored** for the length of the azimuth hold
    # rather than solved. The opening needs it: while the lens swings ninety
    # degrees from behind the grid onto the rail, the field's apparent width
    # swings with it, and a solve chasing that number drove the reach from 21
    # units out to 12 and back to 21 inside a second - the camera pumping in
    # and out while the race launched. Through the hold the composition is the
    # one the first frame was built for, and the solve takes over as the swing
    # finishes.
    reach_hold: bool = False
    # How far the lens may breathe with the group, in degrees either side of
    # `fov`. Small everywhere except the run-in, which has to hold a field
    # arriving across a nine-unit run-out deck without the lens retreating
    # twenty units downcourse to do it - and downcourse of the last hairpin is
    # where the last hairpin gets between the lens and the racers.
    breath: float = 2.5
    # Extra height the lens takes on **once the leader crosses the line**, and
    # over how many seconds.
    #
    # The run-out is a twelve-unit dish and the field spreads right across it,
    # so a lens held at the sprint's own height is a camera looking *along* a
    # deck at marbles standing on it: at -1.2 under the rail a fifth of the
    # leading group is behind the deck's own lip, and V28 recorded the same
    # defect from the same place. Three units of rise fixes it.
    #
    # It is keyed on the crossing rather than on a time because that is what it
    # is *for* - the shot stays low through the sprint, where low is the whole
    # drama, and cranes up as the winner goes through, which is where the
    # subject stops being a contest and becomes a field arriving. A rise is not
    # a cut: the hard rule holds.
    lift_after_line: float = 0.0
    # Over how many layout units of arc past the line the rise happens. In arc
    # rather than in seconds, so it is keyed to where the racers are and not to
    # how fast this particular seed's were going.
    lift_rise: float = 3.5
    # Spring half-lives, in seconds.
    follow: float = 0.24
    aim_follow: float = 0.20
    reach_follow: float = 0.50
    note: str = ""

    def with_(self, **changes) -> "Rig":
        return replace(self, **changes)


# The six primitives. Every candidate camera is built from these and nothing
# else, which is what makes the comparison about editing rather than about one
# candidate having been given a better lens.
RIGS: dict[str, Rig] = {
    # Behind and a little out: the default travelling shot. The course ahead
    # occupies the far third of frame, the pack the near two thirds.
    "chase_rear_3q": Rig(
        "chase_rear_3q", trail=8.5, reach=10.5, lift=0.0, lead=12.0,
        look_ahead=0.30, fov=34.0, target_width=0.40,
        note="behind and out: the pack in the near two thirds, the course in the far third",
    ),
    # Closer and squarer behind. Used where the point is the pack itself rather
    # than what it is about to meet.
    "chase_pack": Rig(
        "chase_pack", trail=6.5, reach=9.5, lift=-0.4, lead=9.0,
        look_ahead=0.22, fov=35.0, target_width=0.36,
        note="close behind the group, with the pack itself as the subject",
    ),
    # Nearly abreast, further out: the pack crosses frame instead of receding.
    # The broadcast side camera, and the one that reads speed best on a straight.
    "chase_side": Rig(
        "chase_side", trail=2.0, reach=12.0, lift=-0.8, lead=8.0,
        look_ahead=0.18, fov=34.0, target_width=0.42, follow=0.28,
        note="abreast and out: the field crosses frame, which is where speed reads",
    ),
    # Tight and low inside a compression, where the contact is.
    "compression_follow": Rig(
        "compression_follow", trail=4.5, reach=8.5, lift=-1.0, lead=6.0,
        look_ahead=0.14, fov=38.0, target_width=0.46, follow=0.18, aim_follow=0.15,
        note="tight and low where the contact is, held past it to read the consequence",
    ),
    # A long trail, so the lens is still entering the bend while the pack is
    # leaving it. **That is what a bend orbit is on a spine-trailed rig**: no
    # special case, just enough lag that the camera swings through the hairpin
    # after the racers and the viewer watches the course turn.
    "bend_orbit": Rig(
        "bend_orbit", trail=12.5, reach=10.0, lift=0.6, lead=14.0,
        look_ahead=0.34, fov=34.0, target_width=0.40, follow=0.34,
        note="a long trail through a hairpin, so the turn happens in front of the lens",
    ),
    # Low, close, almost abreast, and looking at nobody but the racers.
    "finish_chase": Rig(
        "finish_chase", trail=3.0, reach=9.0, lift=-1.2, lead=5.0,
        look_ahead=0.06, fov=34.0, target_width=0.45, reach_span=(1.0, 2.1),
        breath=5.0, lift_after_line=4.4, lift_rise=3.2,
        follow=0.22, aim_follow=0.16,
        note="low and alongside to the line: the closing gap is the whole picture",
    ),
    # The opening. Close enough that eight racers have colours, already moving.
    "hook_release": Rig(
        "hook_release", trail=4.0, reach=9.0, lift=-1.0, lead=7.0,
        look_ahead=0.14, fov=32.0, target_width=0.80, frame_count=8,
        azimuth_hold=90.0, azimuth_blend=1.1, reach_span=(1.0, 3.6),
        reach_hold=True, follow=0.30, aim_follow=0.24, reach_follow=0.28,
        note="eight racers large and the floor going, with the lens already travelling",
    ),
}


@dataclass(frozen=True)
class Shot:
    """One continuous take: a rig, a window, and why it is a separate shot."""

    name: str
    rig: str
    start: float
    end: float
    # Overrides on the rig, so a candidate can lower or tighten one shot
    # without inventing a seventh primitive.
    tweaks: dict[str, float] = field(default_factory=dict)
    note: str = ""
    # What physical moment the cut *into* this shot lands on. Recorded so
    # `race2.flow` can say whether the film cuts on motion or on nothing.
    cut_on: str = ""

    def rig_for(self) -> Rig:
        base = RIGS[self.rig]
        return base.with_(**self.tweaks) if self.tweaks else base

    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Plan:
    """A whole candidate camera: its shots, and the rail they ride."""

    name: str
    shots: list[Shot] = field(default_factory=list)
    fps: int = 60
    note: str = ""

    def duration(self) -> float:
        return max((shot.end for shot in self.shots), default=0.0)

    def cuts(self) -> int:
        """Hard cuts, which is one fewer than the number of shots."""
        return max(len(self.shots) - 1, 0)

    def check(self) -> list[str]:
        out: list[str] = []
        for a, b in zip(self.shots, self.shots[1:]):
            if b.start < a.end - 1e-6:
                out.append(f"{a.name} and {b.name} overlap by {a.end - b.start:.3f} s")
            elif b.start > a.end + 1e-6:
                out.append(f"{a.name} to {b.name} leaves {b.start - a.end:.3f} s uncovered")
        return out


# --- the race, as the camera needs it ----------------------------------------


class PackTrack:
    """Where the pack is, per replay frame, in the terms a rig asks in.

    Built once per race and shared by every candidate, so A, B and C are
    filming provably the same thing: the arcs, the active pack and the anchors
    below are computed here and nowhere else.
    """

    def __init__(self, replay: dict[str, Any], spine: Spine, outcome) -> None:
        self.spine = spine
        self.fps = float(replay.get("replay_fps", 60))
        frames = replay["frames"]
        self.times = [float(frame["t"]) for frame in frames]
        self.ranks = {round(when, 4): order for when, order in outcome.rank_series}
        self._rank_times = sorted(self.ranks)

        # Positions per frame, in layout units.
        self.places: list[dict[int, tuple[float, float, float]]] = []
        for frame in frames:
            row: dict[int, tuple[float, float, float]] = {}
            for sample in frame["marbles"]:
                point = sample["p"] if isinstance(sample, dict) else sample[1]
                marble = sample["id"] if isinstance(sample, dict) else sample[0]
                row[int(marble)] = tuple(float(v) * SIM_TO_LAYOUT for v in point)
            self.places.append(row)

        # Arc length per marble per frame, walked forward with the previous
        # answer as the hint. **Monotone by construction**, which is both what
        # makes it correct on a folded course and what makes it deterministic.
        self.arcs: list[dict[int, float]] = []
        hints: dict[int, float] = {}
        for row in self.places:
            here: dict[int, float] = {}
            for marble, point in row.items():
                hint = hints.get(marble)
                value = spine.progress_of(point, hint)
                if hint is not None and value < hint:
                    value = hint
                here[marble] = value
                hints[marble] = value
            self.arcs.append(here)

        # And the derived per-frame answers.
        self.packs: list[list[int]] = []
        self.anchors: list[tuple[float, float, float]] = []
        self.pack_arcs: list[float] = []
        self.extents: list[float] = []
        self.floor_bound = 0
        self.cap_bound = 0
        for index, (row, arcs) in enumerate(zip(self.places, self.arcs)):
            order = self.order_at(self.times[index])
            ranked = [m for m in order if m in arcs]
            within = [m for m in ranked if (arcs[ranked[0]] - arcs[m]) <= PACK_GAP] if ranked else []
            pack = active_pack(order, arcs)
            if len(within) < PACK_MIN:
                self.floor_bound += 1
            if len(within) > PACK_MAX:
                self.cap_bound += 1
            self.packs.append(pack)
            points = [row[m] for m in pack] or list(row.values())[:1]
            self.anchors.append(tuple(
                sum(p[axis] for p in points) / len(points) for axis in range(3)
            ))
            self.pack_arcs.append(sum(arcs[m] for m in pack) / max(len(pack), 1))
            self.extents.append(
                max((math.dist(a, b) for i, a in enumerate(points) for b in points[i + 1:]),
                    default=2.0 * MARBLE_RADIUS)
            )

    def rates(self, index: int) -> tuple[float, tuple[float, float, float]]:
        """How fast the pack's arc and its anchor are moving, per second.

        A central difference over the neighbouring frames, so it is defined at
        every sample and is a pure function of the replay. Fed to the springs so
        they track a moving pack without the constant lag a damped follower
        otherwise carries - see `Spring`.
        """
        before = max(index - 1, 0)
        after = min(index + 1, len(self.times) - 1)
        span = self.times[after] - self.times[before]
        if span <= 1e-9:
            return 0.0, (0.0, 0.0, 0.0)
        arc = (self.pack_arcs[after] - self.pack_arcs[before]) / span
        anchor = tuple(
            (self.anchors[after][axis] - self.anchors[before][axis]) / span
            for axis in range(3)
        )
        return arc, anchor

    def frame_at(self, seconds: float) -> int:
        return max(0, min(len(self.times) - 1, int(round(seconds * self.fps))))

    def framed_ids(self, index: int, count: int) -> list[int]:
        """The leading `count` racers at a frame, in rank order."""
        row = self.places[index]
        order = self.order_at(self.times[index])
        ranked = [m for m in order if m in row]
        if count >= len(ranked):
            return ranked
        pack = self.packs[index]
        return (pack if len(pack) >= count else ranked)[:count]

    def rear(self, index: int, count: int) -> float:
        """How far behind the pack's own arc the last framed racer is.

        The number a chase rig has to trail by. **A lens that trails the mean
        by less than this has the back of the field level with it or behind
        it**, and a marble level with the lens projects to the edge of the
        frame whatever the reach is - which is where 43% of the opening's
        active pack was going in the first build, with the framing solve
        reporting the group comfortably inside 80% of frame width because the
        marbles it could still see were.
        """
        arcs = self.arcs[index]
        ids = [m for m in self.framed_ids(index, count) if m in arcs]
        if not ids:
            return 0.0
        return max(self.pack_arcs[index] - min(arcs[m] for m in ids), 0.0)

    def framed(self, index: int, count: int) -> list[tuple[float, float, float]]:
        """The leading `count` racers' positions at a frame, for the framing solve.

        The active pack when `count` is the cap, and the whole field when a rig
        asks for all of them - which the opening does, because the promise the
        PICK A COLOUR premise makes is that all eight are on screen.
        """
        row = self.places[index]
        return [row[m] for m in self.framed_ids(index, count)]

    def order_at(self, seconds: float) -> tuple[int, ...]:
        if not self._rank_times:
            return tuple(sorted(self.places[self.frame_at(seconds)]))
        key = min(self._rank_times, key=lambda t: abs(t - seconds))
        return self.ranks[key]

    def describe(self) -> dict[str, Any]:
        sizes = [len(p) for p in self.packs]
        return {
            "frames": len(self.times),
            "mean_pack": round(sum(sizes) / len(sizes), 3),
            "pack_range": [min(sizes), max(sizes)],
            "floor_bound_frames": self.floor_bound,
            "cap_bound_frames": self.cap_bound,
            "mean_extent": round(sum(self.extents) / len(self.extents), 3),
            "max_extent": round(max(self.extents), 3),
        }


# --- the spring --------------------------------------------------------------

# Where a half-life becomes an angular frequency for a critically damped
# system: the step response is (1 + wt)e^-wt, which is half settled at wt =
# 1.6783. Quoted rather than approximated so the half-lives on the rigs mean
# what they say.
HALF_LIFE_OMEGA = 1.67834699


class Spring:
    """A critically damped scalar follower, integrated implicitly.

    Unconditionally stable and free of overshoot at any step size, which is why
    it is this and not a hand-rolled lerp: a lerp with a per-frame coefficient
    is a first-order lag, and a first-order lag on a camera is the rubber-band
    motion the brief rules out. This has the velocity term, so it leads into a
    move and settles out of one without ringing.

    ## Why `step` takes the target's own velocity

    **A critically damped spring tracking a moving target lags it by a constant,
    and the constant is proportional to how fast the target is going.** For this
    integrator the steady-state error against a ramp is `2 * rate / omega`,
    which is `1.19 * half_life * rate`. That is textbook and it is easy to
    forget, and on a racing camera it is not a subtlety - it is the defect.

    Measured on the first build of this branch: the opening shot ended with the
    pack's centroid at **screen x of -1.34**, a third of a frame outside the
    left edge, with every framing solve in the film reporting the group
    comfortably inside its target. Nothing was wrong with the solves. The pack
    was doing 15 layout units a second, the aim spring had a 0.24 s half-life,
    and 1.19 * 0.24 * 15 is 4.3 layout units of lag - which at that shot's
    20-unit depth is exactly the 1.3 half-widths that were missing.

    So the target's velocity is passed in and the spring aims that far ahead of
    it. The lag against a steady ramp cancels; the damping still does its job on
    everything that is not steady, which is what the smoothing is for.
    """

    __slots__ = ("value", "velocity", "omega", "lead")

    def __init__(self, value: float, half_life: float) -> None:
        self.value = float(value)
        self.velocity = 0.0
        self.omega = HALF_LIFE_OMEGA / max(half_life, 1e-3)
        self.lead = 2.0 / self.omega

    def step(self, target: float, dt: float, rate: float = 0.0) -> float:
        target = target + rate * self.lead
        omega = self.omega
        f = 1.0 + 2.0 * dt * omega
        oo = omega * omega
        hoo = dt * oo
        hhoo = dt * hoo
        det = 1.0 / (f + hhoo)
        value = (self.value * f + self.velocity * dt + target * hhoo) * det
        self.velocity = (self.velocity + (target - self.value) * hoo) * det
        self.value = value
        return value


class VectorSpring:
    """Three `Spring`s, so an aim point settles the way a scalar does."""

    __slots__ = ("axes",)

    def __init__(self, value: Sequence[float], half_life: float) -> None:
        self.axes = [Spring(value[axis], half_life) for axis in range(3)]

    def step(self, target: Sequence[float], dt: float,
             rate: Sequence[float] = (0.0, 0.0, 0.0)) -> tuple[float, float, float]:
        return tuple(
            self.axes[axis].step(float(target[axis]), dt, float(rate[axis]))
            for axis in range(3)
        )


# --- building the track ------------------------------------------------------

# How much the lens may breathe with the pack, in degrees either side of the
# rig's own field. Small, and on a 1.4-second half-life, so it is a thing the
# viewer feels rather than sees.
FOV_BREATH = 2.5
FOV_HALF_LIFE = 1.4
HEIGHT_HALF_LIFE = 0.32

# How far from frame centre a framed racer may sit before the look-ahead blend
# is pulled back, as a fraction of the half-frame. 0.70 leaves a fifth of the
# frame outside the racers on the far side, which is where the course ahead
# goes.
FRAME_HOLD_X = 0.70
FRAME_HOLD_Y = 0.80

# How far in front of the lens the last framed racer must stay, in layout units
# of arc. Three units is about five marble diameters: enough that the rearmost
# racer is in front of the camera rather than beside it.
TRAIL_MARGIN = 3.0

# The steepest a shot may look down, in degrees. Past it a three-quarter view
# has become the plan view the brief rules out, and V28 stopped at 44 for the
# same reason. It binds where the rail has had to climb over a hairpin and the
# framing solve has come in close at the same time.
MAX_DEPRESSION = 45.0


def _unit(v: Sequence[float]) -> tuple[float, float, float]:
    span = math.sqrt(sum(float(c) * float(c) for c in v)) or 1.0
    return (float(v[0]) / span, float(v[1]) / span, float(v[2]) / span)


def _basis(position, aim):
    """The lens's forward, right and up, with the camera held level."""
    forward = _unit(tuple(aim[axis] - position[axis] for axis in range(3)))
    right = _unit((-forward[2], 0.0, forward[0]))
    up = (
        right[1] * forward[2] - right[2] * forward[1],
        right[2] * forward[0] - right[0] * forward[2],
        right[0] * forward[1] - right[1] * forward[0],
    )
    return forward, right, _unit(up)


def _screen(points, position, aim, fov):
    """Projected `(x, y)` of each point, in [-1, 1]; behind-lens points dropped."""
    forward, right, up = _basis(position, aim)
    half_up = math.tan(math.radians(fov) * 0.5)
    half_right = half_up * (FRAME_WIDTH / FRAME_HEIGHT)
    out: list[tuple[float, float]] = []
    for point in points:
        offset = [point[axis] - position[axis] for axis in range(3)]
        depth = sum(offset[axis] * forward[axis] for axis in range(3))
        if depth <= 1e-3:
            # Behind the lens: report it as far off frame rather than dropping
            # it, so a solve that has put a racer behind the camera is charged
            # for it instead of being told the frame is empty.
            out.append((9.0, 9.0))
            continue
        out.append((
            sum(offset[axis] * right[axis] for axis in range(3)) / (depth * half_right),
            sum(offset[axis] * up[axis] for axis in range(3)) / (depth * half_up),
        ))
    return out


def _span_of(screen) -> float:
    """Half the horizontal extent of a projected set, as a fraction of width."""
    if not screen:
        return 0.0
    return (max(x for x, _ in screen) - min(x for x, _ in screen)) / 2.0


def _worst(screen) -> float:
    """The furthest any projected point is from frame centre, the wider axis."""
    if not screen:
        return 0.0
    return max(max(abs(x), abs(y) * FRAME_HOLD_X / FRAME_HOLD_Y) for x, y in screen)


def _solve_reach(spine, s_cam, azimuth, height_for, anchor, points, fov,
                 target_width, lo, hi) -> float:
    """How far out to stand so the framed group spans `target_width` of width.

    **Bisected on the projected span, not computed from a world extent.** The
    first build of this branch sized the reach from the greatest distance
    between two racers and treated it as horizontal, which is V28's rule; on a
    *trailing* rig that number is mostly depth, and the reach it produced left
    48 to 63 per cent of the active pack outside the frame while reporting the
    group at 20 per cent of frame width. Projecting and measuring is two dozen
    lines and it is the only version that can be checked against the picture.

    `height_for` is a function of the trial reach rather than a number, because
    **the rail defines a depression angle and not a height**. Holding the height
    while the reach doubles halves the angle the lens looks down at, and a lens
    18 units out and 5 up is 15 degrees above a channel whose own guard rail
    needs 20 to see over - which is a rendered frame of the track edge-on as a
    thin white ribbon with the marbles sitting on its lip. That is what the
    first rendered contact sheet of this branch actually looked like.

    Monotone in practice - standing further away subtends less, and rising in
    proportion keeps it so - so a plain bisection converges, and eight steps
    resolve a 20-unit range to 0.08 units, which is under a tenth of a marble.
    """
    if not points:
        return lo

    def span_at(reach: float) -> float:
        position = spine.offset(s_cam, azimuth, height_for(reach), reach)
        return _span_of(_screen(points, position, anchor, fov))

    if span_at(hi) > target_width:
        return hi
    if span_at(lo) <= target_width:
        return lo
    low, high = lo, hi
    for _ in range(8):
        mid = 0.5 * (low + high)
        if span_at(mid) > target_width:
            low = mid
        else:
            high = mid
    return high


def _hold_aim(anchor, ahead, look_ahead, position, points, fov):
    """Blend the aim toward the course ahead, but never out of the racers.

    The brief's rule is that camera *position* follows the racers while camera
    *orientation* reveals what is coming. The trap on a switchback course is
    that "twelve units ahead along the course" can be ninety degrees off the
    direction of travel - round a hairpin it is almost behind - so a fixed
    30 per cent blend swings the lens off the pack entirely. Measured on the
    first build: the group sat at screen x 0.38 to 1.29 on a straight where its
    own spread was under three layout units, which is to say it was off the
    side of the frame for a reason that had nothing to do with how spread out
    it was.

    So the blend is a **ceiling, not a value**. The largest fraction that keeps
    every framed racer inside `FRAME_HOLD_X` of centre is taken, by bisection,
    and on a hairpin that is a good deal less than the authored number. The
    look-ahead is then self-limiting: strong where the course runs straight
    ahead and where it costs nothing, weak exactly where it would cost the
    racers.
    """
    if look_ahead <= 1e-6 or not points:
        return anchor

    def aim_at(blend: float):
        return tuple(
            anchor[axis] * (1.0 - blend) + ahead[axis] * blend for axis in range(3)
        )

    if _worst(_screen(points, position, aim_at(look_ahead), fov)) <= FRAME_HOLD_X:
        return aim_at(look_ahead)
    low, high = 0.0, look_ahead
    for _ in range(6):
        mid = 0.5 * (low + high)
        if _worst(_screen(points, position, aim_at(mid), fov)) <= FRAME_HOLD_X:
            low = mid
        else:
            high = mid
    return aim_at(low)


def build_track(
    plan: Plan,
    pack: PackTrack,
    spine: Spine,
    rails: dict[float, Rail] | None = None,
) -> dict[str, Any]:
    """The camera track, in the JSON the Race #2 renderer already reads.

    One pass per shot. The springs are **re-seeded at each cut** rather than
    carried across it: a hard cut is a new camera, and a spring that carried its
    velocity through one would fly the new lens away from where it was placed.
    Inside a shot nothing is re-seeded, which is what makes a six-second take
    one continuous move.

    Per frame, in order:

        1. where the pack is, and how far along the course
        2. the arc the lens should be at, sprung
        3. the rail's azimuth and height there, plus the rig's lift
        4. the reach that frames the group, solved on screen and sprung
        5. the aim, blended toward the course ahead as far as the racers allow
    """
    rails = {} if rails is None else dict(rails)
    fps = plan.fps
    dt = 1.0 / fps
    cuts: list[dict[str, Any]] = []

    for shot in plan.shots:
        rig = shot.rig_for()
        rail = rails.get(round(rig.reach, 3))
        if rail is None:
            rail = camera_rail(spine, reach=rig.reach)
            rails[round(rig.reach, 3)] = rail

        first = int(round(shot.start * fps))
        last = max(int(round(shot.end * fps)), first + 1)
        times = [index / fps for index in range(first, last)]
        lo, hi = rig.reach * rig.reach_span[0], rig.reach * rig.reach_span[1]

        # Seed every spring at the value the rig asks for on its first frame,
        # so a shot opens exactly where it was authored and settles from there.
        index = pack.frame_at(times[0])
        s_seed = max(pack.pack_arcs[index] - _trail(rig, pack, index), 0.0)
        azimuth, height = _pose(rail, spine, rig, s_seed, times[0], shot.start,
                                pack.pack_arcs[index])
        seed_reach = _solve_reach(
            spine, s_seed, azimuth, _riser(height, rig.reach), pack.anchors[index],
            pack.framed(index, rig.frame_count), rig.fov, rig.target_width, lo, hi,
        )
        arc_spring = Spring(s_seed, rig.follow)
        reach_spring = Spring(seed_reach, rig.reach_follow)
        fov_spring = Spring(rig.fov, FOV_HALF_LIFE)
        # **The height is sprung too, and the crane at the line is why.**
        # Everything else the lens stands on is a smooth function of the arc,
        # but the arc itself is the *mean* of the active pack - so when a racer
        # finishes and the pack's membership changes, the mean steps, and any
        # term keyed on it steps with it. Measured: the crane-up fired across
        # one such step and moved the lens 108 layout units a second for two
        # frames at 16.05 s, which is a jump cut wearing a camera move.
        height_spring = Spring(height, HEIGHT_HALF_LIFE)
        # Seeded on the *solved* aim, not on the raw anchor. Seeding on the
        # anchor makes the first frame of every shot look somewhere the rest of
        # the shot never looks, which the cut metric reads - correctly - as the
        # pack jumping most of a frame width at the cut.
        aim_spring = VectorSpring(
            _hold_aim(
                pack.anchors[index],
                spine.point_at(min(pack.pack_arcs[index] + rig.lead, spine.length)),
                rig.look_ahead,
                spine.offset(s_seed, azimuth, height, reach_spring.value),
                pack.framed(index, rig.frame_count),
                rig.fov,
            ),
            rig.aim_follow,
        )

        rows: list[list[float]] = []
        for when in times:
            index = pack.frame_at(when)
            s_pack = pack.pack_arcs[index]
            anchor = pack.anchors[index]
            framed = pack.framed(index, rig.frame_count)

            arc_rate, anchor_rate = pack.rates(index)
            s_cam = arc_spring.step(
                max(s_pack - _trail(rig, pack, index), 0.0), dt, arc_rate
            )
            azimuth, height = _pose(rail, spine, rig, s_cam, when, shot.start, s_pack)
            height = height_spring.step(height, dt)
            rise = _riser(height, rig.reach)
            solved = _solve_reach(spine, s_cam, azimuth, rise, anchor, framed,
                                  rig.fov, rig.target_width, lo, hi)
            if rig.reach_hold and rig.azimuth_hold is not None:
                solved = _mix(seed_reach, solved, _blend(rig, when, shot.start))
            reach = reach_spring.step(solved, dt)
            position = spine.offset(s_cam, azimuth, rise(reach), reach)

            # A tighter lens when the group is compressed, a wider one when it
            # is spread - within FOV_BREATH, on a long half-life.
            spread = max(-1.0, min(1.0, (_span_of(
                _screen(framed, position, anchor, rig.fov)
            ) - rig.target_width) / max(rig.target_width, 0.05)))
            fov = fov_spring.step(rig.fov + rig.breath * spread, dt)

            ahead = spine.point_at(min(s_pack + rig.lead, spine.length))
            target = _hold_aim(anchor, ahead, rig.look_ahead, position, framed, fov)
            aim = aim_spring.step(target, dt, anchor_rate)

            rows.append([
                round(when, 6),
                round(position[0], 5), round(position[1], 5), round(position[2], 5),
                round(aim[0], 5), round(aim[1], 5), round(aim[2], 5),
                round(fov, 3),
            ])

        cuts.append({
            "name": shot.name,
            "mode": shot.rig,
            "subject": "",
            "note": shot.note or rig.note,
            "cut_on": shot.cut_on,
            "side": 1.0,
            "from": round(shot.start, 6),
            "to": round(shot.end, 6),
            "frames": rows,
        })

    return {
        "fps": fps,
        "duration": round(plan.duration(), 6),
        "course": spine.course.concept or spine.course.title,
        "camera": plan.name,
        "modes": {shot.name: shot.rig for shot in plan.shots},
        "cuts": cuts,
    }


def _riser(height: float, nominal: float):
    """The height a lens stands at, as a function of how far out it is.

    The rail solves a height at its own nominal reach; what that pair really
    encodes is an **angle**, and the flown reach is often twice the nominal
    because the framing solve has pulled back to hold the group. So the height
    travels with it, and the depression the rail chose is the depression the
    shot gets.
    """
    scale = min(height / max(nominal, 1e-6), math.tan(math.radians(MAX_DEPRESSION)))

    def at(reach: float) -> float:
        return scale * reach

    return at


def _mix(a: float, b: float, t: float) -> float:
    return a * (1.0 - t) + b * t


def _blend(rig: Rig, when: float, started: float) -> float:
    """Smoothstep through a rig's azimuth hold: 0 while held, 1 once handed back."""
    t = min(max((when - started) / max(rig.azimuth_blend, 1e-6), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def _trail(rig: Rig, pack: PackTrack, index: int) -> float:
    """How far behind the pack the lens should be, in layout units of arc.

    The rig's authored trail, or enough to keep the back of the framed group
    `TRAIL_MARGIN` in front of the lens - whichever is more. The authored number
    is what the shot wants; this is what the field allows.
    """
    return max(rig.trail, pack.rear(index, rig.frame_count) + TRAIL_MARGIN)


def _pose(rail: Rail, spine: Spine, rig: Rig, s_cam: float, when: float,
          started: float, s_pack: float = 0.0) -> tuple[float, float]:
    """The lens's world azimuth and height above the channel at one instant.

    The rail's, unless the rig holds its own azimuth for the opening of its
    shot - see `Rig.azimuth_hold`, and the starting grid for why one shot needs
    to.
    """
    azimuth, height = rail.at(s_cam)
    if rig.azimuth_hold is not None:
        base = spine.downhill_azimuth + rig.azimuth_hold
        blend = _blend(rig, when, started)
        # Unwrap so the shorter way round is always taken.
        while azimuth - base > 180.0:
            azimuth -= 360.0
        while azimuth - base < -180.0:
            azimuth += 360.0
        azimuth = _mix(base, azimuth, blend)
    lift = rig.lift
    if rig.lift_after_line > 0.0:
        # How far past the line the pack is, as a fraction of the rise. The
        # spine's tail is 8 units and the rise is quoted in seconds, so it is
        # converted at the speed a marble actually leaves the line - about six
        # layout units a second on the run-out.
        past = (s_pack - spine.racing_length) / max(rig.lift_rise, 1e-6)
        ramp = min(max(past, 0.0), 1.0)
        lift += rig.lift_after_line * ramp * ramp * (3.0 - 2.0 * ramp)
    return azimuth, height + lift


def write_track(track: dict[str, Any], path: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(track, handle, separators=(",", ":"))
        handle.write("\n")
    return path
