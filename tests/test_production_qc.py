"""Phase 6C tests: what a finished Short has to prove.

Every rule here is checked against facts rather than against files, which is
the whole reason gathering and judging are separate: a batch of video is not
needed to prove that a sequence one frame short fails, or that a true peak
above the limit fails while a quiet Short only warns.

The aggregate sequence hash gets real files, because what it has to detect -
a missing frame, a changed frame, two frames swapped - is a property of the
directory rather than of a dataclass.
"""

from __future__ import annotations

import json
import os
import struct
import zlib

import pytest

from audio.soundtrack import SOUNDTRACK_VERSION
from production import qc
from rendering import png_frames
from rendering.render_plan import RENDER_FORMAT_VERSION, frame_filename
from replay.exporter import REPLAY_VERSION

SEED = 21465
FRAMES = 969
GAMEPLAY = 861
SAMPLES = FRAMES * 800


def item(**overrides) -> dict:
    """A manifest item, in exactly the shape build_batch writes."""
    entry = {
        "index": 3,
        "seed": SEED,
        "arena_mode": "procedural",
        "layout_id": f"procedural-{SEED}",
        "label": "TITAN vs ORBIT",
        "powers": ["titan", "orbit"],
        "matchup": ["orbit", "titan"],
        "winner_id": 0,
        "duration": 14.342,
        "score": 92.646,
    }
    entry.update(overrides)
    return entry


def replay_facts(**overrides) -> qc.ReplayFacts:
    settings = {
        "exists": True,
        "version": REPLAY_VERSION,
        "seed": SEED,
        "powers": ("titan", "orbit"),
        "winner_id": 0,
        "is_draw": False,
        "duration": 14.342,
        "sha256": "a" * 64,
    }
    settings.update(overrides)
    return qc.ReplayFacts(**settings)


def render_facts(**overrides) -> qc.RenderFacts:
    settings = {
        "exists": True,
        "render_version": RENDER_FORMAT_VERSION,
        "width": 1080,
        "height": 1920,
        "fps": 60,
        "frame_count": FRAMES,
        "gameplay_frames": GAMEPLAY,
        "post_roll_frames": 108,
        "replay_sha256": "a" * 64,
        "sequence_sha256": "b" * 64,
    }
    settings.update(overrides)
    return qc.RenderFacts(**settings)


def audio_facts(**overrides) -> qc.AudioFacts:
    settings = {
        "exists": True,
        "audio_version": SOUNDTRACK_VERSION,
        "sample_rate": 48000,
        "channels": 2,
        "bit_depth": 24,
        "samples": SAMPLES,
        "pcm_sha256": "c" * 64,
        "replay_sha256": "a" * 64,
        "peak": 0.86,
    }
    settings.update(overrides)
    return qc.AudioFacts(**settings)


def video_facts(**overrides) -> qc.VideoFacts:
    settings = {
        "exists": True,
        "sha256": "d" * 64,
        "size": 6_500_000,
        "codec": "h264",
        "profile": "High",
        "width": 1080,
        "height": 1920,
        "pix_fmt": "yuv420p",
        "frame_rate": "60/1",
        "field_order": "progressive",
        "frames": FRAMES,
        "duration": FRAMES / 60,
        "audio_codec": "aac",
        "audio_profile": "LC",
        "audio_rate": 48000,
        "audio_channels": 2,
        "audio_duration": FRAMES / 60,
        "decoded_samples": SAMPLES + 992,
        "faststart": True,
    }
    settings.update(overrides)
    return qc.VideoFacts(**settings)


def loudness_facts(**overrides) -> qc.LoudnessFacts:
    settings = {
        "integrated_lufs": -20.3,
        "true_peak_dbfs": -1.3,
        "range_lu": 2.0,
        "band_lufs": -22.5,
    }
    settings.update(overrides)
    return qc.LoudnessFacts(**settings)


def evidence(**overrides) -> qc.Evidence:
    settings = {
        "item": item(),
        "replay": replay_facts(),
        "render": render_facts(),
        "audio": audio_facts(),
        "video": video_facts(),
        "loudness": loudness_facts(),
    }
    settings.update(overrides)
    return qc.Evidence(**settings)


