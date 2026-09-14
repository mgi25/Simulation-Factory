"""V24: the first scroll decision, treated as the product.

The first Short went up as V22.1 and the retention came back:

    stayed to watch          19.6%
    swiped away              80.4%
    average view duration    ~24 s of ~27
    approximate viewed       ~89%

Nobody who stayed got bored. Four viewers in five left **before the premise
arrived**, and the premise arrived at output 4.2 s behind 3.5 s of aerial
preview over an empty hillside and a first race frame frozen for 0.7 s.

So V24 is a controlled experiment with one variable: *what is on screen at
second zero*. The race is V22.1's - seed 5432, the same replay, the same
physics, the same finish order 5, 2, 7, 4, 1, 6, 3, 0, the same course, the
same lenses through the body, the same environment and the same grade. There
is no V23 in it. What changes is the opening, the length and the end card, and
this module is where those three meet.

    OUTPUT  0.000 -  1.400   the hook: eight racers, large, under PICK A COLOR,
                             live, pulling back onto the shipped start lens
    OUTPUT  1.400 -  3.800   the start: the field pours, the drum mixes, the
                             floor drops
    OUTPUT  3.800 - 15.500   the race body, V22.1's to the microsecond bar one
                             omission inside the spinner trap
    OUTPUT 15.500 - 20.050   the finish, the winner, PURPLE WINS

## Three things this module is, and one it is not

**It is a re-render.** The pacing lab found that cutting the delivered master
leaves camera discontinuities, because V22.1's constant-rate legs were solved
against V22.1's windows. Every V24 window is therefore solved to its own
bounds: the start is re-split by `v221_shuffle.constant_rate_legs` across the
windows V24 actually has, so position *and* velocity carry across both joins
inside it. Nothing here frame-selects from `real_race_v221.mp4`.

**It is one edit map, every segment slope 1.** `presentation.omit_frames`
cannot represent a cut in the middle of a window - it emits one segment per
window and the surviving replay is compressed into it at slope 1.43 - so V24
does not use it and does not need it. An omission here is a **window
boundary**, which is what an omission is; `EDITIONS["v24"]["cuts"]` is empty
and the master is rendered to the film's own length.

**It is V22.1's body, solved once.** `build_race_track` takes the shipped
chase and finish from `v221.build_race_track` and replaces only the start
cuts. The chase is a function of replay time, so the frames V24 keeps are the
frames V22.1 rendered, pose for pose; the trap omission is a split of one
solved cut and the tail is a truncation of another.

It is **not** a physics change. Nothing in this module simulates, seeds,
re-solves or re-times the race. Every number below is a decision about which of
`race_5432.json`'s frames to render and from where.

## The omission the measurement moved

Candidate B of the pacing lab takes five omissions. Three of them - the stopped
rotor, the pre-release stillness and the fall - were chosen by **churn**: the
deadest stretches in the film, where the marbles travel least per second.

That criterion is exactly right for a uniformly coloured sphere and exactly
inverted for a marked one. With `--racers=meridian` the marbles' real rotation
is finally visible, and a rotation cut is hidden by *motion*: measured against
each shot's own per-frame spread of visible-face change,

    join                    omitted   visible change   its shot's p95   ratio
    SPIN     mixer          2.433 s       0.260            0.220         1.2
    STOPPED  rotor halted   0.283 s       0.220            0.046         4.8
    ANTICIP  pre-release    0.200 s       0.157            0.052         3.0
    FALL     on a lens cut  0.283 s       0.244            0.231         1.1
    TRAP     spinner trap   0.517 s       0.254            0.187         1.4

The two cheapest cuts in the film on churn are the two most exposed cuts in it
on marking, and by a factor of three to five. The mixer - where a marble turns
119 degrees across the join, which sounds like the worst of them - is the
safest, because in the mixer a marble turns that much anyway and the picture is
already churning.

`STOPPED` and `ANTICIPATION` are therefore **not in V24**, and the 0.483 s they
bought is given back. See `docs/sloped_race_v24.md` for the measured audit and
`tools/sloped_v24_audit.py` for the instrument.

## The rotor phase, taken from the rendered frames rather than the plan

The renderer draws each cut's rows and drops the **first** row of every cut
after the first, so a window written `from 4.000` first appears at 4.016667.
V22.1's b116 join is one frame off its own nominal phase lock for exactly that
reason: it asks for a gap of four exact revolutions and renders a gap of one
more frame, so the blades step 24.86 degrees where a frame step is 12.41.

V24's mixer omission resumes 28 rendered frames later, which makes the rendered
gap 146 frame steps - 145 of them five exact revolutions. Measured on the
replay's own actuator quaternions, the blades step **12.46 degrees** across it
against a frame step of 12.41: a phase error of 0.05 degrees, where the shipped
film has 12.44. V24's mixer join is more phase-exact than the one it extends.

`RESUME_AT` is therefore written as the window bound, 4.466667, and the frame
the film resumes on is 4.483333. The two are a frame apart and the difference
is the whole of that finding.
"""

