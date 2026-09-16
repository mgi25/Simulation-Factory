"""V30.1: the premium art pass over V30's contained stage.

Five groups.

**The locks.** Written as literals rather than recomputed from the code under
test, so a change to the thing under test breaks the test instead of moving
with it: the hero seed's outcome, camera A's four shots and three cuts and its
6.47 s uninterrupted final sprint with no frame missing, that no physics,
camera or course module moved, and - the point of an art pass - that **V30 and
V29 are still byte-identical to what they shipped**, because both are the
controls every number here is measured against.

**The architecture, unchanged.** V30.1 authors surfaces, module sizes and
where the warm light is let into the building. It authors no architecture, and
these assert that: the four wall radii, the bearing arcs, the absence of a
canopy, the stage footprint, the floor's reach past the centre ray, and the
lens keep-out are all V30's numbers, checked against V30's own profile rather
than against a literal.

**What the scene actually builds.** The group this pass exists because of.
`environment_stage` silently refuses a pad or a bay inside its clearance of
the racing line or its keep-out of the camera path, and the V30 profile loses
five of its nine warm floor inlays - two of them from the final sprint's own
measured footprint - and its whole `sweep` portal that way. So: every element
V30.1 authors must be accepted, nothing may be buried under another floor
element, and V30's own refusals are asserted as the historical fact they are.
If a later change to the guards makes V30 build all thirteen pads, this group
fails and the V30.1 write-up needs a correction.

**The measurements.** What the rendered frames say, asserted against the
values this branch measured.

**The floor frequency.** The defect the brief sent this pass to fix, as the
two numbers that name it: the seam rate the module implies, and the edge
density and line count the film actually contains.

The rendered measurements are read from `docs/validation/race2/v301_stage/`
and skip where that has not been produced, in the same way the world tests in
this repository skip without `$GODOT_BIN`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
            / "environment" / "profiles")
VALIDATION = (pathlib.Path(REPO) / "docs" / "validation" / "race2"
              / "v301_stage")
STAGE = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
         / "environment" / "environment_stage.gd")
SCENE = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"

BASE = "origin/v30-contained-stage-v2"
WINNER = "contained_bay_v301"
V30 = "contained_bay_v30"
VARIANTS = ("contained_bay_v301a", "contained_bay_v301b",
            "contained_bay_v301c")

# The envelope, as `tools/race2_v30_envelope.py` measures it. V30.1 changes no
# architecture, so these are still the numbers every dimension answers to.
COURSE_REACH = 27.06
EYE_REACH = 45.68
LIVE_ARC = (75.0, 240.0)
FRAME_TOP_ELEV = -9.10

# Camera A's median ground speed, from `envelope.parallax`. Half of the seam
# rate; the other half is the module pitch.
CAMERA_SPEED = 12.04


def _profile(name: str) -> dict:
    return json.loads((PROFILES / f"{name}.json").read_text(encoding="utf-8"))


def _measured(name: str):
    path = VALIDATION / name
    if not path.is_file():
        pytest.skip(f"{path} not produced; "
                    f"run tools/race2_v301_review.py all")
    return json.loads(path.read_text(encoding="utf-8"))


def _bands(profile: dict) -> list:
    return profile["world"].get("shell", {}).get("bands", [])


def _plates(profile: dict) -> list:
    return profile["world"].get("deck", {}).get("plates", [])


def _pads(profile: dict) -> list:
    return profile["world"].get("deck", {}).get("pads", [])


def _git(*args: str):
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git is not available")


def _pitch(field: dict) -> float:
    """The seam spacing that decides the seam *rate*: the smaller of the two.

    **A plate field has two pitches and only one of them is the pattern.**
    V30's plate is 52 long by 2.2 deep, so its two pitches are 52.18 and 2.38;
    the seams that sweep the frame are the ones 2.38 apart, and taking the
    other gives the grate a rate of 0.23 a second. The minimum is the honest
    reduction for a strip field and is exact for a square one.
    """
    return min(field["cell"][0] + field["gap"],
               field["cell"][2] + field["gap"])


# --- the locks --------------------------------------------------------------


def test_the_hero_race_is_the_one_v28_to_v30_filmed():
    """Seed 8 on SWITCHYARD, unchanged. This pass is surfaces only."""
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
    assert [c["name"] for c in cuts] == ["release", "upper", "middle",
                                         "run_in"]
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
    """The brief's absolute locks, as a statement about which files moved."""
    diff = _git("diff", "--name-only", f"{BASE}...HEAD")
    if diff.returncode != 0:
        pytest.skip(f"cannot diff against {BASE}")
    touched = [p for p in diff.stdout.split() if p]
    if not touched:
        pytest.skip("no diff against the base; nothing to check")
    forbidden = ("race2/race.py", "race2/spine.py", "race2/rig.py",
                 "race2/courses.py", "race2/course.py", "race2/flow.py",
                 "race2/start.py", "race2/track.py", "race2/parts.py",
                 "race2/cinematography.py", "race2/events.py")
    assert not [p for p in touched if p in forbidden], touched