def problems_of(**overrides) -> list[str]:
    return qc.evaluate(evidence(**overrides))[0]


def mentions(lines: list[str], fragment: str) -> bool:
    return any(fragment in line for line in lines)


# --- versions -------------------------------------------------------------


def test_qc_has_its_own_version() -> None:
    """One number per thing that has a schema, and QC is a thing."""
    assert qc.QC_VERSION == 1
    assert REPLAY_VERSION == 6
    assert RENDER_FORMAT_VERSION == 1
    assert SOUNDTRACK_VERSION == 1


def test_the_production_format_qc_checks_is_the_one_that_is_produced() -> None:
    from rendering import encode

    assert (qc.EXPECTED_WIDTH, qc.EXPECTED_HEIGHT) == (
        encode.DEFAULT_SPEC.width,
        encode.DEFAULT_SPEC.height,
    )
    assert qc.EXPECTED_FPS == encode.DEFAULT_SPEC.fps
    assert qc.EXPECTED_SAMPLE_RATE == encode.DEFAULT_SPEC.sample_rate
    assert qc.EXPECTED_CHANNELS == encode.DEFAULT_SPEC.channels
    assert qc.SAMPLES_PER_FRAME == 800


# --- the aggregate frame-sequence hash ------------------------------------


def write_png(path: str, width: int, height: int, fill: bytes = b"\x20\x30\x40") -> str:
    raw = b"".join(b"\x00" + fill * width for _ in range(height))
    chunks = [
        (b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
        (b"IDAT", zlib.compress(raw, 1)),
        (b"IEND", b""),
    ]
    body = b"".join(
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload))
        for kind, payload in chunks
    )
    with open(path, "wb") as handle:
        handle.write(png_frames.PNG_SIGNATURE + body)
    return path


def make_sequence(directory, count: int, size: int = 4) -> str:
    frames_dir = os.path.join(str(directory), "frames")
    os.makedirs(frames_dir, exist_ok=True)
    for index in range(count):
        write_png(
            os.path.join(frames_dir, frame_filename(index)),
            size,
            size,
            bytes((index % 251, (index * 7) % 251, 60)),
        )
    return frames_dir


def test_the_sequence_hash_is_stable_for_the_same_sequence(tmp_path) -> None:
    frames_dir = make_sequence(tmp_path, 6)
    first = qc.sequence_digest(frames_dir, 6)
    assert first == qc.sequence_digest(frames_dir, 6)
    assert len(first) == 64


def test_the_sequence_hash_does_not_depend_on_modification_time(tmp_path) -> None:
    """A file touched but not changed is the same sequence."""
    frames_dir = make_sequence(tmp_path, 4)
    before = qc.sequence_digest(frames_dir, 4)
    path = os.path.join(frames_dir, frame_filename(2))
    os.utime(path, (1_000_000, 1_000_000))
    assert qc.sequence_digest(frames_dir, 4) == before


def test_the_sequence_hash_notices_a_missing_frame(tmp_path) -> None:
    frames_dir = make_sequence(tmp_path, 5)
    os.remove(os.path.join(frames_dir, frame_filename(3)))
    with pytest.raises(qc.QcError):
        qc.sequence_digest(frames_dir, 5)


def test_the_sequence_hash_notices_a_changed_frame(tmp_path) -> None:
    frames_dir = make_sequence(tmp_path, 5)
    before = qc.sequence_digest(frames_dir, 5)
    write_png(os.path.join(frames_dir, frame_filename(2)), 4, 4, b"\xff\x00\x00")
    assert qc.sequence_digest(frames_dir, 5) != before


def test_the_sequence_hash_notices_two_frames_swapped(tmp_path) -> None:
    """Same files, same bytes, different order: a different video."""
    frames_dir = make_sequence(tmp_path, 5)
    before = qc.sequence_digest(frames_dir, 5)
    one = os.path.join(frames_dir, frame_filename(1))
    other = os.path.join(frames_dir, frame_filename(3))
    spare = os.path.join(frames_dir, "spare.bin")
    os.rename(one, spare)
    os.rename(other, one)
    os.rename(spare, other)
    assert qc.sequence_digest(frames_dir, 5) != before


