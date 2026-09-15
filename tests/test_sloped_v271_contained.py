"""What V27.1 must be true of: one field changed, and a corrected ruler.

V27.1 is a finish correction over V27's recommended stage. Almost everything
here is an assertion that something did *not* move - the same shape V27's own
suite has, for the same reason - plus a small group that checks the two things
this pass actually adds: a corrected separation instrument, and a render-only
country skin.

Organised by what could go wrong:

* **`contained_hall` is untouched.** Its profile file, its resolved dictionary
  and its render are V27's, so every proof in `docs/sloped_race_v27_contained.md`
  still reproduces. A pass that corrects a measurement by editing the thing it
  measured has measured nothing.
* **the delta is one field.** `contained_hall_v271` resolves to `contained_hall`
  with exactly one leaf different, and that leaf is the finish bay's landing
  pad. No geometry, no new material key, no light, no grade, no camera.
* **the film is V24's.** Seed, replay, camera track, edit map and the twelve
  moment seconds are V27's own, re-derived from the delivered track.
* **the corrected instrument is a correction.** `machine_mask` is an occlusion
  test with a stated threshold; it agrees with V27's segmentation on the
  control, where the two cannot differ, and disagrees on the contained case,
  where V27's own §19 number came from.
* **the country skin is render-only.** One appearance, reachable only through
  `--flag-racer=`, with the shipped default untouched; and the key the Python
  side hands Godot is the key Godot knows, which the first run of the probe got
  wrong and photographed five sheets of plain marbles for.

The replay and the solved track are generated output and not in the branch, so
the tests that need them skip rather than fail. So do the renders, which need
`$GODOT_BIN`.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from sloped import environment as env
from sloped import v24_payoff, v26
from sloped import v27_contained as v27
from sloped import v271_finish as v271

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "godot"
PROFILES = GODOT / "assets" / "marble_machine" / "environment" / "profiles"
RACER_GD = GODOT / "assets" / "marble_machine" / "racers" / "racer_visual.gd"
SCENE_GD = GODOT / "scripts" / "sloped_race_scene.gd"
GENERATOR = ROOT / "tools" / "sloped_v271_profiles.py"
LAB = ROOT / "tools" / "sloped_v271_finish.py"

OUT = ROOT / "output" / "sloped_race_v1"
TRACK = OUT / f"cameras_v24_{v27.SEED}.json"
REPLAY = OUT / f"race_{v27.SEED}.json"
CONTRACT = OUT / f"start_contract_{v27.SEED}.json"

#: The four files this pass writes. `contained_hall` is not among them.
NEW_PROFILES = ("contained_hall_v271", "_marker_v271", "_probe_v271",
                "_probe_v271_pad")

#: Everything V27 and earlier shipped. None of it may change.
FROZEN = (
    "alpine_neon", "canyon_dusk", "glow_valley", "mono_readability",
    "aurora_valley", "aurora_valley_v25", "aurora_valley_v25a",
    "aurora_valley_v25b", "aurora_valley_v25c", "aurora_valley_v251",
    "aurora_valley_v252", "aurora_valley_v26", "contained_base",
    "contained_hall", "diorama_chamber", "industrial_chamber",
    "_marker_v27a", "_marker_v27b", "_marker_v27c", "_marker_v27_control",
)


def _read(name: str) -> dict:
    with open(PROFILES / f"{name}.json", encoding="utf-8") as handle:
        return json.load(handle)


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


# --- the profiles exist and are data ----------------------------------------


def test_the_four_profiles_exist_and_are_indexed():
    index = _read("index")["profiles"]
    for name in NEW_PROFILES:
        assert (PROFILES / f"{name}.json").is_file(), f"{name} is not written"
        assert name in index, f"{name} is not in index.json"


def test_the_generator_is_a_no_op():
    """Re-running the writer must change nothing, or the files have drifted."""
    done = subprocess.run([sys.executable, str(GENERATOR)], cwd=str(ROOT),
                          capture_output=True, text=True, encoding="utf-8")
    assert done.returncode == 0, done.stderr
    assert "up to date" in done.stdout, done.stdout


def test_every_new_profile_resolves():
    for name in NEW_PROFILES:
        resolved = env.resolve(name)
        assert resolved["id"] == name
        assert not env.validate(resolved), env.validate(resolved)


def test_contained_hall_is_not_overwritten():
    """V27's proofs are quoted against this file. It may not move."""
    hall = _read("contained_hall")
    assert hall["id"] == "contained_hall"
    assert hall["extends"] == "contained_base"
    pad = hall["world"]["deck"]["pads"][0]
    assert pad["material"] == "hall_deck", (
        "contained_hall's own finish pad changed - V27's numbers no longer "
        "reproduce from it")