def test_every_control_this_pass_measures_against_is_untouched():
    """**V30 is a control now, not a baseline this pass may edit.**

    Every number in the V30.1 write-up is a difference against a render of
    `contained_bay_v30`, so that profile moving would invalidate the whole
    comparison - and the same is true of V27.2's hall and V26's outdoor world,
    which V30 measured against for the same reason.
    """
    watched = [
        f"godot/assets/marble_machine/environment/profiles/{name}.json"
        for name in ("aurora_valley_v26", "contained_base", "contained_hall",
                     "contained_hall_v271", "contained_hall_v272",
                     "contained_bay_v30", "horseshoe_arena_v30",
                     "stepped_chamber_v30")]
    diff = _git("diff", "--name-only", f"{BASE}...HEAD", "--", *watched)
    if diff.returncode != 0:
        pytest.skip(f"cannot diff against {BASE}")
    assert diff.stdout.split() == []


def test_v30s_own_tools_and_tests_are_untouched():
    """An art pass may add instruments. It may not edit the one that produced
    the evidence it is arguing against."""
    watched = ["tools/race2_v30_stage.py", "tools/race2_v30_envelope.py",
               "tools/race2_v30_review.py", "tools/race2_v30_surfaces.py",
               "tests/test_race2_v30_stage.py",
               "docs/race2_v30_contained_stage.md"]
    diff = _git("diff", "--name-only", f"{BASE}...HEAD", "--", *watched)
    if diff.returncode != 0:
        pytest.skip(f"cannot diff against {BASE}")
    assert diff.stdout.split() == []


def test_every_historical_profile_is_still_resolvable():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    listed = index["profiles"]
    for name in ("aurora_valley_v26", "contained_base", "contained_hall",
                 "contained_hall_v271", "contained_hall_v272",
                 "contained_bay_v30", "horseshoe_arena_v30",
                 "stepped_chamber_v30"):
        assert name in listed, name
        assert (PROFILES / f"{name}.json").is_file(), name


def test_no_diagnostic_profile_was_left_behind():
    """The probe profiles this pass wrote to isolate the specular finding are
    diagnostics, not editions. Forty-five of them existed at one point."""
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    strays = [p for p in index["profiles"] if p.startswith("_probe")]
    assert strays == [], strays
    assert list(PROFILES.glob("_probe*.json")) == []


def test_the_v29_failure_profile_still_chains_the_way_it_did():
    v272 = _profile("contained_hall_v272")
    assert v272["extends"] == "contained_hall_v271"
    assert _profile("contained_hall_v271")["extends"] == "contained_hall"
    assert _profile("contained_hall")["extends"] == "contained_base"
    hall = _profile("contained_hall")["world"]
    assert hall["deck"]["rings"][0]["inner"] == 88.0
    assert not hall["deck"].get("plates"), "the hall never had a floor"


# --- the architecture, unchanged --------------------------------------------


