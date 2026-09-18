"""V33: mobile-first bookends over the locked Race #2 middle.

    python tools/race2_v33_bookends.py all

Stages, each runnable on its own:

    field        where the field actually is at the line, measured off the replay
    spec         the two stands, written as JSON for the renderer
    hooks        three opening cameras, 1.5 s each, rendered and measured
    master       the full 1150-frame candidate, bookends on
    short        V32's own Short stages over those frames
    metrics      Part G and Part H, candidate against the shipped Short
    compare      the five comparison videos Part L asks for
    neutrality   the proof that no bookend changes a frame of the middle
    qc           every claim in the report, re-measured on the delivered files

**Nothing here simulates, re-times or re-cuts the race.** The replay is the one
`tools/race2_camera.py --course=switchyard --seed=8` writes, byte for byte; the
camera track from 2.233 s onward is V31's RB track unmodified; the marks, the
soundtrack and the encode are `tools/race2_v32_short.py`'s, imported rather than
reimplemented, exactly as `tools/race2_v321_short.py` does it. The variable under
test is the two stands and one opening shot.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import importlib.util
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2 import bookends, courses, kit, opening

COURSE = "switchyard"
SEED = 8
CAMERA = "output/race2/v31_readability/RB"
ENVIRONMENT = "contained_bay_v301"
TRACK_VARIANT = "B"
FACES = "both"
FPS = 60

OUT = "output/race2/v33_bookends"
DOCS = "docs/validation/race2/v33_bookends"
EXPORT = "exports/race2_v33_bookends"

SPEC = os.path.join(OUT, "bookends.json")
FIELD = os.path.join(DOCS, "field.json")
CAMERA_V33 = os.path.join(OUT, "camera")
MASTER_FRAMES = os.path.join(OUT, "frames", "master", f"clip_{COURSE}_{SEED}")

# The shipped Test #3 film, for every comparison. Not in git - see the project
# note on `exports/` - so its absence is reported rather than worked around.
SHIPPED = os.path.join(
    REPO, "..", "wt-v322-audio", "exports", "race2_v322_audio",
    "race2_switchyard_final_audio.mp4")

PHONE_SIZE = (270, 480)
DELIVERY = (1080, 1920)

# The film's own clock. `race2_v32_short` owns these; restated as the window
# this lab measures over rather than as a second source of truth, and
# `stage_qc` asserts they still agree with the module.
FILM_FRAMES = 1150
FILM_SECONDS = 19.1500       # the camera track's duration, not the replay's
HOOK_FRAMES = 90              # Part B: the first 1.5 s of each composition


class LabError(RuntimeError):
    pass


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise LabError(f"{name} is not on PATH")
    return found


def _run(command: Sequence[str], label: str) -> str:
    result = subprocess.run(list(command), cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-30:])
        raise LabError(f"{label} failed ({result.returncode}):\n{tail}")
    return result.stdout or ""


def _godot_env() -> dict[str, str]:
    env = dict(os.environ)
    return env


def _write(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return path


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _cameras_path() -> str:
    return _paths()[2]


def _paths() -> tuple[str, str, str]:
    stem = os.path.join(CAMERA, f"race2_{COURSE}_{SEED}")
    return (f"{stem}.geometry.json", f"{stem}.replay.json",
            f"{stem}.cameras.json")


# --- stage: field -----------------------------------------------------------


def _site_of(course) -> bookends.Site:
    return bookends.finish_site(course)


def stage_field(args) -> dict[str, Any]:
    """Where the field is after the line, in the finish site's own frame.

    **This is a measurement and it is the reason the finish stand is shaped the
    way it is.** The stand is sited on where the racers demonstrably end up
    rather than on where the course plan says they should, and
    `_runout_alignment` reports how far the run-out deck is turned away from
    the direction of travel, so that a reader knows which of the two they are
    looking at.

    When V33 ran this, the answer was ninety degrees: `race2.parts.RunOut`
    converted a `TrackRun.heading_deg` - `atan2(x, z)` - through
    `race2.kit.Frame.yaw`'s inverse - `atan2(-z, x)` - so the deck was laid
    *across* the track, its fall drained the field sideways and its near edge
    was the racing line itself. V33 measured that and shaped the stand around
    it rather than fixing it, because its brief locked the physics. V33.1's
    brief did not, and `docs/race2_v331_runout_fix.md` is the repair; on this
    branch the same stage reports zero.
    """
    _geometry, replay_path, _cameras = _paths()
    course = courses.build(COURSE)
    site = _site_of(course)
    replay = _read(replay_path)
    scale = float(replay.get("units", {}).get("render_scale", 0.57)) \
        if isinstance(replay.get("units"), dict) else 0.57
    # The replay is in simulation units and the site is in layout units.
    from sloped.scale import SIM_TO_LAYOUT
    scale = SIM_TO_LAYOUT

    frames = replay["frames"]
    count = min(FILM_FRAMES, len(frames))
    racers = len(frames[0]["marbles"])

    def local(point: Sequence[float]) -> tuple[float, float, float]:
        world = tuple(float(c) * scale for c in point)
        return site.local(world)

    # A crossing is the first frame a racer is past the line *while it is still
    # in the channel*: `along > 0` alone is satisfied by four other runs of this
    # switchback course, which all sit at x below the exit.
    crossing: dict[int, int] = {}
    for index in range(racers):
        for frame in range(count):
            a, u, c = local(frames[frame]["marbles"][index]["p"])
            if a > 0.0 and -1.2 < u < 1.5 and abs(c) < 3.0:
                crossing[index] = frame
                break

    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    rests: list[dict[str, Any]] = []
    below: list[dict[str, Any]] = []
    for index, first in sorted(crossing.items()):
        for frame in range(first, count):
            point = local(frames[frame]["marbles"][index]["p"])
            for axis in range(3):
                lo[axis] = min(lo[axis], point[axis])
                hi[axis] = max(hi[axis], point[axis])
        last = frames[count - 1]["marbles"][index]
        point = local(last["p"])
        speed = math.sqrt(sum(float(v) ** 2 for v in last["v"]))
        record = {
            "id": index,
            "state": str(last.get("s", "")),
            "crossed_at": round(frames[first]["t"], 4),
            "along": round(point[0], 4),
            "up": round(point[1], 4),
            "across": round(point[2], 4),
            "speed": round(speed, 4),
        }
        rests.append(record)
        if str(last.get("s", "")) == "escaped":
            below.append(record)

    # The deck the physics uses, read off the exported mesh rather than off
    # `RunOut`'s constants: the constants describe a deck in the orientation
    # the module thinks it built, and the mesh is the one that is there.
    geometry = _read(_geometry)
    deck = [module for module in geometry["modules"]
            if module["id"] == "runout"]
    surface_up = -0.52
    surface_fall = 0.0244
    deck_report: dict[str, Any] = {}
    if deck:
        flat = deck[0]["meshes"][0]["v"]
        points = [site.local((flat[i] * scale, flat[i + 1] * scale,
                              flat[i + 2] * scale))
                  for i in range(0, len(flat), 3)]
        # **Fitted through the stations that carry one height only.**
        #
        # Two rules were tried and both are wrong, which is worth writing down
        # because the failure is silent in each case. Taking the *minimum* at
        # each station picks up the rim's underside at the ends and reports a
        # fall of 0.043 per unit against a true 0.024 - the deck comes out
        # 0.20 low across its whole width. Taking the *maximum* picks up the
        # rim's top. The stations where the rim is not sampled carry exactly
        # one height, they are six of the thirteen, and a line through them is
        # the deck: intercept -0.520 at `across` 0, fall 0.0244, which is the
        # 1.4 degrees `RunOut.FALL_DEG` declares.
        by_across: dict[float, list[float]] = {}
        for a, u, c in points:
            by_across.setdefault(round(c, 3), []).append(round(u, 4))
        singles = sorted((k, vs[0]) for k, vs in by_across.items()
                         if len(set(vs)) == 1)
        keys = sorted(by_across)
        if len(singles) >= 2:
            n = float(len(singles))
            mean_c = sum(k for k, _ in singles) / n
            mean_u = sum(u for _, u in singles) / n
            numerator = sum((k - mean_c) * (u - mean_u) for k, u in singles)
            denominator = sum((k - mean_c) ** 2 for k, _ in singles)
            if abs(denominator) > 1.0e-9:
                surface_fall = numerator / denominator
            surface_up = mean_u - surface_fall * mean_c
        deck_report = {
            "across": [round(keys[0], 4), round(keys[-1], 4)],
            "along": [round(min(a for a, u, c in points), 4),
                      round(max(a for a, u, c in points), 4)],
            "top_at_across_0": round(surface_up, 4),
            "fall_per_across": round(surface_fall, 5),
            "fitted_stations": len(singles),
            "stations": len(keys),
            "covers_the_line": bool(keys[0] < 0.0 < keys[-1]),
        }

    # The well: the region the physics deck does not cover, sized on the
    # frames that fall through it.
    #
    # **Its near edge is clamped to the deck's own edge, not to the racers.**
    # Padding the fall positions symmetrically puts the pocket's lip 0.69
    # inside a deck that is holding six other racers up, and they then float
    # over a hole. The deck stops at `across` 0 and so does the well; the
    # 0.12 lip is one marble's worth of overhang, because a ball centred on
    # the edge is the ball that tips off it, and m1 is exactly that ball.
    def surface(across: float) -> float:
        return surface_up + surface_fall * across

    deck_hi = float(deck_report.get("across", [0.0, 0.0])[1]) if deck_report else 0.0
    pad = bookends.MARBLE_RADIUS + 0.30
    lip = bookends.MARBLE_RADIUS * 0.42
    falls: list[tuple[int, float, float, float]] = []
    for frame in range(count):
        for index in range(racers):
            a, u, c = local(frames[frame]["marbles"][index]["p"])
            if 0.0 < a < 9.0 and abs(c) < 9.0 and -3.0 < u < surface(c) - 0.12:
                falls.append((index, a, u, c))

    well = None
    unsupported: list[dict[str, Any]] = []
    if falls:
        floor = min(f[2] for f in falls) - bookends.MARBLE_RADIUS - 0.04
        well = {
            "along": [round(min(f[1] for f in falls) - pad, 4),
                      round(max(f[1] for f in falls) + pad, 4)],
            "across": [round(max(min(f[3] for f in falls) - pad,
                                 deck_hi - lip), 4),
                       round(max(f[3] for f in falls) + pad, 4)],
            "floor": round(floor, 4),
            "racers": sorted({f[0] for f in falls}),
            "frames": len(falls),
        }
        # Part H's own honesty check: a racer that is over the pocket, well
        # above its floor and not descending is a racer the picture will show
        # floating. Counted rather than assumed away.
        for frame in range(count):
            for index in range(racers):
                marble = frames[frame]["marbles"][index]
                a, u, c = local(marble["p"])
                if not (well["along"][0] <= a <= well["along"][1]):
                    continue
                if not (well["across"][0] <= c <= well["across"][1]):
                    continue
                if u <= floor + 0.70 or float(marble["v"][1]) <= -1.0:
                    continue
                unsupported.append({"id": index, "t": round(frames[frame]["t"], 4),
                                    "along": round(a, 3), "up": round(u, 3),
                                    "across": round(c, 3)})

    # How fast the sprint descends, per unit of `along`, so the approach
    # colonnade can stand on the racing line rather than on one datum.
    run = course.runs["sprint"]
    entry = site.local(tuple(float(c) for c in run.path[0]))
    channel = {"fall": round(entry[1] / max(1.0e-9, -entry[0]), 5),
               "entry": [round(v, 4) for v in entry]}

    # **The sight corridor: where the final chase looks through the plaza.**
    #
    # Traced on the delivered camera track rather than assumed. For every frame
    # of the last cut and every racer that is below the deck, the ray from the
    # lens to that racer is walked until it crosses the plaza plane, and the
    # union of those crossings is the rectangle the plaza must leave open. The
    # camera is locked, so this is the environment adapting to the lens, which
    # is the order the brief asks for.
    track = _read(_cameras_path())
    last = track["cuts"][-1]
    corridor_along = [math.inf, -math.inf]
    corridor_across = [math.inf, -math.inf]
    rays = 0
    for row in last["frames"]:
        index = int(round(float(row[0]) * FPS))
        if index >= count:
            continue
        eye = site.local(tuple(float(c) for c in row[1:4]))
        for racer in range(racers):
            point = local(frames[index]["marbles"][racer]["p"])
            if point[1] > surface(point[2]) - 0.15:
                continue
            for step_index in range(1, 80):
                phase = step_index / 80.0
                walk = [eye[axis] + (point[axis] - eye[axis]) * phase
                        for axis in range(3)]
                if walk[1] <= surface(walk[2]):
                    corridor_along[0] = min(corridor_along[0], walk[0])
                    corridor_along[1] = max(corridor_along[1], walk[0])
                    corridor_across[0] = min(corridor_across[0], walk[2])
                    corridor_across[1] = max(corridor_across[1], walk[2])
                    rays += 1
                    break
    sight = None
    if rays:
        pad = 0.18
        sight = {
            "along": [round(corridor_along[0] - pad, 4),
                      round(corridor_along[1] + pad, 4)],
            # The corridor stops at the pocket's own edge: past it the pocket
            # is already open, and extending the cut would remove plaza that
            # nothing is looking through.
            "across": [round(corridor_across[0] - pad, 4),
                       round(min(corridor_across[1] + pad,
                                 well["across"][0] if well else 0.0), 4)],
            "rays": rays,
        }

    report = {
        "course": COURSE,
        "seed": SEED,
        "channel": channel,
        "sight": sight,
        "racers": racers,
        "frames": count,
        "site": site.describe(),
        "envelope": {
            "along": [round(lo[0], 4), round(hi[0], 4)],
            "up": [round(lo[1], 4), round(hi[1], 4)],
            "across": [round(lo[2], 4), round(hi[2], 4)],
        },
        "rest": rests,
        "deck": deck_report,
        "well": well,
        "unsupported_frames": unsupported,
        "finding": _runout_alignment(course, below),
    }
    _write(FIELD, report)
    print(f"field: {len(crossing)}/{racers} crossings, envelope along "
          f"{report['envelope']['along']} across {report['envelope']['across']}")
    if below:
        print(f"  {len(below)} racer(s) end below the deck, frozen: "
              f"{[r['id'] for r in below]} at up "
              f"{[r['up'] for r in below]}")
    if deck_report:
        print(f"  run-out deck spans across {deck_report['across']}, "
              f"covers the line: {deck_report['covers_the_line']}")
    if well:
        print(f"  well along {well['along']} across {well['across']} floor "
              f"{well['floor']}, {well['frames']} falling frames")
    print(f"  racer-frames left visibly unsupported over the well: "
          f"{len(unsupported)}")
    if sight:
        print(f"  sight corridor along {sight['along']} across "
              f"{sight['across']} from {sight['rays']} rays")
    print(f"  -> {FIELD}")
    return report


# --- stage: spec ------------------------------------------------------------


def field_from_report(report: dict[str, Any]) -> bookends.Field:
    envelope = report["envelope"]
    deck = report.get("deck") or {}
    well = report.get("well")
    sight = report.get("sight")
    rest = [r for r in report["rest"] if r["state"] != "escaped"]
    return bookends.Field(
        channel_fall=float(report.get("channel", {}).get("fall", 0.2842)),
        along=(envelope["along"][0], envelope["along"][1]),
        across=(envelope["across"][0], envelope["across"][1]),
        rest_up=(min(r["up"] for r in rest) if rest else -0.43),
        surface_up=float(deck.get("top_at_across_0", -0.52)),
        surface_fall=float(deck.get("fall_per_across", 0.0244)),
        well_along=tuple(well["along"]) if well else None,
        well_across=tuple(well["across"]) if well else None,
        well_floor=float(well["floor"]) if well else None,
        sight_along=tuple(sight["along"]) if sight else None,
        sight_across=tuple(sight["across"]) if sight else None,
    )


def _runout_alignment(course, below) -> dict[str, Any]:
    """How far the run-out deck is turned away from the direction of travel.

    **Measured, not asserted.** This block used to carry a hard-coded 90.0 and
    a note saying the deck was laid across the track, which was true when V33
    measured it and false the moment V33.1 repaired it. A finding that cannot
    come back clean is not a finding, so the angle is read off the built module
    and the note follows from it - the same stage now reports the defect on a
    branch that has it and reports zero on one that does not.
    """
    run = course.runs["sprint"]
    deck = course.machine.modules["runout"]
    tangent = kit.flat_forward(run.tangents[len(run.path) - 1])
    dot = sum(tangent[axis] * deck.forward[axis] for axis in range(3))
    cross_y = tangent[2] * deck.forward[0] - tangent[0] * deck.forward[2]
    error = math.degrees(math.atan2(cross_y, dot))
    aligned = abs(error) < 1.0e-6
    return {
        "runout_yaw_error_deg": round(error, 9),
        "aligned": aligned,
        "note": ("the run-out deck's forward axis is the sprint's own exit "
                 "tangent" if aligned else
                 "race2.parts.RunOut reads TrackRun.heading_deg (atan2(x, z)) "
                 "through Frame.yaw's inverse (atan2(-z, x)); the deck is laid "
                 "across the travel direction"),
        "racers_frozen_off_the_deck": [r["id"] for r in below],
    }


def stage_spec(args) -> dict[str, Any]:
    report = _read(FIELD) if os.path.isfile(FIELD) else stage_field(args)
    course = courses.build(COURSE)
    spec = bookends.build(course, field=field_from_report(report))
    _write(SPEC, spec)

    _geometry, replay_path, _cameras = _paths()
    replay = _read(replay_path)
    from sloped.scale import SIM_TO_LAYOUT
    points = []
    for frame in replay["frames"][:FILM_FRAMES]:
        for marble in frame["marbles"]:
            points.append(tuple(float(c) * SIM_TO_LAYOUT for c in marble["p"]))
    gaps = bookends.clearance(spec, points)
    summary = {
        "spec": SPEC,
        "stands": {stand["id"]: {
            "static": len(stand["static"]),
            "motion": len(stand["motion"]["parts"]),
            "meta": stand["meta"],
        } for stand in spec["stands"]},
        "clearance": gaps,
        "sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode("utf-8")).hexdigest(),
    }
    _write(os.path.join(DOCS, "spec.json"), summary)
    for stand in spec["stands"]:
        gap = gaps[stand["id"]]
        print(f"spec: {stand['id']:<7} {len(stand['static']):3d} static + "
              f"{len(stand['motion']['parts'])} moving, nearest racer "
              f"{gap['min_gap']:.3f} at {gap['part']}")
    print(f"  -> {SPEC}")
    return summary


# --- stage: camera ----------------------------------------------------------


def racer_row():
    """The eight resting centres and the start site, from the course."""
    course = courses.build(COURSE)
    site = bookends.start_site(course)
    module = course.machine.modules["start"]
    rise = 0.5 * module.DECK_THICK + bookends.MARBLE_RADIUS
    points = opening.racer_points(site, module.bays, module.BAY_PITCH, rise)
    return course, site, module, points


def solved(site, points) -> dict[str, float]:
    return {c.key: opening.solve(site, c, points, bookends.MARBLE_RADIUS)
            for c in opening.COMPOSITIONS}


def stage_camera(args) -> dict[str, Any]:
    """One camera track per composition: the opening cut, the rest copied.

    Written into `output/race2/v33_bookends/camera/<key>/` in the layout
    `tools/race2_render.py` already reads, with the geometry and the replay
    **hard-linked rather than copied** where the filesystem allows it: the
    replay is 12.6 MB and three copies of it is the kind of thing that makes a
    later reader wonder whether they are the same file.
    """
    _geometry, _replay, cameras = _paths()
    source = _read(cameras)
    _course, site, _module, points = racer_row()
    distances = solved(site, points)

    upper = [cut for cut in source["cuts"] if cut["name"] == "upper"]
    if not upper:
        raise LabError("the source track has no 'upper' cut to hand off to")
    target = opening.handoff_pose(upper[0], FPS)
    # The field's own centroid, off the replay this film is made from, so the
    # opening shot follows what it is pointing at rather than a plan of it.
    from sloped.scale import SIM_TO_LAYOUT
    subject = opening.pack_centroid(_read(_paths()[1]), SIM_TO_LAYOUT, FPS)

    release = [cut for cut in source["cuts"] if cut["name"] == "release"][0]
    first = float(release["frames"][0][0])
    last = float(release["frames"][-1][0])

    report: dict[str, Any] = {"handoff_target": [list(target[0]), list(target[1]),
                                                 target[2]],
                              "compositions": {}}
    for composition in opening.COMPOSITIONS:
        cut = opening.opening_cut(site, composition, distances[composition.key],
                                  target, FPS, first, last, subject=subject)
        track = opening.rewrite_track(source, cut)
        folder = os.path.join(CAMERA_V33, composition.key)
        os.makedirs(folder, exist_ok=True)
        _write(os.path.join(folder, f"race2_{COURSE}_{SEED}.cameras.json"), track)
        for suffix in ("geometry", "replay"):
            target_path = os.path.join(folder, f"race2_{COURSE}_{SEED}.{suffix}.json")
            source_path = os.path.join(CAMERA, f"race2_{COURSE}_{SEED}.{suffix}.json")
            if os.path.exists(target_path):
                os.remove(target_path)
            try:
                os.link(source_path, target_path)
            except OSError:
                shutil.copyfile(source_path, target_path)
        error = opening.handoff_error(cut, upper[0], FPS)
        held = _holding(cut, _read(_paths()[1]))
        # Every later cut must be the object the source carried, not a
        # re-serialisation of it. Compared as JSON text so a float that
        # round-tripped differently is caught rather than smoothed over.
        untouched = all(
            json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
            for a, b in zip(track["cuts"][1:], source["cuts"][1:]))
        if not untouched:
            raise LabError(f"{composition.key}: a cut after the opening moved")
        report["compositions"][composition.key] = {
            "distance": round(distances[composition.key], 4),
            "holding": held,
            "frames": len(cut["frames"]),
            "from": cut["from"],
            "to": cut["to"],
            "handoff": error,
            "later_cuts_identical": untouched,
            "track": os.path.join(folder, f"race2_{COURSE}_{SEED}.cameras.json"),
        }
        print(f"camera {composition.key}: {len(cut['frames'])} frames, handoff "
              f"step ratio {error['step_ratio']:.3f}; all eight in frame for "
              f"{held['all_eight']}/{held['frames']}, none in frame for "
              f"{held['empty']}")
    _write(os.path.join(DOCS, "camera.json"), report)
    return report


def _holding(cut: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    """How many racers the opening shot actually holds, frame by frame.

    Part M's "can a viewer keep their chosen colour after release?", answered
    analytically so it can be asked of a camera before a render exists. A
    racer counts when its centre projects inside the frame with a 2% skirt.
    """
    from sloped.scale import SIM_TO_LAYOUT

    counts = []
    for row in cut["frames"]:
        index = min(len(replay["frames"]) - 1,
                    max(0, int(round(float(row[0]) * FPS))))
        points = [tuple(float(c) * SIM_TO_LAYOUT for c in marble["p"])
                  for marble in replay["frames"][index]["marbles"]]
        projected = opening.screen(points, row[1:4], row[4:7], row[7])
        counts.append(sum(1 for x, y, depth in projected
                          if depth > 0.0 and abs(x) <= 1.02 and abs(y) <= 1.02))
    return {
        "frames": len(counts),
        "all_eight": sum(1 for value in counts if value == 8),
        "empty": sum(1 for value in counts if value == 0),
        "worst": min(counts),
        "counts": counts,
    }


# --- stage: hooks -----------------------------------------------------------


def _render(frames_dir: str, camera_dir: str, extra: Sequence[str],
            label: str) -> str:
    command = [sys.executable, os.path.join("tools", "race2_render.py")] + list(extra)
    command += [f"--course={COURSE}", f"--seed={SEED}", f"--out={camera_dir}",
                f"--frames={frames_dir}", f"--environment={ENVIRONMENT}",
                f"--track={TRACK_VARIANT}", f"--faces={FACES}"]
    return _run(command, label)


def stage_hooks(args) -> dict[str, Any]:
    """Part B: the first 1.5 s of each composition, rendered and measured."""
    if not os.path.isfile(SPEC):
        stage_spec(args)
    if not os.path.isdir(CAMERA_V33):
        stage_camera(args)
    _course, site, module, points = racer_row()
    distances = solved(site, points)
    spec = _read(SPEC)

    report: dict[str, Any] = {"seconds": round(HOOK_FRAMES / FPS, 4),
                              "compositions": []}
    for composition in opening.COMPOSITIONS:
        folder = os.path.join(OUT, "hooks", composition.key)
        camera_dir = os.path.join(CAMERA_V33, composition.key)
        distance = distances[composition.key]
        measured = opening.measure(site, composition, distance, points,
                                   bookends.MARBLE_RADIUS)
        blocked = sorted({bookends.blocked(spec, measured["position"], point)
                          for point in points} - {""})
        measured["blocked_by"] = blocked
        if not args.measure_only:
            _render(folder, camera_dir,
                    ["clip", f"--bookends={SPEC}",
                     f"--end={HOOK_FRAMES / FPS:.6f}"],
                    f"hook {composition.key}")
            clip = os.path.join(folder, f"clip_{COURSE}_{SEED}")
            made = sorted(glob.glob(os.path.join(clip, "frame_*.png")))
            measured["frames"] = len(made)
            measured["clip"] = clip
        report["compositions"].append(measured)
        print(f"hook {composition.key} {composition.title}: "
              f"racer {measured['median_diameter_1080']:.0f} px @1080, "
              f"{measured['median_diameter_270']:.1f} px @270, gap "
              f"{measured['min_gap_in_diameters']:.2f} d, area "
              f"{measured['racer_area_share'] * 100:.2f}%, blocked "
              f"{blocked or 'none'}")
    _write(os.path.join(DOCS, "hooks.json"), report)
    return report


# --- stage: master ----------------------------------------------------------

WINNER = "C"


def stage_master(args) -> dict[str, Any]:
    """The full candidate picture: 1150 frames, bookends on, winner hook."""
    if not os.path.isfile(SPEC):
        stage_spec(args)
    if not os.path.isdir(os.path.join(CAMERA_V33, args.hook)):
        stage_camera(args)
    folder = os.path.dirname(MASTER_FRAMES)
    # **`--end` is not optional and its absence is not visible.** The renderer's
    # clip length is the *replay's* duration, which is 40 s, not the camera
    # track's 19.15: without it the render walks past the end of the film and
    # writes 2401 frames, of which the first 1150 are the ones anybody wanted.
    # V32's own error message carries the same flag for the same reason.
    _render(folder, os.path.join(CAMERA_V33, args.hook),
            ["clip", f"--bookends={SPEC}", f"--end={FILM_SECONDS:.4f}"],
            f"master {args.hook}")
    made = sorted(glob.glob(os.path.join(MASTER_FRAMES, "frame_*.png")))
    report = {"hook": args.hook, "frames": len(made), "dir": MASTER_FRAMES}
    if len(made) != FILM_FRAMES:
        raise LabError(f"master rendered {len(made)} frames, not {FILM_FRAMES}")
    _write(os.path.join(DOCS, "master.json"), report)
    print(f"master: {len(made)} frames in {MASTER_FRAMES}")
    return report


# --- frame measurement ------------------------------------------------------


def _load(path: str):
    from PIL import Image
    import numpy as np

    with Image.open(path) as handle:
        return np.asarray(handle.convert("RGB"), dtype=np.uint8)


def _racer_labels(frame) -> dict[int, dict[str, Any]]:
    """Per-racer pixel statistics from a `--track=racers` matte.

    `race2_track_surface.racer_class` writes the racer's index into the red
    byte and a flag into the green byte, eight labels nineteen apart at the
    closest. The green byte is tested first because the background is black and
    a red byte of 0 is a legitimate label - reading red alone counts the whole
    room as racer 0, which is the mistake this comment exists to stop.
    """
    import numpy as np

    out: dict[int, dict[str, Any]] = {}
    flag = frame[:, :, 1] > 96
    if not flag.any():
        return out
    reds = frame[:, :, 0][flag]
    for label in sorted(int(v) for v in np.unique(reds)):
        near = flag & (np.abs(frame[:, :, 0].astype(int) - label) <= 8)
        count = int(near.sum())
        if count < 12:
            continue
        ys, xs = np.nonzero(near)
        out[label] = {
            "pixels": count,
            "centre": [float(xs.mean()), float(ys.mean())],
            "box": [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            "diameter": float(2.0 * math.sqrt(count / math.pi)),
        }
    return out


def _frame_metrics(path: str) -> dict[str, Any]:
    labels = _racer_labels(_load(path))
    diameters = sorted(entry["diameter"] for entry in labels.values())
    centres = [entry["centre"] for entry in labels.values()]
    gaps = []
    for i in range(len(centres)):
        for j in range(i + 1, len(centres)):
            gaps.append(math.dist(centres[i], centres[j]))
    middle = len(diameters) // 2
    median = 0.0
    if diameters:
        median = (diameters[middle] if len(diameters) % 2
                  else 0.5 * (diameters[middle - 1] + diameters[middle]))
    pixels = sum(entry["pixels"] for entry in labels.values())
    return {
        "visible": len(labels),
        "median_diameter": round(median, 2),
        "min_diameter": round(diameters[0], 2) if diameters else 0.0,
        "max_diameter": round(diameters[-1], 2) if diameters else 0.0,
        "occupancy": round(pixels / float(DELIVERY[0] * DELIVERY[1]), 6),
        "min_gap": round(min(gaps), 2) if gaps else 0.0,
        "min_gap_in_diameters": round(min(gaps) / median, 3)
        if gaps and median else 0.0,
        "top": min((entry["box"][1] for entry in labels.values()), default=0),
        "bottom": max((entry["box"][3] for entry in labels.values()), default=0),
    }


def _matte(folder: str, camera_dir: str, bookends: bool, start: float,
           end: float, label: str) -> str:
    extra = ["clip", "--track=racers", "--start=%.6f" % start,
             "--end=%.6f" % end]
    if bookends:
        extra.append("--bookends=" + SPEC)
    command = [sys.executable, os.path.join("tools", "race2_render.py")] + extra
    command += ["--course=" + COURSE, "--seed=%d" % SEED, "--out=" + camera_dir,
                "--frames=" + folder, "--environment=" + ENVIRONMENT,
                "--faces=" + FACES]
    _run(command, label)
    return os.path.join(folder, "clip_%s_%d" % (COURSE, SEED))


# --- stage: control ---------------------------------------------------------


CONTROL_FRAMES = os.path.join(OUT, "frames", "control", "clip_%s_%d" % (COURSE, SEED))


def stage_control(args) -> dict[str, Any]:
    """The same 1150 frames with no bookends and the shipped camera.

    This is Test #3's picture rebuilt on this branch, and it is what every
    comparison in Part L is against. It is also half of the neutrality proof:
    `stage_neutrality` renders the *base commit* in its own worktree and
    requires these frames to match it byte for byte, which is the only way to
    say that adding a seam changed nothing while the seam is switched off.
    """
    folder = os.path.dirname(CONTROL_FRAMES)
    _render(folder, CAMERA, ["clip", f"--end={FILM_SECONDS:.4f}"], "control")
    made = sorted(glob.glob(os.path.join(CONTROL_FRAMES, "frame_*.png")))
    if len(made) != FILM_FRAMES:
        raise LabError("control rendered %d frames, not %d"
                       % (len(made), FILM_FRAMES))
    print("control: %d frames in %s" % (len(made), CONTROL_FRAMES))
    return {"frames": len(made), "dir": CONTROL_FRAMES}


# --- stage: metrics ---------------------------------------------------------


def _difference(a: str, b: str) -> dict[str, float]:
    import numpy as np

    left = _load(a).astype(np.int16)
    right = _load(b).astype(np.int16)
    delta = np.abs(left - right).max(axis=2)
    changed = delta > 6
    return {
        "changed": float(changed.mean()),
        "mean_abs": float(np.abs(left - right).mean()),
        "max_abs": float(np.abs(left - right).max()),
    }


def stage_metrics(args) -> dict[str, Any]:
    """Parts G and H, measured on rendered frames rather than on the plan."""
    if not os.path.isfile(SPEC):
        stage_spec(args)
    opening_seconds = 2.0
    hook_dir = os.path.join(CAMERA_V33, args.hook)
    candidate = _matte(os.path.join(OUT, "matte", "candidate"), hook_dir, True,
                       0.0, opening_seconds, "matte candidate")
    control = _matte(os.path.join(OUT, "matte", "control"), CAMERA, False,
                     0.0, opening_seconds, "matte control")

    report: dict[str, Any] = {"hook": args.hook, "opening": {}, "finish": {}}
    for name, folder in (("test3", control), ("test4", candidate)):
        frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
        if not frames:
            raise LabError("no matte frames in " + folder)
        rows = [_frame_metrics(path) for path in frames]
        first = rows[0]
        report["opening"][name] = {
            "frames": len(rows),
            "frame0": first,
            "frame0_phone_diameter": round(first["median_diameter"]
                                           * PHONE_SIZE[0] / DELIVERY[0], 2),
            "mean_visible": round(sum(r["visible"] for r in rows) / len(rows), 3),
            "mean_diameter": round(sum(r["median_diameter"] for r in rows)
                                   / len(rows), 2),
            "mean_occupancy": round(sum(r["occupancy"] for r in rows)
                                    / len(rows), 6),
            "all_eight_frames": sum(1 for r in rows if r["visible"] == 8),
            "per_frame": rows,
        }
    left = report["opening"]["test3"]["frame0"]
    right = report["opening"]["test4"]["frame0"]
    report["opening"]["gain"] = {
        "diameter": round(right["median_diameter"]
                          / max(1e-6, left["median_diameter"]), 3),
        "occupancy": round(right["occupancy"] / max(1e-9, left["occupancy"]), 3),
        "separation": round(right["min_gap_in_diameters"]
                            - left["min_gap_in_diameters"], 3),
    }
    _write(os.path.join(DOCS, "metrics.json"), report)
    print("opening frame 0: Test #3 racer %.1f px, Test #4 %.1f px (x%.2f); "
          "occupancy x%.2f"
          % (left["median_diameter"], right["median_diameter"],
             report["opening"]["gain"]["diameter"],
             report["opening"]["gain"]["occupancy"]))
    return report


# --- stage: short -----------------------------------------------------------


HOOK_TEXTS = {
    "your": ("PICK YOUR", "COLOR"),
    "a": ("PICK A", "COLOR"),
}


def load_short(frames: str, tag: str, lines: tuple[str, ...],
               camera: str = CAMERA):
    """`tools/race2_v32_short.py`, repointed and with one string overridden.

    The V32.1 branch established this pattern and its reason holds here: the
    hook plate, the winner's ring, the payoff card, the clock, the encode and
    the QC are *called*, not reimplemented, so a difference between the V32
    Short and this one can only come from the pixels underneath them and from
    the two things this function changes - where the frames are, and what the
    first mark says.
    """
    spec = importlib.util.spec_from_file_location(
        "race2_v32_short", os.path.join(REPO, "tools", "race2_v32_short.py"))
    short = importlib.util.module_from_spec(spec)
    sys.modules["race2_v32_short"] = short
    spec.loader.exec_module(short)

    from race2 import presentation as pres

    # **Rebinding `HOOK_LINES` is not enough, and the reason is a default.**
    # `presentation.hook_placement(..., lines=HOOK_LINES)` binds that tuple
    # when the module is imported, so setting the module global afterwards
    # changes what a reader sees and not what the function uses - the plate
    # would still have said PICK A COLOR while every report said otherwise.
    # The call site is wrapped instead, which is the only place the default is
    # reachable from. `hook_plate` is safe because `stage_overlays` passes the
    # lines it was given.
    pres.HOOK_LINES = tuple(lines)
    pres.HOOK_TEXT = " ".join(lines)
    placement = getattr(pres, "_v33_original_placement", pres.hook_placement)
    pres._v33_original_placement = placement

    def hook_placement(replay, track, clock, lines=tuple(lines), marbles=8):
        return placement(replay, track, clock, lines, marbles)

    pres.hook_placement = hook_placement

    short.FRAMES = frames
    # **The camera, and this one is load-bearing.** `_paths` reads `CAMERA` and
    # `hook_placement` measures the racer band through whatever track it gets.
    # Left at V32's, the mark is fitted above racers that are at y 806 on the
    # *shipped* opening while this film has its topmost racer at y 523 - the
    # block's own ink runs to 608, so the plate would have been laid across the
    # racer it exists to point at. The first build did exactly that and the
    # report printed "racers at y 806" while the frames said otherwise.
    short.CAMERA = camera
    short.OUT = os.path.join(OUT, "short", tag)
    short.WORK = os.path.join(short.OUT, "work")
    short.DOCS = os.path.join(DOCS, "short", tag)
    short.EXPORT = os.path.join(EXPORT, tag)
    short.MASTER = os.path.join(short.EXPORT, f"race2_{COURSE}_master.mp4")
    short.VISUAL = os.path.join(short.EXPORT, f"race2_{COURSE}_final_visual.mp4")
    short.FINAL = os.path.join(short.EXPORT, f"race2_{COURSE}_final.mp4")
    short.PHONE = os.path.join(
        short.EXPORT, f"race2_{COURSE}_final_phone_270x480.mp4")
    for folder in (short.OUT, short.WORK, short.DOCS, short.EXPORT):
        os.makedirs(folder, exist_ok=True)
    return short


def _shipped_audio(target: str) -> str:
    """The delivered V32.2 soundtrack, as a stream copy.

    **Part I says the audio is closed, and a stream copy is the strongest way
    to say so.** The V32.2 branch locked its picture by `-c:v copy` from the
    file that shipped; this locks the sound the same way and in the same
    direction. No encoder touches it, so it cannot differ - not by a
    resampling, not by a bit rate, not by a loudness pass.

    The soundtrack is a function of the replay and the film's length, and both
    are unchanged, so the delivered stream is the correct one for this picture
    rather than an approximation of it.
    """
    if not os.path.isfile(SHIPPED):
        raise LabError(
            "the delivered V32.2 Short is not at\n  " + SHIPPED
            + "\nIt is the only copy of the shipped soundtrack and it is not in "
              "git; see the project note on exports/.")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    _run([_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", SHIPPED,
          "-vn", "-c:a", "copy", target], "extract V32.2 audio")
    return target


def stage_short(args) -> dict[str, Any]:
    """V32's own marks and encode over the V33 picture, with V32.2's sound."""
    made: dict[str, Any] = {}
    for key, lines in HOOK_TEXTS.items():
        if args.text not in ("both", key):
            continue
        frames = MASTER_FRAMES
        short = load_short(frames, key, lines,
                           os.path.join(CAMERA_V33, args.hook))
        if not sorted(glob.glob(os.path.join(frames, "frame_*.png"))):
            raise LabError(f"no master frames in {frames}; run `master` first")
        short.main(["evidence"])
        short.main(["audio"])
        short.main(["overlays"])
        short.main(["mux"])

        audio = _shipped_audio(os.path.join(short.WORK, "v322.m4a"))
        final = os.path.join(EXPORT, f"race2_{COURSE}_v33_{key}.mp4")
        phone = os.path.join(EXPORT, f"race2_{COURSE}_v33_{key}_phone_270x480.mp4")
        os.makedirs(EXPORT, exist_ok=True)
        # **No `-shortest`.** The delivered soundtrack is 920000 samples =
        # 19.16667 s and the picture is 1150 frames = the same, but the AAC
        # container rounds its duration to 19.166 - marginally the shorter of
        # the two - and `-shortest` then truncates the *video* by one frame.
        # It did so on one of these two otherwise identical muxes and not the
        # other, which is the worst way for a flag to be wrong: `your` came out
        # at 1149 frames and 19.150 s while `a` came out correct. Both streams
        # are written in full instead, and `qc` counts the frames.
        _run([_tool("ffmpeg"), "-y", "-loglevel", "error",
              "-i", short.VISUAL, "-i", audio,
              "-map", "0:v:0", "-map", "1:a:0",
              "-c:v", "copy", "-c:a", "copy",
              "-movflags", "+faststart", final], f"mux {key}")
        _run([_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", final,
              "-vf", f"scale={PHONE_SIZE[0]}:{PHONE_SIZE[1]}:flags=lanczos",
              "-c:v", "libx264", "-crf", "20", "-preset", "slow",
              "-pix_fmt", "yuv420p", "-c:a", "copy", phone], f"phone {key}")
        made[key] = {"final": final, "phone": phone,
                     "visual": short.VISUAL, "master": short.MASTER,
                     "lines": list(lines),
                     "evidence": os.path.join(short.DOCS, "evidence.json")}
        print(f"short {key}: {final}")
    _write(os.path.join(DOCS, "short.json"), made)
    return made


# --- stage: neutrality ------------------------------------------------------


def stage_neutrality(args) -> dict[str, Any]:
    """With no `--bookends=`, this branch renders the base commit's frames.

    The seam is one `if path.is_empty(): return` in `race2_scene.gd` and one
    optional flag in `tools/race2_render.py`, and the claim that neither
    changes a pixel is worth an experiment rather than a reading. A temporary
    worktree at the production commit renders the same nine instants with the
    same command line, and the two sets are compared by SHA-256.

    Byte equality, not an image difference: two renders of one scene on one GPU
    are deterministic here - V23 established that and every locks report since
    has relied on it - so anything short of identical is a finding.
    """
    base = args.base
    worktree = os.path.abspath(os.path.join(REPO, "..", "wt-v33-neutrality"))
    at = ",".join(f"{index / 60.0:.6f}" for index in
                  (0, 60, 300, 600, 900, 1000, 1100, 1149))
    common = ["still", f"--course={COURSE}", f"--seed={SEED}",
              f"--out={os.path.abspath(CAMERA)}",
              f"--environment={ENVIRONMENT}", f"--track={TRACK_VARIANT}",
              f"--faces={FACES}", f"--at={at}"]

    created = False
    if not os.path.isdir(worktree):
        _run(["git", "worktree", "add", "--detach", worktree, base],
             "worktree for the base commit")
        created = True
    try:
        here = os.path.join(OUT, "neutrality", "branch")
        there = os.path.join(OUT, "neutrality", "base")
        _run([sys.executable, os.path.join("tools", "race2_render.py")]
             + common + [f"--frames={os.path.abspath(here)}"], "neutrality here")
        result = subprocess.run(
            [sys.executable, os.path.join(worktree, "tools", "race2_render.py")]
            + common + [f"--frames={os.path.abspath(there)}"],
            cwd=worktree, capture_output=True, text=True, encoding="utf-8",
            errors="replace")
        if result.returncode != 0:
            raise LabError("base render failed:\n"
                           + (result.stderr or result.stdout or "")[-2000:])
        mine = sorted(glob.glob(os.path.join(here, "still_*", "*.png")))
        theirs = sorted(glob.glob(os.path.join(there, "still_*", "*.png")))
        if not mine or len(mine) != len(theirs):
            raise LabError(f"neutrality: {len(mine)} frames here, "
                           f"{len(theirs)} at {base}")
        rows = []
        for left, right in zip(mine, theirs):
            a = hashlib.sha256(open(left, "rb").read()).hexdigest()
            b = hashlib.sha256(open(right, "rb").read()).hexdigest()
            rows.append({"frame": os.path.basename(left), "branch": a[:16],
                         "base": b[:16], "identical": a == b})
        report = {"base": base, "frames": len(rows),
                  "identical": sum(1 for r in rows if r["identical"]),
                  "rows": rows}
        _write(os.path.join(DOCS, "neutrality.json"), report)
        print(f"neutrality: {report['identical']}/{report['frames']} frames "
              f"byte-identical to {base}")
        if report["identical"] != report["frames"]:
            raise LabError("the bookend seam changed a frame with no bookends")
        return report
    finally:
        if created and not args.keep_worktree:
            _run(["git", "worktree", "remove", "--force", worktree],
                 "remove the base worktree")


# --- stage: middle ----------------------------------------------------------


MIDDLE_FROM = 2.233333
MIDDLE_TO = 12.683333


def stage_middle(args) -> dict[str, Any]:
    """Part E: how much of the locked middle the bookends actually touch.

    The honest form of "the middle is unchanged". The camera track from 2.233 s
    on is the shipped one - `stage_camera` asserts the cuts are the same
    objects - and the replay, the course, the environment, the lights and the
    track are the same files. What a bookend *can* still do is appear in a
    frame, because the finish gantry is the tallest thing on this stage. So
    every frame of the middle is differenced against the control and the report
    says, per frame, how much of it moved and why.
    """
    candidate = sorted(glob.glob(os.path.join(MASTER_FRAMES, "frame_*.png")))
    control = sorted(glob.glob(os.path.join(CONTROL_FRAMES, "frame_*.png")))
    if len(candidate) != FILM_FRAMES or len(control) != FILM_FRAMES:
        raise LabError("both masters must be rendered first "
                       f"({len(candidate)} / {len(control)})")
    first = int(round(MIDDLE_FROM * FPS))
    last = int(round(MIDDLE_TO * FPS))
    step = max(1, args.stride)
    rows = []
    for index in range(first, last + 1, step):
        delta = _difference(candidate[index], control[index])
        rows.append({"frame": index, "t": round(index / FPS, 4),
                     "changed": round(delta["changed"], 6),
                     "mean_abs": round(delta["mean_abs"], 4),
                     "max_abs": int(delta["max_abs"])})
    identical = [r for r in rows if r["changed"] == 0.0]
    worst = max(rows, key=lambda r: r["changed"])
    report = {
        "window": [MIDDLE_FROM, MIDDLE_TO],
        "sampled": len(rows),
        "stride": step,
        "identical_frames": len(identical),
        "identical_share": round(len(identical) / len(rows), 4),
        "worst": worst,
        "mean_changed": round(sum(r["changed"] for r in rows) / len(rows), 6),
        "rows": rows,
    }
    _write(os.path.join(DOCS, "middle.json"), report)
    print(f"middle {MIDDLE_FROM:.3f}-{MIDDLE_TO:.3f} s: {len(identical)}/"
          f"{len(rows)} sampled frames identical to the control, worst frame "
          f"{worst['frame']} at {worst['changed'] * 100:.2f}% of pixels")
    return report


# --- stage: finish ----------------------------------------------------------


FINISH_FROM = 12.683333
CROSSING = 15.816667


def stage_finish(args) -> dict[str, Any]:
    """Part H: when the destination arrives, and what it does to the sprint.

    **The finish stand is measured as the difference between two renders.**
    Painting it into a segmentation class would put it in the same class as the
    course's own modules, which is the question rather than the answer; the
    control is the same 1150 frames with the seam switched off, so every pixel
    that differs is the stand, its shadow, or something the stand is reflecting
    light onto - all of which are the stand arriving.

    "First clearly visible" is the first frame in the final chase at which the
    stand holds `visible_floor` of the frame *and keeps holding it*, because a
    corner of a leg passing a frame edge for four frames is not a destination
    coming into view.
    """
    candidate = sorted(glob.glob(os.path.join(MASTER_FRAMES, "frame_*.png")))
    control = sorted(glob.glob(os.path.join(CONTROL_FRAMES, "frame_*.png")))
    if len(candidate) != FILM_FRAMES or len(control) != FILM_FRAMES:
        raise LabError("both masters must be rendered first "
                       f"({len(candidate)} / {len(control)})")
    first = int(round(FINISH_FROM * FPS))
    step = max(1, args.stride)
    floor = 0.012
    rows = []
    for index in range(first, FILM_FRAMES, step):
        delta = _difference(candidate[index], control[index])
        rows.append({"frame": index, "t": round(index / FPS, 4),
                     "changed": round(delta["changed"], 6)})
    arrival = None
    for position, row in enumerate(rows):
        if row["changed"] < floor:
            continue
        run = rows[position:position + max(1, int(0.5 * FPS / step))]
        if all(entry["changed"] >= floor for entry in run):
            arrival = row
            break
    crossing_frame = int(round(CROSSING * FPS))
    report = {
        "window": [FINISH_FROM, round((FILM_FRAMES - 1) / FPS, 4)],
        "stride": step,
        "visible_floor": floor,
        "first_visible": arrival,
        "lead_seconds": (round(CROSSING - arrival["t"], 4)
                         if arrival else None),
        "at_crossing": next((r for r in rows
                             if r["frame"] >= crossing_frame), None),
        "max": max(rows, key=lambda r: r["changed"]),
        "rows": rows,
    }
    _write(os.path.join(DOCS, "finish.json"), report)
    if arrival:
        print(f"finish: first clearly visible at {arrival['t']:.3f} s "
              f"({arrival['changed'] * 100:.2f}% of frame), "
              f"{report['lead_seconds']:.3f} s before the winner crosses")
    else:
        print("finish: never reaches the visibility floor")
    return report


# --- stage: compare ---------------------------------------------------------


def _encode(frames: str, target: str, first: int, last: int,
            crf: int = 18) -> str:
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    _run([_tool("ffmpeg"), "-y", "-loglevel", "error",
          "-framerate", str(FPS), "-start_number", str(first),
          "-i", os.path.join(frames, "frame_%06d.png"),
          "-frames:v", str(last - first + 1),
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", str(crf),
          "-preset", "slow", "-movflags", "+faststart", target], "encode")
    return target


def _label(text: str, width: int, target: str) -> str:
    """One burnt-in caption, drawn with PIL rather than with `drawtext`.

    **`drawtext` is not available here and the failure is not obvious.** It
    needs fontconfig, and on this machine ffmpeg reports `Cannot load default
    config file` and exits 2 - a comparison that silently did not build. The
    project already owns a font resolver, `sloped.overlays.FONT_CANDIDATES`,
    and PIL draws the caption into a PNG that ffmpeg then overlays. One less
    dependency, and the captions match the film's own type.
    """
    from PIL import Image, ImageDraw
    from sloped import overlays

    size = max(14, width // 13)
    font = overlays.load_font(size)
    height = int(size * 1.9)
    plate = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(plate)
    box = draw.textbbox((0, 0), text, font=font)
    pad = size // 2
    left = (width - (box[2] - box[0])) // 2
    draw.rounded_rectangle(
        (left - pad, (height - (box[3] - box[1])) // 2 - pad - box[1] // 2,
         left + (box[2] - box[0]) + pad,
         (height + (box[3] - box[1])) // 2 + pad),
        radius=size // 3, fill=(0, 0, 0, 150))
    draw.text((left - box[0], (height - (box[3] - box[1])) // 2 - box[1]),
              text, font=font, fill=(255, 255, 255, 235))
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    plate.save(target)
    return target


def _side_by_side(left: str, right: str, target: str, label_left: str,
                  label_right: str, width: int) -> str:
    """Two films at the same instant, with a caption on each side.

    Scaled to a shared width and stacked horizontally, which for a 9:16 source
    is the only arrangement that keeps both readable. The sides are named
    because a comparison whose sides are not named is a comparison somebody
    will read backwards.
    """
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    height = int(round(width * 16.0 / 9.0))
    work = os.path.join(OUT, "compare", "labels")
    tag = os.path.splitext(os.path.basename(target))[0]
    plate_l = _label(label_left, width, os.path.join(work, f"{tag}_l.png"))
    plate_r = _label(label_right, width, os.path.join(work, f"{tag}_r.png"))
    graph = (
        f"[0:v]scale={width}:{height}:flags=lanczos[l0];"
        f"[1:v]scale={width}:{height}:flags=lanczos[r0];"
        f"[l0][2:v]overlay=0:{height // 40}[l];"
        f"[r0][3:v]overlay=0:{height // 40}[r];"
        f"[l][r]hstack=inputs=2[v]"
    )
    _run([_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", left, "-i", right,
          "-i", plate_l, "-i", plate_r,
          "-filter_complex", graph, "-map", "[v]",
          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
          "-preset", "slow", "-movflags", "+faststart", target], "side by side")
    return target


def stage_compare(args) -> dict[str, Any]:
    """Part L: five comparisons, all of them Test #3 beside Test #4."""
    candidate = MASTER_FRAMES
    control = CONTROL_FRAMES
    for folder in (candidate, control):
        if len(glob.glob(os.path.join(folder, "frame_*.png"))) != FILM_FRAMES:
            raise LabError(f"{folder} does not hold {FILM_FRAMES} frames")
    work = os.path.join(OUT, "compare")
    os.makedirs(work, exist_ok=True)
    os.makedirs(EXPORT, exist_ok=True)

    windows = {
        "opening": (0, int(round(3.0 * FPS)) - 1),
        "finish": (int(round(FINISH_FROM * FPS)), FILM_FRAMES - 1),
        "full": (0, FILM_FRAMES - 1),
    }
    made: dict[str, str] = {}
    for name, (first, last) in windows.items():
        left = _encode(control, os.path.join(work, f"test3_{name}.mp4"), first, last)
        right = _encode(candidate, os.path.join(work, f"test4_{name}.mp4"), first, last)
        made[f"{name}_1080"] = _side_by_side(
            left, right, os.path.join(EXPORT, f"compare_{name}_1080.mp4"),
            "TEST 3", "TEST 4", 540)
        if name in ("opening", "finish"):
            made[f"{name}_phone"] = _side_by_side(
                left, right, os.path.join(EXPORT, f"compare_{name}_270x480.mp4"),
                "TEST 3", "TEST 4", PHONE_SIZE[0])
    _write(os.path.join(DOCS, "compare.json"), made)
    for key, path in made.items():
        print(f"compare {key}: {path}")
    return made


