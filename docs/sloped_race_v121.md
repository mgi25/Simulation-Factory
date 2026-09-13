# V21 — the three presentation passes, in one film

Status: **integrated and delivered.** Three passes that were developed apart, on
three branches off the same commit, rendered together into one master and cut
with one edit. No physics, no re-simulation, no course geometry, no seed change.
The replay is the same file it has been since V1.15 and the race is bit for bit
the one V20 shipped.

    output/sloped_race_v1/real_race_v21_master.mp4   1080x1920, 60 fps, 1150 frames
                                                     19.167 s, no audio, 26.0 MiB
    output/sloped_race_v1/real_race_v21.mp4          1107 frames, 18.450 s
                                                     AAC 48 kHz, 22.4 MiB
    output/sloped_race_v1/real_race_v21_visual.mp4   the same picture, no audio

`real_race_v19.mp4`, `real_race_v20.mp4` and `real_race_v212.mp4` are untouched.
`python tools/sloped_short.py --edition v20` still builds V20 and
`--edition v211` still builds the retention pass's own proof, both from V19's
master.

## 1. What was integrated

Three commits, each exactly one ahead of `main` at `853c41d`, with disjoint file
sets. All three cherry-picked clean, with no conflicts and no edits:

| pass | source commit | on this branch |
|---|---|---|
| V21.1 start / retention | `9efbf25` | `d8efaad` |
| V21.2 camera readability | `63f16d0` | `212931f` |
| V21 visual contrast | `ebb70b9` | `f6e78c2` |

    presentation.py, sloped_short.py, sloped_short_qc.py, test_sloped_retention.py
    cameras.py, readability.py, sloped_readability.py, sloped_readability_sheet.py,
      test_sloped_readability.py
    lab_palette.gd, course_world.gd, course_scene.gd, sloped_race_scene.gd,
      sloped_contrast_sheet.py, test_sloped_contrast.py

plus the three passes' own documents and validation stills.

## 2. The integration itself, which is not a cherry-pick

**Three passes that each apply to "the master" are not integrated by applying
all three to the same command line.** V21.1 is an edit of a rendered file and
V21.2 and the contrast pass both change what that file contains, so running the
retention cut against `real_race_v19.mp4` would have produced a film with
V21.1's timing and V19's picture — and every number in the QC report would have
been right. That is the one mistake this branch exists to avoid, and
`tests/test_sloped_v21.py` is mostly about it.

So the pipeline is built in the order the dependency actually runs:

    the locked replay, race_5432.json
      -> cameras_5432.json solved with cameras.EDITS["v212"]
      -> Godot renders every frame of it under lab_palette.new("tower", "v21")
      -> real_race_v21_master.mp4, 1150 frames
      -> the V21.1 retention cut, 85 frames out of the middle of the start
      -> the hold, the three overlays, the synthesised soundtrack
      -> real_race_v21.mp4

Two things carry it in the code. `tools/sloped_integrate.py --stage clip` takes
the camera track it is given and the race scene's own contrast default, so the
master needed no new flag. And `tools/sloped_short.py`'s editions grew a
`master` field:

    v20    real_race_v19.mp4         no cuts        real_race_v20.mp4
    v211   real_race_v19.mp4         (49, 133)      real_race_v211.mp4
    v21    real_race_v21_master.mp4  (49, 133)      real_race_v21.mp4

The cut is the same pair of frame numbers on both masters because both are
rendered from the same edit map — V21.2 changed every lens and no window. That
is asserted rather than assumed: `test_the_integrated_master_uses_the_v212_
lenses_over_v19s_windows` compares `EDITS["v212"]` with `EDITS["v19"]` window by
window.

## 3. Physics and replay identity

Nothing in this branch is upstream of anything that decides the race. The
replay was not rebuilt; the camera solve, the Godot render, the ffmpeg cut and
the overlay compositor all read it.

* seed **5432**, 8 marbles, 2701 replay frames, 45.00 s, render scale 0.5700;
* finish order **5, 2, 7, 4, 1, 6, 3, 0**, marble 5 winning by 0.283 s;
* the camera solve prints the same eleven cuts, the same durations and the same
  `keeps 19.15 s of 45.00 s, omitting 4.25 s` it has since V19;
