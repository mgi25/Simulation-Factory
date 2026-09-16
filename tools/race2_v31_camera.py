"""Build and measure the V31 readability variants against camera A.

Usage:

    python tools/race2_v31_camera.py --seed=8              # control + RA/RB/RC
    python tools/race2_v31_camera.py --only=RB             # one variant
    python tools/race2_v31_camera.py --probe               # the diagnosis, per frame

Writes, per candidate, a camera track in the layout `tools/race2_render.py`
already reads, plus a flow report, a readability report and one comparison:

    output/race2/v31_readability/<cam>/race2_switchyard_8.cameras.json
    docs/validation/race2/v31_readability/flow_<cam>.json
    docs/validation/race2/v31_readability/read_<cam>.json
    docs/validation/race2/v31_readability/compare.json

**The replay is never re-simulated.** It is read from the control run and
shared by every candidate, exactly as `tools/race2_cine.py` does it, so the
brief's locks on physics, seed, finish order and event timing hold because
there is no code path here that could break them. The race *is* re-run, with
`with_replay=False`, for its outcome and timeline only - the schedules are
authored on mechanism markers and those come from the timeline.

The control is camera A, **rebuilt** rather than read. That is deliberate and
it is the strongest test in this branch: the V28.1 plan, built through the V31
code, has to produce the delivered track byte for byte, which is what proves
every new term defaults to off.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race2 import cinematography, courses
from race2.events import extract
from race2.flow import anticipation, measure, summary
from race2.race import run_race
from race2.readability import measure_readability, readability_summary
from race2.rig import PackTrack, build_track, write_track
from race2.spine import Spine
from sloped.scale import SIM_TO_LAYOUT

OUT = "output/race2/v31_readability"
DOCS = "docs/validation/race2/v31_readability"
SOURCE = "output/race2"
# Camera A as delivered, for the byte-identity check. Written by
# `tools/race2_cine.py` and never by this tool.
CONTROL = "output/race2/v281_camera/A/race2_switchyard_8.cameras.json"

# Which group rule each candidate's `PackTrack` is built with. The control must
# be "pack" - that is what makes it the control.
RULES = {"A": "pack", "RA": "interest", "RB": "interest", "RC": "interest"}


def stations_of(course) -> dict[str, dict]:
    """Every station's centre and radius, in layout units, for Part G."""
    out: dict[str, dict] = {}
    for module_id in course.stations:
        module = course.machine.modules.get(module_id)
        if module is None:
            continue
        bounds = module.bounds()
        out[module_id] = {
            "centre": tuple(
                0.5 * (bounds.lower[axis] + bounds.upper[axis]) * SIM_TO_LAYOUT
                for axis in range(3)
            ),
            "radius": 0.5 * max(
                bounds.upper[axis] - bounds.lower[axis] for axis in range(3)
            ) * SIM_TO_LAYOUT,
        }
    return out


def context(args):
    """Course, spine, outcome, replay and markers - shared by every candidate."""
    course = courses.build(args.course)
    spine = Spine(course)
    replay_path = os.path.join(args.source,
                               f"race2_{args.course}_{args.seed}.replay.json")
    if not os.path.isfile(replay_path):
        raise SystemExit(
            f"missing {replay_path}\n  run: python tools/race2_camera.py "
            f"--course={args.course} --seed={args.seed}"
        )
    outcome, _replay = run_race(course, seed=args.seed, duration=args.duration,
                                marble_count=args.marbles, with_replay=False)
    timeline = extract(outcome, course, outcome.sim_events)
    with open(replay_path, encoding="utf-8") as handle:
        raw = json.load(handle)
    marks = cinematography.markers(course, outcome, timeline)
    return course, spine, outcome, raw, marks, replay_path


def stage(folder: str, geometry: str, replay: str) -> str:
    """One directory per candidate, in the layout the renderer expects."""
    os.makedirs(folder, exist_ok=True)
    for source in (geometry, replay):
        target = os.path.join(folder, os.path.basename(source))
        if (not os.path.isfile(target)
                or os.path.getmtime(source) > os.path.getmtime(target)):
            shutil.copyfile(source, target)
    return folder


