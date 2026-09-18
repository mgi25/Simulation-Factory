"""V33.1: the post-finish run-out, laid along the track instead of across it.

One defect, one geometry change, and everything else held still.

## What was wrong

`race2.parts.RunOut` built its deck from `TrackRun.heading_deg(exit)` - which
is `atan2(x, z)` - by way of `(cos yaw, 0, -sin yaw)`, which is the forward
vector of `race2.kit.Frame.yaw`'s convention, `atan2(-z, x)`. The two are
ninety degrees apart at *every* heading: the dot product of `(sin h, 0, cos h)`
and `(cos h, 0, -sin h)` is identically zero. So the deck was laid across the
direction of travel. Its near edge lay along the racing line, its eight-unit
depth ran off to one side, and the eleven units the field was meant to run out
along were the eleven units it was meant to spread across.

The V33 replay says what that cost. Three of eight racers - including the
winner - left the machine within half a second of crossing:

    m7 crosses 15.8167 s, escapes 15.9292 s, frozen from 15.9667 s
    m1 crosses 16.1333 s, escapes 16.2375 s
    m4 crosses 18.7500 s, escapes 19.1792 s

A racer that escapes is retired: `MarbleSimulation._retire` zeroes its velocity
and removes it from the world, and the replay then repeats its last pose to the
end. The winner of Test #4 therefore hangs motionless in mid-air, 1.75 units
below the running surface, for the last 192 frames - 3.2 seconds - of a
19.17-second Short.

## What this lab does

`convention` proves the coordinate rule on cardinals and diagonals. `physics`
re-runs the hero seed and proves that nothing before the line moved. `field`
through `master` are V33's own stages, called rather than reimplemented, with
their paths repointed - so the candidate is V33's picture with one module's
geometry corrected and nothing else. `baseline` renders V33 from this same
worktree so the comparison is an A/B with one variable. `compare`, `sheets` and
`post` are the proofs.

Usage:

    python tools/race2_v331_runout.py convention
    python tools/race2_v331_runout.py physics
    python tools/race2_v331_runout.py all --godot=<path to Godot 4>
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

from race2 import courses, kit, opening
from sloped.scale import SIM_TO_LAYOUT

COURSE = "switchyard"
SEED = 8
FPS = 60

OUT = os.path.join("output", "race2", "v331_runout")
DOCS = os.path.join("docs", "validation", "race2", "v331_runout")
EXPORT = os.path.join("exports", "race2_v331_runout")

# The V33 film's own camera track, and the only thing in this lab that is
# copied from the shipped build rather than rebuilt: the brief locks the
# camera, so it is carried across byte for byte and `qc` says so.
V33_CAMERA = os.path.join("output", "race2", "v31_readability", "RB")

# Two input sets for the renderer, identical but for the one module. Each holds
# a replay, a geometry export and the *same* camera track.
SOURCE = os.path.join(OUT, "source")          # V33.1: the corrected deck
BASELINE = os.path.join(OUT, "baseline")      # V33: the deck as it shipped

FILM_FRAMES = 1150
FILM_SECONDS = 19.1500
CROSSING = 15.816667
FINISH_FROM = 12.683333
WINNER = 7
WINNER_LABEL = "PINK"
FINISH_ORDER = [7, 2, 1, 5, 3, 0, 6, 4]
# The eight crossing times the V33 replay records, which this pass must not
# move by a tick. Restated here so a test can read them without a 12.6 MB file.
CROSSINGS = {7: 15.816667, 2: 15.883333, 1: 16.133333, 5: 16.583333,
             3: 17.2, 0: 17.716667, 6: 17.816667, 4: 18.75}

PHONE_SIZE = (270, 480)
DELIVERY = (1080, 1920)


class LabError(RuntimeError):
    pass


def _run(command: Sequence[str], label: str) -> str:
    result = subprocess.run(list(command), cwd=REPO, capture_output=True,
                            text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        tail = "\n".join((result.stderr or result.stdout or "").splitlines()[-30:])
        raise LabError(f"{label} failed ({result.returncode}):\n{tail}")
    return result.stdout or ""


def _tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise LabError(f"{name} is not on PATH")
    return found


def _write(path: str, payload: Any) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1, sort_keys=True)
        handle.write("\n")
    return path


def _read(path: str) -> Any:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sha(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _names(folder: str) -> tuple[str, str, str]:
    stem = os.path.join(folder, f"race2_{COURSE}_{SEED}")
    return (f"{stem}.geometry.json", f"{stem}.replay.json", f"{stem}.cameras.json")


# --- the V33 lab, repointed -------------------------------------------------


def v33(camera: str, out: str, docs: str, export: str):
    """`tools/race2_v33_bookends.py` with its four path constants rebound.

    **Called, not reimplemented.** The field measurement, the bookends spec,
    the per-composition camera, the master render, the phone sheets and the
    Short are V33's, so a difference between the Test #4 candidate and this one
    can only come from the geometry underneath them. The constants below are
    module-level strings derived at import time from `OUT`/`DOCS`/`CAMERA`, so
    every one of them is rebound rather than just the three roots - a
    half-repointed module would write the candidate's spec into V33's own
    directory, which is the kind of mistake that is only visible afterwards.
    """
    spec = importlib.util.spec_from_file_location(
        "race2_v33_bookends", os.path.join(REPO, "tools", "race2_v33_bookends.py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules["race2_v33_bookends"] = module
    spec.loader.exec_module(module)

    module.CAMERA = camera
    module.OUT = out
    module.DOCS = docs
    module.EXPORT = export
    module.SPEC = os.path.join(out, "bookends.json")
    module.FIELD = os.path.join(docs, "field.json")
    module.CAMERA_V33 = os.path.join(out, "camera")
    module.MASTER_FRAMES = os.path.join(out, "frames", "master",
                                        f"clip_{COURSE}_{SEED}")
    module.CONTROL_FRAMES = os.path.join(out, "frames", "control",
                                         f"clip_{COURSE}_{SEED}")
    return module


def _lab(kind: str = "source"):
    if kind == "source":
        return v33(SOURCE, OUT, DOCS, EXPORT)
    return v33(BASELINE, os.path.join(OUT, "v33"),
               os.path.join(DOCS, "v33"), os.path.join(EXPORT, "v33"))


# --- stage: convention ------------------------------------------------------


CARDINALS = {
    "+X": (1.0, 0.0, 0.0),
    "-X": (-1.0, 0.0, 0.0),
    "+Z": (0.0, 0.0, 1.0),
    "-Z": (0.0, 0.0, -1.0),
}
DIAGONALS = {
    "+X+Z": (1.0, 0.0, 1.0),
    "+X-Z": (1.0, 0.0, -1.0),
    "-X-Z": (-1.0, 0.0, -1.0),
    "-X+Z": (-3.0, 0.0, 1.0),       # not 45 degrees: an arbitrary bearing
}


def _run_out_forward(forward: Sequence[float]) -> tuple[float, float, float]:
    """The deck's own +along axis for a run heading `forward`.

    Built through the real `RunOut` rather than by repeating its arithmetic: a
    test that re-derives the expression it is testing proves the expression is
    self-consistent and nothing else.
    """
    from race2.parts import RunOut

    return RunOut("probe", _StraightRun(forward)).forward


class _StraightRun:
    """The three attributes `RunOut` reads off a `TrackRun`, and no more.

    `RunOut.__init__` takes `path`, `tangents` and `scale`. A straight two-
    sample run on a given bearing is enough to ask "which way does the deck
    point?", and it lets the question be asked at bearings the switchyard
    course does not happen to contain.
    """

    def __init__(self, forward: Sequence[float]) -> None:
        unit = kit.flat_forward(forward)
        self.path = [(0.0, 0.0, 0.0), tuple(4.0 * c for c in unit)]
        self.tangents = [unit, unit]
        self.scale = 1.0


def stage_convention(args) -> dict[str, Any]:
    """The canonical direction test: does the deck point where the run does?

    For every bearing below, the deck's `forward` must be the run's own
    flattened tangent - `dot == 1`, not merely `dot > 0`. The old expression
    scored `dot == 0` at every one of them, which is why a test that only asked
    "is it roughly downhill?" would have passed the broken build too.
    """
    rows = []
    worst = 1.0
    for name, direction in list(CARDINALS.items()) + list(DIAGONALS.items()):
        want = kit.flat_forward(direction)
        got = _run_out_forward(direction)
        dot = sum(want[i] * got[i] for i in range(3))
        cross_y = want[2] * got[0] - want[0] * got[2]
        # What the shipped expression would have answered, for the record.
        heading = math.radians(kit.heading_from_forward(direction))
        old = (math.cos(heading), 0.0, -math.sin(heading))
        rows.append({
            "bearing": name,
            "heading_deg": round(kit.heading_from_forward(direction), 4),
            "build_yaw_deg": round(kit.build_yaw_from_forward(direction), 4),
            "want": [round(c, 9) for c in want],
            "got": [round(c, 9) for c in got],
            "dot": round(dot, 12),
            "cross_y": round(cross_y, 12),
            "error_deg": round(math.degrees(math.atan2(cross_y, dot)), 9),
            "old_forward": [round(c, 9) for c in old],
            "old_dot": round(sum(want[i] * old[i] for i in range(3)), 12),
        })
        worst = min(worst, dot)
    report = {
        "rule": ("heading_deg is atan2(x, z) and its forward is "
                 "(sin h, 0, cos h); Frame.yaw is atan2(-z, x) and its forward "
                 "is (cos y, 0, -sin y); build_yaw = heading - 90 exactly"),
        "worst_dot": round(worst, 12),
        "rows": rows,
    }
    _write(os.path.join(DOCS, "convention.json"), report)
    for row in rows:
        print(f"convention {row['bearing']:>5}: heading {row['heading_deg']:8.3f}  "
              f"dot {row['dot']:.9f}  (shipped expression: {row['old_dot']:+.9f})")
    print(f"  worst dot over {len(rows)} bearings: {worst:.12f}")
    return report


# --- stage: physics ---------------------------------------------------------


def _race(folder: str) -> None:
    """One hero race into `folder`, through the tool that made the V33 one."""
    os.makedirs(folder, exist_ok=True)
    _run([sys.executable, os.path.join("tools", "race2_camera.py"),
          f"--course={COURSE}", f"--seed={SEED}",
          f"--out={folder}", f"--docs={folder}"], f"race into {folder}")


def _install_camera(folder: str) -> None:
    """The V33 camera track, byte for byte, beside a replay.

    Copied rather than re-solved. `tools/race2_camera.py` writes a camera track
    of its own next to the replay and it is *not* the film's: the delivered
    picture is cut on the V31 readability pass's RB track, and the brief locks
    it. The solved one is overwritten here so that nothing downstream can pick
    it up by accident.
    """
    _geometry, _replay, cameras = _names(folder)
    shutil.copyfile(_names(V33_CAMERA)[2], cameras)


def stage_physics(args) -> dict[str, Any]:
    """The hero seed, before and after, and the proof that the race is the same.

    **The lock is stated per racer, at its own crossing.** "The frames before
    the winner crosses are identical" is true here but it is the weaker claim:
    five racers are still on the course at that instant, and a deck that had
    moved under them would show up later than frame 949 and pass. So the test
    below is that *each* marble's record is identical through the frame after
    its own line crossing - which is every tick of every racer's actual race.
    """
    baseline_replay = _names(BASELINE)[1]
    if not os.path.isfile(baseline_replay):
        raise LabError(
            f"the V33 replay is not at {baseline_replay}. Run\n"
            "  python tools/race2_v331_runout.py stash\n"
            "from a clean checkout of v33-mobile-race-bookends first, or copy "
            "the shipped one into place.")
    _race(SOURCE)
    _install_camera(SOURCE)

    base = _read(baseline_replay)
    fixed = _read(_names(SOURCE)[1])
    report = _compare_replays(base, fixed)
    _write(os.path.join(DOCS, "physics.json"), report)

    lock = report["lock"]
    print(f"physics: winner m{report['winner']} ({WINNER_LABEL}), order "
          f"{report['finish_order']}")
    print(f"  crossing times unchanged: {lock['crossings_identical']}")
    print(f"  events before the line:   {lock['events_before_line']} identical: "
          f"{lock['events_before_line_identical']}")
    print(f"  frames identical through: {lock['frames_identical_through']} "
          f"(t={lock['frames_identical_through'] / FPS:.4f})")
    for row in report["per_racer_lock"]:
        flag = "ok" if row["locked"] else "MOVED"
        print(f"  m{row['id']}: crossing f{row['crossing_frame']:4d}, identical "
              f"through f{row['identical_through']:4d}, worst drift before it "
              f"{row['worst_drift_before_crossing_sim']:.1f}  {flag}")
    print(f"  retired before the end - V33 {report['v33']['retired']}, "
          f"V33.1 {report['v331']['retired']}")
    return report


def _crossings(replay: dict) -> list[tuple[int, float, int]]:
    return [(int(e["id"]), round(float(e["t"]), 6), int(e["order"]))
            for e in replay["events"] if e["kind"] == "finish_line"]


def _retired(replay: dict) -> list[dict[str, Any]]:
    return [{"id": int(e["id"]), "kind": e["kind"], "t": round(float(e["t"]), 6)}
            for e in replay["events"] if e["kind"] in ("escaped", "finish")]


def _frozen_from(frames: list, marble: int, last: int) -> int | None:
    """The first frame from which a marble never moves again, or None.

    A retired racer repeats one pose to the end of the replay, and that is what
    "frozen" looks like from the outside. Read backwards from `last` so a
    marble that has genuinely come to rest on the deck is reported too - the
    difference between the two is whether it is resting on something, which
    `_supported` answers separately.
    """
    end = frames[last]["marbles"][marble]["p"]
    first = last
    for index in range(last, 0, -1):
        if frames[index - 1]["marbles"][marble]["p"] != end:
            return first
        first = index - 1
    return first


def _compare_replays(base: dict, fixed: dict) -> dict[str, Any]:
    a, b = base["frames"], fixed["frames"]
    crossings_a, crossings_b = _crossings(base), _crossings(fixed)
    order = [row[0] for row in crossings_b]

    before = CROSSING - 1e-9
    events_a = [e for e in base["events"] if e["t"] < before]
    events_b = [e for e in fixed["events"] if e["t"] < before]

    through = 0
    for index in range(min(len(a), len(b))):
        if a[index]["marbles"] != b[index]["marbles"]:
            break
        through = index

    # **The lock is "strictly before its own crossing", and the word matters.**
    # A racer's crossing frame is the frame it is *on* the line, and the winner
    # is already on the corrected deck by then: from frame 950 the two solvers
    # are integrating different contact sets, so every body in the island picks
    # up float noise whether or not anything touched it. m2 shows 0.004 layout
    # units - seven thousandths of a marble diameter - at frame 953, which is
    # its own crossing frame and not one tick earlier. Claiming identity *at*
    # the crossing would therefore be a claim about rounding; claiming it
    # everywhere before is a claim about the race, and that is the one that
    # holds for all eight.
    per_racer = []
    for marble in range(len(a[0]["marbles"])):
        identical = -1
        for index in range(min(len(a), len(b))):
            if a[index]["marbles"][marble] != b[index]["marbles"][marble]:
                break
            identical = index
        crossing = int(round(CROSSINGS[marble] * FPS))
        worst = 0.0
        for index in range(min(crossing, len(a), len(b))):
            worst = max(worst, math.dist(a[index]["marbles"][marble]["p"],
                                         b[index]["marbles"][marble]["p"]))
        per_racer.append({
            "id": marble,
            "crossing_frame": crossing,
            "crossing_time": CROSSINGS[marble],
            "identical_through": identical,
            "worst_drift_before_crossing_sim": round(worst, 12),
            "locked": identical >= crossing - 1 and worst == 0.0,
        })

    return {
        "winner": crossings_b[0][0],
        "winner_label": WINNER_LABEL,
        "finish_order": order,
        "crossings": {str(i): t for i, t, _o in crossings_b},
        "lock": {
            "crossings_identical": crossings_a == crossings_b,
            "winner_unchanged": crossings_b[0][0] == WINNER,
            "order_unchanged": order == FINISH_ORDER,
            "events_before_line": len(events_a),
            "events_before_line_identical": events_a == events_b,
            "frames_identical_through": through,
            "frame_count_unchanged": len(a) == len(b),
            "every_racer_locked_to_its_own_crossing":
                all(row["locked"] for row in per_racer),
            "worst_drift_before_any_crossing_sim":
                max(row["worst_drift_before_crossing_sim"] for row in per_racer),
        },
        "per_racer_lock": per_racer,
        "v33": {"retired": _retired(base),
                "digest": base["digest"], "event_digest": base["event_digest"]},
        "v331": {"retired": _retired(fixed),
                 "digest": fixed["digest"], "event_digest": fixed["event_digest"]},
    }


# --- stage: post ------------------------------------------------------------


def _deck():
    course = courses.build(COURSE)
    return course.machine.modules["runout"]


def _deck_local(deck, point: Sequence[float]) -> tuple[float, float, float]:
    """A simulation-unit world point in the deck's own (along, up, across)."""
    world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
    offset = [world[axis] - deck.origin[axis] for axis in range(3)]
    return (
        offset[0] * deck.forward[0] + offset[2] * deck.forward[2],
        offset[1],
        offset[0] * deck.across[0] + offset[2] * deck.across[2],
    )


