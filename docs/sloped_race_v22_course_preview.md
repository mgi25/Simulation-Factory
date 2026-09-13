# V22 — the course preview

Status: **prototype, for review.** A camera and nothing else. No physics, no
course geometry, no lighting, no change to `sloped/cameras.py`,
`sloped/presentation.py`, `tools/sloped_short.py` or `tools/sloped_short_qc.py`,
and no Godot script added or changed. Seed 5432 is untouched; the race replay is
read and never rewritten.

    output/sloped_race_v1/course_preview_v22.mp4
    1080x1920, 60 fps, no audio, 120 frames = 2.000 s, 5.2 MiB

The brief: a pre-race course preview of the kind a party game puts in front of a
round, compressed to what a vertical Short can carry — begin at the finish,
travel backwards through the whole course past the landmarks the race will use,
arrive at the start, and settle into an elevated behind-the-racers viewpoint the
race camera can take over from.

## The move

**The camera faces down-course for the whole shot and travels up-course: a
reverse dolly.** That is the finding this prototype is built on, and it is
arithmetic rather than taste.

The obvious reading of "travel backwards through the course" is to fly up it
looking where you are going. On layout B that camera is unwatchable. Measured on
the drawn centreline, the plan heading of the course's sections runs

    sprint            68 deg
    between branches -19
    leg 3             41
    leg 2            -48
    leg 1             48
    launch            63

— about 350 degrees of accumulated yaw. A camera that takes its facing from the
course spends that in the two seconds the preview has, which is 175 degrees a
second of rotation.

Facing down-course while retreating up-course costs none of it. Three things
fall out for free:

* It **begins looking at the finish arena** rather than past it, because the
  arena is down-course of where the camera starts.
* Each landmark **enters at the bottom of the frame and recedes up it**, which
  is the one direction a 1080x1920 frame has to spare. `sloped/cameras.py` found
  the same thing for the race: looking along the channel puts the ribbon
  receding up the frame and the field in depth rather than in a line across the
  middle.
* It **arrives behind the start facing down the launch with no turn at all.** A
  camera that flew up the course looking forward would have to swing 180 degrees
  in the last half second to get there, and there is no way to spend 180 degrees
  in half a second that a viewer forgives.

The motion is very nearly anti-parallel to the gaze, so what the frame does is
open out rather than swing. Over the whole flight the lens travels **81.4 layout
units along its own sight line against 15.0 across it**.

## The corridor

The flight line is not the course. It is the centreline convolved with a
Gaussian fifty layout units wide, with both ends pinned back onto the start and
finish nodes so the shot still begins and ends over the right places. The aim
rides the same corridor a `lead` ahead of the camera.

`CORRIDOR_SIGMA` is the one number that trades how much the flight turns against
how far it strays from the track, and the trade is very one-sided:

    sigma   heading swing   mean stray   worst stray   length
       26        73.4 deg         3.85          9.59    106.7
       32        52.5            4.07         10.10    104.0
       40        35.3            4.31         10.52    102.5
       50        22.6            4.61         10.98    101.7
       64        12.2            4.94         11.50    101.3

Fifty-odd degrees of swing costs three quarters of a layout unit of stray. At 26
the residual of leg 1 and leg 2's zig-zag survived the blur as a 73-degree S
near the top of the course and the shot spent it in half a second — 2.6 degrees
of yaw a frame, against a pitch that never moved more than 0.38. At 50 the whole
flight is one curve.

Aiming at the **course** instead of the corridor was tried and is wrong twice:
the aim darts into every hairpin, and between the fork and the merge there are
two ribbons thirty-six units apart and the aim would have to pick one. On the
corridor it passes between the lobes, which is what a shot of a split has to
look at. `sloped/cameras.py` records the same fault for the race's own merge
shot, which held 1.86 racers of the 4.86 it had in frame.

## Three findings, each from a measurement

### The ground may not be in the flight path

The first solve took the lens height as `max(corridor, ground) + lift`, which is
right frame by frame and produces a path that wears the mountain's own shape.
The crest above the start moved the lens **3.7 layout units in one frame** and
put a 1.84-degree kink in the gaze; the dip beyond it cost 1.9 units of sideways
travel a frame.

