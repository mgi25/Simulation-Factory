"""V19 rebuilds one lens. These pin what was wrong with V18's and what is not.

The V18 finish camera stood twenty layout units behind the leading pair at
twelve degrees of elevation, and twenty units behind this finish line is not
open air: the course doubles back through there. From 16.9 s of output to the
end of the film the lens was inside `orange`'s channel with the track body
across the frame. Every check the pipeline had passed, because every check the
pipeline had asks about the mountain, the aim or the frustum, and none of them
asks whether the *course* is in the way.

So `sloped.sightlines` answers that, and these tests hold three things:

* the check fails V18's finish and passes V19's, which is the regression;
* V19 changes **only** the finish - the other ten cuts and the whole edit map
  come out byte-identical, so the film before 15.75 s cannot have moved;
* every one of the six crossings inside the shot is unobstructed, which is what
  the lens was rebuilt for.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import cameras, layout, sightlines, terrain
from sloped.course import sloped_course

REPLAY = ROOT / "output" / "sloped_race_v1" / "race_5432.json"
WINDOW = (20.20, 23.60)


@pytest.fixture(scope="module")
def built():
    if not REPLAY.is_file():
        pytest.skip("the selected replay is not built")
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    machine = sloped_course(routes="both")
    config = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, config))
    )
    return {
        "replay": replay,
        "machine": machine,
        "bundle": bundle,
        "v18": cameras.build_track(replay, machine, fps=60, edit=cameras.EDIT_V18),
        "v19": cameras.build_track(replay, machine, fps=60, edit=cameras.EDIT_V19),
    }


def _finish(track):
    return [cut for cut in track["cuts"] if cut["name"] == "finish"][-1]


# --- the regression -------------------------------------------------------


def test_the_check_fails_v18s_finish(built):
    """The lens was in the course, and the check has to say so by name."""
    problems = sightlines.check_shot(
        built["v18"], built["replay"], built["machine"], built["bundle"]
    )
    assert problems, "the check passes the shot it exists to fail"
    joined = " ".join(problems)
    assert "orange" in joined, joined
    assert "lens is" in joined and "centre of the frame is blocked" in joined, joined


def test_v18s_lens_was_inside_the_channel(built):
    """0.15 layout units is a quarter of a marble's diameter."""
    rows = sightlines.shot_report(
        built["v18"], built["replay"], built["machine"], built["bundle"]
    )
    worst = min(row["clearance"] for row in rows)
    assert worst < 0.5, worst
    blocked = [row for row in rows if row["centre"] is not None]
    assert len(blocked) > len(rows) // 2, "the frame was obstructed for most of the shot"


def test_the_check_passes_v19s_finish(built):
    problems = sightlines.check_shot(
        built["v19"], built["replay"], built["machine"], built["bundle"]
    )
    assert problems == [], problems


def test_v19s_lens_stands_well_clear_of_everything(built):
    rows = sightlines.shot_report(
        built["v19"], built["replay"], built["machine"], built["bundle"]
    )
    worst = min(row["clearance"] for row in rows)
    assert worst > 10.0, worst
    assert all(row["centre"] is None for row in rows), "the frame is obstructed"


# --- the flip that put it there -------------------------------------------


def test_a_fixed_side_cannot_flip_mid_shot(built):
    """`terrain.lower_side` changed its mind and took the camera with it.

    V18's finish asked the ground which side to stand on every frame and got a
    different answer at `final[105]`, where the sprint reaches the finish mesa.
    The camera crossed seven layout units between two frames - a cut inside a
    shot - and landed where `orange` runs.
    """
    def worst_step(track):
        rows = _finish(track)["frames"]
        return max(math.dist(a[1:4], b[1:4]) for a, b in zip(rows, rows[1:]))

    assert worst_step(built["v18"]) > 5.0
    assert worst_step(built["v19"]) < 0.2


def test_side_zero_still_asks_the_terrain(built):
    """Every other cut keeps the behaviour it has always had."""
    for cut in cameras.SECTIONS:
        assert cut.side == 0, cut.name
    for cut in built["v19"]["cuts"]:
        if cut["name"] != "finish":
            assert cut["side"] == 0, cut["name"]
    assert _finish(built["v19"])["side"] == -1


