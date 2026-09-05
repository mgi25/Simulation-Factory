"""V1 tests: the neon course, and the contract the visual proof rests on.

Two kinds of assertion live here, and only the second kind is unusual.

The first is the geometry the course was debugged into satisfying, exactly as
`test_race_course.py` does for the prototype: a drain wide enough that two
racers cannot arch across it, a spout wide enough to pour through, checkpoints
that go one way.

The second is the *presentation contract*. The renderer derives a marble's
height inside the bowl from its distance to the bowl's centre, and builds the
bowl mesh from the same function - so a racer sits on the surface by
construction rather than by tuning. That only holds while every point a racer
can reach inside the bowl is inside the disc the mesh covers. It is a property
of the course, it is invisible from anywhere else in this project, and if it
ever stops being true the failure is sixteen marbles hanging in mid-air. So it
is asserted here, against a recorded race rather than against the geometry
alone: what matters is where racers actually go.

There is no test of the GDScript itself - Godot is not in this test run - but
the two numbers Python and GDScript have to agree on are checked by reading
the scene file, because a camera comparison shot at one elevation and shipped
at another would be a silent lie in the report.
"""

from __future__ import annotations

import math
import os
import re
import sys

import pytest

from engine.arena import CANVAS_WIDTH
from race.config import RACER_RADIUS
from race.course import ROLE_GATE, RaceCourse
from race.courses import COURSE_NAMES, build_course
from race.courses.neon import (
    BOWL_CENTRE_X,
    BOWL_CENTRE_Y,
    BOWL_RADIUS,
    BOWL_TOP,
    DRAIN_HALF,
    LANE_COUNT,
    LANE_RIB,
    LANE_WIDTH,
    NEON_COURSE_ID,
    NEON_RACER_COUNT,
    NEON_SECTIONS,
    PLATFORM_LEFT,
    PLATFORM_RIGHT,
    SPOUT_INNER,
    SPOUT_OUTER,
    THROAT_END,
    bridge_centre_x,
    lane_bounds,
)
from rendering.deck_geometry import DECK_MARGIN
from replay.race_exporter import record_race
from tools import neon_proof

RACER_DIAMETER = 2.0 * RACER_RADIUS

# The renderer clamps a bowl radius at this, and draws a flat lip out to it.
# Anything past it is a racer standing on nothing, so it is the number the
# recorded race is measured against. It mirrors `FLANGE_OUTER` in
# `neon_scene.gd`; `test_the_scene_and_the_tool_agree_on_the_lip` keeps the two
# from drifting apart.
#
# V1.1 widened it from 1.16, because the acrylic wall now stands on the flange
# and a flange with a wall bolted to it wants some width to bolt it to.
FLANGE_OUTER = 1.20

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_PATH = os.path.join(PROJECT_ROOT, "godot", "scripts", "neon_scene.gd")

# One seed, used by every test that needs a race rather than a course. The
# proof ships on it, so it is the run the invariants are worth proving on.
PROOF_SEED = neon_proof.DEFAULT_SEED


@pytest.fixture(scope="module")
def course() -> RaceCourse:
    return build_course(NEON_COURSE_ID, PROOF_SEED)


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_race(
        PROOF_SEED, course_name=NEON_COURSE_ID, racer_count=NEON_RACER_COUNT
    )


