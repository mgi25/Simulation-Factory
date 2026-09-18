"""V33.1: the run-out points along the track, and the race is the one V33 ran.

Three kinds of claim, and the tests are grouped by which.

**The convention.** There are two yaw conventions in this package, ninety
degrees apart, and reading one through the other's inverse is the defect this
pass exists to repair. The tests below pin the rule itself - a round trip, an
exact ninety-degree offset - and then ask the real `RunOut` which way it faces
at four cardinal bearings and two diagonals. They are written so that the
shipped expression *fails* every one of them: a check that only asked "is the
deck roughly downhill of the line?" would have passed the broken build, and
that is exactly the check nobody had.

**The race.** The brief locks everything before the finish line. The strong
form of that is per racer: each marble's record must be bit-identical at every
frame strictly before its own crossing, not merely before the winner's. Five
racers are still on the course when the winner crosses, and a deck that had
moved under one of them would show up later than frame 949 and pass the weak
test.

**The film.** The camera track, the audio source, the frame count and the
start stand are carried over rather than rebuilt, and the tests say so by
digest. The ones that want a render skip when the frames are not on disk,
because a render needs a GPU and `output/` is not in the branch.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from race2 import courses, kit
from race2.parts import RunOut
from sloped.scale import SIM_TO_LAYOUT

COURSE = "switchyard"
SEED = 8
FPS = 60
FILM_FRAMES = 1150
RUNTIME = FILM_FRAMES / FPS

WINNER = 7
WINNER_LABEL = "PINK"
FINISH_ORDER = [7, 2, 1, 5, 3, 0, 6, 4]
CROSSINGS = {7: 15.816667, 2: 15.883333, 1: 16.133333, 5: 16.583333,
             3: 17.2, 0: 17.716667, 6: 17.816667, 4: 18.75}
DELIVERY = (1080, 1920)

OUT = os.path.join(REPO, "output", "race2", "v331_runout")
DOCS = os.path.join(REPO, "docs", "validation", "race2", "v331_runout")
SOURCE = os.path.join(OUT, "source")
BASELINE = os.path.join(OUT, "baseline")
V33_CAMERA = os.path.join(REPO, "output", "race2", "v31_readability", "RB")

# The production replay's own digests, from `docs/race2_v32_production.md`.
# The race before the line is that race, so these must still be the V33 pair's.
REPLAY_DIGEST = ("751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7"
                 "f539")
EVENT_DIGEST = ("51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f5333369830165"
                "02")


def _names(folder):
    stem = os.path.join(folder, f"race2_{COURSE}_{SEED}")
    return (f"{stem}.geometry.json", f"{stem}.replay.json",
            f"{stem}.cameras.json")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _need(path, what):
    if not os.path.exists(path):
        pytest.skip(f"{what} is not on disk: run `python "
                    f"tools/race2_v331_runout.py all` first")
    return path


@pytest.fixture(scope="module")
def course():
    return courses.build(COURSE)


@pytest.fixture(scope="module")
def deck(course):
    return course.machine.modules["runout"]


@pytest.fixture(scope="module")
def fixed_replay():
    return _read(_need(_names(SOURCE)[1], "the V33.1 replay"))


@pytest.fixture(scope="module")
def base_replay():
    return _read(_need(_names(BASELINE)[1], "the V33 replay"))


# --- the convention ---------------------------------------------------------


BEARINGS = {
    "+X": (1.0, 0.0, 0.0),
    "-X": (-1.0, 0.0, 0.0),
    "+Z": (0.0, 0.0, 1.0),
    "-Z": (0.0, 0.0, -1.0),
    "+X+Z": (1.0, 0.0, 1.0),
    "-X+Z": (-3.0, 0.0, 1.0),
}


def test_the_compass_heading_round_trips_through_its_own_forward():
    """`forward_from_heading` and `heading_from_forward` are inverses.

    And they agree with `TrackRun.heading_deg`, which is the angle they exist
    to convert: both are `atan2(x, z)` over the same flattened tangent.
    """
    for degrees in range(-180, 181, 7):
        forward = kit.forward_from_heading(degrees)
        assert math.isclose(kit.heading_from_forward(forward), degrees,
                            abs_tol=1e-9)
        assert math.isclose(math.hypot(forward[0], forward[2]), 1.0,
                            abs_tol=1e-12)
        assert forward[1] == 0.0


def test_the_two_conventions_differ_by_exactly_ninety_degrees():
    """The whole defect, as an identity rather than as a story.

    `build_yaw = heading - 90` at every bearing. This is why feeding a heading
    into the build-yaw formula is not a small error anywhere: there is no
    heading at which the two happen to nearly agree.
    """
    for degrees in range(-180, 181, 3):
        forward = kit.forward_from_heading(degrees)
        offset = (degrees - kit.build_yaw_from_forward(forward)) % 360.0
        assert math.isclose(offset, 90.0, abs_tol=1e-9), degrees


def test_the_shipped_expression_was_perpendicular_at_every_heading():
    """`(cos h, 0, -sin h)` against `(sin h, 0, cos h)`: dot is zero, always.

    The characterisation of the bug. It is asserted rather than described so
    that anyone reverting the fix is told what they have reintroduced.
    """
    for degrees in range(-180, 181, 5):
        heading = math.radians(degrees)
        want = kit.forward_from_heading(degrees)
        shipped = (math.cos(heading), 0.0, -math.sin(heading))
        assert abs(want[0] * shipped[0] + want[2] * shipped[2]) < 1e-12


class _StraightRun:
    """The three attributes `RunOut` reads off a `TrackRun`, on a bearing."""

    def __init__(self, forward):
        unit = kit.flat_forward(forward)
        self.path = [(0.0, 0.0, 0.0), tuple(4.0 * c for c in unit)]
        self.tangents = [unit, unit]
        self.scale = 1.0


@pytest.mark.parametrize("name", sorted(BEARINGS))
def test_the_run_out_points_the_way_the_run_does(name):
    """The canonical direction test, on cardinals and on two diagonals.

    `dot == 1`, not `dot > 0`. The broken build scored exactly zero here, and
    a tolerance loose enough to be comfortable would have been loose enough to
    miss it.
    """
    direction = BEARINGS[name]
    want = kit.flat_forward(direction)
    got = RunOut("probe", _StraightRun(direction)).forward
    dot = sum(want[axis] * got[axis] for axis in range(3))
    assert math.isclose(dot, 1.0, abs_tol=1e-12), (name, want, got)


@pytest.mark.parametrize("name", sorted(BEARINGS))
def test_the_run_out_across_axis_is_square_and_left_handed(name):
    """`across = up x forward`, so +across is to the left of travel.

    Stated because a receiving lane numbered the wrong way round is a defect
    that looks like a working one.
    """
    direction = BEARINGS[name]
    deck = RunOut("probe", _StraightRun(direction))
    assert math.isclose(sum(deck.forward[a] * deck.across[a] for a in range(3)),
                        0.0, abs_tol=1e-12)
    cross_y = deck.forward[2] * deck.across[0] - deck.forward[0] * deck.across[2]
    assert math.isclose(cross_y, -1.0, abs_tol=1e-12)


def test_the_deck_forward_is_the_sprints_own_exit_tangent(course, deck):
    """On the real course, not on a probe: the deck follows the racing line."""
    sprint = course.runs["sprint"]
    tangent = kit.flat_forward(sprint.tangents[len(sprint.path) - 1])
    dot = sum(tangent[axis] * deck.forward[axis] for axis in range(3))
    assert math.isclose(dot, 1.0, abs_tol=1e-12)


def test_the_deck_is_built_from_a_tangent_and_not_from_an_angle():
    """No heading is constructed on the way to the deck's frame.

    The structural half of the fix: an expression that never makes an angle
    cannot read one back through the wrong convention. If a later edit
    reintroduces `heading_deg` here, this is the test that says so.
    """
    import inspect

    # Comments stripped: this file *documents* the old expression on purpose,
    # and a test that could not tell prose from code would forbid saying what
    # went wrong.
    body = [line for line in inspect.getsource(RunOut.__init__).splitlines()
            if not line.lstrip().startswith("#")]
    source = " ".join(body)
    assert "heading_deg" not in source
    assert "flat_forward" in source


def test_the_finish_gate_is_behind_the_back_wall(deck):
    """A racer resting on the back wall must not be captured by the exit gate.

    `MarbleSimulation._past_finish` retires anything past the last module's
    exit socket - it zeroes the velocity and removes the body - so a gate in
    front of the wall makes the wall decorative and freezes whoever reaches it.
    """
    from marble3d.units import MARBLE_RADIUS

    radius = MARBLE_RADIUS * SIM_TO_LAYOUT
    resting = deck.DEPTH - radius
    gate = deck.DEPTH + deck.CATCH
    assert gate > resting + radius, (gate, resting, radius)


# --- the race ---------------------------------------------------------------


def test_the_v33_replay_is_the_production_race(base_replay):
    """The control is the race Test #3 shipped, by digest, before anything else."""
    assert base_replay["digest"] == REPLAY_DIGEST
    assert base_replay["event_digest"] == EVENT_DIGEST
    assert int(base_replay["seed"]) == SEED


