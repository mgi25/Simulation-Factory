"""The V24 payoff lab: measure the V22.1 finish, then prove three cards on it.

    python tools/sloped_v24_payoff.py --stage all
    python tools/sloped_v24_payoff.py --stage visibility
    python tools/sloped_v24_payoff.py --stage proof --style plate

Nothing here re-simulates and nothing here re-renders the machine. Every proof
is the **delivered V22.1 master**, frame for frame, with a card composited on
top, which is the only way to argue about legibility against a background that
actually exists. The stages, in the order they were run:

    winner      who won seed 5432, from the replay and from a fresh race
    visibility  when the winner is on screen, measured against the pixels
    band        where a card can go, from the row maxima of the real tail
    cards       the three styles, at 1080x1920
    proof       cards over real frames, full size and at 270x480
    compare     the shipped end card and the new one, on one sheet

`--stage visibility`, `band`, `proof` and `compare` need the master's frames.
They are extracted once with ffmpeg into `WORK_DIR` and reused.

## The instrument, and why it is not a projection

`presentation.screen_track` says where a marble *would* land on the frame. It
does not know about the finish gantry, and the finish gantry is most of what
happens to the winner after it crosses. So "is the winner visible" is answered
here by looking for the racer's **own hue** inside the disc the projection
gives, on the rendered pixels: at least 25 per cent of the disc within 22
degrees of the marble's hue, saturated above 0.30 and not in shadow.

That distinction is the whole finding. By the projection the winner is on
screen for the entire tail; by the pixels it is behind a rail for 1.400 s of
it, including every instant either of V22.1's two winner marks is up.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sloped import overlays, presentation, v221, v24_payoff  # noqa: E402
from sloped.v24_payoff import WINNER_INDEX  # noqa: E402

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v24_payoff")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v24_payoff")

REPLAY = os.path.join(OUT_DIR, "race_5432.json")
TRACK = os.path.join(OUT_DIR, "cameras_v221_5432.json")

# The delivered V22.1 master, which is where every proof frame comes from. It
# is not in the branch - `exports/` is ignored on purpose, see `.gitignore` -
# so the default is the sibling checkout the film was delivered from and
# `--film` overrides it.
DEFAULT_FILM = os.path.join(
    "..", "Simulation Factory", "exports", "v221_integration",
    "real_race_v221_master.mp4",
)
DELIVERED = os.path.join(
    "..", "Simulation Factory", "exports", "v221_integration", "real_race_v221.mp4"
)

FPS = 60
# The tail: from the winner's crossing to the last frame of the film.
FIRST_FRAME = int(round(v24_payoff.CROSSING * FPS))
LAST_FRAME = 1591

# The two frames every proof is taken on. The first is the card's own opening
# beat, with the winner behind the rail; the second is 1.0 s later, when it has
# come back out onto the deck underneath the card.
PROOF_FRAMES = ((1434, "23900"), (1494, "24900"))


class LabError(RuntimeError):
    pass


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if not found:
        raise LabError("ffmpeg is not on PATH")
    return found


def frames_dir() -> str:
    return os.path.join(WORK_DIR, "master")


def ensure_frames(film: str) -> str:
    """Pull the tail of the master out once, and keep it."""
    directory = frames_dir()
    marker = os.path.join(directory, f"f{LAST_FRAME:04d}.png")
    if os.path.isfile(marker):
        return directory
    if not os.path.isfile(film):
        raise LabError(
            f"the V22.1 master is not at {film!r}; pass --film with its path"
        )
    os.makedirs(directory, exist_ok=True)
    subprocess.run(
        [
            _ffmpeg(), "-v", "error", "-y", "-i", film,
            "-vf", f"select='gte(n\\,{FIRST_FRAME})'", "-vsync", "0",
            "-start_number", str(FIRST_FRAME),
            os.path.join(directory, "f%04d.png"),
        ],
        check=True,
    )
    return directory


def load_clock() -> tuple[dict[str, Any], dict[str, Any], presentation.Clock]:
    if not os.path.isfile(TRACK):
        raise LabError(
            f"{TRACK} is missing. Build it with:\n"
            "    python -c \"import json;from sloped import v221;"
            "from sloped.course import sloped_course;"
            "json.dump(v221.build_race_track("
            f"json.load(open(r'{REPLAY}')), sloped_course(routes='both')),"
            f"open(r'{TRACK}','w'))\""
        )
    track = json.load(open(TRACK, encoding="utf-8"))
    master = int(round(float(track["duration"]) * FPS)) + 1
    return presentation.load(REPLAY, TRACK, master, prefix=v221.PREVIEW_SECONDS)


# --- stages -----------------------------------------------------------------


def stage_winner() -> dict[str, Any]:
    """Who won, from the replay the film ships - and from a fresh race."""
    replay = json.load(open(REPLAY, encoding="utf-8"))
    events = sorted(
        (e for e in replay["events"] if e["kind"] == "finish_line"),
        key=lambda e: int(e["order"]),
    )
    order = [int(e["id"]) for e in events]
    winner = order[0]
    crossed = float(events[0]["t"])

    print(f"replay {REPLAY}: seed {replay['seed']}")
    print(f"  finish order  {order}")
    print(f"  winner        marble {winner}, crossing replay {crossed}")
    hue = overlays.MARBLE_HUES[winner]
    print(
        f"  colour        {v24_payoff.winner_label(winner)}  "
        f"#{hue[0]:02X}{hue[1]:02X}{hue[2]:02X}  "
        f"hue {v24_payoff._hue_angle(hue):.1f} deg"
    )
    if winner != WINNER_INDEX:
        raise LabError(
            f"the replay's winner is {winner}, the module is pinned to "
            f"{WINNER_INDEX}"
        )
    _, _, clock = load_clock()
    print(f"  film second   {clock.at(crossed):.4f} of {clock.duration:.4f}")
    return {"order": order, "winner": winner, "crossed": crossed}


def _hues() -> list[float]:
    return [v24_payoff._hue_angle(h) for h in overlays.MARBLE_HUES]


def _places(replay, track, clock) -> dict[int, dict[int, tuple[float, float, float]]]:
    rows: dict[int, dict[int, tuple[float, float, float]]] = {}
    window = (v24_payoff.CROSSING, clock.duration)
    for marble in range(len(overlays.MARBLE_HUES)):
        for when, x, y, radius in presentation.screen_track(
            replay, track, clock, marble, window
        ):
            # A near-plane projection blows up to millions of pixels; anything
            # that big is not a marble on the frame, it is the maths giving up.
            if radius > 300 or not (-50 <= x <= 1130) or not (-50 <= y <= 1970):
                continue
            rows.setdefault(int(round(when * FPS)), {})[marble] = (x, y, radius)
    return rows


def _hsv(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    high = pixels.max(axis=2)
    low = pixels.min(axis=2)
    spread = high - low
    safe = np.maximum(spread, 1e-6)
    red, green, blue = pixels[:, :, 0], pixels[:, :, 1], pixels[:, :, 2]
    angle = np.where(
        high == red, ((green - blue) / safe) % 6.0,
        np.where(high == green, ((blue - red) / safe) + 2.0,
                 ((red - green) / safe) + 4.0),
    ) * 60.0
    saturation = np.where(high > 0, spread / np.maximum(high, 1e-6), 0.0)
    return angle, saturation, high


def visible_fraction(
    frame: np.ndarray, marble: int, x: float, y: float, radius: float
) -> float:
    """How much of a racer's projected disc is actually its own colour."""
    reach = max(3.0, radius * 0.75)
    x0, x1 = int(max(0, x - reach)), int(min(overlays.WIDTH, x + reach + 1))
    y0, y1 = int(max(0, y - reach)), int(min(overlays.HEIGHT, y + reach + 1))
    if x1 <= x0 or y1 <= y0:
        return 0.0
    patch = frame[y0:y1, x0:x1]
    ys, xs = np.mgrid[y0:y1, x0:x1]
    disc = ((xs - x) ** 2 + (ys - y) ** 2) <= reach * reach
    if not disc.any():
        return 0.0
    angle, saturation, value = _hsv(patch)
    delta = np.abs((angle - _hues()[marble] + 180.0) % 360.0 - 180.0)
    hit = disc & (delta < 22.0) & (saturation > 0.30) & (value > 0.12)
    return float(hit.sum()) / float(disc.sum())


