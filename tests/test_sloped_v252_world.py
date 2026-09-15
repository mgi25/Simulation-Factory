"""V25.2 world lookdev: a pass that may change how the world *shades* and
nothing else.

V25.2 changes no count, no site, no radius, no bearing and no kit assignment
that V25.1 did not already choose. What it changes is the shading response -
crease-limited normal softening, a baked albedo gradient, a material shadow
floor - plus warmth in the brief's hierarchy, one silhouette event per hero
formation, three vegetation form options, and two compositions that were
re-solved against the cameras they are photographed by.

So this file asserts six kinds of thing, in the shape V25's and V25.1's own
suites established:

* **Nothing reached the race.** The seed, the replay, the layout tables, the
  terrain height function, the camera solve and the edit are untouched, and
  the test reads the files rather than trusting a claim about them.
* **Nothing reached the landform or the physics.** The changed modules build
  meshes and nothing else: no collider, no terrain field, no `PhysicsBody`.
* **V23, V25 and V25.1 still render what they rendered.** Every option this
  pass adds defaults to off, in the generator as well as in the profile, and
  no profile shipped before it names one. The rock and flora generators are
  asserted to produce byte-identical output when the new fields are absent.
* **The machine and the environment stay independent.** No world light can
  reach the machine, no world material is named by a machine pass, and the
  machine palette is untouched.
* **The pass is a delta.** `aurora_valley_v252` extends `aurora_valley_v251`
  and restates no layout: every count in it is lower than or equal to V25.1's.
* **The instruments are sound.** Every surface the profile paints exists in the
  palette and is in exactly one band of the marker table, and the three new
  measures behave correctly on an empty mask.

What is *not* asserted here is that the art is good. The brief is explicit that
the decisive test is rendered motion, and no number in this file is offered as
evidence of quality.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import numpy as np
import pytest

from sloped import v25_world, v251_world, v252_world

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
ASSETS = GODOT / "assets" / "marble_machine"
PROFILES = ASSETS / "environment" / "profiles"

WORLD_GD = ASSETS / "environment" / "environment_world.gd"
ROCK_GD = ASSETS / "environment" / "world_rock.gd"
FLORA_GD = ASSETS / "environment" / "world_flora.gd"
TERRAIN_GD = ASSETS / "course" / "course_terrain.gd"
LAYOUT_GD = ASSETS / "course" / "course_layout.gd"
PALETTE_GD = ASSETS / "lab_palette.gd"

WORLD = WORLD_GD.read_text(encoding="utf-8")
ROCK = ROCK_GD.read_text(encoding="utf-8")
FLORA = FLORA_GD.read_text(encoding="utf-8")
TERRAIN_SRC = TERRAIN_GD.read_text(encoding="utf-8")
PALETTE = PALETTE_GD.read_text(encoding="utf-8")

#: Every profile that existed before this pass and must keep rendering what it
#: did - the four shipped looks, V23's, all four of V25's, and V25.1's.
PRE_V252 = ("alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
            "aurora_valley", "aurora_valley_v25", "aurora_valley_v25a",
            "aurora_valley_v25b", "aurora_valley_v25c", "aurora_valley_v251")

#: The fields that turn a V25.1 builder or generator into a V25.2 one. No
#: profile shipped before this pass may name any of them, and every one of them
#: must default to a no-op - that pair is what makes V25 B and V25.1 still
#: reproduce from this branch.
SHAPE_OPT_IN = ("temper", "crease", "shade", "shade_crown", "shade_foot",
                "shade_warm", "shade_cool", "shade_bearing", "jag",
                "overhang", "overhang_step", "shoulder")
FLORA_OPT_IN = ("bough", "ragged", "aspect", "stem_width")
SPEC_OPT_IN = ("smooth", "roles")
PALETTE_OPT_IN = ("soft_light", "edge_light", "edge_tint",
                  "floor_lift", "floor_energy", "vertex_tint")


def _tool(name: str):
    """Load a tool by path; `tools/` is not a package."""
    spec = importlib.util.spec_from_file_location(
        "_v252_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def profiles():
    return _tool("sloped_v252_profiles")


@pytest.fixture(scope="module")
def v252():
    return json.loads((PROFILES / "aurora_valley_v252.json")
                      .read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def v251():
    return json.loads((PROFILES / "aurora_valley_v251.json")
                      .read_text(encoding="utf-8"))


# --- nothing reached the race -----------------------------------------------


def test_the_seed_is_still_5432():
    lab = _tool("sloped_v252_world")
    assert lab.lab.SEED == 5432


def test_the_lab_renders_v221s_own_solved_tracks():
    """A different camera track is a different film, not a different look."""
    lab = _tool("sloped_v252_world")
    assert lab.lab.RACE_TRACK.endswith("cameras_v221_5432.json")
    assert lab.lab.PREVIEW_TRACK.endswith("preview_v221_5432.json")
    assert lab.lab.REPLAY.endswith("race_5432.json")


def test_the_moments_and_clips_are_v25s_own():
    """The comparison is at V25's seconds or it is not a comparison."""
    assert v252_world.MOMENTS is v25_world.MOMENTS
    assert v252_world.CLIPS is v25_world.CLIPS
    assert v252_world.LAYERS is v25_world.LAYERS


