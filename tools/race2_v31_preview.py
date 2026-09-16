"""The production preview: the winning camera with the viewer-facing marks on.

Usage:

    python tools/race2_v31_review.py preview            # RB, composited
    python tools/race2_v31_preview.py --camera=RB       # the same, directly
    python tools/race2_v31_preview.py --place-only      # just the arithmetic

Three marks and nothing else, all of them `sloped.overlays`' - the established
presentation language, imported rather than restated:

    PICK A COLOR   over the opening, gone before the first cut
    a ring on the winner, from just after it crosses
    FROM 6TH -> 1ST, at the very end

**Every placement here is measured, not chosen.** `sloped.overlays` places its
marks against screen positions taken from the delivered frames, and this does
the same thing with this branch's own projector: where the eight racers are in
the opening decides where the title's baseline goes, and where the winner is
after it crosses decides where the ring goes. Two things this makes checkable
rather than hopeful:

- **The title never covers a racer.** The baseline is pushed to whichever band
  of the frame the opening's eight marbles are not in, and the chosen band is
  reported.
- **The ring is on a marble the viewer can see.** V24's payoff lab found both
  shipped winner marks pointing at a marble hidden behind the finish gantry.
  The same occlusion test `race2.readability` uses runs over the ring's whole
  life here, and the tool refuses to composite if the winner is hidden for any
  of it.

The film underneath is the delivered clip, frame for frame. Nothing is
re-rendered and no camera, geometry, replay or environment is touched.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2.flow import DELIVERY, MARBLE_RADIUS, _basis, _project  # noqa: E402

TRACKS = "output/race2/v31_readability"
FRAMES = "output/race2/v31_readability/frames"
DOCS = "docs/validation/race2/v31_readability"
EXPORT = "exports/race2_v31_readability"

# The title's life, in seconds of film. V24's timing, kept: up on frame zero
# over live footage - there is no held frame to fade it in over - and away
# before the lens finishes its opening move, so the first cut lands clean.
TITLE_IN = 0.0
TITLE_OUT_FROM = 1.05
TITLE_OUT_TO = 1.30
# The two baselines the title may take, and the margin it must clear the
# racers by. Both are `sloped.overlays`' own geometry: the mark is about 150 px
# tall and sits on its baseline.
TITLE_HIGH = 395
TITLE_LOW = 1430
TITLE_HEIGHT = 190
TITLE_MARGIN = 60

# The winner's mark: when it opens after the crossing, and how long it lives.
RING_AFTER = 0.18
RING_FOR = 0.70
# And the closing fact, which holds to the last frame.
FACT_FROM = 18.20
FACT_FADE = 0.35


def load_track(camera: str, course: str, seed: int) -> list:
    with open(os.path.join(TRACKS, camera, f"race2_{course}_{seed}.cameras.json"),
              encoding="utf-8") as handle:
        track = json.load(handle)
    return [row for cut in track["cuts"] for row in cut["frames"]]


def screen_of(row, point) -> tuple[float, float, float] | None:
    """A world point as `(x, y, radius)` in delivered 1080x1920 pixels."""
    position = (row[1], row[2], row[3])
    aim = (row[4], row[5], row[6])
    fov = row[7]
    forward, right, up = _basis(position, aim)
    projected, depth = _project(point, position, forward, right, up, fov, DELIVERY)
    if projected is None:
        return None
    half_up = math.tan(math.radians(fov) * 0.5)
    return (
        (projected[0] + 1.0) * 0.5 * DELIVERY[0],
        (1.0 - projected[1]) * 0.5 * DELIVERY[1],
        MARBLE_RADIUS / max(depth * half_up, 1e-6) * 0.5 * DELIVERY[1],
    )


def _context(args):
    from race2 import courses
    from race2.race import run_race
    from race2.rig import PackTrack
    from race2.spine import Spine

    course = courses.build(args.course)
    spine = Spine(course)
    outcome, _replay = run_race(course, seed=args.seed, duration=40.0,
                                marble_count=8, with_replay=False)
    with open(os.path.join("output/race2",
                           f"race2_{args.course}_{args.seed}.replay.json"),
              encoding="utf-8") as handle:
        raw = json.load(handle)
    pack = PackTrack(raw, spine, outcome, group="interest")
    return spine, outcome, pack


def placement(args) -> dict:
    """The arithmetic behind all three marks."""
    spine, outcome, pack = _context(args)
    rows = load_track(args.camera, args.course, args.seed)

    def row_at(when: float):
        return min(rows, key=lambda r: abs(r[0] - when))

    # --- the title: which band of the opening is empty of racers -------------
    lowest, highest = DELIVERY[1], 0.0
    for step in range(0, int(TITLE_OUT_TO * 60) + 1):
        when = step / 60.0
        row = row_at(when)
        for point in pack.places[pack.frame_at(when)].values():
            at = screen_of(row, point)
            if at is None:
                continue
            if -200 < at[0] < DELIVERY[0] + 200:
                lowest = min(lowest, at[1] - at[2])
                highest = max(highest, at[1] + at[2])
    high_clear = lowest - (TITLE_HIGH + TITLE_MARGIN)
    low_clear = (TITLE_LOW - TITLE_HEIGHT - TITLE_MARGIN) - highest
    baseline = TITLE_HIGH if high_clear >= low_clear else TITLE_LOW

    # --- the winner's ring ---------------------------------------------------
    finishes = sorted((r.finish_time, r.marble_id) for r in outcome.racers
                      if r.finish_time is not None)
    winner = finishes[0][1]
    crossing = finishes[0][0]
    ring: list[dict] = []
    hidden = 0
    for step in range(int(RING_FOR * 60) + 1):
        when = crossing + RING_AFTER + step / 60.0
        row = row_at(when)
        point = pack.places[pack.frame_at(when)].get(winner)
        if point is None:
            continue
        at = screen_of(row, point)
        if at is None:
            hidden += 1
            continue
        blocked = spine.blocked((row[1], row[2], row[3]), point)
        inside = (at[2] < at[0] < DELIVERY[0] - at[2]
                  and at[2] < at[1] < DELIVERY[1] - at[2])
        if blocked or not inside:
            hidden += 1
        ring.append({"t": round(when, 4), "x": round(at[0], 1),
                     "y": round(at[1], 1), "r": round(at[2], 1),
                     "blocked": bool(blocked), "inside": bool(inside)})

    # --- the closing fact ----------------------------------------------------
    worst = 1
    for _when, order in outcome.rank_series:
        if winner in order:
            worst = max(worst, list(order).index(winner) + 1)

    return {
        "camera": args.camera,
        "title": {
            "text": args.title,
            "baseline": baseline,
            "band": "high" if baseline == TITLE_HIGH else "low",
            "racers_top": round(lowest, 1),
            "racers_bottom": round(highest, 1),
            "clearance_high": round(high_clear, 1),
            "clearance_low": round(low_clear, 1),
            "in": TITLE_IN, "out_from": TITLE_OUT_FROM, "out_to": TITLE_OUT_TO,
        },
        "winner": {
            "marble": winner,
            "crossing": round(crossing, 4),
            "from": round(crossing + RING_AFTER, 4),
            "to": round(crossing + RING_AFTER + RING_FOR, 4),
            "frames": len(ring),
            "frames_hidden": hidden,
            "radius_px": [round(min(r["r"] for r in ring), 1),
                          round(max(r["r"] for r in ring), 1)],
            "track": ring,
        },
        # The card carries the winning marble's own hue, which is the only
        # thing tying a line of text at the bottom of the frame to a ball that
        # crossed two seconds earlier. `overlays.WINNER_HUE` defaults to the
        # *sloped* race's seed-5432 winner - purple - and this race's winner is
        # m7, which is pink, so the default would point at the wrong colour in
        # a format whose whole premise is that the viewer picked one.
        "fact": {"before": f"FROM {_ordinal(worst)}", "after": "1ST",
                 "from": FACT_FROM, "accent": list(_hue(winner))},
    }


def _hue(marble: int):
    """The delivered body colour of one racer, from the renderer's own palette."""
    from sloped.overlays import MARBLE_HUES

    return MARBLE_HUES[marble % len(MARBLE_HUES)]


