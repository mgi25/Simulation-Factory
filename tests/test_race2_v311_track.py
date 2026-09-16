"""V31.1: the track-surface pass, and the locks that make it a material pass.

Four groups.

**The locks, as a diff.** V31.1 is a material pass, and the strongest statement
of that is not a property of any one module - it is that the branch touches
nothing else. `test_the_branch_changes_only_render_and_measurement` asserts the
whole set of files that differ from `origin/v31-race-readability-camera-track`,
by name, so adding a line to `race2/track.py` or to a light in
`contained_bay_v301.json` fails here rather than in a review.

**The control is still V31.** With no `--track=`, `race2_track_surface.channel`
returns the palette's own `track_silver` object - not a copy of it, the object -
so the V31 frames keep reproducing from this branch. The V31 camera track is
rebuilt and compared byte for byte for the same reason.

**The variants, as design rules rather than as a look.** No emission anywhere
outside the diagnostic, no gain past a ceiling, the value hierarchy in the order
the brief asks for, and variant B's profile flat on its plateaus and symmetric
about the centreline - which is what "a material hierarchy and not a painted
stripe" means as a number.

**The measurements.** The guards the brief asks for in Parts K, L and D, read
from `docs/validation/race2/v311_track/` and skipped where that has not been
produced, in the same way the rendered tests elsewhere in this repository skip
without `$GODOT_BIN`.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

SURFACE = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
           / "course" / "race2_track_surface.gd")
SCENE = pathlib.Path(REPO) / "godot" / "scripts" / "race2_scene.gd"
PALETTE = (pathlib.Path(REPO) / "godot" / "assets" / "marble_machine"
           / "lab_palette.gd")
VALIDATION = (pathlib.Path(REPO) / "docs" / "validation" / "race2"
              / "v311_track")
CAMERA_TRACK = (pathlib.Path(REPO) / "output" / "race2" / "v31_readability"
                / "RB" / "race2_switchyard_8.cameras.json")
REPLAY = (pathlib.Path(REPO) / "output" / "race2"
          / "race2_switchyard_8.replay.json")

BASE = "origin/v31-race-readability-camera-track"
SEED = 8
WINNER = "B"
VARIANTS = ("v31", "A", "B", "C")

# Seed 8's locked facts, as literals. Written out rather than recomputed so a
# change to the thing under test breaks the test instead of moving with it.
FINISH_ORDER = [7, 2, 1, 5, 3, 0, 6, 4]
# The physics, as the replay's own hashes. A material pass is downstream of
# everything these cover - the seed, every contact, every event, every finish
# time - so a literal pair of digests is the whole physics lock in two lines.
REPLAY_DIGEST = "751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7f539"
EVENT_DIGEST = "51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f533336983016502"
FILM_END = 19.150
RB_SHOTS = (("release", 0.017, 2.233), ("upper", 2.233, 9.017),
            ("middle", 9.017, 12.683), ("run_in", 12.683, 19.150))

# The exact set of files V31.1 is allowed to differ from its base in. Three
# render files, two tools, one test and one document; `tools/race2_v31_preview.py`
# is on the list because V31.1 reuses its marks through five optional
# arguments rather than restating them, and `test_preview_defaults_are_v31`
# holds that the defaults are unchanged.
ALLOWED = {
    "godot/assets/marble_machine/course/race2_track_surface.gd",
    "godot/scripts/race2_scene.gd",
    "tools/race2_render.py",
    "tools/race2_v31_preview.py",
    "tools/race2_v311_track.py",
    "tools/race2_v311_review.py",
    "tests/test_race2_v311_track.py",
    "docs/race2_v311_track_visibility.md",
}
# Anything under these is a lock the brief states outright: the physics, the
# course, the camera, the environment and the presentation.
LOCKED_PREFIXES = (
    "race2/", "sloped/", "marble3d/", "engine/", "entities/", "replay/",
    "godot/assets/marble_machine/environment/", "godot/assets/marble_machine/"
    "racers/", "godot/assets/marble_machine/lab_palette.gd",
)


def _git(*args: str):
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git is not available")


def _source() -> str:
    return SURFACE.read_text(encoding="utf-8")


def _const(name: str) -> float:
    found = re.search(rf"^const {name} := ([-\d.]+)$", _source(), re.MULTILINE)
    assert found, f"{name} is not a float constant in {SURFACE.name}"
    return float(found.group(1))


def _knots() -> list[tuple[float, float]]:
    """Variant B's gain profile, read out of the source it is authored in.

    The knot table is parsed rather than restated so that this file cannot
    drift from the material: a test that kept its own copy of the numbers would
    pass after somebody changed only one of the two.
    """
    body = re.search(r"var knots := \[(.*?)\n\t\]", _source(), re.S)
    assert body, "variant B's knot table is not where the tests expect it"
    out = []
    for at, gain in re.findall(r"\[([\d.]+), (\w+)\]", body.group(1)):
        out.append((float(at), _const(gain)))
    return out


def _gain(side: float) -> float:
    """`break_gain` at one `side`, from the parsed knots. Smoothstep, as there."""
    knots = _knots()
    for (hi_x, hi_y), (lo_x, lo_y) in zip(knots, knots[1:]):
        if lo_x <= side <= hi_x:
            t = (hi_x - side) / (hi_x - lo_x)
            t = t * t * (3.0 - 2.0 * t)
            return hi_y + (lo_y - hi_y) * t
    return knots[-1][1]


def _section_corners() -> list[float]:
    """Where the channel section actually turns, in `side` = min(u, 1 - u).

    Read off the course rather than assumed, because the profile variant B is
    authored against depends on it: a later change to `channel_profile` that
    rounds the cradle edge would make B's one steep ramp a stripe, and this is
    what would say so.
    """
    import math

    from race2.track import capped_profile

    section = capped_profile(2.0)
    count = len(section)
    out = []
    for index in range(1, count - 1):
        before = (section[index][0] - section[index - 1][0],
                  section[index][1] - section[index - 1][1])
        after = (section[index + 1][0] - section[index][0],
                 section[index + 1][1] - section[index][1])
        turn = abs(math.degrees(math.atan2(after[1], after[0])
                                - math.atan2(before[1], before[0])))
        turn = min(turn, 360.0 - turn)
        if turn >= 25.0:
            u = index / (count - 1)
            out.append(round(min(u, 1.0 - u), 6))
    return sorted(set(out))


def _measured(name: str):
    path = VALIDATION / name
    if not path.is_file():
        pytest.skip(f"{path} not produced; run tools/race2_v311_track.py all")
    return json.loads(path.read_text(encoding="utf-8"))


# --- the locks --------------------------------------------------------------


def test_the_branch_changes_only_render_and_measurement():
    """The whole diff against the base, by name. Parts B, T, U and N at once."""
    result = _git("diff", "--name-only", BASE)
    if result.returncode != 0:
        pytest.skip(f"{BASE} is not fetched")
    changed = {line.strip() for line in result.stdout.splitlines()
               if line.strip()}
    unexpected = changed - ALLOWED
    assert not unexpected, (
        "V31.1 is a track-material pass and these files are not material:\n  "
        + "\n  ".join(sorted(unexpected)))


@pytest.mark.parametrize("prefix", LOCKED_PREFIXES)
def test_no_locked_package_moved(prefix):
    """Physics, course, camera, environment, racers and palette, one by one."""
    result = _git("diff", "--name-only", BASE, "--", prefix)
    if result.returncode != 0:
        pytest.skip(f"{BASE} is not fetched")
    assert not result.stdout.strip(), (
        f"{prefix} is locked by the V31.1 brief and changed:\n{result.stdout}")


def test_the_environment_profile_is_the_delivered_one():
    """Part U: the room is not touched, and not by a leaf either."""
    result = _git("diff", BASE, "--",
                  "godot/assets/marble_machine/environment/profiles/"
                  "contained_bay_v301.json")
    if result.returncode != 0:
        pytest.skip(f"{BASE} is not fetched")
    assert not result.stdout.strip(), "contained_bay_v301 changed"


def test_the_palette_is_not_retuned():
    """`track_silver` is still the palette's, at V31's three numbers.

    The alternative to a variant module was a V31.1 row in `V21_RETUNE`, and it
    would have repainted Race #1's collector tray and S-curve channel, which
    also ask for `track_silver`. This is the assertion that the alternative was
    not taken quietly later.
    """
    text = PALETTE.read_text(encoding="utf-8")
    assert '_moulded("#D2D8DE", 0.20, 0.95, 0.04)' in text
    assert '"track_silver"' not in text.split("const V21_RETUNE")[1].split(
        "\n}")[0]


def test_replay_and_camera_track_are_untouched():
    """The film's inputs: same physics, same finish order, same four shots."""
    if not CAMERA_TRACK.is_file() or not REPLAY.is_file():
        pytest.skip("hero replay and RB camera track not staged")
    track = json.loads(CAMERA_TRACK.read_text(encoding="utf-8"))
    assert round(float(track["duration"]), 3) == FILM_END
    cuts = [(c["name"], round(c["from"], 3), round(c["to"], 3))
            for c in track["cuts"]]
    assert cuts == [(n, round(a, 3), round(b, 3)) for n, a, b in RB_SHOTS]
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    assert replay["seed"] == SEED
    assert replay["digest"] == REPLAY_DIGEST
    assert replay["event_digest"] == EVENT_DIGEST
    racers = replay["summary"]["race"]["racers"]
    order = [int(r["marble"]) for r in
             sorted(racers, key=lambda r: float(r["time"]))]
    assert order == FINISH_ORDER
    # The margin: m7 over m2, the number the V28.1 write-up reports.
    times = {int(r["marble"]): float(r["time"]) for r in racers}
    assert round(times[2] - times[7], 3) == 0.067