def stage_post(args) -> dict[str, Any]:
    """Part P: what the field does after the line, measured in the deck's frame.

    **Supported is a height test against the deck the marble is over, not a
    box.** The deck falls `FALL_DEG` away from the line, so a fixed height band
    reports a racer several units out as floating by two hundredths; the
    surface is evaluated at the racer's own `along` and a racer counts as
    supported when its centre is within a tenth of a radius of resting on it.

    **Both builds are measured against V33.1's deck, and only some of the
    numbers survive that.** There is one course object here and it carries the
    corrected run-out, so `frames_on_deck` and `frames_outside_the_deck` for
    the V33 replay answer "where are V33's racers relative to V33.1's deck?",
    which is not a fact about V33. The figures that *are* build-independent -
    what the machine retired, and how many racer-frames repeat a single pose -
    are the ones to quote across the two, and `retired` and `frozen_frames`
    are those. The deck-relative counts are reported for V33.1, where the deck
    they are measured against is the one the racers are on.
    """
    from sloped import layout
    from marble3d.units import MARBLE_RADIUS

    deck = _deck()
    radius_layout = MARBLE_RADIUS * SIM_TO_LAYOUT
    fall = math.tan(math.radians(deck.FALL_DEG))
    half = 0.5 * deck.width

    def surface(along: float) -> float:
        return -fall * max(along, 0.0)

    rows: dict[str, Any] = {}
    for name, folder in (("v33", BASELINE), ("v331", SOURCE)):
        replay = _read(_names(folder)[1])
        frames = replay["frames"]
        last = FILM_FRAMES - 1
        racers = []
        unsupported_total = 0
        for marble in range(len(frames[0]["marbles"])):
            crossing = int(round(CROSSINGS[marble] * FPS))
            on_deck = 0
            supported = 0
            outside = 0
            travelled = 0.0
            peak = 0.0
            window = range(crossing, last + 1)
            for index in window:
                along, up, across = _deck_local(deck, frames[index]["marbles"][marble]["p"])
                peak = max(peak, along)
                inside = (-radius_layout <= along <= deck.DEPTH + deck.CATCH
                          and abs(across) <= half + radius_layout)
                if inside:
                    on_deck += 1
                    if abs(up - (surface(along) + radius_layout)) <= 0.1 * radius_layout:
                        supported += 1
                else:
                    outside += 1
            end = _deck_local(deck, frames[last]["marbles"][marble]["p"])
            velocity = frames[last]["marbles"][marble].get("v") or (0.0, 0.0, 0.0)
            frozen = _frozen_from(frames, marble, last)
            racers.append({
                "id": marble,
                "crossing_frame": crossing,
                "frames_after_crossing": len(window),
                "frames_on_deck": on_deck,
                "frames_supported": supported,
                "frames_outside_the_deck": outside,
                "forward_travel": round(peak, 4),
                "final_local": [round(v, 4) for v in end],
                "final_speed": round(math.dist(velocity, (0.0, 0.0, 0.0)), 4),
                "still_moving_at_the_last_frame": frozen is None or frozen >= last,
                "frozen_from_frame": None if frozen is None or frozen >= last else frozen,
                "frozen_frames": 0 if frozen is None or frozen >= last else last - frozen,
            })
            unsupported_total += outside
        rows[name] = {
            "racers": racers,
            "measured_against": "v331 deck",
            "deck_relative_figures_are_meaningful": name == "v331",
            "unsupported_frames": unsupported_total,
            "retired": _retired(replay),
            "frozen": [r["id"] for r in racers if r["frozen_frames"]],
            "frozen_frames": sum(r["frozen_frames"] for r in racers),
        }

    winner = {
        name: next(r for r in rows[name]["racers"] if r["id"] == WINNER)
        for name in rows
    }
    report = {
        "deck": {
            "origin": [round(c, 4) for c in deck.origin],
            "forward": [round(c, 6) for c in deck.forward],
            "across": [round(c, 6) for c in deck.across],
            "depth": deck.DEPTH, "width": deck.width,
            "rim": deck.RIM, "fall_deg": deck.FALL_DEG, "catch": deck.CATCH,
            "floor_y": layout.FLOOR_Y,
        },
        "window": [int(round(CROSSING * FPS)), FILM_FRAMES - 1],
        "by_build": rows,
        "winner": winner,
    }
    _write(os.path.join(DOCS, "post_finish.json"), report)
    for name in ("v33", "v331"):
        block = rows[name]
        deck_note = "" if name == "v331" else " (against V33.1's deck)"
        print(f"post {name}: {block['unsupported_frames']} racer-frames off "
              f"the deck{deck_note}, {block['frozen_frames']} frozen "
              f"racer-frames, retired {[r['id'] for r in block['retired']]}")
        w = winner[name]
        print(f"  winner m{WINNER}: travelled {w['forward_travel']:.2f} forward, "
              f"supported {w['frames_supported']}/{w['frames_after_crossing']}, "
              f"ends at {w['final_local']} at {w['final_speed']:.2f}")
    return report