def _crossings(replay):
    return [(int(e["id"]), round(float(e["t"]), 6), int(e["order"]))
            for e in replay["events"] if e["kind"] == "finish_line"]


def test_the_winner_is_unchanged(fixed_replay):
    assert _crossings(fixed_replay)[0][0] == WINNER


def test_the_finish_order_is_unchanged(fixed_replay):
    assert [row[0] for row in _crossings(fixed_replay)] == FINISH_ORDER


def test_every_crossing_time_is_unchanged(base_replay, fixed_replay):
    """Ids, times and placings, as one comparison rather than three.

    The placings are in it because they nearly were not: `Race2` extends
    `MarbleSimulation` and the two shared a `_finish_count` attribute, so the
    first racer to reach the machine's exit socket alive - which no Race #2
    racer ever had, because they all fell out instead - renumbered everything
    from fourth place down.
    """
    assert _crossings(fixed_replay) == _crossings(base_replay)
    assert {row[0]: row[1] for row in _crossings(fixed_replay)} == CROSSINGS


def test_every_racer_is_bit_identical_before_its_own_crossing(base_replay,
                                                              fixed_replay):
    """The strong form of the pre-finish lock, per racer.

    Every frame strictly before a racer crosses must be byte-identical. Not
    "before the winner crosses": five racers are still on the course then.
    """
    a, b = base_replay["frames"], fixed_replay["frames"]
    for marble, crossing in CROSSINGS.items():
        last = int(round(crossing * FPS))
        for index in range(last):
            assert a[index]["marbles"][marble] == b[index]["marbles"][marble], (
                f"m{marble} moved at frame {index}, {index / FPS:.4f} s, "
                f"before its own crossing at {crossing}")


