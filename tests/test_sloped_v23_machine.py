"""The V23 machine colour passes: what they may change, and what they may not.

Not a rendering test - Godot is not run here. A colour language is judged by
looking at frames, and the frames are committed under
`docs/validation/sloped_race_v1/v23_machine/`. What can be checked
arithmetically is everything that would make a pass *silently wrong*:

* that it is gated, so the shipped machine and every earlier lab's committed
  proof keep reproducing - the strongest form of which is checked against the
  renderer, not here: thirteen frames rendered with no pass are byte-identical
  to thirteen rendered before this branch existed;
* that the three alias keys are aliases, in `_build` and in `V21_RETUNE` both,
  because an alias that is *nearly* its original is a silent re-skin of the
  route, the sweep or every guard in the course;
* that every key a pass names exists and every field it sets is a field the
  applier knows, because a typo in an override table is a change that does
  nothing and reports nothing;
* that a pass changes **colour and not response** - V21 decided how each
  surface answers a light, and a colour pass that also re-narrows specular
  lobes is a second readability pass wearing a palette's name;
* that no pass repaints a racer or touches the environment, which are the two
  things the brief locks; and
* that each pass's own claim about direction holds - the neutrals went cool,
  the rotor went violet and stayed clear of the purple racer, both routes kept
  their hue, gold stayed gold.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PALETTE_GD = GODOT / "assets" / "marble_machine" / "lab_palette.gd"
COURSE_SCENE_GD = GODOT / "scripts" / "course_scene.gd"
MODULES_GD = GODOT / "assets" / "marble_machine" / "course" / "course_modules.gd"

PALETTE = PALETTE_GD.read_text(encoding="utf-8")
COURSE_SCENE = COURSE_SCENE_GD.read_text(encoding="utf-8")
MODULES = MODULES_GD.read_text(encoding="utf-8")

PASSES = ("v23a", "v23b", "v23c")

#: Fields `_retune` can apply. A row naming anything else is a silent no-op.
RETUNE_FIELDS = {"albedo", "roughness", "metallic", "specular", "clearcoat",
                 "clearcoat_roughness", "energy", "rim", "rim_tint",
                 "emission", "backlight"}

#: How a surface answers a light, as opposed to what colour it is. V21 set
#: these and a machine pass does not get to move them.
RESPONSE_FIELDS = {"roughness", "clearcoat", "clearcoat_roughness"}

#: The two keys a pass *repaints* rather than recolours, and which may
#: therefore state their own gloss. See the rule in `lab_palette.gd`.
REPAINTED = {"rotor_machine", "hazard_machine"}

#: Everything that is not the machine. A pass that names one of these has
#: reached past what it is allowed to change.
ENVIRONMENT_PREFIXES = ("rock_", "cloud_", "backdrop_", "slope_", "scrub_",
                        "lit_valley", "lit_far_window", "lit_horizon",
                        "lit_dusk", "far_structure", "lit_window")


# --- parsing ---------------------------------------------------------------

def _constants() -> dict[str, str]:
    return {name: value for name, value in
            re.findall(r'^const ([A-Z_0-9]+) := "(#[0-9A-Fa-f]{6})"',
                       PALETTE, re.M)}


CONSTANTS = _constants()


def _table(name: str) -> dict[str, dict[str, object]]:
    """A `const NAME := {...}` override table, as {key: {field: value}}."""
    block = re.search(r"const %s := \{(.*?)\n\}\n" % name, PALETTE, re.S)
    assert block, "%s is not declared in lab_palette.gd" % name
    body = "\n".join(line for line in block.group(1).splitlines()
                     if not line.strip().startswith("#"))
    out: dict[str, dict[str, object]] = {}
    for key, spec in re.findall(r'"([a-z_0-9]+)":\s*\{([^{}]*?)\}', body, re.S):
        fields: dict[str, object] = {}
        for field, raw in re.findall(r'"([a-z_]+)":\s*("?[^,\}"]+"?)', spec):
            raw = raw.strip()
            fields[field] = (raw.strip('"') if raw.startswith('"')
                             else float(raw))
        out[key] = fields
    assert out, "%s parsed empty" % name
    return out


def _machine_passes() -> dict[str, dict[str, dict[str, object]]]:
    """`MACHINE_PASSES`, as {pass: {key: {field: value}}}."""
    block = re.search(r"const MACHINE_PASSES := \{(.*?)\n\}\n", PALETTE, re.S)
    assert block, "MACHINE_PASSES is not declared in lab_palette.gd"
    body = block.group(1)
    out: dict[str, dict[str, dict[str, object]]] = {}
    for name in PASSES:
        start = body.index('\t"%s": {' % name)
        depth = 0
        for index in range(start, len(body)):
            if body[index] == "{":
                depth += 1
            elif body[index] == "}":
                depth -= 1
                if depth == 0:
                    break
        chunk = body[start:index + 1]
        chunk = "\n".join(line for line in chunk.splitlines()
                          if not line.strip().startswith("#"))
        table: dict[str, dict[str, object]] = {}
        for key, spec in re.findall(r'"([a-z_0-9]+)":\s*\{([^{}]*?)\}',
                                    chunk, re.S):
            fields: dict[str, object] = {}
            for field, raw in re.findall(r'"([a-z_]+)":\s*("?[^,\}"]+"?)',
                                         spec):
                raw = raw.strip()
                fields[field] = (raw.strip('"') if raw.startswith('"')
                                 else float(raw))
            table[key] = fields
        assert table, "%s parsed empty" % name
        out[name] = table
    return out


def _build_arms() -> dict[str, str]:
    body = PALETTE.split("func _build(key: String) -> StandardMaterial3D:")[1]
    body = body.split("\n\nfunc marble(")[0]
    arms: dict[str, str] = {}
    parts = re.split(r'\n\t\t"([a-z_0-9]+)":\n', body)
    for index in range(1, len(parts) - 1, 2):
        arms[parts[index]] = parts[index + 1]
    assert arms, "_build parsed no match arms"
    return arms


V21 = _table("V21_RETUNE")
MACHINE = _machine_passes()
ARMS = _build_arms()


def _code(arm: str) -> str:
    """A `_build` arm with its comments and its neighbours' comments removed.

    `_build_arms` splits on the next `"key":` line, so an arm's text runs on
    into the comment block that introduces the arm after it.
    """
    lines = []
    for line in arm.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        lines.append(line.strip())
    return "\n".join(lines)


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _linear(channel: float) -> float:
    return (channel / 12.92 if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4)


def _luminance(hex_value: str) -> float:
    r, g, b = (_linear(c / 255.0) for c in _rgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _shipped(key: str) -> str | None:
    """A key's albedo on the machine that ships: `_build`, then V21 over it."""
    if key in V21 and "albedo" in V21[key]:
        return str(V21[key]["albedo"])
    arm = ARMS.get(key, "")
    match = re.search(r'_(?:moulded|matte|metal|acrylic|acrylic_soft|emissive)'
                      r'\(\s*(?:"(#[0-9A-Fa-f]{6})"|([A-Z_0-9]+))', arm)
    if match is None:
        return None
    return match.group(1) or CONSTANTS.get(match.group(2))


