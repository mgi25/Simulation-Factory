"""The environment profile system: the registry, the rules, and the two readers.

Three things are worth testing here and they are not the obvious one.

**That the rules are enforced, not documented.** GEOMETRY IS NOT THEME is the
constraint the whole design rests on - ``course_terrain.height`` decides where
every support pier stops and :mod:`sloped.terrain` is an exact port of it that
every production camera is solved against, so a theme that moved the landform
would invalidate both silently. ``validate`` has to reject that, and no profile
in the registry may carry one of those fields.

**That the two readers agree.** The profiles are JSON precisely so that
``environment_profile.gd`` and :mod:`sloped.environment` can parse the same
bytes instead of transcribing them. What can still drift is the *logic* - the
section list, the shape-field list, the merge rule - so the GDScript is read
as text and its constants are compared with Python's. A tool that validated
against a different rulebook than the scene builds under is the instrument bug
this project has already paid for twice.

**That every material a profile names exists.** A profile is data, so a typo in
it is not a syntax error anywhere: it is a ``push_error`` at render time, four
minutes into a batch. The palette's own key list is parsed out of
``lab_palette.gd`` and every key any profile references is checked against it.
"""

from __future__ import annotations

import copy
import io
import json
import os
import re

import pytest

from sloped import environment as env

GODOT = os.path.join(env.REPO, "godot", "assets", "marble_machine")
PROFILE_GD = os.path.join(GODOT, "environment", "environment_profile.gd")
BUILDER_GD = os.path.join(GODOT, "environment", "environment_builder.gd")
PALETTE_GD = os.path.join(GODOT, "lab_palette.gd")


def _read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


def _gd_string_list(source: str, name: str) -> list[str]:
    """The strings in a ``const NAME := [...]`` block of GDScript."""
    match = re.search(rf"const {name} := \[(.*?)\]", source, re.S)
    assert match, f"{name} not found in the GDScript"
    return re.findall(r'"([^"]+)"', match.group(1))


# --- the registry ---------------------------------------------------------


def test_every_listed_profile_loads_and_names_itself():
    for name in env.ids():
        raw = env.load(name)
        # The id inside the file has to match the file it is in, or
        # `--environment=x` selects one profile and the scene reports another.
        assert raw["id"] == name


def test_the_default_is_in_the_registry():
    assert env.default_id() in env.ids()


def test_the_root_profile_extends_nothing_and_is_the_default():
    assert env.load(env.default_id())["extends"] is None


def test_every_profile_resolves_clean_under_both_contrast_passes():
    for name in env.ids():
        for contrast in ("", "v21"):
            assert env.validate(env.resolve(name, contrast)) == []


def test_the_root_profile_sets_every_section():
    profile = env.resolve("alpine_neon")
    for section in ("sky", "grade", "fog", "ssao", "ssr", "glow", "lights",
                    "backdrop", "terrain", "dressing", "zones", "accent",
                    "palette"):
        assert section in profile, section


# --- inheritance ----------------------------------------------------------


def test_a_delta_inherits_what_it_does_not_set():
    root = env.resolve("alpine_neon")
    canyon = env.resolve("canyon_dusk")
    # canyon_dusk says nothing about SSAO, so it gets the root's.
    assert canyon["ssao"] == root["ssao"]
    assert canyon["sky"]["top"] != root["sky"]["top"]
    # ... and inherits the untouched half of a section it does edit.
    assert canyon["sky"]["curve"] != root["sky"]["curve"]
    assert canyon["fog"]["height_density"] != root["fog"]["height_density"]
    assert canyon["dressing"]["lamps"]["spacing"] == \
        root["dressing"]["lamps"]["spacing"]


def test_identity_survives_inheritance():
    canyon = env.resolve("canyon_dusk")
    assert canyon["id"] == "canyon_dusk"
    assert canyon["title"] != env.resolve("alpine_neon")["title"]
    assert canyon["extends"] == "alpine_neon"


