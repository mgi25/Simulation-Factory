"""V32: the Race #2 production Short, and the locks that make it a finish pass.

Four groups.

**The locks, as a diff.** V32 develops no system. The strongest statement of
that is not a property of any module - it is that the branch touches nothing
that defines physics, camera, environment or track.
`test_the_branch_adds_only_presentation` asserts the whole set of changed files
by name, so a line added to `race2/race.py` or to a light in
`contained_bay_v301.json` fails here rather than in a review.

**The clock.** Race #2's film has one segment of slope one, which is what makes
"zero temporal omissions" something the type system enforces rather than
something a report claims. The frame count, the runtime and the sample count all
follow from it and are pinned.

**The marks.** PICK A COLOR on frame zero and gone before the first cut; the
ring on the actual winner, opening on the crossing, blocked on no frame; the
card naming the colour the renderer actually paints, carrying a rank two
instruments agree on.

**The comeback, adversarially.** `test_the_six_place_claim_is_false` exists
because the shipped V31 preview makes it. It asserts the rejection rather than
only the answer.

Tests that need the rendered master or the delivered files skip without them,
the same way the rendered tests elsewhere in this repository skip without
`$GODOT_BIN`.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from race2 import presentation as pres  # noqa: E402
from sloped import overlays, v24_payoff  # noqa: E402

BASE = "fa39d7a794444ee761b499a3f855f452517b4369"
SEED = 8
COURSE = "switchyard"
WINNER = 7
WINNER_LABEL = "PINK"
CROSSING = 15.816667
FRAMES = 1150
RUNTIME = FRAMES / 60.0
COMEBACK = 5

ROOT = pathlib.Path(REPO)
DOCS = ROOT / "docs" / "validation" / "race2" / "v32_final"
EXPORT = ROOT / "exports" / "race2_v32_final"
MASTER_DIR = (ROOT / "output" / "race2" / "v32_final" / "frames" / "master"
              / f"clip_{COURSE}_{SEED}")
REPLAY = ROOT / "output" / "race2" / f"race2_{COURSE}_{SEED}.replay.json"
TRACK = (ROOT / "output" / "race2" / "v31_readability" / "RB"
         / f"race2_{COURSE}_{SEED}.cameras.json")

# Everything this branch is allowed to touch. Presentation, its tool, its tests
# and its documents - and nothing that any earlier pass locked.
ALLOWED = {
    "race2/presentation.py",
    "tools/race2_v32_short.py",
    "tests/test_race2_v32_final.py",
    "docs/race2_v32_production.md",
}
# The one directory of new evidence this pass writes. Everything under it is
# measurement output, never code.
ALLOWED_PREFIX = "docs/validation/race2/v32_final/"
# The packages and files the brief locks outright, checked one at a time so a
# failure names the layer rather than the diff.
LOCKED = (
    "race2/race.py", "race2/course.py", "race2/courses.py", "race2/parts.py",
    "race2/kit.py", "race2/start.py", "race2/track.py", "race2/spine.py",
    "race2/rig.py", "race2/cinematography.py", "race2/shots.py",
    "race2/flow.py", "race2/readability.py", "race2/events.py",
    "godot/scripts/race2_scene.gd", "godot/scripts/race2_render.gd",
    "godot/assets/marble_machine/course/race2_track_surface.gd",
    "godot/assets/marble_machine/environment/profiles/contained_bay_v301.json",
    "godot/assets/marble_machine/lab_palette.gd",
    "godot/assets/marble_machine/racers/racer_visual.gd",
    "sloped/overlays.py", "sloped/v24_payoff.py", "sloped/v24_hook.py",
    "sloped/presentation.py", "audio/marble.py",
)


def _git(*args):
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                          text=True, encoding="utf-8")


def _evidence():
    path = DOCS / "evidence.json"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py evidence` first")
    return json.loads(path.read_text(encoding="utf-8"))


def _film():
    if not (REPLAY.is_file() and TRACK.is_file()):
        pytest.skip("the replay and RB camera track have not been built")
    return pres.load_film(str(REPLAY), str(TRACK), master_frames=FRAMES)


# --- the locks --------------------------------------------------------------


def test_the_branch_adds_only_presentation():
    """The whole diff against the base commit, by name.

    **Tracked changes and untracked additions both.** `git diff --name-only`
    only sees files git already knows about, so before this pass is committed
    every file it adds is invisible to it - the check would pass on an empty
    set and say nothing. `git status --porcelain -uall` is the other half, and
    respects `.gitignore`, so rendered frames and exports stay out of it.
    """
    result = _git("diff", "--name-only", BASE)
    if result.returncode != 0:
        pytest.skip(f"{BASE} is not in this clone")
    changed = {line.strip().replace("\\", "/")
               for line in result.stdout.splitlines() if line.strip()}
    status = _git("status", "--porcelain", "-uall")
    changed |= {
        line[3:].strip().strip('"').replace("\\", "/")
        for line in status.stdout.splitlines() if line.strip()
    }
    unexpected = {
        path for path in changed
        if path not in ALLOWED and not path.startswith(ALLOWED_PREFIX)
    }
    assert not unexpected, (
        "V32 is a presentation pass and these files are not presentation:\n  "
        + "\n  ".join(sorted(unexpected)))
    assert "race2/presentation.py" in changed, (
        "this test must be able to see the files this pass adds")


@pytest.mark.parametrize("path", LOCKED)
def test_no_locked_file_moved(path):
    result = _git("diff", "--name-only", BASE, "--", path)
    if result.returncode != 0:
        pytest.skip(f"{BASE} is not in this clone")
    assert not result.stdout.strip(), f"{path} is locked by the V32 brief"


def test_the_locks_report_passes():
    path = DOCS / "locks.json"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py locks` first")
    report = json.loads(path.read_text(encoding="utf-8"))
    assert report["base_commit"] == BASE
    for layer, block in report["layers"].items():
        moved = [row["path"] for row in block["files"] if row.get("unchanged") is False]
        assert not moved, f"{layer} moved: {moved}"
    for layer, block in report["reproduced"].items():
        assert block["identical"], (
            f"{layer}: {block['report']} does not regenerate identically; "
            f"{block['fields_differing']}")
    assert report["ok"]


def test_the_replay_is_the_hero_seed():
    if not REPLAY.is_file():
        pytest.skip("the replay has not been built")
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    assert int(replay["seed"]) == SEED
    assert replay["digest"] and replay["event_digest"]


# --- the clock --------------------------------------------------------------


def test_the_clock_is_one_segment_of_slope_one():
    """Zero temporal omissions, by construction rather than by assertion."""
    clock = pres.film_clock({"duration": 19.15, "fps": 60})
    assert len(clock.segments) == 1
    out_from, out_to, replay_from, replay_to = clock.segments[0]
    assert (out_to - out_from) == pytest.approx(replay_to - replay_from)
    assert clock.hold == 0.0 and clock.prefix == 0.0
    from sloped import presentation as sloped_pres
    assert sloped_pres.omissions(clock) == []


def test_the_film_is_1150_frames():
    """The renderer's own rule: frames 0 to round(19.15 * 60) inclusive."""
    clock = pres.film_clock({"duration": 19.15, "fps": 60})
    assert clock.master_frames == FRAMES
    assert clock.frames == FRAMES
    assert clock.duration == pytest.approx(RUNTIME)
    # And the soundtrack is exactly one frame's worth of samples per frame.
    assert int(round(clock.duration * 48000)) == FRAMES * 800


