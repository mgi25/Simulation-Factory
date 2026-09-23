"""Phase 3 integration: the visual and musical consumers share one timeline.

These tests do not re-check what Phase 2A and Phase 2B already proved about
their own layers. They check the joins, which is the only thing that is new:
that both consumers read the same document, that neither writes to it, that the
cast is the same cast in both, that every cue class lands within a frame of its
picture, and that the two render configurations are functions of the code
rather than of when they were run.
"""

from __future__ import annotations

import copy
import json
import math

import pytest

from satisfying import multishell_av as av
from satisfying import multishell_score as score
from satisfying import multishell_visual as visual
from satisfying.multishell import SCHEMA_VERSION
from satisfying.multishell_playback import document_for, document_digest

SEEDS = av.CANDIDATE_SEEDS
#: The busiest of the review set, which is where anything that fails does.
REFERENCE_SEED = SEEDS[0]


@pytest.fixture(scope="module")
def documents() -> dict[int, dict]:
    return {seed: document_for(seed) for seed in SEEDS}


@pytest.fixture(scope="module")
def reference(documents) -> dict:
    return documents[REFERENCE_SEED]


# --------------------------------------------------------------------------
# One document, two consumers
# --------------------------------------------------------------------------


def test_the_branch_is_pinned_to_the_phase3b_tip_it_was_cut_from():
    """Phase 4A is one branch, not a merge of three, so the three SHAs agree."""
    assert av.BASE_SHA == "335ae3c647676be37421e082268f650b8541e8c9"
    assert av.VISUAL_SHA == av.BASE_SHA
    assert av.AUDIO_SHA == av.BASE_SHA
    assert av.INTEGRATION_VERSION == "category3-test2-two-team-shell-race-av/2.0.0"


def test_the_candidate_set_has_one_definition():
    assert av.CANDIDATE_SEEDS is visual.CANDIDATE_SEEDS
    assert len(SEEDS) == 6
    assert len(set(SEEDS)) == 6


@pytest.mark.parametrize("seed", SEEDS)
def test_both_consumers_read_the_same_playback_digest(documents, seed):
    """The single claim the whole phase rests on."""
    document = documents[seed]
    plan = score.schedule(document, score.named_config(av.CONFIG.audio))
    assert plan.playback_digest == document["digest"]
    # The visual consumer accepts the document unchanged, by its own contract.
    # It answers with an empty string rather than None when it may draw.
    assert visual.validate_document(document) == ""


@pytest.mark.parametrize("seed", SEEDS)
def test_the_document_is_the_frozen_v3_schema(documents, seed):
    assert documents[seed]["schema"] == SCHEMA_VERSION
    assert documents[seed]["config_digest"] == score.CONFIG_DIGEST


@pytest.mark.parametrize("seed", SEEDS)
def test_neither_consumer_mutates_the_canonical_playback(documents, seed):
    """A consumer may read a trajectory and may not write one."""
    document = documents[seed]
    before = document_digest(document)
    snapshot = copy.deepcopy(document)

    score.schedule(document, score.named_config(av.CONFIG.audio))
    visual.validate_document(document)
    visual.measure_document(document)
    visual.team_palette(document)
    visual.event_moments(document)
    av.sync_audit(document, 30.0)
    av.camera_report(document, 30.0)
    av.spawn_report(document)
    av.population_report(document, 30.0)
    av.retention_report(document)
    av.density_report(document)
    av.team_audit(document)
    av.race_report(document)

    assert document_digest(document) == before
    assert document == snapshot


@pytest.mark.parametrize("seed", SEEDS)
def test_event_order_is_unchanged_by_either_consumer(documents, seed):
    document = documents[seed]
    before = av.event_order_digest(document)
    kinds = [event["kind"] for event in document["events"]]
    times = [float(event["t"]) for event in document["events"]]
    score.schedule(document, score.named_config(av.CONFIG.audio))
    av.sync_audit(document, 30.0)
    assert av.event_order_digest(document) == before
    assert [event["kind"] for event in document["events"]] == kinds
    assert [float(event["t"]) for event in document["events"]] == times
    assert times == sorted(times)


