"""Solve, measure and render the V22.1 finish candidates.

    python tools/sloped_v221_finish.py --stage sweep
    python tools/sloped_v221_finish.py --stage measure
    python tools/sloped_v221_finish.py --stage render --godot PATH
    python tools/sloped_v221_finish.py --stage sheet

Stages:

    solve    write each candidate's camera track and its five-second clip
    sweep         the park pose, measured rather than chosen
    sweep-split   where the chase stops following, and when the aim looks ahead
    sweep-orbit   what the camera may do once the winner is past
    measure  every number the brief asks for, per candidate, as JSON and text
    render   Godot renders each candidate's clip; ffmpeg encodes it
    sheet    a phone-size contact sheet at the crossings, candidates side by side
    all      solve, measure, render, sheet

**Nothing here renders the whole film and nothing re-simulates.** The replay is
the locked `race_5432.json`, read and never written; every candidate is the
frozen V22 track with its tail replaced, and `v221_finish.finish_clip` re-times
the edit so Godot walks only the last few seconds.

## The metrics, and which of them is new

`camera_step`, `turn_rate`, `px`, `in_frame` and `hidden_share` all come from
the production instruments - `sloped.readability` and `sloped.sightlines` - so
a V22.1 number is comparable with a V22 one by construction.

Three are new because the brief asks three questions the film has not had to
answer before:

* **`finish_lead`** - how long before the winner crosses a viewer can see the
  line. Measured as the longest unbroken run of sampled frames, ending at the
  crossing, in which the finish node projects inside the frame with a margin
  *and* no drawn surface stands between the lens and it. Anticipation is the
  thing the brief is buying and this is its unit.
* **`crossings`** - per racer, at its own crossing instant: is it in frame, how
  big is it, how far from the line is it on screen, and is anything in front of
  it. A finish shot that is smooth and shows nobody crossing has failed.
* **`discontinuities`** - frames where the lens moves more than
  `chase_camera.MAX_PHASE_STEP` or the view direction turns more than
  `MAX_TURN_RATE`, counted over the whole track rather than per cut, plus the
  measured jump at every edit boundary. One number for "how many times does the
  picture change abruptly".
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from sloped import (
    cameras,
    chase_camera,
    presentation,
    readability,
    sightlines,
    terrain,
    v22,
    v221_finish,
)
from sloped.course import sloped_course
from sloped.v221_finish import Candidate, Orbit, Pose

PROJECT_ROOT = os.getcwd()
GODOT_PROJECT = os.path.join(PROJECT_ROOT, "godot")
RENDER_SCENE = "res://scenes/SlopedRaceRender.tscn"

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v221")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v221_finish")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
PHONE = (270, 480)
VIDEO_CRF = 18
VIDEO_PRESET = "slow"

# How far back from the last crossing a proof clip starts. Six seconds covers
# the whole of every candidate's move plus a second of chase before it, which
# is what makes the join visible rather than merely measured.
CLIP_SECONDS = 6.4

# A racer is "readable" at 48 px, which is `readability.MIN_MEDIAN_PX` and the
# number every lens in this film has been swept against.
MIN_PX = readability.MIN_MEDIAN_PX

# How near the frame edge the finish line may be and still count as seen. The
# delivery frame is 1080x1920; 90 px is a twelfth of the narrow axis, which is
# about the margin at which a thing stops reading as "ahead" and starts reading
# as "leaving".
EDGE_MARGIN = 90.0


class V221Error(RuntimeError):
    pass


# --- the candidates ---------------------------------------------------------
#
# The park poses are `--stage sweep`'s answers; the reasoning is in
# `docs/sloped_race_v221_finish_continuity.md`. Only the control is not a
# choice.

CONTROL = v221_finish.register(Candidate(
    name="c_v22",
    split=None,
    park=None,
    note="V22 as integrated: chase to replay 20.200, hard cut to V19's finish lens",
))


def candidates(track: dict[str, Any], machine) -> list[Candidate]:
    """The four this pass compares, with B's target read off the control.

    B eases onto *V19's own lens*, so its target pose is taken from the solved
    finish cut rather than retyped - a change to that lens in production reaches
    this comparison without an edit here.

    D is on the list because it is **falsified** and a report should carry the
    measurement rather than only the conclusion: a straight pull-back recovers
    the stragglers a rear park cannot hold, and costs every crossing after the
    third its readability. See `--stage sweep-orbit`.
    """
    lens = v221_finish.lens_pose(track, machine)
    common = {"split": PARK["split"], "park": PARK["pose"], "ratio": PARK["ratio"],
              "aim_settle": PARK["aim_settle"]}
    a = v221_finish.register(Candidate(
        name="a_chase", **common,
        note="continuous rear chase: parks behind the line, never cuts",
    ))
    b = v221_finish.register(Candidate(
        name="b_orbit", **common,
        orbit=Orbit(at=ORBIT["at"], seconds=ORBIT["seconds"], to=lens,
                    ease=ORBIT["ease"]),
        note="rear chase through the winner, then an orbit onto V19's finish lens",
    ))
    d = v221_finish.register(Candidate(
        name="d_pull", **common,
        orbit=Orbit(at=ORBIT["at"], seconds=ORBIT["seconds"], to=PULL["pose"],
                    ease=ORBIT["ease"]),
        note="rear chase, then a straight pull-back instead of an orbit (falsified)",
    ))
    return [a, b, CONTROL, d]


# What `--stage sweep`, `--stage sweep-split` and `--stage sweep-orbit` answer;
# `docs/sloped_race_v221_finish_continuity.md` is why.
#
#   split 18.900    the merge phase's own fastest frame. The settle is bought
#                   with the chase's entry speed, so the split that leaves the
#                   most room is the one the chase is moving quickest at rather
#                   than the earliest one - 18.900 brakes in 2.68 s where
#                   18.600 needs 5.02 and 19.050 loses the finish line entirely
#   ratio 2.0       the middle of `v221_finish.MIN_RATIO`'s band, so the lens
#                   never moves faster than the chase already was
#   aim_settle 1.2  the aim reaches the line 1.48 s before the lens does. This
#                   is the anticipation: 1.37 s of visible finish line against
#                   the control's 0.63, at a *lower* turn rate than tying the
#                   two channels together produces
#   bearing 180     directly up-course. An off-axis park swings the line across
#                   the frame during the settle and breaks the run
#   radius 26       the winner is 54.9 px at the crossing and the smallest
#                   crossing is 52.6 px, both over `MIN_PX`. Not the sweep's own
#                   first choice - ranked by the winner's size it picks radius
#                   20 at height 14, 66.3 px - and the 11.4 px is spent on the
#                   0.29 of a racer and the 4 units of ground clearance that
#                   standing further back buys. See the report; it is the one
#                   number here that is a judgement rather than a measurement
PARK: dict[str, Any] = {
    "split": 18.900,
    "ratio": 2.0,
    "aim_settle": 1.2,
    "pose": Pose(bearing=180.0, radius=26.0, height=18.0, aim_ahead=0.0,
                 aim_lift=1.0, fov=36.0),
}

# **The orbit is slow because of two gantry legs, and that is the whole story
# of candidate B.** `--stage sweep-orbit` measures it: over the azimuth band
# 85-90 degrees (and its mirror at 270-280) the near leg of the finish gantry
# stands between the lens and marble 4, at *every* radius from 14 to 28 and
# every height from 14 to 50. It cannot be flown over, because raising the
# camera slides the sight line down the leg rather than past it.
#
# Any orbit from behind the line to a lens that can read the FINISH board has
# to cross that band. So the only question left is *when*, and the answer is
# "in a gap between crossings": 5.40 s at a 0.45 ease puts the band between the
# 6th finisher at 23.500 and the 7th at 24.317, and every one of the eight
# crosses clear. The first two cross at bearing 180.0 - the orbit has not moved
# at all yet, which is the brief's "only after the winner" taken literally.
#
# The price is that 5.40 s from 20.900 does not finish inside the replay: the
# film ends at bearing 62 rather than V19's 27, still turning at 0.86 degrees a
# frame. See the report.
ORBIT: dict[str, Any] = {"at": 20.900, "seconds": 5.400, "ease": 0.45}

PULL: dict[str, Any] = {
    "pose": Pose(bearing=180.0, radius=38.0, height=26.0, aim_ahead=0.0,
                 aim_lift=1.0, fov=36.0),
}


# --- loading ----------------------------------------------------------------


def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _dump(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=1)


def world(seed: int) -> tuple[dict[str, Any], Any, dict[str, Any], Any]:
    """The replay, the course, the frozen V22 track and the sightline bundle."""
    replay = _load(os.path.join(OUT_DIR, f"race_{seed}.json"))
    machine = sloped_course(routes="both")
    path = os.path.join(OUT_DIR, f"cameras_v22_{seed}.json")
    if os.path.isfile(path):
        track = _load(path)
    else:
        track = v22.build_race_track(replay, machine)
        _dump(path, track)
    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )
    return replay, machine, track, bundle


# --- the measurements -------------------------------------------------------


def _rows(track: dict[str, Any], since: float | None = None) -> list[list[float]]:
    rows = v221_finish._rows(track)
    if since is None:
        return rows
    return [row for row in rows if float(row[0]) >= since - 1e-9]


def _direction(row: Sequence[float]) -> tuple[float, float, float]:
    forward = [float(row[4 + axis]) - float(row[1 + axis]) for axis in range(3)]
    length = math.sqrt(sum(v * v for v in forward)) or 1.0
    return tuple(v / length for v in forward)


def motion(track: dict[str, Any], since: float) -> dict[str, Any]:
    """The lens's own movement, per frame, over the finish window.

    Walked over the **deduped row list** rather than per cut, because a cut
    boundary is exactly where a chase is allowed to hide a jump and this is the
    number that says whether it did. A row pair that straddles an edit omission
    is skipped: the two frames are not consecutive in the replay and the
    distance between them is an edit decision, measured separately as a jump.
    """
    rows = _rows(track, since)
    steps: list[tuple[float, float]] = []
    turns: list[tuple[float, float]] = []
    for before, after in zip(rows, rows[1:]):
        if float(after[0]) - float(before[0]) > 1.5 / FPS:
            continue
        steps.append((float(after[0]), math.dist(before[1:4], after[1:4])))
        one, two = _direction(before), _direction(after)
        dot = max(-1.0, min(1.0, sum(one[a] * two[a] for a in range(3))))
        turns.append((float(after[0]), math.degrees(math.acos(dot))))
    worst_step = max(steps, key=lambda pair: pair[1]) if steps else (0.0, 0.0)
    worst_turn = max(turns, key=lambda pair: pair[1]) if turns else (0.0, 0.0)
    return {
        "frames": len(rows),
        "max_step": round(worst_step[1], 4),
        "max_step_at": round(worst_step[0], 4),
        "mean_step": round(sum(s for _t, s in steps) / max(len(steps), 1), 4),
        "max_turn": round(worst_turn[1], 4),
        "max_turn_at": round(worst_turn[0], 4),
        "over_step": sum(1 for _t, s in steps if s > chase_camera.MAX_PHASE_STEP),
        "over_turn": sum(1 for _t, s in turns if s > chase_camera.MAX_TURN_RATE),
    }


def screen_motion(track: dict[str, Any], replay: dict[str, Any], since: float,
                  stride: int = 1) -> dict[str, Any]:
    """How far a racer moves across the frame between consecutive frames.

    The camera's own step says nothing about what a viewer's eye has to do: a
    lens that moves a tenth of a unit while swinging onto a near subject can
    still throw the picture. This follows every racer that is in *both* frames
    and reports the worst single displacement, in pixels and as a share of the
    frame diagonal.
    """
    rows = _rows(track, since)[::stride]
    diagonal = math.hypot(WIDTH, HEIGHT)
    worst = (0.0, 0.0, -1)
    total, count = 0.0, 0
    previous: dict[int, tuple[float, float]] | None = None
    for row in rows:
        read = readability.cut_reads({"frames": [row]}, replay, WIDTH, HEIGHT)[0]
        here = {m: (v[0], v[1]) for m, v in read["racers"].items()}
        if previous is not None:
            for marble in set(previous) & set(here):
                moved = math.dist(previous[marble], here[marble])
                total += moved
                count += 1
                if moved > worst[0]:
                    worst = (moved, float(row[0]), marble)
        previous = here
    return {
        "max_px": round(worst[0], 2),
        "max_share": round(worst[0] / diagonal, 4),
        "max_at": round(worst[1], 4),
        "max_marble": worst[2],
        "mean_px": round(total / max(count, 1), 2),
    }


def finish_lead(track: dict[str, Any], replay: dict[str, Any], machine,
                bundle, stride: int = 2) -> dict[str, Any]:
    """How long before the winner crosses the viewer can see the finish line.

    The longest unbroken run of sampled frames **ending at the crossing** in
    which the line's own node projects inside the frame, no nearer the edge than
    `EDGE_MARGIN`, and nothing drawn stands between the lens and it. Ending at
    the crossing is the point: a shot that shows the line early, loses it, and
    finds it again has not told the viewer the finish is coming.
    """
    node, _forward, _right = v221_finish.finish_frame(machine)
    _marble, won = v221_finish.winner(replay)
    rows = [row for row in _rows(track) if float(row[0]) <= won + 1e-9][::stride]
    if not rows:
        return {"seconds": 0.0, "from": None, "frames": 0, "blocked_by": {}}
    run_from: float | None = None
    blockers: dict[str, int] = {}
    seen = 0
    for row in rows:
        camera, aim, fov = row[1:4], row[4:7], float(row[7])
        placed = presentation.project(camera, aim, fov, node, WIDTH, HEIGHT)
        inside = placed is not None and (
            EDGE_MARGIN <= placed[0] <= WIDTH - EDGE_MARGIN
            and EDGE_MARGIN <= placed[1] <= HEIGHT - EDGE_MARGIN
        )
        hit = bundle.first_hit(camera, node, shorten=0.30) if inside else None
        if hit is not None:
            blockers[hit[1]] = blockers.get(hit[1], 0) + 1
        if inside and hit is None:
            if run_from is None:
                run_from = float(row[0])
            seen += 1
        else:
            run_from = None
            seen = 0
    return {
        "seconds": round(won - run_from, 4) if run_from is not None else 0.0,
        "from": None if run_from is None else round(run_from, 4),
        "winner_crosses": round(won, 4),
        "frames": seen,
        "blocked_by": dict(sorted(blockers.items(), key=lambda kv: -kv[1])[:4]),
    }


def crossings(track: dict[str, Any], replay: dict[str, Any], machine,
              bundle) -> list[dict[str, Any]]:
    """Every racer at its own crossing instant: seen, how big, how far from the line.

    `gap_px` is the on-screen distance from the racer to the finish node at the
    moment the physics says it crossed. Small is good and zero is suspicious:
    a marble drawn on top of the line it is crossing is a marble whose crossing
    a viewer can place. Large means the shot is showing the win somewhere other
    than where it is happening.
    """
    node, _forward, _right = v221_finish.finish_frame(machine)
    crossed = v221_finish._crossings(replay)
    times = [float(frame["t"]) for frame in replay["frames"]]
    rows = _rows(track)
    radius = float(
        replay.get("units", {}).get("layout_marble_radius", 0.285)
    )
    order = sorted(crossed, key=lambda m: crossed[m])
    out: list[dict[str, Any]] = []
    for place, marble in enumerate(order, start=1):
        when = crossed[marble]
        row = min(rows, key=lambda r: abs(float(r[0]) - when))
        index = min(range(len(times)), key=lambda k: abs(times[k] - when))
        point = replay["frames"][index]["marbles"][marble]["p"]
        point = [float(v) * chase_camera.SIM_TO_LAYOUT for v in point]
        camera, aim, fov = row[1:4], row[4:7], float(row[7])
        placed = presentation.project(camera, aim, fov, point, WIDTH, HEIGHT)
        at_line = presentation.project(camera, aim, fov, node, WIDTH, HEIGHT)
        hit = bundle.first_hit(camera, point, shorten=radius)
        entry: dict[str, Any] = {
            "place": place,
            "marble": marble,
            "t": round(when, 4),
            "in_frame": False,
            "px": 0.0,
            "clear": hit is None,
            "blocker": None if hit is None else hit[1],
            "gap_px": None,
        }
        if placed is not None:
            entry["in_frame"] = (
                0.0 <= placed[0] <= WIDTH and 0.0 <= placed[1] <= HEIGHT
            )
            entry["px"] = round(
                (2.0 * radius / placed[2]) / (2.0 * math.tan(math.radians(fov) * 0.5))
                * HEIGHT, 1
            )
            entry["at"] = (round(placed[0]), round(placed[1]))
            if at_line is not None:
                entry["gap_px"] = round(math.dist(placed[:2], at_line[:2]), 1)
        out.append(entry)
    return out


def window_reads(track: dict[str, Any], replay: dict[str, Any], machine,
                 bundle, since: float, stride: int = 3) -> dict[str, Any]:
    """Scale, coverage and obstruction over the finish window, whatever cuts it is in.

    The control's finish window is one cut and a candidate's is another, so a
    per-cut report cannot be pooled between them without deciding which cuts
    count. This measures a **replay window** instead, which is the same seconds
    of physics in every candidate.
    """
    rows = _rows(track, since)[::stride]
    radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    times = [float(frame["t"]) for frame in replay["frames"]]
    in_frame: list[int] = []
    of: list[int] = []
    visible: list[int] = []
    medians: list[float] = []
    smallest: list[float] = []
    blockers: dict[str, int] = {}
    lost = 0
    for row in rows:
        read = readability.cut_reads({"frames": [row]}, replay, WIDTH, HEIGHT)[0]
        in_frame.append(read["in_frame"])
        of.append(read["of"])
        if read["of"] and read["in_frame"] < 0.75 * read["of"]:
            lost += 1
        index = min(range(len(times)), key=lambda k: abs(times[k] - float(row[0])))
        points = readability._racer_points(replay, index)
        clear = 0
        for marble in read["racers"]:
            hit = bundle.first_hit(row[1:4], points[marble], shorten=radius)
            if hit is None:
                clear += 1
            else:
                blockers[hit[1]] = blockers.get(hit[1], 0) + 1
        visible.append(clear)
        if read["diameters"]:
            medians.append(readability._median(read["diameters"]))
            smallest.append(min(read["diameters"]))
    total = sum(in_frame) or 1
    # What share of the racers still running are in frame. The mean count alone
    # cannot be compared across the run-out, where the number still running
    # falls from seven to one: two racers in frame of two left is a shot that
    # shows the finish, and two of seven is not.
    live = sum(of) or 1
    return {
        "sampled": len(rows),
        "seen_share": round(sum(in_frame) / live, 3),
        "in_frame_mean": round(sum(in_frame) / max(len(in_frame), 1), 2),
        "in_frame_min": min(in_frame) if in_frame else 0,
        "visible_mean": round(sum(visible) / max(len(visible), 1), 2),
        "visible_min": min(visible) if visible else 0,
        "hidden_share": round(1.0 - sum(visible) / total, 3),
        "px_median": round(readability._median(medians), 1) if medians else 0.0,
        "px_min": round(min(smallest), 1) if smallest else 0.0,
        "under_min_px": sum(1 for v in smallest if v < MIN_PX),
        "lost_share": round(lost / max(len(rows), 1), 3),
        "blockers": dict(sorted(blockers.items(), key=lambda kv: -kv[1])[:4]),
    }


def winner_scale(track: dict[str, Any], replay: dict[str, Any], machine,
                 before: float = 1.5, stride: int = 3) -> dict[str, Any]:
    """How big the winner is over the seconds it spends approaching the line."""
    marble, won = v221_finish.winner(replay)
    times = [float(frame["t"]) for frame in replay["frames"]]
    rows = [
        row for row in _rows(track)
        if won - before - 1e-9 <= float(row[0]) <= won + 1e-9
    ][::stride]
    sizes: list[float] = []
    off = 0
    radius = float(replay.get("units", {}).get("layout_marble_radius", 0.285))
    for row in rows:
        index = min(range(len(times)), key=lambda k: abs(times[k] - float(row[0])))
        point = [
            float(v) * chase_camera.SIM_TO_LAYOUT
            for v in replay["frames"][index]["marbles"][marble]["p"]
        ]
        placed = presentation.project(row[1:4], row[4:7], float(row[7]), point,
                                      WIDTH, HEIGHT)
        if placed is None or not (0 <= placed[0] <= WIDTH and 0 <= placed[1] <= HEIGHT):
            off += 1
            continue
        sizes.append(
            (2.0 * radius / placed[2])
            / (2.0 * math.tan(math.radians(float(row[7])) * 0.5)) * HEIGHT
        )
    return {
        "marble": marble,
        "crosses": round(won, 4),
        "sampled": len(rows),
        "px_at_crossing": round(sizes[-1], 1) if sizes else 0.0,
        "px_median": round(readability._median(sizes), 1) if sizes else 0.0,
        "px_min": round(min(sizes), 1) if sizes else 0.0,
        "off_frame": off,
    }


def joins(track: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    """Every boundary in the edit and how far the eye moves across it."""
    report = readability.continuity_report(track, replay)
    measured = [float(j["jump"]) for j in report if j.get("jump") is not None]
    return {
        "boundaries": len(report),
        "max_jump": round(max(measured or [0.0]), 4),
        "hard_cuts": sum(1 for v in measured if v > readability.MAX_CUT_JUMP),
        "joins": [
            {"from": j["from"], "to": j["to"], "jump": j["jump"],
             "drift": j["drift"], "swing": j["swing"], "travel": j["travel"],
             "shared": j["shared"], "turn": j["turn"]}
            for j in report
        ],
    }


def terrain_clear(track: dict[str, Any], machine, since: float,
                  stride: int = 2) -> dict[str, Any]:
    """The worst the lens comes to the ground and to its own sight line."""
    cfg = terrain.terrain_config(machine.runs)
    rows = _rows(track, since)[::stride]
    ground = min(
        float(row[2]) - terrain.height(float(row[1]), float(row[3]), cfg)
        for row in rows
    )
    sight = min(terrain.clearance(row[1:4], row[4:7], cfg) for row in rows)
    return {
        "min_ground": round(ground, 3),
        "min_sight": round(sight, 3),
        "ground_ok": ground >= chase_camera.GROUND_MARGIN,
        "sight_ok": sight >= chase_camera.SIGHT_MARGIN,
    }


def measure(candidate: Candidate, track: dict[str, Any], replay: dict[str, Any],
            machine, bundle, since: float) -> dict[str, Any]:
    """Every number the brief asks for, for one candidate."""
    _marble, won = v221_finish.winner(replay)
    cross = crossings(track, replay, machine, bundle)
    step = motion(track, since)
    return {
        "candidate": candidate.name,
        "note": candidate.note,
        "split": candidate.split,
        "shape": track.get("shape"),
        "park": None if candidate.park is None else candidate.park.__dict__,
        "orbit": None if candidate.orbit is None else {
            "at": candidate.orbit.at, "seconds": candidate.orbit.seconds,
            "to": candidate.orbit.to.__dict__,
        },
        "motion": step,
        "screen": screen_motion(track, replay, since, stride=1),
        "finish_lead": finish_lead(track, replay, machine, bundle),
        "window": window_reads(track, replay, machine, bundle, since),
        # **The run-out is measured separately, and it has to be.** Pooled from
        # the split, a candidate's approach and its run-out average into one
        # number, and they are asking opposite questions: the approach is about
        # the winner and the run-out is about everybody else. `window_after`
        # starts at the winner's own crossing, so it is exactly the brief's
        # "once winner crosses, the viewer should appreciate subsequent
        # finishers" with nothing of the approach mixed into it.
        "window_after": window_reads(track, replay, machine, bundle, won),
        "winner": winner_scale(track, replay, machine),
        "crossings": cross,
        "all_eight": {
            "crossed": len(cross),
            "in_frame": sum(1 for c in cross if c["in_frame"]),
            "clear": sum(1 for c in cross if c["in_frame"] and c["clear"]),
            "readable": sum(
                1 for c in cross
                if c["in_frame"] and c["clear"] and c["px"] >= MIN_PX
            ),
        },
        "joins": joins(track, replay),
        "terrain": terrain_clear(track, machine, since),
        "discontinuities": step["over_step"] + step["over_turn"] + sum(
            1 for j in readability.continuity_report(track, replay)
            if j.get("jump") is not None and float(j["jump"]) > readability.MAX_CUT_JUMP
        ),
        "findings": v221_finish.check_finish(track, replay),
    }


# --- the sweeps -------------------------------------------------------------
#
# Each one is admissible-then-ranked rather than scored: a trial is admissible
# if it keeps every crossing in frame, clear and at least `MIN_PX`, keeps the
# lens off the ground and its sight line off the terrain, and returns no
# `v221_finish.check_finish` findings. Among the admissible it is ranked by the
# thing that sweep is *for*. A single weighted score would have let a pose buy
# anticipation with the winner's size, which is the one trade the brief forbids.


def _trial(replay, machine, base, bundle, candidate: Candidate,
           since: float) -> dict[str, Any]:
    """One candidate, measured down to the handful of numbers a sweep ranks on."""
    track = v221_finish.build(base, replay, machine, candidate)
    step = motion(track, since)
    cross = crossings(track, replay, machine, bundle)
    lead = finish_lead(track, replay, machine, bundle, stride=2)
    win = winner_scale(track, replay, machine, stride=3)
    seen = window_reads(track, replay, machine, bundle, 20.2, stride=4)
    ground = terrain_clear(track, machine, since, stride=4)
    findings = v221_finish.check_finish(track, replay)
    readable = sum(
        1 for c in cross if c["in_frame"] and c["clear"] and c["px"] >= MIN_PX
    )
    return {
        "settle": track["shape"]["settle"],
        "aim_settle": track["shape"]["aim_settle"],
        "ratio": track["shape"]["ratio"],
        "aim_ratio": track["shape"]["aim_ratio"],
        "parked_at": track["shape"]["parked_at"],
        "max_step": step["max_step"],
        "max_turn": step["max_turn"],
        "lead": lead["seconds"],
        "winner_px": win["px_at_crossing"],
        "smallest_crossing_px": round(min(c["px"] for c in cross), 1),
        "readable": readable,
        "in_frame": seen["in_frame_mean"],
        "visible": seen["visible_mean"],
        "hidden_share": seen["hidden_share"],
        "min_ground": ground["min_ground"],
        "min_sight": ground["min_sight"],
        "findings": findings,
        "ok": (
            readable == len(cross)
            and ground["ground_ok"] and ground["sight_ok"]
            and not findings
        ),
    }


def _show(label: str, row: dict[str, Any]) -> None:
    flag = "ok " if row["ok"] else "   "
    aim = "tied" if row["aim_settle"] is None else f"{row['aim_settle']:.2f}"
    print(f"{flag}{label} | settle {row['settle']:5.2f} aim {aim} "
          f"step {row['max_step']:.3f} turn {row['max_turn']:.2f} "
          f"| lead {row['lead']:5.2f}s win {row['winner_px']:5.1f}px "
          f"min {row['smallest_crossing_px']:5.1f}px rd {row['readable']}/8 "
          f"| inF {row['in_frame']:.2f} hid {row['hidden_share']:.3f} "
          f"gnd {row['min_ground']:5.1f}"
          + (f" | {row['findings'][0]}" if row["findings"] else ""))


def sweep(seed: int, coarse: bool = False) -> dict[str, Any]:
    """The park pose: where the camera ends up standing, over bearing, radius, height.

    Ranked by the winner's own size at the crossing, then by how many racers are
    in frame - which is the trade this sweep exists to price. Radius buys
    company and costs scale, at about 2.4 px a layout unit here.
    """
    replay, machine, base, bundle = world(seed)
    if coarse:
        poses = [(180.0, radius, height)
                 for radius in (22.0, 26.0, 30.0) for height in (16.0, 20.0)]
    else:
        poses = [
            (bearing, radius, height)
            for bearing in (172.0, 176.0, 180.0, 184.0, 188.0)
            for radius in (20.0, 22.0, 24.0, 26.0, 28.0, 32.0)
            for height in (14.0, 16.0, 18.0, 20.0, 24.0)
        ]
    rows: list[dict[str, Any]] = []
    for bearing, radius, height in poses:
        pose = Pose(bearing=bearing, radius=radius, height=height,
                    aim_ahead=PARK["pose"].aim_ahead,
                    aim_lift=PARK["pose"].aim_lift, fov=PARK["pose"].fov)
        trial = Candidate(name="sweep", split=PARK["split"], park=pose,
                          ratio=PARK["ratio"], aim_settle=PARK["aim_settle"])
        row = _trial(replay, machine, base, bundle, trial, PARK["split"])
        row.update(bearing=bearing, radius=radius, height=height)
        rows.append(row)
        _show(f"b{bearing:5.0f} r{radius:4.0f} h{height:4.0f}", row)
    good = sorted((r for r in rows if r["ok"]),
                  key=lambda r: (-r["winner_px"], -r["in_frame"]))
    out = {"seed": seed, "trials": rows, "admissible": len(good), "best": good[:8]}
    _dump(os.path.join(DOCS_DIR, "park_sweep.json"), out)
    print(f"\n{len(good)} of {len(rows)} admissible")
    return out


def sweep_split(seed: int) -> dict[str, Any]:
    """Where the chase stops following the pack, how hard it brakes, and when it looks.

    Ranked by anticipation, because that is what the split and the aim's own
    settle buy. The surprise this sweep produced is in the module docstring: a
    *later* split can leave more room than an earlier one, because the room is
    bought with the chase's entry speed rather than with wall-clock seconds.
    """
    replay, machine, base, bundle = world(seed)
    rows: list[dict[str, Any]] = []
    for split in (18.600, 18.750, 18.900, 19.050, 19.200, 19.400):
        for target in (1.6, 2.0, 2.6):
            for aim in (None, 1.6, 1.2, 0.8):
                trial = Candidate(name="sweep", split=split, park=PARK["pose"],
                                  ratio=target, aim_settle=aim)
                try:
                    row = _trial(replay, machine, base, bundle, trial, split)
                except ValueError as error:
                    print(f"   split {split} ratio {target}: {error}")
                    continue
                row.update(split=split, target_ratio=target,
                           asked_aim=aim, aim_settle=row["aim_settle"])
                rows.append(row)
                _show(f"split {split:.3f} r{target:4.1f}", row)
    good = sorted((r for r in rows if r["ok"]), key=lambda r: -r["lead"])
    out = {"seed": seed, "trials": rows, "admissible": len(good), "best": good[:8]}
    _dump(os.path.join(DOCS_DIR, "split_sweep.json"), out)
    print(f"\n{len(good)} of {len(rows)} admissible; best by anticipation:")
    for row in good[:6]:
        print(f"  split {row['split']:.3f} ratio {row['target_ratio']:.1f} "
              f"aim {row['aim_settle']:.2f} -> lead {row['lead']:.2f}s, "
              f"turn {row['max_turn']:.2f}, winner {row['winner_px']:.1f}px")
    return out


def sweep_orbit(seed: int) -> dict[str, Any]:
    """What the camera may do once the winner is past: three targets, three timings.

    The falsification is here. A straight pull-back - same bearing, further
    back - is the obvious way to recover the stragglers a rear park cannot hold,
    and it does: it is the only target that gets more than 1.3 racers into an
    average frame. It also takes every crossing after the third under `MIN_PX`,
    because the thing it pulls back from is the line. A finish that shows more
    of the field and none of the finishing is not a finish.
    """
    replay, machine, base, bundle = world(seed)
    lens = v221_finish.lens_pose(base, machine)
    targets = {
        "v19": lens,
        "quarter": Pose(bearing=128.0, radius=22.0, height=16.0, aim_lift=1.0),
        "pull": PULL["pose"],
    }
    rows: list[dict[str, Any]] = []
    for name, target in targets.items():
        for at in (21.050, 21.150, 21.400):
            for seconds, ease in ((2.4, 0.25), (2.8, 0.25), (3.2, 0.25), (2.8, 0.40)):
                if at + seconds > v221_finish.FINISH_END - 0.02:
                    continue
                trial = Candidate(
                    name="sweep", split=PARK["split"], park=PARK["pose"],
                    ratio=PARK["ratio"], aim_settle=PARK["aim_settle"],
                    orbit=Orbit(at=at, seconds=seconds, to=target, ease=ease),
                )
                row = _trial(replay, machine, base, bundle, trial, PARK["split"])
                swing = abs(
                    v221_finish._bearing_path(PARK["pose"].bearing, target.bearing)
                    - PARK["pose"].bearing
                )
                row.update(target=name, at=at, seconds=seconds, ease=ease,
                           swing=round(swing, 1))
                rows.append(row)
                _show(f"{name:>8} at {at:.2f} {seconds:.1f}s ease {ease:.2f}", row)
    good = sorted((r for r in rows if r["ok"]),
                  key=lambda r: (-r["in_frame"], r["max_turn"]))
    out = {"seed": seed, "trials": rows, "admissible": len(good), "best": good[:8]}
    _dump(os.path.join(DOCS_DIR, "orbit_sweep.json"), out)
    print(f"\n{len(good)} of {len(rows)} admissible")
    return out


# --- stages -----------------------------------------------------------------


def stage_solve(seed: int) -> dict[str, Any]:
    replay, machine, base, _bundle = world(seed)
    _marble, won = v221_finish.winner(replay)
    last = max(v221_finish._crossings(replay).values())
    since = max(0.0, last - CLIP_SECONDS)
    out: dict[str, Any] = {"clip_from": round(since, 4), "tracks": {}}
    for candidate in candidates(base, machine):
        track = v221_finish.build(base, replay, machine, candidate)
        path = os.path.join(WORK_DIR, f"track_{candidate.name}_{seed}.json")
        _dump(path, track)
        clip = v221_finish.finish_clip(track, since)
        clip_path = os.path.join(WORK_DIR, f"clip_{candidate.name}_{seed}.json")
        _dump(clip_path, clip)
        out["tracks"][candidate.name] = {
            "track": path, "clip": clip_path,
            "duration": clip["duration"],
            "cuts": [c["name"] for c in clip["cuts"]],
        }
        print(f"{candidate.name:8s}  clip {clip['duration']:.3f} s  "
              f"cuts {[c['name'] for c in clip['cuts']]}")
    print(f"winner crosses at replay {won:.4f}; clip opens at {since:.4f}")
    return out


def stage_measure(seed: int) -> dict[str, Any]:
    replay, machine, base, bundle = world(seed)
    since = PARK["split"]
    out: dict[str, Any] = {"seed": seed, "since": since, "candidates": {}}
    for candidate in candidates(base, machine):
        track = v221_finish.build(base, replay, machine, candidate)
        out["candidates"][candidate.name] = measure(
            candidate, track, replay, machine, bundle, since
        )
    _dump(os.path.join(DOCS_DIR, "metrics.json"), out)
    _print(out)
    return out


def _print(data: dict[str, Any]) -> None:
    print(f"\nmeasured from replay {data['since']:.3f}\n")
    head = f"{'':22s}" + "".join(f"{name:>14s}" for name in data["candidates"])
    print(head)
    lines = (
        ("max camera step", lambda d: f"{d['motion']['max_step']:.3f}"),
        ("max turn deg/frame", lambda d: f"{d['motion']['max_turn']:.3f}"),
        ("max screen move px", lambda d: f"{d['screen']['max_px']:.0f}"),
        ("finish lead s", lambda d: f"{d['finish_lead']['seconds']:.2f}"),
        ("winner px @ cross", lambda d: f"{d['winner']['px_at_crossing']:.1f}"),
        ("winner px median", lambda d: f"{d['winner']['px_median']:.1f}"),
        ("racers in frame", lambda d: f"{d['window']['in_frame_mean']:.2f}"),
        ("racers visible", lambda d: f"{d['window']['visible_mean']:.2f}"),
        ("hidden share", lambda d: f"{d['window']['hidden_share']:.3f}"),
        ("median racer px", lambda d: f"{d['window']['px_median']:.1f}"),
        ("run-out in frame", lambda d: f"{d['window_after']['in_frame_mean']:.2f}"),
        ("run-out visible", lambda d: f"{d['window_after']['visible_mean']:.2f}"),
        ("run-out share seen",
         lambda d: f"{d['window_after']['seen_share']:.2f}"),
        ("run-out racer px", lambda d: f"{d['window_after']['px_median']:.1f}"),
        ("crossings in frame", lambda d: f"{d['all_eight']['in_frame']}/8"),
        ("crossings readable", lambda d: f"{d['all_eight']['readable']}/8"),
        ("max cut jump", lambda d: f"{d['joins']['max_jump']:.3f}"),
        ("hard cuts", lambda d: f"{d['joins']['hard_cuts']}"),
        ("discontinuities", lambda d: f"{d['discontinuities']}"),
        ("min ground", lambda d: f"{d['terrain']['min_ground']:.2f}"),
        ("min sight", lambda d: f"{d['terrain']['min_sight']:.2f}"),
        ("findings", lambda d: f"{len(d['findings'])}"),
    )
    for label, pick in lines:
        row = f"{label:22s}" + "".join(
            f"{pick(d):>14s}" for d in data["candidates"].values()
        )
        print(row)
    for name, entry in data["candidates"].items():
        print(f"\n{name}: crossings")
        for c in entry["crossings"]:
            mark = "ok" if c["in_frame"] and c["clear"] and c["px"] >= MIN_PX else "--"
            print(f"  {mark} {c['place']}. m{c['marble']} t={c['t']:.3f} "
                  f"{c['px']:5.1f}px gap {c['gap_px']} "
                  f"{'' if c['clear'] else 'blocked by ' + str(c['blocker'])}")


# --- rendering --------------------------------------------------------------


def find_godot(explicit: str | None) -> str:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        found = shutil.which(explicit)
        if found:
            return found
        raise V221Error(f"--godot does not name an executable: {explicit}")
    for variable in ("GODOT_BIN", "GODOT4_BIN"):
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
    for name in ("godot", "godot4"):
        found = shutil.which(name)
        if found:
            return found
    raise V221Error(
        "cannot find Godot 4. Pass --godot PATH, set $GODOT_BIN, or put it on PATH."
    )


def _run_godot(godot: str, extra: Sequence[str], label: str) -> float:
    started = time.perf_counter()
    done = subprocess.run(
        [godot, "--path", GODOT_PROJECT, RENDER_SCENE, "--", *extra],
        cwd=PROJECT_ROOT, stderr=subprocess.PIPE, text=True,
        encoding="utf-8", errors="replace",
    )
    elapsed = time.perf_counter() - started
    tail = "\n".join((done.stderr or "").splitlines()[-20:])
    if done.returncode != 0:
        raise V221Error(f"{label}: Godot exited {done.returncode}\n{tail}")
    for line in (done.stderr or "").splitlines():
        if "SCRIPT ERROR" in line or "Parse Error" in line:
            raise V221Error(f"{label}: Godot reported an error: {line.strip()}")
    return elapsed


def _encode(frames_dir: str, names: Sequence[str], video: str) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise V221Error("ffmpeg is not on PATH; frames are rendered but not encoded")
    first = int(names[0].split("_")[1].split(".")[0])
    os.makedirs(os.path.dirname(os.path.abspath(video)), exist_ok=True)
    done = subprocess.run(
        [ffmpeg, "-y", "-framerate", str(FPS), "-start_number", str(first),
         "-i", os.path.join(frames_dir, "frame_%06d.png"),
         "-frames:v", str(len(names)), "-an",
         "-c:v", "libx264", "-preset", VIDEO_PRESET, "-crf", str(VIDEO_CRF),
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", video],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-15:])
        raise V221Error(f"ffmpeg exited {done.returncode}\n{tail}")
    print(f"  video: {video}  {os.path.getsize(video) / (1024 * 1024):.1f} MiB")


def stage_render(godot: str, seed: int) -> dict[str, Any]:
    replay, machine, base, _bundle = world(seed)
    contract = os.path.join(OUT_DIR, f"start_contract_{seed}.json")
    out: dict[str, Any] = {}
    for candidate in candidates(base, machine):
        clip_path = os.path.join(WORK_DIR, f"clip_{candidate.name}_{seed}.json")
        if not os.path.isfile(clip_path):
            stage_solve(seed)
        clip = _load(clip_path)
        frames_dir = os.path.join(WORK_DIR, f"frames_{candidate.name}")
        if os.path.isdir(frames_dir):
            shutil.rmtree(frames_dir)
        os.makedirs(frames_dir, exist_ok=True)
        flags = [
            f"--out-dir={os.path.abspath(frames_dir)}",
            f"--replay={os.path.abspath(os.path.join(OUT_DIR, f'race_{seed}.json'))}",
            f"--cameras={os.path.abspath(clip_path)}",
            "--clip=1", f"--end={float(clip['duration']):.6f}", f"--fps={FPS}",
            f"--width={WIDTH}", f"--height={HEIGHT}",
            "--layout=b", "--detail=hero", "--routes=both",
        ]
        if os.path.isfile(contract):
            flags.append(f"--start-contract={os.path.abspath(contract)}")
        elapsed = _run_godot(godot, flags, candidate.name)
        names = sorted(f for f in os.listdir(frames_dir) if f.endswith(".png"))
        if not names:
            raise V221Error(f"{candidate.name}: no frames were written")
        print(f"{candidate.name}: {len(names)} frames in {elapsed:.1f} s")
        video = os.path.join(WORK_DIR, f"finish_{candidate.name}.mp4")
        _encode(frames_dir, names, video)
        out[candidate.name] = {"frames": len(names), "video": video}
    return out


# --- the phone sheet --------------------------------------------------------


def stage_sheet(seed: int) -> str:
    """A phone-size contact sheet: the same six instants, candidate per column.

    The instants are the crossings the brief cares about, taken in **output**
    time through each candidate's own clip clock - the clip re-times the edit,
    so the frame number for a given replay second is not the same in all three.
    """
    from PIL import Image, ImageDraw

    replay, machine, base, _bundle = world(seed)
    crossed = v221_finish._crossings(replay)
    order = sorted(crossed, key=lambda m: crossed[m])
    marks = [
        ("approach", crossed[order[0]] - 1.20),
        ("winner", crossed[order[0]]),
        ("2nd", crossed[order[1]]),
        ("3rd", crossed[order[2]]),
        ("5th", crossed[order[4]]),
        ("8th", crossed[order[7]]),
    ]
    picked = candidates(base, machine)
    gap, label_h, top = 8, 18, 24
    width = len(picked) * (PHONE[0] + gap) + gap
    height = top + len(marks) * (PHONE[1] + label_h + gap)
    sheet = Image.new("RGB", (width, height), (16, 16, 18))
    draw = ImageDraw.Draw(sheet)
    for column, candidate in enumerate(picked):
        x = gap + column * (PHONE[0] + gap)
        draw.text((x + 4, 6), candidate.name, fill=(230, 230, 230))
        clip = _load(os.path.join(WORK_DIR, f"clip_{candidate.name}_{seed}.json"))
        frames_dir = os.path.join(WORK_DIR, f"frames_{candidate.name}")
        for row, (name, when) in enumerate(marks):
            y = top + row * (PHONE[1] + label_h + gap)
            index = _frame_for(clip, when)
            path = os.path.join(frames_dir, f"frame_{index:06d}.png")
            draw.text((x + 4, y), f"{name} {when:.2f}s", fill=(190, 190, 190))
            if not os.path.isfile(path):
                draw.rectangle([x, y + label_h, x + PHONE[0], y + label_h + PHONE[1]],
                               outline=(90, 60, 60))
                continue
            with Image.open(path) as image:
                sheet.paste(image.convert("RGB").resize(PHONE, Image.LANCZOS),
                            (x, y + label_h))
    os.makedirs(DOCS_DIR, exist_ok=True)
    out = os.path.join(DOCS_DIR, "phone_sheet.png")
    sheet.save(out)
    print(f"sheet: {out}  {sheet.size[0]}x{sheet.size[1]}")
    return out


def _frame_for(clip: dict[str, Any], replay_at: float) -> int:
    """Which rendered frame of a clip holds one replay second."""
    for segment in clip["edit"]:
        low, high = float(segment["replay"][0]), float(segment["replay"][1])
        if low - 1e-6 <= replay_at <= high + 1e-6:
            out = float(segment["out"][0]) + (replay_at - low)
            return int(round(out * FPS))
    last = clip["edit"][-1]
    return int(round(float(last["out"][1]) * FPS))


# --- entry point ------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--stage", default="measure",
                        choices=("solve", "sweep", "sweep-split", "sweep-orbit",
                                 "measure", "render", "sheet", "all"))
    parser.add_argument("--godot", default=None)
    parser.add_argument("--coarse", action="store_true")
    args = parser.parse_args(argv)

    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    try:
        if args.stage == "sweep":
            sweep(args.seed, coarse=args.coarse)
        elif args.stage == "sweep-split":
            sweep_split(args.seed)
        elif args.stage == "sweep-orbit":
            sweep_orbit(args.seed)
        elif args.stage == "solve":
            stage_solve(args.seed)
        elif args.stage == "measure":
            stage_measure(args.seed)
        elif args.stage == "render":
            stage_render(find_godot(args.godot), args.seed)
        elif args.stage == "sheet":
            stage_sheet(args.seed)
        else:
            stage_solve(args.seed)
            stage_measure(args.seed)
            stage_render(find_godot(args.godot), args.seed)
            stage_sheet(args.seed)
    except V221Error as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