def test_no_event_before_the_line_moved(base_replay, fixed_replay):
    winner = CROSSINGS[WINNER]
    before_a = [e for e in base_replay["events"] if e["t"] < winner - 1e-9]
    before_b = [e for e in fixed_replay["events"] if e["t"] < winner - 1e-9]
    assert before_a == before_b
    assert len(before_b) > 300


LOCKED_KINDS = ("release", "mechanism_hit", "line_choice",
                "module_enter", "module_exit", "collision")


@pytest.mark.parametrize("kind", LOCKED_KINDS)
def test_every_event_kind_before_the_line_is_unchanged(base_replay,
                                                       fixed_replay, kind):
    """The brief's named locks, one assertion each so a failure names the one.

    `release` is the start gate, `mechanism_hit` is the mixer, the drum, the
    sweep and the pair, and `line_choice` is the route split. All 32 mechanism
    hits and all 8 releases happen before the line, so for those two kinds this
    is the whole timeline and not a prefix of it.
    """
    line = CROSSINGS[WINNER]
    before = [[e for e in replay["events"]
               if e["kind"] == kind and e["t"] < line]
              for replay in (base_replay, fixed_replay)]
    assert before[0] == before[1]
    assert before[0], kind


def test_the_whole_mechanism_and_gate_timeline_is_before_the_line(fixed_replay):
    """So the comparison above is exhaustive for those two kinds, not partial."""
    line = CROSSINGS[WINNER]
    for kind, expected in (("release", 8), ("mechanism_hit", 32)):
        events = [e for e in fixed_replay["events"] if e["kind"] == kind]
        assert len(events) == expected, kind
        assert all(e["t"] < line for e in events), kind


