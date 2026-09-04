"""Original, deterministic sound for a finished Short.

Every sample this package produces comes out of code inside it: oscillators,
envelopes, filters and a seeded noise generator. There are no samples, no
loops, no packs, no music services and no licensed libraries anywhere in the
chain, which is what lets a rendered video be used wherever the project
wants to use it.

The layers, lowest first:

* `synthesis` - oscillators, envelopes, filters, a seeded PRNG. Knows
  nothing about battles.
* `cues` - what each event sounds like, and the quiet ambient bed.
* `soundtrack` - the exact integer timeline, stereo placement, the mix, the
  master and the deterministic sidecar.
* `wav_io` - the PCM master on disk, and reading it back to check it.

Deliberately absent: music. The first production format is sound effects and
room tone only, so that what a battle sounds like can be judged before
anything is layered on top of it.
"""

from __future__ import annotations

from audio.soundtrack import (
    PEAK_CEILING,
    PEAK_CEILING_DBFS,
    PHYSICS_HZ,
    SAMPLES_PER_FRAME,
    SAMPLES_PER_TICK,
    SOUNDTRACK_VERSION,
    VIDEO_FPS,
    Soundtrack,
    SoundtrackError,
    SoundtrackPlan,
    audio_metadata,
    build_soundtrack,
    frame_to_sample,
    plan_soundtrack,
    tick_to_sample,
    total_samples,
)
from audio.synthesis import CHANNELS, SAMPLE_RATE
from audio.wav_io import DEFAULT_BIT_DEPTH, WavError, read_wav, write_wav

__all__ = [
    "CHANNELS",
    "DEFAULT_BIT_DEPTH",
    "PEAK_CEILING",
    "PEAK_CEILING_DBFS",
    "PHYSICS_HZ",
    "SAMPLES_PER_FRAME",
    "SAMPLES_PER_TICK",
    "SAMPLE_RATE",
    "SOUNDTRACK_VERSION",
    "VIDEO_FPS",
    "Soundtrack",
    "SoundtrackError",
    "SoundtrackPlan",
    "WavError",
    "audio_metadata",
    "build_soundtrack",
    "frame_to_sample",
    "plan_soundtrack",
    "read_wav",
    "tick_to_sample",
    "total_samples",
    "write_wav",
]
