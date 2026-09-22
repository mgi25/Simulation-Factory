from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from satisfying.shell_playback import panel_closed_at
from satisfying.shell_visual import (
    ARENA_CENTRE_X_FRACTION,
    ARENA_CENTRE_Y_FRACTION,
    ARENA_WIDTH_FRACTION,
    BALL_DRAW_SCALE,
    EXPECTED_CONFIG_DIGEST,
    EXPECTED_DOCUMENT_VERSION,
    EXPECTED_SCHEMA_VERSION,
    RELEASE_SECONDS,
    REPRESENTATIVE_SEEDS,
    TRAIL_SAMPLES,
    TRAIL_SECONDS,
    active_near_misses,
    candidate_report,
    load_document,
    panel_segment,
    panel_visual_state,
    render_config_digest,
    representative_moments,
    safe_area_report,
)

ROOT = Path(__file__).parents[1]
PLAYBACK = ROOT / "docs" / "validation" / "category3_shell_escape"
SCENE = ROOT / "godot" / "scripts" / "shell_escape_scene.gd"


def _document(seed: int = 9589) -> dict:
    return load_document(PLAYBACK / f"phase1_playback_seed{seed}.json")


def test_phase1_schema_and_digest_are_unchanged() -> None:
    for seed in REPRESENTATIVE_SEEDS:
        document = _document(seed)
        assert document["document_version"] == EXPECTED_DOCUMENT_VERSION
        assert document["schema_version"] == EXPECTED_SCHEMA_VERSION
        assert document["config_digest"] == EXPECTED_CONFIG_DIGEST
        assert document["config_digest"].startswith("7da0cbc80d595826")


def test_godot_is_a_playback_consumer_not_a_physics_implementation() -> None:
    source = SCENE.read_text(encoding="utf-8")
    assert 'flight["p"]' in source and 'flight["v"]' in source
    assert '_document["panel_states"]' in source
    forbidden = (
        "RigidBody", "CharacterBody", "move_and_collide", "apply_force",
        "bounce(", "reflect(", "randomize(", "RandomNumberGenerator",
        "shell_escape.py", "shell_arena.py", "simulate(",
    )
    for token in forbidden:
        assert token not in source


def test_render_constants_match_the_godot_consumer() -> None:
    source = SCENE.read_text(encoding="utf-8")
    expected = {
        "ARENA_WIDTH_FRACTION": ARENA_WIDTH_FRACTION,
        "ARENA_CENTRE_X_FRACTION": ARENA_CENTRE_X_FRACTION,
        "ARENA_CENTRE_Y_FRACTION": ARENA_CENTRE_Y_FRACTION,
        "BALL_DRAW_SCALE": BALL_DRAW_SCALE,
        "TRAIL_SECONDS": TRAIL_SECONDS,
        "RELEASE_SECONDS": RELEASE_SECONDS,
    }
    for name, value in expected.items():
        match = re.search(rf"const {name} := ([0-9.]+)", source)
        assert match, name
        assert float(match.group(1)) == pytest.approx(value)
    match = re.search(r"const TRAIL_SAMPLES := ([0-9]+)", source)
    assert match and int(match.group(1)) == TRAIL_SAMPLES


def test_render_configuration_is_deterministic_and_stable() -> None:
    assert render_config_digest() == "77335e59def5e7f7"
    assert render_config_digest() == render_config_digest()


def test_openings_and_panels_use_canonical_shell_geometry() -> None:
    document = _document()
    for shell in document["shells"]:
        shell_id = int(shell["shell_id"])
        for slot in range(int(shell["panel_count"])):
            a, b = panel_segment(document, shell_id, slot, 3.25)
            assert math.hypot(*a) == pytest.approx(float(shell["radius"]), rel=1e-12)
            assert math.hypot(*b) == pytest.approx(float(shell["radius"]), rel=1e-12)
            state = panel_visual_state(document, shell_id, slot, 0.0)
            assert (state == "opening") == (slot in shell["open_slots"])