def stage_visibility(film: str) -> dict[str, Any]:
    """The winner's visibility, frame by frame, against the rendered pixels."""
    directory = ensure_frames(film)
    replay, track, clock = load_clock()
    rows = _places(replay, track, clock)

    curve: dict[int, float] = {}
    others: dict[int, dict[int, float]] = {}
    for number in sorted(rows):
        path = os.path.join(directory, f"f{number:04d}.png")
        if not os.path.isfile(path):
            continue
        frame = np.asarray(Image.open(path).convert("RGB")).astype(np.float32) / 255.0
        seen = {}
        for marble, (x, y, radius) in rows[number].items():
            seen[marble] = visible_fraction(frame, marble, x, y, radius)
        others[number] = seen
        curve[number] = seen.get(WINNER_INDEX, 0.0)

    runs: list[tuple[int, int, bool]] = []
    current: list[Any] | None = None
    for number in sorted(curve):
        on = curve[number] >= 0.25
        if current is None or current[2] != on:
            if current is not None:
                runs.append(tuple(current))
            current = [number, number, on]
        else:
            current[1] = number
    if current is not None:
        runs.append(tuple(current))

    print("winner visibility, threshold 0.25 of the projected disc:")
    for low, high, on in runs:
        print(
            f"  {'VISIBLE' if on else 'hidden ':<7}  "
            f"t {low / FPS:.3f} - {high / FPS:.3f}   "
            f"({(high - low + 1) / FPS:.3f} s)"
        )

    marks = {
        "V22.1 winner ring": (23.100, 23.800),
        "V22.1 end fact": (25.883, 26.533),
        "V24 ring": v24_payoff.schedule()["ring"],
        "V24 card": v24_payoff.schedule()["card"],
    }
    print("\nhow much of each mark has a visible winner under it:")
    for name, (low, high) in marks.items():
        seconds = 0.0
        for number, value in curve.items():
            when = number / FPS
            if low - 1e-9 <= when <= high + 1e-9 and value >= 0.25:
                seconds += 1.0 / FPS
        print(f"  {name:<20} {low:7.3f} - {high:7.3f}   {seconds:.3f} s")

    os.makedirs(DOCS_DIR, exist_ok=True)
    payload = {
        "runs": [
            {"from": low / FPS, "to": high / FPS, "visible": bool(on)}
            for low, high, on in runs
        ],
        "curve": {str(k): round(v, 4) for k, v in curve.items()},
        "marks": {k: list(v) for k, v in marks.items()},
    }
    with open(os.path.join(DOCS_DIR, "winner_visibility.json"), "w",
              encoding="utf-8") as handle:
        json.dump(payload, handle, indent=1)
    return payload


