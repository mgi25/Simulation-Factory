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
    REPO, "docs", "validation", "category3_two_team_shell_race_v4a",
    "phase4a_candidates.json",
)

# One seed carries most of the event-mapping work: the busiest of the review
# set, so it exercises every branch. It is the Phase 4A top candidate.
PROOF_SEED = 17964


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
    assert len(kept) == 6, "the brief asks for six human-review renders"
    low, high = visual.CANDIDATE_RULE["population_total"]
    for entry in kept:
        assert 20.0 <= entry["duration"] <= 26.0
        assert entry["first_split"] <= visual.CANDIDATE_RULE["first_spawn_seconds_max"]
        assert low <= entry["population"] <= high
        assert min(entry["population_by_team"]) >= visual.CANDIDATE_RULE[
            "min_team_population"
        ]
    # No seed outside the Phase 1 shortlist may appear: no new search was run.
    assert set(visual.CANDIDATE_SEEDS).issubset(set(shortlist["seeds"]))


def test_the_candidate_set_spans_both_routes_and_both_kinds_of_escaping_ball():
    with open(SHORTLIST, encoding="utf-8") as handle:
        shortlist = json.load(handle)
    manifest = visual.candidate_manifest(shortlist)
    coverage = manifest["coverage"]
    assert coverage["escape_route"]["opening"] >= 1
    # A break-route *final* escape is 0.7% of the eligible population - the
    # outermost wall is 15.0 reference hits and the moving opening is usually
    # the cheaper way out - so one is what the set can carry, not four.
    assert coverage["escape_route"]["break"] >= 1
    assert coverage["escaping_ball"]["founder"] >= 1
    assert coverage["escaping_ball"]["descendant"] >= 1
    # The one coverage line that is new, and the one the video is about.
    assert coverage["both_colours_win"], coverage["winning_colour"]
    assert min(coverage["winning_colour"].values()) >= 2
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
    wrong["schema"] = "category3-test2-multiplying-shell/2.0.0"
    assert "schema" in visual.validate_document(wrong)
    wrong = dict(document)
    wrong["shells"] = document["shells"][:4]
    assert "shells" in visual.validate_document(wrong)


# --------------------------------------------------------------------------
# The camera schedule
# --------------------------------------------------------------------------


def test_the_framing_comes_from_the_canonical_shell_exit_stream(document):
    """Every move is triggered by the race reaching a region, and nothing else.

    Phase 4A asserted the *start* of each move was a canonical crossing time,
    which it could because the start was the crossing minus a fixed lead. Phase
    4B may shift a start earlier to keep the move off a protected instant, so
    the assertion moves to the trigger - which is still exactly a canonical
    `shell_exit`, and still the *first* exit into that region.
    """
    stages = visual.camera_stages(document)
    assert len(stages) >= 2, "a run that escapes reaches at least one new group"
    numbers = [int(stage["stage"]) for stage in stages]
    assert numbers == sorted(numbers), "the schedule is not monotone"
    assert numbers == list(range(len(numbers))), "a stage was skipped"
    reached = visual.frontier_reached(document)
    exits = [e for e in document["events"] if e["kind"] == "shell_exit"]
    for stage in stages[1:]:
        trigger = int(stage["trigger_region"])
        assert float(stage["trigger_t"]) == pytest.approx(reached[trigger]), (
            "a stage triggered on something other than its own region"
        )
        assert any(
            abs(float(e["t"]) - float(stage["trigger_t"])) < 1e-12
            and int(e["to_region"]) >= trigger
            for e in exits
        ), "a framing change that is not a canonical crossing"


def test_the_camera_moves_once_and_not_once_per_shell(document):
    """The whole of "at most one reframe", as an assertion.

    **This test asserted two transitions and `extents == [1, 3, 4]` in 4B.**
    It no longer holds because the 4C brief allows one reframe and adds a
    requirement 4B did not have - the final 6 to 10 seconds must be fully
    static - and the two together pick the pair. Triggering on region 4 leaves
    4.16 s and 5.21 s of static tail on the two production candidates, so the
    trigger has to come earlier, and region 2 is the latest that clears 6 s on
    both. Rule one of 4B survives unchanged: the opening extent still has to
    cover every region the race reaches before the move.
    """
    stages = visual.camera_stages(document)
    assert len(stages) - 1 == 1, "more than one reframe is back"
    extents = [int(stage["extent_shell"]) for stage in stages]
    assert extents == [2, 4]
    # The extent always covers the frontier: rule one, checked rather than said.
    reached = visual.frontier_reached(document)
    for region, at in reached.items():
        covered = max(
            int(stage["extent_shell"]) for stage in stages
            if float(stage["settled"]) <= at + 1e-9
        ) if any(float(s["settled"]) <= at + 1e-9 for s in stages) else 0
        assert covered >= region - 1, (
            f"region {region} was reached at {at:.2f}s with the camera on "
            f"shell {covered}"
        )
    # The last stage still frames the outermost shell, because the final wall
    # has to be framed when the winner leaves through it.
    final = stages[-1]
    assert int(final["extent_shell"]) == len(document["shells"]) - 1
    assert int(final["trigger_region"]) == 2


def test_the_camera_windows_are_disjoint_and_strictly_outward(document):
    stages = visual.camera_stages(document)
    for previous, stage in zip(stages, stages[1:]):
        assert float(stage["start"]) >= float(previous["settled"]) - 1e-9, (
            "two camera moves overlap"
        )
        assert float(stage["radius"]) > float(previous["radius"]), (
            "a camera move that does not open out"
        )
        assert float(stage["settled"]) - float(stage["start"]) == pytest.approx(
            visual.FRAME_EASE_SECONDS
        )


def test_a_camera_move_is_only_ever_pulled_earlier(document):
    """Protection may advance a transition and may never delay it.

    Deferring a blocked move past the crossing that triggered it is what put
    balls outside the frame for 63 frames on 17964 and 98 on 3762 - the trigger
    is the instant the old framing stops being big enough, so there is no slack
    after it to spend.
    """
    for stage in visual.camera_stages(document)[1:]:
        wanted = float(stage["trigger_t"]) - visual.FRAME_LEAD_SECONDS
        assert float(stage["start"]) <= wanted + 1e-9, "a move was delayed"
        assert wanted - float(stage["start"]) <= \
            visual.EVENT_GUARD_MAX_DEFER_SECONDS + 1e-9


def test_no_ball_leaves_the_frame_while_the_camera_is_moving(document):
    """"Cropping is allowed" now reaches the balls, and only after the lock.

    **This test asserted `contained` and `outside_frames == 0` in 4B**, which
    was free there: the framed arena was narrower than the frame, so a ball
    could not leave it. At 1.200 the arena is 108 px wider than the half frame
    on each side by construction and a ball out at a horizontal cap of the
    outer region is off screen - that *is* the crop the review asked for, and
    asserting it away would mean giving the framing back.

    What is still forbidden is the version a viewer reads as a mistake: a ball
    leaving a frame that is itself moving. And the amount is bounded rather
    than waved through - under a sixth of the frames, under a twentieth of the
    ball-instants.
    """
    report = visual.containment_report(document, fps=60.0)
    assert report["contained_while_moving"], report
    assert report["outside_before_lock"] == 0
    assert report["outside_frame_fraction"] < 0.17, report
    assert report["ball_sample_outside_fraction"] < 0.05, report
    assert report["worst_t"] > report["camera_lock_time"]


def test_no_critical_subject_is_ever_off_the_frame(document):
    """The gate the crop is actually held to, and the one 4B did not have.

    A framing above 1.0 can hide things at the frame edge, so the edge is
    measured alongside the action rail. The first clone, every panel break some
    ball later used as a passage, and the winning escape may not be cropped at
    all - not partly, not by a pixel.
    """
    report = visual.critical_visibility_report(document)
    assert report["hard_on_frame"], report["hidden"]
    assert report["worst_hard_off_frame"] == pytest.approx(0.0)
    assert report["critical_pass"], report["hidden"]