def test_output_second_is_replay_second():
    clock = pres.film_clock({"duration": 19.15, "fps": 60})
    for index in (0, 1, 573, 1148, 1149):
        when = index / 60.0
        assert clock.at(when) == pytest.approx(when)
        assert clock.replay_at(when) == pytest.approx(when)


def test_the_master_frames_are_contiguous():
    if not MASTER_DIR.is_dir():
        pytest.skip("the master has not been rendered")
    names = sorted(p.name for p in MASTER_DIR.glob("frame_*.png"))
    assert len(names) == FRAMES
    indices = [int(name[6:12]) for name in names]
    assert indices == list(range(indices[0], indices[0] + FRAMES))
    assert indices[0] == 0


# --- the winner -------------------------------------------------------------


def test_the_winner_is_marble_seven():
    replay, _track, _clock = _film()
    marble, when = pres.winner_of(replay)
    assert marble == WINNER
    assert when == pytest.approx(CROSSING, abs=1e-5)


def test_the_winner_label_is_the_rendered_colour():
    """PINK is the renderer's own palette entry for m7, not a Race #1 label.

    `lab_palette.MARBLE_COLOURS[7]` is `#F0559B`, `race2_scene` paints racer
    `info["id"]` with `_palette.marble(id)`, and the delivered frames measure
    hue 330.1 degrees over m7's labelled pixels - 2.8 degrees from the albedo
    and 47.7 from its nearest neighbour in the field.
    """
    assert v24_payoff.winner_label(WINNER) == WINNER_LABEL
    assert overlays.MARBLE_HUES[WINNER] == (240, 85, 155)
    palette = (ROOT / "godot" / "assets" / "marble_machine"
               / "lab_palette.gd").read_text(encoding="utf-8")
    block = palette.split("const MARBLE_COLOURS := [", 1)[1].split("]", 1)[0]
    skins = [line.split('"')[1] for line in block.splitlines() if '"' in line]
    assert skins[WINNER].upper() == "#F0559B"