from __future__ import annotations

from typing import Any, Sequence

from sloped import cameras, presentation, v221, v221_shuffle, v24_hook
from sloped.v22 import FPS
from sloped.v24_payoff import PAYOFF_SECONDS
from sloped.v24_timeline import SPIN, TRAP

__all__ = [
    "BEAT",
    "BODY_OMISSIONS",
    "EDIT",
    "FALL_AT",
    "FPS",
    "HOOK",
    "MARK_BASELINE",
    "MARK_IN",
    "MARK_OUT_FROM",
    "MARK_OUT_TO",
    "OMISSIONS",
    "RACERS",
    "RESUME_AT",
    "START_WINDOWS",
    "IN_FRAME_ACTUATORS",
    "PHASE_BAR_DEG",
    "TAIL_AT",
    "TRAP_FROM",
    "TRAP_TO",
    "WINNER_CROSSES",
    "build_opening_track",
    "build_race_track",
    "build_start_track",
    "film_clock",
    "master_frames",
    "opening_windows",
    "rendered_instants",
    "split_cut",
    "start_windows",
    "trim_cut",
]

# The edit plan's name, for the reports and the edition tables. Like `v221`'s
# it is not a key in `cameras.EDITS`: the windows are computed, not typed.
EDIT = "v24"


def _sec(frames: int) -> float:
    """A whole number of frames, in seconds, rounded once.

    **Every replay bound in this module is a whole frame, so every one of them
    is written as one.** Rounding `4.466667 + 1/60` gives 4.483334 and rounding
    `269/60` gives 4.483333, and the frame the film resumes on is the second of
    those. A sixth-decimal error is a whole frame's worth of rotor phase at the
    resolution the joins below are checked at, so the arithmetic is done in
    frames and converted once.
    """
    return round(frames / float(FPS), 6)

# The racer surface V24 renders with. `solid` - the uniformly coloured sphere
# every film up to and including V22.1 shipped - is still `sloped_race_scene`'s
# own default, so every earlier edition re-renders exactly what it shipped.
RACERS = "meridian"

# --- the hook ---------------------------------------------------------------
#
# `b_gate` of the hook lab, by name rather than by its numbers, so the framing
# the proofs were rendered from is the framing production runs: the front
# three-quarter across the gate row, opening at extent 7.2 with the course's own
# START sign in the picture and the massif in shade behind the mark.
#
# Measured on its own first frame: eight racers of eight in their own colours at
# both 1080x1920 and 270x480, median 146 px, 6.61% of the frame by area, 0.08
# off centre, 34.5% of the frame racer-and-machine and 8.2% distant hill and sky.
HOOK = v24_hook.HOOKS["b_gate"]

# Where PICK A COLOR sits and when it goes. The baseline is `text_plate`'s
# answer for this framing - the top of the frame, above the START sign - and not
# `overlays.PICK_ONE_BASELINE`, which was measured against V20's held opening
# frame with the racers at y 831-887.
MARK_BASELINE = 269