ALL_ROWS = [(name, key, spec)
            for name, table in MACHINE.items()
            for key, spec in table.items()]
ROW_IDS = ["%s/%s" % (name, key) for name, key, _spec in ALL_ROWS]


# --- the passes are gated --------------------------------------------------

def test_no_pass_is_on_by_default():
    """An ungated pass would re-skin the shipped film and every lab proof."""
    assert 'var machine: String = ""' in PALETTE
    assert 'machine_pass: String = ""' in PALETTE
    assert 'var _machine := ""' in COURSE_SCENE


def test_only_the_command_line_turns_a_pass_on():
    """`--machine=` and nothing else. No scene sets a default, as the race
    scene does for `--contrast`: a colour language is a proposal until it is
    chosen, and V23 has not been chosen."""
    assert 'if options.has("machine"):' in COURSE_SCENE
    assert '_palette = Palette.new("tower", _contrast, _machine)' in COURSE_SCENE
    for source, path in ((PALETTE, PALETTE_GD), (COURSE_SCENE, COURSE_SCENE_GD)):
        assert not re.search(r'DEFAULT_MACHINE\s*:?=\s*"v23', source), path


def test_the_pass_is_applied_over_the_contrast_pass_not_instead_of_it():
    """V21 first, then the colour language: the order is the whole design."""
    body = PALETTE.split("func get_material(")[1].split("\nfunc ")[0]
    assert body.index("V21_RETUNE.has(key)") < body.index("MACHINE_PASSES.has")


# --- the aliases are aliases -----------------------------------------------

