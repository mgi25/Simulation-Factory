"""What V27.2 must be true of: one reflectance changed, and nothing else.

V27.2 is a merge correction over V27.1's finish correction. It has the same
shape as its two predecessors' suites and most of it asserts that something did
*not* move, because that is what a narrow local pass is.

Organised by what could go wrong:

* **the two profiles it inherits from are untouched.** `contained_hall` and
  `contained_hall_v271` keep their files, their resolved dictionaries and their
  renders, so every proof in `docs/sloped_race_v27_contained.md` and
  `docs/sloped_race_v271_contained_finish.md` still reproduces from the profile
  that produced it.
* **the delta is one leaf, and it is a reflectance.**
  `contained_hall_v272` resolves to `contained_hall_v271` with exactly one
  theme leaf different - `palette.hall_panel_dark.specular` - which the parent
  never named at all. No geometry, no new material key, no value, no light, no
  grade, no camera, no timing.
* **the film is V24's.** Seed, replay, camera track, edit map and every moment
  second, including the two this pass adds, re-derived from the delivered
  track rather than trusted.
* **the instrument is V27.1's.** The mask is imported, not reimplemented, and
  the pass reproduces V27.1's own published table from V27.1's own profile.
* **nothing regresses.** The hook is byte-identical, and no guarded moment
  falls.
* **no probe artefact survives.** Every diagnostic this pass builds is
  ephemeral, and the registry is checked for leftovers.
* **the country probe is not expanded.** Still one flag, one racer, one
  appearance behind one flag, and still render-only.

The replay and the solved track are generated output and not in the branch, so
the tests that need them skip rather than fail. So do the renders, which need
`$GODOT_BIN`, and the measured tables, which need the lab to have been run in
this tree.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import v24_payoff, v26
from sloped import v27_contained as v27
from sloped import v271_finish as v271
from sloped import v272_merge as v272

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PROFILES = GODOT / "assets" / "marble_machine" / "environment" / "profiles"
RACER_GD = GODOT / "assets" / "marble_machine" / "racers" / "racer_visual.gd"
GENERATOR = ROOT / "tools" / "sloped_v272_profiles.py"
LAB = ROOT / "tools" / "sloped_v272_merge.py"
MODULE = ROOT / "sloped" / "v272_merge.py"

OUT = ROOT / "output" / "sloped_race_v1"
LAB_DIR = OUT / "v272_contained"
DOC_DIR = ROOT / "docs" / "validation" / "sloped_race_v1" / "v272_contained"
TRACK = OUT / f"cameras_v24_{v27.SEED}.json"
REPLAY = OUT / f"race_{v27.SEED}.json"
CONTRACT = OUT / f"start_contract_{v27.SEED}.json"

#: The one file this pass writes. Neither of its parents is among them, and
#: neither is any probe.
NEW_PROFILES = ("contained_hall_v272",)

#: Everything V27.1 and earlier shipped. None of it may change.
FROZEN = (
    "alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
    "aurora_valley", "aurora_valley_v25", "aurora_valley_v25a",
    "aurora_valley_v25b", "aurora_valley_v25c", "aurora_valley_v251",
    "aurora_valley_v252", "aurora_valley_v26", "contained_base",
    "contained_hall", "diorama_chamber", "industrial_chamber",
    "_marker_v27a", "_marker_v27b", "_marker_v27c", "_marker_v27_control",
    "contained_hall_v271", "_marker_v271", "_probe_v271", "_probe_v271_pad",
)


def _read(name: str) -> dict:
    with open(PROFILES / f"{name}.json", encoding="utf-8") as handle:
        return json.load(handle)


def _measured(name: str):
    path = LAB_DIR / name
    if not path.is_file():
        pytest.skip(f"{name} not measured in this tree")
    return json.loads(path.read_text(encoding="utf-8"))


def _leaves(node, prefix: str = "") -> dict:
    """Every scalar in a nested structure, keyed by its path."""
    out: dict = {}
    if isinstance(node, dict):
        for key, value in node.items():
            out.update(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out.update(_leaves(value, f"{prefix}[{index}]"))
    else:
        out[prefix] = node
    return out


# --- the profile exists, and is the only one this pass leaves ---------------


def test_the_profile_exists_parses_and_is_indexed():
    listed = _read("index")["profiles"]
    for name in NEW_PROFILES:
        assert (PROFILES / f"{name}.json").is_file()
        assert isinstance(_read(name), dict)
        assert name in listed


def test_the_profile_resolves_without_complaint():
    profile = env.resolve(v272.PROFILE)
    assert env.validate(profile) == [], env.validate(profile)


def test_the_generator_is_a_no_op():
    """Re-running the generator must write nothing.

    The profile is committed and the generator is how it is regenerated; a
    generator that has drifted from its output is a table nobody is reading.
    """
    done = subprocess.run([sys.executable, str(GENERATOR)],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    wrote = [line for line in done.stdout.splitlines()
             if line.startswith("wrote ") or line.startswith("! ")]
    assert wrote == [], "the generator rewrote files:\n" + "\n".join(wrote)


def test_no_probe_artefact_is_left_in_the_profiles_or_the_index():
    """The brief's standing instruction, as an assertion.

    Every diagnostic this pass builds - a depth-band marker and nine surface
    probes - is written, rendered and deleted inside
    `sloped_v272_profiles.temporary`, which also restores `index.json` from the
    bytes it had on entry. This is the check that a killed run did not leave
    one behind, and that nobody has since committed one.
    """
    import tools.sloped_v272_profiles as gen

    assert gen.leftovers() == [], gen.leftovers()


def test_the_registry_gained_exactly_one_entry_over_v271():
    """V27.1 left four profiles in the index; this pass leaves one."""
    listed = _read("index")["profiles"]
    mine = [one for one in listed if "v272" in one]
    assert mine == [v272.PROFILE], mine


# --- the two parents are untouched ------------------------------------------


@pytest.mark.parametrize("name", FROZEN)
def test_no_earlier_profile_mentions_v272(name):
    body = (PROFILES / f"{name}.json").read_text(encoding="utf-8")
    assert "v272" not in body, f"{name} names V27.2"


def test_contained_hall_and_v271_are_not_extended_or_edited():
    """The two profiles this pass measures against are its parents, not its
    subjects."""
    assert env.load(v272.PROFILE)["extends"] == v272.PARENT
    assert env.load(v272.PARENT)["extends"] == v272.GRANDPARENT
    assert env.load(v272.GRANDPARENT)["extends"] == "contained_base"
    # and neither parent names a specular anywhere in its palette, which is
    # the field this pass adds
    for name in (v272.GRANDPARENT, v272.PARENT):
        for key, row in env.resolve(name)["palette"].items():
            assert "specular" not in row, f"{name}.{key} already has specular"


def test_v271_still_resolves_to_what_v271_published():
    """V27.1's own delta, re-derived: one leaf, the finish pad's material."""
    before = _leaves(env.resolve(v272.GRANDPARENT))
    after = _leaves(env.resolve(v272.PARENT))
    moved = {k for k in set(before) | set(after)
             if before.get(k) != after.get(k)}
    moved -= {"id", "title", "summary", "extends"}
    assert moved == {"world.deck.pads[0].material"}, moved
    assert after["world.deck.pads[0].material"] == "hall_deck_dark"


# --- the delta is one leaf, and it is a reflectance --------------------------


def test_the_delta_is_exactly_one_leaf():
    before = _leaves(env.resolve(v272.PARENT))
    after = _leaves(env.resolve(v272.PROFILE))
    moved = {k for k in set(before) | set(after)
             if before.get(k) != after.get(k)}
    moved -= {"id", "title", "summary", "extends"}
    assert moved == {"palette.hall_panel_dark.specular"}, moved


def test_the_leaf_is_a_reflectance_the_parent_never_named():
    """The field is *added*, not changed: nothing had ever set it.

    That is why no earlier pass had anything to look at. `lab_palette._matte`
    sets albedo, metallic and roughness and leaves `metallic_specular` at
    StandardMaterial3D's default of 0.5.
    """
    import tools.sloped_v272_profiles as gen

    parent = env.resolve(v272.PARENT)["palette"]["hall_panel_dark"]
    child = env.resolve(v272.PROFILE)["palette"]["hall_panel_dark"]
    assert "specular" not in parent
    assert child["specular"] == gen.DELTA_VALUE == 0.06
    assert 0.0 <= child["specular"] < gen.DELTA_DEFAULT
    # every other field of the row is inherited untouched
    for field in ("albedo", "roughness", "soft_light", "floor_lift"):
        assert child[field] == parent[field]


def test_the_delta_adds_no_geometry_and_no_new_material_key():
    before = env.resolve(v272.PARENT)
    after = env.resolve(v272.PROFILE)
    assert before["world"] == after["world"], "the delta reached the world"
    assert set(before["palette"]) == set(after["palette"]), \
        "the delta named a material key the parent did not have"
    for section in ("sky", "grade", "fog", "lights", "backdrop", "terrain",
                    "dressing", "ravine", "accent", "ssao", "ssr", "glow"):
        assert before.get(section) == after.get(section), \
            f"the delta reached {section}"


def test_the_material_the_delta_touches_is_the_one_the_probe_named():
    """`hall_panel_dark`, and the two objects that wear it."""
    import tools.sloped_v272_profiles as gen

    assert gen.DELTA_PATH[:2] == ("palette", "hall_panel_dark")
    world = env.resolve(v272.PROFILE)["world"]
    assert world["bays"]["sites"]["merge"]["material"] == "hall_panel_dark"
    assert world["shell"]["bands"][2]["material"] == "hall_panel_dark"


def test_the_delta_does_not_move_a_depth_band():
    """A material that changed bands would move the ruler as well as the
    picture.

    The delta touches no material *assignment* at all, so every surface stays
    in the `v27.MARKED` band it was in, and the marker over V27.2 paints what
    the marker over V27.1 paints. The render-level version of this claim is
    `test_the_marker_is_byte_identical_to_v271s`.
    """
    banded = {key: band for band, keys in v27.MARKED.items() for key in keys}
    assert banded["hall_panel_dark"] == "shell"
    before = env.resolve(v272.PARENT)["world"]
    after = env.resolve(v272.PROFILE)["world"]
    assert before == after


# --- the film is V24's -------------------------------------------------------


def test_the_seed_frame_size_and_fps_are_v27s():
    assert v272.SEED == v27.SEED == 5432
    assert (v272.WIDTH, v272.HEIGHT) == (v27.WIDTH, v27.HEIGHT) == (1080, 1920)
    assert v272.FPS == v27.FPS == 60


def test_the_twelve_v27_moments_are_carried_unchanged():
    """List A is V27's own list, not a re-derivation of it."""
    assert v272.LIST_A == v27.seconds()
    for one in v27.MOMENTS:
        mine = v272.moment(one.key)
        assert (mine.second, mine.replay) == (one.second, one.replay)