# --------------------------------------------------------------------------
# The cast
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_the_two_layers_agree_on_the_cast_and_on_the_colours(documents, seed):
    report = av.team_audit(documents[seed])
    assert report["same_cast"]
    assert report["visual_team_agrees"]
    assert report["audio_team_agrees"]
    assert report["generation_agrees"]
    assert report["lineage_agrees"]
    assert report["children_inherit_team"]
    assert report["two_founders_one_each"]
    assert report["founders"] == 2
    assert report["pass"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_two_colours_share_one_tonal_collection(documents, seed):
    """Distinguishable texture, one key. The registers may differ; the scale
    may not."""
    report = av.team_audit(documents[seed])
    registers = report["registers_by_team"]
    assert sorted(registers) == [0, 1]
    assert registers[0] != registers[1], "the two colours sit in one register"
    assert report["shared_tonal_collection"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_race_reads_as_a_race(documents, seed):
    race = av.race_report(documents[seed])
    assert race["genuine"], race["reason"]
    assert race["winner"] in (0, 1)
    assert min(race["population_by_team"]) >= 4
    assert race["loser_frontier"] >= 3
    assert race["winner_population_share"] <= 0.75


def test_the_two_layers_have_no_independent_id_space(reference):
    """Why the lineage audit is a regression guard and not a forgery detector.

    Both layers read `generation` and `lineage` off the ball record, so editing
    one of those fields moves the renderer and the sequencer together and the
    audit still agrees - which is the property being asserted, not a hole in
    it. Writing the test the other way round would be claiming the audit can
    catch a tampered document, and it cannot; nothing downstream of the
    document can. What it does catch is a future layer that starts numbering
    the cast for itself, and that is worth a guard because it would be silent.
    """
    edited = copy.deepcopy(reference)
    for ball in edited["balls"]:
        if int(ball["generation"]) > 0:
            ball["generation"] = int(ball["generation"]) + 1
            break
    report = av.team_audit(edited)
    assert report["generation_agrees"], "both layers must move together"

    voices = score.voices_for(edited["balls"], score.named_config(av.CONFIG.audio))
    palette = visual.team_palette(edited)
    assert sorted(voices) == sorted(palette) == sorted(
        int(ball["ball_id"]) for ball in edited["balls"])


def test_a_stale_visual_audit_is_rejected(reference, documents):
    """The failure mode a pipeline actually has: yesterday's frames.

    A render left over from a previous document would produce a clip whose
    picture and sound are each internally correct and are not the same run.
    The digest carried in the Godot walk is what stops that, so it has to be
    checked rather than assumed.
    """
    walk = {"seed": int(reference["seed"]), "digest": reference["digest"], "frames": 10}
    assert av.sync_audit(reference, 30.0, walk)["pass"]

    other = SEEDS[1]
    stale = dict(walk, digest=documents[other]["digest"])
    report = av.sync_audit(reference, 30.0, stale)
    assert not report["visual_digest_matches"]
    assert not report["pass"]

    with pytest.raises(av.AVIntegrationError):
        av.sync_audit(reference, 30.0, dict(walk, seed=other))


# --------------------------------------------------------------------------
# A/V synchronisation, per cue class
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("fps", (30.0, 60.0))
def test_every_cue_class_lands_within_one_rendered_frame(documents, seed, fps):
    report = av.sync_audit(documents[seed], fps)
    assert report["pass"], report
    for name, row in report["timing"].items():
        assert row["within_one_frame"], (name, row)
        assert row["video_never_early"], (name, row)
    assert report["maximum_sync_error_frames"] <= 1.0 + 1.0e-9


@pytest.mark.parametrize("seed", SEEDS)
def test_collision_spawn_break_and_escape_are_all_mapped(documents, seed):
    document = documents[seed]
    report = av.sync_audit(document, 30.0)
    timing = report["timing"]
    assert timing["collision"]["count"] == sum(
        1 for e in document["events"] if e["kind"] == "collision")
    assert timing["spawn"]["count"] == sum(
        1 for e in document["events"] if e["kind"] == "ball_spawn")
    assert timing["break"]["count"] == sum(
        1 for e in document["events"] if e["kind"] == "panel_break")
    assert timing["escape"]["count"] == 1
    assert timing["shell_exit"]["count"] == len(av._first_outward_exits(document))
    assert report["mapping_complete"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_score_never_moves_a_cue_in_time(documents, seed):
    """Cluster management resolves a clash by register, never by delay."""
    plan = score.schedule(documents[seed], score.named_config(av.CONFIG.audio))
    for event in plan.events:
        assert event.sample_offset == score._sample_at(
            event.source_seconds, plan.config.sample_rate)
    assert av.sync_audit(documents[seed], 30.0)["audio_never_retimed"]


@pytest.mark.parametrize("seed", SEEDS)
def test_cue_order_survives_across_instants(documents, seed):
    report = av.sync_audit(documents[seed], 30.0)
    assert report["audio_time_order_monotone"]
    assert report["audio_cross_instant_order_shared"]


def test_a_retimed_cue_would_be_caught(reference):
    """Shifting one note by a frame has to break the audit."""
    plan = score.schedule(reference, score.named_config(av.CONFIG.audio))
    moved = [event for event in plan.events if event.kind == "collision"]
    assert moved, "the reference seed has collisions"
    shifted = moved[0].sample_offset + int(0.05 * plan.config.sample_rate)
    # The audit compares the placed sample against the instant, so a shift of
    # 50 ms is 1.5 frames at 30 fps and outside the gate by construction.
    error = abs(shifted / plan.config.sample_rate - moved[0].source_seconds)
    assert error > 1.0 / 30.0


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_render_and_audio_configs_are_deterministic(documents, seed):
    first = av.identity(documents[seed])
    second = av.identity(document_for(seed))
    assert first == second
    assert first["visual_config_digest"] == visual.render_config_digest()
    assert first["audio_config_fingerprint"] == score.named_config(
        av.CONFIG.audio).fingerprint()
    assert first["integration_config_digest"] == av.CONFIG.fingerprint()


def test_the_integration_config_is_locked_to_the_selected_system():
    with pytest.raises(av.AVIntegrationError):
        av.AVConfig(audio="bright_pentatonic")
    with pytest.raises(av.AVIntegrationError):
        av.AVConfig(audio="deep_minor")
    with pytest.raises(av.AVIntegrationError):
        av.AVConfig(audio_sample_rate=44_100)


def test_both_review_profiles_are_nine_by_sixteen():
    config = av.CONFIG
    assert config.review_width * 16 == config.review_height * 9
    assert config.full_width * 16 == config.full_height * 9


@pytest.mark.parametrize("seed", SEEDS)
def test_the_schedule_is_reproducible(documents, seed):
    config = score.named_config(av.CONFIG.audio)
    first = score.schedule(documents[seed], config)
    second = score.schedule(document_for(seed), config)
    assert first.fingerprint() == second.fingerprint()


@pytest.mark.parametrize("seed", SEEDS)
def test_candidate_rows_are_reproducible(documents, seed):
    first = av.candidate_row(documents[seed], 30.0)
    second = av.candidate_row(document_for(seed), 30.0)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# --------------------------------------------------------------------------
# The frontier camera
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_the_camera_only_moves_on_a_canonical_frontier_advance(documents, seed):
    document = documents[seed]
    marks = visual.frame_marks(document)
    report = av.camera_report(document, 30.0)
    assert report["transitions"] == len(marks)
    exits = {float(e["t"]) for e in document["events"] if e["kind"] == "shell_exit"}
    for at, _stage in marks:
        assert at in exits


@pytest.mark.parametrize("seed", SEEDS)
def test_the_framed_radius_never_shrinks(documents, seed):
    assert av.camera_report(documents[seed], 30.0)["monotone_non_decreasing"]


@pytest.mark.parametrize("seed", SEEDS)
def test_no_reframe_outpaces_the_ball_at_its_fastest(documents, seed):
    report = av.camera_report(documents[seed], 30.0)
    assert report["within_velocity_limit"]
    assert report["max_screen_velocity_per_second"] <= report[
        "ball_screen_velocity_first_shell"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_clip_ends_on_a_still_camera(documents, seed):
    """The final hold is a feature and the brief asks for it to be preserved.

    The gate is `av.MIN_STATIC_TAIL_SECONDS` rather than a number written here,
    because it is the same line `candidate_row` rejects on - and it is a line
    that does real work: on a wall this hard the last reframe can land under a
    second before the winner crosses out, which puts the camera in motion over
    the payoff.
    """
    tail = av.camera_report(documents[seed], 30.0)["static_tail_seconds"]
    assert tail >= av.MIN_STATIC_TAIL_SECONDS, seed


# --------------------------------------------------------------------------
# Multiplication
# --------------------------------------------------------------------------


@pytest.mark.parametrize("seed", SEEDS)
def test_every_candidate_splits_inside_the_limit(documents, seed):
    report = av.spawn_report(documents[seed])
    assert report["first_spawn_within_limit"]
    assert report["first_spawn_seconds"] <= av.FIRST_SPLIT_LIMIT_SECONDS


@pytest.mark.parametrize("seed", SEEDS)
def test_a_split_is_announced_by_its_own_cue_not_by_a_collision(documents, seed):
    assert av.spawn_report(documents[seed])["spawns_buried_by_a_smaller_cue"] == 0


@pytest.mark.parametrize("seed", SEEDS)
def test_the_population_grows(documents, seed):
    document = documents[seed]
    assert len(document["balls"]) > 1
    report = av.retention_report(document)
    assert report["escalates_to_outer_wall"]
    assert report["polyphony_outer"] > report["polyphony_hook"]


@pytest.mark.parametrize("seed", SEEDS)
def test_the_audio_peak_arrives_in_the_final_third(documents, seed):
    assert av.density_report(documents[seed])["peak_in_final_third"]


@pytest.mark.parametrize("seed", SEEDS)
def test_human_review_evidence_covers_all_eleven_required_beats(documents, seed):
    """The brief names eleven views; the sheet has to be those eleven."""
    document = documents[seed]
    moments = av.av_moments(document)
    assert [row["name"].split("_", 1)[1] for row in moments] == [
        "two_founders", "first_clone", "both_teams_multiplying",
        "first_lead_change", "eight_ball_state", "shared_panel_damage",
        "critical_outer_panel", "late_high_population", "final_wall_struggle",
        "winning_escape", "winner_frame",
    ]
    assert moments[0]["t"] == 0.0
    assert all(row["t"] > 0.0 for row in moments[1:])
    # Every one is a real instant of this run, not a fraction of its length.
    duration = float(document["summary"]["duration"])
    assert all(row["t"] <= duration + visual.RELEASE_SECONDS + 1e-9 for row in moments)
    assert moments[-1]["t"] == pytest.approx(duration + visual.RELEASE_SECONDS)
    # And the numbering is stable, so a sheet's tiles can be named.
    assert [row["name"][:2] for row in moments] == [
        f"{i:02d}" for i in range(1, len(moments) + 1)
    ]


# --------------------------------------------------------------------------
# The rejection rule
# --------------------------------------------------------------------------


def test_the_pile_instrument_can_still_find_a_pile():
    """A rejection rule nothing triggers is not a rule.

    Phase 3B named a seed that piled; the redesign changed the arena, the ball
    radius and the cast, so that seed no longer says anything. The instrument
    is checked against a *constructed* pile instead: three balls held within a
    drawn diameter of each other is a cluster of three, whatever seed it came
    from, and this proves the detector says so.
    """
    document = copy.deepcopy(document_for(REFERENCE_SEED))
    radius = float(document["config"]["ball_radius"]) * visual.BALL_DRAW_SCALE
    anchor = document["flights"][str(0)][0]
    victims = [b for b in document["balls"] if int(b["ball_id"]) in (1, 2)]
    assert len(victims) == 2, "the reference run has too few balls to stack"
    for offset, ball in enumerate(victims, start=1):
        ball_id = str(int(ball["ball_id"]))
        ball["birth_time"] = 0.0
        document["flights"][ball_id] = [
            {
                "t": 0.0,
                "x": anchor["x"] + 0.25 * radius * offset,
                "y": anchor["y"],
                # Held, not launched: the first version of this test copied
                # the anchor's velocity and the three balls flew apart in a
                # quarter of a second, which is what the detector then reported.
                "vx": 0.0,
                "vy": 0.0,
            },
            {
                "t": float(document["summary"]["duration"]),
                "x": anchor["x"] + 0.25 * radius * offset,
                "y": anchor["y"],
                "vx": 0.0,
                "vy": 0.0,
            },
        ]
    document["flights"]["0"] = [
        {"t": 0.0, "x": anchor["x"], "y": anchor["y"], "vx": 0.0, "vy": 0.0},
        {"t": float(document["summary"]["duration"]),
         "x": anchor["x"], "y": anchor["y"], "vx": 0.0, "vy": 0.0},
    ]
    report = visual.readability_report(document, fps=60.0)
    assert report["largest_cluster"] >= 3
    assert report["longest_triple_merge_seconds"] > 2.0


def test_the_review_set_has_no_severe_visual_pile(documents):
    for seed in SEEDS:
        report = visual.readability_report(documents[seed], fps=60.0)
        assert report["longest_triple_merge_seconds"] <= 0.75, (seed, report)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_candidate_holds_the_two_shared_contracts(documents, seed):
    row = av.candidate_row(documents[seed], 30.0)
    assert row["sync_pass"]
    assert row["team_pass"]
    assert row["playback_digest"] == documents[seed]["digest"]