def test_the_racers_themselves_are_unchanged(base_replay, fixed_replay):
    """Count, radius, mass, start slot and the solver's own configuration."""
    assert fixed_replay["marbles"] == base_replay["marbles"]
    assert fixed_replay["config"] == base_replay["config"]
    assert len(fixed_replay["marbles"]) == 8


def test_the_replay_is_the_same_length(base_replay, fixed_replay):
    assert len(fixed_replay["frames"]) == len(base_replay["frames"])
    assert fixed_replay["replay_fps"] == base_replay["replay_fps"]
    assert fixed_replay["physics_hz"] == base_replay["physics_hz"]


def test_nobody_leaves_the_machine_any_more(base_replay, fixed_replay):
    """Three racers escaped in V33, including the winner. None may now."""
    def retired(replay):
        return [(e["kind"], int(e["id"])) for e in replay["events"]
                if e["kind"] in ("escaped", "finish")]

    assert retired(base_replay) == [("escaped", 7), ("escaped", 1),
                                    ("escaped", 4)]
    assert retired(fixed_replay) == []


def test_no_racer_is_frozen_in_the_film(fixed_replay):
    """Nobody may come to a dead stop and stay there before the film ends.

    A retired marble repeats one pose to the end of the replay, which is what
    the V33 winner does for 192 frames. A racer that has genuinely rolled to
    rest on the deck is a different thing and is allowed - what is not is a
    racer whose position is frame-for-frame identical over the last second
    while its own record says it is still in the world.
    """
    frames = fixed_replay["frames"]
    last = FILM_FRAMES - 1
    for marble in CROSSINGS:
        window = [frames[index]["marbles"][marble]["p"]
                  for index in range(last - FPS, last + 1)]
        assert len(set(tuple(p) for p in window)) > 1, (
            f"m{marble} has not moved for a second by the end of the film")


def test_the_winner_is_supported_after_crossing(fixed_replay, deck):
    """The winner runs out on the deck, not through it and not off its side."""
    from marble3d.units import MARBLE_RADIUS

    radius = MARBLE_RADIUS * SIM_TO_LAYOUT
    fall = math.tan(math.radians(deck.FALL_DEG))
    supported = 0
    window = range(int(round(CROSSINGS[WINNER] * FPS)), FILM_FRAMES)
    for index in window:
        point = fixed_replay["frames"][index]["marbles"][WINNER]["p"]
        world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
        offset = [world[axis] - deck.origin[axis] for axis in range(3)]
        along = offset[0] * deck.forward[0] + offset[2] * deck.forward[2]
        across = offset[0] * deck.across[0] + offset[2] * deck.across[2]
        assert -radius <= along <= deck.DEPTH + deck.CATCH, (index, along)
        assert abs(across) <= 0.5 * deck.width + radius, (index, across)
        surface = -fall * max(along, 0.0) + radius
        if abs(offset[1] - surface) <= 0.1 * radius:
            supported += 1
    assert supported >= 0.9 * len(window), (supported, len(window))


def _final_height(replay, deck) -> float:
    """The winner's height above the deck's own origin plane at the last frame."""
    point = replay["frames"][FILM_FRAMES - 1]["marbles"][WINNER]["p"]
    world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
    return world[1] - deck.origin[1]


def test_the_winner_travels_forward_after_the_line(fixed_replay, base_replay,
                                                   deck):
    """Forward along the track, and further than V33 managed before it fell."""
    def reach(replay):
        best = 0.0
        for index in range(int(round(CROSSINGS[WINNER] * FPS)), FILM_FRAMES):
            point = replay["frames"][index]["marbles"][WINNER]["p"]
            world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
            offset = [world[axis] - deck.origin[axis] for axis in range(3)]
            best = max(best, offset[0] * deck.forward[0]
                       + offset[2] * deck.forward[2])
        return best

    # Against the deck's own length rather than a bare number, so the test
    # still means "it runs the length of the run-out" if the run-out is
    # resized again.
    #
    # **Not "further than V33 managed".** V33's winner covers 2.86 units in
    # this same frame before it runs out of deck and falls; V33.1's covers
    # 2.92 and stops against a wall. Distance is not what changed and a test
    # on it would be measuring the wrong thing. What changed is the end state,
    # which `test_the_winner_is_supported_after_crossing` asserts and which the
    # two numbers below carry: V33's winner finishes 1.23 units *under* the
    # deck plane, V33.1's finishes on it.
    assert reach(fixed_replay) > 0.85 * deck.DEPTH
    assert _final_height(fixed_replay, deck) > 0.0
    assert _final_height(base_replay, deck) < -1.0