def probe(args, spine, pack, outcome, stations) -> None:
    """The diagnosis this branch was built on, printed rather than argued.

    For a handful of frames of the delivered camera A: where the centreline
    ahead of the pack lands on screen, and why it stops being visible. The
    answer is the whole finding - it leaves *sideways*, it is never occluded,
    and the coming hairpin is one to three half-frames outside the picture.
    """
    from race2.flow import DELIVERY, _basis, _project

    with open(CONTROL, encoding="utf-8") as handle:
        track = json.load(handle)
    rows = [row for cut in track["cuts"] for row in cut["frames"]]
    print(f"{'t':>6}{'run':<9}{'ds':>5}{'x':>8}{'y':>8}{'depth':>7}  why")
    for when in (1.0, 4.0, 7.0, 10.0, 14.0, 17.0):
        row = min(rows, key=lambda r: abs(r[0] - when))
        position = (row[1], row[2], row[3])
        aim = (row[4], row[5], row[6])
        fov = row[7]
        forward, right, up = _basis(position, aim)
        s_pack = pack.pack_arcs[pack.frame_at(when)]
        for step in (0, 4, 8, 12, 16, 20, 24):
            s = min(s_pack + step, spine.length)
            point = spine.point_at(s)
            projected, depth = _project(point, position, forward, right, up,
                                        fov, DELIVERY)
            if projected is None:
                why = "behind the lens"
                x = y = float("nan")
            else:
                x, y = projected
                if abs(x) > 0.94:
                    why = "off the SIDE"
                elif abs(y) > 0.94:
                    why = "off the top/bottom"
                elif spine.blocked(position, point):
                    why = "occluded"
                else:
                    why = "visible"
            label = f"{when:6.1f}{spine.run_at(s):<9}" if step == 0 else " " * 15
            print(f"{label}{step:5d}{x:8.2f}{y:8.2f}{depth:7.1f}  {why}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--source", default=SOURCE)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--docs", default=DOCS)
    parser.add_argument("--only", default="")
    parser.add_argument("--stride", type=int, default=2)
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    course, spine, outcome, raw, marks, replay_path = context(args)
    geometry = os.path.join(args.source,
                            f"race2_{args.course}_{args.seed}.geometry.json")
    stations = stations_of(course)
    packs = {rule: PackTrack(raw, spine, outcome, group=rule)
             for rule in ("pack", "interest")}

    if args.probe:
        probe(args, spine, packs["pack"], outcome, stations)
        return 0

    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.docs, exist_ok=True)
    wanted = ["A", "RA", "RB", "RC"]
    if args.only:
        wanted = [k for k in wanted if k in args.only.split(",")]

    rails: dict[float, object] = {}
    reports: dict[str, dict] = {}
    builders = dict(cinematography.READABILITY)
    builders["A"] = cinematography.plan_a

    for key in wanted:
        pack = packs[RULES[key]]
        plan = builders[key](marks)
        track = build_track(plan, pack, spine, rails)  # type: ignore[arg-type]
        stem = f"race2_{args.course}_{args.seed}.cameras.json"
        folder = stage(os.path.join(args.out, key), geometry, replay_path)
        path = write_track(track, os.path.join(folder, stem))

        report = measure(track, pack, spine, outcome, marks)
        # `race2.flow.anticipation` takes bare centres; the readability
        # instrument needs a radius too, so the richer table is narrowed here
        # rather than the two of them being kept separately.
        report["anticipation"] = anticipation(
            track, spine, {k: v["centre"] for k, v in stations.items()},
            {k: v for k, v in marks["first"].items() if k != "studs"},
        )
        report["read"] = measure_readability(track, pack, spine, outcome,
                                             stations, stride=args.stride)
        report["path"] = path
        report["note"] = plan.note
        report["rule"] = RULES[key]
        report["pack"] = pack.describe()
        report["sha256"] = hashlib.sha256(
            open(path, "rb").read()).hexdigest()[:16]
        reports[key] = report

        for label, blob in (("flow", {k: v for k, v in report.items()
                                      if k not in ("read",)}),
                            ("read", report["read"])):
            with open(os.path.join(args.docs, f"{label}_{key}.json"), "w",
                      encoding="utf-8") as handle:
                json.dump(blob, handle, indent=1)

        if key == "A" and os.path.isfile(CONTROL):
            same = open(path, "rb").read() == open(CONTROL, "rb").read()
            report["matches_delivered"] = same
            print(f"  control camera A rebuilt: "
                  f"{'byte-identical to the delivered track' if same else 'DIFFERS'}")
            if not same:
                return 1

        if not args.quiet:
            print(f"\n=== {key}: {plan.note} ===")
            print(summary(report))
            print(readability_summary(report["read"]))
            for complaint in plan.check():
                print(f"  schedule: {complaint}")
            print(f"  track {path}  sha {report['sha256']}")

    with open(os.path.join(args.docs, "compare.json"), "w", encoding="utf-8") as handle:
        json.dump({
            "seed": args.seed,
            "course": args.course,
            "spine": spine.describe(),
            "markers": {k: v for k, v in marks.items() if k != "stations"},
            "candidates": {
                key: {k: v for k, v in report.items()
                      if k not in ("shot_rows", "cut_rows")}
                for key, report in reports.items()
            },
        }, handle, indent=1)

    if not args.quiet and len(reports) > 1:
        print("\n=== camera ===")
        head = (f"{'cam':<5}{'shots':>6}{'cuts':>6}{'mean s':>8}{'flips':>7}"
                f"{'reacq':>7}{'scale':>7}{'px':>9}{'phone':>7}{'clr':>6}{'flow':>7}")
        print(head)
        print("-" * len(head))
        for key, report in reports.items():
            print(f"{key:<5}{report['shots']:6d}{report['hard_cuts']:6d}"
                  f"{report['mean_shot']:8.2f}{report['direction_flips']:7d}"
                  f"{report['worst_reacquire']:7.3f}{report['worst_scale_jump']:7.2f}"
                  f"{report['racer_pixels'][0]:5.0f}-{report['racer_pixels'][1]:<3.0f}"
                  f"{report['phone_pixels'][0]:7.1f}"
                  f"{report['min_lens_clearance']:6.2f}{report['flow_score']:7.1f}")

        print("\n=== readability ===")
        head = (f"{'cam':<5}{'grp':>6}{'vis%':>7}{'all%':>7}{'width':>7}{'y':>8}"
                f"{'ahead_u':>9}{'seen_u':>8}{'short%':>8}{'turn':>7}{'mech%':>7}"
                f"{'worst m':>8}{'gap s':>7}")
        print(head)
        print("-" * len(head))
        for key, report in reports.items():
            read = report["read"]
            print(f"{key:<5}{read['group']['mean_size']:6.2f}"
                  f"{read['group']['visible_pct']:7.1f}"
                  f"{read['group']['all_visible_pct']:7.1f}"
                  f"{read['group']['screen_width_mean']:7.3f}"
                  f"{read['group']['screen_y_mean']:+8.3f}"
                  f"{read['track']['forward_arc_mean']:9.2f}"
                  f"{read['track']['seen_arc_mean']:8.2f}"
                  f"{read['track']['short_path_pct']:8.1f}"
                  f"{read['turns']['turn_read_mean']:7.2f}"
                  f"{read['mechanism']['dominant_pct']:7.1f}"
                  f"{read['racer_visible_pct_min']:8.1f}"
                  f"{read['racer_longest_gap_s']:7.2f}")

        print("\n=== per racer, visible % of its own race ===")
        ids = sorted(reports[wanted[0]]["read"]["racers"])
        print(f"{'cam':<5}" + "".join(f"{'m' + m:>7}" for m in ids))
        for key, report in reports.items():
            row = report["read"]["racers"]
            print(f"{key:<5}" + "".join(
                f"{row[m]['visible_pct']:7.1f}" for m in ids))
        print(f"\n{'cam':<5}longest disappearance, seconds")
        for key, report in reports.items():
            row = report["read"]["racers"]
            print(f"{key:<5}" + "".join(
                f"{row[m]['longest_gap_s']:7.2f}" for m in ids))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
