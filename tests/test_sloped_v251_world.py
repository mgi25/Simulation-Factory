"""V25.1 world art: a pass that may change how the world looks and nothing else.

V25.1 rebuilds the world's *forms* - a faceted rock kit instead of a noise
dome, a tiered vegetation kit instead of a cone, cut benches instead of
scattered blocks, stylised material zones over the heightfield, and five
landmarks sited against the frames rather than against the layout. It adds no
density, moves no terrain, and touches no physics, camera or edit.

So this file asserts five kinds of thing, in the shape V25's own suite
established:

* **Nothing reached the race.** The seed, the replay, the layout tables, the
  terrain height function, the camera solve and the edit are untouched, and the
  test reads the files rather than trusting a claim about them.
* **Nothing reached the landform.** The two new modules build meshes and
  nothing else: no collider, no terrain field, no `PhysicsBody`. The material
  zones follow `Terrain.height` and never write it.
* **V25 still renders V25.** Every profile shipped before this pass - including
  all four V25 variants and their markers - is still registered, still
  resolves, and still names no V25.1 feature. Every new builder behaviour is
  opt-in behind a field no older profile sets.
* **The kit is a kit.** Both generators are deterministic, both are driven from
  a named table, and every surface the profile paints exists in the palette and
  is in the marker table.
* **The instruments are sound.** The siting tool's output-to-replay map is the
  render scene's own, its projector puts each race node in the middle of the
  frame named for it, and every authored site lands in at least one frame.

What is *not* asserted here is that the art is good. The brief is explicit that
the decisive test is rendered motion, and no number in this file is offered as
evidence of quality.
"""

from __future__ import annotations

import importlib.util
import json
import math
import re
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import terrain, v25_world, v251_world

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
ASSETS = GODOT / "assets" / "marble_machine"
PROFILES = ASSETS / "environment" / "profiles"

WORLD_GD = ASSETS / "environment" / "environment_world.gd"
ROCK_GD = ASSETS / "environment" / "world_rock.gd"
FLORA_GD = ASSETS / "environment" / "world_flora.gd"
BUILDER_GD = ASSETS / "environment" / "environment_builder.gd"
MACHINE_GD = ASSETS / "course" / "course_machine.gd"
TERRAIN_GD = ASSETS / "course" / "course_terrain.gd"
LAYOUT_GD = ASSETS / "course" / "course_layout.gd"
PALETTE_GD = ASSETS / "lab_palette.gd"

WORLD = WORLD_GD.read_text(encoding="utf-8")
ROCK = ROCK_GD.read_text(encoding="utf-8")
FLORA = FLORA_GD.read_text(encoding="utf-8")
MACHINE = MACHINE_GD.read_text(encoding="utf-8")
TERRAIN_SRC = TERRAIN_GD.read_text(encoding="utf-8")
PALETTE = PALETTE_GD.read_text(encoding="utf-8")

#: Every profile that existed before this pass and must keep rendering what it
#: did - the four shipped looks, V23's, and all four of V25's with the markers.
PRE_V251 = ("alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
            "aurora_valley", "aurora_valley_v25", "aurora_valley_v25a",
            "aurora_valley_v25b", "aurora_valley_v25c")

#: Fields a profile sets to turn a V25 builder into a V25.1 one. No profile
#: shipped before this pass may set any of them, which is what makes V25's own
#: renders reproducible from this branch.
OPT_IN = ("kit", "kits", "form", "shape", "crown", "node", "steps")