def test_null_erases_rather_than_shadows():
    """The rule that lets canyon_dusk take a generated ring.

    An empty list would still read as authored and the generator would never
    run, so erasure has to be a distinct outcome from replacement.
    """
    canyon = env.resolve("canyon_dusk")
    assert "masses" not in canyon["backdrop"]["near_range"]
    assert "ring" in canyon["backdrop"]["near_range"]
    assert env.masses_of(canyon["backdrop"]["near_range"])


def test_merge_leaves_the_base_alone():
    base = {"a": {"b": 1}, "c": [1, 2]}
    before = copy.deepcopy(base)
    env.merge(base, {"a": {"b": 2}, "c": [3]})
    assert base == before


# --- the contrast overlay -------------------------------------------------


def test_the_contrast_pass_is_an_overlay_not_a_fork():
    plain = env.resolve("alpine_neon")
    v21 = env.resolve("alpine_neon", "v21")
    assert plain["grade"]["ambient_energy"] == 0.42
    assert v21["grade"]["ambient_energy"] == 0.35
    assert v21["lights"]["Key"]["energy"] == 2.7
    # Everything the pass does not name is untouched.
    assert v21["sky"] == plain["sky"]
    assert v21["lights"]["WorldWarm"] == plain["lights"]["WorldWarm"]


def test_the_contrast_pass_composes_with_any_profile():
    """It is inherited, so a theme gets the readability retune for free."""
    canyon = env.resolve("canyon_dusk", "v21")
    assert canyon["ssao"]["radius"] == 0.7
    assert canyon["glow"]["hdr_threshold"] == 1.34
    # ... and the theme still wins where the two overlap, because the overlay
    # is merged on top of the resolved chain, not on top of the root.
    assert canyon["lights"]["WorldWarm"]["colour"] == "#FF7A2E"


def test_the_resolved_profile_records_which_pass_it_is_under():
    assert env.resolve("alpine_neon", "v21")["contrast_pass"] == "v21"
    assert env.resolve("alpine_neon")["contrast_pass"] == ""
    assert "contrast" not in env.resolve("alpine_neon")


# --- the accent dial ------------------------------------------------------


def test_accent_one_changes_nothing():
    profile = env.resolve("alpine_neon")
    assert profile["accent"]["intensity"] == 1.0
    assert profile["zones"]["start"]["energy"] == 2.6


def test_accent_scales_the_lit_values_the_profile_owns():
    raw = env.load("glow_valley")
    gain = raw["accent"]["intensity"]
    resolved = env.resolve("glow_valley")
    assert resolved["zones"]["start"]["energy"] == \
        pytest.approx(raw["zones"]["start"]["energy"] * gain)
    assert resolved["dressing"]["practicals"]["spill"]["energy"] == \
        pytest.approx(raw["dressing"]["practicals"]["spill"]["energy"] * gain)
    assert resolved["palette"]["lit_valley_hero"]["energy"] == \
        pytest.approx(raw["palette"]["lit_valley_hero"]["energy"] * gain)


def test_accent_leaves_surfaces_it_was_never_shown():
    """The dial reaches nothing it cannot see a base value for.

    A dial that silently scaled materials it had not been handed would make
    two profiles with identical numbers render differently, which is the one
    thing a data-driven system must not do.
    """
    resolved = env.resolve("mono_readability")
    assert resolved["accent"]["intensity"] != 1.0
    assert "energy" not in resolved["palette"]["slope_cliff"]


# --- GEOMETRY IS NOT THEME ------------------------------------------------


def test_no_profile_in_the_registry_touches_the_landform():
    for name in env.ids():
        terrain = env.resolve(name).get("terrain", {})
        assert not set(terrain) & set(env.SHAPE_FIELDS), name


@pytest.mark.parametrize("field", ["grade", "gorge_depth", "pads", "noise",
                                   "cell", "x_min"])