So the corridor's own height is the base — smooth by construction — and the
ground reaches the shot only through `_solve_lift`, which measures the shortfall
per frame, dilates it over a window and blurs it. A correction becomes a swell
that begins before the obstruction and ends after it. Blurring alone sags at
exactly the peak the requirement is at; dilating first is what leaves the blur
headroom to spend.

The envelope's kernel is **truncated at the dilation width**, and that is what
makes it a guarantee. A Gaussian's natural reach is three sigma, so with sigma 9
over a dilation of 16 it reaches 27 samples either side and the output comes back
*under* the requirement at the middle of the plateau. A unit test caught that,
not a render.

### A flyover's smoothness is not one number

The shipped V21 race track, over all 1145 of its frames, moves the lens at most
0.504 layout units in a frame and turns the gaze at most 0.132 degrees. That is
a camera whose subject moves and which therefore barely does. A preview has to
cross 102 units of corridor in two seconds and cannot be held to it.

What it can be held to is the *shape* of the motion, so the step is resolved
into the frame's own axes — along the gaze (a dolly, which reads as the frame
opening and is not capped), up and down the frame (on a flyover this is the
reveal itself), and left and right (the one that reads as the world sliding
sideways). The angles are split the same way: a steady pitch with the yaw doing
the work is a pan, and a pan is what makes a viewer ill.

Resolved that way the first solve's "lateral 1.06 a frame" turned out to be
almost entirely *vertical* flow from a gaze depressed 48 degrees, and the fix
was not to slow the camera down but to stop looking so steeply down.

### The cut boundaries duplicated three frames

`sloped_race_scene._place_from_track` picks the first cut whose `to` is at or
after the wanted second, then indexes into that cut's rows from its own first
row's time. Both are float comparisons against a number written with six decimal
places, and the renderer's clock is `index / fps` at full precision. Frame 17 of
a 60 fps shot is 0.28333333; the cut's `to` was written 0.283333; so the frame
fell through into the next cut, indexed at zero, and was drawn with frame 18's
pose.

Rendered, that duplicated three frames of the 120 — 17 and 18, 47 and 48, 83 and
84 — each preceded by a step of exactly twice the usual size. Mean absolute
inter-frame difference at those pairs was **0.013 against a shot mean of 17.9**.
It reproduced byte for byte across independent renders of different windows,
which is what ruled out a GPU hiccup and pointed at the track.

Each cut now carries one row past its own last frame — the first row of the cut
after it — and its `to` is that row's time. Both readings are then right:
dither that keeps the frame in this cut finds the row it added, and dither that
pushes it into the next finds that cut's row zero, which is the same frame.
Seven duplicated rows in the whole track.

The production edit does not have this fault because its cut bounds are *station*
times, which land between frames rather than on them. A track cut by frame index
lands on them every time.

## What came out

    duration                1.983 s, 120 frames at 60 fps, fov 48 vertical
    opens at                ( 8.90, 25.09,  20.15) looking at (20.91,  5.71, 41.54)
    hands over at           (-32.09, 57.29, -52.22) looking at (-18.60, 41.05, -37.20)
    handoff pose            25.9 layout units out at 38.8 degrees of elevation

    step                    max 1.267   mean 0.847   layout units per frame
      sideways                  0.303   (bar 0.55)
      up and down the frame     0.592   (bar 1.30)
    gaze turn               max 0.541   mean 0.325   degrees per frame
      yaw                       0.764   (bar 1.00)
      pitch                     0.506   (bar 1.00)
      total over the shot      38.6 degrees
    aim step                max 1.316   layout units per frame

    sight line over ground  5.25 at worst   (needs 0.60)
    lens to any surface    13.55 at worst, nearest leg3   (needs 2.00)
    frame centre blocked    0 of 60 sampled frames
    gaze from vertical     41.2 degrees at worst   (needs 20)
    ribbon in frame         44.7% on average, 6.2% at worst
    corridor               101.7 units of a 185.3-unit course, straying 4.6
                           on average and 10.8 at worst

    rendered clip           no duplicate frames; the worst inter-frame
                            difference is 1.12 times its neighbours