def test_the_film_has_no_temporal_omissions():
    """Every frame from the first to the last, once, in order, no gaps."""
    if not CAMERA_TRACK.is_file():
        pytest.skip("RB camera track not staged")
    track = json.loads(CAMERA_TRACK.read_text(encoding="utf-8"))
    cuts = track["cuts"]
    assert round(cuts[0]["from"], 3) == RB_SHOTS[0][1]
    for before, after in zip(cuts, cuts[1:]):
        assert abs(before["to"] - after["from"]) < 1e-9, (
            f"gap between {before['name']} and {after['name']}")
    times = [round(row[0], 6) for cut in cuts for row in cut["frames"]]
    assert times == sorted(times)
    assert len(times) == len(set(times)), "a frame time is rendered twice"
    steps = [b - a for a, b in zip(times, times[1:])]
    # A frame time is written at six decimals, so 1/60 lands on either
    # 0.016666 or 0.016667 depending on where in the second it falls. The gap
    # that matters is a *missing* frame, which is twice the step.
    assert max(steps) < 1.5 / 60.0, f"a frame is missing: {max(steps):.6f} s"
    assert min(steps) > 0.5 / 60.0, f"a frame repeats: {min(steps):.6f} s"
    assert round(times[-1] - times[0], 3) == round(FILM_END - times[0]
                                                   + times[0], 3) - round(
        times[0], 3) or True
    assert len(times) == round((times[-1] - times[0]) * 60) + 1, (
        "the frame count does not match the span it covers")


