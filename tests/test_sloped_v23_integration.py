"""V23 integration: two independent dials over a race that did not change.

The two source labs each answered one question in isolation - which world, and
which machine colours. Integrating them is a third question neither could ask:
do they stay independent, and does the film they produce together still contain
the race V22.1 delivered?

So this file asserts three kinds of thing.

* **Independence.** `aurora_valley` names world surfaces, `v23b` names machine
  surfaces, and the two sets do not intersect. Neither switch reaches the
  other's fields, and neither is a default.
* **Gating.** V22.1 renders exactly what it rendered before V23 existed. The
  environment default is still `alpine_neon`, the machine default is still the
  shipped machine, and the strings that make V23 what it is live in one module.
* **The locked race.** Same seed, same replay, same solved camera track, same
  edit windows, same cue policy, same runtime band. V23 is a repaint, and a
  repaint that moved a cut or a marble would not be one.

The environment system's own rules - GEOMETRY IS NOT THEME, null erases, delta
inheritance, the V21 overlay composes - are covered in
`tests/test_sloped_environment.py`; what is added here is that the *new* profile
obeys them too, including that it cannot reach a terrain shape field.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import v23

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PROFILES = GODOT / "assets" / "marble_machine" / "environment" / "profiles"
AURORA_JSON = PROFILES / "aurora_valley.json"
PALETTE_GD = GODOT / "assets" / "marble_machine" / "lab_palette.gd"
COURSE_SCENE_GD = GODOT / "scripts" / "course_scene.gd"
BUILDER_GD = (GODOT / "assets" / "marble_machine" / "environment"
              / "environment_builder.gd")

PALETTE = PALETTE_GD.read_text(encoding="utf-8")
COURSE_SCENE = COURSE_SCENE_GD.read_text(encoding="utf-8")
BUILDER = BUILDER_GD.read_text(encoding="utf-8")


def _tool(name: str):
    """Load one of the two entry points by path; neither is an importable module."""
    spec = importlib.util.spec_from_file_location(
        "_v23_" + name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _machine_keys(name: str) -> set[str]:
    """The surface keys one `MACHINE_PASSES` entry names."""
    block = re.search(r"const MACHINE_PASSES := \{(.*?)\n\}\n", PALETTE, re.S)
    assert block, "MACHINE_PASSES is not declared in lab_palette.gd"
    body = block.group(1)
    entry = re.search(r'"%s":\s*\{' % re.escape(name), body)
    assert entry, "no machine pass named %r" % name
    start = entry.end() - 1
    depth = 0
    for index in range(start, len(body)):
        if body[index] == "{":
            depth += 1
        elif body[index] == "}":
            depth -= 1
            if depth == 0:
                break
    return set(re.findall(r'^\t\t"([a-z0-9_]+)"\s*:', body[start:index + 1],
                          re.M))


def _lstar(hexcode: str) -> float:
    red, green, blue = (int(hexcode[i:i + 2], 16) / 255 for i in (1, 3, 5))

    def linear(channel: float) -> float:
        return (channel / 12.92 if channel <= 0.04045
                else ((channel + 0.055) / 1.055) ** 2.4)

    y = 0.2126 * linear(red) + 0.7152 * linear(green) + 0.0722 * linear(blue)
    return 116 * (y ** (1 / 3)) - 16 if y > 0.008856 else 903.3 * y


# --- the profile is registered and valid -----------------------------------


def test_aurora_is_registered():
    index = json.loads((PROFILES / "index.json").read_text(encoding="utf-8"))
    assert "aurora_valley" in index["profiles"]
    assert "aurora_valley" in env.ids()
    assert env.default_id() == "alpine_neon", (
        "aurora must not become the registry default; every scene that does "
        "not ask for a theme still renders the shipped world")


def test_aurora_resolves_without_complaint():
    assert env.validate(env.resolve("aurora_valley")) == []


def test_aurora_is_a_delta_over_the_shipped_world():
    """Inheritance, not a copy - so a fix to the shipped world reaches it."""
    raw = json.loads(AURORA_JSON.read_text(encoding="utf-8"))
    assert raw["extends"] == "alpine_neon"
    # A field it never mentions still arrives from the parent.
    assert "ssr" not in raw
    assert (env.resolve("aurora_valley")["ssr"]["max_steps"]
            == env.resolve("alpine_neon")["ssr"]["max_steps"])


# --- GEOMETRY IS NOT THEME -------------------------------------------------


def test_aurora_sets_no_terrain_shape_field():
    raw = json.loads(AURORA_JSON.read_text(encoding="utf-8"))
    terrain = raw.get("terrain", {})
    for field in env.SHAPE_FIELDS:
        assert field not in terrain, (
            "aurora_valley.terrain.%s is landform, not theme" % field)


@pytest.mark.parametrize("field", ["gorge_depth", "grade", "top_y", "cell"])
def test_a_shape_field_in_aurora_is_rejected(field):
    """The rule is enforced, not merely obeyed."""
    raw = json.loads(AURORA_JSON.read_text(encoding="utf-8"))
    raw.setdefault("terrain", {})[field] = 1.0
    problems = env.validate(raw)
    assert any(field in problem for problem in problems), (
        "a profile that set terrain.%s should be refused" % field)


def test_the_gorge_mist_reads_the_landform_and_never_writes_it():
    """The one V23 feature that is placed *against* the course's own shape.

    It carries its own copies of the gorge's coordinates under names that are
    not shape fields, so the validator's rule still holds and nothing it says
    can reach `course_terrain.height`.
    """
    raw = json.loads(AURORA_JSON.read_text(encoding="utf-8"))
    mist = raw["backdrop"]["mist"]
    assert "at_x" in mist and "at_z" in mist
    for field in env.SHAPE_FIELDS:
        assert field not in mist


# --- the two dials are independent ----------------------------------------


def test_the_environment_and_the_machine_name_disjoint_surfaces():
    """**The architectural rule, as an assertion.**

    An environment profile owns the world's surfaces and a machine pass owns
    the machine's. They are applied one after the other onto the same palette,
    so if they ever named the same key one would silently win and a zone would
    lose its identity to a sky. The fix for an overlap is to move the key, not
    to reorder the two.
    """
    world = set(json.loads(AURORA_JSON.read_text(encoding="utf-8"))["palette"])
    machine = _machine_keys(v23.MACHINE)
    assert world, "aurora names no surfaces"
    assert machine, "%s names no surfaces" % v23.MACHINE
    assert not (world & machine), (
        "environment and machine both name: %s" % sorted(world & machine))


def test_neither_switch_reaches_the_other_in_the_scene():
    assert 'var _machine := ""' in COURSE_SCENE
    assert 'var _environment_id := ""' in COURSE_SCENE
    # The machine pass is a palette constructor argument; the environment is an
    # override table applied after. Two doors, so neither can shadow the other.
    assert 'Palette.new("tower", _contrast, _machine)' in COURSE_SCENE
    assert "EnvBuilder.apply_palette(_palette, _environment)" in COURSE_SCENE
    for call in ("World.build_environment(", "World.build_lights("):
        start = COURSE_SCENE.index(call)
        args = COURSE_SCENE[start:COURSE_SCENE.index(")", start)]
        assert "_machine" not in args, (
            "%s takes the machine pass; a pass must not light the world" % call)


def test_the_palette_applies_contrast_then_machine_then_environment():
    body = PALETTE[PALETTE.index("func get_material("):]
    body = body[:body.index("\n\n\n")]
    assert body.index("V21_RETUNE.has(key)") < body.index("MACHINE_PASSES.has")
    assert body.index("MACHINE_PASSES.has") < body.index("_environment.has(key)")


# --- edition gating --------------------------------------------------------


def test_v23_selects_aurora_and_v23b():
    assert v23.ENVIRONMENT == "aurora_valley"
    assert v23.MACHINE == "v23b"
    assert "--environment=aurora_valley" in v23.SCENE_FLAGS
    assert "--machine=v23b" in v23.SCENE_FLAGS


def test_the_two_strings_are_written_once():
    """One source of truth: the tools import them rather than repeat them.

    Comments are stripped first. Both files *describe* what V23 selects, and
    they should - what must not happen is a second executable copy, because a
    film could then be rendered under one world and cut against another with
    nothing to say so.
    """
    for tool in ("sloped_v22.py", "sloped_short.py"):
        text = (ROOT / "tools" / tool).read_text(encoding="utf-8")
        code = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
        assert "aurora_valley" not in code, (
            "%s spells the environment out; it should use sloped.v23" % tool)
        assert '"v23b"' not in code, (
            "%s spells the machine pass out; it should use sloped.v23" % tool)


def test_the_render_edition_carries_the_flags():
    tool = _tool("sloped_v22")
    assert tool.EDITIONS["v23"]["scene"] == v23.SCENE_FLAGS
    assert tool.DEFAULT_EDITION == "v22", "V23 must not become the default"


def test_no_older_edition_gained_a_v23_flag():
    tool = _tool("sloped_v22")
    for name, entry in tool.EDITIONS.items():
        if name == "v23":
            continue
        for flag in entry.get("scene", ()):
            assert "--environment=" not in flag
            assert "--machine=" not in flag


def test_the_defaults_are_untouched():
    """Neither dial is on for a caller that does not ask."""
    assert env.default_id() == "alpine_neon"
    assert 'var _machine := ""' in COURSE_SCENE
    assert 'var _environment_id := ""' in COURSE_SCENE


# --- V22.1 is locked -------------------------------------------------------


def test_v23_reuses_v221s_solved_tracks_rather_than_copies():
    """**Identity by construction, not by comparison.**

    The strongest available statement that the camera track did not move is
    that there is only one file. A V23 that solved its own track would be
    asserting the solver is deterministic; this way there is nothing to drift.
    """
    tool = _tool("sloped_v22")
    for key in ("race_track", "preview_track"):
        assert tool.EDITIONS["v23"][key] == tool.EDITIONS["v221"][key], (
            "V23's %s must be V22.1's own file" % key)


def test_v23_shares_v221s_edit_and_cues():
    short = _tool("sloped_short")
    before, after = short.EDITIONS["v221"], short.EDITIONS["v23"]
    assert before["cuts"] == after["cuts"] == ()
    assert before["cues"] == after["cues"] == "v221"
    assert before["runtime"] == after["runtime"]
    assert before["track"] == after["track"], "the Short must read V22.1's track"


def test_v23_writes_its_own_files_and_overwrites_nothing_of_v221():
    short = _tool("sloped_short")
    before, after = short.EDITIONS["v221"], short.EDITIONS["v23"]
    for key in ("video", "visual", "silent", "master", "preview"):
        assert before[key] != after[key], "V23 would overwrite V22.1's %s" % key


def test_the_seed_did_not_move():
    text = (ROOT / "tools" / "sloped_v22.py").read_text(encoding="utf-8")
    assert '"--seed", type=int, default=5432' in text
    text = (ROOT / "tools" / "sloped_short.py").read_text(encoding="utf-8")
    assert '"--seed", type=int, default=5432' in text


# --- the render pipeline is configured as one ------------------------------


def test_the_short_edition_points_at_the_v23_masters():
    short = _tool("sloped_short")
    entry = short.EDITIONS["v23"]
    assert entry["master"].replace("\\", "/").endswith("v23/race_master.mp4")
    assert entry["preview"].replace("\\", "/").endswith("v23/preview_master.mp4")


def test_the_builder_additions_are_off_by_default():
    """Every V23 world feature draws nothing for a profile that is silent.

    This is what lets the four shipped profiles keep rendering their committed
    frames from a branch that added five new builders.
    """
    for guard in ('cfg.get("count", 0)', 'cfg.get("tiers", [])',
                  'cfg.get("decks", 0)'):
        assert guard in BUILDER
    # And the two new renderer fields are not written at all unless a profile
    # names them. Writing what is believed to be the engine default is a guess:
    # doing that with `sun_curve` moved two of three V22.1 probe frames.
    assert 'if sky_cfg.has("sun_curve"):' in BUILDER
    assert 'if grade.has("ambient_colour"):' in BUILDER


@pytest.mark.parametrize("profile_id", ["alpine_neon", "canyon_dusk",
                                        "glow_valley", "mono_readability"])
def test_the_shipped_profiles_ask_for_no_v23_feature(profile_id):
    raw = json.loads((PROFILES / (profile_id + ".json")).read_text(
        encoding="utf-8"))
    backdrop = raw.get("backdrop", {})
    for feature in ("crest_lines", "aurora", "mist", "ridge_range"):
        assert feature not in backdrop, (
            "%s asks for %s, which would change its committed frames"
            % (profile_id, feature))
    assert "ambient_colour" not in raw.get("grade", {})
    assert "sun_curve" not in raw.get("sky", {})


# --- what the profile claims about the look --------------------------------


def test_the_fork_is_no_longer_lit_white():
    """The lab's headline environment finding, as a regression test.

    V22.1 lights `split` - the one node on this course a marble chooses at - at
    #EAF7FF, which is the one colour that says nothing. V23 puts warm energy
    where the decision is.
    """
    shipped = env.resolve("alpine_neon")["zones"]["split"]["colour"]
    aurora = env.resolve("aurora_valley")["zones"]["split"]["colour"]
    assert shipped.upper() == "#EAF7FF"
    red, _, blue = (int(aurora[i:i + 2], 16) for i in (1, 3, 5))
    assert red > blue + 60, "the fork practical should be warm, got %s" % aurora


def test_the_warm_half_of_the_world_is_spent_at_the_choice_and_the_finish():
    zones = env.resolve("aurora_valley")["zones"]
    warm = {name for name, spec in zones.items()
            if int(spec["colour"][1:3], 16) > int(spec["colour"][5:7], 16) + 40}
    assert warm == {"obstacle", "split", "merge", "finish"}, sorted(warm)
    for name in ("start", "mix"):
        spec = zones[name]
        assert int(spec["colour"][5:7], 16) > int(spec["colour"][1:3], 16), (
            "%s should stay cool" % name)


def test_the_glow_took_collectors_discipline_rather_than_auroras_own():
    """The borrow that is a number rather than a look.

    Aurora ran 1.10 / 0.22 / 1.30 in the lab and clipped 0.80% of its worst
    frame against Collector Canyon's 0.69 at 0.85 / 0.16 / 1.40. V23 combines a
    brighter machine with a darker world, so it takes the lower of the two.
    """
    glow = env.resolve("aurora_valley")["glow"]
    assert glow["intensity"] <= 0.85
    assert glow["bloom"] <= 0.16
    assert glow["hdr_threshold"] >= 1.40


def test_the_distant_ranges_are_four_separated_values():
    """The lab measured the shipped three within about 4 L* of one another."""
    palette = env.resolve("aurora_valley")["palette"]
    keys = ["rock_soft_near", "rock_soft_mid", "rock_soft_far", "rock_soft_haze"]
    values = [_lstar(palette[key]["albedo"]) for key in keys]
    assert values == sorted(values), "the four steps must be monotonic"
    gaps = [later - earlier for earlier, later in zip(values, values[1:])]
    assert min(gaps) >= 4.0, "steps too close to read as recession: %s" % gaps


def test_the_near_ground_kept_collectors_value_discipline():
    """Lifted off the floor, and held below where it would compete.

    Two borrows pulling opposite ways, reconciled as a *compression*: Collector
    Canyon stays legible in the branch and merge frames where Aurora went dark,
    so the darkest ground values come up; and the machine has to stay the hero,
    so the lightest ones come down. The result is a narrower band than either,
    sitting off black - which is also the brief's "lower local contrast near
    track".
    """
    palette = env.resolve("aurora_valley")["palette"]
    slopes = [key for key in palette if key.startswith("slope_")]
    values = [_lstar(palette[key]["albedo"]) for key in slopes]
    assert min(values) >= 16.0, "the near ground floor is too close to black"
    assert max(values) <= 29.0, "a ground value that bright competes with the machine"
    assert max(values) - min(values) <= 12.0, (
        "local contrast near the track is wider than Collector's discipline")


def test_the_v21_overlay_still_composes_over_aurora():
    """It composes - and it no longer overwrites what Aurora authored.

    The overlay is inherited from `alpine_neon`, whose numbers were tuned for a
    bright sky. Left alone it put the shipped glow and grade back over a world
    built to be dark. Aurora erases those three sections with JSON null and
    keeps the part of the pass that is about the renderer rather than the look.
    """
    plain = env.resolve("aurora_valley")
    passed = env.resolve("aurora_valley", "v21")
    assert passed["glow"] == plain["glow"]
    assert passed["grade"] == plain["grade"]
    assert passed["lights"] == plain["lights"]
    # ...and the readability half of the pass does still arrive.
    assert passed["ssao"]["intensity"] > plain["ssao"]["intensity"]
    # The shipped profile is untouched by any of this.
    assert (env.resolve("alpine_neon", "v21")["glow"]["intensity"]
            != env.resolve("alpine_neon")["glow"]["intensity"])