def test_the_control_is_v251_itself():
    assert v252_world.CONTROL is v251_world.CANDIDATE
    assert v252_world.CONTROL.key == "aurora_valley_v251"
    assert v252_world.marker("aurora_valley_v251") == "_marker_v251"


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
    for moment in v252_world.MOMENTS:
        assert moment.second >= 0.0
        assert moment.second <= (22.317 if moment.track == "race" else 3.483)


def test_the_profile_names_nothing_the_physics_reads(v252):
    """A profile may repaint the mountain; it may not move it."""
    text = json.dumps(v252)
    for field in ("top_y", "z_top", "grade", "gorge_at", "gorge_depth",
                  "crest_rise", "cut_depth", "noise", "cell", "pads",
                  "seed", "replay", "cameras", "fps"):
        assert f'"{field}"' not in text, f"v252 profile names {field}"


# --- nothing reached the landform or the physics ----------------------------


def test_no_changed_module_creates_a_collider():
    for name, source in (("environment_world", WORLD), ("world_rock", ROCK),
                         ("world_flora", FLORA)):
        for banned in ("StaticBody3D", "CollisionShape3D", "RigidBody3D",
                       "ConcavePolygonShape3D", "HeightMapShape3D"):
            assert banned not in source, f"{name} creates a {banned}"


def test_the_material_zones_still_read_the_terrain_and_never_write_it():
    """`smooth` samples `Terrain.normal`; nothing here assigns a height."""
    body = WORLD[WORLD.index("static func _patches("):
                 WORLD.index("# --- A: the valley walls")]
    assert "Terrain.normal(" in body
    assert "Terrain.height(" in body
    assert not re.search(r"cfg\[[^\]]+\]\s*=", body), \
        "_patches writes into the terrain config"


def test_every_world_mesh_is_still_on_the_world_light_layer():
    assert "const WORLD_LAYER := 2" in WORLD
    assert "(node as VisualInstance3D).layers = WORLD_LAYER" in WORLD


def test_a_world_practical_still_cannot_light_the_machine():
    body = WORLD[WORLD.index("static func _lamps("):]
    assert "lamp.light_cull_mask = 1 << (WORLD_LAYER - 1)" in body


def test_every_light_the_profile_touches_is_world_only(v252, v251):
    """A light this pass re-energises may not be a machine light.

    Only the energy of lights V25.1 already declared on cull mask 2 moves
    here, so this checks the inherited declaration rather than trusting that
    an energy-only override is harmless.
    """
    for name in v252["lights"]:
        assert set(v252["lights"][name]) <= {"energy"}, \
            f"{name} changes more than its energy"
        declared = v251.get("lights", {}).get(name, {})
        if "cull_mask" in declared:
            assert declared["cull_mask"] == 2
        else:
            # Inherited from a V25 or V23 ancestor; those are asserted
            # world-only by the V23 and V25 suites. What must hold here is
            # that this pass did not introduce a *new* light.
            assert name in ("WorldKey", "WorldWarm", "WorldRim",
                            "WorldBounce"), f"{name} is a new light"


# --- V23, V25 and V25.1 still render what they rendered ---------------------


def test_every_profile_shipped_before_v252_is_still_registered():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    for name in PRE_V252:
        assert name in index["profiles"], f"{name} was dropped"
    assert index["default"] == "alpine_neon"


