"""Focused contracts for the Category 3 Test #2 audiovisual integration."""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

from satisfying import shell_audio, shell_av, shell_score, shell_visual


ROOT = Path(__file__).resolve().parents[1]
PLAYBACK = (
    ROOT / "docs" / "validation" / "category3_shell_escape" /
    "phase1_playback_seed11929.json"
)


def _document():
    return json.loads(PLAYBACK.read_text(encoding="utf-8"))


def _visual_audit(document):
    return {
        "seed": document["seed"],
        "digest": document["digest"],
        "schema_version": document["schema_version"],
        "config_digest": document["config_digest"],
        "event_times": [event["t"] for event in document["events"]],
        "event_kinds": [event["kind"] for event in document["events"]],
    }


def _audit():
    document = _document()
    return shell_av.sync_audit(document, _visual_audit(document), 30)


def test_both_branches_preserve_the_frozen_schema_and_config():
    document = _document()
    assert document["schema_version"] == shell_visual.EXPECTED_SCHEMA_VERSION
    assert document["schema_version"] == shell_score.SCHEMA_VERSION
    assert document["config_digest"] == shell_visual.EXPECTED_CONFIG_DIGEST
    assert document["config_digest"] == shell_score.CONFIG_DIGEST
    shell_av.validate_shared_document(document)


def test_visual_and_audio_read_the_same_playback_digest():
    report = _audit()
    assert report["playback_digest"] == report["visual_playback_digest"]
    assert report["playback_digest"] == report["score_playback_digest"]


def test_exact_canonical_event_order_is_shared_by_both_consumers():
    report = _audit()
    assert report["visual_event_order_exact"]
    assert report["audio_source_order_shared"]
    assert report["event_order_digest"] == shell_av.event_order_digest(_document())


def test_every_collision_is_av_synchronised_within_one_frame():
    row = _audit()["timing"]["collision"]
    assert row["count"] == 76
    assert row["within_one_frame"]


def test_every_near_miss_ornament_is_av_synchronised_within_one_frame():
    row = _audit()["timing"]["near_miss"]
    assert row["count"] == 12
    assert row["within_one_frame"]


def test_every_break_bloom_is_av_synchronised_within_one_frame():
    row = _audit()["timing"]["break"]
    assert row["count"] == 14
    assert row["within_one_frame"]


def test_every_first_outward_shell_exit_is_av_synchronised_within_one_frame():
    row = _audit()["timing"]["shell_exit"]
    assert row["count"] == 6
    assert row["within_one_frame"]


def test_final_escape_resolution_is_av_synchronised_within_one_frame():
    report = _audit()
    row = report["timing"]["escape"]
    assert row["count"] == 1
    assert row["within_one_frame"]
    assert report["within_one_rendered_frame"]


def test_audio_does_not_mutate_playback():
    document = _document()
    before = copy.deepcopy(document)
    plan = shell_score.schedule(document, shell_score.named_config("refined_hybrid"))
    shell_audio.render(plan)
    assert document == before


def test_visual_layer_does_not_recompute_physics():
    python_source = inspect.getsource(shell_visual)
    godot_source = (ROOT / "godot" / "scripts" / "shell_escape_scene.gd").read_text(
        encoding="utf-8"
    )
    for forbidden in ("from satisfying.shell_escape import", "shell_arena", "simulate("):
        assert forbidden not in python_source
    for forbidden in ("PhysicsBody", "move_and_collide", "move_and_slide", "RandomNumberGenerator"):
        assert forbidden not in godot_source
    assert "_document[\"flights\"]" in godot_source


def test_integrated_render_and_score_configuration_is_deterministic():
    document = _document()
    first = shell_av.identity(document)
    second = shell_av.identity(document)
    assert first == second
    assert first["integration_config_digest"] == shell_av.CONFIG.fingerprint()
    assert first["visual_config_digest"] == "77335e59def5e7f7"
    assert first["audio_config"] == "refined_hybrid"
    assert first["audio_config_fingerprint"] == shell_score.DEFAULT_CONFIG.fingerprint()


def test_post_contacts_share_the_collision_clock_and_complete_mapping():
    report = _audit()
    assert report["timing"]["post"]["count"] > 0
    assert report["timing"]["post"]["within_one_frame"]
    assert report["mapping_complete"]
    assert report["pass"]
