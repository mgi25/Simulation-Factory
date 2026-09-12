# V19 — the finish lens

Status: **V18's edit with one shot re-lensed.** No physics, no course geometry,
no re-simulation, and no change to the cut list or the edit map. The replay's
state digest is still
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6`.

    output/sloped_race_v1/real_race_v19.mp4
    1080x1920, 60 fps, no audio, 1150 frames = 19.17 s, 29.0 MiB

Frame count, duration and edit map are **identical to V18**. Ten of the eleven
cuts come out byte-identical; `finish` is the only one that differs, which
`test_v19_changes_only_the_finish` pins by comparing the solved tracks.

## The failure, measured

The review said the camera became occluded at about 16.9 s and that from
roughly 17.5 s the race was hidden. It is worse than "occluded": the lens was
**inside the course**.

V18 placed the finish camera twenty layout units behind the leading pair at
twelve degrees of elevation. Twenty units behind *this* finish line is not open
air — the course doubles back through there. The sprint runs `final` from
(0.00, 4.85, 36.40) out to the line at (19.80, 1.02, 44.40); `orange` comes down
the other way just above and behind it, from (18.40, 8.20, 23.60) to
(1.10, 4.90, 36.05), where it meets the merge beside the sprint's own start. So
twenty units back along the sprint's axis is not empty — it is beside orange's
last descent. Sampled against the drawn course:

    output   lens to nearest surface    sight line to its own aim
     16.50          3.15 (blue)         clear
     16.75          2.39 (merge)        clear
     17.00          0.47 (merge)        BLOCKED by orange 2.43 units out
     17.50          0.15 (orange)       BLOCKED by orange 2.09 units out
     19.15          0.37 (orange)       BLOCKED by orange 0.54 units out

**0.15 layout units is a quarter of a marble's diameter.** Over the whole shot
the centre of the frame was obstructed in 31 of 35 sampled frames and the next
racer to cross was behind `orange` for **2.50 s at a stretch**.

### What put it there

`terrain.lower_side` was asked, per frame, which side of the track to stand on.
It probes nine units either side of the aim and takes the lower ground, and
where the two are close that verdict flips. On the run-out it does: the side is
`(-0.35, +0.94)` for a hundred samples of `final` and `(+0.36, -0.94)` from
sample 105 on, because the sprint arrives at the finish mesa and the deck's own
ground comes up beside it.

V18's finish crossed that boundary at replay 21.367 s — **output 16.92 s, which
is the review's "approximately 16.9"** — and the camera moved **7.385 layout
units in a single frame**. That is a cut in the middle of a shot, and it landed
the lens on the side `orange` occupies, where it stayed to the end.

Nothing in the pipeline could see it. `check_track` knows where the mountain is;
`terrain.clearance` reported 3.705 units of daylight under the sight line the
whole time, because the *ground* really was clear. `frame_report` counted the
racers inside the frustum and says in its own docstring that it cannot see
occlusion. Between them they checked everything except whether the course was in
the way.

## The check

`sloped.sightlines` builds the drawn course as labelled triangles in layout
units and answers two questions: how far the lens is from the nearest surface,
and what the first thing between the lens and a given point is.

The channel shells are **not mirrored** — they come from `TrackRun.section_at`
and `track.ring_points`, the expression `local_colliders` sweeps and
`v2_forms.banked_sweep` draws, so the guard rail tested against is the rail on
screen. The colliders alone are not enough, though: a camera is stopped by what
is *drawn*, and the FINISH gantry, the deck's rim, its corner pylons and the
piers under every run carry no collider at all. Those are mirrored from
`course_finish.gd` and `course_machine.gd`, and admitted as mirrors.

`check_shot` reports three faults and no others — a lens standing in the course,
an obstructed frame centre, and losing the next racer to cross for longer than a
third of a second at a stretch. It is deliberately not a general camera
framework. On V18 it returns:

    finish at 21.80s: the lens is 0.13 layout units from orange, inside the 2.0 it needs
    finish: the centre of the frame is blocked in 31 of 35 sampled frames, first at
            20.20s by merge 15.36 units from the lens
    finish: the next racer to cross is behind orange for 2.50 s at a stretch, ending 23.60s

On V19 it returns nothing. `tools/sloped_integrate.py` runs it in the `cameras`
stage, so a finish lens like V18's cannot reach a render again.

**A third of a second, not "never", and the difference matters.** V19 loses the
fourth and fifth placed marbles behind the FINISH sign for 0.12 s, two tenths
*before* they cross; they come out from behind it at 81 px and dead-heat in
clear view. That is a post in the foreground, which is how an arena is built and
how it should photograph. V18 lost its subject for 2.50 s and never got it back.

## The new lens

An outside, elevated three-quarter from **downstream**, looking back up the
sprint at the field coming on, with the deck and its gantry between the lens and
the mountain rather than a channel between the lens and the racers.

                        V18                     V19
    target              pair                    node "finish_line"
    subject             marbles 2 and 7         the line itself
    bearing             170 (behind)            25 (ahead quarter)
    elevation           12                      43
    side                terrain, per frame      -1, fixed
    extent / distance   13 / 20.0               16 / 24.6
    orbit / dolly       (-2,2) / (0.06,-0.05)   (-2,2) / (0.03,-0.12)
    camera at 21.90     (  2.65, 5.49, 34.77)   ( 32.11, 17.34, 56.41)
    aim at 21.90        ( 19.80, 1.30, 44.40)   ( 19.80,  1.30, 44.40)
    lens clearance      0.13 .. 3.75            14.24 .. 17.56
    centre blocked      31 of 35 frames         0 of 35
    worst camera step   7.385 units/frame       0.059 units/frame

Three numbers carry it.

**`Cut.side`, so the shot never asks the ground.** Zero keeps the per-frame
terrain choice and is what every other cut still does; +1 and -1 fix the
perpendicular for the whole shot. Nothing detects a flip and smooths it — a shot
that needs smoothing is a shot standing where the ground cannot decide.

**The aim is the line, not the pair.** `target = "pair"` ranks by progress along
the route, and a marble that has crossed is rolling out across a deck that is
not on the route. On this seed the V18 finish's own subject came out marbles
**2 and 7 — second and third**: the winner had already crossed at the cut's
midpoint and was no longer, by that measure, in front. A finish does not need
following; the racers come to the line, so the line is the aim, taken from the
built run's last sample and raised a radius.

**Elevation 43, and 40 is a floor the geometry sets.** The FINISH gantry carries
a 5.4-unit sign whose bottom edge stands 3.26 above the deck, four units
up-course of the deck's centre — directly between a downstream lens and a racer
still short of the line. At the winner's crossing the second-placed marble is
5.22 units back, and swept across every bearing from 20 to 35 on both sides, the
sign is across it at **every elevation below 40 degrees**. 43 leaves three
degrees under the sign and three under this file's own 46-degree ceiling.

### Extent 16, and why the contact sheet decided it

Extents of 14, 16, 17, 18 and 20 all pass `check_shot` with no findings, so the
arithmetic had nothing left to say and the frames were rendered and looked at.
At 14 the FINISH sign — which stands *at* the aim, 3.8 units of gantry on a
14-unit frame — takes a third of the picture and the racers are crowded onto the
bottom edge. At 20 the arena reads but the marbles are barely larger than V17's.

16 is where the sprint still arrives from the top of the frame, the gantry is a
band across the middle rather than the subject, and the deck and its catch lanes
hold the bottom third. Measured on the delivered frame at the winner's crossing
the leading marble is **58 x 64 px**; V17's extent of 24 predicts 46.

The push is a slow tighten rather than a push-in. The drama here is *early* —
the winner crosses 0.65 s into a 3.4 s shot — so a lens that started wide would
be widest exactly when the 0.283 s gap has to read.

## The shot, validated before anything was rendered

`docs/validation/sloped_race_v1/v119/finish_contact_sheet_v19.png`, seventeen
frames: the eleven output times the brief names plus all six crossings.

      out     rep    lens clear   near plane   centre   line    next crosser
    15.75   20.20      17.56        clear      clear    clear   m5 clear
    16.00   20.45      17.33        clear      clear    clear   m5 clear
    16.25   20.70      17.12        clear      clear    clear   m5 behind the sign
    16.50   20.95      16.85        clear      clear    clear   m2 behind the sign
    16.75   21.20      16.65        clear      clear    clear   m7 clear
    17.00   21.45      16.40        clear      clear    clear   m7 clear
    17.25   21.70      16.14        clear      clear    clear   m7 clear
    17.50   21.95      15.89        clear      clear    clear   m4 clear
    18.00   22.45      15.38        clear      clear    clear   m4 behind the sign
    18.50   22.95      14.88        clear      clear    clear   m6 clear
    19.00   23.45      14.39        clear      clear    clear   m6 clear
    19.15   23.60      14.24        clear      clear    clear   m3 clear

Terrain lift 0 degrees, sight line 3.71 above the ground. The three "behind the
sign" entries are the 0.12 s foreground passes described above; every one of
them is followed by a clear crossing.

**All six crossings inside the window are unobstructed:**

    place  replay   output   crossing racer          the one behind it
      1    20.850   16.400   m5  68 px  clear        m2  60 px  clear
      2    21.133   16.683   m2  69 px  clear        m5  77 px  clear
      3    21.717   17.267   m7  71 px  clear        m5  83 px  clear
      4    22.633   18.183   m4  75 px  clear
      5    22.650   18.200   m1  74 px  clear
      6    23.500   19.050   m6  77 px  clear

So the 0.283 s at the front is the winner at the line with the second a clear
frame-quarter back up the channel, and the 0.017 s between fourth and fifth is
two marbles touching at the line. **Nobody is out of shot in any of the 205
frames of the cut.**

Note that the frame at output 15.75 exactly is the *last* frame of the `merge`
shot, not the first of the finish: the renderer picks the cut whose `to` the
time has not passed, and merge ends at replay 20.20. One frame, pre-existing,
invisible.

## One bug found on the way

`sloped_race_scene.cut_midpoint` returned a cut's midpoint in **replay**
seconds and `set_time` takes **output** seconds. Without an edit those are the
same number and it was right for five versions. With one they are not: V18's
finish runs replay 20.20-23.60 at output 15.75-19.15, so its midpoint of 21.90
was read as an output second, clamped past the end of the last window and
photographed at replay 23.60 — the last frame of the film rather than the middle
of the shot.

No video was ever wrong; the **validation stills** were. Fixed by taking the
midpoint from the edit map, which is the only thing that knows both clocks. The
V1.17-era stills committed under `docs/validation/sloped_race_v1/` were taken
before the fix and are not regenerated here, because that would change
deliverables for cuts this pass is not allowed to touch.

## What was not changed

Physics, seed 5432, the replay, course geometry, playback speed, the edit map,
and the start, descent, straight, obstacle, split, branch and merge cameras. The
finish window is V18's exactly — replay 20.20-23.60 at output 15.75-19.15 — and
the film is 19.17 s, as it was.

`check_track` reports one finding on V19: *"merge: the aim is 6.1 layout units
from the nearest racer"*. It reports the same finding on V18. Pre-existing, on a
cut this pass is locked out of.
