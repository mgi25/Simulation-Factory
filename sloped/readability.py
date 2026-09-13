"""Whether a viewer can follow one marble, measured rather than looked at.

`cameras.frame_report` answers "can I see the marbles" with two numbers at one
instant per cut: how many racers are inside the frustum, and how wide the
*nearest* one is. Both were enough to catch the failures they were written for
- a lens aimed ten units off the field, a shot holding one racer of eight - and
neither is enough for the question V21 is asked:

    *I picked a marble at the line. Can I still find it at eight seconds?*

That question has four parts, and this module measures each of them over
**every frame of every cut** rather than at a midpoint:

* **scale** - how large a racer is on a 1080x1920 phone frame. Not the nearest
  racer, which is a single lucky sample: the *median* of the racers in shot,
  and the tenth percentile under it, because a shot whose median is comfortable
  and whose tail is eighteen pixels has lost half the field into scenery.
* **coverage** - how many of the eight are in frame, and for how long the
  count stays low. A cut that holds three racers for two seconds has lost five
  viewers' marbles for two seconds.
* **placement** - how far the pack's own centroid sits from the middle of the
  frame, in half-heights, and how much of the frame its bounding box fills.
  Empty track is the readability fault this pass exists to remove, and pack
  occupancy is the number that sees it.
* **continuity** - across a cut, where the pack was on the outgoing frame
  against where it is on the incoming one. A viewer reacquires a marble by
  looking where it was; a cut that moves the pack across the diagonal makes
  them search.

## Why a screen measure and not a layout one

Every earlier camera argument in this repo is in layout units - extents,
bearings, clearances - and layout units cannot say whether a marble is
legible, because that depends on the lens as well as on the distance. A racer
is about `2 * MARBLE_RADIUS * height / extent` pixels across at the aim plane,
so `extent` is the one lens number that translates directly into readability:
1094 px-units divided by the extent. That relation is the whole of section A of
the V21 brief, and it is measured here rather than asserted.

## What this cannot see

Occlusion. A racer behind its own guard rail projects exactly as it does in the
open. `sloped.sightlines` is the module that answers that, and V21 runs it on
every cut rather than only on the finish.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from sloped import layout
from sloped.presentation import WIDTH, HEIGHT, project
from sloped.scale import SIM_TO_LAYOUT

__all__ = [
    "MIN_MEDIAN_PX",
    "MIN_TAIL_PX",
    "MIN_COVERAGE",
    "MAX_OFF_CENTRE",
    "MAX_CUT_JUMP",
    "MAX_TURN",
    "travel_direction",
    "cut_reads",
    "readability_report",
    "continuity_report",
    "visibility_report",
    "check_readability",
]


# What a racer has to be for a viewer to keep hold of it, in pixels of the
# delivered 1080x1920 frame.
#
# **Both are measured off the shot this pass is told to treat as evidence.**
# The V19 finish lens is the strongest section of V20 and it runs at an extent
# of 16, which puts a racer at the aim plane at 2 * 0.285 * 1920 / 16 = 68 px;
# over its own frames its median racer is 63 px and its tenth percentile 46. So
# 48 and 34 are three quarters of each - the floor a race shot has to clear to
# be in the same class as the finish, rather than a copy of it.
MIN_MEDIAN_PX = 48.0
MIN_TAIL_PX = 34.0

# How much of the field a race shot has to hold, as a fraction of the racers
# **still in the race**. Three quarters rather than all of it: a two-lobe field
# at the fork spans thirty layout units, and framing all of it is what made the
# racers dots in the first place. The number that matters to a viewer is not
# the fraction but how long it stays low, which is why `lost_seconds` is
# reported beside it.
MIN_COVERAGE = 0.75
MAX_LOST_SECONDS = 0.50

# How far the pack's centroid may sit from the middle of the frame, in units of
# half the frame height. 1.0 is the top or bottom edge; 0.55 keeps the field
# inside the middle two thirds, which is where a phone viewer's eye rests and
# where a marble is not about to leave the picture.
MAX_OFF_CENTRE = 0.55

# How far the pack may move across the frame at a cut, as a fraction of the
# frame diagonal. A third of the diagonal is about 750 px on this frame - a
# pack that was low-left arriving high-centre, which still reads as a new angle
# on the same race. Past that a viewer is searching.
MAX_CUT_JUMP = 0.34

# How far the pack's screen direction of travel may turn across a cut, as a
# cosine. **This is the "no sudden side flips" of the brief, and it is not the
# same question as where the pack lands.**
#
# A cut can put the field in exactly the same corner of the frame and still
# reverse which way it is going, and that is the one thing an audience cannot
# absorb: the eye tracks motion. Measured on this course the difference is
# stark, because the world direction of the pack is *identical* either side of
# every cut in the edit - the cuts are at the same instant - so any turn the
# screen shows is the camera having crossed the line, never the racers turning.
#
# -0.5 is a hundred and twenty degrees. Under that is a change of angle, which
# reads; past it the pack is going backwards.
MAX_TURN = -0.5


def _racer_points(replay: dict[str, Any], index: int) -> dict[int, tuple[float, float, float]]:
    scale = float(replay.get("units", {}).get("render_scale", SIM_TO_LAYOUT))
    return {
        int(marble["id"]): tuple(float(marble["p"][axis]) * scale for axis in range(3))
        for marble in replay["frames"][index]["marbles"]
    }


def crossings(replay: dict[str, Any]) -> dict[int, float]:
    """When each marble crossed the line, for the ones that did.

    **A racer's state never leaves `running`.** The replay's `s` field is
    `queued` on the grid and `running` from the gate to the end of the record,
    crossed or not, so it cannot say who is still in the race - and a coverage
    measure that counts finishers is a measure that marks the finish lens down
    for the marbles it has already delivered. The `finish_line` events are what
    knows, so they are what is used.
    """
    return {
        int(event["id"]): float(event["t"])
        for event in replay.get("events", ())
        if event["kind"] == "finish_line"
    }


def routes(replay: dict[str, Any]) -> dict[int, str]:
    """Which route each marble took, from the replay's own `route` events."""
    return {
        int(event["id"]): str(event["route"])
        for event in replay.get("events", ())
        if event["kind"] == "route"
    }


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return 0.5 * (ordered[middle - 1] + ordered[middle])


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    at = fraction * (len(ordered) - 1)
    low = int(math.floor(at))
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (at - low)