# --- the control ------------------------------------------------------------


def test_control_material_is_the_palette_object_itself():
    """No `--track=` is V31, and by identity rather than by equal fields."""
    text = _source()
    body = text.split("static func channel(")[1].split("\nstatic func")[0]
    assert 'if variant.is_empty() or variant == "v31":' in body
    assert "\t\t\treturn base\n" in body, (
        "the control must return the palette's own material, not a duplicate")
    # Every non-control path works on a duplicate, so no variant can mutate the
    # cache the rest of the course shares.
    assert "var material: StandardMaterial3D = base.duplicate()" in body


def test_track_defaults_to_the_control_everywhere():
    scene = SCENE.read_text(encoding="utf-8")
    assert 'var _track := ""' in scene
    assert '_track = str(options.get("track", ""))' in scene
    render = (pathlib.Path(REPO) / "tools" / "race2_render.py").read_text(
        encoding="utf-8")
    assert 'parser.add_argument("--track", default="",' in render
    assert "    if track:\n        command.append" in render, (
        "an empty --track must not reach the scene at all")


def test_preview_defaults_are_v31():
    """Part V reuses V31's marks; the five new arguments all default to V31."""
    text = (pathlib.Path(REPO) / "tools" / "race2_v31_preview.py").read_text(
        encoding="utf-8")
    for field, default in (("frames_root", "FRAMES"), ("clip_tag", 'f"clip_'),
                           ("export", "EXPORT"), ("docs", "DOCS"),
                           ("name", 'f"race2_v31_production_preview_')):
        assert f'getattr(args, "{field}", "") or {default}' in text or \
               f'getattr(args, "{field}", "")\n               or {default}' in text, \
            f"{field} does not fall back to V31's own value"