# --- stage: visibility ------------------------------------------------------


def _camera_rows() -> dict[int, list]:
    """The locked track, by frame index. The film's camera, not a solved one."""
    track = _read(_names(SOURCE)[2])
    rows: dict[int, list] = {}
    for cut in track["cuts"]:
        for row in cut["frames"]:
            rows[int(round(float(row[0]) * FPS))] = row
    return rows


RACER_LEVELS = tuple(int(round(255.0 * index / 7.0)) for index in range(8))


def _matte_racers(path: str) -> dict[int, int]:
    """Racer index -> pixel count, from a `--track=racers` frame.

    **The red byte is a level, not an index.** `race2_track_surface.racer_class`
    writes `round(255 * index / (count - 1))`, so eight racers land on 0, 36,
    73, 109, 146, 182, 219 and 255. Reading the byte as the racer number - which
    is what a first pass at this did - reports the winner as invisible in every
    frame of every build, including the ones where it is plainly on screen.
    """
    import numpy as np
    from PIL import Image

    with Image.open(path) as handle:
        frame = np.asarray(handle.convert("RGB"), dtype=np.uint8)
    flag = frame[:, :, 1] > 96
    if not flag.any():
        return {}
    red = frame[:, :, 0].astype(int)
    out: dict[int, int] = {}
    for index, level in enumerate(RACER_LEVELS):
        count = int((flag & (np.abs(red - level) <= 8)).sum())
        if count >= 12:
            out[index] = count
    return out


