"""V22: the course preview, the restored pacing and the chase camera, as one film.

Three prototypes solved three problems apart from each other. This module is the
place they meet, and almost all of it is about **one clock**:

    OUTPUT 0.000 - 2.000      the course preview, 120 frames of its own footage
    OUTPUT 2.000 - 2.700      the held first race frame, under PICK ONE
    OUTPUT 2.700 - 23.050     the race, through `cameras.EDITS["v22"]`

Nothing here re-simulates, re-seeds or re-solves the physics. The replay is the
locked `race_5432.json` it has been since V1.15, the finish order is still
5, 2, 7, 4, 1, 6, 3, 0, and every window below is a decision about which of its
frames to render and from where.

## The three things integration actually had to decide

**Where the preview hands over.** `course_preview.Preview.end_pose` was built to
take the race camera's first pose, and the race camera's first pose is now the
chase's start shot at `chase_camera.START_BEARING` - round behind the machine,
32 degrees off the axis the preview's reverse dolly arrives on. See
`cameras.V22_START_ORBIT`: the *live* start shot spends that angle, at 0.39
degrees a frame under the gates opening, instead of the preview spending it at
1.9 degrees a frame under a decelerating flight. The preview then lands on the
chase's own first frame exactly, so there is no cut between them at all.

**That the obstacle needs no special handling.** The pacing pass asked for replay
14.500-15.350 back, and the chase covers replay 7.620-20.200 in one unbroken
span - so the restoration is not a window that had to be added, it is a window
that the chase never had. The film's *only* omission after V22 is the one in the
start, which is why there is exactly one whoosh.

**That the finish is a bookend, not a chase phase.** `chase_camera` already
lifts V21's start and finish lenses out of `cameras.EDITS`; extending the finish
to replay 24.467 so all eight marbles actually cross is therefore a change to the
edit plan and nothing else.

## What `prefix` is, and the one arithmetic trap in it

The preview is **120 rendered frames**, and what it costs the output clock is
`120 / 60 = 2.000 s` exactly. Its own report calls its duration 1.9833 s, which
is the span from the first frame's centre to the last's - a real number about a
different question. Taking it would put every cue in the film one frame early.
`presentation.Clock.prefix` is seconds of output, so it is given 2.000.
"""

from __future__ import annotations

import json
import os
from typing import Any

from sloped import cameras, chase_camera, course_preview, presentation, terrain

__all__ = [
    "EDIT",
    "FPS",
    "HANDOFF_COLUMNS",
    "HANDOFF_TOLERANCE",
    "PREVIEW",
    "assert_handoff",
    "build_preview_track",
    "build_race_track",
    "film_clock",
    "handoff_pose",
    "preview_prefix",
]

FPS = 60

# The edit plan the race master is rendered to. See `cameras.EDIT_V22`.
EDIT = "v22"

# The preview, as V22 ships it. Three of its numbers are the course-preview
# pass's own and two are integration's:
#
# * `ease` 0.65 -> 0.45. The authored 0.65 was chosen so the flight settles into
#   the handoff - "reads as arriving rather than as being cut away from". With
#   an explicit `end_pose` that argument moves: the blend is a smootherstep onto
#   the target, so its velocity is already zero at the last frame whatever the
#   ease does, and a firm ease now only piles the flight's own motion into the
#   middle of the shot where the blend is also working. Measured, 0.65 leaves
#   the lens moving 1.71 layout units in a frame against the 1.60 a dolly may;
#   0.45 brings it to 1.59 and the shot passes `check_preview` clean.
# * `end_blend` 0.32 -> 0.72, for the same reason from the other side: the
#   handoff is a real move now rather than a nudge, and 0.32 of the shot is not
#   enough room to spend it in.
#
# `lead`, `lift`, `aim_lift`, `sway`, `fov` and the two overruns are untouched.
PREVIEW = course_preview.Preview(ease=0.45, end_blend=0.72, name="v22")


# The camera record's columns after the timestamp, in the order a track row
# writes them. **The eighth is the field of view and V22 does not check it**:
# see `assert_handoff`.
HANDOFF_COLUMNS = ("px", "py", "pz", "ax", "ay", "az", "fov")

# How far apart the two frames may be, per column. The end blend sets the pose
# exactly, so this is a rounding tolerance rather than a budget.
HANDOFF_TOLERANCE = 5e-4