# --- the comeback -----------------------------------------------------------


def test_the_six_place_claim_is_false():
    """The claim V31's preview ships, rejected on this film's own evidence.

    m7 occupies 6th for a single run of 13 samples. Every instrument that
    weighs a rank by how long it was held says 5th, and so does the race's own
    checkpoint ladder.
    """
    evidence = _evidence()
    comeback = evidence["comeback"]
    assert comeback["deepest_instant_rank"] == 6
    assert comeback["rank"] == COMEBACK
    rejected = {row["rank"]: row for row in comeback["rejected"]}
    assert 6 in rejected, "the 6th-place run must be reported, not silently dropped"
    assert rejected[6]["frames_longest"] < 30
    assert rejected[6]["longest_run"] < comeback["floor_seconds"]


def test_both_rank_instruments_agree():
    evidence = _evidence()
    comeback = evidence["comeback"]
    assert comeback["checkpoint_worst"] == COMEBACK
    assert comeback["instruments_agree"]
    assert comeback["longest_run_at_rank"] >= comeback["floor_seconds"]


def test_comeback_rank_rejects_a_blip():
    """The rule, on made-up runs, so it is the rule that is tested."""
    runs = [(0.0, 0.2, 6), (0.22, 1.4, 5), (1.42, 9.0, 3), (9.02, 19.0, 1)]
    out = pres.comeback_rank(runs, checkpoints={"a": 5})
    assert out["rank"] == 5
    assert out["deepest_instant_rank"] == 6
    assert [row["rank"] for row in out["rejected"]] == [6]
    # And it keeps a rank that was genuinely held.
    longer = [(0.0, 1.0, 6), (1.02, 19.0, 1)]
    assert pres.comeback_rank(longer)["rank"] == 6


# --- the marks --------------------------------------------------------------


def test_pick_a_color_is_up_on_frame_zero():
    evidence = _evidence()
    hook = evidence["hook"]
    assert hook["text"] == "PICK A COLOR"
    assert "".join(hook["lines"]).replace("", "") == "PICK ACOLOR"
    assert hook["in"] == 0.0
    assert hook["out_from"] == 1.05 and hook["out_to"] == 1.30


def test_the_mark_clears_the_first_cut():
    """It must be gone before the lens changes, and it is by 0.93 s."""
    evidence = _evidence()
    _replay, track, _clock = _film()
    first_cut = min(float(cut["to"]) for cut in track["cuts"])
    assert evidence["hook"]["out_to"] < first_cut
    assert first_cut - evidence["hook"]["out_to"] > 0.5


def test_the_mark_never_covers_a_racer():
    evidence = _evidence()
    hook = evidence["hook"]
    ink_low = hook["top_baseline"] + (len(hook["lines"]) - 1) * hook["lead"] * hook["size"]
    assert ink_low < hook["racers_top"]
    assert hook["clearance"] >= pres.HOOK_CLEARANCE


def test_the_mark_is_larger_than_the_v31_preview():
    """Part A, as a number: V31's preview set one line at 104 pt.

    Measured on the delivered face that is a 77 px cap, which is 19.2 px at
    270x480. The two-line block has to beat it by a margin a viewer can see.
    """
    evidence = _evidence()
    one_line = overlays._shadowed("PICK A COLOR", 104, 395, tracking=0.09)
    box = one_line.getchannel("A").point(lambda v: 255 if v >= 200 else 0).getbbox()
    v31_cap_at_phone = (box[3] - box[1]) / 4.0
    assert evidence["hook"]["cap_px_at_270"] > 1.5 * v31_cap_at_phone


def test_the_mark_keeps_its_gutter():
    evidence = _evidence()
    hook = evidence["hook"]
    for width in hook["line_ink_px"]:
        margin = (1080 - width) / 2.0
        assert margin >= hook["gutter_px"] - 1


def test_the_ring_opens_on_the_crossing_and_is_on_the_winner():
    evidence = _evidence()
    ring = evidence["ring"]
    assert ring["marble"] == evidence["winner"]["marble"] == WINNER
    assert ring["from"] == pytest.approx(CROSSING, abs=1.0 / 60 + 1e-6)
    assert ring["frames"] == int(round(pres.RING_SECONDS * 60))
    assert ring["frames_blocked"] == 0


