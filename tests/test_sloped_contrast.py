"""The V21 readability pass: what it is allowed to change, and what it is not.

Not a rendering test - Godot is not run here. A material pass is judged by
looking at frames, and the frames are committed under
`docs/validation/sloped_race_v1/v21/`. What can be checked arithmetically is
everything that would make the pass *silently wrong*, and that is what these
are:

* that it is gated, so every earlier lab's committed frames still reproduce;
* that every key it retunes is a key that exists, because a typo in an
  override table is a change that does nothing and reports nothing;
* that every field it sets is a field the applier knows about, for the same
  reason;
* that the direction of each move is the direction the pass claims - the
  pearls came *down*, the edge lights got *quieter* - because a sign error
  here is the one mistake the measurements would not obviously catch; and
* that the art direction survives it: pearl is still warm-neutral pearl and
  not a grey card, the two route identities keep their hue, and gold is still
  gold.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from sloped import environment as env

GODOT = Path(__file__).resolve().parents[1] / "godot"
PALETTE_GD = GODOT / "assets" / "marble_machine" / "lab_palette.gd"
WORLD_GD = GODOT / "assets" / "marble_machine" / "course" / "course_world.gd"
COURSE_SCENE_GD = GODOT / "scripts" / "course_scene.gd"
RACE_SCENE_GD = GODOT / "scripts" / "sloped_race_scene.gd"

PALETTE = PALETTE_GD.read_text(encoding="utf-8")
WORLD = WORLD_GD.read_text(encoding="utf-8")

# Fields `_retune` is able to apply. A table entry naming anything else is a
# silent no-op.
RETUNE_FIELDS = {"albedo", "roughness", "metallic", "specular", "clearcoat",
                 "clearcoat_roughness", "energy", "rim", "rim_tint"}


def _hex_to_rgb(value: str) -> tuple[float, float, float]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _linear(channel: float) -> float:
    return (channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4)


def _luminance(hex_value: str) -> float:
    r, g, b = (_linear(c) for c in _hex_to_rgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _constants() -> dict[str, str]:
    return {name: value for name, value in
            re.findall(r'^const ([A-Z_0-9]+) := "(#[0-9A-Fa-f]{6})"',
                       PALETTE, re.M)}


def _retune_table() -> dict[str, dict[str, object]]:
    """`V21_RETUNE`, parsed into {key: {field: value}}."""
    block = re.search(r"const V21_RETUNE := \{(.*?)\n\}\n", PALETTE, re.S)
    assert block, "V21_RETUNE is not declared in lab_palette.gd"
    # Whole-line comments only: a `#` also starts every colour in the table,
    # and stripping from it would eat the values this is here to read.
    body = "\n".join(line for line in block.group(1).splitlines()
                     if not line.strip().startswith("#"))
    table: dict[str, dict[str, object]] = {}
    for key, spec in re.findall(r'"([a-z_0-9]+)":\s*\{(.*?)\}', body, re.S):
        fields: dict[str, object] = {}
        for field, raw in re.findall(r'"([a-z_]+)":\s*("?[^,\}"]+"?)', spec):
            raw = raw.strip()
            fields[field] = (raw.strip('"') if raw.startswith('"')
                             else float(raw))
        table[key] = fields
    assert table, "V21_RETUNE parsed empty"
    return table


def _build_arms() -> dict[str, str]:
    """`_build`'s match arms, as {key: the source of its branch}."""
    body = PALETTE.split("func _build(key: String) -> StandardMaterial3D:")[1]
    body = body.split("\n\nfunc marble(")[0]
    arms: dict[str, str] = {}
    parts = re.split(r'\n\t\t"([a-z_0-9]+)":\n', body)
    for index in range(1, len(parts) - 1, 2):
        arms[parts[index]] = parts[index + 1]
    assert arms, "_build parsed no match arms"
    return arms


TABLE = _retune_table()
ARMS = _build_arms()
CONSTANTS = _constants()


def _arm_albedo(key: str) -> str | None:
    """The hex a `_build` arm paints with, resolving a named constant."""
    arm = ARMS[key]
    match = re.search(r'_(?:moulded|matte|metal|acrylic|acrylic_soft|emissive)'
                      r'\(\s*(?:"(#[0-9A-Fa-f]{6})"|([A-Z_0-9]+))', arm)
    if match is None:
        return None
    return match.group(1) or CONSTANTS.get(match.group(2))


def _arm_number(key: str, position: int) -> float | None:
    """The nth positional float of an arm's builder call."""
    arm = ARMS[key]
    match = re.search(r"_(?:moulded|matte|metal|emissive)\(([^)]*)\)", arm)
    if match is None:
        return None
    args = [a.strip() for a in match.group(1).split(",")]
    if len(args) <= position:
        return None
    try:
        return float(args[position])
    except ValueError:
        return None


# --- the pass is gated -----------------------------------------------------

