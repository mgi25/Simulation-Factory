"""Entry point: run a seeded obstacle race, with or without a window.

The sibling of `main.py`, which runs a duel. Kept separate rather than
folded in behind a mode flag because the two share no rules, no physics and
no HUD - only the canvas they are composed for.
"""

from __future__ import annotations

import argparse
import os

from engine.arena import CANVAS_HEIGHT
from race.camera import RaceCamera
from race.config import PHYSICS_DT, PHYSICS_HZ, RACER_COUNT
from race.courses import COURSE_NAMES, DEFAULT_COURSE
from race.manager import RaceManager
from race.seeds import generate_seed
from race.simulation import RaceSimulation
from race.telemetry import format_summary

RENDER_FPS = 60
# Physics ticks per drawn frame. Fixed, never derived from real elapsed
# time: a race has to run the same number of ticks on every machine or the
# same seed would not give the same race. A machine that cannot hold the
# frame rate plays the race slowly instead of playing a different one.
TICKS_PER_FRAME = PHYSICS_HZ // RENDER_FPS
PREVIEW_SCALE = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulation Factory race preview")
    parser.add_argument(
        "--seed", type=int, default=None, help="race seed (random if omitted)"
    )
    parser.add_argument(
        "--course", choices=COURSE_NAMES, default=DEFAULT_COURSE, help="which course to run"
    )
    parser.add_argument(
        "--racers", type=int, default=RACER_COUNT, help="how many racers to start"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=PREVIEW_SCALE,
        help="preview scale relative to the 1080x1920 logical canvas",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="run with no window and print the summary",
    )
    parser.add_argument(
        "--export-replay",
        metavar="PATH",
        default=None,
        help="run headlessly and write a deterministic race replay to PATH",
    )
    parser.add_argument(
        "--debug", action="store_true", help="start with the debug overlay visible"
    )
    parser.add_argument(
        "--snapshot",
        metavar="PATH",
        default=None,
        help="save PNG frames to PATH_<seconds>.png and exit (implies no window)",
    )
    parser.add_argument(
        "--snapshot-at",
        metavar="SECONDS",
        default="0.5,8,14,20",
        help="comma-separated race times to snapshot",
    )
    return parser.parse_args()


def new_race(args: argparse.Namespace, seed: int) -> tuple[RaceManager, RaceCamera]:
    """Build a fresh race and a camera framed on the starting grid."""
    sim = RaceSimulation(
        seed, course_name=args.course, racer_count=max(1, args.racers)
    )
    manager = RaceManager(sim)
    camera = RaceCamera(sim.course, CANVAS_HEIGHT)
    camera.snap_to(sim.racers)
    return manager, camera


def run_headless(args: argparse.Namespace, seed: int) -> None:
    manager, _ = new_race(args, seed)
    manager.run()
    print(format_summary(manager))


def run_export(args: argparse.Namespace, seed: int) -> None:
    """Record one race to a replay file and report what is in it.

    The production front door: no window, no display driver, no pygame at
    all. The race is run by the exporter rather than here, because the
    exporter owns the sampling clock and the camera track - a second loop
    that stepped the race its own way would eventually step it differently.
    """
    from replay.race_exporter import RACE_REPLAY_VERSION, record_race, write_replay

    replay = record_race(seed, course_name=args.course, racer_count=max(1, args.racers))
    path = write_replay(replay, args.export_replay)

    course = replay["course"]
    result = replay["result"]
    routes = len(course["branches"]) or 1
    winner_time = result["winner_time"]
    duration = result["duration"]
    size = os.path.getsize(path)

    print(f"=== RACE REPLAY v{RACE_REPLAY_VERSION} ===")
    print(f"Seed: {replay['seed']}")
    print(
        f"Course: {course['id']}  {len(course['pieces'])} pieces,"
        f" {len(course['spinners'])} spinners,"
        f" {len(course['checkpoints'])} checkpoints, {routes} route(s)"
    )
    print(f"Racers: {len(replay['racers'])}")
    print(f"Winner: {result['winner_name'] or 'NONE'}")
    print(f"Time: {'n/a' if winner_time is None else f'{winner_time:.2f}s'}")
    print(f"Duration: {'n/a' if duration is None else f'{duration:.2f}s'}")
    print(f"Finished: {result['racers_finished']}/{len(replay['racers'])}")
    print(
        f"Frames: {len(replay['frames'])} @ {replay['fps']}fps"
        f"  ({len(replay['frames']) / replay['fps']:.2f}s)"
    )
    print(f"Events: {len(replay['events'])}")
    print(f"Wrote {path}  ({size / 1024 / 1024:.1f} MiB)")