def test_the_run_out_knows_nothing_about_which_racer_is_on_it():
    """No winner-specific handling in the geometry the field runs out onto.

    The brief forbids freezing, magnetising or braking the winner. The
    structural half of that claim: `race2.parts` builds one deck, one set of
    walls and one gate, and it cannot name a racer because nothing in it has a
    marble to name. `RunOut.holds` takes a point, not an id.
    """
    import ast
    import inspect

    from race2 import parts

    # **Code only.** `ast.unparse` of a parsed module drops every comment, and
    # the docstrings are dropped below, so what is left is what actually runs.
    # This file explains the defect it repairs at some length and a check that
    # could not tell prose from code would forbid the explanation.
    tree = ast.parse(inspect.getsource(parts))
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = node.body
        if (body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)):
            node.body = body[1:] or [ast.Pass()]
    source = ast.unparse(tree)
    for banned in ("winner", "marble_id", "racer_id", "leader"):
        assert banned not in source, banned


def test_every_racer_runs_out_the_same_way(fixed_replay, deck):
    """The empirical half: the winner is not the best-treated racer.

    Every one of the eight crosses, runs forward onto the deck and is held up
    by it, measured the same way for each. If the winner were being helped -
    or spared - it would be the outlier here, and it is not.
    """
    from marble3d.units import MARBLE_RADIUS

    radius = MARBLE_RADIUS * SIM_TO_LAYOUT
    fall = math.tan(math.radians(deck.FALL_DEG))
    reached = {}
    for marble, crossing in CROSSINGS.items():
        window = range(int(round(crossing * FPS)), FILM_FRAMES)
        best = 0.0
        settled = None
        rise = 0.0
        sink = 0.0
        for index in window:
            point = fixed_replay["frames"][index]["marbles"][marble]["p"]
            world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
            offset = [world[axis] - deck.origin[axis] for axis in range(3)]
            along = offset[0] * deck.forward[0] + offset[2] * deck.forward[2]
            across = offset[0] * deck.across[0] + offset[2] * deck.across[2]
            assert -radius <= along <= deck.DEPTH + deck.CATCH, (marble, index)
            assert abs(across) <= 0.5 * deck.width + radius, (marble, index)
            best = max(best, along)
            rest = -fall * max(along, 0.0) + radius
            if settled is None and abs(offset[1] - rest) <= 0.1 * radius:
                settled = index - window.start
            if settled is not None:
                rise = max(rise, offset[1] - rest)
                sink = min(sink, offset[1] - rest)
        reached[marble] = (best, settled, rise, sink)
    # **Measured from where each racer lands, not from the line, and measured
    # as a height rather than as a count.** A racer arrives off a descending
    # channel with its centre above the deck and is airborne for a few frames
    # before it is on anything; the last one home crosses 0.4 s before the film
    # ends and is still in the air for twelve of its twenty-five remaining
    # frames. A supported-frame *count* over that window measures how late a
    # racer finished, not whether the deck holds it. What the brief actually
    # forbids is a violent bounce and a drop through the floor, and those are
    # heights: after it lands, a racer must stay inside the wall that stopped
    # it and must not sink into the deck.
    diameter = 2.0 * radius
    for marble, (best, settled, rise, sink) in reached.items():
        assert settled is not None, marble
        # Half a second to be on the deck. A racer arrives on a descending
        # channel with its centre well above the run-out and flies the first
        # part of its arrival; measured, the slowest to land is 18 frames and
        # most are down within two.
        assert settled <= 30, (marble, settled)
        # **The bound on the bounce is the rim, not a number chosen here.** How
        # high a racer comes off the back wall does not converge as the deck is
        # tuned - see `test_the_rim_contains_the_bounce_the_deck_causes` and
        # the document's section 4 - so the honest assertion is the one the
        # geometry itself makes: a racer stays inside the wall that stopped it.
        # A separate tolerance would be a second number to keep in step with
        # the first. `sink` catches a racer going through the floor rather than
        # onto it.
        assert rise + radius <= deck.RIM, (marble, rise)
        assert sink >= -0.1 * diameter, (marble, sink)
        assert best > 0.8 * deck.DEPTH, (marble, best)