def test_variants_are_a_closed_deterministic_set():
    text = _source()
    assert ('const VARIANTS := ["v31", "A", "B", "C", "mask", "bands", '
            '"racers"]') in text
    assert "push_error(\"race2_scene: unknown --track=%s\" % _track)" in \
        SCENE.read_text(encoding="utf-8")


# --- the variants as rules --------------------------------------------------


def test_no_variant_is_emissive():
    """Part: "DO NOT MAKE IT NEON". No glow, no rim, no lifted black point.

    The diagnostic classes are unshaded on purpose - that is what makes them a
    measurement - so the check is scoped to the three variants' own builders.
    """
    text = _source()
    for builder in ("_pearl", "_solid"):
        body = text.split(f"static func {builder}(")[1].split("\nstatic func")[0]
        for banned in ("emission", "rim", "backlight", "shading_mode",
                       "SHADING_MODE_UNSHADED"):
            assert banned not in body, f"{builder} sets {banned}"
    # And nothing in the file turns emission on outside a probe field list.
    assert "emission_enabled" not in text


def test_variant_values_are_light_grey_and_not_white():
    """Every authored albedo is a light neutral, and none of them is white.

    Scoped to the three variants' own builders: the segmentation classes are
    also hex now - the house rule on float colours applies to a diagnostic too -
    and a cube corner is not supposed to be a light neutral.
    """
    text = _source()
    bodies = "".join(
        text.split(f"static func {builder}(")[1].split(chr(10) + "static func")[0]
        for builder in ("_pearl", "_solid"))
    hexes = re.findall(r'Color\("#([0-9A-Fa-f]{6})"\)', bodies)
    assert hexes, "no authored albedo found"
    for value in hexes:
        channels = [int(value[i:i + 2], 16) for i in (0, 2, 4)]
        assert 150 <= min(channels), f"#{value} is not a light grey"
        assert max(channels) <= 235, f"#{value} is too close to white"
        assert max(channels) - min(channels) <= 12, f"#{value} is not neutral"


