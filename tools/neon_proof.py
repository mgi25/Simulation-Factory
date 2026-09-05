"""Produce the Neon Marble Machine visual proof: replay, stills, video.

The prototype's front door, and the only thing that knows the whole shape of
the deliverable. Everything it does is a step of the pipeline the project
already has - Python simulates, the exporter freezes the run, Godot draws it,
FFmpeg encodes it - with the V1 scene selected by one flag:

    python tools/neon_proof.py --seed 7 --all

Steps, and each one can be asked for on its own:

    --replay     simulate the neon course and export a race replay
    --cameras    the same four moments at 48, 52 and 55 degrees
    --frames     the full 1080x1920 sequence at the chosen elevation
    --sections   the five section stills, pulled out of that sequence
    --heroes     the three hero stills the brief asks to be judged on
    --video      the 5-8 second proof, cut from that sequence
    --countries  the badge experiment: three treatments at three moments
    --phone      every still again at the size a Short is actually watched at
    --before     V1 against V1.1 at matched timestamps, side by side

Nothing here re-simulates between steps. The replay is written once and every
later step reads it, so the camera comparison, the section stills and the
video are all the same race at the same instants - which is the only way a
comparison is about what it claims to be about.

The video window is computed from the replay rather than chosen: it opens a
fixed lead-in before the tick the gate is recorded open and runs for the
brief's length. Two runs of the same seed cut the same seven seconds.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race.courses.neon import NEON_COURSE_ID, NEON_RACER_COUNT  # noqa: E402
from rendering import encode  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    frame_filename,
)
from tools.race_moments import THUMB_SCALE, write_thumb  # noqa: E402
from tools.render_replay import (  # noqa: E402
    GODOT_PROJECT,
    PROJECT_ROOT,
    RENDER_SCENE,
    RenderError,
    find_godot,
)

DEFAULT_SEED = 7
DEFAULT_ROOT = os.path.join("output", "neon_v11")
DEFAULT_STILLS = os.path.join("docs", "validation", "neon_v11")
# Where V1's committed stills live, for the before-and-after.
V1_STILLS = os.path.join("docs", "validation", "neon_v1", "sections")

# The elevations the brief asks to be compared for V1.1, and the one this
# revision ships on. `SELECTED_ELEVATION` is what `--frames` and `--video`
# shoot with unless `--elevation` says otherwise; it must match the scene's own
# `CAM_ELEVATION`, and `tests/test_neon_proof.py` checks that it does.
CAMERA_ANGLES = (48.0, 52.0, 55.0)
SELECTED_ELEVATION = 52.0

# The proof, in seconds. Opens on the platform, holds through the release, the
# bowl and the bridge.
VIDEO_LEAD_IN = 1.2
VIDEO_SECONDS = 7.0

# The moments the camera comparison is judged on, as seconds from the tick the
# gate opens. Negative is before the release. The last is late enough to be
# past the bowl, because 'visible support structure' is one of the four things
# the brief asks the elevation to be chosen on and the supports are under the
# bridge.
CAMERA_MOMENTS = (-0.6, 2.0, 2.8, 5.3)

# The five section stills, as (name, seconds after the gate opens). Chosen from
# the reference replay's own timings and stated here rather than searched for,
# so the same five moments come out of any render of it.
SECTION_MOMENTS = (
    ("start_platform", -0.6),
    ("entering_bowl", 1.3),
    ("inside_bowl", 2.0),
    ("bowl_exit", 2.8),
    ("s_curve_bridge", 4.3),
)

# The three the brief asks to be judged on, and each one is a different
# question. The start has to show the platform, the feed channels and the bowl
# below them in one frame; the bowl has to show the glass and the cradle with
# the field mixing inside; the bridge has to show the supports and the room.
HERO_MOMENTS = (
    ("start_hero", 0.90),
    ("bowl_hero", 2.0),
    ("bridge_hero", 5.3),
)

# The country experiment: three treatments of the same five racers, at three
# moments. Nine stills, and the only thing that differs across a row is the
# badge - which is the only thing the experiment is asking about.
COUNTRY_MODES = ("number", "flag", "code")
COUNTRY_MOMENTS = (("start", 0.55), ("bowl", 2.0), ("bridge", 5.3))

# What a Short is actually watched at. The brief asks explicitly not to judge
# only at desktop full-screen, and 0.28 of 1080x1920 is 302x538 - about a
# phone's worth of pixels for a portrait video in a feed.
PHONE_SCALE = 0.28


class ProofError(RuntimeError):
    """A step of the proof could not be completed."""


# --- replay -----------------------------------------------------------------


def export_replay(path: str, seed: int, racers: int) -> dict:
    from replay.race_exporter import record_race, write_replay

    replay = record_race(seed, course_name=NEON_COURSE_ID, racer_count=racers)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    write_replay(replay, path)
    result = replay["result"]
    print(
        f"    seed {seed}  {len(replay['racers'])} racers"
        f"  {len(replay['frames'])} frames"
        f" ({len(replay['frames']) / replay['fps']:.2f}s)\n"
        f"    winner {result['winner_name']} at {result['winner_time']:.2f}s,"
        f" {result['racers_finished']}/{len(replay['racers'])} home\n"
        f"    wrote {path} ({os.path.getsize(path) / 1024 / 1024:.1f} MiB)"
    )
    return replay


def load_replay(path: str) -> dict:
    if not os.path.isfile(path):
        raise ProofError(f"no replay at {path}; run with --replay first")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def gate_frame(replay: dict) -> int:
    """The output frame the starting gate is first recorded open on.

    Every moment in this file is measured from here rather than from frame
    zero, because frame zero is three seconds of countdown that no part of the
    proof is about.
    """
    for index, frame in enumerate(replay.get("frames", [])):
        if frame.get("gates_open"):
            return index
    raise ProofError("the replay never opens its gate")


def moment_frame(replay: dict, seconds: float) -> int:
    """An output frame index, given seconds either side of the release."""
    last = max(0, len(replay.get("frames", [])) - 1)
    return max(0, min(last, gate_frame(replay) + int(round(seconds * RENDER_FPS))))


# --- rendering --------------------------------------------------------------


def godot_command(
    godot: str,
    replay_path: str,
    out_dir: str,
    total: int,
    elevation: float,
    stills: tuple[int, ...] = (),
    countries: str = "",
) -> list[str]:
    """One Godot invocation, as an argument list.

    `--race-style=neon` is the whole difference from `render_replay.py`: the
    same scene tree, the same offline renderer and the same clock, with the
    prototype's scene in place of the production one.
    """
    command = [
        godot,
        "--path",
        GODOT_PROJECT,
        RENDER_SCENE,
        "--",
        f"--replay={os.path.abspath(replay_path)}",
        f"--out-dir={os.path.abspath(out_dir)}",
        f"--frames={total}",
        f"--fps={RENDER_FPS}",
        f"--width={RENDER_WIDTH}",
        f"--height={RENDER_HEIGHT}",
        "--race-camera=production",
        "--race-style=neon",
        f"--race-elevation={elevation:g}",
    ]
    if stills:
        command.append(f"--stills={','.join(str(index) for index in stills)}")
    if countries:
        command.append(f"--neon-countries={countries}")
    return command


def run_godot(command: list[str], label: str) -> None:
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ProofError(f"Godot exited {completed.returncode} while rendering {label}")


def render_cameras(
    godot: str, replay: dict, replay_path: str, out_root: str, angles: tuple[float, ...]
) -> dict[float, list[str]]:
    """The same moments at each elevation, one directory per angle."""
    total = len(replay["frames"])
    frames = tuple(moment_frame(replay, at) for at in CAMERA_MOMENTS)
    written: dict[float, list[str]] = {}
    for angle in angles:
        out_dir = os.path.join(out_root, f"e{angle:g}")
        os.makedirs(out_dir, exist_ok=True)
        print(f"    {angle:g} degrees -> {out_dir}")
        run_godot(
            godot_command(godot, replay_path, out_dir, total, angle, frames),
            f"{angle:g} degrees",
        )
        written[angle] = [
            os.path.join(out_dir, f"still_{index:06d}.png") for index in frames
        ]
    return written


def render_frames(
    godot: str, replay: dict, replay_path: str, render_dir: str, elevation: float
) -> str:
    """The whole sequence, at the elevation the prototype ships on."""
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    os.makedirs(frames_dir, exist_ok=True)
    for name in os.listdir(frames_dir):
        if name.startswith("frame_") and name.endswith(".png"):
            os.remove(os.path.join(frames_dir, name))

    total = len(replay["frames"])
    print(f"    {total} frames at {elevation:g} degrees -> {frames_dir}")
    run_godot(
        godot_command(godot, replay_path, frames_dir, total, elevation),
        "the full sequence",
    )
    missing = [
        index
        for index in range(total)
        if not os.path.isfile(os.path.join(frames_dir, frame_filename(index)))
    ]
    if missing:
        raise ProofError(
            f"{len(missing)} frames missing, first {frame_filename(missing[0])}"
        )
    return frames_dir


def render_countries(
    godot: str, replay: dict, replay_path: str, out_dir: str, elevation: float
) -> list[tuple[str, str, str]]:
    """The three badge treatments at the three moments.

    Every still comes out of the same replay at the same frames through the
    same scene, so the only thing that differs down a column is the badge -
    which is the only thing the experiment is asking about.
    """
    total = len(replay["frames"])
    indices = tuple(moment_frame(replay, at) for _, at in COUNTRY_MOMENTS)
    written: list[tuple[str, str, str]] = []
    for mode in COUNTRY_MODES:
        target = os.path.join(out_dir, mode)
        os.makedirs(target, exist_ok=True)
        run_godot(
            godot_command(
                godot,
                replay_path,
                target,
                total,
                elevation,
                indices,
                "" if mode == "number" else mode,
            ),
            f"the {mode} badges",
        )
        for (label, _), index in zip(COUNTRY_MOMENTS, indices):
            written.append(
                (mode, label, os.path.join(target, f"still_{index:06d}.png"))
            )
    return written


# --- stills and video -------------------------------------------------------


def save_stills(sources: list[str], targets: list[str], scale: float) -> list[str]:
    """Put the stills where they are reviewed from, at review size.

    Half size by default, and `tools/race_moments.py`'s own resampler is used
    rather than a second one, for the reason that file gives: these are judged
    by eye, and a point-sampled downscale of a 1080p frame turns every thin lit
    edge on the machine into a dashed line.

    Half size is also what keeps them committable. Full-size PNGs of a machine
    this pale come out near a megabyte each, and thirty of them is thirty
    megabytes of repository for pictures nobody measures - the measuring is
    done on the sequence under `output/`, which is not committed.
    `--still-scale 1` writes them full size if that is ever wanted.
    """
    written = []
    for source, target in zip(sources, targets):
        if not os.path.isfile(source):
            raise ProofError(f"expected a still at {source}")
        os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
        if scale >= 1.0:
            shutil.copyfile(source, target)
        else:
            write_thumb(source, target, scale)
        written.append(target)
    return written


def extract_moments(
    replay: dict,
    frames_dir: str,
    out_dir: str,
    moments: tuple[tuple[str, float], ...],
    scale: float,
) -> list[str]:
    """Named moments, copied out of the finished sequence."""
    sources = []
    targets = []
    for name, at in moments:
        index = moment_frame(replay, at)
        sources.append(os.path.join(frames_dir, frame_filename(index)))
        targets.append(os.path.join(out_dir, f"{name}.png"))
        print(f"    {name:<16} frame {index:>5}  ({at:+.1f}s from the release)")
    return save_stills(sources, targets, scale)


def video_window(replay: dict) -> tuple[int, int]:
    """Which frames the proof video is cut from. First frame, and how many."""
    start = max(0, gate_frame(replay) - int(round(VIDEO_LEAD_IN * RENDER_FPS)))
    count = int(round(VIDEO_SECONDS * RENDER_FPS))
    available = len(replay.get("frames", [])) - start
    return start, max(1, min(count, available))


def encode_video(replay: dict, frames_dir: str, output: str) -> str:
    try:
        ffmpeg = encode.find_ffmpeg(None)
    except encode.EncodeError as error:
        raise ProofError(str(error)) from None
    start, count = video_window(replay)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    command = encode.encode_command(
        ffmpeg,
        frames=encode.frames_pattern(frames_dir),
        audio=None,
        output=output,
        frame_count=count,
        start_number=start,
    )
    print(
        f"    frames {start}..{start + count - 1}"
        f"  ({count / RENDER_FPS:.2f}s at {RENDER_FPS}fps)"
    )
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ProofError(f"ffmpeg exited {completed.returncode}")
    size = os.path.getsize(output)
    print(f"    wrote {output} ({size / 1024 / 1024:.1f} MiB)")
    return output


# --- comparison sheets ------------------------------------------------------


CAPTION = 44


def _caption(surface, text: str, x: int, width: int) -> None:
    import pygame

    font = pygame.font.SysFont("dejavusans,arial", 22)
    label = font.render(text, True, (214, 224, 236))
    surface.blit(label, (x + (width - label.get_width()) // 2, 12))


def compose(pairs: list[tuple[str, str]], target: str) -> str:
    """Several stills side by side under their labels, as one sheet.

    A comparison the reviewer has to open two files to make is a comparison
    that does not get made. `pairs` is `(caption, path)` in the order they
    should read left to right.
    """
    import pygame

    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    images = []
    for caption, path in pairs:
        if not os.path.isfile(path):
            raise ProofError(f"expected a still at {path}")
        images.append((caption, pygame.image.load(path)))

    width = sum(image.get_width() for _, image in images)
    height = max(image.get_height() for _, image in images)
    sheet = pygame.Surface((width, height + CAPTION))
    sheet.fill((10, 12, 17))
    x = 0
    for caption, image in images:
        sheet.blit(image, (x, CAPTION))
        _caption(sheet, caption, x, image.get_width())
        x += image.get_width()

    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    pygame.image.save(sheet, target)
    return target


def before_after(stills_root: str, out_dir: str) -> list[str]:
    """V1 against V1.1 at matched timestamps.

    Both sides are the same seconds from the release of the same seed. The
    *races* differ - the chute is four launch channels now instead of one
    apron, so the field arrives differently - and that is what is being
    compared: this is an art-direction revision, not a re-render.
    """
    written = []
    for name, at in SECTION_MOMENTS:
        old = os.path.join(V1_STILLS, f"{name}.png")
        new = os.path.join(stills_root, "sections", f"{name}.png")
        if not os.path.isfile(old):
            print(f"    skipped {name}: no V1 still at {old}")
            continue
        target = os.path.join(out_dir, f"{name}.png")
        compose(
            [(f"V1   {name}  {at:+.1f}s", old), (f"V1.1   {name}  {at:+.1f}s", new)],
            target,
        )
        written.append(target)
        print(f"    {name}")
    return written


def country_sheets(
    written: list[tuple[str, str, str]], out_dir: str, scale: float
) -> list[str]:
    """One sheet per moment: numbers, flags and codes side by side."""
    sheets = []
    for label, _ in COUNTRY_MOMENTS:
        pairs = []
        for mode in COUNTRY_MODES:
            source = next(
                path for m, l, path in written if m == mode and l == label
            )
            scaled = os.path.join(out_dir, f".{mode}_{label}.png")
            save_stills([source], [scaled], scale)
            pairs.append((f"{mode}   {label}", scaled))
        target = os.path.join(out_dir, f"{label}.png")
        compose(pairs, target)
        for _, path in pairs:
            os.remove(path)
        sheets.append(target)
        print(f"    {label}")
    return sheets


def phone_previews(stills_root: str, out_dir: str) -> list[str]:
    """Every judged still again at the size a Short is watched at.

    The brief is explicit that this must not be optimised only for a desktop
    full-screen view, so the review set includes the review size. These are
    downscaled from the committed stills rather than re-rendered, which is
    what a viewer's phone does to the video too.
    """
    written = []
    for name, _ in HERO_MOMENTS:
        source = os.path.join(stills_root, f"{name}.png")
        if not os.path.isfile(source):
            continue
        target = os.path.join(out_dir, f"{name}.png")
        # The committed stills are already at half size, so the extra factor
        # is what takes 1080x1920 to a phone's worth of pixels.
        write_thumb(source, target, PHONE_SCALE / THUMB_SCALE)
        written.append(target)
    for label, _ in COUNTRY_MOMENTS:
        source = os.path.join(stills_root, "countries", f"{label}.png")
        if not os.path.isfile(source):
            continue
        target = os.path.join(out_dir, f"countries_{label}.png")
        write_thumb(source, target, PHONE_SCALE / THUMB_SCALE)
        written.append(target)
    return written


# --- the run ----------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="produce the Neon Marble Machine visual proof"
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--racers", type=int, default=NEON_RACER_COUNT)
    parser.add_argument("--root", default=DEFAULT_ROOT, help="working output root")
    parser.add_argument("--stills", default=DEFAULT_STILLS, help="where stills land")
    parser.add_argument("--godot", default=None)
    parser.add_argument(
        "--elevation",
        type=float,
        default=SELECTED_ELEVATION,
        help="camera elevation for the sequence and the video",
    )
    parser.add_argument(
        "--angles",
        default=",".join(f"{angle:g}" for angle in CAMERA_ANGLES),
        help="comma-separated elevations for the camera comparison",
    )
    parser.add_argument(
        "--still-scale",
        type=float,
        default=THUMB_SCALE,
        help="size the committed stills are written at, relative to 1080x1920",
    )
    parser.add_argument("--all", action="store_true", help="every step, in order")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--cameras", action="store_true")
    parser.add_argument("--frames", action="store_true")
    parser.add_argument("--sections", action="store_true")
    parser.add_argument("--heroes", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--countries", action="store_true")
    parser.add_argument("--phone", action="store_true")
    parser.add_argument("--before", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    steps = {
        "replay": args.replay or args.all,
        "cameras": args.cameras or args.all,
        "frames": args.frames or args.all,
        "sections": args.sections or args.all,
        "heroes": args.heroes or args.all,
        "video": args.video or args.all,
        "countries": args.countries or args.all,
        "phone": args.phone or args.all,
        "before": args.before or args.all,
    }
    if not any(steps.values()):
        print("nothing to do; pass --all or one of the step flags", file=sys.stderr)
        return 2

    replay_path = os.path.join(args.root, f"neon_{args.seed}.json")
    render_dir = os.path.join(args.root, f"render_e{args.elevation:g}")
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)

    try:
        if steps["replay"]:
            print("=== replay ===")
            export_replay(replay_path, args.seed, args.racers)
        replay = load_replay(replay_path)

        godot = None
        if steps["cameras"] or steps["frames"] or steps["countries"]:
            godot = find_godot(args.godot)
            print(f"godot: {godot}")

        if steps["cameras"]:
            print("=== camera comparison ===")
            angles = tuple(
                float(value) for value in args.angles.split(",") if value.strip()
            )
            written = render_cameras(
                godot, replay, replay_path, os.path.join(args.root, "camera"), angles
            )
            for angle, paths in written.items():
                targets = [
                    os.path.join(
                        args.stills, "camera", f"e{angle:g}", os.path.basename(path)
                    )
                    for path in paths
                ]
                save_stills(paths, targets, args.still_scale)
            print(f"    {sum(len(v) for v in written.values())} stills")

        if steps["frames"]:
            print("=== sequence ===")
            render_frames(godot, replay, replay_path, render_dir, args.elevation)

        if steps["sections"]:
            print("=== section stills ===")
            extract_moments(
                replay,
                frames_dir,
                os.path.join(args.stills, "sections"),
                SECTION_MOMENTS,
                args.still_scale,
            )

        if steps["heroes"]:
            print("=== hero stills ===")
            extract_moments(
                replay, frames_dir, args.stills, HERO_MOMENTS, args.still_scale
            )

        if steps["video"]:
            print("=== video ===")
            encode_video(
                replay, frames_dir, os.path.join(args.root, "neon_machine_polish.mp4")
            )

        if steps["countries"]:
            print("=== country badge experiment ===")
            written = render_countries(
                godot,
                replay,
                replay_path,
                os.path.join(args.root, "countries"),
                args.elevation,
            )
            country_sheets(
                written, os.path.join(args.stills, "countries"), args.still_scale
            )

        if steps["before"]:
            print("=== before and after ===")
            before_after(args.stills, os.path.join(args.stills, "before_after"))

        if steps["phone"]:
            print("=== phone-size review ===")
            written_phone = phone_previews(
                args.stills, os.path.join(args.stills, "phone")
            )
            print(f"    {len(written_phone)} previews at {PHONE_SCALE:.2f}")
    # `RenderError` is in here because `find_godot` is borrowed from
    # `render_replay.py` and raises its error, not this file's. It is a sibling
    # of `ProofError` rather than an ancestor, so leaving it out meant a
    # mistyped `--godot` came back as a traceback instead of one line saying
    # which executable was not found.
    except (
        ProofError,
        RenderError,
        encode.EncodeError,
        OSError,
        ValueError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print("\nproof complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
