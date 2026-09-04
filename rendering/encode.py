"""Turning a frame sequence plus a PCM master into a finished Short.

Everything here is a pure function of the plan: which executable to call,
what arguments it gets, and what the result has to report back before it is
allowed to be called finished. The subprocess calls themselves live in
`tools/encode_short.py`, so the decisions are testable without an encoder
installed.

H.264 and AAC are FFmpeg's job. Writing our own encoder would be months of
work to arrive somewhere worse, and the container format is the one thing in
this pipeline that genuinely has to match what the rest of the world expects.

Finding FFmpeg, in order: `--ffmpeg`, then `$FFMPEG_BIN`, then the PATH, then
an `imageio_ffmpeg` install if one already happens to be present. Nothing is
downloaded and no machine-specific path is committed anywhere in the project;
when there is no usable executable the encode fails and says exactly what was
looked for.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any

from rendering import png_frames
from rendering.render_plan import frame_filename, sequence_problems

# Production output format. These are the numbers a finished Short is
# validated against, and they are the same numbers the render plan and the
# soundtrack are built from.
VIDEO_CODEC = "h264"
VIDEO_ENCODER = "libx264"
VIDEO_PROFILE = "High"
PIXEL_FORMAT = "yuv420p"
AUDIO_CODEC = "aac"
AUDIO_PROFILE = "LC"
AUDIO_ENCODER_PROFILE = "aac_low"
CONTAINER_HINT = "mp4"
SHORT_NAME = "short.mp4"

# One AAC-LC frame. The encoder works in whole frames, so a master whose
# length is not a multiple of 1024 comes back padded to the next one - up to
# 21 ms of silence that the container's own duration accounts for. It is the
# reason the decoded stream may be slightly longer than the master and the
# reason that is not a synchronisation error.
AAC_FRAME_SAMPLES = 1024

FFMPEG_ENV_VARS = ("FFMPEG_BIN",)
FFPROBE_ENV_VARS = ("FFPROBE_BIN",)
FFMPEG_ON_PATH = ("ffmpeg",)
FFPROBE_ON_PATH = ("ffprobe",)


class EncodeError(RuntimeError):
    """The Short could not be produced, or is not what production requires."""


@dataclass(frozen=True)
class EncodeSpec:
    """Every encoder decision, in one place.

    Quality first: CRF 18 with the `slow` preset is visually transparent on
    this material at 1080x1920 and lands a twenty-second Short around eight
    megabytes. File size is not being optimised in this phase.
    """

    width: int = 1080
    height: int = 1920
    fps: int = 60
    crf: int = 18
    preset: str = "slow"
    profile: str = "high"
    pix_fmt: str = PIXEL_FORMAT
    # Closed GOP every half second at 60 fps, with scene-cut insertion off so
    # the interval is actually fixed rather than "at most". Two B-frames is
    # what High profile is for.
    gop: int = 30
    bframes: int = 2
    audio_bitrate: str = "192k"
    sample_rate: int = 48000
    channels: int = 2
    faststart: bool = True

    @property
    def frame_seconds(self) -> float:
        return 1.0 / self.fps


DEFAULT_SPEC = EncodeSpec()


# --- locating the tools -----------------------------------------------------


def _resolve(
    explicit: str | None, env_vars: tuple[str, ...], names: tuple[str, ...]
) -> str | None:
    if explicit:
        if os.path.isfile(explicit):
            return explicit
        return shutil.which(explicit)

    for variable in env_vars:
        value = os.environ.get(variable)
        if value and os.path.isfile(value):
            return value
        if value:
            found = shutil.which(value)
            if found:
                return found

    for name in names:
        found = shutil.which(name)
        if found:
            return found
    return None


def find_ffmpeg(explicit: str | None = None) -> str:
    """The FFmpeg executable to use, or a failure that says what is missing."""
    found = _resolve(explicit, FFMPEG_ENV_VARS, FFMPEG_ON_PATH)
    if found:
        return found
    if explicit:
        raise EncodeError(f"--ffmpeg does not name an executable: {explicit}")

    bundled = _imageio_ffmpeg()
    if bundled:
        return bundled
    raise EncodeError(
        "cannot find FFmpeg. Pass --ffmpeg PATH, set $FFMPEG_BIN, or put"
        " ffmpeg on PATH. Nothing is downloaded automatically."
    )


def find_ffprobe(explicit: str | None = None, ffmpeg: str | None = None) -> str:
    """The ffprobe beside the FFmpeg being used, or one from the environment.

    Looked for next to `ffmpeg` first: a machine with two FFmpeg builds
    installed should validate with the probe that belongs to the encoder that
    wrote the file, not whichever one the PATH happens to reach first.
    """
    if explicit:
        found = _resolve(explicit, (), ())
        if found:
            return found
        raise EncodeError(f"--ffprobe does not name an executable: {explicit}")

    if ffmpeg:
        directory = os.path.dirname(os.path.abspath(ffmpeg))
        for name in ("ffprobe.exe", "ffprobe"):
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate):
                return candidate

    found = _resolve(None, FFPROBE_ENV_VARS, FFPROBE_ON_PATH)
    if found:
        return found
    raise EncodeError(
        "cannot find ffprobe, so a finished Short could not be validated."
        " Pass --ffprobe PATH, set $FFPROBE_BIN, or put ffprobe on PATH."
    )


def _imageio_ffmpeg() -> str | None:
    """An already-installed imageio_ffmpeg, if there is one. Never installs."""
    try:
        import imageio_ffmpeg  # noqa: PLC0415 - optional, probed not required
    except ImportError:
        return None
    try:
        path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - depends on the install
        return None
    return path if path and os.path.isfile(path) else None


# --- the commands -----------------------------------------------------------


def frames_pattern(frames_dir: str, pattern: str = "frame_%06d.png") -> str:
    return os.path.join(frames_dir, pattern)


def output_path(render_dir: str, name: str = SHORT_NAME) -> str:
    """Where a render directory's finished Short goes. One name, always."""
    return os.path.join(render_dir, name)