# --- the film ---------------------------------------------------------------


def test_the_camera_track_is_carried_over_byte_for_byte():
    """The brief locks the camera, so it is copied and not re-solved."""
    shipped = _need(_names(V33_CAMERA)[2], "the V33 camera track")
    for folder in (SOURCE, BASELINE):
        track = _need(_names(folder)[2], f"the camera track in {folder}")
        assert _sha(track) == _sha(shipped)


def test_the_per_composition_camera_tracks_match_v33():
    """Including the one cut V33 rewrites: the opening reads the replay.

    `stage_camera` sites the opening on the field's own centroid, off the
    replay. That window is before the line, where the two replays are
    identical, so the rewritten cut must come out identical too - and if the
    fix had reached the start, this is where it would show.
    """
    report = os.path.join(DOCS, "camera.json")
    _need(report, "the camera report")
    for key, block in _read(report)["compositions"].items():
        assert block["later_cuts_identical"], key
        assert block["handoff"]["step_ratio"] == pytest.approx(1.0, abs=0.05)


def test_only_the_run_out_module_moved():
    """The smallest-correction claim, as a diff of the renderer's own export."""
    report = _read(_need(os.path.join(DOCS, "geometry.json"),
                         "the geometry report"))
    assert report["modules_changed"] == ["runout"]
    assert report["runs_identical"]
    assert report["start_identical"]
    assert report["actuators_identical"]
    assert report["only_the_runout_moved"]


def test_the_start_stand_is_unchanged():
    """Thirty-six parts and the same nearest-racer gap as V33's own report."""
    spec = _read(_need(os.path.join(DOCS, "spec.json"), "the spec report"))
    start = spec["stands"]["start"]
    assert start["static"] == 36
    assert start["motion"] == 3
    assert spec["clearance"]["start"]["min_gap"] == pytest.approx(0.345,
                                                                 abs=5e-4)


def test_no_bookend_part_stands_where_a_racer_goes():
    """Every part against every marble centre, on a *matched* spec and replay.

    V33 makes this check too, but its `spec` fixture falls back to a live
    `bookends.build(course)` when its own built bookends are not on disk, and a
    plaza sited on V33.1's field compared against V33's recorded trajectories
    reports a collision that neither build has. That test now skips on an
    unmatched pair and this one carries the claim: `stage_spec` measures the
    clearance of the spec it just built against the replay it was built from.
    """
    report = _read(_need(os.path.join(DOCS, "spec.json"), "the spec report"))
    for stand, entry in report["clearance"].items():
        assert entry["inside_a_racer"] == [], (stand, entry["inside_a_racer"])
        assert entry["min_gap"] > 0.285, (stand, entry["min_gap"])


def test_the_gantry_and_the_colonnade_did_not_move():
    """Every part the brief says to keep, byte-identical to V33's own build.

    The plaza is allowed to move - it is the receiving area and it follows the
    field, which is the point of the pass - but the gantry header, its cap and
    accent, the four approach portals and the finish line's own inlay and
    kerbs are the finish art and they are locked.
    """
    ours = _read(_need(os.path.join(OUT, "bookends.json"), "the V33.1 spec"))
    theirs = _read(_need(os.path.join(REPO, "..", "wt-v33-bookends", "output",
                                      "race2", "v33_bookends", "bookends.json"),
                         "V33's built bookends"))

    def parts(spec):
        stand = [s for s in spec["stands"] if s["id"] == "finish"][0]
        return {p.get("name"): p for p in stand["static"]}

    a, b = parts(theirs), parts(ours)
    locked = [name for name in a
              if name.startswith(("gantry_", "approach_", "line_", "brace_"))]
    assert len(locked) >= 20
    for name in locked:
        assert name in b, name
        assert json.dumps(a[name], sort_keys=True) == \
            json.dumps(b[name], sort_keys=True), name


