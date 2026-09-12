# V18 — the edit

Status: **a presentation edit of the exact seed-5432 replay.** No physics, no
course geometry, no re-simulation. The replay's state digest is still
`aafb0d3d872e6c5f6db3a6f52d567ae073f1888fbac4ea4970867c130cf17de6`, and V18
changes only which windows of it are shown and through which lens.

    output/sloped_race_v1/real_race_v18.mp4
    1080x1920, 60 fps, no audio, 1150 frames = 19.17 s, 28.7 MiB
    19.15 s kept of a 45.00 s replay; 4.25 s of it omitted by two cuts

## A cut list is not an edit

`SECTIONS` tiles the replay: every second the physics ran is a second of video
and the only decision left is which lens is on. That is right for a proof and
wrong for a film — the selected race spends three and a half seconds mixing
eight marbles in a drum, which is worth one look and not a fifth of the running
time.

So `sloped.cameras` gains an **edit**: a list of `(lens, replay from, replay to)`
windows that need not touch, plus optional lens overrides. The track then
carries an **edit map** from output time to replay time, and every segment of it
has **slope exactly one**. Between two windows the map steps — that is the cut —
and inside one it runs at the rate PyBullet produced. Nothing can be sped up or
slowed down by construction, which is what
`test_the_edit_never_changes_the_rate` pins.

`sloped_race_scene.replay_at()` applies the map; the renderer already walked
output time, so nothing else in the chain changed. Without an edit the map is
the identity and every earlier render reproduces.

## What the edit does

    lens        output          replay        note
    start        0.00- 2.10      0.20- 2.30   opens on the eight on the line
    start        2.10- 4.02      5.70- 7.62   after the cut: the trapdoor
    descent      4.02- 5.02      7.62- 8.62
    long         5.02- 6.20      8.62- 9.80
    hairpin      6.20- 7.20      9.80-10.80
    straight     7.20- 8.40     10.80-12.00
    obstacle     8.40-10.90     12.00-14.50   3.37 s trimmed to 2.50
    split       10.90-13.22     15.35-17.67   V17's fork shot, unchanged
    branch      13.22-14.62     17.67-19.07
    merge       14.62-15.75     19.07-20.20
    finish      15.75-19.15     20.20-23.60   rebuilt, and the longest shot

* **No establishing shot.** It was 0.95 s of a course 205 units away with the
  field 14 pixels across — a title card rather than a race. The film opens on
  the eight racers in their bays.
* **Two seconds of the line, then the cut.** `ShuffleFloor` mixes from 1.6 s to
  4.6 s and settles to 5.8; the edit drops **3.40 s** of that and returns just
  before the floor opens at 6.10, so the trapdoor and the drop are both on
  screen. The lens is the same on both sides of the cut, so it reads as a skip
  within one shot rather than a change of viewpoint.
* **The spinner corridor** goes 3.37 s to 2.50 s — enough to read the busiest
  thing on the course without dwelling on it.
* **The fork shot is V17's**, untouched: a fixed aim on the divider held over
  both of this seed's decisions, orange at 16.07 s and blue at 17.17 s.

## The finish, rebuilt

V17 framed the leading pair at an extent of 24 because the pair straddles 5.3
layout units and a portrait frame is narrow. That was correct and it made the
marbles small and the line distant.

The answer was not a wider lens but a **lower, closer one almost directly
behind**: at a bearing of 170 and an elevation of 12 the sprint recedes up the
frame, which is the one direction a 1080x1920 frame has to spare, so the pair
and the line they are running at both fit across **13 units instead of 24**. The
winner is about 150 px across at the crossing and the finish deck fills the
upper third.

It runs 20.20 to 23.60 s of replay — the longest shot in the film — so the
0.283 s between first and second and the 0.017 s between fourth and fifth are
both inside it, and it ends 0.95 s after the fifth racer lands.

## One defect the tests caught

Lengthening the finish to start at 20.20 while `merge` still ended at 20.30 left
**0.1 s of replay shown twice** — a backwards step in the map and a visible
stutter. `test_the_map_is_monotone_and_tiles_the_output` failed on it before
anything was rendered. The seam is closed.