def test_no_frozen_profile_gained_a_v271_section():
    for name in FROZEN:
        raw = (PROFILES / f"{name}.json").read_text(encoding="utf-8")
        assert "v271" not in raw, f"{name} names V27.1"
        assert "_probe" not in raw, f"{name} names a V27.1 probe"


# --- the delta is one field -------------------------------------------------


def test_the_delta_is_exactly_one_leaf():
    """The whole of V27.1, stated as a diff of resolved dictionaries."""
    before = _leaves(env.resolve("contained_hall"))
    after = _leaves(env.resolve(v271.PROFILE))
    moved = {key: (before.get(key), after[key])
             for key in after
             if key not in ("id", "title", "summary", "extends")
             and before.get(key) != after[key]}
    gone = [key for key in before if key not in after]
    assert not gone, f"V27.1 dropped {gone}"
    assert list(moved) == ["world.deck.pads[0].material"], moved
    assert moved["world.deck.pads[0].material"] == ("hall_deck",
                                                    "hall_deck_dark")


def test_the_delta_names_no_new_material_key():
    """Part G: no new materials. The pad's new key is one the hall already had."""
    hall = env.resolve("contained_hall")
    keys = set(hall.get("palette", {}))
    corrected = _read(v271.PROFILE)
    assert "palette" not in corrected, "V27.1 declares a palette of its own"
    assert corrected["world"]["deck"]["pads"][0]["material"] in keys


def test_the_delta_adds_no_geometry():
    """Same pads, same rings, same bands, same pylons, same bays."""
    before = env.resolve("contained_hall")["world"]
    after = env.resolve(v271.PROFILE)["world"]
    assert len(before["deck"]["pads"]) == len(after["deck"]["pads"]) == 1
    assert before["deck"]["rings"] == after["deck"]["rings"]
    assert before["shell"] == after["shell"]
    assert before["pylons"] == after["pylons"]
    assert before["bays"] == after["bays"]


def test_the_delta_touches_no_light_grade_sky_or_fog():
    before = env.resolve("contained_hall")
    after = env.resolve(v271.PROFILE)
    for section in ("lights", "grade", "sky", "fog", "terrain", "dressing",
                    "backdrop"):
        assert before.get(section) == after.get(section), section


def test_the_pad_is_still_where_and_what_it_was():
    """Only its value changed: not its size, place, bearing or guards."""
    before = env.resolve("contained_hall")["world"]["deck"]["pads"][0]
    after = env.resolve(v271.PROFILE)["world"]["deck"]["pads"][0]
    for field in ("at", "size", "sink", "bearing", "clearance", "keepout"):
        assert before[field] == after[field], field


# --- nothing about the film moved -------------------------------------------


def test_the_seed_and_the_film_are_v26s():
    assert v271.SEED == v27.SEED == 5432
    assert v271.CONTROL == v26.ENVIRONMENT
    assert v271.FLAG_RACER == v26.WINNER
    assert v271.MOMENTS is v27.MOMENTS
    assert (v271.WIDTH, v271.HEIGHT) == (1080, 1920)
    assert v271.FPS == 60


def test_the_lab_renders_v24s_own_flags():
    """The machine, racer and board flags are V27's, unchanged."""
    source = LAB.read_text(encoding="utf-8")
    assert "lab.FIXED_FLAGS" in source
    assert "--machine=" not in source, "V27.1 names a machine of its own"
    assert "--layout=" not in source, "V27.1 names a layout of its own"


