"""V21 rebuilds ten lenses. These pin what was wrong and what must stay right.

The review of V20 said a viewer picks a marble and loses it in the middle of
the race. `sloped.readability` turns that into four measurements over every
frame of every cut - how big a racer is on a 1080x1920 frame, how much of the
field is in shot, where the pack sits in the frame, and what happens across a
cut - and `sloped.sightlines`, which V19 wrote for the finish, answers the
fifth: how much of what is in frame the course itself is hiding.

Three faults came out of that, and each has a test here:

* **the racers were behind the course** - the spinner corridor had 7.9 of 8
  inside the frustum and 1.35 of them actually visible, the rest behind
  `leg2`'s own guard rail;
* **the lens jumped mid-shot** - five cuts moved the camera 20 to 30 layout
  units in a single frame, because the bearing is measured off a course tangent
  that reverses at the junction, and nothing in `check_track` could see it;
* **the late cuts were framed for a spread that is mostly depth** - the two
  routes' own centroids are 10 to 14 units apart, not the 30 the extents were
  set against.

And two things V21 may not do: change the edit, or change the finish.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sloped import cameras, readability, sightlines, terrain
from sloped.course import sloped_course

REPLAY = ROOT / "output" / "sloped_race_v1" / "race_5432.json"

# The cuts that are a race rather than a machine or an arrival, and therefore
# the ones the readability floors apply to.
RACE_CUTS = ("descent", "long", "hairpin", "straight", "obstacle", "split",
             "branch", "merge")


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
    v19 = cameras.build_track(replay, machine, fps=60, edit=cameras.EDIT_V19)
    v21 = cameras.build_track(replay, machine, fps=60, edit=cameras.EDIT_V212)
    return {
        "replay": replay,
        "machine": machine,
        "bundle": bundle,
        "v19": v19,
        "v21": v21,
        "read19": {row["cut"]: row for row in readability.readability_report(v19, replay)},
        "read21": {row["cut"]: row for row in readability.readability_report(v21, replay)},
        "see19": {
            row["cut"]: row
            for row in readability.visibility_report(v19, replay, machine, bundle, stride=6)
        },
        "see21": {
            row["cut"]: row
            for row in readability.visibility_report(v21, replay, machine, bundle, stride=6)
        },
    }


# --- what V21 may not touch ------------------------------------------------


def test_v212_keeps_v19s_edit_map(built):
    """Same windows, same omissions, same clock - so V20's soundtrack still fits.

    The brief for this pass is the cameras and nothing else. If a window moved,
    every impact, both whooshes, all six crossings and the three overlays that
    `sloped.presentation.Clock` places would move with it.
    """
    assert built["v19"]["edit"] == built["v21"]["edit"]
    assert built["v19"]["duration"] == built["v21"]["duration"]
    assert built["v19"]["omitted"] == built["v21"]["omitted"]
    for before, after in zip(cameras.EDIT_V19, cameras.EDIT_V212):
        assert (before[0], before[1], before[2]) == (after[0], after[1], after[2])


def test_v212_leaves_the_finish_lens_alone(built):
    """The strongest shot in the film is an input to this pass, not an output."""
    assert cameras.EDIT_V212[-1] == cameras.EDIT_V19[-1]
    finish19 = [cut for cut in built["v19"]["cuts"] if cut["name"] == "finish"][0]
    finish21 = [cut for cut in built["v21"]["cuts"] if cut["name"] == "finish"][0]
    assert finish19 == finish21


# --- the three faults ------------------------------------------------------


def test_the_course_was_hiding_the_racers_and_is_not_now(built):
    """Frustum count is not visibility, and the spinner corridor proves it.

    V19's obstacle cut holds 7.9 racers of 8 inside its frustum and shows 1.35
    of them; the rest are behind `leg2`'s outer guard, which is why the section
    read as busy rather than as a race. The whole fix is elevation.
    """
    assert built["see19"]["obstacle"]["visible_mean"] < 2.0
    assert built["see21"]["obstacle"]["visible_mean"] > 7.0
    # And not only there: every race cut shows at least as many as it did -
    # except `hairpin`, which is the one shot that pays for something else.
    # Its best framing holds 7.18 and this one holds 5.73, because the better
    # side reverses the racers on screen across the cut into `straight`. The
    # exception is named here so it cannot quietly become two.
    for name in RACE_CUTS:
        if name == "hairpin":
            continue
        assert built["see21"][name]["visible_mean"] >= built["see19"][name]["visible_mean"]
    assert built["see19"]["hairpin"]["visible_mean"] - built["see21"]["hairpin"]["visible_mean"] < 1.0
    assert built["read21"]["hairpin"]["px_median"] > built["read19"]["hairpin"]["px_median"] + 10.0
    for name in ("descent", "straight", "obstacle"):
        assert built["see21"][name]["visible_mean"] >= 2.0 * built["see19"][name]["visible_mean"]


def test_the_lens_no_longer_jumps_inside_a_shot(built):
    """A camera that moves 30 units in a frame is a cut nobody edited.

    Five of V19's eleven cuts do it - the second `start` window, `long`,
    `hairpin`, `split` and `merge` - because the bearing is measured off the
    leader's own course tangent, and that tangent reverses where the run-out
    doubles back and swings hard through the turns. `Cut.fixed_heading` takes
    the heading once, at the cut's midpoint, and holds it.
    """
    def worst(track):
        out = {}
        for cut in track["cuts"]:
            step = max(
                (math.dist(a[1:4], b[1:4]) for a, b in zip(cut["frames"], cut["frames"][1:])),
                default=0.0,
            )
            out[cut["name"]] = max(out.get(cut["name"], 0.0), step)
        return out

    before, after = worst(built["v19"]), worst(built["v21"])
    assert max(before.values()) > 20.0
    assert max(after.values()) <= cameras.MAX_CAMERA_STEP
    for name in ("start", "long", "hairpin", "merge"):
        assert after[name] < 1.0 < before[name]


def test_check_track_now_reports_a_lens_that_jumps(built):
    """The check that would have caught it, on the track that has the fault."""
    problems = cameras.check_track(built["v19"], built["replay"])
    jumps = [line for line in problems if "in one frame" in line]
    assert jumps, problems
    assert not [
        line for line in cameras.check_track(built["v21"], built["replay"])
        if "in one frame" in line
    ]


def test_the_racers_are_bigger_on_a_phone_frame(built):
    """Section A of the brief, as a number per cut rather than an impression."""
    bigger = [
        name for name in RACE_CUTS
        if built["read21"][name]["px_median"] > built["read19"][name]["px_median"]
    ]
    # Six of the eight grow. The two that do not are the two whose fault was
    # never scale: `obstacle` was already 136 px and needed 23 degrees of
    # elevation, and `straight` was the one race cut losing a quarter of the
    # field, so it is deliberately wider than V19 had it.
    assert len(bigger) >= 6, bigger
    assert "straight" not in bigger
    assert built["read21"]["obstacle"]["px_median"] > 130.0
    median19 = sorted(built["read19"][name]["px_median"] for name in RACE_CUTS)
    median21 = sorted(built["read21"][name]["px_median"] for name in RACE_CUTS)
    assert median21[len(median21) // 2] > median19[len(median19) // 2]
    # Nothing in the race is left in V19's dot range.
    assert min(median21) > min(median19)
    assert min(built["read21"][name]["px_median"] for name in RACE_CUTS) >= 35.0


def test_no_race_cut_loses_more_of_the_field_than_v19_did(built):
    """Bigger racers are only worth having if the marble you picked is still in shot."""
    for name in RACE_CUTS:
        before, after = built["read19"][name], built["read21"][name]
        assert after["coverage"] >= before["coverage"] - 0.06, name


# --- the fork and the merge ------------------------------------------------


def test_both_routes_are_visible_where_the_route_is_the_story(built):
    """`branch` and `merge` exist to say there are two ways down.

    A shot holding six racers that are all blue tells nobody there is a second
    route, so the measure is the share of sampled frames with a racer on *each*
    route in frame and unobstructed.
    """
    for name in ("split", "branch", "merge"):
        assert built["see21"][name]["both_routes"] >= built["see19"][name]["both_routes"]
    assert built["see21"]["branch"]["both_routes"] == 1.0
    assert built["see21"]["merge"]["both_routes"] >= 0.7
    assert built["see19"]["merge"]["both_routes"] < 0.5


def test_the_fork_holds_the_field_through_the_decision(built):
    """V19's split lost a quarter of the field for 0.90 s at the fork."""
    assert built["read19"]["split"]["lost_seconds"] > 0.5
    assert built["read21"]["split"]["lost_seconds"] <= 0.2
    assert built["read21"]["split"]["coverage"] > 0.85