def run_snapshots(args: argparse.Namespace, seed: int) -> None:
    """Render a race with no display and save frames at fixed race times.

    The visual check that does not need a human at a window: it is how the
    course geometry, the spinners and the HUD were verified, and how a
    regression in any of them would be caught.
    """
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    from rendering.race_renderer import RaceRenderer

    wanted = sorted(
        float(value) for value in args.snapshot_at.split(",") if value.strip()
    )
    manager, camera = new_race(args, seed)
    renderer = RaceRenderer(seed, scale=args.scale, debug=args.debug)
    saved = []
    try:
        pending = list(wanted)
        while pending:
            for _ in range(TICKS_PER_FRAME):
                if not manager.step():
                    break
            camera.update(manager.sim.racers, TICKS_PER_FRAME * PHYSICS_DT)
            renderer.draw(manager, camera)
            while pending and manager.race_time >= pending[0]:
                at = pending.pop(0)
                saved.append(renderer.save_frame(f"{args.snapshot}_{at:g}s.png"))
            if manager.complete:
                # Race over before the last requested time: save the final
                # frame under the remaining names rather than looping.
                for at in pending:
                    saved.append(renderer.save_frame(f"{args.snapshot}_{at:g}s.png"))
                break
        # Snapshots taken; finish the race off so the summary printed below
        # describes a whole race rather than however far the last requested
        # frame happened to get.
        manager.run()
    finally:
        renderer.close()
    print(format_summary(manager))
    for path in saved:
        print(f"  wrote {path}")


def run_preview(args: argparse.Namespace, seed: int) -> None:
    """The interactive loop. Owns the race lifecycle; the window does not."""
    from rendering.race_renderer import (
        COMMAND_NEW_SEED,
        COMMAND_QUIT,
        COMMAND_RESTART,
        RaceRenderer,
    )

    manager, camera = new_race(args, seed)
    renderer = RaceRenderer(seed, scale=args.scale, debug=args.debug)
    report_start(manager)
    try:
        reported = False
        while True:
            renderer.tick(RENDER_FPS)
            commands = renderer.handle_events()
            if COMMAND_QUIT in commands:
                break
            if commands & {COMMAND_RESTART, COMMAND_NEW_SEED}:
                if COMMAND_NEW_SEED in commands:
                    seed = generate_seed()
                manager, camera = new_race(args, seed)
                renderer.set_caption(seed)
                renderer.paused = False
                reported = False
                report_start(manager)

            if not renderer.paused:
                for _ in range(TICKS_PER_FRAME):
                    if not manager.step():
                        break
                camera.update(manager.sim.racers, TICKS_PER_FRAME * PHYSICS_DT)

            if manager.complete and not reported:
                print(format_summary(manager))
                print("  R restart  N new seed  Space pause  F1 debug  Esc quit")
                reported = True
            renderer.draw(manager, camera)
    finally:
        renderer.close()


def report_start(manager: RaceManager) -> None:
    sim = manager.sim
    course = sim.course
    print(
        f"seed={sim.seed} course={course.course_id} racers={len(sim.racers)} "
        f"physics={PHYSICS_HZ}Hz drop={course.height:.0f}px "
        f"checkpoints={len(course.checkpoints)}"
    )


def main() -> None:
    args = parse_args()
    seed = args.seed if args.seed is not None else generate_seed()

    if args.export_replay:
        run_export(args, seed)
    elif args.snapshot:
        run_snapshots(args, seed)
    elif args.headless:
        run_headless(args, seed)
    else:
        run_preview(args, seed)


if __name__ == "__main__":
    main()
