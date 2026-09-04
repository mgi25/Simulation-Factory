"""What a finished Short has to prove, and the record that proves it.

Split deliberately in two. Gathering facts touches the filesystem and calls
ffprobe; judging them is a pure function of the facts. That is what makes
every rule below testable without a renderer, an encoder or a batch of
video, and it is why the rules live here rather than inside a CLI.

The judgement is a hard pass or fail. There is no "mostly fine": a Short
with 1426 of 1427 frames is not a Short, and a sequence whose aggregate hash
does not match the one recorded beside it is not the sequence that was
approved. Loudness is the one measurement that can merely warn, because a
Short being a decibel quieter than preferred is a thing to know about rather
than a reason to throw away four minutes of rendering - and because this
phase measures audio, it does not retune it.
"""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Any

# The QC record's own schema version. Nothing to do with the replay format
# (v6), the batch manifest (v1), the render manifest (v1) or the soundtrack
# (v1): this describes a verdict about one finished video.
QC_VERSION = 1
QC_NAME = "qc.json"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"

# The second layer. Automated QC cannot tell whether a battle is dull, so a
# person does, and their answer is never written by a machine.
REVIEW_PENDING = "pending"
REVIEW_APPROVED = "approved"
REVIEW_REJECTED = "rejected"
REVIEW_STATUSES = (REVIEW_PENDING, REVIEW_APPROVED, REVIEW_REJECTED)

# Loudness expectations, from the Phase 6B.1 mastering that produced them.
# The preferred band is a warning: batch consistency matters more than any
# single file, and remastering one Short to hit a number would make it the
# odd one out. The true peak is not a preference - a file above it can clip
# on playback, and nothing downstream will fix that.
LOUDNESS_PREFERRED_MIN = -22.0
LOUDNESS_PREFERRED_MAX = -18.0
TRUE_PEAK_MAX_DBFS = -1.0
# How far from the batch's own middle a phone-band measurement has to sit
# before it is worth mentioning. Phase 6B.1 closed this spread to about a
# decibel, so anything near this is a regression rather than a quirk.
PHONE_BAND_OUTLIER_DB = 4.0

# The production format, restated here as the thing QC checks against. These
# are the same numbers `rendering.encode` builds the command from; QC asserts
# them against what the finished file actually reports.
EXPECTED_WIDTH = 1080
EXPECTED_HEIGHT = 1920
EXPECTED_FPS = 60
EXPECTED_SAMPLE_RATE = 48000
EXPECTED_CHANNELS = 2
SAMPLES_PER_FRAME = EXPECTED_SAMPLE_RATE // EXPECTED_FPS

# How a frame contributes to the sequence hash. File bytes rather than
# decoded pixels: Phase 6A established that Godot's PNG encoder writes no
# timestamps and no run ids, so the file is already a stable identity, and
# hashing two million pixels per frame would cost a minute and a half per
# Short to learn the same thing. Recorded in the QC record so that if this
# ever changes, the change is visible rather than silent.
SEQUENCE_METHOD = "file-sha256"


class QcError(RuntimeError):
    """A finished Short could not be checked at all."""


# --- the aggregate identity of a rendered sequence -------------------------