def encode_command(
    ffmpeg: str,
    *,
    frames: str,
    audio: str,
    output: str,
    frame_count: int,
    spec: EncodeSpec = DEFAULT_SPEC,
    start_number: int = 0,
) -> list[str]:
    """The whole encode, as one argument list.

    Points worth knowing, because each one is a thing FFmpeg would otherwise
    decide for itself:

    * `-framerate` on the input and `-r` with `-fps_mode cfr` on the output.
      The image sequence carries no timing of its own, so the rate is stated
      on both sides rather than inferred once and hoped about.
    * `-frames:v` pins the count to what the render plan says, so a stray
      file in the frames directory cannot lengthen the video.
    * `-map_metadata -1 -map_chapters -1` and `-bitexact` between them leave
      no creation time, no machine name and no encoder version in the file.
      `-bitexact` also stops x264 writing its settings into the bitstream,
      which is what makes two encodes of the same inputs comparable.
    * no `-shortest`. The soundtrack is generated at exactly the right
      length; trimming to the shorter stream would hide a wrong one.
    """
    command = [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-loglevel",
        "error",
        "-stats",
        "-framerate",
        str(spec.fps),
        "-start_number",
        str(start_number),
        "-i",
        frames,
        "-i",
        audio,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-map_metadata",
        "-1",
        "-map_chapters",
        "-1",
        "-frames:v",
        str(frame_count),
        "-c:v",
        VIDEO_ENCODER,
        "-preset",
        spec.preset,
        "-crf",
        str(spec.crf),
        "-profile:v",
        spec.profile,
        "-pix_fmt",
        spec.pix_fmt,
        "-g",
        str(spec.gop),
        "-keyint_min",
        str(spec.gop),
        "-bf",
        str(spec.bframes),
        "-x264-params",
        "scenecut=0:open-gop=0",
        "-colorspace",
        "bt709",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-fps_mode",
        "cfr",
        "-r",
        str(spec.fps),
        "-video_track_timescale",
        str(spec.fps * 1000),
        "-c:a",
        AUDIO_CODEC,
        "-profile:a",
        AUDIO_ENCODER_PROFILE,
        "-b:a",
        spec.audio_bitrate,
        "-ar",
        str(spec.sample_rate),
        "-ac",
        str(spec.channels),
        "-bitexact",
    ]
    if spec.faststart:
        command += ["-movflags", "+faststart"]
    command.append(output)
    return command


def source_frame_problems(
    frames_dir: str, frame_count: int, spec: EncodeSpec = DEFAULT_SPEC
) -> list[str]:
    """Everything wrong with the sequence about to be encoded.

    Run before FFmpeg is called at all. An incomplete render must never
    become a video: a missing frame in the middle of an image sequence does
    not fail an encode, it silently shortens it, and the result would look
    fine right up until the moment it was watched.

    Headers only. Every frame is checked - which is the point, since one
    wrong size anywhere is a wrong Short - and reading 33 bytes per file
    makes checking all of them affordable.
    """
    if not os.path.isdir(frames_dir):
        return [f"no frames directory at {frames_dir}"]

    problems = sequence_problems(os.listdir(frames_dir), frame_count)
    if problems:
        return problems

    for index in range(frame_count):
        path = os.path.join(frames_dir, frame_filename(index))
        try:
            header = png_frames.read_header(path)
        except png_frames.PngError as error:
            return [str(error)]
        if (header.width, header.height) != (spec.width, spec.height):
            return [
                f"{frame_filename(index)} is {header.width}x{header.height},"
                f" expected {spec.width}x{spec.height}"
            ]
    return []