def test_the_production_profile_and_the_three_variants_are_listed():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    for name in (WINNER, *VARIANTS):
        assert name in index["profiles"], name
        profile = _profile(name)
        assert profile["id"] == name
        assert profile["family"] == "contained"
        assert profile["extends"] == "contained_base"


def test_the_wall_is_v30s_wall_to_the_unit():
    """**The brief locks the wall placement strategy and the stage footprint,
    and those are these numbers.** Checked against V30's own profile rather
    than a literal, so the two cannot drift apart silently."""
    v30 = _bands(_profile(V30))
    v301 = _bands(_profile(WINNER))
    assert len(v301) == len(v30)
    for a, b in zip(v30, v301):
        for field in ("radius", "height", "foot", "thickness", "count",
                      "bearing_from", "bearing_step", "batter"):
            assert a[field] == b[field], (field, a[field], b[field])


def test_the_pylon_ring_is_v30s_ring():
    """It is the third parallax speed, and the brief locks the 4.88x image
    speed spread that depends on its radius."""
    v30 = _profile(V30)["world"]["pylons"]["bands"][0]
    v301 = _profile(WINNER)["world"]["pylons"]["bands"][0]
    for field in ("count", "bearing_from", "bearing_step", "radius",
                  "height", "width", "depth"):
        assert v30[field] == v301[field], field


def test_the_lens_keepout_is_v30s_guide_unchanged():
    assert _profile(WINNER)["world"]["keepout"] == \
        _profile(V30)["world"]["keepout"]


def test_the_walls_still_stand_only_where_the_film_looks():
    for name in (WINNER, *VARIANTS):
        for band in _bands(_profile(name)):
            first = band["bearing_from"]
            last = first + band["bearing_step"] * (band["count"] - 1)
            assert first >= LIVE_ARC[0] - 1e-6, (name, first)
            assert last <= LIVE_ARC[1] + 15.0 + 1e-6, (name, last)
            assert (last - first) < 359.0, (name, first, last)
            assert band["radius"] > EYE_REACH, (name, band["radius"])
            assert band["radius"] <= 80.0, (name, band["radius"])


def test_no_variant_authors_a_canopy_or_a_deck_ring():
    """Camera A's frame top never rises above -9.10 degrees, so overhead
    architecture cannot appear in any frame; and a ring is an annulus, which
    is the V29 hole."""
    assert FRAME_TOP_ELEV < 0.0
    for name in (WINNER, *VARIANTS):
        world = _profile(name)["world"]
        assert "canopy" not in world, name
        assert not world.get("deck", {}).get("rings"), name


def test_every_variant_puts_a_continuous_floor_under_the_race():
    for name in (WINNER, *VARIANTS):
        plates = _plates(_profile(name))
        assert plates, f"{name} authors no floor"
        covered = False
        for field in plates:
            nx, nz = field["cells"]
            half_x = _pitch(field) * nx * 0.5
            half_z = (field["cell"][2] + field["gap"]) * nz * 0.5
            assert "inner" not in field, f"{name}: a plate field has no hole"
            if half_x >= COURSE_REACH and half_z >= COURSE_REACH:
                covered = True
        assert covered, name


def test_the_floor_still_reaches_past_where_the_centre_ray_lands():
    """The centre ray lands at r = 7.4 to 80.9, so a floor stopping short of
    ~81 has frames with a hole in the middle. V29's deck *started* at 88."""
    for name in (WINNER, *VARIANTS):
        best = 0.0
        for field in _plates(_profile(name)):
            nx, nz = field["cells"]
            half = min(_pitch(field) * nx * 0.5,
                       (field["cell"][2] + field["gap"]) * nz * 0.5)
            if field.get("radius"):
                half = min(half, field["radius"])
            best = max(best, half)
        assert best >= 75.0, (name, best)


def test_the_stage_is_still_reached_through_the_seam_v29_wired():
    code = SCENE.read_text(encoding="utf-8")
    assert "EnvBuilder.apply_palette(_palette, profile)" in code
    assert "_build_stage(profile)" in code
    assert 'STAGE_KEYS := ["deck", "shell", "pylons", "canopy", "bays"]' in code
    assert 'world_cfg["keepout"] = authored["keepout"]' in code
    assert "const STAGE_FLOOR_CLEARANCE := 2.0" in code