def _ordinal(value: int) -> str:
    return f"{value}{'TH' if 11 <= value % 100 <= 13 else {1: 'ST', 2: 'ND', 3: 'RD'}.get(value % 10, 'TH')}"


def build_preview(args) -> None:
    """Composite the three marks over the winner's delivered frames.

    **Five optional fields, all defaulting to V31's own paths.** V31.1 changes
    the channel's material and nothing about these marks, so it reuses this
    function rather than restating the measured title placement and the
    occlusion refusal. Given none of them this behaves exactly as it did, and
    `tests/test_race2_v311_track.py::test_preview_defaults_are_v31` holds that.
    """
    from PIL import Image
    from sloped import overlays

    frames_root = str(getattr(args, "frames_root", "") or FRAMES)
    clip_tag = str(getattr(args, "clip_tag", "") or f"clip_{args.camera}")
    export = str(getattr(args, "export", "") or EXPORT)
    docs = str(getattr(args, "docs", "") or DOCS)
    name = str(getattr(args, "name", "")
               or f"race2_v31_production_preview_{args.camera}")

    marks = placement(args)
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "preview_placement.json"), "w",
              encoding="utf-8") as handle:
        json.dump(marks, handle, indent=1)
    title = marks["title"]
    print(f"  title   '{title['text']}' baseline {title['baseline']} "
          f"({title['band']} band): racers occupy y "
          f"{title['racers_top']:.0f}-{title['racers_bottom']:.0f}, "
          f"clearance high {title['clearance_high']:.0f} / "
          f"low {title['clearance_low']:.0f}")
    win = marks["winner"]
    print(f"  ring    m{win['marble']} {win['from']:.2f}-{win['to']:.2f} s, "
          f"{win['frames']} frames, {win['frames_hidden']} hidden, "
          f"radius {win['radius_px'][0]:.0f}-{win['radius_px'][1]:.0f} px")
    print(f"  fact    {marks['fact']['before']} -> {marks['fact']['after']} "
          f"from {marks['fact']['from']:.2f} s, "
          f"accent rgb{tuple(marks['fact']['accent'])} (m{win['marble']}'s own)")
    if win["frames_hidden"]:
        raise SystemExit(
            f"the winner is hidden for {win['frames_hidden']} of the ring's "
            f"{win['frames']} frames - see V24's payoff lab; the mark would "
            "point at a marble the viewer cannot see"
        )
    if args.place_only:
        return

    source = os.path.join(frames_root, clip_tag,
                          f"clip_{args.course}_{args.seed}")
    found = sorted(glob.glob(os.path.join(source, "frame_*.png")))
    if not found:
        raise SystemExit(f"no frames in {source}; run "
                         f"`python tools/race2_v31_review.py clips` first")
    out = os.path.join(frames_root, f"preview_{args.camera}")
    os.makedirs(out, exist_ok=True)

    plate = overlays.pick_one(title["text"], size=args.title_size)
    if title["baseline"] != overlays.PICK_ONE_BASELINE:
        plate = plate.transform(
            plate.size, Image.AFFINE,
            (1, 0, 0, 0, 1, overlays.PICK_ONE_BASELINE - title["baseline"]),
            resample=Image.BILINEAR)
    fact = overlays.end_fact(marks["fact"]["before"], marks["fact"]["after"],
                             accent=tuple(marks["fact"]["accent"]))
    ring_rows = {round(r["t"] * 60): r for r in win["track"]}
    first_ring = min(ring_rows)

    written = 0
    for index, path in enumerate(found):
        when = index / 60.0
        frame = Image.open(path).convert("RGBA")
        touched = False

        if when <= TITLE_OUT_TO:
            alpha = 1.0
            if when > TITLE_OUT_FROM:
                alpha = 1.0 - (when - TITLE_OUT_FROM) / (TITLE_OUT_TO - TITLE_OUT_FROM)
            frame.alpha_composite(_faded(plate, alpha))
            touched = True

        row = ring_rows.get(index)
        if row is not None:
            phase = (index - first_ring) / max(len(ring_rows) - 1, 1)
            frame.alpha_composite(
                overlays.winner_ring(row["x"], row["y"], row["r"], phase))
            touched = True

        if when >= marks["fact"]["from"]:
            alpha = min(1.0, (when - marks["fact"]["from"]) / FACT_FADE)
            frame.alpha_composite(_faded(fact, alpha))
            touched = True

        frame.convert("RGB").save(
            os.path.join(out, os.path.basename(path)))
        written += 1 if touched else 0

    from tools.race2_v30_review import encode

    target = os.path.join(export, f"{name}.mp4")
    encode(out, target)
    print(f"  {len(found)} frames, {written} carrying a mark")
    print(f"  wrote {target}")


def _faded(plate, alpha: float):
    from PIL import Image

    if alpha >= 0.999:
        return plate
    if alpha <= 0.001:
        return Image.new("RGBA", plate.size, (0, 0, 0, 0))
    faded = plate.copy()
    faded.putalpha(plate.getchannel("A").point(
        lambda value: int(round(value * alpha))))
    return faded


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--camera", default="RB")
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--title", default="PICK A COLOR")
    parser.add_argument("--title-size", type=int, default=104)
    parser.add_argument("--place-only", action="store_true")
    build_preview(parser.parse_args())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