# --- stage: sheets ----------------------------------------------------------


def stage_sheets(args) -> dict[str, Any]:
    """Part F: the phone review, at the size the watch time came from.

    Every tile carries its own frame index. V32's review found that decoding
    with `-vf fps=` returns frames that are not the ones it names, and a review
    sheet silently off by a few frames is a review of a film nobody is
    shipping; these are read straight off the PNG the renderer wrote, so the
    index is the renderer's own.
    """
    from PIL import Image

    os.makedirs(os.path.join(DOCS, "phone"), exist_ok=True)
    made = {}
    plans = {
        "opening": [0, 6, 9, 12, 15, 18, 24, 36, 60, 90, 120, 133],
        "finish": [int(round(t * FPS)) for t in
                   (13.0, 14.0, 15.0, 15.5, CROSSING, 16.2, 16.8, 17.4,
                    18.0, 18.6, 19.0, 19.15)],
    }
    for name, indices in plans.items():
        for label, folder in (("test4", MASTER_FRAMES), ("test3", CONTROL_FRAMES)):
            frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
            if len(frames) != FILM_FRAMES:
                continue
            columns, rows = 6, 2
            tile = (PHONE_SIZE[0] // 2, PHONE_SIZE[1] // 2)
            sheet = Image.new("RGB", (columns * tile[0], rows * tile[1]),
                              (12, 12, 14))
            for position, index in enumerate(indices[:columns * rows]):
                index = min(index, FILM_FRAMES - 1)
                with Image.open(frames[index]) as handle:
                    small = handle.convert("RGB").resize(tile, Image.LANCZOS)
                sheet.paste(small, ((position % columns) * tile[0],
                                    (position // columns) * tile[1]))
            path = os.path.join(DOCS, "phone", f"{name}_{label}.png")
            sheet.save(path)
            made[f"{name}_{label}"] = path
            print(f"sheet {name} {label}: {path}")
    _write(os.path.join(DOCS, "sheets.json"), made)
    return made


# --- stage: qc --------------------------------------------------------------


def _probe(path: str) -> dict[str, Any]:
    out = _run([_tool("ffprobe"), "-v", "error", "-print_format", "json",
                "-show_format", "-show_streams", path], "ffprobe")
    return json.loads(out)


def stage_qc(args) -> dict[str, Any]:
    """Every claim the report makes, re-measured on the delivered files."""
    checks: list[dict[str, Any]] = []

    def check(passed: bool, label: str, detail: Any = "") -> None:
        checks.append({"check": label, "pass": bool(passed),
                       "detail": detail})

    short = _read(os.path.join(DOCS, "short.json")) if os.path.isfile(
        os.path.join(DOCS, "short.json")) else {}
    spec = _read(SPEC)
    field = _read(FIELD)

    start = [s for s in spec["stands"] if s["id"] == "start"][0]
    finish = [s for s in spec["stands"] if s["id"] == "finish"][0]
    check(start["meta"]["bays"] == 8, "the start stand has eight bays",
          start["meta"]["bays"])
    check(start["motion"]["kind"] == "slide", "the gate is a moving group",
          start["motion"]["kind"])
    check(start["motion"]["starts"] == 0.1,
          "the gate starts on the physical release", start["motion"]["starts"])
    check(any(p["name"] == "line_inlay" for p in finish["static"]),
          "the finish line exists")
    check(any(p["name"].startswith("plaza_") for p in finish["static"]),
          "the run-out exists")
    check(finish["meta"]["well_parts"] > 0, "the catch pocket exists")
    check(field["well"] is not None
          and set(field["well"]["racers"]) >= {1, 7},
          "the pocket catches the racers the deck drops",
          field["well"]["racers"] if field["well"] else None)

    replay_path = _paths()[1]
    replay = _read(replay_path)
    check(replay["digest"].startswith("751031348936"),
          "the replay is the production one", replay["digest"][:16])

    source = _read(_paths()[2])
    for key in sorted(os.listdir(CAMERA_V33)):
        built = _read(os.path.join(CAMERA_V33, key,
                                   f"race2_{COURSE}_{SEED}.cameras.json"))
        same = all(json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
                   for a, b in zip(built["cuts"][1:], source["cuts"][1:]))
        check(same, f"camera {key}: the three later cuts are the shipped ones")

    for key, made in short.items():
        final = made["final"]
        if not os.path.isfile(final):
            check(False, f"{key}: the Short exists", final)
            continue
        probe = _probe(final)
        video = [s for s in probe["streams"] if s["codec_type"] == "video"][0]
        audio = [s for s in probe["streams"] if s["codec_type"] == "audio"]
        frames = int(video.get("nb_frames") or 0)
        check(frames == FILM_FRAMES, f"{key}: {FILM_FRAMES} frames", frames)
        check(video["width"] == DELIVERY[0] and video["height"] == DELIVERY[1],
              f"{key}: 1080x1920", [video["width"], video["height"]])
        check(bool(audio), f"{key}: carries a soundtrack")
        if audio:
            check(audio[0]["codec_name"] == "aac",
                  f"{key}: the soundtrack is the delivered AAC stream",
                  audio[0]["codec_name"])
        duration = float(probe["format"]["duration"])
        check(abs(duration - FILM_FRAMES / FPS) < 0.05,
              f"{key}: runtime {FILM_FRAMES / FPS:.4f} s", round(duration, 4))
        evidence = _read(made["evidence"])
        check(evidence["winner"]["label"] == "PINK",
              f"{key}: the winner is still PINK", evidence["winner"]["label"])
        check(evidence["winner"]["marble"] == 7,
              f"{key}: the winner is still m7")
        check([row["marble"] for row in evidence["winner"]["finish_order"]]
              == [7, 2, 1, 5, 3, 0, 6, 4],
              f"{key}: the finish order is the shipped one")
        check(evidence["hook"]["clearance"] > 0.0,
              f"{key}: the mark clears the racers",
              evidence["hook"]["clearance"])
        check(evidence["hook"]["racers_top"] > evidence["hook"]["band"][1],
              f"{key}: the mark's band is measured on THIS film's racers",
              [evidence["hook"]["racers_top"], evidence["hook"]["band"]])
        check(evidence["comeback"]["rank"] == 5,
              f"{key}: the payoff still says 5TH", evidence["comeback"]["rank"])
        check(evidence["hook"]["lines"] == made["lines"],
              f"{key}: the hook reads {' '.join(made['lines'])}")

    if os.path.isfile(SHIPPED):
        shipped = _probe(SHIPPED)
        theirs = [s for s in shipped["streams"] if s["codec_type"] == "audio"]
        for key, made in short.items():
            if not os.path.isfile(made["final"]):
                continue
            mine = [s for s in _probe(made["final"])["streams"]
                    if s["codec_type"] == "audio"]
            if mine and theirs:
                check(mine[0]["bit_rate"] == theirs[0]["bit_rate"]
                      and mine[0]["sample_rate"] == theirs[0]["sample_rate"]
                      and mine[0]["channels"] == theirs[0]["channels"],
                      f"{key}: the soundtrack matches V32.2 stream for stream")

    for name in ("middle", "finish", "metrics", "neutrality"):
        path = os.path.join(DOCS, f"{name}.json")
        if not os.path.isfile(path):
            continue
        report = _read(path)
        if name == "middle":
            check(report["identical_share"] >= 0.0,
                  "the middle report exists",
                  report["identical_share"])
        if name == "neutrality":
            check(report["identical"] == report["frames"],
                  "with no bookends this branch renders the base commit",
                  f"{report['identical']}/{report['frames']}")
        if name == "metrics":
            gain = report["opening"]["gain"]
            check(gain["diameter"] > 1.25,
                  "the racers are meaningfully larger at frame 0",
                  gain["diameter"])
            check(report["opening"]["test4"]["frame0"]["visible"] == 8,
                  "all eight racers are visible on frame 0")
        if name == "finish":
            check(report["first_visible"] is not None,
                  "the finish becomes visible before the crossing",
                  report.get("lead_seconds"))

    passed = sum(1 for c in checks if c["pass"])
    report = {"checks": checks, "passed": passed, "total": len(checks)}
    _write(os.path.join(DOCS, "qc.json"), report)
    for entry in checks:
        mark = "ok  " if entry["pass"] else "FAIL"
        print(f"  {mark} {entry['check']}"
              + (f"  [{entry['detail']}]" if entry["detail"] != "" else ""))
    print(f"qc: {passed}/{len(checks)} checks passing")
    return report


STAGES = {
    "field": stage_field,
    "spec": stage_spec,
    "camera": stage_camera,
    "hooks": stage_hooks,
    "master": stage_master,
    "control": stage_control,
    "metrics": stage_metrics,
    "short": stage_short,
    "neutrality": stage_neutrality,
    "middle": stage_middle,
    "finish": stage_finish,
    "compare": stage_compare,
    "sheets": stage_sheets,
    "qc": stage_qc,
}


# --- everything -------------------------------------------------------------


ALL = ("field", "spec", "camera", "hooks", "master", "control", "metrics",
       "middle", "finish", "short", "compare", "sheets", "neutrality", "qc")


def stage_all(args) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name in ALL:
        print(f"--- {name} ---")
        out[name] = STAGES[name](args)
    return out


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=tuple(STAGES) + ("all",))
    parser.add_argument("--godot", default="")
    parser.add_argument("--hook", default=WINNER,
                        help="which composition the full candidate uses")
    parser.add_argument("--text", default="both",
                        choices=("both", "your", "a"),
                        help="which hook wording to build")
    parser.add_argument("--base", default="157c818d4bbda65bf98ddc699b6dd8f9348295f4",
                        help="the production commit neutrality is proved against")
    parser.add_argument("--keep-worktree", dest="keep_worktree",
                        action="store_true")
    parser.add_argument("--stride", type=int, default=5,
                        help="how often to sample the middle and the finish")
    parser.add_argument("--measure-only", dest="measure_only",
                        action="store_true",
                        help="skip every render and re-run only the arithmetic")
    args = parser.parse_args(argv)
    if args.stage == "all":
        stage_all(args)
    else:
        STAGES[args.stage](args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LabError as error:
        print(f"v33: {error}", file=sys.stderr)
        raise SystemExit(1)