def test_the_lab_writes_no_replay_and_no_track():
    source = LAB.read_text(encoding="utf-8")
    for path in ("REPLAY", "TRACK", "START_CONTRACT"):
        assert f"{path} = lab.{path}" in source
    assert not re.search(r'open\(\s*(REPLAY|TRACK|START_CONTRACT)[^)]*"w"',
                         source), "the lab opens an input for writing"


def test_the_finish_moments_are_three_of_v27s_twelve():
    for key in v271.FINISH:
        assert v27.moment(key) is not None
    assert v271.FINISH == ("final_approach", "winner", "payoff")


@pytest.mark.skipif(not TRACK.is_file(), reason="solved track not in branch")
def test_the_track_is_read_on_its_own_clock():
    """The solved track is keyed by replay seconds, not output seconds.

    The survey's first version matched `Moment.second` against `frame[0]` and
    put every finish camera three seconds from where the picture was taken.
    The track's own range is the proof: it starts at the hook's replay second
    and ends past the film's 20.117 s runtime.
    """
    with open(TRACK, encoding="utf-8") as handle:
        track = json.load(handle)
    frames = v271.frames_of(track)
    assert frames[0][0] == pytest.approx(v27.moment("frame0").replay, abs=1e-6)
    assert frames[-1][0] > 20.117
    for one in v27.MOMENTS:
        frame = v271.frame_at(frames, one.replay)
        assert abs(frame[0] - one.replay) < 0.05, one.key


# --- the corrected instrument -----------------------------------------------


def test_the_threshold_is_stated_and_on_the_plateau():
    assert 10.0 <= v271.DIFF_FLOOR <= 60.0


def test_machine_mask_is_an_occlusion_test():
    import numpy as np

    world = np.zeros((8, 8, 3), dtype=float)
    world[:, :] = (255, 60, 120)
    whole = world.copy()
    whole[2:6, 2:6] = (230, 222, 190)      # the cream chute over rose terrain
    machine = v271.machine_mask(whole, world)
    assert machine.sum() == 16
    assert machine[3, 3] and not machine[0, 0]


def test_v27s_segmentation_keeps_the_chute_and_the_correction_drops_it():
    """The bug, reproduced in eight by eight pixels.

    Cream's nearest neighbour among V27's four band hues is `terrain`'s rose,
    so over a rose landform the whole and world-only passes agree and the
    chute survives as background. Over V26's magenta near-field rock they
    disagree and it does not. That asymmetry is the 90-to-49 number.
    """
    import numpy as np

    chute = (230, 222, 190)
    for behind, band, kept in (((255, 60, 120), "terrain", True),
                               ((255, 0, 200), "structure", False)):
        world = np.zeros((8, 8, 3), dtype=float)
        world[:, :] = behind
        whole = world.copy()
        whole[2:6, 2:6] = chute
        old = v27.segment(whole, world)
        assert bool(old[band][3, 3]) is kept, band
        bands, machine = v271.background_mask(whole, world)
        assert machine[3, 3], "the corrected mask lost the chute"
        assert not bands[band][3, 3]


def test_separation_is_machine_minus_background():
    import numpy as np

    pixels = np.zeros((40, 40, 3), dtype=float)
    pixels[:20, :] = 255.0
    machine = np.zeros((40, 40), dtype=bool)
    machine[:20, :] = True
    background = ~machine
    assert v271.separation(pixels, machine, background) == pytest.approx(255.0)
    # Either population under 200 px is not a mean worth quoting.
    thin = np.zeros((40, 40), dtype=bool)
    thin[0, :4] = True
    assert v271.separation(pixels, thin, background) is None


