"""Focused contracts for the Category 3 Test #2 production master.

These are the things a delivered file has to keep being true about, written so
that a later change which quietly moves the seed, the score, the frame, the
rate or the encoder fails here rather than in somebody's upload.

The tests that need the delivered MP4 skip when it is absent, because
`output/` is gitignored and a clone has no master in it. The tests that decide
*what* would be delivered need nothing but the repository, and never skip.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from satisfying import (
    shell_av,
    shell_production,
    shell_production_cli,
    shell_score,
    shell_visual,
)


ROOT = Path(__file__).resolve().parents[1]
PLAYBACK = (
    ROOT / "docs" / "validation" / "category3_shell_escape" /
    "phase1_playback_seed9589.json"
)
EVIDENCE = ROOT / "docs" / "validation" / "category3_shell_production_v4"
OUT = ROOT / "output" / "category3_shell_production_v4"
DELIVERY = OUT / "master" / "category3_test2_seed9589_delivery.mp4"


def _document() -> dict:
    return json.loads(PLAYBACK.read_text(encoding="utf-8"))


def _evidence(name: str) -> dict:
    path = EVIDENCE / name
    if not path.is_file():
        pytest.skip(f"{path} is produced by shell_production_cli; not in a clone")
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# What is being delivered
# --------------------------------------------------------------------------


def test_the_production_seed_is_the_one_phase_three_selected():
    assert shell_production.PRODUCTION.seed == 9589
    assert shell_production.PRODUCTION.backup_seed == 11929


def test_a_production_cannot_quietly_be_built_on_another_seed():
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(seed=11929)
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(seed=3654)


def test_the_backup_is_reachable_but_only_by_naming_it():
    backup = shell_production_cli._backup_config(shell_production.PRODUCTION, 11929)
    assert backup.seed == 11929
    # Every other dial is the production's, so the backup is the same film.
    primary = shell_production.PRODUCTION.as_dict()
    changed = {key for key, value in backup.as_dict().items()
               if value != primary[key]}
    assert changed == {"seed", "name"}


def test_the_frozen_simulation_contract_is_unchanged():
    document = _document()
    assert document["schema_version"] == "category3-test2-shell-escape/1.0.0"
    assert document["config_digest"].startswith("7da0cbc80d595826")
    assert document["schema_version"] == shell_visual.EXPECTED_SCHEMA_VERSION
    assert document["config_digest"] == shell_visual.EXPECTED_CONFIG_DIGEST
    shell_av.validate_shared_document(document)


def test_the_production_never_reaches_the_simulator():
    """Neither production module may import or call the simulator.

    Checked over the parsed import graph rather than the raw text, because
    both modules legitimately mention the string `category3_shell_escape` -
    it is the directory the recorded Phase 1 playback is read from, which is
    precisely the point: the production reads that file instead of running
    the thing that produced it.
    """
    import ast

    for module in (shell_production, shell_production_cli):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported.update(f"{node.module}.{a.name}" for a in node.names)
        assert not {name for name in imported
                    if "shell_escape" in name or "shell_arena" in name}, module.__name__
        called = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "simulate" not in called, module.__name__


# --------------------------------------------------------------------------
# Determinism of the configuration
# --------------------------------------------------------------------------


def test_the_visual_configuration_is_deterministic_and_unmoved():
    assert shell_visual.render_config_digest() == "77335e59def5e7f7"
    assert shell_visual.render_config_digest() == shell_visual.render_config_digest()


def test_the_audio_configuration_is_deterministic_and_unmoved():
    config = shell_production.PRODUCTION.audio_config
    assert shell_production.PRODUCTION.audio == "refined_hybrid"
    assert config.fingerprint() == "eaedaafdb37866f1"
    assert config.fingerprint() == shell_score.DEFAULT_CONFIG.fingerprint()


def test_the_production_identity_is_deterministic():
    document = _document()
    first = shell_production.identity(document)
    second = shell_production.identity(document)
    assert first == second
    assert (shell_production.production_digest(document)
            == shell_production.production_digest(document))
    assert first["production"]["fingerprint"] == shell_production.PRODUCTION.fingerprint()


def test_the_identity_separates_the_layers_it_claims_to():
    base = shell_production.identity()
    moved = shell_production.identity(
        config=shell_production_cli._backup_config(
            shell_production.PRODUCTION, 11929)
    )
    # Moving the seed moves `production`, and no other layer.
    assert base["encode"] == moved["encode"]
    assert base["audio"] == moved["audio"]
    assert base["composition"] == moved["composition"]
    assert base["simulation"] == moved["simulation"]
    assert base["safe_area"] == moved["safe_area"]
    assert base["production"]["fingerprint"] != moved["production"]["fingerprint"]


def test_an_identity_refuses_a_playback_that_is_not_its_own_seed():
    """The identity is a claim about one file, so it checks its own inputs."""
    backup = shell_production_cli._backup_config(shell_production.PRODUCTION, 11929)
    with pytest.raises(shell_production.ProductionError):
        shell_production.identity(_document(), backup)


# --------------------------------------------------------------------------
# The delivery configuration
# --------------------------------------------------------------------------


def test_the_delivery_profile_is_the_locked_one():
    config = shell_production.PRODUCTION
    assert (config.width, config.height) == (1080, 1920)
    assert config.fps == 60.0
    assert config.video_codec == "libx264"
    assert config.crf == 17
    assert config.preset == "slow"
    assert config.pixel_format == "yuv420p"
    assert config.audio_codec == "aac"
    assert config.audio_bitrate == "192k"
    assert config.audio_sample_rate == 48_000
    assert config.faststart is True


def test_the_frame_rate_cannot_drift_from_the_rate_the_visual_layer_renders():
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(fps=30.0)


def test_the_hook_and_the_score_cannot_be_swapped_silently():
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(hook="WILL IT ESCAPE?")
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(audio="clean_percussive")


def test_the_master_applies_no_gain_limiter_or_compressor():
    identity = shell_production.identity()
    assert identity["audio"]["master_gain_db"] == 0.0
    assert identity["audio"]["limiter"] is False
    assert identity["audio"]["compressor"] is False
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(master_gain_db=3.0)


def test_the_archive_may_not_be_worse_than_the_delivery_file():
    assert shell_production.PRODUCTION.archive_crf < shell_production.PRODUCTION.crf
    assert shell_production.PRODUCTION.archive_audio == "pcm_s24le"
    with pytest.raises(shell_production.ProductionError):
        shell_production.ProductionConfig(archive_crf=20)


def test_the_delivery_ceiling_is_the_repositorys_established_one():
    from satisfying import tile_phase6_cli

    assert (shell_production.DELIVERY_TRUE_PEAK_DBTP
            == tile_phase6_cli.DELIVERY_TRUE_PEAK_DBTP == -1.0)


def test_the_expected_frame_count_matches_the_renderers_own_clock():
    document = _document()
    # `shell_escape_render.gd` writes indices 0..floor(render_duration*fps).
    duration = (float(document["summary"]["duration"])
                + shell_visual.RELEASE_SECONDS + shell_visual.END_HOLD_SECONDS)
    assert (shell_production.rendered_frame_count(document, 60.0)
            == int(math.floor(duration * 60.0)) + 1 == 1422)


# --------------------------------------------------------------------------
# The delivered file
# --------------------------------------------------------------------------


def test_the_delivered_master_passed_every_verification_gate():
    report = _evidence("delivery_verification.json")
    assert report["failures"] == []
    assert report["pass"]


def test_the_delivered_master_is_1080x1920_at_60_fps():
    container = _evidence("delivery_verification.json")["container"]
    assert (container["width"], container["height"]) == (1080, 1920)
    assert container["fps"] == 60.0
    assert container["video_codec"] == "h264"
    assert container["audio_codec"] == "aac"
    assert container["audio_sample_rate"] == 48_000
    assert container["faststart"]


def test_the_delivered_duration_is_the_simulation_plus_its_resolution():
    report = _evidence("delivery_verification.json")
    document = _document()
    duration = float(document["summary"]["duration"])
    # The picture runs to the last rendered frame and the score resolves just
    # after it; nothing is allowed to wander past that.
    assert duration < report["container"]["duration_seconds"] < duration + 1.0
    assert report["container"]["muxed_frames"] >= report["container"]["rendered_frames"]
    assert report["final_frame_padding_frames"] <= 60


def test_the_delivered_audio_does_not_clip_and_keeps_its_headroom():
    audio = _evidence("delivery_verification.json")["audio"]
    assert audio["clipped_samples"] == 0
    assert audio["true_peak_dbtp"] <= shell_production.DELIVERY_TRUE_PEAK_DBTP
    assert audio["sample_peak_dbfs"] < 0.0


def test_the_delivered_audio_keeps_a_musical_dynamic_range():
    audio = _evidence("delivery_verification.json")["audio"]
    # Phase 3 measured 6.03 LU on the source. A master that flattened the
    # six-register hierarchy would show up here as a collapsed range.
    assert audio["loudness_range_lu"] > 4.0


def test_the_delivered_file_ends_in_silence_rather_than_a_cut():
    audio = _evidence("delivery_verification.json")["audio"]
    assert audio["final_50ms_peak_dbfs"] <= -40.0


def test_every_cue_class_stays_inside_one_delivered_frame():
    sync = _evidence("delivery_verification.json")["sync"]
    assert sync["pass"]
    assert sync["within_one_rendered_frame"]
    for kind in ("collision", "post", "near_miss", "break", "shell_exit", "escape"):
        assert sync["timing"][kind]["within_one_frame"], kind
        assert sync["timing"][kind]["count"] > 0


def test_the_delivered_picture_and_score_read_one_canonical_document():
    sync = _evidence("delivery_verification.json")["sync"]
    assert sync["playback_digest"] == sync["visual_playback_digest"]
    assert sync["playback_digest"] == sync["score_playback_digest"]
    assert sync["playback_digest"] == _document()["digest"]


def test_the_conservative_shorts_gate_passes_across_the_whole_clip():
    report = _evidence("safe_area.json")
    assert report["safe_area"] == "shorts_conservative"
    assert report["gate_pass"]
    assert report["ball_hidden_frames"] == 0
    assert report["openings_clear"]
    assert report["outer_shell_clearance_px"] >= 0.0
    assert report["hook_clearance_px"] >= 0.0
    assert report["final_escape_clearance_px"] >= 0.0
    # The sweep has to have been taken at the delivered rate, not the default.
    assert report["fps"] == 60.0


def test_the_recorded_identity_matches_the_repository_it_claims_to_come_from():
    identity = _evidence("production_identity.json")
    document = _document()
    assert identity["production"]["seed"] == 9589
    assert identity["production"]["fps"] == 60.0
    assert identity["run"]["digest"] == document["digest"]
    assert identity["run"]["config_digest"] == shell_visual.EXPECTED_CONFIG_DIGEST
    assert identity["composition"]["visual_config_digest"] == shell_visual.render_config_digest()
    assert identity["audio"]["fingerprint"] == shell_score.DEFAULT_CONFIG.fingerprint()
    assert identity["production_digest"] == shell_production.production_digest(document)


def test_the_delivered_master_exists_where_the_report_says_it_does():
    if not DELIVERY.is_file():
        pytest.skip("output/ is gitignored; run `shell_production_cli master`")
    assert DELIVERY.stat().st_size > 1_000_000