def test_validate_rejects_a_landform_field(field):
    profile = env.resolve("alpine_neon")
    profile["terrain"][field] = 1.0
    problems = env.validate(profile)
    assert any("GEOMETRY IS NOT THEME" in problem for problem in problems)


def test_validate_rejects_a_landform_field_hidden_in_a_contrast_overlay():
    profile = env.load("alpine_neon")
    profile["contrast"]["v21"]["terrain"] = {"gorge_depth": 2.0}
    assert any("landform" in problem for problem in env.validate(profile))


def test_validate_rejects_an_unknown_section():
    profile = env.resolve("alpine_neon")
    profile["weather"] = {}
    assert any("weather" in problem for problem in env.validate(profile))


def test_validate_rejects_an_unknown_terrain_key():
    profile = env.resolve("alpine_neon")
    profile["terrain"]["trees"] = 4
    assert any("trees" in problem for problem in env.validate(profile))


def test_validate_rejects_a_negative_light():
    profile = env.resolve("alpine_neon")
    profile["lights"]["Key"]["energy"] = -1.0
    assert any("negative" in problem for problem in env.validate(profile))


def test_validate_wants_an_identity():
    assert "missing title" in env.validate({"id": "x", "summary": "y"})


# --- the backdrop generator -----------------------------------------------


def test_authored_masses_win_over_a_ring():
    layer = {"masses": [[1.0, 2.0, 3.0, 4.0, 5]],
             "ring": {"count": 9, "radius": 100.0}}
    assert env.masses_of(layer) == [[1.0, 2.0, 3.0, 4.0, 5]]


def test_a_ring_generates_the_same_five_columns():
    layer = {"ring": {"count": 3, "bearing_from": 10.0, "bearing_step": 20.0,
                      "radius": 200.0, "radius_step": 10.0, "radius_cycle": 2,
                      "height": 100.0, "base": 40.0,
                      "seed_from": 3, "seed_step": 8}}
    masses = env.masses_of(layer)
    assert [entry[0] for entry in masses] == [10.0, 30.0, 50.0]
    assert [entry[1] for entry in masses] == [200.0, 210.0, 200.0]
    assert [entry[4] for entry in masses] == [3, 11, 19]
    assert all(len(entry) == 5 for entry in masses)


def test_a_ring_wraps_its_bearings():
    layer = {"ring": {"count": 2, "bearing_from": 350.0, "bearing_step": 20.0,
                      "radius": 1.0}}
    assert [entry[0] for entry in env.masses_of(layer)] == [350.0, 10.0]


def test_a_layer_with_neither_builds_nothing():
    assert env.masses_of({"facets": 12}) == []


# --- the two readers ------------------------------------------------------


def test_the_shape_field_list_matches_the_gdscript():
    source = _read(PROFILE_GD)
    assert _gd_string_list(source, "SHAPE_FIELDS") == list(env.SHAPE_FIELDS)


def test_the_section_list_matches_the_gdscript():
    source = _read(PROFILE_GD)
    assert _gd_string_list(source, "SECTIONS") == list(env.SECTIONS)
    assert _gd_string_list(source, "TERRAIN_SECTIONS") == \
        list(env.TERRAIN_SECTIONS)


def test_the_default_id_matches_the_gdscript():
    source = _read(PROFILE_GD)
    match = re.search(r'const DEFAULT_ID := "([^"]+)"', source)
    assert match and match.group(1) == env.DEFAULT_ID


def test_the_builder_holds_no_colours_of_its_own():
    """No default look in the builder - the profile decides or nothing does.

    The only hex literals allowed are the last-resort fallbacks inside a
    `.get(key, "#......")`, which fire on a malformed profile and never on a
    valid one. A colour anywhere else is a value that cannot be themed and
    that no profile diff would ever show, which is exactly how a framework
    quietly becomes a hard-coded environment again.
    """
    source = re.sub(r'get\(\s*"[a-z_0-9]+"\s*,\s*"#[0-9A-Fa-f]{6}"\s*\)',
                    "get()", _read(BUILDER_GD))
    assert not re.findall(r'"#[0-9A-Fa-f]{6}"', source)