def test_the_audio_is_the_delivered_stream():
    """No rebuild: the V32.2 soundtrack is stream-copied, as V33 copied it.

    Checked on the AAC elementary stream rather than on the file, because two
    MP4s built at different times differ in their containers whatever the
    audio is doing. Equal digests mean no encoder touched the soundtrack
    between the film that shipped as Test #3 and this one.
    """
    qc = _read(_need(os.path.join(DOCS, "qc.json"), "the QC report"))
    audio = qc["audio"]
    assert audio["present"]
    assert audio["source"].replace("\\", "/").endswith(
        "wt-v322-audio/exports/race2_v322_audio/race2_switchyard_final_audio.mp4")
    if "adts_sha256" not in audio:
        pytest.skip("the Short has not been muxed")
    assert len(audio["adts_sha256"]) >= 2
    assert audio["identical_to_v322"], audio["adts_sha256"]


def test_the_runtime_is_unchanged():
    qc = _read(_need(os.path.join(DOCS, "qc.json"), "the QC report"))
    assert qc["frames"]["v331"] == FILM_FRAMES
    assert qc["frames"]["v33"] == FILM_FRAMES
    assert qc["runtime_seconds"] == pytest.approx(RUNTIME, abs=1e-6)


def test_the_start_and_the_middle_render_identically():
    """Frame 0 and everything up to the run-out entering shot, by PNG digest.

    **The first difference is 27 frames before the winner crosses, and that is
    the right answer.** What moved is the run-out and the plaza that follows
    it, and scenery comes into shot before the racer running toward it does.
    That it is scenery and not a racer is proved elsewhere and exactly: the
    replay is byte-identical for every marble through frame 949 and the camera
    track is literally the same file, so nothing that changed on screen at
    frame 922 can be a racer in a different place.

    What this test pins is that the identical run covers the start, the whole
    middle and most of the sprint, and that the difference *begins* as a
    hundred pixels at the edge of the frame rather than as something arriving
    in the middle of the picture.
    """
    qc = _read(_need(os.path.join(DOCS, "qc.json"), "the QC report"))
    if "picture" not in qc:
        pytest.skip("the two masters have not both been rendered")
    picture = qc["picture"]
    assert picture["frame_zero_identical"]
    if picture["first_difference"] is None:
        return
    cuts = {cut["name"]: cut for cut in picture["by_cut"]}
    # The start and the long chase are the same files, frame for frame.
    for name in ("release", "upper"):
        assert cuts[name]["frames_differing"] == 0, cuts[name]
        assert cuts[name]["frames_total"] > 100, cuts[name]
    # The middle is identical too on the shipped geometry, and a tolerance is
    # kept only because it need not be: a run-out tall or long enough to reach
    # into the middle cut may clip its bottom-left corner, and a corner is not
    # a regression. Anything larger than that is.
    middle = cuts["middle"]
    assert middle["frames_differing"] <= 0.1 * middle["frames_total"], middle
    assert middle["worst_changed"] < 0.001, middle
    if middle["box"] is not None:
        left, top, right, bottom = middle["box"]
        assert right <= DELIVERY[0] // 4, middle
        assert top >= 0.9 * DELIVERY[1], middle
        assert bottom == DELIVERY[1] - 1, middle


def test_the_delivered_short_is_the_locked_length():
    qc = _read(_need(os.path.join(DOCS, "qc.json"), "the QC report"))
    if "delivered" not in qc:
        pytest.skip("the Short has not been muxed")
    for key, streams in qc["delivered"].items():
        video = [s for s in streams if s["codec_type"] == "video"][0]
        audio = [s for s in streams if s["codec_type"] == "audio"][0]
        assert int(video["nb_frames"]) == FILM_FRAMES, key
        assert audio["codec_name"] == "aac", key
        assert int(audio["sample_rate"]) == 48000, key