Every landmark the brief names is in frame, and the gaze passes them in reverse
race order:

    finish     0.00 - 1.98 s   closest 38.8   17.3% of frame height
    merge      0.72 - 1.48     closest 57.2   11.8%
    branches   0.70 - 1.62     closest 47.8   14.1%
    fork       0.53 - 1.98     closest 31.4   21.4%
    obstacle   1.02 - 1.70     closest 47.0   14.3%
    turns      1.70 - 1.98     closest 68.9    9.8%
    mixer      1.28 - 1.98     closest 34.2   19.7%
    start      1.52 - 1.98     closest 27.4   24.6%

`turns` — leg 1's eastern apex — is the weakest of the eight at 9.8% of frame
height, and that is inherent to the move: it is the landmark furthest off the
corridor and the camera only gets up-course of it in the last third of the shot.

## How it is rendered

The preview is a camera, so it is rendered by the **shipped** `SlopedRaceRender.tscn`
driving the **shipped** `sloped_race_scene.gd`, with two files handed to it:

* `output/sloped_race_v1/preview/preview_cameras.json` — the camera track, in the
  format that scene already reads, one cut per landmark
* `output/sloped_race_v1/preview/preview_replay.json` — a **frozen replay**: the
  race's own frame zero repeated for the length of the preview, so the eight
  racers sit loaded in the start drum and every paddle, rotor and wheel is at
  rest

That is the whole of the integration. The course, the lighting and the V21
readability pass in frame are exactly the ones the race ships, because they are
the same scene. The frozen replay carries no digest, no summary and no events:
it is a pose, not a physical record, and a file that claimed to be one would
eventually be checked as one.

## Running it

    export GODOT_BIN=.../Godot_v4.7.2-stable_win64_console.exe
    python tools/sloped_course_preview.py solve      # no Godot needed
    python tools/sloped_course_preview.py all        # + stills, clip, qc, sheet

`solve` is the whole prototype: it writes the track, the report and the QC
verdict and needs nothing but Python. `--seconds`, `--fov`, `--sway`, `--lift`,
`--lead` and `--end-pose` retune it without editing the module; `at --at=1.98`
photographs any output second, which is how the handoff frame was judged.

Proof:

    docs/validation/sloped_race_v1/v22_preview/contact_sheet.png   8 landmark frames at phone size
    docs/validation/sloped_race_v1/v22_preview/flight_plan.png     plan of course, corridor, flight and gaze
    output/sloped_race_v1/course_preview_v22.mp4                   the clip
    output/sloped_race_v1/preview/preview_report.json              every number above

## For the integration session

* **The handoff pose is a knob.** `Preview.end_pose` takes the chase camera's own
  first `(position, aim)` and the last third of the flight eases onto it with a
  smootherstep, so the join has zero velocity at both ends and the solved path is
  not deflected where the blend begins. `check_preview` still applies, so a
  target that costs too much motion fails rather than ships.
  `--end-pose=px,py,pz,ax,ay,az`.
* **The default handoff is 25.9 units out at 38.8 degrees**, up-course of the
  start and looking down the launch. For comparison the shipped race's own
  `start` cut stands 25.2 units out at 16 degrees — but it is a *front*-quarter
  view, down-course of the machine looking back at the field. The two cannot be
  the same pose; a preview that ended on V21's `start` would have to turn 180
  degrees to get there.
* **The handoff cannot be a low angle.** Everywhere behind the start is uphill:
  the crest over the start rises 5.5 layout units and the western flank another
  17, and the lens has to stand `GROUND_GAP` over whichever it is on.
* **The track's times are output times** and its edit map is the identity, so it
  does not compose with an edit map of its own. Splicing the preview in front of
  the race means offsetting the race's output clock by the preview's duration,
  not merging the two `edit` arrays.
* **`sloped/course_preview.py` imports nothing from `sloped/cameras.py`.** They
  share only `sloped.terrain`, `sloped.sightlines` and `sloped.pathing`, so the
  two camera systems can be changed independently.
* **Nothing decides the Short's runtime here.** The preview is 1.983 s because
  the brief asked for 1.5 to 2.2; `--seconds` moves it and `check_preview` holds
  it in that band.
