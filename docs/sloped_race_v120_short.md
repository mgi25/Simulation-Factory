# V20 — the Short

Status: **presentation and audio over the locked V19 master.** No physics, no
course geometry, no re-simulation, no camera. Godot is never opened. V19 is an
*input*: the film is V19's first frame held for 42 frames, three overlays, and a
soundtrack synthesised from the same replay the pictures came from.

    output/sloped_race_v1/real_race_v20.mp4          1080x1920, 60 fps, 1192 frames
                                                     19.867 s, AAC 48 kHz, 26.9 MiB
    output/sloped_race_v1/real_race_v20_visual.mp4   the same picture, no audio

V19 is untouched and still on disk.

## The clock

Three clocks meet in `sloped.presentation.Clock`: the replay's 45 seconds, the
edit's 19.15 s of it in eleven windows, and V20's held opening. Everything —
every impact, both releases, both whooshes, all six crossings, all three
overlays — is placed through it, so nothing is ever positioned by hand.

    replay 0.317  gates open            output 0.817
    replay 2.30 -> 5.70  (3.40 s cut)   output 2.800
    replay 6.117  trapdoor opens        output 3.217
    replay 14.50 -> 15.35 (0.85 s cut)  output 11.600
    replay 16.300 first orange commit   output 12.550
    replay 16.767 first blue commit     output 13.017
    replay 20.850 winner crosses        output 17.100
    replay 21.133 second, +0.283 s      output 17.383
    replay 22.633/22.650 fourth/fifth   output 18.883/18.900
    replay 23.500 sixth                 output 19.750

**The hold is 42 frames, not 0.70 seconds.** A fractional hold makes `tpad`
round somewhere the code cannot see. 42 at 60 fps is exactly 0.70 s, the audio
is built to the same integer, and the file is 1192 frames — which the QC counts
rather than assumes.

**The master is 1150 frames, not 19.15 s.** `build_track` reports 19.15 and the
renderer walks frames 0 to `round(19.15 * 60)` inclusive, which is 19.1667 s.
Taking the nominal figure makes the soundtrack one frame shorter than the
picture.

## Sound

Every sample is synthesised in `audio/marble.py` from `audio.synthesis` —
oscillators, envelopes, filters and a seeded noise source. No samples, no loops,
no packs, no licensed music. The Short carries nobody's rights but ours.

### An impact is a contact impulse, not a change of velocity

The naive reading of a replay frame is that a marble whose velocity jumped hit
something. The distribution refutes it: the 90th percentile of `|dv|` over
21 600 marble-frames is **4.088**, and gravity over one 60 Hz frame is
245.25 / 60 = **4.0875**. Nine tenths of the "impacts" are marbles falling.

Removing gravity does not filter `dv`, it changes what is being measured — to
the impulse a surface applied — and that settles every threshold:

* **free fall** touches nothing and scores near zero, however fast it is going;
* **resting or rolling** is being held up, so it scores its own weight, 4.0875,
  which is why that is the median of the whole signal;
* an **impact** scores the impulse above that, so the floor of 11 wu/s is "about
  two and a half times the marble's own weight".

### Texture is not events

At a floor of 6 wu/s this race has **1594 contacts, 83 a second** — a cradle
correcting a marble a hundred times a second. A cue on each is the arcade
gunfire the brief forbids. So contacts are rationed by *isolation*, not
loudness: the 11 wu/s floor, then one cue per marble per 0.11 s keeping the
loudest, then at most two anywhere in any 0.05 s. **213 contacts survive, 11 a
second**, peaking at 25 in the busiest second and zero in the quiet ones. The
rest of the signal is not discarded — everything under the floor is summed per
frame and drives the *rattle* on the rolling bed, so the texture is still the
machine's own.

### The mix, and the mistake that shaped it

    voice              level          placed by
    winner crossing    reference      the finish_line event
    fourth/fifth       -3.0 dB        crossings within 0.20 s of each other
    other crossings    -6.5 dB
    trapdoor           -4.0 dB        `start.panel` actuators first moving
    gate               -7.0 dB        `start.paddle` actuators first moving
    whoosh             -10.0 dB       each omission in the edit map
    split              -11.0 dB       first commitment to each route
    loudest impact     -12.0 dB       contact impulse
    rolling bed        -21.0 dB RMS   recorded speed
    music              -19.0 dB RMS
    ambience           -31.0 dB RMS

The first version set the winner at −2.5 dBFS, which is a sensible level for the
loudest thing in a film until a bed and two hundred contacts go underneath it.
The sum arrived at **+0.98 dBFS**, the limiter pulled 2.3 dB out, and every
accent in the finish came out at exactly **−1.31 dBFS**: the winner, second
place and the dead heat all identical. A limiter working that hard is a machine
for removing the difference between loud things, and the finish is where those
differences are the point.

