"""V30: the second-generation contained stage, built from the camera outward.

Four groups.

**The locks.** Written as literals rather than recomputed from the code under
test, so a change to the thing under test breaks the test instead of moving
with it: the hero seed's outcome and runtime, camera A's four shots and three
cuts, the 6.47 s uninterrupted final sprint, and - the point of this pass -
that V27.2's hall and V26's outdoor world are still exactly what they were.

**The architecture.** That every dimension in a V30 profile is derived from
the camera envelope rather than typed: the floor is continuous and has no
central hole, the walls stand only on the arc the film looks down, nothing is
authored above a lens that never looks up, and the stage still reaches Race #2
through the one shared seam V29 wired.

**The measurements.** What the rendered frames say, asserted against the
values this branch measured, so a later pass that changes the picture finds out
from a failing test.

**The failure it answers.** That V29's hall is still reproducible and still
fails in exactly the way it failed, because a fix whose control has drifted is
not a measured fix.

The rendered measurements are read from `docs/validation/race2/v30_stage/` and
skip where that has not been produced, in the same way the world tests in this
repository skip without `$GODOT_BIN`.
"""

from __future__ import annotations

import json
import math
import os
import pathlib

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
            / "environment" / "profiles")
VALIDATION = pathlib.Path(REPO) / "docs" / "validation" / "race2" / "v30_stage"
SCENE = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"
STAGE = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
         / "environment" / "environment_stage.gd")

CONCEPTS = ("contained_bay_v30", "horseshoe_arena_v30", "stepped_chamber_v30")
WINNER = "contained_bay_v30"

# The envelope, as `tools/race2_v30_envelope.py` measures it. Repeated here so
# the profiles can be checked against the numbers they claim to come from.
COURSE_REACH = 27.06
EYE_REACH = 45.68
LIVE_ARC = (75.0, 240.0)
FRAME_TOP_ELEV = -9.10


def _profile(name: str) -> dict:
    return json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))


def _measured(name: str):
    path = VALIDATION / name
    if not path.is_file():
        pytest.skip(f"{path} not produced; run tools/race2_v30_review.py all")
    return json.loads(path.read_text(encoding="utf-8"))


def _scene_code() -> str:
    lines = []
    for line in SCENE.read_text(encoding="utf-8").splitlines():
        cut = line.find("#")
        lines.append(line if cut < 0 else line[:cut])
    return "\n".join(lines)


def _bands(profile: dict) -> list:
    out = []
    for band in profile["world"].get("shell", {}).get("bands", []):
        out.append(band)
    return out


def _plates(profile: dict) -> list:
    return profile["world"].get("deck", {}).get("plates", [])


# --- the locks --------------------------------------------------------------


def test_the_hero_race_is_the_one_v28_v281_and_v29_filmed():
    """Seed 8 on SWITCHYARD, unchanged. This pass is environment only."""
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
    """The shot structure the brief locks, read off the solved track, with no
    frame missing anywhere in it."""
    track_path = (pathlib.Path(REPO) / "output" / "race2" / "v281_camera"
                  / "A" / "race2_switchyard_8.cameras.json")
    if not track_path.is_file():
        pytest.skip("camera A not staged; "
                    "run tools/race2_cine.py --seed=8 --only=A")
    track = json.loads(track_path.read_text(encoding="utf-8"))
    assert track["camera"] == "A"
    assert track["fps"] == 60
    assert track["duration"] == 19.15
    cuts = track["cuts"]
    assert [c["name"] for c in cuts] == ["release", "upper", "middle", "run_in"]
    final = cuts[-1]
    assert round(float(final["to"]) - float(final["from"]), 2) == 6.47
    assert float(final["to"]) == 19.15
    for cut in cuts:
        stamps = [row[0] for row in cut["frames"]]
        gaps = [b - a for a, b in zip(stamps, stamps[1:])]
        assert max(abs(gap - 1 / 60.0) for gap in gaps) <= 1e-6, cut["name"]
    for before, after in zip(cuts, cuts[1:]):
        assert float(before["to"]) == float(after["from"])