def stage_visibility(args) -> dict[str, Any]:
    """Is the winner still on screen after it crosses? Two instruments.

    **A frustum count is not visibility, and this pass needed both.** The
    projection below says whether a racer's centre is inside the camera's
    frame; it knows nothing about the geometry in front of it. The matte is a
    render of the same frames with every racer painted as a flat class, so a
    racer hidden behind a parapet counts as hidden. They are reported side by
    side, and a gap between them is an occlusion.

    This is the measurement that sent V33.1 back for a second geometry change.
    Rotating the deck alone put the field eight units past the line, and the
    finish shot's own reach shrinks to about 4.3 units by the end of the film -
    so the corrected run-out parked the whole field, winner included, behind
    the picture.
    """
    rows = _camera_rows()
    replays = {name: _read(_names(folder)[1])
               for name, folder in (("v33", BASELINE), ("v331", SOURCE))}
    start = int(round(CROSSING * FPS))
    report: dict[str, Any] = {"window": [start, FILM_FRAMES - 1], "by_build": {}}

    for name, replay in replays.items():
        frustum = {index: 0 for index in range(8)}
        frames = 0
        for frame in range(start, FILM_FRAMES):
            row = rows.get(frame)
            if row is None:
                continue
            frames += 1
            points = [[float(c) * SIM_TO_LAYOUT for c in
                       replay["frames"][frame]["marbles"][index]["p"]]
                      for index in range(8)]
            for index, (x, y, depth) in enumerate(
                    opening.screen(points, row[1:4], row[4:7], row[7])):
                if depth > 0.0 and abs(x) <= 1.0 and abs(y) <= 1.0:
                    frustum[index] += 1
        report["by_build"][name] = {
            "frames": frames,
            "in_frustum": frustum,
            "winner_in_frustum": frustum[WINNER],
        }

    for name in ("v33", "v331"):
        folder = os.path.join(OUT, "matte", name, f"clip_{COURSE}_{SEED}")
        made = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
        if not made:
            continue
        counts = [_matte_racers(path) for path in made]
        block = report["by_build"][name]
        block["matte_frames"] = len(counts)
        block["matte_first_frame"] = int(round(MATTE_FROM * FPS))
        block["winner_on_screen"] = sum(1 for row in counts if WINNER in row)
        block["mean_racers_on_screen"] = round(
            sum(len(row) for row in counts) / max(len(counts), 1), 3)
        block["empty_frames"] = sum(1 for row in counts if not row)
        block["winner_pixels"] = [row.get(WINNER, 0) for row in counts]

    _write(os.path.join(DOCS, "visibility.json"), report)
    for name in ("v33", "v331"):
        block = report["by_build"][name]
        line = (f"visibility {name}: winner in frustum "
                f"{block['winner_in_frustum']}/{block['frames']}")
        if "winner_on_screen" in block:
            line += (f", on screen in the matte {block['winner_on_screen']}"
                     f"/{block['matte_frames']}, mean racers "
                     f"{block['mean_racers_on_screen']}")
        print(line)
    return report


