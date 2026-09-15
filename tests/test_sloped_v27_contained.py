"""What V27 must be true of: three new rooms, and nothing else moved.

V27 is an environment experiment, so almost every assertion here is that
something did **not** change. The pass adds five builders, eleven material
keys and eight profiles; it may not touch the physics, the replay, the camera
track, the edit, the machine, the racers, the overlays or any world shipped
before it, and each of those is checked against a file rather than against a
docstring.

The suite is organised by what could go wrong:

* **the profiles are data and they resolve.** Eight new files, all valid, all
  in the index, all reaching Godot through `--environment=` and nothing else;
* **the stage is render-only.** No collider, no landform field, no physics
  import, and every builder behind a key no earlier profile carries;
* **V26 is byte-identical.** Its profile file, its resolved dictionary, its
  census and its four flags are untouched, and so is every profile before it;
* **the film is V24's.** The seed, the replay path, the camera track file, the
  edit map and the twelve moment seconds are all re-derived from the delivered
  track and checked, so a moved cut boundary fails here;
* **the two tables cannot drift.** The band table is disjoint, the marker
  profiles are generated from it, and re-running the generator is a no-op.

The replay and the solved track are generated output and not in the branch, so
the tests that need them skip rather than fail.
"""

from __future__ import annotations

import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import layout, v23, v24, v26
from sloped import v27_contained as v27

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PROFILES = GODOT / "assets" / "marble_machine" / "environment" / "profiles"
ENV_DIR = GODOT / "assets" / "marble_machine" / "environment"
STAGE_GD = ENV_DIR / "environment_stage.gd"
WORLD_GD = ENV_DIR / "environment_world.gd"
PROFILE_GD = ENV_DIR / "environment_profile.gd"
PALETTE_GD = GODOT / "assets" / "marble_machine" / "lab_palette.gd"
GENERATOR = ROOT / "tools" / "sloped_v27_profiles.py"
LAB = ROOT / "tools" / "sloped_v27_contained.py"

OUT = ROOT / "output" / "sloped_race_v1"
TRACK = OUT / f"cameras_v24_{v27.SEED}.json"
REPLAY = OUT / f"race_{v27.SEED}.json"

#: Every profile that existed before this pass. None of them may change and
#: none of them may gain a V27 section.
HISTORICAL = (
    "alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
    "aurora_valley", "aurora_valley_v25", "aurora_valley_v25a",
    "aurora_valley_v25b", "aurora_valley_v25c", "aurora_valley_v251",
    "aurora_valley_v252", "aurora_valley_v26",
)

#: The five keys this pass adds under `world`. No profile older than V27 may
#: carry one, and every one of them must be in the build order.
STAGE_KEYS = ("deck", "shell", "pylons", "canopy", "bays")

#: The eleven material keys this pass adds. No machine pass may name one.
STAGE_MATERIALS = (
    "hall_panel", "hall_panel_dark", "hall_rib", "hall_trim", "hall_deck",
    "hall_deck_dark", "hall_glass", "hall_beam", "hall_grate",
    "lit_hall_warm", "lit_hall_cool",
)

NEW_PROFILES = ("contained_base", "contained_hall", "diorama_chamber",
                "industrial_chamber", "_marker_v27a", "_marker_v27b",
                "_marker_v27c", "_marker_v27_control")


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _json(path: Path):
    return json.loads(_text(path))


# --- the profiles are data, and they resolve --------------------------------


def test_every_new_profile_is_in_the_index():
    listed = _json(PROFILES / "index.json")["profiles"]
    for name in NEW_PROFILES:
        assert name in listed, f"{name} is not in index.json"


def test_every_new_profile_file_exists_and_parses():
    for name in NEW_PROFILES:
        path = PROFILES / f"{name}.json"
        assert path.is_file(), f"{path} is missing"
        assert isinstance(_json(path), dict)


@pytest.mark.parametrize("name", NEW_PROFILES)
def test_new_profiles_resolve_without_complaint(name):
    profile = env.resolve(name)
    assert env.validate(profile) == [], env.validate(profile)


