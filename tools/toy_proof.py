"""Produce the premium-toy art-direction proof: variants, hero stills, clip.

The front door of the toy style lock, and a sibling of `tools/neon_proof.py`
rather than a change to it. The neon proof still runs, still renders, and is
still the thing this one is measured against - it is the *negative* comparison
the brief names, and a tool that overwrote it would destroy the comparison.

    python tools/toy_proof.py --seed 7 --all

Steps, and each can be asked for on its own:

    --replay      simulate the course and export the replay this all reads
    --variants    the three palettes at one moment, from one build, one replay
    --shots       the three hero framings, in the selected variant
    --hero        the single deliverable still, docs/validation/.../hero.png
    --noglow      the same hero frame with bloom switched off
    --phone       every still again at the size a Short is watched at
    --frames      the full 1080x1920 sequence for the clip
    --video       the four-to-six second motion proof
    --comparison  target concept | V1.1 | new toy style, as one sheet
    --all         all of the above, in that order

## What is frozen

Everything about the race. This tool never balances, re-seeds, curates or
re-simulates between steps: the replay is written once and every later step
reads it, so the variant comparison, the hero stills and the video are the
same race at the same instants. The physics is the existing two-dimensional
solver, untouched, and the winner is whoever the existing simulation says.
The brief asks for appearance to be judged and nothing else, and a comparison
in which two frames differ in more than one thing is not a comparison.

## Why eight racers

The brief asks for six to ten, and for them to be big. Sixteen marbles at the
size that reads on a phone is a bowl with no bowl visible in it. Eight is the
field the style prototype is shot with; it is not a decision about the final
race, which is why nothing here writes it anywhere but its own replay.

Godot is found the way the rest of the project finds it: `--godot`, then
`$GODOT_BIN`, then the PATH.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race.courses.neon import NEON_COURSE_ID  # noqa: E402
from rendering import encode  # noqa: E402
from rendering.render_plan import (  # noqa: E402
    FRAMES_SUBDIR,
    RENDER_FPS,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    frame_filename,
)
from tools.neon_proof import (  # noqa: E402
    ProofError,
    compose,
    export_replay,
    gate_frame,
    load_replay,
    moment_frame,
    run_godot,
    save_stills,
)
from tools.render_replay import (  # noqa: E402
    GODOT_PROJECT,
    PROJECT_ROOT,
    RENDER_SCENE,
    RenderError,
    find_godot,
)

DEFAULT_SEED = 7
DEFAULT_ROOT = os.path.join("output", "toy_style_lock")
DEFAULT_STILLS = os.path.join("docs", "validation", "toy_style_lock")

# The reference the whole exercise is aimed at, and the frame the current
# direction is being replaced *because of*. Both are committed, so the
# comparison sheet can be built without re-rendering either.
CONCEPT = os.path.join("docs", "references", "neon_marble_machine_concept.png")
V11_HERO = os.path.join("docs", "validation", "neon_v11", "bowl_hero.png")

# Six to ten, per the brief. See the module docstring.
TOY_RACER_COUNT = 8

# The three palettes, and the one this prototype ships on. `--variant`
# overrides the selection at render time so the sweep comes out of one build
# of one scene from one replay - the brief's "identical geometry/camera where
# possible so palette is actually being compared", enforced by construction
# rather than by care.
VARIANTS = ("a", "b", "c")
VARIANT_NAMES = {
    "a": "A  Pearl + Aqua",
    "b": "B  Warm Toy",
    "c": "C  Futuristic Candy",
}
# Chosen by eye off `docs/validation/toy_style_lock/variants.png` and its
# phone-scale twin, which is the only way this decision can honestly be made.
# See `docs/toy_machine_visual_style_lock.md` for why A over B and C.
SELECTED_VARIANT = "a"

# The three framings the brief asks to be judged on. Each is a fixed
# product-photography lens rather than a moment of the follow-cam: the
# question is whether the object is desirable, and a shot that is wherever
# the leaders happen to have got to answers a different one.
SHOTS = ("a", "b", "c")
SHOT_NAMES = {
    "a": "A  establishing",
    "b": "B  bowl hero",
    "c": "C  track hero",
}
# Where each shot is taken, in seconds from the release. Chosen so the field
# is in the part of the machine the shot is about.
SHOT_MOMENTS = {"a": 2.05, "b": 2.32, "c": 4.60}

# The hero still: which shot and which variant the single deliverable frame
# is. The brief's most important output.
HERO_SHOT = "a"

# The clip. Four to six seconds, per the brief.
VIDEO_LEAD_IN = 0.9
VIDEO_SECONDS = 5.0

# What a Short is actually watched at: 0.28 of 1080x1920 is 302x538.
PHONE_SCALE = 0.28
STILL_SCALE = 0.5


# --- rendering --------------------------------------------------------------


def godot_command(
    godot: str,
    replay_path: str,
    out_dir: str,
    total: int,
    variant: str,
    shot: str = "",
    stills: tuple[int, ...] = (),
    no_glow: bool = False,
) -> list[str]:
    """One Godot invocation, as an argument list.

    `--race-style=toy` is the whole difference from `neon_proof.py`: the same
    scene tree, the same offline renderer and the same clock, with the toy
    scene in place of the neon one. `--toy-variant` and `--toy-shot` are read
    at render time for the reason every other sweep in this project is - so
    the frames being compared come out of one build of one scene.
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
        "--race-style=toy",
        f"--toy-variant={variant}",
    ]
    if shot:
        command.append(f"--toy-shot={shot}")
    if stills:
        command.append(f"--stills={','.join(str(index) for index in stills)}")
    if no_glow:
        command.append("--toy-no-glow=1")
    return command