def test_the_merge_bearing_cannot_swing_with_the_lead(built):
    """`heading_run` is why V19's merge moved 29.7 layout units in one frame."""
    from sloped import layout

    merge = [cut for cut in built["v21"]["cuts"] if cut["name"] == "merge"][0]
    aim = merge["frames"][0][4:7]
    # The merge follows the pack rather than a node, so what is pinned here is
    # that its *bearing* is measured off `blue` and therefore cannot swing when
    # the lead changes arms. Compare the lens direction at the two ends of the
    # shot: a heading taken from the leader reverses through the junction.
    first, last = merge["frames"][0], merge["frames"][-1]

    def direction(row):
        forward = [row[4 + axis] - row[1 + axis] for axis in range(3)]
        length = math.sqrt(sum(value * value for value in forward)) or 1.0
        return [value / length for value in forward]

    one, two = direction(first), direction(last)
    assert sum(a * b for a, b in zip(one, two)) > 0.9
    # And the pack it is aimed at is the field, not a point on the map.
    assert math.dist(aim, layout.NODES["merge"]) > 4.0


# --- continuity ------------------------------------------------------------


def test_the_cuts_are_no_worse_to_follow_than_v19s(built):
    """Where the pack lands after a cut, measured on the racers in both frames.

    Only the marbles visible on *both* sides of a cut can answer a viewer's
    question, so the jump is their centroid's, not each frame's own.
    """
    before = {
        (row["from"], row["to"]): row
        for row in readability.continuity_report(built["v19"], built["replay"])
    }
    after = {
        (row["from"], row["to"]): row
        for row in readability.continuity_report(built["v21"], built["replay"])
    }
    assert set(before) == set(after)
    scored = [
        key for key in after
        if after[key]["jump"] is not None and before[key]["jump"] is not None
    ]
    inside = [key for key in scored if after[key]["jump"] <= readability.MAX_CUT_JUMP]
    assert len(inside) >= len(scored) - 2
    # The four cuts through the middle of the race, which is the section the
    # review named, land the pack within a tenth of the frame diagonal - about
    # 220 px on the delivered frame, or two marble diameters at these framings.
    # V19's worst of the same four is 0.412.
    for key in (("descent", "long"), ("long", "hairpin"), ("hairpin", "straight"),
                ("straight", "obstacle")):
        assert after[key]["jump"] < 0.10, (key, after[key])
    assert max(before[key]["jump"] for key in (("obstacle", "split"),)) > 0.4