# --- what V19 is allowed to have changed ----------------------------------


def test_v19_changes_only_the_finish(built):
    """The edit map is identical and ten of the eleven cuts are byte-identical."""
    a, b = built["v18"], built["v19"]
    assert a["edit"] == b["edit"], "the output clock moved"
    assert a["duration"] == b["duration"] == pytest.approx(19.15, abs=1e-6)
    assert len(a["cuts"]) == len(b["cuts"])
    changed = [
        one["name"]
        for one, two in zip(a["cuts"], b["cuts"])
        if json.dumps(one, sort_keys=True) != json.dumps(two, sort_keys=True)
    ]
    assert changed == ["finish"], changed


def test_the_finish_window_is_v18s(built):
    finish = [row for row in built["v19"]["edit"] if row["cut"] == "finish"][-1]
    assert finish["replay"] == pytest.approx(list(WINDOW), abs=1e-6)
    assert finish["out"] == pytest.approx([15.75, 19.15], abs=1e-6)


# --- the new lens ---------------------------------------------------------


def test_the_finish_line_node_comes_from_the_built_run(built):
    """Derived, so a course that moves its sprint moves the aim with it."""
    end = built["machine"].runs["final"].path[-1]
    aim = _finish(built["v19"])["frames"][0][4:7]
    assert aim[0] == pytest.approx(end[0], abs=1e-3)
    assert aim[1] == pytest.approx(end[1] + layout.MARBLE_RADIUS, abs=1e-3)
    assert aim[2] == pytest.approx(end[2], abs=1e-3)


def test_the_aim_is_the_line_rather_than_the_leading_pair(built):
    """`pair` ranks by progress, and a marble that has crossed has left the route.

    On this seed the V18 finish's own subject came out marbles 2 and 7 - second
    and third. The winner had already crossed at the cut's midpoint.
    """
    assert _finish(built["v18"])["target"] == "pair"
    assert _finish(built["v18"])["subject"] == [2, 7]
    assert _finish(built["v19"])["target"] == "node"
    assert _finish(built["v19"])["node"] == "finish_line"


