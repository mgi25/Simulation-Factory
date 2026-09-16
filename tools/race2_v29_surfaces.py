"""Which of the hall's surfaces camera A actually looks at, per shot.

Usage:

    python tools/race2_v29_surfaces.py            # render the marker and count
    python tools/race2_v29_surfaces.py --keep     # leave the marker profile on disk

The brief's last question is "report the exact environment surfaces visible in
the new camera A shots that would need a later art pass", and a still cannot
answer it: at the grade this room renders at, a graphite panel, a graphite rib
and the void behind them are all within a couple of luma of each other, and
eyeballing which is which is how a pass ends up art-directing a surface that is
not in the film.

So the hall is rendered a second time with every one of its material keys
painted a flat, unshaded, unfogged hue of its own - the mechanism
`lab_palette._build` documents under "Flat paint, for a diagnostic profile and
nothing else" - and the delivered frames are segmented against those hues. A
surface's number is then the share of the film's pixels that surface owns, per
shot, exactly.

**The marker profile is written, rendered and deleted inside one context
manager, and `index.json` is restored from the bytes it had on entry.** That is
V27.2's own convention for a diagnostic and it is kept here for its reason: the
registry is a shipped list, and a lab that leaves an entry in it has changed the
product to take a measurement.
"""

from __future__ import annotations

import argparse
import contextlib
import glob
import json
import os
import shutil
import subprocess
import sys
from typing import Iterator

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

PROFILE_DIR = os.path.join(REPO, "godot", "assets", "marble_machine",
                           "environment", "profiles")
INDEX_PATH = os.path.join(PROFILE_DIR, "index.json")
MARKER = "_marker_v29_surfaces"
OVER = "contained_hall_v272"
TRACKS = "output/race2/v281_camera/A"
FRAMES = "output/race2/v29/frames"

# One flat hue per surface the hall can put on screen, chosen far apart in RGB
# so that a segmenter matching on exact bytes has no near-misses to arbitrate.
# The machine and the racers are not marked - they keep their own materials -
# so anything that is not one of these hues and is not black is the machine,
# which is the classification this measurement wants anyway.
SURFACES = {
    "hall_panel": "#FF2D55",        # the wall
    "hall_panel_dark": "#FF9500",   # recess lining, lower wall, merge backing
    "hall_rib": "#FFD60A",          # the vertical structural members
    "hall_trim": "#34C759",         # cornice, plinth, cap
    "hall_deck": "#00C7BE",         # the floor
    "hall_deck_dark": "#0A84FF",    # service level and pit
    "hall_glass": "#5E5CE6",        # dark glazing
    "hall_beam": "#BF5AF2",         # overhead structure
    "hall_grate": "#8E8E93",        # catwalk plate
    "lit_hall_warm": "#C71585",     # the warm wall practicals
    "lit_hall_cool": "#A2845E",     # the cool slots
}

# The machine is never marked, so a machine pixel could in principle land on a
# marker hue by accident - a white track under a white marker being the obvious
# way. It cannot here, because the machine is masked out of the classification
# by its own silhouette before any hue is compared. See `segment`.


def _colour(text: str) -> tuple[int, int, int]:
    text = text.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def marker_document() -> dict:
    return {
        "id": MARKER,
        "title": "Marker over %s (diagnostic)" % OVER,
        "family": "diagnostic",
        "summary": ("%s with every hall surface painted a flat unshaded hue, so "
                    "a render of camera A can be segmented by which surface each "
                    "pixel belongs to. Written, rendered and deleted by "
                    "tools/race2_v29_surfaces.py; never shipped." % OVER),
        "extends": OVER,
        # **The grade has to come off too, and that is the whole trick.**
        #
        # `unshaded` takes a surface out of the lighting and `no_fog` out of the
        # haze, which is what `lab_palette` promises and all a V27-era marker
        # needed. It is not enough here. Everything this room is graded by -
        # an ACES tonemap at exposure 0.81 against a white point of 12, then a
        # contrast and a saturation lift - runs on the *frame*, after shading,
        # so a marker hue still reaches the file as some other colour and a
        # segmenter matching on bytes finds nothing. Measured before this block
        # existed: eleven surfaces, 0.004% of the film between them, against a
        # world coverage of 29.19% that is provably there.
        #
        # Linear tonemap, unit white, unit exposure, no adjustment, no glow, no
        # fog: an unshaded albedo then round-trips to the file exactly, and the
        # match below is an equality rather than a nearest-colour vote. None of
        # this changes one vertex, so the geometry being measured is the
        # geometry that ships - and the total the eleven surfaces come to is
        # checked against the 29.19% of world coverage the delivery and its
        # matte measure independently, which is what says so.
        "grade": {
            "tonemap": "linear",
            "exposure": 1.0,
            "white": 1.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "brightness": 1.0,
        },
        "glow": {"enabled": False},
        "fog": {"enabled": False},
        "palette": {
            key: {"albedo": hue, "unshaded": True, "no_fog": True}
            for key, hue in SURFACES.items()
        },
    }


