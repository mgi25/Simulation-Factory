# V22 — the pacing pass

Status: **a proposal and four proof clips. Nothing is delivered and nothing in
the production path is touched.** No physics, no re-simulation, no course
geometry, no camera pose, no seed change, no Godot. `sloped/cameras.py`,
`sloped/presentation.py`, `tools/sloped_short.py` and `tools/sloped_short_qc.py`
are read and never written. The replay is still
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6` and marble 5
still wins by 0.283 s.

    sloped/v22_timeline.py            the model
    tools/sloped_v22_pacing.py        analyse / candidates / clips / sheet / recommend
    tests/test_sloped_v22_pacing.py   59 tests
    exports/v22_pacing/*.mp4          four labelled proof clips, V21's picture

The brief's instinct is right, and the measurement says it is right in one more
place than the brief looked.

## "Too fast" is not an editing instruction, so this pass made one

V21 is 18.45 s and it feels rushed. That is a verdict, not a cut list, and the
way it turns into one here is a single question asked of every quarter-second of
the replay: **is anything happening?**

The answer is `churn` — how far the eight marbles travel, per marble, per second
of replay. Path length, not displacement between the ends, because a marble
rattling in a pocket comes back to where it started and a difference of endpoints
would score the spinner trap as dead air. And displacement rather than speed,
because a marble falling at 40 wu/s and a marble pinned against a turning blade at
3 wu/s are completely different pictures and speed cannot tell them apart.

Measured that way the film sorts itself into two populations with **nothing in
between**:

    the parked drum, replay 2.30-5.70          churn 0.43 - 1.64
    every 0.25 s the film keeps, 0.20-23.60    churn 2.33 - 9.28 and up

A factor of 1.4 between the top of one and the bottom of the other, and not a
single slice in the gap. `CHURN_FLOOR = 2.00` sits in it, and anything from about
1.7 to 2.3 would pick out exactly the same frames. That is the whole argument of
this pass: the criterion was found, not chosen.

## Run V21's own omissions past it and two of the three come back wrong

    replay           churn  hits  verdict
    1.000 - 2.300     4.11     8  LIVE. V21.1 cut it.
    2.300 - 5.700     1.17     0  DEAD. Correctly cut.
    14.500 - 15.350   7.01     0  LIVE. V19 cut it, and nothing since has looked.
    23.600 - 24.467  12.19     1  LIVE. Never in any edition; the film just stops.

**The start.** V21.1 took 85 frames out of the middle of the drum and it took one
frame too many by a wide margin. The eight are randomised between replay 0.32 and
1.30; V21 cuts at **1.000**, which is *inside the tumble*. It throws away eight of
the drum's fifteen marble-on-marble contacts, and among them the hardest one in
the whole start — 9.08 wu/s at replay 1.1875, marbles 0 and 3. The film keeps the
seven weakest hits and cuts the peak.

**The spinner exit.** This is the one nobody asked about, and it is worse. The
map has always skipped replay 14.500–15.350, and its four quarters score **5.03,
6.80, 8.29, 9.28** — rising monotonically, the highest-churn stretch the film
omits anywhere. It is the field accelerating out of the spinner trap after 2.5 s
of being held, and it contains marble 7 entering `leg3` at 14.9958: **the leader's
escape**. The film spends two and a half seconds watching the machine hold the
whole field, and then cuts away one frame before the first marble gets out.

**The finish.** The film ends at replay 23.600, which is 0.100 s after the sixth
crossing and while two marbles are still running at speed. Churn over the
0.867 s that would complete the race is 10.8–13.0 — higher than anything inside
the finish window itself.

So the correction is not "make the film longer". It is **put the omission where
the machine is idle**, and that is one place, not three.

## The second reason to restore the mixing, which nobody asked for

An omission is visible in proportion to how far things move across it. Measure
the mean distance each marble teleports at the start join:

    cut at replay   mean jump   worst   the field is 6.4 wu wide
    1.000  (V21)      3.76 wu   6.57    more than half the drum
    1.900  (A)        1.05 wu   2.32
    2.100  (B)        1.00 wu   2.07
    2.300  (C)        1.00 wu   2.17

By replay 1.9 the eight have found the arrangement they then hold all the way to
5.83, so a join made there barely moves them. **Restoring the mixing does not buy
a more obvious cut. It buys a less obvious one**, and V21 put its cut at the one
instant in the drum where the field is least reconcilable across it.

## The candidates

The start is one dial. Master frame `f` of the first window shows replay
`0.200 + f/60`, so a candidate is named by the frame it stops on. All four also
drop master frames 127–133 — the head of the second start window, the field
parked before the floor opens — which is V21.1's trim and is right at every
setting.

    key  stops on  replay  drop        frames  runtime   drum   live   hits   jump  onmove
    v21        48   1.000  (49, 133)     1107   18.450  0.800  0.683   7/15   3.76   10.40
    a         102   1.900  (103, 133)    1161   19.350  1.700  1.583  13/15   1.05    2.72
    b         114   2.100  (115, 133)    1173   19.550  1.900  1.783  15/15   1.00    1.51
    c         126   2.300  (127, 133)    1185   19.750  2.100  1.983  15/15   1.00    1.40

`drum` is the start window on screen; `live` is the part after the gates first
move at replay 0.3167. `onmove` is churn over the last 0.1 s before the cut.

**There is no candidate D, and 2.5 s of mixing does not exist.** It would run to
replay 2.817. The drum's last contact is at **2.0125**, the camera track stops at
2.300, and every quarter from 2.300 to 5.700 scores under 1.64. The extra 0.517 s
is footage that was never rendered *and* shows eight marbles crawling. The dial's
useful range ends at C and — see below — its useful setting is short of it.

## Recommended: A, plus both restorations

Not the longest, and here is the argument for stopping where it stops.

**Two criteria pull against each other at the cut, and only A satisfies both.**
An omission reads as a *skip* if the field is still moving when it happens; cut a
settling shot and the viewer's last impression is that the machine stopped, which
is the one thing the whoosh then contradicts. But cut while the field is *flying*
and the far side cannot be reconciled with the near one, and the skip reads as a
jump cut instead. So the cut wants churn above the floor **and** a small jump:

    V21   onmove 10.40   jump 3.76   cut mid-tumble: a jump cut
    A     onmove  2.72   jump 1.05   moving, and the far side matches
    B     onmove  1.51   jump 1.00   the field has already settled
    C     onmove  1.40   jump 1.00   more so

**A keeps all the mixing there is.** Its cut is the frame churn falls through the
floor. It retains 1.583 s of live mixing against V21's 0.683 — **2.3 times** —
and 13 of the 15 drum contacts including the 9.08 peak. The two it drops are
3.89 and 5.55 wu/s, the weakest in the drum, and both land after the field has
slowed below the floor.

**What B and C buy is not mixing.** B's extra 0.2 s buys those two weak knocks
among a decelerating field. C's further 0.2 s buys nothing at all: zero contacts,
four quarters scoring 1.52, 1.82, 1.77, 1.02. And C is 19.750 s against V20's
19.867 — it is a near-complete undo of V21.1, whose diagnosis of V20 (the viewer
waits until 3.217 s for the floor) was correct and still is.

The contact sheet says the same thing in pictures. In
`docs/validation/sloped_race_v1/v22_pacing/candidates_opening.png`, read across
the 2.8 s column: A and B are already on the settled field with the floor about
to drop, and C is still in the drum showing a **stopped** group. C's last drum
frame undercuts the impression that mixing is what just happened.

### The timeline

    #  lens      replay from   replay to   seconds   note
    0  start        0.200000    1.900000     1.700   the dial: master frame 102
       -- omit 1.900000 -> 5.833333, 3.933 s of parked drum, one whoosh --
    1  start        5.833333    7.620000     1.787
    2  descent      7.620000    8.620000     1.000
    3  long         8.620000    9.800000     1.180
    4  hairpin      9.800000   10.800000     1.000
    5  straight    10.800000   12.000000     1.200
    6  obstacle    12.000000   15.350000     3.350   +0.850 RESTORED, needs a render
    7  split       15.350000   17.670000     2.320
    8  branch      17.670000   19.070000     1.400
    9  merge       19.070000   20.200000     1.130
    10 finish      20.200000   24.467000     4.267   +0.867 RESTORED, needs a render
       hold                                  0.700   the opening frame, under PICK ONE

    replay covered  20.3337 s
    picture         1263 frames = 21.050 s
    + preview 1.5   22.550 s
    + preview 1.85  22.900 s
    + preview 2.2   23.250 s

**The brief's 21–25 s window is hit without aiming at it.** Nothing above was
sized to a runtime: the start stops where churn stops, the two restorations are
the two live stretches the film omits, and 22.9 s is what those decisions add up
to.

### Budgeting for the preview

The preview is 1.5–2.2 s and it lands in front of everything, so the front of the
film becomes

    preview 1.5-2.2  the course, top to bottom
    0.70             the hold, PICK ONE over the eight in their bays
    0.117            still on the line
    1.583            the gates open and the eight tumble
    the cut          3.933 s of parked drum, one whoosh
    0.283            the settled field
    the floor opens  at 2.700 + the preview, so 4.20-4.90

That is **later than V20's 3.217**, and it is worth saying plainly rather than
hiding. The defence is that it is not the same wait: V20's four seconds were
2.30 s of a parked drum after the viewer's only decision was already made, and
these are a course preview the viewer has not seen followed by live mixing. There
is no idle stretch in front of the floor at all. But it is the one number in this
proposal that gets worse, and if it measures badly in the cut, **the hold is the
place to take it out of** — 0.70 s of still frame is generous once a 1.85 s
preview has already shown the viewer what they are choosing between. That is an
integration call, not one this pass should make.

## Processing time: the beats, and which ones V21 breaks

Approach, contact, exit for everything the machine does, mapped onto V21's clock.
A beat whose **exit** is missing is one the viewer sees happen and never sees the
result of, and that is the specific failure here.

    beat            approach   contact      exit
    line-up            0.700     0.817     0.817
    gates              0.817     1.120     1.120
    tumble             1.120       cut       cut   <-- V21 cuts mid-tumble
    settle               cut       cut       cut   <-- gone entirely
    parked               cut       cut       cut       correctly, and only this one
    trapdoor           1.583     1.800     1.983
    the drop           1.800     2.554     3.303
    run-out            2.571     3.383     3.746
    first descent      3.303     4.303     5.483
    hairpin            5.483     6.083     6.483
    obstacle           6.483     7.983    10.183
    the trap           7.983     9.083    10.083
    the escape        10.083       cut    12.887   <-- the leader's escape, cut
    the fork          11.133    12.683    14.183
    branch race       12.503    13.903    14.200
    the merge         14.200    14.900    15.554
    final sprint      14.900    15.683    15.683
    the crossings     15.683    18.333       cut   <-- 7th and 8th are not in it

Five beats are incomplete and exactly one of them should be: `parked` is the
3.4 s of idle drum, and cutting it whole is the film's one correct omission. The
other four are the failure. The recommended timeline fixes all four — the tumble
and the settle come back with the start dial, the escape with the obstacle
restoration, the crossings with the finish one.

## Map size: the course is not short, the film is short of it

The brief suspects the ~237-unit course is adequate and the problem is
presentation. **Confirmed, with one correction to how the compression is
distributed.**

    the course, as locked          237 layout units of channel = 415.8 wu
    the winner's racing path       329.4 wu (187.8 layout units), launch to line
    the winner's racing time       12.788 s at 25.8 wu/s mean
    of which V21 puts on screen    11.938 s = 93.4%
    omitted inside the race        0.850 s - the 14.500 skip, and that is all
    beats in the racing leg        9, one every 1.42 s of replay

**The body of the film is not compressed.** From the first downhill lens to the
last crossing the race runs at 93.4% of real time, and the only 6.6% missing is
the one skip this pass wants back — after which it is 100%. Between `descent` and
`finish` there is no 0.25 s slice anywhere that falls below churn 2.33, which is
to say **there is nothing in the body of this film that could be trimmed even if
somebody wanted to.** A course that delivers a beat every 1.42 s for 12.8 s is
not a short course.

The compression is entirely at the front. Of the 7.62 s of replay before the
first downhill lens, V21 shows **1.787 s** — and 3.4 s of what it drops genuinely
deserves dropping. The film is short of the course in exactly two places, and
both are named above.

### What is *not* a map problem but is still worth a camera session's attention

V21 runs **11 shots in 18.45 s, a mean of 1.68 s**, and five of them are 1.25 s
or shorter: `descent` 1.00, `hairpin` 1.00, `merge` 1.13, `long` 1.18,
`straight` 1.20. The machine produces a beat every 1.42 s and the camera changes
every 1.68 s, so the two rates are close enough that events and lens changes
collide rather than nest. Two collide badly:

* the **obstacle** contact storm runs replay 11.25–12.30 and the lens changes at
  **12.000**, mid-impact — the 42.4 and 35.1 wu/s hits are on the `straight` lens
  and their result is on the `obstacle` one;
* the **merge** runs 19.37–20.58 and the lens changes at **20.200**, again
  mid-event.

This pass does not touch camera definitions and makes no proposal about them.
It is recorded here because `v22-chase-camera` is solving that map and these are
two boundaries worth moving while it does. **A longer timeline does not fix a
shot that changes in the middle of the thing it is showing.**

## Honesty

The rules are V21.1's and they are checked rather than asserted, by
`sloped.v22_timeline.verify` and by 59 tests.

* **No speed change.** Every window runs one second of replay per second of film,
  checked to 2e-6 per window on every candidate.
* **No fabricated frames.** `presentation.omit_frames` only ever removes whole
  frames; ffmpeg's `select` decides on the master's own frame number and
  `setpts=N/FRAME_RATE/TB` closes the gap. Nothing is interpolated, blended, sped
  up or slowed down.
* **No repeats and no rewinds.** The replay instant steps strictly forwards at
  every frame boundary of every candidate, by exactly 1/60 at all but the two
  omissions.
* **Exact frame arithmetic.** Each candidate is named by the master frame it stops
  on and the clock's window edge is checked against `0.200 + f/60`.
* **Checked in the pixels, not just the arithmetic.** In the delivered
  `v22_pacing_b.mp4`, clip frames 155–158 were measured against master frames
  113, 114, 134, 135: each matches its intended frame to a mean of **1.25–1.39**
  of 255 below the label banner, while the two sides of the join differ from each
  other by **38.6** and in 94.8% of pixels. The cut is exactly where the clock
  says and nowhere else.
* **Nothing promised that cannot be shown.** The two restorations are replay the
  camera track never covered. They are not in the proof clips, the clips do not
  pretend otherwise, and a test asserts that neither span is on the master's map.

## The proof clips

    exports/v22_pacing/v22_pacing_v21.mp4   1107 frames  18.450 s   the baseline
    exports/v22_pacing/v22_pacing_a.mp4     1161 frames  19.350 s   RECOMMENDED
    exports/v22_pacing/v22_pacing_b.mp4     1173 frames  19.550 s
    exports/v22_pacing/v22_pacing_c.mp4     1185 frames  19.750 s

Each is 1080x1920 at 60 fps, silent, and carries a burnt-in label giving the
candidate, the runtime, the mixing retained and the contact count, plus the line
**"V21 picture — timing only, not a delivery"**. They use the V21 camera master
deliberately: this pass is judging how long things last, not how they look, and
holding the picture still is what makes the timing answerable. **Neither
restoration is in them** — both clips and both restorations are additive, so what
a clip shows is the start dial and nothing else.

Contact sheet: `docs/validation/sloped_race_v1/v22_pacing/candidates_opening.png`
— all four openings, a column every 0.4 s for 5.2 s, each captioned with the
replay instant on screen.

## Sound

Nothing in `audio/marble.py` needs editing, and this pass did not open it. Every
cue it places is derived from the clock it is handed, so a new timeline moves the
whole soundtrack with the picture. What an integrator should expect to *measure*
afterwards, before the preview is added:

    0.817   the tension run-up ends on the gates      unchanged
    2.417   the whoosh                                was 1.517, and is now
                                                      3.933 s rather than 4.833
    2.700   the trapdoor, on start.panel's own frame  was 1.800
    17.433  the winner accent                         was 15.683

Three consequences worth flagging now:

* **V22 carries one whoosh, not two.** V21's second whoosh at output 10.183 marks
  the 0.850 s skip at replay 14.500. That skip is *restored*, not moved, so the
  cue has nothing to mark and should go. A whoosh over continuous footage is the
  one cue that would make the film sound like it is hiding something it is not.
* **The impact cues gain the drum's peak.** V21 rations contacts and three of the
  drum's hits were in omitted footage, so they made no sound. Under A, thirteen
  of fifteen are in the film including the 9.08 — the loudest thing in the start
  before the trapdoor.
* **Everything after replay 14.500 lands 0.850 s later** than the proof clips
  show it, because the restoration is in front of it. The winner accent moves from
  16.583 in the clip to 17.433 in the finished timeline, plus the preview.

Final audio is an integration task and none of it was designed here.

## Tests

`tests/test_sloped_v22_pacing.py`, **59 tests, all passing**. The suite pins the
frame arithmetic, monotonic replay time, the absence of repeats and rewinds, the
slope, the omission boundaries, event inclusion measured off the replay rather
than asserted, the tie-break, and — the one that matters most — that
`CHURN_FLOOR` still sits in a gap with no population in it. If new footage ever
lands between the parked drum and everything else, the criterion stops being
defensible and the suite says so.

`tests/test_sloped_retention.py` (25) and `tests/test_sloped_short.py` (22) are
untouched and still pass, which is the point: V20 is still V20 and V21 is still
V21. The wider sloped suite is 665 passed, 3 skipped.

## For the V22 integration

1. **The start dial is `(103, 133)`** against the V21 master's frame numbering,
   or equivalently "window 0 ends at replay 1.900000". Against a re-rendered V22
   master it is a map edge, not a frame cut — `sloped/v22_timeline.CANDIDATES`
   carries both readings.
2. **Two windows need extending and therefore re-solving**: `obstacle` to replay
   15.350 and `finish` to 24.467. Both are camera work and neither was done here.
   Extending `finish` means the FINISH sign's 40° elevation floor applies over
   0.867 s more of footage than V19 solved for.
3. **Drop the second whoosh.** With `obstacle` extended there is no omission at
   replay 14.500 for it to mark.
4. **The preview goes in front of the hold**, and if the front measures slow, the
   0.70 s hold is the place to take it out of rather than the mixing.
5. **The camera map's two mid-event boundaries** (replay 12.000 and 20.200) are
   worth moving while `v22-chase-camera` is re-solving anyway. Not this pass's
   call, but this pass's measurement.
6. `python tools/sloped_v22_pacing.py --stage recommend` prints the whole map,
   the frame arithmetic and the cue positions, so none of the above has to be
   retyped.

## What was not changed

Physics, PyBullet, seed 5432, the replay, the course, the start module, the fork,
the merge, every camera pose, the winner, `sloped/cameras.py`,
`sloped/presentation.py`, `tools/sloped_short.py`, `tools/sloped_short_qc.py`,
`audio/marble.py`, the overlays, and every delivered film from V19 to V21.