def test_the_labs_default_to_the_v20_look():
    """An ungated retune would silently re-grade every committed lab frame.

    The V23 environment system moved the world's numbers into
    `environment/profiles/alpine_neon.json` and added a resolved profile to
    both calls. The gate did not move: `_contrast` still starts empty, and it
    is still what selects the pass.
    """
    text = COURSE_SCENE_GD.read_text(encoding="utf-8")
    assert 'var _contrast := ""' in text
    assert 'Palette.new("tower", _contrast)' in text
    assert "World.build_environment(_no_glow, _contrast," in text
    assert "World.build_lights(self, _contrast," in text


def test_only_the_race_scene_turns_the_pass_on():
    text = RACE_SCENE_GD.read_text(encoding="utf-8")
    assert 'const DEFAULT_CONTRAST := "v21"' in text
    assert '_contrast = str(early.get("contrast", DEFAULT_CONTRAST))' in text
    # ...and it has to be set *before* `super()`, because the palette, the
    # environment and the light rig are all built inside it.
    body = text.split("func _ready() -> void:")[1]
    assert body.index("_contrast = str(early.get(") < body.index("\n\tsuper()")


def test_every_environment_change_is_behind_the_flag():
    """`build_environment` and `build_lights` must do nothing new by default.

    This used to be read out of `course_world.gd`, where each energy the pass
    moves was written as `2.7 if v21 else 3.2` so the V20 value stayed in the
    file. V23 moved those numbers into the root environment profile and the
    pass into its `contrast.v21` overlay, so the same guarantee is now a
    property of the data: the profile resolved with no contrast pass is the
    V20 rig, field for field.
    """
    assert 'const CONTRAST_V21 := "v21"' in WORLD
    assert 'static func build_environment(no_glow: bool, contrast := ""' in WORLD
    assert 'static func build_lights(parent: Node3D, contrast := ""' in WORLD
    v20 = env.resolve("alpine_neon")
    for light, energy in (("Key", 3.2), ("WorldKey", 2.9),
                          ("WorldFill", 0.95), ("Rim", 2.3),
                          ("ValleyBounce", 1.15)):
        assert v20["lights"][light]["energy"] == energy, \
            f"{light} lost its V20 value"
    assert v20["grade"]["ambient_energy"] == 0.42
    assert v20["glow"]["hdr_threshold"] == 1.16
    assert v20["ssao"]["radius"] == 0.9


def test_the_v21_pass_still_moves_exactly_what_it_moved():
    """The overlay is the whole of the pass, and it is a short list.

    V21 was argued light by light. If a later theme edit widened the overlay
    the argument would no longer describe what ships, so the overlay's own
    reach is pinned here rather than left to a render comparison.
    """
    v20 = env.resolve("alpine_neon")
    v21 = env.resolve("alpine_neon", "v21")
    moved = {path for path, _, _ in env.diff(v20, v21)}
    assert moved == {
        "contrast_pass",
        "grade.ambient_energy", "grade.contrast", "grade.saturation",
        "fog.density", "fog.aerial_perspective",
        "ssao.radius", "ssao.intensity", "ssao.light_affect",
        "glow.intensity", "glow.bloom", "glow.hdr_threshold",
        "lights.Key.energy", "lights.WorldKey.energy",
        "lights.WorldFill.energy",
        "lights.Rim.energy", "lights.Rim.specular",
        "lights.ValleyBounce.energy",
    }


def test_the_palette_only_retunes_when_asked():
    assert "if contrast == CONTRAST_V21 and V21_RETUNE.has(key):" in PALETTE
    assert "func _init(art_variant: String = VARIANT_TOWER," in PALETTE


# --- the table is not silently broken --------------------------------------

@pytest.mark.parametrize("key", sorted(TABLE))
def test_every_retuned_key_is_a_key_that_exists(key):
    """A typo in an override table is a change that does nothing, quietly."""
    assert key in ARMS, f"'{key}' is retuned but `_build` does not define it"


@pytest.mark.parametrize("key", sorted(TABLE))
def test_every_retuned_field_is_a_field_the_applier_knows(key):
    unknown = set(TABLE[key]) - RETUNE_FIELDS
    assert not unknown, f"'{key}' sets {sorted(unknown)}, which `_retune` drops"


def test_the_applier_handles_every_field_the_table_uses():
    used = {field for spec in TABLE.values() for field in spec}
    applier = PALETTE.split("func _retune(")[1].split("\n\n\n")[0]
    for field in sorted(used):
        assert f'spec.has("{field}")' in applier, f"`_retune` ignores {field}"


# --- the moves go the way the pass says they go ----------------------------

PEARL_KEYS = ["pearl_lip", "pearl_track", "pearl_shell", "pearl_shade",
              "pearl_lip_v2", "pearl_soft", "pearl_warm", "pearl_warm_shade",
              "running_polished", "running_warm", "running_blue",
              "running_orange", "checker_light", "track_floor_v2",
              "dish_polished", "pan_polished", "dish_floor"]


