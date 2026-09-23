"""Category 3, Test #2 redesign - the visual Phase 2A contract, under test.

Four things are checked here and they are different in kind.

**The consumer contract.** `satisfying/multishell_visual.py` and
`godot/scripts/multishell_scene.gd` may read the canonical V2 playback document
and may not compute a trajectory. Python cannot run GDScript, but it can read
it, so the scene is parsed as text and asserted against: no body, no collider,
no `_physics_process`, no clock of its own, and no import of the simulator on
the Python side.

**The shared constants.** Every pixel number in the report is predicted in
Python from a constant the *scene* draws with. If the two copies drift, the
report is a description of a render nobody made. So each shared constant is
read out of the GDScript and compared.

**The event mapping.** A spawn ripple that fired on something other than a
canonical `ball_spawn`, a break effect on something other than a `panel_break`,
or a panel drawn in a state its ledger does not have, would each be a
presentation that has started inventing. Each is checked against the document.

**The composition.** The safe area is a gate, not a preference, and the
candidate set is a rule rather than a taste. Both are asserted.

The Phase 1 simulation, schema and evaluator are untouched by this branch, and
one test asserts that by digest rather than by assertion in a document.
"""

from __future__ import annotations

import json
import math
import os
import re

import pytest

from satisfying import multishell_visual as visual
from satisfying.multishell import DEFAULT_CONFIG, SCHEMA_VERSION
from satisfying.multishell_playback import document_for, panel_state_at, position_at
from satisfying.tile_safe_area import DEFAULT_SAFE_AREA

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENE_GD = os.path.join(REPO, "godot", "scripts", "multishell_scene.gd")
RENDER_GD = os.path.join(REPO, "godot", "scripts", "multishell_render.gd")
RENDER_SCENE = os.path.join(REPO, "godot", "scenes", "MultishellRender.tscn")
SHORTLIST = os.path.join(REPO, visual.SHORTLIST_PATH)
MANIFEST = os.path.join(
    REPO, "docs", "validation", "category3_multiplying_shell_adjust_v3b",
    "phase3b_candidates.json",
)

# One seed carries most of the event-mapping work. 12818 is the busiest of the
# seven - 607 events, 19 breaks, 15 balls - so it exercises every branch.
PROOF_SEED = 15793


@pytest.fixture(scope="module")
def document():
    return document_for(PROOF_SEED)


@pytest.fixture(scope="module")
def scene_source() -> str:
    with open(SCENE_GD, encoding="utf-8") as handle:
        return handle.read()


