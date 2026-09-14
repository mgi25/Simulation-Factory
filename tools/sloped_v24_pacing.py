"""The V24 pacing lab: timeline proofs cut from the V22.1 picture.

    python tools/sloped_v24_pacing.py --stage all --seed 5432

**TIMING PROOF ONLY.** Everything this writes is the V22.1 master with frames
taken out of it. The lenses, the grade, the framing and the hook are V22.1's and
none of them is a proposal - Session A owns the hook composition, and a still
from one of these clips is a still of V22.1. What is being proposed here is
*when things happen*.

Stages:

    machine   read the start mechanism's five instants off the replay
    survey    where the time is: churn, and what an omission costs on screen
    report    the candidates, measured against everything the brief asks
    clip      write one silent proof clip per candidate, plus the V22.1 control
    verify    pull frames back out of the clips and match them to the master
    all       all five

Inputs, all of them already on disk and none of them rebuilt here:

    output/sloped_race_v1/race_5432.json             the locked replay
    output/sloped_race_v1/cameras_v221_5432.json     the V22.1 camera track
    output/sloped_race_v1/v221/race_master.mp4       the V22.1 race master

The course preview master is deliberately *not* an input. V24 has none.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
from typing import Any, Sequence

sys.path.insert(0, os.getcwd())

from PIL import Image, ImageDraw

from sloped import overlays, v24_timeline
from sloped.v22_timeline import churn
from sloped.v24_timeline import (
    CANDIDATES,
    REJECTED,
    FPS,
    Master,
    Plan,
    build,
    kept_frames,
    load_master,
    machine_state,
    report,
    screen_field,
)

OUT_DIR = os.path.join("output", "sloped_race_v1")
WORK_DIR = os.path.join(OUT_DIR, "v24")
MASTER = os.path.join(OUT_DIR, "v221", "race_master.mp4")
DOC_DIR = os.path.join("docs", "validation", "sloped_race_v1", "v24_pacing")

WIDTH, HEIGHT = 1080, 1920
VIDEO_CRF = 18
VIDEO_PRESET = "medium"

# The label burned into every clip. A proof clip that escapes this directory
# without it is a still of V22.1 being read as a V24 framing proposal.
LABEL = "TIMING PROOF ONLY"


class PacingError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _load(seed: int) -> tuple[dict[str, Any], dict[str, Any], Master]:
    replay_path = os.path.join(OUT_DIR, f"race_{seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_v221_{seed}.json")
    for path in (replay_path, track_path):
        if not os.path.isfile(path):
            raise PacingError(f"missing input: {path}")
    with open(replay_path, "r", encoding="utf-8") as handle:
        replay = json.load(handle)
    with open(track_path, "r", encoding="utf-8") as handle:
        track = json.load(handle)
    return replay, track, load_master(track)


def _ffmpeg() -> str:
    found = shutil.which("ffmpeg")
    if found is None:
        raise PacingError("ffmpeg is not on PATH")
    return found


def _run(command: Sequence[str], label: str) -> None:
    done = subprocess.run(command, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if done.returncode != 0:
        tail = "\n".join((done.stderr or "").splitlines()[-20:])
        raise PacingError(f"{label}: exited {done.returncode}\n{tail}")


# --- machine ----------------------------------------------------------------


def stage_machine(replay: dict[str, Any]) -> dict[str, float]:
    """The start mechanism's instants, read off the recorded transforms.

    Every timing in `sloped/v24_timeline.py` is quoted against these and the
    tests re-derive them, so this stage is the audit trail for the constants
    rather than a display.
    """
    frames = replay["frames"]
    marks: dict[str, float] = {}
    previous: dict[str, float] | None = None
    for index in range(1, len(frames)):
        when = round(float(frames[index]["t"]), 6)
        if when > 8.0:
            break
        state = machine_state(replay, when)
        if previous is not None:
            if "gates" not in marks and abs(
                state.get("paddle_height", 0.0) - previous.get("paddle_height", 0.0)
            ) > 1e-4:
                marks["gates"] = when
            if "rotor_start" not in marks and state.get("rotor_rate", 0.0) > 1.0:
                marks["rotor_start"] = when
            if ("rotor_start" in marks and "spin_down" not in marks
                    and state.get("rotor_rate", 0.0) < previous.get("rotor_rate", 0.0) - 0.05):
                marks["spin_down"] = when
            if ("spin_down" in marks and "rotor_stop" not in marks
                    and state.get("rotor_rate", 0.0) < 0.05):
                marks["rotor_stop"] = when
            if "lift" not in marks and abs(
                state.get("rotor_height", 0.0) - previous.get("rotor_height", 0.0)
            ) > 1e-3:
                marks["lift"] = when
            if ("lift" in marks and "lift_done" not in marks and when > marks["lift"]
                    and abs(state.get("rotor_height", 0.0)
                            - previous.get("rotor_height", 0.0)) < 1e-4):
                marks["lift_done"] = when
            if "release" not in marks and abs(
                state.get("panel_height", 0.0) - previous.get("panel_height", 0.0)
            ) > 1e-4:
                marks["release"] = when
        previous = state

    print("the start mechanism, from the replay's own transforms")
    for key in ("gates", "rotor_start", "spin_down", "rotor_stop", "lift",
                "lift_done", "release"):
        if key in marks:
            print(f"    {key:12s} replay {marks[key]:8.4f}")
    rate = machine_state(replay, 3.0).get("rotor_rate", 0.0)
    per_frame = math.degrees(rate / FPS)
    print(f"    rotor rate   {rate:.3f} rad/s = {per_frame:.4f} deg a frame; "
          f"one revolution is {360.0 / per_frame:.3f} frames")
    return marks


# --- survey -----------------------------------------------------------------


def stage_survey(replay: dict[str, Any], master: Master) -> None:
    """Where the time is, and what taking it would cost on the delivered frame."""
    print("the master, window by window")
    print(f"{'window':10s} {'frames':>12s} {'replay':>18s} {'s':>7s} {'churn':>7s}")
    for index, (out_from, out_to, replay_from, replay_to) in enumerate(master.segments):
        mine = [f for f in range(master.frames) if master.window_of(f) == index]
        low, high = master.replay_of[mine[0]], master.replay_of[mine[-1]]
        print(f"{master.names[index]:10s} {mine[0]:5d}..{mine[-1]:<5d} "
              f"{low:8.3f}..{high:<8.3f} {len(mine) / FPS:7.3f} "
              f"{churn(replay, low, high):7.2f}")
    print(f"{'':10s} {master.frames:>12d} {'':>18s} "
          f"{master.frames / FPS:7.3f}")

    print()
    print("the bar: the join the shipped V22.1 film already contains")
    _join_line("b116 (master 111 -> 112)", master, replay, 111, 112)
    print("    a normal one-frame step, either side of it")
    for frame in (109, 110, 113):
        _join_line(f"      master {frame} -> {frame + 1}", master, replay,
                   frame, frame + 1)

    print()
    print("what a 30-frame omission costs, best placement inside each window")
    for index in range(len(master.segments)):
        mine = [f for f in range(master.frames) if master.window_of(f) == index]
        best = None
        for first in range(mine[0], mine[-1] - 31, 5):
            rows = _cost(master, replay, first, first + 31)
            if best is None or rows["widths_mean"] < best[1]["widths_mean"]:
                best = (first, rows)
        if best is None:
            continue
        first, rows = best
        verdict = v24_timeline.machine_match(
            replay, master.replay_of[first], master.replay_of[first + 31]
        )
        note = "; ".join(verdict["problems"]) or "legal"
        print(f"    {master.names[index]:10s} keep {first:4d} then {first + 31:4d}  "
              f"replay {master.replay_of[first]:7.3f} -> "
              f"{master.replay_of[first + 31]:7.3f}  "
              f"{rows['px_mean']:6.1f} px  {rows['widths_mean']:5.2f} widths  "
              f"camera steps {rows['camera']:6.3f}")
        print(f"    {'':10s}   {note}")

    print()
    print("the inventory this pass uses")
    for cut in (v24_timeline.SPIN, v24_timeline.STOPPED,
                v24_timeline.ANTICIPATION, v24_timeline.ANTICIPATION_DEEP,
                v24_timeline.FALL, v24_timeline.FALL_DEEP,
                v24_timeline.TRAP, v24_timeline.TRAP_SHORT,
                v24_timeline.DRUM_FALSIFIED):
        print(f"    master {cut.first:4d}..{cut.last:<4d} "
              f"{cut.frames:3d} f  {cut.seconds:5.3f} s  "
              f"replay {master.replay_of[cut.first]:7.3f}.."
              f"{master.replay_of[cut.last]:<7.3f}  {cut.why}")


def _cost(master: Master, replay: dict[str, Any], first: int, second: int) -> dict[str, float]:
    near = screen_field(master, replay, first)
    far = screen_field(master, replay, second)
    both = [key for key in near if key in far]
    px = [math.dist(near[key][:2], far[key][:2]) for key in both]
    widths = [
        gap / (2.0 * 0.5 * (near[key][2] + far[key][2])) for gap, key in zip(px, both)
    ]
    return {
        "px_mean": sum(px) / len(px) if px else float("nan"),
        "px_max": max(px) if px else float("nan"),
        "widths_mean": sum(widths) / len(widths) if widths else float("nan"),
        "widths_max": max(widths) if widths else float("nan"),
        "camera": math.dist(master.poses[first][1:4], master.poses[second][1:4]),
    }


def _join_line(label: str, master: Master, replay: dict[str, Any],
               first: int, second: int) -> None:
    rows = _cost(master, replay, first, second)
    print(f"    {label:34s} {rows['px_mean']:7.1f} px mean  "
          f"{rows['px_max']:7.1f} worst  {rows['widths_mean']:5.2f} / "
          f"{rows['widths_max']:5.2f} marble widths  "
          f"camera steps {rows['camera']:6.3f}")


# --- report -----------------------------------------------------------------


def stage_report(replay: dict[str, Any], master: Master,
                 write: bool = True) -> dict[str, Any]:
    plans = {**CANDIDATES(master), **REJECTED(master)}
    rows: dict[str, Any] = {}
    base = master.frames + v24_timeline.HOLD_FRAMES
    print(f"the V22.1 picture with its preview removed: {base} frames, "
          f"{base / FPS:.3f} s")
    print()
    for key, plan in plans.items():
        row = report(master, replay, plan)
        rows[key] = row
        _print_candidate(row, plan, master)
        print()

    print("side by side")
    header = (f"{'':4s} {'runtime':>8s} {'frames':>7s} {'joins':>6s} "
              f"{'start->downhill':>16s} {'release':>8s} {'action':>7s} "
              f"{'winner':>7s} {'after':>7s} {'crossings':>10s} {'coverage':>9s}")
    print(header)
    for key, row in rows.items():
        print(f"{key:4s} {row['runtime']:8.3f} {row['frames']:7d} "
              f"{row['join_count']:6d} {row['start']['to_downhill'] or 0.0:16.3f} "
              f"{row['start']['to_release'] or 0.0:8.3f} "
              f"{row['start']['first_race_action'] or 0.0:7.3f} "
              f"{row['winner_output'] or 0.0:7.3f} {row['post_winner'] or 0.0:7.3f} "
              f"{row['crossings_shown']:6d} / 8 {row['coverage']['coverage']:9.3f}")

    if write:
        os.makedirs(DOC_DIR, exist_ok=True)
        path = os.path.join(DOC_DIR, "candidates.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({key: _plain(row) for key, row in rows.items()}, handle, indent=2)
        print()
        print(f"wrote {path}")
    return rows


def _print_candidate(row: dict[str, Any], plan: Plan, master: Master) -> None:
    print(f"=== {row['title']} ===")
    print(f"    {row['note']}")
    print(f"    runtime {row['runtime']:.3f} s, {row['frames']} frames "
          f"({row['hold']:.3f} s hold + {row['master_frames']} master frames)")
    cover = row["coverage"]
    print(f"    shows {cover['shown']:.3f} s of the replay it spans "
          f"({cover['replay_from']:.3f}-{cover['replay_to']:.3f}, "
          f"{cover['spanned']:.3f} s) = {cover['coverage'] * 100:.1f}% coverage")
    start = row["start"]
    print(f"    start: gates at {start['gates']:.3f}, release at "
          f"{start['to_release']:.3f}, downhill at {start['to_downhill']:.3f}, "
          f"first race action at {start['first_race_action']:.3f}")
    print(f"    winner crosses at {row['winner_output']:.3f}, "
          f"{row['post_winner']:.3f} s of film after it, "
          f"{row['crossings_shown']} of 8 crossings shown")
    print(f"    {row['join_count']} omissions:")
    for one in row["omissions"]:
        span = one["master_frames"]
        where = f"master {span[0]}..{span[1]}" if span else "never rendered"
        print(f"        {one['kind']:11s} replay {one['replay_from']:7.3f} -> "
              f"{one['replay_to']:7.3f}  {one['seconds']:6.3f} s  "
              f"{one['frames']:4d} f  ({where})")
    print("    joins, measured on the delivered frame:")
    for join in row["joins"]:
        print(f"        output {join.output:6.3f}  {join.window[0]}->{join.window[1]}"
              f"  {join.omitted_frames:3d} f  "
              f"field moves {join.world_mean:5.2f} wu = {join.px_mean:6.1f} px = "
              f"{join.widths_mean:4.2f} marble widths (worst {join.widths_max:4.2f})"
              f"  camera steps {join.camera_step:5.3f}  "
              f"blades {join.machine['phase_error_deg']:+6.2f} deg off")
    print("    shots:")
    for shot in row["sections"]:
        print(f"        {shot['name']:16s} {shot['output_from']:6.3f} - "
              f"{shot['output_to']:6.3f}   {shot['seconds']:6.3f} s")
    print("    approach / interaction / exit:")
    for seg in row["segments"]:
        mark = "" if seg["whole"] else "   <- INCOMPLETE"
        run_up = f"{seg['run_up']:.3f}" if seg["run_up"] is not None else "  -  "
        pay = f"{seg['pay_off']:.3f}" if seg["pay_off"] is not None else "  -  "
        print(f"        {seg['name']:10s} run-up {run_up:>7s} s   "
              f"pay-off {pay:>7s} s{mark}")
    if row["problems"]:
        print("    PROBLEMS:")
        for note in row["problems"]:
            print(f"        {note}")
    else:
        print("    no problems")


def _plain(row: dict[str, Any]) -> dict[str, Any]:
    """The report without the objects a JSON file cannot carry."""
    out = {key: value for key, value in row.items()
           if key not in ("clock", "joins", "keep")}
    out["keep"] = [list(pair) for pair in row["keep"]]
    out["joins"] = [
        {
            "output": join.output,
            "before_frame": join.before_frame,
            "after_frame": join.after_frame,
            "replay": list(join.replay),
            "omitted_frames": join.omitted_frames,
            "seconds": join.seconds,
            "world_mean": join.world_mean,
            "world_max": join.world_max,
            "px_mean": join.px_mean,
            "px_max": join.px_max,
            "widths_mean": join.widths_mean,
            "widths_max": join.widths_max,
            "camera_step": join.camera_step,
            "aim_step": join.aim_step,
            "fov_step": join.fov_step,
            "churn_before": join.churn_before,
            "phase_error_deg": join.machine["phase_error_deg"],
            "window": list(join.window),
            "problems": list(join.problems),
        }
        for join in row["joins"]
    ]
    return out


# --- clips ------------------------------------------------------------------


def _label_png(path: str, title: str, detail: str) -> str:
    """The proof label, drawn once and overlaid on every frame of a clip.

    Drawn rather than burned with `drawtext` so it does not depend on ffmpeg's
    font configuration, and through `overlays.load_font` so it is the same face
    the delivered marks use.
    """
    image = Image.new("RGBA", (WIDTH, 150), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, WIDTH, 150), fill=(18, 15, 13, 205))
    draw.text((36, 62), title, font=overlays.load_font(46),
              fill=(255, 205, 116, 255), anchor="ls")
    draw.text((36, 112), detail, font=overlays.load_font(28),
              fill=(255, 249, 238, 235), anchor="ls")
    image.save(path)
    return path


def _select(keep: Sequence[tuple[int, int]]) -> str:
    """The filter that keeps exactly these master frames, in order.

    `select` decides frame by frame on the master's own frame number, so a cut
    lands where the plan says it does; `setpts=N/FRAME_RATE/TB` closes the gap by
    renumbering what survives. Neither filter touches a frame's content and
    neither can reorder or repeat one.
    """
    spans = "+".join(f"between(n\\,{first}\\,{last})" for first, last in keep)
    return f"select='{spans}',setpts=N/FRAME_RATE/TB"


def stage_clip(replay: dict[str, Any], master: Master, seed: int,
               only: str | None = None) -> list[str]:
    ffmpeg = _ffmpeg()
    if not os.path.isfile(MASTER):
        raise PacingError(f"missing input: {MASTER}")
    os.makedirs(WORK_DIR, exist_ok=True)
    plans = CANDIDATES(master)
    written: list[str] = []

    # The control: the same picture with nothing but the preview removed, so a
    # reviewer can see what the candidates are shorter *than*.
    control = Plan(key="v221", title="V22.1, preview removed",
                   hold_frames=v24_timeline.HOLD_FRAMES, cuts=(),
                   tail=master.frames - 1,
                   note="the control")
    everything = {"v221": control, **plans, **REJECTED(master)}
    for key, plan in everything.items():
        if only and key != only:
            continue
        clock, keep = build(master, plan)
        detail = (f"{plan.key.upper()}  {clock.duration:.3f} s  "
                  f"{clock.frames} frames  {len(plan.cuts)} omissions  "
                  "V22.1 picture, V24 timeline")
        label = _label_png(os.path.join(WORK_DIR, f"label_{key}.png"),
                           LABEL, detail)
        video = os.path.join(WORK_DIR, f"v24_{key}_TIMING_PROOF_ONLY.mp4")
        chain = (
            f"[0:v]{_select(keep)},"
            f"tpad=start={plan.hold_frames}:start_mode=clone,"
            f"setpts=N/FRAME_RATE/TB[cut];"
            f"[cut][1:v]overlay=0:0:format=auto[out]"
        )
        _run([ffmpeg, "-v", "error", "-y", "-i", MASTER, "-i", label,
              "-filter_complex", chain, "-map", "[out]",
              "-frames:v", str(clock.frames),
              "-an", "-c:v", "libx264", "-preset", VIDEO_PRESET,
              "-crf", str(VIDEO_CRF), "-pix_fmt", "yuv420p",
              "-r", str(FPS), video],
             f"clip {key}")
        count = _frames(video)
        if count != clock.frames:
            raise PacingError(
                f"{video}: {count} frames, the clock says {clock.frames}"
            )
        print(f"    {key:5s} {video}  {count} frames  {count / FPS:.3f} s")
        written.append(video)
    return written


def stage_verify(replay: dict[str, Any], master: Master,
                 samples: int = 24) -> dict[str, Any]:
    """Does the clip show the frames the plan says? Checked against the master.

    A frame count only proves the clip is the right *length*. This proves it is
    the right *frames*: for a spread of output positions, the clip's frame is
    pulled and compared against the master frame the plan maps that position to,
    and against the two master frames either side of it.

    The comparison is on the picture below the label strip, in mean absolute
    grey, and the test is **which master frame it matches best** rather than an
    absolute threshold - both files are lossy re-encodes of the same render, so
    the residual is never zero and is not the interesting number. A clip that is
    a frame out matches its neighbour better, and that is what this catches.
    """
    import numpy as np
    from PIL import Image

    ffmpeg = _ffmpeg()
    plans = {**CANDIDATES(master), **REJECTED(master)}
    scratch = os.path.join(WORK_DIR, "verify")
    os.makedirs(scratch, exist_ok=True)
    results: dict[str, Any] = {}
    for key, plan in plans.items():
        clip = os.path.join(WORK_DIR, f"v24_{key}_TIMING_PROOF_ONLY.mp4")
        if not os.path.isfile(clip):
            raise PacingError(f"missing clip: {clip} - run --stage clip first")
        kept = kept_frames(master, plan)
        # Spread across the film, and always the frame each side of every join.
        positions = {
            int(round(index * (len(kept) - 1) / (samples - 1)))
            for index in range(samples)
        }
        for position, frame in enumerate(kept):
            if position and kept[position] != kept[position - 1] + 1:
                positions.update({position - 1, position})
        positions = sorted(one for one in positions if 0 <= one < len(kept))

        want = {plan.hold_frames + one for one in positions}
        _extract(ffmpeg, clip, want, os.path.join(scratch, f"clip_{key}"))
        _extract(ffmpeg, MASTER, {kept[one] for one in positions},
                 os.path.join(scratch, f"ref_{key}"))

        misses: list[str] = []
        for position in positions:
            mine = _grey(os.path.join(scratch, f"clip_{key}",
                                      "f_%06d.png" % (plan.hold_frames + position)))
            scores = {}
            for offset in (-1, 0, 1):
                neighbour = kept[position] + offset
                if not 0 <= neighbour < master.frames:
                    continue
                path = os.path.join(scratch, f"ref_{key}", "f_%06d.png" % neighbour)
                if not os.path.isfile(path):
                    _extract(ffmpeg, MASTER, {neighbour},
                             os.path.join(scratch, f"ref_{key}"))
                scores[offset] = float(np.mean(np.abs(mine - _grey(path))))
            best = min(scores, key=scores.get)
            if best != 0:
                misses.append(
                    f"output frame {plan.hold_frames + position} matches master "
                    f"{kept[position] + best} better than master {kept[position]} "
                    f"({scores})"
                )
        results[key] = {"checked": len(positions), "misses": misses}
        state = "every sampled frame is the one the plan names" if not misses \
            else f"{len(misses)} MISMATCHES"
        print(f"    {key:11s} {len(positions):3d} frames checked - {state}")
        for note in misses:
            print(f"        {note}")

    # The hold really is the first frame, repeated.
    for key, plan in plans.items():
        first = _grey(os.path.join(scratch, f"clip_{key}",
                                   "f_%06d.png" % plan.hold_frames))
        _extract(ffmpeg, os.path.join(WORK_DIR,
                                      f"v24_{key}_TIMING_PROOF_ONLY.mp4"),
                 {0}, os.path.join(scratch, f"hold_{key}"))
        held = _grey(os.path.join(scratch, f"hold_{key}", "f_%06d.png" % 0))
        import numpy as np
        gap = float(np.mean(np.abs(first - held)))
        print(f"    {key:11s} the hold is master frame 0, repeated "
              f"{plan.hold_frames} times (mean |dpix| to the first live frame "
              f"{gap:.3f})")
    return results


def _extract(ffmpeg: str, path: str, frames: set[int], into: str) -> None:
    os.makedirs(into, exist_ok=True)
    wanted = sorted(frames)
    if not wanted:
        return
    expr = "+".join(f"eq(n\\,{one})" for one in wanted)
    _run([ffmpeg, "-v", "error", "-y", "-i", path,
          "-vf", f"select='{expr}'", "-vsync", "0", "-frame_pts", "1",
          os.path.join(into, "f_%06d.png")], f"extract from {path}")


def _grey(path: str):
    import numpy as np
    from PIL import Image
    # Below the label strip, which the clip has and the master does not.
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)[150:, :]


def _frames(path: str) -> int:
    found = shutil.which("ffprobe")
    if found is None:
        raise PacingError("ffprobe is not on PATH")
    done = subprocess.run(
        [found, "-v", "error", "-select_streams", "v:0", "-count_frames",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        raise PacingError(f"ffprobe failed on {path}")
    return int(done.stdout.strip().splitlines()[0])


# --- entry ------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument("--stage", default="report",
                        choices=("machine", "survey", "report", "clip",
                                 "verify", "all"))
    parser.add_argument("--candidate", default=None,
                        help="clip one candidate only")
    args = parser.parse_args(argv)

    replay, _track, master = _load(args.seed)
    print(f"master: {master.frames} frames, {master.frames / FPS:.3f} s, "
          f"{len(master.segments)} windows, no preview")
    print()

    if args.stage in ("machine", "all"):
        stage_machine(replay)
        print()
    if args.stage in ("survey", "all"):
        stage_survey(replay, master)
        print()
    if args.stage in ("report", "all"):
        stage_report(replay, master)
        print()
    if args.stage in ("clip", "all"):
        print("proof clips")
        stage_clip(replay, master, args.seed, args.candidate)
        print()
    if args.stage in ("verify", "all"):
        print("verifying the clips against the master")
        stage_verify(replay, master)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PacingError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
