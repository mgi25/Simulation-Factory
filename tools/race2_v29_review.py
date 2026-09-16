"""The review questions that a coverage number does not answer.

Usage:

    python tools/race2_v29_review.py            # all six measures
    python tools/race2_v29_review.py --only=fit,bands

Reads only frames that `tools/race2_v29_short.py` and
`tools/race2_v29_surfaces.py` have already rendered; it simulates nothing,
renders nothing and changes nothing.

    fit        how the room and the lens fit, from geometry alone
    bands      where in the frame the blackness is, by vertical third
    card       what a PICK A COLOR plate would sit on, in each world
    racers     whether the racers stay readable, shot by shot
    parallax   whether the environment moves enough to read as depth
    occlusion  how much of the machine the environment covers
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

FRAMES = "output/race2/v29/frames"
TRACK = "output/race2/v281_camera/A/race2_switchyard_8.cameras.json"
WORLDS = ("outdoor", "contained")

# V24 put PICK A COLOR on a baseline of 269 with 71 px of cap height and a
# 798 px measure centred in 1080 - `docs/sloped_race_v24.md` section 3.1 - and
# it is up from output 0.000 to 1.05. Race #2 has no overlay system, so this is
# not a measurement of a card in this film. It is a measurement of the picture
# a card would have to be legible over, taken in the band that card occupies.
CARD_BOX = (141, 198, 939, 269)   # x0, y0, x1, y1
CARD_UNTIL = 1.05

SURFACES = {
    "hall_panel": "#FF2D55", "hall_panel_dark": "#FF9500",
    "hall_rib": "#FFD60A", "hall_trim": "#34C759",
    "hall_deck": "#00C7BE", "hall_deck_dark": "#0A84FF",
    "hall_glass": "#5E5CE6", "hall_beam": "#BF5AF2",
    "hall_grate": "#8E8E93", "lit_hall_warm": "#C71585",
    "lit_hall_cool": "#A2845E",
}


def _rgb(text: str):
    text = text.lstrip("#")
    return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))


def frames_of(folder: str):
    return sorted(glob.glob(os.path.join(folder, "frame_*.png")))


def clip(world: str) -> str:
    return os.path.join(FRAMES, f"delivery_{world}", "clip_switchyard_8")


def matte(world: str) -> str:
    return os.path.join(FRAMES, f"matte_{world}", "clip_switchyard_8")


def shots():
    with open(TRACK, encoding="utf-8") as handle:
        return json.load(handle)["cuts"]


def shot_at(seconds: float) -> str:
    for cut in shots():
        if float(cut["from"]) <= seconds <= float(cut["to"]):
            return str(cut["name"])
    return "?"


def card(report: dict) -> None:
    """What a title plate would have under it, in the band V24 used."""
    import numpy as np
    from PIL import Image

    x0, y0, x1, y1 = CARD_BOX
    out = {}
    for world in WORLDS:
        files = frames_of(clip(world))
        rows = []
        for index in range(0, int(CARD_UNTIL * 60) + 1, 3):
            if index >= len(files):
                break
            image = np.asarray(Image.open(files[index]).convert("RGB")).astype(np.float32)
            band = image[y0:y1, x0:x1]
            luma = 0.2126 * band[..., 0] + 0.7152 * band[..., 1] + 0.0722 * band[..., 2]
            rows.append({
                "t": round(index / 60.0, 3),
                "mean": round(float(luma.mean()), 2),
                "sd": round(float(luma.std()), 2),
                "p95": round(float(np.percentile(luma, 95)), 2),
                # White type at 96 pt needs the plate under it to stay well
                # below it. The share over 128 is the share that would fight.
                "over_128": round(100.0 * float((luma >= 128).mean()), 3),
            })
        out[world] = {
            "box": CARD_BOX, "until": CARD_UNTIL, "samples": len(rows),
            "mean": round(sum(r["mean"] for r in rows) / len(rows), 2),
            "sd": round(sum(r["sd"] for r in rows) / len(rows), 2),
            "worst_sd": round(max(r["sd"] for r in rows), 2),
            "over_128": round(sum(r["over_128"] for r in rows) / len(rows), 3),
            "rows": rows,
        }
    report["card"] = out
    print("\nWHAT A TITLE PLATE WOULD SIT ON  (V24's band, first 1.05 s)")
    print(f"{'world':<11}{'luma':>8}{'sd':>8}{'worst sd':>10}{'>128 %':>9}")
    for world, data in out.items():
        print(f"{world:<11}{data['mean']:>8.2f}{data['sd']:>8.2f}"
              f"{data['worst_sd']:>10.2f}{data['over_128']:>9.3f}")


def racers(report: dict) -> None:
    """Are the racers still readable, and are they still their own colour?

    The racers are picked out of each world's matte by saturation: the machine
    is graphite and white and the racers are the only saturated thing in the
    silhouette. Then the same pixels are read out of the *delivery*, so the
    number is the racers as the finished film shows them.
    """
    import numpy as np
    from PIL import Image

    out = {}
    for world in WORLDS:
        files = frames_of(clip(world))
        mattes = frames_of(matte(world))
        rows = []
        for index in range(0, min(len(files), len(mattes)), 6):
            seconds = index / 60.0
            silhouette = np.asarray(
                Image.open(mattes[index]).convert("RGB")).astype(np.float32)
            top = silhouette.max(axis=2)
            low = silhouette.min(axis=2)
            saturation = np.where(top > 0, (top - low) / np.maximum(top, 1.0), 0.0)
            mask = (saturation >= 0.35) & (top >= 8.0)
            if mask.sum() < 50:
                continue
            frame = np.asarray(Image.open(files[index]).convert("RGB")).astype(np.float32)
            picked = frame[mask]
            luma = (0.2126 * picked[..., 0] + 0.7152 * picked[..., 1]
                    + 0.0722 * picked[..., 2])
            ptop = picked.max(axis=1)
            plow = picked.min(axis=1)
            chroma = np.where(ptop > 0, (ptop - plow) / np.maximum(ptop, 1.0), 0.0)
            rows.append({
                "t": round(seconds, 3),
                "shot": shot_at(seconds),
                "px": int(mask.sum()),
                "luma": round(float(luma.mean()), 2),
                "sat": round(float(chroma.mean()), 4),
            })
        by_shot: dict = {}
        for row in rows:
            by_shot.setdefault(row["shot"], []).append(row)
        out[world] = {
            "shots": {
                name: {
                    "samples": len(items),
                    "luma": round(sum(r["luma"] for r in items) / len(items), 2),
                    "sat": round(sum(r["sat"] for r in items) / len(items), 4),
                    "px": int(sum(r["px"] for r in items) / len(items)),
                }
                for name, items in by_shot.items()
            },
            "rows": rows,
        }
    report["racers"] = out
    order = [str(c["name"]) for c in shots()]
    print("\nTHE RACERS, AS THE DELIVERED FILM SHOWS THEM")
    print(f"{'shot':<10}" + "".join(f"{w + ' luma':>15}" for w in WORLDS)
          + "".join(f"{w + ' sat':>14}" for w in WORLDS))
    for name in order:
        cells = ""
        for world in WORLDS:
            data = out[world]["shots"].get(name)
            cells += f"{data['luma']:>15.2f}" if data else f"{'-':>15}"
        for world in WORLDS:
            data = out[world]["shots"].get(name)
            cells += f"{data['sat']:>14.4f}" if data else f"{'-':>14}"
        print(f"{name:<10}{cells}")


def parallax(report: dict) -> None:
    """Does the environment move enough, frame to frame, to read as depth?

    Motion energy over the environment's own pixels: the mean absolute change
    between consecutive frames, counted only where that world drew something
    that is not the machine. A backdrop pinned at infinity contributes almost
    nothing here however detailed it is; a wall going past the lens contributes
    a lot. Reported per shot, and against the other world.
    """
    import numpy as np
    from PIL import Image

    out = {}
    for world in WORLDS:
        files = frames_of(clip(world))
        mattes = frames_of(matte(world))
        rows = []
        previous = None
        for index in range(0, min(len(files), len(mattes)), 6):
            seconds = index / 60.0
            frame = np.asarray(Image.open(files[index]).convert("RGB")).astype(np.float32)
            silhouette = np.asarray(
                Image.open(mattes[index]).convert("RGB")).astype(np.float32)
            machine = ((0.2126 * silhouette[..., 0] + 0.7152 * silhouette[..., 1]
                        + 0.0722 * silhouette[..., 2]) >= 0.5)
            luma = 0.2126 * frame[..., 0] + 0.7152 * frame[..., 1] + 0.0722 * frame[..., 2]
            if previous is not None:
                region = ~machine
                change = np.abs(luma - previous)[region]
                rows.append({
                    "t": round(seconds, 3),
                    "shot": shot_at(seconds),
                    "motion": round(float(change.mean()), 4),
                })
            previous = luma
        by_shot: dict = {}
        for row in rows:
            by_shot.setdefault(row["shot"], []).append(row)
        out[world] = {
            "note": "mean |luma change| per 0.1 s over non-machine pixels",
            "shots": {
                name: round(sum(r["motion"] for r in items) / len(items), 4)
                for name, items in by_shot.items()
            },
            "film": round(sum(r["motion"] for r in rows) / len(rows), 4),
            "rows": rows,
        }
    report["parallax"] = out
    order = [str(c["name"]) for c in shots()] + ["film"]
    print("\nENVIRONMENT MOTION ENERGY  (mean |dluma| per 0.1 s, background only)")
    print(f"{'shot':<10}" + "".join(f"{w:>13}" for w in WORLDS) + f"{'ratio':>9}")
    for name in order:
        cells, values = "", []
        for world in WORLDS:
            value = (out[world]["film"] if name == "film"
                     else out[world]["shots"].get(name))
            values.append(value)
            cells += f"{value:>13.4f}" if value is not None else f"{'-':>13}"
        ratio = (values[1] / values[0]) if values[0] else 0.0
        print(f"{name:<10}{cells}{ratio:>9.3f}")


def occlusion(report: dict) -> None:
    """How much of the machine's own silhouette the hall is drawn in front of."""
    import numpy as np
    from PIL import Image

    marker = frames_of(os.path.join(FRAMES, "marker", "clip_switchyard_8"))
    mattes = frames_of(matte("contained"))
    if not marker:
        print("\n  (no marker frames; run tools/race2_v29_surfaces.py)")
        return
    targets = np.array([_rgb(v) for v in SURFACES.values()], dtype=np.int16)
    rows = []
    for index in range(0, min(len(marker), len(mattes)), 6):
        seconds = index / 60.0
        image = np.asarray(Image.open(marker[index]).convert("RGB")).astype(np.int16)
        silhouette = np.asarray(
            Image.open(mattes[index]).convert("RGB")).astype(np.float32)
        machine = ((0.2126 * silhouette[..., 0] + 0.7152 * silhouette[..., 1]
                    + 0.0722 * silhouette[..., 2]) >= 0.5)
        hall = np.zeros(image.shape[:2], dtype=bool)
        for target in targets:
            hall |= (np.abs(image - target).max(axis=2) <= 6)
        covered = int((hall & machine).sum())
        total = int(machine.sum())
        rows.append({
            "t": round(seconds, 3),
            "shot": shot_at(seconds),
            "covered": round(100.0 * covered / max(1, total), 4),
        })
    by_shot: dict = {}
    for row in rows:
        by_shot.setdefault(row["shot"], []).append(row)
    report["occlusion"] = {
        "note": "share of the machine's silhouette that hall geometry covers",
        "shots": {
            name: {
                "mean": round(sum(r["covered"] for r in items) / len(items), 4),
                "max": round(max(r["covered"] for r in items), 4),
            }
            for name, items in by_shot.items()
        },
        "film_mean": round(sum(r["covered"] for r in rows) / len(rows), 4),
        "film_max": round(max(r["covered"] for r in rows), 4),
        "rows": rows,
    }
    print("\nHALL GEOMETRY IN FRONT OF THE MACHINE  (% of its silhouette)")
    print(f"{'shot':<10}{'mean':>10}{'max':>10}")
    for name, data in report["occlusion"]["shots"].items():
        print(f"{name:<10}{data['mean']:>10.4f}{data['max']:>10.4f}")
    print(f"{'film':<10}{report['occlusion']['film_mean']:>10.4f}"
          f"{report['occlusion']['film_max']:>10.4f}")


