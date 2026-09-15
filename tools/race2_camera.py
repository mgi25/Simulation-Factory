"""One race, its event timeline, its camera schedule and the framing report.

Usage:

    python tools/race2_camera.py --course=switchyard --seed=5501 \
        --out=output/race2 --docs=docs/validation/race2

Writes four things and prints three:

    <out>/race2_<course>_<seed>.replay.json     the physics record
    <out>/race2_<course>_<seed>.geometry.json   the course, for the renderer
    <out>/race2_<course>_<seed>.cameras.json    the solved camera track
    <docs>/events_<seed>.json                   the timeline and its metrics

    the race-event map      what changed, and when
    the camera-event map    which shot covered it, and why
    the framing report      how big the racers were and whether the next
                            mechanism was on screen before it was hit

The two maps are printed side by side on purpose. A shot with nothing in its
right-hand column is a shot that is covering nothing, which is the failure the
brief's Part N exists to make visible.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from marble3d.replay import write_replay

from race2 import concepts, courses
from race2.camera import TrackState, build_track, write_track
from race2.events import extract
from race2.export import write_geometry
from race2.framing import report, summary
from race2.race import run_race
from race2.shots import plan_for


def build_course(name: str):
    return courses.build(name) if name in courses.COURSES else concepts.build(name)


def camera_map(track: dict, timeline) -> str:
    """Every shot beside the events it covers."""
    lines = [f"{'from':>7}{'to':>8}  {'shot':<24}{'mode':<22} events covered"]
    lines.append("-" * 96)
    for cut in track["cuts"]:
        start, stop = float(cut["from"]), float(cut["to"])
        covered = [
            f"{e.kind}"
            for e in timeline.events
            if start <= e.time < stop and e.kind != "overtake_cluster"
        ]
        seen: list[str] = []
        for kind in covered:
            if kind not in seen:
                seen.append(kind)
        lines.append(
            f"{start:7.2f}{stop:8.2f}  {cut['name']:<24}{cut.get('mode', ''):<22}"
            f"{', '.join(seen) if seen else '-- nothing --'}"
        )
        if cut.get("note"):
            lines.append(f"{'':17}  why: {cut['note']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course", default="switchyard")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--duration", type=float, default=40.0)
    parser.add_argument("--marbles", type=int, default=8)
    parser.add_argument("--out", default="output/race2")
    parser.add_argument("--docs", default="docs/validation/race2")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    course = build_course(args.course)
    outcome, replay = run_race(course, seed=args.seed, duration=args.duration,
                               marble_count=args.marbles, with_replay=True)
    if replay is None:
        print("no replay produced", file=sys.stderr)
        return 1
    timeline = extract(outcome, course, outcome.sim_events)

    stem = os.path.join(args.out, f"race2_{args.course}_{args.seed}")
    os.makedirs(args.out, exist_ok=True)
    replay_path = write_replay(replay, f"{stem}.replay.json")
    geometry_path = write_geometry(course, f"{stem}.geometry.json")

    raw = json.loads(open(replay_path, encoding="utf-8").read())
    state = TrackState(raw, course, outcome)
    plan = plan_for(course, outcome, timeline)
    complaints = plan.check()
    track = build_track(plan, state, course)
    camera_path = write_track(track, f"{stem}.cameras.json")

    os.makedirs(args.docs, exist_ok=True)
    events_path = os.path.join(args.docs, f"events_{args.course}_{args.seed}.json")
    with open(events_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "course": course.to_json(),
                "race": outcome.to_json(),
                "timeline": timeline.to_json(),
                "camera": {
                    "duration": track["duration"],
                    "cuts": [
                        {k: v for k, v in cut.items() if k != "frames"}
                        for cut in track["cuts"]
                    ],
                },
            },
            handle,
            indent=1,
        )

    rows = report(track, raw, course, outcome, timeline)
    framing_path = os.path.join(args.docs, f"framing_{args.course}_{args.seed}.json")
    with open(framing_path, "w", encoding="utf-8") as handle:
        json.dump([row.to_json() for row in rows], handle, indent=1)

    if not args.quiet:
        print(f"=== {course.title}  seed {args.seed} ===")
        print(f"finished {outcome.finished}/{len(outcome.racers)}  "
              f"lead changes {outcome.lead_changes}  "
              f"race {timeline.start:.2f} to {timeline.end:.2f} s")
        winner = outcome.winner()
        if winner is not None:
            print(f"winner m{winner.marble_id} from bay {winner.start_slot}, "
                  f"ranks {winner.ranks}")
        print()
        print(timeline.render())
        print()
        print(camera_map(track, timeline))
        print()
        print(summary(rows))
        for complaint in complaints:
            print(f"  schedule: {complaint}")

    print(f"\nreplay   {replay_path}")
    print(f"geometry {geometry_path}")
    print(f"cameras  {camera_path}")
    print(f"events   {events_path}")
    print(f"framing  {framing_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
