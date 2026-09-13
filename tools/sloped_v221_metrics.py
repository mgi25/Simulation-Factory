"""What the finished V22.1 film is, measured, against V22.

    python tools/sloped_v221_metrics.py

The three prototypes each measured their own track and none of those tracks was
rendered. This measures the **integrated** one, which is a different document in
every place the passes met:

* the preview was solved against V22's start camera, and V22.1's stands 1.6
  layout units away at a different elevation. Its handoff numbers are therefore
  not the prototype's;
* the shuffle prototype measured a start-only track built by
  `v221_shuffle.build_start_track`; production's start is the first two cuts of
  a chase solve, which smooths across a boundary the prototype did not have;
* the finish prototype rewrote the tail of *V22's* chase. Production rewrites
  the tail of a chase whose own start is 1.983 s longer.

Nothing here renders, simulates or writes anything but the report. Every
instrument is the one the pass that cares about that question already built -
`v221_preview.pace_report`, `v221_shuffle.join_report`, the finish tool's
`measure`, and `readability`/`chase_camera` for the race body - so a number here
is comparable with a number there.

The race body is the section to read first: V22.1 is a pass over three joins,
and the whole of it is wrong if the middle of the film moved.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.join(os.getcwd(), "tools"))

from sloped import (
    chase_camera,
    presentation,
    readability,
    sightlines,
    terrain,
    v22,
    v221,
    v221_preview,
    v221_shuffle,
)
from sloped.course import sloped_course

import sloped_v221_finish as finish_tool
from sloped_v22_metrics import _pool

OUT_DIR = os.path.join("output", "sloped_race_v1")
DOCS_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v221_final")

# The race body, cut for cut. **`finish` has no pair and that is the point of
# the pass**: V22 ends on V19's spectator lens and V22.1 ends on the chase
# itself, so the two are not the same shot and comparing their numbers would be
# comparing a stand with a park. It is measured on its own, below.
#
# `merge` is paired but truncated: V22.1 splits out of the chase at replay
# 18.900, which is inside V22's merge window, so V22.1's merge is 0.483 s where
# V22's is 1.783. The rows carry `seconds` so the difference is visible rather
# than hidden inside a mean.
PAIRS = (
    ("opening / start", ("start",), ("start",)),
    ("first descent", ("descent",), ("descent",)),
    ("obstacle", ("obstacle",), ("obstacle",)),
    ("fork", ("fork",), ("fork",)),
    ("branches", ("branches",), ("branches",)),
    ("merge", ("merge",), ("merge",)),
)

def _load(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _clock(track: dict[str, Any], prefix: float) -> presentation.Clock:
    master = int(round(float(track["duration"]) * v221.FPS)) + 1
    return presentation.Clock(
        tuple(
            (row["out"][0], row["out"][1], row["replay"][0], row["replay"][1])
            for row in track["edit"]
        ),
        fps=v221.FPS, master_frames=master, prefix=prefix,
    )


def report(seed: int = 5432) -> dict[str, Any]:
    replay = _load(os.path.join(OUT_DIR, f"race_{seed}.json"))
    machine = sloped_course(routes="both")
    cfg = terrain.terrain_config(machine.runs)
    bundle = sightlines.Bundle(
        sightlines.course_solids(machine, lambda x, z: terrain.height(x, z, cfg))
    )

    new = _load(os.path.join(OUT_DIR, f"cameras_v221_{seed}.json"))
    old = _load(os.path.join(OUT_DIR, f"cameras_v22_{seed}.json"))
    new_preview = _load(os.path.join(OUT_DIR, f"preview_v221_{seed}.json"))
    old_preview = _load(os.path.join(OUT_DIR, f"preview_v22_{seed}.json"))

    out: dict[str, Any] = {"seed": seed}

    # --- the shape of the film ----------------------------------------------
    shapes = {}
    for tag, track, preview in (("v22", old, old_preview), ("v221", new, new_preview)):
        prefix = v22.preview_prefix(preview)
        clock = _clock(track, prefix)
        shapes[tag] = {
            "preview_frames": v22.preview_frames(preview),
            "preview_seconds": round(prefix, 6),
            "hold_frames": clock.hold_frames,
            "race_frames": clock.master_frames,
            "frames": clock.frames,
            "runtime": round(clock.duration, 6),
            "replay_covered": round(float(track["duration"]), 6),
            "omitted": round(float(track["omitted"]), 6),
            "omissions": [
                {"at": round(at, 4), "dropped": round(dropped, 6)}
                for at, dropped in presentation.omissions(clock)
            ],
            "cuts": len(track["cuts"]),
        }
    out["film"] = shapes
    out["film"]["delta"] = {
        key: round(shapes["v221"][key] - shapes["v22"][key], 6)
        for key in ("preview_seconds", "runtime", "frames", "race_frames")
    }

    # --- the preview --------------------------------------------------------
    #
    # Re-solved rather than read back: `pace_report` needs the solve, not the
    # written rows. The flight is deterministic and it is solved against the
    # track on disk, so `_same_flight` proves the two are the same shot.
    resolved, paced = v221.build_preview_track(new, machine, seed)
    _same_flight(new_preview, resolved)
    out["preview"] = {
        "frames": v221.preview_frames(resolved),
        "prefix": round(v221.preview_prefix(resolved), 6),
        "duration": paced["duration"],
        "max_step": paced["max_step"],
        "mean_step": paced["mean_step"],
        "max_turn": paced["max_turn"],
        "max_yaw": paced["max_yaw"],
        "max_pitch": paced["max_pitch"],
        "max_aim_step": paced["max_aim_step"],
        "breath_ratio": paced["breath_ratio"],
        "flat_units_per_frame": paced["flat_units_per_frame"],
        "v22_peak_step": paced["v22_peak_step"],
        "mean_visible_fraction": paced["mean_visible_fraction"],
        "min_sight_clearance": paced["min_sight_clearance"],
        "landmarks_seen": paced["landmarks_seen"],
        "centre_seconds": paced["centre_seconds"],
        "subject_seconds": {k: round(v, 3)
                            for k, v in paced["subject_seconds"].items()},
        "handoff": paced["handoff"],
        "problems": paced["problems"],
        "handoff_columns": v221.assert_handoff(new, new_preview),
    }

    # --- the start ----------------------------------------------------------
    starts = {}
    for tag, track, plan in (("v22", old, v221_shuffle.PLANS["v22"]),
                             ("v221", new, v221.START)):
        window = {
            "duration": float(track["cuts"][1]["to"]) - float(track["cuts"][0]["from"]),
            "cuts": track["cuts"][:2],
        }
        row = v221_shuffle.join_report(window, replay, plan, machine)
        starts[tag] = {
            "plan": row["plan"],
            "live": row["live"],
            "omitted": row["omitted"],
            "omitted_frames": row["omitted_frames"],
            "camera_step_join": row["camera_step_join"],
            "camera_reach_change": row["camera_reach_change"],
            "aim_step_join": row["aim_step_join"],
            "camera_step_inside": row["camera_step_inside"],
            "rotor": row["rotor"],
            "marbles": {k: row["marbles"][k]
                        for k in ("max_sim", "mean_sim", "max_px", "max_diameters")},
            "anticipation": row["live_anticipation"],
            "last_collision_to_gate": row["last_collision_to_gate"],
        }
    out["start"] = starts
    out["start"]["beats"] = v221_shuffle.rotor_timeline(machine)

    # --- the race body ------------------------------------------------------
    out["body"] = {}
    reads = {tag: readability.readability_report(track, replay, stride=2)
             for tag, track in (("v22", old), ("v221", new))}
    seen = {tag: readability.visibility_report(track, replay, machine, bundle, stride=6)
            for tag, track in (("v22", old), ("v221", new))}
    ahead = {tag: chase_camera.chase_report(track, replay, machine, bundle, stride=6)
             for tag, track in (("v22", old), ("v221", new))}
    for label, old_names, new_names in PAIRS:
        row: dict[str, Any] = {}
        for tag, names in (("v22", old_names), ("v221", new_names)):
            row[tag] = {
                "seconds": round(sum(float(r["seconds"]) for r in reads[tag]
                                     if r["cut"] in names), 3),
                "px_median": round(_pool(reads[tag], names, "px_median"), 1),
                "in_frame": round(_pool(reads[tag], names, "in_frame_mean"), 2),
                "visible": round(_pool(seen[tag], names, "visible_mean", "sampled"), 2),
                "hidden_share": round(_pool(seen[tag], names, "hidden_share",
                                            "sampled"), 3),
                "ahead_share": round(_pool(ahead[tag], names, "ahead_share"), 3),
                "ahead_units": round(_pool(ahead[tag], names, "ahead_units"), 1),
                "camera_step": round(max([float(r["camera_step"]) for r in reads[tag]
                                          if r["cut"] in names] or [0.0]), 3),
            }
        out["body"][label] = row

    # --- the finish ---------------------------------------------------------
    measured = finish_tool.measure(
        v221.FINISH, new, replay, machine, bundle, v221.FINISH.split
    )
    out["finish"] = {
        "strategy": v221.FINISH.name,
        "split": v221.FINISH.split,
        "shape": measured["shape"],
        "motion": measured["motion"],
        "screen": measured["screen"],
        "lead": measured["finish_lead"],
        "winner": measured["winner"],
        "all_eight": measured["all_eight"],
        "window_after": measured["window_after"],
        "joins": {k: measured["joins"][k]
                  for k in ("boundaries", "max_jump", "hard_cuts")},
        "discontinuities": measured["discontinuities"],
        "findings": measured["findings"],
    }
    # V22's own finish, for the record: it is a different shot, not a worse one,
    # and the only number that is a like-for-like comparison is the lead time.
    out["finish"]["v22"] = {
        "lead": finish_tool.finish_lead(old, replay, machine, bundle),
        "joins": {k: finish_tool.joins(old, replay)[k]
                  for k in ("boundaries", "max_jump", "hard_cuts")},
    }

    # --- the whole track ----------------------------------------------------
    out["continuity"] = {}
    for tag, track in (("v22", old), ("v221", new)):
        joins = readability.continuity_report(track, replay)
        values = [float(j["jump"]) for j in joins if j.get("jump") is not None]
        out["continuity"][tag] = {
            "boundaries": len(joins),
            "measured": len(values),
            "max_jump": round(max(values or [0.0]), 4),
            "hard_cuts": sum(1 for v in values if v > readability.MAX_CUT_JUMP),
        }
    out["findings"] = {
        "v221": measured["findings"],
        "v221_chase_checker": chase_camera.check_chase(new, replay),
    }
    return out


def _same_flight(written: dict[str, Any], resolved: dict[str, Any]) -> None:
    """The preview on disk is the one just re-solved, to the written precision."""
    a = {round(float(row[0]), 6): row
         for cut in written["cuts"] for row in cut["frames"]}
    b = {round(float(row[0]), 6): row
         for cut in resolved["cuts"] for row in cut["frames"]}
    if set(a) != set(b):
        raise SystemExit("the written preview and the re-solved one differ in frames")
    worst = max(
        max(abs(float(a[when][i]) - float(b[when][i])) for i in range(1, 8))
        for when in a
    )
    if worst > 1e-3:
        raise SystemExit(
            f"the written preview is stale: {worst:.6f} from the re-solve"
        )


def _print(data: dict[str, Any]) -> None:
    film = data["film"]
    print("the film")
    print(f"  {'':22s} {'v22':>12s} {'v221':>12s}")
    for key in ("preview_frames", "preview_seconds", "race_frames", "frames",
                "runtime", "omitted", "cuts"):
        print(f"  {key:22s} {film['v22'][key]:>12} {film['v221'][key]:>12}")
    print(f"  runtime moves {film['delta']['runtime']:+.3f} s "
          f"({film['delta']['frames']:+d} frames)")

    preview = data["preview"]
    print("\nthe preview")
    print(f"  {preview['frames']} frames, {preview['prefix']:.4f} s of screen, "
          f"{preview['duration']:.4f} s of frame centres")
    print(f"  step max {preview['max_step']:.3f}  turn max {preview['max_turn']:.3f}"
          f"  breath {preview['breath_ratio']:.1f}x"
          f"  flat {preview['flat_units_per_frame']:.3f} vs V22's peak "
          f"{preview['v22_peak_step']:.3f}")
    print(f"  visible {100.0 * preview['mean_visible_fraction']:.1f}% of the ribbon, "
          f"{preview['landmarks_seen']}/8 landmarks")
    print("  landmark   centre   subject")
    for name, second in sorted(preview["centre_seconds"].items(),
                               key=lambda kv: kv[1]):
        print(f"    {name:10s} {second:6.3f}    "
              f"{preview['subject_seconds'].get(name, 0.0):5.3f}")
    hand = preview["handoff"]
    print(f"  handoff  pose {hand['pose_delta']:.6f}  aim {hand['aim_delta']:.6f}  "
          f"fov {hand['fov_delta']:.6f}")
    print(f"           velocity residual {hand['velocity_residual']:+.5f}  "
          f"turn residual {hand['turn_residual']:+.5f}")
    print(f"           preview last step {hand['last_step']:.5f}  "
          f"race first step {hand['race_first_step']:.5f}")
    print(f"  columns  " + "  ".join(f"{k} {v:.6f}"
                                     for k, v in preview["handoff_columns"].items()))
    print(f"  problems {preview['problems'] or 'none'}")

    start = data["start"]
    print("\nthe start")
    print(f"  {'':24s} {'v22':>12s} {'v221':>12s}")
    for key in ("live", "omitted", "omitted_frames", "camera_step_join",
                "camera_reach_change", "aim_step_join", "camera_step_inside"):
        print(f"  {key:24s} {start['v22'][key]:>12} {start['v221'][key]:>12}")
    for key in ("phase_error_deg", "lift_change"):
        print(f"  rotor {key:18s} {start['v22']['rotor'][key]:>12} "
              f"{start['v221']['rotor'][key]:>12}")
    for key in ("max_sim", "max_diameters"):
        print(f"  marbles {key:16s} {start['v22']['marbles'][key]:>12} "
              f"{start['v221']['marbles'][key]:>12}")
    for key in ("spin_down", "blade_lift", "still", "to_gate"):
        print(f"  anticipation {key:11s} {start['v22']['anticipation'][key]:>12} "
              f"{start['v221']['anticipation'][key]:>12}")

    print("\nthe race body, v22 -> v221")
    print(f"  {'':16s} {'seconds':>14s} {'px':>12s} {'in frame':>13s} "
          f"{'visible':>13s} {'ahead u':>13s}")
    for label, row in data["body"].items():
        def pair(key, fmt="%.2f"):
            return (f"{fmt % row['v22'][key]:>6s} {fmt % row['v221'][key]:>6s}")
        print(f"  {label:16s} {pair('seconds', '%.2f'):>14s} "
              f"{pair('px_median', '%.0f'):>12s} {pair('in_frame'):>13s} "
              f"{pair('visible'):>13s} {pair('ahead_units', '%.1f'):>13s}")

    fin = data["finish"]
    print("\nthe finish")
    print(f"  strategy {fin['strategy']}, split at replay {fin['split']}")
    print(f"  settle {fin['shape']['settle']:.3f} s, parked at replay "
          f"{fin['shape']['parked_at']:.3f}, aim settle "
          f"{fin['shape']['aim_settle']:.2f} s")
    print(f"  camera   max step {fin['motion']['max_step']:.3f} u/frame  "
          f"max turn {fin['motion']['max_turn']:.3f} deg/frame")
    print(f"  screen   max racer {fin['screen']['max_px']:.1f} px/frame")
    print(f"  lead     finish visible {fin['lead']['seconds']:.3f} s before the "
          f"winner (V22: {fin['v22']['lead']['seconds']:.3f} s)")
    print(f"  winner   {fin['winner']['px_at_crossing']:.1f} px at the crossing")
    print(f"  all 8    crossed {fin['all_eight']['crossed']}  "
          f"in frame {fin['all_eight']['in_frame']}  clear {fin['all_eight']['clear']}  "
          f"readable {fin['all_eight']['readable']}")
    print(f"  joins    {fin['joins']['hard_cuts']} hard cuts, max jump "
          f"{fin['joins']['max_jump']:.3f} (V22: {fin['v22']['joins']['hard_cuts']} "
          f"hard cuts, {fin['v22']['joins']['max_jump']:.3f})")
    print(f"  discontinuities {fin['discontinuities']}   findings "
          f"{fin['findings'] or 'none'}")

    print("\nthe whole track")
    for tag, row in data["continuity"].items():
        print(f"  {tag:5s} {row['boundaries']} boundaries, {row['measured']} measured, "
              f"max jump {row['max_jump']:.3f}, {row['hard_cuts']} hard cuts")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    args = parser.parse_args(argv)
    data = report(args.seed)
    _print(data)
    os.makedirs(DOCS_DIR, exist_ok=True)
    path = os.path.join(DOCS_DIR, "metrics.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