def _tool(name: str):
    """Load a tool by path; `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "_v251_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def profiles():
    return _tool("sloped_v251_profiles")


@pytest.fixture(scope="module")
def sites():
    return _tool("sloped_v251_sites")


@pytest.fixture(scope="module")
def v251():
    return json.loads((PROFILES / "aurora_valley_v251.json")
                      .read_text(encoding="utf-8"))


# --- nothing reached the race -----------------------------------------------


def test_the_seed_is_still_5432():
    tool = _tool("sloped_v251_world")
    assert "race_5432.json" in _tool("sloped_v25_world").REPLAY
    assert tool.LAB_DIR.endswith("v251_world")


def test_the_lab_renders_v221s_own_solved_tracks():
    """No camera is re-solved, so no camera timing can have changed."""
    base = _tool("sloped_v25_world")
    assert base.RACE_TRACK.endswith("cameras_v221_5432.json")
    assert base.PREVIEW_TRACK.endswith("preview_v221_5432.json")
    assert "--stage solve" not in _tool("sloped_v251_world").__doc__


def test_the_moments_and_clips_are_v25s_own():
    """The control has to be compared at the frames it was measured at.

    Re-deriving the comparison seconds would make a V25 B still from this
    branch a different still from the one in V25's own sheet, and the whole
    pass is a before-and-after.
    """
    assert v251_world.MOMENTS is v25_world.MOMENTS
    assert v251_world.CLIPS is v25_world.CLIPS
    assert v251_world.LAYERS is v25_world.LAYERS


def test_the_terrain_height_function_is_untouched():
    """`course_terrain.height` decides where every pier stops."""
    body = TERRAIN_SRC[TERRAIN_SRC.index("static func height("):
                       TERRAIN_SRC.index("static func index_cut(")]
    for line in ('var run: float = z - float(cfg["z_top"])',
                 'h -= float(cfg["gorge_depth"]) * pow(right, 1.4)',
                 'h += float(cfg["left_rise"]) * pow(left, 1.5)',
                 "h += _noise(x, z, 0.0085, 3) * amplitude * 3.4"):
        assert line in body, f"course_terrain.height lost: {line}"


def test_the_layout_tables_are_untouched():
    layout = LAYOUT_GD.read_text(encoding="utf-8")
    for line in ('"top_y": 39.6, "z_top": -34.0, "grade": 0.45,',
                 '"gorge_at": 15.0, "gorge_span": 24.0, "gorge_depth": 28.0,',
                 '"noise": 2.3, "cell": 1.3,',
                 "Vector3(19.80, 1.02, 44.40)"):
        assert line in layout, f"course_layout lost: {line}"


def test_every_comparison_second_is_inside_the_v221_edit():
    """A moment outside the edit is a frame the film does not have."""
    for moment in v251_world.MOMENTS:
        assert moment.second >= 0.0
        if moment.track == "race":
            assert moment.second <= 22.317
        else:
            assert moment.second <= 3.483


# --- nothing reached the landform -------------------------------------------


def test_neither_new_module_creates_a_collider():
    """Render-only, and asserted on the source rather than claimed.

    A `StaticBody3D` or a `CollisionShape3D` anywhere in the world kit would be
    a landform change wearing a dressing costume - `sloped/terrain.py` is the
    only authority on where the ground is, and PyBullet is the only authority
    on the physics.
    """
    for name, source in (("world_rock.gd", ROCK), ("world_flora.gd", FLORA),
                         ("environment_world.gd", WORLD)):
        for banned in ("StaticBody", "CollisionShape", "PhysicsBody",
                       "RigidBody", "Area3D", "create_trimesh",
                       "create_convex"):
            assert banned not in source, f"{name} names {banned}"


def test_the_material_zones_read_the_terrain_and_never_write_it():
    """A patch follows `Terrain.height` and adds no surface of its own."""
    body = WORLD[WORLD.index("static func _patches("):
                 WORLD.index("# --- A: the valley walls")]
    assert "Terrain.height(" in body
    for banned in ("cfg[", "terrain_cfg", "_material_of", "index_cut"):
        assert banned not in body, f"_patches writes terrain state: {banned}"


def test_the_world_builder_never_writes_a_terrain_field(v251):
    """A profile may not reshape the ground, and V25.1 does not try."""
    shape_fields = ("top_y", "grade", "gorge_depth", "gorge_span", "noise",
                    "cell", "amplitude", "left_rise", "edge_from", "edge_to")
    text = json.dumps(v251)
    for field in shape_fields:
        assert f'"{field}"' not in text, f"V25.1 names terrain field {field}"


def test_every_world_mesh_is_on_the_world_light_layer():
    assert "const WORLD_LAYER := 2" in WORLD
    assert "_to_world_layer(group)" in WORLD


def test_a_world_practical_cannot_light_the_machine():
    assert "lamp.light_cull_mask = 1 << (WORLD_LAYER - 1)" in WORLD


def test_the_warm_world_light_is_world_only(v251):
    """`WorldWarm` is the one new light, and it may not reach the machine.

    The machine's light is the machine's: V21 tuned `Key` and `Rim` against the
    pearl shell, and a world fill that also lifted the product would be
    spending the hero's own headroom on scenery.
    """
    warm = v251["lights"]["WorldWarm"]
    assert warm["cull_mask"] == 2
    assert warm["shadow"]["enabled"] is False
    assert warm["energy"] < v251["lights"]["WorldKey"]["energy"]


# --- V25 still renders V25 --------------------------------------------------


def test_every_profile_shipped_before_v251_is_still_registered():
    listed = env.ids()
    for one in PRE_V251:
        assert one in listed, f"{one} fell out of the registry"
        assert (PROFILES / f"{one}.json").is_file()


def test_every_profile_still_resolves_and_validates():
    for one in tuple(PRE_V251) + ("aurora_valley_v251",):
        resolved = env.resolve(one, contrast="v21")
        assert env.validate(resolved) == [], f"{one} no longer validates"


def test_no_profile_shipped_before_v251_sets_a_v251_field():
    """Every V25.1 builder behaviour is opt-in, which is what keeps V25's own
    renders reproducible from this branch."""
    for one in PRE_V251:
        text = (PROFILES / f"{one}.json").read_text(encoding="utf-8")
        body = json.loads(text)
        world = json.dumps(body.get("world", {}))
        for field in OPT_IN:
            assert f'"{field}"' not in world, \
                f"{one} sets the V25.1 field {field}"


def test_the_rock_dispatcher_falls_back_to_smooth_mass():
    """A spec with no `kit` builds exactly what V25 built."""
    body = WORLD[WORLD.index("static func _rock("):
                 WORLD.index("static func _bands(")]
    assert 'var kit := str(spec.get("kit", ""))' in body
    assert "return _mass(height, base, salt, facets, tiers, taper)" in body


def test_the_bench_is_opt_in():
    assert 'if str(spec.get("form", "")) == "bench":' in WORLD


def test_the_registry_default_is_still_alpine_neon():
    assert env.default_id() == "alpine_neon"


# --- the kit is a kit -------------------------------------------------------


def test_the_rock_kit_has_the_eight_named_forms():
    """The brief asks for a small reusable kit rather than unique crude
    objects; eight entries is the whole of it."""
    listed = re.findall(r'^\t"([a-z]+)": \{', ROCK, re.MULTILINE)
    assert set(listed) == {"cliff", "block", "ledge", "needle", "slab",
                           "boulder", "wall", "mountain"}


def test_the_flora_kit_has_the_five_named_plants():
    listed = re.findall(r'^\t"([a-z]+)": \{', FLORA, re.MULTILINE)
    assert set(listed) == {"conifer", "spruce", "hero", "shrub", "tuft"}


def test_a_cluster_is_composed_rather_than_filled():
    """One hero per cluster, then a mix - which is the placement half of the
    vegetation fix and is worth nothing without the kit half."""
    assert "const CLUSTER := [" in FLORA
    assert FLORA[FLORA.index("const CLUSTER := ["):].startswith(
        'const CLUSTER := ["hero"')


def test_both_generators_are_deterministic():
    """No RNG object and no clock anywhere in either kit: two renders of one
    world have to be identical, and the whole environment system is built on
    a lattice hash for exactly that reason."""
    for name, source in (("world_rock.gd", ROCK), ("world_flora.gd", FLORA)):
        for banned in ("RandomNumberGenerator", "randf", "randi", "randomize",
                       "Time.get_ticks"):
            assert banned not in source, f"{name} uses {banned}"
        assert "static func _h(seed_value: int, salt: int) -> float:" in source


def test_every_rock_form_is_flat_shaded():
    """Flat faces are the whole argument of the kit: a form built with
    `quad_smooth_auto` would be a dome with more triangles in it."""
    assert "Geometry.quad_auto(" in ROCK
    assert "quad_smooth_auto" not in ROCK


def test_a_ledge_is_a_partial_arc(v251):
    """A step that goes all the way round a form is a cake tier.

    This is the correction the kit's probe sheet forced, and it is a property
    of the generator rather than of a number, so it is asserted on the source.
    """
    body = ROCK[ROCK.index("static func _profile("):]
    assert '"start": int(_h(seed_value, 61 + which * 3)' in body
    assert "for offset in int(mark[\"span\"]):" in body


# --- the profile is complete and consistent ---------------------------------


def test_the_generator_regenerating_the_committed_json_is_a_no_op(profiles):
    assert profiles.write(check=True) == []


def test_every_surface_the_profile_paints_exists_in_the_palette(v251):
    named = set()
    world = v251["world"]
    for feature in world.values():
        if not isinstance(feature, dict):
            continue
        for key in ("materials", "shrubs", "kits"):
            for one in feature.get(key, []):
                if isinstance(one, str) and one.startswith("world_") \
                        or isinstance(one, str) and one.startswith("conifer"):
                    named.add(one)
        for key in ("material", "bank_material", "deck", "kerb", "stone"):
            if isinstance(feature.get(key), str):
                named.add(feature[key])
        for site in feature.get("sites", []) or []:
            if isinstance(site, list) and len(site) > 3 \
                    and isinstance(site[3], str) and site[3].startswith("world"):
                named.add(site[3])
        if isinstance(feature.get("sites"), dict):
            for site in feature["sites"].values():
                if isinstance(site.get("material"), str):
                    named.add(site["material"])
    assert named, "no surfaces were found - the walk is wrong"
    for key in sorted(named):
        assert f'"{key}":' in PALETTE, f"palette has no surface {key}"


def test_every_new_surface_is_in_the_marker_table():
    """A world surface nobody marks shows up in a sheet as a hole rather than
    as somebody else's band, which is how V25 found two segmentation bugs."""
    marked = {one for keys in v251_world.MARKED.values() for one in keys}
    for key in ("world_concrete", "world_gravel", "world_bench", "world_ember",
                "world_damp", "world_warm_rock", "lit_world_amber"):
        assert key in marked, f"{key} is painted but never marked"