def bands(report: dict) -> None:
    """Where in the frame the blackness is, by vertical third.

    The single most diagnostic number in the pass. A room that is simply too
    dark goes black everywhere at once; this one goes black from the bottom of
    the picture upward, because the bottom of the frame is the steepest ray out
    of a downward-looking lens and so reaches the hole in the deck first. The
    shape of this table is the fingerprint of the mechanism in `fit`.
    """
    import numpy as np
    from PIL import Image

    out = {}
    for world in WORLDS:
        files = frames_of(clip(world))
        rows = []
        for index in range(0, len(files), 6):
            seconds = index / 60.0
            image = np.asarray(Image.open(files[index]).convert("RGB")).astype(np.float32)
            luma = (0.2126 * image[..., 0] + 0.7152 * image[..., 1]
                    + 0.0722 * image[..., 2])
            third = luma.shape[0] // 3
            rows.append({
                "t": round(seconds, 3),
                "shot": shot_at(seconds),
                "top": round(100.0 * float((luma[:third] < 0.5).mean()), 2),
                "middle": round(100.0 * float(
                    (luma[third:2 * third] < 0.5).mean()), 2),
                "bottom": round(100.0 * float((luma[2 * third:] < 0.5).mean()), 2),
            })
        by_shot: dict = {}
        for row in rows:
            by_shot.setdefault(row["shot"], []).append(row)
        out[world] = {
            "shots": {
                name: {
                    part: round(sum(r[part] for r in items) / len(items), 2)
                    for part in ("top", "middle", "bottom")
                }
                for name, items in by_shot.items()
            },
            "rows": rows,
        }
    report["bands"] = out
    print("\nWHERE THE BLACKNESS IS  (% of each third, mean per shot)")
    print(f"{'shot':<10}" + "".join(
        f"{w + ' ' + part:>18}" for w in WORLDS
        for part in ("top", "mid", "bot")))
    for cut in shots():
        name = str(cut["name"])
        cells = ""
        for world in WORLDS:
            data = out[world]["shots"].get(name, {})
            for part in ("top", "middle", "bottom"):
                value = data.get(part)
                cells += f"{value:>18.2f}" if value is not None else f"{'-':>18}"
        print(f"{name:<10}{cells}")


