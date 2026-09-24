"""Phase 4C: the production identity, and what may not drift under it.

The deliverable is a file somebody uploads. The claim attached to it is that
this repository at this commit can make that file again, and these are the
assertions that claim rests on. They are deliberately about the *identity* and
the *command graph* rather than about the bytes of the encode: x264 is free to
differ between builds, so what is fixed here is everything upstream of it plus
the decoded properties the brief names.
"""

from __future__ import annotations

import inspect

import pytest

from satisfying import multishell_av as av
from satisfying import multishell_production as production
from satisfying import multishell_production_cli as production_cli
from satisfying import multishell_visual as visual
from satisfying.multishell_playback import document_for


@pytest.fixture(scope="module")
def document():
    return document_for(production.PRODUCTION.seed)


# --------------------------------------------------------------------------
# The configuration
# --------------------------------------------------------------------------


def test_the_production_is_the_delivery_profile_the_brief_asks_for():
    """1080x1920, 60 fps, H.264 CRF 17 slow, AAC 192 kbps at 48 kHz."""
    config = production.PRODUCTION
    assert (config.width, config.height) == (1080, 1920)
    assert config.width * 16 == config.height * 9
    assert config.fps == 60.0
    assert config.video_codec == "libx264"
    assert config.crf == 17
    assert config.preset == "slow"
    assert config.pixel_format == "yuv420p"
    assert config.audio_codec == "aac"
    assert config.audio_bitrate == "192k"
    assert config.audio_sample_rate == 48_000
    assert config.faststart is True


def test_the_archive_is_a_better_master_and_carries_pcm():
    """An archive that is worse than the delivery is not an archive."""
    config = production.PRODUCTION
    assert config.archive_crf < config.crf
    assert config.archive_audio.startswith("pcm")
    assert "24" in config.archive_audio, "the brief asks for 24-bit PCM"


def test_the_delivery_configuration_is_deterministic():
    """Same dials, same fingerprint; one dial moved, a different one."""
    first = production.ProductionConfig()
    second = production.ProductionConfig()
    assert first.fingerprint() == second.fingerprint()
    assert production.PRODUCTION.fingerprint() == first.fingerprint()
    assert len(first.fingerprint()) == 16
    moved = production.ProductionConfig(crf=18)
    assert moved.fingerprint() != first.fingerprint()


def test_the_production_cannot_describe_a_framing_the_renderer_does_not_use():
    """The identity is only worth having if it cannot lie about the render.

    A production block recording 1.200 beside a renderer drawing 0.850 would
    be a document describing a file nobody made, which is the exact failure
    the 1.778x frustum error was. So the configuration refuses to exist unless
    its framing and its camera-stage count are the renderer's own.
    """
    assert (production.PRODUCTION.frame_fraction
            == visual.FRONTIER_WIDTH_FRACTION)
    assert (production.PRODUCTION.camera_stages
            == len(visual.CAMERA_STAGE_PLAN))
    assert production.PRODUCTION.transitions == 1
    with pytest.raises(production.ProductionError):
        production.ProductionConfig(frame_fraction=0.850)
    with pytest.raises(production.ProductionError):
        production.ProductionConfig(camera_stages=3)


def test_the_production_refuses_a_seed_outside_the_frozen_candidate_set():
    with pytest.raises(production.ProductionError):
        production.ProductionConfig(seed=1)


def test_the_production_refuses_to_redesign_the_score():
    """The 4C brief freezes the audio; the configuration enforces it."""
    with pytest.raises(production.ProductionError):
        production.ProductionConfig(audio="something_else")
    assert production.PRODUCTION.audio == av.CONFIG.audio


# --------------------------------------------------------------------------
# The identity
# --------------------------------------------------------------------------


def test_the_production_identity_is_deterministic(document):
    """Two calls, byte-identical - including the camera schedule inside it."""
    first = production.identity(document)
    visual._STAGE_CACHE.clear()
    second = production.identity(document_for(production.PRODUCTION.seed))
    assert first == second


def test_the_identity_records_every_layer_the_brief_asks_for(document):
    identity = production.identity(document)
    assert identity["production"]["seed"] == production.PRODUCTION.seed
    assert identity["production"]["frame"] == [1080, 1920]
    assert identity["production"]["fps"] == 60.0
    assert identity["production"]["frame_fraction"] == pytest.approx(1.200)
    assert identity["production"]["camera_transitions"] == 1
    # The four digests the brief names, each from its own layer.
    assert identity["run"]["config_digest"] == visual.EXPECTED_CONFIG_DIGEST
    assert identity["run"]["playback_digest"] == document["digest"]
    assert identity["visual"]["render_config_digest"] == \
        visual.render_config_digest()
    assert identity["audio"]["fingerprint"] == \
        production.PRODUCTION.audio_config.fingerprint()
    # And the camera transition, as a trigger and a time rather than a claim.
    stages = identity["visual"]["camera_stages"]
    assert len(stages) == 2
    assert stages[1]["trigger_region"] == 2
    assert stages[1]["settled"] - stages[1]["start"] == pytest.approx(
        visual.FRAME_EASE_SECONDS)
    assert identity["visual"]["camera_lock_time"] == pytest.approx(
        stages[1]["settled"])