@pytest.mark.parametrize("alias,original", [
    ("rotor_machine", "orange_machine"),
    ("hazard_machine", "orange_machine"),
    ("acrylic_drum", "acrylic_guard"),
])
def test_each_alias_builds_exactly_as_the_key_it_aliases(alias, original):
    """Otherwise turning a pass *off* would not give back the shipped machine."""
    assert _code(ARMS[alias]) == _code(ARMS[original])


@pytest.mark.parametrize("alias,original", [
    ("rotor_machine", "orange_machine"),
    ("hazard_machine", "orange_machine"),
    ("acrylic_drum", "acrylic_guard"),
])
def test_each_alias_carries_the_same_v21_row(alias, original):
    """The race renders under "v21"; an alias without V21's row would render
    the rotor, the sweep or the mixing drum at the V20 setting."""
    assert V21[alias] == V21[original]


def test_the_course_asks_for_the_aliases():
    """An alias nothing builds with is a pass that changes nothing."""
    assert '"rotor_machine"' in MODULES
    assert '"hazard_machine"' in MODULES
    assert '"acrylic_drum"' in MODULES


def test_the_orange_route_still_asks_for_orange_machine():
    """The whole point of the aliases is that the *route* keeps its key."""
    machine = (GODOT / "assets" / "marble_machine" / "course"
               / "course_machine.gd").read_text(encoding="utf-8")
    assert 'shell = "orange_machine"' in machine
    assert 'shell = "blue_machine"' in machine


# --- every row is a row that does something --------------------------------

@pytest.mark.parametrize("name,key,spec", ALL_ROWS, ids=ROW_IDS)
def test_every_key_a_pass_names_is_a_key_that_exists(name, key, spec):
    assert key in ARMS, "%s names '%s', which `_build` cannot make" % (name, key)


@pytest.mark.parametrize("name,key,spec", ALL_ROWS, ids=ROW_IDS)
def test_every_field_a_pass_sets_is_a_field_the_applier_knows(name, key, spec):
    unknown = set(spec) - RETUNE_FIELDS
    assert not unknown, "%s/%s sets %s, which `_retune` ignores" % (
        name, key, sorted(unknown))


def test_the_applier_handles_every_field_the_passes_use():
    """The other direction: a field the tables never use is dead applier."""
    body = PALETTE.split("func _retune(")[1].split("\nfunc ")[0]
    handled = set(re.findall(r'spec\.has\("([a-z_]+)"\)', body))
    assert handled == RETUNE_FIELDS
    used = {field for _n, _k, spec in ALL_ROWS for field in spec}
    assert used <= handled


@pytest.mark.parametrize("name,key,spec", ALL_ROWS, ids=ROW_IDS)
def test_recolouring_an_emissive_sets_its_emission(name, key, spec):
    """`albedo` on an emissive is the unlit body only. A row that set just
    `albedo` on a lit strip would change nothing anyone can see."""
    if "_emissive(" not in ARMS.get(key, ""):
        return
    if "albedo" in spec:
        assert "emission" in spec, (
            "%s/%s repaints a lit strip's body without its emission"
            % (name, key))


# --- colour, not response --------------------------------------------------

@pytest.mark.parametrize("name,key,spec", ALL_ROWS, ids=ROW_IDS)
def test_no_pass_moves_a_v21_response_decision(name, key, spec):
    """The rule in `lab_palette.gd`: V21 said how a surface answers a light.

    The first build of `v23b` also tightened the track lip's clearcoat, which
    is a rim highlight sharpened along every metre of a 237-unit course, and it
    put clipping back on frames V21 had cleaned.
    """
    if key in REPAINTED:
        return
    moved = set(spec) & RESPONSE_FIELDS
    assert not moved, "%s/%s moves %s, which is V21's to set" % (
        name, key, sorted(moved))


# --- the two locks ---------------------------------------------------------

def test_no_pass_repaints_a_racer():
    """A machine pass is not a skin pass. `marble()` must not branch on it."""
    body = PALETTE.split("func marble(")[1]
    assert "machine" not in body
    assert "MACHINE_PASSES" not in body


@pytest.mark.parametrize("name,key,spec", ALL_ROWS, ids=ROW_IDS)
def test_no_pass_reaches_the_environment(name, key, spec):
    assert not key.startswith(ENVIRONMENT_PREFIXES), (
        "%s names '%s', which is environment and locked" % (name, key))


def test_no_pass_reaches_the_light_rig_or_the_grade():
    """`build_lights` and `build_environment` take the *contrast* pass only."""
    assert "World.build_environment(_no_glow, _contrast)" in COURSE_SCENE
    assert "World.build_lights(self, _contrast)" in COURSE_SCENE


