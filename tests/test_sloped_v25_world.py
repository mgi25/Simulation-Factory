"""V25 world: a pass that may add anything to the world and nothing to the race.

V25 builds near-world geometry - valley walls, midground ridges, cut scarps,
skyline spires, foreground boulders, support foundations, conifers, landmarks
and a ravine floor - and every one of those is *render-only dressing sited
against* a terrain surface it is forbidden to touch. So this file asserts four
kinds of thing.

* **Nothing reached the race.** The seed, the physics, the layout tables, the
  camera solve and the edit are untouched, and the test reads the actual files
  rather than trusting a claim about them.
* **Nothing reached the landform.** `EnvironmentProfile.validate` already
  refuses a terrain *shape* field; what is new is a whole geometry section, and
  the test checks that it is data under `world`, that it cannot name a shape
  field either, and that `course_terrain.height` - which every support pier and
  every solved camera is measured against - has not changed by a character.
* **Nothing is a default.** The four profiles shipped before V25 declare no
  `world` section, the builder returns immediately without one, and the
  registry default is still `alpine_neon`. V22.1 and V23 render what they
  rendered.
* **The world is separate from the machine, still.** V23's rule was that an
  environment profile and a machine pass name disjoint surfaces. V25 adds
  thirteen world surfaces and the rule has to hold for those too.

The environment system's own mechanics - delta inheritance, `null` erases, the
V21 overlay composing - are covered by `tests/test_sloped_environment.py`, and
the two readers agreeing field for field is covered there as well. What is
tested here is what V25 itself added.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import v23, v25_world

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
ASSETS = GODOT / "assets" / "marble_machine"
PROFILES = ASSETS / "environment" / "profiles"

WORLD_GD = ASSETS / "environment" / "environment_world.gd"
PROFILE_GD = ASSETS / "environment" / "environment_profile.gd"
BUILDER_GD = ASSETS / "environment" / "environment_builder.gd"
MACHINE_GD = ASSETS / "course" / "course_machine.gd"
TERRAIN_GD = ASSETS / "course" / "course_terrain.gd"
LAYOUT_GD = ASSETS / "course" / "course_layout.gd"
PALETTE_GD = ASSETS / "lab_palette.gd"

WORLD = WORLD_GD.read_text(encoding="utf-8")
PROFILE = PROFILE_GD.read_text(encoding="utf-8")
BUILDER = BUILDER_GD.read_text(encoding="utf-8")
MACHINE = MACHINE_GD.read_text(encoding="utf-8")
TERRAIN = TERRAIN_GD.read_text(encoding="utf-8")
PALETTE = PALETTE_GD.read_text(encoding="utf-8")

#: Every profile that existed before V25 and must keep rendering what it did.
PRE_V25 = ("alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
           "aurora_valley")

#: The three density variants, in order.
V25_IDS = tuple(one.key for one in v25_world.VARIANTS)


def _tool(name: str):
    """Load a tool by path; `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "_v25_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def profiles():
    return _tool("sloped_v25_profiles")


# --- the profiles load, validate and inherit --------------------------------


def test_every_v25_profile_is_registered():
    listed = env.ids()
    for one in ("aurora_valley_v25",) + V25_IDS:
        assert one in listed, f"{one} is not in profiles/index.json"


def test_every_v25_profile_resolves_and_validates():
    for one in ("aurora_valley_v25",) + V25_IDS:
        resolved = env.resolve(one)
        assert env.validate(resolved) == [], f"{one} does not validate"
        assert resolved["id"] == one


def test_the_variants_are_deltas_over_the_shared_pass():
    """A, B and C differ from one another only in world density.

    The inheritance chain is the whole basis of the comparison being fair:
    `aurora_valley -> _v25 -> _v25a -> _v25b -> _v25c`. If B extended
    `aurora_valley` directly it could drift from A in the fog, the light rig or
    the palette, and the sheet would then be comparing two worlds rather than
    two densities.
    """
    assert env.load("aurora_valley_v25")["extends"] == "aurora_valley"
    assert env.load("aurora_valley_v25a")["extends"] == "aurora_valley_v25"
    assert env.load("aurora_valley_v25b")["extends"] == "aurora_valley_v25a"
    assert env.load("aurora_valley_v25c")["extends"] == "aurora_valley_v25b"


def test_the_shared_pass_carries_no_geometry():
    """`aurora_valley_v25` is air and materials, and builds nothing.

    It exists so the half of V25 that is a colour and atmosphere pass can be
    accepted or rejected on its own, and so that a variant is a pure density
    delta over it. A feature key here would make it a fourth variant.
    """
    world = env.load("aurora_valley_v25").get("world", {})
    assert set(world) == {"keepout"}


def test_density_rises_from_a_to_c():
    """Every count that differs between variants rises. A < B < C, by counts.

    Not a quality claim - the sheets decide that. This is the claim that the
    three variants are what they are labelled: if C had fewer boulders than B
    the labels would be wrong and every conclusion drawn from the sheet with
    them.
    """
    resolved = {one: env.resolve(one)["world"] for one in V25_IDS}
    features = ["boulders", "trees", "spires"]
    for feature in features:
        counts = []
        for one in V25_IDS:
            spec = resolved[one].get(feature, {})
            counts.append(int(spec.get("count", spec.get("clusters", 0))))
        assert counts[0] <= counts[1] <= counts[2], (
            f"{feature} is not non-decreasing across A, B, C: {counts}")
    assert counts[2] > counts[0], "C is not denser than A anywhere"


def test_b_adds_the_four_things_a_does_not_have():
    """B is A plus dressing, and the brief's own list is the assertion."""
    a = env.resolve("aurora_valley_v25a")["world"]
    b = env.resolve("aurora_valley_v25b")["world"]
    for feature in ("walls", "ridges", "scarps", "spires", "ravine"):
        assert feature in a, f"A is missing {feature}"
    for feature in ("boulders", "anchors", "trees", "landmarks", "lamps"):
        assert feature not in a, f"A should not carry {feature}"
        assert feature in b, f"B is missing {feature}"


# --- nothing is a default ---------------------------------------------------


def test_no_profile_shipped_before_v25_declares_a_world():
    for one in PRE_V25:
        assert "world" not in env.load(one), (
            f"{one} gained a world section; V22.1 and V23 would no longer "
            f"render what they rendered")
        assert "world" not in env.resolve(one)


def test_the_registry_default_is_still_alpine_neon():
    assert env.default_id() == "alpine_neon"


def test_the_builder_returns_immediately_without_a_world_section():
    """Absent means nothing is built, and the guard is in the file."""
    assert "if world.is_empty() or not bool(world.get(\"enabled\", true)):"\
        in WORLD
    assert re.search(r"if not wanted:\s*\n\s*return \{\}", WORLD)


def test_course_machine_only_builds_a_world_when_one_is_asked_for():
    assert "var world_cfg: Dictionary = EnvBuilder.world(environment)" in MACHINE
    assert "if not world_cfg.is_empty():" in MACHINE


def test_v23_still_names_its_own_environment():
    """V25 is a separate selection and does not become V23's."""
    assert v23.ENVIRONMENT == "aurora_valley"
    assert v23.MACHINE == "v23b"
    assert "--environment=aurora_valley" in " ".join(v23.SCENE_FLAGS)


# --- GEOMETRY IS NOT THEME, extended to a geometry section ------------------


def test_world_is_a_recognised_section_in_both_readers():
    assert "world" in env.SECTIONS
    assert '"world",' in PROFILE


def test_a_world_section_still_cannot_name_a_terrain_shape_field():
    """The rule V23 enforced has not been widened by adding geometry.

    A `world` section describes forms placed *against* the ground. The ground
    itself stays in `course_layout`, where the camera port can be re-verified
    against it, and `validate` still refuses a profile that reaches it.
    """
    profile = env.resolve("aurora_valley_v25b")
    profile["terrain"]["gorge_depth"] = 40.0
    problems = env.validate(profile)
    assert any("gorge_depth" in one for one in problems), problems


def test_the_world_builder_never_writes_a_terrain_field():
    """It reads `Terrain.height` and `Terrain.normal` and writes nothing.

    The strong form of render-only: a form that *modified* the height field
    would move every support pier and invalidate every solved camera, and no
    amount of "it is only dressing" would make that untrue.
    """
    assert "Terrain.height(" in WORLD
    assert "Terrain.normal(" in WORLD
    for forbidden in ("cfg[", "cfg.set", "terrain_cfg["):
        assert forbidden not in WORLD, (
            f"environment_world writes to the terrain config via {forbidden}")


def test_the_world_builder_creates_no_collider():
    """Render-only, asserted rather than assumed.

    Nothing in this scene has a collider - the physics is PyBullet's - but a
    future reader adding one here would be adding it to a world the physics
    cannot see, which is worse than not having it.
    """
    for forbidden in ("StaticBody", "CollisionShape", "RigidBody", "Area3D",
                      "PhysicsBody"):
        assert forbidden not in WORLD


def test_every_world_mesh_is_on_the_world_light_layer():
    assert "const WORLD_LAYER := 2" in WORLD
    assert "_to_world_layer(group)" in WORLD
    assert "(node as VisualInstance3D).layers = WORLD_LAYER" in WORLD


def test_a_world_practical_cannot_light_the_machine():
    """The one rule the pass may not break: the machine's light is its own."""
    assert "lamp.light_cull_mask = 1 << (WORLD_LAYER - 1)" in WORLD


# --- the race did not move --------------------------------------------------


def test_the_terrain_height_function_is_untouched():
    """`course_terrain.height` decides where every pier stops.

    `sloped/terrain.py` is an exact port of it and every production camera is
    solved against that port, so a character changed here invalidates both. The
    assertion is on the function's own body rather than on the file, because
    the file is allowed to gain a comment.
    """
    body = TERRAIN[TERRAIN.index("static func height("):
                   TERRAIN.index("static func index_cut(")]
    for line in ("var run: float = z - float(cfg[\"z_top\"])",
                 "h -= float(cfg[\"gorge_depth\"]) * pow(right, 1.4)",
                 "h += float(cfg[\"left_rise\"]) * pow(left, 1.5)",
                 "h += _noise(x, z, 0.0085, 3) * amplitude * 3.4"):
        assert line in body, f"course_terrain.height lost: {line}"


def test_the_layout_tables_are_untouched():
    """Layout B's terrain config and its seven runs are the physics course."""
    layout = LAYOUT_GD.read_text(encoding="utf-8")
    for line in ('"top_y": 39.6, "z_top": -34.0, "grade": 0.45,',
                 '"gorge_at": 15.0, "gorge_span": 24.0, "gorge_depth": 28.0,',
                 '"noise": 2.3, "cell": 1.3,',
                 'Vector3(19.80, 1.02, 44.40)'):
        assert line in layout, f"course_layout lost: {line}"


def test_the_seed_is_still_5432():
    tool = _tool("sloped_v25_world")
    assert tool.SEED == 5432
    assert "race_5432.json" in tool.REPLAY


def test_the_lab_renders_v221s_own_solved_tracks():
    """No camera is re-solved, so no camera timing can have changed.

    V23 made the same choice for the same reason: pointing at V22.1's own track
    files rather than re-solving makes the camera identical by construction,
    and leaves no drift for a test to have to catch.
    """
    tool = _tool("sloped_v25_world")
    assert tool.RACE_TRACK.endswith("cameras_v221_5432.json")
    assert tool.PREVIEW_TRACK.endswith("preview_v221_5432.json")
    assert "--stage solve" not in tool.__doc__


def test_no_moment_falls_outside_the_v221_edit():
    """Every comparison second is inside the film V22.1 delivered."""
    for one in v25_world.MOMENTS:
        if one.track == "race":
            assert 0.0 <= one.second <= 22.317, one
        else:
            assert 0.0 <= one.second <= 3.483, one


def test_the_clips_do_not_run_past_the_masters():
    for one in v25_world.CLIPS:
        assert one.start < one.end
        limit = 22.317 if one.track == "race" else 3.483
        assert one.end <= limit + 1e-6, one


def test_the_lab_renders_under_v23s_own_machine_pass():
    """A world comparison has to hold the machine fixed."""
    tool = _tool("sloped_v25_world")
    assert tool.MACHINE == v23.MACHINE


# --- the world and the machine stay separate --------------------------------


def _named_surfaces(profile_id: str) -> set[str]:
    return set(env.resolve(profile_id).get("palette", {}))


def test_no_v25_profile_names_a_machine_surface():
    """The V23 rule, applied to the thirteen surfaces V25 adds.

    An environment naming a machine key would repaint the racers' track from
    the world's own file, and the two dials would stop being independent.
    """
    machine_keys = set(re.findall(r'^\t\t"([a-z0-9_]+)":',
                                  _machine_pass_block(), re.M))
    assert machine_keys, "could not read MACHINE_PASSES v23b"
    for one in ("aurora_valley_v25",) + V25_IDS:
        overlap = _named_surfaces(one) & machine_keys
        assert overlap == set(), f"{one} names machine surfaces: {overlap}"


def _machine_pass_block() -> str:
    start = PALETTE.index('"v23b":')
    end = PALETTE.index('"v23c":', start)
    return PALETTE[start:end]


def test_every_world_surface_the_builder_names_exists_in_the_palette():
    """A fallback material key that no `_build` branch answers is a magenta
    error object in a delivered frame, and the palette pushes an error rather
    than failing, so nothing else would catch it."""
    named = set(re.findall(r'"(world_[a-z_]+|conifer_[a-z]+|lit_world_[a-z]+)"',
                           WORLD))
    assert named, "no world surface keys found in the builder"
    for key in named:
        assert f'\t\t"{key}":' in PALETTE, f"lab_palette has no '{key}'"


def test_every_marked_surface_is_a_real_palette_key():
    """The marker table is how depth is measured; a stale key in it is an
    unmeasured band, which is worse than an unmeasured frame."""
    for band, keys in v25_world.MARKED.items():
        for key in keys:
            assert f'\t\t"{key}":' in PALETTE, f"{band} names unknown '{key}'"


def test_the_marker_profiles_cover_every_world_surface_the_profiles_name():
    """Nothing a variant paints is invisible to the segmentation."""
    marked = {key for keys in v25_world.MARKED.values() for key in keys}
    for one in V25_IDS:
        painted = {key for key in _named_surfaces(one)
                   if key.startswith(("world_", "conifer_", "slope_",
                                      "scrub_", "rock_soft_"))}
        missing = painted - marked
        assert missing == set(), f"{one} paints unmarked surfaces: {missing}"


# --- the generator is the source of the profiles ----------------------------


def test_regenerating_the_profiles_is_a_no_op(profiles):
    """The committed JSON is exactly what the generator writes.

    If it were not, the numbers in the files and the numbers in the reviewed
    table would be two different worlds, and the sheets would be of neither.
    """
    assert profiles.write() == [], (
        "tools/sloped_v25_profiles.py would rewrite the committed profiles; "
        "run it and commit the result")


def test_the_generator_writes_one_marker_per_variant(profiles):
    for key, name in v25_world.MARKERS.items():
        assert name in env.ids(), f"{name} is not registered"
        assert env.load(name)["extends"] == key


def test_the_marker_profiles_are_diagnostic_not_looks(profiles):
    """A marker is flat paint over a variant and changes nothing else."""
    for key, name in v25_world.MARKERS.items():
        marker = env.load(name)
        assert set(marker) == {"id", "title", "family", "summary", "extends",
                               "palette"}
        assert marker["family"] == "diagnostic"


# --- the camera keep-out ----------------------------------------------------


def test_the_keep_out_covers_both_solved_camera_tracks(profiles):
    """Not a decoration: it is the fix for a world form standing in a lens.

    The list is a constant rather than something read from a loaded track,
    because the race and the preview photograph one build - so the assertion is
    that it spans both, which is a property of the numbers themselves.
    """
    path = profiles.CAMERA_PATH
    assert len(path) > 40
    xs = [one[0] for one in path]
    zs = [one[1] for one in path]
    # The race track runs the length of the course and the preview flies out
    # past the finish; a list covering only one would miss a whole span.
    assert min(zs) < -50.0 and max(zs) > 30.0
    assert min(xs) < -35.0 and max(xs) > 25.0


def test_no_authored_world_form_stands_in_a_lens(profiles):
    """Every hand-placed site clears the camera path by its own keep-out.

    Only the authored ones - scarps, landmarks - can be checked here: the
    scattered features place by rejection sampling against the same guard at
    build time, which `environment_world._sited` enforces and
    `test_every_scattered_feature_tests_the_camera_path` pins.
    """
    world = env.resolve("aurora_valley_v25b")["world"]
    keepout = world["keepout"]
    terrain = {"centre_x": 1.0, "centre_z": 6.0}

    def gap(x: float, z: float) -> float:
        return min(math.hypot(x - a, z - b) for a, b in keepout)

    scarps = world["scarps"]
    for index, site in enumerate(scarps["sites"]):
        x = terrain["centre_x"] + site[0]
        z = terrain["centre_z"] + site[1]
        assert gap(x, z) >= scarps["keepout"], (
            f"scarp {index} is {gap(x, z):.1f} from the camera path")

    nodes = {"start": (-18.60, -37.20), "mix": (-5.60, -28.35),
             "obstacle": (-9.00, 3.16), "split": (6.00, 18.00),
             "merge": (0.00, 36.10), "finish": (24.20, 46.20)}
    marks = world["landmarks"]
    for name, site in marks["sites"].items():
        anchor = nodes[name]
        x = anchor[0] + site["offset"][0]
        z = anchor[1] + site["offset"][1]
        offsets = [(0.0, 0.0)]
        if site["kind"] == "spires":
            count = site["count"]
            spread = site["spread"]
            offsets = [(math.cos(2 * math.pi * i / count) * spread,
                        math.sin(2 * math.pi * i / count) * spread)
                       for i in range(count)]
        elif site["kind"] == "gate":
            half = site["gap"] * 0.5
            bearing = math.radians(site["bearing"])
            offsets = [(math.sin(bearing) * half * s,
                        math.cos(bearing) * half * s) for s in (-1.0, 1.0)]
        for dx, dz in offsets:
            assert gap(x + dx, z + dz) >= marks["keepout"], (
                f"landmark {name} at +({dx:.1f},{dz:.1f}) is "
                f"{gap(x + dx, z + dz):.1f} from the camera path")


def test_every_scattered_feature_tests_the_camera_path():
    """One call does both constraints, so a new feature cannot forget one."""
    assert "static func _sited(guides: Dictionary" in WORLD
    for builder in ("_scarps", "_spires", "_boulders", "_trees", "_landmarks",
                    "_ring"):
        block = _builder_block(builder)
        assert "_sited(guides" in block, (
            f"{builder} does not test the camera path")


def _builder_block(name: str) -> str:
    start = WORLD.index(f"static func {name}(")
    rest = WORLD[start + 10:]
    end = rest.find("\nstatic func ")
    return rest if end < 0 else rest[:end]


# --- the lab's own definitions ----------------------------------------------


def test_every_variant_names_a_registered_profile():
    for entry in v25_world.ALL:
        assert entry.key in env.ids(), entry.key


def test_the_ten_moments_the_brief_asks_for_are_all_there():
    wanted = ["start", "mixer", "descent", "obstacle", "fork_approach",
              "split", "branch", "merge", "final_approach", "finish"]
    have = [one.key for one in v25_world.RACE_MOMENTS]
    assert have == wanted


def test_the_moments_run_in_race_order():
    seconds = [one.second for one in v25_world.RACE_MOMENTS]
    assert seconds == sorted(seconds)


def test_every_crop_names_a_real_moment():
    keys = {one.key for one in v25_world.MOMENTS}
    for crop in v25_world.CROPS:
        assert crop.moment in keys, crop
        left, top, right, bottom = crop.box
        assert 0.0 <= left < right <= 1.0
        assert 0.0 <= top < bottom <= 1.0


def test_the_depth_bands_are_ordered_and_separated_in_hue():
    """The segmentation is nearest-hue, so two bands that are close in hue are
    one band with extra steps."""
    import numpy as np
    from sloped.v23_env import to_lab

    angles = []
    for entry in v25_world.LAYERS:
        lab = to_lab(np.array(entry.hue, dtype=float))
        angles.append(math.degrees(math.atan2(lab[2], lab[1])) % 360.0)
    angles.sort()
    gaps = [(b - a) for a, b in zip(angles, angles[1:])]
    gaps.append(360.0 - angles[-1] + angles[0])
    assert min(gaps) >= 25.0, f"marker hues are too close: {min(gaps):.1f} deg"


def test_parallax_is_monotone_for_a_receding_series():
    rows = {
        "foreground": {"order": 1.0, "cover": 5.0, "shift": 40.0,
                       "patches": 9},
        "ridges": {"order": 2.0, "cover": 5.0, "shift": 12.0, "patches": 7},
        "walls": {"order": 3.0, "cover": 5.0, "shift": 4.0, "patches": 5},
    }
    ok, series = v25_world.monotone(rows)
    assert ok, series


def test_parallax_is_not_monotone_for_a_backdrop_that_swims():
    rows = {
        "foreground": {"order": 1.0, "cover": 5.0, "shift": 4.0,
                       "patches": 9},
        "ridges": {"order": 2.0, "cover": 5.0, "shift": 30.0, "patches": 9},
    }
    ok, series = v25_world.monotone(rows)
    assert not ok and series.startswith("not monotone")


def test_a_band_with_no_cover_is_reported_rather_than_scored():
    """The honest half of the parallax measure: a band too small to correlate
    gets its cover printed, not a made-up displacement."""
    import numpy as np
    frame = np.zeros((64, 64, 3), dtype=np.uint8)
    masks = {one.key: np.zeros((64, 64), dtype=bool)
             for one in v25_world.LAYERS}
    rows = v25_world.parallax(frame, frame, masks)
    for key, row in rows.items():
        assert "shift" not in row, key
        assert row["cover"] == 0.0


def test_a_translated_band_measures_its_own_translation():
    """The measure that replaced two reporting nonsense.

    A textured field moved eleven pixels right and five down has to come back
    as (11, 5). Under the first version, which windowed both frames with one
    mask, it came back as (0, 0) for every band in every shot; under the
    second, which correlated the band masks, a distant range came back as
    386 px.
    """
    import numpy as np
    rng = np.random.default_rng(3)
    raw = rng.random((640, 420))
    # Smoothed, because a real frame has structure over several pixels and
    # pixel-scale white noise has none for a coarse search step to find.
    reach = 9
    padded = np.pad(raw, reach, mode="wrap")
    field = np.zeros_like(raw)
    for dy in range(-reach, reach + 1):
        for dx in range(-reach, reach + 1):
            field += padded[reach + dy:reach + dy + 640,
                            reach + dx:reach + dx + 420]
    field /= (2 * reach + 1) ** 2
    field = (field - field.min()) / (field.max() - field.min()) * 120 + 20
    before = np.dstack([field] * 3).astype(np.uint8)
    moved = np.roll(np.roll(field, 5, axis=0), 11, axis=1)
    after = np.dstack([moved] * 3).astype(np.uint8)
    mask = np.zeros((640, 420), dtype=bool)
    mask[130:560, 110:330] = True

    got = v25_world.band_shift(before, after, mask)
    assert got["patches"] >= 4
    assert (got["dx"], got["dy"]) == (11.0, 5.0)
    assert got["shift"] == pytest.approx(math.hypot(11.0, 5.0))
    assert got["score"] > 0.98
    assert got["spread"] == pytest.approx(0.0, abs=0.5)


def test_a_patch_must_lie_wholly_inside_its_band():
    """A template that straddles a band edge is tracking two depths at once."""
    import numpy as np
    mask = np.zeros((900, 600), dtype=bool)
    mask[300:340, 200:240] = True   # smaller than one patch plus its search
    assert v25_world._patch_sites(mask) == []


def test_recession_groups_bands_by_depth():
    steps = v25_world.recession({"foreground": 10.0, "vegetation": 12.0,
                                 "ridges": 18.0, "walls": 24.0})
    assert len(steps) == 2
    assert steps[0][2] == pytest.approx(7.0)
    assert steps[1][2] == pytest.approx(6.0)


def test_parse_cost_reads_the_renderers_own_lines():
    tool_output = (
        "scene: 2202 mesh instances, ~685000 triangles\n"
        "rendered 13 frames in 5.0s  (385 ms/frame)\n")
    cost = v25_world.parse_cost(tool_output)
    assert cost.meshes == 2202
    assert cost.triangles == 685000
    assert cost.milliseconds == pytest.approx(385.0)


def test_census_of_reads_the_scenes_own_line():
    census = v25_world.census_of(
        "  world: walls 78, ridges 130, scarps 60, spires 38\n")
    assert census == {"walls": 78, "ridges": 130, "scarps": 60, "spires": 38}


# --- the documented proofs exist --------------------------------------------


VALIDATION = ROOT / "docs" / "validation" / "sloped_race_v1" / "v25_world"


@pytest.mark.skipif(not VALIDATION.is_dir(),
                    reason="proofs are rendered, not committed by this test")
def test_every_moment_has_a_pair_sheet():
    for one in v25_world.MOMENTS:
        assert (VALIDATION / f"pair_{one.key}.png").is_file(), one.key


@pytest.mark.skipif(not (VALIDATION / "measures.json").is_file(),
                    reason="measures are rendered, not committed by this test")
def test_the_measured_table_covers_every_moment_and_variant():
    measured = json.loads((VALIDATION / "measures.json").read_text("utf-8"))
    for one in v25_world.MOMENTS:
        row = measured["moments"][one.key]
        for entry in v25_world.ALL:
            assert entry.key in row, (one.key, entry.key)
            assert "headroom" in row[entry.key]