def cut_reads(
    cut: dict[str, Any],
    replay: dict[str, Any],
    width: int = WIDTH,
    height: int = HEIGHT,
    stride: int = 1,
) -> list[dict[str, Any]]:
    """One measurement per sampled frame of one cut.

    A racer's diameter in pixels is `2 * radius / depth` over the vertical
    half-angle, times the frame height - the same expression
    `cameras.frame_report` uses for its nearest racer, applied to all of them.
    `presentation.project` supplies the pose arithmetic, which is the one place
    in this repo where screen right is written the way Godot means it.
    """
    radius = float(
        replay.get("units", {}).get("layout_marble_radius", layout.MARBLE_RADIUS)
    )
    times = [float(frame["t"]) for frame in replay["frames"]]
    crossed = crossings(replay)
    rows = cut.get("frames") or []
    out: list[dict[str, Any]] = []
    for row in rows[::stride]:
        when = float(row[0])
        camera = (row[1], row[2], row[3])
        aim = (row[4], row[5], row[6])
        fov = float(row[7])
        half_up = math.tan(math.radians(fov) * 0.5)
        index = min(range(len(times)), key=lambda k: abs(times[k] - when))
        points = _racer_points(replay, index)
        # Only racers still in the race. One that has crossed is a marble whose
        # viewer already has their answer, and counting it either way flatters
        # or punishes a shot for something that is not racing.
        playing = [
            marble for marble in points if crossed.get(marble, math.inf) > when
        ]
        seen: list[dict[str, float]] = []
        for marble in playing:
            placed = project(camera, aim, fov, points[marble], width, height)
            if placed is None:
                continue
            x, y, depth = placed
            if not (0.0 <= x <= width and 0.0 <= y <= height):
                continue
            seen.append(
                {
                    "id": float(marble),
                    "x": x,
                    "y": y,
                    "px": (2.0 * radius / depth) / (2.0 * half_up) * height,
                }
            )
        record: dict[str, Any] = {
            "t": round(when, 4),
            "in_frame": len(seen),
            "of": len(playing),
            "racers": {int(entry["id"]): (entry["x"], entry["y"], entry["px"]) for entry in seen},
            "diameters": [entry["px"] for entry in seen],
        }
        if seen:
            xs = [entry["x"] for entry in seen]
            ys = [entry["y"] for entry in seen]
            record["bbox"] = (min(xs), min(ys), max(xs), max(ys))
            record["centroid"] = (sum(xs) / len(xs), sum(ys) / len(ys))
            # Bounding box area as a fraction of the frame. A pack of one is a
            # box of zero area, so this is read together with `in_frame`.
            record["occupancy"] = (
                (max(xs) - min(xs)) * (max(ys) - min(ys)) / float(width * height)
            )
            # Distance from the frame's middle in half-heights, which makes the
            # vertical edge exactly 1.0 on a portrait frame and the horizontal
            # edge 0.5625 - the axis that is actually the tight one.
            record["off_centre"] = math.hypot(
                (record["centroid"][0] - 0.5 * width) / (0.5 * height),
                (record["centroid"][1] - 0.5 * height) / (0.5 * height),
            )
        else:
            record["bbox"] = None
            record["centroid"] = None
            record["occupancy"] = 0.0
            record["off_centre"] = 1.0
        out.append(record)
    return out