def gd_code(source: str) -> str:
    """GDScript with its comments removed.

    The scene documents the bugs that cost the most time here by naming them -
    "a `RigidBody`", "the first version reset to zero". A test scanning the raw
    file would then fail on the comment explaining why the thing it is looking
    for is absent.
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


def gd_number(source: str, name: str) -> float:
    match = re.search(rf"^const {name} :?= (-?[0-9.]+)$", source, re.MULTILINE)
    assert match is not None, f"{name} is not a numeric constant in multishell_scene.gd"
    return float(match.group(1))


def gd_list(source: str, name: str) -> list[float]:
    match = re.search(rf"^const {name} :?= \[([^\]]*)\]", source, re.MULTILINE)
    assert match is not None, f"{name} is not a list constant in multishell_scene.gd"
    return [float(part) for part in match.group(1).replace("\n", "").split(",") if part.strip()]


# --------------------------------------------------------------------------
# Phase 1 is untouched
# --------------------------------------------------------------------------


def test_the_frozen_simulation_is_the_one_this_branch_was_cut_from():
    """The brief forbids modifying the Phase 1 simulation, schema or evaluator.

    A digest is the only form of that promise a test can keep: a change to any
    field of the operating configuration, or to the schema version, moves it.
    """
    assert SCHEMA_VERSION == visual.EXPECTED_SCHEMA_VERSION
    assert DEFAULT_CONFIG.digest() == visual.EXPECTED_CONFIG_DIGEST


def test_the_visual_module_never_imports_the_simulator():
    """A playback consumer that can call `simulate` will eventually call it."""
    with open(os.path.join(REPO, "satisfying", "multishell_visual.py"),
              encoding="utf-8") as handle:
        source = handle.read()
    for forbidden in ("from satisfying.multishell import",
                      "import satisfying.multishell\n",
                      "simulate(", "MultishellRun", "build_arena"):
        assert forbidden not in source, f"{forbidden} in multishell_visual.py"


# --------------------------------------------------------------------------
# The candidate set
# --------------------------------------------------------------------------


def test_the_candidate_set_is_the_rule_applied_to_the_phase_one_shortlist():
    with open(SHORTLIST, encoding="utf-8") as handle:
        shortlist = json.load(handle)
    kept = visual.candidate_seeds(shortlist)
    assert [entry["seed"] for entry in kept] == list(visual.CANDIDATE_SEEDS)
    assert 6 <= len(kept) <= 8, "the brief asks for approximately six to eight"
    for entry in kept:
        assert 20.0 <= entry["duration"] <= 26.0
        assert entry["first_split"] <= 3.0
        assert 8 <= entry["population"] <= 15
    # No seed outside the Phase 1 shortlist may appear: no new search was run.
    assert set(visual.CANDIDATE_SEEDS).issubset(set(shortlist["seeds"]))


def test_the_candidate_set_spans_both_routes_and_both_kinds_of_escaping_ball():
    with open(SHORTLIST, encoding="utf-8") as handle:
        shortlist = json.load(handle)
    manifest = visual.candidate_manifest(shortlist)
    coverage = manifest["coverage"]
    assert coverage["escape_route"]["opening"] >= 1
    assert coverage["escape_route"]["break"] >= 4
    assert coverage["escaping_ball"]["founder"] >= 1
    assert coverage["escaping_ball"]["descendant"] >= 4
    assert coverage["opening_dominant"], "no opening-dominant route in the set"


def test_the_committed_manifest_matches_the_rule():
    """Audio Phase 2B reads this file, so it has to be the same seven seeds."""
    assert os.path.isfile(MANIFEST), "run `multishell_visual_cli candidates`"
    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    assert manifest["seeds"] == list(visual.CANDIDATE_SEEDS)
    assert manifest["expected_config_digest"] == visual.EXPECTED_CONFIG_DIGEST
    assert manifest["config_digest"] == visual.EXPECTED_CONFIG_DIGEST
    assert manifest["rule"] == visual.CANDIDATE_RULE


def test_the_manifest_carries_the_phase_one_digest_of_every_seed():
    """A seed that has quietly become a different run has to fail loudly."""
    with open(MANIFEST, encoding="utf-8") as handle:
        manifest = json.load(handle)
    for entry in manifest["candidates"][:2]:
        document = document_for(int(entry["seed"]))
        assert document["digest"] == entry["digest"]


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def test_a_document_from_another_configuration_is_refused(document):
    assert visual.validate_document(document) == ""
    wrong = dict(document)
    wrong["config_digest"] = "0" * 64
    assert "configuration" in visual.validate_document(wrong)
    wrong = dict(document)
    wrong["schema"] = "category3-test2-multiplying-shell/1.0.0"
    assert "schema" in visual.validate_document(wrong)
    wrong = dict(document)
    wrong["shells"] = document["shells"][:4]
    assert "shells" in visual.validate_document(wrong)


# --------------------------------------------------------------------------
# The camera schedule
# --------------------------------------------------------------------------


def test_the_framing_comes_from_the_canonical_shell_exit_stream(document):
    marks = visual.frame_marks(document)
    assert marks, "a run that escapes crosses at least one shell"
    stages = [stage for _t, stage in marks]
    assert stages == sorted(stages), "the schedule is not monotone"
    assert stages == list(range(1, len(stages) + 1)), "a stage was skipped"
    exits = [e for e in document["events"] if e["kind"] == "shell_exit"]
    for at, _stage in marks:
        assert any(abs(float(e["t"]) - at) < 1e-12 for e in exits), (
            "a framing change that is not a canonical crossing"
        )


def test_the_framing_never_zooms_in(document):
    duration = float(document["summary"]["duration"])
    previous = -math.inf
    for index in range(2001):
        radius = visual.view_radius_at(document, duration * index / 2000.0)
        assert radius >= previous - 1e-12, "the framing went backwards"
        previous = radius


def test_the_framing_reaches_the_whole_arena_and_then_stops(document):
    duration = float(document["summary"]["duration"])
    radii = visual.shell_view_radii(document)
    assert visual.view_radius_at(document, 0.0) == pytest.approx(radii[0])
    assert visual.view_radius_at(document, duration) == pytest.approx(radii[-1], rel=1e-6)
    composition = visual.composition_report(document)
    # The climax is rendered by a camera that has not moved for seconds.
    assert composition["static_tail_seconds"] > 3.0
    assert composition["camera_moving_fraction"] < 0.20


def test_the_projection_of_the_play_plane_is_an_exact_uniform_scale(document):
    """Every pixel number in the report depends on this being true.

    The camera is perspective, which is what makes a panel's flank visible, but
    it looks straight down -Z and every canonical position is at z = 0, so the
    plane the physics lives in is projected by a constant.
    """
    radius = visual.view_radius_at(document, 3.0)
    scale = visual.pixels_per_unit(radius)
    a = visual.project((0.0, 0.0), radius)
    b = visual.project((10.0, 0.0), radius)
    c = visual.project((20.0, 0.0), radius)
    assert (b[0] - a[0]) == pytest.approx(10.0 * scale)
    assert (c[0] - b[0]) == pytest.approx(10.0 * scale)
    up = visual.project((0.0, 7.0), radius)
    assert (a[1] - up[1]) == pytest.approx(7.0 * scale)


def test_projected_shell_centres_are_exactly_aligned_on_every_frame(document):
    report = visual.centre_alignment_report(document, fps=60.0)
    assert report["passes"]
    assert report["maximum_disagreement_px"] <= 0.5


def test_camera_reframing_preserves_one_invariant_screen_centre(document):
    expected = (
        visual.FRAME_WIDTH * visual.ARENA_CENTRE_X_FRACTION,
        visual.FRAME_HEIGHT * visual.ARENA_CENTRE_Y_FRACTION,
    )
    for index in range(101):
        t = float(document["summary"]["duration"]) * index / 100.0
        centres = visual.projected_shell_centres(visual.view_radius_at(document, t))
        assert all(point == pytest.approx(expected, abs=1.0e-12) for point in centres)


def test_a_flank_is_drawn_inside_the_panel_it_belongs_to(document):
    """The whole "nothing outside the canonical silhouette" argument.

    A panel's body recedes to z = -depth, and a point behind the play plane
    projects *closer to the centre* than the front face, so the flank is always
    inside the collision silhouette and can never cover a ball.
    """
    for view in visual.shell_view_radii(document):
        distance = visual.camera_distance(view)
        for shell in document["shells"]:
            index = int(shell["shell_id"])
            radius = float(shell["radius"])
            depth = visual.PANEL_DEPTH[index]
            back = radius * distance / (distance + depth)
            assert back < radius, "a flank projected outside its own panel"
            assert visual.flank_width(radius, depth, view) == pytest.approx(
                radius - back)


# --------------------------------------------------------------------------
# Lineage
# --------------------------------------------------------------------------


def test_the_lineage_tint_is_a_function_of_the_document(document):
    first = visual.lineage_palette(document)
    second = visual.lineage_palette(document_for(PROOF_SEED))
    assert {k: v["rgb"] for k, v in first.items()} == \
        {k: v["rgb"] for k, v in second.items()}


def test_a_descendant_keeps_its_founder_childs_hue(document):
    palette = visual.lineage_palette(document)
    balls = {int(b["ball_id"]): b for b in document["balls"]}
    for ball_id, entry in palette.items():
        lineage = balls[ball_id]["lineage"]
        if len(lineage) < 2:
            assert entry["family"] == -1
            assert entry["rgb"] == visual.FOUNDER_RGB
            continue
        root = int(lineage[1])
        assert entry["family_root"] == root
        assert entry["family"] == palette[root]["family"], (
            "a descendant left its family"
        )


def test_the_palette_is_not_a_rainbow(document):
    """At most one hue per founder-child, plus the founder. Five is the ceiling
    because a founder can reproduce at most once per shell."""
    palette = visual.lineage_palette(document)
    families = {entry["family"] for entry in palette.values()}
    assert len(families) <= len(visual.FAMILY_RGB) + 1
    assert len(visual.FAMILY_RGB) == 5


def test_a_deeper_generation_is_paler_than_its_parent(document):
    palette = visual.lineage_palette(document)
    balls = {int(b["ball_id"]): b for b in document["balls"]}
    checked = 0
    for ball_id, entry in palette.items():
        parent = balls[ball_id]["parent_id"]
        if parent is None or int(parent) == 0:
            continue
        mine = sum(entry["rgb"]) / 3.0
        theirs = sum(palette[int(parent)]["rgb"]) / 3.0
        assert mine >= theirs - 1e-9, "a child was darker than its parent"
        checked += 1
    assert checked > 0


# --------------------------------------------------------------------------
# Damage, breaks, spawns: only what the document says
# --------------------------------------------------------------------------


def test_a_panel_is_drawn_in_the_state_its_ledger_gives(document):
    """Read the state, never accumulate the damage stream to get it."""
    ledger = {(int(e["shell_id"]), int(e["panel_id"])): e
              for e in document["panel_states"]}
    assert ledger, "the proof seed damaged nothing"
    for (shell_id, panel_id), entry in list(ledger.items())[:12]:
        for transition in entry["transitions"]:
            at = float(transition["t"])
            assert panel_state_at(document, shell_id, panel_id, at) == \
                transition["state"]
            assert panel_state_at(document, shell_id, panel_id, at - 1e-9) != \
                transition["state"]
        if entry["break_time"] is not None:
            after = float(entry["break_time"]) + 1e-6
            assert panel_state_at(document, shell_id, panel_id, after) == "broken"
            # No repair anywhere in the model.
            assert panel_state_at(
                document, shell_id, panel_id,
                float(document["summary"]["duration"])) == "broken"


def test_damage_marks_sit_where_the_ball_actually_hit(document):
    offsets = visual.panel_impact_offsets(document)
    assert offsets
    shells = {int(s["shell_id"]): s for s in document["shells"]}
    for (shell_id, panel_id), values in offsets.items():
        half = 0.5 * float(shells[shell_id]["chord_length"])
        for value in values:
            assert -half - 1e-6 <= value <= half + 1e-6, (
                "an impact offset outside the panel it is on"
            )


def test_every_state_the_scene_can_draw_is_a_canonical_state():
    assert visual.DAMAGE_STATES == (
        "healthy", "damaged", "critical", "fractured", "broken")
    assert len(visual.DAMAGE_EMISSION_ENERGY) == len(visual.DAMAGE_STATES)
    assert len(visual.DAMAGE_CRACK_COUNT) == len(visual.DAMAGE_STATES)
    # `healthy` and `broken` carry no marks: one has nothing to show and the
    # other is not there.
    assert visual.DAMAGE_CRACK_COUNT[0] == 0
    assert visual.DAMAGE_CRACK_COUNT[-1] == 0
    middle = visual.DAMAGE_CRACK_COUNT[1:-1]
    assert list(middle) == sorted(middle), "the crack ramp is not monotone"


def test_the_still_moments_are_canonical_event_times(document):
    moments = visual.event_moments(document)
    names = [entry["name"] for entry in moments]
    for required in ("a_opening", "b_first_split", "g_panel_break", "i_final_escape"):
        assert required in names
    duration = float(document["summary"]["duration"])
    for entry in moments:
        assert 0.0 <= entry["t"] <= duration + visual.RELEASE_SECONDS

    spawns = [float(e["t"]) for e in document["events"] if e["kind"] == "ball_spawn"]
    split = next(m for m in moments if m["name"] == "b_first_split")
    assert min(spawns) <= split["t"] <= min(spawns) + visual.SPAWN_LINK_SECONDS

    breaks = [float(e["t"]) for e in document["events"] if e["kind"] == "panel_break"]
    shot = next(m for m in moments if m["name"] == "g_panel_break")
    assert any(at <= shot["t"] <= at + visual.BREAK_RETRACT_SECONDS for at in breaks)

    escape = next(float(e["t"]) for e in document["events"] if e["kind"] == "escape")
    ending = next(m for m in moments if m["name"] == "i_final_escape")
    assert escape <= ending["t"] <= escape + visual.ESCAPE_FLARE_SECONDS


def test_the_ending_extends_only_the_ball_that_escaped(scene_code):
    """The document stops at the escape.

    Every other ball is mid-flight with a wall in front of it, and evaluating
    its flight record past the end would draw it through one. Only the escapee,
    which is outside the arena, may run on.
    """
    assert "func _escapee_time() -> float:" in scene_code
    body = scene_code.split("func _escapee_time() -> float:")[1].split("func ")[0]
    assert "release_seconds" in body
    apply_balls = scene_code.split("func _apply_balls(")[1].split("\nfunc ")[0]
    assert "_escapee_time()" in apply_balls
    assert "escapee" in apply_balls


# --------------------------------------------------------------------------
# Composition and the safe area
# --------------------------------------------------------------------------


def test_the_arena_clears_the_conservative_shorts_safe_area(document):
    report = visual.safe_area_report(document)
    assert report["safe_area"] == "shorts_conservative"
    assert report["arena_clear"], report["arena_regions"]
    assert report["min_clearance_px"] > 0.0
    assert report["ball_pass"], report
    assert report["ball_hidden_longest_seconds"] <= \
        DEFAULT_SAFE_AREA.ball_hidden_budget_seconds


def test_the_framing_is_the_largest_disc_the_rail_and_the_title_block_allow():
    """0.834 is derived, not chosen, and this is the derivation.

    The action rail starts at x=0.840 and the arena is centred at x=0.420, so
    the disc's radius cannot exceed 0.420 of the frame width. The pad turns
    that into the view radius, and what is left over is the clearance the
    safe-area report measures.
    """
    rail = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "action_rail")
    assert visual.ARENA_CENTRE_X_FRACTION < rail.left
    ceiling = 2.0 * min(visual.ARENA_CENTRE_X_FRACTION,
                        rail.left - visual.ARENA_CENTRE_X_FRACTION)
    assert visual.VIEW_DIAMETER_FRACTION < ceiling
    title = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "title_block")
    top = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "top_bar")
    half_height = 0.5 * visual.VIEW_DIAMETER_FRACTION * visual.FRAME_WIDTH \
        / visual.FRAME_HEIGHT
    assert visual.ARENA_CENTRE_Y_FRACTION - half_height > top.bottom
    assert visual.ARENA_CENTRE_Y_FRACTION + half_height < title.top


def test_the_ball_is_never_drawn_far_enough_into_a_panel_to_read_as_through_it():
    """1.375 is where a drawn ball first touches a panel it is only touching.

    `ball_radius + thickness/2` is the contact distance, so anything above that
    overlaps. 1.50 overlaps by 0.05 world units, which is 3.2 px at the opening
    framing and 0.9 px at the final one.
    """
    ball_radius = float(DEFAULT_CONFIG.ball_radius)
    contact = ball_radius + 0.5 * float(DEFAULT_CONFIG.panel_thickness)
    overlap = ball_radius * visual.BALL_DRAW_SCALE - contact
    assert overlap > 0.0, "the constant no longer needs this argument"
    assert overlap < 0.10, "the ball is drawn far enough in to read as through"
    # Worst case is the tightest framing, where a world unit is the most pixels.
    worst = visual.pixels_per_unit(min(
        float(s["radius"]) + 0.5 * float(s["thickness"]) + visual.VIEW_RADIUS_PAD
        for s in [{"radius": 6.0, "thickness": 0.3}]))
    assert overlap * worst < 4.0


def test_the_five_layers_are_drawn_with_increasing_weight(document):
    report = visual.shell_geometry_report(document)
    walls = [entry["at_final_stage"]["wall_px"] for entry in report]
    assert walls == sorted(walls), "the wall ramp is not monotone outward"
    assert walls[-1] > 3.0 * walls[0], "the outer wall is not visibly heavier"
    # Every layer is at least a few pixels of wall even at the widest framing.
    assert min(walls) > 5.0
    # The outermost shell is the most closed, and it has the narrowest gap.
    openness = [entry["open_fraction"] for entry in report]
    assert openness == sorted(openness, reverse=True)
    gaps = [entry["at_final_stage"]["gap_px"] for entry in report]
    assert gaps[-1] == min(gaps), "the last wall does not have the smallest gap"


def test_an_opening_is_bigger_than_the_ball_that_has_to_thread_it(document):
    report = visual.shell_geometry_report(document)
    ball = 2.0 * float(document["config"]["ball_radius"]) \
        * visual.BALL_DRAW_SCALE
    for entry in report:
        scale = entry["at_final_stage"]["pixels_per_unit"]
        assert entry["at_final_stage"]["gap_px"] > 2.5 * ball * scale, (
            f"shell {entry['shell_id']} reads as impassable"
        )


def test_the_balls_do_not_merge_into_one_blob_at_peak_population(document):
    report = visual.readability_report(document)
    assert report["peak_population"] >= 8
    assert report["population_by_third"] == sorted(report["population_by_third"])
    assert report["population_by_third"][-1] > \
        2 * report["population_by_third"][0], "the escalation does not read"
    assert not report["strobes"], report["max_step_diameters"]
    assert report["mean_blobs_per_ball"] > 0.80
    assert report["longest_triple_merge_seconds"] <= 0.75


# --------------------------------------------------------------------------
# The GDScript, read as text
# --------------------------------------------------------------------------


def test_the_render_scene_and_its_scripts_exist():
    for path in (SCENE_GD, RENDER_GD, RENDER_SCENE):
        assert os.path.isfile(path), path
    with open(RENDER_SCENE, encoding="utf-8") as handle:
        assert "multishell_render.gd" in handle.read()


@pytest.mark.parametrize(
    "name, python_value",
    [
        ("VIEW_DIAMETER_FRACTION", visual.VIEW_DIAMETER_FRACTION),
        ("ARENA_CENTRE_X_FRACTION", visual.ARENA_CENTRE_X_FRACTION),
        ("ARENA_CENTRE_Y_FRACTION", visual.ARENA_CENTRE_Y_FRACTION),
        ("VIEW_RADIUS_PAD", visual.VIEW_RADIUS_PAD),
        ("CAMERA_HFOV_DEGREES", visual.CAMERA_HFOV_DEGREES),
        ("FRAME_LEAD_SECONDS", visual.FRAME_LEAD_SECONDS),
        ("FRAME_EASE_SECONDS", visual.FRAME_EASE_SECONDS),
        ("BALL_DRAW_SCALE", visual.BALL_DRAW_SCALE),
        ("HALO_SCALE", visual.HALO_SCALE),
        ("BALL_RIM_SCALE", visual.BALL_RIM_SCALE),
        ("TRAIL_SECONDS", visual.TRAIL_SECONDS),
        ("TRAIL_SAMPLES", visual.TRAIL_SAMPLES),
        ("POST_DEPTH_FACTOR", visual.POST_DEPTH_FACTOR),
        ("PANEL_CHAMFER", visual.PANEL_CHAMFER),
        ("PANEL_SEGMENTS", visual.PANEL_SEGMENTS),
        ("DAMAGE_MARK_CHORD", visual.DAMAGE_MARK_CHORD),
        ("FRACTURE_GAP", visual.FRACTURE_GAP),
        ("FRACTURE_TILT_DEGREES", visual.FRACTURE_TILT_DEGREES),
        ("FRACTURE_RECESS", visual.FRACTURE_RECESS),
        ("SPAWN_FLASH_SECONDS", visual.SPAWN_FLASH_SECONDS),
        ("SPAWN_FLASH_RADIUS", visual.SPAWN_FLASH_RADIUS),
        ("SPAWN_LINK_SECONDS", visual.SPAWN_LINK_SECONDS),
        ("NEAR_MISS_SECONDS", visual.NEAR_MISS_SECONDS),
        ("BREAK_FLASH_SECONDS", visual.BREAK_FLASH_SECONDS),
        ("BREAK_RETRACT_SECONDS", visual.BREAK_RETRACT_SECONDS),
        ("BREAK_DEBRIS_SECONDS", visual.BREAK_DEBRIS_SECONDS),
        ("BREAK_DEBRIS_COUNT", visual.BREAK_DEBRIS_COUNT),
        ("BREAK_RING_SECONDS", visual.BREAK_RING_SECONDS),
        ("BREAK_RING_RADIUS", visual.BREAK_RING_RADIUS),
        ("ESCAPE_FLARE_SECONDS", visual.ESCAPE_FLARE_SECONDS),
        ("ESCAPE_RING_SECONDS", visual.ESCAPE_RING_SECONDS),
        ("RELEASE_SECONDS", visual.RELEASE_SECONDS),
        ("END_HOLD_SECONDS", visual.END_HOLD_SECONDS),
        ("GENERATION_WHITEN", visual.GENERATION_WHITEN),
        ("GENERATION_WHITEN_MAX", visual.GENERATION_WHITEN_MAX),
        ("GENERATION_ENERGY_STEP", visual.GENERATION_ENERGY_STEP),
        ("FACE_ENERGY", visual.FACE_ENERGY),
        ("BACK_ENERGY", visual.BACK_ENERGY),
        ("POST_EDGE_ENERGY", visual.POST_EDGE_ENERGY),
        ("POST_BASE_ENERGY", visual.POST_BASE_ENERGY),
        ("POST_EDGE_DEPTH", visual.POST_EDGE_DEPTH),
        ("TRAIL_HEAD_WIDTH", visual.TRAIL_HEAD_WIDTH),
        ("TRAIL_TAIL_WIDTH", visual.TRAIL_TAIL_WIDTH),
        ("BREAK_DEBRIS_SIZE", visual.BREAK_DEBRIS_SIZE),
        ("BREAK_DEBRIS_SPEED", visual.BREAK_DEBRIS_SPEED),
        ("BREAK_DEBRIS_SPEED_SPREAD", visual.BREAK_DEBRIS_SPEED_SPREAD),
        ("BALL_RIM_Z", visual.BALL_RIM_Z),
        ("TRAIL_Z", visual.TRAIL_Z),
        ("HALO_Z", visual.HALO_Z),
        ("EFFECT_Z", visual.EFFECT_Z),
        ("BACKDROP_Z", visual.BACKDROP_Z),
        ("GLOW_POOL_Z", visual.GLOW_POOL_Z),
        ("GLOW_POOL_RADII", visual.GLOW_POOL_RADII),
        ("GLOW_POOL_ALPHA", visual.GLOW_POOL_ALPHA),
    ],
)
def test_python_and_gdscript_agree_on_every_shared_constant(
    scene_source, name, python_value
):
    """Every pixel figure in the report is predicted from the Python copy.

    If the scene's copy drifts, the report describes a render nobody made.
    GDScript constants cannot be imported, so the file is read instead.
    """
    assert gd_number(scene_source, name) == pytest.approx(python_value)


@pytest.mark.parametrize(
    "name, python_value",
    [
        ("PANEL_DEPTH", list(visual.PANEL_DEPTH)),
        ("SHELL_METALLIC", list(visual.SHELL_METALLIC)),
        ("SHELL_ROUGHNESS", list(visual.SHELL_ROUGHNESS)),
        ("SHELL_ALBEDO_VALUE", list(visual.SHELL_ALBEDO_VALUE)),
        ("DAMAGE_EMISSION_ENERGY", list(visual.DAMAGE_EMISSION_ENERGY)),
        ("DAMAGE_CRACK_COUNT", [float(v) for v in visual.DAMAGE_CRACK_COUNT]),
    ],
)
def test_python_and_gdscript_agree_on_every_shared_ramp(
    scene_source, name, python_value
):
    assert gd_list(scene_source, name) == pytest.approx(python_value)


def test_the_scene_expects_the_frozen_configuration(scene_source):
    assert visual.EXPECTED_CONFIG_DIGEST in scene_source
    assert visual.EXPECTED_SCHEMA_VERSION in scene_source


def test_the_scene_contains_no_physics(scene_code):
    """The whole architecture in one assertion.

    A `RigidBody`, a `move_and_slide` or a `_physics_process` here would be a
    second simulation of a chaotic billiard with a reproducing population, and
    two of those do not agree - not just about a trajectory, about the cast.
    """
    for forbidden in (
        "RigidBody", "CharacterBody", "move_and_slide", "move_and_collide",
        "_physics_process", "PhysicsServer", "apply_impulse", "Area3D",
        "randf", "randi", "RandomNumberGenerator",
    ):
        assert forbidden not in scene_code, f"{forbidden} found in the scene"


def test_the_scene_never_advances_its_own_clock(scene_code):
    """`set_time` and `set_render_time` are the only ways in.

    A scene that accumulated `delta` would give a clip and a still different
    pictures of the same instant, and would drift against the canonical times
    at a rate that depends on how fast the render happened to run.
    """
    assert "func _process(" not in scene_code
    assert "func set_time(t: float)" in scene_code
    assert "func set_render_time(r: float)" in scene_code


def test_the_scene_reads_the_canonical_streams_and_not_others(scene_code):
    for required in ('playback["flights"]', 'playback["panel_states"]',
                     'playback["shells"]', 'playback["balls"]',
                     'playback["events"]'):
        assert required in scene_code, f"{required} is not read"
    # Every effect the scene has is keyed to an event kind that exists.
    read_events = scene_code.split("func _read_events()")[1].split("\nfunc ")[0]
    for kind in ("ball_spawn", "near_miss", "panel_break", "escape"):
        assert f'== "{kind}"' in read_events
    for invented in ("collision_flash", "combo", "streak", "milestone"):
        assert invented not in read_events


def test_one_effect_is_built_per_canonical_event_and_no_others(scene_code):
    """A spawn ripple on anything but a `ball_spawn` is a presentation that has
    started inventing, and the cheapest way to prevent it is to build the nodes
    from the event list itself rather than from a count."""
    build = scene_code.split("func _build_effects()")[1].split(chr(10) + "func ")[0]
    assert "for spawn in _spawns:" in build
    assert "for _entry in _near_misses:" in build
    assert "for _entry in _breaks:" in build
    # The three arrays are only ever filled from their own canonical kind.
    read = scene_code.split("func _read_events()")[1].split(chr(10) + "func ")[0]
    for array, kind in (("_spawns", "ball_spawn"),
                        ("_near_misses", "near_miss"),
                        ("_breaks", "panel_break")):
        block = read.split(f'== "{kind}"')[1].split("elif")[0]
        assert f"{array}.append(" in block
        for other in ("_spawns", "_near_misses", "_breaks"):
            if other != array:
                assert f"{other}.append(" not in block


def test_every_effect_is_timed_from_its_own_canonical_event(scene_code):
    """No effect has a clock of its own; each is `now - the event time`."""
    body = scene_code.split("func _apply_effects(")[1].split(chr(10) + "func ")[0]
    assert body.count("var since :=") >= 3
    for window in ("SPAWN_FLASH_SECONDS", "SPAWN_LINK_SECONDS",
                   "NEAR_MISS_SECONDS", "BREAK_RING_SECONDS",
                   "BREAK_DEBRIS_SECONDS", "ESCAPE_RING_SECONDS"):
        assert window in body, f"{window} is not the gate for its effect"
    assert 'float(spawn["t"])' in body
    assert 'float(miss["t"])' in body
    assert 'float(entry["t"])' in body
    assert 'float(_escape["t"])' in body


def test_the_scene_draws_no_text(scene_code):
    """The brief allows an arrow or a caption only if geometry alone fails.

    It did not: the narrowest opening in the arena is 3.7 ball diameters wide
    at the final framing and every opening is posted. So the render carries no
    type at all, and this is the assertion that keeps it that way.
    """
    for forbidden in ("Label.new", "Label3D", "RichTextLabel", "draw_string",
                      "TextMesh", "hook_text"):
        assert forbidden not in scene_code, f"{forbidden} in the scene"


def test_a_near_miss_is_reinforced_and_never_manufactured(scene_code):
    """Restrained feedback on a canonical event, scaled by the canonical
    closeness, and no retiming anywhere."""
    body = scene_code.split("func _apply_effects(")[1].split(chr(10) + "func ")[0]
    assert 'float(miss["radii"])' in body, "the spark ignores how close it was"
    assert "_light_post(" in body
    for forbidden in ("time_scale", "slow", "Engine.time_scale"):
        assert forbidden not in scene_code


def test_the_panel_basis_is_built_right_handed(scene_code):
    """A mirrored basis reverses every triangle's winding and the slab is culled.

    Godot's front face is the *clockwise* winding, which is the opposite of the
    convention most graphics writing assumes; Test #1 rendered an arena with
    none of its fifty-one tiles visible before this was found.
    """
    body = scene_code.split("func _oriented_basis(")[1].split("\nfunc ")[0]
    assert "z.cross(x)" in body
    assert "x.cross(z)" not in body


def test_no_texture_is_constructed_from_a_per_frame_path(scene_code):
    """Test #1 made 125,000 gradient textures in one audit.

    It took a render from 0.6 s to 28.8 s and crashed the engine during
    shutdown after writing a correct file. Every builder here runs once.
    """
    for function in ("_apply_panels", "_apply_balls", "_apply_effects",
                     "_apply_trail", "_apply_camera", "_apply_panel_marks"):
        body = scene_code.split(f"func {function}(")[1].split("\nfunc ")[0]
        for forbidden in ("GradientTexture2D.new", "Gradient.new",
                          "_radial_gradient(", "_ring_gradient(",
                          "StandardMaterial3D.new", "MeshInstance3D.new",
                          "QuadMesh.new", "SphereMesh.new", "ArrayMesh.new"):
            assert forbidden not in body, f"{forbidden} in {function}"


def test_the_audit_reports_in_doubles_not_through_a_vector2(scene_code):
    """A Godot `Vector2` is 32-bit.

    Reporting the audit through one costs about 1e-6 world units - a million
    times the arithmetic the scene does - and the first audit of this phase
    read 1.18e-06 for exactly that reason.
    """
    body = scene_code.split("func audit_state()")[1].split("\nfunc ")[0]
    assert "_position_pair(" in body
    assert "_position_row(" not in body


def test_the_renderer_refuses_a_document_it_should_not_draw(scene_code):
    body = scene_code.split("func validate_document()")[1].split("\nfunc ")[0]
    assert "EXPECTED_CONFIG_DIGEST" in body
    assert "EXPECTED_SCHEMA" in body
    assert "EXPECTED_SHELL_COUNT" in body
    with open(RENDER_GD, encoding="utf-8") as handle:
        render = gd_code(handle.read())
    assert "validate_document()" in render
    assert "_fail(" in render


# --------------------------------------------------------------------------
# The render configuration
# --------------------------------------------------------------------------


def test_the_render_config_digest_moves_when_the_look_moves():
    before = visual.render_config_digest()
    assert len(before) == 16
    original = visual.BALL_DRAW_SCALE
    try:
        visual.BALL_DRAW_SCALE = original + 0.01
        assert visual.render_config_digest() != before
    finally:
        visual.BALL_DRAW_SCALE = original
    assert visual.render_config_digest() == before


def test_the_render_config_names_the_safe_area_it_was_measured_against():
    config = visual.render_config()
    assert config["safe_area"] == DEFAULT_SAFE_AREA.fingerprint()
    assert config["config_digest"] == visual.EXPECTED_CONFIG_DIGEST
    assert config["frame"] == [1080, 1920]