def test_the_lens_is_an_outside_elevated_three_quarter(built):
    finish = _finish(built["v19"])
    assert 20.0 <= finish["bearing"] <= 45.0, finish["bearing"]
    # 40 degrees is a floor the FINISH gantry sets, 46 is this file's ceiling.
    assert 40.0 <= finish["elevation"] < cameras.MAX_ELEVATION, finish["elevation"]
    # Downstream of the line, looking back up the sprint at the field coming on.
    camera = finish["frames"][len(finish["frames"]) // 2][1:4]
    aim = finish["frames"][len(finish["frames"]) // 2][4:7]
    run = built["machine"].runs["final"]
    forward = run.tangents[len(run.path) - 1]
    along = sum(
        (camera[axis] - aim[axis]) * forward[axis] for axis in (0, 2)
    )
    assert along > 0.0, "the camera is up-course of the line, not downstream"
    # And laterally off the channel rather than on its axis.
    flat = math.hypot(forward[0], forward[2])
    side = (forward[2] / flat, -forward[0] / flat)
    across = abs((camera[0] - aim[0]) * side[0] + (camera[2] - aim[2]) * side[1])
    # Two channel widths off the axis: 7.27 layout units against a sprint whose
    # own clear width is 3.30, so the lens is nowhere near over the cradle.
    assert across > 2.0 * run.clear_width, across


def test_the_racers_are_larger_than_v17s(built):
    """V17 framed the finish at an extent of 24; the lens is closer than that."""
    default = {cut.name: cut for cut in cameras.SECTIONS}["finish"]
    assert default.extent == 24.0, "V17's finish extent moved; re-read this test"
    finish = _finish(built["v19"])
    assert finish["distance"] < 0.75 * (
        0.5 * default.extent / math.tan(math.radians(default.fov) * 0.5)
    ), finish["distance"]


def test_every_crossing_in_the_shot_is_unobstructed(built):
    """The thing the lens exists for: six racers cross and all six are seen."""
    replay = built["replay"]
    scale = float(replay["units"]["render_scale"])
    radius = float(replay["units"]["layout_marble_radius"])
    times = [float(frame["t"]) for frame in replay["frames"]]
    rows = _finish(built["v19"])["frames"]
    crossings = [
        (float(event["t"]), int(event["id"]))
        for event in replay["events"]
        if event["kind"] == "finish_line" and WINDOW[0] <= float(event["t"]) <= WINDOW[1]
    ]
    assert len(crossings) == 6, crossings
    for when, marble in crossings:
        row = min(rows, key=lambda entry: abs(entry[0] - when))
        index = min(range(len(times)), key=lambda k: abs(times[k] - when))
        sample = next(
            one for one in replay["frames"][index]["marbles"] if int(one["id"]) == marble
        )
        where = tuple(float(sample["p"][axis]) * scale for axis in range(3))
        blocker = built["bundle"].first_hit(tuple(row[1:4]), where, shorten=radius)
        assert blocker is None, f"marble {marble} is behind {blocker} as it crosses"


def test_the_shot_is_never_empty(built):
    """A finish camera with nobody in it is a held frame, not a shot."""
    replay = built["replay"]
    scale = float(replay["units"]["render_scale"])
    radius = float(replay["units"]["layout_marble_radius"])
    times = [float(frame["t"]) for frame in replay["frames"]]
    finish = _finish(built["v19"])
    half_up = math.tan(math.radians(finish["fov"]) * 0.5)
    half_across = half_up * (1080 / 1920)
    for row in finish["frames"][::6]:
        camera, aim = tuple(row[1:4]), tuple(row[4:7])
        forward = [aim[axis] - camera[axis] for axis in range(3)]
        reach = math.sqrt(sum(value * value for value in forward))
        forward = [value / reach for value in forward]
        right = [forward[2], 0.0, -forward[0]]
        length = math.hypot(right[0], right[2])
        right = [right[0] / length, 0.0, right[2] / length]
        up = [
            right[1] * forward[2] - right[2] * forward[1],
            right[2] * forward[0] - right[0] * forward[2],
            right[0] * forward[1] - right[1] * forward[0],
        ]
        index = min(range(len(times)), key=lambda k: abs(times[k] - row[0]))
        seen = 0
        for sample in replay["frames"][index]["marbles"]:
            where = tuple(float(sample["p"][axis]) * scale for axis in range(3))
            offset = [where[axis] - camera[axis] for axis in range(3)]
            depth = sum(offset[axis] * forward[axis] for axis in range(3))
            if depth <= 0.05:
                continue
            if abs(sum(offset[axis] * right[axis] for axis in range(3)) / depth) > half_across:
                continue
            if abs(sum(offset[axis] * up[axis] for axis in range(3)) / depth) > half_up:
                continue
            if built["bundle"].first_hit(camera, where, shorten=radius) is None:
                seen += 1
        assert seen > 0, f"nobody is in shot at replay {row[0]:.2f}s"


# --- the solids -----------------------------------------------------------


def test_the_gantry_is_modelled_although_it_has_no_collider(built):
    """A camera is stopped by what is drawn, not by what the physics can touch."""
    solids = dict(sightlines.course_solids(built["machine"]))
    assert "finish:gantry" in solids
    assert "finish:rim" in solids
    gantry_top = max(point[1] for tri in solids["finish:gantry"] for point in tri)
    deck_top = max(point[1] for tri in solids["finish"] for point in tri)
    assert gantry_top > deck_top + 2.0, (gantry_top, deck_top)


def test_the_channel_shells_are_swept_not_mirrored(built):
    """They come from the same expression the collider and the mesh use."""
    solids = dict(sightlines.course_solids(built["machine"]))
    run = built["machine"].runs["final"]
    points = [point for tri in solids["final"] for point in tri]
    for axis, index in ((0, 0), (2, 2)):
        lower = min(point[axis] for point in points)
        upper = max(point[axis] for point in points)
        for sample in run.path:
            assert lower - 3.0 <= sample[index] <= upper + 3.0
    # The guard rail's top, which is what a low camera is stopped by.
    section = run.section_at(len(run.path) // 2)
    assert max(up for _across, up in section) == pytest.approx(
        layout.CONTAINMENT_TOP, abs=1e-6
    )
