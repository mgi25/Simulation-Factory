"""Regression tests for the Neon machine's deck builder.

The V1 report ended with a limitation the V1.1 brief promotes to a
requirement: the builder that derives every stretch of drawn track from the
simulation's walls lives in GDScript, nothing in this suite can reach GDScript,
and it had already shipped two defects that put marbles over nothing.

`rendering/deck_geometry.py` is that builder in Python - a transcription, not a
re-derivation - and this file is what makes keeping it worth anything. It is
in two halves.

**The port and the scene must not drift.** Every constant the two share is
parsed out of `neon_scene.gd` and asserted, and the three lines that carry the
fixes for the historical defects are asserted to still be there. A value edited
on one side and not the other, or a fix deleted, fails here rather than in a
render nobody measures.

**The geometry must hold on a real race.** The rest replays seed 7 through the
port and asks the questions the brief names: does a leaning wall get a deck of
the width it actually has, does a change in channel count leave anything
unswept, is every ribbon continuous, is a racer ever over open air, and is deck
ever swept where there is no channel.
"""

from __future__ import annotations

import math
import os
import re

import pytest

from race.config import RACER_RADIUS
from race.courses.neon import (
    BRIDGE_HALF_WIDTH,
    LANE_COUNT,
    LANE_RIB,
    LANE_WIDTH,
    NEON_COURSE_ID,
    NEON_RACER_COUNT,
    SURFACE,
    bridge_centre_x,
    lane_bounds,
    rib_centres,
)
from rendering import deck_geometry as dg
from replay.race_exporter import record_race
from tools import neon_proof

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_PATH = os.path.join(PROJECT_ROOT, "godot", "scripts", "neon_scene.gd")

PROOF_SEED = neon_proof.DEFAULT_SEED

# How far past its walls each section's deck is drawn, matching the calls in
# `neon_scene.gd`'s `build()`. The throat's is negative: the drain is a hole cut
# in the bowl at exactly the radius of the throat's walls, so a throat that
# reached past them would meet the bowl's floor at its own height.
SECTION_MARGINS = {
    "start": 12.0,      # BAY_MARGIN - the ribs are only 90px wide
    "chute": dg.DECK_MARGIN,
    "throat": -8.0,
    "bridge": dg.DECK_MARGIN,
    "finish": dg.DECK_MARGIN,
}


@pytest.fixture(scope="module")
def replay() -> dict:
    return record_race(
        PROOF_SEED, course_name=NEON_COURSE_ID, racer_count=NEON_RACER_COUNT
    )


@pytest.fixture(scope="module")
def course(replay: dict) -> dict:
    """The course as the *renderer* sees it: plain dicts out of the replay.

    Deliberately not `RaceCourse`. The GDScript reads the exported dictionaries
    and so does the port, and a test that fed the port richer objects than the
    scene gets would be testing something the scene cannot do.
    """
    return replay["course"]