def travel_direction(
    row: Sequence[float],
    replay: dict[str, Any],
    ahead: float = 0.25,
    width: int = WIDTH,
    height: int = HEIGHT,
) -> tuple[float, float] | None:
    """Which way the pack would move on screen from one camera row.

    The pack's own centroid a quarter-second later, projected through the same
    lens, minus where it is now - so this is the *racers'* direction seen
    through this camera, not the centroid's apparent drift, which also moves
    when a marble enters or leaves the shot.
    """
    times = [float(frame["t"]) for frame in replay["frames"]]
    when = float(row[0])
    crossed = crossings(replay)
    here_index = min(range(len(times)), key=lambda k: abs(times[k] - when))
    there_index = min(range(len(times)), key=lambda k: abs(times[k] - (when + ahead)))
    here = _racer_points(replay, here_index)
    there = _racer_points(replay, there_index)
    live = [
        marble for marble in here
        if marble in there and crossed.get(marble, math.inf) > when + ahead
    ] or [marble for marble in here if marble in there]
    if not live:
        return None
    camera, aim, fov = tuple(row[1:4]), tuple(row[4:7]), float(row[7])
    before = [sum(here[m][axis] for m in live) / len(live) for axis in range(3)]
    after = [sum(there[m][axis] for m in live) / len(live) for axis in range(3)]
    one = project(camera, aim, fov, before, width, height)
    two = project(camera, aim, fov, after, width, height)
    if one is None or two is None:
        return None
    dx, dy = two[0] - one[0], two[1] - one[1]
    size = math.hypot(dx, dy)
    if size < 1e-6:
        return None
    return (dx / size, dy / size)