def test_no_profile_shipped_before_v252_names_a_v252_field():
    """Every option this pass adds is opt-in, and this is the proof."""
    for name in PRE_V252 + ("_marker_v25b", "_marker_v251"):
        path = PROFILES / f"{name}.json"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for field in SHAPE_OPT_IN + FLORA_OPT_IN + SPEC_OPT_IN \
                + PALETTE_OPT_IN:
            assert f'"{field}"' not in text, f"{name} names {field}"


def test_the_new_rock_options_all_default_to_a_no_op():
    """A `spec.get` with a falsy default is what makes V25.1 reproduce."""
    for field, default in (("temper", "0.0"), ("shade", "0.0"),
                           ("jag", "0.0"), ("overhang", "0"),
                           ("shoulder", "0")):
        assert re.search(
            r'spec\.get\("%s",\s*%s\)' % (field, re.escape(default)), ROCK), \
            f"world_rock.{field} does not default to {default}"


def test_the_untempered_rock_path_is_still_the_shared_helper():
    """Byte-identical means the same emitter, not an equivalent one."""
    assert "if temper <= 0.0 and shade <= 0.0:" in ROCK
    assert "Geometry.quad_auto(surface, a, b, c, d, flat)" in ROCK


def test_the_new_flora_options_all_default_to_a_no_op():
    for field, default in (("bough", "0.0"), ("ragged", "0.0"),
                           ("aspect", "0.0"), ("stem_width", "0.15")):
        assert re.search(
            r'spec\.get\("%s",\s*%s\)' % (field, re.escape(default)), FLORA), \
            f"world_flora.{field} does not default to {default}"
    assert "static func _tier(radius: float, height: float, facets: int,\n" \
           "\t\tseed_value: int, bough := 0.0, ragged := 0.0)" in FLORA


def test_the_smooth_material_zone_is_opt_in():
    assert 'bool(spec.get("smooth", false))' in WORLD
    assert "if not smooth or ring >= rings - 1:" in WORLD


def test_the_cluster_composition_falls_back_to_the_kit():
    body = WORLD[WORLD.index("static func _trees("):
                 WORLD.index("# --- H: the landmarks")]
    assert 'spec.get("roles", [])' in body
    assert "order = Flora.CLUSTER" in body


def test_the_four_new_palette_fields_are_new_names():
    """They enable a flag, so they may not collide with an existing row.

    `rim`, `backlight` and `emission` set a value on a feature the builder
    already turned on, and V21's retune and the machine passes both use them.
    Enabling the flag from those rows would change shipped pictures, which is
    why V25.2 added four differently named fields instead.
    """
    for field in ("soft_light", "edge_light", "floor_lift",
                  "vertex_tint"):
        assert f'spec.has("{field}")' in PALETTE
    v21 = PALETTE[PALETTE.index("const V21_RETUNE"):
                  PALETTE.index("const MACHINE_PASSES")]
    machine = PALETTE[PALETTE.index("const MACHINE_PASSES"):
                      PALETTE.index("func get_material(")]
    for field in ("soft_light", "edge_light", "floor_lift",
                  "vertex_tint"):
        assert f'"{field}"' not in v21
        assert f'"{field}"' not in machine


def test_the_rock_kit_is_still_the_eight_named_forms():
    """This pass adds options, not entries. Eight was a decision."""
    kinds = set(re.findall(r'^\t"(\w+)": \{', ROCK, re.M))
    assert kinds == {"cliff", "block", "ledge", "needle", "slab", "boulder",
                     "wall", "mountain"}


def test_the_flora_kit_gained_exactly_one_form():
    kinds = set(re.findall(r'^\t"(\w+)": \{', FLORA, re.M))
    assert kinds == {"conifer", "spruce", "hero", "shrub", "tuft", "snag"}


# --- the pass is a delta ----------------------------------------------------


def test_the_profile_extends_v251(v252):
    assert v252["extends"] == "aurora_valley_v251"
    assert v252["id"] == "aurora_valley_v252"


def test_no_world_count_rose(v252, v251):
    """Part I: this pass may remove objects and may not add any."""
    for key in ("spires", "boulders"):
        after = v252["world"].get(key, {}).get("count")
        if after is None:
            continue
        assert after <= v251["world"][key]["count"], f"{key} count rose"
    for key in ("scarps", "patches"):
        after = v252["world"].get(key, {}).get("sites")
        if after is None:
            continue
        assert len(after) <= len(v251["world"][key]["sites"]), \
            f"{key} site count rose"
    assert len(v252["world"]["lamps"]["sites"]) \
        == len(v251["world"]["lamps"]["sites"])


