"""V32.1: the render/collision separation, and the locks it must not break.

The pass's claim is narrow and checkable: **the picture of the Race #2 channel
changed and the collider did not.** These tests are that claim, split into the
places it could fail.

They are deliberately of two kinds. The pure ones - the section transforms, the
collider digest, the material fields - run anywhere. The ones that need a
rendered frame skip when the frames are not on disk, because a render needs a
GPU and a 452 MB frame set that is not in the branch; what they check when the
frames *are* there is that the analytic instrument this pass measured with and
the renderer it measured agree.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from race2 import courses, export, v321_section
from race2.track import capped_profile

BASE_COMMIT = "ab5d516fac12b3cca569d2ecc41e229fbdefd08e"
OUT = os.path.join(REPO, "output", "race2", "v321_track_geometry")
DOCS = os.path.join(REPO, "docs", "validation", "race2", "v321_track_geometry")
SOURCE = os.path.join(REPO, "output", "race2", "v31_readability", "RB")

# The two digests the V32 branch shipped, read off
# `output/race2/v31_readability/RB/race2_switchyard_8.replay.json` at `ab5d516`.
# Written down rather than recomputed from the local file, because a test that
# compares a file with itself is not a test.
V32_REPLAY_DIGEST = "751031348936808792ad2fac667bfdfb6e726dca7520ffdaf19429c6a2f7f539"
V32_EVENT_DIGEST = "51078e8d31e56f53993c6ee9aa61b482a6757942a422fb43f533336983016502"


def _tool():
    spec = importlib.util.spec_from_file_location(
        "race2_v321_geometry", os.path.join(REPO, "tools", "race2_v321_geometry.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(*args: str) -> str | None:
    try:
        return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


@pytest.fixture(scope="module")
def course():
    return courses.build("switchyard")


@pytest.fixture(scope="module")
def section():
    return capped_profile(2.0)


# --- the separation ---------------------------------------------------------


def test_the_render_variant_never_reaches_the_collider(course):
    """Part M's hard rule, checked where it could actually be broken.

    `TrackRun.local_colliders` is what pybullet is handed. It builds its rings
    from `section_at`, and `race2.export._run_rings` builds *its* rings from the
    same call - which is why V31.1 could not move a vertex. V32.1 maps the
    section in `_run_rings` only, so this walks every run's collider mesh with
    the variant set to each of the four and asserts the vertices are identical
    to the byte.
    """
    baseline = {}
    for name, run in course.runs.items():
        run._mesh = None
        mesh = run.local_colliders()[0]
        baseline[name] = _sha_bytes(
            json.dumps([[round(v, 12) for v in vertex] for vertex in mesh.vertices]
                       + [list(mesh.indices)]).encode())

    for variant in v321_section.VARIANTS:
        os.environ["RACE2_RENDER_SECTION"] = variant
        try:
            for name, run in course.runs.items():
                run._mesh = None
                mesh = run.local_colliders()[0]
                digest = _sha_bytes(
                    json.dumps([[round(v, 12) for v in vertex]
                                for vertex in mesh.vertices]
                               + [list(mesh.indices)]).encode())
                assert digest == baseline[name], (
                    f"{variant} changed the collider of {name}")
        finally:
            os.environ.pop("RACE2_RENDER_SECTION", None)


def test_the_identity_variant_is_the_identity(section):
    for name in ("", "CONTROL", "S"):
        assert v321_section.transform(name, section) == [
            (float(a), float(u)) for a, u in section]


def test_a_variant_only_moves_a_vertex_outward_and_down(course, section):
    """The one geometric invariant that keeps a marble inside its own picture.

    Checked on the **built** course rather than on the bare profile, so a run
    with a guard boost or an opened wall is checked as it is actually swept.
    """
    for variant in ("A", "B", "C"):
        for name, run in course.runs.items():
            for index in range(0, len(run.path), 7):
                collider = run.section_at(index)
                render = v321_section.transform(variant, collider)
                assert len(render) == len(collider)
                for (a0, u0), (a1, u1) in zip(collider, render):
                    assert abs(a1) >= abs(a0) - 1e-9, (
                        f"{variant} moved {name} inward at {a0}")
                    assert u1 <= u0 + 1e-9, (
                        f"{variant} raised {name} at {a0}")


def test_a_variant_keeps_the_section_a_function_of_across(section):
    """No overhang: `across` stays non-decreasing from west guard to east.

    The first draft of the shoulder slid the foot of the face further than its
    crown, which stood the face back over the shelf and made `across` fold. The
    strip builder does not care, but `sloped.track._interpolate_rise` does, the
    band texture does, and a folded section renders as a surface passing through
    itself.
    """
    for variant in v321_section.VARIANTS:
        points = v321_section.transform(variant, section)
        for (a0, _u0), (a1, _u1) in zip(points, points[1:]):
            assert a1 >= a0 - 1e-9, f"{variant} folds at {a0}"


def test_a_variant_keeps_the_cradle_exactly(section):
    """Every variant leaves the running surface alone.

    The cradle is where the marbles are, it is the surface the pass exists to
    show, and moving it would be moving the road rather than the fence.
    """
    west, east = v321_section.cradle_edges(section)
    for variant in v321_section.VARIANTS:
        points = v321_section.transform(variant, section)
        assert points[west:east + 1] == [
            (float(a), float(u)) for a, u in section[west:east + 1]]


def test_the_transform_is_pure_and_deterministic(section):
    for variant in v321_section.VARIANTS:
        first = v321_section.transform(variant, section)
        second = v321_section.transform(variant, list(section))
        assert first == second
        assert section == capped_profile(2.0)


def test_an_unknown_variant_is_refused(section):
    with pytest.raises(KeyError):
        v321_section.transform("nope", section)
    os.environ["RACE2_RENDER_SECTION"] = "nope"
    try:
        with pytest.raises(ValueError):
            export.render_section()
    finally:
        os.environ.pop("RACE2_RENDER_SECTION", None)


def test_the_export_hook_is_off_by_default():
    os.environ.pop("RACE2_RENDER_SECTION", None)
    assert export.render_section() == ""
    os.environ["RACE2_RENDER_SECTION"] = "CONTROL"
    try:
        assert export.render_section() == ""
    finally:
        os.environ.pop("RACE2_RENDER_SECTION", None)


# --- the locks --------------------------------------------------------------


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    OUT, "CONTROL", "race2_switchyard_8.geometry.json")),
    reason="run `tools/race2_v321_geometry.py build` first")
def test_control_reproduces_the_v32_geometry_byte_for_byte():
    a = open(os.path.join(OUT, "CONTROL", "race2_switchyard_8.geometry.json"), "rb").read()
    b = open(os.path.join(SOURCE, "race2_switchyard_8.geometry.json"), "rb").read()
    assert _sha_bytes(a) == _sha_bytes(b)
    # S differs from CONTROL only by the weld: its *cross-section* is the
    # collider's, which is what `test_the_identity_variant_is_the_identity`
    # holds, and its rings differ only in each run's last one.
    with open(os.path.join(OUT, "S", "race2_switchyard_8.geometry.json"),
              encoding="utf-8") as handle:
        welded = json.load(handle)
    with open(os.path.join(OUT, "CONTROL", "race2_switchyard_8.geometry.json"),
              encoding="utf-8") as handle:
        plain = json.load(handle)
    for one, two in zip(welded["runs"], plain["runs"]):
        assert one["name"] == two["name"]
        assert one["rings"][:-1] == two["rings"][:-1], (
            f"the weld touched more than the last ring of {one['name']}")


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    SOURCE, "race2_switchyard_8.replay.json")), reason="no replay on disk")
def test_the_replay_and_event_digests_are_v32s():
    """Part M. The physics record is the V32 one, by its own two digests.

    The replay file differs from the V32 branch's copy in exactly one field -
    `summary.race.wall_seconds`, how long the simulation took to run - which is
    why the file's sha differs and neither digest does.
    """
    with open(os.path.join(SOURCE, "race2_switchyard_8.replay.json"),
              encoding="utf-8") as handle:
        replay = json.load(handle)
    assert replay["digest"] == V32_REPLAY_DIGEST
    assert replay["event_digest"] == V32_EVENT_DIGEST
    assert replay["seed"] == 8
    assert replay["physics_hz"] == 240
    assert replay["replay_fps"] == 60


@pytest.mark.skipif(not os.path.isdir(OUT), reason="run `build` first")
def test_every_variant_shares_one_replay_and_one_camera_plan():
    """Part N, as a file comparison rather than a claim about a camera.

    A camera cannot have moved between two films that were rendered from the
    same bytes, so this is the strongest form the camera lock can take.
    """
    reference = None
    for variant in ("CONTROL", "S", "A", "B", "C"):
        folder = os.path.join(OUT, variant)
        if not os.path.isdir(folder):
            pytest.skip("run `build` first")
        digests = tuple(
            _sha_bytes(open(os.path.join(
                folder, f"race2_switchyard_8.{kind}.json"), "rb").read())
            for kind in ("replay", "cameras"))
        if reference is None:
            reference = digests
        assert digests == reference, f"{variant} does not share the camera plan"
    source = tuple(
        _sha_bytes(open(os.path.join(
            SOURCE, f"race2_switchyard_8.{kind}.json"), "rb").read())
        for kind in ("replay", "cameras"))
    assert reference == source


def test_the_branch_changes_only_render_and_measurement():
    """Part L, as a diff against the base rather than as a promise.

    The environment, the camera solver, the flow and readability measures, the
    presentation, the audio and the physics are all absent from this list, and a
    file arriving here that is not in it is the thing this test exists to catch.
    """
    diff = _git("diff", "--name-only", BASE_COMMIT)
    if diff is None:
        pytest.skip("not a git checkout")
    changed = {line.strip() for line in diff.splitlines() if line.strip()}
    allowed = {
        "race2/export.py",                # the one render call site
        "race2/v321_section.py",          # the render-only sections
        "godot/assets/marble_machine/course/race2_track_surface.gd",  # --faces
        "godot/scripts/race2_scene.gd",   # reads --faces
        "tools/race2_render.py",          # passes --faces
        "tools/race2_v321_geometry.py",   # the measurement
        "tools/race2_v321_short.py",      # the production candidate
        # **The one presentation file, and why.** Drawing the running surface
        # put a bright raceway through the rows V32's payoff card sat in, and
        # `card_band` had no answer for a film with no dark band left. See
        # `test_the_card_band_is_v32s_on_v32s_frames` for the half of that
        # change which is a bug fix, and section 8 of the doc for the half which
        # is new. Nothing about the card's drawing, content or timing moves.
        "race2/presentation.py",
        "tests/test_race2_v321_geometry.py",
        "docs/race2_v321_track_geometry.md",
    }
    stray = {path for path in changed
             if path not in allowed
             and not path.startswith("docs/validation/race2/v321_track_geometry/")}
    assert not stray, f"this pass touched files it should not: {sorted(stray)}"


def test_the_channel_material_is_v311_variant_b_field_for_field():
    """Part D. Every colour, gloss and texture field of Variant B is untouched.

    `cull_mode` is the one field V32.1 changes, and it is not one of them: it
    decides **which side of a surface is drawn**, not what the surface looks
    like. The check is on the source rather than on a rendered pixel because a
    pixel would also be testing the lights.
    """
    path = os.path.join(REPO, "godot", "assets", "marble_machine",
                        "course", "race2_track_surface.gd")
    current = open(path, encoding="utf-8").read()
    for line in (
        'material.albedo_color = Color("#BEC1C4")',
        "material.roughness = 0.42",
        "material.clearcoat = 0.55",
        "material.clearcoat_roughness = 0.10",
        "const CRADLE_GAIN := 1.35",
        "const LIP_GAIN := 0.55",
        "const WALL_BASE_GAIN := 0.70",
        "const WALL_TOP_GAIN := 1.14",
        "const CROWN_GAIN := 1.34",
        "const DECK_FROM := 0.30",
        "const DECK_TO := 0.70",
    ):
        assert line in current, f"Variant B lost {line!r}"

    base = _git("show", f"{BASE_COMMIT}:godot/assets/marble_machine/course/"
                        "race2_track_surface.gd")
    if base is None:
        pytest.skip("not a git checkout")
    added = [line for line in current.splitlines() if line not in base.splitlines()]
    forbidden = ("albedo", "roughness", "clearcoat", "metallic", "GAIN",
                 "DECK_FROM", "DECK_TO")
    for line in added:
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("##"):
            continue
        assert not any(word in stripped for word in forbidden), (
            f"V32.1 added a look field: {stripped!r}")


def test_the_default_face_mode_is_v32s():
    """A render with no `--faces` is V32's render.

    The same property `race2_track_surface.channel` already had for `--track`:
    every new term defaults to off, so the control is reproducible from this
    branch rather than kept as a copy of an old one.
    """
    for path, needle in (
        (os.path.join(REPO, "godot", "scripts", "race2_scene.gd"),
         'str(options.get("faces", "front"))'),
        (os.path.join(REPO, "godot", "assets", "marble_machine", "course",
                      "race2_track_surface.gd"),
         'face_mode: String = "front"'),
    ):
        assert needle in open(path, encoding="utf-8").read()
    assert v321_section.FACES["CONTROL"] == "front"
    assert all(v321_section.FACES[v] == "both" for v in ("S", "A", "B", "C"))


# --- the numbers the variants are shaped around -----------------------------


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "contacts.json")),
                    reason="run `contacts` first")
def test_the_load_bearing_numbers_are_measured():
    with open(os.path.join(DOCS, "contacts.json"), encoding="utf-8") as handle:
        contacts = json.load(handle)
    assert abs(contacts["highest_contact_fraction"]
               - v321_section.LOAD_BEARING_MAX) < 0.01
    assert abs(contacts["p99"] - v321_section.LOAD_BEARING_P99) < 0.01
    assert contacts["resting_on_face"] > 0
    assert contacts["face_share"] < 0.05, (
        "if marbles were on the face more than a per cent or two of the time, "
        "lowering it would be a physics claim rather than a picture one")


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "contacts.json")),
                    reason="run `contacts` first")
def test_every_variant_clears_the_ninety_ninth_percentile_contact(section):
    for variant in v321_section.VARIANTS:
        data = v321_section.describe(variant, section)
        assert data["clears_p99"] == 1.0, (
            f"{variant} keeps a render face lower than the 99th percentile of "
            "the contacts the marbles actually make on it")


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "expose.json")),
                    reason="run `expose` first")
def test_the_winding_fix_is_what_moves_the_deck():
    """The pass's headline, as an assertion rather than a paragraph.

    CONTROL's deck is not small. It is absent - and the reason it is absent is
    that nothing is in front of it.
    """
    with open(os.path.join(DOCS, "expose.json"), encoding="utf-8") as handle:
        expose = json.load(handle)
    summary = expose["summary"]
    assert summary["CONTROL"]["deck_pct"] < 0.1
    assert summary["CONTROL"]["lane_px"] < 5.0
    assert summary["S"]["deck_pct"] > 10.0
    assert summary["S"]["lane_px"] > 200.0
    for variant in ("A", "B", "C"):
        assert summary[variant]["lane_px"] >= summary["S"]["lane_px"], (
            f"{variant} should widen the lane S already exposed")


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "expose.json")),
                    reason="run `expose` first")
def test_the_control_deck_is_culled_and_not_occluded():
    with open(os.path.join(DOCS, "expose.json"), encoding="utf-8") as handle:
        expose = json.load(handle)
    blamed = []
    for moment in expose["moments"]:
        over = moment["variants"]["CONTROL"]["over"]
        blamed.append(over["none"] / max(sum(over.values()), 1))
    assert min(blamed) > 0.4, (
        "on every moment most of the missing deck has *nothing* in front of "
        "it, which is what 'backfacing' means as a measurement")


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "contrast.json")),
                    reason="run `contrast` first")
def test_no_variant_loses_a_racer_to_the_deck():
    """Part I. A broader pale deck must not swallow the marbles.

    12 dE is the floor: it is roughly four times a just-noticeable difference
    at these sizes, and it is the number V31.1's own guard used.
    """
    with open(os.path.join(DOCS, "contrast.json"), encoding="utf-8") as handle:
        contrast = json.load(handle)
    for variant, row in contrast["summary"].items():
        assert row["moments_below_12"] == 0, (
            f"{variant} lets a racer within 12 dE of the surface it is on")
        assert row["weakest_vs_deck"] > 12.0, variant
        assert row["weakest_vs_room"] > 12.0, variant


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "contrast.json")),
                    reason="run `contrast` first")
def test_the_deck_does_not_clip_to_paper_white():
    """V21 shipped a film clipping 5.5% of every frame; this is that guard.

    The deck is now the largest bright surface in the picture, so it is where a
    clip would show first.
    """
    with open(os.path.join(DOCS, "contrast.json"), encoding="utf-8") as handle:
        contrast = json.load(handle)
    for variant, row in contrast["summary"].items():
        assert row["deck_clip_pct"] < 1.0, (
            f"{variant} clips {row['deck_clip_pct']:.2f}% of its deck")


@pytest.mark.skipif(not os.path.isfile(os.path.join(DOCS, "joins.json")),
                    reason="run `joins` first")
def test_the_weld_closes_the_run_joins_exactly():
    """The seam the fix uncovered, and the render-only join that closes it.

    CONTROL keeps V32's gap because CONTROL is V32. Every candidate closes it to
    zero, which is what "share an edge" means when one ring is literally the
    other.
    """
    with open(os.path.join(DOCS, "joins.json"), encoding="utf-8") as handle:
        joins = json.load(handle)["variants"]
    assert joins["CONTROL"]["world_gap_max"] > 0.3
    assert joins["CONTROL"]["screen_px_max"] > 40.0
    assert joins["CONTROL"]["moments_in_frame"] >= 10
    for name in ("S", "A", "B", "C"):
        assert joins[name]["world_gap_max"] == 0.0, name
        assert joins[name]["screen_px_max"] == 0.0, name


def test_the_weld_never_reaches_the_collider(course):
    """The same rule as the sections, for the other render-only change."""
    baseline = {}
    for name, run in course.runs.items():
        run._mesh = None
        mesh = run.local_colliders()[0]
        baseline[name] = _sha_bytes(json.dumps(
            [[round(v, 12) for v in vertex] for vertex in mesh.vertices]).encode())
    os.environ["RACE2_RENDER_WELD"] = "1"
    try:
        assert export.render_weld() is True
        for name, run in course.runs.items():
            run._mesh = None
            mesh = run.local_colliders()[0]
            digest = _sha_bytes(json.dumps(
                [[round(v, 12) for v in vertex] for vertex in mesh.vertices]).encode())
            assert digest == baseline[name], f"the weld changed {name}'s collider"
    finally:
        os.environ.pop("RACE2_RENDER_WELD", None)
    assert export.render_weld() is False


def test_the_weld_does_not_stretch_or_fold_a_quad():
    """The bridging quad has to look like the sample step it replaces.

    Measured on the built course: 0.77 to 1.25 times the run's own step at the
    centreline. A weld that produced a quad several times the step would be a
    visible stretch in the material's `v`, which the strip tiles eight times
    along a run.
    """
    import numpy as np

    tool = _tool()
    path = os.path.join(OUT, "S", "race2_switchyard_8.geometry.json")
    if not os.path.isfile(path):
        pytest.skip("run `build` first")
    with open(path, encoding="utf-8") as handle:
        geometry = json.load(handle)
    rings = tool.run_rings(geometry)
    middle = None
    for run in geometry["runs"]:
        block = rings[str(run["name"])]
        middle = block.shape[1] // 2
        bridge = float(np.linalg.norm(block[-1][middle] - block[-2][middle]))
        step = float(np.linalg.norm(block[-2][middle] - block[-3][middle]))
        assert 0.5 <= bridge / max(step, 1e-9) <= 2.0, (
            f"{run['name']} bridging quad is {bridge / step:.2f} of its own step")


# --- the payoff card's band -------------------------------------------------


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    OUT, "CONTROL", "frames", "clip_switchyard_8", "frame_001149.png")),
    reason="run `films` first")
def test_the_card_band_is_v32s_on_v32s_frames():
    """The placement rule still gives V32's answer on V32's pictures.

    This is the test that makes the `card_band` change safe. The delivered V32
    Short put the card in `[97, 372]` with its ink at `[112, 147, 966, 372]`,
    and both halves of V32.1's change - the bottom gutter and the
    no-band-is-tall-enough fallback - are written so that a film which has a
    band keeps getting it.
    """
    from race2 import presentation as pres

    tool = importlib.util.spec_from_file_location(
        "race2_v321_short", os.path.join(REPO, "tools", "race2_v321_short.py"))
    module = importlib.util.module_from_spec(tool)
    tool.loader.exec_module(module)
    short = module.load_short("CONTROL")
    replay, track, clock = short.load()
    frames = os.path.join(OUT, "CONTROL", "frames", "clip_switchyard_8")
    band = pres.card_band(frames, replay, track, clock, 16.8167)
    assert band["band"] == [97, 372]
    assert band["fallback"] is False
    assert band["max_luma"] == 84.1
    _payoff, _image, card = pres.card_plate(7, 5, band["band"])
    assert card["ink_box"] == [112, 147, 966, 372]
    assert card["inside_band"] is True


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    OUT, "A", "frames", "clip_switchyard_8", "frame_001149.png")),
    reason="run `films` first")
def test_the_card_band_falls_back_and_says_so():
    from race2 import presentation as pres

    tool = importlib.util.spec_from_file_location(
        "race2_v321_short", os.path.join(REPO, "tools", "race2_v321_short.py"))
    module = importlib.util.module_from_spec(tool)
    tool.loader.exec_module(module)
    short = module.load_short("A")
    replay, track, clock = short.load()
    frames = os.path.join(OUT, "A", "frames", "clip_switchyard_8")
    band = pres.card_band(frames, replay, track, clock, 16.8167)
    assert band["fallback"] is True
    assert band["max_luma_under_ink"] < pres.CARD_LUMA, (
        "the fallback's whole point is that the glyphs land on something dark; "
        "if they do not it should not have been offered")
    assert band["band"][1] <= 1920 - pres.HOOK_TOP, "the frame's bottom gutter"
    assert band["band"][0] >= pres.HOOK_TOP
    _payoff, _image, card = pres.card_plate(7, 5, band["band"])
    assert card["inside_band"] is True


def test_the_card_band_knows_which_card_it_is_sizing():
    """A five-letter winner gets bigger type than a six-letter one.

    `v24_payoff` fits its lines to the frame's gutter, so PINK's ink is 225 rows
    tall and PURPLE's is 201. Sizing the band from the module's default winner
    put it 24 rows short of the card that was going to be drawn, and
    `card_plate` reported the card as outside a band that had been computed for
    a different card.
    """
    from race2 import presentation as pres

    assert pres.card_height(winner=7) == 225
    assert pres.card_height(winner=5) == 201
    assert pres.card_height(winner=7) != pres.card_height(winner=5)


# --- the delivered candidate ------------------------------------------------


SHORT = os.path.join(DOCS, "short", "A")


@pytest.mark.skipif(not os.path.isfile(os.path.join(SHORT, "qc.json")),
                    reason="run `tools/race2_v321_short.py qc --variant=A` first")
def test_the_candidate_passes_every_qc_check():
    """Part X, read back off the report the candidate was measured into.

    The file itself is the evidence; this asserts that nothing in it is a
    failure and that the handful of numbers the brief names by value are the
    values it names.
    """
    with open(os.path.join(SHORT, "qc.json"), encoding="utf-8") as handle:
        qc = json.load(handle)
    failures = [row for row in qc["checks"] if not row.get("pass", True)]
    assert not failures, failures
    assert qc["ok"] is True
    assert qc["frames"] == 1150
    assert qc["duplicate_frames"] == []
    assert qc["black_frames"] == []
    assert abs(qc["loudness"]["input_tp"] - -1.93) < 0.15
    assert abs(qc["loudness"]["input_i"] - -14.18) < 0.15


@pytest.mark.skipif(not os.path.isfile(os.path.join(SHORT, "evidence.json")),
                    reason="run the candidate first")
def test_the_candidate_keeps_v32s_winner_payoff_and_clock():
    """Parts V and W: the film underneath changed and nothing above it did."""
    with open(os.path.join(SHORT, "evidence.json"), encoding="utf-8") as handle:
        evidence = json.load(handle)
    assert evidence["film"]["frames"] == 1150
    assert evidence["film"]["contiguous"] is True
    assert evidence["film"]["temporal_omissions"] == 0
    assert evidence["winner"]["marble"] == 7
    assert evidence["card"]["label"] == "PINK"
    assert evidence["comeback"]["rank"] == 5
    assert evidence["comeback"]["instruments_agree"] is True
    assert evidence["card"]["inside_band"] is True
    assert evidence["ring"]["marble"] == 7
    assert evidence["ring"]["frames_blocked"] == 0


@pytest.mark.skipif(not os.path.isfile(os.path.join(SHORT, "locks.json")),
                    reason="run the candidate first")
def test_the_physics_and_camera_layers_did_not_move():
    """Part M and Part N, off V32's own lock report.

    The environment and track layers are expected to show a changed file each -
    `race2_scene.gd` reads `--faces` and `race2_track_surface.gd` implements it,
    and those two files are the pass. What must not have moved is every file in
    the physics and camera layers, the replay's two digests, and the three
    reports V32 regenerates and compares field by field.
    """
    with open(os.path.join(SHORT, "locks.json"), encoding="utf-8") as handle:
        locks = json.load(handle)
    for layer in ("physics", "camera"):
        for row in locks["layers"][layer]["files"]:
            assert row.get("unchanged") is not False, (layer, row["path"])
    assert locks["layers"]["physics"]["replay_digest"] == V32_REPLAY_DIGEST
    assert locks["layers"]["physics"]["replay_event_digest"] == V32_EVENT_DIGEST
    changed = {row["path"] for layer in locks["layers"].values()
               for row in layer["files"] if row.get("unchanged") is False}
    assert changed == {
        "godot/scripts/race2_scene.gd",
        "godot/assets/marble_machine/course/race2_track_surface.gd",
    }, changed
    # The environment profile itself - the thing Part L actually locks - is one
    # of the files that did *not* move.
    profile = "godot/assets/marble_machine/environment/profiles/contained_bay_v301.json"
    rows = {row["path"]: row for row in locks["layers"]["environment"]["files"]}
    assert rows[profile]["unchanged"] is True
    for name, report in locks.get("reproduced", {}).items():
        assert report.get("identical") is True, name


# --- the instrument ---------------------------------------------------------


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    OUT, "CONTROL", "bands", "at_003.200.png")), reason="run `bands` first")
def test_the_rasteriser_agrees_with_the_renderer_about_the_deck():
    """The analytic instrument against the GPU, band by band.

    Cradle and lip agree to a fraction of a per cent. Wall and crown are checked
    as a **sum**: a crown four pixels wide on the delivery frame is one pixel at
    the rasteriser's 540, and a point sample cannot be narrower than its pixel.
    """
    import numpy as np
    from PIL import Image

    tool = _tool()
    _g, replay, cameras = tool.load(SOURCE)
    with open(os.path.join(OUT, "CONTROL", "race2_switchyard_8.geometry.json"),
              encoding="utf-8") as handle:
        rings = tool.run_rings(json.load(handle))

    for seconds in (3.200, 8.400, 15.400):
        path = os.path.join(OUT, "CONTROL", "bands", f"at_{seconds:07.3f}.png")
        image = np.asarray(Image.open(path).convert("RGB")).astype(int)
        total = image.shape[0] * image.shape[1]
        truth = {}
        for name, colour in tool.BANDS.items():
            truth[name] = float((np.abs(image - np.array(colour)).sum(2) < 60
                                 ).sum()) / total * 100.0
        camera = tool.camera_at(cameras, seconds, size=tool.EXPOSE_SIZE)
        buffers = tool.rasterise(camera, rings, tool.EXPOSE_SIZE, both=False)
        label = buffers["label"]
        cells = tool.EXPOSE_SIZE[0] * tool.EXPOSE_SIZE[1]
        mine = {name: float((label == k).sum()) / cells * 100.0
                for k, name in ((1, "cradle"), (2, "lip"), (3, "wall"),
                                (4, "crown"))}
        assert abs(mine["cradle"] - truth["cradle"]) < 0.05, seconds
        assert abs(mine["lip"] - truth["lip"]) < 0.20, seconds
        assert abs((mine["wall"] + mine["crown"])
                   - (truth["wall"] + truth["crown"])) < 0.60, seconds


@pytest.mark.skipif(not os.path.isfile(os.path.join(
    OUT, "S", "bands", "at_008.400.png")), reason="run `bands` first")
def test_the_renderer_agrees_that_the_deck_was_backfacing():
    """The root cause, in the renderer's own pixels.

    The same frame, the same geometry, the same material, the same camera - one
    field of difference, and the running surface goes from absent to nearly half
    the picture.
    """
    import numpy as np
    from PIL import Image

    def deck(path: str) -> float:
        image = np.asarray(Image.open(path).convert("RGB")).astype(int)
        hit = np.abs(image - np.array((255, 0, 0))).sum(2) < 60
        return float(hit.mean()) * 100.0

    before = deck(os.path.join(OUT, "CONTROL", "bands", "at_008.400.png"))
    after = deck(os.path.join(OUT, "S", "bands", "at_008.400.png"))
    assert before < 0.01
    assert after > 30.0