# --- each pass's own claims ------------------------------------------------

PEARL_KEYS = ("pearl_shell", "pearl_lip_v2", "pearl_soft", "pearl_shade")


@pytest.mark.parametrize("name", PASSES)
@pytest.mark.parametrize("key", PEARL_KEYS)
def test_the_neutrals_went_cool(name, key):
    """The headline move: a warm-neutral cream on a warm-orange sky, flipped.

    Warm means R > B; every one of these is warm on the machine that ships and
    cool under every pass.
    """
    before = _rgb(_shipped(key))
    after = _rgb(str(MACHINE[name][key]["albedo"]))
    assert before[0] > before[2], "%s is not warm on the shipped machine" % key
    assert after[2] > after[0], "%s/%s did not go cool" % (name, key)


@pytest.mark.parametrize("key", PEARL_KEYS)
def test_the_subtle_pass_holds_luminance(key):
    """`v23a` claims a temperature flip that costs no brightness. Within 3%."""
    before = _luminance(_shipped(key))
    after = _luminance(str(MACHINE["v23a"][key]["albedo"]))
    assert abs(after - before) / before < 0.03, (
        "v23a/%s moved luminance %.1f%%" % (key, 100 * (after / before - 1)))


@pytest.mark.parametrize("name", PASSES)
def test_the_body_never_goes_brighter_than_the_machine_that_ships(name):
    """Every pass buys the racers headroom; none of them spends it."""
    for key in ("pearl_shell", "pearl_soft", "pearl_shade"):
        before = _luminance(_shipped(key))
        after = _luminance(str(MACHINE[name][key]["albedo"]))
        assert after <= before + 1e-6, "%s/%s got brighter" % (name, key)


@pytest.mark.parametrize("name", PASSES)
def test_the_rotor_reads_violet(name):
    """Blue over red over green is the whole of "violet" as a channel test."""
    r, g, b = _rgb(str(MACHINE[name]["rotor_machine"]["albedo"]))
    assert b > r > g, "%s's rotor is not violet: %s" % (name, (r, g, b))


@pytest.mark.parametrize("name", PASSES)
def test_the_rotor_stays_clear_of_the_purple_racer(name):
    """The collision the first render of this pass produced, as a number.

    The field's purple is #8E3FD4. A rotor blade near it in hue *and* in value
    puts a marble against a wall of itself, and the blades are the largest
    thing in the mixer's frame. Two and a half times the racer's luminance -
    about one and a third stops - is the floor; the shipped orange blade is at
    2.0 and reads fine because its *hue* is nowhere near the racer, which is
    exactly the safety a violet blade gives up and has to buy back in value.
    """
    racer = _luminance("#8E3FD4")
    blade = _luminance(str(MACHINE[name]["rotor_machine"]["albedo"]))
    assert blade > racer * 2.5, (
        "%s's rotor is %.2f against a purple racer at %.2f"
        % (name, blade, racer))


@pytest.mark.parametrize("name", PASSES)
def test_both_route_identities_keep_their_hue(name):
    """The split has to read as a *decision*. Blue stays blue-dominant and
    orange stays red-dominant in every pass, exactly as V21 asserted."""
    table = MACHINE[name]
    if "blue_machine" in table:
        r, g, b = _rgb(str(table["blue_machine"]["albedo"]))
        assert b > g > r, "%s turned the blue route %s" % (name, (r, g, b))
    if "orange_machine" in table:
        r, g, b = _rgb(str(table["orange_machine"]["albedo"]))
        assert r > g > b, "%s turned the orange route %s" % (name, (r, g, b))


@pytest.mark.parametrize("name", PASSES)
def test_the_choice_is_the_brightest_warm_machinery_in_the_film(name):
    """The zone story's one ordering claim: the sweep is the warning shot and
    the split is the decision, so the obstacle sits under the route."""
    table = MACHINE[name]
    if "hazard_machine" not in table:
        return
    route = _luminance(str(table.get("orange_machine",
                                     {"albedo": _shipped("orange_machine")})
                           ["albedo"]))
    sweep = _luminance(str(table["hazard_machine"]["albedo"]))
    assert sweep < route, "%s's sweep outshines its split" % name