# **The mark is up at frame zero and it is over live footage.** There is no
# hold to fade it in over, so there is no fade in: frame 0 is the hook and the
# premise is on it. It leaves before the lens finishes its move, so the landing
# on the start shot is clean.
MARK_IN = 0.0
MARK_OUT_FROM = 1.05
MARK_OUT_TO = 1.30

# --- the start --------------------------------------------------------------
#
# The hook consumes replay 0.200 to its handoff and the shipped start shot
# carries on from there, with one omission in it: the mixer.
#
# `SPIN` is the pacing lab's, and it is an *extension* of V22.1's own b116
# omission rather than a new cut - the film already joins replay 2.050 to the
# drum, and this joins it 28 rendered frames further on. See the module
# docstring for why that is the phase-exact one.
#
# `RESUME_AT` is a **window bound**, and the frame the film resumes on is one
# frame later. Written as the bound rather than the frame so that
# `cameras.build_track` and `presentation.load` agree with the renderer.
CUT_AT = 2.05
_B116_RESUME = round(v221_shuffle.PLANS["b116"].resume_at * FPS)   # 240 frames
RESUME_AT = _sec(_B116_RESUME + SPIN.frames)
RESUME_FRAME = _sec(_B116_RESUME + SPIN.frames + 1)

# Where the start shot hands the field to the chase. `v221.START_HANDOFF` is
# 6.700 and the chase's first window still opens there; the start's last frame
# is 0.283 s earlier, which is the pacing lab's FALL - 17 frames taken against
# the master's one hard lens change, where the boundary already moves the field
# 2.51 marble widths with nothing omitted and 2.38 with them gone.
FALL_AT = _sec(385)


def start_windows(hook=HOOK, fps: int = FPS) -> tuple[tuple[float, float], ...]:
    """The live replay spans the start shot plays, after the hook has had its.

    Two, not V22.1's two-with-a-different-second and not Candidate B's four:
    the mixer omission stays and the two stillness omissions are gone. See the
    module docstring.
    """
    return (
        (hook.hands_over(fps), CUT_AT),
        (RESUME_AT, FALL_AT),
    )


START_WINDOWS = start_windows()


def build_start_track(
    replay: dict[str, Any],
    machine,
    hook=HOOK,
    fps: int = FPS,
    plan=None,
) -> dict[str, Any]:
    """The shipped start lens over V24's windows, re-split so the rate is one.

    ## Why the legs are recomputed rather than carried

    `v221_shuffle.plan_legs` hands each window the share of the whole start's
    orbit and dolly that its own length earns, so the rate never changes across
    a join. V24's start is 2.400 s of screen where V22.1's is 4.550, and it
    starts at the pose the hook lands on rather than at the shipped opening, so
    neither the shipped legs nor the shipped rate is the right answer:

        orbit   -36.0 -> +4.0 over 4.550 s   =  8.79 deg/s     V22.1
                -23.7 -> +4.0 over 2.400 s   = 11.54 deg/s     V24

    The travel is the same arc and it ends on the same pose - the framing at the
    hand-off to the chase is the framing V22.1 hands over on - and it is spent in
    the time V24 has. `constant_rate_legs` splits it across however many windows
    it is given, which is the whole reason it takes a sequence.

    The near end of the first leg is `start_plan_for`'s: the value the shipped
    ramp had at the second the hook hands over, so the hook arrives on the pose
    the start shot would have been at rather than on one invented for it.
    """
    plan = plan if plan is not None else v221.START
    resumed = v24_hook.start_plan_for(hook, plan, fps)
    windows = start_windows(hook, fps)
    spans = tuple(round(high - low, 6) for low, high in windows)

    # The travel still to spend: from where the shipped ramp stood at the
    # handoff to where the shipped ramp ends.
    orbit_legs = v221_shuffle.constant_rate_legs(
        spans, (resumed.orbit[0][0], resumed.orbit[-1][1])
    )
    dolly_legs = v221_shuffle.constant_rate_legs(
        spans, (resumed.dolly[0][0], resumed.dolly[-1][1])
    )

    base: dict[str, Any] = {
        "fixed_heading": True,
        "bearing": v221_shuffle.START_BEARING,
    }
    if plan.elevation is not None:
        base["elevation"] = plan.elevation
    edit = tuple(
        (
            v221_shuffle.START_LENS,
            low,
            high,
            {**base, "orbit": tuple(orbit_legs[index]), "dolly": tuple(dolly_legs[index])},
        )
        for index, (low, high) in enumerate(windows)
    )
    lens = next(cut for cut in cameras.SECTIONS if cut.name == v221_shuffle.START_LENS)
    return cameras.build_track(
        replay, machine, sections=(lens,), fps=fps, edit=edit
    )