def test_the_sequence_hash_covers_the_length_it_was_asked_for(tmp_path) -> None:
    """A longer render is a different sequence even if it starts the same."""
    frames_dir = make_sequence(tmp_path, 6)
    assert qc.sequence_digest(frames_dir, 4) != qc.sequence_digest(frames_dir, 5)


def test_the_sequence_hash_records_how_it_was_taken() -> None:
    """So a change of method is visible in the record rather than silent."""
    assert qc.SEQUENCE_METHOD == "file-sha256"
    record = qc.qc_record(evidence(), batch_id="b", problems=[], warnings=[])
    assert record["render"]["sequence_method"] == qc.SEQUENCE_METHOD


def test_a_negative_frame_count_is_refused(tmp_path) -> None:
    with pytest.raises(qc.QcError):
        qc.sequence_digest(str(tmp_path), -1)


# --- visual sanity checkpoints -------------------------------------------


def test_the_checkpoints_cover_the_whole_short_in_order() -> None:
    points = qc.visual_checkpoints(FRAMES, GAMEPLAY)
    assert list(points) == [
        "first",
        "intro end",
        "25%",
        "50%",
        "75%",
        "final gameplay",
        "result panel",
        "last",
    ]
    indices = list(points.values())
    assert indices == sorted(indices)
    assert points["first"] == 0
    assert points["final gameplay"] == GAMEPLAY - 1
    assert points["last"] == FRAMES - 1
    assert GAMEPLAY <= points["result panel"] < FRAMES
    assert all(0 <= index < FRAMES for index in indices)


def test_the_checkpoints_survive_a_very_short_render() -> None:
    points = qc.visual_checkpoints(4, 2)
    assert all(0 <= index < 4 for index in points.values())
    assert len(points) == 8


def test_an_empty_render_has_no_checkpoints() -> None:
    with pytest.raises(qc.QcError):
        qc.visual_checkpoints(0, 0)


# --- fast start -----------------------------------------------------------


