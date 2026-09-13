"""V22.1: the three continuity prototypes as one film.

V22 was watched end to end and three things were reported about it, all of them
about *joins* rather than about shots:

    the course preview is too fast to read
    the shuffle still looks cut
    the last chase hits the finish as a jump

This module is where the three prototypes that answered those meet production.
Like `sloped.v22` before it, almost all of it is about **one clock**:

    OUTPUT  0.000 -  3.500    the course preview, 210 frames of its own footage
    OUTPUT  3.500 -  4.200    the held first race frame, under PICK ONE
    OUTPUT  4.200 - 26.533    the race, through `edit()`

and, as before, nothing here re-simulates, re-seeds or re-solves the physics.
The replay is the locked `race_5432.json`, the finish order is still
5, 2, 7, 4, 1, 6, 3, 0, and every number below is a decision about which of its
frames to render and from where.

## What changed from V22, in one line each

**The preview is 210 frames rather than 120, and it spends them unevenly.**
`v221_preview` is the same solver as `course_preview` with one function of it
substituted - the map from frame to station - so a landmark's share of the shot
is authored rather than falling out of its length. See `PACING`.

**The start omits 116 frames from inside the rotor's constant-rate spin rather
than 235 frames across its spin-down.** `v221_shuffle.PLANS["b116"]`: four whole
rotor revolutions, so the blades are continuous across the join to a hundredth
of a degree, with the camera's legs computed by `constant_rate_legs` so its
position *and* its velocity carry through as well. See `START`.

**The finish is the end of the chase rather than a shot after it.** The chase
decelerates from its own velocity at replay 18.900 onto a stand behind the line
and holds while all eight arrive. See `FINISH`.

## The one ordering constraint, and why it is a call graph rather than a comment

The b116 start stands the opening lens at elevation 30 with its own orbit legs,
which moves the race camera's first pose about 1.6 layout units from where V22
had it. The preview is solved *to* that pose. So the preview cannot be built
until the race track is, and `build_preview_track` takes the race track as its
first argument for exactly that reason - there is no way to call these two in
the wrong order.

## What `prefix` is, and the arithmetic trap `sloped.v22` documented

The preview is **210 rendered frames**, and what it costs the output clock is
`210 / 60 = 3.500 s` exactly. Its own report calls its duration 3.4833 s, the
span from the first frame's centre to the last's. `presentation.Clock.prefix` is
seconds of output, so it is given 3.500. `preview_prefix` is `sloped.v22`'s and
is imported rather than rewritten.

## The eighth column

V22 checked its handoff on six numbers - position and aim - and the field of
view was not one of them. It was 48 degrees at the preview's last frame and 34
at the race's first, which is a zoom snap nobody measured because nobody looked.
`v221_preview._fov_land` eases the column and `assert_handoff` below now reads
all seven, so the same defect cannot come back unnoticed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sloped import (
    chase_camera,
    course_preview,
    terrain,
    v22,
    v221_finish,
    v221_preview,
    v221_shuffle,
)
from sloped.v221_finish import Candidate, Pose
from sloped.v22 import FPS, film_clock, preview_frames, preview_prefix

__all__ = [
    "EDIT",
    "FINISH",
    "FPS",
    "PACING",
    "PREVIEW_FRAMES",
    "PREVIEW_SECONDS",
    "START",
    "START_HANDOFF",
    "assert_handoff",
    "build_preview_track",
    "build_race_track",
    "edit",
    "film_clock",
    "handoff_pose",
    "preview_frames",
    "preview_prefix",
    "rail",
]

# The edit plan's name, for the reports and the edition table. It is *not* a key
# in `cameras.EDITS`: see `edit()`.
EDIT = "v221"

# --- the start --------------------------------------------------------------
#
# `b116` of the shuffle pass, taken by name rather than by its numbers so that
# the plan the proofs were rendered from is the plan production runs. What it is:
#
#     replay 0.200 - 2.050   live. The gates open at 0.317, the field pours down
#                            the apron, the rotor takes hold at 1.600
#     116 frames omitted     1.933 s of screen nobody sees, 1.950 s between the
#                            two window edges - see `StartPlan.omitted`. Four
#                            whole revolutions at 13.0 rad/s, so the blades come
#                            back within a hundredth of a degree of where they
#                            left
#     replay 4.000 - 7.620   live. The spin-down at 4.600-4.900, the blades
#                            lifting out of the drum at 5.200-5.900, stillness,
#                            and the trapdoor at 6.100
#
# V22 put 3.487 s of this on screen and landed 0.267 s before the trapdoor, with
# the blades already up. This puts 4.550 s on screen and 1.500 s of it is the
# anticipation - the machine visibly winding down, withdrawing its own blades
# and stopping before the floor goes.
#
# **One number is production's rather than the prototype's: `tail_to`.**
#
# The shuffle pass ended its start window at replay 7.620 because that is where
# V21.2 and V22 end theirs, and it flagged - without being able to check it,
# having rendered no integrated film - that the field is "mostly through the
# chute by roughly replay 6.6" and the shot might then be holding on an empty
# machine. The integrated render says it is, and by more than that guess:
# measured against the trapdoor panels' own height, **every marble is below the
# chamber floor by replay 6.400**, 1.220 s before the window ends. The frames
# bear it out - at 6.9, 7.2 and 7.6 the drum is empty and the lens is still
# dollying across it.
#
# The fix the brief asks for, and the only honest one: **move the camera's
# handoff, not the clock**. No replay second is omitted, nothing is sped up and
# no physics is deleted - replay 6.700 to 7.620 is still in the film, shot by
# the chase camera following the field down the launch chute instead of by the
# start lens watching the box they left. Runtime is unchanged at 26.533 s.
#
# 6.700 is 0.300 s after the last marble clears the floor, which is enough to
# see them go, and it is where the handoff measures best. Swept against the
# integrated track:
#
#     tail_to   start->chase jump   racers in frame, first second of chase
#      6.500          0.066                        8.00
#      6.700          0.058                        8.00      <- taken
#      6.850          0.069                        8.00
#      7.000          0.081                        7.98
#      7.620          0.243                        7.85      <- V22's boundary
#
# Every earlier boundary beats 7.620 on both, because the chase picks the pack
# up while it is still together rather than a second after it has strung out.
# The legs stay constant-rate: `constant_rate_legs` re-splits the same 40-degree
# orbit across the shorter second window, so the rate rises from 7.3 to 8.8
# degrees a second - 0.15 degrees a frame - and the first pose, which the
# preview lands on, does not move at all.
START_HANDOFF = 6.700

START = replace(v221_shuffle.PLANS["b116"], name="b116_v221",
                tail_to=START_HANDOFF)

# --- the preview ------------------------------------------------------------
#
# 3.500 s, the longest of the three the breathing pass measured and the one it
# recommends. `Pacing` carries the landmark dwell table, the two end terms and
# the quadrature; `preview_spec` carries the two composition numbers the pacing
# forced (`FINISH_OVERRUN`, `AIM_LIFT`). Both are the prototype's, unmodified.
PREVIEW_SECONDS = 3.5
PACING = v221_preview.Pacing(seconds=PREVIEW_SECONDS, name=EDIT)
PREVIEW_FRAMES = PACING.frames()

# --- the finish -------------------------------------------------------------
#
# Candidate A of the finish pass: a chase that stops chasing. Retyped here
# rather than imported from `tools/sloped_v221_finish.py`, because a library may
# not import a tool - and pinned against that tool's own numbers by
# `tests/test_sloped_v221_integration.py`, so the two cannot drift apart in
# silence.
#
#     split 18.900     the merge phase's own fastest frame. The settle is bought
#                      with the chase's entry speed, so the split that leaves
#                      the most room is the one the chase is moving quickest at
#     ratio 2.0        the middle of `v221_finish.MIN_RATIO`'s band: the lens
#                      never moves faster than the chase already was
#     aim_settle 1.2   the aim reaches the line 1.48 s before the lens does,
#                      which is the anticipation - 1.37 s of visible finish line
#     bearing 180      directly up-course, behind the racers
#     radius 26        the winner is 54.9 px at the crossing and the smallest
#                      crossing 52.6 px, both over `readability.MIN_MEDIAN_PX`
#
# There is no `Orbit`. Candidate B swings onto V19's lens afterwards and needs
# 5.4 s to clear the gantry legs without crossing a racer; A simply holds, and
# the film ends on the stand it parked at.
FINISH = Candidate(
    name="a_chase",
    split=18.900,
    park=Pose(bearing=180.0, radius=26.0, height=18.0, aim_ahead=0.0,
              aim_lift=1.0, fov=36.0),
    ratio=2.0,
    aim_settle=1.2,
    note="V22.1: continuous rear chase parked behind the finish line",
)


def edit(base: str = v22.EDIT) -> tuple[tuple, ...]:
    """V22's edit map with its two start windows replaced by `START`'s.

    Everything else is V22's to the microsecond - the restored obstacle window,
    the nine middle lenses, the finish bound at 24.467 - because V22.1 is a pass
    over three joins and not over the race body. The finish *window* stays in
    the plan and is then dropped by `v221_finish.build`, which cannot drop what
    was never solved: the park has to continue a chase that reached replay
    18.900, and that chase's far bound is this plan's finish entry.
    """
    plan = chase_camera.edit_plan(base)
    windows = v221_shuffle.plan_windows(START)
    out: list[tuple] = []
    taken = False
    for entry in plan:
        if entry[0] == v221_shuffle.START_LENS:
            if not taken:
                out.extend(windows)
                taken = True
            continue
        out.append(tuple(entry))
    if not taken:
        raise ValueError(f"the {base!r} edit has no start window to replace")
    return tuple(out)


def build_race_track(replay: dict[str, Any], machine, fps: int = FPS) -> dict[str, Any]:
    """The V22.1 race camera track: V22's chase, new bookends at both ends.

    Two rewrites of one solve, in the order they depend on each other. The start
    is an *input* to the chase - `chase_camera` reads the edit's start windows to
    know where its own first phase begins - so it goes in through `edit`. The
    finish is an *output* of it: `v221_finish.build` needs the chase's own
    velocity at replay 18.900, which does not exist until the chase is solved.
    """
    base = chase_camera.build_chase(replay, machine, fps=fps, edit=edit())
    return v221_finish.build(base, replay, machine, FINISH, fps=fps)


def handoff_pose(track: dict[str, Any]) -> tuple[tuple[float, float, float],
                                                 tuple[float, float, float]]:
    """The race camera's very first `(position, aim)`. `sloped.v22`'s."""
    return v22.handoff_pose(track)


def rail(track: dict[str, Any]) -> v221_preview.Rail:
    """The race camera's opening, readable at negative frame offsets.

    The preview's tail is eased onto this rather than onto one fixed pose, so it
    arrives moving at the rate the start shot leaves at. See `v221_preview.Rail`.
    """
    return v221_preview.Rail(track["cuts"][0]["frames"])


def build_preview_track(
    race_track: dict[str, Any],
    machine,
    seed: int,
    pacing: v221_preview.Pacing | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The paced preview that ends on the race camera's own first frame.

    Returns the camera track and `v221_preview.pace_report`'s reading of it,
    with `problems` from `check_v221` - the shipped bar minus its duration
    clause, which this pass is deliberately outside, plus the four the pacing
    introduces.

    Measured at stride 1 rather than the report's default 2: the whole claim of
    this pass is that it has more frames, and the one centre-blocked frame the
    prototype found lives between V22's.
    """
    from sloped import sightlines

    pacing = pacing or PACING
    spec = v221_preview.preview_spec(v22.PREVIEW)
    line = course_preview.course_line()
    spine = course_preview.corridor(line)
    cfg = terrain.terrain_config()
    track_rail = rail(race_track)
    solved = v221_preview.build(
        pacing, spec, rail=track_rail, land="rail", line=line, spine=spine, cfg=cfg
    )
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    report = v221_preview.pace_report(
        solved, bundle=bundle, rail=track_rail, stride=1
    )
    report["problems"] = v221_preview.check_v221(report)
    return v221_preview.preview_track(solved, seed=seed), report


def assert_handoff(race: dict[str, Any], preview: dict[str, Any]) -> dict[str, float]:
    """The preview's last frame and the race's first, compared on **all seven**.

    `sloped.v22`'s check reads columns 1 to 6 - position and aim - and passed a
    film whose field of view stepped 48 to 34 degrees across the join. A zoom
    snap is a cut; it just is not one a positional check can see. Returns the
    per-column deltas so a report can print them rather than only assert them.
    """
    return v22.assert_handoff(race, preview, columns=len(v22.HANDOFF_COLUMNS))