def test_the_two_new_moments_are_new_and_in_order():
    keys = [one.key for one in v272.MOMENTS]
    assert keys.count("merge_approach") == 1
    assert keys.count("post_merge") == 1
    assert len(keys) == len(v27.MOMENTS) + 2
    seconds = [one.second for one in v272.MOMENTS]
    assert seconds == sorted(seconds)
    assert keys.index("merge_approach") < keys.index("merge") < \
        keys.index("post_merge")


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_every_moment_is_inside_the_cut_that_owns_it():
    """All fourteen seconds re-derived from the delivered track.

    V27's own assertion, extended to the two this pass adds: a cut boundary
    that moved would put a moment in the wrong shot and every sheet here would
    be comparing two different instants.
    """
    track = json.loads(TRACK.read_text(encoding="utf-8"))
    spans = [(segment["out"][0], segment["out"][1], segment["replay"][0])
             for segment in track["edit"]]
    for one in v272.MOMENTS:
        match = [row for row in spans
                 if row[0] - 1e-6 <= one.second <= row[1] + 1e-6]
        assert match, f"{one.key} at {one.second} is in no cut"
        low, _high, replay_low = match[0]
        want = replay_low + (one.second - low)
        assert abs(want - one.replay) < 1e-3, \
            f"{one.key}: output {one.second} is replay {want}, table says " \
            f"{one.replay}"


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_new_moments_stand_clear_of_every_cut_boundary():
    """A sample on a boundary is a sample of whichever shot resolved first.

    V22.1 found it. 0.15 s is the margin this pass keeps, and the two new
    moments are the only ones it chose, so they are the only ones it has to
    defend.
    """
    track = json.loads(TRACK.read_text(encoding="utf-8"))
    edges = sorted({round(float(value), 6) for segment in track["edit"]
                    for value in segment["out"]})
    for one in v272.EXTRA:
        gap = min(abs(one.second - edge) for edge in edges)
        assert gap >= 0.15, f"{one.key} is {gap:.3f} s from a cut boundary"


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_clip_spans_the_branch_the_merge_and_the_shot_after_it():
    track = json.loads(TRACK.read_text(encoding="utf-8"))
    spans = {segment["cut"]: segment["out"] for segment in track["edit"]}
    start, end = v272.CLIP
    assert start > spans["branches"][0], "the clip opens on a cut boundary"
    assert start < spans["merge"][0] < end, "the clip does not cross the merge"
    assert end > spans["final"][0], "the clip stops before the merge resolves"
    assert end < spans["final"][1]
    seconds = v272.clip_seconds()
    assert len(seconds) == 159
    assert abs(seconds[1] - seconds[0] - 1.0 / v272.FPS) < 1e-6