def stage_band(film: str) -> dict[str, Any]:
    """Where a card can live: the tallest row band nothing bright ever enters."""
    directory = ensure_frames(film)
    start = int(round((v24_payoff.CROSSING + 0.8) * FPS))
    stack = []
    for number in range(start, LAST_FRAME + 1, 2):
        path = os.path.join(directory, f"f{number:04d}.png")
        if not os.path.isfile(path):
            continue
        pixels = np.asarray(Image.open(path).convert("RGB")).astype(np.float32)
        stack.append(
            0.2126 * pixels[:, :, 0]
            + 0.7152 * pixels[:, :, 1]
            + 0.0722 * pixels[:, :, 2]
        )
    if not stack:
        raise LabError("no frames to measure the band on")
    corridor = np.stack(stack)[:, :, v24_payoff.GUTTER - 6: overlays.WIDTH
                               - v24_payoff.GUTTER + 6]
    row_max = corridor.max(axis=(0, 2))

    best = (0, -1)
    run_from: int | None = None
    for y in range(overlays.HEIGHT):
        if row_max[y] < 130.0:
            run_from = y if run_from is None else run_from
            if y - run_from > best[1] - best[0]:
                best = (run_from, y)
        else:
            run_from = None
    print(
        f"tallest band with max luma < 130 over the corridor: "
        f"y {best[0]}..{best[1]} ({best[1] - best[0] + 1} px), "
        f"peak {row_max[best[0]:best[1] + 1].max():.1f}"
    )
    print(f"the module uses PAYOFF_BAND = {v24_payoff.PAYOFF_BAND}")
    return {"band": list(best), "peak": float(row_max[best[0]:best[1] + 1].max())}


