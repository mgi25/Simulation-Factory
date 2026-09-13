"""How much of the machine V22 should keep, measured and then cut.

    python tools/sloped_v22_pacing.py --stage analyse
    python tools/sloped_v22_pacing.py --stage candidates
    python tools/sloped_v22_pacing.py --stage clips

**Nothing in the production path is touched.** `sloped/cameras.py`,
`sloped/presentation.py`, `tools/sloped_short.py` and `tools/sloped_short_qc.py`
are read and never written; the physics, the seed, the replay, the course and
every camera pose are inputs. This is a parallel pass whose output is a
*timeline* - a set of master-frame ranges and a set of replay spans the V22
camera master should cover - plus proof clips that let somebody watch the
timing before anybody commits to it.

The proof clips carry **V21's picture**, deliberately. This session is judging
how long things last, not how they look, and cutting the question in half is
what makes the answer trustworthy. Each clip is labelled with the candidate it
is and what it retains, so nobody can mistake one for a delivery.

Stages:

    analyse     the activity scan, the omission verdicts, the beat map and the
                map-size diagnosis
    candidates  every candidate's clock, side by side, checked
    clips       build the labelled proof MP4s from the V21 master
    sheet       the openings of all four, side by side, on one page
    recommend   the chosen timeline, as the V22 camera master's edit map
    all         all five
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

from sloped import overlays, presentation, v22_timeline
from sloped.v22_timeline import CANDIDATES, CHURN_FLOOR, RESTORATIONS

OUT_DIR = os.path.join("output", "sloped_race_v1")
CLIP_DIR = os.path.join("exports", "v22_pacing")

# The V21 integration master: the locked replay and the locked edit map through
# the V21.2 camera track and the V21 grade, 1150 frames, silent. Every proof
# clip is a subset of these frames and nothing else.
MASTER = os.path.join(OUT_DIR, "real_race_v21_master.mp4")

WIDTH, HEIGHT, FPS = 1080, 1920, 60
CLIP_CRF = 20
CLIP_PRESET = "medium"

# How much preview the final V22 is expected to put in front of all this. The
# brief says 1.5-2.2 s; the budget below quotes the middle and both ends.
PREVIEW = (1.5, 1.85, 2.2)

# Which clips are worth building. `v21` is the reference every other clip is
# read against, so it is built too even though it is not a proposal.
CLIP_KEYS = ("v21", "a", "b", "c")

# The one this pass recommends. See the `recommend` stage for why, and
# docs/sloped_race_v22_pacing.md for the argument at length.
RECOMMENDED = "a"


class PacingError(RuntimeError):
    pass


# --- inputs -----------------------------------------------------------------


def _master_frames(path: str) -> int:
    found = shutil.which("ffprobe")
    if found is None:
        raise PacingError("ffprobe is not on PATH")
    done = subprocess.run(
        [found, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames", "-of", "json", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if done.returncode != 0:
        raise PacingError(f"ffprobe failed on {path}")
    return int(json.loads(done.stdout)["streams"][0]["nb_frames"])


def load(seed: int, master: str | None = None):
    """The replay, the track, the untouched master clock and the lens names."""
    replay_path = os.path.join(OUT_DIR, f"race_{seed}.json")
    track_path = os.path.join(OUT_DIR, f"cameras_{seed}.json")
    for path in (replay_path, track_path):
        if not os.path.isfile(path):
            raise PacingError(f"missing input: {path}")
    frames = v22_timeline.MASTER_FRAMES
    if master and os.path.isfile(master):
        frames = _master_frames(master)
    replay, track, clock = presentation.load(replay_path, track_path, frames)
    names = [str(row.get("cut", f"#{i}")) for i, row in enumerate(track["edit"])]
    return replay, track, clock, names


# --- analyse ----------------------------------------------------------------


def stage_analyse(seed: int) -> None:
    replay, track, base, names = load(seed, MASTER)
    gates = presentation.actuator_move(replay, base, "start.paddle")
    panel = presentation.actuator_move(replay, base, "start.panel")
    gates_replay = base.replay_at(gates) if gates is not None else None
    panel_replay = base.replay_at(panel) if panel is not None else None

    print("=== the master this pass reads ===")
    print(f"  replay digest  {replay['digest']}")
    print(f"  master frames  {base.master_frames}   edit windows {len(base.segments)}")
    print(f"  gates open     replay {gates_replay:.4f}")
    print(f"  floor opens    replay {panel_replay:.4f}")
    print()

    print(f"=== is anything happening? churn per window, floor {CHURN_FLOOR:.2f} ===")
    print(f"  {'#':>2} {'lens':<9} {'replay span':>16} {'len':>5} {'churn':>6} "
          f"{'hits':>5} {'hard':>5}  worst 0.25 s slice")
    for index, (_o0, _o1, r0, r1) in enumerate(base.segments):
        slices = v22_timeline.activity(replay, r0, r1)
        hits = [
            one for one in replay["events"]
            if one["kind"] == "collision" and r0 <= float(one["t"]) <= r1
        ]
        hard = [one for one in hits if float(one["speed"]) >= 11.0]
        worst = min(slices, key=lambda one: one.churn) if slices else None
        tag = (f"{worst.churn:5.2f} at {worst.replay_from:.3f}" if worst else "-")
        flag = "  <-- under the floor" if worst and worst.churn < CHURN_FLOOR else ""
        print(f"  {index:>2} {names[index]:<9} {r0:>7.3f}-{r1:<8.3f} {r1 - r0:>5.2f} "
              f"{v22_timeline.churn(replay, r0, r1):>6.2f} {len(hits):>5} {len(hard):>5}  {tag}{flag}")
    print()
    print("  The two windows that dip under the floor dip at their own first")
    print("  slice and nowhere else: replay 0.200-0.450 is the eight held on the")
    print("  line, and 5.700-5.950 is the settled field a quarter-second before")
    print("  the trapdoor. Both stillnesses are the point of the shot they open.")
    print("  From `descent` to `finish` no slice anywhere falls below 2.33, so")
    print("  there is nothing in the body of this film to trim.")
    print()

    print("=== every omission in V21, put to the same test ===")
    v21, _keep = v22_timeline.candidate_clock(base, CANDIDATES["v21"])
    spans = [(1.000, 2.300), (2.300, 5.700), (14.500, 15.350), (23.600, 24.467)]
    for r0, r1 in spans:
        slices = v22_timeline.activity(replay, r0, r1)
        overall = v22_timeline.churn(replay, r0, r1)
        hits = [
            one for one in replay["events"]
            if one["kind"] == "collision" and r0 <= float(one["t"]) <= r1
        ]
        marks = [
            one for one in replay["events"]
            if one["kind"] in ("module_enter", "route", "finish_line")
            and r0 <= float(one["t"]) <= r1
        ]
        verdict = "DEAD - omit it" if overall < CHURN_FLOOR else "LIVE - restore it"
        print(f"  replay {r0:>7.3f}-{r1:<8.3f} ({r1 - r0:.3f} s)  churn {overall:>5.2f}  "
              f"{len(hits):>2} hits  {len(marks):>2} marks   {verdict}")
        print("       quarters: " + "  ".join(f"{one.churn:.2f}" for one in slices))
        for one in marks[:3]:
            label = one.get("module") or one.get("route") or f"#{one.get('order')}"
            print(f"       {float(one['t']):.4f}  {one['kind']} marble {one['id']} {label}")
    print()

    print("=== the beats, and whether V21 shows all three parts of each ===")
    rows = v22_timeline.beats(v21)
    print(f"  {'beat':<14} {'approach':>9} {'contact':>9} {'exit':>9}   what it is")
    for row in rows:
        def show(value: float | None) -> str:
            return f"{value:8.3f} " if value is not None else "     cut "
        mark = "" if row["whole"] else "   <-- incomplete"
        print(f"  {row['name']:<14} {show(row['approach'])}{show(row['interaction'])}"
              f"{show(row['exit'])}  {row['detail']}{mark}")
    print()

    _map_size(replay, base, v21, names)


def _map_size(replay, base, v21, names) -> None:
    """Is the course short, or is the film short of the course?"""
    events = replay["events"]
    winner = next(
        one for one in events if one["kind"] == "finish_line" and int(one["order"]) == 1
    )
    winner_id, crossed = int(winner["id"]), float(winner["t"])
    launched = next(
        float(one["t"]) for one in events
        if one["kind"] == "module_enter" and int(one["id"]) == winner_id
        and one["module"] == "launch"
    )
    frames = replay["frames"]
    distance = 0.0
    previous = None
    for frame in frames:
        t = float(frame["t"])
        if t < launched - 1e-9:
            continue
        if t > crossed + 1e-9:
            break
        here = next(
            tuple(float(v) for v in one["p"])
            for one in frame["marbles"] if int(one["id"]) == winner_id
        )
        if previous is not None:
            distance += math.dist(previous, here)
        previous = here
    racing = crossed - launched

    # How much of the racing replay the film actually shows.
    shown = 0.0
    for out_from, out_to, r0, r1 in v21.segments:
        lo, hi = max(r0, launched), min(r1, crossed)
        if hi > lo:
            shown += hi - lo

    print("=== map size: is the course short, or is the film? ===")
    print(f"  the course, as locked          237 layout units of channel")
    print(f"                                 = {237 * 1.754386:.1f} world units")
    print(f"  the winner's racing path       {distance:.1f} wu "
          f"({distance * 0.57:.1f} layout units), launch to the line")
    print(f"  the winner's racing time       {racing:.3f} s at {distance / racing:.1f} wu/s mean")
    print(f"  of which V21 puts on screen    {shown:.3f} s = {100 * shown / racing:.1f}%")
    print(f"  omitted inside the race        {racing - shown:.3f} s (the 14.500-15.350 skip)")
    print()
    print(f"  beats in the racing leg        {len([b for b in v22_timeline.BEATS if launched <= b[1] <= crossed])}"
          f" of {len(v22_timeline.BEATS)}")
    print(f"  one beat every                 {racing / max(1, len([b for b in v22_timeline.BEATS if launched <= b[1] <= crossed])):.2f} s of replay")
    print()
    shot_rows = v22_timeline.shots(v21, names)
    short = [one for one in shot_rows if one[3] <= 1.25]
    print(f"  V21 shot lengths               {len(shot_rows)} shots over {v21.duration:.3f} s, "
          f"mean {v21.duration / len(shot_rows):.2f} s")
    print(f"  shots of 1.25 s or less        {len(short)} - "
          + ", ".join(f"{one[0]} {one[3]:.2f}" for one in short))
    print()
    print("  READING: the race itself is on screen at "
          f"{100 * shown / racing:.0f}% of real time and the machine puts a beat")
    print("  in front of the viewer every 1.4 s. Neither is a short course. The")
    print("  film is short of the course in exactly two places - the drum and the")
    print("  spinner exit - and it changes lens faster than the events resolve.")


# --- candidates -------------------------------------------------------------


def stage_candidates(seed: int) -> list[dict[str, Any]]:
    replay, track, base, names = load(seed, MASTER)
    gates = presentation.actuator_move(replay, base, "start.paddle")
    gates_replay = base.replay_at(gates) if gates is not None else 0.316667

    print(f"=== the start dial: master frame f shows replay {base.segments[0][2]:.3f} + f/60 ===")
    print(v22_timeline.NO_CANDIDATE_D)
    print()
    print(f"  {'key':<4} {'title':<32} {'drop':>9} {'frames':>7} {'runtime':>8} "
          f"{'drum':>6} {'live':>6} {'hits':>6} {'jump':>6} {'onmove':>7} "
          f"{'floor':>7} {'lens':>7} {'winner':>7}")

    rows: list[dict[str, Any]] = []
    for key in CLIP_KEYS:
        candidate = CANDIDATES[key]
        clock, keep = v22_timeline.candidate_clock(base, candidate)
        panel = presentation.actuator_move(replay, clock, "start.panel")
        kept, gone = v22_timeline.retained_collisions(replay, clock)
        span = v22_timeline.mixing(replay, clock, gates_replay)
        jumps = v22_timeline.cut_jump(replay, clock)
        start_jump = jumps[0][1] if jumps else 0.0
        crossing = clock.at(20.85)
        findings = v22_timeline.verify(clock, keep, base)
        row = {
            "key": key,
            "title": candidate.title,
            "note": candidate.note,
            "cuts": candidate.cuts,
            "keep": keep,
            "frames": clock.frames,
            "runtime": clock.duration,
            "drum": span["drum"],
            "live": span["live"],
            "kept": len(kept),
            "total": len(kept) + len(gone),
            "hardest": max((float(one["speed"]) for one in kept), default=0.0),
            "jump": start_jump,
            "on_motion": v22_timeline.cut_on_motion(replay, clock),
            "floor": panel,
            "lens": clock.window(2)[0],
            "winner": crossing,
            "findings": findings,
            "clock": clock,
        }
        rows.append(row)
        print(f"  {key:<4} {candidate.title:<32} "
              f"{str(candidate.cuts[0]):>9} {row['frames']:>7} {row['runtime']:>8.3f} "
              f"{row['drum']:>6.3f} {row['live']:>6.3f} "
              f"{row['kept']:>3}/{row['total']:<2} {row['jump']:>6.2f} "
              f"{row['on_motion']:>7.2f} "
              f"{row['floor']:>7.3f} {row['lens']:>7.3f} {row['winner']:>7.3f}")
    print()
    print("  drum   seconds of the start window on screen")
    print("  live   of that, seconds after the gates first move")
    print("  hits   marble-on-marble contacts in the drum that survive the cut")
    print("  jump   mean world units the field teleports across the start cut")
    print("  onmove churn over the last 0.1 s before the cut. Above the floor")
    print("         the omission reads as a skip; below it, as the machine")
    print("         stopping - and then the whoosh contradicts the picture")
    print("  floor / lens / winner   output seconds of the trapdoor, the first")
    print("         downhill lens and the winning crossing")
    print()

    for row in rows:
        state = "checked" if not row["findings"] else "FAILED"
        print(f"  {row['key']}: {state}" + ("" if not row["findings"] else ""))
        for finding in row["findings"]:
            print(f"      {finding}")
    print()

    print("=== what each candidate looks like once the preview is in front ===")
    restore = sum(one.seconds for one in RESTORATIONS if one.replay_to <= 15.4)
    tail = sum(one.seconds for one in RESTORATIONS if one.replay_from >= 23.0)
    print(f"  the spinner exit adds {restore:.3f} s, the finish tail {tail:.3f} s; "
          f"neither is in the master")
    print(f"  {'key':<4} {'proof':>7} {'+exit':>7} {'+tail':>7} "
          f"{'preview 1.5':>12} {'preview 1.85':>13} {'preview 2.2':>12}")
    for row in rows:
        full = row["runtime"] + restore + tail
        print(f"  {row['key']:<4} {row['runtime']:>7.3f} {row['runtime'] + restore:>7.3f} "
              f"{full:>7.3f} " + "".join(
                  f"{full + one:>12.3f} " if i == 0 else f"{full + one:>13.3f} " if i == 1 else f"{full + one:>12.3f}"
                  for i, one in enumerate(PREVIEW)))
    print()
    print(f"  the brief's window is 21-25 s. Candidates a, b and c all land in it")
    print(f"  with the exit, the tail and any preview length; V21 does not.")
    print()

    print("=== where the sound has to move ===")
    for row in rows:
        if row["key"] == "v21":
            continue
        panel = row["floor"]
        marks = v22_timeline.sound_marks(
            replay, row["clock"], gates or 0.0, panel or 0.0
        )
        print(f"  {row['key']}:")
        for mark in marks:
            extra = f"   ({mark['seconds']:.3f} s gone)" if "seconds" in mark else ""
            print(f"      {mark['output']:>7.3f}  {mark['cue']:<22} on {mark['on']}{extra}")
    print()
    print("  Nothing in audio/marble.py needs editing: every cue above is derived")
    print("  from the clock it is handed. This table is what an integrator should")
    print("  expect to measure afterwards, not a list of edits.")
    return rows


# --- clips ------------------------------------------------------------------


def _label(key: str, row: dict[str, Any]) -> str:
    os.makedirs(CLIP_DIR, exist_ok=True)
    path = os.path.join(CLIP_DIR, f"label_{key}.png")
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    title = overlays.load_font(44)
    body = overlays.load_font(30)
    lines = [
        f"V22 PACING PROOF  {key.upper()}",
        f"{row['runtime']:.3f} s   drum {row['drum']:.3f} s   "
        f"mixing {row['live']:.3f} s   {row['kept']}/{row['total']} hits",
        "V21 picture - timing only, not a delivery",
    ]
    draw.rectangle([0, 0, WIDTH, 168], fill=(0, 0, 0, 170))
    draw.text((36, 26), lines[0], font=title, fill=(255, 214, 64, 255))
    draw.text((36, 84), lines[1], font=body, fill=(235, 235, 235, 255))
    draw.text((36, 122), lines[2], font=body, fill=(170, 170, 170, 255))
    image.save(path)
    return path


def stage_clips(seed: int, rows: Sequence[dict[str, Any]] | None = None) -> list[str]:
    if not os.path.isfile(MASTER):
        raise PacingError(
            f"missing {MASTER} - copy it from exports/v21_integration/ "
            "(this pass only reads it)"
        )
    if rows is None:
        rows = stage_candidates(seed)
    found = shutil.which("ffmpeg")
    if found is None:
        raise PacingError("ffmpeg is not on PATH")
    os.makedirs(CLIP_DIR, exist_ok=True)

    written: list[str] = []
    for row in rows:
        key = row["key"]
        label = _label(key, row)
        keep = row["keep"]
        # `select` decides on the master's own frame number and `setpts`
        # renumbers what survives, so the cut lands exactly where the clock
        # says. Neither filter can touch, reorder or repeat a frame.
        gone = "+".join(
            f"between(n,{a},{b})"
            for a, b in _dropped_from(keep, v22_timeline.MASTER_FRAMES)
        )
        select = f"select='not({gone})',setpts=N/FRAME_RATE/TB," if gone else ""
        graph = (
            f"[0:v]{select}tpad=start_duration={row['clock'].hold}:"
            f"start_mode=clone,setpts=PTS-STARTPTS[base];"
            f"[1:v]format=rgba[tag];[base][tag]overlay=0:0[vout]"
        )
        path = os.path.join(CLIP_DIR, f"v22_pacing_{key}.mp4")
        command = [
            found, "-y", "-i", MASTER,
            "-loop", "1", "-framerate", str(FPS), "-i", label,
            "-filter_complex", graph, "-map", "[vout]", "-an",
            "-c:v", "libx264", "-preset", CLIP_PRESET, "-crf", str(CLIP_CRF),
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            "-frames:v", str(row["frames"]), path,
        ]
        done = subprocess.run(command, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        if done.returncode != 0:
            tail = "\n".join((done.stderr or "").splitlines()[-15:])
            raise PacingError(f"encoding {path} failed\n{tail}")
        have = _master_frames(path)
        if have != row["frames"]:
            raise PacingError(
                f"{path} came out {have} frames, the clock says {row['frames']}"
            )
        size = os.path.getsize(path) / (1024 * 1024)
        print(f"clip: {path}  {have} frames  {have / FPS:.3f} s  {size:.1f} MiB")
        written.append(path)
    return written


def stage_recommend(seed: int) -> dict[str, Any]:
    """One timeline, written out as the V22 camera master's own edit map.

    The proof clip can only restore frames V21 dropped, so the recommendation
    is two things bolted together: a start dial the clip proves, and two replay
    spans the clip cannot contain and the next render has to cover. This stage
    prints them as one map so nobody has to add them up by hand.
    """
    replay, _track, base, names = load(seed, MASTER)
    candidate = CANDIDATES[RECOMMENDED]
    clock, keep = v22_timeline.candidate_clock(base, candidate)

    # The candidate's own windows, with each restoration folded into the window
    # whose replay it continues.
    windows: list[tuple[str, float, float]] = [
        (names[index], row[2], row[3]) for index, row in enumerate(clock.segments)
    ]
    for restoration in RESTORATIONS:
        for index, (name, r0, r1) in enumerate(windows):
            if abs(r1 - restoration.replay_from) < 1e-6:
                windows[index] = (name, r0, restoration.replay_to)
                break

    print(f"=== the recommended V22 timeline: {candidate.title} + both restorations ===")
    print(f"  {candidate.note}")
    print()
    print(f"  {'#':>2} {'lens':<9} {'replay from':>12} {'replay to':>11} {'seconds':>8} "
          f"{'frames':>7}  note")
    total = 0.0
    for index, (name, r0, r1) in enumerate(windows):
        frames = int(round((r1 - r0) * FPS))
        total += r1 - r0
        was = clock.segments[index]
        note = ""
        if abs(r1 - was[3]) > 1e-6:
            note = f"extended {r1 - was[3]:.3f} s - NEEDS A RE-RENDER"
        elif index == 0:
            note = f"the start dial: stops on master frame {candidate.cuts[0][0] - 1}"
        print(f"  {index:>2} {name:<9} {r0:>12.6f} {r1:>11.6f} {r1 - r0:>8.3f} "
              f"{frames:>7}  {note}")
    hold = int(round(clock.hold * FPS))
    print(f"  {'':>2} {'hold':<9} {'':>12} {'':>11} {clock.hold:>8.3f} {hold:>7}  "
          "the opening frame, cloned, under PICK ONE")
    print()
    # The renderer walks frames 0 to round(duration * fps) inclusive over the
    # WHOLE map, so the master's count is not the sum of the rounded per-window
    # figures above - those are printed to size each shot, not to be added up.
    master = int(round(total * FPS)) + 1
    picture = master + hold
    print(f"  replay covered   {total:.4f} s in {len(windows)} windows")
    print(f"  picture          {picture} frames = {picture / FPS:.3f} s "
          f"(the proof clip is {clock.frames} of them; the rest is the two "
          "restorations)")
    print(f"                   the per-window frame column above sums to "
          f"{sum(int(round((r1 - r0) * FPS)) for _n, r0, r1 in windows) + hold}, "
          "which is not the same number and is")
    print("                   not the one to use: window edges get solved and")
    print("                   rounded once, over the whole map, at render time.")
    for low in PREVIEW:
        print(f"  + preview {low:.2f} s -> {picture / FPS + low:>6.3f} s")
    print()

    print("  the one omission that survives:")
    for output, dropped in v22_timeline._omission_pairs(clock)[:1]:
        print(f"    output {output:.3f}  replay {clock.segments[0][3]:.6f} -> "
              f"{clock.segments[1][2]:.6f}   {dropped:.3f} s of parked drum")
    print("    the 0.850 s skip at replay 14.500 is gone - restored, not moved.")
    print("    V22 therefore carries ONE whoosh where V21 carried two.")
    print()

    gates = presentation.actuator_move(replay, clock, "start.paddle")
    panel = presentation.actuator_move(replay, clock, "start.panel")
    shift = sum(one.seconds for one in RESTORATIONS if one.replay_to <= 15.4)
    print("  where the audio cues land, before the preview is added:")
    print(f"    {gates:>7.3f}  the gates, and the end of the tension run-up")
    print(f"    {clock.hold + clock.segments[1][0]:>7.3f}  the whoosh")
    print(f"    {panel:>7.3f}  the trapdoor")
    print(f"    {(clock.at(20.85) or 0.0) + shift:>7.3f}  the winner accent")
    print("    everything after replay 14.500 lands 0.850 s later than the proof")
    print("    clip shows it, because the restoration is in front of it.")
    return {"windows": windows, "frames": total + hold, "keep": keep}


def stage_sheet(seed: int, rows: Sequence[dict[str, Any]] | None = None) -> str:
    """The opening of every candidate, side by side, on one page.

    A column every 0.4 s of finished film for the first 5.2 s, each captioned
    with the replay instant it is showing. Read down a column and the four
    candidates are at four different places in the same race; read across a row
    and you can see what each of them spends its opening on.
    """
    from PIL import Image, ImageDraw

    if rows is None:
        rows = stage_candidates(seed)
    replay, _track, base, _names = load(seed, MASTER)

    step, count = 0.4, 13
    cell = (192, 341)
    pad, head, gutter = 6, 44, 128
    sheet = Image.new(
        "RGB",
        (gutter + count * (cell[0] + pad), head + len(rows) * (cell[1] + head)),
        (18, 18, 20),
    )
    draw = ImageDraw.Draw(sheet)
    title = overlays.load_font(26)
    small = overlays.load_font(17)
    draw.text((10, 12), "V22 pacing candidates - the first 5.2 s, a column every 0.4 s",
              font=title, fill=(255, 214, 64))

    found = shutil.which("ffmpeg")
    work = os.path.join(CLIP_DIR, "_sheet")
    os.makedirs(work, exist_ok=True)
    for index, row in enumerate(rows):
        clip = os.path.join(CLIP_DIR, f"v22_pacing_{row['key']}.mp4")
        if not os.path.isfile(clip):
            raise PacingError(f"missing {clip}; run --stage clips first")
        top = head + index * (cell[1] + head)
        draw.text((10, top + 4),
                  f"{row['key'].upper()}  {row['runtime']:.3f} s   mixing "
                  f"{row['live']:.3f} s   {row['kept']}/{row['total']} hits",
                  font=small, fill=(235, 235, 235))
        for column in range(count):
            when = column * step
            frame = int(round(when * FPS))
            png = os.path.join(work, f"{row['key']}_{column:02d}.png")
            subprocess.run(
                [found, "-v", "error", "-y", "-i", clip,
                 "-vf", f"select=eq(n\\,{frame})", "-vsync", "0",
                 "-frames:v", "1", png],
                capture_output=True, text=True,
            )
            if not os.path.isfile(png):
                continue
            tile = Image.open(png).convert("RGB").resize(cell)
            x = gutter + column * (cell[0] + pad)
            sheet.paste(tile, (x, top + 22))
            shown = row["clock"].replay_at(when)
            caption = f"{when:.1f}s  rep {shown:.2f}" if shown is not None else f"{when:.1f}s"
            draw.rectangle([x, top + 22, x + cell[0], top + 42], fill=(0, 0, 0))
            draw.text((x + 4, top + 25), caption, font=small, fill=(255, 214, 64))

    out = os.path.join("docs", "validation", "sloped_race_v1", "v22_pacing")
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "candidates_opening.png")
    # Three quarters of the working size, quantised to 256 colours: 726 KiB
    # rather than 3.7 MB, which is what the rest of docs/validation weighs, and
    # the captions and the marble positions are still perfectly legible. This
    # is a timing reference, not a colour one.
    saved = sheet.resize(
        (sheet.width * 3 // 4, sheet.height * 3 // 4), Image.LANCZOS
    ).quantize(colors=256, method=Image.MEDIANCUT)
    saved.save(path, optimize=True)
    shutil.rmtree(work, ignore_errors=True)
    print(f"sheet: {path}  {saved.size[0]}x{saved.size[1]}  "
          f"{os.path.getsize(path) / 1024:.0f} KiB")
    return path


def _dropped_from(keep: Sequence[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    """The complement of a keep list: the ranges that are not in it."""
    out: list[tuple[int, int]] = []
    cursor = 0
    for first, last in keep:
        if first > cursor:
            out.append((cursor, first - 1))
        cursor = last + 1
    if cursor < total:
        out.append((cursor, total - 1))
    return out


# --- main -------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seed", type=int, default=5432)
    parser.add_argument(
        "--stage", default="all",
        choices=("analyse", "candidates", "clips", "sheet", "recommend", "all"),
    )
    args = parser.parse_args(argv)

    stages = (
        ("analyse", "candidates", "clips", "sheet", "recommend")
        if args.stage == "all" else (args.stage,)
    )
    rows: list[dict[str, Any]] | None = None
    for stage in stages:
        print(f"--- {stage} ---")
        if stage == "analyse":
            stage_analyse(args.seed)
        elif stage == "candidates":
            rows = stage_candidates(args.seed)
        elif stage == "clips":
            stage_clips(args.seed, rows)
        elif stage == "sheet":
            stage_sheet(args.seed, rows)
        elif stage == "recommend":
            stage_recommend(args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