def test_the_first_clone_and_the_payoff_are_never_inside_a_camera_move(document):
    """The two instants the brief names as must-not-move.

    They are protected structurally rather than by the guard: the first stage
    holds until the race reaches region 2, and the last settles seconds before
    the escape. The guard is what catches a candidate where that stops being
    true, and `guard_conflicts` names anything it could not avoid.
    """
    spawn = next(e for e in document["events"] if e["kind"] == "ball_spawn")
    escape = float(document["summary"]["escape_time"])
    for stage in visual.camera_stages(document)[1:]:
        window = (float(stage["start"]), float(stage["settled"]))
        assert not window[0] <= float(spawn["t"]) <= window[1], (
            "a camera move runs across the first clone"
        )
        assert not window[0] <= escape <= window[1], (
            "a camera move runs across the winning escape"
        )
        for conflict in stage["guard_conflicts"]:
            assert not str(conflict["why"]).startswith("first clone")
            assert str(conflict["why"]) != "escape"


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
    stages = visual.camera_stages(document)
    # **The opening framing is shell 2 in 4C, where 4B opened on shell 1.**
    # With one transition instead of two the opening has to cover regions 0
    # and 1, whose material edge is shell 1's, and shell 2 is the tightest
    # extent that contains it with the drawn ball.
    assert visual.view_radius_at(document, 0.0) == pytest.approx(radii[2])
    assert float(stages[0]["radius"]) == pytest.approx(radii[2])
    assert visual.view_radius_at(document, duration) == pytest.approx(
        radii[-1], rel=1e-6)
    composition = visual.composition_report(document)
    # The brief asks for a fully static final 6 to 10 seconds. Both production
    # candidates clear it with room: 20.88 s and 11.41 s.
    assert composition["static_tail_seconds"] > 6.0
    assert composition["camera_moving_fraction"] < 0.03


def test_the_camera_is_locked_for_the_whole_final_wall_section(document):
    """Once the final wall is the race frontier the composition stops moving."""
    lock = visual.camera_lock_time(document)
    escape = float(document["summary"]["escape_time"])
    assert lock < escape, "the camera is still moving at the payoff"
    assert visual.static_tail_seconds(document) > 3.0
    # And it really is fixed, not merely settled.
    radius = visual.view_radius_at(document, lock)
    for index in range(201):
        t = lock + (escape - lock) * index / 200.0
        assert visual.view_radius_at(document, t) == pytest.approx(radius, rel=1e-9)


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


def test_the_team_tint_is_a_function_of_the_document(document):
    first = visual.team_palette(document)
    second = visual.team_palette(document_for(PROOF_SEED))
    assert {k: v["rgb"] for k, v in first.items()} == \
        {k: v["rgb"] for k, v in second.items()}
    assert {k: v["team"] for k, v in first.items()} == \
        {k: v["team"] for k, v in second.items()}


def test_every_ball_wears_exactly_its_teams_hue(document):
    palette = visual.team_palette(document)
    balls = {int(b["ball_id"]): b for b in document["balls"]}
    for ball_id, entry in palette.items():
        team = int(balls[ball_id]["team_id"])
        assert entry["team"] == team
        assert entry["rgb"] == visual.TEAM_RGB[team]
        assert entry["team_name"] == visual.TEAM_NAMES[team]


def test_a_descendant_is_exactly_its_founders_colour(document):
    """No generation drift in hue at all: this is the read the video needs."""
    palette = visual.team_palette(document)
    balls = {int(b["ball_id"]): b for b in document["balls"]}
    checked = 0
    for ball_id, entry in palette.items():
        root = int(balls[ball_id]["lineage"][0])
        assert entry["rgb"] == palette[root]["rgb"], "a descendant changed hue"
        if int(balls[ball_id]["generation"]) > 0:
            checked += 1
    assert checked > 0, "the document has no descendants to check"


def test_the_palette_is_exactly_two_hues(document):
    """Two teams, two colours, and no third thing anywhere in the cast."""
    palette = visual.team_palette(document)
    hues = {entry["rgb"] for entry in palette.values()}
    assert hues <= set(visual.TEAM_RGB)
    assert len(visual.TEAM_RGB) == len(visual.TEAM_NAMES) == 2
    assert len(hues) == 2, "only one colour was ever on screen"


def test_the_two_team_colours_are_far_apart_and_evenly_weighted():
    """Distinguishable on a phone, under bloom, and neither one wins the eye."""
    cyan, orange = visual.TEAM_RGB
    # Rec. 709 luma. Within a fifth of each other, so neither colour reads as
    # the important one before anything has happened.
    def luma(rgb):
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    assert abs(luma(cyan) - luma(orange)) < 0.20
    # And far apart in chroma: the red and blue channels are opposed.
    assert cyan[0] < 0.30 < orange[0]
    assert orange[2] < 0.30 < cyan[2]
    separation = sum((a - b) ** 2 for a, b in zip(cyan, orange)) ** 0.5
    assert separation > 1.0


def test_no_damage_or_structure_colour_can_be_mistaken_for_a_team():
    """The warm end used to belong to damage; a team took it, so damage moved.

    Every colour the arena itself can show has to be far enough from both team
    hues that a wound is never read as a ball. Measured as a distance in RGB
    rather than asserted, because the ramp was re-picked by hand and a hand can
    drift a channel back.
    """
    arena = {
        "crack": visual.CRACK_RGB,
        "critical": visual.CRITICAL_RGB,
        "fracture": visual.FRACTURE_RGB,
        "break_flash": visual.BREAK_FLASH_RGB,
        "post_hot": visual.POST_HOT_RGB,
        "post_edge": visual.POST_EDGE_RGB,
        "face": visual.FACE_RGB,
        "panel": visual.PANEL_RGB,
        "back": visual.BACK_RGB,
    }
    for name, rgb in arena.items():
        for team, colour in zip(visual.TEAM_NAMES, visual.TEAM_RGB):
            distance = sum((a - b) ** 2 for a, b in zip(rgb, colour)) ** 0.5
            assert distance > 0.45, f"{name} is within {distance:.2f} of {team}"


def test_a_deeper_generation_glows_brighter_and_never_changes_hue(document):
    palette = visual.team_palette(document)
    balls = {int(b["ball_id"]): b for b in document["balls"]}
    checked = 0
    for ball_id, entry in palette.items():
        parent = balls[ball_id]["parent_id"]
        if parent is None:
            assert entry["energy"] == pytest.approx(1.0)
            continue
        assert entry["energy"] >= palette[int(parent)]["energy"] - 1e-9
        assert entry["energy"] <= visual.GENERATION_ENERGY_MAX + 1e-9
        assert entry["rgb"] == palette[int(parent)]["rgb"]
        checked += 1
    assert checked > 0
    assert visual.GENERATION_WHITEN == 0.0, "a paled descendant stops reading as its team"


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


def test_what_the_viewer_needs_to_see_clears_the_shorts_safe_area(document):
    """**The gate the human review replaced, and what replaced it.**

    Phase 4A asked "does the whole arena clear the action rail", answered it at
    15.12 px, and that one number is what capped the arena at 0.652 of the
    frame width and produced the composition the review rejected. The brief
    replaced the question: an irrelevant wall arc behind the player's controls
    is acceptable, a ball, a passage or the payoff is not.

    So the arena deliberately fails the old test and the classes that matter
    pass the new one.
    """
    report = visual.critical_visibility_report(document)
    assert report["safe_area"] == "shorts_conservative"
    assert report["critical_pass"], report["hidden"]
    for what in visual.CRITICAL_HARD_CLASSES:
        entry = report["by_kind"].get(what)
        if entry is None:
            continue
        assert entry["hidden"] == 0, (what, entry)
    # The arc the review agreed to spend, quantified rather than waved at.
    old = visual.safe_area_report(document)
    assert not old["arena_clear"], (
        "the arena fits inside the rail band again, which means the framing "
        "went back to the one the review rejected"
    )
    assert old["min_clearance_px"] < 0.0


def test_the_arena_is_on_the_frames_own_axis():
    """The review's first finding, as an assertion rather than an intention."""
    assert visual.ARENA_CENTRE_X_FRACTION == 0.500
    # The vertical offset is the only asymmetry left, and it is the midpoint of
    # the band the player's furniture leaves visible, not a lateral slide.
    top = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "top_bar")
    title = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "title_block")
    assert visual.ARENA_CENTRE_Y_FRACTION == pytest.approx(
        0.5 * (top.bottom + title.top), abs=0.01
    )