def test_the_ring_never_leaves_the_frame():
    path = DOCS / "ring_track.json"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py evidence` first")
    ring = json.loads(path.read_text(encoding="utf-8"))
    for row in ring["track"]:
        assert row["inside"], f"the winner is off the frame at {row['t']}"


def test_the_card_names_the_winner_and_the_measured_rank():
    evidence = _evidence()
    card = evidence["card"]
    assert card["label"] == WINNER_LABEL
    assert card["winner"] == WINNER
    assert card["from_place"] == COMEBACK == evidence["comeback"]["rank"]
    assert tuple(card["hue"]) == overlays.MARBLE_HUES[WINNER]
    assert card["style"] == "plate"


def test_the_card_comes_after_the_result():
    evidence = _evidence()
    card = evidence["card"]
    beat = card["from"] - evidence["winner"]["crossing"]
    assert 0.8 - 1e-9 <= beat <= 1.5 + 1e-9
    assert card["to"] == pytest.approx(evidence["film"]["runtime_seconds"])
    ring = evidence["ring"]
    assert card["from"] > ring["to"], "the ring and the card must not overlap"


def test_the_card_sits_in_a_band_this_film_measured():
    """Not V24's band: that one has racers in it for the whole of the card."""
    evidence = _evidence()
    card = evidence["card"]
    assert card["inside_band"]
    assert card["band"] != list(v24_payoff.PAYOFF_BAND)
    assert card["band_measure"]["max_luma"] <= pres.CARD_LUMA
    # The card's ink must clear every row a still-racing marble reaches.
    racing = card["band_measure"]["racing_rows"]
    top_racing = min((row[0] for row in racing), default=1920)
    assert card["ink_box"][3] <= top_racing


def test_the_card_reads_as_large_text():
    payoff = v24_payoff.build(style="plate", winner=WINNER, from_place=COMEBACK)
    assert payoff.text_contrast >= 3.0, "WCAG large-text floor"
    assert payoff.colour_pixels > 40000, "the colour has to be an area, not a dot"


# --- audio ------------------------------------------------------------------


def test_the_soundtrack_is_exactly_as_long_as_the_picture():
    path = ROOT / "output" / "race2" / "v32_final" / "work" / f"race2_{COURSE}_{SEED}.wav"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py audio` first")
    from audio.wav_io import read_wav
    info, _data = read_wav(str(path))
    assert info.sample_rate == 48000
    assert info.channels == 2
    # 48000 / 60 = 800 samples per output frame, exactly. See `audio.soundtrack`.
    assert info.sample_count == FRAMES * 800
    assert info.duration == pytest.approx(RUNTIME)


def test_every_mechanism_hit_but_one_is_audible():
    """Part G, measured: the established impact instrument already covers them.

    Race #2's wheels and mixer are not `start.rotor`, so `build_race_audio`'s
    mechanism bed does not fire - correctly, this machine has no mixer. What
    makes a blade strike audible is the same thing that makes any contact
    audible: a velocity residual gravity cannot explain.
    """
    replay, _track, clock = _film()
    from sloped import presentation as sloped_pres
    cues = sloped_pres.impacts(replay, clock)
    hits = [float(e["t"]) for e in replay["events"] if e["kind"] == "mechanism_hit"]
    covered = sum(1 for when in hits if any(abs(c.at - when) <= 0.12 for c in cues))
    assert len(hits) >= 30
    assert covered >= len(hits) - 1