def opening_windows(hook=HOOK, fps: int = FPS) -> tuple[tuple[float, float], ...]:
    """The hook's window and the start's, in the order the film plays them."""
    return ((hook.opens_at, hook.hands_over(fps)), *start_windows(hook, fps))


def build_opening_track(
    replay: dict[str, Any],
    machine,
    hook=HOOK,
    fps: int = FPS,
    plan=None,
) -> dict[str, Any]:
    """The hook and V24's start windows as one track.

    The hook is solved *against this start track* rather than against a
    `StartPlan`'s, because V24's start is not a shape a `StartPlan` can hold -
    it has an omission inside it and its legs are re-split. The hook reads two
    things from the shot it lands on, its opening pose and its opening rate, and
    both are read from the track that will actually follow it. See
    `v24_hook.build_hook_track`.
    """
    start = build_start_track(replay, machine, hook, fps, plan)
    hook_track = v24_hook.build_hook_track(
        replay, machine, hook, plan, fps, start_track=start
    )
    return _assemble(
        [hook_track["cuts"][0], *start["cuts"]], opening_windows(hook, fps), replay, fps
    )


# --- the body ---------------------------------------------------------------
#
# One omission and one truncation, both on cuts `v221` has already solved.

# The spinner trap: the field held against the turning blades, churn 3.18 to
# 4.75 and the lowest sustained stretch in the race body. The pacing lab's
# placement, resuming 0.896 s before the leader's escape at replay 14.996.
#
# `TRAP_FROM` is the last frame the film shows and `TRAP_TO` is the window
# *bound* the far side opens on, so the frame it resumes on is 14.100 - the
# pacing lab's own resume - and the 0.517 s between them is the omission.
#
# The near edge is derived from `v24_timeline.TRAP`'s master frames rather than
# typed. The V22.1 master's obstacle window opens at replay 9.666667 and its
# first *rendered* frame is 451 + 1, so master frame f inside it shows
#
#     replay = OBSTACLE_FROM + (f - OBSTACLE_ROW_ZERO) / fps
#
# `tests/test_sloped_v24_integration.py` pins it against `load_master`'s own
# reading of the delivered track, so a track that concatenates differently
# fails there rather than silently moving the cut.
_OBSTACLE_FROM = 580              # frames: replay 9.666667, the window's bound
OBSTACLE_ROW_ZERO = 451           # the master frame that bound would have been
OBSTACLE_FROM = _sec(_OBSTACLE_FROM)
TRAP_FROM = _sec(_OBSTACLE_FROM + TRAP.first - 1 - OBSTACLE_ROW_ZERO)