# --- the one new primitive --------------------------------------------------


def test_plates_gained_a_row_and_column_skip_and_nothing_else():
    """The only builder change in the pass. A channel is an omitted module,
    because widening `gap` widens every joint in the field at once."""
    code = STAGE.read_text(encoding="utf-8")
    assert 'field.get("skip_x", [])' in code
    assert 'field.get("skip_z", [])' in code
    assert "if ix in skip_x or iz in skip_z:" in code
    # And it warns rather than cutting a hole to whatever lies beyond.
    assert "omits modules" in code
    # The ring builder's own guard is untouched: a ring is still an annulus.
    assert "deck ring %d has inner %.1f " in code
    assert "static func _plates(" in code


def test_only_the_channel_variant_omits_modules():
    """`skip_x` is authored by exactly the treatment that needs it, and the
    production floor is treatment B, which does not."""
    assert not _plates(_profile(WINNER))[0].get("skip_x")
    assert not _plates(_profile(WINNER))[0].get("skip_z")
    channel = _plates(_profile("contained_bay_v301c"))[0]
    assert channel["skip_x"] == [2]
    assert channel["skip_z"] == [6]
    assert channel.get("under"), "a channel needs a slab to line it"


def test_no_plate_field_terraces_over_a_flat_base():
    """**A genuine builder incompatibility, found by the surface audit.**
    `terrace` drops the outer bands of plates and `under` is one box at one
    height, so past the second step the lining stands *above* the plates it
    lines and the floor renders as bare `hall_deck_dark` - 18.24% of the film
    when floor B was authored with a step, against V30's 0.09%."""
    for name in (WINNER, *VARIANTS):
        for field in _plates(_profile(name)):
            if field.get("under") and field.get("terrace"):
                pytest.fail(f"{name}: terrace over a flat under slab")


# --- what the scene actually builds -----------------------------------------


def test_no_element_v301_authors_is_refused_or_buried():
    """**The group this pass exists because of.**

    `tools/race2_v301_stage.siting` reimplements the two guards
    `environment_stage` applies - nearest-point distance to the racing line
    against each element's `clearance`, and to the camera path against its
    `keepout` - and checks the answer against the scene's own `stage: census`
    print. Nothing V30.1 authors may be silently dropped, and nothing may be
    hidden under another floor element.
    """
    report = VALIDATION / "siting.json"
    if not report.is_file():
        pytest.skip("run tools/race2_v301_stage.py siting")
    placed = json.loads(report.read_text(encoding="utf-8"))
    assert placed["refused"] == [], placed["refused"]
    assert placed["buried"] == [], placed["buried"]
    assert placed["centre"] == [0.0, 0.0], placed["centre"]


def test_the_flush_floor_elements_cannot_reach_the_racing_line():
    """Why their clearance is 0, as a proof rather than a waiver.

    `race2_scene` lifts the stage so the floor's top sits
    `STAGE_FLOOR_CLEARANCE` = 2.0 **below the lowest point of the racing
    line**, so an element whose top is under 2.0 above the floor cannot reach
    the line anywhere on the course.
    """
    floor_top = 0.0
    for pad in _pads(_profile(WINNER)):
        top = pad["y"] + pad["size"][1] * 0.5
        if pad.get("clearance", 7.0) == 0.0 and pad["material"] != "hall_grate":
            assert top - floor_top < 2.0, (pad["material"], top)


def test_the_station_kerbs_are_the_only_standing_pads_with_no_guard():
    """A kerb under a mechanism is *deliberately* under the racing line -
    which is the one thing rejection sampling exists to refuse - so it says
    zero, and `_deck` makes the same argument about its own pads."""
    kerbs = [p for p in _pads(_profile(WINNER))
             if p["material"] == "hall_grate"]
    assert len(kerbs) == 5, len(kerbs)
    for kerb in kerbs:
        assert kerb["clearance"] == 0.0
        assert kerb["keepout"] == 0.0


