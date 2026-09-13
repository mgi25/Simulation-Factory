# V22.1 — the finish as the end of the chase

*A prototype on `v221-finish-continuity`, from `origin/v22-integration`
(`57d50da`). Nothing here is merged and nothing here is production.*

## The defect

V22's chase runs replay 7.620 to 20.200 in one unbroken span and then cuts to
V19's finish lens. Measured by `readability.continuity_report` the cut moves the
shared racer **0.443 of the frame diagonal**, swings the view **56.1 degrees**
and teleports the lens **51.17 layout units**. Only one marble is in both
pictures, so the viewer following their own ball has one thing to reacquire it
by and it has moved almost half the screen.

It is softer than V21's 0.605 and it is still the only hard cut left in the film
after the start's omission. And it lands at replay 20.200 — **0.650 s before
the winner crosses at 20.850**. Of all the half-seconds in the race, that is the
worst one to ask a viewer to re-find their marble in.

Integration's own repair — easing the chase lens onto the finish lens — failed,
at 2.5 to 6.6 layout units a frame. This pass does not repeat it.

## The mechanism: a chase that stops chasing is a stand

The failed repair moved a *moving* camera onto a *distant* one, so the ease's
travel and the chase's own travel added. The alternative is to notice what the
end of a race actually is:

> The racers come to the line. So the camera does not have to.

The last thing the chase does is **park**: decelerate from its own velocity at
a chosen split onto a pose fixed to the finish line, up-course of it and above
it, and hold. A parked camera has no whip available to it, and the whole of the
move is spent up-course of the crossing where there is nothing to read yet.

`sloped/v221_finish.py` takes the **frozen** V22 track and rewrites only its
tail. Every row before the split is the row the V22 solve wrote — byte for
byte, asserted by `test_nothing_before_the_split_moves`.

### The one number this pass turned on

Write the deceleration as a cubic Hermite whose start tangent is the chase's own
per-frame velocity `v0` and whose end tangent is zero. In the curve's own units,
with `u(s)` the fraction of the journey covered and

    r = steps * v0 / distance

— how much of the journey the entry speed would cover if it never changed — the
derivative is

    u'(s) = (1 - s) * ((6 - 3r) * s + r)

and that expression decides everything without a sweep:

| `r` | what the lens does |
|---|---|
| `> 3` | **overshoots.** `u'` goes negative before `s = 1`: the lens flies past the park and comes back. A bounce. |
| `< 1.5` | **bulges.** The peak of `u'` moves off `s = 0` and the lens must speed *up* to arrive in time. This is the previous attempt's 2.5–6.6 units a frame, reached from the other direction. |
| `1.5 … 3` | **maximum step is exactly `v0`.** `u'` is largest at `s = 0` where it is `r`, and `(D/N) * r = v0`. |

So a settle solved into that band cannot move the lens faster than the chase was
already moving it, *whatever the distance is*. The V22 chase's own worst interior
step is 0.832 layout units a frame, and that becomes the ceiling for free.
`settle_seconds` solves for `r = 2.0`, the middle of the band.

The first rendered step comes out a shade *under* `v0` — 0.824 against 0.831 —
because a rendered step is the integral of a falling derivative across one frame.
The deficit is `1/steps`, and it is the right sign: the first frame of the finish
can only be calmer than the last frame of the chase.

### The aim gets its own settle, and that is the anticipation

Tying the aim to the position was the first version and it was quietly bad: the
finish line did not enter the frame until the lens had nearly stopped, so the
shot arrived at the finish at the same moment the viewer did.

The two channels have different jobs. The position has 71 layout units to cross
and may not do it faster than the chase already was. The aim has 31 and its only
real limit is how fast the picture may turn. Given its own, shorter settle the
camera **looks where it is going before it gets there** — which is the brief's
"aim slightly ahead toward the finish line", said as a number.

Swept (`--stage sweep-split`), shortening the aim's settle improves four things
at once and costs one:

| aim settle | finish-line lead | max turn °/frame | aim step | `check_finish` |
|---|---|---|---|---|
| tied to position (2.68 s) | 0.83 s | 0.98 | 0.294 | clean |
| 1.60 s | 1.17 s | 0.88 | 0.37 | clean |
| **1.20 s** | **1.37 s** | **0.88** | **0.484** | **clean** |
| 1.00 s | 1.47 s | 0.88 | 0.588 | clean |
| 0.80 s | 1.57 s | 0.88 | 0.745 | **aim outruns the field** |

The turn rate *falls* as the aim settles sooner, which is counter-intuitive until
you see why: with a slow aim the camera keeps yawing all the way through its own
travel, and with a fast one the aim locks onto the line early and the view
direction afterwards only changes as the lens translates. The floor is the
production aim-speed rule — `cameras.check_track` allows an aim to move at
`max(fastest racer, one radius) * 1.15`, which here is 0.60 units a frame.
**1.2 s is the fastest setting with real margin**, and it is what ships.

### Where the split goes, and the surprise in it

The obvious reading is that an earlier split leaves more room to brake in. It
does not, because the room is bought with the chase's **entry speed** rather
than with wall-clock seconds — `settle = r * distance / v0`.

| split | chase speed there | settle needed | parked at | lead | winner px | crossings readable |
|---|---|---|---|---|---|---|
| 18.600 | 0.464 | 5.02 s | 23.62 | 1.67 s | 29.2 | 5/8 |
| 18.750 | 0.697 | 3.29 s | 22.04 | 1.50 s | 47.0 | 7/8 |
| **18.900** | **0.831** | **2.68 s** | **21.58** | **1.37 s** | **54.9** | **8/8** |
| 19.050 | 0.672 | 3.16 s | 22.21 | 1.10 s | 41.7 | 6/8 |
| 19.200 | 0.670 | 3.13 s | 22.33 | 0.90 s | 37.9 | 6/8 |
| 19.400 | 0.534 | 3.67 s | 23.07 | 0.70 s | 37.2 | 6/8 |

**An earlier split buys more anticipation and loses the race.** 18.600 has the
longest lead in the table — 1.67 s — and 5 of its 8 crossings are under the
readable floor, because a 5.02 s settle from 18.600 parks the lens at 23.62 and
the winner crosses at 20.850 with the camera still most of the way up-course of
where it is going. The winner is 29 px.

18.900 is the only split in the sweep that is **admissible at all**: 8 of 8
crossings in frame, clear and over 48 px. It is the merge phase's own fastest
frame, and since `settle = r * distance / v0` the fastest frame is the one that
brakes soonest. It is also 0.483 s **into** the merge phase, so the branch
cameras and the opening of the merge are untouched — which is what the brief
asked for, and is asserted rather than claimed.

## The candidates

All four are the same track before replay 18.900.

| | **A** rear chase | **B** rear then orbit | **C** V22 control | **D** rear then pull-back |
|---|---|---|---|---|
| max camera step, units/frame | **0.824** | **0.824** | 51.123 | 0.824 |
| max turn, °/frame | **0.880** | **0.880** | 55.986 | 0.880 |
| max screen move, px/frame | **43** | **43** | 974 | 43 |
| **finish-line lead** | **1.37 s** | **1.37 s** | 0.63 s | 1.37 s |
| winner px at the crossing | 54.9 | 54.9 | **67.3** | 54.9 |
| winner px, median over its last 1.5 s | **54.9** | **54.9** | 32.7 | 54.9 |
| racers in frame, mean | 1.76 | 1.54 | **2.46** | 1.86 |
| racers unobstructed, mean | 1.63 | 1.38 | **1.92** | 1.73 |
| hidden share | 0.071 | 0.105 | 0.221 | **0.067** |
| run-out: share of live racers seen | 0.31 | 0.22 | **0.33** | 0.34 |
| run-out racer px | **64.4** | 61.8 | 60.9 | 59.1 |
| crossings in frame | 8/8 | 8/8 | 8/8 | 8/8 |
| **crossings readable (≥48 px, clear)** | **8/8** | **8/8** | **8/8** | 5/8 |
| max cut jump | 0.243 | 0.243 | **0.443** | 0.243 |
| hard cuts | **0** | **0** | 1 | **0** |
| camera discontinuities | **0** | **0** | 3 | **0** |
| min ground clearance | 24.93 | 25.21 | 18.71 | 24.98 |
| `check_finish` findings | **0** | **0** | **0** | **0** |

