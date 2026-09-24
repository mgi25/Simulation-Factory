"""The Phase 4C production identity: one object that decides the master.

Category 3 Test #2's deliverable is a file somebody uploads, and the claim
attached to it is that this repository can make that file again. This module is
where that claim lives. Every dial the upload depends on - the seed, the
framing, the camera schedule, the audio system, the encoder - is one frozen
object with a digest over all of it, so "the same master" is something that can
be checked rather than remembered.

It is a sibling of `satisfying.tile_production`, which does the same job for
Test #1, and deliberately not a generalisation of it: the two tests have
different composition dials and a shared base class would have to carry both
sets and mean neither.

## What is in here and what is not

In: things that change the bytes of the delivered file.

Out: anything to do with publishing. No title, no description, no tags, no
thumbnail. Those belong to whatever uploads the file, and a video carrying its
own metadata cannot be re-titled without a re-encode.

## Why the digest is layered

`audio` is the string `"open_quartal"`, not a copy of that configuration's
fields; the fields are digested separately and both digests appear in
`identity()`. So a change to an audio dial moves the audio fingerprint and the
production fingerprint, while a change to the CRF moves only the production
one - a mismatch says *which layer* moved, where a single flattened digest
could only say that something had.

## The reproduction claim, stated precisely

Given this repository at the recorded commit and `PRODUCTION` unchanged:

* the simulation is a function of `seed` and the frozen Phase 1 config, and its
  `config_digest` and playback `digest` are recorded;
* the camera, the framing and the damage geometry are functions of that
  document and the constants in `multishell_visual`, whose
  `render_config_digest` is recorded;
* the audio is a function of the document and the named `AudioConfig`;
* the delivery file is a function of the rendered frames, the master WAV and
  the encoder settings below - **and the archive is a function of the same two
  sources, not of the delivery file**, so keeping an archive costs no
  generation loss anywhere and neither file is derived from the other.

The first three are exactly reproducible. The fourth is not claimed to be
bit-exact, because x264 is free to differ between builds; what is checked there
is the *decoded* result - resolution, frame count, duration, true peak and
synchronisation.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from satisfying import multishell_av as av
from satisfying import multishell_score as score
from satisfying import multishell_visual as visual

__all__ = [
    "PRODUCTION_FORMAT",
    "ProductionError",
    "ProductionConfig",
    "PRODUCTION",
    "identity",
    "file_digest",
]

PRODUCTION_FORMAT = 1


class ProductionError(RuntimeError):
    """A production configuration that cannot be delivered."""


@dataclass(frozen=True)
class ProductionConfig:
    """Everything that decides the bytes of the upload."""

    # --- what is being made ----------------------------------------------
    name: str = "category3_test2_seed1176"
    #: **1176, and chosen against 17964 from rendered frames.** Its climax is a
    #: break rather than an opening - the wall is worn, cracks, fails and the
    #: winner leaves through the hole its own team made - which is the one
    #: sequence the brief calls the most important proof. And at the selected
    #: framing its escape is at the bottom left rather than at a cropped
    #: horizontal cap, so the escapee is fully framed for the whole 0.55 s
    #: release where 17964's is framed for 0.05 s of it.
    seed: int = 1176

    # --- the picture ------------------------------------------------------
    width: int = 1080
    height: int = 1920
    fps: float = 60.0
    #: The final structure's material diameter as a share of the frame width.
    #: Above 1.0: the outer wall is 1296 px across in a 1080 px frame and its
    #: left and right caps are cropped, which is the 4C framing rule.
    frame_fraction: float = 1.200
    #: One reframe, trigger region 2, extents shell 2 then shell 4.
    camera_stages: int = 2
    audio: str = "open_quartal"
    safe_area: str = "shorts_conservative"

    # --- the encode -------------------------------------------------------
    video_codec: str = "libx264"
    crf: int = 17
    preset: str = "slow"
    pixel_format: str = "yuv420p"
    #: The archival master: the same picture, visually lossless, with the audio
    #: carried as 24-bit PCM so nothing is encoded twice. The delivery file is
    #: made from the frames and the WAV directly, **not** from this.
    archive_crf: int = 12
    archive_audio: str = "pcm_s24le"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48_000
    faststart: bool = True

    def __post_init__(self) -> None:
        if self.audio != "open_quartal":
            raise ProductionError(
                "Test #2 is locked to the open_quartal score; the 4C brief "
                "forbids redesigning it"
            )
        if self.seed not in visual.CANDIDATE_SEEDS:
            raise ProductionError(
                f"seed {self.seed} is not in the frozen candidate set"
            )
        if self.width <= 0 or self.height <= self.width:
            raise ProductionError("the delivery frame is vertical 9:16")
        if abs(self.width * 16 - self.height * 9) > 1:
            raise ProductionError("the delivery frame is not 9:16")
        if self.fps <= 0.0:
            raise ProductionError("fps must be positive")
        if not 0 <= self.crf <= 51 or not 0 <= self.archive_crf <= 51:
            raise ProductionError("a CRF outside 0-51 is not an x264 setting")
        if self.archive_crf > self.crf:
            raise ProductionError(
                "the archive would be lower quality than the delivery file, "
                "which is the wrong way round for an archive"
            )
        if self.audio_sample_rate != 48_000:
            raise ProductionError("the score is mastered at 48 kHz")
        # The production may not silently describe a framing the renderer does
        # not use. Both files' defaults are the single source here; the
        # laboratory dial exists but never changes a default.
        if self.frame_fraction != visual.FRONTIER_WIDTH_FRACTION:
            raise ProductionError(
                f"production frame fraction {self.frame_fraction} is not the "
                f"renderer's {visual.FRONTIER_WIDTH_FRACTION}"
            )
        if self.camera_stages != len(visual.CAMERA_STAGE_PLAN):
            raise ProductionError(
                f"production expects {self.camera_stages} camera stages, the "
                f"renderer plans {len(visual.CAMERA_STAGE_PLAN)}"
            )

    @property
    def audio_config(self) -> score.AudioConfig:
        return score.named_config(self.audio)

    @property
    def transitions(self) -> int:
        """Camera moves, which is one fewer than the number of stages."""
        return max(0, self.camera_stages - 1)

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


#: The locked production. The phase's whole job is that this object and the
#: repository at its commit are enough to make the upload again.
PRODUCTION = ProductionConfig()


def file_digest(path: str) -> str:
    """SHA-256 of a delivered artefact, read in blocks."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(document: Mapping[str, Any],
             config: ProductionConfig = PRODUCTION) -> dict[str, Any]:
    """The production identity, as the block that goes beside the master.

    Layered on purpose - see the module docstring. `production` moves when a
    delivery dial moves, `audio` when a sound dial moves, `visual` when the
    frame moves, and `run` when the physics moves. A reader comparing two of
    these can say which layer changed.
    """
    if int(document["seed"]) != config.seed:
        raise ProductionError(
            f"identity asked for seed {config.seed} with a document for "
            f"{document['seed']}"
        )
    av.validate_shared_document(document)
    stages = visual.camera_stages(dict(document))
    summary = document["summary"]
    return {
        "format": PRODUCTION_FORMAT,
        "production": {
            "name": config.name,
            "fingerprint": config.fingerprint(),
            "seed": config.seed,
            "frame": [config.width, config.height],
            "fps": config.fps,
            "frame_fraction": config.frame_fraction,
            "camera_transitions": config.transitions,
        },
        "run": {
            "schema": str(document["schema"]),
            "config_digest": str(document["config_digest"]),
            "playback_digest": str(document["digest"]),
            "event_order_digest": av.event_order_digest(document),
            "duration_seconds": float(summary["duration"]),
            "escape_time": float(summary["escape_time"]),
            "winner_team": int(summary["winner_team"]),
            "winner_team_name": str(summary["winner_team_name"]),
            "winner_route": str(summary["winner_route"]),
            "winner_ball": int(summary["escape_ball"]),
            "max_population": int(summary["max_population"]),
            "breaks": int(summary["breaks"]),
        },
        "visual": {
            "render_config_digest": visual.render_config_digest(),
            "safe_area": config.safe_area,
            "camera_stage_plan": [list(entry)
                                  for entry in visual.CAMERA_STAGE_PLAN],
            "camera_stages": [
                {
                    "stage": int(stage["stage"]),
                    "extent_shell": int(stage["extent_shell"]),
                    "trigger_region": stage["trigger_region"],
                    "trigger_t": float(stage["trigger_t"]),
                    "start": float(stage["start"]),
                    "settled": float(stage["settled"]),
                    "view_radius": float(stage["radius"]),
                }
                for stage in stages
            ],
            "camera_lock_time": visual.camera_lock_time(dict(document)),
            "static_tail_seconds": visual.static_tail_seconds(dict(document)),
            "transition_seconds": visual.FRAME_EASE_SECONDS,
        },
        "audio": {
            "config": config.audio,
            "fingerprint": config.audio_config.fingerprint(),
            "sample_rate": config.audio_sample_rate,
            "codec": config.audio_codec,
            "bitrate": config.audio_bitrate,
        },
        "encode": {
            "video_codec": config.video_codec,
            "crf": config.crf,
            "preset": config.preset,
            "pixel_format": config.pixel_format,
            "faststart": config.faststart,
            "archive_crf": config.archive_crf,
            "archive_audio": config.archive_audio,
        },
    }