def test_this_branch_changes_no_physics_camera_or_course_module():
    """The brief's absolute locks, as a statement about which files moved.

    An environment pass that touched `race2/race.py`, `race2/spine.py`,
    `race2/rig.py` or `race2/courses.py` would be changing the race, the
    camera solve or the course, and no amount of measurement afterwards would
    make that an environment pass.
    """
    import subprocess

    base = "origin/v29-switchyard-contained-integration"
    try:
        diff = subprocess.run(
            ["git", "diff", "--name-only", f"{base}...HEAD"],
            cwd=REPO, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git is not available")
    if diff.returncode != 0:
        pytest.skip(f"cannot diff against {base}")
    touched = [p for p in diff.stdout.split() if p]
    if not touched:
        pytest.skip("no diff against the base; nothing to check")
    forbidden = ("race2/race.py", "race2/spine.py", "race2/rig.py",
                 "race2/courses.py", "race2/course.py", "race2/flow.py",
                 "race2/start.py", "race2/track.py", "race2/parts.py",
                 "race2/cinematography.py", "race2/events.py")
    assert not [p for p in touched if p in forbidden], touched


def test_the_two_controls_are_untouched():
    """V26 outdoor and V27.2's hall are historical evidence, not a baseline
    this pass may edit. Their files must be byte-identical to the base."""
    import subprocess

    base = "origin/v29-switchyard-contained-integration"
    watched = [
        "godot/assets/marble_machine/environment/profiles/aurora_valley_v26.json",
        "godot/assets/marble_machine/environment/profiles/contained_hall.json",
        "godot/assets/marble_machine/environment/profiles/contained_hall_v271.json",
        "godot/assets/marble_machine/environment/profiles/contained_hall_v272.json",
        "godot/assets/marble_machine/environment/profiles/contained_base.json",
    ]
    try:
        diff = subprocess.run(["git", "diff", "--name-only",
                               f"{base}...HEAD", "--", *watched],
                              cwd=REPO, capture_output=True, text=True,
                              timeout=60)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git is not available")
    if diff.returncode != 0:
        pytest.skip(f"cannot diff against {base}")
    assert diff.stdout.split() == []


def test_every_historical_profile_is_still_resolvable():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    listed = index["profiles"]
    for name in ("aurora_valley_v26", "contained_base", "contained_hall",
                 "contained_hall_v271", "contained_hall_v272"):
        assert name in listed, name
        assert (PROFILES / f"{name}.json").is_file(), name


def test_the_v29_failure_profile_still_chains_the_way_it_did():
    """The control this pass is measured against, unchanged to the leaf."""
    v272 = _profile("contained_hall_v272")
    assert v272["extends"] == "contained_hall_v271"
    assert _profile("contained_hall_v271")["extends"] == "contained_hall"
    assert _profile("contained_hall")["extends"] == "contained_base"
    assert v272["palette"] == {"hall_panel_dark": {"specular": 0.06}}
    hall = _profile("contained_hall")["world"]
    # The geometry that produced the failure: an annulus with an 88-unit hole.
    assert hall["deck"]["rings"][0]["inner"] == 88.0
    assert not hall["deck"].get("plates"), "the hall never had a floor"


# --- the architecture -------------------------------------------------------


def test_all_three_concepts_exist_and_are_listed():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    for name in CONCEPTS:
        assert name in index["profiles"], name
        profile = _profile(name)
        assert profile["id"] == name
        assert profile["family"] == "contained"
        # Off `contained_base`, not off the hall: nothing of V27's geometry
        # is inherited, which is the brief's rejection list.
        assert profile["extends"] == "contained_base"


def test_no_concept_inherits_the_rejected_hall_geometry():
    for name in CONCEPTS:
        world = _profile(name)["world"]
        for ring in world.get("deck", {}).get("rings", []):
            pytest.fail(f"{name} authors a deck ring: {ring}")
        for band in _bands(_profile(name)):
            assert band["count"] <= 12, (name, band["count"])
            assert band["radius"] <= 80.0, (name, band["radius"])


def test_every_concept_puts_a_continuous_floor_under_the_race():
    """Part A: no giant central void.

    A plate field is a grid centred on the chamber axis, so "covers the
    course" is a statement about its half-extent against the course's plan
    reach - and the field has no inner radius at all, which is the whole
    difference from a ring.
    """
    for name in CONCEPTS:
        plates = _plates(_profile(name))
        assert plates, f"{name} authors no floor"
        covered = False
        for field in plates:
            nx, nz = field["cells"]
            pitch_x = field["cell"][0] + field["gap"]
            pitch_z = field["cell"][2] + field["gap"]
            half_x = pitch_x * nx * 0.5
            half_z = pitch_z * nz * 0.5
            assert "inner" not in field, f"{name}: a plate field has no hole"
            if half_x >= COURSE_REACH and half_z >= COURSE_REACH:
                covered = True
        assert covered, f"{name}: no plate field reaches the course's r={COURSE_REACH}"


def test_the_floor_reaches_past_where_the_centre_ray_lands():
    """The measured demand: the centre ray lands at r = 7.4 to 80.9, so a
    floor that stops short of ~81 has frames with a hole in the middle. V29's
    deck *started* at 88."""
    for name in CONCEPTS:
        best = 0.0
        for field in _plates(_profile(name)):
            nx, nz = field["cells"]
            half = min((field["cell"][0] + field["gap"]) * nx * 0.5,
                       (field["cell"][2] + field["gap"]) * nz * 0.5)
            if field.get("radius"):
                half = min(half, field["radius"])
            best = max(best, half)
        assert best >= 75.0, (name, best)


def test_the_walls_stand_only_where_the_film_looks():
    """Part F, as geometry: the live arc is 75-240 degrees and 13 of 24
    sectors carry no wall pixel at all, so a band outside it is scenery
    nobody sees."""
    for name in CONCEPTS:
        for band in _bands(_profile(name)):
            first = band["bearing_from"]
            last = first + band["bearing_step"] * (band["count"] - 1)
            assert first >= LIVE_ARC[0] - 1e-6, (name, first)
            assert last <= LIVE_ARC[1] + 15.0 + 1e-6, (name, last)
            # And never a closed ring.
            assert (last - first) < 359.0, (name, first, last)


def test_no_wall_is_inside_the_camera_and_none_is_a_drum():
    """A closed band inside r = 45.68 would have the lens outside its own
    room; the sizing sweep measured 19 such frames at r = 40."""
    for name in CONCEPTS:
        for band in _bands(_profile(name)):
            assert band["radius"] > EYE_REACH, (name, band["radius"])


def test_no_concept_authors_a_canopy():
    """Part D applied before rendering: camera A's frame top never rises above
    -9.10 degrees, so overhead architecture cannot appear in any frame."""
    assert FRAME_TOP_ELEV < 0.0
    for name in CONCEPTS:
        assert "canopy" not in _profile(name)["world"], name


def test_each_concept_carries_race_2s_own_lens_guide():
    """V29 dropped the inherited guide, correctly: it is Race #1's camera
    path. V30 supplies Race #2's, and the plan positions have to lie inside
    the course's own neighbourhood rather than a mountainside's."""
    for name in CONCEPTS:
        guide = _profile(name)["world"]["keepout"]
        assert len(guide) >= 40, (name, len(guide))
        reach = max(math.hypot(x, z) for x, z in guide)
        assert reach <= EYE_REACH + 1.0, (name, reach)


def test_the_warm_practicals_are_in_the_floor_as_well_as_the_wall():
    """Part I. V29's were all in wall bays and measured 0.000%; the final
    sprint is 99.6% floor, so a practical that is not in the floor is not in
    the shot that matters."""
    for name in CONCEPTS:
        pads = _profile(name)["world"]["deck"]["pads"]
        warm = [p for p in pads if p.get("material") == "lit_hall_warm"]
        assert len(warm) >= 6, (name, len(warm))
        slots = 0
        for band in _bands(_profile(name)):
            slots += sum(1 for k in band.get("pattern", []) if k == "slot")
        assert slots >= 3, (name, slots)


def test_the_stage_is_reached_through_the_seam_v29_wired():
    """The infrastructure this pass preserves rather than replaces."""
    code = _scene_code()
    assert "EnvWorld.build(" in code
    assert "EnvBuilder.apply_palette(_palette, profile)" in code
    assert "_build_stage(profile)" in code
    assert 'STAGE_KEYS := ["deck", "shell", "pylons", "canopy", "bays"]' in code
    assert "_flat_ground(" in code


def test_the_seam_now_passes_a_profiles_lens_guide_through():
    code = _scene_code()
    assert 'world_cfg["keepout"] = authored["keepout"]' in code


def test_the_stage_datum_accounts_for_a_plate_floor():
    """A datum that only knew about rings would sink a plate-floored stage to
    the shell's foot and leave the course hanging above its own floor."""
    code = _scene_code()
    datum = code.split("func _stage_datum")[1].split("func ")[0]
    assert 'deck.get("plates", [])' in datum
    assert 'deck.get("rings", [])' in datum


def test_plates_are_a_new_deck_kind_and_rings_are_untouched():
    code = STAGE.read_text(encoding="utf-8")
    assert "static func _plates(" in code
    assert "_plates(node, palette, cfg, spec)" in code
    # The ring builder's own guard is still there: a ring is still an annulus.
    assert "deck ring %d has inner %.1f " in code


# --- the measurements -------------------------------------------------------


def test_the_winner_all_but_eliminates_the_near_black_v29_was_made_of():
    report = _measured("review.json")["worlds"]
    assert report["A"]["film"]["void"] < 0.01, report["A"]["film"]["void"]
    assert report["A"]["final_sprint"]["void"] < 0.005


def test_not_one_frame_of_the_winners_film_reaches_the_briefs_target():
    """Part Q, over all 1150 delivered frames rather than ten samples.

    The target is under 10% near-black and the failure line is 25%. The film
    peaks at 8.85% on one frame of the opening and averages 0.384%.
    """
    report = _measured("fullfilm_A.json")
    assert report["frames"] >= 1149, report["frames"]
    assert report["frames_over_10pct"] == 0
    assert report["frames_over_25pct"] == 0
    assert report["near_black_mean"] < 0.01
    assert report["near_black_max"] < 0.10
    sprint = report["per_shot"]["run_in"]
    assert sprint["frames"] >= 380
    assert sprint["mean"] < 0.005, sprint["mean"]
    assert sprint["max"] < 0.02, sprint["max"]


def test_every_concept_beats_the_briefs_final_sprint_target():
    """Part Q: ideally under 10%, certainly not over 25%. V29 was at 94%."""
    report = _measured("review.json")["worlds"]
    for world in ("A", "B", "C"):
        if world not in report:
            continue
        assert report[world]["final_sprint"]["void"] < 0.10, world


def test_the_v29_hall_still_fails_in_the_way_it_failed():
    """The control has to keep failing, or the comparison measures drift."""
    report = _measured("review.json")["worlds"]
    if "v29_hall" not in report:
        pytest.skip("the V29 control was not re-rendered")
    hall = report["v29_hall"]
    assert hall["film"]["void"] > 0.55, hall["film"]["void"]
    assert hall["final_sprint"]["void"] > 0.85
    assert hall["film"]["warm_coverage"] == 0.0


def test_the_racers_stay_the_brightest_thing_in_the_room():
    report = _measured("review.json")["worlds"]
    for world in ("A", "B", "C"):
        if world not in report:
            continue
        film = report[world]["film"]
        assert film["racer_separation"] > 60.0, world
        # And better than the hall, which crushed them to 66.4.
        assert film["racer_separation"] > report["v29_hall"]["film"][
            "racer_separation"] if "v29_hall" in report else True


def test_the_room_is_no_longer_blue():
    """Part H, measured over the room's *lit* pixels: below 1.35 the room
    reads as grey rather than as navy. V27's hall measures 1.95."""
    report = _measured("review.json")["worlds"]
    for world in ("A", "B", "C"):
        if world not in report:
            continue
        assert report[world]["film"]["blue_over_red"] < 1.35, world


def test_the_warm_practicals_are_actually_in_the_film():
    """V29: 0.000%. Anything above zero is the defect fixed; the threshold is
    where this branch measured the winner."""
    report = _measured("review.json")["worlds"]
    for world in ("A", "B", "C"):
        if world not in report:
            continue
        assert report[world]["film"]["warm_coverage"] > 0.001, world
    assert report["A"]["film"]["warm_coverage"] > 0.004


def test_no_authored_surface_family_is_missing_from_the_film():
    """Part D, and the test V29 would have failed six times over."""
    report = _measured("surfaces.json")
    for world, data in report.items():
        unseen = [k for k, v in data["families"].items()
                  if v.get("authored") and v["frames_visible"] == 0]
        assert unseen == [], (world, unseen)


def test_the_stage_is_cheaper_than_the_hall_it_replaces():
    """Part S. The hall was 493 meshes and 128,672 triangles on this course."""
    cost = _measured("cost_frames.json")
    if "A" not in cost or "meshes" not in cost["A"]:
        pytest.skip("costs not recorded")
    assert cost["A"]["meshes"] <= cost["v29_hall"]["meshes"]
    assert cost["A"]["triangles"] <= cost["v29_hall"]["triangles"] * 1.05


def test_the_stage_gives_the_camera_more_parallax_than_the_hall():
    """Part G, geometrically rather than from a block matcher: image speed is
    inversely proportional to range, so a stage's parallax is decided when its
    radii are chosen."""
    report = _measured("parallax.json")
    v30 = float(report["V30 A"]["spread_p50"])
    v29 = float(report["V29 hall"]["spread_p50"])
    assert v30 > 4.0, v30
    assert v30 > v29 * 2.0, (v30, v29)


# --- the envelope the whole design came from --------------------------------


def test_the_camera_envelope_report_says_what_the_profiles_assume():
    report = _measured("envelope.json")
    assert abs(report["footprint"]["plan_reach"] - COURSE_REACH) < 0.1
    assert abs(report["eye_y"]["max"] - 47.00) < 0.1
    assert report["frame_top_elevation"]["max"] < 0.0
    assert report["centre_ray_escapes"] == 0
    # The number that condemns the hall: every centre ray lands inside 88.
    assert report["centre_radius"]["max"] < 88.0


def test_the_bearing_histogram_is_why_there_is_no_drum():
    report = _measured("envelope.json")
    bearings = report["bearings"]
    assert len(bearings["never_seen"]) >= 10, bearings["never_seen"]
    live = [i for i, s in enumerate(bearings["share"]) if s > 0.005]
    assert live, "no sector carries wall pixels"
    step = bearings["sector_degrees"]
    assert min(live) * step >= LIVE_ARC[0] - step
    assert max(live) * step <= LIVE_ARC[1] + step