def test_v30_really_does_drop_eight_pads_and_a_bay():
    """**The historical fact this pass found, asserted so it stays found.**

    V30 authors 13 deck pads and 2 bays; the scene builds 8 and 1. All five
    refused pads are warm floor inlays, and two of them are from the group
    V30 sites inside the final sprint's own footprint. Its `sweep` portal sits
    6.6 units from camera A's plan path against a keep-out of 14 and has never
    appeared in a frame. If a later change to the guards makes V30 build all of
    them, this test fails and the V30.1 write-up needs a correction.
    """
    v30 = _profile(V30)
    pads = _pads(v30)
    assert len(pads) == 13, len(pads)
    warm = [p for p in pads if p["material"] == "lit_hall_warm"]
    assert len(warm) == 9, len(warm)
    # Three of the ring miss a clearance of 13 by 1.0 to 2.5 units, and two of
    # the three sited inside the final sprint's own footprint miss a 6-unit
    # camera keep-out by 0.7 and 2.5. The coordinates are the assertion: they
    # are what a later change to the guards would move.
    assert [p["at"] for p in warm if p["clearance"] == 6.0] == \
        [[-18.0, 33.0], [-20.0, 21.0], [-4.0, 35.0]]
    sweep = v30["world"]["bays"]["sites"]["sweep"]
    assert sweep["offset"] == [-30.0, -22.0]
    assert float(sweep.get("keepout",
                           v30["world"]["bays"]["keepout"])) == 14.0
    # And V30.1's moved, rather than being exempted from the guard.
    moved = _profile(WINNER)["world"]["bays"]["sites"]["sweep"]
    assert moved["offset"] != sweep["offset"]
    assert float(moved.get("keepout",
                           _profile(WINNER)["world"]["bays"]["keepout"])) \
        == 14.0


def test_the_warm_practicals_are_in_the_floor_and_in_the_wall():
    for name in (WINNER, *VARIANTS):
        pads = _pads(_profile(name))
        warm = [p for p in pads if p.get("material") == "lit_hall_warm"]
        assert len(warm) >= 6, (name, len(warm))
        # Warm reaches the wall two ways: a `slot` in a band's own rhythm,
        # and the strip inside a `bay`. Both are architecture rather than a
        # fitting on it, which is the brief's Part D, so both count.
        slots = 0
        for band in _bands(_profile(name)):
            slots += sum(1 for k in band.get("pattern", []) if k == "slot")
            if band.get("bay", {}).get("strip", {}).get("material") \
                    == "lit_hall_warm":
                slots += sum(1 for k in band.get("pattern", [])
                             if k == "bay")
        assert slots >= 3, (name, slots)


# --- the measurements -------------------------------------------------------


def test_the_room_is_no_longer_teal_where_the_eye_reads_it():
    """**The finding this pass is built on, as a test.**

    V30's hue measure is a channel-mean ratio over every room pixel above luma
    20, and it reported 1.18 on a floor whose lit panel tops render at a
    blue-to-red ratio of 1.97 and a chroma of 0.49. The average was not wrong,
    it was answering a different question: hue is a property the eye reads
    where the picture is bright. Both are asserted, and the *bright* one is
    where the improvement is.
    """
    report = _measured("review.json")["worlds"]
    v301, v30 = report["v301"]["film"], report["v30"]["film"]
    assert v301["blue_over_red"] < 1.35
    assert v301["bright_chroma"] < 0.25, v301["bright_chroma"]
    assert v301["bright_chroma"] < v30["bright_chroma"] * 0.7
    assert 0.85 < v301["bright_blue_over_red"] < 1.20


