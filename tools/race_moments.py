"""Pull the same handful of moments out of any rendered race.

A review artefact, and the answer to "did this change make it better". Judging
a visual change by scrubbing two thousand-frame sequences by hand does not
work; judging it from the same five moments of the same race, side by side,
does.

The moments are found in the replay rather than chosen by eye. Every course
exports its sections, so "the funnel" is the frame the leading racer first
crosses into the section called `funnel` - which means this tool works on a
course it has never seen, and picks the same instant in a V0.2 render and a
V0.3 render of one replay. That last part is the whole point: two frames
compared have to be the same moment, or the comparison is about the moment
rather than about the change.

    python tools/race_moments.py output/race_v03/render_production_x \\
        --replay output/race_v03/prototype_839271.json \\
        --out docs/validation/race_v03/after --label after

Frames are written at half size. A 1080x1920 PNG is half a megabyte, and
these are for looking at rather than for measuring - the measuring is
`verify_race_render.py`, which reads the full-resolution originals.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rendering.render_plan import FRAMES_SUBDIR, METADATA_NAME, frame_filename  # noqa: E402

# Half of 1080x1920. Big enough to judge materials and lighting, small enough
# that a set of them can live in the repository beside the document that
# refers to them.
THUMB_SCALE = 0.5

# The one moment that is not a section: the frame the winner crosses. Named
# here so a caller sees the whole set in one place.
FINISH_MOMENT = "finish_line"


class MomentError(RuntimeError):
    """The moments could not be extracted."""


def load_json(path: str) -> dict:
    if not os.path.isfile(path):
        raise MomentError(f"no file at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def resolve_replay(render_dir: str, explicit: str | None) -> str:
    if explicit:
        return explicit
    metadata = load_json(os.path.join(render_dir, METADATA_NAME))
    name = str((metadata.get("replay") or {}).get("path") or "")
    if not name:
        raise MomentError(f"{render_dir}: the sidecar does not name a replay")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidate = os.path.join(root, name)
    return candidate if os.path.isfile(candidate) else name


def leader_y(frame: dict) -> float:
    """How far down the course the race has actually got.

    The furthest racer still running, rather than the one ranked first: at the
    moment a section is entered they are usually the same racer, and where
    they are not, what a viewer is looking at is the one in front.
    """
    best = float("-inf")
    for racer in frame.get("racers", []):
        if racer.get("retired") or racer.get("finished"):
            continue
        best = max(best, float(racer.get("y", 0.0)))
    return best


def section_moments(replay: dict) -> dict[str, int]:
    """The first frame the race reaches each named section of the course.

    Sections come out of the replay, so this needs no idea what a funnel or a
    jump is - only that the course said one starts there.
    """
    frames = replay.get("frames", [])
    sections = (replay.get("course") or {}).get("sections", [])
    moments: dict[str, int] = {}
    for section in sections:
        name = str(section.get("name", ""))
        top = float(section.get("top", 0.0))
        if not name or name == "boundary":
            continue
        for index, frame in enumerate(frames):
            if leader_y(frame) >= top:
                moments[name] = index
                break
    return moments


def finish_moment(replay: dict) -> int | None:
    """The frame the winner crosses, from the event rather than from a guess."""
    ticks_per_frame = max(1, int(replay.get("ticks_per_frame", 2)))
    frames = replay.get("frames", [])
    for event in replay.get("events", []):
        if str(event.get("type", "")) != "winner":
            continue
        # `frames[i].tick` is not always exactly `2 * i`, so the index is
        # clamped rather than computed and trusted.
        return min(len(frames) - 1, int(event.get("tick", 0)) // ticks_per_frame)
    return None


def moments(replay: dict, wanted: list[str] | None) -> dict[str, int]:
    found = section_moments(replay)
    finish = finish_moment(replay)
    if finish is not None:
        found[FINISH_MOMENT] = finish
    if not wanted:
        return found
    return {name: found[name] for name in wanted if name in found}


def write_thumb(source_path: str, target_path: str, scale: float) -> tuple[int, int]:
    import pygame

    surface = pygame.image.load(source_path)
    width, height = surface.get_size()
    size = (max(1, int(width * scale)), max(1, int(height * scale)))
    # Smoothscale rather than a nearest-neighbour scale: these are judged by
    # eye and a point-sampled downscale of a 1080p frame aliases every thin
    # lit edge on the course into a dashed line.
    scaled = pygame.transform.smoothscale(surface, size)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    pygame.image.save(scaled, target_path)
    return size


def extract(render_dir: str, replay: dict, out_dir: str, label: str,
		wanted: list[str] | None, scale: float) -> list[str]:
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    if not os.path.isdir(frames_dir):
        raise MomentError(f"no frames directory in {render_dir}")

    import pygame

    pygame.init()
    written = []
    try:
        for name, index in sorted(moments(replay, wanted).items(), key=lambda p: p[1]):
            source_path = os.path.join(frames_dir, frame_filename(index))
            if not os.path.isfile(source_path):
                print(f"  {name}: frame {index} is not in this render", file=sys.stderr)
                continue
            stem = f"{label}_{name}" if label else name
            target = os.path.join(out_dir, f"{stem}.png")
            size = write_thumb(source_path, target, scale)
            written.append(target)
            print(f"  {name:<16} frame {index:>5}  ->  {target}  ({size[0]}x{size[1]})")
    finally:
        pygame.quit()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(
        description="extract the same named moments from a rendered race"
    )
    parser.add_argument("render", help="a render directory")
    parser.add_argument("--replay", default=None, help="the replay, if not in metadata")
    parser.add_argument("--out", required=True, help="where to write the stills")
    parser.add_argument("--label", default="", help="prefix for each filename")
    parser.add_argument(
        "--moments",
        default=None,
        help="comma-separated section names, default every one the course has",
    )
    parser.add_argument("--scale", type=float, default=THUMB_SCALE)
    args = parser.parse_args()

    try:
        replay_path = resolve_replay(args.render, args.replay)
        replay = load_json(replay_path)
        wanted = None
        if args.moments:
            wanted = [name.strip() for name in args.moments.split(",") if name.strip()]
        print(f"=== {args.render} ===\n    replay {replay_path}")
        written = extract(
            args.render, replay, args.out, args.label, wanted, args.scale
        )
    except (MomentError, OSError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not written:
        print("error: no moments extracted", file=sys.stderr)
        return 1
    print(f"    {len(written)} still(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