The 0.243 in A, B and D is the film's pre-existing `start → descent` boundary
across the start omission. It is not new and this pass does not touch it.

Per-crossing sizes, which is the brief's "exactly which marble crosses first":

| place | marble | replay | A | B | C | D |
|---|---|---|---|---|---|---|
| 1 | m5 | 20.850 | 54.9 | 54.9 | 67.3 | 54.9 |
| 2 | m2 | 21.133 | 54.4 | 54.4 | 68.5 | 54.4 |
| 3 | m7 | 21.717 | 53.0 | 53.2 | 70.3 | 52.6 |
| 4 | m4 | 22.633 | 52.6 | 54.8 | 72.8 | 48.5 |
| 5 | m1 | 22.650 | 53.0 | 55.4 | 72.8 | 48.8 |
| 6 | m6 | 23.500 | 52.8 | 58.1 | 74.4 | **43.6** |
| 7 | m3 | 24.317 | 53.0 | 61.6 | 76.4 | **39.7** |
| 8 | m0 | 24.417 | 52.8 | 63.3 | 77.8 | **39.2** |

**D is falsified and is in the list for that reason.** A straight pull-back is
the obvious way to recover the stragglers a rear park cannot hold, and it does —
it is the only variant that gets more than 1.8 racers into an average frame. It
also takes the last three crossings under the 48 px floor, because the thing it
pulls back from is the line. A finish that shows more of the field and less of
the finishing is not a finish.

## Two findings that decide the shape of this

### 1. A rear park cannot hold the whole field, and no tuning fixes it