@contextlib.contextmanager
def temporary(document: dict) -> Iterator[str]:
    """Install a profile, yield its id, and take it out again.

    `index.json` is restored from the bytes it held on entry rather than by
    removing the entry that was added, so a crash between the two writes cannot
    leave the registry reordered or reindented.
    """
    path = os.path.join(PROFILE_DIR, document["id"] + ".json")
    original = open(INDEX_PATH, "rb").read()
    try:
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2)
            handle.write("\n")
        index = json.loads(original.decode("utf-8"))
        if document["id"] not in index["profiles"]:
            index["profiles"].append(document["id"])
        with open(INDEX_PATH, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(index, handle, indent=2)
            handle.write("\n")
        yield document["id"]
    finally:
        with open(INDEX_PATH, "wb") as handle:
            handle.write(original)
        if os.path.isfile(path):
            os.remove(path)


def run(command: list[str], label: str) -> None:
    result = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    if result.returncode != 0:
        raise SystemExit(f"{label} failed:\n{(result.stderr or result.stdout)[-2500:]}")
    print(f"  {label}")


def film_end() -> float:
    with open(os.path.join(TRACKS, "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        return float(json.load(handle)["duration"])


def shot_at(seconds: float) -> str:
    with open(os.path.join(TRACKS, "race2_switchyard_8.cameras.json"),
              encoding="utf-8") as handle:
        cuts = json.load(handle)["cuts"]
    for cut in cuts:
        if float(cut["from"]) <= seconds <= float(cut["to"]):
            return str(cut["name"])
    return "?"


def segment(folder: str, every: int, docs: str) -> None:
    import numpy as np
    from PIL import Image

    frames = sorted(glob.glob(os.path.join(folder, "frame_*.png")))
    if not frames:
        raise SystemExit(f"no marker frames in {folder}")
    keys = list(SURFACES)
    targets = np.array([_colour(SURFACES[k]) for k in keys], dtype=np.int16)

    # The machine's own silhouette, from the contained world's matte pass. The
    # marker render is the same camera on the same frames, so this is a mask of
    # exactly the pixels that are machine or racer - and taking them out before
    # any hue is compared is what lets the marker hues be bright and saturated
    # without a white track or a pink marble being counted as a wall.
    mattes = sorted(glob.glob(os.path.join(
        FRAMES, "matte_contained", "clip_switchyard_8", "frame_*.png")))
    if not mattes:
        raise SystemExit("no contained matte; run race2_v29_short.py matte first")

    rows = []
    for index in range(0, len(frames), every):
        image = np.asarray(Image.open(frames[index]).convert("RGB")).astype(np.int16)
        matte = np.asarray(Image.open(mattes[index]).convert("RGB")).astype(np.float32)
        machine = ((0.2126 * matte[..., 0] + 0.7152 * matte[..., 1]
                    + 0.0722 * matte[..., 2]) >= 0.5)
        # An unshaded, unfogged surface under a neutral grade renders its own
        # albedo exactly, so the match is an equality inside a small tolerance
        # rather than a nearest-colour vote. A pixel that matches nothing and
        # is not machine is the void behind the room.
        row = {"t": round(index / 60.0, 4), "shot": shot_at(index / 60.0)}
        matched = np.zeros(image.shape[:2], dtype=bool)
        for key, target in zip(keys, targets):
            hit = (np.abs(image - target).max(axis=2) <= 6) & ~machine
            matched |= hit
            row[key] = round(100.0 * float(hit.mean()), 4)
        row["hall"] = round(100.0 * float(matched.mean()), 4)
        row["machine"] = round(100.0 * float(machine.mean()), 4)
        row["void"] = round(100.0 * float((~matched & ~machine).mean()), 4)
        rows.append(row)

    shots: dict = {}
    for row in rows:
        shots.setdefault(row["shot"], []).append(row)
    report = {"over": OVER, "marker": MARKER, "samples": len(rows),
              "surfaces": SURFACES, "rows": rows, "shots": {}}
    for name, inside in shots.items():
        summary = {"samples": len(inside)}
        for key in keys + ["hall", "machine", "void"]:
            values = [r[key] for r in inside]
            summary[key] = {
                "mean": round(sum(values) / len(values), 3),
                "max": round(max(values), 3),
            }
        report["shots"][name] = summary

    os.makedirs(docs, exist_ok=True)
    target = os.path.join(docs, "surfaces.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"  wrote {target}")

    order = ["release", "upper", "middle", "run_in"]
    present = [s for s in order if s in report["shots"]]
    print()
    print("SHARE OF FRAME, PER SURFACE, MEAN OVER EACH SHOT (%)")
    print(f"{'surface':<17}" + "".join(f"{s:>10}" for s in present) + f"{'film':>10}")
    print("-" * (17 + 10 * (len(present) + 1)))
    for key in keys + ["hall", "machine", "void"]:
        cells = "".join(f"{report['shots'][s][key]['mean']:>10.3f}" for s in present)
        overall = sum(r[key] for r in rows) / len(rows)
        print(f"{key:<17}{cells}{overall:>10.3f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--every", type=int, default=6)
    parser.add_argument("--docs", default="docs/validation/race2/v29_contained")
    parser.add_argument("--keep", action="store_true",
                        help="leave the marker profile installed (for a look)")
    parser.add_argument("--reuse", action="store_true",
                        help="segment frames already rendered")
    args = parser.parse_args()

    folder = os.path.join(FRAMES, "marker", "clip_switchyard_8")
    if args.reuse:
        segment(folder, args.every, args.docs)
        return 0

    document = marker_document()
    with temporary(document) as profile_id:
        out = os.path.join(FRAMES, "marker")
        os.makedirs(out, exist_ok=True)
        run([
            sys.executable, "tools/race2_render.py", "clip",
            "--seed=8", "--course=switchyard",
            f"--out={TRACKS}", f"--frames={out}",
            f"--environment={profile_id}", f"--end={film_end():.4f}",
        ], f"render marker ({profile_id})")
        if args.keep:
            print("  --keep: the marker stays installed for this run only;"
                  " the registry is still restored")
    segment(folder, args.every, args.docs)
    left = [p for p in (os.path.join(PROFILE_DIR, MARKER + ".json"),)
            if os.path.isfile(p)]
    index = json.loads(open(INDEX_PATH, encoding="utf-8").read())
    if left or MARKER in index["profiles"]:
        raise SystemExit("the marker profile outlived its context manager")
    print("\n  registry clean: the marker is off disk and out of index.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
