"""Entry point: run a seeded simulation with a live pygame preview."""

from __future__ import annotations

import argparse

from engine.randomizer import generate_seed
from engine.simulation import PHYSICS_HZ, Simulation
from rendering.renderer import DEFAULT_SCALE, Renderer

TARGET_FPS = 60


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simulation Factory preview")
    parser.add_argument(
        "--seed", type=int, default=None, help="simulation seed (random if omitted)"
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=DEFAULT_SCALE,
        help="preview scale relative to the 1080x1920 logical canvas",
    )
    return parser.parse_args()


def report_start(sim: Simulation) -> None:
    print(f"seed={sim.seed} physics={PHYSICS_HZ}Hz render<={TARGET_FPS}fps")
    for ball in sim.balls:
        x, y = ball.position
        vx, vy = ball.velocity
        print(
            f"  ball {ball.ball_id}: pos=({x:.1f}, {y:.1f}) "
            f"vel=({vx:.1f}, {vy:.1f}) r={ball.radius:.1f}"
        )


def main() -> None:
    args = parse_args()
    seed = args.seed if args.seed is not None else generate_seed()

    sim = Simulation(seed)
    report_start(sim)

    renderer = Renderer(seed, scale=args.scale)
    try:
        running = True
        while running:
            frame_seconds = renderer.tick(TARGET_FPS)
            running = renderer.handle_window_events()
            sim.advance(frame_seconds)
            renderer.draw(sim)
    finally:
        renderer.close()


if __name__ == "__main__":
    main()
