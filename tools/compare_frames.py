"""Compare two rendered sequences frame by frame.

The determinism check. Render one replay twice and this says whether the two
sequences are the same images - not "they look the same", but the same bytes,
and if the bytes ever differ, whether the *pixels* still match.

    python tools/compare_frames.py output/render_a output/render_b

A directory may be either a render directory or the frames directory inside
it, so both of these mean the same thing::

    output/render_seed_21465
    output/render_seed_21465/frames
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendering import png_frames  # noqa: E402
from rendering.render_plan import FRAMES_SUBDIR, frame_index  # noqa: E402


def frames_dir(path: str) -> str:
    nested = os.path.join(path, FRAMES_SUBDIR)
    return nested if os.path.isdir(nested) else path


def frame_names(directory: str) -> list[str]:
    names = [name for name in os.listdir(directory) if frame_index(name) is not None]
    return sorted(names)


def compare(left_dir: str, right_dir: str, sample_every: int) -> int:
    left_names = frame_names(left_dir)
    right_names = frame_names(right_dir)

    if not left_names:
        print(f"no frames in {left_dir}", file=sys.stderr)
        return 1
    if left_names != right_names:
        only_left = sorted(set(left_names) - set(right_names))
        only_right = sorted(set(right_names) - set(left_names))
        print(
            f"frame lists differ: {len(left_names)} vs {len(right_names)} files"
            + (f", only in left: {only_left[:3]}" if only_left else "")
            + (f", only in right: {only_right[:3]}" if only_right else ""),
            file=sys.stderr,
        )
        return 1

    checked = [name for i, name in enumerate(left_names) if i % sample_every == 0]
    if checked and checked[-1] != left_names[-1]:
        checked.append(left_names[-1])

    byte_mismatches: list[str] = []
    pixel_mismatches: list[str] = []
    for name in checked:
        left = os.path.join(left_dir, name)
        right = os.path.join(right_dir, name)
        if png_frames.file_digest(left) == png_frames.file_digest(right):
            continue
        byte_mismatches.append(name)
        # Identical pictures in non-identical files would still be a pass,
        # so the decoded pixels get the final word.
        if png_frames.pixel_digest(left) != png_frames.pixel_digest(right):
            pixel_mismatches.append(name)

    print(f"frames        {len(left_names)}")
    print(f"compared      {len(checked)} (every {sample_every})")
    print(f"byte-identical  {len(checked) - len(byte_mismatches)}/{len(checked)}")
    if byte_mismatches:
        print(f"  differing files: {byte_mismatches[:5]}")
        print(f"  of which differing pixels: {len(pixel_mismatches)}")
        if pixel_mismatches:
            print(f"  differing pixels: {pixel_mismatches[:5]}")
    return 1 if pixel_mismatches or byte_mismatches else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="compare two rendered sequences")
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument(
        "--every",
        type=int,
        default=1,
        help="compare every Nth frame (default: all of them)",
    )
    args = parser.parse_args()

    status = compare(frames_dir(args.left), frames_dir(args.right), max(1, args.every))
    print("IDENTICAL" if status == 0 else "DIFFERENT")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