def test_the_racers_are_more_readable_than_v30_not_less():
    """Part Q: the polish is a failure if it makes the race harder to follow."""
    report = _measured("review.json")["worlds"]
    for world in ("v301", *(f"floor_{k}" for k in "abc")):
        if world not in report:
            continue
        film = report[world]["film"]
        assert film["racer_separation"] > 60.0, world
        assert film["machine_separation"] > 120.0, world
    assert report["v301"]["film"]["racer_separation"] >= \
        report["v30"]["film"]["racer_separation"], "racer readability regressed"
    assert report["v301"]["final_sprint"]["racer_separation"] >= \
        report["v30"]["final_sprint"]["racer_separation"]


def test_the_near_black_guard_holds_over_the_whole_film():
    """The brief's Part P guard: under 2% over the film and under 2% in the
    final sprint. Measured on every delivered frame, not on ten of them.

    **The film mean is higher than V30's and the cause is not the
    environment.** The worst frames are the opening half second and one moment
    at t = 8.15, and on the void map their near-black is the *machine's* own
    shadowed undersides - which darkened because the room did. Three
    environment levers were swept against it - ambient energy +47%, `WorldFill`
    doubled, `WorldWarm` +50% - and each moved it by under 0.2 percentage
    points while costing racer separation. It is the price of the darker room
    that bought the readability the test above asserts.
    """
    report = _measured("fullfilm_v301.json")
    assert report["frames"] >= 1149, report["frames"]
    assert report["near_black_mean"] < 0.02, report["near_black_mean"]
    assert report["per_shot"]["run_in"]["near_mean"] < 0.02
    assert report["frames_over_25pct"] == 0
    assert report["near_black_max"] < 0.15, report["near_black_max"]


def test_the_final_sprint_is_still_391_uninterrupted_frames():
    report = _measured("fullfilm_v301.json")
    sprint = report["per_shot"]["run_in"]
    assert sprint["frames"] >= 388, sprint["frames"]
    control = _measured("fullfilm_v30.json")["per_shot"]["run_in"]
    assert sprint["frames"] == control["frames"]


def test_the_warm_practicals_are_more_present_than_v30s():
    """V29: 0.000%. V30: 0.565% of the film, of which four of twelve authored
    inlays. V30.1 builds all eight it authors."""
    report = _measured("review.json")["worlds"]
    assert report["v301"]["film"]["warm_coverage"] > \
        report["v30"]["film"]["warm_coverage"]
    assert report["v301"]["film"]["warm_coverage"] > 0.008
    assert report["v301"]["final_sprint"]["warm_coverage"] > \
        report["v30"]["final_sprint"]["warm_coverage"]
    # And not so much that the room has gone orange.
    assert report["v301"]["film"]["warm_coverage"] < 0.04


def test_no_authored_surface_family_is_missing_from_the_film():
    report = _measured("surfaces.json")
    for world, data in report.items():
        unseen = [k for k, v in data["families"].items()
                  if v.get("authored") and v["frames_visible"] == 0]
        assert unseen == [], (world, unseen)


def test_the_floors_own_value_is_the_floors_largest_surface():
    """**The check the surface audit needed and V30 did not.** A floor whose
    dark lining outweighs its deck is a dark floor with plates on it rather
    than a light floor with joints in it, and two separate V30.1 builds got
    there: `hall_deck_dark` at 20.26% against `hall_deck`'s 14.04%, once from
    a 7-unit `under` margin and once from a terrace over a flat base."""
    report = _measured("surfaces.json")["v301"]["families"]
    assert report["hall_deck"]["coverage"] > report["hall_deck_dark"][
        "coverage"] * 3.0
    assert report["hall_deck_dark"]["coverage"] < 0.08
    assert report["hall_deck"]["coverage"] > 0.25


def test_the_stage_is_cheaper_than_v30_not_dearer():
    """Part R: under +20% triangles. It is under V30 outright."""
    cost = _measured("cost_frames.json")
    if "v301" not in cost or "meshes" not in cost["v301"]:
        pytest.skip("costs not recorded")
    assert cost["v301"]["meshes"] <= cost["v30"]["meshes"]
    assert cost["v301"]["triangles"] <= cost["v30"]["triangles"] * 1.20
    assert cost["v301"]["ms_per_frame"] <= cost["v30"]["ms_per_frame"] * 1.15