def probe_command(ffprobe: str, path: str) -> list[str]:
    """Everything validation needs, in one call.

    Packets are counted rather than frames decoded: for H.264 in MP4 one
    packet is one frame, and counting them does not spend a minute decoding
    two thousand pictures to learn a number the container already knows.
    """
    return [
        ffprobe,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        "-count_packets",
        path,
    ]


def decode_audio_command(ffmpeg: str, path: str, sample_rate: int = 48000) -> list[str]:
    """Decode a finished Short's audio to raw PCM on stdout.

    Used to compare two encodes: MP4 container bytes can differ between
    FFmpeg builds, but what a player actually hears cannot.
    """
    return [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-i",
        path,
        "-map",
        "0:a:0",
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-",
    ]


def extract_frame_command(ffmpeg: str, path: str, index: int, output: str) -> list[str]:
    """Decode one frame of a finished Short to a PNG, by frame number."""
    return [
        ffmpeg,
        "-v",
        "error",
        "-nostdin",
        "-y",
        "-i",
        path,
        "-vf",
        f"select=eq(n\\,{index})",
        "-frames:v",
        "1",
        "-vsync",
        "0",
        output,
    ]


# The band a phone or laptop speaker actually reproduces. Measuring inside
# it is how Phase 6B.1 found that a Titan-heavy Short was six decibels down
# on the rest of a batch while its full-band loudness looked normal.
PHONE_BAND = "highpass=f=180,lowpass=f=5000"


def loudness_command(ffmpeg: str, path: str, band: str | None = None) -> list[str]:
    """Measure integrated loudness and true peak. Reporting only.

    `band` prepends a filter, so the same measurement can be taken over the
    whole spectrum or over just the part a small speaker has.
    """
    graph = "ebur128=peak=true:framelog=quiet"
    if band:
        graph = f"{band},{graph}"
    return [
        ffmpeg,
        "-hide_banner",
        "-nostdin",
        "-i",
        path,
        "-filter_complex",
        graph,
        "-f",
        "null",
        "-",
    ]


@dataclass(frozen=True)
class Loudness:
    integrated_lufs: float | None
    true_peak_dbfs: float | None
    range_lu: float | None


def parse_loudness(text: str) -> Loudness:
    """Pull the summary numbers out of ebur128's report on stderr."""
    integrated = peak = span = None
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if line.endswith(":") and not line.startswith(("I:", "Peak:", "LRA:")):
            section = line
            continue
        try:
            if line.startswith("I:"):
                integrated = float(line.split()[1])
            elif line.startswith("LRA:"):
                span = float(line.split()[1])
            elif line.startswith("Peak:") and "peak" in section.lower():
                peak = float(line.split()[1])
        except (IndexError, ValueError):
            continue
    return Loudness(integrated, peak, span)


# --- what the result has to report ------------------------------------------


@dataclass(frozen=True)
class VideoStream:
    codec: str
    profile: str
    width: int
    height: int
    pix_fmt: str
    frame_rate: str
    avg_frame_rate: str
    field_order: str | None
    frames: int | None
    duration: float | None


@dataclass(frozen=True)
class AudioStream:
    codec: str
    profile: str
    sample_rate: int
    channels: int
    duration: float | None
    samples: int | None