MATTE_FROM = 15.0


def stage_matte(args) -> dict[str, Any]:
    """The racer segmentation pass over the finish, for both builds."""
    made = {}
    for name, folder, root in (("v331", SOURCE, OUT),
                               ("v33", BASELINE, os.path.join(OUT, "v33"))):
        spec = os.path.join(root, "bookends.json")
        camera = os.path.join(root, "camera", args.hook)
        target = os.path.join(OUT, "matte", name)
        command = [sys.executable, os.path.join("tools", "race2_render.py"),
                   "clip", "--track=racers", f"--start={MATTE_FROM:.4f}",
                   f"--end={FILM_SECONDS:.4f}", f"--bookends={spec}",
                   f"--course={COURSE}", f"--seed={SEED}", f"--out={camera}",
                   f"--frames={target}", "--environment=contained_bay_v301",
                   "--faces=both"]
        _run(command, f"matte {name}")
        made[name] = os.path.join(target, f"clip_{COURSE}_{SEED}")
        print(f"matte {name}: {made[name]}")
    return made


# --- stage: stash -----------------------------------------------------------


def stage_stash(args) -> dict[str, Any]:
    """The V33 replay and geometry, put where `physics` looks for them.

    The shipped pair is not in git - `output/` is ignored - so this stage
    rebuilds them from whichever commit is checked out. Run it *before* the
    fix if you have a clean tree; otherwise `--from` names a directory that
    already holds them.
    """
    os.makedirs(BASELINE, exist_ok=True)
    if args.source:
        for path in _names(args.source)[:2]:
            shutil.copyfile(path, os.path.join(BASELINE, os.path.basename(path)))
    else:
        _race(BASELINE)
    _install_camera(BASELINE)
    made = {name: _sha(name) for name in _names(BASELINE)}
    _write(os.path.join(DOCS, "baseline.json"), {"files": made})
    for name, digest in made.items():
        print(f"stash {os.path.basename(name)}: {digest[:16]}")
    return {"files": made}


# --- stage: geometry --------------------------------------------------------


def stage_geometry(args) -> dict[str, Any]:
    """Which modules moved, by name, in the renderer's own export.

    The brief's "smallest correction" claim, stated as a diff rather than as a
    description: every run, every station and the start must be byte-identical
    between the two geometry exports, and `runout` must be the only entry that
    is not.
    """
    base = _read(_names(BASELINE)[0])
    fixed = _read(_names(SOURCE)[0])
    changed = [key for key in sorted(base) if base[key] != fixed.get(key)]
    modules_a = {m["id"]: m for m in base["modules"]}
    modules_b = {m["id"]: m for m in fixed["modules"]}
    moved = [mid for mid in modules_a if modules_a[mid] != modules_b.get(mid)]
    report = {
        "top_level_changed": changed,
        "modules_changed": moved,
        "modules_unchanged": [mid for mid in modules_a if mid not in moved],
        "runs_identical": base["runs"] == fixed["runs"],
        "start_identical": base["start"] == fixed["start"],
        "actuators_identical": base["actuators"] == fixed["actuators"],
        "only_the_runout_moved": moved == ["runout"] and changed == ["modules"],
    }
    _write(os.path.join(DOCS, "geometry.json"), report)
    print(f"geometry: modules changed {moved}; runs identical "
          f"{report['runs_identical']}; only the run-out moved "
          f"{report['only_the_runout_moved']}")
    return report