@pytest.mark.parametrize("key", PEARL_KEYS)
def test_every_light_surface_came_down(key):
    """The pass exists because these were clipping. None may get brighter."""
    before = _arm_albedo(key)
    assert before, f"could not read `_build`'s albedo for '{key}'"
    after = TABLE[key]["albedo"]
    assert _luminance(after) < _luminance(before), (
        f"{key}: {before} -> {after} is not darker")


@pytest.mark.parametrize("key", PEARL_KEYS)
def test_no_light_surface_came_down_more_than_half_a_stop(key):
    """The mistake the whole palette was rewritten to stop happening twice.

    A grey card is linear 0.18, and `lab_palette`'s own docstring records that
    reading sRGB floats as brightness is what turned an earlier machine into
    one. This pass is a quarter to under half a stop - a regrade, not a
    repaint - and the bound is what stops a later edit turning it into one.
    """
    before = _arm_albedo(key)
    assert _luminance(TABLE[key]["albedo"]) > _luminance(before) * 0.70


PEARL_WHITES = ["pearl_lip", "pearl_track", "pearl_shell", "pearl_lip_v2",
                "pearl_warm", "checker_light"]


@pytest.mark.parametrize("key", PEARL_WHITES)
def test_the_white_family_is_still_white_plastic(key):
    """Well clear of a grey card, or it stops reading as moulded at all."""
    assert _luminance(TABLE[key]["albedo"]) > 0.45


@pytest.mark.parametrize("key", ["pearl_lip", "pearl_track", "pearl_shell",
                                 "pearl_shade", "pearl_lip_v2", "pearl_warm"])
def test_the_pearl_family_is_still_warm_neutral(key):
    """`Pearl runs warm` is a palette rule, not a V20 accident."""
    r, g, b = _hex_to_rgb(TABLE[key]["albedo"])
    assert r > b, f"{key} lost its warm cast"
    assert (max(r, g, b) - min(r, g, b)) < 0.14, f"{key} is no longer neutral"


@pytest.mark.parametrize("key", ["pearl_lip", "pearl_track", "pearl_shell",
                                 "pearl_shade", "pearl_lip_v2", "pearl_warm",
                                 "running_polished", "dish_floor"])
def test_the_light_surfaces_also_got_rougher(key):
    """Value alone flattens a surface; roughness is what shades it."""
    before = _arm_number(key, 1)
    assert before is not None, f"could not read `_build`'s roughness for {key}"
    assert TABLE[key]["roughness"] > before


EDGE_LIGHTS = ["lit_cyan_line_hero", "neon_violet_hero", "neon_blue",
               "lit_orange_line", "lit_gold_line", "lit_cyan_line",
               "lit_violet_ring_hero", "lit_gold_wash", "lit_valley_hero"]


@pytest.mark.parametrize("key", EDGE_LIGHTS)
def test_every_edge_light_got_quieter(key):
    before = _arm_number(key, 1)
    assert before is not None, f"could not read `_build`'s energy for {key}"
    assert TABLE[key]["energy"] < before, f"{key} did not come down"


def test_the_zone_story_survives():
    """Cyan, violet, blue, orange, gold - in that order down the course.

    The retune may change how loud each zone is and may not change which
    colour it is, because the edge lights are how a viewer four seconds into
    a Short knows roughly where in the race they are.
    """
    for key in EDGE_LIGHTS:
        assert "albedo" not in TABLE[key], f"{key} changed colour, not energy"
        assert set(TABLE[key]) == {"energy"}


def test_both_route_identities_keep_their_hue():
    """Blue is blue and orange is orange, or the split stops being a choice."""
    for key, channel in (("blue_machine", 2), ("orange_machine", 0)):
        before = _arm_albedo(key)
        after = TABLE[key]["albedo"]
        for hue in (_hex_to_rgb(before), _hex_to_rgb(after)):
            assert hue.index(max(hue)) == channel
        # And no more than a half step of value, so neither branch becomes a
        # different colour on the way to becoming a less washed one.
        assert _luminance(after) > _luminance(before) * 0.80


def test_the_finish_keeps_its_gold_and_its_checker():
    """Section 5 of the brief: the finish identity is not up for redesign."""
    # Gold is retuned for roughness and specular only - never repainted.
    for key in ("gold", "gold_bright", "gold_dark"):
        assert "albedo" not in TABLE[key]
    # The checker is a contrast motif, so only the light tile is allowed to
    # move; darkening the dark tile too would keep the ratio and lose the read.
    assert "checker_dark" not in TABLE
    assert _luminance(TABLE["checker_light"]["albedo"]) > 0.45


def test_the_racers_keep_their_skins():
    """The one racer change is a response change. The eight hues do not move."""
    body = PALETTE.split("func marble(index: int)")[1]
    assert "if contrast == CONTRAST_V21:" in body
    assert "material.rim = 0.42" in body
    assert "material.rim_tint = 0.95" in body
    # Nothing in the V21 branch touches the body colour.
    branch = body.split("if contrast == CONTRAST_V21:")[1].split("_cache[")[0]
    assert "albedo" not in branch
    assert "MARBLE_COLOURS" not in branch
    for key in TABLE:
        assert not key.startswith("marble"), "a racer skin is being retuned"
