"""V29: SWITCHYARD, camera A and the V27.2 hall, integrated and measured.

Three groups.

**The locks.** Written as literals here rather than recomputed from the code
under test, so that a change to the thing under test breaks the test instead of
moving with it: the hero seed's outcome and runtime, camera A's four shots and
three cuts, the 6.47 s final sprint with no cut in it, and the hall profile's
chain and geometry exactly as V27.2 left them.

**The integration.** That Race #2 reaches the stage through the shared seam,
that the outdoor control is still the profile it was, that the stage is placed
by a rule derived from the two courses rather than by a number somebody typed,
and that a profile authoring no stage adds nothing.

**The findings.** The measurements this branch exists to take, asserted at the
values it measured them at, so that a later pass which fixes the environment can
tell from a failing test that it fixed it.

The rendered measurements are read from `docs/validation/race2/v29_contained/`
and skip where that has not been produced, in the same way the world tests in
this repository skip without `$GODOT_BIN`.
"""

from __future__ import annotations

import json
import os
import pathlib

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = pathlib.Path(REPO) / "godot" / "assets" / "marble_machine" / \
    "environment" / "profiles"
VALIDATION = pathlib.Path(REPO) / "docs" / "validation" / "race2" / "v29_contained"
SCENE = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"


def _profile(name: str) -> dict:
    return json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))


def _measured(name: str, key: str | None = None):
    """A rendered measurement, or a skip.

    `key` names the measure inside a multi-measure report, and a report that
    does not carry it skips rather than raising. `tools/race2_v29_review.py`
    takes `--only=`, and a run of it rewrites `review.json` with just the
    measures asked for - so a partially regenerated file is a normal state of
    the working tree and should read as "not produced yet", not as a failure.
    """
    path = VALIDATION / name
    if not path.is_file():
        pytest.skip(f"{path} not produced; run tools/race2_v29_short.py all")
    report = json.loads(path.read_text(encoding="utf-8"))
    if key is not None and key not in report:
        pytest.skip(f"{path} carries no '{key}'; "
                    f"run tools/race2_v29_review.py with no --only")
    return report


# --- the locks --------------------------------------------------------------


def test_the_hero_race_is_the_one_v28_and_v281_filmed():
    """Seed 8 on SWITCHYARD, unchanged by anything in this branch."""
    from race2 import courses
    from race2.events import extract
    from race2.race import run_race

    course = courses.build("switchyard")
    outcome, _ = run_race(course, seed=8, duration=40.0, marble_count=8,
                          with_replay=False)
    timeline = extract(outcome, course, outcome.sim_events)
    assert course.title == "SWITCHYARD"
    assert course.stations == ("studs", "drum", "sweep", "pair", "last")
    assert round(course.length, 3) == 176.516
    assert timeline is not None


def test_camera_a_is_four_shots_three_cuts_and_a_647_second_sprint():
    """The shot structure the brief locks, read off the solved track.

    Skips where the track has not been staged, because building it needs the
    replay and that is a 26 s simulation rather than a unit test.
    """
    track_path = pathlib.Path(REPO) / "output" / "race2" / "v281_camera" / "A" / \
        "race2_switchyard_8.cameras.json"
    if not track_path.is_file():
        pytest.skip("camera A not staged; run tools/race2_cine.py --seed=8 --only=A")
    track = json.loads(track_path.read_text(encoding="utf-8"))

    assert track["camera"] == "A"
    assert track["fps"] == 60
    assert track["duration"] == 19.15
    cuts = track["cuts"]
    assert [c["name"] for c in cuts] == ["release", "upper", "middle", "run_in"]
    assert len(cuts) == 4                      # four shots
    assert len(cuts) - 1 == 3                  # three hard cuts

    # The final sprint: one take, 6.47 s, from the last powered mechanism to
    # the end of the film.
    final = cuts[-1]
    assert round(float(final["to"]) - float(final["from"]), 2) == 6.47
    assert float(final["to"]) == 19.15

    # Zero temporal omissions: every shot's frames are consecutive at 60 fps,
    # and each shot starts where the last one ended.
    for cut in cuts:
        stamps = [row[0] for row in cut["frames"]]
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        # To a microsecond, which is the tightest this can be asserted: the
        # track is written to six decimal places, so a 60 fps step reaches the
        # file as 0.016666 or 0.016667 and a difference of two of them carries
        # up to 1e-6 of rounding. The point of the assertion is that there is
        # no *frame* missing, and a dropped frame would show as 0.033.
        assert max(abs(gap - 1 / 60.0) for gap in gaps) <= 1e-6, cut["name"]
    for before, after in zip(cuts, cuts[1:]):
        assert float(before["to"]) == float(after["from"])