def readability_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    width: int = WIDTH,
    height: int = HEIGHT,
    stride: int = 1,
) -> list[dict[str, Any]]:
    """Per cut, over all its frames: scale, coverage, placement, motion."""
    fps = max(float(track.get("fps", 60.0)), 1.0)
    report: list[dict[str, Any]] = []
    for cut in track["cuts"]:
        reads = cut_reads(cut, replay, width, height, stride)
        if not reads:
            continue
        pooled = [px for read in reads for px in read["diameters"]]
        per_frame_median = [
            _median(read["diameters"]) for read in reads if read["diameters"]
        ]
        counts = [read["in_frame"] for read in reads]
        shares = [
            read["in_frame"] / read["of"] if read["of"] else 1.0 for read in reads
        ]

        # The longest unbroken spell below `MIN_COVERAGE`, in seconds. A share
        # that dips for three frames is a marble clipping the edge; one that
        # sits low for a second is a viewer who has lost their marble.
        step = stride / fps
        run = 0
        longest = 0
        for share in shares:
            if share >= MIN_COVERAGE:
                run = 0
                continue
            run += 1
            longest = max(longest, run)

        entries = cut["frames"]
        motion = 0.0
        for a, b in zip(entries, entries[1:]):
            motion = max(motion, math.dist(a[1:4], b[1:4]))

        report.append(
            {
                "cut": cut["name"],
                "from": cut["from"],
                "to": cut["to"],
                "seconds": round(cut["to"] - cut["from"], 3),
                "extent": cut.get("extent"),
                "frames": len(reads),
                "in_frame_mean": round(sum(counts) / len(counts), 2),
                "in_frame_min": min(counts),
                "coverage": round(sum(shares) / len(shares), 3),
                "of": max(read["of"] for read in reads),
                "in_play": round(sum(read["of"] for read in reads) / len(reads), 2),
                "lost_seconds": round(longest * step, 3),
                "px_median": round(_median(per_frame_median), 1),
                "px_tail": round(_percentile(pooled, 0.10), 1),
                "px_max": round(max(pooled) if pooled else 0.0, 1),
                "occupancy": round(_median([read["occupancy"] for read in reads]), 4),
                "off_centre": round(_median([read["off_centre"] for read in reads]), 3),
                "camera_step": round(motion, 4),
            }
        )
    return report


def continuity_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    width: int = WIDTH,
    height: int = HEIGHT,
) -> list[dict[str, Any]]:
    """At every cut: where the pack was, where it lands, and how far the eye moves.

    Measured across the **edit's** order, which is what a viewer sees, and
    between the last frame of the outgoing shot and the first of the incoming
    one - not between their midpoints, because a cut is an instant and the eye
    only ever compares those two pictures.

    Three numbers per boundary:

    * `jump` - how far the pack's centroid moves across the frame, as a
      fraction of the frame diagonal. This is the continuity the brief asks
      for: a marble reacquired where it was left.
    * `swing` - how many degrees the view direction turns. A cut that keeps the
      pack in place while reversing the view is a screen-direction flip, and
      the centroid alone would call it continuous.
    * `travel` - how far the lens itself moves, in layout units, which is what
      says whether the new angle is a step along the course or a teleport.
    """
    cuts = track["cuts"]
    out: list[dict[str, Any]] = []
    for before, after in zip(cuts, cuts[1:]):
        rows_before = before.get("frames") or []
        rows_after = after.get("frames") or []
        if not rows_before or not rows_after:
            continue
        last = rows_before[-1]
        first = rows_after[0]
        left = cut_reads({"frames": [last]}, replay, width, height)[0]
        right = cut_reads({"frames": [first]}, replay, width, height)[0]

        # **The jump is measured over the racers in both pictures, not over
        # each picture's own centroid.** A cut where one marble is left in the
        # outgoing frame and eight arrive in the incoming one compares a single
        # racer against a whole field, and the difference between those two
        # centroids is a fact about who is in shot rather than about where the
        # eye has to go. The viewer's question is about *their* marble, and the
        # only marbles that can answer it are the ones visible on both sides.
        shared = sorted(set(left["racers"]) & set(right["racers"]))
        jump = None
        drift = None
        if shared:
            diagonal = math.hypot(width, height)
            before_mid = (
                sum(left["racers"][m][0] for m in shared) / len(shared),
                sum(left["racers"][m][1] for m in shared) / len(shared),
            )
            after_mid = (
                sum(right["racers"][m][0] for m in shared) / len(shared),
                sum(right["racers"][m][1] for m in shared) / len(shared),
            )
            jump = math.dist(before_mid, after_mid) / diagonal
            # The worst single marble's move, which is what a viewer following
            # one racer actually experiences.
            drift = max(
                math.dist(left["racers"][m][:2], right["racers"][m][:2]) / diagonal
                for m in shared
            )

        def direction(row: Sequence[float]) -> tuple[float, float, float]:
            forward = [row[4 + axis] - row[1 + axis] for axis in range(3)]
            length = math.sqrt(sum(value * value for value in forward)) or 1.0
            return tuple(value / length for value in forward)

        one, two = direction(last), direction(first)
        dot = max(-1.0, min(1.0, sum(one[axis] * two[axis] for axis in range(3))))
        # Which way the racers are going on screen, either side of the cut.
        going = travel_direction(last, replay, width=width, height=height)
        landing = travel_direction(first, replay, width=width, height=height)
        turn = None
        if going is not None and landing is not None:
            turn = going[0] * landing[0] + going[1] * landing[1]
        out.append(
            {
                "from": before["name"],
                "to": after["name"],
                "jump": None if jump is None else round(jump, 3),
                "drift": None if drift is None else round(drift, 3),
                "turn": None if turn is None else round(turn, 3),
                "shared": len(shared),
                "swing": round(math.degrees(math.acos(dot)), 1),
                "travel": round(math.dist(last[1:4], first[1:4]), 2),
                "left": None if left["centroid"] is None else (
                    round(left["centroid"][0]), round(left["centroid"][1])
                ),
                "landed": None if right["centroid"] is None else (
                    round(right["centroid"][0]), round(right["centroid"][1])
                ),
                "in_frame": (left["in_frame"], right["in_frame"]),
            }
        )
    return out