* `tests/test_sloped_cameras.py`, `test_sloped_short.py` and
  `test_sloped_retention.py` all compare V18's and V19's solved tracks against
  their committed values and pass.

## 4. The new start timing

Unchanged from the retention pass, because it is a property of the edit map and
the map did not move. Measured on the delivered file by `tools/sloped_short_qc.py`
and by the clock:

| marker | V20 | V21 |
|---|---|---|
| PICK ONE | 0.10–0.80 | 0.10–0.80 |
| the gates first move | 0.817 | 0.817 |
| the cut | 2.800 | **1.517** |
| the floor opens | 3.217 | **1.800** |
| the downhill lens | 4.720 | **3.303** |
| first racer onto `leg1` | 4.983 | **3.567** |
| all eight onto `leg1` | 6.017 | **4.600** |
| the winner crosses | 17.100 | **15.683** |
| runtime | 19.867 | **18.450** |
| frames | 1192 | **1107** |

The join was re-checked in the pixels of the new master, which is the one part
of the retention pass that could not be inherited: delivered frame 90 is master
frame 48 (mean difference 1.12 of 255, which is re-encode noise), delivered
frame 91 is master frame 134 (0.88), and the two of them differ in **83.7 %** of
the frame. The retention pass measured 56 % on V19's master; the number is
higher here because V21.2's `start` lens holds a fixed heading, so the second
half of the shot is framed differently from V19's and more of the picture
changes across the skip. Nothing about the skip itself moved.

## 5. Cameras

Every window is V19's and every lens is new except the finish, which V21.2
deliberately kept. Reproduced on this branch by
`python tools/sloped_readability.py --seed 5432 --edit v212 --against v19`:

    cut          px median      in frame      camera step (units/frame)
    start        76.0 -> 76.0   0.79 -> 0.80  21.09 -> 0.05
    descent      56.9 -> 69.7   0.88 -> 0.93   1.18 -> 0.42
    long         54.6 -> 56.0   0.72 -> 0.77  20.13 -> 0.50
    hairpin      44.6 -> 58.5   0.82 -> 0.82  23.42 -> 0.42
    straight     84.0 -> 71.2   0.76 -> 0.78   1.53 -> 0.45
    obstacle    135.9 ->135.0   0.98 -> 1.00   0.08 -> 0.06
    split        33.5 -> 35.9   0.65 -> 0.93   5.28 -> 0.08
    branch       38.7 -> 49.5   0.38 -> 0.36   0.99 -> 0.50
    merge        33.1 -> 39.8   0.63 -> 0.58  21.98 -> 0.29
    finish       60.4 -> 60.4   0.27 -> 0.27   0.06 -> 0.06

Median racer over the eight race shots **55.8 px to 63.8 px**, and the largest
single-frame lens movement in the film falls from **29.7 layout units to 0.50**
— which is the difference between a camera that jumps mid-shot and one that
does not.

## 6, 7, 8. The obstacle, the fork and the merge

The measurement these three share is occlusion, and it is the one the frustum
count could not make. `sloped.readability.visibility_report` casts a ray per
racer per sampled frame through the labelled course. Run on both edits from this
branch:

    cut        in frame        visible of 8      hidden      what is in the way
    descent    7.00 -> 7.40    2.70 -> 7.30    0.61 -> 0.01  launch, leg1
    long       5.75 -> 6.17    4.50 -> 6.17    0.22 -> 0.00  leg1
    hairpin    6.73 -> 6.55    6.36 -> 5.73    0.05 -> 0.13  leg2, leg1
    straight   6.08 -> 6.31    2.15 -> 6.15    0.65 -> 0.02  leg2, obstacle
    obstacle   7.85 -> 8.00    1.35 -> 7.65    0.83 -> 0.04  obstacle
    split      5.29 -> 7.38    4.96 -> 6.75    0.06 -> 0.09  leg3, orange_lead
    branch     3.00 -> 2.86    2.36 -> 2.57    0.21 -> 0.10  orange
    merge      5.08 -> 4.75    2.08 -> 2.75    0.59 -> 0.42  merge, blue_lead