def test_the_landmark_sites_are_v251s_own(v252, v251):
    """A hero rock may be re-composed; a landmark may not be invented."""
    assert set(v252["world"]["landmarks"]["sites"]) \
        <= set(v251["world"]["landmarks"]["sites"])


def test_the_profile_restates_no_layout(v252, v251):
    """Every band, bearing and radius stays V25.1's unless Part F re-solved it.

    The finish arc is the one exception and it is a deliberate, documented one:
    V25.1's arc is outside the finish lens. Everything else that carries a
    position - the wall ring, the two ridge bands, the spire zone - must be
    inherited rather than restated, or the density lock is not a lock.
    """
    for key in ("walls", "spires", "boulders", "ravine"):
        section = v252["world"].get(key, {})
        for field in ("bearing_from", "bearing_step", "radius", "radius_step",
                      "zone", "at_x", "at_z"):
            assert field not in section, f"{key} restates {field}"
    for band in v252["world"]["ridges"]["bands"]:
        assert band["radius"] in (100.0, 188.0)


def test_the_moved_landmarks_are_the_two_the_brief_names(v252):
    """Only the obstacle wall and the finish basin may move."""
    moved = {name for name, site in v252["world"]["landmarks"]["sites"].items()
             if set(site) - {"shape"}}
    assert moved == {"east_wall", "finish", "finish_floor"}


# --- machine and environment stay independent -------------------------------


def test_no_machine_surface_is_in_the_world_profile(v252):
    machine_surfaces = ("pearl_lip", "pearl_track", "pearl_shell",
                        "pearl_shade", "silver", "track_silver",
                        "running_blue", "running_orange", "marble_blue")
    for key in machine_surfaces:
        assert key not in v252["palette"], f"v252 repaints the machine: {key}"


def test_the_pocket_surfaces_exist_in_the_palette():
    for key in ("world_pocket", "world_pocket_floor", "world_pocket_grit"):
        assert f'"{key}":' in PALETTE, f"{key} is not built anywhere"


def test_every_surface_the_profile_paints_is_in_exactly_one_band(v252):
    """A surface in two bands is a measurement bug, and this pass had one.

    The obstacle's ground zones were first painted with the obstacle's *rock*
    key, which is a midground key - and the measured world cover at the
    obstacle went from 12.5% to 39.3% with no object added. This is the
    assertion that would have caught it.
    """
    seen: dict[str, str] = {}
    for band, keys in v252_world.MARKED.items():
        for key in keys:
            assert key not in seen, \
                f"{key} is in both {seen.get(key)} and {band}"
            seen[key] = band
    for key in v252["palette"]:
        if key.startswith("lit_") or key.startswith("slope_"):
            continue
        if not key.startswith("world_") and not key.startswith("conifer"):
            continue
        assert key in seen, f"{key} is painted but in no marker band"


def test_the_marker_paints_every_marked_surface(profiles):
    marker = next(one for one in profiles.profiles()
                  if one["id"] == "_marker_v252")
    for band, keys in v252_world.MARKED.items():
        for key in keys:
            assert key in marker["palette"], f"{key} is unmarked"
            assert marker["palette"][key]["unshaded"] is True
            assert marker["palette"][key]["no_fog"] is True


def test_the_profile_json_is_not_stale(profiles):
    assert profiles.write(check=True) == [], \
        "run tools/sloped_v252_profiles.py"


# --- the instruments are sound ----------------------------------------------


def test_the_new_measures_return_nan_on_an_empty_band():
    """Empty is not zero: a band that vanished is not a band that improved."""
    grey = np.zeros((80, 80), dtype=float)
    empty = np.zeros((80, 80), dtype=bool)
    assert np.isnan(v252_world.dark_fraction(grey, empty))
    assert np.isnan(v252_world.value_spread(grey, empty))
    assert np.isnan(v252_world.warm_fraction(
        np.zeros((80, 80, 3), dtype=np.uint8), empty))


def test_the_dark_fraction_is_v251s_own_threshold():
    assert v252_world.DARK == 12