def scene_constant(name: str) -> float:
    """One `const NAME := value` out of the Godot scene, as a number."""
    with open(SCENE_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    found = re.search(rf"^const {name} := (-?[0-9.]+)$", source, re.MULTILINE)
    assert found, f"{name} is not a plain constant in neon_scene.gd"
    return float(found.group(1))


# --- the course exists and is reachable -------------------------------------


def test_the_neon_course_is_in_the_registry():
    assert NEON_COURSE_ID in COURSE_NAMES
    assert build_course(NEON_COURSE_ID, 1).course_id == NEON_COURSE_ID


def test_the_course_is_the_same_whatever_seed_it_is_built_for():
    """No seeded geometry at all, which is what makes the proof repeatable."""
    one = build_course(NEON_COURSE_ID, 1)
    other = build_course(NEON_COURSE_ID, 999)
    assert [piece.spec for piece in one.pieces] == [
        piece.spec for piece in other.pieces
    ]
    assert one.spinners == other.spinners
    assert one.metadata == other.metadata


def test_the_sections_are_the_three_the_brief_asks_for_and_their_joins():
    """Start, bowl and bridge, plus the chute, throat and catch between them."""
    course = build_course(NEON_COURSE_ID, PROOF_SEED)
    names = tuple(section.name for section in course.sections)
    assert names == NEON_SECTIONS
    for section in course.sections:
        assert section.height > 0.0, f"{section.name} has no extent"
    for earlier, later in zip(course.sections, course.sections[1:]):
        assert earlier.bottom == later.top, "sections must meet, not overlap or gap"


def test_the_grid_holds_the_whole_field(course: RaceCourse):
    assert len(course.spawns) == NEON_RACER_COUNT
    assert 12 <= NEON_RACER_COUNT <= 16
    for spawn in course.spawns:
        assert 0.0 < spawn.x < CANVAS_WIDTH
        assert spawn.y < course.metadata["gate_y"]


def test_there_is_exactly_one_gate_and_it_spans_the_platform(course: RaceCourse):
    gates = [piece for piece in course.pieces if piece.role == ROLE_GATE]
    assert len(gates) == 1
    left, _, right, _ = gates[0].bounds()
    assert left == pytest.approx(course.metadata["platform_left"], abs=1.0)
    assert right == pytest.approx(course.metadata["platform_right"], abs=1.0)


def test_the_progress_ladder_only_goes_one_way(course: RaceCourse):
    heights = [checkpoint.y for checkpoint in course.checkpoints]
    assert heights == sorted(heights)
    assert len(set(heights)) == len(heights)
    assert course.finish.y < course.bottom


# --- the openings are wide enough not to jam --------------------------------


def test_the_drain_is_too_wide_for_two_racers_to_arch_across():
    """Two diameters plus a margin, which is the threshold the other courses
    in this project found the hard way."""
    assert 2.0 * DRAIN_HALF > 2.0 * RACER_DIAMETER + 40.0


def test_each_spout_takes_more_than_two_racers_abreast():
    assert SPOUT_OUTER - SPOUT_INNER > 2.0 * RACER_DIAMETER


def test_the_s_curve_stays_inside_the_playable_width():
    """The bridge's outer wall plus a rail has to clear the boundary."""
    extremes = [bridge_centre_x(y) for y in range(2200, 3801, 20)]
    assert max(extremes) < CANVAS_WIDTH - 150.0
    assert min(extremes) > 150.0


# --- the presentation contract ----------------------------------------------


def bowl_rho(x: float, y: float) -> float:
    return math.hypot(x - BOWL_CENTRE_X, y - BOWL_CENTRE_Y) / BOWL_RADIUS


def test_the_bowl_section_geometry_is_inside_the_disc(course: RaceCourse):
    """Every corner of every piece in the bowl, inside the radius.

    The walls are what a racer rests on, so a wall outside the disc is a racer
    outside it a tick later.
    """
    for piece in course.pieces:
        if piece.section != "bowl":
            continue
        for x, y in piece.spec.corners():
            assert bowl_rho(x, y) <= 1.0, f"piece {piece.piece_id} leaves the bowl"


def test_the_bowl_seam_is_the_top_of_the_disc():
    """The plane the spouts hand over at has to be exactly a radius above the
    centre, or a racer arriving in the middle of it starts halfway down the
    bowl instead of on its rim."""
    assert BOWL_TOP == pytest.approx(BOWL_CENTRE_Y - BOWL_RADIUS)


def test_no_racer_ever_leaves_the_drawn_bowl(replay: dict):
    """The load-bearing invariant, measured on a real race.

    A racer inside the bowl section is drawn on the bowl surface at its own
    radius, clamped to the lip. Past the lip there is no mesh, so a racer that
    got there would be drawn standing on nothing.
    """
    worst = 0.0
    seen = 0
    for frame in replay["frames"]:
        for racer in frame["racers"]:
            if not BOWL_TOP <= racer["y"] <= BOWL_CENTRE_Y:
                continue
            seen += 1
            worst = max(worst, bowl_rho(racer["x"], racer["y"]))
    assert seen > 200, "the race barely used the bowl; check the course"
    assert worst <= FLANGE_OUTER, f"a racer reached radius {worst:.3f}"


def test_racers_only_ever_leave_the_bowl_through_the_drain(replay: dict):
    """Nobody crosses the drain plane anywhere but the drain.

    The mapping eases the throat away from the bowl's surface at each point,
    so it is continuous across the drain plane for every x - but the *throat
    channel* is only 220 pixels wide, and a racer that got past the plane
    outside it would be drawn under the bowl's far wall with the bowl's own
    surface on top of it. The geometry is what prevents that, so the geometry
    is what is asserted.
    """
    centre = BOWL_CENTRE_X
    reach = DRAIN_HALF + RACER_RADIUS
    for frame in replay["frames"]:
        for racer in frame["racers"]:
            if racer["retired"]:
                continue
            if BOWL_CENTRE_Y < racer["y"] <= THROAT_END:
                assert abs(racer["x"] - centre) <= reach, (
                    f"racer {racer['id']} is past the drain plane at"
                    f" x={racer['x']:.0f}, outside the throat"
                )


def test_the_bowl_actually_holds_the_field(replay: dict):
    """At its fullest, most of the field is in the bowl at once.

    Not a physics assertion - a *proof* assertion. The still the brief asks
    for is 'racers inside the bowl', and a bowl that never has more than three
    racers in it cannot produce one.
    """
    fullest = max(
        sum(
            1
            for racer in frame["racers"]
            if BOWL_TOP <= racer["y"] <= BOWL_CENTRE_Y + 80.0
        )
        for frame in replay["frames"]
    )
    assert fullest >= NEON_RACER_COUNT * 0.6


def test_the_race_finishes_cleanly_with_nobody_rescued(replay: dict):
    """A recovery teleports a racer, and a teleport in a seven second proof is
    the one thing a viewer would certainly notice."""
    result = replay["result"]
    assert result["racers_finished"] == len(replay["racers"])
    assert result["retirements"] == 0
    assert result["recoveries"] == 0
    assert not result["timed_out"]


def test_the_course_exports_everything_the_renderer_is_told(course: RaceCourse):
    """The scene reads the bowl out of the metadata rather than knowing it."""
    required = {
        "bowl_centre_x",
        "bowl_centre_y",
        "bowl_radius",
        "bowl_top",
        "drain_half",
        "drain_y",
        "gate_y",
        "platform_left",
        "platform_right",
        "platform_top",
        "throat_end",
        "bridge_top",
        "bridge_end",
    }
    assert required <= set(course.metadata)
    assert course.metadata["bowl_radius"] > 0.0
    assert course.metadata["platform_left"] < course.metadata["platform_right"]
    assert course.metadata["bridge_top"] < course.metadata["bridge_end"]


# --- the proof tool ---------------------------------------------------------


def test_the_video_is_the_length_the_brief_asks_for(replay: dict):
    start, count = neon_proof.video_window(replay)
    seconds = count / 60.0
    assert 5.0 <= seconds <= 8.0
    assert start >= 0
    assert start + count <= len(replay["frames"])


def test_the_video_opens_before_the_release_and_reaches_the_bridge(replay: dict):
    start, count = neon_proof.video_window(replay)
    gate = neon_proof.gate_frame(replay)
    assert start < gate, "the proof has to open on the platform"
    last = replay["frames"][start + count - 1]
    furthest = max(racer["y"] for racer in last["racers"])
    assert furthest > replay["course"]["metadata"]["bridge_top"]


def test_the_camera_sweep_is_the_angles_the_brief_names():
    """48, 52 and 55, which is what V1.1 asks to be compared.

    V1 swept 42 to 56 to find the range; those two ends are settled - 42 hides
    the bridge's supports behind the deck and 56 flattens the bowl towards a
    plan of itself - so this revision compares inside the range rather than
    re-deciding it.
    """
    assert neon_proof.CAMERA_ANGLES == (48.0, 52.0, 55.0)
    assert neon_proof.SELECTED_ELEVATION in neon_proof.CAMERA_ANGLES


def test_the_scene_ships_on_the_elevation_the_tool_selects():
    """A comparison shot at one angle and delivered at another is a silent
    lie, and nothing else in the pipeline would catch it."""
    assert scene_constant("CAM_ELEVATION") == neon_proof.SELECTED_ELEVATION


def test_the_scene_and_the_tool_agree_on_the_lip():
    assert scene_constant("FLANGE_OUTER") == FLANGE_OUTER


def test_every_section_still_the_brief_asks_for_is_produced(replay: dict):
    wanted = {name for name, _ in neon_proof.SECTION_MOMENTS}
    assert wanted == {
        "start_platform",
        "entering_bowl",
        "inside_bowl",
        "bowl_exit",
        "s_curve_bridge",
    }
    for _, at in neon_proof.SECTION_MOMENTS:
        index = neon_proof.moment_frame(replay, at)
        assert 0 <= index < len(replay["frames"])


def test_the_godot_command_selects_the_prototype_scene():
    command = neon_proof.godot_command(
        "godot", "replay.json", "out", 100, 52.0, (1, 2), "flag"
    )
    assert "--race-style=neon" in command
    assert "--race-elevation=52" in command
    assert "--stills=1,2" in command
    assert "--neon-countries=flag" in command


def test_the_plain_treatment_asks_for_no_country_badges_at_all():
    """The 'number' arm of the comparison is the scene's own default.

    It has to be: the comparison is only about the badge, so the control has
    to be the thing that ships rather than a third treatment that happens to
    look like it.
    """
    command = neon_proof.godot_command(
        "godot", "replay.json", "out", 100, 52.0, (1,), ""
    )
    assert not [arg for arg in command if arg.startswith("--neon-countries")]


def test_a_missing_godot_is_reported_rather_than_raised(monkeypatch, capsys):
    """One line and exit 1, not a traceback.

    `find_godot` is borrowed from `render_replay.py` and raises *its* error,
    which is a sibling of this tool's rather than an ancestor - so it is the
    one exception a caller can trigger from the command line that the handler
    could plausibly miss.
    """
    monkeypatch.setattr(
        sys, "argv", ["neon_proof.py", "--cameras", "--godot", "C:/nope.exe"]
    )
    assert neon_proof.main() == 1
    captured = capsys.readouterr()
    assert "nope.exe" in captured.err
    assert "Traceback" not in captured.err


def test_the_replay_viewer_knows_how_to_reach_the_prototype_scene():
    path = os.path.join(PROJECT_ROOT, "godot", "scripts", "replay_viewer.gd")
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "--race-style=" in source
    assert "neon_scene.gd" in source


# --- the launch channels ----------------------------------------------------


def test_the_start_is_four_channels_of_the_width_the_brief_asks_for():
    """Several narrow lanes rather than one giant slab, measured.

    V1's chute was one apron eight hundred and ninety pixels wide. The four
    channels are what replace it, and the two numbers that matter are the
    lane - wide enough for racers to pass each other - and the rib, which has
    to be wide enough that the two decks either side of it still leave a gap
    once each has reached its rail's width past its own wall.
    """
    assert LANE_COUNT == 4
    assert LANE_WIDTH > 2.0 * RACER_DIAMETER
    assert LANE_RIB > 2.0 * DECK_MARGIN
    for index in range(LANE_COUNT):
        left, right = lane_bounds(index)
        assert right - left == pytest.approx(LANE_WIDTH)
        assert PLATFORM_LEFT <= left < right <= PLATFORM_RIGHT
    for earlier, later in zip(range(LANE_COUNT), range(1, LANE_COUNT)):
        gap = lane_bounds(later)[0] - lane_bounds(earlier)[1]
        assert gap == pytest.approx(LANE_RIB)


def test_the_channels_and_the_platform_are_the_same_block():
    """A marble leaving the platform is already over a lane."""
    assert lane_bounds(0)[0] == pytest.approx(PLATFORM_LEFT)
    assert lane_bounds(LANE_COUNT - 1)[1] == pytest.approx(PLATFORM_RIGHT)


def test_every_starting_slot_stands_inside_a_lane_with_room_to_spare(
    course: RaceCourse,
):
    """The grid is derived from the channels, so it cannot drift off them.

    Four racers to a bay is also what makes 'synchronised lane release' mean
    anything: the gate opens once and four channels empty at the same instant.
    """
    per_lane = [0] * LANE_COUNT
    for spawn in course.spawns:
        inside = [
            index
            for index in range(LANE_COUNT)
            if lane_bounds(index)[0] + RACER_RADIUS
            <= spawn.x
            <= lane_bounds(index)[1] - RACER_RADIUS
        ]
        assert len(inside) == 1, f"spawn at x={spawn.x} is not in exactly one lane"
        per_lane[inside[0]] += 1
    assert per_lane == [NEON_RACER_COUNT // LANE_COUNT] * LANE_COUNT


def test_the_feed_spouts_stay_inside_the_drawn_bowl():
    """Where the chute hands over, every point has to be on the flange.

    A racer arriving at the seam plane is at bowl radius `hypot(dx, R) / R`,
    and the renderer draws the bowl out to `FLANGE_OUTER` and no further. This
    is the same argument the V1 report made for `SPOUT_OUTER`, re-checked
    because V1.1 moved both numbers.
    """
    reach = SPOUT_OUTER - RACER_RADIUS
    worst = math.hypot(reach, BOWL_RADIUS) / BOWL_RADIUS
    assert worst < FLANGE_OUTER, f"a racer at the spout edge is at rho {worst:.3f}"


def test_the_course_exports_the_channels_to_the_renderer(course: RaceCourse):
    """The scene builds the bays, the gate blades and the frame under the
    channels from these, rather than counting clear spans and hoping."""
    for key in ("lane_count", "lane_width", "lane_rib", "lane_end_y",
                "splitter_y", "converge_end_y", "spout_y",
                "spout_inner", "spout_outer"):
        assert key in course.metadata
    assert course.metadata["lane_count"] == float(LANE_COUNT)
    assert course.metadata["lane_width"] == LANE_WIDTH
    assert course.metadata["spout_inner"] < course.metadata["spout_outer"]


# --- the presentation contract, after the revision --------------------------


def test_the_throat_window_covers_ground_no_racer_can_stand_on(replay: dict):
    """The window in the far half of the bowl's floor costs no racing surface.

    Two halves to that, and they are different kinds of claim.

    The first is geometry: the window is a sector centred on the point of the
    disc furthest from the lens, so every point of it is past the drain plane.
    The second is the mapping: `deck_height` sends anything past the drain
    plane down the *throat*, below the floor, so the far half of the disc is
    scenery and nothing is ever drawn standing on it.

    Both are asserted, because if either stopped holding the failure would be
    marbles rolling across a sheet of glass.
    """
    half = math.radians(scene_constant("THROAT_WINDOW_HALF"))
    inner = scene_constant("THROAT_WINDOW_INNER")
    assert half < math.pi / 2.0 and inner > 0.0
    # The nearest point of the sector to the drain plane, in course pixels.
    nearest = BOWL_CENTRE_Y + inner * BOWL_RADIUS * math.cos(half)
    assert nearest > BOWL_CENTRE_Y

    with open(SCENE_PATH, "r", encoding="utf-8") as handle:
        source = handle.read()
    mapping = "if sim_y <= _drain_y:\n\t\treturn bowl_surface_y"
    assert mapping in source, (
        "the mapping no longer sends everything past the drain down the throat"
    )

    # ...and the window is a window onto something: the field does cross it.
    seen = 0
    for frame in replay["frames"]:
        for racer in frame["racers"]:
            if racer["retired"]:
                continue
            rho = bowl_rho(racer["x"], racer["y"])
            if racer["y"] > BOWL_CENTRE_Y and inner <= rho <= scene_constant(
                "THROAT_WINDOW_OUTER"
            ):
                seen += 1
    assert seen > 200, "nothing ever passes under the window"


def test_the_scene_reads_the_window_from_the_same_disc_the_bowl_is_built_on():
    """The window's radii are fractions of the bowl radius, so a bowl that
    moved would take its own window with it."""
    inner = scene_constant("THROAT_WINDOW_INNER")
    outer = scene_constant("THROAT_WINDOW_OUTER")
    assert 0.0 < inner < outer < 1.0
    # The throat runs from the drain to `throat_end`, which is this far out.
    reach = (THROAT_END - BOWL_CENTRE_Y) / BOWL_RADIUS
    assert outer > reach, "the window stops before the throat does"


def test_the_cradle_stands_outside_the_flange_it_is_holding():
    """V1's hoop was inside the rim and invisible from any lens that can see
    into the bowl; the brief calls that out and this is the fix, as a number."""
    assert scene_constant("CRADLE_RHO") > FLANGE_OUTER


def test_the_acrylic_wall_stands_on_the_flange_and_leaves_the_field_a_way_in():
    """The gap in the glass has to be wider than the arc the spouts arrive on,
    or the feed would be drawn through it."""
    gap = scene_constant("GLASS_GAP_HALF")
    entry = math.degrees(math.atan2(SPOUT_OUTER, BOWL_RADIUS))
    assert gap > entry, f"the spouts reach {entry:.1f} degrees either side"


# --- the country experiment -------------------------------------------------


def test_the_experiment_compares_three_treatments_at_three_moments():
    assert neon_proof.COUNTRY_MODES == ("number", "flag", "code")
    assert len(neon_proof.COUNTRY_MOMENTS) == 3
    assert {label for label, _ in neon_proof.COUNTRY_MOMENTS} == {
        "start", "bowl", "bridge"
    }


def test_the_five_countries_are_the_ones_the_brief_names():
    """Read out of the GDScript, because that is where they are declared and a
    list that drifted would make the report describe a comparison nobody ran."""
    path = os.path.join(PROJECT_ROOT, "godot", "scripts", "neon_flags.gd")
    with open(path, "r", encoding="utf-8") as handle:
        source = handle.read()
    codes = re.findall(r'\{"code": "([A-Z]{3})"', source)
    assert codes == ["IND", "JPN", "BRA", "USA", "GER"]
    assert "albedo_texture" not in source, "no wrapped flags; the brief rules them out"


def test_the_badge_is_small_enough_not_to_own_the_marble():
    """A plate the size of the ball it labels is a label with a marble
    attached, and a pile-up of sixteen is where it would show."""
    plate = scene_constant("COUNTRY_PLATE_SIZE")
    assert plate < 2.0 * RACER_RADIUS / 100.0 * 1.2


# --- the hero stills the brief asks to be judged on -------------------------


def test_the_three_hero_moments_are_inside_the_video(replay: dict):
    """A hero still that is not a frame of the clip is a picture of something
    the viewer never sees."""
    start, count = neon_proof.video_window(replay)
    for name, at in neon_proof.HERO_MOMENTS:
        index = neon_proof.moment_frame(replay, at)
        assert start <= index < start + count, name


def test_the_hero_moments_are_one_per_section(replay: dict):
    """Each hero answers a different question, so each has to be somewhere
    different: over the platform, inside the bowl, out on the bridge."""
    metadata = replay["course"]["metadata"]
    wanted = {
        "start_hero": lambda y: y < metadata["bowl_top"],
        "bowl_hero": lambda y: metadata["bowl_top"] <= y <= metadata["drain_y"],
        "bridge_hero": lambda y: y > metadata["throat_end"],
    }
    for name, at in neon_proof.HERO_MOMENTS:
        frame = replay["frames"][neon_proof.moment_frame(replay, at)]
        heights = [racer["y"] for racer in frame["racers"] if not racer["retired"]]
        matching = sum(1 for y in heights if wanted[name](y))
        assert matching >= len(heights) * 0.5, (
            f"{name} at {at:+.1f}s has only {matching} of {len(heights)} racers"
            " where it says it does"
        )


def test_the_phone_preview_is_actually_phone_sized():
    """The brief asks explicitly not to judge only at desktop full-screen."""
    assert 0.2 <= neon_proof.PHONE_SCALE <= 0.35
    assert int(1080 * neon_proof.PHONE_SCALE) < 400
