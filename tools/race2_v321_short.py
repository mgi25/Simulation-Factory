"""The V32.1 production candidate: V32's Short, over V32.1's pictures.

    python tools/race2_v321_short.py all --variant=B

**This file contains no presentation and no audio.** It imports
`tools/race2_v32_short.py`, repoints four module paths at one variant's frames,
and runs V32's own stages unchanged. That is the strongest form the brief's
"do not redesign presentation" can take: the hook, the ring, the payoff card,
the soundtrack, the clock, the encode and the QC are not reimplemented here,
they are *called*, and a difference between the V32 Short and this one can only
come from the pixels underneath them.

The four paths, and why each one moves:

    FRAMES   the master PNGs              -> the variant's own clip
    OUT      working files and reports    -> this branch's output tree
    DOCS     the evidence JSON            -> this branch's validation tree
    EXPORT   the delivered files          -> exports/race2_v321_track_geometry

Everything else - `SEED`, `COURSE`, `CAMERA`, `ENVIRONMENT`, `TRACK_VARIANT`,
`FPS`, `VIDEO_CRF`, `VIDEO_PRESET`, `AUDIO_BITRATE`, the three marks' timings -
is left exactly as V32 set it, and `stage_locks` is run to say so.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2 import v321_section

OUT = "output/race2/v321_track_geometry"
DOCS = "docs/validation/race2/v321_track_geometry"
EXPORT = "exports/race2_v321_track_geometry"
CANDIDATE = os.path.join(EXPORT, "race2_switchyard_final_candidate.mp4")
CANDIDATE_PHONE = os.path.join(EXPORT, "race2_switchyard_final_candidate_phone_270x480.mp4")


def load_short(variant: str):
    """`tools/race2_v32_short.py`, repointed at one variant and nothing else."""
    if variant not in v321_section.FACES:
        raise SystemExit(f"unknown variant {variant}")
    spec = importlib.util.spec_from_file_location(
        "race2_v32_short", os.path.join(REPO, "tools", "race2_v32_short.py"))
    short = importlib.util.module_from_spec(spec)
    sys.modules["race2_v32_short"] = short
    spec.loader.exec_module(short)

    tag = f"clip_{short.COURSE}_{short.SEED}"
    short.FRAMES = os.path.join(OUT, variant, "frames", tag)
    short.OUT = os.path.join(OUT, "short", variant)
    short.WORK = os.path.join(short.OUT, "work")
    short.DOCS = os.path.join(DOCS, "short", variant)
    short.EXPORT = os.path.join(EXPORT, variant)
    short.MASTER = os.path.join(short.EXPORT, f"race2_{short.COURSE}_master.mp4")
    short.VISUAL = os.path.join(short.EXPORT, f"race2_{short.COURSE}_final_visual.mp4")
    short.FINAL = os.path.join(short.EXPORT, f"race2_{short.COURSE}_final.mp4")
    short.PHONE = os.path.join(
        short.EXPORT, f"race2_{short.COURSE}_final_phone_270x480.mp4")
    for folder in (short.OUT, short.WORK, short.DOCS, short.EXPORT):
        os.makedirs(folder, exist_ok=True)
    return short


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("evidence", "audio", "overlays", "mux",
                                          "proofs", "review", "locks", "qc",
                                          "all"))
    parser.add_argument("--variant", default="B")
    parser.add_argument("--rebuild-overlays", dest="rebuild_overlays",
                        action="store_true")
    args = parser.parse_args(argv)

    short = load_short(args.variant)
    print(f"V32.1 candidate: variant {args.variant} "
          f"({v321_section.VARIANTS[args.variant]['title']}, "
          f"faces={v321_section.FACES[args.variant]})")
    print(f"  frames {short.FRAMES}")
    rc = short.main([args.stage] + (["--rebuild-overlays"]
                                    if args.rebuild_overlays else []))
    if args.stage in ("mux", "all") and os.path.isfile(short.FINAL):
        os.makedirs(EXPORT, exist_ok=True)
        shutil.copyfile(short.FINAL, CANDIDATE)
        print(f"  candidate -> {CANDIDATE}")
        if os.path.isfile(short.PHONE):
            shutil.copyfile(short.PHONE, CANDIDATE_PHONE)
            print(f"  phone     -> {CANDIDATE_PHONE}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
