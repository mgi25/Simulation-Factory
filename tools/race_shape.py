"""Draw the *shape* of a race: who led, where the winner was, how spread out.

Three charts stacked, one race per column, so two courses can be put beside
each other and compared as pictures rather than as tables:

    LEADER        a colour band per sample - which racer was in front
    WINNER RANK   the eventual winner's position over the whole race
    PACK SPREAD   course progress between the leader and the last racer

The first two are the V0.4 brief's central question drawn directly. A V0.3
race is a single band of colour with a flat line under it: one racer takes the
front early and the picture stops changing. A race worth watching is a striped
band and a line that climbs.

    python -m tools.race_shape --out docs/validation/race_v04/shape.png \\
        --race prototype:839271:10 --race machine:20411:16

Drawn with pygame rather than a plotting library because pygame is already a
dependency and this is three bar charts - adding matplotlib to the project to
draw them would be a poor trade.
"""

from __future__ import annotations

import argparse
import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from race.analysis import RaceTrace, race_metrics, trace_race  # noqa: E402
from race.config import RACER_COLORS  # noqa: E402

__all__ = ["draw_shape", "parse_race"]

PANEL_WIDTH = 640
PANEL_GAP = 28
CHART_HEIGHT = 190
CHART_GAP = 46
MARGIN = 34
TITLE_HEIGHT = 100

BACKGROUND = (14, 17, 24)
PANEL = (22, 26, 35)
GRID = (46, 53, 68)
TEXT = (226, 231, 240)
DIM = (140, 150, 168)
ACCENT = (86, 196, 240)


def parse_race(spec: str) -> tuple[str, int, int]:
    """`course:seed:racers`, with the racer count optional."""
    parts = spec.split(":")
    if len(parts) < 2:
        raise SystemExit(f"--race wants course:seed[:racers], got {spec!r}")
    course, seed = parts[0], int(parts[1])
    racers = int(parts[2]) if len(parts) > 2 else 10
    return (course, seed, racers)


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    return pygame.font.SysFont("consolas,dejavusansmono,monospace", size, bold=bold)


def _text(surface, message, x, y, size=17, color=TEXT, bold=False) -> int:
    rendered = _font(size, bold).render(message, True, color)
    surface.blit(rendered, (x, y))
    return rendered.get_height()


def _chart_frame(surface, x, y, width, height, title, subtitle="") -> None:
    pygame.draw.rect(surface, PANEL, (x, y, width, height))
    pygame.draw.rect(surface, GRID, (x, y, width, height), 1)
    _text(surface, title, x, y - 26, 16, DIM, bold=True)
    if subtitle:
        rendered = _font(14).render(subtitle, True, DIM)
        surface.blit(rendered, (x + width - rendered.get_width(), y - 24))


def _leader_band(surface, trace: RaceTrace, x, y, width, height) -> None:
    """One vertical stripe per sample, coloured by whoever was leading."""
    window = trace.decided
    if not window:
        return
    step = width / max(1, len(window))
    for index, sample in enumerate(window):
        leader = sample.leader
        if leader is None:
            continue
        color = RACER_COLORS[leader % len(RACER_COLORS)]
        left = x + index * step
        pygame.draw.rect(
            surface, color, (int(left), y + 1, max(1, int(step) + 1), height - 2)
        )
    # A hatch wherever first place changed hands: the eye finds the count
    # faster than it finds the colour boundaries.
    previous = None
    for index, sample in enumerate(window):
        if previous is not None and sample.leader != previous:
            left = int(x + index * step)
            pygame.draw.line(surface, (12, 14, 20), (left, y), (left, y + height), 2)
        previous = sample.leader


def _line_chart(surface, values, x, y, width, height, low, high, color) -> None:
    if not values:
        return
    span = max(1e-6, high - low)
    points = []
    for index, value in enumerate(values):
        px = x + width * index / max(1, len(values) - 1)
        py = y + height - height * (min(high, max(low, value)) - low) / span
        points.append((px, py))
    for fraction in (0.25, 0.5, 0.75):
        gy = int(y + height * fraction)
        pygame.draw.line(surface, GRID, (x + 1, gy), (x + width - 1, gy), 1)
    if len(points) > 1:
        pygame.draw.lines(surface, color, False, points, 2)