def test_the_concept_table_names_real_profiles():
    listed = set(_json(PROFILES / "index.json")["profiles"])
    for entry in v27.ALL:
        assert entry.key in listed
        assert v27.marker(entry.key) in listed


def test_every_concept_extends_the_shared_base():
    for entry in v27.CONCEPTS:
        assert env.load(entry.key)["extends"] == "contained_base"
    assert env.load("contained_base")["extends"] == v26.ENVIRONMENT


def test_the_base_builds_no_architecture_of_its_own():
    """`contained_base` is the empty stage: a spine, not a room."""
    world = env.resolve("contained_base")["world"]
    for key in STAGE_KEYS:
        assert key not in world, f"contained_base carries {key}"


def test_each_concept_builds_at_least_a_wall_and_a_floor():
    for entry in v27.CONCEPTS:
        world = env.resolve(entry.key)["world"]
        assert "shell" in world, f"{entry.key} has no enclosure"
        assert "deck" in world, f"{entry.key} has no floor"


def test_the_generator_is_a_no_op():
    """Re-running the generator must write nothing.

    The profiles are committed and the generator is how they are regenerated;
    a generator that has drifted from its output is a table nobody is reading.
    """
    done = subprocess.run([sys.executable, str(GENERATOR)],
                          cwd=str(ROOT), capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "", \
        "the generator rewrote files:\n" + done.stdout


# --- nothing older than V27 changed -----------------------------------------


def test_v26_still_names_its_own_world():
    assert v26.ENVIRONMENT == "aurora_valley_v26"
    assert v26.BASE_ENVIRONMENT == "aurora_valley_v252"
    assert v26.MACHINE == v23.MACHINE
    assert v26.RACERS == v24.RACERS


def test_v26_scene_flags_are_unchanged():
    assert v26.SCENE_FLAGS == (
        v23.FINISH_SIGN,
        "--environment=aurora_valley_v26",
        f"--machine={v23.MACHINE}",
        f"--racers={v24.RACERS}",
    )


@pytest.mark.parametrize("name", HISTORICAL)
def test_historical_profiles_carry_no_stage_section(name):
    world = env.resolve(name).get("world", {})
    for key in STAGE_KEYS:
        assert key not in world, f"{name} gained a V27 {key} section"


@pytest.mark.parametrize("name", HISTORICAL)
def test_historical_profiles_name_no_stage_material(name):
    palette = env.resolve(name).get("palette", {})
    for key in STAGE_MATERIALS:
        assert key not in palette, f"{name} gained the V27 material {key}"


@pytest.mark.parametrize("name", HISTORICAL)
def test_historical_profiles_still_resolve(name):
    assert env.validate(env.resolve(name)) == []


def test_v26_resolves_to_exactly_what_it_did():
    """The two leaves V26 is defined by, and its parent's identity.

    Not a hash of the whole profile - that would fail on a formatting change
    and say nothing - but the three facts `sloped/v26.py` documents: it extends
    V25.2, it moves one scarp three units, and it changes nothing else
    geometric.
    """
    profile = env.resolve("aurora_valley_v26")
    parent = env.resolve("aurora_valley_v252")
    changed = [row for row in env.diff(parent, profile)
               if not row[0].startswith(("id", "title", "summary", "extends"))]
    assert len(changed) == 1, changed
    path, before, after = changed[0]
    assert path == "world.scarps.sites"
    assert before[8] == [31.0, 34.0, 90.0, 1.0]
    assert after[8] == [34.0, 34.0, 90.0, 1.0]


# --- the stage is render-only -----------------------------------------------


def test_the_stage_declares_no_collider():
    body = _text(STAGE_GD)
    for banned in ("StaticBody3D", "CollisionShape3D", "RigidBody3D",
                   "Area3D", "PhysicsBody3D", "create_trimesh_collision",
                   "create_convex_collision"):
        assert banned not in body, f"environment_stage.gd mentions {banned}"


def test_the_stage_writes_no_terrain():
    """It may read `Terrain.height`; it may never set a landform field."""
    body = _text(STAGE_GD)
    assert "Terrain.height(" in body
    for field in env.SHAPE_FIELDS:
        assert f'cfg["{field}"]' not in body
        assert f"cfg.set({field}" not in body


def test_no_stage_profile_carries_a_landform_field():
    for name in NEW_PROFILES:
        terrain = env.resolve(name).get("terrain", {})
        for field in env.SHAPE_FIELDS:
            assert field not in terrain, f"{name} sets terrain.{field}"


def test_the_stage_is_reached_only_through_the_build_order():
    world = _text(WORLD_GD)
    order = re.search(r"const BUILD_ORDER := \[(.*?)\]", world, re.S)
    assert order is not None
    listed = re.findall(r'"([a-z_]+)"', order.group(1))
    for key in STAGE_KEYS:
        assert key in listed, f"{key} is not in BUILD_ORDER"
    # The eleven that were there keep their relative order.
    before = ["patches", "walls", "ridges", "scarps", "spires", "boulders",
              "anchors", "trees", "landmarks", "ravine", "lamps"]
    kept = [one for one in listed if one in before]
    assert kept == before


def test_the_stage_order_and_the_build_order_agree():
    stage = _text(STAGE_GD)
    order = re.search(r"const STAGE_ORDER := \[(.*?)\]", stage, re.S)
    assert order is not None
    assert set(re.findall(r'"([a-z_]+)"', order.group(1))) == set(STAGE_KEYS)


def test_every_builder_tests_the_camera_path():
    """A form that ignores the lens is a lens cap, and one did.

    The canopy shipped its first build with no keep-out at all and put a beam
    across the FINISH board. Every builder that places anything must reach the
    shared `_sited` test.
    """
    stage = _text(STAGE_GD)
    for builder in ("_deck", "_shell_band", "_pylon_band", "_canopy",
                    "_bays"):
        start = stage.index(f"static func {builder}(")
        nxt = stage.find("\nstatic func ", start + 1)
        body = stage[start:nxt if nxt > 0 else len(stage)]
        assert "_sited(" in body, f"{builder} never calls _sited"


def test_the_new_materials_exist_in_the_palette():
    body = _text(PALETTE_GD)
    for key in STAGE_MATERIALS:
        assert f'"{key}":' in body, f"lab_palette has no {key}"


def test_no_machine_pass_names_a_stage_material():
    """The disjointness rule V23's suite enforces, for the new keys.

    A profile names world surfaces and a machine pass names machine surfaces;
    an overlap is the bug, not the ordering.
    """
    body = _text(PALETTE_GD)
    start = body.index("MACHINE_PASSES")
    end = body.index("func ", start)
    passes = body[start:end]
    for key in STAGE_MATERIALS:
        assert f'"{key}"' not in passes, f"a machine pass names {key}"


# --- the band table ---------------------------------------------------------


def test_the_bands_are_disjoint():
    """One surface may not belong to two depth bands - V25.2's lesson."""
    for table in (v27.MARKED, v27.MARKED_CONTROL):
        seen: dict[str, str] = {}
        for band, keys in table.items():
            for key in keys:
                assert key not in seen, \
                    f"{key} is in both {seen[key]} and {band}"
                seen[key] = band


def test_every_stage_material_is_banded_or_emissive():
    banded = {key for keys in v27.MARKED.values() for key in keys}
    for key in STAGE_MATERIALS:
        if key.startswith("lit_"):
            assert key not in banded, f"{key} is emissive and cannot be a band"
            continue
        assert key in banded, f"{key} belongs to no depth band"


def test_hall_trim_is_the_shells_alone():
    """The one key both the wall and a column could have claimed.

    `hall_trim` is the shell's cornice and plinth and nothing else, which is
    what keeps the band table disjoint. A pylon cap is `hall_rib` in all three
    profiles and this is the assertion that keeps it that way.
    """
    assert "hall_trim" in v27.MARKED["shell"]
    for entry in v27.CONCEPTS:
        world = env.resolve(entry.key)["world"]
        cap = world.get("pylons", {}).get("cap", {})
        assert cap.get("material", "hall_rib") != "hall_trim", entry.key


def test_the_markers_are_generated_from_the_band_table():
    for entry in v27.ALL:
        marker = env.resolve(v27.marker(entry.key))
        palette = marker["palette"]
        for band, keys in v27.marked_for(entry.key).items():
            want = "#%02X%02X%02X" % v27.layer(band).hue
            for key in keys:
                assert palette[key]["albedo"] == want, f"{key} in {band}"
                assert palette[key]["unshaded"] is True
                assert palette[key]["no_fog"] is True


def test_a_marker_changes_nothing_but_paint():
    """A diagnostic twin must be the same geometry as what it measures."""
    for entry in v27.ALL:
        base = env.resolve(entry.key)
        marker = env.resolve(v27.marker(entry.key))
        for path, before, after in env.diff(base, marker):
            assert path.startswith(("palette.", "id", "title", "family",
                                    "summary", "extends")), \
                f"{v27.marker(entry.key)} changes {path}"


# --- the film is V24's ------------------------------------------------------


def test_the_lab_renders_through_v24s_own_track():
    body = _text(LAB)
    assert 'f"cameras_v24_{SEED}.json"' in body
    assert "SEED = v27.SEED" in body
    assert v27.SEED == 5432


def test_the_lab_holds_every_other_flag_fixed():
    """Only `--environment=` may differ between two renders in this lab."""
    body = _text(LAB)
    fixed = re.search(r"FIXED_FLAGS = \((.*?)\)", body, re.S)
    assert fixed is not None
    flags = re.findall(r'"(--[a-z-]+=?[a-z0-9]*)"', fixed.group(1))
    assert "--machine=v23b" in flags
    assert "--racers=meridian" in flags
    assert "--finish-sign=double" in flags
    assert "--environment" not in " ".join(flags)


def test_the_lab_never_writes_the_replay_or_the_track():
    body = _text(LAB)
    for line in body.splitlines():
        if "open(" in line and '"w"' in line:
            assert "REPLAY" not in line and "TRACK" not in line, line
    assert "sloped_course(" not in body
    assert "import pybullet" not in body


def test_no_v27_file_imports_the_physics():
    for path in (ROOT / "sloped" / "v27_contained.py", LAB, GENERATOR):
        body = _text(path)
        assert "pybullet" not in body
        assert "from marble3d" not in body


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_every_moment_is_inside_the_cut_that_owns_it():
    """The twelve seconds are re-derived from the delivered track.

    A cut boundary that moved would put a moment in the wrong shot and every
    sheet in this pass would be comparing two different instants; this is the
    assertion that fails instead.
    """
    track = _json(TRACK)
    spans = [(segment["out"][0], segment["out"][1], segment["replay"][0])
             for segment in track["edit"]]
    for one in v27.MOMENTS:
        match = [row for row in spans
                 if row[0] - 1e-6 <= one.second <= row[1] + 1e-6]
        assert match, f"{one.key} at {one.second} is in no cut"
        low, _, replay_low = match[0]
        want = replay_low + (one.second - low)
        assert abs(want - one.replay) < 1e-3, \
            f"{one.key}: output {one.second} is replay {want}, table says " \
            f"{one.replay}"


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_moments_span_the_whole_film():
    track = _json(TRACK)
    assert v27.MOMENTS[0].second == 0.0
    assert v27.MOMENTS[-1].second < float(track["duration"])
    seconds = [one.second for one in v27.MOMENTS]
    assert seconds == sorted(seconds)


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_parallax_pairs_are_inside_one_cut_each():
    """A pair that straddles a cut measures an edit, not a camera move."""
    track = _json(TRACK)
    spans = [(segment["out"][0], segment["out"][1])
             for segment in track["edit"]]
    for label, before, after in v27.PARALLAX_PAIRS:
        holding = [row for row in spans
                   if row[0] - 1e-6 <= before and after <= row[1] + 1e-6]
        assert holding, f"{label} straddles a cut"


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_keepout_covers_the_camera_track_it_renders_through():
    """Every V24 camera position must be near a keep-out point.

    The inherited list was decimated from V22.1's two tracks and V26 renders
    V24's; the generator appends V24's own path for exactly this reason, and
    four units is the spacing it decimates at.
    """
    keepout = env.resolve("contained_hall")["world"]["keepout"]
    track = _json(TRACK)
    worst = 0.0
    for cut in track["cuts"]:
        for frame in cut["frames"]:
            gap = min(math.hypot(frame[1] - a, frame[3] - b)
                      for a, b in keepout)
            worst = max(worst, gap)
    assert worst < 4.0, f"a camera stands {worst:.2f} from the nearest point"


@pytest.mark.skipif(not (TRACK.is_file() and REPLAY.is_file()),
                    reason="replay or track not in branch")
def test_the_replay_the_lab_reads_is_seed_5432():
    assert _json(REPLAY)["seed"] == 5432
    assert _json(TRACK)["seed"] == 5432


# --- the envelope measurement -----------------------------------------------


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_no_v26_frame_looks_above_its_own_eye_height():
    """The measurement the three profiles were rebuilt around.

    Elevation 30 to 54 degrees against a vertical field of 34 to 36 means the
    top edge of every frame is below horizontal. If a future camera solve
    breaks that, the "a ceiling is invisible" finding stops being true and this
    test is where it says so.
    """
    frames = v27.frames_of(_json(TRACK))
    worst = min(
        math.degrees(math.atan2(-(frame[5] - frame[2]),
                                math.hypot(frame[4] - frame[1],
                                           frame[6] - frame[3])))
        - float(frame[7]) / 2.0
        for frame in frames)
    assert worst > 0.0, \
        f"a frame's top edge is {worst:.2f} degrees above horizontal"


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_visible_ceiling_falls_with_radius_on_the_finish_side():
    """Further out is lower in frame, which is what a wall has to be built to.

    Read on bearing 0, which is the finish side and the one where the ground
    has fallen furthest.
    """
    frames = v27.frames_of(_json(TRACK))
    heights = []
    for radius in (30.0, 70.0, 110.0, 160.0):
        heights.append(v27.visible_ceiling(
            frames, v27.CENTRE[0], v27.CENTRE[1] + radius))
    assert all(one is not None for one in heights)
    assert heights == sorted(heights, reverse=True), heights


# --- the stage geometry keeps clear -----------------------------------------


def test_every_shell_band_has_a_camera_keepout():
    for entry in v27.CONCEPTS:
        shell = env.resolve(entry.key)["world"]["shell"]
        for index, band in enumerate(shell.get("bands", [shell])):
            assert float(band.get("keepout", 0.0)) > 0.0, \
                f"{entry.key} shell band {index} has no keep-out"


def test_the_floor_pads_disable_both_guards_on_purpose():
    """A plate under the racing line is the one form that must not be sited.

    It is also exactly what rejection sampling exists to refuse, so the two
    zeroes are a deliberate, reviewable statement rather than an omission.
    """
    for entry in v27.CONCEPTS:
        deck = env.resolve(entry.key)["world"]["deck"]
        for pad in deck.get("pads", []):
            assert float(pad.get("clearance", -1.0)) == 0.0, entry.key
            assert float(pad.get("keepout", -1.0)) == 0.0, entry.key


def test_no_bay_is_authored_at_the_obstacle():
    """The site search found no legal, in-frame, behind-the-action position.

    If a later pass finds one, this test is where the finding is revisited
    rather than quietly contradicted.
    """
    for entry in v27.CONCEPTS:
        sites = env.resolve(entry.key)["world"]["bays"]["sites"]
        assert "obstacle" not in sites, \
            f"{entry.key} authors an obstacle bay; re-run --stage sites"


def test_every_bay_names_a_node_the_layout_has():
    for entry in v27.CONCEPTS:
        sites = env.resolve(entry.key)["world"]["bays"]["sites"]
        for name, site in sites.items():
            node = site.get("node", name)
            assert node in layout.NODES, f"{entry.key} bay {name} -> {node}"


def test_the_three_concepts_are_genuinely_different():
    """Not palette variants: the enclosures differ in plan and in rhythm."""
    walls = {}
    for entry in v27.CONCEPTS:
        shell = env.resolve(entry.key)["world"]["shell"]
        bands = shell.get("bands", [shell])
        walls[entry.tag] = {
            "bands": len(bands),
            "radii": sorted({float(band.get("radius", 0.0))
                             for band in bands}),
            "segments": sum(int(band.get("count", 0)) for band in bands),
            "lobed": any(float(band.get("radius_step", 0.0)) != 0.0
                         for band in bands),
            "full_ring": [abs(float(band.get("bearing_step", 0.0))
                              * int(band.get("count", 0)) - 360.0) < 1.0
                          for band in bands],
        }
    assert walls["a"]["radii"] != walls["b"]["radii"]
    assert walls["b"]["radii"] != walls["c"]["radii"]
    assert walls["b"]["lobed"] and not walls["a"]["lobed"]
    # A and B each close at least one full ring; C closes only its far one,
    # because its near wall is two facing arcs and that is its whole idea.
    assert any(walls["a"]["full_ring"])
    assert any(walls["b"]["full_ring"])
    assert sum(walls["c"]["full_ring"]) == 1, walls["c"]["full_ring"]
    assert walls["c"]["radii"][0] < min(walls["a"]["radii"]),         "C's near wall should stand closer than A's"


def test_the_contained_stages_are_cheaper_than_the_outdoor_world():
    """Part X, checked against the census rather than against a claim.

    The census is written by a render, so this skips without one - but when it
    is there, "contained is cheaper" stops being a sentence in a report.
    """
    cost = ROOT / "output" / "sloped_race_v1" / "v27_contained" / "cost.json"
    if not cost.is_file():
        pytest.skip("no render cost recorded")
    table = _json(cost)
    if not all(tag in table for tag in ("v26", "a", "b", "c")):
        pytest.skip("cost table is incomplete")
    control = table["v26"]
    for tag in ("a", "b", "c"):
        assert table[tag]["meshes"] < control["meshes"], tag
        assert table[tag]["triangles"] < control["triangles"], tag


# --- the documentation ------------------------------------------------------


def test_the_pass_is_documented():
    doc = ROOT / "docs" / "sloped_race_v27_contained.md"
    assert doc.is_file()
    body = _text(doc)
    for heading in ("motivation", "Concept A", "Concept B", "Concept C",
                    "Recommendation", "Weaknesses"):
        assert heading.lower() in body.lower(), f"the doc has no {heading}"
    for entry in v27.CONCEPTS:
        assert entry.key in body


# --- render neutrality ------------------------------------------------------
#
# Godot-gated: these skip unless $GODOT_BIN names an executable, because a
# render is not something a unit suite can require.


GODOT_BIN = os.environ.get("GODOT_BIN") or os.environ.get("GODOT4_BIN")
CAN_RENDER = bool(GODOT_BIN and Path(GODOT_BIN).is_file()
                  and TRACK.is_file() and REPLAY.is_file())


def _render_v26_census(tmp_path: Path) -> str:
    out = tmp_path / "frames"
    out.mkdir()
    done = subprocess.run(
        [GODOT_BIN, "--path", str(GODOT),
         "res://scenes/SlopedRaceRender.tscn", "--",
         f"--out-dir={out}",
         f"--replay={REPLAY}", f"--cameras={TRACK}",
         f"--start-contract={OUT / f'start_contract_{v27.SEED}.json'}",
         "--at=0.000", "--width=270", "--height=480",
         "--layout=b", "--detail=hero", "--routes=both",
         *[flag for flag in v26.SCENE_FLAGS]],
        cwd=str(ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace")
    assert done.returncode == 0, done.stderr[-2000:]
    for line in (done.stdout or "").splitlines():
        if line.strip().startswith("world:"):
            return line.strip()
    return ""


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_a_v26_render_builds_no_stage_feature(tmp_path):
    """The census is what the scene says it made, and it must be V25.2's.

    A build order that leaked a V27 key into an earlier profile would show up
    here as an extra entry, and nowhere else until somebody diffed a frame.
    """
    census = _render_v26_census(tmp_path)
    assert census, "the scene printed no world census"
    for key in STAGE_KEYS:
        assert f"{key} " not in census, f"a V26 render built {key}: {census}"
    for key in ("patches", "walls", "ridges", "scarps", "spires", "boulders",
                "anchors", "trees", "landmarks", "ravine", "lamps"):
        assert f"{key} " in census, f"a V26 render lost {key}: {census}"