def fit(report: dict) -> None:
    """Why the frames look the way they do, from the two geometries.

    No render is read here. The camera track says where the lens is and which
    way it points; the profile says where the room's surfaces are. Between them
    they predict the coverage the other measures went and photographed, and a
    mechanism that predicts the picture is worth more to a later pass than the
    picture is.
    """
    import math

    profiles = os.path.join(REPO, "godot", "assets", "marble_machine",
                            "environment", "profiles")
    with open(os.path.join(profiles, "contained_hall.json"), encoding="utf-8") as h:
        hall = json.load(h)["world"]
    rings = hall["deck"]["rings"]
    datum = max(r["y"] + r["thickness"] * 0.5 for r in rings)
    inner = min(r["inner"] for r in rings)

    from race2 import courses
    course = courses.build("switchyard")
    reach, floor_y = 0.0, float("inf")
    for run in course.runs.values():
        for point in run.path:
            reach = max(reach, math.hypot(point[0], point[2]))
            floor_y = min(floor_y, point[1])
    lift = (floor_y - 2.0) - datum          # race2_scene.STAGE_FLOOR_CLEARANCE

    with open(TRACK, encoding="utf-8") as handle:
        cuts = json.load(handle)["cuts"]
    per_shot = {}
    tops, landings = [], []
    for cut in cuts:
        rows = []
        for stamp, ex, ey, ez, ax, ay, az, fov in cut["frames"]:
            dx, dy, dz = ax - ex, ay - ey, az - ez
            elevation = math.degrees(math.atan2(dy, math.hypot(dx, dz)))
            top = elevation + fov / 2.0
            landing = None
            if dy < 0.0:
                step = (datum + lift - ey) / dy
                landing = math.hypot(ex + step * dx, ez + step * dz)
            rows.append((ey, math.hypot(ex, ez), elevation, top, landing))
            tops.append(top)
            if landing is not None:
                landings.append(landing)
        hits = [r[4] for r in rows if r[4] is not None]
        per_shot[str(cut["name"])] = {
            "eye_y": round(sum(r[0] for r in rows) / len(rows), 2),
            "eye_radius": round(sum(r[1] for r in rows) / len(rows), 2),
            "aim_elevation": round(sum(r[2] for r in rows) / len(rows), 2),
            "frame_top": round(sum(r[3] for r in rows) / len(rows), 2),
            "floor_hit_radius": round(sum(hits) / len(hits), 2) if hits else None,
            "inside_the_hole": round(
                100.0 * sum(1 for h in hits if h < inner) / max(1, len(hits)), 1),
        }
    report["fit"] = {
        "course_plan_reach": round(reach, 2),
        "course_floor_y": round(floor_y, 2),
        "deck_datum": datum,
        "deck_inner_radius": inner,
        "nearest_standing_element": min(
            b["radius"] for b in hall["pylons"]["bands"]),
        "lift": round(lift, 2),
        "hall_floor_world_y": round(datum + lift, 2),
        "frame_top_min": round(min(tops), 2),
        "frame_top_max": round(max(tops), 2),
        "shots": per_shot,
    }
    data = report["fit"]
    print("\nHOW THE ROOM AND THE LENS FIT  (layout units, degrees)")
    print(f"  course plan reach from the axis   {data['course_plan_reach']:8.2f}")
    print(f"  deck inner radius (the hole)      {data['deck_inner_radius']:8.2f}"
          f"   = {data['deck_inner_radius'] / data['course_plan_reach']:.2f}x the course")
    print(f"  nearest standing element          "
          f"{data['nearest_standing_element']:8.2f}"
          f"   = {data['nearest_standing_element'] / data['course_plan_reach']:.2f}x")
    print(f"  stage lift applied                {data['lift']:8.2f}")
    print(f"  hall floor, world y               {data['hall_floor_world_y']:8.2f}")
    print(f"  frame top edge, whole film        "
          f"{data['frame_top_min']:8.2f} to {data['frame_top_max']:.2f} deg")
    print()
    print(f"{'shot':<10}{'eye y':>8}{'eye r':>8}{'aim elev':>10}"
          f"{'frame top':>11}{'floor hit r':>13}{'in hole %':>11}")
    for name, row in per_shot.items():
        print(f"{name:<10}{row['eye_y']:>8.1f}{row['eye_radius']:>8.1f}"
              f"{row['aim_elevation']:>10.1f}{row['frame_top']:>11.1f}"
              f"{row['floor_hit_radius']:>13.1f}{row['inside_the_hole']:>11.0f}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs", default="docs/validation/race2/v29_contained")
    parser.add_argument("--only", default="")
    args = parser.parse_args()
    wanted = [w for w in args.only.split(",") if w] or [
        "fit", "bands", "card", "racers", "parallax", "occlusion"]

    report: dict = {}
    for name in wanted:
        {"fit": fit, "bands": bands, "card": card, "racers": racers,
         "parallax": parallax, "occlusion": occlusion}[name](report)

    os.makedirs(args.docs, exist_ok=True)
    target = os.path.join(args.docs, "review.json")
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=1)
    print(f"\n  wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