@dataclass(frozen=True)
class Probe:
    """What ffprobe says a file is."""

    format_name: str
    duration: float | None
    size: int | None
    video: VideoStream | None
    audio: AudioStream | None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _count(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_probe(payload: str | dict[str, Any]) -> Probe:
    """ffprobe's JSON, reduced to what production checks."""
    data = json.loads(payload) if isinstance(payload, str) else payload
    container = data.get("format") or {}
    video = audio = None

    for stream in data.get("streams") or []:
        kind = stream.get("codec_type")
        if kind == "video" and video is None:
            video = VideoStream(
                codec=str(stream.get("codec_name", "")),
                profile=str(stream.get("profile", "")),
                width=_count(stream.get("width")) or 0,
                height=_count(stream.get("height")) or 0,
                pix_fmt=str(stream.get("pix_fmt", "")),
                frame_rate=str(stream.get("r_frame_rate", "")),
                avg_frame_rate=str(stream.get("avg_frame_rate", "")),
                field_order=stream.get("field_order"),
                frames=_count(stream.get("nb_frames"))
                or _count(stream.get("nb_read_packets")),
                duration=_number(stream.get("duration")),
            )
        elif kind == "audio" and audio is None:
            audio = AudioStream(
                codec=str(stream.get("codec_name", "")),
                profile=str(stream.get("profile", "")),
                sample_rate=_count(stream.get("sample_rate")) or 0,
                channels=_count(stream.get("channels")) or 0,
                duration=_number(stream.get("duration")),
                samples=_count(stream.get("duration_ts")),
            )

    return Probe(
        format_name=str(container.get("format_name", "")),
        duration=_number(container.get("duration")),
        size=_count(container.get("size")),
        video=video,
        audio=audio,
    )


def probe_problems(
    probe: Probe,
    *,
    frame_count: int,
    spec: EncodeSpec = DEFAULT_SPEC,
    duration: float | None = None,
) -> list[str]:
    """Everything about a finished Short that is not what production requires.

    Every line this returns fails the encode. There is no repair path and no
    warning level: a file that is not 1080x1920 H.264 High at exactly 60 fps
    with 48 kHz stereo AAC-LC beside it is not the format, and uploading it
    would put the wrong thing in front of an audience.
    """
    problems: list[str] = []
    expected = duration if duration is not None else frame_count / spec.fps
    tolerance = spec.frame_seconds
    rate = f"{spec.fps}/1"

    if CONTAINER_HINT not in probe.format_name:
        problems.append(f"container is {probe.format_name!r}, expected MP4")

    if probe.video is None:
        problems.append("no video stream")
    else:
        video = probe.video
        if video.codec != VIDEO_CODEC:
            problems.append(f"video codec is {video.codec!r}, expected {VIDEO_CODEC!r}")
        if video.profile != VIDEO_PROFILE:
            problems.append(
                f"video profile is {video.profile!r}, expected {VIDEO_PROFILE!r}"
            )
        if (video.width, video.height) != (spec.width, spec.height):
            problems.append(
                f"video is {video.width}x{video.height},"
                f" expected {spec.width}x{spec.height}"
            )
        if video.pix_fmt != spec.pix_fmt:
            problems.append(
                f"pixel format is {video.pix_fmt!r}, expected {spec.pix_fmt!r}"
            )
        if video.frame_rate != rate or video.avg_frame_rate != rate:
            problems.append(
                f"frame rate is {video.frame_rate}/{video.avg_frame_rate},"
                f" expected {rate} constant"
            )
        if video.field_order not in (None, "progressive", "unknown"):
            problems.append(f"scan is {video.field_order!r}, expected progressive")
        if video.frames is not None and video.frames != frame_count:
            problems.append(f"{video.frames} video frames, expected {frame_count}")
        if video.duration is not None and abs(video.duration - expected) > tolerance:
            problems.append(
                f"video runs {video.duration:.4f}s, expected {expected:.4f}s"
            )

    if probe.audio is None:
        problems.append("no audio stream")
    else:
        audio = probe.audio
        if audio.codec != AUDIO_CODEC:
            problems.append(f"audio codec is {audio.codec!r}, expected {AUDIO_CODEC!r}")
        if audio.profile != AUDIO_PROFILE:
            problems.append(
                f"audio profile is {audio.profile!r}, expected AAC-{AUDIO_PROFILE}"
            )
        if audio.sample_rate != spec.sample_rate:
            problems.append(
                f"audio is {audio.sample_rate} Hz, expected {spec.sample_rate} Hz"
            )
        if audio.channels != spec.channels:
            problems.append(
                f"audio has {audio.channels} channels, expected {spec.channels}"
            )
        if audio.duration is not None and abs(audio.duration - expected) > tolerance:
            problems.append(
                f"audio runs {audio.duration:.4f}s, expected {expected:.4f}s"
            )

    if probe.video and probe.audio:
        one, other = probe.video.duration, probe.audio.duration
        if one is not None and other is not None and abs(one - other) > tolerance:
            problems.append(
                f"video and audio differ by {abs(one - other) * 1000:.1f} ms,"
                f" more than one {spec.fps} fps frame"
            )
    return problems


def decoded_audio_problems(
    samples: int, expected: int, sample_rate: int = 48000
) -> list[str]:
    """Whether a Short's decoded audio is the master, allowing for AAC padding.

    An AAC-LC encoder emits whole 1024-sample frames, so a master that is not
    a multiple of that comes back with up to one frame of silence on the end.
    Padding is accepted; anything missing is not, because a short soundtrack
    means the last thing a viewer hears was cut off.
    """
    problems: list[str] = []
    if samples < expected:
        problems.append(
            f"decoded audio is {expected - samples} samples short of the"
            f" {expected}-sample master"
        )
    elif samples - expected >= AAC_FRAME_SAMPLES:
        problems.append(
            f"decoded audio is {samples - expected} samples longer than the master,"
            f" more than one {AAC_FRAME_SAMPLES}-sample AAC frame of padding"
        )
    return problems