def test_collar_pair_uses_the_shared_silhouette():
    """Two worlds, one machine: the fix for the coverage confound.

    Measured on its own silhouette a contained frame loses at the collar, and
    the reason is that V26's foreground rock hides four per cent of the frame's
    worth of machine - the dark, far, lower edge of it. Asking both worlds
    about the same pixels is the only fair form of the question.
    """
    import numpy as np

    pixels = np.zeros((200, 200, 3), dtype=float)
    pixels[60:140, 60:140] = 200.0
    a = np.zeros((200, 200), dtype=bool)
    a[60:140, 60:140] = True
    b = a.copy()
    b[60:80, 60:140] = False               # one world hides a strip of machine
    first, second = v271.collar_pair(pixels, a, ~a, pixels, b, ~b)
    assert first is not None and second is not None
    # Both worlds are asked about `b`'s silhouette, which is the smaller one,
    # so neither is scored on machine the other cannot show. The two answers
    # still differ, and should: the *ring* is each world's own background, and
    # here one world has a bright strip there that the other calls machine.
    # What the pairing removes is the silhouette confound, not the worlds.
    assert int((a & b).sum()) == int(b.sum())
    assert first != second


# --- the country skin is render-only ----------------------------------------


def test_the_flag_key_is_the_appearance_godot_knows():
    """The mismatch that photographed five sheets of the wrong thing.

    `FLAG.key` is handed straight to `--racers=`, so it has to be a member of
    `racer_visual.APPEARANCES`. It held a country name once, the scene did not
    recognise it, `sloped_race_scene` fell back to its default appearance, and
    the probe scored five renders of plain marbles without anything failing.
    """
    source = RACER_GD.read_text(encoding="utf-8")
    appearances = re.search(r"const APPEARANCES := \[(.*?)\]", source, re.S)
    assert appearances, "APPEARANCES is not a literal list any more"
    names = re.findall(r'"([^"]+)"', appearances.group(1))
    assert v271.FLAG.key in names, (
        f"{v271.FLAG.key!r} is not an appearance: {names}")
    flags = re.search(r"const FLAGS := \{(.*?)\n\}", source, re.S)
    assert flags and f'"{v271.FLAG.key}"' in flags.group(1)


def test_the_lab_fails_on_a_scene_push_error():
    """A push_error exits 0. The lab has to treat one as a failure."""
    source = LAB.read_text(encoding="utf-8")
    assert 'if "sloped_race_scene:" in line or "racer_visual:" in line:' in source
    assert "raise LabError" in source


def test_the_shipped_appearances_are_untouched():
    """`solid`, `ribbon`, `crescent` and `meridian` must still be first."""
    source = RACER_GD.read_text(encoding="utf-8")
    appearances = re.search(r"const APPEARANCES := \[(.*?)\]", source, re.S)
    names = re.findall(r'"([^"]+)"', appearances.group(1))
    assert names[:4] == ["solid", "ribbon", "crescent", "meridian"]
    assert "MARKER_TINT := 0.52" in source
    assert "const TEXTURE_WIDTH := 512" in source
    assert "const TEXTURE_HEIGHT := 256" in source


def test_a_flag_reaches_only_the_chosen_racer():
    """`appearance_for`'s contract, read off the source rather than run."""
    source = RACER_GD.read_text(encoding="utf-8")
    assert "return appearance if marble_id == flag_on else FLAG_FALLBACK" in source
    assert 'const FLAG_FALLBACK := "meridian"' in source


def test_the_default_render_has_no_flag():
    """`--flag-racer` defaults to none, so nothing shipped can reach a skin."""
    scene = SCENE_GD.read_text(encoding="utf-8")
    assert 'var _flag_racer := -1' in scene
    assert 'int(early.get("flag-racer", -1))' in scene
    assert 'const DEFAULT_RACERS := "solid"' in scene


def test_the_flag_axes_are_orthogonal():
    """The wheel has to sit in the white band, not over a stripe boundary."""
    band, emblem = v271.flag_axes()
    dot = sum(a * b for a, b in zip(band, emblem))
    assert abs(dot) < 0.01, dot
    for axis in (band, emblem):
        length = sum(v * v for v in axis) ** 0.5
        assert 0.98 < length < 1.02
        assert max(abs(v) for v in axis) < 0.99, "an axis is nearly aligned"


def test_the_flag_bands_are_equal_by_area():
    low, high = v271.band_edges()
    assert low == pytest.approx(-1.0 / 3.0)
    assert high == pytest.approx(1.0 / 3.0)


def test_the_probe_racer_is_the_winner():
    assert v271.FLAG_RACER == v24_payoff.WINNER_INDEX
    assert v24_payoff.winner_label(v271.FLAG_RACER) == "PURPLE"


