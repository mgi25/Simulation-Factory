"""Entry point: run a seeded battle with a live pygame preview."""

from __future__ import annotations

import argparse

from engine.randomizer import generate_seed
from engine.simulation import PHYSICS_HZ, Simulation
from modes.power_battle import BATTLE_DURATION_SECONDS, PowerBattleMode
from replay.exporter import record_battle, write_replay

TARGET_FPS = 60
PREVIEW_SCALE = 0.5


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulation Factory preview")
    parser.add_argument(
        "--seed", type=int, default=None, help="simulation seed (random if omitted)"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=PREVIEW_SCALE,
        help="preview scale relative to the 1080x1920 logical canvas",
    )
    parser.add_argument(
        "--export-replay",
        metavar="PATH",
        default=None,
        help="run headlessly, write a replay JSON to PATH and exit",
    )
    return parser.parse_args()


def report_start(sim: Simulation) -> None:
    print(
        f"seed={sim.seed} physics={PHYSICS_HZ}Hz render<={TARGET_FPS}fps "
        f"limit={BATTLE_DURATION_SECONDS:.0f}s"
    )
    for ball in sim.balls:
        x, y = ball.position
        vx, vy = ball.velocity
        print(
            f"  {ball.name} (id {ball.ball_id}): pos=({x:.1f}, {y:.1f}) "
            f"vel=({vx:.1f}, {vy:.1f}) r={ball.radius:.1f}"
        )


def report_result(mode: PowerBattleMode) -> None:
    health = "  ".join(
        f"{ball.name} {round(ball.health)} HP" for ball in mode.sim.balls
    )
    print(f"{mode.result_text} after {mode.duration:.1f}s  |  {health}")


def export_replay(seed: int, path: str) -> None:
    """Headless path: no pygame, no window, just simulation plus JSON."""
    replay = record_battle(seed)
    write_replay(replay, path)
    result = replay["result"]
    winner = "DRAW" if result["is_draw"] else replay["fighters"][result["winner_id"]]["name"]
    print(
        f"seed={seed} frames={len(replay['frames'])} "
        f"duration={result['duration']:.1f}s result={winner} -> {path}"
    )


def run_preview(sim: Simulation, mode: PowerBattleMode, scale: float) -> None:
    # Imported here so replay export never needs pygame or a display.
    from rendering.renderer import Renderer

    renderer = Renderer(sim.seed, scale=scale)
    try:
        running = True
        reported = False
        while running:
            frame_seconds = renderer.tick(TARGET_FPS)
            running = renderer.handle_window_events()
            mode.advance(frame_seconds)
            if mode.finished and not reported:
                report_result(mode)
                reported = True
            renderer.draw(sim, mode)
    finally:
        renderer.close()


def main() -> None:
    args = parse_args()
    seed = args.seed if args.seed is not None else generate_seed()

    if args.export_replay:
        export_replay(seed, args.export_replay)
        return

    sim = Simulation(seed)
    mode = PowerBattleMode(sim)
    report_start(sim)
    run_preview(sim, mode, args.scale)


if __name__ == "__main__":
    main()