def _lock_marker(surface, trace: RaceTrace, x, y, width, height) -> None:
    """Where the winner took first place for the last time."""
    record = race_metrics(trace)
    fraction = record.get("winner_lock_fraction")
    if fraction is None:
        return
    px = int(x + width * min(1.0, max(0.0, fraction)))
    pygame.draw.line(surface, (255, 220, 120), (px, y), (px, y + height), 2)


def _panel(surface, trace: RaceTrace, x, y, width, label: str) -> None:
    record = race_metrics(trace)
    winner = record["winner_id"]
    _text(surface, label, x, y, 21, TEXT, bold=True)
    _text(
        surface,
        f"seed {trace.seed}   {trace.racer_count} racers   "
        f"winner {'-' if winner is None else winner + 1}   "
        f"{record['winner_time'] or 0.0:.1f}s",
        x,
        y + 26,
        15,
        DIM,
    )
    lock = record.get("winner_lock_fraction")
    _text(
        surface,
        f"lock {0.0 if lock is None else lock:.0%}   "
        f"lead changes {record['lead_changes']}   "
        f"winner worst rank {record['winner_worst_rank']}",
        x,
        y + 46,
        15,
        ACCENT,
    )

    top = y + TITLE_HEIGHT
    _chart_frame(surface, x, top, width, 46, "LEADER", "colour = racer in front")
    _leader_band(surface, trace, x, top, width, 46)

    window = trace.decided
    top += 46 + CHART_GAP
    _chart_frame(
        surface, x, top, width, CHART_HEIGHT, "WINNER RANK", "1st at the top"
    )
    ranks = [
        -float(sample.rank_of(winner)) if winner is not None else 0.0
        for sample in window
    ]
    _line_chart(
        surface, ranks, x, top, width, CHART_HEIGHT,
        -float(trace.racer_count), -1.0, (120, 230, 150),
    )
    _lock_marker(surface, trace, x, top, width, CHART_HEIGHT)

    top += CHART_HEIGHT + CHART_GAP
    _chart_frame(
        surface, x, top, width, CHART_HEIGHT, "PACK SPREAD",
        "leader to last, as a share of the course",
    )
    _line_chart(
        surface, [sample.spread() for sample in window],
        x, top, width, CHART_HEIGHT, 0.0, 1.0, (250, 170, 90),
    )

    top += CHART_HEIGHT + CHART_GAP
    _chart_frame(
        surface, x, top, width, CHART_HEIGHT, "COMPETITIVE",
        "racers within 10% of the lead",
    )
    _line_chart(
        surface, [float(sample.competitive()) for sample in window],
        x, top, width, CHART_HEIGHT, 0.0, float(trace.racer_count), ACCENT,
    )


def draw_shape(races: list[tuple[str, int, int]], out_path: str) -> str:
    pygame.init()
    pygame.font.init()

    traces = []
    for course, seed, racers in races:
        _, trace = trace_race(seed, course_name=course, racer_count=racers)
        traces.append((f"{course}  {racers} racers", trace))

    width = MARGIN * 2 + len(traces) * PANEL_WIDTH + (len(traces) - 1) * PANEL_GAP
    height = MARGIN * 2 + TITLE_HEIGHT + 46 + 3 * (CHART_HEIGHT + CHART_GAP) + 20
    surface = pygame.Surface((width, height))
    surface.fill(BACKGROUND)

    for index, (label, trace) in enumerate(traces):
        x = MARGIN + index * (PANEL_WIDTH + PANEL_GAP)
        _panel(surface, trace, x, MARGIN, PANEL_WIDTH, label)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    pygame.image.save(surface, out_path)
    pygame.quit()
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Draw the shape of one or more races")
    parser.add_argument(
        "--race", action="append", required=True,
        help="course:seed[:racers], repeatable",
    )
    parser.add_argument("--out", default="output/race_shape.png")
    args = parser.parse_args()

    races = [parse_race(spec) for spec in args.race]
    path = draw_shape(races, args.out)
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