def test_the_probe_moments_are_the_briefs_five():
    assert v271.FLAG_MOMENTS == ("frame0", "mixer", "obstacle",
                                 "fork_approach", "winner")
    for key in v271.FLAG_MOMENTS:
        assert v27.moment(key) is not None


# --- the payoff is V24's ----------------------------------------------------


def test_the_payoff_card_is_not_redesigned():
    card = v24_payoff.build()
    assert card.style == v24_payoff.RECOMMENDED
    assert card.label == "PURPLE"
    assert card.from_place == 6
    source = LAB.read_text(encoding="utf-8")
    assert "v24_payoff.build()" in source
    assert "v24_payoff.measured_contrast" in source


def test_the_payoff_threshold_is_stated():
    """Part C: the bar is V26's own number on V26's own frame, not a constant."""
    source = LAB.read_text(encoding="utf-8")
    assert "WCAG large text wants 3.0" in source
    measured = ROOT / "output" / "sloped_race_v1" / "v271_contained" / "payoff.json"
    if not measured.is_file():
        pytest.skip("payoff.json not measured in this tree")
    got = json.loads(measured.read_text(encoding="utf-8"))["worlds"]
    assert got["v271"]["worst"] >= got["v26"]["worst"], (
        "the card reads worse on the contained bay than on V26's")
    assert got["v271"]["worst"] >= 3.0


# --- the measured results, when this tree has them --------------------------


MEASURES = ROOT / "output" / "sloped_race_v1" / "v271_contained" / "measures.json"


@pytest.mark.skipif(not MEASURES.is_file(), reason="not measured in this tree")
def test_the_finish_clears_the_brief_target():
    got = json.loads(MEASURES.read_text(encoding="utf-8"))["worlds"]
    for key in v271.FINISH:
        value = got["v271"]["moments"][key]["separation"]
        assert value >= v271.TARGET, f"{key} is {value}, target {v271.TARGET}"


@pytest.mark.skipif(not MEASURES.is_file(), reason="not measured in this tree")
def test_the_correction_regresses_no_moment():
    got = json.loads(MEASURES.read_text(encoding="utf-8"))["worlds"]
    for one in v27.MOMENTS:
        before = got["v27"]["moments"][one.key]["separation"]
        after = got["v271"]["moments"][one.key]["separation"]
        assert after >= before - 0.05, f"{one.key}: {before} -> {after}"


@pytest.mark.skipif(not MEASURES.is_file(), reason="not measured in this tree")
def test_the_cost_is_within_two_per_cent_of_contained_hall():
    got = json.loads(MEASURES.read_text(encoding="utf-8"))
    cost = got.get("cost", {})
    if not {"v27", "v271"} <= set(cost):
        pytest.skip("cost not recorded")
    assert cost["v271"]["meshes"] == cost["v27"]["meshes"]
    assert cost["v271"]["triangles"] == cost["v27"]["triangles"]
    ratio = cost["v271"]["ms_per_frame"] / cost["v27"]["ms_per_frame"]
    assert 0.98 <= ratio <= 1.02, ratio


DELTA = ROOT / "output" / "sloped_race_v1" / "v271_contained" / "delta.json"


@pytest.mark.skipif(not DELTA.is_file(), reason="not measured in this tree")
def test_the_hook_and_the_start_are_byte_identical():
    """Part F: no finish fix may reach the opening."""
    got = json.loads(DELTA.read_text(encoding="utf-8"))
    for key in ("frame0", "mixer", "release", "descent"):
        assert got[key]["changed"] == 0.0, f"{key} moved: {got[key]}"


WINNER = ROOT / "output" / "sloped_race_v1" / "v271_contained" / "winner.json"


@pytest.mark.skipif(not WINNER.is_file(), reason="not measured in this tree")
def test_the_winner_is_on_screen_and_unoccluded_when_it_crosses():
    got = json.loads(WINNER.read_text(encoding="utf-8"))
    assert got["winner"] == v24_payoff.WINNER_INDEX
    for key in ("winner", "payoff"):
        where = got["moments"][key]["where"]
        assert where["on_screen"], f"the winner is off screen at {key}"
        row = got["moments"][key]["worlds"]["v271"]
        assert row["occluded"] == 0.0, f"something stands in front at {key}"
        assert row["delta_e"] >= 60.0, f"the winner is flat at {key}"