def visibility_report(
    track: dict[str, Any],
    replay: dict[str, Any],
    machine,
    bundle=None,
    width: int = WIDTH,
    height: int = HEIGHT,
    stride: int = 6,
) -> list[dict[str, Any]]:
    """Per cut: of the racers in frame, how many the course itself hides.

    `cut_reads` counts a racer inside the frustum whether or not there is a
    guard rail in front of it, and says so. This walks the same racers through
    `sloped.sightlines` - the drawn course as labelled triangles, rails, piers,
    gantries and all - and reports how many are actually on screen.

    It is the instrument for the brief's "avoid rails/supports hiding racers",
    and it is what decides a bearing: the file's own rule is that a camera
    looking *across* a leg has the channel's outer acrylic guard between it and
    a marble sitting 1.4 diameters below the guard's top edge, which is a claim
    about visibility that the frustum count cannot check and this can.

    `stride` is in track rows, so the default of six is a tenth of a second.
    A ray per racer per sampled frame, which is why it is not on by default in
    `check_readability`.
    """
    from sloped import sightlines, terrain

    if bundle is None:
        cfg = terrain.terrain_config(machine.runs)
        bundle = sightlines.Bundle(
            sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
        )
    radius = float(
        replay.get("units", {}).get("layout_marble_radius", layout.MARBLE_RADIUS)
    )
    times = [float(frame["t"]) for frame in replay["frames"]]
    report: list[dict[str, Any]] = []
    for cut in track["cuts"]:
        rows = cut.get("frames") or []
        if not rows:
            continue
        reads = cut_reads(cut, replay, width, height, stride)
        seen_counts: list[int] = []
        frame_counts: list[int] = []
        blockers: dict[str, int] = {}
        # How often a viewer can see a racer on **each** route at the same
        # instant. This is what "the viewer can perceive racers arriving from
        # both routes" means as a number, and neither the frustum count nor the
        # median diameter can express it: a shot holding six racers that are
        # all blue tells nobody there is a second route.
        both = 0
        route_of = routes(replay)
        live = {route for route in route_of.values()}
        for read, row in zip(reads, rows[::stride]):
            camera = (row[1], row[2], row[3])
            index = min(range(len(times)), key=lambda k: abs(times[k] - read["t"]))
            points = _racer_points(replay, index)
            clear = 0
            showing: set[str] = set()
            for marble in read["racers"]:
                hit = bundle.first_hit(camera, points[marble], shorten=radius)
                if hit is None:
                    clear += 1
                    showing.add(route_of.get(marble, "blue"))
                else:
                    blockers[hit[1]] = blockers.get(hit[1], 0) + 1
            if len(live) > 1 and showing >= live:
                both += 1
            seen_counts.append(clear)
            frame_counts.append(read["in_frame"])
        total_in_frame = sum(frame_counts) or 1
        report.append(
            {
                "cut": cut["name"],
                "sampled": len(reads),
                "in_frame_mean": round(sum(frame_counts) / max(len(frame_counts), 1), 2),
                "visible_mean": round(sum(seen_counts) / max(len(seen_counts), 1), 2),
                "hidden_share": round(1.0 - sum(seen_counts) / total_in_frame, 3),
                "both_routes": round(both / max(len(reads), 1), 3),
                "blockers": dict(sorted(blockers.items(), key=lambda kv: -kv[1])[:4]),
            }
        )
    return report