# **The far edge is the pacing lab's moved four frames, and the four frames are
# the spinner's own phase lock.**
#
# The start's mixer omission is phase-exact because `v221_shuffle` locked it to
# the rotor, and `v24_spin.MACHINE_KEYS` - the constraint every earlier pass
# checked a cut against - is `start.rotor0..3` and nothing else. That is the
# right set for a cut in the start shot. The trap cut is not in the start shot:
# its subject is `obstacle.wheel0..2`, three four-bladed wheels the field is
# being held against, and no pass before this one had them in a check.
#
# Measured on the replay's own actuator quaternions, with the near edge fixed at
# TRAP_FROM and the far edge slid a frame at a time. A wheel has four identical
# blades, so its symmetry period is 90 degrees and the error is the distance
# from a whole number of quarter turns plus the one frame step a join is owed:
#
#     resume     omitted   blades step   phase error   marbles move
#     14.0167    25 f       89.38 deg       4.06 deg     0.820 units
#     14.0333    26 f       92.82           0.62         0.859        <- taken
#     14.0833    29 f      103.13           9.69         0.974
#     14.1000    30 f      106.57          13.13         1.013        <- the lab's
#
# 14.0333 is better on the blades by a factor of twenty-one and better on the
# marbles as well, and it costs four frames of runtime. One frame of blade step
# is 3.44 degrees, so the lab's placement puts 3.8 frames of blade rotation into
# a single frame on the one mechanism the shot is looking at.
TRAP_RESUME_FRAMES = 26
TRAP_TO = _sec(_OBSTACLE_FROM + TRAP.first - 1 - OBSTACLE_ROW_ZERO
               + TRAP_RESUME_FRAMES)
TRAP_FRAME = _sec(_OBSTACLE_FROM + TRAP.first - OBSTACLE_ROW_ZERO
                  + TRAP_RESUME_FRAMES)

# The actuator families a join has to be phase-clean on, per shot. There is one
# entry rather than one constant because "the machine" is a different machine in
# the start shot and in the spinner corridor, and checking the wrong one is
# exactly the gap this pass found. `tools/sloped_v24_audit.py` reports every
# family across every join and flags the one that is on screen.
IN_FRAME_ACTUATORS: dict[str, tuple[str, ...]] = {
    "spin": ("start.rotor",),
    "fall": ("start.rotor",),
    "trap": ("obstacle.wheel0_blade", "obstacle.wheel1_blade",
             "obstacle.wheel2_blade"),
}

# How far out of its own symmetry a mechanism on screen may land, in degrees.
# One frame of the slowest of them is 3.44 degrees, so this is under half a
# frame's worth of rotation appearing where none should.
PHASE_BAR_DEG = 1.5

# Where the master stops. Not a join - there is no far side - so it costs no
# continuity at all, only the crossings after it.
#
# Seed 5432 crosses at 20.850, 21.133, 21.717, 22.633, 22.650, 23.500, 24.317
# and 24.417. **The winner is the first of those**, which is the whole reason a
# tail this short is legible: PURPLE has already won by 20.850 and everything
# after it is the field arriving.
#
# **The number is derived rather than chosen.** The payoff card is up a
# recognition beat after the winner's crossing and runs its own length, and the
# film ends when the card does - so the tail is exactly as long as the payoff
# needs and not a frame longer:
#
#     20.850   the winner crosses
#    + 0.800   BEAT, the bottom of `v24_payoff.schedule`'s 0.8-1.5 s band
#    + 1.800   PAYOFF_SECONDS, long enough to read two lines twice
#    = 23.450
#
# which is 0.050 s short of the sixth crossing at 23.500. Five marbles arrive,
# and no sixth is caught half way down the channel by the last frame.
#
# Candidate B stops at 23.000 and would leave the card 1.267 s, which is under
# the length the payoff lab measured it needs. 0.450 s is what that costs, and
# `RUNTIME` carries it: the brief's ceiling is a preference and the payoff's
# legibility is a requirement.
WINNER_CROSSES = 20.85
BEAT = 0.8
TAIL_AT = round(WINNER_CROSSES + BEAT + PAYOFF_SECONDS, 6)

# The two omissions inside the body, and the one inside the start, as
# `(replay before, replay after)` pairs of **rendered** instants.
OMISSIONS: tuple[tuple[str, float, float], ...] = (
    ("spin", CUT_AT, RESUME_FRAME),
    ("fall", FALL_AT, _sec(round(v221.START_HANDOFF * FPS) + 1)),
    ("trap", TRAP_FROM, TRAP_FRAME),
)
BODY_OMISSIONS = OMISSIONS[2:]