def test_no_cut_crosses_the_line(built):
    """The pack must not be going one way on screen and the other way after a cut.

    **On this edit the racers cannot be the cause.** Every cut joins two shots
    of the same instant, so the pack's world direction is identical either side
    of all ten - which means any turn the screen shows is the camera having
    crossed the line. Neither `jump` nor `swing` can see it: a cut can put the
    field in exactly the same corner of the frame and still reverse it.

    V19 crosses the line at the fork and at the merge. A first pass at V21 fixed
    both of those and broke two others in the middle; the middle four lenses
    were then solved as a chain, which is why `descent` and `hairpin` carry a
    `side` they would not otherwise need.
    """
    def turns(track):
        return {
            (row["from"], row["to"]): row["turn"]
            for row in readability.continuity_report(track, built["replay"])
            if row["turn"] is not None
        }

    before, after = turns(built["v19"]), turns(built["v21"])
    assert [key for key, value in before.items() if value < readability.MAX_TURN]
    assert not [key for key, value in after.items() if value < readability.MAX_TURN], after
    # The two V19 crosses this pass was asked to fix by name.
    assert before[("split", "branch")] < 0.0 < after[("split", "branch")]
    assert before[("branch", "merge")] < 0.0 < after[("branch", "merge")]


def test_the_racers_are_the_reason_a_screen_direction_could_change(built):
    """The premise the line test rests on, checked rather than assumed."""
    cuts = built["v21"]["cuts"]
    for before, after in zip(cuts, cuts[1:]):
        gap = after["frames"][0][0] - before["frames"][-1][0]
        # Either the cut is on the same frame, or it is one of the edit's two
        # deliberate omissions - and those are the only two.
        assert gap < 0.05 or gap in (pytest.approx(0.85, abs=0.02),
                                     pytest.approx(3.40, abs=0.02)), gap


# --- the instrument itself -------------------------------------------------


def test_a_finished_racer_is_not_counted_against_the_shot(built):
    """The replay's `s` field never leaves `running`, so crossings are the truth."""
    crossed = readability.crossings(built["replay"])
    assert len(crossed) == 8
    finish = [row for row in readability.readability_report(built["v21"], built["replay"])
              if row["cut"] == "finish"][0]
    # Six of the eight cross inside the finish window, so the racers the shot
    # is judged on fall from eight to two over its own run.
    assert finish["in_play"] < 8.0


def test_the_scale_floors_come_from_the_finish_lens(built):
    """48 and 34 are three quarters of what the shot held up as evidence does."""
    finish = built["read21"]["finish"]
    assert readability.MIN_MEDIAN_PX == pytest.approx(0.75 * 64.0, abs=1.0)
    assert finish["px_median"] > readability.MIN_MEDIAN_PX
    assert finish["px_tail"] > readability.MIN_TAIL_PX


def test_the_report_is_measured_on_the_frame_that_ships(built):
    """A racer is 2R*height/extent px at the aim plane, and this checks it holds."""
    from sloped import layout

    for name in ("obstacle", "hairpin", "finish"):
        cut = [row for row in built["v21"]["cuts"] if row["name"] == name][0]
        predicted = 2.0 * layout.MARBLE_RADIUS * 1920.0 / cut["extent"]
        measured = built["read21"][name]["px_median"]
        assert 0.45 * predicted < measured < 1.9 * predicted, (name, predicted, measured)