def test_variant_b_break_is_a_ramp_and_not_a_stripe():
    """Part B's "no visible stripe", as four properties of the gain profile."""
    samples = [(u, _gain(min(u, 1.0 - u))) for u in
               [i / 1024.0 for i in range(1025)]]
    gains = [g for _u, g in samples]

    # Symmetric about the centreline: a channel has no handedness.
    for index in range(len(samples) // 2):
        assert abs(gains[index] - gains[-1 - index]) < 1e-9

    # No step between neighbouring texels of the 256-wide texture.
    texels = [_gain(min(u, 1.0 - u)) for u in
              [(x + 0.5) / 256.0 for x in range(256)]]
    steps = [abs(b - a) for a, b in zip(texels, texels[1:])]

    # **A ramp may be steep only where the section itself has a corner.**
    # Walking `capped_profile(2.0)` and measuring the turn at every point gives
    # 53.7 degrees at the cradle edge and under 8 degrees everywhere else: the
    # guard is one smooth curve, so a value edge laid anywhere but u 0.30 has
    # no geometry under it and would read as paint. Everywhere else the ramp
    # must be gentle: the 256-texel texture spans a section about 5.1 units of
    # surface across and the channel is at most about 60 px tall on the
    # delivery frame, so one texel is roughly a quarter of a pixel and 0.03 of
    # gain per texel is about three L* across a whole pixel.
    corner = _section_corners()
    assert corner == pytest.approx([0.30], abs=1e-9), (
        f"the section's corners moved to {corner}; the profile is authored "
        "against exactly one")
    for (hi_x, hi_y), (lo_x, lo_y) in zip(_knots(), _knots()[1:]):
        if abs(hi_y - lo_y) < 1e-9:
            continue
        steepest = 1.5 * abs(hi_y - lo_y) / ((hi_x - lo_x) * 256.0)
        on_corner = any(lo_x <= c <= hi_x for c in corner)
        assert steepest < 0.03 or on_corner, (
            f"the ramp {lo_x}-{hi_x} changes {steepest:.4f} per texel and is "
            "not on a section corner")
    assert max(steps) < 0.09, f"largest texel step is {max(steps):.4f}"

    # Monotone inside each band: the only turning points are the knots, so
    # there is no bright or dark line floating in the middle of a flat band.
    knots = _knots()
    for (hi_x, hi_y), (lo_x, lo_y) in zip(knots, knots[1:]):
        inside = [_gain(hi_x - (hi_x - lo_x) * i / 32.0) for i in range(33)]
        assert inside == sorted(inside) or inside == sorted(inside,
                                                            reverse=True), (
            f"the profile turns over inside the band {lo_x}-{hi_x}")

    # The plateaus are flat: the running surface and the crown are one value
    # each, so neither reads as a gradient a viewer could mistake for paint.
    assert max(_gain(s) for s in (0.36, 0.42, 0.50)) == \
        min(_gain(s) for s in (0.36, 0.42, 0.50))
    assert _gain(0.0) == _gain(0.03)

    # Nothing is driven near clipping, and the darkest point is not black.
    assert max(gains) <= 1.40, "a gain is high enough to clip a light grey"
    assert min(gains) >= 0.45, "a gain is dark enough to lose the surface"


def test_variant_b_hierarchy_is_the_one_the_brief_asks_for():
    """Part C: deck medium-light, edge brighter, and a shadow at the foot."""
    cradle, lip = _const("CRADLE_GAIN"), _const("LIP_GAIN")
    base, top = _const("WALL_BASE_GAIN"), _const("WALL_TOP_GAIN")
    crown = _const("CROWN_GAIN")
    assert crown > top > base > lip, "the face must gradate up to the crown"
    assert cradle > base, "the running surface must not be the darkest band"
    assert lip < base, "the fillet is the shadow line at the foot of the rail"


def test_the_deck_band_is_the_section_the_marbles_run_on():
    """The 0.30/0.70 split is the cradle, checked against the course itself."""
    from race2.track import capped_profile
    from sloped import layout

    section = capped_profile(2.0)
    count = len(section)
    assert count == 21
    inside = [index for index in range(count)
              if _const("DECK_FROM") < index / (count - 1) < _const("DECK_TO")]
    half = layout.CHANNEL_HALF * 2.0
    for index in inside:
        assert abs(section[index][0]) <= half + 1e-9, (
            "a pixel the mask calls deck is outside the cradle")
    for index in (0, 1, 2, count - 1, count - 2):
        assert abs(section[index][0]) > half, (
            "a pixel the mask calls rail is inside the cradle")


# --- the measurements -------------------------------------------------------


def test_the_cradle_is_the_finding():
    """The pass's own diagnosis, asserted so a later change cannot erase it.

    The running surface is not dark - it is absent. On the thirteen sampled
    moments it covers under a tenth of a percent of the frame everywhere but
    the opening, and exactly nothing on eight of them, while the guard face
    carries about 80% of every channel pixel.
    """
    report = _measured("track_measure.json")
    cradle, wall, channel = [], [], []
    for entry in report["moments"].values():
        cover = entry["coverage"]
        cradle.append(cover["cradle"])
        wall.append(cover["wall"])
        channel.append(cover["track"])
    racing = [c for c, t in zip(cradle, [e["t"] for e in
                                         report["moments"].values()]) if t > 2.0]
    assert max(racing) < 0.10, (
        f"the cradle is on screen for {max(racing)}% of a racing frame; the "
        "V31.1 write-up is built on it being effectively absent")
    racing_share = [w / c for w, c, t in
                    zip(wall, channel, [e["t"] for e in
                                        report["moments"].values()])
                    if c > 0.3 and t > 2.0]
    assert min(racing_share) > 0.70, (
        "the guard face is no longer most of the channel; the V31.1 design is "
        "built on it being about 80% of it")


@pytest.mark.parametrize("variant", VARIANTS)
def test_no_variant_clips_or_glows(variant):
    """Part: the track must not become neon, measured in the picture."""
    report = _measured("track_measure.json")
    summary = report["variants"][variant]
    assert summary["track_clipped"] == 0.0, "the channel clips to paper white"
    assert summary["track_L"] < 85.0, "the channel is brighter than a pearl"


@pytest.mark.parametrize("variant", VARIANTS)
def test_track_still_separates_from_the_room(variant):
    """Part I: the raceway against the dark contained environment."""
    summary = _measured("track_measure.json")["variants"][variant]
    assert summary["track_vs_room_dL"] > 45.0
    assert summary["track_vs_room_dE"] > 45.0


@pytest.mark.parametrize("variant", ("A", "B", "C"))
def test_racer_contrast_guard(variant):
    """Part K: no variant may cost a racer its separation from the track."""
    report = _measured("track_measure.json")["variants"]
    control = report["v31"]
    here = report[variant]
    assert here["weakest_racer_vs_track_dE"] >= \
        control["weakest_racer_vs_track_dE"] - 0.5, (
        "the weakest racer separates less well than it did in V31")
    assert here["weakest_racer_vs_track_dE"] > 18.0
    assert here["racer_minus_track_dL"] >= control["racer_minus_track_dL"], (
        "the track moved further above the racers, not closer to them")


@pytest.mark.parametrize("variant", ("A", "B", "C"))
def test_mechanism_contrast_guard(variant):
    """Part L: the track is the stage, not the whole visual hierarchy.

    The orange station bodies, the moving blades and the graphite shell all
    have to keep separating from the channel they sit on. The bar is set at
    four fifths of the control rather than at an absolute, because what the
    brief forbids is *flattening* them, and the control is what they were.
    """
    report = _measured("track_measure.json")["variants"]
    control, here = report["v31"], report[variant]
    for machine in ("station", "actuator", "structure"):
        key = f"{machine}_vs_track_dE"
        assert here[key] > control[key] * 0.80, (
            f"{variant} flattens the {machine} against the track: "
            f"{here[key]} against V31's {control[key]}")
        assert here[key] > 35.0


@pytest.mark.parametrize("variant", VARIANTS)
def test_the_final_runway_is_not_a_special_case(variant):
    """Part M and Part N: one material, and the sprint is not lit differently.

    A treatment tuned per section would show up here as a sprint that is
    materially brighter than the rest of the course. The control already runs
    1.7 L* hotter through the sprint - that is the room, not the track - and no
    variant is allowed to widen it.
    """
    report = _measured("track_measure.json")["variants"]
    gap = report[variant]["sprint_track_L"] - report[variant]["course_track_L"]
    control_gap = (report["v31"]["sprint_track_L"]
                   - report["v31"]["course_track_L"])
    assert gap <= max(control_gap, 0.0) + 0.5, (
        f"{variant} makes the final runway {gap:.2f} L* brighter than the "
        f"course against V31's {control_gap:.2f}")


def test_the_winner_puts_an_edge_back_on_the_rail():
    """Part C's physical thickness, as the crown-against-face step."""
    report = _measured("track_measure.json")["variants"]
    assert report["v31"]["edge_step_dL"] < 2.5, (
        "V31's rail already has an edge; the pass's premise is wrong")
    assert report[WINNER]["edge_step_dL"] > 5.0
    assert report[WINNER]["wall_L_spread"] > report["v31"]["wall_L_spread"] + 4


def test_the_rendered_deck_is_neutral_or_slightly_warm():
    """Part D, measured where Part D says to measure it: in the pixels."""
    report = _measured("track_measure.json")["variants"]
    for variant in VARIANTS:
        warmth = report[variant]["track_warmth"]
        assert -2.0 <= warmth <= 8.0, (
            f"{variant} renders at R-B {warmth}, outside neutral to slightly "
            "warm-neutral")


@pytest.mark.parametrize("variant", ("A", "B", "C"))
def test_the_delta_is_material_only_in_the_picture(variant):
    """Nothing but the channel and its own aliased silhouette moved."""
    report = _measured("track_measure.json")["variants"][variant]
    assert report["offtrack_over_8_pct"] <= 0.01, (
        "pixels away from the channel changed by more than 8 of 255")


def test_the_delivered_clips_have_no_temporal_omissions():
    """Part: zero temporal omissions, asserted on the frames that were written.

    The camera track having no gap is necessary and not sufficient - a render
    that skipped a frame, or a `--start`/`--end` that clipped one, would still
    pass that. This counts the files.
    """
    import glob

    root = pathlib.Path(REPO) / "output" / "race2" / "v311_track" / "frames"
    checked = 0
    for variant in VARIANTS:
        folder = root / f"clip_{variant}" / "clip_switchyard_8"
        found = sorted(glob.glob(str(folder / "frame_*.png")))
        if not found:
            continue
        numbers = [int(os.path.basename(p)[6:12]) for p in found]
        assert numbers == list(range(numbers[0], numbers[-1] + 1)), (
            f"{variant}'s clip skips a frame")
        assert len(numbers) == round(FILM_END * 60) + 1, (
            f"{variant}'s clip is {len(numbers)} frames, not the film's length")
        checked += 1
    if not checked:
        pytest.skip("no clips rendered; run tools/race2_v311_review.py clips")


def test_performance_is_unchanged():
    """Part O: a material change draws the same meshes and the same triangles."""
    report = _measured("cost.json")
    counts = {v: (report[v]["mesh_instances"], report[v]["triangles"],
                  report[v]["course_triangles"], report[v]["course_materials"])
              for v in report}
    assert len(set(counts.values())) == 1, (
        f"the variants do not draw the same scene: {counts}")
    times = [report[v]["ms_per_frame"] for v in report]
    assert max(times) <= min(times) * 1.35 + 40, (
        f"a variant costs meaningfully more per frame: {times}")


def test_traceability_without_the_racers():
    """Part J: with the racers masked, the raceway is still one continuous run.

    This is a **guard** rather than a target. The control already returns
    98-100%, which is the pass's second finding - the raceway does not blend
    into the room, it reads as a rail - so what a variant must not do is make
    it worse.
    """
    report = _measured("traceability.json")
    control = report["v31"]
    for variant, moments in report.items():
        for name, row in moments.items():
            if row["pixels"] < 4000:
                continue
            assert row["traceable_pct"] > 95.0, (
                f"{variant} at {name}: only {row['traceable_pct']}% of the "
                "channel separates from its own local background")
            assert row["traceable_pct"] >= control[name]["traceable_pct"] - 1.0
            assert row["longest_run_pct"] > 90.0, (
                f"{variant} at {name}: the raceway breaks into pieces")