So the whole budget drops by 9 dB, the limiter has nothing to catch, and one
`trim` puts the peak on the ceiling with every relationship intact. Bus
compression (2.2:1, soft knee, look-ahead) then buys back the loudness:

    peak into the master  -10.37 dBFS      compressor  5.38 dB
    peak out               -1.37 dBFS      limiter     idle
    integrated            -14.06 LUFS      true peak  -1.31 dBTP
    crossings   #1 -1.39   #4/#5 -2.42   #2 -2.64   #3 -2.85   #6 -5.87

The winner's crossing is the loudest instant in the film, 7.7 dB over a typical
mid-race moment.

### Two whooshes, and what they mark

A whoosh marks **omitted time**, not a change of lens. This film omits time
twice — 3.40 s of mixing at output 2.80 and 0.85 s at 11.60 — and the cue is
scaled to how much was dropped. The 2.80 one is the one the brief asks to make
legible, because the lens is the same on both sides of it and without a cue it
reads as a glitch. Ordinary camera cuts get nothing: there is nothing to
explain.

### The split

One cue, placed twice — at the first commitment to orange (12.550) and the first
to blue (13.017) — identical waveform, identical level, panned only by where
each marble is on the frame. There is no arrangement of two identical sounds
that favours one, which is the cheapest possible guarantee of the brief's "do
not make one branch sound like the scripted winner".

## Picture

Three marks and nothing else. No HUD, no leaderboard, no progress bar, no
caption under the race.

**PICK ONE**, 0.00–0.80 s, fading out at 0.62. The eight racers sit at y 831–887
on the first frame, so the mark is at y 247–436, above the START sign and clear
of the field. It is gone before the gates first move at 0.817.

**A ring on the winner**, 17.300–18.000 s. It starts 0.20 s *after* the winner
crosses and ends **0.88 s before** the fourth and fifth arrive together, so it
cannot be on screen during the close finish. It tracks the marble by projection,
not by hand.

**FROM 6TH → 1ST**, 19.217–19.867 s, in dark letters on a light halo.

### Two placement errors the frames found

**The ring was on the wrong side of the marble.** `project` copied
`cameras.frame_report`'s screen-right vector, which is written as
`(forward.z, 0, -forward.x)` — the negative of `cross(forward, up)`.
`frame_report` is right to: it only ever compares absolute values, and flipping
`right` flips `up` with it. Placing a *pixel* is the first thing that can tell
left from right, and the first rendered frame showed the mark 98 px off.

**The end fact was gold on a lit deck.** The hook works in gold because it sits
on unlit mountain; the fact does not, because it sits on the finish arena.
Measured over the last second the background under every candidate band runs
130–159 luma — cream, checker and channel all bright — against gold's 205. It is
now dark letters on a warm halo, which is also the machine's own idiom: the
FINISH gantry the racers have just passed under is dark letterforms on a lit
panel.

Its baseline moved 1255 → 1395 for a second measured reason. The sixth racer is
still descending through the whole window and reaches y 1151 on the final frame;
the parked finishers start at y 1586. The clear band is **1152–1586**, and 1255
grazed the sixth racer by 1.4 px. The new baseline centres the line in the band
with about 140 px of air either side.

Both marks are inside a phone-safe gutter — PICK ONE spans x 95–988, the fact
x 105–976, each about nine per cent in from the edge.

### No route labels

The brief allows small BLUE and ORANGE marks at the branch entrances if the
footage needs them. It does not: the fork's structure is already colour-coded in
the geometry, a blue gantry on one arm and an amber one on the other. Measured,
the two branch entries also swim across the frame during the shot — blue's from
(214, 905) to (592, 1303), orange's from (728, 991) to (532, 785), crossing over
each other on the way, with the blue lead-in leaving the frame entirely — so a
pinned label would wander through the picture and sometimes off it. The split is
marked in the sound instead.

## QC

`tools/sloped_short_qc.py`, 18 checks, all passing: format, frame count,
runtime, stream layout, true peak, the crossing hierarchy, the limiter, black
frames, duplicate frames, the hold, and the three overlay windows against
measured marble positions.

**Duplicates are a pixel question and mean luma cannot answer it.** The first
version of that check called two frames identical when their `YAVG` matched and
reported duplicates at 17.98 s and 19.82 s. Compared properly the pairs differ
in **778 930** and **726 555** pixels. `mpdecimate` is now asked instead, and
the hold is verified as a still picture below the hook — not by bit-equality,
because h.264 is lossy, but by the character of the difference: mean 0.0139 with
0.08% of pixels off by more than two, which is noise spread evenly rather than a
region that moved.

## Tests

`tests/test_sloped_short.py`, 22 tests. The suite is otherwise unchanged: 342
passing against 320 before, with the same 20 failures and 22 errors, all of them
`ModuleNotFoundError: pybullet` in this worktree's interpreter.
`tests/test_soundtrack.py` additionally needs `pymunk` and does not collect
here; neither gap is new.

## What was not changed

Physics, seed 5432, the replay, course geometry, the edit map, every camera
pose, the start module, the fork, the merge, the finish camera, and
`real_race_v19.mp4` itself.