# --- the material keys ----------------------------------------------------


def _palette_keys() -> set[str]:
    source = _read(PALETTE_GD)
    body = source[source.index("func _build(key: String)"):]
    keys: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.endswith(":") and stripped.startswith('"'):
            keys.update(re.findall(r'"([a-z_0-9]+)"', stripped))
    return keys


def _referenced_materials(profile: dict) -> set[str]:
    """Every palette key a resolved profile names, wherever it names it."""
    named: set[str] = set(profile.get("palette", {}))
    backdrop = profile.get("backdrop", {})
    for layer in ("near_range", "mid_range", "far_range"):
        named.update(backdrop.get(layer, {}).get("materials", []))
    for section, fields in (("structures", ("shell", "lit")),
                            ("dusk_band", ("material",)),
                            ("clouds", ("material",))):
        for field in fields:
            value = backdrop.get(section, {}).get(field)
            if value:
                named.add(value)
    terrain = profile.get("terrain", {})
    named.update(terrain.get("surfaces", {}).values())
    for entry in terrain.get("scatter", []):
        named.update(entry.get("materials", []))
    dressing = profile.get("dressing", {})
    for field in ("column", "foot", "arm", "head"):
        if dressing.get("lamps", {}).get(field):
            named.add(dressing["lamps"][field])
    named.update(dressing.get("lamps", {}).get("lenses", []))
    named.update(dressing.get("scrub", {}).get("materials", []))
    for field in ("beacon", "leg", "tie"):
        if dressing.get("pylons", {}).get(field):
            named.add(dressing["pylons"][field])
    for field in ("deck", "glow", "block"):
        if dressing.get("valley", {}).get(field):
            named.add(dressing["valley"][field])
    return named


def test_the_palette_key_parser_finds_the_palette():
    keys = _palette_keys()
    assert {"slope_cliff", "cloud_bank", "graphite", "lit_dusk_band"} <= keys


def test_every_material_a_profile_names_exists():
    known = _palette_keys()
    for name in env.ids():
        missing = _referenced_materials(env.resolve(name)) - known
        assert not missing, f"{name} names unknown materials: {sorted(missing)}"


# --- the files themselves -------------------------------------------------


def test_the_profiles_on_disk_are_the_ones_in_the_index():
    on_disk = {
        os.path.splitext(name)[0]
        for name in os.listdir(env.PROFILE_ROOT)
        if name.endswith(".json") and name != "index.json"
    }
    assert on_disk == set(env.ids())


def test_every_profile_carries_a_summary_worth_reading():
    for name in env.ids():
        summary = env.load(name)["summary"]
        assert len(summary) > 80, name


def test_a_profile_file_is_valid_json_with_a_trailing_newline():
    for name in env.ids() + ["index"]:
        path = os.path.join(env.PROFILE_ROOT, f"{name}.json")
        text = io.open(path, encoding="utf-8").read()
        json.loads(text)
        assert text.endswith("\n"), name


def test_diff_reports_what_changed_and_nothing_else():
    changes = env.diff(env.resolve("alpine_neon"), env.resolve("alpine_neon"))
    assert changes == []
    paths = [path for path, _, _ in
             env.diff(env.resolve("alpine_neon"), env.resolve("glow_valley"))]
    assert "sky.top" in paths
    assert "ssao.radius" not in paths


def test_describe_counts_what_the_scene_will_build():
    profile = env.resolve("alpine_neon")
    line = env.describe(profile)
    masses = sum(len(env.masses_of(profile["backdrop"][layer]))
                 for layer in ("near_range", "mid_range", "far_range"))
    assert f"{masses} backdrop masses" in line
    assert "174 scattered rocks" in line
