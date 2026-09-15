"""Build and measure the V28.1 candidate cameras over one hero replay.

Usage:

    python tools/race2_cine.py --seed=8                  # control + A + B + C
    python tools/race2_cine.py --seed=8 --only=B         # one candidate
    python tools/race2_cine.py --seed=8 --rail           # print the solved rail

Writes, per candidate, a camera track beside the replay in the name the
renderer already expects, plus one JSON of flow metrics per candidate and a
comparison table:

    output/race2/v281_camera/race2_switchyard_<seed>_<cam>.cameras.json
    docs/validation/race2/v281_camera/flow_<cam>.json
    docs/validation/race2/v281_camera/compare.json

**The replay is never re-simulated here.** It is read from the control run, so
every candidate is provably filming the same race - the brief's locks on
physics, seed, finish order and event timing are satisfied by there being no
code path in this tool that could break them. If the replay is missing the tool
says so and names the command that makes it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from race2 import cinematography, courses
from race2.events import extract
from race2.flow import measure, summary
from race2.race import run_race
from race2.rig import PackTrack, build_track, write_track
from race2.spine import Spine, camera_rail


def _paths(out: str, course: str, seed: int) -> tuple[str, str, str]:
    stem = os.path.join(out, f"race2_{course}_{seed}")
    return (f"{stem}.geometry.json", f"{stem}.replay.json", f"{stem}.cameras.json")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=8)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--source", default="output/race2",
                        help="where the control replay and geometry live")
    parser.add_argument("--out", default="output/race2/v281_camera")
    parser.add_argument("--docs", default="docs/validation/race2/v281_camera")
    parser.add_argument("--only", default="")
    parser.add_argument("--rail", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    course = courses.build(args.course)
    spine = Spine(course)
    if args.rail:
        rail = camera_rail(spine)
        print("spine ", json.dumps(spine.describe()))
        print("rail  ", json.dumps(rail.describe()))
        print(f"{'s':>7} {'run':<8}{'azimuth':>9}{'height':>8}{'clear':>7}{'seen':>6}")
        for index in range(0, len(rail.arc), 2):
            s = rail.arc[index]
            print(f"{s:7.1f} {spine.run_at(s):<8}{rail.azimuth[index]:9.1f}"
                  f"{rail.height[index]:8.2f}{rail.clearance[index]:7.2f}"
                  f"{rail.seen[index]:6d}")
        return 0

    geometry, replay_path, control = _paths(args.source, args.course, args.seed)
    if not os.path.isfile(replay_path):
        print(f"missing {replay_path}\n  run: python tools/race2_camera.py "
              f"--course={args.course} --seed={args.seed}", file=sys.stderr)
        return 1

    # The race is re-run only for its outcome and timeline - the *replay* used
    # for every camera is the one on disk, so the physics cannot differ between
    # the control and the candidates.
    outcome, _replay = run_race(course, seed=args.seed, duration=args.duration,
                                marble_count=args.marbles, with_replay=False)
    timeline = extract(outcome, course, outcome.sim_events)
    raw = json.loads(open(replay_path, encoding="utf-8").read())

    pack = PackTrack(raw, spine, outcome)
    marks = cinematography.markers(course, outcome, timeline)
    os.makedirs(args.out, exist_ok=True)
    os.makedirs(args.docs, exist_ok=True)

    def stage(camera: str) -> str:
        """One directory per candidate, in the layout `tools/race2_render.py`
        already expects: the same geometry, the same replay, its own camera
        track. Copying the replay four times is 50 MB of scratch and it buys
        the renderer needing no new flag and no new code path - which is what
        keeps the V28 control renderable by the command that always rendered
        it."""
        folder = os.path.join(args.out, camera)
        os.makedirs(folder, exist_ok=True)
        for source in (geometry, replay_path):
            target = os.path.join(folder, os.path.basename(source))
            if (not os.path.isfile(target)
                    or os.path.getmtime(source) > os.path.getmtime(target)):
                shutil.copyfile(source, target)
        return folder

    wanted = [k for k in ("A", "B", "C") if not args.only or k in args.only.split(",")]
    rails: dict[float, object] = {}
    reports: dict[str, dict] = {}

    # The control, measured with the same instrument. Its track is V28's, read
    # rather than rebuilt: this tool must not be able to change it.
    if os.path.isfile(control):
        control_track = json.loads(open(control, encoding="utf-8").read())
        control_track.setdefault("camera", "V28")
        reports["V28"] = measure(control_track, pack, spine, outcome, marks)
        folder = stage("V28")
        shutil.copyfile(control, os.path.join(folder, os.path.basename(control)))
        reports["V28"]["path"] = os.path.join(folder, os.path.basename(control))

    for key in wanted:
        plan = cinematography.CANDIDATES[key](marks)
        complaints = plan.check()
        track = build_track(plan, pack, spine, rails)  # type: ignore[arg-type]
        stem = f"race2_{args.course}_{args.seed}.cameras.json"
        path = write_track(track, os.path.join(stage(key), stem))
        report = measure(track, pack, spine, outcome, marks)
        report["path"] = path
        report["note"] = plan.note
        reports[key] = report
        with open(os.path.join(args.docs, f"flow_{key}.json"), "w",
                  encoding="utf-8") as handle:
            json.dump(report, handle, indent=1)
        if not args.quiet:
            print(f"\n=== camera {key}: {plan.note} ===")
            print(summary(report))
            for complaint in complaints:
                print(f"  schedule: {complaint}")
            print(f"  track {path}")

    with open(os.path.join(args.docs, "compare.json"), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "seed": args.seed,
                "course": args.course,
                "pack": pack.describe(),
                "spine": spine.describe(),
                "markers": {k: v for k, v in marks.items() if k != "stations"},
                "candidates": {
                    key: {k: v for k, v in report.items()
                          if k not in ("shot_rows", "cut_rows")}
                    for key, report in reports.items()
                },
            },
            handle, indent=1,
        )

    if not args.quiet:
        print("\n=== comparison ===")
        header = (f"{'camera':<8}{'shots':>6}{'cuts':>6}{'mean s':>8}{'short':>7}"
                  f"{'long':>7}{'2-long%':>9}{'flips':>7}{'reacq':>7}{'scale':>7}"
                  f"{'px':>8}{'phone':>7}{'flow':>7}")
        print(header)
        print("-" * len(header))
        for key in ("V28", "A", "B", "C"):
            report = reports.get(key)
            if not report:
                continue
            print(f"{key:<8}{report['shots']:6d}{report['hard_cuts']:6d}"
                  f"{report['mean_shot']:8.2f}{report['shortest_shot']:7.2f}"
                  f"{report['longest_shot']:7.2f}"
                  f"{report['two_longest_share'] * 100:8.0f}%"
                  f"{report['direction_flips']:7d}{report['worst_reacquire']:7.3f}"
                  f"{report['worst_scale_jump']:7.2f}"
                  f"{report['racer_pixels'][0]:5.0f}-{report['racer_pixels'][1]:<3.0f}"
                  f"{report['phone_pixels'][0]:7.1f}{report['flow_score']:7.1f}")
        print()
        print(f"pack  {json.dumps(pack.describe())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
