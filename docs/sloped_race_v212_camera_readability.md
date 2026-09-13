# V21.2 — the camera readability pass

Status: **ten lenses rebuilt over the untouched V19 edit.** No physics, no
course geometry, no re-simulation, no change to seed 5432, to the race, or to
any window of the edit. The replay reproduces its state digest
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6` from the
same command, and the film is still 1150 frames — 19.17 s — with the same two
omissions at the same output seconds, so V20's soundtrack and all three of its
overlays still land where they were placed.

    output/sloped_race_v1/real_race_v212.mp4
    1080x1920, 60 fps, no audio, 1150 frames = 19.17 s, 26.5 MiB

The review this answers: *"I picked a marble, but I lose it during the middle of
the race."*

## The three faults, measured

`sloped.readability` is new and it is the whole of the argument. It measures
four things over **every frame of every cut** rather than at a midpoint — how
large a racer is on a 1080x1920 frame, how much of the field is in shot, where
the pack sits, and what happens across a cut — and it asks `sloped.sightlines`,
which V19 wrote for the finish, the fifth question: of the racers in frame, how
many the course itself is hiding.

Run against V19 it says this:

    cut        px med   in frame   visible of 8   what is in the way
    descent      56.9    7.0/8         2.70       launch's own shell
    long         54.6    5.8/8         4.50       leg1
    hairpin      44.6    6.6/8         6.36       -
    straight     84.0    6.1/8         2.15       leg2
    obstacle    135.9    7.9/8         1.35       leg2, in 101 of 123 samples
    split        33.5    5.2/8         4.96       -
    branch       38.7    3.0/8         2.36       orange
    merge        33.1    5.1/8         2.08       merge, orange, blue

Three separate faults live in that table, and **not one of them was visible to
any check the pipeline had**.

### The racers were behind the course

A marble sits in a cradle 1.4 diameters below its guard rail. Six of the eleven
shots were low enough or side-on enough for that rail to be between the lens and
the field, and the spinner corridor is the extreme: **7.9 racers of 8 inside the
frustum and 1.35 of them actually on screen**. That is the review's "the
obstacle area is visually busy" — it is busy because the busiest thing in the
picture is the wall in front of the racers.

`cameras.frame_report` counts racers inside the frustum and says in its own
docstring that it cannot see occlusion. `readability.visibility_report` casts a
ray per racer per sampled frame through `sightlines`' labelled course and can.

Elevation is the fix and it is nearly free. Swept at the spinner corridor at one
extent and one elevation, bearing 20 shows **7.62 of 8** and bearing 110 shows
**2.08**. Side-on is not a style choice on this course; it is a wall.

### The lens was jumping in the middle of a shot

V19's `merge` moves the camera **29.7 layout units in a single frame**, its
`hairpin` 23.4, its second `start` window 21.1, `long` 20.1 and `split` 5.3 a
frame for 58 consecutive frames. Each of those is a cut nobody edited, and four
of the five are inside the 5–16 s the review names.

The cause is the same one V19 found in its own finish and fixed only there: the
bearing is measured off the *leader's* course tangent, and that tangent reverses
where the run-out doubles back and swings hard through the turns. V19 answered
it with `Cut.side`, which fixes the perpendicular; V21.2 adds `Cut.fixed_heading`,
which fixes the direction that perpendicular is measured from — the heading is
taken once, at the cut's own midpoint, and held.

`check_track` limits how fast the **aim** moves and says nothing about the lens,
and the aim on every one of those shots is either a fixed node or a smoothed
centroid: perfectly steady while the camera flies around it. `MAX_CAMERA_STEP`
is now in the same file, and 1.2 layout units a frame is two marble diameters.

### The late cuts were framed for a spread that is mostly depth

V1.15 set `split`, `branch` and `merge` to extents of 30, 31 and 32 on the
measurement that "the widest the pack itself spans during each cut" is about
thirty layout units. It is — but measured **per route**, the two lobes' own
centroids are only **10 to 14 units apart**; the other twenty are the field
strung out *along* the routes, which a camera absorbs in depth and does not have
to pay for in extent.

A racer is `2 * MARBLE_RADIUS * height / extent` ≈ 1094/extent pixels across at
the aim plane, so those three numbers were spending two thirds of the frame on
length.

## What changed, cut by cut

Every window is V19's. Only the lens is new.

    cut          output      px median     visible/8      coverage      lens step
    start       0.00- 2.10   73.5 -> 73.5  0.59 -> 0.61  1.00 -> 1.00   0.04 ->  0.04
    start       2.10- 4.02   76.0 -> 76.0  0.59 -> 0.61  0.79 -> 0.80  21.09 ->  0.05
    descent     4.02- 5.02   56.9 -> 69.7  0.34 -> 0.91  0.88 -> 0.93   1.18 ->  0.42
    long        5.02- 6.20   54.6 -> 56.0  0.56 -> 0.77  0.72 -> 0.77  20.13 ->  0.50
    hairpin     6.20- 7.20   44.6 -> 58.5  0.80 -> 0.72  0.82 -> 0.82  23.42 ->  0.42
    straight    7.20- 8.40   84.0 -> 71.2  0.27 -> 0.77  0.76 -> 0.78   1.53 ->  0.45
    obstacle    8.40-10.90  135.9 ->135.0  0.17 -> 0.96  0.98 -> 1.00   0.08 ->  0.06
    split      10.90-13.22   33.5 -> 35.9  0.62 -> 0.84  0.65 -> 0.93   5.28 ->  0.08
    branch     13.22-14.62   38.7 -> 49.5  0.29 -> 0.32  0.38 -> 0.36   0.99 ->  0.50
    merge      14.62-15.75   33.1 -> 39.8  0.26 -> 0.34  0.63 -> 0.58  21.98 ->  0.29
    finish     15.75-19.15   60.4 -> 60.4  0.14 -> 0.14  0.27 -> 0.27   0.06 ->  0.06

`visible/8` is the share of the eight racers that are in frame **and not behind
the course**. It is the number this pass exists to move, and over the eight race
shots it goes from 0.40 to 0.73.

Median racer size over the race shots: **55.8 px to 63.8 px**, and the smallest
any of them gets is 35.9 rather than 33.1.

### The start, the obstacle and the finish

The start keeps V19's lens exactly — it was already the best-framed shot in the
film at 8 racers of 8 and 73 px — and gains only a steady heading, which is what
removes the 21-unit jump as the trapdoor opens.

**The obstacle keeps V19's extent too.** At 8 layout units the racers are
already 135 px across, twice anything else in the film; the fault was entirely
that they were behind `leg2`'s guard. Raised from 15 degrees to 38 and swung
from 44 to 20, 7.65 of 8 are visible. Widening it was tried and rejected on the
measurement: at extents of 7.5, 8, 9 and 10 the visible count is 7.65, 7.65,
7.62 and 7.65 — identical — so a wider frame buys nothing and costs 27 px a
racer, and the brief asked for closer.

**The finish is V19's, untouched, and it is the standard the rest were built
to.** Over its own 205 frames it runs at a median 60 px with the winner 68 px at
the crossing, nothing is behind anything for more than 0.12 s, and the lens
moves 0.059 units a frame. The scale floors in `readability` are three quarters
of its own numbers — 48 px median and 34 px at the tenth percentile — so it is
literally the yardstick. There was no measured case for replacing it and it was
not replaced; `test_v212_leaves_the_finish_lens_alone` compares the solved cuts.

### The fork

The aim is still V17's fixed point on the divider: a pack aim cannot show a
choice, and that argument is unchanged. What is new is where the camera stands.
Swept over the whole azimuth at a fixed heading, **330 degrees** is the bearing
that holds the arriving leg *and* both mouths: 6.7 racers of 8 visible against
V19's 4.96, and nobody drops out of shot for a single frame where V19 lost a
quarter of the field for 0.90 s.

**The dolly was twice as strong and the frame edge is what stopped it.** At
(0.12, −0.30) the median racer reaches 38 px, and the price is the blue mouth:
projected frame by frame it slides from x=130 to x=23 and is gone by the end, so
the last second of the fork shot holds one arm of two. That is exactly the fault
V20 recorded — "the blue lead-in leaving the frame entirely" — and no amount of
racer scale is worth a fork with one road. At (0.10, −0.12) the blue mouth stays
between x=103 and x=131 throughout, the racers are 36 px, and a marble on
**each** route is in frame and unobstructed in every sampled frame.

### The branch and the merge

`branch` exists to say there are two ways down, so the measure is
`both_routes`: the share of sampled frames with a racer on each route in frame
*and* unobstructed. It goes **0.79 to 1.00**, and the median racer 38.7 px to
49.5, because the extent stops paying for the 31 units the field is strung out
along the lobes and pays only for the 10 to 14 they are apart.

`merge` gains `Cut.heading_run`. At a junction the leader is on one arm or the
other, so a bearing measured off its tangent stands the lens beside one route
looking across the other — which is how V19 came to show 1.86 racers of the 4.86
it had in frame. Measured off `blue`, the bearing means one thing for the whole
shot however the lead changes. `both_routes` goes **0.42 to 0.75**.

44 degrees is high and it is the geometry's price. The `MergeCatch` the two arms
empty into is a basin whose rim stands 1.1 units above a marble's centre, so a
lens not looking down into it is looking at its wall. The three racers this shot
is about — m5 and m7 on orange, m2 on blue — pass the junction within **0.03 s**
of each other at replay 19.38.

## The line, and the one trade that goes the other way

Every cut in this edit joins two shots of the **same instant**, so the pack's
direction in the world is identical on both sides: `readability` measures +1.00
at all ten boundaries. Any turn the screen shows is therefore the camera having
crossed the line, never the racers turning — and a viewer tracks motion, so that
is the one discontinuity a cut cannot afford.

Neither `jump` nor `swing` can see it. A cut can put the field in exactly the
same corner of the frame and still reverse which way it is going.

    boundary               pack jump         screen direction
    descent  -> long       0.026 -> 0.096    +0.32 -> -0.16
    long     -> hairpin    0.051 -> 0.072    +0.94 -> -0.15
    hairpin  -> straight   0.041 -> 0.097    +0.99 -> -0.28
    straight -> obstacle   0.005 -> 0.003    +0.98 -> +0.92
    obstacle -> split      0.412 -> 0.345    +0.66 -> +0.96
    split    -> branch     0.552 -> None     -0.62 -> +0.97
    branch   -> merge      0.190 -> 0.254    -0.67 -> +0.99
    merge    -> finish     0.521 -> 0.605    +0.99 -> +0.96

V19 crosses the line twice, at the fork and at the merge, and V21.2 does not
cross it anywhere. A first pass fixed those two and broke two others in the
middle at −0.99 and −0.73, so the four middle lenses were solved **as a chain**:
every (bearing, side) candidate measured once for its own visibility and for the
screen direction at each of its ends, then the combination with the most visible
racers among those whose five seams all stay above −0.35.

It costs 2.6 racers of visibility across four shots, and `hairpin` pays most of
it — its best framing holds 7.18 and this one holds 5.73, against V19's 6.36.
That is the single trade in this pass that goes against "racers first", and it
is made because a marble you cannot follow through a cut is not a marble you are
following. `hairpin` still gains 14 px of scale and loses a 23-unit lens jump.

## What is still wrong

Reported rather than hidden, by `tools/sloped_readability.py`:

* **`split` runs at 36 px and `merge` at 40**, under the 48 px floor. The fork
  is a wide subject — the divider plus both mouths plus the leg arriving at
  them — and no framing holds it at finish-lens scale. Both are better than V19
  by 2 to 7 px and by 1.5 to 0.7 of a racer of visibility.
* **`branch` holds 2.9 of 8**, because eight racers spread over 31 units on two
  lobes cannot be held at any readable scale. It holds both *routes* in every
  frame, which is what the shot is for.
* **`merge` hides 42% of what it has in frame**, in the catch basin. Nothing
  below the file's own 46-degree ceiling sees into it.
* **`obstacle -> split` moves the pack 0.345 of the diagonal** and
  **`merge -> finish` 0.605**. The first is the edit's own 0.85 s omission; the
  second is V19's finish opening on one racer at the top-left corner, and the
  finish is not this pass's to move.
* **`start -> descent` and `split -> branch` share no racer** across the cut.
  The first is the field dropping out of the bottom of the machine; the second
  is a lens change at a standstill — the camera travels 17 units and swings 22
  degrees, and the screen direction is +0.97.

## Evidence

    docs/validation/sloped_race_v1/v21/readability_sheet_v212.png

Thirteen moments, V19 above and V21.2 below, the same output second in both
rows, with the measured racer count and size printed under each. The moments are
facts about the replay rather than tastes: both route commitments, the three-way
arrival at the junction, and the winner's crossing all come from the replay's
own events through the edit map. Nine single stills are beside it.

## Tests

`tests/test_sloped_readability.py`, 16 tests: that the edit map and the finish
are untouched, that the course no longer hides the racers, that the lens no
longer jumps, that `check_track` would now catch it, that the racers are bigger,
that no cut loses more of the field than V19's did, that both routes are visible
where the route is the story, that no cut crosses the line, and that the premise
that test rests on — the racers' own direction being identical across every
cut — is true rather than assumed.

The wider suite is unchanged: 1693 passing, 22 skipped, with one pre-existing
failure in `tests/test_neon_proof.py` that also fails on `main` in this
environment.

`SECTIONS` — the blocking cut list, which the labs and the unedited proof render
use — now turns `fixed_heading` on for every cut, because the fault is not
particular to the edit: on a twelve-second proof race it moved the lens 21.3
units in a frame on `start`. **V18 and V19 override it back to False window by
window.** They are delivered films whose tracks the tests compare frame for
frame, and both come out byte-identical to what `main` produces.

## What was not changed

Physics, seed 5432, the replay, the course, the race outcome, the edit map, the
two omissions, the frame count, the start module, the obstacle, the fork
geometry, the merge geometry, the finish lens, marble skins, and
`real_race_v19.mp4` and `real_race_v20.mp4`, which are both still on disk.