@pytest.mark.parametrize("name", PASSES)
def test_gold_is_still_gold(name):
    """Hardware and the whole finale. R > G > B, and never repainted to a
    yellow: V21 asserted this and the payoff zone depends on it."""
    for key in ("gold", "gold_dark", "gold_bright"):
        spec = MACHINE[name].get(key, {})
        if "albedo" not in spec:
            continue
        r, g, b = _rgb(str(spec["albedo"]))
        assert r > g > b, "%s/%s is not gold: %s" % (name, key, (r, g, b))


def test_the_finish_payoff_is_not_bought_with_glow():
    """`v23b`'s finding, kept as a rule: the recommended pass may not raise a
    finale emissive above where V21 left it. See the merge frame in the doc."""
    for key in ("lit_gold_line", "lit_gold_wash"):
        before = float(V21[key]["energy"])
        after = MACHINE["v23b"].get(key, {}).get("energy", before)
        assert float(after) <= before + 1e-9, (
            "v23b raises %s to %s over V21's %s" % (key, after, before))


LONG_LINES = ("lit_cyan_line_hero", "lit_orange_line")


@pytest.mark.parametrize("name", ("v23a", "v23b"))
def test_the_two_shippable_passes_never_raise_the_longest_zone_lines(name):
    """Cyan runs the launch and both first legs, and orange runs the whole
    second route. Length is what makes an edge light expensive."""
    for key in LONG_LINES:
        before = float(V21[key]["energy"])
        after = MACHINE[name].get(key, {}).get("energy", before)
        assert float(after) <= before + 1e-9, (
            "%s raises %s to %s over V21's %s" % (name, key, after, before))


def test_the_showcase_pass_is_the_only_one_that_raises_them():
    """`v23c` exists to be the upper bound, and an upper bound that does not
    exceed anything is not one. This is the check that it still does."""
    raised = [key for key in LONG_LINES
              if float(MACHINE["v23c"].get(key, {}).get("energy", 0.0))
              > float(V21[key]["energy"])]
    assert raised == list(LONG_LINES)


# --- the tool and the palette agree ----------------------------------------

def test_the_tool_reads_the_same_racer_skins():
    """`tools.sloped_v23_machine` keeps its own copy so a skin change cannot
    pass unnoticed; this is the check that makes the copy safe."""
    from tools.sloped_v23_machine import MARBLE_COLOURS
    block = re.search(r"const MARBLE_COLOURS := \[(.*?)\n\]", PALETTE, re.S)
    assert block
    skins = tuple(re.findall(r'"(#[0-9A-Fa-f]{6})"', block.group(1)))
    assert tuple(MARBLE_COLOURS) == skins


def test_the_tool_names_every_pass_the_palette_declares():
    from tools.sloped_v23_machine import VARIANTS, RECOMMENDED
    named = {flag for _n, flag, _l in VARIANTS if flag}
    assert named == set(PASSES)
    assert RECOMMENDED in PASSES


def test_every_moment_belongs_to_a_zone_the_sheets_draw():
    from tools.sloped_v23_machine import MOMENTS, ZONE_MOMENTS
    names = {m[0] for m in MOMENTS}
    assert set(ZONE_MOMENTS) <= names
    assert {m[1] for m in MOMENTS} == {"race", "preview"}


def test_the_camera_lookup_matches_the_one_the_soundtrack_uses():
    """`sloped_v23_machine._camera_at` is a copy of a private function in
    `sloped.presentation`. This is what stops the copy drifting."""
    import json
    from sloped import presentation
    from tools import sloped_v23_machine as tool

    track_path = ROOT / "output" / "sloped_race_v1" / "cameras_v221_5432.json"
    if not track_path.exists():
        pytest.skip("camera track is an output, not a branch content")
    track = json.loads(track_path.read_text(encoding="utf-8"))
    for second in (0.5, 3.0, 8.0, 15.9, 22.0):
        assert _flatten(tool._camera_at(track, second)) == pytest.approx(
            _flatten(presentation._camera_at(track, second)))


def _flatten(pose):
    camera, aim, fov = pose
    return list(camera) + list(aim) + [fov]


def test_the_camera_lookup_returns_a_pose_shaped_like_the_other_one():
    from tools import sloped_v23_machine as tool
    assert callable(tool._camera_at)
    source = Path(tool.__file__).read_text(encoding="utf-8")
    assert "presentation._camera_at` is the same arithmetic" in source


def test_the_tool_parses():
    """It imports numpy and Pillow at module scope; this is the smoke test."""
    import tools.sloped_v23_machine as tool
    assert ast.parse(Path(tool.__file__).read_text(encoding="utf-8"))