def handoff_deltas(
    race: dict[str, Any], preview: dict[str, Any], columns: int = len(HANDOFF_COLUMNS),
) -> dict[str, float]:
    """Per-column distance between the preview's last frame and the race's first."""
    last = preview["cuts"][-1]["frames"][-1]
    first = race["cuts"][0]["frames"][0]
    return {
        name: abs(float(last[index]) - float(first[index]))
        for index, name in enumerate(HANDOFF_COLUMNS[:columns], start=1)
    }


def assert_handoff(
    race: dict[str, Any],
    preview: dict[str, Any],
    columns: int = 6,
    tolerance: float = HANDOFF_TOLERANCE,
) -> dict[str, float]:
    """The preview's last frame and the race's first must be the same camera.

    This is the whole claim of the opening - that there is no cut between the
    preview and the race - so it is checked rather than assumed.

    **`columns` defaults to six, which is position and aim, and that default is
    a statement about V22 rather than about what a handoff is.** V22's preview
    ends at a 48-degree field of view and its race begins at 34, so a
    seven-column check would fail the delivered film; the zoom snap is real and
    it is what V22.1 fixes. Editions that ease the eighth column - see
    `v221_preview._fov_land` - pass `columns=7` and get the stricter reading.
    """
    deltas = handoff_deltas(race, preview, columns)
    worst = max(deltas.values())
    if worst > tolerance:
        column = max(deltas, key=deltas.__getitem__)
        raise ValueError(
            f"the preview does not arrive on the race camera: {column} is "
            f"{worst:.6f} apart at the handoff"
        )
    return deltas


def handoff_pose(track: dict[str, Any]) -> tuple[tuple[float, float, float],
                                                 tuple[float, float, float]]:
    """The race camera's very first `(position, aim)`, in layout units.

    This is the pose the preview is asked to arrive at, so the two pieces of
    footage meet on one lens rather than on a cut.
    """
    first = track["cuts"][0]["frames"][0]
    return (tuple(first[1:4]), tuple(first[4:7]))


def build_race_track(replay: dict[str, Any], machine, fps: int = FPS) -> dict[str, Any]:
    """The V22 race camera track: chase phases between V21's two bookends."""
    return chase_camera.build_chase(replay, machine, fps=fps, edit=EDIT)


def build_preview_track(
    race_track: dict[str, Any],
    machine,
    seed: int,
    spec: course_preview.Preview | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The preview flight that ends on the race camera's first pose.

    Returns the camera track and `course_preview.path_report`'s reading of it.
    """
    from sloped import sightlines

    spec = spec or PREVIEW
    spec = course_preview.Preview(
        **{**spec.__dict__, "end_pose": handoff_pose(race_track)}
    )
    line = course_preview.course_line()
    spine = course_preview.corridor(line)
    cfg = terrain.terrain_config()
    solved = course_preview.build_preview(spec, line=line, spine=spine, cfg=cfg)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    report = course_preview.path_report(solved, bundle=bundle)
    report["problems"] = course_preview.check_preview(report)
    return course_preview.preview_track(solved, seed=seed), report


def preview_prefix(preview_track: dict[str, Any], fps: int = FPS) -> float:
    """Output seconds the preview occupies: **frames over fps**, not `duration`.

    A 120-frame preview at 60 fps holds the screen for 2.000 s. Its `duration`
    is 1.9833, the span of its frame *centres*, and using that here would put
    the whole race a frame early. See the module docstring.
    """
    return preview_frames(preview_track) / float(fps)


def preview_frames(preview_track: dict[str, Any]) -> int:
    """How many distinct frames the preview renders.

    Not the sum of the cuts' row counts: consecutive cuts share a boundary row
    on purpose - see `course_preview.preview_track` - so that sum over-counts by
    one per join.
    """
    times = {
        round(float(row[0]), 6)
        for cut in preview_track["cuts"]
        for row in cut["frames"]
    }
    return len(times)


def film_clock(
    replay_path: str,
    race_track_path: str,
    master_frames: int,
    prefix: float,
) -> tuple[dict[str, Any], dict[str, Any], presentation.Clock]:
    """The replay, the race track and the clock the finished V22 runs on."""
    return presentation.load(
        replay_path, race_track_path, master_frames, prefix=prefix
    )