def test_the_marker_profile_is_written_from_the_marker_table(profiles):
    marker = json.loads((PROFILES / "_marker_v251.json")
                        .read_text(encoding="utf-8"))
    marked = {one for keys in v251_world.MARKED.values() for one in keys}
    assert set(marker["palette"]) == marked
    for spec in marker["palette"].values():
        assert spec["unshaded"] is True and spec["no_fog"] is True


def test_v251_is_a_sibling_of_the_variants_rather_than_a_delta_on_b(v251):
    """B is the control. A candidate that inherited from it would make every
    number B chose invisible unless V25.1 happened to override it."""
    assert v251["extends"] == "aurora_valley_v25"
    for feature in ("patches", "walls", "ridges", "scarps", "spires",
                    "boulders", "anchors", "trees", "landmarks", "ravine",
                    "lamps"):
        assert feature in v251["world"], f"V25.1 does not restate {feature}"


def test_the_profile_adds_no_density_over_b(profiles):
    """The brief locks B's density; this pass improves the art at or below it.

    Counted the way the census counts - the number of *forms* a feature is
    asked for, not the number of meshes they turn into.
    """
    base = _tool("sloped_v25_profiles")
    assert profiles.SPIRES["count"] <= base.SPIRES["count"]
    assert profiles.BOULDERS["count"] <= base.BOULDERS["count"]
    assert profiles.TREES["clusters"] <= base.TREES["clusters"]
    assert profiles.WALLS["count"] == base.WALLS["count"]
    assert profiles.ANCHORS["every"] >= base.ANCHORS["every"]


