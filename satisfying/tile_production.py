"""The production identity: one object that decides everything about the master.

Phase 6's deliverable is a file somebody uploads, and the claim attached to it
is that the repository can make that file again. This module is where that
claim lives. It holds every dial the upload depends on - the seed, the audio
configuration, the composition, the hook, the frame, the encoder - as one
frozen object with a digest over all of it, so "the same master" is a statement
that can be checked rather than remembered.

## What is in here and what is deliberately not

In: things that change the bytes of the delivered file.

Out: anything to do with publishing. No title, no description, no tags, no
thumbnail. Those belong to whatever uploads the file and they must not be baked
into the video - the brief is explicit about that, and it is also just true
that a video carrying its own metadata cannot be re-titled without a re-encode.

## Why the digest is over names rather than over values

`audio` is the string `"v3_hold_drone"`, not a copy of that configuration's
forty-odd fields. The fields are digested separately by
`AudioConfig.fingerprint()` and both digests appear in `identity()`. Keeping
them apart means a change to an audio dial moves the audio fingerprint and the
identity, while a change to, say, the CRF moves only the identity - so a
mismatch says *which layer* moved. A single digest over everything flattened
together could only say that something had.

## The reproduction claim, stated precisely

Given this repository at the recorded commit and `PRODUCTION` unchanged:

* the simulation is a function of `seed` and the locked config, and its
  `digest` is recorded;
* the playback document is a function of the simulation and `timing`;
* the frames are a function of the document, the composition constants and
  the hook;
* the audio is a function of the document and the `AudioConfig`;
* the delivered file is a function of the frames, the audio and the encoder
  settings below.

Every one of those five is checked by `tile_phase6_cli verify`, and the first
four are exactly reproducible. The fifth is not claimed to be bit-exact -
x264 is free to differ between builds - so what is checked there is the
*decoded* result: duration, frame count, sample count, true peak and
synchronisation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from satisfying import tile_readability, tile_safe_area, tile_score

__all__ = [
    "PRODUCTION_FORMAT",
    "ProductionError",
    "ProductionConfig",
    "PRODUCTION",
    "identity",
]

PRODUCTION_FORMAT = 1


class ProductionError(RuntimeError):
    """A production configuration that cannot be delivered."""


@dataclass(frozen=True)
class ProductionConfig:
    """Everything that decides the bytes of the upload."""

    # --- what is being made ----------------------------------------------
    name: str = "category3_test1_seed3530"
    seed: int = 3530
    # `tile_completion`'s timing preset. `standard` is the locked climax.
    timing: str = "standard"

    # --- the picture ------------------------------------------------------
    # 1080x1920 is the Shorts delivery frame; 30 fps is locked.
    width: int = 1080
    height: int = 1920
    fps: float = 30.0
    hook: str = "HIT EVERY TILE TO ESCAPE"
    trail: str = "temporal"
    show_counter: bool = True
    show_debug: bool = False

    # --- the sound --------------------------------------------------------
    # The confirmation hold is `drone`, which is what `v3_hold_drone` is.
    audio: str = "v3_hold_drone"

    # --- how the safe area was judged -------------------------------------
    safe_area: str = "shorts_conservative"

    # --- the encode -------------------------------------------------------
    # CRF 17 and `slow` are Phase 5's preview settings, kept because they were
    # measured rather than guessed and because a master is not the place to
    # start trading quality for time. The colour fields are written down so the
    # delivered stream's tags are a recorded decision rather than whatever the
    # encoder inferred - and one of them turned out to be exactly that; see
    # `colour_trc`.
    video_codec: str = "libx264"
    crf: int = 17
    preset: str = "slow"
    pixel_format: str = "yuv420p"
    colour_primaries: str = "bt709"
    # sRGB, not bt709, and that is deliberate rather than a leftover. The
    # frames are sRGB PNGs written by Godot, ffmpeg propagates the input's
    # transfer characteristic to the output stream, and neither `-color_trc
    # bt709` nor `-x264-params transfer=bt709` overrides it - both were tried
    # and the tag came back `iec61966-2-1` regardless. Recording bt709 here
    # while the file said sRGB would make this object describe a file that does
    # not exist, and sRGB is the honest tag anyway: it is what the source is,
    # and it differs from bt709 only in the toe of the curve.
    colour_trc: str = "iec61966-2-1"
    colour_space: str = "bt709"
    # The archival master: the same picture, visually lossless, with the audio
    # carried as PCM rather than AAC so nothing is encoded twice. The delivery
    # file is made from the frames and the WAV directly, *not* from this, so
    # keeping an archive costs no generation loss anywhere.
    archive_crf: int = 12
    archive_audio: str = "pcm_s24le"
    # The delivery file's audio. 192 kbps AAC at 48 kHz is the repository's
    # standard and what Phase 5's true-peak reserve was measured against.
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48000
    # Where the moov atom goes. A Short is streamed, so it goes first.
    faststart: bool = True

    def __post_init__(self) -> None:
        if self.audio not in tile_score.CONFIGS:
            raise ProductionError(
                f"unknown audio configuration {self.audio!r}; "
                f"known: {sorted(tile_score.CONFIGS)}"
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
        if self.fps <= 0.0:
            raise ProductionError("fps must be positive")
        if not self.hook.strip():
            raise ProductionError(
                "the hook cannot be blank: Part 2 chose a line and the frame "
                "is composed around it"
            )
        if not 0 <= self.crf <= 51 or not 0 <= self.archive_crf <= 51:
            raise ProductionError("a CRF outside 0-51 is not an x264 setting")
        if self.archive_crf > self.crf:
            raise ProductionError(
                "the archive would be lower quality than the delivery file, "
                "which is the wrong way round for an archive"
            )

    @property
    def audio_config(self) -> tile_score.AudioConfig:
        """The `AudioConfig` this production uses, at this production's fps.

        `fps` is overridden rather than trusted: the frame grid decides where
        every cue lands, so a production at 30 fps and an `AudioConfig` left at
        its own default would place sound against a picture that does not
        exist. `AudioConfig.fps` is part of its fingerprint for this reason.
        """
        return tile_score.named_config(self.audio, fps=self.fps)

    @property
    def safe_area_config(self) -> tile_safe_area.SafeAreaConfig:
        return tile_safe_area.named_safe_area(self.safe_area, fps=self.fps)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# The locked production. Phase 6's whole job is that this object and the
# repository at its commit are enough to make the upload again.
PRODUCTION = ProductionConfig()


def identity(document: dict[str, Any] | None = None,
             config: ProductionConfig = PRODUCTION) -> dict[str, Any]:
    """The production identity, as the block that goes beside the master.

    Layered on purpose - see the module docstring. `production` moves when a
    delivery dial moves, `audio` when a sound dial moves, `composition` when
    the frame moves, and `run` when the physics moves. A reader comparing two
    of these can say which layer changed.
    """
    out: dict[str, Any] = {
        "format": PRODUCTION_FORMAT,
        "production": {
            "name": config.name,
            "fingerprint": config.fingerprint(),
            "seed": config.seed,
            "timing": config.timing,
            "hook": config.hook,
            "frame": [config.width, config.height],
            "fps": config.fps,
        },
        "audio": {
            "config": config.audio,
            "fingerprint": config.audio_config.fingerprint(),
            "confirmation": config.audio_config.confirmation,
            "activation_duck": config.audio_config.activation_duck,
            "sample_rate": config.audio_config.sample_rate,
        },
        "composition": {
            "arena_width_fraction": tile_readability.ARENA_WIDTH_FRACTION,
            "arena_centre_offset_fraction":
                tile_readability.ARENA_CENTRE_OFFSET_FRACTION,
            "hook_top_fraction": tile_readability.HOOK_TOP_FRACTION,
            "counter_top_fraction": tile_readability.COUNTER_TOP_FRACTION,
            "trail_seconds": tile_readability.TRAIL_SECONDS,
            "ball_draw_scale": tile_readability.BALL_DRAW_SCALE,
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
            "faststart": config.faststart,
            "archive_crf": config.archive_crf,
            "archive_audio": config.archive_audio,
        },
    }
    if document is not None:
        out["run"] = {
            "digest": str(document["digest"]),
            "seed": int(document["seed"]),
            "contacts": len(document["collisions"]),
            "activated_tiles": int(document["activated_tiles"]),
            "total_tiles": int(document["total_tiles"]),
            "completion_seconds": float(document["completion_seconds"]),
        }
        if document.get("completion"):
            block = document["completion"]
            out["run"]["climax_seconds"] = float(block["climax_seconds"])
            out["run"]["total_render_seconds"] = float(
                block["total_render_seconds"])
            out["run"]["final_tile"] = int(block["final_tile"])
            out["run"]["frames"] = int(
                round(float(block["total_render_seconds"]) * config.fps)) + 1
    return out
