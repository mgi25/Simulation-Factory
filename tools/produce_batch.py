"""Produce a whole curated batch: replay, frames, audio, MP4, QC, delivery.

One command for what used to be four per video::

    python tools/produce_batch.py output/batch_audit10/manifest.json
    python tools/produce_batch.py output/batch_shorts001/manifest.json --limit 5
    python tools/produce_batch.py output/batch_audit10/manifest.json --force

It does not simulate, render, synthesise or encode anything itself. Every
stage is the tool that already existed and is already tested - the replay
exporter, `render_replay.render`, `encode_short.generate_audio`,
`encode_short.encode_video` - called in order, with the checking and the
packaging around them.

Two things it adds that the individual tools could not:

* Resume. Rendering a Short is two and a half minutes, so a second run has
  to reuse what is already good. Reuse is decided by the same rules that
  decide whether an item passes QC at all, never by a file existing, and
  every decision is printed rather than kept in a cache.
* A delivery folder. Finished MP4s and their QC records, and nothing else -
  no frame sequences, no WAVs, no replays. Those stay in the working render
  directories where they were made.

Automated QC is a hard pass or fail. Whether a Short is any good is a
separate question with a separate answer, and this tool only ever writes
`pending` to it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audio import wav_io  # noqa: E402
from audio.soundtrack import SOUNDTRACK_VERSION  # noqa: E402
from production import contact_sheet, delivery, qc  # noqa: E402
from rendering import encode, png_frames  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    METADATA_NAME,
    POST_ROLL_SECONDS,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    frame_filename,
    sequence_problems,
)
from replay.exporter import record_battle, write_replay  # noqa: E402
from tools import build_batch, encode_short, render_replay  # noqa: E402

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT_ROOT = "output"
MIB = 1024 * 1024
STAGES = ("replay", "frames", "audio", "encode", "qc")


class ProductionError(RuntimeError):
    """One item could not be produced."""


# --- reading the batch -----------------------------------------------------


def load_batch(path: str) -> tuple[dict, str, str]:
    """The manifest, its directory, and the batch id. Validated, not trusted."""
    if not os.path.isfile(path):
        raise ProductionError(f"no batch manifest at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)

    version = int(manifest.get("version", 0))
    if version != build_batch.MANIFEST_VERSION:
        raise ProductionError(
            f"{path}: batch manifest version {version},"
            f" production reads v{build_batch.MANIFEST_VERSION}"
        )
    items = manifest.get("items") or []
    if not items:
        raise ProductionError(f"{path}: the batch has no items")
    for entry in items:
        for required in ("index", "seed", "powers", "winner_id", "duration"):
            if entry.get(required) is None:
                raise ProductionError(
                    f"{path}: item {entry.get('index')} has no {required!r}"
                )
    batch_id = str(manifest.get("batch_id") or "batch")
    return manifest, os.path.dirname(os.path.abspath(path)), batch_id


def replay_path_for(entry: dict, batch_dir: str) -> str:
    """Where this item's replay lives, whether or not it is there yet.

    A manifest built with `--export-replays` names the path; one built
    without it does not, and production still has to know where to put the
    replay it exports, so the same naming is used either way.
    """
    relative = entry.get("replay_path")
    if not relative:
        relative = (
            f"{build_batch.REPLAY_SUBDIR}/"
            f"{int(entry['index']):03d}_seed_{int(entry['seed'])}.json"
        )
    return os.path.join(batch_dir, relative)


# --- gathering the facts ---------------------------------------------------


def gather_replay(path: str) -> qc.ReplayFacts:
    if not os.path.isfile(path):
        return qc.ReplayFacts()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            replay = json.load(handle)
    except (OSError, ValueError):
        return qc.ReplayFacts()
    result = replay.get("result") or {}
    return qc.ReplayFacts(
        exists=True,
        version=int(replay.get("version", 0)),
        seed=int(replay.get("seed", -1)),
        powers=tuple(
            fighter.get("power", "") for fighter in replay.get("fighters") or ()
        ),
        winner_id=result.get("winner_id"),
        is_draw=bool(result.get("is_draw")),
        duration=float(result.get("duration", 0.0) or 0.0),
        sha256=png_frames.file_digest(path),
    )


def gather_render(
    render_dir: str, replay: qc.ReplayFacts, recorded: str | None
) -> qc.RenderFacts:
    """Everything about the frame sequence, including its aggregate hash.

    The hash is computed on every run, which is the point: a sequence that
    has changed since it was last checked has to be caught before its frames
    are muxed into a video somebody approves.
    """
    metadata = delivery.read_json(os.path.join(render_dir, METADATA_NAME))
    if not metadata:
        return qc.RenderFacts()

    video = metadata.get("video") or {}
    timeline = metadata.get("timeline") or {}
    frame_count = int(video.get("frame_count", 0))
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)

    problems: list[str] = []
    if not os.path.isdir(frames_dir):
        problems.append(f"no frames directory in {os.path.basename(render_dir)}")
    else:
        problems.extend(sequence_problems(os.listdir(frames_dir), frame_count))
        if not problems:
            problems.extend(
                encode.source_frame_problems(
                    frames_dir,
                    frame_count,
                    encode.EncodeSpec(
                        width=int(video.get("width", 0)),
                        height=int(video.get("height", 0)),
                    ),
                )
            )

    digest = ""
    blank: list[str] = []
    if not problems:
        digest = qc.sequence_digest(frames_dir, frame_count)
        blank = blank_frames(
            frames_dir, frame_count, int(timeline.get("gameplay_frames", 0))
        )

    return qc.RenderFacts(
        exists=True,
        render_version=int(metadata.get("render_version", 0)),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=int(video.get("fps", 0)),
        frame_count=frame_count,
        gameplay_frames=int(timeline.get("gameplay_frames", 0)),
        post_roll_frames=int(timeline.get("post_roll_frames", 0)),
        replay_sha256=str((metadata.get("replay") or {}).get("sha256", "")),
        sequence_sha256=digest,
        sequence_problems=tuple(problems),
        blank_frames=tuple(blank),
        recorded_sequence_sha256=recorded,
    )


def blank_frames(frames_dir: str, frame_count: int, gameplay_frames: int) -> list[str]:
    """Representative frames that have nothing drawn in them.

    Eight samples rather than two thousand: enough to catch a render that
    produced black, a result panel that never arrived, or a sequence of
    identical pictures, without decoding the whole Short. Nothing here judges
    how a frame *looks* - that is a person's job, and this phase does not
    change a single pixel either way.
    """
    if frame_count <= 0 or gameplay_frames <= 0:
        return []
    empty: list[str] = []
    for label, index in qc.visual_checkpoints(frame_count, gameplay_frames).items():
        path = os.path.join(frames_dir, frame_filename(index))
        if not os.path.isfile(path):
            empty.append(f"{frame_filename(index)} ({label}) is missing")
            continue
        try:
            frame = png_frames.sample(path)
        except png_frames.PngError as error:
            empty.append(f"{frame_filename(index)} ({label}): {error}")
            continue
        if (frame.width, frame.height) != (RENDER_WIDTH, RENDER_HEIGHT):
            empty.append(
                f"{frame_filename(index)} ({label}) is {frame.width}x{frame.height}"
            )
        elif frame.is_black:
            empty.append(f"{frame_filename(index)} ({label}) is completely black")
        elif frame.is_blank:
            empty.append(f"{frame_filename(index)} ({label}) is a flat colour")
    return empty


def gather_audio(render_dir: str, replay: qc.ReplayFacts) -> qc.AudioFacts:
    audio_path = os.path.join(render_dir, encode_short.AUDIO_NAME)
    sidecar = delivery.read_json(
        os.path.join(render_dir, encode_short.AUDIO_METADATA_NAME)
    )
    if not os.path.isfile(audio_path) or not sidecar:
        return qc.AudioFacts()

    try:
        info, data = wav_io.read_wav(audio_path)
    except wav_io.WavError as error:
        return qc.AudioFacts(exists=True, problems=(str(error),))

    section = sidecar.get("audio") or {}
    problems = wav_io.wav_problems(
        info,
        data,
        sample_rate=qc.EXPECTED_SAMPLE_RATE,
        channels=qc.EXPECTED_CHANNELS,
        sample_count=info.sample_count,
    )
    recorded = str(section.get("pcm_sha256", ""))
    actual = wav_io.sha256_hex(data)
    if recorded and recorded != actual:
        problems.append(
            f"audio.wav does not match its own metadata ({actual[:12]} now,"
            f" {recorded[:12]} recorded)"
        )
    return qc.AudioFacts(
        exists=True,
        audio_version=int(sidecar.get("audio_version", 0)),
        sample_rate=info.sample_rate,
        channels=info.channels,
        bit_depth=info.bit_depth,
        samples=info.sample_count,
        pcm_sha256=actual,
        replay_sha256=str((sidecar.get("replay") or {}).get("sha256", "")),
        peak=wav_io.pcm_peak(data, info.bit_depth),
        problems=tuple(problems),
    )


def gather_video(
    ffmpeg: str,
    ffprobe: str,
    path: str,
    frame_count: int,
    expected_samples: int,
    spec: encode.EncodeSpec,
) -> qc.VideoFacts:
    if not os.path.isfile(path):
        return qc.VideoFacts()

    completed = encode_short.run(encode.probe_command(ffprobe, path), capture=True)
    if completed.returncode != 0:
        return qc.VideoFacts(exists=True, problems=("ffprobe could not read the file",))
    probe = encode.parse_probe(completed.stdout.decode("utf-8", "replace"))

    problems = encode.probe_problems(probe, frame_count=frame_count, spec=spec)
    decoded = encode_short.decoded_audio(ffmpeg, path, spec.sample_rate)
    samples = len(decoded) // (2 * spec.channels)
    problems += encode.decoded_audio_problems(samples, expected_samples, spec.sample_rate)

    video, audio = probe.video, probe.audio
    return qc.VideoFacts(
        exists=True,
        sha256=png_frames.file_digest(path),
        size=os.path.getsize(path),
        codec="" if video is None else video.codec,
        profile="" if video is None else video.profile,
        width=0 if video is None else video.width,
        height=0 if video is None else video.height,
        pix_fmt="" if video is None else video.pix_fmt,
        frame_rate="" if video is None else video.frame_rate,
        field_order=None if video is None else video.field_order,
        frames=None if video is None else video.frames,
        duration=None if video is None else video.duration,
        audio_codec="" if audio is None else audio.codec,
        audio_profile="" if audio is None else audio.profile,
        audio_rate=0 if audio is None else audio.sample_rate,
        audio_channels=0 if audio is None else audio.channels,
        audio_duration=None if audio is None else audio.duration,
        decoded_samples=samples,
        faststart=qc.moov_before_mdat(path),
        problems=tuple(problems),
    )


def gather_loudness(ffmpeg: str, path: str) -> qc.LoudnessFacts:
    """Measured, and only measured. Phase 6C does not retune audio."""
    full = encode.parse_loudness(
        encode_short.run(encode.loudness_command(ffmpeg, path), capture=True).stderr.decode(
            "utf-8", "replace"
        )
    )
    band = encode.parse_loudness(
        encode_short.run(
            encode.loudness_command(ffmpeg, path, encode.PHONE_BAND), capture=True
        ).stderr.decode("utf-8", "replace")
    )
    return qc.LoudnessFacts(
        integrated_lufs=full.integrated_lufs,
        true_peak_dbfs=full.true_peak_dbfs,
        range_lu=full.range_lu,
        band_lufs=band.integrated_lufs,
    )


# --- the stages ------------------------------------------------------------


def export_replay(entry: dict, path: str) -> None:
    """Run the selected battle once and freeze it, then check it is the one.

    The only place in production that runs gameplay at all, and it only runs
    when there is no replay yet. Once a replay exists it is the creative
    source and nothing re-derives it - restarting the production tool must
    never quietly produce a different battle.
    """
    replay = record_battle(
        int(entry["seed"]), arena_mode=str(entry.get("arena_mode") or "classic")
    )
    actual = build_batch.replay_facts(replay)
    expected = build_batch.manifest_facts(entry)
    if actual != expected:
        raise ProductionError(
            f"seed {entry['seed']}: the exported replay is not the battle the"
            f" manifest selected.\n  manifest {expected}\n  replay   {actual}"
        )
    write_replay(replay, path)


def render_frames(godot: str, replay_path: str, render_dir: str) -> None:
    render_replay.render(
        godot,
        replay_path,
        render_dir,
        RENDER_FPS,
        RENDER_WIDTH,
        RENDER_HEIGHT,
        POST_ROLL_SECONDS,
    )


def build_audio(render_dir: str, replay_path: str, replay: qc.ReplayFacts) -> None:
    metadata = encode_short.load_render(render_dir)
    with open(replay_path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    encode_short.generate_audio(
        render_dir,
        metadata,
        loaded,
        replay_path,
        replay.sha256,
        int((metadata.get("video") or {}).get("frame_count", 0)),
        wav_io.DEFAULT_BIT_DEPTH,
    )


def encode_mp4(
    ffmpeg: str, render_dir: str, frame_count: int, spec: encode.EncodeSpec
) -> str:
    output = encode.output_path(render_dir)
    encode_short.encode_video(
        ffmpeg,
        render_dir,
        os.path.join(render_dir, encode_short.AUDIO_NAME),
        frame_count,
        output,
        spec,
    )
    return output


# --- one item --------------------------------------------------------------


def produce_item(
    entry: dict,
    *,
    batch_id: str,
    batch_dir: str,
    render_dir: str,
    delivery_dir: str,
    godot: str,
    ffmpeg: str,
    ffprobe: str,
    spec: encode.EncodeSpec,
    force: bool,
    timings: dict[str, float],
) -> dict:
    """Take one manifest item all the way to a delivered, checked Short."""
    index, seed = int(entry["index"]), int(entry["seed"])
    print(f"\n{index:03d} seed {seed}  {entry.get('label', '')}")

    previous = delivery.read_json(os.path.join(delivery_dir, qc.QC_NAME))
    review_status, review_note = qc.review_of(previous)
    recorded_sequence = ((previous or {}).get("render") or {}).get("sequence_sha256")

    replay_path = replay_path_for(entry, batch_dir)
    short_path = encode.output_path(render_dir)

    # --- the replay first, because everything else is checked against it --
    replay = gather_replay(replay_path)
    if qc.replay_problems(entry, replay):
        if replay.exists:
            # It is there and it is not the battle the manifest selected.
            # Re-exporting would paper over whichever of the two is wrong.
            raise ProductionError("; ".join(qc.replay_problems(entry, replay)))
        started = time.perf_counter()
        export_replay(entry, replay_path)
        timings["replay"] += time.perf_counter() - started
        replay = gather_replay(replay_path)
        problems = qc.replay_problems(entry, replay)
        if problems:
            raise ProductionError("; ".join(problems))
        replay_action = delivery.GENERATED
    else:
        replay_action = delivery.REUSED
    print(f"  replay   {replay_action}")

    # --- what else is already good ---------------------------------------
    render = gather_render(render_dir, replay, recorded_sequence)
    audio = gather_audio(render_dir, replay)
    video = qc.VideoFacts()
    render_valid = not qc.render_problems(render, replay)
    audio_valid = not qc.audio_problems(audio, render, replay)
    if render_valid and audio_valid:
        video = gather_video(
            ffmpeg, ffprobe, short_path, render.frame_count, audio.samples, spec
        )
    plan = delivery.stage_plan(render_valid, audio_valid, not qc.video_problems(video))

    if plan["frames"] == delivery.GENERATED:
        if not godot:
            raise ProductionError(
                "frames need rendering but no Godot was found. Pass --godot PATH"
                " or set $GODOT_BIN."
            )
        started = time.perf_counter()
        render_frames(godot, replay_path, render_dir)
        timings["frames"] += time.perf_counter() - started
        render = gather_render(render_dir, replay, None)
    print(f"  frames   {plan['frames']}")

    if plan["audio"] == delivery.GENERATED:
        started = time.perf_counter()
        build_audio(render_dir, replay_path, replay)
        timings["audio"] += time.perf_counter() - started
        audio = gather_audio(render_dir, replay)
    print(f"  audio    {plan['audio']}")

    if plan["encode"] == delivery.GENERATED:
        started = time.perf_counter()
        encode_mp4(ffmpeg, render_dir, render.frame_count, spec)
        timings["encode"] += time.perf_counter() - started
        video = gather_video(
            ffmpeg, ffprobe, short_path, render.frame_count, audio.samples, spec
        )
    print(f"  encode   {plan['encode']}")

    # --- judge and package ------------------------------------------------
    started = time.perf_counter()
    loudness = (
        gather_loudness(ffmpeg, short_path) if video.exists else qc.LoudnessFacts()
    )
    evidence = qc.Evidence(
        item=entry, replay=replay, render=render, audio=audio, video=video,
        loudness=loudness,
    )
    problems, warnings = qc.evaluate(evidence)
    record = qc.with_review(
        qc.qc_record(evidence, batch_id=batch_id, problems=problems, warnings=warnings),
        review_status,
        review_note,
    )

    if record["status"] == qc.STATUS_PASS:
        outcome = delivery.deliver_file(
            short_path,
            os.path.join(delivery_dir, encode.SHORT_NAME),
            digest_of=png_frames.file_digest,
            force=force,
            protected=review_status == qc.REVIEW_APPROVED,
        )
    else:
        outcome = "not delivered"
    delivery.write_json(os.path.join(delivery_dir, qc.QC_NAME), record)
    timings["qc"] += time.perf_counter() - started

    print(f"  QC       {record['status'].upper()}  ({outcome})")
    for line in warnings:
        print(f"    warning: {line}")
    for line in problems:
        print(f"    FAIL: {line}")
    return record


# --- the batch -------------------------------------------------------------


def draw_contact_sheet(
    records: list[dict], render_dirs: dict[int, str], path: str
) -> str | None:
    """One sheet for the batch, from the mid-battle frame of each Short."""
    cells = []
    for record in records:
        source = record.get("source") or {}
        index = int(source.get("index", 0))
        render = record.get("render") or {}
        frames = int(render.get("frames", 0))
        gameplay = int(render.get("gameplay_frames", 0)) or frames
        frame_path = ""
        if frames > 0 and index in render_dirs:
            middle = qc.visual_checkpoints(frames, gameplay)["50%"]
            frame_path = os.path.join(
                render_dirs[index], FRAMES_SUBDIR, frame_filename(middle)
            )
        cells.append(
            (
                index,
                int(source.get("seed", 0)),
                str(source.get("label", "")),
                str(record.get("status", "")),
                frame_path,
            )
        )
    if not cells:
        return None
    try:
        return contact_sheet.build_sheet(cells, path)
    except Exception as error:  # pragma: no cover - review artefact only
        print(f"  (contact sheet skipped: {error})", file=sys.stderr)
        return None


def report(manifest: dict, elapsed: float, timings: dict[str, float]) -> None:
    summary = manifest["summary"]
    review = summary["review"]
    print(f"\n{'=' * 62}\nBatch {manifest['batch_id']}\n{'=' * 62}")
    print(f"Items:            {summary['items']}")
    print(f"Automated PASS:   {summary['automated_pass']}")
    print(f"Automated FAIL:   {summary['automated_fail']}")
    print(f"Warnings:         {summary['warnings']}")
    print(
        f"\nReview:           approved {review['approved']},"
        f" pending {review['pending']}, rejected {review['rejected']}"
    )
    score, duration = summary["score"], summary["duration"]
    print(
        f"\nScore:            min {score['min']}  mean {score['mean']}"
        f"  max {score['max']}"
    )
    print(
        f"Duration:         min {duration['min']}s  mean {duration['mean']}s"
        f"  max {duration['max']}s  total {duration['total']}s"
    )
    loudness, band = summary["integrated_lufs"], summary["phone_band_lufs"]
    print(
        f"Integrated LUFS:  min {loudness['min']}  mean {loudness['mean']}"
        f"  max {loudness['max']}"
    )
    print(
        f"Phone-band LUFS:  min {band['min']}  mean {band['mean']}  max {band['max']}"
    )
    sizes = summary["video_bytes"]
    print(
        f"Final MP4:        total {sizes['total'] / MIB:.1f} MiB"
        f"  mean {sizes['mean'] / MIB:.1f} MiB"
    )
    print(
        f"\nProduction time:  {elapsed:.1f}s"
        f"  (replay {timings['replay']:.1f}s, render {timings['frames']:.1f}s,"
        f" audio {timings['audio']:.1f}s, encode {timings['encode']:.1f}s,"
        f" QC/package {timings['qc']:.1f}s)"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="produce, check and package a whole curated batch of Shorts"
    )
    parser.add_argument("manifest", help="curated batch manifest to produce")
    parser.add_argument("--limit", type=int, default=None, help="first N items only")
    parser.add_argument("--output-root", default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--godot", default=None, help="path to the Godot 4 executable")
    parser.add_argument("--ffmpeg", default=None, help="path to the FFmpeg executable")
    parser.add_argument("--ffprobe", default=None, help="path to the ffprobe executable")
    parser.add_argument("--crf", type=int, default=encode.DEFAULT_SPEC.crf)
    parser.add_argument("--preset", default=encode.DEFAULT_SPEC.preset)
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace a delivered video whose bytes differ, reviewed or not",
    )
    parser.add_argument(
        "--stop-on-failure",
        action="store_true",
        help="give up at the first failing item instead of finishing the batch",
    )
    parser.add_argument(
        "--no-contact-sheet", dest="contact_sheet", action="store_false"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = encode.EncodeSpec(crf=args.crf, preset=args.preset)

    try:
        manifest, batch_dir, batch_id = load_batch(args.manifest)
        ffmpeg = encode.find_ffmpeg(args.ffmpeg)
        ffprobe = encode.find_ffprobe(args.ffprobe, ffmpeg)
    except (ProductionError, encode.EncodeError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    # Godot is only needed if something actually has to be rendered, so a
    # resume run on a machine without it still works.
    try:
        godot = render_replay.find_godot(args.godot)
    except render_replay.RenderError:
        godot = ""

    items = manifest["items"][: args.limit] if args.limit else manifest["items"]
    production_dir = os.path.join(
        args.output_root, delivery.production_dir_name(batch_id)
    )
    render_root = os.path.join(args.output_root, f"render_{batch_id}")

    print(f"batch:      {delivery.relative_to(args.manifest, PROJECT_ROOT)}")
    print(f"items:      {len(items)} of {len(manifest['items'])}")
    print(f"work:       {delivery.relative_to(render_root, PROJECT_ROOT)}")
    print(f"delivery:   {delivery.relative_to(production_dir, PROJECT_ROOT)}")
    print(f"godot:      {godot or '(not found - reuse only)'}")
    print(f"ffmpeg:     {ffmpeg}")
    print(f"audio:      soundtrack v{SOUNDTRACK_VERSION}, QC v{qc.QC_VERSION}")

    timings = {name: 0.0 for name in STAGES}
    started = time.perf_counter()
    records: list[dict] = []
    entries: list[dict] = []
    render_dirs: dict[int, str] = {}
    failures: list[str] = []

    for entry in items:
        index, seed = int(entry["index"]), int(entry["seed"])
        name = delivery.item_dir_name(index, seed)
        render_dir = os.path.join(render_root, name)
        item_dir = os.path.join(production_dir, name)
        render_dirs[index] = render_dir
        try:
            record = produce_item(
                entry,
                batch_id=batch_id,
                batch_dir=batch_dir,
                render_dir=render_dir,
                delivery_dir=item_dir,
                godot=godot,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                spec=spec,
                force=args.force,
                timings=timings,
            )
        except (
            ProductionError,
            delivery.DeliveryError,
            qc.QcError,
            encode.EncodeError,
            encode_short.ShortError,
            render_replay.RenderError,
            wav_io.WavError,
            png_frames.PngError,
            OSError,
        ) as error:
            print(f"  FAILED: {error}", file=sys.stderr)
            failures.append(f"{index:03d} seed {seed}: {error}")
            # The delivery folder must not be left holding a record that
            # says this item passed, and the batch summary must not simply
            # lose it. Whatever a person already decided about it is kept.
            status, note = qc.review_of(
                delivery.read_json(os.path.join(item_dir, qc.QC_NAME))
            )
            record = qc.with_review(
                qc.failure_record(entry, batch_id, [str(error)]), status, note
            )
            delivery.write_json(os.path.join(item_dir, qc.QC_NAME), record)
            records.append(record)
            entries.append(
                delivery.manifest_item(
                    record,
                    video=f"{name}/{encode.SHORT_NAME}",
                    qc=f"{name}/{qc.QC_NAME}",
                )
            )
            if args.stop_on_failure:
                break
            continue

        records.append(record)
        entries.append(
            delivery.manifest_item(
                record,
                video=f"{name}/{encode.SHORT_NAME}",
                qc=f"{name}/{qc.QC_NAME}",
            )
        )

    elapsed = time.perf_counter() - started

    production = delivery.production_manifest(
        batch_id,
        delivery.relative_to(args.manifest, PROJECT_ROOT),
        entries,
    )
    delivery.write_json(
        os.path.join(production_dir, delivery.PRODUCTION_MANIFEST_NAME), production
    )
    if args.contact_sheet and records:
        sheet = draw_contact_sheet(
            records,
            render_dirs,
            os.path.join(production_dir, delivery.CONTACT_SHEET_NAME),
        )
        if sheet:
            print(f"\ncontact sheet: {delivery.relative_to(sheet, PROJECT_ROOT)}")

    report(production, elapsed, timings)

    if failures:
        print(f"\n{len(failures)} of {len(items)} items failed:", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
    failed = production["summary"]["automated_fail"]
    if failed:
        print(f"{failed} item(s) failed automated QC", file=sys.stderr)
    return 1 if (failures or failed) else 0


if __name__ == "__main__":
    raise SystemExit(main())