def test_the_lab_never_writes_the_replay_or_the_track():
    """A presentation pass may read the race and may not produce one.

    Checked structurally rather than by substring: every `open` in the tool is
    parsed, and any that names `REPLAY`, `TRACK` or `START_CONTRACT` must be a
    read. A grep for "solve" would match "the solved track" in a docstring,
    which is how the first version of this assertion failed.
    """
    tree = ast.parse(LAB.read_text(encoding="utf-8"))
    guarded = {"REPLAY", "TRACK", "START_CONTRACT"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", "") or getattr(node.func, "attr", "")
        if name not in ("open", "copy2", "copy", "move", "rmtree", "remove"):
            continue
        for index, argument in enumerate(node.args):
            if isinstance(argument, ast.Name) and argument.id in guarded:
                assert name == "open" and index == 0, \
                    f"the lab passes {argument.id} to {name}()"
                mode = node.args[1] if len(node.args) > 1 else None
                assert mode is None or "w" not in str(
                    getattr(mode, "value", "")), \
                    f"the lab opens {argument.id} for writing"


def test_the_lab_does_not_simulate_or_re_solve():
    body = LAB.read_text(encoding="utf-8")
    for forbidden in ("run_race", "stepSimulation", "solve_track",
                      "cameras_module", "write_replay"):
        assert forbidden not in body, f"the lab calls {forbidden}"


def test_the_lab_touches_no_physics_camera_or_timing_module():
    """The locks, as an import check.

    The tool may read the replay, the solved track and V24's edit; it may not
    import the solver, the camera module or the race.
    """
    body = LAB.read_text(encoding="utf-8")
    for forbidden in ("from sloped import cameras", "import pybullet",
                      "from sloped.race", "from sloped import race",
                      "sloped.course import", "from marble3d"):
        assert forbidden not in body, f"the lab imports {forbidden}"


def test_the_module_reuses_v271s_instrument_rather_than_restating_it():
    """The mask is imported. A second copy of it is a second ruler."""
    body = MODULE.read_text(encoding="utf-8")
    assert "from sloped.v271_finish import" in body
    assert v272.machine_mask is v271.machine_mask
    assert v272.collar_pair is v271.collar_pair
    assert v272.surface_masks is v271.surface_masks
    assert v272.DIFF_FLOOR == v271.DIFF_FLOOR == 24.0
    assert "def machine_mask" not in body, "the instrument is reimplemented"


# --- the measured results ----------------------------------------------------


def test_this_pass_reproduces_v271s_published_table():
    """The instrument check: same profile, same list, same numbers.

    If this fails, nothing else measured here can be read beside V27.1's
    report, whatever it says about V27.2.
    """
    got = _measured("measures.json")
    rows = got["lists"]["a"]["worlds"]
    for key, published in v272.V271_PUBLISHED.items():
        for tag in ("v26", "v271"):
            mine = rows[tag]["moments"][key]["separation"]
            assert abs(mine - published[tag]) < 0.1, \
                f"{key}/{tag}: measured {mine}, V27.1 published {published[tag]}"


def test_the_merge_separation_improved_at_all_three_moments():
    got = _measured("measures.json")
    rows = got["lists"]["b"]["worlds"]
    for key in v272.MERGE:
        before = rows["v271"]["moments"][key]["separation"]
        after = rows["v272"]["moments"][key]["separation"]
        assert after > before + 5.0, \
            f"{key}: {before} -> {after} is not a correction"


def test_the_merge_clears_the_briefs_target_at_the_silhouette():
    """The like-for-like bar.

    The brief's 110 is quoted against a whole-frame mean, and §3 of the report
    is why that mean is not a like-for-like comparison at this section: V26's
    foreground rock hides the machine's own dark half, which lifts V26's
    machine mean and nothing else. On the silhouette both worlds show - the
    pairing V27.1 built for exactly this - the corrected hall clears the bar.
    """
    got = _measured("measures.json")
    pairs = got["lists"]["b"]["common_collar"]
    for key in v272.MERGE:
        row = pairs[key]
        assert row["v272"] is not None
        assert row["v272"] >= row["v271"], f"{key} fell at the silhouette"
        assert row["v272"] > row["v26_vs_v272"], \
            f"{key}: {row['v272']} is under V26's {row['v26_vs_v272']}"


def test_no_moment_regresses():
    """Every frame the delta reaches improves, and none falls."""
    got = _measured("delta.json")
    for key, row in got.items():
        step = row.get("d_separation")
        if step is None:
            continue
        assert step >= -0.05, f"{key} fell by {step}"


def test_the_black_floor_is_measured_and_bounded():
    """The delta's one real cost, guarded rather than only described.

    Removing a specular lobe from a surface that was already dark puts part of
    it under luma 5. The report's §6.1 is the table; this is the bound, so the
    cost cannot grow quietly if anything upstream changes. White clipping may
    not move at all - there is no mechanism by which taking light off a wall
    could add any - and the moments that gain the most must still be the ones
    that clip the least.
    """
    got = _measured("delta.json")
    for key, row in got.items():
        assert abs(row["clip_white_after"] - row["clip_white_before"]) < 1e-4,             f"{key} moved white clipping"
        assert row["clip_black_after"] <= 0.12,             f"{key} clips {row['clip_black_after']:.2%} black"
    # the merge and the final approach are where the surface was bright, and
    # there it lands well clear of the floor
    for key in ("merge", "final_approach"):
        assert got[key]["region_black_after"] <= 0.001, key
        assert got[key]["region_luma_after"] > 10.0, key


def test_the_hook_is_byte_identical():
    got = _measured("delta.json")
    assert got["frame0"]["changed"] == 0.0, \
        "the merge correction reached frame zero"
    assert got["frame0"]["max_dluma"] == 0.0


def test_the_finish_is_not_reopened_and_does_not_fall():
    """V27.1's three finish moments keep at least V27.1's figures."""
    got = _measured("measures.json")
    rows = got["lists"]["a"]["worlds"]
    for key in v271.FINISH:
        before = rows["v271"]["moments"][key]["separation"]
        after = rows["v272"]["moments"][key]["separation"]
        assert after >= before, f"{key}: {before} -> {after}"
        assert after >= v271.TARGET, f"{key} is under V27.1's own bar"


def test_the_fork_and_the_obstacle_do_not_regress():
    got = _measured("regress.json")["moments"]
    for key in ("obstacle", "fork_approach", "split", "branch"):
        assert got[key]["step"] >= -0.05, f"{key} fell by {got[key]['step']}"


def test_the_winner_is_unchanged_at_the_crossing():
    """The payoff marble: same size, same clearance, same separation."""
    got = _measured("winner.json")
    for key in ("winner", "payoff"):
        before = got["moments"][key]["worlds"]["v271"]
        after = got["moments"][key]["worlds"]["v272"]
        assert after["occluded"] == before["occluded"] == 0.0
        assert after["delta_e"] >= before["delta_e"] - 0.1


def test_the_payoff_card_reads_at_least_as_well_as_v271s():
    measured = _measured("payoff.json")
    got = measured["worlds"]
    assert got["v272"]["worst"] >= got["v271"]["worst"]
    assert got["v272"]["worst"] >= got["v26"]["worst"]
    assert got["v272"]["band_max"] <= got["v271"]["band_max"]
    # and V24's card itself is not redesigned
    card = v24_payoff.build()
    assert card.style == measured["style"]
    assert card.label == measured["label"]


def test_the_country_probe_is_unchanged_and_still_render_only():
    """Not expanded, and not disturbed.

    The same one flag on the same one racer through the same one appearance,
    and every number within a rounding step of V27.1's column - which is the
    whole question this pass asks of it.
    """
    got = _measured("country.json")
    assert got["flag"] == v271.FLAG.key
    assert got["racer"] == v271.FLAG_RACER
    for key in v271.FLAG_MOMENTS:
        before = got["moments"][key]["worlds"]["v271"]
        after = got["moments"][key]["worlds"]["v272"]
        assert after["bands"] == before["bands"] >= 2
        assert abs(after["delta_e"] - before["delta_e"]) < 0.5


def test_the_country_skin_is_still_one_appearance_behind_one_flag():
    """No country system: V27.1's file is not grown by this pass."""
    body = RACER_GD.read_text(encoding="utf-8")
    assert body.count("flag_in") >= 1
    for invented in ("flag_us", "flag_gb", "flag_jp", "COUNTRIES",
                     "country_of", "NATIONS"):
        assert invented not in body, f"racer_visual grew {invented}"
    assert "flag_racer" in ROOT.joinpath(
        "godot", "scripts", "sloped_race_scene.gd").read_text(encoding="utf-8")


def test_the_cost_is_within_two_per_cent_with_identical_geometry():
    got = _measured("timing.json")
    against = got.get("against_v271")
    if against is None:
        pytest.skip("timing not measured against V27.1 in this tree")
    assert against["identical_geometry"], "the delta added geometry"
    assert abs(against["percent"]) <= 2.0, against


def test_the_two_at_lists_agree_on_the_frames_they_share():
    """The reproducibility trap, bounded rather than assumed.

    V27 found that a still is only comparable with one asked for in the same
    `--at` list. This pass renders four moments in both lists on purpose so the
    size of that effect is a measured number; if it ever grew past a luma, the
    report's cross-list quotations would stop being safe.
    """
    got = _measured("listcheck.json")
    assert got["worst_d_separation"] <= 1.0, got["worst_d_separation"]


# --- the probe that chose the fix -------------------------------------------


def test_the_isolate_probe_is_a_difference_and_not_a_hue_match():
    """The instrument bug this pass hit, as an assertion.

    The first version classified the probe by nearest hue and reported 0.00%
    cover for all eight objects: the isolate hue is authored `#00FF80` and
    renders `(127, 243, 154)`, because an unshaded albedo still goes through
    the profile's grade. A difference cannot fail that way.
    """
    body = LAB.read_text(encoding="utf-8")
    assert "def _isolate_mask" in body
    assert "np.abs(base - probe).max(axis=2) > v272.DIFF_FLOOR" in body
    assert "ISOLATE_HUE" not in body.split("def _isolate_mask")[1][:2000]


def test_every_isolate_names_a_material_the_profile_actually_has():
    """A probe that re-materials nothing measures nothing.

    The generator raises on a mismatch; this is the same check as data, so a
    profile edit that moved one of these objects fails here rather than
    silently producing a table of zeroes.
    """
    resolved = env.resolve(v272.PARENT)
    for one in v272.ISOLATES:
        found = resolved
        for part in one.path:
            found = found[part]
        assert found == one.material, \
            f"{one.key}: profile says {found}, table says {one.material}"


def test_the_isolate_key_is_built_by_nothing_the_hall_makes():
    """`hall_grate` is the spare key, and that is why the probe is exact."""
    body = (PROFILES / "contained_hall.json").read_text(encoding="utf-8")
    assert v272.ISOLATE_KEY not in body
    assert v272.ISOLATE_KEY not in (
        PROFILES / "contained_hall_v271.json").read_text(encoding="utf-8")
    assert v272.ISOLATE_KEY not in (
        PROFILES / "contained_hall_v272.json").read_text(encoding="utf-8")
    # and lab_palette does know it, or the probe would push_error
    palette = (GODOT / "assets" / "marble_machine"
               / "lab_palette.gd").read_text(encoding="utf-8")
    assert f'"{v272.ISOLATE_KEY}"' in palette


def test_the_probe_hues_do_not_collide_with_each_other():
    """V27.1 §3.1's lesson as arithmetic: two things one colour is the bug."""
    import tools.sloped_v272_profiles as gen

    hexes = (list(v271.SURFACES.values()) + [gen.ISOLATE_HUE]
             + [v271.SURFACE_GROUND])
    points = [tuple(int(one[i:i + 2], 16) for i in (1, 3, 5)) for one in hexes]
    for index, first in enumerate(points):
        for second in points[index + 1:]:
            gap = sum((a - b) ** 2 for a, b in zip(first, second)) ** 0.5
            assert gap > 80.0, f"{first} and {second} are {gap:.0f} apart"


def test_the_isolate_probe_does_not_reach_the_machine():
    """A world material may not change a machine pixel.

    Measured rather than argued: the lab records the leak for every object at
    every moment. The finish pad's is the only one that is not zero, and the
    report says why - the machine's transparent guards show the world behind
    them, so a pixel the mask calls machine really does change.
    """
    got = _measured("isolate.json")
    for name, leak in got["leak"].items():
        assert leak < 0.01, f"{name} leaked {leak:.4%} of the frame"


def test_the_named_object_is_the_one_with_the_largest_prize():
    """The fix went to the top of the ranked table, not to a preference."""
    got = _measured("isolate.json")
    ranked = got["ranked"]
    assert ranked[0]["material"] == "hall_panel_dark", ranked[0]
    assert ranked[0]["gain"] > 0.0
    top_two = {one["material"] for one in ranked[:2]}
    assert top_two == {"hall_panel_dark"}, top_two


# --- render neutrality ------------------------------------------------------
#
# Godot-gated, exactly as V27's and V27.1's suites are.


GODOT_BIN = os.environ.get("GODOT_BIN") or os.environ.get("GODOT4_BIN")
CAN_RENDER = bool(GODOT_BIN and Path(GODOT_BIN).is_file()
                  and TRACK.is_file() and REPLAY.is_file()
                  and CONTRACT.is_file())


def _render(tmp_path: Path, environment: str, at: str,
            extra: tuple[str, ...] = ()) -> tuple[Path, str]:
    out = tmp_path / environment.replace("/", "_")
    out.mkdir(parents=True, exist_ok=True)
    done = subprocess.run(
        [GODOT_BIN, "--path", str(GODOT),
         "res://scenes/SlopedRaceRender.tscn", "--",
         f"--out-dir={out}", f"--replay={REPLAY}", f"--cameras={TRACK}",
         f"--start-contract={CONTRACT}", f"--at={at}",
         "--width=270", "--height=480",
         "--layout=b", "--detail=hero", "--routes=both",
         "--finish-sign=double", "--machine=v23b", "--racers=meridian",
         f"--environment={environment}", *extra],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    assert done.returncode == 0, done.stderr[-2000:]
    for line in (done.stderr or "").splitlines():
        assert "SCRIPT ERROR" not in line, line
        assert "course_scene:" not in line, line
    return out, done.stdout or ""


def _digests(directory: Path) -> dict[str, str]:
    import hashlib

    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.glob("*.png"))}


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_v26_v27_and_v271_still_render_what_they_rendered(tmp_path):
    """Three editions' reproducibility, taken as hashes rather than argued.

    All of them through the *same* `--at` list, because a still is only
    comparable with one asked for in the same list.
    """
    at = "0.000,15.267,17.517"
    first = {name: _render(tmp_path / "a", name, at)[0]
             for name in ("aurora_valley_v26", v272.GRANDPARENT, v272.PARENT)}
    again = {name: _render(tmp_path / "b", name, at)[0]
             for name in ("aurora_valley_v26", v272.GRANDPARENT, v272.PARENT)}
    for name, folder in first.items():
        assert _digests(folder) == _digests(again[name]), name
    seen = [tuple(sorted(_digests(folder).items())) for folder in first.values()]
    assert len(set(seen)) == len(seen), "two editions rendered the same picture"


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_correction_changes_the_merge_and_not_the_hook(tmp_path):
    """The delta, as pixels."""
    at = "0.000,15.267"
    before, _ = _render(tmp_path, v272.PARENT, at)
    after, _ = _render(tmp_path, v272.PROFILE, at)
    one, two = _digests(before), _digests(after)
    assert one["at_000.000.png"] == two["at_000.000.png"], \
        "the merge fix reached frame zero"
    assert one["at_015.267.png"] != two["at_015.267.png"], \
        "the merge fix did not reach the merge"


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_correction_builds_the_same_world_as_v271(tmp_path):
    """Same census, same counts: a material value and not a build change."""
    _before, one = _render(tmp_path, v272.PARENT, "0.000")
    _after, two = _render(tmp_path, v272.PROFILE, "0.000")

    def line(stdout: str, prefix: str) -> str:
        for row in stdout.splitlines():
            if row.strip().startswith(prefix):
                return row.strip()
        return ""

    assert line(one, "world:"), "the scene printed no world census"
    assert line(one, "world:") == line(two, "world:")
    assert line(one, "scene: 1513"), "the scene printed no mesh count"
    assert line(one, "scene: 1513") == line(two, "scene: 1513")


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_marker_over_v272_is_the_marker_over_v271(tmp_path):
    """The claim that the ruler did not move, as a render.

    An unshaded marker surface has no specular response, so a specular-only
    delta cannot reach a marker frame. That is an argument; this is the proof,
    and it is what lets V27.1's and V27.2's separations be read side by side.
    """
    import tools.sloped_v272_profiles as gen

    at = "0.000,15.267"
    with gen.temporary([gen.marker(v272.PROFILE)]):
        mine, _ = _render(tmp_path / "v272", v272.MARKER, at)
        digests = _digests(mine)
    theirs, _ = _render(tmp_path / "v271", "_marker_v271", at)
    assert digests == _digests(theirs)
    assert gen.leftovers() == [], "the marker outlived its context manager"


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_a_temporary_profile_is_registered_then_removed(tmp_path):
    """The mechanism the no-artefact rule depends on, exercised end to end."""
    import tools.sloped_v272_profiles as gen

    index_before = (PROFILES / "index.json").read_bytes()
    document = gen.isolate_probe("merge_backing", over=v272.PARENT)
    with gen.temporary([document]) as names:
        assert names == [document["id"]]
        assert (PROFILES / f"{document['id']}.json").is_file()
        assert document["id"] in _read("index")["profiles"]
        out, _ = _render(tmp_path, document["id"], "15.267")
        assert _digests(out), "the probe rendered nothing"
    assert not (PROFILES / f"{document['id']}.json").exists()
    assert (PROFILES / "index.json").read_bytes() == index_before
