"""Turn a rendered frame sequence into a finished, upload-ready Short.

The last step of the production pipeline. It takes a render directory that
Phase 6A already produced, generates the soundtrack for the replay that
render came from, and muxes the two into one H.264/AAC MP4::

    python tools/encode_short.py output/render_seed_33
    python tools/encode_short.py --batch output/render_audit10
    python tools/encode_short.py output/render_seed_33 --repeat-encode

Nothing is re-simulated and nothing is re-rendered. The frames on disk and
the replay they came from are both read-only; the render's own metadata is
what says which replay that is, and its recorded hash is what proves the
replay has not changed since.

Order matters, and it is: validate the source, generate the audio, validate
the audio, encode, validate the encode. FFmpeg is not called at all until
everything going into it has been checked, and nothing is ever deleted until
everything coming out of it has been.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio import cues, soundtrack, wav_io  # noqa: E402
from rendering import encode, png_frames  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    METADATA_NAME,
    frame_filename,
)
from replay.exporter import REPLAY_VERSION  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

AUDIO_NAME = "audio.wav"
AUDIO_METADATA_NAME = "audio_metadata.json"

MIB = 1024 * 1024
# Where a visual comparison looks. Four places a compression problem would
# show up differently: the opening, the middle of the fight, the busiest
# frame of VFX the render has, and the result panel where text has to stay
# readable.
COMPARE_LABELS = ("intro", "mid-battle", "busy VFX", "winner hold")


class ShortError(RuntimeError):
    """This render could not be turned into a finished Short."""


# --- reading what Phase 6A left behind --------------------------------------


def load_render(render_dir: str) -> dict:
    """A render directory's metadata, or a clear failure.

    The metadata is the contract between the two phases: it says how many
    frames exist, what size they are, which replay produced them and what
    that replay hashed to at the time.
    """
    path = os.path.join(render_dir, METADATA_NAME)
    if not os.path.isfile(path):
        raise ShortError(
            f"{render_dir} is not a render directory: no {METADATA_NAME}."
            " Render it first with tools/render_replay.py."
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_replay(metadata: dict, render_dir: str) -> str:
    """Where the replay this render came from actually is.

    The metadata records a repo-relative path deliberately, so the usual case
    is one join. A replay recorded by name alone - one that came from outside
    the project - is looked for beside the render as a fallback.
    """
    section = metadata.get("replay") or {}
    relative = section.get("path") or section.get("name")
    if not relative:
        raise ShortError(f"{render_dir}: metadata names no source replay")

    for candidate in (
        os.path.join(PROJECT_ROOT, relative),
        os.path.join(render_dir, relative),
        relative,
    ):
        if os.path.isfile(candidate):
            return candidate
    raise ShortError(f"{render_dir}: cannot find the source replay {relative!r}")


def load_replay(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    version = int(replay.get("version", 0))
    if version != REPLAY_VERSION:
        raise ShortError(
            f"{path}: replay version {version}, this pipeline plays v{REPLAY_VERSION}"
        )
    return replay


def check_source(
    render_dir: str, metadata: dict, replay_path: str, spec
) -> tuple[int, str]:
    """Validate everything going in, before anything is generated.

    Returns the frame count and the replay's hash. Raises rather than
    reporting, because there is nothing useful to do with a render whose
    frames are missing or whose replay has been edited since.
    """
    video = metadata.get("video") or {}
    frame_count = int(video.get("frame_count", 0))
    if frame_count <= 0:
        raise ShortError(f"{render_dir}: metadata says {frame_count} frames")
    if int(video.get("fps", 0)) != spec.fps:
        raise ShortError(
            f"{render_dir}: rendered at {video.get('fps')} fps,"
            f" this encode produces {spec.fps}"
        )
    if (int(video.get("width", 0)), int(video.get("height", 0))) != (
        spec.width,
        spec.height,
    ):
        raise ShortError(
            f"{render_dir}: rendered at {video.get('width')}x{video.get('height')},"
            f" expected {spec.width}x{spec.height}. This encode never rescales."
        )

    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    problems = encode.source_frame_problems(frames_dir, frame_count, spec)
    if problems:
        raise ShortError(
            f"{render_dir}: frame sequence is not complete; " + "; ".join(problems)
        )

    recorded = (metadata.get("replay") or {}).get("sha256")
    actual = png_frames.file_digest(replay_path)
    if recorded and recorded != actual:
        raise ShortError(
            f"{replay_path} has changed since it was rendered"
            f" ({actual[:12]} now, {recorded[:12]} then);"
            " the audio would not match the pictures"
        )
    return frame_count, actual


# --- the soundtrack ---------------------------------------------------------


def generate_audio(
    render_dir: str,
    metadata: dict,
    replay: dict,
    replay_path: str,
    replay_sha256: str,
    frame_count: int,
    bit_depth: int,
) -> tuple[str, soundtrack.Soundtrack, float]:
    """Build, write and validate the PCM master for one render."""
    plan = soundtrack.plan_soundtrack(replay, frame_count, bit_depth=bit_depth)

    started = time.perf_counter()
    track = soundtrack.build_soundtrack(replay, plan)
    elapsed = time.perf_counter() - started

    expected = frame_count * plan.samples_per_frame
    if track.sample_count != expected:
        raise ShortError(
            f"soundtrack is {track.sample_count} samples per channel,"
            f" expected exactly {frame_count} x {plan.samples_per_frame} = {expected}"
        )

    audio_path = os.path.join(render_dir, AUDIO_NAME)
    wav_io.write_wav(
        audio_path,
        track.left,
        track.right,
        sample_rate=plan.sample_rate,
        bit_depth=bit_depth,
    )

    info, data = wav_io.read_wav(audio_path)
    problems = wav_io.wav_problems(
        info,
        data,
        sample_rate=plan.sample_rate,
        channels=plan.channels,
        sample_count=expected,
        ceiling=soundtrack.PEAK_CEILING,
    )
    if problems:
        raise ShortError(f"{audio_path} is not a usable master: " + "; ".join(problems))

    section = metadata.get("replay") or {}
    sidecar = soundtrack.audio_metadata(
        track,
        replay_name=str(section.get("name") or os.path.basename(replay_path)),
        replay_path=str(section.get("path") or os.path.basename(replay_path)),
        replay_sha256=replay_sha256,
        pcm_sha256=wav_io.sha256_hex(data),
    )
    with open(
        os.path.join(render_dir, AUDIO_METADATA_NAME), "w", encoding="utf-8", newline="\n"
    ) as handle:
        json.dump(sidecar, handle, indent=2, sort_keys=True)
        handle.write("\n")

    return audio_path, track, elapsed


# --- the encode -------------------------------------------------------------


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def encode_video(
    ffmpeg: str, render_dir: str, audio_path: str, frame_count: int, output: str, spec
) -> float:
    frames = encode.frames_pattern(os.path.join(render_dir, FRAMES_SUBDIR))
    command = encode.encode_command(
        ffmpeg,
        frames=frames,
        audio=audio_path,
        output=output,
        frame_count=frame_count,
        spec=spec,
    )
    started = time.perf_counter()
    completed = run(command)
    elapsed = time.perf_counter() - started
    if completed.returncode != 0:
        raise ShortError(f"FFmpeg exited {completed.returncode}; no Short was produced")
    if not os.path.isfile(output):
        raise ShortError(f"FFmpeg reported success but {output} is not there")
    return elapsed


def probe(ffprobe: str, path: str) -> encode.Probe:
    completed = run(encode.probe_command(ffprobe, path), capture=True)
    if completed.returncode != 0:
        raise ShortError(
            f"ffprobe exited {completed.returncode} on {path}:"
            f" {completed.stderr.decode('utf-8', 'replace').strip()}"
        )
    return encode.parse_probe(completed.stdout.decode("utf-8", "replace"))


def decoded_audio(ffmpeg: str, path: str, sample_rate: int) -> bytes:
    completed = run(encode.decode_audio_command(ffmpeg, path, sample_rate), capture=True)
    if completed.returncode != 0:
        raise ShortError(f"could not decode the audio of {path}")
    return completed.stdout


def measure_loudness(ffmpeg: str, path: str) -> encode.Loudness:
    completed = run(encode.loudness_command(ffmpeg, path), capture=True)
    return encode.parse_loudness(completed.stderr.decode("utf-8", "replace"))


def validate_short(
    ffmpeg: str, ffprobe: str, path: str, frame_count: int, expected_samples: int, spec
) -> tuple[encode.Probe, int]:
    """Everything the finished file has to report before it is accepted."""
    result = probe(ffprobe, path)
    problems = encode.probe_problems(result, frame_count=frame_count, spec=spec)

    pcm = decoded_audio(ffmpeg, path, spec.sample_rate)
    samples = len(pcm) // (2 * spec.channels)
    problems += encode.decoded_audio_problems(samples, expected_samples, spec.sample_rate)

    if problems:
        raise ShortError(
            f"{os.path.basename(path)} is not the production format: "
            + "; ".join(problems)
        )
    return result, samples


# --- optional checks --------------------------------------------------------


def compare_frames(ffmpeg: str, render_dir: str, short: str, metadata: dict) -> list[str]:
    """Decode a few frames of the Short and measure them against the source.

    H.264 is lossy, so these can never match exactly and a digest would say
    nothing. What is worth knowing is whether they are the same picture: the
    same size, in the same order, a few levels off rather than a few dozen.
    """
    timeline = metadata.get("timeline") or {}
    frame_count = int((metadata.get("video") or {}).get("frame_count", 0))
    gameplay = int(timeline.get("gameplay_frames", frame_count))
    indices = (0, gameplay // 2, max(0, gameplay - 1), frame_count - 1)

    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    scratch = os.path.join(render_dir, "_compare.png")
    lines: list[str] = []
    try:
        for label, index in zip(COMPARE_LABELS, indices):
            completed = run(
                encode.extract_frame_command(ffmpeg, short, index, scratch), capture=True
            )
            if completed.returncode != 0 or not os.path.isfile(scratch):
                lines.append(f"    {label:12s} frame {index}: could not be decoded")
                continue
            source = png_frames.rgb_bytes(os.path.join(frames_dir, frame_filename(index)))
            decoded = png_frames.rgb_bytes(scratch)
            if source[:2] != decoded[:2]:
                lines.append(
                    f"    {label:12s} frame {index}: decoded {decoded[0]}x{decoded[1]},"
                    f" source {source[0]}x{source[1]}"
                )
                continue
            total = sum(abs(a - b) for a, b in zip(source[2], decoded[2]))
            worst = max(abs(a - b) for a, b in zip(source[2], decoded[2]))
            mean = total / len(source[2])
            lines.append(
                f"    {label:12s} frame {index:5d}  mean |diff| {mean:5.2f}/255"
                f"  worst {worst:3d}"
            )
    finally:
        if os.path.isfile(scratch):
            os.remove(scratch)
    return lines


def repeat_encode(
    ffmpeg: str, ffprobe: str, render_dir: str, audio_path: str, frame_count: int, spec
) -> list[str]:
    """Encode the same inputs a second time and say how far the results agree.

    Container metadata can differ between FFmpeg builds, so byte identity is
    reported when it happens rather than required. What is required is that
    the two files are the same video and the same sound: identical stream
    properties, identical decoded audio, identical decoded pixels on
    representative frames.
    """
    first = encode.output_path(render_dir)
    second = os.path.join(render_dir, "_repeat.mp4")
    lines: list[str] = []
    try:
        encode_video(ffmpeg, render_dir, audio_path, frame_count, second, spec)

        same_bytes = png_frames.file_digest(first) == png_frames.file_digest(second)
        lines.append(f"    file bytes      {'IDENTICAL' if same_bytes else 'differ'}")

        one, other = probe(ffprobe, first), probe(ffprobe, second)
        lines.append(
            f"    stream props    {'IDENTICAL' if one == other else 'DIFFER'}"
        )

        pcm_one = decoded_audio(ffmpeg, first, spec.sample_rate)
        pcm_two = decoded_audio(ffmpeg, second, spec.sample_rate)
        lines.append(
            "    decoded audio   "
            + (
                "IDENTICAL"
                if wav_io.sha256_hex(pcm_one) == wav_io.sha256_hex(pcm_two)
                else "DIFFER"
            )
        )

        checkpoints = (0, frame_count // 2, frame_count - 1)
        digests = []
        for path in (first, second):
            per_file = []
            for index in checkpoints:
                scratch = os.path.join(render_dir, f"_det_{index}.png")
                run(
                    encode.extract_frame_command(ffmpeg, path, index, scratch),
                    capture=True,
                )
                per_file.append(
                    png_frames.pixel_digest(scratch) if os.path.isfile(scratch) else None
                )
                if os.path.isfile(scratch):
                    os.remove(scratch)
            digests.append(per_file)
        lines.append(
            f"    decoded pixels  "
            f"{'IDENTICAL' if digests[0] == digests[1] and all(digests[0]) else 'DIFFER'}"
            f" ({len(checkpoints)} frames)"
        )
    finally:
        if os.path.isfile(second):
            os.remove(second)
    return lines


def cleanup(render_dir: str, frame_count: int, frames: bool, audio: bool) -> list[str]:
    """Remove the intermediates, and only ever after everything has passed.

    Called at the very end of a successful job and nowhere else. A failed
    encode leaves its source frames exactly where they are, because they are
    an hour of rendering and the failure is the thing that needs fixing.
    """
    removed: list[str] = []
    if frames:
        frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
        freed = 0
        for index in range(frame_count):
            path = os.path.join(frames_dir, frame_filename(index))
            if os.path.isfile(path):
                freed += os.path.getsize(path)
                os.remove(path)
        removed.append(f"frames ({freed / MIB:.0f} MiB)")
    if audio:
        path = os.path.join(render_dir, AUDIO_NAME)
        if os.path.isfile(path):
            removed.append(f"{AUDIO_NAME} ({os.path.getsize(path) / MIB:.1f} MiB)")
            os.remove(path)
    return removed


# --- one job ----------------------------------------------------------------


def encode_short(
    render_dir: str, args: argparse.Namespace, ffmpeg: str, ffprobe: str
) -> None:
    spec = encode.EncodeSpec(crf=args.crf, preset=args.preset)
    metadata = load_render(render_dir)
    replay_path = resolve_replay(metadata, render_dir)
    frame_count, replay_sha256 = check_source(render_dir, metadata, replay_path, spec)
    replay = load_replay(replay_path)

    seed = (metadata.get("replay") or {}).get("seed")
    print(
        f"\n=== {os.path.relpath(render_dir, PROJECT_ROOT)}  seed {seed} ===\n"
        f"    {frame_count} frames @ {spec.fps}fps = {frame_count / spec.fps:.3f}s,"
        f" {spec.width}x{spec.height}"
    )

    audio_path = os.path.join(render_dir, AUDIO_NAME)
    if args.skip_audio:
        if not os.path.isfile(audio_path):
            raise ShortError(f"--skip-audio but there is no {AUDIO_NAME} to reuse")
        track = None
        audio_seconds = 0.0
        info, _ = wav_io.read_wav(audio_path)
        expected_samples = info.sample_count
        print(f"    audio      reused {AUDIO_NAME} ({info.sample_count} samples)")
    else:
        audio_path, track, audio_seconds = generate_audio(
            render_dir,
            metadata,
            replay,
            replay_path,
            replay_sha256,
            frame_count,
            args.bit_depth,
        )
        expected_samples = track.sample_count
        cue_summary = ", ".join(
            f"{name} x{count}" for name, count in sorted(track.cue_counts.items())
        )
        print(
            f"    audio      {audio_seconds:.1f}s"
            f"  {track.sample_count} samples/ch @ {track.plan.sample_rate} Hz"
            f" {args.bit_depth}-bit\n"
            f"               peak {soundtrack.gain_to_db(track.peak):+.2f} dBFS,"
            f" rms {soundtrack.gain_to_db(track.level_rms):+.2f} dBFS,"
            f" makeup {soundtrack.gain_to_db(track.makeup_gain):+.2f} dB,"
            f" limiter {'engaged' if track.limited else 'idle'}\n"
            f"               {len(track.schedule)} cues: {cue_summary}"
        )

    if args.audio_only:
        print("    (--audio-only: stopping before the encode)")
        return

    short = encode.output_path(render_dir)
    encode_seconds = encode_video(ffmpeg, render_dir, audio_path, frame_count, short, spec)
    result, decoded = validate_short(
        ffmpeg, ffprobe, short, frame_count, expected_samples, spec
    )

    video, audio = result.video, result.audio
    print(
        f"    encode     {encode_seconds:.1f}s"
        f"  ({frame_count / max(encode_seconds, 1e-6):.0f} frames/sec)\n"
        f"    validated  {video.codec} {video.profile} {video.width}x{video.height}"
        f" {video.pix_fmt} {video.frame_rate}, {video.frames} frames\n"
        f"               {audio.codec} {audio.profile} {audio.sample_rate} Hz"
        f" x{audio.channels}, {decoded} samples decoded"
        f" (+{decoded - expected_samples} AAC padding)\n"
        f"               video {video.duration:.4f}s, audio {audio.duration:.4f}s,"
        f" planned {frame_count / spec.fps:.4f}s,"
        f" sync {abs(video.duration - audio.duration) * 1000:.2f} ms"
    )

    if args.loudness:
        level = measure_loudness(ffmpeg, short)
        print(
            f"    loudness   {level.integrated_lufs} LUFS integrated,"
            f" true peak {level.true_peak_dbfs} dBFS, range {level.range_lu} LU"
        )

    if args.compare_frames:
        print("    source vs decoded:")
        for line in compare_frames(ffmpeg, render_dir, short, metadata):
            print(line)

    if args.repeat_encode:
        print("    repeat encode:")
        for line in repeat_encode(
            ffmpeg, ffprobe, render_dir, audio_path, frame_count, spec
        ):
            print(line)

    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    frames_size = sum(
        os.path.getsize(os.path.join(frames_dir, frame_filename(index)))
        for index in range(frame_count)
    )
    print(
        f"    sizes      frames {frames_size / MIB:.0f} MiB,"
        f" wav {os.path.getsize(audio_path) / MIB:.1f} MiB,"
        f" mp4 {os.path.getsize(short) / MIB:.1f} MiB\n"
        f"    {os.path.relpath(short, PROJECT_ROOT)}"
    )

    removed = cleanup(render_dir, frame_count, args.cleanup_frames, args.cleanup_audio)
    if removed:
        print(f"    cleaned up  {', '.join(removed)}")


# --- batches ----------------------------------------------------------------


def batch_jobs(root: str, limit: int | None) -> list[str]:
    """Every render directory directly under `root`, in name order."""
    if not os.path.isdir(root):
        raise ShortError(f"no such directory: {root}")
    found = [
        os.path.join(root, name)
        for name in sorted(os.listdir(root))
        if os.path.isfile(os.path.join(root, name, METADATA_NAME))
    ]
    if not found and os.path.isfile(os.path.join(root, METADATA_NAME)):
        found = [root]
    return found if limit is None else found[:limit]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="encode a rendered sequence and its original soundtrack into an MP4"
    )
    parser.add_argument("render", nargs="*", help="render directories to encode")
    parser.add_argument("--batch", default=None, help="encode every render under this root")
    parser.add_argument("--limit", type=int, default=None, help="first N batch items")
    parser.add_argument("--ffmpeg", default=None, help="path to the FFmpeg executable")
    parser.add_argument("--ffprobe", default=None, help="path to the ffprobe executable")
    parser.add_argument("--crf", type=int, default=encode.DEFAULT_SPEC.crf)
    parser.add_argument("--preset", default=encode.DEFAULT_SPEC.preset)
    parser.add_argument(
        "--bit-depth", type=int, default=wav_io.DEFAULT_BIT_DEPTH, choices=wav_io.BIT_DEPTHS
    )
    parser.add_argument(
        "--audio-only", action="store_true", help="write the WAV and stop"
    )
    parser.add_argument(
        "--skip-audio", action="store_true", help="reuse the audio.wav already there"
    )
    parser.add_argument(
        "--no-loudness",
        dest="loudness",
        action="store_false",
        help="skip the ebur128 loudness measurement",
    )
    parser.add_argument(
        "--compare-frames",
        action="store_true",
        help="decode representative frames and measure them against the source PNGs",
    )
    parser.add_argument(
        "--repeat-encode",
        action="store_true",
        help="encode twice and report how far the two results agree",
    )
    parser.add_argument(
        "--cleanup-frames",
        action="store_true",
        help="delete the source PNGs, but only after the Short has been validated",
    )
    parser.add_argument(
        "--cleanup-audio",
        action="store_true",
        help="delete audio.wav, but only after the Short has been validated",
    )
    parser.add_argument(
        "--keep-going",
        action="store_true",
        help="finish the remaining items after one fails, then still exit non-zero",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if bool(args.render) == bool(args.batch):
        print(
            "give either one or more render directories, or --batch ROOT",
            file=sys.stderr,
        )
        return 2
    if args.audio_only and args.skip_audio:
        print("--audio-only and --skip-audio cannot both be given", file=sys.stderr)
        return 2

    try:
        jobs = batch_jobs(args.batch, args.limit) if args.batch else list(args.render)
        if not jobs:
            raise ShortError("nothing to encode")
        if args.audio_only:
            ffmpeg = ffprobe = ""
        else:
            ffmpeg = encode.find_ffmpeg(args.ffmpeg)
            ffprobe = encode.find_ffprobe(args.ffprobe, ffmpeg)
    except (ShortError, encode.EncodeError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not args.audio_only:
        print(f"ffmpeg:  {ffmpeg}\nffprobe: {ffprobe}")
    print(
        f"audio:   v{soundtrack.SOUNDTRACK_VERSION} original synthesis,"
        f" {soundtrack.SAMPLES_PER_FRAME} samples/frame,"
        f" {soundtrack.SAMPLES_PER_TICK} samples/tick,"
        f" bed {cues.AMBIENCE_LOW_RMS_DBFS:.0f}/"
        f"{cues.AMBIENCE_MID_RMS_DBFS:.0f} dBFS RMS pre-master"
    )

    started = time.perf_counter()
    failures: list[str] = []
    for render_dir in jobs:
        try:
            encode_short(render_dir, args, ffmpeg, ffprobe)
        except (
            ShortError,
            encode.EncodeError,
            soundtrack.SoundtrackError,
            wav_io.WavError,
            png_frames.PngError,
            OSError,
        ) as error:
            print(f"    FAILED: {error}", file=sys.stderr)
            failures.append(f"{os.path.basename(render_dir)}: {error}")
            if not args.keep_going:
                break
    total = time.perf_counter() - started

    if failures:
        print(f"\n{len(failures)} of {len(jobs)} encodes failed:", file=sys.stderr)
        for failure in failures:
            print(f"  {failure}", file=sys.stderr)
        return 1

    print(f"\n{len(jobs)} Short(s) complete in {total:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