def stage_cards() -> dict[str, Any]:
    os.makedirs(WORK_DIR, exist_ok=True)
    os.makedirs(DOCS_DIR, exist_ok=True)
    report: dict[str, Any] = {}
    for style in v24_payoff.STYLES:
        card = v24_payoff.build(style)
        path = os.path.join(WORK_DIR, f"card_{style}.png")
        card.image.save(path)
        low, high = v24_payoff.PAYOFF_BAND
        inside = low <= card.box[1] and card.box[3] <= high
        report[style] = {
            "box": list(card.box),
            "in_band": bool(inside),
            "text_contrast": round(card.text_contrast, 2),
            "colour_pixels": card.colour_pixels,
        }
        print(
            f"{style:<6} box {card.box}  in band {inside}  "
            f"contrast {card.text_contrast:.2f}:1  "
            f"colour {card.colour_pixels} px"
        )
    shipped = overlays.end_fact(accent=overlays.MARBLE_HUES[WINNER_INDEX])
    report["shipped_end_fact_colour_pixels"] = v24_payoff._colour_area(
        shipped, overlays.MARBLE_HUES[WINNER_INDEX]
    )
    print(
        f"\nshipped end_fact states the colour in "
        f"{report['shipped_end_fact_colour_pixels']} px"
    )
    return report


def stage_proof(film: str, styles: Sequence[str]) -> dict[str, Any]:
    """Cards over real frames, full size and at the size they are judged at."""
    directory = ensure_frames(film)
    os.makedirs(DOCS_DIR, exist_ok=True)
    report: dict[str, Any] = {}
    for style in styles:
        card = v24_payoff.build(style)
        worst = (99.0, 99.0)
        for number, tag in PROOF_FRAMES:
            base = Image.open(os.path.join(directory, f"f{number:04d}.png"))
            full = v24_payoff.over(base, card.image)
            # Full size is kept in the branch only for the recommended style;
            # the others are reviewed at phone size, which is where the choice
            # between them is actually made, and rebuilt here on demand.
            keep = DOCS_DIR if style == v24_payoff.RECOMMENDED else WORK_DIR
            os.makedirs(keep, exist_ok=True)
            full.save(os.path.join(keep, f"proof_{style}_{tag}.png"))
            v24_payoff.phone(full).save(
                os.path.join(DOCS_DIR, f"phone_{style}_{tag}.png")
            )
            low, median = v24_payoff.measured_contrast(base, card.image)
            worst = (min(worst[0], low), min(worst[1], median))
            print(
                f"{style:<6} {tag}  measured contrast "
                f"worst {low:.2f}:1  median {median:.2f}:1"
            )
        report[style] = {
            "worst_glyph_contrast": round(worst[0], 2),
            "median_glyph_contrast": round(worst[1], 2),
        }

    row = Image.new("RGB", (3 * 270 + 2 * 20, 480), (18, 18, 18))
    for index, style in enumerate(v24_payoff.STYLES):
        row.paste(
            Image.open(os.path.join(DOCS_DIR, f"phone_{style}_23900.png")),
            (index * 290, 0),
        )
    row.save(os.path.join(DOCS_DIR, "phone_row.png"))
    print(f"wrote {os.path.join(DOCS_DIR, 'phone_row.png')}")
    return report