@pytest.fixture(scope="module")
def scene_source() -> str:
    with open(SCENE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def scene_constant(source: str, name: str) -> float:
    """One `const NAME := value` out of the Godot scene, as a number.

    The trailing comment is optional because several of these carry one, and a
    constant that is documented on its own line should not be harder to read
    than one that is not.
    """
    found = re.search(
        rf"^const {name} := (-?[0-9.]+)\s*(?:#.*)?$", source, re.MULTILINE
    )
    assert found, f"{name} is not a plain constant in neon_scene.gd"
    return float(found.group(1))


def ribbons_of(course: dict, section: str) -> list[list[dg.Sample]]:
    margin = SECTION_MARGINS[section]
    return [
        dg.widen(run, -margin, margin) for run in dg.deck_ribbons(course, section)
    ]


# --- the port and the scene must not drift ----------------------------------


def test_the_scene_and_the_port_agree_on_every_shared_constant(scene_source: str):
    """The one thing that makes a port worth keeping.

    Every number the two implementations share, in one assertion, so a value
    edited on one side and not the other is a failing test rather than a deck
    that is quietly the wrong shape.
    """
    shared = {
        "DECK_MARGIN": dg.DECK_MARGIN,
        "DECK_STEP": dg.DECK_STEP,
        "MIN_SPAN": dg.MIN_SPAN,
        "EDGE_SMOOTHING": float(dg.EDGE_SMOOTHING),
        "WALL_SIN_MIN": dg.WALL_SIN_MIN,
    }
    for name, expected in shared.items():
        assert scene_constant(scene_source, name) == expected, name


def test_the_scene_still_carries_the_three_fixes_the_port_was_written_for(
    scene_source: str,
):
    """Three lines, each of which was a bug that drew marbles over nothing.

    Asserting on source text is a blunt instrument and it is the right one
    here: these are not behaviours this suite can reach, and every one of them
    is a line somebody could delete while tidying without the render obviously
    breaking.
    """
    # The wall is clipped against the plane, not measured by its extent.
    assert "var t := (y - here.y) / (next.y - here.y)" in scene_source
    # Runs close and open on one plane where the channel count changes.
    assert "var seam := (previous + y) * 0.5" in scene_source
    # Every run that reaches a section's plane is carried to it.
    assert "run.append(Vector3(tail.x, tail.y, bounds.y))" in scene_source


# --- a wall is measured where the plane cuts it -----------------------------


def test_a_leaning_wall_is_measured_at_the_height_it_is_asked_about():
    """The first defect, as a unit test.

    A box leaning at forty-five degrees is at a different x at every y, and the
    deck under it has to be too. Measuring it by its axis-aligned extent gives
    the same answer at every height - which is how the V1 finish apron, one
    long ramp per side flaring from 300 pixels wide to 810, came out as a deck
    of one constant width with six of sixteen racers standing in the void
    beside the rails.
    """
    spec = {
        "type": "box",
        "x": 0.0,
        "y": 0.0,
        "width": 200.0 * math.sqrt(2.0),
        "height": 40.0,
        "rotation_degrees": 45.0,
    }
    # Sixty either side of the middle, which is inside the run of the long
    # faces - a cut nearer the ends crosses an end cap instead and measures
    # the bevel rather than the wall.
    low = dg.piece_span(spec, -60.0)
    middle = dg.piece_span(spec, 0.0)
    high = dg.piece_span(spec, 60.0)
    assert low is not None and middle is not None and high is not None
    centres = [(span[0] + span[1]) * 0.5 for span in (low, middle, high)]
    # The centre tracks the lean: sixty down the wall is sixty across it,
    # because the wall leans at forty-five degrees.
    assert centres[0] == pytest.approx(-60.0, abs=2.0)
    assert centres[1] == pytest.approx(0.0, abs=2.0)
    assert centres[2] == pytest.approx(60.0, abs=2.0)
    # ...and the width stays the box's own thickness across the lean, not its
    # whole diagonal, which is what the axis-aligned reading would have given.
    for span in (low, middle, high):
        assert span[1] - span[0] == pytest.approx(56.6, abs=2.0)


def test_a_wall_that_does_not_reach_the_plane_blocks_nothing():
    spec = {
        "type": "box", "x": 0.0, "y": 0.0,
        "width": 100.0, "height": 40.0, "rotation_degrees": 90.0,
    }
    assert dg.piece_span(spec, 0.0) is not None
    assert dg.piece_span(spec, 400.0) is None


def test_a_circle_contributes_its_chord_rather_than_its_diameter():
    spec = {"type": "circle", "x": 0.0, "y": 0.0, "radius": 100.0}
    middle = dg.piece_span(spec, 0.0)
    edge = dg.piece_span(spec, 80.0)
    assert middle == pytest.approx((-100.0, 100.0))
    assert edge is not None
    assert edge[1] - edge[0] == pytest.approx(120.0, abs=1.0)
    assert dg.piece_span(spec, 140.0) is None


def test_a_near_horizontal_piece_is_a_floor_and_not_a_wall():
    """Otherwise the finish apron's own floor is read as a wall right across
    the section it is the floor of."""
    floor = {
        "type": "box", "x": 0.0, "y": 0.0,
        "width": 800.0, "height": 26.0, "rotation_degrees": 0.0,
    }
    assert dg.piece_span(floor, 0.0) is None
    leaning = dict(floor, rotation_degrees=30.0)   # sin 0.5, past the threshold
    assert dg.piece_span(leaning, 0.0) is not None


# --- only channels get decks ------------------------------------------------


def test_a_gap_open_to_one_side_is_not_a_channel():
    """The open air beside the machine is not track.

    The first version of the builder paved anything clear, including the space
    outside the outermost wall: the V0 chute came out ten units wide with the
    spouts drawn as scratches on it.
    """
    pieces = [
        {"type": "box", "section": "s", "x": 0.0, "y": 0.0,
         "width": 100.0, "height": 40.0, "rotation_degrees": 90.0},
        {"type": "box", "section": "s", "x": 400.0, "y": 0.0,
         "width": 100.0, "height": 40.0, "rotation_degrees": 90.0},
    ]
    spans = dg.clear_spans(pieces, "s", 0.0)
    assert len(spans) == 1
    assert spans[0] == pytest.approx((20.0, 380.0))


def test_a_gap_narrower_than_a_racer_is_not_a_channel():
    """`MIN_SPAN` rejects the slivers a conservative wall measurement leaves
    either side of a joint."""
    pieces = [
        {"type": "box", "section": "s", "x": 0.0, "y": 0.0,
         "width": 100.0, "height": 40.0, "rotation_degrees": 90.0},
        {"type": "box", "section": "s", "x": 60.0, "y": 0.0,
         "width": 100.0, "height": 40.0, "rotation_degrees": 90.0},
        {"type": "box", "section": "s", "x": 400.0, "y": 0.0,
         "width": 100.0, "height": 40.0, "rotation_degrees": 90.0},
    ]
    spans = dg.clear_spans(pieces, "s", 0.0)
    assert len(spans) == 1, "the 40px sliver between the first two is not track"
    assert dg.MIN_SPAN >= 2.0 * RACER_RADIUS


def test_the_gaps_between_the_launch_channels_are_never_paved(course: dict):
    """The ribs are the whole point of the launch section.

    A rib is a strip with no deck over it, and a strip with no deck over it is
    where the structure underneath shows through. If the deck margins ever grew
    enough to close them, the four channels would silently become one apron
    again - which is the thing this revision exists to remove.
    """
    ribbons = ribbons_of(course, "chute")
    for rib in rib_centres()[::2]:      # the two that stop at the merge
        covered = [
            run for run in ribbons
            if dg.covered([run], rib, 800.0, 0.0)
        ]
        assert not covered, f"the rib at x={rib} has deck over it"
    # ...and the gap left is wide enough to read as a gap rather than a seam.
    assert LANE_RIB - 2.0 * dg.DECK_MARGIN > 0.0


# --- the channels themselves ------------------------------------------------


def test_the_launch_section_is_four_channels_and_then_two(course: dict):
    """The shape the brief asks for, measured rather than asserted in a
    comment: four narrow lanes, merging in pairs into two feed spouts."""
    ribbons = dg.deck_ribbons(course, "chute")
    lanes = [run for run in ribbons if run[0][1] - run[0][0] < LANE_WIDTH * 1.4]
    feeds = [run for run in ribbons if run not in lanes]
    assert len(lanes) == LANE_COUNT
    assert len(feeds) == 2
    for index, run in enumerate(sorted(lanes, key=lambda r: r[0][0])):
        left, right = lane_bounds(index)
        assert run[0][0] == pytest.approx(left, abs=1.0)
        assert run[0][1] == pytest.approx(right, abs=1.0)


def test_the_platform_is_four_bays_over_the_four_channels(course: dict):
    """The ribs are carried up through the start section, so the field stands
    in the channels it is about to be released into."""
    ribbons = dg.deck_ribbons(course, "start")
    assert len(ribbons) == LANE_COUNT
    for index, run in enumerate(sorted(ribbons, key=lambda r: r[0][0])):
        left, right = lane_bounds(index)
        assert run[0][0] == pytest.approx(left, abs=1.0)
        assert run[0][1] == pytest.approx(right, abs=1.0)


def test_changing_the_channel_count_leaves_nothing_unswept(course: dict):
    """The second defect, and the one that shipped inside the V1 video.

    Where the count of channels changes, the closing runs and the opening runs
    have to meet on *one* plane. Closing at the last sample and opening at the
    next leaves a full sample step with nothing swept between - and because
    every run is capped at both ends, that is an open slot right across the
    deck rather than a seam. The whole field of sixteen was drawn crossing it.
    """
    ribbons = dg.deck_ribbons(course, "chute")
    closing = max(run[-1][2] for run in ribbons if run[-1][2] < 1300.0)
    opening = min(run[0][2] for run in ribbons if run[0][2] > 900.0)
    assert opening == pytest.approx(closing, abs=1.0e-6), (
        "the merge leaves a step of deck unswept"
    )


def test_every_ribbon_is_continuous_along_its_own_length(course: dict):
    """No one-sample gaps, and no jump in width that a racer could fall down.

    A ribbon is swept between consecutive cross-sections, so a gap in `z` is a
    gap in the deck. The tolerance is one sampling step plus a hair, which is
    what the head and tail extensions to a section's own planes cost.
    """
    for section in ("start", "chute", "throat", "bridge", "finish"):
        for run in dg.deck_ribbons(course, section):
            assert len(run) >= 2, f"{section} has a one-sample ribbon"
            for here, nxt in zip(run, run[1:]):
                step = nxt[2] - here[2]
                assert 0.0 < step <= dg.DECK_STEP + 2.5, (
                    f"{section} has a {step:.1f}px gap at z={here[2]:.0f}"
                )
                # A channel that changes width faster than this is a wall the
                # sweep is cutting a corner on rather than following.
                for edge in (0, 1):
                    assert abs(nxt[edge] - here[edge]) < 90.0, (
                        f"{section} jumps {abs(nxt[edge] - here[edge]):.0f}px"
                        f" at z={here[2]:.0f}"
                    )


def test_every_section_is_swept_to_its_own_planes(course: dict):
    """The seams between two stretches of track are closed.

    The sweep stops two pixels short of a section's bottom - at the plane
    itself this section's walls have ended and the next section's have begun,
    which reads as a change of channel count and splits every run. Carrying
    each run that reaches that plane on to it is what closes the gap, and the
    gap is where a racer would be standing over nothing.
    """
    for section in ("chute", "throat", "bridge"):
        bounds = dg.section_bounds(course, section)
        assert bounds is not None
        ribbons = dg.deck_ribbons(course, section)
        assert min(run[0][2] for run in ribbons) == pytest.approx(bounds[0], abs=1.0)
        assert max(run[-1][2] for run in ribbons) == pytest.approx(bounds[1], abs=1.0e-6)


def test_smoothing_leaves_the_curve_where_the_wall_put_it(course: dict):
    """The scallop remover has to move the joints and nothing else.

    A wall is a chain of straight boxes that overlap, so the clear width has a
    shallow corner at each joint; averaging over a window a little wider than
    one box removes them. What it must not do is move the *curve*, which is two
    orders of magnitude longer.

    The bridge is the case that could go wrong, because its walls turn for
    their whole length - so this measures the swept deck's own centre line
    against `bridge_centre_x`, which is the function the walls were placed from
    and which the renderer never sees.

    Sixteen pixels is the bound, and it is a real number rather than a
    comfortable one: a moving average over seven samples of a curve pulls the
    extremes of that curve inwards, and at the crest of this S the measured
    worst case is fourteen. That is a quarter of a racer and the deck reaches
    thirty-two pixels past its walls either way, so the racing line is still
    well inside the drawn surface - which is the thing that has to be true.
    """
    for run in dg.deck_ribbons(course, "bridge"):
        for sample in run[2:-2]:
            centre = (sample[0] + sample[1]) * 0.5
            assert centre == pytest.approx(bridge_centre_x(sample[2]), abs=16.0)
            # The clear span is the channel less one wall thickness: the
            # walls are centred on the offset polyline, so half of each of
            # them is inside the channel.
            assert sample[1] - sample[0] == pytest.approx(
                2.0 * BRIDGE_HALF_WIDTH - SURFACE, abs=14.0
            )


# --- the invariant the whole builder exists for -----------------------------


def test_no_racer_is_ever_over_open_air(replay: dict, course: dict):
    """The one that matters, measured on a recorded race.

    Every racer outside the bowl, on every frame, has to be over drawn deck.
    Both of the builder's historical defects failed exactly here and nothing
    else in the pipeline would have noticed: a marble drawn standing on
    nothing is still a marble at the right coordinates.
    """
    metadata = course["metadata"]
    ribbons = {
        section: ribbons_of(course, section)
        for section in ("chute", "throat", "bridge")
    }
    checked = 0
    for frame in replay["frames"]:
        for racer in frame["racers"]:
            if racer["retired"]:
                continue
            y = racer["y"]
            if metadata["gate_y"] < y <= metadata["bowl_top"]:
                section = "chute"
            elif metadata["drain_y"] < y <= metadata["throat_end"]:
                section = "throat"
            elif metadata["throat_end"] < y <= metadata["bridge_end"]:
                section = "bridge"
            else:
                continue
            checked += 1
            assert dg.covered(ribbons[section], racer["x"], y, 0.0), (
                f"racer {racer['id']} is over nothing at"
                f" ({racer['x']:.0f}, {y:.0f}) in the {section}"
            )
    assert checked > 3000, "the race barely used the machine; check the course"


def test_no_racer_is_ever_over_a_rib(replay: dict, course: dict):
    """A racer between two launch channels would be standing in the gap.

    The ribs are solid in the simulation, so this cannot happen - which is
    exactly why it is worth asserting: it is the property that lets the drawn
    gaps be as wide as they are.
    """
    reach = RACER_RADIUS
    for frame in replay["frames"]:
        for racer in frame["racers"]:
            if racer["retired"] or not 740.0 < racer["y"] < 1000.0:
                continue
            for rib in rib_centres():
                assert abs(racer["x"] - rib) > LANE_RIB * 0.5 - reach, (
                    f"racer {racer['id']} is inside the rib at x={rib}"
                )
