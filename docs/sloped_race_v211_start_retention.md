# V21.1 — the start / retention pass

Status: **an edit of the locked V19 master. Nothing else.** No physics, no
re-simulation, no course geometry, no camera pose, no seed change, no Godot. The
replay's state digest is still
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6` and the
camera track rebuilt from the committed source is byte-identical to the one V19
shipped. What changed is **which 1065 of the master's 1150 frames are in the
film**.

    output/sloped_race_v1/real_race_v21.mp4          1080x1920, 60 fps, 1107 frames
                                                     18.450 s, AAC 48 kHz, 25.2 MiB
    output/sloped_race_v1/real_race_v21_visual.mp4   the same picture, no audio

`real_race_v19.mp4` and `real_race_v20.mp4` are untouched and still on disk.
`python tools/sloped_short.py --seed 5432 --edition v20` still builds V20.

## The problem was not the length, it was the order

V20 is 19.87 s and gives the viewer a marble to choose in the first 0.7 s. Then
it makes them wait. The floor did not open until **3.217 s**, the downhill lens
did not come on until **4.720 s**, and the first racer did not touch `leg1` — the
first run of the actual mountain — until **4.983 s**. A quarter of the film went
by before the thing the viewer was promised started, and they had already made
their only decision in the first second of it.

The start is not worthless: it is where the fairness is shown. Eight marbles are
released from eight bays into a drum, tumbled, and dropped through a trapdoor
onto the course, and a viewer who does not see that has no reason to believe the
result is not scripted. But *showing* it and *dwelling in it* are different, and
the measurements say the dwelling is nearly all of it.

**The mixing is over long before the mechanism is.** Read off the replay:

    replay  mean speed  max speed  spread in x
    0.20      0.08        0.38        7.08     held on the line
    0.50      4.31        4.48        7.02     the gates have opened
    0.80      9.35       16.56        5.63     pouring out, closing up
    1.10     10.36       16.48        4.66     the tumble, at its fastest
    1.50      4.25        6.78        6.25     landed, drifting
    2.10      0.69        1.39        7.62     parked
    3.00      0.68        1.43        7.61     parked
    5.00      0.49        0.97        7.21     parked
    6.00      0.43        0.93        6.20     parked
    6.20      7.27       14.68        5.85     the floor has opened

The eight are *randomised between replay 0.32 and 1.30*. After 2.1 s they crawl
at a fifteenth of their tumbling speed while the rotor and the paddle wheels turn
above them — the machine is busy, the race is not. V20 spent **2.30 s** of screen
time on the parked half and **1.10 s** on the half that does the mixing.

## What V21.1 does

Eighty-five whole frames come out of the middle of the start shot, and V20's two
start windows become one. Master frame 48 is replay 1.000; master frame 134 is
replay 5.833333; both are on the same `start` lens, so the join is a skip inside
one shot rather than a change of viewpoint — the same argument V18 made for its
own cut, applied one window earlier and one second harder.

    output       replay          what is on screen
    0.000-0.700  0.200 held      PICK ONE over the eight in their bays
    0.700-1.500  0.200-1.000     the gates open at 0.817 and the eight pour
                                 out and tumble together
    1.500        cut             4.833 s of drum omitted, one whoosh
    1.517-3.303  5.833-7.620     the settled field, the floor drops at 1.800,
                                 and they are away
    3.303-       7.620-          the downhill, unchanged from here to the end

Everything after the cut is the same footage it always was, 85 frames earlier.

    marker                    V20       V21.1     moved
    PICK ONE                  0.10-0.80 0.10-0.80  -
    gates first move          0.817     0.817      -
    the cut                   2.800     1.517     1.283 s earlier
    the floor opens           3.217     1.800     1.417 s earlier
    the downhill lens         4.720     3.303     1.417 s earlier
    first racer onto leg1     4.983     3.567     1.417 s earlier
    all eight onto leg1       6.017     4.600     1.417 s earlier
    the winner crosses       17.100    15.683     1.417 s earlier
    runtime                  19.867    18.450     1.417 s shorter

`docs/validation/sloped_race_v1/v21_1_start/opening_v20_vs_v21_1.png` is the
first 4.8 s of both, a column every 0.4 s, captioned with the replay second on
screen. At 4.8 s V20 has just arrived at replay 7.70 and is taking its first look
down the mountain; V21.1 is at 9.12 and the field is strung out along the first
bend.

## Why the floor is the mark, not the lens

"When does the race start" has three defensible answers and they are 1.80, 3.30
and 3.57 s. The one this pass optimises is **the floor opening at 1.80 s**, and
the replay says why: the field goes from 0.43 wu/s to 22.00 wu/s in the two
tenths after the trapdoor moves and never stops descending afterwards. `leg1` is
a label the course applies at replay 7.883; falling, accelerating and running
downhill start at 6.117. The camera change at 3.303 is a camera change.

**This is also the floor of what is possible without lying.** The release runs
6.117 to 6.300 and the drop and the run-out to the first downhill lens take until
7.620, so the second window cannot be shorter than 1.79 s without cutting into
the release itself or into the field's flight — which is the one part of the
start the brief asks to keep legible. Given the 0.70 s hold, the 0.80 s of mixing
and that 1.79 s, the earliest honest release is about 1.80 s and the earliest
honest downhill lens about 3.30 s. Getting the *lens* to 2.0 s would mean cutting
the marbles mid-air, and it was not done.

## The rules this had to keep, and how each is held

An omission is the one edit that can quietly stop being honest, so each rule is
checked by something rather than asserted.

* **No speed change.** Every window has slope one, checked to 2e-6 per window and
  end to end: take the two jumps out of the span the film covers and what is left
  is exactly one frame of replay per frame of film.
* **No fabricated frames.** `presentation.omit_frames` only ever *removes* whole
  frames; ffmpeg's `select` decides on the master's own frame number and
  `setpts=N/FRAME_RATE/TB` closes the gap. Nothing is interpolated and nothing is
  blended.
* **No repeats and no rewinds.** The replay instant shown steps forwards at every
  one of the film's 1064 frame boundaries, by exactly 1/60 at all but two of
  them. `omit_frames` refuses a cut whose far side is not later than its near
  side. `mpdecimate` on the delivered file keeps 1081 of 1107 frames — the only
  collapse is the held opening, which is meant to be one picture.
* **Exact replay mapping.** Every surviving frame was checked against V19's own
  map, frame for frame: 1065 of 1065 show the instant they always showed. The
  join was then checked in the *pixels* — the delivered frame 90 is master frame
  48 and frame 91 is master frame 134, each differing only by re-encode noise
  (mean 1.09 and 0.87 of 255), while the two of them differ from each other in
  56% of the frame.
* **The winner, the seed, the course, the physics.** Untouched. The film still
  carries six of the eight crossings and marble 5 still wins by 0.283 s.

### Two details that had to be got right

**The replay edges of the map are rounded to six decimals and the output edges
are not**, and the asymmetry is deliberate. `Clock.at` is asked about replay
instants that come out of the replay file, where every `t` is written to six
decimals — an edge carrying a sixteen-digit `5.833333333…` excludes the very
frame it names, and 44 frames of the film silently fell off the map the first
time. `Clock.replay_at` is asked about output seconds that are exact `frame/fps`
divisions, so an edge rounded *up* past one excludes that frame instead. Each
edge is now written in the units it is compared against.

**V19's own cut reports 0.85 s and steps 0.866667 s.** Its `split` window opens
at replay 15.35 but the first frame of it lands at 15.366667, so the map's figure
is a sixtieth short of the gap the pictures make. V21.1's cut is written from the
frames that survived, so its two figures agree. The test states both rather than
averaging them.

## Sound

Nothing in `audio/marble.py` changed. Everything it places is derived from the
clock, so the whole soundtrack moved with the picture:

* the tension run-up still ends on the gates at **0.817**;
* the trapdoor cue is on the frame `start.panel` first moves, now **1.800**;
* the whooshes are the edit map's own omissions — **4.833 s at 1.517** and the
  unchanged **0.850 s at 10.183**. The first is bigger than V20's and the cue is
  scaled to how much went, so the larger skip is the louder mark;
* 210 contacts survive the rationing rather than V20's 213: three of them were in
  the omitted drum and are not in the film, so they make no sound.

The mix behaves as designed on the new length — peak in −10.62 dBFS, compressor
5.15 dB, out −1.62 dBFS, **limiter idle**, integrated −14.00 LUFS, true peak
−1.58 dBTP. The crossing hierarchy holds: #1 −1.63, #4/#5 −2.55, #2 −2.73, #3
−2.83, #6 −6.04, and the winner is 7.5 dB over a typical mid-race moment.

## Picture

The three marks are unchanged and all three are placed through the clock, so
none of them needed touching:

* **PICK ONE** 0.10–0.80, fading from 0.62. It is still gone before the gates
  first move at 0.817 — the hold is the choosing time and the hold did not move.
* **The ring on the winner** 15.883–16.583, still starting 0.20 s after the
  crossing and still ending 0.89 s before the fourth and fifth arrive together.
* **FROM 6TH → 1ST** 17.800–18.450, over exactly the footage it covered in V20.

## QC

`tools/sloped_short_qc.py` takes an edition and derives the frame count from that
edition's clock rather than carrying a typed 1192 around. Nineteen checks on
`real_race_v21.mp4`, all passing: format, 1107 frames, runtime inside 18.2–18.7,
stream layout, true peak, the crossing hierarchy, the idle limiter, no black
frames, `mpdecimate`, the hold as a still picture, the three overlay windows
against measured marble positions, and the release inside the first two seconds.

The mid-race reference the winner is compared against is now taken between the
`long` and `split` windows through the clock rather than at a fixed 4–11 s, so
both editions are measured against the same footage.

## Tests

`tests/test_sloped_retention.py`, 25 tests, all passing. `tests/test_sloped_
short.py`'s 22 are unchanged and still pass, which is the point: V20 is still
exactly V20.

The suite has one failure that is not this pass — `tests/test_sloped_cameras.py::
test_the_track_has_no_findings`, from a concurrent `MAX_CAMERA_STEP` check being
added to `sloped/cameras.py` in the same working tree on another branch.

## What was not changed

Physics, PyBullet, seed 5432, the replay, the course, the start module, the fork,
the merge, every camera pose, the edit map's later windows, the winner, the
audio design, the overlays, `real_race_v19.mp4` and `real_race_v20.mp4`.