def render_stills(
    godot: str,
    replay: dict,
    replay_path: str,
    out_dir: str,
    variant: str,
    shot: str,
    moments: tuple[float, ...],
    no_glow: bool = False,
) -> list[str]:
    """A handful of moments, one Godot run, nothing else rendered."""
    total = len(replay["frames"])
    indices = tuple(moment_frame(replay, at) for at in moments)
    os.makedirs(out_dir, exist_ok=True)
    run_godot(
        godot_command(
            godot, replay_path, out_dir, total, variant, shot, indices, no_glow
        ),
        f"variant {variant} shot {shot or 'follow'}",
    )
    written = []
    for index in indices:
        path = os.path.join(out_dir, f"still_{index:06d}.png")
        if not os.path.isfile(path):
            raise ProofError(f"Godot wrote no still at {path}")
        written.append(path)
    return written


def render_variants(
    godot: str, replay: dict, replay_path: str, out_root: str
) -> dict[str, str]:
    """The same frame in all three palettes, from the same shot.

    One directory per variant, and the geometry, the camera, the replay and
    the moment are identical across them. What differs is the palette, which
    is the only thing the comparison is about.
    """
    written: dict[str, str] = {}
    for variant in VARIANTS:
        out_dir = os.path.join(out_root, f"variant_{variant}")
        print(f"    {VARIANT_NAMES[variant]} -> {out_dir}")
        stills = render_stills(
            godot,
            replay,
            replay_path,
            out_dir,
            variant,
            HERO_SHOT,
            (SHOT_MOMENTS[HERO_SHOT],),
        )
        written[variant] = stills[0]
    return written


def render_shots(
    godot: str, replay: dict, replay_path: str, out_root: str, variant: str
) -> dict[str, str]:
    """The three hero framings, in one palette."""
    written: dict[str, str] = {}
    for shot in SHOTS:
        out_dir = os.path.join(out_root, f"shot_{shot}")
        print(f"    {SHOT_NAMES[shot]} -> {out_dir}")
        stills = render_stills(
            godot,
            replay,
            replay_path,
            out_dir,
            variant,
            shot,
            (SHOT_MOMENTS[shot],),
        )
        written[shot] = stills[0]
    return written


