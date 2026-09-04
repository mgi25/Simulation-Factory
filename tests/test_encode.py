"""Phase 6B tests: the final encode, and what it is not allowed to be.

FFmpeg does the encoding, so what is testable here is every decision around
it: which executable is chosen, exactly what arguments it is handed, what the
sequence going in has to look like, what the file coming out has to report,
and that nothing is ever deleted before all of that has passed. None of it
needs an encoder installed.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import struct
import zlib

import pytest

from audio import soundtrack, wav_io
from rendering import encode, png_frames
from rendering.render_plan import METADATA_NAME, frame_filename
from replay.exporter import REPLAY_VERSION

FRAME_COUNT = 616
DURATION = FRAME_COUNT / 60


def option(command: list[str], flag: str) -> str | None:
    """The value that follows `flag`, or None if the flag is not there."""
    return command[command.index(flag) + 1] if flag in command else None


def options(command: list[str], flag: str) -> list[str]:
    """Every value that follows each occurrence of `flag`."""
    return [
        command[index + 1] for index, item in enumerate(command) if item == flag
    ]


def make_command(**kwargs) -> list[str]:
    settings = {
        "frames": "output/render_seed_33/frames/frame_%06d.png",
        "audio": "output/render_seed_33/audio.wav",
        "output": "output/render_seed_33/short.mp4",
        "frame_count": FRAME_COUNT,
    }
    settings.update(kwargs)
    return encode.encode_command("ffmpeg", **settings)


# What ffprobe actually reports for a correctly encoded Short. Copied from a
# real run rather than invented, so the parser is tested against the shape it
# will really be given.
GOOD_PROBE = {
    "streams": [
        {
            "codec_name": "h264",
            "codec_type": "video",
            "profile": "High",
            "width": 1080,
            "height": 1920,
            "pix_fmt": "yuv420p",
            "r_frame_rate": "60/1",
            "avg_frame_rate": "60/1",
            "field_order": "progressive",
            "nb_frames": str(FRAME_COUNT),
            "nb_read_packets": str(FRAME_COUNT),
            "duration": f"{DURATION:.6f}",
            "time_base": "1/60000",
        },
        {
            "codec_name": "aac",
            "codec_type": "audio",
            "profile": "LC",
            "sample_rate": "48000",
            "channels": 2,
            "duration": "10.266000",
            "duration_ts": 492768,
            "nb_frames": "483",
        },
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": f"{DURATION:.6f}",
        "size": "4309606",
        "nb_streams": 2,
    },
}


def probe_of(**changes) -> encode.Probe:
    """The good probe with individual stream fields overridden."""
    payload = copy.deepcopy(GOOD_PROBE)
    for key, value in changes.items():
        kind, _, field = key.partition("__")
        index = 0 if kind == "video" else 1
        if kind == "format":
            payload["format"][field] = value
        elif value is None:
            payload["streams"][index].pop(field, None)
        else:
            payload["streams"][index][field] = value
    return encode.parse_probe(payload)


def problems(**changes) -> list[str]:
    return encode.probe_problems(probe_of(**changes), frame_count=FRAME_COUNT)


# --- the production format ------------------------------------------------


def test_the_spec_is_the_format_the_phase_asked_for() -> None:
    spec = encode.DEFAULT_SPEC
    assert (spec.width, spec.height) == (1080, 1920)
    assert spec.fps == 60
    assert spec.pix_fmt == "yuv420p"
    assert spec.profile == "high"
    assert spec.crf == 18
    assert spec.sample_rate == 48000
    assert spec.channels == 2
    assert spec.audio_bitrate == "192k"
    assert spec.faststart is True
    # A closed GOP every half second at 60 fps, with two B-frames.
    assert spec.gop == 30
    assert spec.bframes == 2
    assert spec.frame_seconds == pytest.approx(1 / 60)


def test_the_audio_format_matches_the_soundtrack_that_feeds_it() -> None:
    """One disagreement here would be a Short whose sound was resampled."""
    assert encode.DEFAULT_SPEC.sample_rate == soundtrack.SAMPLE_RATE
    assert encode.DEFAULT_SPEC.channels == soundtrack.CHANNELS
    assert encode.DEFAULT_SPEC.fps == soundtrack.VIDEO_FPS


def test_the_short_has_one_filename() -> None:
    assert encode.output_path("output/render_seed_33") == os.path.join(
        "output/render_seed_33", "short.mp4"
    )
    assert encode.SHORT_NAME == "short.mp4"
    assert encode.output_path("a") != encode.output_path("b")


def test_frames_are_addressed_by_the_pattern_the_renderer_writes() -> None:
    pattern = encode.frames_pattern("output/render_seed_33/frames")
    assert pattern.endswith("frame_%06d.png")
    assert frame_filename(0) == "frame_000000.png"


# --- the command ----------------------------------------------------------


def test_the_frame_rate_is_stated_on_both_sides_of_the_encode() -> None:
    """The image sequence carries no timing, so nothing is left to infer."""
    command = make_command()
    assert option(command, "-framerate") == "60"
    assert option(command, "-r") == "60"
    assert option(command, "-fps_mode") == "cfr"
    assert command.index("-framerate") < command.index("-i")


def test_the_frame_count_is_pinned_to_the_plan() -> None:
    command = make_command(frame_count=1427)
    assert option(command, "-frames:v") == "1427"
    assert option(command, "-start_number") == "0"


def test_the_video_settings_are_the_production_ones() -> None:
    command = make_command()
    assert option(command, "-c:v") == "libx264"
    assert option(command, "-crf") == "18"
    assert option(command, "-preset") == "slow"
    assert option(command, "-profile:v") == "high"
    assert option(command, "-pix_fmt") == "yuv420p"
    assert option(command, "-g") == "30"
    assert option(command, "-keyint_min") == "30"
    assert option(command, "-bf") == "2"
    # Closed GOP with a fixed interval: without these x264 would move a
    # keyframe to a scene change and the interval would only be a maximum.
    assert "scenecut=0" in option(command, "-x264-params")
    assert "open-gop=0" in option(command, "-x264-params")


def test_the_audio_settings_are_the_production_ones() -> None:
    command = make_command()
    assert option(command, "-c:a") == "aac"
    assert option(command, "-profile:a") == "aac_low"
    assert option(command, "-b:a") == "192k"
    assert option(command, "-ar") == "48000"
    assert option(command, "-ac") == "2"


def test_both_inputs_are_mapped_and_nothing_else_is() -> None:
    command = make_command()
    assert options(command, "-i") == [
        "output/render_seed_33/frames/frame_%06d.png",
        "output/render_seed_33/audio.wav",
    ]
    assert options(command, "-map") == ["0:v:0", "1:a:0"]
    assert command[-1] == "output/render_seed_33/short.mp4"


def test_the_file_carries_no_clock_no_machine_and_no_encoder_version() -> None:
    command = make_command()
    assert option(command, "-map_metadata") == "-1"
    assert option(command, "-map_chapters") == "-1"
    assert "-bitexact" in command


def test_fast_start_is_asked_for() -> None:
    assert option(make_command(), "-movflags") == "+faststart"
    plain = encode.EncodeSpec(faststart=False)
    assert "-movflags" not in make_command(spec=plain)


def test_the_soundtrack_length_is_never_hidden_by_trimming() -> None:
    """`-shortest` would turn a wrong soundtrack length into a silent bug."""
    command = make_command()
    assert "-shortest" not in command
    assert "-t" not in command
    assert "-vf" not in command and "-s" not in command


def test_nothing_in_the_command_rescales_or_crops() -> None:
    command = make_command()
    for forbidden in ("-vf", "-filter:v", "-s", "-aspect", "-crop"):
        assert forbidden not in command


def test_the_command_never_waits_for_input() -> None:
    command = make_command()
    assert "-nostdin" in command
    assert "-y" in command


def test_a_different_quality_setting_reaches_the_command() -> None:
    command = make_command(spec=encode.EncodeSpec(crf=14, preset="veryslow"))
    assert option(command, "-crf") == "14"
    assert option(command, "-preset") == "veryslow"


def test_the_probe_asks_for_streams_format_and_a_packet_count() -> None:
    command = encode.probe_command("ffprobe", "short.mp4")
    assert "-show_streams" in command and "-show_format" in command
    assert "-count_packets" in command
    assert option(command, "-print_format") == "json"
    assert command[-1] == "short.mp4"


def test_the_audio_of_a_finished_short_can_be_decoded_back_out() -> None:
    command = encode.decode_audio_command("ffmpeg", "short.mp4")
    assert option(command, "-f") == "s16le"
    assert option(command, "-map") == "0:a:0"
    assert option(command, "-ar") == "48000"
    assert command[-1] == "-"


def test_one_frame_can_be_decoded_by_number() -> None:
    command = encode.extract_frame_command("ffmpeg", "short.mp4", 507, "out.png")
    assert "select=eq(n\\,507)" in command
    assert option(command, "-frames:v") == "1"
    assert command[-1] == "out.png"


# --- reading the result ---------------------------------------------------


def test_the_probe_parser_reads_what_ffprobe_reports() -> None:
    probe = encode.parse_probe(json.dumps(GOOD_PROBE))
    assert "mp4" in probe.format_name
    assert probe.duration == pytest.approx(DURATION)
    assert probe.size == 4309606

    assert probe.video.codec == "h264"
    assert probe.video.profile == "High"
    assert (probe.video.width, probe.video.height) == (1080, 1920)
    assert probe.video.pix_fmt == "yuv420p"
    assert probe.video.frame_rate == probe.video.avg_frame_rate == "60/1"
    assert probe.video.field_order == "progressive"
    assert probe.video.frames == FRAME_COUNT

    assert probe.audio.codec == "aac"
    assert probe.audio.profile == "LC"
    assert probe.audio.sample_rate == 48000
    assert probe.audio.channels == 2
    assert probe.audio.samples == 492768


def test_a_packet_count_stands_in_when_a_frame_count_is_missing() -> None:
    probe = probe_of(video__nb_frames=None)
    assert probe.video.frames == FRAME_COUNT


def test_a_correct_short_has_nothing_wrong_with_it() -> None:
    assert problems() == []


def test_a_missing_stream_is_a_failure() -> None:
    payload = {"streams": [GOOD_PROBE["streams"][0]], "format": GOOD_PROBE["format"]}
    assert any("no audio" in line for line in encode.probe_problems(
        encode.parse_probe(payload), frame_count=FRAME_COUNT
    ))
    payload = {"streams": [GOOD_PROBE["streams"][1]], "format": GOOD_PROBE["format"]}
    assert any("no video" in line for line in encode.probe_problems(
        encode.parse_probe(payload), frame_count=FRAME_COUNT
    ))


def test_the_wrong_resolution_fails() -> None:
    """Including the 540x960 the project deliberately stopped rendering at."""
    for width, height in ((540, 960), (1920, 1080), (1080, 1921)):
        found = problems(video__width=width, video__height=height)
        assert any("expected 1080x1920" in line for line in found)


def test_the_wrong_frame_rate_fails() -> None:
    for rate in ("30/1", "60000/1001", "59/1"):
        found = problems(video__r_frame_rate=rate, video__avg_frame_rate=rate)
        assert any("frame rate" in line for line in found)
    # Variable frame rate: nominally 60 but not actually delivering it.
    assert any(
        "frame rate" in line for line in problems(video__avg_frame_rate="5993/100")
    )


def test_the_wrong_audio_sample_rate_fails() -> None:
    for rate in ("44100", "32000", "96000"):
        found = problems(audio__sample_rate=rate)
        assert any("expected 48000 Hz" in line for line in found)


def test_the_wrong_codec_profile_or_pixel_format_fails() -> None:
    assert any("video codec" in line for line in problems(video__codec_name="hevc"))
    assert any("video profile" in line for line in problems(video__profile="Main"))
    assert any("pixel format" in line for line in problems(video__pix_fmt="yuv444p"))
    assert any("audio codec" in line for line in problems(audio__codec_name="mp3"))
    assert any("audio profile" in line for line in problems(audio__profile="HE-AAC"))
    assert any("channels" in line for line in problems(audio__channels=1))
    assert any(
        "expected MP4" in line for line in problems(format__format_name="matroska,webm")
    )


def test_an_interlaced_short_fails() -> None:
    assert any("progressive" in line for line in problems(video__field_order="tt"))
    # Not every build reports the field order; absent is not interlaced.
    assert problems(video__field_order=None) == []


def test_a_short_with_the_wrong_number_of_frames_fails() -> None:
    found = problems(video__nb_frames="615", video__nb_read_packets="615")
    assert any(f"expected {FRAME_COUNT}" in line for line in found)


def test_a_short_of_the_wrong_length_fails() -> None:
    assert any("video runs" in line for line in problems(video__duration="9.500000"))
    assert any("audio runs" in line for line in problems(audio__duration="12.000000"))


def test_audio_and_video_more_than_a_frame_apart_fails() -> None:
    """The AAC frame granularity a correct encode does leave is not a failure."""
    assert problems() == []
    drifted = problems(audio__duration=f"{DURATION + 0.5 / 60:.6f}")
    assert drifted == []
    broken = problems(
        video__duration=f"{DURATION:.6f}", audio__duration=f"{DURATION + 0.9:.6f}"
    )
    assert any("differ by" in line for line in broken)


def test_the_duration_can_be_checked_against_the_plan_instead() -> None:
    probe = probe_of()
    assert encode.probe_problems(probe, frame_count=FRAME_COUNT, duration=DURATION) == []
    found = encode.probe_problems(
        probe, frame_count=FRAME_COUNT, duration=DURATION + 1.0
    )
    assert any("video runs" in line for line in found)


# --- the decoded soundtrack ----------------------------------------------


def test_aac_padding_is_accepted_and_a_short_soundtrack_is_not() -> None:
    expected = FRAME_COUNT * 800
    assert encode.AAC_FRAME_SAMPLES == 1024
    assert encode.decoded_audio_problems(expected, expected) == []
    assert encode.decoded_audio_problems(expected + 768, expected) == []
    assert encode.decoded_audio_problems(expected + 1023, expected) == []

    too_long = encode.decoded_audio_problems(expected + 1024, expected)
    assert any("longer than the master" in line for line in too_long)
    truncated = encode.decoded_audio_problems(expected - 1, expected)
    assert any("short of the" in line for line in truncated)


# --- the sequence going in ------------------------------------------------


def write_png(path: str, width: int, height: int, fill: bytes = b"\x20\x30\x40") -> str:
    """A minimal, valid, non-interlaced 8-bit RGB PNG."""
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


def make_frames(directory, count: int, width: int = 1080, height: int = 1920) -> str:
    """A frames directory holding `count` frames of the given size.

    The pictures are one flat colour, because nothing in this file looks at
    the pixels - the encode is validated by what the container reports, and
    the sequence is validated by its headers.
    """
    frames_dir = os.path.join(str(directory), "frames")
    os.makedirs(frames_dir, exist_ok=True)
    for index in range(count):
        write_png(os.path.join(frames_dir, frame_filename(index)), width, height)
    return frames_dir


def test_a_complete_sequence_at_the_right_size_passes(tmp_path) -> None:
    frames_dir = make_frames(tmp_path, 3)
    assert encode.source_frame_problems(frames_dir, 3) == []


def test_an_incomplete_sequence_is_caught_before_ffmpeg_is_called(tmp_path) -> None:
    """A gap does not fail an encode, it silently shortens it."""
    frames_dir = make_frames(tmp_path, 3)
    os.remove(os.path.join(frames_dir, frame_filename(1)))
    found = encode.source_frame_problems(frames_dir, 3)
    assert any("missing frames" in line for line in found)

    assert any(
        "missing frames" in line for line in encode.source_frame_problems(frames_dir, 10)
    )


def test_a_frame_past_the_end_of_the_plan_is_caught(tmp_path) -> None:
    frames_dir = make_frames(tmp_path, 4)
    found = encode.source_frame_problems(frames_dir, 3)
    assert any("past the end" in line for line in found)


def test_a_stray_file_in_the_frames_directory_is_caught(tmp_path) -> None:
    frames_dir = make_frames(tmp_path, 2)
    open(os.path.join(frames_dir, "frame_2.png"), "wb").close()
    found = encode.source_frame_problems(frames_dir, 2)
    assert any("unrecognised" in line for line in found)


def test_a_wrongly_sized_frame_is_caught(tmp_path) -> None:
    frames_dir = make_frames(tmp_path, 2, width=540, height=960)
    found = encode.source_frame_problems(frames_dir, 2)
    assert any("540x960" in line and "1080x1920" in line for line in found)


def test_a_frame_that_is_not_a_png_is_caught(tmp_path) -> None:
    frames_dir = make_frames(tmp_path, 2)
    with open(os.path.join(frames_dir, frame_filename(1)), "wb") as handle:
        handle.write(b"not a png")
    assert encode.source_frame_problems(frames_dir, 2) != []


def test_a_missing_frames_directory_is_caught(tmp_path) -> None:
    found = encode.source_frame_problems(str(tmp_path / "nothing"), 3)
    assert any("no frames directory" in line for line in found)


# --- finding the tools ----------------------------------------------------


def test_an_explicit_path_that_is_not_an_executable_is_refused(tmp_path) -> None:
    with pytest.raises(encode.EncodeError):
        encode.find_ffmpeg(str(tmp_path / "no-such-ffmpeg"))
    with pytest.raises(encode.EncodeError):
        encode.find_ffprobe(str(tmp_path / "no-such-ffprobe"))


def test_an_explicit_path_wins(tmp_path, monkeypatch) -> None:
    fake = tmp_path / "my-ffmpeg"
    fake.write_bytes(b"")
    monkeypatch.setenv("FFMPEG_BIN", str(tmp_path / "other"))
    assert encode.find_ffmpeg(str(fake)) == str(fake)


def test_the_environment_variable_is_used_before_the_path(tmp_path, monkeypatch) -> None:
    fake = tmp_path / "env-ffmpeg"
    fake.write_bytes(b"")
    monkeypatch.setenv("FFMPEG_BIN", str(fake))
    monkeypatch.setattr(shutil, "which", lambda name: "/somewhere/else/ffmpeg")
    assert encode.find_ffmpeg() == str(fake)


def test_the_path_is_used_when_nothing_else_names_one(monkeypatch) -> None:
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    assert encode.find_ffmpeg() == "/usr/bin/ffmpeg"


def test_a_missing_ffmpeg_says_exactly_what_was_looked_for(monkeypatch) -> None:
    """No download, no guess: it stops and says what is missing."""
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(encode, "_imageio_ffmpeg", lambda: None)
    with pytest.raises(encode.EncodeError) as error:
        encode.find_ffmpeg()
    message = str(error.value)
    assert "--ffmpeg" in message and "FFMPEG_BIN" in message and "PATH" in message
    assert "download" in message


def test_an_existing_imageio_ffmpeg_is_the_last_resort(tmp_path, monkeypatch) -> None:
    bundled = tmp_path / "bundled-ffmpeg"
    bundled.write_bytes(b"")
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    monkeypatch.setattr(encode, "_imageio_ffmpeg", lambda: str(bundled))
    assert encode.find_ffmpeg() == str(bundled)


def test_ffprobe_is_looked_for_beside_the_ffmpeg_in_use(tmp_path, monkeypatch) -> None:
    (tmp_path / "ffmpeg").write_bytes(b"")
    (tmp_path / "ffprobe").write_bytes(b"")
    monkeypatch.delenv("FFPROBE_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: "/elsewhere/ffprobe")
    found = encode.find_ffprobe(None, str(tmp_path / "ffmpeg"))
    assert found == str(tmp_path / "ffprobe")


def test_a_missing_ffprobe_stops_the_encode(monkeypatch) -> None:
    monkeypatch.delenv("FFPROBE_BIN", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(encode.EncodeError) as error:
        encode.find_ffprobe()
    assert "validated" in str(error.value)


def test_no_machine_specific_path_is_committed() -> None:
    """The discovery order is names and variables, never a real location."""
    for value in encode.FFMPEG_ON_PATH + encode.FFPROBE_ON_PATH:
        assert os.sep not in value and "/" not in value
    assert encode.FFMPEG_ENV_VARS == ("FFMPEG_BIN",)


# --- loudness reporting ---------------------------------------------------


def test_the_loudness_report_is_read_from_ffmpegs_summary() -> None:
    text = """[Parsed_ebur128_0 @ 0000] Summary:

  Integrated loudness:
    I:         -24.9 LUFS
    Threshold: -35.1 LUFS

  Loudness range:
    LRA:        10.4 LU
    Threshold: -45.4 LUFS
    LRA low:   -31.5 LUFS
    LRA high:  -21.1 LUFS

  True peak:
    Peak:       -1.1 dBFS