def test_panel_visualization_matches_canonical_states() -> None:
    document = _document()
    for shell in document["shells"]:
        shell_id = int(shell["shell_id"])
        for panel_id in range(int(shell["panel_count"])):
            if panel_id in shell["open_slots"]:
                continue
            for t in (0.0, 7.0, 14.0, float(document["summary"]["duration"])):
                state = panel_visual_state(document, shell_id, panel_id, t)
                assert (state != "broken") == panel_closed_at(
                    document, shell_id, panel_id, t
                )
                assert state in {"healthy", "damaged", "heavily_damaged", "broken"}


def test_damage_states_are_derived_only_from_canonical_damage_events() -> None:
    document = _document()
    damage = next(event for event in document["events"] if event["kind"] == "damage")
    shell_id, panel_id, t = damage["shell_id"], damage["panel_id"], damage["t"]
    assert panel_visual_state(document, shell_id, panel_id, t - 1e-8) == "healthy"
    assert panel_visual_state(document, shell_id, panel_id, t) in {
        "healthy", "damaged", "heavily_damaged", "broken"
    }


def test_near_miss_feedback_occurs_only_for_canonical_near_miss_events() -> None:
    document = _document()
    miss = next(event for event in document["events"] if event["kind"] == "near_miss")
    active = active_near_misses(document, float(miss["t"]) + 0.02)
    assert miss in active
    assert all(event["kind"] == "near_miss" for event in active)
    collision = next(
        event for event in document["events"]
        if event["kind"] == "collision"
        and not any(
            near["kind"] == "near_miss" and near["t"] == event["t"]
            for near in document["events"]
        )
    )
    assert active_near_misses(document, float(collision["t"]) + 1e-6) == []


def test_event_order_is_identical_in_every_representative_document() -> None:
    for seed in REPRESENTATIVE_SEEDS:
        events = _document(seed)["events"]
        assert [event["t"] for event in events] == sorted(event["t"] for event in events)
        assert events[-1]["kind"] == "escape"


def test_safe_area_configuration_clears_every_critical_target() -> None:
    for seed in REPRESENTATIVE_SEEDS:
        report = safe_area_report(_document(seed))
        assert report["safe_area_fingerprint"] == "3776358f1bf13326"
        assert report["arena_occupancy_width_pct"] == 72.0
        assert report["outer_shell_clearance_px"] > 0.0
        assert report["ball_hidden_frames"] == 0
        assert report["openings_clear"]
        assert report["hook_clearance_px"] > 0.0
        assert report["final_escape_clearance_px"] > 0.0
        assert report["gate_pass"]


def test_seven_required_evidence_moments_exist() -> None:
    names = [name for name, _ in representative_moments(_document())]
    assert names == [
        "a_opening", "b_first_shell", "c_near_miss", "d_panel_break",
        "e_middle_progress", "f_outer_sequence", "g_final_escape",
    ]


def test_candidate_cast_covers_bands_routes_and_mixed_progression() -> None:
    reports = [candidate_report(_document(seed)) for seed in REPRESENTATIVE_SEEDS]
    assert any(20 <= row["duration"] < 22 for row in reports)
    assert any(22 <= row["duration"] < 24 for row in reports)
    assert any(24 <= row["duration"] <= 26 for row in reports)
    assert {row["final_method"] for row in reports} == {"opening", "break"}
    assert max(row["near_misses"] for row in reports) >= 15
    mixed = next(row for row in reports if row["seed"] == 11929)
    assert (mixed["opening_progressions"], mixed["break_progressions"]) == (2, 4)


def test_visual_phase_contains_no_audio_implementation() -> None:
    source = SCENE.read_text(encoding="utf-8")
    assert "AudioStream" not in source
    assert "play()" not in source


def test_recorded_godot_audit_replays_without_reordering() -> None:
    path = ROOT / "docs" / "validation" / "category3_shell_visual_v2a" \
        / "playback_audit_seed9589.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["pass"]
    assert audit["digest_matches"]
    assert audit["event_order_unchanged"]
    assert audit["event_kinds_unchanged"]
    assert audit["panel_states_unchanged"]
    assert audit["sampled_positions_match"]