def stage_ring(film: str) -> dict[str, Any]:
    """The winner mark, moved onto the 0.217 s where the winner is on screen."""
    directory = ensure_frames(film)
    replay, track, clock = load_clock()
    plan = v24_payoff.schedule()
    ring_from, ring_to = plan["ring"]
    where = {
        round(row[0], 6): row[1:]
        for row in presentation.screen_track(
            replay, track, clock, WINNER_INDEX, (ring_from - 0.05, ring_to + 0.05)
        )
    }
    times = sorted(where)
    os.makedirs(DOCS_DIR, exist_ok=True)
    os.makedirs(WORK_DIR, exist_ok=True)
    count = int(round(v24_payoff.RING_SECONDS * FPS))
    shots = []
    # The three frames go into the ignored work dir and only the contact row is
    # kept in the branch: three 1 MB stills that a 568 KB row already shows is
    # the kind of thing that makes a validation folder twice the size of every
    # other one in the repository.
    crop = (260, 780, 980, 2060)
    tiles = []
    for index in (0, count // 3, 2 * count // 3):
        when = ring_from + index / FPS
        nearest = min(times, key=lambda value: abs(value - when))
        x, y, radius = where[nearest]
        number = int(round(when * FPS))
        base = Image.open(os.path.join(directory, f"f{number:04d}.png"))
        mark = overlays.winner_ring(x, y, radius, index / max(1, count - 1))
        shot = v24_payoff.over(base, mark)
        shot.save(os.path.join(WORK_DIR, f"ring_{index:02d}.png"))
        tiles.append(shot.crop(crop).resize((360, 640), Image.LANCZOS))
        frame = np.asarray(base.convert("RGB")).astype(np.float32) / 255.0
        seen = visible_fraction(frame, WINNER_INDEX, x, y, radius)
        shots.append({"frame": number, "t": when, "visible": round(seen, 3)})
        print(f"ring frame {number} (t {when:.3f})  winner visible {seen:.2f}")

    row = Image.new("RGB", (len(tiles) * 380 - 20, 640), (16, 16, 16))
    for index, tile in enumerate(tiles):
        row.paste(tile, (index * 380, 0))
    row.save(os.path.join(DOCS_DIR, "ring_row.png"))
    print(f"wrote {os.path.join(DOCS_DIR, 'ring_row.png')}")
    return {"ring": [ring_from, ring_to], "shots": shots}


def stage_compare(film: str) -> None:
    """The shipped end card and the recommended one, on one sheet."""
    directory = ensure_frames(film)
    os.makedirs(DOCS_DIR, exist_ok=True)
    shipped_frame = 1572
    base_old = Image.open(os.path.join(directory, f"f{shipped_frame:04d}.png"))
    old = v24_payoff.over(
        base_old, overlays.end_fact(accent=overlays.MARBLE_HUES[WINNER_INDEX])
    )
    base_new = Image.open(os.path.join(directory, "f1494.png"))
    new = v24_payoff.over(base_new, v24_payoff.build("plate").image)

    pad = 24
    sheet = Image.new("RGB", (2 * 540 + 3 * pad, 960 + 2 * pad + 46), (16, 16, 16))
    sheet.paste(old.resize((540, 960), Image.LANCZOS), (pad, pad + 46))
    sheet.paste(new.resize((540, 960), Image.LANCZOS), (2 * pad + 540, pad + 46))
    pen = ImageDraw.Draw(sheet)
    font = overlays.load_font(26)
    pen.text((pad, pad + 6), "V22.1  end fact, 25.883-26.533", font=font,
             fill=(235, 230, 220))
    pen.text((2 * pad + 540, pad + 6), "V24  plate, 23.900-25.700", font=font,
             fill=(235, 230, 220))
    sheet.save(os.path.join(DOCS_DIR, "compare.png"))
    print(f"wrote {os.path.join(DOCS_DIR, 'compare.png')}")
    _ring_compare(directory)


def _ring_compare(directory: str) -> None:
    """The shipped ring and the moved one, on the frames they each run on.

    The "before" is taken from the **delivered** film rather than rebuilt,
    because the claim being made is about what shipped: at 23.400 the gold
    ring and the word WINNER are on the gantry rail with nothing inside them,
    and the nearest racer is the emerald that came second.
    """
    if not os.path.isfile(DELIVERED):
        print(f"  (skipping ring_compare: {DELIVERED} not found)")
        return
    before = os.path.join(WORK_DIR, "delivered_1404.png")
    if not os.path.isfile(before):
        subprocess.run(
            [
                _ffmpeg(), "-v", "error", "-y", "-i", DELIVERED,
                "-vf", "select='eq(n\\,1404)'", "-vsync", "0", "-frames:v", "1",
                before,
            ],
            check=True,
        )

    replay, track, clock = load_clock()
    rows = presentation.screen_track(
        replay, track, clock, WINNER_INDEX, (22.88, 22.93)
    )
    _, x, y, radius = rows[0]
    after = v24_payoff.over(
        Image.open(os.path.join(directory, "f1374.png")),
        overlays.winner_ring(x, y, radius, 0.18),
    )

    crop = (250, 760, 1010, 1520)
    pad = 24
    sheet = Image.new("RGB", (2 * 380 + 3 * pad, 380 + 2 * pad + 46), (16, 16, 16))
    sheet.paste(Image.open(before).crop(crop).resize((380, 380), Image.LANCZOS),
                (pad, pad + 46))
    sheet.paste(after.crop(crop).resize((380, 380), Image.LANCZOS),
                (2 * pad + 380, pad + 46))
    pen = ImageDraw.Draw(sheet)
    font = overlays.load_font(22)
    pen.text((pad, pad + 8), "V22.1  ring at 23.400: winner hidden",
             font=font, fill=(235, 230, 220))
    pen.text((2 * pad + 380, pad + 8), "V24  ring at 22.900: winner inside it",
             font=font, fill=(235, 230, 220))
    sheet.save(os.path.join(DOCS_DIR, "ring_compare.png"))
    print(f"wrote {os.path.join(DOCS_DIR, 'ring_compare.png')}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        default="all",
        choices=("all", "winner", "visibility", "band", "cards", "proof", "ring",
                 "compare"),
    )
    parser.add_argument("--film", default=DEFAULT_FILM,
                        help="the delivered V22.1 silent master")
    parser.add_argument("--style", default=None, choices=tuple(v24_payoff.STYLES))
    args = parser.parse_args(argv)

    styles = (args.style,) if args.style else tuple(v24_payoff.STYLES)
    stage = args.stage
    summary: dict[str, Any] = {}

    if stage in ("all", "winner"):
        print("=== winner ===")
        summary["winner"] = stage_winner()
    if stage in ("all", "visibility"):
        print("\n=== visibility ===")
        summary["visibility"] = stage_visibility(args.film)
    if stage in ("all", "band"):
        print("\n=== band ===")
        summary["band"] = stage_band(args.film)
    if stage in ("all", "cards"):
        print("\n=== cards ===")
        summary["cards"] = stage_cards()
    if stage in ("all", "proof"):
        print("\n=== proof ===")
        summary["proof"] = stage_proof(args.film, styles)
    if stage in ("all", "ring"):
        print("\n=== ring ===")
        summary["ring"] = stage_ring(args.film)
    if stage in ("all", "compare"):
        print("\n=== compare ===")
        stage_compare(args.film)

    if stage == "all":
        os.makedirs(DOCS_DIR, exist_ok=True)
        summary["schedule"] = v24_payoff.schedule()
        summary["describe"] = v24_payoff.describe()
        path = os.path.join(DOCS_DIR, "payoff.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(summary, handle, indent=1, default=str)
        print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