def split_cut(
    cut: dict[str, Any], keep_to: float, resume_from: float, fps: int = FPS,
) -> list[dict[str, Any]]:
    """One solved cut as two, with the replay between the bounds dropped.

    The camera is untouched: every surviving row is the row the shot already
    had, at the replay instant it already had, so the two halves are the same
    solve seen either side of a gap. That is what makes this a *window* split
    and not a re-solve - and it is why the pacing lab's warning about camera
    discontinuity does not apply to it, the discontinuity being exactly the
    0.517 s of the camera's own travel that the gap omits.
    """
    rows = cut["frames"]
    first = [row for row in rows if float(row[0]) <= keep_to + 1e-9]
    second = [row for row in rows if float(row[0]) >= resume_from - 1e-9]
    if not first or not second:
        raise ValueError(
            f"the split at {keep_to}-{resume_from} leaves {cut['name']} with an "
            f"empty half ({len(first)} and {len(second)} rows)"
        )
    head = {**cut, "to": round(float(first[-1][0]), 6), "frames": first}
    tail = {**cut, "from": round(float(second[0][0]), 6), "frames": second}
    return [head, tail]


def trim_cut(cut: dict[str, Any], keep_to: float) -> dict[str, Any]:
    """One solved cut with everything after a replay instant dropped."""
    rows = [row for row in cut["frames"] if float(row[0]) <= keep_to + 1e-9]
    if not rows:
        raise ValueError(f"the trim at {keep_to} leaves {cut['name']} empty")
    return {**cut, "to": round(float(rows[-1][0]), 6), "frames": rows}


def _assemble(
    cuts: Sequence[dict[str, Any]],
    windows: Sequence[tuple[float, float]],
    replay: dict[str, Any],
    fps: int = FPS,
) -> dict[str, Any]:
    """A `cameras`-schema track from cuts and the windows they play.

    The edit map is built by laying the windows end to end in output time, so
    **every segment has slope 1 by construction** and the film's duration is the
    sum of the window spans. This is the shape `presentation.load` reads and the
    shape `sloped_race_scene.gd` renders; nothing downstream has to know which
    of the boundaries used to be inside a shot.
    """
    if len(cuts) != len(windows):
        raise ValueError(f"{len(cuts)} cuts against {len(windows)} windows")
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for cut, (low, high) in zip(cuts, windows):
        span = round(high - low, 6)
        if span <= 0.0:
            raise ValueError(f"{cut['name']} has an empty window {low}-{high}")
        segments.append(
            {
                "cut": cut["name"],
                "out": [round(cursor, 6), round(cursor + span, 6)],
                "replay": [round(low, 6), round(high, 6)],
            }
        )
        cursor = round(cursor + span, 6)
    covered = windows[-1][1] - windows[0][0]
    crossings = [
        float(event["t"]) for event in replay.get("events", ())
        if event.get("kind") == "finish_line"
    ]
    return {
        "units": "layout",
        "fps": fps,
        "seed": replay["seed"],
        "edited": True,
        "chase": True,
        "rule": "adaptive",
        "duration": round(cursor, 6),
        "replay_duration": float(replay["frames"][-1]["t"]),
        "omitted": round(max(0.0, covered - cursor), 6),
        "last_crossing": round(max(crossings) if crossings else 0.0, 6),
        "edit": segments,
        "cuts": list(cuts),
    }