def check_readability(
    track: dict[str, Any],
    replay: dict[str, Any],
    width: int = WIDTH,
    height: int = HEIGHT,
    stride: int = 1,
    skip: Sequence[str] = ("establish",),
    arrivals: Sequence[str] = ("finish",),
) -> list[str]:
    """The readability faults, in the same shape `check_track` reports its own.

    `skip` is the establishing shot, whose subject is the course and whose
    racers are meant to be specks - the one cut in the list that is allowed to
    fail every test here.

    `arrivals` are shots the racers **come to** rather than shots that follow
    them: a fixed lens on the finish line is not at fault for the six marbles
    still on the mountain behind it, any more than a photograph of a tape is at
    fault for the back of the field. They are held to the scale rules, which
    are about whether a marble reads, and released from the coverage and
    centring rules, which assume a camera whose job is the whole field.
    **This is the one exemption in this module and it is worth being suspicious
    of**, because an exemption that grows swallows the measurement: the way to
    tell it is honest here is that the finish is also the shot every other one
    in V21 was tuned to match, and it wins on the rules it is still held to -
    60 px median against a race-shot floor of 48.
    """
    problems: list[str] = []
    for row in readability_report(track, replay, width, height, stride):
        if row["cut"] in skip:
            continue
        arrival = row["cut"] in arrivals
        if row["px_median"] < MIN_MEDIAN_PX:
            problems.append(
                f"{row['cut']}: the median racer is {row['px_median']:.0f} px across, "
                f"under the {MIN_MEDIAN_PX:.0f} a phone frame needs"
            )
        if row["px_tail"] < MIN_TAIL_PX:
            problems.append(
                f"{row['cut']}: a tenth of the racers in shot are under "
                f"{row['px_tail']:.0f} px, which reads as scenery"
            )
        if not arrival and row["coverage"] < MIN_COVERAGE:
            problems.append(
                f"{row['cut']}: {row['in_frame_mean']:.1f} of the {row['in_play']:.1f} "
                f"racers still in the race are in frame on average, so most viewers' "
                f"marbles are outside it"
            )
        if not arrival and row["lost_seconds"] > MAX_LOST_SECONDS:
            problems.append(
                f"{row['cut']}: under {MIN_COVERAGE * 100:.0f}% of the field is in frame "
                f"for {row['lost_seconds']:.2f} s at a stretch"
            )
        if not arrival and row["off_centre"] > MAX_OFF_CENTRE:
            problems.append(
                f"{row["cut"]}: the pack sits {row['off_centre']:.2f} half-heights off "
                f"the middle of the frame"
            )
    for row in continuity_report(track, replay, width, height):
        if row["from"] in skip or row["to"] in skip:
            continue
        if row["jump"] is not None and row["jump"] > MAX_CUT_JUMP:
            problems.append(
                f"{row['from']} -> {row['to']}: the pack moves {row['jump']:.2f} of the "
                f"frame diagonal across the cut, from {row['left']} to {row['landed']}"
            )
        if row["turn"] is not None and row["turn"] < MAX_TURN:
            problems.append(
                f"{row['from']} -> {row['to']}: the cut crosses the line - the pack is "
                f"travelling one way on screen and the other way after it "
                f"(cos {row['turn']:+.2f})"
            )
    return problems