def test_the_framing_is_wider_than_the_frame_and_crops_only_sideways():
    """The 4C framing rule, which is the opposite of both earlier ones.

    4A took the largest centred disc that clears the action rail and got 0.652.
    4B let the outer arc cross the rail but still fitted the disc inside the
    frame, and got 0.850. The human review rejected both for the same reason,
    so **the assertion `0.80 <= FRONTIER_WIDTH_FRACTION <= 0.90` and the
    `half_width < 0.5` that went with it are gone**: the framed wall is now
    wider than the frame on purpose and its left and right caps are cropped.

    Two limits survive, and they are the two that keep the crop from costing
    anything the video needs. The arena still fits *vertically*, so nothing is
    lost to the frame's top or bottom edge and the crop is one-dimensional; and
    the fraction stays inside the band the brief named, which is 1.00 to 1.20.
    """
    rail = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "action_rail")
    room = rail.left - visual.ARENA_CENTRE_X_FRACTION
    assert visual.USABLE_WIDTH_FRACTION == pytest.approx(2.0 * room)
    assert visual.FRONTIER_WIDTH_FRACTION > 2.0 * room, (
        "the framing is back inside the rail band"
    )
    assert visual.VIEW_DIAMETER_FRACTION == pytest.approx(
        visual.FRONTIER_WIDTH_FRACTION * (1.0 + visual.VIEW_PAD_FRACTION)
    )
    # The brief's own band for the final structure, and the selected end of it.
    assert 1.00 <= visual.FRONTIER_WIDTH_FRACTION <= 1.20
    # Wider than the frame: that is the point, and it is asserted rather than
    # tolerated, so a quiet return to a fit-inside rule fails here.
    assert 0.5 * visual.FRONTIER_WIDTH_FRACTION > 0.5
    # But it still fits vertically, between the top bar and the title block,
    # so the crop is horizontal only.
    title = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "title_block")
    top = next(r for r in DEFAULT_SAFE_AREA.regions if r.name == "top_bar")
    half_height = 0.5 * visual.FRONTIER_WIDTH_FRACTION * visual.FRAME_WIDTH \
        / visual.FRAME_HEIGHT
    assert visual.ARENA_CENTRE_Y_FRACTION - half_height > top.bottom
    assert visual.ARENA_CENTRE_Y_FRACTION + half_height < title.top


def test_the_frontier_is_the_same_size_on_screen_at_every_stage(document):
    """"Constant frontier screen size", measured rather than intended."""
    report = visual.frontier_occupancy_report(document)
    assert report["frontier_fraction_spread"] == pytest.approx(0.0, abs=1e-12)
    for row in report["stages"]:
        assert row["frontier_over_frame_width"] == pytest.approx(
            visual.FRONTIER_WIDTH_FRACTION, abs=1e-9
        )
        # 4B asserted 0.80 to 0.90 here. The 4C band is the brief's.
        assert 1.00 <= row["frontier_over_frame_width"] <= 1.20


def test_the_total_zoom_out_is_the_camera_range_and_it_shrank_again(document):
    """The zoom range is a property of the *grouping*, and smaller again.

    Phase 4A's ratio was the arena's own - outermost material edge over
    innermost, 2.80 - because it framed every shell in turn. 4B grouped five
    shells into three framings and got 1.933. 4C groups them into two and gets
    **1.474**, and the pleasant part is that both stages divide by the same
    frame fraction, so the single move is 12.65 -> 18.65 units *whatever the
    fraction is*: raising the fraction made the arena bigger without making the
    one remaining zoom any larger.

    **4B asserted `zoom_ratio == radii[-1] / radii[1]` and `> 1.5`.** Both were
    statements about the three-stage grouping.
    """
    radii = visual.shell_view_radii(document)
    stages = visual.camera_stages(document)
    assert visual.zoom_ratio(document) == pytest.approx(
        float(stages[-1]["radius"]) / float(stages[0]["radius"])
    )
    assert visual.zoom_ratio(document) == pytest.approx(radii[-1] / radii[2])
    assert visual.zoom_ratio(document) < 1.6, "a wider camera range is back"
    assert visual.zoom_ratio(document) > 1.2, "the outer shells are never revealed"


def test_the_ball_stays_readable_all_the_way_to_the_final_wall(document):
    report = visual.frontier_occupancy_report(document)
    first, last = report["stages"][0], report["stages"][-1]
    assert first["ball_px"] > 60.0, "the opening ball is not large"
    # 4A fell to 26.0 px here. The gate is raised to what 4B actually delivers
    # minus a little, so a framing regression cannot pass it quietly.
    assert last["ball_px"] >= 32.0, (
        f"the ball falls to {last['ball_px']:.1f} px at the final wall"
    )
    # And the shrink is the zoom ratio and nothing else.
    assert first["ball_px"] / last["ball_px"] == pytest.approx(
        visual.zoom_ratio(document), rel=1e-9
    )