# --- rendering --------------------------------------------------------------


def _godot_arg(args) -> list[str]:
    return [f"--godot={args.godot}"] if args.godot else []


def stage_field(args) -> dict[str, Any]:
    return _lab("source").stage_field(args)


def stage_spec(args) -> dict[str, Any]:
    return _lab("source").stage_spec(args)


def stage_camera(args) -> dict[str, Any]:
    return _lab("source").stage_camera(args)


def stage_master(args) -> dict[str, Any]:
    """The V33.1 candidate picture: 1150 frames, corrected deck."""
    return _lab("source").stage_master(args)


# The bookends V33 shipped, and its digest as V33's own `spec.json` and commit
# message record it. Not in git - see the project note on `output/` - so its
# absence is reported rather than worked around.
V33_SPEC = os.path.join(REPO, "..", "wt-v33-bookends", "output", "race2",
                        "v33_bookends", "bookends.json")
V33_SPEC_SHA = "d9db6d351c8a9190"


def _v33_spec(target: str) -> str:
    """V33's built bookends, copied and checked against its recorded digest.

    **Not recomputed.** `field_from_report` reads `surface_up` and
    `surface_fall` off the *deck*, which this branch has corrected, and the
    envelope off the *replay*, which the control has not. Rebuilding the
    control's spec here would therefore produce a hybrid that V33 never
    shipped - a plaza sited on V33's field at V33.1's deck height - and the
    A/B would have two variables in it. The shipped file is copied instead and
    its digest is checked, which is the same argument `_shipped_audio` makes
    about the soundtrack.
    """
    if not os.path.isfile(V33_SPEC):
        raise LabError(
            "V33's built bookends are not at\n  " + V33_SPEC
            + "\nThey are the control for every comparison in this pass "
              "and they are not in git; see the project note on output/.")
    digest = hashlib.sha256(
        json.dumps(_read(V33_SPEC), sort_keys=True).encode("utf-8")).hexdigest()
    if not digest.startswith(V33_SPEC_SHA):
        raise LabError(f"{V33_SPEC} hashes {digest[:16]}, not {V33_SPEC_SHA}; "
                       "that is not the spec V33 shipped")
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    shutil.copyfile(V33_SPEC, target)
    return target


def stage_baseline(args) -> dict[str, Any]:
    """The V33 picture, rendered here, as the control for every comparison.

    **Not the shipped MP4.** A side-by-side against a file built on another
    branch on another day compares an encode as much as a picture. This renders
    Test #4's own frames from Test #4's own replay, geometry, camera track and
    bookends in this worktree, so the only difference between the two masters
    is the geometry of one module.
    """
    lab = _lab("baseline")
    _v33_spec(lab.SPEC)
    lab.stage_camera(args)
    return lab.stage_master(args)


def _frames(kind: str) -> str:
    root = OUT if kind == "source" else os.path.join(OUT, "v33")
    return os.path.join(root, "frames", "master", f"clip_{COURSE}_{SEED}")


# --- stage: compare ---------------------------------------------------------


COMPARE_AT = {
    "approach": CROSSING - 0.75,
    "crossing": CROSSING,
    "plus_0_2": CROSSING + 0.2,
    "plus_0_5": CROSSING + 0.5,
    "plus_1_0": CROSSING + 1.0,
    "payoff": 17.5,
    "final": (FILM_FRAMES - 1) / FPS,
}


def stage_compare(args) -> dict[str, Any]:
    """The seven instants the brief names, V33 beside V33.1, plus three clips."""
    lab = _lab("source")
    candidate, control = _frames("source"), _frames("baseline")
    for folder in (candidate, control):
        if len(glob.glob(os.path.join(folder, "frame_*.png"))) != FILM_FRAMES:
            raise LabError(f"{folder} does not hold {FILM_FRAMES} frames")
    os.makedirs(EXPORT, exist_ok=True)
    work = os.path.join(OUT, "compare")
    os.makedirs(work, exist_ok=True)
    lab.OUT = OUT       # `_side_by_side` writes its caption plates under OUT

    windows = {
        "finish": (int(round(FINISH_FROM * FPS)), FILM_FRAMES - 1),
        "sprint": (int(round((CROSSING - 2.5) * FPS)), FILM_FRAMES - 1),
        "full": (0, FILM_FRAMES - 1),
    }
    made: dict[str, str] = {}
    for name, (first, last) in windows.items():
        left = lab._encode(control, os.path.join(work, f"v33_{name}.mp4"), first, last)
        right = lab._encode(candidate, os.path.join(work, f"v331_{name}.mp4"), first, last)
        made[f"{name}_v33"] = left
        made[f"{name}_v331"] = right
        made[f"{name}_1080"] = lab._side_by_side(
            left, right, os.path.join(EXPORT, f"compare_{name}_1080.mp4"),
            "V33", "V33.1", 540)
        if name == "finish":
            made[f"{name}_phone"] = lab._side_by_side(
                left, right, os.path.join(EXPORT, f"compare_{name}_270x480.mp4"),
                "V33", "V33.1", PHONE_SIZE[0])
    made["final_sprint"] = shutil.copyfile(
        made["sprint_v331"], os.path.join(EXPORT, "final_sprint_v331.mp4"))
    _write(os.path.join(DOCS, "compare.json"), made)
    for key, path in sorted(made.items()):
        print(f"compare {key}: {path}")
    return made


# --- stage: sheets ----------------------------------------------------------