"""
    level = encode.parse_loudness(text)
    assert level.integrated_lufs == -24.9
    assert level.range_lu == 10.4
    assert level.true_peak_dbfs == -1.1


def test_a_loudness_report_that_is_not_there_is_not_an_error() -> None:
    level = encode.parse_loudness("ffmpeg said nothing useful")
    assert level == encode.Loudness(None, None, None)


# --- cleanup --------------------------------------------------------------


def make_render(tmp_path, frames: int = 3, width: int = 1080, height: int = 1920):
    """A render directory and the replay it claims to have come from."""
    from tools import encode_short

    render_dir = tmp_path / "render_seed_1"
    render_dir.mkdir()
    make_frames(render_dir, frames, width, height)

    replay_path = render_dir / "replay.json"
    replay = {
        "version": REPLAY_VERSION,
        "seed": 1,
        "fps": 60,
        "physics_hz": 120,
        "canvas": {"width": 1080, "height": 1920},
        "arena": {"left": 60, "top": 380, "right": 1020, "bottom": 1540},
        "frames": [{"tick": index * 2} for index in range(frames)],
        "events": [],
        "result": {"winner_id": 0, "is_draw": False, "finished_tick": 0},
    }
    replay_path.write_text(json.dumps(replay), encoding="utf-8")

    metadata = {
        "render_version": 1,
        "replay": {
            "name": "replay.json",
            "path": "replay.json",
            "version": REPLAY_VERSION,
            "seed": 1,
            "sha256": png_frames.file_digest(str(replay_path)),
        },
        "video": {"width": width, "height": height, "fps": 60, "frame_count": frames},
        "timeline": {"gameplay_frames": frames, "post_roll_frames": 0},
    }
    (render_dir / METADATA_NAME).write_text(json.dumps(metadata), encoding="utf-8")
    return encode_short, str(render_dir), str(replay_path)


def cleanup_args(**overrides) -> argparse.Namespace:
    settings = {
        "crf": 18,
        "preset": "slow",
        "bit_depth": 24,
        "audio_only": False,
        "skip_audio": False,
        "loudness": False,
        "compare_frames": False,
        "repeat_encode": False,
        "cleanup_frames": True,
        "cleanup_audio": True,
        "keep_going": False,
    }
    settings.update(overrides)
    return argparse.Namespace(**settings)


def frames_present(render_dir: str, count: int) -> int:
    frames_dir = os.path.join(render_dir, "frames")
    return sum(
        os.path.isfile(os.path.join(frames_dir, frame_filename(index)))
        for index in range(count)
    )


def test_cleanup_removes_only_what_it_was_asked_to(tmp_path) -> None:
    tool, render_dir, _ = make_render(tmp_path, frames=3)
    audio = os.path.join(render_dir, tool.AUDIO_NAME)
    with open(audio, "wb") as handle:
        handle.write(b"\x00" * 64)

    assert tool.cleanup(render_dir, 3, frames=False, audio=False) == []
    assert frames_present(render_dir, 3) == 3
    assert os.path.isfile(audio)

    removed = tool.cleanup(render_dir, 3, frames=True, audio=True)
    assert len(removed) == 2
    assert frames_present(render_dir, 3) == 0
    assert not os.path.isfile(audio)


def test_frames_and_audio_are_kept_unless_asked_for(monkeypatch) -> None:
    """Both cleanups are opt-in. Rendering is expensive; deleting is cheap."""
    from tools import encode_short

    monkeypatch.setattr("sys.argv", ["encode_short.py", "output/render_seed_33"])
    args = encode_short.parse_args()
    assert args.cleanup_frames is False
    assert args.cleanup_audio is False
    assert args.loudness is True
    assert args.crf == encode.DEFAULT_SPEC.crf
    assert args.bit_depth == wav_io.DEFAULT_BIT_DEPTH

    monkeypatch.setattr(
        "sys.argv", ["encode_short.py", "r", "--cleanup-frames", "--cleanup-audio"]
    )
    opted_in = encode_short.parse_args()
    assert opted_in.cleanup_frames is True and opted_in.cleanup_audio is True


def test_a_failed_encode_leaves_its_source_frames_alone(tmp_path) -> None:
    """An hour of rendering is not thrown away because the encode broke.

    Cleanup is the last thing a successful job does. This one fails at the
    first validation - a frame is missing - with both cleanup flags on, and
    every frame that is there has to still be there afterwards.
    """
    tool, render_dir, replay_path = make_render(tmp_path, frames=4)
    os.remove(os.path.join(render_dir, "frames", frame_filename(2)))

    with pytest.raises(tool.ShortError):
        tool.encode_short(render_dir, cleanup_args(), "ffmpeg", "ffprobe")

    assert frames_present(render_dir, 4) == 3
    assert os.path.isfile(replay_path)
    assert not os.path.isfile(encode.output_path(render_dir))


def test_a_render_at_the_wrong_resolution_never_reaches_ffmpeg(tmp_path) -> None:
    tool, render_dir, _ = make_render(tmp_path, frames=2, width=540, height=960)
    with pytest.raises(tool.ShortError) as error:
        tool.encode_short(render_dir, cleanup_args(), "ffmpeg", "ffprobe")
    assert "never rescales" in str(error.value)
    assert frames_present(render_dir, 2) == 2


def test_an_edited_replay_stops_the_encode(tmp_path) -> None:
    """The audio comes from the replay; a changed one would not match."""
    tool, render_dir, replay_path = make_render(tmp_path, frames=3)
    with open(replay_path, "r+", encoding="utf-8") as handle:
        data = json.load(handle)
        data["seed"] = 999
        handle.seek(0)
        handle.truncate()
        json.dump(data, handle)

    with pytest.raises(tool.ShortError) as error:
        tool.encode_short(render_dir, cleanup_args(), "ffmpeg", "ffprobe")
    assert "changed since it was rendered" in str(error.value)
    assert frames_present(render_dir, 3) == 3


def test_a_directory_that_is_not_a_render_is_refused(tmp_path) -> None:
    from tools import encode_short

    with pytest.raises(encode_short.ShortError) as error:
        encode_short.load_render(str(tmp_path))
    assert METADATA_NAME in str(error.value)


def test_a_batch_finds_every_render_under_a_root(tmp_path) -> None:
    from tools import encode_short

    for name in ("002_seed_2", "001_seed_1", "not_a_render"):
        (tmp_path / name).mkdir()
    for name in ("001_seed_1", "002_seed_2"):
        (tmp_path / name / METADATA_NAME).write_text("{}", encoding="utf-8")

    jobs = encode_short.batch_jobs(str(tmp_path), None)
    assert [os.path.basename(job) for job in jobs] == ["001_seed_1", "002_seed_2"]
    assert encode_short.batch_jobs(str(tmp_path), 1) == jobs[:1]


def test_a_single_render_directory_is_its_own_batch(tmp_path) -> None:
    from tools import encode_short

    (tmp_path / METADATA_NAME).write_text("{}", encoding="utf-8")
    assert encode_short.batch_jobs(str(tmp_path), None) == [str(tmp_path)]


def test_the_audio_written_beside_a_render_has_the_expected_names() -> None:
    from tools import encode_short

    assert encode_short.AUDIO_NAME == "audio.wav"
    assert encode_short.AUDIO_METADATA_NAME == "audio_metadata.json"
    assert wav_io.DEFAULT_BIT_DEPTH in wav_io.BIT_DEPTHS
