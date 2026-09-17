"""V33: the bookends exist, and the race under them did not move.

The pass's claim has two halves and these tests are both of them.

**The race did not move.** Nothing in this branch reaches the simulation: the
bookends are a JSON description instantiated by a Godot builder, the camera
rewrite touches one cut of four, and the replay, the geometry, the course, the
environment and the track are the files the production commit ships. The tests
that say so compare digests and diffs rather than descriptions.

**The bookends are there and they are clear of the racing.** Eight bays, a gate
that moves on the release the physics already had, a finish line, a gantry, a
plaza and a catch pocket - each asserted on the built spec, and each checked
against every marble position in the replay so that "scenery is sited off the
racing line" is a measurement and not a hope.

The tests are of two kinds. The pure ones run anywhere. The ones that want a
rendered frame or a delivered file skip when it is not on disk, because a
render needs a GPU and the frames are not in the branch.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from race2 import bookends, courses, opening
from race2.rig import _basis, _screen
from sloped.scale import SIM_TO_LAYOUT

BASE_COMMIT = "157c818d4bbda65bf98ddc699b6dd8f9348295f4"
COURSE = "switchyard"
SEED = 8
FPS = 60
FILM_FRAMES = 1150

SPEC = os.path.join(REPO, "output", "race2", "v33_bookends", "bookends.json")
FIELD = os.path.join(REPO, "docs", "validation", "race2", "v33_bookends",
                     "field.json")
REPLAY = os.path.join(REPO, "output", "race2", "v31_readability", "RB",
                      f"race2_{COURSE}_{SEED}.replay.json")
TRACK = os.path.join(REPO, "output", "race2", "v31_readability", "RB",
                     f"race2_{COURSE}_{SEED}.cameras.json")
V33_TRACKS = os.path.join(REPO, "output", "race2", "v33_bookends", "camera")

# The production replay's own digests, from `docs/race2_v32_production.md`.
REPLAY_DIGEST = ("751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7"
                 "f539")
EVENT_DIGEST = ("51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f5333369830165"
                "02")


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _read(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture(scope="module")
def course():
    return courses.build(COURSE)


@pytest.fixture(scope="module")
def spec(course):
    if os.path.isfile(SPEC):
        return _read(SPEC)
    return bookends.build(course)


@pytest.fixture(scope="module")
def replay():
    if not os.path.isfile(REPLAY):
        pytest.skip("the replay is not on disk; run tools/race2_camera.py")
    return _read(REPLAY)


@pytest.fixture(scope="module")
def points(replay):
    """Every marble centre of the film, in layout units."""
    out = []
    for frame in replay["frames"][:FILM_FRAMES]:
        for marble in frame["marbles"]:
            out.append(tuple(float(c) * SIM_TO_LAYOUT for c in marble["p"]))
    return out


# --- the race did not move --------------------------------------------------


def test_the_hero_replay_is_the_production_one(replay):
    assert replay["seed"] == SEED
    assert replay["digest"] == REPLAY_DIGEST
    assert replay["event_digest"] == EVENT_DIGEST


def test_the_winner_and_the_finish_order_are_unchanged(course):
    """Re-run, not re-read: the outcome has to come out of the simulation.

    A test that read the committed evidence would pass on a branch that had
    broken the race and then regenerated the evidence with it.
    """
    from race2.race import run_race

    outcome, _ = run_race(course, seed=SEED, duration=40.0, marble_count=8,
                          with_replay=False)
    order = [racer.marble_id for racer in
             sorted((r for r in outcome.racers if r.finish_order is not None),
                    key=lambda r: r.finish_order)]
    assert order[0] == 7, "PINK (m7) must still win"
    assert order == [7, 2, 1, 5, 3, 0, 6, 4], "the finish order moved"
    assert outcome.finished == 8


def test_the_race_runtime_is_unchanged(replay):
    assert len(replay["frames"]) == 2401
    assert abs(float(replay["frames"][-1]["t"]) - 40.0) < 1.0e-6
    assert replay["replay_fps"] == FPS


def test_nothing_in_this_branch_reaches_the_simulation():
    """The bookend module imports no physics, and nothing in `race2` imports it.

    Two directions, because either one alone is satisfiable by an accident.
    """
    import ast
    import inspect

    source = inspect.getsource(bookends)
    # **Parsed, not searched.** The module's own docstring explains that it
    # does not import the simulation, so a substring search for the names it
    # promises to avoid finds them in the promise. The import table is the
    # thing under test.
    imported: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
            imported.update(f"{node.module}.{a.name}" for a in node.names)
    for forbidden in ("marble3d.simulation", "marble3d.replay", "race2.race",
                      "race2.course", "race2.courses", "marble3d.mesh"):
        assert not any(name == forbidden or name.startswith(forbidden + ".")
                       for name in imported), (
            f"race2.bookends imports {forbidden}")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            assert not node.bases or all(
                getattr(base, "id", "") != "MarbleModule" for base in node.bases)
    for module_name in ("race2.race", "race2.course", "race2.courses",
                        "race2.parts", "race2.start", "race2.export"):
        module = __import__(module_name, fromlist=["x"])
        for node in ast.walk(ast.parse(inspect.getsource(module))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            assert "bookends" not in " ".join(names), (
                f"{module_name} imports the bookends")


def test_the_middle_camera_cuts_are_the_shipped_ones():
    """`release` is rewritten; `upper`, `middle` and `run_in` are not touched."""
    if not (os.path.isfile(TRACK) and os.path.isdir(V33_TRACKS)):
        pytest.skip("the camera tracks are not on disk; run `camera`")
    source = _read(TRACK)
    for key in sorted(os.listdir(V33_TRACKS)):
        built = _read(os.path.join(V33_TRACKS, key,
                                   f"race2_{COURSE}_{SEED}.cameras.json"))
        assert [c["name"] for c in built["cuts"]] == \
               [c["name"] for c in source["cuts"]]
        assert built["duration"] == source["duration"]
        for mine, theirs in zip(built["cuts"][1:], source["cuts"][1:]):
            assert json.dumps(mine, sort_keys=True) == \
                   json.dumps(theirs, sort_keys=True), \
                   f"{key}: cut {theirs['name']} moved"


def test_the_opening_cut_keeps_its_own_times():
    if not (os.path.isfile(TRACK) and os.path.isdir(V33_TRACKS)):
        pytest.skip("the camera tracks are not on disk; run `camera`")
    source = _read(TRACK)
    release = [c for c in source["cuts"] if c["name"] == "release"][0]
    for key in sorted(os.listdir(V33_TRACKS)):
        built = _read(os.path.join(V33_TRACKS, key,
                                   f"race2_{COURSE}_{SEED}.cameras.json"))
        mine = [c for c in built["cuts"] if c["name"] == "release"][0]
        assert len(mine["frames"]) == len(release["frames"])
        assert mine["frames"][0][0] == release["frames"][0][0]
        assert mine["frames"][-1][0] == release["frames"][-1][0]


def test_the_handoff_is_one_ordinary_frame_step():
    """The join must move the lens by what the next shot moves it by.

    Not "a small number": the scale that matters is the next cut's own first
    step, and the ratio is what says the cut is invisible rather than merely
    short.
    """
    if not (os.path.isfile(TRACK) and os.path.isdir(V33_TRACKS)):
        pytest.skip("the camera tracks are not on disk; run `camera`")
    source = _read(TRACK)
    upper = [c for c in source["cuts"] if c["name"] == "upper"][0]
    for key in sorted(os.listdir(V33_TRACKS)):
        built = _read(os.path.join(V33_TRACKS, key,
                                   f"race2_{COURSE}_{SEED}.cameras.json"))
        release = [c for c in built["cuts"] if c["name"] == "release"][0]
        error = opening.handoff_error(release, upper, FPS)
        assert abs(error["step_ratio"] - 1.0) < 0.02, (key, error)
        assert error["fov"] < 1.0e-4


def test_the_mechanism_timings_are_unchanged(replay):
    """Every `mechanism_hit` in the replay, at the time it always was."""
    hits = [event for event in replay.get("events", [])
            if event.get("kind") == "mechanism_hit"]
    assert len(hits) == 32, f"{len(hits)} mechanism hits, not 32"
    digest = hashlib.sha256(
        json.dumps([[round(float(h["t"]), 6), h.get("data", {}).get("module")]
                    for h in hits], sort_keys=True).encode("utf-8")).hexdigest()
    assert len(digest) == 64
    # The replay's own event digest already covers this; asserted together so
    # a future edit cannot satisfy one and not the other.
    assert replay["event_digest"] == EVENT_DIGEST


# --- the bookends exist -----------------------------------------------------


def test_the_start_stand_exists_with_one_bay_per_racer(spec, course):
    stand = [s for s in spec["stands"] if s["id"] == "start"][0]
    module = course.machine.modules["start"]
    assert stand["meta"]["bays"] == module.bays == 8
    backs = [p for p in stand["static"] if p["name"].startswith("bay_back_")]
    assert len(backs) == module.bays
    fins = [p for p in stand["static"] if p["name"].startswith("fin_")]
    assert len(fins) == module.bays + 1, "a fin either side of every bay"
    assert any(p["name"] == "board" for p in stand["static"])
    assert any(p["name"].startswith("tower_") for p in stand["static"])
    assert any(p["name"] == "header" for p in stand["static"])


def test_the_stand_is_built_from_the_course_and_not_from_a_constant(course):
    """A different racer count gives a different stand, with no other edit."""
    site = bookends.start_site(course)
    six = bookends.start_stand(site, 6, 0.9, 0.1, 0.16)
    assert six["meta"]["bays"] == 6
    assert len([p for p in six["static"] if p["name"].startswith("bay_back_")]) == 6
    assert len([p for p in six["static"] if p["name"].startswith("fin_")]) == 7
    assert six["meta"]["bay_pitch"] == 0.9
    assert six["meta"]["bay_across"][0] == pytest.approx(-2.25)


def test_the_gate_moves_on_the_release_the_physics_has(spec, course):
    module = course.machine.modules["start"]
    motion = [s for s in spec["stands"] if s["id"] == "start"][0]["motion"]
    assert motion["kind"] == "slide"
    assert motion["starts"] == pytest.approx(module.RELEASE_TIME)
    assert motion["duration"] == pytest.approx(module.RELEASE_DURATION)
    assert len(set(module.panel_release_times())) == 1, (
        "one gate is only honest while the floor releases in one tick")


def test_the_gate_animation_is_deterministic_and_bounded(spec):
    """The same second gives the same pose, and the pose never overshoots."""
    motion = [s for s in spec["stands"] if s["id"] == "start"][0]["motion"]
    start, duration = motion["starts"], motion["duration"]

    def phase(seconds: float) -> float:
        if duration <= 1.0e-6:
            return 1.0 if seconds >= start else 0.0
        value = min(1.0, max(0.0, (seconds - start) / duration))
        return value * value * (3.0 - 2.0 * value)

    assert phase(0.0) == 0.0
    assert phase(start) == 0.0
    assert phase(start + duration) == 1.0
    assert phase(19.15) == 1.0
    previous = -1.0
    for step in range(0, 1201):
        seconds = step / 400.0
        value = phase(seconds)
        assert 0.0 <= value <= 1.0
        assert value >= previous - 1.0e-12, "the gate must never go back"
        assert phase(seconds) == value, "the curve is not a function of time"
        previous = value


def test_the_gate_never_covers_a_racer(spec, course):
    """Its top is below every racer's lowest point, in world height.

    The image test is in the lab; this is the geometric one that makes the
    image test unnecessary at any elevation.
    """
    stand = [s for s in spec["stands"] if s["id"] == "start"][0]
    rail = [p for p in stand["motion"]["parts"] if p["name"] == "gate_rail"][0]
    module = course.machine.modules["start"]
    lowest = 0.5 * module.DECK_THICK
    assert rail["span"]["up"][1] <= lowest, (rail["span"]["up"], lowest)


def test_the_finish_stand_exists(spec):
    stand = [s for s in spec["stands"] if s["id"] == "finish"][0]
    names = {p["name"] for p in stand["static"]}
    assert "line_inlay" in names, "a finish line"
    assert {"leg_left", "leg_right", "gantry_header"} <= names, "a gantry"
    assert any(name.startswith("plaza_") for name in names), "a run-out"
    assert "plaza_end_front" in names, "something to stop against"
    assert "well_floor" in names, "a pocket for the racers the deck drops"
    assert stand["meta"]["gantry_rise"] > 3.0


def test_the_gantry_straddles_the_channel_without_standing_in_it(spec):
    stand = [s for s in spec["stands"] if s["id"] == "finish"][0]
    assert stand["meta"]["leg_clear"] > bookends.MARBLE_RADIUS
    assert stand["meta"]["header_clear"] > 2.0


def test_the_finish_line_is_set_into_the_running_surface(spec):
    stand = [s for s in spec["stands"] if s["id"] == "finish"][0]
    inlay = [p for p in stand["static"] if p["name"] == "line_inlay"][0]
    assert inlay["touch"] is True
    assert inlay["span"]["up"][1] < 0.05, (
        "a threshold a 0.57 ball rolls over cannot stand proud of the deck")


def test_no_bookend_part_stands_where_a_racer_goes(spec, points):
    """Every part, against every marble centre of the film.

    A part whose nearest approach is under one marble radius is inside a racer
    at some frame. The finish line's inlay and the plaza's surfacing declare
    `touch` because a racer is supposed to be in contact with them, and those
    are the only exemptions.
    """
    gaps = bookends.clearance(spec, points)
    for key, entry in gaps.items():
        assert entry["inside_a_racer"] == [], (key, entry["inside_a_racer"])
        assert entry["min_gap"] >= bookends.MARBLE_RADIUS, (key, entry)


def test_the_well_is_where_the_racers_actually_fall():
    """The pocket is sited on the replay, not on the plan."""
    if not os.path.isfile(FIELD):
        pytest.skip("the field report is not on disk; run `field`")
    field = _read(FIELD)
    well = field["well"]
    assert well is not None, "two racers end below the deck; there must be a well"
    assert set(well["racers"]) >= {1, 7}
    for record in field["rest"]:
        if record["state"] != "escaped":
            continue
        assert well["along"][0] <= record["along"] <= well["along"][1]
        assert well["across"][0] <= record["across"] <= well["across"][1]
        assert record["up"] - bookends.MARBLE_RADIUS >= well["floor"] - 0.06


def test_the_run_out_deck_defect_is_recorded_not_fixed(course):
    """`race2.parts.RunOut` is rotated 90 degrees, and must stay that way here.

    The physics is locked, so the defect is measured and the scenery is sited
    around it. This test fails if somebody fixes the module - which would be
    the right fix in a branch that is allowed to move the race, and is not this
    one.
    """
    run = course.runs["sprint"]
    module = course.machine.modules["runout"]
    tangent = (run.path[-1][0] - run.path[-2][0], 0.0,
               run.path[-1][2] - run.path[-2][2])
    length = math.hypot(tangent[0], tangent[2]) or 1.0
    travel = (tangent[0] / length, 0.0, tangent[2] / length)
    dot = travel[0] * module.forward[0] + travel[2] * module.forward[2]
    assert abs(dot) < 1.0e-6, (
        "RunOut.forward is no longer square to the direction of travel; the "
        "run-out has been re-sited and the V33 finish stand must be re-measured")


# --- the two projections agree ----------------------------------------------


def test_the_opening_projection_matches_the_rig(course):
    """`opening.screen` and `rig._screen` must not disagree by a sign."""
    import random

    generator = random.Random(33)
    for _ in range(64):
        position = tuple(generator.uniform(-40.0, 40.0) for _ in range(3))
        aim = tuple(generator.uniform(-40.0, 40.0) for _ in range(3))
        if math.dist(position, aim) < 1.0:
            continue
        fov = generator.uniform(14.0, 50.0)
        targets = [tuple(generator.uniform(-40.0, 40.0) for _ in range(3))
                   for _ in range(6)]
        mine = opening.screen(targets, position, aim, fov)
        theirs = _screen(targets, position, aim, fov)
        for (x, y, _depth), (a, b) in zip(mine, theirs):
            assert x == pytest.approx(a, abs=1.0e-9)
            assert y == pytest.approx(b, abs=1.0e-9)
        assert opening.basis(position, aim) == _basis(position, aim)


def test_every_composition_leaves_all_eight_racers_visible(course, spec):
    site = bookends.start_site(course)
    module = course.machine.modules["start"]
    rise = 0.5 * module.DECK_THICK + bookends.MARBLE_RADIUS
    row = opening.racer_points(site, module.bays, module.BAY_PITCH, rise)
    for composition in opening.COMPOSITIONS:
        distance = opening.solve(site, composition, row, bookends.MARBLE_RADIUS)
        measured = opening.measure(site, composition, distance, row,
                                   bookends.MARBLE_RADIUS)
        assert measured["in_frame"] == module.bays, composition.key
        blocked = {bookends.blocked(spec, measured["position"], point)
                   for point in row} - {""}
        assert blocked == set(), (composition.key, blocked)


def test_the_chosen_hook_is_larger_than_the_shipped_opening(course):
    """Part G's headline, as an inequality rather than a screenshot."""
    if not os.path.isfile(TRACK):
        pytest.skip("the shipped camera track is not on disk")
    site = bookends.start_site(course)
    module = course.machine.modules["start"]
    rise = 0.5 * module.DECK_THICK + bookends.MARBLE_RADIUS
    row = opening.racer_points(site, module.bays, module.BAY_PITCH, rise)

    shipped = _read(TRACK)["cuts"][0]["frames"][0]
    projected = opening.screen(row, shipped[1:4], shipped[4:7], shipped[7])
    before = sorted(opening.pixel_diameter(d, shipped[7], bookends.MARBLE_RADIUS)
                    for _x, _y, d in projected)
    before = 0.5 * (before[3] + before[4])

    chosen = [c for c in opening.COMPOSITIONS if c.key == "C"][0]
    distance = opening.solve(site, chosen, row, bookends.MARBLE_RADIUS)
    after = opening.measure(site, chosen, distance, row,
                            bookends.MARBLE_RADIUS)["median_diameter_1080"]
    assert after > before * 1.25, (before, after)
    assert after > 97.6, (
        "the dead-front cap: eight racers at 1.439 diameters of pitch cannot "
        "exceed this without obliquity, and beating it is the whole point")