def stage_sheets(args) -> dict[str, Any]:
    """The finish comparison sheet: seven instants, V33 over V33.1.

    Two rows of tiles at the delivered aspect, each tile carrying the frame
    index the renderer wrote, and a 270x480 edition of the same sheet - the
    size the watch time came from, and the size at which "is the winner still
    on screen?" is actually decided.
    """
    from PIL import Image, ImageDraw
    from sloped import overlays

    candidate, control = _frames("source"), _frames("baseline")
    rows = [("V33", control), ("V33.1", candidate)]
    made: dict[str, Any] = {}
    for tag, width in (("1080", 300), ("phone", PHONE_SIZE[0] // 2)):
        height = int(round(width * DELIVERY[1] / DELIVERY[0]))
        pad = max(4, width // 40)
        head = max(18, width // 9)
        sheet = Image.new("RGB",
                          (pad + len(COMPARE_AT) * (width + pad),
                           head + len(rows) * (height + head + pad)),
                          (16, 16, 18))
        draw = ImageDraw.Draw(sheet)
        font = overlays.load_font(max(11, width // 18))
        for row, (label, folder) in enumerate(rows):
            top = head + row * (height + head + pad)
            for column, (name, when) in enumerate(COMPARE_AT.items()):
                index = min(FILM_FRAMES - 1, max(0, int(round(when * FPS))))
                path = os.path.join(folder, f"frame_{index:06d}.png")
                if not os.path.isfile(path):
                    raise LabError(f"missing {path}")
                with Image.open(path) as handle:
                    tile = handle.convert("RGB").resize((width, height),
                                                        Image.LANCZOS)
                left = pad + column * (width + pad)
                sheet.paste(tile, (left, top))
                draw.text((left, top - head + 2),
                          f"{label}  {name}  f{index}", font=font,
                          fill=(238, 238, 240))
        target = os.path.join(DOCS, f"finish_compare_{tag}.png")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        sheet.save(target)
        made[tag] = target
        print(f"sheet {tag}: {target} ({sheet.size[0]}x{sheet.size[1]})")
    _write(os.path.join(DOCS, "sheets.json"), made)
    return made


# --- stage: short -----------------------------------------------------------


def stage_short(args) -> dict[str, Any]:
    """The upload candidate: V33's marks and V32.2's sound over this picture."""
    lab = _lab("source")
    made = lab.stage_short(args)
    renamed: dict[str, Any] = {}
    for key, block in made.items():
        for field in ("final", "phone"):
            old = block[field]
            new = old.replace("_v33_", "_v331_")
            if old != new and os.path.isfile(old):
                shutil.move(old, new)
                block[field] = new
        renamed[key] = block
        print(f"short {key}: {block['final']}")
    _write(os.path.join(DOCS, "short.json"), renamed)
    return renamed


# --- stage: qc --------------------------------------------------------------


def stage_qc(args) -> dict[str, Any]:
    """Every lock the brief names, answered from a file rather than from memory."""
    report: dict[str, Any] = {}

    physics = _read(os.path.join(DOCS, "physics.json"))
    report["physics"] = physics["lock"]
    report["winner"] = physics["winner"]
    report["finish_order"] = physics["finish_order"]

    cameras = {
        "v33": _sha(_names(V33_CAMERA)[2]),
        "source": _sha(_names(SOURCE)[2]),
        "baseline": _sha(_names(BASELINE)[2]),
    }
    report["camera"] = {
        "sha256": cameras,
        "identical": len(set(cameras.values())) == 1,
    }

    shipped = os.path.join(
        REPO, "..", "wt-v322-audio", "exports", "race2_v322_audio",
        "race2_switchyard_final_audio.mp4")
    report["audio"] = {"source": shipped, "present": os.path.isfile(shipped)}
    if os.path.isfile(shipped):
        # **The elementary stream, not the container.** Two MP4s built at
        # different times differ in their headers whatever the audio is doing,
        # so the AAC is demuxed to raw ADTS and hashed. Equal digests here mean
        # no encoder has touched the soundtrack between V32.2 and this film.
        report["audio"]["adts_sha256"] = {
            name: _audio_digest(path)
            for name, path in (("v322_shipped", shipped),) + _delivered_films()
        }
        digests = set(report["audio"]["adts_sha256"].values())
        report["audio"]["identical_to_v322"] = len(digests) == 1
    short = os.path.join(DOCS, "short.json")
    if os.path.isfile(short):
        made = _read(short)
        streams = {}
        for key, block in made.items():
            probe = _run([_tool("ffprobe"), "-v", "error", "-show_entries",
                          "stream=codec_type,codec_name,nb_frames,duration,"
                          "sample_rate,channels", "-of", "json", block["final"]],
                         f"probe {key}")
            streams[key] = json.loads(probe)["streams"]
        report["delivered"] = streams

    candidate, control = _frames("source"), _frames("baseline")
    counts = {name: len(glob.glob(os.path.join(folder, "frame_*.png")))
              for name, folder in (("v331", candidate), ("v33", control))}
    report["frames"] = counts
    report["runtime_seconds"] = round(FILM_FRAMES / FPS, 6)

    if all(value == FILM_FRAMES for value in counts.values()):
        report["picture"] = _picture_lock(control, candidate)

    _write(os.path.join(DOCS, "qc.json"), report)
    print(f"qc: winner m{report['winner']}, order {report['finish_order']}")
    print(f"  camera track identical across all three inputs: "
          f"{report['camera']['identical']}")
    print(f"  frames {counts}, runtime {report['runtime_seconds']} s")
    if "picture" in report:
        block = report["picture"]
        print(f"  identical through frame {block['identical_through']} "
              f"(t={block['identical_seconds']:.4f} s); first difference at "
              f"{block['first_difference']}")
        for cut in block["by_cut"]:
            print(f"    cut {cut['name']:<8} {cut['seconds'][0]:6.2f}-"
                  f"{cut['seconds'][1]:6.2f} s: {cut['frames_differing']:4d}"
                  f"/{cut['frames_total']} frames differ, worst "
                  f"{cut['worst_changed'] * 100:7.4f}% of frame, box "
                  f"{cut['box']}")
    return report


def _delivered_films() -> tuple:
    """The films this pass has muxed, by tag, for the audio comparison."""
    short = os.path.join(DOCS, "short.json")
    if not os.path.isfile(short):
        return ()
    return tuple((f"v331_{key}", block["final"])
                 for key, block in _read(short).items()
                 if os.path.isfile(block["final"]))


def _audio_digest(path: str) -> str:
    """The AAC elementary stream of a film, hashed."""
    work = os.path.join(OUT, "audio")
    os.makedirs(work, exist_ok=True)
    target = os.path.join(
        work, os.path.splitext(os.path.basename(path))[0] + ".aac")
    _run([_tool("ffmpeg"), "-y", "-loglevel", "error", "-i", path,
          "-vn", "-c:a", "copy", "-f", "adts", target], f"demux {path}")
    return _sha(target)


def _picture_lock(control: str, candidate: str) -> dict[str, Any]:
    """Where the two films first differ as pixels, and how the difference grows.

    The start and middle regressions, answered by file digest rather than by a
    difference metric: a byte-identical PNG is the strongest statement that a
    frame did not move.

    **The first difference is before the crossing, and that is correct.** The
    corrected run-out and the plaza that follows it are *scenery*, and scenery
    enters frame before the racer that is running toward it does - at 15.367 s,
    0.45 s ahead of the winner. The replay is byte-identical for every racer
    through frame 949, and the camera track is the same file, so nothing on
    screen at 15.367 s can be a racer in a different place. The ramp below is
    what that looks like: a hundred pixels at the frame edge, then the plaza
    arriving.
    """
    import numpy as np
    from PIL import Image

    first = None
    identical = -1
    for index in range(FILM_FRAMES):
        left = os.path.join(control, f"frame_{index:06d}.png")
        right = os.path.join(candidate, f"frame_{index:06d}.png")
        if _sha(left) != _sha(right):
            first = index
            break
        identical = index

    def ramp(index: int) -> dict[str, Any]:
        pair = [np.asarray(Image.open(os.path.join(folder,
                                                   f"frame_{index:06d}.png")
                                      ).convert("RGB"), dtype=np.int16)
                for folder in (control, candidate)]
        delta = np.abs(pair[0] - pair[1]).max(axis=2)
        mask = delta > 6
        box = None
        if mask.any():
            ys, xs = np.nonzero(mask)
            box = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        return {"frame": index, "t": round(index / FPS, 4),
                "changed": round(float(mask.mean()), 6),
                "max_channel_delta": int(delta.max()), "box": box}

    # **The budget, per camera cut.** "Before the winner crosses" is the wrong
    # window to quote: the final chase is on screen from 12.68 s and the
    # corrected receiving architecture is *supposed* to be in it, so a single
    # number over everything up to 15.82 s mixes the thing this pass is for
    # with the thing it must not touch. Per cut separates them: the start, the
    # upper chase and the middle are the shots the brief locks, and the final
    # chase is the shot the run-out is in.
    crossing_frame = int(round(CROSSING * FPS))
    cuts = []
    for cut in _read(_names(SOURCE)[2])["cuts"]:
        lo = int(round(float(cut["from"]) * FPS))
        hi = min(FILM_FRAMES - 1, int(round(float(cut["to"]) * FPS)))
        rows = [ramp(index) for index in range(max(lo, 0), hi + 1)
                if first is not None and index >= first]
        hot = [row for row in rows if row["changed"] > 0.0]
        cuts.append({
            "name": cut["name"],
            "frames": [lo, hi],
            "seconds": [round(lo / FPS, 4), round(hi / FPS, 4)],
            "frames_differing": len(hot),
            "frames_total": hi - lo + 1,
            "worst_changed": round(max((row["changed"] for row in hot),
                                       default=0.0), 6),
            "worst_channel_delta": max((row["max_channel_delta"]
                                        for row in hot), default=0),
            "box": ([min(row["box"][0] for row in hot),
                     min(row["box"][1] for row in hot),
                     max(row["box"][2] for row in hot),
                     max(row["box"][3] for row in hot)] if hot else None),
        })

    marks = [] if first is None else [
        ramp(index) for index in
        sorted({first, first + 3, first + 8, first + 18,
                int(round(CROSSING * FPS)), FILM_FRAMES - 1})
        if index < FILM_FRAMES]
    return {
        "frame_zero_identical": first != 0,
        "identical_through": identical,
        "identical_seconds": round(identical / FPS, 4),
        "first_difference": first,
        "first_difference_seconds": None if first is None else round(first / FPS, 4),
        "winner_crossing_frame": int(round(CROSSING * FPS)),
        "difference_is_scenery_not_racers": (
            first is None or first < int(round(CROSSING * FPS))),
        "by_cut": cuts,
        "ramp": marks,
    }


# --- everything -------------------------------------------------------------


STAGES = {
    "convention": stage_convention,
    "stash": stage_stash,
    "physics": stage_physics,
    "geometry": stage_geometry,
    "post": stage_post,
    "matte": stage_matte,
    "visibility": stage_visibility,
    "field": stage_field,
    "spec": stage_spec,
    "camera": stage_camera,
    "master": stage_master,
    "baseline": stage_baseline,
    "compare": stage_compare,
    "sheets": stage_sheets,
    "short": stage_short,
    "qc": stage_qc,
}

ALL = ("convention", "physics", "geometry", "post", "field", "spec", "camera",
       "master", "baseline", "matte", "visibility", "compare", "sheets",
       "short", "qc")


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
    parser.add_argument("--hook", default="C",
                        help="which opening composition the candidate uses")
    parser.add_argument("--text", default="your",
                        choices=("both", "your", "a"))
    parser.add_argument("--source", default="",
                        help="stash: a directory that already holds the V33 pair")
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--base", default="")
    parser.add_argument("--keep-worktree", dest="keep_worktree",
                        action="store_true")
    parser.add_argument("--measure-only", dest="measure_only",
                        action="store_true")
    args = parser.parse_args(argv)
    if args.godot:
        os.environ.setdefault("GODOT_BIN", args.godot)
    if args.stage == "all":
        stage_all(args)
    else:
        STAGES[args.stage](args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LabError as error:
        print(f"v331: {error}", file=sys.stderr)
        raise SystemExit(1)
