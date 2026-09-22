"""The production identity for Category 3 Test #2: the shell escape master.

Phase 4's deliverable is a file somebody uploads, and the claim attached to it
is that the repository can make that file again. This module is where that
claim lives: every dial the upload depends on - the seed, the score, the
composition, the hook, the frame, the encoder - as one frozen object with a
digest over all of it, so "the same master" is checkable rather than
remembered.

It is deliberately the same shape as `tile_production.py`, which did this job
for Test #1. Two productions that answer the same questions in the same order
can be compared; two that invent their own vocabularies cannot.

## What is in here and what is deliberately not

In: things that change the bytes of the delivered file.

Out: anything to do with publishing - no title, description, tags or
thumbnail. Those belong to whatever uploads the file, and a video carrying its
own metadata cannot be re-titled without a re-encode.

## Why 60 fps here and 30 fps in Test #1

Test #1's tiles are static until they are hit, so 30 fps costs it nothing.
Test #2's six shells rotate continuously and the ball never stops, so every
frame is a different picture. Phase 3 measured the full-quality 60 fps profile
and every cue class landed inside one frame at that rate, so 60 is both the
better picture and the already-proven timing.

## The mastering decision, stated so it can be argued with

There is no limiter and no compressor, and `master_gain_db` is 0.0. That is
not an oversight. The refined-hybrid score for seed 9589 renders at -4.53 dBTP
with no clipped samples, which is already 3.5 dB below the repository's
`-1.0 dBTP` delivery ceiling. Adding gain to approach that ceiling would buy
loudness the brief explicitly did not ask for and would spend the dynamic
range - 6.03 LU - that the whole six-register design exists to produce. So the
ceiling is enforced as a *gate on the decoded delivery file*, exactly as
`tile_phase6_cli` enforces it, rather than as a target to normalise toward.

## The reproduction claim, stated precisely

Given this repository at the recorded commit and `PRODUCTION` unchanged:

* the simulation is frozen and its playback document is already recorded and
  digested by Phase 1 - Phase 4 copies it and never re-simulates;
* the frames are a function of that document, the composition constants and
  the hook;
* the audio is a function of that document and the named score config;
* the delivery file is a function of the frames, the audio and the encoder
  settings below.

The first three are exactly reproducible and are digested. The fourth is not
claimed to be bit-exact - x264 is free to differ between builds - so what is
checked is the *decoded* result: duration, frame count, sample count, true
peak, clipping and synchronisation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

from satisfying import shell_av, shell_score, shell_visual, tile_safe_area

__all__ = [
    "PRODUCTION_FORMAT",
    "ProductionError",
    "ProductionConfig",
    "PRODUCTION",
    "DELIVERY_TRUE_PEAK_DBTP",
    "rendered_frame_count",
    "identity",
]

PRODUCTION_FORMAT = 1

# The repository's established delivery ceiling, taken from Test #1's
# `tile_phase6_cli.DELIVERY_TRUE_PEAK_DBTP` rather than invented here. It is a
# gate on the decoded delivered file, not a normalisation target.
DELIVERY_TRUE_PEAK_DBTP = -1.0

# Phase 3's decision, restated where the production can enforce it.
PRIMARY_SEED = 9589
BACKUP_SEED = 11929


class ProductionError(RuntimeError):
    """A production configuration that cannot be delivered."""


def rendered_frame_count(document: dict[str, Any], fps: float) -> int:
    """How many frames the Godot driver writes for this document.

    Mirrored from `shell_escape_render.gd`, which renders frame indices 0 to
    `floor(render_duration * fps)` inclusive, where `render_duration` is the
    playback duration plus the release and the end hold. Deriving it here
    rather than counting PNGs is what lets the QC say a render is *complete*
    rather than merely non-empty.
    """
    render_duration = (
        float(document["summary"]["duration"])
        + shell_visual.RELEASE_SECONDS
        + shell_visual.END_HOLD_SECONDS
    )
    return int(math.floor(render_duration * fps)) + 1


@dataclass(frozen=True)
class ProductionConfig:
    """Everything that decides the bytes of the upload."""

    # --- what is being made ----------------------------------------------
    name: str = "category3_test2_seed9589"
    seed: int = PRIMARY_SEED
    # Kept reproducible and named, but not rendered: Phase 4 delivers one
    # master. `shell_production_cli master --seed 11929` is what makes the
    # backup, and it is deliberately not run unless 9589 fails QC.
    backup_seed: int = BACKUP_SEED

    # --- the picture ------------------------------------------------------
    width: int = 1080
    height: int = 1920
    fps: float = 60.0
    hook: str = "CAN THE BALL ESCAPE?"

    # --- the sound --------------------------------------------------------
    audio: str = "refined_hybrid"
    # No limiter, no compressor, no normalisation. See the module docstring.
    master_gain_db: float = 0.0

    # --- how the safe area is judged --------------------------------------
    safe_area: str = "shorts_conservative"

    # --- the encode -------------------------------------------------------
    # CRF 17 / `slow` is the repository's production setting, carried from
    # Test #1's Phase 6 master and from this test's own Phase 3 full-quality
    # profile, so the delivery file is encoded exactly as the proof was.
    video_codec: str = "libx264"
    crf: int = 17
    preset: str = "slow"
    pixel_format: str = "yuv420p"
    colour_primaries: str = "bt709"
    # sRGB, not bt709, for the reason Test #1 recorded: Godot writes sRGB PNGs
    # and ffmpeg propagates the input transfer characteristic, so the stream
    # tag comes back `iec61966-2-1` whatever is requested. Recording bt709
    # here would describe a file that does not exist.
    colour_trc: str = "iec61966-2-1"
    colour_space: str = "bt709"
    # The archival master: same picture, visually lossless, audio carried as
    # PCM so nothing is encoded twice. The delivery file is built from the
    # frames and the WAV directly and *not* from this, so keeping an archive
    # costs no generation loss anywhere.
    archive_crf: int = 12
    archive_audio: str = "pcm_s24le"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48_000
    # A Short is streamed, so the moov atom goes first.
    faststart: bool = True
    # The picture stops at the last rendered frame; the score keeps decaying
    # for its final resolution. Cloning that frame to the score end is what
    # Phase 3 measured and is the only padding allowed.
    final_frame_padding: str = "clone_to_audio_end"

    def __post_init__(self) -> None:
        if self.seed != PRIMARY_SEED:
            raise ProductionError(
                f"Phase 3 selected seed {PRIMARY_SEED}; a different production "
                f"seed needs a recorded decision, not a default"
            )
        if self.audio not in shell_score.CONFIGS:
            raise ProductionError(
                f"unknown audio configuration {self.audio!r}; "
                f"known: {sorted(shell_score.CONFIGS)}"
            )
        if self.audio != "refined_hybrid":
            raise ProductionError("the production score is locked to refined_hybrid")
        if self.hook != shell_av.CONFIG.hook:
            raise ProductionError(
                "the production hook must stay the one the frame is composed "
                f"around: {shell_av.CONFIG.hook!r}"
            )
        if self.safe_area not in tile_safe_area.SAFE_AREAS:
            raise ProductionError(
                f"unknown safe area {self.safe_area!r}; "
                f"known: {sorted(tile_safe_area.SAFE_AREAS)}"
            )
        if self.width <= 0 or self.height <= 0:
            raise ProductionError("the frame must have a positive size")
        if self.height <= self.width:
            raise ProductionError(
                "the delivery frame is vertical; height must exceed width"
            )
        if (self.width, self.height) != (shell_visual.FRAME_WIDTH,
                                         shell_visual.FRAME_HEIGHT):
            raise ProductionError(
                "the delivery frame must match the composed visual frame "
                f"{shell_visual.FRAME_WIDTH}x{shell_visual.FRAME_HEIGHT}"
            )
        if self.fps <= 0.0:
            raise ProductionError("fps must be positive")
        if self.fps != float(shell_visual.RENDER_FPS):
            raise ProductionError(
                "the production frame rate must match the rate the visual "
                f"layer renders and was timed at: {shell_visual.RENDER_FPS}"
            )
        if not 0 <= self.crf <= 51 or not 0 <= self.archive_crf <= 51:
            raise ProductionError("a CRF outside 0-51 is not an x264 setting")
        if self.archive_crf > self.crf:
            raise ProductionError(
                "the archive would be lower quality than the delivery file, "
                "which is the wrong way round for an archive"
            )
        if self.audio_sample_rate != 48_000:
            raise ProductionError("the selected score is mastered at 48 kHz")
        if self.master_gain_db != 0.0:
            raise ProductionError(
                "the production master applies no gain; changing this needs a "
                "recorded mastering decision, because the score's dynamic "
                "range is the point of the six-register design"
            )
        if self.final_frame_padding != "clone_to_audio_end":
            raise ProductionError(
                "the only padding Phase 3 measured is the final frame cloned "
                "to the score end"
            )

    @property
    def audio_config(self) -> shell_score.AudioConfig:
        return shell_score.named_config(self.audio)

    @property
    def safe_area_config(self) -> tile_safe_area.SafeAreaConfig:
        """The safe area at *this production's* frame rate.

        The rate matters: the hidden-ball sweep samples the ball once per
        frame, so a report left at the 30 fps default would be checking a
        picture the upload does not contain.
        """
        return tile_safe_area.named_safe_area(self.safe_area, fps=self.fps)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# The locked production. Phase 4's whole job is that this object and the
# repository at its commit are enough to make the upload again.
PRODUCTION = ProductionConfig()


def identity(document: dict[str, Any] | None = None,
             config: ProductionConfig = PRODUCTION) -> dict[str, Any]:
    """The production identity, as the block that goes beside the master.

    Layered on purpose, the same way Test #1 layers it: `production` moves when
    a delivery dial moves, `audio` when a sound dial moves, `composition` when
    the frame moves, `encode` when the encoder moves, and `run` when the
    physics moves. A reader comparing two of these can say which layer changed;
    one digest over everything flattened together could only say that something
    had.
    """
    out: dict[str, Any] = {
        "format": PRODUCTION_FORMAT,
        "production": {
            "name": config.name,
            "fingerprint": config.fingerprint(),
            "seed": config.seed,
            "backup_seed": config.backup_seed,
            "hook": config.hook,
            "frame": [config.width, config.height],
            "fps": config.fps,
        },
        "simulation": {
            "schema_version": shell_visual.EXPECTED_SCHEMA_VERSION,
            "config_digest": shell_visual.EXPECTED_CONFIG_DIGEST,
        },
        "audio": {
            "config": config.audio,
            "fingerprint": config.audio_config.fingerprint(),
            "sample_rate": config.audio_config.sample_rate,
            "master_gain_db": config.master_gain_db,
            "limiter": False,
            "compressor": False,
            "delivery_true_peak_ceiling_dbtp": DELIVERY_TRUE_PEAK_DBTP,
        },
        "composition": {
            "arena_width_fraction": shell_visual.ARENA_WIDTH_FRACTION,
            "arena_centre": [shell_visual.ARENA_CENTRE_X_FRACTION,
                             shell_visual.ARENA_CENTRE_Y_FRACTION],
            "ball_draw_scale": shell_visual.BALL_DRAW_SCALE,
            "trail_seconds": shell_visual.TRAIL_SECONDS,
            "release_seconds": shell_visual.RELEASE_SECONDS,
            "end_hold_seconds": shell_visual.END_HOLD_SECONDS,
            "visual_config_digest": shell_visual.render_config_digest(),
        },
        "safe_area": {
            "config": config.safe_area,
            "fingerprint": config.safe_area_config.fingerprint(),
        },
        "encode": {
            "video": config.video_codec,
            "crf": config.crf,
            "preset": config.preset,
            "pixel_format": config.pixel_format,
            "colour": [config.colour_primaries, config.colour_trc,
                       config.colour_space],
            "audio": config.audio_codec,
            "audio_bitrate": config.audio_bitrate,
            "audio_sample_rate": config.audio_sample_rate,
            "faststart": config.faststart,
            "final_frame_padding": config.final_frame_padding,
            "archive_crf": config.archive_crf,
            "archive_audio": config.archive_audio,
        },
    }
    if document is not None:
        shell_av.validate_shared_document(document)
        if int(document["seed"]) != config.seed:
            raise ProductionError(
                f"playback seed {document['seed']} is not the production seed "
                f"{config.seed}"
            )
        summary = document["summary"]
        out["run"] = {
            "digest": str(document["digest"]),
            "seed": int(document["seed"]),
            "schema_version": str(document["schema_version"]),
            "config_digest": str(document["config_digest"]),
            "event_order_digest": shell_av.event_order_digest(document),
            "events": len(document["events"]),
            "duration_seconds": float(summary["duration"]),
            "rendered_frames": rendered_frame_count(document, config.fps),
        }
    return out


def production_digest(document: dict[str, Any] | None = None,
                      config: ProductionConfig = PRODUCTION) -> str:
    """One digest over the whole identity, for the line in the report."""
    blob = json.dumps(identity(document, config), sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