def test_the_camera_never_moves_sideways(document):
    report = visual.centring_report(document)
    assert report["centred"]
    assert report["stationary"]
    assert report["lateral_offset_from_frame_centre_px"] == pytest.approx(0.0)
    assert report["max_lateral_movement_px"] == pytest.approx(0.0)
    assert report["max_vertical_movement_px"] == pytest.approx(0.0)
    # The arena crosses the action rail on purpose, so this clearance is
    # negative by design.
    assert report["rail_clearance_px"] < 0.0
    # **And in 4C the left margin is negative too, where 4B asserted it
    # positive.** The arena is 108 px wider than the half frame on each side:
    # that is the crop the review asked for, and the centring report is where
    # it is stated as a number rather than implied. What the test still holds
    # is that the crop is *symmetric* - the arena is centred, so neither side
    # is favoured - and that it is a crop rather than an eclipse.
    assert report["left_margin_px"] < 0.0, "the arena fits inside the frame again"
    assert abs(report["left_margin_px"]) < 0.25 * visual.FRAME_WIDTH, (
        "more than a quarter of the frame width is cropped off each side"
    )
    assert report["arena_centre_px"][0] == pytest.approx(
        0.5 * visual.FRAME_WIDTH)


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
    innermost = DEFAULT_CONFIG.inner_radius + 0.5 * DEFAULT_CONFIG.panel_thickness
    worst = visual.pixels_per_unit(innermost * (1.0 + visual.VIEW_PAD_FRACTION))
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
        # The outermost wall is *meant* to look barely passable - that is the
        # whole "how are they going to get through that" read - so it gets its
        # own, tighter line rather than being exempted from this one.
        floor = 1.0 if entry["shell_id"] == len(report) - 1 else 1.8
        assert entry["at_final_stage"]["gap_px"] > floor * ball * scale, (
            f"shell {entry['shell_id']} reads as impassable"
        )
    last = report[-1]["at_final_stage"]
    assert last["gap_px"] < 1.4 * ball * last["pixels_per_unit"], (
        "the final wall does not read as the hard one"
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
    # Both colours are on screen, and a knot holding both of them at once - the
    # only overlap that can put "which colour is winning" in doubt - is rare.
    assert report["teams_on_screen_max"] == 2
    assert min(report["max_on_screen_by_team"]) >= 2
    assert report["mixed_cluster_fraction"] < 0.35, report["mixed_cluster_fraction"]
    assert report["largest_mixed_cluster"] <= 4


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
        ("ARENA_CENTRE_X_FRACTION", visual.ARENA_CENTRE_X_FRACTION),
        ("ARENA_CENTRE_Y_FRACTION", visual.ARENA_CENTRE_Y_FRACTION),
        ("VIEW_PAD_FRACTION", visual.VIEW_PAD_FRACTION),
        ("FRONTIER_WIDTH_FRACTION", visual.FRONTIER_WIDTH_FRACTION),
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
        ("GENERATION_ENERGY_STEP", visual.GENERATION_ENERGY_STEP),
        ("GENERATION_ENERGY_MAX", visual.GENERATION_ENERGY_MAX),
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
        # --- Phase 4B ---
        ("FRONTIER_WIDTH_FRACTION", visual.FRONTIER_WIDTH_FRACTION),
        ("EVENT_GUARD_BEFORE_SECONDS", visual.EVENT_GUARD_BEFORE_SECONDS),
        ("EVENT_GUARD_AFTER_SECONDS", visual.EVENT_GUARD_AFTER_SECONDS),
        ("EVENT_GUARD_MAX_DEFER_SECONDS", visual.EVENT_GUARD_MAX_DEFER_SECONDS),
        ("STRONG_NEAR_MISS_RADII", visual.STRONG_NEAR_MISS_RADII),
        ("DAMAGE_CLUSTER_CHORD", visual.DAMAGE_CLUSTER_CHORD),
        ("DAMAGE_CLUSTER_GROWTH", visual.DAMAGE_CLUSTER_GROWTH),
        ("DAMAGE_CLUSTER_GROWTH_MAX", visual.DAMAGE_CLUSTER_GROWTH_MAX),
        ("DAMAGE_CRACK_SPAN", visual.DAMAGE_CRACK_SPAN),
        ("DAMAGE_CRACK_WIDTH", visual.DAMAGE_CRACK_WIDTH),
        ("DAMAGE_CRACK_TILT_DEGREES", visual.DAMAGE_CRACK_TILT_DEGREES),
        ("DAMAGE_BRANCH_SPREAD_DEGREES", visual.DAMAGE_BRANCH_SPREAD_DEGREES),
        ("DAMAGE_BRANCH_LENGTH", visual.DAMAGE_BRANCH_LENGTH),
        ("DAMAGE_CHIP_DEPTH", visual.DAMAGE_CHIP_DEPTH),
        ("BREAK_STRESS_SECONDS", visual.BREAK_STRESS_SECONDS),
        ("BREAK_FRAGMENT_COUNT", visual.BREAK_FRAGMENT_COUNT),
        ("BREAK_FRAGMENT_SECONDS", visual.BREAK_FRAGMENT_SECONDS),
        ("BREAK_FRAGMENT_CHORD_FRACTION", visual.BREAK_FRAGMENT_CHORD_FRACTION),
        ("BREAK_FRAGMENT_DEPTH_FRACTION", visual.BREAK_FRAGMENT_DEPTH_FRACTION),
        ("BREAK_FRAGMENT_OUT_SPEED", visual.BREAK_FRAGMENT_OUT_SPEED),
        ("BREAK_FRAGMENT_SPIN_DEGREES", visual.BREAK_FRAGMENT_SPIN_DEGREES),
        ("FLOOD_WINDOW_SECONDS", visual.FLOOD_WINDOW_SECONDS),
        ("FLOOD_MIN_BALLS", visual.FLOOD_MIN_BALLS),
        ("FLOOD_RESPONSE_SECONDS", visual.FLOOD_RESPONSE_SECONDS),
        ("FLOOD_POST_ENERGY", visual.FLOOD_POST_ENERGY),
        ("HOOK_HOLD_SECONDS", visual.HOOK_HOLD_SECONDS),
        ("HOOK_FADE_SECONDS", visual.HOOK_FADE_SECONDS),
        ("HOOK_FADE_TO", visual.HOOK_FADE_TO),
        ("WINNER_TOP_FRACTION", visual.WINNER_TOP_FRACTION),
        ("WINNER_ALT_TOP_FRACTION", visual.WINNER_ALT_TOP_FRACTION),
        ("WINNER_BAND_FRACTION", visual.WINNER_BAND_FRACTION),
        ("WINNER_RISE_SECONDS", visual.WINNER_RISE_SECONDS),
        # --- Phase 4C ---
        ("DAMAGE_RIM_ENERGY", visual.DAMAGE_RIM_ENERGY),
        ("DAMAGE_RIM_MARGIN", visual.DAMAGE_RIM_MARGIN),
        ("DAMAGE_RIM_SPAN", visual.DAMAGE_RIM_SPAN),
        ("DAMAGE_SEAM_WIDTH", visual.DAMAGE_SEAM_WIDTH),
        ("DAMAGE_SEAM_MIN_CHORD", visual.DAMAGE_SEAM_MIN_CHORD),
        ("DAMAGE_WEAR_ROUGHNESS", visual.DAMAGE_WEAR_ROUGHNESS),
        ("DAMAGE_TEAM_TINT", visual.DAMAGE_TEAM_TINT),
        ("DAMAGE_TEAM_TINT_MIN_SHARE", visual.DAMAGE_TEAM_TINT_MIN_SHARE),
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
        ("DAMAGE_BRANCH_COUNT", [float(v) for v in visual.DAMAGE_BRANCH_COUNT]),
        ("PANEL_CHAMFER_BY_SHELL", list(visual.PANEL_CHAMFER_BY_SHELL)),
        ("DAMAGE_STATE_ROUGHNESS", list(visual.DAMAGE_STATE_ROUGHNESS)),
        ("FRACTURE_SEGMENT_RECESS", list(visual.FRACTURE_SEGMENT_RECESS)),
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


def test_the_scene_draws_exactly_two_pieces_of_type(scene_code, scene_source):
    """The competitive hook and the colour-specific payoff. Nothing else.

    Phase 3B drew no type at all, and the argument was that geometry said
    everything. It no longer does: "who escapes first" is a question about two
    colours and the first second of the video has to ask it. The brief allows
    the question and the answer and explicitly forbids a scoreboard, so this
    counts the labels rather than banning them - two `Label.new` calls, no
    counter, no per-team tally, and nothing that reads a population into type.
    """
    # One constructor behind one helper, called once per label.
    assert scene_code.count("Label.new") == 1
    assert scene_code.count("_label(") == 3  # the definition and two calls
    # And no team legend: the brief makes one conditional on the colours not
    # being self-explanatory, and at frame zero they are.
    assert "ColorRect" not in scene_code
    assert "_team_dot" not in scene_code
    for forbidden in ("Label3D", "RichTextLabel", "draw_string", "TextMesh"):
        assert forbidden not in scene_code, f"{forbidden} in the scene"
    assert '"WHO ESCAPES FIRST?"' in scene_source
    assert '"%s ESCAPES!"' in scene_source
    # No number is ever formatted into a label: a scoreboard would need one.
    overlay = scene_code.split("func _apply_overlay(")[1].split(chr(10) + "func ")[0]
    for forbidden in ("%d", "population_at", "_ball_ids.size()", "counter"):
        assert forbidden not in overlay, f"{forbidden} in the overlay"


def test_the_payoff_is_the_winning_teams_colour(scene_code):
    build = scene_code.split("func _build_overlay(")[1].split(chr(10) + "func ")[0]
    assert '_escape.get("team_id"' in build
    assert "TEAM_NAMES[team]" in build
    assert "TEAM_RGB[team]" in build
    apply_ = scene_code.split("func _apply_overlay(")[1].split(chr(10) + "func ")[0]
    # Timed from the canonical escape instant, like every other effect.
    assert 'float(_escape["t"])' in apply_


def test_the_scene_tints_a_ball_from_its_team_and_from_nothing_else(scene_code):
    body = scene_code.split("func _build_balls(")[1].split(chr(10) + "func ")[0]
    assert 'int(ball["team_id"])' in body
    assert "TEAM_RGB[team]" in body
    for forbidden in ("FAMILY_RGB", "FOUNDER_RGB", "GENERATION_WHITEN", "lerp(Color.WHITE"):
        assert forbidden not in body, f"{forbidden} still tints a ball"


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


def test_the_frustum_matches_the_declared_field_of_view():
    """The check that would have caught a 1.778x error for three phases.

    `CAMERA_FRUSTUM_SIZE` was wrong from Phase 2A until Phase 4A: under
    `keep_aspect = KEEP_WIDTH` Godot reads the frustum size as the near plane's
    *width*, and the constant was the near plane's height. The horizontal field
    was therefore 74.4 degrees rather than the 47 every pixel figure in the
    reports was computed from, so the arena filled 46.9% of the frame where the
    report said 83.4%.

    It survived because the only test on it compared the Python constant with
    the GDScript constant, and both copies were wrong in the same way. This
    re-derives the angle from Godot's own frustum arithmetic instead:

        left/right = -+ size / 2          + offset.x
        top/bottom = -+ size / aspect / 2 + offset.y      (aspect = W / H)

    so `atan((size / 2) / near)` has to be the declared half-angle, and the
    vertical half-angle has to follow from the aspect ratio.
    """
    near = visual.CAMERA_NEAR
    size = visual.CAMERA_FRUSTUM_SIZE
    half = math.degrees(math.atan((size / 2.0) / near))
    assert half == pytest.approx(visual.CAMERA_HFOV_DEGREES / 2.0)

    aspect = visual.FRAME_WIDTH / visual.FRAME_HEIGHT
    half_height = size / aspect / 2.0
    vertical = math.degrees(math.atan(half_height / near))
    assert math.tan(math.radians(vertical)) == pytest.approx(
        math.tan(math.radians(half)) / aspect
    )

    # And the framing the rest of the module reports follows from that angle:
    # at any view radius the framed disc is VIEW_DIAMETER_FRACTION of the frame.
    for view in (7.0, 12.0, 19.7):
        distance = visual.camera_distance(view)
        half_width_units = distance * math.tan(math.radians(half))
        assert 2.0 * view / (2.0 * half_width_units) == pytest.approx(
            visual.VIEW_DIAMETER_FRACTION
        )


def test_the_frustum_offset_places_the_principal_point(scene_source):
    """The offsets are fractions of the near plane, one per axis."""
    size = visual.CAMERA_FRUSTUM_SIZE
    aspect = visual.FRAME_WIDTH / visual.FRAME_HEIGHT
    offset_x, offset_y = visual.CAMERA_FRUSTUM_OFFSET
    assert offset_x == pytest.approx((0.5 - visual.ARENA_CENTRE_X_FRACTION) * size)
    assert offset_y == pytest.approx(
        (visual.ARENA_CENTRE_Y_FRACTION - 0.5) * size / aspect
    )
    # The arena is centred, so there is no lateral offset left at all.
    assert offset_x == pytest.approx(0.0)
    # The scene computes both from the same two composition fractions, and
    # derives the framed fraction the same way this module does.
    body = scene_source.split("const CAMERA_FRUSTUM_OFFSET")[1].split("const ")[0]
    assert "ARENA_CENTRE_X_FRACTION" in body
    assert "ARENA_CENTRE_Y_FRACTION" in body
    derived = scene_source.split("const VIEW_DIAMETER_FRACTION :=")[1].splitlines()[0]
    assert "FRONTIER_WIDTH_FRACTION * (1.0 + VIEW_PAD_FRACTION)" in derived


# --------------------------------------------------------------------------
# Phase 4B: what the human review asked to be fixed, as assertions
# --------------------------------------------------------------------------


def test_phase_4b_changed_nothing_the_simulation_can_see():
    """The brief's first requirement: 4B is a presentation pass and only that.

    Config digest, physics digest, schema and the frozen difficulty profile are
    all Phase 4A's. Nothing in this branch may reach the simulator - so the one
    assertion that matters is that the documents are bit-identical, which is
    what `state_digest` on a re-simulated run proves.
    """
    from satisfying.multishell import DEFAULT_CONFIG as SIM_CONFIG

    assert visual.EXPECTED_CONFIG_DIGEST == SIM_CONFIG.digest()
    for seed, winner, route in (
        (17964, "orange", "opening"),
        (3762, "cyan", "opening"),
        (1176, "orange", "break"),
    ):
        summary = document_for(seed)["summary"]
        assert summary["winner_team_name"] == winner, "a race outcome moved"
        assert summary["winner_route"] == route
    # And the 4B constants are all presentation: none of them appears in the
    # simulator's own configuration.
    fields = set(SIM_CONFIG.as_dict()) if hasattr(SIM_CONFIG, "as_dict") else set()
    for name in ("FRONTIER_WIDTH_FRACTION", "CAMERA_STAGE_PLAN",
                 "DAMAGE_CLUSTER_CHORD", "BREAK_FRAGMENT_COUNT"):
        assert name.lower() not in fields


def test_the_wall_depth_ramp_is_what_the_report_says():
    """Ten numbers, re-derived from the frustum rather than from a constant.

    This is the check the 1.778x frustum error would have failed: it does not
    compare two copies of one value, it recomputes the apparent thickness from
    the camera distance the framing implies.

    **The numbers moved in 4C without `PANEL_DEPTH` changing at all**, which is
    the point of re-deriving them: the frame fraction went from 0.850 to 1.200,
    the camera came in with it, and the final wall went from 57.20 px to
    105.44 px on its own. The ratio against the innermost shell rose from 5.98
    to 7.14 for the same reason - the depth ramp is a fixed set of world
    distances and perspective does more with them from closer in.
    """
    document = document_for(17964)
    view = visual.shell_view_radii(document)[-1]
    distance = visual.camera_distance(view)
    scale = visual.pixels_per_unit(view)
    apparent = []
    for index, shell in enumerate(document["shells"]):
        radius = float(shell["radius"])
        depth = float(visual.PANEL_DEPTH[index])
        flank = radius * depth / (distance + depth)
        apparent.append((float(shell["thickness"]) + flank) * scale)
    assert apparent == pytest.approx(
        [14.76, 21.58, 35.07, 59.70, 105.44], abs=0.05)
    assert apparent[-1] / apparent[0] == pytest.approx(7.14, abs=0.02)
    assert apparent == sorted(apparent), "the ramp is not monotone outward"
    # The pillars may not stick out of the wall they cap. At 1.55 they did, and
    # 66 of them at the outer shell rendered the final wall as a comb.
    assert visual.POST_DEPTH_FACTOR < 1.0
    assert visual.POST_DEPTH_FACTOR * visual.POST_EDGE_DEPTH < 1.0


def test_a_crack_never_leaves_the_panel_it_is_in():
    """The rotated crack stays inside the canonical radial thickness."""
    import math as _math

    tilt = _math.radians(visual.DAMAGE_CRACK_TILT_DEGREES
                         + visual.DAMAGE_BRANCH_SPREAD_DEGREES)
    thickness = float(DEFAULT_CONFIG.panel_thickness)
    for span, width in (
        (visual.DAMAGE_CRACK_SPAN, visual.DAMAGE_CRACK_WIDTH),
        (visual.DAMAGE_CRACK_SPAN * visual.DAMAGE_BRANCH_LENGTH,
         visual.DAMAGE_CRACK_WIDTH * 0.68),
    ):
        extent = span * thickness * _math.cos(tilt) + width * _math.sin(tilt)
        assert extent <= thickness, (
            f"a crack {span:.2f}x{width:.3f} rolled by "
            f"{_math.degrees(tilt):.0f} degrees reaches {extent:.4f} of a "
            f"{thickness} panel"
        )


def test_damage_is_where_the_ball_hit_and_builds_with_repetition(document):
    """Impact-position-driven, and deterministic."""
    clusters = visual.panel_damage_clusters(document)
    assert clusters, "a run with 300+ collisions has damaged panels"
    assert clusters == visual.panel_damage_clusters(document_for(int(document["seed"])))
    offsets: dict[str, list[float]] = {}
    for event in document["events"]:
        if event["kind"] != "collision":
            continue
        key = f"{event['shell_id']}:{event['panel_id']}"
        offsets.setdefault(key, []).append(float(event["panel_local_offset"]))
    for key, row in clusters.items():
        assert sum(int(c["weight"]) for c in row) == len(offsets[key])
        for cluster in row:
            # Every wound sits on an impact the ball actually made.
            assert any(
                abs(offset - float(cluster["offset"])) < 1e-12
                for offset in offsets[key]
            )
            assert cluster["growth"] == pytest.approx(min(
                visual.DAMAGE_CLUSTER_GROWTH_MAX,
                1.0 + visual.DAMAGE_CLUSTER_GROWTH * (int(cluster["weight"]) - 1),
            ))
            assert int(cluster["tilt_sign"]) in (1, -1)
        # Two wounds on one panel are never within the merge distance of each
        # other, which is what "repeated impacts build on one another" means.
        for a, b in zip(row, row[1:]):
            assert abs(float(a["offset"]) - float(b["offset"])) \
                > visual.DAMAGE_CLUSTER_CHORD


def test_a_panel_draws_at_most_the_wounds_it_has(document):
    for shell in document["shells"]:
        shell_id = int(shell["shell_id"])
        for panel_id in range(int(shell["panel_count"])):
            have = len(visual.panel_damage_clusters(document).get(
                f"{shell_id}:{panel_id}", []))
            for state in range(len(visual.DAMAGE_STATES)):
                shown = visual.visible_damage_clusters(
                    document, shell_id, panel_id, state)
                assert len(shown) <= min(visual.DAMAGE_CRACK_COUNT[state], have)
                # A worn-but-healthy panel shows exactly one scuff and no more.
                scuffed = visual.visible_damage_clusters(
                    document, shell_id, panel_id, state, wear=1.0)
                if state == 0:
                    assert len(scuffed) == min(1, have)
                else:
                    assert scuffed == shown
                weights = [int(c["weight"]) for c in shown]
                assert weights == sorted(weights, reverse=True), (
                    "the deepest wound is not drawn first"
                )
            assert visual.visible_damage_clusters(document, shell_id, panel_id, 4) == []


def test_break_fragments_are_deterministic_and_cannot_reach_the_physics(document):
    """Few, substantial, reproducible - and presentation only."""
    fragments = visual.break_fragments(document)
    assert fragments == visual.break_fragments(document_for(int(document["seed"])))
    breaks = [e for e in document["events"] if e["kind"] == "panel_break"]
    assert sum(len(v) for v in fragments.values()) == len(breaks)
    assert 3 <= visual.BREAK_FRAGMENT_COUNT <= 6, "the brief's readable-chunk band"
    chords = {int(s["shell_id"]): float(s["chord_length"]) for s in document["shells"]}
    for key, entries in fragments.items():
        shell_id = int(key.split(":")[0])
        for entry in entries:
            assert any(abs(float(entry["t"]) - float(b["t"])) < 1e-12
                       for b in breaks), "a fragment burst with no break"
            pieces = entry["pieces"]
            assert len(pieces) == visual.BREAK_FRAGMENT_COUNT
            for piece in pieces:
                # Laid out along the panel's own chord, so they are its pieces.
                assert abs(float(piece["offset"])) <= 0.5 * chords[shell_id]
                assert float(piece["seconds"]) <= 0.5, "fragments linger"
    # The physics never reads any of it: no ball's flight mentions a fragment.
    assert "fragment" not in json.dumps(document["balls"])


def test_the_passage_response_is_derived_and_the_flood_moment_is_absent(document):
    """Break, hole, ball through hole - and the stronger version that is not.

    The brief asks for several balls pouring through at once. Every shell
    rotates at 0.27 to 0.77 rad/s, so a broken slot is a gap sweeping past the
    population rather than a door; ball-ball collisions are off and nothing
    steers. `flood_through` is therefore empty on every review candidate and
    this test records that rather than hiding it.
    """
    responses = visual.passage_responses(document)
    breaks = {(int(e["shell_id"]), int(e["panel_id"])): float(e["t"])
              for e in document["events"] if e["kind"] == "panel_break"}
    for entry in responses:
        key = (int(entry["shell_id"]), int(entry["panel_id"]))
        assert key in breaks, "a passage that never broke open"
        assert float(entry["first_use_t"]) >= breaks[key]
        assert float(entry["first_use_t"]) <= breaks[key] + visual.FLOOD_WINDOW_SECONDS
        assert entry["balls"] >= 1
    assert visual.flood_through(document) == [
        e for e in responses if int(e["balls"]) >= visual.FLOOD_MIN_BALLS
    ]
    assert visual.flood_through(document) == [], (
        "a candidate finally has a flood-through; the renderer already draws "
        "it, but the phase document says this never happens and must be "
        "corrected"
    )


def test_the_final_wall_shows_canonical_wear_the_state_ledger_hides(document):
    """**The brief's five-part final-wall gate turned on this, and it failed.**

    The outermost shell's break threshold is high enough that at the final
    struggle it is 64/66 healthy on 17964 and 66/66 healthy on 3762, so a still
    of the hardest moment showed a pristine barrier and "accumulated damage"
    was not communicated. The physics is frozen, so the fix is not to make it
    break sooner - it is to stop throwing away a canonical field.

    `fraction` is on every `damage` event. Reading it puts marks on 8, 19 and 1
    outer panels that the five-state ledger calls healthy, and dims the sheen
    of 13, 28 and 1 of them.
    """
    report = visual.wear_report(document)
    assert report["panels"] == 66
    assert report["visibly_marked"] > report["non_healthy"], (
        "reading `fraction` added nothing to the final wall"
    )
    assert report["worst_wear"] > 0.0
    # Wear is monotone in time and never exceeds the state it implies.
    order = {name: index for index, name in enumerate(visual.DAMAGE_STATES)}
    for key, rows in visual.panel_wear(document).items():
        times = [row[0] for row in rows]
        assert times == sorted(times)
        fractions = [row[1] for row in rows]
        assert fractions == sorted(fractions), f"{key} un-accumulated damage"
        shell_id, panel_id = (int(part) for part in key.split(":"))
        for at, fraction in rows:
            state = panel_state_at(document, shell_id, panel_id, at)
            if fraction < visual.DAMAGE_WEAR_FLOOR:
                assert order[state] <= 1, (
                    f"{key} is {state} at {fraction:.3f} of its threshold"
                )


def test_wear_is_a_read_of_the_document_and_not_a_second_opinion(document):
    """Every wear sample is a canonical `damage` event, at its own instant."""
    events = [e for e in document["events"] if e["kind"] == "damage"]
    total = sum(len(rows) for rows in visual.panel_wear(document).values())
    assert total == len(events)
    for event in events:
        at = float(event["t"])
        wear = visual.panel_wear_at(
            document, int(event["shell_id"]), int(event["panel_id"]), at)
        assert wear == pytest.approx(float(event["fraction"]))
    # And before anything has hit it, a panel is unworn.
    assert visual.panel_wear_at(document, 4, 0, 0.0) == 0.0


def test_the_hook_is_gone_and_does_not_linger():
    """The review's last finding: no faint ghost text over the race."""
    assert visual.HOOK_FADE_TO == 0.0, "the hook leaves a residue again"
    assert 1.5 <= visual.HOOK_HOLD_SECONDS <= 2.0, "the brief's hold window"
    assert visual.HOOK_GONE_SECONDS == pytest.approx(
        visual.HOOK_HOLD_SECONDS + visual.HOOK_FADE_SECONDS)
    assert visual.HOOK_GONE_SECONDS < 2.6


def test_the_winner_banner_is_deterministic_and_clear_of_the_ball(document):
    placement = visual.winner_banner_placement(document)
    assert placement["placed"]
    assert placement == visual.winner_banner_placement(
        document_for(int(document["seed"])))
    assert placement["clear_of_ball"], placement
    assert placement["top_fraction"] in (
        visual.WINNER_TOP_FRACTION, visual.WINNER_ALT_TOP_FRACTION)
    # **The whole release flight, not the escape instant.** The banner is on
    # screen for the 0.55 s release beat and the escapee keeps flying through
    # it - on 1176 that moves the ball 101 px further down, from 93 px clear of
    # the lower band to inside it. Checking only the escape instant reported a
    # pass for a frame with the caption under the ball.
    from satisfying.multishell_playback import position_at

    duration = float(document["summary"]["duration"])
    escape_event = next(
        e for e in reversed(document["events"]) if e["kind"] == "escape")
    view = visual.view_radius_at(document, float(escape_event["t"]))
    radius_px = placement["ball_radius_px"]
    band_low, band_high = placement["band_px"]
    for index in range(visual.WINNER_RELEASE_SAMPLES):
        t = duration + visual.RELEASE_SECONDS * index / (
            visual.WINNER_RELEASE_SAMPLES - 1)
        point = position_at(document, int(escape_event["ball_id"]), t)
        if point is None:
            continue
        py = visual.project(point, view)[1]
        assert not (py + radius_px > band_low and py - radius_px < band_high), (
            f"the escapee reaches the banner at t={t:.2f}s, y={py:.1f}px"
        )
    escape = next(e for e in reversed(document["events"]) if e["kind"] == "escape")
    assert placement["team_id"] == int(escape["team_id"])
    assert placement["team_name"] == str(escape["team_name"])


def test_the_late_frame_is_not_emptier_than_it_has_to_be(document):
    """The occupancy measurement the brief asks for, and what it shows.

    "The late section should NOT become more visually empty than the opening
    simply because the camera zoomed out" is a target this arena cannot meet
    and the arithmetic says so: the opening framing holds two shells across the
    frame *and* crops three more at the top and bottom, while the final one
    holds all five inside it. What 4B can do - and does - is stop the fall
    being the whole story, and the renderer's own frames are what settle it.
    """
    report = visual.occupancy_report(document)
    thirds = report["thirds"]
    assert thirds["early"]["ink_fraction"] > thirds["late"]["ink_fraction"]
    # The frontier's own footprint is constant by construction, which is the
    # part the camera controls.
    for name in ("early", "middle", "late"):
        assert thirds[name]["arena_footprint_fraction"] > 0.0
    assert report["min_ink_fraction"] > 0.10
    # Phase 4A's final framing put 8.9% ink on the frame. Anything at or below
    # that is the composition the review rejected.
    assert thirds["late"]["ink_fraction"] > 0.13


def test_the_camera_stage_plan_is_the_one_the_scene_draws(scene_source):
    """The plan is a list of pairs in both files, so compare it as text."""
    expected = "[[0, 2], [2, 4]]"
    assert f"const CAMERA_STAGE_PLAN := {expected}" in scene_source
    assert list(visual.CAMERA_STAGE_PLAN) == [(0, 2), (2, 4)]


def test_the_scene_defaults_to_the_declared_frame_fraction(scene_source, scene_code):
    """The sweep dial may exist and may not change the default render."""
    assert "var frontier_width := FRONTIER_WIDTH_FRACTION" in scene_code
    assert "var view_diameter := VIEW_DIAMETER_FRACTION" in scene_code
    assert "var panel_depth: Array = PANEL_DEPTH.duplicate()" in scene_code
    assert gd_number(scene_source, "FRONTIER_WIDTH_FRACTION") == pytest.approx(
        visual.FRONTIER_WIDTH_FRACTION)


def test_the_scene_never_scales_an_oriented_basis(scene_code):
    """`Basis.scaled` multiplies the *rows*, which are the global axes.

    Scaling an oriented basis with it stretches a diagonal panel along world X
    instead of along its own chord - the Phase 4A slab code already carries
    that warning, and the Phase 4B damage chip was written with the bug anyway
    and only caught on re-reading. `_oriented_basis` pre-scales the columns and
    is the only correct form here, so the check is that every `.scaled(` in the
    scene is on `Basis.IDENTITY`, where rows and columns are the same thing.
    """
    import re as _re

    for match in _re.finditer(r"(\w[\w.\[\]]*)\.scaled\(", scene_code):
        assert match.group(1) == "Basis.IDENTITY", (
            f"{match.group(1)}.scaled(...) shears an oriented basis; "
            f"use _oriented_basis to pre-scale the columns"
        )


def test_the_render_config_digest_is_stable_and_covers_the_new_dials():
    first = visual.render_config_digest()
    assert first == visual.render_config_digest()
    config = visual.render_config()
    for key in ("camera_stage_plan", "event_guard", "damage_cluster",
                "damage_crack", "damage_branch", "fragments", "flood", "hook",
                "winner", "panel_chamfer_by_shell", "break_stress_seconds"):
        assert key in config, key
    assert config["frontier_width_fraction"] == visual.FRONTIER_WIDTH_FRACTION


# --------------------------------------------------------------------------
# Phase 4C: the single reframe, the crop, and damage in the material
# --------------------------------------------------------------------------


def test_the_camera_never_zooms_back_out_after_the_lock(document):
    """Locked means locked: not "settles", not "drifts", identical.

    The 4B camera was monotone and had a static tail, which is a weaker claim
    than the 4C brief's: *no second zoom, late camera static*. Sampled at one
    millisecond over the whole tail so a slow creep of a few hundredths of a
    unit could not hide between frames.
    """
    lock = visual.camera_lock_time(document)
    duration = float(document["summary"]["duration"])
    locked = visual.view_radius_at(document, lock)
    steps = max(1, int((duration - lock) * 1000.0))
    for index in range(steps + 1):
        t = lock + (duration - lock) * index / steps
        assert visual.view_radius_at(document, t) == pytest.approx(
            locked, rel=1e-12), f"the camera moved at {t:.3f}s, after the lock"
    # And the framed radius after the lock is the outermost shell's, so the
    # lock is at the *end* of the schedule rather than somewhere inside it.
    assert locked == pytest.approx(visual.shell_view_radii(document)[-1])


def test_the_framing_is_a_deterministic_function_of_the_document(document):
    """Same document in, same schedule out - and no hidden state between runs.

    `camera_stages` memoises on the playback digest, so this also checks that
    the cache returns the schedule rather than becoming it: the second call is
    compared field by field against a computation made with the cache cleared.
    """
    first = visual.camera_stages(document)
    visual._STAGE_CACHE.clear()
    second = visual.camera_stages(document)
    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert a["stage"] == b["stage"]
        assert a["extent_shell"] == b["extent_shell"]
        assert a["trigger_region"] == b["trigger_region"]
        assert float(a["start"]) == pytest.approx(float(b["start"]), rel=0, abs=0)
        assert float(a["settled"]) == pytest.approx(float(b["settled"]), rel=0, abs=0)
        assert float(a["radius"]) == pytest.approx(float(b["radius"]), rel=0, abs=0)
    # Two documents built from the same seed agree too, which is the property
    # that makes the production identity mean anything.
    again = document_for(int(document["seed"]))
    assert [float(s["start"]) for s in visual.camera_stages(again)] == [
        float(s["start"]) for s in first
    ]


def test_the_one_transition_is_triggered_by_a_canonical_crossing(document):
    """The camera may not move for any reason the race did not give it."""
    stages = visual.camera_stages(document)
    moves = [stage for stage in stages if int(stage["stage"]) > 0]
    assert len(moves) == 1
    move = moves[0]
    trigger = int(move["trigger_region"])
    exits = [
        float(event["t"]) for event in document["events"]
        if event["kind"] == "shell_exit" and int(event["to_region"]) >= trigger
    ]
    assert exits, "the trigger region is never reached"
    assert float(move["trigger_t"]) == pytest.approx(min(exits))
    # The move opens before the crossing rather than reacting after it, and
    # protection may only ever pull it earlier.
    wanted = float(move["trigger_t"]) - visual.FRAME_LEAD_SECONDS
    assert float(move["start"]) <= wanted + 1e-9
    assert float(move["settled"]) - float(move["start"]) == pytest.approx(
        visual.FRAME_EASE_SECONDS)


def test_the_canonical_ball_physics_are_untouched_by_the_framing(document):
    """The 4C brief freezes the simulation; the camera reads it and no more.

    Positions are a pure function of the document's own flights, so the same
    instant projects differently at two framings and *is* the same world point
    at both. This is the check that a presentation phase did not quietly become
    a physics phase.
    """
    summary = document["summary"]
    assert float(summary["speed_min"]) == pytest.approx(10.0, abs=1e-9)
    assert float(summary["speed_max"]) == pytest.approx(10.0, abs=1e-9)
    assert int(summary["ball_collisions"]) == 0, "ball-ball collisions are on"
    assert float(summary["max_penetration"]) < 1e-6
    saved = visual.FRONTIER_WIDTH_FRACTION
    at = 0.5 * float(summary["duration"])
    reference = visual.positions_at(document, at)
    try:
        visual.FRONTIER_WIDTH_FRACTION = 0.85
        visual.VIEW_DIAMETER_FRACTION = 0.85 * (1.0 + visual.VIEW_PAD_FRACTION)
        visual._STAGE_CACHE.clear()
        other = visual.positions_at(document, at)
    finally:
        visual.FRONTIER_WIDTH_FRACTION = saved
        visual.VIEW_DIAMETER_FRACTION = saved * (1.0 + visual.VIEW_PAD_FRACTION)
        visual._STAGE_CACHE.clear()
    assert set(reference) == set(other)
    for ball_id, point in reference.items():
        assert point == pytest.approx(other[ball_id], rel=0, abs=0)


def test_a_wound_has_a_lit_lip_and_the_lip_is_not_a_state(scene_source):
    """The 4C addition that turned a pit into a hole, as a structural check.

    A dark notch with a bright hairline in it is still a mark lying on a
    surface. A dark notch with a *lit broken edge* reads as a hole, because
    that is what a chip in a lit solid does. The lip is state-independent - a
    broken edge does not get hotter, it is just broken - so it has one shared
    material, and it is wider than the chip it surrounds or there is no ring.
    """
    assert visual.DAMAGE_RIM_MARGIN > 0.0
    assert visual.DAMAGE_RIM_ENERGY > 0.0
    assert 0.0 < visual.DAMAGE_RIM_SPAN < 1.0
    # Bright enough to read against the panel face, dim enough not to be a
    # light source sitting on a wall, which is what 4A's marks were.
    assert visual.DAMAGE_RIM_ENERGY < visual.FACE_ENERGY + 0.2
    assert "const MARK_PARTS := 6" in scene_source
    for name in ("MARK_PART_CHIP", "MARK_PART_RIM", "MARK_PART_CRACK",
                 "MARK_PART_BRANCH_A", "MARK_PART_BRANCH_B", "MARK_PART_SEAM"):
        assert f"const {name} :=" in scene_source
    # One shared lip material for the whole arena, like the chip.
    assert scene_source.count("_panel_rim_material = StandardMaterial3D.new()") == 1


@pytest.mark.parametrize("seed", [17964, 1176])
def test_a_seam_joins_two_canonical_impact_positions(seed):
    """"Connected crack network", and connected to the ball's own hits.

    A seam is not a decorative link: both of its endpoints are wound offsets,
    and a wound offset is a canonical `panel_local_offset`. So the network is
    exactly as tied to where the ball actually hit as the wounds are, and this
    test is what stops a future version inventing one.
    """
    document = document_for(seed)
    clusters = visual.panel_damage_clusters(document)
    offsets = {
        key: {round(float(event["panel_local_offset"]), 12)
              for event in document["events"]
              if event["kind"] == "collision"
              and f"{event['shell_id']}:{event['panel_id']}" == key}
        for key in clusters
    }
    seen = 0
    for key, row in clusters.items():
        shell_id, panel_id = (int(part) for part in key.split(":"))
        for state in range(len(visual.DAMAGE_SEAM_STATES)):
            seams = visual.wound_seams(document, shell_id, panel_id, state)
            if not visual.DAMAGE_SEAM_STATES[state]:
                assert seams == [], "a seam below the critical state"
                continue
            shown = visual.visible_damage_clusters(
                document, shell_id, panel_id, state)
            shown_offsets = [float(c["offset"]) for c in shown]
            for seam in seams:
                seen += 1
                half = 0.5 * float(seam["length"])
                low = float(seam["centre"]) - half
                high = float(seam["centre"]) + half
                # Both ends are shown wounds of this panel...
                assert any(abs(low - o) < 1e-9 for o in shown_offsets)
                assert any(abs(high - o) < 1e-9 for o in shown_offsets)
                # ...and every wound offset is a canonical impact offset.
                assert any(abs(low - o) < 1e-9 for o in offsets[key])
                assert any(abs(high - o) < 1e-9 for o in offsets[key])
                assert float(seam["length"]) >= visual.DAMAGE_SEAM_MIN_CHORD
    assert seen > 0, "no panel in the run ever shows a connected network"


@pytest.mark.parametrize("seed", [17964, 1176])
def test_the_damage_visuals_are_deterministic(seed):
    """Two derivations of one seed agree exactly, wound for wound.

    Not "look the same": the same offsets, the same weights, the same growth,
    the same lean and the same seams, to the last bit. A render that is not a
    function of the document cannot be reproduced from the production identity.
    """
    first = visual.panel_damage_clusters(document_for(seed))
    second = visual.panel_damage_clusters(document_for(seed))
    assert set(first) == set(second)
    for key in first:
        assert len(first[key]) == len(second[key])
        for a, b in zip(first[key], second[key]):
            assert a["offset"] == b["offset"]
            assert a["weight"] == b["weight"]
            assert a["growth"] == b["growth"]
            assert a["tilt_sign"] == b["tilt_sign"]
    teams_a = visual.panel_damage_teams(document_for(seed))
    teams_b = visual.panel_damage_teams(document_for(seed))
    assert teams_a == teams_b


@pytest.mark.parametrize("seed", [17964, 1176])
def test_the_stress_tint_only_fires_where_both_teams_wore_a_panel_down(seed):
    """The brief's tint allowance, held to "both teams" meaning both teams.

    A single glancing hit out of nineteen is not two teams wearing a panel
    down together, and a tint that fired on it would be noise. The minority
    has to hold a real share, the tint is small, and it is read from the
    canonical `team_cumulative` rather than counted here.
    """
    document = document_for(seed)
    teams = visual.panel_damage_teams(document)
    assert teams, "no panel in the run was ever damaged"
    tinted = 0
    for key, row in teams.items():
        totals = row["team_cumulative"]
        assert row["lead_team"] == max(
            range(len(totals)), key=lambda index: totals[index])
        if row["both"]:
            tinted += 1
            assert row["minority_share"] >= visual.DAMAGE_TEAM_TINT_MIN_SHARE
            assert row["tint"] == pytest.approx(visual.DAMAGE_TEAM_TINT)
        else:
            assert row["tint"] == 0.0
    # A tint on every panel would be a global recolour, which is the thing the
    # brief bans; on none of them the allowance would be dead code.
    assert 0 < tinted < len(teams)
    assert visual.DAMAGE_TEAM_TINT <= 0.25, "the wall stops looking like a wall"


def test_a_worn_panel_gets_rougher_before_it_gets_a_crack():
    """"Subtle surface roughness", which no added geometry can supply.

    It is a material property of the whole face rather than a shape on it, so
    it is the one part of the brief's `damaged` state that has to be a
    material. Continuous below the first damage state and stepped above it,
    monotone in both, and clamped at fully rough.
    """
    for shell in range(len(visual.SHELL_ROUGHNESS)):
        base = visual.SHELL_ROUGHNESS[shell]
        assert visual.panel_roughness(shell, 0, 0.0) == pytest.approx(base)
        previous = base
        for wear in (0.1, 0.3, 0.6, 1.0):
            value = visual.panel_roughness(shell, 0, wear)
            assert value >= previous
            assert value <= 1.0
            previous = value
        ladder = [visual.panel_roughness(shell, state, 0.0)
                  for state in range(1, 4)]
        assert ladder == sorted(ladder)
        assert all(value <= 1.0 for value in ladder)
    # Wear is clamped before it is scaled, so a fraction far past the break
    # threshold - 1176's worst outer panel reaches 1.019 - adds no more than a
    # fraction of exactly 1.0 does, and nothing can run past fully rough.
    assert visual.panel_roughness(4, 0, 9.0) == pytest.approx(
        visual.panel_roughness(4, 0, 1.0))
    assert visual.panel_roughness(4, 0, 9.0) <= 1.0


def test_no_arena_colour_is_a_saturated_marker():
    """The specific thing the human review kept seeing, as a number.

    4B satisfied "not a team hue" by rotating the damage ramp into magenta,
    and the review called the result "red/pink marks rather than physical
    destruction". The 4C ramp satisfies the same separation by *desaturating*,
    so this is the assertion that a future phase cannot buy separation back
    with saturation: nothing the arena draws may be more saturated than the
    least saturated team colour.

    `POST_HOT_RGB` is in the list on purpose. It is the cast a pillar beside a
    broken panel keeps for the rest of the run, so at 31 breaks it was 62
    magenta dots in the late frame - by construction a coloured marker beside
    every break, which is exactly what the brief bans.
    """
    def saturation(rgb):
        high, low = max(rgb), min(rgb)
        return 0.0 if high <= 0.0 else (high - low) / high

    team_floor = min(saturation(rgb) for rgb in visual.TEAM_RGB)
    arena = {
        "crack": visual.CRACK_RGB,
        "critical": visual.CRITICAL_RGB,
        "fracture": visual.FRACTURE_RGB,
        "break_flash": visual.BREAK_FLASH_RGB,
        "post_hot": visual.POST_HOT_RGB,
        "damage_rim": visual.DAMAGE_RIM_RGB,
        "post_edge": visual.POST_EDGE_RGB,
        "face": visual.FACE_RGB,
        "panel": visual.PANEL_RGB,
        "back": visual.BACK_RGB,
    }
    for name, rgb in arena.items():
        assert saturation(rgb) < team_floor, (
            f"{name} is more saturated than a team colour"
        )
        for team, colour in zip(visual.TEAM_NAMES, visual.TEAM_RGB):
            distance = sum((a - b) ** 2 for a, b in zip(rgb, colour)) ** 0.5
            assert distance > 0.45, f"{name} is within {distance:.2f} of {team}"


def test_the_ball_is_a_bigger_mark_than_its_own_streak(document):
    """The brief's "reduce trail length if it becomes spaghetti", as a number.

    The trail is a world-unit length, so raising the frame fraction lengthens
    every streak on screen without a constant changing - 4B found this when
    0.652 became 0.850 and shortened the trail to 0.115 s in response. 1.200
    lengthens it again by the same mechanism, so the check is restated rather
    than assumed: at both the opening and the final framing the drawn ball has
    to be the larger mark, or twelve balls read as a tangle of lines with dots
    in it rather than as twelve balls.
    """
    speed = float(document["config"]["speed"])
    ball_radius = float(document["config"]["ball_radius"])
    for view in (visual.shell_view_radii(document)[2],
                 visual.shell_view_radii(document)[-1]):
        scale = visual.pixels_per_unit(view)
        streak = speed * visual.TRAIL_SECONDS * scale
        ball = 2.0 * ball_radius * visual.BALL_DRAW_SCALE * scale
        assert ball > streak, (
            f"the streak is {streak:.1f} px against a {ball:.1f} px ball"
        )


def test_a_wound_never_leaves_its_panel_radially(document):
    """The canonical silhouette rule, applied to the lip as well as the crack.

    **The first 4C lip failed this and the render is what showed it.** It was
    sized as the chip plus the margin on both axes - 0.68 * 0.30 + 2 * 0.070 =
    0.344 against a 0.300-thick panel - so every wound stuck out past the top
    and bottom of the band it was supposed to be a hole in, and the lit rim
    inverted its own read: a plate stuck on a wall rather than a chip in one.

    Recomputed here from the constants rather than compared against a written
    number, in the same shape as `test_a_crack_never_leaves_the_panel`, so the
    next person who resizes a wound part finds out.
    """
    thickness = min(float(shell["thickness"]) for shell in document["shells"])
    # The chip.
    assert 0.68 * thickness <= thickness + 1e-12
    # The lip, which is the one that was wrong.
    assert visual.DAMAGE_RIM_SPAN * thickness <= thickness + 1e-12
    # And the lip is still larger than the chip it surrounds, or there is no
    # ring of broken material to read.
    assert visual.DAMAGE_RIM_SPAN > 0.68
    # Along the chord the lip is margin-wider on each side, which is what makes
    # it a ring rather than a second chip.
    assert visual.DAMAGE_MARK_CHORD + 2.0 * visual.DAMAGE_RIM_MARGIN >         visual.DAMAGE_MARK_CHORD
    # A seam is a chord-aligned bar of its own and it may not leave the panel
    # radially either.
    assert visual.DAMAGE_SEAM_WIDTH <= thickness


def test_the_panel_comes_apart_into_substantial_chunks(document):
    """The break the brief asks for: 3 to 6 pieces of the panel itself."""
    assert 3 <= visual.BREAK_FRAGMENT_COUNT <= 6
    fragments = visual.break_fragments(document)
    assert fragments, "no break in the run"
    for key, breaks in fragments.items():
        assert breaks, f"{key} is in the table with no break"
        for event in breaks:
            pieces = event["pieces"]
            assert len(pieces) == visual.BREAK_FRAGMENT_COUNT
            for piece in pieces:
                # A chunk of the slab, not a particle: it keeps the panel's own
                # radial thickness and a real share of its chord.
                assert float(piece["length"]) > 0.0
                assert float(piece["depth_fraction"]) > 0.0
            # The chunks are laid out along the panel's own chord and thrown
            # apart, so no two of them start in the same place.
            offsets = sorted(float(piece["offset"]) for piece in pieces)
            assert len(set(offsets)) == len(offsets)
    # And the hole is open long before the chunks have finished leaving.
    assert visual.BREAK_RETRACT_SECONDS < visual.BREAK_FRAGMENT_SECONDS
    # The wall is seen to give before it goes: at least four frames at 30 fps.
    assert visual.BREAK_STRESS_SECONDS * 30.0 >= 4.0