def render_sequence(
    godot: str, replay: dict, replay_path: str, render_dir: str, variant: str
) -> str:
    """The whole sequence, in the shipped palette, for the clip."""
    frames_dir = os.path.join(render_dir, FRAMES_SUBDIR)
    os.makedirs(frames_dir, exist_ok=True)
    for name in os.listdir(frames_dir):
        if name.startswith("frame_") and name.endswith(".png"):
            os.remove(os.path.join(frames_dir, name))

    total = len(replay["frames"])
    print(f"    {total} frames -> {frames_dir}")
    run_godot(
        godot_command(godot, replay_path, frames_dir, total, variant),
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


# --- video ------------------------------------------------------------------


def video_window(replay: dict) -> tuple[int, int]:
    """Which frames the clip is cut from. First frame, and how many."""
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
        f"  ({count / RENDER_FPS:.2f}s at {RENDER_FPS}fps, no audio)"
    )
    completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    if completed.returncode != 0:
        raise ProofError(f"ffmpeg exited {completed.returncode}")
    print(f"    wrote {output} ({os.path.getsize(output) / 1024 / 1024:.1f} MiB)")
    return output


# --- sheets -----------------------------------------------------------------


def variant_sheet(written: dict[str, str], out_dir: str, scale: float) -> str:
    """The three palettes side by side, at review size."""
    pairs = []
    for variant in VARIANTS:
        if variant not in written:
            continue
        scaled = os.path.join(out_dir, f".variant_{variant}.png")
        save_stills([written[variant]], [scaled], scale)
        pairs.append((VARIANT_NAMES[variant], scaled))
    target = os.path.join(out_dir, "variants.png")
    compose(pairs, target)
    for _, path in pairs:
        if os.path.basename(path).startswith("."):
            os.remove(path)
    return target


def shot_sheet(written: dict[str, str], out_dir: str, scale: float) -> str:
    """The three hero framings side by side."""
    pairs = []
    for shot in SHOTS:
        if shot not in written:
            continue
        scaled = os.path.join(out_dir, f".shot_{shot}.png")
        save_stills([written[shot]], [scaled], scale)
        pairs.append((SHOT_NAMES[shot], scaled))
    target = os.path.join(out_dir, "shots.png")
    compose(pairs, target)
    for _, path in pairs:
        if os.path.basename(path).startswith("."):
            os.remove(path)
    return target


# The concept sheet is a whole info page - a hero render, seven section
# panels, an alternative angle and a legend. Only the hero render is a
# comparable subject, and it is the tall column down the left. These are its
# pixel bounds in the committed 1214x1295 file, measured off it once and
# stated here so the comparison crops the same way every time.
CONCEPT_CROP = (88, 60, 300, 1240)


def comparison_sheet(hero: str, out_dir: str) -> str:
    """TARGET CONCEPT | V1.1 | NEW TOY STYLE, at one subject height.

    The mandatory deliverable, and the only one that answers the brief's
    actual question.

    Two things make it a fair comparison rather than three pictures in a row.
    The concept is cropped to its own hero column, because putting a whole
    multi-panel info sheet beside two portrait renders compares page layout
    rather than art direction. And all three panels are scaled to a common
    *height*, not a common width, which is what puts the machines at similar
    apparent size in a portrait strip.
    """
    import pygame

    pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()

    panels = [
        ("TARGET CONCEPT", CONCEPT, True),
        ("V1.1  neon", V11_HERO, False),
        ("NEW  toy style", hero, False),
    ]
    for _, path, _ in panels:
        if not os.path.isfile(path):
            raise ProofError(f"comparison needs a panel at {path}")

    height = 1100
    scaled = []
    for caption, path, crop in panels:
        image = pygame.image.load(path)
        if crop:
            left, top, right, bottom = CONCEPT_CROP
            right = min(right, image.get_width())
            bottom = min(bottom, image.get_height())
            column = pygame.Surface((right - left, bottom - top))
            column.blit(image, (0, 0), pygame.Rect(
                left, top, right - left, bottom - top))
            image = column
        width = max(1, int(round(image.get_width() * height / image.get_height())))
        scaled.append((caption, pygame.transform.smoothscale(image, (width, height))))

    os.makedirs(out_dir, exist_ok=True)
    staged = []
    for index, (caption, image) in enumerate(scaled):
        path = os.path.join(out_dir, f".panel{index}.png")
        pygame.image.save(image, path)
        staged.append((caption, path))
    target = os.path.join(out_dir, "comparison.png")
    compose(staged, target)
    for _, path in staged:
        os.remove(path)
    return target