def test_the_qc_report_passes():
    path = DOCS / "qc.json"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py qc` first")
    report = json.loads(path.read_text(encoding="utf-8"))
    failed = [row["line"] for row in report["checks"] if not row["pass"]]
    assert not failed, "QC failures:\n  " + "\n  ".join(failed)
    assert report["frames"] == FRAMES
    assert report["runtime_seconds"] == pytest.approx(RUNTIME)
    assert not report["duplicate_frames"]
    assert not report["black_frames"]
    peak = report["loudness"].get("input_tp")
    assert peak is not None and peak <= -1.0 + 0.05
    integrated = report["loudness"].get("input_i")
    assert integrated is not None and -16.0 <= integrated <= -12.0


def test_the_delivered_files_exist():
    missing = [
        name for name in (
            f"race2_{COURSE}_master.mp4",
            f"race2_{COURSE}_final.mp4",
            f"race2_{COURSE}_final_visual.mp4",
            f"race2_{COURSE}_final_phone_270x480.mp4",
        ) if not (EXPORT / name).is_file()
    ]
    if len(missing) == 4:
        pytest.skip("run `python tools/race2_v32_short.py mux` first")
    assert not missing, f"missing deliverables: {missing}"


# --- production cleanliness -------------------------------------------------


def _delivery_graph():
    """The filter graph the mux stage actually hands ffmpeg, built from evidence.

    The generated string rather than the source text: a test that greps the
    function body is really a test of its comments, and this one has to be a
    test of the chain.
    """
    import tools.race2_v32_short as tool

    evidence = _evidence()
    plan = {
        "ring_from": evidence["ring"]["from"],
        "ring_from_frame": evidence["ring"]["from_frame"],
        "ring_frames": evidence["ring"]["frames"],
    }
    return tool._graph(evidence, plan)


def test_nothing_diagnostic_reaches_the_film():
    """Part K, as a property of the filter graph rather than of a frame.

    The only images composited over the master are the three marks, and the
    only text in any of them is PICK A COLOR, WINNER, the colour name, WINS and
    the two ordinals. There is no version label, no camera annotation, no mask,
    no border and no debug marker anywhere in the chain.
    """
    graph = _delivery_graph()
    assert graph.count("overlay=0:0") == 3, "exactly three marks"
    for forbidden in ("drawtext", "drawbox", "V31", "V32", "control",
                      "hstack", "vstack", "xstack", "pad=", "track=mask",
                      "track=bands", "geq", "colorchannelmixer"):
        assert forbidden not in graph, f"{forbidden!r} in the delivery graph"


def test_the_film_is_never_re_timed():
    graph = _delivery_graph()
    for forbidden in ("minterpolate", "tpad", "trim=", "concat", "reverse",
                      "loop=", "fps=", "framerate=", "setrange", "select="):
        assert forbidden not in graph, f"{forbidden!r} would re-time the film"
    # The one `setpts` that is there offsets the ring sequence by a whole
    # number of frames and does not scale anything.
    assert graph.count("setpts") == 1
    assert "setpts=PTS-STARTPTS+" in graph
    offset = graph.split("setpts=PTS-STARTPTS+", 1)[1].split("/TB", 1)[0]
    numerator, denominator = offset.split("/")
    assert int(numerator) == _evidence()["ring"]["from_frame"]
    assert int(denominator) == 60


def test_every_mark_window_is_stated_in_whole_frames():
    """The frame-snap guard, as a property of the graph.

    A window written in seconds put the ring's first image on frame 950 instead
    of 949 and threw away the flash - `qc`'s `_mark_presence` measured it on the
    delivered file at a 0.9-of-255 difference from the master. Every window is
    now `N/60`, and this asserts the numerators are the frames the evidence
    names.
    """
    import re

    evidence = _evidence()
    graph = _delivery_graph()
    windows = re.findall(r"between\(t,([-\d.]+)/60,([-\d.]+)/60\)", graph)
    assert len(windows) == 3, f"expected three windows, got {windows}"
    spans = [(float(a) + 0.5, float(b) - 0.5) for a, b in windows]
    assert spans[0] == (0.0, round(evidence["hook"]["out_to"] * 60))
    assert spans[1][0] == evidence["ring"]["from_frame"]
    assert spans[1][1] == evidence["ring"]["from_frame"] + evidence["ring"]["frames"] - 1
    assert spans[2] == (evidence["card"]["from_frame"],
                        float(evidence["film"]["last_frame"]))


def test_the_marks_are_where_the_delivered_file_says_they_are():
    """Part J and Part N, measured on the file that ships.

    `qc` decodes the Short and the master at the same frame indices and
    differences them: outside every mark's window the two must be the same
    picture, and inside one the difference must be in that mark's own box.
    """
    path = DOCS / "qc.json"
    if not path.is_file():
        pytest.skip("run `python tools/race2_v32_short.py qc` first")
    report = json.loads(path.read_text(encoding="utf-8"))
    probes = report.get("mark_presence")
    if not probes:
        pytest.skip("this qc.json predates the mark-presence probe")
    for row in probes:
        if row["expect_mark"]:
            assert row["in_box_delta"] is not None and row["in_box_delta"] > 2.0, (
                f"{row['label']}: the mark is not on frame {row['frame']}")
        else:
            assert row["whole_frame_delta"] < 0.5, (
                f"{row['label']}: something is drawn on frame {row['frame']}")
    # The crossing frame specifically: this is the one the frame-snap lost.
    crossing = next(r for r in probes if r["mark"] == "ring"
                    and r["frame"] == _evidence()["ring"]["from_frame"])
    assert crossing["in_box_delta"] > 2.0, (
        "the ring's flash is missing from the frame the winner crosses")