def test_the_winner_stays_on_screen_after_crossing():
    """The camera review, on the render rather than on the projection.

    **A frustum count is not visibility**, so this reads the matte: every racer
    painted as a flat class and counted in pixels, which a parapet can hide.
    The brief requires the winner to remain visible after it crosses, under the
    locked camera, with the geometry doing the work.

    This is the test the pass was nearly shipped without. Rotating the deck and
    changing nothing else put the field eight units past the line while the
    finish shot's reach falls to 4.3, and the winner spent the last 1.7 s -
    the payoff - off the left of frame. The numbers below are what sent it
    back for the resize.
    """
    report = _read(_need(os.path.join(DOCS, "visibility.json"),
                         "the visibility report"))
    ours = report["by_build"]["v331"]
    theirs = report["by_build"]["v33"]
    if "winner_on_screen" not in ours:
        pytest.skip("the mattes have not been rendered")
    # **One frame, and it is the gantry's.** The winner is behind the near
    # gantry leg at f953 - 0.07 s after it crosses - and out the other side at
    # f954. That is locked finish architecture doing what it has always done
    # (V24's payoff lab found both of its winner marks pointing at a marble
    # behind this gantry), not anything this pass added. What would be a defect
    # is a *sustained* loss, so the assertion is on the longest run of hidden
    # frames rather than on the total.
    pixels = ours["winner_pixels"]
    longest = run = 0
    for count in pixels:
        run = run + 1 if count == 0 else 0
        longest = max(longest, run)
    assert longest <= 1, (longest, ours["winner_on_screen"],
                          ours["matte_frames"])
    assert ours["winner_on_screen"] >= 0.99 * ours["matte_frames"]
    assert ours["empty_frames"] == 0
    # And the rest of the field is no worse off than it was in V33 - a taller
    # rim that hid racers behind it would show up here as a fall.
    assert ours["mean_racers_on_screen"] >= theirs["mean_racers_on_screen"]


def test_the_winner_is_inside_the_camera_frustum_throughout():
    """The projection half of the same claim, which is cheap and exact."""
    report = _read(_need(os.path.join(DOCS, "visibility.json"),
                         "the visibility report"))
    ours = report["by_build"]["v331"]
    assert ours["winner_in_frustum"] == ours["frames"]


def test_the_rim_contains_the_bounce_the_deck_causes(fixed_replay, deck):
    """Nobody may get their centre over the top of the wall that stops them.

    The mechanism behind the resize. At `RIM` 0.80 the wall was lower than the
    rebound it produced, so whether the winner cleared it and was retired
    through the gate behind it depended on contact timing: at `DEPTH` 4.8 and
    5.6 it did, at 4.6, 5.0 and 5.2 it did not. There is no reading of that
    which is a design.
    """
    from marble3d.units import MARBLE_RADIUS

    radius = MARBLE_RADIUS * SIM_TO_LAYOUT
    fall = math.tan(math.radians(deck.FALL_DEG))
    worst = 0.0
    for marble, crossing in CROSSINGS.items():
        for index in range(int(round(crossing * FPS)), FILM_FRAMES):
            point = fixed_replay["frames"][index]["marbles"][marble]["p"]
            world = [float(point[axis]) * SIM_TO_LAYOUT for axis in range(3)]
            offset = [world[axis] - deck.origin[axis] for axis in range(3)]
            along = offset[0] * deck.forward[0] + offset[2] * deck.forward[2]
            worst = max(worst, offset[1] + fall * max(along, 0.0))
    assert worst + radius <= deck.RIM, (worst, deck.RIM)
    # And with room to spare rather than by a rounding: the rim is set above
    # the worst rebound seen anywhere over `DEPTH` 3.0 to 3.6, not just at the
    # depth that ships, because the rebound does not settle down as the deck
    # is tuned.
    assert deck.RIM - (worst + radius) >= 0.5 * radius, (worst, deck.RIM)


def test_the_post_finish_report_says_nobody_is_stranded():
    report = _read(_need(os.path.join(DOCS, "post_finish.json"),
                         "the post-finish report"))
    after = report["by_build"]["v331"]
    before = report["by_build"]["v33"]
    assert after["unsupported_frames"] == 0
    assert after["frozen_frames"] == 0
    assert after["retired"] == []
    assert before["unsupported_frames"] > 0
    assert before["frozen_frames"] > 0


def test_the_convention_report_covers_cardinals_and_diagonals():
    report = _read(_need(os.path.join(DOCS, "convention.json"),
                         "the convention report"))
    bearings = {row["bearing"] for row in report["rows"]}
    assert {"+X", "-X", "+Z", "-Z"} <= bearings
    assert len(bearings) >= 6
    assert report["worst_dot"] == pytest.approx(1.0, abs=1e-9)
    for row in report["rows"]:
        assert abs(row["old_dot"]) < 1e-9, row["bearing"]