# --- the instruments are sound ----------------------------------------------


def test_the_siting_tool_uses_the_scenes_own_edit_map(sites):
    """An output second is not a replay second, and by the finish they are
    nearly two apart.

    The first version of the tool read the camera frame stamped with the same
    number as the moment, which at the descent is 2.15 s of a moving chase
    camera away from the frame the sheet shows. Two landmarks were authored
    against that before this check caught it.
    """
    race = json.loads((ROOT / "output" / "sloped_race_v1"
                       / "cameras_v221_5432.json").read_text(encoding="utf-8"))
    assert sites.replay_second(race, 0.0) == pytest.approx(0.2)
    assert sites.replay_second(race, 3.0) == pytest.approx(5.15)
    assert sites.replay_second(race, 21.4) > 21.4
    assert sites.replay_second({}, 7.0) == 7.0


def test_the_projector_puts_each_node_in_the_frame_named_for_it(sites):
    """The instrument check, run as a test.

    A tracking camera aimed at the pack should have the race node it is named
    for near the middle of frame at the moment it is named for. Three of them
    are within a tenth of the frame width of centre; `split` is the exception
    and it is the one cut where the pack has already passed its node.
    """
    from sloped import layout

    shots = {one.cut: one for one in sites.shots()}
    for node, moment, limit in (("start", "start", 0.1),
                                ("obstacle", "obstacle", 0.1),
                                ("merge", "merge", 0.1),
                                ("finish", "finish", 0.1)):
        point = layout.NODES[node]
        inside, u, _, _ = shots[moment].project(point)
        assert inside, f"{node} is out of the {moment} frame"
        assert abs(u) <= limit, f"{node} is at u={u:.2f} in {moment}"