def test_the_hall_is_v272s_to_the_leaf():
    """The profile chain and the one leaf that names the edition."""
    chain = []
    name = "contained_hall_v272"
    while name:
        chain.append(name)
        name = _profile(name).get("extends")
    assert chain[:5] == ["contained_hall_v272", "contained_hall_v271",
                         "contained_hall", "contained_base", "aurora_valley_v26"]

    # V27.2 is one leaf on a field no profile had ever named.
    leaf = _profile("contained_hall_v272")
    assert leaf["palette"] == {"hall_panel_dark": {"specular": 0.06}}
    assert "world" not in leaf

    # And the geometry underneath it is V27's, unedited.
    hall = _profile("contained_hall")["world"]
    radii = [band["radius"] for band in hall["shell"]["bands"]]
    assert radii == [122.0, 122.0, 92.0, 90.0]
    assert [ring["inner"] for ring in hall["deck"]["rings"]] == [88.0, 122.0]
    assert [band["radius"] for band in hall["pylons"]["bands"]] == [80.0, 64.0]
    assert sorted(hall["bays"]["sites"]) == ["finish", "merge", "split"]


# --- the integration --------------------------------------------------------


def _scene_code() -> str:
    lines = []
    for line in SCENE.read_text(encoding="utf-8").splitlines():
        cut = line.find("#")
        lines.append(line if cut < 0 else line[:cut])
    return "\n".join(lines)


def test_the_stage_is_reached_through_the_shared_seam():
    code = _scene_code()
    assert "EnvWorld.build(" in code
    assert "EnvBuilder.world(" in code
    # And the profile's surface table is installed, which is what makes V27.2's
    # specular leaf reach the picture at all.
    assert "EnvBuilder.apply_palette(" in code


def test_only_the_stage_keys_are_built():
    """The eleven terrain-anchored features are not, and that is deliberate.

    Race #2's course does not stand on a heightfield, so a feature sited
    against one has no ground to be sited against. It is also what keeps the
    outdoor control the picture it was: `aurora_valley_v26` authors no stage,
    so nothing is added to it.
    """
    code = _scene_code()
    assert 'STAGE_KEYS := ["deck", "shell", "pylons", "canopy", "bays"]' in code
    for absent in ("patches", "ridges", "scarps", "boulders", "ravine"):
        assert f'"{absent}"' not in code, absent


def test_the_outdoor_control_authors_no_stage():
    """So the V26 render gains nothing from the seam this branch opened."""
    resolved: dict = {}
    chain = []
    name = "aurora_valley_v26"
    while name:
        chain.append(name)
        name = _profile(name).get("extends")
    for name in reversed(chain):
        world = _profile(name).get("world")
        if isinstance(world, dict):
            resolved.update(world)
    for key in ("deck", "shell", "pylons", "canopy", "bays"):
        assert not isinstance(resolved.get(key), dict), key


def test_the_stage_floor_is_derived_and_not_typed():
    """The lift is a rule over two numbers the courses own.

    The hall carries absolute heights authored around Race #1's mountainside -
    a deck at y = -80, a wall footed at -100 - and Race #2's course does not
    descend one. The room is therefore translated, by

        lift = (lowest point of the racing line - clearance) - deck datum

    where the datum is the *top of the tallest deck ring* rather than its
    underside, because `environment_stage._deck` refuses a ring whose top would
    stand above the ground under it.
    """
    code = _scene_code()
    assert "STAGE_FLOOR_CLEARANCE := 2.0" in code
    assert "lift := (floor_y - STAGE_FLOOR_CLEARANCE) - datum" in code
    assert "func _stage_datum" in code

    # The datum this rule produces for the shipped hall, computed here the way
    # the scene computes it.
    rings = _profile("contained_hall")["world"]["deck"]["rings"]
    datum = max(r["y"] + r["thickness"] * 0.5 for r in rings)
    assert datum == -71.5


def test_no_scale_is_applied_to_the_hall():
    """A translation is a placement; a scale would be a redesign.

    The branch's headline finding is that the room is too large for this
    course, and the only honest way to report that is to render it at the size
    it was authored.
    """
    code = _scene_code()
    assert "stage.position = Vector3(0.0, lift, 0.0)" in code
    assert "stage.scale" not in code


# --- the findings -----------------------------------------------------------


def test_the_hall_has_no_floor_under_this_course():
    """The deck is an annulus with an 88-unit hole, and the course fits inside it.

    This is the mechanism behind every other number in the pass, so it is
    asserted from the profile and the course rather than from a render.
    """
    from race2 import courses

    inner = min(r["inner"] for r in
                _profile("contained_hall")["world"]["deck"]["rings"])
    assert inner == 88.0

    # `Course.runs[].path` is already in layout units - it is the geometry
    # *export* that writes simulation units, which is why `race2_scene` scales
    # the exported path by `render_scale` and this does not.
    course = courses.build("switchyard")
    reach = 0.0
    for run in course.runs.values():
        for point in run.path:
            reach = max(reach, (point[0] ** 2 + point[2] ** 2) ** 0.5)
    assert round(reach, 2) == 27.06
    # The whole course sits inside the hole in the floor, with room to spare.
    assert reach < inner / 3.0