# --- the floor frequency ----------------------------------------------------


def test_the_selected_module_is_inside_the_seam_rate_band():
    """**The number nothing in the V30 toolchain ever printed.** V30's floor
    is a 2.2 plate on a 0.18 gap, and at camera A's median 12.04 units a
    second that is 5.06 seams a second. Above about two a second the floor is
    a pattern the eye tracks instead of the race; below about 0.4 the narrow
    shots contain no edge at all."""
    field = _plates(_profile(WINNER))[0]
    rate = CAMERA_SPEED / _pitch(field)
    assert 0.4 <= rate <= 2.0, rate
    v30_rate = CAMERA_SPEED / _pitch(_plates(_profile(V30))[0])
    assert v30_rate > 4.0, v30_rate
    assert rate < v30_rate / 3.0


def test_the_three_variants_span_the_band_rather_than_repeating_it():
    rates = sorted(CAMERA_SPEED / _pitch(_plates(_profile(n))[0])
                   for n in VARIANTS)
    assert rates[0] >= 0.4
    assert rates[-1] <= 2.0
    assert rates[-1] / rates[0] > 1.8, rates


def test_a_seam_is_a_line_rather_than_a_trench():
    """V30 laid 0.6 plates on a base 1.45 below them, so a 0.18 seam opened
    onto a surface 0.55 down: an aspect ratio of 0.33, which at this grazing
    angle is a slot in full shadow. A premium floor's joint is wider than it
    is deep."""
    for name in (WINNER, *VARIANTS):
        field = _plates(_profile(name))[0]
        under = field["under"]
        plate_top = field["y"] + field["thickness"] * 0.5
        under_top = field["y"] - under["drop"] + under["thickness"] * 0.5
        depth = plate_top - under_top
        assert depth > 0.0, name
        assert field["gap"] / depth > 1.0, (name, field["gap"], depth)


def test_the_films_background_frequency_actually_fell():
    """Part J. The metric is diagnostic and the image decides, but a polish
    pass that claims to have quietened the floor and measures busier has not."""
    report = _measured("review.json")["worlds"]
    v301, v30 = report["v301"], report["v30"]
    assert v301["film"]["edge_density"] < v30["film"]["edge_density"] * 0.5
    assert v301["final_sprint"]["edge_density"] < \
        v30["final_sprint"]["edge_density"] * 0.5
    assert v301["stripe_sprint"]["lines"] < v30["stripe_sprint"]["lines"] * 0.7


def test_the_module_is_larger_than_v30s_by_more_than_a_factor_of_five():
    """The brief's Part A, as arithmetic: the strip language is replaced by a
    large-scale module, not tuned."""
    v301 = _pitch(_plates(_profile(WINNER))[0])
    v30 = _pitch(_plates(_profile(V30))[0])
    assert v301 / v30 > 5.0, (v301, v30)
    assert _plates(_profile(WINNER))[0]["cells"] == [12, 12]


def test_the_floor_module_is_square_rather_than_a_strip():
    """A strip has one scale and a module has one shape. V30's plate is 52 by
    2.2 - an aspect ratio of 24 - which is what makes a field of them read as
    a grate however wide the gaps are."""
    for name in (WINNER, *VARIANTS):
        field = _plates(_profile(name))[0]
        aspect = field["cell"][0] / field["cell"][2]
        assert 0.5 < aspect < 2.0, (name, aspect)
    v30 = _plates(_profile(V30))[0]
    assert v30["cell"][0] / v30["cell"][2] > 20.0


def test_the_wall_reads_as_a_few_large_shapes_rather_than_many_small_ones():
    """Part B at phone resolution: 2 to 4 large architectural shapes per band,
    not thirty details. A form that *runs* across several segments is one
    shape, so the measure is the number of runs in the pattern."""
    for band in _bands(_profile(WINNER)):
        kinds = band["pattern"]
        runs = 1 + sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
        assert runs <= 5, (kinds, runs)
    near = _bands(_profile(WINNER))[0]["pattern"]
    v30_near = _bands(_profile(V30))[0]["pattern"]
    def _runs(kinds):
        return 1 + sum(1 for a, b in zip(kinds, kinds[1:]) if a != b)
    assert _runs(near) < _runs(v30_near), (near, v30_near)


