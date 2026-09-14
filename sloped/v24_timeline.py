"""V24: a tighter Short, cut out of the V22.1 picture and nothing else.

V22.1 went up at 26.533 s and the retention numbers came back:

    stayed to watch          19.6%
    average watch            ~24 s
    approximate viewed       ~89%

The body of the race is holding people. What it is being asked to hold them
*through* is 3.500 s of course preview before the race starts and 3.617 s of
machine after the winner has crossed. So V24 is a **timeline** pass: the same
master, the same replay, the same lenses, the same physics, and a question
about which of its frames the film keeps.

The target is roughly **18.5 to 20.5 s**, and deliberately not 20.000 exactly -
a whole-frame edit lands where the frames land.

## What this module is allowed to do, and what it is not

One honest operation, twice:

* **drop whole frames from inside the master and close the gap.** Every
  surviving frame keeps the replay instant it always had; nothing is resampled,
  reordered, repeated or held longer than 1/fps.
* **stop the master early.** A tail trim is not a join at all - there is no far
  side - so it costs no continuity and it is the cheapest second the film has.

`presentation.omit_frames` is the production function for the first of those and
this pass does **not** use it, for a reason it found rather than assumed: it
emits one segment per window of the edit map, which is right for every cut
production has ever made and wrong for a cut in the middle of a window. See
`build`, which carries the reproduction.

There is no speed change here, no interpolation, no blending and no physics.
`sloped/presentation.py`, `sloped/cameras.py`, `tools/sloped_short.py` and
`tools/sloped_short_qc.py` are not touched by this pass; this module imports
from the first of them and nothing imports from here.

**The course preview is gone entirely.** It is 210 frames of separate footage
joined by `concat`, so removing it is removing a file from the command rather
than cutting anything: `Clock.prefix` goes to 0.0 and the film starts on the
held race frame. That alone is 3.500 s.

## The frame the renderer actually drew

Every cut in `cameras_v221_5432.json` repeats its boundary frame - cut 0's last
entry and cut 1's first entry are both at output 1.850 - so the 1347 rows in
the track become 1340 rendered frames, and *which* row was dropped decides what
replay instant every master frame after the first boundary is showing. The two
readings differ by one frame everywhere, which is exactly the size of the errors
this pass is trying to measure.

It was settled from the pixels rather than from the code. The start lens hands
over to the chase at replay 6.700, and that is the one hard lens change in the
master, so it is visible as a spike in the frame-to-frame difference:

    master 270->271   mean |dpix|   2.410
    master 271->272   mean |dpix|   2.416
    master 272->273   mean |dpix|   2.420
    master 273->274   mean |dpix|  56.046      <- the lens change
    master 274->275   mean |dpix|   0.857

So the renderer keeps each cut's frames and drops the **first** row of every cut
after the first, and master frame `f` shows the replay instant that
`presentation._window_of` assigns to output `f / 60` - production's own reading.
`load_master` rebuilds the per-frame pose list the same way and asserts the two
agree to 0.0 s, so a future track that concatenates differently fails here
rather than silently mis-placing every measurement below.

## The bar: the join the shipped film already contains

An omission is not good or bad in the abstract; it is better or worse than one
the audience has already accepted. V22.1's start omission - `b116`, four rotor
revolutions taken out of the constant-rate spin - is that reference, measured on
the delivered master:

    marbles move        0.50 wu,  34.6 px mean,  84.3 px worst
                        = 0.47 marble widths mean, 1.12 worst
    camera steps        0.054 layout units - one frame's worth of its own orbit
    blades step         24.86 degrees, where a frame step is 12.41

Every candidate join below is quoted in the same units and against that bar.
`MARBLE_WIDTH_BAR` is it, rounded up a little.

## The rotor is the constraint, and it is arithmetic

The start's drum spins four identical blades at 13.0 rad/s, which is 12.4139
degrees a frame. An omission inside that spin is invisible only if the blades
come back where the next frame would have put them anyway - the gap in frame
steps, less the one step a join is entitled to, has to be a whole number of
quarter turns. At 60 Hz a quarter turn is 7.2498 frames, so only whole
revolutions land near an integer, and one revolution is 29 frames (360.03
degrees, 0.03 of error).

**The shipped join is one frame off that lock.** `v221_shuffle.PLANS["b116"]`
asks for `cut_at=2.05, resume_at=4.0`, which is 117 frame steps and four exact
revolutions - but replay 4.000 is the duplicated boundary row the renderer drops,
so the first frame the film actually resumes on is 4.016667 and the gap is 118
steps. The blades step 24.86 degrees across the join instead of 12.41: one extra
frame of rotation, 12.44 degrees of phase error where the pass's own report
claims a hundredth of a degree.

It is not worth fixing and this pass does not try - a one-frame hiccup in a
12.4-degree-a-frame spin is under the noise, and the pixels agree (the join
differs by 4.09 where its neighbours differ by 3.3 to 3.5). It matters here for
one reason: it changes the arithmetic of **extending** that omission. Adding a
whole revolution would keep the error at 12.44; adding **28** frames instead
makes the gap 146 steps, 145 of which is five exact revolutions, and the blades
land within 0.09 degrees. The extension is a frame shorter than the thing it is
extending by.

## The drum shot's tail cannot be trimmed at all, and the reason is three frames

The obvious second lever is the other edge: end the shuffle shot earlier and let
the same omission carry the difference. It does not exist, and the arithmetic
says why. Resuming at master frame 140 needs `256 - last ≡ 0 (mod 29)`, so the
last drum frame can only be **111, 82, 53 or 24** - and the rotor does not take
hold until replay 1.6167, which is **master frame 85**. Every phase-safe trim
lands before the blades are turning, so the join would show a stationary rotor
cutting to one at 13.0 rad/s:

    drum ends   replay    marbles              machine
    111         2.0500    0.53 marble widths   same state          <- shipped
     82         1.5667    0.89                 0.00 -> 13.00 rad/s
     53         1.0833    2.32                 0.00 -> 13.00 rad/s
     24         0.6000    4.16                 0.00 -> 13.00 rad/s

82 misses by three frames. `DRUM_FALSIFIED` records it rather than offering it,
because "trim the shuffle" is the first thing any later pass will reach for.

## The one place a time skip is free

A join placed exactly on an **existing lens change** costs nothing new, because
the film already cuts there and a cut is what a cut looks like. The master has
one: the start lens hands to the chase between frames 273 and 274. Measured with
nothing omitted at all, that boundary already moves the marbles 162.7 px - 2.51
marble widths - and the camera 19.3 layout units, because it is a different lens
in a different place. Omitting 21 further frames into it moves them **158.4 px,
2.38 widths**: slightly *less*, and well inside the noise of the cut that is
already there.

So the start shot may end early and let the chase pick the field up, and the bar
does not apply to that join. `Join.problems` exempts a join whose two frames are
in different windows for exactly this reason, and reports it against the
unmodified boundary instead.

## Where the time is, measured

Churn - world units of marble travel per marble per second, `v22_timeline`'s and
imported rather than rewritten - over the master's own coverage:

    start, replay 4.02-6.00     0.43 to 1.48     the machine ceremony
    the trap, replay 12.9-14.4  3.18 to 4.75     held against turning blades
    everything else             6 to 48

and the screen-space sweep says the same thing in the units that matter. The
cost of a 30-frame omission, best placement inside each window:

    descent      107 px   1.4 marble widths   camera steps 8.4 units
    obstacle      84 px   1.1                 camera steps 0.75
    fork         102 px   -                   camera steps 9.5
    branches     191 px   -                   camera steps 13.8
    final        182 px   -                   camera steps 0.0

Only the obstacle is affordable, and inside it only the trap. Everywhere else
the chase camera is flying, and an omission moves the whole frame rather than
the marbles in it. **The finish is the worst of all** - the marbles are closest
to the lens there, so a 45-frame cut moves one of them 1235 px - which is why
the finish gives its time back by *stopping*, not by skipping.

## The five places time can come from, and nowhere else

    SPIN          28 frames   the constant-rate spin, phase-exact at 5 revs
    STOPPED       16 frames   rotor halted, blades not yet lifting, nothing moves
    ANTICIPATION  11 or 19    blades up, floor shut, nothing moves
    FALL          17 or 21    the tail of the start shot, on the lens change
    TRAP       20-30 frames   the field held against the blades
    the tail    43-94 frames  stopping the master after a crossing

The first four are the whole of the start's slack: 76 frames, 1.267 s. The
spin-down (4.617-4.917) and the blade lift (5.217-5.650) are machine motion and
an omission across either one changes the machine's state in a single frame -
which is precisely the defect V22 shipped and V22.1 was written to fix. This
module refuses those cuts rather than offering them: see `machine_match`. The
cheapest-looking 30-frame omission anywhere in the start, on the marbles alone,
is master 137 to 168 at 0.13 marble widths - and it straddles the wind-down, so
it is exactly the cut that is not available.

## The floor this puts under the start, which is above the brief's target

The brief asks for start timings around 2.2-2.5, 2.7-3.0 and 3.2 s. Measured to
the descent lens - where the field is on the downhill and the start section is
over - the V22.1 master cannot go below **3.73 s**, and measured to the trapdoor
opening it cannot go below **3.50 s**. The whole of the start's slack is 1.233 s
against a 5.267 s start, and the drum's tail is not trimmable at any setting.

Every shorter start needs one of two things this pass may not do: a camera
re-solve, or a cut across the machine's own state. The candidates report the
number under all three readings of "the start" so the gap is legible rather than
argued - see `start_timings`.

## The camera is the cost nobody pays until the re-render

A phase-exact omission keeps the *blades* continuous. It does not keep the
*camera* continuous, because `v221_shuffle.constant_rate_legs` split the orbit
across the windows the shipped film has, and dropping 28 more frames steps the
lens 28 frames' worth of that orbit - 1.56 layout units, where the shipped join
steps 0.054. That is real and it is visible as parallax, and it is also
**entirely removable by re-solving the track to the new bounds**, which is the
integration step rather than this one. Every join reports it; the proof clips
show it; nothing here pretends it is not there.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Sequence

from sloped.presentation import Clock, HOLD_SECONDS, omit_frames, project
from sloped.v22_timeline import churn, field_at

__all__ = [
    "ANTICIPATION",
    "ANTICIPATION_DEEP",
    "CANDIDATES",
    "DRUM_FALSIFIED",
    "FALL",
    "FALL_DEEP",
    "FPS",
    "Cut",
    "Join",
    "MARBLE_WIDTH_BAR",
    "Master",
    "Plan",
    "REJECTED",
    "RUNTIME_BOUNDS",
    "SEGMENTS",
    "SPIN",
    "STOPPED",
    "TRAP",
    "TRAP_SHORT",
    "build",
    "candidates",
    "check",
    "coverage",
    "crossings",
    "joins",
    "kept_frames",
    "load_master",
    "machine_match",
    "machine_state",
    "omissions",
    "phase_error",
    "production_clock",
    "rejected",
    "report",
    "rotor_phase",
    "runs",
    "screen_field",
    "section_times",
    "segment_times",
    "start_timings",
    "tail_after",
]

FPS = 60

# The V22.1 race master, `output/sloped_race_v1/v221/race_master.mp4`. Asserted
# against the track rather than trusted: `load_master` raises if the edit map
# and the concatenated pose list disagree about a single frame.
MASTER_FRAMES = 1340

# V22.1's held opening frame, in frames. `presentation.HOLD_SECONDS` is 0.70 and
# 42 at 60 fps is exactly that; the number is kept in frames here because a
# fractional hold is a rounding nobody can see.
HOLD_FRAMES = int(round(HOLD_SECONDS * FPS))

# The runtime the brief asks for, in seconds. Not a target to hit exactly - a
# whole-frame edit lands on a multiple of 1/60 and the brief says so.
RUNTIME_BOUNDS = (18.5, 20.5)

# How far a join is allowed to move the marbles, in marble widths on the
# delivered 1080x1920 frame. The shipped V22.1 start join measures 0.47 and the
# worst single marble in it moves 1.12, so this is that join with room rather
# than a number from taste. A join over the bar is reported as a problem; it is
# not refused, because the trap's own best placement sits just above it and the
# choice is the reviewer's.
MARBLE_WIDTH_BAR = 1.20

# The rotor: four blades, 13.0 rad/s, from `start.rotor_rate`. One frame is
# 12.4139 degrees and the blades are identical every 90.
BLADE_SYMMETRY_DEG = 90.0

# How far the blades may be from where the next frame would have put them, in
# degrees, before a join counts as a phase break. One revolution rounds to 29
# frames with 0.03 degrees of error and the shipped join is 12.44 out, so this
# separates them with a wide margin on both sides.
PHASE_TOLERANCE_DEG = 1.0

# How closely the machine's own state has to match across a join. `rate` is
# radians a second and the drum's two states are 13.0 and 0.0, so anything under
# a radian is "the same state"; `rise` is layout units and the blade lift is
# 1.19 of them end to end.
RATE_TOLERANCE = 1.0
RISE_TOLERANCE = 0.02


# --- the master -------------------------------------------------------------


@dataclass(frozen=True)
class Master:
    """The rendered V22.1 race master, as a frame-indexed object.

    `replay_of[f]` is the replay instant master frame `f` is showing and
    `poses[f]` is the camera row the renderer drew it with:
    `(replay, px, py, pz, ax, ay, az, fov)`. `base` is the clock the master runs
    on before anything is cut out of it, with **no prefix** - V24 has no course
    preview, so the film starts on the held race frame.
    """

    frames: int
    segments: tuple[tuple[float, float, float, float], ...]
    names: tuple[str, ...]
    replay_of: tuple[float, ...]
    poses: tuple[tuple[float, ...], ...]
    base: Clock

    def window_of(self, frame: int) -> int:
        output = frame / float(FPS)
        for index, (out_from, out_to, _rf, _rt) in enumerate(self.segments):
            if out_from - 1e-9 <= output <= out_to + 1e-9:
                return index
        raise ValueError(f"master frame {frame} is not on the edit map")

    def frame_at(self, replay: float) -> int | None:
        """The master frame showing this replay instant, or None if it is cut.

        Exact rather than nearest: the replay is written at 60 Hz and every
        boundary in this module is a frame, so a request that lands between two
        frames is a bug in the caller and is reported as a miss.
        """
        for frame, when in enumerate(self.replay_of):
            if abs(when - replay) <= 0.5 / FPS:
                return frame
        return None


def load_master(track: dict[str, Any], hold_frames: int = HOLD_FRAMES) -> Master:
    """The master, rebuilt from the camera track the way the renderer built it.

    Each cut's frame list repeats the boundary row, so the concatenation drops
    the **first** row of every cut after the first - see the module docstring for
    how that was settled. The result is checked against the edit map's own
    arithmetic frame by frame; a disagreement is raised rather than absorbed,
    because every measurement in this module is indexed by master frame.
    """
    segments = tuple(
        (
            float(row["out"][0]),
            float(row["out"][1]),
            float(row["replay"][0]),
            float(row["replay"][1]),
        )
        for row in track["edit"]
    )
    names = tuple(str(row["cut"]) for row in track["edit"])
    poses: list[tuple[float, ...]] = []
    for index, cut in enumerate(track["cuts"]):
        rows = cut["frames"] if index == 0 else cut["frames"][1:]
        poses.extend(tuple(float(value) for value in row) for row in rows)
    frames = len(poses)

    replay_of: list[float] = []
    for frame in range(frames):
        output = frame / float(FPS)
        found = None
        for out_from, out_to, replay_from, _replay_to in segments:
            if out_from - 1e-9 <= output <= out_to + 1e-9:
                found = round(replay_from + (output - out_from), 6)
                break
        if found is None:
            raise ValueError(f"master frame {frame} is not on the edit map")
        replay_of.append(found)

    worst = max(abs(poses[frame][0] - replay_of[frame]) for frame in range(frames))
    if worst > 1e-6:
        raise ValueError(
            "the camera track's frame rows and its edit map disagree by "
            f"{worst:.6f} s - the concatenation rule in `load_master` no longer "
            "matches the renderer"
        )

    base = Clock(segments, hold=hold_frames / float(FPS), fps=FPS,
                 master_frames=frames, prefix=0.0)
    return Master(
        frames=frames,
        segments=segments,
        names=names,
        replay_of=tuple(replay_of),
        poses=tuple(poses),
        base=base,
    )


# --- the plan ---------------------------------------------------------------


@dataclass(frozen=True)
class Cut:
    """One inclusive range of master frames the film does not show."""

    first: int
    last: int
    why: str

    @property
    def frames(self) -> int:
        return self.last - self.first + 1

    @property
    def seconds(self) -> float:
        return self.frames / float(FPS)


@dataclass(frozen=True)
class Plan:
    """One V24 timeline: the hold, the omissions and where the master stops.

    `tail` is the last master frame the film keeps, which is a *truncation* and
    not an omission - there is no far side to join to, so it costs no continuity
    at all. `cuts` are interior and every one of them is a visible join.

    Frame 0 is never in `cuts`, because the hold clones it.
    """

    key: str
    title: str
    hold_frames: int
    cuts: tuple[Cut, ...]
    tail: int
    note: str

    @property
    def dropped(self) -> int:
        return sum(cut.frames for cut in self.cuts)

    def omitted_frames(self) -> set[int]:
        gone: set[int] = set()
        for cut in self.cuts:
            gone.update(range(cut.first, cut.last + 1))
        return gone


def runs(master: Master, plan: Plan) -> tuple[tuple[int, int], ...]:
    """The master frames this plan keeps, as contiguous inclusive ranges.

    This is what an encoder needs, and it is also the thing the clock is built
    out of: **one segment per run**, not one per window. See `build`.
    """
    kept = kept_frames(master, plan)
    out: list[tuple[int, int]] = []
    run_from = previous = kept[0]
    for frame in kept[1:]:
        if frame != previous + 1:
            out.append((run_from, previous))
            run_from = frame
        previous = frame
    out.append((run_from, previous))
    return tuple(out)


def build(master: Master, plan: Plan) -> tuple[Clock, tuple[tuple[int, int], ...]]:
    """The clock this plan's film runs on, and the master frames to keep.

    ## Why this does not call `presentation.omit_frames`, which it would like to

    `omit_frames` is production's, it is what the delivered films are cut with,
    and it emits **one segment per window of the original edit map**. That is
    exactly right for every cut production has ever made - V21.1's 49..133 trims
    the tail of one window and the head of the next, so each window's surviving
    frames stay contiguous and one segment carries them. It is wrong for a cut
    in the *middle* of a window, and silently:

        a 100-frame window, replay 0.000-1.650, omit master frames 30..59
        omit_frames returns one segment  (0.0, 1.15, 0.0, 1.65)

    1.15 s of output carrying 1.65 s of replay is slope **1.43**, not 1. Every
    frame after the cut is mis-dated by up to 0.500 s, and `at(0.700)` returns
    an output second for a replay instant that is not in the film at all.

    V24's plans are mostly interior cuts - the stopped rotor, the pre-release
    stillness and the spinner trap are all in the middle of their windows - so
    this builds the segments itself: **one per contiguous run of kept frames**,
    each of them slope 1 by construction. `sloped/presentation.py` is production
    and this pass does not touch it; the limitation is reported instead, and
    `tests/test_sloped_v24_pacing.py` pins both halves - that `omit_frames`
    still behaves the way the delivered films rely on, and that this builder
    agrees with it frame for frame on the head-and-tail cuts where it is right.

    ## The edges

    A run that begins on its window's own first frame keeps that window's
    nominal `out_from` and `replay_from`; one that ends on its window's own last
    frame keeps the nominal `out_to` and `replay_to`. Trimmed edges become the
    surviving frame's own figures. That is production's convention, and keeping
    it is what makes the two builders agree where they overlap.
    """
    if plan.tail >= master.frames:
        raise ValueError(f"the master has {master.frames} frames; tail {plan.tail}")
    if plan.tail < 1:
        raise ValueError("the tail has to keep at least frame 0 and one more")
    for cut in plan.cuts:
        if not 0 < cut.first <= cut.last < plan.tail:
            raise ValueError(
                f"the cut {(cut.first, cut.last)} is not inside master frames "
                f"1..{plan.tail - 1}"
            )
    ordered = sorted((cut.first, cut.last) for cut in plan.cuts)
    for (first, last), (next_first, _next_last) in zip(ordered, ordered[1:]):
        if next_first <= last:
            raise ValueError(f"the cut {(next_first, _next_last)} overlaps {(first, last)}")

    keep = runs(master, plan)
    # Where each window starts and ends in the untrimmed master, so an edge can
    # be recognised as its window's own rather than one this plan made.
    heads: dict[int, int] = {}
    tails: dict[int, int] = {}
    for frame in range(master.frames):
        index = master.window_of(frame)
        heads.setdefault(index, frame)
        tails[index] = frame

    # A kept run may span several windows - `(274, 686)` covers the descent and
    # most of the obstacle - and a segment may not, because its replay edges are
    # its window's. So each run is split at the window boundaries it crosses,
    # which is what the original edit map does at those same frames.
    pieces: list[tuple[int, int, int]] = []
    for first, last in keep:
        start = first
        while start <= last:
            index = master.window_of(start)
            stop = start
            while stop < last and master.window_of(stop + 1) == index:
                stop += 1
            pieces.append((start, stop, index))
            start = stop + 1

    segments: list[tuple[float, float, float, float]] = []
    shown = 0
    for first, last, index in pieces:
        out_from, out_to, replay_from, replay_to = master.segments[index]
        # Frames dropped before this piece. Constant across it, because a piece
        # is contiguous by construction.
        gone = first - shown
        position = shown + (last - first)
        # **An untouched edge keeps its window's own figure, moved by the frames
        # that went before it; a trimmed edge becomes the frame that survived.**
        # This is `presentation.omit_frames`'s convention and it is not cosmetic:
        # a window's nominal output span is 1/60 longer than its frames' span,
        # because `out_to` is also the next window's `out_from`. Writing one edge
        # nominally and the other from a frame index mixes the two and puts a
        # frame of slope error into every shot.
        if first == heads[index]:
            new_from, near = out_from - gone / float(FPS), replay_from
        else:
            new_from, near = (first - gone) / float(FPS), master.replay_of[first]
        if last == tails[index]:
            new_to, far = out_to - gone / float(FPS), replay_to
        else:
            new_to, far = position / float(FPS), master.replay_of[last]
        # **The replay edges are rounded and the output edges are not**, for the
        # reason `omit_frames` gives: `at()` is asked about instants that come
        # out of the replay file and `replay_at()` about exact `frame / fps`
        # divisions, so each edge is written in the units it is compared against.
        segments.append((new_from, new_to, round(near, 6), round(far, 6)))
        shown += last - first + 1

    clock = Clock(tuple(segments), hold=plan.hold_frames / float(FPS), fps=FPS,
                  master_frames=shown, prefix=0.0)
    return clock, keep


def kept_frames(master: Master, plan: Plan) -> list[int]:
    gone = plan.omitted_frames()
    return [frame for frame in range(plan.tail + 1) if frame not in gone]


def production_clock(master: Master, plan: Plan) -> tuple[Clock, tuple[tuple[int, int], ...]]:
    """What `presentation.omit_frames` makes of a plan, for comparison.

    Only defined where it is *right*: every window's surviving frames have to be
    contiguous, which is the case for head-and-tail cuts and not for interior
    ones. Raises rather than returning a clock with the wrong slope in it, so
    the comparison in `tests/test_sloped_v24_pacing.py` cannot quietly pass on
    a plan production could not carry.
    """
    kept = kept_frames(master, plan)
    by_window: dict[int, list[int]] = {}
    for frame in kept:
        by_window.setdefault(master.window_of(frame), []).append(frame)
    for index, frames in by_window.items():
        if frames[-1] - frames[0] + 1 != len(frames):
            raise ValueError(
                f"window {index} ({master.names[index]}) keeps a discontiguous "
                "run; `omit_frames` emits one segment per window and cannot "
                "represent that - see `build`"
            )
    if plan.tail != master.frames - 1:
        raise ValueError("`omit_frames` cannot trim the master's last frame")
    return omit_frames(master.base, tuple((cut.first, cut.last) for cut in plan.cuts))


# --- the machine ------------------------------------------------------------


def machine_state(replay: dict[str, Any], when: float) -> dict[str, float]:
    """What the start mechanism is doing at a replay instant.

    `rate` is the rotor's turn in radians a second, `rise` the blades' mean
    height above their resting height, `panel` the trapdoor's mean height below
    its closed height and `paddle` the bay gates'. All four come out of the
    recorded transforms, none of them is modelled, and together they are the
    machine's whole visible state in the start shot.

    The rate is read across the frame *into* `when`, which is the step a viewer
    sees arriving at that frame.
    """
    frames = replay["frames"]
    index = max(1, min(len(frames) - 1, int(round(when * FPS))))
    return _state_at(frames, index)


def _state_at(frames: Sequence[dict[str, Any]], index: int) -> dict[str, float]:
    current = frames[index].get("actuators") or {}
    previous = frames[index - 1].get("actuators") or {}
    span = max(float(frames[index]["t"]) - float(frames[index - 1]["t"]), 1e-9)
    out: dict[str, float] = {}
    for prefix, label in (("start.rotor", "rotor"), ("start.panel", "panel"),
                          ("start.paddle", "paddle")):
        mine = {name: value for name, value in current.items()
                if name.startswith(prefix)}
        was = {name: value for name, value in previous.items()
               if name.startswith(prefix)}
        if not mine:
            continue
        total = 0.0
        counted = 0
        for name, value in mine.items():
            before = was.get(name)
            if before is None:
                continue
            dot = abs(sum(a * b for a, b in zip(before["q"], value["q"])))
            total += 2.0 * math.acos(min(1.0, dot))
            counted += 1
        out[f"{label}_rate"] = (total / counted / span) if counted else 0.0
        out[f"{label}_height"] = sum(
            value["p"][1] for value in mine.values()
        ) / len(mine)
    return out


def rotor_phase(replay: dict[str, Any], first: float, second: float) -> float:
    """Degrees the blades turn between two replay instants.

    Accumulated frame by frame from the recorded quaternions rather than from
    the rate, so a spin-up or a spin-down inside the span is counted correctly.
    At 13.0 rad/s a frame is 12.41 degrees, so no step is near the half turn
    where the unsigned angle would wrap and there is nothing to unwind.
    """
    frames = replay["frames"]
    low = max(0, int(round(min(first, second) * FPS)))
    high = min(len(frames) - 1, int(round(max(first, second) * FPS)))
    total = 0.0
    previous: list[float] | None = None
    for index in range(low, high + 1):
        blade = (frames[index].get("actuators") or {}).get("start.rotor0")
        if blade is None:
            return 0.0
        current = [float(value) for value in blade["q"]]
        if previous is not None:
            dot = abs(sum(a * b for a, b in zip(previous, current)))
            total += math.degrees(2.0 * math.acos(min(1.0, dot)))
        previous = current
    return total if second >= first else -total


def phase_error(replay: dict[str, Any], before: float, after: float) -> float:
    """How far off the blade lock a join lands, in degrees, folded to +/-45.

    A join is entitled to one frame of rotation - the step any two consecutive
    frames have. What it may not have is the *rest*: the blades are identical
    every 90 degrees, so everything above that has to be a whole number of
    quarter turns. Returns 0.0 when the rotor is not turning on either side,
    because a stopped rotor has no phase to break.
    """
    turned = rotor_phase(replay, before, after)
    step = rotor_phase(replay, before, round(before + 1.0 / FPS, 6))
    residual = (turned - step) % BLADE_SYMMETRY_DEG
    if residual > BLADE_SYMMETRY_DEG * 0.5:
        residual -= BLADE_SYMMETRY_DEG
    return residual


def machine_match(replay: dict[str, Any], before: float, after: float) -> dict[str, Any]:
    """Whether the machine is in the same state either side of a join.

    This is the check that refuses V22's start cut. The rotor spins at 13.0
    rad/s until 4.617, decelerates to a stop by 4.917, and the blades lift out
    of the drum between 5.217 and 5.650; a join whose two sides straddle either
    of those transitions shows the machine in one state and then, one frame
    later, in another. That is what "the shuffle still looks cut" was.

    An omission is allowed only where the state on both sides agrees - and then,
    if the rotor is turning, where the blades also land on the lock.
    """
    near = machine_state(replay, before)
    far = machine_state(replay, after)
    rate = abs(near.get("rotor_rate", 0.0) - far.get("rotor_rate", 0.0))
    rise = abs(near.get("rotor_height", 0.0) - far.get("rotor_height", 0.0))
    panel = abs(near.get("panel_height", 0.0) - far.get("panel_height", 0.0))
    paddle = abs(near.get("paddle_height", 0.0) - far.get("paddle_height", 0.0))
    spinning = max(near.get("rotor_rate", 0.0), far.get("rotor_rate", 0.0)) > RATE_TOLERANCE
    error = phase_error(replay, before, after) if spinning else 0.0
    problems: list[str] = []
    if rate > RATE_TOLERANCE:
        problems.append(
            f"the rotor turns at {near.get('rotor_rate', 0.0):.2f} rad/s before "
            f"the join and {far.get('rotor_rate', 0.0):.2f} after it"
        )
    if rise > RISE_TOLERANCE:
        problems.append(
            f"the blades stand {rise:.3f} layout units apart across the join"
        )
    if panel > RISE_TOLERANCE:
        problems.append(f"the trapdoor moves {panel:.3f} units across the join")
    if paddle > RISE_TOLERANCE:
        problems.append(f"the bay gates move {paddle:.3f} units across the join")
    if spinning and abs(error) > PHASE_TOLERANCE_DEG:
        problems.append(
            f"the blades land {error:+.2f} degrees off the lock "
            f"({BLADE_SYMMETRY_DEG:.0f} degree symmetry, "
            f"{rotor_phase(replay, before, round(before + 1.0 / FPS, 6)):.2f} "
            "degrees a frame)"
        )
    return {
        "rotor_rate": (near.get("rotor_rate", 0.0), far.get("rotor_rate", 0.0)),
        "rotor_rise": rise,
        "panel": panel,
        "paddle": paddle,
        "phase_error_deg": error,
        "problems": tuple(problems),
    }


# --- what a join costs on screen --------------------------------------------


def screen_field(
    master: Master, replay: dict[str, Any], frame: int
) -> dict[int, tuple[float, float, float]]:
    """Every marble on master frame `f` as `(x px, y px, radius px)`.

    The camera is the row the renderer drew that frame with and the projection
    is `presentation.project`, which is Godot's own arithmetic transcribed and
    checked against a rendered frame. Marbles behind the lens are left out.

    This is the measurement the whole pass turns on: "does the cut teleport a
    marble" is a question about the delivered frame, and a world-unit answer to
    it is the wrong units. A 30-frame omission in the descent moves the field
    7.8 wu and 107 px; the same omission in the trap moves it 1.6 wu and 84 px.
    The wu figures are a factor of five apart and the pixels are not, because the
    chase camera is travelling in one and nearly still in the other.
    """
    units = replay.get("units", {})
    scale = float(units.get("render_scale", 0.57))
    radius = float(units.get("layout_marble_radius", 0.285))
    row = master.poses[frame]
    camera, aim, fov = row[1:4], row[4:7], row[7]
    half_up = math.tan(math.radians(fov) * 0.5)
    height = 1920
    out: dict[int, tuple[float, float, float]] = {}
    for marble, point in field_at(replay, master.replay_of[frame]).items():
        placed = project(camera, aim, fov, tuple(value * scale for value in point))
        if placed is None:
            continue
        x, y, depth = placed
        out[marble] = (x, y, (radius / depth) / half_up * (height * 0.5))
    return out


@dataclass(frozen=True)
class Join:
    """One place the film steps over time, with everything it costs."""

    output: float
    before_frame: int
    after_frame: int
    replay: tuple[float, float]
    omitted_frames: int
    world_mean: float
    world_max: float
    px_mean: float
    px_max: float
    widths_mean: float
    widths_max: float
    camera_step: float
    aim_step: float
    fov_step: float
    churn_before: float
    machine: dict[str, Any]
    window: tuple[str, str]
    # True when the join sits on a lens change the master already makes. The
    # bar does not apply to one of those - the film cuts there whatever this
    # pass does - so it is measured against the unmodified boundary instead,
    # which is what `baseline_widths` is.
    lens_cut: bool = False
    baseline_widths: float = 0.0

    @property
    def seconds(self) -> float:
        return self.replay[1] - self.replay[0]

    @property
    def problems(self) -> tuple[str, ...]:
        out = list(self.machine["problems"])
        if self.lens_cut:
            # Adding time to an existing cut is allowed to cost a little; it is
            # not allowed to make the cut visibly worse than it already is.
            if self.widths_mean > self.baseline_widths + MARBLE_WIDTH_BAR:
                out.append(
                    f"the lens change moves the field {self.widths_mean:.2f} "
                    f"marble widths with these frames omitted, against "
                    f"{self.baseline_widths:.2f} with none"
                )
        elif self.widths_mean > MARBLE_WIDTH_BAR:
            out.append(
                f"the field moves {self.widths_mean:.2f} marble widths across "
                f"the join, over the {MARBLE_WIDTH_BAR:.2f} bar"
            )
        return tuple(out)


def _spread(master: Master, replay: dict[str, Any],
            before: int, after: int) -> tuple[list[float], list[float]]:
    near = screen_field(master, replay, before)
    far = screen_field(master, replay, after)
    both = [key for key in near if key in far]
    px = [math.dist(near[key][:2], far[key][:2]) for key in both]
    widths = [
        gap / (2.0 * 0.5 * (near[key][2] + far[key][2]))
        for gap, key in zip(px, both)
    ]
    return px, widths


def joins(master: Master, replay: dict[str, Any], plan: Plan) -> list[Join]:
    """Every omission in a plan, measured. The tail trim is not one of them."""
    kept = kept_frames(master, plan)
    out: list[Join] = []
    for position, (before, after) in enumerate(zip(kept, kept[1:])):
        # **A join is where the replay skips, not where the frame numbers do.**
        # The master's own b116 gap sits between two consecutive master frames -
        # 111 and 112 - and it is a join in the finished film whether or not
        # this plan dropped anything around it.
        if master.replay_of[after] - master.replay_of[before] <= 1.5 / FPS:
            continue
        px, widths = _spread(master, replay, before, after)
        lens_cut = master.window_of(before) != master.window_of(after)
        baseline = 0.0
        if lens_cut:
            # The same boundary with nothing omitted: the last frame of the
            # earlier window against the first frame of the later one.
            edge = max(
                frame for frame in range(master.frames)
                if master.window_of(frame) == master.window_of(before)
            )
            _bpx, bwidths = _spread(master, replay, edge, edge + 1)
            baseline = sum(bwidths) / len(bwidths) if bwidths else 0.0
        world_near = field_at(replay, master.replay_of[before])
        world_far = field_at(replay, master.replay_of[after])
        world = [
            math.dist(world_near[key], world_far[key])
            for key in world_near
            if key in world_far
        ]
        row_near, row_far = master.poses[before], master.poses[after]
        # The join lands at the first output second the far frame is shown on.
        index = kept.index(after)
        out.append(
            Join(
                output=plan.hold_frames / float(FPS) + index / float(FPS),
                before_frame=before,
                after_frame=after,
                replay=(master.replay_of[before], master.replay_of[after]),
                omitted_frames=after - before - 1,
                world_mean=sum(world) / len(world) if world else 0.0,
                world_max=max(world) if world else 0.0,
                px_mean=sum(px) / len(px) if px else float("nan"),
                px_max=max(px) if px else float("nan"),
                widths_mean=sum(widths) / len(widths) if widths else float("nan"),
                widths_max=max(widths) if widths else float("nan"),
                camera_step=math.dist(row_near[1:4], row_far[1:4]),
                aim_step=math.dist(row_near[4:7], row_far[4:7]),
                fov_step=abs(row_near[7] - row_far[7]),
                churn_before=churn(
                    replay,
                    max(0.0, master.replay_of[before] - 0.1),
                    master.replay_of[before],
                ),
                machine=machine_match(
                    replay, master.replay_of[before], master.replay_of[after]
                ),
                window=(master.names[master.window_of(before)],
                        master.names[master.window_of(after)]),
                lens_cut=lens_cut,
                baseline_widths=baseline,
            )
        )
    return out


# --- the inventory ----------------------------------------------------------
#
# Every reduction this pass found, as master-frame ranges, with the number that
# makes each of them legal. They are constants rather than a search because each
# one is pinned to a machine instant that does not move: the rotor's constant
# rate ends at replay 4.617, it stops at 4.917, the blades start lifting at
# 5.217 and reach the top at 5.650, and the trapdoor's panels first move at
# 6.117. `tests/test_sloped_v24_pacing.py` re-reads all five off the replay.

# The constant-rate spin, extending V22.1's own omission forwards. 28 frames
# rather than 29 because the shipped join is a frame long: 118 + 28 = 146 steps,
# 145 of which is five exact revolutions. Resumes at replay 4.483, which leaves
# eight frames of constant spin before the wind-down starts.
SPIN = Cut(112, 139, "28 frames of constant-rate rotor spin, five exact revolutions")

# The rotor has stopped and the blades have not started to lift. Nothing in the
# machine moves and the field crawls at churn 0.45: the deadest 0.3 s in the
# film, and the cheapest join in it at 0.11 marble widths.
#
# It ends at 182 rather than 183, because 183 is replay 5.200 and the blades
# leave the floor at 5.2167 - master frame 184. Stopping a frame short is what
# keeps the far edge on the plateau rather than 0.0048 layout units into the
# lift, which is invisible and is still a transition the join would straddle.
STOPPED = Cut(167, 182, "the stopped rotor, before the blades lift - nothing moves")

# Blades up, floor shut, field settled. V22.1 holds this for 0.467 s as the
# anticipation before the release; 12 frames of it go and 0.250 s stays, which
# is V22's own figure and enough to read the machine as stopped before the floor
# opens under it. The deep setting leaves 0.117 s, which is close enough to the
# release that the cut and the floor read as one event - available, and the
# reason `check` guards 0.25 s in front of a payoff.
ANTICIPATION = Cut(212, 222, "0.183 s of the pre-release stillness, 0.250 s kept")
ANTICIPATION_DEEP = Cut(212, 230, "0.317 s of it, 0.117 s kept")

# The tail of the start shot, taken against the master's one hard lens change.
# The trapdoor's panels finish opening at replay 6.317, so the release is whole
# either way; what goes is part of the fall, which the chase lens then opens on.
# Free, in the sense that matters: the boundary already moves the field 2.51
# marble widths with nothing omitted and 2.38 with 21 frames omitted.
FALL = Cut(257, 273, "0.283 s of the fall, handed to the chase lens early")
FALL_DEEP = Cut(253, 273, "0.350 s of it")

# **Falsified.** The drum shot's tail is phase-exact only at 29-frame steps, and
# every one of them lands before the rotor takes hold at replay 1.6167 (master
# frame 85). 82 misses by three frames. Kept here, unused, because "trim the
# shuffle" is the first thing a later pass will reach for.
DRUM_FALSIFIED = Cut(83, 111, "REJECTED: resumes a stationary rotor into a "
                              "spinning one - the phase lock and the spin-up "
                              "are three frames apart")

# The field held against the spinners' turning blades - churn 3.18 to 4.75, the
# lowest sustained stretch in the race body. Both placements resume at replay
# 14.100, which leaves 0.896 s of run-up to the leader's escape at 14.996.
TRAP = Cut(687, 716, "0.500 s of the spinner trap, the field held and turning")
TRAP_SHORT = Cut(689, 708, "0.333 s of the spinner trap")


def tail_after(master: Master, replay_at: float) -> int:
    """The last master frame at or before a replay instant."""
    best = 0
    for frame, when in enumerate(master.replay_of):
        if when <= replay_at + 1e-9:
            best = frame
    return best


# The finish's dial, in replay seconds, with the crossing each one lands after.
# Seed 5432 finishes 5, 2, 7, 4, 1, 6, 3, 0 at 20.850, 21.133, 21.717, 22.633,
# 22.650, 23.500, 24.317 and 24.417.
#
#     22.900   five crossings, 0.250 s after the 4th and 5th arrive together
#     23.000   five crossings, 0.350 s after them
#     23.750   six crossings, 0.250 s after the 6th
#     24.467   the shipped tail, all eight
#
# A trim is not a join and costs no continuity; what it costs is the crossings
# after it, which is an editorial call and is why it is a dial.
TAIL_FIVE = 22.900
TAIL_FIVE_LONG = 23.000
TAIL_SIX = 23.750
TAIL_ALL = 24.466667


# --- the candidates ---------------------------------------------------------


def _plan(key, title, hold, cuts, tail_replay, note, master: Master) -> Plan:
    return Plan(
        key=key,
        title=title,
        hold_frames=hold,
        cuts=tuple(cuts),
        tail=tail_after(master, tail_replay),
        note=note,
    )


def candidates(master: Master) -> dict[str, Plan]:
    """The three timelines this pass offers, shortest start first.

    They are the same film. What separates them is one dial each at the two ends
    - how much of the drum the start keeps, and which crossing the finish stops
    after - because those are the only two places the master has seconds to give
    that do not cost a join over the bar.
    """
    return {
        "a": _plan(
            "a", "A - the compact start",
            36,
            (SPIN, STOPPED, ANTICIPATION, FALL_DEEP, TRAP),
            TAIL_FIVE,
            "every frame of the start's slack, a 0.600 s hold, and the deepest "
            "trap cut - the floor this master has",
            master,
        ),
        "b": _plan(
            "b", "B - the balanced start",
            HOLD_FRAMES,
            (SPIN, STOPPED, ANTICIPATION, FALL, TRAP),
            TAIL_FIVE_LONG,
            "the full 0.700 s hold, 0.250 s of anticipation kept in front of "
            "the release, and 0.100 s of the fall before the chase takes over",
            master,
        ),
        "c": _plan(
            "c", "C - the richer start",
            HOLD_FRAMES,
            (SPIN, STOPPED, TRAP),
            TAIL_FIVE,
            "the machine's ceremony left whole - the full 0.467 s of "
            "anticipation and the whole fall - paid for at the finish",
            master,
        ),
    }


def rejected(master: Master) -> dict[str, Plan]:
    """The brief's own start target, built, measured and turned down.

    "Explore compact start timelines... A. aggressive ~2.2-2.5 s start." The
    three candidates above cannot reach it and say so. **D can**, and it is here
    so that the floor is a demonstrated cost rather than an assertion: one
    omission from master 112 to 236 takes the whole machine ceremony out and
    puts the field on the downhill at **2.733 s**, inside the brief's second
    band.

    What it costs is the thing V22.1 was written to fix. The marbles barely
    move across the join - they are settled on both sides - but the rotor is
    turning at 13.0 rad/s on one frame and stopped with its blades withdrawn on
    the next. That is V22's start cut, rebuilt, and the note that came back
    about V22 was "the shuffle still looks cut".

    `check` fails it. It is rendered anyway, labelled REJECTED, because a
    reviewer weighing 2.7 s against 4.0 s should be able to watch the
    difference rather than read about it.
    """
    return {
        "d_rejected": _plan(
            "d_rejected", "D - REJECTED: the brief's start target, and its cost",
            36,
            (Cut(112, 236,
                 "REJECTED: the whole machine ceremony in one omission - the "
                 "rotor is turning on one frame and stopped on the next"),
             FALL_DEEP, TRAP),
            TAIL_FIVE_LONG,
            "the field on the downhill at 2.733 s, which is the brief's own "
            "band - and a rotor that stops in a single frame to get there",
            master,
        ),
    }


# What CANDIDATES would be if a master were already loaded. Kept as a function
# rather than a dict because every plan's `tail` is a frame of a specific master
# and a constant would be a frame number typed from memory.
CANDIDATES = candidates
REJECTED = rejected


# --- reading a candidate ----------------------------------------------------


# Approach, interaction and exit for each thing the machine does, in replay
# seconds. Read off the events, the churn and the recorded actuator transforms
# rather than typed from memory - `tests/test_sloped_v24_pacing.py` re-derives
# the machine instants and the crossings from the replay and fails if these move.
#
# The brief's rule is that a segment may not lose all three: a viewer needs to
# see the field arrive, see what happens to it, and see the result. `segment_times`
# reports the screen seconds each of the three gets under a given plan.
#
# Two of the exits are deliberately not the last thing that happens in their
# segment. The release's is the trapdoor finishing its swing rather than the
# field clearing the chamber, because the fall belongs to the chase lens; and
# the finish's is the **third** crossing rather than the eighth, because that is
# where the result is legible - a winner, a runner-up and a gap. What the film
# does about crossings four to eight is a separate number, `crossings_shown`,
# and trimming them is a choice rather than a broken segment.
SEGMENTS: tuple[tuple[str, float, float, float, str], ...] = (
    ("start", 0.200, 0.316667, 2.050,
     "eight in eight bays, the gates at 0.317, fifteen contacts to 2.013"),
    ("shuffle", 1.616667, 4.616667, 5.650,
     "the rotor takes hold at 1.617, runs at 13.0 rad/s, winds down over "
     "4.617-4.917 and lifts its blades clear over 5.217-5.650"),
    ("release", 5.650, 6.116667, 6.316667,
     "stillness, then the trapdoor's panels swing over 6.117-6.317"),
    ("descent", 6.716667, 7.700, 9.666667,
     "the launch chute at 6.9-7.4, then leg1 with the field strung out past "
     "48 wu/s"),
    ("obstacle", 9.683333, 11.400, 15.100,
     "the approach at 44 wu/s, 39 contacts over 11.4-12.65, then the trap"),
    ("escape", 14.400, 14.995833, 16.300,
     "the field accelerating out of the blades, the leader into leg3 at 14.996"),
    ("fork", 15.116667, 16.300, 19.350,
     "eight route decisions, marble 7 first at 16.300, blue against orange"),
    ("branches", 16.733333, 17.850, 18.416667,
     "the two routes run side by side"),
    ("merge", 18.416667, 18.900, 19.366667,
     "the routes converge on the final channel"),
    ("finish", 18.916667, 20.850, 21.716667,
     "the chase parks behind the line; the winner at 20.850 and the podium "
     "settled by 21.717"),
)


def coverage(master: Master, plan: Plan, replay: dict[str, Any]) -> dict[str, float]:
    """How much of the replay the film shows, and of how much it spans."""
    kept = kept_frames(master, plan)
    shown = len(kept) / float(FPS)
    first = master.replay_of[kept[0]]
    last = master.replay_of[kept[-1]]
    spanned = last - first
    total = float(replay["frames"][-1]["t"])
    return {
        "shown": shown,
        "replay_from": first,
        "replay_to": last,
        "spanned": spanned,
        "coverage": shown / spanned if spanned > 0 else 0.0,
        "of_whole_replay": shown / total if total > 0 else 0.0,
    }


def omissions(master: Master, plan: Plan) -> list[dict[str, Any]]:
    """Every replay interval the film leaves out, including the master's own.

    Three kinds, and they are different things:

    * `master` - replay the V22.1 master never rendered. There is exactly one,
      the `b116` gap, and it is inside every V24 candidate whether or not the
      candidate touches the start.
    * `cut` - frames this plan drops. These are the joins.
    * `tail` - replay after the film stops. Not a join.
    """
    kept = kept_frames(master, plan)
    gone = plan.omitted_frames()
    out: list[dict[str, Any]] = []
    for before, after in zip(kept, kept[1:]):
        if master.replay_of[after] - master.replay_of[before] <= 1.5 / FPS:
            continue
        dropped = sorted(frame for frame in range(before + 1, after) if frame in gone)
        kind = "cut" if dropped else "master"
        if dropped and len(dropped) < after - before - 1:
            kind = "cut+master"
        out.append({
            "kind": kind,
            "replay_from": master.replay_of[before],
            "replay_to": master.replay_of[after],
            "seconds": master.replay_of[after] - master.replay_of[before],
            "frames": after - before - 1,
            "master_frames": (dropped[0], dropped[-1]) if dropped else None,
        })
    if plan.tail < master.frames - 1:
        out.append({
            "kind": "tail",
            "replay_from": master.replay_of[plan.tail],
            "replay_to": master.replay_of[master.frames - 1],
            "seconds": master.replay_of[master.frames - 1] - master.replay_of[plan.tail],
            "frames": master.frames - 1 - plan.tail,
            "master_frames": (plan.tail + 1, master.frames - 1),
        })
    return out


def crossings(replay: dict[str, Any], clock: Clock) -> list[dict[str, Any]]:
    """The eight finish-line events, with the output second each lands on."""
    out: list[dict[str, Any]] = []
    for event in replay["events"]:
        if event["kind"] != "finish_line":
            continue
        when = float(event["t"])
        out.append({
            "order": int(event["order"]),
            "marble": int(event["id"]),
            "route": str(event.get("route") or ""),
            "replay": when,
            "output": clock.at(when),
        })
    return sorted(out, key=lambda row: row["order"])


def segment_times(clock: Clock) -> list[dict[str, Any]]:
    """Per segment: whether the approach, the interaction and the exit survive.

    A segment reports `whole` when all three are on screen, and the seconds each
    of the three phases gets. `None` where the film does not show that instant.
    """
    out: list[dict[str, Any]] = []
    for name, approach, interaction, exit_at, detail in SEGMENTS:
        marks = {
            "approach": clock.at(approach),
            "interaction": clock.at(interaction),
            "exit": clock.at(exit_at),
        }
        row: dict[str, Any] = {"name": name, "detail": detail, **marks}
        row["replay"] = (approach, interaction, exit_at)
        row["whole"] = all(value is not None for value in marks.values())
        if marks["approach"] is not None and marks["interaction"] is not None:
            row["run_up"] = marks["interaction"] - marks["approach"]
        else:
            row["run_up"] = None
        if marks["interaction"] is not None and marks["exit"] is not None:
            row["pay_off"] = marks["exit"] - marks["interaction"]
        else:
            row["pay_off"] = None
        out.append(row)
    return out


def section_times(master: Master, plan: Plan, clock: Clock) -> list[dict[str, Any]]:
    """Screen seconds per lens, which is what a viewer experiences as a shot."""
    kept = kept_frames(master, plan)
    counts: dict[int, int] = {}
    for frame in kept:
        index = master.window_of(frame)
        counts[index] = counts.get(index, 0) + 1
    out: list[dict[str, Any]] = []
    running = plan.hold_frames
    for index in sorted(counts):
        frames = counts[index]
        out.append({
            "name": master.names[index],
            "frames": frames,
            "seconds": frames / float(FPS),
            "output_from": running / float(FPS),
            "output_to": (running + frames) / float(FPS),
        })
        running += frames
    # The hold is part of the first shot as far as a viewer is concerned - it is
    # the opening lens, standing still - so it is reported as its own row rather
    # than folded in, and the first shot's `output_from` is the hold's end.
    out.insert(0, {
        "name": "hold (PICK ONE)",
        "frames": plan.hold_frames,
        "seconds": plan.hold_frames / float(FPS),
        "output_from": 0.0,
        "output_to": plan.hold_frames / float(FPS),
    })
    return out


# The machine instants the start's timings are quoted against. All five are read
# off the recorded transforms by `tools/sloped_v24_pacing.py --stage machine` and
# re-derived by the tests; they are here so a report does not have to.
GATES_AT = 0.316667
ROTOR_AT = 1.616667
SPIN_DOWN_AT = 4.616667
LIFT_AT = 5.216667
RELEASE_AT = 6.116667
# The field is on the downhill when the descent lens takes over.
DOWNHILL_AT = 6.716667
# Marble 6 leaves the start module - the first frame of the race proper.
FIRST_RACE_ACTION = 6.8875


def start_timings(clock: Clock) -> dict[str, float | None]:
    """The start, under all three readings of the word.

    The brief asks for start durations around 2.2-2.5, 2.7-3.0 and 3.2 s and
    does not say which of these it means, and they differ by more than the range
    it is asking across. So all three are reported:

    * `to_release` - the film's first frame to the trapdoor's panels moving.
      "How long until the marbles are let go."
    * `to_downhill` - to the descent lens taking over, which is where the start
      section ends and the race body begins. This is the reading the brief's own
      0-3 s / 3-6 s sketch implies, and the one the candidates are named for.
    * `drum` - the hold plus the shuffle shot, before the machine's ceremony.
    """
    return {
        "gates": clock.at(GATES_AT),
        "to_release": clock.at(RELEASE_AT),
        "to_downhill": clock.at(DOWNHILL_AT),
        "drum": clock.at(2.050) if clock.at(2.050) is not None else None,
        "first_race_action": clock.at(FIRST_RACE_ACTION),
    }


def report(master: Master, replay: dict[str, Any], plan: Plan) -> dict[str, Any]:
    """Everything the brief asks to be told about one candidate."""
    clock, keep = build(master, plan)
    ordered = joins(master, replay, plan)
    finish = crossings(replay, clock)
    winner = next((row for row in finish if row["order"] == 1), None)
    shown = [row for row in finish if row["output"] is not None]
    return {
        "key": plan.key,
        "title": plan.title,
        "note": plan.note,
        "runtime": clock.duration,
        "frames": clock.frames,
        "hold": plan.hold_frames / float(FPS),
        "master_frames": clock.master_frames,
        "keep": keep,
        "clock": clock,
        "coverage": coverage(master, plan, replay),
        "omissions": omissions(master, plan),
        "join_count": len(ordered),
        "joins": ordered,
        "sections": section_times(master, plan, clock),
        "segments": segment_times(clock),
        "start": start_timings(clock),
        "crossings": finish,
        "crossings_shown": len(shown),
        "winner_output": winner["output"] if winner else None,
        "post_winner": (clock.duration - winner["output"]) if winner and winner["output"] else None,
        "problems": check(master, replay, plan, clock, ordered),
    }


def check(
    master: Master,
    replay: dict[str, Any],
    plan: Plan,
    clock: Clock,
    ordered: Sequence[Join] | None = None,
) -> list[str]:
    """Every way a candidate can be wrong, in one list. Empty means it is not.

    This is the bar the tests assert against and the tool prints. It is the
    brief's own list plus the two constraints the measurements added - the
    machine's state and the blades' phase.
    """
    problems: list[str] = []
    ordered = list(ordered if ordered is not None else joins(master, replay, plan))
    kept = kept_frames(master, plan)

    if kept[0] != 0:
        problems.append("frame 0 is not kept, and the hold clones it")
    if len(set(kept)) != len(kept):
        problems.append("a frame is kept twice")
    for before, after in zip(kept, kept[1:]):
        if after <= before:
            problems.append(f"master frames run backwards at {before} -> {after}")
        if master.replay_of[after] <= master.replay_of[before]:
            problems.append(
                f"the replay does not step forwards at master {before} -> {after}"
            )

    low, high = RUNTIME_BOUNDS
    if not low - 1e-9 <= clock.duration <= high + 1e-9:
        problems.append(
            f"the runtime is {clock.duration:.3f} s, outside {low}-{high}"
        )
    if clock.prefix != 0.0:
        problems.append("there is a course preview in front of the film")

    for join in ordered:
        for note in join.problems:
            problems.append(f"at output {join.output:.3f}: {note}")

    # The brief's keep list, as instants that have to be on screen.
    must = {
        "the gates opening": GATES_AT,
        "the trapdoor releasing": RELEASE_AT,
        "the obstacle payoff": 11.400,
        "the leader's escape": 14.995833,
        "the first route decision": 16.300,
        "the merge": 18.416667,
        "the winner crossing": 20.850,
    }
    for label, when in must.items():
        if clock.at(when) is None:
            problems.append(f"{label} (replay {when:.3f}) is not in the film")

    # No cut may land on a payoff. 0.25 s either side, which is the smallest
    # run-up any of these candidates leaves anywhere.
    guarded = {
        "the obstacle payoff": 11.400,
        "the leader's escape": 14.995833,
        "the trapdoor releasing": RELEASE_AT,
    }
    for join in ordered:
        for label, when in guarded.items():
            if 0.0 <= when - join.replay[1] < 0.25:
                problems.append(
                    f"the join at output {join.output:.3f} resumes "
                    f"{when - join.replay[1]:.3f} s before {label}"
                )

    order = [row["marble"] for row in crossings(replay, clock)]
    if order != [5, 2, 7, 4, 1, 6, 3, 0]:
        problems.append(f"the finish order is {order}, not seed 5432's")

    return problems