def atom(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def test_fast_start_is_read_from_the_atom_order(tmp_path) -> None:
    fast = tmp_path / "fast.mp4"
    fast.write_bytes(
        atom(b"ftyp", b"isom") + atom(b"moov", b"x" * 32) + atom(b"mdat", b"y" * 64)
    )
    assert qc.moov_before_mdat(str(fast)) is True

    slow = tmp_path / "slow.mp4"
    slow.write_bytes(
        atom(b"ftyp", b"isom") + atom(b"mdat", b"y" * 64) + atom(b"moov", b"x" * 32)
    )
    assert qc.moov_before_mdat(str(slow)) is False


def test_a_truncated_or_odd_file_is_not_fast_start(tmp_path) -> None:
    stub = tmp_path / "stub.mp4"
    stub.write_bytes(b"\x00\x00")
    assert qc.moov_before_mdat(str(stub)) is False

    zero = tmp_path / "zero.mp4"
    zero.write_bytes(struct.pack(">I4s", 0, b"mdat"))
    assert qc.moov_before_mdat(str(zero)) is False


# --- the hard pass --------------------------------------------------------


def test_a_correct_item_has_nothing_wrong_with_it() -> None:
    problems, warnings = qc.evaluate(evidence())
    assert problems == []
    assert warnings == []


def test_a_missing_stage_fails_and_says_which() -> None:
    assert mentions(problems_of(replay=qc.ReplayFacts()), "replay is missing")
    assert mentions(problems_of(render=qc.RenderFacts()), "frame sequence is missing")
    assert mentions(problems_of(audio=qc.AudioFacts()), "soundtrack is missing")
    assert mentions(problems_of(video=qc.VideoFacts()), "short.mp4 is missing")


def test_a_replay_that_is_not_the_selected_battle_fails() -> None:
    """The replay is the creative source; if it is wrong, nothing else matters."""
    assert mentions(problems_of(replay=replay_facts(seed=999)), "replay seed")
    assert mentions(
        problems_of(replay=replay_facts(powers=("rush", "echo"))), "replay powers"
    )
    assert mentions(problems_of(replay=replay_facts(winner_id=1)), "replay winner")
    assert mentions(problems_of(replay=replay_facts(duration=9.5)), "replay runs")
    assert mentions(problems_of(replay=replay_facts(version=5)), "version 5")
    assert mentions(problems_of(replay=replay_facts(sha256="")), "never hashed")


def test_a_draw_is_still_checked_against_the_manifest() -> None:
    drawn = qc.evaluate(
        evidence(
            item=item(winner_id=None),
            replay=replay_facts(winner_id=None, is_draw=True),
        )
    )[0]
    assert drawn == []
    assert mentions(
        problems_of(item=item(winner_id=None)),
        "manifest says None",
    )


def test_the_wrong_render_geometry_fails() -> None:
    assert mentions(
        problems_of(render=render_facts(width=540, height=960)), "540x960"
    )
    assert mentions(problems_of(render=render_facts(fps=30)), "30 fps")
    assert mentions(problems_of(render=render_facts(render_version=2)), "version 2")


def test_an_incomplete_sequence_fails() -> None:
    broken = render_facts(sequence_problems=("2 missing frames, first frame_000004.png",))
    assert mentions(problems_of(render=broken), "missing frames")
    assert mentions(problems_of(render=render_facts(sequence_sha256="")), "never hashed")
    assert mentions(problems_of(render=render_facts(frame_count=0)), "0 frames")
    assert mentions(
        problems_of(render=render_facts(gameplay_frames=FRAMES + 5)), "makes no sense"
    )


def test_a_sequence_that_changed_since_it_was_checked_fails() -> None:
    """The protection against a delivered Short's frames moving underneath it."""
    moved = render_facts(
        sequence_sha256="b" * 64, recorded_sequence_sha256="e" * 64
    )
    assert mentions(problems_of(render=moved), "has changed since it was last checked")
    same = render_facts(sequence_sha256="b" * 64, recorded_sequence_sha256="b" * 64)
    assert qc.render_problems(same, replay_facts()) == []


def test_frames_rendered_from_another_replay_fail() -> None:
    assert mentions(
        problems_of(render=render_facts(replay_sha256="f" * 64)),
        "rendered from a different replay",
    )


def test_a_blank_or_black_frame_fails() -> None:
    """Reported, never repaired: production QC does not touch pixels."""
    blank = render_facts(blank_frames=("frame_000000.png (first) is completely black",))
    assert mentions(problems_of(render=blank), "completely black")


def test_audio_that_is_not_the_production_format_fails() -> None:
    assert mentions(problems_of(audio=audio_facts(sample_rate=44100)), "44100 Hz")
    assert mentions(problems_of(audio=audio_facts(channels=1)), "1 channels")
    assert mentions(problems_of(audio=audio_facts(audio_version=2)), "version 2")
    assert mentions(problems_of(audio=audio_facts(pcm_sha256="")), "never hashed")


def test_audio_of_the_wrong_length_fails() -> None:
    """The exactness Phase 6B built the whole timeline around."""
    for samples in (SAMPLES - 1, SAMPLES + 1, SAMPLES + 800, 0):
        found = problems_of(audio=audio_facts(samples=samples))
        assert mentions(found, f"expected exactly {FRAMES} x 800 = {SAMPLES}")
    assert qc.audio_problems(audio_facts(), render_facts(), replay_facts()) == []


def test_audio_built_from_another_replay_fails() -> None:
    assert mentions(
        problems_of(audio=audio_facts(replay_sha256="f" * 64)),
        "built from a different replay",
    )


def test_an_unsafe_audio_peak_fails() -> None:
    hot = audio_facts(problems=("peak 0.999999 is above the 0.851138 ceiling",))
    assert mentions(problems_of(audio=hot), "above the")


def test_a_video_that_is_not_the_production_format_fails() -> None:
    """The probe rules themselves are `rendering.encode`'s and tested there.

    What is checked here is that QC carries them through rather than dropping
    them, plus the one gate that is QC's own: fast start.
    """
    carried = video_facts(problems=("video is 540x960, expected 1080x1920",))
    assert mentions(problems_of(video=carried), "540x960")
    assert mentions(problems_of(video=video_facts(faststart=False)), "fast start is off")
    assert mentions(problems_of(video=video_facts(sha256="")), "never hashed")


# --- loudness: one gate, one warning -------------------------------------


def test_a_true_peak_over_the_limit_fails() -> None:
    """It can clip on playback and nothing downstream will fix it."""
    assert qc.TRUE_PEAK_MAX_DBFS == -1.0
    assert mentions(problems_of(loudness=loudness_facts(true_peak_dbfs=-0.8)), "true peak")
    assert mentions(problems_of(loudness=loudness_facts(true_peak_dbfs=0.0)), "true peak")
    assert problems_of(loudness=loudness_facts(true_peak_dbfs=-1.0)) == []
    assert mentions(
        problems_of(loudness=loudness_facts(true_peak_dbfs=None)), "not measured"
    )


def test_loudness_outside_the_preferred_band_only_warns() -> None:
    """Phase 6C measures audio. Remastering one Short would break the batch."""
    assert (qc.LOUDNESS_PREFERRED_MIN, qc.LOUDNESS_PREFERRED_MAX) == (-22.0, -18.0)
    for level in (-26.0, -22.1, -17.9, -12.0):
        problems, warnings = qc.evaluate(
            evidence(loudness=loudness_facts(integrated_lufs=level))
        )
        assert problems == []
        assert mentions(warnings, "outside the preferred")
    for level in (-22.0, -20.0, -18.0):
        assert qc.loudness_warnings(loudness_facts(integrated_lufs=level)) == []


def test_a_phone_band_outlier_warns_against_the_batch() -> None:
    """Phase 6B.1 closed this spread to about a decibel, so a gap is a signal."""
    facts = loudness_facts(band_lufs=-30.9)
    assert qc.loudness_warnings(facts, band_reference=-22.3) != []
    assert mentions(qc.loudness_warnings(facts, band_reference=-22.3), "phone-band")
    assert qc.loudness_warnings(loudness_facts(band_lufs=-23.0), -22.3) == []
    # With nothing to compare against, there is nothing to say.
    assert qc.loudness_warnings(loudness_facts(band_lufs=-30.9)) == []


def test_warnings_never_change_the_status() -> None:
    record = qc.qc_record(
        evidence(),
        batch_id="audit10",
        problems=[],
        warnings=["integrated loudness -26.0 LUFS is outside the preferred band"],
    )
    assert record["status"] == qc.STATUS_PASS
    assert record["warnings"]


# --- the record -----------------------------------------------------------


def test_the_record_spells_out_the_whole_chain() -> None:
    """Manifest item to replay to frames to audio to video, in one file."""
    record = qc.qc_record(evidence(), batch_id="audit10", problems=[], warnings=[])
    assert record["version"] == qc.QC_VERSION
    assert record["status"] == qc.STATUS_PASS
    assert record["source"]["batch_id"] == "audit10"
    assert record["source"]["index"] == 3
    assert record["source"]["seed"] == SEED
    assert record["replay"]["sha256"] == "a" * 64
    assert record["render"]["replay_sha256"] == record["replay"]["sha256"]
    assert record["render"]["sequence_sha256"] == "b" * 64
    assert record["audio"]["pcm_sha256"] == "c" * 64
    assert record["video"]["sha256"] == "d" * 64
    assert record["render"]["frames"] * 800 == record["audio"]["samples"]


def test_a_failing_record_carries_its_reasons() -> None:
    record = qc.qc_record(
        evidence(), batch_id="b", problems=["replay is missing"], warnings=[]
    )
    assert record["status"] == qc.STATUS_FAIL
    assert record["problems"] == ["replay is missing"]


def test_the_record_is_byte_identical_between_runs() -> None:
    dumps = [
        json.dumps(
            qc.qc_record(evidence(), batch_id="audit10", problems=[], warnings=[]),
            indent=2,
            sort_keys=True,
        )
        for _ in range(2)
    ]
    assert dumps[0] == dumps[1]


def test_the_record_holds_nothing_that_could_vary() -> None:
    record = qc.qc_record(evidence(), batch_id="audit10", problems=[], warnings=[])
    text = json.dumps(record).lower()
    for forbidden in (
        "timestamp",
        "created",
        "creation",
        "hostname",
        "machine",
        "platform",
        "uuid",
        "run_id",
        "elapsed",
        "c:\\\\",
    ):
        assert forbidden not in text
    for value in (record["source"]["layout_id"], record["render"]["sequence_method"]):
        assert not os.path.isabs(value)


# --- an item that never got far enough to be described -------------------


def test_an_item_that_failed_early_still_gets_a_record() -> None:
    """Otherwise the previous run's record stays beside the video saying pass.

    A replay that is not the battle the manifest selected stops production
    before a frame is read, so there is nothing to describe - but leaving
    the delivery folder disagreeing with itself about a Short somebody is
    about to review is worse than a sparse record.
    """
    record = qc.failure_record(item(), "audit10", ["replay is missing"])
    assert record["version"] == qc.QC_VERSION
    assert record["status"] == qc.STATUS_FAIL
    assert record["problems"] == ["replay is missing"]
    assert record["source"]["index"] == 3
    assert record["source"]["seed"] == SEED
    assert record["source"]["label"] == "TITAN vs ORBIT"
    # Nothing is claimed about stages that never ran.
    assert record["render"]["sequence_sha256"] == ""
    assert record["audio"]["pcm_sha256"] == ""
    assert record["video"]["sha256"] == ""
    assert record["video"]["faststart"] is False


def test_a_failure_record_is_deterministic_and_reviewable() -> None:
    first, second = (
        json.dumps(qc.failure_record(item(), "b", ["broken"]), sort_keys=True)
        for _ in range(2)
    )
    assert first == second
    reviewed = qc.with_review(
        qc.failure_record(item(), "b", ["broken"]), qc.REVIEW_REJECTED, "no good"
    )
    assert reviewed["status"] == qc.STATUS_FAIL
    assert reviewed["review_status"] == qc.REVIEW_REJECTED


# --- the review layer ----------------------------------------------------


def test_review_defaults_to_pending() -> None:
    """A machine never approves anything."""
    record = qc.with_review(
        qc.qc_record(evidence(), batch_id="b", problems=[], warnings=[])
    )
    assert record["review_status"] == qc.REVIEW_PENDING
    assert record["review_note"] == ""
    assert qc.review_of(None) == (qc.REVIEW_PENDING, "")
    assert qc.review_of({}) == (qc.REVIEW_PENDING, "")


def test_a_review_answer_can_be_read_back() -> None:
    record = qc.with_review(
        qc.qc_record(evidence(), batch_id="b", problems=[], warnings=[]),
        qc.REVIEW_REJECTED,
        "battle feels repetitive",
    )
    assert qc.review_of(record) == (qc.REVIEW_REJECTED, "battle feels repetitive")


def test_an_unknown_review_status_is_refused() -> None:
    base = qc.qc_record(evidence(), batch_id="b", problems=[], warnings=[])
    with pytest.raises(qc.QcError):
        qc.with_review(base, "shipped")
    # An unreadable status on disk reads as pending rather than crashing.
    assert qc.review_of({"review_status": "shipped"})[0] == qc.REVIEW_PENDING


def test_review_does_not_touch_the_automated_half() -> None:
    base = qc.qc_record(evidence(), batch_id="b", problems=[], warnings=[])
    reviewed = qc.with_review(base, qc.REVIEW_APPROVED, "good one")
    assert {key: reviewed[key] for key in base} == base
    assert set(reviewed) - set(base) == {"review_status", "review_note"}