COUNTRY = ROOT / "output" / "sloped_race_v1" / "v271_contained" / "country.json"


@pytest.mark.skipif(not COUNTRY.is_file(), reason="not measured in this tree")
def test_the_country_probe_actually_rendered_a_flag():
    """A plain marble scores a spread too; two of three bands does not.

    This is the assertion that would have caught the fallback: a sheet of
    unskinned marbles reports 0 of 3 bands at every moment.
    """
    got = json.loads(COUNTRY.read_text(encoding="utf-8"))
    assert got["flag"] == v271.FLAG.key
    for key in v271.FLAG_MOMENTS:
        row = got["moments"][key]["worlds"]["v271"]
        assert row["bands"] >= 2, f"{key} shows {row['bands']} of 3 bands"


# --- render neutrality ------------------------------------------------------
#
# Godot-gated, exactly as V27's suite is: a render is not something a unit
# suite can require.


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
    return out, done.stdout or ""


def _digests(directory: Path) -> dict[str, str]:
    import hashlib

    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(directory.glob("*.png"))}


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_v26_and_contained_hall_still_render_what_they_rendered(tmp_path):
    """The reproducibility claim, taken as a hash rather than argued.

    Both worlds are rendered through the *same* `--at` list, because V27 found
    that a still is only comparable with one requested in the same list: the
    renderer accumulates between samples inside one process.
    """
    at = "0.000,9.600,17.517"
    control, _ = _render(tmp_path / "a", "aurora_valley_v26", at)
    hall, _ = _render(tmp_path / "a", "contained_hall", at)
    again_control, _ = _render(tmp_path / "b", "aurora_valley_v26", at)
    again_hall, _ = _render(tmp_path / "b", "contained_hall", at)
    assert _digests(control) == _digests(again_control)
    assert _digests(hall) == _digests(again_hall)
    assert _digests(control) != _digests(hall)


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_correction_changes_the_finish_and_not_the_hook(tmp_path):
    """The delta, as pixels: frame zero identical, the winner not."""
    at = "0.000,9.600,17.517"
    hall, _ = _render(tmp_path, "contained_hall", at)
    fixed, _ = _render(tmp_path, v271.PROFILE, at)
    before, after = _digests(hall), _digests(fixed)
    assert before["at_000.000.png"] == after["at_000.000.png"], (
        "the finish fix reached frame zero")
    assert before["at_017.517.png"] != after["at_017.517.png"], (
        "the finish fix did not reach the winner")


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_correction_builds_the_same_world_as_contained_hall(tmp_path):
    """Same census, same counts: a value change and not a build change."""
    _hall, before = _render(tmp_path, "contained_hall", "0.000")
    _fixed, after = _render(tmp_path, v271.PROFILE, "0.000")

    def census(stdout: str) -> str:
        for line in stdout.splitlines():
            if line.strip().startswith("world:"):
                return line.strip()
        return ""

    assert census(before), "the scene printed no world census"
    assert census(before) == census(after)


@pytest.mark.skipif(not CAN_RENDER, reason="no GODOT_BIN, replay or track")
def test_the_flag_reaches_one_racer_and_no_shipped_render(tmp_path):
    """Part E: render-only, and one marble of eight."""
    plain, _ = _render(tmp_path, v271.PROFILE, "0.000")
    flagged, _ = _render(
        tmp_path / "flag", v271.PROFILE, "0.000",
        extra=(f"--racers={v271.FLAG.key}", f"--flag-racer={v271.FLAG_RACER}"))
    assert _digests(plain) != _digests(flagged), (
        "the flag probe rendered the shipped picture - it did not apply")
    # And the default, with no --flag-racer at all, is the shipped picture.
    default, _ = _render(tmp_path / "default", v271.PROFILE, "0.000")
    assert _digests(default) == _digests(plain)