def sequence_digest(
    frames_dir: str,
    frame_count: int,
    digest_of=None,
    *,
    frame_filename=None,
) -> str:
    """One hash standing for a whole frame sequence.

    Each frame contributes its filename and its digest, in index order, so
    the result changes if a frame goes missing, if a frame's contents change,
    or if two frames swap places. Nothing about the filesystem goes into it -
    no modification times, no sizes, no directory order - so the same render
    hashes the same on any machine.

    `digest_of` and `frame_filename` are injectable for tests; production
    always passes the real ones.
    """
    import os

    from rendering import png_frames
    from rendering.render_plan import frame_filename as real_name

    naming = frame_filename or real_name
    hashing = digest_of or png_frames.file_digest

    if frame_count < 0:
        raise QcError(f"frame count cannot be negative: {frame_count}")

    digest = hashlib.sha256()
    digest.update(f"{SEQUENCE_METHOD}:{frame_count}\n".encode("utf-8"))
    for index in range(frame_count):
        name = naming(index)
        path = os.path.join(frames_dir, name)
        if not os.path.isfile(path):
            raise QcError(f"missing frame {name} in {frames_dir}")
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashing(path).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def visual_checkpoints(frame_count: int, gameplay_frames: int) -> dict[str, int]:
    """The frames a sanity check looks at, and what each one is for.

    Eight places where a different kind of failure would show up: an opening
    that never drew, an intro that stayed black, three points across the
    battle, the last gameplay moment, the result panel, and the final held
    frame. Ordered, so the report reads like the video plays.
    """
    if frame_count <= 0 or gameplay_frames <= 0:
        raise QcError(
            f"cannot pick checkpoints in {frame_count} frames"
            f" ({gameplay_frames} gameplay)"
        )
    gameplay = min(gameplay_frames, frame_count)
    post_roll = frame_count - gameplay
    last_gameplay = gameplay - 1
    checkpoints = {
        "first": 0,
        "intro end": min(last_gameplay, gameplay // 20),
        "25%": min(last_gameplay, gameplay // 4),
        "50%": min(last_gameplay, gameplay // 2),
        "75%": min(last_gameplay, (gameplay * 3) // 4),
        "final gameplay": last_gameplay,
        "result panel": min(frame_count - 1, gameplay + post_roll // 2),
        "last": frame_count - 1,
    }
    return checkpoints


def moov_before_mdat(path: str) -> bool:
    """Whether an MP4's index sits in front of its data - "fast start".

    Walks the top-level atoms rather than searching for a byte pattern, so a
    stray "mdat" inside compressed video cannot be mistaken for the real one.
    A file whose data comes first still plays, but a viewer has to fetch the
    end of it before it can begin, which on a phone is the difference between
    a Short starting and a Short buffering.
    """
    with open(path, "rb") as handle:
        offset = 0
        while True:
            head = handle.read(8)
            if len(head) < 8:
                return False
            size, kind = struct.unpack(">I4s", head)
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:
                extended = handle.read(8)
                if len(extended) < 8:
                    return False
                size = struct.unpack(">Q", extended)[0]
            elif size == 0:
                # Runs to the end of the file, so nothing follows it.
                return False
            if size < 8:
                return False
            offset += size
            handle.seek(offset)


# --- the facts -------------------------------------------------------------


@dataclass(frozen=True)
class ReplayFacts:
    """What the replay on disk turned out to be."""

    exists: bool = False
    version: int = 0
    seed: int = 0
    powers: tuple[str, ...] = ()
    winner_id: int | None = None
    is_draw: bool = False
    duration: float = 0.0
    sha256: str = ""


@dataclass(frozen=True)
class RenderFacts:
    """What the frame sequence turned out to be."""

    exists: bool = False
    render_version: int = 0
    width: int = 0
    height: int = 0
    fps: int = 0
    frame_count: int = 0
    gameplay_frames: int = 0
    post_roll_frames: int = 0
    replay_sha256: str = ""
    sequence_sha256: str = ""
    sequence_problems: tuple[str, ...] = ()
    blank_frames: tuple[str, ...] = ()
    recorded_sequence_sha256: str | None = None


@dataclass(frozen=True)
class AudioFacts:
    """What the PCM master turned out to be."""

    exists: bool = False
    audio_version: int = 0
    sample_rate: int = 0
    channels: int = 0
    bit_depth: int = 0
    samples: int = 0
    pcm_sha256: str = ""
    replay_sha256: str = ""
    peak: float = 0.0
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class VideoFacts:
    """What the finished MP4 turned out to be."""

    exists: bool = False
    sha256: str = ""
    size: int = 0
    codec: str = ""
    profile: str = ""
    width: int = 0
    height: int = 0
    pix_fmt: str = ""
    frame_rate: str = ""
    field_order: str | None = None
    frames: int | None = None
    duration: float | None = None
    audio_codec: str = ""
    audio_profile: str = ""
    audio_rate: int = 0
    audio_channels: int = 0
    audio_duration: float | None = None
    decoded_samples: int = 0
    faststart: bool = False
    problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class LoudnessFacts:
    """What the finished MP4 measured. Reported, never acted on."""

    integrated_lufs: float | None = None
    true_peak_dbfs: float | None = None
    range_lu: float | None = None
    band_lufs: float | None = None


@dataclass(frozen=True)
class Evidence:
    """Everything gathered about one item, ready to be judged."""

    item: dict[str, Any]
    replay: ReplayFacts = field(default_factory=ReplayFacts)
    render: RenderFacts = field(default_factory=RenderFacts)
    audio: AudioFacts = field(default_factory=AudioFacts)
    video: VideoFacts = field(default_factory=VideoFacts)
    loudness: LoudnessFacts = field(default_factory=LoudnessFacts)


# --- the judgement ---------------------------------------------------------


def _expected(item: dict[str, Any]) -> dict[str, Any]:
    """What the manifest says this battle is."""
    return {
        "seed": int(item.get("seed", -1)),
        "powers": tuple(item.get("powers") or ()),
        "winner_id": item.get("winner_id"),
        "duration": round(float(item.get("duration", 0.0)), 3),
    }


def replay_problems(item: dict[str, Any], facts: ReplayFacts) -> list[str]:
    """Whether the replay is the battle the manifest selected.

    The replay is the frozen creative source: everything downstream is a
    function of it, so if it is not the battle that was curated then the
    score, the matchup and the reason it was picked all describe something
    else. Checked rather than assumed on every run.
    """
    if not facts.exists:
        return ["replay is missing"]

    problems: list[str] = []
    from replay.exporter import REPLAY_VERSION

    if facts.version != REPLAY_VERSION:
        problems.append(
            f"replay is version {facts.version}, production plays v{REPLAY_VERSION}"
        )
    expected = _expected(item)
    if facts.seed != expected["seed"]:
        problems.append(f"replay seed {facts.seed}, manifest says {expected['seed']}")
    if expected["powers"] and facts.powers != expected["powers"]:
        problems.append(
            f"replay powers {list(facts.powers)}, manifest says {list(expected['powers'])}"
        )
    if facts.winner_id != expected["winner_id"]:
        problems.append(
            f"replay winner {facts.winner_id}, manifest says {expected['winner_id']}"
        )
    if round(facts.duration, 3) != expected["duration"]:
        problems.append(
            f"replay runs {facts.duration:.3f}s,"
            f" manifest says {expected['duration']:.3f}s"
        )
    if not facts.sha256:
        problems.append("replay was never hashed")
    return problems


def render_problems(facts: RenderFacts, replay: ReplayFacts) -> list[str]:
    """Whether the sequence is a complete 1080x1920 render of that replay."""
    if not facts.exists:
        return ["frame sequence is missing"]

    problems: list[str] = []
    from rendering.render_plan import RENDER_FORMAT_VERSION

    if facts.render_version != RENDER_FORMAT_VERSION:
        problems.append(
            f"render manifest is version {facts.render_version},"
            f" production reads v{RENDER_FORMAT_VERSION}"
        )
    if (facts.width, facts.height) != (EXPECTED_WIDTH, EXPECTED_HEIGHT):
        problems.append(
            f"rendered at {facts.width}x{facts.height},"
            f" production is {EXPECTED_WIDTH}x{EXPECTED_HEIGHT}"
        )
    if facts.fps != EXPECTED_FPS:
        problems.append(f"rendered at {facts.fps} fps, production is {EXPECTED_FPS}")
    if facts.frame_count <= 0:
        problems.append(f"render claims {facts.frame_count} frames")
    if facts.gameplay_frames <= 0 or facts.gameplay_frames > facts.frame_count:
        problems.append(
            f"{facts.gameplay_frames} gameplay frames of {facts.frame_count}"
            " makes no sense"
        )
    problems.extend(facts.sequence_problems)
    if not facts.sequence_sha256:
        problems.append("frame sequence was never hashed")
    if (
        facts.recorded_sequence_sha256
        and facts.sequence_sha256
        and facts.recorded_sequence_sha256 != facts.sequence_sha256
    ):
        problems.append(
            "frame sequence has changed since it was last checked"
            f" ({facts.sequence_sha256[:12]} now,"
            f" {facts.recorded_sequence_sha256[:12]} then)"
        )
    if replay.exists and facts.replay_sha256 and facts.replay_sha256 != replay.sha256:
        problems.append(
            "the frames were rendered from a different replay"
            f" ({facts.replay_sha256[:12]} then, {replay.sha256[:12]} now)"
        )
    for name in facts.blank_frames:
        problems.append(f"{name} has nothing drawn in it")
    return problems


def audio_problems(
    facts: AudioFacts, render: RenderFacts, replay: ReplayFacts
) -> list[str]:
    """Whether the soundtrack is exactly as long as the pictures."""
    if not facts.exists:
        return ["soundtrack is missing"]

    problems: list[str] = []
    from audio.soundtrack import SOUNDTRACK_VERSION

    if facts.audio_version != SOUNDTRACK_VERSION:
        problems.append(
            f"soundtrack is version {facts.audio_version},"
            f" production is v{SOUNDTRACK_VERSION}"
        )
    if facts.sample_rate != EXPECTED_SAMPLE_RATE:
        problems.append(
            f"audio is {facts.sample_rate} Hz, production is {EXPECTED_SAMPLE_RATE}"
        )
    if facts.channels != EXPECTED_CHANNELS:
        problems.append(
            f"audio has {facts.channels} channels, production is {EXPECTED_CHANNELS}"
        )
    if render.frame_count > 0:
        expected = render.frame_count * SAMPLES_PER_FRAME
        if facts.samples != expected:
            problems.append(
                f"audio is {facts.samples} samples per channel, expected exactly"
                f" {render.frame_count} x {SAMPLES_PER_FRAME} = {expected}"
            )
    if not facts.pcm_sha256:
        problems.append("audio was never hashed")
    if replay.exists and facts.replay_sha256 and facts.replay_sha256 != replay.sha256:
        problems.append(
            "the soundtrack was built from a different replay"
            f" ({facts.replay_sha256[:12]} then, {replay.sha256[:12]} now)"
        )
    problems.extend(facts.problems)
    return problems


def video_problems(facts: VideoFacts) -> list[str]:
    """Whether the MP4 is the production format, plus fast start."""
    if not facts.exists:
        return ["short.mp4 is missing"]
    problems = list(facts.problems)
    if not facts.faststart:
        problems.append("the moov atom is behind the media data; fast start is off")
    if not facts.sha256:
        problems.append("the finished video was never hashed")
    return problems


def loudness_problems(facts: LoudnessFacts) -> list[str]:
    """The one hard audio gate: a peak that could clip on playback."""
    problems: list[str] = []
    if facts.true_peak_dbfs is None:
        problems.append("true peak was not measured")
    elif facts.true_peak_dbfs > TRUE_PEAK_MAX_DBFS:
        problems.append(
            f"true peak is {facts.true_peak_dbfs:+.1f} dBFS,"
            f" above the {TRUE_PEAK_MAX_DBFS:+.1f} dBFS limit"
        )
    return problems


def loudness_warnings(
    facts: LoudnessFacts, band_reference: float | None = None
) -> list[str]:
    """Loudness worth knowing about, which is not the same as worth failing.

    Phase 6C measures audio and does not retune it. Remastering one Short to
    pull it inside a preferred band would make it the loudest or quietest
    thing in the batch, which is a worse problem than the one it solved.
    """
    warnings: list[str] = []
    if facts.integrated_lufs is None:
        warnings.append("integrated loudness was not measured")
    elif not LOUDNESS_PREFERRED_MIN <= facts.integrated_lufs <= LOUDNESS_PREFERRED_MAX:
        warnings.append(
            f"integrated loudness {facts.integrated_lufs:.1f} LUFS is outside the"
            f" preferred {LOUDNESS_PREFERRED_MIN:.0f} to"
            f" {LOUDNESS_PREFERRED_MAX:.0f} LUFS band"
        )
    if (
        band_reference is not None
        and facts.band_lufs is not None
        and abs(facts.band_lufs - band_reference) > PHONE_BAND_OUTLIER_DB
    ):
        warnings.append(
            f"phone-band loudness {facts.band_lufs:.1f} LUFS is"
            f" {abs(facts.band_lufs - band_reference):.1f} dB from the batch's"
            f" {band_reference:.1f} LUFS"
        )
    return warnings


def evaluate(
    evidence: Evidence, band_reference: float | None = None
) -> tuple[list[str], list[str]]:
    """Every reason this item fails, and everything else worth mentioning.

    Ordered by where in the pipeline the problem is, so the first line of a
    failure is the earliest thing that went wrong rather than the loudest.
    """
    problems = replay_problems(evidence.item, evidence.replay)
    problems += render_problems(evidence.render, evidence.replay)
    problems += audio_problems(evidence.audio, evidence.render, evidence.replay)
    problems += video_problems(evidence.video)
    problems += loudness_problems(evidence.loudness)
    return problems, loudness_warnings(evidence.loudness, band_reference)


# --- the record ------------------------------------------------------------


def qc_record(
    evidence: Evidence,
    *,
    batch_id: str,
    problems: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    """The deterministic half of `qc.json`.

    A pure function of the facts: no timestamps, no machine name, no
    absolute path, no run id. Two runs over the same finished Short produce
    the same bytes, which is what makes it worth hashing a batch against.

    The chain from the batch manifest to the finished file is spelled out
    here on purpose - manifest item, replay hash, render identity, PCM hash,
    video hash - so a question about any delivered Short can be answered from
    the record beside it rather than by re-deriving the pipeline.
    """
    item = evidence.item
    render, audio, video, level = (
        evidence.render,
        evidence.audio,
        evidence.video,
        evidence.loudness,
    )
    return {
        "version": QC_VERSION,
        "status": STATUS_FAIL if problems else STATUS_PASS,
        "problems": list(problems),
        "warnings": list(warnings),
        "source": {
            "batch_id": batch_id,
            "index": int(item.get("index", 0)),
            "seed": int(item.get("seed", 0)),
            "label": item.get("label", ""),
            "powers": list(item.get("powers") or ()),
            "arena_mode": item.get("arena_mode", ""),
            "layout_id": item.get("layout_id", ""),
            "score": item.get("score"),
            "duration": item.get("duration"),
        },
        "replay": {
            "version": evidence.replay.version,
            "seed": evidence.replay.seed,
            "powers": list(evidence.replay.powers),
            "winner_id": evidence.replay.winner_id,
            "is_draw": evidence.replay.is_draw,
            "duration": round(evidence.replay.duration, 3),
            "sha256": evidence.replay.sha256,
        },
        "render": {
            "version": render.render_version,
            "width": render.width,
            "height": render.height,
            "fps": render.fps,
            "frames": render.frame_count,
            "gameplay_frames": render.gameplay_frames,
            "post_roll_frames": render.post_roll_frames,
            "sequence_method": SEQUENCE_METHOD,
            "sequence_sha256": render.sequence_sha256,
            "replay_sha256": render.replay_sha256,
        },
        "audio": {
            "version": audio.audio_version,
            "sample_rate": audio.sample_rate,
            "channels": audio.channels,
            "bit_depth": audio.bit_depth,
            "samples": audio.samples,
            "samples_per_frame": SAMPLES_PER_FRAME,
            "pcm_sha256": audio.pcm_sha256,
            "peak": round(audio.peak, 6),
            "integrated_lufs": level.integrated_lufs,
            "true_peak_dbfs": level.true_peak_dbfs,
            "loudness_range_lu": level.range_lu,
            "phone_band_lufs": level.band_lufs,
        },
        "video": {
            "sha256": video.sha256,
            "bytes": video.size,
            "codec": video.codec,
            "profile": video.profile,
            "width": video.width,
            "height": video.height,
            "pix_fmt": video.pix_fmt,
            "frame_rate": video.frame_rate,
            "frames": video.frames,
            "duration": None if video.duration is None else round(video.duration, 4),
            "audio_codec": video.audio_codec,
            "audio_profile": video.audio_profile,
            "audio_rate": video.audio_rate,
            "audio_channels": video.audio_channels,
            "audio_duration": (
                None if video.audio_duration is None else round(video.audio_duration, 4)
            ),
            "decoded_samples": video.decoded_samples,
            "faststart": video.faststart,
        },
    }


def failure_record(
    item: dict[str, Any], batch_id: str, problems: list[str]
) -> dict[str, Any]:
    """A record for an item that could not be produced at all.

    An item can fail before there is anything to describe - a replay that is
    not the battle the manifest selected stops production before a frame is
    read. It still gets a record, because the alternative is worse: the
    previous run's record stays on disk beside the video saying `pass`, and
    the delivery folder ends up disagreeing with itself about a Short a
    person is about to review.
    """
    return qc_record(
        Evidence(item=item), batch_id=batch_id, problems=problems, warnings=[]
    )


def with_review(
    record: dict[str, Any],
    status: str = REVIEW_PENDING,
    note: str = "",
) -> dict[str, Any]:
    """The record plus the half a person owns.

    Kept separate from `qc_record` so the automated half stays a pure
    function of the pipeline and can be compared between runs, while the
    review answer survives them.
    """
    if status not in REVIEW_STATUSES:
        raise QcError(
            f"unknown review status {status!r}; expected one of {REVIEW_STATUSES}"
        )
    merged = dict(record)
    merged["review_status"] = status
    merged["review_note"] = note
    return merged


def review_of(record: dict[str, Any] | None) -> tuple[str, str]:
    """The review answer already recorded, or `pending` if there is none."""
    if not record:
        return REVIEW_PENDING, ""
    status = record.get("review_status", REVIEW_PENDING)
    if status not in REVIEW_STATUSES:
        status = REVIEW_PENDING
    return status, str(record.get("review_note", "") or "")