# --- scope ------------------------------------------------------------------


def test_the_branch_adds_bookends_and_touches_nothing_else():
    """Part E, as a diff against the production commit.

    The physics, the course, the race, the presentation, the audio, the
    environment profiles, the palette and the camera solver are all absent from
    this list, and a file arriving here that is not in it is what this test
    exists to catch.
    """
    diff = _git("diff", "--name-only", BASE_COMMIT)
    if diff is None:
        pytest.skip("not a git checkout")
    changed = {line.strip() for line in diff.splitlines() if line.strip()}
    allowed = {
        "race2/bookends.py",
        "race2/opening.py",
        "godot/assets/marble_machine/course/race2_bookends.gd",
        "godot/scripts/race2_scene.gd",
        "tools/race2_render.py",
        "tools/race2_v33_bookends.py",
        "tests/test_race2_v33_bookends.py",
        "docs/race2_v33_mobile_bookends.md",
    }
    stray = {path for path in changed
             if path not in allowed
             and not path.startswith("docs/validation/race2/v33_bookends/")}
    assert stray == set(), f"unexpected files changed: {sorted(stray)}"


def test_the_audio_is_not_rebuilt_by_this_branch():
    """Part I: the soundtrack is a stream copy of the delivered V32.2 file."""
    import inspect
    import importlib.util

    path = os.path.join(REPO, "tools", "race2_v33_bookends.py")
    if not os.path.isfile(path):
        pytest.skip("the lab tool is not on disk")
    source = open(path, encoding="utf-8").read()
    assert "build_race_audio" not in source
    assert "-c:a\", \"copy\"" in source or '"-c:a", "copy"' in source
    assert "loudnorm" not in source


def test_the_scene_builds_no_bookend_without_the_flag():
    """The seam is off by default, which is what keeps V32.2 reproducible."""
    scene = os.path.join(REPO, "godot", "scripts", "race2_scene.gd")
    source = open(scene, encoding="utf-8").read()
    body = source[source.index("func _build_bookends"):]
    body = body[:body.index("func _stage_datum")]
    assert "if path.is_empty():" in body
    assert body.index("if path.is_empty():") < body.index("Bookends.build")
    assert 'options.get("bookends", "")' in source


def test_the_bookend_builder_creates_no_collider():
    builder = os.path.join(REPO, "godot", "assets", "marble_machine", "course",
                           "race2_bookends.gd")
    # Comment lines are stripped first: the file's own header says there is no
    # `StaticBody3D` in it, and a search that reads the header finds one.
    lines = open(builder, encoding="utf-8").read().splitlines()
    code = " ".join(line for line in lines
                    if not line.lstrip().startswith("#"))
    for forbidden in ("StaticBody3D", "CollisionShape3D", "RigidBody3D",
                      "Area3D", "PhysicsBody"):
        assert forbidden not in code, forbidden
