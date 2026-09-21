"""Phase 3: the playback document, the cast, and the renderer's half of the contract.

Phase 3 adds a renderer to a simulation that was already settled, so these
tests are almost entirely about one question: **can the presentation layer
change the run?** The architecture says no - Godot reads a document and
evaluates a closed form - and these tests are what makes that a claim with
teeth rather than a paragraph in a docstring.

Four groups:

**The document.** It round-trips losslessly, it describes the run it names, and
its own evaluators agree with `TileEscapeRun`'s to the last bit. A document
that lost precision would be a renderer drawing a nearby run.

**Frame arithmetic.** `activation_frames` is the bridge between a continuous
simulation and a discrete render, and it is the one place an off-by-one would
produce a video that looks right and is wrong.

**The cast.** Role selection is deterministic, each role means what it says,
and - the two the first implementation got wrong - the bands sit at their
centres and the contrast case is filmable.

**The GDScript.** The scene file is parsed as text and checked against the
Python constants it mirrors, and against the two mistakes that cost the most
time here: a mirrored tile basis and a per-frame texture allocation. A test
cannot run GDScript, but it can read it, and a constant that has drifted
between the two languages is exactly the kind of silent divergence that makes a
measured report wrong.

Nothing here launches Godot. The renders are *evidence*, produced by
`satisfying.tile_phase3_cli`, and a suite that demanded a GPU would not run
anywhere useful. The one test that reads the rendered evidence sits behind
`requires_evidence` and skips when `output/` is absent, which it is in any
fresh worktree - `output/` is gitignored. Everything else checks the Python,
the GDScript as text, and a synthetic audit built from the document.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import re

import pytest

from satisfying import tile_cast, tile_playback, tile_readability
from satisfying.tile_escape import simulate
from satisfying.tile_evaluator import evaluate
from satisfying.tile_sweep import PHASE2_ARENA, PHASE2_CONFIG

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_GD = os.path.join(REPO, "godot", "scripts", "tile_escape_scene.gd")
RENDER_GD = os.path.join(REPO, "godot", "scripts", "tile_escape_render.gd")
RENDER_SCENE = os.path.join(REPO, "godot", "scenes", "TileEscapeRender.tscn")

PHASE3_CONFIG = dataclasses.replace(PHASE2_CONFIG, speed=85.0)

# The Phase 3 cast's centre-band seed. A named constant rather than a fixture
# that re-sweeps: the 50,000-seed selection takes three minutes and these tests
# need one run.
CAST_SEED = 3530


@pytest.fixture(scope="module")
def run():
    return simulate(CAST_SEED, PHASE3_CONFIG, PHASE2_ARENA)


@pytest.fixture(scope="module")
def document(run):
    return tile_playback.playback_document(run)


@pytest.fixture(scope="module")
def scene_source() -> str:
    with open(SCENE_GD, "r", encoding="utf-8") as handle:
        return handle.read()


def gd_code(source: str) -> str:
    """GDScript with its comments removed.

    The scene documents the two bugs that cost the most time here, and does so
    by naming them - "a Godot scene with a `RigidBody2D`", "`Basis(along,
    normal, +Z)` is mirrored". A test scanning the raw file would then fail on
    the comment explaining why the thing it is looking for is absent. So the
    comments come off first, and what is left is the code.
    """
    stripped: list[str] = []
    for line in source.splitlines():
        quote = ""
        cut = len(line)
        for index, character in enumerate(line):
            if quote:
                if character == quote:
                    quote = ""
            elif character in "\"'":
                quote = character
            elif character == "#":
                cut = index
                break
        stripped.append(line[:cut])
    return "\n".join(stripped)


@pytest.fixture(scope="module")
def scene_code(scene_source) -> str:
    return gd_code(scene_source)


def gd_constant(source: str, name: str) -> float:
    match = re.search(rf"^const {name} :?= ([0-9.]+)$", source, re.MULTILINE)
    assert match is not None, f"{name} is not a constant in tile_escape_scene.gd"
    return float(match.group(1))


# --------------------------------------------------------------------------
# The document
# --------------------------------------------------------------------------


def test_the_document_describes_the_run_it_names(document):
    report = tile_playback.verify_document(document)
    assert report["digest_matches"]
    assert report["activation_order_matches"]
    assert report["activation_times_match_exactly"]
    assert report["completion_matches"]
    assert report["collision_count_matches"]


def test_json_round_trips_the_document_without_losing_a_bit(document, tmp_path):
    """The check that would catch "round to six decimals to shrink the file".

    Not an aesthetic point: a chaotic billiard rounded at the sixth decimal is
    a different run by the twentieth collision, and the renderer would draw
    that different run perfectly.
    """
    path = tmp_path / "playback.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
    reloaded = tile_playback.read_playback(str(path))
    assert reloaded["digest"] == document["digest"]
    assert reloaded["flights"] == document["flights"]
    assert reloaded["activations"] == document["activations"]
    assert reloaded["completion_seconds"] == document["completion_seconds"]


def test_a_document_of_another_kind_or_format_is_refused(tmp_path, document):
    wrong_kind = tmp_path / "wrong_kind.json"
    with open(wrong_kind, "w", encoding="utf-8") as handle:
        json.dump({"kind": "something_else"}, handle)
    with pytest.raises(tile_playback.PlaybackMismatch):
        tile_playback.read_playback(str(wrong_kind))

    future = tmp_path / "future.json"
    with open(future, "w", encoding="utf-8") as handle:
        json.dump({**document, "format": tile_playback.PLAYBACK_FORMAT + 1}, handle)
    with pytest.raises(tile_playback.PlaybackMismatch):
        tile_playback.read_playback(str(future))


def test_the_documents_position_agrees_with_the_runs_exactly(run, document):
    """Bit-for-bit, not to a tolerance.

    The two evaluate the same closed form over the same doubles, so any
    difference at all would mean one of them had started computing rather than
    replaying.
    """
    for step in range(0, 400):
        t = step * (run.completion_time / 400.0)
        assert tile_playback.position_at(document, t) == run.position_at(t)


def test_the_ball_holds_at_the_runs_end_rather_than_leaving_the_arena(document):
    """Past `end_seconds` the document defines no trajectory.

    Extrapolating the final flight sent the ball straight through the wall -
    0.6 s past completion at 85 wu/s is 51 world units, and the completion
    still showed a finished arena with no ball in it.
    """
    end = float(document["end_seconds"])
    at_end = tile_playback.position_at(document, end)
    for later in (end + 0.1, end + 0.6, end + 5.0):
        assert tile_playback.position_at(document, later) == at_end
    circumradius = float(document["arena"]["circumradius"])
    assert math.hypot(*at_end) <= circumradius


def test_activated_count_agrees_with_the_run_at_every_activation(run, document):
    for entry in document["activations"]:
        t = entry["t"]
        assert tile_playback.activated_count_at(document, t) == entry["count"]
        assert tile_playback.activated_count_at(document, t) == run.activated_count_at(t)


def test_the_document_carries_duplicate_hits_and_not_only_activations(document):
    """The renderer needs the repeats to show a bounce that is not progress."""
    duplicates = [hit for hit in document["collisions"] if not hit["new"]]
    assert duplicates, "a run at this operating point always has repeat hits"
    assert len(document["activations"]) == document["activated_tiles"]
    assert len(document["collisions"]) > len(document["activations"])


# --------------------------------------------------------------------------
# Frame arithmetic
# --------------------------------------------------------------------------


@pytest.mark.parametrize("fps", [24.0, 30.0, 60.0])
def test_each_activation_is_first_visible_on_its_own_frame(document, fps):
    """The frame named is the first one at or after the activation, and the one
    before it is genuinely before."""
    frames = tile_playback.activation_frames(document, fps)
    for entry, frame in zip(document["activations"], frames):
        assert frame / fps >= entry["t"] - 1.0e-12
        assert (frame - 1) / fps < entry["t"]


@pytest.mark.parametrize("fps", [24.0, 30.0, 60.0])
def test_activation_frames_never_go_backwards(document, fps):
    frames = tile_playback.activation_frames(document, fps)
    assert frames == sorted(frames)


def test_a_higher_frame_rate_cannot_reorder_activations(document):
    """The order is the document's at every rate; only the frame numbers move."""
    order = [entry["tile"] for entry in document["activations"]]
    for fps in (24.0, 30.0, 50.0, 60.0, 120.0):
        frames = tile_playback.activation_frames(document, fps)
        paired = sorted(zip(frames, range(len(order))))
        assert [order[index] for _frame, index in paired] == order


# --------------------------------------------------------------------------
# The cast
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def population():
    """A small sweep. Enough to exercise selection, cheap enough to run always."""
    evaluations = []
    final_tiles: dict[int, int | None] = {}
    for seed in range(2500):
        one = simulate(seed, PHASE3_CONFIG, PHASE2_ARENA)
        evaluations.append(evaluate(one))
        final_tiles[seed] = tile_cast.final_tile_index(one)
    return evaluations, final_tiles


def test_selection_is_deterministic(population):
    evaluations, final_tiles = population
    first = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    second = tile_cast.select_cast(
        list(reversed(evaluations)), final_tiles, PHASE2_ARENA
    )
    assert first.seeds == second.seeds


def test_no_seed_fills_two_roles(population):
    evaluations, final_tiles = population
    cast = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    assert len(set(cast.seeds)) == len(cast.seeds)


def test_each_band_lands_at_its_centre_and_not_at_its_edge(population):
    """The failure the first implementation had.

    `candidate_score` peaks at 32.5 s, so "highest-scoring accepted seed in
    25-30 s" returns a 29.9 s run and the fast band tests the middle again.
    """
    evaluations, final_tiles = population
    cast = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    by_role = {member.role: member for member in cast.members}
    for role, centre in tile_cast.BAND_CENTRES.items():
        if role not in by_role:
            continue
        seconds = by_role[role].completion_seconds
        assert seconds is not None
        assert abs(seconds - centre) <= tile_cast.BAND_HALF_WIDTH


def test_the_contrast_case_completes_every_tile_and_is_short_enough_to_film(
    population,
):
    """Both halves of "mathematically valid but visually questionable".

    Unbounded, this role picks the population's worst pathology - in the
    50,000-seed sweep a run that completes after 1,691 seconds, which teaches
    nobody anything about a 32-second one.
    """
    evaluations, final_tiles = population
    cast = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    contrast = [m for m in cast.members if m.role == "contrast"]
    if not contrast:
        pytest.skip("no rejected-but-completing seed in this population")
    member = contrast[0]
    assert not member.accepted
    assert member.failures
    assert member.completion_seconds is not None
    assert member.completion_seconds <= tile_cast.CONTRAST_MAX_SECONDS


def test_every_accepted_role_really_passes_every_acceptance_condition(population):
    evaluations, final_tiles = population
    cast = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    for member in cast.members:
        if member.role == "contrast":
            continue
        assert member.accepted, f"{member.role} chose a rejected seed"
        assert member.failures == ()


def test_the_final_tile_roles_are_on_the_sides_of_the_arena_they_claim(population):
    evaluations, final_tiles = population
    cast = tile_cast.select_cast(evaluations, final_tiles, PHASE2_ARENA)
    by_role = {member.role: member for member in cast.members}
    if "final_tile_high" in by_role:
        assert by_role["final_tile_high"].final_tile_height >= 2.0 / 3.0
    if "final_tile_low" in by_role:
        assert by_role["final_tile_low"].final_tile_height <= 1.0 / 3.0


def test_the_last_tile_to_light_is_the_one_the_selector_names():
    one = simulate(CAST_SEED, PHASE3_CONFIG, PHASE2_ARENA)
    index = tile_cast.final_tile_index(one)
    assert index is not None
    tile = PHASE2_ARENA.tiles[index]
    assert one.first_hit_time[tile.tile_id] == max(one.first_hit_time.values())
    assert one.first_hit_time[tile.tile_id] == one.completion_time


def test_a_run_that_never_completed_has_no_final_tile():
    truncated = dataclasses.replace(PHASE3_CONFIG, duration=2.0)
    short = simulate(CAST_SEED, truncated, PHASE2_ARENA)
    assert short.activated_tiles < short.total_tiles
    assert tile_cast.final_tile_index(short) is None


# --------------------------------------------------------------------------
# Composition and motion, predicted from the document
# --------------------------------------------------------------------------


def test_the_projection_is_a_pure_scale_because_the_camera_is_orthographic(document):
    """Two points the same distance apart in world units are the same distance
    apart in pixels, wherever they are in the frame."""
    scale = tile_readability.pixels_per_unit(document, 1080)
    for a, b in (((0.0, 0.0), (1.0, 0.0)), ((-8.0, 7.0), (-7.0, 7.0))):
        pa = tile_readability.project(document, a, 1080, 1920)
        pb = tile_readability.project(document, b, 1080, 1920)
        assert math.dist(pa, pb) == pytest.approx(scale, rel=1e-12)


def test_the_arena_occupies_the_frame_width_the_scene_says_it_does(document):
    geometry = tile_readability.frame_geometry(document, 1080, 1920)
    assert geometry["arena_occupancy_width"] == pytest.approx(
        tile_readability.ARENA_WIDTH_FRACTION, rel=1e-12
    )


def test_the_hook_and_the_counter_clear_the_arena(document):
    """Both at delivery size and at phone size, which is the one that matters."""
    for width, height in ((1080, 1920), (270, 480)):
        geometry = tile_readability.frame_geometry(document, width, height)
        assert geometry["hook_clearance_px"] > 0.0, "the hook overlaps the arena"
        assert geometry["counter_clearance_px"] > 0.0
        assert geometry["arena_side_margin_px"] >= 0.0


def test_the_ball_strobes_without_a_temporal_treatment(document):
    """Phase 1 warned about this and did not characterise it. Here it is.

    At 85 wu/s the ball moves further between two frames than it is wide, at
    both frame rates the brief asks about. No ball size fixes that: a ball wide
    enough to overlap at 30 fps would be a third of the arena across.
    """
    for fps in (30.0, 60.0):
        motion = tile_readability.motion_report(document, fps, 1080, 1920)
        assert motion["travel_px_median"] > motion["ball_drawn_diameter_px"]
        assert motion["frames_over_ball_diameter_fraction"] > 0.9


def test_the_trail_is_long_enough_to_bridge_a_frame_at_thirty(document):
    for fps in (30.0, 60.0):
        motion = tile_readability.motion_report(document, fps, 1080, 1920)
        assert motion["trail_covers_frame_step"]
        # And its samples overlap, or the trail is a dotted line rather than a
        # streak.
        assert motion["trail_sample_spacing_in_ball_radii"] < 1.0


def test_the_trail_is_a_time_and_so_does_not_change_with_the_frame_rate(document):
    lengths = {
        tile_readability.motion_report(document, fps, 1080, 1920)["trail_length_px"]
        for fps in (24.0, 30.0, 60.0, 120.0)
    }
    assert len(lengths) == 1


# --------------------------------------------------------------------------
# The GDScript, read as text
# --------------------------------------------------------------------------


def test_the_render_scene_and_its_scripts_exist():
    for path in (SCENE_GD, RENDER_GD, RENDER_SCENE):
        assert os.path.isfile(path), path
    with open(RENDER_SCENE, "r", encoding="utf-8") as handle:
        assert "tile_escape_render.gd" in handle.read()


@pytest.mark.parametrize(
    "name, python_value",
    [
        ("ARENA_WIDTH_FRACTION", tile_readability.ARENA_WIDTH_FRACTION),
        ("BALL_DRAW_SCALE", tile_readability.BALL_DRAW_SCALE),
        ("TRAIL_SECONDS", tile_readability.TRAIL_SECONDS),
        ("TRAIL_SAMPLES", tile_readability.TRAIL_SAMPLES),
        ("TILE_GAP_FRACTION", tile_readability.TILE_GAP_FRACTION),
        ("SAFE_MARGIN_FRACTION", tile_readability.SAFE_MARGIN_FRACTION),
        ("HOOK_TOP_FRACTION", tile_readability.HOOK_TOP_FRACTION),
        ("COUNTER_TOP_FRACTION", tile_readability.COUNTER_TOP_FRACTION),
    ],
)
def test_python_and_gdscript_agree_on_every_shared_constant(
    scene_source, name, python_value
):
    """`tile_readability` predicts pixel measurements from these numbers.

    If the scene's copy drifts, every predicted measurement in the report is
    quietly describing a render nobody made. GDScript constants cannot be
    imported into Python, so the file is read instead.
    """
    assert gd_constant(scene_source, name) == pytest.approx(python_value)


def test_the_scene_contains_no_physics(scene_code):
    """The whole architecture in one assertion.

    A `RigidBody`, a `move_and_slide` or a `_physics_process` in this file
    would be a second simulation of a chaotic billiard, and two simulations of
    a chaotic billiard do not agree.
    """
    for forbidden in (
        "RigidBody",
        "CharacterBody",
        "move_and_slide",
        "move_and_collide",
        "_physics_process",
        "PhysicsServer",
        "apply_impulse",
    ):
        assert forbidden not in scene_code, f"{forbidden} found in the scene"


def test_the_scene_never_advances_its_own_clock(scene_code):
    """`set_time` is the only way in, and `_process(delta)` is not implemented.

    A scene that accumulated `delta` would give a clip and a still different
    pictures of the same instant, and would drift against the canonical times
    at a rate that depends on how fast the render happened to run.
    """
    assert "func _process(" not in scene_code
    assert "func set_time(t: float)" in scene_code


def test_the_tile_basis_is_built_right_handed(scene_code):
    """The mirrored-basis bug, asserted so it cannot come back.

    The arena's vertices run counter-clockwise, so `Basis(along, normal, +Z)`
    has determinant -1 for every side; that reverses each triangle's winding,
    backface culling removes all fifty-one slabs, and the render is an empty
    arena with a ball in it. Building the second axis as `depth.cross(along)`
    is right-handed by construction.
    """
    assert "depth.cross(along)" in scene_code
    assert "Basis(along, normal," not in scene_code


def test_the_trail_does_not_allocate_a_texture_per_frame(scene_code):
    """`_radial_gradient` is called from the build path, never from `_apply_ball`.

    Calling it per sample per frame made 125,000 textures in one audit, took
    that audit from 0.6 s to 28.8 s, and crashed the engine during shutdown
    after the output had already been written correctly.
    """
    body = scene_code.split("func _apply_ball(")[1].split("\nfunc ")[0]
    assert "_radial_gradient()" not in body


def test_a_duplicate_hit_is_weaker_than_an_activation_in_kind_and_degree(
    scene_source, scene_code
):
    """With roughly two duplicates per activation, a duplicate that read like
    an activation would turn the progress signal into noise."""
    scale = gd_constant(scene_source, "DUP_HIT_PULSE_SCALE")
    assert 0.0 < scale < 0.5
    new_seconds = gd_constant(scene_source, "NEW_HIT_PULSE_SECONDS")
    dup_seconds = gd_constant(scene_source, "DUP_HIT_PULSE_SECONDS")
    assert dup_seconds < new_seconds
    # And different in kind: only a new hit moves the slab.
    tiles_body = scene_source.split("func _apply_tiles(")[1].split("\nfunc ")[0]
    assert "push = NEW_HIT_PUSH * pulse" in tiles_body
    assert "push = DUP" not in tiles_body


def test_the_renderer_checks_the_playback_format_before_drawing():
    with open(RENDER_GD, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "category3_tile_escape_playback" in source
    assert 'this renderer reads 1' in source


def test_the_renderer_clocks_on_the_frame_index_and_not_on_wall_time():
    """A render that crawls and one that flies must produce identical images."""
    with open(RENDER_GD, "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "_scene.set_time(float(index) / _fps)" in source
    assert "get_process_delta_time" not in gd_code(source)


# --------------------------------------------------------------------------
# The audit comparison, on a synthetic audit
# --------------------------------------------------------------------------


def _audit_for(document, fps: float) -> dict:
    """The audit a correct renderer would write, built from the document."""
    frames = tile_playback.activation_frames(document, fps)
    order = [entry["tile"] for entry in document["activations"]]
    last = max(frames)
    times, xs, ys, counts = [], [], [], []
    for index in range(last + 1):
        t = index / fps
        x, y = tile_playback.position_at(document, t)
        times.append(t)
        xs.append(x)
        ys.append(y)
        counts.append(tile_playback.activated_count_at(document, t))
    return {
        "kind": "category3_tile_escape_audit",
        "seed": document["seed"],
        "digest": document["digest"],
        "fps": fps,
        "width": 1080,
        "height": 1920,
        "frames": last + 1,
        "pixels_per_unit": tile_readability.pixels_per_unit(document, 1080),
        "final_activated": document["activated_tiles"],
        "total_tiles": document["total_tiles"],
        "first_lit_frame": {
            str(tile): frame for tile, frame in zip(order, frames)
        },
        "sample_t": times,
        "sample_x": xs,
        "sample_y": ys,
        "sample_count": counts,
    }


def test_a_correct_audit_compares_clean(document, tmp_path):
    for fps in (30.0, 60.0):
        path = tmp_path / f"audit_{int(fps)}.json"
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(_audit_for(document, fps), handle)
        report = tile_readability.compare_audit(document, str(path))
        assert report["playback_matches"]
        assert report["activation_order_matches"]
        assert report["activation_frames_match"]
        assert report["max_position_error_wu"] == 0.0


def test_an_audit_one_frame_out_is_caught(document, tmp_path):
    """The off-by-one a renderer gets by accumulating `delta`.

    It would produce a video that is one frame early everywhere and looks
    perfectly fine, which is exactly why it needs a test rather than an eye.
    """
    audit = _audit_for(document, 30.0)
    audit["first_lit_frame"] = {
        tile: frame - 1 for tile, frame in audit["first_lit_frame"].items()
    }
    path = tmp_path / "early.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(audit, handle)
    report = tile_readability.compare_audit(document, str(path))
    assert not report["activation_frames_match"]
    assert not report["playback_matches"]


def test_an_audit_of_a_different_run_is_refused(document, tmp_path):
    audit = _audit_for(document, 30.0)
    audit["digest"] = "0" * 64
    path = tmp_path / "other.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(audit, handle)
    with pytest.raises(tile_playback.PlaybackMismatch):
        tile_readability.compare_audit(document, str(path))


def test_a_nudged_ball_position_is_caught(document, tmp_path):
    """The tolerance is 1e-9 world units, which is a ten-thousandth of a pixel.

    It is not a visual tolerance and is not meant to be: the renderer
    evaluates the same closed form on the same doubles, so anything bigger than
    JSON round-trip noise means it computed rather than replayed.
    """
    audit = _audit_for(document, 30.0)
    audit["sample_x"] = list(audit["sample_x"])
    audit["sample_x"][40] += 1.0e-6
    path = tmp_path / "nudged.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(audit, handle)
    report = tile_readability.compare_audit(document, str(path))
    assert not report["positions_match"]
    assert not report["playback_matches"]


def test_an_audit_that_lit_the_wrong_number_of_tiles_is_caught(document, tmp_path):
    audit = _audit_for(document, 30.0)
    audit["final_activated"] = document["activated_tiles"] - 1
    path = tmp_path / "short.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(audit, handle)
    report = tile_readability.compare_audit(document, str(path))
    assert not report["activation_count_matches"]
    assert not report["playback_matches"]


# --------------------------------------------------------------------------
# The evidence, when it is present
# --------------------------------------------------------------------------

EVIDENCE = os.path.join(REPO, "output", "category3_v3")
requires_evidence = pytest.mark.skipif(
    not os.path.isdir(EVIDENCE),
    reason="output/ is gitignored; run `tile_phase3_cli` to produce the evidence",
)


@requires_evidence
def test_every_recorded_audit_agrees_with_its_document():
    """Over whatever the evidence directory happens to hold.

    Skipped in a fresh worktree, where `output/` does not exist. That is the
    right behaviour for a directory this repository does not track - the test
    is here to check evidence that was produced, not to demand a GPU.
    """
    checked = 0
    for name in sorted(os.listdir(os.path.join(EVIDENCE, "audit"))):
        seed = int(name.removeprefix("seed_"))
        document = tile_playback.read_playback(
            os.path.join(EVIDENCE, "playback", f"seed_{seed}.json")
        )
        directory = os.path.join(EVIDENCE, "audit", name)
        for audit_name in sorted(os.listdir(directory)):
            report = tile_readability.compare_audit(
                document, os.path.join(directory, audit_name)
            )
            assert report["playback_matches"], (seed, audit_name, report)
            assert report["final_activated"] == report["total_tiles"]
            checked += 1
    assert checked > 0