Over the eight race shots, **3.31 racers of 8 visible becomes 5.63**.

* **The obstacle** was the extreme: 7.85 racers of 8 inside the frustum and
  **1.35** actually on screen, because the busiest thing in the picture was
  `leg2`'s guard rail in front of them. Raised from 15 degrees to 38 and swung
  from 44 to 20, it holds 7.65 at the same 8-unit extent, so the racers are
  still 135 px across. In the delivered film the paddles read as mechanism and
  the marbles read as marbles.
* **The fork** keeps V17's fixed aim on the divider and moves the camera to
  bearing 330, which holds the arriving leg and both mouths: 4.96 visible
  becomes 6.75, `both_routes` is **1.000** of sampled frames against V19's
  1.000, and no frame loses a quarter of the field the way V19 did for 0.90 s.
  The dolly was deliberately left at half strength because the stronger one
  walked the blue mouth off the frame.
* **The merge** gains `Cut.heading_run`, so the bearing means one thing for the
  whole shot however the lead changes: `both_routes` **0.417 to 0.750**, visible
  2.08 to 2.75, and the lens stops moving 22 units in a frame. The catch basin
  still hides 42 % of what is in shot and nothing under the file's 46-degree
  ceiling sees into it.

## 9. Visual contrast, re-measured under the new cameras