At the winner's crossing the seven live racers are spread from 5.2 to 34.4
layout units from the line. A camera parked 26 units up-course has two of them
*behind it*. Pushing the park back far enough to contain them costs the winner
its readability: at radius 26 the winner is 54.9 px and at radius 38 (candidate
D's park) the tail crossings are 39 px.

So the rear language trades **company for scale**, at about 0.9 px of racer per
layout unit of radius. Swept at bearing 180 and height 18 (`--stage sweep`, 115
of 150 poses admissible):

| radius | winner px | smallest crossing px | racers in frame | |
|---|---|---|---|---|
| 20 | 60.4 | 60.4 | 0.88 | |
| 22 | 58.5 | 58.4 | 0.95 | |
| 24 | 56.7 | 55.4 | 1.06 | |
| **26** | **54.9** | **52.6** | **1.15** | **ships** |
| 28 | 53.1 | 50.0 | 1.26 | 2.0 px of floor margin |
| 32 | 49.8 | 45.4 | 1.55 | **1 of 8 readable** |

**The sweep's own ranking does not pick 26.** Ranked by the winner's size it
picks radius 20 at height 14, which puts the winner at 66.3 px — within 1 px of
the control's 67.3 — and shows 0.86 racers in an average frame. Taking 26
instead gives up 11.4 px of winner to buy 0.29 of a racer and 4 layout units of
ground clearance. That is a judgement and not a measurement, and it is the one
place in this report where the numbers were overruled: the brief names "remaining
racers become impossible to see" as a failure mode, and 0.86 is close enough to
"one marble at a time" to be worth 11 px that were never going to be missed
above a 48 px floor.

At 26 the run-out ends up showing the same share of the live field as the control
does (0.31 against 0.33) at a *larger* size, which is the sanity check on that
judgement.

### 2. The gantry legs make a 15-degree azimuth band impassable

This is the finding that decides candidate B, and it took a rendered frame to
see and a ray cast to pin down.

`sightlines._finish_furniture` gives the finish gantry two legs, 3.80 layout
units either side of the deck centre, plus a crossbar and the sign. Cast a ray
from a camera standing at each bearing about the line, at radius 22 and height
17.6, to the crossing point and to the two marbles that finish 0.017 s apart:

| bearing | 70 | 75 | 80 | 85 | 90 | 95 | 105 |
|---|---|---|---|---|---|---|---|
| the line itself | blocked | blocked | blocked | clear | clear | clear | clear |
| m4, the 4th | clear | clear | blocked | blocked | blocked | clear | clear |
| m1, the 5th | clear | blocked | blocked | clear | clear | clear | clear |

At **85 and 90 degrees marble 4 is behind the gantry at every radius from 14 to
28 and every height from 14 to 50 that was tried.** It cannot be flown over:
raising the camera slides the sight line *down* the leg rather than past it. The
mirrored band at 270–285 behaves the same way. Any orbit from behind the line to
a lens that can read the FINISH board has to cross it.

**And the band is wider in the picture than in the ray cast, which is how this
was actually found.** Candidate B's first timing — 2.8 s from 21.150, chosen
purely on turn rate — put the 4th/5th dead heat at bearing 96.1: six degrees
outside the band, ray-clear, and **every aggregate metric called it admissible,
8 of 8 crossings readable**. The rendered frame is the reason it is not shipped:
at 96 degrees the camera is nearly edge-on to the deck, the near gantry leg
stands immediately beside the two closest finishers, and the pair sit squeezed
against the deck's edge while the deck itself fills the other half of the frame.
The rays passed through the marble centres; it was the composition that failed,
and no number in this report can see that.

So the question is *when* the swing crosses the band — and the answer has to be
"in a gap between crossings, with room either side". 5.400 s at a 0.45 ease from
20.900 puts it between the 6th finisher at 23.500 and the 7th at 24.317. Bearing
at each of the eight crossings is then **180, 180, 177, 152, 151, 109, 67, 62**,
and nothing is within 13 degrees of the band. That is the version measured and
rendered above.

### A third, smaller one: the FINISH board is a one-sided object

The board faces **down-course**, so it reads from the finish side and a camera
behind the racers sees its blank back. The orange finish tape across the track
is likewise only obvious from in front. This is not a bug and it is not fixable
from behind: it is why candidate C's crossing frame is the most explicit single
image in the comparison, and it is the honest cost of the rear language.

What the rear camera has instead is the deck's own checkerboard, which the
marble visibly rolls onto, and the fact that the viewer has been watching the
line approach for 1.37 s rather than 0.63.

## Recommendation: **A**, the continuous rear chase

Against the control it wins on every continuity measure and on the thing the
brief named as the goal:

* **no cut at all** — the 0.443 boundary does not become smaller, it stops
  existing. 0 hard cuts, 0 discontinuities, 0 `check_finish` findings.
* **2.1× the anticipation** — 1.37 s of unbroken, unobstructed finish line
  before the winner, against 0.63 s. Tightened to "inside the middle half of the
  frame" rather than "inside the frame with a 90 px margin", it is 1.20 s
  against 0.65 s, so the margin is not where the win comes from.
* **a bigger winner for longer** — 54.9 px median over its last 1.5 s against
  32.7 px, because the camera is parked while the winner comes to it instead of
  cutting to a lens that has just acquired it.
* **all eight cross readable** — the smallest is 52.6 px, and nothing is behind
  anything at any crossing.
* **a steadier winner mark** — 15.6 px/frame of screen drift against 37.7.

It loses on exactly one number: the winner is 54.9 px at the crossing instant
rather than 67.3. Both are well over the 48 px floor.

**B is viable and is the option if the run-out matters more than I have judged.**
It costs nothing in motion (identical step and turn to A), it keeps the rear
camera through the first two crossings, and it grows the later crossings to
58–63 px. Its costs are that the orbit does not complete inside the replay — the
film ends at bearing 62 rather than V19's 27, still turning at 0.86 °/frame —
and that it shows *fewer* racers than A during the run-out (0.22 against 0.31),
because it is moving toward a tighter lens.

**Do not ship B's first timing.** Any future retune must keep the 85–90 band out
of a crossing.

## Phone review, at 270×480

`docs/validation/sloped_race_v1/v221_finish/phone_sheet.png` is four candidates
× six instants at delivery scale. Read honestly:

1. **Can I see the finish approaching?** A, B and D: **yes** — at 19.65 s the
   deck and its checkerboard are in the upper left of the frame and growing. C:
   **no** — at 19.65 s it is still on the merge chase and the finish is not in
   shot at all. This is the clearest single difference on the sheet.
2. **Can I see the leading marbles?** All four: yes, at every instant.
3. **Can I see exactly which marble crosses first?** A: **yes** — at 20.850 the
   purple winner is at the deck mouth with the green second a clear distance
   back down the chute. C is more explicit still, because the marble is on an
   orange tape under a board that says FINISH.

Where A is weaker at phone scale is the **later** crossings: at 22.65 and 24.42
its marbles are 53 px on a bright checkerboard and take a moment to find, where
C's are 73 and 78 px against the tape. B recovers this — its later crossings are
58 to 63 px and the last two are under the FINISH board — which is the whole
argument for B over A and the reason it is not dismissed.

## Winner overlay: compatible, no retiming, one number worth raising

`tools/sloped_short.py` projects the ring through `presentation.screen_track`,
which reads whatever camera track it is handed — so the mark **reprojects
itself** and needs no change. Measured over its own window (replay 21.050 to
21.750, which is `WINNER_DELAY` 0.20 and `WINNER_SECONDS` 0.70):

| | frames in frame | x range | y range | marble radius | worst drift |
|---|---|---|---|---|---|
| A | 48/48 | 407–678 | 763–889 | 23.1–25.9 px | **15.6 px/frame** |
| B | 48/48 | 407–705 | 763–889 | 23.2–25.9 px | 15.6 px/frame |
| C | 48/48 | 646–977 | 1183–1574 | 36.1–41.9 px | 37.7 px/frame |

The mark is *steadier* under A — less than half the screen drift — and sits in
the upper middle of the frame rather than the lower right.

**The one thing integration must decide is the ring's size.**
`overlays.winner_ring` is drawn from the marble's projected radius, and under A
that is 23–26 px against V22's 36–42. The pulse will be about two thirds the
diameter. If that reads as weak, the fix is a floor on the radius passed to
`winner_ring`, in `tools/sloped_short.py` — **not** a change to
`sloped/overlays.py`, which is drawing exactly what it is asked for.

The ring window also falls inside the settle (the lens parks at 21.747), so the
mark opens on a camera that is still gently arriving, at about a third of the
step it came in with. That is why its drift is low rather than zero.

## From 6th to 1st

Not redesigned, and it does not need to be. `overlays.end_fact` draws at
`END_FACT_BASELINE = 1395` — the lower third. Under A the last crossings happen
between y 763 and 889 and the camera is parked, so the lower third of the frame
holds the approach chute and the ground, with nothing crossing it. The
composition is at least as available as the control's, and the camera under it
is not moving at all.

Under B the camera is still turning at the final frame, which is the weaker of
the two for text.

## What this prototype does not do

* It does not touch `sloped/cameras.py`, `sloped/presentation.py`,
  `sloped/v22.py`, `tools/sloped_short.py` or `tools/sloped_short_qc.py`.
* It does not change the physics, the seed, the replay, the map, the finish
  location, the ordering or the edit's last replay second. `EDIT_V22` is read,
  never written; the bookend lens candidate B eases onto is *read off* the
  solved control rather than retyped.
* It does not render the film. `--stage render` renders 6.45 s clips, re-timed
  by `finish_clip` so Godot walks the tail and nothing before it.

## Weaknesses

1. **One seed.** Everything here is seed 5432. The park is expressed relative to
   the finish line rather than to the pack, so it is seed-independent by
   construction — but the *split* is not: 18.900 was chosen because it is where
   this race's chase happens to be moving fastest. On another seed the split
   would have to be re-solved, and `sweep_split` is the tool for it.
2. **The split is inside the merge phase.** The branch cameras and the first
   0.483 s of the merge are untouched, and the rest of the merge phase is
   replaced. If "do not change the merge camera" was meant literally, this
   prototype fails it and there is no version of a final approach that does not.
3. **The rear camera loses the tail of the field**, structurally — see finding 1.
   The run-out share matches the control, but the *approach* shows 1.76 racers
   against 2.46.
4. **The FINISH board never reads under A.** See finding 3.
5. **`finish_lead` is a landmark metric, not a comprehension one.** It measures
   the crossing point's own projection, unobstructed, with a 90 px edge margin.
   It does not know whether a viewer recognises what they are looking at.
6. **Candidate B's orbit is unfinished when the replay ends.** It was timed for
   the gantry band, and the band is what it could be timed for.
7. **No audio, no overlays, no encode settings** are exercised. The proofs are
   silent Godot renders at CRF 18.
8. **The 4th and 5th finish 0.017 s apart** — one frame at 60. No camera makes
   that order legible; both are at the line in the same frame in every
   candidate, including the control.

## Files

| path | what |
|---|---|
| `sloped/v221_finish.py` | the park, the ratio band, the trapezoid orbit, `check_finish` |
| `tools/sloped_v221_finish.py` | solve, three sweeps, the metrics, the render, the phone sheet |
| `tests/test_sloped_v221_finish.py` | 22 tests |
| `docs/validation/sloped_race_v1/v221_finish/metrics.json` | the table above, as data |
| `docs/validation/sloped_race_v1/v221_finish/park_sweep.json` | 150 park poses |
| `docs/validation/sloped_race_v1/v221_finish/split_sweep.json` | 72 split/ratio/aim trials |
| `docs/validation/sloped_race_v1/v221_finish/orbit_sweep.json` | 33 orbit trials |
| `docs/validation/sloped_race_v1/v221_finish/phone_sheet.png` | 270×480, four candidates × six instants |

## Exact integration instructions

If A is accepted, integration is four edits and none of them is to a lens.

1. **Give the chase a final phase.** In `sloped/chase_camera.py`, the cleanest
   home for this is a new `ChasePhase`-like terminal stand, but the prototype
   deliberately did not put it there. The minimum change that keeps the shape is
   to import `sloped.v221_finish` from `sloped/v22.py` and make
   `build_race_track` return
   `v221_finish.build(chase_camera.build_chase(...), replay, machine, CANDIDATE)`
   with `CANDIDATE = Candidate(name="v221", split=18.900, park=Pose(bearing=180,
   radius=26, height=18, aim_ahead=0, aim_lift=1), ratio=2.0, aim_settle=1.2)`.
2. **Drop the finish window from the V22 edit.** `chase_camera._bookends` lifts
   the `finish` entry out of `EDITS["v22"]`; with a final phase the chase runs to
   the replay's own end and the bookend must not also be appended. Either pass
   `edit="v22_nofinish"` (a plan with the `finish` entry removed — `_v22_edit`
   already builds the plan programmatically, so this is one filter) or let
   `v221_finish.build` keep doing it, which is what it does now: it truncates the
   edit at the split and appends one `final` window. **The film's runtime does
   not change** — the last replay second is still 24.467 and the edit still
   tiles from 7.620.
3. **Re-solve the master.** `tools/sloped_v22.py --stage solve` then
   `--stage race`. The preview's handoff is unaffected: it takes
   `track["cuts"][0]["frames"][0]`, which is the start bookend and is untouched.
   `tools/sloped_v22.py --stage freeze` likewise.
4. **Consider a radius floor for the winner ring.** In `tools/sloped_short.py`,
   `overlays.winner_ring(x, y, radius, ...)` — clamp `radius` to at least ~34 px
   so the pulse keeps V22's weight. Decide this on the rendered Short, not on
   this prototype.

Things that need **no** change: `presentation.Clock` (the edit still tiles and
still has exactly one omission, in the start), the soundtrack (output times of
every window before the split are identical, and the finish window's output
start moves from 20.200 to 18.900 only in *which cut* covers it — the output
clock is unchanged because the windows still tile at slope one), `sloped_short`'s
end card, and `sloped_short_qc`.

The one number to re-check after integration is
`readability.continuity_report`'s boundary list: it should contain exactly one
measured jump, the 0.243 at `start → descent`, and no `finish` entry at all.