def test_the_specular_finding_is_authored_on_every_large_surface():
    """**The mechanism, as a property of the profile.**

    `lab_palette._matte` never sets `metallic_specular`, so every V27 and V30
    room surface carries Godot's 0.5 default, and at the 20-58 degrees below
    horizontal this lens sees the floor at, that term is half the frame's
    brightness. Every large surface in V30.1 authors it; V30 authors it on
    exactly one.
    """
    v301 = _profile(WINNER)["palette"]
    large = ("hall_deck", "hall_deck_mid", "hall_deck_dark", "hall_panel",
             "hall_grate")
    for key in large:
        assert "specular" in v301[key], key
        assert v301[key]["specular"] <= 0.30, (key, v301[key]["specular"])
    v30 = _profile(V30)["palette"]
    assert [k for k in large if "specular" in v30[k]] == ["hall_panel"]


def test_the_fifth_world_light_is_no_longer_blue():
    """`contained_base` authors five lights and V30 moved four. `WorldBounce`
    is inherited at #3C5878 through a deep merge - the strongest remaining
    blue in the room and higher-energy than either light V30 dimmed."""
    def channels(hex_colour):
        return tuple(int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))

    base = _profile("contained_base")["lights"]["WorldBounce"]
    assert base["colour"] == "#3C5878"
    base_red, _base_green, base_blue = channels(base["colour"])
    assert base_blue - base_red > 40, base["colour"]
    assert "WorldBounce" not in _profile(V30)["lights"]
    bounce = _profile(WINNER)["lights"]["WorldBounce"]
    red, _green, blue = channels(bounce["colour"])
    assert blue <= red, bounce["colour"]
    # Neutralised rather than removed: it points up at +24 degrees and is the
    # only light reaching the underside of every reveal, seam and channel.
    assert bounce["energy"] == base["energy"]


def test_the_grade_and_the_tonemap_are_v30s():
    """V30's sweep showed every tonemap that reduces the cast also costs the
    racers their candy, and `white` 12.0 at exposure 0.82 is what keeps them
    at 211. An art pass does not reopen that."""
    v30 = _profile(V30)["grade"]
    v301 = _profile(WINNER)["grade"]
    for field in ("exposure", "white", "contrast", "saturation",
                  "ambient_sky_contribution"):
        assert v30[field] == v301[field], field
    assert "tonemap" not in v301


# --- the envelope this all still answers to ---------------------------------


def test_the_floor_envelope_reports_the_seam_rates_the_modules_came_from():
    report = _measured("floor.json")
    assert abs(report["camera_speed"] - CAMERA_SPEED) < 0.1
    assert abs(report["floor_y"] - (-2.6)) < 0.01
    sprint = report["frame_width"]["run_in"]
    assert sprint["width_min"] < 8.0, sprint
    assert sprint["width_p50"] < 12.0, sprint
    rates = {row["pitch"]: row["seams_per_second"] for row in
             report["modules"]}
    assert abs(rates[2.38] - 5.06) < 0.02
    assert abs(rates[13.0] - 0.93) < 0.02


def test_the_money_box_is_where_the_last_four_seconds_look():
    """The measurement that sited the runway: the sprint settles from about
    t = 15.1 and the rest of the film is one framing, on a floor patch about
    12 across by 20 deep centred near (-14, 26)."""
    report = _measured("floor.json")
    box = report["per_shot"]["run_in"]
    assert box["x"][0] >= -40.0 and box["x"][1] <= 44.0, box
    assert box["z"][0] >= -40.0 and box["z"][1] <= 40.0, box
    top = report["map"]["cells"][0]
    assert top["shots"]["run_in"] > 0.9, top
    assert -20.0 <= top["at"][0] <= -8.0, top
    assert 16.0 <= top["at"][1] <= 36.0, top