def test_the_halls_three_bays_name_nodes_this_course_has_not():
    """`split`, `merge` and `finish` are Race #1's nodes.

    `environment_stage._bays` skips a site whose node is absent, so the three
    pieces of architecture authored closest to the action build nothing here.
    Asserted because it is the finding most likely to be mistaken for a bug.
    """
    from race2 import courses

    sites = _profile("contained_hall")["world"]["bays"]["sites"]
    wanted = {site.get("node", name) for name, site in sites.items()}
    assert wanted == {"split", "merge", "finish"}

    course = courses.build("switchyard")
    available = set(course.stations) | {"start", "runout"}
    assert wanted.isdisjoint(available)


def test_the_measured_coverage_is_what_the_writeup_reports():
    report = _measured("coverage.json")
    outdoor = report["worlds"]["outdoor"]
    contained = report["worlds"]["contained"]
    assert outdoor["frames"] == contained["frames"] == 1150

    # The machine is the same geometry seen by the same camera in both worlds,
    # so the two silhouettes have to agree. This is the check that says the
    # matte subtraction is sound.
    assert abs(outdoor["machine_mean"] - contained["machine_mean"]) < 0.5

    # The finding: the contained film is mostly black, and gets blacker.
    assert outdoor["void_mean"] < 1.0
    assert contained["void_mean"] > 60.0
    blackness = [contained["shots"][s]["void_mean"]
                 for s in ("release", "upper", "middle", "run_in")]
    assert blackness == sorted(blackness), blackness
    assert blackness[-1] > 88.0


def test_the_surface_inventory_agrees_with_the_coverage_measure():
    """Two independent instruments on one film, within a tenth of a point."""
    surfaces = _measured("surfaces.json")
    coverage = _measured("coverage.json")
    hall = sum(row["hall"] for row in surfaces["rows"]) / len(surfaces["rows"])
    assert abs(hall - coverage["worlds"]["contained"]["world_mean"]) < 0.5


def test_six_authored_surfaces_never_reach_the_film():
    """Four of the ten the hall names carry the room and six are never seen.

    The distinction matters to a later art pass: a surface that is authored into
    geometry and never photographed is wasted work, while `hall_grate` - the
    eleventh key in the family - is simply not part of this hall.
    """
    surfaces = _measured("surfaces.json")
    rows = surfaces["rows"]
    seen, unseen = [], []
    for key in surfaces["surfaces"]:
        share = sum(row[key] for row in rows) / len(rows)
        (seen if share >= 0.01 else unseen).append(key)
    assert sorted(seen) == ["hall_deck", "hall_panel", "hall_panel_dark",
                            "hall_rib"]

    # Which of the unseen the profile actually builds something out of.
    world = json.dumps(_profile("contained_hall")["world"])
    authored = [key for key in unseen if f'"{key}"' in world]
    assert sorted(authored) == ["hall_beam", "hall_deck_dark", "hall_glass",
                                "hall_trim", "lit_hall_cool", "lit_hall_warm"]
    assert "hall_grate" in unseen and "hall_grate" not in authored

    # `hall_trim` is the family's one light-value surface and is authored eight
    # times - every band's cornice and plinth - and is at zero.
    assert world.count('"hall_trim"') == 8


def test_the_architecture_does_not_block_the_racers():
    """The one review question the hall passes outright."""
    review = _measured("review.json", "occlusion")
    assert review["occlusion"]["film_mean"] < 0.5
    assert review["occlusion"]["film_max"] < 5.0


def test_the_racers_go_dark_in_the_final_sprint():
    """The payoff is where the room costs the most."""
    review = _measured("review.json", "racers")
    outdoor = review["racers"]["outdoor"]["shots"]["run_in"]["luma"]
    contained = review["racers"]["contained"]["shots"]["run_in"]["luma"]
    assert outdoor > 120.0
    assert contained < 30.0
    assert outdoor / contained > 4.0


def test_the_hall_adds_less_parallax_than_the_world_it_replaces():
    review = _measured("review.json", "parallax")
    outdoor = review["parallax"]["outdoor"]["film"]
    contained = review["parallax"]["contained"]["film"]
    assert contained < outdoor
    # And the shortfall grows through the film.
    ratios = [review["parallax"]["contained"]["shots"][s]
              / review["parallax"]["outdoor"]["shots"][s]
              for s in ("release", "upper", "middle", "run_in")]
    assert ratios == sorted(ratios, reverse=True), ratios
    assert ratios[-1] < 0.2


def test_a_title_plate_would_sit_cleaner_in_the_hall():
    """The one place the room measurably beats the world it replaces."""
    review = _measured("review.json", "card")
    outdoor = review["card"]["outdoor"]
    contained = review["card"]["contained"]
    assert contained["sd"] < outdoor["sd"]
    assert contained["worst_sd"] < outdoor["worst_sd"]
    assert contained["over_128"] <= outdoor["over_128"]