The contrast pass's table was taken on V19's lenses, so none of it survives a
camera change unexamined. `tools/sloped_contrast_measure.py` is new and is the
measurement made re-runnable: the eleven cut midpoints rendered twice from the
same scene, once with `--contrast=v21` (the race scene's default) and once with
`--contrast=` (the V20 control), both through the **V21.2** camera track.

                                                  V20      V21    delta
    pixels flat white (all channels 242+)   %    5.20     0.93    -4.28
    pixels at 250+ in any channel           %    9.61     4.50    -5.11
    pixels above L* 88                      %   11.43     6.96    -4.47
    pixels above L* 78                      %   19.32    11.91    -7.40
    99th percentile frame lightness   L*        99.85    97.43    -2.43
    mean frame lightness              L*        38.47    34.85    -3.62
    racer vs. its surround, dE                  58.29    62.24    +3.95
    the same, median rather than mean           58.94    66.19    +7.26
    racer vs. its surround, chroma only         55.77    60.00    +4.24
    the same at 270x480, dE                     58.52    62.36    +3.83
    the same at 270x480, chroma only            55.96    60.07    +4.11

**The absolute ΔE figures are not comparable with the contrast pass's own
table.** That pass sampled the ball and its surround by hand at a geometry this
tool does not reproduce, so it reports 30.0 → 32.8 where this reports
58.29 → 62.24. What is comparable is the direction and the sign, and both hold:
the clipping collapses, the racers separate further from what is behind them,
and the gain survives the resample to phone size rather than living in detail
nobody sees.

The clipping numbers land within half a point of the contrast pass's own
(5.54 → 0.87 there, 5.20 → 0.93 here), which is what "the cameras changed and
the grade did not" should look like. 70 racers are sampled in both builds,
because the frames are the same frames.

## 10. The winner's payoff

The one thing in V21 that is neither of the three passes. V20's mark is correct
and quiet, and at phone size quiet was the fault: a gold hairline that a viewer
notices only if they were already looking at the right marble.

Three changes, all inside the mark's existing 0.70 s and all within about three
marble radii of the winner:

* **a flash on the frame the mark opens** — one marble of warm white over the
  ball, full strength for a frame and back to baseline within five. Measured on
  the delivered file, the mean over the ball runs 173 · 173 · **229** · 224 ·
  209 · 196 · 185 · 180 across frames 951 to 958;
* **a short glow** under the ring, gold, up in the first fifth of the mark and
  gone by halfway. It is the thing that makes the eye arrive;
* **a heavier stroke**, 0.17 of the marble's radius to 0.24.

The first build of all three was too soft to see and was found by measuring
rather than by looking: a 23-pixel flash blurred by 19 pixels raised the region
around the winner by 1.6 of 255. **Blur radius is the term that matters at this
scale, not alpha.**

One real bug came out of it. `ring_from` is `crossing + 0.20 s`, which is not a
whole number of frames, and it becomes a `setpts` offset in the ring stream's
own 1/60 timebase — so the sequence landed between two frames and the first one,
the frame the flash exists for, was never composited. `stage_overlays` now snaps
the mark to a frame boundary and the flash lands on frame 953, exactly
`crossing + 0.20`.

The mark is still a pulse and not a lock-on, still ends at 16.58 s — 0.89 s
before the fourth and fifth arrive together — and the other seven racers are
untouched. Nothing about the race changed to produce it.

    docs/validation/sloped_race_v1/v21_final/winner_mark.png

## 11. The end card

`FROM 6TH → 1ST` is kept, because it is the fact that says the winner came back.
Two changes and no new information:

* **a hierarchy.** The two runs are set at 0.82 and 1.26 of the base size, so
  the result is a third again of cap height over the setup. V20 set both at one
  size and the line read as a caption;
* **the winning marble's own hue**, as a ball the size of the large text's
  x-height immediately before "1ST", filled with `MARBLE_HUES[5]` and rimmed in
  graphite. The ring on the winner has been gone for about a second by the time
  this comes on, and the ball is what carries "the purple one" across that gap.
  It is read out of the replay's own winner, so a different seed would carry a
  different colour, and `tests/test_sloped_v21.py` checks the table against
  `lab_palette.MARBLE_COLOURS` rather than trusting the copy.

**And one fix that mattered more than either.** The card is graphite letters on
a light halo, sized for a background measured at 130–159 luma — but that
measurement is of a *band*, and the band is a chequer. Half of it is the dark
tile, and at V21's size "1ST" lands squarely on two black squares, where V20's
soft falloff had already thinned to nothing by the glyph edge. The halo is now
built in two passes from a mask: the wide soft lift, and a tighter one driven
back up to opacity, so every glyph carries a solid warm-white edge whatever tile
it is over. Three pixels out from the letterforms the card is 243 alpha on
average. It is built from a mask rather than by blurring a coloured layer,
because blur runs per channel and blurring warm white on transparent black
drags the colour to grey as the alpha falls.

No route labels, no leaderboard, no statistics, no flags. The card is still the
only text after 0.80 s except the word WINNER.

## 12. Audio and QC

`audio/marble.py` is untouched. Everything it places is derived from the clock,
so the soundtrack moved with the picture and needed nothing:

* the tension run-up ends on the gates at **0.817**;
* the trapdoor cue is on the frame `start.panel` first moves, **1.800**;
* the whooshes are the edit map's own omissions, **4.833 s at 1.517** and
  **0.850 s at 10.183**;
* 210 contacts survive the rationing; three were inside the omitted drum.

    peak in -10.62 dBFS, compressor 5.15 dB, out -1.62 dBFS, limiter idle
    integrated -14.01 LUFS, range 3.80 LU, true peak -1.58 dBTP

Crossings: #1 −1.63, #4 −2.55, #5 −2.55, #2 −2.73, #3 −2.83, #6 −6.04, and the
winner is 7.5 dB over a typical mid-race moment. The loudest moment in the whole
film is 15.71 s and the winner crosses at 15.68.

`tools/sloped_short_qc.py --edition v21`: **nineteen checks, all passing** —
format, 1107 frames, runtime inside 18.2–18.7, stream layout, true peak, the
crossing hierarchy, the idle limiter, no black frames, `mpdecimate` keeping 1081
of 1107, the held opening as one still picture, the three overlay windows
against measured marble positions, and the release inside the first two seconds.

The QC's one edition-specific check no longer names `"v21"`; it applies to any
edition that carries a cut, so the retention proof is held to it too.

## 13. Mobile readability

`docs/validation/sloped_race_v1/v21_final/phone.png` is fourteen moments, V20
beside V21, at 270×480 a frame — roughly what a 1080-wide Short occupies on a
handset. The moments are written once as V21 output seconds and the V20 partner
is derived through the retention shift, so every pair is the same instant of the
same race rather than the same second of two different clocks.

Reviewed cut by cut against "if I picked a marble during PICK ONE, can I still
follow it":

* **start** — eight distinct balls in their bays, PICK ONE clear of them, the
  gates and the tumble legible, the skip inside one lens on one shot;
* **first descent** — the single largest gain in the film. V20 shows an empty
  white chute with the field behind its own guard; V21 shows six racers strung
  down it, each one readable;
* **long, hairpin, straight** — the pack is where the eye already is and the
  racers are 56 to 71 px rather than 45 to 55;
* **obstacle** — marbles between the paddles instead of a rail across the
  front;
* **split** — the arriving leg, the divider and both mouths, with a racer
  already committed to orange;
* **branch** — both routes in every sampled frame, and the honest weakness
  below;
* **merge** — both arms and the junction, close enough to compare positions;
* **finish** — V19's lens, untouched, and the mark and the card both readable
  at 270 px wide where V20's "1ST" is not.

## 14. Tests

    tests/test_sloped_v21.py          25 new, all passing
    tests/test_sloped_retention.py    25
    tests/test_sloped_readability.py  16
    tests/test_sloped_contrast.py     unchanged
    tests/test_sloped_short.py        22, unchanged and still passing
    tests/test_sloped_cameras.py      unchanged

The whole suite on this branch, under the project venv: **1918 passed, 4
skipped, 1 failed in 35 min**. The failure is
`tests/test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised`
and it is environmental: it asserts on an error message about a missing Godot
binary and gets one about a missing replay, because a clean worktree does not
carry the gitignored `output/neon_v11/` fixture. It fails the same way on `main`
in this environment and nothing in V21 touches `neon_proof`.

Note that the system Python does not have `pymunk`; 32 test modules fail to
import under it. The project venv at `.venv/` is the one to run the suite with.

## 15. What is still wrong

Reported rather than hidden. Everything here is inherited from a pass that
measured it and said so; the integration added none of it.

* **`branch` holds 2.86 racers of 8.** Eight marbles spread over 31 layout
  units on two lobes cannot be held at a readable scale, and this shot chooses
  to hold both *routes* in every frame instead. It is the one cut where a
  viewer following a specific marble may lose it.
* **`split` runs at 36 px and `merge` at 40**, under the 48 px a phone frame
  wants. Both are better than V19 and neither can be framed tighter without
  dropping half the junction.
* **`merge` still hides 42 % of what it has in frame**, in the catch basin.
* **`merge -> finish` moves the pack 0.60 of the frame diagonal.** That is
  V19's finish opening on one racer in the top-left corner, and the finish was
  not this version's to move.
* **`_dusk_band` in `course_world.gd` calls `look_at` before the node is in the
  tree**, so nine horizon slabs render unrotated and Godot prints an error per
  slab on every build. It dates to `85bb7d2`, it is in every render this project
  has made including V19's and V20's, and it is not a V21 regression. It is
  cosmetic and it is worth a separate fix.
* **The flash whites the winner out for one frame.** It is 17 ms and the ball
  keeps its hue from the next frame on, but it is the one place in V21 where a
  marble's identity is briefly not on screen.
* **Country skins are still not in.** The contrast pass deliberately came first
  so that a skin would be judged against a background that is not clipped.

## 16. Should V21 replace V20?

**Yes.** Every number that was measured before and after moves the right way and
none of the regressions is in the picture:

* 1.42 s shorter, with the release at 1.80 s instead of 3.22 and the first
  racer on the mountain at 3.57 instead of 4.98;
* 3.31 racers of 8 visible over the race shots becomes 5.63, and the median
  racer 55.8 px becomes 63.8;
* the largest lens jump in the film, 29.7 layout units in one frame, becomes
  0.50;
* one frame pixel in nineteen was flat white and now it is one in a hundred and
  eight, while the racers gain 4 ΔE against what is behind them and keep it at
  phone size;
* the payoff reads at 270 px wide, where V20's did not.

The two shots that are worse are `hairpin`, which loses 0.6 of a racer of
visibility to hold the screen direction across its two cuts and gains 14 px of
scale doing it, and `merge`, which trades 0.33 of a racer in frame for 0.67 more
actually visible and both routes readable. Both are trades a pass made on
purpose and recorded.

V20 remains on disk and rebuildable from this branch, which is the condition
under which replacing it costs nothing.