def test_the_value_spread_falls_when_a_field_is_smoothed():
    """The mosaic measure has to move the right way on a known input."""
    size = 400
    mask = np.ones((size, size), dtype=bool)
    # Facets a third the width of the 41-pixel template, so a window
    # straddles several of them. A facet much *wider* than the window
    # correctly measures zero - a template landing wholly inside one flat
    # face sees one value - and that is the property the parallax test's
    # own texture floor trips over, recorded in V25.1 section 15.
    cell = 13
    tiles = np.random.default_rng(5432).integers(
        8, 92, size=(size // cell + 1, size // cell + 1)).astype(float)
    facets = np.repeat(np.repeat(tiles, cell, 0), cell, 1)[:size, :size]
    ramp = np.tile(np.linspace(10, 90, size), (size, 1))
    assert v252_world.value_spread(facets, mask) \
        > v252_world.value_spread(ramp, mask)


def test_the_warm_fraction_counts_red_over_green_not_over_blue():
    """The correction that made the finish measurable.

    A cool-lit surface can warm a long way without red passing blue, so a
    threshold on `R - B` measures the light rather than the paint. Half of
    this image is teal - green well over red, blue over both - and half is
    warm; only the warm half may count, and it does so while every pixel in
    the image still has more blue than red.
    """
    image = np.zeros((60, 60, 3), dtype=np.uint8)
    mask = np.ones((60, 60), dtype=bool)
    image[..., 2] = 200
    image[:30, ..., 0] = 60
    image[:30, ..., 1] = 150
    image[30:, ..., 0] = 150
    image[30:, ..., 1] = 60
    assert v252_world.warm_fraction(image, mask) == pytest.approx(0.5)
    assert (image[..., 0].astype(int) - image[..., 2]).max() < 0
    assert v252_world.warm_shift(image, mask) < 0


def test_the_five_new_crops_are_inside_the_frame():
    for entry in v252_world.CROPS:
        left, top, right, bottom = entry.box
        assert 0.0 <= left < right <= 1.0
        assert 0.0 <= top < bottom <= 1.0
        assert entry.moment in {one.key for one in v252_world.MOMENTS}


def test_the_geometric_parallax_field_is_identical_to_v251s():
    """Part Q's "parallax remains strong", proved rather than asserted.

    Parallax is a property of where the forms are and where the camera goes.
    This pass moves no ring, no bearing and no radius, so the *analytic*
    parallax - the world's own form positions projected through the solved
    camera at two instants - must come out identical, band for band and pixel
    for pixel. If it does not, something in this pass moved geometry it said it
    did not.

    The image-space block matcher cannot make this call: V25.1's section 15
    records it failing on flat facets, and V25.2 breaks it a second way, on
    tempered gradients. This one never looks at a surface.
    """
    import math

    lab = _tool("sloped_v252_world")
    sites = _tool("sloped_v251_sites")
    from sloped import terrain

    cfg = terrain.terrain_config("b")
    readings = []
    for entry in v252_world.ALL:
        bands = sites._band_points(lab._Shim(lab._resolved(entry.key)), cfg)
        row = {}
        for label, track, before, after in sites.MOVES:
            first = sites._shot_at(track, before)
            second = sites._shot_at(track, after)
            for name, points in bands.items():
                moved = []
                for x, y, z in points:
                    a = first.project((x, y, z))
                    b = second.project((x, y, z))
                    if a[0] and b[0]:
                        moved.append(math.hypot(
                            (b[1] - a[1]) * 540.0, (b[2] - a[2]) * 960.0))
                if moved:
                    moved.sort()
                    row[(label, name)] = round(moved[len(moved) // 2], 3)
        readings.append(row)
    assert readings[0] == readings[1], "V25.2 moved the parallax field"
    assert readings[0], "the analytic parallax measured nothing at all"


def test_the_lab_writes_where_the_brief_says():
    lab = _tool("sloped_v252_world")
    assert lab.LAB_DIR.replace("\\", "/").endswith(
        "output/sloped_race_v1/v252_world")
    assert lab.DOC_DIR.replace("\\", "/").endswith(
        "docs/validation/sloped_race_v1/v252_world")
    assert lab.EXPORT_DIR.replace("\\", "/").endswith(
        "exports/v252_world_final_lookdev")