def test_the_identity_refuses_a_document_for_another_seed():
    other = document_for(17964)
    with pytest.raises(production.ProductionError):
        production.identity(other)


# --------------------------------------------------------------------------
# What the master is a video of
# --------------------------------------------------------------------------


def test_the_simulation_is_unchanged(document):
    """The 4C brief freezes the mechanic; this is the check, not the promise.

    The config digest is the whole frozen Phase 1 operating configuration, and
    it is the same string Phase 4A, 4B and 4C all render against. The schema
    version pins the document's shape on top of it.
    """
    assert document["config_digest"] == visual.EXPECTED_CONFIG_DIGEST
    assert document["schema"] == visual.EXPECTED_SCHEMA_VERSION
    summary = document["summary"]
    assert int(summary["ball_collisions"]) == 0
    assert float(summary["speed_min"]) == pytest.approx(10.0, abs=1e-9)
    assert float(summary["speed_max"]) == pytest.approx(10.0, abs=1e-9)


def test_the_race_winner_is_unchanged(document):
    """1176 is the destruction candidate and this is what that means.

    Orange wins by **break** - the outermost wall fails at 23.27 s and the
    winner goes through the hole 0.50 s later - which is the sequence the
    brief calls the most important proof of the destruction design. A
    presentation change that altered any of this would have changed the
    simulation, which the brief forbids.
    """
    summary = document["summary"]
    assert int(summary["winner_team"]) == 1
    assert summary["winner_team_name"] == "orange"
    assert summary["winner_route"] == "break"
    assert int(summary["escape_ball"]) == 10
    assert float(summary["escape_time"]) == pytest.approx(23.7651458, abs=1e-6)
    assert int(summary["max_population"]) == 12
    assert int(summary["breaks"]) == 20
    # The winning route is a real break of the outermost shell, used after it.
    outer = max(int(shell["shell_id"]) for shell in document["shells"])
    breaks = [event for event in document["events"]
              if event["kind"] == "panel_break" and int(event["shell_id"]) == outer]
    assert breaks, "the outer wall never breaks, so the win cannot be by break"
    assert min(float(event["t"]) for event in breaks) < float(
        summary["escape_time"])


def test_the_final_camera_is_static_for_the_whole_payoff(document):
    """The brief's "final 6 to 10 seconds fully static", on the real candidate."""
    tail = visual.static_tail_seconds(document)
    assert tail > 6.0
    lock = visual.camera_lock_time(document)
    escape = float(document["summary"]["escape_time"])
    assert lock < escape
    # Nothing moves the camera between the lock and the end of the release.
    locked = visual.view_radius_at(document, lock)
    for index in range(2001):
        t = lock + (escape + visual.RELEASE_SECONDS - lock) * index / 2000.0
        assert visual.view_radius_at(document, t) == pytest.approx(
            locked, rel=1e-12)


# --------------------------------------------------------------------------
# The command graph
# --------------------------------------------------------------------------


def test_the_archive_is_not_derived_from_the_delivery_or_the_other_way():
    """The brief's sourcing rule, as a property of the code rather than a claim.

    Both commands call one `_encode`, which only ever reads the PNG sequence
    and the master WAV. Neither ever names the other's output as an input, so
    a generation loss cannot be introduced by running them in either order -
    or by running one of them twice.
    """
    deliver = inspect.getsource(production_cli.cmd_deliver)
    archive = inspect.getsource(production_cli.cmd_archive)
    assert "archive_path" not in deliver
    assert "delivery_path" not in archive
    encode = inspect.getsource(production_cli._encode)
    assert "frames_dir(config)" in encode
    assert "wav_path" in encode
    for name in ("delivery_path", "archive_path"):
        assert name not in encode, "the encoder chose its own source"
    # And the encode reads PNGs, not a video file.
    assert "frame_%05d.png" in encode


def test_the_production_render_asks_for_the_production_frame():
    """The frame command may not quietly render the review profile."""
    source = inspect.getsource(production_cli.cmd_frames)
    assert "--width={config.width}" in source
    assert "--height={config.height}" in source
    assert "--fps={config.fps:g}" in source
    assert "--clip=1" in source


def test_the_qc_checks_cover_the_briefs_list():
    """Every named delivery check is actually in the check set."""
    source = inspect.getsource(production_cli.cmd_qc)
    for name in (
        "resolution_is_production", "fps_is_production",
        "video_codec_is_production", "audio_codec_is_production",
        "sample_rate_is_production", "stereo",
        "av_drift_under_one_frame", "no_clipped_samples", "no_limiter",
        "cue_sync_pass", "no_black_span",
    ):
        assert f'"{name}"' in source
    # And the digests the brief asks to be published with the master.
    for name in ("playback", "master_wav", "delivery_mp4", "archive_mkv"):
        assert f'"{name}"' in source