def build_race_track(
    replay: dict[str, Any], machine, fps: int = FPS,
) -> dict[str, Any]:
    """The V24 camera track: a new opening on V22.1's own body.

    Three operations, in the order they depend on each other:

    1. the body is `v221.build_race_track` - the same chase solved over the same
       replay seconds against the same bookends, so the descent, the obstacle,
       the fork, the branches, the merge and the parked finish are pose for pose
       what the delivered film renders;
    2. its two start cuts are replaced by the hook and V24's start windows,
       which are solved here;
    3. the obstacle cut is split at the trap and the finish cut is trimmed.

    The chase is solved *before* anything is taken out of it, which is the point:
    its first pose still comes from a start shot that ends at `v221.START_HANDOFF`,
    so V24's start ending 0.283 s earlier changes where the chase picks the field
    up and not how the chase was solved.
    """
    body = v221.build_race_track(replay, machine, fps=fps)
    opening = build_opening_track(replay, machine, fps=fps)

    cuts: list[dict[str, Any]] = list(opening["cuts"])
    windows: list[tuple[float, float]] = [
        (float(row["replay"][0]), float(row["replay"][1])) for row in opening["edit"]
    ]

    body_segments = [row for row in body["edit"] if row["cut"] != "start"]
    body_cuts = [cut for cut in body["cuts"] if cut["name"] != "start"]
    if len(body_segments) != len(body_cuts):
        raise ValueError("the V22.1 body's cuts and edit map disagree")

    for cut, segment in zip(body_cuts, body_segments):
        low, high = float(segment["replay"][0]), float(segment["replay"][1])
        if cut["name"] == "obstacle":
            head, tail = split_cut(cut, TRAP_FROM, TRAP_TO, fps)
            cuts.extend((head, tail))
            windows.extend(((low, TRAP_FROM), (TRAP_TO, high)))
        elif cut["name"] == "final":
            cuts.append(trim_cut(cut, TAIL_AT))
            windows.append((low, TAIL_AT))
        else:
            cuts.append(cut)
            windows.append((low, high))

    return _assemble(cuts, windows, replay, fps)


# --- what the renderer will actually draw -----------------------------------


def rendered_instants(track: dict[str, Any]) -> list[float]:
    """The replay second every output frame of this track shows.

    `presentation._window_of` takes the **first** window an output second falls
    in, and consecutive windows share their boundary - so a window written
    `from X` first appears at `X + 1/fps` and the frame at `X` belongs to the
    window before it. That is the renderer's own rule, settled from the pixels
    by the pacing lab, and it is the difference between a phase-exact rotor join
    and one that is a frame out. See the module docstring.
    """
    fps = int(track.get("fps", FPS))
    clock = presentation.Clock(
        tuple(
            (
                float(row["out"][0]), float(row["out"][1]),
                float(row["replay"][0]), float(row["replay"][1]),
            )
            for row in track["edit"]
        ),
        hold=0.0,
        fps=fps,
        master_frames=master_frames(track),
    )
    out: list[float] = []
    for frame in range(clock.master_frames):
        when = clock.replay_at(frame / float(fps))
        if when is None:
            raise ValueError(f"output frame {frame} is in no window")
        out.append(round(when, 6))
    return out


def master_frames(track: dict[str, Any], fps: int | None = None) -> int:
    """How many frames the renderer writes for this track.

    The renderer's own rule - frames 0 to `round(duration * fps)` inclusive -
    which is what `sloped_v22._render` asks Godot for with `--end`.
    """
    fps = int(fps or track.get("fps", FPS))
    return int(round(float(track["duration"]) * fps)) + 1


def film_clock(
    replay_path: str, track_path: str, frames: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any], presentation.Clock]:
    """The replay, the track and the clock the finished V24 runs on.

    **No prefix and no hold.** V24 has no course preview to put in front and it
    does not freeze its first frame, so the film's second zero is the master's
    first frame and `Clock.origin` is 0.0. Both are the experiment: the hook is
    what the opening is instead.
    """
    import json

    with open(track_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    replay, track, clock = presentation.load(
        replay_path, track_path, frames if frames is not None else master_frames(track)
    )
    return replay, track, presentation.Clock(
        clock.segments, hold=0.0, fps=clock.fps,
        master_frames=clock.master_frames, prefix=0.0,
    )