# --- the tool ---------------------------------------------------------------


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--racers", type=int, default=TOY_RACER_COUNT)
    parser.add_argument("--variant", choices=VARIANTS, default=SELECTED_VARIANT)
    parser.add_argument("--out", default=DEFAULT_ROOT)
    parser.add_argument("--stills", default=DEFAULT_STILLS)
    parser.add_argument("--still-scale", type=float, default=STILL_SCALE)
    parser.add_argument("--godot", default=None)
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--variants", action="store_true")
    parser.add_argument("--shots", action="store_true")
    parser.add_argument("--hero", action="store_true")
    parser.add_argument("--noglow", action="store_true")
    parser.add_argument("--phone", action="store_true")
    parser.add_argument("--frames", action="store_true")
    parser.add_argument("--video", action="store_true")
    parser.add_argument("--comparison", action="store_true")
    parser.add_argument("--all", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    every = args.all or not any(
        [
            args.replay,
            args.variants,
            args.shots,
            args.hero,
            args.noglow,
            args.phone,
            args.frames,
            args.video,
            args.comparison,
        ]
    )

    root = args.out
    stills_root = args.stills
    replay_path = os.path.join(root, f"toy_{args.seed}.json")
    scale = args.still_scale

    try:
        if every or args.replay:
            print("=== replay ===")
            export_replay(replay_path, args.seed, args.racers)

        needs_godot = every or any(
            [args.variants, args.shots, args.hero, args.noglow, args.frames]
        )
        godot = ""
        if needs_godot:
            godot = find_godot(args.godot)

        replay = load_replay(replay_path) if not (every or args.replay) else None
        if replay is None:
            replay = load_replay(replay_path)

        if every or args.variants:
            print("=== variants ===")
            written = render_variants(godot, replay, replay_path, root)
            sheet = variant_sheet(written, os.path.join(stills_root), scale)
            print(f"    sheet -> {sheet}")

        if every or args.shots:
            print("=== hero shots ===")
            written = render_shots(godot, replay, replay_path, root, args.variant)
            sheet = shot_sheet(written, os.path.join(stills_root), scale)
            print(f"    sheet -> {sheet}")
            for shot, source in written.items():
                target = os.path.join(stills_root, f"shot_{shot}.png")
                save_stills([source], [target], scale)
                print(f"    shot {shot} -> {target}")

        if every or args.hero:
            print("=== hero still ===")
            written = render_stills(
                godot,
                replay,
                replay_path,
                os.path.join(root, "hero"),
                args.variant,
                HERO_SHOT,
                (SHOT_MOMENTS[HERO_SHOT],),
            )
            target = os.path.join(stills_root, "hero.png")
            save_stills(written, [target], 1.0)
            print(f"    {target}")

        if every or args.noglow:
            print("=== hero, no glow ===")
            written = render_stills(
                godot,
                replay,
                replay_path,
                os.path.join(root, "noglow"),
                args.variant,
                HERO_SHOT,
                (SHOT_MOMENTS[HERO_SHOT],),
                no_glow=True,
            )
            target = os.path.join(stills_root, "hero_no_glow.png")
            save_stills(written, [target], scale)
            print(f"    {target}")

        if every or args.phone:
            print("=== phone previews ===")
            phone_dir = os.path.join(stills_root, "phone")
            names = ["hero.png", "hero_no_glow.png"]
            names += [f"shot_{shot}.png" for shot in SHOTS]
            for name in names:
                source = os.path.join(stills_root, name)
                if not os.path.isfile(source):
                    continue
                # The phone preview is taken off the committed still, whose
                # own scale is half - so the factor is the ratio, not the
                # figure, or a half-size source would land at half the size
                # a phone actually shows.
                factor = PHONE_SCALE / (1.0 if name == "hero.png" else scale)
                save_stills([source], [os.path.join(phone_dir, name)], factor)
                print(f"    {name}")

        if every or args.frames:
            print("=== sequence ===")
            render_sequence(godot, replay, replay_path, root, args.variant)

        if every or args.video:
            print("=== video ===")
            encode_video(
                replay,
                os.path.join(root, FRAMES_SUBDIR),
                os.path.join(root, "toy_machine_visual_lock.mp4"),
            )

        if every or args.comparison:
            print("=== comparison ===")
            target = comparison_sheet(
                os.path.join(stills_root, "hero.png"), stills_root
            )
            print(f"    {target}")

    except (ProofError, RenderError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print("\nproof complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