def test_every_authored_site_lands_in_at_least_one_frame(profiles, sites):
    """The finding this pass is built on, asserted so it cannot come back.

    Three of V25's five landmarks stand where no camera on this course ever
    looks. A landmark nobody can see is not a weak landmark, it is cost.
    """
    cfg = terrain.terrain_config("b")
    shots = sites.shots()
    for name, site in profiles.LANDMARKS["sites"].items():
        anchor = profiles.NODES[site.get("node", name)]
        offset = site.get("offset", [0.0, 0.0])
        x = anchor[0] + offset[0]
        z = anchor[1] + offset[1]
        ground = terrain.height(x, z, cfg)
        height = float(site.get("height", 20.0))
        seen = [one.cut for one in shots
                if one.project((x, ground, z))[0]
                or one.project((x, ground + height, z))[0]]
        assert seen, f"landmark {name} is in no frame"
    for index, site in enumerate(profiles.PATCHES["sites"]):
        x = profiles.CENTRE[0] + site[0]
        z = profiles.CENTRE[1] + site[1]
        seen = [one.cut for one in shots
                if one.project((x, terrain.height(x, z, cfg), z))[0]]
        assert seen, f"patch {index} ({site[3]}) is in no frame"


def test_no_authored_site_is_inside_a_lens_or_the_racing_line(profiles):
    """The builder rejects such a site and warns; a test is what stops the
    warning being the only record of it."""
    base = _tool("sloped_v25_profiles")
    lens = [(one[0], one[1]) for one in base.CAMERA_PATH]
    keep_out = float(profiles.LANDMARKS["keepout"])
    for name, site in profiles.LANDMARKS["sites"].items():
        anchor = profiles.NODES[site.get("node", name)]
        offset = site.get("offset", [0.0, 0.0])
        x = anchor[0] + offset[0]
        z = anchor[1] + offset[1]
        reach = float(site.get("gap", 0.0)) * 0.5 \
            + float(site.get("radius", 0.0))
        gap = min(math.dist((x, z), one) for one in lens)
        assert gap + reach >= keep_out, \
            f"landmark {name} centre is {gap:.1f} from a lens"


def test_the_analytic_parallax_finds_a_spread_in_every_chase(sites):
    """Part N: the parallax V25 solved must survive the art change.

    This is the shading-blind measure, and it exists because the image-space
    one loses bands on flat-shaded rock - see `--stage texture`. A chase cut
    has to show at least three bands moving at measurably different rates.
    """
    cfg = terrain.terrain_config("b")
    report = sites.geometric_parallax(cfg)
    for move in ("obstacle_pan", "fork_swing", "preview_dolly"):
        row = [one for one in report.splitlines() if one.startswith(move)]
        assert row, f"no row for {move}"
        found = re.findall(r"(\d+)px/(\d+)n", row[0])
        assert len(found) >= 3, f"{move} tracked fewer than three bands"
        rates = sorted(int(one[0]) for one in found)
        assert rates[-1] >= rates[0] * 1.4, \
            f"{move} has no spread: {rates}"


# --- the machine and the world stay independent -----------------------------


def test_no_v251_profile_names_a_machine_surface(v251):
    """V23's rule, extended to the seven surfaces this pass adds."""
    machine_keys = ("pearl_", "graphite", "brass", "marble_", "lit_zone",
                    "chrome", "acrylic")
    for key in v251.get("palette", {}):
        for prefix in machine_keys:
            assert not key.startswith(prefix), \
                f"V25.1 names the machine surface {key}"


def test_course_machine_only_builds_a_world_when_one_is_asked_for():
    assert "if not world.is_empty():" in MACHINE \
        or "world.is_empty()" in WORLD


def test_the_new_modules_are_not_reachable_from_the_machine():
    """`world_rock.gd` and `world_flora.gd` are the world's, and a machine
    script that preloaded one would make the two passes a single pass."""
    for path in sorted((ASSETS).rglob("*.gd")):
        if path.name in ("world_rock.gd", "world_flora.gd",
                         "environment_world.gd"):
            continue
        text = path.read_text(encoding="utf-8")
        for module in ("world_rock.gd", "world_flora.gd"):
            assert module not in text, f"{path.name} preloads {module}"
